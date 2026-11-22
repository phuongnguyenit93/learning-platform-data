# @WithMockUser không mô phỏng đầy đủ principal Resource Server

## 1. Khác biệt cốt lõi

Trong Spring Security Servlet, `@WithMockUser` tạo một `UsernamePasswordAuthenticationToken` đã authenticated, với principal kiểu `UserDetails`. Một request JWT Resource Server đi qua `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider`, `JwtDecoder` và `JwtAuthenticationConverter`, sau đó tạo `JwtAuthenticationToken` với principal kiểu `Jwt`.

Vì vậy `@WithMockUser` bỏ qua Bearer token extraction, decoder, chữ ký, issuer, audience, thời hạn và claim conversion. Test có thể chứng minh một authority được phép gọi endpoint, nhưng không chứng minh Resource Server đã xác minh token hoặc tạo đúng principal.

**Chọn helper theo điều cần kiểm tra:** `@WithMockUser` cho authority-only tests; MockMvc `jwt()` cho JWT principal/claims; Bearer JWT đã ký qua filter chain cho integration tests của decoder và converter.

## 2. Principal khác nhau giữa các authentication mechanisms

| Cơ chế | Authentication thường gặp | Principal thường gặp | Servlet test helper |
|---|---|---|---|
| `@WithMockUser` | `UsernamePasswordAuthenticationToken` | `UserDetails` / `User` | `@WithMockUser` |
| Resource Server JWT | `JwtAuthenticationToken` | `Jwt` | MockMvc `jwt()` |
| Resource Server opaque token | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` | MockMvc `opaqueToken()` |
| OIDC Login | OAuth2 Login Authentication | `OidcUser` | `oidcLogin()` |
| OAuth2 Login | OAuth2 Login Authentication | `OAuth2User` | `oauth2Login()` |
| Authentication tùy biến | Tùy implementation | Tùy principal contract | `authentication()` |

Các class cụ thể có thể khác theo provider và version, nhưng principal contract là điểm cần lưu ý.

### 2.1. @WithMockUser tạo UserDetails

~~~java
@Test
@WithMockUser(username = "alice", roles = {"ADMIN"})
void adminCanReadReport() throws Exception {
    mvc.perform(get("/api/admin/report"))
        .andExpect(status().isOk());
}
~~~

Annotation tạo user `alice`, principal là `UserDetails`, và role `ADMIN` trở thành authority `ROLE_ADMIN`. Nếu không truyền thuộc tính, Spring Security Test mặc định dùng user `user` và role `USER`.

`roles` tự thêm prefix `ROLE_`; `authorities` dùng chuỗi authority chính xác:

~~~java
@WithMockUser(roles = "ADMIN")
// ROLE_ADMIN

@WithMockUser(authorities = "SCOPE_orders.read")
// SCOPE_orders.read
~~~

Nếu policy dùng OAuth scope authorities, hãy dùng `authorities` hoặc JWT-aware helper. Không dùng `roles` rồi mong Spring tự chuyển thành `SCOPE_...`.

### 2.2. JWT Resource Server tạo JwtAuthenticationToken

Một JWT access token có thể chứa:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a"
}
~~~

Với converter mặc định, scope values thường được chuyển thành `SCOPE_orders.read` và `SCOPE_orders.write`. `JwtAuthenticationToken` chứa JWT principal và authorities. Controller có thể nhận:

~~~java
@GetMapping("/api/me")
MeResponse me(@AuthenticationPrincipal Jwt jwt) {
    return new MeResponse(
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );
}
~~~

`@WithMockUser` không tạo `Jwt`, do đó không cung cấp `iss`, `aud`, `sub` hay `tenant_id` theo contract của access token.

## 3. Hạn chế cụ thể của @WithMockUser

### 3.1. Principal không đúng kiểu

Nếu controller yêu cầu `@AuthenticationPrincipal Jwt`, `@WithMockUser` đưa vào một principal `UserDetails`. Resolver không thể biến User thành Jwt. Với `@AuthenticationPrincipal` mặc định, argument không đúng type có thể nhận `null`; nếu bật `errorOnInvalidType = true`, mismatch sẽ được báo lỗi thay vì âm thầm nhận null.

~~~java
@GetMapping("/api/me")
MeResponse me(
        @AuthenticationPrincipal(errorOnInvalidType = true) Jwt jwt) {
    return new MeResponse(
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );
}
~~~

### 3.2. Không kiểm tra JWT validation

`@WithMockUser` không chạy:

- Bearer token extraction.
- `JwtDecoder` và signature verification.
- Issuer, audience, expiry và not-before validation.
- JWKS lookup, key rotation hoặc algorithm policy.
- Token profile validators.
- Custom claim-to-authority converter.
- DPoP/certificate-bound token checks nếu ứng dụng có triển khai.

### 3.3. Không mô phỏng opaque token hoặc OIDC Login

Opaque Resource Server thường tạo principal `OAuth2AuthenticatedPrincipal` sau introspection; OIDC Login tạo `OidcUser`. `@WithMockUser` không mô phỏng hai principal này.

### 3.4. Không kiểm tra credential trong HTTP request

Test với `@WithMockUser` không chứng minh client gửi đúng `Authorization: Bearer ...`, token được parse đúng, token invalid trả 401 hoặc API không redirect sang browser login.

## 4. Khi @WithMockUser vẫn phù hợp

Annotation phù hợp khi test chỉ kiểm tra authorization dựa trên Authentication tổng quát, không phụ thuộc principal JWT hoặc token conversion.

~~~java
@Test
@WithMockUser(authorities = "SCOPE_orders.read")
void readAuthorityCanAccessReadEndpoint() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "SCOPE_profile")
void unrelatedAuthorityCannotReadOrders() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isForbidden());
}
~~~

Các test này kiểm tra URL authorization nhận authority nào. Đặt tên test như “read authority can access endpoint”; không đặt “valid JWT can read order” vì chưa có JWT nào được xác minh.

Với method security:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto load(String id) {
    return repository.findDtoById(id);
}
~~~

`@WithMockUser(authorities = "SCOPE_orders.read")` có thể kiểm tra rule authority-only. Nhưng nếu expression đọc `authentication.principal.claims['tenant_id']`, principal UserDetails không đáp ứng contract; dùng JWT-aware context.

## 5. MockMvc jwt() cho JWT principal giả lập

Spring Security Test cung cấp request post-processor `jwt()` trong Servlet/MockMvc. Nó tạo `JwtAuthenticationToken` và principal `Jwt`, phù hợp với controller và authorization tests phụ thuộc claims.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
~~~

### 5.1. Test controller đọc Jwt principal

~~~java
@Test
void jwtPrincipalProvidesSubjectAndTenant() throws Exception {
    mvc.perform(get("/api/me")
            .with(jwt().jwt(jwt -> jwt
                .subject("user-123")
                .claim("tenant_id", "tenant-a")
            )))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("user-123"))
        .andExpect(jsonPath("$.tenantId").value("tenant-a"));
}
~~~

Helper gắn JWT Authentication giả lập vào request. Controller nhận đúng principal type và có thể đọc claims.

**Giới hạn:** `jwt()` không gọi `JwtDecoder` để xác minh chữ ký. JWT object được dựng trong test, không phải compact token được gửi qua Bearer header.

### 5.2. Test scope authorities

~~~java
@Test
void jwtWithReadScopeCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void jwtWithoutReadScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            )))
        .andExpect(status().isForbidden());
}
~~~

`jwt().authorities(...)` chủ động gán authorities để kiểm tra authorization; nó không kiểm tra converter của ứng dụng.

### 5.3. Test claims

~~~java
@Test
void jwtPrincipalContainsResourceClaims() throws Exception {
    mvc.perform(get("/api/me")
            .with(jwt().jwt(jwt -> jwt
                .issuer(URI.create("https://id.example.test/realms/shop"))
                .subject("user-123")
                .audience(List.of("orders-api"))
                .claim("client_id", "orders-web")
                .claim("tenant_id", "tenant-a")
                .claim("scope", "orders.read")
            )))
        .andExpect(status().isOk());
}
~~~

Các claims này chỉ được dựng để controller/policy đọc; chưa được chứng minh là do issuer thật ký.

### 5.4. jwt() không chứng minh application converter được gọi

Nếu test tự gán `SCOPE_orders.read`, converter bị hỏng nhưng test vẫn có thể pass. Hãy kiểm tra converter riêng và thêm Bearer integration test.

## 6. opaqueToken() cho opaque Resource Server principal

Với opaque token, principal sau introspection thường là `OAuth2AuthenticatedPrincipal`, không phải Jwt. MockMvc helper:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
~~~

~~~java
@Test
void opaquePrincipalCanAccessPartnerReport() throws Exception {
    mvc.perform(get("/api/partners/reports/2026")
            .with(opaqueToken()
                .attributes(attributes -> {
                    attributes.put("sub", "partner-user-01");
                    attributes.put("client_id", "partner-client");
                })
                .authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_partner.reports.read"
                    )
                )
            ))
        .andExpect(status().isOk());
}
~~~

`opaqueToken()` kiểm tra principal attributes và authorization. Nó không gọi introspection endpoint thật, do đó không kiểm tra client authentication, `active`, timeout, HTTP status, schema drift, cache hoặc revocation. Muốn kiểm tra các phần đó, test `OpaqueTokenIntrospector` hoặc dùng HTTP stub/sandbox.

## 7. oidcLogin() cho OIDC browser principal

Controller browser có thể nhận `OidcUser`:

~~~java
@GetMapping("/console/profile")
Profile profile(@AuthenticationPrincipal OidcUser user) {
    return new Profile(user.getSubject(), user.getEmail());
}
~~~

Test dùng:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;

@Test
void oidcUserHasIdTokenAndUserInfoClaims() throws Exception {
    mvc.perform(get("/console/profile")
            .with(oidcLogin()
                .idToken(token -> token.subject("browser-user-01"))
                .userInfo(userInfo ->
                    userInfo.email("browser@example.test")
                )
            ))
        .andExpect(status().isOk());
}
~~~

`oidcLogin()` mô phỏng OIDC Login principal; nó không mô phỏng Resource Server `JwtAuthenticationToken`. `oauth2Login()` cũng dành cho OAuth2 Login principal, không phải JWT access token.

## 8. authentication() và custom @WithSecurityContext

### 8.1. Truyền Authentication tường minh

~~~java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "none")
    .issuer(URI.create("https://id.example.test/realms/shop"))
    .subject("user-123")
    .audience(List.of("orders-api"))
    .issuedAt(Instant.parse("2026-11-15T00:00:00Z"))
    .expiresAt(Instant.parse("2026-11-15T00:05:00Z"))
    .claim("tenant_id", "tenant-a")
    .build();

JwtAuthenticationToken authentication =
    new JwtAuthenticationToken(
        jwt,
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );

mvc.perform(get("/api/me")
        .with(authentication(authentication)))
    .andExpect(status().isOk());
~~~

Object JWT này được dựng trực tiếp. Header `alg` trong object không biến nó thành compact JWT đã ký; không dùng test này để kết luận decoder đã xác minh chữ ký.

### 8.2. Custom annotation với @WithSecurityContext

Nếu nhiều tests cần cùng một JWT principal, có thể tạo annotation riêng, ví dụ `@WithJwtPrincipal`. Đây là annotation do ứng dụng định nghĩa, không phải annotation built-in mặc định của Spring Security Test.

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = WithJwtPrincipal.Factory.class)
public @interface WithJwtPrincipal {

    String subject() default "user-123";
    String tenant() default "tenant-a";
    String[] authorities() default {"SCOPE_orders.read"};

    final class Factory
            implements WithSecurityContextFactory<WithJwtPrincipal> {

        @Override
        public SecurityContext createSecurityContext(
                WithJwtPrincipal annotation) {

            Instant now = Instant.parse("2026-11-15T00:00:00Z");

            Jwt jwt = Jwt.withTokenValue("synthetic-test-token")
                .header("alg", "none")
                .issuer(URI.create("https://id.example.test/realms/shop"))
                .subject(annotation.subject())
                .audience(List.of("orders-api"))
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300))
                .claim("tenant_id", annotation.tenant())
                .build();

            List<GrantedAuthority> authorities =
                Arrays.stream(annotation.authorities())
                    .map(SimpleGrantedAuthority::new)
                    .collect(Collectors.toList());

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();

            context.setAuthentication(
                new JwtAuthenticationToken(jwt, authorities)
            );
            return context;
        }
    }
}
~~~

Imports bổ sung:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.net.URI;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.test.context.support.WithSecurityContext;
import org.springframework.security.test.context.support.WithSecurityContextFactory;
~~~

Sử dụng:

~~~java
@Test
@WithJwtPrincipal(
    subject = "tenant-a-user",
    tenant = "tenant-a",
    authorities = {"SCOPE_orders.read"}
)
void tenantUserCanReadOwnOrders() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk());
}
~~~

Annotation này tạo đúng principal shape và claims cho test context. Nó vẫn bỏ qua Bearer token parsing, JWT signature, issuer/audience validators và converter. Với test thời gian deterministic, dùng clock cố định hoặc inject clock thay vì dựa vào giờ máy.

## 9. Kiểm tra JwtAuthenticationConverter riêng

Nếu Resource Server dùng custom `JwtAuthenticationConverter`, kiểm tra converter trực tiếp. Ví dụ:

~~~java
JwtGrantedAuthoritiesConverter grantedAuthorities =
    new JwtGrantedAuthoritiesConverter();

grantedAuthorities.setAuthoritiesClaimName("scope");
grantedAuthorities.setAuthorityPrefix("SCOPE_");

JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setJwtGrantedAuthoritiesConverter(grantedAuthorities);
~~~

Test:

~~~java
@Test
void convertsScopeClaimIntoAuthorities() {
    Jwt jwt = Jwt.withTokenValue("synthetic")
        .header("alg", "none")
        .subject("user-123")
        .claim("scope", "orders.read orders.write")
        .build();

    AbstractAuthenticationToken authentication =
        converter.convert(jwt);

    assertThat(authentication.getAuthorities())
        .extracting(GrantedAuthority::getAuthority)
        .containsExactlyInAnyOrder(
            "SCOPE_orders.read",
            "SCOPE_orders.write"
        );
}
~~~

Test thêm claim đúng/sai kiểu, claim thiếu, role ngoài allowlist, scope không thuộc API và tenant claim sai. Test converter trực tiếp chưa chứng minh decoder/filter chain đã gọi converter; cần thêm Bearer integration test.

## 10. Integration test với Bearer JWT đã ký

### 10.1. Security configuration

~~~java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Ví dụ minh họa Servlet stack. Decoder cần issuer/audience validators phù hợp; `Customizer.withDefaults()` không thay thế trust contract.

### 10.2. Gửi token qua Authorization header

Giả sử test fixture `testTokens` ký JWT bằng private key chỉ dùng trong test và test context cấu hình decoder với public key tương ứng:

~~~java
@Test
void signedBearerTokenPassesThroughResourceServer() throws Exception {
    String token = testTokens.issue(
        "user-123",
        TRUSTED_ISSUER,
        List.of("orders-api"),
        "orders.read",
        "tenant-a"
    );

    mvc.perform(get("/api/orders/42")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isOk());
}
~~~

Test này đi qua MockMvc, Spring Security filter chain, Bearer extraction, JWT decoder, signature/claims validators, Authentication converter, authorization và controller/service. `testTokens` là test-only factory; không dùng access token hoặc signing key production.

### 10.3. Token có chữ ký sai

~~~java
@Test
void invalidSignatureIsRejected() throws Exception {
    String token = tokenSignedByUntrustedKey();

    mvc.perform(get("/api/orders/42")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

Token được ký bởi key khác với public key decoder tin. Đây là test signature path thực; `jwt()` không thay thế được.

### 10.4. Audience sai

~~~java
@Test
void wrongAudienceIsRejected() throws Exception {
    String token = testTokens.issue(
        "user-123",
        TRUSTED_ISSUER,
        List.of("billing-api"),
        "orders.read",
        "tenant-a"
    );

    mvc.perform(get("/api/orders/42")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

### 10.5. Principal thật tại controller

~~~java
@Test
void signedTokenProvidesExpectedPrincipalClaims() throws Exception {
    String token = testTokens.issue(
        "user-123",
        TRUSTED_ISSUER,
        List.of("orders-api"),
        "orders.read",
        "tenant-a"
    );

    mvc.perform(get("/api/me")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("user-123"))
        .andExpect(jsonPath("$.tenantId").value("tenant-a"));
}
~~~

Test này kiểm tra JWT validation và principal claims được đưa tới controller.

## 11. Kiểm tra custom converter qua filter chain

Nếu cấu hình:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(customJwtAuthenticationConverter)
    )
)
~~~

thì cần integration test với Bearer JWT chứa claims mà converter đọc, ví dụ:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "app_roles": ["STORE_MANAGER"],
  "tenant_id": "tenant-a"
}
~~~

Xác nhận decoder chấp nhận token, scope thành `SCOPE_orders.read`, role thành `ROLE_STORE_MANAGER` nếu mapping cho phép, role ngoài allowlist không tạo global admin, và controller nhận JWT claim tenant đúng.

Một test dùng `jwt().authorities(...)` không chứng minh custom converter đã được gọi.

## 12. Phân biệt 401 và 403

| Tình huống | Authentication | Authorization | HTTP thường gặp |
|---|---|---|---|
| Không token tới protected API | Chưa authenticated | Không đến policy quyền | 401 |
| JWT signature sai | Authentication failure | Không tới URL authorization | 401 |
| Issuer/audience/expiry sai | Authentication failure | Không tới URL authorization | 401 |
| JWT hợp lệ, thiếu scope | Authenticated JwtAuthenticationToken | Denied | 403 |
| JWT hợp lệ, scope đủ nhưng sai tenant | Authenticated | Domain authorization denied | 403 hoặc 404 theo policy |
| @WithMockUser thiếu authority | Mock authenticated User | Denied | 403 |
| @WithMockUser đủ authority | Mock authenticated User | Allowed | Qua URL policy |

Đừng dùng `@WithMockUser` để test invalid token. Annotation tạo Authentication hợp lệ trong test context, không tạo token invalid.

## 13. Cấu hình MockMvc security đúng cách

Ví dụ Spring Boot test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrdersSecurityTests {

    @Autowired
    MockMvc mvc;
}
~~~

Với MockMvc tự dựng:

~~~java
mvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Static import:

~~~java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;
~~~

Các annotation-based test contexts như `@WithMockUser` dùng Spring Security Test listener; request post-processors như `jwt()` gắn Authentication vào request cụ thể. Đảm bảo MockMvc chạy qua filter chain thật khi mục tiêu là integration testing.

### 13.1. Cẩn thận với addFilters = false

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

có thể làm security filters không chạy. Test controller thuần có thể dùng cấu hình này cho mục đích riêng, nhưng không được dùng kết quả đó để kết luận Resource Server authentication hoạt động.

## 14. Servlet và WebFlux helper khác nhau

| Mục đích | Servlet / MockMvc | WebFlux / WebTestClient |
|---|---|---|
| Mock user | `@WithMockUser` hoặc `user()` | `@WithMockUser` hoặc reactive test support |
| Mock JWT principal | `jwt()` | `mockJwt()` |
| Mock opaque token | `opaqueToken()` | Reactive opaque-token support theo version |
| HTTP test client | `MockMvc` | `WebTestClient` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |

`mockJwt()` trong `SecurityMockServerConfigurers` dành cho WebFlux/WebTestClient. Không import helper reactive vào Servlet MockMvc tests. Kiểm tra package/overloads theo Spring Security version.

## 15. Ma trận chọn test helper

| Mục tiêu | Helper phù hợp | Không chứng minh |
|---|---|---|
| Authority-only method security | `@WithMockUser` | JWT principal/claims/decoder |
| Controller nhận Jwt | MockMvc `jwt()` | Signature, issuer, audience, configured converter |
| JWT claims trong controller | `jwt().jwt(...)` | Token thật do issuer ký |
| Opaque principal attributes | `opaqueToken()` | Introspection HTTP request/response |
| OIDC Login principal | `oidcLogin()` | Resource Server access-token authentication |
| Custom Authentication | `authentication(...)` | Provider/decoder pipeline |
| Reusable synthetic JWT context | Custom `@WithSecurityContext` | Bearer parsing/signature validation |
| Claim-to-authority converter | Unit test converter | Full filter-chain wiring |
| JWT signature/issuer/audience/expiry | Signed Bearer token qua MockMvc | Production IdP availability |
| JWKS/key rotation | Decoder integration với JWKS stub/sandbox | Browser login nếu không test riêng |
| Opaque introspection | HTTP stub + introspector thật | JWT decoder |

## 16. Các lỗi thường gặp

### Lỗi 1 — Dùng @WithMockUser rồi kết luận Jwt principal hoạt động

Annotation tạo UserDetails, không phải Jwt. Dùng `jwt()` hoặc Bearer JWT thật.

### Lỗi 2 — Dùng roles thay scope authority

`roles = ADMIN` tạo `ROLE_ADMIN`, không tạo `SCOPE_orders.read`.

### Lỗi 3 — Gán authority trong jwt() rồi kết luận converter đúng

`jwt().authorities(...)` đã chỉ định kết quả cuối. Test converter riêng và test Bearer integration.

### Lỗi 4 — Dùng jwt() để test signature

Request post-processor tạo JwtAuthenticationToken giả lập; decoder không được gọi. Gửi compact JWT ký bằng test key qua Authorization header.

### Lỗi 5 — Dùng @WithMockUser để test issuer/audience

Annotation không thực hiện issuer/audience validation. Dùng decoder integration test với token ký đúng nhưng claim sai.

### Lỗi 6 — Dùng oidcLogin() cho API Bearer

OIDC Login principal là OidcUser; API Resource Server JWT thường dùng JwtAuthenticationToken.

### Lỗi 7 — Dùng opaque helper nhưng mong kiểm tra introspection endpoint

opaqueToken() mô phỏng authentication đã có; nó không gọi Authorization Server. Dùng HTTP stub cho introspector.

### Lỗi 8 — Tắt security filters trong test nhưng vẫn assert security behavior

Nếu filter chain không chạy, test không bảo vệ token extraction/validation.

### Lỗi 9 — Test chỉ kiểm tra HTTP 200

Request có thể qua mock Authentication nhưng controller không nhận claims đúng hoặc dùng sai tenant. Assert principal/response và negative cases.

### Lỗi 10 — Gọi test “valid JWT” nhưng không có compact JWT nào được decode

Tên test phải phản ánh đúng phần đã kiểm tra. Nếu chỉ tạo JwtAuthenticationToken giả lập, gọi đó là JWT-principal/authorization test.

## 17. Chiến lược kiểm thử theo tầng

~~~mermaid
flowchart TD
    A["JWT claim / authority converter unit tests"] --> B["MockMvc jwt() principal + authorization tests"]
    B --> C["Signed Bearer JWT through SecurityFilterChain"]
    C --> D["JWKS / issuer / audience / expiry integration tests"]
    D --> E["Tenant, owner, method-security and API behavior"]
~~~

1. **Converter tests:** claim schema, authority prefix, allowlist và invalid claim types.
2. **Principal/authorization tests:** `jwt()` cho JWT principal; `@WithMockUser` cho authority tổng quát.
3. **Bearer filter-chain integration:** signed token, test private key và decoder dùng public key; kiểm tra extraction, signature, issuer, audience, time và converter.
4. **Provider/edge integration:** JWKS, rotation, discovery, proxy, introspection và error responses.

## 18. Checklist trước khi chọn @WithMockUser

- [ ] Test chỉ quan tâm authority hay cần JWT principal?
- [ ] Controller có nhận `@AuthenticationPrincipal Jwt` không?
- [ ] Method security có đọc `authentication.principal.claims` không?
- [ ] Test cần issuer, audience, subject hoặc tenant claim không?
- [ ] Cần kiểm tra scope/role converter không?
- [ ] Cần kiểm tra chữ ký, expiry, issuer hoặc audience không?
- [ ] Cần kiểm tra Bearer header parsing và 401 challenge không?
- [ ] Token là JWT, opaque token hay OIDC Login principal?
- [ ] Dùng đúng MockMvc helper hay WebTestClient helper?
- [ ] Test có vô tình disable security filters không?
- [ ] Tên test phản ánh đúng phần đã được mô phỏng?
- [ ] Có integration test đi qua Resource Server filter chain với signed token không?

## 19. Kết luận

`@WithMockUser` phù hợp với test chỉ cần authenticated user và authorities. Nó **không mô phỏng đầy đủ principal Resource Server**: principal của nó là `UserDetails`, còn JWT Resource Server tạo `JwtAuthenticationToken` với principal `Jwt`.

Trong Servlet testing:

- Dùng `@WithMockUser` cho authority-only authorization.
- Dùng MockMvc `jwt()` cho JWT principal/claims và authorization behavior.
- Dùng `opaqueToken()` cho opaque principal.
- Dùng `oidcLogin()` cho OIDC browser principal.
- Dùng custom `@WithSecurityContext` khi cần synthetic principal tái sử dụng.
- Dùng **signed Bearer JWT qua MockMvc và decoder thật** để kiểm tra token extraction, signature, issuer, audience, time validators và converter wiring.

Không có một helper nào thay thế mọi lớp kiểm thử. Hãy chọn helper theo principal contract và xác minh token thật ở integration boundary mà Resource Server sử dụng.

### Tài liệu tham khảo

- [Spring Security Reference — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security Reference — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security Reference — MockMvc Request Post Processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security API — WithMockUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html)
- [Spring Security API — JwtAuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationToken.html)
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html)
- [Spring Security API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)

