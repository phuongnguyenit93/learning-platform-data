# Principal tùy chỉnh và giới hạn của `@WithMockUser`

## 1. Vì sao principal tùy chỉnh quan trọng?

Trong Spring Security, **principal** là đối tượng đại diện cho danh tính đang được xác thực. Với ứng dụng đơn giản, username và danh sách quyền có thể đã đủ. Nhưng hệ thống thực tế thường cần thêm dữ liệu như `accountId`, `tenantId`, `displayName`, loại tài khoản hoặc thông tin miền nghiệp vụ. Controller và service có thể nhận các thuộc tính này qua `@AuthenticationPrincipal`.

`@WithMockUser` là cách nhanh để kiểm tra phân quyền, nhưng nó tạo principal mặc định kiểu `org.springframework.security.core.userdetails.User`. Annotation không cho phép chỉ định lớp principal tùy chỉnh. Nếu mã ứng dụng yêu cầu `AppUserPrincipal`, test dùng `@WithMockUser` có thể không cung cấp đúng đối tượng mà controller mong đợi.

Bài học thuộc chương **Annotation người dùng** của module **SPRING_SECURITY_TESTING**. Module hướng dẫn kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive; người học sử dụng `MockMvc`, `WebTestClient`, `SecurityContext` và các công cụ giả lập JWT/OAuth2/OIDC.

Sau bài học, bạn có thể:

- Nhận biết kiểu principal mà `@WithMockUser` tạo ra và những dữ liệu nó không thể cung cấp.
- Dùng `@WithUserDetails` để tải principal tùy chỉnh triển khai `UserDetails`.
- Gán principal riêng cho từng request bằng `user(UserDetails)` trong `MockMvc`.
- Tạo annotation test riêng bằng `@WithSecurityContext` và factory.
- Hiểu cách `@AuthenticationPrincipal` xử lý principal sai kiểu.
- Chọn đúng helper cho JWT, OAuth2, OIDC và WebFlux.

## 2. Principal mặc định của @WithMockUser

Ví dụ:

```java
@Test
@WithMockUser(username = "mai", roles = "ADMIN")
void userCanAccessAdminFeature() {
    Authentication authentication = SecurityContextHolder.getContext()
            .getAuthentication();

    assertThat(authentication.getName()).isEqualTo("mai");
    assertThat(authentication.getPrincipal())
            .isInstanceOf(org.springframework.security.core.userdetails.User.class);
    assertThat(authentication.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactly("ROLE_ADMIN");
}
```

Thông thường, context được tạo có:

| Thành phần | Giá trị điển hình |
| --- | --- |
| Kiểu Authentication | `UsernamePasswordAuthenticationToken` |
| Principal | `org.springframework.security.core.userdetails.User` |
| Kiểu principal | Triển khai `UserDetails` mặc định của Spring Security |
| Username | Giá trị từ `username` hoặc `value` |
| Password | Chuỗi giả lập từ thuộc tính `password` |
| Authorities | Được tạo từ `roles` hoặc lấy nguyên văn từ `authorities` |

`@WithMockUser` **không** tạo entity người dùng của ứng dụng, không gọi `UserDetailsService`, và không tự thêm các thuộc tính riêng như `accountId` hoặc `tenantId`. Nó phù hợp khi mục tiêu test chỉ là kiểm tra quy tắc authorization dựa trên username và authorities.

Ví dụ, nếu controller có:

```java
@GetMapping("/me")
String me(@AuthenticationPrincipal AppUserPrincipal principal) {
    return principal.getDisplayName();
}
```

thì principal mặc định từ `@WithMockUser` không phải `AppUserPrincipal`. Việc khai báo `@WithMockUser(username = "mai")` không làm Spring tự chuyển đối tượng `User` sang lớp principal của dự án.

## 3. Điều gì xảy ra khi @AuthenticationPrincipal nhận sai kiểu?

`@AuthenticationPrincipal` lấy đối tượng `Authentication.getPrincipal()` rồi gán vào tham số controller. Nếu principal không tương thích với kiểu tham số, hành vi mặc định là trả về `null`. Nếu đặt `errorOnInvalidType = true`, Spring ném `ClassCastException` để chỉ rõ lỗi kiểu:

```java
@GetMapping("/me")
String me(
        @AuthenticationPrincipal(errorOnInvalidType = true)
        AppUserPrincipal principal) {
    return principal.getDisplayName();
}
```

