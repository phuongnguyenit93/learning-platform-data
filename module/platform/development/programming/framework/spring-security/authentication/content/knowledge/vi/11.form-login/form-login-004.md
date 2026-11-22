# Trang đăng nhập tự tạo và những đường dẫn cần được truy cập công khai

> **Ngữ cảnh:** Spring Security – authentication, nhóm **Đăng nhập biểu mẫu**. Bài học giải thích cách tự tạo trang đăng nhập bằng Spring MVC + Thymeleaf, phân biệt URL **hiển thị form** với URL **xử lý credential**, và cấu hình những đường dẫn phải cho phép truy cập khi người dùng **chưa đăng nhập**. Ví dụ hoàn chỉnh dùng **Java 17+**, **Spring Boot 4.1.2**, Spring Security Servlet và Thymeleaf; có CSRF, form login, logout, trang bảo vệ, CSS công khai, sơ đồ luồng, kiểm thử và cách chẩn đoán redirect loop.

## 1. Vì sao trang đăng nhập tự tạo cần quyền truy cập công khai?

Khi thêm Spring Security vào ứng dụng web, chính sách phổ biến là: những URL nghiệp vụ cần authentication, còn một số endpoint cung cấp nội dung cần thiết **trước khi xác thực** phải truy cập được.

Trang đăng nhập là ví dụ rõ nhất. Người dùng chưa có session hợp lệ phải tải được trang chứa form để nhập username và password. Nếu chính trang login cũng yêu cầu authentication, quy trình có thể tự chuyển hướng về chính nó:

```text
GET /dashboard (chưa đăng nhập)
       |
       v
Security yêu cầu authentication
       |
       v
302 Location: /sign-in
       |
       v
GET /sign-in
       |
       +-- Nếu /sign-in cũng yêu cầu authentication
       |       |
       |       v
       |   302 Location: /sign-in
       |       |
       |       +-- lặp lại -> redirect loop
       |
       +-- Nếu /sign-in permitAll
               |
               v
           HTTP 200, form đăng nhập
```

Tuy nhiên, **không có nghĩa toàn bộ ứng dụng phải công khai**. Chỉ những resource thực sự cần trước khi login được cấp `permitAll`. Endpoint nghiệp vụ như `/dashboard`, `/account/settings` hoặc `/admin/**` vẫn được bảo vệ.

Một trang login cũng thường tải file CSS, hình ảnh/logo, icon và JavaScript. Nếu trang `/sign-in` là public nhưng `/css/site.css` vẫn yêu cầu login, HTML có thể trả 200 trong khi giao diện bị hỏng hoặc trình duyệt nhận HTML thay vì CSS. Vì thế danh sách public cần nhìn ở mức **toàn bộ luồng hiển thị** chứ không chỉ một URL.

## 2. Form login gồm ít nhất hai URL khác nhau

Với Spring Security Servlet, cần phân biệt:

1. **Trang hiển thị form (login page):** ví dụ `GET /sign-in`. Spring MVC `@Controller` render Thymeleaf template.
2. **Đường xử lý credential (login processing URL):** ví dụ `POST /perform-login`. `UsernamePasswordAuthenticationFilter` của Spring Security tiếp nhận username/password; thông thường **không cần viết controller `@PostMapping` cho đường này**.

Sơ đồ:

```text
Browser chưa login
      |
      | GET /sign-in
      v
PageController.signIn()
      |
      v
templates/sign-in.html   (username, password, CSRF token)
      |
      | POST /perform-login
      v
Spring Security UsernamePasswordAuthenticationFilter
      |
      v
AuthenticationManager / AuthenticationProvider
      |
      +-- sai -> 302 /sign-in?error
      |
      +-- đúng -> session/SecurityContext
                        |
                        v
             302 /dashboard hoặc saved request
                        |
                        v
                Trang được bảo vệ
```

**Không được nhầm:**

- `loginPage("/sign-in")` khai báo địa chỉ trang login để redirect khi chưa authenticated.
- `loginProcessingUrl("/perform-login")` là nơi bộ lọc authentication **nhận POST**.
- `failureUrl("/sign-in?error")` là URL chuyển hướng khi login thất bại.
- `defaultSuccessUrl("/dashboard", false)` chỉ ra đích mặc định khi không có saved request ưu tiên.
- `permitAll()` trên form login giúp các URL login/failure/processing liên quan được phép truy cập mà không cần authentication, nhưng **không tự cho phép toàn bộ CSS, ảnh, trang đăng ký hoặc reset password**.

### Bảng phân loại đường dẫn cần thiết

| Request | Có cần authentication trước không? | Thành phần xử lý |
| --- | --- | --- |
| `GET /sign-in` | **Không** | Spring MVC controller + Thymeleaf |
| `POST /perform-login` | **Không phải đã authenticated**; phải đi qua CSRF và bộ lọc login | `UsernamePasswordAuthenticationFilter` |
| `GET /sign-in?error` | **Không** | Cùng MVC controller; template hiển thị thông báo |
| `GET /sign-in?logout` | **Không** | Cùng MVC controller; template hiển thị trạng thái |
| `GET /css/site.css` | **Không** | Spring Boot static resource handler |
| `GET /images/logo.svg` nếu trang login dùng | **Không** | Static resource handler |
| `GET /public/about` | **Không** nếu nội dung công khai | Spring MVC/controller |
| `GET /dashboard` | **Có** | Controller bảo vệ |
| `GET /admin/**` | **Có role phù hợp** | Authorization + controller |
| `POST /sign-out` | Không cần login trước nếu logout config permitAll, **vẫn cần CSRF** | `LogoutFilter` |
| `POST /register` nếu có | Có thể public, nhưng cần validation/CSRF/rate limit | Service đăng ký |
| `POST /reset-password` nếu có | Có thể public, nhưng phải chứng thực reset token | Service reset password |

**Public route ≠ không có bảo vệ.** `permitAll` bỏ yêu cầu authentication tại tầng authorization; CSRF, input validation, rate limit, kiểm tra token reset, các security filter và logic nghiệp vụ vẫn cần hoạt động.

## 3. Trang đăng nhập tự tạo khác trang mặc định của Spring Security

Nếu chỉ cấu hình `formLogin(withDefaults())` và không cung cấp trang tùy biến, Spring Security có thể tạo một trang đăng nhập mặc định để phát triển/thử nghiệm. Trang đó do filter của framework cung cấp.

Khi gọi `formLogin(form -> form.loginPage("/sign-in"))`, bạn đã nói với Spring Security rằng **ứng dụng sẽ tự cung cấp** trang `/sign-in`. Framework không tự sinh file Thymeleaf, không tự thêm `@GetMapping("/sign-in")` và không biết bố cục/branding bạn muốn.

Một trang tự tạo tối thiểu cần:

- Một **controller** trả view name cho `GET /sign-in`.
- File template ở đúng thư mục mà Thymeleaf tìm.
- Form `method="post"` có action khớp `loginProcessingUrl`.
- Input name đúng `usernameParameter` và `passwordParameter` (mặc định `username`, `password`).
- CSRF token hợp lệ khi form POST.
- Quy tắc `permitAll` cho login page và những tài nguyên public cần thiết.
- Success/failure URL hợp lý, không tạo vòng lặp.

