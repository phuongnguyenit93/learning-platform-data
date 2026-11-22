# Kiểm thử Remember-me: cookie hợp lệ, hết hạn, bị sửa và đăng xuất

## 1. Mục tiêu và phạm vi bài học

**Remember-me** trong Spring Security cho phép trình duyệt nhận diện lại người dùng sau khi phiên đăng nhập tương tác trước đó đã mất hoặc hết hạn, thông qua một **cookie lưu lâu hơn HTTP session**. Đây là một cơ chế **tái xác thực tự động**, không phải một thuộc tính khiến session `JSESSIONID` tồn tại mãi, cũng không phải OAuth refresh token hay WebAuthn passkey.

Trong module **Spring Security - authentication**, nhóm **Kiểm thử đăng nhập**, mục tiêu của bài là **viết và hiểu kiểm thử Remember-me** cho các trường hợp:

1. Người dùng đăng nhập tương tác **không chọn** remember-me → không cấp persistent-login cookie.
2. Người dùng **chọn** remember-me → có cookie; request mới không có session cũ vẫn có thể được xác thực.
3. Cookie hợp lệ nhưng **hết hạn** → bị từ chối, không tạo phiên có quyền.
4. Cookie bị **sửa nội dung hoặc chữ ký** → bị từ chối; không coi một chuỗi Base64 có thể đọc được là đáng tin.
5. Cookie **persistent series/token** bị sửa, bị replay sau rotation → phát hiện không khớp và xử lý kho token theo hành vi Spring Security.
6. **Logout** → xóa cookie trình duyệt, chấm dứt HTTP session và thu hồi persistent tokens theo điều kiện; kiểm tra rõ bản sao cookie cũ.
7. Thay đổi mật khẩu, disable account, đổi signing key, xóa database token và thay đổi cookie flags ảnh hưởng thế nào.
8. Kết hợp **unit test service**, **integration test qua SecurityFilterChain/MockMvc** và kiểm thử đa node/HTTP thật.
9. Phân biệt một `RememberMeAuthenticationToken` được chấp nhận theo `authenticated()` với **fully authenticated** để bảo vệ thao tác nhạy cảm.

**Baseline ví dụ:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, JUnit Jupiter 5, Spring Test/MockMvc. Nội dung tập trung **Servlet security**: `HttpSecurity`, `RememberMeAuthenticationFilter`, `RememberMeServices`, `TokenBasedRememberMeServices` và `PersistentTokenBasedRememberMeServices`. Nếu ứng dụng dùng WebFlux, xem phần so sánh ở cuối; không copy nguyên code Servlet vào reactive chain.

> Các giá trị password/key/token trong code đều là **fixture test**, không phải mật khẩu hoặc secret sử dụng trong production. Không copy `{noop}` hoặc test signing key vào ứng dụng thật.

## 2. Remember-me nằm đâu trong quá trình đăng nhập?

```text
                                 REQUEST TƯƠNG TÁC
User -> POST /login (username, password, remember-me=on, CSRF)
                   |
                   v
           UsernamePasswordAuthenticationFilter
                   |
                   v
           AuthenticationManager/Provider xác thực password
                   |
                   +-- FAIL -> RememberMeServices.loginFail(...)
                   |
                   +-- SUCCESS
                          |
                          v
                   RememberMeServices.loginSuccess(...)
                          |
                   nếu "remember-me" được chọn:
                     Set-Cookie: remember-me=...
                          |
                          v
                   phiên browser login thông thường

                         REQUEST LẦN SAU
Browser -> GET /private, không mang session đã xác thực
           Cookie: remember-me=...
                   |
                   v
           RememberMeAuthenticationFilter
                   |
                   v
           RememberMeServices.autoLogin(request, response)
                   |
                   +-- null: không xác thực tự động; tùy URL -> login/401
                   |
                   +-- RememberMeAuthenticationToken
                              |
                              v
                    AuthenticationManager xác minh token
                              |
                              v
                    SecurityContext cho request
                              |
                              v
                    Authorization: authenticated() hay fullyAuthenticated()?
```

Các ranh giới dễ nhầm:

- `UsernamePasswordAuthenticationFilter` hoặc authentication filter tương tác báo **loginSuccess/loginFail** cho service.
- `RememberMeAuthenticationFilter` thử **autoLogin** khi chưa có `Authentication` trong SecurityContext.
- `RememberMeAuthenticationProvider` trong `AuthenticationManager` xác minh khóa ứng dụng của `RememberMeAuthenticationToken`. Đây **không phải** bước xác minh password được lặp lại như một form POST.
- `HttpSession` có thể tồn tại song song với remember-me cookie; khi test tác dụng cookie, phải **loại bỏ session cũ** để không tạo false positive.
- Authentication được tạo bằng remember-me thường được coi **remember-me**, không phải fully authenticated theo Spring Security trust resolver.
- Điều kiện cookie valid chưa đủ nếu account disabled/locked hoặc quyền truy cập yêu cầu step-up.

Theo Spring Security 6.5, `RememberMeServices` có các method:

```java
Authentication autoLogin(
        HttpServletRequest request,
        HttpServletResponse response);

void loginSuccess(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication successfulAuthentication);

void loginFail(
        HttpServletRequest request,
        HttpServletResponse response);
```

Các hàm này là **chữ ký interface rút gọn để học**, cần import `org.springframework.security.web.authentication.RememberMeServices` và các kiểu Spring/Servlet. `autoLogin` trả `Authentication` hoặc `null`; một cookie không hợp lệ thường bị từ chối và bị yêu cầu xóa trên response.

## 3. Hai implementation chính và khác biệt kiểm thử

| Thuộc tính | `TokenBasedRememberMeServices` | `PersistentTokenBasedRememberMeServices` |
| --- | --- | --- |
| Cơ sở xác thực cookie | Chữ ký hash trên username, thời điểm hết hạn, password hash và application key | `series` + `token`; server tìm bản ghi qua `PersistentTokenRepository` |
| Kho server-side riêng | Không cần | Cần persistent token repository |
| Có thể thu hồi từng thiết bị/token series? | Không có lookup store theo series; thường cần thay password/key hoặc thiết kế bổ sung | Có thể xóa row/series trong custom store; API mặc định `removeUserTokens(username)` xóa mọi series của user |
| Cookie còn hợp lệ sau password change? | **Không**, do chữ ký dùng password hiện tại | Không tự bị thu hồi chỉ vì password đổi; phải chủ động quản lý persistent records |
| Tự xoay token sau auto-login thành công | Không theo mô hình series/token rotation | **Có**: cùng series, token value mới |
| Cookie cũ sau token rotation | Không áp dụng | Mismatch series/token: hành vi chống nghi bị đánh cắp |
| Hết hạn | Kiểm tra timestamp expiry được ký | Kiểm tra ngày `last_used` + configured validity |
| Logout | Xóa cookie; bản sao cookie cũ có thể vẫn còn hợp lệ | Xóa cookie và **removeUserTokens** khi `Authentication != null` |
| Test nhanh | Không cần database | `InMemoryTokenRepositoryImpl` cho unit tests; JDBC cho integration |
| Dùng đa node | Cần cùng signing key, UserDetails/password state nhất quán | Cần shared repository + handling race/rotation |

**Lưu ý thuật ngữ:** tên “persistent token” không có nghĩa Spring Session hoặc OAuth refresh token. Đó là một kho dữ liệu chuyên dùng cho **persistent browser login**. Không dùng nó để gọi REST API như một OAuth Bearer token.

### 3.1. Vì sao signed cookie không phải “encrypted cookie”?

Cơ chế `TokenBasedRememberMeServices` sử dụng cookie Base64 chứa các trường có thể đọc được khi decode, cùng chữ ký/hash kiểm chứng:

```text
Base64(
  username : expiryTimeMillis : algorithmName : signatureHex
)
```

`signatureHex` phụ thuộc username, thời gian hết hạn, password từ `UserDetails` và secret key của ứng dụng. **Base64 không mã hóa bí mật**; đây là cách biểu diễn dữ liệu. Client có thể sửa giá trị bất kỳ nhưng không được chấp nhận nếu không thể tạo chữ ký hợp lệ.

Trong Spring Security 6.5, mặc định thuật toán ký là **SHA-256**, và có cơ chế khai báo thuật toán để hỗ trợ nâng cấp/matching; không làm bài test dựa trên giả định cũ là MD5 không có trường algorithm. Không tự so chuỗi Base64 để quyết định cookie hợp lệ.

### 3.2. Vì sao persistent cookie không chỉ kiểm timestamp?

Persistent cookie được encode từ:

```text
Base64(series : token)
```

Bản ghi `persistent_logins` chứa username, series, token và last-used timestamp. Khi có cookie:

