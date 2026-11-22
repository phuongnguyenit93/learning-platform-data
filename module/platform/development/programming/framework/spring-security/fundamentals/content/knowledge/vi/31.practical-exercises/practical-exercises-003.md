# Xây đăng nhập biểu mẫu, phiên và đăng xuất an toàn

## 1. Mục tiêu của bài thực hành tổng hợp

Bài này xây dựng một ứng dụng **Spring Boot + Spring MVC + Spring Security (Servlet)** có màn hình đăng nhập bằng biểu mẫu HTML, giữ trạng thái đăng nhập bằng HTTP session, bảo vệ yêu cầu thay đổi trạng thái bằng CSRF token, đổi session ID sau xác thực và đăng xuất đúng cách. Sau bài học, người đọc cần giải thích được **vì sao một request được xem là đã đăng nhập**, **cookie và session lưu gì**, và **làm thế nào biết logout thực sự thu hồi quyền truy cập của phiên hiện tại**.

Tiêu chí nghiệm thu:

1. Khách chưa đăng nhập xem được trang công khai nhưng bị chuyển đến trang login khi mở tài nguyên bảo vệ.
2. Form `POST /login` mang `username`, `password` và CSRF token; mật khẩu đúng tạo phiên đăng nhập, mật khẩu sai không tạo phiên xác thực.
3. Session ID đổi khi xác thực thành công để giảm nguy cơ **session fixation**; request sau đó được nhận diện nhờ cookie phiên.
4. Trang bảo vệ hiển thị tên người dùng đã xác thực, lấy từ `Authentication` do Spring Security cung cấp.
5. Nút đăng xuất gửi **POST + CSRF token** đến `/logout`, làm mất hiệu lực session và không còn truy cập được trang bảo vệ với phiên cũ.
6. Có kiểm thử cho login thành công/thất bại, CSRF, truy cập ẩn danh, dùng lại session và logout.

Ví dụ cố định ở **Java 17, Spring Boot 3.5.0, Spring Security 6.5.x**, Maven và Thymeleaf. Đây là bản có phiên bản cụ thể để có thể tái tạo bài học; trong dự án thật hãy cập nhật lên bản vá Boot/Security được hỗ trợ. Spring Boot 4/Spring Security 7 có khác biệt cần đối chiếu tài liệu migration. Bài tập dùng `InMemoryUserDetailsManager` và mật khẩu demo; phần cuối giải thích yêu cầu thay thế khi triển khai thực tế.

## 2. Phân biệt các khái niệm trước khi viết code

| Khái niệm | Vai trò trong bài | Điều không nên nhầm |
|---|---|---|
| **Authentication** | Kết quả kiểm tra danh tính; Spring Security đặt principal và authorities vào `Authentication` | Không đồng nghĩa với session |
| **SecurityContext** | Chứa `Authentication` của request hiện tại | Không phải cookie mà browser tự hiểu |
| **HTTP session** | Dữ liệu phía server được gắn với một session ID | Không phải kho lưu mật khẩu thô |
| **`JSESSIONID`** | Cookie thông thường để trình duyệt gửi session ID cho máy chủ | Cookie không chứa nguyên `Authentication` hay password |
| **CSRF token** | Giá trị chống request giả mạo khi trình duyệt tự gửi cookie | Không thay thế xác thực mật khẩu hoặc TLS |
| **Session fixation** | Kẻ tấn công cố khiến nạn nhân đăng nhập với session ID đã biết | Khác với session hijacking/đánh cắp cookie |
| **Logout** | Thu hồi trạng thái xác thực của phiên hiện tại, dọn security context và dữ liệu liên quan | Chỉ redirect về trang login chưa đủ |
| **Session timeout** | Phiên không còn giá trị sau thời gian không hoạt động được cấu hình | Không đồng nghĩa cookie biến mất khỏi mọi browser |
| **Authorization** | Quyết định user đã đăng nhập có quyền truy cập một tài nguyên hay không | Xác thực thành công không có nghĩa là được mọi quyền |

**Luồng khái niệm:**

```text
A. Truy cập lần đầu
Browser -> GET /dashboard
        -> SecurityFilterChain thấy chưa xác thực
        -> 302 /login
        -> GET /login -> render form và CSRF token

B. Đăng nhập
Browser -> POST /login (username, password, _csrf)
        -> CsrfFilter kiểm tra token
        -> UsernamePasswordAuthenticationFilter
        -> AuthenticationManager / DaoAuthenticationProvider
        -> UserDetailsService + PasswordEncoder
        -> thành công: tạo Authentication, bảo vệ session fixation,
                         lưu SecurityContext vào session, redirect
        -> thất bại: xóa context của lần thử, redirect /login?error

C. Request sau login
Browser -> GET /dashboard + Cookie: JSESSIONID=...
        -> container tìm HTTP session
        -> Spring Security tải SecurityContext cho request
        -> AuthorizationFilter cho phép
        -> Controller nhận Authentication

D. Đăng xuất
Browser -> POST /logout + CSRF token + session cookie
        -> CsrfFilter xác minh
        -> LogoutFilter gọi các LogoutHandler
        -> invalidate session + clear authentication/context + CSRF cleanup
        -> 302 /login?logout
        -> GET /dashboard sau đó phải đăng nhập lại
```

