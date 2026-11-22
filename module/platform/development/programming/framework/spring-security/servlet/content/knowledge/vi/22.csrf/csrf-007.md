# CSRF trong biểu mẫu đăng nhập, đăng xuất và thay đổi dữ liệu — Spring Security Servlet

## 1. CSRF là gì và vì sao biểu mẫu cần được bảo vệ?

**Cross-Site Request Forgery (CSRF)** là tình huống một trang do kẻ tấn công kiểm soát khiến trình duyệt của người dùng gửi yêu cầu đến ứng dụng khác trong khi trình duyệt tự kèm thông tin xác thực, chẳng hạn cookie phiên `JSESSIONID`. Máy chủ thấy phiên hợp lệ nhưng **không thể suy ra người dùng thực sự chủ ý thực hiện thao tác** chỉ từ cookie.

Ví dụ: người dùng đã đăng nhập ở `https://app.example.test`. Họ mở một trang khác chứa biểu mẫu gửi POST đến `/profile` của ứng dụng. Tùy chính sách cookie, ngữ cảnh trang và trình duyệt, cookie xác thực có thể được tự gửi cùng yêu cầu. Nếu ứng dụng chỉ kiểm tra cookie mà không kiểm tra nguồn gốc hợp lệ của thao tác, dữ liệu có thể bị thay đổi trái ý người dùng.

Ba điều kiện thường tạo nên nguy cơ CSRF:

1. Endpoint gây tác dụng phụ: đăng nhập, đăng xuất, cập nhật, xóa hoặc thực hiện nghiệp vụ.
2. Trình duyệt có thể tự đính kèm credential cho đích mà mã của trang tấn công không cần biết giá trị credential.
3. Backend thiếu bước xác minh một tín hiệu mà trang độc hại từ origin khác không dễ biết hoặc tạo được.

**CSRF token** là tín hiệu đó: máy chủ tạo giá trị khó đoán cho trang hợp lệ; biểu mẫu hoặc mã JavaScript gửi nó về trong một tham số hoặc header; backend đối chiếu trước khi thực hiện thao tác. Một trang từ origin khác thường không thể đọc token trong HTML của ứng dụng do chính sách cùng nguồn gốc.

Bài này dùng **Spring Security Servlet + Spring MVC + xác thực dựa trên phiên**. Spring Security WebFlux/reactive dùng thành phần và API khác.

## 2. Ba luồng quan trọng: login, logout, thay đổi dữ liệu

| Luồng | Giao diện/endpoint | Nguy cơ thiếu CSRF | Hành vi cần có |
| --- | --- | --- | --- |
| Đăng nhập | `GET /login`, `POST /login` | **Login CSRF**: ép người dùng sử dụng phiên đăng nhập bằng tài khoản của kẻ tấn công | GET có thể công khai, nhưng POST login phải có token |
| Đăng xuất | `POST /logout` | **Logout CSRF**: trang ngoài gây đăng xuất ngoài ý muốn | Đăng xuất bằng form POST có token, không thực hiện logout qua link GET |
| Cập nhật dữ liệu | `POST /profile`, `PUT`, `PATCH`, `DELETE` | Cập nhật/xóa/thực hiện giao dịch ngoài ý muốn | Kiểm tra token trên thao tác ghi; tiếp tục xác thực, phân quyền và validate dữ liệu |

### 2.1. Vì sao login cũng cần CSRF khi người dùng chưa xác thực?

Trong **login CSRF**, kẻ tấn công tìm cách khiến trình duyệt nạn nhân đăng nhập bằng *tài khoản do kẻ tấn công kiểm soát*. Nạn nhân có thể tưởng đang sử dụng tài khoản cá nhân rồi lưu thông tin hoặc thực hiện hoạt động trên tài khoản mà đối phương quan sát được.

`permitAll()` trong `authorizeHttpRequests` chỉ cho phép truy cập endpoint mà không cần đăng nhập trước. Nó **không tắt bộ lọc CSRF**. Vì thế login form vẫn phải mang token, dù `GET /login` là trang công khai.

Luồng chuẩn:

1. Browser tải `GET /login` và nhận HTML với CSRF token.
2. Người dùng nhập `username`, `password`.
3. Form gửi `POST /login` kèm cookie phiên hiện tại và hidden CSRF token.
4. Spring Security kiểm tra CSRF trước khi xác thực tài khoản.
5. Với token hợp lệ, luồng xác thực mới kiểm tra credential và xử lý thành công/thất bại.

