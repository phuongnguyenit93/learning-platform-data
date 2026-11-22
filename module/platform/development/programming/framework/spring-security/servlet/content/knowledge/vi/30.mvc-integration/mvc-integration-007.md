# Tích hợp biểu mẫu, Thymeleaf hoặc JSP với danh tính và CSRF token

**Module:** Spring Security – Servlet  
**Chủ đề cha:** Tích hợp MVC

## 1. Mục tiêu và bài toán

Một trang Spring MVC render HTML thường cần ba việc đồng thời:

1. **Xác định người dùng hiện tại** từ `Authentication` của Spring Security, thay vì tin tên người dùng hoặc vai trò do form gửi.
2. **Bảo vệ các thao tác thay đổi trạng thái** như POST tạo bản ghi, POST cập nhật hoặc POST logout khỏi **Cross-Site Request Forgery (CSRF)** khi browser tự gửi session cookie.
3. **Bind và validate biểu mẫu**, hiển thị lỗi và nội dung bằng cách escape HTML; không hiểu nhầm CSRF token thành biện pháp kiểm tra đầu vào hoặc chống XSS.

Bài này tập trung vào **Spring Security Servlet + Spring MVC + server-rendered Thymeleaf hoặc JSP**. Ta xây một ví dụ đăng nhập form, hiển thị username, tạo ghi chú riêng theo user và logout bằng POST có CSRF token. Sau đó đối chiếu cách viết JSP và kiểm thử với MockMvc.

**Nguyên tắc:** Authentication trả lời “ai”; Authorization trả lời “được làm gì”; CSRF token giảm nguy cơ trình duyệt bị lợi dụng gửi thao tác ngoài ý muốn; validation/escaping giữ dữ liệu an toàn và đúng nghiệp vụ. Các lớp này không thay thế nhau.

## 2. Luồng request và nơi danh tính/CSRF tham gia

~~~text
Browser                     Spring Security Servlet       Spring MVC
   | GET /notes                       |                        |
   |--------------------------------->|                        |
   |      session cookie được đọc     |                        |
   |                Authentication -> | ----> Controller GET   |
   |                                  |       Model + View      |
   |         HTML: username, notes, form, _csrf.token          |
   |<---------------------------------------------------------|
   | POST /notes + cookie + CSRF field                         |
   |---------------------------------------------------------> |
   |                CsrfFilter kiểm tra token                   |
   |                Authorization kiểm tra quyền               |
   |                                  | ----> @Valid form      |
   |                                  |       ghi đúng owner   |
   |               302 /notes         |                        |
   |<---------------------------------------------------------|
   | GET /notes (Post/Redirect/Get)                             |
   |---------------------------------------------------------->|
~~~

Nếu POST thiếu token hợp lệ, **`CsrfFilter` thường trả HTTP 403** và controller không thực hiện thao tác. Nếu chưa login, request GET tới trang cần đăng nhập thường được chuyển hướng tới trang login. Không nên mặc định suy ra mọi 403 là lỗi CSRF: thiếu quyền cũng có thể trả 403; cần kiểm tra log/flow ở mức an toàn.

### Authentication và Principal

Spring Security lưu `Authentication` trong `SecurityContext`. Với form login thông thường, principal có thể là `UserDetails`; với OAuth2/OIDC login có thể là `OAuth2User` hoặc `OidcUser`.

Trong controller MVC:

~~~java
@GetMapping("/profile")
String profile(Authentication authentication, Model model) {
    model.addAttribute("username", authentication.getName());
    return "profile";
}
~~~

Đây là **đoạn method minh họa bên trong một controller đã được bảo vệ**, không phải class Java độc lập. `Authentication#getName()` trả danh tính từ Spring Security, không phải field người dùng tùy ý sửa trong browser.

Các cách khác:

- `@AuthenticationPrincipal UserDetails user` nếu ứng dụng chắc chắn principal là `UserDetails`.
- `@AuthenticationPrincipal` với principal OAuth2/OIDC phù hợp nếu sử dụng loại login đó.
- Trong Thymeleaf với extras: `sec:authentication="name"`.
- Trong JSP: Servlet `request.userPrincipal` hoặc Spring Security taglib phù hợp.

