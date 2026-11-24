# Không cấp quyền từ claim chưa được xác minh trong Spring Security

## 1. Vấn đề: một claim chứa quyền không đồng nghĩa người gọi có quyền

Xét một API đơn hàng nhận Bearer access token. Client gửi một chuỗi trông giống JWT, trong đó có thông tin:

~~~json
{
  "sub": "user-123",
  "scope": "orders:read orders:write",
  "roles": ["ADMIN"]
}
~~~

Nếu backend chỉ giải mã Base64 phần payload rồi tạo `GrantedAuthority("ROLE_ADMIN")` hoặc `GrantedAuthority("SCOPE_orders:write")`, người gửi có thể tự tạo một chuỗi khác với scope/role cao hơn và giả mạo quyền truy cập. **Đọc được claim không chứng minh claim được cấp bởi nguồn đáng tin.**

Trong Spring Security, nguyên tắc cơ bản là:

> **Chỉ tạo quyền dùng để phân quyền từ dữ liệu đã đi qua quy trình xác thực token đầy đủ, đúng issuer, đúng audience, đúng loại token và đúng chính sách của tài nguyên. Sau đó vẫn phải kiểm quyền trên hành động và đối tượng dữ liệu.**

Bài học thuộc chương **Spring Security authorities** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, có phạm vi tìm hiểu mô hình tin cậy và vòng đời token, JWT/opaque token, access token/refresh token, OAuth 2.0/OpenID Connect (OIDC), kiểm tra claims/scope/audience, thu hồi token và chống token bị đánh cắp hoặc phát lại.

Các ví dụ tập trung vào **Spring Security 6, Spring Boot 3, Java và OAuth 2.0 Resource Server dùng Servlet**. Một vài extension point và chính sách token có thể khác theo phiên bản hoặc Authorization Server; triển khai thực tế cần đối chiếu hợp đồng của issuer.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **parse/decode**, **verify** và **authorize**.
2. Liệt kê những bước cần kiểm tra trước khi sử dụng JWT claims để tạo `Authentication` và `GrantedAuthority`.
3. Nhận biết claim có chữ ký hợp lệ nhưng **không phù hợp để cấp quyền** do audience, mục đích, nguồn dữ liệu hoặc semantics sai.
4. Cấu hình `JwtDecoder`, validators, `JwtAuthenticationConverter` và rule `hasAuthority` đúng ranh giới trách nhiệm.
5. Phân biệt xác thực JWT và introspection opaque token; không dùng ID token/refresh token làm access token.
6. Phân tích rủi ro cấp quyền nhầm qua header gateway, dữ liệu client tự khai, multi-issuer, tenant và cache.
7. Kiểm thử riêng quá trình xác thực token, ánh xạ authority và phân quyền trên tài nguyên cụ thể.

## 2. Ba bước khác nhau: decode, verify và authorize

| Bước | Câu hỏi | Ví dụ | Nếu bỏ qua |
|---|---|---|---|
| **Decode/parse** | Chuỗi có thể đọc thành header/payload không? | Base64URL decode JWT để lấy `scope`. | Chỉ có dữ liệu do người gửi cung cấp; **chưa có bằng chứng tin cậy**. |
| **Verify/validate** | Token có được issuer được phép phát hành, còn hiệu lực và dành cho API này không? | Kiểm chữ ký, thuật toán, key, `iss`, `exp`, `nbf`, `aud`, token purpose, revocation nếu cần. | Có thể chấp nhận token giả, hết hạn hoặc cấp cho dịch vụ khác. |
| **Authorize** | Caller đã xác thực được phép gọi thao tác và đối tượng cụ thể không? | Kiểm `SCOPE_orders:read` và owner/tenant của đơn hàng. | Người có token hợp lệ có thể đọc dữ liệu ngoài phạm vi được cấp. |

**JWT được mã hóa Base64URL để mang dữ liệu, không phải được bảo vệ bằng Base64URL.** Với JWT ký (JWS), chữ ký cùng quy tắc khóa/thuật toán mới giúp phát hiện chỉnh sửa token. Đối với JWT mã hóa (JWE) hoặc nested JWT, ứng dụng phải dùng pipeline giải mã/xác thực đúng kiểu token; không tự suy ra độ tin cậy từ việc parse ra JSON.

~~~mermaid
flowchart TD
    A[Nhận Bearer token] --> B{Đúng định dạng và cơ chế xác thực?}
    B -- Không --> U[401: token không hợp lệ]
    B -- Có --> C{Chữ ký / introspection và issuer đáng tin?}
    C -- Không --> U
    C -- Có --> D{Hạn dùng, audience và mục đích hợp lệ?}
    D -- Không --> U
    D -- Có --> E[Ánh xạ claims được tin cậy thành GrantedAuthority]
    E --> F[Authentication trong SecurityContext]
    F --> G{Authority phù hợp hành động?}
    G -- Không --> H[403: thiếu quyền]
    G -- Có --> I{Ownership, tenant, business policy hợp lệ?}
    I -- Không --> J[403 hoặc 404 theo chính sách]
    I -- Có --> K[Thực hiện nghiệp vụ]
~~~

Một lỗi trong bước **xác thực** thường cần trả 401; thiếu quyền sau xác thực thường là 403. Quyết định dùng 404 để không lộ sự tồn tại tài nguyên thuộc chính sách nghiệp vụ, không thay thế việc kiểm quyền.