1. Tìm bản ghi bằng `series`.
2. Không tìm được → không auto-login.
3. Series có nhưng token value khác → nghi replay/cookie theft: xóa **mọi persistent series của user** theo implementation mặc định và từ chối.
4. Token trùng nhưng record đã quá hạn → từ chối; record **không tự bị xóa** khi chỉ kiểm expiry.
5. Token còn hợp lệ → xoay token value, cập nhật ngày dùng, ghi cookie mới, sau đó nạp `UserDetails`.

Cơ chế rotation cải thiện khả năng phát hiện replay, nhưng **hai request đồng thời từ cùng một browser với cùng cookie** có thể gặp race và kích hoạt cơ chế nghi theft nếu storage/transaction/response timing không được thiết kế cẩn thận. Đừng coi `InMemoryTokenRepositoryImpl` là bằng chứng bảo đảm distributed concurrency; thử tải/đa node với database thật trước production.

## 4. Thiết kế ma trận test đúng trước khi viết test

Một ma trận tối thiểu:

| ID | Dữ liệu đầu vào | Kỳ vọng quan sát |
| --- | --- | --- |
| R01 | Interactive login đúng password, **không opt-in** | Không cấp remember-me cookie mới |
| R02 | Interactive login đúng password, `remember-me=on` | Có cookie với Max-Age/cấu hình bảo mật đúng |
| R03 | Cookie valid, **không mang JSESSIONID** | Auto-login thành công bằng remember-me |
| R04 | Cookie không có hoặc rỗng | Không auto-login |
| R05 | Signed cookie sai một ký tự chữ ký | Không auto-login; response yêu cầu xóa cookie |
| R06 | Signed cookie có expiry trong quá khứ nhưng chữ ký đúng | Không auto-login |
| R07 | Signed cookie hợp lệ sau đổi password hash | Không auto-login |
| R08 | Signed cookie sau logout, browser đã xóa cookie | Browser không gửi được cookie nữa |
| R09 | **Bản sao** signed cookie từ trước logout | Có thể vẫn valid nếu password/key không đổi; cần policy bổ sung |
| R10 | Persistent cookie valid, first reuse | Auto-login, cập nhật token value mới |
| R11 | Persistent cookie thiếu series | Không auto-login |
| R12 | Persistent cookie series đúng/token sai | Không auto-login; removeUserTokens(user) |
| R13 | Persistent cookie cũ sau một lần rotation thành công | Bị coi là mismatch/replay, có thể xóa các series |
| R14 | Persistent row có last-used quá cũ | Không auto-login; vẫn còn record tới cleanup |
| R15 | Persistent cookie sau logout với `Authentication != null` | Client cookie bị xóa, server token records của user bị xóa |
| R16 | Gọi service.logout với `Authentication == null` | Cookie bị xóa; **không được mặc định khẳng định** record server cũng bị xóa |
| R17 | Account disabled/locked/removed | Auto-login không được trao quyền |
| R18 | `authenticated()` vs `fullyAuthenticated()` | Remember-me có thể qua rule trước nhưng bị chặn ở rule sau |
| R19 | Tùy chỉnh cookie Secure/HttpOnly/SameSite | Flags phù hợp HTTPS/browser contract |
| R20 | Logout CSRF sai/thiếu | Không có side effect logout không được phép |
| R21 | API client không có cookie / endpoint stateless | Không tự dựa vào remember-me để mở quyền API ngoài policy |
| R22 | Multiple replicas và shared storage | Không mâu thuẫn về key/store/rotation |

**Tiêu chí quan trọng:** không chỉ assert HTTP 200/302. Phải chứng minh **vì sao** thành công hay thất bại: request không còn session, cookie thực sự được cấp/đọc/xóa, principal là remember-me, kho persistent token được cập nhật/thu hồi, và nhánh authorization cho phép/không cho phép.

## 5. Cấu hình Spring Security Servlet để kiểm thử

Trong **project Spring Boot 3.x Java 17+** dùng Gradle Groovy và Spring Boot plugin/BOM phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` cung cấp JUnit Jupiter và Spring Test, `spring-security-test` cung cấp MockMvc helpers và Spring security test support. Với JDBC persistent tokens, bổ sung `spring-boot-starter-jdbc` và driver phù hợp.

### 5.1. Form login + remember-me có opt-in

```java
// Trích đoạn trong bean SecurityFilterChain; chưa phải file độc lập.
@Bean
SecurityFilterChain security(HttpSecurity http,
        UserDetailsService userDetailsService) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .requestMatchers("/sensitive").fullyAuthenticated()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                    .key(rememberKey)
                    .userDetailsService(userDetailsService)
                    .rememberMeParameter("remember-me")
                    .tokenValiditySeconds(7 * 24 * 60 * 60))
            .build();
}
```

Giả định `rememberKey` là một chuỗi bí mật được inject từ configuration. Không tự hard-code vào source production. `rememberMeParameter("remember-me")` trùng tên ô checkbox/field trong request POST login. Nếu người dùng không opt-in và bạn **không** đặt `alwaysRemember(true)`, framework không cấp remember-me cookie mới.

Lưu ý security chain trên dùng form login/HTTP session. Khi thử remember-me, **không được** tái dùng HTTP session cũ rồi quy kết kết quả 200 do cookie.

### 5.2. Cấu hình cookie

Các tùy chọn thường cần:

- Tên mặc định `remember-me`; có thể dùng `rememberMeCookieName(...)` trên DSL hoặc `setCookieName(...)` của service.
- `HttpOnly` để JavaScript không đọc token; default `AbstractRememberMeServices` đặt HttpOnly.
- `Secure` khi dùng HTTPS; nên bắt buộc Secure ở môi trường production sau proxy TLS.
- `SameSite=Lax` hoặc `Strict` theo UX/CSRF policy và nhu cầu cross-site navigation. Spring Security 6.5 cho `AbstractRememberMeServices.setCookieCustomizer(...)` nếu bạn tạo service bean tường minh.
- `Path`/`Domain` đúng với endpoint dùng cookie và endpoint logout; sai path/domain có thể làm browser vẫn giữ bản cookie cũ.
- `Max-Age` phải tương thích TTL server-side. Browser có thể xóa cookie sớm, nhưng nếu vẫn gửi cookie quá hạn, **server phải từ chối**.
- Cookie không chứa password rõ, token không được ghi vào log, metrics, URL query hoặc screenshot.

Ví dụ customization trong class cấu hình cho service do bạn tạo:

```java
rememberMeServices.setUseSecureCookie(true);
rememberMeServices.setCookieCustomizer(cookie -> {
    cookie.setHttpOnly(true);
    cookie.setAttribute("SameSite", "Lax");
});
```

Đây là **trích đoạn** với biến `rememberMeServices` là một `AbstractRememberMeServices`; yêu cầu Servlet version hỗ trợ cookie attribute. Khi dùng custom service bean, nhớ gắn service vào DSL bằng `.rememberMeServices(rememberMeServices)`, đồng nhất signing key và `UserDetailsService` giữa các node.

## 6. Demo Spring Boot hoàn chỉnh để chạy MockMvc

File `src/main/java/demo/remember/RememberMeDemoApplication.java`:

```java
package demo.remember;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RememberMeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RememberMeDemoApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}demo-password")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http,
            UserDetailsService users,
            @Value("${app.remember.key}") String key) throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .requestMatchers("/sensitive").fullyAuthenticated()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .rememberMe(remember -> remember
                        .key(key)
                        .userDetailsService(users)
                        .rememberMeParameter("remember-me")
                        .tokenValiditySeconds(86400))
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String home() {
            return "Public";
        }

        @GetMapping("/private")
        String privatePage(Authentication authentication) {
            return "Hello, " + authentication.getName();
        }

        @GetMapping("/sensitive")
        String sensitive() {
            return "Recent login required";
        }
    }
}
```

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
app:
  remember:
    key: "${REMEMBER_ME_KEY}"
```

Ở local, cung cấp `REMEMBER_ME_KEY` bằng biến môi trường; trong unit/integration test có thể cung cấp key test riêng qua `@SpringBootTest(properties=...)`. Khóa cần bí mật, ổn định qua restart và **giống nhau trên các node**; nếu mỗi node dùng một key ngẫu nhiên khác nhau thì cookie được cấp ở node A sẽ bị từ chối ở B. Thay key chủ động có thể dùng để vô hiệu hóa mọi signed cookie cũ.

Mật khẩu `{noop}demo-password` **chỉ** dùng cho demo test. Trong production dùng `PasswordEncoder` phù hợp, TLS, rate limiting, account status/lockout và audit. Remember-me không phải thay thế cho MFA/passkey khi tài nguyên cần assurance cao.

### 6.1. Chạy demo

```bash
./gradlew bootRun
```

