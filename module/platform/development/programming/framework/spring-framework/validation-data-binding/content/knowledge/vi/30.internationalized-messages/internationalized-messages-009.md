# Phân biệt mã lỗi ổn định với thông báo đã dịch trong Spring Validation

## 1. Vì sao một API cần cả `code` lẫn `message`?

Một ứng dụng Spring MVC phục vụ nhiều ngôn ngữ cần giải quyết **hai nhiệm vụ khác nhau** khi dữ liệu không hợp lệ:

1. Cung cấp **định danh lỗi mà client có thể xử lý ổn định**, ví dụ `NAME_REQUIRED`, `EMAIL_INVALID`, `AGE_TOO_YOUNG` hoặc `INVALID_TYPE`.
2. Cung cấp **câu thông báo dễ đọc bằng ngôn ngữ của người dùng**, ví dụ “Name is required” hoặc “Tên không được để trống”.

Hai phần không nên đồng nhất. Mã lỗi thuộc **hợp đồng giữa client và server**; thông báo thuộc **lớp trình bày, có thể nội suy và dịch thuật**. Một bản cập nhật cách diễn đạt, đổi ngôn ngữ, sửa dấu câu hoặc thêm tham số nội suy không nên buộc frontend phải thay đổi nhánh xử lý lỗi.

Ví dụ cùng một lỗi:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "name",
      "code": "NAME_REQUIRED",
      "message": "Name is required"
    }
  ]
}
```

Với người dùng tiếng Việt:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "name",
      "code": "NAME_REQUIRED",
      "message": "Tên không được để trống"
    }
  ]
}
```

**Bất biến:** `VALIDATION_FAILED` và `NAME_REQUIRED` giữ nguyên. **Thay đổi:** chuỗi `message` phụ thuộc `Locale`, tài nguyên dịch và cách ứng dụng chọn câu chữ. Client nên dùng `code` để quyết định hiển thị trạng thái, điều hướng hoặc yêu cầu thao tác; `message` để hiển thị cho con người.

Bài học nằm trong chủ đề **Thông báo đa ngữ** của Spring Framework validation/data binding, tập trung vào **Spring `MessageSource`**, `Errors`/`BindingResult`, `FieldError`, `MessageCodesResolver`, Jakarta Validation và thiết kế mã API ổn định. Ví dụ chạy bằng **Java 17, Spring Boot 3.x / Spring Framework 6.x và MockMvc**.

## 2. Ba lớp “mã lỗi” dễ bị nhầm lẫn

Trong Spring, chữ “code” có thể chỉ **ba loại dữ liệu khác nhau**:

| Lớp | Ví dụ | Ai sở hữu | Có nên dùng trực tiếp làm mã API vĩnh viễn? |
| --- | --- | --- | --- |
| **Mã lỗi nghiệp vụ/API** | `NAME_REQUIRED` | Ứng dụng định nghĩa và quản lý version | **Có**, nếu công bố trong API contract |
| **Mã tra cứu message của Spring** | `NotBlank.signup.name`, `NotBlank.name`, `NotBlank` | `DefaultMessageCodesResolver`, object name và validator | Không nên phụ thuộc trực tiếp |
| **Thông báo đã nội suy** | `Tên không được để trống` | `MessageSource`, `Locale`, provider validation | **Không**, vì nội dung có thể đổi |

Một lỗi `@NotBlank` trên field `name` của model attribute tên `signup` có thể cung cấp mảng mã tra cứu theo mức độ cụ thể:

```text
NotBlank.signup.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
```

Đây là ví dụ theo **DefaultMessageCodesResolver** và kiểu field String. Thứ tự/số mã có thể thay đổi theo cách tạo lỗi, object name, field path, kiểu property hoặc MessageCodesResolver đã tùy biến. Spring dùng các mã ấy để **tìm message**, không mặc nhiên hứa rằng mã đứng đầu là định danh public bất biến.

### Điểm thường bị hiểu nhầm: FieldError#getCode()

`ObjectError#getCode()` thường trả **mã đầu tiên** từ mảng `getCodes()`. Với lỗi nêu trên, đó có thể là `NotBlank.signup.name`, chứ **không nhất thiết** là `NotBlank`. Vì thế hai lỗi cùng constraint `@NotBlank` nhưng model attribute khác tên có thể cho `getCode()` khác nhau.

Ví dụ:

```java
String firstCode = fieldError.getCode();
String[] candidates = fieldError.getCodes();
String defaultText = fieldError.getDefaultMessage();
```

Đây là fragment, biến `fieldError` được cung cấp trong handler/validator. Ý nghĩa:

- `getCode()`: một mã tra cứu ưu tiên, thường cụ thể theo object/field.
- `getCodes()`: các mã tra cứu theo thứ tự cho `MessageSource`.
- `getDefaultMessage()`: thông điệp dự phòng đã được lưu trong error object; với Jakarta Validation nó có thể là câu đã nội suy ở lúc validate.
- **Không field nào trong ba field trên tự bảo đảm là “API error code ổn định”**. Nếu muốn hợp đồng công khai, phải định nghĩa một lớp mapping riêng hoặc sử dụng các mã thuộc quyền sở hữu ứng dụng và kiểm soát tác động khi refactor.

## 3. MessageSource dùng code để lấy câu chữ theo Locale

`org.springframework.context.MessageSource` có các dạng tra cứu thường dùng:

```java
// Message key + arguments + locale:
String text = messageSource.getMessage(
        "api.error.NAME_REQUIRED",
        null,
        locale
);

// Có fallback tường minh nếu key chưa tồn tại:
String safeText = messageSource.getMessage(
        "api.error.NAME_REQUIRED",
        null,
        "Invalid field",
        locale
);

// Trực tiếp nhận Spring MessageSourceResolvable:
String resolved = messageSource.getMessage(
        fieldError, locale
);
```

Đây là **fragment**. Ba lời gọi có mục đích khác nhau:

1. Tra cứu key **được ứng dụng quy định**: hữu ích để giữ message có thể dịch nhưng mã API không đổi.
2. Tra cứu cùng key với **default message an toàn** nếu bản dịch chưa được thêm.
3. Dùng trực tiếp danh sách `FieldError#getCodes()` và default message để lấy thông điệp của validation framework; phù hợp rendering form hoặc những nơi chấp nhận quy tắc message-code của Spring.

**Chọn hướng nào?** Có thể dùng cả hai, nhưng khi thiết kế API dài hạn nên xác định ranh giới:

- **Public code**: tên ổn định như `NAME_REQUIRED`, được client biết.
- **Internal lookup key**: tên resource bundle như `api.error.NAME_REQUIRED`; có thể giữ tương ứng 1–1 để dễ quản trị, nhưng không nên bắt client gửi key đó.
- **Localized text**: kết quả từ `MessageSource` với một `Locale` xác định.

### MessageSourceResolvable và DefaultMessageCodesResolver

`FieldError` implement `MessageSourceResolvable` thông qua `ObjectError`. `MessageSource#getMessage(resolvable, locale)` kiểm tra các candidate codes theo thứ tự, rồi dùng default message nếu không có mã nào tìm được. Mặc định Spring có thể tạo nhiều mã với độ cụ thể giảm dần, ví dụ:

```text
typeMismatch.signup.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
```

Cơ chế này hữu ích để viết thông điệp chung cho lỗi chuyển kiểu hoặc thông điệp riêng cho từng field. Nhưng nếu thay tên command object từ `signup` sang `registration`, mã đầu tiên có thể thay đổi, dù lỗi nghiệp vụ vẫn là **“tuổi không đúng kiểu”**. Mapping API sang `INVALID_TYPE` giúp tránh coupling đó.

**Không dùng câu đã dịch để suy ngược lỗi**:

```java
// Anti-pattern:
if ("Name is required".equals(fieldError.getDefaultMessage())) {
    // ...
}
```

Khi locale đổi sang tiếng Việt, khi dịch thay đổi hoặc khi annotation message được cập nhật, nhánh code này hỏng. Hãy dựa vào metadata constraint/binding, mã nội bộ có kiểm soát hoặc error code được định nghĩa ở lớp nghiệp vụ.

## 4. Mã nguồn lỗi không phải lúc nào cũng cùng một exception

Trong Spring MVC, lỗi đầu vào xuất hiện ở nhiều giai đoạn:

| Nguồn lỗi | Ví dụ | Dấu hiệu Spring | Mã API gợi ý |
| --- | --- | --- | --- |
| Property binding/type conversion | `age=abc` cho `Integer age` | `FieldError.isBindingFailure() == true` | `INVALID_TYPE` |
| Jakarta constraint trên model | `@NotBlank` với name rỗng | `FieldError.getCodes()` có thể chứa `NotBlank` | `NAME_REQUIRED` |
| Jakarta constraint trên model | `@Min(18)` với age=16 | Candidate code `Min` | `AGE_TOO_YOUNG` |
| Spring custom `Validator` | Tên `admin` bị đặt trước | `rejectValue("name","signup.name.reserved")` | `NAME_RESERVED` |
| Field ngoài allowlist | `role=ADMIN` khi `setAllowedFields` cấm | `BindingResult#getSuppressedFields()` | `DISALLOWED_FIELDS` |
| JSON sai cú pháp | `{"age":,}` | `HttpMessageNotReadableException` | `REQUEST_BODY_UNREADABLE` |
| Lỗi method validation | Direct `@Min` trên `@RequestParam` | Có thể `HandlerMethodValidationException` | `METHOD_VALIDATION_FAILED` |
| Nghiệp vụ tại service | Trùng email trong DB | Exception/kết quả service riêng | `EMAIL_ALREADY_EXISTS` |

Bảng là **gợi ý thiết kế API**, không phải bộ tên mã có sẵn của Spring. Mã phải được ứng dụng tài liệu hóa; đừng xem bất kỳ ví dụ `NAME_REQUIRED` nào là built-in constant.

**Đặc biệt**: lỗi syntax JSON không nhất thiết đi qua cùng `BindingResult` của `@ModelAttribute`. Một endpoint `@RequestBody` cần handler lỗi converter tương ứng. Đừng gom mọi HTTP 400 thành lỗi “NotBlank” hoặc chờ `MessageSource` tự phân biệt chúng.

## 5. Thiết kế hợp đồng lỗi ổn định theo thời gian

Một thiết kế hữu ích gồm ba trường hợp:

1. **Mã cấp request**: `VALIDATION_FAILED` cho nhóm field validation; hoặc `REQUEST_BODY_UNREADABLE` cho body không đọc được.
2. **Mã cấp field**: `NAME_REQUIRED`, `EMAIL_INVALID`, `INVALID_TYPE`; chỉ xuất `field` khi lỗi thực sự liên quan một property.
3. **Message đã dịch**: ngắn gọn, có thể được người dùng hiểu, không lộ implementation detail.

Ví dụ:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Some submitted values are invalid",
  "errors": [
    {
      "field": "age",
      "code": "AGE_TOO_YOUNG",
      "message": "Age must be at least 18"
    }
  ]
}
```

Với tiếng Việt:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Một số giá trị gửi lên không hợp lệ",
  "errors": [
    {
      "field": "age",
      "code": "AGE_TOO_YOUNG",
      "message": "Tuổi phải từ 18 trở lên"
    }
  ]
}
```

Không dùng HTTP status làm mã nghiệp vụ duy nhất. Hai lỗi có thể cùng HTTP **400 Bad Request** nhưng đòi client sửa khác nhau. Ngược lại, một mã nghiệp vụ có thể xuất hiện với một status đã được hợp đồng hóa; nếu đổi status, phải xem tác động đến client, cache, retry và monitoring.

### Các đặc tính của mã API tốt

- **Ổn định** qua các ngôn ngữ và các lần sửa message.
- **Đủ cụ thể** để frontend phân loại và hỗ trợ người dùng.
- **Không lộ** tên class, stack trace, tên bảng nội bộ, email hoặc rejected values.
- **Có thể tài liệu hóa** bằng bảng code → ý nghĩa → cách sửa.
- **Không phụ thuộc** tên method controller, tên JavaBean, thứ tự nội bộ của `DefaultMessageCodesResolver`.
- **Thống nhất** giữa frontend, backend và logging/tracing.
- Có fallback không gây vỡ client cho lỗi lạ, ví dụ `INVALID_FIELD` hoặc `VALIDATION_FAILED`.

### Không nên làm

- Client viết `if (error.message === "Email is invalid")`.
- Server trả `getDefaultMessage()` làm trường `code`.
- Server trả một mã `typeMismatch.signup.age` làm hợp đồng public mà không có chính sách versioning.
- Server serializes nguyên `FieldError` hay `ConstraintViolation` vào HTTP response.
- Server thay `NAME_REQUIRED` thành `TEN_BAT_BUOC` vì giao diện chuyển sang tiếng Việt.
- Mỗi endpoint tự sáng tạo một lỗi mới cho cùng một quy tắc và khiến client phải viết nhiều nhánh không cần thiết.

## 6. Ví dụ Java 17 hoàn chỉnh: một mã, hai ngôn ngữ

Ta xây Spring Boot MVC ứng dụng có endpoint:

`POST /signups` với input `application/x-www-form-urlencoded`, các trường `name`, `email` và `age`.

Các yêu cầu:

- `name` không được rỗng; tên `admin` bị dành riêng bởi một Spring `Validator`.
- `email` không được rỗng và phải giống định dạng email.
- `age` bắt buộc là số nguyên và ít nhất 18.
- `role` không được bind từ request dù DTO cố ý có setter, để minh họa xử lý suppressed fields.
- `Accept-Language: en` / `Accept-Language: vi` thay đổi các thông báo.
- `code` ở cấp request và field **không thay đổi theo locale**.
- Các lỗi được sắp xếp để response/tests ổn định, không phụ thuộc thứ tự validator trả về.

Chúng ta cố ý chọn **form-urlencoded / @ModelAttribute** để quan sát cả `BindingResult`, custom Spring Validator và `getSuppressedFields()`. Với JSON `@RequestBody`, pipeline chuyển đổi khác; phần 11 sẽ chỉ rõ giới hạn này.

