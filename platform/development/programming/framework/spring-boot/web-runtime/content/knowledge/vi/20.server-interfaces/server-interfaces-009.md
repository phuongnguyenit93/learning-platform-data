# Escaping dữ liệu, liên kết URL và biểu mẫu an toàn trong giao diện máy chủ Spring Boot

## 1. Mục tiêu và phạm vi

Giao diện máy chủ (*server-rendered UI*) thường dùng **Spring MVC + Thymeleaf** để biến dữ liệu từ controller, database và người dùng thành HTML. Nếu dữ liệu không đáng tin cậy được đặt vào HTML, đường dẫn URL, JavaScript hoặc biểu mẫu sai cách, trình duyệt có thể diễn giải dữ liệu thành mã hoặc thao tác ngoài ý muốn. Bài này trình bày cách hiển thị an toàn, tạo liên kết và tiếp nhận form trong **Spring Boot web runtime**, tập trung vào Thymeleaf 3.x, Spring MVC và Spring Security.

Học xong bài, bạn cần làm được những việc sau:

1. Phân biệt dữ liệu thuần với mã HTML/JavaScript và chọn **escaping đúng ngữ cảnh đầu ra**.
2. Dùng `th:text`, `th:value`, `th:field`, `th:href="@{...}"`, `th:action="@{...}"` thay cho nối chuỗi HTML và URL thủ công.
3. Biết tại sao **HTML escaping không đủ để xác minh một URL**, và vì sao liên kết ngoài phải được kiểm tra scheme/host/đích.
4. Thiết kế biểu mẫu POST có **server-side validation**, **CSRF protection**, phân quyền và luồng phản hồi hợp lý.
5. Kiểm thử rằng chuỗi chứa thẻ HTML vẫn hiển thị như văn bản, URL được encode, input sai bị từ chối và POST không có CSRF token không được chấp nhận.

Nguyên tắc quan trọng nhất: **dữ liệu chỉ được coi là dữ liệu**. Tại mỗi điểm xuất ra trình duyệt, phải biết trình duyệt sẽ phân tích nó như **HTML text**, **HTML attribute**, **URL**, **JavaScript**, **CSS** hay một bối cảnh khác. Không có một hàm escape chung an toàn cho mọi ngữ cảnh.

## 2. Threat model: dữ liệu không tin cậy có thể đi vào giao diện ở đâu?

Nguồn dữ liệu không tin cậy không chỉ là `@RequestParam`. Nó còn có thể là: trường trong database, nhận xét của người dùng, phản hồi API ngoài, nội dung import từ file, giá trị từ queue, URL callback, metadata upload, lỗi validation hoặc dữ liệu đã lưu từ trước (*stored XSS*).

Ví dụ, người dùng nhập:

```text
<img src=x onerror=alert(1)>
```

Nếu coi đây là **text**, trang nên hiển thị nguyên chuỗi như một đoạn chữ. Nếu ghép trực tiếp chuỗi đó vào HTML mà không mã hóa đúng, trình duyệt có thể tạo thẻ `img`, dẫn tới thực thi event handler. XSS còn xuất hiện ở attribute, URL scheme, code JavaScript, CSS và DOM API phía client.

Một ví dụ khác:

```text
javascript:alert(1)
```

Chuỗi này có thể đã được **HTML-attribute-escaped** an toàn về dấu nháy nhưng vẫn là một URL nguy hiểm nếu được gán cho `href`. Nghĩa là **escaping cú pháp** và **xác thực ngữ nghĩa/cho phép đích** là hai bước khác nhau.

| Ngữ cảnh đầu ra | Cách xử lý ưu tiên | Điều dễ mắc sai |
| --- | --- | --- |
| Nội dung text của HTML element | `th:text` hoặc `[[...]]` trong template HTML | `th:utext` hoặc `[(...)]` với dữ liệu người dùng |
| Thuộc tính HTML thông thường | `th:value`, `th:title`, `th:attr` với giá trị được kiểm soát | Tạo cả chuỗi markup bằng nối chuỗi |
| URL path/query do ứng dụng tạo | `th:href="@{/path(...)}"`, `th:src="@{...}"` | Ghép `"?q=" + query` hoặc gán toàn bộ URL do client đưa |
| JavaScript literal | Tách dữ liệu khỏi script; nếu cần, `th:inline="javascript"` và `[[...]]` | Nối vào JavaScript string hoặc dùng `[(...)]` |
| CSS | Tốt nhất chọn CSS class cố định theo allowlist | Đưa CSS declaration/`url(...)` tự do từ người dùng |
| Form body | `th:field` + Bean Validation phía server + CSRF | Tin `required`/`maxlength` ở browser hoặc bỏ CSRF |

**Escape không thay thế validation và authorization**. Cả khi hiển thị an toàn, ứng dụng vẫn cần xác nhận dữ liệu đúng nghiệp vụ, không cho một tài khoản sửa tài nguyên của người khác và bảo vệ các request thay đổi trạng thái.

## 3. Thymeleaf: `th:text` thay cho `th:utext`

