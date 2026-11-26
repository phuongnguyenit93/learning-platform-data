# Đưa token vào nút đăng nhập và form đăng xuất

Trong module `SPRING_SECURITY_HTTP_PROTECTION`, hai thao tác quen thuộc nhất trên giao diện là **đăng nhập** và **đăng xuất** cũng là các thao tác HTTP cần phòng vệ CSRF khi ứng dụng dùng cơ chế xác thực qua cookie/phiên. Cấu hình Spring Security có thể tự kiểm tra CSRF cho `POST /login` và `POST /logout`, nhưng nếu lập trình viên viết giao diện tùy chỉnh, HTML phải thực sự gửi kèm token mà Spring Security mong đợi.

Tên bài nhắc tới **nút đăng nhập** và **form đăng xuất**, nhưng cần hiểu chính xác: **token được đặt trong dữ liệu của form gửi request**, thông thường là một `<input type="hidden">` nằm trong `<form>`; bản thân `<button>` chỉ kích hoạt submit. Bài học trình bày cơ chế trên Spring MVC/Servlet, các biến thể với template engine và đối chiếu WebFlux/Reactive.

## 1. Mục tiêu học tập

Hoàn thành bài học, người học có thể:

- Giải thích tại sao cả **login CSRF** lẫn **logout CSRF** đều đáng quan tâm, dù trang đăng nhập chưa yêu cầu người dùng được xác thực.
- Phân biệt `GET /login` để hiển thị giao diện, `POST /login` để thực hiện xác thực và `POST /logout` để đăng xuất.
- Cấu hình `SecurityFilterChain` và tạo trang đăng nhập tùy chỉnh có trường `username`, `password` và CSRF token.
- Xây nút **Đăng xuất** bằng một form POST, kể cả khi muốn đặt nút nằm ngoài vị trí hiển thị của form.
- So sánh cách thêm token tự động của Thymeleaf với JSP, form HTML thuần và JavaScript.
- Hiểu việc vô hiệu hóa token cũ sau xác thực/đăng xuất và kiểm thử các tình huống hợp lệ, thiếu hoặc sai token.
- Nhận biết khác biệt trong WebFlux, nơi token có thể được cung cấp qua `Mono<CsrfToken>`.

## 2. Vì sao form đăng nhập và đăng xuất cần chống CSRF?

### 2.1. Login CSRF: ép trình duyệt đăng nhập vào tài khoản khác

Một kịch bản ít được chú ý là kẻ tấn công có tài khoản hợp lệ trên ứng dụng, rồi dụ trình duyệt nạn nhân gửi request đăng nhập bằng thông tin của **tài khoản kẻ tấn công**.

Nếu ứng dụng nhận request login từ bên ngoài mà không xác thực nguồn gốc bằng CSRF token, nạn nhân có thể vô tình sử dụng ứng dụng trong phiên của tài khoản do kẻ tấn công kiểm soát. Những dữ liệu nạn nhân nhập sau đó có thể được lưu vào tài khoản ấy. Đây là rủi ro **login CSRF**; nó không đòi hỏi kẻ tấn công biết mật khẩu thật của nạn nhân.

Vì vậy, dù endpoint `POST /login` phải được phép truy cập khi **chưa đăng nhập**, nó vẫn nên được bảo vệ trước CSRF trong ứng dụng dùng cookie phiên.

### 2.2. Logout CSRF: ép người dùng kết thúc phiên

Nếu đăng xuất được thực hiện bằng `GET /logout` và ứng dụng không yêu cầu xác nhận request, một trang khác có thể lôi kéo trình duyệt gửi GET để kết thúc phiên của người dùng. Đây là hành vi thay đổi trạng thái không nên xảy ra qua phương thức GET.

Với CSRF bật theo mặc định, Spring Security sử dụng **POST** cho hành vi logout được bảo vệ. Một đường dẫn GET `/logout` trong một số cấu hình mặc định có thể hiển thị **trang xác nhận đăng xuất**, nhưng không nên được hiểu là request đã đăng xuất. Hành vi chính xác còn phụ thuộc cấu hình `LogoutFilter`/trang logout của ứng dụng.

### 2.3. Luồng request

