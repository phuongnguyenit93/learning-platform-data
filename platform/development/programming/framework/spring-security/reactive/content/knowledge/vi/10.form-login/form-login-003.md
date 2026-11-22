# Tạo trang đăng nhập riêng và cấu hình địa chỉ xử lý đăng nhập trong Spring Security WebFlux

## Mục tiêu bài học

Trong ứng dụng **Spring Security - reactive**, Spring Security có thể tạo trang đăng nhập mặc định. Nhưng khi xây dựng sản phẩm, ta thường cần giao diện của riêng mình tại một URL dễ nhớ và đôi khi muốn **địa chỉ hiển thị trang đăng nhập khác với địa chỉ nhận dữ liệu đăng nhập**.

Bài thuộc nhóm **Đăng nhập biểu mẫu**. Sau khi học, bạn sẽ:

1. Phân biệt **GET trang đăng nhập**, **POST xử lý đăng nhập**, **URL báo lỗi**, và **URL sau khi đăng nhập thành công**.
2. Hiểu `ServerHttpSecurity.formLogin(...)`, `FormLoginSpec.loginPage(...)` và `requiresAuthenticationMatcher(...)` trong WebFlux.
3. Biết chính xác vì sao `loginPage("/signin")` mặc định cũng cấu hình **POST /signin**, và làm sao chuyển riêng sang **POST /auth/session**.
4. Tạo trang HTML/Thymeleaf riêng có các trường `username`, `password` và **CSRF token**.
5. Cấu hình route công khai, kết quả xác thực thành công/thất bại và lưu đăng nhập qua WebSession.
6. Dựng ví dụ đầy đủ bằng **Java 17+, Spring Boot 3.3.13, Spring WebFlux**, chạy bằng Gradle và kiểm thử bằng `WebTestClient`.
7. Nhận biết lỗi vòng lặp redirect, POST nhầm URL, thiếu CSRF, nhầm API Servlet, security chain không bao phủ login và trạng thái 401/403/302.

**Phạm vi:** Form login của **Spring Security WebFlux** với `SecurityWebFilterChain` và `ServerHttpSecurity`. Các API `HttpSecurity`, `SecurityFilterChain`, `UsernamePasswordAuthenticationFilter` và `loginProcessingUrl(...)` thuộc **Servlet**; không được sao chép chúng sang cấu hình reactive.

## 1. Bốn URL có vai trò khác nhau

Giả sử trang chủ ứng dụng cần đăng nhập. Ta chọn:

| Chức năng | URL minh họa | Ai xử lý? | Kết quả mong đợi |
| --- | --- | --- | --- |
| Trang đăng nhập riêng | `GET /signin` | WebFlux controller trả HTML/template | 200 và form |
| Nơi nhận dữ liệu đăng nhập | `POST /auth/session` | `AuthenticationWebFilter` của Spring Security | Xác thực credentials, redirect thành công/thất bại |
| Trang đăng nhập khi sai mật khẩu | `GET /signin?error` | Cùng controller ở `GET /signin` | 200 và thông báo lỗi chung |
| Trang sau đăng nhập | `GET /dashboard` | Handler ứng dụng, cần authenticated | 200 khi có session hợp lệ |

Lưu ý: **`GET /signin` và `POST /auth/session` là hai request khác nhau**. Controller chỉ cần render HTML cho GET; thông thường **không tự khai báo `@PostMapping("/auth/session")` để so sánh mật khẩu**, vì form authentication filter đã nhận request POST và giao cho `ReactiveAuthenticationManager`. Việc viết thêm controller POST trùng đường dễ dẫn đến xử lý không đúng hoặc không được gọi.

**Ba trạng thái của một yêu cầu cần đăng nhập:**

```text
GET /dashboard (chưa xác thực)
    |
    +--> security entry point: 302 Location: /signin
    |
    v
GET /signin
    |
    +--> WebFlux Controller render form HTML + CSRF token
    |
    v
POST /auth/session (username, password, _csrf)
    |
    +--> Spring Security Form AuthenticationWebFilter
            |
            +--> credentials đúng: SecurityContext + session, redirect
            |
            +--> credentials sai: redirect /signin?error
```

Mã HTTP chính xác phụ thuộc entry point/handlers và cấu hình cụ thể. Ví dụ này dùng redirect vì là ứng dụng web với form; REST API dùng Basic hoặc Bearer thường có cơ chế challenge 401 khác.

## 2. Phân biệt cấu hình mặc định và cấu hình riêng

### 2.1. Mặc định của Spring Security WebFlux

Khi bật form login mà không chọn URL tùy biến:

```java
http.formLogin(Customizer.withDefaults());
```

Theo hợp đồng `ServerHttpSecurity.FormLoginSpec`, Spring Security WebFlux có thể cung cấp trang mặc định tại **`GET /login`** và nhận credentials tại **`POST /login`**. Thất bại mặc định chuyển về **`/login?error`**. Nếu không cần thay giao diện, đây là cách nhanh để bắt đầu.

### 2.2. Chỉ đổi trang đăng nhập

```java
http.formLogin(form -> form.loginPage("/signin"));
```

Trong **WebFlux**, `loginPage("/signin")` có hiệu lực **đồng thời** đối với:

- URL entry point đưa người chưa đăng nhập đến.
- Trang mà **ứng dụng phải tự render** ở `GET /signin`.
- URL thông báo lỗi mặc định `/signin?error`.
- Mặc định, **địa chỉ thực hiện xác thực là POST /signin**.

Đây là khác biệt đáng nhớ với DSL Servlet: trong WebFlux, bạn không cần `loginProcessingUrl("/signin")`. `FormLoginSpec` reactive không cung cấp phương thức đó. Javadoc nói rõ việc đặt login page cũng đặt địa chỉ POST cùng đường dẫn, trừ khi bạn ghi đè matcher xác thực.

