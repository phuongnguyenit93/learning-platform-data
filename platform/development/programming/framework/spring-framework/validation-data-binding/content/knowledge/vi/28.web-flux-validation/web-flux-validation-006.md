# WebExchangeBindException và xử lý lỗi phản ứng trong Spring WebFlux

## 1. WebExchangeBindException là gì?

Trong **Spring WebFlux**, khi một controller dùng `@Valid` hoặc `@Validated` để kiểm tra command object từ request, Spring có thể phát sinh:

```java
org.springframework.web.bind.support.WebExchangeBindException
```

Đây là exception báo rằng **dữ liệu đã đi qua bước binding/giải tuần tự hóa thành object, nhưng object không đạt các quy tắc validation được áp dụng**. Exception chứa thông tin `BindingResult`: field errors, global errors, object name, error codes và thông báo lỗi. Với request input thông thường, Spring xử lý thành **HTTP 400 Bad Request**.

Ví dụ:

```java
@PostMapping("/accounts")
public Mono<AccountView> create(
        @Valid @RequestBody AccountInput input) {
    return service.create(input);
}
```

Nếu `AccountInput` có `@NotBlank String name` mà client gửi `"name": " "`, WebFlux có thể ném `WebExchangeBindException` **trước khi thân controller được gọi**. Nếu controller khai báo input kiểu `Mono<AccountInput>`, exception thường xuất hiện như một **tín hiệu lỗi trong publisher**, và có thể được xử lý bằng Reactor operator như `onErrorResume`.

Điều dễ nhầm: Spring MVC ở Servlet stack thường dùng `MethodArgumentNotValidException` cho tình huống validation tương đương. **Đừng copy handler MVC rồi chờ nó bắt lỗi WebFlux**. Cả hai cùng cung cấp thông tin binding/validation, nhưng class và mô hình thực thi khác nhau.

**Phạm vi bài:** Spring Framework 6.1–6.2, Spring Boot 3.x, Java 17+, Jakarta Validation 3.x, annotated controllers trên Spring WebFlux. Đặc điểm của controller functional routing (WebFlux.fn) được trình bày riêng. Những ví dụ dùng package `jakarta.validation`, không phải `javax.validation` của dự án cũ.

## 2. Lỗi validation nằm ở bước nào của chuỗi phản ứng?

Một lời gọi REST WebFlux đi qua các bước:

```text
HTTP request
    |
    v
Reactor Netty / web server adapter
    |
    v
WebFilter -> DispatcherHandler
    |
    v
Handler mapping -> annotated controller
    |
    v
Argument resolver + HttpMessageReader / codec
    |  giải tuần tự hóa JSON hoặc multipart part thành Java object
    |
    +-- JSON sai cú pháp / kiểu không đọc được
    |       -> ServerWebInputException hoặc lỗi codec liên quan
    |
    v
Bean Validation (@Valid / @Validated)
    |
    +-- Object không đạt constraint
    |       -> WebExchangeBindException
    |       -> onError signal hoặc exception resolution
    |
    v
Controller business flow -> Mono/Flux
    |
    v
Return serialization / ServerHttpResponse
```

Đường thực tế còn phụ thuộc vào hình thức argument:

- **`@Valid @RequestBody AccountInput input`:** framework phải resolve argument thành object **trước khi gọi** handler. Nếu validation thất bại, body controller không được chạy; một `@RestControllerAdvice` có thể xử lý exception.
- **`@Valid @RequestBody Mono<AccountInput> input`:** controller nhận publisher; khi body được đọc, decode và validate trong pipeline, lỗi có thể đi theo tín hiệu `onError` của `Mono`. Controller có thể tự dùng `onErrorResume(WebExchangeBindException.class, ...)` ngay trên chuỗi ấy.
- **`@Valid @RequestPart("metadata") Mono<Metadata> metadata`:** tương tự, nhưng object đến từ **một part** của request multipart, đọc bằng codec thích hợp.
- **`@Valid @ModelAttribute Form form`:** Spring WebFlux dùng data binding cho form/command object; lỗi validation cũng có thể biểu diễn bằng `WebExchangeBindException`.
- **Constraint trực tiếp trên tham số method** như `@Min(1)` ở `@PathVariable int page`: từ Framework 6.1+, đây có thể là **method validation**, dẫn đến `HandlerMethodValidationException`, không phải `WebExchangeBindException`.

Từ khóa “phản ứng” không có nghĩa Bean Validation tự biến thành tác vụ bất đồng bộ. Provider Jakarta Validation thường thực hiện kiểm tra **đồng bộ, tại chỗ** khi object đã có. Phần reactive là cách request body được đọc và cách **lỗi được phát ra, lan truyền hoặc phục hồi** trong `Mono`/`Flux`.

## 3. Phân biệt binding, validation, deserialization và business errors

Bốn tình huống có thể cùng biểu hiện HTTP 400 nhưng nguyên nhân rất khác:

| Đầu vào / sự kiện | Giai đoạn thất bại | Exception điển hình | Cách ứng phó |
| --- | --- | --- | --- |
| JSON hợp lệ, `name=" "` với `@NotBlank` | Bean Validation | `WebExchangeBindException` | Trả field error, HTTP 400 |
| JSON hợp lệ, `age=15` với `@Min(18)` | Bean Validation | `WebExchangeBindException` | Trả field error, HTTP 400 |
| JSON malformed `{"name":` | Decode/parse | `ServerWebInputException` hoặc codec error được bọc | Trả mã payload không đọc được, HTTP 400 |
| Thiếu `@RequestBody` bắt buộc | Argument resolution | `ServerWebInputException` | Trả lỗi thiếu body, HTTP 400 |
| Content-Type không hỗ trợ | Codec/content negotiation | `UnsupportedMediaTypeStatusException` hoặc lỗi HTTP 415 tương ứng | Trả HTTP 415 |
| `@PathVariable @Min(1) int page` sai | Method validation | `HandlerMethodValidationException` | Thường HTTP 400 |
| Controller trả dữ liệu trái return constraint | Method return validation | `HandlerMethodValidationException` | Thường HTTP 500 |
| Tài khoản/email đã tồn tại | Nghiệp vụ/repository | Exception hoặc kết quả do ứng dụng thiết kế | HTTP 409 có thể phù hợp, không gộp với binding |
| Hệ thống kho dữ liệu mất kết nối | Runtime/infrastructure | Exception từ service/database | Thường 5xx, tránh trả 400 |

**Không gán tất cả vào `WebExchangeBindException`.** Một JSON sai cú pháp không có object hợp lệ để kiểm tra `@NotBlank`, và một quy tắc uniqueness phụ thuộc database không được bảo đảm chỉ bằng Jakarta Validation trên DTO.

