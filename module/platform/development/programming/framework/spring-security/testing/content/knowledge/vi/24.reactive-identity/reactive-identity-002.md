# mockAuthentication với loại Authentication riêng

## 1. Khi mockUser không đại diện đúng danh tính của ứng dụng

`mockUser()` rất tiện khi ứng dụng dùng principal kiểu `UserDetails` với username, role và authority thông thường. Nhưng không phải ứng dụng Reactive nào cũng nhận `UsernamePasswordAuthenticationToken`:

- Resource Server dùng `JwtAuthenticationToken` và cần claim `sub`, `tenant_id` hoặc thông tin từ JWT.
- OAuth2 Login dùng `OAuth2AuthenticationToken` và principal là `OAuth2User`.
- OIDC Login dùng `OidcUser` cùng `OidcUserAuthority`.
- Ứng dụng tích hợp hệ thống nội bộ có thể dùng `PreAuthenticatedAuthenticationToken` hoặc một lớp `Authentication` riêng.
- Service có thể kiểm tra kiểu principal cụ thể thay vì chỉ đọc `Authentication.getName()`.

Nếu test luôn dùng `mockUser("alice")`, principal được tạo có thể sai kiểu so với production. Code ép kiểu sang `JwtAuthenticationToken` hoặc truy cập claim của JWT sẽ thất bại, dù test đang cố kiểm tra một luồng JWT.

Trong module **SPRING_SECURITY_TESTING**, người học dùng `spring-security-test` để kiểm chứng xác thực, phân quyền và bảo vệ HTTP trên Servlet/Reactive với `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập. Bài này tập trung vào `SecurityMockServerConfigurers.mockAuthentication(Authentication)` để gắn trực tiếp loại Authentication mà ứng dụng mong đợi vào request WebFlux.

Sau bài học, bạn có thể:

- Dùng `mockAuthentication(authentication)` với một đối tượng `Authentication` dựng sẵn.
- Chọn đúng loại token như `TestingAuthenticationToken`, `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken` hoặc custom token.
- Kiểm tra principal, credentials, authorities, tên người dùng và trạng thái `isAuthenticated`.
- Viết test khi controller/service phụ thuộc kiểu Authentication cụ thể.
- Phân biệt việc dựng SecurityContext với quá trình xác thực thật.
- Biết khi nào nên dùng `mockUser`, `mockJwt`, `mockOAuth2Login`, `mockOidcLogin` hoặc `mockAuthentication`.

## 2. mockAuthentication(Authentication) làm gì?

`mockAuthentication` thuộc `SecurityMockServerConfigurers`:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockAuthentication;
```

Nó nhận một đối tượng triển khai `org.springframework.security.core.Authentication` và dùng đối tượng đó làm danh tính của request kiểm thử. Cách sử dụng:

```java
Authentication authentication = new TestingAuthenticationToken(
    "alice",
    "test-credentials",
    "ROLE_REVIEWER"
);

client.mutateWith(mockAuthentication(authentication))
    .get()
    .uri("/api/review")
    .exchange()
    .expectStatus().isOk();
```

Đối tượng Authentication được đặt vào ngữ cảnh bảo mật Reactive cho request đó. Các thành phần như `AuthorizationWebFilter`, controller và service có thể đọc danh tính thông qua cơ chế SecurityContext của WebFlux.

### Những thuộc tính được giữ từ Authentication

Về nguyên tắc, ứng dụng nhận đúng đối tượng Authentication mà test truyền vào. Những thông tin quan trọng gồm:

| Thành phần | API | Ý nghĩa |
| --- | --- | --- |
| Principal | `getPrincipal()` | Danh tính hoặc đối tượng principal |
| Tên | `getName()` | Tên định danh do Authentication cung cấp |
| Credentials | `getCredentials()` | Thông tin xác thực; test nên dùng giá trị giả |
| Authorities | `getAuthorities()` | Role/scope/permission dùng cho authorization |
| Trạng thái | `isAuthenticated()` | Authentication có được đánh dấu đã xác thực không |
| Details | `getDetails()` | Metadata bổ sung nếu token hỗ trợ |

`mockAuthentication` không tự chuyển đổi chuỗi role, không tự thêm tiền tố `ROLE_` và không suy ra scope từ claim. Hãy tạo Authentication với authorities chính xác mà ứng dụng cần kiểm tra.

## 3. Dùng TestingAuthenticationToken cho test authorization

`TestingAuthenticationToken` là token tiện ích dành cho test. Constructor có authorities tạo một Authentication đã authenticated:

```java
Authentication reviewer = new TestingAuthenticationToken(
    "alice",
    "not-a-real-password",
    "ROLE_REVIEWER",
    "invoice:read"
);

client.mutateWith(mockAuthentication(reviewer))
    .get()
    .uri("/api/invoices")
    .exchange()
    .expectStatus().isOk();
```

Ở ví dụ này:

- `getName()` trả `alice`.
- Authorities có `ROLE_REVIEWER` và `invoice:read`.
- `isAuthenticated()` là `true`.
- Credentials chỉ là chuỗi giả dùng trong test, không phải password được xác minh.

Constructor hai tham số không có authorities tạo token chưa authenticated:

```java
Authentication pending = new TestingAuthenticationToken(
    "alice",
    "not-authenticated"
);

assertThat(pending.isAuthenticated()).isFalse();
```

Đây là cách hữu ích để kiểm tra code có phân biệt Authentication đã xác thực và chưa xác thực. Tuy nhiên, việc tiêm trực tiếp một token chưa authenticated không tái hiện đầy đủ challenge/entry point của một request không có credentials. Nếu mục tiêu là kiểm tra hành vi anonymous, gửi request không dùng mutator; nếu mục tiêu là kiểm tra login thất bại, chạy authentication flow thực tế.

### Test role và permission chính xác

Giả sử security rule:

```java
.pathMatchers("/api/review").hasRole("REVIEWER")
.pathMatchers("/api/invoices").hasAuthority("invoice:read")
```

Các ca:

```java
Authentication reviewer = new TestingAuthenticationToken(
    "alice", "n/a", "ROLE_REVIEWER");

Authentication reader = new TestingAuthenticationToken(
    "bob", "n/a", "invoice:read");

client.mutateWith(mockAuthentication(reviewer))
    .get().uri("/api/review")
    .exchange()
    .expectStatus().isOk();

client.mutateWith(mockAuthentication(reader))
    .get().uri("/api/review")
    .exchange()
    .expectStatus().isForbidden();

client.mutateWith(mockAuthentication(reader))
    .get().uri("/api/invoices")
    .exchange()
    .expectStatus().isOk();
```

`hasRole("REVIEWER")` kiểm tra `ROLE_REVIEWER` theo tiền tố mặc định. `hasAuthority("invoice:read")` so sánh chính xác chuỗi permission.

## 4. Khi controller yêu cầu JwtAuthenticationToken

Resource Server thường tạo `JwtAuthenticationToken` sau khi JWT decoder xác minh token. Controller hoặc service có thể phụ thuộc vào kiểu này để đọc claims:

```java
@RestController
class OrderIdentityController {
    @GetMapping("/api/order-owner")
    Mono<String> owner() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .cast(JwtAuthenticationToken.class)
            .map(authentication ->
                authentication.getToken().getSubject());
    }
}
```

Nếu dùng `mockUser("alice")`, principal là `UserDetails` và Authentication là `UsernamePasswordAuthenticationToken`. Phép `cast(JwtAuthenticationToken.class)` sẽ thất bại. Dùng `mockAuthentication` với đúng token type:

```java
Instant now = Instant.now();
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "none")
    .subject("alice")
    .claim("tenant_id", "tenant-a")
    .issuedAt(now)
    .expiresAt(now.plusSeconds(300))
    .build();

JwtAuthenticationToken jwtAuthentication =
    new JwtAuthenticationToken(
        jwt,
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );

client.mutateWith(mockAuthentication(jwtAuthentication))
    .get()
    .uri("/api/order-owner")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("alice");
```

Đối tượng `Jwt` ở đây được tạo trực tiếp trong bộ nhớ; header `alg` không được dùng để xác minh chữ ký. `mockAuthentication` đặt sẵn `JwtAuthenticationToken` vào SecurityContext, nên test này xác minh code phía sau nhận đúng kiểu token và claim, **không** kiểm tra `JwtDecoder`, issuer, audience, chữ ký hoặc thời hạn token thực tế.

Nếu muốn kiểm tra mapping claim và authority do ứng dụng cấu hình, dùng `mockJwt()` khi phù hợp hoặc gửi Bearer token qua decoder thật trong integration test. Chọn cách test theo mục tiêu:

| Mục tiêu | Cách phù hợp |
| --- | --- |
| Controller cần đúng kiểu `JwtAuthenticationToken` | `mockAuthentication(jwtAuthentication)` |
| Kiểm tra endpoint với JWT principal giả lập, authority tùy chỉnh | `mockJwt()` |
| Kiểm tra decoder, chữ ký, issuer, audience và expiry | Bearer token qua Resource Server/decoder thật |

