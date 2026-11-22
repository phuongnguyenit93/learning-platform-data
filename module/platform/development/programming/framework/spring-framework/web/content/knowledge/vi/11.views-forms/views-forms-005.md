# Liên kết biểu mẫu, hiển thị BindingResult và thông báo lỗi trong Spring MVC

## 1. Mục tiêu và phạm vi

Trong ứng dụng Spring MVC có **HTML view**, người dùng nhập dữ liệu trong form, gửi POST, rồi mong được giữ lại những gì đã nhập và thấy lỗi tại đúng ô nếu sai. Bài này bao quát toàn bộ chu trình form GET/POST, data binding, validation, hiển thị lỗi qua Thymeleaf và Post/Redirect/Get.

Sau bài học, bạn sẽ biết:

- Dùng `@Controller`, `Model`, `@ModelAttribute` và form backing object/DTO để nối HTML với Java.
- Phân biệt lỗi chuyển kiểu (`typeMismatch`), lỗi Bean Validation (`NotBlank`, `Min`, `Email`), lỗi business và lỗi toàn object.
- Đặt `BindingResult` đúng ngay sau form argument; đọc `FieldError`, `ObjectError`, rejected values và suppressed fields.
- Giữ dữ liệu form trong nhánh trả lại view khi có lỗi; hiển thị lỗi bằng `th:object`, `th:field`, `th:errors`, `th:errorclass` và `#fields`.
- Tạo ví dụ **Java 17+, Spring Boot 3.x/Spring Framework 6.x, Thymeleaf 3.1/Spring 6, Jakarta Bean Validation** có thể chạy trong một dự án Spring Web/Thymeleaf/Validation.
- Test bằng MockMvc để biết cả model có lỗi **và người dùng thực sự nhìn thấy thông báo trong HTML**.

Spring WebFlux dùng cơ chế và API khác; ví dụ ở đây là Spring MVC trên Servlet stack. Khi dùng Spring Boot 4 hoặc Spring Framework 7, nên đối chiếu API/dialect/test với phiên bản thực tế.

## 2. Toàn bộ vòng đời biểu mẫu

```text
Browser GET /register
    -> @Controller.showForm(Model)
    -> model["registration"] = RegistrationForm mới
    -> Thymeleaf templates/registration.html
       th:object="${registration}", th:field="*{fullName}"
    -> HTML có input name="fullName", name="age", ...

Browser POST /register
    -> application/x-www-form-urlencoded
    -> @ModelAttribute("registration") RegistrationForm
    -> WebDataBinder: parameter String -> String, Integer, LocalDate
    -> @Valid: kiểm tra Jakarta constraints
    -> BindingResult lưu binding errors + validation errors
    -> @Controller.submit(form, result, redirectAttributes)
         |
         +-- result.hasErrors()
         |      -> return "registration"
         |      -> render lại giá trị nhập, th:errors cho field/global
         |
         +-- không có errors
                -> service xử lý nghiệp vụ
                -> addFlashAttribute(...)
                -> redirect:/register/success
                -> Browser GET /register/success
```

Không phải mọi lớp đều chạy validation tự động. `@Valid` hoặc `@Validated` kích hoạt validator nếu đã cấu hình provider, còn binding/conversion xảy ra khi Spring resolve argument. Form HTML thường gửi `application/x-www-form-urlencoded`; JSON `@RequestBody` đi qua `HttpMessageConverter` khác với luồng property binding.

## 3. Form backing object và tên property

Một form DTO chứa **những trường browser được phép gửi**, không nhất thiết là JPA entity hoặc domain object. Ví dụ DTO `RegistrationForm` gồm `fullName`, `email`, `age`, `startDate`.

```html
<form method="post" action="/register">
  <input name="fullName" value="Lan">
  <input name="age" value="20">
</form>
```

Trình duyệt gửi `fullName=Lan&age=20`. `WebDataBinder` tìm các property tên tương ứng và gán chúng vào Java object, dùng type conversion khi cần. `name` của input quyết định tên request parameter; `id` dành cho label/CSS/JS và không thay thế `name`.

Lý do dùng DTO form riêng:

- Client không thể tùy ý bind vào `isAdmin`, `role`, `ownerId` hoặc các field persistence không thuộc hợp đồng.
- Form có thể có validation và message phù hợp UX mà database entity không nên mang theo.
- Khi validation sai, object vẫn mang những giá trị bind được; những giá trị lỗi chuyển kiểu có thể nằm trong `BindingResult`.
- DTO nhỏ dễ thay đổi trình bày mà không khiến view phụ thuộc schema database.
- Dù dùng DTO, **authorization** ở service vẫn bắt buộc; một field có mặt trong DTO không đồng nghĩa mọi client đều được sửa.

### Missing, empty và invalid khác nhau