Khi tùy biến `loginPage`, **trang đăng nhập/đăng xuất được tạo tự động sẽ không còn được Spring Security cung cấp theo cấu hình mặc định đó**. Phải tự tạo trang login, trạng thái `?error`, và nếu ứng dụng cần trang xác nhận logout thì tự cung cấp UI tương ứng. Filter logout POST vẫn là vấn đề cấu hình riêng.

### 2.3. Đổi riêng địa chỉ POST

Nếu muốn giữ **`GET /signin`** nhưng gửi form tới **`POST /auth/session`**:

```java
http.formLogin(form -> form
    .loginPage("/signin")
    .requiresAuthenticationMatcher(
        new PathPatternParserServerWebExchangeMatcher(
            "/auth/session", HttpMethod.POST)));
```

- `loginPage` điều khiển đường dẫn trang và hướng redirect đến trang đăng nhập.
- `requiresAuthenticationMatcher(...)` chỉ định **request nào sẽ kích hoạt form authentication filter**. Trong ví dụ, phải đúng cả **path** và **HTTP method POST**.
- Form HTML phải đặt `action="/auth/session"` và `method="post"` tương ứng.
- Mặc định converter form lấy các trường `username`, `password` trong body `application/x-www-form-urlencoded`.
- Bản thân URL `/auth/session` **không cần một controller POST riêng**.
- `GET /auth/session` không phải POST authentication request. Nếu không có handler GET và bị bảo vệ, nó có thể dẫn đến redirect/challenge/404 tùy chain; không được coi là đã xác thực.

**Thứ tự trong cấu hình nên rõ ràng:** đặt `loginPage(...)` rồi `requiresAuthenticationMatcher(...)`. Cách này dễ hiểu vì matcher POST được ghi đè sau các mặc định mà `loginPage` áp dụng.

### 2.4. Đừng trộn API Servlet và Reactive

| Nhu cầu | Spring Security WebFlux | Spring Security Servlet |
| --- | --- | --- |
| Cấu hình | `ServerHttpSecurity` | `HttpSecurity` |
| Security chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Form login | `ServerHttpSecurity.FormLoginSpec` | `FormLoginConfigurer` |
| Trang login | `loginPage("/signin")` | `loginPage("/signin")` |
| POST xử lý đường riêng | `requiresAuthenticationMatcher(ServerWebExchangeMatcher)` | `loginProcessingUrl("/auth/session")` |
| Authentication filter | `AuthenticationWebFilter` | `UsernamePasswordAuthenticationFilter` |
| Request/context | `ServerWebExchange`, Reactor Context | `HttpServletRequest`, ThreadLocal/Servlet |
| Session | `WebSession` | `HttpSession` |

Nếu thấy hướng dẫn dùng `.loginProcessingUrl(...)` trên `HttpSecurity`, trước khi sao chép phải xác định đó là ví dụ **Servlet** hay **WebFlux**.

## 3. Tách rõ phần của ứng dụng và phần của framework

Luồng đầy đủ ở mức filter:

```text
Browser
  |
  | GET /signin
  v
WebFlux WebFilter chain
  |
  v
Spring Security WebFilterChainProxy
  |
  +-- chọn SecurityWebFilterChain có formLogin
  +-- CSRF filter tạo/đưa token cho request
  +-- authorization cho phép GET /signin
  |
  v
@Controller GET /signin -> template signin.html
  |
  v
Browser nhận HTML form

Browser
  |
  | POST /auth/session, Content-Type: application/x-www-form-urlencoded
  | username=...&password=...&_csrf=...
  v
Spring Security WebFilterChainProxy
  |
  +-- CSRF filter kiểm tra token ở POST
  +-- AuthenticationWebFilter:
          |
          +-- requiresAuthenticationMatcher khớp POST /auth/session
          +-- converter -> UsernamePasswordAuthenticationToken
          +-- ReactiveAuthenticationManager xác thực
          +-- nếu đúng: lưu SecurityContext, success handler redirect
          +-- nếu sai: failure handler redirect /signin?error
  |
  v
Browser nhận redirect -> gửi request mới kèm session cookie
```

Có ba trách nhiệm độc lập:

1. **Trang HTML:** bố cục, thông báo lỗi không tiết lộ thông tin nhạy cảm, form fields, CSRF token.
2. **Security configuration:** chọn route nào cần authentication, địa chỉ nào chạy form auth, entry point/success/failure handler và nơi lưu SecurityContext.
3. **Identity service:** xác thực tên người dùng/mật khẩu, hash mật khẩu đúng chuẩn và cung cấp roles/authorities.

Không đưa password verification vào Thymeleaf template hoặc render controller. Không chuyển mật khẩu qua query parameter `GET /signin?password=...`. Không ghi raw password, Authorization header hoặc session cookie vào log.

## 4. Ví dụ hoàn chỉnh: Java 17+, Spring Boot 3.3.13 và Thymeleaf

Ví dụ này chủ động tạo **trang GET riêng** và **URL POST riêng**, giữ CSRF bật và cho phép đăng nhập bằng WebSession.

Các URL:

- `GET /`: công khai, trả `PUBLIC_HOME`.
- `GET /signin`: template HTML với input username/password/CSRF.
- `POST /auth/session`: Spring Security xử lý; không có controller POST.
- `GET /signin?error`: template hiển thị lỗi chung.
- `GET /dashboard`: cần đăng nhập, trả `DASHBOARD:alice` sau khi login đúng.
- `GET /public/ping`: endpoint công khai dùng làm smoke test.

### 4.1. Cấu trúc dự án

