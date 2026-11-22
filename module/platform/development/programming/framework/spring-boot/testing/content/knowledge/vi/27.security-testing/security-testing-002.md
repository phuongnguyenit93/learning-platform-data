# @WithMockUser, anonymous và danh tính tùy chỉnh trong Spring Boot Testing

## 1. Vì sao phải kiểm thử theo danh tính?

Một endpoint Spring Boot có Spring Security không chỉ phụ thuộc request path và body. Kết quả còn phụ thuộc **người gọi**, trạng thái xác thực và quyền mà họ sở hữu.

Ví dụ hệ thống quản lý tài nguyên theo tenant:

- Anonymous được phép gọi `GET /api/public` nhưng bị chặn ở `GET /api/me`.
- User bình thường truy cập tài nguyên công khai/riêng của mình, nhưng không được truy cập `/api/admin`.
- Admin có `ROLE_ADMIN` được vào `/api/admin`.
- Service đọc dữ liệu tenant chỉ chấp nhận principal chứa `tenantId` và authority `TENANT_READ`.
- Một request `POST` của user hợp lệ vẫn có thể bị `403` vì thiếu CSRF token.

Nếu tất cả tests chạy dưới một tài khoản ADMIN hoặc tắt filters để làm controller test “xanh”, những ranh giới quan trọng này sẽ không được kiểm.

Spring Security Test cung cấp ba nhóm công cụ thiết yếu:

1. **`@WithMockUser`**: giả lập user có username, roles, authorities, không cần tài khoản tồn tại trong DB.
2. **`@WithAnonymousUser`**: tạo danh tính anonymous để test policy chưa đăng nhập và ghi đè user class-level.
3. **`@WithUserDetails` / `@WithSecurityContext`**: tạo principal tùy chỉnh, chứa tenant ID hoặc kiểu Authentication mà ứng dụng thật cần.

Các annotation này phù hợp với **method-security tests** và **MockMvc tests được cấu hình Spring Security**. Chúng **không** tự gửi credentials qua một HTTP request thật tới server chạy trên thread khác.

### Mục tiêu học tập

Sau bài, bạn có thể:

- Giải thích `Authentication`, `SecurityContext`, principal, roles, authorities và anonymous token.
- Phân biệt authentication (đã xác định danh tính) với authorization (có được phép hay không).
- Kiểm `401`, `403` và `200` theo authentication entry point/policy hiện hành.
- Viết `@WithMockUser(username=...,roles=...)` và `@WithMockUser(authorities=...)` đúng.
- Dùng `@WithAnonymousUser` ở class/method và request postprocessor `anonymous()`.
- Hiểu vì sao `@WithMockUser` thường **không** trả về kiểu `AppPrincipal` riêng của ứng dụng.
- Dùng `@WithUserDetails` để đọc principal từ bean `UserDetailsService` thật.
- Tự tạo `@WithTenantIdentity` bằng `@WithSecurityContext` và `WithSecurityContextFactory`.
- Chạy MockMvc với security filters, CSRF và request-level user.
- Chạy HTTP thật bằng Basic credentials, không dựa vào SecurityContext của JUnit thread.
- Tránh những false positives khi test JWT, password, role/tenant authorization và async/reactive security.

## 2. Authentication không phải Authorization

**Authentication** trả lời: “Đang gọi là ai?”. Spring Security dùng `Authentication` nằm trong `SecurityContext`, có thể là `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken` hoặc `AnonymousAuthenticationToken`.

**Authorization** trả lời: “Danh tính này có quyền thực hiện thao tác không?”. Quy tắc có thể xét `hasRole("ADMIN")`, `hasAuthority("TENANT_READ")`, resource ownership, tenant, scope hoặc annotation `@PreAuthorize`.

~~~text
SecurityContextHolder
        |
        +-- SecurityContext
                |
                +-- Authentication
                        |-- principal: User / AppPrincipal / Jwt ...
                        |-- name: alice
                        |-- authorities:
                        |      ROLE_USER
                        |      TENANT_READ
                        |-- credentials
                        |-- authenticated
~~~

Hai quy tắc khác nhau:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public String adminOnly() {
    return "admin";
}

@PreAuthorize("hasAuthority('TENANT_READ')")
public String tenantInfo() {
    return "tenant";
}
~~~

Các method trên chỉ là **mẫu minh họa**, chưa thuộc project hoàn chỉnh. `hasRole("ADMIN")` thường tìm authority `ROLE_ADMIN`; `hasAuthority("TENANT_READ")` tìm đúng chuỗi `TENANT_READ`.

**Đừng suy từ một test login thành công rằng mọi tài nguyên đã được phân quyền đúng.** Phải có negative tests cho thiếu role, thiếu authority, anonymous và cross-tenant.

## 3. Anonymous không đồng nghĩa authentication == null

Khi servlet security filter chain bật anonymous authentication, một request chưa đăng nhập có thể được biểu diễn bằng `AnonymousAuthenticationToken`. Token này có thể có `isAuthenticated() == true` theo implementation, nhưng Spring Security vẫn xem nó là anonymous thông qua `AuthenticationTrustResolver`.

Do đó:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

boolean reallyLoggedIn =
        authentication != null && authentication.isAuthenticated();
~~~

là **cách không đủ tin cậy** để xác định user đã login trong mọi trường hợp.

Dùng chính authorization rules của Spring Security như `authenticated()`/`anonymous()`, hoặc khi cần phân tích thủ công:

~~~java
AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

