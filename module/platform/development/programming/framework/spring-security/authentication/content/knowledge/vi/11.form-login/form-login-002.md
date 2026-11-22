# formLogin, loginPage và loginProcessingUrl

## Mục tiêu

Một trang đăng nhập bằng biểu mẫu thường liên quan **hai HTTP request độc lập**: GET để xem form và POST để gửi username/password. Trong Spring Security Servlet, ba cấu hình có tên gần nhau nhưng trách nhiệm khác nhau:

- `formLogin(...)` bật cơ chế form authentication, kết nối filter, entry point, manager và các handlers.
- `loginPage("/signin")` cho biết **URL hiển thị trang login**, thường là GET. Khi chỉ định trang tùy chỉnh, bạn **phải tạo controller/view** để render HTML.
- `loginProcessingUrl("/auth/login")` xác định **URL POST mà `UsernamePasswordAuthenticationFilter` nhận credentials**. Thông thường ứng dụng **không viết @PostMapping** cho URL này.

Theo mặc định, nếu bật form login mà không chỉ định trang tùy chỉnh, Spring Security có thể sinh trang ở `GET /login` và xử lý `POST /login`. Đường dẫn có thể giống nhau nhưng **HTTP method, xử lý và mục đích khác nhau**.

Bài học thuộc nhóm **Đăng nhập biểu mẫu**, module *Spring Security - authentication*, dùng Java 17+, Spring Boot 3.x và Spring Security 6.x trên Servlet. Ví dụ chính chạy bằng Spring MVC + Thymeleaf + BCrypt. WebFlux, JWT resource server và OIDC có những luồng khác, không áp dụng nguyên cấu hình form login MVC này.

Sau bài học bạn sẽ:

1. Phân biệt generated login page, custom login page và processing endpoint.
2. Theo dõi request từ protected resource đến trang login, rồi submit credentials, tạo session và redirect.
3. Viết `SecurityFilterChain` có `loginPage` và `loginProcessingUrl` khác nhau, đồng bộ HTML form.
4. Kiểm tra các tham số `username`, `password`, CSRF token, success/failure URLs, saved requests và logout.
5. Phân biệt login matcher, `securityMatcher` chọn chain và `requestMatchers` cấp quyền.
6. Chạy app Java 17+ hoàn chỉnh và kiểm thử đăng nhập đúng/sai bằng MockMvc.
7. Xử lý lỗi 403, 404, redirect loop, wrong method, login thành công nhưng session không được giữ.

## 1. Đọc ba API theo đúng trách nhiệm

| Cấu hình | Vai trò | Request ví dụ | Thành phần xử lý |
| --- | --- | --- | --- |
| `formLogin(withDefaults())` | Bật form authentication | GET/POST login mặc định | Spring Security filters |
| `loginPage("/signin")` | Trang **hiển thị** form | `GET /signin` | Spring MVC controller + view/template |
| `loginProcessingUrl("/auth/login")` | **Xử lý** form credentials | `POST /auth/login` | `UsernamePasswordAuthenticationFilter` |
| `usernameParameter("username")` | Tên field username | Form field `name="username"` | Filter đọc request parameter |
| `passwordParameter("password")` | Tên field password | Form field `name="password"` | Filter đọc request parameter |
| `failureUrl("/signin?error")` | Trang sau xác thực thất bại | GET sau redirect | AuthenticationFailureHandler + MVC |
| `defaultSuccessUrl("/me", true)` | Trang đích cố định sau success | GET sau redirect | AuthenticationSuccessHandler |
| `form.permitAll()` | Đặt quyền public cho các URL cần thiết của form login | Login page/processing/failure | Authorization rule, **không tắt CSRF** |

`loginPage` **không phải** endpoint kiểm tra mật khẩu. `loginProcessingUrl` **không phải** đường dẫn của template. `formLogin` **không thay thế** cấu hình UserDetailsService/AuthenticationProvider hoặc authorization.

### 1.1. Các mặc định trong Spring Security 6

