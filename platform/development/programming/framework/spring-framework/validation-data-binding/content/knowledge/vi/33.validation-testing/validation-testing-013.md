# Kiểm thử thông báo đa ngữ và che dữ liệu nhạy cảm trong Spring Framework

## 1. Bài toán: đúng ngôn ngữ nhưng không được lộ dữ liệu gốc

Một API Spring nhận thông tin đăng ký, gồm email, mật khẩu, mã truy cập và các phần tử liên hệ. Người dùng ở Việt Nam cần thông báo tiếng Việt; người dùng ở Mỹ cần thông báo tiếng Anh. Đồng thời, phản hồi lỗi **không được chứa lại dữ liệu nhạy cảm** của người dùng.

Ví dụ request **hoàn toàn giả lập**:

~~~json
{
  "email": "CANARY_EMAIL_77",
  "password": "CANARY_PASSWORD_88!",
  "apiToken": "CANARY_TOKEN_99!",
  "contacts": [{"name": "", "priority": 0}]
}
~~~

Các chuỗi `CANARY_*` được cố ý đặt khác nhau để dễ phát hiện rò rỉ trong test; không dùng credentials thật.

Nếu controller trả nguyên `BindingResult`, `FieldError`, `ConstraintViolation` hay `Exception#getMessage()`, nội dung có thể chứa `rejectedValue`, `invalidValue`, JSON parser excerpt, tên Java class hoặc thông báo từ custom validator đã ghép input gốc. Cách trả này làm lộ dữ liệu và gây phụ thuộc vào chi tiết framework.

Một response **do ứng dụng chủ động định nghĩa** nên giống:

~~~json
{
  "type": "urn:problem:invalid-request",
  "title": "Yêu cầu không hợp lệ",
  "status": 400,
  "detail": "Hãy kiểm tra các trường được đánh dấu.",
  "code": "INVALID_REQUEST",
  "issues": [
    {
      "code": "INVALID_EMAIL",
      "path": "email",
      "location": "body",
      "message": "Địa chỉ email không hợp lệ"
    },
    {
      "code": "INVALID_FORMAT",
      "path": "password",
      "location": "body",
      "message": "Giá trị sai định dạng"
    }
  ]
}
~~~

Đây là **ví dụ rút gọn**, không phải output đầy đủ cho request trên: còn có thể có issues ở `apiToken` và `contacts`. `ProblemDetail` của Spring 6.x hỗ trợ RFC 9457, nhưng `code`, `issues`, `path` và `location` là các **extensions do API tự chọn**.

Bài này kiểm thử **hai thuộc tính đồng thời**:
- *i18n correctness*: cùng lỗi, `en-US` và `vi-VN` có message đúng ngôn ngữ, còn mã lỗi và đường dẫn không đổi.
- *data minimization*: toàn bộ phản hồi không chứa email/mật khẩu/token đã nhập, parser diagnostics, stack trace hay tên method/class nhạy cảm.

Nội dung sử dụng **Java 17, Spring Boot 3.5.7, Spring Framework 6.2, Jakarta Bean Validation, JUnit 5 và MockMvc**. Có project chạy được và kết quả kỳ vọng, nhưng không khẳng định Maven đã chạy.

## 2. Phân biệt dữ liệu cần giữ và dữ liệu cần che

| Thành phần | Có nên trả? | Lý do |
| --- | --- | --- |
| HTTP `status` và mã response `INVALID_REQUEST` | Có | Client xử lý đáng tin |
| Issue code `INVALID_EMAIL`, `REQUIRED` | Có | Không phụ thuộc ngôn ngữ |
| Path `contacts[0].priority` sau allowlist | Có | Frontend biết phần tử nào sai |
| `location` như `body`, `form`, `query` | Có | Xác định nguồn input |
| Message từ catalog server đã duyệt | Có | Đa ngữ và dễ kiểm thử |
| `FieldError#getRejectedValue()` | **Không** | Có thể chứa password/token/PII |
| `ConstraintViolation#getInvalidValue()` | **Không** | Có thể là nested object |
| Raw `ObjectError#getArguments()` | **Không** | Metadata/values nội bộ |
| `MessageSourceResolvable#getArguments()` | **Không** | Không phải public schema |
| `FieldError#getDefaultMessage()` tùy tiện | **Không mặc định** | Custom validator có thể chèn input |
| `Throwable#getMessage()`/cause/stack | **Không** | Rò parser/config/method details |
| Raw Map key trong field path | Cần xét duyệt | Key có thể là email/token |
| Constraint descriptor chứa regexp/groups/payload | Không mặc định | Có thể lộ chính sách |
| Server-generated request ID | Có thể | Hỗ trợ tra cứu khi định dạng an toàn |

**Lưu ý:** không chỉ bỏ property `rejectedValue` khỏi JSON. Một validator có thể tạo message kiểu `"Bad value: CANARY_PASSWORD_88!"`, làm rò dữ liệu dù response chỉ có trường `message`. Vì vậy public message phải đến từ **danh mục do server kiểm soát**, được chọn bằng mã đã whitelist.

Một anti-pattern:

~~~java
// Không dùng cho public API:
return ResponseEntity.badRequest()
        .body(exception.getBindingResult().getFieldErrors());
~~~

Một anti-pattern khác:

~~~java
// Không dùng làm cơ chế bảo mật:
String publicText = exception.getMessage()
        .replace("password", "[redacted]");
~~~

Cách thay thế chuỗi không bao phủ URL encoding, JSON escaped text, nested errors hay tên field không biết trước. Phòng tuyến mạnh hơn là **không đưa raw exception text vào DTO public từ đầu**.

## 3. Hai lớp đa ngữ phải được kiểm thử riêng

### 3.1. Nội suy message của Bean Validation

Constraint annotations có thể dùng template:

~~~java
@NotBlank(message = "{validation.required}")
@Email(message = "{validation.email}")
private String email;
~~~

`{validation.email}` là resource bundle key. Spring Boot 3.5 tích hợp application `MessageSource` vào việc giải quyết các tham số message của Bean Validation, sau đó Jakarta provider hoàn thành interpolation. Với cấu hình Boot chuẩn có `spring-boot-starter-validation` và các `messages*.properties` hợp lệ, thường không cần tự khai báo `LocalValidatorFactoryBean` chỉ để dùng i18n.

Trong test, inject Spring-managed `jakarta.validation.Validator` và xác nhận `ConstraintViolation#getMessage()` đã được nội suy, khác với `getMessageTemplate()`.

### 3.2. Public message từ API mapper

Giả sử `@Pattern` tạo framework code `Pattern`. Mapper xử lý:

~~~text
FieldError code "Pattern"
     |
     v
Public code "INVALID_FORMAT"
     |
     v
MessageSource "api.error.INVALID_FORMAT"
     |
     +-- Locale en-US: Value has an invalid format
     |
     +-- Locale vi-VN: Giá trị sai định dạng
~~~

Ở tầng này mapper **không lấy `FieldError#getDefaultMessage()`**, nên một thông điệp custom validator thiếu an toàn sẽ không đi ra public response.

