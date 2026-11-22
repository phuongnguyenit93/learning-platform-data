# Thực hành tổng hợp: Xây dựng ứng dụng WebFlux dùng form login, phiên, CSRF và đăng xuất

## 1. Mục tiêu, phạm vi và thành phẩm

Bài thực hành xây dựng một ứng dụng **Spring Boot + Spring WebFlux + Spring Security** cho người dùng đăng nhập bằng **biểu mẫu HTML**, duy trì trạng thái xác thực qua **WebSession**, thực hiện một thao tác **POST được bảo vệ CSRF** và **đăng xuất bằng POST**. Trọng tâm là hiểu luồng bảo mật và kiểm chứng hành vi thực tế, không chỉ bật vài tùy chọn cấu hình.

Ứng dụng sau khi hoàn thành có các chức năng:

1. Khách truy cập được xem trang chủ `GET /` và trang đăng nhập tự xây dựng `GET /login`.
2. Người dùng nhập `username`, `password` và CSRF token trong form `POST /login`. **Spring Security xử lý POST /login**, không cần tự viết controller kiểm tra mật khẩu.
3. Khi đăng nhập thành công, trạng thái `SecurityContext` được lưu theo `WebSession`. Các request sau dùng cookie phiên để tiếp tục truy cập `GET /dashboard`.
4. Người dùng đổi giao diện demo qua `POST /preferences`. Request không có CSRF token đúng phải bị chặn, không thay đổi dữ liệu.
5. Người dùng gửi form `POST /logout` kèm CSRF token. Đăng xuất xóa ngữ cảnh bảo mật, đồng thời ứng dụng được cấu hình **hủy toàn bộ WebSession**. Sau đó truy cập trang bảo vệ phải đăng nhập lại.

**Công nghệ trong ví dụ:** Java 17+ (minh họa với JDK 21), Spring Boot 3.3.x, Spring Security 6.x, Gradle, WebFlux và Reactor. Code dùng một controller trả HTML trực tiếp để nhìn rõ cơ chế CSRF; ứng dụng lớn có thể dùng Thymeleaf reactive thay thế. Không áp dụng API của Servlet như `HttpSecurity`, `SecurityFilterChain`, `HttpSession`, `HttpServletRequest` hoặc `SecurityContextHolder` kiểu ThreadLocal như trong các ví dụ Spring MVC.

## 2. Luồng hoạt động và các khái niệm

```text
Trình duyệt chưa đăng nhập
    |
    | GET /dashboard
    v
SecurityWebFilterChain -> chưa có Authentication
    |
    | Redirect tới /login
    v
GET /login -> server sinh/cấp CsrfToken; WebSession liên kết token
    |
    | Form POST /login:
    | username + password + _csrf
    v
CsrfWebFilter kiểm tra token
    |
    v
AuthenticationWebFilter xác thực credential
    |
    +-- Sai --> quay lại trang login với thông báo lỗi
    |
    +-- Đúng --> SecurityContext lưu trong WebSession
                    |
                    | Cookie phiên theo các request tiếp theo
                    v
                GET /dashboard (đã xác thực)
                    |
                    +--> POST /preferences + CSRF: đổi state demo
                    |
                    +--> POST /logout + CSRF:
                             xóa SecurityContext + hủy WebSession
                             |
                             v
                         Quay lại login; quyền truy cập cũ mất
```

**Phân biệt các thành phần:**

| Thành phần | Vai trò trong ví dụ |
| --- | --- |
| `SecurityWebFilterChain` / `ServerHttpSecurity` | Quyết định route nào public, route nào cần role và kích hoạt form login/CSRF/logout |
| `MapReactiveUserDetailsService` | Nguồn tài khoản demo; thay bằng repository/dịch vụ người dùng trong sản phẩm thực |
| `PasswordEncoder` (`BCryptPasswordEncoder`) | So sánh mật khẩu với hash khi xác thực; không dùng `{noop}` trong sản phẩm |
| `WebSession` | Phiên server-side lưu `SecurityContext`, CSRF token và lựa chọn giao diện demo |
| Cookie phiên | Chứa định danh phiên để browser tìm lại dữ liệu trên server; bản thân cookie không phải token CSRF |
| `WebSessionServerCsrfTokenRepository` | Cơ chế mặc định lưu expected CSRF token trong `WebSession` |
| `CsrfWebFilter` | Xác minh token trên request thay đổi trạng thái; thường bắt buộc với POST |
| `LogoutWebFilter` | Tiếp nhận POST logout; chuyển cho `ServerLogoutHandler` |
| `WebSessionServerLogoutHandler` | Hủy toàn bộ `WebSession` khi được thêm vào cấu hình logout |