```text
webflux-custom-login/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/CustomLoginApplication.java
      resources/templates/signin.html
    test/
      java/example/CustomLoginApplicationTests.java
```

Tạo `settings.gradle`:

```groovy
rootProject.name = 'webflux-custom-login'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` cung cấp WebFlux/Netty; `spring-boot-starter-security` cung cấp Spring Security; `spring-boot-starter-thymeleaf` render view HTML. Ví dụ dùng Boot BOM quản lý phiên bản tương thích. Không thêm `spring-boot-starter-web` (MVC/Servlet) vì muốn giữ runtime reactive.

### 4.2. Lớp ứng dụng và cấu hình bảo mật

Tạo `src/main/java/example/CustomLoginApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.stereotype.Controller;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@Controller
public class CustomLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomLoginApplication.class, args);
    }

    @GetMapping("/")
    @ResponseBody
    public String index() {
        return "PUBLIC_HOME";
    }

    @GetMapping("/public/ping")
    @ResponseBody
    public String ping() {
        return "PONG";
    }

    @GetMapping("/dashboard")
    @ResponseBody
    public Mono<String> dashboard() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .map(name -> "DASHBOARD:" + name);
    }

    @GetMapping("/signin")
    public Mono<Rendering> signin(
            ServerWebExchange exchange,
            @RequestParam(name = "error", required = false) String error) {

        Mono<CsrfToken> tokenPublisher =
                exchange.getAttribute(CsrfToken.class.getName());

        if (tokenPublisher == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token is unavailable"));
        }

        return tokenPublisher.map(token -> Rendering.view("signin")
                .modelAttribute("csrf", token)
                .modelAttribute("loginError", error != null)
                .build());
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                "/", "/signin", "/public/**", "/css/**")
                        .permitAll()
                        .pathMatchers(HttpMethod.POST, "/auth/session")
                        .permitAll()
                        .anyExchange().authenticated())
                .formLogin(form -> form
                        .loginPage("/signin")
                        .requiresAuthenticationMatcher(
                                new PathPatternParserServerWebExchangeMatcher(
                                        "/auth/session", HttpMethod.POST))
                        .authenticationSuccessHandler(
                                new RedirectServerAuthenticationSuccessHandler(
                                        "/dashboard"))
                        .authenticationFailureHandler(
                                new RedirectServerAuthenticationFailureHandler(
                                        "/signin?error")))
                .httpBasic(basic -> basic.disable())
                // Giữ CSRF mặc định: POST login phải gửi token.
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }
}
```

**Giải thích từng đoạn:**

- `@EnableWebFluxSecurity` kích hoạt Spring Security cho WebFlux. Bean `SecurityWebFilterChain` dùng `ServerHttpSecurity`, không dùng `HttpSecurity`.
- `GET /signin` là controller **chỉ tạo giao diện**. Nó lấy publisher `Mono<CsrfToken>` từ `ServerWebExchange` theo tên attribute `CsrfToken.class.getName()`, rồi map thành model template `csrf`.
- Nếu vì cấu hình sai mà CSRF token không hiện diện, demo trả lỗi rõ ràng thay vì render một form âm thầm không gửi CSRF. Điều này giúp phát hiện sai security chain ngay khi học.
- `.pathMatchers("/signin").permitAll()` cho phép người chưa đăng nhập truy cập trang; nếu bỏ, browser có thể rơi vào vòng lặp redirect tới một trang cũng yêu cầu login.
- `.pathMatchers(HttpMethod.POST, "/auth/session").permitAll()` làm rõ URL xử lý form nằm trong chính sách public. Nó **không bỏ qua** `AuthenticationWebFilter` và không vô hiệu hóa CSRF. Filter xác thực chặn request ở tầng filter trước khi handler ứng dụng.
- `.loginPage("/signin")` điều khiển trang/login entry point. `requiresAuthenticationMatcher("/auth/session", POST)` chuyển riêng nơi nhận credentials.
- `authenticationSuccessHandler` đưa người dùng tới `/dashboard` khi không có saved request ưu tiên; một yêu cầu bảo vệ đã được lưu trong request cache có thể được khôi phục trước. `authenticationFailureHandler` chuyển về `/signin?error`.
- `httpBasic(...disable())` giúp trình duyệt đi theo form login. Nếu ứng dụng có REST API, hãy cân nhắc tách `SecurityWebFilterChain` và cơ chế authentication tương ứng.
- `MapReactiveUserDetailsService` chỉ là kho người dùng in-memory cho demo. `{noop}learn` **không dùng trong production**; phải lưu password hash bằng encoder phù hợp và sử dụng HTTPS.

### 4.3. Trang Thymeleaf

Tạo `src/main/resources/templates/signin.html`:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="utf-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1">
    <title>Đăng nhập</title>
</head>
<body>
<main>
    <h1>Đăng nhập ứng dụng</h1>

    <p th:if="${loginError}" role="alert">
        Không thể đăng nhập. Vui lòng kiểm tra thông tin.
    </p>

    <form action="/auth/session" method="post">
        <label for="username">Tên người dùng</label>
        <input id="username" name="username"
               type="text" autocomplete="username" required>

        <label for="password">Mật khẩu</label>
        <input id="password" name="password"
               type="password" autocomplete="current-password"
               required>

        <input type="hidden"
               th:name="${csrf.parameterName}"
               th:value="${csrf.token}">

        <button type="submit">Đăng nhập</button>
    </form>
