# Tích hợp với form tag và template engine phù hợp

Trong module `SPRING_SECURITY_HTTP_PROTECTION`, CSRF là một trong các lớp bảo vệ HTTP và trình duyệt bên cạnh CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ phiên. Với ứng dụng có biểu mẫu HTML được render trên máy chủ, chỉ bật `csrf()` trong Spring Security là chưa đủ để form hoạt động: **view phải đưa token thích hợp vào dữ liệu submit**. Cách thực hiện phụ thuộc việc dùng Thymeleaf, Spring MVC form tag, JSP thuần, FreeMarker, Mustache hay template engine tự phát triển.

Bài này tập trung vào **cơ chế tích hợp giữa Spring Security và công cụ render form**, cách chọn giải pháp tương ứng và cách kiểm chứng. Các ví dụ ưu tiên ứng dụng Spring MVC/Servlet; phần cuối chỉ rõ sự khác biệt khi chuyển sang WebFlux/Reactive.

## 1. Mục tiêu

Sau bài học, người học có thể:

- Chọn cơ chế tích hợp cho từng loại form: `th:action`, `<form:form>`, `<sec:csrfInput />` hoặc chèn token bằng dữ liệu model.
- Phân biệt **binding dữ liệu form** với **thêm CSRF token**, hiểu vì sao có công cụ hỗ trợ cả hai.
- Giải thích vị trí của `CsrfRequestDataValueProcessor` trong đường đi từ filter security đến template.
- Triển khai form có dữ liệu model và CSRF mà không chèn trùng hidden field hoặc vô tình tắt bảo vệ.
- Đọc HTML đã render, kiểm tra POST, tìm nguyên nhân HTTP 403 và viết kiểm thử có ý nghĩa.
- Nêu điểm cần thay đổi trong Reactive/WebFlux, nơi token ban đầu được cung cấp bất đồng bộ.

## 2. Tích hợp thực chất diễn ra ở đâu?

Trình duyệt gửi cookie phiên theo quy tắc cookie, nhưng trang độc hại có thể tạo một form POST gửi sang ứng dụng đích. Với CSRF protection, request thay đổi trạng thái cần gửi **một giá trị token hợp lệ**, ngoài cookie phiên. Token trong hidden input không phải mật khẩu: người dùng có thể xem nó trong HTML của trang hợp lệ; trang độc hại ở origin khác thông thường không thể đọc nội dung trang đó do same-origin policy.

Trong Spring MVC/Servlet, các mắt xích là:

```text
GET /profile/edit
       |
       v
Spring Security filter chain
  CsrfFilter
  CsrfTokenRepository       : tạo / tải token kỳ vọng
  CsrfTokenRequestHandler   : đưa token cho request / view
       |
       v
Controller -> model -> view
       |
       +-- Thymeleaf th:action ---------+
       |                                |
       +-- JSP <form:form> -------------+--> RequestDataValueProcessor
       |                                |    -> hidden input CSRF
       +-- JSP raw / engine khác -------+--> tự chèn qua request/model
       |
       v
HTML trả về trình duyệt:
<form method="post" ...>
    ...
    <input type="hidden" name="_csrf" value="...">
</form>
       |
       v
POST /profile/edit: cookie + dữ liệu form + _csrf
       |
       v
CsrfFilter kiểm tra trước khi controller xử lý
```

### 2.1. Những thành phần cần phân biệt

| Thành phần | Nhiệm vụ | Điều dễ nhầm |
| --- | --- | --- |
| `CsrfFilter` | Quyết định request nào cần CSRF và kiểm tra token khi request tới. | Controller có thể chưa chạy vì filter đã trả 403. |
| `CsrfTokenRepository` | Tạo, lưu, tải token kỳ vọng; mặc định trên Servlet là `HttpSessionCsrfTokenRepository`. | Repository không tự sửa HTML của form. |
| `CsrfTokenRequestHandler` | Cung cấp token cho request và giải mã/đọc token khi submit. | Token được render có thể khác chuỗi token gốc trong repository. |
| `CsrfRequestDataValueProcessor` | Kết nối với hệ thống `RequestDataValueProcessor` của Spring MVC để cung cấp hidden field cho những form được hỗ trợ. | Chỉ hoạt động khi view/tag thực sự gọi cơ chế xử lý tương ứng. |
| `<form:form>`, `th:action` | Cách view engine dựng action và có thể lấy thêm CSRF hidden field. | `th:field` / `form:input` chủ yếu phục vụ data binding, không phải bộ kiểm tra CSRF. |
| `<sec:csrfInput />` | Thẻ JSP bổ sung trường CSRF cho một form HTML thông thường. | Không cần lặp lại bên trong form đã tự chèn token. |