Windows PowerShell/cmd tùy project có thể dùng `gradlew.bat bootRun`. Truy cập `http://localhost:8080/login`, nhập username `alice` và password `demo-password`. Trang login mặc định có thể có checkbox remember-me khi tính năng đã bật. Với form tự thiết kế, field phải tên `remember-me`, đúng quy tắc CSRF của Spring Security.

Không in remember-me cookie hoặc giá trị signing key lên stdout. Nếu dùng DevTools và test trên HTTP local, cookie không phải Secure; **không** đem cấu hình HTTP local lên production.

## 7. MockMvc: kiểm chứng login có/không opt-in và cookie trên request mới

Lưu file `src/test/java/demo/remember/RememberMeWebFlowTest.java`:

```java
package demo.remember;

import java.util.Arrays;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest(properties =
        "app.remember.key=local-test-signing-key-not-for-production")
@AutoConfigureMockMvc
class RememberMeWebFlowTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean optIn) throws Exception {
        var request = post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-password");

        if (optIn) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
                .andExpect(status().is3xxRedirection())
                .andReturn();
    }

    private static Cookie rememberCookie(MvcResult result) {
        return Arrays.stream(result.getResponse().getCookies())
                .filter(c -> c.getName().equals("remember-me"))
                .findFirst()
                .orElseThrow();
    }

    @Test
    void optOutDoesNotIssueRememberMeCookie() throws Exception {
        MvcResult loggedIn = login(false);

        boolean issued = Arrays.stream(
                loggedIn.getResponse().getCookies())
                .anyMatch(c -> c.getName().equals("remember-me")
                        && c.getMaxAge() > 0);

        assertFalse(issued);
    }

    @Test
    void optedInCookieReauthenticatesWithoutOriginalSession()
            throws Exception {
        Cookie cookie = rememberCookie(login(true));

        // Cố ý KHÔNG truyền MockHttpSession/JSESSIONID từ lần login.
        mvc.perform(get("/private").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, alice"));
    }

    @Test
    void rememberMeIsNotFullyAuthenticated() throws Exception {
        Cookie cookie = rememberCookie(login(true));

        // authenticated() cho phép remember-me, fullyAuthenticated()
        // yêu cầu authentication mạnh hơn remember-me.
        mvc.perform(get("/sensitive").cookie(cookie))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithSessionClearsCookie() throws Exception {
        MvcResult loggedIn = login(true);
        Cookie cookie = rememberCookie(loggedIn);
        MockHttpSession session = (MockHttpSession)
                loggedIn.getRequest().getSession(false);

        assertNotNull(session);

        MvcResult logout = mvc.perform(post("/logout")
                        .with(csrf())
                        .session(session)
                        .cookie(cookie))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        Cookie cleared = Arrays.stream(
                logout.getResponse().getCookies())
                .filter(c -> c.getName().equals("remember-me"))
                .findFirst()
                .orElseThrow();

        assertEquals(0, cleared.getMaxAge());
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.remember.RememberMeWebFlowTest
```

Kỳ vọng **4 tests PASS** khi project dùng đúng Servlet stack/configuration như demo. Không có stdout JUnit cố định: Gradle có thể in summary khác nhau; chỉ cần test report ghi **4 tests, 0 failed**.

### 7.1. Những gì test này thực sự chứng minh

- Form login đúng password và opt-in có thể phát remember-me cookie.
- Không opt-in không cấp remember-me cookie **mới**.
- Một request **không mang HttpSession từ lần login** nhưng có remember-me cookie hợp lệ vẫn truy cập `/private` được.
- `fullyAuthenticated()` khác `authenticated()`: request chỉ dùng remember-me bị yêu cầu đăng nhập mạnh hơn.
- Logout với session đã xác thực xóa cookie ở response.

### 7.2. Những gì test này không chứng minh

- Không kiểm tra cookie đã bị sửa hoặc bị hết hạn: để tránh chờ thời gian thật, dùng unit tests ở các mục sau.
- Không chứng minh browser thực đã xóa cookie vì `MockMvc` mô phỏng HTTP; muốn kiểm tra browser persistence/cookie attributes cần E2E test.
- Không chứng minh **bản sao cookie bị đánh cắp** sau logout không còn hợp lệ. Với signed cookie, mặc định nó có thể vẫn được chấp nhận tới expiry nếu password/key không thay đổi.
- Không kiểm tra cookie `Secure` trong local HTTP; production HTTPS phải có test riêng.
- Không chứng minh rằng `MockMvc.with(user("alice"))` đã đi qua RememberMeAuthenticationFilter: demo cố ý sử dụng cookie thật do login sinh, không fake principal.

## 8. Unit test TokenBasedRememberMeServices: không chọn, hợp lệ, sửa chữ ký, hết hạn

`TokenBasedRememberMeServices` có thể được test **không khởi động Spring Boot/HTTP server** bằng `MockHttpServletRequest`, `MockHttpServletResponse` và một `InMemoryUserDetailsManager`. Việc gọi trực tiếp `loginSuccess` và `autoLogin` kiểm thử thuật toán cookie thực, không chỉ Mockito stub.

File `src/test/java/demo/remember/SignedRememberMeServiceTest.java`:

```java
package demo.remember;

import java.time.Instant;
import java.util.Arrays;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.authentication.rememberme
        .TokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme
        .TokenBasedRememberMeServices.RememberMeTokenAlgorithm;

import static org.junit.jupiter.api.Assertions.*;

class SignedRememberMeServiceTest {

    private InMemoryUserDetailsManager users;
    private TestableSignedService service;

    static final class TestableSignedService
            extends TokenBasedRememberMeServices {

        TestableSignedService(InMemoryUserDetailsManager users) {
            super("unit-test-key", users, RememberMeTokenAlgorithm.SHA256);
        }

        String[] parts(Cookie cookie) {
            return decodeCookie(cookie.getValue());
        }

        Cookie pack(String[] parts) {
            return new Cookie("remember-me", encodeCookie(parts));
        }

        Cookie expiredButCorrectlySigned(String username,
                String storedPassword) {
            long expiry = Instant.parse(
                    "2000-01-01T00:00:00Z").toEpochMilli();
            String signature = makeTokenSignature(
                    expiry, username, storedPassword,
                    RememberMeTokenAlgorithm.SHA256);

            return pack(new String[] {
                    username,
                    Long.toString(expiry),
                    "SHA256",
                    signature
            });
        }
    }

    @BeforeEach
    void setup() {
        users = new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-password")
                        .roles("USER")
                        .build());

        service = new TestableSignedService(users);
        service.setTokenValiditySeconds(3600);
        service.afterPropertiesSet();
    }

    private Authentication authenticatedAlice() {
        UserDetails user = users.loadUserByUsername("alice");
        return UsernamePasswordAuthenticationToken.authenticated(
                user, null, user.getAuthorities());
    }

    private Cookie issue() {
        MockHttpServletRequest login =
                new MockHttpServletRequest("POST", "/login");
        login.addParameter("remember-me", "on");
        MockHttpServletResponse response =
                new MockHttpServletResponse();
        service.loginSuccess(login, response, authenticatedAlice());

        return Arrays.stream(response.getCookies())
                .filter(c -> c.getName().equals("remember-me"))
                .findFirst()
                .orElseThrow();
    }

    private MockHttpServletRequest withCookie(Cookie cookie) {
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/private");
        request.setCookies(cookie);
        return request;
    }

    private static Cookie cancellation(MockHttpServletResponse response) {
        return Arrays.stream(response.getCookies())
                .filter(c -> c.getName().equals("remember-me"))
                .findFirst()
                .orElseThrow();
    }

    @Test
    void noOptInMeansNoPersistentLoginCookie() {
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        service.loginSuccess(
                new MockHttpServletRequest("POST", "/login"),
                response, authenticatedAlice());

        assertEquals(0, response.getCookies().length);
    }

    @Test
    void validCookieAutoLogsInAlice() {
        Cookie cookie = issue();

        Authentication result = service.autoLogin(
                withCookie(cookie), new MockHttpServletResponse());

        assertNotNull(result);
        assertInstanceOf(RememberMeAuthenticationToken.class, result);
        assertEquals("alice", result.getName());
        assertTrue(result.isAuthenticated());
    }

    @Test
    void modifiedSignatureIsRejectedAndCookieCleared() {
        Cookie original = issue();
        String[] parts = service.parts(original);
        String signature = parts[3];

        // Đổi chắc chắn một ký tự chữ ký, giữ format Base64 hợp lệ.
        parts[3] = (signature.charAt(0) == '0' ? "1" : "0")
                + signature.substring(1);
        Cookie tampered = service.pack(parts);
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        Authentication result = service.autoLogin(
                withCookie(tampered), response);

        assertNull(result);
        assertEquals(0, cancellation(response).getMaxAge());
    }

    @Test
    void correctlySignedExpiredCookieIsRejected() {
        String storedPassword =
                users.loadUserByUsername("alice").getPassword();
        Cookie expired = service.expiredButCorrectlySigned(
                "alice", storedPassword);

        MockHttpServletResponse response =
                new MockHttpServletResponse();
        Authentication result = service.autoLogin(
                withCookie(expired), response);

        assertNull(result);
        assertEquals(0, cancellation(response).getMaxAge());
    }

    @Test
    void changingPasswordInvalidatesSignedCookie() {
        Cookie oldCookie = issue();
        users.updateUser(User.withUsername("alice")
                .password("{noop}new-password")
                .roles("USER")
                .build());

        Authentication result = service.autoLogin(
                withCookie(oldCookie), new MockHttpServletResponse());

        assertNull(result);
    }

    @Test
    void disabledUserCannotAutoLoginEvenWithValidSignature() {
        Cookie oldCookie = issue();
        users.updateUser(User.withUsername("alice")
                .password("{noop}demo-password")
                .roles("USER")
                .disabled(true)
                .build());

        Authentication result = service.autoLogin(
                withCookie(oldCookie), new MockHttpServletResponse());

        assertNull(result);
    }

    @Test
    void logoutClearsCookieButCannotRevokeCapturedSignedCopy() {
        Cookie capturedCopy = issue();
        MockHttpServletResponse logoutResponse =
                new MockHttpServletResponse();

        service.logout(withCookie(capturedCopy),
                logoutResponse, authenticatedAlice());

        assertEquals(0, cancellation(logoutResponse).getMaxAge());

        // Mô phỏng attacker vẫn giữ bản sao cookie từ trước.
        Authentication replay = service.autoLogin(
                withCookie(capturedCopy), new MockHttpServletResponse());

        assertNotNull(replay);
        assertEquals("alice", replay.getName());
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.remember.SignedRememberMeServiceTest
```