### 6.1. Cấu trúc project

```text
stable-error-code-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── StableCodeApplication.java
    │   │   ├── SignupForm.java
    │   │   ├── SignupNameValidator.java
    │   │   └── SignupController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── messages.properties
    │       └── messages_vi.properties
    └── test/java/demo/
        └── SignupLocalizationTest.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>stable-error-code-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
```

`spring-boot-starter-validation` bổ sung Jakarta Bean Validation provider. Không nên mặc định `spring-boot-starter-web` luôn đủ cho Bean Validation trong mọi thế hệ Spring Boot.

### 6.3. src/main/java/demo/StableCodeApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StableCodeApplication {
    public static void main(String[] args) {
        SpringApplication.run(StableCodeApplication.class, args);
    }
}
```

Main class ở package `demo` để quét controller. Không cần tạo `MessageSource` thủ công trong ví dụ vì Spring Boot tự cấu hình từ `messages.properties` ở classpath root.

### 6.4. src/main/java/demo/SignupForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank(message = "{signup.name.required}")
    private String name;

    @NotBlank(message = "{signup.email.required}")
    @Email(message = "{signup.email.invalid}")
    private String email;

    @NotNull(message = "{signup.age.required}")
    @Min(value = 18, message = "{signup.age.min}")
    private Integer age;

    // Trường nhạy cảm có setter chỉ để minh họa chống mass assignment.
    private String role = "USER";

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
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

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }
}
```

Annotation `@NotBlank`, `@Email`, `@NotNull`, `@Min` tạo ra những constraint thuộc Jakarta Validation. Phần `message = "{signup.name.required}"` là **khóa nội suy message** của validator, **không phải mã API**.

Trong một Spring Boot application có validation provider và `MessageSource` đúng cấu hình, Spring có thể tích hợp message bundles vào Bean Validation interpolation. Nhưng ngay cả khi thông điệp mặc định từ validator đã được nội suy, endpoint demo **không sử dụng nguyên văn thông điệp đó làm định danh lỗi**.

### 6.5. src/main/java/demo/SignupNameValidator.java

```java
package demo;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class SignupNameValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;

        if ("admin".equalsIgnoreCase(form.getName())) {
            errors.rejectValue(
                    "name",
                    "signup.name.reserved",
                    "Name is reserved"
            );
        }
    }
}
```

Đây là **Spring `Validator`**, không phải `jakarta.validation.Validator`. Khi `name=admin`, nó tạo một `FieldError` với code gốc do ứng dụng chọn (`signup.name.reserved`). Spring vẫn có thể tạo các biến thể cụ thể theo object/field từ code đó; API demo sẽ map nhóm mã này sang **`NAME_RESERVED`**.

Đừng dùng `String#equalsIgnoreCase` trên biến `form.getName()` khi có thể null mà không kiểm tra. Ở đây code gọi phương thức trên **hằng chuỗi** `"admin"` nên an toàn khi người dùng không gửi tên.

### 6.6. src/main/java/demo/SignupController.java

```java
package demo;

import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import jakarta.validation.Valid;
import org.springframework.context.MessageSource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SignupController {

    private final MessageSource messages;

    public SignupController(MessageSource messages) {
        this.messages = messages;
    }

    @InitBinder("signup")
    public void initSignup(WebDataBinder binder) {
        binder.setAllowedFields("name", "email", "age");
        binder.addValidators(new SignupNameValidator());
    }

    public record FieldIssue(
            String field,
            String code,
            String message) {
    }

    public record ApiError(
            String code,
            String message,
            List<FieldIssue> errors) {
    }

    @PostMapping(
            path = "/signups",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> submit(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult result,
            Locale locale) {

        if (result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body(
                    new ApiError(
                            "DISALLOWED_FIELDS",
                            message("DISALLOWED_FIELDS", locale),
                            List.of()
                    ));
        }

        if (result.hasErrors()) {
            List<FieldIssue> issues = result.getFieldErrors().stream()
                    .map(error -> {
                        String code = stableCode(error);
                        return new FieldIssue(
                                error.getField(),
                                code,
                                message(code, locale)
                        );
                    })
                    .sorted(Comparator
                            .comparing(FieldIssue::field)
                            .thenComparing(FieldIssue::code))
                    .toList();

            return ResponseEntity.badRequest().body(
                    new ApiError(
                            "VALIDATION_FAILED",
                            message("VALIDATION_FAILED", locale),
                            issues
                    ));
        }

        return ResponseEntity.ok(Map.of(
                "status", "accepted",
                "name", form.getName()
        ));
    }

    private String message(String code, Locale locale) {
        return messages.getMessage(
                "api.error." + code,
                null,
                "Invalid input",
                locale
        );
    }

    private static boolean hasCode(
            FieldError error, String candidate) {
        String[] codes = error.getCodes();
        return codes != null
                && Arrays.asList(codes).contains(candidate);
    }

    private static String stableCode(FieldError error) {
        // Chuyển kiểu thất bại: không nhầm với @Min/@NotNull.
        if (error.isBindingFailure()) {
            return "INVALID_TYPE";
        }

        String field = error.getField();

        if ("name".equals(field)) {
            if (hasCode(error, "signup.name.reserved")) {
                return "NAME_RESERVED";
            }
            if (hasCode(error, "NotBlank")) {
                return "NAME_REQUIRED";
            }
        }

        if ("email".equals(field)) {
            if (hasCode(error, "NotBlank")) {
                return "EMAIL_REQUIRED";
            }
            if (hasCode(error, "Email")) {
                return "EMAIL_INVALID";
            }
        }

        if ("age".equals(field)) {
            if (hasCode(error, "NotNull")) {
                return "AGE_REQUIRED";
            }
            if (hasCode(error, "Min")) {
                return "AGE_TOO_YOUNG";
            }
        }

        // Mã public có fallback; không công khai codes nội bộ.
        return "INVALID_FIELD";
    }
}
```

Đây là một controller **chạy được** cùng các file trước đó. Điểm then chốt:

1. `@InitBinder("signup")` dùng đúng objectName từ `@ModelAttribute("signup")`.
2. `setAllowedFields(...)` ngăn property binding ngoài `name/email/age`. Nếu có `role=ADMIN`, `getSuppressedFields()` cho biết field bị loại; endpoint chủ động trả `DISALLOWED_FIELDS`.
3. `@Valid` kích hoạt Jakarta Validation, còn `addValidators(...)` thêm Spring Validator mà không cố ý thay global validator.
4. `BindingResult` ngay sau form object cho phép controller xem field errors, global errors và suppressed fields.
5. `stableCode(...)` mapping từ metadata Spring sang **vocabulary ổn định do API sở hữu**. Đây là điểm duy nhất cần cập nhật khi thay constraint hoặc policy.
6. `message(...)` tra cứu `api.error.CODE` bằng `Locale`. Không dịch mã `CODE`.
7. Danh sách lỗi được sắp xếp theo `field` rồi `code`, vì thứ tự lỗi từ validators có thể không ổn định.
8. Không xuất `getRejectedValue()` hoặc toàn bộ exception ra response.

