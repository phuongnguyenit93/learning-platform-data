# Đưa lỗi đầu vào về phản hồi nhất quán mà không chặn luồng trong Spring WebFlux

## 1. Mục tiêu

Một API reactive cần xử lý dữ liệu sai, thiếu hoặc không hợp lệ theo cách nhất quán để client biết phải sửa gì, trong khi server vẫn giữ đúng vòng đời bất đồng bộ. Khi client gửi JSON sai cấu trúc, query parameter không chuyển đổi được, trường vi phạm Bean Validation hoặc một quy tắc nghiệp vụ không được đáp ứng, controller cần trả status HTTP và error body phù hợp.

Bài học này tập trung vào **Spring WebFlux annotated controllers**, Project Reactor và Spring Framework 6.1+/Spring Boot 3.2+. Các mục tiêu chính:

- Phân biệt **binding**, **type conversion**, **Bean Validation** và **business validation**.
- Nhận diện các exception thường gặp, đặc biệt `WebExchangeBindException` và `HandlerMethodValidationException`.
- Chuẩn hóa lỗi bằng `@RestControllerAdvice` và RFC 9457 `ProblemDetail`.
- Kết hợp xử lý lỗi bằng `Mono/Flux` mà không gọi `block()` hoặc tự `subscribe()`.
- Kiểm thử status, error body và các đường lỗi bằng `WebTestClient`.

**Không chặn luồng** không có nghĩa là bỏ qua validation. Nó có nghĩa là giữ các thao tác I/O bất đồng bộ trong reactive pipeline, không chặn Netty event-loop để chờ kết quả, và không tự tạo một subscription tách khỏi request HTTP.

## 2. Bốn lớp lỗi cần phân biệt

Khi một request đi vào controller, lỗi có thể xuất hiện ở những giai đoạn khác nhau:

| Lớp | Ví dụ | Thường phát sinh khi nào? | Cách xử lý |
| --- | --- | --- | --- |
| Binding / decoding | JSON sai cú pháp, body không đọc được, thiếu giá trị bắt buộc | Đọc request và tạo method argument | HTTP 400 hoặc status tương ứng; mô tả input không hợp lệ |
| Type conversion | `?page=abc` trong khi method yêu cầu `int page` | Chuyển chuỗi HTTP sang kiểu Java | HTTP 400; chỉ rõ tham số/format sai nếu an toàn |
| Bean Validation | Email sai định dạng, tên rỗng, tuổi ngoài giới hạn | Sau khi bind object hoặc khi kiểm tra method parameter | HTTP 400; trả danh sách lỗi field/parameter |
| Business validation | Email đã tồn tại, trạng thái đơn hàng không cho phép thao tác | Trong service hoặc khi truy vấn nghiệp vụ | Status theo contract, ví dụ 409 Conflict |

Bốn lớp này không nên bị gộp thành một thông báo “server error”. Client cần biết request sai định dạng, sai trường hay xung đột với trạng thái hiện tại.

Cũng không nên trả toàn bộ exception message hoặc stack trace cho client. Exception có thể chứa tên class, câu SQL, rejected value hoặc thông tin nội bộ. Error response nên có mã/status, thông điệp ổn định và những field errors đã được chọn lọc.

## 3. Luồng xử lý trong WebFlux

Một request đi qua controller reactive có thể hình dung:

```text
HTTP request
    |
    v
Resolve route + read headers/query/body
    |
    v
Bind method arguments + convert types
    |
    v
Bean Validation / method validation
    |
    +---- invalid ----> Exception / ErrorResponse
    |                         |
    |                         v
    |                 @RestControllerAdvice
    |                         |
    |                         v
    |                 HTTP ProblemDetail
    |
    v
Controller returns Mono / Flux
    |
    v
Reactive service + non-blocking I/O
    |
    +---- business error ---> onError signal
    |                              |
    |                              v
    |                      @ExceptionHandler
    |
    v
Serialize response asynchronously
```

Spring WebFlux giải quyết method arguments và áp dụng validation theo contract của framework. Khi handler trả về `Mono`/`Flux`, framework quản lý subscription và ghi response. Lỗi phát sinh trong quá trình đọc body, binding hoặc validation có thể được chuyển thành HTTP error response; lỗi phát sinh sau đó trong reactive pipeline đi theo tín hiệu `onError`.

**Bean Validation thông thường là thao tác đồng bộ và chủ yếu dùng CPU**, ví dụ kiểm tra chuỗi rỗng, độ dài hoặc regex. Framework gọi validator trong quá trình xử lý request. Điều đó không có nghĩa mọi validator đều phù hợp để làm công việc nặng: không gọi database, HTTP hoặc một API blocking từ `ConstraintValidator` trên event-loop. Những kiểm tra phụ thuộc I/O cần được biểu diễn thành publisher trong service.