Spring Security 6 sử dụng **deferred token loading** và mặc định áp dụng cơ chế che token nhằm giảm nguy cơ BREACH. Một token lưu trong session có thể được biểu diễn bằng các chuỗi khác nhau khi render. Vì vậy hãy lấy **token do request hiện tại cung cấp** (ví dụ `_csrf.token`), không tự lấy chuỗi thô từ repository để ghép vào template.

### 2.2. Data binding và CSRF là hai trách nhiệm khác nhau

Ví dụ với profile có thuộc tính `displayName`:

- `th:object="${profileForm}"` và `th:field="*{displayName}"` trong Thymeleaf giúp liên kết model với trường nhập.
- `modelAttribute="profileForm"` và `<form:input path="displayName" />` của Spring form tags cũng phục vụ data binding.
- `th:action` trên form POST và `<form:form>` là điểm tích hợp phổ biến để có thêm hidden CSRF field.
- `CsrfFilter`, không phải template engine, mới là nơi **thực hiện kiểm tra CSRF của request**.

Một form có thể bind dữ liệu chính xác nhưng vẫn trả 403 nếu token không được gửi. Ngược lại, POST có token hợp lệ vẫn phải qua xác thực, phân quyền, kiểm tra dữ liệu đầu vào và nghiệp vụ.

## 3. Chọn công cụ theo loại ứng dụng

| Môi trường render | Cách dùng nên ưu tiên | Khi nào phải tự chèn? | Điều cần kiểm tra |
| --- | --- | --- | --- |
| Spring MVC + Thymeleaf (tích hợp Spring) | `<form th:action="@{/...}" method="post">`; dùng `th:object`, `th:field` nếu bind model. | Form không đi qua tích hợp Thymeleaf/Spring, hoặc dùng template tùy biến. | HTML Response có hidden CSRF input và action đúng context path. |
| Spring MVC + JSP Spring form tags | `<form:form method="post" modelAttribute="...">`, kết hợp `<form:input>`. | Chỉ dùng thẻ `<form>` thuần, không qua Spring form tag. | Có đúng model attribute và hidden CSRF input sau render. |
| JSP HTML thuần | `<sec:csrfInput />` nếu đã có `spring-security-taglibs`. | Khi không dùng security JSP taglib, chèn input từ `_csrf`. | Không chèn lặp, không vô tình dùng action URL sai. |
| FreeMarker / Mustache / engine tự tạo | Chủ động đưa token từ request vào view model và render hidden input. | Thường cần tự tích hợp nếu engine không gọi `RequestDataValueProcessor`. | Escape dữ liệu an toàn; token lấy từ request đã được Spring Security xử lý. |
| Spring WebFlux + engine Reactive | Dùng tích hợp view tương thích Reactive; kiểm tra cơ chế auto CSRF của engine đó. | Khi template/custom view cần tiêu thụ `Mono<CsrfToken>` và tự render. | Tránh cast `Mono` thành token và tránh `block()` trong pipeline. |

**Nguyên tắc chọn:** Ưu tiên đường tích hợp có sẵn của view engine và Spring Security. Chỉ bổ sung input thủ công khi HTML đầu ra thực sự thiếu token. Với nhiều template khác nhau trong cùng hệ thống, kiểm tra từng loại form vì không có một bộ tự chèn duy nhất áp dụng cho mọi engine.

## 4. Ví dụ Spring MVC + Thymeleaf

### 4.1. Controller và form model

