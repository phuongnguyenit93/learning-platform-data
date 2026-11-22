# Cấu hình opaque token bằng introspection endpoint và thông tin xác thực

Trong một ứng dụng **Spring Security OAuth 2.0 Resource Server**, API thường nhận access token từ client qua header `Authorization: Bearer ...`. Nếu access token là **opaque token** (chuỗi mà API không tự giải mã và xác minh claim được), Resource Server cần một cách đáng tin cậy để biết token còn hiệu lực, được cấp cho ai và có những quyền gì. Phương thức phổ biến là gửi token đến **token introspection endpoint** do Authorization Server cung cấp, theo cơ chế của **RFC 7662**.

Để cấu hình thành công, cần phân biệt rõ **hai loại thông tin xác thực** trong một request có introspection:

1. **Access token từ client gửi tới Resource Server**: credential của request nghiệp vụ, ví dụ `Authorization: Bearer <ACCESS_TOKEN>`.
2. **Thông tin xác thực của Resource Server khi gọi introspection endpoint**: credential riêng để Authorization Server cho phép API tra cứu trạng thái token, thường là **introspection client ID + client secret**, được gửi bằng HTTP Basic qua HTTPS.

Đây là hai thông tin khác mục đích. **Không dùng access token của người dùng làm client secret**; cũng không gửi client secret của Resource Server trong phản hồi API hay cho trình duyệt. Bài học trình bày cách thiết kế hợp đồng này và cấu hình trên **Spring MVC/Servlet** cũng như **Spring WebFlux/Reactive**, kèm ví dụ HTTP, YAML, Java, phân quyền, lỗi vận hành và bảo mật.

> Các hostname, token, client ID và URL trong bài là **ví dụ giả lập**. Với hệ thống thật, cần lấy endpoint và chính sách xác thực từ Authorization Server/nhà cung cấp danh tính (IdP) đã tin cậy.

## 1. Opaque access token và token introspection là gì?

OAuth 2.0 không bắt buộc access token có cấu trúc JWT. Authorization Server có thể cấp một chuỗi mà chỉ nó hiểu được, ví dụ:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer opa_9f47a2e1c9b84d67a03
Accept: application/json
~~~

Giá trị `opa_9f47a2e1c9b84d67a03` chỉ minh họa, không có hiệu lực thật. Client không cần biết token biểu diễn thế nào: nó chỉ đặt **chuỗi access token** sau scheme `Bearer`. Resource Server cũng **không nên suy đoán** rằng token có quyền gì chỉ từ các ký tự trong chuỗi.

**Introspection** là yêu cầu backend-to-backend từ Resource Server đến một endpoint được Authorization Server bảo vệ. Resource Server gửi token cần kiểm tra và xác thực **chính nó** với endpoint. Authorization Server trả lời token có `active` không và, khi phù hợp, các metadata như `scope`, `sub`, `client_id`, `exp` hoặc `aud`.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server (Orders API)
    participant AS as Authorization Server
    C->>RS: GET /api/orders/42 + Bearer opaque token
    RS->>AS: POST /oauth2/introspect<br/>token=... + xác thực introspection client
    AS->>AS: Kiểm tra token và quyền tra cứu của RS
    AS-->>RS: JSON: active, scope, sub, ...
    alt Token active và đủ quyền
        RS->>RS: Tạo Authentication, kiểm tra scope và policy
        RS-->>C: 200 OK (hoặc response nghiệp vụ)
    else Token inactive/không phù hợp
        RS-->>C: 401 Unauthorized
    else Token active nhưng thiếu quyền
        RS-->>C: 403 Forbidden
    end
~~~

### 1.1. Opaque token khác JWT theo cách Resource Server xử lý

| Tiêu chí | JWT access token được xác minh cục bộ | Opaque access token với introspection |
|---|---|---|
| Hình dạng token | Thường có ba phần Base64URL phân cách bằng dấu chấm | Không cần có cấu trúc API đọc được |
| Phương thức kiểm tra điển hình | Xác minh chữ ký/JWK, issuer, thời gian, audience, claim validation | Gọi introspection endpoint tin cậy, nhận `active` và metadata |
| Phụ thuộc kết nối đến Authorization Server mỗi request | Thường không, sau khi cache JWK/metadata phù hợp | Thường có, trừ khi có cache được thiết kế rõ |
| Khả năng nhận biết token bị thu hồi | Cần chiến lược revocation riêng hoặc TTL ngắn | Có thể phát hiện gần thời gian thực qua introspection, tùy cache và chính sách AS |
| Thông tin được Resource Server sử dụng | Các claim JWT **sau khi xác minh** | Các thuộc tính introspection **từ endpoint tin cậy** |
| Cách client gửi token | `Authorization: Bearer <token>` | `Authorization: Bearer <token>` |

Introspection cũng có thể áp dụng cho token ở định dạng JWT nếu hệ thống chủ động chọn cách đó. Tên `opaqueToken(...)` trong Spring Security chỉ **đường xác thực bằng introspection**, không phải lệnh kiểm tra định dạng token phải là một loại chuỗi cụ thể.

## 2. Phân biệt ba endpoint thường bị nhầm

Trong hệ thống OAuth 2.0/OIDC có nhiều endpoint cùng thuộc Authorization Server. Chúng không thể thay thế cho nhau:

| Endpoint | Ai gọi | Mục đích | Dữ liệu gửi đi |
|---|---|---|---|
| **Token endpoint** | OAuth 2.0 client | Xin access token/refresh token theo grant | `grant_type`, code, client credential, refresh token... |
| **Introspection endpoint** | Resource Server hoặc client được AS cho phép | Kiểm tra một token đã cấp và lấy metadata theo quyền tra cứu | `token`, tùy chọn `token_type_hint`; caller phải được xác thực/ủy quyền phù hợp |
| **OIDC UserInfo endpoint** | OIDC client với access token phù hợp | Lấy claim về end-user theo OIDC | Access token dành cho UserInfo, thường gửi Bearer |
| **JWK Set endpoint** | Thành phần xác minh JWT | Lấy khóa công khai được công bố | Thường GET; không phải chỗ hỏi `active` của opaque token |

Ví dụ endpoint introspection (không có hiệu lực thật):

~~~text
https://idp.example.test/oauth2/introspect
~~~