## 4. Binding và decoding lỗi trước khi controller chạy

Ví dụ endpoint nhận JSON:

```java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @RequestBody Mono<CreateAccountRequest> body) {
    return body.map(this::toResponse);
}
```

Đây là mã minh họa. Khi client gửi JSON, WebFlux dùng message reader/codec để đọc body và tạo object. Một số lỗi xảy ra trước khi business method nhận được object:

- JSON sai cú pháp hoặc không thể deserialize.
- Giá trị JSON không tương thích kiểu Java, ví dụ chuỗi ở nơi yêu cầu số nguyên.
- Body bắt buộc bị thiếu.
- Content-Type không được hỗ trợ.
- Query/header/cookie thiếu hoặc không chuyển đổi được.

Các lỗi đó không phải lỗi Bean Validation. Ví dụ chuỗi `"age":"many"` không thể chuyển thành `int age` là lỗi decoding/conversion; còn `"age":12` có thể deserialize thành công nhưng vi phạm quy tắc tuổi tối thiểu là 18.

Spring WebFlux có các exception liên quan đến request input như `ServerWebInputException`, các exception theo contract `ErrorResponse` và lỗi codec. Loại exception cụ thể phụ thuộc giai đoạn và nguyên nhân; không nên giả định mọi lỗi parse JSON đều cùng một class. Các exception built-in có thể cung cấp HTTP status và thông tin cho RFC 9457.

## 5. Bean Validation cho DTO và method parameters

### 5.1. Validation trên một request object