Ví dụ dưới đây áp dụng cho Spring Boot sử dụng Spring MVC, Spring Security, Thymeleaf. Phần phụ thuộc cần có: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-thymeleaf`; với kiểm thử cần `spring-security-test` và bộ starter test phù hợp phiên bản Spring Boot.

Tạo JavaBean để Spring MVC bind dữ liệu:

```java
public class ProfileForm {
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Controller cung cấp model cho GET và nhận model đã bind ở POST:

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class ProfileController {

    @GetMapping("/profile/edit")
    String edit(Model model) {
        model.addAttribute("profileForm", new ProfileForm());
        return "profile-edit";
    }

    @PostMapping("/profile/edit")
    String save(@ModelAttribute("profileForm") ProfileForm form,
                RedirectAttributes redirects) {
        // Minh họa: ứng dụng thực cần validate, phân quyền và lưu dữ liệu.
        redirects.addFlashAttribute("notice", "Đã nhận thông tin");
        return "redirect:/profile/edit";
    }
}
```

Cấu hình Security ngắn gọn để có thể thử GET/POST mà không cần đăng nhập:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/profile/edit").permitAll()
                        .anyRequest().authenticated())
                .csrf(Customizer.withDefaults())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
```

`permitAll()` chỉ miễn yêu cầu xác thực ở đường dẫn minh họa. **Nó không miễn kiểm tra CSRF.** Trong hệ thống thật, trang chỉnh sửa hồ sơ thường cần authenticated user và kiểm tra người dùng có quyền sửa đúng tài nguyên.

### 4.2. Template Thymeleaf

Tạo `src/main/resources/templates/profile-edit.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Chỉnh sửa hồ sơ</title>
</head>
<body>
    <p th:if="${notice}" th:text="${notice}"></p>

    <form th:action="@{/profile/edit}"
          th:object="${profileForm}"
          method="post">
        <label for="displayName">Tên hiển thị</label>
        <input id="displayName"
               type="text"
               th:field="*{displayName}">
        <button type="submit">Lưu</button>
    </form>
</body>
</html>
```

Tại đây:

1. `th:action="@{/profile/edit}"` tính action của form theo context path, đồng thời đưa form POST qua điểm tích hợp với Spring `RequestDataValueProcessor`.
2. `th:object` chọn đối tượng form trong model; `th:field` tạo `name="displayName"` và bind giá trị.
3. Với Thymeleaf tích hợp Spring MVC/Spring Security đúng cách, hidden CSRF input được thêm **khi render**, dù mã nguồn template không viết nó.
4. `th:text` xuất thông báo theo cách escape HTML, tránh biến nội dung động thành mã HTML do người dùng điều khiển.

HTML được gửi về trình duyệt có thể tương tự:

```html
<form action="/profile/edit" method="post">
    <label for="displayName">Tên hiển thị</label>
    <input id="displayName" type="text" name="displayName" value="">
    <button type="submit">Lưu</button>
    <input type="hidden" name="_csrf" value="gia-tri-do-spring-security-render">
</form>
```

Không giả định chính xác vị trí input trong HTML hoặc giá trị token. Cần kiểm tra **response HTML thực tế** trong Network tab; mã nguồn template được lưu trên đĩa chưa phản ánh các input được thêm khi render.

### 4.3. Sai lầm dễ gặp với Thymeleaf

```html
<!-- Thiếu th:action: không nên mặc định trông chờ tích hợp tự thêm token -->
<form action="/profile/edit" method="post">
    <input name="displayName">
    <button type="submit">Lưu</button>
</form>
```

Đây có thể là form hợp lệ về HTML nhưng **không kích hoạt tích hợp tạo hidden input của Thymeleaf**. Dùng `th:action` như ví dụ chuẩn, hoặc chủ động render token nếu hệ thống dùng form HTML thuần:

```html
<!-- Cách thủ công chỉ dùng khi biết form chưa được tự chèn CSRF token -->
<form action="/profile/edit" method="post">
    <input name="displayName">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Lưu</button>
</form>
```

Trong phương án thủ công, phải đảm bảo action có context path phù hợp với nơi triển khai và `_csrf` hiện diện trong request. **Không thêm cả hai phương án** rồi để hai hidden input có cùng tên vì thứ tự hoặc cách đọc các tham số lặp có thể gây kết quả khó dự đoán.

## 5. Spring MVC form tag trong JSP

### 5.1. Form binding và CSRF cùng hoạt động

Với JSP, Spring MVC cung cấp thư viện tag có URI `http://www.springframework.org/tags/form`. Khi form được render bằng `<form:form>`, Spring form tag dùng `RequestDataValueProcessor` và tương thích với việc Spring Security bổ sung CSRF hidden input.

Ví dụ JSP (dùng lại model `profileForm` do controller cung cấp):

```jsp
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<c:url var="saveUrl" value="/profile/edit" />

<form:form action="${saveUrl}"
           method="post"
           modelAttribute="profileForm">
    <label for="displayName">Tên hiển thị</label>
    <form:input path="displayName" id="displayName" />
    <button type="submit">Lưu</button>
</form:form>
```

Cụ thể:

- `modelAttribute="profileForm"` phải khớp với model controller tạo; nếu không, view có thể gặp lỗi binding trước khi kiểm tra CSRF.
- `<form:input path="displayName" />` bind trường thuộc JavaBean và xử lý giá trị form.
- `<form:form method="post">` đưa form qua integration của Spring MVC và Spring Security; hidden input được thêm tự động vào HTML.
- `<c:url>` tạo URL có xét context path, tránh hardcode đường dẫn tuyệt đối khi ứng dụng không chạy tại `/`.

**Không cần đặt `<sec:csrfInput />` bên trong `<form:form>` khi automatic integration đang hoạt động.** Nếu thấy hai input cùng tên `_csrf` trong HTML thì cần loại bỏ đường chèn trùng.

Lưu ý môi trường: JSP thường cần cấu hình view resolver, JSP engine và kiểu đóng gói tương thích với Spring Boot/container. URI taglib JSTL `jakarta.tags.core` áp dụng cho Jakarta hiện đại; dự án Java EE cũ có thể dùng URI `http://java.sun.com/jsp/jstl/core`. Khác biệt taglib hoặc container là vấn đề render, không phải lỗi CSRF.

### 5.2. JSP thuần và Spring Security taglib

Nếu không dùng `<form:form>`, có thể chèn token bằng Spring Security JSP tag:

```jsp
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<%@ taglib prefix="sec" uri="http://www.springframework.org/security/tags" %>
<c:url var="saveUrl" value="/profile/edit" />

<form action="${saveUrl}" method="post">
    <label for="displayName">Tên hiển thị</label>
    <input id="displayName" name="displayName">
    <sec:csrfInput />
    <button type="submit">Lưu</button>
</form>
```

`<sec:csrfInput />` thuộc thư viện JSP tag của Spring Security (artifact `spring-security-taglibs`). Nó sinh hidden input CSRF khi CSRF đang được bật. Với JSP thuần và không có taglib này, lấy từ thuộc tính request:

```jsp
<form action="${saveUrl}" method="post">
    <input name="displayName">
    <input type="hidden"
           name="${_csrf.parameterName}"
           value="${_csrf.token}">
    <button type="submit">Lưu</button>
</form>
```

Tên tham số và giá trị token phải được xuất từ request tương ứng, không cố định `_csrf` hoặc giá trị token trong mã nguồn. Khi dùng form tag tự động hoặc `sec:csrfInput`, không cần tự viết hidden input này.

## 6. Template engine không có tích hợp tự động

FreeMarker, Mustache hoặc view renderer tự tạo có thể không gọi `RequestDataValueProcessor` khi render form HTML. Khi đó ứng dụng cần **đưa CSRF token đã được Spring Security expose vào view model** rồi render một hidden input.

### 6.1. Controller đưa token vào model (Servlet)

Ví dụ thêm một endpoint dùng FreeMarker/Mustache:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class ManualProfilePageController {

    @GetMapping("/profile/manual")
    String manualForm(HttpServletRequest request, Model model) {
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException("Không có CSRF token trong request");
        }

        model.addAttribute("csrfParameterName", token.getParameterName());
        model.addAttribute("csrfTokenValue", token.getToken());
        return "profile-manual";
    }
}
```

Ở đây, token lấy từ **request attribute do Spring Security quản lý** nên giữ đúng hình thức được handler cung cấp cho view. Không tự gọi `CsrfTokenRepository.loadToken(...)` rồi render token thô khi ứng dụng đang dùng handler che token (ví dụ cơ chế XOR mặc định của Servlet Security 6).

### 6.2. Ví dụ FreeMarker

Với template `profile-manual.ftlh`, cấu hình output format HTML và auto escaping để dữ liệu trong attribute được escape đúng cách:

```ftl
<#ftl output_format="HTML" auto_esc=true>
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Chỉnh sửa hồ sơ</title>
</head>
<body>
    <form method="post" action="/profile/edit">
        <label for="displayName">Tên hiển thị</label>
        <input id="displayName" name="displayName">
        <input type="hidden"
               name="${csrfParameterName}"
               value="${csrfTokenValue}">
        <button type="submit">Lưu</button>
    </form>