```text
Trình duyệt                     Spring Security                 Ứng dụng
     |                                |                            |
     | GET /login                     |                            |
     |------------------------------->|----> controller/view ------>|
     |<--- HTML form + CSRF token ----|<---------------------------|
     |                                |                            |
     | POST /login                    |                            |
     | username + password + _csrf    |                            |
     |------------------------------->|                            |
     |                                | 1. CsrfFilter kiểm tra      |
     |                                | 2. Authentication filter   |
     |<--------- Redirect ------------|                            |
     |                                |                            |
     | GET /dashboard                 |                            |
     |------------------------------->|----> render trang -------->|
     |<--- HTML có form logout -------|<---------------------------|
     |                                |                            |
     | POST /logout + _csrf           |                            |
     |------------------------------->| 1. Kiểm tra CSRF            |
     |                                | 2. LogoutFilter xử lý       |
     |<------ /login?logout ----------|                            |
```

Thứ tự quan trọng: CSRF có thể từ chối request với **403 Forbidden trước khi** bộ lọc xác thực nhận username/password hoặc trước khi logout handler được chạy. Có token hợp lệ cũng chưa đảm bảo đăng nhập thành công: mật khẩu vẫn có thể sai, tài khoản có thể bị khóa hoặc quy tắc bảo mật khác có thể từ chối.

## 3. Cấu hình Spring Security Servlet cho cả hai thao tác

Một ví dụ hoàn chỉnh dùng Spring Boot với Spring MVC, Spring Security và Thymeleaf. Dependency chính:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
implementation 'org.springframework.boot:spring-boot-starter-security'
implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
```

Dùng cấu hình minh họa sau:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error", "/assets/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginPage("/login")
                        .defaultSuccessUrl("/dashboard", true)
                        .permitAll())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutSuccessUrl("/login?logout")
                        .permitAll())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails demo = User.withUsername("learner")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(demo);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
```

Tài khoản `learner / demo-pass` chỉ phục vụ bài thực hành nội bộ; trong hệ thống thực tế phải dùng nguồn người dùng, quy trình cấp mật khẩu và chính sách xác thực phù hợp. Không đưa thông tin xác thực mẫu hoặc mật khẩu thật vào ứng dụng triển khai thực.

Đọc cấu hình theo ý nghĩa:

| Cấu hình | Tác động |
| --- | --- |
| `requestMatchers("/login", ...).permitAll()` | Người chưa xác thực được truy cập trang login; quy tắc authorization không ngăn hiển thị form. |
| `formLogin(...loginPage("/login"))` | Dùng giao diện đăng nhập riêng thay vì trang login tự sinh của Spring Security. |
| `defaultSuccessUrl("/dashboard", true)` | Sau đăng nhập thành công luôn chuyển về dashboard trong bài thực hành. |
| `logoutUrl("/logout")` | Định nghĩa endpoint để `LogoutFilter` thực hiện logout. |
| `logoutSuccessUrl("/login?logout")` | Điều hướng sau logout thành công. |
| `csrf(Customizer.withDefaults())` | Duy trì cơ chế CSRF mặc định; POST login và logout vẫn phải có token hợp lệ. |

Đặc biệt, **`permitAll()` không vô hiệu hóa `CsrfFilter`**. Cho phép một người chưa đăng nhập gửi yêu cầu login không có nghĩa cho phép họ bỏ qua CSRF.

Trong ví dụ này, `UsernamePasswordAuthenticationFilter` xử lý `POST /login` với hai tham số tên mặc định là `username` và `password`. **Không cần tạo `@PostMapping("/login")` trong MVC controller** chỉ để xác thực bằng form mặc định; request được xử lý trong Spring Security filter chain. Nếu bạn cấu hình `loginProcessingUrl` hoặc tên tham số khác, phải cập nhật `action` và input tương ứng.

## 4. Trang login tùy chỉnh: token nằm trong form của nút Đăng nhập

### 4.1. Controller hiển thị trang login

```java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/login")
    String login() {
        return "login";
    }

    @GetMapping("/dashboard")
    String dashboard() {
        return "dashboard";
    }
}
```

`GET /login` trả về template; `POST /login` sẽ do Spring Security xử lý. Nên để đường dẫn GET chạy qua security filter chain thông thường để request được cung cấp CSRF token. Nếu dùng cơ chế `web.ignoring()` bỏ qua toàn bộ security filters cho `/login`, trang login có thể không nhận được token. `permitAll()` giữ request trong filter chain nên phù hợp hơn trong tình huống này.

### 4.2. Thymeleaf tự chèn hidden CSRF input