Hai điểm quan trọng:

- **`POST /login` và `POST /logout` được Spring Security filter xử lý**, không cần tự tạo `@PostMapping` để so sánh password hoặc gọi `session.invalidate()`. Controller của ta chỉ render `GET /login` và các trang.
- Sau đăng nhập, browser không gửi lại username/password trên mỗi request session-based; browser gửi cookie định danh session, và server đọc trạng thái xác thực đã lưu. Vì vậy bảo vệ cookie, ngăn fixation và hết hạn session là thành phần của bảo mật xác thực.

## 3. Cấu trúc dự án chạy được

```text
session-login-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/sessionlogin/
    │   │   ├── SessionLoginApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PagesController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/
    │           ├── index.html
    │           ├── login.html
    │           └── dashboard.html
    └── test/java/com/example/sessionlogin/
        └── LoginSessionLogoutTest.java
```

### 3.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>session-login-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

`spring-boot-starter-web` cung cấp Spring MVC và Servlet container nhúng; `spring-boot-starter-security` cung cấp filter chain và các thành phần xác thực; Thymeleaf render form HTML và tích hợp CSRF token; hai dependency test phục vụ MockMvc và các matcher/helper của Spring Security.

### 3.2. `src/main/java/com/example/sessionlogin/SessionLoginApplication.java`

```java
package com.example.sessionlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLoginApplication.class, args);
    }
}
```

### 3.3. `src/main/java/com/example/sessionlogin/SecurityConfiguration.java`

```java
package com.example.sessionlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/dashboard", false)
                .failureUrl("/login?error")
                .permitAll()
            )
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .permitAll()
            )
            .csrf(withDefaults())
            .httpBasic(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        var learner = User.withUsername("learner")
            .password(encoder.encode("lesson-password-123"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}
```

**Phân tích từng cấu hình:**

- `authorizeHttpRequests` cho phép khách vào trang công khai và trang login; các URL khác yêu cầu authenticated. Nếu sau này có `/admin`, cần thêm `hasRole("ADMIN")` hoặc policy nghiệp vụ riêng.
- `loginPage("/login")` nói rằng **ứng dụng tự render trang login**. Khi thay form mặc định, phải có `GET /login` trong controller, và endpoint đó phải được truy cập ẩn danh; nếu không dễ tạo vòng chuyển hướng.
- `loginProcessingUrl("/login")` là URL mà `UsernamePasswordAuthenticationFilter` nhận HTTP POST. Không đặt `@PostMapping("/login")` để tự xử lý password.
- `defaultSuccessUrl("/dashboard", false)` chuyển về dashboard khi không có trang đích đã lưu; nếu người dùng ban đầu bị chặn ở một URL bảo vệ, Spring có thể điều hướng về URL ban đầu sau login. Đối số `false` bảo toàn cơ chế saved request; `true` sẽ luôn chọn dashboard.
- `failureUrl("/login?error")` chỉ hiển thị lỗi chung; đừng báo tài khoản có tồn tại hay không. Đường dẫn này là minh họa; production cần thêm rate limiting và theo dõi brute force.
- `sessionFixation(...changeSessionId())` yêu cầu Servlet container đổi session ID khi xác thực thành công, giữ thuộc tính session cần thiết. Với Servlet hiện đại đây vốn là cách bảo vệ mặc định; đặt tường minh để quan sát và học.
- `logout` sử dụng filter của framework để invalidate session, clear Authentication và redirect. `deleteCookies("JSESSIONID")` là dọn cookie bổ sung; **hiệu lực logout trên server đến từ session invalidation**, còn xóa cookie phụ thuộc đúng Path/Domain/cấu hình container.
- `csrf(withDefaults())` **giữ CSRF bật** cho các request thay đổi trạng thái. Đặc biệt cần cho login và logout dùng cookie/session.
- `httpBasic(...disable)` để demo chỉ dùng form login; nếu bật cả Basic, API clients có thể nhận hành vi challenge khác.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` lưu mật khẩu demo dưới dạng hash có tiền tố thuật toán như `{bcrypt}...`. Trong production mật khẩu người dùng phải được tạo/đổi theo quy trình an toàn và lưu tại DB/IdP; không chứa password demo cố định trong mã.
- Không đặt `SessionCreationPolicy.STATELESS`: nó không phù hợp mục tiêu **form login có session**.

### 3.4. `src/main/java/com/example/sessionlogin/PagesController.java`

```java
package com.example.sessionlogin;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PagesController {

    @GetMapping("/")
    String home() {
        return "index";
    }

    @GetMapping("/login")
    String login() {
        return "login";
    }

    @GetMapping("/dashboard")
    String dashboard(Authentication authentication, Model model) {
        model.addAttribute("username", authentication.getName());
        return "dashboard";
    }
}
```

Controller không tự kiểm tra cookie hay mật khẩu. Security filter đã quyết định `/dashboard` cần authenticated, nên khi controller chạy thành công, `Authentication` có principal đã xác thực. Tên tài khoản đưa vào model để Thymeleaf xuất bằng `th:text` (HTML escaping mặc định).

### 3.5. `src/main/resources/templates/index.html`

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang công khai</title>
</head>
<body>
    <h1>Trang công khai</h1>
    <p>Ai cũng xem được trang này.</p>
    <a th:href="@{/login}">Đăng nhập</a>
    <a th:href="@{/dashboard}">Vào dashboard</a>
</body>
</html>
```