</main>
</body>
</html>
```

Lưu ý phần `<form action="/auth/session" method="post">` sử dụng action cố định đúng yêu cầu demo chạy ở root context. Khi triển khai dưới context path hoặc reverse proxy có prefix, cập nhật URL tương ứng. Nếu dùng `th:action`, Thymeleaf có tích hợp tự chèn CSRF hidden field cho form POST; tránh cấu hình vừa tự chèn vừa thêm một trường CSRF thứ hai không cần thiết. Trong ví dụ này, ta giữ action HTML và **cấp một hidden field tường minh** lấy từ model.

**CSRF quan trọng:** Ở Spring Security WebFlux, `CsrfWebFilter` để một `Mono<CsrfToken>` trong exchange attributes. Các phiên bản Spring Security 6.x dùng cơ chế request handler bảo vệ BREACH bằng token đã xử lý cho việc đưa vào trang. Bài sử dụng `csrf.token` **từ request attribute dành cho render**, không tự lấy token lưu ở session rồi đoán cách mã hóa. Không hardcode token, không đưa token vào URL, không đặt mật khẩu vào query string.

### 4.4. Chạy ứng dụng

Yêu cầu Java 17+ và Gradle tương thích với Spring Boot plugin.

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows.

Mở browser:

1. Truy cập `http://localhost:8080/signin`. Trang riêng phải hiển thị các trường username/password, kèm hidden CSRF token đã render.
2. Nhập **`alice` / `learn`**. Form gửi **POST `/auth/session`**, Spring Security xử lý và redirect sau khi xác thực thành công.
3. Truy cập `http://localhost:8080/dashboard`. Khi browser giữ session cookie, response body là:

```text
DASHBOARD:alice
```

4. Đăng nhập lại với mật khẩu sai trong một phiên chưa xác thực: redirect về `/signin?error`, thông báo lỗi chung hiển thị; không có authentication thành công.
5. Mở cửa sổ riêng tư không dùng chung session cookie và truy cập `/dashboard`: request được redirect về trang login.

**Có thể kiểm tra endpoint GET công khai bằng curl:**

```bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/signin
```

Body của hai lệnh đầu lần lượt là `PUBLIC_HOME` và `PONG` khi HTTP 200. Lệnh thứ ba trả HTML chứa `action="/auth/session"` và hidden CSRF field; giá trị token thay đổi theo phiên/request và không thể ghi thành stdout hằng số.

**Không nên giả định lệnh sau đăng nhập được:**

```bash
curl -i -X POST http://localhost:8080/auth/session \
  -d "username=alice&password=learn"
```

Nó thường trả **403** vì thiếu CSRF token, không phải do thiếu controller POST. Muốn thử form bằng HTTP client, cần lấy HTML/CSRF và session cookie từ GET `/signin`, rồi gửi form POST kèm chính token và cookie của phiên đó. Browser làm sẵn việc này.

## 5. Mô hình CSRF của trang login riêng

Một form login cần bảo vệ chống **login CSRF**: bên tấn công có thể tìm cách khiến browser nạn nhân đăng nhập vào tài khoản do kẻ tấn công kiểm soát, làm thay đổi trạng thái phiên và gây hậu quả nghiệp vụ.

Theo tài liệu Spring Security WebFlux, CSRF **được bật mặc định** và **POST login được bảo vệ**. Form POST nên chứa token đã được cấp cho session/request hợp lệ:

```http
POST /auth/session HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: SESSION=...

username=alice&password=learn&_csrf=<token-cua-phien>
```

**Diễn giải đúng các trường:**

| Field | Vai trò |
| --- | --- |
| `username` | Tên người dùng mà form authentication converter đọc |
| `password` | Mật khẩu gốc người dùng vừa nhập, gửi qua TLS; không log |
| `_csrf` | Bằng chứng chống CSRF, được server cấp và kiểm chứng |
| `SESSION` | Cookie giúp server tìm WebSession; khác với CSRF token |

Không cần ép token thành một chuỗi tĩnh, cũng không nên lấy tên trường `_csrf` bằng cách đoán nếu ứng dụng đã tùy biến CSRF repository/handler. Template dùng `csrf.parameterName` và `csrf.token` để giữ đúng contract.

**Đừng tắt `csrf` chỉ vì thấy 403 khi POST login.** Hãy kiểm tra token có được render, session cookie có gửi lại, CSRF request handler có tương thích, method POST có đúng và form body có đúng media type không. Đối với giao diện trình duyệt dùng cookie, việc vô hiệu CSRF vì tiện thử nghiệm là một thay đổi chính sách bảo mật lớn.

Trong Spring Security 6.x, `XorServerCsrfTokenRequestAttributeHandler` mặc định che token hiển thị để giảm nguy cơ BREACH. Vì vậy chuỗi token đưa vào HTML có thể khác với giá trị lưu trữ trực tiếp. Để có token phù hợp với bộ kiểm chứng, hãy dùng attribute do `CsrfWebFilter` cung cấp cho request.

### Phân biệt GET và POST về CSRF

- `GET /signin` là thao tác đọc, dùng để hiển thị form và token. GET thường không bị CSRF bảo vệ theo nghĩa yêu cầu token để gọi.
- `POST /auth/session` thay đổi trạng thái phiên xác thực, phải gửi token.
- `POST /logout` cũng cần CSRF theo cấu hình mặc định. Đừng dùng GET logout chỉ để dễ tạo link.
- `GET /signin?error` chỉ là GET trang có tham số trạng thái; không phải nơi nhận mật khẩu.

Đừng đưa CSRF token hoặc password vào `GET` query parameters, vì URL có thể xuất hiện trong history, referrer và log proxy.

## 6. Authentication success, failure và session

### 6.1. Khi thành công

Form authentication filter đọc dữ liệu form, tạo `Authentication` chưa xác thực, gọi `ReactiveAuthenticationManager` để kiểm tra thông tin. Nếu thành công, nó đặt security context của request và có thể lưu `SecurityContext` qua `ServerSecurityContextRepository` mặc định dùng WebSession cho form login. Success handler quyết định redirect.