Kỳ vọng **7 tests PASS**. Bài test hết hạn dùng một class con test để truy cập `makeTokenSignature(...)`/`encodeCookie(...)` **protected** từ chính implementation; không đặt `Thread.sleep(...)`, không giả mạo bằng token có chữ ký sai rồi gọi nó là “test expiry”.

### 8.1. Giải thích test “đã logout mà captured copy còn valid”

Nó cố ý mô tả một **giới hạn bảo mật** của signed/stateless remember-me. Logout thường chỉ gửi cookie hết hạn tới browser. Server không có per-token series để biết và thu hồi mọi bản sao cookie đã bị lấy trước đó. Nếu vẫn còn password hash và signing key cũ, **bản sao cookie cũ** có thể còn được sử dụng tới lúc expiry. Với account có nghi compromise:

- Đổi password làm chữ ký của cookie cũ không còn khớp trong `TokenBasedRememberMeServices`.
- Xoay application remember-me signing key khiến các cookie ký theo key cũ không hợp lệ, thường áp dụng cho **tất cả** user của key đó.
- Có thể chuyển sang persistent token store để hỗ trợ server-side revocation, hoặc không dùng remember-me ở tài khoản nhạy cảm.
- Hủy HTTP session thôi chưa đủ nếu cookie cũ có thể tạo lại authentication trong request tiếp theo.

Không tuyên bố “logout vô hiệu mọi session/token đã từng phát” chỉ vì test kiểm tra `Max-Age=0`.

## 9. Unit test PersistentTokenBasedRememberMeServices: rotation, expiry, sửa token và logout

Persistent implementation cho phép kiểm thử vòng đời bằng **`InMemoryTokenRepositoryImpl`**. Đó là test repository **chỉ dành cho môi trường kiểm thử**, không phải lựa chọn production đa instance.

Một persistent cookie có hai phần (`series` và `token`); test nên dùng encode/decode của chính lớp bằng subclass test nhỏ, tránh tự đoán Base64 format. Đặc biệt nhớ kiểm tra **rotation** khi valid token được dùng: series giữ nguyên, token value thay đổi.

File `src/test/java/demo/remember/PersistentRememberMeServiceTest.java`:

```java
package demo.remember;

import java.util.Arrays;
import java.util.Date;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.authentication.rememberme
        .InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme
        .PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme
        .PersistentTokenRepository;

import static org.junit.jupiter.api.Assertions.*;

class PersistentRememberMeServiceTest {

    private InMemoryUserDetailsManager users;
    private InMemoryTokenRepositoryImpl store;
    private TestablePersistentService service;

    static final class TestablePersistentService
            extends PersistentTokenBasedRememberMeServices {

        TestablePersistentService(InMemoryUserDetailsManager users,
                PersistentTokenRepository store) {
            super("persistent-test-key", users, store);
        }

        String[] parts(Cookie cookie) {
            return decodeCookie(cookie.getValue());
        }

        Cookie pack(String[] parts) {
            return new Cookie("remember-me", encodeCookie(parts));
        }
    }

    @BeforeEach
    void setup() {
        users = new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-password")
                        .roles("USER")
                        .build());

        store = new InMemoryTokenRepositoryImpl();
        service = new TestablePersistentService(users, store);
        service.setTokenValiditySeconds(3600);
        service.afterPropertiesSet();
    }

    private Authentication authenticatedAlice() {
        UserDetails user = users.loadUserByUsername("alice");
        return UsernamePasswordAuthenticationToken.authenticated(
                user, null, user.getAuthorities());
    }

    private MockHttpServletRequest withCookie(Cookie cookie) {
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/private");
        request.setCookies(cookie);
        return request;
    }

    private static Cookie findCookie(MockHttpServletResponse response) {
        return Arrays.stream(response.getCookies())
                .filter(c -> c.getName().equals("remember-me"))
                .findFirst()
                .orElseThrow();
    }

    private Cookie issue() {
        MockHttpServletRequest login =
                new MockHttpServletRequest("POST", "/login");
        login.addParameter("remember-me", "on");

        MockHttpServletResponse response =
                new MockHttpServletResponse();
        service.loginSuccess(login, response, authenticatedAlice());

        return findCookie(response);
    }

    @Test
    void validPersistentCookieAuthenticatesAndRotates() {
        Cookie before = issue();
        String[] old = service.parts(before);

        MockHttpServletResponse response =
                new MockHttpServletResponse();
        Authentication result = service.autoLogin(
                withCookie(before), response);

        assertNotNull(result);
        assertInstanceOf(RememberMeAuthenticationToken.class, result);
        assertEquals("alice", result.getName());

        Cookie rotated = findCookie(response);
        String[] newer = service.parts(rotated);

        assertEquals(old[0], newer[0]);  // series không đổi
        assertNotEquals(old[1], newer[1]); // token được xoay
        assertEquals(newer[1],
                store.getTokenForSeries(old[0]).getTokenValue());
    }

    @Test
    void modifiedTokenWithKnownSeriesRevokesUserTokens() {
        Cookie issued = issue();
        String[] parts = service.parts(issued);
        String series = parts[0];
        parts[1] = parts[1] + "-changed";

        Cookie tampered = service.pack(parts);
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        assertNull(service.autoLogin(withCookie(tampered), response));
        assertEquals(0, findCookie(response).getMaxAge());

        // Spring Security xử lý mismatch bằng removeUserTokens(username).
        assertNull(store.getTokenForSeries(series));
    }

    @Test
    void replayingOldCookieAfterRotationTriggersRevocation() {
        Cookie original = issue();
        String series = service.parts(original)[0];

        // Lần đầu hợp lệ, token được rotate.
        assertNotNull(service.autoLogin(
                withCookie(original), new MockHttpServletResponse()));

        // Bản sao cũ giờ không trùng token hiện tại của cùng series.
        assertNull(service.autoLogin(
                withCookie(original), new MockHttpServletResponse()));
        assertNull(store.getTokenForSeries(series));
    }

    @Test
    void expiredPersistentRecordIsRejectedButNotAutoDeleted() {
        Cookie original = issue();
        String[] parts = service.parts(original);

        // Không sleep; ghi last-used trong quá khứ rất xa.
        store.updateToken(parts[0], parts[1], new Date(0L));

        MockHttpServletResponse response =
                new MockHttpServletResponse();
        assertNull(service.autoLogin(withCookie(original), response));
        assertEquals(0, findCookie(response).getMaxAge());

        // Đánh giá hết hạn KHÔNG tự cleanup record.
        assertNotNull(store.getTokenForSeries(parts[0]));
    }

    @Test
    void unknownSeriesDoesNotAuthenticate() {
        Cookie issued = issue();
        String[] parts = service.parts(issued);
        parts[0] = "does-not-exist";

        assertNull(service.autoLogin(
                withCookie(service.pack(parts)),
                new MockHttpServletResponse()));
    }

    @Test
    void logoutWithPrincipalClearsCookieAndServerRecords() {
        Cookie original = issue();
        String series = service.parts(original)[0];
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        service.logout(
                withCookie(original), response, authenticatedAlice());

        assertEquals(0, findCookie(response).getMaxAge());
        assertNull(store.getTokenForSeries(series));
        assertNull(service.autoLogin(
                withCookie(original), new MockHttpServletResponse()));
    }

    @Test
    void logoutWithoutPrincipalOnlyClearsBrowserCookie() {
        Cookie capturedCopy = issue();
        String series = service.parts(capturedCopy)[0];

        MockHttpServletResponse response =
                new MockHttpServletResponse();
        service.logout(withCookie(capturedCopy), response, null);

        assertEquals(0, findCookie(response).getMaxAge());

        // Implementation mặc định chỉ removeUserTokens nếu auth != null.
        assertNotNull(store.getTokenForSeries(series));

        // Bản sao vẫn có thể được chấp nhận nếu attacker còn giữ.
        assertNotNull(service.autoLogin(
                withCookie(capturedCopy), new MockHttpServletResponse()));
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.remember.PersistentRememberMeServiceTest
```

