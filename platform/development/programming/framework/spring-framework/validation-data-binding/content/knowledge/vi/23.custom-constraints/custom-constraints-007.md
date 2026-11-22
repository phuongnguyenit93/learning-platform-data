# Đưa lỗi toàn đối tượng về một đường dẫn trường trong Spring Validation

## 1. Bài toán và kết quả mong muốn

Một quy tắc cần kiểm tra **quan hệ giữa nhiều thuộc tính** thường được đặt ở cấp đối tượng (class-level): ví dụ `password` phải bằng `confirmPassword`, ngày kết thúc phải sau ngày bắt đầu, hoặc `minPrice` không được lớn hơn `maxPrice`. Nếu ràng buộc cấp lớp trả về lỗi theo mặc định, đường dẫn vi phạm (property path) trỏ tới chính đối tượng; trong Spring MVC lỗi thường trở thành `ObjectError`, còn giao diện muốn hiển thị lỗi ngay dưới một ô nhập cụ thể thường cần `FieldError`.

**Mục tiêu:** vẫn kiểm tra quy tắc liên trường, nhưng gắn thông báo vào đường dẫn trường có trách nhiệm sửa lỗi, chẳng hạn `confirmPassword`. Với Jakarta Bean Validation, làm việc này **ngay trong `ConstraintValidator`** bằng `ConstraintValidatorContext.addPropertyNode(...)`. Với kiểm tra thủ công trong Spring, dùng `Errors.rejectValue(...)` hoặc `BindingResult.rejectValue(...)` để đăng ký lỗi trường.

Ví dụ khi hai mật khẩu khác nhau:

| Cách ghi nhận | Đường dẫn/lỗi | Cách trình bày thường gặp |
| --- | --- | --- |
| Class-level violation mặc định | Property path rỗng ở root; Spring nhận `ObjectError` | Thông báo chung của biểu mẫu |
| Class-level violation + `addPropertyNode("confirmPassword")` | Property path `confirmPassword`; Spring nhận `FieldError` | Thông báo cạnh ô xác nhận mật khẩu |
| Spring `errors.reject("password.mismatch", ...)` | `ObjectError` | Thông báo chung |
| Spring `errors.rejectValue("confirmPassword", ...)` | `FieldError` | Thông báo cạnh ô xác nhận mật khẩu |

Không cần và cũng không nên cố “đổi loại” một `ObjectError` đã được tạo. Hãy tạo lỗi với **đường dẫn đúng ngay từ nguồn kiểm tra**.

## 2. Cơ chế ánh xạ từ Bean Validation sang Spring

1. `@Valid` trên tham số model yêu cầu Bean Validation kiểm tra đối tượng, nếu đã cấu hình nhà cung cấp validation.
2. Ràng buộc cấp lớp chạy `ConstraintValidator<Annotation, Form>.isValid(form, context)`.
3. Nếu trả về `false` mà không chỉnh context, vi phạm nằm ở đối tượng gốc; path thường là chuỗi rỗng.
4. Khi gọi `context.disableDefaultConstraintViolation()` rồi xây violation với `addPropertyNode("confirmPassword")`, vi phạm mới có property path `confirmPassword`.
5. Cơ chế tích hợp Spring chuyển violation theo field path thành lỗi thuộc trường trên `BindingResult`; Thymeleaf hoặc mã xử lý API có thể truy cập qua `getFieldErrors("confirmPassword")`.

**Hai chi tiết bắt buộc:** sau `buildConstraintViolationWithTemplate(...)` phải kết thúc bằng `addConstraintViolation()`; nếu vô hiệu hóa default violation thì phải tạo ít nhất một violation mới khi trả về `false`. Đừng gọi `addBeanNode()` nếu mong muốn một property path.

## 3. Ví dụ hoàn chỉnh: khớp mật khẩu, thông báo ở `confirmPassword`

Ví dụ dùng Java 17, Spring Boot 3.5.7, Spring MVC và Jakarta Validation (các package `jakarta.validation.*`). Mỗi lớp dưới đây nằm trong package `com.example.demo`. Cấu trúc chính:

~~~text
pom.xml
src/main/java/com/example/demo/
  DemoApplication.java
  RegistrationForm.java
  MatchingPasswords.java
  MatchingPasswordsValidator.java
  RegistrationController.java
src/main/resources/templates/register.html
src/test/java/com/example/demo/RegistrationValidationTest.java
~~~

### 3.1. Maven dependencies

~~~xml
<!-- pom.xml -->
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
    <artifactId>validation-field-path-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

`spring-boot-starter-validation` cung cấp Bean Validation provider; chỉ có `jakarta.validation-api` mà không có provider thì ví dụ thực thi chưa đủ. Với Spring Framework 5 / Boot 2, các import tương đương thuộc `javax.validation.*`; không trộn hai namespace.

### 3.2. Đối tượng cần kiểm tra

~~~java
// src/main/java/com/example/demo/RegistrationForm.java
package com.example.demo;

import jakarta.validation.constraints.NotBlank;

@MatchingPasswords
public class RegistrationForm {
    @NotBlank(message = "Vui lòng nhập mật khẩu")
    private String password;

    @NotBlank(message = "Vui lòng xác nhận mật khẩu")
    private String confirmPassword;

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getConfirmPassword() {
        return confirmPassword;
    }

    public void setConfirmPassword(String confirmPassword) {
        this.confirmPassword = confirmPassword;
    }
}
~~~

`@MatchingPasswords` được gắn trên **class**, vì cần nhìn cả hai giá trị. `@NotBlank` vẫn kiểm tra từng trường độc lập; validator liên trường sẽ tránh sinh thêm lỗi trùng cho giá trị trống.

### 3.3. Khai báo class-level constraint

~~~java
// src/main/java/com/example/demo/MatchingPasswords.java
package com.example.demo;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = MatchingPasswordsValidator.class)
public @interface MatchingPasswords {
    String message() default "Mật khẩu xác nhận không khớp";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

`message`, `groups` và `payload` là các phần tử chuẩn của một annotation Bean Validation constraint. `@Target(TYPE)` giúp quy tắc chạy trên toàn bộ `RegistrationForm`.

### 3.4. Gắn lỗi đối tượng vào trường cụ thể

~~~java
// src/main/java/com/example/demo/MatchingPasswordsValidator.java
package com.example.demo;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.util.Objects;

public final class MatchingPasswordsValidator
        implements ConstraintValidator<MatchingPasswords, RegistrationForm> {

    @Override
    public boolean isValid(
            RegistrationForm form,
            ConstraintValidatorContext context) {

        if (form == null) {
            return true; // Dùng @NotNull riêng nếu đối tượng bắt buộc tồn tại.
        }

        String password = form.getPassword();
        String confirmation = form.getConfirmPassword();

        if (password == null || confirmation == null
                || password.isBlank() || confirmation.isBlank()) {
            return true; // Để @NotBlank xử lý từng trường trống.
        }

        if (Objects.equals(password, confirmation)) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        context.buildConstraintViolationWithTemplate(
                    context.getDefaultConstraintMessageTemplate())
                .addPropertyNode("confirmPassword")
                .addConstraintViolation();

        return false;
    }
}
~~~

Cách đọc đoạn chính:

- `disableDefaultConstraintViolation()` bỏ violation mặc định ở cấp đối tượng, tránh xuất hiện đồng thời lỗi chung và lỗi trường cho cùng một lần so khớp.
- `getDefaultConstraintMessageTemplate()` tái sử dụng message khai báo trên annotation; có thể thay bằng một template/key khác.
- `addPropertyNode("confirmPassword")` **nối tên thuộc tính vào đường dẫn vi phạm**, không đổi đối tượng đang được validate và không gán lại giá trị trường.
- `addConstraintViolation()` thực sự đăng ký violation mới; `return false` báo kết quả không hợp lệ.

Với `password="abc123"` và `confirmPassword="xyz456"`, violation có `getPropertyPath().toString()` bằng **`confirmPassword`**. Nếu bỏ `addPropertyNode(...)` và để mặc định, path sẽ nằm ở root.

### 3.5. Kết nối Spring MVC và Thymeleaf

~~~java
// src/main/java/com/example/demo/DemoApplication.java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

~~~java
// src/main/java/com/example/demo/RegistrationController.java
package com.example.demo;

import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
@RequestMapping("/register")
public class RegistrationController {