Cấu hình cơ bản:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Đoạn này là fragment của class có import `@Bean`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`. Khi form login được bật theo cấu hình thông thường:

- `GET /login`: trang login mặc định được Spring Security sinh ra.
- `POST /login`: filter xử lý username/password.
- Sai credentials: thường redirect `GET /login?error`.
- Sau logout: thường redirect `GET /login?logout`.
- Username parameter: `username`.
- Password parameter: `password`.
- Khi chưa đăng nhập truy cập URL protected: redirect tới trang login.
- Khi login thành công: success handler thường ưu tiên saved request, nếu có.

Chú ý: sau khi bạn tự khai báo `SecurityFilterChain`, hãy **bật formLogin rõ ràng** nếu muốn dùng nó; đừng dựa vào suy đoán Spring Boot luôn tự cấu hình mọi cơ chế. Một chain có `securityMatcher` giới hạn path có thể không chứa `/login` nên filter sẽ không cung cấp endpoint đó.

### 1.2. Chỉ định trang custom có ảnh hưởng mặc định liên quan

~~~java
http.formLogin(form -> form
    .loginPage("/signin")
    .permitAll()
);
~~~

Khi chỉ định `loginPage` custom, generator không còn chịu trách nhiệm render trang đó: bạn phải tạo MVC route hoặc cơ chế trả HTML. Javadoc `FormLoginConfigurer` cũng giải thích việc thay trang custom ảnh hưởng những giá trị mặc định liên quan (processing/failure/logout). Để bài code dễ hiểu và vận hành ổn định, ví dụ sẽ **chỉ định tường minh** `loginProcessingUrl`, `failureUrl` và `logoutSuccessUrl` thay vì ngầm đoán chúng.

Nếu muốn GET form và POST processing trùng path, bạn có thể dùng cả `loginPage("/signin")` và `loginProcessingUrl("/signin")`. Nhưng tách GET `/signin` và POST `/auth/login` làm rõ hai trách nhiệm và giúp debug thuận tiện.

## 2. Chuỗi xử lý request khi đăng nhập

~~~text
Browser -> GET /me (chưa authenticated)
          |
          v
FilterChainProxy / AuthorizationFilter
          |
          v
Không được truy cập /me
          |
          v
ExceptionTranslationFilter -> AuthenticationEntryPoint
          |
          v
302 /signin

Browser -> GET /signin
          |
          v
@Controller @GetMapping("/signin") -> signin.html
          |
          v
200 HTML có form POST /auth/login và CSRF token

Browser -> POST /auth/login
           username=alice&password=...&_csrf=...
          |
          v
CsrfFilter (nếu bật) kiểm tra token
          |
          v
UsernamePasswordAuthenticationFilter
          |
          v
UsernamePasswordAuthenticationToken chưa xác thực
          |
          v
AuthenticationManager -> AuthenticationProvider
          |
          +-- UserDetailsService tải account
          +-- PasswordEncoder.matches(rawPassword, hash)
          +-- account-status checks
          |
          +-- FAILURE -> failure handler -> 302 /signin?error
          |
          +-- SUCCESS -> SecurityContext + session strategy
                         -> success handler -> 302 /me

Browser -> GET /me + session cookie
          |
          v
SecurityContext được khôi phục -> 200 trang tài khoản
~~~

Đây là luồng logic theo Servlet; thứ tự chính xác của các filters còn phụ thuộc chain. `loginProcessingUrl` chỉ quyết định filter có nhận request credentials; nó không cho user quyền truy cập. CORS/CSRF có thể chặn POST **trước khi authentication filter thử password**.

### 2.1. Vai trò của trang GET

`GET /signin` chỉ **render HTML**, không xác minh password. Một MVC handler thường trả view name:

~~~java
@Controller
class SigninPage {
    @GetMapping("/signin")
    String signin() {
        return "signin";
    }
}
~~~

Đây là code fragment, cần imports và template `signin.html`. Dùng `@Controller`, không dùng `@RestController` nếu muốn return string thành view name. Đừng đưa password vào view model.

### 2.2. Vì sao POST không cần @PostMapping?

Khi filter chain được cấu hình đúng:

~~~java
.formLogin(form -> form
    .loginPage("/signin")
    .loginProcessingUrl("/auth/login")
    .permitAll()
)
~~~

thì `UsernamePasswordAuthenticationFilter` xử lý `POST /auth/login`. Không cần `@PostMapping("/auth/login")` trong MVC. Một controller POST tự so password và tự tạo authenticated token từ username có nguy cơ bypass provider, account status, session fixation và handlers.

Với form login chuẩn, hãy giao xử lý credentials cho Spring Security. Chỉ viết custom filter/provider khi yêu cầu thực sự vượt quá DSL chuẩn và đã xác định rõ trách nhiệm an ninh bổ sung.

### 2.3. Gửi sai method hoặc URL

| Request | Có phải authentication attempt chuẩn? | Điều xảy ra sau đó |
| --- | --- | --- |
| `GET /signin` | Không | MVC render form |
| `POST /auth/login` | Có, nếu chain/filter phù hợp | Xác thực hoặc CSRF fail |
| `GET /auth/login` | Không | MVC/authorization xử lý tiếp |
| `POST /signin` | Không nếu processing URL là `/auth/login` | Có thể redirect, 404, 405 |
| `OPTIONS /auth/login` | Không | CORS preflight/rules |
| `POST /api/orders` | Không | Filter/controller nghiệp vụ khác |

Đừng đoán rằng `GET /auth/login` nhất định phải trả 405; khi filter bỏ qua, authorization có thể redirect anonymous tới `/signin` trước khi request đến Spring MVC.

## 3. loginPage và quyền truy cập trang

### 3.1. Vì sao custom page cần permitAll?

Cấu hình sai:

~~~java
http
    .authorizeHttpRequests(auth ->
        auth.anyRequest().authenticated()
    )
    .formLogin(form ->
        form.loginPage("/signin")
    );
~~~

Nếu `/signin` bị áp rule authenticated, anonymous GET `/me` redirect tới `/signin`, rồi GET `/signin` lại redirect chính nó. Browser báo redirect loop. Cấu hình nên có:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/signin", "/public").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/auth/login")
        .permitAll()
    );
~~~

`form.permitAll()` cho phép các endpoint cần thiết của form login nhưng **không vô hiệu hóa** CSRF, security headers hoặc authentication filter. `permitAll("/**")` là mở toàn app; không dùng để chữa redirect loop.

### 3.2. Public CSS/JS chỉ mở theo nhu cầu

Nếu trang cần `/css/signin.css` hoặc `/images/logo.svg`, có thể thêm rule `requestMatchers("/css/**", "/images/**").permitAll()`. Đừng mở `/api/**` hoặc dữ liệu riêng tư chỉ để trang login có style. `permitAll` khác `web.ignoring`: các security filters vẫn có thể chạy khi rule là permitAll.

### 3.3. Generated login page không phải custom login page

Khi bật `formLogin(withDefaults())`, Spring Security cung cấp form mặc định. Khi bạn đặt `loginPage("/signin")`, trang custom không tự xuất hiện nếu app chưa có controller/template. Đừng vừa đặt trang custom, vừa kỳ vọng generator sẽ xử lý GET custom URL thay mình.

## 4. loginProcessingUrl, form fields và CSRF

### 4.1. Form action phải khớp URL xử lý

Với:

~~~java
.loginProcessingUrl("/auth/login")
~~~

HTML đúng cần:

~~~html
<form action="/auth/login" method="post">
    <input type="text" name="username">
    <input type="password" name="password">
    <button type="submit">Đăng nhập</button>
</form>
~~~

Đoạn HTML trên **chưa đủ cho môi trường có CSRF** và hardcode action theo root. Ở ví dụ Thymeleaf sau, dùng `th:action="@{/auth/login}"` để thêm context path đúng, đồng thời nhờ tích hợp Spring MVC/Thymeleaf sinh hidden CSRF input.

Nếu form POST `/login` nhưng processing URL là `/auth/login`, filter không nhận credentials. Đừng đổi PasswordEncoder hoặc tạo controller xử lý POST trùng để che lỗi; hãy sửa URL action.

### 4.2. Tên input là thuộc tính name

Mặc định filter đọc:

~~~text
username=alice
password=demo-pass
~~~

Nếu đổi DSL:

~~~java
.usernameParameter("loginId")
.passwordParameter("secret")
~~~

thì form phải dùng `name="loginId"` và `name="secret"`. Thuộc tính `id` và `placeholder` chỉ phục vụ HTML/UI, không thay tên parameter request. Đừng log form body hoặc đặt raw password vào URL/query.

### 4.3. Form data không phải JSON

`UsernamePasswordAuthenticationFilter` mặc định đọc HTTP parameters, thường từ `application/x-www-form-urlencoded`. Nếu frontend gửi `Content-Type: application/json` với body:

~~~json
{"username":"alice","password":"demo-pass"}
~~~

thì URL processing chính xác **không đồng nghĩa filter tự parse JSON**. JSON login cần authentication converter/filter và response behavior riêng. Không bật JSON chỉ bằng cách thay `loginProcessingUrl`.

### 4.4. CSRF token bảo vệ POST

Spring Security có `CsrfFilter` kiểm tra token với state-changing requests theo cấu hình mặc định. POST login thiếu/sai CSRF token có thể **403 Forbidden trước khi password được kiểm tra**.

HTML server-side có thể dùng:

~~~html
<form th:action="@{/auth/login}" method="post">
    <input type="text" name="username">
    <input type="password" name="password">
    <button type="submit">Đăng nhập</button>
</form>
~~~

Với Thymeleaf + Spring MVC/Security integration, `th:action` sử dụng `RequestDataValueProcessor` để thêm hidden CSRF token khi có request CSRF. Nếu dùng template engine khác, phải render hidden field tương ứng `CsrfToken` bằng cách được hỗ trợ; không tùy tiện tắt CSRF toàn cục.

CSRF token phải gắn với chính flow/request/cookie phù hợp. Một curl POST chỉ gửi username/password có thể nhận 403 dù account và password đều chính xác. Khi thử qua browser, kiểm tra hidden token trong HTML đã render và session cookie trong DevTools.

## 5. failureUrl, defaultSuccessUrl và logoutSuccessUrl

### 5.1. Đăng nhập sai: failure URL

~~~java
.failureUrl("/signin?error")
~~~

Khi provider từ chối credentials, failure handler có thể redirect về URL này. Controller tiếp tục render trang signin, template hiển thị thông báo **chung**. Đừng tiết lộ username tồn tại, account disabled hay trạng thái nội bộ cho người chưa xác thực; dùng audit nội bộ được kiểm soát.

### 5.2. Đăng nhập đúng: saved request hay target cố định?

Mặc định Spring Security thường lưu URL mà anonymous user đã cố mở:

~~~text
GET /orders -> 302 /signin
POST /auth/login -> successful authentication
-> GET /orders (nếu saved request hợp lệ)
~~~

Nếu muốn **luôn** về `/me` cho ví dụ deterministic:

~~~java
.defaultSuccessUrl("/me", true)
~~~

Tham số `true` ép chuyển đến `/me` ngay cả khi có saved request. Với app thực, có thể giữ behavior saved-request hoặc dùng `defaultSuccessUrl("/me")` không ép bỏ saved request. Đừng lấy URL redirect do client gửi mà không validate destination, kẻ xấu có thể tạo open redirect.

### 5.3. Logout tách khỏi login

Ví dụ:

~~~java
.logout(logout -> logout
    .logoutSuccessUrl("/signin?logout")
    .permitAll()
)
~~~

Với CSRF bật, logout thực tế thường kích hoạt bằng **POST /logout** có CSRF token. Spring Security dọn session/context và redirect tới success URL; một custom login page có thể hiển thị thông báo logout qua query. Không dùng link GET logout rồi tắt CSRF chỉ để tiện điều hướng.

## 6. Ví dụ Spring Boot 3.x / Java 17+ hoàn chỉnh

Demo sử dụng Spring Web, Spring Security, Thymeleaf và một user thử trong bộ nhớ. Không dùng database, JSON login hoặc controller POST thay filter.

### 6.1. Khởi tạo project

Spring Initializr:

- Maven, Spring Boot **3.x**, Java **17 hoặc 21**.
- Group `com.example`, artifact `custom-form-login`, package `com.example.demo`.
- Dependencies: `spring-boot-starter-web`, `spring-boot-starter-security` và `spring-boot-starter-thymeleaf`.
- Để chạy test, thêm `spring-boot-starter-test` và `spring-security-test` dưới scope test.

Cấu trúc:

~~~text
custom-form-login/
  pom.xml
  src/main/java/com/example/demo/FormLoginDemoApplication.java
  src/main/resources/templates/signin.html
  src/main/resources/templates/me.html
  src/test/java/com/example/demo/FormLoginDemoTest.java
~~~

### 6.2. File Java đầy đủ

Tạo `src/main/java/com/example/demo/FormLoginDemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FormLoginDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormLoginDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/signin").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/signin")
                .loginProcessingUrl("/auth/login")
                .failureUrl("/signin?error")
                .defaultSuccessUrl("/me", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/signin?logout")
                .permitAll()
            )
            .build();
    }

    @Controller
    static class Pages {
        @GetMapping("/signin")
        String signin() {
            return "signin";
        }

        @GetMapping("/me")
        String me(Authentication authentication, Model model) {
            model.addAttribute("username", authentication.getName());
            return "me";
        }
    }

    @RestController
    static class Resources {
        @GetMapping("/public")
        String open() {
            return "public";
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
~~~

Điểm đáng chú ý:

- `formLogin` bật authentication filter và redirect handlers.
- `loginPage("/signin")` yêu cầu controller GET trang login.
- `loginProcessingUrl("/auth/login")` do filter xử lý; không viết `@PostMapping("/auth/login")`.
- `failureUrl` và `logoutSuccessUrl` trỏ về trang custom có query flag.
- `defaultSuccessUrl("/me", true)` giúp đường dẫn sau success xác định.
- `form.permitAll()` đảm bảo các URL login liên quan có authorization public, còn `/me` authenticated, `/admin` role ADMIN.
- Spring Security dùng BCrypt băm password demo; authentication provider dùng encoder để verify, không so plaintext.
- `@Controller` trả tên template, `@RestController` trả body.

Không dùng password hardcode hoặc HTTP không TLS trong production; đây là ví dụ chạy ở localhost.

### 6.3. File signin.html

Tạo `src/main/resources/templates/signin.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
    <h1>Đăng nhập</h1>

    <p th:if="${param.error}">
        Không thể đăng nhập bằng thông tin đã cung cấp.
    </p>
    <p th:if="${param.logout}">
        Bạn đã đăng xuất.
    </p>

    <form th:action="@{/auth/login}" method="post">
        <label for="username">Tên đăng nhập</label>
        <input id="username" name="username" type="text"
               autocomplete="username" required>

        <label for="password">Mật khẩu</label>
        <input id="password" name="password" type="password"
               autocomplete="current-password" required>

        <button type="submit">Đăng nhập</button>
    </form>
</body>
</html>
~~~

`th:action="@{/auth/login}"` giúp sinh action tương thích context path (ví dụ khi app được deploy dưới `/shop`). Thymeleaf tích hợp Spring MVC tự thêm CSRF hidden input cho POST form qua `RequestDataValueProcessor` khi cấu hình phù hợp; kiểm tra HTML thực tế nếu dùng engine khác hoặc tùy chỉnh integration.

### 6.4. File me.html và logout POST

Tạo `src/main/resources/templates/me.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang tài khoản</title>
</head>
<body>
    <h1>Trang tài khoản</h1>
    <p>Xin chào <strong th:text="${username}">user</strong></p>

    <form th:action="@{/logout}" method="post">
        <button type="submit">Đăng xuất</button>
    </form>
</body>
</html>
~~~

`th:text` escape username thay vì nối HTML thô. Nút logout dùng POST (CSRF bảo vệ). Chỉ `SecurityContextHolder.clearContext()` không bảo đảm toàn session được logout; dùng logout hỗ trợ sẵn của Spring Security.

### 6.5. Chạy và quan sát

Trong thư mục chứa `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Dùng browser vì browser quản lý cookie và Thymeleaf render CSRF:

1. `GET http://localhost:8080/public` → HTTP 200, body `public`.
2. `GET http://localhost:8080/me` khi anonymous → redirect tới `/signin`.
3. `GET /signin` → trang HTML, có form POST `/auth/login` và CSRF token.
4. Nhập **alice / demo-pass**, submit → login thành công, redirect `/me`, trang hiển thị **Xin chào alice**.
5. `GET /admin` khi đã login là Alice → HTTP **403** do thiếu ROLE_ADMIN.
6. Logout bằng nút trên `/me` → POST `/logout`, redirect `/signin?logout`.
7. Truy cập lại `/me` → phải login lại. Browser incognito không dùng cookie của phiên Alice.
8. Thử sai password → redirect `/signin?error`; trang hiển thị thông điệp chung.

Nếu DevTools hiển thị 200 ở trang cuối sau redirect, xem chuỗi Network để phân biệt response 302 của login/filter với GET 200 của trang đích.

## 7. Kiểm thử tích hợp bằng MockMvc

Một lần thay URL rất dễ gây bug form action, CSRF hoặc success handler. Test nên kiểm chứng cả filter chain và session.

### 7.1. Dependencies test

Trong `pom.xml` thêm nếu chưa có:

~~~xml
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
~~~

### 7.2. File JUnit 5 chạy được

Tạo `src/test/java/com/example/demo/FormLoginDemoTest.java`:

~~~java
package com.example.demo;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class FormLoginDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicAndSigninAreAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/signin"))
            .andExpect(status().isOk())
            .andExpect(view().name("signin"));
    }

    @Test
    void anonymousMustVisitCustomSignin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/signin"));
    }

    @Test
    void correctLoginPersistsSessionButNotAdminRole()
            throws Exception {
        MvcResult login = mvc.perform(
                post("/auth/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass")
            )
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andReturn();

        HttpSession session = login.getRequest().getSession(false);
        assertNotNull(session);

        MockHttpSession mockSession = (MockHttpSession) session;

        mvc.perform(get("/me").session(mockSession))
            .andExpect(status().isOk())
            .andExpect(view().name("me"))
            .andExpect(model().attribute("username", "alice"));

        mvc.perform(get("/admin").session(mockSession))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordRedirectsToFailure() throws Exception {
        mvc.perform(
                post("/auth/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "wrong")
            )
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signin?error"));
    }

    @Test
    void missingCsrfIsForbidden() throws Exception {
        mvc.perform(
                post("/auth/login")
                    .param("username", "alice")
                    .param("password", "demo-pass")
            )
            .andExpect(status().isForbidden());
    }
}
~~~

Test xác nhận GET custom login page được phép, anonymous redirect đến custom page, đúng credentials tạo session và có quyền user nhưng không phải admin, sai password về failure page, thiếu CSRF bị từ chối trước auth.

### 7.3. Chạy test và kết quả kỳ vọng

~~~bash
./mvnw test
~~~

Windows:

~~~powershell
.\mvnw.cmd test
~~~

Với dependencies/version phù hợp, kỳ vọng **5 test methods pass**. Dòng Surefire thường có dạng:

~~~text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
~~~

Đây là **kết quả dự kiến**, không phải build log đã chạy thực tế. Tại dự án production cần bổ sung test POST logout có CSRF, login form HTML chứa CSRF/action chính xác, context path thực tế, lock/disabled accounts, session fixation và multi-chain.

## 8. Saved request, form action và login URL trong nhiều SecurityFilterChain

Spring Security có ba cấp matcher dễ nhầm:

| Matcher | Tác dụng |
| --- | --- |
| `http.securityMatcher("/app/**")` | Chain này có xử lý request không? |
| `UsernamePasswordAuthenticationFilter` matcher từ `loginProcessingUrl` | Filter có thử authentication ở URL/method này không? |
| `authorizeHttpRequests().requestMatchers("/admin").hasRole("ADMIN")` | Request đã vào chain có được truy cập tài nguyên không? |

Cấu hình sau dễ lỗi:

~~~java
http
    .securityMatcher("/app/**")
    .formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/auth/login")
    );
~~~

`/signin` và `/auth/login` không nằm trong `/app/**`. Chain này không được chọn, nên login filter của nó **không thể nhận POST /auth/login`**. Thêm `permitAll("/auth/login")` bên trong chain không tự sửa lỗi chain selection.

Cách thiết kế:

- Đưa page và processing URLs vào cùng namespace, ví dụ `/app/signin` và `/app/auth/login`; viết controller/template thống nhất.
- Hoặc mở rộng matcher của chain có kiểm soát bằng RequestMatcher bao phủ các URL cần thiết, vẫn giữ catch-all chain để bảo vệ phần còn lại.
- Nếu nhiều chains, đặt `@Order` rõ ràng. Spring Security chọn **SecurityFilterChain đầu tiên khớp**, không chạy tất cả chains.

Saved request (`GET /orders` trước khi login) thường được success handler ưu tiên trừ khi bạn đặt `defaultSuccessUrl("/me", true)`. Khi dùng custom success handler, kiểm tra cả saved request và redirect destination để tránh open redirect.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách kiểm tra/sửa |
| --- | --- | --- |
| `GET /signin` 404 | Thiếu controller hoặc template | Tạo `@Controller @GetMapping` + `templates/signin.html` |
| GET chỉ trả chữ signin | Dùng `@RestController` thay vì view controller | Dùng `@Controller` |
| Redirect loop `/signin` | Trang login bị bảo vệ bởi authenticated rule | `form.permitAll()` và rule public chính xác |
| Form submit nhưng không xác thực | Action không khớp processing URL | Đồng bộ `th:action` và `loginProcessingUrl` |
| Form submit POST sai method/path | HTML method GET hoặc URL cũ | Kiểm tra browser Network |
| POST login trả 403 | Missing/invalid CSRF | Kiểm tra token+session, không tắt CSRF bừa bãi |
| Form POST JSON nhưng login fail | Filter chuẩn đọc form parameters | Converter/filter JSON riêng nếu cần |
| Đổi `usernameParameter` rồi login fail | Input `name` không khớp | Cập nhật template và filter |
| Login thành công nhưng `/admin` 403 | User thiếu ROLE_ADMIN | Debug authorization, không sửa password |
| Login success nhưng request sau anonymous | Session/cookie/context persistence sai | Xem repository, session policy, success flow |
| Có `JSESSIONID` nhưng vẫn anonymous | Session không nhất thiết chứa Authentication | Kiểm tra context |
| Chỉ app prefix `/app/**` được bảo vệ | Processing/login URLs nằm ngoài chain | Đồng bộ chain matcher |
| Action root hỏng khi deploy `/shop` | Hardcode `action="/auth/login"` | Dùng `th:action="@{/auth/login}"` |
| Default page không còn | Custom `loginPage` đã thay generator | Cung cấp custom GET view |
| Login filter chạy hai lần | Đăng ký filter custom cả container và security chain | Chỉ wiring đúng một lần |
| Logout thành công nhưng tab khác vẫn login | Token/session khác chưa revoke | Thiết kế logout/revocation phù hợp |

### 9.1. Checklist debug có thứ tự

1. Dùng DevTools xem **HTTP method**, path và response Location; không chỉ nhìn trang cuối.
2. Kiểm tra `FilterChainProxy` chọn chain nào và filter form login có trong chain không.
3. Xác nhận `GET /signin` trả HTML từ MVC, không phải text hoặc redirect loop.
4. Xem form render cuối cùng có POST `/auth/login`, fields `username`/`password` và CSRF hidden input không.
5. Nếu 403 trước auth, xem `CsrfFilter`, session/cookies và CORS.
6. Nếu đã tới provider, kiểm tra `UserDetailsService`, `PasswordEncoder`, trạng thái account.
7. Nếu login success mà refresh mất auth, kiểm tra session cookie, SecurityContextRepository/session creation policy.
8. Nếu đã authenticated nhưng 403 vào admin, xem authorities.
9. Nếu logout không dọn session, kiểm tra logout flow và token/session store.
10. Không log raw password, hash, session cookie, CSRF token hay full Authentication object.

## 10. Bảo mật cần bảo đảm

**HTTPS:** form POST không bảo vệ credentials khỏi network eavesdropping nếu chạy HTTP. Production cần TLS, cookie Secure/HttpOnly/SameSite phù hợp và tuyệt đối không để password trong URL/query.

**CSRF:** form login và logout trong ứng dụng dựa cookie cần CSRF protection. Thymeleaf tích hợp Spring MVC có thể tự sinh hidden token khi dùng `th:action`, nhưng phải kiểm tra HTML đã render trong môi trường thật. `permitAll` không miễn CSRF.

**Rate limiting và MFA:** `formLogin` không tự bảo đảm chống mọi password spraying/brute force. Cần rate limiting nhiều chiều, account lockout tránh DoS, MFA/passkeys khi phù hợp, monitoring và audit có kiểm soát.

**Không lộ account status:** trang `/signin?error` nên hiển thị lỗi chung, không tiết lộ user tồn tại/disabled/locked cho người chưa xác thực. Không echo raw credentials.

**Session fixation:** form login chuẩn tích hợp session authentication strategy. Nếu tự viết login handler rồi chỉ `SecurityContextHolder.setContext`, có thể quên session fixation protection và explicit `saveContext` của Spring Security 6.

**Stored hash:** dùng `PasswordEncoder` adaptive (BCrypt/Argon2id...) và đúng format; không lưu plaintext. Hash match mới là bước đầu: authorization và account-status checks vẫn quan trọng.

**XSS:** template sử dụng `th:text` escape username, không dùng unescaped HTML từ query error hoặc user input. XSS trên trang login có thể làm lộ credentials.

**Token/session revocation:** thay role hoặc disable user trong DB không tự xóa mọi session đã authenticated. Cần policy session invalidation, token TTL/revocation theo mức rủi ro.

## 11. Bài tập và đáp án

**Câu 1.** `formLogin` đang bật mặc định. `GET /login` và `POST /login` có cùng tác dụng?

**Đáp án:** không. GET hiển thị trang login generated; POST nhận credentials qua filter.

**Câu 2.** Đã dùng `loginPage("/signin")` nhưng chưa viết controller/template. Tại sao anonymous bị 404?

**Đáp án:** Spring Security không render HTML của trang custom thay ứng dụng; cần GET route và view.

**Câu 3.** Form HTML POST `/login` nhưng `loginProcessingUrl("/auth/login")`. Password đúng vẫn không login?

**Đáp án:** request đi sai processing URL; sửa `th:action`, không thay provider hoặc tự tạo controller đăng nhập.

**Câu 4.** POST đúng URL nhưng thiếu CSRF bị 403. Có chứng minh password sai không?

**Đáp án:** không. `CsrfFilter` có thể chặn trước khi filter đăng nhập chạy.

**Câu 5.** Dùng `@RestController` return `"signin"` có render `signin.html` không?

**Đáp án:** không theo cách return string body thông thường; dùng `@Controller` trả view name.

**Câu 6.** Tại sao trang login nên `permitAll` dù hệ thống yêu cầu authenticated cho phần lớn URLs?

**Đáp án:** anonymous cần xem form và submit credentials. Nếu chính trang login bị chặn, có thể redirect loop. `permitAll` không cho phép truy cập tài nguyên riêng tư.

**Câu 7.** Cấu hình `defaultSuccessUrl("/me", true)` ảnh hưởng saved request thế nào?

**Đáp án:** ép redirect /me sau thành công, dù người dùng đang cố truy cập trang protected khác.

**Câu 8.** `UsernamePasswordAuthenticationFilter` có tự parse JSON login body không?

**Đáp án:** không trong form-parameter implementation chuẩn; cần converter/filter riêng.

**Câu 9.** `/admin` trả 403 sau login thành công; có liên quan `loginPage` không?

**Đáp án:** thường không. User đã authenticated nhưng thiếu authority theo authorization rule.

**Câu 10.** `http.securityMatcher("/app/**")` nhưng trang login và processing ở root. Dùng `form.permitAll()` có sửa chain selection không?

**Đáp án:** không. Login endpoints phải thuộc chain chứa authentication filter hoặc thiết kế lại chain matcher.

**Câu 11.** Deploy dưới context path `/shop`, form hardcode action `/auth/login`. Tại sao browser gửi sai URL?

**Đáp án:** root path của domain không kèm context path `/shop`; dùng `th:action="@{/auth/login}"`.

**Câu 12.** Vì sao không nên bỏ qua CSRF cho login/logout khi dùng session cookie?

**Đáp án:** browser tự gửi cookie và có thể bị kích hoạt state-changing requests cross-site. Dùng token đúng flow, không tắt bảo vệ vì tiện test.

## 12. Checklist triển khai

- [ ] `formLogin` được bật trong đúng `SecurityFilterChain`.
- [ ] `loginPage` có GET controller/template thật và anonymous được truy cập.
- [ ] `loginProcessingUrl` khớp chính xác URL form POST; không viết controller POST trùng không cần thiết.
- [ ] Form dùng method POST, parameter names đúng và CSRF token hợp lệ.
- [ ] `failureUrl`, `logoutSuccessUrl`, success/saved-request behavior thống nhất với view.
- [ ] Không redirect loop vì login page bị yêu cầu authenticated.
- [ ] Không mở `permitAll` cho toàn app chỉ để login hoạt động.
- [ ] Resource admin có authorization riêng; không suy login success là có mọi quyền.
- [ ] Context path, servlet path, reverse proxy và static asset paths được test.
- [ ] Multi-chain `securityMatcher` bao phủ cả login page và processing endpoint; có catch-all protection.
- [ ] Dùng BCrypt/PasswordEncoder đúng với stored password format; UserDetailsService không tự authenticate.
- [ ] HTTPS, rate limiting, MFA, CSRF, session fixation và cookie policy được thiết kế.
- [ ] Integration tests GET login, POST đúng/sai, missing CSRF, role 403, session persistence, logout.
- [ ] Không log raw credentials/hash, CSRF, session cookie; không tự tạo authenticated token từ input client.

**Kết luận:** `formLogin` bật authentication qua biểu mẫu; `loginPage` quy định **trang GET hiển thị form**; `loginProcessingUrl` quy định **POST nơi filter nhận credentials**. Những cấu hình này phải đồng bộ với MVC view, HTML action/fields, CSRF, success/failure handlers, session và các rules của SecurityFilterChain. Khi tách đúng trách nhiệm, bạn sẽ chẩn đoán được 404 do thiếu view, 403 do CSRF, redirect loop do thiếu permitAll và 403 authorization sau khi login thành công.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — FormLoginConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html)
- [Spring Security 6.5 — AbstractAuthenticationFilterConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/AbstractAuthenticationFilterConfigurer.html)
- [Spring Security 6.5 — UsernamePasswordAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/UsernamePasswordAuthenticationFilter.html)
- [Spring Security 6.5 — Java Configuration and FilterChain endpoints](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — Authentication Persistence](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
