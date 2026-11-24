# Chặn request trước controller

Một ứng dụng Java Spring Boot cung cấp API `GET /api/orders/42`. Client gửi `Authorization: Bearer ...`. Nếu access token hết hạn, được phát từ issuer lạ, dành cho `payments-api` thay vì `orders-api` hoặc thiếu scope `orders:read`, hệ thống **phải từ chối trước khi controller chạy** — không cho handler đọc cơ sở dữ liệu, gọi service có side effect hoặc trả dữ liệu rồi mới phát hiện token không hợp lệ.

Đây là một trong những trách nhiệm cốt lõi của **OAuth 2.0 Resource Server (RS)**: xác thực credential, xác minh nguồn phát/đối tượng nhận/hiệu lực token, áp chính sách truy cập API và chỉ chuyển yêu cầu đủ điều kiện đến tầng xử lý nghiệp vụ. Trong Spring Security, việc này thường diễn ra ở **Servlet filter chain** trước `DispatcherServlet` và controller. Tuy vậy, **chặn ở filter không có nghĩa mọi authorization đều được giải quyết ở filter**: quyền trên *đúng một đơn hàng, tenant, chủ sở hữu bản ghi, trạng thái kinh doanh* thường phải được kiểm tiếp trong service/database sau khi đã nhận principal đáng tin.

Bài thuộc chương **Resource server** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Phạm vi module gồm mô hình tin cậy, vòng đời JWT/opaque token, access/refresh token, OAuth 2.0/OIDC, phát hành và kiểm claims, scope, audience, lưu trữ, thu hồi và chống token bị đánh cắp hoặc replay. Chủ đề trực tiếp của bài là **“Chặn request trước controller”**: hiểu rõ pipeline Spring Security, triển khai pre-controller authentication/route authorization, kiểm thử bypass/fail-closed và phân biệt phần nào cần kiểm tại business layer.

> **Nguyên tắc:** Không có access token hợp lệ hoặc không đáp ứng route policy thì **không gọi controller**. Nhưng access token hợp lệ chỉ là **điều kiện cần**, không tự chứng minh người gọi được xem `orderId=42` hay dữ liệu tenant khác. Token format (JWT, opaque, encrypted) không thay nguyên tắc này.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Vẽ luồng HTTP request từ reverse proxy tới `FilterChainProxy`, `SecurityFilterChain`, `DispatcherServlet`, controller và service.
2. Phân biệt **authentication** (token hợp lệ và principal tin cậy) với **authorization** (scope, audience, quyền route, quyền object).
3. Giải thích chức năng của `BearerTokenAuthenticationFilter`, `AuthenticationManager`, `JwtDecoder` / opaque introspector, `SecurityContextHolder`, `AuthorizationFilter` và exception translation trong Spring Security.
4. Thiết kế **deny-by-default** và biết khi nào `securityMatcher`/`requestMatchers` có thể làm lọt route không được bảo vệ.
5. Xác minh access JWT bằng chữ ký, issuer, audience, thời gian, loại token và thuật toán/key trust; không chấp nhận ID token/refresh token thay access token.
6. Sử dụng RFC 7662 introspection cho opaque token và hiểu `active=false`, caller authentication, cache/thu hồi và outage.
7. Trả đúng HTTP **401** khi authentication thất bại và **403** khi principal đã xác thực nhưng không được cấp quyền, theo RFC 6750/profile áp dụng.
8. Quyết định chính sách CORS, CSRF, `SessionCreationPolicy.STATELESS`, cookie và reverse proxy theo loại client.
9. Thêm kiểm tra method/business authorization cho tenant, record ownership và phân biệt service principal với end user.
10. Viết negative tests để chứng minh request bị chặn **trước controller**, không chỉ chứng minh response HTTP có mã lỗi.
11. Xử lý token replay, sender binding DPoP/mTLS, logging redaction, JWKS/introspection outage và incident telemetry.
12. Áp checklist bảo mật cho một API triển khai bằng Java/Spring Boot.

## 2. “Trước controller” chính xác là vị trí nào?

### 2.1. HTTP pipeline cho Servlet Spring MVC

~~~mermaid
flowchart LR
    U[Client] --> P[Ingress / Reverse Proxy]
    P --> SF[Servlet Filter Chain]
    SF --> SC[Spring Security FilterChainProxy]
    SC --> AUTHN[Bearer Token Authentication]
    AUTHN --> AUTHZ[Route Authorization]
    AUTHZ --> DS[DispatcherServlet]
    DS --> HM[Handler Mapping]
    HM --> CT[Controller]
    CT --> SV[Service + DB Policy]
    SV --> DB[(Database)]
    AUTHN -->|Invalid token| R401[401 Unauthorized]
    AUTHZ -->|Insufficient permission| R403[403 Forbidden]
~~~

Sơ đồ mô tả **đường chính**. Trên thực tế `FilterChainProxy` chứa nhiều security filters; `DispatcherServlet` thường chạy sau Servlet filters. Spring Security quyết định một request có tiếp tục chạy đến controller hay không. Các cơ chế khác như ingress/WAF/Servlet filters của ứng dụng có thể chặn sớm hơn; không mặc định reverse proxy tự verify access JWT nếu không được cấu hình và kiểm chứng.

### 2.2. Ba lớp kiểm tra không được nhập làm một

| Lớp | Câu hỏi | Ví dụ | Nơi thực hiện phổ biến |
|---|---|---|---|
| **Authentication** | Credential có hợp lệ, tin cậy, đúng purpose không? | Token sai chữ ký, hết hạn, AS lạ. | Bearer authentication provider/decoder/introspector. |
| **API/route authorization** | Principal có được gọi loại endpoint này không? | `orders:read` cho GET; `orders:write` cho POST. | `AuthorizationFilter` theo `requestMatchers`. |
| **Business/object authorization** | Principal có được làm việc trên **đối tượng cụ thể** không? | User Beta đọc order của tenant Anpha. | Service/method/database policies sau controller entry. |

Đừng cố chuyển toàn bộ BOLA/IDOR thành kiểm `scope` ở filter: scope `orders:read` chỉ cho phép **loại hành động**, không chứng minh owner của mọi order.

### 2.3. Điều kiện tối thiểu để controller không chạy

~~~text
if token is absent on protected route:
    reject before controller
else if token signature/introspection/issuer/audience/time is invalid:
    reject before controller
else if token is valid but route authority is missing:
    reject before controller
else:
    pass authenticated principal to controller/service
    then check tenant/object-level authorization
~~~

“Chặn sớm” còn là tối ưu chi phí: không mở transaction dữ liệu, không chạy business logic không cần thiết. Nhưng **không lấy hiệu năng làm lý do bỏ object authorization**.

### 2.4. Controller không phải điểm bắt đầu mọi side effect

Một Servlet filter khác, interceptor hay gateway hook có thể đã ghi log, thay header hoặc gây side effect **trước** controller. Vì vậy, phát biểu “controller không chạy” không có nghĩa “không hề có bất cứ tác động nào”. Thiết kế các filters phía trước để hạn chế side effects và **không gọi business services trên request chưa xác thực**.

## 3. Các thành phần Spring Security trong luồng request

### 3.1. Những lớp chính

| Thành phần | Vai trò | Điều không nên giả định |
|---|---|---|
| `DelegatingFilterProxy` | Cầu nối Servlet container filter với Spring bean security chain. | Tự kiểm JWT/scope. |
| `FilterChainProxy` | Chọn một `SecurityFilterChain` phù hợp request. | Tự áp mọi filter cho mọi route trong mọi chain. |
| `SecurityFilterChain` | Danh sách security filters của một nhóm requests. | Mọi request đều khớp chain đang cấu hình. |
| `BearerTokenAuthenticationFilter` | Tìm Bearer token theo resolver và tạo authentication attempt. | Tự biết token JWT hay opaque, scope/tenant business policy. |
| `AuthenticationManager` / provider | Điều phối xác thực Bearer credential. | Tự cấp object permission cho mọi tài nguyên. |
| `JwtAuthenticationProvider` / `JwtDecoder` | Verify JWT signature, claims validators, tạo principal/authorities. | Một chữ ký đúng tự bảo đảm `aud`/scope/tenant. |
| `OpaqueTokenAuthenticationProvider` / `OpaqueTokenIntrospector` | Hỏi AS introspection, lấy validated metadata theo profile. | HTTP 200 introspection tự nghĩa là `active=true`. |
| `SecurityContextHolder` | Giữ authenticated principal/context cho phần xử lý đang chạy. | Principal luôn là end user; có thể là service principal. |
| `AuthorizationFilter` | Quyết định route access theo request rules/`AuthorizationManager`. | Có thể thay object-level ACL khi chưa biết dữ liệu object. |
| `ExceptionTranslationFilter` / handlers | Chuyển authentication/authorization exceptions thành HTTP handling phù hợp. | Bắt mọi exception ứng dụng đều là invalid token. |

Tên/chi tiết thứ tự filters có thể thay đổi theo cấu hình và phiên bản Spring Security. Không nên tự lập bản filter-order cứng rồi dựa vào đó ở mọi dự án. Điều quan trọng là **authentication diễn ra trước khi protected handler được cho phép**, và authorization decision cần kiểm cho mọi request.

### 3.2. Hai đường xác thực Bearer phổ biến

~~~mermaid
flowchart TD
    R[Authorization: Bearer token] --> F[BearerTokenAuthenticationFilter]
    F --> D{Resource Server token profile}
    D -->|JWT access token| J[JwtDecoder]
    J --> V[Verify signature and claims]
    D -->|Opaque access token| I[Authenticated RFC 7662 Introspection]
    I --> A[Require active true, trusted metadata]
    V --> P[Authenticated principal]
    A --> P
    P --> AZ[Route Authorization Manager]
    AZ -->|Permit| C[Controller and service policies]
    AZ -->|Deny| E[403 or appropriate denial]
    F -->|Missing/invalid credential| U[401 or corresponding auth failure]
~~~

AS phát access token và quản lý grants; RS **không phát lại access token chỉ vì nhận Bearer credential**. RS cũng không cần private issuer signing key khi verify JWT dùng chữ ký bất đối xứng: nó dùng public verification key/JWKS đúng issuer.

### 3.3. Filter chọn theo path hay mọi route?

Với nhiều `SecurityFilterChain`, **chain đầu tiên khớp request** được dùng; các filters trong một chain không tự “cộng dồn” từ chain khác. Một chain chỉ có `securityMatcher("/api/**")` sẽ không bảo vệ `/admin/**` nếu không có chain khác phù hợp. Đây là lỗi phổ biến tạo cảm giác “đã bật security” nhưng route vẫn mở.

### 3.4. Chặn sớm và xử lý response

- Thiếu hoặc sai credential trên route protected → thường **401** theo Bearer challenge.
- Principal hợp lệ nhưng thiếu scope/route permission → thường **403**.
- Token đúng, route đúng nhưng order không thuộc user → **403 hoặc 404** theo API disclosure policy, quyết định trong service.
- AS introspection/JWKS dependency lỗi → **không mặc định cho qua**; phân biệt availability problem với credential invalid khi response/logging.

### 3.5. Async và SecurityContext

Spring Security quản lý `SecurityContext` theo request/thread strategy. Nếu controller/service chạy async, background executor hoặc reactive pipeline, **không tự đọc context bằng global static biến** và không tự copy token tới shared threads. Dùng cơ chế context propagation/framework đúng, rồi vẫn thực hiện authorization ở nơi có dữ liệu nghiệp vụ. Context leak giữa threads/requests có thể biến một request đúng thành principal sai ở request khác.

## 4. Những gì cần xác minh trước khi controller được phép chạy

### 4.1. Access token chứ không phải “chuỗi bất kỳ trông như JWT”

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <redacted-access-token>
~~~

Các dạng credential khác nhau:

| Thứ client gửi | RS có thể chấp nhận làm OAuth access token? | Vì sao |
|---|---|---|
| **Signed JWT access token** đúng issuer/audience/profile | Có, sau verify signature/claims. | Access token profile dành cho RS này. |
| **Opaque reference access token** | Có, nếu introspection/contract xác nhận active và đúng RS. | Token có state/metadata phía AS. |
| **JWE encrypted access token** | Chỉ theo profile RS hỗ trợ và validate đầy đủ. | Cần decryption key, issuer trust, claims/purpose. |
| **OIDC ID token** | **Không** dùng thay access token. | `aud`/purpose dành cho client xác thực user. |
| **Refresh token** | **Không** gửi tới RS. | Dùng tại AS token endpoint để xin access token mới. |
| **Authorization code** | **Không** dùng gọi API. | Chỉ đổi tại token endpoint theo client/PKCE binding. |
| **Client assertion JWT** | **Không** tự là API access token. | Dùng xác thực OAuth client theo profile. |
| **Access token của audience khác** | **Không**. | Cross-service token forwarding/token substitution. |

### 4.2. JWT kiểm chữ ký thôi chưa đủ

Với JWT access token, RS cần kiểm:

1. **Token purpose/type** đúng access-token profile, không nhận ID token.
2. **Trusted issuer (`iss`)** đúng AS được cấu hình.
3. **Trusted signature algorithm/key** theo allowlist/JWKS/`kid` đáng tin; không tin `alg=none` hoặc key URL untrusted.
4. **Audience (`aud`)** bao gồm identifier của resource này.
5. **Thời gian (`exp`, `nbf`, `iat` khi cần)** và clock skew hợp lý.
6. **Scope/authorities** đủ cho route.
7. **Client/subject/tenant semantics** phù hợp route (service vs user, token exchange khi dùng).
8. **Sender binding/revocation/state** nếu token profile và risk policy yêu cầu.
9. **Business object ownership** tại service/data layer sau route permission.

Một JWT có chữ ký chính xác nhưng `aud=payments-api` không được Orders RS nhận.

### 4.3. Opaque token cần AS introspection đã xác thực

Với opaque reference, token có thể chỉ là chuỗi CSPRNG ngẫu nhiên. RS không decode claims từ token string; nó gọi **RFC 7662 introspection** qua TLS với client/service credentials được AS cho phép. RS cần phân biệt:

~~~json
{"active": true, "iss": "https://login.example.com", "aud": ["orders-api"], "scope": "orders:read", "exp": 1893456000}
~~~

và:

~~~json
{"active": false}
~~~

**HTTP 200** từ introspection endpoint có thể đi kèm `active=false`. AS/RS profile phải xác định metadata bắt buộc; khi thiếu `aud` hoặc issuer/trust mà route cần, **fail closed**, không tự cho mặc định.

### 4.4. “Authentication completed” không đảm bảo tenant đúng

Nếu `sub=user-742`, `scope=orders:read` và `aud=orders-api` đều hợp lệ, request vẫn có thể truy cập `/api/orders/42` không thuộc user-742 nếu service chỉ lấy `orderId` và trả database row. Đây là **Broken Object Level Authorization (BOLA/IDOR)**, không phải lỗi JWT parser. Chặn authentication trước controller và object ACL ở service là **hai lớp bổ sung**.

## 5. HTTP Bearer behavior: không biến token thành input vô hại

### 5.1. Định dạng Bearer token

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer <redacted-token>
Accept: application/json
~~~

`Authorization` header phải được xử lý theo Bearer policy, giới hạn kích thước, tránh credential duplication/ambiguity. Không cho một request tự ý lựa chọn token từ query, cookie, body rồi vượt qua API policy chỉ vì `Authorization` thiếu.

### 5.2. Vì sao không nên nhận `access_token` trong query?

~~~text
GET /api/orders?access_token=<secret>
~~~

URL dễ rò vào browser history, reverse proxy logs, referrer, analytics, traces. RFC 6750 mô tả phương thức Bearer khác nhau nhưng **Authorization header** là đường phổ biến an toàn hơn để kiểm soát. Nên cấu hình/token resolver từ chối cách truyền không mong muốn, không “cứ tìm thấy token ở đâu thì dùng”.

### 5.3. Bearer token bị copy vẫn có thể replay

Token JWT, opaque hoặc JWE dùng như **Bearer** đều có thể bị người khác trình lại nếu credential string bị lấy và chưa hết hiệu lực. **Chữ ký JWT/JWE encryption không chứng minh sender là client gốc**. Cần TLS, tránh logs/storage leak, TTL, scope/audience, revocation và DPoP/mTLS khi threat model đòi hỏi.

### 5.4. Header spoof và trust boundaries

Không tạo `Authentication` từ HTTP `X-User-Id`/`X-Tenant-Id`/`X-Roles` do public caller khai nếu chưa có gateway-authenticated contract. Reverse proxy cũng phải strip/overwrite forwarded identity headers. Một attacker có thể gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
X-User-Id: admin
X-Tenant-Id: other-tenant
Authorization: Bearer <redacted-token>
~~~

Các headers này **không tự làm thay đổi `sub` hay tenant** đã được RS xác minh; service phải dùng trusted principal/context và kiểm lại object policy.

## 6. Spring Boot 3 / Spring Security 6: chặn route ngay trong filter chain

### 6.1. Những dependency cần cho Resource Server

Một ứng dụng Spring Boot MVC thường sử dụng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Đây là đoạn dependencies minh họa, không có version vì dự án phải quản lý theo **Spring Boot dependency management/BOM** phù hợp. Spring Security OAuth2 Resource Server JWT cần thư viện JOSE/JWT resolver/decoder được starter cung cấp theo version. Không tự viết filter decode JWT bằng Base64 thay cho component đã được kiểm định.

### 6.2. Cấu hình tối thiểu của JWT Resource Server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

`issuer-uri` phải là trusted issuer configured ở deployment, không lấy từ `iss` hoặc `jku` của token chưa verify. Spring Security có thể dùng issuer metadata discovery để tìm JWKS; **hãy kiểm tác động startup/availability khi AS metadata endpoint unreachable**. Cấu hình `jwk-set-uri` tin cậy riêng nếu cần tách startup discovery, và phải bảo đảm issuer validation vẫn được cấu hình.

Cấu hình issuer cơ bản **không đủ** để khẳng định audience `orders-api` đã được enforce theo yêu cầu riêng. Phải bổ sung audience validator/profile validation.

### 6.3. Chọn chain và deny-by-default

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().denyAll())
            .build();
    }
}
~~~

**Ràng buộc ví dụ:** `csrf.disable()` trong `apiChain` **chỉ hợp lý** nếu API thực sự stateless, xác thực **chỉ bằng Bearer header**, không chấp nhận cookie/session credentials cho state-changing endpoints. Nếu cùng API nhận cookie tự động gửi từ browser hoặc có BFF session, phải thiết kế **CSRF protection**, không sao chép cấu hình này máy móc. CORS được cấu hình riêng nếu browser cross-origin có nhu cầu.

### 6.4. Vì sao dùng hai chains?

`apiChain` chỉ chọn những request thuộc `/api/**`. `fallbackChain` sẽ xử lý routes còn lại, ví dụ `/admin/**` hoặc `/internal/**`, bằng deny-by-default trừ `/health`. Nếu **không có fallback chain**, một URL ngoài `/api/**` có thể không được bảo vệ như đội triển khai nghĩ. Chọn chain bằng `securityMatcher` và chọn rule bên trong bằng `requestMatchers` là **hai quyết định khác nhau**.

Đừng dùng:

~~~java
// RUI RO: only /api/** is protected by this chain.
// Other routes might have no security chain at all.
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
~~~

và sau đó tưởng mọi controller đều được bảo vệ. Route mới phải có coverage test; management/actuator/Swagger/internal endpoints có policy riêng.

### 6.5. Thứ tự matcher quan trọng

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders:read")
    .anyRequest().denyAll())
~~~

Các request rules được xét theo thứ tự trong chain. Một rule rộng `anyRequest().permitAll()` đặt trước rule nhạy cảm hoặc một securityMatcher thiếu route có thể tạo bypass. Với các API thay đổi liên tục, cách an toàn là **liệt kê rõ routes/permitted methods rồi denyAll phần còn lại**; có tests bảo đảm mỗi route mới được kiểm.

### 6.6. Tránh filter thủ công trong controller

~~~java
// KHONG NEN:
@GetMapping("/orders/{id}")
public OrderDto get(@PathVariable long id,
                    @RequestHeader("Authorization") String header) {
    String sub = unsafeDecodeJwtPayload(header);
    return ordersService.read(id, sub);
}
~~~

Giải mã Base64URL payload mà không verify signature/issuer/audience là lỗ hổng xác thực. Spring Security nên xây principal từ Bearer credential **trước controller**; controller chỉ nhận verified `Authentication`/`Jwt` qua framework và dùng service policy cho object.

## 7. JWT Resource Server: issuer, audience, expiry và thuật toán

### 7.1. Trusted public JWKS

Giả sử AS có issuer:

~~~text
https://login.example.com
~~~

và công bố public JWK Set tại URL được cấu hình tin cậy:

~~~text
https://login.example.com/oauth2/jwks
~~~

RS chỉ dùng public keys của đúng AS để verify asymmetric JWS. **Không cho token tự chọn JWKS host** từ `jku`, `x5u` hoặc URL claim chưa verify. `kid` là key selector **trong trusted key set**, không phải quyền truy cập vào một URL hoặc file tùy ý.

### 7.2. Validator kết hợp issuer và audience

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;

@Configuration
public class OrdersJwtValidation {

    private static final String ISSUER = "https://login.example.com";
    private static final String JWKS =
        "https://login.example.com/oauth2/jwks";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Access token audience is not this resource",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audience));

        return decoder;
    }
}
~~~

Đây là ví dụ xây **validator issuer/time và audience** rõ ràng trong Spring Security 6. Nó minh họa lựa chọn `RS256` theo issuer profile giả định, **không** có nghĩa mọi AS phải dùng RS256; `PS256`/`ES256` cũng có thể phù hợp nếu được đăng ký và thư viện hỗ trợ. **Không bật thuật toán tùy ý theo `alg` của token**. Nếu cấp JWT theo **RFC 9068**, kiểm thêm token `typ=at+jwt`/profile và các claims bắt buộc theo hợp đồng để tránh cross-JWT confusion.

### 7.3. Validator phải đi trước authorities converter

Quyền `SCOPE_orders:read` chỉ đáng tin **sau khi JWT được verify**. Không parse `scope` từ Base64URL JWT ở filter tự viết rồi xây authorities trước khi kiểm signature/issuer/audience. Bỏ hoặc override `JwtDecoder` bean có thể làm mất validators mong đợi; regression tests phải bắt sai audience/issuer/time và algorithm confusion.

### 7.4. Mapping scope thành Spring authorities

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtAuthorityMapping {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        scopes.setAuthoritiesClaimName("scope");
        scopes.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(scopes);
        return converter;
    }
}
~~~

Và khi cấu hình resource-server chain, gắn converter vào JWT DSL:

~~~java
.oauth2ResourceServer(oauth -> oauth
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(jwtAuthenticationConverter())))
~~~

Cấu hình này ánh xạ `scope` được trả theo JWT profile (thường space-separated string) thành `SCOPE_orders:read`. Nếu AS dùng claim `scp` dạng array hoặc scope names khác, phải cấu hình converter/validation đúng schema thật. Không tự biến mọi `roles` thành quyền Spring `ROLE_ADMIN` mà thiếu mapping/tenant policy có kiểm.

### 7.5. Chỉ chấp nhận loại token phù hợp

Một OIDC ID token cũng có `iss`, `sub`, `aud`, `exp` và chữ ký hợp lệ. RS phải phân biệt **purpose**: ID token thường có `aud` client ID, access token có audience của RS; nếu cùng client/resources có tên trùng hoặc issuer phát nhiều loại JWT, phải thêm token type/header/claim validation theo profile. **Audience validator là cần thiết nhưng không tự bảo đảm chống mọi token substitution**.

### 7.6. JWKS rotation và cache

AS có thể xoay signing key K1 sang K2. RS thường cache public JWKS để verify, không gọi AS cho mỗi request. Khi `kid` mới xuất hiện, có thể refresh JWKS theo library policy; không fetch arbitrary `jku`, không tạo unbounded refresh/DoS từ random `kid`, không chấp nhận token với key lạ chỉ vì AS tạm unreachable. Trong normal rotation, public K1 có thể cần giữ cho JWT cũ còn hạn; khi **private key K1 bị compromise**, emergency trust cutoff cần xử lý khác.

## 8. Opaque Resource Server: introspection thay local JWT verification

### 8.1. Cấu hình phổ biến

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: INJECT_FROM_SECRET_MANAGER
~~~

`client-secret` là placeholder. Production cần managed secrets, TLS, correct introspection client authentication và access restrictions. Không nhúng introspection credentials vào SPA/mobile clients; đây là quyền của RS/backend.

### 8.2. Luồng HTTP

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant RS as Orders RS Filter Chain
    participant AS as Authorization Server
    participant ST as Token Store
    participant CT as Orders Controller
    C->>RS: GET /api/orders/42 + Bearer opaque T
    RS->>AS: POST introspection T with RS auth via TLS
    AS->>ST: Check token/grant/revoked/expiry
    ST-->>AS: Current token metadata
    AS-->>RS: active true/false and authorized metadata
    alt inactive or wrong audience
        RS-->>C: Reject before controller
    else active and right audience and scope
        RS->>CT: Continue with trusted principal
        CT-->>C: Business response after ACL
    end
~~~

### 8.3. Request và response mẫu

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic <redacted-rs-credential>
Content-Type: application/x-www-form-urlencoded

token=<redacted-opaque-access-token>&token_type_hint=access_token
~~~

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-742",
  "client_id": "shop-bff",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "token_type": "Bearer",
  "exp": 1893456000
}
~~~

RFC 7662 metadata fields có thể tùy profile/AS. RS phải có hợp đồng về các trường bắt buộc; khi thiếu issuer/audience/expiry/purpose cần thiết, **không mặc định chấp nhận**. `token_type_hint` chỉ là hint, không chứng minh loại token.

