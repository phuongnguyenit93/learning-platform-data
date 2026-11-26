# Chèn token vào form hiển thị phía máy chủ

Trong một ứng dụng Spring Security sử dụng trình duyệt và cookie phiên, việc có form đăng nhập, cập nhật hồ sơ, gửi phản hồi hay đăng xuất thường đồng nghĩa với việc phải bảo vệ các thao tác thay đổi trạng thái trước **Cross-Site Request Forgery (CSRF)**. Bài này hướng dẫn cách đưa CSRF token vào **HTML form được render trên máy chủ**, trước hết với Spring MVC/Servlet, sau đó đối chiếu với Spring WebFlux/Reactive.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Giải thích vì sao cookie phiên không đủ để xác định một form POST thực sự do người dùng chủ động gửi.
- Phân biệt **token mà máy chủ kỳ vọng**, **token được render trong HTML** và **token được gửi trở lại cùng request**.
- Sử dụng cơ chế tự chèn token của **Thymeleaf** và **Spring MVC form tags**.
- Chèn token thủ công vào form HTML/JSP khi view không hỗ trợ tích hợp tự động, tránh chèn trùng.
- Nhận diện khác biệt giữa Servlet (`CsrfFilter`, `HttpServletRequest`) và Reactive (`CsrfWebFilter`, `ServerWebExchange`, `Mono<CsrfToken>`).
- Kiểm tra các trường hợp token hợp lệ, thiếu token, sai token và xử lý lỗi HTTP 403.

**Phạm vi:** Form HTML được trả về từ máy chủ (server-side rendering); phần gọi AJAX/SPA chỉ được nhắc tới khi cần phân biệt cách truyền token. Bảo vệ CSRF phải được bật và request phải đi qua Spring Security filter chain.

## 2. Vì sao form cần token?

Giả sử người dùng đã đăng nhập ứng dụng ngân hàng tại `bank.example`. Trình duyệt tự gắn cookie xác thực vào những request phù hợp. Một trang độc hại có thể tạo form POST đến ứng dụng đó; nếu máy chủ chỉ nhìn cookie, request giả mạo có thể được xử lý như thao tác của người dùng.

CSRF token khắc phục bằng cách yêu cầu request thay đổi trạng thái mang thêm một giá trị mà trang độc hại không thể tự đọc từ trang hợp lệ. Máy chủ so sánh giá trị nhận được với token kỳ vọng gắn với ngữ cảnh bảo mật tương ứng.

```text
1. GET /feedback  ────────────────> Ứng dụng Spring
2.                                Spring Security tạo/tải CSRF token
3. <── HTML có hidden input _csrf ── View engine render form
4. Người dùng submit form:
   POST /feedback
   Cookie phiên + message + _csrf ─> CsrfFilter kiểm tra token
5.                                Hợp lệ: xử lý POST
                                  Thiếu/sai: từ chối (mặc định 403)
```

Điểm cốt lõi: trình duyệt **tự gửi cookie** nhưng **không tự biết giá trị token của trang hợp lệ để đưa vào trường form**. Vì vậy token phải được thêm vào dữ liệu request, thường qua hidden input:

```html
<form method="post" action="/feedback">
    <input name="message" type="text">
    <input type="hidden" name="_csrf" value="gia-tri-token-do-server-render">
    <button type="submit">Gửi</button>
</form>
```

`value` chỉ là giá trị minh họa. Trong ứng dụng thực, **không hardcode token**, không dùng một token cố định cho mọi người dùng và không đưa token vào URL. Hidden input vẫn hiển thị được trong DevTools; CSRF không dựa trên việc giấu token với chính người dùng. XSS vẫn có thể đọc token của trang nên phòng vệ CSRF không thay thế việc chống XSS.

Các method `GET`, `HEAD`, `OPTIONS`, `TRACE` được xem là an toàn theo mặc định; không dùng chúng để thực hiện thay đổi trạng thái. Spring Security mặc định kiểm tra CSRF đối với các method không an toàn như `POST`, `PUT`, `PATCH`, `DELETE`.

## 3. Cơ chế Spring Security trên Servlet