Không ép kiểu principal của form login khi ứng dụng thực tế dùng OAuth2. Với endpoint `permitAll()` và request chưa xác thực, cần kiểm tra `null`/anonymous trước khi sử dụng.

### Authority không chỉ là việc ẩn nút

`hasRole("USER")` thông thường kiểm tra authority `ROLE_USER`. Việc Thymeleaf/JSP ẩn nút dựa trên role chỉ hỗ trợ giao diện; client vẫn có thể gửi HTTP request trực tiếp. Server phải bảo vệ endpoint, sau đó kiểm tra quyền **trên chính resource và tenant** khi cần.

## 3. Cơ chế CSRF của Spring Security Servlet

### 3.1. Vì sao session cookie tạo rủi ro CSRF?

Browser có thể tự gửi cookie xác thực khi phát request tới website đúng phạm vi cookie. Một website khác có thể cố kích hoạt hành động trên ứng dụng thật trong ngữ cảnh browser của nạn nhân. Nếu server chỉ kiểm tra session cookie, request ngoài ý muốn có thể bị coi là hợp lệ.

CSRF protection của Spring Security thường yêu cầu token đối với **POST, PUT, PATCH, DELETE** và coi **GET, HEAD, OPTIONS, TRACE** là safe theo matcher mặc định. Vì thế **không thực hiện thao tác thay đổi dữ liệu bằng GET** để né CSRF.

Form được render từ server có thể mang trường ẩn:

~~~html
<form method="post" action="/notes">
    <input name="text" value="Xin chào">
    <input name="_csrf" type="hidden" value="token-do-server-cap">
    <button type="submit">Lưu</button>
</form>
~~~

Chuỗi `token-do-server-cap` chỉ là ví dụ giải thích; **không bao giờ hard-code token**. Giá trị và tên field thực phải lấy từ `CsrfToken` của request.

### 3.2. Những thành phần quan trọng

| Thành phần | Vai trò |
| --- | --- |
| `CsrfFilter` | Quyết định method nào cần token và kiểm tra token trong request. |
| `CsrfTokenRepository` | Tạo và lưu token kỳ vọng; cấu hình phổ biến cho MVC session dùng `HttpSessionCsrfTokenRepository`. |
| `CsrfTokenRequestHandler` | Làm token khả dụng trong request và xử lý giá trị được gửi; Spring Security 6 có xử lý deferred token/XOR masking để giảm rủi ro BREACH. |
| Request attribute `_csrf` | Cho template đọc `_csrf.parameterName`, `_csrf.token`, `_csrf.headerName`. |
| Session cookie | Giữ phiên đăng nhập; không thể thay thế giá trị CSRF token. |

Trong các cấu hình HTTP thông thường, Spring Security **bật CSRF mặc định**. Không gọi `csrf.disable()` chỉ để vượt qua lỗi 403 khi form bị thiếu field.

### 3.3. Token từ form đi vào filter như thế nào?

~~~text
GET /notes
  -> filter expose _csrf
  -> template render hidden field tên _csrf.parameterName
     và giá trị _csrf.token
  -> browser giữ session cookie

POST /notes
  -> browser gửi cookie + hidden field
  -> CsrfFilter đối chiếu token với repository/handler
  -> nếu hợp lệ: tiếp tục authorization và controller
  -> nếu sai/thiếu: thường 403
~~~

Một form POST khác như `/logout` cũng cần token khi CSRF đang bật. Token có thể bị xóa và tạo lại khi login/logout, vì vậy một form HTML còn mở từ session cũ có thể bị 403. Cách xử lý thường là **tải lại trang/form** để nhận token hiện hành, không vô hiệu hóa CSRF.

### 3.4. Những trường hợp không được hiểu nhầm

