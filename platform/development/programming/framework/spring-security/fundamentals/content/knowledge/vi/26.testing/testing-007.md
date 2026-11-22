# Kiểm thử đăng nhập đúng, thông tin sai và tài khoản không được sử dụng

> **Phạm vi:** kiểm thử xác thực bằng username/password với **Spring Boot 3.x, Spring Security 6.x, Spring MVC (Servlet), Java 17+**. Bài thực hành dùng form login và `MockMvc` để phân biệt ba nhóm kết quả: **đăng nhập thành công**, **thông tin đăng nhập không hợp lệ**, **tài khoản tồn tại nhưng không được phép sử dụng** (ví dụ bị vô hiệu hóa, bị khóa, hết hạn). Các tình huống bổ trợ gồm truy cập tài nguyên bảo vệ, CSRF, session và thiếu quyền. Ví dụ tích hợp đầy đủ với `spring-security-test`; không coi mã HTTP 401 là kết quả mặc định của **form login**.

## 1. Mục tiêu và ma trận tình huống

Đăng nhập không chỉ là kiểm tra `POST /login` trả về trạng thái HTTP nào. Một bộ kiểm thử xác thực tốt phải chứng minh: **thông tin hợp lệ tạo ra danh tính đã xác thực đúng**, còn thông tin không hợp lệ hoặc tài khoản không được sử dụng **không thể tạo ra ngữ cảnh đã xác thực**. Đồng thời cần kiểm tra đường dẫn chuyển hướng và quyền truy cập sau login.

| Tình huống | Bằng chứng xác thực | Trạng thái tài khoản | Kết quả kỳ vọng khi dùng form login |
| --- | --- | --- | --- |
| Đăng nhập đúng | Username tồn tại, password đúng | Enabled, không bị khóa, chưa hết hạn | Chuyển hướng tới `/home`; `authenticated()` đúng username/role |
| Sai password | Username tồn tại, password sai | Đang hoạt động | Chuyển hướng `/login?error`; `unauthenticated()` |
| Username không tồn tại | Username không có trong kho | Không áp dụng | Chuyển hướng `/login?error`; `unauthenticated()` |
| Thiếu username hoặc password | Credential thiếu hoặc rỗng | Không xác định | Thất bại xác thực; không có danh tính authenticated |
| Tài khoản disabled | Password đúng | `enabled=false` | Thất bại; không cấp session đăng nhập hợp lệ |
| Tài khoản locked | Password đúng | `accountNonLocked=false` | Thất bại; không cấp danh tính đã xác thực |
| Tài khoản hết hạn | Password đúng | `accountNonExpired=false` | Thất bại; không được sử dụng tài khoản |
| Credentials hết hạn | Password đúng | `credentialsNonExpired=false` | Thất bại; yêu cầu quy trình đổi/cấp lại credential theo thiết kế |
| Có tài khoản hợp lệ nhưng thiếu role | Đăng nhập thành công | Đang hoạt động | Đã xác thực nhưng request vào `/admin` bị **403** |
| POST login thiếu CSRF | Credential có thể đúng | Đang hoạt động | **403 từ bảo vệ CSRF** trước khi hoàn thành xác thực |

**Phân biệt hai khái niệm:** *xác thực thất bại* là không chấp nhận credential/tài khoản; *phân quyền thất bại* xảy ra khi đã xác thực nhưng không được phép làm thao tác. Do đó, một test trả 403 khi gọi `/admin` không chứng minh login đã thất bại.

**Điểm dễ nhầm với HTTP:** Trong ví dụ **form login**, cả đăng nhập đúng và đăng nhập sai đều có thể trả **302 Found** vì cơ chế trả kết quả bằng redirect. Thành công đi tới `/home`, thất bại về `/login?error`. Với **HTTP Basic**, lỗi credential thường trả **401** và `WWW-Authenticate`. Viết assertion đúng với cơ chế đang cấu hình, không ép mọi login failure phải 401.

## 2. Dòng xử lý form login của Spring Security

