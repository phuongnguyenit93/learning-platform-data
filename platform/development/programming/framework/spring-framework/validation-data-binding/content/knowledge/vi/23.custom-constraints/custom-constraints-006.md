# ConstraintValidatorContext và tạo thông báo tùy chỉnh

## 1. Mục tiêu và vị trí trong Spring Validation

Khi viết một ràng buộc Bean Validation riêng (custom constraint), phương thức `ConstraintValidator#isValid(...)` quyết định dữ liệu hợp lệ hay không. Tham số `ConstraintValidatorContext` cho phép điều khiển **thông báo lỗi**, **số lượng lỗi** và **đường dẫn (property path) nơi lỗi được gắn vào**. Đây là công cụ hữu ích cho quy tắc phụ thuộc nhiều trường, ví dụ mật khẩu và xác nhận mật khẩu phải khớp nhau.

Luồng xử lý thường gặp:

1. Lớp dữ liệu (DTO/record/bean) được gắn annotation constraint, ví dụ `@PasswordMatches`.
2. Spring kích hoạt Jakarta Bean Validation khi tham số được đánh dấu `@Valid` hoặc `@Validated`, hoặc khi ứng dụng gọi `jakarta.validation.Validator#validate`.
3. Provider (thường là Hibernate Validator trong Spring Boot) gọi `isValid(value, context)`.
4. Nếu trả về `false`, provider tạo một hoặc nhiều `ConstraintViolation` từ thông báo mặc định và/hoặc các builder tùy chỉnh.
5. Spring MVC chuyển vi phạm thành lỗi binding/validation hoặc phản hồi HTTP 400 tùy cách controller xử lý.

**Phân biệt:** `jakarta.validation.ConstraintValidator` và `jakarta.validation.Validator` thuộc Jakarta Validation; `org.springframework.validation.Validator` là giao diện khác, dùng `Errors.reject(...)`/`rejectValue(...)`. `ConstraintValidatorContext` thuộc cơ chế thứ nhất. Trong Spring Boot 3+ dùng import `jakarta.validation.*`, không dùng `javax.validation.*` của thế hệ cũ.

## 2. API quan trọng của ConstraintValidatorContext

| API | Vai trò | Khi dùng |
| --- | --- | --- |
| `getDefaultConstraintMessageTemplate()` | Lấy mẫu thông báo chưa được nội suy từ thuộc tính `message` của annotation. | Muốn giữ thông báo do người dùng annotation cấu hình, nhưng gắn nó vào trường khác. |
| `disableDefaultConstraintViolation()` | Không tạo thêm vi phạm mặc định của annotation. | Muốn thay thế lỗi cấp object bằng lỗi cụ thể ở một field hoặc nhiều lỗi riêng biệt. |
| `buildConstraintViolationWithTemplate(String)` | Bắt đầu định nghĩa một vi phạm với thông báo mới hoặc khóa i18n. | Muốn thay câu chữ, thêm ngữ cảnh, hoặc xây đường dẫn khác. |
| `addPropertyNode("fieldName")` | Nối một property vào đường dẫn lỗi hiện tại. | Với constraint cấp class, gắn lỗi vào field như `confirmPassword`. |
| `addBeanNode()` | Nối bean node vào đường dẫn; dùng trong cấu trúc object/container sâu. | Khi cần trỏ đến chính bean con thay vì một thuộc tính. |
| `addConstraintViolation()` | **Kết thúc builder và đăng ký vi phạm**. | Bắt buộc cho mỗi vi phạm tùy chỉnh muốn tạo. |

Các phương thức như `addContainerElementNode(...)`, `inIterable().atIndex(...)` và `inIterable().atKey(...)` phục vụ đường dẫn đến phần tử list/map. `addParameterNode(index)` chỉ dành cho cross-parameter constraint của method/constructor, không dùng tùy tiện cho DTO thông thường.

Ví dụ ngắn khi quy tắc đặt ở **cấp class**:

~~~java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        context.getDefaultConstraintMessageTemplate())
    .addPropertyNode("confirmPassword")
    .addConstraintViolation();
return false;
~~~