### 8.4. Không nhầm HTTP success với `active=true`

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

Introspection xử lý request HTTP thành công nhưng token **không active**. Spring opaque introspector/provider phải reject token; không viết custom code `if(status == 200) authenticated = true`.

### 8.5. Caching và thu hồi

Opaque token có thể bị AS revoke trước expiry. Nếu RS cache response `active=true`, nó có thể nhận token đã revoke **đến hết bounded cache TTL**. Cần đo **revoke-to-deny SLA** qua caches/replicas. `active=false` nên bị chặn tại filter, còn object/tenant policy vẫn ở service. Đừng kéo dài positive cache quá `exp`, đừng dùng raw bearer string làm metric label.

### 8.6. Introspection service outage

Nếu AS trả 401/403 vì RS caller credentials sai hoặc trả 5xx/timeout, RS **không có bằng chứng mới token active**. Không fail open. Có thể trả HTTP 503 khi phụ thuộc không xác minh được theo API contract, khác với token rõ ràng inactive (401). Nếu policy cho phép sử dụng cached active metadata còn TTL, giới hạn bằng expiry, audience, scope, risk và consistency rules.

## 9. HTTP 401, 403 và cách từ chối an toàn

### 9.1. Hai nhóm lỗi cần tách

| Request | Kết quả điển hình | Lý do |
|---|---|---|
| Không có Bearer trên route protected. | **401 Unauthorized** + Bearer challenge. | Chưa có authenticated principal. |
| Bearer sai chữ ký/issuer/audience/`exp`. | **401** / `invalid_token`. | Credential không được chấp nhận. |
| Opaque `active=false`. | **401** / invalid token. | Credential không active. |
| Token hợp lệ nhưng thiếu `orders:read`. | **403 Forbidden** / `insufficient_scope`. | Đã xác thực nhưng không có route permission. |
| Token hợp lệ nhưng order khác tenant. | **403** hoặc **404** tùy API disclosure policy. | Object-level authorization deny. |
| AS introspection unreachable. | **503** hoặc response fail-closed theo contract. | Không có kết quả xác minh; không tự suy credential invalid. |
| Malformed/duplicate Authorization headers. | **400/401** theo Bearer resolver/profile. | Request không hợp lệ/ambiguous credential. |

### 9.2. `WWW-Authenticate` response samples

Thiếu token:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
~~~

Token invalid:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
~~~

Token hợp lệ nhưng không đủ scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders:read"
Cache-Control: no-store
~~~

Các ví dụ áp dụng hành vi RFC 6750/profile tương ứng; trong thực tế framework/gateway có thể định dạng response body khác. **Không ghi raw token, private user claims hoặc stacktrace trong HTTP error**; `error_description` nếu có cần ngắn, an toàn, không phân biệt chi tiết nhạy cảm.

### 9.3. Dùng entry point và access-denied handler phù hợp

Spring Security Resource Server cung cấp các handler như:

~~~java
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

// Example when explicitly customizing exception behavior:
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(
        new BearerTokenAuthenticationEntryPoint())
    .accessDeniedHandler(
        new BearerTokenAccessDeniedHandler()));
~~~

**Đoạn này minh họa code thêm vào HTTP security configuration**, không phải Java class đầy đủ để copy nguyên file. Trong resource-server DSL, framework đã thiết lập Bearer handlers theo cấu hình phổ biến; chỉ override nếu cần và test 401/403. Đừng cấu hình một custom entry point trả 200 khi thiếu authentication hoặc gộp mọi access-denied thành login HTML redirect trong JSON API.

### 9.4. Log đúng lỗi, đừng leak credential

~~~text
JWT_INVALID_SIGNATURE
JWT_WRONG_ISSUER
JWT_WRONG_AUDIENCE
JWT_EXPIRED
OPAQUE_TOKEN_INACTIVE
INTROSPECTION_DEPENDENCY_FAILURE
AUTHORITY_INSUFFICIENT_SCOPE
OBJECT_PERMISSION_DENIED
DPoP_PROOF_INVALID
~~~

Event categories có thể dùng ở logs/metrics có RBAC, **không phản chiếu toàn bộ lý do/claims ra public HTTP response**. Không log `Authorization` header, raw JWT, refresh token, client secret hoặc introspection form body. Token invalid có thể do user lỗi hoặc attacker probe; phân loại qua counts/context an toàn.

## 10. CORS, CSRF và sessions: “chặn sớm” đúng ngữ cảnh trình duyệt

### 10.1. CORS là browser access policy, không phải xác thực

Browser cross-origin request gửi preflight `OPTIONS` nếu cần. Preflight thường **không có Bearer token**, nên cấu hình CORS phải được xử lý trước khi Security authentication/authorization làm chặn sai:

~~~mermaid
flowchart LR
    B[Browser] -->|OPTIONS preflight| C[CORS policy]
    C -->|Allowed origin/method/headers| S[Actual request with Bearer header]
    C -->|Not allowed| X[Browser blocks cross-origin call]
    S --> A[Spring Bearer Authentication]
    A --> Z[Scope and route authorization]
    Z --> CT[Controller]
~~~

CORS không xác thực user: một script/API client ngoài browser có thể gửi request trực tiếp. **Không dùng Access-Control-Allow-Origin như là policy cấp quyền cho API**. API vẫn phải kiểm token, scope, audience và object ACL.

### 10.2. CORS configuration sample

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.cors.CorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type"));
    config.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Ví dụ dùng Bearer header, không dựa trên browser cookies. Gắn vào security chain bằng `.cors(Customizer.withDefaults())` nếu app cần CORS. Nếu BFF dùng cookie credentials thì CORS/CSRF policy khác, không bật `allowCredentials=true` với wildcard origins hay trộn session-cookie endpoints và stateless JWT endpoints tùy tiện.

### 10.3. Khi nào disable CSRF là sai?

CSRF xảy ra khi browser tự động gửi credential (ví dụ session cookie) tới endpoint gây side effect. Một pure stateless API **chỉ nhận Authorization Bearer header do JavaScript/client thêm chủ động** có thể disable CSRF filter theo threat model; nhưng:

- API nhận cookie session tự động → CSRF protection có thể cần.
- BFF với login session cookie → cần CSRF tokens/SameSite/origin checks phù hợp.
- Header-based Bearer API vẫn cần **XSS protection** vì script trong origin có thể lấy/dùng token.
- DPoP/mTLS và CORS cũng không tự loại bỏ CSRF mọi kiến trúc.
- Việc `SessionCreationPolicy.STATELESS` không bảo đảm ứng dụng **không có bất kỳ credential cookie nào** từ các middleware khác.

### 10.4. Session và principal khác access token

Spring Security `SecurityContext` có thể được lưu trong session tùy chain/framework. Với Bearer-only RS thường chọn stateless để request nào cũng được xác thực từ token và tránh nhầm session. Nhưng BFF/web login có thể sử dụng session cookie hợp lệ. Không cấu hình một security chain duy nhất với `csrf.disable()` và `STATELESS` cho toàn ứng dụng nếu có cả browser session và token APIs mà chưa tách scope rõ ràng.

### 10.5. Preflight bypass policy không được lấn sang protected requests

Một cấu hình permitAll cho `OPTIONS /api/**` có thể hợp lý để CORS preflight hoạt động, nhưng **không** được permitAll cho mọi method/route chỉ vì client gặp 401 khi OPTIONS. Dùng CORS handling đã cấu hình, test preflight với allowed/disallowed origins và kiểm actual GET/POST vẫn bắt buộc Bearer + scope.

## 11. Route matching: nơi dễ xuất hiện bypass ngoài ý muốn

### 11.1. `securityMatcher` và `requestMatchers` là hai cấp kiểm

~~~text
securityMatcher("/api/**")
    -> which SecurityFilterChain processes this HTTP request?

authorizeHttpRequests().requestMatchers(...)
    -> which authorization rule runs inside that chain?
~~~

Nếu app mới thêm `/v2/orders` hoặc `/internal/orders/export` mà security chain chỉ khớp `/api/**`, route mới có thể rơi vào chain khác hoặc không có policy phù hợp. **Review route coverage ở mỗi lần deploy**, không chỉ review `JwtDecoder`.

### 11.2. Một chain match-all đặt trước có thể nuốt chain an toàn

~~~text
Order 1: securityMatcher("/**") -> permitAll
Order 2: securityMatcher("/api/**") -> require scope

Result: The second chain will never be selected.
~~~

Spring Security chọn chain đầu tiên match request; filters từ chain sau không tự cộng vào chain đã chọn. Nếu thực sự cần nhiều chains, dùng `@Order`, các matchers không phủ sai và một **fallback deny-by-default**.

### 11.3. Test coverage cho routes và HTTP methods

~~~text
GET    /health                  -> public only if intended
GET    /api/orders/42           -> SCOPE_orders:read
POST   /api/orders              -> SCOPE_orders:write
DELETE /api/orders/42           -> explicit strong policy or deny
GET    /api/admin/metrics       -> admin policy / deny
GET    /internal/reindex        -> deny unless explicitly authorized
GET    /actuator/health         -> distinct operational policy
GET    /swagger-ui/index.html   -> environment-dependent explicit policy
~~~

`anyRequest().permitAll()` hoặc `requestMatchers("/api/**").permitAll()` là nguy hiểm nếu đặt ở chain/rule không đúng. Route mới chưa được mapping nên bị **deny**, không được tự công khai. Kiểm `GET/HEAD/OPTIONS/POST/PUT/PATCH/DELETE` theo API contract.

### 11.4. Path normalization và proxy rewrites

Security matchers, Servlet container và Spring MVC có thể xử lý trailing slashes, encoded slash, double slash, semicolon path parameters, forwarded prefix khác nhau tùy stack. Một matcher test với `/api/orders/42` chưa đủ: cần thử variants trong test environment để chắc chắn **đường dẫn mà filter cho phép đúng với handler MVC sẽ chạy**. Tránh tự viết regex URL parsing không được test.

### 11.5. Error, forward và async dispatch

Servlet request có thể có các `DispatcherType` như REQUEST, ERROR, FORWARD, ASYNC. Filter registration và Spring Security có thể áp khác nhau theo dispatch. Nếu cần permit ERROR dispatch cho error renderer, giới hạn phạm vi theo hướng dẫn framework và bảo đảm internal forward không mở đường vào protected business handler. Async execution cần context propagation đúng, tránh principal context leak giữa requests.

### 11.6. Health check và monitoring không nên thành public admin API

`/health` chỉ nên tiết lộ thông tin tối thiểu cho liveness; readiness/deep-health/actuator/admin metrics cần network, authentication và permission policy theo deployment. Đừng để giải pháp “probe bị 401, permitAll toàn bộ `/actuator/**`” công khai secrets/configuration.

## 12. Method security: kết hợp route authorization với business policy

### 12.1. Route scope không chứng minh chủ sở hữu bản ghi

~~~text
GET /api/orders/{orderId}
  -> pre-controller: valid access token for orders-api
  -> pre-controller: has scope orders:read
  -> service: orderId belongs to this user/tenant?
  -> service: current business policy allows reading?
~~~

**Trước controller** là nơi lý tưởng để chặn authentication/scope/route violations. Nhưng object-level BOLA/IDOR thường cần query DB hoặc domain policy và phải được kiểm tiếp ở service/data boundary. Không viết một filter chứa tất cả business SQL chỉ để tuyên bố mọi quyết định đều “trước controller”.

### 12.2. Bật Method Security

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {}
~~~

