# BearerTokenAccessDeniedHandler và phản hồi thiếu quyền

Khi một ứng dụng **Spring Security OAuth 2.0 / OIDC Resource Server** nhận Bearer access token, có hai câu hỏi bảo mật khác nhau: **token có xác thực được không** và **chủ thể đã xác thực có đủ quyền thực hiện thao tác không**. Nếu token hợp lệ nhưng quyền không đủ, API thường cần trả **HTTP 403 Forbidden**. Với Bearer token, phản hồi còn có thể mang header **`WWW-Authenticate`** theo **RFC 6750**, nêu lỗi `insufficient_scope` để Client hiểu rằng credential hiện tại không cung cấp quyền cần thiết.

Spring Security cung cấp **`BearerTokenAccessDeniedHandler`** để xử lý tình huống `AccessDeniedException` trong Resource Server. Đây là một **`AccessDeniedHandler`**, không phải thành phần giải mã JWT, không phải nơi tính scope và cũng không phải nơi xác định user được xem đơn hàng nào. Nó phụ trách **biểu diễn việc truy cập bị từ chối thành phản hồi HTTP phù hợp với Bearer authentication**.

Ví dụ Shop Web đã có access token hợp lệ chỉ mang scope `orders.read`:

~~~http
POST /api/orders/42/cancel HTTP/1.1
Host: orders.example.test
Authorization: Bearer <valid-access-token-with-orders.read>
~~~

Orders API yêu cầu `SCOPE_orders.cancel` cho endpoint hủy đơn. Token đã được xác minh nhưng thiếu authority này, vì vậy **không được thực hiện thao tác hủy**. Một phản hồi minh họa:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
~~~

Tùy phiên bản/cấu hình, header thực tế có thể bổ sung `error_description` và `error_uri`. Không được suy ra handler mặc định sẽ luôn chỉ rõ chính xác scope đang thiếu hoặc tự sinh JSON body.

> **Điểm cần nhớ:** `BearerTokenAccessDeniedHandler` được gọi khi authorization từ chối quyền. Nó giúp xuất **403 và Bearer challenge** phù hợp. **`BearerTokenAuthenticationEntryPoint`** lại phục vụ những trường hợp cần bắt đầu authentication hoặc authentication không hợp lệ, thường tạo **401**. Hai thành phần giải quyết **hai loại thất bại khác nhau**.

## 1. Bối cảnh: OAuth2 Client, Authorization Server và Resource Server

Giả sử hệ thống bán hàng gồm:

- **Identity Server:** Authorization Server phát hành signed JWT hoặc opaque OAuth 2.0 access token.
- **Shop Web:** OAuth2/OIDC Client xin access token và gọi API thay mặt người dùng.
- **Orders API:** Spring Security Resource Server bảo vệ đơn hàng.
- **Order Service/Database:** thực thi quy tắc ownership, tenant, trạng thái đơn và phân công nhân viên.

Một hợp đồng quyền:

| Request | Authority tối thiểu | Điều kiện nghiệp vụ bổ sung |
| --- | --- | --- |
| `GET /api/orders/42` | `SCOPE_orders.read` | Caller được xem đơn 42 |
| `POST /api/orders` | `SCOPE_orders.write` | Được tạo đơn trong tenant hiện tại |
| `POST /api/orders/42/cancel` | `SCOPE_orders.cancel` | Đúng owner/role và đơn còn hủy được |
| `GET /api/public/catalog` | Không yêu cầu Bearer token | Chỉ hiển thị dữ liệu công khai |

Khi kiểm tra Bearer access token, **authentication** phải xác minh token theo hợp đồng AS/API: chữ ký và `iss`/`aud`/thời hạn đối với JWT, hoặc `active` và resource binding đối với opaque token qua introspection. Sau đó **authorization** mới so scope/authority và quyền trên bản ghi.

~~~mermaid
flowchart TD
    A["HTTP request + Bearer token"]
    B["BearerTokenAuthenticationFilter"]
    C["JWT verification hoặc opaque introspection"]
    D{"Có Authentication hợp lệ?"}
    E["BearerTokenAuthenticationEntryPoint<br>401 (authentication)"]
    F["AuthorizationFilter / method security"]
    G{"Có đủ authority và policy?"}
    H["AccessDeniedException"]
    I["BearerTokenAccessDeniedHandler<br>403 + WWW-Authenticate"]
    J["Controller / service thực thi"]

    A --> B --> C --> D
    D -->|Không| E
    D -->|Có| F --> G
    G -->|Không| H --> I
    G -->|Có| J
~~~

Đây là **luồng khái niệm**: một số request public không bắt buộc token; lỗi và vị trí xử lý có thể thay đổi theo filter chain, exception handler, phiên bản Spring Security và cách tích hợp. Điểm cốt lõi là **không gọi nghiệp vụ protected khi authentication/authorization chưa đạt**.

## 2. Phân biệt authentication failure và access denied

Một API có thể trả cùng loại thông báo “không được phép”, nhưng nguyên nhân rất khác.

| Tình huống | Lớp cần xử lý | HTTP điển hình | Bearer error thường gặp |
| --- | --- | --- | --- |
| Không gửi token tới endpoint protected | Authentication | **401** | Challenge `Bearer`, có thể không có `error` |
| Token sai chữ ký, không active hoặc hết hạn | Authentication | **401** | `invalid_token` khi áp dụng |
| Token malformed / yêu cầu Bearer sai quy tắc | Authentication | Có thể 400/401 theo lỗi và framework | `invalid_request` hoặc lỗi khác theo RFC |
| Token hợp lệ, thiếu scope endpoint | Authorization | **403** | `insufficient_scope` |
| Token hợp lệ, scope có nhưng thiếu role/permission | Authorization | **403** | Có thể `insufficient_scope` dưới Bearer handler, dù nguyên nhân là permission |
| Token hợp lệ, đủ scope nhưng sai tenant/owner | Resource policy | **403** hoặc **404** theo hợp đồng | Phụ thuộc cách policy và error handling được thiết kế |
| API gọi JWKS/introspection bị timeout | Authentication dependency | Tùy exception handling | Không được giả vờ token hợp lệ |

**401 không phải là “403 ở mức nghiêm trọng hơn”**. Nó chỉ ra rằng Client cần cung cấp credential được chấp nhận; còn **403** chỉ ra rằng request đã đến ranh giới quyền nhưng bị từ chối. Không tự động trả 401 cho mọi trường hợp thiếu scope vì điều đó có thể khiến Client lặp đăng nhập/refresh token vô ích.

### 2.1. Hai exception path trong Spring Security

**`AuthenticationException`** biểu diễn lỗi xác thực. Một Resource Server thường dùng `AuthenticationEntryPoint` để phát challenge tương ứng:

~~~java
BearerTokenAuthenticationEntryPoint authenticationEntryPoint =
        new BearerTokenAuthenticationEntryPoint();
~~~

**`AccessDeniedException`** biểu diễn quyền bị từ chối sau khi policy xét request:

~~~java
BearerTokenAccessDeniedHandler accessDeniedHandler =
        new BearerTokenAccessDeniedHandler();
~~~