Tại sao CSRF quan trọng dù cookie đã có `HttpOnly`? Browser **tự động gửi cookie** theo chính sách cookie khi truy cập cùng site hoặc một số cross-site navigation. Một trang độc hại có thể thử kích hoạt thao tác POST bằng phiên người dùng; yêu cầu một CSRF token mà trang khác không thể lấy trực tiếp sẽ chặn kiểu tấn công đó. `SameSite` giúp giảm rủi ro nhưng không thay thế đầy đủ việc bảo vệ các form quan trọng.

## 3. Khởi tạo dự án Gradle

Có thể tạo dự án Spring Boot Gradle bằng Spring Initializr với các dependency **Spring Reactive Web** và **Spring Security**. Nếu tạo dự án rỗng thủ công, cấu trúc cần đạt:

```text
webflux-form-session-demo/
├── settings.gradle
├── build.gradle
├── gradlew                 # nếu đã tạo Gradle Wrapper
├── gradlew.bat             # nếu đã tạo Gradle Wrapper
└── src/main/java/demo/
    └── WebfluxFormSessionApplication.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'webflux-form-session-demo'
```

**`build.gradle` (Gradle Groovy DSL):**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu dự án hiện có đã dùng Spring Boot 3.3.x, giữ phiên bản plugin/Gradle do dự án quản lý và bổ sung đúng starter cần thiết; không chèn plugin/dependency phiên bản riêng vào build nhiều module khi đã có dependency management. Mẫu trên dùng JDK 21; API chính phù hợp Java 17+ với toolchain được điều chỉnh tương ứng.

**Mật khẩu demo:** ứng dụng yêu cầu biến môi trường `DEMO_PASSWORD` ngay khi khởi động, mã hóa bằng BCrypt rồi mới tạo tài khoản `learner`. Không hard-code mật khẩu thực hoặc bản hash dùng chung nhiều hệ thống vào kho mã nguồn. Chỉ dùng tài khoản mẫu cho học tập trên localhost.

## 4. Ứng dụng Java hoàn chỉnh

Đặt toàn bộ code dưới đây vào **`src/main/java/demo/WebfluxFormSessionApplication.java`**. Đây là một tệp Java đầy đủ có `main`, cấu hình bảo mật, user demo và controller HTML. Không cần thêm template hoặc JavaScript.

