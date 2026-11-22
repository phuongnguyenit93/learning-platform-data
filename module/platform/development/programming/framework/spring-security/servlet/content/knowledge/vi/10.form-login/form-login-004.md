# Trang đăng nhập tự tạo và yêu cầu cho tài nguyên tĩnh trong Spring Security Servlet

## Mục tiêu

Khi bật formLogin trong Spring Security Servlet, ứng dụng có thể dùng trang đăng nhập do framework sinh sẵn. Trong một ứng dụng thực tế, ta thường muốn **tự thiết kế trang GET /login** và dùng CSS, JavaScript, hình ảnh, font hoặc favicon của ứng dụng. Muốn trang này hiển thị khi chưa có phiên đăng nhập, không chỉ cần một file HTML: phải cấu hình đúng **đường dẫn công khai**, **endpoint xử lý form POST**, **CSRF** và **quyền truy cập các tài nguyên tĩnh**.

Sau bài học, bạn có thể:

- Phân biệt **trang GET /login** do MVC render với **POST /login** được Spring Security filter xử lý.
- Cấu hình SecurityFilterChain với formLogin.loginPage(...), loginProcessingUrl(...), defaultSuccessUrl(...), failureUrl(...).
- Phân biệt authorizeHttpRequests().requestMatchers(...).permitAll(), formLogin().permitAll() và WebSecurityCustomizer.ignoring().
- Công khai chính xác CSS/JS/images dùng cho trang login mà không vô tình công khai các endpoint nghiệp vụ.
- Hiểu PathRequest.toStaticResources().atCommonLocations() của Spring Boot và quy ước thư mục src/main/resources/static.
- Tạo trang Thymeleaf có biểu mẫu username/password, token CSRF và liên kết tài nguyên tương thích context path.
- Chạy một ví dụ hoàn chỉnh bằng Java 17+ với Spring Boot 3.x/Spring Security 6.x và kiểm thử bằng MockMvc.
- Chẩn đoán 302 vòng lặp, 403 khi POST login, tài nguyên 404/302, lỗi redirect sau đăng nhập hoặc logout.

Phạm vi là **Spring MVC/Servlet**. Cấu hình SecurityFilterChain không tương đương với SecurityWebFilterChain của WebFlux. Ví dụ sử dụng form login có session và bảo vệ CSRF mặc định; không dùng password/token production.

## 1. Có hai endpoint “login” với hai nhiệm vụ khác nhau

Một trang login tùy chỉnh cần phân biệt ít nhất hai tương tác:

1. **GET /login:** trình duyệt yêu cầu giao diện. Một @Controller trả về view login.html. Người dùng chưa đăng nhập cũng phải được phép xem trang này và tải CSS/JS/images cần thiết.
2. **POST /login:** browser gửi username, password và CSRF token. Mặc định **UsernamePasswordAuthenticationFilter** (được kích hoạt qua formLogin) nhận request và gọi AuthenticationManager. Controller GET /login **không phải nơi xác minh mật khẩu**.

Luồng thông thường:

~~~text
GET /dashboard (chưa có session)
        |
FilterChainProxy -> SecurityFilterChain
        |
AuthorizationFilter yêu cầu authenticated
        |
ExceptionTranslationFilter / authentication entry point
        |
302 Location: /login
        |
GET /login
        |
requestMatchers("/login").permitAll()
        |
PageController.loginPage() -> view templates/login.html
        |
browser tải GET /css/login.css, /js/login.js, /images/logo.svg
        |
các request static được permitAll -> Spring MVC resource handler
        |
người dùng điền form
        |
POST /login + username + password + CSRF
        |
CsrfFilter xác minh token
        |
UsernamePasswordAuthenticationFilter
        |
AuthenticationManager / AuthenticationProvider
        |
        +-- thành công -> lưu SecurityContext/session -> redirect /dashboard
        |
        +-- thất bại -> redirect /login?error
~~~

Ở cấu hình mẫu của bài, trang GET /login và POST /login dùng cùng URL nhưng **khác HTTP method, khác người chịu trách nhiệm**. Không viết @PostMapping("/login") tự kiểm tra raw password khi đã cấu hình Spring Security xử lý POST /login.

Nếu bạn chọn loginPage("/sign-in") và loginProcessingUrl("/authenticate"), trang GET và request POST nằm ở hai đường dẫn khác. HTML form phải gửi đến **đúng** loginProcessingUrl; Spring Security không tự đọc form action rồi cập nhật URL xử lý.

## 2. Vì sao trang đăng nhập phải truy cập được khi chưa xác thực?

Giả sử cấu hình:

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated())
.formLogin(form -> form
    .loginPage("/login"))
~~~

Nếu GET /login không được cho phép, người dùng chưa xác thực truy cập trang được chuyển đến /login, nhưng /login lại tiếp tục yêu cầu xác thực. Kết quả có thể là **vòng lặp redirect** hoặc không thấy form, tùy cấu hình. Vì vậy phải cho phép endpoint trang login và những endpoint cần thiết để nó tải được.

Một cấu hình rõ ràng:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login").permitAll()
    .anyRequest().authenticated())
.formLogin(form -> form
    .loginPage("/login")
    .permitAll())
~~~

Đây là **đoạn trích** trong chuỗi cấu hình HttpSecurity; ví dụ đầy đủ nằm ở phần thực hành. formLogin(...).permitAll() cho phép các URL liên quan cơ chế form login, bao gồm trang/URL xử lý theo cấu hình của formLogin. Việc khai báo rõ requestMatchers("/login").permitAll() vẫn hữu ích để người đọc nhìn thấy chủ đích và kiểm tra chính sách.