### 12.3. Service vừa kiểm scope vừa lọc record

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public OrderDto readOwnedOrder(
            long id, VerifiedSubject subject) {
        return orders.findByIdAndTenantAndOwner(
                id, subject.tenantId(), subject.userId())
            .map(OrderDto::fromEntity)
            .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

`VerifiedSubject`, `OrderRepository`, `OrderDto` và `OrderNotFoundException` là types minh họa của domain, cần định nghĩa trong ứng dụng. `VerifiedSubject` phải đến từ trusted principal/introspection và current tenant permission, **không do client tự gửi**.

### 12.4. Database authorization predicate

~~~sql
SELECT id, tenant_id, owner_user_id, total_amount
FROM orders
WHERE id = :orderId
  AND tenant_id = :trustedTenantId
  AND owner_user_id = :trustedUserId;
~~~

Một query có predicate theo principal và object thường rõ hơn “load tất cả order rồi lỡ quên kiểm owner”. Với group sharing, admin/delegation, trạng thái giao dịch, policy phải mở rộng có kiểm. Không coi mọi user với `orders:read` đều đọc mọi đơn hàng.

### 12.5. Kiểm trước side effects

`@PostAuthorize` kiểm kết quả sau khi method đã chạy, có thể quá muộn nếu method đã transfer tiền, phát thông báo, commit dữ liệu hoặc publish event. Với writes nhạy cảm, kiểm permission **trước hành động** và bảo đảm transaction/race handling đúng. `@PreAuthorize` cũng không thay query/tenant policy nếu chỉ kiểm scope.

### 12.6. Method security có giới hạn kỹ thuật

Method security dựa trên Spring interceptor/AOP trong nhiều kiểu cấu hình; self-invocation (`this.method()`), non-proxied objects, background jobs, message consumers có thể **không đi qua interceptor như kỳ vọng**. Đặt business authorization tại use-case/service boundary rõ, test mọi entrypoint, và không dựa duy nhất vào HTTP `AuthorizationFilter`.

## 13. Multi-tenant và principal type: bảo vệ đúng ngữ nghĩa

### 13.1. Ví dụ BOLA dù JWT hợp lệ

~~~text
Verified token:
  iss=https://login.example.com
  sub=user-742
  aud=orders-api
  scope=orders:read
  tenant=tenant-beta

Request:
  GET /api/orders/9001

Actual record:
  orderId=9001
  tenant=tenant-anpha
  owner=user-999
~~~

Filter có thể xác thực token và cho GET route chạy, nhưng service phải **từ chối** order của tenant khác. Không gán tenant từ header `X-Tenant-Id` công khai; kiểm membership hiện tại theo business security policy.

### 13.2. Một `sub` không luôn là end-user

Token `client_credentials` đại diện service/client principal; không có nghĩa một người dùng đã đăng nhập và consent. Token exchange/delegation có `act`/`sub` semantics tùy profile. Đừng biến `Authentication.getName()` hoặc `client_id` thành user ID của mọi request. Endpoint user-only phải kiểm **principal type**, còn machine API phải có service role/scope riêng.

### 13.3. Token từ issuer khác không tự có cùng quyền

Hai AS có thể dùng tên scope `admin` nhưng quản lý clients/grants/tenants khác nhau. Scope-to-authority mapping cần gắn issuer/resource policy; không lấy chuỗi `role=admin` của issuer khác để nâng quyền trong Orders. Kiểm đúng `iss`, `aud`, token purpose, scopes và tenant mapping.

### 13.4. Token forwarding sai audience

Orders nhận access token `aud=orders-api` và gọi Payments. Nếu chuyển nguyên token đó cho Payments, Payments phải reject `aud` sai. Muốn delegation đúng, cân nhắc AS cấp access token audience `payments-api` hoặc **OAuth Token Exchange (RFC 8693)** theo registration/policy; không sửa JWT payload hoặc bypass validation.

### 13.5. Scope không phải quyết định kinh doanh cuối

`orders:refund` cho phép loại nghiệp vụ được ủy quyền, **không** mặc định cho refund mọi amount/order. Service còn kiểm order status, payment ownership, approval thresholds, segregation of duties và fraud policy. Route gate chỉ là lớp đầu của hệ thống authorization.

## 14. Sender-constrained access tokens: DPoP và mTLS

### 14.1. Bearer replay vẫn là nguy cơ

JWT được ký, opaque token `active=true` hoặc JWE được mã hóa đều có thể bị **phát lại nguyên chuỗi** nếu access token dùng như Bearer và bị copy. Một Bearer filter xác minh nguồn/token không chứng minh caller hiện tại là sender gốc.

### 14.2. DPoP theo RFC 9449

Với DPoP token profile, client thường gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: DPoP <redacted-access-token>
DPoP: <redacted-proof-jwt>
~~~

RS phải kiểm theo profile:

1. Access token đúng AS/issuer, audience, scope, time và token type.
2. Token confirmation binding, ví dụ `cnf.jkt`, đến từ trusted access token/introspection metadata.
3. DPoP proof JWT signature với holder public key.
4. `htm` và `htu` khớp request method/target URI.
5. `iat`/`jti`/nonce và replay window/cache theo yêu cầu.
6. `ath` ràng buộc proof với access token value.
7. Thumbprint holder public key khớp token confirmation binding.
8. Route/business authorization vẫn được kiểm sau khi sender proof hợp lệ.

**Spring Security `oauth2ResourceServer().jwt()` với Bearer mặc định không có nghĩa toàn bộ DPoP proof validation đã bật.** Nếu cần DPoP, triển khai thư viện/filter/gateway tuân RFC 9449 và test missing proof, wrong `ath`, replay, key mismatch, wrong method/URI. Không chỉ nhìn `cnf` rồi chấp nhận Bearer.

### 14.3. mTLS certificate-bound access tokens

Theo RFC 8705, AS có thể ràng buộc access token với client certificate thumbprint, ví dụ `cnf.x5t#S256`. RS/gateway phải có **TLS client certificate thật đã authenticated** và so thumbprint; không tin raw `X-Client-Cert` từ public client. Nếu TLS được terminate tại ingress, cần trusted authenticated propagation và kiểm đúng ranh giới trách nhiệm.

### 14.4. Sender binding không thay quyền nghiệp vụ

DPoP/mTLS chứng minh caller đang sở hữu credential khóa tương ứng, không tự chứng minh user được xem `orderId=42`. Nếu attacker chiếm cả token lẫn holder private key hoặc có quyền thực hiện signing trong compromised client origin, sender binding có thể không ngăn misuse. Vẫn bảo vệ token storage, TLS, TTL, scope/audience, grants và object ACL.

### 14.5. Proxy và URI normalization

Khi DPoP `htu` được xác minh ở backend sau reverse proxy, phải xác định external URI từ **trusted proxy configuration**, không từ untrusted `X-Forwarded-Host`. Test TLS termination, path rewriting, canonicalization và method/URI binding end-to-end.

## 15. Nhiều Authorization Servers và token substitution

### 15.1. Issuer allowlist thay token-directed discovery

Một RS có thể tin các issuers:

~~~text
https://employee-login.example.com
https://customers.example.com
https://service-login.example.com
~~~

Mỗi issuer có JWKS, algorithms, audiences, roles, scope semantics và client types riêng. Không fetch arbitrary `jku`/`x5u`/`iss` URL từ unverified JWT. Nếu cần nhiều issuer, dùng trusted issuer allowlist và per-issuer validation manager; Spring Security có cơ chế `JwtIssuerAuthenticationManagerResolver` phù hợp theo profile, nhưng phải kiểm input chỉ chọn **issuer đã tin**.

### 15.2. Cross-JWT confusion

Các JWT khác nhau có thể đều mang `iss`, `sub`, `aud`, `exp`:

~~~text
OAuth JWT access token
OIDC ID token
private_key_jwt client assertion
DPoP proof JWT
JWT-Secured Authorization Request
Internal service assertion
~~~

RS chỉ chấp nhận **access token** đúng purpose/typ/profile, trusted issuer/audience/signature và required claims. Không dùng OIDC ID token (aud thường là OAuth client ID) thay access token cho API; không dùng DPoP proof (ký bằng holder key) làm access token do AS ký.

### 15.3. Authority mapping theo issuer

Một issuer có `roles=["admin"]` và issuer khác có `scope="admin"` không có nghĩa cùng quyền `ROLE_ADMIN` trong Orders RS. Converter phải theo contract issuer/resource/tenant; không tự gán quyền hệ thống từ một claim signed bất kỳ mà thiếu mapping policy.

### 15.4. Service principal và delegated actor

Token từ `client_credentials` thường là service principal, không chứng minh end-user đã login. Token Exchange (RFC 8693) có thể mang subject/actor semantics theo profile; phải kiểm delegated audience/scope và hiện tại ai là authority. Endpoint user-only nên reject service-only token ngay ở route/policy boundary.

### 15.5. BFF session cookie khác Bearer RS

Một web client dùng OAuth login cookie session; API RS dùng access Bearer. Nếu chung Spring Boot, tách `SecurityFilterChain` theo route, CSRF/session/permissions rõ. Tránh để web login session vô tình bypass API Bearer-only rules.

## 16. Custom filter và lý do nên dùng Resource Server built-ins

### 16.1. Tự decode Base64URL không phải authenticate

~~~java
// SAI: extracting JWT payload without verifying signature.
String token = request.getHeader("Authorization").substring(7);
String payload = token.split("\\.")[1];
String json = new String(
    java.util.Base64.getUrlDecoder().decode(payload));
// Do not build Authentication authorities from this unverified data.
~~~

Code trên không verify JWS signature, `iss`, `aud`, `exp`, token purpose hoặc sender binding; cũng dễ lỗi với malformed headers. Dùng `BearerTokenAuthenticationFilter`, trusted `JwtDecoder`/`OpaqueTokenIntrospector` thay vì viết lại token parser.

### 16.2. `OncePerRequestFilter` chỉ làm việc phụ được xác định rõ

~~~java
// Sketch: add sanitized correlation, NOT a JWT validator.
public final class SafeCorrelationFilter
        extends org.springframework.web.filter.OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            jakarta.servlet.http.HttpServletRequest request,
            jakarta.servlet.http.HttpServletResponse response,
            jakarta.servlet.FilterChain chain)
            throws jakarta.servlet.ServletException, java.io.IOException {

        // Never log raw Authorization, Bearer, JWT or private claims.
        chain.doFilter(request, response);
    }
}
~~~

Custom filter cho DPoP/proxy proof cần review **filter order, dispatch types, error translation, fail-closed behavior, URI parsing, token resolver và negative tests**. Không tự cho request qua khi auth filter lỗi; không ghi request body/headers vào exception logs.

### 16.3. Side effects và non-HTTP entrypoints

Rate limit/request-size controls có thể nằm ở gateway/Servlet filter trước JWT crypto tốn tài nguyên. Nhưng authorization nghiệp vụ còn có thể được gọi từ scheduled jobs, message consumers, gRPC và internal Java methods **không đi qua HTTP filter**. Service/domain policy phải bảo vệ những entrypoints đó theo caller context, không phụ thuộc một MVC filter duy nhất.

### 16.4. Method proxy/self-invocation

Một service method gắn `@PreAuthorize` có thể bị gọi qua `this.method()` trong cùng class, không đi qua Spring AOP proxy tùy cấu hình. Test method security thật và đặt checks đúng architectural boundary; không lấy việc test controller 401 làm bằng chứng mọi service call đều được authorized.

## 17. JWKS/introspection outage: phải fail closed đúng cách

### 17.1. JWT có thể verify local nhưng vẫn phụ thuộc key trust

Resource Server JWT thường giữ trusted public JWKS trong cache. Khi Authorization Server tạm offline, RS có thể tiếp tục verify JWT bằng keys đã cache **nếu trust policy cho phép**. Nhưng khi xuất hiện `kid` mới, RS cần refresh JWKS và có thể thất bại nếu provider unreachable.

**Không:**

- Accept JWT với unknown `kid` chỉ vì JWKS service down.
- Bật `alg=none`, tắt signature/audience/issuer validation để chữa lỗi 401.
- Fetch `jku`/`x5u` URL bất kỳ do token đưa.
- Retry JWKS refresh không giới hạn từ random `kid` và gây DoS.
- Log raw JWT/ký tự secret khi decoder throw exception.
- Tự coi lỗi decoder do network là “token hợp lệ”.

### 17.2. Normal key rotation khác compromised key

~~~text
Normal:
  AS generates K2
  AS publishes public K2 in JWKS
  RS validates K2 in canary
  AS starts signing new JWT with K2
  AS stops signing with K1
  Keep public K1 as needed until existing authorized tokens expire
  Retire K1 safely

Compromise:
  Private K1 is leaked or signer misuse confirmed
  Emergency trust cutoff/reissue/revoke decisions
  RS must stop accepting attacker-forged K1 tokens per incident plan
~~~

Một token cũ ký K1 nhưng còn `exp` vẫn có thể hợp lệ trong normal rotation. Nếu private K1 bị lộ, không giữ nguyên trust K1 chỉ để bảo đảm availability. Log key lifecycle và xác minh RS/JWKS cache propagation.

### 17.3. Introspection outage với opaque access tokens

RS gọi AS/token store. Nếu AS trả timeout/5xx hoặc RS introspection client credentials sai, RS **không nhận được trusted active metadata mới**. Tùy API contract có thể trả 503 để phân biệt dependency outage; không nên gán mọi timeout thành 401 invalid_token và khiến clients refresh/login lại vô hạn.

Cache positive introspection có thể được dùng **trong bounded TTL** theo risk policy; phải tôn trọng `exp`, audience, scope, sender binding và revocation visibility SLA. Không đổi `active=false` thành `active=true` vì availability.

### 17.4. Revocation trước expiry

- **Opaque access token:** AS có thể revoke token/grant trong store; RS thấy khi introspection/caches cập nhật.
- **Signed JWT:** nếu chỉ verify local, token còn hạn vẫn có thể được chấp nhận sau revoke trừ khi có denylist/`jti` state, revocation events hoặc online check.
- **Refresh token:** được AS dùng ở token endpoint, có family/rotation/reuse detection riêng; RS không introspect nó như access token.
- **JWE access token:** mã hóa không tạo revocation tự động; vẫn cần state/policy nếu phải revoke sớm.

Chọn trade-off **availability vs revocation latency** theo SLA và đo end-to-end qua multi-region/cache/failover. Không nói “opaque revoke tức thì tuyệt đối” khi có RS caches.