```java
package demo;

import java.security.Principal;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.util.HtmlUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class WebfluxFormSessionApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebfluxFormSessionApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        String password = System.getenv("DEMO_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalStateException(
                    "Set DEMO_PASSWORD before running the local demo");
        }
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode(password))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        var logoutHandlers = new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler());

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/login").permitAll()
                        .pathMatchers(HttpMethod.GET, "/dashboard")
                        .hasRole("USER")
                        .pathMatchers(HttpMethod.POST, "/preferences")
                        .hasRole("USER")
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.loginPage("/login"))
                .csrf(Customizer.withDefaults())
                .logout(logout -> logout.logoutHandler(logoutHandlers))
                .build();
    }

    @RestController
    static class Pages {

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> home() {
            return Mono.just("""
                    <!doctype html>
                    <html lang="vi"><head><meta charset="UTF-8">
                    <title>Trang chủ</title></head><body>
                      <h1>WebFlux Security Demo</h1>
                      <p><a href="/dashboard">Mở dashboard</a></p>
                      <p><a href="/login">Đăng nhập</a></p>
                    </body></html>
                    """);
        }

        @GetMapping(value = "/login",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> loginPage(ServerWebExchange exchange) {
            return csrf(exchange).map(token -> """
                    <!doctype html>
                    <html lang="vi"><head><meta charset="UTF-8">
                    <title>Đăng nhập</title></head><body>
                      <h1>Đăng nhập</h1>
                      <form method="post" action="/login">
                        <label>Tên đăng nhập
                          <input name="username" autocomplete="username"
                                 required>
                        </label>
                        <label>Mật khẩu
                          <input type="password" name="password"
                                 autocomplete="current-password" required>
                        </label>
                        %s
                        <button type="submit">Đăng nhập</button>
                      </form>
                      <p><a href="/">Về trang chủ</a></p>
                    </body></html>
                    """.formatted(hiddenCsrf(token)));
        }

        @GetMapping(value = "/dashboard",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> dashboard(ServerWebExchange exchange) {
            Mono<Principal> currentUser = exchange.getPrincipal();
            return Mono.zip(currentUser, csrf(exchange),
                    exchange.getSession()).map(values -> {
                String user = HtmlUtils.htmlEscape(
                        values.getT1().getName());
                CsrfToken token = values.getT2();
                WebSession session = values.getT3();
                String preference = session.getAttributeOrDefault(
                        "theme", "light");
                String hidden = hiddenCsrf(token);

                return """
                        <!doctype html>
                        <html lang="vi"><head><meta charset="UTF-8">
                        <title>Dashboard</title></head><body>
                          <h1>Dashboard</h1>
                          <p>Đã đăng nhập: %s</p>
                          <p>Giao diện trong phiên: %s</p>
                          <form method="post" action="/preferences">
                            <label>Chọn giao diện
                              <select name="theme">
                                <option value="light">light</option>
                                <option value="dark">dark</option>
                              </select>
                            </label>
                            %s
                            <button type="submit">Lưu</button>
                          </form>
                          <form method="post" action="/logout">
                            %s
                            <button type="submit">Đăng xuất</button>
                          </form>
                        </body></html>
                        """.formatted(user,
                        HtmlUtils.htmlEscape(preference),
                        hidden, hidden);
            });
        }

        @PostMapping(value = "/preferences",
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> savePreference(ServerWebExchange exchange) {
            return exchange.getFormData().flatMap(form -> {
                String theme = form.getFirst("theme");
                if (theme == null || !Set.of("light", "dark").contains(theme)) {
                    return Mono.error(new ResponseStatusException(
                            HttpStatus.BAD_REQUEST, "Invalid theme"));
                }
                return exchange.getSession().map(session -> {
                    session.getAttributes().put("theme", theme);
                    return "Saved theme: " + theme;
                });
            });
        }

        private static Mono<CsrfToken> csrf(
                ServerWebExchange exchange) {
            Mono<CsrfToken> token = exchange.getAttribute(
                    CsrfToken.class.getName());
            if (token == null) {
                return Mono.error(new IllegalStateException(
                        "CSRF request attribute unavailable"));
            }
            return token;
        }

        private static String hiddenCsrf(CsrfToken token) {
            return "<input type=\"hidden\" name=\""
                    + HtmlUtils.htmlEscape(token.getParameterName())
                    + "\" value=\""
                    + HtmlUtils.htmlEscape(token.getToken()) + "\">";
        }
    }
}
```

**Giải thích các quyết định quan trọng:**

