# Loại bỏ rejectedValue nhạy cảm và chi tiết nội bộ trước khi trả lỗi trong Spring

## 1. Mục tiêu: phản hồi lỗi hữu ích nhưng không tiết lộ dữ liệu

Khi Spring MVC hoặc Spring WebFlux kiểm tra request, framework có thể giữ giá trị client đã gửi để giúp developer chẩn đoán. Ví dụ `FieldError#getRejectedValue()` chứa giá trị không bind hoặc không đạt constraint; `ConstraintViolation#getInvalidValue()` chứa dữ liệu vi phạm; exception từ Jackson, type conversion hay custom validator có thể có message chứa input, tên class hoặc chi tiết cấu hình.

Các dữ liệu ấy **không tự nhiên an toàn để trả về cho client**.

Giả sử request:

~~~json
{
  "email": "not-an-email_PRIVATE",
  "password": "SECRET-password-123!",
  "apiToken": "TOKEN-secret-456!",
  "contacts": [
    {"name": "", "priority": 0}
  ]
}
~~~

Một cách xử lý sai:

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
public Object unsafe(MethodArgumentNotValidException ex) {
    return ex.getBindingResult().getAllErrors();
}
~~~

Đoạn này chỉ **minh họa cách làm nguy hiểm**, không phải một phần project chạy được. Nếu Jackson serialize các object framework, response có thể xuất hiện field `rejectedValue`, tên class hoặc metadata không thuộc hợp đồng API. Một anti-pattern khác:

~~~java
return Map.of("error", ex.getMessage());
~~~

`ex.getMessage()` được tạo để chẩn đoán, **không phải hợp đồng public**; nó có thể chứa field path, rejected value, Java method signatures hoặc raw parser diagnostics.

Thay vào đó, trả một response chủ động định nghĩa:

~~~json
{
  "type": "urn:problem:invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Review the indicated fields.",
  "code": "INVALID_REQUEST",
  "issues": [
    {
      "code": "INVALID_EMAIL",
      "path": "email",
      "location": "body",
      "message": "Enter a valid email address"
    },
    {
      "code": "INVALID_FORMAT",
      "path": "password",
      "location": "body",
      "message": "Value has an invalid format"
    }
  ]
}
~~~

Đây là ví dụ rút gọn: một request có thể có thêm lỗi ở `apiToken` và `contacts`, nhưng không có chỗ nào dành cho secret input hoặc full exception details. Các fields `code`, `issues`, `path`, `location` là **extensions do ứng dụng tự thiết kế** trên `ProblemDetail` của Spring 6.x/RFC 9457.

**Nguyên tắc xuyên suốt:**
- Giữ **mã lỗi, field path đã kiểm soát, nguồn input và thông điệp an toàn** để client sửa lỗi.
- Loại bỏ **rejected/invalid values, stack trace, cause, Java class/method signatures, SQL, filesystem paths và provider internals** trước khi serialize.
- **Không giả định `getDefaultMessage()` luôn an toàn**: custom validator có thể tự ghép input vào message.
- HTTP 400 dành cho input không hợp lệ; lỗi validation của **giá trị trả về** là vấn đề server và thường phải giữ HTTP 500 với thông tin công khai tối thiểu.
- Cùng quy tắc phải áp dụng cho body HTTP, headers, logs, traces, monitoring, WebSocket/RSocket error frames và các kênh error reporting khác.

Bài dùng **Java 17, Spring Boot 3.5.7, Spring Framework 6.2, Jakarta Validation**. Có project hoàn chỉnh và JUnit/MockMvc tests để chứng minh secret không rò qua phản hồi.

## 2. Vì sao rejectedValue là dữ liệu nhạy cảm?

### 2.1. `FieldError#getRejectedValue()`

Với một form field:

~~~text
password=SECRET-password-123!
~~~

Nếu Java DTO có constraint `@Pattern`, Spring có thể tạo `FieldError` chứa:
- `objectName`: tên model object.
- `field`: tên thuộc tính, ví dụ `password`.
- `rejectedValue`: chính chuỗi đã bị từ chối.
- `codes`: danh sách Spring error codes.
- `arguments`: arguments dùng để resolve messages.
- `defaultMessage`: thông báo lỗi.
- `bindingFailure`: lỗi conversion/binding hay lỗi constraint tùy nguồn.

Nhà phát triển có thể cần các thông tin đó trong debugger, nhưng **đối tượng `FieldError` không phải một public DTO**. Không return `FieldError`, `BindingResult` hoặc `MethodArgumentNotValidException` từ API và để Jackson tự quyết định các thuộc tính nào được xuất.

### 2.2. `ConstraintViolation#getInvalidValue()`

Với Jakarta Bean Validation:

~~~java
Set<ConstraintViolation<RegistrationInput>> violations =
        validator.validate(input);
~~~

Từng `ConstraintViolation` có `getPropertyPath()`, `getMessage()`, `getMessageTemplate()`, `getConstraintDescriptor()` và `getInvalidValue()`. Không serialize toàn bộ `ConstraintViolation`. Đặc biệt:
- `getInvalidValue()` có thể là password, access token, mã OTP, email, số giấy tờ hoặc nested object.
- `getConstraintDescriptor().getAttributes()` có thể chứa regex, groups, payload và cấu hình riêng.
- `getRootBean()` / `getLeafBean()` có thể tham chiếu object chứa dữ liệu không dành cho client.

Khi cần mã từ Jakarta constraint, xác định loại annotation có trong **allowlist** rồi chuyển thành mã công khai. Khi cần thông tin như minimum/maximum, lấy **đúng thuộc tính an toàn được phép tiết lộ**, không trả toàn bộ descriptor.

### 2.3. Exception message, cause và parser details

Một `HttpMessageNotReadableException` có thể bao bọc Jackson exception. Message/cause chain có thể đề cập:
- JSON token đã đọc, input gần vị trí lỗi hoặc tên property.
- Java target type, package/class.
- Vị trí dòng/cột và internals của serializer.
- Đường dẫn object hoặc constructor signature.
- Cấu hình converter/provider.

`MethodArgumentTypeMismatchException#getValue()` có thể chứa query parameter sai. `MissingServletRequestParameterException#getMessage()` là thông tin chẩn đoán, không phải sentence dành cho public API.

**Không tạo response bằng `exception.getMessage()`, `getMostSpecificCause()`, `getRootCause()`, `getStackTrace()` hoặc `printStackTrace()`.** Những dữ liệu này có thể ghi ở hệ thống quan sát nội bộ được bảo vệ khi thật sự cần, nhưng vẫn phải qua chính sách kiểm soát dữ liệu nhạy cảm.

### 2.4. Nội dung raw trong custom validation message

Một custom validator đôi khi tự tạo message như:

~~~java
context.buildConstraintViolationWithTemplate(
        "Invalid token: " + tokenFromRequest);
~~~

Đây là **một ví dụ sai**: dù bạn không đọc `rejectedValue`, `FieldError#getDefaultMessage()` sau đó cũng có thể chứa chính token. Do đó **chỉ loại bỏ field `rejectedValue` khỏi JSON chưa đủ**.

