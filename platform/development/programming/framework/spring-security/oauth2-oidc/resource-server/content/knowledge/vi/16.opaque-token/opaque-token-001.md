# Opaque token và xác minh thông qua introspection

Khi bảo vệ API bằng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, nhiều người bắt đầu với JWT access token: API nhận một chuỗi có các phần phân tách bởi dấu chấm, tải khóa công khai từ JWKS rồi xác minh chữ ký và các claims. Tuy nhiên, **OAuth 2.0 không yêu cầu access token phải là JWT**. Authorization Server hoàn toàn có thể phát hành **opaque access token**: một chuỗi mà Resource Server không nên tự diễn giải để biết người gọi, thời hạn hoặc quyền.

Với kiểu token này, một cơ chế phổ biến là **OAuth 2.0 Token Introspection (RFC 7662)**. Resource Server gửi token đến một endpoint đáng tin của Authorization Server để hỏi **token có đang active không, được cấp cho ai, Client nào và mang phạm vi quyền nào**. Chỉ sau khi có kết quả introspection đáng tin, Resource Server mới tạo `Authentication` và thực thi authorization.

Ví dụ đơn giản:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer Y6f9HkA7Pz9rKx...opaque...
~~~

Orders API **không nên** cố tách chuỗi này thành header/payload/signature, giải mã Base64URL hoặc suy đoán quyền từ hình dạng token. Nó hỏi Authorization Server qua introspection endpoint, sau đó áp dụng chính sách bảo mật của **chính Orders API**.

> **Quy tắc cốt lõi:** **Opaque token là Bearer credential**, không phải danh tính hay quyền tự chứng minh. `active: true` là kết quả kiểm tra trạng thái từ Authorization Server; nó **chưa thay thế** kiểm tra audience/resource, scope, tenant, quyền trên dữ liệu và hợp đồng token của API. Khi không xác minh được token, phải **fail closed**.

## 1. Opaque access token là gì?

Một opaque access token được coi là **không có cấu trúc có ý nghĩa để Client hoặc Resource Server tự tin cậy và giải mã**. Nó có thể trông giống chuỗi ngẫu nhiên:

~~~text
4Q0D6WnJ8z...qk93
~~~

hoặc có hình dạng khác do nhà phát hành quyết định. Nội dung đó có thể là một tham chiếu đến trạng thái phía Authorization Server, một giá trị được mã hóa/định dạng riêng, thậm chí một chuỗi có cấu trúc mà Resource Server vẫn **chọn kiểm tra thông qua introspection**. Vì thế “opaque” mô tả **hợp đồng sử dụng**: bên nhận không tự suy ra danh tính hoặc quyền từ token.

### 1.1. So sánh opaque token và signed JWT access token

| Tiêu chí | Opaque access token | Signed JWT access token |
| --- | --- | --- |
| Hình thức | Chuỗi không được Resource Server tự giải thích | JWS compact thường có ba phần `header.payload.signature` |
| Nguồn thông tin trạng thái | Phản hồi introspection hoặc cơ chế xác minh do AS định nghĩa | Claims trong JWT sau khi xác minh chữ ký |
| Cách xác thực điển hình | Gọi introspection endpoint của AS | Xác minh JWS bằng khóa tin cậy, validate claims |
| Phụ thuộc kết nối tới AS lúc xác minh | Thường **có**, nếu introspect từng request/token | Không nhất thiết, khi public key phù hợp đã có |
| Thu hồi token | AS có thể phản ánh trạng thái tại thời điểm introspection | JWT đã ký thường được chấp nhận cho tới lúc hết hạn nếu không có cơ chế thu hồi bổ sung |
| Tính mới của quyền | Có thể phản ánh dữ liệu AS cập nhật hơn, theo hợp đồng và cách AS tính quyền | Claims thường cố định từ lúc phát token |
| Độ trễ | Có thêm network hop, trừ khi có cache phù hợp | Thường chủ yếu là CPU/memory sau khi có khóa |
| Bảo mật Bearer credential | Phải giữ kín, dùng HTTPS, không log nguyên token | **Cũng vậy**, dù payload JWT có thể đọc được |

**Không phải opaque luôn “an toàn hơn JWT” hoặc JWT luôn “nhanh hơn opaque” trong mọi hệ thống.** Sự lựa chọn liên quan tới yêu cầu thu hồi, độ khả dụng, dữ liệu quyền động, số lượng request, vận hành và cách triển khai.

### 1.2. Token vẫn là Bearer token

OAuth 2.0 Bearer Token Usage (RFC 6750) quy định cách một caller trình access token, thường qua header:

~~~http
Authorization: Bearer <access-token>
~~~

**Ai nắm giữ một Bearer token hợp lệ đều có thể thử dùng nó.** Vì vậy opaque token không tự bảo vệ khỏi bị sao chép: Client và API vẫn cần HTTPS/TLS, không để token vào URL/log, bảo vệ nơi lưu token và áp dụng thời hạn/quyền tối thiểu. Nếu cần ràng buộc token với bên sở hữu bằng chứng mật mã, đó là một thiết kế token binding khác như DPoP hoặc mutual TLS, không mặc nhiên có từ opaque token.

## 2. Các bên trong luồng introspection

Trong ví dụ Orders API:

- **Shop Web hoặc một service Client** xin access token theo một grant hợp lệ.
- **Identity Server** là Authorization Server, lưu/biết trạng thái token và cung cấp introspection endpoint.
- **Orders API** là Resource Server nhận Bearer token, đồng thời có credential riêng để được gọi introspection.
- **Order database/policy** quyết định quyền thực tế trên từng đơn hàng.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant R as Orders API
    participant DB as Order policy / database

    U->>C: Yêu cầu xem đơn
    C->>AS: Xin access token theo OAuth2 grant
    AS-->>C: Opaque access token
    C->>R: GET /api/orders/42 + Bearer token
    R->>AS: POST /introspect (token + credential API)
    AS-->>R: active, scope, sub, aud, client_id, exp...
    alt Token active và đúng hợp đồng API
        R->>R: Tạo Authentication/authorities
        R->>DB: Kiểm tra scope, owner, tenant, status
        DB-->>R: Cho phép hoặc từ chối
        R-->>C: Kết quả phù hợp
    else Token không active hoặc không được chấp nhận
        R-->>C: Từ chối request được bảo vệ
    end
~~~

Phản hồi từ introspection cần đến qua **kết nối tin cậy đã xác thực** đến đúng Authorization Server. Nó không phải JSON do caller có thể tự gửi thay cho introspection. Caller chỉ được gửi **Bearer token**, không được tự khai `active`, `scope` hoặc `sub` qua header khác để Resource Server tin ngay.

## 3. OAuth 2.0 Token Introspection theo RFC 7662

**Introspection endpoint** là giao diện cho Resource Server hoặc bên được ủy quyền hỏi Authorization Server về trạng thái/metadata của token. Endpoint do Authorization Server công bố hoặc cung cấp qua tài liệu/metadata tích hợp; **không có một đường dẫn cố định áp dụng cho mọi nhà phát hành**.

Ví dụ đường dẫn:

~~~text
https://identity.example.test/realms/shop/protocol/openid-connect/token/introspect
~~~

Đây là URL minh họa theo một kiểu sản phẩm; ứng dụng phải dùng **endpoint thực tế** của nhà phát hành, không tự ghép path rồi giả định luôn đúng.

### 3.1. Request introspection