## 5. Khi ứng dụng dùng OAuth2AuthenticationToken

OAuth2 Login tạo `OAuth2AuthenticationToken` với principal triển khai `OAuth2User`. Nếu code phụ thuộc kiểu Authentication hoặc thuộc tính registration ID, có thể dựng token trực tiếp:

```java
Map<String, Object> attributes = Map.of(
    "sub", "alice-123",
    "name", "Alice Nguyen",
    "email", "alice@example.test"
);

OAuth2User principal = new DefaultOAuth2User(
    List.of(new SimpleGrantedAuthority("ROLE_USER")),
    attributes,
    "sub"
);

OAuth2AuthenticationToken oauthAuthentication =
    new OAuth2AuthenticationToken(
        principal,
        principal.getAuthorities(),
        "corporate-login"
    );

client.mutateWith(mockAuthentication(oauthAuthentication))
    .get()
    .uri("/api/oauth-profile")
    .exchange()
    .expectStatus().isOk();
```

`OAuth2AuthenticationToken` giữ registration ID `corporate-login` và principal `DefaultOAuth2User`. Test có thể xác minh:

```java
OAuth2AuthenticationToken authentication =
    (OAuth2AuthenticationToken) context.getAuthentication();

String registrationId = authentication.getAuthorizedClientRegistrationId();
String subject = authentication.getPrincipal().getAttribute("sub");
```

Token được dựng trực tiếp không chứng minh authorization code flow, redirect URI, state, PKCE, token endpoint hoặc việc tải user info. Khi kiểm tra các bước đó, cần test OAuth2 Login flow riêng.

## 6. Khi ứng dụng dùng OidcUser và OidcAuthenticationToken

OIDC Login thường cung cấp `OidcUser` với `OidcIdToken` và có thể có `OidcUserInfo`. Nếu ứng dụng truy cập ID token hoặc claim OIDC cụ thể, hãy tạo Authentication tương ứng.

Ví dụ dựng principal:

```java
Instant now = Instant.now();

OidcIdToken idToken = new OidcIdToken(
    "test-id-token",
    now,
    now.plusSeconds(300),
    Map.of(
        "iss", "https://issuer.example.test",
        "sub", "alice-123",
        "aud", List.of("web-client"),
        "iat", now,
        "exp", now.plusSeconds(300),
        "name", "Alice Nguyen"
    )
);

OidcUser oidcUser = new DefaultOidcUser(
    List.of(new SimpleGrantedAuthority("ROLE_USER")),
    idToken
);

OAuth2AuthenticationToken oidcAuthentication =
    new OAuth2AuthenticationToken(
        oidcUser,
        oidcUser.getAuthorities(),
        "corporate-oidc"
    );
```

`OidcUser` triển khai `OAuth2User`; Authentication sau login vẫn là `OAuth2AuthenticationToken`. Khác biệt nằm ở principal có thông tin OIDC như `getIdToken()`.

Tiêm token:

```java
client.mutateWith(mockAuthentication(oidcAuthentication))
    .get()
    .uri("/api/oidc-profile")
    .exchange()
    .expectStatus().isOk();
```

Đây là principal OIDC được dựng trong test. Nó không xác minh chữ ký ID token, nonce, issuer hoặc quy trình discovery/JWKS. Nếu mục tiêu là kiểm tra OIDC login, dùng `mockOidcLogin()` cho test authorization phù hợp và integration test riêng cho flow thật.

## 7. Custom Authentication và custom principal

Một số hệ thống có token riêng, ví dụ principal chứa employee code, tenant hoặc client application. Trong trường hợp đó, `mockAuthentication` giúp test đúng hợp đồng kiểu dữ liệu.

Ví dụ principal:

```java
record EmployeePrincipal(
    String username,
    String employeeCode,
    String tenantId
) implements Principal {
    @Override
    public String getName() {
        return username;
    }
}
```

Tạo token:

```java
final class EmployeeAuthentication
        extends AbstractAuthenticationToken {

    private final EmployeePrincipal principal;

    EmployeeAuthentication(
            EmployeePrincipal principal,
            Collection<? extends GrantedAuthority> authorities) {
        super(authorities);
        this.principal = principal;
        super.setAuthenticated(true);
    }

    @Override
    public Object getCredentials() {
        return "";
    }

    @Override
    public Object getPrincipal() {
        return this.principal;
    }

    @Override
    public String getName() {
        return this.principal.getName();
    }
}
```

