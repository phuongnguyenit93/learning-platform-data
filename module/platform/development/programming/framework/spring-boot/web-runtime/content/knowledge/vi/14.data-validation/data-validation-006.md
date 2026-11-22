# BindingResult trong Spring MVC và điều kiện xử lý tại Controller

## 1. Mục tiêu và tình huống thực tế

Một form HTML có thể gửi tên người dùng rỗng, email sai định dạng hoặc tuổi không phải số. Ứng dụng Spring MVC phải phân biệt dữ liệu **không thể bind sang kiểu Java**, dữ liệu **bind được nhưng vi phạm quy tắc validation** và dữ liệu **hợp lệ để xử lý nghiệp vụ**.

`BindingResult` cho controller biết những lỗi phát sinh trong quá trình **data binding** và **validation** của một đối tượng cụ thể. Nhờ đó, controller quyết định có nên trả lại trang form với thông báo lỗi, hay chuyển sang lưu dữ liệu và redirect khi đầu vào hợp lệ.

Ví dụ cốt lõi:

```java
@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "signup/form";
    }

    return "redirect:/signup/success";
}
```

Hai điểm cần ghi nhớ ngay:

1. **`BindingResult` phải nằm ngay sau tham số mà nó kiểm soát**, ở đây là `@Valid @ModelAttribute("signup") SignupForm form`.
2. **`@Valid` không tự động ngăn controller chạy nếu có `BindingResult` hợp lệ bên cạnh.** Controller nhận lỗi và phải chủ động rẽ nhánh `hasErrors()` trước khi gọi nghiệp vụ.

Bài học tập trung vào **Spring MVC/Servlet stack**, với ví dụ Spring Boot **3.5.x**, Java **17**, Thymeleaf và MockMvc. Spring WebFlux có API binding/validation tương ứng nhưng luồng xử lý khác, không mặc nhiên áp dụng mọi chi tiết của MVC.

## 2. Binding, conversion và validation là ba khái niệm liên quan nhưng khác nhau

| Khâu | Nhiệm vụ | Ví dụ thành công | Ví dụ lỗi |
|---|---|---|---|
| Data binding | Gắn request fields vào thuộc tính object | `fullName=Lan` → `form.fullName` | Field không được bind hoặc path không phù hợp |
| Type conversion | Chuyển chuỗi HTTP sang kiểu thuộc tính | `age=25` → `Integer.valueOf(25)` | `age=abc` không chuyển được sang `Integer` |
| Bean Validation | Kiểm tra constraint trên object đã được bind | `age=25` đáp ứng `@Min(18)` | `age=16` vi phạm `@Min(18)` |
| Business validation | Kiểm tra quy tắc nghiệp vụ theo ngữ cảnh | Email chưa tồn tại, gói dịch vụ hợp lệ | Email đã đăng ký, quota hết hoặc quyền bị từ chối |

`BindingResult` có thể chứa **field errors** do conversion/binding hoặc Bean Validation tạo ra và **global errors** liên quan đến cả object. Business validation cũng có thể chủ động bổ sung lỗi bằng `rejectValue` hoặc `reject` trước khi quyết định xử lý.

Ví dụ cùng một field `age`:

- `age=abc`: type conversion thất bại, thường có field error mã `typeMismatch`.
- `age=15`: conversion thành công, nhưng `@Min(18)` thất bại.
- `age=20`: qua constraint, nhưng vẫn có thể vi phạm một quy tắc kinh doanh như yêu cầu độ tuổi cao hơn cho một sản phẩm cụ thể.

Không kết luận rằng object bind thành công thì đã an toàn để ghi database; cũng không xem `BindingResult` là cơ chế thay thế authentication/authorization.

## 3. Cơ chế hoạt động trong Spring MVC

Với form `application/x-www-form-urlencoded`:

```text
POST /signup
fullName=Lan&email=lan@example.org&age=25
             |
             v
DispatcherServlet
             |
             v
HandlerMapping -> HandlerAdapter
             |
             v
@ModelAttribute("signup") SignupForm
  - tạo/lấy form object
  - WebDataBinder gắn các request parameters
  - ConversionService chuyển String -> kiểu field
  - Validator kiểm tra constraint nếu có @Valid
             |
             v
BindingResult cho object "signup"
  - FieldError nếu sai field
  - ObjectError nếu sai toàn bộ object
             |
             v
Controller submit(form, bindingResult)
  - hasErrors() == true -> return "signup/form"
  - hasErrors() == false -> xử lý -> redirect
             |
             v
ViewResolver + Thymeleaf -> HTML / redirect response
```

`WebDataBinder` kết hợp request data, conversion và validator; kết quả được giữ trong một `BindingResult` gắn với **tên model attribute cụ thể**. Trong trường hợp render form, Spring MVC đưa object và thông tin binding errors vào model để template engine hiển thị.

**Điều kiện quan trọng:** việc đặt một `BindingResult` trong chữ ký method không tự kích hoạt Bean Validation. Cần `@Valid`, `@Validated` hoặc gọi validation theo cách thích hợp; còn lỗi conversion có thể được ghi nhận ngay trong binding dù không có annotation validation.