### 3.1. Một constraint @NotNull không đủ để bắt mọi trường trống

Ví dụ:

```java
public record AccountInput(
        @NotBlank String name,
        @NotNull @Min(18) Integer age
) {}
```

- `name = null`, `""` hoặc `"   "` không qua `@NotBlank`.
- `age = 15` không qua `@Min(18)`.
- `age = null` không qua `@NotNull`; bản thân `@Min` coi null hợp lệ theo contract Jakarta Validation.
- `age = "abc"` trong JSON có thể thất bại ngay ở Jackson/codec do không chuyển thành Integer được. Đó không phải chứng cứ `@Min` đã chạy.
- Nếu thiếu annotation kích hoạt validation tại boundary, sự hiện diện của `@NotBlank` trong record không bảo đảm mọi controller tự validate.

### 3.2. Cascading: @Valid trên trường con

```java
public record Address(
        @NotBlank String city
) {}

public record AccountInput(
        @NotBlank String name,
        @NotNull @Min(18) Integer age,
        @NotNull @Valid Address address
) {}
```

`@Valid` trên `address` yêu cầu đi vào object con để đánh giá `city`. Nếu bỏ `@Valid` này, một `Address` có `city=""` có thể vượt qua lần validate outer object. Ngược lại, `@Valid` không tự cấm null: cần `@NotNull` khi address bắt buộc.

Với collection, Jakarta Validation hỗ trợ container-element constraints và cascading (ví dụ `List<@Valid Item>`) khi cấu trúc phù hợp. Tuy nhiên **top-level List/Map** trong argument không nên được giả định có đường validation y hệt command object trong mọi WebFlux signature. Nếu cần input phức tạp, hãy dùng wrapper DTO và test HTTP thực tế.

## 4. Exception chứa những thông tin gì?

`WebExchangeBindException` có thể cung cấp dữ liệu từ `BindingResult`:

```java
ex.getBindingResult().getFieldErrors();
ex.getBindingResult().getGlobalErrors();
ex.getBindingResult().getAllErrors();
ex.getBindingResult().getObjectName();
```

Đó là **snippet minh họa bên trong một exception handler** có biến `ex` kiểu `WebExchangeBindException`. Exception còn triển khai các method tương tự của binding error để truy cập trực tiếp.

### 4.1. FieldError

Mỗi `FieldError` có thể chứa:

- `getField()`: tên property bị vi phạm, ví dụ `name`, `age` hoặc `address.city`.
- `getCode()`: mã lỗi ngắn do Spring sinh cho constraint hoặc binding, ví dụ `NotBlank`, `Min`, `NotNull`.
- `getCodes()`: các message codes có thể dùng để nội suy thông báo theo độ cụ thể.
- `getDefaultMessage()`: message đã được nội suy, có thể thay đổi theo locale và message bundle.
- `getRejectedValue()`: giá trị bị từ chối; **không được phản chiếu tùy tiện** nếu có password/token/PII.
- `isBindingFailure()`: phân biệt một số lỗi binding/type conversion với lỗi validation; không thay thế việc hiểu exception gốc.

`getCode()` khá hữu ích để chuẩn hóa thông tin cho UI, nhưng API lớn nên ánh xạ sang **mã lỗi nghiệp vụ ổn định** do ứng dụng định nghĩa thay vì buộc client phụ thuộc hoàn toàn cách Spring/provider đặt code.

### 4.2. ObjectError / global error

Custom constraint cấp lớp có thể tạo `ObjectError` cho quan hệ nhiều trường. Nếu handler chỉ đọc `getFieldErrors()` mà bỏ qua `getGlobalErrors()`, response có thể **thiếu lỗi quan trọng**. Một error DTO tốt cần diễn đạt cả lỗi field và lỗi object-level.

Ví dụ response có thể chuẩn hóa:

```json
{
  "code": "VALIDATION_ERROR",
  "fields": [
    {"field": "age", "code": "Min"},
    {"field": "name", "code": "NotBlank"}
  ]
}
```

Đây là **format do ứng dụng quyết định**, không phải JSON mặc định bắt buộc của Spring WebFlux. Thứ tự các constraint violations không được cam kết; nếu muốn thứ tự ổn định cho snapshot/test, sort theo tên field và code như trong demo.

### 4.3. Trạng thái HTTP và Problem Details

`WebExchangeBindException` có hợp đồng HTTP error response của Spring, thông thường status **400 Bad Request**. Spring Framework hỗ trợ `ProblemDetail` và RFC 9457; có thể dùng `ResponseEntityExceptionHandler` của **package WebFlux** để tùy biến chung, hoặc viết `@RestControllerAdvice` để trả contract JSON riêng.

Đừng import nhầm `ResponseEntityExceptionHandler` trong namespace Servlet MVC khi ứng dụng chạy WebFlux:

```java
// WebFlux:
org.springframework.web.reactive.result.method.annotation
        .ResponseEntityExceptionHandler

// Spring MVC:
org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler
```

Tên đơn giản giống nhau nhưng loại HTTP runtime và cách kết hợp handler khác nhau. Ví dụ runnable dùng `@RestControllerAdvice` trực tiếp để dễ kiểm tra chính xác các response.

## 5. Xử lý lỗi phản ứng: onError khác try/catch

### 5.1. Error là tín hiệu của Publisher

Một `Mono<T>` có ba loại tín hiệu chính:

```text
onSubscribe
    |
    +-- onNext(value) -> onComplete     (thành công)
    |
    +-- onComplete                      (không có giá trị)
    |
    +-- onError(error)                   (thất bại)
```

Một publisher kết thúc bằng `onError` không phát thêm giá trị hay `onComplete` nữa. Khi Spring WebFlux deserialize và validate request từ `Mono<AccountInput>`, `WebExchangeBindException` có thể trở thành chính tín hiệu `onError`.

`try/catch` bao quanh câu lệnh **tạo Mono** thường không bắt được lỗi phát sinh **sau khi publisher được subscribe**. Ví dụ:

```java
try {
    return request.map(this::save);
} catch (WebExchangeBindException ex) {
    // Thường không chạy khi lỗi xảy ra trong reactive pipeline.
}
```

Đây là **minh họa**, giả sử `request` và `save` đã định nghĩa. Cách xử lý lỗi reactive phù hợp là:

```java
return request
        .map(this::save)
        .onErrorResume(
                WebExchangeBindException.class,
                ex -> Mono.just(fallbackResponse(ex))
        );
```

Trong đó `fallbackResponse` phải có cùng loại dữ liệu kết quả với pipeline; code trên là **snippet**, không phải phương thức độc lập.