boolean anonymous = resolver.isAnonymous(authentication);
~~~

Các đoạn trên là mẫu Java, cần imports và context phù hợp.

### 3.1 Phân biệt ba trạng thái

| Trạng thái | Ví dụ | Hệ quả có thể xảy ra |
| --- | --- | --- |
| Không có `Authentication` | Gọi trực tiếp secured service trong test chưa set identity | `AuthenticationCredentialsNotFoundException` |
| Có `AnonymousAuthenticationToken` | `@WithAnonymousUser` hoặc anonymous filter | Phần lớn protected operations bị từ chối |
| Có authenticated user/token | `@WithMockUser`, `@WithUserDetails`, Basic/Bearer thực | Còn phải kiểm authorization |

HTTP `401` và `403` không phải constants bất biến cho mọi security config. Ứng dụng `httpBasic()` trong ví dụ này trả `401` cho unauthenticated requests tới protected URL và thường `403` khi authenticated nhưng không đủ quyền. Form-login có thể redirect, còn resource-server có thể trả `WWW-Authenticate` phù hợp.

## 4. Spring Security Test hoạt động ở đâu?

Spring Security Test tích hợp với Spring TestContext qua `WithSecurityContextTestExecutionListener`. Listener thiết lập `SecurityContextHolder` trước test và dọn sau test. Nếu method security là reactive, còn cần integration với `ReactorContextTestExecutionListener` và reactive security context.

~~~text
Spring TestContext
     |
     +-- WithSecurityContextTestExecutionListener
     |       |
     |       +-- đọc @WithMockUser / @WithUserDetails
     |       +-- tạo SecurityContext cho test thread
     |       +-- chạy test code / MockMvc
     |       +-- clear test SecurityContext sau test
     |
     +-- test method / assertions
~~~

**SecurityContext của test thread ≠ session hoặc token thật của HTTP server.** Khi `@SpringBootTest(RANDOM_PORT)` xử lý request qua TCP trên server thread, request phải tự mang Basic/Bearer/cookie cần thiết.

### 4.1 Phạm vi công cụ

| Công cụ | Principal được tạo | Dùng khi nào |
| --- | --- | --- |
| `@WithMockUser` | Spring Security `User` | Username, role, authority tests cơ bản |
| `@WithAnonymousUser` | Anonymous token | Kiểm anonymous, ghi đè class-level user |
| `@WithUserDetails` | UserDetails từ UserDetailsService bean | Cần đúng principal custom của ứng dụng |
| `@WithSecurityContext` | Tùy factory | Cần tenant ID, claims, Authentication type riêng |
| `with(user(...))` | Identity theo một MockMvc request | Một test cần nhiều users |
| `with(anonymous())` | Anonymous theo request | Kiểm route công khai/protected |
| `with(authentication(...))` | Custom Authentication theo request | Test các token tự tạo |
| `with(csrf())` | CSRF token test hợp lệ | POST/PUT/PATCH/DELETE khi CSRF bật |
| `with(jwt())` | JWT Authentication giả lập | Kiểm authorization resource server, không kiểm chữ ký JWT |

## 5. @WithMockUser: mặc định và biến thể

Ví dụ:

~~~java
@Test
@WithMockUser
void defaultMockUser() {
    // username "user"
    // mock password "password"
    // authority ROLE_USER
}
~~~

`@WithMockUser` tạo một `UsernamePasswordAuthenticationToken` với principal kiểu `org.springframework.security.core.userdetails.User`. User **không cần có trong database/UserDetailsService**; password cũng **không qua login hay PasswordEncoder**.

### 5.1 Username

~~~java
@WithMockUser(username = "minh")
~~~

Tên authentication mà test nhìn thấy thường là `minh`.

### 5.2 roles vs authorities

~~~java
@WithMockUser(roles = "ADMIN")
~~~

Tạo authority `ROLE_ADMIN`.

~~~java
@WithMockUser(authorities = "ADMIN")
~~~

Tạo authority `ADMIN`, **không** thêm `ROLE_`. Vì vậy nếu URL dùng `hasRole("ADMIN")`, trường hợp đầu PASS còn trường hợp sau thường bị từ chối. Có thể khai báo:

~~~java
@WithMockUser(authorities = "ROLE_ADMIN")
~~~

để cấp trực tiếp authority có prefix phù hợp.

**Không** khai báo `roles="ROLE_ADMIN"` nếu dùng prefix mặc định: tham số `roles` nhận tên vai trò **không có** `ROLE_`. Nếu ứng dụng tùy chỉnh role prefix, phải kiểm lại đúng configuration.

### 5.3 Giới hạn custom principal

Nếu code production ép:

~~~java
AppPrincipal p = (AppPrincipal) SecurityContextHolder
        .getContext().getAuthentication().getPrincipal();
~~~

thì `@WithMockUser` mặc định có thể gây `ClassCastException` vì principal thật là `User`, không phải `AppPrincipal`. Với service đọc `tenantId`, dùng `@WithUserDetails` hoặc `@WithSecurityContext` phù hợp.

## 6. @WithAnonymousUser, class-level override và meta-annotations

~~~java
@WithMockUser(username = "default-member")
class ExampleTests {

    @Test
    void usesDefaultMember() {
        // default-member
    }

    @Test
    @WithAnonymousUser
    void methodIsAnonymous() {
        // Method annotation ghi đè class-level user.
    }
}
~~~

Đây là mẫu, cần Spring test context phù hợp. `@WithAnonymousUser` hữu ích khi đa số tests chạy với một user nhưng có vài trường hợp “chưa đăng nhập”.