**Lưu ý:** ví dụ chỉ serialize **field errors**, không xuất global errors do `errors.reject(...)`. Với form có cross-field constraint, hãy mở rộng `ApiError` để chứa object-level errors và định nghĩa mã API tương ứng. Không gán bừa lỗi toàn object sang một field.

### 6.7. src/main/resources/application.properties

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Ý nghĩa:

- Spring Boot dùng bundles `messages.properties`, `messages_vi.properties` theo `Locale`.
- UTF-8 giúp lưu tiếng Việt có dấu bằng tài nguyên text.
- `fallback-to-system-locale=false` tránh phụ thuộc locale ngầm của máy chủ/CI khi không tìm thấy resource tương ứng. Khi thiếu bản dịch theo locale, hệ thống trở về bundle mặc định theo quy tắc đã cấu hình.

**Quan trọng:** Spring Boot chỉ tự cấu hình `MessageSource` từ basename như trên khi có **file bundle mặc định** (`messages.properties`). Nếu project chỉ có `messages_vi.properties`, không nên mặc định auto-config vẫn hoạt động như mong muốn.

### 6.8. src/main/resources/messages.properties

```properties
# Message keys for annotations / Jakarta Bean Validation:
signup.name.required=Name is required
signup.email.required=Email is required
signup.email.invalid=Email must be valid
signup.age.required=Age is required
signup.age.min=Age must be at least 18
signup.name.reserved=This name is reserved

# Public API messages, driven by stable error code:
api.error.VALIDATION_FAILED=Some submitted values are invalid
api.error.DISALLOWED_FIELDS=This request contains fields that cannot be changed
api.error.INVALID_TYPE=Value has an invalid type
api.error.NAME_REQUIRED=Name is required
api.error.NAME_RESERVED=This name is reserved
api.error.EMAIL_REQUIRED=Email is required
api.error.EMAIL_INVALID=Email must be valid
api.error.AGE_REQUIRED=Age is required
api.error.AGE_TOO_YOUNG=Age must be at least 18
api.error.INVALID_FIELD=One field is invalid
```

Ở đây có **hai namespace cùng phục vụ translation nhưng khác mục đích**:

- `signup.*`: dùng làm key nội suy annotation và custom Spring Validator; có thể biến đổi theo thiết kế form.
- `api.error.*`: dùng để render lời giải thích cho các **mã lỗi ổn định đã công bố**; ứng dụng quản trị và version cùng API.

Việc có text giống nhau trong hai key là chủ ý cho bài học. Trong dự án thật, có thể tổ chức resource nhiều file hoặc tái sử dụng MessageFormat để giảm trùng, miễn không làm mất ranh giới “API code bất biến, localized message tùy biến”.

### 6.9. src/main/resources/messages_vi.properties

```properties
signup.name.required=Tên không được để trống
signup.email.required=Email không được để trống
signup.email.invalid=Địa chỉ email không hợp lệ
signup.age.required=Tuổi là bắt buộc
signup.age.min=Tuổi phải từ 18 trở lên
signup.name.reserved=Tên này đã được dành riêng

api.error.VALIDATION_FAILED=Một số giá trị gửi lên không hợp lệ
api.error.DISALLOWED_FIELDS=Yêu cầu chứa trường không được phép thay đổi
api.error.INVALID_TYPE=Giá trị không đúng kiểu dữ liệu
api.error.NAME_REQUIRED=Tên không được để trống
api.error.NAME_RESERVED=Tên này đã được dành riêng
api.error.EMAIL_REQUIRED=Email không được để trống
api.error.EMAIL_INVALID=Địa chỉ email không hợp lệ
api.error.AGE_REQUIRED=Tuổi là bắt buộc
api.error.AGE_TOO_YOUNG=Tuổi phải từ 18 trở lên
api.error.INVALID_FIELD=Một trường có giá trị không hợp lệ
```

So sánh hai file: **key hoàn toàn giống nhau**, nhưng **value được dịch**. Không sửa `api.error.NAME_REQUIRED` thành `api.error.TEN_BAT_BUOC` khi tạo tiếng Việt. Nếu một locale thiếu key, nội dung fallback theo cấu hình MessageSource phải được kiểm thử.

**Khác với mã API**: `NAME_REQUIRED` không có dấu, không đổi theo locale, thường dùng như enum/string constant trong client. Message thì được phép đổi để tăng tính rõ ràng, lịch sự, phù hợp vùng miền.

### 6.10. src/test/java/demo/SignupLocalizationTest.java

```java
package demo;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupLocalizationTest {

    private static final Locale VI = Locale.forLanguageTag("vi");
    private static final Locale EN = Locale.ENGLISH;

    @Autowired
    MockMvc mvc;

    private ResultActions signup(Locale locale, String... fields)
            throws Exception {
        MockHttpServletRequestBuilder request =
                post("/signups")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .locale(locale);

        for (int i = 0; i < fields.length; i += 2) {
            request.param(fields[i], fields[i + 1]);
        }
        return mvc.perform(request);
    }

    @Test
    void validRequestWorksInVietnamese() throws Exception {
        signup(VI,
                "name", "Lan",
                "email", "lan@example.org",
                "age", "22")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("accepted"))
                .andExpect(jsonPath("$.name").value("Lan"));
    }

    @Test
    void requiredNameHasEnglishMessage() throws Exception {
        signup(EN,
                "name", "",
                "email", "lan@example.org",
                "age", "22")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("NAME_REQUIRED"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Name is required"));
    }

    @Test
    void requiredNameHasSameCodeInVietnamese()
            throws Exception {
        signup(VI,
                "name", "",
                "email", "lan@example.org",
                "age", "22")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.message")
                        .value("Một số giá trị gửi lên không hợp lệ"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("NAME_REQUIRED"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tên không được để trống"));
    }

    @Test
    void invalidEmailUsesStableCode() throws Exception {
        signup(VI,
                "name", "Lan",
                "email", "not-an-email",
                "age", "22")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("email"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("EMAIL_INVALID"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Địa chỉ email không hợp lệ"));
    }

    @Test
    void ageBelowMinimumIsConstraintViolation()
            throws Exception {
        signup(EN,
                "name", "Lan",
                "email", "lan@example.org",
                "age", "16")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("AGE_TOO_YOUNG"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Age must be at least 18"));
    }

    @Test
    void wrongAgeTypeIsNotMinConstraint() throws Exception {
        signup(VI,
                "name", "Lan",
                "email", "lan@example.org",
                "age", "abc")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("INVALID_TYPE"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Giá trị không đúng kiểu dữ liệu"));
    }

    @Test
    void reservedNameIsLocalized() throws Exception {
        signup(VI,
                "name", "admin",
                "email", "admin@example.org",
                "age", "22")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("NAME_RESERVED"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tên này đã được dành riêng"));
    }

    @Test
    void missingAgeMapsToRequiredCode() throws Exception {
        signup(EN,
                "name", "Lan",
                "email", "lan@example.org")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("AGE_REQUIRED"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Age is required"));
    }

    @Test
    void disallowedFieldIsIndependentOfLocale()
            throws Exception {
        signup(EN,
                "name", "Lan",
                "email", "lan@example.org",
                "age", "22",
                "role", "ADMIN")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.message")
                        .value("This request contains fields that cannot be changed"))
                .andExpect(jsonPath("$.errors.length()")
                        .value(0));
    }

    @Test
    void localeFallbackKeepsStableCode() throws Exception {
        signup(Locale.FRENCH,
                "name", "",
                "email", "lan@example.org",
                "age", "22")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("NAME_REQUIRED"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Name is required"));
    }
}
```

