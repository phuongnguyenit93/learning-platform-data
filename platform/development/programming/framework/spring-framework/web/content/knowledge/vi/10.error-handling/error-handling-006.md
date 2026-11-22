# Biểu diễn lỗi từng trường, thông tin mở rộng và mã lỗi ổn định trong Spring MVC

## 1. Bài toán và kết quả mong đợi

Một REST endpoint nhận request không hợp lệ cần trả lại nhiều hơn trạng thái HTTP 400. Frontend phải biết **trường nào lỗi**, **vì sao lỗi** và hiển thị thông điệp dễ hiểu; client tự động cần **mã lỗi ổn định** để phân nhánh mà không phụ thuộc vào ngôn ngữ hiển thị, tên exception hay cấu trúc nội bộ của Java.

Ví dụ request:

~~~http
POST /api/registrations HTTP/1.1
Content-Type: application/json
Accept: application/problem+json

{"name":"","email":"not-an-email","seats":0}
~~~

Một hợp đồng phản hồi hữu ích:

~~~json
{
  "type": "about:blank",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/api/registrations",
  "code": "REQUEST_VALIDATION_FAILED",
  "violations": [
    {"field":"email","code":"INVALID_FORMAT","message":"Invalid field format"},
    {"field":"name","code":"REQUIRED","message":"This field is required"},
    {"field":"seats","code":"OUT_OF_RANGE","message":"Value is outside the allowed range"}
  ]
}
~~~

Đây là **hợp đồng JSON do ứng dụng định nghĩa** dựa trên RFC 9457. Spring không tự thêm mã `REQUEST_VALIDATION_FAILED` hay mảng `violations`; người viết API phải xây dựng, duy trì và kiểm thử chúng. `instance` có thể được Spring điền theo request path khi còn thiếu; giá trị và cách serialize phụ thuộc cấu hình ứng dụng.

Bài học tập trung vào Spring MVC Servlet stack, Java 17+, Spring Boot 3.x / Spring Framework 6.x, bao gồm:
- Cấu trúc HTTP status, RFC 9457 `ProblemDetail` và phần mở rộng.
- Chuyển `FieldError`, `ObjectError` và validation results thành lỗi từng trường.
- Mã máy đọc được ổn định, nội dung hiển thị có thể dịch.
- Phân biệt lỗi đọc JSON, validation DTO, method validation, lỗi nghiệp vụ và lỗi server.
- Tạo `@RestControllerAdvice` đúng cơ chế, tránh exception handler xung đột.
- Kiểm thử contract bằng MockMvc; tránh tiết lộ dữ liệu hoặc exception nội bộ.

## 2. Tách HTTP status, loại lỗi, vị trí lỗi và thông điệp

| Trường | Dành cho | Cam kết |
| --- | --- | --- |
| HTTP `status` | Giao thức HTTP, middleware/client | 400 input lỗi; 404 tài nguyên thiếu; 409 xung đột; 500 lỗi server tùy chính sách |
| `type` của Problem Details | Nhận diện loại problem theo URI | Có thể dùng URI tài liệu ổn định, hoặc `about:blank` |
| Extension `code` | Logic máy, telemetry, hỗ trợ vận hành | Mã public như `REQUEST_VALIDATION_FAILED`, không đổi tùy locale |
| `violations[].field` | UI ánh xạ tới input field | Dùng public DTO field/path, không dùng Java method name |
| `violations[].code` | UI và client tự động hiểu loại lỗi | `REQUIRED`, `INVALID_FORMAT`, `OUT_OF_RANGE`... |
| `title` / `detail` / `message` | Người đọc | Có thể dịch, thay câu chữ; client không parse làm điều kiện logic |
| `requestId` | Correlation/tracing khi được triển khai | Lấy từ infrastructure đáng tin, không phản chiếu token |

Ví dụ, lỗi email trống và email sai format đều thường dẫn đến 400 nhưng hành động hiển thị khác. Client có thể dựa vào `field=email` và `code=REQUIRED` hoặc `INVALID_FORMAT`. Client không nên tìm substring tiếng Anh `"is required"` vì thông điệp có thể được dịch sang tiếng Việt.

Mã top-level `REQUEST_VALIDATION_FAILED` cho biết **nhóm vấn đề của request**; mã `REQUIRED` nằm trong violation chỉ rõ cách sửa. Một API có thể công bố ít mã top-level nhưng nhiều mã field-level nếu nó cần UX chi tiết.

## 3. RFC 9457 và `ProblemDetail`

### 3.1. Năm trường chuẩn

RFC 9457 Problem Details for HTTP APIs có năm thành phần thông dụng:

| Trường | Ý nghĩa |
| --- | --- |
| `type` | URI reference nhận diện loại vấn đề. `about:blank` diễn giải theo status mặc định |
| `title` | Tên ngắn của loại lỗi, thích hợp cho UI/log |
| `status` | Mã HTTP status khi tạo problem; phải tương thích status thực tế |
| `detail` | Thông tin mô tả riêng cho lần lỗi này, không chứa bí mật |
| `instance` | URI reference của lần xảy ra lỗi/request liên quan |

RFC 9457 cho phép trường bổ sung (*extension members*) như `code`, `violations`, `requestId`, `retryable` hay `documentation`. Không thêm phần mở rộng chỉ vì có thông tin trong exception; cân nhắc lợi ích cho client và quyền riêng tư.

Nếu dùng `type` là URI tài liệu, backend phải sở hữu và duy trì URI đó. Với một API nhỏ, `about:blank` cùng mã `code` ổn định cũng có thể là quy ước hợp lý. Chọn một cơ chế để client định danh lỗi và ghi rõ trong OpenAPI.