Theo RFC 7662, Resource Server gửi **HTTP POST** với body dạng `application/x-www-form-urlencoded`, có tham số bắt buộc `token` và có thể thêm `token_type_hint`:

~~~http
POST /introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <credential-cua-resource-server>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=4Q0D6WnJ8z...qk93&token_type_hint=access_token
~~~

Lưu ý:

- `token` ở body là **access token Client đã trình cho Orders API**.
- Credential trong header `Authorization: Basic ...` là **credential của Resource Server khi gọi AS** (nếu nhà phát hành chọn kiểu xác thực đó), không phải credential của người dùng.
- `token_type_hint=access_token` là **gợi ý**, không phải bằng chứng token hợp lệ; Authorization Server xử lý theo giao thức của nó.
- Spring Security thường cung cấp cơ chế cấu hình Client ID/secret để gọi introspection; nếu nhà phát hành yêu cầu mutual TLS, private_key_jwt hoặc cơ chế khác, cần cấu hình client HTTP/authentication phù hợp.
- Token và introspection credential đều nhạy cảm; các giá trị dạng dấu chấm ở đây **không phải credential thật**.

Để tự hiểu protocol trong môi trường kiểm thử, có thể viết ví dụ cURL:

~~~bash
# Chỉ minh họa request. Dùng credential/test token của môi trường thử.
curl --request POST \
  --url "https://identity.example.test/introspect" \
  --user "orders-api-introspection:<test-secret>" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=<test-access-token>" \
  --data-urlencode "token_type_hint=access_token"
~~~

**Không chạy lệnh với token/secret production theo cách khiến chúng lưu trong lịch sử shell, process list hoặc log.** Với môi trường thật, secret nên được cấp bằng secret manager và cách gọi bảo mật phù hợp. cURL là ví dụ về giao thức, không phải hướng dẫn vận hành credential production.

### 3.2. Token active

Một phản hồi thành công về mặt HTTP có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read orders.cancel",
  "client_id": "shop-web",
  "sub": "user-842",
  "username": "linh.nguyen",
  "token_type": "Bearer",
  "iss": "https://identity.example.test/realms/shop",
  "aud": ["orders-api"],
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900
}
~~~

Các thuộc tính ngoài `active` là ví dụ. RFC 7662 định nghĩa những tên metadata thường gặp như `scope`, `client_id`, `username`, `token_type`, `exp`, `iat`, `nbf`, `sub`, `aud`, `iss`, `jti`. **Authorization Server có thể trả tập thuộc tính khác nhau**, hoặc thêm claims riêng; API cần một hợp đồng rõ về thuộc tính bắt buộc cho quyết định bảo mật.

**`active: true` không có nghĩa token có mọi quyền**. Resource Server còn phải xác nhận:

1. Phản hồi đến từ introspection endpoint tin cậy mà API đã xác thực với nó.
2. Token được cấp cho API này theo audience/resource binding đã thỏa thuận.
3. Scope/permissions tương ứng endpoint thực sự có mặt.
4. Chủ thể/Client/tenant phù hợp chính sách.
5. Quyền trên bản ghi cụ thể được kiểm tra ở tầng nghiệp vụ.

### 3.3. Token inactive

Một token không tồn tại, hết hạn, bị thu hồi hoặc không còn active theo chính sách AS có thể nhận:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
~~~

Đây là **kết quả introspection thành công nhưng token không được chấp nhận**, không phải lỗi xác thực của Resource Server đối với introspection endpoint. RFC 7662 yêu cầu phản hồi của token không active **không tiết lộ thêm metadata** ngoài `active` trong trường hợp thông thường.

Resource Server không được đọc `scope` từ token do caller đưa vào rồi bỏ qua `active: false`. Với endpoint bảo vệ bằng Bearer authentication, token inactive thường dẫn tới **401 Unauthorized** từ Orders API.

### 3.4. Một số tình huống HTTP khác nhau

| Phản hồi khi Orders API gọi AS | Nghĩa điển hình | Orders API nên xử lý |
| --- | --- | --- |
| `200`, `active: true` | Token đang active theo AS | Còn phải kiểm tra hợp đồng token và policy |
| `200`, `active: false` | Token không được chấp nhận | Không tạo authentication hợp lệ |
| `401 Unauthorized` từ introspection endpoint | Credential Resource Server gửi tới AS sai/không được chấp nhận | Đây là lỗi tích hợp/credential introspection, **không** được coi token tự động active |
| `403 Forbidden` từ introspection endpoint | Resource Server không được introspect theo chính sách AS | Kiểm tra quyền client/endpoint, từ chối request được bảo vệ |
| `400 Bad Request` từ AS | Request introspection sai cú pháp hoặc tham số | Sửa tích hợp, không cho qua token |
| `429`/`5xx`/timeout | Rate limit, AS hoặc mạng gặp sự cố | Fail closed; áp dụng timeout/retry/backoff theo thiết kế |
| JSON sai định dạng hoặc thiếu `active` | Không có phản hồi hợp lệ theo hợp đồng | Không xem token là đã xác thực |

**Đừng gán cứng một mã HTTP từ Orders API cho mọi lỗi ở AS.** Tùy exception handling/framework, một lỗi mạng có thể biểu hiện khác lỗi token inactive. Điều quan trọng về bảo mật là **không thực thi thao tác được bảo vệ khi không có kết quả xác thực đáng tin**.

## 4. Introspection là xác minh trạng thái token, không phải cấp token

OAuth2 có nhiều endpoint khác nhau:

| Endpoint | Ai gọi? | Mục đích |
| --- | --- | --- |
| **Authorization endpoint** | OAuth2 Client, browser | Bắt đầu authorization code/consent |
| **Token endpoint** | OAuth2 Client | Đổi code/refresh token/client credentials thành token |
| **Introspection endpoint** | Resource Server hoặc bên được phép | Hỏi trạng thái và metadata token đã cấp |
| **Revocation endpoint** | Client hoặc chủ thể được phép theo policy | Yêu cầu thu hồi token |
| **JWKS endpoint** | Bên cần xác minh chữ ký JWT | Lấy public keys |

**Introspection không phải thao tác thu hồi token.** Việc gọi introspection không làm token mất hiệu lực. **Revocation** là cơ chế/yêu cầu khác, và việc AS phản ánh revocation vào `active` tùy cách triển khai.

**JWKS không tự dùng để xác minh opaque token.** Public key giúp kiểm tra chữ ký JWT; opaque token không có hợp đồng JWS để Resource Server tự xác minh. Một Resource Server có thể dùng introspection cho cả token có hình dạng JWT nếu đó là thiết kế của hệ thống, nhưng không nên trộn hai cơ chế một cách tình cờ.

## 5. Cấu hình Spring Boot Resource Server nhận opaque token

Ví dụ dùng **Spring Boot 3 / Spring Security 6** với Orders API dạng REST, nhận access token qua `Authorization: Bearer`.

### 5.1. Dependency

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Hoặc với Maven, thêm `spring-boot-starter-oauth2-resource-server`. Không bắt buộc dùng `oauth2Login()` chỉ để API nhận opaque access token; **Resource Server** và **OAuth2/OIDC Client** là hai vai trò khác nhau.

### 5.2. application.yml với introspection

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

Ví dụ môi trường dev:

~~~text
OAUTH_INTROSPECTION_URI=https://id.dev.example.test/introspect
OAUTH_INTROSPECTION_CLIENT_ID=orders-api-introspection-dev
OAUTH_INTROSPECTION_CLIENT_SECRET=<secret-do-he-thong-trien-khai-cap>
~~~