## 4. BindingResult là gì, dùng được những phương thức nào?

Import đúng cho Spring MVC:

```java
import org.springframework.validation.BindingResult;
```

`BindingResult` là interface kế thừa `Errors`. Nó bổ sung khả năng truy cập thông tin binding, model và field value ngoài các API báo lỗi của `Errors`.

| API | Tác dụng |
|---|---|
| `hasErrors()` | Có ít nhất một field/global error không? |
| `getErrorCount()` | Tổng số lỗi được ghi nhận |
| `hasFieldErrors("email")` | Riêng field `email` có lỗi không? |
| `getFieldError("age")` | Lấy một `FieldError` của field |
| `getFieldErrors()` | Danh sách lỗi của các field |
| `getGlobalErrors()` | Danh sách lỗi ở cấp object |
| `getAllErrors()` | Tất cả `ObjectError` và `FieldError` |
| `getObjectName()` | Tên object được bind, ví dụ `signup` |
| `rejectValue(field, code, message)` | Chủ động thêm lỗi cho một field |
| `reject(code, message)` | Chủ động thêm lỗi ở cấp object |
| `getFieldValue(field)` | Giá trị field phù hợp cho cơ chế hiển thị sau binding |
| `getSuppressedFields()` | Những field bị suppression theo cấu hình binder |
| `getModel()` | Map chứa object và BindingResult của object đó |

Ví dụ kiểm tra:

```java
if (bindingResult.hasFieldErrors("email")) {
    // Có lỗi cho email, không nên tiếp tục xử lý phụ thuộc email.
}
if (bindingResult.hasErrors()) {
    return "signup/form";
}
```

Không nên log bừa `getRejectedValue()` hoặc toàn bộ `BindingResult`, vì các giá trị bị từ chối có thể chứa email, địa chỉ, token hoặc dữ liệu cá nhân. Log **mã lỗi**, **tên field** và một request ID phù hợp thường an toàn hơn.

## 5. Vị trí bắt buộc của BindingResult trong chữ ký Controller

**Đúng:**

```java
@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult bindingResult,
        Model model) {
    // BindingResult gắn trực tiếp với form ở trước nó.
    return bindingResult.hasErrors()
        ? "signup/form"
        : "redirect:/signup/success";
}
```

**Sai hoặc dễ phát sinh lỗi:**

```java
@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        Model model,
        BindingResult bindingResult) {
    // BindingResult không đứng ngay sau đối tượng được bind.
    return "signup/form";
}
```

Trong Spring MVC, `Errors` / `BindingResult` phải ngay sau đối tượng tương ứng để handler argument resolver xác định chính xác nơi áp kết quả lỗi. Nếu đặt cách bởi `Model`, `RedirectAttributes`, `@RequestParam` hoặc một object khác, runtime có thể ném exception hoặc không cho phép kiểm soát lỗi như mong muốn.

Khi có **nhiều form objects**, mỗi object cần một `BindingResult` đứng ngay sau:

```java
public String process(
        @Valid @ModelAttribute("customer") CustomerForm customer,
        BindingResult customerErrors,
        @Valid @ModelAttribute("address") AddressForm address,
        BindingResult addressErrors) {
    if (customerErrors.hasErrors() || addressErrors.hasErrors()) {
        return "checkout/form";
    }
    return "redirect:/checkout/success";
}
```

Đoạn này là fragment minh họa; `CustomerForm` và `AddressForm` là class giả định, method cần annotation mapping. Không nên gom một `BindingResult` cho hai form objects.

## 6. Dependencies và cấu trúc project thực hành

Tạo project Spring Boot **3.5.x**, **Java 17**, Maven với Spring Web, Thymeleaf và Validation. Trong `pom.xml` đã có Spring Boot parent hoặc dependency management, cần:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
```

Đây là phần dependencies, **không phải file POM đầy đủ**. Nếu thiếu starter validation hoặc Jakarta Bean Validation provider tương đương, các annotation `@NotBlank`, `@Min`... có thể không được áp dụng như kỳ vọng.

Tổ chức các file:

```text
src/main/java/com/example/forms/
    FormsApplication.java
    SignupForm.java
    SignupController.java
src/main/resources/
    application.properties
    templates/
        signup/
            form.html
            success.html
src/test/java/com/example/forms/
    SignupControllerTest.java