## 3. Ví dụ phản diện: cấp quyền từ payload chưa xác minh

Đoạn sau minh họa một **anti-pattern**, không dùng trong production:

~~~java
// SAI: mã minh họa lỗi, không sử dụng trong hệ thống thật.
String token = authorizationHeader.substring("Bearer ".length());
String payload = token.split("\\.")[1];
String json = new String(
    Base64.getUrlDecoder().decode(payload),
    StandardCharsets.UTF_8
);

// Giả sử parse json và lấy claim roles do người gửi tự cung cấp.
List<GrantedAuthority> granted = List.of(
    new SimpleGrantedAuthority("ROLE_ADMIN")
);
Authentication auth = new UsernamePasswordAuthenticationToken(
    "user-123", null, granted
);
SecurityContextHolder.getContext().setAuthentication(auth);
~~~

Đoạn mã không hề biết chuỗi token có bị sửa không, chữ ký hợp lệ không, ai phát hành, dành cho API nào hay đã hết hạn chưa. Kẻ tấn công có thể tạo payload giống `{"roles":["ADMIN"]}` mà không cần được Authorization Server cấp quyền.

**Đặc biệt nguy hiểm:** constructor `UsernamePasswordAuthenticationToken(principal, credentials, authorities)` tạo authentication được coi là đã xác thực trong nhiều luồng xử lý. Đặt nó vào `SecurityContextHolder` dựa trên claim chưa kiểm tra là tự cấp quyền cho dữ liệu đầu vào không đáng tin.

Đừng dùng các phương pháp như sau để xác minh quyền:

- `Base64.getUrlDecoder()` rồi parse JSON thủ công.
- Phương thức chỉ đọc claims của thư viện JWT mà **không xác minh signature**.
- Lấy `sub`, `scope`, `roles`, `tenant_id` trực tiếp từ query string/body/header request.
- Đọc `Authorization` bằng regex rồi gán `SecurityContextHolder` mà bỏ qua `AuthenticationProvider` và validators.
- Tin vào JWT trên chỉ vì trình duyệt đã “đăng nhập” hoặc một endpoint public trước đó trả thành công.

Có thể parse JWT để làm **telemetry không nhạy cảm** hoặc định tuyến sơ bộ nếu kiến trúc yêu cầu, nhưng kết quả đó vẫn phải được coi là **untrusted** cho tới khi verify. Thông tin đọc trước xác thực tuyệt đối không được làm căn cứ cấp quyền hoặc chọn khóa/issuer không qua allowlist.

## 4. Những điều kiện làm claim trở nên đáng tin cậy cho một Resource Server

Một JWT có chữ ký hợp lệ **chưa đủ** để lấy mọi claim làm quyền. Resource Server cần xác định rõ hợp đồng tin cậy với từng issuer.

### 4.1. Chữ ký, khóa và thuật toán phải được kiểm soát

- Chấp nhận **đúng các thuật toán được cho phép** và khóa đáng tin cho issuer; không để header `alg` tự quyết định một thuật toán ngoài allowlist.
- Lấy JWK từ JWKS endpoint đã cấu hình/đã khám phá theo issuer tin cậy, không tùy tiện đi đến địa chỉ `jku`, `x5u` do token tự đề xuất.
- `kid` chỉ là gợi ý chọn khóa **bên trong tập khóa tin cậy**, không phải bằng chứng rằng khóa hoặc issuer đã an toàn.
- Không chấp nhận `alg=none` cho access token có yêu cầu chữ ký; chống nhầm khóa đối xứng/bất đối xứng khi cấu hình thư viện.
- Hỗ trợ key rotation theo chính sách; khi cache JWKS, vẫn giữ giới hạn issuer và thuật toán được phép.

**Lưu ý:** xác minh signature chứng minh token được ký bởi khóa tin cậy trong phạm vi cấu hình, không tự chứng minh mọi trường trong token có ý nghĩa cấp quyền cho ứng dụng của bạn.

### 4.2. Issuer phải được chấp nhận

Claim `iss` chỉ có ý nghĩa khi được kiểm tra với Authorization Server mà Resource Server tin cậy. Token được ký bởi **issuer B** không được cấp quyền của **issuer A** chỉ vì có cùng `sub` hay `scope`.

Trong hệ thống nhiều issuer, cần chính sách theo từng issuer về JWKS, audience, claim mapping và semantics của role. Tuyệt đối không nhận mọi issuer do token tự nêu mà không có allowlist hoặc trust configuration rõ ràng.

### 4.3. Audience phải đúng tài nguyên

Ví dụ một Authorization Server phát token:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["catalog-api"],
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

Dù signature và `scope` đúng cú pháp, **`orders-api` không được dùng token dành cho `catalog-api`**. Resource Server phải kiểm `aud` theo API, tránh token bị sử dụng chéo tài nguyên (cross-resource token substitution).

`scope` không thể sửa chữa `aud` sai. Việc gán `SCOPE_orders:read` từ token sai audience có thể gây nhầm lẫn trong mã hoặc policy. Hãy từ chối token ở bước xác thực, trước khi phân quyền.

### 4.4. Thời hạn, thời điểm có hiệu lực và trạng thái thu hồi

