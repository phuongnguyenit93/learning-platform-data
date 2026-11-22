# Giữ giá trị bị từ chối để hiển thị lại form trong Spring MVC

## Mục tiêu bài học

Khi người dùng nhập form rồi bấm **Gửi**, nếu một trường sai, ứng dụng nên hiển thị lại đúng dữ liệu người dùng vừa gõ cùng thông báo lỗi. Việc này khó hơn tưởng tượng: dữ liệu đầu vào HTTP là chuỗi, nhưng thuộc tính Java có thể là `Integer`, `LocalDate` hoặc một kiểu miền riêng. Nếu chuyển đổi kiểu thất bại, đối tượng Java **không chứa được giá trị thô vừa nhập**; Spring MVC cần giữ nó trong kết quả binding để form vẫn hiển thị lại.

Bài học nằm trong chủ đề **Binding trong MVC**. Sau khi học, bạn có thể:

- Giải thích `WebDataBinder`, `BindingResult`, `FieldError` và `rejectedValue` phối hợp thế nào.
- Phân biệt lỗi chuyển đổi kiểu (`typeMismatch`) với lỗi Bean Validation (`@NotBlank`, `@Email`, `@Min`).
- Viết controller dùng `@Valid @ModelAttribute` và đặt `BindingResult` đúng vị trí để re-render form thay vì mất input.
- Dùng Thymeleaf `th:object`, `th:field`, `th:errors` để trả lại giá trị lỗi mà không lấy trực tiếp chuỗi thô từ request.
- Kiểm thử đúng với trường hợp `age=abc` nhưng Java property `age` có kiểu `Integer`.
- Nhận biết các tình huống làm mất dữ liệu: thay model object, redirect lúc lỗi, tên thuộc tính không khớp, hoặc tự render `getAge()` thay vì tích hợp binding.

## 1. Tình huống và yêu cầu UX

Form đăng ký có ba ô:

~~~text
Họ tên: Lan
Email: sai-email
Tuổi: abc
[ Gửi ]
~~~

Ứng dụng Java dùng model:

~~~java
private String displayName;
private String email;
private Integer age;
~~~

Có hai loại vấn đề khác nhau:

1. `email = "sai-email"` bind được vào `String` nhưng không đạt `@Email`. Đây là **validation failure**.
2. `age = "abc"` không thể chuyển thành `Integer`. Đây là **binding/conversion failure**, thường có mã lỗi `typeMismatch`.

Nếu controller render lại form chỉ bằng cách đọc `signupForm.getAge()`, giá trị age có thể là `null`: người dùng sẽ thấy ô tuổi bị xóa dù vừa gõ `abc`. Tuy nhiên, `BindingResult` còn giữ thông tin về trường lỗi và giá trị bị từ chối để view có thể hiển thị lại `abc`.

Kết quả mong muốn:

~~~text
Họ tên: Lan
Email: sai-email
       Email không hợp lệ
Tuổi: abc
      Tuổi phải là một số nguyên
[ Gửi ]
~~~

Thông điệp lỗi có thể do message bundle quyết định; ví dụ minh họa trên không có nghĩa Spring tự sinh chính xác các câu tiếng Việt đó. Điều cần bảo đảm là **input được giữ**, lỗi được đặt cạnh trường phù hợp và chỉ dữ liệu hợp lệ mới đi tiếp vào xử lý nghiệp vụ.

## 2. Spring MVC lấy đâu ra “giá trị bị từ chối”?

Một HTTP form gửi request theo quy ước tên trường, ví dụ:

~~~http
POST /signup
Content-Type: application/x-www-form-urlencoded

displayName=Lan&email=sai-email&age=abc
~~~

Giá trị từ request ban đầu là các chuỗi. Khi gặp đối số `@ModelAttribute("signupForm")`, Spring MVC thực hiện đại ý:

~~~text
Request parameters: "Lan", "sai-email", "abc"
   |
   v
@ModelAttribute("signupForm")
   |
   v
WebDataBinder
   |-- chọn property được phép bind
   |-- đổi kiểu theo ConversionService/PropertyEditor
   |-- gán thuộc tính thành công vào SignupForm
   |-- ghi lỗi nếu không đổi kiểu được
   |
   v
@Valid / @Validated (nếu có, tại điểm hỗ trợ)
   |
   v
BindingResult
   |-- ObjectError và FieldError
   |-- rejectedValue cho trường thất bại
   |-- mã lỗi, arguments, default message
   |
   v
Controller: nếu hasErrors() thì return "signup"
   |
   v
Thymeleaf th:field + th:errors lấy thông tin binding
   |
   v
Form hiển thị lại input và lỗi
~~~

`WebDataBinder` chịu trách nhiệm liên kết giá trị nguồn với object và nhận diện lỗi đổi kiểu. `BindingResult` là giao diện giữ kết quả binding và validation, gồm cả những giá trị không thể nằm trong Java bean.

Một `FieldError` hỗ trợ:

~~~java
String field = fieldError.getField();
Object rejected = fieldError.getRejectedValue();
String code = fieldError.getCode();
boolean conversionFailed = fieldError.isBindingFailure();
String defaultMessage = fieldError.getDefaultMessage();
~~~

Đây là snippet API với biến `fieldError` đã có, **không phải class Java độc lập**.

- `getField()`: tên field, ví dụ `age` hoặc `address.city`.
- `getRejectedValue()`: giá trị bị từ chối. Với `age=abc` ở ví dụ thông thường là chuỗi `"abc"`; với `age=17` bind thành công nhưng vi phạm `@Min(18)`, giá trị có thể là số nguyên `17`.
- `isBindingFailure()`: `true` với lỗi binding như không đổi được kiểu; `false` với lỗi do validator phát hiện trên dữ liệu đã bind.
- `getCode()`: mã lỗi chính, ví dụ `typeMismatch`, `Email`, `Min`; khi muốn tùy biến thông điệp, kiểm tra `getCodes()` (danh sách mã ưu tiên) thay vì đoán mỗi mã.
- `getDefaultMessage()`: thông điệp mặc định, có thể phụ thuộc message source/locale.

**Quan trọng:** `rejectedValue` không đồng nghĩa với một thuộc tính luôn chứa giá trị ban đầu của *mọi* field. Nó có ý nghĩa trong ngữ cảnh **một lỗi**. Với field hợp lệ, nên lấy giá trị qua model/binding status như thông thường.

## 3. Lỗi conversion khác lỗi validation như thế nào?

Hai nhánh này cần phân biệt khi kiểm thử và render:

| Input | Kiểu đích | Ràng buộc | Kết quả binding | Kết quả validation |
| --- | --- | --- | --- | --- |
| `age=22` | `Integer` | `@Min(18)` | Thành công: `22` | Hợp lệ |
| `age=17` | `Integer` | `@Min(18)` | Thành công: `17` | Lỗi `Min` |
| `age=abc` | `Integer` | `@Min(18)` | Không đổi được thành `Integer` | Có lỗi `typeMismatch`; có thể thêm lỗi khác tùy cấu hình |
| `email=not-an-email` | `String` | `@Email` | Thành công | Lỗi `Email` |
| `displayName=""` | `String` | `@NotBlank` | Thành công: `""` | Lỗi `NotBlank` |

Nếu conversion fail, Java bean có thể còn `null` hoặc giá trị cũ tại property đích; không suy luận rằng nó giữ `"abc"`. Đối với validation failure, giá trị đã được bind thường nằm trong model, đồng thời `FieldError` giữ giá trị bị từ chối.

Cùng một field đôi khi có hơn một lỗi (ví dụ conversion thất bại làm thuộc tính còn `null` và có cả `@NotNull`). Do đó, không ép bài toán về quy tắc “mỗi field chỉ có một FieldError”; `getFieldErrors("age")` có thể trả nhiều phần tử. Khi cần tìm **lỗi binding**, kiểm tra `isBindingFailure()` thay vì chỉ lấy lỗi đầu rồi khẳng định đó luôn là lỗi duy nhất.

## 4. Ví dụ Spring Boot 3 + Java 17 chạy được

Ví dụ dùng Spring MVC, Jakarta Bean Validation và Thymeleaf. Người dùng truy cập `GET /signup`, gửi `POST /signup`. Khi lỗi, controller trả về lại view `signup` và giữ `BindingResult`. Khi hợp lệ, chương trình redirect tới trang thành công mẫu; ví dụ không lưu dữ liệu xuống database.

Cấu trúc thư mục:

~~~text
rejected-values-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/form/
    │   │   ├── FormApplication.java
    │   │   ├── SignupForm.java
    │   │   └── SignupController.java
    │   └── resources/
    │       ├── templates/signup.html
    │       └── application.properties
    └── test/
        └── java/com/example/form/SignupControllerTest.java
~~~

### 4.1. Maven: pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>rejected-values-demo</artifactId>
    <version>1.0.0</version>
    <name>rejected-values-demo</name>

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

Spring Boot 3.3.5 là bản ví dụ cố định, dùng namespace `jakarta.validation.*` và Java 17. Trong dự án thật, dùng phiên bản Spring Boot/BOM đã được quản lý của dự án; không thêm trùng provider validation.

### 4.2. Điểm khởi động: FormApplication.java

~~~java
package com.example.form;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormApplication {
    public static void main(String[] args) {
        SpringApplication.run(FormApplication.class, args);
    }
}
~~~

### 4.3. Form backing object: SignupForm.java

~~~java
package com.example.form;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank
    private String displayName;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
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
~~~

Dùng một **DTO riêng cho form** để tránh cho HTTP request ghi trực tiếp vào entity/domain object. `Integer` giúp thể hiện rõ lỗi conversion (số nhập dưới dạng chuỗi) và trường hợp người dùng chưa nhập gì. `@NotNull` kiểm tra việc hiện diện, `@Min(18)` kiểm tra giá trị sau chuyển đổi thành công.

### 4.4. Controller: SignupController.java

~~~java
package com.example.form;

