# Thực hành tổng hợp: Xây đăng nhập biểu mẫu với tài khoản trong bộ nhớ rồi chuyển sang kho dữ liệu

## 1. Mục tiêu bài thực hành và sản phẩm cuối cùng

Bài thực hành này xây dựng **đăng nhập qua biểu mẫu HTML (form login)** cho ứng dụng Spring Boot, khởi đầu bằng hai tài khoản lưu trong RAM thông qua `InMemoryUserDetailsManager`, sau đó **thay riêng nguồn tài khoản** bằng `JdbcUserDetailsManager` và cơ sở dữ liệu H2. Người dùng vẫn đăng nhập tại cùng URL, dùng cùng mẫu HTML, cùng quy tắc phân quyền và cơ chế session/CSRF; thay đổi được giới hạn ở phần **lưu và truy xuất UserDetails**. Sau khi kiểm thử bản H2, bài chỉ rõ cách chuyển kiến trúc sang cơ sở dữ liệu thật với migration, secret manager, unique constraints và vận hành an toàn.

Môi trường tham chiếu: **Java 17+, Spring Boot 3.x, Spring Security 6.x (ưu tiên API của 6.5), Spring MVC/Servlet, Gradle**, Thymeleaf, JDBC, H2 cho local demo và JUnit 5/MockMvc. Không trộn đoạn Servlet `HttpSecurity` với WebFlux `ServerHttpSecurity`. Chọn dòng Spring Boot 3.x tương thích Spring Security 6.x theo BOM; không tự ép một spring-security version không được Boot quản lý.

Sau khi hoàn thành:

- Mở `GET /login` thấy form HTML tự xây, `POST /login` được filter của Spring Security xử lý (không viết controller tự kiểm password).
- Alice có `ROLE_USER` đăng nhập được, xem `/dashboard` nhưng bị từ chối tại `/admin`; Admin có `ROLE_ADMIN` xem được cả hai.
- Password được mã hóa bằng `BCryptPasswordEncoder`; không lưu plain text vào database. `PasswordEncoder.matches`/`DaoAuthenticationProvider` xử lý so khớp, không phải controller.
- Đăng nhập thiếu/sai mật khẩu không tạo principal được xác thực; CSRF được giữ trên form login/logout.
- Chạy profile `memory` để dùng `InMemoryUserDetailsManager`, rồi chuyển profile `jdbc` để dùng schema `users` + `authorities` và `JdbcUserDetailsManager` mà không thay controller/template/authorization.
- Có bộ kiểm thử HTTP dùng `MockMvc` cho cả hai profiles và bộ kiểm tra dữ liệu JDBC; biết giới hạn của H2 in-memory, quy trình lên PostgreSQL/MySQL thật.

**Quan trọng:** ví dụ chứa username/password công khai chỉ dùng để học trên máy local. Không deploy các fixture này ra internet, không bật H2 Console công khai, không ghi password/headers/session cookie vào log. Với ứng dụng thật, tạo người dùng qua quy trình đăng ký đã xác minh, password reset/lock/rate-limit, chính sách MFA và audit.

## 2. Kiến trúc: đổi UserDetailsService, không đổi điểm bảo vệ

Luồng chính:

```text
Browser
  GET /dashboard (chưa đăng nhập)
       |
       v
Spring Security AuthorizationFilter
  -> yêu cầu authentication
  -> LoginUrlAuthenticationEntryPoint
  -> 302 Location: /login
       |
       v
GET /login -> Controller -> Thymeleaf login.html
       |
       | POST /login {username, password, _csrf}
       v
UsernamePasswordAuthenticationFilter
       |
       v
AuthenticationManager / DaoAuthenticationProvider
       | 1. loadUserByUsername(username)
       v
UserDetailsService ----------------------+
   |                                    |
   | profile=memory                      | profile=jdbc
   v                                    v
InMemoryUserDetailsManager       JdbcUserDetailsManager
   |                                    |
   | Java objects in RAM                | DataSource / SQL
   |                                    | tables users, authorities
   +-----------------+------------------+
                     |
                     v
             UserDetails(username, encoded password,
                         enabled, authorities)
                     |
                     v
       PasswordEncoder.matches(raw, encoded)
                     |
             +-------+--------+
             |                |
           SUCCESS          FAILURE
             |                |
      SecurityContext    Clear/fail auth
      session strategy   redirect /login?error
             |
      302 /dashboard
             |
      /admin -> hasRole("ADMIN") -> 200 or 403
```

**Phân tách trách nhiệm:**

| Thành phần | Vai trò | Không nên làm |
| --- | --- | --- |
| `SecurityFilterChain` | Bảo vệ URL, bật form login/CSRF/logout/session | Tự chứa SQL truy vấn người dùng |
| `UsernamePasswordAuthenticationFilter` | Đọc trường `username/password` từ POST /login | Để controller tự tạo authenticated token theo request |
| `DaoAuthenticationProvider` | Lấy UserDetails, kiểm password hash và trạng thái tài khoản | So raw password bằng `String.equals` |
| `UserDetailsService` | Tải account, quyền và trạng thái | Nhận raw password, trả account tùy tiện |
| `InMemoryUserDetailsManager` | Tra cứu/management users trong một JVM | Coi là kho tài khoản bền vững production |
| `JdbcUserDetailsManager` | Tra cứu/quản lý users trong cơ sở dữ liệu quan hệ | Mặc định hiểu mọi cấu trúc JPA custom/tenant |
| `PasswordEncoder` | Hash và kiểm mật khẩu | Lưu `{noop}`/raw password production |
| `SecurityContextRepository`/HttpSession | Giữ trạng thái authenticated qua request | Tự thu hồi mọi JWT/refresh token ở IdP |
| `@Controller`/Thymeleaf | Hiển thị trang login/dashboard và thông điệp | Tự tra DB để so password ở `POST /login` |