Kỳ vọng **7 tests PASS** khi dùng đúng Spring Security 6.5.x và test dependencies. Không cần chờ đồng hồ vì case expiry thay `last_used` trong test repository. Với application thật, “expired record còn tồn tại” là bài toán cleanup storage, **không** phải bằng chứng token vẫn được chấp nhận.

### 9.1. Phân biệt sửa series và sửa token

- **Series không tồn tại**: lookup không thấy record; việc này không thể kết luận cookie bị đánh cắp từ user nào, vì thế không có user để gọi `removeUserTokens`.
- **Series có thật nhưng token value sai**: có thể là **cookie cũ bị replay hoặc bị sửa**, và mặc định Spring Security gọi `removeUserTokens(username)`, khiến mọi persistent remembered logins của user bị thu hồi.
- **Record đúng nhưng hết hạn**: từ chối vì TTL; record có thể còn tồn tại tới scheduled cleanup.
- **Record đúng, còn hạn**: authentication được tạo, store nhận token mới và response phát cookie tương ứng.

Với account đa thiết bị, một mismatch có thể làm nhiều thiết bị phải đăng nhập lại. Cần có UX/monitoring về nghi replay, nhưng không trả chi tiết series/token vào HTTP error hoặc log.

## 10. Logout có ba lớp: cookie, session, server token

Một người dùng bấm Sign out. Thao tác cần xét tối thiểu:

```text
POST /logout (+ CSRF cho browser session)
       |
       v
Spring Security LogoutFilter / LogoutHandlers
       |
       +--> SecurityContextLogoutHandler
       |       invalidate session và clear context
       |
       +--> RememberMeServices.logout(...)
       |       send Set-Cookie remember-me=; Max-Age=0
       |       nếu persistent & authentication != null:
       |           removeUserTokens(authentication.getName())
       |
       +--> CsrfLogoutHandler / các handlers liên quan
       |
       v
LogoutSuccessHandler -> redirect/response
```

**Ba loại state độc lập:**

1. **Browser cookie:** Set-Cookie với `Max-Age=0` yêu cầu browser bỏ remember-me credential. Để xóa đúng cookie, tên, Path, Domain, Secure, SameSite policy nên tương thích khi phát cookie. MockMvc chỉ nhìn response; E2E browser mới kiểm tra cookie jar thực tế.
2. **HTTP session:** `JSESSIONID`/SecurityContext của interactive login cần bị invalidated/cleared. Xóa remember-me cookie **không** chứng minh session đã bị hủy; và xóa session **không** tự vô hiệu hóa một bản sao remember-me cookie đã bị đánh cắp.
3. **Persistent token record:** với `PersistentTokenBasedRememberMeServices`, `logout(..., authentication)` chỉ xóa `removeUserTokens(username)` **nếu có authentication khác null**. Nếu null thì hành vi mặc định chỉ là xóa cookie ở client.

### 10.1. Vì sao logout sau khi session đã mất cần test riêng?

Spring Security `LogoutFilter` có thể được thực thi trước `RememberMeAuthenticationFilter` trong filter chain. Nếu người dùng không còn session nhưng browser vẫn gửi remember-me cookie, tại thời điểm LogoutFilter chạy có thể **chưa có Authentication** được phục hồi. Khi đó persistent logout service có thể không biết user nào cần xóa token record.

Không kết luận một lời gọi `POST /logout` **luôn** thu hồi mọi persistent tokens chỉ từ việc nhìn HTTP 302 hoặc cookie Max-Age=0. Muốn đạt yêu cầu “logout và revoke ở server dù không có session”, cần một flow an toàn có khả năng nhận diện/kiểm chứng cookie trước khi thu hồi hoặc một endpoint quản trị đã xác minh tài khoản; phải chống CSRF và không cho client tùy chọn username để xóa token của người khác.

**Không** tự giải quyết bằng cách decode cookie lấy username rồi xóa mọi token: persistent cookie không mang username, và kể cả signed cookie có username thì việc đọc string chưa xác minh không phải chứng cứ được phép revoke bất kỳ ai.

### 10.2. Hành vi “logout mọi thiết bị”

`PersistentTokenRepository.removeUserTokens(username)` có thể thu hồi mọi series remember-me **cho username**. Nhưng nó không mặc định:

- Hủy mọi HTTP sessions ở Redis/Spring Session.
- Thu hồi OAuth refresh token/access token tại Authorization Server.
- Hủy OP/IdP SSO session hoặc passkey trên thiết bị.
- Xóa cookie đang lưu ở mọi trình duyệt; browser sẽ tự xóa khi nhận response của chính nó, hoặc server từ chối cookie trên những request sau.

Với security incident, phải phối hợp nhiều store/thiết bị và xác nhận hiệu lực từng thành phần. Nếu yêu cầu chỉ “đăng xuất thiết bị hiện tại”, xóa **tất cả series của user** có thể rộng hơn mong muốn. Hãy định nghĩa UX và chính sách trước khi dùng default method này.

## 11. Kiểm thử HTTP logout: CSRF, session và redirect

Trong demo `/login` với Spring Security CSRF bật mặc định, logout được thực hiện bằng **POST /logout** và CSRF token hợp lệ:

```java
// Trích đoạn MockMvc trong @SpringBootTest với MockMvc mvc:
mvc.perform(post("/logout")
        .with(csrf())
        .session(existingLoggedInSession))
    .andExpect(status().is3xxRedirection());
```

Cần test request thiếu CSRF:

```java
// Trích đoạn - logout không được diễn ra khi CSRF bắt buộc.
mvc.perform(post("/logout")
        .session(existingLoggedInSession))
    .andExpect(status().isForbidden());
```

Ở phiên bản và config tiêu chuẩn, `GET /logout` có thể hiển thị trang xác nhận; nó **không tương đương** `POST /logout` thay đổi trạng thái. Nếu bạn tắt CSRF toàn bộ, mapping mặc định có thể thay đổi; đừng tắt CSRF để test logout “dễ pass”.

Khi logout đúng, các assertion bổ sung:

- Session đã bị invalidate hoặc SecurityContext đã bị xóa theo handler.
- Response có remember-me cookie xóa đúng tên/path và max age.
- Với persistent flow và account đã xác thực, repository records đã xóa.
- Thử request **mới, không có session cũ** với bản cookie trước logout để xác định server chấp nhận hay từ chối.
- Client không bị redirect tới một URL ngoài domain do query parameter không đáng tin.

## 12. Hết hạn: đừng dùng Thread.sleep và đừng nhầm cookie Max-Age

### 12.1. Hai loại thời gian

- **Browser cookie Max-Age/Expires:** browser quyết định lưu/gửi cookie bao lâu.
- **Server-side token validity:** Spring Security kiểm tra thời hạn token/cookie hoặc ngày last-used trong persistent store.

Một browser có thể không gửi cookie đã hết Max-Age, nhưng attacker có thể **tự gửi cookie cũ bằng HTTP client**. Vì vậy server bắt buộc kiểm tra expiry, không dựa vào browser. Ngược lại, cookie bị xóa sớm không có nghĩa server token record đã hết hạn.

### 12.2. Test deterministic

**Signed strategy:** Test subclass `TokenBasedRememberMeServices` ở mục 8 dùng `makeTokenSignature(...)` thật và giá trị expiry năm 2000. Không phụ thuộc đồng hồ máy chạy nhanh/chậm vài giây.

**Persistent strategy:** Test repository dùng `Date(0)` cho last-used của một record đúng. Với `tokenValiditySeconds=3600`, record hiển nhiên hết hạn. Không phải `Thread.sleep(3600000)`.

