# OAuth 2.0, OpenID Connect và vai trò resource server

## 1. Bài toán: có token chưa có nghĩa được xem mọi đơn hàng

Orders API có **GET /api/orders/{id}**. Server xác minh chữ ký JWT thành công nhưng cho phép đọc mọi order ID: đây là lỗi **broken object-level authorization** vì xác thực token khác quyền trên từng tài nguyên.

Sai lầm khác là gửi **ID token** thay **access token** đến API; cả hai có thể là JWT nhưng **khác đối tượng nhận và mục đích**.

Bài thuộc chương **Xác thực**, module **INTEGRATION_API_REST**, gắn với resource/URI, HTTP methods/status, dữ liệu, phân trang, cache, idempotency, OpenAPI, phân quyền, lỗi và Java/Spring. Trọng tâm là **OAuth 2.0, OIDC và nhiệm vụ resource server**.

**Mục tiêu:** nhận diện các vai trò/luồng OAuth, chọn đúng token, kiểm tra issuer/audience/thời gian/scope, triển khai Spring Security Resource Server, bảo vệ tenant/order, trả đúng 401/403 và kiểm thử cả token sai.

## 2. OAuth 2.0 và OIDC giải quyết vấn đề gì?

### 2.1. OAuth 2.0 là khung ủy quyền truy cập

OAuth 2.0 giúp **client** lấy **access token** để truy cập **protected resource** theo quyền AS cấp.

| Vai trò | Ví dụ Orders API | Trách nhiệm |
| --- | --- | --- |
| **Resource owner** | Người có quyền với tài nguyên, thường là người dùng | Có thể chấp thuận cấp quyền theo luồng/policy; không phải luồng nào cũng có người dùng. |
| **Client** | Web/mobile/backend tích hợp | Xin token và gửi access token đến API. |
| **Authorization Server (AS)** | Nhà cung cấp OAuth/OIDC tin cậy | Xác thực theo policy, cấp token, công bố metadata/JWKS hoặc introspection. |
| **Resource Server (RS)** | Orders REST API | Kiểm chứng access token và áp chính sách bảo vệ resource. |

**OAuth 2.0 không phải giao thức đăng nhập**; grant client credentials còn không có người dùng. Scope **không chứng minh sở hữu order**.

### 2.2. OIDC thêm lớp xác thực danh tính

**OIDC** bổ sung **ID token**, quy tắc xác minh iss/aud/sub/exp/nonce, UserInfo và discovery. **Relying Party** kiểm ID token **dành cho chính client** để quản lý đăng nhập.

Một sản phẩm có thể đồng thời:

1. Dùng OIDC để người dùng đăng nhập web/mobile.
2. Dùng **OAuth 2.0 access token** khi web/mobile gọi Orders API.
3. Dùng **domain authorization** ở Orders API để quyết định người dùng này có được xem đơn yêu cầu không.

**Đăng nhập không cấp quyền mọi API**; chữ ký hợp lệ không biến ID token thành access token.

### 2.3. Ranh giới giữa client, AS và RS

~~~mermaid
flowchart LR
    U["Người dùng"] --> C["Web/mobile client"]
    C -->|"Authorization Code + PKCE"| AS["OAuth/OIDC Authorization Server"]
    AS -->|"access token; có thể ID/refresh token"| C
    C -->|"Authorization: Bearer access token"| RS["Orders Resource Server"]
    RS -->|"JWT/JWKS hoặc introspection"| AS
    RS --> P["Scope + tenant/object authorization"]
    P --> DB[("Orders DB")]
    DB --> RS
    RS -->|"200/201/401/403/404"| C
~~~

**JWT** có thể xác minh cục bộ bằng JWKS cache; **opaque** thường cần introspection với AS.

## 3. Access token, ID token và refresh token không thể hoán đổi