Dùng Jakarta Bean Validation annotations trên DTO:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateAccountRequest(
        @NotBlank(message = "name must not be blank")
        @Size(max = 80, message = "name must be at most 80 characters")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email must be valid")
        @Size(max = 254, message = "email must be at most 254 characters")
        String email,

        @Min(value = 18, message = "age must be at least 18")
        @Max(value = 120, message = "age must be at most 120")
        int age
) {}
```

Sau đó dùng `@Valid`:

```java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @Valid @RequestBody Mono<CreateAccountRequest> body) {

    return body.map(this::toResponse);
}
```

Trong WebFlux, validation có thể áp dụng cho `@RequestBody` có reactive wrapper như `Mono<CreateAccountRequest>`. Khi object được đọc và validation không đạt, Spring phát `WebExchangeBindException`; lỗi có thể được xử lý tại controller hoặc tập trung trong advice.

### 5.2. Validation trực tiếp trên tham số method

Có thể đặt constraint ngay trên query parameter hoặc header:

```java
@GetMapping("/accounts/by-age")
public Mono<String> byAge(
        @RequestParam("age")
        @Min(18) @Max(120) int age) {

    return Mono.just("accepted age=" + age);
}
```

Với cơ chế method validation built-in từ **Spring Framework 6.1**, constraint trực tiếp trên method parameter làm Spring validate toàn bộ method. Khi validation đầu vào thất bại, exception là `HandlerMethodValidationException`.

Điểm dễ nhầm: `@Valid` **không phải** một constraint annotation. `@Valid` yêu cầu validate các field lồng bên trong object; tự nó không kích hoạt method validation. Các constraint như `@Min`, `@NotBlank` đặt trực tiếp trên tham số mới làm method validation được áp dụng.

Nếu controller có `@Validated` ở cấp class để kích hoạt method validation qua AOP theo cách cũ, hành vi có thể khác. Với built-in method validation của Spring Framework 6.1+, hãy bỏ class-level `@Validated` khỏi controller theo hướng dẫn Spring để framework thực hiện method validation tích hợp.

### 5.3. Hai exception validation quan trọng

| Exception | Khi nào thường gặp | Phạm vi lỗi |
| --- | --- | --- |
| `WebExchangeBindException` | Validate riêng một command object như `@Valid @RequestBody` hoặc `@ModelAttribute` | Một object, có `BindingResult` với field/global errors |
| `HandlerMethodValidationException` | Validate method do constraint đặt trực tiếp trên tham số hoặc return value | Tập kết quả validation được nhóm theo method parameter |

Một ứng dụng nên xử lý **cả hai**, vì exception phụ thuộc signature của controller. `HandlerMethodValidationException` cũng có thể liên quan đến validation return value; khi đó status phản ánh lỗi phía server (thường 500), không được ép mọi trường hợp thành 400. Hãy giữ status do exception cung cấp khi xử lý tổng quát.

Nếu có `Errors`/`BindingResult` ngay sau tham số object, Spring có thể đưa lỗi cho controller tự xử lý. Tuy nhiên, với `@RequestBody Mono<DTO>`, body được đọc bất đồng bộ; không thể tùy tiện đặt một `BindingResult` ngay sau reactive wrapper như cách làm với object được resolve trước. Trong trường hợp reactive body, global advice hoặc error operators thường phù hợp hơn.

## 6. Chuẩn hóa lỗi bằng RFC 9457 Problem Details

RFC 9457 định nghĩa định dạng chung cho HTTP API problem details. Spring Framework cung cấp `ProblemDetail` và `ErrorResponse` để biểu diễn lỗi có status, headers và body.

Một body lỗi thường có các trường:

| Field | Ý nghĩa |
| --- | --- |
| `type` | URI định danh loại vấn đề; có thể là `about:blank` nếu không có type riêng |
| `title` | Tên ngắn, ổn định của loại lỗi |
| `status` | HTTP status code |
| `detail` | Mô tả dễ hiểu về lỗi cụ thể |
| `instance` | URI/path của lần xảy ra lỗi |
| Extension properties | Trường mở rộng, ví dụ danh sách `errors` theo field |

Ví dụ response:

```json
{
  "type": "about:blank",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "instance": "/api/accounts",
  "errors": [
    {
      "field": "email",
      "code": "Email",
      "message": "email must be valid"
    },
    {
      "field": "age",
      "code": "Min",
      "message": "age must be at least 18"
    }
  ]
}
```

Spring có thể render `ProblemDetail` với media type `application/problem+json`. Các property mở rộng được thêm bằng `setProperty(...)`. Dùng một schema ổn định giúp frontend xử lý mọi lỗi theo cùng một contract, dù nguồn là binding, validation hay business rule.

### 6.1. Chọn status code theo loại lỗi

| Tình huống | Status thường dùng | Lý do |
| --- | --- | --- |
| Thiếu field bắt buộc, JSON sai cú pháp, type conversion thất bại | 400 Bad Request | Request không thỏa cú pháp/contract đầu vào |
| Chưa xác thực | 401 Unauthorized | Cần authentication hợp lệ |
| Không đủ quyền | 403 Forbidden | Đã nhận diện nhưng không được phép |
| Không có resource | 404 Not Found | Resource không tồn tại/không được công khai |
| Trùng dữ liệu hoặc xung đột trạng thái | 409 Conflict | Request hợp lệ về cú pháp nhưng xung đột trạng thái hiện tại |
| Media type không hỗ trợ | 415 Unsupported Media Type | Content-Type không được endpoint hỗ trợ |
| Quá nhiều request | 429 Too Many Requests | Rate limit |
| Lỗi không mong đợi | 500 Internal Server Error | Lỗi phía server |

Có thể chọn 422 Unprocessable Content cho một số API nếu contract quy định rõ, nhưng không nên trộn 400 và 422 tùy tiện. Điều quan trọng là client có thể dự đoán status và schema lỗi qua mọi endpoint.

## 7. Tập trung xử lý lỗi với @RestControllerAdvice

### 7.1. Lấy lỗi field từ WebExchangeBindException

Ví dụ advice sau chuẩn hóa lỗi validation của DTO. Nó không trả rejected value để tránh làm lộ dữ liệu nhạy cảm.

Tệp `src/main/java/demo/ApiExceptionHandler.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ProblemDetail> handleBindingValidation(
            WebExchangeBindException exception) {

        List<ApiViolation> violations = new ArrayList<>();

        for (FieldError error : exception.getFieldErrors()) {
            violations.add(new ApiViolation(
                    error.getField(),
                    error.getCode() == null ? "invalid" : error.getCode(),
                    error.getDefaultMessage() == null
                            ? "Invalid value"
                            : error.getDefaultMessage()));
        }

        for (ObjectError error : exception.getGlobalErrors()) {
            violations.add(new ApiViolation(
                    "$",
                    error.getCode() == null ? "invalid" : error.getCode(),
                    error.getDefaultMessage() == null
                            ? "Invalid object"
                            : error.getDefaultMessage()));
        }

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid.");

        problem.setTitle("Request validation failed");
        problem.setProperty("errors", violations);

        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> handleMethodValidation(
            HandlerMethodValidationException exception) {

        HttpStatusCode status = exception.getStatusCode();
        boolean clientError = status.is4xxClientError();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                clientError
                        ? "One or more request parameters are invalid."
                        : "A server-side validation constraint failed.");

        problem.setTitle(clientError
                ? "Request validation failed"
                : "Response validation failed");

        return ResponseEntity.status(status).body(problem);
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ProblemDetail> handleInvalidInput(
            ServerWebInputException exception) {

        HttpStatusCode status = exception.getStatusCode();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                "The request contains missing or malformed input.");

        problem.setTitle("Invalid request input");

        return ResponseEntity.status(status).body(problem);
    }

    public record ApiViolation(
            String field,
            String code,
            String message) {
    }
}
```

Đây là class Java hoàn chỉnh cho ba nhóm lỗi thường gặp; ứng dụng thực tế có thể bổ sung handler cho exception nghiệp vụ. Import được nhóm theo package Spring/JDK; nếu IDE tự sắp xếp import, giữ nguyên các kiểu cần thiết.

**Vì sao handler method validation không ép status thành 400?** `HandlerMethodValidationException` có thể đại diện lỗi tham số đầu vào hoặc lỗi return value. Giữ `exception.getStatusCode()` giúp lỗi request tiếp tục là 4xx, còn lỗi contract do server tạo response không hợp lệ vẫn giữ status phía server.

### 7.2. Xử lý lỗi nghiệp vụ

Một lỗi nghiệp vụ nên có exception riêng để advice map sang status phù hợp:

```java
package demo;