### 2.2. Vì sao logout nên là POST?

Đăng xuất thay đổi trạng thái xác thực. Một link kiểu `<a href="/logout">Đăng xuất</a>` tạo GET, dễ bị kích hoạt qua điều hướng hoặc tác nhân tải trang tự động. Với CSRF bật, Spring Security mặc định yêu cầu POST chứa token hợp lệ cho logout. `GET /logout` không phải thao tác đăng xuất; tùy cấu hình nó có thể hiển thị trang xác nhận.

Sau logout, phiên và token cũ không nên tiếp tục được tái sử dụng. Trang đăng nhập mới có thể cấp token mới cho phiên kế tiếp.

### 2.3. CSRF không thay thế phân quyền

Một yêu cầu `POST /orders/123/cancel` có CSRF token hợp lệ vẫn phải kiểm tra người gọi có quyền hủy đơn `123`. CSRF chống một dạng giả mạo yêu cầu; nó không giải quyết quyền sở hữu dữ liệu, XSS, injection hoặc validation.

## 3. Cơ chế mặc định trong Spring Security 6 Servlet

Trong cấu hình Spring Security cho Servlet:

1. `CsrfFilter` xác định yêu cầu có cần kiểm tra hay không. Mặc định `GET`, `HEAD`, `TRACE`, `OPTIONS` được loại khỏi kiểm tra; `POST`, `PUT`, `PATCH`, `DELETE` và các method khác phải có token.
2. `CsrfTokenRepository` quản lý token kỳ vọng. Mặc định với kiểu cấu hình này là `HttpSessionCsrfTokenRepository`, gắn token với phiên HTTP. Việc tạo/nạp token có thể được thực hiện lười (deferred).
3. Khi render view của Spring MVC, request có thể có thuộc tính `_csrf` cung cấp `parameterName`, `headerName`, `token`.
4. Form gửi lại hidden field; AJAX gửi header tương ứng. `CsrfFilter` lấy giá trị nhận được và so sánh với token kỳ vọng. Thiếu hoặc sai thường trả **HTTP 403 Forbidden**, trước khi controller được gọi.
5. Sau xác thực thành công hoặc đăng xuất, các chiến lược tích hợp Spring Security xóa token cũ; yêu cầu kế tiếp cần nhận token mới. SPA giữ token cũ có thể gặp 403 sau login/logout.

Tên tham số mặc định thường là `_csrf` và header thường là `X-CSRF-TOKEN`; hãy lấy tên thực tế từ `_csrf` vì cấu hình repository và request handler có thể khác.

**Spring Security 6 dùng XOR CSRF request handler để che giấu giá trị token khi đưa ra trang**, nhằm giảm một số rủi ro như BREACH. Vì vậy giá trị token thấy trong hai lần render có thể khác nhau dù token gốc trong repository không đổi. Không tự so sánh token đã hiển thị để kết luận phiên bị đổi.

## 4. Demo chạy được: Spring Boot MVC + Thymeleaf

Tạo project Spring Boot 3.x dùng **Java 17+** với các dependency: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-thymeleaf`. Để chạy bài test ở phần 7, thêm `spring-boot-starter-test` và `spring-security-test` vào test dependencies. Đặt các file theo cấu trúc:

```text
src/main/java/com/example/csrf/
  CsrfFormsApplication.java
  SecurityConfig.java
  FormController.java
src/main/resources/templates/
  login.html
  home.html
src/test/java/com/example/csrf/
  CsrfFormsSecurityTests.java
