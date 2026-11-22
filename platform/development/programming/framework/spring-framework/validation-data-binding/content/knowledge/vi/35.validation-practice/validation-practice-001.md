# Xây dựng bộ kiểm tra form với Spring Validator và Errors

## 1. Bài toán thực hành

Bạn có một biểu mẫu đăng ký khóa học gồm tên người tham dự, email, khóa học, số lượng chỗ và mã ưu đãi. Những quy tắc cần kiểm tra:

1. **Tên người tham dự**: không được trống hoặc chỉ có khoảng trắng.
2. **Email**: bắt buộc và phải có cấu trúc email cơ bản.
3. **Khóa học**: chỉ chấp nhận `JAVA` hoặc `SPRING`.
4. **Số chỗ**: bắt buộc và phải nằm từ 1 đến 5.
5. **Mã ưu đãi `GROUP`**: nếu dùng, phải đăng ký tối thiểu 3 chỗ. Đây là quy tắc phụ thuộc nhiều trường, có thể được báo thành **lỗi toàn biểu mẫu**.
6. **Sai kiểu dữ liệu** như `seats=abc`: phải phản hồi lỗi chuyển đổi dữ liệu, không được che bằng lỗi “thiếu số chỗ”.
7. Các tham số không thuộc form, chẳng hạn `isAdmin=true`, không được tự ý bind vào dữ liệu nghiệp vụ.

Thay vì chỉ dùng các constraint Jakarta Bean Validation như `@NotBlank` và `@Min`, ta sẽ tự xây dựng một validator bằng **Spring Framework native validation API**:

```java
org.springframework.validation.Validator
org.springframework.validation.Errors
org.springframework.validation.ValidationUtils
```

Khi kết nối với Spring MVC, dùng thêm:

```java
org.springframework.web.bind.WebDataBinder
org.springframework.web.bind.annotation.InitBinder
org.springframework.validation.annotation.Validated
org.springframework.validation.BindingResult
```

Mục tiêu không chỉ là biết cách viết `if`. Sau bài này, bạn sẽ hiểu cách lưu các lỗi field/global vào `Errors`, gắn validator vào bộ bind form, tránh nhân đôi lỗi `typeMismatch`, xử lý mã lỗi qua `MessageSource`, trả JSON ổn định, và kiểm thử cả API HTTP lẫn validator độc lập.

**Môi trường tham chiếu:** Java 17+, Spring Framework 6.1.x, Spring Boot 3.3.6, Servlet Spring MVC. Project demo dùng **Spring Validator thuần**, không yêu cầu các annotation Jakarta Validation để kích hoạt kiểm tra. Nếu project thật đồng thời dùng Bean Validation provider, cách phối hợp được giải thích ở phần sau.

## 2. Spring Validator, Errors và BindingResult có nhiệm vụ gì?

### 2.1. Validator là hợp đồng hai phương thức

```java
public interface Validator {

    boolean supports(Class<?> clazz);

    void validate(Object target, Errors errors);
}
```

Đây là chữ ký rút gọn để giải thích, không phải tệp mã cần sao chép. Ý nghĩa:

- `supports(Class<?> clazz)`: validator này có thể kiểm tra loại object nào.
- `validate(Object target, Errors errors)`: áp dụng quy tắc, **ghi lỗi** vào đối tượng `Errors` được truyền vào.
- Phương thức `validate` thường không ném exception cho những input sai nghiệp vụ thông thường; thay vào đó gọi `errors.rejectValue(...)` hoặc `errors.reject(...)`.
- Exception vẫn có thể xảy ra do bug, cấu hình sai, truy cập property không tồn tại hoặc hạ tầng lỗi. Đừng dùng một `catch (Exception)` bao quanh toàn bộ validator rồi tự coi mọi lỗi thành “form invalid”.

Spring `Validator` không phải `jakarta.validation.Validator`. Hai API tồn tại song song, có vai trò bổ sung chứ không đồng nhất.

### 2.2. Errors là nơi tích lũy các vi phạm

`Errors` ghi nhận cả lỗi cấp trường và lỗi cấp object:

```java
errors.rejectValue(
        "email",
        "format",
        "Please enter a valid email address"
);

errors.reject(
        "coupon.minimumSeats",
        new Object[]{3},
        "GROUP coupon requires at least {0} seats"
);
```

Dòng đầu là **field error**: trường `email` sai định dạng. Dòng sau là **global/object error**: quan hệ giữa coupon và số chỗ không hợp lệ.

Những phương thức đọc thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `errors.hasErrors()` | Có ít nhất một lỗi bất kỳ |
| `errors.hasFieldErrors("email")` | Riêng field email có lỗi |
| `errors.getFieldError("email")` | Lấy một FieldError của email, có thể null |
| `errors.getFieldErrors()` | Danh sách tất cả FieldError |
| `errors.getGlobalErrors()` | Danh sách ObjectError cấp form |
| `errors.getAllErrors()` | Danh sách cả field và global errors |
| `errors.getErrorCount()` | Tổng số lỗi |
| `errors.getFieldValue("seats")` | Giá trị field theo biểu diễn của Errors/binding |
| `errors.pushNestedPath("address")` | Chuyển ngữ cảnh đến object lồng nhau |
| `errors.popNestedPath()` | Khôi phục nested path trước đó |

Không được giả định `getFieldValue` luôn là giá trị kiểu Java đã chuyển đổi. Với `BindingResult` do binder tạo, khi chuyển đổi thất bại nó có thể giữ giá trị input thô để phục vụ hiển thị form. Đừng trực tiếp ép kiểu dựa trên `getFieldValue` mà không biết binding state.

### 2.3. BindingResult mở rộng Errors

`BindingResult` kế thừa `Errors` và bổ sung thông tin về quá trình bind, bao gồm:

- Tên model attribute.
- Các `FieldError` do chuyển đổi dữ liệu thất bại.
- Danh sách suppressed fields khi cấu hình binding allowlist.
- Các error codes được giải theo `MessageCodesResolver`.
- Model chứa target và binding result, dùng cho HTML form rendering.

Trong Spring MVC, chữ ký controller hợp lệ:

```java
@PostMapping("/register")
public ResponseEntity<?> register(
        @Validated @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult bindingResult) {
    // ...
}
```

`BindingResult` phải đặt **ngay sau** argument được validate/bind. Nếu không có `BindingResult` liền kề, Spring MVC có thể ném `MethodArgumentNotValidException` cho lỗi argument validation thông thường thay vì đưa errors đến handler.

**Phân biệt chính xác:** `Errors` là API ghi/đọc lỗi mà validator sử dụng; `BindingResult` là triển khai/extension gắn với quá trình bind cụ thể. Bạn có thể gọi validator thủ công với một `BeanPropertyBindingResult` mà không cần HTTP request.

## 3. Ba nhóm lỗi trong biểu mẫu

### 3.1. Lỗi giá trị một trường

Tên trống:

```java
errors.rejectValue(
        "participantName",
        "required",
        "Participant name is required"
);
```

Email sai:

```java
errors.rejectValue(
        "email",
        "format",
        "Please enter a valid email address"
);
```

Số chỗ không hợp lệ:

```java
errors.rejectValue(
        "seats",
        "range",
        new Object[]{1, 5},
        "Seats must be between {0} and {1}"
);
```

Các chuỗi `required`, `format`, `range` là **error codes**, không phải HTTP status hay bản dịch. Bạn có thể ánh xạ chúng thành thông báo tùy locale qua `MessageSource`.

### 3.2. Lỗi toàn form

Một coupon chỉ hợp lệ khi `seats >= 3`:

```java
errors.reject(
        "coupon.minimumSeats",
        new Object[]{3},
        "GROUP coupon requires at least {0} seats"
);
```

Đây là lỗi quan hệ giữa nhiều trường. Nếu gắn nó vào `couponCode` bằng `rejectValue` vẫn có thể hợp lý cho UX, nhưng trong bài học cố ý dùng `reject` để minh họa **ObjectError**. Khi tạo response JSON, phải đọc `getGlobalErrors()`; chỉ dùng `getFieldErrors()` sẽ bỏ mất lỗi này.

### 3.3. Lỗi binding hoặc chuyển kiểu

HTTP form gửi:

```text
seats=abc
```

Trước khi business validation chạy, `WebDataBinder` cố chuyển String `"abc"` thành `Integer`. Khi thất bại, binder ghi một `FieldError` có code chính thường là `typeMismatch`; sau đó target bean có thể vẫn có `seats=null`.

Nếu custom validator lại nhìn thấy null và gọi:

```java
errors.rejectValue("seats", "required", "Seats are required");
```

thì cùng một input sẽ có **hai lỗi trái ngữ cảnh**: “sai kiểu” và “thiếu”. Giải pháp là **không tạo business error thứ hai cho field đã có binding failure**:

```java
if (!errors.hasFieldErrors("seats")) {
    Integer seats = form.getSeats();

    if (seats == null) {
        errors.rejectValue("seats", "required",
                "Seats are required");
    } else if (seats < 1 || seats > 5) {
        errors.rejectValue("seats", "range",
                new Object[]{1, 5},
                "Seats must be between {0} and {1}");
    }
}
```

Đây là một phần mã sẽ nằm trong validator hoàn chỉnh. Cách này đặc biệt hữu ích khi `WebDataBinder` đã xử lý raw input trước khi gọi Spring Validator.

## 4. ValidationUtils và kiểm tra chuỗi bắt buộc

Spring cung cấp helper:

```java
ValidationUtils.rejectIfEmptyOrWhitespace(
        errors,
        "participantName",
        "required",
        "Participant name is required"
);
```

Helper kiểm tra property thông qua `Errors`, nhận diện null, chuỗi rỗng hoặc chỉ whitespace (theo semantics của helper) và gọi `rejectValue` khi cần. Nó giúp giảm lặp code cho required text fields.

Tuy nhiên:

- Nó **không** kiểm tra email format, numeric range hoặc quy tắc liên trường.
- Nó cần field/property phù hợp với target object và cơ chế property access.
- Đối với một value object không có property convention thích hợp, cần chọn cách truy cập phù hợp.
- Không nên áp dụng helper này cho mọi loại dữ liệu tùy tiện. Với `Integer seats`, kiểm tra `null` sau khi loại bỏ binding errors rõ ràng hơn.
- Một chuỗi `" A "` không trống; việc trim trước khi lưu là quyết định khác, không tự biến thành yêu cầu validation.

## 5. Spring Validator khác Jakarta Bean Validation như thế nào?

| Khía cạnh | Spring Validator | Jakarta Bean Validation |
| --- | --- | --- |
| Interface chính | `org.springframework.validation.Validator` | `jakarta.validation.Validator` |
| Định nghĩa quy tắc | Java code trong `validate(target, Errors)` | Annotation constraints, class-level constraints, custom `ConstraintValidator` |
| Chọn kiểu | `supports(Class<?>)` | Metadata constraints cho bean |
| Kết quả | Lỗi được ghi vào `Errors`/`BindingResult` | `Set<ConstraintViolation<T>>` |
| Multi-field logic | `errors.reject(...)` | Class-level custom constraint hoặc service rule |
| Tích hợp MVC | `@InitBinder` + `@Validated`, hoặc validator toàn cục | LocalValidatorFactoryBean và `@Valid`/`@Validated` |
| Phụ thuộc provider | Không cần Jakarta provider cho custom Spring Validator | Cần provider để thực thi Bean Validation |
| Truy cập binding failures | Trực tiếp qua `Errors` | Raw Jakarta validator không tự biết `typeMismatch` từ Spring binder |
| Phù hợp | Quy tắc form phức tạp, cần biết binding state, validate tùy workflow | Dữ liệu/constraint declarative và tái sử dụng giữa nhiều tầng |

Chúng có thể cùng tồn tại. Spring MVC thường có `LocalValidatorFactoryBean` khi Jakarta provider ở classpath; bạn có thể dùng thêm custom Spring `Validator`. Nhưng bài này chọn **Spring Validator thuần** để chứng minh `supports`/`validate`/`Errors` hoạt động thật, không tình cờ pass do annotation trên DTO.

**Lưu ý quan trọng:** `@Validated` của Spring trên `@ModelAttribute` argument kích hoạt validation trong data binder. Nó khác mục đích class-level `@Validated` trên service để bật **AOP method validation**. Không gắn `@Validated` trên controller class khi chỉ muốn đăng ký một form validator và tránh nhầm đường method validation mới của Spring MVC 6.1+.

## 6. Dự án chạy được: form đăng ký khóa học

Dự án có hai endpoint nhận `application/x-www-form-urlencoded`:

- `POST /api/registrations/checked`: có `BindingResult` liền kề, controller tự quyết định trả 400 hay 200.
- `POST /api/registrations/strict`: không có `BindingResult`, Spring MVC ném `MethodArgumentNotValidException` cho form validation errors và `@RestControllerAdvice` tạo response.

Các lớp chính:

- `RegistrationForm`: mutable input DTO có public getters/setters.
- `RegistrationFormValidator`: hiện thực Spring `Validator`.
- `RegistrationController`: `@InitBinder`, `@Validated`, cho phép binding những trường đã khai báo.
- `FormErrorMapper`: chuẩn hóa field/global errors thành JSON và dịch bằng `MessageSource`.
- `RegistrationExceptionAdvice`: xử lý đường strict.
- `RegistrationFormTest`: `MockMvc` và unit-style tests trực tiếp với Spring `Errors`/`DataBinder`.

Project cố tình **không dùng JPA entity làm request DTO**. Một form object phục vụ UI không nên lộ setter/field nhạy cảm của domain entity, chẳng hạn `role`, `ownerId`, `balance`.

### 6.1. Cấu trúc thư mục

```text
spring-validator-errors-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/formvalidation/
        FormValidationApplication.java
        RegistrationForm.java
        RegistrationFormValidator.java
        RegistrationView.java
        FieldIssue.java
        GlobalIssue.java
        ApiError.java
        FormErrorMapper.java
        RegistrationController.java
        RegistrationExceptionAdvice.java
      resources/
        application.properties
        messages.properties
        messages_vi.properties
    test/
      java/com/example/formvalidation/
        RegistrationFormTest.java
```