public class DuplicateEmailException extends RuntimeException {
    public DuplicateEmailException() {
        super("An account with this email already exists.");
    }
}
```

Bổ sung vào `ApiExceptionHandler`:

```java
@ExceptionHandler(DuplicateEmailException.class)
public ResponseEntity<ProblemDetail> handleDuplicateEmail(
        DuplicateEmailException exception) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "An account with this email already exists.");

    problem.setTitle("Account conflict");

    return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
}
```

Đoạn handler này cần đặt **bên trong class ApiExceptionHandler** ở ví dụ trên. Không đưa exception message tùy ý từ database vào response. Thông báo nên ổn định, không tiết lộ tên constraint, SQL hoặc dữ liệu người dùng khác.

### 7.3. Khi nào dùng ResponseEntityExceptionHandler?

Spring cung cấp `ResponseEntityExceptionHandler` làm base class cho `@ControllerAdvice` để xử lý các exception WebFlux built-in và error response theo RFC 9457. Đây là lựa chọn phù hợp nếu muốn tùy biến rộng nhiều loại lỗi framework như method not allowed, unsupported media type, missing request value và validation.

Nếu chỉ cần chuẩn hóa một số exception nghiệp vụ/validation, các method `@ExceptionHandler` cụ thể như ví dụ là đủ. Với Spring Boot, property `spring.webflux.problemdetails.enabled=true` có thể bật cấu hình Problem Details cho exception built-in. Khi thay thế một handler built-in do Boot tạo, cần chú ý thứ tự `@ControllerAdvice` theo hướng dẫn Boot/Spring để handler tùy chỉnh được chọn.

Không viết một handler tổng quát `Exception.class` rồi biến mọi lỗi thành 400. Lỗi lập trình, database unavailable, lỗi mạng và lỗi cấu hình cần status 5xx; chỉ các lỗi đầu vào đã nhận diện mới nên trả 4xx.

## 8. Kết hợp reactive error operators mà không chặn luồng

### 8.1. Lỗi trong pipeline là onError signal

Khi một exception phát sinh bên trong operator như `map` hoặc `flatMap`, Reactor chuyển nó thành tín hiệu `onError`. Có thể chuyển loại lỗi bằng `onErrorMap`:

```java
return accountRepository.save(account)
        .onErrorMap(
                DuplicateKeyException.class,
                error -> new DuplicateEmailException());
```

Đây là **đoạn service minh họa**. Repository phải trả reactive publisher và DuplicateKeyException phải là loại exception thực tế của driver. Service đổi exception hạ tầng sang exception nghiệp vụ; advice chịu trách nhiệm ánh xạ exception nghiệp vụ thành HTTP 409.

### 8.2. Dùng onErrorResume cho fallback có ý nghĩa

```java
return pricingService.findPrice(sku)
        .onErrorResume(PriceUnavailableException.class,
                error -> Mono.just(Price.unavailable()));
```

Chỉ dùng fallback khi nghiệp vụ cho phép trả một kết quả thay thế. Không biến lỗi database thành danh sách rỗng hoặc lỗi validation thành HTTP 200 chỉ để pipeline “không báo lỗi”.

### 8.3. Không dùng try/catch quanh publisher để bắt lỗi chạy sau

Ví dụ không đủ:

```java
try {
    return service.create(request);
} catch (Exception exception) {
    return Mono.error(exception);
}
```

Try/catch này chỉ bắt exception phát sinh **ngay khi gọi method và dựng publisher**. Lỗi có thể xảy ra sau đó, lúc publisher được subscribe và thực thi. Hãy dùng reactive operators:

```java
return service.create(request)
        .onErrorMap(DuplicateKeyException.class,
                error -> new DuplicateEmailException());
