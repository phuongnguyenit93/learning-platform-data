# `ProblemDetail`, `ErrorResponse` và chuẩn phản hồi lỗi trong Spring WebFlux

## 1. Vì sao API cần một chuẩn phản hồi lỗi?

Một API không chỉ trả dữ liệu khi thành công. Nó còn phải giải thích nhất quán những tình huống như:

- Client gửi JSON sai cú pháp hoặc thiếu trường bắt buộc.
- Resource không tồn tại hoặc người dùng không có quyền truy cập.
- HTTP method hoặc `Content-Type` không được endpoint hỗ trợ.
- Một quy tắc nghiệp vụ không cho phép thao tác hiện tại.
- Server gặp lỗi ngoài dự kiến.

Nếu mỗi controller tự tạo một JSON khác nhau, client phải viết nhiều nhánh phân tích lỗi. Một endpoint có thể trả `{"message":"not found"}`, endpoint khác trả `{"error":"ORDER_MISSING"}`, còn endpoint thứ ba trả HTML hoặc body rỗng. Điều này làm client khó xử lý tự động, khó quan sát và khó thay đổi API.

Spring Framework hỗ trợ chuẩn **Problem Details for HTTP APIs**, hiện được đặc tả trong **RFC 9457** (kế nhiệm RFC 7807). Spring cung cấp ba abstraction quan trọng:

- **`ProblemDetail`**: object biểu diễn nội dung problem theo RFC 9457.
- **`ErrorResponse`**: hợp đồng mô tả toàn bộ HTTP error response, gồm status, headers và body `ProblemDetail`.
- **`ErrorResponseException`**: exception cơ sở triển khai `ErrorResponse`, giúp exception nghiệp vụ mang theo cách ánh xạ thành HTTP response.

Trong WebFlux, các exception HTTP tích hợp của Spring cũng triển khai `ErrorResponse`. Vì vậy ứng dụng có thể chuẩn hóa cả lỗi do framework tạo ra lẫn lỗi nghiệp vụ do chính ứng dụng phát sinh.

## 2. RFC 9457: cấu trúc của Problem Details

Một response lỗi theo RFC 9457 thường có media type:

```http
Content-Type: application/problem+json
```

Ví dụ:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 42",
  "instance": "/orders/42",
  "code": "ORDER_NOT_FOUND",
  "orderId": 42
}
```

Năm thành viên chuẩn:

| Thành viên | Ý nghĩa | Quy tắc sử dụng |
|---|---|---|
| `type` | URI xác định loại problem | Nên ổn định, có thể trỏ tới tài liệu mô tả lỗi; mặc định có thể là `about:blank` |
| `title` | Tóm tắt ngắn gọn loại problem | Không nên thay đổi theo từng lần xảy ra lỗi; có thể được bản địa hóa |
| `status` | HTTP status code của problem | Phải khớp status code thực tế gửi trong HTTP response |
| `detail` | Giải thích cụ thể cho lần xảy ra lỗi | Viết cho người dùng/client; không tiết lộ stack trace hay dữ liệu nội bộ |
| `instance` | URI reference nhận diện lần xảy ra lỗi cụ thể | Có thể là đường dẫn request, ví dụ `/orders/42` |

Các trường chuẩn có thể vắng mặt nếu không có giá trị phù hợp. `type` là định danh loại lỗi; `instance` là định danh lần xảy ra lỗi. Không dùng chúng thay thế nhau.

### 2.1. `type` và `title` nên ổn định

Ví dụ hai lần request khác nhau đều gặp lỗi cùng loại:

```json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 42",
  "instance": "/orders/42"
}
```

và:

```json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 99",
  "instance": "/orders/99"
}
```

`type` và `title` mô tả cùng một loại problem; `detail` và `instance` thay đổi theo request cụ thể. Client có thể dựa vào `type` hoặc extension `code` để chọn hành vi, thay vì phân tích chuỗi `detail`.

### 2.2. Extension members

RFC 9457 cho phép thêm các trường riêng của API. Ví dụ:

```json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid",
  "instance": "/orders",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "quantity",
      "code": "must-be-positive",
      "message": "Quantity must be greater than zero"
    }
  ],
  "traceId": "req-8f21"
}
```

Các extension hữu ích có thể là `code`, `errors`, `traceId`, `retryable` hoặc `orderId`. Chọn tên rõ ràng, nhất quán và tránh trùng với năm thành viên chuẩn.

Không trả toàn bộ object exception, stack trace, SQL, đường dẫn filesystem, access token hoặc dữ liệu cá nhân trong extension. Các chi tiết chẩn đoán nội bộ nên được ghi ở log/trace phía server và liên kết bằng một mã tương quan an toàn.

## 3. `ProblemDetail` trong Spring Framework

`org.springframework.http.ProblemDetail` là class mô hình hóa problem. Các factory method thường dùng:

```java
ProblemDetail notFound = ProblemDetail.forStatus(
        HttpStatus.NOT_FOUND
);