Một user tồn tại trong DB **không đồng nghĩa login thành công**: provider còn kiểm mật khẩu, `enabled` và những chính sách authentication khác. Một user đăng nhập thành công **không đồng nghĩa có ROLE_ADMIN**: authorization được kiểm riêng.

## 3. Tạo project, dependencies và cấu trúc thư mục

Dùng Spring Initializr tạo **Spring Boot 3.x**, Gradle Groovy, Java 17, dependencies:

- Spring Web (Servlet MVC), Spring Security;
- Thymeleaf;
- Spring JDBC và H2 Database cho phần thực hành dữ liệu;
- Spring Boot Test + Spring Security Test.

Nếu đã có Gradle wrapper và plugin Spring Boot, phần dependencies tương đương:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không cần tự ghi version cho các dependencies trên nếu Spring Boot BOM quản lý chúng. Cấu trúc file dự kiến:

```text
src/
  main/
    java/com/example/formlogin/
      FormLoginApplication.java
      SecurityConfig.java
      PageController.java
    resources/
      application.yml
      application-jdbc.yml
      schema-jdbc.sql
      templates/
        login.html
        dashboard.html
        admin.html
  test/java/com/example/formlogin/
      FormLoginMemoryTest.java
      FormLoginJdbcTest.java
```

**Chú ý hai profiles:** `memory` và `jdbc` là hai chế độ **loại trừ lẫn nhau**. Không chạy `--spring.profiles.active=memory,jdbc`, vì sẽ tạo hai bean cung cấp `UserDetailsService` và khiến lựa chọn provider/seed không rõ ràng. Khi chạy mà không chọn profile, ứng dụng ví dụ không được coi là đã chọn nguồn account mong muốn; hãy luôn chỉ định một profile và kiểm Bean thực được tạo. `jdbc` trong bài sử dụng H2 in-memory **chỉ cho demo**, không phải cấu hình database thật.

## 4. Tạo lớp khởi động ứng dụng

File `src/main/java/com/example/formlogin/FormLoginApplication.java`:

```java
package com.example.formlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormLoginApplication.class, args);
    }
}
```

Đặt các lớp còn lại trong cùng package `com.example.formlogin` để component scanning tìm thấy `@Configuration` và `@Controller`. Nếu tách package, bảo đảm nằm dưới base package của `@SpringBootApplication` hoặc cấu hình scan rõ ràng.

## 5. Viết SecurityFilterChain: một chính sách dùng chung cho memory và JDBC

File `src/main/java/com/example/formlogin/SecurityConfig.java`:

```java
package com.example.formlogin;

import javax.sql.DataSource;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/css/**").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .failureUrl("/login?error")
                .defaultSuccessUrl("/dashboard", false)
                .permitAll())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .permitAll())
            // Không tắt CSRF; Spring Security giữ CSRF protection.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    @Profile("memory")
    UserDetailsService memoryUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();
        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    @Profile("jdbc")
    JdbcUserDetailsManager jdbcUsers(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }

    @Bean
    @Profile("jdbc")
    CommandLineRunner seedJdbcDemoUsers(
            JdbcUserDetailsManager users, PasswordEncoder encoder) {
        return args -> {
            if (!users.userExists("alice")) {
                users.createUser(User.withUsername("alice")
                    .password(encoder.encode("alice-pass"))
                    .roles("USER")
                    .build());
            }
            if (!users.userExists("admin")) {
                users.createUser(User.withUsername("admin")
                    .password(encoder.encode("admin-pass"))
                    .roles("USER", "ADMIN")
                    .build());
            }
        };
    }
}
```

Đây là **cấu hình hoàn chỉnh cho demo**, với các lưu ý bắt buộc:

1. Các `@Bean` dưới hai `@Profile` khác nhau tạo ra **một nguồn UserDetails tại mỗi lượt chạy**. `JdbcUserDetailsManager` triển khai `UserDetailsService`/`UserDetailsManager`, vì vậy bộ phận authentication của Spring vẫn dùng `DaoAuthenticationProvider` như trường hợp in-memory.
2. `PasswordEncoder` dùng BCrypt; mỗi lần chạy profile `memory` có thể sinh salt/hash khác, nhưng `PasswordEncoder.matches("alice-pass", storedHash)` vẫn đúng. **Không so hai BCrypt hashes bằng equals**, vì salt khác nhau.
3. Trong `.roles("USER")`, Spring tạo `ROLE_USER`. `.hasRole("ADMIN")` đòi authority `ROLE_ADMIN`. Khi dùng JDBC, cột `authorities.authority` phải chứa **tên đầy đủ** như `ROLE_ADMIN`.
4. Form Login xử lý **POST /login**, vì vậy controller của chúng ta chỉ cung cấp **GET /login**. Không tạo POST mapping khác giành URL này hoặc tự so username/password.
5. `defaultSuccessUrl("/dashboard", false)` có nghĩa dùng dashboard làm đích mặc định, nhưng nếu user ban đầu bị redirect khi truy cập URL protected, Spring Security có thể ưu tiên saved request. Vì vậy không assert mọi login thành công luôn redirect đúng dashboard khi có RequestCache.
6. `invalidateHttpSession(true)` xử lý session logout hiện tại; nó không tự logout mọi thiết bị, thu hồi remember-me cookie tuỳ cấu hình hoặc revoke OAuth access/refresh tokens. Ví dụ chưa bật remember-me hay OAuth2.
7. `seedJdbcDemoUsers` chỉ để local chạy được ngay. **Đừng giữ code tự tạo tài khoản với password công khai trong production**; một hệ thống thật dùng migration/provisioning được kiểm soát, account enrollment và secret management.
8. Khi có một bean `UserDetailsService` duy nhất và `PasswordEncoder`, Spring Security cấu hình authentication dựa trên các bean đó trong trường hợp username/password tiêu chuẩn. Nếu project có AuthenticationProvider/AuthenticationManager tự khai báo, hãy kiểm thiết lập provider thật thay vì giả định auto-configuration luôn chọn đúng bean.

### Không nhầm UserDetailsService với UserDetailsManager