```text
Browser
  |
  | GET /login
  v
Trang login do Spring Security tạo
  |
  | POST /login + username/password + CSRF
  v
CsrfFilter
  |-- thiếu/sai CSRF --> thường 403 (chưa kiểm tra password)
  |
  v
UsernamePasswordAuthenticationFilter
  |
  | tạo UsernamePasswordAuthenticationToken chưa xác thực
  v
AuthenticationManager (thường là ProviderManager)
  |
  v
DaoAuthenticationProvider
  |-- UserDetailsService tìm UserDetails
  |-- kiểm tra các trạng thái tài khoản
  |-- PasswordEncoder so khớp password/hash
  |-- kiểm tra trạng thái credential
  |
  +------ thành công ----------------- thất bại -------+
  |                                                    |
  v                                                    v
Authentication hợp lệ                         AuthenticationException
  |                                                    |
  v                                                    v
SecurityContext được thiết lập                SecurityContext bị làm sạch
và được lưu theo cơ chế login                  AuthenticationFailureHandler
  |                                                    |
  v                                                    v
AuthenticationSuccessHandler                     Redirect /login?error
  |
  v
Redirect /home
  |
  v
GET /home kèm phiên xác thực -> 200
```

Vai trò của các thành phần:

- `UserDetailsService`: trả về `UserDetails` từ kho tài khoản. Ví dụ dùng `InMemoryUserDetailsManager`; production có thể thay bằng database/LDAP hoặc adapter phù hợp.
- `PasswordEncoder`: dùng `matches(rawPassword, storedHash)` để xác minh mật khẩu. Ví dụ sử dụng `BCryptPasswordEncoder`; không để password rõ trong kho dữ liệu production.
- `DaoAuthenticationProvider`: cơ chế tiêu chuẩn kiểm tra username/password và trạng thái `UserDetails`. Không cần tự viết provider chỉ để kiểm thử các trạng thái enabled/locked/expired.
- `UsernamePasswordAuthenticationFilter`: xử lý request login thực tế, tạo token đầu vào và chuyển tới manager.
- `AuthenticationSuccessHandler`/`AuthenticationFailureHandler`: quyết định redirect hoặc kiểu phản hồi sau khi xác thực.
- `SecurityContext`: chứa `Authentication` đã chấp nhận. Ở form login dựa trên session, context được lưu giữa các request theo cơ chế của Spring Security.
- `AuthorizationFilter`: áp dụng quyền lên URL sau xác thực; `/admin` cần `ROLE_ADMIN` sẽ bị từ chối đối với người có `ROLE_USER`.

Một test chỉ kiểm tra `response.status == 302` là yếu: **cả hai nhánh đều có thể 302**. Cần thêm `redirectedUrl` và security result matcher. Một test chỉ gọi `get("/home").with(user("alice"))` cũng không chứng minh password được kiểm tra: helper `user(...)` đã đưa danh tính mock vào request.

## 3. Chuẩn bị ứng dụng minh họa

### 3.1. Dependencies

Dùng dự án Spring Boot 3.x với Java 17+ và Gradle plugin Spring Boot đã cấu hình. Thêm vào khối `dependencies` của `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **khối phụ thuộc**, không phải toàn bộ file Gradle. `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ/Hamcrest và MockMvc; `spring-security-test` cung cấp `formLogin()`, `authenticated()`, `unauthenticated()` cùng các hỗ trợ kiểm thử security. Không cần khởi chạy một server bên ngoài để dùng `MockMvc`.

### 3.2. Tạo ứng dụng và các trạng thái tài khoản