Biện pháp chắc chắn hơn: public message đến từ **catalog đáng tin cậy** được chọn theo mã đã whitelist, không lấy tùy tiện bất kỳ default message nào từ exception/provider. Nếu product phải hiển thị một số custom validation messages, duy trì danh sách message codes được review, không ghép raw input.

## 3. Phân loại dữ liệu: nên giữ, cân nhắc, hoặc loại bỏ

| Dữ liệu | Chính sách public API | Lý do |
| --- | --- | --- |
| Mã nghiệp vụ `INVALID_EMAIL`, `REQUIRED` | Giữ | Ổn định, client xử lý được |
| HTTP status 400/422/500 phù hợp | Giữ | Đúng ý nghĩa HTTP |
| Field path `contacts[0].priority` | Giữ **nếu được allowlist/canonicalize** | UI cần đánh dấu phần tử |
| Nguồn `body`/`form`/`query` | Giữ | Không mơ hồ giữa các nguồn |
| Thông báo do server chọn từ message catalog | Giữ | Hữu ích và có thể đa ngữ |
| Ngưỡng public `min=1` | Chỉ giữ nếu được xét duyệt | Có thể giúp UX, không phải luôn cần |
| Map key nằm trong path | Xem xét/che | Map key có thể là email/token |
| `rejectedValue` / `invalidValue` | **Không trả** | Có thể chứa secret/PII |
| Raw `ObjectError#getArguments()` | **Không trả** | Có thể mang metadata/value nội bộ |
| Full `ConstraintViolation` / `BindingResult` | **Không trả** | Không phải DTO public |
| Regex, internal validation group, payload | Mặc định **không trả** | Có thể lộ chính sách nội bộ |
| Exception class/method/stack trace | **Không trả** | Hỗ trợ tấn công, không hữu ích cho người dùng |
| Raw SQL, hostname, file path, connection string | **Không trả** | Làm lộ cấu hình hệ thống |
| Access token, cookie, Authorization header | **Không trả, không log raw** | Bí mật xác thực |
| Correlation/trace ID do server tạo | Có thể giữ | Giúp hỗ trợ nếu không lộ secret |
| Error timestamp | Tùy contract | Ít rủi ro nhưng không tự giải quyết lỗi |
| Toàn bộ request body | **Không trả lại** | Client đã có input; lặp lại tạo rủi ro |

Quan trọng: `path` dù trông giống “metadata” cũng có thể chứa dữ liệu do client điều khiển, ví dụ `contacts[private-email@example.com].email`. Đừng áp một quy tắc đơn giản “value là nhạy cảm, path luôn an toàn”. Path được công bố phải có grammar và giới hạn.

## 4. Thiết kế một hợp đồng lỗi tối thiểu và an toàn

Ví dụ dùng `ProblemDetail` (RFC 9457):

~~~json
{
  "type": "urn:problem:invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Review the indicated fields.",
  "code": "INVALID_REQUEST",
  "issues": [
    {
      "code": "INVALID_FORMAT",
      "path": "password",
      "location": "body",
      "message": "Value has an invalid format"
    }
  ]
}
~~~

Trong thiết kế này:

1. `type` định danh loại lỗi, không chứa URI với query string có secrets.
2. `status` phân biệt lỗi do client (400) với lỗi server (500).
3. `detail` là câu tổng quát từ ứng dụng, không lấy từ `Exception#getMessage()`.
4. `code` là mã lỗi ổn định cho toàn response.
5. `issues` là danh sách các lỗi an toàn đã được chọn lọc.
6. `issues[*].code` chỉ đến từ allowlist, ví dụ `REQUIRED`, `INVALID_EMAIL`, `INVALID_FORMAT`, `BELOW_MIN`, `INVALID_TYPE`.
7. `issues[*].path` chứa field name/path đã được phê duyệt, không phải raw Java property path tùy ý.
8. `issues[*].message` do `MessageSource` tra từ code ổn định, không đưa rejected values vào arguments.

**Không nhất thiết phải trả cả path cho mọi lỗi.** Với JSON malformed, backend có thể không xác định field an toàn, nên trả issue ở `path=""` / `location="body"`. Với lỗi return-value hoặc cấu hình Bean Validation phía server, không trả danh sách field nội bộ.

### 4.1. Mã lỗi public không phải toàn bộ Spring error codes

`FieldError#getCodes()` có thể chứa `Pattern.registrationInput.password`, `Pattern.password`, `Pattern.java.lang.String`, `Pattern`. Một phần trong các code này lộ tên Java class/object. Chọn một mã public:

~~~text
Pattern     -> INVALID_FORMAT
NotBlank    -> REQUIRED
NotNull     -> REQUIRED
Email       -> INVALID_EMAIL
Min         -> BELOW_MIN
Size        -> INVALID_LENGTH
typeMismatch -> INVALID_TYPE
unknown     -> INVALID_VALUE
~~~

Ánh xạ này là **API policy**, không phải bảng mapping mặc định của Spring. Với custom constraints, đưa mã riêng vào allowlist sau khi review; đừng serialize `error.getCodes()` nguyên dạng.

### 4.2. Path phải có schema công khai

Demo chỉ công bố:
- `email`, `password`, `apiToken`.
- `contacts[0].name`, `contacts[0].priority`, … với index nhỏ.
- `count` trong query.
- `path=""` nếu lỗi ở body tổng thể hoặc không có tên public được chấp nhận.

Các field khác trở thành `field` hoặc `parameter` thay vì echo một path chưa review. Với hệ thống có hundreds of DTOs, xây metadata-driven allowlist từ API schema, tránh hard-code tùy tiện; **nhưng không thay allowlist bằng “lấy bất kỳ reflection property nào”**.

### 4.3. Chỉ lưu số lượng issues cần thiết

Đối với request ác ý có hàng nghìn phần tử không hợp lệ, bộ lỗi đầy đủ có thể tốn memory và băng thông. Hãy có policy:
- Sắp xếp các issues an toàn và ổn định.
- Giới hạn số vấn đề trả về, ví dụ tối đa 50, và thêm cờ `truncated=true` nếu cần.
- Không tạo message từ raw values để “giải thích hơn”.
- Bảo đảm framework input-size/collection-count limits hoạt động trước bước tạo issues.

Project demo để logic dễ thấy, không cố đóng vai trò một API gateway hoàn chỉnh.

## 5. Ngữ cảnh exception trong Spring MVC 6.1+/6.2

### 5.1. `MethodArgumentNotValidException`

Thường xảy ra khi `@Valid @RequestBody` hoặc `@Valid @ModelAttribute` kiểm tra một command object mà không có `BindingResult` ngay sau. Đọc:

~~~java
BindingResult binding = ex.getBindingResult();
for (ObjectError error : binding.getAllErrors()) {
    // Lấy mã, field name sau khi kiểm tra allowlist.
    // Không đọc rejectedValue để đưa vào response.
}
~~~

`getAllErrors()` bao gồm field và global/object errors. Dùng `getFieldErrors()` nếu chỉ cần field errors, nhưng lúc đó phải xử lý global errors riêng để không bỏ sót.