| Form parameter | Target Java | Kết quả điển hình |
| --- | --- | --- |
| Không gửi `age` | `Integer age` | `null`, có thể lỗi `@NotNull` |
| `age=` | `Integer age` | Có thể convert thành `null`, rồi lỗi `@NotNull` |
| `age=abc` | `Integer age` | Không convert được, `FieldError` với `typeMismatch` |
| `age=15` | `Integer age` | Convert thành công nhưng `@Min(18)` lỗi |
| `age=20` | `Integer age` | Convert và validation thành công |
| `fullName=   ` | `String` | Chuỗi có khoảng trắng; `@NotBlank` lỗi |
| `startDate=tomorrow` | `LocalDate` với ISO date | Lỗi formatter/conversion |

Một form HTML không có `Content-Type: application/json` chỉ vì một field nhìn giống JSON. Dùng `@ModelAttribute` cho form-urlencoded, dùng `@RequestBody`/Jackson cho JSON. Nếu POST gửi sai media type, có thể gặp `415` trước khi validation.

## 4. @ModelAttribute và BindingResult

`@ModelAttribute("registration")` chỉ định tên model object để Spring tạo/lấy đối tượng và bind request parameters. Ví dụ method xử lý POST:

```java
@PostMapping("/register")
public String submit(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult result,
        RedirectAttributes redirectAttributes) {

    if (result.hasErrors()) {
        return "registration";
    }
    redirectAttributes.addFlashAttribute("notice", "Đã nhận đăng ký");
    return "redirect:/register/success";
}
```

Đây là đoạn method minh họa trong controller; mã controller hoàn chỉnh ở phần dưới.

**`BindingResult` phải nằm ngay sau argument đang được bind/validate.** Đặt `Model`, `RedirectAttributes`, `@RequestParam` hoặc argument khác chen vào giữa có thể khiến Spring không thể gắn lỗi đúng target và dẫn tới exception. Nếu nhiều form object trong một handler, mỗi BindingResult cần đi ngay sau object tương ứng.

Các phương thức thực tế:

| Phương thức | Công dụng |
| --- | --- |
| `hasErrors()` / `getErrorCount()` | Phát hiện lỗi và đếm lỗi |
| `getFieldErrors()` | Lấy lỗi field (có thể nhiều lỗi một field) |
| `hasFieldErrors("age")` | Kiểm tra field tuổi |
| `getGlobalErrors()` | Lỗi object không gắn field riêng |
| `getAllErrors()` | Tất cả `FieldError` và `ObjectError` |
| `FieldError.getField()` | Tên field tương ứng |
| `FieldError.getCode()` | Mã lỗi chính như `typeMismatch`, `Min`, `NotBlank` |
| `FieldError.getCodes()` | Danh sách mã cụ thể tới tổng quát dùng cho message resolution |
| `FieldError.getRejectedValue()` | Giá trị bị từ chối, phải tránh log/lộ dữ liệu nhạy cảm |
| `FieldError.isBindingFailure()` | Gợi ý lỗi binding/conversion hay lỗi do validator |
| `rejectValue("field", "code", "fallback")` | Thêm field error theo quy tắc tùy chỉnh |
| `reject("code", "fallback")` | Thêm global error |
| `getSuppressedFields()` | Những field bị binder từ chối, không nhất thiết là FieldError |

Trong nhánh lỗi, controller trả lại `"registration"`. Spring MVC giữ attribute `registration` và companion BindingResult trong model. **Không tạo DTO mới sau khi POST đã có lỗi**, vì bạn có thể xóa giá trị người dùng vừa nhập và đánh mất rejected values mà Thymeleaf cần để hiển thị lại.

### Conversion error cũng có thể nằm trong BindingResult

`age=abc` không phải số. Binder không thể gán `Integer` nên ghi lỗi field với code chính thường là `typeMismatch`. `age=15` chuyển thành Integer được, nhưng `@Min(18)` thất bại, tạo mã `Min`. Hai tình huống khác nhau; hãy hiển thị thông điệp có ích riêng cho từng loại.

Nếu JSON body chứa `"age":"abc"` và được xử lý bằng `@RequestBody`, Jackson có thể báo `HttpMessageNotReadableException` trước Bean Validation, **không nhất thiết tạo cùng FieldError của @ModelAttribute**.

## 5. Jakarta Bean Validation trong form

Spring Boot 3 dùng namespace `jakarta.validation`, và dự án cần `spring-boot-starter-validation`. Những constraint phổ biến:

| Annotation | Ý nghĩa |
| --- | --- |
| `@NotBlank` | Chuỗi phải có ký tự không phải khoảng trắng |
| `@Email` | Kiểm tra cú pháp email theo validator, không xác nhận hộp thư tồn tại |
| `@Size(max=80)` | Giới hạn độ dài hợp lệ |
| `@NotNull` | Giá trị không được `null` |
| `@Min(18)` | Số >= 18; null thường được phép riêng bởi @Min |
| `@PastOrPresent` | Ngày không ở tương lai khi nghiệp vụ yêu cầu |

Nếu cần tuổi bắt buộc, dùng `Integer age` với `@NotNull @Min(18)`. `int` primitive có thể mang giá trị mặc định 0 trước kiểm tra, làm mất dấu vết thiếu/null. Với ngày tháng, `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` cho binder biết format `yyyy-MM-dd` của `LocalDate`; lỗi `startDate=tomorrow` là lỗi conversion. `@NotNull` không xác định được một chuỗi sai format có nghĩa ngày đã qua hay chưa.