</body>
</html>
```

Đường dẫn action cần được xây dựng theo context path thực tế nếu ứng dụng không chạy tại root; có thể truyền một `formAction` đã tính đúng vào model. Đừng nối URL bằng dữ liệu người dùng không kiểm soát.

### 6.3. Ví dụ Mustache

Nếu model đã có `csrfParameterName` và `csrfTokenValue`, form Mustache có thể sử dụng:

```html
<form method="post" action="/profile/edit">
    <input name="displayName">
    <input type="hidden"
           name="{{csrfParameterName}}"
           value="{{csrfTokenValue}}">
    <button type="submit">Lưu</button>
</form>
```

Thông thường biến Mustache dạng `{{name}}` được escape; tránh kiểu output không escape như `{{{name}}}` đối với dữ liệu có thể chứa nội dung không tin cậy. Không giả định mọi cấu hình Mustache tự thêm CSRF. Cần xem **HTML sau render** và thử request thực tế.

**Điều kiện chung:** Security filter chain phải áp dụng cho GET render form và POST xử lý form; nếu GET đi qua pipeline khác, token có thể không được expose. Với view engine tuỳ biến, trách nhiệm chính là đọc đúng token dành cho request, tạo hidden input và đảm bảo output encoding phù hợp.

## 7. WebFlux/Reactive: tương đồng về mục tiêu, khác về cách lấy token

Trong WebFlux, Spring Security sử dụng `CsrfWebFilter`. Repository mặc định gắn với `WebSession`; thuộc tính exchange theo khóa `CsrfToken.class.getName()` là **`Mono<CsrfToken>`**, không phải `CsrfToken` trực tiếp.

Sự khác biệt này quyết định cách tích hợp view engine:

| Câu hỏi | Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- | --- |
| Lấy token ở đầu luồng render | `HttpServletRequest` attribute `_csrf` / `CsrfToken.class.getName()` | `ServerWebExchange` attribute `CsrfToken.class.getName()` chứa `Mono<CsrfToken>` |
| Chuẩn bị dữ liệu model cho template tùy biến | Đọc token đồng bộ rồi đặt vào `Model` | Tiêu thụ publisher bất đồng bộ rồi mới đặt vào model |
| Bộ lọc thực thi | `CsrfFilter` | `CsrfWebFilter` |
| Tích hợp form tự động | `RequestDataValueProcessor` trên nền Spring MVC | Tích hợp riêng của view engine/Reactive; xác minh support và HTML cuối cùng |

Với WebFlux + Thymeleaf được cấu hình phù hợp, form có `th:action` có thể tự nhận hidden CSRF input thông qua tích hợp Reactive. Nếu render bằng template tự tạo, controller có thể lấy token bất đồng bộ để cấp cho model như sau:

```java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
public class ReactiveManualProfileController {