- CSRF token **không** ngăn một đoạn JavaScript độc hại đã chạy trong origin ứng dụng lợi dụng quyền của user; cần chống XSS bằng escaping/CSP phù hợp.
- CSRF token **không** làm field `ownerId`, `role`, `price` thành dữ liệu đáng tin. Client có thể sửa hidden inputs.
- **SameSite cookie** giảm rủi ro trong một số tình huống nhưng không phải lý do mặc định để bỏ CSRF token.
- API stateless xác thực **chỉ bằng bearer token trong Authorization header** có threat model khác. Không lấy cấu hình API đó áp lên MVC form dùng session cookie.
- Nếu ứng dụng triển khai nhiều `SecurityFilterChain`, phải bảo đảm path form đi qua chain có CSRF và authorization đúng.

## 4. Thymeleaf: identity, form binding và CSRF token

Thymeleaf nhận Model từ controller, xử lý giá trị field và tự escape khi dùng các processor thích hợp.

### 4.1. Hiển thị danh tính bằng Thymeleaf extras

Với dependency `thymeleaf-extras-springsecurity6` tương thích Spring Security 6, có thể viết:

~~~html
<html xmlns:th="http://www.thymeleaf.org"
      xmlns:sec="https://www.thymeleaf.org/extras/spring-security">
<body>
    <p sec:authorize="isAuthenticated()">
        Xin chào, <strong sec:authentication="name">Tên</strong>
    </p>
</body>
</html>
~~~

`sec:authentication="name"` lấy thông tin authentication được server quản lý. `sec:authorize` chỉ thay đổi phần **view**; không được sử dụng làm kiểm tra quyền duy nhất.

### 4.2. Token tường minh trong form

~~~html
<form method="post" action="/notes" th:object="${noteForm}">
    <label for="text">Ghi chú</label>
    <input id="text" th:field="*{text}" type="text"
           maxlength="200" required>

    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">

    <p th:if="${#fields.hasErrors('text')}"
       th:errors="*{text}">Dữ liệu không hợp lệ</p>

    <button type="submit">Lưu</button>
</form>
~~~

- `th:object` chọn DTO, `th:field` bind input với property `text`.
- `_csrf.parameterName` và `_csrf.token` đến từ Spring Security request.
- `th:errors` hiển thị lỗi từ `BindingResult`; server phải dùng `@Valid`.
- `required` và `maxlength` phía HTML chỉ hỗ trợ UX, dễ bị bypass bằng request tự tạo.

**Cẩn trọng với CSRF tự động:** với `th:action`, Thymeleaf tích hợp Spring có thể tự thêm CSRF hidden field qua `RequestDataValueProcessor`. Khi dùng cách tự động, không thêm một bản tường minh thứ hai. Ví dụ ở đây chọn cách **tường minh** và `action` cố định. Nếu ứng dụng chạy dưới context path không phải `/`, dùng URL expression `@{/notes}` và kiểm tra HTML kết quả để tránh lỗi path/duplicate token.

### 4.3. Escape dữ liệu khi hiển thị

~~~html
<!-- An toàn: Thymeleaf escape nội dung trong HTML text context. -->
<li th:each="note : ${notes}"
    th:text="${note}">Nội dung ghi chú</li>

<!-- Không an toàn với dữ liệu chưa sanitize. -->
<li th:utext="${note}">Nội dung ghi chú</li>
~~~

Nếu user lưu chuỗi `<img src=x onerror=alert(1)>`, `th:text` hiển thị như **văn bản**, không tạo thẻ HTML thật. CSRF token không thay output escaping; validation độ dài cũng không tự chống XSS.

## 5. Dự án Spring Boot 3.3.5 / Java 17 hoàn chỉnh

Dự án này dùng Spring MVC Servlet, Security form login, Thymeleaf, Bean Validation và MockMvc. Bản Boot cố định để tái hiện cú pháp; production cần dùng release được hỗ trợ và cập nhật bản vá.

Chức năng:

- `GET /notes`: chỉ user có `ROLE_USER` xem được.
- `POST /notes`: chỉ user có `ROLE_USER`, token CSRF hợp lệ và dữ liệu hợp lệ mới ghi.
- `POST /logout`: đăng xuất qua Spring Security, có CSRF token.
- Notes được phân vùng theo username **server đã xác thực**; không nhận `ownerId` từ form.
- Dữ liệu lưu tạm trong bộ nhớ, không phải repository production.