Với cấu hình thông thường, Spring Security **bật CSRF mặc định**. Các thành phần liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `CsrfFilter` | Chặn request cần CSRF, đọc token từ request và kiểm tra token. |
| `CsrfTokenRepository` | Tạo, lưu và tải token kỳ vọng; mặc định dùng `HttpSessionCsrfTokenRepository`. |
| `CsrfTokenRequestHandler` | Cung cấp token cho tầng view và lấy token do client gửi tới. |
| `CsrfRequestDataValueProcessor` | Kết nối với view engine/Spring form tags để tự sinh hidden input cho các form thích hợp. |
| Thuộc tính `_csrf` | Thuộc tính của `HttpServletRequest` cho phép template truy cập `parameterName`, `token` và `headerName`. |

Từ Spring Security 6, token được **tải trì hoãn** khi cần, chẳng hạn khi render form hoặc xử lý POST. Handler mặc định là `XorCsrfTokenRequestAttributeHandler`, xuất giá trị đã được che/mã hóa để giảm rủi ro BREACH. Vì thế, **giá trị hiển thị trong hai lần GET có thể khác nhau dù token lưu trong phiên không đổi**. Không so sánh chuỗi hidden input giữa các lần render để kết luận lỗi; hãy kiểm tra bằng cách gửi token do chính trang đó render.

Khi submit form, tham số thường mang tên `_csrf`, nhưng tên thật lấy từ `_csrf.parameterName`. Không phụ thuộc vào tên mặc định nếu ứng dụng có cấu hình tùy chỉnh.

## 4. Ví dụ Spring MVC + Thymeleaf: tự động chèn token

### 4.1. Cấu hình tối thiểu

Với Spring Boot (Servlet), dùng các dependency phù hợp:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
implementation 'org.springframework.boot:spring-boot-starter-security'
implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
```

Cấu hình bên dưới cho phép mở trang phản hồi mà không cần đăng nhập, để quan sát rằng `permitAll()` **không tắt CSRF** đối với POST:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/feedback").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

Trong ứng dụng thực tế, phân quyền cho từng endpoint theo nghiệp vụ; `permitAll()` ở đây chỉ giúp bài thực hành dễ kiểm chứng.

Controller nhận GET để trả view và POST để mô phỏng lưu dữ liệu:

```java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class FeedbackController {

    @GetMapping("/feedback")
    String form() {
        return "feedback";
    }

    @PostMapping("/feedback")
    String submit(@RequestParam String message,
                  RedirectAttributes redirectAttributes) {
        // Ở hệ thống thật: validate và ghi dữ liệu theo nghiệp vụ.
        redirectAttributes.addFlashAttribute("result", "Đã gửi: " + message);
        return "redirect:/feedback";
    }
}
```

Tạo `src/main/resources/templates/feedback.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Gửi phản hồi</title>
</head>
<body>
    <p th:if="${result}" th:text="${result}"></p>

    <form th:action="@{/feedback}" method="post">
        <label for="message">Nội dung</label>
        <input id="message" name="message" required>
        <button type="submit">Gửi phản hồi</button>
    </form>
</body>
</html>
```

**Không cần tự viết hidden input** trong mẫu này. Khi Thymeleaf xử lý `th:action` với form POST và tích hợp Spring/Spring Security, `CsrfRequestDataValueProcessor` thêm token vào form. Kiểm tra tab **Network → Response** của `GET /feedback` hoặc **View Page Source** để thấy HTML đã render có dạng:

```html
<form action="/feedback" method="post">
    <label for="message">Nội dung</label>
    <input id="message" name="message" required>
    <button type="submit">Gửi phản hồi</button>
    <input type="hidden" name="_csrf" value="token-thuc-te-duoc-sinh-tu-server">
</form>
```

Vị trí và giá trị thực tế của hidden input có thể khác ví dụ. Khi bấm **Gửi phản hồi**, trình duyệt gửi cả `message` lẫn `_csrf` trong body cùng cookie phiên; `CsrfFilter` kiểm tra token trước khi request đến controller.

### 4.2. Khi phải chèn thủ công với Thymeleaf

Với form HTML thuần hoặc hệ thống template tùy biến không kích hoạt tích hợp tự động, có thể dùng thuộc tính `_csrf`:

```html
<!-- Chỉ dùng cách thủ công khi form không được tự chèn token -->
<form action="/feedback" method="post">
    <input name="message" required>
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Gửi</button>
</form>
```

Đoạn này giả định template được render với Thymeleaf và thuộc tính `_csrf` hiện diện trong request. Nếu ứng dụng được triển khai dưới context path khác `/`, cần xây dựng URL action tương ứng. **Không trộn cách thủ công với cơ chế tự động** nếu nó đã chèn token; cách dễ kiểm tra nhất là xem HTML cuối cùng và đảm bảo mỗi form có một trường token hợp lệ.

## 5. JSP và Spring MVC form tag

### 5.1. Spring form tag tự thêm token

Khi dùng thư viện Spring MVC form tags, `<form:form>` tích hợp với `RequestDataValueProcessor`:

```jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form action="/feedback" method="post">
    <label for="message">Nội dung</label>
    <input id="message" name="message">
    <button type="submit">Gửi</button>
