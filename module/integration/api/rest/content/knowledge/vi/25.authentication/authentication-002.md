# API key, HTTP Basic, Bearer token và phạm vi áp dụng

> **Module:** INTEGRATION_API_REST — thiết kế REST API theo resource, URI, HTTP method/status và hợp đồng dữ liệu; thực hành xác thực, phân quyền, xử lý lỗi, OpenAPI và kiểm thử với Java/Spring.  
> **Chương:** Xác thực.  
> **Trọng tâm:** Hiểu và lựa chọn **API key**, **HTTP Basic** và **Bearer token**, thiết kế hợp đồng HTTP đúng, bảo vệ bí mật, phân biệt xác thực với phân quyền và triển khai/kiểm thử bằng Spring Security.

## 1. Một endpoint, ba cách chứng minh danh tính

Một đối tác tích hợp API lấy trạng thái đơn hàng:

```http
GET /api/orders/ord-501 HTTP/1.1
Host: api.example.com
Accept: application/json
```

Máy chủ cần biết **ai đang gọi** trước khi quyết định có cho đọc đơn `ord-501` hay không. Ba cách cung cấp thông tin xác thực thường gặp:

```http
# API key theo hợp đồng riêng của API
X-API-Key: <secret-key>

# HTTP Basic theo chuẩn HTTP Authentication
Authorization: Basic <base64(username:password)>

# Bearer token theo chuẩn HTTP Authentication
Authorization: Bearer <access-token>
```

Cả ba chỉ an toàn khi **HTTPS/TLS được cấu hình và xác minh đúng**. Giá trị trong header là bí mật có thể bị lộ qua log, proxy, URL/history nếu triển khai sai. Đừng đánh đồng việc “có một chuỗi bí mật” với việc “có quyền với mọi resource”.

Sau bài này, bạn có thể:

1. Chọn cơ chế phù hợp với tích hợp máy–máy, hệ thống cũ hoặc ứng dụng OAuth/OIDC.
2. Phân biệt **authentication (AuthN)**, **authorization (AuthZ)**, client identity, user identity và scope.
3. Thiết kế phản hồi **401/403**, `WWW-Authenticate` và lỗi có cấu trúc.
4. Triển khai luồng xác thực trong Spring Security, không tự tạo cơ chế token thiếu kiểm tra.
5. Test token/key sai, hết hạn, thiếu quyền, sai tenant, rate limit và rò dữ liệu.

## 2. Trước hết: xác thực không phải phân quyền

**Authentication** trả lời: request được gắn với **principal nào** (người dùng, đối tác hoặc service account)?  
**Authorization** trả lời: principal đó có được thực hiện **hành động cụ thể trên resource cụ thể** không?

```mermaid
flowchart LR
    C["Client + credential"] --> T["TLS + Authentication"]
    T --> P["Principal / client identity"]
    P --> A["Scope/role + tenant/resource authorization"]
    A --> D["Domain service / database"]
    A -->|Denied| E["401/403/404 theo policy"]
    D --> R["200/201/204 hoặc domain error"]
```

Ví dụ token có quyền `orders.read` không có nghĩa người gọi được đọc **mọi** đơn hàng:

```text
Principal: partner-12
Allowed tenant: tenant-A
Scopes: orders.read

GET /orders/ord-501 (thuộc tenant-A) → có thể được phép
GET /orders/ord-902 (thuộc tenant-B) → phải từ chối
```

Scope là một **điều kiện cần** trong nhiều hệ thống, nhưng không thay kiểm tra tenant, owner, trạng thái đơn hay policy nghiệp vụ. Tên API key, tên user trong Basic hoặc trường `sub` trong JWT không đủ để tự động xác định quyền.

### 2.1. Danh tính của ứng dụng khác danh tính người dùng

