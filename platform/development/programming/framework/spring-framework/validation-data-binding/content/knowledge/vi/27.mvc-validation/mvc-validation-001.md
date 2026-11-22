# @Valid hoặc @Validated trên @ModelAttribute trong Spring MVC

## Mục tiêu

`@ModelAttribute` biến dữ liệu từ HTML form, query parameters và những request values tương thích thành một Java object. Tuy nhiên **binding thành công không có nghĩa dữ liệu hợp lệ**: chuỗi `""` vẫn bind được vào `String`, email sai cú pháp vẫn là chuỗi, và tuổi `16` vẫn chuyển thành `Integer` được dù ứng dụng yêu cầu ít nhất 18 tuổi. Spring MVC có thể tự kiểm tra object đã bind bằng `@Valid` hoặc `@Validated`, rồi đưa lỗi vào `BindingResult`.

Bài học thuộc phần **Validation trong MVC** và tập trung vào annotation **trên tham số `@ModelAttribute` của controller**. Bạn sẽ:

- Phân biệt `jakarta.validation.Valid` với `org.springframework.validation.annotation.Validated`, nhất là validation groups.
- Hiểu trình tự data binding, type conversion, Bean Validation, `BindingResult` và render lại view.
- Dùng đúng `@Valid @ModelAttribute("registrationForm")` hoặc `@Validated(...) @ModelAttribute(...)`.
- Viết một ví dụ Java 17+/Spring Boot 3 với hai hành động *Lưu nháp* và *Gửi cuối*; kiểm thử bằng MockMvc.
- Xác định khi nào nhận `MethodArgumentNotValidException` hoặc `HandlerMethodValidationException` thay vì tự xử lý lỗi.
- Giải quyết lỗi thường gặp liên quan form lồng nhau, giá trị bị từ chối, group mặc định, template, security và Spring AOP.

## 1. Cơ chế từ request đến BindingResult

Ví dụ trình duyệt gửi:

~~~http
POST /register/draft
Content-Type: application/x-www-form-urlencoded

fullName=Lan&email=lan@example.com&age=21&address.city=Ha+Noi
~~~

Controller nhận:

~~~java
@PostMapping("/register/draft")
String save(
        @ModelAttribute("registrationForm") RegistrationForm form) {
    // Xử lý form đã được bind
    return "registration";
}
~~~

`@ModelAttribute` chỉ rõ rằng handler cần một object tên `registrationForm`. Spring tìm object đã có trong model hoặc tạo object mới bằng cơ chế phù hợp, dùng `WebDataBinder` để chuyển và gán request values cho constructor arguments/properties. Ví dụ `"21"` chuyển thành `Integer.valueOf(21)` nếu property `age` là `Integer`.

Khi có `@Valid` hoặc `@Validated`, Spring yêu cầu validator kiểm tra các ràng buộc đã khai báo trên object sau bước binding. Cả lỗi binding lẫn validation đều có thể được ghi vào `BindingResult`.

~~~text
HTTP form / query / path variables / compatible headers
                         |
                         v
             @ModelAttribute("registrationForm")
                         |
                         v
           Tạo hoặc lấy RegistrationForm
                         |
                         v
     WebDataBinder + ConversionService / Formatter
                         |
          +--------------+---------------+
          |                              |
    Chuyển kiểu được                 Chuyển kiểu lỗi
    Gán vào object                  FieldError typeMismatch
          |                              |
          +--------------+---------------+
                         |
                         v
        @Valid / @Validated → Validator
        Đọc @NotBlank, @Email, @Min, @Valid...
                         |
                         v
           BindingResult: lỗi binding + validation
                         |
             +-----------+-----------+
             |                       |
         Có lỗi                   Không lỗi
         return view               thực hiện nghiệp vụ
         và hiện lại form          / redirect
~~~

`@ModelAttribute` **không tự định nghĩa constraint**. Nếu DTO không có annotation kiểm tra, custom `Validator`, hoặc provider Bean Validation phù hợp, `@Valid` không tự nghĩ ra các quy tắc nghiệp vụ.

Trong Spring Boot 3, `spring-boot-starter-validation` thường cung cấp Jakarta Validation provider (như Hibernate Validator) cho cách viết `jakarta.validation.*`. Không trộn `javax.validation.*` của hệ sinh thái cũ vào Spring Framework 6/Spring Boot 3.

## 2. @Valid so với @Validated