### 5.2. Những operator quan trọng

| Operator | Vai trò | Nên dùng khi |
| --- | --- | --- |
| `onErrorResume(Type.class, ex -> alternateMono)` | Chuyển lỗi phù hợp sang publisher khác | Trả 400 có cấu trúc / fallback có chủ đích |
| `onErrorMap(Type.class, mapper)` | Chuyển loại exception | Muốn giữ lỗi và chuẩn hóa một domain exception |
| `doOnError(Type.class, consumer)` | Side effect quan sát lỗi, không phục hồi | Log/metric không chứa dữ liệu nhạy cảm |
| `onErrorReturn(value)` | Trả giá trị thay thế vô điều kiện cho lỗi phù hợp | Chỉ khi fallback là nghiệp vụ hợp lệ |
| `switchIfEmpty(alternate)` | Xử lý publisher hoàn thành **không có giá trị** | Khác hoàn toàn lỗi validation |
| `onErrorContinue` | Bỏ qua phần tử lỗi trong vài operator | **Không phù hợp mặc định** để bỏ lỗi validation input |
| `retry(...)` | Đăng ký lại publisher sau lỗi | Không nên retry lỗi request không hợp lệ |

Ví dụ **không nên làm**:

```java
return validatedInput
        .onErrorReturn(new AccountInput("guest", 18, new Address("X")));
```

Đoạn này có thể biến một request sai thành account giả được chấp nhận, che giấu lỗi người dùng và tạo dữ liệu không đúng intent. Trong API tạo tài nguyên, hãy trả HTTP 400 rõ ràng hoặc giữ lỗi cho exception handler xử lý.

### 5.3. Không nuốt mọi exception

```java
.onErrorResume(Throwable.class, error ->
        Mono.just(badRequest()))
```

Đoạn phản ví dụ trên biến **mọi lỗi** (database, bug, permission, server failure) thành HTTP 400, khiến client bị đổ lỗi sai. Chỉ bắt `WebExchangeBindException` khi muốn xử lý validation locally; các lỗi khác nên được đưa tới handler phù hợp hoặc propagate.

Nếu dùng `doOnError` để log, tránh in `FieldError#getRejectedValue()` cho dữ liệu nhạy cảm, không đổ stack trace của mọi input 400 vào hệ thống logging.

## 6. Ba nơi có thể đặt error handling trong WebFlux

### 6.1. Ngay trong controller: local recovery

Khi argument là `Mono<AccountInput>`, controller có thể xử lý lỗi tại chỗ:

```java
@PostMapping("/accounts/reactive")
public Mono<ResponseEntity<Map<String, Object>>> create(
        @Valid @RequestBody Mono<AccountInput> body) {

    return body
        .map(this::created)
        .onErrorResume(WebExchangeBindException.class, ex -> {
            Map<String, Object> error =
                    Map.of("code", "LOCAL_VALIDATION_ERROR");
            return Mono.just(ResponseEntity.badRequest().body(error));
        });
}
```

Đây là snippet minh họa; `created` giả định trả `ResponseEntity<Map<String,Object>>`. Khi lỗi đúng loại phát sinh từ publisher, nhánh `onErrorResume` **thay thế** tín hiệu lỗi bằng response. Vì lỗi đã được xử lý, global `@RestControllerAdvice` không còn nhận nó.

Ưu điểm: local logic ở sát endpoint, thích hợp nếu chỉ một luồng có phản hồi đặc biệt. Nhược điểm: lặp error mapping ở nhiều controller; khó bảo đảm nhất quán nếu mọi method viết logic khác nhau.

### 6.2. @RestControllerAdvice: response chuẩn hóa toàn annotated controllers

```java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    Mono<ResponseEntity<ApiError>> invalid(
            WebExchangeBindException ex) {
        // ...
    }
}
```

Đây là snippet; trong demo bên dưới có class đầy đủ. Advice xử lý exception phát sinh khi Spring resolve argument hoặc error được propagate từ handler. Sử dụng một mapping chung giúp client nhận contract 400 đồng nhất.

### 6.3. WebExceptionHandler / ErrorWebExceptionHandler: lớp web chung

Spring WebFlux còn có tầng xử lý lỗi thấp hơn:

- `org.springframework.web.server.WebExceptionHandler`: xử lý exception trong web handling chain thông qua `Mono<Void>`.
- `org.springframework.boot.web.reactive.error.ErrorWebExceptionHandler`: Spring Boot cung cấp hạ tầng lỗi web reactive, bao gồm đường default error handling.
- `@ControllerAdvice` là cơ chế **của annotated controllers**; không nên mặc nhiên cho rằng handler này bắt tất cả lỗi của WebFlux.fn, WebFilter hoặc lỗi đã xảy ra trước khi controller được chọn.

WebFlux.fn không tự có cơ chế argument resolver `@Valid @RequestBody` theo cách annotated controller, vì handler dùng `ServerRequest` và viết pipeline riêng. Nếu cần validate functional endpoint, bạn thường gọi `Validator` theo chủ đích rồi quyết định phản hồi trong `Mono<ServerResponse>`, hoặc dùng component error handler phù hợp.

Nếu response đã commit, global handler không chắc còn quyền đổi status hay ghi lại body. Vì vậy hãy validate input **trước các side effect**, và tránh tạo partial response trước khi biết request hợp lệ.

## 7. Dự án Spring Boot chạy được: global advice và local onErrorResume

Ví dụ dùng Java 17, Spring Boot **3.3.6**, Spring WebFlux 6.1.x và Jakarta Validation. Ứng dụng có:

- `POST /api/accounts` với **DTO trực tiếp**: lỗi được `@RestControllerAdvice` xử lý.
- `POST /api/accounts/reactive` với **Mono<DTO>`: lỗi validation được `onErrorResume` trong controller xử lý.
- `GET /api/pages/{page}` có constraint trực tiếp `@Min(1)` để đối chiếu `HandlerMethodValidationException`.
- `WebTestClient` kiểm tra đường thành công, lỗi field/nested constraint, JSON malformed, local recovery và method validation.

### 7.1. Cấu trúc dự án

```text
webflux-validation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/webfluxvalidation/
    │   ├── WebfluxValidationApplication.java
    │   ├── Address.java
    │   ├── AccountInput.java
    │   ├── FieldIssue.java
    │   ├── ApiError.java
    │   ├── AccountController.java
    │   └── ApiErrorAdvice.java
    └── test/java/com/example/webfluxvalidation/
        └── AccountControllerTest.java