Tách namespaces:
- `validation.*` phục vụ Bean Validation interpolation.
- `api.error.*` và `api.problem.*` phục vụ public response.

Một test Bean Validation pass không chứng minh API response đã được dịch. Một test API response pass cũng không chứng minh annotation templates được resolve đúng. Hãy test cả hai.

### 3.3. Locale resolution trong MVC

Với MVC, `LocaleResolver` xác định locale từ request hoặc cấu hình ứng dụng. Nếu resolver dựa vào header, client gửi:

~~~http
Accept-Language: vi-VN
~~~

Sau đó Spring có thể đặt locale thích hợp vào `LocaleContextHolder` trong luồng request. Trong `MockMvc`, `.locale(Locale.forLanguageTag("vi-VN"))` giúp chọn locale tường minh; trong unit test ngoài request phải lưu và khôi phục locale context trong `finally`.

Không dùng `Locale.getDefault()` để quyết định message cho người dùng; JVM/CI có thể chạy trên máy có locale khác. Với WebFlux, không mặc định ThreadLocal lan qua mọi Reactor scheduler.

## 4. Thiết kế hợp đồng lỗi theo hướng allowlist

Một public issue đơn giản:

~~~java
public record PublicIssue(
        String code,
        String path,
        String location,
        String message) {
}
~~~

Record này **không có** rejected/invalid value, cause, stack trace hay đối tượng framework.

Hợp đồng mã lỗi do ứng dụng chọn:

| Code framework | Code public |
| --- | --- |
| `NotBlank`, `NotNull`, `NotEmpty` | `REQUIRED` |
| `Email` | `INVALID_EMAIL` |
| `Pattern` | `INVALID_FORMAT` |
| `Min` | `BELOW_MIN` |
| `typeMismatch` | `INVALID_TYPE` |
| Lỗi không nhận diện | `INVALID_VALUE` |
| JSON không đọc được | `INVALID_JSON` |
| Query bắt buộc bị thiếu | `MISSING_PARAMETER` |

Không trả toàn bộ `FieldError#getCodes()`: các codes cụ thể có thể chứa object name, Java type, method signature. Client chỉ cần public code ổn định.

**Path cũng cần kiểm soát.** `contacts[0].name` hữu ích cho UI, nhưng `contacts[private-email@example.com].name` có thể rò dữ liệu nằm ngay trong key. Demo chỉ cho phép các fields `email`, `password`, `apiToken`, `count` và indexed `contacts[0..7].name/priority`. Path ngoài allowlist trở thành chuỗi rỗng, không được echo.

`location` được advice cấp bằng từ vựng đã duyệt (`body`, `form`, `query`), không phải raw request parameter. Nếu ứng dụng lớn có Map keys động, hãy dùng canonical public identifiers hoặc parser/escaping có kiểm thử thay vì mở mọi tên field.

## 5. Cấu trúc project và Maven

Dự án runnable dùng **Spring MVC Servlet stack**.

~~~text
pom.xml
src/main/java/com/example/i18nsafe/
  I18nSafeApplication.java
  ContactInput.java
  RegistrationInput.java
  PublicIssue.java
  SafeIssueMapper.java
  RegistrationController.java
  SafeErrorAdvice.java
src/main/resources/
  application.properties
  messages.properties
  messages_en.properties
  messages_vi.properties
src/test/java/com/example/i18nsafe/
  SafeErrorIntegrationTest.java
  SafeIssueMapperTest.java
  BeanValidationLocaleTest.java
~~~

### 5.1. `pom.xml`

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
    <artifactId>i18n-safe-validation</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Không cần database. `spring-boot-starter-web` dùng MVC, `spring-boot-starter-validation` có Jakarta provider, `spring-boot-starter-test` có JUnit Jupiter, Hamcrest, JSONPath và MockMvc.

### 5.2. Spring Boot application

~~~java
// src/main/java/com/example/i18nsafe/I18nSafeApplication.java
package com.example.i18nsafe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class I18nSafeApplication {
    public static void main(String[] args) {
        SpringApplication.run(I18nSafeApplication.class, args);
    }
}
~~~

### 5.3. Nested DTO: `ContactInput.java`

~~~java
// src/main/java/com/example/i18nsafe/ContactInput.java
package com.example.i18nsafe;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ContactInput {

    @NotBlank(message = "{validation.required}")
    private String name;

    @NotNull(message = "{validation.required}")
    @Min(value = 1, message = "{validation.min}")
    private Integer priority;

    public ContactInput() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public Integer getPriority() { return priority; }
    public void setPriority(Integer priority) {
        this.priority = priority;
    }
}
~~~

`priority=0` được parse thành `Integer` nhưng vi phạm `@Min(1)`. Với form gửi `priority=CANARY_BAD_PRIORITY`, `WebDataBinder` thất bại khi conversion và tạo lỗi `typeMismatch`, không phải đơn thuần `@Min`.

### 5.4. Input DTO: `RegistrationInput.java`

~~~java
// src/main/java/com/example/i18nsafe/RegistrationInput.java
package com.example.i18nsafe;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;

import java.util.ArrayList;
import java.util.List;

public class RegistrationInput {

    @NotBlank(message = "{validation.required}")
    @Email(message = "{validation.email}")
    private String email;

    @NotBlank(message = "{validation.required}")
    @Pattern(regexp = "[A-Za-z0-9]{12,40}",
             message = "{validation.format}")
    private String password;

    @NotBlank(message = "{validation.required}")
    @Pattern(regexp = "[A-Z0-9]{8,32}",
             message = "{validation.format}")
    private String apiToken;

    @NotEmpty(message = "{validation.required}")
    private List<@Valid ContactInput> contacts =
            new ArrayList<>();

    public RegistrationInput() {}

    public String getEmail() { return email; }
    public void setEmail(String email) {
        this.email = email;
    }

    public String getPassword() { return password; }
    public void setPassword(String password) {
        this.password = password;
    }

    public String getApiToken() { return apiToken; }
    public void setApiToken(String apiToken) {
        this.apiToken = apiToken;
    }

    public List<ContactInput> getContacts() {
        return contacts;
    }
    public void setContacts(List<ContactInput> contacts) {
        this.contacts = contacts;
    }
}
~~~

**Mật khẩu/token trong demo chỉ có regex để tạo trường hợp kiểm thử.** Đây không phải thiết kế production cho bảo mật credentials. Hệ thống thực cần password hashing, token lifecycle, giới hạn thử đăng nhập, kiểm tra quyền và không log secret. Các canary strings là dữ liệu giả.

`List<@Valid ContactInput>` cascading validation vào từng element, tạo indexed paths như `contacts[0].name`. Không xóa index khỏi path nếu nó đã qua whitelist: frontend cần biết phần tử nào sai.

### 5.5. Public DTO: `PublicIssue.java`

~~~java
// src/main/java/com/example/i18nsafe/PublicIssue.java
package com.example.i18nsafe;