`UserDetailsService` chỉ hứa phương thức `loadUserByUsername(String)`. `InMemoryUserDetailsManager` và `JdbcUserDetailsManager` còn có chức năng quản lý user (create/update/delete) qua `UserDetailsManager`. Đó là lý do code seed JDBC gọi `users.createUser(...)`, nhưng controller login chỉ cần UserDetailsService. Trong production không đưa toàn bộ chức năng tạo user ra endpoint công khai bằng cách inject `UserDetailsManager` vô điều kiện.

## 6. Viết controller: trang HTML, không đụng vào POST /login

File `src/main/java/com/example/formlogin/PageController.java`:

```java
package com.example.formlogin;

import java.security.Principal;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/")
    public String home() {
        return "redirect:/dashboard";
    }

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/dashboard")
    public String dashboard(Principal principal, Model model) {
        model.addAttribute("username", principal.getName());
        return "dashboard";
    }

    @GetMapping("/admin")
    public String admin(Principal principal, Model model) {
        model.addAttribute("username", principal.getName());
        return "admin";
    }
}
```

Vì `/dashboard` và `/admin` được bảo vệ bởi security chain, code chỉ gọi `principal.getName()` sau khi Spring Security cho truy cập. Trong ứng dụng phức tạp, đừng lấy username từ query parameter và tin nó là principal. Các quyền trên từng object/resource phải được kiểm ở service layer nữa, không chỉ dựa vào URL.

**Không có controller POST /login** trong dự án mẫu. Request đăng nhập được xử lý bởi `UsernamePasswordAuthenticationFilter`. Nếu bạn thấy controller POST /login đang được gọi để tự query password, có thể filter chain/path của bạn bị tách hoặc code đang bypass Spring Security.

## 7. Tạo biểu mẫu Thymeleaf đúng CSRF và tên trường

### 7.1. templates/login.html

File `src/main/resources/templates/login.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
    <h1>Đăng nhập</h1>

    <p th:if="${param.error}">
        Tên đăng nhập hoặc mật khẩu không hợp lệ.
    </p>
    <p th:if="${param.logout}">
        Bạn đã đăng xuất.
    </p>

    <form th:action="@{/login}" method="post">
        <label for="username">Tên tài khoản</label>
        <input id="username" name="username" type="text"
               autocomplete="username" required>

        <label for="password">Mật khẩu</label>
        <input id="password" name="password" type="password"
               autocomplete="current-password" required>

        <button type="submit">Đăng nhập</button>
    </form>
</body>
</html>
```

**Chi tiết phải kiểm:**

- `th:action="@{/login}"` định tuyến đúng context path và hợp tác với Spring MVC/Thymeleaf để đưa CSRF hidden input vào form POST khi cấu hình tích hợp Security và CSRF đúng. Kiểm HTML render thật có field `_csrf`. Nếu không có, request POST sẽ bị Spring CSRF filter trả **403**, không phải password sai.
- Parameter mặc định đúng là `username` và `password`. Nếu bạn đổi tên input, phải đổi `usernameParameter(...)`/`passwordParameter(...)` tương ứng trong config.
- `th:if="${param.error}"` hiển thị thông báo chung, không nêu “user không tồn tại” hay “đã tồn tại nhưng mật khẩu sai” để tránh dò username. Ngoài ra cần rate limit, backoff, giám sát và MFA theo rủi ro; generic message **không tự ngăn brute force**.
- Không đặt password vào GET query, localStorage hoặc hidden fields. `autocomplete="current-password"` cho phép password manager hoạt động đúng; không cấm copy/paste mật khẩu vô cớ.
- HTML template nằm trong `resources/templates` để Thymeleaf render. Nếu đặt file trong static và không có controller, `/login` có thể 404 hoặc CSRF integration không như dự kiến.

### 7.2. templates/dashboard.html

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Dashboard</title></head>
<body>
    <h1>Trang cá nhân</h1>
    <p>Xin chào <strong th:text="${username}">user</strong></p>

    <a th:href="@{/admin}">Trang quản trị</a>

    <form th:action="@{/logout}" method="post">
        <button type="submit">Đăng xuất</button>
    </form>
</body>
</html>
```

`th:text` escape dữ liệu đầu vào thành text, giảm nguy cơ XSS khi hiển thị username. Không dùng `th:utext` cho dữ liệu chưa tin. Form logout dùng **POST** cùng CSRF thay vì liên kết GET đổi state. Đừng tắt CSRF để cho logout bằng GET trong ứng dụng có cookie-based session.

### 7.3. templates/admin.html

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Quản trị</title></head>
<body>
    <h1>Trang quản trị</h1>
    <p>Tài khoản: <span th:text="${username}">admin</span></p>
    <a th:href="@{/dashboard}">Quay lại dashboard</a>
</body>
</html>
```

Việc template có đường link `/admin` không có nghĩa Alice được quyền truy cập. Server kiểm `hasRole("ADMIN")`; user không có quyền sẽ nhận 403. **Ẩn menu hoặc link trong giao diện không phải authorization**.

## 8. Chạy lần 1: tài khoản trong bộ nhớ

Chạy từ thư mục project có Gradle wrapper:

```bash
./gradlew bootRun --args='--spring.profiles.active=memory'
```

Với Windows PowerShell/cmd có thể dùng:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=memory"
```

Mở `http://localhost:8080/login` **trên máy local**. Trong môi trường triển khai thực phải dùng HTTPS; HTTP trên localhost chỉ là lab. Tài khoản thử nghiệm:

| Account | Mật khẩu demo | Quyền | Hành vi |
| --- | --- | --- | --- |
| `alice` | `alice-pass` | `ROLE_USER` | Login → dashboard; GET /admin → 403 |
| `admin` | `admin-pass` | `ROLE_USER` và `ROLE_ADMIN` | Login → dashboard; GET /admin → 200 |
| `ghost` | bất kỳ | Không tồn tại | Login fail → trang /login?error |
| `alice` | sai mật khẩu | Account tồn tại | Login fail, không authenticated |