### 3.2. Cách Spring MVC xử lý

Spring Framework 6 cung cấp:
- `org.springframework.http.ProblemDetail`: biểu diễn body theo RFC 9457.
- `org.springframework.web.ErrorResponse`: contract về status, headers và problem body của một lỗi HTTP.
- `org.springframework.web.ErrorResponseException`: exception cơ bản mang thông tin ErrorResponse.
- `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler`: lớp nền cho advice xử lý nhiều exception có sẵn của Spring MVC.

Khi trả `ProblemDetail`, Spring MVC có thể ghi body với media type `application/problem+json`. Trong cấu hình Jackson thông thường của Spring, các phần tử trong `ProblemDetail.properties` được **unwrap thành trường JSON ở top-level**.

Ví dụ minh họa (chưa đầy đủ imports và biến `violations`):

~~~java
ProblemDetail body = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
body.setTitle("Request validation failed");
body.setDetail("One or more fields are invalid.");
body.setProperty("code", "REQUEST_VALIDATION_FAILED");
body.setProperty("violations", violations);
~~~

Kết quả sẽ có `code` và `violations` ngang hàng `title` và `status`, thay vì mặc nhiên nằm bên trong `"properties":{...}`. Tránh đặt extension tên `type`, `status`, `title`, `detail` hoặc `instance` gây nhập nhằng với trường chuẩn.

Spring Boot có cấu hình `spring.mvc.problemdetails.enabled` để auto-configure xử lý một số lỗi built-in thành problem details. Khi tự triển khai subclass `ResponseEntityExceptionHandler`, bạn sở hữu response của các nhánh override và cần xác nhận thứ tự advice với configuration Boot hiện hữu.

## 4. Thiết kế mảng lỗi từng trường (`violations`)

Một phần tử nên có tối thiểu:

~~~json
{"field":"profile.email","code":"INVALID_FORMAT","message":"Invalid field format"}
~~~

Trong đó:
- `field` là tên hoặc đường dẫn public của dữ liệu request; nếu có object lồng, có thể là `profile.email`; với mảng có thể là `items[0].quantity`.
- `code` là mã máy đọc được trong tập mã do API công bố.
- `message` là thông điệp an toàn dành cho người dùng, có thể bản địa hóa.

Nếu lỗi không thuộc trường nào, ví dụ constraint liên quan hai field, có thể quy ước `field:"$"` để nói lỗi ở mức object. Không bắt client đoán lúc nào `field` null, lúc nào chuỗi rỗng, lúc nào không có thuộc tính.

**Cho phép nhiều lỗi trên một field.** Một giá trị có thể vi phạm nhiều constraint. Backend có thể trả nhiều violation hoặc chọn lỗi ưu tiên, nhưng phải quyết định quy tắc và test. Đặc biệt, thứ tự errors từ Bean Validation provider không nên tự được coi là thứ tự UI; nếu API công bố thứ tự, hãy tự sort theo một quy tắc định nghĩa.

### 4.1. Mã field-level công khai

| Constraint/binding nội bộ | Mã public ví dụ | Ý nghĩa |
| --- | --- | --- |
| `NotBlank`, `NotNull`, `NotEmpty` | `REQUIRED` | Không được vắng/rỗng theo quy tắc áp dụng |
| `Email`, `Pattern` | `INVALID_FORMAT` | Không đáp ứng định dạng |
| `Min`, `Max`, `Positive` | `OUT_OF_RANGE` | Không đáp ứng khoảng giá trị |
| `Size` | `INVALID_LENGTH` | Độ dài/số phần tử không phù hợp |
| Constraint khác | `INVALID_VALUE` | Một quy tắc không được đáp ứng |
| Query/parameter method invalid | `INVALID_PARAMETER` | Input không thỏa điều kiện method |

`FieldError.getCode()` trả mã do Spring/validation tạo như `NotBlank`, `Email`, `Min`. Các mã trong `getCodes()` còn có thể gắn tên object và field Java. Đó là dữ liệu **nội bộ** phục vụ binding và MessageSource, không nhất thiết phù hợp làm hợp đồng API.

Dùng tầng mapping để giữ `INVALID_FORMAT` ổn định dù validator chuyển từ `@Email` sang custom constraint. Ngược lại, nếu đổi public code hay ý nghĩa của nó, hãy coi đó là thay đổi API cần versioning/review.

### 4.2. Không xuất giá trị bị từ chối (`rejectedValue`)

`FieldError` có thể chứa `getRejectedValue()`, nhưng đây có thể là password, token, email, số giấy tờ hoặc object rất dài. **Không đưa rejectedValue, stack trace, SQL exception, tên package, raw parser message ra public response.** Frontend đã có giá trị người dùng nhập; server chỉ cần báo field và lỗi.

Với lỗi JSON parser, có trường hợp server chưa tạo ra DTO nên không có field name chính xác. Đừng bịa một violation cụ thể nếu không đủ bằng chứng.

## 5. Những nhánh lỗi thực sự gặp trong Spring MVC

Một pipeline đơn giản:

~~~text
HTTP request
  |
  +-- Không đọc được body / JSON sai
  |     -> HttpMessageNotReadableException
  |
  +-- Thiếu query param hoặc đổi kiểu thất bại
  |     -> MissingServletRequestParameterException
  |     -> MethodArgumentTypeMismatchException / TypeMismatchException
  |
  +-- Có @Valid @RequestBody DTO, không có direct method constraint
  |     -> MethodArgumentNotValidException (individual argument validation)
  |
  +-- Có constraint trực tiếp trên method parameter, Spring MVC 6.1+
  |     -> HandlerMethodValidationException (input: 400)
  |
  +-- Method return value vi phạm constraint
        -> HandlerMethodValidationException (server: 500)