```text
POST /auth/session
  -> authentication thành công
  -> lưu SecurityContext vào WebSession
  -> response redirect (Location /dashboard hoặc saved request)
  -> browser giữ/cập nhật SESSION cookie
  -> GET /dashboard
  -> load SecurityContext từ WebSession
  -> ReactiveSecurityContextHolder có principal
  -> handler trả DASHBOARD:alice
```

**Saved request:** `RedirectServerAuthenticationSuccessHandler` thường ưu tiên một request cần login đã được lưu trong `ServerRequestCache`, rồi mới dùng URL fallback của constructor. Vì vậy `new RedirectServerAuthenticationSuccessHandler("/dashboard")` không phải lời hứa mọi thành công luôn đi đúng `/dashboard` khi người dùng bắt đầu từ endpoint được bảo vệ khác.

**Session ID:** repository lưu context trong `WebSession` có thể đổi session ID để chống session fixation. Khi kiểm thử bằng HTTP client, hãy đọc cookie mới từ response POST login, thay vì giả định cookie trước và sau login giống nhau.

### 6.2. Khi sai username/password

`RedirectServerAuthenticationFailureHandler("/signin?error")` sẽ đưa browser về trang đăng nhập và hiển thị lỗi chung. Không nên gửi lý do “username không tồn tại” hoặc “password sai” quá chi tiết; nên giữ thông điệp không giúp liệt kê tài khoản.

Trang `GET /signin?error` phải được render ở cùng controller với `GET /signin`; query string `error` không phải một URL controller khác. Với mảnh Java trên, `error != null` làm template bật `loginError`.

Một redirect sau khi credentials sai **không có nghĩa authentication thành công**. Để xác minh, hãy gửi request mới tới `/dashboard` ở cùng session: nếu chưa từng đăng nhập thành công, phải bị yêu cầu xác thực.

### 6.3. Khi lưu session hoặc backend lỗi

Lỗi authentication manager, session store, thiếu memory hay sai cấu hình không nhất thiết là “mật khẩu sai”. Đừng dùng `onErrorReturn(true)`, redirect giả thành công hoặc ghi dữ liệu nhạy cảm vào log. Tách HTTP user-facing response với metric/log về loại lỗi để vận hành biết lỗi thuộc storage, CSRF hay credentials.

## 7. Tùy biến tên trường và format request

Theo hợp đồng form login thông thường, request cần **`application/x-www-form-urlencoded`** với tên field **`username`** và **`password`**. Ví dụ HTML sai:

```html
<form action="/auth/session" method="post">
    <input name="email">
    <input name="secret" type="password">
    <button>Đăng nhập</button>
</form>
```

Nếu không đổi authentication converter, filter tìm `username` và `password`, sẽ không đọc đúng hai field trên. Thay đổi giao diện/tên label là việc riêng với **tên tham số gửi**. Có thể hiển thị label “Email” nhưng giữ `name="username"` nếu user lookup nhận email như username.

Nếu nghiệp vụ thực sự cần `email`/`secret`, Spring Security WebFlux có `ServerFormLoginAuthenticationConverter` hỗ trợ tùy biến parameter names và `FormLoginSpec.authenticationConverter(...)`. Mảnh cấu hình **minh họa** (không phải ứng dụng độc lập):

```java
ServerFormLoginAuthenticationConverter converter =
        new ServerFormLoginAuthenticationConverter();

converter.setUsernameParameter("email");
converter.setPasswordParameter("secret");

http.formLogin(form -> form
        .loginPage("/signin")
        .requiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/auth/session", HttpMethod.POST))
        .authenticationConverter(converter));
```

Cần import `org.springframework.security.web.server.authentication.ServerFormLoginAuthenticationConverter`. Kiểm tra JavaDoc cho đúng phiên bản vì lớp cũ cùng tên ở package `org.springframework.security.web.server` đã được đánh dấu deprecated. Khi đổi converter, form HTML, API kiểm thử và dịch vụ lookup user phải thống nhất. Không đánh đồng “đổi path POST” với “đổi tên field”: chúng là hai cấu hình độc lập.

**Nếu client gửi JSON** với `Content-Type: application/json`, form converter mặc định sẽ không tự xem nó như username/password form. Muốn JSON login cần thiết kế authentication converter/endpoint phù hợp, xử lý CSRF nếu browser gửi cookie và cấu hình cơ chế session/token tương ứng; không thể chỉ đổi `method="post"` hoặc `action` trên HTML để có JSON authentication.

## 8. Tích hợp với nhiều SecurityWebFilterChain

Trong Spring Security reactive, `WebFilterChainProxy` chọn **`SecurityWebFilterChain` đầu tiên khớp request** theo thứ tự. Mỗi chain có thể có matcher, authentication và authorization khác nhau.

Giả sử ứng dụng có:

```text
Order 1: /api/**       -> Bearer token, không dùng form
Order 2: /admin/**     -> cơ chế quản trị riêng
Order 3: fallback      -> form login UI
```

Khi người dùng gửi **GET /signin** hoặc **POST /auth/session**, cả hai request phải đến **chain fallback có cấu hình form login**. Nếu chain UI chỉ match `/app/**` thì GET trang và POST processing ở ngoài phạm vi; filter form login có thể không chạy dù HTML vẫn được controller trả về ở nơi khác.

### 8.1. Cấu hình sai thường gặp

```java
// Mảnh cấu hình SAI nếu không có chain bao phủ /signin và /auth/session.
http
    .securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/app/**"))
    .formLogin(form -> form
        .loginPage("/signin")
        .requiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/auth/session", HttpMethod.POST)));
```

