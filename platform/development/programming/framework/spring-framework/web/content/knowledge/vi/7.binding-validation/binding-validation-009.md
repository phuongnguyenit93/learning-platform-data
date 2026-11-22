# Kiểm tra tham số phương thức và phân biệt các ngoại lệ validation theo phiên bản Spring MVC

## 1. Vấn đề thực tế: cùng một lỗi đầu vào, vì sao nhận các exception khác nhau?

Trong Spring MVC, hãy xem ba khai báo sau:

~~~java
// (A) Kiểm tra thuộc tính của một DTO request.
public Receipt create(@Valid @RequestBody CreateOrder request) { ... }

// (B) Kiểm tra ràng buộc trực tiếp trên một tham số HTTP.
public Receipt find(@RequestParam("page") @Min(1) int page) { ... }

// (C) Kiểm tra cả tham số trực tiếp lẫn DTO trong cùng một handler.
public Receipt create(@RequestParam("batch") @Min(1) int batch,
                      @Valid @RequestBody CreateOrder request) { ... }
~~~

Ba đoạn trên **chỉ là chữ ký minh họa**, không phải các phương thức Java độc lập. Điều đáng chú ý: với **Spring Framework 6.1+**, (A) thường đi theo **validation của argument riêng lẻ** và có thể ném `MethodArgumentNotValidException`; (B), (C) thường đi theo **method validation tích hợp của Spring MVC** và có thể ném `HandlerMethodValidationException`. Trong (C), cả lỗi thuộc tính của DTO cũng có thể được gom vào method validation. Khi lớp controller còn `@Validated` ở **mức class**, đường đi có thể thay đổi qua proxy AOP và exception lại khác.

Hiểu được các cơ chế này giúp bạn:
- Biết trường hợp nào kích hoạt kiểm tra argument, trường hợp nào kích hoạt toàn bộ phương thức.
- Dùng `@Valid`, `@Validated` và các constraint như `@NotBlank`/`@Min` đúng chỗ.
- Phân biệt lỗi JSON, lỗi chuyển kiểu, lỗi field validation, lỗi method validation, và lỗi phía server khi giá trị trả về vi phạm contract.
- Thiết kế `@ControllerAdvice` xử lý ổn định khi dự án nâng Spring Framework/Spring Boot.

**Phạm vi:** Spring MVC trên Servlet stack. Bài đặc biệt phân biệt các nhánh trong **Spring Framework 6.0, 6.1, 6.2**; Java 17+, Jakarta Bean Validation và Spring Boot 3.x. Spring Boot 2.x/Spring 5.x được nhắc để nhận diện migration. Spring WebFlux có exception/adapter riêng, không lấy bảng của MVC áp dụng nguyên xi.

## 2. Phân biệt ba tầng xử lý

Với request JSON ví dụ:

~~~http
POST /api/registrations?batch=0 HTTP/1.1
Content-Type: application/json

{"name":"","email":"not-an-email","tickets":0}
~~~

Một handler có thể gặp lỗi ở các tầng khác nhau:

~~~text
HTTP request
  │
  ▼
DispatcherServlet tìm handler + handler argument resolvers
  │
  ├── Đọc/parse/bind request, đổi kiểu, kiểm tra điều kiện required
  │     ├── JSON sai / thiếu body                → HttpMessageNotReadableException
  │     ├── query thiếu                         → MissingServletRequestParameterException
  │     └── query không đổi được kiểu          → MethodArgumentTypeMismatchException
  │
  ├── Bean Validation cho từng @RequestBody/@ModelAttribute/@RequestPart
  │     └── MethodArgumentNotValidException (khi phù hợp)
  │
  ├── Built-in MVC method validation (Spring 6.1+, khi kích hoạt)
  │     └── HandlerMethodValidationException
  │
  └── Gọi handler, có thể xác minh constraint trên return value
        └── HandlerMethodValidationException (isForReturnValue = true)
~~~

Sơ đồ trên là **đường ra quyết định**, không có nghĩa một request phải đi qua đủ từng loại validation. Khi method validation áp dụng, Spring MVC phối hợp với argument validation để **tránh kiểm tra trùng**, và có thể phát sinh `HandlerMethodValidationException` cho các lỗi lồng trong DTO. Khi sử dụng **AOP method validation** với `@Validated` trên class, một proxy khác tham gia và có thể phát sinh `ConstraintViolationException`/`MethodValidationException`.

Đừng đánh đồng mọi HTTP 400 với `MethodArgumentNotValidException`. Request sai cú pháp, sai Content-Type hay không chuyển được kiểu có thể bị từ chối **trước khi Bean Validation chạy**.

## 3. Nền tảng Jakarta Bean Validation

### 3.1. Constraint là gì?

Các annotation của `jakarta.validation.constraints` chứa quy tắc được validator kiểm tra:

| Annotation | Áp dụng thường gặp | Ghi chú |
| --- | --- | --- |
| `@NotNull` | reference khác null | Cho phép chuỗi rỗng, khác `@NotBlank` |
| `@NotBlank` | `CharSequence` có ký tự không phải whitespace | Không phù hợp cho `long`/`int` |
| `@NotEmpty` | chuỗi, collection, map, array | Không tự loại whitespace-only cho chuỗi |
| `@Size(min=..., max=...)` | chuỗi/collection/array | Kiểm tra độ dài/kích thước, không phải giá trị số |
| `@Min(1)`, `@Max(10)` | số tương thích | So sánh giá trị số |
| `@Positive`, `@PositiveOrZero` | số | 0 chỉ hợp lệ với `PositiveOrZero` |
| `@Email` | chuỗi dạng địa chỉ email | Nên kết hợp `@NotBlank` nếu không cho phép vắng/rỗng |
| `@Pattern(regexp="...")` | chuỗi | Regex là constraint riêng, không chuyển đổi input |
| `@Valid` | đối tượng lồng nhau / collection elements | **Kích hoạt cascade**, tự nó **không phải constraint** |
| Spring `@Validated` | chọn validation groups, kích hoạt AOP class/method ở ngữ cảnh phù hợp | Không đồng nghĩa `@Valid` ở mọi vị trí |

Ví dụ DTO có Bean Validation metadata:

~~~java
package com.example.validationdemo.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank @Size(max = 80) String name,
        @NotBlank @Email String email,
        @Min(1) int tickets) {
}
~~~

Mẫu này dùng Java record. Nếu gửi JSON `{"name":"","email":"bad","tickets":0}`, có thể có nhiều violations: `name` blank, `email` sai định dạng và `tickets` nhỏ hơn 1. **Bắt buộc có Bean Validation provider** (thường Hibernate Validator qua `spring-boot-starter-validation`); chỉ import các annotation không tự đảm bảo Spring chạy được validation.

Với kiểu primitive `int`, thuộc tính JSON không được cung cấp có thể thành giá trị mặc định trong một số đường deserialize/bind, phụ thuộc cấu hình; nếu cần phân biệt “vắng mặt” với số 0, chọn `Integer` với `@NotNull` và kiểm thử JSON thực tế.

### 3.2. `@Valid` không tự kích hoạt method validation

Cần phân biệt:

~~~java
public String save(@Valid @RequestBody SignupRequest input)
~~~

với

~~~java
public String save(@NotNull @Valid @RequestBody SignupRequest input)
~~~

Trong Spring MVC 6.1+, ví dụ đầu **chỉ** yêu cầu cascade validation của đối tượng riêng lẻ khi đủ điều kiện; ví dụ sau có `@NotNull` là **constraint trực tiếp trên method parameter**, từ đó kích hoạt method validation. Việc thêm một annotation có thể làm đổi kiểu exception dù cùng DTO và cùng request JSON.

Không thêm `@NotNull` vô thức chỉ để “tăng độ an toàn”. `@RequestBody` mặc định `required=true` đã có cơ chế kiểm tra thiếu body. Hai cách kiểm tra diễn ra ở tầng khác nhau và có thể cho ra error response khác.

### 3.3. Groups và vị trí của `@Validated`

`@Validated(Group.class)` của Spring có thể dùng ở tham số để định nghĩa validation groups cho argument. `@Validated` **mức class controller** có ý nghĩa khác: nó là tín hiệu cho cơ chế AOP method validation nếu có post-processor tương ứng. Từ Spring 6.1, nếu muốn dùng **built-in MVC method validation**, hãy **bỏ `@Validated` ở mức class**. Tài liệu Spring nêu rõ yêu cầu này.

Trong Spring Boot 3.x, hãy kiểm tra dependency/runtime thực sự có validator và cấu hình MVC, thay vì giả định chỉ cần annotation thì tất cả constraints đều có hiệu lực.

## 4. Hai kiểu validation trong Spring MVC 6.1+

### 4.1. Individual argument validation

Một method chỉ có DTO cần validate và **không có method constraints trực tiếp**:

~~~java
@PostMapping("/object")
public Receipt object(@Valid @RequestBody SignupRequest request) {
    return new Receipt(request.name(), request.tickets());
}
~~~

Với Bean Validation provider và không có `Errors`/`BindingResult` ngay sau argument, lỗi constraint trên record thường tạo:

~~~text
org.springframework.web.bind.MethodArgumentNotValidException
HTTP status mặc định: 400 Bad Request
~~~

`MethodArgumentNotValidException` mang một `BindingResult`. Bạn có thể đọc:
- `getFieldErrors()`: lỗi thuộc tính như `name` và `tickets`.
- `getGlobalErrors()`: lỗi mức object.
- `getAllErrors()`: tổng hợp errors.
- `getBindingResult()`: binding/validation result để render response lỗi.

Áp dụng tương tự về nguyên tắc cho `@Valid @ModelAttribute` và `@Valid @RequestPart` (kiểu DTO thích hợp). Điều kiện chính xác còn phụ thuộc annotation, object type, method signature và có method validation hay không.

### 4.2. Built-in MVC method validation

Có constraint **trực tiếp trên tham số method** hoặc **trên method return value**:

~~~java
@GetMapping("/page")
public PageView page(@RequestParam("page") @Min(1) int page) {
    return new PageView(page);
}
~~~

Với Spring Framework **6.1+**, không đặt `@Validated` ở class và có validator phù hợp, `GET /page?page=0` vi phạm `@Min(1)` thường sinh:

~~~text
org.springframework.web.method.annotation.HandlerMethodValidationException
HTTP status mặc định: 400 Bad Request (input violation)
~~~

Cùng method có thể kiểm tra DTO lồng:

~~~java
@PostMapping("/method")
public Receipt method(
        @RequestParam("batch") @Min(1) int batch,
        @Valid @RequestBody SignupRequest request) {
    return new Receipt(request.name(), request.tickets());
}
~~~

Vì `@Min(1)` trên `batch`, method validation **bao phủ** cả lỗi `batch` và lỗi cascade từ `@Valid SignupRequest`. Do đó, khi gửi `batch=1` nhưng DTO sai, vẫn có thể nhận **`HandlerMethodValidationException`**, không phải `MethodArgumentNotValidException`. Đây là điểm migration dễ bỏ sót: **kiểu exception phụ thuộc toàn bộ chữ ký handler, không chỉ annotation của DTO**.

`HandlerMethodValidationException` gom các kết quả theo tham số (`ParameterValidationResult`; lỗi bean có thể được biểu diễn qua `ParameterErrors`). Nó có `getAllValidationResults()` và `visitResults(Visitor)` để phân loại các nguồn như `@RequestParam`, `@PathVariable`, `@RequestHeader`, `@ModelAttribute`; không giả định chỉ có một field error của DTO.

### 4.3. Return value validation

Method cũng có thể khai báo constraint trên **kết quả trả về**:

~~~java
@GetMapping("/returned")
@NotBlank
public String returned() {
    return "";
}
~~~

Trong demo, handler trả chuỗi blank nên vi phạm contract `@NotBlank`. Với built-in MVC method validation (Spring 6.1+), có thể phát sinh `HandlerMethodValidationException` với `isForReturnValue() == true`. **Status mặc định là 500 Internal Server Error**, vì đây là lỗi hợp đồng **phía server**, khác với dữ liệu request không hợp lệ (400). Không viết handler bắt tất cả validation exception rồi ép thành HTTP 400.

Sự khác biệt này rất quan trọng khi monitoring: 4xx thường đại diện vấn đề đầu vào từ client; 5xx do method return violation phải được phát hiện và sửa trong code/service.

### 4.4. `BindingResult` / `Errors` ngay sau tham số

~~~java
@PostMapping("/form")
public ResponseEntity<?> form(
        @Valid @ModelAttribute SignupForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Form invalid");
    }
    return ResponseEntity.ok("Accepted");
}
~~~

Đây là fragment minh họa; `SignupForm` phải là DTO form bind được. Với `BindingResult`/`Errors` **ngay sau** đối tượng được validate, controller có thể tự xử lý lỗi của đối tượng đó. Nếu method validation cũng áp dụng, Spring chỉ tiếp tục gọi handler khi các lỗi có thể được xử lý trong các tham số `Errors` phù hợp; **có lỗi ở một tham số khác không có `Errors` ngay sau** thì vẫn ném `HandlerMethodValidationException`. Không đặt `BindingResult` tùy ý cuối chữ ký hoặc dùng nó như trình bắt lỗi cho `@RequestParam @Min`.

Tình huống hay nhầm:

~~~java
// Đây không phải bộ bắt lỗi chung cho mọi method parameter:
public String submit(
        @Valid @ModelAttribute SignupForm form,
        BindingResult result,
        @RequestParam("page") @Min(1) int page) {
    ...
}
~~~

Nếu `page=0`, controller không đương nhiên được gọi chỉ vì có `BindingResult` cho `form`.

## 5. Ma trận exception theo phiên bản và cơ chế

| Ngữ cảnh | Spring Framework trước 6.1 (đặc biệt 5.x/6.0) | Spring Framework 6.1+/6.2 | Trạng thái điển hình |
| --- | --- | --- | --- |
| `@Valid @RequestBody DTO`, không có direct method constraint và không có `BindingResult` | `MethodArgumentNotValidException` | `MethodArgumentNotValidException` | 400 |
| `@Valid @ModelAttribute DTO`, không có `BindingResult` | Có thể gặp `BindException` (nhất là MVC cũ); trên Spring 6.0 đã chuyển nhiều nhánh sang `MethodArgumentNotValidException` | `MethodArgumentNotValidException` khi individual validation áp dụng | 400 |
| Direct `@Min`/`@NotBlank` trên method parameter, không dùng AOP `@Validated` class | Trước 6.1 **chưa có built-in MVC method validation mới**; phải dựa cấu hình khác, thường AOP | `HandlerMethodValidationException` | 400 nếu input vi phạm |
| Có direct method constraint **và** `@Valid` DTO trên cùng handler | Validation của DTO có thể chạy ở argument resolver; direct constraints cần cơ chế AOP phù hợp | Method validation bao phủ cả direct và cascade constraints → `HandlerMethodValidationException` | 400 |
| Constraint trên **return value** của handler | Thường cần AOP/executable validation riêng | Built-in MVC method validation → `HandlerMethodValidationException` | 500 nếu server trả sai |
| `@Validated` **ở class**, AOP method validation hoạt động | Phổ biến: `ConstraintViolationException` | Vẫn có thể đi theo AOP: `ConstraintViolationException`, hoặc `MethodValidationException` nếu AOP cấu hình adapt | Phụ thuộc exception handler; **không mặc định suy ra 400** |
| JSON sai cú pháp hoặc thiếu required body | `HttpMessageNotReadableException` | `HttpMessageNotReadableException` | Thường 400 |
| `@RequestParam` bắt buộc bị thiếu | `MissingServletRequestParameterException` | `MissingServletRequestParameterException` | Thường 400 |
| `@RequestParam int` nhận `abc` | `MethodArgumentTypeMismatchException`/conversion error | Tương tự | Thường 400 |

