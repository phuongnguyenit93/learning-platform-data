# Bộ kiểm thử hồi quy cho đăng nhập, duy trì danh tính và thu hồi truy cập sau nâng cấp Spring Security

## 1. Bài toán: ứng dụng vẫn chạy nhưng ranh giới xác thực đã thay đổi

Nâng cấp Spring Boot, Spring Framework, Spring Security, servlet container hoặc thư viện xác thực không chỉ là đổi số phiên bản. Có thể không có lỗi biên dịch, màn hình login vẫn trả HTTP 302 và unit test vẫn xanh, nhưng những hành vi quan trọng đã thay đổi:

- `POST /login` nhận đúng password nhưng `SecurityContext` **không được lưu**: redirect thành công, request tiếp theo lại bị coi là anonymous.
- Người dùng A đã đăng nhập, nhưng request mới vô tình mang principal của B vì test giả lập `SecurityContextHolder` mà không gửi session/cookie đúng.
- Session ID trước/sau login không được luân chuyển; session fixation protection bị mất khi sửa filter chain.
- `GET /logout` bắt đầu thực hiện logout hoặc `POST /logout` không cần CSRF, tạo lỗ hổng forced logout.
- Logout redirect thành công nhưng session cũ vẫn được backend chấp nhận.
- Khóa tài khoản chỉ chặn login mới, **session đã xác thực** vẫn truy cập được vì authentication đã được lưu trong HTTP session.
- Resource Server trả 200 cho access token đã revoked vì validator/introspection/cache bị cấu hình khác sau nâng cấp.
- Refresh token cũ vẫn cấp access token mới sau rotation hoặc logout; các node chưa đồng bộ revocation state.
- SecurityFilterChain mới match sai path: `/api/**` chạy qua filter dành cho browser hoặc ngược lại.
- Test dùng `@WithMockUser`/`.with(user(...))` pass, nhưng luồng xác thực thật đã hỏng.
- Browser, reverse proxy, SSO callback, SameSite cookie hoặc TLS khác giữa trước/sau upgrade.

**Trọng tâm bài học:** xây dựng bộ kiểm thử hồi quy **có thể lặp lại** để so sánh bản nền và bản ứng viên, bao phủ ba bất biến: **(1) đăng nhập đúng và từ chối đúng; (2) danh tính không mất/không lẫn ở request tiếp theo; (3) quyền được thu hồi đúng và không tự sống lại**.

Ví dụ dùng **Java 17, Spring Boot 3.3.12 và Spring Security Servlet** để minh họa mã/lệnh cụ thể. Đây là **mốc lab được ghim** chứ không khẳng định nó là bản stable mới nhất vào mọi thời điểm. Với việc nâng thực tế lên Boot/Security version khác, đọc migration guide **đúng cặp phiên bản** và chạy cùng test contract trên bản cũ/bản mới; không copy BOM/test libraries cũ sang release mới nếu chúng không tương thích.

### 1.1. Kết quả học tập

Sau bài này, bạn sẽ:
1. Viết test matrices cho anonymous, credential sai, disabled account, session persistence, CSRF, session fixation, logout và account revocation.
2. Biết vai trò của `SecurityContextRepository`, `SecurityContextHolderFilter`, `SessionAuthenticationStrategy`, `LogoutFilter` và HTTP session.
3. Viết `MockMvc` tests thật sự tạo login session rồi **sử dụng lại chính session ấy** cho request khác.
4. Phân biệt `logout` session với access token OAuth2, refresh token và SSO session; không kiểm thử sai kỳ vọng.
5. Sử dụng một revocation guard minh họa để chứng minh tài khoản bị disable thì **session đang mở** bị từ chối.
6. Tách smoke tests, regression tests, browser/proxy E2E, multi-node và negative security tests.
7. Thiết kế CI so sánh baseline/candidate, lưu bằng chứng và gate rollout/rollback.

## 2. Định nghĩa bất biến trước khi thay đổi dependency

**Bất biến** là kết quả bảo mật mà hệ thống phải giữ dù framework implementation thay đổi. Viết chúng dưới dạng quan sát được ở API/browser, tránh assert quá nhiều chi tiết class/filter nội bộ.

| Nhóm | Bất biến | Test tối thiểu |
| --- | --- | --- |
| Đăng nhập | Anonymous không đọc protected endpoint | GET protected → redirect login / 401 theo contract |
| Đăng nhập | Credential đúng được xác minh qua provider thật | POST login đúng → authenticated, success redirect |
| Đăng nhập | Password sai không tạo authenticated principal | POST login sai → failure, không được xem dữ liệu |
| Đăng nhập | Account disabled/locked không đăng nhập được | Form login với account disabled → failure |
| CSRF | Login/POST thay đổi trạng thái phải có token ở browser-session flow | POST login/logout/setting thiếu token → 403 |
| Duy trì danh tính | Request mới cùng session đọc đúng user | Login → GET /me với session cũ → 200 + đúng principal |
| Cách ly phiên | Session A không biến thành B | Hai login/browser contexts → principal tách biệt |
| Session fixation | ID trước/sau login đổi | Pre-auth session ID khác post-auth session ID |
| Quyền | Đã login nhưng thiếu role vẫn bị chặn | USER gọi ADMIN → 403 |
| Logout | POST logout + CSRF chấm dứt session | Session invalidated, request tiếp không truy cập được |
| Logout | GET logout không có side effect | GET chỉ confirmation; session vẫn hợp lệ |
| Thu hồi | Disable account **chặn cả session cũ** nếu có yêu cầu nghiệp vụ | Disable → request cũ nhận 401/403, session bị revoke |
| Thu hồi | Access token revoked/expired/wrong issuer/audience không vào API | Token invalid → 401 |
| Thu hồi | Refresh token bị rotate/reuse/revoked không mint token mới | Reuse old refresh → reject, audit |
| Multi-node | Auth và revoke nhất quán qua LB/pod | Đổi node → identity đúng; revoke → deny mọi node |
| Trình duyệt | Cookie/TLS/redirect thực phù hợp | Browser HTTPS, Secure/HttpOnly/SameSite, cookie jar |
| Audit | Failure không lộ credential/token/session | Logs/traces redacted, request-id |

**Kết luận của ma trận:** “Login trả 302” chỉ chứng minh một đoạn. Bộ regression phải đi tới **lần request kế tiếp** và **lần request sau thu hồi**.

## 3. Baseline và candidate: kiểm thử trước–sau có ý nghĩa

Chọn hai môi trường:
- **Baseline:** bản đang hoạt động trước khi nâng, gồm app artifact, Spring Boot/Security transitive versions, Java runtime, Tomcat, reverse proxy và cấu hình thật.
- **Candidate:** bản mới với thay đổi **được công bố**: dependency, JVM, config, custom authentication code, filter chain, session repository hoặc gateway.

Không thay đồng thời nhiều yếu tố mà không ghi nhận nếu cần xác định nguồn hồi quy. Ghim phiên bản và lưu artifact digest; không so sánh hai môi trường với dữ liệu/người dùng/cookie policy khác nhau rồi kết luận nâng cấp làm hỏng authentication.