Trong filter chain, `ExceptionTranslationFilter` đóng vai trò chuyển các exception bảo mật thành response thông qua entry point hoặc access denied handler. Nếu caller chưa có authentication đáng tin trong ngữ cảnh được bảo vệ, một `AccessDeniedException` cũng có thể khiến entry point được sử dụng thay vì 403. Việc phân nhánh phụ thuộc ngữ cảnh authentication và các filter được cấu hình.

**Không nên tự ném `AccessDeniedException` chỉ để tạo status 403 trước khi xác thực token**. Để bộ lọc Bearer và provider xác thực đảm nhận token invalid/missing; policy mới quyết định quyền.

## 3. RFC 6750: Bearer challenge và `insufficient_scope`

**RFC 6750 — OAuth 2.0 Bearer Token Usage** mô tả cách Client trình Bearer token và cách Resource Server phản hồi một số lỗi. Header `WWW-Authenticate` dùng authentication scheme `Bearer` và có thể chứa các tham số:

| Tham số | Mục đích | Lưu ý |
| --- | --- | --- |
| `realm` | Miền bảo vệ được công bố | Có thể cấu hình; không bắt buộc mọi response có |
| `error` | Mã lỗi Bearer | Ví dụ `invalid_token`, `insufficient_scope` |
| `error_description` | Mô tả ngắn, hướng đến Client | Không tiết lộ token, dữ liệu nội bộ hay danh tính người khác |
| `error_uri` | URI tài liệu giải thích lỗi | Có thể dẫn đến phần đặc tả liên quan |
| `scope` | Gợi ý phạm vi scope cần thiết | Theo RFC là tùy chọn, không được suy rằng Spring handler mặc định tự tính nó |

Đối với lỗi quyền:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Một phiên bản có cấu hình realm có thể trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", error_description="The request requires higher privileges than provided by the access token."
~~~

Đây là **ví dụ**; thứ tự tham số, `error_description` và `error_uri` có thể khác trong phiên bản thực tế. Hãy kiểm thử đúng response của phiên bản Spring Security đang triển khai.

### 3.1. `insufficient_scope` không có nghĩa “scope được sửa”

Mã lỗi `insufficient_scope` nói rằng **credential không cung cấp đủ quyền để đáp ứng request**. Nó **không** tự:

- Xin scope bổ sung từ Authorization Server.
- Refresh access token.
- Thêm authority vào `SecurityContext`.
- Chuyển role thành scope.
- Thay đổi quyền trong database.
- Xóa hoặc thu hồi access token.
- Trả chính xác scope nào Client cần xin.

Client có thể dùng thông tin lỗi để quyết định **hiển thị thông báo thiếu quyền** hoặc bắt đầu **luồng xin thêm quyền có chủ đích** nếu sản phẩm và Authorization Server hỗ trợ. **Không nên tự động retry vô hạn hoặc tự ý yêu cầu scope cao hơn** chỉ vì nhận 403.

### 3.2. Header `WWW-Authenticate` có thể xuất hiện cả ở 401 và 403

Một suy nghĩ dễ nhầm là “`WWW-Authenticate` chỉ dùng với 401”. Trong Bearer protocol, `WWW-Authenticate` cũng có thể đi kèm **403** với `insufficient_scope`. Nó cung cấp thông tin lỗi theo authentication scheme, không đồng nghĩa server yêu cầu Client đăng nhập lại.

Ví dụ so sánh:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

và:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
~~~

Client nên phân biệt status và error code, không chỉ kiểm tra header có chứa chữ `Bearer`.

### 3.3. Có nên gửi tham số `scope`?

RFC 6750 cho phép Resource Server chỉ ra scope cần thiết bằng tham số `scope` trong lỗi `insufficient_scope` nếu phù hợp. Nhưng nhiều endpoint yêu cầu **role, permission, quyền dữ liệu hoặc nhiều điều kiện kết hợp**, không thể biểu diễn thành một chuỗi scope đơn giản.

**`BearerTokenAccessDeniedHandler` mặc định không tự phân tích toàn bộ `SecurityFilterChain` để biết “scope bị thiếu”**. Nếu muốn gửi `scope="orders.cancel"`, cần một thiết kế custom với dữ liệu đáng tin về requirement của endpoint, cân nhắc nguy cơ tiết lộ chi tiết policy. Không tự nhét vào header giá trị do Client gửi hoặc exception message chứa dữ liệu nội bộ.

## 4. `BearerTokenAccessDeniedHandler` thực sự làm gì?

`BearerTokenAccessDeniedHandler` là một triển khai của `AccessDeniedHandler` trong Spring Security OAuth2 Resource Server:

~~~java
import org.springframework.security.oauth2.server.resource.web.access
        .BearerTokenAccessDeniedHandler;

BearerTokenAccessDeniedHandler handler =
        new BearerTokenAccessDeniedHandler();
~~~

Khi `handle(request, response, accessDeniedException)` được gọi, mục đích của nó là:

1. Đặt **HTTP 403 Forbidden** cho request bị từ chối.
2. Tạo hoặc bổ sung **`WWW-Authenticate: Bearer ...`** phù hợp.
3. Khi Spring Security xác định request có OAuth2 authentication hợp lệ trong ngữ cảnh Bearer, sử dụng thông tin `insufficient_scope` theo RFC 6750.
4. Nếu không xác định được ngữ cảnh Bearer authentication hợp lệ, không được mặc định khẳng định thiếu scope; response có thể chỉ gồm Bearer challenge hoặc 403 chung theo cách implementation xử lý.

Các lớp handler **không chịu trách nhiệm**:

- Xác minh chữ ký JWT bằng JWKS.
- Introspect opaque token.
- Chọn `SecurityFilterChain` hoặc so sánh `requestMatchers`.
- Map `scope` hoặc nested roles thành `GrantedAuthority`.
- Quyết định owner/tenant của một Order.
- Tạo JSON body nghiệp vụ mặc định theo mẫu của ứng dụng.

### 4.1. Handler không phải authorization decision maker

Ví dụ:

~~~java
.requestMatchers(HttpMethod.POST, "/api/orders/{id}/cancel")
    .hasAuthority("SCOPE_orders.cancel")
~~~

Chính rule `hasAuthority(...)` quyết định caller có quyền gọi URL hay không. Nếu không có authority yêu cầu, Spring Security có thể phát `AccessDeniedException`. **`BearerTokenAccessDeniedHandler` phản ánh quyết định đó ra HTTP 403**, chứ không thay rule.

Nếu developer bỏ rule `hasAuthority` nhưng vẫn giữ handler, endpoint có thể vô tình được mở vì **không còn một quyết định deny để gọi handler**. Đây là lý do phải kiểm thử cả đường cho phép và đường bị từ chối.

### 4.2. `setRealmName`

Có thể cấu hình realm để challenge của API có định danh dễ nhận biết:

~~~java
BearerTokenAccessDeniedHandler deniedHandler =
        new BearerTokenAccessDeniedHandler();
deniedHandler.setRealmName("orders-api");
~~~

Realm là một **nhãn bảo vệ**, không phải JWT audience, OAuth2 Client ID, issuer hay tên role. Việc đặt `realm="orders-api"` **không tự kiểm tra `aud`** của token. API vẫn phải validate audience/resource theo hợp đồng.

### 4.3. Khác với `BearerTokenAuthenticationEntryPoint`