**Thực tế:** dùng Clock injectable với custom time-aware component nếu bạn tự viết service; đừng sửa global system clock cho toàn bộ JVM test. Nếu business policy yêu cầu TTL 7 ngày, có thể test riêng token generated Max-Age=604800 và server verify expiry qua test fixture.

### 12.3. Boundary tests

Thêm test tại các ngưỡng:

1. Còn trước expiry → valid.
2. **Đúng** expiry → hành vi theo dấu so sánh implementation thực tế; test source theo phiên bản thay vì tự đoán `<` hoặc `<=`.
3. Ngay sau expiry → invalid.
4. Clock skew giữa nodes; expiry timestamp millisecond vs seconds.
5. Token được rotate lúc gần hết hạn: persistent token có thể kéo dài theo **last-used**, trong khi signed expiry thường cố định từ lần interactive login.
6. Browser tiếp tục gửi cookie dù máy đồng hồ sai: server vẫn phải là nguồn xác quyết định thời hạn.

**Không** tự coi persistent `last_used` là thời điểm phát hành cố định. Token rotation có thể kéo dài remembered login theo chính sách, trừ khi hệ thống bổ sung **absolute maximum lifetime** riêng.

## 13. Token bị sửa: bốn nhóm tampering cần phân biệt

| Tamper | Signed-cookie | Persistent-cookie |
| --- | --- | --- |
| Cắt ngắn/bỏ một trường | Cookie invalid, autoLogin từ chối/xóa | Cookie invalid, autoLogin từ chối/xóa |
| Đổi username | Chữ ký không còn hợp lệ | Không có username trong cookie |
| Đổi expiry | Chữ ký không còn hợp lệ nếu không ký lại | Expiry dựa trên record server, không nằm trong cookie |
| Đổi signature | So sánh chữ ký thất bại | Không áp dụng; thay token cùng series → mismatch/theft handling |
| Đổi series | Không có series | Không tìm thấy row hoặc trúng series khác với token sai |
| Replay cookie cũ sau rotation | Không có per-request rotation mặc định | Token cũ khác token mới → chống replay và xóa series của user theo code mặc định |
| Thay application key | Signed token cũ không verify | Persistent token vẫn dựa vào store; key còn liên quan authentication-provider key matching |

**Test “tampered” đúng nghĩa không nên chỉ đưa một string không phải Base64** rồi nhận 401 và kết luận chữ ký chống sửa hoạt động. Có hai test khác nhau: malformed encoding và **định dạng hợp lệ nhưng nội dung/chữ ký không khớp**. Bài đã dùng helper `decodeCookie/encodeCookie` để làm trường hợp thứ hai.

### 13.1. Không ghi raw cookie vào log/CI artifacts

Cookie remember-me là **credential**. JUnit failure message như `assertEquals(expectedCookieValue, actualCookieValue)` có thể in credential ra test report. Với integration test dùng user test thì rủi ro nhỏ hơn, nhưng vẫn phải giữ thói quen không đẩy cookie vào log, snapshot hoặc metrics. Dùng hash/correlation ID an toàn khi cần.

## 14. Cookie bị đánh cắp: đổi password, disabled account và khóa ký

### 14.1. Đổi password

Signed strategy dùng password string/hash hiện tại trong chữ ký. Vì vậy thay passwordHash trên `UserDetails` có thể khiến cookie cũ không khớp, như test mục 8. Đừng tự nối password plaintext vào response — cơ chế chỉ sử dụng trên server để tính/check signature.

Persistent strategy không tự sử dụng password hash để check series/token. **Sau đổi mật khẩu, phải chủ động xóa persistent tokens** (ví dụ `removeUserTokens(username)`) nếu business policy yêu cầu đăng nhập lại mọi thiết bị. Đồng thời hủy session cũ/refresh tokens nếu có.

### 14.2. Disable/locked account

`AbstractRememberMeServices` có `setUserDetailsChecker(...)` và mặc định dùng account-status checks phù hợp. Khi user disabled/locked/expired, autoLogin nên không tạo authenticated principal. Một custom `UserDetailsService` không đưa đúng trạng thái vào `UserDetails` có thể làm policy bị bypass.

Test cần:

- Issue cookie **trước khi** disable user.
- Disable user trong trusted repository.
- Request **không mang session** với cookie cũ.
- Expect no remember-me Authentication và access bị chặn.
- Restore account chỉ qua đúng reactivation policy, không tự revive persistent records đã revoked.

### 14.3. Signing key

Nếu signing key bị lộ, attacker có thể tạo cookie signed hợp lệ nếu các dữ liệu cần thiết đều có; cần rotation key, rà soát phiên và nâng mức bảo vệ. Các nodes đang dùng key khác nhau có thể gây lỗi intermittent. Nên lưu key ở secret manager, rotation có thời hạn và runbook rõ. Với signed strategy, đổi key thường invalidates cookie cũ trên toàn ứng dụng.

## 15. Persistent token storage: JDBC và cleanup

Spring Security cung cấp `JdbcTokenRepositoryImpl` thực hiện `PersistentTokenRepository`. Theo reference 6.5, schema cơ bản:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

Đây là schema tham khảo; với PostgreSQL/MySQL/SQL Server cần migration theo dialect/requirements. Không dựa vào `setCreateTableOnStartup(true)` ở production: tính năng đó chỉ tiện debug.

Ví dụ bean Servlet JDBC:

```java
// Trích đoạn trong @Configuration của Spring Boot JDBC app.
@Bean
PersistentTokenRepository rememberTokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}

@Bean
SecurityFilterChain security(HttpSecurity http,
        PersistentTokenRepository repository,
        UserDetailsService users,
        @Value("${app.remember.key}") String key) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                    .key(key)
                    .userDetailsService(users)
                    .tokenRepository(repository)
                    .tokenValiditySeconds(86400))
            .build();
}
```

Hai snippet cần imports `javax.sql.DataSource`, Spring Security config, rememberme types, v.v. Chúng minh họa **cấu hình persistent** riêng, không nên chạy trong cùng application demo signed-cookie ở mục 6 mà không chọn một chiến lược rõ.

### 15.1. Tests JDBC thực sự khác in-memory

`InMemoryTokenRepositoryImpl` có thể pass unit tests nhưng không chứng minh:

- DB transaction/isolation, unique constraint trên series.
- Rotation update và concurrent requests ở hai application replicas.
- Dữ liệu token tồn tại qua restart/deploy.
- Cơ chế cleanup row hết hạn, retention và DB capacity.
- Credential row được xóa khi logout, password change, account delete/disable trên **mọi node**.
- Row-level security/tenant boundary và bảo vệ token trong backups/DB query logs.

Test integration với H2/Testcontainers hoặc DB thật theo ứng dụng, áp dụng schema bằng Flyway/Liquibase và dùng hai HTTP clients với cookie jar tách biệt. Đừng bật create table tự động khi nhiều replicas cạnh tranh.

### 15.2. Concurrency và rotation

Nếu hai request đồng thời dùng cùng persistent cookie:

```text
Request A                         Request B
 read series S, token T           read series S, token T
 compare T == stored T            compare T == stored T
 update stored token = T_A        update stored token = T_B ?
 Set-Cookie(T_A)                  Set-Cookie(T_B)
```

Kết quả phụ thuộc storage isolation và thời điểm các reads/writes. Khi một request nhận cookie cũ sau rotation, implementation có thể coi mismatch là dấu hiệu theft và xóa tất cả tokens của user. Production cần load tests thực tế, đảm bảo chính sách replay, concurrency/transaction và UX phù hợp. Không hứa rằng mặc định JDBC implementation đã có compare-and-swap atomic để loại bỏ mọi race nếu chưa kiểm chứng source/dialect.

## 16. Remember-me và authorization: authenticated khác fullyAuthenticated

Spring Security có `AuthenticationTrustResolver` và các authorization expression để phân biệt authentication bằng remember-me với login mạnh hơn:

```java
// Trong authorizeHttpRequests:
.requestMatchers("/profile").authenticated()
.requestMatchers("/change-password").fullyAuthenticated()
```

- `authenticated()`: request có một `Authentication` được xem là authenticated, bao gồm remember-me khi phù hợp.
- `fullyAuthenticated()`: yêu cầu **không phải** anonymous và **không phải** remember-me; có thể redirect tới login hoặc trả challenge theo config nếu chỉ có remembered identity.
- Quyền theo role/scope vẫn áp dụng riêng; `fullyAuthenticated()` không tự chứng minh MFA/passkey/UV hoặc thời điểm login gần đây.
- Với lệnh chuyển tiền, đổi email/khóa, xóa account, đăng ký passkey, việc “fullyAuthenticated” **có thể vẫn chưa đủ**; cần recent reauthentication/step-up và business authorization tương ứng.