- **API key:** thường định danh **ứng dụng/đối tác/project**; có thể gắn quyền và quota do server quản lý, nhưng không mặc định đại diện cho người dùng cuối.
- **HTTP Basic:** mang username/password của account; account đó có thể là người hoặc service account. Không nên chia sẻ tài khoản người dùng giữa nhiều ứng dụng.
- **Bearer access token:** có thể đại diện cho người dùng được ủy quyền hoặc cho **client** (OAuth 2.0 client credentials); cần xem **issuer, audience, grant, scopes/claims** và policy.


## 3. API key: bí mật tĩnh cho tích hợp có kiểm soát

```http
GET /api/partner/orders HTTP/1.1
X-API-Key: <partner-secret>
```

`X-API-Key` là **convention của API**, không phải HTTP authentication scheme chuẩn. API key thường định danh **ứng dụng/đối tác**, giúp cấp quyền hẹp, quota và audit. Nó phù hợp máy–máy với ít đối tác, không tự đại diện cho một người dùng hay hỗ trợ delegation kiểu OAuth.

### 3.1. Cấp, xác minh và thu hồi

1. Sinh secret bằng CSPRNG với entropy cao (ví dụ 256 bit), cấp **key ID** riêng để tra cứu.
2. Hiển thị secret **một lần**; client lưu trong secrets manager, không nhúng vào frontend hoặc mã nguồn.
3. Lưu metadata `keyId`, tenant, scopes/policy, expiry/revoked và digest/HMAC của secret; không lưu plain text.
4. Khi nhận request, tra key ID, so sánh digest an toàn, kiểm tra trạng thái/tenant/quota/rate limit.
5. Cho phép **rotation hai key chồng lấn ngắn hạn**, cập nhật client, thu hồi key cũ và audit.

Ví dụ format `pk_live_<public-id>.<random-secret>` chỉ là quy ước minh họa. Với random secret đủ entropy, SHA-256/HMAC dùng cho verification; HMAC pepper phía server giúp giảm ảnh hưởng khi database lộ. Password người dùng entropy thấp thì cần password KDF chậm như Argon2id/bcrypt, không áp nguyên xi thiết kế API key.

**Rủi ro:** key bị copy có thể bị dùng lại; một key không nên có quyền vượt tenant/quota. Tránh `?api_key=...` vì URL dễ lọt vào history, proxy log, referrer. Không cấp secret dài hạn cho SPA/mobile app có thể bị trích xuất; cân nhắc backend-for-frontend hoặc OAuth user delegation.

## 4. HTTP Basic: Base64 của username/password

```http
GET /api/legacy/reports HTTP/1.1
Authorization: Basic YXBpLXVzZXI6c2VjcmV0
```

Theo **RFC 7617**, chuỗi trên giải mã thành `api-user:secret`. **Base64 không mã hóa password**, nên TLS/HTTPS bắt buộc. Client thường gửi lại credential trong mỗi request; cú pháp Basic **không có** access token expiry, scopes hoặc refresh token.