| Thành phần | Kiểu | Được dùng cho | Status điển hình |
| --- | --- | --- | --- |
| `BearerTokenAuthenticationEntryPoint` | `AuthenticationEntryPoint` | Request cần authentication hoặc token không hợp lệ | 401 |
| `BearerTokenAccessDeniedHandler` | `AccessDeniedHandler` | Request bị từ chối bởi authorization | 403 |

Hai handler có thể cùng dùng realm nhưng không thay thế nhau. Nếu dùng entry point để xử lý thiếu scope, API dễ trả **401** thay vì **403**. Nếu dùng access denied handler để xử lý mọi lỗi token malformed, Client dễ nhận thông báo `insufficient_scope` sai bản chất.

## 5. Phản hồi mặc định với JWT Resource Server

Ví dụ ký hiệu một JWT access token đã được xác minh có:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893459600
}
~~~

Trong Spring Security JWT Resource Server, claim `scope` thường được ánh xạ thành:

~~~text
SCOPE_orders.read
~~~

Giả sử endpoint hủy đơn yêu cầu:

~~~java
hasAuthority("SCOPE_orders.cancel")
~~~

Kết quả:

~~~text
Authentication: hợp lệ
JWT issuer/audience/time: được xác minh
GrantedAuthorities: [SCOPE_orders.read]
Rule endpoint: yêu cầu SCOPE_orders.cancel
Authorization: bị từ chối
BearerTokenAccessDeniedHandler: xuất phản hồi 403
WWW-Authenticate: Bearer ... insufficient_scope ...
~~~

**Token được ký đúng không có nghĩa token có đủ quyền**. Tương tự, **scope `orders.read` không đương nhiên bao hàm `orders.cancel`**, trừ khi chính sách AS/API quy định một quan hệ bao hàm và hệ thống thực thi quy tắc đó đúng.

### 5.1. Opaque token cũng có thể đi qua handler này

Với opaque access token, `OpaqueTokenIntrospector` có thể trả:

~~~json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "user-842"
}
~~~

Sau introspection, Spring Security tạo một dạng OAuth2 Bearer authentication cùng authorities thích hợp. Nếu HTTP rule yêu cầu `SCOPE_orders.cancel`, request cũng có thể bị từ chối bằng `BearerTokenAccessDeniedHandler`. Handler **không cần biết** token đã được xác minh bằng JWS hay introspection; nó được sử dụng ở **lớp phản hồi authorization**.

Tuy nhiên, scope, issuer, audience, active và claims bắt buộc phải được xử lý trước theo hợp đồng. **Không coi active=true hoặc signature hợp lệ là được phép thực hiện mọi request**.

## 6. Cấu hình Spring Boot 3 / Spring Security 6

Ví dụ Orders API dùng signed JWT access token.

### 6.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 6.2. Cấu hình nguồn xác minh token

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}
~~~

Ví dụ:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
~~~

URI chỉ minh họa. Bên cạnh issuer, ứng dụng cần bảo đảm **audience đúng Orders API**, token type/profile, thuật toán và thời hạn theo hợp đồng. `BearerTokenAccessDeniedHandler` không bổ sung các JWT validators ấy. Nếu tự dựng `JwtDecoder`, phải cấu hình validators đúng và không thay chúng bằng logic của response handler.

### 6.3. SecurityFilterChain có Bearer handlers

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access
        .BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        BearerTokenAuthenticationEntryPoint entryPoint =
                new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler deniedHandler =
                new BearerTokenAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.POST,
                        "/api/orders/{id}/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().denyAll())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Điểm cần chú ý:

- `oauth2ResourceServer().jwt()` bật pipeline Bearer JWT authentication.
- `authenticationEntryPoint(...)` định dạng lỗi khi authentication thất bại, phổ biến là **401**.
- `accessDeniedHandler(...)` định dạng lỗi thiếu quyền, phổ biến là **403**.
- `requestMatchers` **đưa ra quyết định** quyền theo method và URL.
- `anyRequest().denyAll()` trong chain chặn các API route chưa được cấp.
- Realm chỉ là nhãn challenge, không tạo quyền hay validate audience.

Trong cấu hình Resource Server chuẩn, Spring Security thường thiết lập các Bearer entry point/denied handler phù hợp khi không bị override. **Cấu hình tường minh** ở đây giúp nhìn rõ chức năng và có nơi tùy biến. Không nhất thiết phải tạo lại handler trong mọi ứng dụng; quan trọng là đừng vô tình thay mất hành vi Bearer khi đưa exception handler khác vào.

Ví dụ này chỉ dành cho REST API **xác thực bằng Bearer token trong header**, không dùng session cookie cho `/api/**`; do đó chain tắt CSRF và dùng stateless session. Ứng dụng có web UI/session cần cấu hình CSRF/filter chain phù hợp. Ngoài ra, `securityMatcher("/api/**")` chỉ bao phủ `/api/**`; phải có policy/chain khác cho endpoint ngoài phạm vi này.

### 6.4. Biến thể opaque token

Nếu Resource Server dùng token introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Trong SecurityFilterChain, thay phần JWT bằng:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

**Đây là một cấu hình thay thế**, không phải thêm hai pipeline rồi mặc định framework tự đoán loại token. Access denied handler vẫn phản hồi lỗi thiếu quyền sau khi token opaque đã được introspect và authentication hợp lệ.

## 7. Phân tích tình huống HTTP cụ thể

Giả sử `GET /api/orders/{id}` yêu cầu `orders.read` và `POST /api/orders/{id}/cancel` yêu cầu `orders.cancel`.

### 7.1. Không gửi Bearer token

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
~~~

Đây là lỗi **authentication chưa có**, không phải lỗi thiếu scope của một token đã xác minh. API thường phản hồi:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

**`BearerTokenAuthenticationEntryPoint`** là thành phần phù hợp. Không nên trả `insufficient_scope` vì caller chưa cung cấp token để hệ thống đánh giá quyền.

### 7.2. JWT hết hạn, sai chữ ký hoặc issuer/audience

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <invalid-or-expired-token>
~~~

`JwtDecoder` hoặc một validator hợp đồng từ chối token. Đây là **authentication failure**, thường dẫn đến 401 và có thể mang `invalid_token`. Client có thể cần lấy access token mới **theo luồng OAuth hợp lệ**. Không đưa chi tiết private key, claims nhạy cảm hay stack trace vào response.

### 7.3. Token hợp lệ nhưng scope không đủ

~~~http
POST /api/orders/42/cancel HTTP/1.1
Authorization: Bearer <valid-token-with-only-orders.read>
~~~

Token được xác minh, nhưng authority thiếu `SCOPE_orders.cancel`. Đây là **access denied**, phổ biến:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
~~~

Không được hủy đơn 42 hoặc phát event hủy đơn nếu request bị từ chối.

### 7.4. Token hợp lệ và đủ scope nhưng quyền dữ liệu bị từ chối

Caller có `orders.read`, nhưng Order 42 thuộc tenant khác:

~~~text
Authentication: success
HTTP scope: success
Data policy: denied (tenant mismatch)
~~~

Nếu policy ném `AccessDeniedException` và đi qua exception handling Bearer, response có thể là **403**, đôi khi mang `insufficient_scope` do handler nhận diện một OAuth2 Authentication đã có. Điều đó **không chứng minh nguyên nhân thật là thiếu OAuth scope**: nó có thể là role, owner, tenant hoặc trạng thái dữ liệu.