Trình tự browser:

1. Ở cửa sổ ẩn danh, mở trực tiếp `/dashboard`. Nếu chưa login, Spring Security redirect `302` đến `/login`. Trang login tự render `200` không phải dashboard thành công.
2. Login `alice/alice-pass` bằng form; sau redirect, trang dashboard hiển thị “Xin chào alice”.
3. Mở `/admin`: kỳ vọng 403 do thiếu `ROLE_ADMIN`. Đó là lỗi authorization, **không phải** password sai.
4. POST logout bằng nút trên trang dashboard. Sau đó dùng URL `/dashboard` phải yêu cầu login mới.
5. Login `admin/admin-pass`, mở `/admin` thấy trang admin.
6. Trong cửa sổ riêng, nhập `ghost`/password sai. Đảm bảo không có quyền authenticated và thông báo không tiết lộ user có tồn tại hay không.

**Đối chiếu thật:** nhìn Network tab để thấy POST /login (CSRF), status 302, Set-Cookie session, redirect target. Nếu DevTools chỉ hiển thị 200 từ trang cuối do tự follow redirects, đừng kết luận POST trả 200.

### Những đặc tính của bộ nhớ

`InMemoryUserDetailsManager` lưu accounts trong một JVM. Mỗi lần restart, bean tái tạo hai account theo code; nếu bạn thêm account lúc runtime mà không ghi ra kho bền vững, account đó sẽ biến mất sau restart. Hai pod mỗi pod có memory riêng không tự chia sẻ users; đổi password/disable ở pod A có thể không được pod B biết. Đây là lý do cần database/identity store thực khi đi production.

## 9. MockMvc cho profile memory: kiểm đủ authentication, authorization và CSRF

Tạo file `src/test/java/com/example/formlogin/FormLoginMemoryTest.java`:

```java
package com.example.formlogin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("memory")
class FormLoginMemoryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginPageIsPublic() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk());
    }

    @Test
    void aliceCanAuthenticate() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("alice"))
                .andExpect(redirectedUrl("/dashboard"));
    }

    @Test
    void nonexistentAccountDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "ghost")
                    .param("password", "irrelevant"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(unauthenticated());
    }

    @Test
    void missingCsrfIsRejectedBeforePasswordCheck() throws Exception {
        mvc.perform(post("/login")
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(status().isForbidden());
    }

    @Test
    void aliceCannotAccessAdminButCanSeeDashboard() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk());
        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenAdminPage() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "admin")
                    .param("password", "admin-pass"))
                .andExpect(authenticated().withUsername("admin"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();
        mvc.perform(get("/admin").session(session))
                .andExpect(status().isOk());
    }

    @Test
    void logoutInvalidatesCurrentSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(authenticated())
                .andReturn();
        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection());

        assertThat(session.isInvalid()).isTrue();
    }
}
```

Chạy:

```bash
./gradlew test --tests com.example.formlogin.FormLoginMemoryTest
```

**Kiểm thử này có giá trị gì?** `post("/login").with(csrf())` đưa request qua filter login và PasswordEncoder thực, không tạo principal giả. `SecurityMockMvcResultMatchers.authenticated()` kiểm Spring Security Context sau request; `get("/admin").session(session)` kiểm sử dụng session qua request tiếp theo, không chỉ HTTP 302 của login.

**Giới hạn:** MockMvc dùng mock servlet environment, không chứng minh cookie thực hoặc reverse proxy/session store trên production. Thêm browser/E2E test cho `Set-Cookie`, HTTPS, session fixation, idle timeout và concurrent sessions. Trong ứng dụng có RequestCache/saved request hoặc custom success handler, expected redirect target có thể khác, nhưng phải assert đúng cấu hình đã chọn.

### Ghi chú về mock authentication

`@WithMockUser` hữu ích kiểm policy controller/role nhưng **không gọi** `InMemoryUserDetailsManager`, không so mật khẩu, không đi qua `POST /login`. Đừng dùng test `@WithMockUser(roles="ADMIN")` để tuyên bố đã chứng minh database login hoạt động. Với test authentication, cần submit credential thật qua provider và quan sát session/principal.

## 10. Chạy lần 2: thay InMemoryUserDetailsManager bằng JDBC

Lúc này **không đổi** các class `PageController`, `SecurityFilterChain`, ba template, hay các URL. Chúng ta bổ sung schema và chạy profile `jdbc` để bean `jdbcUsers(DataSource)` thay bean `memoryUsers(...)`. Điều này chính là ý nghĩa của “chuyển sang kho dữ liệu”: thay provider của account lookup, **giữ authentication protocol và authorization policy nhất quán**.

### 10.1. Schema SQL đúng mặc định JdbcUserDetailsManager

File `src/main/resources/schema-jdbc.sql`:

```sql
CREATE TABLE users (
    username VARCHAR(50) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_authorities_user
        FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uk_user_authority
        UNIQUE (username, authority)
);
```

Lược đồ này phù hợp với các **default queries** của `JdbcUserDetailsManager`/`JdbcDaoImpl`:

```sql
SELECT username, password, enabled
FROM users
WHERE username = ?;

SELECT username, authority
FROM authorities
WHERE username = ?;
```

Không được viết query nối chuỗi username vào SQL; dùng parameter binding qua JDBC. Cột `password` chứa password đã được mã hóa bằng PasswordEncoder, không phải raw text; `authority` chứa `ROLE_USER`, `ROLE_ADMIN`. Constraint UNIQUE tránh lưu trùng cùng một authority, khóa ngoại ngăn role mồ côi. Tùy database và collation, `alice` và `Alice` có thể được so khác nhau; production phải có normalized identity policy và unique key theo tenant/account.