ProblemDetail invalid = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "The request contains an invalid quantity"
);
```

Các thuộc tính chính:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "The supplied quantity must be positive"
);

problem.setType(URI.create(
        "https://api.example.com/problems/invalid-quantity"
));
problem.setTitle("Invalid quantity");
problem.setInstance(URI.create("/orders"));
problem.setProperty("code", "INVALID_QUANTITY");
problem.setProperty("field", "quantity");
```

Spring cung cấp getter/setter tương ứng cho `type`, `title`, `status`, `detail`, `instance` và `properties`.

### 3.1. `status` trong body và status HTTP

Khi tạo `ProblemDetail`, hãy bảo đảm status trong body khớp status HTTP thực tế. Ví dụ body ghi `404` nhưng response line lại là `200 OK` sẽ khiến client không biết nên tin giá trị nào.

Khi Spring render trực tiếp một `ProblemDetail` từ `@ExceptionHandler` hoặc `@RequestMapping`, thuộc tính `status` được dùng để xác định HTTP status. Nếu `instance` chưa được đặt, Spring có thể khởi tạo nó từ request path.

Nếu tự tạo `ResponseEntity<ProblemDetail>`, hãy đặt status của `ResponseEntity` tương ứng với `ProblemDetail.status`.

### 3.2. Extension properties và Jackson

Có thể thêm extension bằng:

```java
problem.setProperty("code", "ORDER_NOT_FOUND");
problem.setProperty("orderId", 42L);
```

Khi Jackson có trên classpath, Spring đăng ký `ProblemDetailJacksonMixin`; map `properties` được trải thành các thuộc tính cấp cao nhất trong JSON. Vì vậy client thường thấy:

```json
{
  "status": 404,
  "code": "ORDER_NOT_FOUND",
  "orderId": 42
}
```

thay vì một object con `"properties"`. Nếu dùng JSON codec khác hoặc không có Jackson, cách serialize có thể khác. Hãy kiểm tra representation thực tế mà API công bố.

## 4. `ErrorResponse`: hợp đồng cho toàn bộ HTTP error

`ProblemDetail` mô tả **body**. `ErrorResponse` mô tả cách tạo **toàn bộ response**:

```text
ErrorResponse
   |
   +-- getStatusCode() : HttpStatusCode
   |
   +-- getHeaders()    : HttpHeaders
   |
   +-- getBody()       : ProblemDetail
```

Interface `org.springframework.web.ErrorResponse` còn cung cấp các message code và argument để giải quyết `type`, `title`, `detail` thông qua Spring `MessageSource`.

Điều này hữu ích vì exception có thể tự mang thông tin ánh xạ HTTP thay vì buộc mỗi controller phải viết một `try/catch` và tự tạo response.

Ví dụ tạo một `ErrorResponse`:

```java
ErrorResponse error = ErrorResponse.create(
        new IllegalStateException("Order is already closed"),
        HttpStatus.CONFLICT,
        "The order cannot be changed after closing"
);

HttpStatusCode status = error.getStatusCode();
HttpHeaders headers = error.getHeaders();
ProblemDetail body = error.getBody();
```

Đây là đoạn API minh họa dùng trong Spring Framework 6.x. `ErrorResponse.create(...)` tạo một implementation có status, headers và `ProblemDetail` tương ứng. Nếu cần kiểm soát nhiều hơn, có thể dùng `ErrorResponse.builder(...)` rồi `build()`.

Một `ErrorResponse` tốt cần bảo đảm:

- `getStatusCode()` phản ánh đúng lỗi HTTP.
- `getBody().getStatus()` khớp status code.
- Headers cần thiết được giữ lại, ví dụ `Allow` cho lỗi method không hỗ trợ hoặc header liên quan đến authentication.
- Body chứa thông tin công khai, an toàn và đủ để client xử lý.
- Message code/arguments không phụ thuộc vào chuỗi lỗi nội bộ khó ổn định.

## 5. `ErrorResponseException` và `ResponseStatusException`

### 5.1. `ErrorResponseException`

`ErrorResponseException` là runtime exception triển khai `ErrorResponse`. Nó có thể được ném trực tiếp hoặc làm base class cho exception nghiệp vụ cụ thể.

Các constructor chính trong Spring Framework 6.1:

```java
new ErrorResponseException(HttpStatus.NOT_FOUND);

new ErrorResponseException(
        HttpStatus.NOT_FOUND,
        cause
);

new ErrorResponseException(
        HttpStatus.NOT_FOUND,
        problemDetail,
        cause
);
```

