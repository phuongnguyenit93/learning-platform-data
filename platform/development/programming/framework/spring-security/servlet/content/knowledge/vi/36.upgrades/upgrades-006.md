# Từ authorizeRequests, AccessDecisionManager sang mô hình AuthorizationManager

**Phạm vi:** nâng cấp **Spring Security Servlet/Spring MVC** từ lối cấu hình cũ `authorizeRequests()`, `FilterSecurityInterceptor`, `AccessDecisionManager` và các `AccessDecisionVoter` sang mô hình **`authorizeHttpRequests()` + `AuthorizationManager`** của Spring Security 6.x, Spring Boot 3.x, Java 17+. Bài học bao gồm kiến trúc, bảng đối chiếu API, cách viết quy tắc request/method, chuyển logic tùy biến, phép thử trước–sau, và những thay đổi có thể gây **nới lỏng hoặc siết sai quyền** khi nâng cấp.

**Cảnh báo phiên bản:** các đoạn `antMatchers()` và `WebSecurityConfigurerAdapter` được ghi rõ là **mã lịch sử dành cho Spring Security 5.x**, không copy vào Spring Security 6.x. Những ví dụ chính dùng `SecurityFilterChain` và các API Servlet Spring Security 6.x. Một số method đã được đánh dấu deprecated ở các minor release về sau (chẳng hạn dạng `AuthorizationManager.check(...)`), nhưng vẫn có thể có mặt trong Spring Security 6.x; xem tài liệu/migration notes của **đúng phiên bản dependency** trước khi đổi API sâu hơn. Không áp dụng nguyên cấu hình Servlet cho WebFlux, nơi dùng `ServerHttpSecurity.authorizeExchange(...)`.

## 1. Vì sao phải chuyển mô hình?

### 1.1 Authentication khác Authorization

- **Authentication**: “Người đang gọi là ai?”. Sau khi login/JWT/basic authentication hoàn tất, Spring Security có `Authentication` chứa principal và authorities như `ROLE_ADMIN`, `REPORT_READ`.
- **Authorization**: “Người đó có được truy cập request hoặc tài nguyên này không?”. Ví dụ `GET /api/reports/quarterly` yêu cầu `REPORT_READ`, còn `POST /api/reports` yêu cầu `REPORT_WRITE`.
- **AccessDecisionManager** cũ và **AuthorizationManager** mới đều phục vụ quyết định **authorization**, **không thay** `AuthenticationManager` hay `AuthenticationProvider` dùng xác thực thông tin đăng nhập.

Khi nâng cấp, tên API đổi nhưng mục tiêu bảo mật không đổi: **deny by default**, chỉ cho phép request thỏa rule, bảo vệ quyền ở service/domain object và có test cho cả 200/401/403.

### 1.2 Hai mô hình, nhìn ở ranh giới HTTP

```text
TRƯỚC: authorizeRequests (Spring Security 5.x)
  HTTP request
       │
       ▼
  FilterSecurityInterceptor
       │
       ├── SecurityMetadataSource / ConfigAttributes cho URL
       │
       ▼
  AccessDecisionManager
       │
       ├── AccessDecisionVoter A (grant/deny/abstain)
       ├── AccessDecisionVoter B
       └── các chiến lược như AffirmativeBased / UnanimousBased
       │
       ▼
  Cho phép hoặc ném AccessDeniedException

SAU: authorizeHttpRequests (Spring Security 6.x)
  HTTP request
       │
       ▼
  AuthorizationFilter
       │
       ▼
  AuthorizationManager<HttpServletRequest> hoặc manager
  được điều phối qua RequestMatcherDelegatingAuthorizationManager
       │
       ├── Rule 1: requestMatcher + AuthorizationManager
       ├── Rule 2: requestMatcher + AuthorizationManager
       └── Rule cuối: anyRequest().denyAll()/authenticated()
       │
       ▼
  Quyết định quyền / từ chối request
```

Sơ đồ giản lược các filter khác (CSRF, authentication, exception handling, security context). Trong hệ thống thật, **authentication diễn ra theo filter chain** và một user có thể không được xác thực ở request hiện tại. Spring Security cung cấp `Supplier<Authentication>` cho authorization manager để **trì hoãn việc lấy Authentication** cho đến khi cần, một điểm khác với cách đọc principal không điều kiện ở nhiều đoạn legacy.

### 1.3 Tại sao mô hình mới dễ mở rộng hơn?

`AuthorizationManager<T>` gom **quyết định cho phép/từ chối** trong một hợp đồng, với `T` là đối tượng đang được bảo vệ. Ví dụ:

- `AuthorizationManager<RequestAuthorizationContext>` cho request được chọn bởi một matcher trong `authorizeHttpRequests`.
- `AuthorizationManager<HttpServletRequest>` tại cấp filter hoặc request dispatcher.
- `AuthorizationManager<MethodInvocation>` / thành phần method security cho gọi phương thức.
- Manager có sẵn: `AuthorityAuthorizationManager`, `AuthenticatedAuthorizationManager`, các manager dựa trên SpEL/metadata phù hợp hoặc composition qua `AuthorizationManagers.allOf(...)` và `anyOf(...)`.

Phần lớn rule đơn giản không cần custom class. Chỉ khi cần policy nghiệp vụ đặc thù mới cần `.access(customManager)` hoặc method security.

## 2. Đối chiếu các thành phần trước và sau nâng cấp