Với `@WithMockUser`, principal là `User`, vì vậy không tương thích với `AppUserPrincipal`. Nếu không bật `errorOnInvalidType`, controller có thể nhận `null` và lỗi khi truy cập thuộc tính. Nếu bật, lỗi chuyển kiểu được báo rõ hơn.

Không nên sửa test bằng cách ép kiểu:

```java
AppUserPrincipal principal =
        (AppUserPrincipal) SecurityContextHolder.getContext()
                .getAuthentication()
                .getPrincipal();
```

đối với một context được tạo bởi `@WithMockUser`. Ép kiểu không thay đổi đối tượng thực tế; nó chỉ làm lỗi xuất hiện ngay tại dòng cast. Hãy tạo đúng principal mà ứng dụng cần.

## 4. Cách 1: dùng @WithUserDetails nếu principal triển khai UserDetails

Nếu ứng dụng có `UserDetailsService` và service trả về principal tùy chỉnh, `@WithUserDetails` thường là lựa chọn tự nhiên nhất.

### 4.1. Tạo principal tùy chỉnh

```java
public final class AppUserPrincipal implements UserDetails {

    private final Long accountId;
    private final String tenantId;
    private final String username;
    private final String password;
    private final Collection<? extends GrantedAuthority> authorities;

    public AppUserPrincipal(
            Long accountId,
            String tenantId,
            String username,
            String password,
            Collection<? extends GrantedAuthority> authorities) {
        this.accountId = accountId;
        this.tenantId = tenantId;
        this.username = username;
        this.password = password;
        this.authorities = List.copyOf(authorities);
    }

    public Long getAccountId() { return accountId; }
    public String getTenantId() { return tenantId; }

    @Override public String getUsername() { return username; }
    @Override public String getPassword() { return password; }
    @Override public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }
    @Override public boolean isAccountNonExpired() { return true; }
    @Override public boolean isAccountNonLocked() { return true; }
    @Override public boolean isCredentialsNonExpired() { return true; }
    @Override public boolean isEnabled() { return true; }

    public String getDisplayName() {
        return username + "@" + tenantId;
    }
}
```

Principal này có hai thuộc tính riêng là `accountId` và `tenantId`, đồng thời vẫn tuân thủ hợp đồng `UserDetails`. Trong dự án thực tế, constructor có thể nhận entity hoặc DTO đã được service ánh xạ.

### 4.2. UserDetailsService trả về kiểu principal đó

```java
@Service("appUserDetailsService")
class AppUserDetailsService implements UserDetailsService {

    private final AccountRepository accountRepository;

    AppUserDetailsService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account account = accountRepository.findByUsername(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Account not found"));

        List<GrantedAuthority> authorities = account.getAuthorities().stream()
                .map(SimpleGrantedAuthority::new)
                .toList();

        return new AppUserPrincipal(
                account.getId(),
                account.getTenantId(),
                account.getUsername(),
                account.getPasswordHash(),
                authorities
        );
    }
}
```

### 4.3. Dùng @WithUserDetails trong test

Controller có thể nhận đúng kiểu principal và trả các thuộc tính riêng:

```java
record ProfileResponse(Long accountId, String tenantId) {}

@RestController
class ProfileController {

    @GetMapping("/me")
    ProfileResponse me(@AuthenticationPrincipal AppUserPrincipal principal) {
        return new ProfileResponse(
                principal.getAccountId(),
                principal.getTenantId()
        );
    }
}
```

```java
@SpringBootTest
@AutoConfigureMockMvc
class AppProfileSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithUserDetails(
        value = "mai",
        userDetailsServiceBeanName = "appUserDetailsService"
    )
    void controllerReceivesCustomPrincipal() throws Exception {
        Object principal = SecurityContextHolder.getContext()
                .getAuthentication()
                .getPrincipal();

        assertThat(principal).isInstanceOf(AppUserPrincipal.class);
        AppUserPrincipal appUser = (AppUserPrincipal) principal;
        assertThat(appUser.getAccountId()).isEqualTo(42L);
        assertThat(appUser.getTenantId()).isEqualTo("tenant-a");

        mockMvc.perform(get("/me"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accountId").value(42L))
                .andExpect(jsonPath("$.tenantId").value("tenant-a"));
    }
}
```

Điều kiện: user `mai` phải tồn tại trong nguồn dữ liệu của service trước khi annotation được xử lý. Nếu fixture được tạo trong `@BeforeEach`, cân nhắc `setupBefore = TestExecutionEvent.TEST_EXECUTION`. `@WithUserDetails` tải principal do service trả về, nhưng không kiểm tra mật khẩu qua `AuthenticationManager`.