    @GetMapping("/profile/manual")
    Mono<String> manual(ServerWebExchange exchange, Model model) {
        Mono<CsrfToken> csrfMono =
                exchange.getAttribute(CsrfToken.class.getName());

        if (csrfMono == null) {
            return Mono.error(new IllegalStateException(
                    "Spring Security chưa cung cấp CSRF token"));
        }

        return csrfMono.map(token -> {
            model.addAttribute("csrfParameterName", token.getParameterName());
            model.addAttribute("csrfTokenValue", token.getToken());
            return "profile-manual";
        });
    }
}
```

Đây là ví dụ cho **renderer cần model thủ công** và giả định nó render view `profile-manual` khi publisher hoàn thành. Nếu Thymeleaf Reactive đã tự chèn token thì không nên bổ sung hidden input lần nữa. Tránh `block()` ngay trên event loop hoặc ép kiểu `Mono<CsrfToken>` thành `CsrfToken`; cả hai đều bỏ qua mô hình xử lý Reactive.

## 8. Các tình huống dễ sai khi phối hợp form và bảo vệ HTTP

### 8.1. Nhiều form trên cùng một trang

Trang quản trị có thể có form sửa tên, khóa tài khoản và xóa tài khoản. **Mỗi form POST** cần được render và submit cùng token hợp lệ. Khi dùng Thymeleaf, đặt `th:action` trên từng form; với JSP form tag, dùng đúng `<form:form>` cho từng form. Đối với form HTML thuần, chèn một hidden input token trong mỗi form cần bảo vệ. Không đặt input ngoài form với hy vọng mọi form đều gửi nó.

### 8.2. Đổi HTTP method bằng hidden field

HTML chỉ hỗ trợ form method GET và POST. Nếu ứng dụng dùng `HiddenHttpMethodFilter` với trường `_method` để xử lý PUT/PATCH/DELETE, điều đó không bỏ yêu cầu CSRF. Cần kiểm tra thứ tự filter và cơ chế method override thực tế; token phải được gửi trên request mà Spring Security bảo vệ.

### 8.3. Xử lý URL, session và cache

- Dùng `th:action="@{/...}"` hoặc `<c:url>` để tính đường dẫn có context path; với template custom, truyền URL đã tạo đúng từ server.
- Không đặt CSRF token vào query string, fragment hoặc form action; token phải nằm trong body/field phù hợp với yêu cầu của CSRF handler.
- Không dùng HTML đã cache **chung cho nhiều session** nếu chứa token phụ thuộc phiên người dùng.
- Sau login/logout hoặc khi phiên thay đổi, token cũ có thể bị làm mới/xóa: người dùng cần tải lại form nếu POST token cũ bị 403.
- Token CSRF không thay thế cookie flags, CSP, HSTS, output encoding, validation hay kiểm soát quyền. Những lớp bảo vệ này phối hợp với nhau.
- `SameSite`, CORS hoặc `permitAll()` không đồng nghĩa với việc tắt yêu cầu CSRF; không dùng `csrf.disable()` để che lỗi tích hợp form.

### 8.4. Phân biệt 403 từ CSRF và lỗi khác

Một POST bị 403 có thể do token thiếu/sai hoặc do authorization. Kiểm tra kết hợp: browser Network payload, cookie session, cấu hình matcher, log Spring Security ở môi trường phát triển và request thực tế. Với CSRF sai, thông thường bộ lọc từ chối **trước khi** controller thực thi; với token đúng, controller vẫn có thể bị chặn bởi quy tắc khác.

## 9. Kiểm thử cơ chế tích hợp và hành vi CSRF

Cần **hai tầng kiểm chứng**:

1. **Kiểm tra view:** HTML đã render có field CSRF cho từng form POST cần bảo vệ, action chính xác và không có hai input cùng tên.
2. **Kiểm tra request:** POST hợp lệ qua được bước CSRF, thiếu token hoặc token sai trả 403 (với cấu hình mặc định) khi authorization và controller không gây nhiễu.

### 9.1. Thao tác bằng trình duyệt

Mở `GET /profile/edit`, kiểm tra Response HTML hoặc View Source. Sau đó vào Network và submit. Request POST thường có dữ liệu tương tự:

```text
POST /profile/edit
Cookie: JSESSIONID=...  (nếu dùng session)
Content-Type: application/x-www-form-urlencoded