### 5.1. Cấu trúc thư mục

~~~text
mvc-form-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/MvcFormApplication.java
    │   └── resources/templates/notes.html
    └── test/java/demo/MvcFormApplicationTests.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>mvc-form-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
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
            <groupId>org.thymeleaf.extras</groupId>
            <artifactId>thymeleaf-extras-springsecurity6</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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
~~~

### 5.3. src/main/java/demo/MvcFormApplication.java

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@SpringBootApplication
public class MvcFormApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcFormApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Chỉ để học: không hard-code mật khẩu trong production.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learning-only"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("learning-only"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/notes")
                    .hasRole("USER")
                .requestMatchers(HttpMethod.POST, "/notes")
                    .hasRole("USER")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        // Không vô hiệu hóa CSRF: mặc định vẫn bảo vệ POST.
        return http.build();
    }

    public static class NoteForm {
        @NotBlank
        @Size(max = 200)
        private String text;

        public String getText() {
            return text;
        }

        public void setText(String text) {
            this.text = text;
        }
    }

    @Controller
    public static class NoteController {
        private final Map<String, CopyOnWriteArrayList<String>> notes =
            new ConcurrentHashMap<>();

        @GetMapping("/notes")
        public String page(Authentication authentication, Model model) {
            model.addAttribute("noteForm", new NoteForm());
            model.addAttribute(
                "notes",
                notes.getOrDefault(
                    authentication.getName(), new CopyOnWriteArrayList<>()
                )
            );
            return "notes";
        }

        @PostMapping("/notes")
        public String save(
                @Valid @ModelAttribute("noteForm") NoteForm form,
                BindingResult errors,
                Authentication authentication,
                Model model) {
            if (errors.hasErrors()) {
                model.addAttribute(
                    "notes",
                    notes.getOrDefault(
                        authentication.getName(), new CopyOnWriteArrayList<>()
                    )
                );
                return "notes";
            }

            // User identity đến từ Authentication, KHÔNG từ hidden field.
            notes.computeIfAbsent(
                authentication.getName(),
                key -> new CopyOnWriteArrayList<>()
            ).add(form.getText());

            return "redirect:/notes";
        }
    }
}
~~~

**Giải thích:**

- `formLogin(Customizer.withDefaults())` tạo form login mặc định tại `/login`. Không cần controller login riêng cho demo.
- In-memory users `alice`/`bob` có password demo `learning-only`. Password được encode bằng Spring PasswordEncoder. **Không đưa cấu hình này vào production**.
- `hasRole("USER")` kiểm tra authority `ROLE_USER` theo tiền tố mặc định.
- `@Valid` + `BindingResult` (đặt ngay sau đối tượng bind) chặn input rỗng/quá dài. Chỉ bind DTO chứa trường `text`, không bind entity có `ownerId` hay `role`.
- `Authentication#getName()` xác định owner. User Alice không thể sửa owner bằng cách tự thêm form parameter.
- Dữ liệu được giữ bằng `ConcurrentHashMap` và `CopyOnWriteArrayList` chỉ để demo ít ghi; không có persistence, transaction hoặc quy tắc quyền cho dữ liệu production.
- `redirect:/notes` thực hiện **Post/Redirect/Get**, tránh submit lại POST khi refresh.
- Logout được Spring Security xử lý mặc định; khi CSRF bật, `POST /logout` có token là cách dùng thông thường.

### 5.4. src/main/resources/templates/notes.html

~~~html
<!DOCTYPE html>
<html lang="vi"
      xmlns:th="http://www.thymeleaf.org"
      xmlns:sec="https://www.thymeleaf.org/extras/spring-security">
<head>
    <meta charset="UTF-8">
    <title>Ghi chú riêng</title>