public record PublicIssue(
        String code,
        String path,
        String location,
        String message) {
}
~~~

DTO chỉ chứa dữ liệu public được duyệt. Không thêm `Object rejectedValue`, `Throwable cause` hay raw `ObjectError` vào record để “giúp debug”.

## 6. Mã mapper: chỉ đọc code/path, không đọc rejected value

### 6.1. `SafeIssueMapper.java`

~~~java
// src/main/java/com/example/i18nsafe/SafeIssueMapper.java
package com.example.i18nsafe;

import org.springframework.context.MessageSource;
import org.springframework.context.MessageSourceResolvable;
import org.springframework.stereotype.Component;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

import java.util.Locale;
import java.util.Set;

@Component
public final class SafeIssueMapper {

    private static final Set<String> PUBLIC_CODES = Set.of(
            "REQUIRED", "INVALID_EMAIL", "INVALID_FORMAT",
            "BELOW_MIN", "INVALID_TYPE", "INVALID_JSON",
            "MISSING_PARAMETER", "INVALID_VALUE");

    private final MessageSource messages;

    public SafeIssueMapper(MessageSource messages) {
        this.messages = messages;
    }

    public PublicIssue fromObjectError(
            ObjectError error, String location, Locale locale) {

        String code = frameworkCode(error.getCode());
        String path = error instanceof FieldError field
                ? safePath(field.getField()) : "";

        // Không đọc getDefaultMessage(), getArguments(),
        // FieldError.getRejectedValue().
        return issue(code, path, location, locale);
    }

    public PublicIssue fromResolvable(
            MessageSourceResolvable error,
            String path, String location, Locale locale) {

        String code = "INVALID_VALUE";
        String[] candidates = error.getCodes();

        if (candidates != null) {
            for (int i = candidates.length - 1; i >= 0; i--) {
                String raw = candidates[i];
                if (raw == null) {
                    continue;
                }

                int dot = raw.indexOf('.');
                String base = dot >= 0
                        ? raw.substring(0, dot)
                        : raw;
                String mapped = frameworkCode(base);

                if (!"INVALID_VALUE".equals(mapped)) {
                    code = mapped;
                    break;
                }
            }
        }

        return issue(code, path, location, locale);
    }

    public PublicIssue issue(
            String code, String path,
            String location, Locale locale) {

        String approved = PUBLIC_CODES.contains(code)
                ? code : "INVALID_VALUE";
        String approvedPath = safePath(path);
        String message = messages.getMessage(
                "api.error." + approved,
                null,
                "Invalid input",
                locale);

        return new PublicIssue(
                approved, approvedPath, location, message);
    }

    private static String frameworkCode(String code) {
        if (code == null) {
            return "INVALID_VALUE";
        }
        return switch (code) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED";
            case "Email" -> "INVALID_EMAIL";
            case "Pattern" -> "INVALID_FORMAT";
            case "Min" -> "BELOW_MIN";
            case "typeMismatch" -> "INVALID_TYPE";
            default -> "INVALID_VALUE";
        };
    }

    static String safePath(String raw) {
        if (raw == null) {
            return "";
        }

        if ("email".equals(raw)
                || "password".equals(raw)
                || "apiToken".equals(raw)
                || "count".equals(raw)) {
            return raw;
        }

        for (int i = 0; i < 8; i++) {
            if (raw.equals("contacts[" + i + "].name")
                    || raw.equals("contacts[" + i + "].priority")) {
                return raw;
            }
        }

        return "";
    }
}
~~~

**Giải thích:**
- `frameworkCode` chỉ ánh xạ source codes đã được biết; loại lạ thành `INVALID_VALUE`.
- `fromObjectError` không bao giờ lấy raw rejected value hoặc custom default message.
- `fromResolvable` chọn mã chung từ danh sách Spring codes mà không trả cả mảng. Với direct `@Min`, mã chung `Min` được ánh xạ thành `BELOW_MIN`.
- `safePath` chỉ chấp nhận các public paths đã duyệt. Code dùng phép so sánh trực tiếp, tránh regex escape nhầm trong Java strings.
- `issue` chọn text từ server-owned `MessageSource` bằng một public code nằm trong allowlist. Text không được nội suy bằng input thô.
- `location` chỉ được advice gọi với những từ cố định; nếu mở đầu vào mới, hãy mở mapping có review.

Với API lớn, `safePath` có thể dựa trên một schema metadata do đội API kiểm soát thay vì vòng lặp cứng, nhưng đừng thay bằng `return raw;`. Map keys, URI template variables và user-created identifiers có thể chứa thông tin riêng.

## 7. Controller tạo tình huống cần kiểm thử

### 7.1. `RegistrationController.java`