Nếu không gọi `addPropertyNode(...)`, lỗi class-level thường nằm ở đường dẫn rỗng (lỗi toàn object). Khi thêm node `confirmPassword`, `ConstraintViolation#getPropertyPath()` trở thành `confirmPassword`, giúp Spring hoặc giao diện người dùng chỉ ra ô nhập tương ứng.

## 3. Ba cách tạo thông báo lỗi

**Cách A — dùng thông báo annotation mặc định.** Nếu `isValid` trả `false` mà không gọi phương thức nào trên context, Bean Validation tạo một vi phạm theo `message` của annotation, tại chính phần tử đang được kiểm tra.

~~~java
@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    return value == null || value.startsWith("SPR-");
}
~~~

Ở đây đoạn code chỉ minh họa thân validator cho một constraint cấp field. Với annotation `message = "Mã phải bắt đầu bằng SPR-"`, vi phạm dùng chính thông báo đó.

**Cách B — thay thông báo nhưng giữ nguyên path.** Dùng builder và tắt lỗi mặc định:

~~~java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate("Mã không đúng định dạng đang hỗ trợ")
    .addConstraintViolation();
return false;
~~~

**Cách C — tùy chỉnh cả thông báo và path.** Với constraint trên DTO, thêm `addPropertyNode(...)` trước `addConstraintViolation()`. Đây là cách thường dùng để thông báo lỗi kiểm tra hai field xuất hiện bên cạnh field cần sửa.

Lưu ý: `disableDefaultConstraintViolation()` không tự tạo lỗi mới. Nếu trả `false` sau khi đã tắt lỗi mặc định mà không hoàn thành ít nhất một builder với `addConstraintViolation()`, provider không có vi phạm hợp lệ để báo và có thể ném `ValidationException`. Nếu không tắt lỗi mặc định, một lỗi tùy chỉnh có thể xuất hiện **cùng** lỗi mặc định, gây trùng thông báo.

## 4. Ví dụ đầy đủ: xác nhận mật khẩu phải khớp

Ví dụ dùng **Java 17+**, Spring Boot 3+ hoặc phiên bản mới tương thích Jakarta Validation. Trong một dự án Spring Boot đã cấu hình Maven, thêm dependency sau nếu chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đặt chương trình sau tại `src/main/java/com/example/validation/ValidationDemoApplication.java`. Đây là một file Java hoàn chỉnh: annotation, validator, record dữ liệu và điểm chạy `main` đều nằm trong file.

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Comparator;
import java.util.Objects;