Không tự ghép hậu tố `/introspect` từ URL của login page hoặc token endpoint trừ khi nhà cung cấp công bố đúng đường dẫn. Với Authorization Server hỗ trợ metadata, có thể tìm `introspection_endpoint` trong **OAuth 2.0 Authorization Server Metadata**, nhưng cần kiểm tra sự tương thích với IdP và cấu hình bảo mật thực tế. Khả năng có OIDC discovery không tự bảo đảm mọi nhà cung cấp đều hỗ trợ introspection cho từng loại token.

## 3. Introspection HTTP request gửi những gì?

Theo RFC 7662, Resource Server gửi HTTP `POST` tới introspection endpoint, sử dụng `application/x-www-form-urlencoded`. Tham số quan trọng nhất là `token`:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.test
Authorization: Basic <BASE64_OF_CLIENT_ID_COLON_CLIENT_SECRET>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=opa_9f47a2e1c9b84d67a03&token_type_hint=access_token
~~~

Giải thích các thành phần:

- `POST /oauth2/introspect`: request **từ Resource Server tới Authorization Server**, không phải request API của end-user.
- `Authorization: Basic ...`: chứng minh danh tính **introspection client** khi nhà cung cấp dùng HTTP Basic. Chuỗi Base64 mã hóa client ID và client secret theo cách HTTP Basic yêu cầu; Base64 **không phải mã hóa bảo mật**, nên kết nối phải dùng HTTPS.
- `Content-Type: application/x-www-form-urlencoded`: yêu cầu POST dùng dữ liệu form theo RFC 7662.
- `token`: **access token cần kiểm tra**; không phải secret của introspection client.
- `token_type_hint=access_token`: gợi ý tùy chọn cho Authorization Server; không phải tham số bắt buộc và nhà cung cấp có thể bỏ qua.
- `Accept: application/json`: client mong muốn phản hồi JSON.

`token` có thể chứa những ký tự cần percent-encoding; HTTP client hoặc thư viện Spring có trách nhiệm mã hóa form đúng cách. **Không tự nối token vào URL query** khi endpoint yêu cầu form body.

### 3.1. Ví dụ trả về token đang active

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read orders.create",
  "client_id": "shop-web-client",
  "sub": "user-123",
  "token_type": "Bearer",
  "exp": 1924992000,
  "iat": 1924988400,
  "aud": ["orders-api"],
  "iss": "https://idp.example.test"
}
~~~

`active: true` cho biết token được Authorization Server xem là còn active theo chính sách của nó. **Không phải mọi Authorization Server đều trả đủ các field trên**. Theo RFC 7662, ngoài `active` các thuộc tính khác được công bố tùy token và chính sách tiết lộ thông tin cho caller.

| Field | Ý nghĩa | Cách API sử dụng |
|---|---|---|
| `active` | Token còn được công nhận hay không | Bắt buộc kiểm tra khi introspection |
| `scope` | Những scope đã được cấp, thường phân tách bằng dấu cách | Ánh xạ thành authorities rồi kiểm tra endpoint |
| `sub` | Chủ thể mà token đại diện theo profile AS | Dùng cho nhận diện principal và quyền dữ liệu, nếu có |
| `client_id` | Client nhận token theo nghĩa AS công bố | Dùng nếu policy giới hạn client gọi API |
| `token_type` | Loại token, thường Bearer | Đối chiếu profile khi hợp đồng yêu cầu |
| `exp` / `iat` / `nbf` | Thời điểm hết hạn, cấp phát, bắt đầu hiệu lực | Giới hạn thời gian và chính sách caching khi có |
| `aud` | Resource/API nhận token | Kiểm tra token có dành cho API hiện tại không nếu được trả về |
| `iss` | Nguồn phát hành token | Kiểm tra khi profile/hợp đồng sử dụng field này |

**Không tin rằng `active=true` đồng nghĩa với “mọi API đều có thể chấp nhận token”.** Nếu một AS phát hành token cho nhiều Resource Server, API cần có hợp đồng ràng buộc audience/resource và cách kiểm tra quyền của introspection caller. Khi field `aud` không được cung cấp, tính phù hợp của resource phải được bảo đảm bằng quy tắc khác đã thỏa thuận với Authorization Server.

### 3.2. Token không active

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
~~~

Một opaque token có thể không active vì hết hạn, bị thu hồi, không tồn tại hoặc không được caller phép tra cứu. Theo RFC 7662, server có thể không tiết lộ lý do cụ thể. **HTTP 200 từ introspection endpoint không có nghĩa access token hợp lệ**; phải đọc `active`.

### 3.3. Introspection client bị từ chối

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
~~~

Đây là tình huống **Resource Server không được phép gọi introspection**, ví dụ sai client secret, client ID, phương thức xác thực hoặc policy. Nó khác với trường hợp introspection trả HTTP 200 và `{"active": false}` vì token của end-user không hợp lệ. Phân biệt hai trường hợp giúp xử lý lỗi đúng nguyên nhân.

## 4. Hai cặp credential và nơi lưu

| Luồng | Credential | Gửi tới | Ai quản lý |
|---|---|---|---|
| Client → API | `Authorization: Bearer <ACCESS_TOKEN>` | Resource Server | OAuth client nhận token từ AS |
| API → Introspection endpoint | `Authorization: Basic <BASE64(id:secret)>` trong cấu hình điển hình | Authorization Server | Resource Server quản lý ID/secret được AS cấp |

Nếu dùng phương thức xác thực introspection khác như **mTLS**, **private_key_jwt**, hoặc Basic kèm cơ chế riêng của nhà cung cấp, cần cấu hình HTTP client/introspector tương ứng. **Ba property cấu hình mặc định dưới đây không tự hỗ trợ mọi loại client authentication**.

Introspection client cần được Authorization Server cấp quyền **tra cứu đúng phạm vi token/resource**. Không nên dùng secret của OAuth client trình duyệt hoặc secret của Authorization Server làm secret introspection. Với mô hình nhiều API, có thể cần client introspection riêng cho từng Resource Server để giữ ranh giới quyền và audit.

### Mối liên hệ giữa `client-id` và `aud`

`client-id` trong cấu hình introspection là **danh tính của Resource Server khi gọi introspection endpoint**. `aud` của access token xác định **API được phép nhận token**. Hai giá trị này có thể khác nhau:

~~~text
Introspection client-id = orders-introspection-client
Token audience         = orders-api
Token client_id        = shop-web-client
~~~

Đó là ba danh tính có mục đích khác nhau. Đừng tự gán `client-id` của introspection bằng `aud` hay `client_id` bên trong access token nếu hợp đồng với AS không yêu cầu như vậy.