### 3.6. `src/main/resources/templates/login.html`

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
    <h1>Đăng nhập</h1>

    <p th:if="${param.error}" role="alert">
        Thông tin đăng nhập không hợp lệ.
    </p>
    <p th:if="${param.logout}" role="status">
        Bạn đã đăng xuất.
    </p>

    <form th:action="@{/login}" method="post">
        <div>
            <label for="username">Tên đăng nhập</label>
            <input id="username" type="text" name="username"
                   autocomplete="username" required>
        </div>
        <div>
            <label for="password">Mật khẩu</label>
            <input id="password" type="password" name="password"
                   autocomplete="current-password" required>
        </div>
        <button type="submit">Đăng nhập</button>
    </form>
</body>
</html>
```

Form phải gửi `POST /login`, sử dụng đúng tên field `username` và `password`. Khi dùng Thymeleaf với Spring Security, `th:action` trên form POST sẽ đưa CSRF token thành input hidden vào HTML được render, tương đương:

```html
<!-- Chỉ minh họa phần được render; token thực tế thay đổi -->
<input type="hidden" name="_csrf" value="a-real-token-generated-by-server">
```

**Không điền giá trị cố định** cho CSRF token. Dùng DevTools → Elements/Network để thấy token do server phát hành; vì CSRF liên quan phiên và request, việc lấy token từ một cửa sổ khác hoặc sau khi session bị thay thường không hợp lệ. Nếu xây giao diện thuần JavaScript, cần cơ chế đọc/gửi token tương ứng và lưu ý token được làm mới sau authentication/logout.

### 3.7. `src/main/resources/templates/dashboard.html`

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Dashboard</title>
</head>
<body>
    <h1>Dashboard cần đăng nhập</h1>
    <p>Xin chào, <strong th:text="${username}">người dùng</strong>.</p>

    <form th:action="@{/logout}" method="post">
        <button type="submit">Đăng xuất</button>
    </form>
</body>
</html>
```

**Vì sao là form thay vì `<a href="/logout">`?** Với CSRF được bật, Spring Security đòi request POST kèm CSRF token để thực hiện logout; GET `/logout` có thể hiển thị trang xác nhận logout mặc định, nhưng không nên dùng GET để làm thay đổi trạng thái. Thymeleaf tự tạo hidden CSRF input cho form POST nêu trên. Không có `@PostMapping("/logout")` trong controller: `LogoutFilter` xử lý request trước khi chuyển đến MVC.

### 3.8. `src/main/resources/application.properties`

```properties
spring.application.name=session-login-lab

# Thời gian không hoạt động trước khi phiên hết hạn
server.servlet.session.timeout=20m

# Cookie phiên không thể đọc bằng document.cookie
server.servlet.session.cookie.http-only=true

# Phù hợp nhiều ứng dụng web login cùng origin thông thường
server.servlet.session.cookie.same-site=lax
```

**Với môi trường local HTTP**, chưa ép `Secure=true` để trình duyệt có thể gửi cookie qua `http://localhost:8080`. **Với production HTTPS**, đặt `server.servlet.session.cookie.secure=true` qua cấu hình môi trường, bảo đảm request thực sự đi qua TLS và reverse proxy được cấu hình tin cậy. `SameSite=Lax` giúp giảm một số bối cảnh gửi cookie cross-site nhưng **không thay thế CSRF token**; nếu sản phẩm có yêu cầu cross-site thực tế, cần thiết kế SameSite, CSRF, CORS, SSO và cookie policy đồng bộ.

## 4. Chạy ứng dụng và quan sát chính xác luồng

Trong thư mục `session-login-lab`:

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

Yêu cầu `java -version` hiển thị JDK 17 trở lên, Maven đủ mới cho dự án. Khi ứng dụng chạy, truy cập `http://localhost:8080`.

**Thực hành bằng trình duyệt:**