| Loại | Mục đích | Đích sử dụng | Sai lầm thường gặp |
| --- | --- | --- | --- |
| **Access token** | Cho phép client gọi protected resource. | RS có audience/policy thích hợp. | Dùng để mặc định xác nhận đăng nhập OIDC. |
| **ID token** | Xác nhận sự kiện xác thực người dùng cho OIDC client. | Client/Relying Party kiểm tra aud/nonce/claims. | Dùng làm Bearer token của Orders API. |
| **Refresh token** | Xin access token mới. | Token endpoint của AS. | Gửi tới Orders API hoặc ghi vào logs. |
| **Authorization code** | Giá trị ngắn hạn, dùng một lần để đổi token. | Token endpoint với client/PKCE verifier. | Coi là access token hoặc tái sử dụng. |

**JWT là định dạng, không đồng nghĩa access token**: access token có thể JWT hoặc opaque.

### 3.1. Audience chặn token substitution

ID token có **aud=shopping-web** không dùng được tại API đòi **aud=orders-api**. Chỉ kiểm chữ ký/issuer tạo nguy cơ **token substitution**.

### 3.2. Claims có ngữ cảnh, không phải quyền tuyệt đối

Payload JWT minh họa sau **đã giải mã**; nó không phải token có chữ ký hợp lệ:

~~~json
{
  "iss": "https://id.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1810000000,
  "iat": 1809996400,
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a",
  "client_id": "shopping-web"
}
~~~

Scope/scp/roles/tenant tùy hợp đồng claim với issuer; không tin claim từ nguồn lạ. Trong **client credentials**, chủ thể có thể là service.

## 4. Authorization Code + PKCE cho đăng nhập người dùng

~~~mermaid
sequenceDiagram
    participant U as Browser/User
    participant C as Client
    participant AS as OAuth/OIDC AS
    participant API as Orders RS
    U->>C: Đăng nhập
    C->>C: Sinh state và PKCE verifier/challenge
    C->>AS: Redirect /authorize với state + challenge
    AS->>U: Xác thực và consent/policy
    AS-->>C: Redirect với code + state
    C->>C: Kiểm tra state
    C->>AS: POST /token: code + code_verifier
    AS-->>C: Access token, có thể ID/refresh token
    C->>API: GET /orders với Bearer access token
    API-->>C: Response theo token, scope, quyền order
~~~

### 4.1. Chốt các tham số phòng vệ

- **redirect_uri** được đăng ký và so khớp nghiêm ngặt với AS, tránh open redirect/wildcard tùy ý.
- **state** khó đoán, liên kết transaction đăng nhập, phải so khớp ở callback.
- **PKCE code_verifier/code_challenge (S256)** ràng buộc authorization code với client khởi tạo; thiết yếu cho public client, khuyến nghị rộng cho authorization code flow.
- **nonce** trong OIDC khi phù hợp ràng buộc ID token với sự kiện xác thực; **nonce không thay state**.
- **Confidential client** phải xác thực với token endpoint bằng phương thức chấp thuận; mobile/public client không thể giữ secret nhúng an toàn.

### 4.2. Ví dụ yêu cầu authorization code

~~~http
GET /authorize?response_type=code&client_id=shopping-web&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&scope=openid%20profile%20orders.read&state=random-state&code_challenge=DERIVED_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: id.example.com
~~~

**state** phải khó đoán, **code_challenge** được tính từ verifier; AS phải cấp đúng scope/audience.

### 4.3. Đổi code ở token endpoint

~~~http
POST /token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=one-time-code&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&client_id=shopping-web&code_verifier=SECRET_VERIFIER
~~~

Đây là public client; confidential client phải xác thực theo AS. **Không log code/verifier/secret/token**. Cân nhắc XSS, CSRF, BFF và cách lưu token; tránh mặc định lưu refresh token ở localStorage.

## 5. Client Credentials, refresh và những luồng cần tránh

### 5.1. Backend-to-backend không có người dùng cuối

Một service báo cáo chạy định kỳ có thể gọi token endpoint với **client credentials**:

~~~http
POST /token HTTP/1.1
Host: id.example.com
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read
~~~

**Basic ở đây chỉ dùng để xác thực OAuth client với AS**, không phải token gửi Orders API. Base64 không phải mã hóa bảo mật, phải dùng HTTPS, secret vault và chính sách rotate credentials; AS có thể hỗ trợ private_key_jwt, mTLS hoặc phương thức khác. Sau khi nhận access token, client mới gọi API với **Bearer access token**.