</head>
<body>
    <h1>Ghi chú của tôi</h1>
    <p sec:authorize="isAuthenticated()">
        Đang đăng nhập:
        <strong sec:authentication="name">Tên người dùng</strong>
    </p>

    <form method="post" action="/notes" th:object="${noteForm}">
        <label for="text">Nội dung</label>
        <input id="text" type="text" th:field="*{text}"
               maxlength="200" required>
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">
        <p th:if="${#fields.hasErrors('text')}"
           th:errors="*{text}">Giá trị không hợp lệ</p>
        <button type="submit">Lưu</button>
    </form>

    <ul>
        <li th:each="note : ${notes}"
            th:text="${note}">Ghi chú được escape</li>
    </ul>

    <form method="post" action="/logout">
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">
        <button type="submit">Đăng xuất</button>
    </form>
</body>
</html>
~~~

Ở đây form sử dụng `action` tĩnh cùng hidden token tường minh. Cả **POST tạo ghi chú** và **POST logout** đều có token. Với `th:action` và tích hợp Spring, framework có thể tự thêm hidden token; không dùng cả hai phương pháp trên cùng form mà không kiểm tra HTML cuối cùng.

`th:text` escape nội dung khi render. Ví dụ nhập `<img src=x onerror=alert(1)>`: trình duyệt phải hiện đoạn text, không chạy event handler. Không thay `th:text` bằng `th:utext` nếu dữ liệu chưa được sanitize theo chính sách rõ ràng.

### 5.5. Chạy thử

Từ thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Mở:

~~~text
http://localhost:8080/notes
~~~

Kỳ vọng trình duyệt chuyển hướng đến `/login`. Đăng nhập bằng `alice` / `learning-only`. Khi form POST có token hợp lệ, trang chuyển hướng trở lại `/notes`; nội dung nằm trong danh sách của Alice. Đăng xuất rồi đăng nhập bằng Bob: danh sách của Bob độc lập với Alice trong bộ nhớ demo.

Thử gửi form không có CSRF token (ví dụ bằng một test HTTP có session cookie): Spring Security thường trả 403. Mở DevTools Network để kiểm tra request field và session cookie, nhưng **không sao chép token hoặc cookie thật vào log/ticket**.

Các bước ở đây mô tả **kết quả dự kiến** khi chạy mã, không phải log chạy thực tế đã được thu thập.

## 6. MockMvc: kiểm thử identity, CSRF, validation và escaping