displayName=An&_csrf=token-duoc-render
```

Đây là minh họa cấu trúc payload. Token và cookie thực cần được sinh trong chính phiên thử nghiệm; không sao chép token mẫu. Dùng **Copy as cURL** rồi bỏ `_csrf` hoặc thay bằng chuỗi sai, giữ cùng cookie và các thông tin khác, để quan sát phản hồi 403. Nếu một view không chèn input, hãy sửa điểm tích hợp template thay vì vô hiệu hóa CSRF.

### 9.2. MockMvc: kiểm tra render lẫn kiểm tra filter

Thêm `spring-security-test` để sử dụng `csrf()`. Với controller và SecurityFilterChain ở mục 4:

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
class ProfileFormSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void thymeleafRendersCsrfInput() throws Exception {
        mvc.perform(get("/profile/edit"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void postWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/profile/edit")
                        .param("displayName", "An"))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithInvalidCsrfIsRejected() throws Exception {
        mvc.perform(post("/profile/edit")
                        .with(csrf().useInvalidToken())
                        .param("displayName", "An"))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithValidCsrfPassesFilter() throws Exception {
        mvc.perform(post("/profile/edit")
                        .with(csrf())
                        .param("displayName", "An"))
                .andExpect(status().is3xxRedirection());
    }
}
```

`csrf()` trong MockMvc tạo request có token hợp lệ phục vụ kiểm thử. **Nó không chứng minh view đã tự chèn token**, vì vậy test kiểm tra HTML là phần riêng và bắt buộc khi mục tiêu là tích hợp template. Với tên tham số CSRF cấu hình tùy chỉnh, cập nhật assertion theo tên thực tế.