## 5. Cấu hình Spring Boot Resource Server sử dụng introspection

Ví dụ cho một Orders API dùng Spring Boot + Spring Security với **opaque token introspection**. Đầu tiên thêm dependency:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Ví dụ môi trường chạy ứng dụng cần cung cấp các giá trị tương ứng:

~~~text
OAUTH_INTROSPECTION_URI=https://idp.example.test/oauth2/introspect
OAUTH_INTROSPECTION_CLIENT_ID=orders-introspection-client
OAUTH_INTROSPECTION_CLIENT_SECRET=<secret-stored-securely>
~~~

Đây là **giá trị minh họa**, không được commit secret thật vào Git, hình ảnh, issue tracker hoặc tài liệu công khai. Property `client-secret` phải lấy từ secret manager, biến môi trường được bảo vệ hoặc cơ chế cấu hình an toàn của hệ thống triển khai.

### 5.1. Ý nghĩa chính xác của từng property

| Spring Boot property | Được dùng làm gì? |
|---|---|
| `spring.security.oauth2.resourceserver.opaquetoken.introspection-uri` | URL HTTPS mà Resource Server gửi token cần kiểm tra |
| `spring.security.oauth2.resourceserver.opaquetoken.client-id` | ID của Resource Server tại introspection endpoint |
| `spring.security.oauth2.resourceserver.opaquetoken.client-secret` | Secret để xác thực Resource Server với introspection endpoint |

Tên property **`opaquetoken`** được viết liền trong đường dẫn cấu hình. Đừng nhầm với `oauth2.client.registration.*` — nhóm property đó dùng cho ứng dụng đóng vai trò **OAuth 2.0 Client**, còn ở đây ứng dụng đóng vai trò **Resource Server** đi introspect token.

Spring Boot sẽ tạo các thành phần introspection phù hợp khi dependency và property được cấu hình và không có bean tùy chỉnh thay thế. Tương ứng với stack Servlet là giao diện `OpaqueTokenIntrospector`; với WebFlux là `ReactiveOpaqueTokenIntrospector`.

### 5.2. Bật opaque token trên HTTP security

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(withDefaults()))
            .build();
    }
}
~~~

Ví dụ trên giả định API **thuần Bearer token, không dùng cookie/session đăng nhập trình duyệt**, do đó minh họa `SessionCreationPolicy.STATELESS` và tắt CSRF. Nếu ứng dụng có login bằng cookie/session hoặc luồng trình duyệt có nguy cơ CSRF, phải thiết kế CSRF protection riêng; không tự tắt CSRF cho toàn bộ ứng dụng.

Trong cấu hình này:

- `oauth2ResourceServer(...opaqueToken(...))` bật cách xác thực access token qua introspection.
- Spring Security dùng cấu hình endpoint và credentials từ YAML để gọi Authorization Server.
- `authorizeHttpRequests(...)` áp dụng quyền truy cập sau xác thực.
- `hasAuthority("SCOPE_orders.read")` kiểm tra scope được ánh xạ từ kết quả introspection.
- `anyRequest().authenticated()` yêu cầu token hợp lệ cho request còn lại; ứng dụng thật cần thiết kế rule cụ thể cho từng endpoint, tránh mở hành động nhạy cảm chỉ với xác thực chung.

### 5.3. Controller đọc principal đã xác thực

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentUserController {

    @GetMapping("/api/me")
    Map<String, String> me(@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("principal", principal.getName());
    }
}
~~~

Ở Resource Server opaque token, Spring Security thường tạo `BearerTokenAuthentication` với principal kiểu `OAuth2AuthenticatedPrincipal` và authorities từ scopes. `principal.getName()` phụ thuộc thuộc tính `sub` hoặc cấu hình/đặc điểm introspection response. Nếu token đại diện cho service, giá trị principal không nhất thiết là username người thật. Không dùng ví dụ này để suy ra quyền truy cập dữ liệu chỉ từ tên principal.

## 6. Luồng thực thi trong Servlet

Khi một request đến:

~~~mermaid
flowchart TD
    A["Client gửi Authorization: Bearer token"] --> B["Spring Security FilterChainProxy"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["BearerTokenAuthenticationToken"]
    D --> E["AuthenticationManager / OpaqueTokenAuthenticationProvider"]
    E --> F["OpaqueTokenIntrospector"]
    F --> G["POST introspection qua HTTPS + xác thực client"]
    G --> H{"active = true?"}
    H -->|No| I["Authentication failure → HTTP 401"]
    H -->|Yes| J["OAuth2AuthenticatedPrincipal + GrantedAuthority"]
    J --> K["BearerTokenAuthentication / SecurityContext"]
    K --> L{"Đủ authority và policy?"}
    L -->|No| M["HTTP 403"]
    L -->|Yes| N["Controller / Service"]
~~~

Resource Server **không tự cấp token** và cũng không gửi password của end-user vào introspection. Nó dùng token đã nhận trong request để hỏi Authorization Server, sau đó đưa principal đã được xác thực vào security context của request.

### Trách nhiệm của những class quan trọng

| Thành phần Spring Security (Servlet) | Trách nhiệm |
|---|---|
| `SecurityFilterChain` | Cấu hình nhóm request được bảo vệ |
| `BearerTokenAuthenticationFilter` | Trích Bearer token và kích hoạt xác thực |
| `BearerTokenAuthenticationToken` | Biểu diễn credential chưa xác thực |
| `AuthenticationManager` / `OpaqueTokenAuthenticationProvider` | Điều phối và xử lý xác thực opaque token |
| `OpaqueTokenIntrospector` | Thực hiện introspection, trả principal được xác thực |
| `OAuth2AuthenticatedPrincipal` | Đại diện principal và những attribute/authority thu được |
| `BearerTokenAuthentication` | Kết quả xác thực Bearer token được đặt vào context |
| `AuthorizationFilter` / rule URL | Kiểm tra authority và chính sách truy cập |

Spring Security phụ trách đường xử lý chuẩn. Ứng dụng nên cấu hình endpoint và quyền đúng hợp đồng, đồng thời chỉ bổ sung introspector tùy chỉnh khi có yêu cầu cụ thể như audience, tenant, mapping thuộc tính hoặc kiểu client authentication không được mặc định hỗ trợ.

## 7. Cấu hình cùng hợp đồng trên Spring WebFlux

Khi ứng dụng chạy **Spring WebFlux**, header client gửi đến API và hợp đồng introspection **không đổi**. Tuy nhiên, pipeline bảo mật sử dụng `SecurityWebFilterChain`, `ServerHttpSecurity` và `ReactiveOpaqueTokenIntrospector` thay cho các interface Servlet.

Dependency cho ứng dụng reactive:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml` dùng cùng nhóm property:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Cấu hình Java tương ứng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .csrf(csrf -> csrf.disable())
            .authorizeExchange(auth -> auth
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(withDefaults()))
            .build();
    }
}
~~~

Đoạn `csrf.disable()` chỉ minh họa giả định ứng dụng là API Bearer thuần, không dựa vào cookie/session. Khi có giao diện đăng nhập bằng cookie, cần cấu hình CSRF riêng như ở Servlet.

Sơ đồ reactive:

~~~mermaid
flowchart TD
    A["Request Bearer token"] --> B["WebFilterChainProxy / SecurityWebFilterChain"]
    B --> C["AuthenticationWebFilter"]
    C --> D["ReactiveAuthenticationManager"]
    D --> E["OpaqueTokenReactiveAuthenticationManager"]
    E --> F["ReactiveOpaqueTokenIntrospector"]
    F --> G["HTTP introspection → Mono<OAuth2AuthenticatedPrincipal>"]
    G --> H["Reactive SecurityContext"]
    H --> I["authorizeExchange"]
    I --> J["WebFlux handler"]
~~~

Lời gọi HTTP tới introspection endpoint phải phù hợp với mô hình reactive để không chặn event loop. Nếu tự viết `ReactiveOpaqueTokenIntrospector`, không gọi HTTP client blocking ngay trong operator như `Mono.just(blockingCall())`. Tránh `block()` trong xử lý request WebFlux.

### 7.1. So sánh các interface

| Trách nhiệm | Servlet / Spring MVC | Reactive / WebFlux |
|---|---|---|
| HTTP security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Cấu hình security | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Bộ lọc Bearer | `BearerTokenAuthenticationFilter` | `AuthenticationWebFilter` |
| Manager cho opaque token | `OpaqueTokenAuthenticationProvider` | `OpaqueTokenReactiveAuthenticationManager` |
| Tích hợp introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Context bảo mật | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Quy tắc scope | `authorizeHttpRequests(...).hasAuthority(...)` | `authorizeExchange(...).hasAuthority(...)` |
| Công cụ HTTP test | `MockMvc` | `WebTestClient` |

Ứng dụng Spring MVC có thể dùng `WebClient` làm HTTP client nhưng điều đó không biến `HttpSecurity` thành `ServerHttpSecurity`. Kiểu cấu hình bảo mật phải tương ứng với **runtime web thực tế** của ứng dụng.

## 8. Scope và principal sau khi introspection thành công

Khi introspection trả:

~~~json
{
  "active": true,
  "scope": "orders.read orders.create",
  "sub": "user-123",
  "client_id": "shop-web-client"
}
~~~

Spring Security thường ánh xạ scope thành các `GrantedAuthority` mang tiền tố `SCOPE_`:

~~~text
scope = "orders.read orders.create"
    ↓
GrantedAuthority: SCOPE_orders.read
GrantedAuthority: SCOPE_orders.create
~~~

Trong `SecurityFilterChain`, khai báo:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Khi đó:

- Token `active=true`, có `orders.read`: qua bước **xác thực** và đáp ứng **rule scope** của GET.
- Token `active=true`, chỉ có `orders.create`: đã xác thực nhưng thiếu quyền GET, thông thường trả **403 Forbidden**.
- Token `active=false`: không tạo principal hợp lệ, thông thường trả **401 Unauthorized**.
- Token `active=true` nhưng principal cố đọc đơn hàng thuộc người khác: service phải **tiếp tục kiểm tra sở hữu dữ liệu/tenant**, không chỉ dựa vào scope.

### 8.1. Quyền hành động và quyền trên tài nguyên

| Endpoint | Scope tối thiểu minh họa | Kiểm tra nghiệp vụ riêng |
|---|---|---|
| `GET /api/orders/{id}` | `orders.read` | Chủ đơn/tenant/quyền chia sẻ |
| `POST /api/orders` | `orders.create` | Khách hàng còn hoạt động, nội dung hợp lệ |
| `POST /api/orders/{id}/cancel` | `orders.cancel` | Chủ đơn và trạng thái cho phép hủy |
| `GET /api/admin/orders` | `orders.admin.read` | Vai trò quản trị và ranh giới tenant |

Không suy ra rằng `client_id` của access token chính là tài khoản end-user. Với grant `client_credentials`, token có thể đại diện cho một dịch vụ, còn với authorization code, nó có thể đại diện cho user và client theo token profile. Hợp đồng introspection cần định nghĩa ý nghĩa của `sub`, `client_id`, `aud` và các claim mở rộng.

### 8.2. Introspection không tự giải quyết audience/issuer binding

Một Authorization Server có thể phát hành token cho nhiều API. Khi đó:

~~~text
Orders API audience  = orders-api
Billing API audience = billing-api
Trusted AS           = https://idp.example.test
~~~

Token dành cho `billing-api` **không nên** được Orders API chấp nhận chỉ vì introspection trả `active=true`. API cần xác định cách đảm bảo ràng buộc resource:

1. AS giới hạn kết quả introspection cho từng Resource Server theo danh tính introspection client và chỉ trả `active=true` với token đúng resource; **hoặc**
2. AS trả `aud`/metadata được tin cậy và Resource Server áp validator cho audience của chính mình; **hoặc**
3. Có cơ chế khác đã thỏa thuận và được thực thi chặt chẽ để chứng minh token dành cho API.

Không giả định Spring Security mặc định sẽ kiểm tra `aud` hay `iss` trong mọi introspection response như với JWT decoder. **Đường tin cậy cốt lõi của introspection là endpoint đã cấu hình, TLS, client authentication và hợp đồng dữ liệu trả về.**

## 9. Khi nào cần `OpaqueTokenIntrospector` tùy chỉnh?

Chỉ dùng ba property endpoint/ID/secret là đủ cho luồng introspection cơ bản khi AS dùng phương thức xác thực được hỗ trợ và hợp đồng mặc định đáp ứng nhu cầu. **Introspector tùy chỉnh** phù hợp trong các tình huống:

- AS trả thêm claim tenant, audience, role và Resource Server bắt buộc kiểm tra trước khi chấp nhận token.
- API cần đổi cách ánh xạ scope/role thành `GrantedAuthority`.
- Endpoint yêu cầu cơ chế HTTP client riêng, timeout, proxy, chứng thư mTLS, `private_key_jwt` hoặc body authentication khác Basic.
- Hệ thống cần cơ chế cache có chính sách, đo độ trễ, retry hữu hạn hoặc failover.
- Resource Server cần giới hạn token chỉ cho một số client/issuer/resource cụ thể theo hợp đồng.

**Nguyên tắc mở rộng:** nhận access token → gọi implementation introspection đáng tin cậy → kiểm tra `active`/metadata theo policy → chỉ trả principal sau khi tất cả điều kiện bắt buộc đã đúng. Không tạo principal thành công khi introspection thất bại hoặc timeout.

### 9.1. Ví dụ wrapper kiểm tra audience

Ví dụ sau minh họa phần kiểm tra audience khi một **delegate introspector đã được cấu hình an toàn**. Nó là class bổ sung, cần được wiring vào bean/DSL theo phiên bản Spring Security và loại ứng dụng thực tế. Không dùng nó thay cho việc xác thực với introspection endpoint.

~~~java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class AudienceCheckingIntrospector implements OpaqueTokenIntrospector {
    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
        Object audience = principal.getAttribute("aud");

        boolean accepted =
            (audience instanceof String && expectedAudience.equals(audience))
            || (audience instanceof Collection<?>
                && ((Collection<?>) audience).contains(expectedAudience));

        if (!accepted) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error(
                    "invalid_token",
                    "The token is not intended for this API",
                    null
                )
            );
        }
        return principal;
    }
}
~~~

Class trên **không tự biết endpoint hoặc thông tin xác thực**: delegate phải được tạo từ HTTP client/introspector thật với URL và credential đã được tin cậy. Trong Spring Boot, nếu tự đăng ký `OpaqueTokenIntrospector` bean, auto-configuration có thể không còn tự tạo bean mặc định cho bạn; cần wiring delegate và wrapper rõ ràng để tránh tạo bean tự tham chiếu.

Tùy Authorization Server, claim `aud` có thể là chuỗi, danh sách hoặc vắng mặt. Với policy ví dụ này, claim thiếu sẽ bị từ chối. Nếu AS không trả audience, phải có ràng buộc resource đáng tin cậy ở phía server hoặc một cơ chế được thỏa thuận khác, thay vì bỏ qua kiểm tra mà không đánh giá.

Trong WebFlux, cơ chế tương tự phải thực hiện bằng `ReactiveOpaqueTokenIntrospector` và publisher phù hợp. Ví dụ Servlet không thể sử dụng nguyên dạng cho WebFlux chỉ bằng thay tên import.

### 9.2. Phương thức xác thực introspection khác HTTP Basic

HTTP Basic với `client-id` và `client-secret` là đường cấu hình phổ biến của Spring Boot opaque-token Resource Server. Một số Authorization Server lại yêu cầu:

| Cơ chế | Tác dụng | Điều cần triển khai thêm |
|---|---|---|
| `client_secret_basic` | Gửi ID/secret qua HTTP Basic | Thường dùng với property mặc định |
| `client_secret_post` | Gửi credential trong form body | Cần HTTP client/introspector hỗ trợ theo quy ước AS |
| `private_key_jwt` | Chứng minh client bằng JWT assertion ký bằng private key | Cần ký assertion, quản lý khóa, claims và endpoint đúng profile |
| Mutual TLS (mTLS) | Resource Server xác thực bằng client certificate | Cấu hình keystore/truststore, HTTP client TLS và policy AS |
| Cơ chế riêng của nhà cung cấp | Ví dụ gateway token hoặc auth header đặc thù | Phải kiểm tra tài liệu AS và xây integration tương ứng |

Không tự thay `Authorization: Basic` bằng `Authorization: Bearer <ACCESS_TOKEN_CUA_NGUOI_DUNG>` trừ khi giao thức riêng của Authorization Server thực sự yêu cầu một token quản trị phù hợp và đã được cấp cho đúng mục đích. Token cần introspect và credential để **được phép introspect** là hai thực thể khác nhau.

### 9.3. Hết hạn và luân chuyển introspection secret

Client secret dùng cho introspection thường có vòng đời do Authorization Server quy định. Nếu secret bị thu hồi hoặc đổi mà API vẫn sử dụng secret cũ, các lệnh introspection có thể thất bại đồng loạt. Một quy trình luân chuyển nên có:

1. Khả năng phát hành secret mới trong secret manager và giới hạn ai có quyền đọc.
2. Cơ chế triển khai/reload hoặc rolling restart để Resource Server dùng credential mới.
3. Chính sách chuyển tiếp khi cả secret cũ và mới cùng hợp lệ, nếu AS hỗ trợ.
4. Kiểm tra health và tín hiệu lỗi xác thực introspection sau khi đổi.
5. Thu hồi secret cũ theo quy trình có kiểm soát.

Không ghi giá trị secret cũ/mới vào log hoặc trạng thái lỗi. **Giữ secret riêng theo môi trường**: production secret không được dùng lại ở môi trường development hoặc staging.

## 10. Thử introspection endpoint bằng HTTP client

Trước khi kết nối Spring Security, đội tích hợp có thể thử introspection endpoint bằng **token thử nghiệm**, tài khoản introspection riêng của môi trường test và kết nối HTTPS. Việc này giúp phân biệt lỗi **endpoint/credentials** với lỗi **cấu hình Spring Security**.

### 10.1. cURL gửi introspection request

Ví dụ Bash/Zsh khi các biến môi trường đã được thiết lập một cách an toàn:

~~~bash
curl --silent --show-error --fail-with-body \
  --request POST \
  --user "$OAUTH_INTROSPECTION_CLIENT_ID:$OAUTH_INTROSPECTION_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=$ACCESS_TOKEN" \
  --data-urlencode "token_type_hint=access_token" \
  "https://idp.example.test/oauth2/introspect"
~~~

`--data-urlencode` giúp mã hóa token theo form body. `--user` để cURL sử dụng HTTP Basic theo hợp đồng ví dụ. Trên hệ thống có yêu cầu bảo vệ credential nghiêm ngặt, lưu ý rằng các tham số lệnh và biến môi trường có thể bị công cụ giám sát tiến trình, shell hoặc hệ thống CI ghi lại; dùng cơ chế quản lý secret và phương thức thử an toàn của tổ chức. Không dùng token thật trong bản chụp màn hình, ví dụ hướng dẫn hoặc log chia sẻ.

**Kết quả cần phân biệt:**

~~~text
HTTP 200 + {"active": true, ...}
    → introspection caller được chấp nhận; token active.

HTTP 200 + {"active": false}
    → introspection caller được chấp nhận; token không active
      hoặc không được phép nhận chi tiết token theo chính sách AS.

HTTP 401/403 từ chính introspection endpoint
    → thường là sai/thiếu credential hoặc caller không đủ quyền tra cứu.

HTTP 404/405
    → thường liên quan URL endpoint/phương thức HTTP sai.

TLS/DNS/timeout/5xx
    → kết nối, cấu hình, tính sẵn sàng hoặc lỗi phía AS/gateway.
~~~

Đừng chỉ nhìn status HTTP 200 của introspection rồi kết luận token hợp lệ. Trường quyết định token đang active là `active`, kết hợp với các thuộc tính phù hợp policy API.

### 10.2. cURL gọi Resource Server

Sau khi cấu hình Spring Security, client thử gọi API với token:

~~~bash
curl --silent --show-error --include \
  --header "Authorization: Bearer $ACCESS_TOKEN" \
  --header "Accept: application/json" \
  "https://orders-api.example.test/api/orders/42"
~~~

Khác biệt quan trọng: request này gửi **Bearer access token cho Orders API**, không gửi introspection client ID/secret. Các giá trị introspection client chỉ tồn tại ở backend.

Không test bằng cách tắt xác thực hoặc chuyển token vào URL query. Một API trả 200 khi bỏ toàn bộ security chain chưa chứng minh endpoint introspection đã được cấu hình đúng.

## 11. Trạng thái lỗi từ hai chặng HTTP khác nhau

Một request opaque token trải qua hai HTTP exchange: client ↔ API và API ↔ Authorization Server. Vì vậy có thể có lỗi ở chặng thứ hai mà client chỉ nhìn thấy biểu hiện ở chặng thứ nhất.

### 11.1. Không gửi access token

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Accept: application/json
~~~

Resource Server bảo vệ endpoint thường trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Trong trường hợp này thường **không cần** gọi introspection endpoint vì không có credential để kiểm tra.

### 11.2. Access token inactive hoặc không hợp lệ

Introspection trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
~~~

Resource Server thường phản hồi tới client:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Không chuyển nguyên thông tin nhạy cảm từ Authorization Server ra client. `invalid_token` đủ diễn đạt rằng Bearer credential bị từ chối, trừ khi API có hợp đồng lỗi cụ thể cần công bố thêm.

### 11.3. Access token active nhưng thiếu scope

Introspection có thể trả `active=true` và `scope="orders.create"` trong khi client đang gọi `GET /api/orders/42` yêu cầu `orders.read`. Khi đó xác thực token có thể thành công, nhưng authorization từ chối:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Header trên là ví dụ theo RFC 6750. Hành vi mặc định và nội dung `WWW-Authenticate` cụ thể có thể khác theo cấu hình Spring Security/authorization handler; quy tắc chính vẫn là **401 cho thiếu/sai credential, 403 cho thiếu quyền sau xác thực**.

### 11.4. Sai introspection client secret

Authorization Server trả 401 cho chính cuộc gọi introspection. Đây là **lỗi cấu hình hoặc quyền của Resource Server**, không có nghĩa mọi token end-user đều không hợp lệ. Ứng dụng phải **không cho phép request** chỉ vì không thể introspect; response HTTP tới caller có thể là 5xx hoặc mã khác tùy exception handling. Không gán cứng mọi lỗi upstream thành 401 của end-user, khiến việc vận hành khó phát hiện secret bị sai/thu hồi.

### 11.5. Introspection endpoint timeout hoặc unavailable

Nếu không thể kiểm chứng token, cần bảo đảm request không tiếp tục như đã xác thực. Hành vi fail-closed về **quyền truy cập** không yêu cầu mọi lỗi upstream phải trả cùng một mã HTTP. Hệ thống có thể thiết kế 503/500 và cơ chế cảnh báo phù hợp; mục tiêu là **không chấp nhận credential chưa kiểm chứng**.

| Lớp lỗi | Dấu hiệu | Hành động |
|---|---|---|
| Client → API thiếu token | Request không có Bearer header | Yêu cầu client gửi access token |
| Client → API có token inactive | Introspection HTTP 200, `active=false` | Từ chối token, client cần lấy token hợp lệ |
| Client → API thiếu scope | Introspection active, thiếu `SCOPE_*` | Từ chối phân quyền |
| API → AS thiếu quyền | Introspection HTTP 401/403 | Sửa registration/secret/policy của introspection client |
| API → AS lỗi kết nối | DNS, TLS, timeout, gateway 502, AS 5xx | Kiểm tra hạ tầng, timeout, khả năng phục hồi |
| API chấp nhận token của resource khác | Introspection thiếu resource binding | Bổ sung kiểm tra audience/policy đã thỏa thuận |

## 12. Độ trễ, timeout, caching và khả năng phục hồi

Với cấu hình introspection thông thường, mỗi request API cần xác thực Bearer token có thể kéo theo **một HTTP call tới Authorization Server**. Nếu client gửi nhiều request đồng thời, số cuộc gọi introspection có thể tăng nhanh và ảnh hưởng đến:

- **Latency** của API: thêm thời gian mạng, TLS, xử lý Authorization Server.
- **Availability**: API phụ thuộc vào trạng thái introspection endpoint.
- **Capacity**: Authorization Server cần đủ khả năng xử lý lưu lượng đến từ các Resource Server.
- **Cost**: có thể tăng tài nguyên mạng và hạ tầng IdP.
- **Revocation freshness**: token bị thu hồi có thể được phát hiện sớm nếu introspection không cache và AS cập nhật trạng thái kịp thời.

### 12.1. Cấu hình timeout và giới hạn retry

Một HTTP client introspection tùy chỉnh cần đặt **connect timeout**, **response/read timeout** và chính sách retry hữu hạn. Không cho request treo vô hạn vì AS không phản hồi. Nếu retry tất cả lỗi không giới hạn, lúc IdP bị sự cố hệ thống có thể tạo **retry storm**, làm tình trạng tệ hơn.

Lưu ý các property `introspection-uri`, `client-id` và `client-secret` chỉ nói **gọi đâu và xác thực bằng gì**. Chúng không trình bày đầy đủ giới hạn timeout, pool kết nối, proxy, retry hoặc chiến lược circuit breaker. Các lựa chọn này phụ thuộc phiên bản/framework và cách cấu hình underlying HTTP client/introspector của ứng dụng.

### 12.2. Có nên cache kết quả introspection?

Caching có thể giảm latency và chi phí, nhưng làm chậm việc nhận biết token bị thu hồi. Một thiết kế cache phải quyết định rõ:

| Nội dung | Cần cân nhắc |
|---|---|
| Cache key | Đại diện token một cách an toàn, tránh log hoặc phát tán token gốc |
| TTL | Không vượt quá `exp` còn lại; cân bằng độ trễ revocation theo chính sách |
| Token inactive | Có cache negative response không, thời gian bao lâu |
| Thay đổi quyền/tenant | Metadata có bị stale khi scope hoặc trạng thái người dùng thay đổi không |
| Dữ liệu trong cache | Token, principal và metadata đều nhạy cảm; cần kiểm soát quyền đọc và bảo vệ |
| Multi-issuer/resource | Không dùng chung kết quả khi policy/nguồn introspection khác nhau |
| Cache outage | Khi cache hoặc AS không sẵn sàng, không tự coi token active |

**Không mặc định rằng Spring Security sẽ cache introspection response theo thời gian tùy ý.** Nếu có cache, nó là quyết định triển khai cần được ghi rõ trong hợp đồng vận hành; đặc biệt không cache `active=true` vượt quá thời hạn token hoặc mức cho phép về revocation.

### 12.3. Quan sát hệ thống mà không rò rỉ token

Các chỉ số vận hành hữu ích:

- Số introspection request theo thời gian và phân loại kết quả active/inactive/error.
- Latency p50/p95/p99 của introspection endpoint và timeout rate.
- Tỷ lệ lỗi xác thực introspection client (401/403 upstream).
- Lỗi DNS/TLS/network riêng với lỗi token không active.
- Số request API 401/403 được phân loại nguyên nhân ở mức **không chứa credential**.
- Số lần secret rotation, thay đổi endpoint và cấu hình policy.

Để liên kết log, sử dụng request ID/trace ID hợp lệ và metadata ít nhạy cảm. **Không log raw access token, refresh token, Basic header hoặc client secret**. Ngay cả hash của token cũng cần chính sách truy cập và mục đích rõ; tránh biến nó thành định danh theo dõi người dùng ngoài ý muốn.

## 13. Kiểm thử cấu hình và hợp đồng introspection

Một bài kiểm tra Resource Server đầy đủ nên có các trường hợp sau:

| Tình huống | Phản hồi introspection / dữ liệu | Kỳ vọng tại API |
|---|---|---|
| Token hợp lệ, scope đủ | `active=true`, `scope="orders.read"` | Được đi vào nghiệp vụ GET |
| Token không tồn tại | `active=false` | `401`, không gọi controller được bảo vệ |
| Token hết hạn / đã thu hồi | AS trả inactive theo policy | `401` |
| Token active, thiếu scope | `active=true`, chỉ có `orders.create` | `403` khi GET đòi `orders.read` |
| Token active, không có audience API | `aud` thiếu hoặc là `billing-api` | Từ chối nếu policy yêu cầu audience |
| Token active, sai tenant | Claim/metadata tenant không khớp tài nguyên | Từ chối theo policy nghiệp vụ |
| Introspection credential sai | AS trả `401/403` | Request API không được chấp nhận; báo lỗi vận hành |
| Introspection endpoint không phản hồi | Timeout/DNS/TLS | Fail closed về quyền truy cập, có cảnh báo |
| Introspection response sai JSON | Parse error | Không tạo principal hợp lệ |
| AS trả `active=false` qua HTTP 200 | HTTP transport thành công nhưng token không active | Vẫn phải từ chối xác thực |
| Request không mang Bearer token | Không cần gọi AS | API bảo vệ trả `401` |
| Request public không mang token | Không cần introspection theo policy | Đi qua endpoint `permitAll` nếu được cấu hình |

### 13.1. Test rule phân quyền bằng Spring Security Test

Với Spring MVC, thư viện `spring-security-test` có request post processor `opaqueToken()` để giả lập một principal đã xác thực. Ví dụ minh họa:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Bên trong test đã cấu hình MockMvc và mapping GET /api/orders/42:
mockMvc.perform(get("/api/orders/42")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

Để dùng đoạn này cần import `org.springframework.security.core.authority.SimpleGrantedAuthority` và setup test controller/context phù hợp. Test với mock token giúp kiểm tra **rule URL/scope**, nhưng **không chứng minh Resource Server đã gọi đúng introspection endpoint hoặc dùng đúng credentials**: request post processor có thể mô phỏng trạng thái xác thực mà không gọi endpoint thật.

Muốn kiểm tra tích hợp introspection, hãy dùng một HTTP stub/server thử nghiệm cho endpoint AS, kiểm tra request `POST` với form field `token` và cách xác thực introspection client, sau đó trả các JSON `active=true/false` và lỗi upstream. Với WebFlux, dùng `WebTestClient` và hỗ trợ security test tương ứng; phân biệt test logic phân quyền với test tương tác HTTP thật.

### 13.2. Trường hợp không nên chỉ test bằng token thật

Một vài access token thủ công không đủ chứng minh:

- Introspection credentials được tự động đọc đúng ở mọi môi trường.
- Policy xử lý `aud`, issuer, scope thiếu và tenant mismatch đúng.
- Kết nối không bị treo khi IdP downtime.
- Không có credential xuất hiện trong log hoặc response lỗi.
- Caching, TTL và secret rotation hoạt động như hợp đồng.

Cần có **test case âm (negative cases)** và test lỗi upstream ngoài happy path để tránh tạo API chỉ hoạt động khi cấu hình IdP hoàn toàn lý tưởng.

## 14. Chẩn đoán khi Spring Boot không xác thực được opaque token

| Triệu chứng | Kiểm tra đầu tiên | Gợi ý xử lý |
|---|---|---|
| Mọi request trả `401` | Client có gửi `Authorization: Bearer` không? | Kiểm tra HTTP request thực, không dùng URL query thay thế |
| API không gọi introspection dù đã cấu hình property | Security chain có bật `opaqueToken()` và đúng runtime không? | Kiểm tra Servlet vs WebFlux, bean security, request matcher |
| Introspection trả `401` với tất cả token | Client ID/secret có đúng và còn hiệu lực không? | Kiểm tra quyền introspection, auth method và secret manager |
| Introspection endpoint trả `404` | `introspection-uri` có phải đường dẫn chính thức không? | Đối chiếu metadata/tài liệu nhà cung cấp |
| Token active nhưng API trả `403` | `scope` có được trả và ánh xạ thành `SCOPE_*` không? | Kiểm tra rule và metadata scope |
| Token ở API khác cũng qua xác thực | Có kiểm tra audience/resource binding chưa? | Bổ sung policy/validator của Resource Server |
| Cùng token lúc được lúc không | Network, AS cluster, revocation/caching, clock/TTL | Kiểm tra quan sát phân tán và policy nhất quán |
| WebFlux chậm, event loop bị nghẽn | Introspector tùy chỉnh có dùng HTTP client blocking không? | Dùng reactive I/O, đặt timeout đúng |
| API hoạt động local nhưng lỗi production | Secret/URI/TLS trust/proxy khác giữa môi trường | Kiểm tra cấu hình triển khai và kết nối bảo mật |
| Browser báo CORS trước khi GET tới API | Preflight OPTIONS bị chặn | Cấu hình CORS trước security phù hợp; preflight thường không có Bearer |
| Đổi secret xong mọi request fail | API còn sử dụng secret cũ | Đồng bộ secret rollout/restart/reload theo thiết kế |

### 14.1. `401` từ API khác `401` từ introspection endpoint

Đây là nhầm lẫn phổ biến:

~~~text
Client --(Bearer token)--> Orders API
   <-- 401 Unauthorized    |    token thiếu / không hợp lệ

Orders API --(client-id + secret, POST token)--> AS Introspection
   <-- 401 Unauthorized                          |    introspection caller sai quyền
~~~

Ở nhánh thứ hai, client end-user không thể sửa lỗi bằng cách thay access token liên tục nếu Resource Server đã mất quyền introspection. Lỗi cần được xử lý ở **cấu hình API/Authorization Server**.

### 14.2. Browser CORS preflight

Request JavaScript cross-origin có header `Authorization` thường dẫn đến một **OPTIONS preflight** không mang Bearer token. Nếu Spring Security chặn preflight trước khi CORS được xử lý, trình duyệt có thể báo CORS error dù introspection URL và token hoàn toàn hợp lệ. Thiết lập origin, method, allowed headers và thứ tự tích hợp CORS đúng theo topology; không vô hiệu hóa xác thực API chỉ để làm preflight đi qua.

## 15. Các ràng buộc bảo mật quan trọng

Introspection làm Resource Server dựa vào Authorization Server để xác nhận credential. Vì vậy:

1. **Chỉ sử dụng HTTPS** cho introspection endpoint và Resource Server API.
2. **Chỉ tin endpoint được cấu hình/phê duyệt trước**. Không lấy URL introspection từ header/token không đáng tin của caller.
3. **Bảo vệ client secret** bằng secret manager hoặc biến môi trường có kiểm soát truy cập; không để trong source code.
4. **Giới hạn quyền introspection client** để AS chỉ trả thông tin cần thiết cho Resource Server.
5. **Kiểm tra scope, audience/resource và tenant** theo hợp đồng sau introspection; `active=true` chưa đủ cho mọi request.
6. **Không log token hay Basic Authorization header**. Chỉ ghi mã lỗi, request ID và metric được phép.
7. **Fail closed** khi chưa xác minh được token; hạ tầng AS lỗi không có nghĩa được tự động bỏ xác thực.
8. **Kiểm soát timeout, retry, rate limit và cache** để tránh làm cạn kết nối của API hoặc IdP.
9. **Phân biệt access token và ID token/refresh token**. API không dùng các token khác thay Bearer access token.
10. **Quản lý thay đổi hợp đồng** khi đổi introspection URI, client authentication method, secret, scope naming hoặc claim resource binding.

### Câu hỏi tự kiểm tra

**Câu 1.** Resource Server nhận opaque access token từ client qua header nào?

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

**Câu 2.** Resource Server gửi gì đến introspection endpoint trong cấu hình mặc định phổ biến?

HTTP `POST` form-urlencoded có tham số `token` và thông tin xác thực của **introspection client**, thường là Basic từ `client-id` và `client-secret`.

**Câu 3.** HTTP 200 từ introspection endpoint có đồng nghĩa token hợp lệ?

**Không.** Phải đọc `active`. Phản hồi `{"active":false}` thường vẫn dùng HTTP 200.

**Câu 4.** Vì sao token active nhưng API trả `403`?

Token được xác thực, nhưng principal thiếu scope/authority hoặc không thỏa policy nghiệp vụ.

**Câu 5.** Có thể gán trực tiếp `spring.security.oauth2.resourceserver.opaquetoken.client-secret` bằng access token của người dùng không?

**Không.** Secret đó là credential riêng để Resource Server xác thực với introspection endpoint. Access token là credential của request nghiệp vụ.

**Câu 6.** Nếu introspection timeout, cho phép request đi tiếp để tránh gián đoạn được không?

**Không.** Chưa kiểm chứng token thì không tạo phiên xác thực thành công. Hệ thống cần từ chối request và xử lý lỗi hạ tầng phù hợp.

## 16. Ghi nhớ cấu hình

Cấu hình cơ bản gồm ba thông số:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Và một chỉ dẫn sử dụng opaque token:

~~~java
// Servlet / HttpSecurity:
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()))

// WebFlux / ServerHttpSecurity:
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()))
~~~

**Cả hai dòng Java đều là những đoạn DSL đặt trong builder tương ứng**, không phải câu lệnh Java đứng độc lập. Servlet và WebFlux dùng class security chain khác nhau, còn property kết nối introspection vẫn cùng cấu trúc.

Trong một request hoàn chỉnh, Spring Security nhận access token từ header `Authorization: Bearer ...`, gửi token đó đến introspection endpoint **đã tin cậy** kèm thông tin xác thực của Resource Server, chỉ chấp nhận kết quả active phù hợp, rồi kiểm tra scope và policy trước khi chuyển request cho nghiệp vụ. **Introspection endpoint/credentials**, **token active/metadata**, và **quyền truy cập API** là ba phần phải được cấu hình và vận hành đồng bộ.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Reactive Bearer Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Servlet CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