Do matcher của **chain** chỉ khớp `/app/**`, request POST `/auth/session` không bao giờ chạy tới filter đăng nhập trong chain này. `requiresAuthenticationMatcher` chỉ có tác dụng **bên trong chain đã được chọn**, không giúp filter được gọi nếu chain bị loại ở tầng proxy.

Cách đúng thường đơn giản hơn: đặt chain form login cuối cùng **bao phủ phần còn lại**, hoặc mở rộng `securityMatcher` của chain UI để chứa đồng thời `/app/**`, `/signin`, `/auth/session` và các URL lỗi/logout.

### 8.2. Phân biệt ba matcher

| Cấu hình | Nó quyết định điều gì? |
| --- | --- |
| `http.securityMatcher(...)` | Chain này có áp dụng cho request không? |
| `form.requiresAuthenticationMatcher(...)` | Trong chain đã chọn, request nào kích hoạt authentication filter? |
| `authorizeExchange(...pathMatchers(...))` | Trong chain đã chọn, request nào được phép/từ chối? |

Chúng **không thay thế nhau**. Một request POST có thể khớp security chain nhưng không khớp matcher của form filter, và cuối cùng đến authorization/handler khác. Một request có thể match form filter nhưng bị CSRF chặn trước khi mật khẩu được kiểm tra.

### 8.3. Phân tách bảo mật UI với API

Form login/cookie session phù hợp với ứng dụng browser. API dùng Bearer token thường cần 401 JSON/`WWW-Authenticate` thay vì redirect HTML. Nếu API và UI dùng chung chain không phân biệt, người gọi API có thể gặp `302 /signin` bất ngờ; cân nhắc chain API riêng.

Với ứng dụng có nhiều reverse proxy, đừng dùng URL bên ngoài chưa được map vào request path WebFlux làm matcher: xác định URL mà ServerWebExchange thực sự nhìn thấy và cấu hình forwarded headers/context path đúng. Đặc biệt kiểm tra `/signin` và `/auth/session` sau khi triển khai dưới prefix.

## 9. Kiểm thử cấu hình bằng WebTestClient

Kiểm thử nên chứng minh không chỉ “HTML hiển thị”, mà cả **matcher POST**, **CSRF**, **authentication success/failure**, **lưu session**, và **truy cập lại request mới**.

### 9.1. Test Java tối thiểu

Tạo `src/test/java/example/CustomLoginApplicationTests.java`:

```java
package example;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class CustomLoginApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicPingIsAccessible() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void customPageRendersConfiguredPostAction() {
        client.get().uri("/signin")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> assertTrue(
                        html.contains("action=\"/auth/session\"")));
    }

    @Test
    void dashboardRequiresAuthentication() {
        client.get().uri("/dashboard")
                .exchange()
                .expectStatus().is3xxRedirection();
    }

    @Test
    void loginPostWithoutCsrfIsRejected() {
        client.post().uri("/auth/session")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Chạy:

```bash
gradle test
```

Các test trên cho thấy trang công khai, form action, bảo vệ `/dashboard` và CSRF của POST. Riêng việc **đăng nhập thành công rồi còn đăng nhập ở request sau** cần test tích hợp có **cookie thật và CSRF thật**, hoặc kiểm tra thủ công trong browser.

### 9.2. Bài test liên request có ý nghĩa hơn mockUser

Để kiểm chứng đúng cấu hình, chạy theo thứ tự:

1. Gửi **GET /signin**, lưu cookie `SESSION` và lấy token từ hidden field có tên `_csrf` trong HTML.
2. Gửi **POST /auth/session** với `Content-Type: application/x-www-form-urlencoded`, payload `username=alice&password=learn&_csrf=TOKEN` và **cookie vừa lấy**.
3. Quan sát response **3xx** khi xác thực thành công, lấy **cookie session mới** nếu server gửi lại sau khi đổi session ID.
4. Gửi **GET /dashboard** bằng cookie hiện hành, xác nhận **200 + `DASHBOARD:alice`**.
5. Gửi GET tương tự **không có cookie**, xác nhận bị chuyển về login.
6. Thử POST với password sai nhưng CSRF đúng, xác nhận redirect về **`/signin?error`** và không tạo context authenticated.
7. Thử POST đúng credentials nhưng **không có CSRF**, phải bị từ chối và không tới success handler.
8. Gửi GET tới `/auth/session` hoặc POST tới đường khác, bảo đảm **không vô tình xác thực** chỉ vì trùng path gần giống.

**Không dùng `mockUser` làm bằng chứng persistence**, vì mock security context có thể bỏ qua chính login flow và session repository đang cần kiểm thử. `mockUser` hữu ích khi test authorization riêng, nhưng ở đây phải chứng minh credentials, POST matcher, CSRF và cookie thực.

### 9.3. Ma trận kết quả

| Kịch bản | HTTP kỳ vọng trong demo | Ý nghĩa |
| --- | --- | --- |
| `GET /signin` chưa login | 200 | Trang riêng hiện đúng |
| `GET /signin?error` | 200 | Thông báo sai thông tin hiển thị |
| `GET /dashboard` không session | 302 đến `/signin` | Entry point bảo vệ trang |
| `POST /auth/session` không CSRF | 403 | `CsrfWebFilter` chặn |
| `POST /auth/session` đúng CSRF, sai password | 302 đến `/signin?error` | Failure handler |
| `POST /auth/session` đúng CSRF và password | 3xx thành công | Success handler, context được lưu |
| `GET /dashboard` sau login và có cookie | 200, `DASHBOARD:alice` | Session được nạp |
| `GET /dashboard` không cookie | 302 đến `/signin` | Không kế thừa context |
| `POST /signin` khi matcher chỉ nhận `/auth/session` | Không đi qua login filter dự kiến | Chứng minh POST URL được tách |
| `GET /auth/session` | Không kích hoạt form authentication | Matcher yêu cầu POST |

Trong một cấu hình khác, mã HTTP từ entry point/exception handler có thể khác. Đừng coi status 403 do thiếu CSRF là cùng loại lỗi với 403 do thiếu quyền.

## 10. Chẩn đoán lỗi thường gặp

### 10.1. Vòng lặp redirect đến trang login

**Triệu chứng:** Browser được đưa đến `/signin` rồi tiếp tục redirect đến `/signin` liên tục.

**Nguyên nhân thường gặp:** `GET /signin` chưa được `permitAll()`, hoặc trang ở ngoài chain cấu hình entry point. Kiểm tra authorization và matcher của security chain, không chỉ route controller.

### 10.2. Trang login hiện nhưng submit không có tác dụng

**Triệu chứng:** Bấm submit nhận 404, redirect trở lại login, hoặc handler khác xử lý.

**Kiểm tra:**

- `action="/auth/session"` có đúng thực tế URL server nhìn thấy không?
- `method="post"` có đúng? Có bị JavaScript đổi sang GET không?
- `requiresAuthenticationMatcher("/auth/session", POST)` có được gắn vào **chain thực sự được chọn**?
- `Content-Type` có là `application/x-www-form-urlencoded` không?
- Input có đúng tên `username` và `password` không?
- Có controller POST trùng URL hoặc security chain khác nuốt request không?

### 10.3. POST luôn 403 dù mật khẩu đúng

**Nguyên nhân thường gặp:** CSRF token thiếu, sai, dùng token của session khác, hoặc browser không gửi cookie session. Không kết luận authentication manager sai khi POST chưa vượt qua `CsrfWebFilter`.

**Kiểm tra:** HTML render có hidden token; token là của request hiện hành; form gửi đúng tên `csrf.parameterName`, giữ cookie; reverse proxy không thay URL hay cookie scope.

### 10.4. POST redirect thành công nhưng request sau lại cần login

**Nguyên nhân:** Session cookie không được giữ/gửi, WebSession persistence lỗi, SecurityContext repository save/load không nhất quán, hoặc session bị hủy/đổi ID.

**Kiểm tra:** Browser devtools Network/Storage, cookie `SESSION`, response redirect, `ServerSecurityContextRepository` cho form login và context load; HTTPS/SameSite/Cookie Path/Domain. Đừng chỉ kiểm tra response của POST.

### 10.5. Đã gọi loginPage nhưng GET trả 404

Khi đặt `loginPage("/signin")`, Spring Security **không tự tạo UI của bạn**. Cần controller/view hoặc static HTML được router phục vụ. Nếu dùng Thymeleaf, kiểm tra file `src/main/resources/templates/signin.html`, dependency Thymeleaf và controller trả view name chính xác.

### 10.6. Trang báo lỗi không hiển thị

Javadoc của `loginPage` mặc định định hướng về `/signin?error`. Cần template đọc tham số để hiển thị nội dung chung, hoặc tự đặt failure handler đúng URL. Nếu redirect tới `/login?error` nhưng controller chỉ có `/signin`, thông báo lỗi sẽ sai trang.

### 10.7. Nhầm loginProcessingUrl của Servlet

Không gọi `loginProcessingUrl` trên `ServerHttpSecurity.FormLoginSpec`. Dùng `requiresAuthenticationMatcher(...)` với `PathPatternParserServerWebExchangeMatcher` (HTTP POST) trong WebFlux. Không đổi sang `HttpSecurity` chỉ để dùng tên phương thức quen thuộc.

### 10.8. Tự kiểm tra mật khẩu trong controller

Không tự viết `@PostMapping("/auth/session")` rồi so sánh password thủ công, trả cookie tuỳ ý hoặc sử dụng `NoOpPasswordEncoder`. Spring Security đã có converter, manager, password encoder, session, CSRF và handlers. Nếu có yêu cầu đặc thù, mở rộng ở đúng abstraction.

### 10.9. Trang login bị ảnh hưởng bởi chain API

Nếu chain API hoặc catch-all có `@Order` cao hơn và matcher bao phủ `/signin` hay `/auth/session`, request có thể vào Basic/Bearer thay vì form login. Kiểm tra thứ tự security chains và cả hai URL; **không thể nhận định chỉ từ số lượng bean**.

### 10.10. Vấn đề CSS, cookie và triển khai dưới prefix

Trang custom có thể tải HTML nhưng CSS `/css/**` bị chặn, hoặc form action dùng path không đúng khi chạy dưới reverse proxy. Cho phép truy cập **chỉ các asset login cần thiết**, chuẩn hóa context path/forwarded headers và test đường dẫn thực tế. Không mở `anyExchange().permitAll()` để “sửa” CSS 403.

### 10.11. Hiện sai ngôn ngữ/mã hóa HTML

Đặt `<meta charset="utf-8">`, kiểm tra template UTF-8 và response Content-Type. Thông báo lỗi phải được Thymeleaf escape khi chứa dữ liệu động; tránh render raw HTML từ query string `error`.

## 11. Bảo vệ form đăng nhập khi đưa vào sản phẩm

Bài tập trung vào **đường dẫn và xử lý form**, nhưng thiết kế đăng nhập còn cần nhiều yêu cầu vận hành:

- **HTTPS** cho mọi form action, redirect và session cookie. Không truyền password qua HTTP công khai.
- **Password hashing** thích hợp (BCrypt/Argon2/PBKDF2/scrypt) với work factor được đo trên hạ tầng thật; `{noop}` chỉ là demo.
- **CSRF** bật cho form login dùng cookie/session; đừng tắt chỉ vì gặp 403 trong test.
- **Rate limiting**, chống credential stuffing và enumeration, audit login success/failure nhưng không log mật khẩu hoặc session ID.
- **Session fixation protection**, session timeout, cookie `Secure`/`HttpOnly`/`SameSite` phù hợp và xử lý logout đầy đủ.
- **Chống open redirect:** không tin mọi tham số `next`/`redirect` người dùng gửi; nếu tùy biến success handler, chỉ cho redirect tới URL được phép hoặc path nội bộ đã validate.
- **CORS/cookie policy:** khác origin và SameSite có thể ảnh hưởng login flow; không mở CORS wildcard với credentials hoặc tắt chính sách cookie không kiểm soát.
- **Accessibility:** label liên kết với input, thông báo lỗi dùng `role="alert"`, biểu mẫu dùng autocomplete phù hợp và hỗ trợ bàn phím.
- **Không lộ credentials:** không đưa username/password hay token vào URL, analytics, crash report hoặc debugging output.
- **Không dựa vào URL bí mật:** đổi `/login` thành `/secret-login` không thay thế xác thực mạnh hoặc chống tấn công.

Những phần này không tự được giải quyết bằng `.loginPage(...)` hoặc đổi địa chỉ POST. Đường đi đúng là điều kiện cần cho form login hoạt động; bảo vệ hoạt động đăng nhập còn cần chính sách và vận hành an toàn.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Với WebFlux chỉ cấu hình `formLogin(form -> form.loginPage("/signin"))`, form mặc định cần POST tới đâu?  
**Đáp:** `POST /signin`. `loginPage` của WebFlux đặt trang login, URL lỗi và nơi xác thực mặc định cùng path; muốn POST nơi khác phải ghi đè matcher.

**Câu 2.** Muốn `GET /signin` và `POST /auth/session`, sử dụng API nào?  
**Đáp:** `loginPage("/signin")` kết hợp `requiresAuthenticationMatcher(new PathPatternParserServerWebExchangeMatcher("/auth/session", HttpMethod.POST))`.

**Câu 3.** Có cần `@PostMapping("/auth/session")` tự viết trong controller không?  
**Đáp:** Không, khi Spring Security form authentication filter được cấu hình và khớp request. Controller dùng để render GET page, còn filter xử lý POST credentials.

**Câu 4.** Tại sao `GET /signin` phải được phép truy cập khi chưa login?  
**Đáp:** Nếu trang login cũng bắt buộc đã đăng nhập, trình duyệt có thể bị redirect vòng lặp khi truy cập endpoint bảo vệ.

**Câu 5.** Form có `username` và `password` đúng, nhưng không có CSRF token; có đăng nhập được không?  
**Đáp:** Với CSRF mặc định bật trong WebFlux, POST thường bị 403 trước khi kiểm tra mật khẩu.

**Câu 6.** `GET /signin?error` có cần một controller riêng không?  
**Đáp:** Không bắt buộc. Một GET handler `/signin` đọc query parameter `error` và bật thông báo chung trong template là đủ.

**Câu 7.** Vì sao đổi `action="/auth/session"` mà chỉ sửa form HTML chưa đủ?  
**Đáp:** `AuthenticationWebFilter` phải có `requiresAuthenticationMatcher` khớp đúng POST URL; nếu không, request sẽ không kích hoạt xác thực như dự kiến.

**Câu 8.** Khi có nhiều `SecurityWebFilterChain`, matcher của form filter có kéo request vào chain UI không?  
**Đáp:** Không. Proxy chọn security chain trước, sau đó filter nội bộ mới xét matcher. Cả GET page và POST processing phải thuộc chain có form login.

**Câu 9.** Redirect thành công đã chứng minh session persistence chưa?  
**Đáp:** Chưa. Phải gửi request mới kèm cookie hiện hành rồi xác nhận principal được load và endpoint bảo vệ cho phép.

**Câu 10.** `loginProcessingUrl(...)` có phải phương thức trên `ServerHttpSecurity.FormLoginSpec` reactive không?  
**Đáp:** Không. Đó là DSL phía Servlet. Reactive dùng `requiresAuthenticationMatcher(...)` để đổi điều kiện xử lý POST.

**Ghi nhớ:** Trong WebFlux, **`loginPage` quyết định trang hiển thị và mặc định nơi POST**, còn **`requiresAuthenticationMatcher` quyết định chính xác request được form authentication filter xử lý**. Để tách **GET /signin** và **POST /auth/session** an toàn, hãy đảm bảo route/chain đúng, input names đúng, CSRF đầy đủ, success/failure redirect hợp lý và kiểm thử session bằng một request mới.

## Tài liệu tham khảo

- [Spring Security 6.5 — ServerHttpSecurity.FormLoginSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html): `loginPage`, `requiresAuthenticationMatcher`, `authenticationFailureHandler` và `authenticationSuccessHandler`.
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): cấu hình WebFlux form login, security chain và authorization.
- [Spring Security — CSRF Protection in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `Mono<CsrfToken>` trong ServerWebExchange, token hiển thị và login/logout CSRF.
- [Spring Security — PathPatternParserServerWebExchangeMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/PathPatternParserServerWebExchangeMatcher.html): matcher path + HTTP method.
- [Spring Security — RedirectServerAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html): redirect sau login và saved request.
- [Spring Security — RedirectServerAuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationFailureHandler.html): redirect khi credentials sai.
- [Spring Security — ServerFormLoginAuthenticationConverter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerFormLoginAuthenticationConverter.html): chuyển form fields thành Authentication.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain` và thiết lập WebFlux.