- `exp` xác định thời điểm token hết hạn; không chấp nhận token đã hết hạn ngoài độ lệch đồng hồ được cho phép.
- `nbf` xác định thời điểm token bắt đầu có hiệu lực; cũng cần áp dụng quy tắc clock skew hợp lý.
- `iat` có thể phục vụ chính sách tuổi token; không tự suy ra token còn được phép nếu thiếu `exp` hoặc thời hạn do hệ thống quy định.
- JWT xác thực offline không tự phát hiện **token đã bị thu hồi**; nếu yêu cầu thu hồi sớm, cần session version, denylist, introspection hoặc giải pháp khác phù hợp.
- Access token bị đánh cắp có thể bị phát lại khi còn hiệu lực; scope/role prefix không chống replay. Bảo vệ token trong client, dùng TTL ngắn và sender-constrained token như DPoP/mTLS khi phù hợp.

### 4.5. Đúng loại token và mục đích sử dụng

OAuth access token dành cho Resource Server phải được phân biệt với:

| Loại | Mục đích chính | Có nên dùng làm Bearer access token của API? |
|---|---|---|
| **Access token** | Client truy cập tài nguyên theo scope/audience được cấp. | Có, sau khi qua validation phù hợp. |
| **Refresh token** | Client xin access token mới tại token endpoint của Authorization Server. | Không. |
| **OIDC ID token** | Client nhận thông tin về kết quả xác thực người dùng. | Không mặc nhiên; thường không dành cho Resource Server. |
| **JWT của nghiệp vụ khác** | Vé nội bộ, email verification, reset password, v.v. | Không, trừ khi có một giao thức xác thực riêng rõ ràng và đúng purpose. |

Nếu issuer dùng `typ: at+jwt` theo JWT Access Token Profile hoặc claim `token_use: access` theo hợp đồng riêng, cấu hình xác minh tương ứng. Không phải mọi Authorization Server dùng cùng tên trường. Điều quan trọng là **API chỉ chấp nhận token đúng mục đích**, không lấy token bất kỳ có chữ ký đúng để tạo `GrantedAuthority`.

### 4.6. Claim được ký vẫn có thể không đủ thẩm quyền

Đây là một nhầm lẫn tinh vi. Một Authorization Server có thể đưa vào JWT các trường người dùng tự sửa như `display_name`, `nickname`, `department_note` hoặc một số metadata đến từ client. Những trường này **đã nằm trong JWT có chữ ký**, nhưng không nhất thiết là nguồn sự thật cho role/permission.

Để biến `roles`, `permissions` hoặc `tenant_id` thành authority, cần trả lời:

1. Ai tạo và kiểm soát giá trị claim? Người dùng có tự chỉnh được không?
2. Issuer có bảo đảm claim thuộc **đúng audience và đúng domain quyền** không?
3. Claim được cập nhật/tái xác nhận như thế nào nếu quyền người dùng bị thu hồi?
4. Claim là thông tin hồ sơ hay quyết định được phép thực hiện hành động?
5. Nếu có nhiều tenant/issuer, giá trị claim được gắn với namespace nào?

Một claim signed nhưng được sinh từ dữ liệu tự khai vẫn có thể gây **privilege escalation** nếu được coi là vai trò do quản trị viên cấp.

## 5. Spring Security đặt ranh giới tin cậy ở đâu?

Với ứng dụng Servlet dùng Spring Security OAuth 2.0 Resource Server, đường xử lý phổ biến:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant P as AuthenticationManager / JwtAuthenticationProvider
    participant D as JwtDecoder + validators
    participant M as JwtAuthenticationConverter
    participant X as SecurityContextHolder
    participant A as AuthorizationFilter / Method Security
    participant R as Controller / Service

    C->>F: Authorization: Bearer token
    F->>P: Yêu cầu xác thực
    P->>D: Decode + verify chữ ký + validate claims
    alt Token không hợp lệ
        D-->>P: JwtException / invalid token
        P-->>F: Xác thực thất bại
        F-->>C: 401
    else Token hợp lệ
        D-->>P: Jwt đã xác minh
        P->>M: convert(jwt)
        M-->>P: JwtAuthenticationToken + GrantedAuthorities
        P-->>F: Authentication đã xác thực
        F->>X: Lưu Authentication trong SecurityContext
        F->>A: Tiếp tục request
        A->>X: Đọc authorities
        alt Đủ quyền
            A->>R: Thực thi, còn kiểm nghiệp vụ
        else Thiếu quyền
            A-->>C: 403
        end
    end
~~~

Trong kiến trúc mặc định:

- `JwtDecoder` xử lý xác minh signature và validator token theo cấu hình.
- `JwtAuthenticationProvider` chỉ dùng `JwtAuthenticationConverter` sau khi decoder trả về `Jwt` hợp lệ.
- `JwtGrantedAuthoritiesConverter` thường ánh xạ `scope` hoặc `scp` của JWT đã xác minh thành authority có tiền tố `SCOPE_`.
- `JwtAuthenticationToken` được đưa vào `SecurityContext` cho request hiện tại; method security và controller có thể dựa vào authorities đó.
- Khi request kết thúc, security context được dọn đúng vòng đời; không dùng nó làm biến toàn cục hay cache xác thực cho request sau.

**Quy tắc quan trọng:** Converter chỉ ánh xạ quyền; **converter không chịu trách nhiệm làm token trở nên đáng tin**. Để code chạy đúng, phải đảm bảo decoder và validators được cấu hình trước khi dùng kết quả converter.