@SpringBootApplication
public class ValidationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showValidation(Validator validator) {
        return args -> validator.validate(
                        new Registration("abc123", "xyz456"))
                .stream()
                .sorted(Comparator.comparing(
                        violation -> violation.getPropertyPath().toString()))
                .forEach(violation -> System.out.println(
                        violation.getPropertyPath() + ": "
                                + violation.getMessage()));
    }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = PasswordMatchesValidator.class)
    public @interface PasswordMatches {
        String message() default "Mật khẩu xác nhận không trùng khớp";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    public static final class PasswordMatchesValidator
            implements ConstraintValidator<PasswordMatches, Registration> {

        @Override
        public boolean isValid(
                Registration value, ConstraintValidatorContext context) {
            // Để @NotBlank xử lý null/blank; tránh lỗi chồng chéo.
            if (value == null
                    || value.password() == null
                    || value.confirmPassword() == null
                    || value.password().isBlank()
                    || value.confirmPassword().isBlank()) {
                return true;
            }

            if (Objects.equals(
                    value.password(), value.confirmPassword())) {
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

    @PasswordMatches
    public record Registration(
            @NotBlank String password,
            @NotBlank String confirmPassword) {
    }
}
~~~

Chạy từ thư mục dự án Spring Boot có Maven wrapper bằng `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`), hoặc `mvn spring-boot:run` khi Maven đã cài. Ngoài log khởi động, chương trình in chính xác dòng do `showValidation` tạo:

~~~text
confirmPassword: Mật khẩu xác nhận không trùng khớp
~~~

Giải thích từng phần:

- `@Target(ElementType.TYPE)` xác định constraint dùng cho class/record vì cần so sánh **hai** field. `@Retention(RUNTIME)` cho phép runtime đọc annotation.
- `@Constraint(validatedBy = PasswordMatchesValidator.class)` liên kết annotation với validator; ba thuộc tính chuẩn `message`, `groups`, `payload` là thành phần cần có của custom constraint.
- Kiểu được kiểm tra trong `ConstraintValidator<PasswordMatches, Registration>` khớp với record gắn annotation. `isValid` được provider gọi, không cần gọi trực tiếp.
- Khi một trường rỗng, `@NotBlank` chịu trách nhiệm báo lỗi riêng. Constraint class-level tạm coi hợp lệ để tránh tạo thông báo thứ hai gây nhiễu.
- Khi cả hai giá trị có nội dung nhưng khác nhau, validator tắt vi phạm cấp class rồi dựng vi phạm tại `confirmPassword`. Kết quả là **một lỗi thuộc đúng field**, dù annotation đặt trên toàn record.
- `getDefaultConstraintMessageTemplate()` giữ cách cấu hình `message` của annotation. Nếu sau này thay thông báo trong annotation hoặc dùng resource bundle, validator không phải sửa.
- `Validator#validate(...)` trả `Set<ConstraintViolation<Registration>>`. Một set **không bảo đảm thứ tự**; ví dụ dùng `sorted(...)` trước khi in để kết quả dễ đọc. Với dữ liệu mẫu chỉ có một lỗi.

Trường hợp thay `confirmPassword` thành `"abc123"` sẽ không tạo vi phạm nào. Trường hợp `confirmPassword` rỗng thì `@NotBlank` tạo lỗi tại field đó, còn `PasswordMatchesValidator` bỏ qua kiểm tra ghép cặp.

## 5. Tạo nhiều lỗi từ một lần kiểm tra

Một class-level validator có thể báo nhiều lý do khác nhau, miễn là mỗi builder kết thúc bằng `addConstraintViolation()`. Đoạn sau chỉ minh họa **phần logic bên trong `isValid`** của một DTO có các thuộc tính `start`/`end`; không phải chương trình độc lập:

~~~java
boolean missingStart = value.start() == null;
boolean missingEnd = value.end() == null;

if (!missingStart && !missingEnd) {
    return true;
}

context.disableDefaultConstraintViolation();

if (missingStart) {
    context.buildConstraintViolationWithTemplate(
            "Cần nhập ngày bắt đầu")
        .addPropertyNode("start")
        .addConstraintViolation();
}

if (missingEnd) {
    context.buildConstraintViolationWithTemplate(
            "Cần nhập ngày kết thúc")
        .addPropertyNode("end")
        .addConstraintViolation();
}

return false;
~~~

Nếu thiếu cả hai giá trị, kết quả có **hai** vi phạm, một path `start` và một path `end`. Trong thực tế, nếu chỉ cần kiểm tra khác `null`, hãy ưu tiên `@NotNull` đặt trên từng field; dùng class-level context khi quy tắc cần xét **quan hệ** giữa các trường hoặc tạo đường dẫn động theo logic nghiệp vụ.

Với thuộc tính lồng nhau, từ class-level constraint có thể tạo path `address.postalCode` bằng:

~~~java
context.buildConstraintViolationWithTemplate("Mã bưu chính không hợp lệ")
    .addPropertyNode("address")
    .addPropertyNode("postalCode")
    .addConstraintViolation();
~~~

Tên node phải đúng cấu trúc model. Đối với constraint đã đặt trên một property, builder **nối thêm** node vào path đang có; đừng giả định mọi path đều bắt đầu từ root. Với list/map, nên dùng API container/iterable tương ứng để lưu index/key đúng ngữ nghĩa.

## 6. Kết nối với Spring MVC và xử lý phản hồi

Giả sử ứng dụng đã có thêm `spring-boot-starter-web`, một controller có thể nhận dữ liệu bằng `@Valid @RequestBody`:

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.Objects;

@RestController
@RequestMapping("/registrations")
class RegistrationController {

    @PostMapping
    ResponseEntity<?> create(
            @Valid @RequestBody ValidationDemoApplication.Registration input,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            var details = bindingResult.getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "message", Objects.toString(
                                    error.getDefaultMessage(), "")))
                    .toList();
            return ResponseEntity.badRequest().body(details);
        }

        return ResponseEntity.ok(Map.of("status", "accepted"));
    }
}
~~~