</form:form>
```

Với tích hợp đúng, Spring Security tự thêm input CSRF vào HTML trả về. **Không thêm thủ công** trường `_csrf` bên trong `<form:form>` chỉ vì không thấy nó trong mã nguồn JSP: phải kiểm tra HTML đã render.

### 5.2. Form HTML thuần trong JSP

Nếu sử dụng thẻ `<form>` thường, có thể đọc trực tiếp thuộc tính request `_csrf` và dùng JSTL `c:url` để tạo URL theo context của ứng dụng:

```jsp
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<c:url var="feedbackUrl" value="/feedback" />

<form action="${feedbackUrl}" method="post">
    <input name="message">
    <input type="hidden"
           name="${_csrf.parameterName}"
           value="${_csrf.token}">
    <button type="submit">Gửi</button>
</form>
```

Ví dụ trên dùng URI taglib JSTL cho môi trường Jakarta hiện đại; với ứng dụng cũ dùng Java EE, URI có thể là `http://java.sun.com/jsp/jstl/core`. Phải dùng phiên bản JSTL tương thích với nền tảng thực tế.

Nếu dự án có module `spring-security-taglibs`, có thể dùng thẻ **`<sec:csrfInput />`** thay cho input thủ công:

```jsp
<%@ taglib prefix="sec" uri="http://www.springframework.org/security/tags" %>

<form action="/feedback" method="post">
    <input name="message">
    <sec:csrfInput />
    <button type="submit">Gửi</button>
</form>
```

`sec:csrfInput` sinh hidden input khi CSRF đang được bật. Thẻ này hữu ích trong HTML form thường, **không dùng lặp lại trong `<form:form>`** vốn đã có cơ chế tự động.

## 6. Đối chiếu với Spring WebFlux/Reactive

Trong WebFlux, thành phần tương ứng là `CsrfWebFilter`, mặc định lưu token trong `WebSession` thông qua `WebSessionServerCsrfTokenRepository`. Thay vì trực tiếp lấy `CsrfToken` từ `HttpServletRequest` như Servlet, Spring Security cung cấp **`Mono<CsrfToken>`** trong thuộc tính của `ServerWebExchange` với khóa `CsrfToken.class.getName()`.

| Nội dung | Spring MVC / Servlet | Spring WebFlux / Reactive |
| --- | --- | --- |
| Bộ lọc | `CsrfFilter` | `CsrfWebFilter` |
| Nơi lưu mặc định | `HttpSession` | `WebSession` |
| Thuộc tính ban đầu | `_csrf` trong request | `Mono<CsrfToken>` trong exchange |
| Template tích hợp | Thymeleaf, Spring MVC form tags | Thymeleaf tích hợp Reactive |
| Mục tiêu khi render | Hidden input có tên/giá trị từ `CsrfToken` | Hidden input có tên/giá trị từ `CsrfToken` sau khi `Mono` được xử lý |

Ví dụ cấu hình WebFlux (sử dụng thay cho Servlet; **không ghép hai filter chain vào cùng một ví dụ ứng dụng**):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.config.web.server.ServerHttpSecurity;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/feedback").permitAll()
                        .anyExchange().authenticated())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

Trong **WebFlux + Thymeleaf**, form `<form th:action="@{/feedback}" method="post">` vẫn có thể tự chèn token nhờ tích hợp với `RequestDataValueProcessor`. Khi dùng view engine tự tạo, cần bảo đảm `Mono<CsrfToken>` được subscribe/xử lý trước khi render token. Không ép kiểu thuộc tính exchange trực tiếp thành `CsrfToken` và cũng không dùng `block()` tùy tiện trong luồng reactive.

Nếu một template tùy biến cần truy cập `_csrf`, một cách là expose token qua model:

```java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@ControllerAdvice
public class ReactiveCsrfModelAdvice {

    @ModelAttribute
    Mono<CsrfToken> csrfForView(ServerWebExchange exchange) {
        Mono<CsrfToken> tokenPublisher =
                exchange.getAttribute(CsrfToken.class.getName());

        if (tokenPublisher == null) {
            return Mono.empty();
        }

        return tokenPublisher.doOnNext(token ->
                exchange.getAttributes().put("_csrf", token));
    }
}
```