Tạo `src/main/resources/templates/login.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
    <h1>Đăng nhập</h1>

    <p th:if="${param.error}">Tên đăng nhập hoặc mật khẩu không hợp lệ.</p>
    <p th:if="${param.logout}">Bạn đã đăng xuất.</p>

    <form th:action="@{/login}" method="post">
        <label for="username">Tên đăng nhập</label>
        <input id="username"
               name="username"
               type="text"
               autocomplete="username"
               required>

        <label for="password">Mật khẩu</label>
        <input id="password"
               name="password"
               type="password"
               autocomplete="current-password"
               required>

        <button type="submit">Đăng nhập</button>
    </form>
</body>
</html>
```

**Không cần tự viết input `_csrf`** trong template này: khi Thymeleaf chạy với Spring MVC và Spring Security tích hợp đúng, `th:action` cho form POST sử dụng `RequestDataValueProcessor` của Spring MVC. Spring Security cung cấp `CsrfRequestDataValueProcessor` để thêm trường CSRF vào HTML đã render.

Ví dụ **HTML trả về** có thể tương tự:

```html
<form action="/login" method="post">
    <label for="username">Tên đăng nhập</label>
    <input id="username" name="username" type="text" required>

    <label for="password">Mật khẩu</label>
    <input id="password" name="password" type="password" required>

    <button type="submit">Đăng nhập</button>
    <input type="hidden" name="_csrf" value="token-duoc-render-tu-request">
</form>
```

Đoạn này chỉ minh họa. Giá trị token thực do Spring Security sinh ra; tên tham số thường là `_csrf`, nhưng có thể thay đổi theo `CsrfTokenRepository` và cấu hình. Hãy kiểm tra **Network → Response** hoặc **View Page Source** của `GET /login` để xem HTML thực sự được render.

**Vì sao token không nằm trên `<button>`?** Khi nhấn nút submit, trình duyệt gửi dữ liệu của các form controls thuộc cùng một `<form>`. Một hidden input có `name` và `value` trong form sẽ được gửi cùng username/password. Đặt token trong thuộc tính HTML tự đặt như `data-csrf` trên nút không tự làm token xuất hiện trong body request.

### 4.3. Khi render thủ công với Thymeleaf

Với form HTML thuần không kích hoạt cơ chế `RequestDataValueProcessor`, có thể dùng thuộc tính request `_csrf`:

```html
<!-- Ví dụ xử lý thủ công: chỉ dùng khi form chưa tự có hidden CSRF -->
<form action="/login" method="post">
    <input name="username">
    <input name="password" type="password">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Đăng nhập</button>
</form>
```

Form ở ví dụ thủ công dùng action `/login` cho ứng dụng chạy ở root; nếu deploy dưới context path khác cần tạo URL tương ứng. Ưu tiên `th:action="@{/login}"` khi dùng Thymeleaf và kiểm tra có token tự sinh trước khi quyết định chèn thủ công.

Kể từ Spring Security 6, token Servlet được xử lý trì hoãn và mặc định có cơ chế che token chống BREACH. **Giá trị hidden input đã render có thể thay đổi giữa các lượt GET** dù token lưu trong phiên không đổi. Dùng giá trị từ request hiện hành, không hardcode, không sao chép token từ request của người dùng khác và không lấy giá trị thô từ repository rồi tự chèn vào HTML.

### 4.4. Khi dùng trang đăng nhập mặc định

Nếu chỉ cấu hình `formLogin(Customizer.withDefaults())` và không chỉ định `loginPage`, Spring Security có thể cung cấp trang đăng nhập mặc định bằng `DefaultLoginPageGeneratingFilter`. Trang mặc định được tạo cùng cơ chế form và CSRF khi bảo vệ CSRF đang bật; người học chỉ cần tự thêm token khi **thay thế bằng form đăng nhập của chính ứng dụng**.

Tránh dùng `<form method="get" action="/login">`: GET chỉ dùng để lấy giao diện, không gửi mật khẩu hay thực hiện xác thực. Username/password phải được gửi qua POST trên kết nối HTTPS.

## 5. Form đăng xuất: POST thực sự nằm sau nút Đăng xuất

### 5.1. Dashboard với Thymeleaf

Tạo `src/main/resources/templates/dashboard.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Dashboard</title>
</head>
<body>
    <h1>Chào mừng</h1>

    <form th:action="@{/logout}" method="post">
        <button type="submit">Đăng xuất</button>
    </form>
</body>
</html>
```

Trong HTML trả về, form logout phải có hidden CSRF input:

```html
<form action="/logout" method="post">
    <button type="submit">Đăng xuất</button>
    <input type="hidden" name="_csrf" value="token-tu-trang-hien-tai">
</form>
```

Đây là cách thiết kế nhỏ gọn và đáng tin cậy: nút submit nằm trong form POST mà Spring Security đã chèn token. Với cấu hình logout mặc định và CSRF bật, request `POST /logout` sẽ đi qua `CsrfFilter` rồi `LogoutFilter`, thực hiện các logout handlers phù hợp và chuyển tới `/login?logout`.

Mặc định, các cơ chế logout của Spring Security có thể xóa authentication, làm mất hiệu lực `HttpSession` và xử lý security context. Tác dụng cụ thể còn phụ thuộc cấu hình session và các `LogoutHandler` tùy chỉnh. Khi người dùng quay lại login page, trang mới cần được render với token thích hợp với trạng thái phiên mới.

### 5.2. Đặt nút đăng xuất trên thanh điều hướng

Bạn có thể đặt một form ít gây ảnh hưởng bố cục và gắn nút hiển thị ở nơi khác thông qua thuộc tính HTML `form`:

```html
<!-- Form vẫn hiện diện trong tài liệu và được Thymeleaf xử lý -->
<form id="logoutForm" th:action="@{/logout}" method="post"></form>

<nav aria-label="Tài khoản">
    <button type="submit" form="logoutForm">Đăng xuất</button>
</nav>
```

Nút nằm ngoài phần tử `<form>` nhưng vẫn liên kết với form có `id="logoutForm"`. Hidden CSRF input **phải thuộc form được submit**, không cần đặt trong nút. Kiểm tra HTML cuối cùng để chắc rằng renderer thêm token vào đúng form.

Ví dụ nút đăng xuất **không phù hợp**:

```html
<!-- Không dùng GET để thực hiện thay đổi trạng thái logout -->
<a href="/logout">Đăng xuất</a>

<!-- Thiếu POST form + CSRF token -->
<button type="button" onclick="location.href='/logout'">Đăng xuất</button>
```

Với cấu hình mặc định có CSRF, các liên kết GET trên thường **không trực tiếp đăng xuất**; có thể dẫn tới trang xác nhận. Nếu thay đổi cấu hình để GET thực hiện logout, việc tải liên kết, preview hoặc điều hướng qua trang khác dễ kích hoạt một hành vi đổi trạng thái ngoài ý định.

### 5.3. Nút động và JavaScript

Nếu UI có nút logout do JavaScript điều khiển, vẫn có thể submit form POST chuẩn:

```html
<form id="logoutForm" th:action="@{/logout}" method="post"></form>
<button type="button" id="logoutButton">Đăng xuất</button>

<script>
    document.getElementById("logoutButton").addEventListener("click", () => {
        document.getElementById("logoutForm").requestSubmit();
    });
</script>
```

`requestSubmit()` kích hoạt quy trình submit theo form, cùng dữ liệu input do Thymeleaf render. Tránh tự tạo request POST thủ công nếu không cần, vì lúc ấy bạn phải tự chuyển token sang body hoặc header thích hợp.

Nếu buộc dùng `fetch` để logout không tải lại toàn trang, lấy token và tên header từ server, ví dụ Thymeleaf:

```html
<meta name="_csrf" th:content="${_csrf.token}">
<meta name="_csrf_header" th:content="${_csrf.headerName}">

<button type="button" id="logoutFetchButton">Đăng xuất</button>
<script>
    document.getElementById("logoutFetchButton").addEventListener("click", async () => {
        const token = document.querySelector('meta[name="_csrf"]').content;
        const headerName = document.querySelector('meta[name="_csrf_header"]').content;

        const response = await fetch("/logout", {
            method: "POST",
            credentials: "same-origin",
            headers: { [headerName]: token }
        });

        if (!response.ok) {
            throw new Error("Logout thất bại: " + response.status);
        }
        // Fetch có thể theo redirect nội bộ; tự điều hướng UI sau khi thành công.
        window.location.assign("/login?logout");
    });
</script>
```

**Lưu ý khi dùng `fetch`:** Ví dụ giả định ứng dụng chạy tại context root và token/header đã được expose trong HTML Thymeleaf. Nếu có context path khác, tạo URL logout/login từ server thay vì hardcode. Response redirect trong `fetch` không đồng nghĩa trình duyệt tự chuyển trang; ứng dụng phải quản lý điều hướng. Trong môi trường dùng redirect tùy chỉnh hoặc gọi cross-origin, cần rà lại credential mode, CORS, cookie và xử lý lỗi.