Một field có thể có nhiều constraint và nhiều lỗi. Không dựa vào thứ tự thông báo khi test; nên xác định code hoặc xuất hiện ít nhất một thông báo phù hợp.

## 6. Thymeleaf form binding

Thymeleaf Spring dialect cung cấp:

```html
<form th:action="@{/register}"
      th:object="${registration}" method="post">
  <label for="fullName">Họ tên</label>
  <input id="fullName" type="text" th:field="*{fullName}">
</form>
```

- `th:object="${registration}"` gắn form backing object mà controller đặt vào model.
- `th:field="*{fullName}"` sinh và quản lý các thuộc tính `name`, `id`, `value` phù hợp Spring form binding.
- `th:action="@{/register}"` xây URL theo ứng dụng/context path thay vì hardcode một địa chỉ tuyệt đối.
- Controller GET và POST phải thống nhất tên model `registration`; thay tên thành `form` ở một nơi mà không đổi các nơi khác gây lỗi bind/render.
- `@Controller` trả tên view; `@RestController` ngầm `@ResponseBody`, nên return `"registration"` thường được ghi thành text body thay vì render HTML.

Khi POST lỗi, Thymeleaf có thể dùng rejected value của BindingResult để khôi phục raw input chưa convert được. Nếu dùng `<input type="number">` cho `age=abc`, một số browser chặn hoặc bỏ giá trị không phải số. Ví dụ học tập dùng `type="text" inputmode="numeric"` để thấy chính xác `abc` và error; trong production chọn loại input theo UX sau khi đã test.

## 7. th:errors, th:errorclass, #fields và thông báo lỗi

```html
<label for="email">Email</label>
<input id="email" type="text" th:field="*{email}"
       th:errorclass="invalid" aria-describedby="emailError">
<p id="emailError" class="error"
   th:if="${#fields.hasErrors('email')}"
   th:errors="*{email}">
  Email không hợp lệ
</p>
```

Ý nghĩa:

- `#fields.hasErrors("email")`: có lỗi cho field này?
- `th:errors="*{email}"`: render một hoặc nhiều messages của field đã được resolve.
- `th:errorclass="invalid"`: thêm class CSS khi field lỗi.
- `#fields.errors("email")`: danh sách messages nếu bạn muốn tự lặp bằng `th:each`.
- `#fields.hasGlobalErrors()` và `#fields.globalErrors()`: lỗi không gắn một field cụ thể.
- `#fields.hasErrors("all")` / `#fields.allErrors()`: tất cả lỗi nếu muốn làm tổng kết trên đầu form.

Lỗi global có thể hiển thị:

```html
<ul th:if="${#fields.hasGlobalErrors()}">
  <li th:each="err : ${#fields.globalErrors()}"
      th:text="${err}">Lỗi toàn biểu mẫu</li>
</ul>
```

Hãy kết hợp thông báo văn bản và CSS, không chỉ dùng viền đỏ. Đặt `label` và `aria-describedby` để hỗ trợ screen reader; khi có lỗi, `aria-invalid` có thể được gắn bằng Thymeleaf. Text do người dùng gửi phải được HTML-escape: dùng `th:text`/`th:errors`, tránh `th:utext` với nội dung không tin cậy.

## 8. Ví dụ runnable: Spring Boot 3 + Thymeleaf + Validation

Tạo project Maven Java 17+ với `spring-boot-starter-web`, `spring-boot-starter-thymeleaf`, `spring-boot-starter-validation` và `spring-boot-starter-test`. Ví dụ không cần database; hoạt động đăng ký chỉ mô phỏng chấp nhận một form hợp lệ.

Cấu trúc tệp:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  RegistrationForm.java
  RegistrationController.java
src/main/resources/templates/
  registration.html
  registration-success.html
src/test/java/com/example/demo/
  RegistrationControllerTest.java
```

### 8.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 8.2. RegistrationForm.java

```java
package com.example.demo;

import java.time.LocalDate;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.format.annotation.DateTimeFormat;

public class RegistrationForm {
    @NotBlank(message = "Vui lòng nhập họ tên")
    @Size(max = 80, message = "Họ tên tối đa 80 ký tự")
    private String fullName;

    @NotBlank(message = "Vui lòng nhập email")
    @Email(message = "Email chưa đúng định dạng")
    private String email;

    @NotNull(message = "Vui lòng nhập tuổi")
    @Min(value = 18, message = "Phải từ 18 tuổi trở lên")
    private Integer age;

    @NotNull(message = "Vui lòng nhập ngày bắt đầu")
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    public RegistrationForm() {}

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }

    public LocalDate getStartDate() { return startDate; }
    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }
}
```

Dùng `Integer` cho nullable/blank input và `LocalDate` cho ngày không có timezone. Sau POST, tất cả các getter/setter cho phép binder xử lý giá trị. DTO không có role, ID, trạng thái admin hoặc field từ database.

### 8.3. RegistrationController.java

```java
package com.example.demo;

