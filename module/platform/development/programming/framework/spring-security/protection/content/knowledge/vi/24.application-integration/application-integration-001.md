# Ứng dụng render phía máy chủ và form có cookie phiên

## Mục tiêu học tập

Sau bài học thuộc chương **Tích hợp ứng dụng**, người học có thể:

- Mô tả luồng **server-side rendering (SSR)**: trình duyệt gửi GET, server render HTML và form, người dùng submit POST, server kiểm chứng phiên và CSRF token rồi cập nhật dữ liệu.
- Phân biệt **cookie chứa session ID**, **thông tin xác thực lưu trên server** và **CSRF token do client gửi chủ động**.
- Thiết kế một luồng **form login → truy cập trang bảo vệ → submit form → Post/Redirect/Get → logout** theo cách phù hợp với HTTP và Spring Security.
- Tích hợp bảo vệ **CSRF, session fixation, SameSite, HttpOnly, Secure, security headers, CSP và HSTS** mà không gây lỗi trải nghiệm người dùng.
- Xây dựng ví dụ **Spring MVC/Servlet + Thymeleaf** và một biến thể **Spring WebFlux/Reactive + view template** với khác biệt API rõ ràng.
- Phân tích các tác nhân triển khai thực tế như **reverse proxy, HTTPS termination, context path, nhiều node, nhiều tab, form hết hạn và đăng nhập lại**.
- Viết kiểm thử `MockMvc`, `WebTestClient` và kiểm thử trình duyệt để phát hiện token bị thiếu/sai, phiên bị mất, GET có tác động và lỗi cấu hình cookie.
- Nhận ra ranh giới trách nhiệm giữa **Spring Security**, tầng view, trình duyệt, reverse proxy, database và code nghiệp vụ.

## 1. SSR với form và session cookie là mô hình gì?

Trong ứng dụng **render phía máy chủ**, HTML của trang được tạo trên server trước khi gửi về trình duyệt. Người dùng thao tác với form trong HTML, và một request mới được gửi đến server để xử lý dữ liệu.

Ví dụ một ứng dụng quản lý hồ sơ:

1. Người dùng truy cập `GET /login`.
2. Server trả HTML có trường username/password và **CSRF token** cho form.
3. Browser gửi `POST /login` chứa credentials và CSRF token.
4. Sau khi xác thực, Spring Security quản lý **SecurityContext** và phiên theo cấu hình; browser nhận cookie chứa định danh phiên.
5. Người dùng mở `GET /account/settings`; browser **tự gửi session cookie** tới host đích nếu chính sách cookie cho phép.
6. Server tra phiên, xác thực/phân quyền, render HTML cài đặt với **CSRF token hợp lệ**.
7. Người dùng submit `POST /account/settings` gồm dữ liệu và CSRF token.
8. `CsrfFilter` kiểm tra token; security chain cũng xử lý xác thực/phân quyền; controller cập nhật dữ liệu.
9. Server trả redirect, browser GET lại trang kết quả — mẫu **Post/Redirect/Get (PRG)**.
10. Người dùng gửi `POST /logout` có CSRF token để kết thúc phiên xác thực.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant S as Spring Security
    participant V as Controller + View
    participant D as Service + Database

    U->>B: Mở /login
    B->>S: GET /login
    S->>V: Hiển thị form và token CSRF
    V-->>B: HTML đăng nhập
    U->>B: Nhập username/password
    B->>S: POST /login + token CSRF
    S->>S: Kiểm tra CSRF và credentials
    S-->>B: Redirect + cookie phiên
    B->>S: GET /account/settings + cookie phiên
    S->>V: Cho phép đọc trang của user
    V-->>B: HTML form có token CSRF
    U->>B: Submit thay đổi
    B->>S: POST /account/settings + cookie + token
    S->>S: Kiểm tra CSRF và quyền truy cập
    S->>V: Cho phép xử lý request
    V->>D: Validate và lưu
    D-->>V: Kết quả
    V-->>B: 303/302 redirect theo triển khai
    B->>S: GET /account/settings + cookie
    S->>V: Render thông tin mới
    V-->>B: HTML kết quả
~~~

**Điểm mấu chốt:** Browser chỉ cần biết **session ID**, không cần giữ toàn bộ `SecurityContext` hay các chi tiết lưu phiên phía server. Nhưng chính vì browser tự gửi cookie trên request hợp lệ về phạm vi, **CSRF** trở thành một thành phần bảo vệ quan trọng với các form làm thay đổi trạng thái.

Bài học tích hợp những lớp phòng vệ của module **SPRING_SECURITY_HTTP_PROTECTION**: CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session cho **Servlet** lẫn **Reactive**. Đây là một kiến trúc điển hình nơi các lớp phải hoạt động **cùng nhau**, không dùng lớp nọ thay lớp kia.

## 2. Phân biệt ba giá trị trong một form đã đăng nhập

Giả sử trình duyệt gửi request:

~~~http
POST /account/settings HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SID_A
Content-Type: application/x-www-form-urlencoded

theme=dark&_csrf=FORM_TOKEN_A
~~~

Có ba khái niệm cần tách bạch:

| Thành phần | Nó dùng để làm gì? | Bên nào gửi? | Nơi kiểm chứng |
|---|---|---|---|
| **Session ID** `SID_A` | Tra phiên đã tồn tại, tìm ngữ cảnh người dùng và dữ liệu phiên | Browser **tự gắn cookie** nếu đủ điều kiện | Servlet container/session infrastructure, Spring Security |
| **Thông tin xác thực trong phiên** | Xác định danh tính Alice và authorities | Thường được lưu/quản lý server-side, **không phải field form** | Spring Security authentication/authorization |
| **CSRF token** `FORM_TOKEN_A` | Chứng minh request có giá trị được cấp theo ngữ cảnh chống giả mạo | Form HTML hoặc JavaScript **chủ động gửi** | CSRF repository, request handler và filter |

**Không dùng session ID làm CSRF token.** Session ID là credential rất nhạy cảm; render nó vào hidden field làm tăng nguy cơ lộ và chiếm phiên. CSRF token được sinh/kiểm tra **độc lập** theo chính sách.

**Không dùng CSRF token làm quyền truy cập.** Request có token đúng nhưng không có phiên xác thực hoặc thiếu authority vẫn có thể bị từ chối. Ngược lại, request có cookie session xác thực nhưng thiếu token CSRF vẫn phải bị chặn nếu phương thức/endpoint thuộc phạm vi bảo vệ.

### 2.1. Cookie HttpOnly không tự chống CSRF

Cookie có thể được phát theo mẫu:

~~~http
Set-Cookie: JSESSIONID=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `HttpOnly`: Hạn chế JavaScript thông thường đọc cookie bằng `document.cookie`.
- `Secure`: Chỉ gửi cookie qua kết nối an toàn phù hợp, thường HTTPS.
- `SameSite=Lax`: Hạn chế nhiều request cross-site có cookie, nhưng vẫn có ngoại lệ như top-level GET và các request same-site khác origin.
- `Path`: Giới hạn đường dẫn gửi cookie; không phải ranh giới bảo mật đủ mạnh giữa các ứng dụng cùng host.

Browser **vẫn có thể tự đính kèm cookie HttpOnly** vào request hợp lệ. Vì vậy các POST dựa trên phiên vẫn cần CSRF token theo mô hình đe dọa.

### 2.2. Same-site không nhất thiết là same-origin

Hai trang `https://app.example.com` và `https://blog.example.com` có thể **cùng site nhưng khác origin**. Nếu một subdomain kém tin cậy bị kiểm soát, browser vẫn có thể gửi cookie của app tới host app theo SameSite policy khi request xuất phát từ blog. CSRF token gắn đúng phiên giúp chặn một form POST không có token hợp lệ từ origin khác.

Same-Origin Policy hạn chế script ở blog đọc DOM/response riêng của app, nhưng **không phải mọi request đều bị ngăn gửi**. Không dùng `SameSite=Strict` làm lý do bỏ CSRF cho ứng dụng SSR có form.

## 3. HTTP method của SSR và form phải đúng ngữ nghĩa

Một luồng form nên phân tách:

| Request | Mục đích | Có thay đổi dữ liệu? | CSRF mặc định? |
|---|---|---|---|
| `GET /login` | Hiển thị form đăng nhập | Không | Không yêu cầu token để GET |
| `POST /login` | Xác thực credentials, tạo phiên | Có thể | **Yêu cầu token** |
| `GET /account/settings` | Render trang cài đặt | Không | Không yêu cầu token để GET |
| `POST /account/settings` | Lưu cài đặt | Có | **Yêu cầu token** |
| `GET /account/delete/confirm` | Hiển thị trang xác nhận xóa | Không | Không yêu cầu token để GET |
| `POST /account/delete` | Xóa tài khoản theo chính sách | Có | **Yêu cầu token** |
| `GET /logout` | Có thể hiển thị trang xác nhận đăng xuất | Không được trực tiếp logout theo mô hình an toàn | Không yêu cầu token để GET |
| `POST /logout` | Thực hiện logout | Có | **Yêu cầu token** |

Spring Security mặc định thường bỏ qua CSRF cho các phương thức **`GET`, `HEAD`, `OPTIONS`, `TRACE`**; các phương thức như `POST`, `PUT`, `PATCH`, `DELETE` được kiểm tra. Do vậy GET **phải thực sự chỉ đọc**.

Ví dụ **không an toàn**:

~~~html
<!-- Tránh: GET /logout có thể bị browser/crawler/link preview kích hoạt -->
<a href="/logout?doIt=true">Đăng xuất ngay</a>
~~~

Nếu server cố ý thực hiện logout trên GET thì một điều hướng có thể gây logout CSRF; cookie `SameSite=Lax` có thể được gửi trong top-level GET cross-site. Hãy dùng một form POST có token.

## 4. Servlet: các lớp Spring tham gia vào form SSR

Trong mô hình **Spring MVC + Spring Security Servlet**, một request đi qua nhiều thành phần:

~~~mermaid
flowchart TD
    A[Browser gửi request + cookie] --> B[Servlet Filter Chain]
    B --> C[Spring Security FilterChainProxy]
    C --> D[SecurityFilterChain phù hợp]
    D --> E[Session và SecurityContext]
    E --> F[CsrfFilter trên unsafe requests]
    F --> G[Authentication và Authorization]
    G --> H[DispatcherServlet / Controller]
    H --> I[Service / Database]
    I --> J[View resolver và Thymeleaf]
    J --> K[HTML / Redirect về browser]
~~~

Sơ đồ **giản lược theo chức năng**; thứ tự chính xác các filter phụ thuộc security version và configuration, và không phải mọi request đều đi qua tất cả bước như một pipeline tuyến tính cố định. `LogoutFilter` hoặc form-login authentication filter có thể xử lý request trước khi nó tới controller.

Những thành phần cần biết:

| Thành phần | Vai trò |
|---|---|
| `SecurityFilterChain` | Tập hợp filter và chính sách cho một phạm vi request |
| `HttpSession` | Lưu dữ liệu phiên theo Servlet container/session store |
| `SecurityContext` | Biểu diễn authentication trong request và repository được cấu hình |
| `UsernamePasswordAuthenticationFilter` | Xử lý form POST login trong cấu hình form login điển hình |
| `CsrfFilter` | Chặn unsafe request thiếu/sai CSRF token |
| `HttpSessionCsrfTokenRepository` | Lưu/tải expected CSRF token theo HttpSession |
| `CsrfTokenRequestHandler` | Cấp/resolve token trong request, hỗ trợ biểu diễn token phù hợp |
| `AuthorizationFilter` | Áp dụng quy tắc phân quyền của `authorizeHttpRequests` |
| `LogoutFilter` | Xử lý request logout theo matcher, không cần controller POST tự viết |
| `DispatcherServlet` và `@Controller` | Định tuyến GET render view và POST nghiệp vụ |
| Thymeleaf | Render HTML; khi tích hợp đúng có thể đưa CSRF token vào form |

Một ứng dụng Spring Security không phải lúc nào cũng dùng đúng cơ chế session lưu authentication theo một cách duy nhất. Trong bài này giả định **SSR + form login + session cookie**, tức là mô hình thông dụng sử dụng trạng thái phiên.

## 5. Ví dụ tích hợp Spring MVC/Servlet

### 5.1. Các thành phần dự kiến trong project

Một project mẫu có thể sử dụng Spring Boot/Spring MVC với các dependency phù hợp:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-thymeleaf
spring-boot-starter-validation    (nếu dùng Bean Validation)
spring-security-test              (phạm vi test)
spring-boot-starter-test          (phạm vi test)
~~~

Danh sách là định hướng chứ không phải file build đầy đủ. Với Spring Security phiên bản hiện đại, nên chọn dependency BOM của Spring Boot tương thích thay vì tự ghép phiên bản tùy ý. Cần có `UserDetailsService`/authentication provider hoặc cơ chế xác thực thực tế; không dùng tài khoản demo cố định trong production.

### 5.2. SecurityFilterChain: form login và CSRF giữ nguyên