| Lối cũ | Lối mới hoặc điểm cần xem xét | Lưu ý |
| --- | --- | --- |
| `http.authorizeRequests(...)` | `http.authorizeHttpRequests(...)` | Thay request authorization DSL; không nhầm với `oauth2Login()`. |
| `.antMatchers("/x/**")` | `.requestMatchers("/x/**")` | Không phải mọi biểu thức/matcher giữ cùng semantics; phải test MVC/servlet path. |
| `.mvcMatchers(...)` | `.requestMatchers(...)` hoặc matcher tường minh phù hợp | Dựa trên MVC matcher/config và phiên bản; chú ý servlet path, PathPattern. |
| `.regexMatchers(...)` | `requestMatchers(RegexRequestMatcher...)` khi cần regex | Đừng đổi regex thành wildcard string mà không kiểm tra. |
| `FilterSecurityInterceptor` | `AuthorizationFilter` khi dùng `authorizeHttpRequests` | Filter behavior, dispatcher types và context có khác biệt. |
| `AccessDecisionManager` | `AuthorizationManager` | Không có ánh xạ 1–1 cho mọi voter policy. |
| `AccessDecisionVoter` | Manager tùy biến/composition | Phải giữ nguyên semantics grant/deny/abstain thực tế. |
| `ConfigAttribute` / `SecurityMetadataSource` | RequestMatcher → AuthorizationManager | Tách việc chọn request khỏi logic quyết định quyền. |
| `AffirmativeBased`, `UnanimousBased` | `AuthorizationManagers.anyOf/allOf` khi tương đương | Chú ý abstain, deny override và short-circuit. |
| `WebSecurityConfigurerAdapter` | `@Bean SecurityFilterChain` | Adapter bị loại bỏ ở Spring Security 6; định nghĩa filter chain bằng bean. |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Method security hiện đại dựa trên các AuthorizationManager interceptors. |
| `access("hasAuthority('X')")` | `.hasAuthority("X")` hoặc `.access(manager)` | Ưu tiên DSL rõ khi biểu thức đơn giản. |

**Không nâng cấp “tìm và thay” máy móc.** Một `.antMatchers(...)` cũ có thể match khác `requestMatchers(...)` do đường dẫn servlet, matcher inference hoặc dispatcher behavior. Tương tự, voter legacy có chính sách tổ hợp phức tạp; thay bằng `anyOf`/`allOf` phải có test chứng minh tương đương.

## 3. Mẫu cấu hình lịch sử: chỉ để nhận diện khi đọc code cũ

Đây là **mã lịch sử minh họa Spring Security 5.x**, không tương thích Spring Security 6.x nếu copy nguyên:

```java
// LEGACY ONLY — không dùng với Spring Security 6.x.
http
    .authorizeRequests()
        .antMatchers("/", "/public/**").permitAll()
        .antMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    .and()
    .formLogin();
```

Khi gặp một dự án cũ, cần ghi lại trước khi sửa:

1. Danh sách các matcher và **thứ tự** của chúng.
2. Những URL public, login/logout, error, static resources, callback OAuth2/OIDC.
3. Quy tắc `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, `denyAll`.
4. `@PreAuthorize`, `@Secured`, `@RolesAllowed`, URL expression handler và custom voters.
5. Các `AccessDecisionManager`, `RunAsManager`, `PermissionEvaluator`, role hierarchy, ACL/domain policy nếu tồn tại.
6. Những exception handlers/entry points tạo 401, 403 hoặc redirect khi chưa login.
7. Cách matcher xử lý HTTP methods, trailing slash, path variables, servlet path, forward/error/async dispatcher.
8. Các `SecurityFilterChain` khác nhau và thứ tự `@Order` nếu application có nhiều chain.

**Baseline tối thiểu:** trước khi thay DSL, nên có test positive/negative cho từng route nhạy cảm. Một bản nâng cấp compile được nhưng vô tình để `/admin/**` rơi vào `anyRequest().authenticated()` vẫn là lỗi bảo mật.

## 4. Cấu hình mới: authorizeHttpRequests trên Spring Security 6.x

### 4.1 Bản chuyển đổi đơn giản

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
```

Đây là **method snippet**, cần imports `@Bean`, `HttpSecurity`, `SecurityFilterChain` và `Customizer` cùng cấu hình Spring. Không thêm `.and()` theo thói quen cũ; Lambda DSL giúp cấu hình rõ ràng hơn.

### 4.2 Cách Spring Security chọn quy tắc

Với `authorizeHttpRequests`, các rule được kiểm tra **theo thứ tự khai báo**. **Rule khớp đầu tiên** được áp dụng; rule sau không được dùng để tự cộng/trừ quyền cho cùng request.

Sai:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Lỗi: request `/api/admin/users` đã khớp `/api/**` và chỉ cần authenticated. Rule `hasRole("ADMIN")` bên dưới **không còn cơ hội áp dụng**.

Đúng:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
```

**Deny by default** với `anyRequest().denyAll()` giúp phát hiện endpoint mới chưa được khai báo. Nếu chọn `anyRequest().authenticated()`, mọi route chưa match vẫn được vào khi đã login, có thể không phù hợp hệ thống nhiều quyền. Quyết định tùy kiến trúc nhưng phải **rõ ràng và có test**.

### 4.3 URL pattern và HTTP method

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("REPORT_READ")
    .requestMatchers(HttpMethod.POST, "/api/reports")
        .hasAuthority("REPORT_WRITE")
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

Đừng để rule `GET` bảo vệ `POST` theo suy đoán: nếu chỉ khai báo GET, một request POST có thể rơi vào rule cuối yếu hơn. Tương tự `HEAD`, `OPTIONS`, custom methods và route actuator/health cần xem xét theo kiến trúc. Đối với CORS preflight, cấu hình CORS đúng thay vì mở mọi phương thức/endpoint bằng wildcard.

String-based `requestMatchers(...)` có thể chọn matcher theo môi trường MVC và phiên bản; khi dùng servlet mapping khác `/`, nhiều `DispatcherServlet` hoặc regex đặc biệt, cần một `RequestMatcher` tường minh phù hợp và test kết quả match. **Không tự động giả định `antMatchers` cũ và `requestMatchers` mới tương đương tuyệt đối**.

## 5. Vai trò của AuthorizationManager và kết quả quyết định

Ở tầng khái niệm, manager trả một kết quả `AuthorizationDecision` (hoặc dạng `AuthorizationResult` theo API/minor version) thể hiện granted/denied. Trong Spring Security 6.x, dạng method thường gặp là:

```java
AuthorizationDecision check(
    Supplier<Authentication> authentication,
    T secureObject
);
```

Một số phiên bản mới cung cấp/hướng tới `authorize(Supplier<Authentication>, T)`; khi viết library dài hạn, kiểm tra đúng interface và deprecation notes của phiên bản đang dùng. Trong các mẫu Spring Security 6.x truyền thống, `check(...)` có thể được override; đừng tự viết cả hai method nếu chưa hiểu contract mặc định.

**Tại sao là `Supplier<Authentication>`?** Khi rule `permitAll` hoặc `denyAll` không cần user, Spring Security có thể tránh tải Authentication không cần thiết. Custom manager nên chỉ gọi `authentication.get()` nếu thật sự cần quyết định dựa trên principal.

### 5.1 Managers dựng sẵn

| Cách dùng | Ý nghĩa |
| --- | --- |
| `.permitAll()` | Cho phép request khớp mà không yêu cầu đăng nhập. |
| `.denyAll()` | Từ chối mọi request khớp, kể cả user authenticated. |
| `.authenticated()` | Yêu cầu user được xem là authenticated theo Spring Security, không nhầm anonymous với user thật. |
| `.fullyAuthenticated()` | Không chấp nhận remember-me authentication như full authentication. |
| `.hasAuthority("REPORT_READ")` | Cần đúng authority string. |
| `.hasAnyAuthority("A", "B")` | Cần ít nhất một authority được khai báo. |
| `.hasRole("ADMIN")` | Thông thường yêu cầu `ROLE_ADMIN`, không phải string `ADMIN` trần. |
| `.access(customAuthorizationManager)` | Dùng policy tùy biến của ứng dụng. |

Ví dụ user có `ROLE_ADMIN` không có nghĩa họ tự có `REPORT_READ` trừ khi policy hoặc role hierarchy của app nói như vậy. Đừng xem roles của JWT hoặc IdP là đáng tin chỉ vì có tên `admin`; mapping claims → authorities phải được cấu hình và test riêng.

### 5.2 Composition và “abstain” không giống nhau

Mô hình legacy voter dùng giá trị **grant/deny/abstain**, sau đó `AccessDecisionManager` tổng hợp theo chiến lược (ví dụ affirmative/unanimous/consensus). Trong mô hình mới, bạn có thể dùng `AuthorizationManagers.allOf(...)` hoặc `anyOf(...)` khi chính sách thật sự tương đương:

- `allOf(A, B)`: thường tương ứng ý tưởng **phải đạt cả hai**.
- `anyOf(A, B)`: thường tương ứng ý tưởng **đạt ít nhất một**.

Nhưng **đừng khẳng định** đây là chuyển đổi chính xác cho mọi legacy voter manager: các ca tất cả abstain, deny override, exception behavior, rule ordering và decision null có thể khác. Hãy lập bảng truth table từ code cũ và viết tests cho tổ hợp grant/deny/abstain trước khi thay.

## 6. Ví dụ hoàn chỉnh: dự án Spring Boot Servlet có thể kiểm thử

Mục tiêu: ứng dụng chứa bốn loại quyền độc lập:

- `GET /` và `GET /api/reports/public`: công khai.
- `GET /api/reports/quarterly`: yêu cầu authority `REPORT_READ`.
- `POST /api/reports`: yêu cầu `REPORT_WRITE` **và** CSRF token (nếu dùng session/web browser theo cấu hình mặc định).
- `GET /api/admin/summary`: yêu cầu role `ROLE_ADMIN`.
- `GET /api/profiles/{username}`: chỉ user có tên khớp path variable mới xem, minh họa custom request authorization.
- `GET /api/service-report`: phải đăng nhập ở HTTP, nhưng service bổ sung `@PreAuthorize` để yêu cầu `REPORT_READ`.

Tạo project Spring Initializr: **Spring Boot 3.x**, **Java 17+**, **Spring Web**, **Spring Security**, **Spring Boot Starter Test**, thêm `spring-security-test`. Ví dụ là **Spring Boot application** chạy bằng Gradle/Maven với dependencies, không thể chạy chỉ bằng `javac` thuần.

### 6.1 Cấu hình dependencies

**`build.gradle`**: phần dependencies cần có, giữ plugins/repositories do Spring Initializr tạo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 6.2 SecurityConfig.java

**`src/main/java/com/example/authmigration/SecurityConfig.java`**

```java
package com.example.authmigration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    UserDetailsService users() {
        var reader = User.withUsername("reader")
            .password("{noop}reader-demo")
            .authorities("REPORT_READ")
            .build();

        var writer = User.withUsername("writer")
            .password("{noop}writer-demo")
            .authorities("REPORT_WRITE")
            .build();

        var admin = User.withUsername("admin")
            .password("{noop}admin-demo")
            .authorities("ROLE_ADMIN", "REPORT_READ")
            .build();

        return new InMemoryUserDetailsManager(reader, writer, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/public"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/**"
                ).hasAuthority("REPORT_READ")
                .requestMatchers(
                    HttpMethod.POST, "/api/reports"
                ).hasAuthority("REPORT_WRITE")
                .requestMatchers(
                    HttpMethod.GET, "/api/admin/**"
                ).hasRole("ADMIN")
                .requestMatchers(
                    HttpMethod.GET, "/api/profiles/{username}"
                ).access(new OwnProfileAuthorizationManager())
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

**Giải thích và phạm vi:**

1. `@EnableMethodSecurity` bật kiểm tra `@PreAuthorize` trong service; không cần cấu hình `@EnableGlobalMethodSecurity` của mô hình cũ.
2. Spring Security xử lý rule HTTP theo thứ tự: public GET trước GET reports rộng; admin và own-profile có rule riêng.
3. `{noop}` và mật khẩu demo dùng **duy nhất** để test/trình bày, không dùng trong production. Production cần password hashing an toàn (ví dụ `PasswordEncoder` phù hợp), user store, MFA/passkeys, login throttling và quản lý session.
4. `.httpBasic(...)` tạo entry point để test rõ 401 khi chưa login; ứng dụng browser thực tế có thể dùng `formLogin`/OIDC thay thế.
5. CSRF protection mặc định vẫn có thể tác động POST theo cấu hình session. Không tắt CSRF để khiến test POST dễ pass.
6. Nếu ứng dụng API stateless dùng bearer JWT thay vì browser cookie, cần thiết kế riêng `oauth2ResourceServer(...)`, session và CSRF theo mô hình. **AuthorizationManager không thay thế JWT validation.**

### 6.3 Tự viết một AuthorizationManager cho request

**`src/main/java/com/example/authmigration/OwnProfileAuthorizationManager.java`**

```java
package com.example.authmigration;

import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class OwnProfileAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current = authentication.get();
        String username = context.getVariables().get("username");

        boolean allowed = current != null
            && !(current instanceof AnonymousAuthenticationToken)
            && current.isAuthenticated()
            && username != null
            && username.equals(current.getName());

        return new AuthorizationDecision(allowed);
    }
}
```

**Cơ chế:** `RequestAuthorizationContext` chứa `HttpServletRequest` và các biến URI được matcher hỗ trợ trích xuất. Ở route `/api/profiles/{username}`, manager đối chiếu username của path với `Authentication.getName()`. Nó trả `AuthorizationDecision(true/false)`.

**Giới hạn quan trọng:** so sánh username đủ minh họa cách viết manager, nhưng **không phải mẫu bảo mật đối tượng production cho mọi ứng dụng**. Username có thể đổi, có trùng giữa tenant hoặc khác canonicalization; dùng account ID bất biến và policy ở database cho quy tắc ownership thực tế. Cần test path matching trả đủ variables ở deployment có servlet path hoặc matcher tùy biến. Nếu matcher không cung cấp variable, đoạn mã **deny** thay vì cấp quyền tùy tiện.

Ở một số Spring Security 6.x mới hơn, `check(...)` có thể được đánh dấu deprecated để hướng sang `authorize(...)`; snippet dùng chữ ký phổ biến của 6.x để mô tả logic. Khi nâng cấp dependency, chọn method tương thích theo interface/version thực và giữ nguyên test hành vi.

**Tránh các lỗi thường gặp trong custom manager:**

- Dùng `authentication.get()` rồi tin `isAuthenticated()==true` là đủ: một `AnonymousAuthenticationToken` cũng có thể được xem là authenticated theo flag. Cần dùng semantics phù hợp (ví dụ trust resolver của Spring Security) thay vì chỉ một boolean.
- Tin role/username trong header do client tự gửi (`X-User`, `X-Role`) mà không được kiểm chứng qua authentication.
- Thực hiện network/DB I/O chậm hoặc side effects thay đổi dữ liệu trong authorization path; có thể tăng latency và tạo retry side effects.
- Trả allow khi thiếu account/tenant/path variable hoặc không tải được policy. Mặc định an toàn là **deny khi không đủ căn cứ**.

### 6.4 ReportService.java: method security

**`src/main/java/com/example/authmigration/ReportService.java`**

```java
package com.example.authmigration;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String restrictedReport() {
        return "quarterly-report";
    }
}
```

`@PreAuthorize` giúp bảo vệ method khi được gọi từ một endpoint khác, scheduled component hoặc một service khác. Đừng chỉ dựa vào URL rule nếu cùng business method có nhiều đường gọi. **Lưu ý proxy:** self-invocation như `this.restrictedReport()` trong cùng bean thường bỏ qua AOP proxy, vì vậy có thể không kích hoạt method interceptor theo kỳ vọng. Phần ví dụ gọi qua bean được Spring quản lý.

### 6.5 Controller và main

**`src/main/java/com/example/authmigration/ReportController.java`**

```java
package com.example.authmigration;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/api/reports/public")
    public String publicReport() {
        return "public-report";
    }

    @GetMapping("/api/reports/quarterly")
    public String quarterly() {
        return reportService.restrictedReport();
    }

    @PostMapping("/api/reports")
    public String createReport() {
        return "created";
    }

    @GetMapping("/api/admin/summary")
    public String adminSummary() {
        return "admin-summary";
    }

    @GetMapping("/api/profiles/{username}")
    public String profile(@PathVariable String username) {
        return "profile:" + username;
    }

    @GetMapping("/api/service-report")
    public String serviceReport() {
        // HTTP rule chỉ authenticated; method rule yêu cầu REPORT_READ.
        return reportService.restrictedReport();
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
```

**`src/main/java/com/example/authmigration/AuthorizationMigrationApplication.java`**

```java
package com.example.authmigration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationMigrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            AuthorizationMigrationApplication.class, args
        );
    }
}
```

Đặt public class đúng tên file, tất cả cùng package. Ứng dụng có thể khởi động với Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ví dụ request dùng HTTP Basic với account demo:

```bash
curl -i http://localhost:8080/api/reports/public
curl -i -u reader:reader-demo \
  http://localhost:8080/api/reports/quarterly
curl -i -u reader:reader-demo \
  http://localhost:8080/api/admin/summary
curl -i -u admin:admin-demo \
  http://localhost:8080/api/admin/summary
```

Kỳ vọng lần lượt **200, 200, 403, 200** với cấu hình demo. HTTP Basic không mã hóa password theo cách độc lập với TLS, vì vậy **dùng HTTPS** nếu thử ngoài localhost và không dùng thông tin đăng nhập demo trong production. Đoạn `curl` chỉ minh họa request; không có transcript giả định rằng một môi trường cụ thể đã chạy thành công.

## 7. Kiểm thử regression: phân quyền theo request và method

Khi nâng cấp authorization, test cần kiểm chứng **hành vi**, không chỉ compile được code. Với dependency `spring-security-test`, MockMvc có thể giả lập user/authorities để xác nhận rule HTTP và method security.

**`src/test/java/com/example/authmigration/AuthorizationMigrationTest.java`**

```java
package com.example.authmigration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationMigrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireAuthentication() throws Exception {
        mvc.perform(get("/api/reports/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public-report"));
    }

    @Test
    void privateReportNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/reports/quarterly"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerMayReadReportButNotAdminPage() throws Exception {
        mvc.perform(get("/api/reports/quarterly").with(
            user("reader").authorities(
                new SimpleGrantedAuthority("REPORT_READ")
            )
        ))
            .andExpect(status().isOk())
            .andExpect(content().string("quarterly-report"));

        mvc.perform(get("/api/admin/summary").with(
            user("reader").authorities(
                new SimpleGrantedAuthority("REPORT_READ")
            )
        ))
            .andExpect(status().isForbidden());
    }

    @Test
    void ordinaryUserCannotReadReport() throws Exception {
        mvc.perform(get("/api/reports/quarterly")
            .with(user("visitor").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleAdminCanEnterAdminArea() throws Exception {
        mvc.perform(get("/api/admin/summary")
            .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-summary"));
    }

    @Test
    void ownProfileManagerRejectsOtherUser() throws Exception {
        mvc.perform(get("/api/profiles/alice")
            .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"));

        mvc.perform(get("/api/profiles/alice")
            .with(user("bob").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void methodSecurityProtectsServiceDespiteWeakHttpFallback()
            throws Exception {

        mvc.perform(get("/api/service-report")
            .with(user("visitor").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/service-report").with(
            user("reader").authorities(
                new SimpleGrantedAuthority("REPORT_READ")
            )
        ))
            .andExpect(status().isOk())
            .andExpect(content().string("quarterly-report"));
    }

    @Test
    void postNeedsBothReportWriteAndCsrf() throws Exception {
        var writer = user("writer").authorities(
            new SimpleGrantedAuthority("REPORT_WRITE")
        );

        mvc.perform(post("/api/reports").with(writer))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/reports").with(writer).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));

        mvc.perform(post("/api/reports").with(
            user("reader").authorities(
                new SimpleGrantedAuthority("REPORT_READ")
            )
        ).with(csrf()))
            .andExpect(status().isForbidden());
    }
}
```

**Đọc kết quả:** các tests dùng `user(...)` dựng Authentication của test để kiểm tra **authorization**. Chúng **không** chứng minh BCrypt, login page, Basic header parsing hay JWT/IdP token verification thật. Muốn kiểm tra authentication boundary, thêm integration tests với credential/token thực qua filter chain phù hợp.

**Kỳ vọng:** tất cả tests ở trên **được thiết kế để pass** với project/cấu hình đầy đủ; bài học không khẳng định chúng đã được biên dịch/chạy trong workspace của người đọc. Dùng:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Lưu ý compiler và formatter:** Java cho phép ngắt dòng sau `import static org...request` rồi nối bằng `.SecurityMockMvcRequestPostProcessors...` như snippet, nhưng có thể dùng import một dòng nếu IDE muốn. Kiểm tra Gradle BOM tương thích Spring Security 6.x/Boot 3.x trước khi copy code.

## 8. Migrating AccessDecisionVoter và AccessDecisionManager tùy biến

Đây là phần khó hơn thay `antMatchers`. Với legacy custom voter, **đừng dịch tên class trước khi xác định logic thật**.

### 8.1 Mô hình legacy

Một `AccessDecisionVoter` cũ có thể trả:

- `ACCESS_GRANTED`: voter đồng ý cho phép.
- `ACCESS_DENIED`: voter phản đối.
- `ACCESS_ABSTAIN`: voter không có ý kiến hoặc không áp dụng.

`AccessDecisionManager` (chẳng hạn `AffirmativeBased`, `UnanimousBased`, `ConsensusBased`) kết hợp nhiều lá phiếu. Các chi tiết như **all-abstain decision**, chiến lược giải quyết phiếu hòa, deny precedence và exception handling có thể ảnh hưởng kết quả. Không đồng nhất “abstain” với “allow”.

Ví dụ policy cũ có thể là: “Cho phép nếu có `ROLE_SUPPORT` *hoặc* người dùng là chủ của record, **nhưng** chặn nếu record nằm trong trạng thái pháp lý đóng băng”. Nếu chỉ chuyển thành `anyOf(role, owner)` mà quên điều kiện đóng băng, app đã **nới quyền nghiêm trọng**.

### 8.2 Chuyển policy thành điều kiện rõ ràng

Viết logic bằng lời trước:

```text
canReadInvoice(actor, invoice):
    require actor is authenticated
    require invoice exists and belongs to correct tenant
    require invoice is not blocked by legal hold
    allow if actor has INVOICE_AUDITOR
             OR actor owns invoice
    otherwise deny
```

Đây là **pseudocode**, không phải Java implementation. Để bảo vệ quyền với object cụ thể, thường nên đặt logic trong domain policy service và method security:

```java
@PreAuthorize("@invoicePolicy.canRead(authentication, #invoiceId)")
public InvoiceDto readInvoice(String invoiceId) {
    return invoiceRepository.findAuthorizedDto(invoiceId);
}
```

Đoạn trên là **method snippet**, cần bean `invoicePolicy`, kiểu `InvoiceDto`, repository và authorization policy được triển khai thực tế. Ở production, phải kiểm tra tenant/ownership từ **nguồn dữ liệu backend đáng tin**, không tin `invoice.owner` do client gửi. Nếu load tài nguyên trước authorization, cần thiết kế để tránh lộ object existence, TOCTOU hoặc lỗi phân quyền giữa lúc check và lúc trả dữ liệu.

### 8.3 Có thể dùng manager ở HTTP route khi policy chỉ phụ thuộc request

Nếu quyết định chỉ dựa vào HTTP path/method và Authentication, `.access(new OwnProfileAuthorizationManager())` như ví dụ chạy được là đủ. Nếu cần kiểm tra object tồn tại và owner, ưu tiên policy service/method security để tránh đọc DB lặp hoặc cho phép route khác bypass.

Với logic tổ hợp rõ ràng, `AuthorizationManagers.allOf/anyOf` có thể giúp thay nhiều check đơn giản; nhưng trước khi thay custom `AccessDecisionManager`, phải xác minh truth table. Đừng âm thầm chuyển một rule “deny luôn thắng” thành `anyOf` khiến một grant bỏ qua deny.

### 8.4 AuthenticationManager vẫn là thành phần khác

Dự án có thể còn sử dụng:

```java
AuthenticationManager authenticationManager;
AuthenticationProvider customProvider;
```

Đó là **cấu phần authentication**: xử lý password, token hoặc yếu tố xác thực. Việc thay `AccessDecisionManager` bằng `AuthorizationManager` **không** có nghĩa phải bỏ `AuthenticationManager`. Hai tên gần giống nhưng trách nhiệm khác nhau.

## 9. Method security: @EnableMethodSecurity và các thay đổi thường quên

### 9.1 Từ @EnableGlobalMethodSecurity

Mã lịch sử Spring Security 5.x thường có:

```java
// LEGACY ONLY:
@EnableGlobalMethodSecurity(prePostEnabled = true)
```

Cấu hình mới thường dùng:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` bật `@PreAuthorize` / `@PostAuthorize` theo defaults phù hợp và sử dụng các authorization managers/interceptors mới. Không bê nguyên mọi tùy chọn của cấu hình cũ mà chưa kiểm tra version/default của project. `@Secured` và JSR-250 roles có thể cần bật cờ `securedEnabled`/`jsr250Enabled` nếu app dùng.

### 9.2 HTTP authorization không thay method security

Các tình huống cần method security:

- Cùng service có thể được gọi từ HTTP controller, job, message consumer hoặc một endpoint khác.
- Quyền phụ thuộc object ownership, tenant, amount, state, role và chính sách từ DB.
- HTTP matcher chỉ bảo vệ phạm vi route nhưng không có đủ dữ liệu để kiểm tra một record cụ thể.
- Logic dùng ở nhiều nơi, cần test độc lập.

Tuy vậy, method security **không miễn kiểm tra URL**: các route public/privileged nên có defense-in-depth. Dùng cả hai khi cần, chú ý test chồng policy và path coverage.

### 9.3 @PreAuthorize không phải một thứ “magic” cho mọi gọi nội bộ

Spring method security thường qua proxy. Nếu trong cùng bean gọi `this.protectedMethod()`, invocation có thể không qua proxy, dẫn tới bỏ kiểm tra. Với method protected, nên gọi qua bean do Spring quản lý, tránh self-invocation, và kiểm tra các chế độ proxy/aspect nếu thay đổi.

Nếu method chạy ở thread khác qua `@Async`, `SecurityContextHolder` thường gắn ThreadLocal: context không mặc nhiên propagate. Cần thiết kế `DelegatingSecurityContextAsyncTaskExecutor` hoặc service identity phù hợp, đồng thời test không rò context giữa các thread tái sử dụng. Đây là vấn đề **truyền identity**, không phải vấn đề DSL `authorizeHttpRequests`.

## 10. Nhiều SecurityFilterChain: securityMatcher khác requestMatchers

Một hệ thống có thể tách API `/api/**` và website `/**` thành nhiều chain. Khi đó cần phân biệt:

- **`http.securityMatcher(...)`:** chọn **request nào thuộc SecurityFilterChain đó**, trước cả phần authorizeHttpRequests bên trong.
- **`authorizeHttpRequests().requestMatchers(...)`:** chọn **rule authorization bên trong chain đã được chọn**.
- Các chain `SecurityFilterChain` được xét theo thứ tự `@Order`; **chain khớp đầu tiên** được sử dụng, không chạy tất cả chains rồi cộng dồn policies.

Ví dụ cấu hình rút gọn:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/login").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
```

Đây là **snippets của hai bean**, cần imports `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer` và một class `@Configuration`. Ở production, mỗi chain phải cấu hình CSRF, session, exceptions, auth mechanism và request matcher theo loại client. Đừng copy thẳng rồi tin rằng token bearer được xử lý: chain API trên dùng **HTTP Basic**, không phải Resource Server.

**Lỗi phổ biến:**

- Chain `/**` có `@Order(1)` sẽ nuốt `/api/**` trước khi API chain được xét.
- Không có fallback chain cho route ngoài `securityMatcher` có thể khiến route **không được bảo vệ bởi Spring Security** nếu không chain nào match.
- Đặt `requestMatchers("/api/**")` trong web chain không khiến request luôn đi qua web chain nếu API chain đã được chọn trước.
- Không kiểm tra path của `/actuator/**`, error endpoints, static resources, custom servlet mapping.

Viết tests cho **mỗi chain, mỗi auth scheme, mỗi route không khớp** và kiểm tra response 401/403/302 đúng kỳ vọng.

## 11. Dispatcher types, ERROR/FORWARD và khác biệt ở AuthorizationFilter

Servlet container có các dispatcher types như `REQUEST`, `FORWARD`, `ERROR` và `ASYNC`. Một request HTTP có thể phát sinh forward/error dispatch bên trong server. Khi nâng cấp sang `AuthorizationFilter`, việc kiểm tra authorization ở các dispatch khác có thể khác code legacy dựa trên `FilterSecurityInterceptor`.

Ví dụ một controller đã được phép nhưng forward sang view/template hoặc error handler có thể gặp 403 nếu rule chưa xem xét dispatcher/URL được dispatch. Trường hợp như vậy **không nên sửa bằng `anyRequest().permitAll()`**.

Nếu sau đánh giá thấy cần cho phép một số dispatcher types, DSL có thể hỗ trợ:

```java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        jakarta.servlet.DispatcherType.FORWARD,
        jakarta.servlet.DispatcherType.ERROR
    ).permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

Đây là **minh họa**; `permitAll` toàn bộ ERROR/FORWARD có thể không phù hợp mọi ứng dụng. Với endpoint nghiệp vụ thực, tránh để client điều khiển forward tới tài nguyên đặc quyền hoặc lộ nội dung qua error path. Nên test riêng dispatch flows cần có trong môi trường thật.

**Với async Servlet:** nếu `Callable` hoặc `DeferredResult` chạy qua thread khác, việc propagation SecurityContext và kiểm tra các dispatch liên quan cũng phải được test. Thay request authorization DSL không tự sửa tất cả vấn đề async context.

## 12. CSRF, CORS, servlet mapping và các cơ chế không nên bị “sửa nhầm”

### 12.1 CSRF không phải một rule authorizeHttpRequests

Một `POST /api/reports` từ browser có session/cookie có thể cần **CSRF token** dù actor có `REPORT_WRITE`. Đó là hai check độc lập:

- **Authorization:** actor có `REPORT_WRITE`?
- **CSRF:** unsafe request từ browser có token hợp lệ theo chiến lược CSRF?

Khi test POST bằng MockMvc, nếu muốn tập trung vào authorization, dùng `with(csrf())`; có test riêng thiếu CSRF → 403. Đừng viết `csrf.disable()` cho toàn app để “khắc phục” lỗi 403 sau nâng cấp. Với API bearer token stateless không dựa vào browser auto-sent cookie, mô hình CSRF có thể khác và cần đánh giá riêng.

### 12.2 CORS không được giải quyết bằng permitAll

Trình duyệt có preflight `OPTIONS`. Cần cấu hình CORS đúng origins/methods/headers và filter ordering, không mở toàn bộ endpoints chỉ vì preflight bị 403. `permitAll` không tự thêm `Access-Control-Allow-Origin`. Với browser credentials, không dùng wildcard origin kèm allowCredentials.

### 12.3 Đừng thay thế permitAll bằng web.ignoring bừa bãi

`permitAll` vẫn đưa request qua Spring Security filter chain (có thể áp các security headers, context, logging, CSRF ở unsafe methods...). `web.ignoring()` loại request khỏi Spring Security filter chain. Với static assets có thể có lý do riêng, nhưng **không dùng ignoring cho endpoint nghiệp vụ** chỉ để tránh việc authorization cấu hình sai.

### 12.4 Matcher và URL encoding

Matcher có thể phụ thuộc vào servlet path, `PathPattern`, encoding, URL normalization, trailing slash và container. Cần test URL như `/admin`, `/admin/`, `/admin/users`, encoded path segments và nhiều dispatcher. Không dựa vào giả định một pattern cũ có hiệu lực tương tự ở mọi phiên bản.

Một controller không được Spring MVC map có thể trả 404; điều đó không chứng minh authorization đã chặn. Với test quyền truy cập, hãy dùng **route có thực**, và assert status/body theo từng principal.

## 13. Phân biệt 401, 403, redirect và những false positives

| Tình huống | Kết quả thường gặp | Ý nghĩa |
| --- | --- | --- |
| `GET /api/reports/quarterly` không authentication (HTTP Basic demo) | 401 | Chưa có credential, cần authentication. |
| Reader thiếu `ROLE_ADMIN` vào admin | 403 | Đã authenticated nhưng không đủ quyền. |
| POST có quyền nhưng thiếu CSRF | 403 | Bị CSRF filter từ chối, không nhất thiết thiếu authority. |
| Web app chưa login dùng formLogin | 302 tới login page | Entry point của web UI, khác API 401. |
| Không có route/mapping | 404 | Chưa chắc authorization đã được test. |
| Filter chain không match route | Có thể bypass Spring Security | Cần kiểm tra SecurityFilterChain selection, không suy từ status 200. |
| Custom manager thiếu context/attribute | Nên deny theo policy | Không auto grant chỉ vì không đọc được principal. |

Để test thật sự có giá trị, luôn kiểm tra **chain được sử dụng**, route tồn tại, principal đã được tạo đúng, authorities đầu vào có chủ đích và body phản hồi xác nhận controller đúng.

## 14. Kế hoạch migration theo từng bước

### Bước 1: Chụp baseline

Lập danh sách **tất cả endpoints** được bảo vệ, các filter chains, roles/scopes, user journeys, controllers và method security annotations. Đặc biệt kiểm kê:

- Các URL public có ý nghĩa bảo mật (login, signup, reset password, actuator health, OAuth2 callback).
- Admin/report/tenant/data-export endpoints.
- Custom AccessDecisionManager, AccessDecisionVoter, PermissionEvaluator, role hierarchy.
- Những chỗ dùng `web.ignoring`, custom access expressions và servlet mapping.
- Request methods và dispatcher types.
- API clients (browser cookie, Basic, OAuth2/JWT, mTLS) và expected 401/403/302.

### Bước 2: Viết behavior tests trước khi sửa

Chạy positive và negative tests ở **version cũ**; ghi nhận request nào có quyền và request nào bị từ chối. Với custom voter, lập truth table cho mọi combination (grant/deny/abstain), bao gồm trường hợp tài nguyên không tồn tại, account disabled, tenant khác và service call.

### Bước 3: Nâng dependency có kiểm soát

Với Java 17+, Spring Boot 3.x và Spring Security 6.x, xác nhận rằng các modules cần có đã được khai báo. Không “nâng” bằng cách thay mã trong khi giữ một số Spring Security jars 5.x trên classpath. Để Boot BOM/quản lý phiên bản giúp tránh lệch dependency, rồi kiểm tra migration guide tương ứng các minor versions.

### Bước 4: Chuyển SecurityFilterChain và request DSL

Chuyển từ adapter/`authorizeRequests`/`antMatchers` sang bean `SecurityFilterChain`/`authorizeHttpRequests`/`requestMatchers`. Giữ thứ tự “cụ thể trước, tổng quát sau”, xem `anyRequest` và bảo vệ fallback. Không thay đổi các cơ chế authentication nếu không cần.

### Bước 5: Chuyển policy custom

Đối với một rule dùng `hasRole/hasAuthority`, ưu tiên built-in DSL. Với policy đa điều kiện, dùng custom `AuthorizationManager` hoặc method security/domain policy. So sánh **behavior, không chỉ class names**. Giữ rõ deny overrides, roles, scopes, tenant and ownership checks.

### Bước 6: Kiểm thử lại tất cả biên

Test:

- anonymous, authenticated, role thiếu, role đủ;
- path/public/static/admin/unknown;
- GET/POST/OPTIONS và CSRF;
- servlet FORWARD/ERROR/ASYNC;
- nhiều SecurityFilterChain và `@Order`;
- method security qua Spring proxy;
- OAuth2/JWT/principal mapping thực tế nếu liên quan;
- service method từ queue/async/background;
- reverse proxy/servlet path/case/trailing slash.

### Bước 7: Triển khai và quan sát

Theo dõi 401/403/302 rates, unexpected access grants, route coverage, login failures, CSRF rejections và logs `AccessDeniedException`. Tránh ghi secrets/tokens trong debug logs. Có kế hoạch rollback dependency/config và feature flags khi cần. Không đánh giá migration thành công chỉ vì “tỷ lệ 403 giảm”.

## 15. Ma trận kiểm thử bảo vệ tránh nới quyền

| Quy tắc | User/Request | Trước nâng cấp | Sau nâng cấp phải giữ |
| --- | --- | --- | --- |
| Public GET | Anonymous GET `/api/reports/public` | 200 | 200 |
| Protected report | Anonymous GET report riêng | 401/302 theo entry point | Giữ semantics tương ứng |
| Protected report | Reader có `REPORT_READ` | 200 | 200 |
| Protected report | Visitor chỉ `ROLE_USER` | 403 | 403 |
| Admin | Reader không `ROLE_ADMIN` | 403 | 403 |
| Admin | Admin có `ROLE_ADMIN` | 200 | 200 |
| Write | Writer có quyền nhưng thiếu CSRF | 403 trong session app | 403 |
| Write | Writer có quyền + CSRF | 2xx | 2xx |
| Object ownership | Bob xem profile Alice | 403 | 403 |
| Method security | User thiếu REPORT_READ gọi service | Deny | Deny |
| Unknown endpoint | Anonymous và authenticated | Theo fallback policy | Không tự nới thành permitAll |
| Multiple chains | API và web routes | Đúng auth scheme/chain | Không bị chain khác nuốt |
| Forward/error dispatch | Các dispatcher hợp lệ | Hành vi đã kiểm kê | Có chủ đích, không mở rộng không kiểm soát |
| Custom voter combinations | grant/deny/abstain permutations | Theo policy cũ | Tương đương hoặc thay đổi có phê duyệt |

**Lưu ý:** bảng dùng các status mang tính minh họa; 401 và 302 phụ thuộc entry point, còn 403 có thể do CSRF trước khi authorization. Trước/sau cần dùng **cùng flow và filter chain tương ứng** để so sánh có ý nghĩa.

## 16. Các lỗi thường gặp khi nâng cấp

| Lỗi | Nguyên nhân | Cách xác minh/sửa |
| --- | --- | --- |
| `antMatchers` không còn compile | API cũ đã bị loại trong Spring Security 6.x. | Dùng `requestMatchers` đúng nghĩa, test matcher semantics. |
| `WebSecurityConfigurerAdapter` không tìm thấy | Cấu hình class adapter đã bị loại. | Định nghĩa bean `SecurityFilterChain`, các beans liên quan. |
| Admin bỗng được vào với user thường | Broad rule `/api/**` đứng trước admin rule. | Sắp specific trước generic; regression 403. |
| Admin bị 403 dù user có "ADMIN" | `hasRole("ADMIN")` thường đòi `ROLE_ADMIN`. | So authorities thực tế, map issuer/roles đúng. |
| Custom voter “deny” bị bỏ qua | Chuyển nhầm sang `anyOf`/semantics khác. | Truth table + tests all-grant/deny/abstain. |
| Unauthenticated route bị 403 thay vì redirect | Đổi entry point/filter chain/CSRF behavior. | Phân biệt 401/403/302, xem `ExceptionTranslationFilter` và auth config. |
| POST test fail 403 | CSRF token thiếu, không phải thiếu role. | Dùng `with(csrf())` cho test authorization, giữ test CSRF âm tính. |
| Error page/forward bị chặn | Dispatcher authorization behavior khác. | Test FORWARD/ERROR, cấu hình matcher chính xác. |
| URL wildcard match khác phiên bản cũ | MVC/servlet path/PathPattern, trailing slash. | Test request thật và matcher tường minh nếu cần. |
| API request không có security | Không chain nào match sau `securityMatcher`. | Có fallback chain, kiểm tra @Order và path. |
| REST endpoint trả 302 HTML login | Web chain/formLogin nuốt API path. | Sửa chain selection, API entry point. |
| `@PreAuthorize` không chạy | Thiếu `@EnableMethodSecurity` hoặc self-invocation. | Kiểm tra proxy và unit/integration test service. |
| User có authenticated nhưng thiếu quyền dữ liệu | HTTP rule chỉ `authenticated`, không owner/tenant. | Method security/domain authorization trên resource. |
| `permitAll` bị đổi thành `web.ignoring` | Bỏ filter chain, mất các security filters cần thiết. | Kiểm tra headers/CSRF/logs, dùng permitAll khi phù hợp. |
| App dùng WebFlux nhưng copy HttpSecurity | Servlet và reactive API khác nhau. | Dùng `ServerHttpSecurity`/`authorizeExchange` cho WebFlux. |
| Có OAuth2 Login nhưng API Bearer không xác minh | AuthorizationManager không phải token decoder. | Cấu hình OAuth2 Resource Server/decoder đúng và test bearer auth thật. |

## 17. Checklist nhanh trước khi merge

- [ ] Chỉ dùng `authorizeHttpRequests`/`SecurityFilterChain` của Spring Security version tương thích; mã legacy chỉ còn trong tài liệu.
- [ ] Matcher cụ thể đứng trước matcher tổng quát, và `anyRequest` có ý nghĩa **deny/fallback** rõ.
- [ ] Tất cả URL và HTTP methods nhạy cảm có rule/test riêng; không bỏ route do nhiều filter chains.
- [ ] `hasRole`/`hasAuthority` được đối chiếu với authorities thực tế, không tự suy từ claims client gửi.
- [ ] Custom voter/AccessDecisionManager được chuyển theo truth table, không chỉ thay class names.
- [ ] Custom AuthorizationManager deny khi thiếu principal/path/object/risk context; không tin header không xác thực.
- [ ] `@EnableMethodSecurity` và `@PreAuthorize` được kiểm thử qua Spring proxy; ownership/tenant checks ở đúng tầng.
- [ ] CSRF, CORS, dispatcher types, OAuth2 callbacks, form login và API entry points được giữ đúng.
- [ ] Tests cover anonymous/reader/admin/writer, 401/403/302, POST+CSRF, object-level deny và cross-chain routing.
- [ ] Không nới `permitAll`/`web.ignoring` để né lỗi build hay 403.
- [ ] Có metrics/alert và phương án rollback sau khi triển khai.

**Ghi nhớ:** `authorizeRequests` + `AccessDecisionManager` là đường authorization cũ dựa trên filter/interceptor, metadata và voters. `authorizeHttpRequests` + `AuthorizationManager` dùng mô hình quyết định gắn với request matcher, dễ áp dụng built-in managers, custom policy và method security. **Điểm quyết định khi nâng cấp không phải thay được API, mà là chứng minh mọi quyền cho phép/từ chối vẫn đúng**, nhất là thứ tự matcher, semantics của custom voter, đa filter chain, quyền theo tài nguyên và những dispatcher/CSRF flows dễ bị bỏ sót.