~~~java
// src/main/java/com/example/i18nsafe/RegistrationController.java
package com.example.i18nsafe;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class RegistrationController {

    @InitBinder("registrationForm")
    void configureForm(WebDataBinder binder) {
        binder.setAllowedFields(
                "email", "password", "apiToken",
                "contacts[*].name",
                "contacts[*].priority");
        binder.setAutoGrowCollectionLimit(8);
    }

    @PostMapping(path = "/api/registrations",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> registerJson(
            @Valid @RequestBody RegistrationInput body) {
        return Map.of("accepted", true);
    }

    @PostMapping(path = "/api/registrations/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> registerForm(
            @Valid @ModelAttribute("registrationForm")
            RegistrationInput form) {
        return Map.of("accepted", true);
    }

    @GetMapping("/api/counts")
    public Map<String, Integer> count(
            @RequestParam(name = "count")
            @Min(value = 1, message = "{validation.min}")
            int count) {
        return Map.of("count", count);
    }

    @GetMapping("/api/invalid-return")
    @NotBlank
    public String invalidReturn() {
        return "";
    }
}
~~~

- JSON dùng Jackson `@RequestBody`; form dùng `@ModelAttribute` và `WebDataBinder`.
- `@InitBinder`/`setAllowedFields` chỉ áp cho property binding của form, **không phải JSON deserialization allowlist**.
- `@Min` trực tiếp trên `@RequestParam` trong Spring MVC 6.1+ thường đi theo `HandlerMethodValidationException` khi invalid.
- `@NotBlank` trên return value tạo một tình huống **server contract failure**; phản hồi phải 500 và không chứa tên method/return content.
- Không thêm `@Validated` ở controller class, vì điều đó có thể đưa method validation sang AOP và thay loại exception.

Không lưu hoặc trả password/apiToken trong successful response; `{"accepted":true}` chỉ phục vụ kiểm thử. Product thật cần xử lý secrets bằng một service với security controls thích hợp.

## 8. Global exception handler với ProblemDetail

### 8.1. `SafeErrorAdvice.java`

~~~java
// src/main/java/com/example/i18nsafe/SafeErrorAdvice.java
package com.example.i18nsafe;

import org.springframework.context.MessageSource;
import org.springframework.context.MessageSourceResolvable;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.ObjectError;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.net.URI;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

@RestControllerAdvice
public class SafeErrorAdvice {

    private final MessageSource messages;
    private final SafeIssueMapper mapper;

    public SafeErrorAdvice(
            MessageSource messages, SafeIssueMapper mapper) {
        this.messages = messages;
        this.mapper = mapper;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> invalidObject(
            MethodArgumentNotValidException ex) {

        Locale locale = LocaleContextHolder.getLocale();
        String location =
                ex.getParameter().hasParameterAnnotation(
                        ModelAttribute.class) ? "form" : "body";

        List<PublicIssue> issues = new ArrayList<>();
        for (ObjectError raw :
                ex.getBindingResult().getAllErrors()) {
            issues.add(mapper.fromObjectError(
                    raw, location, locale));
        }
        return badRequest("INVALID_REQUEST", issues, locale);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> invalidMethod(
            HandlerMethodValidationException ex) {

        if (ex.isForReturnValue()) {
            // Server lỗi; không trả chi tiết method hoặc value.
            return internalFailure();
        }

        Locale locale = LocaleContextHolder.getLocale();
        List<PublicIssue> issues = new ArrayList<>();

        for (ParameterValidationResult result :
                ex.getParameterValidationResults()) {

            MethodParameter parameter =
                    result.getMethodParameter();
            String location = locationOf(parameter);
            String path = publicParameterName(parameter);

            if (result instanceof ParameterErrors nested) {
                for (ObjectError raw : nested.getAllErrors()) {
                    issues.add(mapper.fromObjectError(
                            raw, location, locale));
                }
            } else {
                for (MessageSourceResolvable raw :
                        result.getResolvableErrors()) {
                    issues.add(mapper.fromResolvable(
                            raw, path, location, locale));
                }
            }
        }

        for (MessageSourceResolvable ignored :
                ex.getCrossParameterValidationResults()) {
            issues.add(mapper.issue(
                    "INVALID_VALUE", "", "parameter", locale));
        }

        return badRequest("INVALID_REQUEST", issues, locale);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ProblemDetail> queryType(
            MethodArgumentTypeMismatchException ex) {

        Locale locale = LocaleContextHolder.getLocale();
        return badRequest("INVALID_REQUEST",
                List.of(mapper.issue(
                        "INVALID_TYPE", ex.getName(),
                        "query", locale)),
                locale);
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ProblemDetail> missingQuery(
            MissingServletRequestParameterException ex) {

        Locale locale = LocaleContextHolder.getLocale();
        return badRequest("INVALID_REQUEST",
                List.of(mapper.issue(
                        "MISSING_PARAMETER",
                        ex.getParameterName(), "query", locale)),
                locale);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ProblemDetail> malformedJson(
            HttpMessageNotReadableException ignored) {

        Locale locale = LocaleContextHolder.getLocale();
        return badRequest("INVALID_JSON",
                List.of(mapper.issue(
                        "INVALID_JSON", "", "body", locale)),
                locale);
    }

    private ResponseEntity<ProblemDetail> badRequest(
            String code, List<PublicIssue> issues, Locale locale) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        problem.setType(URI.create("urn:problem:invalid-request"));
        problem.setTitle(messages.getMessage(
                "api.problem.title", null,
                "Invalid request", locale));
        problem.setDetail(messages.getMessage(
                "api.problem.detail", null,
                "Correct the listed fields.", locale));
        problem.setProperty("code", code);

        List<PublicIssue> sorted = issues.stream()
                .sorted(Comparator
                        .comparing(PublicIssue::location)
                        .thenComparing(PublicIssue::path)
                        .thenComparing(PublicIssue::code))
                .toList();
        problem.setProperty("issues", sorted);

        return ResponseEntity.status(
                HttpStatus.BAD_REQUEST).body(problem);
    }

    private static ResponseEntity<ProblemDetail>
            internalFailure() {

        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setType(URI.create("urn:problem:internal-error"));
        problem.setTitle("Internal error");
        problem.setDetail(
                "The service could not complete the request.");
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("issues", List.of());

        return ResponseEntity.status(
                HttpStatus.INTERNAL_SERVER_ERROR).body(problem);
    }

    private static String locationOf(MethodParameter parameter) {
        if (parameter.hasParameterAnnotation(RequestParam.class)) {
            return "query";
        }
        if (parameter.hasParameterAnnotation(ModelAttribute.class)) {
            return "form";
        }
        if (parameter.hasParameterAnnotation(RequestBody.class)) {
            return "body";
        }
        return "parameter";
    }

    private static String publicParameterName(
            MethodParameter parameter) {

        RequestParam annotation =
                parameter.getParameterAnnotation(RequestParam.class);
        if (annotation == null) {
            return "";
        }

        String name = annotation.name().isBlank()
                ? annotation.value() : annotation.name();
        return "count".equals(name) ? "count" : "";
    }
}
~~~

**Không có chỗ nào trong advice dùng `ex.getMessage()`, `FieldError#getRejectedValue()`, raw `MessageSourceResolvable#getArguments()` hay nested cause để tạo response.** Các lỗi từ JSON parser, query type mismatch và missing parameter đều có public error mapping riêng.

`HandlerMethodValidationException#isForReturnValue()` được kiểm tra trước khi đọc các errors: return-value validation là lỗi server (500), không được trả 400 như lỗi nhập liệu.

`getAllErrors()` giữ cả field/global errors. Với direct method constraints, `ParameterValidationResult#getResolvableErrors()` mang các mã giải quyết message; mapper chỉ chọn public code. Nếu `ParameterErrors` chứa nested fields, advice dùng mapper cho từng object error. Với cross-parameter error, code tổng quát và path rỗng tránh lộ method signature.

Trong demo `locationOf` bao phủ đúng các nguồn body/form/query đang dùng. Khi mở rộng controller với header/path/cookie parameters, phải mở mapping theo annotation một cách tường minh và thêm test, không echo mọi argument name.

**Caveat:** Spring có thể điền `ProblemDetail.instance` từ request path. Các routes demo không chứa secret trong URL. Với endpoint có token hoặc dữ liệu nhạy cảm trong URI, cần sửa thiết kế route và kiểm soát `instance`/logs; đừng giả định ProblemDetail tự che mọi dữ liệu path.

## 9. Message bundles và cấu hình đa ngữ

Đặt **`messages.properties`**, **`messages_en.properties`** và **`messages_vi.properties`** ở root `src/main/resources`. `messages.properties` là base bundle để Boot tự tạo MessageSource và fallback khi thiếu bản dịch.

**`messages.properties`:**

~~~properties
api.problem.title=Invalid request
api.problem.detail=Correct the listed fields.
api.error.REQUIRED=This field is required
api.error.INVALID_EMAIL=Enter a valid email address
api.error.INVALID_FORMAT=Value has an invalid format
api.error.BELOW_MIN=Value is below the allowed minimum
api.error.INVALID_TYPE=Value has an invalid type
api.error.INVALID_JSON=Request body is not valid JSON
api.error.MISSING_PARAMETER=A required parameter is missing
api.error.INVALID_VALUE=Invalid input
validation.required=This field is required
validation.email=Invalid email
validation.format=Invalid format
validation.min=Value must be at least {value}
~~~

**`messages_en.properties`:**

~~~properties
api.problem.title=Invalid request
api.problem.detail=Correct the listed fields.
api.error.REQUIRED=This field is required
api.error.INVALID_EMAIL=Enter a valid email address
api.error.INVALID_FORMAT=Value has an invalid format
api.error.BELOW_MIN=Value is below the allowed minimum
api.error.INVALID_TYPE=Value has an invalid type
api.error.INVALID_JSON=Request body is not valid JSON
api.error.MISSING_PARAMETER=A required parameter is missing
api.error.INVALID_VALUE=Invalid input
validation.required=This field is required
validation.email=Invalid email
validation.format=Invalid format
validation.min=Value must be at least {value}
~~~

**`messages_vi.properties`:**

~~~properties
api.problem.title=Yêu cầu không hợp lệ
api.problem.detail=Hãy kiểm tra các trường được đánh dấu.
api.error.REQUIRED=Trường này là bắt buộc
api.error.INVALID_EMAIL=Địa chỉ email không hợp lệ
api.error.INVALID_FORMAT=Giá trị sai định dạng
api.error.BELOW_MIN=Giá trị thấp hơn mức tối thiểu
api.error.INVALID_TYPE=Giá trị sai kiểu dữ liệu
api.error.INVALID_JSON=Nội dung JSON không hợp lệ
api.error.MISSING_PARAMETER=Thiếu tham số bắt buộc
api.error.INVALID_VALUE=Dữ liệu không hợp lệ
validation.required=Trường này là bắt buộc
validation.email=Email không hợp lệ
validation.format=Định dạng không hợp lệ
validation.min=Giá trị phải từ {value} trở lên
~~~

**`application.properties`:**

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
~~~

Bốn chú ý:
1. Bundle theo `vi-VN` là `messages_vi.properties`; Spring có quy tắc chọn bundle theo language/country.
2. `spring.messages.fallback-to-system-locale=false` giảm sự phụ thuộc locale của máy chủ; locale thiếu bản dịch dùng base messages theo lookup.
3. `{value}` trong `validation.min` là constraint attribute của `@Min(value=1)` được Bean Validation provider interpolate, không phải raw user value.
4. `server.error.include-*` kiểm soát một số đường error rendering mặc định của Boot, **không thay thế mapper an toàn** do ứng dụng viết.

## 10. HTTP tests: tiếng Anh, tiếng Việt và fallback

### 10.1. `SafeErrorIntegrationTest.java`

~~~java
// src/test/java/com/example/i18nsafe/SafeErrorIntegrationTest.java
package com.example.i18nsafe;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Locale;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeErrorIntegrationTest {

    @Autowired MockMvc mvc;

    private static final String BAD_JSON = """
        {
          "email":"CANARY_EMAIL_77",
          "password":"CANARY_PASSWORD_88!",
          "apiToken":"CANARY_TOKEN_99!",
          "contacts":[{"name":"","priority":0}]
        }
        """;

    @Test
    void englishErrorsKeepCodesAndDoNotLeakCanaries()
            throws Exception {

        mvc.perform(post("/api/registrations")
                    .locale(Locale.US)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(BAD_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.issues.length()").value(5))
                .andExpect(jsonPath("$.issues[*].path", hasItems(
                        "email", "password", "apiToken",
                        "contacts[0].name", "contacts[0].priority")))
                .andExpect(jsonPath("$.issues[*].code", hasItems(
                        "INVALID_EMAIL", "INVALID_FORMAT",
                        "REQUIRED", "BELOW_MIN")))
                .andExpect(jsonPath("$.issues[*].message",
                        hasItem("Enter a valid email address")))
                .andExpect(content().string(not(
                        containsString("CANARY_EMAIL_77"))))
                .andExpect(content().string(not(
                        containsString("CANARY_PASSWORD_88!"))))
                .andExpect(content().string(not(
                        containsString("CANARY_TOKEN_99!"))))
                .andExpect(content().string(not(
                        containsString("rejectedValue"))));
    }

    @Test
    void vietnameseErrorsTranslateButKeepSameCodes()
            throws Exception {

        mvc.perform(post("/api/registrations")
                    .locale(Locale.forLanguageTag("vi-VN"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(BAD_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.title")
                        .value("Yêu cầu không hợp lệ"))
                .andExpect(jsonPath("$.issues[*].code", hasItems(
                        "INVALID_EMAIL", "INVALID_FORMAT",
                        "REQUIRED", "BELOW_MIN")))
                .andExpect(jsonPath("$.issues[*].message",
                        hasItem("Địa chỉ email không hợp lệ")))
                .andExpect(jsonPath("$.issues[*].path",
                        hasItem("contacts[0].priority")))
                .andExpect(content().string(not(
                        containsString("CANARY_EMAIL_77"))))
                .andExpect(content().string(not(
                        containsString("CANARY_PASSWORD_88!"))))
                .andExpect(content().string(not(
                        containsString("CANARY_TOKEN_99!"))));
    }

    @Test
    void unknownLocaleFallsBackToBaseCatalog()
            throws Exception {

        mvc.perform(post("/api/registrations")
                    .locale(Locale.JAPAN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(BAD_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid request"))
                .andExpect(jsonPath("$.issues[*].message",
                        hasItem("Enter a valid email address")));
    }

    @Test
    void formTypeMismatchNeverEchoesBadNumber()
            throws Exception {

        mvc.perform(post("/api/registrations/form")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "lan@example.com")
                    .param("password", "ValidPassword123")
                    .param("apiToken", "TOKENABC123")
                    .param("contacts[0].name", "Lan")
                    .param("contacts[0].priority",
                            "CANARY_BAD_PRIORITY"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("INVALID_TYPE")))
                .andExpect(jsonPath("$.issues[*].path",
                        hasItem("contacts[0].priority")))
                .andExpect(jsonPath("$.issues[*].location",
                        hasItem("form")))
                .andExpect(content().string(not(
                        containsString("CANARY_BAD_PRIORITY"))));
    }

    @Test
    void malformedJsonNeverShowsParserExcerpt()
            throws Exception {

        mvc.perform(post("/api/registrations")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"email":"CANARY_JSON_EXCERPT",
                         "password":[
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_JSON"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("INVALID_JSON"))
                .andExpect(content().string(not(
                        containsString("CANARY_JSON_EXCERPT"))))
                .andExpect(content().string(not(
                        containsString("JsonParseException"))));
    }

    @Test
    void wrongQueryTypeDoesNotEchoValue() throws Exception {
        mvc.perform(get("/api/counts")
                    .param("count", "CANARY_QUERY_12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].code")
                        .value("INVALID_TYPE"))
                .andExpect(jsonPath("$.issues[0].path").value("count"))
                .andExpect(content().string(not(
                        containsString("CANARY_QUERY_12"))));
    }

    @Test
    void missingQueryGetsStableCode() throws Exception {
        mvc.perform(get("/api/counts"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.issues[0].path").value("count"));
    }

    @Test
    void minViolationUsesVietnameseMessageAndPublicCode()
            throws Exception {
        mvc.perform(get("/api/counts")
                    .locale(Locale.forLanguageTag("vi-VN"))
                    .param("count", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].code")
                        .value("BELOW_MIN"))
                .andExpect(jsonPath("$.issues[0].path")
                        .value("count"))
                .andExpect(jsonPath("$.issues[0].message")
                        .value("Giá trị thấp hơn mức tối thiểu"));
    }

    @Test
    void invalidReturnIsInternalErrorWithoutDetails()
            throws Exception {
        mvc.perform(get("/api/invalid-return"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.issues.length()").value(0))
                .andExpect(content().string(not(
                        containsString("invalidReturn"))))
                .andExpect(content().string(not(
                        containsString("HandlerMethodValidationException"))));
    }

    @Test
    void validJsonAndFormDoNotEchoCredentials()
            throws Exception {
        mvc.perform(post("/api/registrations")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"email":"lan@example.com",
                         "password":"ValidPassword123",
                         "apiToken":"TOKENABC123",
                         "contacts":[{"name":"Lan","priority":1}]}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true))
                .andExpect(content().string(not(
                        containsString("ValidPassword123"))));

        mvc.perform(post("/api/registrations/form")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "lan@example.com")
                    .param("password", "ValidPassword123")
                    .param("apiToken", "TOKENABC123")
                    .param("contacts[0].name", "Lan")
                    .param("contacts[0].priority", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }
}
~~~

**Đây là 10 test methods**, trong đó test cuối thực hiện hai HTTP requests. Các assertions âm trên toàn response body giúp phát hiện marker dù nó bị nhét vào `message`, `detail` hoặc fields mở rộng. Các assertions dương giữ bảo đảm API vẫn cung cấp code/path/message hữu ích, không “sửa bảo mật” bằng cách trả body trống.

Không cần assert thứ tự Bean Validation violations: dùng `hasItems` trên mảng issues thay vì phụ thuộc `issues[0]`. Exception advice có sort để response deterministic, nhưng client vẫn nên định danh lỗi bằng `path` + `code`.

`MockMvc.locale(...)` kiểm tra request locale trong MVC. Khi chạy qua reverse proxy hoặc custom resolver trong production, bổ sung test gửi `Accept-Language` thực để xác minh locale source đúng.

## 11. Unit tests: dữ liệu rò nằm trong defaultMessage hoặc path

### 11.1. `SafeIssueMapperTest.java`

~~~java
// src/test/java/com/example/i18nsafe/SafeIssueMapperTest.java
package com.example.i18nsafe;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.validation.FieldError;

import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class SafeIssueMapperTest {

    @Test
    void rejectedValueAndUnsafeDefaultMessageStayPrivate()
            throws Exception {

        String marker = "CANARY_REJECTED_PASSWORD_501";
        FieldError raw = new FieldError(
                "registrationInput",
                "password",
                marker,
                false,
                new String[]{"Pattern"},
                null,
                "Unsafe validation message: " + marker);

        StaticMessageSource catalog = new StaticMessageSource();
        catalog.addMessage("api.error.INVALID_FORMAT",
                Locale.US, "Value has an invalid format");

        PublicIssue safe = new SafeIssueMapper(catalog)
                .fromObjectError(raw, "body", Locale.US);

        String json = new ObjectMapper()
                .writeValueAsString(safe);

        assertEquals("INVALID_FORMAT", safe.code());
        assertEquals("password", safe.path());
        assertEquals("Value has an invalid format",
                safe.message());
        assertFalse(json.contains(marker));
        assertFalse(json.contains("Unsafe validation message"));
        assertFalse(json.contains("rejectedValue"));
    }

    @Test
    void privateMapKeyIsNotAPublicPath() throws Exception {
        String key = "private-email@example.com";

        FieldError raw = new FieldError(
                "registrationInput",
                "contacts[" + key + "].name",
                "CANARY_PRIVATE_VALUE",
                false,
                new String[]{"NotBlank"},
                null,
                "CANARY_PRIVATE_VALUE");

        StaticMessageSource catalog = new StaticMessageSource();
        catalog.addMessage("api.error.REQUIRED",
                Locale.US, "This field is required");

        PublicIssue safe = new SafeIssueMapper(catalog)
                .fromObjectError(raw, "body", Locale.US);

        String json = new ObjectMapper()
                .writeValueAsString(safe);
        assertEquals("", safe.path());
        assertEquals("REQUIRED", safe.code());
        assertFalse(json.contains(key));
        assertFalse(json.contains("CANARY_PRIVATE_VALUE"));
    }

    @Test
    void codesAndPathsStaySameAcrossLocales() {
        Locale vi = Locale.forLanguageTag("vi-VN");
        StaticMessageSource catalog = new StaticMessageSource();
        catalog.addMessage("api.error.INVALID_FORMAT",
                Locale.US, "Value has an invalid format");
        catalog.addMessage("api.error.INVALID_FORMAT",
                vi, "Giá trị sai định dạng");

        FieldError raw = new FieldError(
                "registrationInput", "password",
                "CANARY_SENSITIVE",
                false,
                new String[]{"Pattern"},
                null,
                "CANARY_SENSITIVE");

        SafeIssueMapper mapper = new SafeIssueMapper(catalog);
        PublicIssue en = mapper.fromObjectError(
                raw, "body", Locale.US);
        PublicIssue vietnamese = mapper.fromObjectError(
                raw, "body", vi);

        assertEquals(en.code(), vietnamese.code());
        assertEquals(en.path(), vietnamese.path());
        assertEquals("Value has an invalid format",
                en.message());
        assertEquals("Giá trị sai định dạng",
                vietnamese.message());
    }
}
~~~

**Ba unit tests này không cần HTTP server.** Chúng buộc mapper xử lý một `FieldError` mà:
- `rejectedValue` có marker nhạy cảm;
- `defaultMessage` cố ý chứa cùng marker;
- `field path` chứa email trong Map key.

Mapper vẫn trả code/path/message đã phê duyệt. Một test HTTP đơn thuần rất khó tạo hết các biến thể này, nên cả hai tầng là bổ sung cho nhau.

## 12. Kiểm thử Bean Validation interpolation riêng

### 12.1. `BeanValidationLocaleTest.java`

~~~java
// src/test/java/com/example/i18nsafe/BeanValidationLocaleTest.java
package com.example.i18nsafe;

import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;

import java.util.List;
import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class BeanValidationLocaleTest {

    @Autowired Validator validator;

    private RegistrationInput inputWithBadEmail() {
        ContactInput contact = new ContactInput();
        contact.setName("Lan");
        contact.setPriority(1);

        RegistrationInput input = new RegistrationInput();
        input.setEmail("CANARY_BAD_EMAIL");
        input.setPassword("ValidPassword123");
        input.setApiToken("TOKENABC123");
        input.setContacts(List.of(contact));
        return input;
    }

    private String emailMessage() {
        return validator.validate(inputWithBadEmail()).stream()
                .filter(v -> "email".equals(
                        v.getPropertyPath().toString()))
                .findFirst()
                .orElseThrow()
                .getMessage();
    }

    @Test
    void vietnameseConstraintMessage() {
        LocaleContext previous =
                LocaleContextHolder.getLocaleContext();
        try {
            LocaleContextHolder.setLocale(
                    Locale.forLanguageTag("vi-VN"));
            assertEquals("Email không hợp lệ", emailMessage());
        } finally {
            LocaleContextHolder.setLocaleContext(previous);
        }
    }

    @Test
    void englishConstraintMessage() {
        LocaleContext previous =
                LocaleContextHolder.getLocaleContext();
        try {
            LocaleContextHolder.setLocale(Locale.US);
            assertEquals("Invalid email", emailMessage());
        } finally {
            LocaleContextHolder.setLocaleContext(previous);
        }
    }
}
~~~

Đây là **hai tests trực tiếp trên Spring-managed Jakarta Validator**, xác minh `{validation.email}` được interpolate theo locale. Không dùng `Validation.buildDefaultValidatorFactory()` thuần bên ngoài Spring context khi mục tiêu là kiểm tra Spring `MessageSource` integration.

`LocaleContextHolder.setLocaleContext(previous)` khôi phục ngữ cảnh ban đầu, không làm nhiễm locale của tests khác. Đối với asynchronous/reactive code, còn cần kiểm tra context propagation riêng.

Nếu direct validation test pass nhưng HTTP API message sai, nghi ngờ locale resolver/advice/mapper. Nếu API message pass nhưng direct constraint interpolation fail, mapper `api.error.*` có thể vẫn đúng trong khi `validation.*` chưa được resolve. Không coi một tầng là bằng chứng thay cho tầng kia.

## 13. Chạy test và đọc kết quả đúng cách

| Class | Tests |
| --- | ---: |
| `SafeErrorIntegrationTest` | 10 |
| `SafeIssueMapperTest` | 3 |
| `BeanValidationLocaleTest` | 2 |
| **Tổng dự kiến** | **15** |

Chạy toàn bộ:

~~~bash
mvn test
~~~

Chạy riêng integration tests:

~~~bash
mvn -Dtest=SafeErrorIntegrationTest test
~~~

Chạy riêng mapper và message tests:

~~~bash
mvn -Dtest=SafeIssueMapperTest,BeanValidationLocaleTest test
~~~

**Kết quả kỳ vọng: 15 JUnit tests PASS** theo code và API đã nêu, nhưng đây **không phải log Maven đã được chạy**. Với CI thực, dựa vào Surefire XML reports và logs để xác nhận kết quả; không gán “PASS” cho test chưa thực thi.

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Ví dụ request tiếng Việt:

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi-VN" \
  -d '{"email":"CANARY_EMAIL_77",
       "password":"CANARY_PASSWORD_88!",
       "apiToken":"CANARY_TOKEN_99!",
       "contacts":[{"name":"","priority":0}]}'
~~~

Response HTTP 400 kỳ vọng có `code="INVALID_REQUEST"` và các issues tiếng Việt, **không chứa bất kỳ chuỗi `CANARY_*` nào**. Trên PowerShell, cú pháp nối dòng/escape JSON khác Linux/macOS/Git Bash; dùng `curl.exe` hoặc lệnh một dòng phù hợp.

## 14. Các tình huống kiểm thử bổ sung cần có trong production

### 14.1. Request locale và fallback

Không chỉ test `en-US` và `vi-VN`. Thêm locale chưa có translation (ví dụ `ja-JP`) và xác minh fallback base English; kiểm tra trường hợp một key có ở base nhưng thiếu ở `messages_vi`. Nếu product yêu cầu locale-specific fallback khác, cấu hình nó tường minh và thêm tests.

Một metamorphic test hữu ích:

~~~text
Same invalid request + locale en-US
    -> issue identity set A (code, path, location)

Same invalid request + locale vi-VN
    -> issue identity set A

Only title/detail/message may differ by locale.
~~~

Nếu dùng multiset errors, đừng convert sang `Map<path,message>` vì có thể làm mất hai violations cùng field. Thứ tự Bean Validation violations không phải một contract; normalize/sort khi product thực sự yêu cầu deterministic output.

### 14.2. Unicode và encoding

Thử input có emoji, tên tiếng Việt, combining accents, Unicode escape, non-breaking spaces và ký tự control. Dùng UTF-8 cho resource bundles, response serialization và test fixtures. Không giả định JS/Java strings luôn tương đương ở mọi normalization form. Khi kiểm tra không lộ marker, cần biết marker có bị encode/escape qua transport hay không; test ở tầng body đã decode và ở JSON semantic model khi phù hợp.

### 14.3. Indexed paths và Map keys

Kiểm thử `contacts[0].name`, `contacts[7].priority`, `contacts[8].name`, index âm và key chứa email/token. `safePath` chỉ chấp nhận các paths có danh tính công khai; trường hợp không được duyệt phải thành path rỗng/placeholder. Nếu product cho phép dynamic map keys, nên canonicalize key hoặc cấp public IDs riêng; không echo nguyên key chỉ để UI highlight.

### 14.4. JSON malformed và type mismatch

JSON sai cú pháp thường dẫn tới `HttpMessageNotReadableException` trước khi Jakarta Bean Validation chạy. Form `priority=abc` được `WebDataBinder` xử lý và có thể tạo `typeMismatch` trong `BindingResult`. Query `count=abc` có thể tạo `MethodArgumentTypeMismatchException`. **Ba lỗi này không nên bị ép vào một loại ConstraintViolation**.

Hãy test cả status, code, path/location và absence của raw input/parser details. Không trả `ex.getMostSpecificCause()` hoặc Jackson snippet làm message công khai.

### 14.5. Method input so với return validation

Spring MVC 6.1+ có built-in method validation; input constraints thường trả 400. Constraint trên return value không đạt là **lỗi server**, thường 500. Trong advice, kiểm tra `isForReturnValue()` trước khi xây issues để không lộ tên Java method, value hoặc constraint details của server.

Nếu thêm `@Validated` ở class controller, method validation có thể chuyển sang AOP và exception khác. Khi thay đổi, phải chạy lại integration tests đúng Spring context, không sửa test chỉ để bỏ lỗi.

### 14.6. Response body không phải nơi duy nhất có leak

Kiểm tra:
- `ProblemDetail.instance`: Spring có thể điền request path; đừng đưa secret vào URLs.
- Access logs/proxy logs: raw query/cookie/Authorization headers.
- Exception logs: `FieldError#toString()`, `BindException#getMessage()` có thể mang rejected values.
- APM/traces/metrics: chỉ gắn public code/status/route template, không gắn raw input.
- Cache: response localized theo `Accept-Language` cần cache policy/Vary phù hợp, thường không cache errors ở endpoints có dữ liệu riêng.
- Frontend render: escape message text, không nhét text từ response vào `innerHTML` không an toàn.

Các setting Boot `server.error.include-message=never` không thay mapper an toàn. Với custom `@RestControllerAdvice` trả raw objects, ứng dụng vẫn có thể làm lộ dữ liệu bất kể setting.

### 14.7. Volume và denial-of-service

Một request có hàng nghìn invalid list elements tạo nhiều issues. Production cần giới hạn HTTP body size, form parameter count, nested depth và collection auto-grow. Cân nhắc policy cắt danh sách errors (ví dụ tối đa 50) và flag `truncated` theo contract. Đừng cố serialize mọi `ConstraintViolation` hoặc object nested lớn.

## 15. Bảng chẩn đoán lỗi

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Có tiếng Việt trên UI nhưng API lỗi tiếng Anh | Advice dùng default locale | Dùng locale request và `MessageSource` |
| Violation message có dạng `{validation.email}` | Thiếu bundle/validator wiring | Test injected Spring `Validator` |
| Mã lỗi thay đổi khi dịch | Code suy từ message text | Map framework code → public code |
| `messages_vi` bị bỏ qua | Sai filename/path/encoding | `src/main/resources/messages_vi.properties`, UTF-8 |
| Locale không hỗ trợ ra tiếng server | Fallback theo JVM | Kiểm tra `fallback-to-system-locale=false` |
| Secret xuất hiện trong `message` | Custom validator ghép raw input | Public message từ vetted catalog |
| Secret nằm trong `path` | Echo Map key của client | Allowlist/canonicalize path |
| Có property `rejectedValue` trong response | Return raw `FieldError` | Public DTO riêng |
| JSON parse lỗi trả parser excerpt | Return exception cause/getMessage | Handler có `INVALID_JSON` tổng quát |
| Form sai kiểu ra khác JSON sai kiểu | Hai binding pipelines khác nhau | Test converter/Jackson riêng |
| Direct query `@Min` không dùng handler như kỳ vọng | Class-level `@Validated` hoặc version khác | Test MVC built-in validation, rà AOP |
| Return validation bị trả 400 | Handler không phân input/return | `isForReturnValue()` → 500 |
| HTTP test pass nhưng leak trong logs | Logging raw exceptions/headers | Audit filter/gateway/APM |
| Một locale mới gây test fail | Catalog/fallback khác | Test key coverage và fallback |
| Tests phụ thuộc thứ tự errors | Dùng `issues[0]` cho nhiều violations | Assert sets hoặc sort contract |
| Chỉ unit mapper pass | Handler khác vẫn return raw error | MockMvc integration end-to-end |
| Thiếu field path khi unknown | Mapper có allowlist chặt | Nếu cần mở, cập nhật public schema + tests |
| Text Việt lỗi dấu | Encoding không nhất quán | Dùng UTF-8 và test Unicode |
| Password có trong response 200 | Controller echo toàn input | Response DTO chỉ chứa thông tin cần thiết |

## 16. Bài tập tự luyện

1. Thêm `@Size(min=12,max=40)` cho password. Tạo public code `INVALID_LENGTH` và dịch en/vi; không xuất raw regex/descriptor.
2. Tạo một custom validator cố tình đặt default message chứa `CANARY_CUSTOM_VALUE`. Xác minh mapper không dùng default message.
3. Viết `@ParameterizedTest` cho `en-US`, `vi-VN`, `fr-FR` và locale không hỗ trợ, kiểm tra code/path bất biến.
4. Thử `contacts[7].name` và `contacts[8].name`; kiểm tra giới hạn path và auto-grow.
5. Dùng Map key giống email, test path normalization và absence của key trong response.
6. Viết một `@RestControllerAdvice` cho WebFlux, sử dụng `WebTestClient` và reactive locale context thích hợp.
7. Viết test capture logs để xác minh không có rejected values/Authorization headers.
8. Nâng Spring/Jakarta provider trong một nhánh thử nghiệm; so sánh exception mapping và thông báo giữa các versions.
9. Kiểm tra liệu response localized có bị CDN cache sai ngôn ngữ; thiết kế cache headers phù hợp.
10. Thử JSON parser failure ở nested arrays với Unicode secret marker, kiểm tra body sau decode.

## 17. Checklist áp dụng

- [ ] Public error schema chỉ gồm mã/path/location/message/metadata được duyệt, không chứa framework objects.
- [ ] Không dùng `getRejectedValue()`, `getInvalidValue()`, raw `getArguments()` hoặc raw `Exception#getMessage()`.
- [ ] Không tin `FieldError#getDefaultMessage()` khi custom validator có thể ghép user input.
- [ ] Mã lỗi ổn định giữa locales, không expose Java class/method names trong `getCodes()`.
- [ ] Paths và Map keys được allowlist/canonicalize, nested indices vẫn hữu ích khi được phép.
- [ ] Message lấy từ `MessageSource` do server kiểm soát với fallback có test.
- [ ] Test riêng Bean Validation `validation.*` interpolation và public API `api.error.*` translation.
- [ ] MockMvc test cả positive code/path/message và absence của canary trong **toàn response**.
- [ ] Có tests cho invalid JSON/form/query, missing parameter, direct method validation và return-value 500.
- [ ] Không đưa credentials thực vào fixtures, CI reports hoặc logs.
- [ ] Không đưa raw request, rejected values, stack traces hay exception messages vào telemetry public.
- [ ] Kiểm tra ProblemDetail instance, cache theo locale và frontend escaping.
- [ ] Giới hạn request size/nesting/collection length và số lượng issues khi cần.
- [ ] Sau nâng Spring/Boot/Jackson/validator, chạy lại tất cả integration regression tests.

## 18. Kết luận

Một API Spring có chất lượng phải đáp ứng hai thuộc tính đồng thời:

~~~text
Cùng lỗi + locale khác:
    code/path không đổi
    message/title/detail được dịch chính xác

Cùng lỗi + raw input có giá trị nhạy cảm:
    safe mapper + whitelist + message catalog
    -> không còn raw value/exception nội bộ trong response
~~~

Chỉ i18n mà không che dữ liệu có thể làm lộ password trong thông báo dịch. Chỉ che dữ liệu mà mất code/path khiến client không biết sửa field nào. Kết hợp **mã public ổn định, message source đáng tin cậy, path allowlist và unit + HTTP tests** giúp giữ cả trải nghiệm đa ngữ lẫn an toàn dữ liệu.

## 19. Tài liệu tham khảo

- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — Error Responses và ProblemDetail: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — FieldError Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 — ObjectError Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html
- Spring Framework 6.2 — HandlerMethodValidationException Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 — ParameterValidationResult Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Boot 3.5 — Bean Validation MessageSource integration: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 — Internationalization: https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html
- Jakarta Bean Validation 3.1 specification: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- OWASP Developer Guide — Handle all Errors and Exceptions: https://devguide.owasp.org/en/04-design/02-web-app-checklist/10-handle-errors-exceptions/
- MITRE CWE-209 — Error messages containing sensitive information: https://cwe.mitre.org/data/definitions/209.html