**Không commit secret thật** vào `application.yml`, `application-prod.yml`, Dockerfile, README hoặc test fixture. Secrets nên được cấp riêng theo dev/staging/production thông qua secret manager, CI/CD hoặc cơ chế secret storage phù hợp. `OAUTH_INTROSPECTION_CLIENT_SECRET` là **credential của API khi gọi Authorization Server**; nó khác access token mà Shop Web gửi tới API.

### 5.3. SecurityFilterChain cho opaque token

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersOpaqueSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Trong cấu hình:

- `oauth2ResourceServer().opaqueToken()` cho Spring Security biết **Bearer token phải được introspect**, không dùng `JwtDecoder` để xác minh JWS.
- Một introspector được tạo/cấu hình từ `introspection-uri`, `client-id` và `client-secret`, trừ khi ứng dụng cung cấp bean/cấu hình thay thế.
- Sau introspection thành công, Spring Security tạo authentication/authorities từ dữ liệu tin cậy và so rule `SCOPE_orders.read` hoặc `SCOPE_orders.write`.
- `anyRequest().denyAll()` trong chain chặn những đường API chưa được cho phép.

Ví dụ giả định `/api/**` **chỉ xác thực bằng Bearer token** và không dùng session cookie, nên tắt CSRF trong chain API và đặt session stateless. Nếu ứng dụng phục vụ web UI bằng cookie/session, phải dùng cấu hình CSRF/filter chain thích hợp cho phần đó. Nếu `securityMatcher("/api/**")` không bao phủ đường ngoài API, cần có **chain khác hoặc fallback deny-all** để không bỏ sót endpoint.

### 5.4. Chạy thử một request

Client gọi:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <opaque-token>
~~~

Authorization Server trả introspection:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-842",
  "client_id": "shop-web",
  "aud": ["orders-api"]
}
~~~

Spring Security có thể ánh xạ giá trị `scope` thành authority `SCOPE_orders.read` theo xử lý introspection mặc định của nó. Khi API rule yêu cầu authority ấy, request **có thể đi tiếp** tới controller/service. Tuy nhiên, nó vẫn có thể bị từ chối nếu đơn 42 không thuộc người dùng hoặc tenant được phép.

## 6. Bên trong Spring Security: từ opaque token đến Authentication

Một chuỗi xử lý khái niệm:

~~~text
HTTP Authorization: Bearer opaque-token
  |
  v
BearerTokenAuthenticationFilter
  |
  v
OpaqueTokenAuthenticationProvider
  |
  v
OpaqueTokenIntrospector
  |
  +-- POST đến introspection endpoint tin cậy
  +-- xác thực Resource Server với AS
  +-- parse active + token metadata
  |
  v
OAuth2AuthenticatedPrincipal + GrantedAuthorities
  |
  v
BearerTokenAuthentication
  |
  v
authorizeHttpRequests / method security
  |
  v
resource policy: owner, tenant, trạng thái...
~~~

Các class quan trọng:

| Thành phần | Trách nhiệm |
| --- | --- |
| `BearerTokenAuthenticationFilter` | Trích Bearer token từ request theo cấu hình |
| `OpaqueTokenAuthenticationProvider` | Sử dụng introspector để xác thực token và tạo authentication |
| `OpaqueTokenIntrospector` | Interface cho cơ chế introspect chuỗi token, trả `OAuth2AuthenticatedPrincipal` |
| `OAuth2AuthenticatedPrincipal` | Principal chứa thuộc tính và authorities từ kết quả tin cậy |
| `BearerTokenAuthentication` | Authentication của Bearer token sau introspection thành công |
| `SecurityFilterChain` | Áp dụng rule theo URL/HTTP method/authority |
| Service/policy nghiệp vụ | Kiểm tra quyền trên dữ liệu thực tế |

Với JWT Resource Server, principal trong `JwtAuthenticationToken` thường là đối tượng `Jwt`; với opaque token, **không nên ép `@AuthenticationPrincipal Jwt`** hoặc giả định token có JWT claims set. Dùng `OAuth2AuthenticatedPrincipal` và các attributes mà introspector cung cấp.

### 6.1. Lấy subject và attributes trong controller

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class CallerController {

    @GetMapping("/whoami")
    CallerInfo whoAmI(
            Authentication authentication,
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        String subject = principal.getAttribute("sub");
        String clientId = principal.getAttribute("client_id");

        return new CallerInfo(
                authentication.getName(),
                subject,
                clientId);
    }

    record CallerInfo(String principalName, String subject, String clientId) {}
}
~~~

Đây là endpoint minh họa. **Không phải mọi introspection response đều có `sub` hoặc `client_id`**, nên thiết kế production phải xác định chúng có bắt buộc không, xử lý null rõ ràng, tránh lộ dữ liệu nhạy cảm trong endpoint chẩn đoán.

**`Authentication.getName()` không mặc nhiên là username hay user ID nội bộ**: ý nghĩa của nó phụ thuộc principal được introspector tạo ra và thông tin AS trả. Nếu API cần một danh tính người dùng ổn định xuyên issuer/tenant, nên duy trì hợp đồng rõ về `(iss, sub)` và ánh xạ user nội bộ thay vì chỉ tin chuỗi display username.

### 6.2. Scopes được đưa vào authorities như thế nào?

Ví dụ AS trả:

~~~json
{
  "active": true,
  "scope": "orders.read orders.cancel",
  "sub": "user-842"
}
~~~

Resource Server có thể nhận authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

Các prefix này là quy ước của Spring Security:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

khác với:

~~~java
.hasAuthority("orders.read")
~~~

Nếu AS trả scope dưới dạng/claim khác với profile Spring hỗ trợ mặc định, cần **introspector hoặc converter tùy chỉnh**. Không giả định một object `roles` hay `permissions` bất kỳ sẽ tự biến thành `ROLE_ADMIN` hoặc `PERM_order:read:tenant`.

## 7. Phân biệt credential introspection với Client credentials và Bearer token

Trong hệ thống có ba loại thông tin khác nhau:

| Giá trị | Bên nắm giữ | Mục đích | Có bí mật? |
| --- | --- | --- | --- |
| **Bearer access token** | OAuth2 Client và Resource Server tạm nhận | Client trình credential để gọi API | **Có tính chất credential nhạy cảm** |
| **Introspection client ID** | Resource Server được AS cấp | Định danh bên hỏi introspection | Thường không |
| **Introspection client secret** | Resource Server và AS | Resource Server xác thực với introspection endpoint | **Có** |
| **Client ID/secret của Shop Web** | Shop Web và AS | Shop Web xin token theo grant phù hợp | Secret cần bảo vệ nếu là confidential Client |
| **Signing private key của AS** | AS/hệ thống ký | Ký JWT nếu AS phát token dạng JWT | **Rất nhạy cảm** |
| **Public JWK/JWKS** | Bên xác minh JWT | Xác minh chữ ký JWT | Không phải private secret |

Không dùng `client-secret` của Shop Web làm credential cho Orders API nếu AS không đăng ký/bật quyền riêng cho Resource Server. Tách Client registrations và secrets theo trách nhiệm, cấp quyền tối thiểu cho introspection và quay vòng bí mật độc lập.