1. Mở cửa sổ private/incognito, truy cập `/dashboard`. Khi chưa có phiên xác thực, browser nhận chuyển hướng đến `/login`. Mở Network để xem status **302** và header `Location`.
2. Nhìn DOM form login: có input `username`, `password` và token `_csrf`. Thử sai mật khẩu: `learner / wrong`. Kết quả: redirect `/login?error`, thông báo lỗi chung, không vào dashboard.
3. Đăng nhập `learner / lesson-password-123`. Kết quả: chuyển đến `/dashboard` (hoặc URL bảo vệ ban đầu đã được lưu) và thấy `Xin chào, learner`.
4. Mở DevTools → Application/Storage → Cookies, tìm `JSESSIONID` và các thuộc tính `HttpOnly`, `SameSite`. Đây là **session ID**, không phải mật khẩu. Quan sát session ID trước và sau login nếu có phiên trước login; với session fixation protection, ID đổi lúc xác thực thành công.
5. Làm mới `/dashboard`: vẫn đăng nhập vì trình duyệt gửi cookie phiên và server tìm lại `SecurityContext` tương ứng. Mở cùng URL trong cửa sổ private mới (không chia sẻ cookie): phải login riêng.
6. Nhấn nút **Đăng xuất** trên dashboard. Trong Network, xác nhận browser gửi **POST /logout** cùng CSRF token; server redirect đến `/login?logout`. Sau đó vào lại `/dashboard`: phải login lại.
7. Thử gửi **POST /logout không có CSRF token** bằng công cụ HTTP/MockMvc: mặc định nhận **403**; tài nguyên bảo vệ không nên bị mở sau một yêu cầu giả mạo như vậy.

**Bảng dự kiến khi không có saved request:**

| Request / thao tác | Trạng thái HTTP điển hình | Ý nghĩa |
|---|---:|---|
| `GET /` khi ẩn danh | 200 | Trang public |
| `GET /dashboard` khi ẩn danh | 302 → `/login` | Bảo vệ đường dẫn |
| `GET /login` | 200 | Hiện form với token |
| `POST /login` đúng password + CSRF | 302 → `/dashboard` | Xác thực thành công |
| `POST /login` sai password + CSRF | 302 → `/login?error` | Không được xác thực |
| `POST /login` thiếu CSRF | 403 | Bị chặn trước xác thực |
| `GET /dashboard` với session hợp lệ | 200 | Server tìm thấy Authentication |
| `POST /logout` với CSRF hợp lệ | 302 → `/login?logout` | Đăng xuất, invalidation |
| `POST /logout` thiếu CSRF | 403 | Chặn logout giả mạo |
| `GET /dashboard` sau logout | 302 → `/login` | Phiên đã mất hiệu lực |

Mã 302/200/403 là kỳ vọng theo ứng dụng demo. Reverse proxy, custom authentication entry point, API-oriented configuration hoặc URL đã được lưu trước login có thể đổi hành vi cụ thể. Đừng dùng bảng này làm giả định cứng cho mọi ứng dụng Spring Security.

## 5. HTTP session, cookie và vòng đời của SecurityContext

### 5.1. Khi nào session được tạo?

Browser có thể nhận `JSESSIONID` ngay khi render form login bởi vì server cần giữ state phục vụ CSRF hoặc lưu request trước khi login. Điều đó **không có nghĩa user đã đăng nhập**. Cần tách:

- *Session exists:* server có HTTP session gắn với một ID.
- *Authenticated session:* trong context được lưu có `Authentication` thành công với principal thích hợp.

Khi đăng nhập thành công, Spring Security gắn authentication vào SecurityContext và dùng `SecurityContextRepository` để duy trì trạng thái qua request. Trong ứng dụng dùng HTTP session, dữ liệu cần thiết được giữ phía server; servlet container dùng cookie để ánh xạ request về đúng session. Spring Security không tự thay vai trò quản lý ID của Servlet container.

### 5.2. Chống session fixation

Ví dụ kịch bản tấn công: một người khiến nạn nhân sử dụng một session ID mà người đó đã biết trước lúc nạn nhân login. Nếu ứng dụng giữ nguyên ID sau login, người biết ID có thể có cơ hội chiếm phiên. Khi dùng `changeSessionId()`, sau khi nạn nhân xác thực, container phát sinh ID mới; ID cũ không còn là khóa truy cập vào phiên đã xác thực đó. Cookie session cần có `Secure` khi HTTPS, `HttpOnly` và điều kiện `SameSite` thích hợp để bổ trợ.

**Không dùng `sessionFixation().none()` chỉ để làm bài tập “dễ chạy”; việc này loại bỏ lớp bảo vệ quan trọng.** Trong môi trường Servlet 3.1+ `changeSessionId` vốn thường là mặc định, nên cấu hình trong demo chủ yếu có mục đích học tập. Đổi ID không chữa được XSS, đánh cắp cookie sau login, thiết bị bị chiếm quyền hoặc thiếu TLS.