### 17.5. Token store failover phải giữ revoked state

Một replica đọc stale state hoặc DB snapshot restore có thể khiến token revoked bị “hồi sinh” nếu không có consistency/DR controls. Với security-sensitive APIs, cần strong-enough reads/invalidations/monotonic revocation state, hoặc thiết kế bounded cache phù hợp. Đây là yêu cầu vận hành của **chặn request trước controller**, không chỉ bài toán database.

### 17.6. Rate limiting và backpressure

~~~text
JWKS:
  trusted key cache
  bounded refresh when unknown kid appears
  fixed AS/JWKS origin
  alarm on signature/unknown kid spikes

Introspection:
  authenticated RS caller, TLS
  bounded timeout/retry/jitter
  circuit breaker and bulkheads
  cache bounded by token expiration/risk
  alarm on AS failures and revocation lag
~~~

Không dùng fail-open. Cần metrics p95/p99 token validation, JWKS refresh error, introspection timeout, cache hit/miss và 401/403/503 rate.

## 18. Telemetry: chứng minh request đã bị chặn mà không rò credential

### 18.1. Event categories

~~~text
RESOURCE_AUTHN_MISSING_TOKEN
RESOURCE_AUTHN_INVALID_SIGNATURE
RESOURCE_AUTHN_WRONG_ISSUER
RESOURCE_AUTHN_WRONG_AUDIENCE
RESOURCE_AUTHN_EXPIRED
RESOURCE_AUTHN_WRONG_TOKEN_PURPOSE
RESOURCE_AUTHN_OPAQUE_INACTIVE
RESOURCE_AUTHN_INTROSPECTION_FAILURE
RESOURCE_AUTHZ_INSUFFICIENT_SCOPE
RESOURCE_AUTHZ_TENANT_DENIED
RESOURCE_AUTHZ_OBJECT_DENIED
RESOURCE_AUTHN_SENDER_BINDING_FAILED
RESOURCE_SECURITY_CHAIN_NOT_MATCHED
RESOURCE_JWKS_UNKNOWN_TRUSTED_KEY
~~~

Tên event là taxonomy minh họa; Spring không nhất thiết phát sẵn tất cả tên này. Log event sau trusted checks, không serialize raw token, exception HTTP request body hoặc introspection client secret.

### 18.2. Structured security event

~~~json
{
  "event_type": "resource.request.denied",
  "resource": "orders-api",
  "route_template": "/api/orders/{id}",
  "http_method": "GET",
  "trusted_issuer_ref": "company-login",
  "reason": "WRONG_AUDIENCE",
  "result": "DENIED_BEFORE_CONTROLLER",
  "correlation_ref": "req-internal-72",
  "timestamp": "2026-11-23T05:30:00Z"
}
~~~

`correlation_ref` được sinh/kiểm từ trusted infrastructure, không là raw bearer token. Tránh log đầy đủ `/api/orders/42?token=...`, user/tenant PII, `Authorization`, Cookie, `code_verifier`, refresh token, decrypted JWT/JWE plaintext hoặc raw token hash như metrics label.

### 18.3. Ví dụ metrics có cardinality thấp

~~~text
resource_authn_total{resource,reason,result}
resource_authz_total{resource,route_group,decision}
resource_bearer_verification_seconds{resource,token_profile}
resource_jwks_refresh_total{issuer_group,result}
resource_introspection_total{resource,result}
resource_introspection_latency_seconds{resource}
resource_introspection_cache_total{resource,result}
resource_sender_binding_failure_total{resource,proof_type}
resource_security_chain_mismatch_total{application}
resource_revocation_visibility_lag_seconds{resource}
~~~

Tránh `sub`, email, raw `kid` attacker khai, `jti`, token fingerprint, order ID hoặc tenant ID số lượng lớn làm metric labels. Nếu cần forensic correlation sâu, dùng restricted logs với refs/retention/approval, không biến Prometheus thành kho credential.

### 18.4. 401 và 403 tăng đột ngột nói lên điều gì?

| Hiện tượng | Giả thuyết cần phân biệt | Bằng chứng |
|---|---|---|
| `JWT_EXPIRED` tăng | Client refresh bug, clock drift, expired sessions. | AS issuance, clock, token TTL. |
| `WRONG_AUDIENCE` tăng | Token forwarding sai, gateway routing, attack. | API client, audiences/grants, deploy change. |
| `INVALID_SIGNATURE` tăng | Attacker probes, issuer key rotation bug. | Trusted JWKS, token alg, key lifecycle. |
| `OPAQUE_INACTIVE` tăng | User logout/revocation, random token probes. | AS active state, access patterns. |
| `INSUFFICIENT_SCOPE` tăng | Client scopes mismatch, privilege probing. | Client grants and API route policy. |
| `OBJECT_DENIED` tăng | BOLA attempts, role change, service bug. | Trusted subject/tenant/record refs. |
| `INTROSPECTION_TIMEOUT` tăng | AS outage, network, token-store saturation. | AS P99, pool saturation, circuit breaker. |
| `CHAIN_NOT_MATCHED` tăng | New route outside `/api/**`, proxy rewrite. | Route inventory and SecurityFilterChain mapping. |
| `DPoP_PROOF_INVALID` tăng | Replay attack or client clock/nonce bug. | Token binding and proof validation logs. |

Không tự gọi mọi 401 là tấn công; cũng không tự coi một spike từ deploy là an toàn. Kiểm nguồn và phiên bản triển khai trước khi điều chỉnh security policy.

### 18.5. Security testing telemetry

Trong integration test, gắn `controllerEntryCounter` hoặc spy để xác nhận **không có business entry** khi token invalid. Có thể ghi event `DENIED_BEFORE_CONTROLLER` chỉ khi test/handler thực sự kiểm điều kiện đó; không suy từ HTTP 401 nếu một controller tự trả 401 sau khi đã gọi service.

## 19. Threat model: các lỗi làm pre-controller gate không đáng tin

| Lỗi/tấn công | Vì sao nguy hiểm | Biện pháp |
|---|---|---|
| **Filter chain chỉ match `/api/**`** | Route `/internal/**`/`/v2/**` có thể không được chặn. | Fallback deny chain, route inventory, matcher tests. |
| **Chain permitAll đứng trước API chain** | Chain scope rules không chạy. | `@Order` đúng, integration requests. |
| **`anyRequest().permitAll()` quá rộng** | Mọi route mới được mở mặc định. | Deny-by-default. |
| **Tự Base64 decode JWT** | Unverified claims tạo authenticated principal. | Spring JwtDecoder/signature + claims validators. |
| **Thiếu issuer validation** | Token từ AS lạ có thể được nhận. | Trusted issuer/JWKS config. |
| **Thiếu audience validation** | Token Payments dùng tại Orders. | Per-resource `aud` validator. |
| **Nhận ID token làm access token** | OIDC client identity bị dùng sai purpose. | Token type/profile/issuer/audience checks. |
| **Nhận refresh token như access token** | Refresh credential bị gửi tới RS, nguy cơ lấy token mới. | Token purpose enforcement, AS-only refresh. |
| **Tin `scope` chưa verify** | Attacker sửa payload thành quyền admin. | Verify first, map authorities second. |
| **Authority mapping không theo issuer** | Roles của AS khác biến thành admin. | Per-issuer/profile mapping. |
| **Access token hết hạn nhưng được dùng** | Broken expiry validation/clock handling. | Validate `exp`/`nbf` and skew. |
| **`kid`/`jku` từ token điều khiển JWKS fetch** | SSRF/key confusion, arbitrary issuer trust. | Trusted JWKS, bounded key lookup. |
| **Opaque HTTP 200 coi là active** | `{"active":false}` được nhận. | Check `active=true` and metadata. |
| **Introspection client credentials lộ** | Unauthorized token metadata access. | Secret Manager, RS auth/AS authorization. |
| **AS timeout thì fail open** | Any token may pass if AS down. | Fail closed, bounded previously verified cache only. |
| **Positive cache sống quá `exp`** | Expired/revoked token tiếp tục được nhận. | TTL cap and revocation lag tests. |
| **Header `X-User-Id` tự khai** | Principal/tenant spoofing. | Authenticated token principal only. |
| **Không kiểm object ownership** | BOLA/IDOR dù token valid. | Tenant/object ACL service/DB. |
| **`client_credentials` thành user identity** | Machine identity vượt user-only routes. | Principal type/actor policy. |
| **Bỏ CSRF cho API dùng cookie** | Browser tự gửi session credentials. | CSRF/SameSite/origin checks for cookie endpoints. |
| **CORS wildcard là API authorization** | Hiểu sai browser policy, API bị lộ. | Independent token/route auth. |
| **Proxy forwarded headers untrusted** | Host/URI/tenant spoofing. | Trusted proxy config and strip input. |
| **DPoP-bound token không verify proof** | Attacker replay token string. | Validate `cnf`, `ath`, `htu`, `htm`, `jti`. |
| **mTLS bound token không verify cert** | Sender constraint bypass. | Authenticated TLS peer certificate binding. |
| **Custom filter nuốt AuthenticationException** | Fail-open hoặc response 200. | Framework exception handling and tests. |
| **Method-security self invocation** | AOP check có thể không chạy. | Architectural boundaries and tests. |
| **Controller trả 401 sau side effect** | Response trông như deny nhưng dữ liệu đã thay đổi. | Pre-controller gate, service auth before writes. |
| **Wrong JWT alg accepted** | Algorithm confusion/downgrade. | Fixed algorithm allowlist and key usage. |
| **Shared symmetric HS256 secret ở nhiều RS** | Mỗi verifier giữ khóa có thể tạo MAC. | Prefer asymmetric verification where appropriate; separate key custody. |
| **Token trong logs/traces** | Bearer credential replay/refresh family theft. | Structured allowlist and redaction. |
| **No fallback for management route** | Actuator/admin exposed. | Separate management security/network and deny defaults. |

### 19.1. Không có một control duy nhất đủ

Bật `oauth2ResourceServer().jwt()` là khởi đầu tốt, nhưng **wrong audience, scope mapping, BOLA, sender binding và route coverage** cần kiểm cụ thể. Filter pre-controller giảm attack surface sớm; service/domain authorization bảo vệ những gì filter chưa thể biết.

### 19.2. Không nhầm “403” với bằng chứng dữ liệu an toàn

Một API có thể gọi service sửa record rồi ném `AccessDeniedException`, cuối cùng trả 403. HTTP status đúng mà side effect đã xảy ra **vẫn là bug nghiêm trọng**. Dùng counters/spies, DB snapshots, audit/outbox để test no unauthorized side effects.

## 20. Case study: Orders Resource Server bảo vệ nhiều endpoint

### 20.1. Bài toán

Hệ thống có:

~~~text
Authorization Server: https://login.example.com

Shop BFF:
  confidential OAuth client "shop-bff"
  Authorization Code + PKCE
  access token audience "orders-api"

Orders Resource Server:
  GET  /api/orders/{id}       -> orders:read + record ACL
  POST /api/orders            -> orders:write + tenant policy
  POST /api/orders/{id}/refund-> orders:refund + payment policy

Payments Resource Server:
  audience "payments-api"
  separate scopes and object policy
~~~

Yêu cầu: **không để controller chạy khi Bearer invalid hoặc thiếu route scope**; trong controller/service vẫn phải kiểm owner/tenant trước khi thay đổi dữ liệu. BFF không dùng ID token cho Orders và không gửi refresh token cho RS.

### 20.2. Yêu cầu 1 — Không gửi access token

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Accept: application/json
~~~

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as Spring Security Filter Chain
    participant CT as OrdersController
    C->>F: GET /api/orders/42 without token
    F->>F: Protected route; no authenticated Bearer
    F-->>C: 401 Bearer challenge
    Note over CT: Not invoked
~~~

Expected: HTTP 401, không gọi controller/service. Nếu controller được gọi rồi tự trả 401, filter/route coverage **chưa đạt yêu cầu pre-controller gate**.

### 20.3. Yêu cầu 2 — Token chữ ký đúng nhưng sai audience

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": ["payments-api"],
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

Đây là payload ví dụ; signed JWT do AS phát (hoặc test fixture). Orders RS phải **reject ở JwtDecoder audience validator** dù signature, issuer và scope đúng. Không chuyển request tới controller. **Scope cùng tên không thể vượt audience boundary.**

### 20.4. Yêu cầu 3 — Token đúng audience nhưng thiếu scope

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": ["orders-api"],
  "scope": "profile:read",
  "exp": 1893456000
}
~~~

JWT có thể authenticate thành công, nhưng `GET /api/orders/42` yêu cầu `SCOPE_orders:read`. `AuthorizationFilter`/AuthorizationManager từ chối request với **403**. Controller không chạy. Không “cho qua để controller tự check profile role”.

### 20.5. Yêu cầu 4 — Token và scope đúng, order ngoài tenant

~~~text
Token:
  sub=user-742
  aud=orders-api
  scope=orders:read
  tenant=tenant-beta