File **src/test/java/demo/MvcFormApplicationTests.java**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcFormApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadNotes() throws Exception {
        mvc.perform(get("/notes"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/notes").param("text", "Hello"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void validPostEscapesStoredNote() throws Exception {
        String payload = "<img src=x onerror=alert(1)>";

        mvc.perform(post("/notes").with(csrf()).param("text", payload))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/notes"));

        mvc.perform(get("/notes"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("&lt;img")))
            .andExpect(content().string(not(containsString(payload))));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void invalidFormIsRejectedByServer() throws Exception {
        mvc.perform(post("/notes").with(csrf()).param("text", "   "))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasFieldErrors("noteForm", "text"));

        mvc.perform(post("/notes").with(csrf())
                .param("text", "a".repeat(201)))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasFieldErrors("noteForm", "text"));
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void otherUserSeesOwnPage() throws Exception {
        mvc.perform(get("/notes"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("bob")));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void logoutWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kỳ vọng:** toàn bộ test pass; đây không phải output chạy thực đã được kiểm chứng ở môi trường này.

`@WithMockUser` tạo SecurityContext giả cho test filter/controller; nó **không kiểm thử password login thật**. `csrf()` là test helper tạo token hợp lệ, không phải cách client production tự tạo token. Với test integration đăng nhập form, dùng `formLogin()` trong Spring Security Test hoặc browser integration theo nhu cầu.

Bài test cũng cần mở rộng trong sản phẩm thật: user không có role, logout hợp lệ, session fixation, đường dẫn bị bảo vệ, resource ownership, token cũ sau đổi session, lỗi binding và các response 403 cần logging an toàn.

## 7. JSP: cùng nguyên tắc security, cách render khác Thymeleaf

JSP được Spring MVC render trong Servlet container. Với Spring Security, server vẫn cung cấp `Authentication`, CSRF request attribute và authorization filter. JSP không phải filter chống CSRF.

**Fragment JSP minh họa**, đặt ở `/WEB-INF/jsp/notes.jsp` trong một dự án JSP đã cấu hình Jakarta JSTL:

~~~jsp
<%@ page contentType="text/html;charset=UTF-8" %>
<%@ taglib prefix="c" uri="jakarta.tags.core" %>

<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Ghi chú JSP</title></head>
<body>
    <p>
        Đã đăng nhập:
        <c:out value="${pageContext.request.userPrincipal.name}"/>
    </p>

    <form method="post"
          action="${pageContext.request.contextPath}/notes">
        <input name="text" maxlength="200" required>
        <input type="hidden"
               name="${_csrf.parameterName}"
               value="${_csrf.token}">
        <button type="submit">Lưu</button>
    </form>

    <ul>
        <c:forEach var="note" items="${notes}">
            <li><c:out value="${note}"/></li>
        </c:forEach>
    </ul>

    <form method="post"
          action="${pageContext.request.contextPath}/logout">
        <input type="hidden"
               name="${_csrf.parameterName}"
               value="${_csrf.token}">
        <button type="submit">Đăng xuất</button>
    </form>
</body>
</html>
~~~

**Phân biệt quan trọng:**

- JSP expression language `${note}` xuất trực tiếp vào HTML **không tự bảo đảm escaping** như `th:text`. Dùng `<c:out>` cho HTML text hoặc encoder tương ứng với ngữ cảnh.
- `request.userPrincipal` phản ánh người dùng hiện tại khi Spring Security/Servlet request wrapper được cấu hình đúng. Trang phải yêu cầu authenticated hoặc xử lý principal vắng mặt.
- `_csrf.parameterName` và `_csrf.token` lấy từ request attribute, không tự phát token trong JSP.
- `${pageContext.request.contextPath}` giúp tạo URL đúng khi ứng dụng không nằm ở context path `/`.
- Nếu ứng dụng dùng Spring MVC form tag library, có cơ chế field binding/error display riêng; vẫn cần Spring Security xử lý CSRF ở filter.

JSP trên Spring Boot 3/Jakarta Servlet cần JSP engine/container/Jakarta JSTL phù hợp (ví dụ Jasper trên Tomcat), view resolver và kiểu đóng gói phù hợp; thường dùng WAR hoặc cấu hình container có hỗ trợ JSP thay vì coi executable JAR luôn chạy được JSP. Các version dependency phải khớp Boot/Jakarta JSP đang triển khai.

**Chỉ trong một dự án JSP**, ví dụ:

~~~properties
spring.mvc.view.prefix=/WEB-INF/jsp/
spring.mvc.view.suffix=.jsp
~~~

Không áp nguyên cấu hình resolver này vào ví dụ Thymeleaf ở mục 5, trừ khi chủ đích tổ chức nhiều resolver. Các snippet JSP là **minh họa view**, không phải project runnable độc lập nếu thiếu JSP runtime.

### 7.1. Bảng đối chiếu Thymeleaf với JSP

| Tác vụ | Thymeleaf | JSP |
| --- | --- | --- |
| Hiển thị username | `sec:authentication="name"` hoặc Model | `request.userPrincipal` / Spring Security JSP taglibs |
| Đưa CSRF vào form | `th:name="${_csrf.parameterName}"`, `th:value="${_csrf.token}"` | `name="${_csrf.parameterName}"`, `value="${_csrf.token}"` |
| Escape HTML text | `th:text` | `<c:out>` |
| Form binding | `th:object`, `th:field`, `th:errors` | Spring form taglib hoặc HTML form + model errors |
| UI theo role | `sec:authorize` | Spring Security JSP taglib hoặc Model |
| Server authorization | `SecurityFilterChain`/method security | `SecurityFilterChain`/method security |
| Runtime | Template engine | JSP compiler, JSTL, container, view resolver |

**Kết luận:** engine render khác nhau, nhưng **CSRF filter và xác thực quyền ở server** là cùng trách nhiệm của Spring Security.

## 8. Login, logout và tình huống nâng cao

### 8.1. Tự viết trang login

Nếu không dùng trang mặc định, có thể tạo custom Thymeleaf form:

~~~html
<form method="post" action="/login">
    <input name="username" autocomplete="username">
    <input name="password" type="password"
           autocomplete="current-password">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Đăng nhập</button>
</form>
~~~

Đây là **fragment**, không phải app hoàn chỉnh. Để dùng custom page, phải khai báo loginPage và tạo GET controller trả view:

~~~java
// Trích đoạn bên trong cấu hình HttpSecurity:
.formLogin(form -> form.loginPage("/login").permitAll())
~~~

**Login POST cũng cần CSRF token** nếu CSRF đang bật, giúp giảm login CSRF. Đừng viết code tự so sánh password trong controller nếu Spring Security đã cung cấp authentication filter/provider.

### 8.2. Logout qua POST

Với CSRF bật, `POST /logout` là cách dùng thông thường. `GET /logout` trong một số cấu hình chỉ hiện trang xác nhận; không dựa vào link GET để đổi trạng thái. Khi session/logout thay đổi, token cũ có thể hết hiệu lực.

### 8.3. AJAX gửi JSON từ trang MVC

Nếu một phần view gửi fetch/AJAX, có thể expose token và tên header dưới dạng meta:

~~~html
<meta name="_csrf" th:content="${_csrf.token}">
<meta name="_csrf_header" th:content="${_csrf.headerName}">
~~~

Rồi gửi header khi POST:

~~~javascript
const token = document.querySelector('meta[name="_csrf"]').content;
const header = document.querySelector('meta[name="_csrf_header"]').content;

const headers = { "Content-Type": "application/json" };
headers[header] = token;

const response = await fetch("/api/action", {
    method: "POST",
    credentials: "same-origin",
    headers,
    body: JSON.stringify({ action: "save" })
});

if (!response.ok) throw new Error("Request failed");
~~~

Đây là **đoạn browser JavaScript minh họa**, giả định API `/api/action` đã được triển khai và bảo vệ đúng cách; không phải một thành phần có sẵn trong project mục 5. Với SPA cross-origin/cookie CSRF repository, cần thiết kế thêm CORS, SameSite, token lifecycle và request handler phù hợp; không dùng tùy tiện raw token từ cookie nếu cấu hình đang dùng XOR/BREACH protection.

### 8.4. Hidden fields không có quyền tự xác thực dữ liệu

CSRF token hợp lệ **không** làm `ownerId`, `role`, `price`, `approved` hoặc `isAdmin` trong hidden field thành đáng tin. Client có thể sửa mọi input trong request. Server phải kiểm tra chính chủ sở hữu từ authentication hoặc resource ownership trong DB, áp rule nghiệp vụ và dùng parameterized queries.

Nếu user không được quyền ghi vào project ID 999, chỉ kiểm tra `hasRole("USER")` là chưa đủ; service phải đối chiếu quyền với project cụ thể.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân và cách xử lý |
| --- | --- |
| POST form trả **403** sau login | Kiểm tra field CSRF, session cookie, token cũ hoặc thiếu quyền; 403 không mặc nhiên là lỗi password. |
| Form có hai field `_csrf` | `th:action`/RequestDataValueProcessor có thể tự chèn, cộng thêm hidden thủ công; dùng một phương pháp. |
| CSRF request attribute vắng mặt | Request không qua chain, CSRF bị disable, handler/view mismatch; kiểm tra cấu hình. |
| GET trang hiển thị nhưng POST báo 404 | Action sai context path hoặc mapping controller sai; dùng URL theo context. |
| `sec:authentication` không hiển thị | Kiểm tra extras dependency, namespace và security context. |
| Ẩn nút bằng `sec:authorize` nhưng gọi URL vẫn được | Thiếu server authorization; UI không thay filter/method security. |
| JSP hiện code HTML từ note | Dùng JSP EL raw thay vì escaping; áp `<c:out>`. |
| Spring Boot 3 JSP không render | Thiếu Jasper/Jakarta JSTL/view resolver, nhầm WAR/JAR, dùng namespace `javax.servlet` cũ. |
| `@Valid` không chặn input | Thiếu validation starter/constraint hoặc `BindingResult` sai vị trí. |
| POST sau logout trả 403 | Session/token đã thay đổi; tải lại form/token, không tắt CSRF. |
| Gửi token hợp lệ nhưng dữ liệu của user khác bị sửa | Lỗi authorization theo resource; xác định owner và kiểm tra quyền ở server. |
| Dùng GET để cập nhật vì “POST bị CSRF” | Sai semantics và gây lỗ hổng; sửa form có token, giữ method đổi trạng thái. |
| Curl POST với cookie vẫn 403 | Curl không tự trích CSRF field từ form GET; phải sử dụng cùng session và token hợp lệ trong test. |

## 10. Checklist nghiệm thu

1. GET trang bảo vệ khi anonymous → bị chuyển tới login hoặc phản hồi phù hợp, không lộ dữ liệu.
2. GET sau login → tên user đúng, không đọc từ field do browser tự gửi.
3. Form POST có token do server render → hợp lệ khi quyền và input hợp lệ.
4. Form POST **thiếu/sai token** → không cập nhật dữ liệu.
5. User chưa có quyền hoặc truy cập resource user khác → server từ chối dù có token hợp lệ.
6. Input rỗng/quá dài → server validation báo lỗi, không ghi.
7. Nội dung có HTML/script → được escape trong Thymeleaf/JSP, không thực thi.
8. Logout POST có token → kết thúc phiên; token cũ không được tái sử dụng ngoài chính sách.
9. Static assets, login page, error page → đúng chain và không vô tình mất security headers.
10. HTTPS, session cookie Secure/HttpOnly/SameSite, timeout và session fixation protection → phù hợp production.
11. Nếu có nhiều chain (MVC form và API bearer) → cấu hình CSRF riêng theo threat model, không disable toàn hệ thống.
12. Với JSP → đã xác nhận taglib, view resolver, container/Jakarta runtime phù hợp.

## 11. Tự kiểm tra

**Câu 1:** Đăng nhập thành công rồi, tại sao form vẫn cần CSRF token?  
**Trả lời:** Browser có thể tự đính kèm session cookie. Token bổ sung bằng chứng request đổi trạng thái xuất phát từ luồng hợp lệ của ứng dụng, không chỉ dựa vào cookie.

**Câu 2:** `sec:authorize` có bảo vệ `POST /notes` không?  
**Trả lời:** Không. Nó chỉ kiểm soát phần HTML render. Authorization phải nằm trong Spring Security filter/method/service.

**Câu 3:** Vì sao JSP nên dùng `<c:out>` để hiển thị note?  
**Trả lời:** JSP EL raw không tự HTML-escape an toàn như `th:text`. Dữ liệu chưa tin cậy phải được encode theo ngữ cảnh đầu ra.

**Câu 4:** CSRF token hợp lệ có làm field `ownerId` trở nên đáng tin không?  
**Trả lời:** Không. Hidden field vẫn do client điều khiển; server phải kiểm tra identity và ownership theo resource.

**Câu 5:** Form từ session cũ POST sau login/logout trả 403 thì nên làm gì?  
**Trả lời:** Lấy token mới qua GET/view hoặc flow refresh phù hợp, kiểm tra session và handler; không bỏ CSRF.

**Câu 6:** Nếu API hoàn toàn stateless chỉ nhận bearer token từ header, có nhất thiết dùng CSRF như form không?  
**Trả lời:** Threat model khác; cần đánh giá việc credential có tự gửi bởi browser không. Không dùng ví dụ API đó để tắt CSRF cho form/session.

---

**Ghi nhớ:** Tích hợp form với Spring Security Servlet phải kết hợp **Authentication**, **Authorization**, **CSRF token**, **server-side validation** và **output encoding**. Thymeleaf và JSP là hai cách render view, không phải hai cơ chế chống CSRF khác nhau. Spring Security xác minh request và quyền; MVC xử lý dữ liệu; template render đúng danh tính, token và nội dung đã escape.