### 6.2. Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'spring-validator-errors-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Không khai báo `spring-boot-starter-validation` có chủ đích:** bài mẫu chỉ sử dụng `org.springframework.validation.Validator` do ứng dụng viết, không sử dụng `jakarta.validation.Validator` hay `@NotBlank`. Spring MVC và các Spring Validator interfaces đã có trong Web starter. Trong project sử dụng Jakarta annotations song song, có thể thêm `spring-boot-starter-validation`, nhưng phải kiểm tra hoạt động của tất cả validators được đăng ký.

### 6.3. Main application

Tệp `src/main/java/com/example/formvalidation/FormValidationApplication.java`:

```java
package com.example.formvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormValidationApplication.class, args);
    }
}
```

### 6.4. Input DTO JavaBean

Tệp `src/main/java/com/example/formvalidation/RegistrationForm.java`:

```java
package com.example.formvalidation;

public class RegistrationForm {

    private String participantName;
    private String email;
    private Integer seats;
    private String course;
    private String couponCode;

    public RegistrationForm() {
    }

    public String getParticipantName() {
        return participantName;
    }

    public void setParticipantName(String participantName) {
        this.participantName = participantName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }

    public String getCourse() {
        return course;
    }

    public void setCourse(String course) {
        this.course = course;
    }

    public String getCouponCode() {
        return couponCode;
    }

    public void setCouponCode(String couponCode) {
        this.couponCode = couponCode;
    }
}
```

Vì đây là JavaBean mutable, Spring `WebDataBinder` có thể bind query/form fields bằng setters. Cách triển khai còn giúp `ValidationUtils` truy cập properties thông qua `Errors`.

Mọi property đều là **input được phép**. Không thêm `isAdmin` hoặc `accountOwnerId` vào DTO chỉ vì entity thật có field đó. Bài mẫu giữ `Integer` thay vì `int` để có thể phân biệt `seats` không được gửi (null) với khách nhập `0`.

### 6.5. RegistrationFormValidator: quy tắc chính

Tệp `src/main/java/com/example/formvalidation/RegistrationFormValidator.java`:

```java
package com.example.formvalidation;

import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

@Component
public class RegistrationFormValidator implements Validator {

    private static final Set<String> COURSES =
            Set.of("JAVA", "SPRING");

    // Kiểm tra cấu trúc tối thiểu, không thay thế việc xác minh email.
    private static final Pattern EMAIL = Pattern.compile(
            "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"
    );

    @Override
    public boolean supports(Class<?> clazz) {
        return RegistrationForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationForm form = (RegistrationForm) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors,
                "participantName",
                "required",
                "Participant name is required"
        );

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors,
                "email",
                "required",
                "Email is required"
        );

        if (!errors.hasFieldErrors("email")) {
            String email = form.getEmail();
            if (!EMAIL.matcher(email).matches()) {
                errors.rejectValue(
                        "email",
                        "format",
                        "Please enter a valid email address"
                );
            }
        }

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors,
                "course",
                "required",
                "Course is required"
        );

        if (!errors.hasFieldErrors("course")
                && !COURSES.contains(form.getCourse())) {
            errors.rejectValue(
                    "course",
                    "choice",
                    "Choose JAVA or SPRING"
            );
        }

        // Nếu binder đã thêm typeMismatch cho seats,
        // không chồng thêm required/range error.
        if (!errors.hasFieldErrors("seats")) {
            Integer seats = form.getSeats();

            if (seats == null) {
                errors.rejectValue(
                        "seats",
                        "required",
                        "Seats are required"
                );
            } else if (seats < 1 || seats > 5) {
                errors.rejectValue(
                        "seats",
                        "range",
                        new Object[]{1, 5},
                        "Seats must be between {0} and {1}"
                );
            }
        }

        if ("GROUP".equals(form.getCouponCode())
                && !errors.hasFieldErrors("seats")
                && form.getSeats() != null
                && form.getSeats() < 3) {

            errors.reject(
                    "coupon.minimumSeats",
                    new Object[]{3},
                    "GROUP coupon requires at least {0} seats"
            );
        }
    }
}
```

**Đọc kỹ thứ tự kiểm tra:**

1. `supports` tuyên bố validator hỗ trợ `RegistrationForm` hoặc subclass.
2. `ValidationUtils` tạo lỗi required cho name/email/course.
3. Chỉ kiểm tra định dạng email nếu trường email **chưa** có lỗi required.
4. Chỉ kiểm tra danh sách course nếu trường course chưa lỗi required.
5. Trước kiểm tra null/range của seats, xem binder có ghi `typeMismatch` hay lỗi nào khác cho seats không.
6. Với coupon `GROUP`, tạo **global error** qua `errors.reject` thay vì field error.
7. Không gọi `errors.reject...` với giá trị từ client trong default message; thông báo được kiểm soát, tránh tiết lộ input tùy tiện.

Regex email này chỉ dùng cho bài tập, **không phải trình xác minh email chuẩn RFC hoàn chỉnh**. Email thực tế có Unicode/IDN, quotes, provider-specific rules và cần xác minh ownership thông qua gửi link/OTP; đừng gọi regex “an toàn tuyệt đối”.

**Một lưu ý về `String#trim`:** code trên không tự trim email, course hoặc coupon. `"JAVA"` được chấp nhận nhưng `" java "` không; `"GROUP"` có ngữ nghĩa đặc biệt, `"group"` không. Nếu sản phẩm muốn case-insensitive hoặc trim whitespace, hãy định nghĩa normalization tại boundary và test, không lặng lẽ thay đổi input contract.

### 6.6. DTO phản hồi thành công

Tệp `src/main/java/com/example/formvalidation/RegistrationView.java`:

```java
package com.example.formvalidation;

public record RegistrationView(
        String participantName,
        String email,
        Integer seats,
        String course,
        String couponCode
) {}
```

Controller chỉ trả public form values đã được xác nhận. Không trả mutable entity hoặc những trường server sở hữu; những bước tạo booking/ghi database thật sẽ nằm trong service riêng.

### 6.7. DTO lỗi field, global và tổng hợp

Tệp `src/main/java/com/example/formvalidation/FieldIssue.java`:

```java
package com.example.formvalidation;

public record FieldIssue(
        String field,
        String code,
        String message
) {}
```

Tệp `src/main/java/com/example/formvalidation/GlobalIssue.java`:

```java
package com.example.formvalidation;

public record GlobalIssue(
        String code,
        String message
) {}
```

Tệp `src/main/java/com/example/formvalidation/ApiError.java`:

```java
package com.example.formvalidation;

import java.util.List;

public record ApiError(
        String code,
        String message,
        List<FieldIssue> fieldErrors,
        List<GlobalIssue> globalErrors
) {}
```