### 5.3. Thời hạn sống và phiên trên nhiều thiết bị

`server.servlet.session.timeout=20m` là thời gian timeout của **session**, thông thường tính theo thời gian không hoạt động. Không nên hiểu là người dùng bị logout chính xác 20 phút sau khi bấm đăng nhập, cũng không nên phụ thuộc vào browser chủ động xóa cookie ngay khi server hết hạn session.

Các câu hỏi thiết kế cần tự trả lời:

- Phiên được phép sống bao lâu nếu user liên tục thao tác? Có cần absolute timeout ngoài idle timeout?
- Sau đổi password, khóa account hoặc revoke quyền, session cũ bị thu hồi khi nào? Cần hủy session hoặc áp dụng lại kiểm tra quyền ở các request quan trọng.
- Có cho user đăng nhập đồng thời trên nhiều browser/thiết bị? Nếu có giới hạn một phiên, cần cấu hình concurrent session control, `SessionRegistry` phù hợp và `HttpSessionEventPublisher`/hạ tầng session tương ứng; test hai browser **độc lập**, vì hai tab cùng browser thường chia sẻ cookie.
- Có chạy nhiều instance ứng dụng? HTTP session in-memory của từng node có thể mất hoặc lệch khi load balancer chuyển node. Cân nhắc Spring Session + Redis/JDBC, affinity và chính sách timeout/cleanup tùy kiến trúc.

Không thêm `maximumSessions(1)` vào demo khi chưa có yêu cầu và hạ tầng kiểm thử cụ thể: giới hạn phiên có tác động sản phẩm và cần kiểm chứng behavior khi phiên cũ bị hủy/hết hạn.

### 5.4. Session policy phải khớp kiểu ứng dụng

Các policy phổ biến:

| Policy | Ý nghĩa tóm tắt | Phù hợp |
|---|---|---|
| `IF_REQUIRED` | Tạo HTTP session khi thật sự cần | Web form login truyền thống |
| `ALWAYS` | Tạo session khi xử lý request | Một số ứng dụng web có nhu cầu state rõ ràng |
| `NEVER` | Security tự không tạo nhưng có thể dùng session có sẵn | Tùy kiến trúc, cần hiểu giới hạn |
| `STATELESS` | Security không tạo/dùng session để lấy SecurityContext | API xác thực mỗi request bằng bearer token, không phù hợp demo |

Session-based và token-based có lifecycle khác nhau. Không thể chỉ thay `STATELESS` vào config trên rồi kỳ vọng form login vẫn duy trì authenticated session giữa các request.

## 6. CSRF trong cả đăng nhập và đăng xuất

**CSRF (Cross-Site Request Forgery)** là tình huống browser đã mang cookie đăng nhập hợp lệ và bị một trang khác dụ gửi request thay đổi trạng thái đến hệ thống của bạn. Server nhìn thấy cookie hợp lệ nhưng không thể mặc nhiên biết người dùng có chủ ý thực hiện thao tác đó.

Trong demo, Spring Security bật CSRF theo mặc định cho các phương thức không an toàn (`POST`, `PUT`, `PATCH`, `DELETE`). Form gửi token được gắn với yêu cầu hợp lệ; một trang bên ngoài không tự lấy được token hợp lệ chỉ nhờ việc browser đính kèm cookie.

**Đăng nhập cũng cần CSRF:** login CSRF có thể khiến nạn nhân bị đăng nhập vào một tài khoản do kẻ khác kiểm soát, làm lệch audit hoặc thay đổi dữ liệu trong ngữ cảnh tài khoản đó. **Đăng xuất cũng cần CSRF:** nếu cho GET/logout dễ dàng, trang ngoài có thể ép browser người dùng logout.

Checklist:

1. Giữ `csrf(withDefaults())` cho ứng dụng cookie/session.
2. Dùng `th:action` trên form POST của Thymeleaf để token được đưa vào HTML. Nếu dùng fetch/AJAX, gửi token qua header phù hợp; đừng copy token tĩnh vào source.
3. Tất cả request thay đổi dữ liệu phải sử dụng HTTP method thích hợp, không dùng GET để xóa/đổi password/logout.
4. CSRF token thay đổi hoặc bị xóa sau authentication/logout theo flow của Spring Security; AJAX client phải lấy token mới khi cần.
5. CORS, SameSite, CSP, XSS mitigation và CSRF là các lớp riêng, không thể thay thế trực tiếp cho nhau.
6. Không disable CSRF toàn bộ chỉ vì một API mobile/bearer token; nếu có nhiều nhóm endpoint, tách `SecurityFilterChain` hoặc CSRF matcher theo ranh giới xác thực rõ ràng và test cụ thể.

**Ví dụ lỗi phổ biến:** gửi `POST /logout` từ Postman hoặc curl chỉ kèm cookie nhưng không kèm CSRF token, nhận **403**. Đây là cơ chế hoạt động bình thường của `CsrfFilter`, không phải lý do tắt CSRF. Để thử qua browser, dùng nút logout của trang Thymeleaf; để kiểm thử tự động, dùng `.with(csrf())`.