Tạo file **`src/main/java/demo/DemoApplication.java`** như sau:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("active")
                        .password(encoder.encode("active-pass"))
                        .roles("USER")
                        .build(),

                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN")
                        .build(),

                User.withUsername("disabled")
                        .password(encoder.encode("disabled-pass"))
                        .roles("USER")
                        .disabled(true)
                        .build(),

                User.withUsername("locked")
                        .password(encoder.encode("locked-pass"))
                        .roles("USER")
                        .accountLocked(true)
                        .build(),

                User.withUsername("expired")
                        .password(encoder.encode("expired-pass"))
                        .roles("USER")
                        .accountExpired(true)
                        .build(),

                User.withUsername("credential-old")
                        .password(encoder.encode("credential-old-pass"))
                        .roles("USER")
                        .credentialsExpired(true)
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .defaultSuccessUrl("/home", true)
                        .failureUrl("/login?error")
                        .permitAll())
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/home")
    String home(Authentication authentication) {
        return "Xin chao " + authentication.getName();
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin-only";
    }
}
```

**Đây là một file Java hoàn chỉnh.** Tên tệp khớp với lớp `public DemoApplication`; `SecurityConfig` và `DemoController` là các top-level class package-private cùng package `demo`. `@SpringBootApplication` quét package này và tự nhận các bean.

Tài khoản dùng trong ví dụ:

| Username | Password demo | Cờ trạng thái quan trọng | Có thể đăng nhập? |
| --- | --- | --- | --- |
| `active` | `active-pass` | Đủ điều kiện mặc định | Có, role `USER` |
| `admin` | `admin-pass` | Đủ điều kiện mặc định | Có, role `ADMIN` |
| `disabled` | `disabled-pass` | `isEnabled() == false` | Không |
| `locked` | `locked-pass` | `isAccountNonLocked() == false` | Không |
| `expired` | `expired-pass` | `isAccountNonExpired() == false` | Không |
| `credential-old` | `credential-old-pass` | `isCredentialsNonExpired() == false` | Không |

`User.withUsername(...)` tạo `UserDetails` cho bài minh họa. Các setter builder `disabled(true)`, `accountLocked(true)`, `accountExpired(true)` và `credentialsExpired(true)` đại diện cho những trạng thái **bị từ chối**. Chú ý cách đặt tên phủ định ở interface: `isAccountNonLocked() == true` nghĩa là tài khoản **không bị khóa**; `isCredentialsNonExpired() == true` nghĩa là credential **chưa hết hạn**.

Trong cấu hình:

- `.requestMatchers("/public").permitAll()` mở một endpoint để so sánh.
- `.requestMatchers("/admin").hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN`; user `active` chỉ có `ROLE_USER`.
- `.anyRequest().authenticated()` yêu cầu xác thực cho endpoint khác như `/home`.
- `.formLogin(...)` bật cơ chế form login và trang login mặc định. Chưa gọi `loginPage(...)` nên Spring Security tự tạo trang `GET /login`. Nếu định nghĩa custom login page sau này, phải tự cung cấp trang đó.
- `.defaultSuccessUrl("/home", true)` giúp lần login thành công luôn redirect tới `/home` trong ví dụ, dù trước đó có saved request.
- `.failureUrl("/login?error")` làm mọi trường hợp login failure có cùng đường chuyển hướng công khai. Đây là lựa chọn giúp tránh lộ “username tồn tại nhưng bị khóa”.
- `.permitAll()` cho phép người chưa xác thực dùng endpoints phục vụ login. Không cần đặt password validation trong controller.
- Không có lệnh `csrf.disable()`. Form login dùng POST nên CSRF vẫn được bảo vệ; test phải gửi token hợp lệ.

**An toàn ví dụ:** tài khoản và password hard-code chỉ dùng ở localhost/lab. Với production, không lưu password nguồn trong code, không xuất hash qua API, dùng HTTPS và kho tài khoản thực cùng chính sách khóa/rate limiting.

## 4. Viết kiểm thử tích hợp với MockMvc

Tạo file **`src/test/java/demo/FormLoginFlowTest.java`**:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormLoginFlowTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    UserDetailsService userDetailsService;

    @Test
    void publicPageDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousVisitorIsRedirectedToLoginPage() throws Exception {
        mvc.perform(get("/home"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        "Location", containsString("/login")));
    }

    @Test
    void correctLoginCreatesAuthenticatedSession() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("active")
                        .password("active-pass"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/home"))
                .andExpect(authenticated()
                        .withUsername("active")
                        .withRoles("USER"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/home").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("Xin chao active"));
    }

    @Test
    void wrongPasswordFailsAuthentication() throws Exception {
        mvc.perform(formLogin()
                        .user("active")
                        .password("wrong-password"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void unknownUsernameHasSamePublicFailureOutcome() throws Exception {
        mvc.perform(formLogin()
                        .user("missing-user")
                        .password("some-password"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void emptyCredentialsFailAuthentication() throws Exception {
        mvc.perform(formLogin()
                        .user("")
                        .password(""))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @ParameterizedTest
    @CsvSource({
            "disabled, disabled-pass",
            "locked, locked-pass",
            "expired, expired-pass",
            "credential-old, credential-old-pass"
    })
    void unusableAccountCannotLogIn(
            String username, String correctPassword) throws Exception {

        mvc.perform(formLogin()
                        .user(username)
                        .password(correctPassword))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void accountStateFlagsAreConfiguredAsExpected() {
        assertFalse(userDetailsService
                .loadUserByUsername("disabled").isEnabled());

        assertFalse(userDetailsService
                .loadUserByUsername("locked").isAccountNonLocked());

        assertFalse(userDetailsService
                .loadUserByUsername("expired").isAccountNonExpired());

        assertFalse(userDetailsService
                .loadUserByUsername("credential-old")
                .isCredentialsNonExpired());
    }

    @Test
    void loggedInUserStillCannotAccessAdminOnlyUrl()
            throws Exception {

        MvcResult login = mvc.perform(formLogin()
                        .user("active")
                        .password("active-pass"))
                .andExpect(authenticated()
                        .withUsername("active"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminOnlyUrlAfterLogin()
            throws Exception {

        MvcResult login = mvc.perform(formLogin()
                        .user("admin")
                        .password("admin-pass"))
                .andExpect(authenticated()
                        .withUsername("admin")
                        .withRoles("ADMIN"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/admin").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-only"));
    }

    @Test
    void postLoginWithoutCsrfIsRejectedBeforePasswordCheck()
            throws Exception {

        mvc.perform(post("/login")
                        .param("username", "active")
                        .param("password", "active-pass"))
                .andExpect(status().isForbidden())
                .andExpect(unauthenticated());
    }
}
```