`fieldErrors` là array cho field-specific errors; `globalErrors` cho cross-field errors. Không gộp tất cả thành `Map<String,String>` vì một trường có thể có nhiều vi phạm và error key không nhất thiết duy nhất. JSON arrays giữ được thông tin đầy đủ, thứ tự có thể được ứng dụng sắp rõ ràng.

### 6.8. MessageSource và error code resolution

Spring `DefaultMessageCodesResolver` có thể phát sinh nhiều mã cụ thể theo tên object, field và type từ một `rejectValue("participantName","required",...)`. Ví dụ thứ tự mã thường gặp:

```text
required.registrationForm.participantName
required.participantName
required.java.lang.String
required
```

`FieldError#getCode()` cho biết mã nguyên thủy `required`. `FieldError#getCodes()` có thể chứa các biến thể để tra resource bundle. Đừng chỉ gọi `messageSource.getMessage(fieldError.getCode(),...)` nếu muốn ưu tiên message theo field: nó bỏ qua danh sách codes của `MessageSourceResolvable`.

Với global error `coupon.minimumSeats`, Spring có thể thử mã cụ thể theo tên form rồi mã chung. Sử dụng:

```java
messageSource.getMessage(objectError, locale)
```

để Spring duyệt codes và default message phù hợp. Nếu là lỗi chuyển kiểu do binder, **đừng đưa raw rejected input** vào response: phần mapper sẽ thay bằng thông báo công khai `registration.typeMismatch`.

Tệp `src/main/resources/application.properties`:

```properties
spring.application.name=spring-validator-errors-demo
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Tệp `src/main/resources/messages.properties`:

```properties
registration.invalid=Registration form contains errors
registration.typeMismatch=Invalid field type

required.registrationForm.participantName=Participant name is required
required.registrationForm.email=Email is required
format.registrationForm.email=Enter a valid email address
required.registrationForm.course=Course is required
choice.registrationForm.course=Choose JAVA or SPRING
required.registrationForm.seats=Seats are required
range.registrationForm.seats=Seats must be between {0} and {1}
coupon.minimumSeats=GROUP coupon requires at least {0} seats
```

Tệp `src/main/resources/messages_vi.properties`:

```properties
registration.invalid=Biểu mẫu đăng ký có lỗi
registration.typeMismatch=Giá trị của trường không đúng kiểu dữ liệu

required.registrationForm.participantName=Tên người tham dự là bắt buộc
required.registrationForm.email=Email là bắt buộc
format.registrationForm.email=Email không đúng định dạng
required.registrationForm.course=Bạn phải chọn khóa học
choice.registrationForm.course=Chỉ được chọn JAVA hoặc SPRING
required.registrationForm.seats=Số chỗ là bắt buộc
range.registrationForm.seats=Số chỗ phải nằm từ {0} đến {1}
coupon.minimumSeats=Mã GROUP yêu cầu ít nhất {0} chỗ
```

**Ghi chú:** Spring Boot thường auto-configure `MessageSource` khi base bundle được khai báo và có mặt (`messages.properties`). Chỉ có `messages_vi.properties` mà thiếu base file có thể khiến auto-configuration không đạt như ý định.

### 6.9. FormErrorMapper: biến BindingResult thành JSON an toàn

Tệp `src/main/java/com/example/formvalidation/FormErrorMapper.java`:

```java
package com.example.formvalidation;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.context.NoSuchMessageException;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

@Component
public class FormErrorMapper {

    private final MessageSource messages;

    public FormErrorMapper(MessageSource messages) {
        this.messages = messages;
    }

    public ApiError from(BindingResult result) {
        Locale locale = LocaleContextHolder.getLocale();

        List<FieldIssue> fields = result.getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        error.getCode() == null
                                ? "invalid" : error.getCode(),
                        safeMessage(error, locale)
                ))
                .sorted(Comparator.comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .toList();

        List<GlobalIssue> globals = result.getGlobalErrors()
                .stream()
                .map(error -> new GlobalIssue(
                        error.getCode() == null
                                ? "invalid" : error.getCode(),
                        safeMessage(error, locale)
                ))
                .sorted(Comparator.comparing(GlobalIssue::code))
                .toList();

        String summary = messages.getMessage(
                "registration.invalid",
                null,
                "Registration form contains errors",
                locale
        );

        return new ApiError(
                "VALIDATION_ERROR", summary, fields, globals
        );
    }

    private String safeMessage(ObjectError error, Locale locale) {

        if (error instanceof FieldError fieldError
                && fieldError.isBindingFailure()) {

            return messages.getMessage(
                    "registration.typeMismatch",
                    null,
                    "Invalid field type",
                    locale
            );
        }

        try {
            return messages.getMessage(error, locale);
        } catch (NoSuchMessageException ignored) {
            // Không phát raw rejectedValue/exception message.
            return "Invalid value";
        }
    }
}
```

Lý do thiết kế:

- `result.getFieldErrors()` tách lỗi của từng field.
- `result.getGlobalErrors()` không bỏ sót quan hệ nhiều field.
- `safeMessage` dùng toàn bộ `ObjectError` làm `MessageSourceResolvable`, nhận đúng biến thể codes.
- Với `FieldError#isBindingFailure()`, luôn dùng một thông báo chung được kiểm soát thay vì default của lỗi chuyển kiểu vốn có thể chứa raw rejected input.
- `NoSuchMessageException` được bắt ở mapper để một key thiếu trong bundle không biến response validation 400 thành lỗi máy chủ ngoài ý muốn; fallback không chứa dữ liệu nhạy cảm.
- Các danh sách được sort theo field/code hoặc code, vì thứ tự lỗi do Binder/provider thêm vào không phải presentation priority bắt buộc.
- `LocaleContextHolder.getLocale()` lấy locale gắn với request hiện tại; Spring MVC `LocaleResolver` và filters/interceptors có thể ảnh hưởng locale thực tế. Đừng tùy tiện thay `Locale.setDefault(...)` toàn JVM theo từng request.

**Lưu ý:** mapper không tự giải quyết mọi bài toán quốc tế hóa. Nếu muốn fallback message tiếng Việt khi key hoàn toàn thiếu, hãy cung cấp defaultMessage tiếng Việt hoặc một key fallback. Trong demo, base tiếng Anh là fallback ngôn ngữ chung; tests xác nhận có key tiếng Việt.

### 6.10. Controller: đăng ký Validator qua @InitBinder

Tệp `src/main/java/com/example/formvalidation/RegistrationController.java`:

```java
package com.example.formvalidation;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/registrations")
public class RegistrationController {

    private final RegistrationFormValidator validator;
    private final FormErrorMapper errorMapper;

    public RegistrationController(
            RegistrationFormValidator validator,
            FormErrorMapper errorMapper) {

        this.validator = validator;
        this.errorMapper = errorMapper;
    }

    @InitBinder("registrationForm")
    public void initRegistrationBinder(WebDataBinder binder) {

        // Mutable form: chỉ cho bind đúng các field public.
        binder.setAllowedFields(
                "participantName",
                "email",
                "seats",
                "course",
                "couponCode"
        );

        binder.addValidators(validator);
    }

    @PostMapping(
            path = "/checked",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> checked(
            @Validated
            @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            return ResponseEntity.badRequest().body(
                    errorMapper.from(bindingResult)
            );
        }

        return ResponseEntity.ok(toView(form));
    }

    @PostMapping(
            path = "/strict",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public RegistrationView strict(
            @Validated
            @ModelAttribute("registrationForm") RegistrationForm form) {

        // Nếu validation lỗi và không có BindingResult liền kề,
        // Spring MVC thường ném MethodArgumentNotValidException.
        return toView(form);
    }

    private static RegistrationView toView(RegistrationForm form) {
        return new RegistrationView(
                form.getParticipantName(),
                form.getEmail(),
                form.getSeats(),
                form.getCourse(),
                form.getCouponCode()
        );
    }
}
```

**Tại sao `binder.addValidators(validator)` thay vì `setValidator(...)`?**

- `addValidators(...)` thêm custom Spring Validator vào danh sách validator của binder; nếu có global validator đã đăng ký, không cần thay thế nó.
- `setValidator(...)` chỉ định một validator và có thể thay đổi danh sách áp dụng, nên nên dùng khi chủ đích là thay thế.
- `@InitBinder("registrationForm")` giới hạn cấu hình tới model attribute có tên `registrationForm`, không áp lên mọi handler argument.
- `setAllowedFields(...)` giúp bảo vệ **property binding** của mutable JavaBean theo allowlist. Nó không thay thế thiết kế DTO ít quyền, authorization hoặc kiểm soát constructor binding.
- `@Validated` ở method argument kích hoạt quá trình gọi các validators của binder. Chỉ đăng ký qua `@InitBinder` rồi bỏ annotation validation có thể khiến custom validator không được tự chạy cho argument đó.

Với controller HTML thay vì REST, controller có thể trả lại template và dùng `BindingResult` để hiện thông báo cạnh input fields, nhưng nguyên tắc ghi lỗi bằng `Errors` giống nhau.

### 6.11. Advice cho endpoint không khai báo BindingResult

Tệp `src/main/java/com/example/formvalidation/RegistrationExceptionAdvice.java`:

```java
package com.example.formvalidation;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class RegistrationExceptionAdvice {

    private final FormErrorMapper mapper;

    public RegistrationExceptionAdvice(FormErrorMapper mapper) {
        this.mapper = mapper;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body(
                mapper.from(exception.getBindingResult())
        );
    }
}
```

Demo chỉ có HTTP form endpoints; `MethodArgumentNotValidException` là exception điển hình khi `@Validated @ModelAttribute` không có `BindingResult` liền kề. Trong project thực tế, khi có direct method constraints từ Spring MVC 6.1+, có thể gặp `HandlerMethodValidationException`; khi có JSON parser errors, có thể gặp `HttpMessageNotReadableException`. Đừng viết handler catch mọi exception rồi tự gán `VALIDATION_ERROR`.

## 7. Chạy bằng Gradle và curl

Nếu project đã có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows:

```powershell
.\gradlew.bat bootRun
```

Nếu chưa có wrapper, có thể dùng `gradle bootRun` với Gradle phù hợp hoặc tạo wrapper. Không dùng `javac` trực tiếp cho toàn dự án vì nó cần Spring Boot/MVC/JUnit dependencies trên classpath.

### 7.1. Dữ liệu hợp lệ

```bash
curl -i -X POST http://localhost:8080/api/registrations/checked \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'participantName=Lan' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'seats=2' \
  --data-urlencode 'course=JAVA'
```

Kỳ vọng HTTP **200 OK** với body:

```json
{
  "participantName": "Lan",
  "email": "lan@example.org",
  "seats": 2,
  "course": "JAVA",
  "couponCode": null
}
```

Không có `couponCode` nghĩa là không áp dụng group discount rule. Không có Bean Validation annotation trên DTO nhưng request vẫn được kiểm tra vì `@InitBinder` thêm `RegistrationFormValidator` và `@Validated` trên argument.

### 7.2. Tên trống và email không hợp lệ

```bash
curl -i -X POST http://localhost:8080/api/registrations/checked \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept-Language: vi' \
  --data-urlencode 'participantName=   ' \
  --data-urlencode 'email=not-an-email' \
  --data-urlencode 'seats=2' \
  --data-urlencode 'course=JAVA'
```

Kỳ vọng HTTP **400**, payload có hai field errors (sau sort theo field):

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Biểu mẫu đăng ký có lỗi",
  "fieldErrors": [
    {
      "field": "email",
      "code": "format",
      "message": "Email không đúng định dạng"
    },
    {
      "field": "participantName",
      "code": "required",
      "message": "Tên người tham dự là bắt buộc"
    }
  ],
  "globalErrors": []
}
```

Phần bản dịch tới từ `messages_vi.properties`; `MessageSource#getMessage(ObjectError, Locale)` quyết định mã cụ thể. Error code `format`/`required` được giữ độc lập với locale để frontend có thể điều khiển UI một cách ổn định.

### 7.3. Coupon GROUP không đủ chỗ

```bash
curl -i -X POST http://localhost:8080/api/registrations/checked \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept-Language: vi' \
  --data-urlencode 'participantName=Lan' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'seats=2' \
  --data-urlencode 'course=SPRING' \
  --data-urlencode 'couponCode=GROUP'
```

Kỳ vọng HTTP 400 với `globalErrors`:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Biểu mẫu đăng ký có lỗi",
  "fieldErrors": [],
  "globalErrors": [
    {
      "code": "coupon.minimumSeats",
      "message": "Mã GROUP yêu cầu ít nhất 3 chỗ"
    }
  ]
}
```

Đây là minh họa `errors.reject(...)` tạo `ObjectError`. Nếu ứng dụng bỏ qua `BindingResult#getGlobalErrors()`, lỗi coupon sẽ biến mất khỏi API mặc dù validator đã phát hiện.

### 7.4. Sai kiểu số chỗ

```bash
curl -i -X POST http://localhost:8080/api/registrations/checked \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'participantName=Lan' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'seats=abc' \
  --data-urlencode 'course=SPRING'
```

Kỳ vọng HTTP 400 có field error `seats` với code `typeMismatch`, message an toàn `Invalid field type`. Không tạo thêm `required` cho seats chỉ vì binder không chuyển đổi được.

Trong hệ thống sử dụng Jakarta/Bean Validation bên cạnh Spring Validator, có thể có nhiều validators cùng tham gia; cần test chính xác số lỗi thay vì suy luận rằng mọi Spring version/provider luôn tạo một error duy nhất cho mọi input sai.

## 8. Bộ kiểm thử MockMvc và Spring Validator độc lập

Tệp `src/test/java/com/example/formvalidation/RegistrationFormTest.java`:

```java
package com.example.formvalidation;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationFormTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    RegistrationFormValidator validator;

    @Test
    void supportsExactlyTheIntendedFormType() {
        assertTrue(validator.supports(RegistrationForm.class));
        assertFalse(validator.supports(String.class));
    }

    @Test
    void validFormReturnsOk() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "JAVA"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.participantName").value("Lan"))
            .andExpect(jsonPath("$.seats").value(2))
            .andExpect(jsonPath("$.course").value("JAVA"));
    }

    @Test
    void missingRequiredFieldsAreCollected() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.fieldErrors.length()").value(4))
            .andExpect(jsonPath("$.globalErrors.length()").value(0));
    }

    @Test
    void blankNameProducesRequiredError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "   ")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("participantName"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("required"));
    }

    @Test
    void invalidEmailProducesFormatError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "wrong-email")
                .param("seats", "2")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("email"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("format"));
    }

    @Test
    void unknownCourseProducesChoiceError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "PYTHON"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("course"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("choice"));
    }

    @Test
    void zeroSeatsProducesRangeError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "0")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("seats"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("range"));
    }

    @Test
    void tooManySeatsProducesRangeError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "6")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("range"));
    }

    @Test
    void missingSeatsProducesRequiredError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("seats"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("required"));
    }

    @Test
    void badNumericInputPreservesBindingErrorOnly()
            throws Exception {

        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "abc")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors.length()").value(1))
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("seats"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("typeMismatch"))
            .andExpect(jsonPath("$.fieldErrors[0].message")
                    .value("Invalid field type"));
    }

    @Test
    void groupCouponCreatesGlobalError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "SPRING")
                .param("couponCode", "GROUP"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors.length()").value(0))
            .andExpect(jsonPath("$.globalErrors.length()").value(1))
            .andExpect(jsonPath("$.globalErrors[0].code")
                    .value("coupon.minimumSeats"));
    }

    @Test
    void groupCouponSucceedsWithThreeSeats() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "3")
                .param("course", "SPRING")
                .param("couponCode", "GROUP"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.couponCode").value("GROUP"))
            .andExpect(jsonPath("$.seats").value(3));
    }

    @Test
    void strictRouteWithoutBindingResultReachesAdvice()
            throws Exception {

        mvc.perform(post("/api/registrations/strict")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", " ")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("required"));
    }

    @Test
    void fieldsAreSortedByName() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", " ")
                .param("email", "invalid")
                .param("seats", "0")
                .param("course", "BAD"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors.length()").value(4))
            .andExpect(jsonPath("$.fieldErrors[0].field").value("course"))
            .andExpect(jsonPath("$.fieldErrors[1].field").value("email"))
            .andExpect(jsonPath("$.fieldErrors[2].field")
                    .value("participantName"))
            .andExpect(jsonPath("$.fieldErrors[3].field").value("seats"));
    }

    @Test
    void vietnameseBundleLocalizesMessages() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .header("Accept-Language", "vi")
                .param("participantName", " ")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message")
                    .value("Biểu mẫu đăng ký có lỗi"))
            .andExpect(jsonPath("$.fieldErrors[0].message")
                    .value("Tên người tham dự là bắt buộc"));
    }

    @Test
    void extraClientPropertyIsNotExposed() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "JAVA")
                .param("isAdmin", "true"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.participantName").value("Lan"))
            .andExpect(jsonPath("$.isAdmin").doesNotExist());
    }

    @Test
    void customValidatorWorksWithoutHttpRequest() {
        RegistrationForm form = new RegistrationForm();

        BindingResult errors = new BeanPropertyBindingResult(
                form, "registrationForm"
        );

        validator.validate(form, errors);

        assertTrue(errors.hasErrors());
        assertEquals(4, errors.getFieldErrorCount());
        assertEquals(0, errors.getGlobalErrorCount());
        assertNotNull(errors.getFieldError("seats"));
    }

    @Test
    void dataBinderSeparatesTypeMismatchFromBusinessRules() {
        RegistrationForm form = new RegistrationForm();

        DataBinder binder = new DataBinder(form, "registrationForm");
        binder.setValidator(validator);

        MutablePropertyValues values = new MutablePropertyValues(
                Map.of(
                        "participantName", "Lan",
                        "email", "lan@example.org",
                        "course", "JAVA",
                        "seats", "abc"
                )
        );

        binder.bind(values);
        binder.validate();

        BindingResult errors = binder.getBindingResult();

        assertEquals(1, errors.getFieldErrorCount());
        assertEquals(
                "typeMismatch",
                errors.getFieldError("seats").getCode()
        );
    }
}
```

Bộ test có **18 phương thức `@Test`**. Chúng bao phủ:

- Chọn đúng target class với `supports`.
- Request hợp lệ qua `@InitBinder` và `@Validated`.
- Thiếu nhiều trường, trường blank, email format, course choice.
- Seats missing, out of range hoặc không parse được.
- Cross-field coupon tạo global error.
- Coupon đủ điều kiện thành công.
- Controller không có `BindingResult` đi vào global exception advice.
- JSON fieldErrors được sort ổn định.
- Messages tiếng Việt qua `Accept-Language`/`MessageSource`.
- Client gửi field thừa không tạo thuộc tính privileged.
- Gọi trực tiếp Spring Validator với `BeanPropertyBindingResult`.
- Gọi trực tiếp Spring `DataBinder`, tách `typeMismatch` khỏi business validations.

### 8.1. Lệnh chạy test

Từ thư mục project có Gradle wrapper:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu project chưa có wrapper, dùng Gradle đã cài để tạo wrapper hoặc chạy `gradle test`. **Kỳ vọng 18 tests PASS** khi dependencies, Java 17 và Spring Boot 3.3.6 đúng như project.

**Trạng thái kiểm chứng:** đây là code và expected outputs của bài thực hành được rà soát tĩnh. Không có tuyên bố đã chạy Gradle/JUnit thật trong bước soạn nội dung. Hãy chạy tests trong môi trường của bạn để kiểm chứng behavior theo version cụ thể.

### 8.2. Vì sao phải test cả Validator thuần và đường MVC?

Khi chỉ test `RegistrationFormValidator#validate` trực tiếp, ta biết business rules đúng nhưng chưa biết `@InitBinder` có được gọi, `@Validated` có kích hoạt validator, hay `BindingResult` đứng đúng vị trí.

Khi chỉ test MockMvc, ta biết HTTP response nhưng có thể không rõ một lỗi đến từ Spring binding, custom validator hay controller exception handler.

Kết hợp cả hai:

1. Unit-style direct validator test chứng minh `supports` và `validate` hoạt động.
2. Direct `DataBinder` test chứng minh binding failure và custom validator phối hợp đúng.
3. `MockMvc` test chứng minh end-to-end form binding, validation, error mapping và localization.

## 9. Nested form: sử dụng Errors.pushNestedPath

Một biểu mẫu thực tế có thể chứa thông tin liên hệ:

```java
public class AddressForm {

    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
```

Nếu một form khác chứa property `address` và bạn có `AddressValidator`, Spring cho phép đẩy nested path:

```java
AddressForm address = form.getAddress();

if (address != null) {
    try {
        errors.pushNestedPath("address");

        ValidationUtils.invokeValidator(
                addressValidator,
                address,
                errors
        );
    } finally {
        errors.popNestedPath();
    }
}
```