Trong template Thymeleaf, cách đơn giản nhất để in nội dung không tin cậy là `th:text`:

```html
<p th:text="${userComment}">Nội dung mẫu</p>
```

Nếu `userComment` là `<strong>Xin chào</strong>`, phần HTML được tạo ra chứa ký tự dạng escaped, chẳng hạn:

```html
<p>&lt;strong&gt;Xin chào&lt;/strong&gt;</p>
```

Trình duyệt hiển thị chữ `<strong>Xin chào</strong>` chứ không biến nó thành thẻ in đậm.

Cú pháp inlining được escape `[[${userComment}]]` tương đương về ý nghĩa với `th:text` trong phần text của template HTML:

```html
<p>Bình luận: [[${userComment}]]</p>
```

**Không đưa nội dung không tin cậy vào `th:utext` hoặc `[(...)]`**, bởi hai cách này cho phép sinh HTML không escape:

```html
<!-- ANTI-PATTERN: không dùng cho bình luận do user nhập -->
<div th:utext="${userComment}"></div>
<div>[(${userComment})]</div>
```

Nếu nghiệp vụ thật sự hỗ trợ rich text do người dùng soạn (ví dụ văn bản có `<b>` và `<i>`), hãy dùng **HTML sanitizer theo allowlist** để giữ đúng những tag/attribute được phép và bỏ script/event handlers/URL scheme nguy hiểm. Sau đó mới render nội dung đã sanitize trong cơ chế riêng, với test bảo mật và Content Security Policy bổ trợ. Đừng dùng `th:utext` với HTML thô từ database, cũng đừng tự xây sanitizer bằng regex.

**Không escape hai lần:** nếu server gọi một hàm tạo `&lt;` trước rồi truyền vào `th:text`, dấu `&` có thể lại thành `&amp;`, khiến người dùng thấy các entity thay vì chữ mong muốn. Giữ dữ liệu ở dạng text thô trong model; để template engine escape tại điểm output.

## 4. Attribute encoding và các ngữ cảnh nguy hiểm

Các processor như `th:value`, `th:title`, `th:alt` đưa dữ liệu vào attribute được định dạng theo quy tắc template. Ví dụ:

```html
<input type="text" th:value="${displayName}">
<img th:src="@{/images/logo.svg}" th:alt="${imageDescription}">
```

Khi `displayName` chứa dấu nháy hoặc ký tự đặc biệt, Thymeleaf tạo attribute với escaping cần thiết. Đừng tạo HTML bằng string:

```java
// ANTI-PATTERN: tạo HTML trực tiếp từ input, không dùng.
String html = "<input value=\"" + userValue + "\">";
```

Tuy nhiên, việc attribute được quote/escape **không biến một giá trị thành an toàn về ngữ nghĩa**:

- `th:href="${externalUrl}"` có thể nhận `javascript:...` hoặc URL giả mạo nếu giá trị được lấy tự do từ client.
- `th:onclick`, `th:onload` và các JavaScript event-handler attributes là **ngữ cảnh code**; đừng đặt nội dung tự do từ người dùng vào đó.
- `th:style` và CSS động có thể tạo hành vi ngoài ý muốn; ưu tiên chọn trong một danh sách CSS class cố định.
- `th:attr` có thể đặt tên thuộc tính linh hoạt, nhưng tên thuộc tính đến từ input là một bề mặt không an toàn; giữ tên attribute cố định ở phía server.
- Có thể dùng `data-*` attribute đã được encode để chuyển dữ liệu cho JavaScript **bằng DOM API**, rồi gán bằng `textContent`. Tránh `innerHTML` với dữ liệu chưa sanitize.

Nếu phải nhúng dữ liệu vào inline JavaScript, dùng đúng chế độ Thymeleaf:

```html
<script th:inline="javascript">
  const displayName = [[${displayName}]];
  console.log(displayName);
</script>
```

Ở đây `[[...]]` trong **JavaScript inlining mode** tạo literal được encode theo JavaScript, gồm dấu nháy. Không tự bọc thêm dấu nháy quanh biểu thức, không dùng `[(...)]` và không xây script block từ input. Trong ứng dụng nghiêm ngặt, ưu tiên script file riêng với **CSP** thích hợp và truyền dữ liệu qua DOM/data attributes hoặc JSON endpoint; cần xử lý mọi ngữ cảnh theo đúng chính sách CSP và cách template được render.

## 5. Liên kết URL an toàn: xây dựng, encode và giới hạn đích

### 5.1. Không nối tay query string

Giả sử tìm kiếm nhận `q = a&b có dấu cách`. Cách viết sau dễ sai:

```html
<!-- ANTI-PATTERN: nhầm dấu & của dữ liệu với dấu & phân tách query -->
<a th:href="|/search?q=${q}|">Tìm kiếm</a>
```

Cách rõ ràng hơn là **link expression** `@{...}`:

```html
<a th:href="@{/search(q=${q})}">Tìm kiếm</a>
```