Mười kiểm thử thể hiện các điểm bắt buộc:

- **Cùng lỗi + locale khác nhau**: `NAME_REQUIRED` giữ nguyên, message đổi từ tiếng Anh sang tiếng Việt.
- **Lỗi khác nhau**: `EMAIL_INVALID`, `AGE_TOO_YOUNG`, `AGE_REQUIRED`, `INVALID_TYPE` và `NAME_RESERVED` có các mã phân biệt rõ ràng.
- **Field bị suppress**: mã request riêng không bị dịch.
- **Fallback locale**: không có bundle tiếng Pháp thì ứng dụng dùng resource mặc định đã cấu hình.
- **Happy path**: khi dữ liệu hợp lệ, controller xử lý và trả 200.

Chạy bằng JDK 17+ và Maven:

```bash
mvn -q clean test
```

**Kỳ vọng**: 10 test pass, Maven exit code 0 khi dependencies sẵn sàng. Không đưa stdout Maven cố định vì plugin, log và hệ điều hành có thể khác nhau. Các test kiểm tra **mã và message cụ thể mà ứng dụng định nghĩa**, không phụ thuộc câu chữ mặc định từ Hibernate Validator.

Chạy server:

```bash
mvn spring-boot:run
```

Gửi cùng một lỗi ở hai ngôn ngữ, từ shell POSIX:

```bash
curl -i -X POST 'http://localhost:8080/signups' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept-Language: en' \
  --data-urlencode 'name=' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'age=22'

curl -i -X POST 'http://localhost:8080/signups' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept-Language: vi' \
  --data-urlencode 'name=' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'age=22'
```

Response tiếng Anh dự kiến:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Some submitted values are invalid",
  "errors": [
    {
      "field": "name",
      "code": "NAME_REQUIRED",
      "message": "Name is required"
    }
  ]
}
```

Response tiếng Việt dự kiến:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Một số giá trị gửi lên không hợp lệ",
  "errors": [
    {
      "field": "name",
      "code": "NAME_REQUIRED",
      "message": "Tên không được để trống"
    }
  ]
}
```

Thứ tự key trong JSON object không phải hợp đồng của API. Mã code và tên field mới là những trường cần ổn định; message phải được dịch đúng với locale. Cách viết test tránh đối chiếu các thông điệp mặc định từ framework: chúng có thể thay đổi theo bundle, provider và phiên bản.

## 7. Quy tắc chọn Locale và Accept-Language

Spring MVC có cơ chế `LocaleResolver`. Trong một ứng dụng Boot MVC thông thường, `AcceptHeaderLocaleResolver` được dùng theo cấu hình mặc định và lấy thông tin ngôn ngữ từ header `Accept-Language`. Ví dụ:

```http
POST /signups HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Accept-Language: vi
```

Đây là fragment header, không phải request HTTP hoàn chỉnh. Một trình duyệt có thể gửi:

```text
Accept-Language: vi-VN,vi;q=0.9,en;q=0.8
```

Server cần chọn `Locale` được hỗ trợ theo resolver/config của mình. Có thể cấu hình danh sách locale hỗ trợ, default locale, hoặc một cơ chế chọn locale theo tài khoản người dùng. **Không ép Locale từ tham số query tùy tiện** khi hợp đồng hệ thống yêu cầu theo header hoặc sở thích đã lưu.

### 7.1. Locale của validation và Locale của API message

Có ít nhất hai nơi message được nội suy:

1. **Validator**: Jakarta validation provider có thể chuyển `{signup.name.required}` thành câu tiếng Việt/Anh trong quá trình tạo `ConstraintViolation`.
2. **API rendering**: controller dùng `MessageSource.getMessage("api.error.NAME_REQUIRED", ..., locale)` để tạo `message` public.

Nếu hai nơi dùng khác `Locale` hoặc khác bundles, một response có thể lẫn ngôn ngữ. Vì vậy hãy chọn **một chiến lược locale nhất quán** và test bằng request locale thực, không chỉ gọi thủ công `new ResourceBundleMessageSource()` ở một đơn vị riêng.

Trong project demo, API message do `MessageSource` và đối số `Locale locale` của controller quyết định. Validator có thể nội suy annotation message, nhưng **public response không copy nguyên defaultMessage**, vì muốn giữ toàn quyền bảo đảm schema và câu chữ.

### 7.2. Fallback và file mặc định

Với `messages.properties` là mặc định tiếng Anh, `messages_vi.properties` là tiếng Việt, cấu hình `spring.messages.fallback-to-system-locale=false` giúp locale không được hỗ trợ (ví dụ `fr`) dùng bundle mặc định thay vì vô tình lấy ngôn ngữ từ máy chủ.

Nên có một chính sách rõ:

- `en`: dùng tiếng Anh.
- `vi`: dùng tiếng Việt.
- Locale chưa hỗ trợ: dùng ngôn ngữ mặc định hoặc lỗi nội bộ theo chính sách, **nhưng giữ nguyên mã API**.

Nếu thiếu key ở một file bản dịch, ứng dụng có thể dùng key tương ứng từ base bundle. Hãy test với những key quan trọng và kiểm tra quy trình CI để không ship một locale bị thiếu hàng loạt.

### 7.3. MessageFormat và tham số nội suy

Khi message có tham số:

```properties
api.error.AGE_TOO_YOUNG=Age must be at least {0}
```

Tra cứu:

```java
String text = messageSource.getMessage(
        "api.error.AGE_TOO_YOUNG",
        new Object[]{18},
        Locale.ENGLISH
);
```

Đây là fragment. Kết quả mong đợi là `Age must be at least 18`. Ở tiếng Việt có thể dùng `Tuổi phải từ {0} trở lên` mà mã `AGE_TOO_YOUNG` vẫn giữ nguyên.

**Chú ý:** `MessageFormat` sử dụng dấu ngoặc nhọn cho placeholders; dấu nháy đơn có quy tắc escaping riêng. Không nối trực tiếp raw user input vào file message templates hoặc response để tránh lỗi format và rủi ro tiết lộ dữ liệu. Kiểm thử thông điệp có arguments và pluralization nếu sản phẩm cần.

## 8. Có nhất thiết ánh xạ mọi FieldError thành một code riêng?

Không. Có hai hướng thiết kế:

### Hướng A — mã tổng quát theo nhóm constraint

Ví dụ `REQUIRED`, `INVALID_FORMAT`, `OUT_OF_RANGE`, `INVALID_TYPE`. Response đi kèm `field` để chỉ vị trí.

Ưu điểm: ít mã phải quản lý, phù hợp ứng dụng form lớn. Nhược điểm: client cần biết ý nghĩa một mã chung theo từng field và có thể không phân biệt tình huống nghiệp vụ đặc thù.