## 6. Ví dụ cấu hình Resource Server: xác thực trước, ánh xạ sau

Giả sử `orders-api` tin một issuer và chỉ nhận JWT access token có audience `orders-api`.

### 6.1. Cấu hình filter chain

~~~java
@Configuration
@EnableMethodSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(sm -> sm
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Ví dụ giả định API chỉ xác thực bằng **Bearer token trong header**, không dựa vào cookie/session do browser tự gửi. Vì vậy phần ví dụ tắt CSRF; với ứng dụng dùng cookie hoặc credential được browser tự đính kèm, phải cấu hình chống CSRF phù hợp, không sao chép `csrf.disable()`.

`SessionCreationPolicy.STATELESS` không có nghĩa request không có `SecurityContext`; context vẫn tồn tại trong quá trình xử lý request. Nó cho biết API không dùng HTTP session làm cách nhớ trạng thái xác thực cho những request tiếp theo.

### 6.2. JWT decoder kết hợp issuer, audience và thời hạn

~~~java
@Bean
JwtDecoder jwtDecoder() {
    // Ba giá trị này phải đến từ cấu hình triển khai được kiểm soát.
    String trustedIssuer = "https://auth.example.test";
    String trustedJwkSetUri = "https://auth.example.test/oauth2/jwks";
    String requiredAudience = "orders-api";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(trustedJwkSetUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    // Kiểm tra tiêu chuẩn, gồm issuer và điều kiện thời gian token.
    OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(trustedIssuer);

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        List<String> audiences = jwt.getAudience();
        if (audiences != null && audiences.contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Audience not accepted by orders-api",
                null));
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            defaults, audienceValidator));

    return decoder;
}
~~~

Các import được lược bỏ: `JwtDecoder`, `NimbusJwtDecoder`, `SignatureAlgorithm`, `Jwt`, `JwtValidators`, `OAuth2TokenValidator`, `OAuth2TokenValidatorResult`, `DelegatingOAuth2TokenValidator`, `OAuth2Error` và Spring `@Bean`.

Trong triển khai thật, thay chuỗi ví dụ bằng cấu hình tin cậy tại môi trường; dùng JWKS URI thuộc issuer đã được xác minh, thuật toán đúng hợp đồng và cơ chế key rotation phù hợp. Nếu issuer cho phép nhiều thuật toán, chỉ thêm từng thuật toán **đã thỏa thuận và đánh giá** vào allowlist. Không đọc JWKS URI tùy ý từ `jku` trong JWT hoặc từ request của client.

`JwtValidators.createDefaultWithIssuer` kết hợp các kiểm tra tiêu chuẩn và issuer. Validator audience được **kết hợp** với các điều kiện đó; không vô ý thay thế toàn bộ validator mặc định chỉ bằng phép kiểm audience. Ví dụ này cũng từ chối khi không có audience phù hợp. Nếu hợp đồng hệ thống **bắt buộc phải có** `exp`, `nbf`, token type, `token_use`, `client_id`/`azp`, `jti` hoặc kiểm thu hồi, hãy bổ sung validator rõ ràng cho các điều kiện bắt buộc đó trước khi xem token đủ tin cậy; không mặc nhiên suy ra mọi claim đều đã được yêu cầu có mặt chỉ từ validator mặc định.

### 6.3. Chỉ dùng authorities đã được tạo qua pipeline xác thực

~~~java
@RestController
@RequestMapping("/api")
public class OrderController {

    @GetMapping("/orders")
    public List<OrderSummary> listOrders(
            JwtAuthenticationToken authentication) {

        // authentication do Spring Security tạo trong request đã xác thực.
        String subject = authentication.getToken().getSubject();

        boolean canRead = authentication.getAuthorities().stream()
            .anyMatch(a ->
                "SCOPE_orders:read".equals(a.getAuthority()));

        if (!canRead) {
            throw new AccessDeniedException("Insufficient scope");
        }

        // Chỉ trả các đơn hàng mà subject này được phép nhìn thấy.
        return orderService.findVisibleOrders(subject);
    }
}
~~~

Đoạn mã minh họa; `orderService` và `OrderSummary` là thành phần nghiệp vụ do ứng dụng định nghĩa, cần inject tương ứng. Với API thật, quyền thường nên kiểm ở filter chain, method security và policy service theo kiến trúc, tránh lặp logic; phần kiểm trong controller giúp thấy rõ dữ liệu phải lấy từ `JwtAuthenticationToken`, **không lấy từ header tự khai**.

Nếu Resource Server hỗ trợ nhiều issuer, đừng coi mỗi `sub` là duy nhất trên toàn hệ thống; mô hình subject thường cần namespace theo `(issuer, subject)`. Quan trọng hơn, `findVisibleOrders` cần thực thi kiểm ownership/tenant ở tầng dữ liệu theo actor đã chuẩn hóa.

## 7. Custom role converter: có chữ ký vẫn cần đúng semantics

Spring Security JWT Resource Server thông thường chuyển `scope`/`scp` thành `SCOPE_...`. Claim `roles` hoặc `permissions` không tự trở thành `ROLE_...` hay `PERM_...`. Nếu muốn ánh xạ role tùy chỉnh, phải biết **nguồn cấp role và quyền quản trị của claim**.