### 5.2. `HandlerMethodValidationException`

Từ Spring Framework 6.1, direct method constraints như `@Min` trên `@RequestParam` hoặc return method có thể kích hoạt built-in MVC method validation.

~~~java
@GetMapping("/api/limits")
public Map<String, Integer> check(
        @RequestParam(name = "count")
        @Min(1) int count) {
    return Map.of("count", count);
}
~~~

Lỗi `count=0` thường trả HTTP 400/`HandlerMethodValidationException`. Vi phạm constraint trên **giá trị trả về** là lỗi 500, không phải input sai.

Với `ex.getParameterValidationResults()`, Spring cung cấp `ParameterValidationResult`, có `getMethodParameter()`, `getResolvableErrors()` và metadata container index/key. Với nested DTO errors, một result có thể là `ParameterErrors` với `getFieldErrors()`. Trong một implementation tổng quát, phải phân loại các parameter kinds (query/header/path/body/form) thay vì xem mọi result là query.

**Không xuất `getArgument()` hoặc raw `MessageSourceResolvable#getArguments()`**. Chúng có thể chứa giá trị không đáng tin cậy, object hoặc metadata framework.

### 5.3. Lỗi JSON parsing, missing parameter, type mismatch

`HttpMessageNotReadableException` cho JSON malformed/unreadable; `MethodArgumentTypeMismatchException` cho query value không chuyển được; `MissingServletRequestParameterException` cho missing required query parameter. Những loại lỗi này xảy ra **trước hoặc ngoài** Bean Validation trên DTO và thường không có `FieldError`.

Đừng cố ép chúng về `ConstraintViolation` hoặc trả parser exception message. Thay vào đó dùng các mã tổng quát:
- `INVALID_JSON`: request body không đọc được.
- `INVALID_TYPE`: query/form input sai kiểu.
- `MISSING_PARAMETER`: thiếu tham số bắt buộc.
- `INTERNAL_ERROR`: lỗi xử lý nội bộ.

### 5.4. Không lẫn Bean Validation với authorization

Dù dữ liệu vượt qua `@Valid`, backend vẫn phải kiểm tra quyền sở hữu, business invariants và permission. Nếu request đưa `role=ADMIN`, không “che giá trị đó trong response” rồi coi là xong; trước hết phải **không bind property nhạy cảm** vào object ứng dụng. Với form binding dùng DTO riêng và `setAllowedFields`; với JSON `@RequestBody`, Jackson deserialize theo DTO/config JSON, không dùng allowlist của form theo cùng cách.

## 6. Project runnable: Spring Boot 3.5.7, Java 17

Ví dụ có đủ:
- JSON `@Valid @RequestBody` chứa password và API token cố tình sai.
- Form URL-encoded có indexed field và type mismatch.
- Query `@Min` có method validation.
- JSON malformed, required parameter missing.
- Return-value constraint sai phía server.
- Một `@RestControllerAdvice` **chỉ xây public DTO từ dữ liệu đã lọc**.
- `MessageSource` cho tiếng Anh/tiếng Việt.
- JUnit/MockMvc integration tests khẳng định response **không chứa chuỗi secret hoặc exception internals**.

Không cần database. Các secret trong test chỉ là **chuỗi giả lập**, không dùng mật khẩu/token thật.

### 6.1. Cây thư mục

~~~text
pom.xml
src/main/java/com/example/safeerrors/
  SafeErrorsApplication.java
  ContactInput.java
  RegistrationInput.java
  PublicIssue.java
  RegistrationController.java
  SafeErrorAdvice.java
src/main/resources/
  messages.properties
  messages_vi.properties
src/test/java/com/example/safeerrors/
  SafeErrorAdviceIntegrationTest.java
  SafeErrorMappingTest.java
~~~

### 6.2. `pom.xml`

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
    <artifactId>safe-validation-errors</artifactId>
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

Ví dụ dùng Servlet Spring MVC (`spring-boot-starter-web`), **không phải WebFlux**. `spring-boot-starter-validation` cung cấp Jakarta Bean Validation provider. Các tests dùng `@SpringBootTest @AutoConfigureMockMvc` để kiểm tra exception resolution thật của MVC thay vì chỉ kiểm tra một helper.

### 6.3. Main application

~~~java
// src/main/java/com/example/safeerrors/SafeErrorsApplication.java
package com.example.safeerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeErrorsApplication.class, args);
    }
}
~~~

### 6.4. DTO nested

~~~java
// src/main/java/com/example/safeerrors/ContactInput.java
package com.example.safeerrors;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class ContactInput {

    @NotBlank
    private String name;

    @Min(1)
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

`@Min(1)` cho phép `null`; nếu priority bắt buộc, thêm `@NotNull`. Bài này để riêng lỗi `typeMismatch` khi form gửi chữ vào Integer: conversion thất bại trước khi constraint có một số hợp lệ.

### 6.5. DTO có thông tin nhạy cảm

~~~java
// src/main/java/com/example/safeerrors/RegistrationInput.java
package com.example.safeerrors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import java.util.ArrayList;
import java.util.List;

public class RegistrationInput {

    @NotBlank
    @Email
    private String email;

    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9]{12,64}",
             message = "Internal password-format rule failed")
    private String password;

    @NotBlank
    @Pattern(regexp = "[A-Z0-9]{8,32}",
             message = "Internal API-token rule failed")
    private String apiToken;

    @Valid
    private List<ContactInput> contacts = new ArrayList<>();

    public RegistrationInput() {}

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

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

Đây là **demo giả lập**, không phải thiết kế chính sách mật khẩu production: regex nêu trong ví dụ chỉ tạo lỗi có thể kiểm thử, không thay thế công nghệ lưu mật khẩu an toàn, breach checks, hashing, MFA hay credential policy.

Hai message trên `@Pattern` được cố tình đặt là **thông điệp nội bộ**. Advice sẽ **không bao giờ dùng `FieldError#getDefaultMessage()` để trả chúng**; thay bằng `error.INVALID_FORMAT` do server quản lý. Test xác minh không có cụm `Internal password-format rule failed` hay `Internal API-token rule failed` trong body.

Để bảo vệ thực tế, không bao giờ ghi password hoặc API token vào logs/traces; khi xử lý thành công, dùng thiết kế lưu trữ/tạo secret chuyên biệt, không đặt chúng trong response.

### 6.6. Controller mô tả các nguồn lỗi

~~~java
// src/main/java/com/example/safeerrors/RegistrationController.java
package com.example.safeerrors;

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
        binder.setAutoGrowCollectionLimit(10);
    }

    @PostMapping(path = "/api/register",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> registerJson(
            @Valid @RequestBody RegistrationInput body) {
        return Map.of("accepted", true);
    }

    @PostMapping(path = "/api/register/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> registerForm(
            @Valid @ModelAttribute("registrationForm")
            RegistrationInput form) {
        return Map.of("accepted", true);
    }

    @GetMapping("/api/limits")
    public Map<String, Integer> getLimit(
            @RequestParam(name = "count") @Min(1) int count) {
        return Map.of("count", count);
    }

    @GetMapping("/api/broken")
    @NotBlank
    public String brokenReturn() {
        return "";
    }
}
~~~