Tạo Authentication và dùng:

```java
EmployeePrincipal principal =
    new EmployeePrincipal("alice", "EMP-1042", "tenant-a");

Authentication employeeAuthentication = new EmployeeAuthentication(
    principal,
    List.of(new SimpleGrantedAuthority("ROLE_REVIEWER"))
);

client.mutateWith(mockAuthentication(employeeAuthentication))
    .get()
    .uri("/api/employee")
    .exchange()
    .expectStatus().isOk();
```

Trong ứng dụng thực, chỉ authentication provider đáng tin cậy mới được tạo token đã authenticated. Constructor trên phục vụ minh họa cho test fixture; không cung cấp API cho client tự tạo Authentication. Nếu custom token cần thêm dữ liệu, hãy làm bất biến và xác định rõ cách provider xác minh danh tính.

### Kiểm tra principal type trong controller

```java
@GetMapping("/api/employee")
Mono<String> employeeCode() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getPrincipal)
        .cast(EmployeePrincipal.class)
        .map(EmployeePrincipal::employeeCode);
}
```

Test với `mockAuthentication(employeeAuthentication)` xác minh code nhận đúng custom principal. Nếu dùng `mockUser`, principal sẽ là UserDetails và phép cast trên không phù hợp.

## 8. Kiểm tra Authentication và SecurityContext trong Reactive

WebFlux lưu SecurityContext trong Reactor Context thay vì dựa vào ThreadLocal. Có thể truy cập trong pipeline:

```java
Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
}
```

Không đọc `SecurityContextHolder.getContext()` trong reactive service rồi mong nhận principal của request hiện tại. Khi publisher chuyển thread, ThreadLocal có thể không còn đúng hoặc không tồn tại.

Một endpoint chẩn đoán trong test có thể trả về các thuộc tính:

```java
@GetMapping("/api/auth-info")
Mono<Map<String, Object>> authInfo() {
    return currentAuthentication().map(authentication -> Map.of(
        "name", authentication.getName(),
        "type", authentication.getClass().getSimpleName(),
        "authenticated", authentication.isAuthenticated(),
        "authorities", authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList(),
        "principalType",
        authentication.getPrincipal().getClass().getSimpleName()
    ));
}
```

Không tạo endpoint chẩn đoán này công khai trong production nếu nó làm lộ thông tin nội bộ. Trong test, nó hữu ích để xác minh đúng loại Authentication và principal đã được tiêm.

## 9. Cấu hình WebTestClient và security chain

Ví dụ test slice:

```java
@WebFluxTest(IdentityController.class)
@Import(ReactiveIdentitySecurityConfig.class)
class MockAuthenticationTest {
    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setUp() {
        this.client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

Static import:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockAuthentication;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

Khi dùng `@WebFluxTest` hoặc `@SpringBootTest`, xác minh test context có `SecurityWebFilterChain` phù hợp. Khi tự dựng `WebTestClient`, `springSecurity()` tích hợp các thành phần kiểm thử Spring Security.

Một ví dụ cấu hình:

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveIdentitySecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/me").authenticated()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/orders").hasAuthority("SCOPE_orders.read")
                .pathMatchers("/api/employee").hasRole("REVIEWER")
                .anyExchange().denyAll())
            .build();
    }
}
```

Các endpoint GET trong ví dụ không cần thay đổi dữ liệu. Nếu test POST/PATCH/DELETE trong ứng dụng bật CSRF, hãy gửi CSRF token hợp lệ để cô lập authorization; không tắt CSRF chỉ để test vượt qua.

## 10. So sánh các mutator Authentication Reactive

Chọn mutator theo loại Authentication mà ứng dụng mong đợi:

| Mutator | Authentication/principal | Dùng khi |
| --- | --- | --- |
| `mockUser()` | `UsernamePasswordAuthenticationToken`, principal kiểu `UserDetails` | Username, role, authority thông thường |
| `mockAuthentication(auth)` | Chính đối tượng `Authentication` được truyền vào | Custom token hoặc token type cụ thể |
| `mockJwt()` | `JwtAuthenticationToken` giả lập | API Resource Server cần claims/scopes |
| `mockOAuth2Login()` | `OAuth2AuthenticationToken` với `OAuth2User` | OAuth2 Login |
| `mockOidcLogin()` | `OAuth2AuthenticationToken` với `OidcUser` | OIDC Login |

`mockAuthentication` linh hoạt vì chấp nhận Authentication trực tiếp, nhưng bạn phải tự tạo principal và authorities chính xác. Các mutator chuyên biệt thường tiện hơn khi cần dựng claim/attribute theo API test của chúng.