Với request:

~~~json
{
  "password": "abc123",
  "confirmPassword": "xyz456"
}
~~~

Response 400 do controller trên tạo:

~~~json
[
  {
    "field": "confirmPassword",
    "message": "Mật khẩu xác nhận không trùng khớp"
  }
]
~~~

Đặt `BindingResult` **ngay sau** tham số `@Valid @RequestBody`. Nếu không tự nhận `BindingResult` và không có cơ chế method validation đặc biệt khác, Spring MVC thường ném `MethodArgumentNotValidException` khi đối tượng request không hợp lệ và trả HTTP 400 theo cơ chế mặc định. Nếu áp dụng validation trên nhiều tham số/phương thức, có thể gặp `HandlerMethodValidationException`; cơ chế xử lý phải tính đến kiểu validation đang sử dụng.

Sự khác biệt quan trọng giữa đường dẫn lỗi:

- Lỗi cấp property (ví dụ `confirmPassword`) thường được ánh xạ thành `FieldError`, truy cập qua `bindingResult.getFieldErrors()`.
- Lỗi cấp object không có property node thường thành `ObjectError`/global error, xem bằng `bindingResult.getGlobalErrors()` hoặc `getAllErrors()`. Controller chỉ lấy field errors như ví dụ sẽ không thấy các lỗi global này.
- `ConstraintValidatorContext` tạo **vi phạm validation**, không tự quyết định mã HTTP, định dạng JSON hay bản dịch phía giao diện. Các việc đó thuộc tầng Spring MVC và ứng dụng.

## 7. Nội suy thông báo và đa ngôn ngữ

Chuỗi truyền vào `buildConstraintViolationWithTemplate(...)` là **template**, không nhất thiết là thông báo hiển thị cuối cùng. Jakarta Validation sẽ nội suy template theo cấu hình provider và message interpolator.

Có thể đổi thuộc tính annotation thành:

~~~java
String message() default "{registration.password.mismatch}";
~~~

Định nghĩa file `src/main/resources/ValidationMessages.properties`:

~~~properties
registration.password.mismatch=Confirmation password does not match
~~~

Và bản tiếng Việt trong `src/main/resources/ValidationMessages_vi.properties`:

~~~properties
registration.password.mismatch=Mật khẩu xác nhận không trùng khớp
~~~

Validator tiếp tục dùng:

~~~java
context.buildConstraintViolationWithTemplate(
        context.getDefaultConstraintMessageTemplate())
    .addPropertyNode("confirmPassword")
    .addConstraintViolation();
~~~

Khi provider chọn locale tiếng Việt, `ConstraintViolation#getMessage()` chứa câu đã nội suy; `getMessageTemplate()` giữ template ban đầu. Locale cụ thể phụ thuộc cấu hình message interpolator/provider và cách ứng dụng quản lý locale; không nên giả định locale HTTP tự động được áp dụng cho mọi lượt validate chạy ngoài web request.

Một số template có thể dùng tham số của annotation, chẳng hạn `{min}` trong constraint có thuộc tính `min`. Tránh ghép trực tiếp nội dung không tin cậy của người dùng vào template: nó có thể dẫn đến thông báo khó kiểm soát hoặc thay đổi nghĩa của cú pháp nội suy. Nếu cần nội dung thay đổi theo dữ liệu, hãy chọn câu chữ an toàn hoặc xử lý tham số/escape theo cơ chế provider hỗ trợ. Không nên dựa vào API mở rộng riêng của Hibernate Validator khi chỉ cần Jakarta Validation tiêu chuẩn.

## 8. Kiểm thử hành vi và lỗi thường gặp

Kiểm thử cần xác nhận **cả nội dung thông báo lẫn property path**. Ví dụ JUnit 5 trong dự án Spring Boot có `spring-boot-starter-test`:

~~~java
package com.example.validation;