    @GetMapping
    public String showForm(Model model) {
        model.addAttribute("registrationForm", new RegistrationForm());
        return "register";
    }

    @PostMapping
    public String submit(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "register";
        }
        return "redirect:/register/success";
    }

    @GetMapping("/success")
    @ResponseBody
    public String success() {
        return "Đăng ký hợp lệ";
    }
}
~~~

`BindingResult` phải đứng **ngay sau** tham số `@Valid @ModelAttribute` tương ứng để Spring cung cấp lỗi binding/validation cho model đó. Nếu đặt sai vị trí, cách xử lý lỗi có thể thay đổi hoặc lời gọi controller thất bại.

~~~html
<!-- src/main/resources/templates/register.html -->
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Đăng ký</title></head>
<body>
<form method="post" th:action="@{/register}"
      th:object="${registrationForm}">
    <label for="password">Mật khẩu</label>
    <input id="password" type="password" th:field="*{password}">
    <p th:if="${#fields.hasErrors('password')}"
       th:errors="*{password}"></p>

    <label for="confirmPassword">Xác nhận mật khẩu</label>
    <input id="confirmPassword" type="password"
           th:field="*{confirmPassword}">
    <p th:if="${#fields.hasErrors('confirmPassword')}"
       th:errors="*{confirmPassword}"></p>

    <button type="submit">Đăng ký</button>
</form>
</body>
</html>
~~~

Gửi hai giá trị khác nhau sẽ trả lại view `register`. Vì lỗi đã gắn vào `confirmPassword`, `#fields.hasErrors('confirmPassword')` là `true` và `th:errors="*{confirmPassword}"` hiển thị “Mật khẩu xác nhận không khớp” cạnh ô thứ hai. Không cần chuyển lỗi bằng mã trong controller.

### 3.6. Kiểm chứng property path bằng JUnit