**Đây là snippet minh họa**, không thuộc project runnable `RegistrationForm` ở trên. Nó giả định form có method `getAddress()` và đã có `addressValidator`.

Điểm quan trọng:

- Khi nested path đang là `address.`, một `rejectValue("city","required")` trong `AddressValidator` có thể trở thành field error `address.city`.
- `finally` bảo đảm khôi phục nested path kể cả validator phụ ném exception.
- Nếu `address` null mà business yêu cầu có địa chỉ, validator cha cần báo lỗi thích hợp, không gọi `invokeValidator` trên null.
- Nếu dùng Jakarta Bean Validation, `@Valid` là một cơ chế cascade khác, không hoàn toàn đồng nhất với `pushNestedPath`.
- Lưu ý Collections/maps có nested keys/index và độ phức tạp path/auto-grow; không nhận bất kỳ client-supplied path không giới hạn nào như một field được phép bind.

## 10. Sử dụng Validator.validateObject từ Spring 6.1

Spring Framework 6.1 bổ sung phương thức tiện ích trên `Validator` để validate một object khi **không có data-binding process**:

```java
Errors errors = validator.validateObject(form);

if (errors.hasErrors()) {
    // Xử lý errors tùy application boundary.
}
```

Và có thể đổi trạng thái lỗi thành exception với `Errors#failOnError`:

```java
validator.validateObject(form)
        .failOnError(IllegalArgumentException::new);
```

Hai đoạn trên là snippets; giả định đã có `RegistrationFormValidator validator` và `RegistrationForm form`. Đây là lựa chọn cho validation thủ công ở service/helper, không thay thế `WebDataBinder` khi cần thu thập **binding failures** từ String → Integer. Nếu lấy một Java object đã xây xong thì `validateObject` không tự biết user đã từng gửi `seats=abc` trong HTTP request.

Trong một workflow cần trả toàn bộ field errors của form, `BindingResult` từ MVC và `FormErrorMapper` đã đủ; không bắt buộc chuyển mọi validation failure thành exception.

## 11. Một số kiến trúc có thể chọn

### 11.1. Controller dùng local @InitBinder

Phù hợp khi form validator dành riêng cho một controller hoặc một model attribute. Đây là thiết kế của demo.

Ưu điểm: phạm vi rõ, không ảnh hưởng tất cả controllers, có thể dùng chung với `BindingResult` của form.

Rủi ro: nếu có nhiều controllers cùng dùng form, phải tổ chức lại cách đăng ký hoặc tạo shared `@ControllerAdvice`.

### 11.2. Global Validator

Bạn có thể cấu hình global validator qua `WebMvcConfigurer#getValidator()`. Nhưng điều đó ảnh hưởng rộng đến argument validation; nếu validator chỉ hỗ trợ một DTO, cần `supports`/scope thích hợp. Với ứng dụng đã dùng Bean Validation mặc định, thay global validator có thể vô tình mất các Jakarta constraints; cần xem cấu hình và test đầy đủ.

Với một form duy nhất, đăng ký local bằng `binder.addValidators(...)` đơn giản và ít tác dụng phụ hơn.

### 11.3. Service validation thay vì HTTP form validation

Một số quy tắc như “coupon còn hiệu lực”, “số ghế còn đủ”, “username duy nhất” cần trạng thái database hoặc tính đồng thời. Form Validator có thể kiểm tra cú pháp và cross-field business logic thuần, nhưng kiểm tra `existsBy...` trước khi insert **không bảo đảm uniqueness** khi hai requests đua nhau. Domain service và database constraints vẫn phải thực thi invariant cuối cùng.

### 11.4. HTML Thymeleaf/JSP thay vì REST JSON

Trong một MVC page controller, khi có lỗi:

```java
if (bindingResult.hasErrors()) {
    return "registration-form";
}
```

Đây là snippet minh họa controller trả tên view, không nằm trong REST demo. Template có thể hiển thị field errors cạnh input và global errors ở đầu form, dùng binding result đã lưu trong model. Ví dụ với Thymeleaf, `th:errors` hiển thị thông báo gắn với field khi có binding result đúng.

Khi dùng template, đừng redirect ngay sang GET nếu chưa thiết kế flash attributes hoặc state handling thích hợp, vì binding errors có thể không còn trong model sau redirect.

## 12. Bảo mật khi xử lý form và Errors

### 12.1. Không trả rejectedValue tùy tiện

`FieldError#getRejectedValue()` có thể chứa email, token, password hoặc dữ liệu riêng tư. `ObjectError#getDefaultMessage()` do conversion exception tạo có thể chứa raw input/Java internals. Do đó mapper demo chỉ trả:

- `field` (tên public field).
- `code` (machine-readable error identifier).
- `message` đã resolve hoặc fallback được kiểm soát.

Đừng làm:

```java
return Map.of(
        "field", fieldError.getField(),
        "rejected", fieldError.getRejectedValue()
);
```

nếu bạn chưa có cơ chế kiểm soát thông tin nào được phép trả về. Với password reset hoặc signup, còn phải phòng chống account/email enumeration.

### 12.2. Allowed fields và mass assignment

Một mutable input form không nên là entity có setter cho mọi property. Spring DataBinder có thể gán những trường client gửi vào target có setter phù hợp. Nếu target có setter `setIsAdmin` và bạn không giới hạn fields, attacker có thể thử `isAdmin=true`.

Demo dùng:

```java
binder.setAllowedFields(
        "participantName",
        "email",
        "seats",
        "course",
        "couponCode"
);
```

Allowlist chỉ là **một lớp**. DTO phải có input surface tối thiểu, service phải kiểm tra authorization, và database phải bảo vệ invariants.

### 12.3. Không giữ Errors vào singleton field

`@Component RegistrationFormValidator` thường là singleton và có thể được gọi đồng thời bởi nhiều HTTP requests. Validator nên **stateless**; `Errors` được tạo cho từng request/binding operation và truyền vào `validate`.

Sai:

```java
@Component
public class BadValidator implements Validator {

    private Errors lastErrors; // trạng thái mutable dùng chung!

    // ...
}
```

Không giữ `Errors`/current target/Locale vào instance field của singleton validator. Regex Pattern và immutable Set of allowed courses như demo có thể dùng static final an toàn.

### 12.4. Tránh chạy truy vấn nặng trong mỗi Validator invocation

Nếu validation phụ thuộc DB/service ngoài, một request có thể bị tăng latency hoặc phát sinh n+1 queries. Cần phân tách fast input checks với business operations, authorization và persistence. Những lỗi hạ tầng cần được phân loại khác với form invalid.

## 13. Phân tích các lỗi phổ biến

**1. Nhầm Spring Validator với jakarta.validation.Validator.** Hai interface không có cùng `supports`/`validate` signature.

**2. Chỉ viết validate() mà không khai báo supports() đúng.** Binder không chấp nhận validator cho target type không tương thích.

**3. Quên @InitBinder hoặc gắn sai tên model attribute.** Custom validator có thể không được đăng ký vào binder dành cho form đó.