import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class PasswordMatchesTest {
    @Autowired
    Validator validator;

    @Test
    void mismatchIsAttachedToConfirmationField() {
        var input = new ValidationDemoApplication.Registration(
                "abc123", "xyz456");

        var violations = validator.validate(input);

        assertEquals(1, violations.size());
        var violation = violations.iterator().next();
        assertEquals("confirmPassword",
                violation.getPropertyPath().toString());
        assertEquals("Mật khẩu xác nhận không trùng khớp",
                violation.getMessage());
    }

    @Test
    void matchingPasswordsHaveNoViolations() {
        var input = new ValidationDemoApplication.Registration(
                "abc123", "abc123");
        assertEquals(0, validator.validate(input).size());
    }
}
~~~

Chạy `./mvnw test` (Windows: `mvnw.cmd test`) trong dự án đã có dependency test và cấu hình Spring Boot hợp lệ.

Các lỗi phổ biến cần tránh:

1. **Quên `addConstraintViolation()`:** builder chưa tạo vi phạm; hãy kết thúc mỗi nhánh báo lỗi.
2. **Tắt default nhưng không thêm lỗi:** `isValid` trả `false` khi không có vi phạm là trạng thái không hợp lệ.
3. **Không tắt default khi muốn thay thế:** nhận hai thông báo (mặc định và tùy chỉnh) cho cùng một nguyên nhân.
4. **Gắn sai cấp annotation/path:** constraint cấp class không tự trở thành field error; cần `addPropertyNode(...)` nếu muốn lỗi ở field.
5. **Dùng `@Valid` trên đối tượng nhưng thiếu provider/dependency:** annotation không đủ nếu ứng dụng chưa cấu hình Bean Validation; trong Spring Boot dùng starter validation.
6. **Nhầm `javax.validation` với `jakarta.validation`:** Spring Boot 3+ dùng namespace Jakarta; tránh trộn hai thế hệ thư viện.
7. **Lấy mỗi `getFieldErrors()` nhưng lỗi là global:** dùng `getAllErrors()`/`getGlobalErrors()` hoặc sửa path cho đúng ý định.
8. **Dùng kiểu dữ liệu sai hoặc giả định thứ tự violation:** kiểu generics của `ConstraintValidator<A,T>` phải khớp đối tượng, và `Set<ConstraintViolation<?>>` không hứa thứ tự.
9. **Validator có side effect hoặc dữ liệu chia sẻ không an toàn:** `isValid` nên kiểm tra và xây lỗi một cách ổn định; instance validator có thể được provider tái sử dụng, nên tránh trạng thái mutable theo request.
10. **Coi client validation là đủ:** quy tắc ở server vẫn cần chạy, đặc biệt với quan hệ nhiều trường và dữ liệu nghiệp vụ.

### Checklist áp dụng nhanh

- Annotation có `@Constraint`, `@Target`, `@Retention(RUNTIME)` và ba thuộc tính `message/groups/payload`.
- Validator xử lý `null`/blank có chủ đích, có đúng kiểu dữ liệu, trả `true/false` theo quy tắc.
- Khi cần thay thông báo, gọi `disableDefaultConstraintViolation()` và tạo đầy đủ ít nhất một custom violation.
- Khi cần lỗi ở field cụ thể, thêm `addPropertyNode("tênField")`; khi cần nhiều lỗi, dùng một builder mới cho từng lỗi.
- Kiểm thử `propertyPath`, `message`, trường hợp hợp lệ và trường hợp dữ liệu thiếu; nếu tích hợp MVC thì kiểm tra cả HTTP response.

## Tài liệu tham khảo

- Jakarta Validation API — `ConstraintValidatorContext`: https://jakarta.ee/specifications/platform/10/apidocs/jakarta/validation/constraintvalidatorcontext
- Jakarta Validation API — `ConstraintViolationBuilder`: https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.1.1/jakarta/validation/ConstraintValidatorContext.ConstraintViolationBuilder.html
- Spring Framework — `@RequestBody` và xử lý validation: https://docs.spring.io/spring/reference/7.1/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — MVC validation: https://docs.spring.io/spring-framework/reference/7.1/web/webmvc/mvc-controller/ann-validation.html