Sau khi tạo, có thể tùy chỉnh body:

```java
exception.setType(URI.create(
        "https://api.example.com/problems/order-not-found"
));
exception.setTitle("Order not found");
exception.setDetail("No order exists with id 42");
exception.setInstance(URI.create("/orders/42"));
```

Hoặc dùng `exception.getBody().setProperty(...)` để thêm extension members.

### 5.2. `ResponseStatusException`

`ResponseStatusException` là subclass của `ErrorResponseException`. Nó phù hợp với lỗi HTTP ngắn gọn, không cần một class exception chuyên biệt:

```java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND,
        "Order 42 was not found"
);
```

Trong reactive chain:

```java
return orderService.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Order was not found"
                )
        ));
```

`reason` mặc định được ánh xạ thành `detail` của `ProblemDetail`. Nếu API cần `type`, `code`, extension members hoặc quy tắc tái sử dụng ổn định, một subclass `ErrorResponseException` thường rõ ràng hơn.

### 5.3. Chọn cách nào?

| Cách | Phù hợp khi |
|---|---|
| `ResponseStatusException` | Lỗi HTTP đơn giản, dùng một lần hoặc không cần extension riêng |
| `ErrorResponseException` trực tiếp | Cần body/status cụ thể nhưng chưa cần một exception class riêng |
| Subclass `ErrorResponseException` | Lỗi nghiệp vụ ổn định, có `type`, `code`, properties và quy tắc HTTP riêng |
| Trả `ProblemDetail` từ `@ExceptionHandler` | Muốn tách exception nội bộ khỏi format HTTP |
| `ErrorResponse` custom | Cần tự triển khai hợp đồng status/headers/body hoặc tích hợp một abstraction lỗi khác |

## 6. Các exception WebFlux tích hợp sẵn

Nhiều exception do Spring WebFlux phát sinh đã triển khai `ErrorResponse`. Ví dụ:

| Exception | Tình huống thường gặp | Status thường dùng |
|---|---|---:|
| `ServerWebInputException` | Request input không hợp lệ | 400 |
| `WebExchangeBindException` | Binding hoặc validation lỗi | 400 |
| `HandlerMethodValidationException` | Method validation thất bại | 400 hoặc theo ngữ cảnh lỗi |
| `MethodNotAllowedException` | HTTP method không được hỗ trợ | 405 |
| `NotAcceptableStatusException` | Không có representation phù hợp `Accept` | 406 |
| `UnsupportedMediaTypeStatusException` | `Content-Type` không được hỗ trợ | 415 |
| `MissingRequestValueException` | Thiếu query/header/cookie/path value bắt buộc | 400 |
| `NoResourceFoundException` | Không tìm thấy static resource | 404 |

Danh sách và chi tiết có thể thay đổi theo phiên bản Spring. Kiểm tra exception cụ thể của phiên bản dự án trước khi phụ thuộc vào một status hoặc message code.

Điểm có ích là các exception framework này đã có status và ProblemDetail tương ứng. Ứng dụng không cần bắt từng loại rồi viết lại một JSON tùy ý.

## 7. Các tầng xử lý lỗi trong Spring WebFlux

WebFlux có nhiều extension point; hãy chọn theo nơi exception phát sinh.

### 7.1. `@ExceptionHandler` và `@RestControllerAdvice`

Đây là lựa chọn thuận tiện cho lỗi trong annotated controller:

```java
@RestControllerAdvice
class ApiExceptionAdvice {

    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ProblemDetail> handleOrderConflict(
            OrderConflictException exception,
            ServerWebExchange exchange) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "The order cannot be changed in its current state"
        );

        problem.setType(URI.create(
                "https://api.example.com/problems/order-conflict"
        ));
        problem.setTitle("Order conflict");
        problem.setInstance(
                URI.create(exchange.getRequest().getPath().value())
        );
        problem.setProperty("code", "ORDER_CONFLICT");

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
```

Đây là mã minh họa độc lập cho một exception nghiệp vụ. `@RestControllerAdvice` áp dụng handler cho các controller được component scan tìm thấy. Trả `ResponseEntity<ProblemDetail>` cho phép chọn status, headers và body cùng lúc.

Nếu chỉ trả `ProblemDetail`, Spring có thể suy ra HTTP status từ `problem.status`; dùng `ResponseEntity` khi muốn thể hiện rõ status và headers.

### 7.2. `ResponseEntityExceptionHandler`

Spring WebFlux có class:

```java
org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler
```

Class này là base class tiện dụng cho `@ControllerAdvice`, xử lý các exception WebFlux tích hợp và `ErrorResponseException`, đồng thời render body theo Problem Details.

Có thể mở rộng:

```java
@RestControllerAdvice
class GlobalApiExceptionHandler
        extends ResponseEntityExceptionHandler {
    // Có thể override các hook xử lý exception cụ thể
    // hoặc bổ sung handler cho exception nghiệp vụ.
}
```

Các hook như `handleExceptionInternal(...)` và `createResponseEntity(...)` cho phép tùy chỉnh response chung hoặc bước tạo `ResponseEntity` cuối cùng. Chữ ký và các hook cụ thể cần đối chiếu Javadoc đúng phiên bản Spring.

Dùng base class này khi muốn giữ xử lý nhất quán cho exception của framework. Tránh tạo nhiều `@ControllerAdvice` cùng xử lý một exception mà không quy định thứ tự.

### 7.3. Bật Problem Details tự động trong Spring Boot

Với Spring Boot WebFlux, có thể bật hỗ trợ Problem Details cho exception tích hợp bằng:

```properties
spring.webflux.problemdetails.enabled=true
```

Khi bật, Boot cấu hình `ResponseEntityExceptionHandler` để xử lý exception WebFlux tích hợp và `ErrorResponseException` với problem response.

Nếu muốn thay cách xử lý một exception tích hợp cụ thể, hãy lưu ý thứ tự `@ControllerAdvice`. Handler riêng cần có thứ tự ưu tiên phù hợp so với advice Boot auto-configure. Đừng vô tình đăng ký hai handler cùng ưu tiên cho cùng exception.

Bật property không có nghĩa mọi lỗi trong mọi tầng của ứng dụng đều tự động có body theo ý muốn. Lỗi trong filter, functional handler hoặc tầng server có thể cần extension point ở WebFlux handler chain hoặc Boot error handler.

### 7.4. `WebExceptionHandler`

`WebExceptionHandler` xử lý exception trong WebFlux `WebHandler` chain, bao gồm lỗi từ filter và target handler. Nó hữu ích khi cần xử lý lỗi ở tầng thấp hơn controller advice.

Spring có `ResponseStatusExceptionHandler` để ánh xạ `ResponseStatusException` sang status. `WebFluxResponseStatusExceptionHandler` còn nhận biết `@ResponseStatus` trên exception. Những handler này tập trung vào status; nếu cần một ProblemDetail body thống nhất cho mọi lỗi ở tầng này, phải triển khai response body tương ứng.

### 7.5. `ErrorWebExceptionHandler` trong Spring Boot

Spring Boot cung cấp `ErrorWebExceptionHandler` và base class `AbstractErrorWebExceptionHandler` để tùy chỉnh lỗi ở tầng server bằng functional style. Đây là extension point thấp hơn controller advice.

Chỉ nên dùng khi cần kiểm soát error handling toàn server, chẳng hạn lỗi ngoài DispatcherHandler hoặc custom routing. Với lỗi nghiệp vụ thông thường của annotated controller, `@RestControllerAdvice`/`ResponseEntityExceptionHandler` thường đơn giản hơn.

Không tạo hai tầng cùng ghi response body cho một lỗi. Khi response đã commit, handler không thể thay status hoặc ghi một response lỗi thứ hai.

## 8. Chuẩn hóa exception nghiệp vụ

Một API lớn nên định nghĩa danh mục lỗi ổn định thay vì để từng service tự chọn status và message.

Ví dụ:

| Mã lỗi | HTTP status | `type` |
|---|---:|---|
| `ORDER_NOT_FOUND` | 404 | `/problems/order-not-found` |
| `ORDER_CONFLICT` | 409 | `/problems/order-conflict` |
| `INVALID_QUANTITY` | 400 | `/problems/invalid-quantity` |
| `PAYMENT_REQUIRED` | 402 hoặc status nghiệp vụ đã thống nhất | `/problems/payment-required` |
| `RATE_LIMITED` | 429 | `/problems/rate-limited` |
| `INTERNAL_ERROR` | 500 | `/problems/internal-error` |

Status phải theo semantics HTTP và hợp đồng API. Không dùng `200 OK` cho lỗi chỉ vì muốn response body có trường `"success": false`.

Một exception nghiệp vụ có thể đóng gói mapping:

```java
final class OrderNotFoundException extends ErrorResponseException {

    OrderNotFoundException(long orderId) {
        super(
                HttpStatus.NOT_FOUND,
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.NOT_FOUND,
                        "No order exists with id " + orderId
                ),
                null
        );

        setType(URI.create(
                "https://api.example.com/problems/order-not-found"
        ));
        setTitle("Order not found");
        getBody().setProperty("code", "ORDER_NOT_FOUND");
        getBody().setProperty("orderId", orderId);
    }
}
```

Service có thể phát exception này:

```java
Mono<Order> findOrder(long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)
            ));
}
```