```

### 7.2. Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'webflux-validation-demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chỉ dùng `spring-boot-starter-webflux`, **không thêm `spring-boot-starter-web`** vào ví dụ. Spring Boot thường ưu tiên Servlet MVC khi cả hai starter web và webflux cùng có mặt; thêm cả hai rồi suy ra app chạy reactive là sai. Nếu thực sự cần cả hai thư viện, có thể cấu hình loại ứng dụng reactive và test rõ runtime, nhưng không cần cho bài này.

`spring-boot-starter-validation` đưa Jakarta Validation provider lên classpath (thường Hibernate Validator). Không có provider phù hợp, `@Valid` trong controller có thể không cho hiệu quả mong đợi.

### 7.3. Application

Tệp `src/main/java/com/example/webfluxvalidation/WebfluxValidationApplication.java`:

```java
package com.example.webfluxvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebfluxValidationApplication.class, args);
    }
}
```

### 7.4. DTO có nested validation

Tệp `src/main/java/com/example/webfluxvalidation/Address.java`:

```java
package com.example.webfluxvalidation;

import jakarta.validation.constraints.NotBlank;

public record Address(
        @NotBlank String city
) {}
```

Tệp `src/main/java/com/example/webfluxvalidation/AccountInput.java`:

```java
package com.example.webfluxvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record AccountInput(
        @NotBlank String name,
        @NotNull @Min(18) Integer age,
        @NotNull @Valid Address address
) {}
```

Với request:

```json
{
  "name": " ",
  "age": 15,
  "address": {"city": ""}
}
```

object được deserialize thành công nhưng vi phạm `@NotBlank`, `@Min(18)` và nested `Address.city`. `@NotNull @Valid` trên `address` vừa cấm thiếu object, vừa cho phép cascade vào thành phần con.

### 7.5. Error DTO độc lập với exception nội bộ

Tệp `src/main/java/com/example/webfluxvalidation/FieldIssue.java`:

```java
package com.example.webfluxvalidation;

public record FieldIssue(String field, String code) {}
```

Tệp `src/main/java/com/example/webfluxvalidation/ApiError.java`:

```java
package com.example.webfluxvalidation;

import java.util.List;