```

Có thể dùng `Mono.defer(...)` nếu cần trì hoãn cả phần gọi method để exception phát sinh khi subscribe được chuyển thành onError. Tuy nhiên, với service trả publisher đúng contract, không cần bọc `defer` một cách máy móc.

### 8.4. Kết hợp business validation bất đồng bộ

Bean Validation thích hợp với các điều kiện cục bộ, nhanh và xác định như not blank, range, format. Nếu cần kiểm tra database hoặc dịch vụ ngoài, trả publisher:

```java
public Mono<AccountResponse> create(CreateAccountRequest request) {
    return accountRepository.existsByEmail(request.email())
            .flatMap(exists -> {
                if (exists) {
                    return Mono.error(new DuplicateEmailException());
                }

                return accountRepository.save(toEntity(request))
                        .map(this::toResponse);
            });
}
```

Đây là **mã service minh họa** với repository reactive. Việc kiểm tra tồn tại rồi insert có thể gặp race condition khi hai request đồng thời cùng email. Database vẫn cần unique constraint và service cần map lỗi unique-key thành `DuplicateEmailException`. Kiểm tra trước không thay thế tính toàn vẹn dữ liệu.

Không viết:

```java
boolean exists = accountRepository.existsByEmail(email).block();
```

Đây là lỗi thiết kế trong WebFlux vì nó chặn thread đang xử lý reactive flow. Cũng không tự gọi `subscribe()` bên trong service để “chạy trước” kiểm tra rồi trả response; việc đó tách tác vụ khỏi request và làm mất liên kết cancellation/error.

## 9. Vì sao không được block khi xử lý lỗi?

### 9.1. Netty event-loop cần được giải phóng

WebFlux thường dùng event-loop để xử lý nhiều connection. Nếu controller hoặc exception handler gọi `block()`, `Future.get()`, `Thread.sleep()` hay một SDK blocking, thread có thể phải chờ trong khi các request khác cũng cần nó.

Một lỗi đầu vào vốn có thể trả response nhanh sẽ trở thành nguyên nhân làm tăng latency của nhiều request khác. Exception handler cũng phải giữ non-blocking; không truy vấn database đồng bộ để dựng nội dung lỗi.

### 9.2. Trả publisher thay vì tự subscribe

Đúng:

```java
@PostMapping("/accounts")
public Mono<ResponseEntity<AccountResponse>> create(
        @Valid @RequestBody Mono<CreateAccountRequest> body) {

    return body.flatMap(accountService::create)
            .map(saved -> ResponseEntity
                    .status(HttpStatus.CREATED)
                    .body(saved));
}
```

Spring WebFlux subscribe và quản lý vòng đời của publisher được return. Nếu lỗi xảy ra trong body decode, validation hoặc service, framework/advice xử lý theo contract HTTP.

Sai:

```java
@PostMapping("/accounts")
public Mono<String> create(
        @RequestBody Mono<CreateAccountRequest> body) {

    body.subscribe(accountService::create);
    return Mono.just("accepted");
}
```

Đoạn trên sai cả kiểu hàm lẫn lifecycle: `subscribe` lồng nhau có thể tạo subscription tách rời, không chờ công việc hoàn tất, không đưa lỗi vào response và không liên kết cancellation với HTTP request. Luôn compose publisher và return nó.

### 9.3. Nếu buộc phải gọi thư viện blocking

Ưu tiên reactive driver/client. Nếu phải dùng thư viện blocking cũ, cô lập đúng đoạn:

```java
return Mono.fromCallable(() -> legacyClient.lookup(key))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là bridge minh họa. Nó chuyển tác vụ blocking sang scheduler phù hợp; nó **không biến thư viện thành non-blocking**. Giữ timeout, concurrency limit và giới hạn connection riêng. Nếu công việc có thể bị cancel, kiểm tra driver có hỗ trợ cancel/interrupt thật sự hay không.

## 10. Ví dụ Spring Boot WebFlux hoàn chỉnh

Ví dụ này xây dựng endpoint tạo account, áp dụng validation cho JSON body, validate query parameter, và trả error body thống nhất cho các lỗi được chọn.

### 10.1. Dependency

Ví dụ dùng Java 17+, Spring Boot 3.2+ (Spring Framework 6.1+) và Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Giả định dự án đã cấu hình Spring Boot Gradle plugin và dependency management. Để BOM quản lý version của Spring Framework, Reactor, Hibernate Validator và test libraries.

### 10.2. DTO và response

Tệp `src/main/java/demo/CreateAccountRequest.java`:

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateAccountRequest(
        @NotBlank(message = "name must not be blank")
        @Size(max = 80, message = "name must be at most 80 characters")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email must be valid")
        @Size(max = 254, message = "email must be at most 254 characters")
        String email,

        @Min(value = 18, message = "age must be at least 18")
        @Max(value = 120, message = "age must be at most 120")
        int age
) {}
```

Tệp `src/main/java/demo/AccountResponse.java`:

```java
package demo;