Với WebFlux, có thể dùng `WebTestClient` và `SecurityMockServerConfigurers.csrf()` để gửi request có CSRF token hợp lệ, kết hợp kiểm thử GET/POST không có token. Kết quả thành công cụ thể phụ thuộc controller và authorization, nên assertion phải phù hợp với endpoint Reactive của dự án.

## 10. Bảng chẩn đoán tích hợp

| Quan sát | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Template có form POST nhưng HTML đầu ra thiếu token | Form HTML thuần; Thymeleaf thiếu `th:action`; renderer không gọi `RequestDataValueProcessor` | Kiểm tra engine thực sự render, sử dụng tích hợp chuẩn hoặc cấp token từ request sang model. |
| Spring JSP form tag render lỗi trước khi xuất HTML | `modelAttribute` không có trong model, `path` sai hoặc taglib/JSP container không khớp | Đồng bộ controller và model; sửa cấu hình JSP trước khi kiểm tra CSRF. |
| JSP xuất hai hidden input `_csrf` | Dùng cả `<form:form>` lẫn `<sec:csrfInput />` hoặc tự chèn thêm input | Bỏ một đường chèn, kiểm tra lại HTML cuối cùng. |
| Mustache/FreeMarker in literal tên biến, token rỗng | Controller chưa đưa token vào model hoặc cú pháp template/escaping sai | Đọc request attribute đã được Security expose, cấp biến model và render lại. |
| Token có mặt nhưng POST vẫn trả 403 | Cookie khác phiên, token không đúng request, token cũ, handler cấu hình khác | Lấy cookie + token từ cùng lượt GET; kiểm tra Security filter và request payload. |
| Thymeleaf form chạy trong MVC nhưng không chạy khi chuyển WebFlux | Ứng dụng đang dùng tích hợp Servlet hoặc lấy sai kiểu token | Dùng view integration Reactive, xử lý `Mono<CsrfToken>` đúng cách. |
| Token đúng nhưng response vẫn 403 | Phân quyền từ chối sau bước CSRF | Kiểm tra security matcher, user principal và quyền thao tác. |
| Token bị đưa vào URL hoặc bị ghi log | Template tự nối action/query string | Chuyển token sang hidden field hoặc header phù hợp; tránh log giá trị token. |

## 11. Bài thực hành tổng hợp

**Yêu cầu:** Xây hai phiên bản của trang `/profile/edit` dùng chung controller, một bằng Thymeleaf và một bằng JSP hoặc template engine tùy chỉnh. Cả hai phải đáp ứng cùng chính sách CSRF.

1. **Thymeleaf:** Tạo `profileForm`, dùng `th:object` và `th:field`, form POST có `th:action`. Ghi nhận hidden input do view render, không tự chèn.
2. **JSP hoặc engine khác:** Chọn `<form:form>` hoặc `<sec:csrfInput />` / chèn từ model theo đúng công cụ. Giải thích vì sao đã chọn giải pháp đó.
3. **Kiểm chứng:** Với mỗi phiên bản, submit token hợp lệ, thiếu và sai. Quan sát status, payload và việc controller có chạy hay không.
4. **Sửa lỗi:** Cố tình tạo form chỉ có `action="/profile/edit"` và không có integration; xác định vì sao thiếu token, sửa đúng ở template.
5. **Chẩn đoán phiên:** Làm mới session hoặc logout/login (nếu cấu hình), sau đó thử submit lại form cũ; xác định thời điểm cần lấy token mới.
6. **Mở rộng Reactive:** Với WebFlux, mô tả sự khác nhau giữa lấy token đồng bộ từ request attribute và tiêu thụ `Mono<CsrfToken>`.

**Tiêu chí hoàn thành:** Người học xác định đúng nơi token được chèn, chọn cơ chế phù hợp với view engine, chứng minh behavior POST qua kiểm thử và không cần tắt CSRF để form hoạt động.

## Tài liệu tham khảo

- [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): `CsrfFilter`, token repository, token request handler và tích hợp với form/template.
- [Spring Security Reference — JSP Tag Libraries](https://docs.spring.io/spring-security/reference/servlet/integrations/jsp-taglibs.html): `csrfInput` và các tag Spring Security.
- [Spring Security Reference — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, `useInvalidToken()`.
- [Spring Security Reference — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `CsrfWebFilter`, `Mono<CsrfToken>` và view integration.
- [Thymeleaf + Spring Tutorial](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): `th:action`, `th:object`, `th:field` và Spring MVC binding.