Thymeleaf xây URL theo context path và **mã hóa tham số query** phù hợp. Giá trị `a&b` trở thành một tham số `q` chứa ampersand trong dữ liệu (thường biểu diễn `q=a%26b`) thay vì bị tách thành các tham số mới. Khi có nhiều query params, dấu `&` phân cách tham số trong HTML source còn được escape như attribute HTML, đó là bước khác với percent-encoding dữ liệu.

Ví dụ hai tham số:

```html
<a th:href="@{/search(q=${q},page=${page})}">Trang tiếp theo</a>
```

Giá trị `page` vẫn cần được xác thực phía server (số nguyên dương, giới hạn độ lớn); encode URL không kiểm tra logic nghiệp vụ.

### 5.2. Encode path variable thay vì ghép cả URL

```html
<a th:href="@{/products/{id}(id=${productId})}">Chi tiết</a>
```

`productId` được Thymeleaf đưa vào placeholder. Nó nên là **ID/slug đã xác thực** (ví dụ số hoặc slug thuộc allowlist), không phải một đường dẫn bất kỳ do client đưa. URL encoding chỉ bảo vệ cú pháp và giúp truyền giá trị, **không thay thế phân quyền truy cập ID** và không tự ngăn những giá trị có ý nghĩa như `..` hoặc ký tự phân tách dẫn đến xử lý route ngoài dự kiến ở proxy/container.

Nếu link phải đưa tới URL ngoài hệ thống, không dùng thẳng toàn bộ `next` hoặc `returnUrl` từ query:

```html
<!-- ANTI-PATTERN: full URL không được kiểm tra có thể là scheme độc hại -->
<a th:href="${returnUrl}">Quay lại</a>
```

Chính sách phù hợp: ưu tiên relative route do server chọn, hoặc parse URL rồi **allowlist scheme `https`, hostname/port đích, và mục đích sử dụng**. Không dùng `startsWith("https://trusted.com")` để kiểm tra host, vì `https://trusted.com.attacker.example` có thể vượt qua kiểm tra chuỗi. Với redirect sau form/login, chỉ cho phép **đích tương đối nội bộ hoặc danh sách redirect URI đã đăng ký**, tránh *open redirect* và phishing. Header `Location` cũng phải được tạo có kiểm soát.

Với link mở tab mới:

```html
<a href="https://example.org/docs"
   target="_blank"
   rel="noopener noreferrer">Tài liệu bên ngoài</a>
```

`rel="noopener noreferrer"` giảm một số rủi ro liên quan cửa sổ được mở và referrer; nó **không xác minh độ tin cậy của destination**.

### 5.3. URL trong browser, URL trong HTTP client và file path là những thứ khác nhau

Không nhầm URL output encoding với:

- **SSRF:** server gọi một URL do user cung cấp, có thể chạm IP nội bộ/metadata endpoint. Cần allowlist đích, kiểm tra redirect/DNS và chính sách network riêng.
- **Path traversal:** user điều khiển đường dẫn file hoặc static resource. Cần location containment/authorization; encode URL không bảo vệ filesystem root.
- **IDOR/BOLA:** user sửa ID trong URL để truy cập tài nguyên của người khác. Cần kiểm tra quyền theo object.
- **Open redirect:** server gửi user sang URL ngoài ý muốn. Cần giới hạn redirect target.

## 6. Form an toàn: từ HTML đến server-side validation

Một biểu mẫu tốt có cả **trải nghiệm nhập liệu tại browser** và **kiểm tra cuối cùng phía server**. HTML `required`, `maxlength`, `type=email` giúp người dùng nhận phản hồi sớm nhưng có thể bị bỏ qua bằng DevTools/curl, vì vậy không phải ranh giới tin cậy.

Với Spring MVC:

1. `@GetMapping` tạo một form object và đưa nó vào `Model`.
2. Thymeleaf dùng `th:object` và `th:field` liên kết các trường của form object vào `input`/`textarea`.
3. `@PostMapping` nhận form bằng `@ModelAttribute` và chạy `@Valid` với Jakarta Bean Validation.
4. `BindingResult` phải đứng **ngay sau tham số được validate** để controller xử lý lỗi và render lại form; không tự coi input sai là thành công.
5. Các thông báo lỗi được render bằng `th:errors`/`th:text`, không được nối HTML.
6. Sau submit hợp lệ, dùng **Post/Redirect/Get** (PRG) để refresh trang không dễ gửi lại POST; **không đồng nghĩa** request POST đã idempotent.

Ví dụ binding:

```html
<form th:action="@{/feedback}" th:object="${feedbackForm}" method="post">
  <label for="name">Tên</label>
  <input id="name" th:field="*{name}" type="text" required maxlength="80">

  <p th:if="${#fields.hasErrors('name')}"
     th:errors="*{name}">Lỗi tên</p>

  <button type="submit">Gửi</button>
</form>
```