Order 42:
  tenant=tenant-anpha
  owner=user-998
~~~

Filter cho request đi tiếp vì token/route hợp lệ. Controller gọi service; service query/ACL thấy tenant mismatch và trả deny (có thể 403/404 theo policy). **Đây không phải lỗi pre-controller gate**. Tính đúng của hệ thống phụ thuộc cả hai lớp. Nếu API trả dữ liệu order, đó là BOLA/IDOR dù security chain vẫn chạy chuẩn.

### 20.6. Yêu cầu 5 — Token bị đánh cắp nhưng vẫn `active=true`

Một access token Bearer bị lưu trong application log, attacker copy nó để gọi Orders. Với token chỉ có bearer semantics, filter có thể xác thực nó **như một credential còn hiệu lực**. Muốn giảm tác động cần log redaction, revoke/TTL, audience/scope, sender-bound proof và anomaly detection. Đừng hứa “đã có JwtDecoder nên không bị replay”.

### 20.7. Yêu cầu 6 — Introspection timeout

Orders dùng opaque token, AS introspection trả timeout. Không có positive cache hợp lệ. Filter **không được** giả `active=true` và gọi controller. Trả dependency error theo API contract, thường 503 cho outage, và alert telemetry. Nếu cache còn hợp lệ và được phép dùng, phải tôn trọng expiry/revocation-window policy; không biến cache thành indefinite session.

### 20.8. Yêu cầu 7 — URL không khớp chain

Một đội khác thêm `GET /v2/orders/42`, nhưng security chain chỉ match `/api/**`. Nếu không có fallback deny chain, endpoint có thể không đi qua OAuth RS authentication filter. Bởi vậy phải có **route inventory/coverage test** và deployment gate đảm bảo mọi protected handler thuộc chain đúng.

### 20.9. Ma trận quyết định theo từng lớp

| Request condition | Token verification | Route scope | Business ACL | Expected controller |
|---|---|---|---|---|
| No Bearer | Fail | Not reached | Not reached | **Not invoked** |
| Invalid signature | Fail | Not reached | Not reached | **Not invoked** |
| Wrong `iss` | Fail | Not reached | Not reached | **Not invoked** |
| Wrong `aud` | Fail | Not reached | Not reached | **Not invoked** |
| Expired token | Fail | Not reached | Not reached | **Not invoked** |
| Valid token, missing scope | Pass | Fail | Not reached | **Not invoked** |
| Valid token, correct scope, cross-tenant order | Pass | Pass | Fail | **Invoked; service denies** |
| Valid token, correct scope, owns order | Pass | Pass | Pass | **Invoked; allowed** |
| Opaque introspection outage | Unknown | Not reached | Not reached | **Not invoked** |
| DPoP-bound token, missing proof | Fail policy | Not reached | Not reached | **Not invoked** |

## 21. Ma trận negative tests: chứng minh chặn trước controller

### 21.1. Test fixtures

~~~text
Trusted issuer: https://login.test.example
JWKS: test RSA key K1 for RS256 only
Resource: orders-api
Other resource: payments-api
Client: shop-bff
User: user-test-742
Tenant: tenant-beta

Protected routes:
  GET  /api/orders/42
  POST /api/orders
  POST /api/orders/42/refund

Test JWT access tokens:
  T_good: iss trusted, aud orders-api, exp future,
          scope orders:read, subject user-test-742
  T_wrong_aud: valid signature, aud payments-api
  T_wrong_iss: valid test signature, iss another issuer
  T_expired: exp past
  T_bad_sig: payload changed after signature
  T_wrong_purpose: valid ID token for shop-bff
  T_no_scope: valid token, scope profile:read

Test opaque:
  O_active: AS returns active=true and authorized claims
  O_inactive: AS returns active=false
  O_timeout: AS unavailable
~~~

Dùng **test-only signing keys và dummy tokens**. Không đưa production private signing key, refresh tokens, client secret hoặc JWT thật vào test fixtures hay CI logs.

### 21.2. Authentication tests

| Test | Input | Expected HTTP/decision | Controller entry |
|---|---|---|---|
| Missing Authorization | Protected GET no header. | 401 Bearer challenge. | 0 |
| Wrong scheme | `Authorization: Basic ...` trên Bearer-only API. | 401/invalid credential. | 0 |
| Empty Bearer | Empty/malformed header. | 400/401 theo resolver/profile. | 0 |
| Duplicate credentials | Multiple ambiguous Authorization headers. | Reject, không chọn bừa token. | 0 |
| JWT bad signature | Altered signed payload. | 401 invalid token. | 0 |
| JWT wrong issuer | `iss` không trusted. | 401. | 0 |
| JWT wrong audience | `aud=payments-api`. | 401. | 0 |
| JWT expired | `exp` quá hạn. | 401. | 0 |
| JWT not yet valid | `nbf` tương lai. | 401. | 0 |
| JWT unknown key | `kid` lạ trong trusted issuer. | 401/controlled JWKS refresh. | 0 |
| JWT unsupported alg | `none`/HS256 khi chỉ RS256 được phép. | Reject. | 0 |
| JWT wrong type | OIDC ID token/client assertion. | Reject token purpose. | 0 |
| Opaque inactive | HTTP 200 `{"active":false}`. | 401. | 0 |
| Opaque wrong audience | Active true nhưng aud Payments. | 401. | 0 |
| Opaque RS auth failure | AS introspection caller 401/403. | Fail closed; infra auth error. | 0 |
| Opaque AS timeout | 5xx/timeout, no valid cache. | Fail closed; service error policy. | 0 |
| Refresh token as Bearer | AS-only refresh credential. | Reject. | 0 |

### 21.3. Route authorization tests

| Test | Input | Expected | Controller entry |
|---|---|---|---|
| Correct JWT/GET scope | `orders:read` for GET. | Route allowed; business ACL next. | 1 |
| Missing read scope | `profile:read` for GET Orders. | 403. | 0 |
| Read-only for POST | `orders:read` for create. | 403. | 0 |
| Read-only for DELETE | No DELETE rule/permission. | Deny default. | 0 |
| Unknown API path | `/api/admin/metrics`. | Deny default. | 0 |
| Route outside API matcher | `/internal/reindex`. | Fallback deny. | 0 |
| New v2 route without policy | `/v2/orders`. | Fallback deny until configured. | 0 |
| Public health | `GET /health`. | Allowed only if explicitly configured. | Health handler only |
| Actuator deep endpoint | `/actuator/env`. | Explicit management policy/deny. | 0 if denied |
| Other issuer admin scope | `roles=admin` from foreign issuer. | Reject or no mapped authority. | 0 |
| Client credentials at user endpoint | Service principal calls `/me`. | Reject principal type/route. | 0 |

### 21.4. Tenant/object authorization tests

| Test | Token/route | Expected |
|---|---|---|
| Own order | User Beta with `orders:read` → Beta owned order. | Allowed. |
| Same tenant, other user's private order | Valid scope, wrong owner. | Deny per object policy. |
| Cross-tenant order | User Beta → Anpha order. | Deny; no record leakage. |
| Tenant spoof header | `X-Tenant-Id: anpha` with Beta principal. | Header ignored/rejected as untrusted. |
| Unknown subject type | `client_credentials` token on user-only route. | Deny according to domain principal policy. |
| Refund above approval threshold | Valid `orders:refund` but no required approval. | Deny before side effect. |
| Refund after order cancelled | Valid scope, invalid business state. | Deny. |
| Method security self-invocation | Method called internally bypassing proxy path. | Architectural check/test catches missing authorization. |
| Direct message consumer call | Same service without HTTP filter. | Domain authorization still enforced. |

### 21.5. Sender constraints và proxy tests

| Test | Input | Expected |
|---|---|---|
| DPoP-bound token no proof | Token có `cnf.jkt`, no proof. | Reject. |
| DPoP wrong `ath` | Proof for different token. | Reject. |
| DPoP wrong method/URI | `htm`/`htu` mismatch. | Reject. |
| DPoP reused `jti` | Proof replay within window. | Reject. |
| DPoP proof key mismatch | Different holder key. | Reject. |
| mTLS bound cert mismatch | Certificate thumbprint khác. | Reject. |
| Proxy-supplied fake subject | Public `X-User-Id=admin`. | Ignore/reject, no elevation. |
| Forged `X-Forwarded-Host` | Claim external host attacker. | Cannot alter trusted URI/policy. |
| Mixed Authorization sources | Header token plus query token. | Reject ambiguity or consistently prohibit query. |
| CORS preflight | Allowed/disallowed origin OPTIONS. | Correct browser CORS semantics; no API data. |
| Cookie CSRF | Browser session POST without CSRF. | Reject if cookie-auth endpoint. |

### 21.6. Failure and resilience tests

| Test | Setup | Expected |
|---|---|---|
| JWKS endpoint down | Cached key K1 valid. | Existing JWT may verify under trusted cache policy. |
| JWKS endpoint down + unknown `kid` | No matching cached key. | Reject, not accept unsigned. |
| JWT alg downgrade | `alg=none` attempt. | Reject. |
| AS introspection down | Opaque no verified cache. | Fail closed, no controller. |
| Positive cache expired | AS still down. | Do not extend active state indefinitely. |
| Token revoked mid-cache | Policy TTL/event invalidation. | Meet measured revoke-to-deny SLA. |
| Token store replica stale | One region active after revoke. | Alert/consistency policy prevents excessive stale acceptance. |
| Flood unknown JWT `kid` | Many random headers. | Bounded JWKS refresh/rate limiting. |
| Flood random opaque tokens | High introspection QPS. | Rate limits/circuit breaker protect AS. |
| Route rewrite after proxy | `/api/orders` becomes internal path. | Security matcher/handler same semantic route. |
| Wrong fallback chain order | PermitAll chain before API. | Test catches unintended controller access. |

### 21.7. Không test mỗi HTTP status

Một controller có thể tự trả `401` sau khi đã gọi `ordersService.delete()`. Khi đó status test `isUnauthorized()` vẫn PASS nhưng bảo mật thất bại. Test cần đo:

~~~text
For invalid authentication / missing scope:
  HTTP response is denial
  controller entry counter is unchanged
  service/repository write methods were not called
  no domain event was published
  no DB mutation occurred
  no protected data leaked in response/logs

For valid auth + wrong object:
  controller may run
  service authorization denies
  no protected data or write side effects
~~~

Đó là bằng chứng mạnh hơn về yêu cầu **“chặn request trước controller”**.

## 22. Spring Security tests: MockMvc và integration JWT thật

### 22.1. Thêm `spring-security-test`

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Security có `SecurityMockMvcRequestPostProcessors.jwt()` để tạo **JWT authentication trong test** mà không cần gọi AS. Đây là công cụ tốt để test **route authorization**, nhưng phải hiểu giới hạn của nó.

### 22.2. MockMvc test route-level authorization

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersRouteAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void protectedRouteWithoutTokenIs401() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedButWrongScopeIs403() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_profile:read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Mẫu này giả định app có `GET /api/orders/{id}`, security chain `/api/**` đã cấu hình và mock data/service không tạo lỗi phụ. Nếu route không tồn tại hoặc app custom error handling khác, test cần điều chỉnh theo deployment. Với scope đúng, test còn cần mock service trả một order có quyền; tránh coi HTTP 200 từ mock là bằng chứng object ACL production đúng.

### 22.3. Cảnh báo cực kỳ quan trọng về `jwt()`

`jwt()` test postprocessor đưa `JwtAuthenticationToken`/principal đã tạo vào test security context. Nó **không thực sự kiểm chữ ký bằng production `JwtDecoder`**. Vì vậy:

~~~text
MockMvc + jwt() is useful for:
  403 vs scope/authority routing
  method authorization rules
  principal propagation

MockMvc + jwt() is NOT proof that:
  invalid signature is rejected by NimbusJwtDecoder
  issuer/audience/time validators actually run
  unknown kid/alg confusion is blocked
  JWKS rotation works
~~~

Cần **integration tests riêng** gửi raw `Authorization: Bearer <signed-test-jwt>` qua filter và JwtDecoder thật, với test-only issuer/JWKS/key set. Kiểm missing/invalid signature, wrong issuer/audience, expired/nbf, alg allowlist và token purpose.

### 22.4. Chứng minh controller không được gọi

Dùng một test fixture `ControllerEntryProbe` hoặc spy/counter trong test environment:

~~~text
before = controllerEntryProbe.count()

response = mockMvc.get(
    "/api/orders/42",
    Authorization="Bearer <expired-test-token>"
)

assert response.status == 401
assert controllerEntryProbe.count() == before
assert orderService.writeCalls == 0
assert databaseMutations == 0
assert noProtectedDataInResponse()
~~~

Pseudocode để diễn giải contract, không phải JUnit chạy nguyên văn. Với 403 thiếu scope, assertions tương tự phải chứng minh controller không chạy. Với object ACL denial, controller **có thể** chạy nhưng service không được trả/sửa record trái quyền.

### 22.5. Kiểm multiple SecurityFilterChains