~~~java
// src/test/java/com/example/demo/RegistrationValidationTest.java
package com.example.demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class RegistrationValidationTest {

    @Autowired
    Validator validator;

    @Test
    void mismatchIsReportedOnConfirmationField() {
        RegistrationForm form = new RegistrationForm();
        form.setPassword("abc123");
        form.setConfirmPassword("xyz456");

        Set<ConstraintViolation<RegistrationForm>> violations =
                validator.validate(form);

        assertEquals(1, violations.size());
        ConstraintViolation<RegistrationForm> error =
                violations.iterator().next();

        assertEquals("confirmPassword",
                error.getPropertyPath().toString());
        assertEquals("Mật khẩu xác nhận không khớp",
                error.getMessage());
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Kết quả kiểm tra cần đạt: test thành công; ở trình duyệt mở `http://localhost:8080/register`, điền hai mật khẩu khác nhau rồi gửi, thông báo xuất hiện tại trường `confirmPassword`. Không dự đoán nguyên văn log Maven vì phụ thuộc môi trường. Trong Spring MVC, có thể kiểm tra tương đương bằng `bindingResult.getFieldError("confirmPassword") != null` và `bindingResult.getGlobalErrors()` không chứa lỗi từ ràng buộc này.

## 4. Cách khác: phát sinh `FieldError` trực tiếp bằng Spring `Errors`

Khi quy tắc liên trường nằm trong một `org.springframework.validation.Validator` tự viết, hoặc bạn chủ động kiểm tra trong controller, có thể đăng ký lỗi trường trực tiếp:

~~~java
// Đoạn mã minh họa bên trong một controller/validator có form và errors:
if (form.getPassword() != null
        && form.getConfirmPassword() != null
        && !java.util.Objects.equals(
                form.getPassword(), form.getConfirmPassword())) {
    errors.rejectValue(
            "confirmPassword",
            "password.mismatch",
            "Mật khẩu xác nhận không khớp");
}
~~~

`errors` ở đây có thể là `BindingResult` hoặc interface `Errors`; phương thức `rejectValue(field, errorCode, defaultMessage)` sẽ ghi một `FieldError`. `password.mismatch` là **mã lỗi** để hệ thống messages/i18n tra cứu, còn chuỗi cuối là thông báo dự phòng. Khác với `errors.reject("password.mismatch", ...)`, vốn tạo **`ObjectError`**.

Lưu ý: đoạn trên là **phương án thay thế** cho `@MatchingPasswords`, không nên chạy cả hai logic cho cùng một quy tắc vì người dùng có thể thấy thông báo lặp. Khi có cấu trúc form và quy tắc ổn định, cách tạo property path ngay trong `ConstraintValidator` thường dễ tái sử dụng trên MVC, service và kiểm tra bằng `jakarta.validation.Validator` hơn.

**Đừng gọi `rejectValue("", ...)` hoặc truyền `null` nếu mục tiêu là một field cụ thể.** Trong root object, field rỗng có thể trở thành global error; hãy cung cấp tên field chính xác.

## 5. Đường dẫn lồng nhau, nhiều trường và danh sách

### Một field lồng nhau

Nếu class-level constraint kiểm tra toàn bộ `OrderForm` nhưng muốn trỏ vào `shippingAddress.postalCode`, hãy xây path theo từng node:

~~~java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
            "Mã bưu chính không phù hợp với quốc gia giao hàng")
        .addPropertyNode("shippingAddress")
        .addPropertyNode("postalCode")
        .addConstraintViolation();
return false;
~~~

Spring sẽ thấy tên field theo dạng `shippingAddress.postalCode` khi cấu trúc đối tượng và đường dẫn phù hợp. Với Spring `Errors` ở root, có thể dùng `errors.rejectValue("shippingAddress.postalCode", ...)`; khi `Errors` đã đặt nested path, tên field là tương đối với nested path hiện tại.

### Cần báo lỗi vào hai field

Một quy tắc “`startDate <= endDate`” có thể có ích khi thông báo ở `endDate`; trường hợp UI thật sự cần hiển thị ở **cả hai** field, tạo **hai** custom violations riêng rồi mới trả về `false`:

~~~java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate("Khoảng ngày không hợp lệ")
        .addPropertyNode("startDate")
        .addConstraintViolation();
context.buildConstraintViolationWithTemplate("Khoảng ngày không hợp lệ")
        .addPropertyNode("endDate")
        .addConstraintViolation();
return false;
~~~

Chỉ làm vậy nếu UX có lý do rõ ràng, bởi Spring sẽ lưu hai lỗi riêng. Với collection (`items[2].price`) hoặc map, Jakarta Validation có API `inIterable().atIndex(...)` / `atKey(...)` để biểu diễn phần tử chính xác; không cố nhét chuỗi chứa dấu ngoặc vuông vào một tên property node nếu API hỗ trợ các node theo cấu trúc.

## 6. Phân biệt các đối tượng lỗi và cách xử lý

| Khái niệm | Ý nghĩa | Ví dụ kiểm tra |
| --- | --- | --- |
| `ConstraintViolation#getPropertyPath()` | Đường dẫn do Jakarta Bean Validation tạo | `confirmPassword` |
| `ObjectError` | Lỗi gắn với toàn đối tượng trong Spring | `errors.getGlobalErrors()` |
| `FieldError` | Lỗi gắn với một trường trong Spring | `errors.getFieldErrors("confirmPassword")` |
| `BindingResult` | Tập lỗi binding và validation của model | `errors.hasFieldErrors("confirmPassword")` |
| `reject(...)` | Thêm global error | Quy tắc không thuộc field cụ thể |
| `rejectValue(...)` | Thêm field error | Chỉ rõ nơi người dùng cần sửa |

**Trường hợp object-level error đã tồn tại:** thêm `rejectValue` chỉ tạo **thêm** lỗi trường, không tự xóa lỗi toàn đối tượng cũ. Với class-level constraint, cách đúng là thay cách phát sinh violation như mục 3.4; với custom Spring `Validator`, gọi `rejectValue` ngay từ đầu. Nếu cần biểu diễn lại lỗi từ một hệ thống ngoài, hãy xây mô hình lỗi đầu ra có kiểm soát thay vì sửa trực tiếp danh sách lỗi của `BindingResult`.

## 7. Các lỗi thường gặp

1. **Quên `disableDefaultConstraintViolation()`:** có thể nhận đồng thời global error và field error cho một quy tắc. Nếu chủ đích chỉ báo ở một field, hãy vô hiệu hóa default trước khi thêm custom violation.
2. **Quên `addConstraintViolation()`:** chuỗi builder chưa đăng ký lỗi mới; khi default đã tắt, việc trả `false` là cấu hình violation không hợp lệ.
3. **Sai tên property:** `"confirm_password"` khác `"confirmPassword"`. Property path cần trỏ đến thuộc tính thực của đối tượng được validate; các tên lồng nhau phải phản ánh đúng cấu trúc.
4. **Đặt `@MatchingPasswords` lên một field:** `ConstraintValidator` trong ví dụ nhận cả `RegistrationForm` nên annotation phải ở cấp class. Ràng buộc field-level đã có sẵn base path là field đó.
5. **Gắn `BindingResult` sai vị trí:** trong Spring MVC, tham số `BindingResult`/`Errors` phải theo ngay sau tham số model mà nó nhận lỗi.
6. **Thiếu Validation provider hoặc nhầm `javax`/`jakarta`:** Spring Boot 3 dùng Jakarta; cần dependency validation có provider. `@Valid` một mình không đủ khi validation chưa được cấu hình.
7. **Kiểm tra trùng khi trường trống:** nếu vừa có `@NotBlank` vừa so khớp mật khẩu, quyết định rõ có muốn hiển thị cả hai lỗi không. Ví dụ chọn bỏ qua so khớp khi một trường trống.
8. **Hiển thị toàn bộ lỗi như JSON:** `FieldError` có thể mang rejected value; không trả/lưu log thô các giá trị nhạy cảm như mật khẩu. Chỉ cung cấp field, mã lỗi và thông điệp phù hợp cho client.
9. **Lầm tưởng class-level constraint luôn là global:** class-level mô tả *phạm vi dữ liệu được xét*; property path mô tả *nơi gắn thông báo*. Hai quyết định độc lập khi dùng custom violation.

## 8. Checklist áp dụng thực tế

- Xác định rõ field người dùng nên sửa; ưu tiên field có thể hành động được.
- Nếu sử dụng Jakarta Bean Validation, đặt constraint ở class khi cần nhiều giá trị; trong validator, tắt default và thêm `addPropertyNode(...).addConstraintViolation()`.
- Nếu sử dụng Spring `Validator` hoặc kiểm tra thủ công, dùng `rejectValue` để phát sinh `FieldError` ngay từ đầu.
- Đảm bảo tên field/path có thật, dữ liệu lồng nhau được xử lý đúng, và biểu mẫu gắn `@Valid` với `BindingResult` đúng vị trí.
- Kiểm tra trường hợp hợp lệ, không hợp lệ, null/rỗng, UI thông báo cạnh field, và không sinh lỗi lặp hay lộ giá trị nhạy cảm.

## Tài liệu tham khảo

- Jakarta Validation `ConstraintValidatorContext` và cách thêm property node: https://jakarta.ee/specifications/platform/10/apidocs/jakarta/validation/constraintvalidatorcontext
- Hibernate Validator Reference Guide, phần custom property paths: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#section-custom-property-paths
- Spring `Errors`/`BindingResult` và `rejectValue`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html