| Vấn đề | `@Valid` | `@Validated` |
| --- | --- | --- |
| Package | `jakarta.validation.Valid` | `org.springframework.validation.annotation.Validated` |
| Mục đích trên `@ModelAttribute` | Kích hoạt Bean Validation cho object | Kích hoạt validation và có thể chọn groups |
| Khi không chọn group khác | Kiểm tra nhóm `Default` | Kiểm tra nhóm `Default` trong cấu hình thường gặp |
| Chọn group tại điểm sử dụng | Không có thuộc tính group | `@Validated(Group.class)` hoặc `@Validated({A.class,B.class})` |
| Cascade vào object con | `@Valid` trên cạnh tham chiếu | Root được validate; các cạnh con vẫn cần `@Valid` |
| Dùng trong Jakarta Validation thuần | Có | Không, thuộc Spring |
| Trên class Spring bean | Không phải marker AOP method validation | Có thể dùng cho cơ chế method validation qua Spring AOP |

**Chọn `@Valid`** khi cùng một form có các quy tắc cố định thuộc group mặc định. **Chọn `@Validated(...)`** khi trạng thái thao tác quyết định constraint nào cần chạy: tạo bản nháp, gửi cuối, duyệt của quản lý hoặc cập nhật hồ sơ.

Ví dụ:

~~~java
@PostMapping("/draft")
String draft(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form,
        BindingResult errors) {
    // ...
}

@PostMapping("/final")
String finalSubmit(
        @Validated({Default.class, FinalSubmit.class})
        @ModelAttribute("registrationForm")
        RegistrationForm form,
        BindingResult errors) {
    // ...
}
~~~

Đây là **snippet chữ ký**, chưa phải controller độc lập; `Default` thuộc `jakarta.validation.groups.Default` còn `FinalSubmit` là marker interface do ứng dụng định nghĩa.

Không cần gắn đồng thời `@Valid` và `@Validated` lên cùng một đối số để “chắc ăn”. Thay vào đó hãy chọn annotation phản ánh rõ group mong muốn. `@Validated` là biến thể mở rộng tiện lợi của Spring; nó không làm Bean Validation tự đi sâu vào mọi object nếu thiếu marker cascade trên DTO.

### Khi chỉ chọn một custom group

Với DTO:

~~~java
@NotBlank
private String fullName; // nhóm Default

@NotBlank(groups = FinalSubmit.class)
private String inviteCode; // nhóm FinalSubmit
~~~

`@Validated(FinalSubmit.class)` thông thường chỉ chạy constraints thuộc `FinalSubmit`, vì vậy `fullName` thuộc `Default` có thể bị bỏ qua. Nếu nghiệp vụ muốn cả tên và mã hợp lệ khi gửi cuối, viết:

~~~java
@Validated({Default.class, FinalSubmit.class})
~~~

Việc liệt kê nhiều group **không có nghĩa** các group được kiểm tra theo thứ tự liệt kê. Muốn thực sự tạo thứ tự nhóm và điều kiện dừng, tìm hiểu `@GroupSequence`; đừng phụ thuộc vào iteration order của error collections.

## 3. BindingResult đứng ngay sau tham số được validate

Đây là mẫu controller cần ghi nhớ:

~~~java
@PostMapping("/register")
public String submit(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration";
    }

    return "redirect:/register/success";
}
~~~

`BindingResult` hoặc `Errors` phải **đứng ngay sau** tham số `@ModelAttribute` tương ứng. Spring MVC gắn lỗi cho chính object vừa bind/validate. Chèn một tham số `Model` hoặc `HttpServletRequest` vào giữa là sai:

~~~java
@PostMapping("/register")
String wrong(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form,
        Model model,
        BindingResult errors) {
    return "registration";
}
~~~

Đoạn `wrong` chỉ là **anti-pattern**, không được đưa vào controller chạy thật.

`BindingResult` có các API:

~~~java
boolean invalid = errors.hasErrors();
int count = errors.getErrorCount();
FieldError field = errors.getFieldError("age");
java.util.List<FieldError> ageErrors =
        errors.getFieldErrors("age");
java.util.List<ObjectError> global =
        errors.getGlobalErrors();
Object fieldDisplayValue = errors.getFieldValue("age");
~~~

Đây là đoạn minh họa khi biến `errors` đã tồn tại.