public record ApiError(
        String code,
        List<FieldIssue> fields
) {}
```

Client nhận mã lỗi và field, không nhận `rejectedValue`, stack trace hoặc chi tiết nội bộ. DTO có `List<FieldIssue>` nhưng danh sách này được tạo **sau khi bắt lỗi**; nó không phải request payload.

### 7.6. Controller: dữ liệu thường và publisher

Tệp `src/main/java/com/example/webfluxvalidation/AccountController.java`:

```java
package com.example.webfluxvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.support.WebExchangeBindException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class AccountController {

    // DTO trực tiếp: exception xuất hiện lúc argument resolution.
    // @RestControllerAdvice xử lý nếu validation thất bại.
    @PostMapping(
        path = "/accounts",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<Map<String, Object>>> create(
            @Valid @RequestBody AccountInput input) {

        return Mono.just(created(input));
    }

    // Mono<DTO>: validation error có thể đi theo onError signal,
    // nên controller tự xử lý bằng onErrorResume.
    @PostMapping(
        path = "/accounts/reactive",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<Map<String, Object>>> createReactive(
            @Valid @RequestBody Mono<AccountInput> input) {

        return input
                .map(AccountController::created)
                .onErrorResume(WebExchangeBindException.class, ex -> {
                    Map<String, Object> error = new LinkedHashMap<>();
                    error.put("code", "LOCAL_VALIDATION_ERROR");
                    error.put("fieldCount",
                            ex.getBindingResult().getFieldErrorCount());
                    return Mono.just(
                            ResponseEntity.badRequest().body(error)
                    );
                });
    }

    // Constraint trực tiếp -> method validation của WebFlux 6.1+.
    @GetMapping("/pages/{page}")
    public Mono<Map<String, Integer>> page(
            @PathVariable("page") @Min(1) int page) {

        return Mono.just(Map.of("page", page));
    }

    private static ResponseEntity<Map<String, Object>> created(
            AccountInput input) {

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("name", input.name());
        response.put("age", input.age());
        response.put("city", input.address().city());

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(response);
    }
}
```

Phân tích chi tiết:

- `create(...)` nhận DTO trực tiếp; khi validation sai, Spring xử lý trước khi chạy thân method. Nơi xử lý tập trung là `ApiErrorAdvice`.
- `createReactive(...)` nhận publisher. `onErrorResume(WebExchangeBindException.class, ...)` chỉ phục hồi loại lỗi validation này, không bắt mọi lỗi của service.
- `fieldCount` minh họa cách lấy thông tin từ `BindingResult`; trong API thật, thường nên trả danh sách field error có code ổn định thay vì chỉ số lượng.
- `page(...)` cố ý đặt `@Min(1)` **trực tiếp trên method parameter**. Nó kích hoạt method validation trong WebFlux 6.1+ và minh họa lỗi thuộc `HandlerMethodValidationException`.
- Controller **không** có `@Validated` cấp class, để giữ đường built-in method validation của Spring Framework 6.1+. Đặt `@Validated` vào type có thể làm Spring chuyển sang cơ chế AOP khác.

### 7.7. Global error handler

Tệp `src/main/java/com/example/webfluxvalidation/ApiErrorAdvice.java`:

```java
package com.example.webfluxvalidation;

import java.util.Comparator;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.server.ServerWebInputException;
import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public Mono<ResponseEntity<ApiError>> validation(
            WebExchangeBindException exception) {

        List<FieldIssue> fields =
                exception.getBindingResult()
                        .getFieldErrors()
                        .stream()
                        .map(this::fieldIssue)
                        .sorted(Comparator
                                .comparing(FieldIssue::field)
                                .thenComparing(FieldIssue::code))
                        .toList();

        return Mono.just(
                ResponseEntity.badRequest()
                        .body(new ApiError("VALIDATION_ERROR", fields))
        );
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public Mono<ResponseEntity<ApiError>> methodValidation(
            HandlerMethodValidationException exception) {

        String code = exception.isForReturnValue()
                ? "SERVER_CONTRACT_VIOLATION"
                : "METHOD_VALIDATION_ERROR";

        return Mono.just(
                ResponseEntity.status(exception.getStatusCode())
                        .body(new ApiError(code, List.of()))
        );
    }

    @ExceptionHandler(ServerWebInputException.class)
    public Mono<ResponseEntity<ApiError>> unreadable(
            ServerWebInputException exception) {

        // Không trả exception.getMessage() hoặc raw JSON ra client.
        return Mono.just(
                ResponseEntity.status(exception.getStatusCode())
                        .body(new ApiError("INVALID_PAYLOAD", List.of()))
        );
    }

    private FieldIssue fieldIssue(FieldError error) {
        String code = error.getCode() == null
                ? "invalid"
                : error.getCode();

        return new FieldIssue(error.getField(), code);
    }
}
```

Vì `WebExchangeBindException` là một loại `ServerWebInputException`, Spring chọn handler cụ thể hơn khi lỗi thực sự là `WebExchangeBindException`. Handler tổng quát `ServerWebInputException` dành cho lỗi giải tuần tự hóa/binding input khác, ví dụ JSON sai cú pháp trong cấu hình thường gặp.

Các lựa chọn trong demo:

- **VALIDATION_ERROR:** Bean Validation của command object, HTTP 400, có danh sách field error đã sort.
- **LOCAL_VALIDATION_ERROR:** cùng bản chất validation nhưng được khôi phục ngay trong publisher của endpoint `/accounts/reactive`. Advice không chạy cho lỗi đã được bắt local.
- **METHOD_VALIDATION_ERROR:** ràng buộc trực tiếp của method parameter không đạt; với input lỗi, HTTP 400.
- **SERVER_CONTRACT_VIOLATION:** ràng buộc trên method return value không đạt; HTTP 500. Dù demo không tạo output violation, handler được viết đúng hướng để không nhầm lỗi server thành 400.
- **INVALID_PAYLOAD:** lỗi input mà codec/resolver không đọc được; HTTP 400 theo exception status trong demo.

**Global errors:** ví dụ này cố ý dùng `getFieldErrors()` vì DTO chỉ có field constraints. Nếu dự án có class-level constraints, handler cần bổ sung `getGlobalErrors()` để không bỏ sót vi phạm.

## 8. Kiểm thử WebFlux với WebTestClient

`WebTestClient` phù hợp cho controller reactive; có thể test status, headers và JSON body mà không cần gọi network thủ công. Tệp `src/test/java/com/example/webfluxvalidation/AccountControllerTest.java`:

```java
package com.example.webfluxvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class AccountControllerTest {

    @Autowired
    private WebTestClient client;

    @Test
    void validRequestIsCreated() {
        client.post().uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Lan",
                          "age": 25,
                          "address": {"city": "Hanoi"}
                        }
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Lan")
                .jsonPath("$.age").isEqualTo(25)
                .jsonPath("$.city").isEqualTo("Hanoi");
    }

    @Test
    void invalidDtoIsCaughtByAdvice() {
        client.post().uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": " ",
                          "age": 15,
                          "address": {"city": ""}
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_ERROR")
                .jsonPath("$.fields.length()").isEqualTo(3);
    }

    @Test
    void nestedConstraintProducesPropertyPath() {
        client.post().uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Lan",
                          "age": 25,
                          "address": {"city": ""}
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fields[0].field").isEqualTo("address.city")
                .jsonPath("$.fields[0].code").isEqualTo("NotBlank");
    }

    @Test
    void invalidMonoInputIsRecoveredLocally() {
        client.post().uri("/api/accounts/reactive")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "",
                          "age": 15,
                          "address": {"city": "Hanoi"}
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("LOCAL_VALIDATION_ERROR")
                .jsonPath("$.fieldCount").isEqualTo(2);
    }

    @Test
    void validMonoInputPasses() {
        client.post().uri("/api/accounts/reactive")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Mai",
                          "age": 30,
                          "address": {"city": "Danang"}
                        }
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Mai");
    }

    @Test
    void malformedJsonIsNotValidationError() {
        client.post().uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":\"Lan\",\"age\":")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_PAYLOAD");
    }

    @Test
    void directParameterConstraintUsesMethodValidation() {
        client.get().uri("/api/pages/0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("METHOD_VALIDATION_ERROR");
    }

    @Test
    void validMethodParameterPasses() {
        client.get().uri("/api/pages/2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(2);
    }
}
```

Chạy:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

**Kỳ vọng:** tám bài test PASS khi dự án có Gradle wrapper, Java 17 và dependency đúng cấu hình. Bài kiểm tra `$.fields.length()` quan sát số lỗi, còn thử nested constraint tách riêng để field path cụ thể. Do handler sort các field, chỉ khi input có **một** lỗi ở `address.city` mới assert nó ở vị trí đầu tiên; không coi thứ tự thô từ provider là ổn định.

Khi ứng dụng chạy, thử:

```bash
./gradlew bootRun
```

Với `curl` trên shell có hỗ trợ quoting POSIX:

```bash
curl -i http://localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","age":25,"address":{"city":"Hanoi"}}'
```

Kỳ vọng HTTP `201 Created`, body chứa:

```json
{"name":"Lan","age":25,"city":"Hanoi"}
```

Nếu gửi:

```bash
curl -i http://localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -d '{"name":" ","age":15,"address":{"city":""}}'
```

Kỳ vọng HTTP `400 Bad Request` với `code = VALIDATION_ERROR`. Giá trị `fields` trong response liệt kê các lỗi `name`, `age` và `address.city`. Không dùng message tiếng Anh của Hibernate Validator làm hợp đồng client.

**Lưu ý về QA:** mã là dự án mẫu đã được thiết kế đầy đủ về class/file/import/test, nhưng không thể suy ra runtime tại mọi máy và mọi phiên bản phụ thuộc sẽ giống hệt. Khi chuyển sang Spring Boot 4/Framework 7, xác minh thay đổi API, Java baseline và đường exception bằng test thực tế.

## 9. Xử lý BindingResult trực tiếp trong controller

WebFlux cũng cho phép nhận `Errors`/`BindingResult` ngay sau một argument **không reactive**:

```java
@PostMapping("/accounts/manual")
public Mono<ResponseEntity<ApiError>> manual(
        @Valid @RequestBody AccountInput input,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just(
                ResponseEntity.badRequest().body(
                        new ApiError("VALIDATION_ERROR", List.of())
                )
        );
    }

    return Mono.just(ResponseEntity.ok(
            new ApiError("OK", List.of())
    ));
}
```

Đây là **method minh họa**, không có trong `AccountController.java` ở mục 7. Cần import `org.springframework.validation.BindingResult` và các kiểu còn lại. `BindingResult` phải đứng **ngay sau** `@RequestBody AccountInput` tương ứng; nếu xen một tham số khác, Spring không thể liên kết lỗi đúng cách.

**Không áp công thức đó trực tiếp cho `@RequestBody Mono<AccountInput>`:** khi argument là publisher, việc giải tuần tự hóa/validation diễn ra bất đồng bộ trong publisher. Để xử lý locally, dùng `onErrorResume`; tham số `BindingResult` cùng với `Mono<DTO>` không phải mô hình thay thế tương đương trong WebFlux.

Cũng cần phân biệt: nếu JSON **không thể parse**, `BindingResult` không giải quyết được vì object chưa tồn tại. Một handler `ServerWebInputException` hoặc error handling tầng codec vẫn cần thiết.

## 10. Validation groups trong pipeline phản ứng

`@Valid` thường dùng group `Default`. Nếu DTO có rules khác nhau theo thao tác, dùng `@Validated` của Spring ngay trên argument:

```java
public interface Create {}