Ở nhiều ứng dụng render phía máy chủ, **form POST bình thường đơn giản và ít phụ thuộc JavaScript hơn**.

## 6. Sử dụng JSP và các template engine khác

### 6.1. Spring MVC JSP với thẻ Spring Security

Khi dùng JSP HTML thuần, có thể chèn token bằng thẻ `<sec:csrfInput />` của artifact `spring-security-taglibs`:

```jsp
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<%@ taglib prefix="sec" uri="http://www.springframework.org/security/tags" %>

<c:url var="loginUrl" value="/login"/>
<c:url var="logoutUrl" value="/logout"/>

<!-- Trang login -->
<form action="${loginUrl}" method="post">
    <label for="username">Tên đăng nhập</label>
    <input id="username" name="username">
    <label for="password">Mật khẩu</label>
    <input id="password" name="password" type="password">
    <sec:csrfInput />
    <button type="submit">Đăng nhập</button>
</form>

<!-- Đặt trên một trang đã đăng nhập -->
<form action="${logoutUrl}" method="post">
    <sec:csrfInput />
    <button type="submit">Đăng xuất</button>
</form>
```

`<sec:csrfInput />` tạo hidden input CSRF nếu CSRF đang được bật. Với JSP dùng `<form:form>` của Spring MVC, CSRF có thể được tích hợp tự động thông qua `RequestDataValueProcessor`; đừng đặt `<sec:csrfInput />` thêm vào form đã tự sinh input.

Với dự án Java EE/JSP cũ, URI của JSTL có thể là `http://java.sun.com/jsp/jstl/core`; ví dụ trên dành cho nền Jakarta tương ứng. Hãy đảm bảo taglib và servlet container dùng cùng thế hệ Jakarta/Java EE.

### 6.2. Form JSP thuần dùng request attribute

Khi không có JSP security taglib, có thể lấy tham số và token từ thuộc tính request `_csrf`:

```jsp
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<c:url var="logoutUrl" value="/logout"/>

<form action="${logoutUrl}" method="post">
    <input type="hidden"
           name="${_csrf.parameterName}"
           value="${_csrf.token}">
    <button type="submit">Đăng xuất</button>
</form>
```

Nguyên tắc này cũng áp dụng cho form login HTML thuần trong JSP. **Không hardcode token** và không dùng cùng một token chuỗi cố định cho tất cả phiên.

### 6.3. FreeMarker, Mustache hoặc renderer tùy biến

Những engine không tự gọi cơ chế `RequestDataValueProcessor` cần nhận token từ controller/request model. Trong Servlet, `CsrfToken` có thể được Spring Security expose dưới request attribute `_csrf` hoặc khóa `CsrfToken.class.getName()`.

Ví dụ controller chuyển token mà request đang expose vào model:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class ManualLoginController {

    @GetMapping("/manual-login")
    String manualLogin(HttpServletRequest request, Model model) {
        CsrfToken csrf = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());

        if (csrf == null) {
            throw new IllegalStateException("CSRF token chưa được cung cấp");
        }

        model.addAttribute("csrfParam", csrf.getParameterName());
        model.addAttribute("csrfValue", csrf.getToken());
        return "manual-login";
    }
}
```

`/manual-login` là URL GET để render **giao diện**; nếu muốn dùng route này trong cấu hình `loginPage`, cần cấu hình khớp endpoint. Form trong template vẫn có thể POST tới `/login` nếu đó là `loginProcessingUrl` đang được Spring Security sử dụng.

Ví dụ Mustache:

```html
<form method="post" action="/login">
    <input name="username">
    <input name="password" type="password">
    <input type="hidden" name="{{csrfParam}}" value="{{csrfValue}}">
    <button type="submit">Đăng nhập</button>