public record AccountResponse(
        String id,
        String name,
        String email,
        int age
) {}
```

### 10.3. Controller

Tệp `src/main/java/demo/AccountController.java`:

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    @PostMapping
    public Mono<ResponseEntity<AccountResponse>> create(
            @Valid @RequestBody Mono<CreateAccountRequest> body) {

        return body
                .map(request -> new AccountResponse(
                        "acct-001",
                        request.name(),
                        request.email(),
                        request.age()))
                .map(response -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(response));
    }

    @GetMapping("/by-age")
    public Mono<String> byAge(
            @RequestParam("age")
            @Min(18) @Max(120) int age) {

        return Mono.just("accepted age=" + age);
    }
}
```

Controller không gọi `block()` hoặc `subscribe()`. `@Valid` áp dụng Bean Validation cho body; `@Min/@Max` trên tham số age kích hoạt built-in method validation của Spring Framework 6.1+. Không đặt class-level `@Validated` lên controller trong ví dụ này.

### 10.4. Advice xử lý lỗi

Tệp `src/main/java/demo/ApiExceptionHandler.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ProblemDetail> handleBodyValidation(
            WebExchangeBindException exception) {

        List<ApiViolation> errors = new ArrayList<>();

        for (FieldError error : exception.getFieldErrors()) {
            errors.add(new ApiViolation(
                    error.getField(),
                    error.getCode() == null ? "invalid" : error.getCode(),
                    error.getDefaultMessage() == null
                            ? "Invalid value"
                            : error.getDefaultMessage()));
        }

        for (ObjectError error : exception.getGlobalErrors()) {
            errors.add(new ApiViolation(
                    "$",
                    error.getCode() == null ? "invalid" : error.getCode(),
                    error.getDefaultMessage() == null
                            ? "Invalid object"
                            : error.getDefaultMessage()));
        }

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid.");

        problem.setTitle("Request validation failed");
        problem.setProperty("errors", errors);

        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> handleMethodValidation(
            HandlerMethodValidationException exception) {

        HttpStatusCode status = exception.getStatusCode();
        boolean clientError = status.is4xxClientError();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                clientError
                        ? "One or more request parameters are invalid."
                        : "A server-side validation constraint failed.");

        problem.setTitle(clientError
                ? "Request validation failed"
                : "Response validation failed");

        return ResponseEntity.status(status).body(problem);
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ProblemDetail> handleInvalidInput(
            ServerWebInputException exception) {

        HttpStatusCode status = exception.getStatusCode();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                "The request contains missing or malformed input.");

        problem.setTitle("Invalid request input");

        return ResponseEntity.status(status).body(problem);
    }

    public record ApiViolation(
            String field,
            String code,
            String message) {
    }
}
```

Các handler cụ thể tránh biến mọi exception thành lỗi đầu vào. Những exception WebFlux khác có thể được xử lý bởi cơ chế built-in hoặc một class advice kế thừa `ResponseEntityExceptionHandler` nếu API cần tùy biến toàn bộ exception framework.

### 10.5. Gọi endpoint và xem kết quả

Khởi động ứng dụng (sau khi có class Spring Boot main và package scan phù hợp):

```bash
./gradlew bootRun
```

Gửi request hợp lệ:

```bash
curl -i -X POST http://localhost:8080/api/accounts   -H "Content-Type: application/json"   -d '{"name":"An","email":"an@example.com","age":25}'
```

Response dự kiến:

```json
{
  "id": "acct-001",
  "name": "An",
  "email": "an@example.com",
  "age": 25
}
```

Status là `201 Created`.

Gửi body không hợp lệ:

```bash
curl -i -X POST http://localhost:8080/api/accounts   -H "Content-Type: application/json"   -d '{"name":"","email":"not-an-email","age":15}'
```

Response là HTTP 400 với body Problem Details; trường `errors` chứa các violation như name, email và age. Thứ tự field errors có thể phụ thuộc validator, nên client/test không nên phụ thuộc thứ tự mảng.

Gửi query parameter sai giới hạn:

```bash
curl -i "http://localhost:8080/api/accounts/by-age?age=15"
```

Method validation phát `HandlerMethodValidationException`; advice trả HTTP 400 và title thống nhất. Nếu một constraint trên return value thất bại, Spring có thể cung cấp status 500; handler giữ status đó để không mô tả lỗi server thành lỗi client.

Gửi query parameter không chuyển đổi được:

```bash
curl -i "http://localhost:8080/api/accounts/by-age?age=abc"
```

Đây là lỗi type conversion trước khi method validation chạy. Nó không giống trường hợp age=15 chuyển đổi thành công rồi vi phạm `@Min(18)`.

## 11. Kiểm thử lỗi bằng WebTestClient

Kiểm thử HTTP contract thay vì chỉ gọi validator trực tiếp. `WebTestClient` có thể test controller mà không cần mở server thật.