Service không cần biết `ResponseEntity`, JSON serialization hoặc controller advice. Exception mang metadata HTTP; tầng web chịu trách nhiệm render nó.

Một nguyên tắc quan trọng: chỉ đưa dữ liệu an toàn ra response. Nếu `orderId` là định danh công khai thì có thể thêm; nếu giá trị là thông tin nội bộ hoặc nhạy cảm, chỉ dùng mã lỗi chung.

## 9. Validation errors: trả lỗi có cấu trúc

Validation thường phát sinh từ:

- `@Valid` trên request body.
- `@Validated` và method validation.
- Bean Validation như `@NotBlank`, `@Positive`, `@Email`.
- Validator tùy chỉnh.

Ví dụ DTO:

```java
public record CreateOrderRequest(
        @NotBlank String product,
        @Positive int quantity
) {}
```

Controller:

```java
@PostMapping("/orders")
Mono<OrderView> create(
        @Valid @RequestBody Mono<CreateOrderRequest> request) {

    return request.flatMap(orderService::create);
}
```

Trong WebFlux, lỗi binding/validation có thể được biểu diễn qua `WebExchangeBindException` hoặc `HandlerMethodValidationException` tùy cách khai báo và loại validation. Đây là các `ErrorResponse` có thể được xử lý bởi Problem Details support.

Body validation nên đưa danh sách lỗi thành extension có cấu trúc:

```json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "quantity",
      "code": "Positive",
      "message": "must be greater than zero"
    }
  ]
}
```

Nên giữ tên field, validation code và message an toàn. Không mặc định trả `rejectedValue` vì giá trị đó có thể chứa password, token hoặc dữ liệu cá nhân.

Nếu cần format lỗi validation riêng, có thể tùy chỉnh handler của `ResponseEntityExceptionHandler` hoặc xử lý `WebExchangeBindException` trong `@ExceptionHandler`. Đảm bảo mọi lỗi vẫn có status 400 và cùng schema extension.

## 10. Quốc tế hóa bằng `MessageSource`

Một API có thể trả thông báo tiếng Việt hoặc tiếng Anh tùy locale. `ErrorResponse` cung cấp message code cho `type`, `title`, `detail` và argument cho detail. `ResponseEntityExceptionHandler` có thể giải quyết các code đó qua Spring `MessageSource`.

Mẫu code mặc định có dạng:

```text
problemDetail.type.<fully-qualified-exception-class>
problemDetail.title.<fully-qualified-exception-class>
problemDetail.detail.<fully-qualified-exception-class>
```

Có thể thêm suffix cho những exception có nhiều loại message.

Ví dụ file `messages.properties`:

```properties
problemDetail.title.com.example.OrderNotFoundException=Order not found
problemDetail.detail.com.example.OrderNotFoundException=No order exists with id {0}
```

File `messages_vi.properties`:

```properties
problemDetail.title.com.example.OrderNotFoundException=Không tìm thấy đơn hàng
problemDetail.detail.com.example.OrderNotFoundException=Không tồn tại đơn hàng có mã {0}
```

Tên exception phải khớp fully qualified class name thật trong dự án. Nếu constructor của `ErrorResponseException` nhận message detail code và arguments, có thể dùng để truyền dữ liệu cho việc resolve detail.

Không dùng message bản địa hóa làm mã lỗi máy đọc. Client nên dựa vào `type` hoặc extension `code`; `title` và `detail` là nội dung trình bày có thể thay đổi theo locale.

## 11. Bảo mật và chất lượng của error response

Một error response tốt cần đủ thông tin để client sửa request hoặc quyết định bước tiếp theo, nhưng không tiết lộ cách hệ thống hoạt động bên trong.

Nên:

- Dùng `type` URI ổn định và `code` máy đọc được.
- Chọn HTTP status đúng semantics.
- Viết `detail` ngắn, cụ thể và có thể hành động.
- Thêm `instance` hoặc correlation ID để hỗ trợ tra cứu.
- Trả validation errors có cấu trúc.
- Giữ stack trace, SQL, hostname, filesystem path và nguyên nhân nhạy cảm trong log nội bộ.
- Phân biệt lỗi client (`4xx`) với lỗi server (`5xx`).
- Không biến mọi exception thành 400 hoặc 200.
- Không gửi thông tin authorization hoặc dữ liệu cá nhân trong extension.
- Không để exception message của thư viện bên thứ ba đi thẳng tới client.

Ví dụ không an toàn:

```json
{
  "status": 500,
  "detail": "org.postgresql.util.PSQLException: password authentication failed for user ..."
}
```

Ví dụ an toàn hơn:

```json
{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "detail": "The request could not be completed",
  "code": "INTERNAL_ERROR",
  "traceId": "req-8f21"
}
```