**Một câu hỏi về quyền riêng tư:** Không phải Resource Server nào cũng có quyền xem metadata của mọi token. Authorization Server nên giới hạn Client nào được introspect token nào, chỉ trả những dữ liệu cần thiết theo hợp đồng. Nếu một client introspection không có quyền, phản hồi có thể là inactive hoặc lỗi tùy chính sách và tiêu chuẩn nhà phát hành; Resource Server vẫn không được dùng token đó để cấp quyền.

## 8. `active: true` vẫn cần kiểm tra audience và token contract

Một sai lầm nguy hiểm:

~~~text
Nếu active == true:
    authentication = authenticated
    cho phép gọi mọi API
~~~

Một token có thể **active trong Authorization Server** nhưng được cấp cho **Billing API**, không phải Orders API.

Ví dụ:

~~~json
{
  "active": true,
  "scope": "billing.read",
  "aud": ["billing-api"],
  "client_id": "billing-web",
  "sub": "user-842"
}
~~~

Orders API phải có chính sách xác nhận token dành cho `orders-api`. Nếu introspection response không chứa `aud`, cần thiết lập **một ràng buộc tương đương do AS và API thỏa thuận**, ví dụ introspection endpoint giới hạn token theo resource hoặc phản hồi một claim resource khác. **Không được mặc định bỏ qua audience chỉ vì kết quả `active = true`**.

### 8.1. Kiểm tra các thuộc tính theo hợp đồng

| Thuộc tính | Câu hỏi | Lưu ý |
| --- | --- | --- |
| `active` | Token còn được AS công nhận? | Bắt buộc cho kết quả introspection |
| `aud` | Token dành cho API nào? | Có thể là chuỗi hoặc danh sách; đôi khi không có nếu hợp đồng khác |
| `iss` | Nguồn phát hành token là ai? | Không phải mọi AS trả claim này; nguồn tin introspection vẫn phải được ràng buộc |
| `scope` | Token được cấp hành động nào? | Không tự chứng minh quyền dữ liệu |
| `sub` | Chủ thể token tham chiếu là ai? | Có thể là người dùng hoặc dịch vụ tùy grant/profile |
| `client_id` | OAuth2 Client được cấp token | **Không đồng nghĩa** credential introspection Client |
| `token_type` | Loại token, ví dụ Bearer | Không tự xác định token dành cho API |
| `exp`, `nbf`, `iat` | Thời gian hiệu lực và phát hành | AS đã đánh giá `active`; policy có thể yêu cầu giới hạn thêm |
| `tenant_id`/custom claims | Bối cảnh quyền của tổ chức | Phải có định nghĩa/kiểu dữ liệu rõ ràng |

**Một phản hồi active có thể không chứa tất cả các trường này.** Điều kiện nào là bắt buộc phải xuất phát từ yêu cầu bảo mật của API và hợp đồng với AS, không phải từ giả định rằng mọi introspection endpoint đều giống nhau.

### 8.2. Viết wrapper kiểm tra audience

Với Spring Security 6, có thể tùy biến `OpaqueTokenIntrospector` để kiểm tra metadata trước khi Authentication được chấp nhận. Ví dụ minh họa sau dùng `NimbusOpaqueTokenIntrospector` làm delegate, với constructor có mặt trong nhiều dòng Spring Security 6; tùy phiên bản dự án có thể dùng `SpringOpaqueTokenIntrospector`/builder tương ứng và vẫn giữ ý tưởng **delegate rồi validate**.

~~~java
import java.util.Collection;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
class OpaqueAudienceValidationConfig {

    @Bean
    OpaqueTokenIntrospector introspector(
            @Value("${spring.security.oauth2.resourceserver.opaque-token.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaque-token.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaque-token.client-secret}")
            String clientSecret,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        OpaqueTokenIntrospector delegate =
                new NimbusOpaqueTokenIntrospector(
                        uri, clientId, clientSecret);

        return token -> {
            // Delegate yêu cầu introspection và từ chối token inactive.
            OAuth2AuthenticatedPrincipal principal =
                    delegate.introspect(token);

            // Metadata đã đến từ endpoint introspection tin cậy.
            Object rawAudience = principal.getAttribute("aud");
            if (!containsAudience(rawAudience, expectedAudience)) {
                throw new BadOpaqueTokenException(
                        "Token is not intended for this resource server");
            }
            return principal;
        };
    }

    private static boolean containsAudience(
            Object rawAudience, String expected) {

        if (rawAudience instanceof String value) {
            return expected.equals(value);
        }
        if (rawAudience instanceof Collection<?> values) {
            return values.contains(expected);
        }
        return false;
    }
}
~~~

Khi sử dụng code trên, bổ sung property:

~~~yaml
app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

Trong ví dụ, token **không có `aud`** sẽ bị từ chối. Đây là lựa chọn **đúng với hợp đồng của Orders API giả định introspection trả audience**. Nếu Authorization Server thật không trả `aud` nhưng bảo đảm resource binding qua phương thức khác, phải thiết kế/kiểm tra điều kiện thay thế theo tài liệu nhà phát hành, không tùy tiện chấp nhận mọi token active.

Một bean `OpaqueTokenIntrospector` tùy chỉnh sẽ thay thế cách auto-configuration chọn introspector ở những cấu hình phù hợp; do đó ứng dụng phải chắc chắn bean này vẫn thực thi xác thực request tới introspection endpoint, xử lý `active`, ràng buộc audience và các điều kiện cần thiết. Đừng trả một principal với authority cao chỉ vì introspection endpoint tạm thời không truy cập được.

**Tại sao không chỉ kiểm tra scope?** Một token cùng `orders.read` nhưng được cấp cho resource khác vẫn có thể có scope trùng tên. Audience/resource binding giúp ngăn **token substitution** giữa các API.

### 8.3. Bổ sung kiểm tra issuer và token profile

Nếu AS cung cấp `iss`, API có thể so với issuer dự kiến theo hợp đồng. Nếu `iss` không có, tính tin cậy vào issuer có thể đến từ **introspection endpoint và credential của Resource Server**, cộng quy tắc AS giới hạn tập token được introspect. Không suy diễn rằng chuỗi `iss` tự do trong một body không xác thực có giá trị bảo mật.

Tương tự, với hệ thống phát cả access token và những loại credential khác, API cần đảm bảo **introspection chỉ tạo authentication từ token được phép dùng làm OAuth2 access token cho API**. Không cho phép OIDC ID token thay access token chỉ vì token đó cũng có thể mang một số claim người dùng.

## 9. Tùy chỉnh authorities từ introspection metadata

Spring Security có thể ánh xạ `scope` thành `SCOPE_...` theo implementation introspection mặc định. Nếu Identity Server trả thêm role hoặc permission, Resource Server cần **một hợp đồng ánh xạ tường minh**, giống nguyên tắc với JWT nhưng **nguồn dữ liệu là principal được introspect**, không phải `Jwt`.

Ví dụ AS trả:

~~~json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "support-12",
  "roles": ["order_support", "billing_admin"],
  "tenant_id": "tenant-A"
}
~~~

Theo hợp đồng của Orders API, chỉ role `order_support` được ánh xạ thành `ROLE_ORDER_SUPPORT`; role `billing_admin` không thuộc miền quyền Orders và bị bỏ qua.

Một wrapper converter minh họa:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