**Không cần tự xử lý password trong controller.** Form processing là công việc của authentication filter/provider. Nếu viết `@PostMapping("/perform-login")` để tự so sánh password và gọi `SecurityContextHolder`, bạn có thể làm trùng hoặc vượt qua cơ chế của Spring Security.

## 4. Luồng xác thực khi người dùng chưa login

Ví dụ người dùng vào `/dashboard` trước:

```text
GET /dashboard (anonymous)
         |
         v
AuthorizationFilter yêu cầu authenticated()
         |
         v
ExceptionTranslationFilter kích hoạt authentication entry point
         |
         v
302 /sign-in
         |
         v
GET /sign-in (permitAll)
         |
         v
200 HTML có form và CSRF hidden input
         |
         v
POST /perform-login
  username=an
  password=training-pass
  _csrf=<token từ form>
         |
         v
UsernamePasswordAuthenticationFilter
         |
         v
AuthenticationManager / DaoAuthenticationProvider
         |
         +-- password sai -> 302 /sign-in?error
         |
         +-- password đúng -> SecurityContext + session
                                     |
                                     v
                         302 /dashboard (saved request)
```

Trong browser flow thông thường, `SavedRequestAwareAuthenticationSuccessHandler` có thể ưu tiên URL người dùng đã yêu cầu trước khi bị chuyển sang login. Vì vậy sau khi đăng nhập từ `/dashboard`, ứng dụng thường đưa về `/dashboard`; nếu người dùng vào thẳng trang login, `defaultSuccessUrl` có thể là đích mặc định.

`defaultSuccessUrl("/dashboard", false)` nghĩa là không ép luôn tới dashboard trong mọi trường hợp. Nếu chọn tham số `true`, request được lưu có thể bị bỏ qua; cần quyết định theo UX của sản phẩm.

### Vì sao login dùng POST?

Credential là dữ liệu nhạy cảm. Gửi username/password bằng GET query string có thể làm lộ chúng trong URL, browser history, proxy logs, analytics hoặc referrer. Spring Security form login tiêu chuẩn xử lý **HTTP POST** tại login processing URL. Ứng dụng thực phải dùng HTTPS; POST đơn lẻ không mã hóa network traffic.

## 5. Cấu hình SecurityFilterChain: public vừa đủ

Ví dụ cấu hình sau tương ứng bộ file ở phần sau.

```java
package com.example.customlogin;

import jakarta.servlet.DispatcherType;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("an")
                .password(encoder.encode("training-pass"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        // Cho phép container hiển thị lỗi phù hợp.
                        .dispatcherTypeMatchers(DispatcherType.ERROR)
                            .permitAll()

                        // MVC page tự tạo cho anonymous.
                        .requestMatchers(HttpMethod.GET, "/sign-in")
                            .permitAll()

                        // Assets và nội dung thật sự public.
                        .requestMatchers(
                                "/css/**", "/images/**",
                                "/favicon.ico", "/public/**")
                            .permitAll()

                        .requestMatchers("/admin/**")
                            .hasRole("ADMIN")

                        // Dashboard và các URL còn lại cần login.
                        .anyRequest().authenticated())

                .formLogin(form -> form
                        .loginPage("/sign-in")
                        .loginProcessingUrl("/perform-login")
                        .usernameParameter("username")
                        .passwordParameter("password")
                        .failureUrl("/sign-in?error")
                        .defaultSuccessUrl("/dashboard", false)
                        .permitAll())

                .logout(logout -> logout
                        .logoutUrl("/sign-out")
                        .logoutSuccessUrl("/sign-in?logout")
                        .permitAll())

                // Không tắt CSRF. Spring Security bảo vệ
                // POST /perform-login và POST /sign-out.
                .build();
    }
}
```

### Phân tích từng phần

**`authorizeHttpRequests`:** rules được đánh giá theo thứ tự khai báo, rule đầu tiên khớp request quyết định authorization. Trong demo, `GET /sign-in` công khai, assets và `/public/**` công khai, `/admin/**` yêu cầu `ROLE_ADMIN`, còn các URL khác yêu cầu authenticated.

**`formLogin`:** `loginPage` là đường dẫn hiển thị form; `loginProcessingUrl` là POST do Spring Security filter xử lý. `permitAll()` của form login bảo đảm những URL liên quan login được phép đi vào filter/hiển thị; nó không tắt các security protections khác.

**`failureUrl`:** `/sign-in?error` vẫn cùng **path `/sign-in`**; query parameter không đòi thêm một controller mới. Template đọc `param.error` để hiện thông báo trung lập.

**`logout`:** `POST /sign-out` do `LogoutFilter` xử lý, không cần controller. Với CSRF mặc định, logout qua POST cần token và sau đó redirect về `/sign-in?logout`, trang công khai.

**`PasswordEncoder`:** demo dùng BCrypt để hash password in-memory. Không dùng plaintext hoặc `{noop}` trên production. User `an` được cấp `ROLE_USER` nên vào dashboard được, nhưng không thể mở `/admin/**`.

**`DispatcherType.ERROR`:** Spring Boot có thể dùng error dispatch tới `/error`. Khi lớp authorization kiểm tra cả ERROR dispatch, cho phép dispatcher type ERROR giúp hiện trang lỗi thay vì che lỗi thành một redirect/403 khó hiểu. Điều này không biến tất cả URL nghiệp vụ thành public.

**Không cần `csrf.disable()`:** ứng dụng form login dùng session cookie nên CSRF protection là thiết yếu. Thymeleaf tích hợp Spring Security có thể đưa hidden token vào form POST qua `th:action`.

### Vì sao không dùng requestMatchers("/**").permitAll()?

Vì điều đó làm mọi URL trông như public, kể cả account settings hoặc admin route nếu rule này nằm trước các rule hạn chế. `permitAll` cho URL login và assets phải **hẹp**, gắn với nhu cầu truy cập trước authentication.

## 6. Ví dụ hoàn chỉnh Spring Boot 4.1.2 + Thymeleaf

Ta tạo một ứng dụng có:

- `GET /sign-in`: trang login tự tạo.
- `POST /perform-login`: đường xử lý authentication bởi Spring Security.
- `GET /dashboard`: trang riêng của người đã login.
- `GET /public/about`: trang công khai.
- `GET /css/site.css`: CSS công khai.
- `POST /sign-out`: logout có CSRF.
- `GET /sign-in?error` / `?logout`: hiện thông báo.

**Dự án học tập:** Java 17+, Maven, Spring Boot 4.1.2, MVC/Security/Thymeleaf. Với production, dùng phiên bản được hỗ trợ và quản lý security advisories, lưu user qua repository/identity provider và không hardcode password.

### 6.1. Cây thư mục

```text
custom-login-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/customlogin/
        │   ├── CustomLoginApplication.java
        │   ├── SecurityConfiguration.java
        │   └── PageController.java
        └── resources/
            ├── templates/
            │   ├── sign-in.html
            │   ├── dashboard.html
            │   └── about.html
            └── static/
                └── css/
                    └── site.css
```

Không cần `application.properties` cho demo cơ bản: Spring Boot dùng cổng 8080 mặc định nếu chưa cấu hình lại.