Chi tiết kỹ thuật đầy đủ vẫn có thể được ghi ở server log theo trace ID, với quyền truy cập và chính sách lưu giữ phù hợp.

## 12. Client đọc Problem Details bằng WebClient

Client không nên chỉ kiểm tra chuỗi message. Nó có thể đọc status, header và body `ProblemDetail`.

Ví dụ:

```java
Mono<OrderView> result = webClient.get()
        .uri("/orders/{id}", 42)
        .retrieve()
        .bodyToMono(OrderView.class)
        .onErrorResume(WebClientResponseException.class, ex -> {
            ProblemDetail problem =
                    ex.getResponseBodyAs(ProblemDetail.class);

            if (problem != null
                    && "ORDER_NOT_FOUND".equals(
                            problem.getProperties() == null
                                    ? null
                                    : problem.getProperties().get("code"))) {
                return Mono.empty();
            }

            return Mono.error(ex);
        });
```

Đây là đoạn minh họa client-side. Cần import `WebClientResponseException` và `ProblemDetail`. Khi Jackson mixin unwrap extension members, `getProperties()` vẫn là API truy cập map sau khi deserialize. Hãy kiểm tra cách client codec cấu hình deserialize extension fields trong phiên bản Spring đang dùng.

Trong code production, đừng biến mọi 404 thành empty nếu 404 có thể mang ý nghĩa khác. Kiểm tra `type` hoặc `code` ổn định để phân biệt loại problem. Với lỗi không được xử lý, giữ nguyên exception hoặc ánh xạ sang một lỗi domain ở client.

## 13. Ví dụ Java 17+ chạy được với Spring Boot WebFlux

Ví dụ dưới đây tạo API có:

- `GET /orders/42`: trả order bình thường.
- `GET /orders/404`: phát `OrderNotFoundException`, trả RFC 9457 Problem Details.
- `GET /orders/0`: phát `ResponseStatusException` với status 400.
- Problem Details được bật cho exception tích hợp bằng cấu hình Spring Boot.

### Cấu trúc dự án

```text
problem-details-webflux/
├── pom.xml
├── src/main/resources/application.properties
└── src/main/java/demo/Main.java
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>problem-details-webflux</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### File `src/main/resources/application.properties`

```properties
server.port=8080
spring.webflux.problemdetails.enabled=true
```

### File `src/main/java/demo/Main.java`

```java
package demo;

import java.net.URI;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.ErrorResponseException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }
}

@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    Mono<OrderView> get(@PathVariable long id) {
        if (id == 0) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Order id must be positive"
            ));
        }

        if (id == 404) {
            return Mono.error(new OrderNotFoundException(id));
        }

        return Mono.just(new OrderView(id, "created"));
    }

    record OrderView(long id, String state) {}
}

final class OrderNotFoundException extends ErrorResponseException {

    OrderNotFoundException(long orderId) {
        super(
                HttpStatus.NOT_FOUND,
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.NOT_FOUND,
                        "No order exists with id " + orderId
                ),
                null
        );

        setType(URI.create(
                "https://api.example.com/problems/order-not-found"
        ));
        setTitle("Order not found");
        getBody().setProperty("code", "ORDER_NOT_FOUND");
        getBody().setProperty("orderId", orderId);
    }
}
```

Chạy từ thư mục dự án với JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

### Request thành công

```bash
curl -i http://localhost:8080/orders/42
```

Body:

```json
{"id":42,"state":"created"}
```

### Request không tìm thấy order

```bash
curl -i http://localhost:8080/orders/404
```

Các phần chính của response:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 404",
  "instance": "/orders/404",
  "code": "ORDER_NOT_FOUND",
  "orderId": 404
}
```

`instance` được Spring thiết lập theo request path nếu body chưa có giá trị. Các header phụ như `Date` có thể khác theo runtime.

### Request có ID không hợp lệ

```bash
curl -i http://localhost:8080/orders/0
```

Response có status `400 Bad Request`; `ResponseStatusException` được ánh xạ qua cơ chế xử lý lỗi WebFlux. Nội dung detail có thể được tùy chỉnh theo cấu hình Problem Details và message source.

**Giải thích luồng:**

1. Spring Boot tạo WebFlux server và controller.
2. Property `spring.webflux.problemdetails.enabled=true` bật hỗ trợ RFC 9457 cho exception WebFlux tích hợp.
3. `OrderNotFoundException` kế thừa `ErrorResponseException`, nên mang theo status 404 và body `ProblemDetail`.
4. `setType`, `setTitle` và `setProperty` thêm thông tin loại lỗi và extension.
5. Exception được phát bằng `Mono.error`; controller không tự subscribe.
6. Error handling của WebFlux/Boot render status, headers và body `application/problem+json`.