</form>
```

Các biến `{{...}}` cần được render bằng engine trong chế độ escape HTML phù hợp; không xuất dữ liệu không tin cậy vào markup mà bỏ qua encoding. Với form logout, thay action thành `/logout`, bỏ username/password và giữ hidden token. Nếu dùng `csrfRequestAttributeHandler` tùy chỉnh, giá trị token request expose có thể được xử lý khác; hãy dùng đúng token mà Spring Security dự kiến nhận khi submit.

## 7. Vòng đời CSRF token quanh login/logout

Với cấu hình CSRF Servlet mặc định, `HttpSessionCsrfTokenRepository` lưu token kỳ vọng trong phiên và Spring Security 6 thường xử lý token theo cơ chế lazy/deferred. Những thời điểm sau quan trọng:

| Sự kiện | Điều cần biết |
| --- | --- |
| GET trang login | View dùng token từ request; việc render token có thể khởi tạo/lấy token phiên. |
| POST login hợp lệ, xác thực thành công | Spring Security có `CsrfAuthenticationStrategy` làm mất hiệu lực token CSRF cũ khi xác thực thành công. |
| Redirect sau login | View mới cần lấy token thích hợp sau khi trạng thái authentication/phiên đổi. |
| POST logout hợp lệ | `CsrfLogoutHandler` làm mất hiệu lực token CSRF cũ; logout thường còn vô hiệu hóa session/security context. |
| GET login mới sau logout | Trang mới tạo/lấy token mới khi cần để người dùng tiếp tục login. |
| Submit form cũ sau khi session đổi | Token đã render trước đây có thể bị từ chối 403; cần tải lại form lấy token mới. |

Hai hệ quả thực tế:

1. **Không cache HTML form có token dùng chung giữa các phiên**. Cần bảo đảm token phù hợp người dùng/phiên và ngữ cảnh request.
2. **Không giả định token cũ dùng mãi**. Khi frontend tự điều khiển luồng login/logout bằng AJAX, cần cơ chế nhận token mới sau khi authentication thay đổi; với luồng server-rendered và redirect GET thông thường, form tiếp theo được render với token phù hợp.

Đừng nhầm việc thay đổi **chuỗi token hiển thị** giữa các lượt GET (do cơ chế che token chống BREACH) với việc **token lưu trong repository đã được thay mới**. Khi kiểm tra, quan sát hành vi POST với chính token được render, không chỉ so sánh chuỗi giữa hai trang.

## 8. Kiểm thử đăng nhập và đăng xuất bằng Spring Security Test

### 8.1. Ma trận tình huống

| Tình huống | Request | Kết quả kỳ vọng trong cấu hình ví dụ |
| --- | --- | --- |
| Mở trang đăng nhập | GET `/login` | 200; HTML chứa username/password và hidden CSRF input. |
| Thiếu CSRF khi login | POST `/login` có username/password, thiếu token | 403; chưa xử lý xác thực thành công. |
| Sai CSRF khi login | POST `/login` có token sai | 403. |
| Login đúng tài khoản, đúng CSRF | POST `/login` với token hợp lệ | Redirect đến `/dashboard`, người dùng được xác thực. |
| Login sai mật khẩu, đúng CSRF | POST `/login` với token hợp lệ | Redirect `/login?error` theo form login mặc định. |
| Mở trang dashboard | GET `/dashboard` khi đã xác thực | 200; HTML có form `POST /logout` và token. |
| Thiếu CSRF khi logout | POST `/logout` thiếu token | 403; logout filter không xử lý yêu cầu. |
| Logout đúng CSRF | POST `/logout` với phiên đăng nhập hợp lệ | Xử lý logout, redirect `/login?logout`. |
| Click liên kết GET `/logout` | GET `/logout` | Không được xem như đường tắt thực hiện logout khi CSRF bật; có thể hiện trang xác nhận. |

Các mã redirect và đường dẫn phụ thuộc cấu hình cụ thể; bảng này gắn với SecurityConfig minh họa ở trên.

### 8.2. Kiểm thử với MockMvc

`spring-security-test` cung cấp `csrf()` và `csrf().useInvalidToken()` để mô phỏng request hợp lệ/sai. Ví dụ:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class LoginLogoutCsrfTests {

    @Autowired
    MockMvc mvc;

    @Test
    void customLoginPageHasToken() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void loginWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "learner")
                        .param("password", "demo-pass"))
                .andExpect(status().isForbidden());
    }

    @Test
    void loginWithWrongCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                        .with(csrf().useInvalidToken())
                        .param("username", "learner")
                        .param("password", "demo-pass"))
                .andExpect(status().isForbidden());
    }

    @Test
    void loginWithValidCsrfSucceeds() throws Exception {
        mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "demo-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/dashboard"))
                .andExpect(authenticated().withUsername("learner"));
    }

    @Test
    void logoutWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/logout")
                        .with(user("learner")))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutWithValidCsrfRedirects() throws Exception {
        mvc.perform(post("/logout")
                        .with(user("learner"))
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));
    }
}
```