Bộ test WebFlow ở mục 7 tạo cookie thật rồi gọi `/sensitive` **không mang session** để khẳng định không bypass. Nếu chỉ dùng `with(user("alice"))`, Spring Security Test tạo authentication giả được coi full và sẽ không kiểm chứng remember-me trust level thật.

## 17. Phân biệt remember-me với OAuth tokens, passkey và SSO

| Credential/state | Mục đích | Logout ảnh hưởng thế nào? |
| --- | --- | --- |
| `remember-me` cookie | Tạo lại authentication cho browser | Logout handler xóa cookie; server-side persistent tokens cần revoke phù hợp |
| `JSESSIONID` / HTTP session | Giữ SecurityContext qua nhiều requests | Session invalidation/clear context |
| OAuth2 refresh token | Xin access token mới từ Authorization Server | Phải revoke grant/token ở AS; logout local không tự revoke |
| JWT access token | Gọi Resource Server | Offline RS có thể tiếp tục chấp nhận tới expiry nếu không có revocation mechanism |
| OIDC OP SSO session | Đăng nhập tập trung tại IdP | RP logout không chắc đã logout OP; cần OIDC logout flow |
| WebAuthn passkey | Credential khóa mật mã để login/step-up | Logout không xóa public-key binding hay private key trên authenticator |

Mất một thiết bị chứa cả session cookie, remember-me cookie và passkey cần **incident response phối hợp**. Đổi password có thể vô hiệu signed remember-me cookie nhưng **không đảm bảo** revoke mọi OAuth tokens hoặc passkey. Xóa passkey tại RP không tự xóa remember-me cookie đã cấp. Đây là lý do test phải xác định từng state store, không gộp thành một assertion “logout all”.

## 18. CORS, CSRF, same-site và browser thực: kiểm thử ngoài MockMvc

Remember-me cookie được browser đính kèm theo domain/path/SameSite policy, vì vậy:

1. Browser không cần JavaScript đọc cookie; HttpOnly nên được bật.
2. Form login/logout dùng cookie authentication và session: giữ **CSRF protection** cho POST theo policy.
3. HTTPS production: Secure cookie bắt buộc, không chấp nhận credential cookie qua HTTP. Sau TLS reverse proxy cần cấu hình forwarded headers/secure request đúng.
4. SameSite có thể ảnh hưởng flows cross-site navigation; không dùng `SameSite=None` bừa bãi, và khi cần phải bật `Secure`.
5. Chạy test E2E trên browser thật để biết cookie có được lưu, gửi trên subdomain/path đúng và xóa thật sau logout không.
6. Cookie có Max-Age nhưng browser policy/private mode có thể xóa sớm; server không suy ra client cookie jar còn hay không.
7. Không đặt remember-me cookie lên phạm vi domain rộng không cần thiết, tránh subdomain không tin cậy nhận cookie.
8. CORS preflight/fetch credentials không đồng nghĩa nhớ đăng nhập. CORS chỉ kiểm soát browser API access, không phải cơ chế xác thực cookie.
9. Giao diện nên có lựa chọn **Remember me on this device** rõ ràng; không auto opt-in trên máy dùng chung nếu chính sách không cho phép.
10. Sau logout, test reload trang trong **browser context sạch** và test attacker gửi thủ công cookie cũ là hai kịch bản khác nhau.

### 18.1. Browser test mô tả dạng pseudocode

```text
Given: user Alice authenticates using interactive login
When: Alice selects "Remember me"
Then: browser stores the remember-me cookie with expected flags

When: the application session disappears but remember-me cookie remains
Then: browser can load a non-sensitive authenticated page

When: Alice logs out
Then: browser drops the remember-me cookie
And: the application session is invalidated

When: an attacker replays the original cookie value with a separate client
Then: expected result depends on signed vs persistent revocation policy
And: high-risk actions still require step-up
```

Không dùng mã giả này thay cho JUnit/HTTP integration tests; đây là acceptance criteria cho Playwright/Selenium hoặc browser test infrastructure.

## 19. Debug các lỗi phổ biến

### 19.1. Đã login nhưng không xuất hiện remember-me cookie

Kiểm tra request POST login có `remember-me=on` không, bạn có đang bật `alwaysRemember(false)` mặc định, login có thật sự thành công, `RememberMeServices.loginSuccess` có được gắn vào authentication filter và cookie path/secure policy có khiến browser bỏ qua không. Nếu dùng custom success handler/provider, nó có gọi đúng hooks không?

### 19.2. Cookie có nhưng user không được auto-login

Kiểm tra cookie có được gửi trong request mới hay không (Domain, Path, SameSite, Secure), có đang mang HttpSession cũ làm test sai không, key giữa nodes có nhất quán, `UserDetailsService` trả đúng password hash/account status không, token có hết hạn, và manager có `RememberMeAuthenticationProvider` tương ứng không.

### 19.3. Test valid pass nhưng HTTP lại 302 login

Có thể route yêu cầu `fullyAuthenticated()`, cookie chưa được browser gửi, cookie bị từ chối hoặc service tạo `RememberMeAuthenticationToken` nhưng provider/manager không tin key. Đọc trace trong môi trường test, không in raw token/password. Đối với `fullyAuthenticated()`, redirect/challenge là hành vi mong muốn.

### 19.4. Sửa cookie mà test vẫn nhận 200

Rất có thể request vẫn có session đã authenticated, nên remember-me filter **không hề chạy**. Xóa JSESSIONID/MockHttpSession khi gửi cookie bị sửa; chỉ đưa cookie `remember-me`. Bảo đảm target route yêu cầu authenticated. Dùng assertions chứng minh SecurityContext là remember-me khi valid.

### 19.5. Test hết hạn thất bại ngẫu nhiên

Đừng dùng `Thread.sleep(1000)` rồi so sát boundary; phụ thuộc CI speed/system clock. Với signed strategy, dùng token được ký đúng nhưng expiry rất xa trong quá khứ; với persistent, dùng record cũ bằng `Date(0)`. Test đúng ngưỡng chỉ khi biết implementation dùng dấu so sánh nào.

### 19.6. Logout 302 và cookie bị xóa nhưng record DB còn

Kiểm tra `PersistentTokenBasedRememberMeServices.logout` có nhận `Authentication != null` không. Kiểm tra logout handler registration và request có session/user context. Đừng kết luận “database phải xóa” chỉ từ HTTP status. Khi design yêu cầu luôn revoke, bổ sung flow nhận diện user theo phương thức đáng tin và test cả phiên đã mất.

### 19.7. Token persistent bị xóa hàng loạt sau một request

Có thể request dùng cookie cũ sau rotation: series đúng nhưng token value không còn trùng, implementation coi như stolen cookie và gọi `removeUserTokens(username)`. Kiểm tra concurrent requests/response race, storage replication và các browser tabs. Không thay bằng logic “nếu mismatch thì chấp nhận” vì phá chống replay.

### 19.8. Thay mật khẩu mà persistent remember-me vẫn hoạt động

Đó là sự khác nhau giữa signed cookie và persistent token store. Phải gọi `removeUserTokens(username)` khi password change/reset hoặc account security event theo policy. Không chờ đổi password tự xóa DB token row.

### 19.9. Thay đổi key làm signed cookies ở mọi browser mất tác dụng

Đúng semantics: signature phụ thuộc key. Nếu rotation không chủ đích, kiểm tra secret configuration trên các replicas/deployments. Nếu rotation vì incident, dự kiến buộc user đăng nhập lại và thông báo phù hợp.

### 19.10. Test dựa vào MockMvc.with(user(...)) luôn pass

Request post-processor đó **tiêm một Authentication đã có**, bỏ qua login/password/remember-me cookie validation. Dùng nó cho authorization tests, không dùng để chứng minh remember-me token valid/expired/tampered. Hãy gọi flow login thật hoặc service thật.

## 20. Test matrix production đầy đủ