- `formLogin(form -> form.loginPage("/login"))` dùng trang HTML tự viết. POST đến `/login` vẫn được **filter Spring Security** xử lý, sử dụng `username`/`password` từ form. Không tạo `@PostMapping("/login")` với logic tự xác thực.
- `/login` và `/` là public; `GET /dashboard` và `POST /preferences` yêu cầu `ROLE_USER`; các route chưa định nghĩa bị `denyAll()`. Dù `/login` được `permitAll`, CSRF vẫn kiểm tra POST trước khi cho xử lý.
- `httpBasic(basic -> basic.disable())` giữ bài tập chỉ dùng form login, tránh việc browser/client xác thực bằng Basic và bỏ qua quan sát session.
- `csrf(Customizer.withDefaults())` bảo vệ request ghi; mặc định Spring Security WebFlux đã bật CSRF, nhưng khai báo tường minh giúp người học hiểu ranh giới cấu hình.
- `CsrfToken.class.getName()` là tên attribute mà `CsrfWebFilter` đặt `Mono<CsrfToken>` lên `ServerWebExchange`. `csrf(exchange)` trả `Mono`, còn việc render HTML **subscribe** gián tiếp khi Spring WebFlux xử lý response. Không `.block()` trên event loop.
- `hiddenCsrf(token)` xuất `<input type="hidden" name="_csrf" value="...">` theo tên/giá trị thật do framework cung cấp; tên field mặc định là `_csrf`. Không tự tạo random string để giả làm CSRF token.
- `HtmlUtils.htmlEscape` bảo vệ dữ liệu được nhúng vào HTML, kể cả username và giá trị input attribute. Không đặt token vào URL/query string hoặc log.
- `savePreference` đọc body `application/x-www-form-urlencoded` qua `exchange.getFormData()`. Trong **WebFlux**, không suy diễn rằng `@RequestParam` luôn đọc form body theo cùng cách của Spring MVC. Chỉ chấp nhận `light`/`dark`. Giá trị được lưu vào `WebSession` hiện hành; đây là minh họa **state trong phiên**, không phải lưu sở thích lâu dài vào database.
- `logoutHandlers` kết hợp `SecurityContextServerLogoutHandler` và `WebSessionServerLogoutHandler`. Logout reactive mặc định có cơ chế xóa ngữ cảnh/CSRF và redirect, nhưng **không nên suy đoán nó tự hủy toàn bộ WebSession**: ở đây ta **chủ động thêm handler hủy phiên**. Một số trạng thái lưu trong phiên như `theme` vì vậy cũng mất sau logout.
- `@RestController` trả HTML body trực tiếp để ví dụ chỉ cần một file Java. Trong sản phẩm có giao diện lớn, Thymeleaf với form `th:action` có hỗ trợ chèn CSRF token tự động khi được cấu hình thích hợp; controller không cần nối chuỗi HTML thủ công.

**Điểm cần phân biệt:** đối với phần mềm thật, biến `DEMO_PASSWORD` chỉ là cách cấp một mật khẩu demo vào tiến trình. Tài khoản cần nằm ở nguồn danh tính phù hợp; hash mật khẩu phải được quản lý và lưu trữ theo chính sách, cùng với giới hạn thử đăng nhập và MFA nếu cần.

## 5. Chạy ứng dụng

Nếu tạo dự án Spring Initializr, sử dụng Gradle Wrapper đi kèm. Nếu chỉ có các file Gradle thủ công, hãy cài Gradle tương thích hoặc tạo Wrapper bằng lệnh `gradle wrapper` trước.

Trên Linux/macOS (Bash):

```bash
export DEMO_PASSWORD='OnlyForLocalPractice!'
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
$env:DEMO_PASSWORD = 'OnlyForLocalPractice!'
.\gradlew.bat bootRun
```

Nếu dùng Gradle cài sẵn thay vì Wrapper, lệnh chạy là `gradle bootRun`. Mật khẩu trên chỉ để thử tại localhost, không sao chép sang staging/production. Khi khởi động thành công, mở `http://localhost:8080/` trong browser.

### 5.1 Kịch bản đăng nhập thành công

1. Mở `/dashboard` ở cửa sổ riêng tư chưa có cookie phiên. Security chain phát hiện chưa xác thực và chuyển tới login (thường HTTP 302 tới `/login`).
2. Trang `GET /login` xuất form có `username`, `password` và hidden CSRF. Trong DevTools → Elements/Network, kiểm tra hidden field tồn tại nhưng **không chép giá trị token ra log hoặc tài liệu**.
3. Nhập username `learner` và mật khẩu bằng `DEMO_PASSWORD` đã đặt ở môi trường chạy. Form gửi POST /login, không cần controller login POST.
4. Nếu xác thực thành công, Spring Security chuyển về request đã lưu hoặc đích mặc định tùy luồng; điều hướng tới `/dashboard` để quan sát username đã đăng nhập.
5. Refresh `/dashboard`: không phải nhập lại mật khẩu vì `SecurityContext` đã được khôi phục qua `WebSession` với cookie của browser.

**Kết quả mong đợi:** form login hoạt động, browser có cookie phiên (thường mang tên `SESSION` với WebFlux mặc định), `/dashboard` trả HTML chứa `Đã đăng nhập: learner`, và refresh vẫn duy trì trạng thái. Giá trị cookie/session ID thực tế được sinh động, **không có stdout hay ID cố định** để chép vào bài.