Giả sử hợp đồng với Authorization Server quy định:

- Issuer đáng tin phát JWT cho `orders-api`, không cho user/client tự sửa claim `app_roles`.
- `app_roles` là những role **của chính orders-api** và chỉ có `SUPPORT` hoặc `OPS`.
- Các giá trị nằm ngoài allowlist sẽ không được cấp authority quản trị.
- Nếu role bị thu hồi, có cơ chế TTL/revocation phù hợp mức bảo đảm.

Có thể định nghĩa converter:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(jwt -> {
        Set<GrantedAuthority> granted =
            new HashSet<>(scopes.convert(jwt));

        Object rawRoles = jwt.getClaims().get("app_roles");

        if (rawRoles instanceof Collection<?> roles) {
            for (Object role : roles) {
                if ("SUPPORT".equals(role) || "OPS".equals(role)) {
                    granted.add(new SimpleGrantedAuthority(
                        "ROLE_" + role));
                }
            }
        }

        return granted;
    });

    return converter;
}
~~~

Và trong cấu hình JWT thay dòng mặc định bằng:

~~~java
.oauth2ResourceServer(oauth -> oauth
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(jwtAuthenticationConverter())))
~~~

Các import liên quan là `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter`, `GrantedAuthority`, `SimpleGrantedAuthority`, `Set`, `HashSet` và `Collection`. Đây là mẫu ánh xạ **sau khi decoder xác thực JWT**; nó không phải bộ kiểm chữ ký.

**Điều kiện tiên quyết:** claim `app_roles` phải thực sự thuộc quyền kiểm soát của issuer và được định nghĩa cho audience này. Nếu user có thể sửa một trường profile tên `app_roles` rồi Authorization Server ký lại vào JWT, converter trên vẫn tạo `ROLE_SUPPORT`/`ROLE_OPS` từ dữ liệu tự khai. Khi đó phải sửa **nguồn cấp claim**, policy quản lý role hoặc lấy quyền từ hệ thống đáng tin khác, chứ không chỉ thêm allowlist.

Trong hệ thống có nhiều issuer, nên phân tách converter và policy theo issuer/tenant hoặc tạo actor đã chuẩn hóa; không áp dụng một claim role của issuer A cho issuer B nếu chưa có trust mapping rõ ràng.

### Vấn đề chữ hoa và role namespace

`hasRole("SUPPORT")` theo quy ước thông thường kiểm `ROLE_SUPPORT`. Trong khi đó `hasAuthority("SCOPE_orders:read")` kiểm chính xác scope authority. Không tự động coi `SCOPE_admin` tương đương `ROLE_ADMIN`. Hai nguồn quyền này có semantics khác nhau.

Nếu có role `ADMIN` trong ứng dụng tài chính, role đó không tự dùng được trong ứng dụng đơn hàng. Token cần đúng audience và phép ánh xạ chỉ những role được chấp nhận trong Resource Server này.

## 8. Opaque access token: tránh nhầm kết quả introspection

Với opaque token, Resource Server không giải mã JWT claims. Thay vào đó, nó gửi token tới **introspection endpoint đáng tin** của Authorization Server và nhận metadata theo RFC 7662 hoặc hợp đồng hệ thống.

Ví dụ phản hồi minh họa:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "client_id": "web-portal",
  "sub": "user-123",
  "scope": "orders:read",
  "aud": ["orders-api"],
  "exp": 1893456000
}
~~~

Trong Spring Security, `OpaqueTokenIntrospector` và provider tương ứng xác thực token/metadata để tạo `BearerTokenAuthentication`, và các scope thường được chuyển thành `SCOPE_...`. Tuy nhiên, không coi `active=true` là bằng chứng đủ cho tất cả ứng dụng:

- Chỉ gọi introspection endpoint **đã cấu hình từ nguồn tin cậy** qua TLS, dùng client authentication phù hợp.
- Xác định response đã được Authorization Server đáng tin cung cấp, không nhận “introspection” JSON do client tự gửi.
- Kiểm token có đúng API, client/purpose/issuer và audience theo hợp đồng. Response introspection không phải lúc nào cũng chứa mọi claim, nên phải định nghĩa policy rõ ràng; khi thiếu điều kiện bắt buộc, nên từ chối.
- Tính toán cache introspection so với mức yêu cầu phát hiện token bị thu hồi. Cache quá lâu làm token đã revoke có thể vẫn được chấp nhận đến khi cache hết hạn.
- Không chuyển arbitrary metadata thành role quản trị nếu nguồn đó không có quyền quyết định permission.

JWT và opaque token là **cách biểu diễn access token**. Dù loại nào, Resource Server chỉ dùng thông tin đã được xác thực và có ngữ nghĩa thích hợp để tạo authorities.

## 9. Nguồn claim giả và việc truyền danh tính qua gateway

Một API gateway có thể xác thực token, rồi chuyển thông tin user/role xuống backend bằng header. Đây là mẫu kiến trúc hợp lệ **chỉ khi backend tin được gateway và bảo vệ đường truyền**.

Ví dụ request trực tiếp từ internet:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.internal.example
X-User-Id: admin
X-User-Roles: ADMIN
X-Authenticated-Scope: orders:write
~~~