Có thể tạo meta-annotation để giảm lặp:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@WithMockUser(username = "auditor", authorities = "REPORT_READ")
public @interface WithAuditor {
}
~~~

Đoạn trên là mẫu minh họa. Meta-annotation dùng `@WithMockUser` vẫn tạo principal kiểu `User`; nếu cần tenant ID/domain principal, meta-annotation phải dùng factory custom hoặc `@WithUserDetails`.

**Đừng** đặt `@WithMockUser(roles="ADMIN")` lên tất cả tests vì dễ bỏ sót nguyên tắc least privilege. Phải có ít nhất một test không đủ quyền.

## 7. @WithUserDetails: khi identity phải đến từ UserDetailsService

`@WithUserDetails` gọi `UserDetailsService.loadUserByUsername(...)` để nạp đúng đối tượng `UserDetails` mà bean trả về.

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "demoUsers")
void worksWithActualAppPrincipalType() {
    // AppPrincipal được trả từ demoUsers.
}
~~~

Các điều kiện:

- Context có bean `UserDetailsService` thích hợp.
- Username test tồn tại; nếu không, setup thất bại từ test listener.
- Nếu nhiều UserDetailsService beans, chỉ định `userDetailsServiceBeanName`.
- UserDetailsService thực trả về AppPrincipal nếu code cần AppPrincipal.
- Factory khởi tạo identity trước khi test chạy; không phải login qua network.

**Không kiểm mật khẩu.** Dù `UserDetailsService` đọc account thật, `@WithUserDetails` bỏ qua bước authenticate password/Basic/token. Muốn kiểm login provider, phải có test gửi credentials qua HTTP hoặc đi qua AuthenticationManager thật.

### 7.1 User được seed trong @BeforeEach: chú ý setupBefore

Mặc định security test listener tạo context ở sự kiện `TestExecutionEvent.TEST_METHOD`, tức **trước JUnit @BeforeEach**. Nếu user chỉ được seed vào database trong `@BeforeEach`, `@WithUserDetails` có thể tìm user quá sớm.

Có thể dùng:

~~~java
@WithUserDetails(
    value = "alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
~~~

để thiết lập context sau `@BeforeEach`, trước `@Test`. Phải kiểm thêm fixture transaction visibility nếu service đọc database từ connection khác. Không dùng `@BeforeAll` để giả định SecurityContext của từng method đã có.

## 8. @WithSecurityContext: custom annotation có tenant và authorities

Một ứng dụng đa tenant có thể dùng principal chứa username, tenantId và authorities. Không muốn test nào cũng gọi user store? Tạo annotation:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(factory = WithTenantIdentityFactory.class)
public @interface WithTenantIdentity {
    String username() default "tenant-user";
    String tenantId() default "tenant-default";
    String[] authorities() default {"ROLE_USER", "TENANT_READ"};
}
~~~

Factory tạo `SecurityContext` mới và `Authentication` đúng principal:

~~~java
@Override
public SecurityContext createSecurityContext(
        WithTenantIdentity config) {

    SecurityContext context =
            SecurityContextHolder.createEmptyContext();

    AppPrincipal principal = new AppPrincipal(
            config.username(),
            config.tenantId(),
            "not-used-for-login",
            config.authorities());

    Authentication authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                    principal, "N/A", principal.getAuthorities());

    context.setAuthentication(authentication);
    return context;
}
~~~

Hai đoạn trên được cung cấp thành files Java hoàn chỉnh ở phần thực hành.

**Không giữ static mutable SecurityContext**: có thể rò danh tính từ test này sang test khác, nhất là với concurrency. Test factory chỉ thể hiện **identity giả định**, không chứng minh user thật có thể nhận những authorities đó từ IDP hay user store.

## 9. MockMvc và security filters: điều kiện để test có ý nghĩa

`MockMvc` giúp gửi mock servlet requests vào MVC controller mà không mở socket TCP. Nhưng muốn test security, cần Spring Security filter chain và test support.

Hai cách thường dùng:

~~~java
// Full app context trong Spring Boot tests:
@SpringBootTest
@AutoConfigureMockMvc
class SecurityMvcTest {
    @Autowired MockMvc mvc;
}
~~~

Hoặc cấu hình MockMvc thủ công:

~~~java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
~~~

Đây là mẫu minh họa, cần imports/context. Nếu dùng `MockMvcBuilders.standaloneSetup(controller)` mà **không gắn Security filters**, controller có thể 200 khi production sẽ 401/403.

### 9.1 Request-scoped users

Một test có thể giả hai users trong hai requests:

~~~java
mvc.perform(get("/api/me")
        .with(user("alice").roles("USER")))
        .andExpect(status().isOk());

mvc.perform(get("/api/me")
        .with(anonymous()))
        .andExpect(status().isUnauthorized());
~~~

Các request postprocessors nằm trong `SecurityMockMvcRequestPostProcessors`. `with(user(...))` không xác minh password hay user existence, chỉ cấu hình identity của request MockMvc. `with(authentication(authentication))` và `with(securityContext(context))` hỗ trợ token tự tạo.

## 10. CSRF: một 403 không phải lúc nào cũng là sai role

Với Spring Security servlet CSRF protection đang bật, một authenticated user gửi `POST` thiếu CSRF token có thể bị chặn `403` dù permission của họ hợp lệ.

~~~java
@Test
@WithMockUser
void postWithoutCsrfFails() throws Exception {
    mvc.perform(post("/api/write"))
            .andExpect(status().isForbidden());
}