### 5.2 Thử thao tác có CSRF

Sau khi đăng nhập, ở dashboard chọn `dark` rồi bấm **Lưu**. Browser gửi:

```http
POST /preferences
Content-Type: application/x-www-form-urlencoded
Cookie: SESSION=(định danh phiên do server cấp)

theme=dark&_csrf=(token tương ứng phiên)
```

Đây là **mẫu cấu trúc HTTP**, không phải bản request mang token có thể chạy nguyên văn. Response body trong ví dụ khi hợp lệ:

```text
Saved theme: dark
```

Sau đó mở lại `/dashboard`, dòng giao diện trong phiên hiển thị `dark`. Nếu xóa/đổi hidden `_csrf` trong form hoặc gửi POST trực tiếp không có token, `CsrfWebFilter` phải chặn thao tác (thường `403 Forbidden`), và giá trị trong phiên **không thay đổi**.

Để kiểm chứng nhanh endpoint không chấp nhận POST ẩn danh thiếu token:

```bash
curl -i -X POST http://localhost:8080/preferences \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'theme=dark'
```

Lệnh không gửi cookie và CSRF token, nên không được phép sửa phiên. Mã 403 là kết quả thường gặp khi CSRF filter từ chối, nhưng thứ tự filter/handler và tùy chỉnh của ứng dụng có thể làm status khác; bất biến cần xác minh là **không có cập nhật**. Khi kiểm thử POST thiếu CSRF **trong phiên đã đăng nhập**, dùng DevTools sửa request hoặc công cụ HTTP giữ nguyên cookie, chỉ bỏ token.

### 5.3 Đăng xuất và kiểm chứng hết phiên

Trên dashboard, bấm **Đăng xuất**. Browser gửi **POST /logout** có CSRF. Spring Security xử lý bằng logout filter và hai handler đã cấu hình. Sau redirect, thử mở lại `/dashboard`: trang bảo vệ phải yêu cầu đăng nhập lại; sở thích `theme` của phiên cũ không được coi là còn hiệu lực.

Kiểm tra thêm:

- Truy cập `GET /logout` **không được coi là cùng hành vi như POST logout**. Ở WebFlux, logout thực hiện qua POST để được CSRF bảo vệ; có thể tồn tại trang xác nhận GET tùy cấu hình.
- Một POST logout **thiếu hoặc sai CSRF** phải bị chặn; không được làm phiên biến mất như logout hợp lệ.
- Cookie phiên cũ gửi sau khi logout không được truy cập `/dashboard` với quyền cũ.
- Khi đăng nhập lại bằng một phiên hợp lệ mới, xem trạng thái demo đã trở về `light` (nếu người dùng không giữ state khác ở ngoài `WebSession`).

**Không gửi mã session thật, mật khẩu hoặc CSRF token vào ticket/log.** Nếu chụp DevTools để báo cáo QA, che giá trị cookie/credential/token.

## 6. Vì sao cần cả session và CSRF?

### 6.1 Phiên: server lưu SecurityContext, browser giữ định danh

Trong form login, browser nhận cookie định danh phiên; server liên kết `SecurityContext` với `WebSession`. Khi browser gửi cookie ở request sau, framework tải ngữ cảnh bảo mật và đánh giá rule của `SecurityWebFilterChain`. Chính vì browser gửi cookie tự động nên form ghi dữ liệu cần CSRF protection.

Các trạng thái độc lập cần hiểu:

- **Unauthenticated:** chưa có `Authentication` đáng tin; `/dashboard` chuyển đến login.
- **Authenticated:** `SecurityContext` được lưu theo WebSession và user có `ROLE_USER`.
- **Session expired:** dữ liệu phiên hết hiệu lực theo cấu hình idle timeout; browser phải đăng nhập lại.
- **Logged out:** ngữ cảnh bảo mật bị xóa và **WebSession bị hủy bởi handler đã thêm**.
- **CSRF rejected:** request ghi dữ liệu thiếu/sai token bị chặn **dù cookie vẫn còn** và user đã đăng nhập.