Tệp `src/test/java/demo/AccountControllerTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(AccountController.class)
@Import(ApiExceptionHandler.class)
class AccountControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void validBodyReturnsCreated() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "An",
                          "email": "an@example.com",
                          "age": 25
                        }
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo("acct-001")
                .jsonPath("$.name").isEqualTo("An");
    }

    @Test
    void invalidBodyReturnsProblemDetails() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "",
                          "email": "not-an-email",
                          "age": 15
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title")
                    .isEqualTo("Request validation failed")
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.errors").isArray();
    }

    @Test
    void methodParameterValidationReturnsProblemDetails() {
        client.get()
                .uri("/api/accounts/by-age?age=15")
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title")
                    .isEqualTo("Request validation failed")
                .jsonPath("$.status").isEqualTo(400);
    }

    @Test
    void invalidIntegerConversionIsBadRequest() {
        client.get()
                .uri("/api/accounts/by-age?age=abc")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Chạy test:

```bash
./gradlew test
```

Dependency `spring-boot-starter-test` cung cấp JUnit Jupiter và WebFlux test support; `spring-boot-starter-validation` đưa Bean Validation provider vào classpath. Dùng dependency management của Spring Boot để chọn phiên bản tương thích.

Test tập trung vào các contract quan trọng: request hợp lệ trả 201; DTO không hợp lệ trả 400 với error body; method constraint trả 400; conversion lỗi trả 400. Nếu dự án có Spring Security, thêm cấu hình test phù hợp hoặc mock principal để kiểm tra error handling trong đúng security chain.

## 12. Bản địa hóa thông báo và giữ error schema ổn định

Thông điệp validation có thể được viết trực tiếp trong annotation, nhưng API đa ngôn ngữ nên dùng message bundle:

```java
@NotBlank(message = "{account.name.required}")
@Size(max = 80, message = "{account.name.max}")
String name
```

Ví dụ trong `messages.properties`:

```properties
account.name.required=Name is required.
account.name.max=Name must be at most 80 characters.
account.email.invalid=Email address is invalid.
```

Có thể tạo các file theo locale, ví dụ `messages_vi.properties`. Spring sử dụng `MessageSource` để resolve message code. Với exception thực thi `ErrorResponse`, Spring cũng hỗ trợ message code cho các trường của ProblemDetail.

Khi trả lỗi, giữ cấu trúc ổn định:

- `field`: tên field/parameter theo API contract.
- `code`: mã lỗi ổn định để client xử lý logic.
- `message`: thông điệp có thể bản địa hóa để người dùng đọc.

Không bắt client phân tích câu văn tự do để quyết định hành vi. Cũng không đổi code lỗi tùy ý giữa các lần deploy nếu frontend phụ thuộc vào nó.

## 13. Validation ở controller, service và database

Mỗi tầng có trách nhiệm riêng:

| Tầng | Kiểm tra phù hợp | Ví dụ |
| --- | --- | --- |
| HTTP binding | Dữ liệu có đọc và chuyển đổi được không? | JSON hợp lệ, query int, header bắt buộc |
| Bean Validation | Cấu trúc/giá trị field có thỏa constraint cục bộ không? | NotBlank, Email, Size, Min |
| Service/domain | Quy tắc phụ thuộc nghiệp vụ hoặc nhiều đối tượng | Account chưa bị khóa, trạng thái cho phép đổi |
| Database | Ràng buộc cuối cùng để bảo vệ dữ liệu khi concurrent | Unique key, foreign key, check constraint |

Không nên đưa mọi logic vào Bean Validation. `ConstraintValidator` chạy đồng bộ; việc gọi remote service/database từ validator có thể chặn thread, gây khó quản lý timeout và retry. Nếu cần kiểm tra bất đồng bộ, hãy để service trả `Mono<Boolean>`/publisher rồi compose bằng `flatMap`.

Ngược lại, không chỉ dựa vào controller để bảo vệ invariant. Hai request đồng thời có thể cùng vượt qua một bước “kiểm tra tồn tại” rồi cùng insert. Database constraint vẫn cần thiết; service chuyển lỗi constraint thành exception nghiệp vụ có status 409.

## 14. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Xem mọi lỗi request là 500 | Client không biết lỗi nằm ở đâu | Phân loại binding, conversion, validation, business và server errors |
| Chỉ handle WebExchangeBindException | Bỏ sót method validation | Handle thêm HandlerMethodValidationException |
| Ép mọi HandlerMethodValidationException thành 400 | Return-value validation phía server bị phân loại sai | Giữ status từ exception |
| Nghĩ @Valid luôn kích hoạt method validation | Nhầm giữa nested object validation và method constraints | Phân biệt @Valid với constraint annotation như @Min/@NotBlank |
| Dùng @Validated cấp class mà quên Spring 6.1 built-in validation | Có thể dùng AOP method validation theo cơ chế khác | Với built-in method validation, bỏ class-level @Validated trên controller |
| Trả rejected value hoặc toàn bộ exception message | Có thể lộ email, token, SQL hoặc dữ liệu nội bộ | Chỉ trả field, code và message đã chọn lọc |
| Dùng một catch-all rồi trả 400 | Che giấu bug và lỗi hạ tầng thành lỗi client | Map từng exception cụ thể, giữ 5xx cho lỗi server |
| Gọi block trong controller/advice | Chặn event-loop và tăng latency | Compose Mono/Flux; giữ error response trong reactive chain |
| Gọi subscribe trong service | Tách công việc khỏi HTTP lifecycle, lỗi và cancel | Return publisher cho caller |
| Dùng try/catch để bắt lỗi phát sinh lúc subscribe | Bỏ sót lỗi bất đồng bộ | Dùng onErrorMap/onErrorResume/doOnError |
| Gọi database từ ConstraintValidator | Validator đồng bộ có thể chặn event-loop | Kiểm tra nghiệp vụ trong reactive service |
| Biến lỗi thành Mono.empty() vô điều kiện | Client có thể nhận 200/204 như thể thành công | Chỉ fallback khi business contract cho phép |
| Trả stack trace trong ProblemDetail | Rò thông tin nội bộ | Ghi log nội bộ, trả detail an toàn |
| Bỏ qua race condition sau exists check | Dữ liệu vẫn có thể trùng khi concurrent | Dùng unique constraint và map lỗi DB |
| Bắt Throwable để xử lý lỗi request | Có thể nuốt lỗi nghiêm trọng và nhầm cancellation | Xử lý exception cụ thể; cancel không phải onError |

## 15. Quy trình thiết kế error handling

Khi thêm một endpoint mới, thực hiện theo trình tự:

1. **Định nghĩa input contract:** field nào required, kiểu nào, giới hạn nào, body có thể rỗng không?
2. **Chọn binding:** DTO cho body, annotation cho query/header/path, reactive wrapper cho body nếu cần stream.
3. **Thêm Bean Validation cục bộ:** NotBlank, Size, Email, Min/Max và constraint tùy nghiệp vụ nhưng không thực hiện I/O blocking.
4. **Xác định loại exception:** binding object, method validation, conversion, decode, business conflict hay infrastructure.
5. **Chọn status:** 400 cho input không hợp lệ, 409 cho conflict, 415 cho media type, 5xx cho lỗi server.
6. **Chuẩn hóa body:** ProblemDetail theo RFC 9457, field errors có code ổn định, không có rejected secret.
7. **Giữ reactive lifecycle:** return Mono/Flux, compose bằng map/flatMap/onErrorMap/onErrorResume, không block/subscribe thủ công.
8. **Xử lý async business checks:** dùng reactive repository/client và timeout; database vẫn giữ constraint để chống race.
9. **Kiểm thử:** valid, missing, malformed, type mismatch, bean validation, method validation, business conflict và unexpected error.
10. **Quan sát production:** log correlation ID, status, error code và latency; không log payload bí mật hoặc stack trace trong response.

## 16. Tài liệu tham khảo chính thức

- [Spring Framework – WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): hai cấp validation, WebExchangeBindException, HandlerMethodValidationException và visitor API.
- [Spring Framework – WebFlux Error Responses](https://docs.spring.io/spring/reference/web/webflux/ann-rest-exceptions.html): ProblemDetail, ErrorResponse, ResponseEntityExceptionHandler, RFC 9457 và message codes.
- [Spring Framework – WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): validation cho request body reactive và cách xử lý lỗi.
- [Spring Framework – WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): đăng ký global Validator và cấu hình validation.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng chuẩn cho HTTP problem responses.
- [Project Reactor Reference – Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): onError, onErrorMap, onErrorResume và các operator xử lý lỗi.

## 17. Ghi nhớ

Một API WebFlux tốt phân loại lỗi trước khi chuẩn hóa response: **binding/conversion** cho dữ liệu không đọc hoặc không chuyển đổi được; **Bean Validation** cho object vi phạm constraint; **method validation** cho constraint trên tham số/return value; **business validation** cho quy tắc nghiệp vụ; và **server errors** cho lỗi ngoài dự kiến.

Với Spring Framework 6.1+, hãy nhớ xử lý cả `WebExchangeBindException` và `HandlerMethodValidationException`. Dùng `@RestControllerAdvice` và `ProblemDetail` để giữ status/schema nhất quán, đồng thời không làm lộ dữ liệu nội bộ. Các kiểm tra cục bộ có thể chạy đồng bộ trong bước validation; mọi I/O phụ thuộc nghiệp vụ nên được compose bằng `Mono/Flux`. Trả publisher cho WebFlux quản lý, không gọi `block()` hay `subscribe()` trong controller/service để giữ request lifecycle và error propagation đúng.