| Test | Tầng | Dữ liệu/trigger | Kết quả bắt buộc |
| --- | --- | --- | --- |
| T01 | MockMvc | POST /login đúng, không remember-me | Không cấp cookie mới |
| T02 | MockMvc | POST /login đúng, opt-in | Có remember-me cookie |
| T03 | MockMvc | POST /login sai password, opt-in | Không cấp remember-me credential hợp lệ |
| T04 | MockMvc | POST /login thiếu CSRF | Không tạo login/cookie |
| T05 | MockMvc | Không mang session, cookie valid | Xác thực bằng remember-me |
| T06 | MockMvc | Chỉ có nhớ đăng nhập, gọi `fullyAuthenticated` | Từ chối/reauth challenge |
| T07 | Unit signed | Cookie bị sửa signature có format hợp lệ | Không autoLogin |
| T08 | Unit signed | Cookie hết hạn nhưng signature đúng | Không autoLogin |
| T09 | Unit signed | Password hash changed | Cookie cũ bị từ chối |
| T10 | Unit signed | Account disabled/locked | Không được autoLogin |
| T11 | Unit signed | Cookie malformed base64/truncated fields | Không autoLogin và cancel cookie |
| T12 | Unit signed | Thay application key | Chữ ký cũ bị từ chối |
| T13 | Unit signed | Logout | Xóa cookie browser; đánh giá nguy cơ replay |
| T14 | Unit persistent | Series/token còn hạn | AutoLogin + rotate |
| T15 | Unit persistent | Series không tồn tại | Từ chối |
| T16 | Unit persistent | Series đúng/token sai | Từ chối, revoke tokens user |
| T17 | Unit persistent | Replay cookie trước rotation | Từ chối và báo nghi theft theo policy |
| T18 | Unit persistent | Record hết hạn | Từ chối nhưng còn record đến cleanup |
| T19 | Unit persistent | Logout có principal | Cookie expire + removeUserTokens |
| T20 | Unit persistent | Logout principal null | Không giả định server token đã bị xóa |
| T21 | JDBC integration | DB restart sau cookie issue | Token persistence đúng thiết kế |
| T22 | JDBC integration | Hai app replicas dùng shared DB | Login/revoke đồng nhất |
| T23 | Concurrency | Hai requests cùng series/token | Không lộ quyền sai, đánh giá rotation race |
| T24 | Browser | Cookie Secure/HttpOnly/SameSite/Path | Browser lưu/gửi/xóa đúng |
| T25 | Browser | POST logout thiếu CSRF | Không logout ngoài chủ đích |
| T26 | Account security | Disable/remove user | Tất cả remember-me paths fail closed |
| T27 | Account security | Password reset/logout all | Revocation theo chính sách của cả cookie và DB |
| T28 | OIDC/OAuth | Local logout + active OAuth/SSO token | Không tuyên bố revoke ngoài phần đã thực thi |
| T29 | Session | HTTP session vẫn còn, cookie sai | Test được tách để không tạo false positive |
| T30 | Ops | Metrics/logs | Không log raw cookies, secrets hoặc password |
| T31 | Recovery | Mất thiết bị có remember-me cookie | Có playbook thu hồi sessions/tokens |
| T32 | Multi-node | Signed key khác nhau giữa nodes | Test phát hiện, policy yêu cầu key nhất quán |
| T33 | Version regression | Nâng Spring Security/Boot | Cookie algorithm/format và integration tests còn đúng |
| T34 | Retention | Persistent rows hết hạn lâu ngày | Cleanup background, không để storage vô hạn |

Sắp xếp mức ưu tiên: **test signed 7 trường hợp + persistent 7 trường hợp + MockMvc 4 trường hợp** là bộ cơ sở để học; các trường hợp JDBC/đa node/browser là lớp kiểm chứng bắt buộc nếu sản phẩm thực sự triển khai remember-me cho người dùng.

## 21. Vận hành và bảo mật: những điều test đúng vẫn chưa đủ

### 21.1. Remember-me là credential dài hạn

Một cookie remember-me hợp lệ có thể cho người sở hữu nó khôi phục authentication khi session đã mất. Hãy bảo vệ nó như credential: HTTPS, Secure/HttpOnly/SameSite, domain/path tối thiểu, TTL có giới hạn, không log hoặc gửi sang bên thứ ba. Nếu account nhạy cảm, cân nhắc **không bật** tính năng hoặc bắt buộc step-up cho thao tác rủi ro.

### 21.2. Thu hồi sau sự cố

Khi user báo mất thiết bị:

1. Khóa/invalidate các session nghi bị chiếm.
2. Thu hồi persistent remember-me token rows hoặc thay signing key/password theo chiến lược phù hợp.
3. Thu hồi refresh grants/API keys cần thiết ở hệ thống khác.
4. Bảo vệ email/phone/passkey recovery tránh attacker lấy lại account.
5. Thông báo/audit và kiểm chứng request mới với cookie bị thu hồi đã bị chặn.
6. Chấp nhận rằng local logout và server-side remember-me revocation có thể có độ trễ trong cluster; đo và giám sát.

Không chỉ gửi `Set-Cookie: remember-me=; Max-Age=0` cho browser hiện tại rồi kết luận attacker không thể dùng bản copy cũ.

### 21.3. Key và repository có chung trust boundary

Key ở `TokenBasedRememberMeServices` phải bí mật, xoay theo policy. Persistent repository phải chống truy cập trái phép, rò rỉ row series/token, log query và backup leak. Nếu có 2+ replicas, dùng store chia sẻ với tính nhất quán đúng yêu cầu; không xem memory repository dùng test là production-ready.

### 21.4. Expired record cleanup

`PersistentTokenBasedRememberMeServices` kiểm tra ngày record nhưng không tự dọn mọi token hết hạn khỏi kho. Thiết kế job cleanup có lịch và index phù hợp; test rằng cleanup không xóa nhầm record active và bị fail retry được. Nếu lưu retention/audit metadata, không giữ raw token lâu hơn cần thiết.

## 22. Checklist trước khi bàn giao bài kiểm thử

1. Đã xác định ứng dụng dùng **signed** hay **persistent** strategy, cookie name, validity và user details source.
2. Có test login **opt-in vs opt-out**, đúng form field và CSRF.
3. Test cookie valid **không truyền session cũ**, tránh false positive.
4. Test signed cookie **signature changed** khác test malformed Base64.
5. Test signed cookie **expired nhưng vẫn signed đúng** và password/key invalidation.
6. Test persistent **valid + rotation** với cả series và token mới; test replay.
7. Test persistent **unknown series**, **same series/wrong token** và expiry record.
8. Test logout với `Authentication != null` **và** `null`, kiểm cả cookie lẫn repository.
9. Đã phân biệt logout chỉ xóa cookie với thu hồi bản copy bị đánh cắp.
10. Test `authenticated()` so với `fullyAuthenticated()` cho endpoint nhạy cảm.
11. Có test account status disabled/locked, UserDetailsChecker và thay đổi password.
12. Nếu dùng JDBC, đã test schema/cleanup/transaction/concurrency và 2+ replicas.
13. Có browser E2E test Secure, HttpOnly, SameSite, Domain, Path, Max-Age, logout và CSRF.
14. Không để remember-me cookie/token/key xuất hiện trong log, request URL, metrics hoặc test reports.
15. Có playbook cho account compromise/mất thiết bị, ký lại cookie hoặc revoke persistent tokens.
16. Có regression tests khi nâng Spring Security, thay login filter hoặc đổi authentication mechanism.

**Kết luận:** kiểm thử Remember-me phải chứng minh **cookie được phát khi opt-in, được chấp nhận khi còn hạn, bị từ chối khi hết hạn/bị sửa, và được xử lý đúng khi logout**. Đặc biệt không đánh đồng **xóa cookie trên browser** với **thu hồi credential server-side** hoặc **chặn một bản sao cookie đã bị lấy cắp**. Với persistent strategy, rotation và mismatch-series/token là những test riêng phải có; với signed strategy, expiry/signature/password-key dependence là trọng tâm.

## 23. Tài liệu chính thức

- [Spring Security 6.5.11 — Remember-Me Authentication (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html): signed approach, persistent approach, loginSuccess/loginFail/autoLogin, `UserDetailsService`, cookie rotation.
- [Spring Security 6.5.11 — RememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/RememberMeServices.html): hợp đồng 3 method và xử lý cookie invalid.
- [Spring Security 6.5.11 — AbstractRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/AbstractRememberMeServices.html): cookie flags, TTL, opt-in và logout.
- [Spring Security 6.5.11 — TokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/TokenBasedRememberMeServices.html): signature, SHA-256, expiry, password/key invalidation.
- [Spring Security 6.5.11 — PersistentTokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html): series/token, refresh/rotation, expiry record, logout.
- [Spring Security 6.5.11 — PersistentRememberMeToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentRememberMeToken.html): username, series, token và date.
- [Spring Security 6.5.11 — InMemoryTokenRepositoryImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/InMemoryTokenRepositoryImpl.html): test repository.
- [Spring Security 6.5.11 — JdbcTokenRepositoryImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/JdbcTokenRepositoryImpl.html): JDBC persistent records và schema/migration.
- [Spring Security 6.5.11 — RememberMeAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/RememberMeAuthenticationFilter.html): auto login filter và SecurityContext.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): LogoutFilter, handlers, CSRF, SecurityContext/session/cookie cleanup.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session persistence, SecurityContext, authentication lifetime.
- [Spring Security — MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): test form login/CSRF/authentication và request post-processors.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session/token lifecycle, cookie flags và invalidation.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): persistent login, reauthentication cho hành động nhạy cảm, chống lộ credential.