Những header này chỉ là dữ liệu HTTP mà client có thể tự gửi. **Backend không được biến `X-User-Roles: ADMIN` thành `ROLE_ADMIN` trừ khi gateway/proxy đã xác thực và có ranh giới truyền dữ liệu đáng tin.**

Yêu cầu khi hệ thống chọn mô hình gateway làm nơi xác thực:

1. Không cho client bên ngoài truy cập trực tiếp backend với giao diện tin header nội bộ.
2. Gateway xóa mọi header danh tính/quyền đầu vào từ internet, rồi tự tạo lại thông tin sau khi xác thực token.
3. Bảo vệ đường truyền gateway → backend (ví dụ mTLS, policy mạng, danh tính workload) và kiểm tra chỉ gateway được phép gửi thông tin tin cậy.
4. Ràng buộc user, tenant, issuer và scope với request thực tế; không nhận một header “authenticated” do caller khai.
5. Quy định chính xác backend được ủy quyền tin gì ở gateway và vẫn phải kiểm business policy/ownership.
6. Nếu có yêu cầu thu hồi hoặc revocation, định nghĩa nơi kiểm và độ trễ tối đa của cache.

Phương án khác là **backend tự xác thực Bearer token** bằng Spring Security Resource Server, giảm phụ thuộc vào header danh tính tự chế. Dù chọn phương án nào, tránh cấu hình đồng thời hai nguồn quyền với mức tin cậy không rõ ràng.

### Khi Authorization Server nhận dữ liệu từ client

Một issuer có thể ký JWT chứa metadata do người dùng hoặc client khai từ trước. Chữ ký bảo vệ **tính toàn vẹn của JWT**, nhưng chưa chứng minh metadata đó được quản trị viên xác nhận. Ví dụ:

- Claim `preferred_username` tự do không nên dùng như khóa role.
- Claim `tenant_id` không mặc nhiên đủ để cho phép đọc mọi bản ghi trong tenant đó.
- Claim `groups` đồng bộ từ nguồn chưa xác thực không tự trở thành `ROLE_ADMIN`.
- Claim `scope` đã cấp cũng cần kiểm được phát hành cho **đúng client, đúng audience và chính sách consent/policy**.

Cần định nghĩa **nguồn sự thật của quyền**: Authorization Server, dịch vụ quản lý quyền có kiểm soát, hoặc policy engine; kiểm tra cách dữ liệu đi vào claim trước khi cho phép converter dùng nó.

## 10. Các tình huống tấn công và bài học

| Tình huống | Điểm yếu | Biện pháp |
|---|---|---|
| Tự sửa JWT payload từ `scope=read` thành `scope=admin` | Backend chỉ parse token. | Bắt buộc verify chữ ký và validator trước khi tạo authentication. |
| Gửi JWT có `alg=none` hoặc thuật toán không mong muốn | Thư viện/cấu hình tin header thuật toán thiếu kiểm soát. | Allowlist thuật toán và khóa từ issuer tin cậy. |
| Đưa `jku` trỏ tới JWKS của attacker | Backend lấy khóa từ URL do token đề xuất. | Chỉ dùng JWKS từ issuer/allowlist đã cấu hình. |
| Token đúng chữ ký nhưng `aud` là API khác | Thiếu kiểm audience. | Kiểm `aud` tại decoder/introspector trước khi phân quyền. |
| Dùng ID token thay access token | Nhầm loại/mục đích token. | Kiểm token type/purpose/audience theo hợp đồng issuer. |
| Claim `roles=ADMIN` có chữ ký nhưng bắt nguồn từ user profile tự chỉnh | Tin sai semantics nguồn dữ liệu. | Role phải từ nguồn quản trị quyền đáng tin, mapping có policy. |
| Gateway chuyển `X-User-Roles` do client tự gửi | Header spoofing. | Xóa/ghi đè header, xác thực gateway, khóa đường backend. |
| Token issuer B trùng `sub` với issuer A | Identity namespace mix-up. | Ánh xạ issuer + subject, trust policy theo issuer. |
| Token `SCOPE_orders:read` truy cập đơn hàng tenant khác | Thiếu kiểm business ownership. | Authorization trên đối tượng, tenant và dữ liệu thực. |
| JWT bị revoke vẫn có `exp` trong tương lai | Chỉ validate offline. | Thiết kế revocation/TTL, session version hoặc introspection. |
| Cùng Bearer token bị sao chép và phát lại | Không ràng buộc token với sender, lưu trữ lỏng lẻo. | Bảo vệ credential, TTL ngắn, sender-constrained token khi phù hợp. |
| Test giả lập authorities được coi là test signature | Test bỏ qua decoder. | Tách unit authorization tests và integration token-verification tests. |

## 11. Kiểm thử ranh giới tin cậy đúng cách

### 11.1. Test converter chỉ kiểm **mapping**, không kiểm chữ ký

~~~java
Jwt jwt = Jwt.withTokenValue("fixture-only")
    .header("alg", "RS256")
    .claim("sub", "user-123")
    .claim("scope", "orders:read")
    .build();

JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();

Collection<GrantedAuthority> authorities = converter.convert(jwt);

assertTrue(authorities.contains(
    new SimpleGrantedAuthority("SCOPE_orders:read")));
~~~

Đối tượng `Jwt` dựng thủ công **chưa qua verify**. Việc converter trả ra `SCOPE_orders:read` ở unit test không nói rằng một token mạng có `scope=orders:read` đã được xác thực. Kết quả chỉ chứng minh chức năng chuyển đổi chuỗi scope thành authority.