public record AccountInput(
        @NotBlank(groups = Create.class) String name,
        @NotNull(groups = Create.class) Integer age
) {}

@PostMapping("/accounts")
public Mono<Void> create(
        @Validated(Create.class)
        @RequestBody Mono<AccountInput> input) {

    return input.then();
}
```

Đây là **snippet minh họa**, không dùng để thay các class demo ở mục 7. Khi lựa chọn `Create`, constraints thuộc `Default` **không được tự động cộng** vào, trừ khi có group inheritance/sequence phù hợp. `@Validated` là annotation Spring, không phải một validation provider riêng.

Nếu trong controller có direct method constraints hoặc return constraints, **method validation** của Framework 6.1+ có thể được chọn, thay đổi exception path. Tránh đặt `@Validated` trên controller class chỉ để làm cho `@Valid @RequestBody` chạy: nó có thể đưa controller vào AOP method validation, khó đoán handler nhận `WebExchangeBindException` hay exception AOP nếu không kiểm thử.

### 10.1. Không được mặc nhiên coi Mono<T> đã “valid” khi khởi tạo

Một `Mono<AccountInput>` có thể tồn tại mà chưa có request body được đọc hoặc được validate. Validation chỉ xảy ra khi publisher được subscribe và trải qua operator phù hợp. Vì vậy:

- Đặt các side effect **sau** bước nhận/kiểm tra dữ liệu.
- Không dùng `subscribe()` thủ công trong controller để “ép chạy validation”, vì như vậy làm lệch lifecycle, lỗi và cancellation khỏi WebFlux.
- Hãy **trả publisher** cho framework; Spring chịu trách nhiệm subscribe và ánh xạ tín hiệu.
- Nếu input sai, dùng `onErrorResume` để tạo response 400 hoặc propagate cho `@RestControllerAdvice`.
- Không gọi `block()` trong luồng xử lý WebFlux chỉ để lấy DTO, vì có thể chặn event loop và tạo vấn đề hiệu năng.

## 11. Xử lý @RequestPart và multipart trong WebFlux

Trong Spring WebFlux, file part thường được biểu diễn bằng `org.springframework.http.codec.multipart.FilePart`, **không phải** `MultipartFile` kiểu Servlet MVC. Ví dụ một handler nhận metadata JSON và file:

```java
@PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<ResponseEntity<String>> upload(
        @Valid @RequestPart("metadata") Mono<DocumentMetadata> metadata,
        @RequestPart("file") FilePart file) {

    return metadata.map(value ->
            ResponseEntity.ok("metadata:" + value.title()))
        .onErrorResume(
            WebExchangeBindException.class,
            ex -> Mono.just(
                ResponseEntity.badRequest().body("Metadata không hợp lệ"))
        );
}
```

Đây là **method minh họa**, giả sử `DocumentMetadata` là record có `@NotBlank String title`, controller đã import `FilePart` và Spring annotations. Nó không lưu file; trong ứng dụng thực tế, phải xử lý dòng dữ liệu upload và kiểm tra kích thước, Content-Type thực, tên file, quyền truy cập và lưu trữ an toàn.

Một part metadata muốn converter giải mã JSON cần có **Content-Type của part là application/json**. Nếu client gửi JSON dưới dạng text/plain, Spring không nhất thiết có message reader phù hợp để deserialize thành `DocumentMetadata`; lỗi này không phải `@NotBlank` violation.

`@RequestPart` trong annotated WebFlux có thể áp `@Valid` và tạo `WebExchangeBindException` khi metadata object sai; `onErrorResume` xử lý tín hiệu khi dùng `Mono<Metadata>`. Với multipart rất lớn, WebFlux còn có `PartEvent` và data buffer streams; phải **tiêu thụ hoặc release buffer đúng cách**, không dùng auto-buffer vô hạn rồi mới validate.

## 12. Functional endpoints: không tự có @Valid argument resolution

Một route WebFlux.fn:

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .POST("/functional/accounts", request ->
                request.bodyToMono(AccountInput.class)
                        .flatMap(input -> ServerResponse.ok()
                                .bodyValue(input.name())))
        .build();
```

Đây là snippet trong cấu hình Java và cần imports `RouterFunction`, `RouterFunctions`, `ServerResponse`; không phải ứng dụng độc lập. Ở đây `bodyToMono(AccountInput.class)` **chỉ deserialize**, không tự gọi Bean Validation như annotated `@Valid @RequestBody`.

Nếu cần validation trong functional handler, tiêm `jakarta.validation.Validator` và gọi:

```java
return request.bodyToMono(AccountInput.class)
        .flatMap(input -> {
            var violations = validator.validate(input);
            if (!violations.isEmpty()) {
                return ServerResponse.badRequest()
                        .bodyValue(Map.of("code", "VALIDATION_ERROR"));
            }
            return ServerResponse.ok()
                    .bodyValue(Map.of("name", input.name()));
        });
```

Đây là **thân handler minh họa**, giả sử `validator` đã được inject và `request` là `ServerRequest`. Nó cho thấy việc gọi `Validator#validate` là đồng bộ nhưng được thực hiện tại một điểm cụ thể trong reactive pipeline. Với validation tùy biến có thao tác I/O chặn như truy vấn JDBC, không được chạy công việc blocking tùy tiện trên event-loop thread.

Lỗi tự ném trong WebFlux.fn không nhất thiết được bắt bởi `@ControllerAdvice` của annotated controllers. Hãy chuẩn hóa tại functional handler/filter hoặc tại WebFlux `WebExceptionHandler` phù hợp, và test đường lỗi bằng `WebTestClient`.

## 13. Thiết kế lỗi JSON cho client và ProblemDetail

### 13.1. API error code ổn định

Một lỗi validation response nên thể hiện:

```json
{
  "code": "VALIDATION_ERROR",
  "fields": [
    {"field": "address.city", "code": "NotBlank"},
    {"field": "age", "code": "Min"}
  ]
}
```

Dùng field path và code để client highlight form. Không trả rejected values nếu có thể chứa password, token hay dữ liệu nhạy cảm. Với class-level constraints, thêm cơ chế báo global errors — ví dụ `errors` có `field = null` hoặc một cấu trúc `objectErrors` riêng.