Không có `@Validated` cấp controller class, để dùng **built-in method validation từ Spring MVC 6.1**. `@InitBinder` chỉ giới hạn **property binding của form**, không kiểm soát Jackson JSON deserialization của `@RequestBody`. DTO được giữ nhỏ và chỉ có các input dự kiến; trong code production, đừng đưa role/owner/payment state vào public DTO.

Method `brokenReturn()` cố tình vi phạm return-value constraint và phải được coi là lỗi server (HTTP 500). Advice bên dưới **không tiết lộ tên method/constraint hay giá trị trả về**.

### 6.7. Record của issue công khai

~~~java
// src/main/java/com/example/safeerrors/PublicIssue.java
package com.example.safeerrors;

public record PublicIssue(
        String code,
        String path,
        String location,
        String message) {
}
~~~

Record này **không có** property `rejectedValue`, `invalidValue`, `cause`, `exception` hoặc `arguments`. Việc loại bỏ dữ liệu nhạy cảm được đảm bảo ở mức schema, không phải bằng cách gọi Jackson `@JsonIgnore` lên một object framework mà ứng dụng không sở hữu.

### 6.8. Advice: chỉ chọn dữ liệu đã qua allowlist

~~~java
// src/main/java/com/example/safeerrors/SafeErrorAdvice.java
package com.example.safeerrors;

import org.springframework.context.MessageSource;
import org.springframework.context.MessageSourceResolvable;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
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

    public SafeErrorAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> objectValidation(
            MethodArgumentNotValidException ex) {

        String location = ex.getParameter()
                .hasParameterAnnotation(ModelAttribute.class)
                ? "form" : "body";

        List<PublicIssue> issues = new ArrayList<>();
        for (ObjectError error :
                ex.getBindingResult().getAllErrors()) {
            issues.add(fromObjectError(
                    error, location, messages,
                    LocaleContextHolder.getLocale()));
        }
        return badRequest("INVALID_REQUEST", issues);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> methodValidation(
            HandlerMethodValidationException ex) {

        if (ex.isForReturnValue()) {
            // Return-value violation: phía server, tuyệt đối
            // không xuất raw method/return validation metadata.
            return internalFailure();
        }

        List<PublicIssue> issues = new ArrayList<>();

        for (ParameterValidationResult result :
                ex.getParameterValidationResults()) {

            MethodParameter parameter =
                    result.getMethodParameter();
            String location = publicLocation(parameter);

            if (result instanceof ParameterErrors nested) {
                for (ObjectError error : nested.getAllErrors()) {
                    issues.add(fromObjectError(
                            error, location, messages,
                            LocaleContextHolder.getLocale()));
                }
            } else {
                String path = publicParameterName(parameter);
                for (MessageSourceResolvable error :
                        result.getResolvableErrors()) {

                    String code = publicCode(error.getCodes());
                    issues.add(new PublicIssue(
                            code, path, location,
                            publicMessage(messages, code,
                                    LocaleContextHolder.getLocale())));
                }
            }
        }

        // Cross-parameter errors không gắn bừa với một field.
        for (MessageSourceResolvable error :
                ex.getCrossParameterValidationResults()) {
            issues.add(new PublicIssue(
                    "INVALID_VALUE", "", "crossParameter",
                    publicMessage(messages, "INVALID_VALUE",
                            LocaleContextHolder.getLocale())));
        }

        return badRequest("INVALID_REQUEST", issues);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ProblemDetail> queryType(
            MethodArgumentTypeMismatchException ex) {

        // Không dùng ex.getValue() hoặc ex.getMessage().
        String path = publicField(ex.getName());
        return badRequest("INVALID_REQUEST",
                List.of(new PublicIssue(
                        "INVALID_TYPE", path, "query",
                        publicMessage(messages, "INVALID_TYPE",
                                LocaleContextHolder.getLocale()))));
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ProblemDetail> missingQuery(
            MissingServletRequestParameterException ex) {

        return badRequest("INVALID_REQUEST",
                List.of(new PublicIssue(
                        "MISSING_PARAMETER",
                        publicField(ex.getParameterName()),
                        "query",
                        publicMessage(messages, "MISSING_PARAMETER",
                                LocaleContextHolder.getLocale()))));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ProblemDetail> invalidJson(
            HttpMessageNotReadableException ex) {

        // Không dùng ex.getMostSpecificCause()
        // hay parser location/excerpt làm public response.
        return badRequest("INVALID_JSON",
                List.of(new PublicIssue(
                        "INVALID_JSON", "", "body",
                        publicMessage(messages, "INVALID_JSON",
                                LocaleContextHolder.getLocale()))));
    }

    private ResponseEntity<ProblemDetail> badRequest(
            String code, List<PublicIssue> issues) {

        ProblemDetail detail =
                ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);

        detail.setType(URI.create("urn:problem:invalid-request"));
        detail.setTitle("Invalid request");
        detail.setDetail("Review the indicated fields.");
        detail.setProperty("code", code);

        List<PublicIssue> safeSorted = issues.stream()
                .sorted(Comparator
                        .comparing(PublicIssue::location)
                        .thenComparing(PublicIssue::path)
                        .thenComparing(PublicIssue::code))
                .toList();
        detail.setProperty("issues", safeSorted);

        return ResponseEntity.badRequest().body(detail);
    }

    private static ResponseEntity<ProblemDetail> internalFailure() {
        ProblemDetail detail =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);

        detail.setType(URI.create("urn:problem:internal-error"));
        detail.setTitle("Internal error");
        detail.setDetail("The service could not complete the request.");
        detail.setProperty("code", "INTERNAL_ERROR");
        detail.setProperty("issues", List.of());

        return ResponseEntity.status(
                HttpStatus.INTERNAL_SERVER_ERROR).body(detail);
    }

    // Package-private để test riêng với một FieldError có secret.
    static PublicIssue fromObjectError(
            ObjectError error,
            String location,
            MessageSource messages,
            Locale locale) {

        String code = publicCode(error.getCode());
        String path = error instanceof FieldError field
                ? publicField(field.getField())
                : "";

        // Không đọc error.getDefaultMessage(),
        // error.getArguments() hoặc field.getRejectedValue().
        return new PublicIssue(
                code, path, location,
                publicMessage(messages, code, locale));
    }

    static String publicCode(String sourceCode) {
        if (sourceCode == null) {
            return "INVALID_VALUE";
        }

        return switch (sourceCode) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED";
            case "Email" -> "INVALID_EMAIL";
            case "Pattern" -> "INVALID_FORMAT";
            case "Size" -> "INVALID_LENGTH";
            case "Min" -> "BELOW_MIN";
            case "typeMismatch" -> "INVALID_TYPE";
            default -> "INVALID_VALUE";
        };
    }

    private static String publicCode(String[] candidateCodes) {
        if (candidateCodes == null) {
            return "INVALID_VALUE";
        }
        // Spring thường sắp mã cụ thể trước, tổng quát sau.
        for (int i = candidateCodes.length - 1; i >= 0; i--) {
            String code = publicCode(candidateCodes[i]);
            if (!"INVALID_VALUE".equals(code)) {
                return code;
            }
        }
        return "INVALID_VALUE";
    }

    private static String publicField(String field) {
        if (field == null) {
            return "field";
        }

        if ("email".equals(field)
                || "password".equals(field)
                || "apiToken".equals(field)
                || "count".equals(field)) {
            return field;
        }

        if (field.matches(
                "contacts\\[(0|[1-9][0-9]?)\\]\\.(name|priority)")) {
            return field;
        }
        return "field";
    }

    private static String publicLocation(
            MethodParameter parameter) {
        if (parameter.hasParameterAnnotation(RequestParam.class)) {
            return "query";
        }
        if (parameter.hasParameterAnnotation(PathVariable.class)) {
            return "path";
        }
        if (parameter.hasParameterAnnotation(RequestHeader.class)) {
            return "header";
        }
        if (parameter.hasParameterAnnotation(RequestBody.class)) {
            return "body";
        }
        if (parameter.hasParameterAnnotation(ModelAttribute.class)) {
            return "form";
        }
        return "parameter";
    }

    private static String publicParameterName(
            MethodParameter parameter) {
        RequestParam annotation =
                parameter.getParameterAnnotation(RequestParam.class);

        if (annotation == null) {
            return "parameter";
        }

        String name = annotation.name().isBlank()
                ? annotation.value() : annotation.name();

        return publicField(name);
    }

    private static String publicMessage(
            MessageSource messages,
            String code,
            Locale locale) {

        return messages.getMessage(
                "error." + code,
                null,
                "Invalid input",
                locale);
    }
}
~~~