### 11.2. Test `jwt()` trong MockMvc cũng không chứng minh decoder

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders:read"))))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders:write"))))
    .andExpect(status().isForbidden());
~~~

Đây là ví dụ cho endpoint được fixture trả thành công khi đúng quyền và đúng ownership; cần dựng repository/service stub phù hợp. `jwt()` từ Spring Security Test đưa authentication giả lập vào test, **bỏ qua đường xác minh chữ ký/issuer/audience**. Nó phù hợp kiểm authorization rule, chưa đủ để chứng minh token validation an toàn.

### 11.3. Integration test với decoder thật

Bộ test cần một issuer/JWKS test được kiểm soát, token ký thực bằng khóa test và request đi qua filter chain. Thử:

| Test case | Kết quả mong đợi |
|---|---|
| JWT đúng chữ ký, issuer, thời hạn, audience và scope | Authentication hợp lệ; scope được map đúng; API kiểm ownership. |
| Chỉ Base64URL-decode được nhưng signature sai | 401; không tạo authentication được dùng để cấp quyền. |
| Header `alg` sai hoặc không được cho phép | 401. |
| Header `jku` chỉ tới endpoint do attacker kiểm soát | Backend không lấy khóa tùy ý; token bị từ chối nếu không khớp khóa tin cậy. |
| JWT từ issuer khác với cùng `sub` | 401 nếu issuer chưa được tin cậy; nếu multi-issuer thì policy phân vùng đúng. |
| JWT đúng chữ ký nhưng `aud=catalog-api` | 401 ở orders-api. |
| JWT hết hạn hoặc `nbf` chưa tới | 401 theo clock skew cấu hình. |
| ID token hoặc refresh token được gửi tới Resource Server | Từ chối theo token purpose/type policy. |
| JWT hợp lệ thiếu `SCOPE_orders:read` | 403 với endpoint cần scope này. |
| JWT có scope nhưng đơn hàng của user khác | 403 hoặc 404 theo chính sách. |
| JWT hợp lệ có claim `app_roles` từ nguồn không đáng tin | Không tạo authority quản trị; kiểm dữ liệu từ nguồn cấp claim. |
| Access token đã thu hồi | Kết quả đúng mức bảo đảm revocation (ngay hoặc giới hạn bằng TTL). |
| Opaque token bị introspection trả `active=false` | Không được cấp authentication. |
| Header `X-User-Roles: ADMIN` gửi trực tiếp từ client | Bị bỏ qua/từ chối theo trust boundary, không tạo role. |

Nếu logic cấp role từ claim phụ thuộc dịch vụ quyền khác, cần test cả nguồn dữ liệu và thời điểm đồng bộ quyền. Không giả lập role đã có rồi kết luận rằng **đường cấp quyền** đúng.

## 12. Quy tắc fail closed và xử lý lỗi

Một hệ thống an toàn cần xác định hành vi nếu thiếu điều kiện bắt buộc:

- Không có khóa xác minh phù hợp hoặc JWKS endpoint không truy cập được theo cơ chế cần thiết: **không tự chuyển sang chấp nhận payload unsigned**.
- Không có `aud` trong JWT khi chính sách bắt buộc audience: **từ chối token**; đừng mặc nhiên chấp nhận vì `scope` có mặt.
- Claim `roles` sai kiểu, không nằm trong allowlist hoặc đến từ issuer không được phép: **không cấp role**; có thể từ chối toàn token nếu contract yêu cầu.
- Introspection gặp lỗi mạng: không tự coi token là `active=true`.
- Token hết hạn hoặc bị revoke: không giữ `SecurityContext` cũ để bỏ qua xác thực request mới.
- Converter không lấy được scope: nên trả tập authority rỗng theo contract hoặc từ chối token nếu scope bắt buộc; không tự thêm quyền mặc định rộng.
- Kiểm phân quyền gặp lỗi policy store: từ chối thao tác nhạy cảm theo chính sách, không mặc định “allow”.

### Lỗi phản hồi và dữ liệu log

Khi token sai, API thường trả **401** và có thể có `WWW-Authenticate: Bearer` phù hợp. Khi token đã xác thực nhưng thiếu scope/permission, trả **403** theo policy. Không công bố token gốc, key, bearer credential hoặc dữ liệu nhạy cảm trong exception/log. Có thể ghi correlation ID, loại lỗi, issuer/subject đã chuẩn hóa với nguyên tắc bảo vệ dữ liệu để hỗ trợ điều tra.

**Từ chối phải có tính nhất quán:** nếu SecurityContext không có authentication hợp lệ, tầng controller/service không được có đường “fallback” lấy user ID trực tiếp từ request rồi tiếp tục thao tác.

## 13. Bài tập tình huống

### Tình huống A: JWT hợp lệ về signature nhưng sai audience

Token của client có:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "staff-21",
  "aud": ["catalog-api"],
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

`orders-api` tin cùng issuer và JWKS nhưng quên audience validation. Resource Server tạo `SCOPE_orders:read` và trả dữ liệu đơn hàng.

**Câu hỏi:** Vì sao đây là lỗi dù chữ ký đúng? Nên sửa ở decoder hay thêm `hasAuthority`? Token sai audience nên trả 401 hay 403?