**Cách đọc bảng:** lỗi validation thực tế phụ thuộc chữ ký, resolver, Bean Validation provider, filter/AOP, `BindingResult`, handler và cấu hình ngoại lệ. Không kết luận kiểu exception chỉ từ HTTP status hoặc chỉ từ một annotation.

### 5.1. Spring Boot phiên bản nào tương ứng?

Để định hướng migration (không dùng bảng này thay cho việc xem dependency tree):
- **Boot 2.x** dùng Spring Framework **5.x**, namespace Bean Validation phổ biến là `javax.validation.*`.
- **Boot 3.0–3.1** dùng Spring Framework **6.0.x**; dùng `jakarta.validation.*`, **chưa có built-in MVC method validation kiểu 6.1**.
- **Boot 3.2–3.3** dùng Spring Framework **6.1.x** trong baseline phổ biến.
- **Boot 3.4–3.5** thường dùng Spring Framework **6.2.x** theo dependency management chuẩn.

Dự án override dependencies có thể khác. **Kiểm tra phiên bản Spring thực sự chạy** (ví dụ `./gradlew dependencies --configuration runtimeClasspath` hoặc Maven dependency tree) và dùng tài liệu versioned tương ứng. Đừng đổi code chỉ vì thấy tên Spring Boot major version.

### 5.2. AOP `@Validated` và `ConstraintViolationException`

Trong các phiên bản cũ, method validation bằng Spring AOP thường yêu cầu:
1. Có `jakarta.validation.Validator` (hoặc `javax.validation.Validator` theo thế hệ).
2. Có `MethodValidationPostProcessor` / auto-configuration tương đương.
3. Controller/service bean được proxy và method call **đi qua proxy**.
4. Thường có `@Validated` ở mức class cần proxy.

Vi phạm method constraint qua `MethodValidationInterceptor` **mặc định** được ném bằng `jakarta.validation.ConstraintViolationException`. Từ Spring 6.1, có khả năng cấu hình `MethodValidationPostProcessor.setAdaptConstraintViolations(true)` để tạo `org.springframework.validation.method.MethodValidationException`. Hai exception này **khác** `HandlerMethodValidationException` của MVC built-in.

Đối với controller Spring MVC 6.1+, nếu giữ `@Validated` tại class, bạn có thể nhận `ConstraintViolationException` sau khi nâng cấp ngay cả khi mong đợi `HandlerMethodValidationException`. Tài liệu Spring khuyến nghị **bỏ class-level `@Validated`** để dùng MVC method validation mới. **Không bỏ `@Validated` trên service** chỉ vì controller cần thay: AOP method validation vẫn hữu ích cho tầng service, nơi không có HTTP method argument resolver.

### 5.3. Lịch sử `BindException` và chú ý khi nâng cấp

Nhiều ứng dụng MVC lâu năm viết:

~~~java
@ExceptionHandler(org.springframework.validation.BindException.class)
public ResponseEntity<?> handleForm(BindException ex) { ... }
~~~

Đoạn trên là minh họa ý tưởng; phải import/khai báo handler đầy đủ trong dự án thật. Trong Spring MVC 6.0, nhiều trường hợp `@ModelAttribute` đã dùng `MethodArgumentNotValidException` (là subclass của `BindException` ở nhánh tương ứng). Khi migration, kiểm tra lại class exception thực tế, phạm vi handler và tương tác với `ResponseEntityExceptionHandler`. Đừng giữ nhiều `@ExceptionHandler` có phạm vi chồng lấn trên cùng advice nếu dẫn đến ambiguity.

**`MethodValidationException` không phải tên mới của `MethodArgumentNotValidException`.** Nó đại diện đường method validation API/AOP và có cách xử lý riêng. Đừng dùng string matching như `ex.getClass().getSimpleName()` hoặc catch toàn bộ `Exception` rồi trả 400.

## 6. Ví dụ Spring Boot 3.3 / Spring Framework 6.1: chạy và tái hiện hai exception chính

Ví dụ dưới đây dùng **Spring Boot 3.3.5** (baseline Spring Framework 6.1.x) với Java 17+. Các tệp có package/class độc lập và có thể chạy trong một project Gradle Spring Boot tương ứng. Không đặt `@Validated` ở class controller để đường built-in MVC method validation được kích hoạt.

Cấu trúc:

~~~text
validation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/validationdemo/
    │   ├── ValidationDemoApplication.java
    │   ├── api/SignupRequest.java
    │   └── web/
    │       ├── ValidationController.java
    │       └── ValidationErrorAdvice.java
    └── test/java/com/example/validationdemo/web/
        └── ValidationControllerTest.java
~~~

### 6.1. Build config

`settings.gradle`:

~~~groovy
rootProject.name = 'validation-demo'
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

Phần `spring-boot-starter-validation` rất quan trọng: Hibernate Validator cung cấp việc thực thi các annotation `@NotBlank`/`@Email`/`@Min`. Ví dụ giả định Gradle 8.x tương thích Java 17 và Spring Boot 3.3, có Gradle wrapper do bạn tạo cho project. Nếu dùng dự án đã có plugin/dependency management khác, chỉ thêm starter cần thiết và giữ phiên bản do dự án quản lý.

### 6.2. Main application

`src/main/java/com/example/validationdemo/ValidationDemoApplication.java`:

~~~java
package com.example.validationdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` ở package root để component scan tìm controller và advice.

### 6.3. DTO request có constraints

`src/main/java/com/example/validationdemo/api/SignupRequest.java`:

~~~java
package com.example.validationdemo.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank @Size(max = 80) String name,
        @NotBlank @Email String email,
        @Min(1) int tickets) {
}
~~~

### 6.4. Controller: đối chứng individual vs method validation

`src/main/java/com/example/validationdemo/web/ValidationController.java`:

~~~java
package com.example.validationdemo.web;

import com.example.validationdemo.api.SignupRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/validation")
public class ValidationController {

    public record Receipt(String name, int tickets) {}
    public record PageView(int page) {}

    // Chỉ validate DTO: individual argument validation.
    @PostMapping("/object")
    public Receipt object(@Valid @RequestBody SignupRequest request) {
        return new Receipt(request.name(), request.tickets());
    }

    // @Min là direct constraint: bật MVC method validation.
    @PostMapping("/method")
    public Receipt method(
            @RequestParam("batch") @Min(1) int batch,
            @Valid @RequestBody SignupRequest request) {
        return new Receipt(request.name(), request.tickets());
    }

    @GetMapping("/page")
    public PageView page(@RequestParam("page") @Min(1) int page) {
        return new PageView(page);
    }

    // Return-value constraint: lỗi phía server phải thành 500.
    @GetMapping("/returned")
    @NotBlank
    public String returned() {
        return "";
    }

    // Có BindingResult ngay sau DTO, xử lý lỗi tại controller.
    @GetMapping("/form")
    public ResponseEntity<Map<String, Boolean>> form(
            @Valid @ModelAttribute FormInput form,
            BindingResult result) {
        return ResponseEntity.ok(Map.of("valid", !result.hasErrors()));
    }

    public static class FormInput {
        @NotBlank
        private String keyword;

        public FormInput() {}

        public String getKeyword() {
            return keyword;
        }

        public void setKeyword(String keyword) {
            this.keyword = keyword;
        }
    }
}
~~~

Chú ý **không dùng `@Validated` ở class**. `@Min(1)` trên `batch` và `page` là những constraint trực tiếp. `@NotBlank` trên `returned()` là constraint trên return value. `FormInput` là DTO dành cho form/query với field `keyword`, và `BindingResult` đứng sát DTO.

### 6.5. Xử lý hai exception của MVC theo một hợp đồng JSON

`src/main/java/com/example/validationdemo/web/ValidationErrorAdvice.java`:

~~~java
package com.example.validationdemo.web;

import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ValidationErrorAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        Map<String, Object> body = Map.of(
                "kind", "argument",
                "fieldErrors", ex.getBindingResult().getFieldErrorCount());

        return new ResponseEntity<>(body, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        Map<String, Object> body = Map.of(
                "kind", "method",
                "resultGroups", ex.getAllValidationResults().size(),
                "returnValue", ex.isForReturnValue());

        return new ResponseEntity<>(body, headers, status);
    }
}
~~~

Ưu điểm:
- Override **đúng hook** của `ResponseEntityExceptionHandler`, thay vì khai báo trùng một `@ExceptionHandler` đã được superclass quản lý.
- Dùng status do framework tính sẵn; với method validation, status có thể là **400 cho input** hoặc **500 cho return value**.
- Dùng `getBindingResult()` ở trường hợp individual và `getAllValidationResults()` ở trường hợp method, phù hợp cấu trúc dữ liệu lỗi của từng loại.
- Không đưa `rejectedValue` (có thể chứa bí mật) trực tiếp vào JSON trả cho client.

Mẫu JSON này là **hợp đồng minh họa của ứng dụng**, không phải body lỗi mặc định của mọi Spring Boot project. Trong sản phẩm thực tế, nên dùng `ProblemDetail`/RFC 9457, message code, localization, trace ID và field paths ổn định. Có thể viết một lớp chuyển đổi riêng để hai nhánh đều xuất ra error schema thống nhất mà vẫn phân biệt được nguyên nhân trong log/telemetry.

## 7. Chạy ứng dụng và xem lỗi thực tế

Từ thư mục dự án đã có wrapper tương ứng:

~~~bash
./gradlew bootRun
~~~

Gọi request sai DTO nhưng **không có direct method constraint**:

~~~bash
curl -i -X POST 'http://localhost:8080/api/validation/object' \
  -H 'Content-Type: application/json' \
  -d '{"name":"","email":"bad","tickets":0}'
~~~

Kết quả dự kiến là **HTTP 400** với response do `ValidationErrorAdvice` tạo, dạng:

~~~json
{"kind":"argument","fieldErrors":3}
~~~

Với default provider/constraints trong ví dụ, `name` blank, `email` invalid, `tickets` dưới 1 tạo ba field violations. **Không dựa vào thứ tự** của field errors để xây UI.

Gọi method có direct parameter constraint:

~~~bash
curl -i -X POST 'http://localhost:8080/api/validation/method?batch=0' \
  -H 'Content-Type: application/json' \
  -d '{"name":"An","email":"an@example.com","tickets":2}'
~~~

Dự kiến **HTTP 400**, body:

~~~json
{"kind":"method","resultGroups":1,"returnValue":false}
~~~

`resultGroups` đếm các **tham số có errors**, không phải số field violations. Nếu gửi `batch=1` nhưng DTO invalid, cũng là lỗi method validation với `kind=method`; số nhóm tùy tham số vi phạm.

Gọi return-value validation:

~~~bash
curl -i 'http://localhost:8080/api/validation/returned'
~~~

Dự kiến **HTTP 500** (mẫu response phía ứng dụng):

~~~json
{"kind":"method","resultGroups":0,"returnValue":true}
~~~

Giá trị `resultGroups=0` trong ví dụ return-only phản ánh danh sách **parameter** results có thể rỗng; return-value violation có API riêng và không nên suy diễn “không có lỗi” từ số nhóm tham số. Nếu triển khai API công khai, hãy giữ thông tin chi tiết của lỗi return ở server logs và trả thông điệp 500 an toàn cho client.

Gọi form query lỗi nhưng có `BindingResult`:

~~~bash
curl -i 'http://localhost:8080/api/validation/form?keyword='
~~~

Dự kiến:

~~~json
{"valid":false}
~~~

HTTP là **200 OK** vì chính controller chủ động chọn `ResponseEntity.ok(...)` để minh họa việc được gọi. Trong hệ thống thực tế, lựa chọn `400` hoặc render form với HTTP 200 tùy loại ứng dụng; ở đây 200 không có nghĩa dữ liệu hợp lệ.

**Phân biệt loại lỗi:** JSON cú pháp sai hoặc thiếu body có thể bị `HttpMessageNotReadableException` **trước khi** vào validation. Query `page=abc` có thể bị conversion error **trước khi** `@Min` được kiểm tra. Không kỳ vọng `ValidationErrorAdvice` hai override ở trên sẽ đổi cả những lỗi này thành `kind=method`/`kind=argument`.

## 8. Kiểm thử MockMvc bắt đúng exception theo hành vi

`src/test/java/com/example/validationdemo/web/ValidationControllerTest.java`:

~~~java
package com.example.validationdemo.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ValidationController.class)
@Import(ValidationErrorAdvice.class)
class ValidationControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidDtoWithoutDirectConstraintUsesArgumentValidation() throws Exception {
        mvc.perform(post("/api/validation/object")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\",\"email\":\"bad\",\"tickets\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.kind").value("argument"))
                .andExpect(jsonPath("$.fieldErrors").value(3));
    }

    @Test
    void directConstraintUsesBuiltInMethodValidation() throws Exception {
        mvc.perform(post("/api/validation/method")
                        .param("batch", "0")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"An\",\"email\":\"an@example.com\","
                               + "\"tickets\":2}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.kind").value("method"))
                .andExpect(jsonPath("$.returnValue").value(false));
    }

    @Test
    void nestedDtoUsesMethodValidationWhenDirectConstraintExists() throws Exception {
        mvc.perform(post("/api/validation/method")
                        .param("batch", "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\",\"email\":\"bad\",\"tickets\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.kind").value("method"));
    }

    @Test
    void invalidReturnValueIsServerFailure() throws Exception {
        mvc.perform(get("/api/validation/returned"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.kind").value("method"))
                .andExpect(jsonPath("$.returnValue").value(true));
    }

    @Test
    void adjacentBindingResultHandlesFormErrorsLocally() throws Exception {
        mvc.perform(get("/api/validation/form").param("keyword", ""))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(false));
    }

    @Test
    void validDtoWorks() throws Exception {
        mvc.perform(post("/api/validation/object")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\",\"email\":\"lan@example.com\","
                               + "\"tickets\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.tickets").value(2));
    }
}
~~~

Bỏ import không dùng `ObjectMapper` nếu IDE/linter cảnh báo; test đang gửi JSON string trực tiếp nên không cần serialize Java object. Mỗi test xác minh **status lẫn loại exception được advice phân loại**, tránh test body lỗi mặc định thay đổi theo configuration.

Chạy:

~~~bash
./gradlew test
~~~

Các test giả định ứng dụng mẫu, Bean Validation provider và Spring MVC test auto-configuration đầy đủ. Nếu project có Spring Security, custom `@ControllerAdvice`, custom validator hoặc filter, `@WebMvcTest` có thể cần cấu hình thêm. Không đem test với cấu hình khác rồi kết luận Spring 6.1 xử lý sai mà chưa xác minh method validation và proxy thực sự được bật.

### 8.1. Test chi tiết exception nếu cần

Ngoài body, có thể assert resolved exception:

~~~java
// Trích từ một @Test đã cấu hình MockMvc:
// .andExpect(result ->
//     assertInstanceOf(MethodArgumentNotValidException.class,
//                      result.getResolvedException()));
~~~

`assertInstanceOf` từ JUnit 5 và `MethodArgumentNotValidException` từ Spring. Đây là đoạn minh họa được comment, cần imports tương ứng. Với lỗi method, thay bằng `HandlerMethodValidationException.class`. Chọn kiểm tra chính xác exception khi mục tiêu là **migration hoặc regression về cơ chế**, còn với API client nên ưu tiên test schema/status ổn định.

## 9. Chuẩn hóa lỗi cho frontend mà không mất ngữ nghĩa

Một error contract thực tế có thể là:

~~~json
{
  "type": "https://example.org/problems/validation",
  "title": "Invalid request",
  "status": 400,
  "violations": [
    {"field": "name", "message": "must not be blank"},
    {"field": "tickets", "message": "must be greater than or equal to 1"}
  ]
}
~~~

JSON trên là **ví dụ thiết kế**, không phải body tự động của Spring. Việc nhận diện field/method parameter tùy:
- `MethodArgumentNotValidException`: dùng `BindingResult` / `FieldError` để truy ra object path.
- `HandlerMethodValidationException`: dùng `getAllValidationResults()` hoặc `visitResults(Visitor)`; có thể có lỗi trực tiếp trên parameter, lỗi nested bean và cross-parameter.
- `ConstraintViolationException`: dùng tập `ConstraintViolation<?>`; path của Jakarta Bean Validation có thể chứa method/parameter names khác với tên HTTP bên ngoài.
- `MethodValidationException`: có `MethodValidationResult` tương ứng; đây không phải HTTP-specific exception.

Không đưa trực tiếp path nội bộ `methodName.arg0` làm API contract nếu muốn ổn định qua refactor. Map tên theo ý nghĩa HTTP (`@RequestParam`/`@PathVariable`) hoặc DTO field khi hợp lệ và phù hợp privacy policy.

Trong Spring MVC 6.1+/6.2, `ResponseEntityExceptionHandler` có hook `handleMethodArgumentNotValid` và `handleHandlerMethodValidationException`, đủ để xử lý hai đường validation built-in. Nếu subclass đã override hook, đừng thêm `@ExceptionHandler` trùng signature trong cùng advice vì superclass đã dùng `@ExceptionHandler` để dispatch.

Trường hợp `ConstraintViolationException` từ AOP cần một đường xử lý khác, chẳng hạn advice chuyên cho service boundary với mapping mã lỗi có chủ đích. Không tự động biến tất cả `ConstraintViolationException` thành 400: có thể là lỗi được tạo khi gọi service nội bộ, không phải dữ liệu client.

## 10. Những lỗi dễ nhầm với validation

| Lỗi quan sát | Ngoại lệ thường gặp | Ý nghĩa | Hướng xử lý |
| --- | --- | --- | --- |
| Body JSON thiếu/sai cú pháp | `HttpMessageNotReadableException` | Converter không tạo được object | Kiểm tra raw request, `Content-Type`, JSON parser |
| DTO tồn tại nhưng constraint sai | `MethodArgumentNotValidException` hoặc `HandlerMethodValidationException` | Bean Validation / method validation | Xem signature, Spring version, AOP, `BindingResult` |
| Query `page=xyz` với `int` | `MethodArgumentTypeMismatchException` | Không chuyển kiểu được | Kiểm tra converter/formatter và HTTP contract |
| Thiếu `@RequestParam(required=true)` | `MissingServletRequestParameterException` | Thiếu nguồn bắt buộc | Thêm input / đổi default/required có chủ đích |
| Unsupported Content-Type | `HttpMediaTypeNotSupportedException` | Không có mapping/converter tương thích | Điều chỉnh header/payload/`consumes` |
| Constraint trên return value sai | `HandlerMethodValidationException` với `isForReturnValue=true` ở 6.1+ | Server trả sai contract | Trả 500, ghi log và sửa producer |
| Có `@Validated` mức class và method AOP | `ConstraintViolationException` hoặc `MethodValidationException` | Đường proxy validation | Xem proxy, `MethodValidationPostProcessor` và version |
| `BindingResult` không nhận được lỗi | Exception vẫn phát sinh | Đặt sai vị trí hoặc lỗi thuộc tham số khác | Đặt ngay sau DTO và tách xử lý method violations |
| `@Valid` không có tác dụng | Không có provider, thiếu constraint/cascade, hoặc sai nơi đặt | Validation chưa được kích hoạt như dự kiến | Kiểm dependency, imports, DTO và test |
| Handler không bao giờ vào | Bị reject trước controller hoặc method validation | Đúng với input lỗi trong nhiều trường hợp | Log có kiểm soát exception class + status + route |

Đặc biệt, Spring Boot có thể render body lỗi khác nhau phụ thuộc cấu hình `spring.mvc.problemdetails.enabled`, custom advice, MessageSource và phiên bản. Để bảo vệ contract frontend, test output API của ứng dụng; để chẩn đoán cơ chế, test/ghi nhận **exception class**.

## 11. Nâng cấp Spring MVC an toàn: trình tự kiểm tra

1. **Ghi nhận phiên bản trước và sau**: `spring-webmvc`, `spring-context`, `jakarta.validation-api` và provider thực tế. Từ Boot 2 sang 3 phải đổi namespace `javax.validation` → `jakarta.validation`, đồng thời dùng phiên bản thư viện tương thích.
2. **Liệt kê controller có `@Validated` ở class** và direct constraint trên method parameters/return. Với Spring 6.1+, cân nhắc bỏ class annotation để chọn built-in MVC validation. Giữ AOP validation ở những service thực sự cần.
3. **Đối chiếu chữ ký từng handler**, không chỉ DTO: `@Min` ở `@RequestParam` có thể chuyển cả `@Valid @RequestBody` trong cùng method sang `HandlerMethodValidationException`.
4. **Kiểm tra `BindingResult` đứng sát argument** nếu controller chủ động xử lý form/body errors. Nếu muốn tất cả lỗi đi qua advice, bỏ đường xử lý cục bộ có chủ đích và thống nhất contract.
5. **Cập nhật advice** để xử lý cả `MethodArgumentNotValidException` lẫn `HandlerMethodValidationException`. Tách return-value violations (500) khỏi client input errors (400).
6. **Xác minh phương thức/proxy và nhóm validation**. AOP self-invocation không được proxy theo cơ chế thông thường; dùng interface/class proxy thay đổi điểm chặn. Đừng quy mọi vấn đề này thành bug của Bean Validation.
7. **Chạy test đối chứng**: valid request, invalid DTO, direct query constraint, hai loại cùng lúc, return-value violation, JSON sai, thiếu required query và binding error.
8. **Quan sát exception thật** trong log/test khi có khác biệt, vì custom `ControllerAdvice` và phiên bản framework có thể ảnh hưởng kết quả. Không truy xuất sensitive `rejectedValue` khi ghi log.
9. **Giữ format lỗi công khai ổn định**: status, type, machine-readable code, field names, locale/message source; không để class name của exception thành API contract.
10. **Kiểm tra validation xảy ra ở ranh giới thích hợp**: request validation cho HTTP input; business invariant và transaction validation ở service/domain; response validation failure là lỗi server.

### Câu hỏi tự kiểm tra

**1.** `@Valid @RequestBody Dto` mà không có direct method constraint, thiếu `BindingResult`, thường phát sinh lỗi gì ở Spring 6.1+?

**Đáp án:** `MethodArgumentNotValidException` khi Bean Validation phát hiện DTO vi phạm.

**2.** Cũng DTO đó, nhưng method nhận thêm `@RequestParam @Min(1) int quantity` thì sao?

**Đáp án:** Built-in method validation được kích hoạt; lỗi direct parameter hoặc lỗi cascade DTO có thể tạo `HandlerMethodValidationException`.

**3.** Tại sao có project nâng Boot rồi lại thấy `ConstraintViolationException`?

**Đáp án:** Có thể controller đang được method validate bởi AOP vì class-level `@Validated`/`MethodValidationPostProcessor`; nên kiểm tra kiểu proxy và version trước khi thay logic xử lý exception.

**4.** `@Valid` đã đủ để kích hoạt method validation khi không có constraint trực tiếp chưa?

**Đáp án:** Không. `@Valid` yêu cầu cascade validation; nó không phải một `@Constraint` trực tiếp như `@NotNull`.

**5.** Tại sao return-value constraint vi phạm nên là 500?

**Đáp án:** Client không kiểm soát được việc server trả một giá trị sai với contract mà server đã công bố; đây là lỗi phía server.

**6.** `BindingResult` sau `@Valid Dto` có xử lý được lỗi `@Min` trên tham số thứ ba không?

**Đáp án:** Không. Nó gắn với DTO đứng ngay trước, không đại diện mọi lỗi của method.

## 12. Tài liệu chính thức để tra theo phiên bản

- [Spring Framework 6.2 — Validation trong Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): phân biệt individual argument vs method validation, `BindingResult`, class-level `@Validated` và hai MVC exception.
- [Spring Framework 6.1 — HandlerMethodValidationException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html): API `isForReturnValue`, `getAllValidationResults`, `visitResults`, status 400/500.
- [Spring Framework 6.1 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): hook xử lý `MethodArgumentNotValidException`/`HandlerMethodValidationException`.
- [Spring Framework 6.1 — MethodValidationPostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.7/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html): AOP method validation, `ConstraintViolationException` và `setAdaptConstraintViolations`.
- [Spring Framework — `@RequestBody` validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): validation, `BindingResult` và xử lý converter.
- [Spring Framework 6.x Upgrade Notes](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x): hướng dẫn migration lên 6.x và tích hợp method validation.
- [Jakarta Bean Validation specification](https://jakarta.ee/specifications/bean-validation/3.0/): phân biệt constraint, cascade, groups và executable validation.

**Ghi nhớ:** hãy xác định **(1) thời điểm giải mã/bind, (2) có direct method constraint hay không, (3) có `BindingResult` sát argument không, (4) controller có class-level `@Validated`/AOP không, (5) phiên bản Spring MVC cụ thể**. Năm điều này thường giải thích vì sao cùng một lỗi đầu vào lại đi qua các exception khác nhau.