Nếu API muốn tránh tiết lộ sự tồn tại của Order 42, có thể cố ý trả **404** theo chính sách thống nhất. Một `AccessDeniedHandler` chung không tự quyết định chính sách 403-vs-404 cho từng tài nguyên. Nhóm phát triển phải thiết kế resource policy và cách map exception rõ ràng, không cho Client suy ra thông tin người khác từ mô tả lỗi.

### 7.5. Endpoint public

~~~http
GET /api/public/catalog HTTP/1.1
~~~

`permitAll()` cho phép request không cần authentication. Tuy vậy, việc gửi **Bearer token bị hỏng** tới endpoint public vẫn có thể khiến Bearer filter xử lý token và trả lỗi trước khi đến rule public; không nên kết luận `permitAll()` bỏ qua toàn bộ filter. Test public nên có trường hợp **không gửi Authorization header**.

## 8. `insufficient_scope` và `hasRole`, `hasAuthority`

Spring Security kiểm tra `GrantedAuthority`. Với JWT Resource Server, `JwtGrantedAuthoritiesConverter` mặc định thường ánh xạ claim `scope` hoặc `scp` sang authorities có prefix `SCOPE_`:

~~~json
{
  "sub": "user-842",
  "scope": "orders.read orders.write"
}
~~~

thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Quy tắc:

~~~java
hasAuthority("SCOPE_orders.cancel")
~~~

khác với:

~~~java
hasAuthority("orders.cancel")
~~~

Nếu ứng dụng dùng role:

~~~java
hasRole("ORDER_SUPPORT")
~~~

Spring Security thường đối chiếu `ROLE_ORDER_SUPPORT` theo quy ước role prefix. **`BearerTokenAccessDeniedHandler` không ánh xạ hay sửa prefix**. Nếu role được đặt trong nested claims, phải có converter theo hợp đồng; nếu không, API có thể liên tục trả 403 dù token mang một chuỗi `order_support` mà backend chưa chuyển thành authority.

### 8.1. Thiếu OAuth scope hay thiếu quyền nghiệp vụ?

| Rule | Nguồn dữ liệu quyền | Khi bị deny |
| --- | --- | --- |
| `hasAuthority("SCOPE_orders.read")` | OAuth scope được ánh xạ từ token | Phù hợp ngữ nghĩa `insufficient_scope` |
| `hasAuthority("ROLE_ORDER_SUPPORT")` | Role mapping theo hợp đồng | 403; handler có thể vẫn dùng mã `insufficient_scope` tổng quát |
| `hasAuthority("PERM_order:cancel:own")` | Permission custom từ token/policy | 403; không nhất thiết thiếu OAuth scope |
| `@orderAccess.canRead(authentication, id)` | Tenant/owner/dữ liệu thực tế | 403 hoặc 404 theo chính sách |

Nếu cần báo lỗi chi tiết giữa “thiếu scope” và “không sở hữu đơn”, phải **thiết kế taxonomy lỗi nghiệp vụ** riêng mà không để lộ thông tin nhạy cảm. Không nên làm toàn bộ exception handler suy đoán nguyên nhân chỉ dựa trên chuỗi `AccessDeniedException.getMessage()`.

## 9. Tùy chỉnh body JSON mà vẫn giữ `WWW-Authenticate`

Nhiều REST API muốn phản hồi JSON theo `application/problem+json` hoặc một schema lỗi thống nhất. Một cách làm là **ủy quyền `BearerTokenAccessDeniedHandler` thiết lập status/header trước**, sau đó thêm body JSON công khai.

### 9.1. Sai lầm khi thay handler bằng response JSON thuần

Ví dụ:

~~~java
// Không nên dùng nếu làm mất Bearer challenge bắt buộc theo hợp đồng.
response.setStatus(403);
response.setContentType("application/json");
response.getWriter().write("{\"error\":\"forbidden\"}");
~~~

Code này có thể trả 403, nhưng không xuất `WWW-Authenticate` theo RFC 6750. Một OAuth2 Client hoặc API gateway đang dựa vào header Bearer có thể mất thông tin để xử lý lỗi.

### 9.2. Handler bao ngoài handler chuẩn

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web.access
        .BearerTokenAccessDeniedHandler;

public final class JsonBearerAccessDeniedHandler {

    public static AccessDeniedHandler create() {
        BearerTokenAccessDeniedHandler delegate =
                new BearerTokenAccessDeniedHandler();
        delegate.setRealmName("orders-api");

        return (request, response, exception) -> {
            // Delegate ghi 403 và WWW-Authenticate Bearer phù hợp.
            delegate.handle(request, response, exception);

            if (!response.isCommitted()) {
                response.setCharacterEncoding(
                        StandardCharsets.UTF_8.name());
                response.setContentType("application/problem+json");
                response.getWriter().write("""
                    {
                      "type": "about:blank",
                      "title": "Forbidden",
                      "status": 403,
                      "detail": "You do not have permission to perform this action."
                    }
                    """);
            }
        };
    }

    private JsonBearerAccessDeniedHandler() {}
}
~~~

Code minh họa dùng **Java 17+ text blocks**. `delegate` chịu trách nhiệm status và Bearer header; body JSON chỉ đưa một thông báo **chung**, không tiết lộ token, object ID của người khác hoặc tên permission nội bộ. Trong production có thể bổ sung request/correlation ID theo cơ chế ứng dụng.

Gắn vào filter chain:

~~~java
.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(entryPoint)
    .accessDeniedHandler(
        JsonBearerAccessDeniedHandler.create()))
~~~

Đây là **biến thể thay thế `accessDeniedHandler(deniedHandler)`** ở cấu hình mục 6, không khai báo cả hai rồi mong chúng đều được gọi.

### 9.3. Cân nhắc khi thêm JSON

- **Giữ nguyên status 403** và header Bearer do delegate tạo.
- Không viết response body **trước** khi delegate thiết lập header.
- Không gọi `sendError(...)` sau khi đã ghi JSON vì response có thể đã committed hoặc bị container thay body.
- Không dùng exception message từ framework làm `detail` trả Client nếu nó chứa thông tin nội bộ.
- Đảm bảo body là JSON hợp lệ, encoding đúng UTF-8, không có lỗi escape dữ liệu.
- Nếu ứng dụng dùng schema lỗi có `code`, tránh nhầm OAuth protocol error `insufficient_scope` với business error code.
- Với endpoint cần **404 để che giấu tài nguyên**, đừng ép mọi business denial đi qua handler 403 chung.

Một response có thể là:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to perform this action."
}
~~~

Đây là response minh họa cho tùy chỉnh JSON, **không phải body mặc định của `BearerTokenAccessDeniedHandler`**.

## 10. Tùy chỉnh response authentication 401 phải tách riêng

Nếu API cũng cần JSON body cho lỗi 401, phải xử lý `AuthenticationEntryPoint` (hoặc cơ chế response authentication error được framework hỗ trợ), không chỉ sửa `AccessDeniedHandler`.

Một entry point chuẩn:

~~~java
BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();
entryPoint.setRealmName("orders-api");
~~~

Khác biệt quan trọng:

~~~text
401 -> chưa có credential được chấp nhận
403 -> authentication có thể đã hợp lệ nhưng quyền bị từ chối
~~~

