# Tài nguyên tĩnh, trang lỗi và endpoint đăng nhập cũng cần được xét tới

## 1. Vì sao bảo vệ endpoint không chỉ gồm API nghiệp vụ?

Khi bật Spring Security cho ứng dụng web, ta thường tập trung vào API như **/account/**, **/orders/** hoặc **/admin/**. Nhưng một request để người dùng thực sự sử dụng ứng dụng còn có thể cần:

- Tải tài nguyên tĩnh: CSS, JavaScript, ảnh, favicon.
- Mở trang đăng nhập và gửi thông tin xác thực.
- Xem thông báo đăng nhập thất bại, đăng xuất thành công hoặc trang từ chối truy cập.
- Nhìn thấy trang lỗi có ý nghĩa khi URL không tồn tại hay server gặp lỗi.
- Truy cập URL được chuyển tiếp nội bộ qua cơ chế servlet dispatcher.

Nếu áp dụng một quy tắc bao phủ mọi thứ như **anyRequest().authenticated()** mà không suy nghĩ về các đường dẫn phục vụ việc đăng nhập, người chưa xác thực có thể bị chuyển về trang đăng nhập nhưng CSS và ảnh của trang đó cũng bị bảo vệ. Nếu trang đăng nhập tùy chỉnh không được phép truy cập, quá trình chuyển hướng có thể tạo vòng lặp hoặc trang hiển thị sai. Nếu lỗi phía server được điều phối sang **/error** nhưng dispatch lỗi lại đòi xác thực, người dùng có thể thấy thông báo đăng nhập/403 thay cho lỗi ban đầu.

Mục tiêu bài học: **xét đầy đủ các nhóm request phụ trợ khi thiết kế chính sách**, phân biệt request HTTP thông thường với ERROR/FORWARD dispatch, hiểu chính xác quyền cho trang đăng nhập và ưu tiên các ngoại lệ hẹp trước quy tắc bảo vệ phần còn lại.

> Phạm vi kỹ thuật: ví dụ chính dùng **Spring Boot 3.x, Spring MVC/Servlet, Spring Security 6.x, Java 17+**. Trong Spring WebFlux, nguyên tắc tương đương nhưng API cấu hình reactive khác; không dùng Servlet FilterChain/HttpSecurity cho ứng dụng WebFlux thuần.

## 2. Một website cần những đường dẫn nào?

Xét website quản lý nội bộ có trang đăng nhập, trang hồ sơ và khu vực quản trị:

| Nhóm | Request ví dụ | Quy tắc gợi ý | Lý do |
| --- | --- | --- | --- |
| Tài nguyên tĩnh công khai | GET /css/site.css, /js/app.js, /images/logo.png | **permitAll()** cho các vị trí công khai đã chọn | Trình duyệt cần tải giao diện trước khi đăng nhập |
| Trang đăng nhập | GET /login | **permitAll()** | Người chưa đăng nhập phải xem được biểu mẫu |
| Xử lý đăng nhập | POST /login | Cho phép Spring Security xử lý credentials; cấu hình formLogin(...).permitAll() | Người dùng chưa xác thực phải có khả năng gửi form |
| Thông báo đăng nhập lỗi | GET /login?error | Tương ứng GET /login | Query parameter không phải một URL bảo vệ riêng |
| Trang công khai | GET /about | **permitAll()** nếu nghiệp vụ chủ động công khai | Nội dung không nhạy cảm |
| Trang hồ sơ | GET /private | **authenticated()** | Chỉ người dùng đã đăng nhập |
| Khu vực quản trị | GET /admin | **hasRole("ADMIN")** | Cần authority **ROLE_ADMIN** theo mặc định |
| Servlet ERROR dispatch | Dispatch tới /error | Có thể **permitAll** theo DispatcherType.ERROR | Giúp render lỗi gốc, không đòi đăng nhập lần nữa |
| Trang từ chối truy cập | Trang hiển thị sau 403, nếu tự xây dựng | Quyết định rõ quyền GET và cơ chế error/forward | Không tạo vòng lặp khi người thiếu quyền cần đọc thông báo |
| URL khác | /internal/..., method không dự kiến | **denyAll()** hoặc chính sách rõ ràng khác | Tránh vô tình mở endpoint mới |

Đây là ví dụ chính sách. Không phải mọi tệp tĩnh đều phải công khai: tài liệu xuất theo yêu cầu người dùng, file đính kèm riêng tư và dữ liệu tenant **không** nên được đặt vào thư mục static công khai chỉ để tải nhanh.

**permitAll không có nghĩa "bỏ qua Spring Security".** Nó chỉ cho phép về mặt authorization; các lớp security liên quan khác trong filter chain vẫn có thể xử lý request.

## 3. Tài nguyên tĩnh: URL thật khác vị trí tệp trên đĩa