Khi cần localize, phía client có thể dịch từ error code ổn định; hoặc server dùng `MessageSource`/locale để nội suy message. **Không** dùng exact text tiếng Việt/tiếng Anh làm cơ chế phân nhánh nghiệp vụ của client.

### 13.2. Spring Problem Details (RFC 9457)

Spring 6 hỗ trợ `ProblemDetail` với các field thông dụng `type`, `title`, `status`, `detail`, `instance`. Bạn có thể:

- Dùng `ResponseEntityExceptionHandler` dành cho WebFlux để tận dụng error response infrastructure;
- Hoặc viết `@ExceptionHandler` trả `ProblemDetail`;
- Hoặc giữ DTO riêng như `ApiError` của demo nếu cần tương thích contract sẵn có.

Không kết luận rằng mọi `WebExchangeBindException` tự động có response JSON chứa `fields` giống demo. Dạng response mặc định bị ảnh hưởng bởi Spring/Boot version, ProblemDetail settings và global error customization.

### 13.3. Ưu tiên mã lỗi hơn tên class exception

Client không nên biết class Java nội bộ `WebExchangeBindException`, `ServerWebInputException` hay `HandlerMethodValidationException`. Những class này là chi tiết Spring phía server. Client chỉ cần mã ổn định và HTTP status:

| Error code đề xuất | HTTP | Ý nghĩa |
| --- | --- | --- |
| `VALIDATION_ERROR` | 400 | DTO input đọc được nhưng có constraint sai |
| `INVALID_PAYLOAD` | 400 | Payload malformed/không deserialize được |
| `METHOD_VALIDATION_ERROR` | 400 | Direct parameter constraint sai |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Codec không hỗ trợ Content-Type |
| `SERVER_CONTRACT_VIOLATION` | 500 | Server trả kết quả trái return constraint |
| `CONFLICT` | 409 | Trạng thái nghiệp vụ xung đột như email đã tồn tại |

Các mã này **không phải tên error code mặc định của Spring**. Đây là gợi ý thiết kế API để tránh ghép logic frontend vào thông báo Jakarta Validation theo từng locale.

## 14. Tính an toàn và hiệu năng của validation trong reactive runtime

### 14.1. Bean Validation thường là đồng bộ

Hibernate Validator/Jakarta provider chạy các `ConstraintValidator` thông thường như công việc Java đồng bộ. Dù được gọi trong WebFlux request pipeline, một custom validator có I/O chặn sẽ **không tự trở thành non-blocking**.

Không nên viết:

```java
@Override
public boolean isValid(String value, ConstraintValidatorContext ctx) {
    return jdbcRepository.existsByName(value); // Blocking JDBC trên event loop!
}
```

Đây là **phản ví dụ**; không phải class đầy đủ. Nếu cần kiểm tra bất biến gắn với database, nên đưa nó sang service reactive (ví dụ dùng R2DBC/WebClient thích hợp) với pipeline kiểm tra và conflict handling riêng, không lạm dụng `ConstraintValidator#isValid` để làm I/O chặn trên event loop. Những kiểm tra deterministic (regex, range, length, format) rất phù hợp với Bean Validation.

### 14.2. Không retry validation errors

Retry `WebExchangeBindException` không làm client input tự thay đổi, chỉ khiến lặp việc đọc/kiểm tra. Retry có thể hữu ích cho transient network error, **không** cho input đã biết sai. Với flow ghi dữ liệu, cần tránh side effect trước validation và xác minh idempotency nếu retry được bật ở tầng khác.

### 14.3. Không để exception làm rò thông tin

Không trả raw:

```java
ex.getBindingResult().getFieldError().getRejectedValue();
ex.getMessage();
```

ra client. Chúng có thể chứa dữ liệu input nhạy cảm hoặc chi tiết nội bộ. Đối với logging/observability, chỉ ghi field name, mã lỗi và request correlation ID khi phù hợp, không log toàn bộ body/password/upload.

### 14.4. Hạn chế kích thước input

Vì JSON phải được decode thành object trước validation, constraint `@Size(max = ...)` **không đủ** để chống request quá lớn trước bước parse. Cấu hình request size, codec memory limit như `spring.codec.max-in-memory-size`, multipart limits, parser nesting limits và timeout tùy profile triển khai. Không ghép toàn bộ `Flux<DataBuffer>` thành một buffer vô hạn trước khi kiểm tra.

### 14.5. Cancellation và side effects

Trong Reactor, client hủy request có thể làm publisher bị cancel. Đừng đặt database write, gửi email hoặc side effect có thể xảy ra **trước** khi dữ liệu đã validate thành công. Và đừng nghĩ `onErrorResume` sau một side effect tự động rollback dữ liệu đã ghi. Những invariant transaction/authorization vẫn phải bảo đảm ở tầng phù hợp.

## 15. Debugging theo triệu chứng

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra |
| --- | --- | --- |
| DTO sai nhưng endpoint vẫn HTTP 200/201 | Thiếu `@Valid`, provider hoặc binding xảy ra ở đường khác | Kiểm tra annotation trên argument, starter validation, WebTestClient |
| JSON malformed không đi vào `@ExceptionHandler(WebExchangeBindException)` | Lỗi parse xảy ra trước Bean Validation | Bắt `ServerWebInputException`/codec error phù hợp |
| `onErrorResume` trong controller không chạy | Controller dùng DTO trực tiếp, lỗi xuất hiện trước khi method được gọi | Chuyển sang `Mono<DTO>` nếu cần local recovery hoặc dùng advice |
| `BindingResult` không nhận lỗi cho `Mono<DTO>` | Reactive argument xử lý dưới dạng publisher | Dùng `onErrorResume` |
| Field lồng nhau không được báo | Thiếu `@Valid` trên nested property | Thêm `@Valid`, test `address.city` |
| `@Min` không bắt null | `@Min` cho phép null | Thêm `@NotNull` |
| Handler bắt mọi lỗi và trả 400 | `onErrorResume(Throwable.class, ...)` quá rộng | Bắt đúng WebExchangeBindException và phân loại 5xx |
| Method argument `@Min` tạo exception khác | WebFlux built-in method validation 6.1+ | Xử lý `HandlerMethodValidationException` |
| Có `@Validated` cấp controller class và đường lỗi khác | AOP method validation đang can thiệp | Rà soát annotation, version, proxy và tests |
| File upload WebFlux bị lỗi kiểu | Import `MultipartFile` từ MVC hoặc thiếu Content-Type part | Dùng `FilePart`/`Part`, test multipart |
| Có cả Spring MVC và WebFlux starter | Boot chọn Servlet MVC làm web application | Kiểm tra dependency; loại bỏ starter không cần hoặc cấu hình reactive rõ |
| Body quá lớn báo lỗi trước `@Valid` | Codec/memory/request size limit | Cấu hình size limits, không xem là violation field |
| Dùng WebFlux.fn mà không nhận `WebExchangeBindException` | Không có annotated argument validation | Gọi validator thủ công và map HTTP error |