~~~text
test "unknown protected route does not escape all chains":
    assert GET /v2/orders/42 without token -> DENY
    assert GET /internal/reindex without token -> DENY
    assert GET /api/orders/42 without token -> 401
    assert GET /health without token -> only permitted health info

test "broad permitAll chain cannot shadow API chain":
    introspect configured security chains and order
    request GET /api/orders/42 without token
    assert no controller entry
~~~

Không chỉ kiểm bằng cách đọc source `@Order`; hãy gửi HTTP requests qua **full Spring Security chain** và có coverage cho mọi paths từ API route inventory.

### 22.6. Kiểm 401/403 có `WWW-Authenticate` và không lộ secrets

~~~text
missing token:
    status 401
    WWW-Authenticate contains Bearer realm/challenge

invalid token:
    status 401
    no raw token/stacktrace in response/logs

valid JWT but scope missing:
    status 403
    optional insufficient_scope challenge per contract
    no controller invocation

opaque introspection timeout:
    fail closed according API service-error policy
    no raw introspection request body in logs
~~~

Kiểm cả response headers/body, backend logs và metrics. Một custom error handler có thể đưa `AuthenticationException.getMessage()` kèm token/claims ra JSON; security regression test cần phát hiện.

### 22.7. Test browser CORS và cookie CSRF

- `OPTIONS` preflight từ allowed origin → CORS response thích hợp; **không cấp protected resource**.
- Preflight từ untrusted origin → không có `Access-Control-Allow-Origin` cho origin đó theo policy.
- Actual protected GET/POST vẫn cần token/scope dù preflight thành công.
- Nếu cùng application có BFF/session-cookie endpoints, cross-site POST thiếu CSRF token phải bị reject theo browser/session contract.
- Nếu API Bearer-only, CSRF policy được phân tích cụ thể và có tests chứng minh không tự nhận cookie như API authentication.

### 22.8. Test end-to-end như một security acceptance criterion

Một bài test tốt không chỉ gọi decoder rồi nhận `true`. Nó gửi request từ bên ngoài tới app/gateway, đi qua **trusted proxy, Servlet security chain, authentication, route authorization** và (với positive path) service/domain ACL. Các yêu cầu về DPoP/mTLS, audience và JWKS/outage chỉ được xem là đạt sau khi test được **deployment topology tương ứng**.

## 23. Incident response: phát hiện request lọt qua security gate

### 23.1. Tình huống

Sau một bản release, endpoint `GET /v2/orders/{id}` mới được thêm. `apiChain` chỉ match `/api/**`, fallback chain bị xóa do refactor. Monitoring phát hiện request không có `Authorization` nhưng trả 200 với dữ liệu orders. Đây là **security bypass**, không chỉ là bug thiếu annotation controller.

### 23.2. Các bước ứng cứu

1. **Bảo toàn bằng chứng:** route, HTTP method, deployment version, timestamps, affected resources và trusted logs; **không copy raw bearer tokens**.
2. **Triage mức độ:** endpoint có public thực không, có trả PII/tenant data không, đã có unauthorized writes không.
3. **Contain nhanh:** chặn route ở ingress/gateway hoặc rollback deploy an toàn; bảo đảm không mở endpoint khác khi sửa.
4. **Tìm nguyên nhân:** `SecurityFilterChain` matchers/order, fallback chain, proxy rewrite, custom filter, method security bypass.
5. **Review logs và data access:** không chỉ đếm HTTP 200; kiểm audit business record reads/writes và object-level ACL.
6. **Restore correct gate:** bảo vệ đúng path/method, JwtDecoder issuer/audience/time, scope/role, session/cookie profile.
7. **Regression tests:** missing/wrong token, wrong audience, unknown path, method, tenant, admin/management routes và controller entry counter.
8. **Token/grant containment khi cần:** nếu access token thật bị lộ hoặc attacker có grants, revoke token/refresh family theo policy; route bypass không mặc nhiên cần rotate AS signing key.
9. **Deploy/canary:** kiểm full proxy→RS chain, metrics 401/403 và allowed requests, không tự fail open khi AS down.
10. **Post-incident:** bắt buộc route inventory/security coverage check trong CI/CD, review code owners, update playbook và time-to-detect metrics.

### 23.3. Các tình huống cần phân biệt

| Signal | Có thể là | Điều tra riêng |
|---|---|---|
| Protected route trả 200 không token. | Chain matcher/fallback/permitAll bypass. | Test coverage và route inventory. |
| JWT `aud` khác vẫn được nhận. | Audience validator thiếu/override. | Decoder bean, validators, test with real signed JWT. |
| Opaque `active=false` vẫn được nhận. | Introspector code sai hoặc stale cache. | AS body, cache TTL, app fallback. |
| Access token hết hạn vẫn chạy. | Time validation/cache bug. | Decoder/clock skew/time policy. |
| Token đúng nhưng cross-tenant order trả dữ liệu. | BOLA/IDOR. | Service query/object ACL, not just filter chain. |
| Hàng loạt 401 sau key rotation. | JWKS propagation/issuer mismatch. | K1/K2 timeline, caches and trust policy. |
| Hàng loạt 503 opaque APIs. | AS introspection/token store outage. | Availability/HA, fail-closed policy. |
| Scope 403 sau deploy mới. | New API requires scope client chưa được cấp. | Client grant, consent, route rules. |
| DPoP token được dùng mà không proof. | Sender-bound enforcement missing. | Token `cnf` and proof verification path. |

### 23.4. Không làm lộ nguyên nhân nhạy cảm tới public caller

Security logs nội bộ có thể phân biệt `WRONG_ISSUER` và `INVALID_SIGNATURE`, nhưng response public thường chỉ nên trả thông tin Bearer error phù hợp. Không trả stacktrace, raw JWT, token introspection response metadata hoặc private policy details. Khi cần hỗ trợ khách hàng, dùng correlation reference nội bộ có RBAC.

### 23.5. Chữa availability mà bỏ xác thực là giải pháp sai

Một đội vận hành có thể đề xuất `anyRequest().permitAll()` hoặc catch `JwtException` rồi set authenticated=true để service chạy qua outage. Điều này biến sự cố hạ tầng thành lỗ hổng bảo mật. Giải pháp đúng là **rollback tin cậy, HA/cache policy, bounded retry, isolate dependency** và error response fail-closed.

### 23.6. Incident metrics nên đo

~~~text
time_to_detect_route_bypass
time_to_contain_unauthorized_route
affected_endpoints_and_methods
unauthorized_reads_and_writes_estimate
token_validation_coverage_percent
controller_entry_after_rejected_auth_attempts
revocation_propagation_latency
post_fix_negative_test_pass_rate
~~~

Các metrics là **định hướng**, cần định nghĩa đo/nguồn evidence thực; không đưa user PII/token IDs vào metric labels. Nếu không có logs đủ tin để ước tính impacted requests, báo **uncertainty** thay vì khẳng định không có unauthorized reads.

## 24. Bài tập tình huống có đáp án

### 24.1. Bài 1 — Controller trả 401 nhưng đã chạy

Một controller tự kiểm `Authorization`, sau đó ghi một audit/business event, cuối cùng mới trả `401 Unauthorized` vì token sai.

**Đáp án:** Chưa đáp ứng **chặn trước controller**. Authentication phải ở Servlet/Spring Security filter chain; request invalid không chạm protected controller. Audit ở security layer có thể ghi safe event, nhưng không để business logic chạy rồi mới deny. Test bằng spy/counter và DB snapshot, không chỉ `status=401`.

### 24.2. Bài 2 — JWT đúng chữ ký nhưng sai audience

Access token do AS thật phát, ký RS256 hợp lệ, `scope=orders:read`, nhưng `aud=payments-api`. Orders RS chỉ check signature.

**Đáp án:** **Từ chối 401 trước controller.** Thêm trusted issuer và per-resource audience validator (`orders-api`), token type và expiry. Signature chỉ cho biết token do signer tương ứng phát, không có quyền dùng ở mọi RS.

### 24.3. Bài 3 — JWT đúng audience nhưng thiếu scope

Token hợp lệ có `aud=orders-api`, `scope=profile:read`. Request `GET /api/orders/42` yêu cầu `orders:read`.

**Đáp án:** Authentication thành công, route authorization phải **403 Forbidden** và controller không chạy. Scope converter phải tạo authorities từ verified claims; rule GET cần `SCOPE_orders:read`. Không dùng `anyRequest().authenticated()` thay scope control.

### 24.4. Bài 4 — Token không có `Authorization` nhưng được tiếp tục

Một request `GET /api/orders/42` không có Bearer nhưng filter chỉ kiểm token **nếu header xuất hiện**, còn thiếu header thì gọi `chain.doFilter()`.

**Đáp án:** Đây là fail-open trên protected route. Dùng Spring Resource Server + `authorizeHttpRequests`; thiếu credential phải **401 Bearer challenge**, không gọi controller. Nếu endpoint public thật, public route phải được khai báo cụ thể.

### 24.5. Bài 5 — HTTP 200 từ introspection

AS trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

**Đáp án:** Token **không hợp lệ**. Introspection HTTP request thành công không có nghĩa credential active. RS phải kiểm `active===true` cùng metadata issuer/audience/expiry/scope theo contract, từ chối trước controller.

### 24.6. Bài 6 — AS introspection timeout

Opaque RS không có cached metadata còn hạn, AS token store unreachable. Đội dev đề nghị `catch(Exception) { return authenticated; }`.

**Đáp án:** **Không được fail open.** Không có bằng chứng token active thì protected controller không chạy. Có thể trả 503 theo contract để phân biệt dependency outage, hoặc áp bounded prior-verified cache theo policy. Cần HA/circuit breaker và kiểm revocation SLA.

### 24.7. Bài 7 — Mở API v2 nhưng chỉ bảo vệ v1

Ứng dụng có `securityMatcher("/api/**")`; đội khác tạo `GET /v2/orders/42`, fallback chain không tồn tại.

**Đáp án:** Route có thể lọt ngoài resource-server filter. Bổ sung fallback deny chain và route inventory/security coverage tests; rà cả ingress/proxy rewriting. Không chỉ gắn `@PreAuthorize` vào controller rồi giả định mọi route đã được chặn theo OAuth policy.

### 24.8. Bài 8 — `permitAll` đặt sai thứ tự

`@Order(1)` chain match `/**`, `permitAll`; `@Order(2)` chain `/api/**` yêu cầu JWT.

**Đáp án:** Chain đầu tiên đã match mọi request, chain thứ hai không được chọn. Sửa chain order/matchers, dùng explicit public health routes và fallback deny. Viết integration tests gửi request thật tới `/api/orders` không có token.

### 24.9. Bài 9 — GET được phép, DELETE chưa có chính sách

Client có token `orders:read`; Spring rule chỉ kiểm `requestMatchers("/api/orders/**").authenticated()` cho mọi methods.

**Đáp án:** Sai về least privilege. GET cần read scope, DELETE/refund/write cần rules riêng và business authorization trước side effects. Nếu method chưa thiết kế, denyAll; không cho authenticated client tự được xóa orders.

### 24.10. Bài 10 — CORS origin được phép thì bỏ token được?

Browser từ `https://app.example.com` qua CORS preflight hợp lệ. Client gửi actual GET nhưng không có Bearer.

**Đáp án:** Actual protected GET phải **401**. CORS là browser cross-origin policy, không chứng minh identity/scope và không thay JWT/introspection. Preflight `OPTIONS` có thể không có credential, nhưng điều đó không cho phép permitAll actual methods.

### 24.11. Bài 11 — Disable CSRF khi có session cookie

Một Spring Boot ứng dụng vừa có BFF session-cookie `POST /app/payments`, vừa có stateless Bearer `/api/**`. Dev disable CSRF toàn ứng dụng vì “đã dùng JWT ở API”.

**Đáp án:** Không an toàn với stateful cookie endpoints. Tách chains/CSRF policy: Bearer-only API có thể tắt CSRF theo threat model, còn cookie-auth flows vẫn cần CSRF/SameSite/origin defenses. `SessionCreationPolicy.STATELESS` của một chain không tự chứng minh các routes khác không nhận cookies.

### 24.12. Bài 12 — JWT có scope đúng, user sai tenant

User `tenant-beta` có `orders:read` và truy cập order thuộc `tenant-anpha`.

**Đáp án:** Filter có thể pass token/route, nhưng service/DB phải **deny object-level**. Dùng verified tenant+subject/current roles trong query/ACL, không trust `X-Tenant-Id`. Đây là BOLA/IDOR chứ không phải lỗi JWT signature.

### 24.13. Bài 13 — DPoP-bound token mà không có proof

Access token có `cnf.jkt` nhưng RS dùng Bearer JWT decoder mặc định và không kiểm `DPoP` header.

**Đáp án:** Không đáp ứng sender constraint. RS phải verify proof signature, `ath`, `htm`/`htu`, freshness/replay và holder thumbprint matching. Chỉ check token valid/`cnf` metadata không ngăn token-string replay.

### 24.14. Bài 14 — mTLS-bound token và header giả