### 3.1. Ghi lại fingerprint trước khi test

Một bản report nhỏ có:

~~~text
application: authentication-service
baseline: release-X, artifact sha256 ...
candidate: release-Y, artifact sha256 ...
java: 17 (hoặc runtime thực tế)
spring-boot: phiên bản phân giải cuối cùng
spring-security: phiên bản phân giải cuối cùng
servlet-container: embedded/external và version
session-store: local / JDBC / Redis / khác
auth-modes: form session / bearer / SSO / Basic / remember-me
csrf: enabled cho browser-session paths
public-origin: https://login.example.org
ingress/LB: image/version và forwarded-headers strategy
browser: Chromium/Firefox/WebKit theo support
migration-notes: tham chiếu những thay đổi trong changelog
~~~

Lấy dependency thực tế:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-config \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-test \
  --configuration testRuntimeClasspath
~~~

Nếu không có Gradle Wrapper, có thể dùng Gradle được cài và được hỗ trợ bởi release. Lệnh output thay đổi theo phiên bản; không lưu credential/secret environment trong build logs.

### 3.2. Contract tests giống nhau, đổi đúng application artifact

Không viết test chỉ chạy trên candidate rồi cho rằng đã regression; phải chạy **cùng bộ test** trên baseline và candidate, sử dụng test data độc lập và cùng external contract.

Những thay đổi hành vi **được phê duyệt** nên lưu trong một danh sách explicit, ví dụ chuyển anonymous API từ redirect login sang 401 JSON; kiểm tra được quyết định product/security. Không dùng snapshot toàn bộ HTML/error JSON dễ biến động rồi bỏ qua sự thay đổi quyền quan trọng.

Ma trận kết quả:

| Case | Baseline | Candidate | Quyết định |
| --- | --- | --- | --- |
| Valid login → identity at next request | PASS | PASS | Giữ |
| Logout → old session rejected | PASS | FAIL | Chặn rollout |
| Invalid CSRF login | PASS | PASS | Giữ |
| Disabled active session | NOT IMPLEMENTED | PASS | Tính năng mới, phải mô tả |
| JWT wrong audience rejected | PASS | FAIL | Chặn rollout |
| Login page CSS hash changed | Changed | Changed | Có thể không liên quan security |

**Không được tự đổi expected từ 403 thành 200 chỉ để candidate pass.** Mọi khác biệt authentication/authorization/revocation phải được review rõ.

## 4. Vì sao nâng Spring Security có thể làm mất danh tính sau redirect?

Trong Spring Security Servlet, `SecurityContextHolder` lưu Authentication theo ngữ cảnh xử lý request. Muốn một request **khác** nhận lại principal, authentication cần được lưu/khôi phục qua `SecurityContextRepository`, thường có `HttpSessionSecurityContextRepository` khi dùng HTTP session.

Ở Spring Security 6, hướng dẫn migration nhấn mạnh **explicit saving** đối với custom authentication mechanisms: `SecurityContextHolderFilter` **đọc** context từ repository, còn code tự tạo `Authentication` ở custom filter/controller phải lưu context rõ ràng nếu muốn duy trì qua requests.

Sơ đồ:

~~~text
POST /custom-login
    |
    +-- AuthenticationManager.authenticate(...) -> authenticated
    |
    +-- SecurityContextHolder.setContext(context)
    |
    +-- [THIẾU securityContextRepository.saveContext(...)]
    |
    v
HTTP 200 / redirect có vẻ thành công

GET /me (request MỚI, cùng JSESSIONID)
    |
    +-- SecurityContextHolderFilter đọc repository
    +-- Không có context đã lưu -> anonymous
    v
302 /login hoặc 401
~~~

Các cơ chế **formLogin mặc định** của Spring Security xử lý persistence phù hợp; lỗi đặc biệt dễ xảy ra khi tự viết converter/filter/JSON controller để login và chỉ set ThreadLocal context.

**Bản sửa đúng ở custom login** (mảnh code minh họa, không phải một controller độc lập):

~~~java
Authentication candidate =
        UsernamePasswordAuthenticationToken.unauthenticated(
                loginRequest.username(), loginRequest.password());

Authentication authenticated =
        authenticationManager.authenticate(candidate);

SecurityContext context =
        securityContextHolderStrategy.createEmptyContext();
context.setAuthentication(authenticated);
securityContextHolderStrategy.setContext(context);

// BƯỚC QUAN TRỌNG để request tiếp theo đọc được danh tính.
securityContextRepository.saveContext(context, request, response);
~~~

Production còn phải áp dụng `SessionAuthenticationStrategy` cho session fixation/concurrent sessions, CSRF login, rate limit, account status và error handling; ví dụ chỉ làm rõ **explicit save**. Không tự viết lại default Spring form-login trừ khi cần custom behavior.

### 4.1. Session fixation và yêu cầu về ID

Spring Security dùng chiến lược đổi session ID sau khi authentication thành công trên servlet container hiện đại, thường `changeSessionId`. Vì vậy test nên ghi **pre-login ID** (từ anonymous session lưu CSRF token) và assert **post-login ID khác**. Không in ID thật vào test logs; chỉ so sánh in-memory. Không giả định post-login principal được xác minh chỉ vì ID đổi — cần test riêng.

### 4.2. Duy trì danh tính không đồng nghĩa chấp nhận credential mãi mãi

Với form login, SecurityContext nằm trong session; nếu tài khoản bị disable ở DB sau khi login, các request có thể vẫn thấy authenticated principal cũ. Đó **không tự động** là lỗi framework. Nếu requirement nói “disable/revoke phải chặn phiên đã mở trong ≤N giây”, sản phẩm phải có chiến lược: session invalidation, session version, token version, revocation store, security epoch hoặc kiểm tra account status theo mỗi request/khoảng cache TTL.

Test hồi quy phải dựa trên **cam kết revocation của ứng dụng**, không mặc định rằng `UserDetailsService` được đọc lại ở mọi request.

## 5. Thiết kế project lab có kiểm thử thật

Ta tạo một ứng dụng Spring Boot 3.3.12 / Java 17 với:
- HTML form login mặc định Spring Security, CSRF bật.
- User `student` có role `USER`, `auditor` có role `USER` để test cách ly session.
- Protected `GET /me` và `POST /preferences`; `GET /admin` yêu cầu `ADMIN`.
- HTTP session lưu SecurityContext sau form login.
- Một `AccountRevocationGuard` **do lab tự cài đặt** để vô hiệu hóa session đang hoạt động khi `student` bị khóa.
- JUnit/MockMvc test request thật và tái sử dụng `MockHttpSession`, không chèn `@WithMockUser` để giả login.
- Thêm một Java 17 thuần để mô tả revocation invariant độc lập, tránh phụ thuộc server khi người mới muốn chạy nhanh.

**Mục tiêu bài học:** kiểm tra *boundary* phiên và rút quyền, không dựng hệ thống quản lý user production. `AccountState` chỉ dùng AtomicBoolean trong một JVM; ở multi-node thực tế phải có nguồn trạng thái tập trung và cache invalidation/latency rõ.