**Đây là một test class đầy đủ** cùng package `demo`, dùng JUnit Jupiter và Spring Security Test. Test dùng `@SpringBootTest` để khởi động context thật của ví dụ, `@AutoConfigureMockMvc` cấu hình `MockMvc` có filter Spring Security. Không gọi tới server mạng; request/response được mô phỏng qua Spring MVC Test trong JVM.

Để chạy trong thư mục dự án:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

Khi muốn chạy đúng một class trong Gradle:

```bash
./gradlew test --tests demo.FormLoginFlowTest
```

**Kết quả kỳ vọng:** toàn bộ phương thức kiểm thử pass nếu mã ứng dụng và dependencies đúng cấu hình ví dụ. Không khẳng định output tổng số test từ một môi trường chưa chạy; `@ParameterizedTest` sinh nhiều invocation và công cụ Gradle/JUnit có thể hiển thị cách đếm khác nhau. Với thất bại thực tế, xem stack trace của đúng test để xác định mismatch giữa redirect, principal, session hay CSRF.

## 5. Đọc kỹ ba nhóm kiểm thử chính

### 5.1. Đăng nhập đúng: không chỉ nhìn mã 302

Test `correctLoginCreatesAuthenticatedSession` gồm bốn lớp chứng cứ:

1. `formLogin().user("active").password("active-pass")` mô phỏng submit `POST /login` với tham số mặc định `username/password` **và CSRF token hợp lệ**.
2. `status().isFound()` và `redirectedUrl("/home")` chứng minh success handler đi tới đường dẫn mong muốn.
3. `authenticated().withUsername("active").withRoles("USER")` chứng minh authentication result đúng danh tính/authority. `withRoles("USER")` kiểm tra quy ước `ROLE_USER`.
4. Lấy `MockHttpSession` từ login request và gửi `GET /home` bằng cùng session chứng minh **request tiếp theo** đọc được `SecurityContext` đã lưu. Response trả chính xác `Xin chao active`.

Nếu chỉ assert 302, test không phát hiện đổi sang redirect failure. Nếu chỉ gọi `get("/home").with(user("active"))`, đó là **mô phỏng người đã xác thực** và có thể bỏ qua password encoder hay logic kiểm tra trạng thái tài khoản. `formLogin()` mới thực sự đi qua cơ chế đăng nhập trong `SecurityFilterChain` của ví dụ.

Lưu ý `@WithMockUser` và `user(...)` hữu ích để thử authorization/controller trong những test khác, nhưng **không đủ** chứng minh rằng thông tin đăng nhập thực sự đã được xác minh qua `AuthenticationManager`.

### 5.2. Sai mật khẩu hoặc không tồn tại username

Test `wrongPasswordFailsAuthentication` dùng username hợp lệ với password sai; test `unknownUsernameHasSamePublicFailureOutcome` dùng username không tồn tại. Cả hai phải:

- Đi về `/login?error`, không tự động được coi là thành công vì trả 302.
- Thỏa `unauthenticated()`; không có principal xác thực thành công.
- Không tạo ra quyền `ROLE_USER` hoặc một phiên đăng nhập dùng được.

Tùy provider/configuration, `UsernameNotFoundException` có thể được che thành `BadCredentialsException` để hạn chế khả năng suy đoán tài khoản tồn tại. **Không đặt yêu cầu “response phải nói user không tồn tại”** trong API công khai. Với test black-box, sự giống nhau của phản hồi được quan sát qua redirect/status và kết quả authentication; trong production cũng cần xem body/message/headers và thời gian đáp ứng nếu vấn đề user enumeration quan trọng.