Ví dụ dùng dữ liệu tĩnh để có output dễ kiểm tra. Trong ứng dụng thật, service/repository sẽ cung cấp order và exception chỉ được phát khi không tìm thấy tài nguyên.

## 14. Kiểm thử bằng `WebTestClient`

Có thể kiểm tra status, media type và extension fields mà không mở cổng TCP:

```java
WebTestClient client = WebTestClient
        .bindToController(new OrderController())
        .build();

client.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);

client.get()
        .uri("/orders/404")
        .exchange()
        .expectStatus().isNotFound()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
        .expectBody()
        .jsonPath("$.type").isEqualTo(
                "https://api.example.com/problems/order-not-found"
        )
        .jsonPath("$.status").isEqualTo(404)
        .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND")
        .jsonPath("$.orderId").isEqualTo(404);
```

Đây là đoạn test minh họa, cần `spring-test` (thường được đưa vào qua `spring-boot-starter-test`) và import `WebTestClient`, `MediaType`. `bindToController` kiểm tra controller và exception mapping cục bộ; để xác minh Boot auto-configuration, advice ordering, codecs và toàn bộ server error chain, hãy viết integration test khởi tạo application context.

Nên có test cho:

- Domain error 404/409 và extension fields.
- Built-in binding/validation error.
- JSON sai cú pháp và `Content-Type` không hỗ trợ.
- Header `Allow` hoặc headers đặc thù của status.
- Locale khác nhau và message source.
- Error response không chứa stack trace hoặc secret.
- Lỗi phát sinh ngoài controller nếu ứng dụng có custom filter/functional route.

## 15. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng body JSON khác nhau cho từng controller | Client phải viết nhiều parser | Chuẩn hóa bằng `ProblemDetail` |
| Body ghi status khác HTTP response | Client nhận hai thông tin mâu thuẫn | Dùng cùng status ở `ResponseEntity` và `ProblemDetail` |
| Dùng `detail` làm mã lỗi | Client phụ thuộc câu chữ/bản dịch | Thêm `type` hoặc extension `code` ổn định |
| Đưa stack trace vào body | Lộ cấu trúc và thông tin nội bộ | Log server-side; trả detail an toàn |
| Dùng `ResponseStatusException` cho mọi lỗi domain | Thiếu type/code/extensions ổn định | Tạo subclass `ErrorResponseException` |
| Nghĩ `ProblemDetail` tự xử lý exception | Có body model nhưng chưa có nơi render exception | Dùng `@ExceptionHandler`, `ResponseEntityExceptionHandler` hoặc error handler phù hợp |
| Bật Boot property nhưng kỳ vọng mọi lỗi mọi tầng đều được xử lý | Lỗi filter/functional/server có thể đi qua tầng khác | Xác định đúng error handling layer |
| Đăng ký nhiều advice cùng xử lý một exception | Handler bị chọn không như dự kiến | Thiết kế thứ tự và phạm vi rõ ràng |
| Trả rejected value cho mọi validation error | Có thể lộ password/token | Chỉ trả field, code và message an toàn |
| Dùng message tiếng Việt làm `type` | Client không có định danh ổn định | Dùng URI/code ổn định, bản địa hóa title/detail |
| Bỏ qua headers trong `ErrorResponse` | Có thể mất `Allow` hoặc metadata HTTP cần thiết | Giữ headers của ErrorResponse khi render |
| Chuyển mọi exception thành 400 | Lỗi server bị gắn nhãn lỗi client | Phân loại lỗi theo status và semantics |
| Cố ghi error response sau khi response đã commit | Không thể thay status/body đã gửi | Quyết định status trước commit; stream lỗi thì kết thúc hoặc phát error event |
| Dùng extension field trùng `status`, `type`, `detail` | Gây nhập nhằng schema | Chọn tên riêng như `code`, `traceId`, `errors` |
| Không test media type | Client nhận body nhưng sai content type | Test `application/problem+json` |

## 16. Checklist thiết kế error contract

Trước khi công bố API, kiểm tra:

1. Mọi lỗi có status HTTP phù hợp không?
2. `ProblemDetail.status` có khớp status thực tế không?
3. `type` và extension `code` có ổn định qua phiên bản không?
4. `title` ngắn gọn và `detail` có thể hành động không?
5. `instance` có nhận diện được lần xảy ra lỗi không?
6. Extension fields có schema thống nhất giữa endpoint không?
7. Validation errors có field/code/message nhưng không lộ rejected value nhạy cảm không?
8. `ErrorResponse` headers đặc thù có được giữ lại không?
9. Lỗi framework và lỗi nghiệp vụ có cùng định dạng không?
10. Lỗi controller, filter, functional route và server có được xử lý ở đúng tầng không?
11. `MessageSource` có hỗ trợ locale cần thiết không?
12. Client có thể xử lý bằng `type`/`code` thay vì parse `detail` không?
13. Có test 4xx, 5xx, media type và extension fields không?
14. Không có stack trace, SQL hoặc secret trong response không?