**Hướng giải:** Token được cấp cho `catalog-api`, nên `orders-api` phải từ chối ở bước **xác thực** bằng kiểm `aud` (thường 401). `hasAuthority` chỉ kiểm scope sau xác thực, không cứu được token dùng sai đối tượng nhận.

### Tình huống B: role được ký nhưng người dùng tự sửa được

Authorization Server đồng bộ claim `roles` từ trang profile cho phép người dùng tự nhập giá trị. JWT được ký chuẩn và có audience đúng. API ánh xạ `roles=["ADMIN"]` thành `ROLE_ADMIN`.

**Câu hỏi:** Chữ ký có đủ để tin role này không? Khắc phục ở đâu?

**Hướng giải:** Không. Signature chứng minh **issuer đã ký**, nhưng không bảo đảm claim là kết quả quyết định quyền. Phải đổi pipeline cấp claim để lấy role từ nguồn quản trị đáng tin, kiểm soát quyền sửa và mapping tương ứng tại Resource Server.

### Tình huống C: gateway tin header từ internet

Một request gửi `X-Authenticated-User: ceo` và `X-Authenticated-Roles: ADMIN` trực tiếp tới backend. Ứng dụng tự đặt `Authentication` với `ROLE_ADMIN` mà không xác thực token.

**Câu hỏi:** Điều kiện nào cần thỏa nếu backend muốn tin dữ liệu danh tính từ gateway? Khi điều kiện không có, phải làm gì?

**Hướng giải:** Gateway phải xác thực credential, loại header do client gửi, tự tạo header đáng tin và có kênh mạng/identity giữa gateway với backend; backend không được truy cập trực tiếp hoặc phải xác thực nguồn tin. Nếu thiếu ranh giới này, bỏ qua header và tự kiểm token ở Resource Server.

### Tình huống D: token bị đánh cắp sau khi đã xác minh

Access token JWT còn hạn đã bị sao chép. Token vẫn có signature, audience và scope hợp lệ, nhưng chủ sở hữu đã logout.

**Câu hỏi:** Kiểm chữ ký và `SCOPE_` có tự vô hiệu token cũ không? Có những lựa chọn giảm rủi ro nào?

**Hướng giải:** Không. Phải có chính sách giới hạn TTL, lưu trữ/bảo vệ token, xác thực theo sender nếu phù hợp và cơ chế kiểm thu hồi/denylist/session version/introspection khi cần vô hiệu sớm.

## 14. Checklist triển khai

- [ ] Access token được lấy từ vị trí Bearer hợp lệ, không lấy identity/role từ header tùy ý.
- [ ] JWT được xác minh chữ ký bằng khóa/thuật toán thuộc allowlist và issuer tin cậy.
- [ ] Validator kiểm `iss`, thời hạn, `aud`, token type/purpose và điều kiện riêng bắt buộc.
- [ ] Opaque token được introspect tại Authorization Server tin cậy; `active` và audience/semantic được xử lý theo contract.
- [ ] `GrantedAuthority` chỉ được tạo từ claims/attributes sau xác thực và có **ngữ nghĩa cấp quyền hợp lệ**.
- [ ] Scope `SCOPE_...`, role `ROLE_...` và permission của ứng dụng có namespace và nguồn cấp rõ ràng.
- [ ] User profile hoặc dữ liệu client tự khai không thể làm role quản trị chỉ nhờ được đóng gói vào JWT.
- [ ] SecurityContext được đặt và dọn qua Spring Security; không tự tạo authenticated token từ claims unverified.
- [ ] Rule endpoint/method security kiểm scope/role; service kiểm quyền với **đối tượng và tenant cụ thể**.
- [ ] Cơ chế TTL, revocation và chống token replay phù hợp với yêu cầu an toàn.
- [ ] Unit test converter, integration test decoder/filter chain, test audience, issuer, token type và ownership đều có.
- [ ] Đường truyền gateway và các header danh tính nội bộ có trust boundary kiểm chứng được.

### Câu hỏi tự kiểm tra

1. Vì sao `Base64URL decode` một JWT không phải là xác minh JWT?
2. Một JWT có chữ ký hợp lệ từ issuer A nhưng audience dành cho API B: API C có được lấy scope làm quyền không?
3. Vì sao claim `roles=ADMIN` được ký có thể vẫn không đủ tin cậy?
4. `JwtGrantedAuthoritiesConverter` có tự xác minh JWT signature không?
5. Phân biệt 401 vì token sai và 403 vì token đã xác thực nhưng thiếu authority.
6. Vì sao `jwt()` trong Spring Security Test không đủ để chứng minh hệ thống từ chối token giả?
7. Vì sao scope hợp lệ chưa chứng minh người dùng sở hữu đơn hàng được yêu cầu?
8. Khi opaque introspection trả `active=true` nhưng không có audience bắt buộc, API nên xử lý ra sao?

**Ghi nhớ:** **Không cấp quyền từ claim chưa được xác minh.** Ngay cả sau khi xác thực chữ ký, hãy kiểm issuer, audience, mục đích sử dụng, thời hạn và semantics của từng claim trước khi ánh xạ thành `GrantedAuthority`. Sau đó tiếp tục kiểm quyền trên hành động, người dùng, tenant và tài nguyên thực tế; dùng cơ chế thu hồi/chống replay riêng cho vòng đời token.