### Hướng B — mã chuyên biệt theo nghiệp vụ

Ví dụ `NAME_REQUIRED`, `EMAIL_INVALID`, `AGE_TOO_YOUNG`, `NAME_RESERVED`. Ưu điểm: rõ ràng và dễ hỗ trợ tính năng cụ thể. Nhược điểm: số lượng mã lớn, phải quản lý thay đổi kỹ.

Ví dụ runnable dùng **hướng B cho constraint phổ biến**, đồng thời cung cấp `INVALID_TYPE` và `INVALID_FIELD` làm mã chung để giảm coupling. Trong hệ thống lớn, có thể kết hợp:

```json
{
  "field": "age",
  "code": "OUT_OF_RANGE",
  "rule": "minimum",
  "message": "Tuổi phải từ 18 trở lên"
}
```

Đây là **ví dụ schema lựa chọn**, không phải output của project demo. Nếu `rule` là contract công khai thì cũng phải version hóa, không thay tùy ý.

### Tránh mapping bằng vị trí mã trong getCodes()

Sai:

```java
String stable = fieldError.getCodes()[0];
```

Vấn đề: code đầu tiên thường phụ thuộc `objectName` và `field`, chẳng hạn `Min.signup.age`. Khi refactor tên form, client có thể bị ảnh hưởng dù quy tắc “tuổi tối thiểu 18” không thay đổi.

Tốt hơn trong ví dụ: kiểm tra có candidate `"Min"` trong mảng và kết hợp field `"age"`. Trong hệ thống cần độ ổn định cao, có thể ánh xạ qua một lớp adapter/enum được unit test kỹ, hoặc xuất domain validation codes trực tiếp từ service mà không phụ thuộc message resolver.

**Không tự tin quá mức vào mapping**: nếu thay Jakarta constraint bằng custom validator, đặt tên field khác hoặc thay `MessageCodesResolver`, cần cập nhật adapter + tests. Stable API không có nghĩa “mapping không bao giờ sửa”; nó có nghĩa **sửa phần nội bộ mà không tùy tiện đổi mã đã công bố**.

## 9. Phân biệt defaultMessage, message template và message cuối cùng

Trong Jakarta Bean Validation:

- `@NotBlank(message = "{signup.name.required}")`: chuỗi trong annotation là **message template**, có thể tham chiếu resource bundle.
- Bean Validation provider nội suy template thành một **message đã render** theo locale/constraint attributes.
- Spring adapter chuyển vi phạm thành `FieldError`/`ObjectError` trong `BindingResult`.
- `FieldError.getDefaultMessage()` thường nhận thông điệp đã nội suy; tuy nhiên kết quả cụ thể phụ thuộc provider, adapter và thời điểm đánh giá.

Trong Spring `Errors.rejectValue(...)`:

```java
errors.rejectValue(
        "name",
        "signup.name.reserved",
        "Name is reserved"
);
```

Tham số thứ ba là **defaultMessage** cho lỗi đó. Khi dùng `messageSource.getMessage(fieldError, locale)`, Spring thử các candidate codes rồi mới dùng default. Vì vậy resource bundle `signup.name.reserved=...` có thể ghi đè câu mặc định theo locale.

Sự khác biệt quan trọng:

| Giá trị | Vai trò | Locale-dependent? |
| --- | --- | --- |
| `"signup.name.reserved"` | Internal message code do app đặt khi reject | Tên code giữ nguyên |
| `"signup.name.required"` | Key trong annotation message template | Tên key giữ nguyên |
| `"NotBlank.signup.name"` | Spring candidate lookup code | Có thể thay khi đổi object/field |
| `"NAME_REQUIRED"` | API public code | **Phải ổn định** |
| `"Tên không được để trống"` | Localized message | **Được thay theo locale** |

Hệ thống sẽ dễ bảo trì hơn khi các thành viên team không dùng chung một biến tên `errorCode` để chứa lúc thì API code, lúc thì message key, lúc thì nội dung đã dịch.

## 10. Xử lý lỗi JSON, method validation và service errors

Project chạy được ở mục 6 sử dụng form-urlencoded để minh họa `BindingResult`. Nhưng một ứng dụng API có thể nhận JSON và dùng validation ở nhiều tầng.

### 10.1. @Valid @RequestBody với JSON hợp lệ

Ví dụ fragment trong REST controller:

```java
@PostMapping("/api/users")
ResponseEntity<?> create(
        @Valid @RequestBody CreateUserRequest request) {
    return ResponseEntity.ok().build();
}
```

Nếu JSON đọc được nhưng DTO vi phạm constraint, với cách khai báo thông thường Spring MVC ném `MethodArgumentNotValidException`. Trong `@RestControllerAdvice` có thể chuyển `ex.getBindingResult().getFieldErrors()` qua **cùng adapter stableCode(...)** về mã API public, thay vì mỗi endpoint trả một định dạng khác nhau.

**Caveat:** với trực tiếp constraint trên method parameter, Spring MVC 6.1+ có thể báo `HandlerMethodValidationException`. Nó không có cùng cấu trúc dữ liệu với `BindingResult` riêng lẻ; cần adapter tương ứng cho `ParameterValidationResult`.

### 10.2. JSON sai cú pháp hoặc không deserialize được

```text
{"age":,}
```

Đây là chuỗi JSON **sai cú pháp**, dùng code fence `text` để không trình bày như JSON hợp lệ. Spring MVC thường báo `HttpMessageNotReadableException`. Không có DTO hợp lệ để chạy `@Min`, nên không gán mã `AGE_TOO_YOUNG` chỉ vì field age xuất hiện trong chuỗi.

Nên trả:

```json
{
  "code": "REQUEST_BODY_UNREADABLE",
  "message": "Request body cannot be read"
}
```

Với tiếng Việt, chỉ đổi `message`. Đừng trả raw Jackson exception, stack trace hoặc property path nội bộ trong response. Nếu cần phân biệt **malformed syntax** và **type mismatch**, hãy bổ sung mapping theo exception cause có kiểm soát, với fallback chung.

### 10.3. Method validation và phạm vi BindingResult

Ví dụ fragment:

```java
@GetMapping("/search")
ResponseEntity<?> search(
        @RequestParam @Min(1) int page) {
    return ResponseEntity.ok().build();
}
```

Với `page=0`, Spring MVC có thể áp built-in method validation (Framework 6.1+) và tạo `HandlerMethodValidationException`. Để giữ schema đồng nhất, handler nên ánh xạ các kết quả validation của method sang mã như `PAGE_OUT_OF_RANGE` hoặc `METHOD_VALIDATION_FAILED` rồi nội suy message theo locale.

Nếu `page=abc` không đổi được sang int, đây là **lỗi chuyển kiểu tham số**, không phải `@Min(1)`. Mã có thể là `INVALID_TYPE`. Không giả định mọi 400 đều có `FieldError` để dùng chung một mapper duy nhất.

### 10.4. Business errors và HTTP status