**Lưu ý:** schema chuẩn Spring Security trong tài liệu thường dùng kiểu `varchar_ignorecase` cho HSQL/H2; SQL ở trên dùng kiểu dễ đọc/portable hơn cho H2 để minh họa contract, nhưng khi port tới PostgreSQL/MySQL phải điều chỉnh DDL/constraints phù hợp hệ quản trị. Đây không phải bộ migration đầy đủ cho sản phẩm có lockout/MFA/audit.

### 10.2. application-jdbc.yml cho môi trường local H2

File `src/main/resources/application-jdbc.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:formlogin-demo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
      schema-locations: classpath:schema-jdbc.sql
```

Khi profile `jdbc` bật, Spring Boot tạo H2 in-memory datasource và chạy SQL schema trước khi CommandLineRunner seed user ở `SecurityConfig`. `JdbcUserDetailsManager.createUser(...)` dùng SQL insert vào `users`/`authorities`; việc password BCrypt có salt được thực hiện ở Java khi seed.

**Không đưa application-jdbc.yml trên vào production như cấu hình database thực.** H2 `mem:` chỉ sống cùng tiến trình; sau restart dữ liệu biến mất. `spring.sql.init.mode=always` chạy schema DDL mỗi startup, có thể gây lỗi hoặc phá quy trình migration ở DB đã tồn tại. Production dùng datasource thật và Flyway/Liquibase với migration versioned, **không tự tạo schema + seed tài khoản demo khi khởi động**.

### 10.3. Khởi động với JDBC profile

```bash
./gradlew bootRun --args='--spring.profiles.active=jdbc'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=jdbc"
```

Kỳ vọng cả Alice và Admin vẫn đăng nhập bằng form như trước:

- Alice đăng nhập → dashboard 200; admin route 403.
- Admin đăng nhập → admin route 200.
- User ghost/password sai vẫn bị từ chối.
- CSRF/logout/session behavior không đổi.
- Nếu restart app H2 in-memory, schema được tạo mới và runner seed lại hai users; chứng tỏ đang dùng DB trong RAM chứ chưa phải persistence qua restart.

Đây là **test regression hữu ích**: đổi nguồn users mà không được làm hỏng login routes, role mapping, CSRF hoặc behavior của session.

## 11. JDBC tests: kiểm dữ liệu và tái chạy cùng HTTP login

Tạo file `src/test/java/com/example/formlogin/FormLoginJdbcTest.java`:

```java
package com.example.formlogin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("jdbc")
class FormLoginJdbcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    JdbcUserDetailsManager users;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void jdbcUsersExistAndPasswordIsHashed() {
        assertThat(users.userExists("alice")).isTrue();
        assertThat(users.userExists("admin")).isTrue();
        assertThat(users.userExists("ghost")).isFalse();

        UserDetails alice = users.loadUserByUsername("alice");
        assertThat(alice.getPassword()).isNotEqualTo("alice-pass");
        assertThat(encoder.matches(
                "alice-pass", alice.getPassword())).isTrue();
        assertThat(alice.getAuthorities().stream()
                .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())))
                .isTrue();

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM users WHERE username = ?",
                Integer.class, "alice");
        assertThat(rows).isEqualTo(1);
    }

    @Test
    void jdbcLoginStillUsesSameFormAndRules() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk());
        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void jdbcAdminHasAdminRole() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "admin")
                    .param("password", "admin-pass"))
                .andExpect(authenticated().withUsername("admin"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/admin").session(session))
                .andExpect(status().isOk());
    }

    @Test
    void jdbcMissingUserAndWrongPasswordFail() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "ghost")
                    .param("password", "any"))
                .andExpect(unauthenticated());

        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "wrong"))
                .andExpect(unauthenticated());
    }

    @Test
    void jdbcLoginStillRequiresCsrf() throws Exception {
        mvc.perform(post("/login")
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(status().isForbidden());
    }
}
```

Chạy kiểm cả hai profiles:

```bash
./gradlew test --tests com.example.formlogin.FormLoginMemoryTest
./gradlew test --tests com.example.formlogin.FormLoginJdbcTest
```

Nếu chạy tất cả tests trong một lệnh:

```bash
./gradlew test
```

**Trọng tâm kiểm thử:** cần chứng minh khi chuyển từ in-memory sang JDBC thì account **thật sự được load từ DB**, password hash kiểm được bằng PasswordEncoder và role `ROLE_ADMIN` không bị mất. Việc controller vẫn trả 200 là chưa đủ, vì app có thể vô tình dùng bean memory vẫn còn trên classpath.

**Về SQL:** query `JdbcTemplate.queryForObject(..., "alice")` dùng parameter binding; không xây SQL bằng cách nối giá trị username vào string. Test `users.userExists("ghost")` không tự chứng minh public login không lộ user existence qua timing/error messages; cần thêm security/penetration test theo chính sách.

### Bắt lỗi một provider còn chạy “lén”

Nếu Spring Boot tự cấu hình một generated user hoặc một AuthenticationProvider tùy biến không theo profile, test HTTP có thể pass/sai bất ngờ. Hãy assert context có đúng bean `JdbcUserDetailsManager` ở jdbc profile và **không có in-memory UserDetailsService** được nạp; tương tự ngược lại ở memory profile. Kiểm logs khởi động có thông báo generated security password là dấu hiệu bean users mong muốn chưa được đăng ký đúng.

## 12. Khác biệt rất quan trọng giữa H2 demo và kho dữ liệu production