## 5. Cách 2: truyền principal tùy chỉnh cho một request MockMvc

Nếu muốn tạo principal cho từng request mà không cần gọi `UserDetailsService`, có thể dùng request post-processor `user(UserDetails)`:

```java
@Test
void requestUsesCustomPrincipal() throws Exception {
    AppUserPrincipal principal = new AppUserPrincipal(
            42L,
            "tenant-a",
            "mai",
            "{noop}test-only",
            List.of(new SimpleGrantedAuthority("report:read"))
    );

    mockMvc.perform(get("/me").with(user(principal)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.accountId").value(42L));
}
```

Import quan trọng:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
```

Overload `user(UserDetails)` sử dụng chính đối tượng `UserDetails` được truyền vào làm principal cho request test. Đây là cách hữu ích khi:

- Muốn kiểm tra nhiều tenant hoặc account ID khác nhau trong cùng lớp test.
- Không cần kiểm tra `UserDetailsService` hoặc repository.
- Muốn tạo nhanh các trường hợp principal tùy chỉnh mà không seed database.

Lưu ý: `user(principal)` là request post-processor của `MockMvc`, không phải thuộc tính của `@WithMockUser`. Khi dùng cách này, mỗi request có danh tính được gắn trực tiếp vào request; không nhầm với annotation thiết lập context theo vòng đời phương thức test.

## 6. Cách 3: tạo annotation riêng bằng @WithSecurityContext

Khi principal cần dữ liệu riêng nhưng không muốn phụ thuộc database hoặc muốn tái sử dụng fixture trên nhiều test, có thể tạo annotation tùy chỉnh. Spring Security Test hỗ trợ meta-annotation `@WithSecurityContext`, liên kết annotation với một factory tạo `SecurityContext`.

### 6.1. Định nghĩa annotation

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = WithAppUserSecurityContextFactory.class)
public @interface WithAppUser {
    long accountId() default 42L;
    String tenantId() default "tenant-a";
    String username() default "mai";
    String[] authorities() default {"report:read"};
}
```

### 6.2. Factory tạo SecurityContext

```java
public class WithAppUserSecurityContextFactory
        implements WithSecurityContextFactory<WithAppUser> {

    @Override
    public SecurityContext createSecurityContext(WithAppUser annotation) {
        List<GrantedAuthority> authorities =
                Arrays.stream(annotation.authorities())
                        .map(SimpleGrantedAuthority::new)
                        .toList();

        AppUserPrincipal principal = new AppUserPrincipal(
                annotation.accountId(),
                annotation.tenantId(),
                annotation.username(),
                "{noop}test-only",
                authorities
        );

        Authentication authentication =
                new UsernamePasswordAuthenticationToken(
                        principal,
                        principal.getPassword(),
                        principal.getAuthorities()
                );

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
```

Factory tạo một authentication đã xác thực bằng constructor ba tham số của `UsernamePasswordAuthenticationToken`, rồi đặt vào context mới. Không dùng constructor hai tham số trong trường hợp này vì constructor đó tạo token chưa xác thực.

### 6.3. Sử dụng annotation

```java
@Test
@WithAppUser(
    accountId = 100L,
    tenantId = "tenant-b",
    username = "linh",
    authorities = {"report:read", "report:approve"}
)
void customAnnotationBuildsPrincipal() {
    AppUserPrincipal principal = (AppUserPrincipal)
            SecurityContextHolder.getContext()
                    .getAuthentication()
                    .getPrincipal();

    assertThat(principal.getAccountId()).isEqualTo(100L);
    assertThat(principal.getTenantId()).isEqualTo("tenant-b");
    assertThat(principal.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder("report:read", "report:approve");
}
```

Các import cho factory:

```java
import java.util.Arrays;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContext;
import org.springframework.security.test.context.support.WithSecurityContextFactory;
```

Với annotation tự tạo, cần khai báo `@Retention(RUNTIME)` để Spring Test đọc được, và `@Target` phù hợp nếu muốn đặt ở phương thức hoặc lớp. Có thể thêm thuộc tính `setupBefore` trong `@WithSecurityContext` nếu cần thay đổi thời điểm thiết lập context.

## 7. So sánh ba cách tạo principal tùy chỉnh

| Cách | Nguồn principal | Cần UserDetailsService? | Phù hợp khi |
| --- | --- | --- | --- |
| `@WithUserDetails` | Service tải theo username | Có | Muốn dùng principal và authorities do ứng dụng cung cấp |
| `.with(user(customUserDetails))` | Đối tượng test tạo cho request | Không | Mỗi request cần fixture riêng, không cần kiểm thử service |
| `@WithSecurityContext` | Factory tùy chỉnh | Không bắt buộc | Muốn tái sử dụng annotation và tạo authentication/principal đặc biệt |