**Đặc điểm bảo mật của code:**
- `fromObjectError(...)` hoàn toàn **không chạm vào rejected value** hoặc message do custom constraint tự tạo.
- `publicCode(...)` và `publicField(...)` là **positive allowlists**, không cố “xóa từ nhạy cảm” trong một string vốn có thể chứa rất nhiều biến thể.
- `publicMessage(...)` lấy text từ **server-owned resource bundle**, không phải dữ liệu request.
- JSON parsing errors không xuất Jackson raw exception.
- Return validation errors được chuyển thành HTTP 500 không có chi tiết method, field hay giá trị.
- `ProblemDetail` chỉ chứa chuẩn fields và extensions mà ứng dụng chủ động set.
- Không log raw exception messages hoặc user input trong code trên.
- Spring có thể tự bổ sung field `instance` của RFC 9457 trong rendering. Trong hệ thống production, nếu URL path chứa giá trị riêng tư, cần **đánh giá cả `instance` và access logs**: không xem ProblemDetail mặc định là đảm bảo ẩn mọi dữ liệu về URL.

**Lưu ý về path:** ứng dụng đã kiểm tra chỉ số `contacts[0]` đến `contacts[99]`. Nếu cần danh sách lớn hơn, điều chỉnh grammar/giới hạn theo public API contract và không đưa email/token bên trong Map keys ra ngoài. Trong WebFlux, API path/container metadata có thể khác, xem mục 10.

### 6.9. Resource bundles cho message được kiểm duyệt

**`src/main/resources/messages.properties`:**

~~~properties
error.REQUIRED=This field is required
error.INVALID_EMAIL=Enter a valid email address
error.INVALID_FORMAT=Value has an invalid format
error.INVALID_LENGTH=Value has an invalid length
error.BELOW_MIN=Value is below the permitted minimum
error.INVALID_TYPE=Value has an invalid type
error.MISSING_PARAMETER=A required parameter is missing
error.INVALID_JSON=Request body is not valid JSON
error.INVALID_VALUE=Invalid value
~~~

**`src/main/resources/messages_vi.properties`:**

~~~properties
error.REQUIRED=Trường này là bắt buộc
error.INVALID_EMAIL=Địa chỉ email không hợp lệ
error.INVALID_FORMAT=Giá trị sai định dạng
error.INVALID_LENGTH=Độ dài giá trị không hợp lệ
error.BELOW_MIN=Giá trị nhỏ hơn ngưỡng cho phép
error.INVALID_TYPE=Giá trị sai kiểu dữ liệu
error.MISSING_PARAMETER=Thiếu tham số bắt buộc
error.INVALID_JSON=Nội dung JSON không hợp lệ
error.INVALID_VALUE=Giá trị không hợp lệ
~~~

Khi client chọn tiếng Việt qua locale của request, **mã `INVALID_FORMAT` giữ nguyên**, chỉ message đổi ngôn ngữ. Trong code này `publicMessage` dùng `LocaleContextHolder.getLocale()` thông qua Spring MVC request context, và có default an toàn nếu thiếu key. Trong ứng dụng WebFlux/reactive chain, phải quan tâm tới locale propagation riêng, không dùng ThreadLocal một cách tùy tiện.

## 7. JUnit/MockMvc: kiểm tra trực tiếp không rò bí mật

Đừng chỉ assert HTTP 400. Một bài test bảo mật phải cố tình gửi input có giá trị nhận diện rõ, rồi **đọc toàn bộ response body** và xác minh giá trị đó không xuất hiện. Nên kết hợp assertions dương (có mã/path hữu ích) và assertions âm (không có secret/exception internals).

### 7.1. HTTP integration tests

~~~java
// src/test/java/com/example/safeerrors/SafeErrorAdviceIntegrationTest.java
package com.example.safeerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Locale;