Với Spring Boot MVC và cấu hình static mặc định, các tệp thông dụng có thể được phục vụ từ những vị trí trên classpath như:

~~~text
src/main/resources/static/css/site.css
src/main/resources/static/js/app.js
src/main/resources/static/images/logo.png
~~~

URL tương ứng thường là:

~~~text
GET /css/site.css
GET /js/app.js
GET /images/logo.png
~~~

**Không tự thêm /static vào URL.** Thư mục **static** là nơi Spring Boot tìm tài nguyên, không nhất thiết là một phần của request path. Nếu ứng dụng đã đổi **spring.mvc.static-path-pattern**, cấu hình resource handler hay context path, phải kiểm tra URL thực tế thay vì đoán từ cấu trúc tệp.

### 3.1. Cấu hình permitAll theo các đường dẫn cụ thể

Fragment trong cấu hình Spring Security Servlet:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/css/**", "/js/**", "/images/**")
            .permitAll()
        .anyRequest().authenticated());
~~~

Mẫu này đơn giản khi ứng dụng kiểm soát rõ những đường dẫn. Tuy nhiên, nó có hai giới hạn: quên một thư mục mới như **/webjars/** thì có thể khiến giao diện mất tài nguyên; dùng matcher quá rộng như **/*** sẽ mở cả URL nhạy cảm.

Spring Boot còn cung cấp matcher tiện lợi:

~~~java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;

// Bên trong authorizeHttpRequests:
.requestMatchers(PathRequest.toStaticResources().atCommonLocations())
    .permitAll()
~~~

**PathRequest.toStaticResources().atCommonLocations()** khớp các vị trí tài nguyên tĩnh thông dụng mà Spring Boot biết. Đây là API của **Spring Boot Servlet**, không phải phương thức của Spring Security core. Nếu dự án dùng vị trí custom, cần xem lại matcher thực tế và thêm quy tắc riêng phù hợp.

### 3.2. permitAll khác web.ignoring

Hai cách dưới đây có kết quả rất khác:

| Cách | Tài nguyên có đi qua Spring Security FilterChainProxy không? | Tác động |
| --- | --- | --- |
| **requestMatchers("/css/**").permitAll()** | Có | Cho phép authorization nhưng filter bảo mật liên quan, bao gồm cơ chế gắn security headers, vẫn có cơ hội chạy. |
| **WebSecurityCustomizer / web.ignoring()** | Không, với URL bị ignore | Bỏ qua toàn bộ Spring Security filter chain cho URL đó; headers từ Spring Security sẽ không được thêm qua chain này. |

Trong Spring Security hiện đại, hướng thường được khuyến nghị là **permitAll cho static assets** thay vì bỏ qua filter chain. Không dùng ignoring chỉ vì cho rằng "file tĩnh thì không liên quan bảo mật". Với tài nguyên bắt buộc được bảo vệ, cần áp dụng policy phù hợp chứ không để trong vùng bỏ qua.

### 3.3. Tệp nào nên công khai?

- **Thường công khai:** CSS/JS phục vụ trang đăng nhập, logo, ảnh giao diện chung, phông chữ công khai, favicon.
- **Thường cần kiểm soát:** file PDF cá nhân, báo cáo riêng, ảnh người dùng chưa được duyệt công khai, attachment, dữ liệu theo tenant, file tải xuống có thông tin nhạy cảm.
- **Không nên xuất như static:** cấu hình nội bộ, secret, private key, source code chưa phát hành hoặc dữ liệu cần kiểm tra ownership.

Cho phép **/images/** không tự làm mọi tài nguyên trở nên an toàn; cần chắc chắn thư mục đó **chỉ chứa nội dung phù hợp để công khai**. Nếu cần bảo vệ nội dung tải xuống, nên đưa nó qua endpoint hoặc cơ chế phân phối có authorization và kiểm tra quyền trên từng tài nguyên.

## 4. Trang đăng nhập là một phần của luồng bảo mật

### 4.1. GET /login và POST /login có hai vai trò

Khi dùng form login với trang đăng nhập tùy chỉnh:

~~~text
Người chưa đăng nhập -> GET /private
                           |
                           v
                       Không đủ xác thực
                           |
                           v
                   Redirect 302 -> GET /login
                                      |
                                      +--> HTML + CSS/JS công khai
                                      |
                                      +--> Người dùng nhập credentials
                                      |
                                      v
                                  POST /login
                                      |
                                      +--> Form authentication filter kiểm tra
                                             |
                                             +--> Thành công: lưu SecurityContext theo cấu hình,
                                             |                 redirect tới trang đích
                                             |
                                             +--> Thất bại: redirect /login?error
~~~

- **GET /login** thường được MVC Controller hoặc template engine phục vụ, trả HTML.
- **POST /login** trong form login mặc định là **đường xử lý xác thực do filter Spring Security đảm nhận**. Không cần tự thêm một @PostMapping("/login") chỉ để xác thực username/password trong ví dụ này.
- **loginPage("/login")** xác định trang biểu mẫu; **loginProcessingUrl("/login")** xác định URL nhận credentials.
- **formLogin(...).permitAll()** đảm bảo các đường phục vụ quá trình đăng nhập được cho phép theo cấu hình tương ứng, ví dụ trang đăng nhập và đường xử lý form.
- **failureUrl("/login?error")** là nơi người dùng được đưa về khi sai credentials. URL path vẫn là **/login**; phần **?error** không làm thay đổi request path matcher.