### 5.1. Cấu trúc source

~~~text
auth-regression-lab/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/java/demo/regression/
│   │   ├── RegressionApplication.java
│   │   ├── AccountState.java
│   │   ├── AccountRevocationGuard.java
│   │   ├── SecurityConfig.java
│   │   ├── Preferences.java
│   │   └── ProtectedController.java
│   └── test/java/demo/regression/
│       └── AuthenticationRegressionTest.java
└── RevocationInvariant.java
~~~

### 5.2. Gradle config

`settings.gradle`:

~~~groovy
rootProject.name = 'auth-regression-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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

Spring Boot dependency management chịu trách nhiệm phân giải Spring Security cùng release line. Khi nâng candidate, nâng BOM/plugin và rà soát versions thực tế; không ép một `spring-security-web` mới vào Boot cũ mà thiếu compatibility review.

### 5.3. Application Java 17

`src/main/java/demo/regression/RegressionApplication.java`:

~~~java
package demo.regression;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegressionApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegressionApplication.class, args);
    }
}
~~~

### 5.4. AccountState — dữ liệu thu hồi giả để thử nghiệm

`src/main/java/demo/regression/AccountState.java`:

~~~java
package demo.regression;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class AccountState {
    private final AtomicBoolean disabled = new AtomicBoolean(false);

    public boolean isDisabled() {
        return disabled.get();
    }

    public void disable() {
        disabled.set(true);
    }

    public void restore() {
        disabled.set(false);
    }
}
~~~

Đây là **state chỉ trong JVM của một app instance**, không phải distributed revocation store. Test multi-node phải dùng Redis/JDBC/event policy hoặc tích hợp identity service thật và kiểm tra consistency. Tùy yêu cầu, còn cần audit actor, timestamp, reason, expiry và revocation transaction.

### 5.5. Guard để thu hồi cả phiên đã mở

`src/main/java/demo/regression/AccountRevocationGuard.java`:

~~~java
package demo.regression;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class AccountRevocationGuard extends OncePerRequestFilter {

    private final AccountState state;

    public AccountRevocationGuard(AccountState state) {
        this.state = state;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        boolean studentSession = auth != null
                && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken)
                && "student".equals(auth.getName());

        if (studentSession && state.isDisabled()) {
            // Thu hồi session CŨ, không chỉ chặn lần login mới.
            HttpSession session = request.getSession(false);
            if (session != null) {
                session.invalidate();
            }
            SecurityContextHolder.clearContext();
            response.setHeader("Cache-Control", "no-store");
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        chain.doFilter(request, response);
    }
}
~~~

**Cách hoạt động:** Spring Security khôi phục context của request từ session trước khi guard chạy; guard nhìn principal `student` và từ chối nếu state bị vô hiệu hóa. Nó invalidate session rồi trả HTTP **401** theo **contract riêng của lab**. Đây **không** phải chức năng tự động mặc định của Spring Security khi admin disable account.

**Cảnh báo sản xuất:**
- Không tra account bằng một `AtomicBoolean` dùng chung cho mọi user; map theo stable user ID + tenant, kiểm soát security epoch/revocation timestamp.
- Định nghĩa cache TTL/consistency SLA và **fail-closed** khi revocation store không khả dụng theo risk model. Không cho truy cập chỉ vì cache/DB timeout.
- Bảo vệ race giữa request đang xử lý và lệnh revoke; test semantics “request bắt đầu sau khi revoke committed” khác với “hủy mọi request đang xử lý”.
- Tránh tạo session mới khi kiểm tra: `getSession(false)`.
- Khi trả 401 từ một web session endpoint, ứng dụng thực có thể muốn redirect và clear cookie; 401 ở đây để test phân biệt revocation rõ ràng.
- Trong distributed system, invalidate session qua shared session repository hoặc server-side revocation check; không phụ thuộc JVM-local `HttpSession`/AtomicBoolean.

### 5.6. Preferences state để kiểm tra không có side effect

`src/main/java/demo/regression/Preferences.java`:

~~~java
package demo.regression;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class Preferences {
    private final AtomicReference<String> theme =
            new AtomicReference<>("light");

    public String getTheme() {
        return theme.get();
    }

    public void setTheme(String value) {
        theme.set(value);
    }

    public void reset() {
        theme.set("light");
    }
}
~~~

Dữ liệu lab chung một JVM chỉ nhằm test CSRF và side effect. Production phải lưu setting theo user/tenant, kèm authorization và persistence.

### 5.7. SecurityFilterChain

`src/main/java/demo/regression/SecurityConfig.java`:

~~~java
package demo.regression;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder, AccountState state) {

        String studentHash = encoder.encode("student-password-123");
        String auditorHash = encoder.encode("auditor-password-123");

        return username -> {
            if ("student".equals(username)) {
                return User.withUsername("student")
                        .password(studentHash)
                        .roles("USER")
                        .disabled(state.isDisabled())
                        .build();
            }

            if ("auditor".equals(username)) {
                return User.withUsername("auditor")
                        .password(auditorHash)
                        .roles("USER")
                        .build();
            }

            throw new UsernameNotFoundException(
                    "Account not found");
        };
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, AccountState state) throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(login -> login
                        .defaultSuccessUrl("/me", true))
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .addFilterBefore(
                        new AccountRevocationGuard(state),
                        AuthorizationFilter.class)
                .build();
    }
}
~~~

Tại sao chỉ dùng **một** filter chain? Để người học nhìn rõ request qua login → session → guard → authorization. Nếu sản phẩm có `/api/**` Bearer-only, cần chain riêng, matcher/`@Order` rõ ràng; test hai scheme độc lập. Đừng tắt CSRF trên toàn ứng dụng chỉ để test đăng nhập.

`formLogin` của Spring Security thực hiện xác minh và persistence cho **session auth**, `csrf` bảo vệ unsafe actions. Guard đứng trước `AuthorizationFilter` nhưng sau các bước khôi phục authentication context; nó **không thay** password validation lúc login. `UserDetailsService` đọc `state.isDisabled()` ở **mỗi lần đăng nhập mới**, còn guard kiểm tra ở mỗi protected request của student session.

### 5.8. Protected endpoints

`src/main/java/demo/regression/ProtectedController.java`:

~~~java
package demo.regression;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProtectedController {

    private final Preferences preferences;

    public ProtectedController(Preferences preferences) {
        this.preferences = preferences;
    }

    @GetMapping(value = "/health",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String health() {
        return "OK";
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/preferences")
    public Map<String, String> preferences() {
        return Map.of("theme", preferences.getTheme());
    }

    @PostMapping("/preferences")
    public Map<String, String> update(
            @RequestParam String value) {
        if (value.isBlank() || value.length() > 30) {
            throw new IllegalArgumentException(
                    "Invalid value in lab");
        }

        preferences.setTheme(value);
        return Map.of("theme", preferences.getTheme());
    }
}
~~~

`/me` hiển thị username, nhưng không trả session ID, password, authorities raw hoặc token. `/admin` để kiểm tra authenticated-but-forbidden. `/preferences` là thao tác có side effect, phải có CSRF token khi auth dựa trên cookie session.

## 6. JUnit/MockMvc regression tests thực sự đi qua login

**Lỗi thường gặp:** viết `mvc.perform(get("/me").with(user("student")))` và kết luận “login/duy trì session hoạt động”. Thực chất helper `user()` chèn Authentication vào một request test mà **không** thực hiện password login/CSRF/session persistence. Dùng nó để test **authorization**, không dùng làm bằng chứng login end-to-end.

Spring Security Test cung cấp `formLogin()` (gửi POST login với CSRF token hợp lệ), `logout()`, `csrf()` và result matchers `authenticated()/unauthenticated()`. Lấy `MockHttpSession` từ response login thật rồi gửi nó ở request kế tiếp để kiểm tra `SecurityContextRepository`.

`src/test/java/demo/regression/AuthenticationRegressionTest.java`:

~~~java
package demo.regression;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationRegressionTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AccountState account;

    @Autowired
    Preferences prefs;

    @AfterEach
    void cleanup() {
        account.restore();
        prefs.reset();
    }

    private MockHttpSession loginAs(
            String username, String password) throws Exception {
        MvcResult result = mvc.perform(formLogin()
                        .user(username)
                        .password(password))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername(username))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void anonymousCannotReadProtectedIdentity() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void correctPasswordCreatesAuthentication() throws Exception {
        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void wrongPasswordNeverAuthenticates() throws Exception {
        mvc.perform(formLogin()
                        .user("student")
                        .password("wrong-password"))
                .andExpect(unauthenticated())
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void loginPostWithoutCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "student")
                        .param("password", "student-password-123"))
                .andExpect(status().isForbidden());
    }

    @Test
    void securityContextSurvivesIndependentHttpRequests()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"));

        mvc.perform(get("/preferences").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void twoSessionsDoNotMixPrincipals() throws Exception {
        MockHttpSession first =
                loginAs("student", "student-password-123");
        MockHttpSession second =
                loginAs("auditor", "auditor-password-123");

        mvc.perform(get("/me").session(first))
                .andExpect(jsonPath("$.username").value("student"));

        mvc.perform(get("/me").session(second))
                .andExpect(jsonPath("$.username").value("auditor"));
    }

    @Test
    void roleCheckStillDeniesAuthenticatedNonAdmin()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void unsafePostMissingCsrfHasNoSideEffect()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(post("/preferences")
                        .session(session)
                        .param("value", "dark"))
                .andExpect(status().isForbidden());

        assertThat(prefs.getTheme()).isEqualTo("light");

        mvc.perform(post("/preferences")
                        .session(session)
                        .with(csrf())
                        .param("value", "dark"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void getLogoutDoesNotImmediatelyRevokeSession()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(get("/logout").session(session))
                .andExpect(status().isOk());

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void logoutWithoutCsrfDoesNotRevokeSession()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk());
    }

    @Test
    void logoutWithCsrfInvalidatesTheSession()
            throws Exception {

        MockHttpSession session =
                loginAs("student", "student-password-123");

        mvc.perform(post("/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));

        assertThat(session.isInvalid()).isTrue();

        // Không gắn lại object MockHttpSession đã bị invalidate.
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void disabledAccountCannotLoginAgain() throws Exception {
        account.disable();

        mvc.perform(formLogin()
                        .user("student")
                        .password("student-password-123"))
                .andExpect(unauthenticated())
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void disablingAccountRevokesAlreadyOpenSession()
            throws Exception {

        MockHttpSession oldSession =
                loginAs("student", "student-password-123");

        mvc.perform(get("/me").session(oldSession))
                .andExpect(status().isOk());

        account.disable();

        mvc.perform(get("/me").session(oldSession))
                .andExpect(status().isUnauthorized());

        assertThat(oldSession.isInvalid()).isTrue();
    }

    @Test
    void sessionIdRotatesDuringFormLogin() throws Exception {
        MvcResult page = mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession before =
                (MockHttpSession) page.getRequest().getSession(false);
        assertThat(before).isNotNull();
        String beforeId = before.getId();

        MvcResult login = mvc.perform(post("/login")
                        .session(before)
                        .with(csrf())
                        .param("username", "student")
                        .param("password", "student-password-123"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("student"))
                .andReturn();

        MockHttpSession after =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(after).isNotNull();
        assertThat(after.getId()).isNotEqualTo(beforeId);
    }
}
~~~

### 6.1. Đọc lại bộ test theo ba bất biến

**Đăng nhập:** Test anonymous, password đúng/sai, CSRF thiếu, disabled account, role insufficient. `formLogin()` thực hiện request qua `UsernamePasswordAuthenticationFilter` với CSRF hợp lệ, không giả định user tự xuất hiện.

**Duy trì danh tính:** Helper lấy `MockHttpSession` từ **request login thật**. Hai lần `GET` khác nhau cùng session phải trả đúng principal; hai session khác nhau phải không lẫn. Test fixation so ID trước/sau mà không in giá trị.

**Thu hồi:** POST logout thiếu CSRF không chấm dứt session; POST hợp lệ phải invalidate. Disable account **đang có session** được guard phát hiện và 401 + invalidate; đây là behavior lab đã tự cài, giúp test không xanh giả khi chỉ chặn login mới.

### 6.2. Số lượng và kỳ vọng

Lớp trên có **14 test methods**. Kỳ vọng khi lab đúng:
- 14 tests pass trên Spring Boot 3.3.12/Java 17 và embedded servlet container tương thích.
- Không có authenticated identity trên request anonymous/password sai.
- Sau login, session được tái sử dụng qua request độc lập.
- Thu hồi session không “hồi sinh” ở request mới.

**Tính trung thực:** đây là mã ví dụ đã được rà soát theo API Spring Security; không tuyên bố đã được compile hay thực thi trong tài liệu. Nếu CI báo fail, xem stack trace/log thực, không sửa expected 401/403 thành 200, không tắt CSRF và không chuyển test sang `with(user())` để che vấn đề persistence.

### 6.3. Điều cần bổ sung khi test thật qua container

`MockHttpSession` không phải browser cookie jar hoặc distributed session store. Trong môi trường thật, hãy **giữ nguyên JSESSIONID cookie** sau login và gửi request tiếp theo qua HTTP client/browser, không chỉ khởi tạo mock session. Sau logout, thử lại cookie **cũ** đối với backend/proxy — không được authenticated. Nếu dùng distributed session repository, test trên **hai app instances khác nhau**. Với MockMvc, không nên tái gắn một `MockHttpSession` đã invalidate vì test object có thể ném lỗi thay vì mô phỏng cookie cũ của browser.

## 7. Chạy bài lab và đọc kết quả

Yêu cầu: JDK 17+ và Gradle Wrapper tương thích; nếu chưa có wrapper, cài Gradle phù hợp rồi tạo wrapper bằng một quy trình độc lập.

~~~bash
# Linux/macOS:
./gradlew clean test

# Windows:
# gradlew.bat clean test

# Nếu dự án demo chưa có Gradle Wrapper:
gradle clean test
gradle bootRun
~~~

Không tự ghi một stdout Gradle cố định vì test runner, dependency resolution và environment khác nhau. Kỳ vọng là bộ test pass theo contract, nhưng **actual result** chỉ có sau khi người học chạy.

### 7.1. Java 17 thuần: mô phỏng trạng thái revoke không cần Spring

Để hiểu rõ ràng rằng có một session/token hợp lệ **không** có nghĩa nó tồn tại vĩnh viễn, tạo `RevocationInvariant.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RevocationInvariant {
    record Session(String id, String user, long issuedVersion) {}

    public static void main(String[] args) {
        Map<String, Long> currentVersion = new HashMap<>();
        currentVersion.put("alice", 1L);

        Session before = new Session("local-lab-id", "alice", 1L);
        System.out.println("before revoke: "
                + valid(before, currentVersion));

        // Admin quyết định thu hồi tất cả session của alice:
        currentVersion.put("alice", 2L);
        System.out.println("after revoke: "
                + valid(before, currentVersion));

        Session fresh = new Session("new-lab-id", "alice", 2L);
        System.out.println("new session: "
                + valid(fresh, currentVersion));
    }

    private static boolean valid(
            Session session, Map<String, Long> versions) {
        Long current = versions.get(session.user());
        return current != null
                && current.longValue() == session.issuedVersion();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RevocationInvariant.java
java RevocationInvariant
~~~

Kết quả deterministic:

~~~text
before revoke: true
after revoke: false
new session: true
~~~

Ý nghĩa: session giữ phiên bản xác thực tại thời điểm cấp. Khi nguồn tin cậy nâng `authVersion`, session cũ thất hiệu lực, kể cả khi cookie/session ID còn tồn tại. **Đây là mô hình học thuật**, không phải production token signing/session implementation: mã dùng `HashMap` không thread-safe, ID cố định không phải CSPRNG, thiếu DB consistency/expiry và chống replay. Trong hệ thống thật, token/session version phải đến từ nguồn tin cậy, tra theo user ID, kiểm soát race/caching, không để client tự khai phiên bản.

## 8. Trọng tâm nâng phiên bản: Session Management migration

Những thay đổi phải review trong upgrade:

| Khu vực | Cần xác minh trước/sau | Rủi ro |
| --- | --- | --- |
| `SecurityContextHolderFilter` | Khi nào context được đọc, ai save, lúc request kết thúc được clear | User login rồi request sau anonymous |
| `SecurityContextRepository` | HttpSession / RequestAttribute / Delegating / Null | Session đột ngột stateful/stateless |
| `requireExplicitSave` | Custom login có gọi `saveContext` không | Persist bị mất sau nâng |
| `SessionAuthenticationStrategy` | Được gọi khi thành công; fixation, concurrent sessions | Session ID cũ tái sử dụng |
| `sessionCreationPolicy` | `IF_REQUIRED` / `ALWAYS` / `NEVER` / `STATELESS` | Nhiều session vô ý hoặc không lưu auth |
| `LogoutFilter` | POST + CSRF, invalidate session/context/repository | Logout redirect nhưng quyền chưa revoke |
| `AuthorizationFilter` | Matcher/method và order | Protected path trở thành public |
| `ExceptionTranslationFilter` | Anonymous vs authenticated denied, entrypoint | Sai 401/403/302 gây che lỗi |
| `CsrfFilter` | Token repo, handler, SPA rotation sau login/logout | Login CSRF, unsafe POST bypass |
| `UserDetailsService`/provider | Disabled/locked/password encoder | Cấp auth cho account sai trạng thái |
| Remember-me | Cookie/token persistence, theft/replay, logout cleanup | Đăng xuất xong vẫn tự login lại |
| OAuth2 Resource Server | JWT decoder/introspection validation, scopes/aud/iss | Token sai vẫn được chấp nhận |
| Session store | Redis/JDBC serialization/TTL/spring-session versions | Mất phiên khi rolling deployment |
| Proxy/cookie | Forwarded HTTPS, Secure/SameSite/Domain | Browser không giữ session hoặc gửi sai scope |

### 8.1. Ví dụ một test mới phát hiện upgrade làm hỏng persistence

Một test dễ bị đánh lừa:

~~~java
// Chỉ minh họa: KHÔNG chứng minh login thật.
mvc.perform(get("/me").with(user("student")))
   .andExpect(status().isOk());
~~~

Test đúng:

~~~java
// Mảnh minh họa trong một @SpringBootTest + @AutoConfigureMockMvc:
MvcResult login = mvc.perform(formLogin()
        .user("student").password("student-password-123"))
    .andExpect(authenticated().withUsername("student"))
    .andReturn();

MockHttpSession session =
    (MockHttpSession) login.getRequest().getSession(false);

mvc.perform(get("/me").session(session))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.username").value("student"));
~~~

Nếu custom auth filter chỉ set `SecurityContextHolder` nhưng không `saveContext`, test loại hai có thể fail dù test loại một luôn xanh. Đây là bài test regression quan trọng khi đổi Spring Security 5→6 hoặc thiết kế lại flow JSON login.

### 8.2. Khi có nhiều SecurityFilterChain

Ví dụ hệ thống có:
- `/web/**` dùng session cookie, form login/CSRF.
- `/api/**` dùng OAuth2 Bearer, stateless.
- `/actuator/health` public nhưng các endpoint admin cần role.
- OIDC/SAML callbacks theo protocol riêng.

Khi upgrade, yêu cầu test matcher precedence và filter selection:
1. Session cookie **không** vô tình xác thực cho API Bearer-only.
2. Bearer token không vô tình bật login page redirect cho API.
3. `/admin/**` không bị chain có `permitAll` match trước.
4. CORS và CSRF exceptions chỉ áp dụng **đúng endpoint/protocol** cần thiết.
5. Session persistence của form không bị `NullSecurityContextRepository` từ API chain ảnh hưởng.
6. Không gửi đồng thời cookie/Bearer khiến app chọn cơ chế ngoài contract.

Dùng `@Order` + `securityMatcher` rõ ràng; regression nên assert response status, principal và headers theo contract ở từng route. Không cần assert tên mọi filter (dễ đổi khi framework nâng).

## 9. Logout không đồng nghĩa thu hồi mọi token

Với **session-based form login**, `POST /logout` của Spring Security mặc định invalidate HTTP session, clear SecurityContext và CSRF token/remember-me state tương ứng. Nó **không** mặc định gửi lệnh thu hồi mọi access token mà client đã giữ, không logout tất cả browser khác và không kết thúc IdP SSO session bên ngoài.

Đặc biệt với OAuth2:
- **JWT access token self-contained** còn hạn có thể tiếp tục được resource server chấp nhận nếu chỉ verify chữ ký/`exp`/`iss`/`aud` mà không check denylist, `authVersion`, `jti` hoặc session binding.
- **Opaque token** có thể được chặn qua introspection nếu AS đánh dấu `active=false`; nhưng cache ở gateway/RS có thể kéo dài hiệu lực cho tới TTL.
- **Refresh token** thường cần rotation và revocation thực hiện ở authorization server; revoke refresh token không nhất thiết làm JWT access token cũ biến mất tức thì.
- **OIDC/SAML login session** ở IdP là một trạng thái khác local application session; back-channel/front-channel logout, state/correlation và session mapping phải được kiểm thử theo protocol.

**Chỉ tiêu hồi quy phải ghi rõ SLA thu hồi**: ví dụ “session local bị từ chối ngay ở request sau logout”; “opaque token bị từ chối sau tối đa N giây theo cache TTL”; “JWT có thể tồn tại đến exp nếu policy cho phép”. Nếu yêu cầu **thu hồi tức thì JWT**, thiết kế phải có additional validation/revocation architecture, không giả định `SecurityContextLogoutHandler` làm việc đó.

### 9.1. Ma trận Bearer/refresh token cần thêm trong thực tế

| Test | Setup | Expected |
| --- | --- | --- |
| No Bearer token | GET API được bảo vệ không Authorization | 401 + Bearer challenge |
| Expired access token | Clock cố định sau `exp` | 401, không vào controller |
| Not-yet-valid | `nbf` ở tương lai | 401 |
| Wrong issuer | `iss` không nằm trust allowlist | 401 |
| Wrong audience | `aud` không dành cho API này | 401 theo custom audience validation |
| Invalid signature/`alg` | Token giả mạo | 401 |
| Missing scope | Token hợp lệ nhưng thiếu authority | 403 |
| Revoked opaque token | AS/introspection `active=false` | 401 trong bound của cache TTL |
| Revoked JWT | `jti` denylist/authVersion đã cập nhật | 401 **nếu** RS thực sự check revocation |
| Refresh rotation | Old refresh token dùng lại | Từ chối, xử lý token family theo policy |
| Concurrent refresh | Hai requests dùng một refresh token | Một transaction thắng, reuse bị nhận diện |
| Logout | Local session ended | Không dùng local session; Bearer token kiểm riêng |
| Clock skew | Timestamp gần exp/nbf | Chỉ chấp nhận skew policy, không vô hạn |
| Token cross-tenant | Scope đúng nhưng tenant sai | 403/404, không lộ dữ liệu |

### 9.2. Ví dụ test pseudo cho token revocation, không tự nhận là Spring default

~~~java
// Pseudocode test contract cho một Resource Server.
// Không phải một @Test class độc lập: cần JwtDecoder,
// Authorization Server/test issuer và revocation store thực.
//
// String token = tokenFactory.issue("user-1", "api.read");
// assertThat(api.get("/api/me", token).status()).isEqualTo(200);
// revocationService.revokeByJti(tokenJti(token));
// eventuallyWithin(Duration.ofSeconds(2), () ->
//     assertThat(api.get("/api/me", token).status()).isEqualTo(401));
~~~

Nếu công ty **không có** `jti` denylist hay token version check, không viết test giả đòi JWT bị revoke ngay khi logout. Lúc đó chính sách nên dùng short-lived access token, refresh revocation và ghi nhận exposure window; hoặc thay thiết kế để đáp ứng SLA. Khi sản phẩm có requirement revoke tức thời, **đó là việc phải thiết kế và kiểm chứng, không phải thay một HTTP status trong test**.

## 10. Browser regression: đừng chỉ kiểm bằng MockMvc

Một app có thể pass session MockMvc nhưng fail trên browser:
- Cookie `SameSite=None` thiếu `Secure` bị từ chối.
- Nginx TLS termination nhưng ứng dụng tạo redirect sang HTTP do forwarded headers sai.
- Host-only cookie bị mở rộng Domain trong một commit mới.
- Cookie `HttpOnly` bị tắt để frontend đọc session, gây tăng rủi ro XSS.
- SPA dùng CSRF token cũ sau login/logout, POST tiếp theo 403.
- Browser nhiều tabs dùng chung cookie và logout tab A phải ảnh hưởng tab B của cùng session.
- IdP callback dùng top-level POST và SameSite policy chặn cookie correlation.
- DevTools/browser storage state chứa session cũ sau upgrade không còn deserialize được.

### 10.1. Playwright regression skeleton

Các tests dưới đây là **mảnh test có thể tích hợp** vào môi trường HTTPS staging đã được cấu hình, không phải source chạy độc lập của project MockMvc ở mục 5 vì project đó chỉ thiết kế lab HTTP session và chưa dựng Nginx/TLS container. Đặt `BASE_URL` trong CI tới HTTPS origin thật, browser phải xác minh certificate (không ignore errors).

~~~javascript
import { test, expect } from "@playwright/test";

const BASE = process.env.BASE_URL;

test("login cookie survives next request, logout revokes", async ({
  page, context
}) => {
  if (!BASE) throw new Error("BASE_URL is required");

  await page.goto(BASE + "/login");
  await page.locator('input[name="username"]').fill("student");
  await page.locator('input[name="password"]').fill(
    process.env.LAB_USER_PASSWORD);
  await page.locator('button[type="submit"]').click();

  await expect(page).toHaveURL(BASE + "/me");

  const cookie = (await context.cookies(BASE))
    .find(c => c.name === "JSESSIONID");
  expect(cookie).toBeDefined();
  expect(cookie.httpOnly).toBe(true);
  expect(cookie.secure).toBe(true);

  // Một request mới trong CÙNG browser context.
  await page.reload();
  await expect(page.locator("body")).toContainText("student");

  await page.goto(BASE + "/logout");
  await page.locator('form[action="/logout"] button').click();

  await page.goto(BASE + "/me");
  await expect(page).toHaveURL(/\/login/);
});
~~~

Để dùng skeleton trên, cần Playwright config/test runner, `BASE_URL`, test account và đúng login/logout page behavior. Trước khi dùng production, tuyệt đối không log password, không lưu session storage-state và không dùng `ignoreHTTPSErrors:true`. Browser test bổ sung MockMvc bằng **Cookie jar và TLS thật**, không dùng request API client để giả lập SameSite.

### 10.2. Hai browser contexts và logout một phiên

Nếu user có nhiều devices/sessions:
- Browser A login → session A.
- Browser B login → session B.
- Logout A **thường chỉ** kết thúc A, không nhất thiết B.
- Chức năng **logout-all-devices** mới phải revoke cả hai; test phụ thuộc product contract.
- Account disable/force revoke phải xử lý cả A/B theo SLA mà sản phẩm cam kết.
- Cookies chứa `Secure/HttpOnly/SameSite/Path/Domain` đúng; không dựa riêng vào `document.cookie` vì HttpOnly chặn JS đọc.

Không tạo test “logout A phải logout B” nếu sản phẩm chỉ cung cấp local logout, vì đó là kỳ vọng sai.

## 11. Multi-node/session store/rolling deployment

Trong một deployment nhiều pod:

~~~text
Login  -> load-balancer -> app-A -> ghi session S vào Redis
GET /me -> load-balancer -> app-B -> đọc session S từ Redis
Disable account -> service updates revocation state
GET /me -> load-balancer -> app-C -> phải deny theo SLA
Logout -> app-B invalidates S; app-A/app-C không được resurrect S
~~~

Bộ kiểm thử cần:
1. Buộc login và request tiếp theo đi qua **node khác** để xác nhận SecurityContext được deserialize/restore.
2. Ép session rotation sau login, xác nhận ID cũ không còn truy cập được.
3. Đổi release ở từng node trong rolling upgrade (mixed versions), xác định session serialization compatibility hoặc policy buộc relogin rõ ràng.
4. Thu hồi session qua node A, thử dùng cookie cũ ở node B/C; phải bị từ chối sau consistency window cam kết.
5. Đánh giá Redis/JDBC TTL, cache invalidation, persistence, session expiration event và store failover.
6. Khi revocation store mất kết nối, ứng dụng có fail-closed/timeout phù hợp thay vì âm thầm bypass.
7. Đồng thời login/logout/disable trong các threads/nodes; kiểm tra race không phục hồi quyền.
8. Test upgrade rồi rollback: bản cũ có đọc được session format mới không? Nếu không, cần kế hoạch drain/re-authentication an toàn.
9. Audit không ghi raw session ID/JWT/password/refresh token.

**Không gọi một unit test với `ConcurrentHashMap` là multi-node test.** Phải dùng ít nhất hai app instances với session/revocation store thực hoặc Testcontainers đủ thành phần mạng.

### 11.1. Thử chính xác quy tắc “revoked” trong trường hợp race

Cần định nghĩa **thời điểm committed** của lệnh thu hồi. Ví dụ:
- Nếu request bắt đầu **trước** khi revoke commit, việc có cho hoàn thành không tùy yêu cầu nghiệp vụ.
- Request bắt đầu **sau** commit phải bị chặn trong SLA (ngay hoặc sau cache TTL công bố).
- Không để một write request sau revoke thành công chỉ vì session đã tạo auth trước đó.
- Dùng transaction/token/session version, cache invalidation và audit với timestamp/ID đáng tin.
- Không dùng `Thread.sleep(5000)` làm bằng chứng revoke TTL nếu CI không ổn định; điều khiển `Clock` hoặc dùng polling bounded và ghi elapsed measured.

## 12. Các lỗi hồi quy thường gặp sau nâng cấp

| Triệu chứng | Root cause điển hình | Test bảo vệ |
| --- | --- | --- |
| Login thành công rồi /me 302 | Context không save với custom login | Login thật → request mới cùng session |
| /me luôn 200 trong tests | Test dùng `@WithMockUser`, không gọi login | Tách authentication integration test |
| Session ID không đổi | Session fixation strategy/filter mismatch | So pre/post ID |
| GET logout thực thi logout | CSRF disabled hoặc matcher GET | GET confirmation + session vẫn dùng được |
| POST logout không token vẫn 302 success | CSRF bị ignore không chủ đích | Negative CSRF test |
| Logout xong cookie cũ còn hiệu lực | Repository không clear/invalidate, proxy session cache | Reuse old cookie qua real HTTP client |
| Disable user nhưng session cũ vẫn đọc /me | Chỉ check UserDetails khi login, không có live revocation | Disable after login rồi retry old session |
| API dùng cookie được vào Bearer-only endpoint | Chain matcher/order sai | Token/cookie isolation tests |
| JWT wrong aud/iss vẫn được accept | Decoder validators bị mất do config | Issuer/audience negative tests |
| Expired JWT vẫn 200 | Clock/skew/cache validator regression | Fixed Clock + exp tests |
| Refresh cũ vẫn dùng được | Token family rotation/reuse detection lỗi | Concurrent refresh tests |
| Node A OK, node B unauthorized | Session store/serialization khác | Cross-node test |
| Candidate login fail chỉ trên browser | Cookie flags/forwarding/CSRF SPA changed | HTTPS Playwright E2E |
| Status 401 vs 403 sai | Entry point/denied handler đổi | Contract tests theo từng scheme |
| Session của hai users lẫn nhau | ThreadLocal/session leakage hoặc test reuse | Two-session isolation test |
| Admin endpoint public | Matcher `permitAll` rộng/chain priority | Forbidden anonymous + role tests |
| Remember-me tự login lại sau logout | RememberMeServices/cookie cleanup khác | Logout remember-me regression |
| Build xanh nhưng prod fail | Test libraries và runtime dùng BOM khác | dependencyInsight + artifact fingerprint |

## 13. Vì sao test không nên bám vào chi tiết implementation?

Một regression test có thể assert:
- HTTP status/redirect theo public API contract.
- Principal sau **request mới**.
- Session ID rotation, HttpOnly/Secure flags.
- Không có side effect sau 403/401.
- Old session/token không còn quyền sau revoke.
- Authorization/method/tenant isolation.

Không cần assert:
- Mọi filter phải đứng đúng một index nội bộ dù framework đổi implementation.
- `SecurityContextHolderFilter` luôn là loại duy nhất theo class name ở mọi release line, nếu chỉ là hành vi external.
- Hash password cụ thể phải giống byte-for-byte sau nâng encoder (salt/algorithm có thể thay; correctness là matches và migration).
- Snapshot đầy đủ HTML login page, csrf token hoặc random cookie ID.
- Thời gian response chính xác từng millisecond của CI.
- Nội dung stack trace/exception text vốn có thể thay mà không vi phạm contract.

Những chi tiết implementation có thể được kiểm trong một **architecture test** riêng nếu có lý do bảo mật rõ ràng, nhưng điều kiện cho phép rollout nên ưu tiên những bất biến quan trọng.

## 14. CI gate, báo cáo và chiến lược rollback

Pipeline gợi ý:

~~~text
Resolve dependencies + SBOM + advisory scan
   |
   v
Unit tests / password and account-state tests
   |
   v
Spring Security MockMvc regression tests
   |
   v
Build immutable candidate image
   |
   v
Deploy ephemeral HTTPS + proxy + session store
   |
   v
Browser E2E + cross-node/revocation cases
   |
   v
Compare baseline / candidate contract results
   |
   +-- FAIL: stop promotion, capture redacted evidence, investigate
   |
   +-- PASS: staged rollout/canary, monitor auth error and session metrics
   |
   v
Release / rollback plan with session compatibility verified
~~~

**Các gates bắt buộc thường là:** anonymous không vào protected endpoint, credential sai không login, context được khôi phục, session fixation, CSRF logout, logout revoke, revoked token/disabled sessions bị chặn theo contract và không có privilege escalation.

Sau rollout, có thể theo dõi:
- Tỷ lệ login success/failure theo nguyên nhân (không log password).
- Session creation/invalidations; abnormal relogin loops.
- 401/403/302 thay đổi theo route và user-agent.
- CSRF failures bất thường sau SPA/frontend deploy.
- Redis/JDBC session read/write failures, deserialization exceptions.
- JWT validation failures theo loại (issuer/audience/exp/scope) đã tổng hợp, không log raw token.
- Logout/revocation propagation latency theo SLO.

**Không auto rollback chỉ dựa trên một metric thô** nếu có thể gây logout toàn bộ user hoặc đưa bản có CVE quay lại. Phải đánh giá session format/downgrade, revocation store schema, token signing keys và thay đổi dữ liệu giữa baseline/candidate.

### 14.1. Format báo cáo hồi quy

~~~text
Suite: auth-upgrade-regression
Candidate: <release, digest, Boot/Security/Java versions>
Baseline: <release, digest>
Environment: <proxy/TLS, session store, browser, nodes>
Tests:
  LOGIN-01 anonymous denied: PASS/FAIL
  LOGIN-02 correct password: PASS/FAIL
  LOGIN-03 bad/disabled password: PASS/FAIL
  CONTEXT-01 persisted across requests: PASS/FAIL
  SESSION-01 fixation rotated: PASS/FAIL
  SESSION-02 two identities isolated: PASS/FAIL
  CSRF-01 unsafe POST without token denied: PASS/FAIL
  LOGOUT-01 GET no side effect: PASS/FAIL
  LOGOUT-02 POST invalidates session: PASS/FAIL
  REVOKE-01 disabled live session denied: PASS/FAIL
  TOKEN-01 expired/wrong audience/issuer denied: PASS/FAIL
  TOKEN-02 refresh family revocation: PASS/FAIL
  HA-01 cross-node session and revocation: PASS/FAIL
Regressions:
  - ID, expected, actual, severity, owner, link to redacted log
Decision:
  - promote / hold / rollback (approved)
~~~

Không lưu cookie/session token, raw Authorization headers, private keys, refresh token, CSRF token hoặc password trong CI artifact. Những trace E2E có thể chứa credential dù đó là test account; áp dụng redaction/quyền truy cập/retention.

## 15. Các bài tập suy luận sau nâng cấp

**Câu 1.** `POST /login` trả 302 và `authenticated()` pass, `GET /me` session cũ lại 302. Khả năng nào?  
**Đáp án:** Custom login code có thể chỉ set `SecurityContextHolder` mà không lưu bằng `SecurityContextRepository`; hoặc browser không gửi cookie, session store không đọc được. Tách bằng MockMvc session persistence và browser/proxy tests.

**Câu 2.** Test `.with(user("alice"))` cho `/me` pass. Đã đủ chứng minh login chưa?  
**Chưa.** Nó đặt principal giả cho request, không đi qua password authentication, session fixation, persistence.

**Câu 3.** Một account bị disable trong DB, session cũ vẫn đọc API được. Spring Security mặc định có lỗi không?  
**Không thể kết luận.** Session đã lưu Authentication; nếu product yêu cầu revoke live session, phải có revocation mechanism và test sau khi disable.

**Câu 4.** POST logout có CSRF, redirect `/login?logout`; browser vẫn đọc API bằng JWT cũ. Có nghĩa logout bị hỏng?  
**Không nhất thiết.** Logout local session không tự revoke access JWT independent; cần đối chiếu token revocation SLA/architecture.

**Câu 5.** JWT đúng chữ ký nhưng `aud` thuộc API khác. Có nên trả `403 insufficient_scope`?  
**Không.** Token không hợp lệ cho resource này nên phải từ chối authentication (thường 401).

**Câu 6.** Sau nâng, API session vẫn OK ở node A nhưng fail ở node B. Test thiếu gì?  
**Cross-node session store/serialization test**, gồm rolling upgrade, shared session data, TTL và persistence.

**Câu 7.** Logout ở tab A nên chấm dứt session của tab B?  
**Nếu cùng browser session cookie thì thường có.** Nhưng logout một thiết bị không mặc định logout mọi thiết bị; cần phân biệt cùng session và logout-all.

**Câu 8.** Login đúng nhưng request sau bị 403 ở POST. Có phải session không được lưu?  
**Không nhất thiết.** Có thể session auth đúng nhưng CSRF token sau login đã đổi hoặc thiếu; thử GET /me và kiểm tra token/session separately.

**Câu 9.** Test chỉ dùng `Thread.sleep(2000)` để chờ JWT hết hạn có đáng tin?  
**Không tốt.** Dùng inject `Clock`, kiểm tra `exp`/`nbf`/skew và bounded eventual assertion khi có hệ thống phân tán.

**Câu 10.** Có thể sửa regression bằng cách thay tất cả 401/403 thành 200 ở expected?  
**Không.** Đây có thể là privilege escalation; thay đổi contract bảo mật phải được xem xét, không “nới” test để pass.

## 16. Checklist trước khi chấp nhận nâng cấp

- [ ] Chạy cùng auth regression suite trên baseline/candidate; lưu phiên bản và artifact digest.
- [ ] Test login thực bằng provider, không chỉ `@WithMockUser`.
- [ ] Anonymous/credential sai/account disabled đều bị từ chối.
- [ ] User login thành công được khôi phục ở request **mới** cùng session.
- [ ] Session A và B không lẫn principal; role/tenant checks vẫn đúng.
- [ ] Session ID được thay sau login, không cho fixation.
- [ ] CSRF enabled cho unsafe browser-session requests, gồm login/logout.
- [ ] GET logout không thay đổi trạng thái; POST logout có CSRF invalidate session.
- [ ] Browser sử dụng cookie thật qua HTTPS; Secure/HttpOnly/SameSite/Path/Domain đúng policy.
- [ ] Account disable/force revoke chặn session đang mở đúng SLA của sản phẩm.
- [ ] JWT/opaque/refresh token có test revocation riêng, không phụ thuộc local logout.
- [ ] Issuer/audience/expiry/scope, clock skew và token replay đều được kiểm tra.
- [ ] Multi-node/shared session/rolling deploy/rollback phù hợp session serialization.
- [ ] Không có filter chain matcher mở nhầm protected routes.
- [ ] Tests không rò password, session/cookie, CSRF token, access/refresh token, private key.
- [ ] Có CI gate/owner/canary metrics và kế hoạch rollback an toàn.

## 17. Nguồn học tập

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextRepository`, explicit save, session fixation, concurrent sessions.
- [Spring Security 6.5 — Session Management Migration](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): thay đổi persistence giữa các release.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): UsernamePasswordAuthenticationFilter, login redirect và failure.
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): session/context invalidation, GET confirmation, POST logout.
- [Spring Security — MockMvc Form Login Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html): `formLogin()` gửi CSRF token đúng.
- [Spring Security — MockMvc Logout Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html): logout request postprocessor.
- [Spring Security — MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html): `authenticated()`, `unauthenticated()`.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): springSecurity() và filter chain.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): signature/issuer/exp/nbf và custom validation.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie, session fixation, invalidation, timeout.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): credential validation, generic errors, throttling.
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): authorization/token security recommendations.

**Kết luận:** Regression sau nâng Spring Security **không phải một bài test login trả 302**. Bộ test phải chứng minh một chuỗi đầy đủ: **anonymous bị chặn → login đúng → context tồn tại ở request khác → user/role đúng và tách biệt → session được luân chuyển → logout hoặc revoke khiến quyền thực sự hết hiệu lực**. Phải tách session revocation với OAuth access/refresh token và chạy cùng contract trên baseline/candidate. Một suite chỉ dùng mock principal sẽ không phát hiện được các lỗi persistence và thu hồi truy cập nguy hiểm nhất.