Grant này **không có end-user login**. API phải ánh xạ service principal với tenant tin cậy, không tin X-Tenant-ID từ caller.

### 5.2. Refresh token thuộc token endpoint

Refresh token chỉ gửi **AS**, không gửi API. AS có thể rotate, revoke và phát hiện reuse; client xử lý **invalid_grant** có giới hạn, không refresh vô hạn.

### 5.3. Không chọn grant cũ cho ứng dụng mới

Tránh **implicit grant** (token qua front channel) và **password grant** (client giữ mật khẩu) cho tích hợp mới. Ưu tiên **Authorization Code + PKCE** hoặc grant thích hợp.

## 6. JWT và opaque access token: hai chiến lược kiểm chứng

| Khía cạnh | JWT access token | Opaque access token |
| --- | --- | --- |
| Biểu diễn | Token có header, payload, chữ ký theo định dạng JWT. | Chuỗi tham chiếu không có payload mà RS tự giải nghĩa. |
| Kiểm chứng | **Chữ ký + thuật toán + issuer/audience/thời hạn/claims**. | **Introspection** với AS hoặc cơ chế xác minh AS quy định. |
| Hiệu năng | Có thể xác minh cục bộ bằng JWKS/cache. | Thường phụ thuộc mạng/AS hoặc cache kết quả. |
| Thu hồi | JWT tự xác minh có thể còn hiệu lực đến exp nếu không kiểm tra bổ sung. | Introspection có thể trả active=false, nhưng cache làm trễ thu hồi. |
| Rủi ro | Nhận sai aud/iss/alg; lộ claims; key rotation sai. | Lộ introspection secret; AS downtime; cache stale. |

**JWT payload thường chỉ Base64URL encode, không mã hóa**: tránh PII/secrets, và không tin token chỉ vì có ba đoạn.

### 6.1. Kiểm tra JWT tại resource server

1. **Signature/algorithm:** xác minh chữ ký bằng khóa của issuer đã cấu hình, chỉ chấp nhận thuật toán cho phép; không nhận alg=none, algorithm confusion hoặc URL jku tùy ý từ token.
2. **Issuer (iss):** khớp AS được cấu hình trước; không tin một issuer bất kỳ do token tự khai báo.
3. **Audience (aud):** chứa audience **orders-api** theo hợp đồng; token dành cho shopping-web hoặc service khác phải bị từ chối.
4. **Lifetime:** kiểm tra exp, nbf và chính sách thời gian hợp lệ/clock skew nhỏ; không tự nới hạn vô hạn.
5. **Token type/profile:** nếu issuer dùng profile/claim phân biệt access token với ID token, phải kiểm tra đúng semantics, không chỉ chữ ký.
6. **Scopes:** chỉ công nhận authorities từ claim được AS thống nhất, ví dụ orders.read/orders.write.
7. **Domain authorization:** xác minh actor, tenant, quan hệ sở hữu và trạng thái resource thật **sau** khi token đã hợp lệ.

**Scope orders.read không chứng minh được đọc mọi order ID**.

### 6.2. JWKS, key rotation và fail closed