## 7. Logout an toàn: hiểu đủ các bước

Spring Security có `LogoutFilter` và các `LogoutHandler`. Với cấu hình trên, POST logout hợp lệ sẽ:

1. Kiểm tra CSRF trước khi logout được thực hiện.
2. Hủy HTTP session tương ứng với request hiện tại.
3. Xóa `Authentication` và ngữ cảnh liên quan (`SecurityContextHolder` và chỗ lưu context).
4. Dọn dữ liệu liên quan như CSRF state, remember-me nếu tính năng đã cấu hình.
5. Cố gắng dọn cookie tên `JSESSIONID` mà ta chỉ định và chuyển hướng đến trang xác nhận.

**Cần phân biệt:**

- Redirect về `/login` chỉ là phản hồi UX. Nếu chỉ tạo một controller trả `"redirect:/login"` mà không gọi logout handler/invalidate session, user có thể vẫn đăng nhập; đó là logout giả.
- Session invalidation làm mất hiệu lực phiên **phía server**. Xóa cookie browser là lớp dọn bổ sung; phải kiểm tra Path, Domain và reverse proxy nếu cookie không bị xóa như mong đợi.
- Logout **một session** không mặc nhiên logout khỏi mọi thiết bị. Muốn “logout tất cả thiết bị” cần quản lý và thu hồi những phiên khác; với JWT truy cập độc lập cần chiến lược token lifetime/revocation riêng.
- Nếu có SSO/OIDC, logout local session **không tự động đăng xuất khỏi Identity Provider**. OIDC RP-initiated logout/front-channel/back-channel là quy trình riêng phải cấu hình theo nhà cung cấp.
- Nếu có `remember-me`, hãy kiểm tra logout xóa token/cookie đúng cách; persistent remember-me cần kho token và rotation/thu hồi an toàn.
- Không gọi GET để thực hiện logout vì link/prefetch/embed có thể kích hoạt ngoài ý muốn; giữ POST với CSRF.

Với ứng dụng có dữ liệu nhạy cảm, sau logout nên kiểm thử việc nhấn nút Back hoặc dùng cache trình duyệt: trang HTML cũ có thể được browser hiển thị từ cache dù session đã chết. Các response chứa dữ liệu cá nhân cần HTTP cache policy phù hợp; **việc hiển thị lại bản cache không đồng nghĩa API vẫn cấp quyền**. Test bằng request mới tới server mới chứng minh được việc thu hồi session.

## 8. Kiểm thử tự động với MockMvc

File `src/test/java/com/example/sessionlogin/LoginSessionLogoutTest.java` dùng Spring Boot test context và `spring-security-test`. Đây là một chương trình test độc lập trong dự án Maven phía trên, không đòi viết giả lập riêng cho `AuthenticationManager`.

```java
package com.example.sessionlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginSessionLogoutTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void anonymousCannotOpenDashboard() throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login"));
    }

    @Test
    void publicAndLoginPagesAreAccessible() throws Exception {
        mvc.perform(get("/")).andExpect(status().isOk());
        mvc.perform(get("/login")).andExpect(status().isOk());
    }

    @Test
    void badPasswordIsRejected() throws Exception {
        mvc.perform(formLogin()
                .user("learner")
                .password("not-the-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void loginSessionAndLogoutWork() throws Exception {
        var login = mvc.perform(formLogin()
                .user("learner")
                .password("lesson-password-123"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/dashboard"))
            .andExpect(authenticated().withUsername("learner"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/dashboard").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("learner")));

        mvc.perform(post("/logout").session(session).with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void csrfIsRequiredForLoginAndLogout() throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "lesson-password-123"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
```

**Lưu ý về helper:** `formLogin()` trong `spring-security-test` tạo POST /login với CSRF token hợp lệ, nên có thể test xác thực thực tế mà không tự tạo token; `.with(csrf())` dùng trong POST logout. `@WithMockUser` và `.with(user(...))` hữu ích khi test phân quyền nhưng **không kiểm tra pipeline đăng nhập thật**; bài này cần test cả password check lẫn session.

Với redirect của request ẩn danh, URL tuyệt đối `http://localhost/login` là hành vi thường thấy của `LoginUrlAuthenticationEntryPoint` trong MockMvc; nếu ứng dụng/container trả `/login` tương đối theo cấu hình cụ thể, điều chỉnh matcher sau khi quan sát response thực tế. Các test khác xác nhận chính xác các outcome chính.

**Kiểm thử sâu hơn nên bổ sung trong dự án thật:**