Ví dụ service trả `EMAIL_ALREADY_EXISTS` khi email trùng unique index. Client có thể hiển thị message tiếng Việt hoặc Anh bằng key `api.error.EMAIL_ALREADY_EXISTS`. Nhưng status có thể là **409 Conflict** hoặc **422** theo API contract, thay vì mặc định 400. Chọn status nhất quán và tài liệu hóa; không để việc đổi ngôn ngữ vô tình làm đổi status.

Lưu ý về race conditions: “kiểm tra email đã tồn tại” trước khi insert không loại bỏ hoàn toàn race; database vẫn cần unique constraint hoặc cơ chế nhất quán. Khi chuyển lỗi database thành mã API, chỉ công bố thông tin phù hợp, không để lộ chi tiết constraint/table.

## 11. ProblemDetail / RFC 9457 và mã lỗi ổn định

Spring Framework hỗ trợ `ProblemDetail` và giao diện `ErrorResponse` để tạo response theo định dạng problem details (RFC 9457). Các field chuẩn có ý nghĩa:

- `type`: định danh loại problem, thường là URI.
- `title`: mô tả ngắn, có thể dùng ngôn ngữ thân thiện.
- `status`: HTTP status.
- `detail`: diễn giải vấn đề.
- `instance`: URI chỉ trường hợp cụ thể nếu phù hợp.

Ví dụ gợi ý:

```json
{
  "type": "https://api.example.org/problems/validation-failed",
  "title": "Dữ liệu không hợp lệ",
  "status": 400,
  "detail": "Một số giá trị gửi lên không hợp lệ",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "name",
      "code": "NAME_REQUIRED",
      "message": "Tên không được để trống"
    }
  ]
}
```

Đây là **gợi ý schema nâng cao**, không phải output của controller runnable ở mục 6. Các thuộc tính `code`/`errors` là **extension do ứng dụng tự định nghĩa**, không bắt buộc bởi RFC 9457.

**Cần quyết định rạch ròi:**

- Nếu `type` là public URI ổn định đại diện loại lỗi, không đổi URI theo locale.
- Có thể dịch `title` và `detail` nhưng không đổi `status` theo locale.
- Nếu thêm `code`, giữ nguyên vocabulary và version semantics.
- Không dùng full localized `detail` làm input cho frontend xử lý nghiệp vụ.
- Khi mở rộng error format, giữ khả năng tương thích hoặc công bố version migration.

Spring có cơ chế lấy thông điệp qua `MessageSource` cho một số `ErrorResponse` chuẩn, nhưng không đồng nghĩa mọi exception tự có **mã API của ứng dụng**. Adapter này vẫn phải được thiết kế.

## 12. Versioning mã lỗi và quản trị bản dịch

### 12.1. Mã API đã công bố là một phần của contract

Nếu client đã viết nhánh `switch (error.code)` cho `NAME_REQUIRED`, đổi mã thành `MISSING_NAME` mà không thông báo là **breaking change**. Thay câu “Name is required” thành “Please enter your name” thường không phải breaking change nếu frontend không dựa vào text.

Mã lỗi mới có thể được **bổ sung** theo phiên bản mà không sửa mã cũ, nhưng client vẫn nên có fallback khi gặp unknown code. Nếu cần gộp hoặc tách các nhóm mã, nên có chính sách deprecation/migration và test contract.

### 12.2. Chọn một nơi sở hữu vocabulary

Một team lớn nên có registry hoặc enum dùng trong backend (ví dụ enum `ApiErrorCode`), kèm tài liệu:

| API code | Ý nghĩa | Trường hợp | Mã thay thế khi refactor |
| --- | --- | --- | --- |
| `NAME_REQUIRED` | Name bị bỏ trống | Input validation | Giữ nguyên |
| `EMAIL_INVALID` | Email sai định dạng | Input validation | Giữ nguyên |
| `AGE_TOO_YOUNG` | Tuổi dưới ngưỡng | Input validation | Giữ nguyên |
| `INVALID_TYPE` | Không chuyển được kiểu dữ liệu | Binding / parsing | Giữ nguyên |
| `NAME_RESERVED` | Tên không dùng được | Business validation | Giữ nguyên |
| `REQUEST_BODY_UNREADABLE` | Không đọc được body | Message converter | Giữ nguyên |

Bảng chỉ minh họa. Không buộc mỗi câu thông báo dịch phải có một mã riêng nếu chúng cùng biểu diễn một điều kiện. Nếu một rule được điều chỉnh theo quốc gia, có thể cùng API code nhưng arguments hoặc message khác; nếu semantics thực sự khác, cân nhắc mã riêng.

### 12.3. CI kiểm tra completeness của bundles

Với hai file `messages.properties` và `messages_vi.properties`, tối thiểu cần kiểm tra:

1. Tập **keys** có đầy đủ cho các error codes public.
2. Không có key dịch sai chữ hoa/thường.
3. Placeholder `{0}`, `{1}` đồng bộ giữa ngôn ngữ.
4. File được lưu đúng encoding, dấu tiếng Việt không biến thành ký tự lỗi.
5. Không để nguyên chuỗi tiếng Anh trong locale tiếng Việt nếu không có chủ đích.
6. Câu chữ không chứa raw user input không được escape trong ngữ cảnh HTML.
7. Locale fallback hoạt động khi không có resource cho một ngôn ngữ.
8. Thay đổi bản dịch không làm thay đổi mã API trong snapshot/contract test.

Một test có thể đọc bundles và so key sets, nhưng nên loại trừ các key nội bộ không bắt buộc dịch nếu dự án có policy rõ. Mẫu kiểm thử nên dựa trên danh sách **public error codes** được công bố, không dựa vào việc toàn bộ file properties phải giống hệt nếu trong mỗi locale có tài nguyên đặc thù.

### 12.4. Không dùng message làm nhãn thống kê

Monitoring nên group theo `code`, endpoint và HTTP status. Nếu group theo message, một lỗi sẽ tách thành nhiều chuỗi theo locale và theo các phiên bản dịch. Điều đó làm khó đo xu hướng và cảnh báo. Logs có thể chứa localized message nếu hữu ích nhưng nên **ưu tiên structured fields** `errorCode`, `requestId`, `status` và field path đã kiểm soát.

## 13. Lỗi thường gặp khi triển khai

### 13.1. Dùng getDefaultMessage làm mã public

Sai:

```java
String apiCode = error.getDefaultMessage();
```

`getDefaultMessage()` có thể đã được dịch, có thể đến từ provider hoặc defaultMessage truyền vào khi reject; không thích hợp cho `apiCode`. Đúng là map từ lỗi sang một mã thuộc vocabulary ứng dụng, rồi tra cứu message.

### 13.2. Dùng getCode() như constant ngữ nghĩa

`FieldError#getCode()` có thể trả `NotBlank.signup.name` (mã ưu tiên đầu tiên), thay vì chỉ `NotBlank`. Nếu model name thay đổi, mã API đã vô tình thay đổi theo. Nếu dùng `getCodes()` để mapping, hiểu nó là **metadata có thể thay đổi** và viết test contract.

### 13.3. Dịch cả code trong bundle