`th:field` điền lại giá trị khi validation thất bại và áp dụng quy tắc output phù hợp. **Không tin hidden fields:** giá, userId, role, tenantId, status hoặc quyền truy cập gửi trong form đều do client sửa được. Kiểm tra authorization phía server và chỉ bind những trường mà người dùng được phép thay đổi. Tránh **mass assignment/over-posting** bằng DTO form riêng, không bind trực tiếp entity chứa trường nhạy cảm.

### CSRF: một vấn đề khác với XSS

**CSRF (Cross-Site Request Forgery)** xảy ra khi trang khác khiến browser của user đã đăng nhập gửi một yêu cầu thay đổi trạng thái ngoài ý muốn. HTML escaping giúp chống XSS ở output, **không cung cấp CSRF protection**. Với ứng dụng dựa trên cookie/session, Spring Security mặc định bảo vệ các HTTP method không an toàn như POST/PUT/PATCH/DELETE bằng token (nếu chưa thay đổi cấu hình).

Với **Spring MVC + Thymeleaf + Spring Security**, `th:action` trên form POST tích hợp với Spring `RequestDataValueProcessor`: khi cấu hình CSRF mặc định đang hoạt động, Thymeleaf có thể **tự chèn hidden input mang CSRF token** vào HTML sinh ra. Token không phải string cố định; không hardcode một token mẫu.

Ví dụ dạng HTML sau khi render (token chỉ minh họa):

```html
<form method="post" action="/feedback">
  <input type="hidden" name="_csrf" value="token-generated-for-this-request">
  <!-- các trường form -->
</form>
```

Khi form sử dụng engine khác hoặc tạo request AJAX, phải truyền CSRF token vào request theo cấu hình Spring Security, ví dụ field hoặc header. Với Spring Security 6+, cần lưu ý cơ chế **deferred token / XOR masking** và xử lý token theo tài liệu phiên bản; không tự lấy token đã mask rồi so sánh hoặc biến đổi trong application code.

**Không tắt CSRF trên toàn bộ ứng dụng để xử lý lỗi 403 của form.** Trước tiên kiểm tra template có `th:action`, Security filter chain, cookie/session và token được gửi hay không. Dùng `SameSite` cookie và `Origin`/`Referer` kiểm tra bổ trợ khi phù hợp, nhưng không mặc nhiên xem chúng là thay thế hoàn toàn cho CSRF token. Với REST API xác thực bằng bearer token gửi thủ công, threat model có thể khác; xác định cơ chế xác thực thực tế rồi quyết định CSRF policy.

## 7. Dự án mẫu chạy được: Spring Boot 3.x + Thymeleaf + Validation + Security

Bài thực hành dùng **Java 17+**, **Spring Boot 3.x**, Spring MVC, Thymeleaf, Jakarta Validation và Spring Security. Nó minh họa cả ba điểm: **text escape**, **URL query encoding** và **form POST được validate/CSRF-protected**.

Tạo dự án bằng Spring Initializr với các dependency:

- `spring-boot-starter-web`
- `spring-boot-starter-thymeleaf`
- `spring-boot-starter-validation`
- `spring-boot-starter-security`
- `spring-boot-starter-test` (scope test)
- `org.springframework.security:spring-security-test` (scope test, để gọi `csrf()` trong MockMvc)

Nếu dùng Maven với Spring Boot parent/BOM, thêm trong `pom.xml` (trong `<dependencies>`):

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

### 7.1. Lớp khởi chạy

**`src/main/java/com/example/demo/SafeUiApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeUiApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeUiApplication.class, args);
    }
}
```

### 7.2. Cấu hình security