## 17. Bài tập tự kiểm tra

**Câu 1.** `ProblemDetail` và `ErrorResponse` khác nhau thế nào?

**Đáp án:** `ProblemDetail` biểu diễn body theo RFC 9457; `ErrorResponse` mô tả toàn bộ HTTP error gồm status, headers và body đó.

**Câu 2.** `ErrorResponseException` có vai trò gì?

**Đáp án:** Là runtime exception triển khai `ErrorResponse`, dùng trực tiếp hoặc làm base class cho exception chuyên biệt.

**Câu 3.** `ResponseStatusException` có quan hệ gì với `ErrorResponseException`?

**Đáp án:** Nó là subclass, nhận status và reason; reason mặc định được ánh xạ vào `ProblemDetail.detail`.

**Câu 4.** Vì sao cần extension field `code` nếu đã có `detail`?

**Đáp án:** `detail` là câu giải thích cho người đọc và có thể được bản địa hóa; `code` là định danh ổn định cho client logic.

**Câu 5.** `ProblemDetail.status` có thể là 404 trong khi HTTP response là 200 không?

**Đáp án:** Không nên. Status trong body phải khớp status HTTP thực tế.

**Câu 6.** Muốn chuẩn hóa exception WebFlux tích hợp trong Spring Boot, property nào cần bật?

**Đáp án:** `spring.webflux.problemdetails.enabled=true`.

**Câu 7.** `ResponseEntityExceptionHandler` của WebFlux nằm ở package nào?

**Đáp án:** `org.springframework.web.reactive.result.method.annotation`, khác package của Spring MVC.

**Câu 8.** Lỗi phát sinh trong WebFilter có nhất thiết đi qua `@RestControllerAdvice` không?

**Đáp án:** Không. Nó có thể cần `WebExceptionHandler` hoặc error handling ở tầng Spring Boot WebFlux.

**Câu 9.** Có nên trả stack trace trong `ProblemDetail.detail` không?

**Đáp án:** Không. Trả thông tin an toàn và dùng trace ID để tra log nội bộ.

**Câu 10.** Khi validation thất bại, nên trả gì để client xử lý được?

**Đáp án:** Status 400, problem type/code ổn định và danh sách lỗi có cấu trúc theo field/code/message; tránh đưa giá trị nhạy cảm của người dùng.

## 18. Quy tắc áp dụng

- Dùng `ProblemDetail` để biểu diễn body lỗi theo RFC 9457.
- Dùng `ErrorResponse` để gói status, headers và body thành một hợp đồng.
- Dùng `ErrorResponseException` hoặc `ResponseStatusException` để exception mang thông tin HTTP.
- Dùng subclass `ErrorResponseException` cho lỗi nghiệp vụ cần `type`, `code` và extension ổn định.
- Dùng `@RestControllerAdvice`/`ResponseEntityExceptionHandler` cho annotated controller; dùng `WebExceptionHandler` hoặc `ErrorWebExceptionHandler` khi lỗi nằm ở tầng thấp hơn.
- Bật `spring.webflux.problemdetails.enabled=true` nếu muốn Boot cấu hình Problem Details cho exception WebFlux tích hợp.
- Chuẩn hóa validation errors, message codes và extension fields.
- Không tiết lộ stack trace, SQL, token hoặc dữ liệu cá nhân.
- Kiểm thử status, headers, `application/problem+json` và schema mà client thực sự nhận được.

**Ghi nhớ:** `ProblemDetail` là nội dung lỗi; `ErrorResponse` là hợp đồng HTTP; `ErrorResponseException` gắn hợp đồng đó vào exception. Spring WebFlux có thể chuẩn hóa lỗi framework và lỗi nghiệp vụ thành RFC 9457, giúp client nhận status, mã lỗi và thông tin xử lý nhất quán.

## 19. Tài liệu tham khảo chính thức

- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [Spring Framework — Error Responses trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html)
- [Spring Framework 6.1 — `ProblemDetail` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Framework 6.1 — `ErrorResponse` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/ErrorResponse.html)
- [Spring Framework 6.1 — `ErrorResponseException` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/ErrorResponseException.html)
- [Spring Framework 6.1 — WebFlux `ResponseEntityExceptionHandler` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework — Reactive exception handling](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Boot — Reactive Web Applications and Problem Details](https://docs.spring.io/spring-boot/reference/web/reactive.html)