### Quy trình điều tra gọn

1. Xác nhận runtime thực sự là **Spring WebFlux** hay Servlet MVC.
2. Tìm entrypoint: annotated controller `@RequestBody`/`@RequestPart` hay functional `ServerRequest`.
3. Xác định argument là **DTO trực tiếp** hay `Mono<DTO>`.
4. Phân biệt parse/conversion error, Bean Validation failure và direct method constraint.
5. Tìm nơi lỗi bị xử lý: `onErrorResume` tại chỗ, `@RestControllerAdvice`, `WebExceptionHandler` hoặc default Spring Boot.
6. Kiểm tra error response status/code mà client nhìn thấy, cùng log server có correlation ID.
7. Viết test `WebTestClient` cho từng nguyên nhân, không chỉ assert một HTTP 400 chung.

## 16. Câu hỏi ôn tập và đáp án

**Câu 1.** Khi nào WebFlux thường phát sinh `WebExchangeBindException`?

Khi một command object của annotated controller được binding/deserialize thành công rồi không đạt Bean Validation do `@Valid`/`@Validated` yêu cầu, và không được xử lý theo `Errors`/`BindingResult` liền kề hoặc không bị method validation thay thế.

**Câu 2.** Vì sao `try/catch` ngoài `Mono.map` không luôn bắt validation error?

Vì lỗi phát sinh **khi publisher được subscribe**, không nhất thiết tại thời điểm tạo object `Mono`. Hãy dùng `onErrorResume` hoặc để Spring exception resolution xử lý.

**Câu 3.** Khác nhau giữa `@Valid @RequestBody AccountInput` và `@Valid @RequestBody Mono<AccountInput>`?

Argument DTO trực tiếp thường phải resolve trước khi gọi handler và lỗi đi qua exception resolver; publisher argument có thể mang lỗi vào pipeline, thuận tiện xử lý local bằng Reactor error operators.

**Câu 4.** Vì sao không bắt `WebExchangeBindException` cho JSON sai cú pháp?

Vì Java object chưa được deserialize đầy đủ; lỗi thường nằm ở message reader/codec, ví dụ `ServerWebInputException`.

**Câu 5.** Vì sao `@Min(18)` không thay thế `@NotNull`?

`@Min` theo Jakarta Validation coi null hợp lệ; muốn bắt trường vắng mặt cần ràng buộc khác.

**Câu 6.** `HandlerMethodValidationException` khác `WebExchangeBindException` thế nào?

Một loại dành cho **method validation** với constraint trực tiếp trên parameters/return value; loại kia dành cho **validation của một command object argument**. Từ Spring 6.1+, ứng dụng WebFlux nên chuẩn bị xử lý cả hai tùy signature.

**Câu 7.** Có nên trả giá trị bị từ chối từ `FieldError#getRejectedValue()`?

Không mặc định. Dữ liệu đó có thể chứa bí mật hoặc PII; trả field và error code ổn định là lựa chọn an toàn hơn.

**Câu 8.** `@ControllerAdvice` có tự validate object trong WebFlux.fn không?

Không. Functional handler dùng `ServerRequest`, phải chủ động gọi `Validator` và xây error response ở đúng pipeline, hoặc dùng handler web error tổng quát phù hợp.

## 17. Checklist triển khai

1. Dùng `spring-boot-starter-webflux` và `spring-boot-starter-validation`; xác nhận không vô tình chạy Servlet MVC.
2. Tách input DTO khỏi entity/domain; dùng constraint Jakarta phù hợp và `@Valid` cho nested object.
3. Xác định nên nhận DTO trực tiếp hay `Mono<DTO>` theo nhu cầu local reactive recovery.
4. Với DTO trực tiếp, dùng `@RestControllerAdvice` xử lý `WebExchangeBindException` và quy chuẩn HTTP 400.
5. Với `Mono<DTO>`, dùng `onErrorResume(WebExchangeBindException.class, ...)` nếu cần fallback tại chỗ; đừng bắt toàn bộ `Throwable`.
6. Xử lý JSON malformed và input conversion error riêng với Bean Validation; không ép mọi lỗi vào `VALIDATION_ERROR`.
7. Nếu có direct method constraint, hỗ trợ `HandlerMethodValidationException` và giữ 400 cho input/500 cho return violation.
8. Với multipart, phân biệt `FilePart` của WebFlux và `MultipartFile` của MVC; media type của JSON part phải đúng.
9. Không dùng blocking I/O trong custom validator/chuỗi WebFlux event loop; không gọi `block()` hay `subscribe()` thủ công trong controller.
10. Không phản chiếu rejected values/stack traces; log/trace có lọc thông tin nhạy cảm.
11. Ràng buộc request size, codec memory, multipart và timeout để phòng input lớn trước bước validation.
12. Viết `WebTestClient` test happy path, field/nested violation, malformed JSON, local recovery, method validation và nếu cần multipart.
13. Theo dõi behavior khi nâng Spring/Boot: exception type và built-in method validation đã thay đổi từ Framework 6.1.
14. Với functional endpoints, quyết định rõ nơi `Validator` được gọi và cách biến violation thành `ServerResponse`.

**Kết luận:** `WebExchangeBindException` là lỗi **binding/Bean Validation của command object trong WebFlux**, mang `BindingResult` và mặc định gắn với HTTP 400. Xử lý phản ứng đúng nghĩa là hiểu lỗi có thể là `onError` trong `Mono`/`Flux`, phục hồi có chọn lọc bằng `onErrorResume` hoặc chuyển cho `@RestControllerAdvice`. Cần phân biệt nó với lỗi codec `ServerWebInputException` và method validation `HandlerMethodValidationException`, đồng thời giữ error contract an toàn, nhất quán và có kiểm thử bằng `WebTestClient`.

## Tài liệu tham khảo

- [Spring Framework — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): `HttpMessageReader`, validation và reactive arguments.
- [Spring Framework — WebFlux Controller Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html): `WebExchangeBindException` vs `HandlerMethodValidationException`.
- [Spring Framework — WebFlux Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html): `@RequestPart`, `FilePart` và `PartEvent`.
- [Spring Framework — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, WebFlux `ResponseEntityExceptionHandler`.
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): `ServerRequest`, `ServerResponse`, reactive routes.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@AutoConfigureWebTestClient` và `@WebFluxTest`.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorResume`, `onErrorMap`, `doOnError` và quy tắc terminal error.