| Vấn đề | `memory` | `jdbc` H2 in-memory trong lab | RDBMS production |
| --- | --- | --- | --- |
| Tài khoản sống ở đâu? | Heap JVM | H2 engine trong process | PostgreSQL/MySQL/Oracle hoặc managed DB |
| Restart service | Tái tạo từ code | Tái tạo schema và seed demo | Dữ liệu phải bền vững qua restart/deploy |
| Multi-node sharing | Không | Không, trừ external H2 service không khuyến nghị | Có, dùng chung DB và connection pool an toàn |
| Mật khẩu | BCrypt trong UserDetails | BCrypt hash ở `users.password` | BCrypt/Argon2/DelegatingEncoder với migration policy |
| Roles | Trong Java fixture | Bảng `authorities` | Bảng role/permission chuẩn, scope/tenant nếu cần |
| Schema changes | Đổi code | `schema-jdbc.sql` mỗi startup | Flyway/Liquibase versioned migrations |
| Account locking/MFA | Cần tự xây | Schema mặc định chỉ có `enabled` | Cần model mở rộng hoặc provider checks |
| Backup/DR | Không | Không như persistent DB | Backup, restore, audit, encryption-at-rest |
| Secret management | Password demo trong code | Password demo trong CommandLineRunner | Secret manager, enrollment, reset/recovery |
| Session persistence | Mặc định HttpSession riêng | Vẫn HttpSession riêng, **không nằm trong users DB** | Cần Spring Session riêng nếu session sharing/revoke xuyên node |

**Chuyển users sang DB không tự chuyển HTTP sessions sang DB.** Authentication state ở `SecurityContext`/HttpSession vẫn có lifecycle riêng; nếu chạy nhiều server replicas và cần share sessions, cân nhắc Spring Session Redis/JDBC. Không đồng nhất bảng `users`/`authorities` với bảng lưu session của Spring Session.

### Hạn chế của JdbcUserDetailsManager mặc định

Schema mặc định chỉ có `users.username`, `password`, `enabled` và `authorities`. Nó không biểu diễn đầy đủ tenant, account locked-until, password rotation history, MFA credentials, email verified hay arbitrary account statuses. Khi cần domain model phức tạp, có thể viết custom `UserDetailsService` dựa trên repository/JPA, nhưng **vẫn giữ contract loadUserByUsername** và để DaoAuthenticationProvider/PasswordEncoder xử lý password. Không tự query role từ request.

## 13. Di chuyển sang PostgreSQL/MySQL thật: từng bước an toàn

Phần này là **quy trình sản phẩm**, không phải file thay thế trực tiếp vào project H2 demo. Nó làm rõ những việc phải hoàn thiện trước khi gọi là “đã chuyển sang kho dữ liệu”.

### 13.1. Dùng migration có phiên bản, không seed plaintext từ code

1. Tạo RDBMS riêng cho môi trường và service account chỉ có quyền cần thiết. Bật TLS cho kết nối, phân quyền đọc/ghi/migration khác nhau khi có thể, backup/restore test.
2. Tạo DDL bằng **Flyway/Liquibase** trong `db/migration/V1__create_auth_tables.sql` theo dialect và user/authority schema của dự án; có indexes/unique constraints, foreign keys và username normalization policy rõ.
3. Dùng `spring.sql.init.mode=never` trong production khi Flyway/Liquibase chịu trách nhiệm migration; không chạy `schema-jdbc.sql` với `CREATE TABLE` mỗi lần restart. Không bật H2 console cho production.
4. Bỏ bean `seedJdbcDemoUsers(...)` hoặc giới hạn bean ấy chỉ xuất hiện trong local/test profile. Account thật được tạo bằng workflow đăng ký quản trị, password reset/verify email, provisioning IdP, IAM hoặc migration job có audit.
5. Cấp credential kết nối DB qua secret manager/environment variables (không commit `spring.datasource.password` vào Git). Rotate DB password theo runbook và không log URL có secret.
6. Cấu hình connection pool và timeout an toàn; lỗi DB không được làm login **fail-open** (cấp guest/default user) hoặc tự fallback sang account in-memory.
7. Test migrations trên snapshot dữ liệu đã ẩn danh, rồi canary service; chỉ cut over khi dữ liệu/roles/password encoders đều chính xác.
8. Rollback có giới hạn: backup/schema compatibility và change plan, không “rollback” bằng việc quay về hardcoded admin credentials.

Ví dụ **cấu hình minh họa** cho môi trường production dùng PostgreSQL (cần thêm JDBC driver và Flyway dependencies tương thích BOM):

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal.example:5432/authdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  sql:
    init:
      mode: never
  flyway:
    enabled: true