import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class SignupController {

    @InitBinder("signupForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "displayName", "email", "age");
    }

    @GetMapping("/signup")
    public String show(Model model) {
        model.addAttribute("signupForm", new SignupForm());
        return "signup";
    }

    @PostMapping("/signup")
    public String submit(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            return "signup";
        }

        // Ứng dụng thật sẽ thực hiện nghiệp vụ/lưu dữ liệu tại đây.
        return "redirect:/signup/success";
    }

    @GetMapping("/signup/success")
    @ResponseBody
    public String success() {
        return "Form accepted";
    }
}
~~~

Đây là cơ chế then chốt:

1. `@ModelAttribute("signupForm")` tạo/lấy object tên `signupForm` và cho Spring bind các parameter phù hợp.
2. `@Valid` yêu cầu chạy Bean Validation sau binding.
3. `BindingResult` **phải đứng ngay sau** tham số `@ModelAttribute` cần nhận lỗi. Không chèn `Model`, `HttpServletRequest` hoặc một tham số không liên quan vào giữa hai đối số.
4. `bindingResult.hasErrors()` phát hiện cả lỗi binding lẫn lỗi validation.
5. Khi có lỗi, `return "signup"` render cùng template trong **chính request POST**. Spring đưa model attribute và BindingResult của nó vào model để view hiển thị đúng dữ liệu.
6. Chỉ khi không có lỗi mới redirect. Ví dụ không thật sự lưu người dùng; thông báo `Form accepted` đơn thuần cho thấy đã vượt qua validation.
7. `@InitBinder` giới hạn những property cho phép ghi từ request: `displayName`, `email`, `age`. Đây là cách giảm rủi ro mass assignment; trong dự án thật còn cần thiết kế DTO và chính sách binding phù hợp.

**Không làm điều sau trong nhánh lỗi:**

~~~java
if (bindingResult.hasErrors()) {
    model.addAttribute("signupForm", new SignupForm());
    return "signup";
}
~~~

Đây là **đoạn code sai để so sánh**, không thuộc controller chạy được ở trên. Nó thay object vừa bind bằng object rỗng, làm thất lạc dữ liệu người dùng và có thể khiến trạng thái model/`BindingResult` lệch nhau.