Gateway terminate TLS; backend nhận `X-Client-Cert` trực tiếp từ public caller mà không xác minh gateway/source.

**Đáp án:** Không thể tin header. Phải authenticate TLS client certificate ở controlled boundary, forward proof/identity metadata qua trusted secured channel và so certificate thumbprint với token binding. Otherwise reject.

### 24.15. Bài 15 — `jwt()` MockMvc test PASS nhưng RS vẫn nhận fake JWT

Test dùng `.with(jwt())` và thấy route trả 200. Production lại chấp nhận token có `iss` lạ.

**Đáp án:** `jwt()` test postprocessor không chạy production JwtDecoder cryptographic validation. Cần integration tests với **real signed test JWT** và actual Bearer header/decoder cho signature, issuer, audience, time, typ, algorithm và JWKS rotation. MockJwt scope test vẫn hữu ích cho AuthorizationFilter.

### 24.16. Bài 16 — Private signing key bị lộ

AS private JWT signing key bị compromise; RS vẫn cache public key và tiếp tục verify JWT cho đến hết hạn.

**Đáp án:** Normal rotation overlap có thể **không phù hợp** khi attacker có khả năng ký giả. Cần emergency trust cutoff/reissue/revocation policy, kiểm mọi RS/JWKS cache và đánh giá blast radius. Không tự chữa bằng cách bật `permitAll` vì phát sinh 401.

### 24.17. Bài 17 — Token hợp lệ nhưng request có side effect trước permission check

Controller gọi `refundPayment()` rồi mới dùng `@PostAuthorize` để kiểm owner.

**Đáp án:** Quá muộn: side effect có thể đã xảy ra trước denial. Kiểm quyền/approvals trước write, áp DB predicates/transactions và method preauthorization, không chỉ nhìn HTTP 403 sau cùng.

### 24.18. Bài 18 — Service gọi từ message consumer

REST route được bảo vệ bằng Spring filter. Nhưng một Kafka consumer gọi cùng service method với actor field từ message không được xác minh, bỏ qua HTTP chain.

**Đáp án:** HTTP filter không chạy với message consumer. Domain/use-case security phải xác thực nguồn message/actor context và kiểm permissions/tenant/object trước side effects. Không coi `@PreAuthorize` proxy hoặc HTTP route là bảo vệ toàn bộ entrypoints nếu không test từng đường gọi.

## 25. Checklist triển khai “Chặn request trước controller”

### 25.1. Token trust và authentication

- [ ] Đã xác định resource identifier/audience của từng API, ví dụ `orders-api` khác `payments-api`.
- [ ] Trusted issuer/JWKS hoặc RFC 7662 introspection endpoint đến từ server configuration, không từ raw token URL/header.
- [ ] Signed access JWT được verify signature bằng approved algorithm/key; không chấp nhận `alg=none`.
- [ ] `iss`, `aud`, `exp`, `nbf` và time policy được kiểm; clock skew có bound hợp lý.
- [ ] Token type/profile (`at+jwt` theo RFC 9068 khi áp dụng) được kiểm để tránh ID token/client assertion/DPoP proof substitution.
- [ ] Refresh token/authorization code không được dùng như Bearer access token tại RS.
- [ ] Opaque token introspection qua TLS với authenticated/authorized RS caller và metadata tối thiểu.
- [ ] HTTP 200 introspection `active=false` vẫn bị reject.
- [ ] Opaque metadata thiếu issuer/audience/expiry/purpose bắt buộc → fail closed theo contract.
- [ ] Token purpose/client principal type (service vs user) rõ trong route authorization.
- [ ] Bearer extraction không nhận token tùy tiện từ query/body/cookie nếu API policy không cho; ambiguous credentials bị reject.
- [ ] Không tạo `Authentication` từ untrusted `X-User-Id`/`X-Tenant-Id` hoặc Base64URL payload chưa verify.
- [ ] AS signing/verification key management, JWKS rotation và emergency compromise policy đã được thiết kế.

### 25.2. SecurityFilterChain và route permissions

- [ ] Spring Security `oauth2ResourceServer().jwt()` hoặc `opaqueToken()` được bật cho protected API chain.
- [ ] `securityMatcher` bao phủ đúng paths; `requestMatchers` bao phủ đúng methods/routes.
- [ ] Multiple chains có order đúng, không có permitAll match-all shadow API chain.
- [ ] Có fallback deny-by-default cho URLs chưa phân loại.
- [ ] Public routes được allowlist rõ; actuator/admin/Swagger có separate environment/network/security policy.
- [ ] Authenticated routes cần scope/role cụ thể, không chỉ `authenticated()` nếu nghiệp vụ đòi quyền.
- [ ] Scope/authorities mapping chạy trên **verified token metadata**, theo issuer/profile và tenant policy.
- [ ] `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` được test đúng API semantics.
- [ ] Route normalization/encoded paths/proxy rewriting không gây security–handler mismatch.
- [ ] Error/forward/async dispatch và SecurityContext propagation được kiểm theo framework configuration.
- [ ] Missing/invalid token hoặc missing required route scope không chạm protected controller.
- [ ] 401 Bearer challenge, 403 insufficient scope và dependency errors có semantics đúng, không leak credentials.

### 25.3. Object authorization và side effects

- [ ] Token scope/audience không thay object-level ACL hoặc tenant membership checks.
- [ ] Principal user/service/actor type được chuẩn hóa từ verified data, không suy từ raw headers.
- [ ] Tenant ID và subject/owner constraints áp tại business service/DB trước dữ liệu nhạy cảm.
- [ ] Writes/refunds/transfers kiểm ownership, state, approvals và policy **trước side effects**.
- [ ] Method security được bật nếu dùng, kiểm proxy/self-invocation và non-HTTP entrypoints.
- [ ] `@PostAuthorize` không được dùng như bước duy nhất bảo vệ side-effecting operations.
- [ ] Delegated access/token exchange kiểm audience/actor/grant boundaries riêng.
- [ ] Valid token khác tenant vẫn bị deny và không trả protected data.
- [ ] Database/RLS/transactions và caches có consistency policy cho permission changes khi cần.

### 25.4. Browser, proxy và replay defenses

- [ ] Nếu RS chỉ dùng Bearer header, stateless/CSRF policy được đánh giá cụ thể, không disable CSRF cho cookie endpoints.
- [ ] CORS preflight được xử lý đúng, không biến allowed origin thành authentication.
- [ ] Cookie/BFF session routes có CSRF, SameSite/HttpOnly/Secure và session fixation defenses.
- [ ] Reverse proxy strip/overwrite untrusted forwarded headers, identity/tenant/cert propagation được xác thực.
- [ ] Token storage, network TLS và access log redaction được kiểm; không log raw Authorization/refresh tokens.
- [ ] DPoP proof/cert binding được verify theo profile nếu access token sender-constrained.
- [ ] DPoP `ath`/`htu`/`htm`/`jti`/nonce/freshness và mTLS certificate checks có negative tests.
- [ ] Rate limiting, input size bounds và DoS controls cho random Bearer/unknown `kid` probes.
- [ ] CORS/CSRF/DPoP/mTLS không được xem là thay issuer/audience/scope/object policy.

### 25.5. Reliability, telemetry và kiểm thử

- [ ] JWKS/public key caches có trusted source, bounded refresh và key-rotation rollout tests.
- [ ] AS introspection timeout/5xx không cho token qua; bounded verified cache policy rõ.
- [ ] Positive introspection cache không vượt `exp`, revocation-to-deny SLA được đo end-to-end.
- [ ] Token store failover/replica/DR không hồi sinh revoked token ngoài policy.
- [ ] Logs/metrics chỉ chứa reason codes/correlation refs, không raw token/user PII/high-cardinality token IDs.
- [ ] Metrics theo dõi JWT invalid signatures, wrong issuer/audience, opaque inactive, scope 403, object denials, sender proof và dependency errors.
- [ ] Có integration tests JWT thật qua `JwtDecoder`, không chỉ MockMvc `jwt()` giả principal.
- [ ] Có negative tests cho wrong signature/alg/issuer/audience/expiry/purpose và opaque active=false.
- [ ] Có chain coverage tests cho `/api/**`, `/v2/**`, `/internal/**`, actuator/admin và fallback deny.
- [ ] Có tests scope/HTTP methods, tenant/object BOLA, CSRF/CORS, proxy forwarded headers, DPoP/mTLS.
- [ ] Với 401/403 pre-controller, test **controller entry counter=0**, service write calls=0, DB mutations=0.
- [ ] Với valid token nhưng wrong object, service policy deny và dữ liệu/side effects không rò.
- [ ] Incident runbook phân biệt filter-chain bypass, AS/JWKS outage, token theft, grant revoke và signing-key compromise.
- [ ] Không chấp nhận workaround `permitAll`/fail-open khi issuer/introspection temporarily down.

**Ghi nhớ:** **Resource Server phải xác thực access token và quyết định quyền route trước controller** bằng một pipeline có thể chứng minh, thường là Spring Security `SecurityFilterChain`. **JWT phải kiểm issuer, audience, signature, expiry, token purpose và scopes**; **opaque token phải có authenticated introspection `active=true` cùng metadata đáng tin**. **401** thường là thiếu/sai credential, **403** là principal đã xác thực nhưng thiếu quyền. Đừng nhầm “controller không chạy” với “mọi dữ liệu đều an toàn”: **tenant/object ownership, business policy và kiểm quyền trước side effects** vẫn thuộc service/database. Thiết kế deny-by-default, kiểm đủ mọi paths/methods/chains, chống replay theo threat model, bảo vệ logs và **fail closed khi không thể xác minh**.

## 26. Tài liệu chuẩn và tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** AS, RS, client roles, access/refresh tokens, grants và scope semantics.
- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage:** Authorization header, `WWW-Authenticate`, `invalid_token` và `insufficient_scope`.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** audience, token handling, code/refresh hardening và replay prevention.
- **RFC 7662 — OAuth 2.0 Token Introspection:** active state, authorized RS caller, minimum response metadata và opaque token support.
- **RFC 7009 — OAuth 2.0 Token Revocation:** access/refresh token revocation và state propagation.
- **RFC 9068 — JSON Web Token Profile for OAuth 2.0 Access Tokens:** access JWT `typ`/claims và resource-server validation.
- **RFC 7519 — JSON Web Token (JWT):** issuer, audience, expiration, not-before và token claims.
- **RFC 7515 — JSON Web Signature (JWS):** signature structure/protected header và verification.
- **RFC 7517 — JSON Web Key (JWK):** trusted JWKS, key parameters và `kid`.
- **RFC 7518 — JSON Web Algorithms (JWA):** JWS `RS256`/`PS256`/`ES256` algorithms và key usage.
- **RFC 7516 — JSON Web Encryption (JWE):** encrypted tokens; decryption does not replace issuer/authorization checks.
- **RFC 8725 — JSON Web Token Best Current Practices:** algorithm confusion, key/issuer trust, cross-JWT substitution và validation.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** resource/audience request and token issuance constraints.
- **RFC 8693 — OAuth 2.0 Token Exchange:** delegated identities and audience-specific downstream tokens.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS sender binding and certificate confirmation.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof, `ath`, `htu`/`htm`, holder keys và replay.
- **OpenID Connect Core 1.0:** ID token purpose/validation khác OAuth access-token purpose.
- **OWASP API Security Top 10 — Broken Object Level Authorization (BOLA):** object/tenant checks after authentication.
- **OWASP REST Security Cheat Sheet:** API authentication, authorization, secure errors and input handling.
- **OWASP JSON Web Token Cheat Sheet:** JWT verification/claims/storage/revocation.
- **OWASP OAuth 2.0 Cheat Sheet:** token protection and Resource Server validation.
- **OWASP Cross-Site Request Forgery Prevention Cheat Sheet:** cookie/session CSRF defense and anti-forgery patterns.
- **OWASP Logging Cheat Sheet:** credential redaction and security-event handling.
- **Spring Security Reference — Architecture:** `FilterChainProxy`, `SecurityFilterChain`, filter ordering and authorization.
- **Spring Security Reference — OAuth2 Resource Server JWT:** `BearerTokenAuthenticationFilter`, `JwtDecoder`, issuer/JWKS/claims validators.
- **Spring Security Reference — OAuth2 Resource Server Opaque Tokens:** `OpaqueTokenIntrospector` and RFC 7662 introspection.
- **Spring Security Reference — Authorize HTTP Requests:** `authorizeHttpRequests`, `securityMatcher`, `requestMatchers` and `AuthorizationFilter`.
- **Spring Security Reference — Method Security:** `@EnableMethodSecurity`, `@PreAuthorize`/`@PostAuthorize` and proxy limitations.
- **Spring Security Reference — CORS and CSRF:** browser preflight, cookies and security filters.
- **Spring Security Reference — Testing:** `spring-security-test`, MockMvc and `SecurityMockMvcRequestPostProcessors.jwt()`.
- **Spring Boot Reference — Security and OAuth2 Resource Server:** auto-configuration and managed security properties.