**Sai username không phải là thiếu quyền:** sai credentials ngăn quá trình xác thực; thiếu quyền xảy ra sau khi danh tính đã được chấp nhận.

### 5.3. Tài khoản không được sử dụng: disabled, locked và expired

Test `unusableAccountCannotLogIn` dùng **password chính xác** cho từng tài khoản nhưng trạng thái không cho phép. Dùng password đúng là chủ đích quan trọng: test phải chứng minh trạng thái account tự nó ngăn login, không bị che bởi lỗi password sai.

| Cờ của UserDetails | Ý nghĩa hợp lệ khi `true` | Ví dụ builder từ chối |
| --- | --- | --- |
| `isEnabled()` | Tài khoản được bật sử dụng | `disabled(true)` |
| `isAccountNonLocked()` | Tài khoản không bị khóa | `accountLocked(true)` |
| `isAccountNonExpired()` | Tài khoản chưa hết hạn | `accountExpired(true)` |
| `isCredentialsNonExpired()` | Credentials chưa hết hạn | `credentialsExpired(true)` |

Những lỗi tương ứng trong các provider tiêu chuẩn thường thuộc nhóm `DisabledException`, `LockedException`, `AccountExpiredException` và `CredentialsExpiredException`, là các kiểu `AuthenticationException`. Thứ tự kiểm tra account/credentials có thể khác tùy provider; đừng dựa vào tên exception nội bộ để thiết kế thông báo quá cụ thể cho client.

Test `accountStateFlagsAreConfiguredAsExpected` kiểm tra trực tiếp dữ liệu `UserDetails`, nhằm chắc chắn các account demo **thực sự có trạng thái bất hợp lệ**. Nhưng test đó **chưa đủ**: nếu cơ chế xác thực bỏ qua cờ trạng thái, test data vẫn đúng mà login sẽ sai. Vì thế cần cả kiểm thử **cấu hình trạng thái** và kiểm thử **đăng nhập bị từ chối**.

Sự kiện `disabled`/`locked` trong ví dụ là trạng thái tĩnh được dựng bằng `UserDetails`. Nó **không tự triển khai chính sách khóa tự động sau N lần sai mật khẩu**. Nếu bài toán thực tế đòi hỏi lockout, giới hạn số lần thử, cooldown hoặc admin unlock, đó là một cơ chế vận hành riêng cần service/storage, chống race condition và test bổ sung.

## 6. Phân biệt login failure, authorization failure và CSRF failure

### Login thất bại: redirect /login?error

Trong cơ chế form login, `AuthenticationFailureHandler` được gọi sau thất bại xác thực; `SecurityContext` được làm sạch theo luồng phù hợp, rồi browser được hướng về trang đăng nhập. Vì ví dụ cấu hình `failureUrl("/login?error")` nên cả bad password lẫn disabled/locked/expired đều cho cùng một đường chuyển hướng.

**Không nên định nghĩa “login failure luôn trả 401”**: đó là hành vi phổ biến của HTTP Basic/Bearer API, không phải tất yếu của form login. Không nên định nghĩa “cứ redirect 302 là thành công”; phải kiểm tra destination và security context.

### Đăng nhập thành công nhưng thiếu quyền: 403

Test `loggedInUserStillCannotAccessAdminOnlyUrl` đăng nhập `active` thành công, lấy session rồi gọi `GET /admin`. Do account chỉ có `ROLE_USER`, request bị Spring Security từ chối, thông thường 403. Điều này là bằng chứng về **authorization**, không phủ nhận việc login đúng.

Test `adminCanAccessAdminOnlyUrlAfterLogin` là đối chứng: cùng endpoint với tài khoản `ROLE_ADMIN` được 200 và body `admin-only`. Nếu thiếu đối chứng, một test 403 có thể pass vì endpoint bị chặn vô điều kiện do cấu hình sai.

### POST thiếu CSRF: 403 trước khi kiểm tra password

Bảo vệ CSRF của Spring Security mặc định áp dụng với các HTTP method không “safe” trong ứng dụng Servlet; form login submit bằng POST cần token hợp lệ. `formLogin()` helper từ `spring-security-test` **tự tạo valid CSRF token**, nên test login đúng/sai chạm tới đường xác thực thay vì bị chặn ở CSRF.

Test `postLoginWithoutCsrfIsRejectedBeforePasswordCheck` cố ý dùng:

```java
mvc.perform(post("/login")
        .param("username", "active")
        .param("password", "active-pass"))
    .andExpect(status().isForbidden())
    .andExpect(unauthenticated());
```

Đây là **mảnh test thuộc class ở mục 4**, không phải file Java độc lập. Nó minh họa một 403 phát sinh từ CSRF, **không chứng minh mật khẩu sai**. Nếu cần POST thủ công với MockMvc:

```java
mvc.perform(post("/login")
        .with(csrf())
        .param("username", "active")
        .param("password", "active-pass"));
```

Đoạn trên cần thêm static import `SecurityMockMvcRequestPostProcessors.csrf`, đồng thời phải có `MockMvc`/kỳ vọng kết quả ở ngữ cảnh test. Đừng tắt `csrf` chỉ để các test login pass; hãy gửi token đúng như browser hoặc dùng helper. Với browser truy cập trang `GET /login` mặc định, Spring Security sinh form có cơ chế hỗ trợ CSRF; với login page tự viết, lập trình viên phải xử lý token form phù hợp.

## 7. Một số lỗi kiểm thử dễ khiến kết quả sai

| Sai sót | Vì sao nguy hiểm | Cách kiểm tra/cải thiện |
| --- | --- | --- |
| Chỉ assert `status=302` | Success và failure đều có redirect | Assert cả `redirectedUrl` và `authenticated()/unauthenticated()` |
| Dùng `@WithMockUser` để chứng minh password đúng | Mock user được gắn vào request, không chạy password authentication | Dùng `formLogin()` hoặc HTTP request thật qua filter |
| Test sai password trên user disabled rồi kết luận đã test được disabled | Không tách được lỗi password với account state | Dùng **password đúng** cho tài khoản disabled |
| Bỏ qua CSRF khi `POST /login` | Test có thể nhận 403 trước khi authentication filter chạy | Dùng `formLogin()` hoặc `.with(csrf())` |
| Cấu hình `.csrf(csrf -> csrf.disable())` trong test nhưng production bật CSRF | Test không còn phản ánh security chain thật | Giữ cấu hình thực hoặc ghi rõ phạm vi nếu môi trường test đặc biệt |
| Chỉ assert redirect mà không kiểm tra session lần sau | Có thể bỏ sót lỗi lưu `SecurityContext` | Reuse `MockHttpSession` và thử endpoint yêu cầu login |
| Chỉ test disabled với flag `isEnabled() == false` | Data đúng nhưng provider vẫn có thể bỏ qua flag | Test thêm request đăng nhập bị từ chối |
| Không có positive control | 403/redirect có thể do lỗi cấu hình chặn toàn bộ | Test tài khoản hoạt động/role phù hợp truy cập thành công |
| Chia sẻ session giữa test | Test sai có thể đi theo user từ test trước | Tạo session độc lập cho mỗi test |
| Hard-code thông báo chi tiết “tài khoản bị khóa” trên trang login | Dễ tiết lộ trạng thái username | Dùng thông báo công khai chung, ghi lý do nội bộ an toàn |
| Mock toàn bộ `UserDetailsService` trong test tích hợp | Bỏ qua cấu hình account state/encoder thật | Test end-to-end qua bean thật; chỉ mock phụ thuộc cần thiết |
| Dùng password plaintext trong kho production | Là rủi ro bảo mật, không kiểm tra hash thật | Dùng `PasswordEncoder` và stored hash |
| Coi GET `/login` trả 200 là proof đăng nhập | Trang login hiển thị cho anonymous | Phải gửi form POST và assert `Authentication` sau xử lý |

Để test dễ đọc, đặt tên theo **hành vi**: `correctLoginCreatesAuthenticatedSession`, `wrongPasswordFailsAuthentication`, `unusableAccountCannotLogIn`. Tránh đặt `test1`, `test2` hoặc test quá nhiều điều kiện không liên quan khiến khi fail khó biết nguyên nhân.

## 8. Tách test đơn vị và test tích hợp

### Unit test phù hợp cho logic nào?

Nếu dùng `UserDetailsService` tự viết hoặc service kiểm tra chính sách khóa tài khoản, có thể unit test những điều kiện sau mà không cần HTTP:

- User tồn tại: trả `UserDetails` với username, authorities và hash đúng.
- User bị vô hiệu hóa: `isEnabled()==false`.
- User đang bị khóa: `isAccountNonLocked()==false`.
- Tài khoản/credentials hết hạn: các flag `isAccountNonExpired()` và `isCredentialsNonExpired()`.
- Nếu có chính sách “khóa sau N lần nhập sai”: thử đếm, mốc khóa, reset khi login thành công, hết thời gian khóa, request đồng thời; những yêu cầu này không tự có trong `InMemoryUserDetailsManager`.
- Nếu viết `AuthenticationProvider` riêng: thử đúng loại token `supports`, credential đúng/sai, trạng thái, `null`/exception theo hợp đồng; cần kiểm tra không đưa password/token thô ra kết quả.

Unit test giúp chẩn đoán nhanh logic nội bộ. Nó **không** thay thế test `formLogin()` đi qua `SecurityFilterChain` vì lỗi đăng ký provider, CSRF, failure handler hoặc lưu session chỉ biểu hiện khi tích hợp.

### MockMvc integration test phù hợp cho điều gì?

`@SpringBootTest + @AutoConfigureMockMvc` trong ví dụ khởi động application context và security filters, không cần cổng server thật. Nó phù hợp kiểm tra:

1. POST login với credential đúng/sai, account flags.
2. Redirect tới URL đúng sau thành công/thất bại.
3. Authentication result và session dùng được ở request kế tiếp.
4. URL bảo vệ: anonymous bị hướng về login, user đã login thiếu role nhận 403.
5. CSRF token của form login được xử lý đúng.

Nếu cần kiểm tra HTTP cookie `Set-Cookie`, reverse proxy, HTTPS, browser thực, SameSite hoặc session clustering, bổ sung kiểm thử HTTP/browser/hạ tầng tương ứng. `MockMvc` không tự chứng minh cấu hình deploy, TLS hay mọi đặc điểm của trình duyệt.

### Kiểm thử chống user enumeration

Cả username không tồn tại và password sai nên có **thông báo công khai thống nhất** theo thiết kế. Các test trong bài so sánh status/redirect và tình trạng xác thực. Khi mở rộng production, cân nhắc kiểm tra response body, error code, header, log sanitization, rate limit và tác động của thời gian phản hồi. Không cần ép mọi đường xử lý mất đúng một số mili giây; cần đánh giá rủi ro thực tế và tránh tiết lộ trạng thái tài khoản qua lỗi công khai.

## 9. Nếu ứng dụng dùng HTTP Basic hoặc API token

Bài thực hành chọn **form login** để người học thấy sự khác biệt giữa success và failure redirect. Nếu ứng dụng dùng HTTP Basic cho API REST, cấu hình và assertion phải đổi cho phù hợp. Với HTTP Basic, có thể viết các request kiểu:

```java
// Mảnh mã dành cho một MockMvc test có bật httpBasic():
mvc.perform(get("/home")
        .with(httpBasic("active", "active-pass")))
    .andExpect(status().isOk());

mvc.perform(get("/home")
        .with(httpBasic("active", "wrong-password")))
    .andExpect(status().isUnauthorized());
```

Cần static import `SecurityMockMvcRequestPostProcessors.httpBasic`, `MockMvcRequestBuilders.get` và `MockMvcResultMatchers.status`. Đoạn này **không thuộc ứng dụng form login ở mục 3**: để chạy đúng như trên, `SecurityFilterChain` cần bật `httpBasic(...)` và thiết kế handler phù hợp.

Tương tự, Bearer JWT thường kiểm tra token signature/expiration và claims, không so sánh trực tiếp password ở từng request. Với WebFlux, dùng `WebTestClient` và reactive security test support. Dù cơ chế nào, cấu trúc test vẫn phải tách ba trường hợp: **bằng chứng hợp lệ + account usable**, **bằng chứng sai**, **account unusable**; đồng thời kiểm tra quyền truy cập sau xác thực.

## 10. Lưu ý về security và sản phẩm thực