`@WithMockUser` vẫn là lựa chọn tốt khi chỉ cần username và quyền đơn giản. Không cần thay tất cả test sang principal tùy chỉnh nếu controller không sử dụng các trường riêng.

## 8. Kiểm thử phân quyền cùng principal tùy chỉnh

Principal tùy chỉnh thường chứa thêm tenant hoặc account ID. Kiểm thử không nên chỉ xác nhận controller đọc được các trường đó; hãy kiểm tra chính sách có sử dụng đúng dữ liệu.

Ví dụ service:

```java
@PreAuthorize("@tenantAccess.canRead(#tenantId, authentication.principal)")
public Report loadReport(String tenantId) {
    // ...
}
```

Trong test, tạo principal với tenant cụ thể rồi xác minh:

| Principal | Tenant của tài nguyên | Kết quả mong đợi |
| --- | --- | --- |
| `accountId=42, tenantId=tenant-a` | `tenant-a` | Được phép |
| `accountId=42, tenantId=tenant-a` | `tenant-b` | Bị từ chối |
| Principal thiếu tenant | `tenant-a` | Bị từ chối hoặc lỗi xác thực theo hợp đồng |
| Anonymous principal | `tenant-a` | Không được truy cập tài nguyên riêng tư |

Nếu dùng `@PreAuthorize`, bật method security và gọi bean qua Spring proxy. Nếu kiểm tra qua HTTP, dùng `MockMvc` với security filter thật để xác minh cả authentication lẫn authorization.

## 9. Giới hạn với JWT, OAuth2 và OIDC

Không phải mọi principal đều triển khai `UserDetails`. Với Resource Server JWT, principal thường là `Jwt`; với OAuth2 Login có thể là `OAuth2User`; với OIDC Login là `OidcUser`. `@WithUserDetails` không tự tạo những kiểu này chỉ vì chúng có username hoặc authorities.

| Kiểu principal ứng dụng cần | Công cụ Spring Security Test phù hợp |
| --- | --- |
| `UserDetails` tùy chỉnh | `@WithUserDetails`, `user(customUserDetails)` |
| `Jwt` | `jwt()` trong MockMvc, `mockJwt()` trong WebTestClient |
| `OAuth2User` | `oauth2Login()` hoặc configurer OAuth2 tương ứng |
| `OidcUser` | `oidcLogin()` |
| `Authentication` hoặc principal hoàn toàn tùy biến | `@WithSecurityContext` hoặc request post-processor tùy chỉnh |

Ví dụ JWT:

```java
mockMvc.perform(get("/api/reports")
        .with(jwt().jwt(jwt -> jwt
                .subject("client-42")
                .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isOk());
```

Helper `jwt()` tạo authentication JWT giả lập để kiểm tra authorization. Nó không xác minh chữ ký, issuer, audience hoặc thời hạn của token thật. Nếu ứng dụng chuyển claim `tenant_id` thành thuộc tính trong principal tùy biến, cần kiểm tra riêng bộ chuyển đổi JWT/converter đó.

## 10. Reactive: kiểm thử principal và context với WebTestClient

Spring WebFlux truyền security context qua Reactor Context. Các helper của `WebTestClient` cho phép thiết lập user hoặc JWT giả lập theo request. Ví dụ user đơn giản:

```java
webTestClient
    .mutateWith(mockUser().roles("USER"))
    .get()
    .uri("/me")
    .exchange()
    .expectStatus().isOk();
```

Hoặc với JWT:

```java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("client-42")
            .claim("tenant_id", "tenant-a")
    ))
    .get()
    .uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

Các đoạn trên là khung minh họa; cần cấu hình `WebTestClient` với Spring Security và các controller/security chain Reactive của ứng dụng. Khi ứng dụng chỉ dùng `ReactiveUserDetailsService`, `@WithUserDetails` đồng bộ không thể tự gọi service trả về `Mono<UserDetails>`; hãy dùng configurer Reactive hoặc viết fixture chuyên biệt.

`mockUser()` tạo danh tính mock theo mô hình user thông thường; không giả định nó tự tạo được mọi lớp principal riêng của ứng dụng. Nếu controller Reactive yêu cầu `AppUserPrincipal`, hãy kiểm thử luồng xác thực Reactive hoặc bộ chuyển đổi tạo principal đó với fixture phù hợp, rồi xác nhận kiểu principal và thuộc tính qua endpoint. Với JWT, dùng `mockJwt()` khi controller mong đợi `Jwt`; nếu cần một principal tùy chỉnh được ánh xạ từ claim, kiểm tra riêng bước ánh xạ.

Tránh đọc `SecurityContextHolder` theo giả định context luôn nằm trên thread hiện tại trong WebFlux. Hãy kiểm tra kết quả qua `WebTestClient` hoặc truy cập Reactor Context theo cơ chế Spring Security Reactive.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@WithMockUser` làm `@AuthenticationPrincipal AppUserPrincipal` nhận null | Principal mặc định là Spring `User` | Dùng `@WithUserDetails`, `user(customUserDetails)` hoặc custom factory |
| Ép kiểu principal bị `ClassCastException` | Kiểu runtime không tương thích | Kiểm tra `Authentication.getPrincipal()` trước khi cast |
| `@WithUserDetails` không tìm thấy bean | Test context thiếu service | Nạp bean bằng test config hoặc dùng `@SpringBootTest` |
| Principal tùy chỉnh thiếu field | Service/factory chưa ánh xạ field | Kiểm tra constructor và mapper |
| Authorities đúng nhưng tenant bị sai | Test chỉ cấp role mà không dựng tenant context | Tạo principal với tenant đúng và kiểm tra policy |
| `@WithSecurityContext` không được nhận diện | Annotation thiếu retention/runtime hoặc factory sai generic | Kiểm tra meta-annotation, `@Retention`, factory |
| Test JWT nhưng controller yêu cầu `AppUserPrincipal` | JWT helper tạo principal JWT | Dùng JWT converter phù hợp hoặc test đúng kiểu principal |
| WebFlux không thấy principal | Chưa tích hợp security configurer/Reactor Context | Cấu hình `WebTestClient` với Spring Security |

Khi test thất bại, hãy xác minh theo thứ tự: **kiểu runtime của principal → nguồn tạo principal → authorities → thuộc tính nghiệp vụ → security chain hoặc method security**. Cách này tách lỗi sai kiểu principal khỏi lỗi phân quyền.

## 12. Bài tập thực hành

Ứng dụng đa tenant có `AppUserPrincipal` gồm `accountId`, `tenantId`, `username` và authorities. Endpoint:

- `GET /tenant/{tenantId}/reports` yêu cầu `report:read` và người dùng thuộc đúng tenant.
- `POST /tenant/{tenantId}/reports/publish` yêu cầu `report:publish` và CSRF hợp lệ.

Hãy thực hiện:

1. Tạo `AppUserPrincipal implements UserDetails` với `accountId` và `tenantId`.
2. Dùng `UserDetailsService` trả về principal đó; viết test bằng `@WithUserDetails`.
3. Dùng `user(customUserDetails)` để tạo hai request có tenant khác nhau và so sánh kết quả.
4. Tạo annotation `@WithAppUser` bằng `@WithSecurityContext` để tái sử dụng fixture.
5. Viết ca đúng tenant được phép và sai tenant bị từ chối.
6. Thử `@WithMockUser` trên controller yêu cầu `AppUserPrincipal`; xác định hành vi khi principal sai kiểu.
7. Nếu API dùng JWT, tạo test `jwt()` và kiểm tra claim `tenant_id`; viết test riêng cho converter ánh xạ claim thành principal/authority.

**Câu hỏi tự kiểm tra:** Có thể dùng `@WithMockUser(username = "mai")` rồi ép principal thành `AppUserPrincipal` không? **Không.** Annotation này tạo principal mặc định kiểu `User`; muốn principal tùy chỉnh, hãy tạo đúng kiểu bằng `@WithUserDetails`, request post-processor hoặc `@WithSecurityContext`.

## 13. Ghi nhớ

`@WithMockUser` chỉ tạo principal mặc định kiểu `org.springframework.security.core.userdetails.User`, vì vậy nó không thể cung cấp các trường riêng của principal ứng dụng. Khi principal tùy chỉnh triển khai `UserDetails`, dùng `@WithUserDetails` để tải từ service hoặc `user(customUserDetails)` để gắn vào từng request `MockMvc`. Khi cần factory riêng, tạo annotation bằng `@WithSecurityContext`. Với JWT/OAuth2/OIDC, chọn helper tương ứng với kiểu principal; và luôn kiểm tra cả kiểu principal lẫn authorities trước khi kết luận endpoint được bảo vệ đúng.