~~~

Sơ đồ chỉ các **nhánh có thể xảy ra**, không phải toàn bộ exception của MVC. Với controller có `@Validated` ở cấp class và cấu hình AOP method validation, đường đi có thể qua proxy và ném `ConstraintViolationException` hoặc `MethodValidationException`. Spring MVC 6.1+ khuyến nghị bỏ class-level `@Validated` nếu bạn muốn dùng built-in MVC method validation.

| Lỗi | Dữ liệu có thể dùng để tạo contract |
| --- | --- |
| `MethodArgumentNotValidException` | `getBindingResult().getFieldErrors()`, `getGlobalErrors()` |
| `HandlerMethodValidationException` | `getAllValidationResults()`, `visitResults(Visitor)`; có thể có `ParameterErrors` cho nested DTO |
| `HttpMessageNotReadableException` | Phân loại body không đọc được; thường không có field-level details đáng tin |
| `MissingServletRequestParameterException` | Tên tham số cần thiết bị thiếu |
| `MethodArgumentTypeMismatchException` | Tham số HTTP và kiểu Java expected; không phơi raw input nhạy cảm |
| Domain exception như not found/conflict | Public domain error code và status theo chính sách |
| Exception nội bộ không dự kiến | `INTERNAL_ERROR`, status 500, log nguyên nhân an toàn phía server |

**Đừng map tất cả lỗi thành HTTP 400.** Vi phạm ràng buộc trên **kết quả trả về của server** nên là 500. Xung đột nghiệp vụ có thể là 409. Request hợp lệ nhưng một tài nguyên không tồn tại thường là 404.

## 6. Ví dụ ứng dụng chạy được: Spring Boot 3.3 / Java 17

Ví dụ minh họa cách triển khai một API nhận đăng ký đơn giản, tự tạo error body không phụ thuộc database. Dùng Spring Boot 3.3.5 (nền Spring Framework 6.1.x khi dùng BOM mặc định), Java 17+, Spring MVC và Hibernate Validator.

Cấu trúc:

~~~text
registration-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/registration/
    │   ├── RegistrationApplication.java
    │   ├── api/RegistrationInput.java
    │   └── web/
    │       ├── RegistrationController.java
    │       └── ApiErrorAdvice.java
    └── test/java/com/example/registration/web/
        └── RegistrationControllerTest.java
~~~

### 6.1. Build

`settings.gradle`:

~~~groovy
rootProject.name = 'registration-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` cung cấp Spring MVC/Jackson. `spring-boot-starter-validation` là phần cần thiết để Bean Validation constraints hoạt động (thường qua Hibernate Validator). `spring-boot-starter-test` hỗ trợ JUnit và MockMvc. Ví dụ giả định project có Gradle wrapper tương thích; code Spring không thể chạy đơn lẻ chỉ bằng `javac` nếu không khai báo classpath Spring.

### 6.2. Main application

`src/main/java/com/example/registration/RegistrationApplication.java`:

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

Lớp đặt tại package root để component scan phát hiện `web` và `api`.

### 6.3. Input DTO có constraints

`src/main/java/com/example/registration/api/RegistrationInput.java`:

~~~java
package com.example.registration.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RegistrationInput(
        @NotBlank @Size(max = 80) String name,
        @NotBlank @Email String email,
        @Min(1) int seats) {
}
~~~

`@NotBlank` kiểm tra chuỗi không chỉ có whitespace; `@Email` kiểm định định dạng cơ bản nhưng không xác minh quyền sở hữu email; `@Min(1)` yêu cầu seats ít nhất 1. Với kiểu primitive `int`, body vắng thuộc tính seats có thể được deserialize thành giá trị mặc định theo cấu hình, rồi vi phạm `@Min`. Nếu cần phân biệt không gửi và gửi 0, dùng `Integer` kết hợp `@NotNull`.

### 6.4. Controller có hai con đường validation

`src/main/java/com/example/registration/web/RegistrationController.java`:

~~~java
package com.example.registration.web;

import com.example.registration.api.RegistrationInput;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/registrations")
public class RegistrationController {

    public record Receipt(String name, int seats) {}

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Receipt submit(@Valid @RequestBody RegistrationInput input) {
        return new Receipt(input.name(), input.seats());
    }

    @GetMapping("/check")
    public Map<String, Integer> check(
            @RequestParam("minimumSeats") @Min(1) int minimumSeats) {
        return Map.of("minimumSeats", minimumSeats);
    }
}
~~~

`submit` có individual argument validation cho `@Valid @RequestBody`; khi dữ liệu vi phạm có thể ném `MethodArgumentNotValidException`. `check` có direct `@Min(1)` trên tham số phương thức nên với Spring MVC **6.1+** built-in method validation có thể ném `HandlerMethodValidationException`.

Không gắn `@Validated` ở **cấp class** trong demo: class-level `@Validated` có thể chuyển sang AOP method validation và loại exception khác. Ví dụ này không lưu dữ liệu; success status mặc định 200 và response receipt chỉ minh họa đường HTTP thành công. Trong API tạo tài nguyên thực, chọn 201/Location và persistence theo business contract.

### 6.5. Advice map hai exception thành cùng error contract

`src/main/java/com/example/registration/web/ApiErrorAdvice.java`:

~~~java
package com.example.registration.web;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    public record Violation(String field, String code, String message) {}

    private static Violation fieldViolation(FieldError error) {
        String stableCode = switch (
                error.getCode() == null ? "" : error.getCode()) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED";
            case "Email", "Pattern" -> "INVALID_FORMAT";
            case "Min", "Max", "Positive", "PositiveOrZero" -> "OUT_OF_RANGE";
            case "Size" -> "INVALID_LENGTH";
            default -> "INVALID_VALUE";
        };

        String safeMessage = switch (stableCode) {
            case "REQUIRED" -> "This field is required";
            case "INVALID_FORMAT" -> "Invalid field format";
            case "OUT_OF_RANGE" -> "Value is outside the allowed range";
            case "INVALID_LENGTH" -> "Invalid field length";
            default -> "Invalid field value";
        };

        return new Violation(error.getField(), stableCode, safeMessage);
    }

    private static List<Violation> sorted(List<Violation> errors) {
        return errors.stream()
                .sorted(Comparator.comparing(Violation::field)
                        .thenComparing(Violation::code))
                .toList();
    }

    private ResponseEntity<Object> problem(
            HttpStatusCode status, HttpHeaders headers, String code,
            String title, String detail, List<Violation> violations) {

        ProblemDetail body = ProblemDetail.forStatus(status);
        body.setTitle(title);
        body.setDetail(detail);
        body.setProperty("code", code);

        if (violations != null) {
            body.setProperty("violations", sorted(violations));
        }
        return new ResponseEntity<>(body, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<Violation> violations = new ArrayList<>();
        ex.getBindingResult().getFieldErrors()
                .forEach(e -> violations.add(fieldViolation(e)));
        ex.getBindingResult().getGlobalErrors()
                .forEach(e -> violations.add(new Violation(
                        "$", "INVALID_OBJECT", "Object-level constraint failed")));

        return problem(status, headers, "REQUEST_VALIDATION_FAILED",
                "Request validation failed",
                "One or more fields are invalid.", violations);
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (ex.isForReturnValue()) {
            return problem(HttpStatus.INTERNAL_SERVER_ERROR, headers,
                    "INTERNAL_ERROR", "Internal server error",
                    "The server could not complete the request.", null);
        }

        List<Violation> violations = new ArrayList<>();

        for (ParameterValidationResult result
                : ex.getAllValidationResults()) {

            if (result instanceof ParameterErrors errors) {
                errors.getFieldErrors().forEach(e ->
                        violations.add(fieldViolation(e)));
                errors.getGlobalErrors().forEach(e ->
                        violations.add(new Violation(
                                "$", "INVALID_OBJECT",
                                "Object-level constraint failed")));
            } else {
                MethodParameter parameter = result.getMethodParameter();
                RequestParam query =
                        parameter.getParameterAnnotation(RequestParam.class);

                String field = query == null || query.name().isBlank()
                        ? "argument" + parameter.getParameterIndex()
                        : query.name();

                String code =
                        parameter.hasParameterAnnotation(Min.class)
                        || parameter.hasParameterAnnotation(Max.class)
                        ? "OUT_OF_RANGE" :
                        parameter.hasParameterAnnotation(NotBlank.class)
                        ? "REQUIRED" : "INVALID_PARAMETER";

                for (var ignored : result.getResolvableErrors()) {
                    violations.add(new Violation(
                            field, code,
                            "Parameter does not satisfy constraints"));
                }
            }
        }

        return problem(status, headers, "REQUEST_VALIDATION_FAILED",
                "Request validation failed",
                "One or more parameters are invalid.", violations);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return problem(status, headers, "MALFORMED_REQUEST_BODY",
                "Request body cannot be read",
                "Request body is missing or malformed.", null);
    }
}
~~~

Điểm quan trọng:
1. Kế thừa `ResponseEntityExceptionHandler` rồi **override method tương ứng**; không đặt thêm `@ExceptionHandler(MethodArgumentNotValidException.class)` trùng với superclass.
2. `fieldViolation()` chuyển mã Bean Validation nội bộ thành mã public. Message được kiểm soát, không trả `getRejectedValue()`.
3. `handleMethodArgumentNotValid()` lấy field errors và object-level errors từ `BindingResult`.
4. `handleHandlerMethodValidationException()` phân biệt **input constraints** và **return-value violation**; riêng lỗi return trả 500 với body an toàn.
5. Với `ParameterErrors` (ví dụ DTO cascade bên trong method validation), advice lấy field paths. Với direct query constraints, nó dùng `@RequestParam` để lấy tên public.
6. Ví dụ chỉ map tốt một tập annotation và tham số: `@RequestParam`, `@Min`, `@Max`, `@NotBlank`, DTO field errors. Với `@PathVariable`, `@RequestHeader`, cross-parameter/nested container constraint, nên triển khai mapper đầy đủ qua `HandlerMethodValidationException.Visitor` hoặc một abstraction domain; fallback `argumentN` không nên dùng như field name public lâu dài.
7. `handleHttpMessageNotReadable()` không giả tạo violation trên một field khi JSON chưa thể parse.
8. `problem()` giữ HTTP status và JSON `status` nhất quán; extension `violations` chỉ có trong những nhánh biết violation.

**Giới hạn phiên bản:** code này sử dụng class/API của Spring MVC 6.1+. Nếu dự án chạy Spring 6.0, nhánh `HandlerMethodValidationException` chưa có cùng cách hoạt động. Nếu controller có class-level `@Validated`, AOP có thể ném `ConstraintViolationException` hoặc `MethodValidationException` và cần mapper khác. Chỉ đổi cơ chế khi có kiểm thử regression.

## 7. Ví dụ request/response và kết quả dự kiến

Trong project đã có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell/CMD dùng `.\gradlew.bat bootRun`. Với Spring dependencies, `javac` thuần không đủ classpath; Gradle plugin xử lý compile/run.

### 7.1. DTO vi phạm ba constraints

~~~bash
curl -i -X POST 'http://localhost:8080/api/registrations' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/problem+json' \
  -d '{"name":"","email":"not-an-email","seats":0}'