import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeErrorAdviceIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidJsonDtoDoesNotEchoPasswordOrToken()
            throws Exception {

        mvc.perform(post("/api/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "email":"not-an-email_PRIVATE",
                      "password":"SECRET-password-123!",
                      "apiToken":"TOKEN-secret-456!",
                      "contacts":[{"name":"","priority":0}]
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_REQUEST"))
            .andExpect(jsonPath("$.issues[*].path", hasItems(
                    "email",
                    "password",
                    "apiToken",
                    "contacts[0].name",
                    "contacts[0].priority")))
            .andExpect(content().string(not(
                    containsString("SECRET-password-123!"))))
            .andExpect(content().string(not(
                    containsString("TOKEN-secret-456!"))))
            .andExpect(content().string(not(
                    containsString("not-an-email_PRIVATE"))))
            .andExpect(content().string(not(
                    containsString("Internal password-format rule"))))
            .andExpect(content().string(not(
                    containsString("Internal API-token rule"))))
            .andExpect(content().string(not(
                    containsString("rejectedValue"))));
    }

    @Test
    void formTypeMismatchIsSafeAndKeepsFieldPath()
            throws Exception {

        mvc.perform(post("/api/register/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "valid@example.com")
                .param("password", "SECRET-password-123!")
                .param("apiToken", "VALIDTOKEN99")
                .param("contacts[0].name", "Lan")
                .param("contacts[0].priority",
                        "not-a-number-PRIVATE"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[*].path", hasItems(
                    "password", "contacts[0].priority")))
            .andExpect(jsonPath("$.issues[*].code", hasItems(
                    "INVALID_FORMAT", "INVALID_TYPE")))
            .andExpect(content().string(not(
                    containsString("SECRET-password-123!"))))
            .andExpect(content().string(not(
                    containsString("not-a-number-PRIVATE"))))
            .andExpect(content().string(not(
                    containsString("typeMismatch.registration"))));
    }

    @Test
    void directMinConstraintShowsCodeWithoutInternalArgument()
            throws Exception {

        mvc.perform(get("/api/limits").param("count", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].path")
                    .value("count"))
            .andExpect(jsonPath("$.issues[0].location")
                    .value("query"))
            .andExpect(jsonPath("$.issues[0].code")
                    .value("BELOW_MIN"));
    }

    @Test
    void malformedNumericQueryNeverEchoesValue()
            throws Exception {

        mvc.perform(get("/api/limits")
                .param("count", "SECRET-QUERY-999"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("INVALID_TYPE"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("count"))
            .andExpect(content().string(not(
                    containsString("SECRET-QUERY-999"))))
            .andExpect(content().string(not(
                    containsString("NumberFormatException"))));
    }

    @Test
    void missingRequiredParameterDoesNotRevealMethodName()
            throws Exception {

        mvc.perform(get("/api/limits"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("MISSING_PARAMETER"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("count"))
            .andExpect(content().string(not(
                    containsString("RegistrationController"))));
    }

    @Test
    void malformedJsonNeverEchoesParserExcerpt()
            throws Exception {

        mvc.perform(post("/api/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"password":"SECRET-IN-BROKEN-JSON",
                     "apiToken":"SECRET-IN-PARSER",
                     "contacts":[
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"))
            .andExpect(content().string(not(
                    containsString("SECRET-IN-BROKEN-JSON"))))
            .andExpect(content().string(not(
                    containsString("SECRET-IN-PARSER"))))
            .andExpect(content().string(not(
                    containsString("JsonParseException"))));
    }

    @Test
    void badServerReturnIs500WithoutInternalDetails()
            throws Exception {

        mvc.perform(get("/api/broken"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
            .andExpect(jsonPath("$.issues.length()").value(0))
            .andExpect(content().string(not(
                    containsString("brokenReturn"))))
            .andExpect(content().string(not(
                    containsString("HandlerMethodValidationException"))));
    }

    @Test
    void vietnameseMessageUsesSameStableCode()
            throws Exception {

        mvc.perform(post("/api/register")
                .locale(Locale.forLanguageTag("vi"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"","password":"ValidPassword1234",
                     "apiToken":"VALIDTOKEN99"}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("REQUIRED"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("email"))
            .andExpect(jsonPath("$.issues[0].message")
                    .value("Trường này là bắt buộc"));
    }

    @Test
    void validBodyAndQueryReturnSuccess() throws Exception {

        mvc.perform(post("/api/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"lan@example.com",
                     "password":"ValidPassword1234",
                     "apiToken":"VALIDTOKEN99",
                     "contacts":[{"name":"Lan","priority":1}]}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.accepted").value(true));

        mvc.perform(get("/api/limits").param("count", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(2));
    }
}
~~~

Các test **không assert raw exception messages**. Chúng assert mã lỗi và paths được công bố, đồng thời xác minh chuỗi secret giả lập, raw parser errors và internal validation messages **không có mặt** trong response.

### 7.2. Unit test với FieldError chứa rejectedValue và defaultMessage độc hại

Integration test có thể đi qua nhiều tầng framework. Unit test sau kiểm tra thẳng **hàm mapping** được thiết kế để loại bỏ dữ liệu thô:

~~~java
// src/test/java/com/example/safeerrors/SafeErrorMappingTest.java
package com.example.safeerrors;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.validation.FieldError;

import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class SafeErrorMappingTest {

    @Test
    void mapperIgnoresRejectedValueAndUntrustedMessage()
            throws Exception {

        String secret = "PRIVATE-REJECTED-PASSWORD";
        FieldError raw = new FieldError(
                "registrationInput",
                "password",
                secret,
                false,
                new String[]{"Pattern"},
                null,
                "UNSAFE default message contains " + secret);

        StaticMessageSource catalog = new StaticMessageSource();
        catalog.addMessage("error.INVALID_FORMAT",
                Locale.ENGLISH, "Value has an invalid format");

        PublicIssue safe = SafeErrorAdvice.fromObjectError(
                raw, "body", catalog, Locale.ENGLISH);

        String json = new ObjectMapper()
                .writeValueAsString(safe);

        assertEquals("INVALID_FORMAT", safe.code());
        assertEquals("password", safe.path());
        assertEquals("Value has an invalid format",
                safe.message());

        assertFalse(json.contains(secret));
        assertFalse(json.contains("UNSAFE default message"));
        assertFalse(json.contains("rejectedValue"));
    }

    @Test
    void unapprovedFieldPathIsReplaced()
            throws Exception {

        FieldError raw = new FieldError(
                "registrationInput",
                "contacts[private-email@example.com].name",
                "private-data",
                false,
                new String[]{"NotBlank"},
                null,
                "private-data");

        StaticMessageSource catalog = new StaticMessageSource();
        catalog.addMessage("error.REQUIRED",
                Locale.ENGLISH, "This field is required");

        PublicIssue safe = SafeErrorAdvice.fromObjectError(
                raw, "body", catalog, Locale.ENGLISH);

        assertEquals("field", safe.path());
        String json = new ObjectMapper()
                .writeValueAsString(safe);
        assertFalse(json.contains("private-email@example.com"));
        assertFalse(json.contains("private-data"));
    }
}
~~~

**Kết quả dự kiến:** 11 JUnit tests PASS (9 tests HTTP và 2 tests mapper) với project như đã khai báo. Đây là kết quả dự kiến dựa trên static code/API analysis, **không phải tuyên bố đã chạy Maven thực tế**.

Lệnh chạy:

~~~bash
mvn test
~~~

Chạy chỉ các test bảo mật:

~~~bash
mvn -Dtest=SafeErrorMappingTest,SafeErrorAdviceIntegrationTest test
~~~

Không sử dụng secret thật trong test, ngay cả ở CI. Các chuỗi mô phỏng như `PRIVATE-REJECTED-PASSWORD` đủ giúp kiểm thử leak mà không tạo nguy cơ dữ liệu nhạy cảm thật trong logs/test reports.

### 7.3. Curl để thử ứng dụng

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -i -X POST http://localhost:8080/api/register \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"email":"bad-email","password":"SECRET-password-123!","apiToken":"VALIDTOKEN99"}'
~~~

Response kỳ vọng là 400, có `code="INVALID_REQUEST"` và các issue có mã như `INVALID_EMAIL`, `INVALID_FORMAT`, nhưng **không** xuất `SECRET-password-123!`. Đừng gửi mật khẩu thật vào trang demo hoặc chia sẻ request chứa credentials qua công cụ không được phép.

## 8. Các anti-patterns cần loại bỏ

### 8.1. Serialize trực tiếp lỗi framework

~~~java
// KHÔNG LÀM:
return ResponseEntity.badRequest()
        .body(ex.getBindingResult());
~~~

Vì `BindingResult` không phải public schema và có thể giữ `rejectedValue`, raw property values hoặc nhiều fields không mong muốn.

~~~java
// KHÔNG LÀM:
return ResponseEntity.badRequest()
        .body(ex.getBindingResult().getFieldErrors());
~~~

Ngay cả khi chỉ lấy `FieldError`, đối tượng vẫn giữ raw rejected value. Thay bằng `PublicIssue` do ứng dụng sở hữu.

### 8.2. Trả raw exception message

~~~java
// KHÔNG LÀM:
return Map.of("message", exception.getMessage());
~~~

Message có thể phản ánh package/class, method signature, JSON snippet, SQL hoặc user input. Chỉ trả message code đã whitelist và text được server kiểm duyệt.

### 8.3. Trả `getDefaultMessage()` cho mọi trường hợp

~~~java
// CHƯA ĐỦ AN TOÀN CHO MỌI HỆ THỐNG:
String publicMessage = error.getDefaultMessage();
~~~

Với built-in constraints mà messages được kiểm soát, `getDefaultMessage()` có thể phù hợp. Nhưng trong hệ thống mở có custom validators, annotations từ thư viện thứ ba, dynamic interpolation, hoặc message đã ghép user input, **không thể mặc định tin tưởng**. Chiến lược mạnh hơn là ánh xạ `sourceCode → publicCode → messageCatalog` như demo. Nếu quyết định cho phép một số default messages, đặt policy cụ thể theo nguồn và test dữ liệu nhạy cảm.

### 8.4. Dùng regex “tẩy secret” trên exception string

~~~java
// KHÔNG NÊN:
String safe = exception.getMessage()
        .replaceAll("password=[^, ]+", "password=***");
~~~

Cách này không phát hiện mọi dạng secret (JSON escaped, URL-encoded, quotes, nested arrays, base64, multiline, custom key names, nhiều ngôn ngữ). **Không nhận raw exception text rồi cố xóa các đoạn nhạy cảm**; hãy chỉ xây response từ những fields được phê duyệt ngay từ đầu.

### 8.5. Trả headers hoặc request body để “giúp debug”

Các headers như `Authorization`, `Cookie`, `X-API-Key`, `Set-Cookie` và query parameters có thể chứa credentials. Không đưa `request.getHeaderNames()` rồi trả toàn bộ key/value pairs. Nếu thực sự cần một request identifier, sử dụng ID do server tạo và được kiểm tra định dạng, không tin mọi giá trị mà client tự xưng là trace-id.

### 8.6. Bọc mọi exception thành HTTP 400

Nếu vi phạm constraint trên return value hoặc backend có lỗi configuration, trả 400 sẽ làm sai ngữ nghĩa, che mất sự cố production và đôi khi lộ chi tiết server. Tách validation input (thường 400) với lỗi server (500); ghi log server-side theo chính sách bảo mật.

## 9. Lưu log và telemetry mà không lộ input

Không trả secret trên HTTP chưa đủ nếu một `@ControllerAdvice` đồng thời:

~~~java
// KHÔNG LÀM:
logger.error("Validation failed: {}", exception.getMessage());
~~~

Đặc biệt, Spring `FieldError#toString()` và `BindException#getMessage()` có thể chứa rejected value. Logs có thể được gửi sang APM, analytics, third-party services hoặc hệ thống ít hạn chế quyền hơn dữ liệu gốc.

### Chính sách log được khuyến nghị

Chỉ ghi các thuộc tính đã được duyệt:

~~~java
// Minh họa, không thuộc project runnable ở mục 6.
log.info("request_rejected code={} issueCount={}",
        "INVALID_REQUEST", safeIssues.size());
~~~

Với audit/incident response cần thêm:
- Server-generated request/correlation ID.
- HTTP method và route template công khai (không raw query string).
- Status và mã lỗi đã chuẩn hóa.
- Số lượng issues, không phải raw failed values.
- Environment/service/version hữu ích bên trong observability system.
- Access controls, retention/TTL và encryption phù hợp.

**Không log password/token kể cả trong debug**. Không log request body của login/registration/payment endpoints. Với lỗi server, stack traces có thể cần thiết trong internal logs được bảo vệ, nhưng luôn xem xét khả năng secret nằm trong exception message/cause; sử dụng error aggregation có redaction/allowlist và kiểm tra sampling trước khi bật production.

### Correlation ID không phải secret

Một ID do backend tạo, ví dụ UUID v4, có thể được trả dưới field `requestId` để support tra cứu log. Nhưng đừng echo mọi `X-Request-ID` client gửi nếu có thể chứa dữ liệu tùy ý. Nếu sử dụng inbound correlation ID, phải kiểm tra format/length/character set và trust boundary. Không đặt raw URL với query token vào `instance` của `ProblemDetail`.

## 10. Tránh rò rỉ qua các tầng khác

### 10.1. `ProblemDetail.instance`

Spring có thể điền `ProblemDetail.instance` từ request path khi chưa được set. Với endpoint chứa thông tin riêng tư trực tiếp trong path, ví dụ `/reset/{secret}`, việc echo path vào response hoặc logs có thể rò secret. **Không thiết kế secret trong URL**; nếu hệ thống cũ đã có, override `instance` bằng giá trị không nhạy cảm hoặc không đưa raw path cho bên ngoài.

### 10.2. JSON serialization không an toàn

Không tạo error DTO chứa `Throwable`, `MethodParameter`, `BindingResult`, `ConstraintDescriptor` hoặc đối tượng domain rồi thêm `@JsonIgnore` ở vài fields. Một upgrade framework có thể làm xuất hiện getter mới, hoặc nested object không được ignore. Thiết kế **record/class dành riêng cho public error schema** là phương pháp dễ kiểm chứng hơn.

### 10.3. GraphQL, gRPC, WebSocket, RSocket

Nguyên tắc chỉ công bố mã lỗi/message và metadata an toàn vẫn áp dụng, dù response không phải HTTP ProblemDetail:
- GraphQL `errors[*].extensions` không nên chứa raw exception/internal state.
- gRPC status details cần schema rõ, không mang object framework thô.
- WebSocket error frames không mang raw request payload hoặc stack trace.
- RSocket application errors không để exception message tự do trở thành text công khai.

Mỗi transport có cách encoding, status mapping và trace handling riêng; không chép y nguyên `@RestControllerAdvice` của MVC vào nơi khác.

### 10.4. Spring WebFlux

Với WebFlux, object-only `@Valid @ModelAttribute` có thể ném `WebExchangeBindException`, còn method validation trong Spring WebFlux 6.1+ có thể ném `HandlerMethodValidationException`. Dùng exception handlers/reactive ResponseEntityExceptionHandler tương ứng với WebFlux, không import Servlet MVC handler.

Giữ quy tắc bảo mật:
- Không serialize `WebExchangeBindException.getBindingResult()`.
- Không gọi `FieldError#getRejectedValue()` để build body.
- Với `Mono<ResponseEntity<ProblemDetail>>`, xây body từ safe issues mà không block event loop.
- Locale trong reactive pipeline cần cơ chế context propagation phù hợp; đừng giả định ThreadLocal luôn theo cùng request.

### 10.5. Validation groups và cross-parameter constraints

`@Validated(Group.class)` chọn nhóm constraints; tên Java group có thể nội bộ. Không đưa class name, payload, raw group metadata ra ngoài. Với cross-parameter constraint, response có thể chỉ `path=""` và mã tổng quát hoặc `relatedFields` từ danh sách công khai, chứ không expose toàn bộ method signature.

## 11. Những vấn đề dễ bị bỏ sót trong kiểm thử

| Tình huống | Dữ liệu có thể rò | Assertion nên có |
| --- | --- | --- |
| Password không đạt `@Pattern` | `FieldError.rejectedValue` | Body không chứa marker password |
| API token sai | `ConstraintViolation.invalidValue` | Body không chứa marker token |
| Email không hợp lệ | Giá trị địa chỉ email | Body chỉ có path `email` + mã lỗi |
| Indexed form sai kiểu | `contacts[0].priority` + raw value | Giữ path, không có raw value |
| JSON malformed | Jackson parser excerpt | Có `INVALID_JSON`, không có parser details |
| Query sai kiểu | `MethodArgumentTypeMismatchException.value` | Có `INVALID_TYPE`, không echo query |
| Thiếu parameter | Java parameter/method details | Có `MISSING_PARAMETER` và tên public |
| Return validation thất bại | Value, method name, class | HTTP 500, issue list rỗng |
| Custom validator ghép input vào message | `defaultMessage` chứa input | Body lấy text từ catalog, không dùng default |
| Map key chứa email/token | Key nằm trong field path | Path canonicalize hoặc placeholder |
| Exception có nested cause | SQL/file paths/internal class | Không có stack trace/cause |
| Locale=vi/en | Message biến đổi | Public code không thay đổi |
| Log/APM | Raw request/exception | Unit/integration audit cho logging filters |
| Tối đa issues | Số lượng quá lớn | Giới hạn có chủ đích và test |
| Header secret | `Authorization`, `Cookie` | Không log/serialize |

Các negative tests nên kiểm tra **toàn response body**. Không chỉ kiểm tra rằng JSON không có property `rejectedValue`, vì secret có thể đã được nối vào `message`, `detail` hoặc `path`.

Đối với một số đường xử lý, response mặc định của framework có thể khác khi bật/tắt `server.error.include-message`, `server.error.include-binding-errors`, `server.error.include-stacktrace` hoặc custom error attributes. Test behavior trên **cấu hình production thực tế**, không chỉ unit test một mapper.

## 12. Deployment hardening và quản trị hợp đồng

### 12.1. Cấu hình error rendering

Spring Boot có các thuộc tính cho error attributes/rendering ở một số error paths, ví dụ:

~~~properties
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
~~~

Những thuộc tính này hữu ích khi dùng cơ chế lỗi của Boot, nhưng **không thay thế** việc sanitize một `@RestControllerAdvice` do ứng dụng viết. Nếu code của bạn return raw `FieldError` thì cấu hình above không tự xóa rejected value.

### 12.2. Review tài liệu API

Document rõ:
- `type`, `status`, `code` ở cấp response.
- Danh sách issue codes ổn định và trường hợp xuất hiện.
- Cú pháp `path` cho nested properties, index và object-level errors.
- Quy tắc `location`, cách xử lý cross-parameter.
- Cơ chế locale và chính sách fallback của `message`.
- Quy tắc không echo invalid values và exception diagnostics.
- Ngưỡng tối đa số issues, thứ tự sắp xếp và versioning.

Nếu client thực sự cần hiển thị lại input sau validation error, nó nên giữ state của form ở phía client. Không dùng backend như nơi trả lại nguyên password/token dưới dạng rejected values.

### 12.3. Security review và observability

OWASP Developer Guide khuyến nghị error messages đủ giúp người dùng hành động **nhưng không tiết lộ dữ liệu quan trọng hoặc internals**; MITRE CWE-209 mô tả chính kiểu điểm yếu này. Thực hiện review trên cả:
1. Response body và headers.
2. Standard/global exception handlers.
3. Application logs và request tracing.
4. Reverse proxy/API gateway logs.
5. Client telemetry/analytics.
6. Sentry/APM/error aggregation.
7. Test reports và CI artifacts.
8. Đường xử lý lỗi trên transports khác.

Một response an toàn không đảm bảo toàn hệ thống an toàn nếu reverse proxy vẫn ghi raw query strings chứa token. Giới hạn dữ liệu từ thiết kế API ban đầu: ưu tiên credentials trong headers/body thích hợp, tránh đưa secret vào URLs, nhưng vẫn không log raw header/body.

## 13. Checklist code review

- [ ] Public error schema do ứng dụng sở hữu, không trả `BindingResult`, `FieldError`, `ConstraintViolation` hoặc `Throwable`.
- [ ] Không serialize `getRejectedValue()`, `getInvalidValue()`, `getArgument()`, raw `getArguments()` hoặc provider descriptors.
- [ ] Không dùng `exception.getMessage()`/`getDefaultMessage()` chưa kiểm duyệt làm public text.
- [ ] Mã lỗi và field path có **allowlist**, không lộ Java class/method names hoặc Map keys nhạy cảm.
- [ ] Messages được chọn bằng code từ server-owned `MessageSource` và hỗ trợ locale.
- [ ] Response-level `detail`, `title`, `type` và `instance` không có input nhạy cảm.
- [ ] Input violations trả HTTP 400 phù hợp; server/return violations giữ 500 với thông tin tối thiểu.
- [ ] Có xử lý cho JSON parse failure, form binding type mismatch, query conversion/missing parameter và object/method validation.
- [ ] Negative tests gửi marker secrets qua body/form/query và assert **không xuất hiện ở bất kỳ field response nào**.
- [ ] Positive tests giữ code, path, location, message đủ để client sửa lỗi.
- [ ] Không log raw request body, authorization headers, exception messages hoặc rejected values trên các endpoints nhạy cảm.
- [ ] Production error settings đã kiểm tra và không được xem là bảo vệ duy nhất.
- [ ] Có chính sách max issues, pagination/truncation (nếu phù hợp), path escaping và rate/size limits.
- [ ] API contract của error responses có regression tests trước khi upgrade Spring/Boot/validator.

## 14. Tài liệu tham khảo

- Spring Framework 6.2 — Spring MVC Error Responses và `ProblemDetail` (RFC 9457): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — MVC Validation, `MethodArgumentNotValidException` và `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — `FieldError` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 — `ObjectError` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html
- Spring Framework 6.2 — `ParameterValidationResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Framework 6.2 — `ResponseEntityExceptionHandler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Boot 3.5 — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- OWASP Developer Guide — Handle all Errors and Exceptions: https://devguide.owasp.org/en/04-design/02-web-app-checklist/10-handle-errors-exceptions/
- MITRE CWE-209 — Generation of Error Message Containing Sensitive Information: https://cwe.mitre.org/data/definitions/209.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