Đây là **phương án dành cho template cần xử lý thủ công**; Thymeleaf đã tích hợp đúng thường không cần lớp này. Thuộc tính `_csrf` chỉ có sau khi publisher được xử lý, nên phải xác minh lifecycle render của view engine và không tạo thêm trường token nếu nó đã tự thêm.

## 7. Kiểm thử form được bảo vệ

### 7.1. Kiểm tra trực tiếp trong trình duyệt

1. Mở `GET /feedback`; xem HTML trả về phải có `<input type="hidden" ...>` với tên token thích hợp.
2. Mở **Network**, submit form và kiểm tra `POST /feedback`: phần **Form Data / Payload** phải có cả dữ liệu nghiệp vụ và tham số CSRF, đồng thời cookie phiên phù hợp.
3. Submit bình thường: request qua được bước kiểm tra CSRF và nhận kết quả nghiệp vụ (ví dụ redirect 302).
4. Dùng DevTools **Copy as cURL** rồi bỏ tham số CSRF hoặc thay giá trị bằng chuỗi sai, giữ nguyên cookie: mặc định request bị chặn với **403 Forbidden**.
5. Thử submit lại form cũ sau đăng nhập/đăng xuất hoặc thay phiên: nếu token cũ không còn khớp thì phải tải lại trang để nhận token mới.

Lưu ý: POST có token hợp lệ vẫn có thể bị từ chối vì **xác thực, phân quyền hoặc validation**; token hợp lệ chỉ chứng minh đã vượt qua kiểm tra CSRF.

### 7.2. Tự động hóa với MockMvc (Servlet)

Ví dụ sau kiểm tra cả HTML render và hành vi chấp nhận/từ chối ở `/feedback`:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
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
class FeedbackCsrfTests {

    @Autowired
    MockMvc mvc;