AS công bố **JWKS** với public keys/**kid**; RS cache/rotate bằng thư viện tin cậy. Không theo JWKS URL do token cung cấp (SSRF), phải có TLS/timeout và **fail closed** nếu không xác minh được.

### 6.3. Opaque token dùng introspection

~~~http
POST /introspect HTTP/1.1
Host: id.example.com
Authorization: Basic <rs-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=opaque-access-token
~~~

Phản hồi minh họa:

~~~json
{
  "active": true,
  "client_id": "shopping-web",
  "sub": "user-123",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "iss": "https://id.example.com/realms/shop",
  "exp": 1810000000
}
~~~

Thông tin này chỉ đáng tin khi đến từ **introspection endpoint được cấu hình** qua kênh bảo vệ, sau khi xác thực resource server. **active=true** chưa tự bảo đảm được xem mọi tài nguyên; RS còn kiểm aud/scope/tenant theo policy. AS không nhất thiết trả tất cả claims ở ví dụ. Introspection secret phải lưu ngoài mã nguồn; caching cần xét độ trễ thu hồi, **timeout** và **fail closed** khi không thể xác thực.

## 7. Access token trong giao thức HTTP: Bearer, 401 và 403

Khi gọi resource server, client gửi token qua **Authorization header**:

~~~http
GET /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json, application/problem+json
~~~

**Bearer** nghĩa là ai sở hữu token có thể sử dụng nó trong phạm vi token và policy; vì vậy chỉ truyền qua **HTTPS**, không đặt vào query string, URL, logs, tracing attributes hay lỗi trả về. Access token và refresh token có mức nhạy cảm khác nhau nhưng đều cần bảo vệ.

| Trường hợp | Response điển hình | Diễn giải |
| --- | --- | --- |
| Thiếu token trên protected route | **401 Unauthorized**, có Bearer challenge | Chưa có credential hợp lệ. |
| Token hết hạn/chữ ký sai/iss hoặc aud sai | **401**, có thể error=invalid_token | Không thể chấp nhận access token. |
| Access token hợp lệ nhưng thiếu scope | **403 Forbidden**, có thể error=insufficient_scope | Đã xác thực nhưng không đủ quyền thao tác. |
| Đủ scope nhưng order thuộc tenant khác | **403 hoặc 404** theo chính sách che tồn tại | Domain authorization từ chối. |
| Order hợp lệ và đủ quyền | **200 OK** với dữ liệu được phép | Cần cả token validation và object authorization. |

Ví dụ Bearer challenge theo RFC 6750:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Cache-Control: no-store
Content-Type: application/problem+json

{
  "type":"https://api.example.com/problems/unauthorized",
  "title":"Unauthorized",
  "status":401
}
~~~

Thiếu credential có thể chỉ cần **WWW-Authenticate: Bearer realm="orders"**, không nhất thiết khai báo error=invalid_token. Với thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders.write"
Cache-Control: no-store
~~~

**Không đổi mọi lỗi thành 401** để client refresh token liên tục. 403 thường cần thay quyền/consent/policy; nếu tổ chức chọn 404 để không lộ order tồn tại, phải dùng nhất quán ở domain service và kiểm thử không rò metadata.

### 7.1. OAuth không thay HTTPS, CORS hay CSRF

OAuth access token không mã hóa đường truyền: dùng TLS và kiểm hostname/certificate. **CORS** là chính sách truy cập cross-origin của browser, không phải cơ chế xác thực. **CSRF** phụ thuộc cách lưu/gửi credential: REST API chỉ nhận Bearer token ở Authorization header có bề mặt CSRF khác với ứng dụng dùng cookie/session tự gửi. Không tắt CSRF cho mọi ứng dụng chỉ vì có OAuth.

### 7.2. Giới hạn quyền và vòng đời token

Ưu tiên **least privilege**, audience hẹp, TTL ngắn phù hợp vận hành, bảo vệ refresh token, có phương án revoke/rotate và theo dõi hành vi bất thường. **JWT hợp lệ chưa đồng nghĩa chưa bị thu hồi**; nếu cần thu hồi gần như tức thời, thiết kế token lifetime, introspection/denylist hoặc cơ chế khác dựa trên rủi ro thực tế. Có thể cân nhắc **sender-constrained tokens** (mTLS/DPoP) để giảm tác động khi token bị đánh cắp, nhưng cần hỗ trợ đồng bộ từ AS, client và RS.

## 8. Spring Boot: resource server xác minh JWT

Ví dụ sử dụng **Spring Boot 3 / Spring Security 6 trên Servlet/Spring MVC**. Dependency cần có **spring-boot-starter-security**, **spring-boot-starter-oauth2-resource-server** (và hỗ trợ JWT/Jose) cùng starter web. Chọn **OAuth2 Resource Server**, không tự viết filter giải mã Base64 rồi tin claims.

### 8.1. Cấu hình issuer/JWKS đáng tin

Ví dụ application configuration (chỉ minh họa, **không tạo file cấu hình mới**):

~~~yaml
app:
  security:
    issuer: https://id.example.com/realms/shop
    jwk-set-uri: https://id.example.com/realms/shop/protocol/openid-connect/certs
~~~

Hai URL phải lấy từ **metadata AS tin cậy** của từng môi trường; JWKS path là ví dụ. Không đọc issuer/JWKS URL từ token rồi tự kết nối. Nếu không cần audience validator tùy chỉnh, Spring Boot hỗ trợ cấu hình **spring.security.oauth2.resourceserver.jwt.issuer-uri** để auto-configure decoder. Trong ví dụ này ta tạo decoder riêng để minh họa rõ bước **kiểm aud**.

### 8.2. SecurityFilterChain kiểm scope tại tầng HTTP

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {
    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(csrf -> csrf.disable())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/health").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .requestMatchers(HttpMethod.POST, "/api/orders")
                            .hasAuthority("SCOPE_orders.write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth -> oauth.jwt(
                        Customizer.withDefaults()))
                .build();
    }
}
~~~

**Giả định:** API chỉ nhận Bearer header, không dùng cookie/session, nên tắt CSRF cho API. **Không áp dụng csrf.disable() cho ứng dụng dùng cookie**. Spring Security chặn request trước controller.

Mặc định Spring Security có thể ánh xạ **scope/scp** hợp lệ thành authority tiền tố **SCOPE_**, nên **orders.read → SCOPE_orders.read**. Issuer có claim roles/permissions riêng cần **JwtAuthenticationConverter** theo hợp đồng; không tin role từ header/query do caller tự điền.

### 8.3. Decoder kiểm signature, issuer, hạn và audience

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtDecoderConfig {
    @Bean
    JwtDecoder jwtDecoder(Environment env) {
        String issuer = env.getRequiredProperty("app.security.issuer");
        String jwksUri =
                env.getRequiredProperty("app.security.jwk-set-uri");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains("orders-api")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Audience must include orders-api",
                                    null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard, audience));
        return decoder;
    }
}
~~~

**NimbusJwtDecoder** kiểm chữ ký; **JwtValidators.createDefaultWithIssuer** kiểm issuer/thời gian; validator riêng kiểm **aud=orders-api**. Nếu AS có token type/profile riêng, kiểm thêm; vận hành phải kiểm thuật toán, clock skew và JWKS rotation.

**Không “sửa” audience mismatch bằng cách bỏ kiểm aud**. AS phải cấp access token đúng audience cho API. Nhiều issuer cần cấu hình trust/audience/mapping riêng, không mặc định tin mọi issuer.

### 8.4. Quyền đối tượng vẫn thuộc domain service

~~~java
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

record OrderView(UUID id, String status, long totalMinorUnit) {}

interface OrderQueryService {
    OrderView findAuthorized(String subject, UUID orderId);
}

@RestController
@RequestMapping("/api/orders")
class OrdersController {
    private final OrderQueryService service;

    OrdersController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(
            @PathVariable UUID id, Authentication authentication) {
        return ResponseEntity.ok(
                service.findAuthorized(authentication.getName(), id));
    }
}
~~~

**findAuthorized** kiểm **order và tenant** thật; ánh xạ identity tin cậy vào actor/tenant nội bộ, không tin tenant do caller chọn. User và service principal có ngữ nghĩa khác nhau. **@RestControllerAdvice** có thể map exception domain thành 403/404 Problem Details.

## 9. Phương án khác: resource server cho opaque token

Nếu AS cấp **opaque token**, cấu hình introspection **thay** JWT decoder:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/realms/shop/introspect
          client-id: <client-id-from-secret-store>
          client-secret: <secret-from-vault>
~~~

Trong SecurityFilterChain, dùng cấu hình **opaqueToken**, thay cho **jwt**:

~~~java
.oauth2ResourceServer(oauth -> oauth.opaqueToken(
        Customizer.withDefaults()))
~~~

Đoạn trên **thay thế** jwt(...) ở phần 8; không dán cả hai rồi cho rằng server tự phân biệt từ hình dạng token. Spring sẽ introspect và tạo authenticated principal/authorities. **active=true** chỉ là điều kiện đầu; vẫn cần kiểm audience/scope/actor/tenant theo policy, có thể dùng **OpaqueTokenIntrospector** tùy chỉnh để kiểm claims. Secret phải lấy từ biến môi trường/vault trong triển khai thật, không để literal placeholder trong production, và không log token hay introspection response nhạy cảm.

JWT và opaque khác về thu hồi, độ trễ, mạng, privacy và vận hành. JWT không hoàn toàn độc lập với AS vì còn JWKS rotation; opaque không tự động thu hồi tức thời nếu cache kết quả introspection.

## 10. OpenAPI: công bố OAuth scope mà không trộn vai trò OIDC

OpenAPI 3.1 có thể mô tả **OAuth authorizationCode flow** và scope cần cho một endpoint:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/orders/{id}:
    get:
      operationId: getOrder
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string, format: uuid}
      security:
        - OrdersOAuth: [orders.read]
      responses:
        '200': {description: Đơn hàng được phép đọc}
        '401': {description: Access token không hợp lệ hoặc thiếu}
        '403': {description: Thiếu quyền}
        '404': {description: Không tìm thấy hoặc được che tồn tại}
components:
  securitySchemes:
    OrdersOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://id.example.com/authorize
          tokenUrl: https://id.example.com/token
          scopes:
            orders.read: Đọc đơn có quyền
            orders.write: Tạo đơn có quyền
~~~

Nếu có **client credentials** hoặc flow khác, mô tả flow tương ứng trong contract. Có thể dùng **type: http, scheme: bearer** khi chỉ cần diễn tả cách mang token mà không mô tả OAuth token acquisition/scopes. **OpenAPI không tự cấu hình backend security**; contract tests phải chứng minh đúng 401/403/tenant. AS/OIDC client lo login, code, refresh và ID token; RS chỉ xác minh **access token** cùng chính sách resource.

## 11. Kiểm thử: token hợp lệ về cú pháp vẫn có thể bị từ chối

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| A01 | Không gửi Authorization | **401** và Bearer challenge; không gọi service. |
| A02 | JWT chữ ký sai, alg sai, hết hạn/chưa hiệu lực | **401**, không chấp nhận claims. |
| A03 | JWT đúng chữ ký nhưng **iss/aud sai** hoặc là ID token dành cho client | **401**; chống token substitution. |
| A04 | Token hợp lệ nhưng thiếu **orders.read** | **403** theo policy. |
| A05 | Đúng scope, order thuộc tenant khác | **403/404**, không rò nội dung. |
| A06 | Đúng quyền, đúng order | **200** và dữ liệu đúng tenant. |
| A07 | Client credentials truy cập endpoint yêu cầu user | Bị từ chối theo policy, không giả client là người dùng. |
| A08 | JWKS rotate hoặc introspection active=false | Khóa mới hoạt động theo policy; token không hợp lệ bị từ chối. |
| A09 | AS/JWKS/introspection timeout | **Fail closed**, có quan sát lỗi và không tự chấp nhận token. |
| A10 | POST retry, refresh/revoke, bearer bị redirect | Không duplicate side effect, không chuyển token sang origin khác. |

### 11.1. MockMvc kiểm phạm vi HTTP với spring-security-test

Ví dụ cho ứng dụng Spring MVC có filter chain ở phần 8:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersSecurityIT {
    @Autowired MockMvc mvc;
    static final String ORDER_ID =
            "11111111-1111-4111-8111-111111111111";

    @Test
    void noTokenIs401() throws Exception {
        mvc.perform(get("/api/orders/{id}", ORDER_ID))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"));
    }

    @Test
    void wrongScopeIs403() throws Exception {
        mvc.perform(get("/api/orders/{id}", ORDER_ID)
                .with(jwt().authorities(new SimpleGrantedAuthority(
                        "SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Test này cần **spring-security-test**, Spring Security filters được áp dụng, và **OrderQueryService bean** (có thể fixture/mock) để context khởi động. Hai nhánh bị từ chối trước controller nên không phụ thuộc dữ liệu order. Trên một số dự án, cần thêm cấu hình JWT decoder test/issuer giả để tránh kết nối AS khi khởi động.

**Quan trọng:** request post-processor **jwt() tạo Authentication giả đã xác thực**, không kiểm chữ ký, exp, iss hoặc aud của token thật. Vì vậy A02/A03/A08 phải có **integration tests qua decoder thật** dùng AS/JWKS test đáng tin hoặc introspection stub. Bổ sung test **đúng scope + order tenant khác** với DB/service thực, không chỉ mock trả 200. Để xác minh 401/403 response body theo RFC 9457, cần cấu hình security exception handlers rồi test Content-Type và schema.

## 12. Những kiểm soát vận hành thường bị bỏ quên

- **JWKS/introspection:** allowlist issuer, TLS, timeout, rotation, metrics lỗi xác minh, không fail open; tránh log nguyên token hoặc introspection credentials.
- **Token lifetime:** chấp nhận clock skew nhỏ theo policy; bảo vệ refresh token, cân nhắc revocation/caching; không kéo dài exp bằng clock skew quá rộng.
- **Least privilege:** tách read/write/admin scopes và audience theo API, bảo vệ resource tại service; không dùng client role để thay quyền người dùng.
- **Browser/mobile:** Authorization Code + PKCE, redirect URI chính xác, state/nonce phù hợp; tránh gửi token qua URL, console và crash reports.
- **Bảo vệ dữ liệu:** HTTPS, rate limit, audit truy cập nhạy cảm, Cache-Control phù hợp với response riêng tư; CORS không thay authentication.
- **Multi-tenant:** lấy tenant từ claim/registry được kiểm chứng, đối chiếu dữ liệu thật; query parameter tenant không phải bằng chứng sở hữu.

## 13. Bài tập và checklist

**Tình huống:** web client đăng nhập bằng OIDC và nhận **ID token có aud=shopping-web**, cùng một access token có **aud=orders-api**, **scope=orders.read**. API còn cho một service batch dùng client credentials với scope orders.read. Một lập trình viên định chấp nhận cả ID token và access token nếu cùng issuer, đồng thời cho phép GET mọi đơn nếu có scope đọc.

**Yêu cầu:** (1) Token nào được gửi trong Authorization của Orders API và vì sao? (2) Vì sao ID token bị từ chối dù chữ ký đúng? (3) Nêu ít nhất năm kiểm tra resource server cần thực hiện. (4) Thiết kế phản hồi cho thiếu token, thiếu scope và đơn khác tenant. (5) Viết ba test phát hiện lỗ hổng trong đề xuất. (6) Với client credentials, làm thế nào gắn service với tenant mà không giả danh user?

**Hướng giải:** gửi **access token dành cho orders-api**; ID token dành cho web client, sai mục đích/audience. RS kiểm chữ ký/introspection, issuer, aud, hạn, token type nếu cần, scope và **tenant/object authorization**. Thiếu/sai token → 401 với Bearer challenge; thiếu scope → 403; order ngoài quyền → 403/404 theo policy. Test sai aud, đúng scope nhưng sai tenant, service principal gọi nhầm quyền user. Batch service ánh xạ client identity qua registry/contract tin cậy, không dựa vào header tenant do caller tự cung cấp.

**Checklist phát hành:**

- [ ] Phân biệt OAuth access token, OIDC ID token và refresh token; không hoán đổi.
- [ ] Chọn grant đúng: Authorization Code + PKCE cho user, Client Credentials cho service.
- [ ] Resource server kiểm **signature/active, iss, aud, exp/nbf, scope và token type** theo policy.
- [ ] Spring SecurityFilterChain chặn route phù hợp; domain service kiểm tenant/order.
- [ ] 401/403/404 và WWW-Authenticate đúng hợp đồng; không biến lỗi DB thành lỗi token.
- [ ] Secrets/refresh/access token không đi vào URL, log, client khác audience hoặc redirect lạ.
- [ ] Kiểm thử decoder/introspection thật bên cạnh MockMvc jwt(), plus key rotation/revocation/timeout.

**Kết luận:** **OAuth 2.0** cấp quyền truy cập qua access token, **OIDC** bổ sung xác thực đăng nhập qua ID token, còn **resource server** là nơi kiểm chứng access token và thực thi quyền đối với API thực tế. Một token có chữ ký hợp lệ chưa đủ: **issuer, audience, thời hạn, scope, subject và quyền từng tài nguyên** phải cùng đúng, có kiểm thử và giám sát vận hành.