@Test
@WithMockUser
void postWithCsrfPasses() throws Exception {
    mvc.perform(post("/api/write").with(csrf()))
            .andExpect(status().isOk());
}
~~~

`csrf()` chỉ tạo **test CSRF token** cho MockMvc request; không kiểm cách browser nhận cookie/session hoặc cách frontend truyền token. Có thể dùng `csrf().useInvalidToken()` để kiểm token không hợp lệ.

**Không tắt security filters/CSRF chỉ để làm bài test PASS** nếu mục tiêu bài test là behavior bảo mật. Với API stateless dùng bearer tokens, CSRF policy có thể khác và cần bám threat model/config thật.

## 11. Cấu trúc bộ ví dụ Java 17+ / Spring Boot 3.5.x

Bộ thực hành có **năm production classes**, **hai test-support classes** và **bốn test classes**, kiểm cả MockMvc, method-security và HTTP thật.

~~~text
security-testing-demo/
  settings.gradle
  build.gradle
  src/
    main/java/example/security/
      SecurityDemoApplication.java
      AppPrincipal.java
      SecurityConfiguration.java
      TenantService.java
      IdentityController.java
    test/java/example/security/
      WithTenantIdentity.java
      WithTenantIdentityFactory.java
      SecurityMvcTest.java
      MethodSecurityTest.java
      ClassLevelIdentityTest.java
      LiveHttpIdentityTest.java
~~~

Mọi Java file thuộc `package example.security`. Ví dụ không cần DB/Docker, có `UserDetailsService` in-memory của demo. Những credentials cố định trong demo **không được dùng trong production**.

### 11.1 settings.gradle

~~~groovy
rootProject.name = 'security-testing-demo'
~~~

### 11.2 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là file `build.gradle` đầy đủ về plugins/dependencies cần cho mini-project. Cần Gradle wrapper hoặc Gradle tương thích để chạy. Các versions được pin cho ví dụ, **không tuyên bố là phiên bản mới nhất**. Bộ test dùng Servlet MVC + Spring Security 6.5.x, không phải WebFlux.

## 12. Production Java: SecurityDemoApplication.java

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

Root package bảo đảm các components, SecurityFilterChain và services được Spring Boot quét đúng.

## 13. Production Java: AppPrincipal.java

~~~java
package example.security;

import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.userdetails.UserDetails;

public final class AppPrincipal implements UserDetails {

    private final String username;
    private final String tenantId;
    private final String password;
    private final List<GrantedAuthority> authorities;

    public AppPrincipal(
            String username,
            String tenantId,
            String password,
            String... authorities) {
        this.username = Objects.requireNonNull(username);
        this.tenantId = Objects.requireNonNull(tenantId);
        this.password = Objects.requireNonNull(password);
        this.authorities = List.copyOf(
                AuthorityUtils.createAuthorityList(authorities));
    }

    public String tenantId() {
        return tenantId;
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public String getPassword() {
        return password;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}
~~~

`AppPrincipal` có domain field `tenantId`. Trong ứng dụng thật, có thể thêm userId bất biến và trạng thái enabled/locked thực tế. `isEnabled()==true` chỉ dùng để đơn giản hóa demo; không thể coi đây là mẫu quản lý account production.

## 14. Production Java: SecurityConfiguration.java

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .requestMatchers(
                                "/api/me",
                                "/api/tenant",
                                "/api/write").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean("demoUsers")
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        // DEMO-ONLY: Không dùng tài khoản này trong production.
        String hash = encoder.encode("demo-pass");

        return username -> switch (username) {
            case "alice" -> new AppPrincipal(
                    "alice", "tenant-blue", hash,
                    "ROLE_USER", "TENANT_READ");
            case "root" -> new AppPrincipal(
                    "root", "tenant-ops", hash,
                    "ROLE_ADMIN", "TENANT_READ");
            default -> throw new UsernameNotFoundException(
                    "User not found");
        };
    }
}
~~~

- `httpBasic()` tạo authentication mechanism dùng cho live HTTP tests.
- `/api/public` là public, `/api/admin` yêu cầu ROLE_ADMIN, endpoints còn lại yêu cầu authenticated.
- `@EnableMethodSecurity` cho phép `@PreAuthorize` trên service.
- `demoUsers` trả **AppPrincipal thật của demo**, không phải Spring Security User.
- Password được encode; không dùng plaintext production store.
- CSRF vẫn bật theo servlet security defaults, nên POST test cần token.

### 14.1 Đừng xem in-memory demo users là giải pháp production

Mục tiêu là minh họa việc `@WithUserDetails` và HTTP Basic dùng cùng user service. Production cần user store/IDP đáng tin, secrets quản lý an toàn, account status, login throttling, token validity và audit.

## 15. Production Java: TenantService.java

~~~java
package example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class TenantService {

    @PreAuthorize("hasAuthority('TENANT_READ')")
    public String currentTenant() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (!(authentication.getPrincipal()
                instanceof AppPrincipal principal)) {
            throw new IllegalStateException(
                    "AppPrincipal required");
        }

        return principal.tenantId();
    }
}
~~~

`@PreAuthorize` kiểm quyền trước method body. Sau đó method yêu cầu principal là `AppPrincipal` để trả tenantId.

Vì vậy:

- `@WithMockUser(roles="USER")`: không có TENANT_READ → denied trước method body.
- `@WithMockUser(authorities="TENANT_READ")`: qua check authority nhưng principal vẫn là `User` → `IllegalStateException`.
- `@WithUserDetails("alice")` hoặc `@WithTenantIdentity`: principal là AppPrincipal và có TENANT_READ → thành công.

Đây là cách tạo negative tests giúp phát hiện cả lỗi quyền lẫn lỗi identity type.

## 16. Production Java: IdentityController.java

~~~java
package example.security;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final TenantService tenants;

    public IdentityController(TenantService tenants) {
        this.tenants = tenants;
    }

    @GetMapping("/api/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/api/me")
    public String currentUser(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }

    @GetMapping("/api/tenant")
    public String tenant() {
        return tenants.currentTenant();
    }

    @PostMapping("/api/write")
    public String write() {
        return "saved";
    }
}
~~~

`/api/write` không thực hiện ghi DB; nó dùng để test CSRF. Nếu sản phẩm cần dữ liệu tenant, service/repository thực phải lọc theo tenant từ verified principal, không tin tenantId từ request parameter một cách vô điều kiện.

## 17. Test-only custom annotation và factory

### 17.1 WithTenantIdentity.java

~~~java
package example.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.test.context.support.WithSecurityContext;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(factory = WithTenantIdentityFactory.class)
public @interface WithTenantIdentity {
    String username() default "tenant-user";
    String tenantId() default "tenant-default";
    String[] authorities() default {"ROLE_USER", "TENANT_READ"};
}
~~~

### 17.2 WithTenantIdentityFactory.java