- `FieldError` mô tả lỗi trên một property như `age`, `email` hoặc `address.city`.
- `ObjectError` mô tả lỗi toàn object, có thể từ class-level constraint hoặc custom validator so sánh nhiều field.
- `getRejectedValue()` giữ giá trị bị lỗi (có thể là chuỗi đầu vào hoặc object đã chuyển kiểu).
- `isBindingFailure()` cho biết lỗi ở bước binding/chuyển kiểu hay ở bước validation.
- `getCodes()` cung cấp dãy mã để tra trong message bundles; `getDefaultMessage()` cho text mặc định.
- `getFieldValue("age")` hữu ích cho view vì khi conversion thất bại, nó có thể trả chuỗi bị từ chối ngay cả khi Java property đang null.

Hai dạng lỗi khác nhau:

| HTTP input | Java property | Kết quả |
| --- | --- | --- |
| `age=21` | `Integer age` + `@Min(18)` | Convert thành 21, hợp lệ |
| `age=16` | `Integer age` + `@Min(18)` | Convert thành 16, lỗi constraint `Min` |
| `age=abc` | `Integer age` + `@Min(18)` | Conversion thất bại, lỗi binding `typeMismatch` |
| `email=khong-phai-email` | `String email` + `@Email` | Bind thành công, lỗi validation `Email` |
| `address.city=` | Field lồng có `@NotBlank` | Lỗi field `address.city` khi cascade `@Valid` được khai báo |

Một field có thể có **nhiều** error, vì vậy đừng luôn giả định `getFieldError("age")` là lỗi duy nhất. Khi cần chọn lỗi conversion, tìm `FieldError::isBindingFailure`.

## 4. Ví dụ hoàn chỉnh: hai nhóm validation trong một form

Ứng dụng minh họa dùng Java 17+, Spring Boot 3.5.7, Spring MVC, Thymeleaf, Bean Validation và MockMvc. Người dùng nhập họ tên, email, tuổi, thành phố và mã xác nhận. Lưu nháp áp dụng `Default`; gửi cuối áp dụng `Default` và `FinalSubmit`.

Cấu trúc dự án:

~~~text
mvc-registration/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/registration/
    │   │   ├── RegistrationApplication.java
    │   │   ├── FinalSubmit.java
    │   │   ├── RegistrationForm.java
    │   │   └── RegistrationController.java
    │   └── resources/
    │       ├── templates/registration.html
    │       └── application.properties
    └── test/
        └── java/com/example/registration/
            └── RegistrationControllerTest.java
~~~

### 4.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-registration</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

`spring-boot-starter-validation` là dependency cần thiết trong ứng dụng Spring Boot 3 thông thường để có Jakarta Validation provider. Spring Boot parent quản lý version các dependency; trong dự án thật hãy chọn version theo chính sách hỗ trợ và cập nhật bảo mật của tổ chức.

### 4.2. RegistrationApplication.java

~~~java
package com.example.registration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegistrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegistrationApplication.class, args);
    }
}
~~~

### 4.3. FinalSubmit.java — nhóm kiểm tra

~~~java
package com.example.registration;

public interface FinalSubmit {
}
~~~

Đây là một marker interface dùng như type-safe group; bản thân interface không chứa logic hay trạng thái.

### 4.4. RegistrationForm.java — DTO và nested validation

~~~java
package com.example.registration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {

    @NotBlank
    private String fullName;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    @NotBlank(groups = FinalSubmit.class)
    private String inviteCode;

    @Valid
    private AddressForm address = new AddressForm();

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

    public String getInviteCode() {
        return inviteCode;
    }

    public void setInviteCode(String inviteCode) {
        this.inviteCode = inviteCode;
    }

    public AddressForm getAddress() {
        return address;
    }

    public void setAddress(AddressForm address) {
        this.address = address;
    }

    public static class AddressForm {
        @NotBlank
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }
}
~~~

Giải thích:

- `fullName`, `email`, `age` là constraints mặc định. `@Email` cần kết hợp `@NotBlank` vì việc kiểm tra định dạng thường cho qua `null`.
- `inviteCode` chỉ có `@NotBlank(groups=FinalSubmit.class)`; lưu nháp không bắt buộc có mã.
- `@Valid` trên `address` đánh dấu cạnh cascade. Nếu bỏ nó, việc validate `RegistrationForm` không đi sâu vào `AddressForm.city`.
- `AddressForm` có getters/setters và object mặc định để property binding có thể xử lý input `address.city`.
- `@Valid` không có nghĩa `address` bắt buộc khác null. Khi cần điều đó, đặt thêm `@NotNull` trên quan hệ.
- `Integer age` giúp nhìn thấy lỗi chuyển kiểu từ chuỗi `abc`; sử dụng `int` sẽ không biểu đạt được cùng trạng thái null khi thiếu input.