### 6.2. File pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>custom-login-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot parent quản lý dependency versions tương thích. `spring-boot-starter-webmvc` dùng MVC Servlet; `spring-boot-starter-thymeleaf` giúp render file từ `src/main/resources/templates/`; Spring Security cung cấp filter chain, form processing và CSRF.

### 6.3. CustomLoginApplication.java

```java
package com.example.customlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomLoginApplication.class, args);
    }
}
```

### 6.4. SecurityConfiguration.java

Sử dụng nguyên class `SecurityConfiguration` đầy đủ ở **phần 5**, lưu vào:

```text
src/main/java/com/example/customlogin/SecurityConfiguration.java
```

Class có cùng package `com.example.customlogin` với `CustomLoginApplication` để Spring Boot component scan nhận được configuration bean. Không đặt thêm một SecurityFilterChain khác có match cùng URL nếu không kiểm soát thứ tự và phạm vi.

### 6.5. PageController.java

```java
package com.example.customlogin;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class PageController {

    @GetMapping("/sign-in")
    String login() {
        return "sign-in";
    }

    @GetMapping("/dashboard")
    String dashboard(Authentication authentication, Model model) {
        model.addAttribute("username", authentication.getName());
        return "dashboard";
    }

    @GetMapping("/public/about")
    String about() {
        return "about";
    }
}
```

**Không có `@PostMapping("/perform-login")`:** username/password đến Spring Security `UsernamePasswordAuthenticationFilter`. Controller chỉ phục vụ HTML pages.

Với `/dashboard`, filter chain yêu cầu authenticated trước khi MVC vào method, nên `Authentication` dự kiến là người dùng đã xác thực. Không đưa password hash hoặc raw authentication object vào model; chỉ xuất dữ liệu hiển thị an toàn.

### 6.6. templates/sign-in.html

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Đăng nhập</title>
    <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
<main class="container">
    <h1>Đăng nhập</h1>

    <p th:if="${param.error}" class="alert" role="alert">
        Thông tin đăng nhập không hợp lệ.
    </p>

    <p th:if="${param.logout}" class="message" role="status">
        Bạn đã đăng xuất.
    </p>

    <form th:action="@{/perform-login}" method="post">
        <label for="username">Tên đăng nhập</label>
        <input id="username" type="text" name="username"
               autocomplete="username" required>

        <label for="password">Mật khẩu</label>
        <input id="password" type="password" name="password"
               autocomplete="current-password" required>

        <button type="submit">Đăng nhập</button>
    </form>

    <p><a th:href="@{/public/about}">Thông tin công khai</a></p>
</main>
</body>
</html>
```

**Điểm cần quan sát:**

- `th:action="@{/perform-login}"` khớp `loginProcessingUrl("/perform-login")`.
- `method="post"` là phương thức form login.
- Input name chính xác là `username` và `password`.
- Thymeleaf tích hợp với Spring MVC/Spring Security sẽ đưa CSRF token vào form POST thông qua cơ chế `RequestDataValueProcessor`; kiểm tra HTML **đã render** để xác nhận có hidden input `_csrf`.
- `th:if="${param.error}"` hiển thị thông báo **chung**, không tiết lộ “username có tồn tại hay không”.
- Các query `?error` / `?logout` không cần route riêng; controller vẫn xử lý path `/sign-in`.
- CSS lấy từ `/css/site.css`; path phải được phép khi chưa authenticated.
- `autocomplete` hỗ trợ password manager, không phải chỉ dấu bảo mật thay cho HTTPS.

**Không đưa raw password vào hidden input, query URL hoặc log.** Không thêm text “Tài khoản này tồn tại nhưng mật khẩu sai” cho user chưa xác thực, vì điều đó hỗ trợ dò username.

### 6.7. templates/dashboard.html

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Dashboard</title>
    <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
<main class="container">
    <h1>Dashboard</h1>
    <p>Xin chào <strong th:text="${username}">người dùng</strong>.</p>

    <p>Trang này yêu cầu một phiên đăng nhập hợp lệ.</p>

    <form th:action="@{/sign-out}" method="post">
        <button type="submit">Đăng xuất</button>
    </form>
</main>
</body>
</html>
```

Logout dùng **POST form**, Thymeleaf cũng bổ sung CSRF token cho form. `logoutUrl("/sign-out")` của Spring Security xử lý request; không cần controller `@PostMapping("/sign-out")`. Sau logout, URL `/sign-in?logout` vẫn public để trình duyệt hiển thị thông báo thành công.

### 6.8. templates/about.html

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Giới thiệu</title>
    <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
<main class="container">
    <h1>Trang công khai</h1>
    <p>Bạn đọc được trang này mà không cần đăng nhập.</p>
    <p><a th:href="@{/sign-in}">Đến trang đăng nhập</a></p>
</main>
</body>
</html>
```

### 6.9. static/css/site.css

```css
body {
    font-family: system-ui, sans-serif;
    background: #f7f8fc;
    color: #172033;
    line-height: 1.5;
}

.container {
    max-width: 420px;
    margin: 48px auto;
    padding: 28px;
    border: 1px solid #dce2ee;
    border-radius: 12px;
    background: white;
}

label, input {
    display: block;
    width: 100%;
    box-sizing: border-box;
}

label { margin-top: 16px; }

input {
    margin-top: 6px;
    padding: 10px;
    border: 1px solid #aeb8ca;
    border-radius: 6px;
}

button {
    margin-top: 22px;
    padding: 10px 16px;
    cursor: pointer;
}