Đây là kiểm thử tích hợp ở mức MockMvc với cấu hình và user in-memory của bài thực hành. Test `.with(csrf())` **không chứng minh HTML tự chèn token**, vì công cụ kiểm thử thêm token trực tiếp vào request. Do đó cần kiểm tra GET login và GET dashboard bằng assertions HTML hoặc trình duyệt thật để bảo đảm mỗi form được render đúng.

Kiểm tra logout form trong dashboard bằng MockMvc với tài khoản giả lập:

```java
@Test
void dashboardContainsLogoutForm() throws Exception {
    mvc.perform(get("/dashboard").with(user("learner")))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("action=\"/logout\"")))
            .andExpect(content().string(containsString("name=\"_csrf\"")));
}
```

Với dự án dùng context path, chỉnh assertion của action URL tương ứng; thậm chí kiểm tra DOM bằng parser chuyên dụng nếu có nhiều form và cần xác định hidden input nằm trong **đúng form**.

### 8.3. Quan sát bằng trình duyệt

1. Mở `GET /login` và xem **Response HTML**, tìm input `type="hidden"` chứa tên/value CSRF.
2. Submit form login với mật khẩu sai nhưng token hợp lệ; nếu nhận `/login?error` thì CSRF đã đi qua, còn bước xác thực từ chối.
3. Đăng nhập thành công, mở dashboard và kiểm tra form logout: phải là `method="post"`, action `/logout`, có token.
4. Đăng xuất qua nút và xác nhận được redirect theo cấu hình.
5. Dùng DevTools **Copy as cURL** để gửi lại request login/logout, lần lượt bỏ token hoặc thay token sai trong khi giữ các thông tin còn lại: mong đợi 403 ở lớp CSRF.
6. Thử gửi lại token cũ sau khi authentication/session đã thay đổi; nếu 403, tải trang mới để lấy token hiện tại.

Không log giá trị token hoặc dùng token mẫu trong bài để gửi request thật. Khi chẩn đoán 403, phân biệt lỗi CSRF với lỗi authentication, authorization, cookie session và action URL.

## 9. Spring WebFlux/Reactive

Trong ứng dụng Reactive, các mục tiêu bảo mật vẫn như Servlet: trang login phải gửi token với POST login; form logout phải thực hiện POST có token. Nhưng thành phần triển khai là `CsrfWebFilter` và hệ thống xử lý reactive, thay cho `CsrfFilter` Servlet.