1. **Không tiết lộ thông tin nhạy cảm:** log thất bại xác thực có thể ghi mã lý do, correlation ID, dấu thời gian và định danh đã giảm nhạy cảm, nhưng không log password, Authorization header, bearer token hay session ID.
2. **Thông báo công khai có chủ đích:** route `/login?error` giữ thông báo chung cho username sai, password sai, disabled/locked/expired; quy trình hỗ trợ tài khoản có thể cung cấp thông tin riêng sau khi xác minh danh tính qua kênh phù hợp.
3. **Không coi mọi thất bại là password sai:** lỗi kho dữ liệu/LDAP timeout là lỗi hệ thống; xử lý theo contract và giám sát riêng, không lặng lẽ biến thành “invalid password”.
4. **Lockout không có sẵn chỉ vì một account bị đánh dấu locked:** thực tế cần chính sách chống brute-force, rate limiting, phát hiện credential stuffing, cooldown và xử lý unlock có kiểm toán.
5. **Form login và session:** xem xét session fixation protection, session timeout, logout, remember-me và lưu `SecurityContext`. Tránh để test phụ thuộc ngầm vào session cũ; đăng nhập một account riêng cho mỗi test.
6. **CSRF:** form login qua POST cần CSRF đúng. Nếu app có token/cookie và browser, không tắt CSRF thiếu căn cứ; phân biệt 403 vì CSRF với 403 vì authorization.
7. **PasswordEncoder:** dùng BCrypt/PBKDF2/scrypt/Argon2 theo chính sách hệ thống; test mô phỏng password đã hash bằng `PasswordEncoder`. Không dùng `{noop}` để chuẩn hóa hành vi production.
8. **MFA/passkeys/OIDC:** đăng nhập đúng password chỉ là một chặng nếu luồng xác thực yêu cầu nhiều yếu tố; test phải bổ sung trạng thái chưa hoàn thành và thành công cuối cùng. Không mặc định username/password đủ cho mọi hệ thống.
9. **Dữ liệu dùng trong test:** không dùng mật khẩu production hoặc dữ liệu người dùng thật; seed test deterministic, cô lập từng test và dọn dữ liệu thay đổi theo chiến lược rõ ràng.
10. **Cấu hình bảo mật giống production:** khi có nhiều `SecurityFilterChain` hoặc `securityMatcher`, test cần xác nhận request đi qua chain dự kiến. Một `@WithMockUser` trong test không thay thế chứng cứ rằng authentication filter/provider đã được cấu hình đúng.

## 11. Bài tập tự luyện

1. Nếu chỉ có `mvc.perform(formLogin(...)).andExpect(status().isFound())`, vì sao không thể kết luận login đã thành công?
2. Khi user `active` gửi password sai, những matcher nào chứng minh thất bại đúng nghĩa hơn một assertion status đơn lẻ?
3. Vì sao trường hợp `disabled` cần dùng password **đúng** để kiểm tra trạng thái tài khoản?
4. `UserDetails.isAccountNonLocked() == false` nghĩa là gì? So sánh với builder `accountLocked(true)`.
5. Nếu request login đúng username/password nhưng thiếu CSRF token, vì sao 403 không có nghĩa password bị từ chối?
6. Sau login thành công, cách nào trong `MockMvc` giúp xác nhận request `GET /home` kế tiếp nhận được danh tính từ session?
7. Tại sao `@WithMockUser(username="active")` không dùng để khẳng định BCrypt/password check hoạt động?
8. Vì sao user `active` vẫn có thể nhận 403 khi truy cập `/admin`, và case này khác `AuthenticationException` như thế nào?
9. Làm sao phát hiện một test “disabled login denied” đang pass vì hệ thống chặn **mọi** tài khoản? Cần positive control nào?
10. Nếu muốn thật sự khóa user sau năm lần sai liên tiếp, chỉ dùng `.accountLocked(true)` trong dữ liệu test đã kiểm tra chính sách ấy chưa? Cần thêm những tình huống nào?
11. Nếu đổi sang HTTP Basic, assertion status và redirect trong ba case chính thay đổi như thế nào?
12. Các kiểm tra nào cần bổ sung nếu login có captcha, MFA hoặc phụ thuộc vào dịch vụ identity bên ngoài?

**Hướng giải:** (1) cả success/failure đều 302; (2) `redirectedUrl("/login?error")` + `unauthenticated()`; (3) cô lập nguyên nhân trạng thái; (4) false tức tài khoản bị khóa; (5) lỗi phát sinh ở `CsrfFilter`; (6) lấy `MockHttpSession` từ login rồi reuse; (7) mock user bỏ qua xác minh mật khẩu; (8) authentication thành công nhưng authorization thiếu role; (9) login đúng và truy cập tài nguyên phải có test 200; (10) cần logic đếm, khóa, mở khóa, mốc thời gian và concurrency; (11) Basic thường 200 cho request hợp lệ, 401 cho credential sai/không sử dụng được, không dùng failure redirect; (12) thiết kế test theo đúng các bước bổ sung của authentication flow.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html)
- [Spring Security 6.5 — Testing Form Based Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — MockMvc Security Result Matchers](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/result-matchers.html)
- [Spring Security 6.5 — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security 6.5 — Running as a User in MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)