```

Các code Java dưới đây là các file dành cho project Maven/Spring Boot; không thể biên dịch toàn bộ chỉ với `javac` của JDK vì còn dependency Spring, Jakarta Validation và Thymeleaf.

## 7. Tạo model dữ liệu đầu vào có constraint rõ ràng

File `src/main/java/com/example/forms/SignupForm.java`:

```java
package com.example.forms;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class SignupForm {

    @NotBlank(message = "Họ tên không được để trống")
    @Size(min = 2, max = 40,
          message = "Họ tên phải dài từ 2 đến 40 ký tự")
    private String fullName;

    @NotBlank(message = "Email không được để trống")
    @Email(message = "Email không đúng định dạng")
    private String email;

    @NotNull(message = "Tuổi là bắt buộc")
    @Min(value = 18, message = "Phải đủ 18 tuổi")
    @Max(value = 120, message = "Tuổi không hợp lệ")
    private Integer age;

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

Tại sao dùng `Integer` thay vì `int`? Vì `Integer` có thể là `null` khi tuổi chưa được điền, kết hợp rõ ràng với `@NotNull`. Trường `age=abc` có thể tạo `typeMismatch` vì không thể convert chuỗi thành `Integer`; `age=16` convert được nhưng vi phạm `@Min(18)`.

`@Email` kiểm tra định dạng email theo provider; **không xác minh email thật hoặc quyền sở hữu mailbox**. `@NotBlank` yêu cầu khác rỗng/blank. `@Size` kiểm tra độ dài chuỗi theo quy tắc constraint; business validation vẫn phải bổ sung khi cần.

## 8. @SpringBootApplication và cấu hình cơ bản

File `src/main/java/com/example/forms/FormsApplication.java`:

```java
package com.example.forms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormsApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormsApplication.class, args);
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.thymeleaf.cache=false
```

`spring.thymeleaf.cache=false` chỉ phù hợp khi phát triển để sửa template nhanh; production thường nên để cache mặc định nhằm giảm chi phí render. Không cần đăng ký bean `BindingResult` thủ công: Spring MVC tạo kết quả binding tương ứng với model attribute trong mỗi request.

## 9. Controller: kiểm tra lỗi trước khi quyết định xử lý

File `src/main/java/com/example/forms/SignupController.java`:

```java
package com.example.forms;

import jakarta.validation.Valid;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class SignupController {

    @GetMapping("/signup")
    public String showForm(Model model) {
        model.addAttribute("signup", new SignupForm());
        return "signup/form";
    }

    @PostMapping("/signup")
    public String submit(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult bindingResult,
            RedirectAttributes redirectAttributes) {

        if ("admin".equalsIgnoreCase(form.getFullName())) {
            bindingResult.rejectValue(
                    "fullName",
                    "name.reserved",
                    "Tên này không được sử dụng");
        }

        if (bindingResult.hasErrors()) {
            return "signup/form";
        }

        // Demo chưa lưu dữ liệu; chỉ minh họa nhánh hợp lệ.
        redirectAttributes.addFlashAttribute(
                "notice", "Dữ liệu đăng ký hợp lệ");
        return "redirect:/signup/success";
    }

    @GetMapping("/signup/success")
    public String success() {
        return "signup/success";
    }
}
```

Logic quan trọng:

1. GET `/signup` đưa một `SignupForm` rỗng vào model.
2. POST tự bind form fields vào `SignupForm`, convert `age` và chạy Bean Validation do có `@Valid`.
3. `BindingResult` đứng **ngay sau** form và chứa field/global errors.
4. Controller bổ sung rule riêng: tên `admin` bị từ chối bằng `rejectValue`.
5. Khi có lỗi, `return "signup/form"` **render lại form trong cùng request**, không redirect.
6. Khi hợp lệ, chuyển sang trang thành công bằng `redirect:/signup/success` và một flash attribute.

Đoạn code không ghi database, không gửi email và không tạo tài khoản thật. Trong ứng dụng thực, chỉ được gọi service lưu dữ liệu **sau khi** `bindingResult.hasErrors()` là `false`, rồi xử lý lỗi nghiệp vụ, transaction và khả năng dữ liệu thay đổi đồng thời.

**Điều kiện kỹ thuật:** `@Controller` trả tên view; nếu thay bằng `@RestController`, chuỗi `"signup/form"` thường trở thành HTTP response body chứ không được ViewResolver dùng để tìm template.

## 10. Template Thymeleaf để hiển thị form và field errors

File `src/main/resources/templates/signup/form.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng ký</title>
</head>
<body>
<h1>Đăng ký</h1>

<form th:action="@{/signup}" th:object="${signup}" method="post">

    <label for="fullName">Họ và tên</label>
    <input type="text" th:field="*{fullName}">
    <p th:if="${#fields.hasErrors('fullName')}"
       th:errors="*{fullName}">Lỗi họ tên</p>

    <label for="email">Email</label>
    <input type="text" th:field="*{email}">
    <p th:if="${#fields.hasErrors('email')}"
       th:errors="*{email}">Lỗi email</p>

    <label for="age">Tuổi</label>
    <input type="text" th:field="*{age}">
    <p th:if="${#fields.hasErrors('age')}"
       th:errors="*{age}">Lỗi tuổi</p>

    <div th:if="${#fields.hasGlobalErrors()}">
        <p th:each="err : ${#fields.globalErrors()}"
           th:text="${err}">Lỗi chung</p>
    </div>

    <button type="submit">Gửi</button>
</form>

</body>
</html>
```

Trong Thymeleaf:

- `th:object="${signup}"` chọn form-backing bean trong model.
- `th:field="*{email}"` sinh các thuộc tính HTML `name`, `id`, value dựa trên model và binding state.
- `#fields.hasErrors('email')` kiểm tra lỗi của một field.
- `th:errors="*{email}"` dựng thông báo lỗi theo message được validator/binder cung cấp.
- `#fields.hasGlobalErrors()` và `#fields.globalErrors()` hỗ trợ lỗi toàn object.
- `th:field` thực hiện HTML escaping phù hợp khi hiển thị giá trị, tránh đưa raw HTML không tin cậy vào trang.

Input tuổi được dùng `type="text"` **có chủ ý** để có thể gửi `age=abc` và quan sát lỗi server-side type conversion. Trong form production có thể dùng `type="number"`, nhưng không được chỉ dựa vào kiểm tra ở browser vì HTTP client có thể gửi bất kỳ dữ liệu nào.

Spring MVC tự đưa thông tin BindingResult vào model khi render form theo luồng đúng. Không cần gọi `model.addAttribute("bindingResult", bindingResult)`; việc thêm thủ công dưới một key tùy ý cũng không bảo đảm template engine đọc được như form errors chuẩn.

## 11. Template thành công và xử lý redirect

File `src/main/resources/templates/signup/success.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng ký hợp lệ</title>
</head>
<body>
<h1>Đã nhận dữ liệu hợp lệ</h1>
<p th:if="${notice}" th:text="${notice}">Thông báo</p>
<a th:href="@{/signup}">Quay lại form</a>
</body>
</html>
```

Khi form hợp lệ, controller trả `redirect:/signup/success`. Trình duyệt nhận response chuyển hướng, thường **302 Found**, rồi thực hiện GET mới tới trang thành công. Flash attribute `notice` được chuyển tạm sang request đích.

Đây là mẫu **Post/Redirect/Get (PRG)**: sau POST thành công, reload không vô tình gửi lại form theo cơ chế trình duyệt bình thường.

**Ngược lại, nếu form có lỗi** nên trả lại view `signup/form` ngay trong request POST để giữ form object và BindingResult. Nếu redirect ngay khi có lỗi, bạn có thể làm mất rejected values và error messages trừ khi thiết kế truyền flash attributes rất cẩn thận.

Việc lỗi render lại form với HTTP **200 OK** là hành vi phổ biến của server-rendered MVC form; không đồng nghĩa API đã chấp nhận dữ liệu. Nếu hợp đồng yêu cầu 400/422 cho form HTML, phải thiết kế status có chủ đích thay vì chỉ kiểm tra `BindingResult`.

## 12. Chạy thử bằng Maven và curl

Khởi động tại thư mục gốc project có Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Mở form trong browser:

```text
http://localhost:8080/signup
```

POST hợp lệ:

```bash
curl -i -X POST http://localhost:8080/signup \
  --data-urlencode 'fullName=Lan Nguyen' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'age=25'
```

Trong project ví dụ, response thường là redirect:

```http
HTTP/1.1 302
Location: http://localhost:8080/signup/success
```

Dòng Location là minh họa; Spring có thể dùng URL tương đối/đầy đủ hoặc headers khác tùy môi trường. `curl -i` không tự follow redirect nếu không thêm `-L`.

POST có lỗi validation và conversion:

```bash
curl -i -X POST http://localhost:8080/signup \
  --data-urlencode 'fullName=A' \
  --data-urlencode 'email=not-an-email' \
  --data-urlencode 'age=abc'
```

Kết quả thường trả **200** với HTML trang form, hiển thị ít nhất các lỗi thuộc `fullName`, `email` và `age`. Không hứa hẹn body HTML byte-for-byte: message text có thể phụ thuộc Bean Validation provider, cấu hình MessageSource và escaping.

POST bị quy tắc riêng chặn:

```bash
curl -i -X POST http://localhost:8080/signup \
  --data-urlencode 'fullName=admin' \
  --data-urlencode 'email=admin@example.org' \
  --data-urlencode 'age=25'
```

`rejectValue("fullName", ...)` thêm lỗi mặc dù các annotation `@NotBlank`, `@Size`, `@Email`, `@Min` đều có thể hợp lệ.

Nếu project có Spring Security, POST form có thể cần CSRF token; các lệnh `curl` trên giả định **chưa thêm Spring Security starter**.

## 13. Phân biệt FieldError và ObjectError

`BindingResult.getFieldErrors()` trả các `FieldError`, thường có:

- `getField()`: tên field, như `age`.
- `getCode()` hoặc `getCodes()`: mã lỗi, như `typeMismatch`, `Min`, `NotBlank`.
- `getDefaultMessage()`: thông báo dùng để hiển thị/fallback.
- `getRejectedValue()`: giá trị bị từ chối khi có, có thể chứa dữ liệu cá nhân.
- `isBindingFailure()`: cho biết lỗi binding của field, giúp phân biệt với lỗi validation trong những tình huống phù hợp.

`BindingResult.getGlobalErrors()` trả các `ObjectError` không gắn với một field cụ thể, ví dụ tổ hợp ngày bắt đầu/kết thúc không hợp lệ.

Ví dụ chỉ ghi tên field và mã lỗi:

```java
for (var fieldError : bindingResult.getFieldErrors()) {
    String name = fieldError.getField();
    String code = fieldError.getCode();
    // Gửi name/code đến hệ thống log có kiểm soát nếu cần.
}
```

Đoạn code là fragment trong controller/service đã có tham chiếu `bindingResult`. Không dump toàn bộ object hay rejected values vào log production.

Để nhận biết lỗi:

```java
boolean invalid = bindingResult.hasErrors();
boolean ageInvalid = bindingResult.hasFieldErrors("age");
int count = bindingResult.getErrorCount();
```

Trong một form có lỗi `typeMismatch`, giá trị Java ở field đó có thể là `null`, nhưng `BindingResult` giữ thông tin lỗi và giá trị người dùng nhập để hỗ trợ hiển thị lại. Đừng chỉ nhìn `form.getAge()` rồi kết luận user đã không nhập gì.

## 14. rejectValue và reject: thêm lỗi nghiệp vụ tại Controller

Khi có một quy tắc không dễ biểu diễn bằng một Bean Validation annotation, controller hoặc validator riêng có thể thêm lỗi.

**Lỗi thuộc một field:**

```java
if ("admin".equalsIgnoreCase(form.getFullName())) {
    bindingResult.rejectValue(
        "fullName", "name.reserved",
        "Tên này không được sử dụng");
}
```

**Lỗi liên quan toàn bộ object:**

```java
if (form.getAge() != null
        && form.getEmail() != null
        && form.getEmail().endsWith("@example.org")
        && form.getAge() < 21) {
    bindingResult.reject(
        "signup.age.email",
        "Đăng ký bằng email ví dụ này yêu cầu đủ 21 tuổi");
}
```

Đoạn thứ hai chỉ là quy tắc demo, không phải yêu cầu tuổi thực tế của bất kỳ sản phẩm nào. Đó là **object error**, vì dựa trên kết hợp nhiều field. Với công việc thật, đưa business validation có tái sử dụng vào service/validator riêng để controller không phình to.

Sau khi bổ sung lỗi, phải kiểm tra `hasErrors()` lần nữa **trước khi gọi service hoặc redirect**. Nếu điều kiện nghiệp vụ phụ thuộc vào field đã có lỗi conversion, kiểm tra `hasFieldErrors(field)` và null-safety để tránh NPE hoặc kiểm tra dựa trên giá trị không hợp lệ.

## 15. Tự viết Validator và đăng ký bằng @InitBinder

Khi nhiều form có cùng một quy tắc, có thể tách sang `org.springframework.validation.Validator`:

```java
public final class SignupBusinessValidator
        implements org.springframework.validation.Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(
            Object target,
            org.springframework.validation.Errors errors) {
        SignupForm form = (SignupForm) target;
        if ("admin".equalsIgnoreCase(form.getFullName())) {
            errors.rejectValue(
                "fullName", "name.reserved",
                "Tên này không được sử dụng");
        }
    }
}
```

Đây là class minh họa có thể đặt trong `com.example.forms`. Nếu sử dụng validator này trong ứng dụng demo, cần **bỏ rule `admin` khỏi controller** để tránh bổ sung lỗi trùng.

Đăng ký trong controller:

```java
@InitBinder("signup")
public void configureBinder(WebDataBinder binder) {
    binder.addValidators(new SignupBusinessValidator());
}
```

Các import cần có là `org.springframework.web.bind.annotation.InitBinder` và `org.springframework.web.bind.WebDataBinder`. Code là fragment đặt trong `SignupController`. Validation binder khi xử lý `@Valid` sẽ kết hợp những validator đã đăng ký phù hợp; kiểm tra tương thích `supports` khi áp dụng cho nhiều object khác nhau.

**Không** dùng `binder.setValidator(...)` một cách tùy tiện nếu làm mất validator mặc định của Jakarta Bean Validation. Dùng `addValidators` khi mục tiêu là bổ sung, và kiểm thử rằng `@NotBlank`/`@Min` vẫn hoạt động.

## 16. hasErrors là điều kiện chuyển luồng, không phải một annotation

Một mẫu controller dễ bảo trì:

```text
POST form
   |
   v
Bind + Validate
   |
   v
Thêm domain validation nếu cần
   |
   v
bindingResult.hasErrors()?
    | YES                     | NO
    v                         v
Return form view           Gọi service
giữ lỗi + dữ liệu nhập     commit thành công?
    |                         |
    v                         v
Hiển thị field errors      Redirect theo PRG
```

Nếu controller cứ gọi service trước rồi mới kiểm tra lỗi, có thể lưu một object thiếu dữ liệu, gây NPE hoặc transaction rollback vô ích.

**Tuy nhiên `hasErrors() == false` không đảm bảo nghiệp vụ sẽ thành công**: database unique constraint có thể bị vi phạm do race condition, dịch vụ downstream có thể lỗi, tài khoản có thể hết quyền hoặc record đã thay đổi. Những lỗi này cần cơ chế service/transaction/exception handling độc lập.

Nên tách:

- **Input validation**: cấu trúc và constraint của form, dùng BindingResult.
- **Domain validation**: tính hợp lệ của dữ liệu theo mô hình nghiệp vụ.
- **Authorization**: ai có quyền thực hiện, không thể thay bằng validation.
- **Persistence errors**: unique constraint, transaction và retry/compensation.

## 17. Vì sao không nên redirect khi form có lỗi?

Khi `BindingResult.hasErrors()` là `true`:

```java
return "signup/form";
```

`BindingResult` và form object vẫn nằm trong request/model, Thymeleaf có thể dùng `th:field` và `th:errors` để hiển thị lại giá trị người dùng đã nhập cùng lỗi.

Nếu dùng:

```java
return "redirect:/signup";
```

Client tạo **request GET mới**, thông thường không còn form object và BindingResult của POST. Thông báo lỗi biến mất, form bị reset. Có thể truyền thông tin qua `RedirectAttributes` theo thiết kế riêng, nhưng làm đúng cho nhiều field errors và rejected values phức tạp hơn; một form HTML truyền thống thường nên return view trực tiếp khi invalid.

Ngược lại, **sau khi lưu thành công**, PRG hữu ích để tránh resubmit khi reload. Không coi `return "signup/form"` là redirect và không coi `redirect:/signup/success` là tên file template.

## 18. @Valid, @Validated, Bean Validation và method validation

`@Valid` thuộc `jakarta.validation.Valid`; `@Validated` thuộc `org.springframework.validation.annotation.Validated`. Với `@ModelAttribute` object, cả hai có thể kích hoạt validation khi có validator phù hợp. `@Validated` còn hỗ trợ **validation groups** trong Spring.

Ví dụ một class có constraints trên fields:

```java
public class SignupForm {
    @NotBlank
    private String fullName;
    // ...
}
```

Nếu controller không dùng `@Valid`/`@Validated` và không gọi validator chủ động, `@NotBlank` không tự chạy chỉ vì lớp có annotation. Tuy nhiên **lỗi binding/type conversion vẫn có thể xuất hiện**.

Spring Framework 6.1+ phân biệt hai nhánh exception quan trọng:

1. **Validation của từng `@ModelAttribute`, `@RequestBody` hoặc `@RequestPart` object:** khi không có `BindingResult` sát bên để xử lý tại chỗ, mặc định có thể phát sinh `MethodArgumentNotValidException`.
2. **Method validation:** khi các `@Constraint` được đặt trực tiếp trên method parameters hoặc return value, có thể phát sinh `HandlerMethodValidationException`. Method validation có các quy tắc phối hợp riêng với tham số `Errors/BindingResult`.

`@Valid` **không tự nó là một constraint annotation** làm method validation được kích hoạt; `@NotNull`, `@Min`, `@NotBlank` trực tiếp trên method parameters mới có thể dẫn đến method validation.

Đừng nhầm `BindingResult` với cơ chế bắt **mọi** lỗi validation trong controller. Nếu có lỗi ở một parameter khác **không** có `Errors` ngay sau, method validation có thể ném exception trước khi body controller chạy.

Nếu class controller dùng `@Validated` cấp class để áp method validation AOP, hãy kiểm tra tương tác với hỗ trợ method validation built-in của Spring Framework 6.1+; tài liệu Spring khuyến nghị bỏ class-level `@Validated` để tận dụng built-in MVC method validation mới.

## 19. So sánh form @ModelAttribute và JSON @RequestBody

Hai dạng input phổ biến:

| Nội dung | HTML form MVC | JSON REST API |
|---|---|---|
| Binding | `@ModelAttribute("signup") SignupForm` | `@RequestBody SignupDto` |
| Nguồn dữ liệu | Request parameters (form/query...) | JSON body qua `HttpMessageConverter` |
| Validation | `@Valid` hoặc `@Validated` | `@Valid` hoặc `@Validated` |
| BindingResult | Đặt ngay sau object để hiển thị lại form | Có thể đặt ngay sau body object để tự xử lý validation |
| Có lỗi | Thường trả lại view HTML, giữ model errors | Thường trả HTTP 400 với cấu trúc lỗi API |
| Thành công | Thường redirect theo PRG | Thường trả response body/status theo REST contract |

Ví dụ REST:

```java
@PostMapping("/api/signup")
public ResponseEntity<?> apiSignup(
        @Valid @RequestBody SignupDto dto,
        BindingResult result) {
    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(
            Map.of("error", "INVALID_SIGNUP"));
    }
    return ResponseEntity.ok().build();
}
```

Đây là **method minh họa**: `SignupDto` là DTO giả định, cần import `Map`, `ResponseEntity`, `@RequestBody`, `@PostMapping`, `@Valid` và `BindingResult`. Spring MVC cho phép local validation handling với `@RequestBody` và `Errors/BindingResult` đứng ngay sau object trong cấu hình phù hợp.

Với JSON **không parse được** (malformed JSON), lỗi `HttpMessageNotReadableException` có thể xảy ra **trước khi tạo object**; BindingResult không phải cơ chế bắt tất cả lỗi deserialize. Một API thường dùng `@RestControllerAdvice`/`ResponseEntityExceptionHandler` để chuẩn hóa errors như 400/415, thay vì redirect tới HTML form.

## 20. BindingResult trong Model và thông điệp lỗi quốc tế hóa

Spring MVC thường thêm vào model:

```text
signup -> SignupForm instance
org.springframework.validation.BindingResult.signup -> BindingResult instance
```

Key thứ hai sử dụng prefix `BindingResult.MODEL_KEY_PREFIX` cộng tên model attribute. Thymeleaf biết tìm binding state và `FieldError` dựa trên `th:object="${signup}"`.

Không thay tên `@ModelAttribute("signup")` trong controller thành `@ModelAttribute("user")` mà quên cập nhật template `th:object` và test.

Message codes có thể được xây theo nhiều mức đặc hiệu, ví dụ:

```text
NotBlank.signup.fullName
NotBlank.fullName
NotBlank.java.lang.String
NotBlank
```

`MessageCodesResolver` và `MessageSource` giúp ánh xạ mã lỗi thành thông báo địa phương hóa.

Ví dụ trong `src/main/resources/messages.properties`:

```properties
name.reserved.signup.fullName=Tên này không được dùng
typeMismatch.signup.age=Tuổi phải là số
```

Các message codes cần kiểm tra theo cấu hình thực tế của `MessageCodesResolver`; ví dụ trên minh họa các mã thường gặp, không cam kết thứ tự fallback trong mọi customization.

Có thể dùng `messages_vi.properties` và `messages_en.properties` cho nhiều locale. Không gắn nội dung validation message vào logic nghiệp vụ (ví dụ so sánh message string để quyết định nhánh), vì thông điệp có thể được dịch.

## 21. @InitBinder, allowed fields và mass assignment

`@ModelAttribute` cho Spring MVC bind request parameters vào object. Nếu dùng trực tiếp **entity** chứa trường nhạy cảm như `role`, `enabled`, `balance`, client có thể cố gửi thêm tên field để gán giá trị ngoài ý muốn.

**Ưu tiên:** tạo một DTO/form object chỉ gồm những field client được quyền nhập, như `SignupForm` với `fullName`, `email`, `age`. Sau đó map sang domain/entity trong service khi validation thành công.

Có thể bổ sung allowlist qua `@InitBinder`:

```java
@InitBinder("signup")
public void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("fullName", "email", "age");
}
```

Fragment này thuộc một `@Controller`, cần import `InitBinder` và `WebDataBinder`. Nếu client gửi field `role=ADMIN` nhưng binder chỉ cho ba field trên, `role` bị bỏ qua; có thể xem các trường bị suppress bằng `bindingResult.getSuppressedFields()`.

**Lưu ý:** việc field bị suppressed không nhất thiết tự tạo validation error. Nếu policy yêu cầu **từ chối** request chứa field bị cấm, phải kiểm tra và trả lỗi rõ. Không coi `allowedFields` là authentication/authorization; service vẫn phải xác minh quyền và kiểm soát dữ liệu nhạy cảm.

## 22. MockMvc: test form lỗi, type mismatch và nhánh thành công

Thêm `spring-boot-starter-test` vào project Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

File `src/test/java/com/example/forms/SignupControllerTest.java`:

```java
package com.example.forms;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void getFormReturnsView() throws Exception {
        mvc.perform(get("/signup"))
            .andExpect(status().isOk())
            .andExpect(view().name("signup/form"))
            .andExpect(model().attributeExists("signup"));
    }

    @Test
    void invalidFormKeepsViewAndErrors() throws Exception {
        mvc.perform(post("/signup")
                .param("fullName", "A")
                .param("email", "not-an-email")
                .param("age", "abc"))
            .andExpect(status().isOk())
            .andExpect(view().name("signup/form"))
            .andExpect(model().attributeHasFieldErrors(
                    "signup", "fullName", "email", "age"));
    }

    @Test
    void underAgeIsValidationError() throws Exception {
        mvc.perform(post("/signup")
                .param("fullName", "Lan Nguyen")
                .param("email", "lan@example.org")
                .param("age", "16"))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasFieldErrors(
                    "signup", "age"));
    }

    @Test
    void reservedNameIsRejected() throws Exception {
        mvc.perform(post("/signup")
                .param("fullName", "admin")
                .param("email", "admin@example.org")
                .param("age", "25"))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasFieldErrors(
                    "signup", "fullName"));
    }

    @Test
    void validFormRedirects() throws Exception {
        mvc.perform(post("/signup")
                .param("fullName", "Lan Nguyen")
                .param("email", "lan@example.org")
                .param("age", "25"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signup/success"))
            .andExpect(view().name("redirect:/signup/success"))
            .andExpect(flash().attribute(
                    "notice", "Dữ liệu đăng ký hợp lệ"));
    }
}
```

Trong project Maven có Maven Wrapper:

```bash
./mvnw test
```

Test dùng `MockMvc` để chạy handler MVC mà không mở socket HTTP thật. Các assertions chứng minh:

- GET form có model attribute.
- POST với dữ liệu sai **không redirect**, mà trả lại view cùng field errors.
- Type mismatch `age=abc` được ghi nhận trong BindingResult.
- Tuổi 16 là validation error, khác conversion error.
- Quy tắc `rejectValue` làm form có lỗi.
- Dữ liệu hợp lệ đi theo nhánh PRG và có flash message.

`MockMvc` test không thay thế integration test với browser cho CSS, accessibility, cookie, session hoặc CSRF khi thêm Spring Security.

## 23. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân phổ biến | Hướng xử lý |
|---|---|---|
| `BindingResult` không nhận được lỗi đúng | Không đứng ngay sau `@ModelAttribute` | Chuyển nó sát object được bind |
| `@NotBlank` không có tác dụng | Thiếu `@Valid` hoặc thiếu Bean Validation provider | Thêm annotation/dependency phù hợp |
| `hasErrors()` luôn false với trường `age=abc` | Controller không đi qua binding object như dự kiến, converter/handler bị thay đổi | Kiểm tra request content type, mapping và chữ ký method |
| Form chỉ hiện chữ `signup/form` | Dùng `@RestController` thay `@Controller` | Dùng MVC view controller phù hợp |
| Template không hiển thị lỗi | Sai `th:object` hoặc không dùng `th:errors`/`#fields` | Đối chiếu model attribute name và error bindings |
| Thông tin người dùng bị mất sau lỗi | Redirect khi invalid | Return cùng form view trong request |
| Đã có lỗi nhưng vẫn ghi database | Gọi service trước `hasErrors()` | Kiểm tra trước khi commit |
| Server trả 400 trước khi vào controller | Thiếu BindingResult, method validation, hoặc JSON deserialize lỗi | Phân loại exception thực tế |
| POST trả 403 với Spring Security | Thiếu CSRF token hoặc user không được phép | Cấu hình CSRF/login đúng, không tắt security để che lỗi |
| Có lỗi ở nhiều object nhưng chỉ đọc một | Chỉ một BindingResult hoặc sai thứ tự | Đặt từng BindingResult ngay sau object tương ứng |
| Lộ email/password trong log | Log `getRejectedValue()` hoặc toàn bộ request | Chỉ log mã lỗi/tên field an toàn |
| Client tự gán field `role` hoặc `enabled` | Bind thẳng entity/mass assignment | Dùng form DTO và allowlist |
| Mã lỗi bị hiển thị thô, chưa dịch | `MessageSource` hoặc message codes chưa cấu hình | Tạo messages bundle và test locale |
| Validation pass nhưng lưu dữ liệu vẫn fail | Unique constraint/race condition | Xử lý transaction và domain errors riêng |

## 24. Checklist trước khi hoàn tất Controller MVC có form

1. `@ModelAttribute` dùng một DTO chỉ chứa field client được phép sửa.
2. Có `@Valid`/`@Validated` nếu muốn tự động chạy constraint validation.
3. Dự án có Bean Validation provider, thường qua `spring-boot-starter-validation`.
4. `BindingResult` **ngay sau** object được bind, trước các tham số khác.
5. Controller gọi `hasErrors()` **trước** khi ghi dữ liệu hoặc phát side effects.
6. Error của riêng field dùng `rejectValue`, error toàn object dùng `reject`.
7. Khi lỗi, return form view trong cùng request để giữ form values và BindingResult.
8. Khi thành công, cân nhắc Post/Redirect/Get và flash attributes.
9. Template dùng `th:object`, `th:field`, `th:errors` với tên model attribute thống nhất.
10. Có test cho lỗi type conversion, Bean Validation, custom rejection và nhánh redirect.
11. Không nhầm validation của `@ModelAttribute` với lỗi JSON parse của `@RequestBody`.
12. Xử lý bảo mật: auth/CSRF, mass assignment, output escaping, secrets/logging.
13. Không dùng validation để thay thế kiểm tra quyền, unique constraints hoặc business rules tại service.
14. Khi áp method validation, xem xét `HandlerMethodValidationException` và quy tắc `BindingResult` đi kèm.

## 25. Kết luận

`BindingResult` là cầu nối giữa **Spring MVC data binding/validation** và **quyết định xử lý của Controller**. Một method có `@Valid @ModelAttribute("signup") SignupForm form, BindingResult result` có thể nhận lỗi tại chỗ; `result.hasErrors()` cho phép trả lại form để hiển thị lỗi thay vì ném exception hoặc xử lý dữ liệu chưa hợp lệ.

Hãy nhớ ba nguyên tắc:

- **Đặt đúng chỗ:** `BindingResult` phải đứng sát tham số đã bind/validate.
- **Rẽ nhánh đúng:** có lỗi thì render form, hợp lệ thì gọi nghiệp vụ và redirect khi thích hợp.
- **Kiểm soát đủ lớp:** validation không thay thế domain rules, security, transaction và xử lý lỗi downstream.

## 26. Tài liệu tham khảo chính thức

- Spring Framework 6.2 — `@ModelAttribute` và `BindingResult`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — Validation của MVC handler methods: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `@RequestBody` validation và local `Errors`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — `@InitBinder` và `WebDataBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework — MVC Validation Configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
- Spring Boot 3.5 — Jakarta Bean Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Framework — `BindingResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/BindingResult.html
- Thymeleaf 3.1 — Integration with Spring, form binding và validation errors: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