Challenge chuẩn khi thiếu/sai credential:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="legacy-partner", charset="UTF-8"
Cache-Control: no-store
```

`realm` chỉ vùng bảo vệ; `charset="UTF-8"` là tham số trên challenge theo RFC 7617. Dùng Basic khi cần tương thích **legacy/internal** có service account riêng, TLS và kế hoạch migration. Không chia sẻ password người dùng giữa đối tác hoặc dùng Basic làm mặc định cho browser public.

Cần password encoder phù hợp, rate limit/lockout, account quyền tối thiểu, rotation, giám sát, không log Authorization/không đặt `user:pass` trong URL. Nếu trình duyệt tự gửi credential (Basic hoặc cookie) khi truy cập, các request ghi vẫn phải **đánh giá CSRF** theo threat model; không mặc định “API dùng HTTP Basic thì miễn CSRF”.

## 5. Bearer access token: người giữ token có thể dùng quyền của nó

```http
GET /api/orders/ord-501 HTTP/1.1
Authorization: Bearer <access-token>
```

Theo **RFC 6750**, Bearer là credential mà **ai giữ token hợp lệ đều có thể sử dụng** trong scope/audience cho phép. TLS, không lưu token trong URL/log, TTL ngắn và quyền hẹp là nền tảng. Bearer thông thường **không chứng minh sở hữu khóa riêng**.

### 5.1. Bearer không đồng nghĩa JWT

| Token | Resource server làm gì? | Đánh đổi |
|---|---|---|
| **JWT self-contained** | Xác minh chữ ký, thuật toán, `iss`, `aud`, `exp`/`nbf` và claims | Validation cục bộ; thu hồi tức thì cần cơ chế riêng |
| **Opaque reference token** | Introspection/token store được bảo vệ, có cache TTL phù hợp | Thu hồi tập trung; phụ thuộc availability/latency của auth server |

**Giải mã payload JWT không phải xác minh chữ ký**. Token có ba phần vẫn có thể là giả; phải allowlist thuật toán/nguồn JWK tin cậy, không chấp nhận issuer/audience không đúng. Cùng một cú pháp Bearer không có nghĩa token nhất thiết do OAuth 2.0 phát hành.

### 5.2. Audience, scope và tenant

Ví dụ **claims minh họa của JWT đã được xác minh**:

```json
{"iss":"https://id.example.com","sub":"user-73",
 "aud":["orders-api"],"exp":1795000000,
 "scope":"orders.read orders.write","tenant_id":"tenant-A"}
```

- `iss`: authorization server đáng tin; `aud`: chính resource server này.
- `exp`/`nbf`: token đang có hiệu lực; key/alg/signature phải hợp lệ.
- `scope`/`scp`: điều kiện quyền ở cấp operation; **không thay** authorization theo order/tenant.
- `sub` có thể là user hoặc client: OAuth `client_credentials` thường đại diện service, không phải user.

Access token TTL ngắn; refresh token (nếu có) **chỉ gửi tới authorization server** và phải được bảo vệ theo grant phù hợp. Không dùng **OIDC ID token** làm access token cho REST API chỉ vì cùng định dạng JWT. JWT cần xử lý key rotation/revocation; opaque cần introspection timeout/fail-closed. Khi rủi ro replay cao, có thể dùng sender-constrained token như **mTLS-bound** hoặc **DPoP**, nếu hệ sinh thái hỗ trợ.

## 6. 401, 403 và `WWW-Authenticate` là hợp đồng HTTP

### 6.1. Với HTTP Basic

Không có credential hoặc sai credential:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="legacy-partner"
Cache-Control: no-store
```

### 6.2. Với OAuth 2.0 Bearer

Không có token (challenge không cần tiết lộ chi tiết lỗi):

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
```

Token đã gửi nhưng hết hạn/không hợp lệ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"https://api.example.com/problems/invalid-token",
 "title":"Thông tin xác thực không hợp lệ","status":401}
```

Token hợp lệ nhưng thiếu OAuth scope cần thiết:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
Content-Type: application/problem+json

{"type":"https://api.example.com/problems/insufficient-scope",
 "title":"Không đủ quyền","status":403}