Nếu muốn dùng cùng một schema JSON cho cả 401 và 403, có thể viết **hai wrappers riêng** quanh entry point và access denied handler. Không nên trộn mọi exception thành một JSON `{"status":403}` khiến Client không biết nó cần lấy token mới hay dừng do thiếu quyền.

### 10.1. Không tiết lộ lý do chữ ký JWT sai

Response 401 không nên nói rằng “khóa private kid X của issuer Y không tồn tại” hoặc đưa nguyên JWT/header vào body. Những chi tiết này thuộc log bảo mật có kiểm soát và không nên trả cho Client. Phần lớn Client chỉ cần biết access token hiện tại không được chấp nhận và phải xử lý theo OAuth flow phù hợp.

### 10.2. Không khuyến khích refresh token vô hạn khi 403

Client nhận:

~~~http
403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

không nên tự động gửi refresh token nhiều lần mong scope tự tăng. Refresh token thường không tự cấp quyền mới vượt authorization grant và chính sách hiện tại. Nếu sản phẩm hỗ trợ **incremental authorization/consent**, Client có thể chủ động hướng người dùng qua luồng cấp quyền mới khi phù hợp, nhưng không tự leo thang quyền.

## 11. Multiple SecurityFilterChain và vị trí của handler

Một hệ thống có thể vừa có API Bearer JWT vừa có web UI dựa trên session cookie:

~~~text
Chain A @Order(1): /api/** -> Bearer Resource Server
Chain B @Order(2): /web/** -> Session login + CSRF
Chain C @Order(3): fallback -> denyAll
~~~

Không phải mọi request bị cấm đều nên nhận `WWW-Authenticate: Bearer`. Nếu một người dùng web session truy cập màn hình quản trị nhưng thiếu role, ứng dụng có thể muốn trả **403 HTML/JSON** theo chuẩn web session, không đưa Bearer challenge.

Vì vậy:

- Đặt `BearerTokenAccessDeniedHandler` trong **SecurityFilterChain bảo vệ API bằng Bearer token**.
- Đặt entry point/denied handler của web UI trong chain session tương ứng.
- Sắp xếp `@Order` và `securityMatcher` đúng để request đi vào **đúng chain**.
- Có fallback cho đường không được một chain nào bảo vệ, theo kiến trúc hệ thống.

### 11.1. Sai lầm: handler ở chain không bao phủ endpoint

Giả sử:

~~~java
.securityMatcher("/api/**")
.exceptionHandling(ex -> ex
    .accessDeniedHandler(new BearerTokenAccessDeniedHandler()))
~~~

Handler chỉ thuộc chain đó. `GET /internal/secrets` **không tự được bảo vệ** chỉ vì chain API có access denied handler. Nếu request không match chain, phải có chain khác hoặc policy server/gateway phù hợp.

### 11.2. Sai lầm: rule quá rộng không bao giờ gọi handler

~~~java
.requestMatchers("/api/**").permitAll()
.requestMatchers(HttpMethod.POST, "/api/orders/{id}/cancel")
    .hasAuthority("SCOPE_orders.cancel")
~~~

Một matcher rộng ở trước có thể cho request đi qua trước khi rule cancel được xét. Khi đó **handler không hề được gọi**, không phải vì handler lỗi mà vì authorization rule đã bị che. Bảo vệ bằng **rule cụ thể trước, default deny cuối**, kèm negative tests.

## 12. Kiểm thử 401/403 và header bằng MockMvc

Ở bước kiểm thử HTTP authorization, Spring Security Test cung cấp `SecurityMockMvcRequestPostProcessors.jwt()` để giả lập một `JwtAuthenticationToken` có authorities xác định. Nó giúp kiểm thử `hasAuthority` và access denied handler mà không cần khởi chạy Authorization Server.

**Lưu ý:** `jwt()` **không xác minh chữ ký hoặc issuer/audience/thời hạn**; test đó kiểm tra SecurityFilterChain và response cho authentication giả lập. Để kiểm tra `JwtDecoder`, cần integration test với **Bearer JWT được ký thật**.

### 12.1. Controller thử nghiệm

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class DemoOrdersController {

    @GetMapping("/orders/{id}")
    String read(@PathVariable String id) {
        return "order:" + id;
    }

    @PostMapping("/orders/{id}/cancel")
    String cancel(@PathVariable String id) {
        return "cancelled:" + id;
    }

    @GetMapping("/public/catalog")
    String catalog() {
        return "public";
    }
}
~~~

Controller này là **fixture**, không có database hay policy thực. Khi test business policy, cần controller/service thật hoặc mock service có assertion không side effect.

### 12.2. Test status và `WWW-Authenticate`

Ví dụ với **JUnit Jupiter**, `@WebMvcTest` và MockMvc:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = DemoOrdersController.class)
@Import({OrdersApiSecurity.class, BearerDeniedTest.TestDecoder.class})
class BearerDeniedTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class TestDecoder {
        @Bean
        JwtDecoder jwtDecoder() {
            // Cho phép test rule bằng jwt() mà không phải gọi JWKS.
            // KHÔNG dùng decoder này trong integration test chữ ký thật.
            return token -> {
                throw new JwtException(
                    "Real JWT verification is tested separately");
            };
        }
    }

    @Test
    void publicCatalogWorksWithoutToken() throws Exception {
        mvc.perform(get("/api/public/catalog"))
            .andExpect(status().isOk());
    }

    @Test
    void noTokenGetsBearerChallenge() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Bearer")));
    }

    @Test
    void readScopeCanRead() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void writeScopeCannotReadOrder() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("insufficient_scope")));
    }

    @Test
    void readScopeCannotCancel() throws Exception {
        mvc.perform(post("/api/orders/42/cancel")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("insufficient_scope")));
    }

    @Test
    void cancelScopeCanCancel() throws Exception {
        mvc.perform(post("/api/orders/42/cancel")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.cancel"))))
            .andExpect(status().isOk());
    }
}
~~~

Trong test, `OrdersApiSecurity` là cấu hình ở mục 6. `jwt()` gắn authentication giả lập cho request: đó là lý do test có thể qua filter bảo mật dù `TestDecoder` không xác minh JWT chuỗi thật. Với bản sử dụng Spring Security/MockMvc khác, cấu hình import/auto-config cần điều chỉnh cho phù hợp; phải bảo đảm **Spring Security filters đang được áp dụng**.

### 12.3. Vì sao assert `containsString("insufficient_scope")` thay vì nguyên header?

Spring Security có thể bổ sung `realm`, `error_description`, `error_uri` hoặc thay đổi thứ tự/chi tiết header theo phiên bản. Nếu mục tiêu test là **thiếu quyền → 403 + Bearer insufficient_scope**, assert các thuộc tính thiết yếu giúp test ít phụ thuộc biểu diễn không quan trọng.

Tuy nhiên, trong **contract test của API gateway hoặc Client**, có thể cần kiểm tra header đầy đủ đúng phiên bản đang dùng. Nên tách hai mức test:

- **Security behavior test:** 403, Bearer challenge, insufficient_scope.
- **HTTP contract test:** chính xác các tham số đã công bố và body schema nếu có.

### 12.4. Test no-token và thiếu-scope phải là hai test khác nhau

Nếu chỉ chạy:

~~~java
get("/api/orders/42").with(jwt())
~~~

thì request đã có authentication giả lập và không kiểm tra được tình huống **không có token**. Tương tự, chỉ test 403 với một token thiếu authority không xác nhận entry point 401 đã hoạt động.

## 13. Unit test trực tiếp `BearerTokenAccessDeniedHandler`

Nếu muốn tách kiểm tra response handler khỏi HTTP route, có thể dùng `MockHttpServletRequest` và `MockHttpServletResponse` trong một test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.access
        .BearerTokenAccessDeniedHandler;

class BearerAccessDeniedHandlerTest {

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void returnsBearerInsufficientScopeForAuthenticatedJwt()
            throws Exception {

        Jwt jwt = Jwt.withTokenValue("test-only-not-a-signed-token")
                .header("alg", "RS256")
                .claim("sub", "user-842")
                .claim("scope", "orders.read")
                .build();

        JwtAuthenticationToken authentication =
                new JwtAuthenticationToken(
                    jwt,
                    List.of(new SimpleGrantedAuthority(
                        "SCOPE_orders.read")));
        SecurityContextHolder.getContext()
                .setAuthentication(authentication);

        var request = new MockHttpServletRequest();
        var response = new MockHttpServletResponse();

        var handler = new BearerTokenAccessDeniedHandler();
        handler.setRealmName("orders-api");
        handler.handle(request, response,
                new AccessDeniedException("Denied by policy"));

        assertEquals(403, response.getStatus());
        String challenge =
                response.getHeader(HttpHeaders.WWW_AUTHENTICATE);
        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Bearer"));
        assertTrue(challenge.contains("insufficient_scope"));
    }
}
~~~

Test này **chỉ kiểm tra handler với SecurityContext giả lập**. Nó không kiểm tra `JwtDecoder`, JWS signature, issuer/audience hay cách một URL tạo ra `AccessDeniedException`. Vì thế vẫn cần filter-chain test ở mục 12 và signed-token integration test ở mục 14.

Trong một request thực, Spring Security chỉ nên coi JWT authentication hợp lệ sau khi token đã được decoder/provider xác minh. Unit test chủ động tạo authentication nên không phải bằng chứng cho tính xác thực token.

## 14. Integration test với Bearer JWT ký thật

`jwt()` rất tốt để thử rule nhưng **bỏ qua khâu cryptographic verification**. Test end-to-end cho Resource Server cần:

1. Sinh cặp RSA/EC test-only; chỉ dùng private key trong fixture.
2. Cấu hình mock JWKS endpoint công bố public key tương ứng.
3. Tạo JWT có chữ ký thật với `iss`, `aud`, `exp` và `scope` theo hợp đồng.
4. Gửi request mang header `Authorization: Bearer <signed-JWT>` qua filter chain thật.
5. Kiểm tra case đủ quyền → được qua, case thiếu scope → **403 + insufficient_scope**.
6. Kiểm tra case chữ ký/issuer/audience/hạn dùng sai → **authentication failure**, không được lầm thành 403 do thiếu scope.

Một ma trận:

| JWT / request | Xác thực token | Quyền endpoint | Kết quả cần kiểm tra |
| --- | --- | --- | --- |
| Chữ ký hợp lệ, `aud=orders-api`, scope `orders.cancel`, POST cancel | Thành công | Đủ | Qua security; nghiệp vụ quyết định tiếp |
| Chữ ký hợp lệ, scope chỉ `orders.read`, POST cancel | Thành công | Thiếu | **403**, Bearer insufficient_scope |
| Chữ ký hợp lệ, scope `orders.write`, GET order | Thành công | Thiếu | **403**, Bearer insufficient_scope |
| Chữ ký sai, scope ghi `orders.cancel` | Thất bại | Không được xét | **Không thể** chạy nghiệp vụ protected |
| JWT đã hết hạn | Thất bại | Không được xét | Thường 401/invalid_token |
| `iss` không được tin cậy | Thất bại | Không được xét | Thường 401 |
| `aud=billing-api` | Thất bại validation | Không được xét | Thường 401 |
| JWT đúng và đủ scope nhưng sai tenant | Thành công | HTTP scope đủ, policy dữ liệu từ chối | 403/404 theo hợp đồng |

Đặc biệt, khi token mang chuỗi `scope="orders.cancel"` nhưng **chữ ký không hợp lệ**, Resource Server phải từ chối ở **authentication**, không bao giờ xây `SCOPE_orders.cancel` từ payload chưa xác minh. Handler phản hồi thiếu quyền không được dùng như biện pháp thay thế việc xác thực token.

### 14.1. Với opaque token

Đường integration test tương tự nhưng thay JWT/JWKS bằng introspection mock:

~~~text
Bearer opaque token
  -> mock AS introspection POST
  -> active:true, audience đúng, scope orders.read
  -> GET orders => qua HTTP authorization
  -> POST cancel => 403 insufficient_scope
~~~

Thêm case `active:false`, audience sai, credential introspection sai, endpoint 503/timeout: **không có quyền nào được cấp khi không introspect được token hợp lệ**. Handler `BearerTokenAccessDeniedHandler` không phải nơi khắc phục lỗi introspection.

## 15. Kiểm thử negative paths và không có side effect

Một test tốt cho endpoint hủy đơn không dừng ở status:

~~~text
POST /api/orders/42/cancel
Bearer token hợp lệ nhưng thiếu SCOPE_orders.cancel

Kỳ vọng:
  - 403 Forbidden
  - WWW-Authenticate có Bearer insufficient_scope nếu áp dụng
  - OrderService.cancel(42) KHÔNG được gọi
  - Order 42 KHÔNG đổi trạng thái
  - KHÔNG có event OrderCancelled được phát
~~~

Đây là ranh giới rất quan trọng: có thể một ứng dụng trả 403 **sau khi** một service đã thay đổi dữ liệu vì exception handling sai vị trí. Khi đó test status vẫn pass nhưng bảo mật đã thất bại.

### 15.1. Test bằng mock service

Ví dụ ý tưởng kiểm tra side effect:

~~~java
// Sau khi gửi POST cancel với token chỉ có orders.read:
mockMvc.perform(post("/api/orders/42/cancel")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isForbidden());

verify(orderService, never()).cancel("42");
~~~

Đoạn trên là **phần thân test** có `orderService` được mock và import Mockito phù hợp. Trong integration test thực tế, cần kiểm tra database và event/outbox nếu thao tác có side effect. Điều kiện quan trọng là **phân quyền phải xảy ra trước hành động protected**.

### 15.2. Negative cases ngoài thiếu scope

| Negative case | Vì sao cần test? |
| --- | --- |
| Không token | Bảo đảm đường entry point 401 hoạt động |
| Bearer token hỏng | Không lầm lỗi authentication thành insufficient_scope |
| Token hợp lệ nhưng scope khác | Không vô tình cho quyền không liên quan |
| Token đủ scope nhưng URL chưa được khai báo | Bảo đảm default deny |
| Token đủ scope nhưng HTTP method khác | Không mở rộng quyền theo path |
| Token đủ scope nhưng tenant khác | Chặn Broken Object Level Authorization |
| Token role admin của resource khác | Không ánh xạ role chéo API |
| Endpoint ngoài `securityMatcher` | Bảo đảm chain/fallback bảo vệ |
| Custom JSON handler | Có 403, header và body đúng contract |

Không nên chỉ dùng một token “admin có tất cả quyền” trong test. Token quyền cao có thể khiến mọi route trả 200 nhưng không chứng minh boundary bị từ chối.

## 16. Mã lỗi cho Client: xử lý 401 khác 403

Client có thể dùng quy tắc:

~~~text
401:
  - credential bị thiếu hoặc không được chấp nhận
  - cân nhắc xin access token mới nếu luồng OAuth cho phép
  - nếu không thể, hướng người dùng đăng nhập/ủy quyền lại

403 + insufficient_scope:
  - credential hiện tại không đủ quyền
  - không retry y hệt vô hạn
  - hiển thị thiếu quyền hoặc quy trình xin thêm quyền có kiểm soát

403 khác:
  - caller không được phép theo chính sách hiện hành
  - có thể liên quan role, owner, tenant hoặc policy dữ liệu

404 theo policy bảo vệ resource:
  - không mặc nhiên suy ra tài nguyên tồn tại nhưng bị cấm
~~~

### 16.1. Ví dụ xử lý trong Client

Pseudocode:

~~~javascript
async function cancelOrder(orderId, accessToken) {
  const response = await fetch('/api/orders/' + orderId + '/cancel', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + accessToken }
  });

  if (response.status === 401) {
    // Chuyển sang luồng lấy token/đăng nhập theo hợp đồng ứng dụng.
    throw new Error('Authentication is required or has expired');
  }

  if (response.status === 403) {
    // Không mặc định refresh vô hạn; quyền có thể thực sự không được cấp.
    throw new Error('You do not have permission to cancel this order');
  }

  if (!response.ok) {
    throw new Error('Order cancellation failed');
  }
}
~~~

Đây là ví dụ **logic ứng dụng** chứ không phải đoạn code xử lý an toàn toàn bộ OAuth2 Client. Trong browser thực tế, việc lưu và sử dụng token phải tuân theo kiến trúc bảo mật của Client, CORS, CSRF nếu có session cookie, cơ chế refresh/reauthorization và chính sách người dùng.

### 16.2. Không ép Client tự xin scope cao hơn

Một API từ chối request có thể do chính sách tổ chức cố ý không cấp quyền cho caller. Việc Client nhận `insufficient_scope` không có nghĩa Client được tự thay request authorization để xin `orders.cancel` mà không có consent hoặc quyền của user/organization. Nếu có khả năng “request additional privileges”, đó phải là luồng đã thiết kế và được AS kiểm soát.

## 17. Quan sát, log và bảo mật thông tin lỗi

Khi debug `BearerTokenAccessDeniedHandler`, cần biết liệu lỗi đến từ:

- Authentication missing/invalid, dẫn đến entry point.
- Authentication hợp lệ nhưng thiếu authority.
- Method security thiếu permission hoặc role.
- Resource policy chặn owner/tenant.
- Matcher quá rộng/hẹp hoặc chain sai thứ tự.
- OAuth scope converter không tạo `SCOPE_...` đúng.

Những trường có thể log an toàn theo policy:

~~~text
request_id
method + normalized path
http_status
security_chain_name / logical policy
error_category: insufficient_authority / invalid_token / forbidden_resource
token_issuer (chỉ khi đã xác minh)
subject hoặc internal ID (theo chính sách audit/PII)
correlation_id
~~~

**Không log nguyên Bearer token**, client secret, refresh token, private key, full authorization header hoặc claims nhạy cảm không cần thiết. Không đưa token vào query parameter để “dễ trace”. Nếu ghi `kid`/`sub` chưa xác minh, phải coi chúng là dữ liệu do caller kiểm soát, tránh log injection hoặc metric cardinality quá cao.

### 17.1. Vì sao không trả danh sách role người dùng còn thiếu?

Một error body kiểu:

~~~json
{
  "requiredInternalRole": "SUPER_ADMIN",
  "allowedTenantIds": ["tenant-A", "tenant-B"],
  "hiddenPolicy": "fraud-team override"
}
~~~

có thể lộ logic quyền và dữ liệu tổ chức. Client thường chỉ cần biết **không đủ quyền**. Nếu cần hướng dẫn người dùng xin scope chính thức, cung cấp tài liệu public/API contract phù hợp; không echo toàn bộ policy nội bộ vào header/body.

### 17.2. Proxy và gateway có thể sửa header

Nếu SecurityFilterChain tạo `WWW-Authenticate` nhưng Client không thấy, kiểm tra reverse proxy/API gateway, CORS và các lớp error handling. Gateway có thể thay status/body hoặc gỡ header. Trong request cross-origin, JavaScript có thể cần cấu hình CORS `Access-Control-Expose-Headers` để **đọc** `WWW-Authenticate`; việc browser không cho JS đọc một response header không nhất thiết nghĩa header đã không tồn tại trên wire. Cần kiểm tra request từ Client được phép và policy CORS phù hợp.

## 18. Các lỗi triển khai thường gặp

### 18.1. Dùng handler thiếu quyền thay AuthenticationEntryPoint

Nếu request thiếu token mà API cố trả `403 insufficient_scope`, Client không phân biệt được cần xác thực hay đang thiếu quyền. Giữ đường **authentication 401** và **authorization 403** đúng chức năng.

### 18.2. Chỉ cấu hình handler mà không viết rule quyền

Handler không tự biết `orders.cancel` là scope yêu cầu. Nếu endpoint bị `permitAll()` hoặc chỉ `authenticated()`, handler có thể không bao giờ được gọi cho token thiếu quyền.

### 18.3. Tưởng `insufficient_scope` chỉ xuất hiện khi OAuth `scope` sai

Với một authentication Bearer hợp lệ, handler mặc định có thể trả `insufficient_scope` cho **AccessDeniedException** do role, permission hoặc policy khác. Đó là header protocol tổng quát, không phải lời giải thích đầy đủ nguyên nhân nghiệp vụ.

### 18.4. Tưởng 403 tự động chứa JSON

`BearerTokenAccessDeniedHandler` chủ yếu quản lý status và `WWW-Authenticate`. Body JSON theo chuẩn ứng dụng cần cấu hình riêng, không nên dựa vào việc handler mặc định sinh một schema cố định.

### 18.5. Thay handler bằng code chỉ gọi `sendError(403)`

Điều này có thể đánh mất Bearer challenge hoặc để servlet container tạo body HTML không phù hợp API contract. Nếu cần body riêng, delegate handler chuẩn và thêm JSON an toàn.

### 18.6. Đổi principal name để sửa lỗi scope

`Authentication.getName()` là tên principal (thường dựa trên `sub` với JWT). Đổi nó sang email/username **không tạo authority `SCOPE_orders.cancel`**. Thiếu quyền phải được sửa ở token scope/claim converter/policy hoặc hợp đồng AS/API, không sửa bằng cách đổi tên principal.

### 18.7. Quên prefix `SCOPE_` hoặc `ROLE_`

Một token có `scope = orders.cancel` không đồng nghĩa security rule `hasAuthority("orders.cancel")` sẽ match. Với converter mặc định, rule thường phải tìm `SCOPE_orders.cancel`. Tương tự `hasRole("ORDER_SUPPORT")` thường đối chiếu `ROLE_ORDER_SUPPORT`.

### 18.8. Trả 401 thay 403 để buộc Client refresh token

Refresh token không tự cấp quyền mới và có thể gây vòng lặp 401/refresh. Nếu caller đã xác thực nhưng thiếu quyền, trả 403 phù hợp hơn theo hợp đồng.

### 18.9. Không kiểm tra tenant/owner vì đã có scope

`SCOPE_orders.read` có thể chỉ cho phép loại thao tác đọc. Nó không cấp quyền đối với **mọi đơn hàng**. Một access denied handler đúng vẫn không bảo vệ khỏi IDOR/BOLA nếu không có data policy.

### 18.10. Đăng ký handler ở chain sai

Bearer handler trong `/api/**` chain không bảo vệ đường `/admin/**` hoặc `/internal/**` nếu không có chain khác. Kiểm tra `securityMatcher`, `@Order` và fallback policy.

### 18.11. Kiểm thử `jwt()` rồi nghĩ JWT signature đã được xác minh

`jwt()` của Spring Security Test giả lập authentication; phải dùng Bearer JWT có chữ ký thật qua `JwtDecoder` để test signature/issuer/audience/time.

### 18.12. Mở scope quá rộng để tránh 403

Nếu một endpoint trả 403, không nên đổi toàn bộ `/api/**` thành `permitAll()` hoặc `authenticated()`. Cần xác định thực tế token thiếu authority, claim converter sai hay endpoint cần scope khác. **Giải quyết lỗi quyền không được làm mất nguyên tắc least privilege**.

## 19. Checklist triển khai và kiểm thử

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| JWT / introspection | Token được xác minh trước khi tạo Authentication |
| Audience/issuer | Token thực sự dành cho Resource Server này |
| Scope mapping | Claim `scope`/`scp` được ánh xạ thành authority đúng |
| HTTP matcher | Rule dùng method + URL phù hợp |
| Default | Những request không được cấp bị deny |
| Bearer 401 | Missing/invalid token dùng entry point đúng |
| Bearer 403 | Valid authentication thiếu quyền dùng access denied handler |
| Header | `WWW-Authenticate` chứa Bearer challenge và `insufficient_scope` khi phù hợp |
| Realm | `realm` phản ánh nhãn bảo vệ, không bị dùng thay audience |
| JSON body | Nếu custom, không làm mất header/status hoặc lộ policy nội bộ |
| Method security | `@PreAuthorize` được bật và áp dụng qua proxy phù hợp |
| Data policy | Owner/tenant/assignment vẫn được kiểm tra |
| Side effect | Request bị deny không cập nhật DB hoặc phát event |
| Multiple chains | API/web/fallback chain được chọn đúng |
| Client behavior | 401 và 403 được xử lý khác, không retry/refresh vô hạn |
| Logging | Không ghi raw Bearer token, client secret, JWT nhạy cảm |

## 20. Bài tập tình huống

**Tình huống A — Không có token:** Client gọi `GET /api/orders/42` không gửi Authorization header. Có nên trả `403 insufficient_scope`?

**Không.** Đây là trường hợp cần authentication, thường trả **401 Bearer challenge** thông qua entry point, không phải thiếu quyền của một authentication đã hợp lệ.

**Tình huống B — Token chỉ có scope đọc:** Client có JWT hợp lệ mang `orders.read`, gọi `POST /api/orders/42/cancel`. Handler nên phản hồi thế nào?

Rule thiếu `SCOPE_orders.cancel` nên phải **từ chối**, thường **403 Forbidden** kèm `WWW-Authenticate: Bearer error="insufficient_scope"` nếu handler nhận diện Bearer authentication hợp lệ.

**Tình huống C — Scope đủ, sai tenant:** Caller có `orders.read` nhưng muốn xem đơn của tenant khác. Handler báo `insufficient_scope`. Có kết luận caller thiếu OAuth scope?

**Không chắc.** Access denied có thể phát sinh do **resource policy** chứ không phải scope. Cần dựa vào logs/policy và thiết kế message không tiết lộ dữ liệu tenant khác.

**Tình huống D — Test `jwt()` pass:** Test MockMvc tạo `JwtAuthenticationToken` với `SCOPE_orders.cancel` và nhận 200. Có thể kết luận ký JWT và JWKS đang đúng?

**Không.** `jwt()` giả lập authentication. Phải có test riêng gửi signed Bearer JWT qua decoder thật.

**Tình huống E — API trả 403 JSON nhưng không có `WWW-Authenticate`:** Có thể framework vẫn hoạt động, nhưng điều gì cần kiểm tra?

Kiểm tra **custom `AccessDeniedHandler`** hoặc gateway có làm mất Bearer challenge theo contract/RFC không. Nếu Client cần header, delegate `BearerTokenAccessDeniedHandler` khi custom JSON.

**Tình huống F — Token hợp lệ nhưng thiếu `SCOPE_orders.write`:** Nhóm phát triển sửa `hasAuthority("SCOPE_orders.write")` thành `authenticated()` để request trả 200. Đây có phải sửa lỗi đúng?

**Không.** Họ đã mở rộng quyền cho mọi caller được xác thực. Phải kiểm tra grant, scope mapping, policy và yêu cầu nghiệp vụ thực sự.

**Tình huống G — Có header `WWW-Authenticate` nhưng browser JS không đọc được:** Có phải handler đã không gửi header?

**Không nhất thiết.** Trong cross-origin request, CORS có thể không expose header cho JavaScript. Cần kiểm tra network response và cấu hình `Access-Control-Expose-Headers` theo chính sách.

**Tình huống H — Token opaque active nhưng sai audience:** API có nên để handler thiếu quyền quyết định có nhận token hay không?

**Không.** Audience/resource binding là phần **xác thực token theo hợp đồng** trước authorization. Nếu sai, token phải bị từ chối trước khi quyền scope được xét.

**Tình huống I — Request hủy đơn trả 403 nhưng DB đã cập nhật trạng thái:** Negative test có pass không?

**Không.** Authorization đến quá muộn hoặc có side effect trước khi bị chặn. Cần sửa luồng thực thi để không có thay đổi dữ liệu khi thiếu quyền.

---

## Kết luận

**`BearerTokenAccessDeniedHandler`** là thành phần chuyên trách phản hồi **truy cập bị từ chối** trong Spring Security OAuth2 Resource Server. Khi một request có Bearer authentication hợp lệ nhưng không đạt rule `hasAuthority`, `hasRole` hoặc một chính sách quyền khác, handler có thể tạo **HTTP 403 Forbidden** cùng **`WWW-Authenticate: Bearer ... error="insufficient_scope"`** theo RFC 6750. Nó khác **`BearerTokenAuthenticationEntryPoint`** của đường lỗi authentication, thường trả **401** cho credential thiếu hoặc không hợp lệ.

Để triển khai đúng, hãy **cấu hình quyền theo method/path**, giữ issuer/audience/token validation, sử dụng Bearer handler ở đúng SecurityFilterChain và **giữ `WWW-Authenticate` khi tùy biến JSON response**. Kiểm thử cả **401 không token**, **403 token hợp lệ thiếu quyền**, **đường được phép**, **quyền trên owner/tenant** và **không có side effect khi bị deny**. Handler xuất phản hồi thiếu quyền; **nó không thay thế quá trình xác minh token, ánh xạ scope hoặc authorization policy của ứng dụng**.