.alert { color: #9b1c1c; }
.message { color: #205d32; }
```

Đặt CSS trong `src/main/resources/static/css/site.css`, Spring Boot tự phục vụ tại URL `/css/site.css`. Nó không nằm dưới `templates/`. Khi dùng CDN hoặc static files ở một host khác, cần xem policy CORS/CSP, nhưng đừng dùng `permitAll("/**")` để chữa lỗi tải CSS.

## 7. Chạy ví dụ và quan sát kết quả

Yêu cầu: JDK 17+, Maven 3.9+ hoặc Maven wrapper của project, khả năng tải Maven dependencies. Tại root `custom-login-demo/`:

```bash
mvn spring-boot:run
```

Nếu có Maven wrapper:

```bash
./mvnw spring-boot:run
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Mở browser và vào:

```text
http://localhost:8080/sign-in
```

Bạn sẽ thấy trang login được tự xây dựng, CSS tải được, form nhập username và password. Dữ liệu demo:

| Username | Password demo | Role |
| --- | --- | --- |
| `an` | `training-pass` | `ROLE_USER` |

**Chỉ dùng local.** Password này là dữ liệu minh họa và nằm trong source code; không dùng cho môi trường công khai. Production cần mật khẩu được đặt/đổi bởi người dùng, hash được lưu trong kho có kiểm soát, chống brute force và MFA khi cần.

### 7.1. Kiểm tra trước khi login

Thử bằng trình duyệt:

- `/sign-in`: trả form 200, không redirect vòng.
- `/public/about`: trả trang công khai 200.
- `/css/site.css`: trả CSS 200, Content-Type thuộc CSS.
- `/dashboard`: redirect tới trang `/sign-in` nếu chưa có session.
- `/admin/test`: khi chưa đăng nhập cũng đưa tới login; khi đăng nhập với An thì bị từ chối vì An thiếu `ROLE_ADMIN`.

Có thể kiểm tra header/status ban đầu bằng curl:

```bash
curl -i http://localhost:8080/sign-in
curl -i http://localhost:8080/public/about
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/dashboard
```

**Kết quả dự kiến:** ba request đầu có HTTP 200; request cuối có redirect HTTP 302 tới `/sign-in`. `curl -i` không tự follow redirect trừ khi thêm `-L`. Nếu dùng PowerShell và alias `curl` hoạt động khác, dùng `curl.exe`.

### 7.2. Kiểm tra CSRF token trong HTML đã render

Mở Developer Tools, xem response hoặc `View Page Source` của `GET /sign-in`. Với Thymeleaf + Spring Security đúng cấu hình, form POST sẽ có hidden input đại diện CSRF token, thường có tên `_csrf`.

Ví dụ **hình dạng** của HTML sau render:

```html
<form action="/perform-login" method="post">
    <input name="username" type="text">
    <input name="password" type="password">
    <input type="hidden" name="_csrf" value="...token do server tạo...">
    <button type="submit">Đăng nhập</button>
</form>
```

Đoạn này là **mẫu HTML mô tả**, không phải token dùng được. Token thật khác nhau theo session/request và cơ chế bảo vệ BREACH. Không hardcode token, không chép từ ví dụ vào client hoặc lưu cùng source code. Thymeleaf tự tích hợp `CsrfRequestDataValueProcessor` cho form POST khi `th:action` được xử lý đúng.

### 7.3. Đăng nhập đúng

Trong browser, nhập `an` / `training-pass` rồi submit. Trình duyệt gửi `POST /perform-login` có cookie CSRF/session phù hợp. Spring Security xác minh password, tạo SecurityContext/session và redirect tới `/dashboard` (hoặc saved request nếu trước đó bạn vào resource bảo vệ).

`GET /dashboard` sau login hiển thị lời chào `an`. Đây là **kết quả dự kiến của demo**. Framework có thể thêm cookie/session headers khác nhau giữa container và môi trường; không đặt assertion cứng về toàn bộ `Set-Cookie` response.

### 7.4. Đăng nhập sai

Nhập `an` và password khác `training-pass`. Kết quả bình thường là HTTP 302 tới `/sign-in?error`, sau đó trang login hiển thị “Thông tin đăng nhập không hợp lệ.” Không trả lỗi chi tiết “username tồn tại nhưng mật khẩu sai”.

### 7.5. Đăng xuất

Từ dashboard, bấm `Đăng xuất`. Form POST tới `/sign-out` kèm CSRF token, Security logout handler sẽ clear context/invalidate session tương ứng, rồi redirect `/sign-in?logout`.

Sau đó thử `/dashboard`: lại chuyển tới login. Nếu có nhiều thiết bị, logout hiện tại không tự có nghĩa đã thu hồi mọi session trên thiết bị khác; đó là bài toán quản lý session/revocation riêng.

### 7.6. Gửi POST không có CSRF token

```bash
curl -i -X POST \
  -d "username=an&password=training-pass" \
  http://localhost:8080/perform-login
```

Với CSRF mặc định, request POST **không có token hợp lệ** thường nhận HTTP 403, ngay cả khi username/password đúng. Đây không phải bằng chứng controller POST bị thiếu; đó là security filter từ chối request thiếu CSRF. Không tắt CSRF chỉ để cURL trả 302.

Để tự thử login bằng HTTP client thay browser, client phải GET login page, giữ cookie/session, lấy token CSRF thật từ form đã render, rồi POST lại token + cookie + form fields với encoding đúng. Browser và Thymeleaf làm việc này tự nhiên hơn; trong test tự động dùng Spring Security Test CSRF support.

## 8. Những URL cần permitAll ngoài trang login

### 8.1. CSS, JS, hình ảnh và favicon

Trang login có thể dùng:

```text
/sign-in
/css/site.css
/js/login.js
/images/logo.svg
/favicon.ico
```

Nếu thực sự tồn tại và cần cho anonymous, các resource này có thể được cho phép bằng matcher hẹp:

```java
.requestMatchers(
        "/css/**",
        "/js/**",
        "/images/**",
        "/favicon.ico")
.permitAll()
```

Đây là **mảnh DSL**, cần đặt trong `authorizeHttpRequests` theo đúng thứ tự. Không cho phép toàn bộ `/assets/**` nếu trong đó có tệp riêng tư chưa được phân loại. Không đặt tài liệu nội bộ chứa thông tin bí mật vào `src/main/resources/static` chỉ vì muốn Thymeleaf tải được.

### 8.2. Trang giới thiệu và hỗ trợ công khai

`/public/about`, `/public/help` hoặc trang điều khoản có thể public nếu không tiết lộ dữ liệu tài khoản. Với trang hỗ trợ yêu cầu login, không nên cho phép chỉ vì có chữ “help” trong URL; phải xem dữ liệu và hành động thật.

### 8.3. Đăng ký tài khoản

`GET /register` phải truy cập được nếu người dùng chưa có tài khoản cần mở form. `POST /register` cũng có thể không yêu cầu session đăng nhập; nhưng “public” không có nghĩa server cho phép tạo arbitrary roles, bỏ CAPTCHA/rate limit, không xác minh email hoặc không kiểm tra uniqueness.

Một API đăng ký phải tự kiểm tra tất cả thuộc tính đầu vào. **Không nhận `role=ADMIN` từ HTML form rồi lưu nó làm quyền server**.

### 8.4. Quên mật khẩu và reset password

`GET /forgot-password` thường public. Form yêu cầu email có thể POST `/forgot-password` mà không yêu cầu login, nhưng cần chống account enumeration và abuse.

`GET /reset-password?token=...` có thể được phép để người dùng chưa đăng nhập mở form reset. `POST /reset-password` cần token reset còn hạn, chưa dùng, được ràng buộc đúng account và có các protection phù hợp; token reset không được coi là token đăng nhập. Nếu có cookie/session browser, bảo vệ CSRF theo thiết kế thay vì `csrf.disable()` toàn ứng dụng.

### 8.5. Error page và dispatcher types

Trong Servlet stack, error dispatch có thể tới `/error`. Spring Security kiểm tra authorization cho nhiều dispatcher types, không chỉ REQUEST. Tùy ứng dụng, cho phép `DispatcherType.ERROR` và `FORWARD` có thể giúp view/error handler được render đúng.

**Không được** coi việc permit error dispatch là lý do bỏ authorization cho URL nghiệp vụ ở REQUEST. Nếu app có nhiều servlet/dispatcher hoặc forward tới endpoint nhạy cảm, cần test cụ thể, không mở rộng rule tùy tiện.

### 8.6. OAuth/OIDC callback nếu dự án có

Khi dùng OAuth2 Login, callback/authorization code handling thuộc các security filters theo giao thức. Không tự tạo `permitAll("/oauth2/**")` thật rộng mà không hiểu các endpoint, state/nonce, redirect URI và chain đang sử dụng. Custom login HTML có thể có link `/oauth2/authorization/{registrationId}`, nhưng cơ chế OAuth2 sẽ quản lý phần xác thực và chống CSRF theo giao thức riêng.

## 9. permitAll khác gì web.ignoring?

Cả hai cách có thể khiến một URL trông như public, nhưng **không tương đương**.

`authorizeHttpRequests(...permitAll())` cho request **tiếp tục đi qua Spring Security filter chain**. Nó bỏ yêu cầu authentication ở authorization nhưng vẫn có thể được áp dụng:

- Security headers.
- CSRF protection.
- Session/security context handling.
- Các filter bảo vệ khác được cấu hình.
- Cơ chế ghi nhận security events hoặc các policy khác trong chain.

`WebSecurityCustomizer.web.ignoring()` loại một request khỏi Spring Security filter chain. Nếu dùng quá rộng cho trang login hoặc endpoint POST public, bạn có thể bỏ qua các lớp bảo vệ cần thiết.

Với trang login và static assets, khuyến nghị hiện nay thường là **`permitAll` thay vì ignore**, trừ khi có một lý do kỹ thuật rõ để hoàn toàn bypass filter chain. Chỉ muốn sửa “CSS trả 302 về login” **không cần** phải ignore toàn bộ `/css/**`.

Ví dụ sự khác biệt:

```text
GET /css/site.css và permitAll:
  -> Qua Spring Security filters
  -> Không yêu cầu Authentication ở authorization
  -> Static Resource Handler trả nội dung

GET /css/site.css và ignoring:
  -> Bỏ qua SecurityFilterChain
  -> Các filter/headers của Spring Security không áp dụng ở đó
```

Đừng dùng ignore cho `/login` hay `/register` như một cách chữa lỗi cấu hình authentication/CSRF mà chưa phân tích hệ quả.

## 10. Các biến thể của URL và cách giữ chúng đồng bộ

Không nhất thiết phải dùng `/sign-in` và `/perform-login`. Ví dụ team muốn giữ cùng path `/login` cho GET/POST:

```java
.formLogin(form -> form
        .loginPage("/login")
        .loginProcessingUrl("/login")
        .failureUrl("/login?error")
        .permitAll())
```

Đây là cấu hình phổ biến và hợp lệ: GET do MVC render, POST do filter xử lý. Tuy nhiên để học rõ trách nhiệm, ví dụ chính cố ý tách hai URL.

Nếu đổi đường dẫn, phải đồng bộ:

| Thành phần | Ví dụ | Nếu lệch |
| --- | --- | --- |
| `loginPage(...)` | `/sign-in` | Security redirect sang URL không có trang |
| `@GetMapping(...)` | `/sign-in` | 404 hoặc redirect loop |
| `th:action` | `@{/perform-login}` | POST gửi sai URL |
| `loginProcessingUrl(...)` | `/perform-login` | Filter không bắt đúng POST |
| `usernameParameter(...)` | `username` | Provider nhận username trống |
| `passwordParameter(...)` | `password` | Provider nhận password trống |
| `failureUrl(...)` | `/sign-in?error` | Failure redirect đến trang không hiển thị |
| `logoutUrl(...)` | `/sign-out` | Logout button không kích hoạt LogoutFilter |
| `logoutSuccessUrl(...)` | `/sign-in?logout` | Redirect tới path sai/không public |

Thymeleaf `@{/...}` hỗ trợ tạo URL dựa trên context path, giúp ứng dụng chạy dưới `/app` mà không phải hardcode link thiếu prefix. Khi ứng dụng nằm sau reverse proxy hoặc `server.servlet.context-path`, hãy kiểm tra base path và forwarded headers; đừng tự nối chuỗi tuyệt đối không qua context.

### Có cần permitAll GET /perform-login?

Không. Trong demo, `POST /perform-login` là điểm cần được authentication filter chấp nhận với CSRF hợp lệ. `formLogin(...permitAll())` làm các login URLs liên quan được phép; không có MVC GET page cho `/perform-login`. Mở GET processing path rộng không mang ý nghĩa tạo trang login. **Cần phân biệt quyền ở authorization với method matcher của filter.**

## 11. Redirect loop: nguyên nhân và cách chẩn đoán

Triệu chứng: browser báo “too many redirects”, network tab lặp `302 /sign-in` hoặc response không tải được form.

### Nguyên nhân A — login page chưa public

```text
GET /sign-in
  -> AuthenticationEntryPoint
  -> 302 /sign-in
  -> GET /sign-in
  -> ... lặp
```

Giải pháp: đảm bảo GET login page có `permitAll` và form login có `permitAll()`. Kiểm tra rule nào được match **đầu tiên**, đặc biệt với `anyRequest().authenticated()`.

### Nguyên nhân B — SecurityFilterChain khác đang bắt URL

Ứng dụng có `@Order(1)` chain cho `/**` với authenticated, còn form login public được cấu hình trong chain `@Order(2)`. Chain đầu có thể bắt cả `/sign-in`, khiến chain dưới không được thực thi.

Giải pháp: kiểm tra `securityMatcher` và thứ tự các `SecurityFilterChain`, test URL login/processing thuộc đúng chain. Không chỉ xem một bean config rồi kết luận toàn app an toàn.

### Nguyên nhân C — MVC route không tồn tại

`loginPage("/sign-in")` chỉ đặt URL; không sinh controller. Nếu thiếu `@GetMapping("/sign-in")` hoặc template sai đường dẫn, có thể ra 404/error response chứ không phải một form login.

### Nguyên nhân D — Session/cookie không được duy trì

Login đúng có thể 302 về dashboard, nhưng browser lại bị redirect về login vì session cookie không được lưu/gửi (Secure, SameSite, domain, path, reverse proxy, HTTP/HTTPS mismatch) hoặc application cấu hình `SessionCreationPolicy.STATELESS` ngoài ý muốn.

### Nguyên nhân E — Login xử lý không đúng

Nếu form submit tới URL khác `loginProcessingUrl`, POST có thể không được authentication filter bắt; lỗi thường là 404, 405, 403 CSRF hoặc redirect bất ngờ.

### Nguyên nhân F — Saved request hoặc success URL không hợp lý

Nếu success handler luôn redirect về một URL lại yêu cầu flow khác, có thể tạo vòng chuyển hướng. Kiểm tra saved request cache, `defaultSuccessUrl`, proxy redirects và rule cho target.

### Cách debug có hệ thống

1. Mở Developer Tools → Network, bật Preserve log.
2. Quan sát chuỗi `GET /dashboard` → `302 /sign-in` → `GET /sign-in`.
3. Kiểm tra `/sign-in` trả HTTP 200 hay lại 302.
4. Kiểm tra response HTML thực sự có form, CSS không redirect về login.
5. Khi submit, kiểm tra `POST /perform-login` có csrf cookie/hidden token, status và `Location` nào.
6. Kiểm tra browser có gửi lại session cookie ở request sau login.
7. Với nhiều filter chain, xem DEBUG logs về chain nào match.
8. Không bật logging raw password, session cookie hoặc CSRF token trên production để debug.

## 12. CSRF: permitAll không tắt kiểm tra POST

Một ngộ nhận phổ biến: “`POST /perform-login` cần public nên phải tắt CSRF”. Điều này sai.

- **Authorization:** request login chưa có user authenticated, do vậy endpoint xử lý login không thể đòi trước đó đã đăng nhập.
- **CSRF:** một browser có thể bị trang ngoài cố tình submit form thay người dùng. CSRF protection chống những request thay đổi trạng thái không đến từ form hợp lệ.

Vì vậy, `permitAll` cho login không loại bỏ `CsrfFilter`. Spring Security mặc định bảo vệ login POST và logout POST.

### Vai trò của Thymeleaf

Thymeleaf tích hợp với `RequestDataValueProcessor` trong Spring MVC/Security. Khi dùng `th:action` trên form POST, framework thường chèn CSRF hidden input. Khi render HTML, cần thấy tên thường là `_csrf` và giá trị token đang hợp lệ.

**Không nên** copy mã HTML tĩnh với một token CSRF cố định. Token cần gắn với session/request strategy và được xác minh ở server. Nếu viết frontend không dùng Thymeleaf, bạn phải tích hợp CSRF token phù hợp qua một kênh an toàn và thêm vào POST.

### Tại sao POST bằng curl bị 403?

Một request:

```bash
curl -i -X POST -d "username=an&password=training-pass" \
  http://localhost:8080/perform-login
```

thường bị 403 nếu thiếu CSRF token hợp lệ, cho dù password đúng. Đây là một bài test hữu ích chứng minh `permitAll` không có nghĩa “bỏ toàn bộ bảo vệ”.

### Token sau login/logout

Spring Security có thể làm mới/clear CSRF token khi authentication hoặc logout thành công. Một frontend AJAX dùng CSRF token cũ sau login có thể bị 403 ở thao tác kế tiếp. Nếu làm SPA hoặc AJAX, cần luồng refresh token mới sau login/logout phù hợp, không tắt CSRF như một workaround.

## 13. Public route và mức độ rủi ro thực tế

| Loại URL | Có thể public? | Bảo vệ khác cần có |
| --- | --- | --- |
| Trang login GET | Có | CSP/HTTPS, không cache thông tin nhạy cảm |
| Login POST | Không yêu cầu login trước | CSRF, rate limiting, credential validation, audit |
| Trang register GET | Có | Không đưa data nội bộ |
| Register POST | Tùy nghiệp vụ | CSRF, email verification, chống spam, uniqueness |
| Forgot password GET/POST | Có thể | Phản hồi chung chống user enumeration, rate limits |
| Reset password GET/POST | Có thể | Token một lần, expiry, bind account, CSRF policy |
| Static CSS/logo/JS login | Có | Kiểm soát nội dung và source |
| Public docs/terms | Có | Không rò tài liệu nội bộ |
| Profile/me | Không | Authenticated và owner checks |
| Account settings/change password | Không | Authentication, reauth/MFA khi cần, CSRF |
| Admin | Không | Quyền admin và resource authorization |
| Actuator/metrics | Thường không | Access control vận hành riêng |
| Error dispatch | Thường có thể permit | Không để error page lộ stack trace/secrets |

**Không dùng tên URL để suy ra dữ liệu vô hại.** Một endpoint bắt đầu bằng `/public/` nhưng trả toàn bộ user emails vẫn có thể là lỗ hổng thiết kế. Public route chỉ mô tả auth requirement, còn response content và nghiệp vụ phải được security review.

### Tránh user enumeration

Trang login lỗi nên dùng thông điệp chung như “Thông tin đăng nhập không hợp lệ.”, không trả “tài khoản không tồn tại” khác “mật khẩu sai”. Tương tự `/forgot-password` nên trả lời trung lập để không tiết lộ địa chỉ email đã đăng ký, đồng thời có rate limiting để tránh spam.

## 14. HTTP 302, 401, 403 và 404 trên form login

Các mã thường được quan sát:

| Kịch bản | Kết quả thường gặp | Ghi chú |
| --- | --- | --- |
| Anonymous GET `/sign-in` | 200 | Trang login public |
| Anonymous GET `/dashboard` | 302 → sign-in | Browser form login |
| Form login credential sai, CSRF hợp lệ | 302 → `/sign-in?error` | Failure handler |
| Form login credential đúng, CSRF hợp lệ | 302 → saved URL/dashboard | Success handler |
| POST login thiếu CSRF | 403 | CsrfFilter từ chối trước authentication |
| Đã authenticated, thiếu `ROLE_ADMIN` | 403 | Authorization |
| CSS bị chặn bởi security | Có thể 302 → login | Browser thấy CSS lỗi/HTML thay CSS |
| Controller GET login không tồn tại | 404 hoặc error flow | `loginPage` không tự sinh MVC route |
| URL processing nhận sai method/path | 404/405/403 hoặc route khác | Phụ thuộc matcher/filter/controller |
| API Basic/Bearer chưa có credential | Thường 401 | Khác UX form-login redirect |

Không nên viết test ép mọi lỗi authentication trả 401 khi ứng dụng đang dùng form login; redirect 302 là hành vi browser-oriented bình thường. Nếu app vừa có API vừa có pages, nên tách entry point/chain theo loại traffic phù hợp.

## 15. Kiểm thử end-to-end cho trang login và các URL công khai

Chỉ test controller `GET /sign-in` trả view name là chưa đủ; phải chạy qua **Spring Security filter chain** với session/CSRF.

### Ma trận kiểm thử

| Test | Input | Assertion quan trọng |
| --- | --- | --- |
| GET login anonymous | `GET /sign-in` | HTTP 200, HTML có form |
| Login failure page | `GET /sign-in?error` | HTTP 200, thông báo chung |
| Public about | `GET /public/about` | HTTP 200 |
| CSS public | `GET /css/site.css` | HTTP 200, CSS body |
| Dashboard anonymous | `GET /dashboard` | 302 tới `/sign-in` |
| Login processing POST | username/password + CSRF hợp lệ | Filter xử lý, 302 sau authentication |
| Credential sai | username sai/password sai + CSRF | 302 về `/sign-in?error` |
| POST thiếu CSRF | Chỉ username/password | 403 |
| Dashboard sau login | Cookie session hợp lệ | 200, tên principal phù hợp |
| Logout POST | Cookie + CSRF hợp lệ | 302 `/sign-in?logout`, session bị xóa |
| Logout rồi vào dashboard | Cookie cũ | 302 về login |
| Admin route với `ROLE_USER` | Login An rồi GET `/admin/**` | 403 nếu endpoint được ánh xạ |
| Trang login có CSS | Browser load link trong HTML | Không redirect CSS về login |
| Duplicate security chains | Nhiều `@Order`/`securityMatcher` | Login nằm trong chain phù hợp |
| Context path khác root | Deploy dưới `/app` | Thymeleaf URLs giữ context path |
| CSRF token sau login/logout | Dùng token mới | POST kế tiếp không 403 bất ngờ |
| Session fixation | Login mới | Session ID được xử lý theo policy |
| Open redirect | Input redirect URL lạ | Không redirect tới domain không tin cậy |
| Forgot/reset nếu có | Public pages & POST | Token verification và rate limit riêng |

### Test với Spring Security Test và MockMvc

Khi xây test của dự án thật, có thể dùng `MockMvc` với Spring Security Test. Dưới đây là **mảnh code tham khảo** chứ không phải file test hoàn chỉnh (cần các imports, annotation test và test starter theo version của Spring Boot):

```java
mockMvc.perform(get("/sign-in"))
        .andExpect(status().isOk());

mockMvc.perform(get("/dashboard"))
        .andExpect(status().is3xxRedirection());

mockMvc.perform(post("/perform-login")
        .param("username", "an")
        .param("password", "training-pass")
        .with(csrf()))
        .andExpect(status().is3xxRedirection());

mockMvc.perform(post("/perform-login")
        .param("username", "an")
        .param("password", "training-pass"))
        .andExpect(status().isForbidden());
```

Các method `get`/`post` đến từ `MockMvcRequestBuilders`, `status` từ `MockMvcResultMatchers` và `csrf` từ `SecurityMockMvcRequestPostProcessors`. Ở Boot 4, test dependencies được chia theo module; hãy chọn các starter test tương ứng MVC/Security do Boot quản lý thay vì sao chép dependency cũ mù quáng.

Đối với login/session, test có thể cần giữ cùng `MockHttpSession` khi gửi request kế tiếp; không chỉ gọi hai `mockMvc.perform` độc lập rồi mặc định chúng dùng chung cookie.

### Kiểm tra browser thay vì chỉ dùng curl

Một flow thực tế:

1. Dùng cửa sổ ẩn danh mở `/dashboard`.
2. Xác nhận redirect `/sign-in`.
3. Xác nhận HTML, CSS và CSRF token tải được mà không cần login.
4. Nhập sai password và kiểm tra failure message chung.
5. Nhập `an`/`training-pass`, kiểm tra URL đích và dashboard.
6. Mở một tab mới, truy cập `/dashboard` và xác nhận session được duy trì.
7. Bấm logout; thử lại dashboard và kiểm tra đã mất quyền truy cập.
8. Mở Network tab xác nhận static assets không bị redirect về sign-in.
9. Kiểm tra cookie `Secure`/`HttpOnly`/`SameSite` và HTTPS theo môi trường triển khai.

## 16. Session, cookie, reverse proxy và môi trường thực tế

Một trang login đã public nhưng đăng nhập xong vẫn quay lại login có thể do session không được duy trì:

- Reverse proxy terminate TLS nhưng app nhận forwarded scheme sai, redirect `http://` ↔ `https://`.
- Cookie domain/path không khớp host/context path.
- Cookie `Secure` không được gửi qua HTTP hoặc browser chặn third-party cookies.
- App cấu hình `SessionCreationPolicy.STATELESS` trong khi muốn browser session.
- Session store trên một node nhưng request sau đến node khác không có state.
- Login success handler redirect tới host/domain sai hoặc URL ngoài ý muốn.
- CSRF token thuộc session khác vì client không giữ cookie giữa GET và POST.

Spring Security thường bảo vệ session fixation trong flow chuẩn; không nên tùy tiện tắt session management hoặc tự tạo session rồi copy SecurityContext mà bỏ qua security strategies. Với browser app có load balancer, cần một session store dùng chung hoặc chiến lược affinity có giới hạn rõ.

### Không dùng session fixation workaround nguy hiểm

Khi đăng nhập thành công, session ID có thể thay đổi/rotate để chống session fixation. Đây là hành vi có chủ đích. Nếu client test giữ cố định cookie session cũ rồi coi login thất bại, hãy xem lại cách lưu `Set-Cookie` và gửi cookie mới; đừng vô hiệu hóa session fixation protection chỉ để test qua được.

### HTTPS, cookies và cache

Trang login và POST credential cần HTTPS, không chỉ production endpoint dữ liệu. Cookie phiên cần flags phù hợp. Không cache response có dữ liệu authentication state/CSRF trong shared proxy. Với asset tĩnh CSS, caching có thể hữu ích, nhưng phải tránh lẫn token/PII vào asset public.

## 17. Nhiều SecurityFilterChain trong cùng ứng dụng

Ví dụ một hệ thống vừa có browser pages vừa có REST API:

```text
SecurityFilterChain #1: /api/**
    -> Bearer token / HTTP Basic tùy giao thức
    -> stateless, thường trả 401 cho API

SecurityFilterChain #2: browser MVC pages
    -> formLogin custom /sign-in
    -> session-based, redirect 302 tới login
```

Điều quan trọng là:

- Chain nào match `GET /sign-in`?
- Chain nào match `POST /perform-login`?
- Chain nào match static `/css/**`, `/images/**`?
- URL login có bị một chain `/**` đứng trước bắt mất không?
- CSRF và CORS giữa API/browser có khác không?
- Có logout handler và entry point nào cho từng chain?

**Chỉ chain đầu tiên khớp request được áp dụng.** Nếu form login processing URL nằm ngoài `securityMatcher` của chain chứa `formLogin`, POST có thể không được `UsernamePasswordAuthenticationFilter` xử lý. Nếu một API chain đòi Bearer token bắt luôn `/sign-in`, browser có thể nhận 401 JSON thay vì trang login.

Khi cấu hình nhiều chain, khai báo `securityMatcher`/`@Order` tường minh, test từng public URL và ưu tiên để static/login routes được áp dụng bởi đúng chain. Không sử dụng `anyRequest().permitAll()` trong một chain tổng quát để che lỗi thứ tự.

## 18. Những sai lầm thường gặp

| Sai lầm | Triệu chứng/rủi ro | Cách khắc phục |
| --- | --- | --- |
| `loginPage` tự tạo nhưng chưa có MVC GET mapping | 404/không hiển thị form | Thêm `@GetMapping` và template |
| Trang login không được permit | Redirect loop | Form `permitAll()` và rule GET login công khai |
| Trang login public nhưng CSS không public | CSS nhận HTML/302 | Permit đúng static path |
| Form action khác processing URL | 404/405/login không chạy | Đồng bộ `th:action` và `loginProcessingUrl` |
| Nhầm controller POST là auth provider | Bỏ qua security pipeline | Để `UsernamePasswordAuthenticationFilter` xử lý |
| Input tên `email` nhưng không đổi `usernameParameter` | Login thất bại | Đồng bộ parameter names |
| Dùng GET truyền password | Lộ trong URL/log | POST + HTTPS |
| Bỏ CSRF vì POST login cần public | Login CSRF/session abuse | Giữ CSRF + hidden token |
| Dùng `permitAll("/**")` để chữa login loop | Mở toàn bộ tài nguyên | Matcher public hẹp |
| Dùng `web.ignoring("/**")` | Bỏ qua toàn bộ security filters | `permitAll` cho public paths |
| Quên `?error`/`?logout` hiển thị | UX khó hiểu | Template đọc query parameter |
| Trả thông báo “username không tồn tại” | User enumeration | Thông báo chung, rate limit |
| Logout qua GET dù CSRF bật | Không xử lý/logout sai | Form POST logout |
| Public reset endpoint không kiểm tra reset token | Chiếm đoạt account | Token một lần, TTL, kiểm chứng |
| Tin register role do client gửi | Privilege escalation | Gán role theo policy server |
| Đặt chain API trước chain login với matcher rộng | Login bị 401/redirect sai | Rà `securityMatcher`, thứ tự |
| Bật `STATELESS` cho form session | Login xong bị quên | Chọn session policy phù hợp |
| Reverse proxy cấu hình sai scheme | HTTP/HTTPS redirect loop | Forwarded headers, cookie flags |
| Bỏ qua ERROR dispatch | Lỗi bị biến thành access denied | Cấu hình dispatcher type hợp lý |
| Test controller không qua filter chain | False confidence | MockMvc + Spring Security integration |
| Dùng demo password trên production | Credential lộ | Account store/secret policy đúng |
| Không test anonymous GET login | Redirect loop lọt production | Integration test public routes |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `loginPage("/sign-in")` có tự sinh MVC controller hoặc file Thymeleaf không?  
**Trả lời:** Không. Ứng dụng phải cung cấp GET handler/template; Spring Security chỉ biết URL để redirect và điều phối form login.

**Câu 2.** Vì sao `GET /sign-in` phải truy cập được khi chưa có Authentication?  
**Trả lời:** Vì người dùng cần nhìn thấy form trước khi gửi credential. Nếu trang login cũng bị yêu cầu login, có thể xảy ra redirect loop.

**Câu 3.** `POST /perform-login` được xử lý ở đâu?  
**Trả lời:** Trong `UsernamePasswordAuthenticationFilter` khi URL/method khớp cấu hình; không cần controller POST riêng.

**Câu 4.** `formLogin(...permitAll())` có tự mở `/css/site.css` không?  
**Trả lời:** Không. Static assets cần được cấp rule công khai phù hợp.

**Câu 5.** Vì sao `permitAll` không đồng nghĩa tắt CSRF?  
**Trả lời:** Vì nó chỉ ảnh hưởng quyết định authorization, còn `CsrfFilter` vẫn bảo vệ unsafe methods như POST login/logout.

**Câu 6.** Nếu POST đúng password nhưng thiếu `_csrf` thì điều gì thường xảy ra?  
**Trả lời:** Request bị chặn 403 do CSRF trước khi authentication password.

**Câu 7.** Thymeleaf giúp gửi CSRF token như thế nào?  
**Trả lời:** Khi dùng `th:action` trên form POST với tích hợp Spring MVC/Security đúng, `RequestDataValueProcessor` thêm hidden CSRF input.

**Câu 8.** Trang login hiển thị nhưng CSS bị redirect về login. Sửa ở đâu?  
**Trả lời:** Kiểm tra static path thật và rule `permitAll` cho CSS, không mở mọi URL hoặc tắt security.

**Câu 9.** Vì sao không viết `@PostMapping("/perform-login")` tự kiểm tra password?  
**Trả lời:** Vì đã có bộ lọc, manager/provider và các chiến lược bảo mật; tự làm dễ xung đột hoặc bỏ sót protections.

**Câu 10.** Có nên permit toàn bộ `/admin/**` để login page tải nhanh hơn không?  
**Trả lời:** Không. Chỉ login/assets public; admin route vẫn yêu cầu quyền admin.

**Câu 11.** Khi nào `defaultSuccessUrl("/dashboard", false)` không đưa user thẳng tới dashboard?  
**Trả lời:** Khi Spring Security còn saved request hợp lệ (ví dụ user vào trang được bảo vệ trước login) và success handler ưu tiên request đó.

**Câu 12.** Logout qua `POST /sign-out` có cần CSRF không?  
**Trả lời:** Trong browser session flow với CSRF mặc định, có; Thymeleaf form POST có thể tự chèn token.

**Câu 13.** `permitAll` khác `web.ignoring` thế nào?  
**Trả lời:** `permitAll` vẫn đi qua SecurityFilterChain; ignoring bỏ qua chuỗi đó, có thể bỏ luôn security headers/CSRF/filter protections.

**Câu 14.** Nếu có hai SecurityFilterChain, chain nào chạy?  
**Trả lời:** Chain đầu tiên có matcher phù hợp request. Cần bảo đảm login page/processing nằm trong chain chứa cấu hình form login đúng.

**Câu 15.** Login thành công nhưng về dashboard lại bị redirect tới login. Nên kiểm tra gì?  
**Trả lời:** Session cookie, Secure/SameSite/path/domain, session policy, reverse proxy, store nhiều node, success URL và request thực tế.

## 20. Checklist thực hành trước khi triển khai

1. Liệt kê rõ các public paths: login GET, failure/logout landing page, CSS/JS/logo, nội dung công khai, signup/forgot/reset nếu có.
2. Phân biệt `loginPage` và `loginProcessingUrl`; form POST action phải khớp filter.
3. Đặt `formLogin(...permitAll())` và matcher public hẹp; các URL còn lại `authenticated()/hasRole` theo policy.
4. Tạo controller GET login và template thật; không tự tạo password-check controller POST trùng filter.
5. Dùng `th:action` để Thymeleaf tích hợp CSRF token trong POST; kiểm tra HTML rendered.
6. Giữ CSRF cho browser session; không disable chỉ để curl POST đơn giản.
7. Kiểm tra public assets có HTTP 200 và MIME type đúng, không nhận redirect/HTML khi trình duyệt tải CSS.
8. Không để admin/profile/account endpoints public chỉ vì tên giống trang hỗ trợ.
9. Nếu có register/forgot/reset, bảo vệ chống spam, enumeration, reset-token replay và CSRF theo threat model.
10. Dùng HTTPS, password hash, rate limiting/MFA khi cần, session cookie flags và session fixation protection.
11. Kiểm thử anonymous GET login, protected redirect, login success/failure, CSRF 403, logout POST và anonymous assets.
12. Rà thứ tự nhiều SecurityFilterChain, matcher servlet context, dispatcher ERROR/FORWARD và reverse proxy.
13. Không dùng `web.ignoring` diện rộng hay `anyRequest().permitAll()` để khắc phục lỗi.
14. Không log raw password, CSRF token, session cookie hoặc nội dung header credential.
15. Dùng account store thực và policy quản lý người dùng trong production; không giữ demo password.
16. Theo dõi các security advisories/version Spring Boot/Spring Security hiện hành và chạy regression tests.

## Kết luận

Trang đăng nhập tự tạo cần **một GET public để render form**, **một POST authentication processing URL do Spring Security xử lý**, và **các static/public resources thực sự cần để anonymous tải trang**. Hai URL login có vai trò khác nhau; phép `permitAll` chỉ bỏ yêu cầu authenticated ở bước authorization, không vô hiệu CSRF hoặc các bảo vệ khác.

Với Spring Security Servlet, cấu hình `loginPage`, `loginProcessingUrl`, `failureUrl`, `defaultSuccessUrl` và `permitAll` phải khớp controller/template, các asset paths và rule `anyRequest().authenticated()`. Dùng Thymeleaf giúp form POST mang CSRF token; test browser/session và filter chain thực tế để tránh redirect loop, 403 thiếu token và lỗi CSS bị chuyển về trang login.

**Ghi nhớ:** *Trang login và những thứ cần để hiển thị nó phải public. Nơi kiểm tra credential không cần người dùng đã đăng nhập từ trước, nhưng vẫn phải được bảo vệ bởi CSRF và authentication pipeline. Mọi tài nguyên nghiệp vụ còn lại cần authorization thích hợp.*

### Tài liệu tham khảo chính thức

- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF trong Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Boot — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