### Chọn cách test theo câu hỏi

- Code có ép kiểu `JwtAuthenticationToken`? Dùng `mockAuthentication(jwtToken)` hoặc `mockJwt()`.
- Code cần `OidcUser.getIdToken()`? Dùng `mockOidcLogin()` hoặc một `OAuth2AuthenticationToken` có `OidcUser`.
- Code chỉ cần username/role? Dùng `mockUser()`.
- Ứng dụng có custom Authentication? Dùng `mockAuthentication(customToken)`.
- Cần kiểm tra password, account status hoặc provider? Chạy authentication manager thật.

## 11. Kiểm tra ca âm và các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Controller cast lỗi từ `UsernamePasswordAuthenticationToken` sang `JwtAuthenticationToken` | Test dùng `mockUser` nhưng production dùng JWT | Dùng `mockAuthentication(jwtAuthentication)` hoặc `mockJwt` |
| `hasRole("ADMIN")` trả `403` | Authorities không có `ROLE_ADMIN` | Dùng authority chính xác hoặc token builder thêm role |
| `hasAuthority("SCOPE_orders.read")` trả `403` | Test chỉ gán role | Gán đúng scope authority |
| `getPrincipal()` không có thuộc tính domain | Dùng principal mặc định | Dùng custom Authentication/UserDetails phù hợp |
| Service không thấy SecurityContext | Đọc ThreadLocal trong reactive pipeline hoặc client không tích hợp security | Dùng `ReactiveSecurityContextHolder` và `springSecurity()` |
| Test pass nhưng JWT thật vẫn lỗi | Test tiêm token trực tiếp, bỏ qua decoder | Thêm integration test với Bearer token và decoder thật |
| Account disabled vẫn được phép trong test | Token đã được dựng authenticated | Kiểm tra account status qua authentication provider thật |
| Một request ảnh hưởng request tiếp theo | Tái sử dụng mutable Authentication hoặc chia sẻ state | Dựng token mới cho mỗi test/request |

### Không chia sẻ Authentication mutable giữa test song song

Một số implementation Authentication có thể thay đổi trạng thái hoặc chứa details mutable. Tạo Authentication mới trong từng test hoặc factory method. Không lưu một token dùng chung ở static field rồi thay đổi authorities/principal giữa các request song song.

### Không đưa credentials thật vào test

`getCredentials()` thường không cần cho authorization test. Dùng giá trị giả hoặc để trống theo token phù hợp; không sao chép password, access token hay secret production vào fixture. Nếu test xác thực credentials, hãy dùng secret giả dành riêng cho test environment.

## 12. Thực hành: kiểm thử API nhiều loại Authentication

Một ứng dụng Reactive có bốn endpoint:

| Endpoint | Yêu cầu |
| --- | --- |
| `GET /api/me` | Đã xác thực |
| `GET /api/admin` | `ROLE_ADMIN` |
| `GET /api/orders` | `SCOPE_orders.read` và principal JWT |
| `GET /api/employee` | Custom `EmployeeAuthentication` với `ROLE_REVIEWER` |
| Request còn lại | Từ chối |

Hãy thực hiện:

1. Dùng `TestingAuthenticationToken` để tạo reviewer có role và permission chính xác.
2. Dùng `UsernamePasswordAuthenticationToken.authenticated(...)` hoặc token phù hợp để kiểm tra principal kiểu `UserDetails`/domain principal.
3. Dựng `JwtAuthenticationToken` với subject và tenant claim; xác minh service đọc đúng claim.
4. Dựng `OAuth2AuthenticationToken` và `OidcUser` cho endpoint phụ thuộc OAuth2/OIDC principal.
5. Tạo custom `Authentication` và kiểm tra principal type trong controller/service.
6. Với mỗi endpoint, viết ca đúng quyền và thiếu quyền; kiểm tra role và scope không tự thay thế nhau.
7. Bổ sung integration test riêng cho JWT decoder hoặc OAuth2/OIDC login nếu cần xác minh authentication flow thật.

**Tiêu chí hoàn thành:** WebTestClient tiêm đúng loại Authentication; principal và authorities giữ đúng dữ liệu; authorization hoạt động theo role/scope; Reactive SecurityContext được đọc trong Reactor pipeline; test giả lập không bị nhầm là bằng chứng xác thực credentials/token thật.

## 13. Tài liệu tham khảo

- [Spring Security Reference — Testing Authentication for WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [Spring Security API — Authentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html)