Trang đăng nhập không tự an toàn chỉ vì được permitAll: POST login phải được Spring Security xác thực đúng cách, HTTPS cần thiết trong production, cookie/session cần cấu hình phù hợp và ứng dụng phải duy trì bảo vệ CSRF cho form.

### 4.2. Trang đăng nhập được sinh sẵn và trang đăng nhập tùy chỉnh

Nếu dùng **formLogin(Customizer.withDefaults())** và không đặt trang tùy chỉnh, Spring Security có thể sinh trang đăng nhập mặc định để phát triển. Khi dùng **loginPage("/login")**, **ứng dụng phải thực sự phục vụ GET /login**, ví dụ qua một MVC Controller trả về template **login**. Chỉ thêm cấu hình loginPage mà không có handler/template có thể làm request đăng nhập kết thúc bằng 404 hoặc vòng lặp khó hiểu.

Các URL liên quan như **/login?error**, **/login?logout** nên được kiểm tra trong thử nghiệm thực tế, vì chúng là phần người dùng nhìn thấy khi xác thực thất bại hoặc logout thành công.

## 5. Trang lỗi và DispatcherType: cùng URL chưa chắc cùng ngữ cảnh

Servlet API có nhiều kiểu dispatch, trong đó quan trọng nhất ở đây là:

| DispatcherType | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| **REQUEST** | Request ban đầu từ client | Trình duyệt gọi GET /private |
| **ERROR** | Server/container điều phối để xử lý lỗi | Một exception dẫn tới error handling ở /error |
| **FORWARD** | Request được chuyển tiếp nội bộ sang resource khác | Controller chuyển tiếp tới một view hoặc handler |
| **ASYNC** | Xử lý bất đồng bộ cần một lượt dispatch khác | Servlet async processing |

**GET /error từ bên ngoài** và **ERROR dispatch nội bộ đến /error** không giống nhau: cùng một URL có thể mang DispatcherType khác nhau. Nếu dự án dùng quy tắc authorization cho các dispatcher type, một request gốc đã qua kiểm tra quyền có thể gặp kiểm tra lần thứ hai khi render lỗi.

Spring Security hỗ trợ matcher theo dispatcher type:

~~~java
import jakarta.servlet.DispatcherType;

// Trong cấu hình authorizeHttpRequests:
.dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
~~~

Rule này chỉ cho phép **ERROR dispatch**, không mặc nhiên cho phép **mọi REQUEST trực tiếp tới /error**. Đó là một cách biểu đạt chủ đích rõ hơn so với cho phép mọi lượt gọi **/error** theo path. Tùy ứng dụng, việc cho phép error dispatch có thể giúp giữ lại thông báo 404/500 hoặc trang lỗi gốc.

Tài liệu Spring Security còn minh họa việc cho phép **DispatcherType.FORWARD, DispatcherType.ERROR** khi kiến trúc view rendering cần các lượt chuyển tiếp đó. Tuy nhiên, **không mở toàn bộ FORWARD một cách máy móc**: nếu ứng dụng có internal forward đến handler nhạy cảm, phải xét đường đi và điểm áp dụng authorization để tránh tạo lối truy cập ngoài ý định.

### 5.1. Lỗi 403 có phải lúc nào cũng đi qua /error?

Không. **403** có thể do authorization, CSRF, access-denied handling hoặc thành phần ứng dụng trả trực tiếp. Tùy cách cấu hình **AccessDeniedHandler**, exception handling và container, response có thể được trả trực tiếp hay điều phối đến error view. **/error** thường liên quan hạ tầng xử lý lỗi của Spring Boot MVC; không được coi nó là toàn bộ cơ chế xử lý mọi status lỗi.

Cũng không thể kết luận một URL không tồn tại luôn trả 404. Nếu SecurityFilterChain từ chối request **trước khi MVC tìm handler**, response có thể là 302 đến login, 401 hoặc 403 tùy cơ chế xác thực. Để thử một trang 404 công khai, cần có một đường dẫn được cho qua authorization nhưng không có resource/controller thực tế.