### 4.5. RegistrationController.java

~~~java
package com.example.registration;

import jakarta.validation.Valid;
import jakarta.validation.groups.Default;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
@RequestMapping("/register")
public class RegistrationController {

    @InitBinder("registrationForm")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "fullName", "email", "age",
                "inviteCode", "address.city");
    }

    @GetMapping
    public String show(Model model) {
        model.addAttribute(
                "registrationForm", new RegistrationForm());
        return "registration";
    }

    @PostMapping("/draft")
    public String saveDraft(
            @Valid @ModelAttribute("registrationForm")
            RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "registration";
        }
        return "redirect:/register/success";
    }

    @PostMapping("/final")
    public String finalSubmit(
            @Validated({Default.class, FinalSubmit.class})
            @ModelAttribute("registrationForm")
            RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "registration";
        }
        return "redirect:/register/success";
    }

    @GetMapping("/success")
    @ResponseBody
    public String success() {
        return "Accepted";
    }
}
~~~

Ở `saveDraft`, `@Valid` áp dụng Default constraints (kể cả nested `address.city`). Ở `finalSubmit`, `@Validated({Default.class, FinalSubmit.class})` kiểm tra thêm `inviteCode`. `BindingResult` đặt sát form argument trong cả hai method.

`@InitBinder` giới hạn property được phép bind, giúp tránh HTTP request ghi vào field không dự kiến (mass assignment). Nó là cơ chế bảo vệ boundary, **khác validation**; không dùng `@NotBlank` thay cho kiểm soát property được phép sửa.

Các handler không ghi database: đây là demo validation nên chỉ redirect đến endpoint thành công. Nếu ứng dụng thực sự lưu hồ sơ, phải gọi service sau `errors.hasErrors() == false` và vẫn xác minh quyền truy cập/domain invariants tại service.