```

### 4.1. Lớp khởi động

**`CsrfFormsApplication.java`**

```java
package com.example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfFormsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfFormsApplication.class, args);
    }
}
```

### 4.2. Cấu hình SecurityFilterChain

**`SecurityConfig.java`**

```java
package com.example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error", "/css/**").permitAll()
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(form -> form
                .loginPage("/login")
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            );

        return http.build();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
```

`csrf(Customizer.withDefaults())` nêu rõ CSRF đang bật; trong cấu hình Spring Security Servlet thông thường, CSRF cũng đã bật theo mặc định. `requestMatchers("/login").permitAll()` không miễn token CSRF cho POST. Spring Security xử lý `POST /login` và `POST /logout` thông qua filter riêng; không cần tự tạo controller để xử lý hai POST đó.

Thông tin `learner` / `demo-password` chỉ dành cho máy học/demo, không phải mật khẩu mẫu an toàn để triển khai lên Internet.

### 4.3. Controller cập nhật dữ liệu

**`FormController.java`**

```java
package com.example.csrf;

import java.security.Principal;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class FormController {
    private final ConcurrentMap<String, String> displayNames =
        new ConcurrentHashMap<>();

    @GetMapping("/login")
    String login() {
        return "login";
    }

    @GetMapping("/")
    String home(Principal principal, Model model) {
        String username = principal.getName();
        model.addAttribute("username", username);
        model.addAttribute(
            "displayName",
            displayNames.getOrDefault(username, username)
        );
        return "home";
    }

    @PostMapping("/profile")
    String updateProfile(
            @RequestParam("displayName") String displayName,
            Principal principal) {
        displayNames.put(principal.getName(), displayName);
        return "redirect:/";
    }
}
```

`GET /login` render form công khai; `GET /` cần xác thực; `POST /profile` thực sự thay đổi dữ liệu demo nếu yêu cầu vượt qua cả xác thực lẫn CSRF. `ConcurrentHashMap` giúp ví dụ ngắn và độc lập nhưng không phải cách lưu hồ sơ production: dữ liệu mất khi restart, và ví dụ chưa có ràng buộc chiều dài/tính hợp lệ tên.

### 4.4. Form đăng nhập

**`src/main/resources/templates/login.html`**

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="utf-8">
    <title>Đăng nhập</title>
</head>
<body>
    <h1>Đăng nhập</h1>
    <p th:if="${param.error}">Tên đăng nhập hoặc mật khẩu sai.</p>
    <p th:if="${param.logout}">Bạn đã đăng xuất.</p>

    <form th:action="@{/login}" method="post">
        <label for="username">Tài khoản</label>
        <input id="username" name="username" required>

        <label for="password">Mật khẩu</label>
        <input id="password" type="password" name="password" required>

        <button type="submit">Đăng nhập</button>
    </form>
</body>
</html>
```

Với tích hợp **Thymeleaf + Spring MVC + Spring Security**, `th:action` đi qua `RequestDataValueProcessor`; Spring Security có thể tự thêm hidden field CSRF vào form POST. Do đó, **không thêm tay một hidden field `_csrf` thứ hai** vào form trên. Có thể kiểm tra DOM form đã render trong trình duyệt để xác nhận trường CSRF thực sự tồn tại.

Khi token đúng nhưng username/password sai, Spring Security xử lý nhánh lỗi xác thực và thường quay lại `/login?error`. Khi POST không có token, yêu cầu bị từ chối ở bộ lọc CSRF trước khi tới logic mật khẩu.

### 4.5. Form thay đổi dữ liệu và đăng xuất

**`src/main/resources/templates/home.html`**

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="utf-8">
    <title>Hồ sơ</title>
</head>
<body>
    <h1>Hồ sơ</h1>
    <p>Tài khoản: <strong th:text="${username}"></strong></p>
    <p>Tên hiển thị: <span th:text="${displayName}"></span></p>

    <form th:action="@{/profile}" method="post">
        <label for="displayName">Tên hiển thị mới</label>
        <input id="displayName" name="displayName" required>
        <button type="submit">Lưu thay đổi</button>
    </form>

    <form th:action="@{/logout}" method="post">
        <button type="submit">Đăng xuất</button>
    </form>
</body>
</html>
```

Cả hai form cần token. `POST /profile` không được phép thay đổi dữ liệu chỉ vì cookie hợp lệ; nó còn phải vượt qua kiểm tra CSRF. `POST /logout` cũng phải có token để Spring Security xử lý hủy trạng thái đăng nhập. Đừng biến thao tác ghi thành GET chỉ để “tránh” lỗi 403.

### 4.6. Chạy và tự kiểm tra

Trong project Gradle Spring Boot có Wrapper:

```bash
./gradlew bootRun
```

Trên PowerShell Windows dùng `.\gradlew.bat bootRun`. Mở `http://localhost:8080/login`, dùng tài khoản demo `learner` / `demo-password`, đổi tên hiển thị ở trang chủ rồi nhấn Đăng xuất. Trong DevTools, kiểm tra payload của các form POST có tham số CSRF; logout form cũng phải có.

Có thể kiểm tra một request cố ý **thiếu** token:

```bash
curl -i -X POST http://localhost:8080/login \
  -d "username=learner&password=demo-password"
```

Kết quả dự kiến **HTTP 403**, bởi request thiếu CSRF token, không phải do sai mật khẩu. Lệnh này chỉ chứng minh nhánh từ chối; đăng nhập qua HTTP client đúng cách đòi lấy token từ GET và gửi cookie phiên tương ứng. Trên PowerShell nên dùng `curl.exe` để tránh alias có hành vi khác.

## 5. Tự đưa token vào form hoặc AJAX

### 5.1. Khi form không dùng th:action

Nếu dùng form Thymeleaf với `action` thông thường và muốn quản lý field thủ công:

```html
<form action="/profile" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <input name="displayName" required>
    <button type="submit">Lưu</button>
</form>
```

Đây là **phương án thay thế** việc Spring Security tự chèn field qua `th:action`, không phải cách để chèn hai token trùng tên. Với ứng dụng có context path khác `/`, cần đảm bảo URL form được xây dựng đúng context path.

### 5.2. Fetch/AJAX cùng origin

Nếu trang server-rendered gọi endpoint POST từ JavaScript, có thể đưa token và header name ra hai meta tag:

```html
<meta name="_csrf" th:content="${_csrf.token}">
<meta name="_csrf_header" th:content="${_csrf.headerName}">
```

Ví dụ gọi đúng endpoint `@PostMapping("/profile")` của demo:

```javascript
async function saveDisplayName(displayName) {
    const token = document.querySelector('meta[name="_csrf"]').content;
    const headerName =
        document.querySelector('meta[name="_csrf_header"]').content;

    const response = await fetch("/profile", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            [headerName]: token,
            "Content-Type": "application/x-www-form-urlencoded"
        },
        body: new URLSearchParams({ displayName }).toString()
    });

    if (!response.ok) {
        throw new Error("Không thể cập nhật: HTTP " + response.status);
    }
}
```

`credentials: "same-origin"` duy trì cookie của cùng origin. Header CSRF là một điều kiện **bổ sung**: chỉ cookie thôi chưa đủ. Ví dụ dùng `application/x-www-form-urlencoded` vì controller nhận `@RequestParam`; nếu chuyển sang JSON phải chỉnh cả payload, Content-Type và tham số của controller. Token cũ giữ trong bộ nhớ SPA có thể không còn hợp lệ sau login/logout; hãy lấy token mới.

### 5.3. CookieCsrfTokenRepository dành cho SPA

`CookieCsrfTokenRepository` thường sử dụng cookie `XSRF-TOKEN` và header `X-XSRF-TOKEN`. Nhưng với Spring Security 6, **chỉ gọi `CookieCsrfTokenRepository.withHttpOnlyFalse()` không tự giải quyết mọi ca SPA**: cần xử lý đúng token che giấu XOR/BREACH, deferred token loading và việc cấp lại token sau login/logout. Cấu hình request handler/cấp token phải phù hợp phiên bản Spring Security thực tế. Không cho JavaScript đọc cookie CSRF nếu không thực sự cần; bất kỳ XSS cùng origin cũng có thể truy cập token mà JavaScript đọc được.

## 6. Những lỗi và ngộ nhận phổ biến

| Triệu chứng hoặc giả định | Cách hiểu và xử lý |
| --- | --- |
| Xem `GET /login` được nhưng `POST /login` báo 403 | Xác nhận form có token thật, cookie phiên tương ứng và token được gửi; `permitAll()` không miễn CSRF |
| Form HTML tĩnh không xuất hiện `_csrf` | HTML tĩnh không biết token phiên; phải render server-side hoặc dùng cơ chế cấp token chủ động |
| Link GET `/logout` không đăng xuất | Sử dụng form POST có token; không bật GET logout chỉ để sửa triệu chứng |
| AJAX bị 403 ngay sau login/logout | Token cũ đã được xóa hoặc session thay đổi; tải/cấp lại token đúng với phiên mới |
| Form bị cache dùng chung hoặc token từ phiên khác | Không cache nhầm HTML chứa token riêng của một phiên; render lại đúng ngữ cảnh |
| Yêu cầu có CSRF token hợp lệ nhưng sửa được tài nguyên người khác | CSRF không thay thế kiểm tra vai trò, quyền và ownership trên backend |
| GET vẫn cập nhật/xóa dữ liệu | Sửa API: GET phải an toàn về tác dụng phụ, vì kiểm tra CSRF mặc định bỏ qua GET |
| Header CSRF có tên đúng nhưng giá trị sai | Kiểm tra request có lấy đúng token của phiên hiện tại, không hard-code hoặc trộn session |
| Tắt `csrf` toàn cục để tránh lỗi 403 | Tìm nguyên nhân token thiếu; `csrf.disable()` rất rủi ro với ứng dụng xác thực bằng cookie |
| Cho rằng CORS chống được CSRF | CORS chủ yếu kiểm soát đọc phản hồi/yêu cầu JavaScript; trình duyệt vẫn có thể gửi form cross-origin |
| Cho rằng `SameSite` thay thế CSRF | `SameSite` giảm nguy cơ trong nhiều ngữ cảnh nhưng phụ thuộc cookie policy, same-site subdomain và cách trình duyệt gửi cookie; vẫn cần chính sách server thích hợp |
| API dùng Bearer token | Nếu JavaScript chủ động gắn `Authorization` và browser không tự gửi credential, mô hình đe dọa khác. Nếu bearer/session token nằm trong cookie tự gửi thì vẫn cần đánh giá CSRF |
| Có lỗ hổng XSS | XSS cùng origin có thể đọc/gửi token; CSRF token không chống XSS. Tiếp tục escaping, CSP và kiểm soát đầu vào |

**Đừng đưa CSRF token vào URL** (query string): URL có thể nằm trong history, log, analytics hay Referer. Dùng hidden field với form và header với AJAX. Trong ứng dụng thật, còn cần HTTPS, cookie `Secure`/`HttpOnly` khi phù hợp, `SameSite`, session fixation protection và validation.

## 7. Kiểm thử bằng MockMvc

Thêm dependency test `spring-boot-starter-test` và `spring-security-test` vào dự án. File **`src/test/java/com/example/csrf/CsrfFormsSecurityTests.java`**:

```java
package com.example.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfFormsSecurityTests {
    @Autowired
    MockMvc mockMvc;

    @Test
    void updateWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/profile")
                .with(user("learner"))
                .param("displayName", "Minh"))
            .andExpect(status().isForbidden());
    }

    @Test
    void updateWithCsrfCanProceed() throws Exception {
        mockMvc.perform(post("/profile")
                .with(user("learner"))
                .with(csrf())
                .param("displayName", "Minh"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/logout")
                .with(user("learner")))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "demo-password"))
            .andExpect(status().isForbidden());
    }
}
```

Chạy `./gradlew test` (Windows: `.\gradlew.bat test`). `with(user("learner"))` tạo người dùng giả để test quyền, `with(csrf())` thêm token hợp lệ. Test cập nhật có token đợi redirect từ controller, cho thấy yêu cầu vượt qua chốt CSRF; nó **không chứng minh** validation, phân quyền từng tài nguyên hoặc persistence production đã đúng. Có thể bổ sung `.with(csrf().useInvalidToken())` để xác nhận token sai bị 403.

Kiểm thử end-to-end trên trình duyệt còn cần xác nhận hidden token được render thực sự, login thành công, logout qua POST, token mới sau login/logout và cookie phiên khớp với token. Unit/integration test dùng `with(csrf())` không tự kiểm tra HTML có trường CSRF hay không.

## 8. Checklist trước khi triển khai

1. Tách thao tác đọc an toàn (`GET`/`HEAD`) khỏi thao tác ghi (`POST`/`PUT`/`PATCH`/`DELETE`); không dùng GET để sửa trạng thái.
2. Với session/cookie tự gửi, giữ CSRF protection của Spring Security; cân nhắc ngoại lệ hẹp chỉ sau khi hiểu rõ credential thực sự được gửi như thế nào.
3. Trang `GET /login` được truy cập công khai nhưng `POST /login` vẫn bắt buộc có token; phân biệt 403 do CSRF với lỗi xác thực.
4. Logout dùng POST với token; quản lý vòng đời token sau xác thực/đăng xuất.
5. Với Thymeleaf, kiểm tra `th:action` và CSRF hidden field đã render; với HTML/AJAX tự viết, truyền token đúng parameter/header và phiên.
6. Test cả trường hợp không token, token sai, token đúng, người dùng chưa/đã xác thực và user không đủ quyền.
7. Giữ authorization, ownership check, validation, chống XSS, HTTPS và cookie policy song song với CSRF.

Với Spring Security Servlet và ba loại biểu mẫu trên, quy tắc thực hành nhất quán là: **giữ CSRF được bật, đưa token vào tất cả yêu cầu thay đổi trạng thái, không biến ghi dữ liệu thành GET, và xác nhận cả nhánh chấp nhận lẫn từ chối bằng test**.
