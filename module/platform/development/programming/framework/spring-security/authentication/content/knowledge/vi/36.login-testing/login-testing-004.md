# Kiểm thử đăng nhập đúng, sai mật khẩu, tài khoản bị khóa và tài khoản bị vô hiệu hóa

> **Chủ đề:** Kiểm thử luồng xác thực username/password trong Spring Security, từ `AuthenticationProvider` đến filter, phản hồi HTTP và phiên đăng nhập. Bốn tình huống trọng tâm là **đăng nhập hợp lệ**, **mật khẩu sai**, **account bị khóa** và **account bị vô hiệu hóa**. Bài hướng tới Java 17+, Spring Boot 3.x và Spring Security 6.x Servlet; ngoài ma trận trạng thái còn kiểm tra CSRF, chống lộ thông tin tài khoản, session, sự kiện bảo mật và lỗi hạ tầng. Các tài khoản/mật khẩu dưới đây là **dữ liệu test**, không được dùng trong production.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt xác thực thành công (`Authentication.isAuthenticated()`) với phản hồi HTTP 200/302, quyền truy cập tài nguyên và việc lưu `SecurityContext` trong phiên.
2. Dựng fixture `UserDetails` cho bốn tình huống: enabled + password đúng, enabled + password sai, `isAccountNonLocked() == false`, `isEnabled() == false`.
3. Kiểm thử đúng hai lớp: **provider-level** cho kết quả/exception nội bộ, **HTTP-level** qua Spring Security filter chain cho response và session thực.
4. Sử dụng `spring-security-test`, `MockMvc`, `formLogin()`, `authenticated()`, `unauthenticated()`, CSRF token và request nối tiếp trong cùng session.
5. Hiểu `BadCredentialsException`, `LockedException`, `DisabledException`; lý do nội bộ có thể khác nhau nhưng public login cần tránh username/account-state enumeration.
6. Kiểm tra ranh giới khóa tạm, disabled dài hạn, tài khoản không tồn tại, sai OTP/MFA, session cũ, brute-force và lỗi repository để bài test không cho một đường bypass.
7. Viết bài kiểm thử đáng tin: fixture cô lập, password được mã hóa, không chỉ giả user đã đăng nhập, assertion có ý nghĩa và không khẳng định response của mọi ứng dụng Spring giống nhau.

## 2. Mô hình xác thực thật trong Spring Security

Với **form login mặc định**, luồng có thể hình dung:

~~~text
Browser POST /login (username, password, CSRF)
   |
   v
Spring Security FilterChain
   |
   +-- CsrfFilter: kiểm tra CSRF cho POST
   |
   +-- UsernamePasswordAuthenticationFilter
             |
             +-- UsernamePasswordAuthenticationToken chưa authenticated
             |
             v
       AuthenticationManager (thường ProviderManager)
             |
             v
       DaoAuthenticationProvider
             |
             +-- UserDetailsService.loadUserByUsername(...)
             +-- UserDetails trạng thái account
             +-- PasswordEncoder.matches(raw, encoded)
             +-- kiểm tra credential expiry / chính sách liên quan
             |
             +-- SUCCESS: Authentication đã authenticated
             +-- FAILURE: AuthenticationException
   |
   +-- Thành công: session strategy / SecurityContext / success handler
   +-- Thất bại: xóa context thất bại / failure handler / response chung
~~~

`DaoAuthenticationProvider` làm việc với `UserDetailsService` và `PasswordEncoder`. `UsernamePasswordAuthenticationFilter` là một phần của form-login Servlet chain; nếu sử dụng HTTP Basic, JSON login custom, OAuth2 Login, SAML hoặc WebFlux thì luồng và HTTP status khác. **Không dùng test formLogin để chứng minh một API stateless dùng JWT đã hoạt động đúng.**

Lưu ý về thứ tự các kiểm tra nội bộ: với `AbstractUserDetailsAuthenticationProvider` có **pre-authentication checks** cho trạng thái tài khoản, password checks và **post-authentication checks** cho thông tin xác thực hết hạn. Các bản vá Spring Security có thể điều chỉnh cách thực thi các kiểm tra để giảm timing enumeration. Bởi vậy cần test từng trạng thái với **mật khẩu đúng đã biết**, không dựa trên kỳ vọng tùy tiện về exception khi **vừa khóa vừa sai mật khẩu**, và không dùng timing của một bản cũ như một hợp đồng ổn định.

## 3. Định nghĩa đúng bốn kịch bản chính

| Kịch bản | User tồn tại? | Password | Account locked? | Enabled? | Kết quả mong đợi |
| --- | --- | --- | --- | --- | --- |
| A — đăng nhập đúng | Có | Đúng | Không | Có | Provider cấp Authentication đã xác thực; form login vào success flow |
| B — sai mật khẩu | Có | Sai | Không | Có | `BadCredentialsException` ở provider thông thường; không tạo authenticated session |
| C — tài khoản khóa | Có | Đúng để cô lập biến trạng thái | Có | Có | Không được xác thực; thường `LockedException` trong đường provider chuẩn |
| D — tài khoản vô hiệu hóa | Có | Đúng để cô lập biến trạng thái | Không | Không | Không được xác thực; thường `DisabledException` |
| E — user không tồn tại | Không | Bất kỳ | N/A | N/A | Không xác thực, public response không xác nhận user tồn tại |
| F — account expired | Có | Đúng | Không | Có nhưng account hết hạn | Không được xác thực; khác disabled |
| G — credentials expired | Có | Đúng | Không | Có | Không được xác thực hoặc đi vào password-update flow riêng theo policy |
| H — lỗi DB/LDAP/IdP | Chưa xác minh | Chưa xác minh | Không biết | Không biết | Hạ tầng lỗi, không đếm như sai password và không fail open |