final class OrdersRoleIntrospector implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    OrdersRoleIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(principal.getAuthorities());

        Object rawRoles = principal.getAttribute("roles");
        if (rawRoles instanceof Collection<?> roles
                && roles.contains("order_support")) {
            authorities.add(
                    new SimpleGrantedAuthority("ROLE_ORDER_SUPPORT"));
        }

        // Không tự cấp authority cho role không thuộc allowlist.
        return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                authorities);
    }
}
~~~

Wrapper này **chỉ minh họa mapping một role**. Trong ứng dụng thật, có thể gộp kiểm tra audience, issuer, token profile và role mapping trong **một chuỗi introspector** được cấu hình rõ. Không đăng ký nhiều bean `OpaqueTokenIntrospector` cạnh tranh mà không xác định bean nào được dùng. Phần kiểm tra quyền của principal phải dựa trên introspection result đã được xác thực, không phải JSON do request client gửi kèm.

**Role không thay thế resource policy:** `ROLE_ORDER_SUPPORT` chỉ biểu diễn vai trò. Service vẫn phải kiểm tra nhân viên hỗ trợ có được xem đơn 42 của tenant A, thuộc nhóm mình hay không.

## 10. Kiểm soát danh tính người dùng và service principal

Opaque token có thể được phát theo:

- **Authorization Code**: thường đại diện quyền truy cập gắn với người dùng, Client và sự chấp thuận/chính sách.
- **Client Credentials**: thường đại diện cho **Client/dịch vụ**, không nhất thiết có người dùng cuối.
- **Các grant hoặc cơ chế được hỗ trợ khác**: metadata và cách diễn giải subject tùy thiết kế AS.

Ví dụ introspection của token Client Credentials:

~~~json
{
  "active": true,
  "client_id": "nightly-sync",
  "sub": "nightly-sync",
  "scope": "orders.sync",
  "aud": ["orders-api"]
}
~~~

Không nên dùng `sub = nightly-sync` như thể đó là ID khách hàng sở hữu đơn. API có thể đặt chính sách:

~~~text
User endpoint:
  requires user context + orders.read + resource ownership

Service sync endpoint:
  requires allowed client identity + orders.sync
  + additional service-level policy
~~~

Nếu API nhận token của nhiều issuer hoặc tenant, một `sub` giống nhau không nhất thiết đại diện cùng chủ thể. Với danh tính người dùng, cặp **`(iss, sub)`** thường hữu ích làm khóa liên kết tới user nội bộ, nếu hợp đồng introspection đảm bảo hai thuộc tính này. Nếu chỉ trả `username`, cần chiến lược định danh riêng; **username/email không tự là khóa ổn định hoặc duy nhất toàn hệ thống**.

## 11. Phân quyền HTTP và quyền trên dữ liệu

Một endpoint ví dụ:

~~~text
GET /api/orders/42
~~~

chỉ nên được phép khi:

1. Caller gửi Bearer opaque token.
2. Introspection thành công với AS đáng tin và token `active = true`.
3. Token dành cho Orders API theo audience/resource contract.
4. Token mang authority `SCOPE_orders.read`.
5. Order 42 nằm trong phạm vi tenant/owner/permission của caller.

Điều kiện ở bước 5 không được suy ra chỉ từ `scope`. Một người có `orders.read` không tự được xem mọi đơn của người khác.