```

Theo RFC 6750, `invalid_request` có thể tương ứng 400, `invalid_token` 401, `insufficient_scope` 403. Không trả chi tiết nhạy cảm như claims, token string, tên user thật hoặc lý do nội bộ vào body. Với thiếu quyền theo **tenant/owner**, 403 hoặc 404 để che sự tồn tại tùy policy, không nhất thiết phát `insufficient_scope` nếu scope đã đủ nhưng object bị cấm.

**HTTP 401 yêu cầu `WWW-Authenticate` challenge phù hợp** theo HTTP semantics. Basic và Bearer có challenge chuẩn. Với API key trong **custom header**, không có challenge chuẩn phổ quát: cần chọn một chính sách lỗi rõ ràng, hoặc định nghĩa scheme/challenge riêng nếu dùng 401; đừng tùy tiện giả một challenge Bearer cho key ở `X-API-Key`. Với key hợp lệ nhưng không đủ quyền, 403 thường phù hợp.

### 6.3. Xử lý lỗi bằng Problem Details

Nếu công bố `application/problem+json`, mọi lớp phát lỗi phải tuân schema:

```json
{
  "type": "https://api.example.com/problems/forbidden",
  "title": "Không đủ quyền",
  "status": 403,
  "detail": "Bạn không được phép truy cập tài nguyên này."
}
```

`detail` chỉ dùng cho con người; client nên dựa trên `type`/HTTP status hoặc code extension ổn định. **Không dùng response `200 OK` kèm `{"success":false}`** cho auth lỗi.

## 7. Chọn cơ chế theo consumer

| Tiêu chí | API key | Basic | Bearer |
|---|---|---|---|
| Danh tính phổ biến | App/partner | Account/service account | Client hoặc end-user |
| Credential | Header theo API | `Authorization: Basic` | `Authorization: Bearer` |
| Quyền | Key policy/quota | Account roles | Scopes/claims + resource policy |
| Vòng đời | Rotation/revoke server | Password rotation | TTL ngắn, refresh/introspection |
| Dùng tốt nhất | Máy–máy đơn giản | Hệ legacy có TLS | Đa client, OAuth delegation |
| Hạn chế | Secret dài hạn, không có user consent | Password lặp lại mỗi request | Replay nếu token bị đánh cắp |

Một batch job hẹp không nhất thiết cần OAuth đầy đủ; hệ thống có user consent và nhiều third-party lại không nên dùng API key chung. Ưu tiên giữ cơ chế đã được quản trị/test tốt thay vì thay chỉ để “hiện đại hóa” cú pháp.

## 8. Spring Security: Bearer JWT và Basic theo từng route

Các ví dụ dùng **Spring Boot 3 / Spring Security 6** với REST API. Tên dependency/bean có thể thay đổi theo version; luôn kiểm thử bản stack thực tế.

### 8.1. Tách security chain để Basic không lan rộng

```java
import static org.springframework.security.config.http.SessionCreationPolicy.STATELESS;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain legacyBasic(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/legacy/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(s -> s.sessionCreationPolicy(STATELESS))
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(s -> s.sessionCreationPolicy(STATELESS))
            .authorizeHttpRequests(a -> a
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

**Basic chỉ áp dụng `/api/legacy/**`**, Bearer JWT cho `/api/**` còn lại. Spring xét chain theo `@Order` và dùng matcher đầu tiên phù hợp.

Basic cần `AuthenticationProvider`/`UserDetailsService` và password encoder; Bearer cần JWT decoder kiểm tra chữ ký, issuer và **audience**. Không hardcode password hoặc chỉ dựa vào `hasAuthority`.

Ví dụ properties nền tảng:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
```

Issuer URI hỗ trợ metadata/JWK và validation; **audience `orders-api` cần được kiểm tra bổ sung**. Mapping `scope`/`scp` thành `SCOPE_*` là convention của Spring Security, không phải đặc tính JWT.

**Về CSRF:** `csrf.disable` trong ví dụ chỉ thích hợp nếu endpoints này thực sự **stateless và không dựa vào cookie/session tự gửi** để xác thực request ghi. Khi trình duyệt gửi cookie/session, phải phân tích CSRF và giữ bảo vệ phù hợp; không copy cấu hình này vào web app một cách máy móc.

### 8.2. Kiểm tra quyền ở resource service

Dù URL `/api/orders/**` đã đòi `SCOPE_orders.read`, controller/service vẫn cần kiểm tra tenant:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService orders;

    OrderController(OrderService orders) { this.orders = orders; }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> find(
            @PathVariable String id, Authentication principal) {

        OrderView view = orders.findVisible(
                principal, id); // Kiểm tra tenant/owner trong service.
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(view);
    }
}
```

Không trả JPA entity chứa trường nhạy cảm. `OrderService` là interface do dự án triển khai; việc `findVisible` cần được thực hiện bằng truy vấn theo scope (hoặc kiểm tra quyền an toàn) để tránh IDOR và side-channel từ resource tồn tại ngoài quyền.

### 8.3. Opaque token: không thay cơ chế header

Với opaque token, HTTP vẫn là:

```http
Authorization: Bearer <opaque-access-token>
```

Spring có thể dùng Resource Server với opaque-token introspection thay JWT validation:

```java
.oauth2ResourceServer(o -> o.opaqueToken(Customizer.withDefaults()))
```

Chỉ chọn **một** cấu hình phù hợp theo issuer/token contract. Introspection endpoint phải có TLS, authentication, timeout và fail-closed policy; không log token. Nếu cần kết hợp nhiều issuer/token formats, thiết kế resolver đáng tin và kiểm thử token confusion.

## 9. Spring Security: API key cần cơ chế riêng

Spring Security hỗ trợ Basic và OAuth2 Resource Server trực tiếp; **`X-API-Key` tùy biến** thường cần filter/provider riêng. Mục tiêu của filter là kiểm chứng key rồi tạo **Authentication** đáng tin cậy cho security chain.

Ví dụ skeleton, không bao gồm quản lý DB/secrets:

```java
final class PartnerApiKeyFilter extends OncePerRequestFilter {
    private final ApiKeyVerifier verifier;
    private final AuthenticationEntryPoint entryPoint;

    PartnerApiKeyFilter(ApiKeyVerifier verifier,
                        AuthenticationEntryPoint entryPoint) {
        this.verifier = verifier;
        this.entryPoint = entryPoint;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String raw = request.getHeader("X-API-Key");
        if (raw == null || raw.isBlank()) {
            chain.doFilter(request, response);
            return; // Authorization sau đó từ chối anonymous.
        }

        var verified = verifier.verify(raw); // Optional<PartnerIdentity>
        if (verified.isEmpty()) {
            SecurityContextHolder.clearContext();
            entryPoint.commence(request, response,
                    new BadCredentialsException("Invalid API key"));
            return;
        }

        PartnerIdentity partner = verified.get();
        var authentication = new UsernamePasswordAuthenticationToken(
                partner, null, partner.authorities());

        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
        chain.doFilter(request, response);
    }
}
```

`ApiKeyVerifier` và `PartnerIdentity` cần hiện thực; giả định verifier tra cứu key ID, kiểm tra hash/HMAC, revoked/expiry, tenant/permissions/rate-limit, không trả raw key hoặc nguyên nhân chi tiết. Với authentication tùy biến, cần đảm bảo context lifecycle được Spring Security quản lý/clear đúng, không giữ principal giữa requests.

Đăng ký filter chỉ cho `/api/partner/**` bằng **SecurityFilterChain riêng**, ví dụ:

```java
@Bean
@Order(0)
SecurityFilterChain partnerApi(
        HttpSecurity http, PartnerApiKeyFilter filter,
        AuthenticationEntryPoint keyEntryPoint) throws Exception {
    return http
        .securityMatcher("/api/partner/**")
        .csrf(AbstractHttpConfigurer::disable)
        .sessionManagement(s -> s.sessionCreationPolicy(STATELESS))
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .exceptionHandling(e -> e.authenticationEntryPoint(keyEntryPoint))
        .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)
        .build();
}
```

Đây là **chain bổ sung** cho mục 8: `@Order(0)` bảo đảm `/api/partner/**` được xét trước chain legacy (1) và Bearer (2). Không auto-register filter **hai lần** qua Servlet và Spring Security; kiểm tra số lần được gọi.

Nếu áp dụng `401` cho API key custom header, `keyEntryPoint` cần công bố cách challenge phù hợp với scheme do API định nghĩa; `WWW-Authenticate: ApiKey realm="partners"` chỉ là **scheme riêng** không có hỗ trợ phổ quát, phải tài liệu hóa. Không phát challenge Bearer cho một API key chỉ được gửi qua `X-API-Key`. Nếu chỉ báo không đủ quyền với key đã xác thực, dùng 403 và Problem Details theo hợp đồng.

### 9.1. Không xây API key bằng cách so chuỗi cố định

Mẫu không an toàn:

```java
if ("super-secret-123".equals(request.getHeader("X-API-Key"))) {
    // allow everything
}
```

Đây là key chung khó rotate, không phân quyền tenant, không audit/expiry/quota. Dùng định danh key, registry/hash và authority được ánh xạ, áp rate limiting theo key/principal/tenant. Secret phải đến từ hệ thống quản trị an toàn.

## 10. OpenAPI 3.1: mô tả từng cơ chế đúng schema

### 10.1. Khai báo securitySchemes

```yaml
openapi: 3.1.2
info:
  title: Orders Integration API
  version: 1.0.0
paths:
  /api/partner/orders:
    get:
      security:
        - partnerKey: []
      responses:
        "200": {description: Danh sách đơn thuộc đối tác}
        "401": {description: API key không hợp lệ theo hợp đồng}
        "403": {description: Không đủ quyền}
  /api/legacy/reports:
    get:
      security:
        - legacyBasic: []
      responses:
        "200": {description: Dữ liệu báo cáo}
        "401": {description: Basic challenge}
  /api/orders/{id}:
    get:
      security:
        - bearerAuth: []
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        "200": {description: Đơn hàng trong phạm vi được phép}
        "401": {description: Bearer token thiếu hoặc không hợp lệ}
        "403": {description: Không đủ quyền}
components:
  securitySchemes:
    partnerKey:
      type: apiKey
      in: header
      name: X-API-Key
    legacyBasic:
      type: http
      scheme: basic
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

`bearerFormat: JWT` là **hint tài liệu**, không buộc token phải là JWT hay tự xác minh chữ ký. Không ghi bí mật thật vào `example` hoặc sample curl công khai.

### 10.2. OAuth scopes phải khai theo OAuth scheme

Với HTTP Bearer scheme thuần, requirement `bearerAuth: []` là đúng; **không điền `[orders.read]` cho HTTP security scheme** để ngầm mô tả OAuth scopes. Nếu endpoint cần scopes OAuth và tài liệu hóa OAuth flow, định nghĩa riêng:

```yaml
components:
  securitySchemes:
    oauth2Client:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://id.example.com/oauth2/token
          scopes:
            orders.read: Đọc đơn hàng được phép
            orders.write: Tạo/cập nhật đơn hàng được phép
```

Operation:

```yaml
security:
  - oauth2Client: [orders.read]
```

Đây là **mô tả** OAuth Client Credentials; không có nghĩa backend tự cấp token hoặc chấp nhận `orders.read` mà không kiểm tra tenant. Khi endpoint có nhiều phương án authentication, phân biệt:

- `security: [{partnerKey: []}, {oauth2Client: [orders.read]}]` = **OR**.
- `security: [{partnerKey: [], oauth2Client: [orders.read]}]` = **AND**.

Không bật OR chỉ để tiện test nếu một trong các phương án yếu hơn sẽ mở đường vượt policy. Giữ security requirements khớp Spring SecurityFilterChain thực sự.

## 11. Threat model: có credential chưa đủ để an toàn

| Nguy cơ | Biện pháp |
|---|---|
| Key/token/password vào URL, logs, analytics | HTTPS, headers, redact logs/proxy/APM, secrets manager |
| Key/password dài hạn bị lộ | Quyền hẹp, expiry, rotation/revoke, audit/rate limit |
| JWT giả hoặc token của API khác | Validate alg/signature/issuer/audience/time và JWKS |
| Token bị copy/replay | TTL ngắn, thu hồi; sender-constrained nếu cần |
| Scope đúng nhưng tenant khác | Object-level authorization, tenant-scoped query |
| Client credential bị redirect sang host khác | Không forward Authorization cross-origin |
| Basic/key brute force | Rate limit, detection, lockout chính sách |
| Browser dùng cookie | CSRF, SameSite, CORS, XSS defense phù hợp |
| Shared CDN trả dữ liệu người khác | `private/no-store`, integration test cache |

**CORS không phải authentication**; curl có key lộ vẫn gọi được. TLS không sửa lỗi lộ token trong localStorage do XSS hoặc trong application logs. Authenticator và authorization phải được kiểm tra độc lập.

## 12. Kiểm thử HTTP và Spring Security

### 12.1. Ma trận test tối thiểu

| Test | Request | Kỳ vọng |
|---|---|---|
| AUTH-01 | Không gửi Authorization vào Bearer route | 401 + `WWW-Authenticate: Bearer` |
| AUTH-02 | Bearer sai chữ ký, hết hạn hoặc sai audience | 401, không vào service |
| AUTH-03 | Token thiếu `orders.read` hoặc đọc sai tenant | 403/404, không lộ dữ liệu |
| AUTH-04 | Token đủ quyền và đúng tenant | 200 + JSON, cache policy phù hợp |
| AUTH-05 | Basic thiếu/sai password hoặc gửi nhầm vào Bearer route | 401 + đúng challenge, không cho qua |
| AUTH-06 | API key thiếu/sai/revoked hoặc thiếu quyền | Lỗi theo contract; quyền thiếu → 403 |
| AUTH-07 | Rotate hai key cùng đối tác | Cùng dùng ngắn hạn, key cũ bị chặn sau revoke |
| AUTH-08 | Brute force key/password | Rate limit, audit, không tiết lộ credential đúng/sai chi tiết |
| AUTH-09 | CDN và browser | Không cache sai tenant; CORS/CSRF đúng policy |

### 12.2. MockMvc cho Bearer JWT

Ví dụ sử dụng `spring-security-test` để kiểm tra **authorization rules** trong application:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAuthorizationTest {
    @Autowired MockMvc mvc;

    @Test
    void missingCredentialIs401() throws Exception {
        mvc.perform(get("/api/orders/ord-501"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Bearer")));
    }

    @Test
    void tokenWithoutReadScopeIs403() throws Exception {
        mvc.perform(get("/api/orders/ord-501")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void permittedScopeCanReadVisibleOrder() throws Exception {
        mvc.perform(get("/api/orders/ord-501")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("ord-501"));
    }
}
```

Đây là **test minh họa**, chưa chạy trong project. Cần import MockMvc/JUnit/spring-security-test static `SecurityMockMvcRequestPostProcessors.jwt`, cấu hình principal/tenant trong fixture, database và `OrderService` tương ứng.

**Ranh giới rất quan trọng:** `jwt()` trong MockMvc **mô phỏng một Authentication hợp lệ**, không kiểm chứng JWT chữ ký, issuer, audience hay JWK. Phải bổ sung integration tests gửi HTTP với token **thật được ký bởi key test**, đảm bảo token giả/chữ ký sai/sai aud/sai exp bị resource server từ chối.

### 12.3. Test API key và Basic thực tế

Với API key, test filter/provider theo scope route đã đăng ký:

```java
mvc.perform(get("/api/partner/orders")
        .header("X-API-Key", testKeyValid))
    .andExpect(status().isOk());

mvc.perform(get("/api/partner/orders")
        .header("X-API-Key", testKeyRevoked))
    .andExpect(status().isUnauthorized()); // Nếu contract chọn 401.
```

Với Basic, dùng encoder/fixture riêng và kiểm tra `WWW-Authenticate: Basic`:

```java
mvc.perform(get("/api/legacy/reports")
        .with(httpBasic("legacy-service", "wrong-password")))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(HttpHeaders.WWW_AUTHENTICATE,
            containsString("Basic")));
```

Test phải đi qua SecurityFilterChain thực, kiểm tra filter API key không bị auto-register hai lần, route không bị overlap và không nhầm Basic thành Bearer. Với mTLS/proxy, thêm HTTP integration test qua đường đi production giống thực tế.

## 13. Bài tập thực hành

### A — Chọn scheme có lý do

Chọn cơ chế cho **batch job nội bộ** ít thao tác, **service legacy** đang dùng Basic có kế hoạch migration, và **SaaS third-party** cần user consent + scopes. Với mỗi trường hợp, nêu TTL, revoke/rotation, tenant authorization và điều kiện bảo mật browser.

### B — Trả HTTP đúng

Viết status/header/body cho: Bearer thiếu, Bearer hết hạn, Bearer thiếu `orders.read`, scope đúng nhưng tenant khác, Basic sai password và API key revoked. Nêu khi nào phải có `WWW-Authenticate` và vì sao không dùng `200 {"success":false}`.

### C — Spring và tests

Thiết kế route `/api/partner/**` dùng API key, `/api/legacy/**` dùng Basic, `/api/orders/**` dùng JWT Bearer; viết ít nhất tám tests về precedence, sai scheme, key rotation, scope, audience, tenant isolation. Bổ sung **test JWT có chữ ký thật**; `jwt()` trong MockMvc không test cryptographic validation.

### D — Điều tra lộ credential

Một key xuất hiện trong proxy logs và token SPA bị đánh cắp qua XSS. Xây kế hoạch revoke/rotate, quota/rate limit, log redaction, BFF khi phù hợp và thông báo client. Phân biệt bảo vệ **trên đường truyền** với bảo vệ **khi secret đã bị lộ**.

## 14. Checklist trước phát hành

- [ ] Xác định principal là app/client hay user; AuthN khác AuthZ theo resource/tenant.
- [ ] TLS bắt buộc; không gửi secrets trong URL, code, logs hoặc ví dụ public.
- [ ] API key đủ entropy, key ID, digest/HMAC, permissions/quota, expiry/revoke, rotation.
- [ ] Basic chỉ dùng trong vùng giới hạn, password encoder/challenge đúng, tránh shared account.
- [ ] Bearer kiểm tra signature, alg, iss, aud, exp/nbf và scopes; opaque introspection an toàn.
- [ ] Không nhầm ID token và access token; không gửi refresh token tới resource server.
- [ ] 401 có `WWW-Authenticate` phù hợp; 403 cho thiếu quyền; Problem Details không lộ bí mật.
- [ ] Spring chains có matcher/order rõ; API key filter không auto-register hai lần.
- [ ] CSRF/CORS, browser storage và cache dữ liệu private theo threat model.
- [ ] MockMvc kiểm thử status/headers/quyền; integration tests JWT validation/tenant/key revoke.

## 15. Ghi nhớ

**API key** phù hợp nhận diện tích hợp đơn giản khi có quota, rotation và quyền hẹp. **HTTP Basic** là cơ chế HTTP tiêu chuẩn nhưng gửi lại password được biểu diễn bằng Base64, nên chủ yếu phù hợp hệ thống legacy qua TLS. **Bearer access token** linh hoạt với OAuth 2.0/OIDC, scope và TTL, nhưng token bị đánh cắp vẫn có thể bị sử dụng lại; JWT cần kiểm tra chữ ký/claims đúng, opaque token cần introspection.

Cả ba trả lời được một phần câu hỏi **“ai gọi API?”**, không tự trả lời đầy đủ **“có được thao tác trên đơn hàng này không?”**. Chất lượng xác thực REST API nằm ở ranh giới tin cậy, quy trình secret/token lifecycle, challenge HTTP đúng, authorization theo tenant/resource và bằng chứng từ các test tích hợp chứ không chỉ ở tên header.