CSRF token gắn với phiên đang dùng, nhưng **không phải mật khẩu**, cũng không phải bearer token dùng để xác thực danh tính. Nó là bằng chứng phía gửi form biết token mà trang ngoài nguồn gốc không nên biết. Cookie `SESSION` tự nó không thay thế token `_csrf`.

### 6.2 WebSession khác HttpSession

| Spring WebFlux / Reactive | Spring MVC / Servlet |
| --- | --- |
| `ServerHttpSecurity` | `HttpSecurity` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `ServerWebExchange` | `HttpServletRequest` |
| `WebSession` | `HttpSession` |
| `WebSessionServerCsrfTokenRepository` | `HttpSessionCsrfTokenRepository` |
| `SecurityContextServerLogoutHandler` | `SecurityContextLogoutHandler` |
| `WebSessionServerLogoutHandler` | `HttpSession.invalidate()` / servlet logout mechanism |

Không đưa các hướng dẫn `SessionCreationPolicy.STATELESS`, `HttpServletRequest#getSession()`, `HttpSecurity.csrf()` hay `HttpSessionCsrfTokenRepository` từ tài liệu Servlet vào ví dụ reactive. Nếu ứng dụng dùng JWT/Bearer stateless thì cơ chế và mức cần thiết của CSRF lại phải đánh giá dựa trên cách browser gửi credential; **bài này cố ý dùng session-cookie-based form login**.

### 6.3 Cách CSRF token được xuất và xác minh

Với Spring Security WebFlux, expected token được giữ trong `WebSession` theo repository mặc định. `CsrfWebFilter` đặt `Mono<CsrfToken>` vào attribute của `ServerWebExchange`; controller render nó thành hidden input trong các form POST. Khi browser submit, framework nhận form field `_csrf` và so sánh với token expected.

Sơ đồ:

```text
GET /login hoặc GET /dashboard
  server tạo/tải CSRF token từ WebSession
  render input hidden _csrf

POST /login, /preferences, /logout
  browser gửi Cookie phiên (tự động)
  browser gửi _csrf (lấy từ form)
  CSRF filter đối chiếu expected token
    +-- Khớp: cho các security filter tiếp tục xử lý
    +-- Thiếu/sai: từ chối POST trước nghiệp vụ
```

CSRF quan trọng cho **đăng nhập** (tránh login CSRF), **đổi trạng thái** và **đăng xuất** (tránh logout CSRF). Không nên tắt CSRF toàn ứng dụng bằng `.csrf(csrf -> csrf.disable())` để một form “chạy được”. Nếu frontend dùng AJAX/JSON, cần gửi token qua header thích hợp (ví dụ `X-CSRF-TOKEN`) hoặc tích hợp token repository/handler được thiết kế cho SPA; khi dùng form urlencoded, hidden input là cách đơn giản nhất.

### 6.4 Redirect sau login, bảo vệ route và status code

| Request | Khi chưa đăng nhập | Sau đăng nhập có role USER |
| --- | --- | --- |
| `GET /` | 200, public | 200, public |
| `GET /login` | 200, form HTML | Tùy ứng dụng; controller vẫn public |
| `GET /dashboard` | Thường 302 tới login | 200, HTML dashboard |
| `POST /preferences` + CSRF hợp lệ | Không có quyền, bị chặn/redirect login | 200, cập nhật theme |
| `POST /preferences` thiếu/sai CSRF | Không được cập nhật | Thường 403; không cập nhật |
| `POST /logout` + CSRF hợp lệ | Không giả định đây là truy cập nghiệp vụ | Xóa context và hủy WebSession, chuyển về login |
| `POST /logout` thiếu CSRF | Không được coi là logout hợp lệ | Thường 403, phiên còn tồn tại |
| Route chưa khai báo | Bị `denyAll` | Vẫn bị `denyAll` |

HTTP status thực tế phụ thuộc phiên bản, entry point và custom error handler. Khi thấy 403, cần phân biệt **CSRF invalid** với **authorization denied** bằng log/đường đi request, không kết luận chỉ từ mã HTTP.

## 7. Bổ sung kiểm thử tự động (tùy chọn)

Kiểm thử bằng browser là cách tốt nhất để nhìn form và cookie. Trong CI, có thể dùng `WebTestClient` với Spring Security test support (`spring-security-test`) để viết các bài test:

- Đường public trả 200; dashboard của anonymous bị redirect.
- User có `ROLE_USER` truy cập dashboard.
- POST preferences đã đăng nhập nhưng thiếu CSRF trả 403; session không đổi.
- POST preferences có token hợp lệ cập nhật state.
- POST logout có token hợp lệ loại bỏ quyền truy cập khi dùng lại cookie cũ.
- POST login với mật khẩu sai không sinh `SecurityContext` đã xác thực.
- Sau session idle timeout, request protected cần xác thực lại.

Khi dùng security test mutator như `mockUser()` hoặc `csrf()`, hãy nhớ đó là **cơ chế kiểm thử tạo sẵn context/token**, không chứng minh trình duyệt gửi đúng cookie và form trong tích hợp thật. Nên có ít nhất một test end-to-end chạy POST login thật qua trang form, giữ cookie jar, gửi POST logout và kiểm tra session cũ không còn quyền. Đừng coi test chỉ assert mã 200 là đủ: phải chứng minh request không có token không gây side effect.

Một kịch bản kiểm tra bằng tay có thể ghi thành acceptance criteria:

```text
Given một browser sạch và tài khoản learner hợp lệ
When GET /dashboard
Then chuyển tới login

When POST /login với username, password và _csrf hợp lệ
Then xác thực thành công và được xem /dashboard

When POST /preferences với theme=dark và _csrf hợp lệ
Then response body là "Saved theme: dark"
And GET /dashboard hiển thị theme dark

When POST /preferences mà _csrf bị bỏ hoặc sai
Then request bị từ chối
And theme trong WebSession không thay đổi

When POST /logout với _csrf hợp lệ
Then phiên cũ không còn quyền truy cập /dashboard
And lần truy cập được yêu cầu đăng nhập lại
```

## 8. Lưu ý triển khai production

1. **HTTPS và cookie:** chỉ dùng session-cookie form login qua HTTPS. Kiểm tra cookie `Secure`, `HttpOnly`, `SameSite`, `Path`, domain và expiry trên browser/proxy thực tế. `SameSite=Lax` hoặc `Strict` cần lựa theo luồng đăng nhập/cross-site có thật; không giả định mọi giá trị cookie của mọi môi trường đều phù hợp.
2. **Session fixation:** bảo đảm session identifier được bảo vệ khi chuyển từ anonymous sang authenticated theo chính sách/phiên bản đang chạy; thử nhận diện ID trước/sau login. Đừng tùy tiện áp dụng cấu hình session fixation của **Servlet** vào WebFlux.
3. **Timeout và multi-node:** đặt idle timeout phù hợp. Session mặc định lưu tại node không thích hợp cho nhiều replica nếu không có sticky session hoặc store chung; cân nhắc Spring Session Reactive với Redis hay store được hỗ trợ để phục vụ load balancing và hủy phiên nhất quán. `spring.session.timeout` là thuộc tính của cấu hình Spring Session, không mặc định suy rộng sang mọi cách lưu WebSession.
4. **Mật khẩu và quản trị tài khoản:** lưu salted adaptive hash (BCrypt/Argon2/PBKDF2 tùy chính sách), không log mật khẩu, chống brute force/rate limit, MFA nếu cần; nguồn `MapReactiveUserDetailsService` là ví dụ nhỏ, không lưu người dùng thật.
5. **Authorization:** bảo vệ endpoint nghiệp vụ ở đúng role/authority và điều kiện sở hữu tài nguyên, không chỉ dựa một trang ẩn trên UI. `permitAll` chỉ dành route public được duyệt.
6. **CSRF:** bắt buộc bảo vệ POST/PUT/PATCH/DELETE khi trình duyệt dùng credential tự động, kể cả login và logout. GET phải không có side effect; không đưa token vào URL, link chia sẻ, access log.
7. **Đăng xuất:** xóa `SecurityContext`, CSRF token và session theo chính sách; đừng tự viết `@PostMapping("/logout")` bỏ qua logout handlers. Với SSO/OIDC, còn cần đánh giá logout của IdP nếu yêu cầu.
8. **Session state:** không lưu số thẻ, mật khẩu, JWT hoặc đối tượng lớn/không serializable trong session. Ví dụ `theme` chỉ minh họa; dữ liệu lâu dài cần database/thiết kế riêng.
9. **CSP/XSS:** escape output HTML, áp Content Security Policy phù hợp; ngăn XSS vì mã độc cùng origin có thể lấy CSRF token và thực hiện yêu cầu thay người dùng.
10. **Quan sát:** ghi số login success/failure, session expiration, CSRF denied, logout, authorization denied (không có token/raw cookie). Kết nối correlation ID trong WebFlux để điều tra qua reactive pipeline.