~~~java
package example.security;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithTenantIdentityFactory
        implements WithSecurityContextFactory<WithTenantIdentity> {

    @Override
    public SecurityContext createSecurityContext(
            WithTenantIdentity config) {

        AppPrincipal principal = new AppPrincipal(
                config.username(),
                config.tenantId(),
                "not-used-for-login",
                config.authorities());

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        principal, "N/A", principal.getAuthorities());

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
~~~

Factory mới tạo `SecurityContext` mỗi lần, không chia sẻ static Authentication. Nó cấp authorities theo annotation **chỉ để test authorization**. Việc giả lập identity như vậy không chứng minh production provider có thể xác thực password/JWT hay tenant claim.

## 18. SecurityMvcTest.java: 14 phương thức JUnit

File `src/test/java/example/security/SecurityMvcTest.java`:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void publicWithoutLogin() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void protectedWithoutLogin() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithAnonymousUser
    void anonymousCanReadPublic() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk());
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadPrivate() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "mika")
    void mockUsernameAppearsInResponse() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("mika"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotReadAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void roleAdminCanReadAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
                .andExpect(status().isOk())
                .andExpect(content().string("admin"));
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void plainAuthorityIsNotRoleAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithUserDetails(
        value = "alice",
        userDetailsServiceBeanName = "demoUsers")
    void withUserDetailsLoadsTenantPrincipal() throws Exception {
        mvc.perform(get("/api/tenant"))
                .andExpect(status().isOk())
                .andExpect(content().string("tenant-blue"));
    }

    @Test
    @WithTenantIdentity(tenantId = "tenant-red")
    void customAnnotationProvidesTenant() throws Exception {
        mvc.perform(get("/api/tenant"))
                .andExpect(status().isOk())
                .andExpect(content().string("tenant-red"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void missingTenantReadIsForbidden() throws Exception {
        mvc.perform(get("/api/tenant"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void postWithoutCsrfFails() throws Exception {
        mvc.perform(post("/api/write"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void postWithCsrfPasses() throws Exception {
        mvc.perform(post("/api/write").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("saved"));
    }

    @Test
    @WithMockUser(username = "annotation-user")
    void requestLevelIdentityOverridesTestAnnotation()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(user("per-request").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("per-request"));
    }
}
~~~

**14 `@Test`**, dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để giữ filter chain và method-security proxy thật. Không tắt filters, không mock TenantService, không cần network thật.

### 18.1 Kết quả cần hiểu

- No auth/anonymous tới private URL → `401` trong HTTP Basic config.
- Role USER tới admin URL → `403`.
- Role ADMIN tới admin URL → `200`.
- Authority `ADMIN` không tự thành `ROLE_ADMIN` → `403`.
- `@WithUserDetails` và custom annotation có AppPrincipal → trả tenant đúng.
- Authenticated user thiếu `TENANT_READ` → `403` từ method security.
- POST thiếu CSRF → `403` ngay cả khi có mock user.
- POST có valid CSRF → `200`.
- Request-specific `user("per-request")` ghi đè identity cho request đó.

Nếu một test fail khác kỳ vọng, kiểm entry point/security configuration chứ không nên đổi expected statuses mù quáng.

## 19. MethodSecurityTest.java: 7 phương thức JUnit

File `src/test/java/example/security/MethodSecurityTest.java`:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class MethodSecurityTest {

    @Autowired TenantService tenants;

    @Test
    void noAuthenticationFails() {
        assertThrows(
                AuthenticationCredentialsNotFoundException.class,
                () -> tenants.currentTenant());
    }

    @Test
    @WithAnonymousUser
    void anonymousFailsAuthorization() {
        assertThrows(AccessDeniedException.class,
                () -> tenants.currentTenant());
    }

    @Test
    @WithMockUser(roles = "USER")
    void roleUserLacksTenantRead() {
        assertThrows(AccessDeniedException.class,
                () -> tenants.currentTenant());
    }

    @Test
    @WithMockUser(authorities = "TENANT_READ")
    void authorityIsNotEnoughWithoutCustomPrincipal() {
        assertThrows(IllegalStateException.class,
                () -> tenants.currentTenant());
    }

    @Test
    @WithUserDetails(
        value = "alice",
        userDetailsServiceBeanName = "demoUsers")
    void withUserDetailsSuppliesAppPrincipal() {
        assertEquals("tenant-blue",
                tenants.currentTenant());
    }

    @Test
    @WithTenantIdentity(tenantId = "tenant-violet")
    void withSecurityContextSuppliesAppPrincipal() {
        assertEquals("tenant-violet",
                tenants.currentTenant());
    }

    @Test
    @WithAnonymousUser
    void anonymousTokenIsNotRealLogin() {
        Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();

        assertInstanceOf(AnonymousAuthenticationToken.class, auth);
        assertTrue(auth.isAuthenticated());
        assertTrue(new AuthenticationTrustResolverImpl()
                .isAnonymous(auth));
    }
}
~~~

**7 `@Test`**. Những methods này gọi **Spring-managed TenantService proxy**, do đó `@PreAuthorize` thực sự được áp dụng. Nếu bỏ `@EnableMethodSecurity`, negative tests sẽ không còn cùng behavior.

## 20. ClassLevelIdentityTest.java: 3 phương thức JUnit

File `src/test/java/example/security/ClassLevelIdentityTest.java`:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@WithMockUser(username = "baseline", roles = "USER")
class ClassLevelIdentityTest {

    @Autowired MockMvc mvc;

    @Test
    void inheritsDefaultUser() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("baseline"));
    }

    @Test
    @WithMockUser(username = "root-mock", roles = "ADMIN")
    void methodOverridesClassRole() throws Exception {
        mvc.perform(get("/api/admin"))
                .andExpect(status().isOk());
    }

    @Test
    @WithAnonymousUser
    void anonymousOverridesClassUser() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

**3 `@Test`** cho thấy method annotation được ưu tiên hơn class-level identity. Đừng dùng class-level ADMIN tràn lan vì có thể vô tình làm routes thiếu quyền vẫn PASS.

## 21. LiveHttpIdentityTest.java: 4 bài kiểm tra HTTP thật

`@WithMockUser` được áp dụng trong **JUnit test thread**. Với `@SpringBootTest(RANDOM_PORT)`, servlet xử lý request trong **server thread**; identity trên test thread không tự truyền qua TCP. Request cần gửi credentials thật (Basic/Bearer/session cookie).

File `src/test/java/example/security/LiveHttpIdentityTest.java`:

~~~java
package example.security;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpIdentityTest {

    @LocalServerPort int port;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @Test
    @WithMockUser(username = "pretend-admin", roles = "ADMIN")
    void mockAnnotationDoesNotAuthenticateLiveRequest()
            throws Exception {
        HttpResponse<String> response =
                get("/api/admin", null);

        assertEquals(401, response.statusCode());
    }

    @Test
    void validBasicLoadsCustomPrincipal() throws Exception {
        HttpResponse<String> response =
                get("/api/tenant", "alice:demo-pass");

        assertEquals(200, response.statusCode());
        assertEquals("tenant-blue", response.body());
    }

    @Test
    void userWithoutAdminRoleIsForbidden() throws Exception {
        HttpResponse<String> response =
                get("/api/admin", "alice:demo-pass");

        assertEquals(403, response.statusCode());
    }

    @Test
    void adminWithBasicCredentialsIsAllowed() throws Exception {
        HttpResponse<String> response =
                get("/api/admin", "root:demo-pass");

        assertEquals(200, response.statusCode());
        assertEquals("admin", response.body());
    }

    private HttpResponse<String> get(
            String path, String credentials)
            throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(10))
                .GET();

        if (credentials != null) {
            String encoded = Base64.getEncoder().encodeToString(
                    credentials.getBytes(StandardCharsets.UTF_8));
            builder.header("Authorization", "Basic " + encoded);
        }

        return http.send(
                builder.build(),
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }
}
~~~

**4 `@Test`**. HTTP Basic requests đi qua filter chain và authentication provider thật của ứng dụng demo. Tài khoản demo được UserDetailsService cung cấp, password được PasswordEncoder xác minh. Đây vẫn không phải kiểm JWT/OAuth2 vì app demo không sử dụng các cơ chế đó.

**Lưu ý bảo mật:** Basic qua HTTP chỉ chấp nhận được cho test localhost tạm thời; production phải bảo vệ credentials bằng HTTPS và không log raw Authorization header. Không dùng password cố định của bài giảng trong hệ thống thật.

## 22. Tổng cộng 28 bài test và lệnh chạy

| Test class | @Test methods | Điều được kiểm |
| --- | ---: | --- |
| `SecurityMvcTest` | 14 | Anonymous, mock user, roles/authorities, CSRF, request identity |
| `MethodSecurityTest` | 7 | `@PreAuthorize`, principal type, anonymous token |
| `ClassLevelIdentityTest` | 3 | Class-level vs method-level overrides |
| `LiveHttpIdentityTest` | 4 | Basic login qua HTTP thật, 401/403/200, thread boundary |
| **Tổng** | **28** | Servlet Security và custom AppPrincipal |

Linux/macOS:

~~~bash
./gradlew test --tests example.security.SecurityMvcTest --tests example.security.MethodSecurityTest --tests example.security.ClassLevelIdentityTest --tests example.security.LiveHttpIdentityTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.security.SecurityMvcTest --tests example.security.MethodSecurityTest --tests example.security.ClassLevelIdentityTest --tests example.security.LiveHttpIdentityTest
~~~

Để chạy toàn bộ:

~~~bash
./gradlew clean test
~~~

**Kết quả kỳ vọng:** JUnit Jupiter phát hiện 28 test methods và tất cả PASS trên Java 17+/Spring Boot 3.5.x/Security 6.5.x với đúng nguồn code/dependencies của bài. Đây là **kỳ vọng sau rà soát cấu trúc, không phải stdout của một Gradle build đã chạy thực tế**. Gradle reports ở `build/reports/tests/test/index.html` khi build xong; random HTTP port và log startup không cố định.

## 23. @WebMvcTest hay @SpringBootTest?

**`@WebMvcTest`** là MVC slice: nhanh, tập trung vào controller, validation và filters. Nó không mặc nhiên load toàn bộ application service/security configuration tùy chỉnh; cần `@Import` và mocks/fakes cần thiết. Nếu mock `TenantService` thì method-security `@PreAuthorize` của service thật **không được kiểm**. Hãy bổ sung service authorization test riêng.

**`@SpringBootTest + @AutoConfigureMockMvc`** tải full context và cho MockMvc đi qua SecurityFilterChain và Spring beans. Nó phù hợp khi muốn kiểm đồng thời controller, filters, method security và principal injection mà không cần TCP.

**`@SpringBootTest(RANDOM_PORT)`** chạy HTTP server thật. `@WithMockUser` trên test **không xác thực live request**. Gửi Basic/Bearer/cookie thực trên request để kiểm authentication mechanism, entry point và server thread.

**Direct method test** gọi service được @Autowired vào test với `@WithMockUser`/`@WithUserDetails`; kiểm `@PreAuthorize` và custom principal, không kiểm HTTP pipeline.

Không chọn full context cho mọi test nếu pure domain logic không dùng Spring. Giữ unit tests nhanh, đồng thời có bộ integration security tests không tắt filter/advice.

## 24. JWT, OAuth2, WebFlux và async khác thế nào?

### 24.1 JWT và OAuth2

Nếu production dùng OAuth2 Resource Server, principal có thể là `Jwt` hoặc `JwtAuthenticationToken`, authorities có thể mang `SCOPE_`. Dùng `spring-security-test` request postprocessor `jwt()`/`oauth2Login()` phù hợp để **giả identity và kiểm authorization**.

~~~text
Access token claim "scope": "invoice:read"
    |
    v
JwtAuthenticationConverter
    |
    v
GrantedAuthority: SCOPE_invoice:read
    |
    v
hasAuthority("SCOPE_invoice:read")
~~~

Đây là flow minh họa, không nằm trong mini-project. `with(jwt())` **không** tự chứng minh token signature, issuer, audience, expiry hay JWK fetching hoạt động thật. Cần test decoder/validators riêng khi đó là security requirement.

### 24.2 WebFlux

Với WebFlux, `SecurityContext` được truyền qua Reactor Context, không đơn thuần bằng servlet ThreadLocal. Dùng WebTestClient security support, ví dụ:

~~~java
webTestClient
        .mutateWith(mockUser().roles("ADMIN"))
        .get()
        .uri("/api/admin")
        .exchange()
        .expectStatus().isOk();
~~~

Đây là đoạn minh họa cho **reactive app**, cần `SecurityMockServerConfigurers.mockUser`, WebTestClient và reactive security config. Không thay thẳng `MockMvc` trong sample mà kỳ vọng semantics hoàn toàn giống.

### 24.3 @Async và thread pools

SecurityContextHolder trong servlet tests thường gắn với thread. `@Async`, executors, scheduled tasks và HTTP server threads không tự thừa hưởng identity. Khi cần propagation, dùng `DelegatingSecurityContextExecutor` hoặc cơ chế context propagation được cấu hình/test có chủ đích.

Không bật `MODE_INHERITABLETHREADLOCAL` toàn cục thiếu cân nhắc: thread pool có thể reuse threads, dẫn đến leak user context nếu cleanup sai.

## 25. Các lỗi thường gặp

**1. Thiếu `spring-security-test`.**  
Annotations và MockMvc postprocessors không compile. Thêm dependency test scope.

**2. `@WithMockUser` được xem là login thật.**  
Nó không so password hay gọi authentication provider. Muốn test provider, gửi credentials thật.

**3. `@WithMockUser(roles="ROLE_ADMIN")`.**  
Sai prefix. Dùng `roles="ADMIN"`.

**4. `@WithMockUser(authorities="ADMIN")` nhưng expect `hasRole("ADMIN")`.**  
Authority này không có ROLE_ prefix.

**5. `@WithMockUser` được dùng cho service yêu cầu AppPrincipal.**  
Mock principal mặc định là Spring User; dùng `@WithUserDetails`/custom factory.

**6. Không có Authentication bị nhầm với anonymous token.**  
Null context và anonymous context có behavior khác.

**7. Tin `auth.isAuthenticated()==true` nghĩa là real login.**  
AnonymousAuthenticationToken có thể cũng trả true; kiểm trust resolver/policy.

**8. `@EnableMethodSecurity` bị thiếu.**  
`@PreAuthorize` không chạy; negative tests phải phát hiện.

**9. `@AutoConfigureMockMvc(addFilters=false)` trong test security.**  
Bypass filters; kết quả 401/403/CSRF không còn ý nghĩa.

**10. User đã @WithMockUser nhưng POST thiếu CSRF.**  
403 có thể do CsrfFilter, không phải thiếu role.

**11. `@WithUserDetails` lookup trước khi @BeforeEach seed user.**  
Dùng setupBefore phù hợp hoặc seed committed fixture trước.

**12. Có nhiều UserDetailsService nhưng không chỉ định bean.**  
Lookup ambiguities; dùng userDetailsServiceBeanName chính xác.

**13. Custom @WithSecurityContext factory dùng static context mutable.**  
Rò identity giữa tests; tạo context mới.

**14. Custom annotation thiếu @Retention(RUNTIME).**  
Listener không đọc metadata lúc chạy.

**15. Test chỉ ROLE_ADMIN.**  
Không kiểm least privilege hoặc anonymous; thêm negative cases.

**16. `@WithMockUser` trên RANDOM_PORT mà HTTP request không mang credentials.**  
Test thread không truyền security context qua TCP; server trả 401 đúng.

**17. MockMvc `user()` được xem là test user database.**  
Request postprocessor không truy vấn account store.

**18. Mock JWT được coi như đã kiểm signature.**  
Phải có decoder/validation tests riêng.

**19. AppPrincipal với tenantId từ test được xem là bảo đảm tenant isolation.**  
Cần integration test cross-tenant/DB filtering, không tin tenantId từ client input.

**20. Test 403 nhưng không phân biệt CSRF và authorization failure.**  
Kiểm có/không có csrf, role, status, security events và logs.

**21. Test chạy song song dùng SecurityContext static.**  
Có thể rò identity; tránh mutation cross-thread và cleanup đúng.

**22. Authentication trong controller không có Principal vì filters tắt.**  
Khôi phục security filter chain thay vì hardcode Principal.

**23. Không kiểm account disabled/locked.**  
`@WithMockUser` bỏ qua login provider; cần authentication tests thật.

**24. Không kiểm negative tenant/ownership.**  
Một user đăng nhập đúng vẫn có thể đọc sai tài nguyên; test ABAC/data scope.

## 26. Checklist thiết kế bài test

1. Xác định mục tiêu là authentication, authorization, principal mapping hay object-level access.
2. Chọn test layer: direct service, MockMvc, WebMvc slice, live HTTP, reactive WebTestClient.
3. Dùng `@WithMockUser` cho roles/authorities đơn giản; không kỳ vọng AppPrincipal.
4. Dùng `@WithAnonymousUser` cho anonymous và class-level override.
5. Dùng `@WithUserDetails` khi có UserDetailsService bean và principal domain.
6. Dùng `@WithSecurityContext` khi cần custom tenant/claims mà không nạp DB.
7. Tạo SecurityContext mới, chỉ cấp authorities test thực sự yêu cầu.
8. Kiểm role prefix `ROLE_` và exact authority names.
9. Giữ filter chain và method-security proxy bật trong security integration tests.
10. Kiểm 401/403 đúng entry point của app; 403 có thể do CSRF.
11. MockMvc `with(csrf())` nếu CSRF bật và method không an toàn.
12. Live HTTP phải mang credentials/token thực, không dựa vào @WithMockUser.
13. Chạy cả positive và negative cases cho role/authority/tenant.
14. Tách test giả identity khỏi test password/JWT signature validation.
15. Kiểm async/reactive context propagation nếu code chuyển thread.
16. Không dùng demo user/password/keys trên môi trường thật.
17. Chạy test trên đúng Spring Boot/Security versions của dự án.

### Checklist cuối

- [ ] Có test anonymous, no-auth, user thiếu quyền và user đủ quyền.
- [ ] `@WithMockUser` roles/authorities đúng prefix.
- [ ] Principal type được kiểm khi service yêu cầu custom fields.
- [ ] `@WithUserDetails` lookup đúng bean/user và đúng lifecycle.
- [ ] Factory của `@WithSecurityContext` tạo context riêng từng test.
- [ ] Class-level user không che negative authorization cases.
- [ ] SecurityFilterChain và `@EnableMethodSecurity` thật sự active.
- [ ] MockMvc filters không bị vô hiệu hóa để làm tests xanh.
- [ ] CSRF tests phản ánh security config hiện hành.
- [ ] RANDOM_PORT tests gửi HTTP credentials/token thật.
- [ ] Authentication-provider/JWT validation có tests riêng khi cần.
- [ ] Tenant ownership/data isolation được kiểm ở repository/service.
- [ ] Không rò user context giữa tests hoặc threads.

**Kết luận:** `@WithMockUser` nhanh và tiện cho role/authority tests; `@WithAnonymousUser` giúp kiểm truy cập chưa đăng nhập; `@WithUserDetails` và `@WithSecurityContext` giúp tạo đúng principal domain khi ứng dụng cần `tenantId` hoặc kiểu Authentication đặc biệt. Nhưng test phải chạy ở **đúng ranh giới**: method security, MockMvc filters hay HTTP server thật. Chỉ khi kiểm đủ negative cases, CSRF, principal type, tenant isolation và authentication entry point, bạn mới có bằng chứng đáng tin cho bảo mật Spring Boot.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, `@WithSecurityContext` và lifecycle.
- [Spring Security 6.5 — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): filter chain và `springSecurity()`.
- [Spring Security 6.5 — MockMvc Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html): `user()`, `anonymous()`, `authentication()` và `securityContext()`.
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()` và invalid token.
- [Spring Security 6.5 — Method Authorization](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, role/authority checks.
- [Spring Security — Reactive Test Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): WebTestClient mockUser và Reactor context.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, RANDOM_PORT.