    @Test
    void formRendersCsrfInput() throws Exception {
        mvc.perform(get("/feedback"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void missingTokenIsForbidden() throws Exception {
        mvc.perform(post("/feedback").param("message", "xin chao"))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongTokenIsForbidden() throws Exception {
        mvc.perform(post("/feedback")
                        .with(csrf().useInvalidToken())
                        .param("message", "xin chao"))
                .andExpect(status().isForbidden());
    }

    @Test
    void validTokenReachesController() throws Exception {
        mvc.perform(post("/feedback")
                        .with(csrf())
                        .param("message", "xin chao"))
                .andExpect(status().is3xxRedirection());
    }
}
```

`csrf()` là công cụ kiểm thử từ `spring-security-test`, dùng để thêm token hợp lệ cho request MockMvc; `useInvalidToken()` cố ý tạo token không hợp lệ. Nó không thay thế kiểm thử **HTML thực sự có hidden input**; hai nhóm kiểm thử bổ sung cho nhau.

Với WebFlux, `spring-security-test` cung cấp `WebTestClient` mutator `SecurityMockServerConfigurers.csrf()`:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

// Giả định WebTestClient đã được cấu hình với Spring Security.
webTestClient.mutateWith(csrf())
        .post()
        .uri("/feedback")
        .bodyValue("message=xin+chao")
        .header("Content-Type", "application/x-www-form-urlencoded")
        .exchange();
```

Ở đoạn WebFlux, status thành công cụ thể tùy controller và cấu hình authorization; nên thêm assertion phù hợp endpoint thực tế. Kiểm thử thiếu hoặc sai token riêng để xác nhận WebFlux trả HTTP 403 khi request thuộc phạm vi bảo vệ CSRF.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| POST trả 403, không vào controller | Thiếu hoặc sai CSRF token | Kiểm tra payload của POST và input đã render; so sánh với token kỳ vọng trong đúng phiên. |
| Template có `th:action` nhưng không thấy hidden input | Trang được phục vụ như file tĩnh, chưa qua Thymeleaf, hoặc tích hợp security/view không đúng | Xác nhận GET đi qua controller và template engine; xem Response HTML thực tế. |
| HTML có hai trường `_csrf` | Tự thêm thủ công trong form vốn được framework chèn tự động | Chọn **một** cơ chế chèn token, render lại và kiểm tra. |
| Form cũ bị 403 sau login/logout | Token được làm mới hoặc phiên thay đổi | Tải lại form để nhận token tương ứng với trạng thái xác thực/phiên hiện tại. |
| POST vẫn 403 dù token nhìn có vẻ đúng | Cookie phiên không khớp, token đã hết hiệu lực hoặc request bị rule khác từ chối | Gửi cookie và token từ cùng lượt GET; xem log security ở môi trường phát triển. |
| Form HTML thuần bị 403 trong khi `form:form` hoạt động | Form thuần không tích hợp `RequestDataValueProcessor` | Thêm input theo `_csrf` hoặc `<sec:csrfInput />` cho JSP. |
| WebFlux hiển thị chuỗi Mono hoặc không có token | Chưa giải quyết `Mono<CsrfToken>` trước khi render | Dùng tích hợp Thymeleaf phù hợp, hoặc expose token vào model theo lifecycle Reactive. |
| Form có token nhưng lệnh `fetch`/AJAX vẫn lỗi | Request JavaScript không tự gửi hidden input HTML | Gửi token qua tham số form hoặc header CSRF phù hợp với request JavaScript. |

Những lưu ý triển khai:

- **Không tắt CSRF để sửa lỗi form** bằng `csrf.disable()` khi ứng dụng vẫn dùng cookie phiên và có request đổi trạng thái. `permitAll()`, CORS và `SameSite` cũng không tự thay thế bước kiểm tra token.
- **Không đặt token trong query string**, URL form action hay log. URL dễ xuất hiện trong lịch sử, log truy cập và các bối cảnh rò rỉ khác.
- **Không cache HTML chứa token theo kiểu dùng chung giữa nhiều phiên**; trang động cần trả về token của đúng ngữ cảnh người dùng.
- **Mỗi form thực hiện thao tác thay đổi trạng thái cần được bao phủ**: gửi dữ liệu, login, logout, xoá, cập nhật... Trong Spring Security, logout mặc định được bảo vệ qua POST.
- Nếu dùng upload `multipart/form-data`, cần xem xét thứ tự xử lý multipart và CSRF vì đọc multipart body có thể tạo tệp tạm trước khi xác thực CSRF; đây là một điểm cần kiểm tra riêng khi triển khai.
- Với `PUT`, `PATCH` hay `DELETE` được tạo từ form qua `_method`, vẫn phải bảo vệ request thay đổi trạng thái và kiểm tra cách ứng dụng chuyển đổi HTTP method.

## 9. Bài thực hành và tiêu chí hoàn thành

**Tình huống:** Xây dựng form `/feedback` như mục 4 và bảo đảm chỉ các POST mang CSRF token hợp lệ mới được chấp nhận.

1. Chạy ứng dụng, GET trang và xác minh token nằm trong HTML trả về; giải thích thành phần nào đã chèn nó.
2. Submit bằng trình duyệt và quan sát payload; ghi lại tên tham số token, method, status và đích redirect.
3. Gửi cùng request nhưng bỏ token; giải thích vì sao token bị thiếu dẫn đến 403 dù `/feedback` được `permitAll()`.
4. Thay token bằng giá trị bất kỳ và quan sát 403; phân biệt lỗi CSRF với lỗi phân quyền.
5. Chuyển form sang HTML/JSP thủ công; áp dụng đúng một cách chèn token, kiểm tra lại ba trường hợp hợp lệ, thiếu và sai.
6. Nếu có ứng dụng WebFlux, giải thích tại sao không nên lấy `Mono<CsrfToken>` bằng cast sang `CsrfToken`; sử dụng Thymeleaf tích hợp hoặc quy trình expose token đúng.

**Đạt yêu cầu** khi người học chỉ ra chính xác hidden input trong HTML đã render, chứng minh request có/không có token cho kết quả phù hợp và giải thích được vai trò của Spring Security thay vì chỉ thêm thủ công một trường `_csrf` bất kỳ.

## Tài liệu tham khảo

- [Spring Security — CSRF cho Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): cơ chế repository, handler, tự chèn token và bảo vệ BREACH.
- [Spring Security — JSP Tag Libraries](https://docs.spring.io/spring-security/reference/servlet/integrations/jsp-taglibs.html): `csrfInput` và tích hợp với `form:form`.
- [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, `useInvalidToken()`.
- [Spring Security — CSRF cho WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `CsrfWebFilter`, `Mono<CsrfToken>` và Thymeleaf Reactive.
- [Spring Security — WebTestClient CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `SecurityMockServerConfigurers.csrf()`.