~~~

Đường `MethodArgumentNotValidException` được advice chuyển thành HTTP 400. Các field chủ yếu trong JSON:

~~~json
{
  "type": "about:blank",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "code": "REQUEST_VALIDATION_FAILED",
  "violations": [
    {"field":"email","code":"INVALID_FORMAT","message":"Invalid field format"},
    {"field":"name","code":"REQUIRED","message":"This field is required"},
    {"field":"seats","code":"OUT_OF_RANGE","message":"Value is outside the allowed range"}
  ]
}
~~~

`instance` có thể được thêm tự động theo đường dẫn request. Bảng lỗi được sort theo `field` nên email trước name rồi seats; đó là **quy tắc do ứng dụng viết**, không phụ thuộc Hibernate Validator duyệt constraints theo thứ tự nào.

### 7.2. Đầu vào hợp lệ

~~~bash
curl -i -X POST 'http://localhost:8080/api/registrations' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","seats":2}'
~~~

Response demo mặc định HTTP 200:

~~~json
{"name":"Lan","seats":2}
~~~

Demo không lưu database, không tuyên bố đăng ký đã được persist. API tạo tài nguyên thực nên quyết định status 201/Location, transactional behavior và exception xung đột riêng.

### 7.3. Direct method validation

~~~bash
curl -i 'http://localhost:8080/api/registrations/check?minimumSeats=0'
~~~

Với Spring MVC 6.1+, `@Min(1)` trên method parameter thường cho HTTP 400 và các extension:

~~~json
{
  "code":"REQUEST_VALIDATION_FAILED",
  "violations":[
    {
      "field":"minimumSeats",
      "code":"OUT_OF_RANGE",
      "message":"Parameter does not satisfy constraints"
    }
  ]
}
~~~

Đây là **phần extension được trích** từ body, response đầy đủ còn có các trường RFC 9457. `minimumSeats` được lấy từ tên khai báo rõ ràng trong `@RequestParam`.

### 7.4. JSON sai cú pháp

~~~bash
curl -i -X POST 'http://localhost:8080/api/registrations' \
  -H 'Content-Type: application/json' \
  -d '{"name":'
~~~

Parser không tạo được DTO; advice trả HTTP 400 với `code=MALFORMED_REQUEST_BODY`, không có `violations`. Không mô tả đây là lỗi field `name` nếu parser chưa xác định chắc được.

### 7.5. Tham số query không chuyển kiểu được

`GET /api/registrations/check?minimumSeats=abc` thường bị Spring MVC từ chối trước method validation bằng lỗi conversion, cũng là HTTP 400 nhưng **advice demo chưa map sang custom `code`**. Nếu hệ thống yêu cầu **mọi** 400 đều có stable code, cần override `handleTypeMismatch(...)` và `handleMissingServletRequestParameter(...)`, đặt `QUERY_PARAMETER_INVALID` / `REQUIRED_PARAMETER_MISSING` và test. Không khẳng định các override ở mục 6 đã chuẩn hóa mọi exception Spring.

## 8. MockMvc kiểm thử contract

`src/test/java/com/example/registration/web/RegistrationControllerTest.java`:

~~~java
package com.example.registration.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidDtoReturnsStableFieldErrors() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.valueOf("application/problem+json"))
                        .content("{\"name\":\"\",\"email\":\"not-an-email\","
                                + "\"seats\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.valueOf("application/problem+json")))
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.code").value("REQUEST_VALIDATION_FAILED"))
                .andExpect(jsonPath("$.violations.length()").value(3))
                .andExpect(jsonPath("$.violations[0].field").value("email"))
                .andExpect(jsonPath("$.violations[0].code").value("INVALID_FORMAT"))
                .andExpect(jsonPath("$.violations[1].field").value("name"))
                .andExpect(jsonPath("$.violations[1].code").value("REQUIRED"))
                .andExpect(jsonPath("$.violations[2].field").value("seats"))
                .andExpect(jsonPath("$.violations[2].code").value("OUT_OF_RANGE"));
    }

    @Test
    void directMethodConstraintIsRepresented() throws Exception {
        mvc.perform(get("/api/registrations/check")
                        .param("minimumSeats", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("REQUEST_VALIDATION_FAILED"))
                .andExpect(jsonPath("$.violations[0].field").value("minimumSeats"))
                .andExpect(jsonPath("$.violations[0].code").value("OUT_OF_RANGE"));
    }

    @Test
    void invalidJsonHasNoFakeFieldErrors() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MALFORMED_REQUEST_BODY"))
                .andExpect(jsonPath("$.violations").doesNotExist());
    }

    @Test
    void validDtoReturnsSuccessResponse() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\",\"email\":\"lan@example.com\","
                                + "\"seats\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.seats").value(2));
    }

    @Test
    void invalidQueryConversionIsStillBadRequest() throws Exception {
        mvc.perform(get("/api/registrations/check")
                        .param("minimumSeats", "abc"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Test này chú trọng **HTTP status, mã public, field path và structure**, không assert thông điệp tiếng Anh vì message có thể được thay bằng bản dịch mà contract vẫn hợp lệ. `violations[0]` được assert vì code advice đã sort. Nếu không muốn hứa thứ tự lỗi, hãy kiểm tra theo tập; **không dựa vào thứ tự từ Bean Validation provider**.

Với dự án có Spring Security, custom MVC config, Jackson modules hay advice khác, MockMvc cần setup tương ứng. Ví dụ không tự động chứng minh mọi project Spring Boot có cùng error JSON; xác nhận cả integration test của hệ thống thực.

## 9. Lỗi mức object, nested field và constraints phức tạp

Một request DTO phức tạp có thể chứa:

~~~json
{
  "contact": {"email":"invalid"},
  "items": [
    {"sku":"A","quantity":0},
    {"sku":"B","quantity":2}
  ]
}
~~~

Để validate nested objects, cần `@Valid` trên các thuộc tính cần cascade và constraint thực tế trong record/class lồng nhau. Field errors từ Spring binding có thể có path `contact.email` hoặc `items[0].quantity`. Đây là **nội dung minh họa**, không phải payload được xử lý bởi demo registration phẳng.

Cần quyết định field path là:
- **Dotted/bracket notation**: `items[0].quantity`, gần cách Spring biểu diễn.
- **JSON Pointer** theo RFC 6901: `/items/0/quantity`, thuận tiện ánh xạ cấu trúc JSON; phải escape các ký tự đặc biệt `~` và `/`.

Đừng trộn hai kiểu path giữa các endpoint. Nếu public DTO field bị đổi từ `contact.email` thành `emailAddress`, error contract cũng có thể phá frontend dù HTTP 400 vẫn không đổi. Có thể dùng lớp mapping từ internal binding paths sang public schema paths.

Các constraint liên quan nhiều field có thể tạo `ObjectError`; ví dụ `startDate` phải trước `endDate`. Response có thể dùng `field="$"` kèm `code=INVALID_OBJECT` hoặc dùng extension `fields:["startDate","endDate"]`, nếu muốn tô đỏ cả hai. Demo chọn dấu `"$"` cho lỗi object; đây là quy ước phải ghi rõ.

## 10. Quốc tế hóa: code bất biến, message linh hoạt

Một frontend tiếng Việt có thể nhận:

~~~json
{
  "code":"REQUEST_VALIDATION_FAILED",
  "violations":[
    {"field":"email","code":"INVALID_FORMAT","message":"Địa chỉ email không hợp lệ"}
  ]
}
~~~

Với locale tiếng Anh, message có thể trở thành `"Invalid email address"` nhưng `INVALID_FORMAT` và `REQUEST_VALIDATION_FAILED` vẫn giữ nguyên. Có hai lựa chọn:
1. Backend dùng `MessageSource` và locale request để resolve message theo mã, trả chuỗi đã dịch.
2. Backend trả code kèm tham số công khai cần thiết; frontend tự dịch theo catalog UI.

`FieldError` là `MessageSourceResolvable` có `getCodes()`, `getArguments()` và default message. MessageSource của Spring hỗ trợ các key như `NotBlank.registrationInput.name` khi object/field names tương ứng, nhưng **tên key thực tế phụ thuộc binding name**. Để tách API khỏi Java DTO refactor, có thể dùng một catalog riêng với key `api.required`, `api.invalidFormat`, `api.outOfRange`.

Một message cần tham số:

~~~json
{
  "field":"name",
  "code":"INVALID_LENGTH",
  "message":"Name must not exceed 80 characters",
  "maxLength":80
}
~~~

`maxLength` là extension có thể hữu ích cho frontend; chỉ xuất tham số công khai. **Advice demo mục 6 chưa xuất `maxLength`**, vì record `Violation` chỉ có field/code/message. Nếu bổ sung field mới, update DTO serializer, OpenAPI và test. Không xuất raw regex, SQL constraint hay policy bảo mật nội bộ.

### Không dùng thông báo làm mã lỗi

Đoạn frontend không nên viết:

~~~javascript
if (error.message.includes("must not be blank")) {
  showRequiredHint();
}
~~~

Khi đổi ngôn ngữ hoặc Bean Validation provider, logic sẽ hỏng. Cách đúng:

~~~javascript
const violations = problem.violations ?? [];
for (const violation of violations) {
  if (violation.code === "REQUIRED") {
    showFieldError(violation.field, violation.message);
  }
}
~~~

Đây là fragment JavaScript dành cho client; ``showFieldError` phải là hàm do giao diện định nghĩa. `problem` là JSON response đã parse thành object.

## 11. Thông tin mở rộng: cái gì hữu ích, cái gì nên tránh

| Extension | Khi có ích | Điều kiện |
| --- | --- | --- |
| `code` | Hầu hết lỗi cần client xử lý | Mã ổn định, có tài liệu |
| `violations` | Validation theo field | Path/code/message, cho phép nhiều lỗi trên một field |
| `requestId` / `traceId` | Support, correlation | ID tạo/xác minh bởi tracing infrastructure |
| `retryable` | API có chính sách retry | Không đánh dấu 400 validation retryable |
| `retryAfterSeconds` | 429/503 có chiến lược retry | Phải nhất quán với header `Retry-After` nếu có |
| `documentation` | Có tài liệu giải thích lỗi | URI ổn định, đúng phiên bản |
| `min`, `max`, `allowedValues` | Điều kiện sửa input công khai | Không lộ quy tắc nội bộ nhạy cảm |
| `resource` hoặc `operation` | Ngữ cảnh nghiệp vụ cần thiết | Không để lộ tenant/identifier không có quyền |

Với 500, body nên an toàn:

~~~json
{
  "type":"about:blank",
  "title":"Internal server error",
  "status":500,
  "detail":"The server could not complete the request.",
  "code":"INTERNAL_ERROR"
}
~~~

Server log exception class, stack trace và diagnostics cần thiết qua kênh có kiểm soát. Nếu có `requestId`, người dùng/support có thể tra sự cố mà không cần public exception details. Không tin một `X-Request-Id` tùy ý do client gửi nếu dùng nó làm bằng chứng an ninh hoặc khóa truy cập log.

**Không xuất:** `getRejectedValue()`, password, OTP, token, session IDs, connection strings, SQL query đầy đủ, raw exception message, stack trace, tên tệp server, đường dẫn hệ thống hoặc nội dung upload. Việc ghi raw input vào log cũng có rủi ro tương tự response.

### Lỗi xung đột thông tin cá nhân

API đăng ký có thể cân nhắc mã `EMAIL_ALREADY_REGISTERED` với HTTP 409. Nhưng trên hệ thống mà việc xác nhận email có tồn tại là dữ liệu nhạy cảm, phản hồi cụ thể có thể tạo rủi ro enumeration. Chọn policy phù hợp: có những luồng nên trả thông điệp trung tính. Đây là quyết định nghiệp vụ/bảo mật, không phải mặc định Spring Validation.

## 12. Error registry và tính tương thích của mã

Một bảng registry có thể xác định:

| Top-level `code` | HTTP | Mô tả | Có `violations`? |
| --- | --- | --- | --- |
| `REQUEST_VALIDATION_FAILED` | 400 | Input đã bind nhưng constraint vi phạm | Có |
| `MALFORMED_REQUEST_BODY` | 400 | Body thiếu/sai cú pháp/không parse được | Không bắt buộc |
| `REQUIRED_PARAMETER_MISSING` | 400 | Query/header/part bắt buộc thiếu | Tùy contract |
| `QUERY_PARAMETER_INVALID` | 400 | Query không thể chuyển kiểu hoặc không hợp lệ | Tùy contract |
| `REGISTRATION_NOT_FOUND` | 404 | Tài nguyên không tồn tại | Không |
| `EMAIL_ALREADY_REGISTERED` | 409 nếu policy cho phép | Xung đột nghiệp vụ | Tùy contract |
| `INTERNAL_ERROR` | 500 | Lỗi server không công khai nguyên nhân | Không |

Bảng này là **thiết kế đầy đủ hơn** so với demo. Code ở mục 6 hiện thực các nhánh `REQUEST_VALIDATION_FAILED`, `MALFORMED_REQUEST_BODY` và `INTERNAL_ERROR` cho return-value violation. Các mã còn lại cần handlers/domain logic khác nếu muốn dùng. Không hứa client nhận mọi mã ở registry khi server chưa triển khai.

Quy tắc quản lý:
- Một mã không đổi ý nghĩa giữa các version chỉ vì đổi Java exception.
- Client phải có fallback `UNKNOWN_ERROR` khi backend thêm mã mới.
- Thay public code, HTTP status của cùng lỗi, schema `violations` hoặc field path có thể là **breaking change**.
- Thay câu chữ message/locale không nhất thiết là breaking change nếu client dùng code cho hành vi.
- Bổ sung extension mới thường an toàn hơn nếu client cho phép unknown fields, nhưng vẫn phải document và test.
- Cần ghi nguyên tắc deprecate/remove codes và giữ compatibility khi nhiều client chưa cập nhật cùng lúc.

Đưa taxonomy vào OpenAPI schema và test JSON contract. Không để raw `Exception.getClass().getSimpleName()` trở thành mã public; tên class thường bị đổi qua nâng cấp thư viện/refactor.

## 13. Khi lỗi thuộc domain thay vì validation

Validation chỉ kiểm tra cấu trúc và điều kiện đầu vào. Một request hoàn toàn hợp lệ vẫn có thể không được xử lý:

~~~text
GET  /api/registrations/999 -> 404 REGISTRATION_NOT_FOUND
POST /api/registrations     -> 409 EMAIL_ALREADY_REGISTERED
POST /api/registrations     -> 400 REQUEST_VALIDATION_FAILED
~~~

Đó là **ví dụ hợp đồng nghiệp vụ**, không phải những endpoint khác đã tồn tại trong demo. Nếu thực thi, tạo exception/domain result chuyên biệt. Không bắt toàn bộ `IllegalArgumentException` rồi trả HTTP 400: có `IllegalArgumentException` là bug trong code server chứ không liên quan client.

Đoạn Java minh họa một handler riêng, cần import và định nghĩa `RegistrationNotFoundException` trong project thực tế:

~~~java
@ExceptionHandler(RegistrationNotFoundException.class)
public ResponseEntity<ProblemDetail> notFound(
        RegistrationNotFoundException ex) {

    ProblemDetail body = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
    body.setTitle("Registration not found");
    body.setDetail("The requested registration does not exist.");
    body.setProperty("code", "REGISTRATION_NOT_FOUND");
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
}
~~~

Nếu thêm vào subclass `ResponseEntityExceptionHandler`, handler này chỉ xử lý custom domain exception đã xác định, không trùng với built-in exception hooks. Trong sản phẩm thực, giữ detail an toàn, không lộ định danh bí mật hoặc nguyên nhân authorization mà client không được biết.

## 14. Logging, observability và hỗ trợ vận hành

Một log có cấu trúc có thể gồm:
- HTTP method, route template, status.
- Public top-level error code.
- Số lượng violations theo loại code hữu hạn.
- Trace/request ID do hạ tầng cung cấp.
- Exception class và stack trace ở hệ thống log bảo vệ, khi cần.

Tránh dùng raw input, email, user-supplied message hoặc URL nguyên bản làm metric label: cardinality cao và nguy cơ lộ thông tin. Dùng route template và error-code registry cho metrics. Client có thể đính kèm request ID khi liên hệ support; backend tra bằng ID đó trong hệ thống có phân quyền.

`ErrorResponse`/`ProblemDetail` giúp chuẩn hóa output, nhưng **không tự bảo vệ** khỏi việc bạn gắn extension nhạy cảm. Mọi property thêm vào JSON đều phải qua review tương tự field API bình thường.

## 15. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Client so sánh tiếng Anh trong `message` | Thiếu mã public | Dùng `code` ổn định; dịch message độc lập |
| Response chỉ có `"Validation failed"` | Không map `FieldError` | Tạo `violations` theo field + code |
| Trả raw `rejectedValue` | Sao chép object validation nội bộ | Loại khỏi public response/log |
| JSON sai cú pháp nhưng báo field lỗi | Chưa có DTO để validate | Dùng `MALFORMED_REQUEST_BODY` |
| Controller Spring 6.1 trả exception khác trước | Built-in method validation hoạt động | Xử lý cả `MethodArgumentNotValidException` và `HandlerMethodValidationException` |
| AOP controller có `@Validated` cấp class | Proxy method validation đổi đường exception | Kiểm tra class annotation và Spring version |
| Lỗi trên server return value trả 400 | Gộp input/server constraint | Trả 500, log nguyên nhân an toàn |
| `BindingResult` có lỗi object nhưng JSON bỏ qua | Chỉ lặp `getFieldErrors()` | Xử lý `getGlobalErrors()` với quy tắc field đặc biệt |
| Hai handlers cùng xử lý built-in exception | Override và `@ExceptionHandler` trùng | Dùng đúng hook trong `ResponseEntityExceptionHandler` |
| Lỗi nested field không tô đúng UI | Path format không thống nhất | Công bố dotted path hoặc JSON Pointer và map rõ |
| Test hỏng vì đổi ngôn ngữ | Assert message thay vì code | Test status/code/path; test localization riêng |
| Upgrading Spring Data/Validator đổi mã lỗi | Expose internal exception/constraint code | Mapping sang public registry code |
| 500 lộ SQL exception | Trả `ex.getMessage()` thẳng | Safe detail + requestId và log nội bộ |
| Các endpoint có `code` ở các vị trí khác nhau | Không có schema chung | Chọn top-level extension và kiểm tra JSON |
| Dự án chỉ xử lý một số 400 | Bỏ sót missing/type mismatch/multipart | Lập bảng exception chính, mở rộng advice và test |

## 16. Checklist triển khai

1. Chọn RFC 9457 hoặc một schema khác nhất quán; document status và Content-Type.
2. Tạo registry cho mã lỗi top-level và mã field-level.
3. Xác định `violations`: field path, code, message, object error và chính sách nhiều lỗi trên một field.
4. Tách lỗi parsing/conversion khỏi Bean Validation và business conflict.
5. Override `ResponseEntityExceptionHandler` đúng nhánh; không thêm handler trùng.
6. Với Spring MVC 6.1+, hỗ trợ `HandlerMethodValidationException` và phân biệt input 400/return 500.
7. Nếu có AOP `@Validated` cấp class, kiểm tra đường proxy và exceptions thực tế.
8. Không phản chiếu sensitive input/rejectedValue/stack traces.
9. Dùng MessageSource hoặc catalog UI để dịch text, giữ code bất biến.
10. Kiểm thử MockMvc cho valid request, nhiều field errors, method constraint, parse error, missing/type mismatch và domain errors.
11. Gắn correlation ID đáng tin vào observability khi cần.
12. Ghi schema/field path và policy versioning để frontend không phụ thuộc implementation.

### Câu hỏi tự kiểm tra

**1.** Tại sao không dùng `FieldError.getDefaultMessage()` làm key xử lý trong frontend?

**Trả lời:** Message có thể thay đổi theo locale, provider hoặc nội dung UX. Client phải dựa vào mã public ổn định.

**2.** `ProblemDetail.setProperty("code","...")` xuất JSON ra sao?

**Trả lời:** Với Jackson support của Spring, property mở rộng thường được unwrap thành top-level field `code` ngang với `status`, không lồng bắt buộc dưới `properties`.

**3.** `@Valid @RequestBody` lỗi thường dùng exception nào?

**Trả lời:** `MethodArgumentNotValidException` trong individual argument validation. Khi method có direct constraint ở Spring MVC 6.1+, `HandlerMethodValidationException` có thể bao cả DTO cascade.

**4.** JSON không parse được thì có nên tạo violation `field=name` không?

**Trả lời:** Không nếu parser không xác định được field chính xác. Phân loại `MALFORMED_REQUEST_BODY`, không bịa nguyên nhân field.

**5.** Khi method trả về một giá trị vi phạm return-value constraint, nên trả 400 hay 500?

**Trả lời:** 500 vì đây là lỗi contract phía server, không phải input mà client sửa được.

**6.** `requestId` nên lấy từ đâu?

**Trả lời:** Từ tracing infrastructure/servlet filter có chính sách phát sinh/xác minh, không coi input request ID tùy ý của client là bằng chứng tin cậy.

## 17. Tài liệu chính thức

- [Spring Framework — Error Responses (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, `ResponseEntityExceptionHandler`, extension members và MessageSource.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): individual argument validation, method validation, `BindingResult` và các MVC exceptions.
- [Spring Framework — RequestBody validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): HTTP message conversion, `@Valid` và lỗi input.
- [Spring Framework — `ProblemDetail` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html): `forStatus` và `setProperty`.
- [Spring Framework — `ResponseEntityExceptionHandler` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): các hook để override.
- [Jakarta Bean Validation Specification 3.0](https://jakarta.ee/specifications/bean-validation/3.0/): constraint, cascade và executable validation.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): cấu trúc chuẩn và extension members.

**Ghi nhớ:** HTTP status phân loại lỗi ở mức giao thức; mã `code` của API giúp máy quyết định hành vi; `violations[].field/code` chỉ ra chỗ cần sửa; còn `message`/`detail` giúp con người hiểu vấn đề. Giữ bốn lớp thông tin này tách bạch để API dễ kiểm thử, dịch, nâng cấp và bảo vệ dữ liệu.