Không viết `"NAME_REQUIRED"` trong tiếng Anh nhưng `"TEN_BAT_BUOC"` trong tiếng Việt vào trường code. Dịch **message**, giữ mã định danh.

### 13.4. Có messages_vi.properties nhưng thiếu messages.properties

Spring Boot cần default bundle để tự cấu hình MessageSource như mong đợi. Nếu chỉ có file locale-specific mà thiếu base, auto-configuration có thể không được kích hoạt theo quy tắc Boot. Thêm base bundle và cấu hình basename đúng.

### 13.5. Quên cấu hình Locale trong test

Nếu test chỉ chạy trong locale mặc định máy dev, có thể pass tình cờ. Dùng `MockMvc.locale(Locale.forLanguageTag("vi"))` hoặc gửi `Accept-Language` và xác nhận cả code lẫn message. Test ít nhất hai locale thực tế và fallback.

### 13.6. Quên phân biệt binding failure với constraint

`age=abc` không thể đổi thành Integer, vì vậy không nên trả `AGE_TOO_YOUNG`. Kiểm tra `FieldError.isBindingFailure()` hoặc exception tương ứng trước khi map `@Min`.

### 13.7. Lộ rejected values

`FieldError.getRejectedValue()` có thể chứa mật khẩu, token, email hoặc dữ liệu nhạy cảm. Không serialize nguyên `BindingResult` trong public API response. Hãy gửi field name, stable code và message thích hợp.

### 13.8. Thiếu global errors

Một validator dùng `errors.reject("invalid.combination")` tạo `ObjectError`, không phải FieldError. Nếu response chỉ xuất danh sách `getFieldErrors()`, client có thể không thấy lỗi liên trường. Cần hỗ trợ global errors bằng code riêng trong hệ thống thật.

### 13.9. Gắn chặt mã public vào constraint annotation

Nếu đổi từ `@Email` sang custom validator nhưng semantics API vẫn là email invalid, đừng đổi mã `EMAIL_INVALID` chỉ vì framework error codes đã thay. Cập nhật adapter để giữ mã public cũ. Nếu thật sự thay đổi nghĩa của rule, xem lại versioning.

### 13.10. Nhầm thông báo “friendly” với thông báo lỗi hệ thống

Exception từ Jackson, database hoặc Hibernate Validator có thể chứa chi tiết kỹ thuật. Không lấy nguyên `ex.getMessage()` để hiển thị cho người dùng. Public message nên thân thiện, không tiết lộ stack trace, câu SQL hoặc class name.

## 14. Kiểm thử hợp đồng lỗi đa ngữ

Một bộ test tốt nên bao phủ tối thiểu:

| Trường hợp | Code (không dịch) | Message theo locale |
| --- | --- | --- |
| `name=""` | `NAME_REQUIRED` | English/Vietnamese |
| `name="admin"` | `NAME_RESERVED` | English/Vietnamese |
| `email="not-an-email"` | `EMAIL_INVALID` | English/Vietnamese |
| `age=16` | `AGE_TOO_YOUNG` | English/Vietnamese |
| Thiếu `age` | `AGE_REQUIRED` | English/Vietnamese |
| `age=abc` | `INVALID_TYPE` | English/Vietnamese |
| `role=ADMIN` | `DISALLOWED_FIELDS` | English/Vietnamese |
| Locale chưa có bundle | Code giữ nguyên | Fallback có chủ đích |
| JSON sai cú pháp | `REQUEST_BODY_UNREADABLE` | Localized chung, không lộ raw exception |
| Tên command object đổi | Code giữ nguyên | Message theo key ứng dụng |
| Bản dịch chỉnh sửa | Code giữ nguyên | Message cập nhật |
| Nhiều field errors | Codes và field paths chính xác | Thứ tự và schema ổn định |

Không chỉ assert status 400; một test muốn chứng minh contract phải kiểm tra **cả code và thông điệp** theo locale. Đồng thời không nên ghi quá nhiều assertions dựa trên default Hibernate Validator message vì chúng có thể đổi qua phiên bản, locale/provider. Mã công khai và message resources do ứng dụng sở hữu là nơi tốt hơn để xác định expectation.

Khi làm snapshot test API, cân nhắc tách hai lớp: snapshot cho stable schema/code và kiểm tra message localization riêng. Như vậy một cập nhật dịch thuật không buộc team xử lý hàng loạt snapshot thay đổi không liên quan đến hành vi.

## 15. Quy trình thiết kế cho sản phẩm đa ngữ

Một luồng triển khai nhất quán:

1. **Định nghĩa điều kiện lỗi** mà client thực sự cần hiểu và sửa.
2. **Gán stable code** không phụ thuộc ngôn ngữ, có mô tả và HTTP status.
3. **Thiết kế adapter** từ validation/binding/business errors sang stable code.
4. **Chuẩn hóa response schema** cho field/global errors và error cấp request.
5. **Tạo translation keys** như `api.error.CODE` và base + locale bundles.
6. **Chọn LocaleResolver** và fallback policy; chỉ sử dụng locale từ nguồn có chủ đích.
7. **Viết test đa ngữ**: cùng payload, code không đổi, message thay đúng.
8. **Thêm trường hợp âm**: conversion, missing values, custom validator, malformed request.
9. **Bảo vệ dữ liệu nhạy cảm**: không serialize rejected values hoặc exception raw.
10. **Đặt monitoring theo code**, không theo message.
11. **Review mọi thay đổi vocabulary** như review một thay đổi API contract.
12. **Cho client fallback** khi gặp code chưa biết mà không crash.

## 16. Kết luận

Trong Spring Validation, có **mã tra cứu message của framework**, **mã lỗi công khai do ứng dụng quy định**, và **thông báo đã dịch để hiển thị**. Chúng liên quan nhưng **không nên bị coi là cùng một thứ**.

- `MessageCodesResolver` tạo những candidate codes phục vụ tìm message, thường phụ thuộc object name, field name và type.
- `MessageSource` chọn câu chữ theo key, arguments và `Locale`.
- `BindingResult` và `FieldError` cung cấp metadata để ứng dụng nhận diện lỗi; chúng không tự định nghĩa API contract ổn định.
- Stable public code như `NAME_REQUIRED` phải giữ nguyên dù message được đổi từ tiếng Anh sang tiếng Việt, hoặc nội bộ được refactor.
- Với JSON decoding, method validation, lỗi nghiệp vụ hoặc dữ liệu nhạy cảm, cần adapter và response design phù hợp thay vì xuất raw exception.

**Nguyên tắc thực hành quan trọng nhất:** *client ra quyết định theo mã lỗi ổn định; người dùng đọc thông báo được dịch*. Khi hai phần được tách rõ, hệ thống có thể nâng cấp đa ngữ mà không làm đứt hợp đồng giữa frontend và backend.

## Tài liệu tham khảo

- [Spring Framework — Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring Framework — Validation and Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Framework — MessageSource interface](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/MessageSource.html)
- [Spring Framework — DefaultMessageCodesResolver API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring Framework — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework — @ModelAttribute and BindingResult](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Error Responses / ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html)
- [Spring Boot 3.4 — Application Properties (spring.messages.*)](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/)