- Bắt đầu bằng session ẩn danh có ID A, thực hiện login, kiểm tra session ID B khác A nhưng nội dung ứng dụng cần giữ vẫn còn.
- Dùng một browser/session cũ sau logout để thử request mới, phải bị buộc đăng nhập lại; đừng chỉ kiểm tra redirect success.
- Sau timeout, session không còn Authentication; thông điệp UI thích hợp nhưng không tiết lộ dữ liệu.
- Đăng nhập trên hai browser độc lập, kiểm tra chính sách concurrent session và “logout all” nếu có.
- Login lỗi phải không phân biệt tài khoản tồn tại với password sai trong thông điệp công khai.
- Thử đăng nhập liên tiếp với sai credential, khóa account, rate limiting và event auditing ở môi trường kiểm thử.
- Kiểm tra session cookie trên HTTPS với `Secure`, `HttpOnly`, `SameSite`, đúng Path/Domain; xác minh không rò session ID qua URL, log, referrer.
- Nếu có reverse proxy hoặc SSO, test redirect URI, host/scheme forwarding, logout liên hệ IdP và các tình huống mất mạng.

## 9. Mở rộng an toàn cho sản phẩm thực tế

### 9.1. Nguồn tài khoản và mật khẩu

`InMemoryUserDetailsManager` là công cụ học tập, không có cơ chế lưu user thay đổi giữa các lần khởi động. Với sản phẩm:

- Dùng `UserDetailsService` từ database/JPA/JDBC hoặc LDAP/OIDC theo nguồn danh tính thật.
- Với mật khẩu nội bộ, lưu hash thích ứng có salt, dùng `PasswordEncoder.matches` thông qua provider; không lưu password thô, không dùng `{noop}` và không log input login.
- Quản lý enabled/locked/expired và authority từ dữ liệu tin cậy; không tin role do browser tự gửi.
- Giới hạn lần thử đăng nhập, phát hiện credential stuffing và áp dụng MFA/step-up authentication nếu mức rủi ro yêu cầu.
- Password reset cần token một lần, timeout, xác minh danh tính và thu hồi session theo chính sách.

### 9.2. Cookie và kết nối

| Kiểm soát | Cách áp dụng | Vì sao |
|---|---|---|
| HTTPS/TLS toàn tuyến | Ép HTTPS ở edge và cấu hình đúng sau reverse proxy | Tránh lộ password/session cookie trên đường truyền |
| `Secure` cookie | `server.servlet.session.cookie.secure=true` ở production HTTPS | Browser không gửi cookie qua HTTP |
| `HttpOnly` | Giữ `server.servlet.session.cookie.http-only=true` | JavaScript bình thường không đọc session cookie |
| `SameSite` | Chọn Lax/Strict/None theo UX và cross-site thật; None cần Secure | Giảm gửi cookie không cần thiết ở bối cảnh cross-site |
| Timeout | Idle timeout, cân nhắc absolute timeout và kích hoạt lại xác thực | Giảm thời gian phiên bị lạm dụng |
| Hạn chế truyền session ID trong URL | Ưu tiên cookie, tránh URL rewriting và log ID | Tránh lộ session ID ở history, referer và logs |
| Security headers & XSS prevention | Giữ header bảo vệ phù hợp, escape dữ liệu, CSP theo ứng dụng | Giảm rủi ro đánh cắp session/token |
| Audit | Ghi sự kiện login success/failure/logout và session revocation bằng mã định danh an toàn | Có dấu vết vận hành mà không rò credentials |

Khi dùng reverse proxy, chỉ tin `Forwarded` / `X-Forwarded-*` từ proxy đã kiểm soát; sai cấu hình có thể tạo redirect `http://` sai hoặc làm mất flag `Secure`. Không xem `HttpOnly` là “đã chống được mọi XSS”: script độc vẫn có thể thao tác thay người dùng nếu có lỗ hổng XSS.

### 9.3. Nhất quán giữa nhiều tính năng xác thực

- **Form login + HTTP session** phù hợp web truyền thống. Cần bảo vệ CSRF, cookie và server-side session lifecycle.
- **OIDC login** vẫn có thể tạo **local HTTP session** sau khi IdP xác thực. Logout local và IdP logout là hai thao tác cần thiết kế.
- **Resource server JWT** thường kiểm chứng bearer token trên mỗi request và có thể stateless. Logout session trong demo không thu hồi access token đã phát hành ở nơi khác.
- **Remember-me** kéo dài khả năng tự xác thực lại, không phải phiên vô hạn. Nếu bật, phải quản lý key, token persistence, rotation, expiry và cleanup logout.
- **Ứng dụng nhiều instance** cần quyết định cách chia sẻ session (ví dụ Spring Session) và cách xử lý deploy/restart; session in-memory trên một node không bảo đảm trải nghiệm đồng nhất.