### 11.1. Dùng method security cho resource policy

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrdersQueryService {

    private final OrdersRepository orders;

    OrdersQueryService(OrdersRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') and " +
        "@orderAccess.canRead(authentication, #orderId)")
    public OrderDto readOrder(String orderId) {
        return orders.findVisibleDtoById(orderId)
                .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

`OrdersRepository`, `OrderDto`, `OrderNotFoundException` và bean `orderAccess` là thành phần nghiệp vụ minh họa, không phải class có sẵn của Spring. Muốn `@PreAuthorize` hoạt động, ứng dụng phải bật `@EnableMethodSecurity` và thực thi method qua Spring security proxy phù hợp.

Bean `orderAccess` cần lấy identity/tenant từ `Authentication` đã introspect và đối chiếu bản ghi trong database/policy service. Không cho Client tự gửi `X-Tenant-Id` hoặc `ownerId` rồi dùng trực tiếp làm bằng chứng quyền.

### 11.2. Introspection không làm permission trở thành vĩnh viễn

Phản hồi có `roles`/`scope` là dữ liệu **tại thời điểm AS tạo phản hồi**. Nếu hệ thống cache kết quả, quyền có thể chậm cập nhật hơn. Cũng có khả năng AS định nghĩa scope cố định tại lúc token được cấp, dù introspection đang online. Vì vậy, khi cần quyền động và thu hồi nhanh, phải hiểu **AS thực sự tính `active` và các metadata như thế nào**, thay vì giả định introspection tự động áp dụng mọi thay đổi quyền tức thời.

## 12. Tác động đến độ trễ, khả dụng và scale

Một request tới Orders API có thể làm phát sinh **một request HTTP tới AS**. Ở lưu lượng lớn, điều này ảnh hưởng:

- **Latency:** tổng thời gian phản hồi API có thêm độ trễ mạng/introspection.
- **Throughput:** AS phải phục vụ số lượng lớn yêu cầu introspection.
- **Availability:** AS/introspection endpoint down có thể khiến API không xác thực được token.
- **Connection resources:** connection pools, DNS, TLS, timeout và thread của API chịu tải.
- **Rate limiting:** AS có thể giới hạn số lần introspection hoặc áp chính sách quota.

### 12.1. Khi AS tạm ngừng

Với signed JWT, một Resource Server đã có public key phù hợp **có thể** xác minh token cục bộ khi AS ngừng, miễn là token còn hạn và đáp ứng các điều kiện khác.

Với opaque token:

~~~text
Bearer opaque token
        |
        v
Need trusted introspection response?
        |
    Yes, but AS unavailable
        |
        v
Cannot establish valid Authentication
        |
        v
Do not perform protected operation
~~~

Nếu Resource Server dùng **introspection online cho từng token** và endpoint không phản hồi, API không thể tự biết token có active hay đã bị thu hồi. Đúng là phải **từ chối hoặc báo lỗi dependency** theo cấu hình mà **không thực hiện hành động được bảo vệ**.

Không bao giờ viết:

~~~java
// SAI VỀ BẢO MẬT: Không được dùng như fallback.
try {
    return introspect(token);
} catch (Exception unavailable) {
    return adminPrincipalForEveryone();
}
~~~

Hoặc:

~~~text
Nếu AS down -> coi mọi token là active.
Nếu introspection timeout -> đọc một vài ký tự token làm userId.
Nếu secret introspection sai -> tắt authentication cho /api/**.
~~~

Những cách này biến outage khả dụng thành **fail-open authentication**.

### 12.2. Timeout, retry và bảo vệ AS

Các điểm vận hành cần cấu hình theo thư viện và môi trường:

1. **Connection timeout** và **response timeout** hữu hạn.
2. **Retry có giới hạn**, phù hợp với status lỗi tạm thời và ngân sách độ trễ của API.
3. Backoff/jitter khi AS gặp 429/5xx để tránh retry storm.
4. Circuit breaker hoặc bulkhead khi cần giới hạn tác động tới thread/connection pool.
5. Metrics: introspection latency, active/inactive, lỗi xác thực client, timeout, 5xx, rate limit.
6. Phân biệt **token inactive** với **introspection dependency down** trong log/alert nội bộ.

Không tự biến mọi lỗi kết nối thành `active: false` rồi che khuất sự cố vận hành; cũng không dùng việc phân biệt ấy để **cho qua request**. Mã HTTP trả cho Client có thể được thiết kế riêng theo policy/exception handler, nhưng security invariant là không có authenticated principal giả khi AS không xác minh được token.

### 12.3. Cache kết quả introspection: một đánh đổi có chủ đích

Caching có thể giảm latency và lượng request tới AS:

~~~text
token T -> introspection active + metadata
        -> cache trong khoảng ngắn, theo policy
        -> các request sau dùng kết quả còn hiệu lực
~~~

Nhưng cache có thể kéo dài thời gian mà API tiếp tục tin token **sau khi token đã bị thu hồi, permission thay đổi hoặc user bị khóa**.

Nếu áp dụng cache, cần định nghĩa:

- **TTL tối đa** dựa trên mức rủi ro và `exp` của token nếu AS cung cấp; không cache vượt thời gian token còn hợp lệ.
- Quy tắc lưu **positive** và **negative** result (inactive) riêng, nếu có.
- Khả năng **invalidation** khi phát hiện token/credential bị thu hồi.
- Cách bảo vệ cache key (token là secret; cân nhắc hash/HMAC và giới hạn truy cập).
- Có cho phép dùng cached active result khi AS down hay không, **chỉ trong thời hạn policy đã cho phép**.
- Khi cache hết hạn mà AS vẫn down, request phải thất bại an toàn.

**Không dùng cache vô hạn** và không tự kéo dài TTL khi AS down. Nếu yêu cầu thu hồi gần như tức thời, caching phải được hạn chế đáng kể hoặc kết hợp cơ chế invalidation chủ động.

### 12.4. Khả dụng của AS và API khác nhau

Introspection cho phép Resource Server có thông tin trạng thái từ AS, nhưng tạo thêm phụ thuộc. Một hệ thống yêu cầu availability rất cao có thể phải đánh giá:

- AS có đủ replicas/regions và SLA cho endpoint introspection?
- API có cần graceful degradation **chỉ với những chức năng public/không cần auth** khi AS down?
- Có cơ chế cache đã được phê duyệt không?
- Có nên dùng JWT access token sống ngắn với xác minh cục bộ cho một số API không?
- Khi AS hồi phục, API có thể phục hồi tự động mà không restart hàng loạt không?

Không chọn cơ chế chỉ vì “opaque bảo mật hơn” mà quên độ trễ và độ khả dụng; cũng không dùng JWT chỉ để tránh mọi vấn đề thu hồi. Cần quyết định theo rủi ro nghiệp vụ và năng lực vận hành.

## 13. Thiết kế kiểm thử introspection với cả trường hợp được phép và phải bị từ chối

Bộ test nên được tách thành **HTTP authorization**, **introspection client/protocol** và **policy dữ liệu**.

### 13.1. Ma trận token và phản hồi introspection

| Tình huống | AS introspection | Kết quả ở Resource Server |
| --- | --- | --- |
| Token hợp lệ dành cho Orders API | `active: true`, `aud = orders-api`, `scope = orders.read` | Có thể xác thực; endpoint đọc qua HTTP rule |
| Token không tồn tại | `active: false` | Từ chối authentication |
| Token đã bị thu hồi | `active: false` | Từ chối authentication |
| Token hết hạn | `active: false` (theo AS) | Từ chối authentication |
| Token active nhưng audience Billing API | `active: true`, `aud = billing-api` | Từ chối theo hợp đồng audience |
| Token active đúng audience nhưng thiếu `orders.read` | `active: true`, `scope = profile` | Authentication có thể thành công; HTTP authorization 403 |
| Token active đúng audience/scope nhưng khác tenant | `active: true` | Data policy từ chối |
| Resource Server dùng sai introspection secret | AS trả 401 | Lỗi xác thực Resource Server với AS, không cấp quyền |
| Endpoint introspection trả 503 hoặc timeout | Không có kết quả đáng tin | Fail closed, không chạy nghiệp vụ được bảo vệ |
| Introspection trả JSON malformed | Phản hồi không hợp lệ | Không tạo Authentication thành công |
| Metadata token thiếu audience bắt buộc | `active: true` nhưng thiếu `aud` | Từ chối theo validator nếu hợp đồng yêu cầu audience |

Khi test, nên kiểm tra **controller/service không có side effects** ở mọi trường hợp bị từ chối; không chỉ nhìn một status HTTP.

### 13.2. Mock introspector cho test HTTP authorization

Nếu chỉ muốn kiểm tra `hasAuthority` và SecurityFilterChain, có thể dựng `OpaqueTokenIntrospector` giả lập, không cần khởi chạy AS thật. Ví dụ với JUnit Jupiter/MockMvc và Spring Security test:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@TestConfiguration
class FakeOpaqueIntrospection {

    @Bean
    OpaqueTokenIntrospector introspector() {
        return token -> {
            if ("active-read".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                        "user-842",
                        Map.of(
                                "sub", "user-842",
                                "aud", List.of("orders-api"),
                                "scope", "orders.read"),
                        List.of(
                            new SimpleGrantedAuthority(
                                    "SCOPE_orders.read")));
            }
            if ("active-write".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                        "user-842",
                        Map.of(
                                "sub", "user-842",
                                "aud", List.of("orders-api"),
                                "scope", "orders.write"),
                        List.of(
                            new SimpleGrantedAuthority(
                                    "SCOPE_orders.write")));
            }
            throw new BadOpaqueTokenException("inactive or unknown token");
        };
    }
}
~~~

Đây là **fixture cho test**, không phải introspector production. Nó chủ động tạo principal từ những chuỗi test như `active-read` và không gọi Authorization Server. Chỉ dùng để cô lập rule HTTP/authority.

Ví dụ các request khi test:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Khi MockMvc được cấu hình với SecurityFilterChain và FakeOpaqueIntrospection:
mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer active-read"))
    .andExpect(status().isOk());

mockMvc.perform(post("/api/orders")
        .header("Authorization", "Bearer active-read"))
    .andExpect(status().isForbidden());

mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer inactive-token"))
    .andExpect(status().isUnauthorized());

mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isUnauthorized());
~~~

Đoạn trên là **phần thân minh họa trong một test có `mockMvc` và controller giả**, không phải class test hoàn chỉnh độc lập. Với policy nghiệp vụ thật, `GET /api/orders/42` có thể bị từ chối sau HTTP authorization nếu không đúng owner/tenant.

### 13.3. Integration test với introspection endpoint mock

Để chứng minh giao thức và credentials thực sự hoạt động, cần test ở mức cao hơn:

1. Chạy **MockWebServer** hoặc **WireMock** làm introspection endpoint của môi trường test.
2. Cấu hình Spring Security Resource Server trỏ `introspection-uri` tới HTTP server test.
3. Gửi request thật tới API với `Authorization: Bearer <test-token>`.
4. Quan sát request AS nhận: **POST**, `Content-Type: application/x-www-form-urlencoded`, tham số `token` và cơ chế authentication được thỏa thuận.
5. Cho mock AS trả `{"active":true,"scope":"orders.read","aud":["orders-api"]}`, xác nhận authority và rule.
6. Cho mock AS trả `{"active":false}`, xác nhận API từ chối.
7. Cho mock AS trả 401 với credential sai, 503, timeout, JSON lỗi và dữ liệu thiếu audience; xác nhận **không có request được bảo vệ nào được thực hiện**.

Nên dùng **test credentials và test tokens**, không gọi introspection production từ unit/integration test. Nếu introspection response có metadata khác nhau giữa các nhà phát hành, hãy kiểm thử đúng schema của hệ thống và validation bổ sung.

### 13.4. Test client identity và token substitution

Ngoài active/inactive, test thêm:

- Token do AS cấp cho `billing-api` nhưng gửi tới Orders API → bị từ chối theo audience.
- Token `client_credentials` cho service A bị gửi đến endpoint chỉ dành cho user → bị từ chối theo policy.
- Hai Client có `client_id` khác nhau nhưng cùng scope → chỉ Client được cho phép trong ngữ cảnh nghiệp vụ mới được thao tác.
- Token của issuer không được tin cậy → bị từ chối theo endpoint/issuer validation contract.
- Token hợp lệ nhưng thiếu role/permission phụ → 403 ở authorization.

Những trường hợp này đảm bảo **`active = true` không bị dùng như “vé vào mọi API”**.

## 14. Kịch bản lỗi và mã HTTP ở Orders API

| Triệu chứng Client nhìn thấy | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| **401** khi không gửi token | Endpoint cần authentication | Xác nhận Client có gửi Bearer header |
| **401** với token từng hoạt động | Token hết hạn, bị thu hồi hoặc AS trả inactive | Kiểm tra kết quả introspection trên môi trường test/diagnostics an toàn |
| **401** dù token active | Audience/resource sai, claim bắt buộc thiếu hoặc policy token riêng | Kiểm tra hợp đồng introspection và validator |
| **403** với token active | Thiếu `SCOPE_orders.read` hoặc authority khác | Kiểm tra `scope` từ AS và rule Spring Security |
| **403/404** khi xem bản ghi | Sai owner/tenant/assignment hoặc resource không tồn tại | Kiểm tra policy dữ liệu |
| **5xx** hoặc lỗi xác thực liên tục khi AS down | Timeout, TLS, DNS, HTTP lỗi từ endpoint introspection | Xem logs dependency, timeout, connection pool, alert |
| Lỗi sau khi quay vòng client secret | Resource Server đang dùng secret cũ | Kiểm tra secret injection, rollout, AS registration |
| Mọi token bị inactive ở một môi trường | Sai introspection URI/tenant/realm hoặc permission của introspection Client | Kiểm tra issuer và environment contract |

**Mã thực tế phụ thuộc Spring Security version và exception handler**, đặc biệt với lỗi mạng/AS 5xx. Đừng che lỗi AS bằng cách tự đổi thành success hoặc cấp authority mặc định. Về mặt bảo mật, request không được thực hiện thao tác nếu không thể xác minh token.

### 14.1. Log, tracing và dữ liệu nhạy cảm

Có thể ghi:

- Request ID, endpoint, thời gian, HTTP status.
- Tên môi trường và introspection endpoint **được cấu hình**.
- Loại thất bại: inactive, invalid audience, insufficient scope, upstream timeout, client authentication error.
- Thời gian round trip introspection, số lần retry, tình trạng cache.
- Subject/client ID **chỉ khi đã nhận được từ nguồn tin cậy**, theo quy tắc audit và quyền riêng tư.

**Không ghi nguyên Bearer token hoặc introspection client secret** vào access log, log HTTP client, trace span, exception, URL query string hay metric label. Nếu cần liên kết truy vết token, có thể dùng một định danh opaque/HMAC dành riêng cho quan sát theo policy, không lưu plaintext token.

## 15. OIDC liên quan thế nào tới opaque access token?

**OpenID Connect (OIDC)** là lớp danh tính xây trên OAuth 2.0, có **ID token** để OIDC Client biết kết quả xác thực. ID token thường là JWT theo OIDC, nhưng **access token mà Client nhận không bắt buộc là JWT**.

Một hệ thống có thể có:

~~~text
Shop Web:
  nhận ID token JWT -> dùng để xử lý đăng nhập OIDC
  nhận opaque access token -> dùng gọi Orders API

Orders API:
  nhận opaque access token
  dùng introspection để xác thực và lấy scope/metadata
  không nhận ID token thay access token
~~~

Tình huống này hoàn toàn hợp lý. Không nhìn thấy `sub` bằng cách decode access token **không có nghĩa** người dùng chưa đăng nhập OIDC; đó chỉ là khác biệt giữa cơ chế mang danh tính tại Client và cơ chế ủy quyền cho API.

### 15.1. ID token không thay cho access token

ID token chủ yếu dành cho **OIDC Client** (audience thường là Client ID). Orders API yêu cầu access token có audience/resource và scope phù hợp. Khi introspection từ AS chấp nhận một chuỗi nào đó, hệ thống vẫn cần đảm bảo đó là **credential được phép dùng làm access token của API** theo hợp đồng, không chỉ là một token còn active ở nhà phát hành.

### 15.2. OAuth2 Client và Resource Server có cấu hình riêng

Shop Web có thể cần:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          shop-login:
            provider: shop-id
            client-id: ${SHOP_WEB_CLIENT_ID}
            client-secret: ${SHOP_WEB_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          shop-id:
            issuer-uri: ${SHOP_IDP_ISSUER_URI}
~~~

Đây là cấu hình **Client**, khác hoàn toàn với `spring.security.oauth2.resourceserver.opaque-token.*` của Orders API. Trong ví dụ này Shop Web là confidential Client; public Client cần mô hình khác (chẳng hạn PKCE, không nhúng client secret vào code phía browser/mobile).

Không mang Client secret của Shop Web vào Orders API nếu mục đích là introspection. Mỗi vai trò dùng đăng ký/credential phù hợp.

## 16. Một số nhầm lẫn phổ biến

**“Opaque token chắc chắn là chuỗi random không có cấu trúc.”** Không nhất thiết. Điểm cốt lõi là Resource Server không được tự giải thích token; nó dùng introspection hoặc cơ chế xác minh theo hợp đồng.

**“Không đọc được payload nên opaque token không thể có scope.”** Sai. AS có thể trả `scope`, `sub`, `aud`, `client_id` và nhiều metadata khác qua introspection.

**“`active = true` nghĩa là API nào cũng được phép nhận.”** Sai. Phải có resource/audience binding và scope/policy của từng API.

**“Introspection endpoint chính là token endpoint.”** Không. Token endpoint cấp token; introspection endpoint hỏi trạng thái của token đã cấp.

**“Gọi introspection là thu hồi token.”** Không. Revocation là một thao tác khác.

**“Resource Server nhận opaque token phải có private key của AS.”** Không. Trường hợp introspection thông thường cần endpoint và credential được phép; private signing key không thuộc Resource Server.

**“Introspection client ID chính là OAuth2 Client ID được ghi trong token.”** Không mặc nhiên. Một ID định danh **bên gọi introspection**; giá trị `client_id` trong response thường mô tả **bên được cấp token**.

**“Dùng `JwtDecoder` để xử lý opaque token bằng cách cắt dấu chấm.”** Sai cơ chế. Cần `OpaqueTokenIntrospector` hoặc phương thức kiểm tra được AS hỗ trợ.

**“Introspection online luôn phản ánh mọi thay đổi quyền ngay tức thì.”** Không chắc. Cần hiểu AS lưu và tính `scope`/roles/permission thế nào; cache phía Resource Server còn có thể làm chậm cập nhật.

**“AS down thì cứ cho qua token đã thấy trước đó.”** Không mặc định. Nếu có cache, hành vi phải nằm trong TTL và policy được thiết kế. Không có chứng cứ tin cậy còn hiệu lực thì fail closed.

**“Kết quả JSON tự gửi từ Client cũng có thể dùng làm introspection.”** Không. Chỉ phản hồi từ endpoint AS đáng tin, qua giao thức/kênh xác thực đúng, mới có thể làm cơ sở tạo Authentication.

**“Đã introspect active thì không cần kiểm tra owner/tenant.”** Sai. Quyền trên bản ghi vẫn là trách nhiệm của Resource Server.

## 17. Quy trình tích hợp thực tế

### Bước 1 — Thống nhất token contract

Identity team và Orders API team cần ghi rõ:

~~~yaml
# Hợp đồng minh họa, không phải cấu hình Spring đọc tự động.
resource_server: orders-api
access_token_format: opaque
trusted_authorization_server: https://identity.example.test
introspection_endpoint: https://identity.example.test/introspect
introspection_client: orders-api-introspection
introspection_auth_method: client_secret_basic
expected_audience: orders-api
required_response_attributes:
  - active
  - aud
  - scope
  - sub
authorization:
  GET /api/orders/{id}:
    scope: orders.read
    data_policy: owner_or_assigned_support
  POST /api/orders:
    scope: orders.write
    data_policy: tenant_can_create_order
inactive_token: reject
upstream_unavailable: fail_closed
~~~

Nếu AS không trả `sub` cho Client Credentials, hoặc không cung cấp `aud`, cần xây hợp đồng riêng cho loại token đó thay vì ép mọi token phải có user subject. Thông tin nào bắt buộc phải đúng với cách issuer thực sự hoạt động.

### Bước 2 — Cấp credential và cấu hình theo môi trường

Dev/staging/production cần:

- Introspection URI chính xác của môi trường.
- Introspection Client registration được phép và **credential riêng**.
- Yêu cầu TLS trust, proxy/network policy.
- Audience/resource và scope mapping cụ thể.
- Cơ chế rotation client secret và quan sát lỗi.

Không hardcode secrets trong source code. Nếu secrets được phân phối bằng biến môi trường, phải kiểm soát quyền xem process/config, log và CI/CD.

### Bước 3 — Cấu hình Resource Server và validation bổ sung

Dùng `opaque-token` trong Spring Security, không dùng `jwt` cho token được phát theo hợp đồng opaque. Nếu AS trả audience, viết validator như mục 8 để từ chối token dành cho API khác. Mapping roles/permissions chỉ thực hiện từ introspection metadata đã được tin.

### Bước 4 — Thử đường được phép và bị từ chối

Chạy bộ test active/inactive, wrong audience, missing scope, owner/tenant sai, introspection 401, 503, timeout và malformed response. Bảo đảm **không có thao tác nghiệp vụ khi bị từ chối**. Với test giao thức, dùng mock server để xác nhận POST/body/authentication đúng thay vì chỉ mock principal.

### Bước 5 — Đo độ trễ và thiết kế chịu lỗi

Đo P95/P99 latency introspection, kết nối, retry, tải AS và tỷ lệ timeout. Nếu dùng cache, ghi rõ giới hạn TTL và các trường hợp cần invalidation. Theo dõi sự khác nhau giữa token inactive bình thường và AS gặp sự cố.

### Bước 6 — Vận hành và quay vòng

Lên kế hoạch đổi introspection client secret, thay endpoint, thay chính sách active/scope và khôi phục AS. Tránh rollout nhiều bản sao API đồng thời khi AS không sẵn sàng nếu chúng phụ thuộc trực tiếp introspection. Không thay đổi cấu hình để **bỏ authentication** chỉ vì outage.

## 18. Bài tập tình huống

**Tình huống A:** Orders API nhận opaque token. Developer cố Base64URL decode token, thất bại và kết luận Client chưa đăng nhập. Kết luận có đúng không?

**Không.** Opaque token không có hợp đồng giải mã cục bộ. Resource Server phải dùng introspection theo thỏa thuận để biết active và metadata.

**Tình huống B:** Introspection trả `{"active":true,"scope":"orders.read","aud":["billing-api"]}`. Orders API có nên cho qua `GET /api/orders/42`?

**Không.** Token không dành cho Orders API. Cần từ chối theo audience/resource binding dù token active.

**Tình huống C:** Token active, audience đúng nhưng không có `orders.write`. Client gọi `POST /api/orders`. Lỗi thuộc lớp nào?

Authentication có thể thành công, nhưng **HTTP authorization** phải từ chối vì thiếu scope/authority yêu cầu, thường là **403**.

**Tình huống D:** Introspection endpoint trả `200 {"active":false}`. API có nên retry vô hạn vì HTTP status 200?

**Không.** `active: false` là kết quả token không active, không phải lỗi dịch vụ. API từ chối token; retry không thay thế quy trình cấp token mới.

**Tình huống E:** Introspection endpoint trả `401` do Orders API dùng secret đã hết hiệu lực. Có được xem mọi token là invalid do user và xóa tài khoản không?

**Không.** Đây là lỗi credential của Resource Server với AS. API vẫn không được chấp nhận token, nhưng chẩn đoán/vận hành phải chỉ ra nguyên nhân tích hợp chứ không quy cho chủ thể token.

**Tình huống F:** AS down, API có cache `active=true` của một token từ vài giờ trước và token đã bị thu hồi. Có nên tiếp tục chấp nhận vô hạn để duy trì availability?

**Không.** Chỉ có thể dùng cache theo TTL/revocation policy đã được phê duyệt; hết hạn hoặc không còn cơ sở tin cậy thì fail closed.

**Tình huống G:** Shop Web đăng nhập OIDC bằng ID token JWT và nhận access token opaque. Orders API có cần dùng JWT decoder cho access token không?

**Không theo hợp đồng này.** ID token phục vụ OIDC Client. Orders API dùng introspection cho opaque access token đã được cấp để gọi API.

**Tình huống H:** Unit test fake `OpaqueTokenIntrospector` trả principal có `SCOPE_orders.read`, API trả 200. Có thể kết luận HTTP POST tới introspection endpoint và Basic auth thực sự đúng chưa?

**Chưa.** Test giả lập chỉ chứng minh HTTP authorization. Cần integration test với mock introspection HTTP endpoint để kiểm tra request, credential và phản hồi thật.

---

## Kết luận

**Opaque access token không phải JWT mà Resource Server có thể tự đọc claims rồi tin ngay.** Với Spring Security OAuth 2.0 Resource Server, cơ chế chuẩn phổ biến là **OAuth 2.0 Token Introspection**: `BearerTokenAuthenticationFilter` chuyển token cho `OpaqueTokenAuthenticationProvider`/`OpaqueTokenIntrospector`, Resource Server gọi endpoint đáng tin với credential được cấp riêng, đánh giá `active` và metadata, rồi mới tạo `Authentication` cùng authorities như `SCOPE_orders.read`.

Để sử dụng an toàn, cần hiểu rõ ba ranh giới: **(1) token active không đồng nghĩa token dành cho API này; (2) scope/role không thay thế quyền trên bản ghi và tenant; (3) lỗi mạng hoặc introspection thất bại không được dẫn tới fail open**. Một thiết kế hoàn chỉnh phải có hợp đồng audience/resource, bí mật introspection riêng, kiểm thử positive/negative, cơ chế quan sát, xử lý timeout và chính sách cache/thu hồi phù hợp yêu cầu nghiệp vụ.