**`src/main/java/com/example/demo/WebSecurityConfig.java`**

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/feedback", "/feedback/**").permitAll()
            .anyRequest().denyAll()
        );
        // Giữ CSRF mặc định của Spring Security.
        return http.build();
    }
}
```

Đây là ứng dụng **demo công khai**; `permitAll` cho phép vào màn hình feedback và submit form, nhưng **CSRF vẫn được kiểm tra đối với POST**. Đối với form tài khoản, đơn hàng hoặc tài liệu riêng, cần yêu cầu xác thực và kiểm tra quyền theo user/object thay vì `permitAll`.

### 7.3. Controller với form DTO riêng

**`src/main/java/com/example/demo/FeedbackController.java`**

```java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class FeedbackController {

    private static final String SAFE_SLUG = "huong-dan";

    @GetMapping("/feedback")
    public String feedbackPage(
            @RequestParam(name = "q", defaultValue = "") String q,
            Model model) {
        return renderForm(q, model);
    }

    @GetMapping("/feedback/{slug}")
    public String feedbackPageForSlug(
            @PathVariable String slug,
            @RequestParam(name = "q", defaultValue = "") String q,
            Model model) {
        if (!SAFE_SLUG.equals(slug)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return renderForm(q, model);
    }

    private String renderForm(String q, Model model) {
        if (!model.containsAttribute("feedbackForm")) {
            model.addAttribute("feedbackForm", new FeedbackForm());
        }
        // q có thể chứa HTML/URL ký tự đặc biệt: để template escape.
        model.addAttribute("query", q);
        model.addAttribute("safeSlug", SAFE_SLUG);
        return "feedback";
    }

    @PostMapping("/feedback")
    public String submit(
            @Valid @ModelAttribute("feedbackForm") FeedbackForm form,
            BindingResult errors,
            Model model,
            RedirectAttributes redirect) {
        if (errors.hasErrors()) {
            model.addAttribute("query", "");
            model.addAttribute("safeSlug", SAFE_SLUG);
            return "feedback";
        }

        // Chỉ minh họa luồng submit hợp lệ, không lưu database.
        // Giá trị user nhập đi qua flash attribute và được render escaped.
        redirect.addFlashAttribute("submittedName", form.getName());
        return "redirect:/feedback";
    }

    public static class FeedbackForm {
        @NotBlank(message = "Tên không được để trống")
        @Size(max = 80, message = "Tên tối đa 80 ký tự")
        private String name;

        @NotBlank(message = "Nội dung không được để trống")
        @Size(max = 500, message = "Nội dung tối đa 500 ký tự")
        private String message;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getMessage() {
            return message;
        }

        public void setMessage(String message) {
            this.message = message;
        }
    }
}
```

Điểm quan trọng:

- `@Controller` trả tên template `feedback`, **khác** `@RestController` vốn thường serialize return value thành response body.
- `q` đi thẳng vào model, **không tự escape trong Java**; output point của Thymeleaf quyết định encoding.
- `safeSlug` do server chọn trong ví dụ. URL parameter không được dùng để thay quyền kiểm soát route.
- `FeedbackForm` chỉ có hai trường user được phép nhập. Không bind entity chứa `role`, `admin`, `price` hoặc `ownerId`.
- `BindingResult` đứng ngay sau `@Valid @ModelAttribute`; nếu lỗi, render lại template với validation messages.
- POST hợp lệ dùng **PRG** và flash attribute. Trong ứng dụng thật, cần lưu/điều phối công việc theo nghiệp vụ rồi mới redirect; cân nhắc idempotency key khi thao tác có tác dụng phụ.

### 7.4. Template Thymeleaf

**`src/main/resources/templates/feedback.html`**

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Feedback an toàn</title>
</head>
<body>
  <h1>Biểu mẫu phản hồi</h1>

  <h2>Dữ liệu được escape</h2>
  <p id="echo" th:text="${query}">Văn bản người dùng</p>
  <input id="query-attribute" type="text" readonly
         th:value="${query}">

  <h2>Liên kết tạo bởi Thymeleaf</h2>
  <a id="query-link"
     th:href="@{/feedback(q=${query})}">Mở lại với query</a>
  <a id="path-link"
     th:href="@{/feedback/{slug}(slug=${safeSlug},q=${query})}">
    Trang hướng dẫn
  </a>

  <p id="thanks"
     th:if="${submittedName != null}"
     th:text="|Đã nhận phản hồi của ${submittedName}.|">
    Cảm ơn!
  </p>

  <h2>Gửi phản hồi</h2>
  <form id="feedback-form" method="post"
        th:action="@{/feedback}"
        th:object="${feedbackForm}">
    <div>
      <label for="name">Tên</label>
      <input id="name" type="text" th:field="*{name}"
             required maxlength="80" autocomplete="name">
      <small th:if="${#fields.hasErrors('name')}"
             th:errors="*{name}">Lỗi tên</small>
    </div>
    <div>
      <label for="message">Nội dung</label>
      <textarea id="message" th:field="*{message}"
                required maxlength="500"></textarea>
      <small th:if="${#fields.hasErrors('message')}"
             th:errors="*{message}">Lỗi nội dung</small>
    </div>
    <button type="submit">Gửi</button>
  </form>
</body>
</html>
```

Lưu ý:

- `th:text="${query}"` đưa query vào **HTML text** với escaping.
- `th:value="${query}"` đưa query vào **attribute value** với encoding phù hợp.
- `th:href="@{/feedback(q=${query})}"` và placeholder `{slug}` xây link đúng path/context và encode giá trị.
- `th:field="*{name}"` / `*{message}` bind dữ liệu cho form, giúp nhập lại và hiển thị lỗi khi submit không hợp lệ.
- `th:action="@{/feedback}"` trên form POST cho phép cơ chế Spring Security + Thymeleaf tự thêm hidden CSRF field khi tích hợp mặc định hoạt động; **không thêm token hardcode** vào template.
- `submittedName` đến từ input trước đó, nhưng `th:text` vẫn escape khi hiển thị. **PRG không làm dữ liệu trở nên đáng tin cậy**.

Ví dụ chủ ý không có JavaScript, CSS hoặc rich HTML từ user. Với dữ liệu có yêu cầu hiển thị rich text, phải thiết kế sanitizer và quyền riêng.

## 8. Chạy thử và quan sát kết quả

Từ thư mục dự án có Maven Wrapper, chạy:

```bash
java -version
./mvnw spring-boot:run
```

Trên Windows dùng `mvnw.cmd spring-boot:run`. Không có **stdout cố định** cho Spring Boot vì version, profile, port và log format thay đổi; kiểm tra server chạy ở `http://localhost:8080` nếu chưa đổi `server.port`.

Truy cập:

```text
http://localhost:8080/feedback
http://localhost:8080/feedback?q=a%26b
http://localhost:8080/feedback/huong-dan?q=a%26b
```

Kết quả hợp lệ: màn hình có form; khi query là `a&b`, trang hiển thị đúng text này; link tạo bởi `th:href` giữ toàn bộ `a&b` trong **một** query parameter.

Gửi một chuỗi trông như HTML:

```bash
curl -G -i --data-urlencode "q=<img src=x onerror=alert(1)>" \
  http://localhost:8080/feedback
```

Bash/Unix hỗ trợ dấu `\` xuống dòng như trên; trong PowerShell hãy đặt toàn bộ lệnh trên một dòng hoặc dùng cú pháp xuống dòng riêng. Trong response HTML, phần `<img ...>` do query cung cấp phải ở dạng text escaped (chẳng hạn `&lt;img ...&gt;`); nó không xuất hiện thành HTML element thực thi. Nếu dùng developer tools, kiểm tra DOM: `#echo` chỉ chứa text, không có thẻ `img` do input tạo.

Mở form bằng browser rồi submit tên và nội dung hợp lệ. Với Spring Security tích hợp Thymeleaf, form được render kèm hidden CSRF token; POST hợp lệ trả redirect (thường HTTP **302**) sang `/feedback` và tên được hiển thị lại bằng `th:text`. Chưa có database hoặc lưu nội dung trong demo nên kết quả chỉ chứng minh validation, redirect và escaping.

Nếu gửi POST trực tiếp **không có CSRF token**:

```bash
curl -i -X POST http://localhost:8080/feedback \
  -d "name=An" -d "message=Xin%20chao"
```

Khi Spring Security CSRF đang bật, request dạng này bị từ chối (thông thường **HTTP 403**), bất kể dữ liệu có hợp lệ theo Bean Validation hay không. Đây là hành vi mong đợi của tầng bảo vệ CSRF. Muốn mô phỏng POST hợp lệ qua curl phải lấy token và session/cookie phù hợp từ server; không tự điền một giá trị token giả.

## 9. Kiểm thử tự động với MockMvc

Dùng `spring-boot-starter-test` và `spring-security-test` ở scope test. Viết các test xác nhận **giá trị nguy hiểm không bị biến thành HTML**, URL query được encode, CSRF hoạt động và validation được thực thi.

**`src/test/java/com/example/demo/SafeUiApplicationTest.java`**

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeUiApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void escapesUntrustedText() throws Exception {
        String attack = "<img src=x onerror=alert(1)>";

        mvc.perform(get("/feedback").param("q", attack))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("&lt;img src=x onerror=alert(1)&gt;")
            ))
            .andExpect(content().string(
                not(containsString(attack))
            ));
    }

    @Test
    void encodesQueryParameterInsideLink() throws Exception {
        mvc.perform(get("/feedback").param("q", "a&b"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("q=a%26b")
            ));
    }

    @Test
    void rejectsPostWithoutCsrfToken() throws Exception {
        mvc.perform(post("/feedback")
                .param("name", "An")
                .param("message", "Xin chao"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validatesInputOnServer() throws Exception {
        mvc.perform(post("/feedback")
                .with(csrf())
                .param("name", "")
                .param("message", "Noi dung hop le"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("Tên không được để trống")
            ));
    }

    @Test
    void validFormPostRedirects() throws Exception {
        mvc.perform(post("/feedback")
                .with(csrf())
                .param("name", "An")
                .param("message", "Xin chao"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/feedback"));
    }
}
```

Chạy:

```bash
./mvnw test
```

Với đúng các file và dependencies mô tả, **năm test được kỳ vọng pass**. Đây là kết quả thiết kế để người học tự chạy, không phải tuyên bố đã chạy test trong repository thực tế. Nếu test fail, kiểm tra phiên bản Spring Boot 3.x, scope của `spring-security-test`, validation starter, tên template và việc form `th:action` thực sự được xử lý bởi Thymeleaf.

Những test nên bổ sung khi triển khai production: input có dấu nháy trong attribute, Unicode, query có `&`/`?`/`#`, URL path encoding, form value quá dài, lỗi Bean Validation, redirect an toàn, link scheme độc hại, authorization theo user/object, file upload, form trùng request, session cookie và phản ứng khi CSRF token hết hạn.

## 10. Validation, sanitization, escaping và CSRF khác nhau như thế nào?

| Biện pháp | Mục đích | Ví dụ | Không thể thay thế |
| --- | --- | --- | --- |
| **Validation** | Bảo đảm dữ liệu đúng quy tắc nhập | `@NotBlank`, `@Size`, kiểu/định dạng/whitelist | Escaping, kiểm tra quyền |
| **Sanitization** | Loại bỏ/giới hạn nội dung nguy hiểm khi thực sự cho phép HTML | Bộ lọc rich HTML allowlist | CSRF, authorization |
| **Output escaping/encoding** | Đảm bảo dữ liệu được trình duyệt hiểu là dữ liệu ở ngữ cảnh hiện tại | `th:text`, `th:value`, `@{...}` | Validation, xác thực URL đích |
| **Authentication/authorization** | Xác định ai được thao tác dữ liệu nào | Spring Security, kiểm tra owner/tenant | XSS/CSRF |
| **CSRF token** | Chống request thay đổi trạng thái được gửi trái ý qua browser có credential | Hidden token trong POST form | XSS, kiểm tra quyền |
| **CSP/security headers** | Giảm khả năng và tác động của một số kiểu injection | `script-src`, chống inline script không được phép | Escaping chính xác, kiểm tra URL |

Một **chuỗi hợp lệ** về độ dài và định dạng vẫn có thể chứa `<script>`. Một **chuỗi được HTML-escaped** vẫn có thể là URL `javascript:` không được phép. Một request **có CSRF token hợp lệ** vẫn có thể truy cập dữ liệu không thuộc user nếu backend thiếu authorization.

### Form submission và an toàn giao dịch

Trong ứng dụng thực tế:

- Không ghi tài nguyên quan trọng bằng **GET**. Link GET có thể bị crawler/browser preview/prefetch theo dõi; thao tác thay đổi trạng thái cần method phù hợp và CSRF protection khi dùng cookie authentication.
- Với POST làm phát sinh thanh toán/đơn hàng, CSRF + PRG **không bảo đảm đúng một lần xử lý**. Cần idempotency key, kiểm tra transaction và chống submit trùng.
- Dùng DTO input và allowlist field; ở service áp dụng authentication, authorization, kiểm tra tenant/owner từ server và tránh mass assignment.
- Lỗi validation có thể chứa giá trị người dùng trong thông báo; render dưới dạng text escaped và tránh đưa dữ liệu bí mật vào thông báo/log.
- `Content-Type`, kích cỡ request, số lượng trường, multipart upload size và giới hạn tốc độ cần được cấu hình phù hợp; browser validation không bảo vệ backend.
- Khi dùng cookie-based session, cân nhắc `HttpOnly`, `Secure` và `SameSite` theo kiến trúc và HTTPS thực tế; chúng bổ trợ cho CSRF/XSS defenses.

## 11. Những lỗi thường gặp và cách sửa

**Lỗi 1 — Dùng `th:utext` để giữ dấu xuống dòng hoặc định dạng.** Nếu chỉ cần xuống dòng, dùng CSS `white-space: pre-wrap` trên element có `th:text`. Khi cần rich HTML, dùng sanitizer theo chính sách rõ; không mở raw HTML cho mọi user.

**Lỗi 2 — Server escape trước, template escape lần nữa.** Kết quả `&amp;lt;` có thể xuất hiện thay cho `&lt;`. Giữ text thô trong model, escape ở output boundary.

**Lỗi 3 — Dùng URL encoding như một kiểm tra quyền hoặc kiểm tra scheme.** `th:href` mã hóa tham số, nhưng không xác nhận user được xem `/orders/123` và không ngăn redirect đến domain lạ. Thêm authorization/allowlist.

**Lỗi 4 — Tạo link thủ công bằng chuỗi `"/search?q=" + q`.** Dấu `&`, `#`, space và Unicode có thể gây URL sai hoặc thay đổi cấu trúc; dùng URL expression với tham số.

**Lỗi 5 — Chỉ đặt `required` ở HTML.** Người dùng có thể gửi POST qua script, curl hoặc thay đổi browser DOM. Dùng `@Valid`/Bean Validation và kiểm tra điều kiện nghiệp vụ trong service.

**Lỗi 6 — Đặt `BindingResult` sai vị trí.** Trong controller MVC, phải đặt ngay sau `@Valid @ModelAttribute` tương ứng để nhận validation errors. Nếu không, Spring có thể ném exception hoặc trả lỗi khác thay vì render lại form.

**Lỗi 7 — Tắt CSRF toàn cục vì nhận 403.** Kiểm tra Spring Security filter chain, `th:action`, hidden token và session/cookies; chỉ miễn CSRF ở những endpoint/kiến trúc đã được đánh giá riêng.

**Lỗi 8 — Gắn input người dùng vào `onclick`/inline script.** HTML attribute escaping không phải cơ chế an toàn để tạo JavaScript code. Dùng JS file tách biệt, event listeners và DOM `textContent`.

**Lỗi 9 — Tin hidden input trong form.** Các trường `role`, `userId`, `totalPrice` trong hidden fields đều có thể bị sửa; các giá trị quyết định quyền và thanh toán phải được xác định/xác minh ở server.

**Lỗi 10 — Cho phép link `returnUrl` bất kỳ.** Dẫn tới open redirect, XSS URL scheme hoặc phishing. Giới hạn redirect trong app hoặc danh sách đích đã đăng ký, parse và so sánh thành phần URL đúng cách.

**Lỗi 11 — HTML escaping xong rồi đưa vào `innerHTML`.** Việc dùng sink DOM có khả năng parse HTML có thể tạo nguy cơ mới nếu chuỗi bị decode/biến đổi tiếp. Ưu tiên `textContent`; dùng sanitization có chủ đích nếu thật sự cần HTML.

**Lỗi 12 — Dùng `|${name}|` trong th:action/URL tùy ý.** Literal substitution không thay thế việc tách path/query component và percent-encode. Dùng `@{...}` cho link/action và data binding thích hợp cho form.

## 12. Checklist review giao diện server-rendered

- [ ] Dữ liệu từ user/database/API ngoài hiển thị dưới dạng text qua `th:text`/`[[...]]`.
- [ ] Không có `th:utext`/`[(...)]` cho dữ liệu chưa qua rich HTML sanitizer đúng chuẩn.
- [ ] Input trong HTML attributes dùng processor Thymeleaf thích hợp; không nối raw HTML.
- [ ] Không gán URL nguyên vẹn từ user vào `href`, `src`, redirect hoặc form action mà chưa xác thực đích.
- [ ] Link path/query dùng `@{...}` với tham số riêng; ID vẫn được validate và authorize.
- [ ] Script/CSS không nội suy trực tiếp dữ liệu chưa tin cậy; dùng ngữ cảnh escape phù hợp hoặc tránh dynamic code.
- [ ] Form có DTO riêng, `@Valid`, `BindingResult` và thông báo lỗi được escape.
- [ ] POST/PUT/PATCH/DELETE dựa trên cookie/session được bảo vệ CSRF; test POST không có token -> 403.
- [ ] Role, owner, tenant, price, status không tin vào hidden/request values; service kiểm tra từ nguồn tin cậy.
- [ ] Test XSS reflected/stored, URL encoding, invalid input, session/CSRF, authorization và redirect.
- [ ] Có cấu hình HTTPS, cookie/security headers và CSP phù hợp threat model.
- [ ] Version Spring Boot, Thymeleaf, Spring Security được bảo trì và cập nhật bản vá.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `th:text="${comment}"` và `th:utext="${comment}"` khác gì?  
**Trả lời:** `th:text` escape HTML text, còn `th:utext` chèn nội dung không escape; không dùng `th:utext` cho nội dung user chưa sanitize.

**Câu 2.** Query `q=a&b` nên tạo link bằng `th:href="|/search?q=${q}|"` hay `th:href="@{/search(q=${q})}"`?  
**Trả lời:** Dùng `@{/search(q=${q})}` để Thymeleaf xử lý URL parameter encoding.

**Câu 3.** `th:href="${externalUrl}"` có an toàn chỉ vì Thymeleaf escape dấu nháy?  
**Trả lời:** Chưa. URL vẫn cần kiểm tra scheme, đích và quyền dùng URL; `javascript:` không trở thành an toàn chỉ nhờ HTML escaping.

**Câu 4.** HTML `required` đã đủ cho form chưa?  
**Trả lời:** Chưa. Phải validate lại bằng `@Valid` và ràng buộc nghiệp vụ trên server.

**Câu 5.** Spring Security đã bật, POST form Thymeleaf không có CSRF token thì sao?  
**Trả lời:** Khi CSRF protection đang hoạt động, request thường bị từ chối với HTTP 403; kiểm tra integration của `th:action` và token/cookie.

**Câu 6.** Dùng `@Valid` có tự chặn user gửi `isAdmin=true` vào entity nếu controller bind toàn bộ entity không?  
**Trả lời:** Không. Phải dùng DTO chỉ có các trường được phép và kiểm tra authorization phía service.

**Câu 7.** Sau POST hợp lệ, redirect về GET có chống trùng một đơn hàng không?  
**Trả lời:** Chưa. PRG hạn chế việc submit lặp do refresh; logic quan trọng vẫn cần idempotency/transaction.

## 14. Tài liệu chính thức

- Thymeleaf 3.1, *Using Thymeleaf*: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html
- Thymeleaf 3.1, *Thymeleaf + Spring*: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
- Spring Security, *CSRF Protection*: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Framework, *Spring MVC Validation*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework, *View Technologies*: https://docs.spring.io/spring-framework/reference/web/webmvc-view.html
- Spring Boot, *Servlet Web Applications*: https://docs.spring.io/spring-boot/reference/web/servlet.html
- OWASP, *Cross Site Scripting Prevention Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- OWASP, *Cross-Site Request Forgery Prevention Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP, *Unvalidated Redirects and Forwards Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

**Kết luận:** Với giao diện render từ Spring Boot, chọn **escape theo ngữ cảnh**, xây link bằng `@{...}`, dùng DTO và Bean Validation cho form, bật CSRF khi cần, giới hạn URL/redirect đích và luôn kiểm tra quyền ở server. Cấu hình an toàn phải được xác nhận bằng test chứa dữ liệu độc hại lẫn các request hợp lệ, vì một trang “trông đúng” vẫn có thể che lỗi XSS, open redirect, mass assignment hoặc CSRF.