### 5.2. Trang lỗi tùy chỉnh phải an toàn

Nếu ứng dụng tự xây dựng trang lỗi, ví dụ **templates/error/404.html** hoặc **templates/error/500.html** trong ứng dụng Boot dùng template engine, nên hiển thị thông tin thân thiện với người dùng:

- Không lộ stack trace, thông tin SQL, đường dẫn filesystem hoặc token.
- Không phụ thuộc vào tài nguyên tĩnh chỉ người đã đăng nhập mới tải được.
- Không biến đường dẫn lỗi thành một API tra cứu dữ liệu bí mật.
- Phân biệt **thông báo được quyền xem** với **chi tiết lỗi phục vụ logging nội bộ**.

Cho phép hiển thị thông báo lỗi không đồng nghĩa cho phép truy cập dữ liệu bị bảo vệ hoặc xử lý thành công nghiệp vụ ban đầu.

## 6. Demo hoàn chỉnh: Spring Boot 3, CSS công khai, form login và ERROR dispatch

Ví dụ này cho thấy ba luồng trong cùng ứng dụng:

1. Người chưa đăng nhập tải được **/login** và **/css/site.css**.
2. Người chưa đăng nhập bị redirect khi truy cập **/private**, còn người có ROLE_USER đăng nhập xong truy cập được.
3. Lỗi do request công khai **/broken** gây ra được xử lý với HTTP 500; việc cho phép ERROR dispatch không biến lỗi thành thành công.

### 6.1. Tạo dự án và tệp

Dùng **Spring Initializr** tạo dự án **Gradle**, **Java 17+**, **Spring Boot 3.x**, group **com.example**, artifact **demo**. Chọn dependencies:

- **Spring Web** (spring-boot-starter-web)
- **Spring Security** (spring-boot-starter-security)
- **Thymeleaf** (spring-boot-starter-thymeleaf)

Tạo ba tệp sau:

~~~text
src/main/java/com/example/demo/SecurityAssetsApplication.java
src/main/resources/templates/login.html
src/main/resources/static/css/site.css
~~~

Giữ nguyên tập tin cấu hình/build do Spring Initializr sinh ra. Không cần tự viết bộ lọc xác thực mới; Spring Security đã cung cấp xử lý form login.

### 6.2. Java: SecurityAssetsApplication.java

Đặt **toàn bộ** mã sau trong **src/main/java/com/example/demo/SecurityAssetsApplication.java**:

~~~java
package com.example.demo;

import jakarta.servlet.DispatcherType;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@SpringBootApplication
public class SecurityAssetsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityAssetsApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                // Cho phép dispatch nội bộ khi render lỗi.
                .dispatcherTypeMatchers(DispatcherType.ERROR)
                    .permitAll()

                // CSS, JS, ảnh và static resources thông dụng.
                .requestMatchers(
                    PathRequest.toStaticResources().atCommonLocations())
                    .permitAll()

                // Trang đăng nhập, trang công khai và endpoint thử lỗi.
                .requestMatchers(HttpMethod.GET,
                    "/login", "/hello", "/broken")
                    .permitAll()

                // POST /login được form-login filter xử lý.
                .requestMatchers(HttpMethod.POST, "/login")
                    .permitAll()

                // Vùng nội bộ chỉ cần xác thực.
                .requestMatchers(HttpMethod.GET, "/private")
                    .authenticated()

                // Vùng quản trị cần ROLE_ADMIN.
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")

                // Mặc định chặn mọi URL/method còn lại.
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/private", true)
                .failureUrl("/login?error")
                .permitAll()
            );

        // CSRF vẫn bật mặc định, kể cả với POST /login.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails member = User.withUsername("member")
                .password("{noop}demo123")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}demo123")
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(member, admin);
    }
}

@Controller
class DemoPages {

    @GetMapping("/login")
    String login() {
        return "login";
    }

    @ResponseBody
    @GetMapping("/hello")
    String publicPage() {
        return "public";
    }

    @ResponseBody
    @GetMapping("/private")
    String privatePage(Authentication authentication) {
        return "hello-" + authentication.getName();
    }

    @ResponseBody
    @GetMapping("/admin")
    String adminPage() {
        return "admin";
    }

    @ResponseBody
    @GetMapping("/broken")
    String broken() {
        throw new IllegalStateException("demo-error");
    }
}
~~~

**Giải thích cấu hình:**