Ví dụ cấu hình cơ bản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/login", "/assets/**").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

Đây là cấu hình **dành riêng cho ứng dụng WebFlux**, không ghép với cấu hình Servlet vào cùng ví dụ chạy. Khi dùng trang login mặc định, Spring Security có thể tự sinh HTML phù hợp. Nếu cần custom view, cần bảo đảm token được đưa vào form mà ứng dụng thực sự render.

Trong WebFlux, Spring Security expose `Mono<CsrfToken>` trong `ServerWebExchange` dưới khóa `CsrfToken.class.getName()`. Với template tùy biến, có thể giải quyết publisher rồi đưa dữ liệu token vào model:

```java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
public class ReactiveLoginPageController {

    @GetMapping("/login")
    Mono<String> login(ServerWebExchange exchange, Model model) {
        Mono<CsrfToken> tokenPublisher =
                exchange.getAttribute(CsrfToken.class.getName());

        if (tokenPublisher == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token không có trong exchange"));
        }

        return tokenPublisher.map(csrf -> {
            model.addAttribute("csrfParameterName", csrf.getParameterName());
            model.addAttribute("csrfTokenValue", csrf.getToken());
            return "login";
        });
    }
}
```

Trong template engine phù hợp, dùng `csrfParameterName` / `csrfTokenValue` để render hidden input cho form login hoặc logout; nếu Thymeleaf Reactive đã tự chèn token thì không chèn thủ công lần nữa. **Không ép kiểu `Mono<CsrfToken>` thành `CsrfToken`**, và không gọi `block()` trên event loop để lấy token.

Kiểm thử WebFlux có thể dùng `WebTestClient` với `SecurityMockServerConfigurers.csrf()` để thử các POST có token hợp lệ. Test thiếu token và token sai cần được thiết kế riêng; trạng thái thành công còn phụ thuộc cấu hình authentication và logout handler Reactive.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách chẩn đoán, sửa |
| --- | --- | --- |
| Login trả 403 dù username/password đúng | `POST /login` thiếu/sai CSRF token. | Kiểm tra HTML của GET login và Form Data của POST; thêm token bằng tích hợp template đúng. |
| Login trả `/login?error` thay vì 403 | CSRF đã qua nhưng bước xác thực thất bại. | Kiểm tra tài khoản, password encoder, tham số `username`/`password`. |
| Form đăng nhập không được hiển thị | `GET /login` không được phép truy cập hoặc không có controller khi dùng `loginPage` tùy chỉnh. | Cho GET login `permitAll()` và khai báo controller/view; giữ request trong security chain. |
| POST login bị 404 hoặc không xác thực | `action` không trùng `loginProcessingUrl`, hoặc bị controller/router khác xử lý. | Kiểm tra `formLogin` và Network; giữ action POST đúng URL. |
| Nhấn Đăng xuất mà không xảy ra logout | Dùng `<a href="/logout">` gửi GET; ứng dụng yêu cầu POST. | Dùng form POST kèm CSRF hidden input, nút `type="submit"`. |
| Đăng xuất trả 403 | Thiếu token, token không đúng phiên hoặc session đổi. | Kiểm tra HTML form và cookie session; tải lại trang sau login nếu token cũ. |
| Logout form có hai trường `_csrf` | Vừa auto chèn qua `th:action`/form tags vừa tự thêm. | Chỉ dùng một cách chèn cho mỗi form, kiểm tra HTML cuối cùng. |
| Login xong form kế tiếp POST bị 403 | Token cũ đã bị xóa/đổi theo lifecycle xác thực. | Render/refetch token mới sau đăng nhập; không cache form từ phiên cũ. |
| Fetch logout trả redirect nhưng UI không chuyển | `fetch` theo redirect bên trong request, không tự thay URL trang. | Sau thành công, chuyển hướng bằng JavaScript theo thiết kế. |
| Reactive template không có token | Đọc nhầm `Mono<CsrfToken>` như đối tượng đồng bộ. | Tiêu thụ publisher trước khi render hoặc dùng tích hợp Reactive của template engine. |

## 11. Bài thực hành cuối bài

**Bài toán:** Tạo trang đăng nhập và dashboard có nút Đăng xuất cho ứng dụng có session. Người dùng truy cập `/login`, đăng nhập bằng tài khoản mẫu, sử dụng `/dashboard` rồi đăng xuất bằng POST. Không được vô hiệu hóa CSRF.

Các bước và đầu ra mong đợi:

1. Tạo `SecurityFilterChain` với `formLogin().loginPage("/login")`, `logoutUrl("/logout")` và CSRF bật; giải thích vì sao `permitAll()` cho login không tắt CSRF.
2. Viết `login.html` với `th:action` và nút submit; xác nhận hidden input do Thymeleaf/Spring Security tạo trong HTML response.
3. Viết `dashboard.html` với form POST logout; thử cách đặt nút ngoài form bằng thuộc tính `form` mà vẫn gửi token.
4. Kiểm tra bốn request: login thiếu token, login token đúng, logout thiếu token, logout token đúng; ghi lại status và xử lý thực tế.
5. Cố tình đổi form logout thành liên kết GET, giải thích vì sao hành vi không đáp ứng nguyên tắc HTTP safe methods và chính sách CSRF mặc định.
6. Thử một lần login/logout rồi mở lại trang mới; so sánh hành vi token cũ và token mới, giải thích vai trò của `CsrfAuthenticationStrategy` / `CsrfLogoutHandler`.
7. Nếu có phiên bản Reactive, chỉ ra đối tượng `Mono<CsrfToken>` và mô tả cách renderer đưa token vào login/logout form mà không block event loop.

**Hoàn thành khi:** Form login và form logout đều có token đúng khi render, POST hợp lệ hoạt động, POST thiếu/sai token bị chặn theo cấu hình, và người học hiểu token thuộc **dữ liệu form**, không phải thuộc tính trang trí của nút.

## Tài liệu tham khảo

- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF cho login/logout, deferred token, BREACH và các chiến lược xử lý token.
- [Spring Security — Servlet Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): custom login page, tên tham số, luồng xử lý login.
- [Spring Security — Servlet Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): yêu cầu POST khi bật CSRF, logout handlers và logout success.
- [Spring Security — JSP Tag Libraries](https://docs.spring.io/spring-security/reference/servlet/integrations/jsp-taglibs.html): `<sec:csrfInput />` và tích hợp JSP.
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()` và `useInvalidToken()`.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `CsrfWebFilter` và `Mono<CsrfToken>`.