Trong bốn trường hợp A–D, **nên dùng cùng một mật khẩu đúng** cho các fixture khác nhau, ví dụ `test-password-123!`, rồi chỉ thay *một* điều kiện mỗi test. Như vậy nếu C/D thất bại, có thể quy nguyên nhân cho trạng thái account, không phải cho một secret sai vô tình. Các giá trị này chỉ tồn tại trong test scope và phải **được mã hóa bởi `PasswordEncoder`** khi đưa vào store.

**Không nhầm “account locked” với “tài khoản bị disabled”:** `isAccountNonLocked=false` thường diễn đạt trạng thái khóa, có thể tạm thời nếu ứng dụng tính theo `lockedUntil`. `isEnabled=false` diễn đạt trạng thái bị vô hiệu hóa bởi quyết định nghiệp vụ/quản trị. Hết thời gian khóa tạm không tự khiến disabled account hoạt động trở lại.

## 4. Bốn cờ quan trọng của UserDetails

Spring Security `UserDetails` có các tín hiệu riêng:

| Phương thức | true có nghĩa | false có thể dẫn tới |
| --- | --- | --- |
| `isEnabled()` | User đang enabled | `DisabledException` |
| `isAccountNonLocked()` | Account **không** bị khóa | `LockedException` |
| `isAccountNonExpired()` | Account chưa hết hạn | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credential (mật khẩu/chứng cứ) chưa hết hạn | `CredentialsExpiredException` |

Đây là **điều kiện kiểm tra cho lần xác thực**, không phải các cột bắt buộc trong một bảng DB. Một `UserDetailsService` có thể tính `isAccountNonLocked()` từ `lockedUntil` và giờ server, hoặc ánh xạ từ cờ lock riêng. Nhưng nếu dùng `InMemoryUserDetailsManager` fixture, bạn có thể thiết lập trực tiếp `User.withUsername(...).accountLocked(true).disabled(true)` và giữ độc lập từng trạng thái.

**Một điểm thường gây lỗi test:** `UserDetails.isAccountNonLocked()` không phải getter `isLocked()`. Giá trị false là **đang khóa**. Tương tự `disabled(true)` trong builder dẫn tới `isEnabled() == false`. Đảo ngược logic khiến test báo thành công cho account đáng lẽ phải bị từ chối.

### Trạng thái HTTP/session không đồng nghĩa trạng thái UserDetails

- **HTTP 302** có thể là login thành công chuyển đến URL đích hoặc login thất bại chuyển tới `/login?error`. Đừng chỉ assert `status().is3xxRedirection()`.
- **HTTP 401** thường gặp ở Basic/Bearer API không xác thực. Browser form-login thất bại mặc định **không nhất thiết trả 401**, có thể redirect.
- **HTTP 403** thường là đã xác thực nhưng thiếu quyền, hoặc POST bị chặn bởi CSRF; không tự hiểu là “password sai”.
- **UserDetails disabled/locked** được kiểm tra khi xác thực mới; trạng thái này **không tự động hủy mọi HttpSession đã tồn tại** nếu ứng dụng chưa thiết kế session revocation hoặc per-request account-state checking.
- **`SecurityContextHolder`** chứa xác thực ở ngữ cảnh hiện tại, còn việc persist qua request phụ thuộc `SecurityContextRepository`/session strategy.

## 5. Thiết kế test ở ba mức

| Mức kiểm thử | Mục tiêu | Công cụ |
| --- | --- | --- |
| **Unit test policy thuần** | Tính `lockedUntil`, disabled flag, reset/counter, boundary clock | Java/JUnit, `Clock.fixed` |
| **Authentication provider test** | UserDetails lookup, PasswordEncoder và loại exception cho từng account | `DaoAuthenticationProvider` thật hoặc `AuthenticationManager` đã cấu hình |
| **HTTP integration test** | CSRF, filter chain, POST form, redirect, security context, cookie/session, protected route | `@SpringBootTest`, `@AutoConfigureMockMvc`, `spring-security-test` |

Không nên dùng `@WithMockUser` hay `get("/private").with(user("alice"))` để chứng minh **mật khẩu được kiểm tra**. Hai helper này gắn sẵn principal vào test request, thường **bỏ qua chính `DaoAuthenticationProvider`** mà bạn đang cần thử. Chúng hữu ích để test authorization sau khi đã xác thực, nhưng không thay cho `formLogin()` hoặc gọi AuthenticationManager thật.