### 4.6. templates/registration.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đăng ký</title>
  <style>
    .error { color: #b00020; }
    .invalid { border: 1px solid #b00020; }
  </style>
</head>
<body>
<h1>Đăng ký</h1>

<form th:action="@{/register/draft}"
      th:object="${registrationForm}"
      method="post">

  <label>Họ tên
    <input type="text"
           th:field="*{fullName}"
           th:errorclass="invalid">
  </label>
  <p class="error"
     th:if="${#fields.hasErrors('fullName')}"
     th:errors="*{fullName}"></p>

  <label>Email
    <input type="text"
           th:field="*{email}"
           th:errorclass="invalid">
  </label>
  <p class="error"
     th:if="${#fields.hasErrors('email')}"
     th:errors="*{email}"></p>

  <label>Tuổi
    <input type="text"
           inputmode="numeric"
           th:field="*{age}"
           th:errorclass="invalid">
  </label>
  <p class="error"
     th:if="${#fields.hasErrors('age')}"
     th:errors="*{age}"></p>

  <label>Thành phố
    <input type="text"
           th:field="*{address.city}"
           th:errorclass="invalid">
  </label>
  <p class="error"
     th:if="${#fields.hasErrors('address.city')}"
     th:errors="*{address.city}"></p>

  <label>Mã xác nhận (chỉ bắt buộc khi gửi cuối)
    <input type="text"
           th:field="*{inviteCode}"
           th:errorclass="invalid">
  </label>
  <p class="error"
     th:if="${#fields.hasErrors('inviteCode')}"
     th:errors="*{inviteCode}"></p>

  <button type="submit">Lưu nháp</button>
  <button type="submit"
          th:formaction="@{/register/final}">Gửi cuối</button>
</form>
</body>
</html>
~~~

Nhờ `th:object="${registrationForm}"` và `th:field="*{...}"`, Thymeleaf đọc Spring binding status, lấy giá trị đã bind **hoặc rejected value nếu có lỗi**. `th:errors` render thông báo bên cạnh field. Đường dẫn nested `address.city` phải nhất quán với Java property và input name.

Hai nút có hai URL: nút mặc định gửi `/register/draft`, nút cuối dùng `formaction` gửi `/register/final`. Vì hai handler chọn nhóm khác nhau nên một mã xác nhận trống có thể hợp lệ ở nháp nhưng sai ở bước cuối.

`type="text" inputmode="numeric"` cho `age` giúp giữ được chuỗi `abc` khi mô phỏng lỗi conversion. Browser có thể tự từ chối/chuẩn hóa giá trị không phải số trong `<input type="number">`, nên HTML control cần được chọn theo UX và kiểm thử thực tế.

### 4.7. application.properties và chạy thử

~~~properties
server.port=8080
spring.thymeleaf.cache=false
~~~

Tắt template cache chỉ dành cho môi trường học/dev. Chạy:

~~~bash
mvn spring-boot:run
~~~

Mở `http://localhost:8080/register`, điền `fullName=Lan`, `email=lan@example.com`, `age=21`, `address.city=Ha Noi`, để trống `inviteCode`.

- Nhấn **Lưu nháp**: Default constraints hợp lệ; `inviteCode` không thuộc Default, nên phản hồi là redirect HTTP **302** đến `/register/success`.
- Nhấn **Gửi cuối**: group `FinalSubmit` được chọn; `inviteCode` trống có `FieldError`. Controller trả view `registration` trong cùng request (mẫu này thường là HTTP **200**) và hiển thị lại input.
- Nhập `inviteCode=ABC123` rồi gửi cuối: mọi constraint demo hợp lệ, chuyển sang redirect HTTP **302**.
- Thử `age=abc`: conversion sang `Integer` thất bại, `BindingResult` chứa lỗi `typeMismatch` và có thể giữ lại chuỗi `"abc"` cho template.

Log khởi động Spring Boot không có stdout cố định giữa các máy; không suy diễn log phải trùng một mẫu duy nhất. Bằng chứng cho bài này là **HTTP behavior và assertions của MockMvc** dưới đây.

## 5. MockMvc kiểm thử validation và groups

File `src/test/java/com/example/registration/RegistrationControllerTest.java`:

~~~java
package com.example.registration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.servlet.ModelAndView;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getPageCreatesForm() throws Exception {
        mvc.perform(get("/register"))
                .andExpect(status().isOk())
                .andExpect(view().name("registration"))
                .andExpect(model().attributeExists(
                        "registrationForm"));
    }

    @Test
    void draftDoesNotRequireInviteCode() throws Exception {
        mvc.perform(post("/register/draft")
                        .param("fullName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "21")
                        .param("address.city", "Ha Noi"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl(
                        "/register/success"));
    }

    @Test
    void finalRequiresInviteCode() throws Exception {
        var response = mvc.perform(post("/register/final")
                        .param("fullName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "21")
                        .param("address.city", "Ha Noi"))
                .andExpect(status().isOk())
                .andExpect(view().name("registration"))
                .andExpect(model().attributeHasFieldErrors(
                        "registrationForm", "inviteCode"))
                .andReturn();

        ModelAndView mav = response.getModelAndView();
        assertNotNull(mav);

        BindingResult result = (BindingResult)
                mav.getModel().get(
                        BindingResult.MODEL_KEY_PREFIX
                        + "registrationForm");

        assertNotNull(result);
        FieldError error = result.getFieldError("inviteCode");
        assertNotNull(error);
        assertEquals("NotBlank", error.getCode());
        assertFalse(error.isBindingFailure());
    }

    @Test
    void finalAcceptsCompleteForm() throws Exception {
        mvc.perform(post("/register/final")
                        .param("fullName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "21")
                        .param("address.city", "Ha Noi")
                        .param("inviteCode", "ABC123"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl(
                        "/register/success"));
    }

    @Test
    void nestedCityConstraintIsChecked() throws Exception {
        mvc.perform(post("/register/draft")
                        .param("fullName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "21")
                        .param("address.city", ""))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "registrationForm", "address.city"));
    }

    @Test
    void failedAgeConversionKeepsRejectedText()
            throws Exception {

        var response = mvc.perform(post("/register/draft")
                        .param("fullName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "abc")
                        .param("address.city", "Ha Noi"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "registrationForm", "age"))
                .andReturn();

        ModelAndView mav = response.getModelAndView();
        assertNotNull(mav);

        BindingResult result = (BindingResult)
                mav.getModel().get(
                        BindingResult.MODEL_KEY_PREFIX
                        + "registrationForm");
        assertNotNull(result);

        FieldError mismatch = result.getFieldErrors("age")
                .stream()
                .filter(FieldError::isBindingFailure)
                .findFirst()
                .orElseThrow();

        assertEquals("abc", mismatch.getRejectedValue());
        assertEquals("abc", result.getFieldValue("age"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Sáu test tách bạch: (1) form khởi tạo; (2) `@Valid` chỉ chạy Default; (3) `@Validated` kết hợp Default + FinalSubmit; (4) gửi cuối hợp lệ; (5) `@Valid` ở nested field; (6) type mismatch và rejected value. Các assertions không phụ thuộc thứ tự `Set<ConstraintViolation>`.

Các test này yêu cầu một Spring test context có MVC, Thymeleaf và Jakarta provider. Nếu ứng dụng thêm Spring Security, cần thêm CSRF token vào các POST test theo security configuration thực tế, nếu không có thể gặp HTTP 403 **trước** khi controller validation chạy.

## 6. Không có BindingResult: MethodArgumentNotValidException

Hai cách ký handler:

~~~java
// A. Có BindingResult: handler tự render lỗi
@PostMapping("/save")
String save(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form,
        BindingResult errors) {
    return errors.hasErrors()
            ? "registration"
            : "redirect:/register/success";
}
~~~

~~~java
// B. Không có BindingResult: framework báo lỗi
@PostMapping("/save")
String save(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form) {
    return "redirect:/register/success";
}
~~~

Đây là **hai snippet so sánh, không copy cùng lúc** vì URL trùng nhau.

Khi một command object `@ModelAttribute` được validate riêng và không có `BindingResult` phù hợp, Spring MVC thường ném `MethodArgumentNotValidException` nếu binding hoặc validation lỗi (xử lý mặc định thường HTTP 400). Handler B không được chạy tới dòng redirect.

Nếu controller có constraint trực tiếp trên method parameter khác, ví dụ:

~~~java
@PostMapping("/check")
String check(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form,
        @RequestParam @Min(1) int count) {
    return "ok";
}
~~~

Đây là snippet minh họa cần thêm import `@RequestParam`, `@Min`. Từ Spring Framework **6.1**, direct constraint như `@Min` có thể kích hoạt native **method validation** trong Spring MVC, bao gồm cả nested constraints trên `@Valid`. Khi method validation gặp lỗi không được xử lý bằng `Errors`/`BindingResult` phù hợp, nó thường ném `HandlerMethodValidationException`.

**Lưu ý:** `@Valid` tự nó **không phải direct constraint** nên không tự kích hoạt method validation của toàn chữ ký. Thêm `@NotNull` trực tiếp vào một method argument có thể thay đổi đường validation/exception. Spring MVC method validation vẫn có thể phối hợp `BindingResult`: controller chỉ được gọi nếu các lỗi đều thuộc những arguments có `Errors` tương ứng ngay sau chúng.

Nếu controller có **class-level `@Validated`**, Spring AOP method validation có thể chạy qua proxy. Muốn dùng native controller method validation của Spring 6.1+, tài liệu Spring khuyến nghị bỏ class-level `@Validated` khi phù hợp. `@Validated` **trên chính form parameter** để chọn groups là use case riêng, không cần `MethodValidationPostProcessor` để hoạt động.

## 7. @ModelAttribute và @RequestBody không đồng nghĩa

| Điểm | `@ModelAttribute` | `@RequestBody` |
| --- | --- | --- |
| Nguồn dữ liệu | HTML form, query, request values tương thích | HTTP body qua message converter, thường JSON |
| Data conversion | `WebDataBinder`/`ConversionService` cho property/constructor | `HttpMessageConverter` deserialization |
| Validation | `@Valid` hoặc `@Validated` trên argument | Cũng có `@Valid` hoặc `@Validated` |
| Lỗi bind | `BindingResult`/field errors hoặc exception | Có thể là parse/converter exception trước validation |
| UI thông thường | Server-rendered HTML view | REST JSON response/frontend xử lý |
| Ví dụ | `POST application/x-www-form-urlencoded` | `POST application/json` |

Không gắn `@RequestBody` chỉ vì muốn dùng `@Valid`; cả hai annotation đều hỗ trợ validation. Trọng tâm là **cách nhận dữ liệu** và media type. `@ModelAttribute` trên argument có thể được suy ra khi không ghi annotation với những kiểu object không được resolver khác xử lý, nhưng khai báo tường minh rõ ràng hơn, nhất là với native-image/AOT inference.

## 8. Nested objects, groups và các trường hợp khó

### 8.1. Null và các constraint khác nhau

`@Valid` trên cạnh object **không yêu cầu object phải tồn tại**. Nếu `address == null`, cascaded validation bỏ qua nhánh đó. Muốn bắt buộc có địa chỉ:

~~~java
@NotNull
@Valid
private AddressForm address;
~~~

`@Email` kiểm tra cú pháp email, còn `@NotBlank` kiểm tra hiện diện/nonblank. `@Min(18)` kiểm tra số sau khi chuyển kiểu thành công; `@NotNull` cấm thiếu tuổi. Mỗi constraint giải quyết một yêu cầu khác nhau, không nên trộn.

### 8.2. Collection và container element

Form có một tập người nhận có thể khai báo:

~~~java
private java.util.List<@Valid RecipientForm> recipients;
~~~

Với `RecipientForm` có `@NotBlank String name`, Jakarta Validation có thể kiểm tra từng phần tử khi được bind và có value extraction phù hợp. Nested path có thể là `recipients[0].name`. Nếu một phần tử trong danh sách là null, `@Valid` đơn lẻ bỏ qua null; thêm `@NotNull` ở type argument khi cần.

Ở form thực tế, cần xác định số lượng item và giới hạn index/auto-grow để tránh input tạo cấu trúc quá lớn. Đây là vấn đề data binding/security, không phải riêng Bean Validation.

### 8.3. Group conversion

Một cạnh cascade có thể dùng `@ConvertGroup`:

~~~java
@Valid
@ConvertGroup(
        from = Default.class,
        to = DetailedChecks.class)
private AddressForm address;
~~~

Snippet này cần import `jakarta.validation.groups.ConvertGroup`, `Default` và interface `DetailedChecks`. Conversion có nghĩa **khi đang validate group Default ở cạnh này**, child được kiểm tra theo group DetailedChecks; không phải “kiểm tra tất cả”. Phải hiểu rõ lý do áp dụng group conversion, tránh cấu hình chồng chéo khó dự đoán.

### 8.4. Custom Spring Validator

Bên cạnh Jakarta Bean Validation, Spring MVC cho phép gắn `org.springframework.validation.Validator` qua `@InitBinder`:

~~~java
@InitBinder("registrationForm")
void attach(WebDataBinder binder) {
    binder.addValidators(myValidator);
}
~~~

Đây là snippet cần biến `myValidator` đã được cung cấp qua dependency injection; không biên dịch độc lập. Custom validator có thể ghi lỗi vào `Errors.rejectValue(...)`, xuất hiện chung trong `BindingResult`. Nếu dùng `@Validated` với groups, hãy bảo đảm custom Spring validator hiểu validation hints/group hoặc chủ động tách trách nhiệm; không mặc định mọi Spring `Validator` đều diễn giải Jakarta groups giống nhau.

## 9. Hiển thị lại form, messages và bảo mật

Để render lại form sau lỗi:

~~~java
if (errors.hasErrors()) {
    return "registration";
}
~~~

Không thay object hiện tại bằng `new RegistrationForm()` khi có lỗi; không redirect sang GET mà không mang theo dữ liệu và `BindingResult`. Mẫu thường dùng là **return cùng view khi lỗi, redirect sau thành công** (Post/Redirect/Get thành công).

Thymeleaf Spring integration dùng `th:object`, `th:field` và `th:errors` để hiện lại cả rejected value lẫn messages. Với field age không chuyển được `"abc"` thành Integer, `RegistrationForm.getAge()` có thể là null nhưng `BindingResult.getFieldValue("age")` có thể trả lại `"abc"`.

Spring giải mã message qua `FieldError.getCodes()`, kết hợp `MessageSource` và locale. Có thể đặt `src/main/resources/messages.properties`:

~~~properties
NotBlank.registrationForm.fullName=Họ tên không được để trống
NotBlank.registrationForm.inviteCode=Cần mã xác nhận khi gửi cuối
Email.registrationForm.email=Email không hợp lệ
Min.registrationForm.age=Tuổi chưa đủ điều kiện
typeMismatch.registrationForm.age=Tuổi phải là số nguyên
~~~

Các mã trên là quy ước thường gặp với object name/field tương ứng; nếu project đổi `MessageCodesResolver` hoặc tên object, kiểm tra `FieldError.getCodes()` thực tế. Với đa ngôn ngữ, dùng các bundle theo locale như `messages_vi.properties` và `messages_en.properties`.

Bảo vệ dữ liệu:

- Chỉ bind request vào **form DTO** chứa những property được phép nhận; khi property binding được dùng, cân nhắc `setAllowedFields(...)`.
- Validation không thay thế authorization, CSRF protection hoặc domain checks trong service.
- Không hiển thị lại password/token/OTP chỉ vì muốn “giữ form”, không log nguyên `getRejectedValue()` nếu có thông tin nhạy cảm.
- Escape output theo HTML context (ví dụ `th:text`/`th:field`), không dùng `th:utext` với dữ liệu chưa tin cậy.
- Khi response là JSON API thay vì HTML view, thiết kế error schema ổn định, tránh xuất toàn bộ exception/target object.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gắn `@Valid` nhưng không có lỗi | Chưa có Jakarta provider, constraints không có/không phù hợp | Kiểm tra dependency, annotation và trigger |
| Form nháp bị buộc nhập mã cuối | Handler draft đã chọn `FinalSubmit` | Chỉ dùng Default ở nhánh draft |
| Gửi cuối bỏ sót `fullName` | Chỉ dùng `@Validated(FinalSubmit.class)` | Chọn thêm `Default.class` |
| `address.city` sai nhưng vẫn cho qua | Thiếu `@Valid` trên `address` | Thêm cascade marker đúng cạnh |
| Handler không nhận lỗi | `BindingResult` không sát object | Sửa thứ tự parameters |
| Đầu vào `age=abc` trở thành null | Conversion lỗi | Render dựa vào binding status/rejected value |
| Sau lỗi form trở về trống | Redirect hoặc tạo object mới | Return cùng view, giữ model và BindingResult |
| Dùng `@Valid` và `@Validated` cùng tham số | Không có thiết kế group rõ ràng | Dùng một annotation phản ánh nhóm cần chạy |
| Controller ném exception khác dự kiến | Có direct method constraint hoặc class-level AOP | Kiểm tra `MethodArgumentNotValidException` và `HandlerMethodValidationException` |
| Không đúng tên field | HTML input name khác property | Dùng `th:field` và mapping đúng |
| Đăng ký được cập nhật field quản trị | Bind entity trực tiếp hoặc thiếu whitelist | Form DTO và allowed fields |
| Dữ liệu sai bị xử lý tiếp | Không kiểm tra `errors.hasErrors()` hoặc swallow exception | Chặn nghiệp vụ khi lỗi |
| Messages không được dịch | Message bundle/codes/locale chưa khớp | Kiểm tra `getCodes()` và cấu hình `MessageSource` |

## 11. Câu hỏi tự kiểm tra

**1.** Tại sao `@ModelAttribute` không đủ để bảo đảm email hợp lệ?  
Vì nó bind dữ liệu; muốn kiểm tra nội dung phải khai báo `@Email` và kích hoạt validation.

**2.** Khi nào nên dùng `@Validated` thay `@Valid`?  
Khi cần chỉ rõ validation groups khác nhau tại điểm nhận object; ví dụ lưu nháp với Default và gửi cuối với Default + FinalSubmit.

**3.** Vì sao `@Validated(FinalSubmit.class)` có thể bỏ qua `@NotBlank` trên `fullName`?  
Vì constraint không khai báo group riêng thuộc `Default`, nhóm này không tự được thêm vào danh sách custom groups.

**4.** `BindingResult` nằm ở đâu?  
Ngay sau tham số `@ModelAttribute` cần nhận kết quả binding/validation trong handler signature.

**5.** Nếu `age=abc`, `getAge()` có thể null trong khi form vẫn hiển thị `abc` bằng cách nào?  
Vì `BindingResult` giữ rejected value, còn Thymeleaf `th:field` lấy binding status.

**6.** Thêm `@Valid` trên handler argument có tự kích hoạt native method validation không?  
Không; nó là marker kích hoạt bean validation/cascade cho argument. Direct constraint trên method parameter có thể khiến Spring MVC dùng method validation.

**7.** Bỏ `@Valid` trên `RegistrationForm.address` có ảnh hưởng gì?  
Constraint trên `AddressForm.city` không được duyệt qua cạnh đó khi validate root form.

**8.** Tại sao không bind thẳng vào entity?  
Để tránh mass assignment và tách dữ liệu web input khỏi thuộc tính nghiệp vụ/quản trị chỉ server được phép sửa.

**Ghi nhớ:** `@ModelAttribute` bind request thành object; `@Valid` kích hoạt validation mặc định và cascade theo các marker con; `@Validated(...)` cho phép chọn nhóm; `BindingResult` lưu lỗi binding + validation. Thiết kế form tốt cần đúng cả **annotation, nhóm, vị trí BindingResult, template, dependency và kiểm thử**.

## Tài liệu tham khảo

- [Spring Framework 6.2 — @ModelAttribute method arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — Configuring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — @Validated API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/annotation/Validated.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/BindingResult.html)
- [Jakarta Validation 3.0 specification — Groups, cascade, constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Thymeleaf + Spring 3.1 tutorial — th:field, th:errors](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html)
- [Spring Boot 3.5.7 release](https://spring.io/blog/2025/10/23/spring-boot-3-5-7-available-now/)