**Không dùng anyRequest().permitAll() chỉ để login page xuất hiện.** Điều đó cũng vô tình biến /dashboard, /admin, /account và các URL khác thành công khai. Không dùng quy tắc rộng kiểu /** khi chỉ cần /login và tài nguyên giao diện.

Nếu chọn một URL lỗi như /login?error, query parameter không làm biến đổi phần đường dẫn cần được match: vẫn là GET /login. Các redirect đích khác phải được xử lý phù hợp với chính sách quyền truy cập.

## 3. Tài nguyên tĩnh: đường dẫn URL khác thư mục trên đĩa

Spring Boot MVC mặc định có các static location quen thuộc, ví dụ:

| File trong project | URL khi không có context path |
| --- | --- |
| src/main/resources/static/css/login.css | GET /css/login.css |
| src/main/resources/static/js/login.js | GET /js/login.js |
| src/main/resources/static/images/logo.svg | GET /images/logo.svg |
| src/main/resources/static/favicon.ico | GET /favicon.ico |
| src/main/resources/templates/login.html | **Không** tự truy cập ở /templates/login.html; MVC Controller render view login |

Một file đặt dưới resources/static được Spring MVC resource handler phân phối theo URL công khai tương ứng. Với mô hình đóng gói JAR của Spring Boot, các resource này đi cùng classpath. Không cần tạo controller riêng cho mỗi CSS hoặc JavaScript.

Ngược lại, file dưới resources/templates là **server-side template**, không nên cho client GET trực tiếp như file tĩnh. Tên view login được Thymeleaf tìm và render khi controller trả về chuỗi "login".

Các static location khác có thể được Spring Boot hỗ trợ theo mặc định như classpath:/public, classpath:/resources, classpath:/META-INF/resources. Cấu hình spring.web.resources.static-locations hoặc spring.mvc.static-path-pattern có thể thay đổi cách ánh xạ. Nếu ứng dụng thay đổi mặc định, hãy kiểm thử đường dẫn thực tế, không sao chép pattern máy móc.

### Quy tắc URL có context path

Nếu server.servlet.context-path=/shop, thì tài nguyên hiển thị dưới URL /shop/css/login.css, không phải /css/login.css ở gốc domain. Trong Thymeleaf, dùng:

~~~html
<link rel="stylesheet" th:href="@{/css/login.css}">
<script defer th:src="@{/js/login.js}"></script>
<img th:src="@{/images/logo.svg}" alt="Logo">
~~~

Thymeleaf/Spring MVC sẽ tạo URL phù hợp context path khi render. Trong form cũng dùng th:action="@{/login}" thay vì hardcode action="/login" nếu ứng dụng có thể chạy dưới context path khác.

**Các string trong securityMatcher/requestMatchers thường áp dụng theo cách RequestMatcher phân tích HttpServletRequest**, không đơn giản là ghép thủ công context path phía trước mỗi path. Khi đổi servlet mapping hoặc static-path-pattern cần test thực tế.

## 4. Công khai tài nguyên tĩnh: hai cách phổ biến

### 4.1. Dùng PathRequest của Spring Boot

Khi sử dụng Spring Boot Servlet và các static location phổ biến:

~~~java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;

http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login", "/error").permitAll()
    .requestMatchers(
        PathRequest.toStaticResources().atCommonLocations()
    ).permitAll()
    .anyRequest().authenticated());
~~~

Đoạn trên là **mảnh code trong cấu hình HttpSecurity**, không phải ứng dụng độc lập. PathRequest là tiện ích **của Spring Boot** để match các tài nguyên ở những vị trí tĩnh thông dụng (CSS, JavaScript, images, WebJars, favicon theo danh sách được Boot hỗ trợ). Nó hữu ích khi muốn tránh duy trì nhiều mẫu URL thủ công cho các common locations.

Lưu ý quan trọng:

- PathRequest không phải API có sẵn trong một ứng dụng chỉ thêm spring-security-config mà không có các module Boot liên quan.
- “Common locations” không có nghĩa **mọi đường dẫn tùy biến của ứng dụng** đều được cho phép.
- Nếu bạn đặt tài nguyên ở đường dẫn riêng như /assets/** hoặc thay đổi cơ chế static resource mapping, cần xác minh matcher thực tế có bao phủ không và thêm luật chính xác nếu cần.
- Không cho rằng một endpoint API tên /images/admin-data tự động là file tĩnh hợp lệ; cấu hình static matcher phải dựa trên resource mapping thật.

### 4.2. Dùng danh sách URL cụ thể

Nếu không muốn phụ thuộc PathRequest hoặc cần chính sách tự quản lý:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/login",
        "/error",
        "/css/**",
        "/js/**",
        "/images/**",
        "/favicon.ico"
    ).permitAll()
    .anyRequest().authenticated())
~~~

Cách này dễ đọc và kiểm thử khi cấu trúc static được kiểm soát. Nhưng nếu có endpoint nghiệp vụ trùng /images/**, một luật wildcard quá rộng có thể công khai thứ không phải static. Hãy giữ cấu trúc URL rõ ràng và tránh đè lên REST API.

Nếu chỉ cần một số file cho login page, bạn có thể cho phép chính xác /css/login.css, /js/login.js, /images/logo.svg; đổi tên file đòi hỏi sửa cấu hình. Hãy chọn độ rộng phù hợp mà không cấp quyền ngoài ý định.

### Vì sao permitAll thường tốt hơn ignoring?

Có thể bắt gặp cấu hình:

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/css/**");
}
~~~

Đây là **ví dụ phản diện cho lựa chọn thông thường**, không phải code bạn cần thêm vào ứng dụng mẫu. ignoring() khiến request bỏ qua Spring Security filter chain; do đó các filter như HeaderWriterFilter không có cơ hội bổ sung security headers cho resource đó. Trong khi đó, permitAll cho phép request đi qua SecurityFilterChain nhưng AuthorizationFilter không đòi xác thực đối với URL được phép.

| Cách làm | Qua security filter chain? | Đòi đăng nhập? | Khi nào dùng |
| --- | --- | --- | --- |
| requestMatchers("/css/**").permitAll() | Có, nếu chain match request | Không theo luật này | Mặc định phù hợp cho CSS/JS/images công khai |
| PathRequest...atCommonLocations().permitAll() | Có, nếu chain match request | Không theo luật này | Spring Boot với common static locations |
| web.ignoring().requestMatchers(...) | Không đi qua Spring Security chain | Không do Spring Security kiểm tra | Chỉ cân nhắc có lý do cụ thể và hiểu rõ hậu quả |
| anyRequest().permitAll() | Có | Không cho mọi request thuộc chain | **Không** dùng chỉ để chữa lỗi login page |

Không dùng permitAll như một lời bảo đảm rằng **mọi** filter đều bỏ qua request: CSRF, custom filter hoặc filter khác vẫn có thể tác động theo quy tắc riêng. Tuy nhiên GET static bình thường không phải loại request mà CsrfFilter mặc định yêu cầu CSRF token.

## 5. Ví dụ chạy được: trang login tùy biến với Thymeleaf

Ta tạo một ứng dụng dùng Java 17, Spring Boot 3.3.5, Spring Security 6.x tương thích do Boot quản lý, Spring MVC và Thymeleaf.

**Kết quả mong đợi:** người chưa login truy cập GET /login sẽ thấy HTML + CSS + JS + logo; GET /dashboard chuyển sang /login; gửi form đúng user/password sẽ chuyển đến /dashboard; sai password quay lại /login?error; đăng xuất bằng POST /logout có CSRF sẽ về /login?logout.

### 5.1. Tạo project và dependency

Cấu trúc:

~~~text
custom-login-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat   (nếu dùng Gradle Wrapper)
  src/main/java/dev/example/customlogin/
    CustomLoginApplication.java
    SecurityConfig.java
    PageController.java
  src/main/resources/
    templates/login.html
    templates/dashboard.html
    static/css/login.css
    static/js/login.js
    static/images/logo.svg
  src/test/java/dev/example/customlogin/
    LoginPageIntegrationTest.java
~~~

settings.gradle:

~~~groovy
rootProject.name = 'custom-login-demo'
~~~

build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dùng project có Gradle Wrapper để chạy các lệnh ở cuối phần này. Đừng chạy javac trên các file riêng lẻ mà không có classpath của Spring/Thymeleaf, vì các import ngoài JDK sẽ không được tìm thấy.

### 5.2. Entry point

Tệp src/main/java/dev/example/customlogin/CustomLoginApplication.java:

~~~java
package dev.example.customlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomLoginApplication.class, args);
    }
}
~~~

### 5.3. Cấu hình SecurityFilterChain

Tệp src/main/java/dev/example/customlogin/SecurityConfig.java:

~~~java
package dev.example.customlogin;

import org.springframework.boot.autoconfigure.security.servlet.PathRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("local-demo-only"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers(
                        PathRequest.toStaticResources().atCommonLocations()
                ).permitAll()
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/dashboard", true)
                .failureUrl("/login?error")
                .permitAll());

        http.logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll());

        return http.build();
    }
}
~~~

Từng dòng quan trọng:

1. **requestMatchers("/login", "/error").permitAll():** cho phép user chưa đăng nhập xem trang login và endpoint lỗi. Đây là phạm vi công khai có chủ đích; không nới quyền /dashboard.
2. **PathRequest.toStaticResources().atCommonLocations():** cho phép CSS/JS/logo đặt trong các common static locations của Boot.
3. **anyRequest().authenticated():** mọi request khác (bao gồm /dashboard) phải có Authentication hợp lệ.
4. **loginPage("/login"):** Spring Security không cần sinh giao diện login mặc định; ứng dụng **chịu trách nhiệm GET /login** và template.
5. **loginProcessingUrl("/login"):** POST /login được filter đăng nhập xử lý. Không cần và không nên tự tạo @PostMapping("/login") để gọi password encoder.
6. **defaultSuccessUrl("/dashboard", true):** sau khi login thành công chuyển tới /dashboard, thay vì ưu tiên saved request. Tham số true cố ý đơn giản hóa kỳ vọng test; nếu muốn quay lại URL trước khi login hãy dùng chính sách saved request phù hợp.
7. **failureUrl("/login?error"):** khi xác thực form thất bại chuyển về trang login kèm cờ lỗi chung. Không truyền chi tiết username, password hay exception nhạy cảm lên query string.
8. **logoutSuccessUrl("/login?logout"):** sau logout thành công quay về trang login và hiển thị thông báo. Cấu hình mặc định Spring Security có xử lý logout; không cần controller POST /logout.
9. **PasswordEncoder và UserDetailsService:** user demo chỉ có student / local-demo-only, được băm trước khi lưu trong bộ nhớ. Không hardcode credential thật trong source production.
10. **Không disable CSRF:** một POST /login hợp lệ cần token; Thymeleaf hỗ trợ đưa token vào form như phần sau.

Vì có một SecurityFilterChain với matcher mặc định bao quát request, các URL trên được phân quyền trong cùng chain. Khi hệ thống có nhiều chain và @Order/securityMatcher riêng, phải bảo đảm GET /login, POST /login và các static URL **nằm trong chain phù hợp**; luật permitAll của một chain không cứu request đi vào chain khác hoặc không đi qua chain nào.

### 5.4. Controller render hai template

Tệp src/main/java/dev/example/customlogin/PageController.java:

~~~java
package dev.example.customlogin;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/login")
    public String loginPage() {
        return "login";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "dashboard";
    }
}
~~~

@Controller, không phải @RestController, để giá trị "login" được xử lý là **tên view** bởi Thymeleaf. Nếu dùng @RestController, trình duyệt có thể chỉ thấy chữ login thay vì HTML. Với convention mặc định, Spring Boot/Thymeleaf tìm templates/login.html và templates/dashboard.html.

Mã chỉ có @GetMapping cho trang login và dashboard. POST /login là trách nhiệm của UsernamePasswordAuthenticationFilter nhờ cấu hình formLogin; POST /logout là trách nhiệm của LogoutFilter.

### 5.5. Template login tùy biến

Tệp src/main/resources/templates/login.html:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Đăng nhập</title>
    <link rel="stylesheet" th:href="@{/css/login.css}">
    <script defer th:src="@{/js/login.js}"></script>
</head>
<body>
<main class="card">
    <img class="logo" th:src="@{/images/logo.svg}" alt="Logo học Java">
    <h1>Đăng nhập</h1>

    <p class="error" th:if="${param.error != null}">
        Tên đăng nhập hoặc mật khẩu không hợp lệ.
    </p>
    <p class="notice" th:if="${param.logout != null}">
        Bạn đã đăng xuất.
    </p>

    <form th:action="@{/login}" method="post">
        <label for="username">Tên đăng nhập</label>
        <input id="username" name="username"
               type="text" autocomplete="username" required>

        <label for="password">Mật khẩu</label>
        <input id="password" name="password"
               type="password" autocomplete="current-password" required>

        <button type="submit">Đăng nhập</button>
    </form>
</main>
</body>
</html>
~~~

Chú ý ba điều:

- Form action do th:action tạo trỏ về URL **POST /login** đúng loginProcessingUrl. Hai input có name="username" và name="password" đúng các tên tham số mặc định mà UsernamePasswordAuthenticationFilter tìm.
- Thymeleaf khi tích hợp Spring MVC và Spring Security sử dụng RequestDataValueProcessor cho form th:action phương thức POST và **tự chèn trường ẩn CSRF** phù hợp. Hãy mở HTML đã render trên môi trường dev để xác minh có hidden input tên thường là _csrf. Không copy một token CSRF cố định vào template. Nếu dùng template engine khác hoặc form HTML thuần, phải tự đưa token hiện hành theo cơ chế được framework hỗ trợ.
- th:href/th:src và th:action giải quyết context path. Nếu viết href="/css/login.css" cố định, ứng dụng deploy dưới /myapp có thể không tải được CSS.

Thông báo lỗi không xác nhận username có tồn tại hay không, tránh làm lộ dữ liệu tài khoản. Khi triển khai thật cần chính sách validation, thông báo truy cập, rate limiting và xử lý nội dung đa ngôn ngữ phù hợp.

### 5.6. Template trang dashboard và logout

Tệp src/main/resources/templates/dashboard.html:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Dashboard</title>
</head>
<body>
    <h1>Chào mừng đến trang được bảo vệ</h1>
    <p>Chỉ người dùng đã đăng nhập mới thấy trang này.</p>

    <form th:action="@{/logout}" method="post">
        <button type="submit">Đăng xuất</button>
    </form>
</body>
</html>
~~~

Mặc định với CSRF đang bật, logout qua **POST /logout** là hướng phù hợp; th:action cùng Spring integration có thể thêm token CSRF cho form. Không tạo một link GET /logout rồi giả định nó luôn thực thi logout khi CSRF đang bật.

**Không** tùy tiện tắt CSRF chỉ để đăng xuất dễ hơn. Khi dùng session cookie trong browser, CSRF protection là một biện pháp quan trọng cho các request thay đổi trạng thái.

### 5.7. Tệp CSS

Tệp src/main/resources/static/css/login.css:

~~~css
:root {
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    color: #243247;
    background: #f4f7fb;
}

body {
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
}

.card {
    width: min(90vw, 360px);
    padding: 2rem;
    background: white;
    border: 1px solid #dfe5ee;
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.07);
}

.logo { width: 64px; height: 64px; }
label { display: block; margin-top: 1rem; }
input, button { box-sizing: border-box; width: 100%; padding: .7rem; }
button { margin-top: 1.2rem; cursor: pointer; }
.error { color: #a12b2b; }
.notice { color: #246a3a; }
~~~

Tệp này ở classpath static/css sẽ được MVC phục vụ tại /css/login.css. SecurityFilterChain phải cho GET URL này đối với người chưa login; nếu không browser có thể nhận 302 tới trang login thay cho CSS, dẫn tới giao diện không có style.

### 5.8. Tệp JavaScript

Tệp src/main/resources/static/js/login.js:

~~~javascript
document.addEventListener("DOMContentLoaded", () => {
    const usernameField = document.querySelector("#username");
    if (usernameField) {
        usernameField.focus();
    }
});
~~~

JS ở đây chỉ hỗ trợ UX; không đưa username/password vào localStorage hoặc query string, không can thiệp vào cơ chế mã hóa mật khẩu và không tự thực hiện xác thực ở frontend.

### 5.9. Tệp logo

Tệp src/main/resources/static/images/logo.svg:

~~~xml
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"
     viewBox="0 0 64 64" role="img" aria-label="Logo học Java">
  <rect width="64" height="64" rx="12" fill="#243247"/>
  <path d="M17 21h30v6H23v10h24v6H17z" fill="#ffffff"/>
</svg>
~~~

Tệp SVG được phục vụ tại /images/logo.svg. Chỉ dùng SVG được kiểm soát nguồn gốc khi cho phép upload tài nguyên từ người dùng; không biến thư mục static công khai thành nơi chứa file bí mật hoặc nội dung HTML/SVG không tin cậy.

### 5.10. Chạy ứng dụng

Trong project có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell với wrapper dạng .bat:

~~~powershell
./gradlew.bat bootRun
~~~

Khi Spring Boot khởi động với cổng 8080 mặc định, mở http://localhost:8080/login. Login với:

~~~text
Username: student
Password: local-demo-only
~~~

Đây là tài khoản demo in-memory **không dùng cho production**. Nếu thành công bạn sẽ được redirect tới /dashboard. Nhấn nút Đăng xuất để POST /logout và được redirect về /login?logout.

Thử các URL mà không login:

~~~bash
curl -i http://localhost:8080/login
curl -i http://localhost:8080/css/login.css
curl -i http://localhost:8080/js/login.js
curl -i http://localhost:8080/images/logo.svg
curl -i http://localhost:8080/dashboard
~~~

Kết quả quan trọng:

| URL | Kết quả điển hình khi chưa login |
| --- | --- |
| GET /login | 200, HTML có form đăng nhập |
| GET /css/login.css | 200, nội dung CSS |
| GET /js/login.js | 200, nội dung JavaScript |
| GET /images/logo.svg | 200, nội dung SVG |
| GET /dashboard | 302 redirect về /login |

Status/header thực tế có thể bổ sung thông tin tùy container, Spring Security headers, proxy và context path. Bảng là kỳ vọng logic của ví dụ, không phải HTTP response byte-for-byte.

**Đừng chỉ dùng curl -d username=... -d password=... với POST /login rồi kết luận mật khẩu sai khi nhận 403.** Với CSRF bật, bạn cần gửi token và session cookie tương ứng; trình duyệt + Thymeleaf hoặc spring-security-test là cách dễ kiểm tra đúng luồng.

## 6. Kiểm thử MockMvc: login page, assets, CSRF, auth và logout

Thêm tệp src/test/java/dev/example/customlogin/LoginPageIntegrationTest.java:

~~~java
package dev.example.customlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginPageIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void customLoginPageRendersForAnonymousUser() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"username\"")))
                .andExpect(content().string(containsString("name=\"password\"")))
                .andExpect(content().string(containsString("_csrf")));
    }

    @Test
    void staticAssetsArePublic() throws Exception {
        mvc.perform(get("/css/login.css")).andExpect(status().isOk());
        mvc.perform(get("/js/login.js")).andExpect(status().isOk());
        mvc.perform(get("/images/logo.svg")).andExpect(status().isOk());
    }

    @Test
    void dashboardRedirectsAnonymousUserToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location", endsWith("/login")));
    }

    @Test
    void validFormLoginCreatesAuthenticatedSession() throws Exception {
        MvcResult result = mvc.perform(
                        post("/login").with(csrf())
                                .param("username", "student")
                                .param("password", "local-demo-only"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        endsWith("/dashboard")))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("trang được bảo vệ")));
    }

    @Test
    void badCredentialsRedirectToPublicErrorMessage() throws Exception {
        mvc.perform(post("/login").with(csrf())
                        .param("username", "student")
                        .param("password", "wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        "Location", containsString("/login?error")));

        mvc.perform(get("/login").param("error", ""))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("không hợp lệ")));
    }

    @Test
    void loginWithoutCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "student")
                        .param("password", "local-demo-only"))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutRequiresPostAndCsrfToken() throws Exception {
        MvcResult result = mvc.perform(
                        post("/login").with(csrf())
                                .param("username", "student")
                                .param("password", "local-demo-only"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(post("/logout").session(session).with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        "Location", containsString("/login?logout")));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Kỳ vọng test pass khi dùng code và dependency đã nêu. Test sử dụng .with(csrf()) do spring-security-test cung cấp để thực hiện POST có token hợp lệ; nó **không chứng minh frontend đã gửi token chính xác**. Test render login.html có kiểm tra chuỗi _csrf nhằm phát hiện thiếu tích hợp token trong trang đã render; vẫn nên kiểm tra form bằng trình duyệt thật.

Lưu ý khi chạy với context path, proxy hoặc redirect strategy khác: Location header có thể chứa context path hoặc absolute URL. Test trong bài dựa trên cấu hình default localhost/không context path; nếu thay đổi, cần điều chỉnh assertion theo hợp đồng URL thực tế.

## 7. CSRF: GET công khai không đồng nghĩa POST không cần token

Một trang GET /login được permitAll là điều đúng; nhưng POST /login thay đổi trạng thái xác thực/session nên thường phải đi qua CSRF protection trong ứng dụng browser dựa trên cookie.

Với Spring Security Servlet mặc định:

- GET/HEAD/OPTIONS/TRACE thông thường được xem là phương thức an toàn theo mặc định của CsrfFilter và không yêu cầu token.
- POST/PUT/PATCH/DELETE thường cần CSRF token nếu request thuộc phạm vi bảo vệ.
- Form đăng nhập phải gửi token hợp lệ nếu CSRF được bật. Thiếu token có thể trả 403 **trước** khi UsernamePasswordAuthenticationFilter kiểm tra password.
- permitAll trên /login và /css/** không tự tắt CSRF; đây là hai vấn đề độc lập.
- Với Thymeleaf th:action ở form method=post, Spring integration có thể chèn hidden CSRF token. Với plain HTML hoặc SPA/API, phải dùng cơ chế cấp/lấy/gửi token phù hợp (ví dụ CookieCsrfTokenRepository khi được cấu hình và được xử lý đúng).

Một input minh họa trong HTML **đã render**, không hard-code vào template:

~~~html
<input type="hidden" name="_csrf" value="token-do-server-sinh-cho-phien-hien-tai">
~~~

Chuỗi value chỉ để minh họa, **không phải token hợp lệ**. Token phải đến từ request/session/repository thực tế. Đừng đăng token vào log hoặc tài liệu công khai.

### Khi dùng JavaScript submit login

Nếu JavaScript gọi fetch("/login", { method: "POST" ... }), bạn phải gửi form data đúng tên trường, token CSRF theo cách Spring Security của ứng dụng đã cấu hình, và quản lý session cookie/cùng-origin đúng yêu cầu. Một form HTML chuẩn với th:action thường ít phức tạp và phù hợp để học form login hơn.

Không chuyển raw password lên URL query string. HTTPS phải được bật trong môi trường thật, và phải có giới hạn thử đăng nhập/sự kiện bất thường phù hợp. Browser không nên lưu credential thô vào localStorage.

## 8. Điều gì xảy ra nếu tùy chỉnh loginProcessingUrl?

Giả sử muốn giao diện tại /sign-in và POST credentials tới /auth/sign-in:

~~~java
.formLogin(form -> form
    .loginPage("/sign-in")
    .loginProcessingUrl("/auth/sign-in")
    .defaultSuccessUrl("/dashboard", true)
    .failureUrl("/sign-in?error")
    .permitAll())
~~~

Bạn cần:

- Controller GET /sign-in render view;
- HTML form th:action="@{/auth/sign-in}" method="post";
- Spring Security chain bao phủ URL /auth/sign-in và bật UsernamePasswordAuthenticationFilter;
- Luật công khai hợp lệ cho trang/form endpoint qua formLogin().permitAll() hoặc cấu hình tương đương;
- POST có username/password theo tên parameter của filter và CSRF token;
- URL báo lỗi, logout-success hiển thị được khi chưa đăng nhập.

Nếu đổi tên trường form sang email và passcode:

~~~java
.formLogin(form -> form
    .loginPage("/sign-in")
    .loginProcessingUrl("/auth/sign-in")
    .usernameParameter("email")
    .passwordParameter("passcode")
    .permitAll())
~~~

thì HTML phải dùng name="email" và name="passcode"; chỉ đổi label hiển thị không đủ. UserDetailsService hoặc provider cũng phải xử lý giá trị email như định danh đăng nhập khi phù hợp.

Không viết controller POST trùng URL đã được login filter claim và không dựa vào việc request sẽ luôn đi tới DispatcherServlet: security filter có thể hoàn tất xác thực rồi redirect trước controller.

## 9. Một số tình huống với nhiều SecurityFilterChain

Ví dụ ứng dụng có API chain và web chain:

~~~text
@Order(1) -> securityMatcher("/api/**")
    -> API auth (Basic/Bearer, tùy yêu cầu)
@Order(2) -> securityMatcher mặc định mọi request
    -> Web form login + GET /login + static assets
~~~

FilterChainProxy chọn **chain đầu tiên match request**. Trong ví dụ, /login và /css/login.css không match /api/**, nên sẽ đi vào web chain được cấu hình permitAll. Nếu nhầm đặt web chain có matcher mọi request ở @Order(1), API chain có thể bị che khuất. Nếu web chain chỉ có securityMatcher("/private/**"), thì /login và static URL có thể không vào chain đó như bạn nghĩ.

Những lỗi phát sinh:

- Cấu hình permitAll("/login") ở chain /api/** nhưng GET /login vào chain web khác → không có tác dụng.
- loginProcessingUrl("/auth/sign-in") nằm ngoài securityMatcher("/private/**") của chain đang có formLogin → filter xử lý login không áp dụng cho POST đó.
- Static URL bị chain API match trước và yêu cầu Bearer token, khiến trang login web tải thiếu CSS/JS.
- Chỉ tạo một chain /api/** mà không có fallback; request khác có thể nằm ngoài Spring Security filter chain và trở thành lỗ hổng bảo mật.

Luôn lập bảng endpoint → chain → authorization rule → filter xử lý, thay vì chỉ nhìn một dòng requestMatchers().permitAll().

## 10. Cách kiểm tra static resource có thật sự được phục vụ

Từ trình duyệt mở DevTools → Network và tải GET /login trong phiên chưa đăng nhập. Kiểm tra ít nhất:

| Request | Mong đợi | Dấu hiệu lỗi |
| --- | --- | --- |
| GET /login | HTTP 200, Content-Type text/html | 302 liên tục hoặc 404 |
| GET /css/login.css | 200, Content-Type text/css | 302 tới login, 404 hoặc nhận HTML |
| GET /js/login.js | 200, JavaScript content | 302 hoặc JS parse error vì nhận HTML |
| GET /images/logo.svg | 200, image/svg+xml | 404, 302 hoặc resource không được đóng gói |
| GET /dashboard khi chưa login | 302 Location /login | Trả 200 không cần authentication |
| POST /login thiếu CSRF | Thường 403 | Đã tắt CSRF ngoài ý muốn nếu trả login response |

**Một CSS URL trả HTTP 200 không đủ:** nếu nó thực chất trả HTML login với status 200 qua proxy/fallback rewrite, browser vẫn không áp CSS. Kiểm tra Content-Type, response body và URL được redirect. Đọc cột Request URL, Status, Location trong Network.

Có thể thử từ terminal:

~~~bash
curl -i http://localhost:8080/css/login.css
curl -I http://localhost:8080/js/login.js
curl -i http://localhost:8080/dashboard
~~~

curl -I dùng HEAD; kết quả HEAD có thể khác GET nếu hệ thống cấu hình đặc biệt. GET là request quan trọng nhất để kiểm tra nội dung và media type thực tế.

### Log có ích ở môi trường development

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Log có thể hỗ trợ xác định chain/filter nào xử lý GET /login, GET /css/login.css hoặc POST /login. Nội dung và tên message thay đổi theo phiên bản; không nên xây quy trình kiểm chứng chỉ dựa vào một câu log cứng. Không bật TRACE lâu dài trong production và không ghi Authorization header, cookie, CSRF token hoặc password vào log.

## 11. Lỗi phổ biến và giải pháp

### 11.1. Redirect loop tại /login

**Triệu chứng:** browser liên tục đổi địa chỉ về /login hoặc báo too many redirects. **Nguyên nhân thường gặp:** URL login bị yêu cầu authenticated, hoặc SecurityFilterChain được chọn không chứa permitAll phù hợp. Kiểm tra SecurityFilterChain, securityMatcher và luật authorization trước; không chữa bằng cách permitAll toàn bộ ứng dụng.

### 11.2. Trang login 404

**Triệu chứng:** GET /login trả 404 hoặc template lỗi. **Nguyên nhân:** đã gọi loginPage("/login") nhưng quên @Controller GET /login, dùng @RestController trả String, đặt template sai thư mục hoặc thiếu Thymeleaf dependency. Phân biệt “được phép truy cập” với “có endpoint/controller phục vụ”.

### 11.3. CSS/JS nhận 302 hoặc nội dung HTML

**Nguyên nhân:** static URL chưa được permitAll, URL bị chain khác xử lý, link trong template sai context path, hoặc proxy rewrite. Thêm đúng URL/resource matcher, dùng th:href/th:src và kiểm tra Network. Không mở /**.

### 11.4. CSS/JS nhận 404

**Nguyên nhân:** file chưa có tại src/main/resources/static/... hoặc URL vẫn kèm /static, build không đóng gói file, static-path-pattern đã đổi, hoặc template dẫn đến tên file sai. Khi Spring Boot dùng static root, /static/css/login.css trên filesystem thường thành /css/login.css trên URL.

### 11.5. POST /login trả 403 ngay cả với password đúng

**Nguyên nhân thường gặp:** thiếu/không hợp lệ CSRF token. Xác nhận form đã render hidden _csrf, browser gửi cookie và token liên quan, không có hai context/session lệch nhau. Trong test dùng .with(csrf()); không tắt CSRF để “chữa” vội.

### 11.6. POST /login trả 404, 405 hoặc không đăng nhập

**Nguyên nhân:** form action khác loginProcessingUrl, filter chain không bao phủ URL POST, dùng method GET, tên username/password parameter khác cấu hình, hoặc custom controller/filter can thiệp. Kiểm tra POST thật trong Network và matcher của UsernamePasswordAuthenticationFilter.

### 11.7. Nhập đúng password nhưng vẫn quay lại /login?error

Kiểm tra UserDetailsService, PasswordEncoder.matches và giá trị account hợp lệ; demo password là local-demo-only và username student. Cũng kiểm tra form input name, AuthenticationManager/Provider, exception log an toàn. Đừng in raw password hoặc encoded hash ra log để debug.

### 11.8. Sau login luôn vào dashboard, không về trang yêu cầu trước đó

Ví dụ dùng defaultSuccessUrl("/dashboard", true): cờ true **cố ý** ép redirect tới dashboard. Nếu muốn ưu tiên URL đã lưu trước login, dùng chính sách saved request và handler phù hợp, tránh open redirect. Đây là quyết định UX, không phải lỗi session.

### 11.9. Logout qua link GET không hoạt động

Với CSRF bật, logout mặc định thường chỉ thực thi qua POST hợp lệ. Dùng form method=post, th:action="@{/logout}" và token CSRF. Không đổi GET logout trừ khi đã phân tích rủi ro và contract riêng.

### 11.10. Trang lỗi login công khai nhưng lộ account enumeration

Thông báo “user không tồn tại” khác “password sai” có thể hỗ trợ dò tài khoản. Dùng thông báo chung, giới hạn retry, giám sát bất thường, HTTPS và MFA theo yêu cầu. Không đưa exception nguyên bản trong query string/HTML.

### 11.11. Thêm static permitAll nhưng bỏ bảo vệ các tệp nhạy cảm

Thư mục public static không phải nơi lưu private upload, config, secret, backup, PDF nội bộ hoặc thông tin người dùng. PermitAll("/images/**") công khai **mọi request match pattern**, không phân biệt nội dung có nhạy cảm không. Đối với file riêng tư, phục vụ qua controller/storage với kiểm tra authorization đúng nghiệp vụ, không đặt trong static root.

### 11.12. Dùng ignoring để “tăng tốc” nhưng mất security headers

Bỏ qua FilterChainProxy đồng nghĩa bỏ qua các security filter cho request đó, có thể mất header hardening, logging hoặc custom security policy. Trước khi tối ưu, đo đạc thực tế và ưu tiên permitAll; cân nhắc CDN/public assets bằng kiến trúc riêng nếu cần.

## 12. Checklist triển khai an toàn

Trước khi đưa trang login tùy chỉnh vào production:

1. **Có GET /login thực sự** và template render đúng khi anonymous; không nhầm với POST /login.
2. **Có POST loginProcessingUrl đúng**, với username/password parameter names khớp form và filter.
3. **Các URL login + lỗi/đăng xuất thành công công khai** đúng phạm vi, không mở rộng sang dashboard/admin/API.
4. **CSS, JS, images và favicon tải được khi chưa login** với status/content type đúng; kiểm thử cả deep-link, proxy và context path.
5. **Thư mục templates không bị phơi trực tiếp**, và không đặt secrets/private user files dưới static root.
6. **CSRF vẫn phù hợp**, form POST và logout POST có token; dùng test kiểm tra request thiếu token bị từ chối.
7. **Redirect đúng UX**, không tạo vòng lặp; kiểm soát saved-request, failureUrl và open redirect.
8. **PasswordEncoder/UserDetailsService/Provider được cấu hình thật**, tài khoản production không hardcode và được bảo vệ bằng HTTPS.
9. **Không tạo trùng controller POST login** với endpoint mà UsernamePasswordAuthenticationFilter đã xử lý.
10. **Với nhiều chain, kiểm thử chain chọn cho từng URL**, kể cả static và login processing.
11. **Bảo vệ biểu mẫu trước brute force và account enumeration**, hạn chế log dữ liệu nhạy cảm và áp dụng MFA khi cần.
12. **Kiểm thử tích hợp và trình duyệt thật** sau thay đổi SecurityFilterChain, template, version Boot/Security, static resource mapping và reverse proxy.

## 13. Tự kiểm tra

**Câu 1.** Khi gọi formLogin().loginPage("/login"), framework còn tự sinh trang login mặc định tại URL đó không? Ai chịu trách nhiệm GET /login?

**Đáp án:** ứng dụng phải cung cấp GET /login (ví dụ @Controller trả view login); custom loginPage không tự tạo HTML template cho bạn.

**Câu 2.** Vì sao GET /login phải được permitAll, trong khi GET /dashboard vẫn cần authenticated?

**Đáp án:** nếu trang login cũng bị bảo vệ, user anonymous không thể tiếp cận form để đăng nhập và có thể gặp vòng lặp redirect. Dashboard là tài nguyên nghiệp vụ nên tiếp tục bảo vệ.

**Câu 3.** Một file có đường dẫn src/main/resources/static/css/login.css thì URL mặc định là gì?

**Đáp án:** /css/login.css, không có phần /static. Nếu có context path /myapp, URL phía client thường là /myapp/css/login.css.

**Câu 4.** formLogin().permitAll() và web.ignoring() giống nhau không?

**Đáp án:** không. permitAll cho phép request đi qua SecurityFilterChain và bỏ yêu cầu authorization ở URL tương ứng; ignoring bỏ qua Spring Security filter chain, làm mất các filter/security headers cho URL đó.

**Câu 5.** Vì sao form đúng username/password nhưng POST /login nhận 403?

**Đáp án:** CSRF token có thể thiếu/sai, khiến CsrfFilter từ chối trước bước kiểm tra mật khẩu. Cần xem hidden field/token và session/cookie, không tự tắt CSRF.

**Câu 6.** Muốn form gửi tới POST /authenticate thay vì /login phải đổi gì?

**Đáp án:** đặt loginProcessingUrl("/authenticate") và th:action="@{/authenticate}" trong HTML; bảo đảm request POST thuộc security chain phù hợp.

**Câu 7.** Nếu CSS trả redirect tới /login mà HTML trang login vẫn 200 thì trang có style không?

**Đáp án:** thường không. Browser yêu cầu text/css nhưng nhận redirect/HTML, dẫn tới style bị bỏ qua hoặc báo MIME error. Phải cho phép URL CSS và xác minh response body.

**Câu 8.** Khi có một /api/** chain và một web chain, tại sao request /css/login.css có thể bị 401?

**Đáp án:** có thể URL static bị chain API hoặc chain tổng quát khác match trước khi tới web chain; phải kiểm tra @Order, securityMatcher, authorization và static mapping.

**Câu 9.** Có nên đưa private avatar/document vào src/main/resources/static/images và permitAll("/images/**")?

**Đáp án:** không. Chỉ đặt tài nguyên công khai ở static root; file riêng tư cần endpoint/storage có authorization theo chủ sở hữu và kiểm soát truy cập.

**Câu 10.** Vì sao login success luôn về /dashboard trong ví dụ, dù trước đó user vào /private?

**Đáp án:** defaultSuccessUrl("/dashboard", true) ép redirect tới đường dẫn này. Nếu cần trở về URL đã yêu cầu, đổi chính sách success handler/saved request.

## Kết luận

Để làm trang đăng nhập tự tạo trong Spring Security Servlet, cần **kết hợp đúng ba tầng**:

- **MVC/view:** Controller phục vụ GET /login, Thymeleaf render form và đường dẫn CSS/JS/images.
- **Spring Security:** SecurityFilterChain cho phép các URL công khai cần thiết, UsernamePasswordAuthenticationFilter xử lý POST login, AuthenticationManager xác minh credentials, các thành phần success/failure/logout quyết định redirect.
- **CSRF và resource delivery:** biểu mẫu POST có token, tài nguyên tĩnh được truy cập khi anonymous nhưng không vô tình phơi URL nghiệp vụ hay file nhạy cảm.

Hãy kiểm thử GET /login, GET từng static URL, POST /login đúng/sai/thiếu CSRF, GET dashboard trước/sau login và POST logout. **Trang được render, assets tải được, và tài nguyên riêng vẫn được bảo vệ** mới là một luồng đăng nhập hoàn chỉnh.