Ví dụ cấu hình có **trang login tùy biến**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletWebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/css/**", "/js/**", "/images/**", "/login", "/error"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(login -> login
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/account/settings", false)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giải thích:**

- `GET /login` **phải do ứng dụng cung cấp** khi đã đặt `loginPage("/login")`.
- `POST /login` được Spring Security xử lý theo `loginProcessingUrl`. Không tự tạo controller POST cùng URL rồi xác thực lần hai.
- `requestMatchers("/login").permitAll()` cho phép người chưa đăng nhập xem form; nó **không có nghĩa POST login được miễn CSRF**.
- `POST /logout` được xử lý bởi Spring Security khi hợp lệ. Không tự triển khai `@PostMapping("/logout")` chỉ để gọi `session.invalidate()`.
- `csrf(Customizer.withDefaults())` giữ CSRF protection; Spring Security web thường bật sẵn, dòng này làm rõ yêu cầu.
- Cấu hình được viết cho ứng dụng **có phiên và dùng browser cookie**; đừng sao chép một mẫu API bearer-only có `csrf.disable()` vào đây.

### 5.3. Controller GET để hiển thị trang login

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class LoginPageController {

    @GetMapping("/login")
    String login() {
        return "auth/login"; // templates/auth/login.html
    }
}
~~~

Controller trên **chỉ render view**. Form được POST tới URL do Spring Security nhận. Nếu server có context path, cần tạo URL phù hợp thay vì chỉ ghép chuỗi tuyệt đối.

### 5.4. Template Thymeleaf cho login có CSRF token

~~~html
<!-- templates/auth/login.html -->
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đăng nhập</title>
</head>
<body>
  <h1>Đăng nhập</h1>

  <p th:if="${param.error}">Thông tin đăng nhập không hợp lệ.</p>
  <p th:if="${param.logout}">Bạn đã đăng xuất.</p>

  <form action="/login" method="post">
    <label for="username">Tên đăng nhập</label>
    <input id="username" name="username"
           autocomplete="username" required>

    <label for="password">Mật khẩu</label>
    <input id="password" type="password" name="password"
           autocomplete="current-password" required>

    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">

    <button type="submit">Đăng nhập</button>
  </form>
</body>
</html>
~~~

Khi Spring Security và MVC/Thymeleaf được tích hợp đúng, request attribute `_csrf` có thể cung cấp tên form field và token mà server chấp nhận. Giá trị form trong HTML thực tế có thể là **XOR-masked token**; không so sánh chuỗi HTML với raw token nội bộ như một điều kiện bắt buộc.

**Không hardcode token**, không lấy `JSESSIONID` làm giá trị `_csrf`, và không đưa password hoặc CSRF token vào URL.

Lưu ý tích hợp Thymeleaf: Khi dùng `th:action` hoặc cơ chế request data value processor, Spring có thể **tự thêm hidden CSRF field** cho form. Mẫu trên dùng `action` tĩnh và chủ động render field để diễn giải; khi chuyển sang `th:action="@{/login}"`, hãy kiểm tra HTML cuối cùng và **tránh trường token trùng nhau**. URL tĩnh cần xem lại nếu deploy ứng dụng dưới context path.

### 5.5. Trang bảo vệ và form thay đổi cài đặt

Controller minh họa:

~~~java
import java.security.Principal;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
class AccountSettingsController {

    private final PreferencesService preferences;

    AccountSettingsController(PreferencesService preferences) {
        this.preferences = preferences;
    }

    @GetMapping("/account/settings")
    String settings(Model model, Principal principal) {
        String theme = preferences.readTheme(principal.getName());
        model.addAttribute("theme", theme);
        return "account/settings";
    }

    @PostMapping("/account/settings")
    String save(@RequestParam String theme,
                Principal principal,
                RedirectAttributes redirect) {

        if (!Set.of("light", "dark").contains(theme)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Theme không hợp lệ");
        }

        preferences.updateTheme(principal.getName(), theme);
        redirect.addFlashAttribute("notice", "Đã lưu cài đặt.");
        return "redirect:/account/settings";
    }
}
~~~

Ở đây `PreferencesService` là **service thuộc ứng dụng cần được triển khai** để đọc/ghi database, kiểm tra quyền theo tài nguyên và xử lý transaction. Controller chỉ minh họa HTTP mapping, input validation và mẫu PRG; không có nghĩa mọi hệ thống có thể lấy Principal name rồi bỏ qua kiểm soát quyền trong service.

Trang view:

~~~html
<!-- templates/account/settings.html -->
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Cài đặt tài khoản</title>
</head>
<body>
  <h1>Cài đặt</h1>
  <p th:if="${notice}" th:text="${notice}"></p>

  <form action="/account/settings" method="post">
    <label for="theme">Giao diện</label>
    <select id="theme" name="theme">
      <option value="light" th:selected="${theme == 'light'}">Sáng</option>
      <option value="dark" th:selected="${theme == 'dark'}">Tối</option>
    </select>

    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Lưu</button>
  </form>

  <form action="/logout" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Đăng xuất</button>
  </form>
</body>
</html>
~~~

**Hai form dùng chung CSRF token thuộc request/phiên hiện tại** nếu repository/handler cho phép. Không có yêu cầu tự tạo một CSRF token riêng cho mỗi field nghiệp vụ. Khi session thay đổi do login/logout/timeout, token được cấp trước đó có thể trở nên không hợp lệ.

### 5.6. Tại sao lưu và logout phải dùng POST?

Một link GET chỉ có thể mở trang xác nhận; nó không được yêu cầu trực tiếp **đổi trạng thái nghiệp vụ**. Với thiết kế trên:

- `GET /account/settings` chỉ đọc dữ liệu và render HTML.
- `POST /account/settings` là nơi thực hiện ghi dữ liệu và phải vượt CSRF.
- `POST /logout` là yêu cầu thay đổi trạng thái đăng nhập và được bảo vệ.
- `GET /logout`, nếu được hỗ trợ như trang xác nhận, **không được hiểu là đã logout**.

Nếu một ứng dụng tùy chỉnh logout matcher để dùng GET, nó có thể vô tình mở đường **logout CSRF**. Không chuyển sang GET logout để “giảm lỗi thiếu token”.

## 6. Post/Redirect/Get (PRG) và an toàn khi submit lại

### 6.1. PRG là gì?

Khi POST cập nhật thành công, server thay vì trả thẳng trang kết quả có thể trả redirect:

~~~http
POST /account/settings HTTP/1.1
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

theme=dark&_csrf=VALID_TOKEN
~~~

~~~http
HTTP/1.1 302 Found
Location: /account/settings
~~~

Browser GET lại:

~~~http
GET /account/settings HTTP/1.1
Cookie: JSESSIONID=SESSION_A
~~~

PRG giúp người dùng nhấn Refresh ở trang kết quả mà **không tự động gửi lại POST trước đó**. Redirect từ controller ở ví dụ Spring MVC thường dùng status phù hợp cơ chế framework; nếu cần semantics rõ ràng, `303 See Other` quy định client dùng GET khi theo redirect từ một request có thể đã thay đổi trạng thái.

**Không nhầm PRG với CSRF:** PRG giúp giảm thao tác gửi lại không chủ ý; **CSRF token** giúp chặn request giả mạo. PRG cũng **không thay idempotency key** cho những giao dịch cần ngăn xử lý trùng.

### 6.2. Flash attribute và session

`RedirectAttributes.addFlashAttribute` thường lưu thông điệp trong cơ chế **FlashMap** phù hợp để hiển thị sau redirect. Không dùng nó làm kho bảo mật hay lưu password/access token. Thông điệp flash có thể liên quan đến session hoặc cơ chế request được framework quản lý, nên cần cân nhắc quy mô session khi vận hành nhiều node.

Nếu người dùng mở nhiều tab, những thao tác song song hoặc redirect khác có thể ảnh hưởng trải nghiệm flash message; không dùng flash attribute làm nơi lưu trạng thái nghiệp vụ quan trọng.

### 6.3. Token hết hạn trong form mở lâu

Một tab có thể mở form ở thời điểm `T1`, sau đó người dùng đăng xuất, đăng nhập lại hoặc session timeout ở thời điểm `T2`. Form cũ khi submit có thể mang token **không còn phù hợp với session mới**, và server trả `403`.

Đó có thể là hành vi bảo mật **đúng**. UI nên giải thích hợp lý và cho phép tải lại form hoặc nhận token mới qua luồng an toàn; **không tắt CSRF** chỉ để form cũ tiếp tục submit được.

## 7. Vòng đời phiên: đăng nhập, nâng cấp danh tính và đăng xuất

### 7.1. Phiên trước đăng nhập vẫn có thể tồn tại

Một ứng dụng Spring Security có thể tạo **anonymous/pre-authentication session** để lưu CSRF token hoặc dữ liệu phục vụ login. Vì vậy `JSESSIONID` xuất hiện trước login **không có nghĩa** người dùng đã được xác thực.

Luồng đăng nhập thông thường:

1. Browser GET trang login, server cấp token cho form nếu cần.
2. Browser POST credentials + CSRF token.
3. Spring Security kiểm tra CSRF và thực hiện authentication.
4. Sau khi xác thực thành công, cơ chế **session fixation protection** có thể đổi session ID để tránh attacker cố định một ID phiên trước login.
5. CSRF token trước login có thể bị xóa; trang render sau login có thể nhận token mới.
6. Browser sử dụng session cookie hiện hành cho các request tiếp theo.

Cần phân biệt **đổi session ID** với **đổi CSRF token**: hai cơ chế khác nhau. Spring Security có những thành phần quản lý CSRF token trong quá trình authentication/logout, nhưng không nên tự viết code copy session ID vào hidden field để “đồng bộ”.

### 7.2. Đăng xuất đúng cách

Spring Security Servlet cung cấp cơ chế logout handler để dọn authentication/security context và thường vô hiệu hóa `HttpSession` theo cấu hình mặc định phù hợp.

Khi nhận `POST /logout` có CSRF token:

~~~http
POST /logout HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SID_A
Content-Type: application/x-www-form-urlencoded

_csrf=TOKEN_A
~~~

Ứng dụng kiểm chứng token trước khi chạy logout. Phản hồi có thể redirect tới `/login?logout`. Sau logout, session đã xác thực không được tiếp tục cho phép truy cập tài nguyên bảo vệ. **Chỉ thấy redirect chưa đủ chứng minh logout đã xóa trạng thái**: cần kiểm tra session thực sự.

Nếu ứng dụng có **remember-me**, custom session store, OAuth2/OIDC, access/refresh token hoặc single sign-on, local logout **không tự bảo đảm thu hồi mọi token hay phiên Identity Provider**. Thiết kế đăng xuất phải ghi rõ các phạm vi đó.

### 7.3. Hai tab, cùng một cookie jar

Nhiều tab của cùng một browser profile thường **chia sẻ cookie phiên**. Khi tab A logout, tab B có thể vẫn hiển thị HTML cũ nhưng request POST từ tab B dùng phiên/token cũ sẽ bị từ chối hoặc yêu cầu đăng nhập lại.

Đừng dùng hai tab trong cùng browser context để giả lập **hai phiên độc lập** khi test ràng buộc CSRF token. Hãy tạo hai browser profiles/contexts hoặc hai cookie jars riêng.

### 7.4. Session timeout và kiểm tra tác động

Khi phiên timeout, request POST từ trang cũ có thể trả `403` do expected token không tồn tại hoặc redirect/`401` theo policy xác thực. Không nên cố “cho mọi POST cũ qua” để giữ trải nghiệm. Thiết kế hợp lý hơn:

- Dùng timeout rõ ràng và thông báo khi form đã cũ.
- Cho phép tải lại form sau khi đăng nhập lại.
- Với nội dung form dài, cân nhắc cơ chế lưu **bản nháp** được bảo vệ, không cố tái sử dụng session ID/CSRF token đã hết hiệu lực.
- Kiểm tra server không tạo side effect trước khi phát hiện token sai hoặc phiên không hợp lệ.

## 8. Session cookie: triển khai đúng các thuộc tính

### 8.1. Thuộc tính cookie và ranh giới trách nhiệm

| Thuộc tính | Vai trò | Lưu ý |
|---|---|---|
| `Secure` | Gửi cookie qua kết nối an toàn thích hợp | Cần HTTPS ở production; proxy TLS termination phải được cấu hình đúng |
| `HttpOnly` | Ngăn script thường đọc trực tiếp session ID | Không ngăn browser tự đính kèm cookie; XSS cùng origin vẫn có thể gọi API |
| `SameSite=Strict` | Hạn chế mạnh request cross-site mang cookie | Có thể ảnh hưởng điều hướng từ email/SSO; không chặn same-site subdomain |
| `SameSite=Lax` | Cân bằng điều hướng và hạn chế nhiều cross-site POST | Vẫn thường gửi cookie trong top-level GET cross-site; GET phải chỉ đọc |
| `SameSite=None; Secure` | Cho phép cookie trong nhiều ngữ cảnh cross-site | Browser có thể chặn third-party cookie; cần chống CSRF riêng |
| Không có `Domain` | Cookie host-only, không được gửi tới mọi subdomain | Một subdomain vẫn có thể kích hoạt request **đến host app** |
| `Path` | Phạm vi đường dẫn gửi cookie | Không phải cơ chế phân quyền giữa các ứng dụng cùng host |
| `Max-Age`/`Expires` | Thời gian lưu cookie trên browser | Không thay server-side session expiry |
| `__Host-` prefix | Yêu cầu Secure, Path=/ và không có Domain ở browser hỗ trợ | Có thể thu hẹp cookie-scope attacks nếu hạ tầng hỗ trợ tên cookie này |

Một cấu hình tham khảo:

~~~http
Set-Cookie: JSESSIONID=random-opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**Không coi SameSite là biện pháp thay thế CSRF token.** Những request *same-site cross-origin* từ subdomain ít tin cậy vẫn có thể mang cookie. Trường hợp login CSRF còn có thể tạo phiên mới mà không cần một cookie đã xác thực từ trước.

### 8.2. Cấu hình cookie Servlet trên Spring Boot

Với ứng dụng Spring Boot/Servlet và phiên bản hỗ trợ các thuộc tính tương ứng:

~~~yaml
# application.yml — ví dụ khi browser truy cập ứng dụng qua HTTPS
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
  forward-headers-strategy: framework
~~~

`server.forward-headers-strategy` chỉ là ví dụ **khi ứng dụng chạy sau reverse proxy tin cậy**, proxy truyền forwarded headers đúng cách. Nếu triển khai trực tiếp, không sao chép tùy tiện cấu hình này. Hạn chế chỉ tin header từ proxy được quản lý để tránh client giả mạo scheme/host.

Nếu dùng **Spring Session** hoặc custom cookie serializer, cookie có thể được phát bởi tầng đó thay vì Servlet container chuẩn. Khi đó thuộc tính cần cấu hình tại **bên thực sự tạo cookie**. Luôn kiểm tra `Set-Cookie` cuối cùng trong response ở trình duyệt.

### 8.3. Cẩn trọng khi bật Strict hoặc None

- `Strict` giảm nhiều trường hợp cookie được gửi từ site khác nhưng có thể khiến link tới trang riêng tư từ email/website ngoài không hiển thị như đang đăng nhập ở lần điều hướng đầu tiên.
- `Lax` thường phù hợp hơn cho luồng điều hướng vào ứng dụng, nhưng không ngăn việc GET có tác động và không bảo vệ toàn bộ same-site request.
- `None; Secure` cần đánh giá các tích hợp cross-site thực sự, ví dụ iframe, frontend khác site hoặc callback bằng form POST. Browser có thể chặn cookie third-party dù đã dùng `None`.
- OAuth2/OIDC callback dùng `state`/PKCE/nonce theo giao thức; chúng không thay CSRF token cho các form POST nghiệp vụ sau login.

## 9. HTTP security headers, CSP và HSTS trong ứng dụng SSR

SSR không tự loại rủi ro XSS. Một giá trị từ database được chèn không escape vào HTML có thể trở thành script chạy ngay trong origin ứng dụng; script đó có thể đọc CSRF token trong form và gửi request cùng origin.

### 9.1. Output encoding ở tầng template

Khi muốn hiển thị input người dùng như **văn bản**:

~~~html
<p th:text="${displayName}">Tên người dùng</p>
~~~

Dùng `th:text` để escape theo ngữ cảnh HTML text. Không dùng `th:utext` với dữ liệu không tin cậy trừ khi đã áp dụng một **HTML sanitizer allowlist** đáng tin cậy và có yêu cầu rich HTML thật sự.

Ở frontend JavaScript:

~~~javascript
// Hiển thị văn bản từ API/model:
document.querySelector("#status").textContent = serverMessage;

// Không làm với input chưa kiểm soát:
// document.querySelector("#status").innerHTML = serverMessage;
~~~

CSRF token ngăn nhiều request giả mạo từ origin ngoài, **không phân biệt** script hợp lệ và XSS đang chạy **trong cùng origin**.

### 9.2. CSP là lớp phòng vệ thêm

Một ứng dụng chỉ dùng JavaScript từ cùng origin có thể bắt đầu bằng chính sách CSP ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Đây là **mẫu định hướng**, không phải CSP tối ưu cho mọi frontend. `script-src 'self'` có thể chưa đủ mạnh nếu origin có thể phục vụ script không tin cậy. Một chính sách chặt hơn có thể dùng nonce/hash và quy trình quản lý script phù hợp.

Trong Spring Security Servlet, có thể bổ sung:

~~~java
// Đặt bên trong cấu hình HttpSecurity trước .build():
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; " +
            "script-src 'self'; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "frame-ancestors 'none'")));
~~~

Nếu ứng dụng dùng inline script, chính sách trên có thể chặn chúng. Không giải quyết bằng cách vội thêm `'unsafe-inline'`; thay vào đó cân nhắc chuyển script sang file được quản lý hoặc dùng nonce/hash đúng vòng đời.

**CSP không thay output encoding/HTML sanitization**. CSP cũng không tạo CSRF token.

### 9.3. HSTS và HTTPS

**HSTS** là response header `Strict-Transport-Security` giúp browser ghi nhớ chính sách sử dụng HTTPS trong phạm vi host và thời hạn. Với Spring Security, header HSTS thường được quản lý trên response HTTPS phù hợp, nhưng muốn có bảo vệ nhất quán cần:

- HTTPS thật sự hoạt động và chứng chỉ hợp lệ;
- cấu hình reverse proxy/forwarded headers đúng;
- không vô tình tạo redirect HTTP vòng lặp;
- kiểm tra ứng dụng tạo cookie `Secure` phù hợp;
- chỉ cân nhắc `includeSubDomains` và `preload` khi **tất cả** subdomain trong phạm vi đáp ứng điều kiện HTTPS lâu dài.

HSTS không ngăn một POST giả mạo tới HTTPS có cookie. Nó giải quyết rủi ro kết nối/hạ cấp, **không phải tính hợp lệ của request nghiệp vụ**.

### 9.4. Clickjacking và frame embedding

Trang form nhạy cảm có thể bị đặt trong iframe của website khác nếu chính sách frame không phù hợp. Có thể dùng CSP `frame-ancestors` và, ở những trường hợp phù hợp, `X-Frame-Options` để hạn chế nhúng trang, giảm nguy cơ clickjacking.

Đây **không** là CSRF token. Một attacker có thể khiến browser gửi form theo nhiều cách không cần nhúng iframe. Do đó giữ cả chính sách frame và lớp CSRF.

## 10. WebFlux/Reactive: SSR vẫn có WebSession và form

Spring WebFlux có thể render HTML qua view engine và xử lý form theo cách tương tự, nhưng sử dụng **`SecurityWebFilterChain`**, `ServerHttpSecurity` và các kiểu **reactive**.

### 10.1. Sự tương ứng giữa Servlet và WebFlux

| Vai trò | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| CSRF filter | `CsrfFilter` | `CsrfWebFilter` |
| Repository token theo phiên | `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| Session API | `HttpSession` | `WebSession` |
| HTTP exchange | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` |
| Form controller | `@Controller` trả view name | `@Controller` có thể trả `Mono<Rendering>` hoặc `Mono<String>` |
| Testing | `MockMvc` | `WebTestClient` |
| Cookie session | Thường `JSESSIONID` | Có thể `SESSION` hoặc tên do resolver cấu hình |

**Điều không đổi:** Browser gửi cookie theo SameSite/Domain/Path/Secure; form cần CSRF token khi submit thao tác ghi; tên cookie không phải bằng chứng request hợp lệ.

### 10.2. Reactive SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
class ReactiveSsrSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/css/**", "/js/**", "/login").permitAll()
                .anyExchange().authenticated()
            )
            .formLogin(form -> form.loginPage("/login"))
            .logout(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
~~~

Ứng dụng cần **ReactiveUserDetailsService** hoặc provider phù hợp để xác thực user; ví dụ này không tự tạo user.

**Phân biệt với Servlet:** Không dùng `HttpSessionCsrfTokenRepository` hay `HttpSecurity` trong ứng dụng WebFlux. Với WebSession, CSRF token và context được quản lý theo cơ chế reactive, không nên gọi API chặn (blocking) trong handler reactive để thao tác database.

### 10.3. Reactive controller render login form có token

Trong các cấu hình WebFlux dùng `CsrfWebFilter`, một `Mono<CsrfToken>` có thể được đặt tại exchange attribute. Controller lấy token rồi đưa vào model:

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveLoginPageController {

    @GetMapping("/login")
    Mono<Rendering> login(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf =
            exchange.getAttribute(CsrfToken.class.getName());

        return csrf.map(token ->
            Rendering.view("auth/login")
                .modelAttribute("_csrf", token)
                .build());
    }
}
~~~

Ví dụ giả định exchange đã đi qua security web filter và token attribute được cung cấp theo version/cách tích hợp đang dùng. Khi subscribe `Mono<CsrfToken>`, token được giải quyết để view render; các tích hợp khác có thể cấp token vào model tự động.

Form HTML về cơ bản vẫn có thể dùng:

~~~html
<form action="/login" method="post">
  <input name="username" required>
  <input name="password" type="password" required>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Đăng nhập</button>
</form>
~~~

Khi dùng template engine trong WebFlux, phải bảo đảm nó được cấu hình tương thích reactive stack. Với login page tùy chỉnh, ứng dụng cần cung cấp GET login; Spring Security vẫn xử lý POST form login theo endpoint đã cấu hình.

### 10.4. WebFlux controller cho form cài đặt và PRG

Giả sử `ReactivePreferencesService` có:

~~~java
interface ReactivePreferencesService {
    Mono<String> readTheme(String username);
    Mono<Void> updateTheme(String username, String theme);
}
~~~

Đây là **service giả định**, cần được hiện thực bằng một tầng lưu trữ non-blocking hoặc một kiến trúc reactive phù hợp. Controller:

~~~java
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.security.web.server.csrf.CsrfToken;

import reactor.core.publisher.Mono;

@Controller
class ReactiveSettingsController {

    private final ReactivePreferencesService preferences;

    ReactiveSettingsController(ReactivePreferencesService preferences) {
        this.preferences = preferences;
    }

    @GetMapping("/account/settings")
    Mono<Rendering> settings(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf =
            exchange.getAttribute(CsrfToken.class.getName());

        return Mono.zip(exchange.getPrincipal(), csrf)
            .flatMap(values -> preferences
                .readTheme(values.getT1().getName())
                .map(theme -> Rendering.view("account/settings")
                    .modelAttribute("theme", theme)
                    .modelAttribute("_csrf", values.getT2())
                    .build()));
    }

    @PostMapping("/account/settings")
    Mono<String> save(@RequestParam String theme,
                      ServerWebExchange exchange) {
        if (!Set.of("light", "dark").contains(theme)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Theme không hợp lệ"));
        }

        return exchange.getPrincipal()
            .flatMap(p -> preferences.updateTheme(p.getName(), theme))
            .thenReturn("redirect:/account/settings");
    }
}
~~~

Ý nghĩa:

- GET **đọc** theme và render form với token.
- POST **ghi** sau khi CSRF web filter đã xử lý request; không tự viết logic so token trong controller.
- View name dạng `redirect:/...` cho phép mẫu PRG khi cấu hình view resolver tương ứng hỗ trợ.
- Nếu service thực tế là JDBC blocking, không chạy blocking call trực tiếp trên event loop; nên chọn reactive driver hoặc cô lập tác vụ theo hướng dẫn về blocking workloads.
- Cần phân quyền và kiểm tra quyền truy cập vào tài nguyên trong service, không chỉ dựa vào username client gửi.

### 10.5. Cấu hình cookie WebSession

Khi sử dụng `CookieWebSessionIdResolver` và Spring Framework version hỗ trợ initializer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class ReactiveSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();

        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax"));

        return resolver;
    }
}
~~~

Nếu ứng dụng dùng **Spring Session**, custom resolver hoặc cấu hình tự động khác, nơi phát cookie thực tế có thể khác. Cần quan sát header cuối cùng thay vì giả định cấu hình này luôn thắng.

### 10.6. Logout ở Reactive có khác Servlet không?

Trong WebFlux, logout handler mặc định có thể dọn security context và thông tin CSRF theo cấu hình nhưng **không nên mặc định khẳng định toàn bộ `WebSession` luôn bị vô hiệu hóa như hành vi thường gặp ở Servlet**.

Nếu chính sách yêu cầu hủy WebSession, có thể cấu hình handler thích hợp, chẳng hạn `WebSessionServerLogoutHandler` kết hợp handler security context trong logout spec theo version đang dùng. Luôn kiểm tra yêu cầu quan trọng nhất: **sau logout, session cũ không còn được xem là đã xác thực trên route bảo vệ**.

Form logout vẫn dùng POST và CSRF token:

~~~html
<form action="/logout" method="post">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Đăng xuất</button>
</form>
~~~

## 11. Triển khai sau reverse proxy và nhiều instance

### 11.1. HTTPS termination và cookie Secure

Một ứng dụng có thể chạy nội bộ bằng HTTP sau reverse proxy, trong khi browser chỉ truy cập `https://app.example.com`:

~~~text
Browser --HTTPS--> Reverse Proxy --HTTP nội bộ--> Spring Boot
~~~

Nếu ứng dụng hiểu sai scheme/host của request, có thể sinh:

- Cookie thiếu `Secure` hoặc thuộc tính không đúng;
- redirect về `http://...` thay vì `https://...`;
- absolute URL sai host/port/context path;
- vòng lặp redirect login;
- callback OAuth2/OIDC không khớp redirect URI.

Giải pháp là cấu hình **proxy tin cậy** truyền forwarded headers phù hợp, Spring Boot/Framework xử lý chúng ở phạm vi được phép và xác minh response từ browser. Không chấp nhận forwarded headers giả mạo trực tiếp từ Internet.

### 11.2. Ứng dụng nhiều node và session store

Một phiên được lưu trên instance A nhưng request sau đi tới instance B có thể gây mất session hoặc token:

~~~mermaid
flowchart LR
    B[Browser giữ JSESSIONID] --> L[Load Balancer]
    L --> A[Node A]
    L --> C[Node B]
    A --> S[(Session Store)]
    C --> S
~~~

Có hai cách triển khai phổ biến:

- **Sticky session:** LB cố giữ request của một phiên đi cùng node; có giới hạn khi node failover/scale.
- **Shared session store:** Dùng một cơ chế phân tán như Spring Session với store phù hợp, nhất quán về thời hạn/serializer và cookie across nodes.

Nếu token CSRF được lưu theo `HttpSession`/`WebSession` mà mỗi node dùng session store không đồng nhất, POST có thể trả `403` ngẫu nhiên. Hãy kiểm tra **session resolution, store replication, deployment rollover và cookie scope** thay vì tắt CSRF.

### 11.3. Context path và đường dẫn form

Với ứng dụng deploy tại `/portal`, form có `action="/account/settings"` có thể gửi tới root của host, **không phải** `/portal/account/settings`.

Thymeleaf có thể tạo URL theo context path:

~~~html
<form th:action="@{/account/settings}" method="post">
  <select name="theme">
    <option value="light">Sáng</option>
    <option value="dark">Tối</option>
  </select>
  <button type="submit">Lưu</button>
</form>
~~~

Với cấu hình Spring MVC/Thymeleaf phù hợp, `th:action` cho phép integration request data value processor tự thêm CSRF hidden field. **Kiểm tra HTML render thật**; nếu đã tự thêm một field `_csrf` trong template khác, không thêm trùng.

### 11.4. CORS và SSR same-origin

Một ứng dụng SSR truyền thống thường phục vụ HTML và nhận form **cùng origin**. Thường không cần bật credentialed CORS rộng để form hoạt động.

Nếu một frontend/iframe/SPA khác origin được tích hợp, cần xác định:

- Hai host có cùng site nhưng khác origin không?
- Cookie `SameSite`/`Domain` có cho browser gửi cookie theo ngữ cảnh không?
- CORS có cho phép JavaScript đọc response và gửi header cần thiết không?
- Endpoint có yêu cầu CSRF token đúng phiên không?
- Origin nào thực sự đáng tin? Có cho phép subdomain ít tin cậy không?

CORS không thay CSRF. HTML form đơn giản từ website khác **có thể gửi POST mà không cần được đọc response**, nên không dùng “CORS không cho site ngoài” làm lý do bỏ CSRF.

## 12. Kiểm thử Servlet với MockMvc: trang đọc, form ghi và CSRF

Một bộ kiểm thử SSR không chỉ kiểm tra controller trả HTML 200. Nó phải xác nhận **security filters thực sự được gắn**, form có token, request thiếu/sai token bị chặn, và form có token đúng thực hiện hành động theo quyền của user.

### 12.1. Ma trận chức năng tối thiểu

| ID | Tình huống | Request | Kết quả cần kiểm tra |
|---|---|---|---|
| **SSR-01** | Khách chưa login mở trang tài khoản | `GET /account/settings` không có phiên | Bị chuyển tới login/entry point theo policy; không lộ dữ liệu |
| **SSR-02** | Khách mở trang login | `GET /login` | Form HTML có token CSRF hợp lệ |
| **SSR-03** | Login thiếu CSRF | `POST /login` có credentials, không token | Bị chặn; không tạo session xác thực |
| **SSR-04** | Login có token | `POST /login` có credentials và token | Tới bước authentication; thành công/thất bại tùy credentials |
| **SSR-05** | User xem cài đặt | `GET /account/settings` với session hợp lệ | Trả view đúng và **không ghi dữ liệu** |
| **SSR-06** | User lưu với token đúng | `POST /account/settings` + cookie + token | Qua CSRF, validate và cập nhật; redirect theo PRG |
| **SSR-07** | User lưu thiếu token | `POST /account/settings` + cookie, không token | Từ chối, **không có side effect** |
| **SSR-08** | User lưu token sai | `POST /account/settings` + cookie, token biến đổi | Từ chối, không ghi dữ liệu |
| **SSR-09** | Token của phiên B gửi trong phiên A | POST + cookie A + token B | Bị từ chối với synchronizer token theo phiên |
| **SSR-10** | User logout không token | `POST /logout`, không token | Bị chặn, không logout |
| **SSR-11** | User logout với token | `POST /logout` + token | Logout; phiên cũ không còn được xác thực |
| **SSR-12** | Form mở lâu qua timeout/login mới | POST với token cũ | Bị xử lý theo policy phiên/token, không thực hiện hành động ngoài ý muốn |
| **SSR-13** | Gửi link GET thay đổi trạng thái | `GET /account/settings?theme=dark` | **Không** đổi theme |
| **SSR-14** | Browser link từ site khác | Top-level GET và cross-site form POST | Cookie theo SameSite; POST thiếu token bị chặn nếu nhận được credential |
| **SSR-15** | Ứng dụng qua proxy/nhiều node | Login → GET form → POST ở node khác | Cookie, session và CSRF token nhất quán |

### 12.2. MockMvc: kiểm tra trang login và request không xác thực

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SsrPageServletTests {

    @Autowired MockMvc mvc;

    @Test
    void loginPageContainsCsrfField() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("name=\"_csrf\"")));
    }

    @Test
    void accountPageRequiresAuthentication() throws Exception {
        mvc.perform(get("/account/settings"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Ví dụ giả định custom login page, Thymeleaf template và SecurityFilterChain đã được cấu hình như ở mục 5. `name="_csrf"` là mặc định thông dụng; nếu repository/request handler đổi tên field, điều chỉnh assertion theo cấu hình thực tế.

**Giới hạn:** Kiểm tra HTML chứa tên field chưa đủ chứng minh token có giá trị đúng. Với mức tích hợp cao hơn, lấy giá trị CSRF token từ HTML và submit bằng **cùng session**.

### 12.3. MockMvc: token đúng, thiếu và sai

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SsrFormServletTests {

    @Autowired MockMvc mvc;

    @Test
    void validCsrfTokenAllowsPostRedirectGet() throws Exception {
        mvc.perform(post("/account/settings")
                .with(user("alice"))
                .with(csrf())
                .param("theme", "dark"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account/settings"));
    }

    @Test
    void missingCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/account/settings")
                .with(user("alice"))
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/account/settings")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }
}
~~~

`with(user("alice"))` tạo **mock authentication** để tránh nhầm lỗi chưa đăng nhập với lỗi CSRF. `with(csrf())` là helper test token, **không chạy lại luồng GET HTML → browser đọc token → gửi cookie thực**. Test phải có endpoint/service phù hợp và dữ liệu fixture riêng.

### 12.4. Kiểm tra không có side effect ở negative cases

Một POST thiếu token trả `403` nhưng database đã thay đổi vẫn là lỗi bảo mật. Sau mỗi negative test, cần kiểm tra:

~~~text
Trước:
    theme(Alice) = "light"

Gửi POST /account/settings dưới phiên Alice, thiếu CSRF token.

Phản hồi:
    403 theo policy test.

Sau:
    theme(Alice) vẫn là "light"
    không có event SettingsChanged được phát
    không có transaction nghiệp vụ được commit
~~~

Có thể dùng database test, fake service hoặc event recorder để xác nhận. `@SpringBootTest`/MockMvc không tự tạo assertion nghiệp vụ này. Khi chạy song song, mỗi test cần dữ liệu độc lập, không dựa vào thứ tự các test method.

### 12.5. Test thật của phiên và token

Một test cao hơn nên:

1. GET `/login`, lấy token và cookie pre-authentication nếu được tạo.
2. POST `/login` với cùng cookie, token và tài khoản test hợp lệ.
3. Theo redirect, lấy cookie phiên sau login và GET `/account/settings`.
4. Lấy CSRF token **mới** từ form theo đúng cách render; token có thể masked.
5. POST dữ liệu cùng cookie phiên và token mới.
6. Thử lặp POST với token thiếu/sai, xác nhận dữ liệu không đổi.
7. Logout với token hợp lệ; gửi request dùng cookie cũ, xác nhận không còn authenticated session.

Trong một test `MockMvc`, có thể dùng `MockHttpSession` hoặc cookie/session API thích hợp để giữ state giữa các bước. Nếu muốn đo chính xác **hành vi cookie của browser** và SameSite, dùng browser automation thực thay vì trông chờ helper MockMvc mô phỏng toàn bộ.

## 13. Kiểm thử WebFlux với WebTestClient

Với ứng dụng Reactive ở mục 10, có thể kiểm tra filter chain bằng `spring-security-test`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SsrReactiveFormTests {

    @Autowired ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void validTokenAllowsPostAndRedirect() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/account/settings")
            .body(BodyInserters.fromFormData("theme", "dark"))
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void missingTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/account/settings")
            .body(BodyInserters.fromFormData("theme", "dark"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/account/settings")
            .header("X-CSRF-TOKEN", "invalid-token")
            .body(BodyInserters.fromFormData("theme", "dark"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Đoạn test giả định handler `POST /account/settings` trả redirect khi cập nhật thành công, có service/fixture hợp lệ và CSRF request handler nhận header `X-CSRF-TOKEN`. Khi dùng cookie repository hoặc request handler tùy chỉnh, phải test đúng tên header.

`mutateWith(mockUser("alice"))` và `mutateWith(csrf())` giúp test CSRF web filter nhưng **không chứng minh WebSession cookie được tạo/luân phiên đúng trong browser**. Cần test E2E hoặc HTTP integration giữ cookie thật cho bước đó.

### 13.1. Kiểm thử logout Reactive

Thiết kế riêng các trường hợp:

- `POST /logout` đã login nhưng thiếu CSRF → không được logout.
- `POST /logout` đã login với token đúng → dọn security context theo cấu hình.
- GET một tài nguyên bảo vệ bằng **cookie phiên trước logout** → không còn quyền truy cập nếu logout hoàn tất.
- Nếu yêu cầu chính sách là **hủy toàn bộ WebSession**, kiểm tra riêng trạng thái WebSession sau logout; khi cần, cấu hình thêm handler tương ứng.

Không khẳng định logout đã hoàn chỉnh chỉ vì API trả một HTTP redirect.

## 14. Kiểm thử end-to-end trên trình duyệt thật

### 14.1. Kịch bản chuẩn

Trong môi trường được phép, thực hiện:

1. Mở `GET /login` trong **browser context mới**.
2. Xem HTML đã render: tên field CSRF, token, `action`, `method`, URL chứa context path đúng.
3. Đăng nhập bằng tài khoản test. Quan sát cookie `JSESSIONID` hoặc cookie session thực tế, bao gồm `HttpOnly`, `Secure`, `SameSite`, `Domain`/`Path`.
4. Theo redirect đến trang đã đăng nhập. Kiểm tra `SecurityContext` phía server hoặc một endpoint hiển thị danh tính hiện tại; không đọc thẳng session ID bằng JavaScript.
5. GET form thay đổi theme, gửi POST hợp lệ và xác nhận **PRG**: browser được chuyển về GET, theme đã cập nhật.
6. Lặp một POST với **token bị xóa** nhưng session cookie vẫn tồn tại; phải bị CSRF chặn và không thay đổi dữ liệu.
7. Lặp một POST với **token bị sửa**; phải bị chặn tương tự.
8. Mở browser context B tạo session khác, thử dùng token B với cookie A; phải bị từ chối khi repository token gắn theo phiên.
9. Đăng xuất qua POST có token, thử lại cookie cũ và kiểm tra không còn phiên đăng nhập.
10. Mở form lâu, logout/login hoặc chờ session timeout, rồi submit; bảo đảm có phản hồi an toàn và đường hồi phục rõ ràng.

### 14.2. Kịch bản SameSite/CORS

Đối với mô hình multi-origin, cần có các website test riêng:

~~~text
https://app.example.test          Ứng dụng SSR
https://blog.example.test         Cross-origin nhưng có thể same-site
https://outside.other.test        Cross-site
~~~

Hãy xác nhận bằng **Network DevTools**:

- Request từ blog đến app có gửi cookie session không? SameSite Strict/Lax vẫn có thể cho cookie với same-site request.
- Cross-site top-level GET có gửi cookie Lax không? Nếu có, GET phải không gây side effect.
- Cross-site form POST có gửi cookie hay không tùy chính sách? Nếu cookie có mặt, server phải chặn request thiếu token.
- CORS error là do preflight hoặc quyền đọc response, **không tự chứng minh** CSRF filter đã từ chối POST.
- Nếu chạy qua `https://...`, `Secure` và forwarded headers có hoạt động đúng không?

Các hostname trên là **mô hình phục vụ test**; cần DNS/hosts, TLS certificate và mapping phù hợp. Không thử khai thác có tác động lên dữ liệu production.

### 14.3. Những thông tin nên thu thập

| Quan sát | Giá trị chẩn đoán |
|---|---|
| HTTP method/path | GET hay POST, URL có context path đúng không |
| Status/redirect target | Chặn ở login, CSRF, authorization hay validation |
| `Set-Cookie` có thuộc tính gì | Cookie session được phát đúng không |
| Header `Cookie` của POST | Browser có tự gửi session cookie không |
| Hidden CSRF field/header | Có/không, tên field/header, nhưng **không log token thật** |
| Authentication principal/authorities | Đúng user và quyền theo policy chưa |
| Session store/node | Request có sử dụng đúng phiên/token không |
| Database trước/sau | Request thiếu/sai token có gây side effect không |
| CSP/HSTS/header response | Lớp bảo vệ browser được phát thật hay chỉ cấu hình trên giấy |
| CORS preflight | Có request OPTIONS; POST thật có đến server không |

## 15. Chẩn đoán những xung đột phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| `GET /login` hiển thị nhưng `POST /login` trả `403` | Form không có token, token sai/khác phiên | Xem HTML render, field `_csrf` và session cookie giữa GET/POST |
| POST sau login đầu tiên trả `403` | CSRF token trước login bị xóa/rotate; SPA vẫn dùng token cũ | Lấy token mới sau login; với SSR GET trang mới thường render token mới |
| Form POST trả `404` sau deploy dưới `/portal` | `action="/..."` bỏ mất context path | Tạo URL bằng template engine, kiểm tra URL trong Network |
| POST có token nhưng vẫn `403` | Thiếu quyền, token sai format/raw/masked hoặc security chain khác | Phân biệt CSRF với authorization; kiểm tra request handler |
| Cookie login không được gửi | `Secure`, `SameSite`, `Domain`, `Path`, browser policy hoặc proxy | Kiểm tra Set-Cookie và Cookie trong browser |
| Redirect từ HTTPS về HTTP | Proxy TLS termination/forward headers sai | Sửa proxy tin cậy và Spring forwarding configuration |
| Login redirect lặp | Cookie session không tồn tại hoặc không được gửi, authentication không được lưu | Kiểm tra session store, proxy, cookie và SecurityContextRepository |
| Lỗi ngẫu nhiên khi scale nhiều node | Phiên/token chỉ có trên node A, node B không nhận | Kiểm tra shared store/sticky sessions và tương thích serializer |
| GET URL thay đổi dữ liệu mà không cần token | GET nằm trong safe methods mặc định | Chuyển hành động sang POST/PUT/PATCH/DELETE có bảo vệ |
| CORS bị chặn khi submit từ origin khác | Form/API tích hợp multi-origin không đúng policy | Phân biệt CORS/SameSite/CSRF; không mở wildcard credentialed CORS |
| `GET /logout` không tự đăng xuất | GET chỉ có thể hiển thị trang xác nhận khi CSRF bật | Dùng form POST có token |
| Logout redirect rồi cookie cũ vẫn dùng được | Session/auth context chưa dọn, remember-me hoặc WebSession policy khác | Test endpoint bảo vệ sau logout, xem handler |
| CSP chặn inline script khi đưa lên production | Chính sách `script-src` không cho đoạn inline | Chuyển script sang nguồn quản lý hoặc dùng nonce/hash phù hợp |
| Trang mở nhiều tab hiển thị token cũ | Login/logout/session timeout ở tab khác | Hướng dẫn reload form, lấy token theo session mới |
| `MockMvc` `with(csrf())` pass nhưng browser vẫn fail | Tích hợp template/URL/cookie thật bị lỗi | Test GET form → giữ session → POST qua browser |

### 15.1. Phân biệt lỗi HTTP

- `401 Unauthorized` thường liên quan thiếu/thất bại xác thực trong một API, nhưng với form login truyền thống có thể là **redirect**.
- `403 Forbidden` có thể do **CSRF token** hoặc **authorization**; chỉ nhìn status không đủ xác định nguyên nhân.
- `400 Bad Request` có thể do validation, parser, method/body không phù hợp.
- CORS error trong browser có thể xảy ra trước khi request POST thật được gửi, hoặc response không được JavaScript đọc.
- `5xx` là lỗi server; không nên dùng catch-all để nuốt ngoại lệ bảo mật rồi vẫn ghi dữ liệu.

Khi ghi log, **không đưa session ID, access token hoặc CSRF token thô vào log**. Chỉ cần phương thức, URL, chain áp dụng, token có/không, tên field/header, exception class và kết quả được phân quyền.

## 16. Checklist triển khai ứng dụng SSR có form và cookie

| Hạng mục | Câu hỏi xác minh |
|---|---|
| HTML SSR | GET chỉ đọc và render đúng form, dữ liệu từ user được escape đúng ngữ cảnh? |
| Form method | Các hành động ghi đều là POST/PUT/PATCH/DELETE, không dùng GET có side effect? |
| CSRF | Login, logout, chỉnh sửa hồ sơ và các unsafe requests nhận token hợp lệ? |
| Token render | Hidden field/header đúng tên, không hardcode, không dùng session ID? |
| Session cookie | `Secure`, `HttpOnly`, `SameSite`, `Path`/`Domain` phù hợp? |
| Session lifecycle | Có session fixation protection, timeout và invalidation/logout thích hợp? |
| Xác thực | URL login processing được security filter xử lý, user provider đúng? |
| Phân quyền | Route và từng bản ghi nghiệp vụ được kiểm tra quyền? |
| PRG | POST thành công redirect, refresh không tự gửi lại POST? |
| Input | Có validation server-side; không tin hidden fields/disabled input của client? |
| XSS | Template auto-escaping, DOM sink an toàn, CSP phù hợp? |
| HTTPS/HSTS | HTTPS và reverse proxy forwarding đúng; cookie Secure thực sự được phát? |
| CORS | Không mở credentialed CORS rộng chỉ để form same-origin hoạt động? |
| HTTP firewall | Không tự vô hiệu hóa các giới hạn request-path/method để “sửa” URL sai? |
| Multi-node | Có chiến lược session store/affinity và khả năng scale/failover? |
| Testing | Có positive + missing/invalid CSRF, token sai phiên, logout, no-side-effects? |

## 17. Câu hỏi tự đánh giá

**Câu 1.** Tại sao server-rendered form dùng cookie phiên thường cần CSRF token, dù cookie đã có `HttpOnly`?

**Đáp án:** `HttpOnly` ngăn JavaScript thông thường đọc cookie nhưng browser vẫn có thể tự gửi cookie khi một request đủ điều kiện được kích hoạt. CSRF token là giá trị client hợp lệ chủ động gửi để server phân biệt nhiều request giả mạo không biết token.

**Câu 2.** Trong ứng dụng MVC + Thymeleaf, nên tạo POST controller `/login` để xử lý username/password không?

**Đáp án:** Với `formLogin()` và `loginProcessingUrl("/login")`, Spring Security form-login filter xử lý POST. Ứng dụng chỉ cần cung cấp **GET /login** khi dùng custom login page. Không tạo controller POST cạnh tranh nếu không có thiết kế custom authentication đặc biệt.

**Câu 3.** Một form mở từ trước khi login lại gửi POST và trả `403`. Đây có nhất thiết là lỗi bảo mật của framework không?

**Đáp án:** Không. Token hoặc phiên cũ có thể không còn hợp lệ sau authentication/logout/timeout. Cần cấp token theo phiên mới và xử lý UX tải lại form, không tắt CSRF.

**Câu 4.** PRG đã giảm gửi lại POST khi Refresh; vì sao vẫn cần CSRF token?

**Đáp án:** PRG là mẫu điều hướng để giảm resubmit tình cờ. Nó không ngăn một website khác tạo POST chứa cookie phiên. CSRF token bảo vệ tính hợp lệ của request.

**Câu 5.** Với WebFlux, có thể dùng `HttpSessionCsrfTokenRepository` như ở MVC không?

**Đáp án:** Không. WebFlux dùng cơ chế Reactive như `WebSessionServerCsrfTokenRepository` và `CsrfWebFilter`; tên API/filter khác Servlet, dù mối đe dọa cookie và form giống nhau.

**Câu 6.** Một app chạy qua HTTPS reverse proxy nhưng redirect login lại trỏ `http://...`. Có thể do đâu?

**Đáp án:** App có thể chưa nhận đúng scheme/host từ forwarded headers hoặc proxy cấu hình sai. Cần kiểm tra proxy đáng tin, forwarding strategy, TLS termination và URL rendering thực tế.

**Câu 7.** Ứng dụng có CSP, HSTS, cookie SameSite và CSRF. Vì sao vẫn cần encode dữ liệu hiển thị bằng Thymeleaf?

**Đáp án:** Nếu dữ liệu không tin cậy được render thành script cùng origin, XSS có thể đọc/sử dụng CSRF token và gửi request trong phiên. CSP là lớp hỗ trợ, không thay output encoding/sanitization.

**Câu 8.** Tại sao `MockMvc` test dùng `with(user())` và `with(csrf())` không chứng minh session cookie SameSite hoạt động?

**Đáp án:** Đó là helper mô phỏng principal và token ở tầng test server, không tự chạy thuật toán cookie và policy cross-site của browser. Cần kiểm thử browser thật với HTTPS và các origin test phù hợp.

## Kết luận

Ứng dụng **render phía máy chủ với HTML form và session cookie** là kiến trúc rất phù hợp với Spring Security, nhưng chỉ an toàn khi các ranh giới được thiết kế đúng. Browser **tự gửi cookie phiên**, Spring Security dùng phiên để quản lý ngữ cảnh xác thực, còn các form **chủ động gửi CSRF token** để bảo vệ những yêu cầu có tác động như login, cập nhật dữ liệu và logout. Những hành động đó dùng POST (hoặc phương thức ghi phù hợp), trong khi GET chỉ đọc và render.

Ở **Servlet/Spring MVC**, các thành phần trọng tâm gồm `HttpSecurity`, `SecurityFilterChain`, `HttpSession`, `CsrfFilter`, `@Controller` và Thymeleaf. Ở **Reactive/WebFlux**, chúng tương ứng với `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebSession`, `CsrfWebFilter` và view/reactive controller. **PRG** làm luồng lưu form dễ sử dụng hơn nhưng không thay CSRF; **SameSite/HttpOnly/Secure, CSP và HSTS** bổ sung các lớp cookie, script và HTTPS chứ không kiểm chứng thay token.

Khi đưa vào production, phải kiểm tra **cookie thật, form thật, token thật, session lifecycle thật và reverse proxy thật**; các helper test `MockMvc`/`WebTestClient` hữu ích nhưng không thay browser E2E. Đây là nền tảng để tích hợp các lớp phòng vệ HTTP một cách nhất quán trong module **SPRING_SECURITY_HTTP_PROTECTION**.

## Tài liệu tham khảo

- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF token, form handling, repository, login/logout.
- [Spring Security — Servlet Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): cấu hình form login và trang login.
- [Spring Security — Handling Logouts (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): logout handler và cơ chế POST với CSRF.
- [Spring Security — CSRF Protection (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF web filter và repository của Reactive.
- [Spring Security — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html): logout và xử lý WebSession/security context.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): CSP, HSTS và header bảo vệ trình duyệt.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): SameSite, Secure, HttpOnly và scope cookie.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token và phòng vệ nhiều lớp.
- [OWASP — XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): output encoding và xử lý dữ liệu không đáng tin cậy.