import jakarta.validation.Valid;
import java.util.Locale;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/register")
public class RegistrationController {

    @GetMapping
    public String showForm(Model model) {
        model.addAttribute("registration", new RegistrationForm());
        return "registration";
    }

    @PostMapping
    public String submit(
            @Valid @ModelAttribute("registration") RegistrationForm form,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {

        // Chỉ để minh họa global error, không phải quy tắc chung.
        if (form.getEmail() != null
                && form.getEmail().toLowerCase(Locale.ROOT)
                    .endsWith("@blocked.example")) {
            errors.reject(
                    "registration.emailDomainBlocked",
                    "Địa chỉ email này không được phép đăng ký");
        }

        if (errors.hasErrors()) {
            return "registration";
        }

        // Demo không ghi DB. Ứng dụng thực gọi service tại đây,
        // sau khi đã validate và kiểm tra quyền nghiệp vụ.
        redirectAttributes.addFlashAttribute(
                "notice", "Đăng ký đã được tiếp nhận");
        return "redirect:/register/success";
    }

    @GetMapping("/success")
    public String success() {
        return "registration-success";
    }
}
```

Controller minh họa:

- GET đặt một object vào model, POST nhận đúng tên model.
- `BindingResult errors` ở ngay sau form argument.
- `errors.reject(...)` tạo global error. Rule domain ở đây chỉ là demo; production nên dùng validator/service riêng để giữ controller tập trung vào HTTP/view.
- Có lỗi: return cùng view, không tạo object mới và không gọi service lưu.
- Không lỗi: dùng Post/Redirect/Get. `addFlashAttribute` chuyển message sang GET kế tiếp, không phải persistence.
- `redirect:/register/success` được Spring tạo Location, giữ browser ở URL GET khi refresh.

### 8.4. registration.html

Tệp `src/main/resources/templates/registration.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Đăng ký</title>
  <style>
    body { max-width: 40rem; margin: 2rem auto; padding: 1rem;
           font-family: system-ui, sans-serif; line-height: 1.5; }
    label { display: block; font-weight: 600; margin-top: 1rem; }
    input { width: 100%; box-sizing: border-box; padding: .5rem; }
    input.invalid { border: 2px solid #b42318; }
    .error { color: #b42318; margin: .3rem 0 .6rem; }
    .global-error { border: 2px solid #b42318; padding: .6rem; }
    button { margin-top: 1.5rem; padding: .6rem 1rem; }
  </style>
</head>
<body>
  <h1>Đăng ký</h1>
  <p>Hãy nhập đầy đủ thông tin. Tuổi tối thiểu là 18.</p>

  <form method="post" th:action="@{/register}"
        th:object="${registration}">

    <div class="global-error" role="alert"
         th:if="${#fields.hasGlobalErrors()}">
      <p>Biểu mẫu chưa được chấp nhận:</p>
      <ul>
        <li th:each="err : ${#fields.globalErrors()}"
            th:text="${err}">Lỗi toàn biểu mẫu</li>
      </ul>
    </div>

    <label for="fullName">Họ tên</label>
    <input id="fullName" type="text" th:field="*{fullName}"
           th:errorclass="invalid"
           th:attr="aria-invalid=${#fields.hasErrors('fullName')}"
           aria-describedby="fullNameError">
    <p id="fullNameError" class="error"
       th:if="${#fields.hasErrors('fullName')}"
       th:errors="*{fullName}">Họ tên không hợp lệ</p>

    <label for="email">Email</label>
    <input id="email" type="text" th:field="*{email}"
           th:errorclass="invalid"
           th:attr="aria-invalid=${#fields.hasErrors('email')}"
           aria-describedby="emailError">
    <p id="emailError" class="error"
       th:if="${#fields.hasErrors('email')}"
       th:errors="*{email}">Email không hợp lệ</p>

    <label for="age">Tuổi</label>
    <input id="age" type="text" inputmode="numeric"
           th:field="*{age}"
           th:errorclass="invalid"
           th:attr="aria-invalid=${#fields.hasErrors('age')}"
           aria-describedby="ageError">
    <p id="ageError" class="error"
       th:if="${#fields.hasErrors('age')}"
       th:errors="*{age}">Tuổi không hợp lệ</p>

    <label for="startDate">Ngày bắt đầu (yyyy-MM-dd)</label>
    <input id="startDate" type="text" placeholder="2026-10-21"
           th:field="*{startDate}"
           th:errorclass="invalid"
           th:attr="aria-invalid=${#fields.hasErrors('startDate')}"
           aria-describedby="dateError">
    <p id="dateError" class="error"
       th:if="${#fields.hasErrors('startDate')}"
       th:errors="*{startDate}">Ngày không hợp lệ</p>

    <button type="submit">Gửi đăng ký</button>
  </form>
</body>
</html>
```

`th:field` đảm bảo các giá trị đã nhập được khôi phục khi render lại form, kể cả trường hợp `age=abc` chưa chuyển thành Integer (nằm trong rejected value của BindingResult). Để quan sát lỗi này, ví dụ dùng input `type="text" inputmode="numeric"`; nhiều trình duyệt tự từ chối giá trị không phải số trong input `type="number"`.

Thymeleaf `th:errors` hiển thị message đã resolve. `th:errorclass` chỉ thêm class CSS nếu field lỗi. `th:attr` đặt thuộc tính ARIA theo `#fields.hasErrors`; trang có thông báo bằng chữ, không phụ thuộc riêng màu đỏ.

Khi ứng dụng bật Spring Security, HTML POST có thể cần CSRF token. Với Thymeleaf Spring integration, Spring Security có thể tự thêm hidden input qua `RequestDataValueProcessor` khi render `th:action`; **kiểm tra HTML thực tế** để chắc chắn đã có token, hoặc tích hợp CSRF theo hướng dẫn security. Không tắt CSRF toàn cục chỉ để form POST chạy.

### 8.5. registration-success.html

Tệp `src/main/resources/templates/registration-success.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Đăng ký thành công</title>
</head>
<body>
  <h1>Đã tiếp nhận biểu mẫu</h1>
  <p th:if="${notice != null}" th:text="${notice}">
    Đăng ký đã được tiếp nhận
  </p>
  <a th:href="@{/register}">Gửi biểu mẫu khác</a>
</body>
</html>
```

Template vẫn hiển thị được khi GET trực tiếp mà không có flash message. `th:text` escape thông điệp an toàn; tránh dùng `th:utext` với message chứa dữ liệu client không tin cậy.

### 8.6. Chạy ứng dụng

Từ project Maven có wrapper:

```bash
./mvnw spring-boot:run
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Mặc định truy cập `http://localhost:8080/register` nếu `server.port` chưa thay đổi. Các tệp Java này cần Spring Web, Thymeleaf và Bean Validation trên classpath; chúng không biên dịch bằng `javac` độc lập với không có dependencies.

## 9. Thực hành HTTP: valid, validation fail, conversion fail, global fail

### 9.1. GET biểu mẫu

```bash
curl -i http://localhost:8080/register
```

Kỳ vọng HTTP 200, `Content-Type` tương thích `text/html` và HTML có các input `name="fullName"`, `name="email"`, `name="age"`, `name="startDate"`. Client nhận HTML đã render, không còn `th:field` nguyên văn.

### 9.2. POST hợp lệ

```bash
curl -i http://localhost:8080/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=Lan" \
  --data-urlencode "email=lan@example.com" \
  --data-urlencode "age=20" \
  --data-urlencode "startDate=2026-10-21"
```

Kỳ vọng response redirect HTTP 302 (URL mới `/register/success`), vì controller không có lỗi và thực hiện Post/Redirect/Get. Header Location thực tế có thể theo context path/gateway.

### 9.3. POST validation thất bại

```bash
curl -i http://localhost:8080/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=" \
  --data-urlencode "email=bad-email" \
  --data-urlencode "age=15" \
  --data-urlencode "startDate=2026-10-21"
```

Trong demo, controller trả lại view `registration`; thông thường HTTP 200 khi render lại HTML có lỗi. Điều này **không có nghĩa đã lưu dữ liệu**, vì handler kiểm tra `hasErrors()`. Ứng dụng khác có thể cố ý trả 400/422 theo UX/HTTP contract, nhưng form view mặc định thường trả 200.

### 9.4. Lỗi conversion, giá trị vẫn hiển thị

```bash
curl -i http://localhost:8080/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=Lan" \
  --data-urlencode "email=lan@example.com" \
  --data-urlencode "age=abc" \
  --data-urlencode "startDate=2026-10-21"
```

`age=abc` không parse được Integer, `BindingResult` lưu `typeMismatch`; Thymeleaf thường render lại text input với `value="abc"` và message nhập số hợp lệ. Nếu POST method tạo `new RegistrationForm()` sau khi có lỗi, rejected value có thể bị mất.

### 9.5. Lỗi global

```bash
curl -i http://localhost:8080/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=Lan" \
  --data-urlencode "email=lan@blocked.example" \
  --data-urlencode "age=20" \
  --data-urlencode "startDate=2026-10-21"
```

Tình huống này thỏa Bean Validation về cú pháp email nhưng vi phạm rule demo; `errors.reject(...)` thêm lỗi global và template hiển thị ở đầu form.

### 9.6. Lỗi định dạng ngày

```bash
curl -i http://localhost:8080/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=Lan" \
  --data-urlencode "email=lan@example.com" \
  --data-urlencode "age=20" \
  --data-urlencode "startDate=tomorrow"
```

`startDate=tomorrow` không khớp định dạng ISO date mà formatter mong đợi; binding lỗi `typeMismatch` cho ngày, khác việc có LocalDate hợp lệ nhưng business rule cho rằng ngày đó không cho phép.

## 10. Kiểm thử MockMvc cả model và HTML

Tệp `src/test/java/com/example/demo/RegistrationControllerTest.java`, sử dụng `spring-boot-starter-test`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void getFormShowsFields() throws Exception {
        mvc.perform(get("/register"))
            .andExpect(status().isOk())
            .andExpect(view().name("registration"))
            .andExpect(model().attributeExists("registration"))
            .andExpect(content().string(containsString("name=\"fullName\"")));
    }

    @Test
    void invalidInputIsShownInHtml() throws Exception {
        mvc.perform(post("/register")
                .param("fullName", "")
                .param("email", "bad-email")
                .param("age", "15")
                .param("startDate", "2026-10-21"))
            .andExpect(status().isOk())
            .andExpect(view().name("registration"))
            .andExpect(model().attributeHasFieldErrors(
                    "registration", "fullName", "email", "age"))
            .andExpect(content().string(
                    containsString("Vui lòng nhập họ tên")));
    }

    @Test
    void invalidIntegerRetainsRejectedText() throws Exception {
        mvc.perform(post("/register")
                .param("fullName", "Lan")
                .param("email", "lan@example.com")
                .param("age", "abc")
                .param("startDate", "2026-10-21"))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasFieldErrorCode(
                    "registration", "age", "typeMismatch"))
            .andExpect(content().string(containsString("value=\"abc\"")));
    }

    @Test
    void globalRuleAddsGlobalError() throws Exception {
        mvc.perform(post("/register")
                .param("fullName", "Lan")
                .param("email", "lan@blocked.example")
                .param("age", "20")
                .param("startDate", "2026-10-21"))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasErrors("registration"))
            .andExpect(content().string(containsString(
                    "Địa chỉ email này không được phép đăng ký")));
    }

    @Test
    void validFormRedirects() throws Exception {
        mvc.perform(post("/register")
                .param("fullName", "Lan")
                .param("email", "lan@example.com")
                .param("age", "20")
                .param("startDate", "2026-10-21"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/register/success"))
            .andExpect(flash().attributeExists("notice"));
    }
}
```

Chạy `./mvnw test` (PowerShell: `.\mvnw.cmd test`). Bộ test này là **mẫu nguồn dành cho project Boot 3 có dependencies đúng**, chưa được thực thi trong bất kỳ repository người dùng nào. Nếu ứng dụng bật Spring Security, phải cấu hình test với `spring-security-test` và CSRF/token/role phù hợp; thiếu CSRF có thể gây HTTP 403 trước controller.

Vì sao cần cả model và HTML assertions? `model().attributeHasFieldErrorCode(...)` xác nhận Spring phát hiện `typeMismatch`, nhưng người dùng có thể vẫn không thấy thông báo nếu template sai. Kiểm tra HTML giúp phát hiện biểu mẫu bỏ quên `th:errors`/th:object hoặc không giữ rejected input.

## 11. MessageSource và thông báo tiếng Việt

Thông báo `@NotBlank(message="...")` có thể đặt trực tiếp trong annotations khi demo. Trong ứng dụng lớn, nên dùng mã lỗi và resource bundle để quốc tế hóa. Spring có thể sinh các code cho lỗi chuyển kiểu tuổi như:

```text
typeMismatch.registration.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
```

Ví dụ tệp `src/main/resources/messages.properties`:

```properties
typeMismatch.registration.age=Tuổi phải là số nguyên hợp lệ
typeMismatch.registration.startDate=Ngày phải theo yyyy-MM-dd
typeMismatch=Giá trị không đúng định dạng
```

Khi cần nhiều ngôn ngữ, dùng `messages_vi.properties`/`messages_en.properties` và cấu hình locale thích hợp. `MessageSource`/Bean Validation message interpolation giúp tách câu chữ hiển thị khỏi logic; tránh lấy `exception.getMessage()` hoặc rejected values nhạy cảm đưa thẳng tới UI.

Mã `typeMismatch` đến từ binding, còn mã `NotBlank`, `Email`, `Min` từ validation. `getCodes()` thường chứa mã cụ thể cho object/field/type để resolve message theo mức ưu tiên. Không hardcode một chuỗi message trong test nếu ứng dụng đổi locale; với test HTML có thể chọn locale cố định.

## 12. Lỗi global, lỗi chéo field và custom validation

Một điều kiện liên quan nhiều field, ví dụ `startDate` trước `endDate`, có thể tạo global error:

```java
errors.reject(
    "registration.invalidPeriod",
    "Ngày kết thúc phải sau ngày bắt đầu");
```

Đây chỉ là snippet trong method có `BindingResult errors`; DTO demo không chứa `endDate`. Nếu biết chính xác input nào phải sửa, dùng:

```java
errors.rejectValue(
    "startDate",
    "registration.startDateInvalid",
    "Ngày bắt đầu không được chấp nhận");
```

`reject(...)` tạo global `ObjectError`. `rejectValue(...)` tạo `FieldError`. Thymeleaf hiển thị chúng bằng `#fields.globalErrors()` hoặc `th:errors="*{startDate}"` tương ứng. Business validation phức tạp nên ở validator/service thích hợp để tránh controller chứa nhiều quy tắc hoặc query database tốn chi phí trước khi form đã pass kiểm tra định dạng.

## 13. WebDataBinder, allowed fields và bảo mật

Form DTO bảo vệ input surface, nhưng nested binding hoặc mass assignment vẫn cần xem xét. Có thể đặt trong controller:

```java
@InitBinder("registration")
public void customizeBinder(WebDataBinder binder) {
    binder.setAllowedFields(
        "fullName", "email", "age", "startDate");
}
```

Đây là một **đoạn method có thể thêm vào controller mẫu** với imports `org.springframework.web.bind.annotation.InitBinder`, `org.springframework.web.bind.WebDataBinder`. Không tự động bắt buộc dùng khi DTO đã nhỏ, nhưng có thể bổ sung defense-in-depth.

Field bị chặn bởi allowlist thường được ghi tại `BindingResult.getSuppressedFields()`; không phải lúc nào tạo FieldError và `hasErrors()` cũng không nhất thiết thành true. Nếu policy yêu cầu từ chối form có field ngoài danh sách:

```java
if (errors.getSuppressedFields().length > 0) {
    errors.reject(
        "registration.unexpectedFields",
        "Biểu mẫu có trường không được phép gửi");
}
```

Chỉ dùng sau khi thực sự cấu hình allowlist. `@InitBinder` còn có thể cấu hình `Formatter`, `PropertyEditor`, `StringTrimmerEditor`. Trimmer chuyển chuỗi trắng thành null có thể làm thay đổi phân biệt missing, empty, blank; hãy test lại tất cả trường hợp.

## 14. Form lỗi và Post/Redirect/Get

| Kết quả POST | Hành động thông dụng | Lý do |
| --- | --- | --- |
| Binding/validation lỗi | `return "registration"` | Giữ object và BindingResult, render lỗi và rejected input |
| Business rule lỗi trình bày trong form | `errors.reject` hoặc `rejectValue` rồi cùng view | Hiển thị lỗi đúng cấp field/global |
| POST đã được xử lý thành công | `redirect:/register/success` | Browser refresh GET, tránh gửi POST lần hai |
| Business conflict sau khi kiểm tra DB | Contract ứng dụng quyết định: form error/409/redirect | Tách lỗi người dùng và server |
| Hệ thống/backend thất bại | Error handling thích hợp, không xác nhận thành công | Không nuốt lỗi thành success |

HTTP 200 với HTML có lỗi form chỉ có nghĩa render view thành công, **không** nghĩa đã lưu hay chấp nhận nghiệp vụ. Nếu API khách hàng yêu cầu 400 hoặc 422, có thể chủ động thiết kế status đó; form MVC mặc định trả view thường dùng 200. Redirect ở nhánh lỗi có thể làm mất BindingResult nếu không triển khai đúng flash/error preservation; vì vậy demo không redirect khi lỗi.

Flash attribute lưu message ngắn sang request GET kế tiếp, không phải session dữ liệu bền hay nơi lưu password. Khi GET success được gọi trực tiếp, template vẫn nên an toàn khi `notice` vắng mặt.

## 15. Accessibility và an toàn nội dung

- Mỗi input có label rõ, text error cạnh đúng field, id/`aria-describedby` phù hợp.
- Kết hợp text với CSS/class, tránh chỉ dùng màu để báo lỗi.
- Có thể thêm error summary/link tới field và focus management cho form lớn, đặc biệt khi validation server-side.
- Dữ liệu do client nhập được escape khi hiển thị. `th:text`/`th:errors` an toàn hơn chèn unescaped HTML bằng `th:utext`.
- Không log `rejectedValue` chứa password, token, thẻ thanh toán hoặc PII; nên gắn code và field name nếu cần observability.
- Nếu dùng email hoặc tên trong flash message, cân nhắc quyền riêng tư. Ví dụ demo chọn thông điệp chung để không echo PII.
- HTML5 `required`/`min` hỗ trợ UX nhưng không thay validation server; attacker có thể gửi request thủ công.
- Nếu dùng Spring Security, hãy xác nhận CSRF token của form POST, quyền truy cập GET/POST và tránh cho phép sửa object ngoài quyền.

## 16. Lỗi hay gặp và cách debug

1. **GET không thêm form object:** template `th:object` không có target.
2. **GET/POST/template dùng ba tên khác nhau:** lỗi/giá trị không nối được.
3. **BindingResult đặt sai vị trí:** Spring không lấy đúng errors, có thể ném exception.
4. **Quên @Valid/validation dependency:** constraint không chạy như mong muốn.
5. **Tạo RegistrationForm mới trong nhánh POST lỗi:** xóa input và BindingResult.
6. **Redirect khi lỗi form mà không giữ flash state đúng:** người dùng mất error messages.
7. **Chỉ hiển thị generic error:** không biết ô nào cần sửa.
8. **Sai type conversion thành một message Min:** `abc` không phải số dưới 18.
9. **`th:value` tự đặt ghi đè `th:field`:** rejected value có thể không được tái hiện.
10. **Đổi input text sang type number rồi đòi browser hiển thị `abc`:** browser có thể bỏ giá trị invalid.
11. **Quên thông báo global:** `reject` lỗi object không xuất hiện cạnh field nào.
12. **Dùng @RestController để trả logical view name:** trình duyệt thấy chữ `registration` thay vì HTML.
13. **Bind JPA entity trực tiếp:** overposting và lộ trường không cho phép.
14. **Bỏ qua getSuppressedFields():** field bị từ chối không nhất thiết gây hasErrors.
15. **Không kiểm tra security/CSRF:** POST nhận 403 trước binder.
16. **Không test HTML:** model có lỗi nhưng template vẫn không hiển thị.
17. **Phát message lỗi chứa exception nội bộ:** lộ class, SQL hoặc dữ liệu client.
18. **Thực hiện side effect trước khi hasErrors():** lưu form sai dữ liệu.
19. **Thay đổi locale mà test cứng câu chữ:** test đổ vỡ không liên quan behavior.
20. **Không test multi-value params:** client gửi field lặp có thể có hành vi không mong muốn tùy binder.
21. **Form action hardcode sai context path:** POST vào URL khác với mapping.
22. **Cho rằng browser validation đủ:** curl và client tự viết vẫn gửi request sai.

## 17. Checklist kiểm tra

- [ ] GET hiển thị đúng template và model attribute tên `registration`.
- [ ] POST dùng `@Valid @ModelAttribute("registration")` và `BindingResult` ngay kế.
- [ ] DTO chỉ có trường client được phép nhập; không bind entity nhạy cảm.
- [ ] Có validation cho required, blank, range, date format và email syntax.
- [ ] Lỗi form giữ object/BindingResult, không gửi dữ liệu vào service.
- [ ] Template dùng `th:object`, `th:field`, `th:errors`, `th:errorclass`.
- [ ] Lỗi global được hiển thị trong khu vực dễ nhận biết.
- [ ] Lỗi conversion có thể giữ rejected input (phù hợp loại HTML input).
- [ ] Có test model BindingResult và HTML đã render.
- [ ] Valid POST redirect và dùng flash message phù hợp.
- [ ] Có CSRF token và quyền khi dùng Spring Security.
- [ ] Text/error/input được HTML-escape, không để lộ dữ liệu nhạy cảm.
- [ ] Resource bundles/message codes phù hợp locale nếu hỗ trợ đa ngôn ngữ.

## 18. Tự kiểm tra

**1.** Vì sao `BindingResult` phải đứng ngay sau `@Valid @ModelAttribute`?

**Đáp án:** Để Spring liên kết errors với đúng model argument. Đặt sai vị trí có thể dẫn đến lỗi resolve argument hoặc mất handling tại controller.

**2.** `age=abc` tạo lỗi gì khi bind vào `Integer`?

**Đáp án:** Lỗi conversion trong binding, thường mã `typeMismatch`. Nó khác `@Min` vì chưa có giá trị số.

**3.** `age=15` thì sao?

**Đáp án:** Convert thành Integer thành công rồi fail constraint `@Min(18)`.

**4.** Dùng gì để hiển thị lỗi field email?

**Đáp án:** `#fields.hasErrors('email')` để hỏi, `th:errors="*{email}"` để render messages, `th:errorclass` để thêm CSS class.

**5.** Global error hiển thị thế nào?

**Đáp án:** Dùng `errors.reject(...)` và `#fields.hasGlobalErrors()`/`#fields.globalErrors()` trong template.

**6.** Vì sao không tạo object mới khi POST lỗi?

**Đáp án:** Nó có thể ghi đè giá trị đã bind và làm mất rejected values/messages trong BindingResult.

**7.** Vì sao valid POST nên redirect?

**Đáp án:** Post/Redirect/Get đưa browser sang GET, refresh không gửi lại POST.

**8.** `hasErrors()==false` có bảo đảm không có field lạ không?

**Đáp án:** Không. Kiểm tra `getSuppressedFields()` nếu dùng allowlist và có chính sách từ chối trường lạ.

**9.** MockMvc test field error đã đủ chứng minh người dùng thấy lỗi chưa?

**Đáp án:** Chưa. Cần kiểm tra rendered HTML, field value và error text/class.

**10.** Nếu có CSRF filter, POST không token có thể trả gì trước controller?

**Đáp án:** Thường 403, tùy cấu hình. Đó là security filter failure, không phải Bean Validation của form.

## 19. Tài liệu tham khảo

- Spring Framework — `@ModelAttribute`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — MVC validation và BindingResult: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `WebDataBinder` / `@InitBinder`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework — Type conversion/formatting: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Thymeleaf 3.1 + Spring integration, form binding và error messages: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
- Thymeleaf `#fields` API: https://www.thymeleaf.org/apidocs/thymeleaf-spring6/3.1.1.RELEASE/org/thymeleaf/spring6/expression/Fields.html
- Spring Framework — RedirectAttributes và FlashMap: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Jakarta Bean Validation: https://jakarta.ee/specifications/bean-validation/