## 9. Lỗi thường gặp và xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| POST /login luôn 403 | Thiếu CSRF hidden input, CSRF token không thuộc cùng session, cookie không được giữ | Xem response GET /login có `_csrf`, kiểm tra POST có cookie + token |
| POST /login 302 về `/login?error` | Sai username/password hoặc cấu hình PasswordEncoder không khớp | Xác minh biến `DEMO_PASSWORD` ở tiến trình server và BCrypt encoder |
| GET /dashboard luôn về login | Browser không gửi cookie, session đã hết hạn, login chưa thành công, context không được lưu | Kiểm tra cookie/session storage và rule authentication; không dựa vào ThreadLocal |
| Form preferences không cập nhật | CSRF bị từ chối, không có role USER, form name không đúng, giá trị theme không hợp lệ | DevTools xem request POST; check status và body; xác minh GET /dashboard sau đó |
| POST /logout báo 403 | Thiếu CSRF token, dùng token của phiên cũ | Render lại dashboard để lấy token hiện hành; không đổi logout thành GET |
| Bấm logout rồi vẫn vào dashboard | Chưa hủy/làm sạch context, gửi cookie của phiên khác, proxy cache nội dung | Kiểm tra logout filter và cả hai logout handlers, vô hiệu cache trang nhạy cảm |
| State `theme` mất sau restart | WebSession in-memory, không phải database | Đây là hành vi của demo; dùng store chung nếu cần persistence có quản lý |
| Chỉ test được khi tắt CSRF | Form chưa truyền token hoặc dùng API Servlet trong WebFlux | Sửa hidden input/handler; giữ CSRF bật |
| HTML hiển thị sai/XSS | Gắn dữ liệu không escape vào HTML | Escape theo ngữ cảnh, dùng template/view engine chuẩn |
| Multi-node login chập chờn | Phiên nằm trên một node, request kế tiếp tới node khác | Dùng store phiên dùng chung hoặc routing phù hợp |

## 10. Checklist tự đánh giá

- [ ] Có thể biên dịch/chạy ứng dụng trên JDK 21 với dependencies WebFlux và Security.
- [ ] GET /login trả HTML form có username, password và CSRF hidden input hợp lệ.
- [ ] POST /login do Spring Security xử lý, mật khẩu so với BCrypt hash.
- [ ] Sau login thành công, truy cập /dashboard ở request tiếp theo bằng cookie phiên.
- [ ] POST /preferences có CSRF hợp lệ đổi state trong `WebSession`.
- [ ] POST /preferences thiếu/sai CSRF bị chặn và **không đổi state**.
- [ ] POST /logout có CSRF hợp lệ xóa SecurityContext và hủy WebSession.
- [ ] Sau logout, cookie cũ không thể tiếp tục truy cập tài nguyên bảo vệ.
- [ ] Route chưa được công khai bị deny, không mở quyền hoặc tắt CSRF để “chữa lỗi”.
- [ ] Trên production có chính sách TLS, cookie, session timeout, session store, password policy và logging phù hợp.

## Tài liệu tham khảo chính thức

- Spring Security — WebFlux Security (cấu hình `SecurityWebFilterChain`, form login): https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Getting Started with WebFlux Applications: https://docs.spring.io/spring-security/reference/reactive/getting-started.html
- Spring Security — Cross Site Request Forgery in WebFlux (CSRF attribute, hidden input, login/logout): https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Reactive Logout (phân biệt clear context và hủy WebSession): https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html
- Spring Security — WebFlux Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Boot — Spring Session và thuộc tính timeout: https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html
- Spring Framework — WebFlux và WebSession: https://docs.spring.io/spring-framework/reference/web/webflux.html