- Matcher **DispatcherType.ERROR** xử lý chính xác lượt dispatch lỗi. Lượt REQUEST gốc vẫn phải qua các rule tiếp theo.
- **PathRequest** cho phép static assets thông dụng trong Spring Boot. Tài nguyên vẫn đi qua filter chain, nhờ vậy các security headers do Spring Security quản lý vẫn có cơ hội được thêm vào response.
- **GET /login** được MVC Controller trả template; **POST /login** do Spring Security xử lý. Không có @PostMapping("/login") tự xử lý mật khẩu.
- **authenticated()** yêu cầu đăng nhập ở GET /private.
- **hasRole("ADMIN")** mặc định yêu cầu authority **ROLE_ADMIN**, được sinh từ **roles("ADMIN")** của UserBuilder.
- **anyRequest().denyAll()** ngăn endpoint hoặc HTTP method ngoài danh sách tự động được công khai.
- Không disable CSRF. **{noop}demo123** chỉ dùng cho demo cục bộ; hệ thống thật phải dùng PasswordEncoder và kho người dùng phù hợp.

### 6.3. HTML: templates/login.html

Đặt nội dung sau vào **src/main/resources/templates/login.html**:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Đăng nhập</title>
    <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
<main class="login-card">
    <h1>Đăng nhập</h1>
    <p>Dùng member hoặc admin; mật khẩu demo123.</p>

    <form th:action="@{/login}" method="post">
        <label for="username">Tên đăng nhập</label>
        <input id="username" name="username" autocomplete="username"
               required>

        <label for="password">Mật khẩu</label>
        <input id="password" name="password" type="password"
               autocomplete="current-password" required>

        <button type="submit">Đăng nhập</button>
    </form>
</main>
</body>
</html>
~~~

Trong cấu hình **Thymeleaf kết hợp Spring MVC/Spring Security**, một form dùng **th:action** cho POST sẽ được xử lý qua cơ chế **RequestDataValueProcessor** và có CSRF token được chèn vào HTML render. Mẫu trên dùng tên field mặc định **username** và **password**, POST về đường **/login**. Có thể kiểm tra HTML thực tế trong DevTools để xác minh hidden CSRF field xuất hiện. Nếu dùng template engine hoặc form xây dựng theo cơ chế khác, phải chủ động gửi CSRF token theo yêu cầu của ứng dụng.

Đường dẫn **src/main/resources/templates/login.html** là nơi Thymeleaf tìm template, **không** phải static resource công khai với URL /templates/login.html. Người dùng truy cập qua **GET /login** do controller điều phối.

### 6.4. CSS: static/css/site.css

Đặt nội dung sau vào **src/main/resources/static/css/site.css**:

~~~css
body {
    font-family: Arial, sans-serif;
    background: #f4f6fb;
    margin: 0;
    padding: 40px 16px;
}
.login-card {
    max-width: 360px;
    margin: 0 auto;
    padding: 24px;
    background: white;
    border-radius: 10px;
    box-shadow: 0 5px 25px rgba(0, 0, 0, 0.08);
}
label {
    display: block;
    margin-top: 14px;
}
input, button {
    display: block;
    box-sizing: border-box;
    width: 100%;
    padding: 10px;
    margin-top: 6px;
}
button {
    margin-top: 20px;
    cursor: pointer;
}
~~~

Tệp CSS này được Boot phục vụ tại **GET /css/site.css**. Nó không cần đăng nhập nhờ matcher static. Nếu CSS ở trang login không tải được, mở trực tiếp URL /css/site.css trong cửa sổ ẩn danh và kiểm tra status, response content type, context path và quy tắc security đang khớp.

### 6.5. Khởi chạy

Tại thư mục gốc dự án Gradle:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng **gradlew.bat bootRun**. Mặc định ứng dụng lắng nghe trên **http://localhost:8080** nếu chưa đổi cấu hình cổng.

Trước khi đăng nhập, thử bằng trình duyệt:

1. Mở **http://localhost:8080/login**: biểu mẫu hiển thị cùng CSS.
2. Mở **http://localhost:8080/css/site.css**: response 200 và nội dung CSS.
3. Mở **http://localhost:8080/private**: trình duyệt bị chuyển đến /login.
4. Đăng nhập bằng **member / demo123**: browser được đưa tới **/private**, trả nội dung **hello-member**.
5. Mở **/admin** khi đang đăng nhập member: bị từ chối 403 vì thiếu ROLE_ADMIN.
6. Đăng nhập trong phiên mới bằng **admin / demo123**: có thể mở **/admin** và nhận **admin**.
7. Mở **/broken**: controller chủ động ném exception, response thường có status 500 và được Spring Boot xử lý qua error handling.

Với curl, có thể quan sát các request **GET** không cần CSRF token:

~~~bash
curl -i http://localhost:8080/login
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/private
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/broken
~~~

**Kết quả HTTP dự kiến từ cấu hình**, không phải log chạy thực tế:

| Request chưa đăng nhập | Status dự kiến | Vì sao |
| --- | --- | --- |
| GET /login | **200** | Được permitAll và có template |
| GET /css/site.css | **200** | Thuộc nhóm static được phép |
| GET /hello | **200** | Endpoint công khai |
| GET /private | **302** | Form-login entry point chuyển tới /login |
| GET /admin | **302** | Chưa có Authentication; được đưa tới /login |
| GET /broken | **500** | Controller ném exception, error handler giữ thông tin status |
| GET /css/missing.css | **404** (với resource không tồn tại) | Static path được phép đi tiếp đến MVC để báo không tìm thấy |

Nếu request đi qua reverse proxy, context path khác, custom error handler hoặc cấu hình khác, URL/status/header cụ thể có thể thay đổi. Với curl không tự follow redirect khi thiếu **-L**, bạn sẽ thấy **302** và header Location.

### 6.6. Chú ý khi thử POST /login bằng curl

Do **CSRF được bật**, gửi POST /login trực tiếp bằng curl mà **không có token và session phù hợp** có thể trả 403 *trước khi* cơ chế xác thực kiểm tra đúng/sai mật khẩu. Để thử login như trình duyệt, cần:

1. GET /login để nhận session cookie và CSRF token trong form.
2. Gửi POST /login với cookie của cùng phiên, field **username**, **password** và CSRF token tương ứng.
3. Quan sát redirect thành công đến /private hoặc redirect lỗi đến /login?error.

Trong trình duyệt, Thymeleaf form của ví dụ đã xử lý việc đưa token vào request. Đây là lý do ví dụ **không tắt CSRF chỉ để làm curl POST thuận tiện**. Với dự án khác kiểu xác thực, cơ chế token/cookie có thể khác; thiết kế CSRF phải dựa vào threat model thực tế.

## 7. Khi nào cần trang báo lỗi riêng?

Ứng dụng có thể cần trang hiển thị dễ hiểu cho:

- **401**: chưa xác thực hợp lệ, phổ biến ở API dùng Basic/Bearer; app dùng form-login thường redirect 302 thay vì trả 401 ngay.
- **403**: đã xác thực nhưng thiếu quyền, CSRF không hợp lệ hoặc access-denied handler từ chối.
- **404**: tài nguyên hoặc handler không tồn tại, *nếu request đã đi qua các kiểm tra bảo mật trước đó*.
- **500**: lỗi xử lý phía server.

### 7.1. Đừng sửa lỗi render 404/500 bằng cách permitAll mọi thứ

Trong ứng dụng dùng **anyRequest().denyAll()**, một URL mới chưa có rule có thể bị từ chối 403/redirect 302 trước khi MVC biết có handler hay không. Đây là hệ quả của chính sách deny-by-default, không nhất thiết do trang lỗi bị hỏng. Muốn hiển thị 404 cho một nhóm route công khai, cần cấp phép đúng nhóm route đó rồi để MVC xử lý tình trạng không tìm thấy.

Nếu lỗi phát sinh từ một endpoint đã được cho phép, ERROR dispatch cho phép sẽ hỗ trợ render lỗi gốc. Không nên dùng **requestMatchers("/**").permitAll()** để “khôi phục trang lỗi”, vì nó mở cả các endpoint cần bảo vệ.

### 7.2. Trang lỗi tùy chỉnh của Spring Boot

Trong ứng dụng dùng Thymeleaf, một mẫu trang lỗi có thể đặt ở **src/main/resources/templates/error/500.html**:

~~~html
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Không thể xử lý yêu cầu</title>
</head>
<body>
    <h1>Đã xảy ra lỗi máy chủ</h1>
    <p>Vui lòng thử lại sau hoặc liên hệ bộ phận hỗ trợ.</p>
</body>
</html>
~~~

Đây là tệp **tùy chọn**, bổ sung nếu muốn tùy biến UX cho status 500. Tương tự có thể tạo **templates/error/404.html** để hiển thị lỗi không tìm thấy. Không nên in exception stack trace, dữ liệu người dùng, tên bảng SQL hoặc cấu hình nội bộ vào view.

Với một trang **/access-denied** riêng cho 403, cần bảo đảm đường xem thông báo đó được phép với người cần thấy nó, ví dụ theo quy tắc GET cụ thể; đồng thời cấu hình **exceptionHandling/accessDeniedPage** nếu chọn dùng cơ chế này. Đừng kết luận rằng cứ có một Controller tên AccessDenied là Spring Security tự chuyển 403 đến đó.

### 7.3. Chọn đúng nơi xử lý lỗi

| Lớp xử lý | Phạm vi thường gặp | Điều cần nhớ |
| --- | --- | --- |
| AuthenticationEntryPoint | Người chưa xác thực bị yêu cầu đăng nhập | Form-login thường redirect tới /login; API Bearer/Basic thường dùng 401. |
| AccessDeniedHandler | Request đã được xác thực nhưng bị từ chối quyền | Có thể trả 403 hoặc chuyển đến trang từ chối tùy cấu hình. |
| Spring MVC exception handling | Exception từ controller/service | ControllerAdvice hoặc resolver có thể xử lý trước khi đưa về error dispatch. |
| Spring Boot /error | Xử lý lỗi fallback thông qua ErrorController và view | Có thể nhận ERROR dispatch; không mặc định thay thế mọi cơ chế lỗi ở trên. |