**4. Chỉ đăng ký binder.addValidators nhưng không yêu cầu validation.** `@Validated` hoặc `@Valid`/cơ chế validation tương ứng phải kích hoạt bước validate.

**5. Đặt BindingResult không liền kề form argument.** Spring không đưa binding errors vào đúng tham số handler.

**6. Chỉ xử lý errors.hasFieldErrors và bỏ lỗi global.** `errors.reject(...)` không xuất hiện trong field-only list.

**7. Dùng errors.rejectValue cho quy tắc toàn form mà không cân nhắc vị trí UI.** Có thể hợp lý, nhưng nếu nhiều field liên quan, cần định nghĩa UX contract rõ.

**8. Kiểm tra seats==null sau khi typeMismatch và gắn thêm required.** Tạo thông báo chồng chéo, không đúng nguyên nhân.

**9. Giả định @NotBlank của Jakarta chạy dù project không có provider.** Demo không dùng Jakarta annotations; validation đến từ Spring Validator.

**10. Tin regex email đơn giản là xác minh quyền sở hữu email.** Cần gửi mail verification và policy riêng.

**11. Chỉ test HTTP 400.** Không chứng minh lỗi thuộc field nào, code nào và có global error hay không.

**12. Dựa vào thứ tự duyệt errors để assert JSON indexes.** Adapter nên sort nếu presentation order cần ổn định.

**13. Dùng FieldError#getCode() duy nhất để dịch message.** Bỏ qua các code cụ thể theo object/field/type.

**14. Thiếu messages.properties nhưng chỉ tạo messages_vi.properties.** Boot auto-configuration có thể không đăng ký MessageSource bundle như mong muốn.

**15. Không xử lý NoSuchMessageException khi message quan trọng bị thiếu.** Error handler có thể lỗi thêm, làm mất response 400 ban đầu.

**16. Dùng exception.getMessage() làm public error response.** Có thể lộ rejected value, tên class/SQL/server details.

**17. Bind trực tiếp vào JPA entity.** Mass assignment và coupling khiến data binding khó kiểm soát.

**18. Dùng @InitBinder toàn controller mà không kiểm soát phạm vi.** Validator thuộc một form có thể ảnh hưởng những model attributes khác.

**19. Gọi validator cho subclass không tương thích.** `supports`/downcast phải có quy tắc rõ.

**20. Quên nested path khi validate object con.** `errors.rejectValue("city",...)` có thể gắn sai tên field nếu không push/pop `address` đúng lúc.

**21. Catch RuntimeException của validator rồi trả "Invalid form".** Che bugs/lỗi dependency, làm sai HTTP status và mất observability.

**22. Trả một Map<String,String> theo field và ghi đè nhiều lỗi cùng trường.** Dùng List hoặc định nghĩa rule priority rõ ràng.

**23. Không test missing khác blank, range, conversion failure.** Những trường hợp này có semantics khác nhau.

**24. Coi Errors có thể tái sử dụng giữa requests.** `Errors` là state gắn với một validation/binding invocation, không nên lưu trong singleton.

**25. Chỉ dùng Validator để bảo vệ business uniqueness/concurrency.** Không thay thế unique constraints hay transactional invariants trong database.

## 14. Checklist trước khi đưa form vào sản phẩm

1. Form DTO chỉ có các field người dùng được phép điều khiển?
2. Spring Validator có `supports(Class<?>)` trả đúng cho target?
3. `validate` có ghi field errors bằng `rejectValue` và global errors bằng `reject` khi phù hợp?
4. Có dùng `ValidationUtils.rejectIfEmptyOrWhitespace` đúng cho text required?
5. Có kiểm tra `hasFieldErrors("seats")` trước khi thêm lỗi range/required sau binding?
6. Có test missing, blank, invalid format, invalid range và `typeMismatch` riêng?
7. Có đăng ký `binder.addValidators(...)` bằng `@InitBinder` đúng attribute name?
8. `@Validated @ModelAttribute` có được khai báo để kích hoạt validation?
9. `BindingResult` có đứng ngay sau argument tương ứng?
10. Có xử lý cả `getFieldErrors()` và `getGlobalErrors()` trong response?
11. Có dùng `MessageSource#getMessage(ObjectError,Locale)` để tận dụng danh sách error codes?
12. Có messages base/locale bundles và fallback không lộ dữ liệu?
13. Có sort danh sách errors nếu JSON ordering là contract?
14. Có che raw rejected input, stack trace và exception internals khỏi response?
15. Có dùng `setAllowedFields` cho mutable property binding nếu cần?
16. Có test form gửi field thừa và kiểm tra không bị mass assignment?
17. Có test validator không cần HTTP qua `BeanPropertyBindingResult` hoặc `DataBinder`?
18. Có test thực tế qua `MockMvc` để đảm bảo wiring từ Spring Context?
19. Có kiểm tra global coupon rules với các giá trị biên 2/3 seats?
20. Có xác định rõ Spring Validator vs Jakarta Bean Validation và provider dependencies?
21. Có tách những quy tắc phụ thuộc database/concurrency sang service/storage layer?
22. Có test locale, special characters và input sizes theo sản phẩm?
23. Có chính sách log/metrics errors mà không lộ thông tin nhạy cảm?
24. Có chạy lại tests sau nâng Spring Framework/Spring Boot?
25. Nếu dùng MVC HTML, có cách hiển thị cả field/global errors và giữ dữ liệu người dùng hợp lệ khi render lại form?

**Kết luận:** Để xây dựng bộ kiểm tra form bằng **Spring Validator**, hãy viết một lớp triển khai `supports` và `validate`, tích lũy vi phạm vào `Errors` bằng `rejectValue`/`reject`, rồi đăng ký lớp đó qua `@InitBinder` và kích hoạt bằng `@Validated` cho `@ModelAttribute`. `BindingResult` là cầu nối giữa **data binding** (có thể thất bại vì sai kiểu) với **business validation** (có thể thất bại vì quy tắc trường/toàn form). Khi trả API errors, phải giữ cả field và global errors, tránh nhân đôi `typeMismatch`, dịch thông báo an toàn và viết tests ở cả cấp Validator lẫn HTTP. Đây là nền tảng kiểm tra form rõ ràng, dễ mở rộng và phù hợp với Spring MVC.

## 15. Tài liệu tham khảo chính thức

- [Spring Framework — Validation Using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html): `Validator`, `Errors`, `ValidationUtils`, nested validators và `validateObject`.
- [Spring Framework — Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html): `DefaultMessageCodesResolver`, `MessageSource` và các biến thể mã lỗi theo field.
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): controller validation, `BindingResult`, `MethodArgumentNotValidException` và method validation.
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): cấu hình `WebDataBinder` và đăng ký local validators.
- [Spring Framework — MVC Validation Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html): global/local validator và `binder.addValidators`.
- [Spring Framework 6.1 — Errors Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/validation/Errors.html): `reject`, `rejectValue`, nested path và đọc lỗi.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): `DataBinder`, `BindingResult` và type conversion errors.
- [Spring Framework — MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): thiết lập allowlist và form-binding behavior.