```

**Đoạn này không đủ để production chạy:** cần driver PostgreSQL, schema migrations, TLS/truststore, datasource permissions, startup readiness, rate limiting, metrics và môi trường quản lý secrets. Hostname `db.internal.example` chỉ để minh họa. Boot chỉ cấu hình Flyway khi có dependency và schema/migrations phù hợp. Đặc biệt, bean `@Profile("jdbc")` của lab có CommandLineRunner seed: **không kích hoạt nguyên profile `jdbc` đó trên production**; tạo profile/config riêng cho môi trường thật và bỏ code seed. Nếu bạn dùng cùng class, điều chỉnh `@Profile` rõ để chỉ một UserDetailsService active và không tạo users demo.

### 13.2. Migration mật khẩu phải giữ nguyên khả năng xác minh

- Khi **đã có password hash tương thích**, có thể migrate **hash** và metadata/algorithm ID theo chính sách; không cần biết plaintext. Không gọi `encoder.encode(existingHash)`, vì như vậy hash được mã hóa lại như một mật khẩu mới và người dùng không thể login với password cũ.
- Nếu dùng `DelegatingPasswordEncoder`, stored values có thể mang prefix như `{bcrypt}...` để chọn encoder phù hợp. Trong demo dùng `BCryptPasswordEncoder` trực tiếp nên database hash không cần prefix; **đừng tự ý thêm `{bcrypt}` rồi tiếp tục dùng BCryptPasswordEncoder trực tiếp nếu code đó không hiểu prefix**.
- Nếu dùng thuật toán cũ yếu (MD5/SHA-1/legacy), xem xét staged upgrade khi login với encoder hỗ trợ legacy theo chính sách, force password reset hoặc migrate có kiểm soát. Không bỏ bước verify hay chấp nhận plaintext vì “không khớp hash”.
- Không sinh user/role mới từ request headers hoặc từ tên folder trong DB. Giữ immutable account ID/tenant mapping và UNIQUE constraints; migration phải phát hiện username trùng/collision do lowercase/Unicode collation.
- Kiểm user disabled, locked, account expired, credentials expired, MFA và quyền tồn tại. Đừng giữ `ROLE_ADMIN` cho user đã bị thu hồi chỉ vì dữ liệu migration cũ.

### 13.3. Cutover không gián đoạn và nguy cơ split-brain

Giả sử hệ thống đang có memory accounts tại nhiều JVM và muốn chuyển sang DB:

1. Inventory tất cả tài khoản, roles và account states hiện tại; xác định **source of truth** và version tại thời điểm cutover.
2. Backfill DB bằng job có kiểm tra count/hash/unique/roles; *không* backfill password plaintext qua log.
3. Chạy kiểm thử xác thực **trên môi trường cách ly** với DB copy phù hợp; không chấp nhận một fallback tài khoản hardcoded có quyền admin.
4. Triển khai bản JDBC đến một nhóm canary; mọi requests sau cutover phải dùng **cùng một user store**. Nếu A vẫn dùng memory còn B dùng DB, thay password/disable có thể có hiệu lực khác nhau giữa pods.
5. Nếu cần dual-read tạm thời, bắt buộc thiết kế explicit: source priority, conflict resolution, stable IDs, consistency, timeout và **không fail-open khi DB lỗi**. Với demo đơn giản, nên cutover một lần sau khi xác nhận DB đúng.
6. Đo login success/failure ratio, latency truy vấn UserDetailsService, password mismatch, account lockout, role mapping, session persistence và error rate của login form.
7. Có rollback được thử nghiệm (cơ sở dữ liệu snapshot/version, app compatibility, incident criteria). **Không** quay về passwords hardcoded và không giữ song song hai stores không kiểm soát.

## 14. Ma trận kiểm thử từ memory đến JDBC và production

| ID | Giai đoạn | Tình huống | Kỳ vọng |
| --- | --- | --- | --- |
| M01 | Memory | GET /login anonymous | 200 HTML form |
| M02 | Memory | GET /dashboard anonymous | 302 tới login |
| M03 | Memory | POST /login Alice đúng + CSRF | Authenticated Alice, redirect hợp lý |
| M04 | Memory | POST /login Alice sai | Không authenticated |
| M05 | Memory | POST /login ghost | Không authenticated, không lộ user tồn tại |
| M06 | Memory | POST /login không CSRF | 403, login không chạy thành công |
| M07 | Memory | GET /admin Alice login | 403 role |
| M08 | Memory | GET /admin Admin login | 200 |
| M09 | Memory | POST /logout + CSRF | Session invalidated |
| M10 | Memory | Truy cập /dashboard bằng session đã logout | Không còn authenticated |
| D01 | JDBC | Schema users/authorities tạo đúng | Bảng, indexes, FK có |
| D02 | JDBC | Alice có password hash | Encoder.matches(raw, hash) đúng |
| D03 | JDBC | JdbcUserDetailsManager.loadUserByUsername("alice") | Principal Alice, ROLE_USER |
| D04 | JDBC | Username "ghost" | UsernameNotFoundException ở service, fail login ở provider |
| D05 | JDBC | Alice wrong password | Authentication fail |
| D06 | JDBC | Admin ROLE_ADMIN | Vào /admin |
| D07 | JDBC | Alice ROLE_USER | Bị 403 ở /admin |
| D08 | JDBC | Không có CSRF | 403 trên POST login/logout |
| D09 | JDBC | Restart H2 mem app | Accounts demo được seed lại, không nhầm là persistence |
| D10 | JDBC | Role missing/duplicate | Không vô tình cấp admin; unique key hoạt động |
| P01 | Production | DB restart sau deployment | Users/roles vẫn bền vững |
| P02 | Production | Duplicate normalized username/tenant | Constraint từ chối hoặc xử lý chính sách rõ |
| P03 | Production | Disable user | Login mới bị chặn; session cũ theo policy revoke |
| P04 | Production | Đổi mật khẩu | Hash mới verify, hash cũ không xác thực |
| P05 | Production | DB timeout | Fail closed, alert, không fallback hardcoded user |
| P06 | Production | Hai replicas cùng account | Tra cùng source of truth, quyền nhất quán |
| P07 | Production | Password hash legacy | Migration/DelegatingEncoder/reset theo policy |
| P08 | Production | Account lockout/brute force | Rate limiting/lockout/audit, thông điệp generic |
| P09 | Production | Không được phép admin | Không có side effect nghiệp vụ |
| P10 | Production | Session fixation/timeout | Rotate ID, timeout/invalid cookie đúng |
| P11 | Production | Rollback JDBC code | Không mất dữ liệu/roles hoặc mở đường fallback |
| P12 | Production | CSRF/Cookie/HTTPS | Cơ chế browser/session chống rủi ro cơ bản |

**Tránh test sai tầng:** `@WithMockUser` chỉ kiểm authorization với user giả; `JdbcTemplate` query chỉ kiểm schema/dữ liệu; POST login có CSRF mới kiểm filter/provider; embedded-container/browser E2E mới xác nhận cookie qua mạng và real redirects. Cần đủ ba tầng để tin hệ thống sau migration.

## 15. Troubleshooting: từ login page đến database và phân quyền

| Triệu chứng | Nguyên nhân hay gặp | Cách chẩn đoán |
| --- | --- | --- |
| GET /login trả 404 | Thiếu `@GetMapping("/login")` hoặc `templates/login.html` | Kiểm controller scan và Thymeleaf starter |
| GET /login chuyển vòng lặp | Login page chưa permitAll/matcher sai | Kiểm `formLogin(...).permitAll()` và authorization |
| POST /login trả 403 | Thiếu/sai CSRF token hoặc cookie session | Kiểm hidden `_csrf` và Thymeleaf integration |
| POST /login sai password trả 302 | Expected của form login failure | Kiểm `Location=/login?error`, không coi 302 là pass |
| POST /login đúng nhưng vẫn lỗi | Sai profile bean, hash không khớp, user disabled hoặc provider khác | Xem trusted auth failure logs đã mask secrets |
| Profile memory chạy nhưng không có Alice | Profile chưa bật hoặc bean không được scan | Kiểm `@Profile("memory")`, không nhìn generated password làm kết luận |
| Profile jdbc không khởi động | Thiếu H2 driver/schema, SQL init lỗi, DataSource config sai | Kiểm schema-jdbc.sql, JDBC URL, init order |
| SQLException table USERS not found | Spring SQL init không chạy hoặc sai profile/resource | Kiểm application-jdbc.yml và schema locations |
| Password "alice-pass" không match | Cột DB có plaintext/{bcrypt} không tương thích BCrypt bean | Kiểm encoder format, không dùng equals |
| Admin có ROLE_ADMIN trong DB nhưng 403 | Prefix/row roles sai, security chain khác, principal cache stale | Kiểm `authorities.authority` và Authentication authorities |
| POST logout trả 403 | Thiếu CSRF token | Dùng Thymeleaf form POST hoặc `csrf()` trong test |
| GET dashboard sau login lại redirect | Session cookie không được giữ, Secure cookie HTTP local, context repository | Kiểm Set-Cookie/path/SameSite/session persistence |
| H2 hoạt động rồi mất user sau restart | H2 `jdbc:h2:mem:...` không durable | Chuyển persistent DB/migrations |
| App crash vì có hai UserDetailsService | Chạy đồng thời memory+jdbc hoặc auto config custom | Chỉ bật một profile, kiểm provider selection |
| Query trả nhầm user tenant khác | username chưa unique/scoped theo tenant | Composite key, stable principal và policy |
| Update disabled user DB nhưng session cũ vẫn vào | Existing HTTP session giữ Authentication đã xác thực | Xây logout-all/session version/revoke theo yêu cầu |
| DB lỗi nhưng hệ thống login được admin demo | Memory fallback/hardcoded account còn bật | Loại fallback fail-open, kiểm active beans |
| Template hiển thị username HTML lạ | Dùng `th:utext` trên dữ liệu chưa tin | Dùng `th:text` và HTML escaping |
| Không gọi DB khi login JDBC | Bean in-memory vẫn là provider hoặc filter mock test bypass | Kiểm injected JdbcUserDetailsManager và SQL query |
| Test pass với @WithMockUser, login thật fail | Test không đi qua password provider | POST /login với CSRF, assert authenticated |
| HTTPS production bị vòng login | Proxy forwarded headers/cookie Secure/path sai | Cấu hình proxy headers đáng tin, session fixation và cookies |
| Role/user trong DB khác casing | Collation, trim/canonicalization không nhất quán | Define normalization/unique index và test |

## 16. Checklist bàn giao bài thực hành

### Mức 1 — Hoàn thành chức năng

- [ ] Project Spring Boot 3/Java17 có Web/Security/Thymeleaf/JDBC/H2 dependencies phù hợp BOM.
- [ ] `GET /login` hiển thị form, `POST /login` do Spring Security xử lý, username/password field names đúng.
- [ ] Template Thymeleaf tạo CSRF hidden token cho POST login/logout.
- [ ] Profile `memory` có đúng hai users đã BCrypt hash, không có `{noop}` production.
- [ ] Alice chỉ có ROLE_USER, Admin có ROLE_ADMIN; admin route bảo vệ phía server.
- [ ] Logout POST invalidate session; request tiếp theo phải xác thực lại.
- [ ] Unit/MockMvc tests cho đúng, sai, thiếu user, CSRF, role và session.

### Mức 2 — Chuyển kho dữ liệu thành công

- [ ] Schema JDBC `users`/`authorities` đúng cấu trúc, foreign key/unique constraint.
- [ ] `JdbcUserDetailsManager` là nguồn duy nhất ở profile `jdbc`; profile `memory` không được bật cùng lúc.
- [ ] Password lưu dưới dạng BCrypt hash; test `matches` và đúng authorities từ DB.
- [ ] PageController, login/dashboard/admin templates và filter chain **không phải đổi** khi thay store.
- [ ] Test profile jdbc chạy qua HTTP login thật; không chỉ query database.
- [ ] Hiểu H2 in-memory không có độ bền sau process restart.

### Mức 3 — Sẵn sàng lên hệ thống thật

- [ ] Dùng RDBMS bền vững, migrations versioned, secret manager và TLS datasource.
- [ ] Không tự tạo Alice/Admin với hardcoded password trong production.
- [ ] Password hash migration tương thích; dữ liệu normalized/tenant/role được kiểm và có unique constraints.
- [ ] Có rate-limit/brute-force defense, MFA nếu cần, generic login errors, audit và account recovery.
- [ ] Có session fixation protection, idle/absolute timeout policy, HTTPS/Secure/HttpOnly/SameSite phù hợp.
- [ ] Có quy trình revoke sessions/remember-me sau disable/đổi password khi yêu cầu.
- [ ] Có backup/recovery, canary, rollback, metrics login/database và negative tests.
- [ ] Không cho fallback in-memory hardcoded admin khi datasource mất.

**Kết luận:** Cách chuyển từ account trong RAM sang database đúng là **thay implementation của UserDetailsService**, giữ nguyên `UsernamePasswordAuthenticationFilter → DaoAuthenticationProvider → PasswordEncoder → SecurityContext` và các chính sách phân quyền. Việc app login thành công trong H2 chỉ chứng minh **cơ chế truy vấn SQL trong local lab**, không đồng nghĩa đã có account persistence, production IAM hay một thiết kế chống tấn công hoàn chỉnh.

### Nguồn tham khảo chính thức

- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html)
- [Spring Security 6.5 — JDBC Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/jdbc.html)
- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — MockMvc Authentication Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security — Spring Security Test Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Boot 3.5 — Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html)
- [Spring Boot — SQL Databases and JdbcTemplate](https://docs.spring.io/spring-boot/reference/data/sql.html)