Nếu một request bị 403, hãy xem *nguyên nhân* trước: không phải mọi 403 đều do thiếu role; có thể là CSRF, method mismatch dẫn tới quy tắc deny hoặc access-denied handler.

## 8. Các lỗi thực tế và cách chẩn đoán

| Hiện tượng | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- |
| Trang /login redirect về chính /login nhiều lần | GET /login bị bảo vệ bởi authenticated hoặc loginPage không được permit | Cho phép đúng GET /login; dùng formLogin(...).permitAll(). |
| Login page hiện HTML nhưng mất CSS/JS | URL static bị bảo vệ, matcher sai hoặc tệp không nằm ở vị trí Boot phục vụ | Kiểm tra Network tab; dùng PathRequest hoặc permitAll hẹp cho /css/**, /js/**. |
| URL /static/css/site.css trả 404 | Nhầm đường dẫn classpath với URL web | Với default Boot, tệp static/css/site.css được phục vụ tại /css/site.css. |
| Gửi POST /login trả 403 trước khi xác thực | Thiếu CSRF token hoặc cookie phiên tương ứng | Kiểm tra form th:action, hidden CSRF field, session/cookie. |
| GET /login trả 404 | Đã cấu hình custom loginPage nhưng thiếu MVC handler hoặc template | Tạo controller GET /login và template login hợp lệ. |
| Login thành công nhưng vào /admin bị 403 | Authentication thiếu ROLE_ADMIN hoặc role mapping sai | Kiểm tra GrantedAuthority thực tế, phân biệt role và authority. |
| /broken trả redirect đăng nhập thay vì trang lỗi | Rule ERROR dispatch bị khóa hoặc cơ chế xử lý lỗi đang yêu cầu authentication | Kiểm tra DispatcherType, filter registration, error handler; chỉ cho phép dispatch cần thiết. |
| Direct GET /error có trạng thái khác ERROR dispatch | Hai request khác DispatcherType | Kiểm tra dispatcherTypeMatchers và requestMatchers path. |
| Static asset riêng tư bị tải công khai | Đặt vào static public hoặc permitAll quá rộng | Chuyển qua endpoint có authorization/ownership phù hợp. |
| File bị WebSecurityCustomizer ignoring | Bỏ qua cả security header/filter mong muốn | Ưu tiên permitAll qua security filter chain. |
| Người dùng nhận 403 khi URL lạ | anyRequest().denyAll() chặn trước MVC | Quy định chính sách cho các nhóm URL cần hỗ trợ; không mở toàn hệ thống. |
| Thêm permitAll toàn bộ FORWARD để sửa lỗi | Internal forward có thể tới handler nhạy cảm | Rà soát routing nội bộ; áp dụng rule hẹp và test các luồng forward. |

Bật log **chỉ trong môi trường phát triển khi cần**:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Khi điều tra, kiểm tra theo thứ tự:

1. URL và HTTP method chính xác.
2. DispatcherType của lượt request (REQUEST, ERROR hay FORWARD).
3. SecurityFilterChain được chọn.
4. RequestMatcher đầu tiên khớp.
5. Authentication và các authority (không log password/token).
6. Phản hồi 302/401/403/404/500 và đường chuyển hướng/dispatch.
7. Tệp static thực tế trong classpath, view template và HTML đã render.

Đừng chỉ xem mã HTML 200 của /login; hãy kiểm tra cả CSS được tải, token được gửi và request protected không lọt qua.

## 9. Những kiểm thử nên có sau khi cấu hình

Ma trận smoke test tối thiểu:

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Anonymous GET /login | 200, không bị vòng lặp redirect |
| Anonymous GET /css/site.css | 200, đúng nội dung CSS, được security headers xử lý |
| Anonymous GET /private | 302 tới /login |
| Member đăng nhập form hợp lệ | Thành công, redirect /private, có SecurityContext trong phiên |
| Member GET /admin | 403 |
| Admin GET /admin | 200 |
| POST /login không CSRF hợp lệ | Bị từ chối theo chính sách CSRF |
| GET /broken | Status 500, không biến thành redirect về login |
| GET /css/missing.css | Status lỗi tài nguyên không tồn tại, không bị chuyển tới trang login |
| GET URL nhạy cảm chưa cấp quyền | Bị từ chối theo rule dự phòng |
| Tệp riêng tư nằm ngoài static public | Không thể tải như asset công khai |

Trong kiểm thử tự động có thể dùng **spring-security-test + MockMvc**. Khi dùng **MockMvc**, test form login với CSRF có thể dùng helper từ spring-security-test; nếu thử authenticated session hoặc role thì cần thiết lập mock security context tương ứng. Không giả định test dùng @WithMockUser đủ để phát hiện mọi lỗi login flow: vẫn cần ít nhất một bài thử đi qua form thực tế/cookie/CSRF, và kiểm tra asset được trả đúng.

### Kiểm tra security headers

Tài nguyên permitAll **vẫn ở trong Spring Security filter chain**, nên các header như X-Content-Type-Options hoặc chính sách bảo mật khác do ứng dụng cấu hình có cơ hội được áp dụng. Header cụ thể phụ thuộc cấu hình/phiên bản và có thể được điều chỉnh qua reverse proxy; đừng khẳng định một danh sách header bất biến. Với tài nguyên bị web.ignoring, filter của Spring Security không thể tự thêm header cho response đó.

## 10. Khi thiết kế API-only hoặc Spring WebFlux

**Ứng dụng API-only:** có thể không có login.html, CSS hay flow redirect; thay vào đó có API xác thực và entry point trả 401/JSON. Dù vậy, nếu có OpenAPI UI, tài liệu API, lỗi JSON, health endpoint hoặc actuator, vẫn phải thiết kế quyền tương ứng. Không mặc định mở actuator endpoints hay tài liệu chứa thông tin nội bộ chỉ vì chúng phục vụ developer.

**Ứng dụng Spring WebFlux:** dùng **SecurityWebFilterChain** và **ServerHttpSecurity.authorizeExchange(...)**. URL static và login vẫn cần quy tắc phù hợp, nhưng **Servlet DispatcherType.ERROR/FORWARD không phải API để sao chép sang reactive**; WebFlux dùng pipeline exception handling riêng. Ví dụ định hướng (fragment trong cấu hình WebFlux, không phải chương trình độc lập):

~~~java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/css/**", "/js/**").permitAll()
        .pathMatchers("/login").permitAll()
        .pathMatchers("/private").authenticated()
        .pathMatchers("/admin").hasRole("ADMIN")
        .anyExchange().denyAll());
~~~

Fragment trên chỉ diễn đạt authorization; bean security chain hoàn chỉnh còn cần cấu hình formLogin/authentication phù hợp với WebFlux và xử lý lỗi/CSRF của reactive stack.

## 11. Tự đánh giá

1. Nếu /private chuyển hướng đến /login nhưng /login lại yêu cầu authenticated, bạn kỳ vọng hiện tượng gì?
2. Vì sao tệp ở **src/main/resources/static/css/site.css** thường truy cập bằng **/css/site.css**, không phải **/static/css/site.css**?
3. **permitAll** cho CSS khác **web.ignoring** ở điều gì liên quan security headers?
4. Nếu user gọi trực tiếp **GET /error**, điều đó có đồng nghĩa với một **ERROR dispatch** không?
5. Tại sao có thể cần **dispatcherTypeMatchers(ERROR).permitAll()** nhưng vẫn giữ quy tắc bảo vệ **/private** và **/admin**?
6. Đối với form login tùy chỉnh, **GET /login** và **POST /login** thường do thành phần nào xử lý?
7. Vì sao POST /login có thể cần CSRF token dù người gửi chưa đăng nhập?
8. Nếu GET /broken đã được permitAll và ném exception, vì sao kết quả mong muốn vẫn là 500 thay vì 200?
9. Điều gì có thể xảy ra khi cho phép mọi FORWARD dispatch mà không kiểm tra đường forward nội bộ?
10. Với một tệp PDF riêng của người dùng, tại sao không nên chỉ đặt tệp vào thư mục static rồi permitAll cho /files/**?

**Ghi nhớ:** Bảo vệ endpoint cần nhìn cả **hành trình request của người dùng**: tải CSS/JS/ảnh, hiển thị GET /login, xử lý POST /login, redirect sau xác thực, xử lý 403/404/500 và những dispatch nội bộ. Hãy cho phép đúng những request cần thiết, **ưu tiên permitAll thay vì bỏ hẳn security filter chain cho static assets**, phân biệt **REQUEST** với **ERROR/FORWARD** và giữ quy tắc bảo vệ rõ ràng cho phần còn lại.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Authorize HttpServletRequests (dispatcher types, permitAll static assets): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Form Login, custom login page và CSRF form: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security — CSRF protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Boot 3.3 API — PathRequest: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/security/servlet/PathRequest.html
- Spring Boot 3.3 API — StaticResourceRequest: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/security/servlet/StaticResourceRequest.html
- Spring Boot — Serving static content and custom error pages: https://docs.spring.io/spring-boot/reference/web/servlet.html