## 10. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân thường gặp | Kiểm tra/sửa |
|---|---|---|
| Truy cập `/dashboard` bị loop đến `/login` | Login page chưa `permitAll`, hoặc cookie/session không được gửi | Kiểm tra matcher, HTTP 302 chain, cookie Path/Secure/SameSite |
| `POST /login` luôn 403 | Thiếu/sai CSRF token, form không dùng `th:action` hoặc token cũ | Xem hidden `_csrf`, session cookie, Spring Security logs |
| Login đúng password vẫn `?error` | Password hash/encoder sai, username khác, account disabled | Kiểm tra `UserDetailsService`, `PasswordEncoder.matches` và trạng thái user |
| Login thành công nhưng request tiếp theo vẫn ẩn danh | Cookie không được browser gửi, sai domain/path, load balancer không dùng chung session | Kiểm tra Network, `Set-Cookie`, session store, proxy |
| Session ID không đổi khi login | Không có session trước login hoặc strategy bị cấu hình sai | Tạo session trước login và so hai ID; giữ `changeSessionId` |
| Click link `/logout` nhưng vẫn đăng nhập | GET không thực hiện logout thực tế khi bật CSRF | Dùng form POST + token; kiểm tra LogoutFilter |
| Logout trả 403 | Thiếu/sai CSRF token hoặc token thuộc phiên khác | Render form mới và POST kèm token hợp lệ |
| Logout redirect xong vẫn truy cập được dữ liệu | Chỉ redirect ở controller, session chưa bị hủy; hoặc còn phiên khác | Dùng LogoutFilter, test request mới bằng cookie cũ |
| Nhiều tab “cùng đăng nhập” | Các tab chia sẻ cookie trong một browser profile | Test với hai profile/browser độc lập |
| Sau login, request AJAX đầu tiên bị CSRF lỗi | Token bị xóa/refresh sau xác thực, JS giữ token cũ | Fetch CSRF token mới sau khi login |
| Trang cũ còn thấy khi nhấn Back | Browser cache lưu bản HTML trước logout | Cấu hình cache headers cho dữ liệu nhạy cảm, test request mới đến server |
| Không có authentication trong async task | SecurityContext là request/thread context, không tự lan sang mọi luồng | Dùng integration hỗ trợ propagation hoặc truyền principal có kiểm soát |

**Nguyên tắc chẩn đoán:** chụp một chuỗi request/response với URL, method, status, redirect, cookie flags, CSRF parameter và session state trong môi trường test; tuyệt đối che giá trị `Cookie`, `Authorization`, password, session ID và token khi chia sẻ logs.

## 11. Câu hỏi tự kiểm tra và bài tập mở rộng

1. Tại sao `GET /login` có thể đã tạo session trong khi `Authentication` vẫn chưa phải người dùng đã đăng nhập?
2. Vì sao cookie chứa session ID, không nên chứa password? Điều gì xảy ra khi kẻ xấu lấy được cookie sau login?
3. Sự khác nhau giữa `SecurityContextHolder` theo request và `SecurityContextRepository` lưu ngữ cảnh qua nhiều request là gì?
4. Tại sao đổi session ID sau login quan trọng? Nếu ID cũ vẫn được dùng thì rủi ro ra sao?
5. Vì sao form login và logout đều nên được CSRF bảo vệ dù người dùng chưa đăng nhập ở lần đầu?
6. Logout bằng redirect đơn thuần khác gì logout qua `LogoutFilter` và session invalidation?
7. Điều gì thay đổi nếu dùng OIDC SSO, nhiều server instance hoặc yêu cầu “logout tất cả thiết bị”?
8. Timeout của server khác gì thời gian tồn tại của cookie trên trình duyệt? Tại sao hai tab thường cùng đăng nhập?

**Bài mở rộng theo trình tự học:**

- Thêm route `/admin` chỉ có `ROLE_ADMIN` truy cập; viết integration test 403 cho user thiếu role.
- Thay tài khoản demo bằng bảng account lưu BCrypt hash, enabled/locked state và role; kiểm thử password sai, tài khoản khóa và reload sau restart.
- Đo thời gian idle của session và xử lý UX khi session hết hạn; cảnh báo trước timeout nếu nghiệp vụ cần.
- Kiểm thử song song hai browser và cài chính sách giới hạn số phiên; cung cấp nút “đăng xuất các thiết bị khác” nếu có yêu cầu.
- Thử deploy hai instance với shared session store, xác minh login/logout còn đúng qua load balancer và restart.
- Khi tích hợp IdP, mô tả riêng local logout, revoke token và SSO single logout.

## 12. Tài liệu chính thức

- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Testing Logout](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Boot — Servlet Web Server, Sessions and Cookies](https://docs.spring.io/spring-boot/reference/web/servlet.html)

Kết quả đạt của bài thực hành là một đường đi có thể quan sát, giải thích và kiểm thử **anonymous → form login → authenticated HTTP session → CSRF-protected logout → anonymous**, trong đó mọi redirect, cookie, context và session đều có vai trò rõ ràng; logic xác thực và logout dựa vào cơ chế chuẩn của Spring Security.