**Khuyến nghị cấu trúc bộ test:** Với mỗi case, mô tả rõ preconditions (fixture state), request/credential, kết quả Authentication nội bộ, public HTTP response, session/context và audit/counter nếu có. Test chỉ pass khi cả kết quả **tích cực** (đúng account vào được route) và kết quả **tiêu cực** (wrong/locked/disabled không vào được route) đều được xác minh.

## 6. Dependencies và cấu trúc project ví dụ

Nếu dùng Maven trong Spring Boot 3.x, test integration thường cần `spring-boot-starter-security`, `spring-boot-starter-web`, `spring-boot-starter-test` và **`spring-security-test`** trong test scope. Spring Boot BOM nên quản lý phiên bản các thư viện Spring để tránh lệch API.

Đoạn `pom.xml` dưới đây là **khối dependencies** trong một project Boot đã có parent/BOM và Java 17, không phải file Maven hoàn chỉnh:

~~~xml
<dependencies>
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
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ví dụ project có các file:

~~~text
src/main/java/example/login/
    LoginTestingApplication.java
    LoginTestSecurityConfig.java
    PrivateController.java
src/test/java/example/login/
    LoginScenariosTest.java
~~~

Các lớp dưới nằm cùng package `example.login`. Đây là **fixture demo dùng InMemoryUserDetailsManager**, không phải thiết kế tài khoản production. Khi đưa vào dự án thực tế, thay users in-memory bằng repository/adapter đúng, bổ sung MFA, account policy, rate limit và kiểm tra session đang sống.

## 7. Ứng dụng Spring Boot nhỏ để kiểm thử HTTP thật

Tệp `LoginTestingApplication.java`:

~~~java
package example.login;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginTestingApplication.class, args);
    }
}
~~~

Tệp `LoginTestSecurityConfig.java`:

~~~java
package example.login;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LoginTestSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService testUsers(PasswordEncoder encoder) {
        UserDetails active = User.withUsername("active")
                .password(encoder.encode("test-password-123!"))
                .roles("USER")
                .build();

        UserDetails locked = User.withUsername("locked")
                .password(encoder.encode("test-password-123!"))
                .roles("USER")
                .accountLocked(true)
                .build();

        UserDetails disabled = User.withUsername("disabled")
                .password(encoder.encode("test-password-123!"))
                .roles("USER")
                .disabled(true)
                .build();

        return new InMemoryUserDetailsManager(active, locked, disabled);
    }

    @Bean
    DaoAuthenticationProvider daoProvider(UserDetailsService testUsers,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(testUsers);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
            DaoAuthenticationProvider daoProvider) throws Exception {
        return http
                .authenticationProvider(daoProvider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .defaultSuccessUrl("/private", true)
                        .failureUrl("/login?error"))
                .build();
    }
}
~~~

**Vì sao cấu hình như vậy?**

- Ba users có cùng password test đã được **BCrypt encode**, cho phép cô lập trạng thái locked/disabled. Trong tài khoản thực, không hardcode password hoặc secrets như thế.
- `active`: mặc định enabled/non-locked/non-expired.
- `locked`: builder `accountLocked(true)` làm `isAccountNonLocked()` trả false.
- `disabled`: builder `disabled(true)` làm `isEnabled()` trả false.
- `DaoAuthenticationProvider` được đăng ký rõ với `SecurityFilterChain`; ứng dụng thực tế phải kiểm tra không có **provider khác** xử lý username/password mà bypass policy.
- `defaultSuccessUrl("/private", true)` làm redirect thành công **cố định** để test deterministic; `failureUrl("/login?error")` dùng response chung, không làm lộ account locked/disabled trên public URL.
- **CSRF giữ mặc định**. Không tắt CSRF chỉ để test form login pass. Helper `formLogin()` của `spring-security-test` tự thêm một CSRF token hợp lệ trong test.
- Bản demo dùng default login page của Spring Security vì chưa chỉ định `loginPage(...)`; không cần tự viết HTML. Trong production, login page custom thường có message chung, rate limiting, CSRF và UX phù hợp.

Tệp `PrivateController.java`:

~~~java
package example.login;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrivateController {
    @GetMapping("/private")
    public String privatePage(Principal principal) {
        return "private:" + principal.getName();
    }
}
~~~

`/private` dùng chính identity đã xác thực từ `Principal`. Test truy cập nó sau login giúp kiểm tra **session continuity**, không chỉ kết quả POST `/login`.

## 8. MockMvc: kiểm thử bốn trạng thái thực sự đi qua filter chain

Tệp `LoginScenariosTest.java` trong `src/test/java/example/login/`:

~~~java
package example.login;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginScenariosTest {

    @Autowired
    MockMvc mvc;

    @Test
    void correctPasswordCreatesAuthenticatedSession() throws Exception {
        MvcResult result = mvc.perform(formLogin()
                        .user("active")
                        .password("test-password-123!"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/private"))
                .andExpect(authenticated().withUsername("active"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/private").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("private:active"));
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(formLogin()
                        .user("active")
                        .password("wrong-password"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void lockedAccountDoesNotAuthenticate() throws Exception {
        mvc.perform(formLogin()
                        .user("locked")
                        .password("test-password-123!"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void disabledAccountDoesNotAuthenticate() throws Exception {
        mvc.perform(formLogin()
                        .user("disabled")
                        .password("test-password-123!"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void unknownUserHasSamePublicFailureDestination()
            throws Exception {
        mvc.perform(formLogin()
                        .user("not-present")
                        .password("test-password-123!"))
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void protectedPageWithoutLoginRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }
}
~~~

### Điều mà các test trên thực sự chứng minh

- `formLogin()` gửi **POST đúng endpoint login** với username/password và CSRF token hợp lệ, khác với giả lập một `@WithMockUser`.
- Test đúng kiểm tra **redirect đến /private**, `authenticated()` gắn đúng username, sau đó **GET /private dùng session từ login** trả nội dung tương ứng. Đây là bằng chứng end-to-end trong MockMvc rằng context đã được giữ cho request tiếp theo.
- Ba test sai/locked/disabled đều kiểm tra public failure URL như nhau và `unauthenticated()`. Điều này cố ý không cho client suy ra account nào bị khóa chỉ từ URL.
- Test unknown user giúp bảo đảm ít nhất **cùng đích redirect** với wrong/locked/disabled; kiểm thử timing, response length, cookie và side-channel cần bài riêng.
- Test không tuyên bố session **không hề tồn tại** ở các case thất bại, vì CSRF/request cache có thể tạo một HttpSession không chứa authenticated principal. Điều cần assert là **không có security context xác thực** cho protected route.

**Lưu ý version API:** Đây là mã tích hợp trong project Spring Boot 3.x + Spring Security 6.x đã cấu hình đúng như phần trước. `formLogin()` và result matchers đến từ `spring-security-test`. Nếu dependency của dự án thuộc version khác, phải căn chỉnh BOM và import; đừng copy nguyên một method thuộc Spring Security 7 vào 6.x.

## 9. Kiểm tra exception nội bộ bằng DaoAuthenticationProvider

HTTP form login đã cố ý đưa **failure response chung**. Để phân biệt nguyên nhân trong unit/integration test của provider, gọi provider thật với token chưa xác thực và assert loại exception — **đây là assertion cho kênh server nội bộ, không phải nội dung trả cho browser**.

Có thể bổ sung vào cùng `LoginScenariosTest.java` (bên trong class `LoginScenariosTest`, thêm imports tương ứng):

~~~java
@Autowired
org.springframework.security.authentication.dao.DaoAuthenticationProvider
        provider;

@Test
void activeWithWrongPasswordRaisesBadCredentials() {
    org.assertj.core.api.Assertions.assertThatThrownBy(() ->
            provider.authenticate(
                    org.springframework.security.authentication
                            .UsernamePasswordAuthenticationToken
                            .unauthenticated("active", "wrong-password")))
            .isInstanceOf(
                    org.springframework.security.authentication
                            .BadCredentialsException.class);
}

@Test
void lockedWithCorrectPasswordRaisesLocked() {
    org.assertj.core.api.Assertions.assertThatThrownBy(() ->
            provider.authenticate(
                    org.springframework.security.authentication
                            .UsernamePasswordAuthenticationToken
                            .unauthenticated("locked", "test-password-123!")))
            .isInstanceOf(
                    org.springframework.security.authentication
                            .LockedException.class);
}

@Test
void disabledWithCorrectPasswordRaisesDisabled() {
    org.assertj.core.api.Assertions.assertThatThrownBy(() ->
            provider.authenticate(
                    org.springframework.security.authentication
                            .UsernamePasswordAuthenticationToken
                            .unauthenticated("disabled", "test-password-123!")))
            .isInstanceOf(
                    org.springframework.security.authentication
                            .DisabledException.class);
}
~~~

**Ranh giới:** Kỳ vọng trên dành cho `DaoAuthenticationProvider` chuẩn của fixture, khi mỗi account chỉ có **một trạng thái lỗi** và password đúng cho case locked/disabled. Nếu bạn viết custom `AuthenticationProvider`, provider chain hoặc user lookup, loại exception có thể thay đổi. Đặc biệt không dùng exception precedence của một account **vừa disabled vừa locked** làm business contract nếu không được quy định riêng. Hãy test trạng thái công khai vẫn từ chối trước, sau đó test mapping nội bộ theo implementation được phép.

### Vì sao không thể chỉ assert `status().isUnauthorized()`?

Trong flow `formLogin` đã cấu hình, **401 không phải phản hồi dự kiến cho wrong-password**. Failure handler dùng redirect `/login?error`, nên 302 + unauthenticated mới là assertion đúng. Trong một JSON API riêng, 401 có thể đúng; test phải tuân theo **giao thức của endpoint** chứ không coi HTTP code của form login và Basic/Bearer là tương đương.

## 10. Ví dụ Java 17 chạy độc lập: mô phỏng quyết định trạng thái

Ví dụ sau **không phải Spring Security implementation**; nó tách riêng bài toán quyết định bốn trạng thái, dùng `Instant` cố định và một boolean `passwordMatches` đại diện cho kết quả xác minh mật khẩu đã có từ một component đáng tin. Không hardcode, so sánh hoặc lưu plaintext password trong chương trình, nên không vô tình dạy dùng `equals` cho password trong production.

Tệp `LoginStateDemo.java`:

~~~java
import java.time.Instant;

public final class LoginStateDemo {
    enum Verdict {
        AUTHENTICATED, BAD_CREDENTIALS, LOCKED, DISABLED
    }

    record Account(boolean enabled, Instant lockedUntil) {}

    static Verdict evaluate(Account account,
            boolean passwordMatches, Instant now) {
        if (account == null) {
            return Verdict.BAD_CREDENTIALS;
        }
        if (!account.enabled()) {
            return Verdict.DISABLED;
        }
        if (now.isBefore(account.lockedUntil())) {
            return Verdict.LOCKED;
        }
        return passwordMatches
                ? Verdict.AUTHENTICATED
                : Verdict.BAD_CREDENTIALS;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");
        Account active = new Account(true, Instant.EPOCH);
        Account locked = new Account(true, now.plusSeconds(60));
        Account disabled = new Account(false, Instant.EPOCH);

        System.out.println("correct: " +
                evaluate(active, true, now));
        System.out.println("wrong password: " +
                evaluate(active, false, now));
        System.out.println("locked: " +
                evaluate(locked, true, now));
        System.out.println("disabled: " +
                evaluate(disabled, true, now));
        System.out.println("locked at deadline: " +
                evaluate(locked, true, now.plusSeconds(60)));
        System.out.println("unknown account: " +
                evaluate(null, false, now));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac LoginStateDemo.java
java LoginStateDemo
~~~

Stdout chính xác:

~~~text
correct: AUTHENTICATED
wrong password: BAD_CREDENTIALS
locked: LOCKED
disabled: DISABLED
locked at deadline: AUTHENTICATED
unknown account: BAD_CREDENTIALS
~~~

**Hiểu đúng ví dụ:** `Account(enabled, lockedUntil)` chỉ là mô hình **để học state/clock**. `passwordMatches` đã là kết quả từ một password verifier tin cậy; chương trình không làm password hashing, account lookup, HTTP session, MFA hay đăng nhập thật. Chính sách demo kiểm tra disabled trước locked, nhưng không mô tả thứ tự nội bộ bắt buộc của Spring Security ở mọi phiên bản. Trong ứng dụng thật, dùng `PasswordEncoder.matches`, `UserDetailsService`, provider và policy riêng.

Mốc `now == lockedUntil` cho phép thử đăng nhập lại trong mô hình khóa tạm. Nó không tự mở account có `isEnabled=false`, không reset trường disabled và không thể thay thế giới hạn retry theo account/IP.

## 11. Bảo đảm CSRF: test không được tắt bảo vệ để “cho pass”

Form login sử dụng cookie-based session và thực hiện POST có tác động tới authentication state. Spring Security mặc định bảo vệ CSRF cho POST; helper `formLogin()` tạo CSRF token hợp lệ. Nếu code test lại dùng `post("/login").param("username",... )` mà không truyền CSRF, bạn có thể nhận **403** trước khi Spring kiểm tra password.

Test phân biệt:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void loginWithoutCsrfIsForbidden() throws Exception {
    mvc.perform(post("/login")
                    .param("username", "active")
                    .param("password", "test-password-123!"))
            .andExpect(status().isForbidden());
}
~~~

Đoạn này là **một method bổ sung bên trong test class đã có field mvc**, không phải file chạy độc lập. Nó chỉ đúng với chain giữ CSRF như fixture ở trên. Nếu framework/test setup có tùy biến CSRF repository, token behavior phải theo contract thực tế.

**Bẫy thường gặp:** Developer thấy 403 rồi kết luận “mật khẩu đúng không vào được” và sửa test bằng cách `csrf.disable()` trong production. Cách sửa đúng là gửi CSRF hợp lệ trong flow dựa vào cookie. Với JSON API chỉ dùng Bearer token, CSRF threat model khác, nhưng không tắt một cách tùy tiện trên các endpoint browser.

## 12. Session continuity và hệ quả của trạng thái account

Một test login đúng chỉ POST rồi thấy 302 vẫn chưa chứng minh request sau có quyền. Phải dùng session/cookie được phát sau login để gọi một protected endpoint và xác nhận `principal.getName()` hoặc authorities đúng.

Ngược lại, **wrong-password, locked, disabled** không được nâng một phiên anonymous thành authenticated. Cần kiểm tra:

- Response redirect chung không chứng minh login success.
- `SecurityContext` của request thất bại không có principal đã xác thực.
- Session tạo do CSRF hoặc request cache (nếu có) **không được hiểu là session đăng nhập**.
- Browser gửi lại cookie cũ của một **phiên đã authenticated trước đó** là tình huống khác: form-login failure không tự đảm bảo policy thu hồi mọi session cũ của user.
- Kiểm tra session fixation protection: sau login thành công, session ID có thể được đổi (`changeSessionId()`); test không hardcode raw ID.
- Logout dùng đúng HTTP method/CSRF theo cấu hình, session bị invalidated và request mới không mang authentication cũ.
- Các policy concurrency (`maximumSessions`), logout all devices và account disable phải test với session registry/shared store; thay `isEnabled` trong DB **không mặc nhiên** tiêu hủy các phiên đã phát trước đó.

**Ví dụ chính sách khi disabled account:** nếu doanh nghiệp muốn cấm ngay cả phiên đang mở, cần bổ sung session revocation/token invalidation hoặc một tầng authorization/status check trên request được bảo vệ. Test như vậy không thể chỉ gọi `provider.authenticate(...)`, vì provider thường chỉ chạy khi đăng nhập mới.

### Tình huống session đã tồn tại trước khi account bị khóa

Khi account bị khóa do password guessing từ bên ngoài, bạn có muốn hủy session hợp lệ đang dùng hay không? Đó là một quyết định rủi ro: hủy mọi session có thể biến bộ đếm password sai thành công cụ DoS. Phân biệt **temporary login throttle** và **compromise-driven security disablement**; test từng hành vi theo policy, không suy diễn rằng locked và disabled đều có cùng hiệu ứng tới phiên cũ.

## 13. Kiểm thử thông điệp lỗi chung và chống username enumeration

Về mặt backend, `BadCredentialsException`, `LockedException` và `DisabledException` mang ý nghĩa nội bộ khác nhau. Nhưng public login không nên phơi bày thông tin có thể giúp attacker xác nhận username có tồn tại hoặc account đã bị khóa.

**Ma trận kết quả hiển thị gợi ý cho form login:**

| Input | Public redirect | Public message | Internal audit category |
| --- | --- | --- | --- |
| Active + password sai | `/login?error` | “Không thể đăng nhập” | BAD_CREDENTIALS |
| User không tồn tại | `/login?error` | “Không thể đăng nhập” | UNKNOWN_ACCOUNT (hạn chế quyền xem) |
| Locked + password đúng | `/login?error` | “Không thể đăng nhập” | LOCKED |
| Disabled + password đúng | `/login?error` | “Không thể đăng nhập” | DISABLED |
| DB auth store unavailable | Error boundary theo policy | “Dịch vụ tạm thời không sẵn sàng” | INFRA_ERROR |

**Không nhất thiết xử lý outage hạ tầng cùng status như sai password**: nếu không đọc được DB/LDAP, phải fail closed và có giám sát lỗi hệ thống, không cộng thêm bad-password count cho user. Nhưng public reason cho account unknown/locked/disabled không nên chứa username, số lần thử còn lại hoặc thời điểm mở khóa mà người chưa xác thực có thể khai thác.

### Timing side channel và bản vá 2026

Ngay cả khi URL/body giống nhau, đường xử lý khác biệt có thể làm thời gian phản hồi phân biệt user active/disabled/locked. Spring công bố **CVE-2026-22746** ngày 20/04/2026 về **user attribute enumeration thông qua timing** khi `DaoAuthenticationProvider` được cấu hình sử dụng `isEnabled`/`isAccountNonExpired`/`isAccountNonLocked`. Các nhánh OSS tương ứng được khắc phục trong **Spring Security 6.5.10 và 7.0.5**; cần cập nhật bản vá mới nhất của nhánh đang vận hành thay vì chỉ dựa vào generic message.

Kiểm thử timing có nhiều nhiễu (JIT, cache, scheduler, network, password encoder); không nên viết unit test assert `responseTimeA == responseTimeB`. Dùng security review, benchmark thống kê hợp lý và kiểm tra nhánh mã thực thi; không cố chữa bằng `Thread.sleep` trong request thread vì sẽ tự tạo rủi ro resource-exhaustion DoS.

Đừng đưa full username/email vào log metric cardinality cao. Internal audit có thể cần category rõ theo RBAC/retention, nhưng không ghi password, session cookie, OTP hay exception message chứa secrets.

## 14. Account locked và disabled: kiểm thử cơ chế khác nhau

“Locked” có hai ý nghĩa thường bị trộn:

1. **Khóa tạm do sai mật khẩu:** `lockedUntil`, số lỗi trong cửa sổ, có thể tự hết hạn và giảm tác động sau retry đúng.
2. **Khóa an ninh/quản trị:** diễn đạt cần điều tra/khôi phục bằng quy trình riêng; không tự mở vì đồng hồ qua.
3. **Disabled:** tài khoản bị vô hiệu theo chính sách hay tổ chức; không tự hết theo timer và thường không được phép tạo session mới.

Fixture `User.accountLocked(true)` minh họa trạng thái tại thời điểm test, **không có đồng hồ** và không tự mở sau 60 giây. Muốn test hết khóa, phải có `UserDetailsService` tính `isAccountNonLocked` từ `lockedUntil` cộng `Clock` được inject, rồi test đúng boundary. Đừng viết test `Thread.sleep(60_000)` vừa chậm vừa không deterministic.

Cần test riêng trường hợp admin disabled trong lúc còn login attempt đang chạy: một success hoặc reset bad-password counter không được ghi lại trạng thái ACTIVE từ snapshot cũ và mở account trái phép. Dùng transaction/optimistic locking để cập nhật đúng cột counter, không overwrite toàn bộ row account.

### Những trường hợp kết hợp khó

- **Locked + disabled:** Kết quả public phải từ chối; loại exception nội bộ có thể phụ thuộc thứ tự checks, phiên bản và chính sách. Không assert ưu tiên nếu contract không quy định.
- **Wrong password + locked:** Kết quả public phải từ chối, không bắt buộc dùng một loại exception nhất định trên mọi phiên bản Spring đã vá.
- **Unknown username + disabled** không có nghĩa; unknown chỉ là unverified input, không nên tạo account state thật từ request.
- **Disabled nhưng còn phiên authenticated từ trước:** sẽ còn quyền nếu không có session/status policy bổ sung; test yêu cầu revoke nếu sản phẩm cam kết.
- **Remember-me/SSO login:** có thể không nhập password mới; cần kiểm tra mechanism này vẫn tôn trọng trạng thái disabled và MFA requirement theo hợp đồng.
- **Account locked tạm do attacker:** đừng mặc nhiên xóa mọi session của nạn nhân đang hoạt động, vì chính điều đó có thể giúp attacker gây DoS.

## 15. Lỗi hạ tầng, kiểm soát thử sai và audit

Một hệ thống test tốt phải phân biệt **authentication denied** với **unable to authenticate**.

| Nguyên nhân | Test phải ghi nhận | Không được làm |
| --- | --- | --- |
| `BadCredentialsException` | Một lần nhập password không hợp lệ | Tính hai lần ở provider và failure handler |
| `LockedException` | Account không được phép thử tại lúc đó | Gọi là “sai password” hoặc tăng bad-password counter |
| `DisabledException` | Policy cấm đăng nhập | Tự mở trong handler khi người dùng báo có password đúng |
| `UsernameNotFoundException` | Không có account đã xác minh | Trả thông tin xác nhận user tồn tại |
| DB timeout/LDAP outage | Infrastructure failure, fail closed | Tạo authenticated principal tạm hoặc đếm lỗi user |
| MFA OTP sai | Lỗi factor thứ hai riêng | Xóa hoặc thay thế password audit tùy ý |
| Session store outage | Không đảm bảo persisting login | Báo login completed khi chưa có session |
| CSRF thiếu hoặc sai | 403 trước password auth | Đếm là wrong password và khóa account |
| Rate limiter chặn trước auth | 429/challenge theo policy | Cho request vào password encoder rồi mới giới hạn |

### Audit với event categories rõ ràng

Ghi thành công/failure với `attempt_id`, server timestamp UTC, user ref an toàn, method, category và correlation ID. Không log raw password, Authorization, Cookie, OTP, CSRF token, credential hash hoặc session ID. Với `AuthenticationFailureHandler` và `AuthenticationEventPublisher`, phân biệt **provider-level failure** và **HTTP login failure** để không nhân đôi số lần thử trong metrics/audit.

Nên kiểm thử event emission: mỗi lần password sai làm tăng counter một lần trong source-of-truth; account locked/disabled không bị tính như bad-password; event sau cùng phản ánh đúng trạng thái. Khi dùng Spring Security test fixture, làm sạch counter/rate limit giữa tests để một test không làm test khác bị khóa bất ngờ.

## 16. Test bằng REST JSON, Basic và Bearer khác form login thế nào?

| Cơ chế | Input | Response thất bại có thể có | Test đúng |
| --- | --- | --- | --- |
| Browser form login | `POST /login` + CSRF | Redirect `/login?error` | `formLogin()` + redirect + unauthenticated |
| HTTP Basic | `Authorization: Basic ...` | `401` + `WWW-Authenticate` | `httpBasic(...)`, status/authentication |
| JSON custom login | `POST /api/auth/login` JSON | `401`/JSON error theo custom controller | `post(...).contentType(...)` và policy |
| OAuth2/OIDC Login | Redirect đến IdP, callback token/code | Redirect hoặc lỗi của protocol | Integration với mock IdP, state/nonce, issuer |
| Bearer JWT Resource Server | `Authorization: Bearer ...` | `401` invalid token, `403` insufficient scope | Resource Server/JWT decoder mock và claims |
| WebFlux | reactive request/response | Theo `SecurityWebFilterChain` | `WebTestClient` và reactive security config |

**Không đem kết quả 302 của `formLogin` áp cho API JSON.** Ngược lại, test JSON mà tự gắn `@WithMockUser` sẽ bỏ qua password credential checks. Mỗi authentication entry point cần một bộ test riêng, đặc biệt khi ứng dụng có nhiều `SecurityFilterChain` với matchers hoặc order khác nhau.

## 17. Những lỗi test dễ khiến báo cáo “pass giả”

| Lỗi kiểm thử | Vì sao không đáng tin | Thay thế |
| --- | --- | --- |
| `@WithMockUser("active")` để test mật khẩu đúng | Không hề kiểm tra password | `formLogin()` hoặc AuthenticationManager thật |
| Chỉ assert status 302 | Cả success và failure đều redirect | Assert đúng `redirectedUrl` và authenticated state |
| Chỉ assert body chứa “login error” | Có thể trả error nhưng vẫn giữ session cũ | Kiểm tra context và request nối tiếp |
| Sai mật khẩu của user locked | Không cô lập locked state | Dùng mật khẩu đúng cho locked/disabled |
| Disable CSRF trong security config để test pass | Làm thay đổi threat model production | Dùng `formLogin()`/`csrf()` |
| Gọi `PasswordEncoder.matches` thủ công trong test rồi kết luận form login đúng | Bỏ qua filter, provider, session | Integration test full chain |
| Test account locked sau khi test brute-force mà không reset fixtures | Lệ thuộc thứ tự chạy test | Fixture mới hoặc cleanup state giữa tests |
| Assert 401 cho form login mặc định | Không đúng giao thức redirect | Kiểm tra 302 `/login?error` |
| Truyền raw password từ DB như test fixture thật | Lộ secret hoặc dùng encoder khác | Encode trong test-only store |
| Assert session == null khi login thất bại | CSRF/request cache có thể tạo anonymous session | Assert unauthenticated và protected route denied |
| Không kiểm tra HTTP method/CSRF | 403 bị nhầm password failure | Test CSRF độc lập |
| Bỏ test unknown user | Có thể lộ username enumeration | Cùng public behavior và timing review |
| Bỏ session continuity | 302 success nhưng request sau vẫn anonymous | GET protected endpoint cùng session |
| Dùng `UserDetails.isAccountNonLocked()` ngược nghĩa | Locked user login được | Fixture check cờ non-locked chính xác |
| Gộp disabled và expired | Policy và UX bị sai | Test flag/exception/route riêng |
| Không kiểm tra provider chain | Provider khác có thể bypass state check | Test tất cả login entrypoints |
| Gọi mọi exception là BadCredentials | Outage gây khóa nhầm user | Distinguish infra errors/audit |
| Dựa vào order/timing của một phiên bản Spring | Patch security thay đổi behavior | Test public contract, pin BOM, cập nhật advisory |

## 18. Checklist áp dụng trong dự án

**Fixture, environment và dependencies**

- [ ] Test project dùng Java 17+, Spring Boot/Security BOM tương thích, `spring-security-test` đúng test scope.
- [ ] Active, wrong-password, locked và disabled accounts được tạo độc lập, mật khẩu test được encode bằng cùng `PasswordEncoder`.
- [ ] Không dùng production credentials, không hardcode secrets thật hoặc log raw password.
- [ ] Đảm bảo test nằm trong SecurityFilterChain thật, không bypass bằng `@WithMockUser` khi cần xác minh password.

**Kết quả Authentication và HTTP**

- [ ] Active + correct -> authenticated principal/roles đúng, success redirect đúng.
- [ ] Active + wrong -> unauthenticated, failure redirect chung.
- [ ] Locked + correct -> unauthenticated, không được tạo full session.
- [ ] Disabled + correct -> unauthenticated, không tự mở vì cooldown kết thúc.
- [ ] Unknown user và các trạng thái lỗi tương đương có public response không tiết lộ trạng thái account.
- [ ] Assert exception nội bộ khi cần, không đưa message/stack trace ra browser.
- [ ] CSRF giữ đúng, request nối tiếp cùng session đến protected endpoint cho kết quả đúng.
- [ ] Nếu có MFA, password success chưa đồng nghĩa full login; test pending/verified factors.

**Khả năng vận hành và bảo mật**

- [ ] Test account status mapping, lockedUntil UTC, clock boundary, stale user cache và concurrent updates.
- [ ] Test trạng thái disabled khi session đã hoạt động, nếu policy yêu cầu revoke/reauth.
- [ ] Lỗi DB/LDAP/session store không tạo authenticated context và không tính bad password.
- [ ] Ghi audit categories đúng, không double-count, không log credentials hoặc PII không cần.
- [ ] Mỗi authentication entrypoint (form, Basic, API, OIDC, remember-me) có test tương ứng.
- [ ] Spring Security được vá advisory account-attribute timing; review rủi ro username enumeration ngoài response body.
- [ ] Tests độc lập, deterministic, không `Thread.sleep` dài, không phụ thuộc thứ tự hoặc state Redis dùng chung.

**Kết luận:** Kiểm thử login không chỉ so một username/password rồi mong HTTP 200. Với Spring Security, cần chứng minh **mật khẩu đúng tạo Authentication thật và phiên/authorization đúng**, trong khi **mật khẩu sai, account bị khóa và account disabled đều không thể tạo đăng nhập hợp lệ**. Các lỗi có thể khác nhau bên trong provider để audit, nhưng public response nên tránh rò danh tính/trạng thái; đồng thời CSRF, session continuity, MFA, clock, rate limit và hạ tầng phải được kiểm thử như các ranh giới riêng.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security — Testing Form Based Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html)
- [Spring Security — MockMvc Authentication Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html)
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — DaoAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring — CVE-2026-22746: User Attribute Enumeration when Using DaoAuthenticationProvider](https://spring.io/security/cve-2026-22746/)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Web Security Testing Guide: Testing for Weak Lock Out Mechanism](https://owasp.org/www-project-web-security-testing-guide/)
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