### 4.5. Thymeleaf template: templates/signup.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng ký</title>
    <style>
        .invalid { border: 2px solid #b00020; }
        .error { color: #b00020; }
    </style>
</head>
<body>
<h1>Đăng ký</h1>

<form th:action="@{/signup}"
      th:object="${signupForm}"
      method="post">

    <div>
        <label for="displayName">Họ tên</label>
        <input type="text"
               th:field="*{displayName}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('displayName')}"
           th:errors="*{displayName}"></p>
    </div>

    <div>
        <label for="email">Email</label>
        <input type="text"
               th:field="*{email}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('email')}"
           th:errors="*{email}"></p>
    </div>

    <div>
        <label for="age">Tuổi</label>
        <input type="text"
               inputmode="numeric"
               th:field="*{age}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('age')}"
           th:errors="*{age}"></p>
    </div>

    <button type="submit">Gửi</button>
</form>
</body>
</html>
~~~

Chú ý cú pháp:

- `th:object="${signupForm}"` chọn form-backing bean có tên chính xác `signupForm`.
- `th:field="*{age}"` tích hợp Spring binding status: khi đã có `FieldError`, nó có thể render lại **giá trị lỗi `"abc"`**, dù `form.getAge()` là `null`.
- `th:errors="*{age}"` hiển thị thông báo lỗi của chính field `age`; `#fields.hasErrors('age')` quyết định có xuất hiện phần thông báo hay không.
- `th:errorclass="invalid"` thêm CSS class khi field sai.
- `inputmode="numeric"` khuyến khích bàn phím nhập số trên thiết bị di động nhưng để `type="text"`, tránh việc trình duyệt loại bỏ hoặc chuẩn hóa một chuỗi `abc` theo quy tắc riêng của `<input type="number">`. Phải tiếp tục validate phía server.
- Spring Thymeleaf escape nội dung khi dùng `th:field`/`th:errors` theo cơ chế template thông thường. Không lấy dữ liệu người dùng chèn bằng HTML chưa escape như `th:utext`.

Tên của `th:object`, `@ModelAttribute`, và key của `BindingResult` cần khớp nhau. Khi model object tên `signupForm`, Spring dùng khóa kết quả binding:

~~~text
org.springframework.validation.BindingResult.signupForm
~~~

Hằng số `BindingResult.MODEL_KEY_PREFIX` có giá trị tiền tố này; không cần tự gõ chuỗi key trong production code.

### 4.6. application.properties

Có thể dùng file cấu hình tối giản:

~~~properties
spring.thymeleaf.cache=false
server.port=8080
~~~

Tắt template cache ở đây chỉ giúp việc sửa HTML trong môi trường học/dev dễ thấy hơn; không nên mặc định tắt cache trong production.

### 4.7. Chạy thử

Từ thư mục chứa `pom.xml`, với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Mở `http://localhost:8080/signup`. Nhập:

~~~text
Họ tên = Lan
Email  = sai-email
Tuổi   = abc
~~~

Rồi gửi form. Controller trả view `signup`, form hiển thị lại `Lan`, `sai-email` và `abc` cùng các thông báo lỗi tương ứng. Response thường là HTTP 200 vì ví dụ chủ động render lại một trang HTML; ứng dụng có thể chọn mã trạng thái khác nếu contract yêu cầu.

Tiếp theo, nhập:

~~~text
Họ tên = Lan
Email  = lan@example.com
Tuổi   = 22
~~~

Lần này form không có lỗi; controller trả `redirect:/signup/success` (HTTP 302) và endpoint đích trả văn bản `Form accepted`. Ví dụ không thực hiện ghi dữ liệu.

## 5. Kiểm thử tự động bằng MockMvc

Ngoài việc nhìn form trong trình duyệt, nên kiểm chứng trực tiếp `BindingResult` để bắt lỗi conversion và lỗi validation. File `src/test/java/com/example/form/SignupControllerTest.java`:

~~~java
package com.example.form;

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
class SignupControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void initialFormHasBackingObject() throws Exception {
        mockMvc.perform(get("/signup"))
                .andExpect(status().isOk())
                .andExpect(view().name("signup"))
                .andExpect(model().attributeExists("signupForm"));
    }

    @Test
    void typeMismatchKeepsRejectedText() throws Exception {
        var result = mockMvc.perform(post("/signup")
                        .param("displayName", "Lan")
                        .param("email", "sai-email")
                        .param("age", "abc"))
                .andExpect(status().isOk())
                .andExpect(view().name("signup"))
                .andExpect(model().attributeHasFieldErrors(
                        "signupForm", "email", "age"))
                .andReturn();

        ModelAndView mav = result.getModelAndView();
        assertNotNull(mav);

        Object rawResult = mav.getModel().get(
                BindingResult.MODEL_KEY_PREFIX + "signupForm");

        assertInstanceOf(BindingResult.class, rawResult);
        BindingResult errors = (BindingResult) rawResult;

        FieldError ageError = errors.getFieldError("age");
        assertNotNull(ageError);
        assertTrue(ageError.isBindingFailure());
        assertEquals("abc", ageError.getRejectedValue());
        assertEquals("abc", errors.getFieldValue("age"));

        SignupForm form = (SignupForm)
                mav.getModel().get("signupForm");
        assertNotNull(form);
        assertEquals("Lan", form.getDisplayName());
        assertEquals("sai-email", form.getEmail());
        assertNull(form.getAge());
    }

    @Test
    void minViolationIsNotTypeMismatch() throws Exception {
        var result = mockMvc.perform(post("/signup")
                        .param("displayName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "17"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "signupForm", "age"))
                .andReturn();

        ModelAndView mav = result.getModelAndView();
        assertNotNull(mav);
        BindingResult errors = (BindingResult) mav.getModel()
                .get(BindingResult.MODEL_KEY_PREFIX
                        + "signupForm");

        assertNotNull(errors);
        FieldError ageError = errors.getFieldError("age");
        assertNotNull(ageError);
        assertFalse(ageError.isBindingFailure());
        assertEquals(17, ageError.getRejectedValue());
    }

    @Test
    void validFormRedirects() throws Exception {
        mockMvc.perform(post("/signup")
                        .param("displayName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "22"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/signup/success"));
    }
}
~~~

Lệnh chạy:

~~~bash
mvn test
~~~

Các khẳng định kỳ vọng:

- `GET /signup` có model attribute `signupForm`.
- POST với `age=abc` render lại `signup`, có lỗi field `age` và `email`; `FieldError.getRejectedValue()` của age giữ `"abc"`.
- `BindingResult.getFieldValue("age")` cũng trả giá trị người dùng cần thấy khi bind thất bại; trong khi `SignupForm.getAge()` là `null` vì `"abc"` không thể gán cho `Integer`.
- POST với `age=17` có lỗi `@Min(18)` nhưng không phải type mismatch; rejected value là giá trị đã chuyển kiểu.
- POST hợp lệ redirect.

Test đọc kết quả trong model thay vì giả định toàn bộ HTML render luôn giữ cùng thứ tự thuộc tính hoặc CSS. Nếu muốn kiểm thử trực quan, có thể bổ sung assertion DOM/HTML rằng input có tên `age` hiển thị lại `abc`. Với HTML form, một browser end-to-end test còn giúp phát hiện hành vi riêng của control như number input, select, checkbox hoặc JavaScript.

## 6. Các API của BindingResult cần hiểu đúng

Đây là phần quan trọng khi debug tại controller:

~~~java
boolean invalid = bindingResult.hasErrors();

int errorCount = bindingResult.getErrorCount();

FieldError firstAgeError =
        bindingResult.getFieldError("age");

java.util.List<FieldError> ageErrors =
        bindingResult.getFieldErrors("age");

Object displayValue =
        bindingResult.getFieldValue("age");

Object rawProperty =
        bindingResult.getRawFieldValue("age");

String[] suppressed =
        bindingResult.getSuppressedFields();
~~~

Đây là code minh họa trong phạm vi controller đã có `bindingResult`; không phải chương trình độc lập.

| API | Trả về gì | Khi nào dùng |
| --- | --- | --- |
| `hasErrors()` | Có ít nhất một lỗi field/global | Quyết định render lại form |
| `getFieldError("age")` | Lỗi đầu tiên của field hoặc `null` | Kiểm tra nhanh trường lỗi |
| `getFieldErrors("age")` | Danh sách lỗi của field | Hiển thị/kiểm tra nhiều constraint |
| `getRejectedValue()` | Giá trị mà một lỗi từ chối | Phân tích nguyên nhân input sai |
| `isBindingFailure()` | Conversion/binding error hay validation error | Phân biệt `typeMismatch` với `Min` |
| `getFieldValue("age")` | Giá trị dành cho giao diện của field: có thể là rejected value | Giữ input khi conversion không thành công |
| `getRawFieldValue("age")` | Giá trị property thô trên target, chưa áp dụng display format | Debug target; **không** thay thế rejected value |
| `getFieldType("age")` | Kiểu Java của property nếu xác định được | Tìm lỗi converter |
| `getAllErrors()` | Cả `FieldError` và `ObjectError` | Hiển thị lỗi field/global |
| `getSuppressedFields()` | Những field bị suppress khi binder từ chối binding | Theo dõi chính sách allowed/disallowed fields |
| `getModel()` | Map gồm object và BindingResult | Khi tự dựng `ModelAndView`/đưa binding context sang view |

**Điểm mấu chốt:** `getRawFieldValue("age")` là dữ liệu gắn với property đích, thường `null` sau conversion failure. `getFieldValue("age")` được thiết kế để trả lại rejected update khi có lỗi, nên phù hợp với yêu cầu hiện giá trị người dùng đã nhập. `FieldError.getRejectedValue()` là dữ liệu của **từng lỗi** và không nên xem là toàn bộ state của form.

`BindingResult` cũng là `Errors`, có API `rejectValue(...)` để đăng ký lỗi nghiệp vụ thủ công. Khi tự thêm lỗi, cần đặt code và giá trị phù hợp; lỗi thủ công không tự là một binding failure. Chỉ dùng `getRejectedValue()` từ lỗi đã ghi đúng thông tin.

### 6.1. Model có hai entry liên quan

Khi Spring tạo `BindingResult` cho object tên `signupForm`, view có thể nhận:

~~~text
"signupForm" -> SignupForm vừa bind
"org.springframework.validation.BindingResult.signupForm" -> BindingResult
~~~

Theo API:

~~~java
String errorsKey =
        BindingResult.MODEL_KEY_PREFIX + "signupForm";

Object errors = model.asMap().get(errorsKey);
~~~

Đây là snippet giải thích model contract; controller ví dụ chính không cần thao tác thủ công. Nếu custom code tự tạo `ModelAndView`, có thể cần chuyển cả object và binding result, chẳng hạn dùng `bindingResult.getModel()`. Trong flow `@ModelAttribute + BindingResult` thông thường, Spring xử lý việc này khi render view.

## 7. Tại sao Thymeleaf th:field giữ được cả giá trị không hợp lệ?

Khi form được bind với object qua `th:object`, cú pháp `th:field="*{age}"` không tương đương với việc đọc đơn giản `signupForm.age`. Tích hợp Thymeleaf/Spring xem **binding status** của field, có thể lấy giá trị reject từ `BindingResult` thay vì chỉ xem getter trên bean.

So sánh:

~~~html
<!-- Đúng: tích hợp Spring binding -->
<input type="text" th:field="*{age}">

<!-- Có thể làm mất "abc" nếu age kiểu Integer và bind lỗi -->
<input type="text" th:value="${signupForm.age}">
~~~

Hai dòng này chỉ là ví dụ đối chiếu trong template đã có `th:object`; dòng thứ hai cố ý minh họa cách làm có vấn đề. Khi age bị type mismatch, property Java có thể `null` nên `th:value` không có dữ liệu để hiển thị, dù `BindingResult` vẫn còn `"abc"`.

Tương tự, dùng JSP Spring form tags:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form modelAttribute="signupForm" method="post" action="/signup">
    <form:input path="age"/>
    <form:errors path="age" cssClass="error"/>
    <button type="submit">Gửi</button>
</form:form>
~~~

Đây là **ví dụ JSP thay cho Thymeleaf**, không thuộc project Maven Thymeleaf phía trên. `<form:input>` và `<form:errors>` cũng dựa trên Spring binding context. Cần cấu hình JSP view resolver riêng nếu dùng JSP.

Không nhất thiết mọi template engine đều tự dùng `BindingResult`. Nếu render HTML bằng tay hoặc dùng engine thiếu Spring integration, phải chủ động lấy `getFieldValue()`/`FieldError` và escape nội dung đúng ngữ cảnh để giữ được rejected input.

## 8. Redirect khi form sai: vì sao dễ mất dữ liệu?

Các dòng sau mang ý nghĩa khác nhau:

~~~java
if (bindingResult.hasErrors()) {
    return "signup";
}
~~~

Đây là cách ví dụ chính dùng: cùng request, model và `BindingResult` còn sẵn, view có thể hiển thị lại input và lỗi.

~~~java
if (bindingResult.hasErrors()) {
    return "redirect:/signup";
}
~~~

Đây là **ví dụ sai khi không có cơ chế lưu trạng thái**. Redirect sinh request GET mới; các request-scoped model attributes và `BindingResult` của POST không tự đi theo. Nếu GET tạo `new SignupForm()`, form sẽ rỗng. Lỗi này thường bị chẩn đoán nhầm là “Thymeleaf không giữ value”.

### 8.1. Khi thật sự cần PRG cho nhánh lỗi

Mẫu **Post/Redirect/Get** hữu ích sau khi thành công để tránh gửi lại form khi refresh. Nếu bắt buộc redirect cả lúc lỗi, cần chuyển có chủ đích **cả form object lẫn BindingResult** qua flash attributes. Ví dụ minh họa trong controller:

~~~java
redirectAttributes.addFlashAttribute(
        "signupForm", form);

redirectAttributes.addFlashAttribute(
        BindingResult.MODEL_KEY_PREFIX + "signupForm",
        bindingResult);

return "redirect:/signup";
~~~

Đoạn này giả định đã inject thêm `RedirectAttributes redirectAttributes` vào handler. Trang GET phải kiểm tra model/flash attribute hiện có trước khi tạo object mới, nếu không sẽ ghi đè dữ liệu vừa flash. Cơ chế flash thường dựa vào session/redirect lifecycle; cần cân nhắc dữ liệu nhạy cảm, độ lớn object, serialized state và concurrency giữa nhiều tab. Trong ứng dụng form bình thường, **return cùng view khi lỗi, redirect khi thành công** dễ kiểm soát hơn.

### 8.2. Không lấy lại form chỉ bằng query string

Không nên chuyển toàn bộ input sai (đặc biệt email/token/thông tin nhạy cảm) lên URL như:

~~~text
/signup?email=sai-email&age=abc
~~~

URL có thể nằm trong browser history, log, analytics và referrer. Nếu yêu cầu chỉ là giữ form sau POST lỗi, `BindingResult` trong server-rendered view đáp ứng đúng mục tiêu mà không cần đưa dữ liệu thô vào URL.

## 9. Những điểm dễ làm giá trị bị đổi hoặc thất lạc

### 9.1. Tên model attribute không đồng nhất

Nếu POST dùng `@ModelAttribute("registration")` nhưng view dùng `th:object="${signupForm}"`, engine không nhìn vào cùng object và binding result. Hãy thống nhất tên ở GET, POST, template và key `BindingResult.MODEL_KEY_PREFIX + objectName`.

### 9.2. Tên field HTML không khớp Java property

Spring bind dựa trên tên field, ví dụ `name="displayName"` với `setDisplayName(...)`. `th:field="*{displayName}"` tạo tên/id phù hợp. Nếu tự ghi `name="full_name"` nhưng model chỉ có `displayName`, cần custom binding/naming thích hợp; không thể kỳ vọng Spring tự suy ra hai tên đồng nghĩa.

### 9.3. Input type có quy tắc riêng của trình duyệt

`<input type="number">` có thể không hiển thị chuỗi như `abc` do trình duyệt thực thi quy tắc HTML form controls. Nếu muốn phục hồi chính xác mọi chuỗi bất hợp lệ để chỉ rõ lỗi server, `type="text" inputmode="numeric"` là lựa chọn minh họa dễ quan sát. Nhưng dù dùng loại control nào, **server vẫn phải kiểm tra** kiểu và giới hạn.

Với `select`, `checkbox`, radio và multi-select, cách giữ state không đơn giản là đặt một chuỗi `value`. Dùng đúng integration `th:field`, `th:checked`/selected semantics và kiểm thử lại khi lựa chọn thiếu hoặc không hợp lệ. Một trường có nhiều lựa chọn phải có loại Java/collection phù hợp.

### 9.4. Định dạng ngày, số và locale

`LocalDate`, `BigDecimal`, tiền tệ và timestamp có conversion/formatting theo locale. Ví dụ input `31/02/2026` không thể thành ngày hợp lệ; model property có thể null nhưng BindingResult còn giá trị lỗi. Cấu hình `@DateTimeFormat`, `Formatter` hoặc `Converter` đúng nghiệp vụ, rồi cho view lấy giá trị qua Spring binding integration.

Không tự chuyển mọi giá trị kiểu ngày/số về một định dạng cố định sau lỗi, vì có thể làm thay đổi ý nghĩa hoặc khiến người dùng không nhận ra dữ liệu vừa nhập. Khi conversion đã thành công nhưng constraint thất bại, view có thể hiện formatted value theo formatter của ứng dụng; **đây là hành vi khác** với việc giữ nguyên chuỗi lỗi từ conversion.

### 9.5. Nested properties và collection indexes

Nếu form có `contact.address.city` hoặc `items[0].quantity`, đường dẫn lỗi sẽ dùng tên field tương ứng:

~~~text
contact.address.city
items[0].quantity
~~~

Muốn view hiện lại giá trị tại đúng trường, Spring binding phải nhận biết nested path và template phải bind đúng đường dẫn. Những collection có thể cần khởi tạo phần tử, index hợp lệ và giới hạn auto-grow; không nên cho HTTP input tạo collection không giới hạn. Kiểm tra thêm `FieldError.getField()` để xác minh lỗi gắn đúng index/property.

### 9.6. Không “sửa” lỗi bằng cách xóa FieldError

Việc gọi `bindingResult.getFieldErrors().clear()` không phải cách tin cậy để sửa kết quả và có thể không được hỗ trợ bởi collection trả về. Muốn chuẩn hóa input như trim khoảng trắng, cần xác định rõ điểm conversion/normalization trước validation, sau đó kiểm thử cách dữ liệu hiển thị. Đừng xóa lỗi chỉ để template không hiện thông báo.

## 10. Bảo mật và giới hạn của việc giữ lại input

Mục tiêu UX “giữ giá trị đã nhập” cần có ngoại lệ:

- **Mật khẩu, OTP, token, API key, số thẻ:** không tự động echo lại input bí mật trong value của HTML, thông báo lỗi, session flash hay log. Thiết kế để người dùng nhập lại giá trị cần bảo vệ.
- **XSS:** render qua `th:field` / `th:text` (escape theo ngữ cảnh), không dùng `th:utext` với input chưa được tin cậy. Cần xử lý thêm attribute/URL/JS context theo chính sách template.
- **Mass assignment:** tránh bind HTTP request trực tiếp vào entity chứa các field quản trị như `id`, `role`, `approved`. Dùng form DTO riêng; nếu property binding được bật, cân nhắc `WebDataBinder.setAllowedFields(...)` và kiểm tra `getSuppressedFields()`.
- **Thông điệp lỗi:** tránh đưa `getRejectedValue()` nguyên văn vào exception/log nếu có thể chứa dữ liệu cá nhân; chọn thông điệp ngắn gọn và mã field ổn định.
- **Đa tab/redirect:** flash/session dùng lại sai object giữa hai submit đồng thời có thể gây khó hiểu. Ưu tiên same-request re-render khi form lỗi.
- **Dữ liệu phía server:** không tin rằng đã render lại value thì input hợp lệ. Chỉ thực hiện nghiệp vụ khi binding và validation đã qua, rồi vẫn kiểm tra domain rules ở tầng phù hợp.

### CSRF khi ứng dụng có Spring Security

Bản demo không thêm Spring Security để tập trung vào binding. Trong ứng dụng có CSRF protection, form POST cần gửi CSRF token đúng cơ chế Spring Security/Thymeleaf đang cấu hình. Không vô hiệu hóa bảo vệ CSRF chỉ vì form validation thất bại. Các lỗi 403 liên quan CSRF phải được phân biệt với `BindingResult.hasErrors()`, vì CSRF failure có thể xảy ra trước khi controller được gọi.

## 11. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân điển hình | Cách sửa |
| --- | --- | --- |
| POST sai, form trở về rỗng | Trả `redirect:/signup` mà không dùng flash, hoặc GET tạo model mới | Trả cùng view khi lỗi; giữ `BindingResult` |
| `age=abc` biến thành ô trắng | Render `form.getAge()` hoặc `th:value` thay vì binding status | Dùng `th:field`/`getFieldValue("age")` |
| Controller không vào nhánh `hasErrors()` | `BindingResult` không đứng ngay sau `@ModelAttribute` hoặc validation không được kích hoạt | Sửa thứ tự đối số, kiểm tra `@Valid` và starter validation |
| Không có thông báo ở field | `th:errors` dùng sai tên property/object hoặc thiếu constraint | Đồng bộ tên model, field và binding path |
| Có lỗi `typeMismatch` nhưng field không nhận giá trị | Converter không thể gán, đó là điều bình thường | Lấy rejected update từ `BindingResult` thay vì bean getter |
| Có `17` nhưng báo lỗi Min | Chuyển đổi thành công; giá trị không đạt `@Min(18)` | Hiển thị lại `17` cùng validation message |
| Không xác định được lỗi nào xảy ra | Chỉ đọc `getErrorCount()` | Duyệt `getFieldErrors()`, `getField()`, `getCodes()`, `isBindingFailure()` |
| Form bị ghi đè sau POST | Controller thay `signupForm` bằng object khác | Giữ object đã bind cho chính view đó |
| Custom formatter “nuốt” chuỗi sai | Converter trả default không hợp lý thay vì báo fail | Sửa conversion semantics; bảo toàn thông tin lỗi |
| Browser không hiện lại chuỗi sai cho số | HTML `type="number"` từ chối giá trị không đúng cú pháp | Dùng control phù hợp; kiểm thử trên browser thật |
| Giá trị bí mật xuất hiện trong HTML | Tái hiển thị mọi field không phân biệt | Không echo password/token; thiết kế field riêng |
| Giữ input nhưng cập nhật nhầm role/admin | Bind trực tiếp entity hoặc không giới hạn allowed fields | Dùng DTO và whitelist field |
| Thông điệp lỗi thay đổi theo locale | MessageSource/Formatter thay đổi display | Kiểm thử lỗi trên locale cần hỗ trợ |

## 12. Quy trình kiểm tra khi form “mất dữ liệu”

Nếu gặp sự cố ngoài thực tế, điều tra theo thứ tự:

1. Kiểm tra request submit thực sự gửi `name=value` nào trong DevTools Network.
2. Kiểm tra controller nhận đúng `@ModelAttribute("...")` và `BindingResult` sát ngay phía sau.
3. Kiểm tra `bindingResult.hasErrors()`, `getFieldErrors()`, `getFieldError("field").getRejectedValue()`, `isBindingFailure()` và `getFieldValue("field")`. Không log dữ liệu nhạy cảm.
4. Xác nhận nhánh lỗi trả về **view name** trực tiếp, không redirect ngoài ý muốn.
5. Kiểm tra model khi render có đúng object name và `BindingResult.MODEL_KEY_PREFIX + objectName`, đặc biệt nếu dùng `ModelAndView` tùy chỉnh.
6. Trong template, ưu tiên `th:field` và `th:errors`; kiểm tra element `name`, field path, loại HTML input và custom JavaScript có ghi đè giá trị sau render hay không.
7. Phân biệt lỗi conversion với lỗi Bean Validation; thử cả `age=abc` và `age=17`.
8. Sau khi sửa, test cả request thành công và request lỗi, không bỏ qua hành vi refresh/redirect hay nhiều tab.

## 13. Bài tập thực hành

**Bài 1 — Phân tích khác biệt:** Gửi `age=abc` vào field `Integer age` có `@Min(18)`. Vì sao getter của object có thể là `null`, còn `BindingResult.getFieldValue("age")` vẫn là `"abc"`? Trả lời dựa trên hai bước conversion và lưu rejected input.

**Bài 2 — Giữ lại dữ liệu:** Đổi template từ `th:field="*{age}"` sang `th:value="${signupForm.age}"`, thử nhập chuỗi không phải số. So sánh UI và giải thích vì sao giữ lại binding status cần thiết.

**Bài 3 — Thêm trường ngày:** Bổ sung `birthDate: LocalDate` với quy tắc định dạng và validation phù hợp. Gửi ngày không hợp lệ, rồi so `getRejectedValue()`, `getFieldValue()` và giá trị trên object.

**Bài 4 — Redirect có chủ đích:** Thay nhánh lỗi thành `redirect:/signup`, quan sát dữ liệu biến mất. Giải thích phải mang theo hai model keys nào nếu dùng flash attributes và tại sao GET không được ghi đè chúng.

**Bài 5 — Lỗi lồng:** Tạo `AddressForm` có field `city`, đặt `@Valid` trên field `address` của form và render `th:field="*{address.city}"`. Xác minh path của `FieldError` là `address.city` và dữ liệu lồng sai vẫn hiện khi re-render.

**Bài 6 — Test bảo mật:** Thử thêm tham số POST `role=ADMIN` khi `SignupForm` không có role hoặc role không nằm trong allowed fields. Xác nhận request không được phép thay đổi state quản trị; không thiết kế form backing bean dùng trực tiếp entity nhạy cảm.

### Ghi nhớ

**Giữ form không chỉ là giữ Java object.** Nếu conversion thất bại, object có thể không giữ được chuỗi vừa nhập. `BindingResult` lưu giá trị bị từ chối và lỗi của field; `th:field`/Spring form tags biết đọc binding status để hiện lại dữ liệu trong cùng request. Controller dùng `@Valid @ModelAttribute`, đặt `BindingResult` ngay sau đó, **return view khi có lỗi** và chỉ redirect sau khi qua validation. Phân biệt conversion failure với validation failure và tránh phản chiếu lại dữ liệu bí mật.

## Tài liệu tham khảo

- [Spring Framework Reference — @ModelAttribute trong handler method, BindingResult và validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework API — BindingResult, getFieldValue, getModel, MODEL_KEY_PREFIX](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework API — FieldError và getRejectedValue/isBindingFailure](https://docs.spring.io/spring-framework/docs/6.2.15-SNAPSHOT/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework API — AbstractBindingResult.getFieldValue](https://docs.spring.io/spring-framework/docs/6.2.0-M7/javadoc-api/org/springframework/validation/AbstractBindingResult.html)
- [Thymeleaf + Spring Tutorial — th:field, th:errors và Spring form integration](https://www.thymeleaf.org/doc/tutorials/3.0/thymeleafspring.html)
- [Spring Framework Reference — Redirect Attributes, Flash Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/flash-attributes.html)
- [Spring Framework Reference — MVC Data Binding và Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html)
