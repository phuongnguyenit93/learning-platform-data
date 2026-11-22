# Tùy biến ResponseEntityExceptionHandler

**Ngữ cảnh:** Spring Framework Reactive → **Lỗi HTTP**.

Trong Spring WebFlux, lỗi có thể phát sinh khi đọc request, giải mã body, binding dữ liệu, validate tham số, chạy controller hoặc gọi service. API cần chuyển các lỗi đó thành HTTP response nhất quán: status đúng, header phù hợp và body dễ hiểu cho client.

`ResponseEntityExceptionHandler` là lớp nền tiện dụng cho một `@ControllerAdvice` trong **WebFlux annotated controllers**. Lớp này xử lý nhiều exception do Spring WebFlux phát sinh và trả `ResponseEntity` theo định dạng **Problem Details for HTTP APIs (RFC 9457)**. Bạn có thể tùy biến từng exception, cách xử lý chung, hoặc bước cuối tạo response.

Các điểm mở rộng chính:

- Override `handleWebExchangeBindException(...)` hoặc một `handle...Exception(...)` cụ thể khi muốn đổi cách xử lý một loại lỗi Spring.
- Override `handleExceptionInternal(...)` để áp dụng chính sách chung cho các exception được lớp nền xử lý.
- Override `createResponseEntity(...)` để bổ sung hoặc điều chỉnh body, headers hay status ở bước cuối.
- Thêm `@ExceptionHandler` cho exception riêng của ứng dụng, chẳng hạn xung đột trạng thái nghiệp vụ.

Các method của WebFlux trả `Mono<ResponseEntity<Object>>`. Đây là API reactive; không dùng chữ ký đồng bộ của Spring MVC.

## 1. Vị trí trong WebFlux

Trong mô hình annotated controller, request đi qua web handler chain, được ánh xạ tới controller, rồi framework xử lý exception phát sinh trong quá trình đó:

```text
HTTP request
    |
    v
WebFilter / Spring Security
    |
    v
DispatcherHandler
    |
    v
Argument resolvers / HttpMessageReader
    |
    v
Controller method
    |
    v
Application service
    |
    +---- success ----> ResponseEntity / body writer
    |
    +---- exception --> @ControllerAdvice
                           |
                           v
                    ResponseEntityExceptionHandler
                           |
                           v
                    Mono<ResponseEntity<Object>>
                           |
                           v
                    HTTP response
```

`ResponseEntityExceptionHandler` nằm trong package:

```java
org.springframework.web.reactive.result.method.annotation
```

Đừng nhầm với lớp Spring MVC:

```java
org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler
```

Hai lớp cùng tên nhưng thuộc hai stack khác nhau:

| Nội dung | WebFlux | Spring MVC |
|---|---|---|
| Package | `org.springframework.web.reactive.result.method.annotation` | `org.springframework.web.servlet.mvc.method.annotation` |
| Request context | `ServerWebExchange` | `WebRequest` |
| Return type của handler protected | `Mono<ResponseEntity<Object>>` | `ResponseEntity<Object>` |
| Execution | Reactive | Servlet MVC |

Một advice WebFlux tối giản:

```java
@RestControllerAdvice
public class ApiExceptionHandler
        extends ResponseEntityExceptionHandler {
}
```

Spring đăng ký advice này trong application context. Lớp nền có method `handleException(...)` được gắn `@ExceptionHandler` để xử lý nhiều exception của WebFlux. Bạn không cần tự khai báo một catch-all `@ExceptionHandler(Exception.class)` trùng với nó.

**Phạm vi cần nhớ:** đây là cơ chế exception handling của annotated controllers. Không mặc định rằng nó bắt mọi lỗi ở mọi nơi trong server. Lỗi xảy ra trong `WebFilter`, Spring Security, server adapter hoặc functional endpoint `RouterFunction` có thể cần xử lý ở tầng tương ứng như `WebExceptionHandler`, `ErrorWebExceptionHandler` hoặc route-local `HandlerFilterFunction`.

## 2. ProblemDetail và RFC 9457

Spring Framework hỗ trợ RFC 9457 để chuẩn hóa error response. `ProblemDetail` là object mô tả một vấn đề HTTP; `ErrorResponse` là contract cung cấp status, headers và ProblemDetail cho exception.

Các field chuẩn:

| Field | Ý nghĩa | Ví dụ |
|---|---|---|
| `type` | URI định danh loại vấn đề | `https://api.example.com/problems/validation` |
| `title` | Tên ngắn của vấn đề | `Validation failed` |
| `status` | HTTP status | `400` |
| `detail` | Giải thích cụ thể cho lần xảy ra này | `One or more fields are invalid.` |
| `instance` | URI/path xác định lần xảy ra | `/orders` |

Ví dụ response:

```json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/orders",
  "errors": [
    {
      "field": "quantity",
      "message": "must be greater than 0"
    }
  ],
  "requestId": "request-123"
}
```

`errors` và `requestId` là extension do ứng dụng thêm. Khi dùng Jackson với cấu hình Spring, `ProblemDetail.properties` được serialize thành các thuộc tính top-level như trên.

`ProblemDetail` không chỉ là DTO lỗi tùy ý. Status của nó là status của HTTP response khi Spring render nó; `instance` được Spring gán từ path hiện tại nếu chưa có giá trị. Với JSON, media type phù hợp là `application/problem+json`.

### 2.1. ErrorResponse và ErrorResponseException

- `ErrorResponse` cung cấp status, response headers, body ProblemDetail và message codes.
- Các exception HTTP built-in của Spring WebFlux triển khai `ErrorResponse`.
- `ErrorResponseException` là base implementation tiện dụng cho exception ứng dụng muốn mang theo thông tin response theo contract này.
- `ResponseEntityExceptionHandler` nhận diện các exception thuộc nhóm `ErrorResponse` và render body tương ứng.

Không cần chuyển mọi exception thành `ProblemDetail` bằng tay. Nếu exception đã cung cấp `ErrorResponse`, lớp nền có thể sử dụng body và metadata của nó.

## 3. Những exception mặc định được xử lý

`handleException(Exception, ServerWebExchange)` là method public, final và được annotation để xử lý các exception WebFlux đã đăng ký. Những nhóm phổ biến:

| Exception | Tình huống thường gặp | Status thường dùng |
|---|---|---:|
| `MethodNotAllowedException` | HTTP method không được route hỗ trợ | 405 |
| `NotAcceptableStatusException` | Không có representation phù hợp với `Accept` | 406 |
| `UnsupportedMediaTypeStatusException` | `Content-Type` request không được hỗ trợ | 415 |
| `MissingRequestValueException` | Thiếu header, query value hoặc request value bắt buộc | 400 |
| `UnsatisfiedRequestParameterException` | Điều kiện request parameter không thỏa | 400 |
| `WebExchangeBindException` | Binding hoặc validation request body/model thất bại | 400 |
| `HandlerMethodValidationException` | Validation tham số/return value của handler method | Tùy ngữ cảnh |
| `ServerWebInputException` | Input không đọc/convert được | 400 |
| `ServerErrorException` | Lỗi phía server | 5xx |
| `ResponseStatusException` | Exception mang status được chỉ định | Theo exception |
| `ErrorResponseException` | Exception triển khai ErrorResponse | Theo exception |
| `MethodValidationException` | Method validation thất bại | Theo ngữ cảnh |

Danh sách method protected và exception cụ thể thay đổi theo phiên bản. Hãy xem Javadoc của đúng Spring Framework đang dùng. Các method như `handleHandlerMethodValidationException` và `handleMethodValidationException` có từ Spring 6.1; không có trong mọi phiên bản cũ.

**Giữ status và headers mà Spring truyền vào.** Ví dụ 405 có thể cần header `Allow`; 415 có thể cần thông tin media type hỗ trợ. Khi override handler, đừng vô tình bỏ các headers đó.

## 4. Ba tầng tùy biến quan trọng

`ResponseEntityExceptionHandler` cung cấp ba tầng với phạm vi khác nhau:

| Method | Khi nào dùng | Phạm vi |
|---|---|---|
| `handleXxxException(...)` | Cần xử lý riêng một exception built-in | Một loại lỗi |
| `handleExceptionInternal(...)` | Cần chính sách chung cho các exception đi qua lớp nền | Nhiều loại lỗi |
| `createResponseEntity(...)` | Cần can thiệp ở bước cuối tạo ResponseEntity | Body/header/status sau xử lý |

Luồng tổng quát:

```text
Spring exception
      |
      v
handleXxxException(...)
      |
      v
handleExceptionInternal(...)
      |
      v
createResponseEntity(...)
      |
      v
ResponseEntity<Object>
```

Không phải mọi đường xử lý tùy biến đều bắt buộc đi qua từng method trong mọi trường hợp. Ví dụ một `@ExceptionHandler` riêng có thể tự trả response; nếu muốn tái sử dụng pipeline chung, hãy gọi `handleExceptionInternal` từ handler đó.

### 4.1. handleException là final

`handleException(Exception, ServerWebExchange)` là entry point để dispatch exception sang các method cụ thể. Method này là `final`. Hãy override method protected tương ứng hoặc các điểm chung, không cố override entry point.

## 5. Override một exception cụ thể

Ví dụ, muốn thay đổi body cho lỗi validation request body `WebExchangeBindException`:

```java
@RestControllerAdvice
public class ApiExceptionHandler
        extends ResponseEntityExceptionHandler {

    @Override
    protected Mono<ResponseEntity<Object>>
    handleWebExchangeBindException(
            WebExchangeBindException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            ServerWebExchange exchange) {

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        status,
                        "One or more fields are invalid.");

        problem.setType(URI.create(
                "https://api.example.com/problems/validation"));
        problem.setTitle("Validation failed");

        List<Map<String, String>> errors =
                ex.getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "message",
                                error.getDefaultMessage() == null
                                        ? "Invalid value"
                                        : error.getDefaultMessage()))
                        .toList();

        problem.setProperty("errors", errors);

        return handleExceptionInternal(
                ex, problem, headers, status, exchange);
    }
}
```

Đây là snippet cần imports và class advice thực tế. Các điểm quan trọng:

1. Chữ ký là reactive: trả `Mono<ResponseEntity<Object>>`.
2. Dùng `status` và `headers` mà framework đã truyền vào, thay vì tự đoán status.
3. Lấy lỗi field từ `getFieldErrors()`.
4. Chỉ đưa field và thông báo an toàn vào response; tránh đưa `rejectedValue` nếu giá trị có thể chứa mật khẩu, token hoặc dữ liệu cá nhân.
5. Gọi `handleExceptionInternal` để giữ xử lý chung của lớp nền và đi tiếp tới `createResponseEntity`.

Trong WebFlux, lỗi binding/validation body thường đi qua `WebExchangeBindException`. Validation tham số method có thể phát sinh `HandlerMethodValidationException`; nếu cần định dạng riêng, override method tương ứng của phiên bản Spring đang dùng.

### 5.1. Khi nào không cần override?

Nếu body ProblemDetail mặc định đã đủ, chỉ cần kế thừa lớp nền:

```java
@RestControllerAdvice
public class ApiExceptionHandler
        extends ResponseEntityExceptionHandler {
}
```

Spring đã cung cấp body và status cho các lỗi built-in. Chỉ tùy biến khi API cần format, field extension, thông điệp hoặc policy riêng.

## 6. handleExceptionInternal: xử lý chung

Chữ ký WebFlux:

```java
protected Mono<ResponseEntity<Object>> handleExceptionInternal(
        Exception ex,
        Object body,
        HttpHeaders headers,
        HttpStatusCode status,
        ServerWebExchange exchange)
```

Method này là nơi tập trung xử lý chung cho các handler protected. Bạn có thể dùng nó để:

- Chuẩn hóa metadata chung cho ProblemDetail.
- Ghi log có kiểm soát theo status và exception type.
- Bảo toàn headers do Spring cung cấp.
- Chuyển tiếp tới implementation mặc định để framework xử lý response đã commit và body từ `ErrorResponse`.

Ví dụ bổ sung path cho ProblemDetail:

```java
@Override
protected Mono<ResponseEntity<Object>> handleExceptionInternal(
        Exception ex,
        Object body,
        HttpHeaders headers,
        HttpStatusCode status,
        ServerWebExchange exchange) {

    if (body instanceof ProblemDetail problem) {
        problem.setProperty(
                "path",
                exchange.getRequest().getPath().value());
    }

    return super.handleExceptionInternal(
            ex, body, headers, status, exchange);
}
```

Đây là snippet; hãy giữ đúng nullability annotation nếu phiên bản dự án yêu cầu. Trong Javadoc hiện hành, body và headers có thể nullable. Nếu cần hỗ trợ cả body không phải ProblemDetail, không ép cast.

Implementation mặc định có thể không tạo response mới khi response đã commit; nó cũng có thể lấy body từ `ErrorResponse` khi body được truyền vào là null.

**Đừng thay thế hoàn toàn implementation mặc định một cách tùy tiện.** Nếu override, gọi `super` sau khi bổ sung phần cần thiết để giữ logic framework, trừ khi bạn có chủ đích thay đổi contract đó.

## 7. createResponseEntity: bước cuối tạo response

Chữ ký WebFlux:

```java
protected Mono<ResponseEntity<Object>> createResponseEntity(
        Object body,
        HttpHeaders headers,
        HttpStatusCode status,
        ServerWebExchange exchange)
```

Đây là điểm cuối để xem hoặc điều chỉnh body, headers và status trước khi `ResponseEntity` được trả về.

Ví dụ thêm request ID và path vào mọi ProblemDetail:

```java
@Override
protected Mono<ResponseEntity<Object>> createResponseEntity(
        Object body,
        HttpHeaders headers,
        HttpStatusCode status,
        ServerWebExchange exchange) {

    if (body instanceof ProblemDetail problem) {
        problem.setProperty(
                "path",
                exchange.getRequest().getPath().value());
        problem.setProperty(
                "requestId",
                exchange.getRequest().getId());
    }

    return super.createResponseEntity(
            body, headers, status, exchange);
}
```

`ServerHttpRequest.getId()` là request identifier do request abstraction cung cấp; nó không mặc nhiên là distributed trace ID. Nếu API cần trace ID xuyên service, lấy từ tracing/observation context đã cấu hình và chỉ đưa giá trị an toàn vào response.

Dùng `createResponseEntity` cho metadata chung. Không thực hiện truy vấn database hoặc gọi service nghiệp vụ tại đây; đây là tầng hoàn tất response.

## 8. Thêm exception nghiệp vụ bằng @ExceptionHandler

Các exception built-in đã được lớp nền xử lý. Exception riêng như “đơn hàng không thể sửa ở trạng thái hiện tại” có thể được khai báo bằng `@ExceptionHandler` trong cùng advice:

```java
@ExceptionHandler(OrderConflictException.class)
public Mono<ResponseEntity<Object>> handleOrderConflict(
        OrderConflictException ex,
        ServerWebExchange exchange) {

    ProblemDetail problem =
            ProblemDetail.forStatusAndDetail(
                    HttpStatus.CONFLICT,
                    "Order cannot be changed in its current state.");

    problem.setType(URI.create(
            "https://api.example.com/problems/order-conflict"));
    problem.setTitle("Order conflict");
    problem.setProperty("code", "ORDER_STATE_CONFLICT");

    return handleExceptionInternal(
            ex,
            problem,
            new HttpHeaders(),
            HttpStatus.CONFLICT,
            exchange);
}
```

Đây là snippet cần class `OrderConflictException`. Gọi `handleExceptionInternal` giúp custom exception dùng cùng bước tạo response và metadata chung. Nếu trả `ResponseEntity` trực tiếp, bạn sẽ không đi qua phần xử lý chung này trừ khi tự gọi nó.

Có thể dùng `ErrorResponseException` cho exception muốn mang theo status, headers và ProblemDetail theo contract Spring. Chọn một chiến lược nhất quán; đừng tạo nhiều handler trùng nhau cho cùng exception.

### 8.1. Exception phát sinh trong reactive chain

Controller có thể trả lỗi từ publisher:

```java
@GetMapping("/orders/{id}")
public Mono<OrderView> getOrder(@PathVariable String id) {
    return orderService.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)));
}
```

Khi publisher lỗi trong lúc xử lý request, WebFlux đưa exception tới cơ chế exception handling của annotated controller. Không gọi `subscribe()` bên trong controller để tự xử lý lỗi; hãy để publisher được compose và trả về framework.

## 9. Không để lộ thông tin nội bộ

Error response là hợp đồng công khai. Một lỗi database có thể chứa SQL, tên bảng, hostname, đường dẫn file hoặc credentials. Không sao chép nguyên `ex.getMessage()` của mọi exception vào `detail`.

| Loại lỗi | Thông tin client nên nhận | Thông tin chỉ nên log nội bộ |
|---|---|---|
| Validation | Field không hợp lệ và quy tắc dễ hiểu | Stack trace, rejected value nhạy cảm |
| Không tìm thấy | Resource không tồn tại | Câu SQL hoặc storage path |
| Xung đột nghiệp vụ | Mã lỗi ổn định và cách khắc phục | Internal state, dữ liệu người dùng khác |
| Lỗi dependency | Thông báo dịch vụ tạm thời | Host, credentials, request nội bộ |
| Lỗi bất ngờ 500 | Thông báo tổng quát và request ID | Stack trace, exception chain, payload nhạy cảm |

Ví dụ body 500 an toàn:

```json
{
  "type": "https://api.example.com/problems/internal",
  "title": "Internal server error",
  "status": 500,
  "detail": "An unexpected error occurred.",
  "instance": "/orders",
  "requestId": "request-123"
}
```

Log nội bộ có thể ghi stack trace gắn với cùng request ID. Không gửi stack trace hoặc tên class exception tới client như một cách debug production.

## 10. Internationalization với MessageSource

`ResponseEntityExceptionHandler` triển khai `MessageSourceAware`. Nó có thể resolve message code cho `type`, `title` và `detail` của `ErrorResponse` bằng `MessageSource`.

Mẫu code mặc định:

```text
problemDetail.type.<fully-qualified-exception-class>
problemDetail.title.<fully-qualified-exception-class>
problemDetail.detail.<fully-qualified-exception-class>
```

Ví dụ resource bundle tiếng Việt:

```properties
problemDetail.title.org.springframework.web.bind.support.WebExchangeBindException=Yêu cầu không hợp lệ
problemDetail.detail.org.springframework.web.bind.support.WebExchangeBindException=Kiểm tra lại các trường trong yêu cầu.
```

Resource bundle tiếng Anh có thể cung cấp cùng message code với nội dung khác. Locale resolution quyết định message phù hợp.

Với exception không triển khai `ErrorResponse`, protected method `createProblemDetail(...)` giúp tạo ProblemDetail và thực hiện MessageSource lookup cho detail. Nếu cần tùy biến message theo nghiệp vụ, hãy dùng message code ổn định và arguments có kiểm soát.

### 10.1. ErrorResponse interceptor

Spring WebFlux cho phép đăng ký `ErrorResponse` interceptor qua `WebFluxConfigurer`. Đây là điểm mở rộng phù hợp khi muốn áp dụng một thao tác chung lên các ProblemDetail response mà không viết lại mọi exception handler. Tránh đồng thời sửa cùng field ở interceptor, advice và response factory nếu không có quy tắc rõ ràng.

## 11. Spring Boot: tránh hai cơ chế cùng xử lý một lỗi

Spring Boot có property:

```properties
spring.webflux.problemdetails.enabled=true
```

Property này bật auto-configuration cho Problem Details và đăng ký handler xử lý exception built-in. Khi Boot đã đăng ký advice của mình, việc thêm một advice khác xử lý cùng exception cần được sắp thứ tự rõ ràng. Tài liệu Spring Boot ghi nhận handler auto-configured có order 0; advice muốn xử lý một exception cụ thể trước nó phải có precedence cao hơn.

Hai hướng thường dùng:

1. **Tự quản lý bằng subclass:** tạo `@RestControllerAdvice` kế thừa `ResponseEntityExceptionHandler` và cấu hình để không có handler auto-configured khác tranh xử lý cùng nhóm built-in exception.
2. **Giữ Boot auto-configuration:** dùng `ErrorAttributes` hoặc một `@ControllerAdvice` riêng cho exception cần tùy biến; nếu override một exception built-in, đặt order trước handler Boot và tránh mapping trùng không cần thiết.

Không bật property và đồng thời đăng ký nhiều catch-all handler mà không kiểm tra thứ tự.

### 11.1. Khi cần tùy biến thấp hơn tầng controller

`ResponseEntityExceptionHandler` không thay thế `ErrorWebExceptionHandler`. Nếu cần xử lý lỗi ở tầng WebFlux server rộng hơn, chẳng hạn lỗi từ filter chain hoặc functional routing, có thể dùng `ErrorWebExceptionHandler`. Spring Boot cung cấp `AbstractErrorWebExceptionHandler` để xây dựng fallback error handler theo functional style.

Với WebFlux.fn, `HandlerFilterFunction` là route-local filter; nó không tự trở thành `@ControllerAdvice`. Hãy chọn đúng tầng cho lỗi từ route, filter hoặc annotated controller.

## 12. Chương trình Java 17+ chạy được: validation và lỗi nghiệp vụ

Ví dụ dưới đây dùng Spring Boot 3.5.x, Spring Framework 6.2.x, WebFlux và Bean Validation. Nó minh họa:

- `@RestControllerAdvice` kế thừa `ResponseEntityExceptionHandler`.
- Override `handleWebExchangeBindException` để tạo validation ProblemDetail.
- Override `createResponseEntity` để thêm path và request ID.
- Thêm `@ExceptionHandler` cho exception nghiệp vụ.
- Kiểm thử status và body bằng `WebTestClient`.

Cấu trúc project:

```text
webflux-error-handler-demo/
├── pom.xml
└── src
    ├── main/java/demo/ErrorHandlingApplication.java
    ├── main/java/demo/OrderController.java
    ├── main/java/demo/ApiExceptionHandler.java
    ├── main/java/demo/CreateOrderRequest.java
    ├── main/java/demo/OrderView.java
    └── main/java/demo/OrderConflictException.java
    └── test/java/demo/ErrorHandlingIntegrationTest.java
```

### 12.1. pom.xml

```xml
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

    <groupId>demo</groupId>
    <artifactId>webflux-error-handler-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
```

### 12.2. ErrorHandlingApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorHandlingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ErrorHandlingApplication.class, args);
    }
}
```

### 12.3. CreateOrderRequest.java

```java
package demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @Positive int quantity) {
}
```

### 12.4. OrderView.java

```java
package demo;

public record OrderView(
        String id,
        String status) {
}
```

### 12.5. OrderConflictException.java

```java
package demo;

public class OrderConflictException extends RuntimeException {

    public OrderConflictException() {
        super("Order state does not allow this operation");
    }
}
```

### 12.6. OrderController.java

```java
package demo;

import jakarta.validation.Valid;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/orders")
public class OrderController {

    @PostMapping
    public Mono<OrderView> create(
            @Valid @RequestBody CreateOrderRequest request) {

        if ("blocked".equals(request.customerId())) {
            return Mono.error(new OrderConflictException());
        }

        return Mono.just(
                new OrderView("order-100", "ACCEPTED"));
    }
}
```

### 12.7. ApiExceptionHandler.java

```java
package demo;

import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler;
import org.springframework.web.bind.support.WebExchangeBindException;

import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiExceptionHandler
        extends ResponseEntityExceptionHandler {

    @Override
    protected Mono<ResponseEntity<Object>>
    handleWebExchangeBindException(
            WebExchangeBindException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            ServerWebExchange exchange) {

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        status,
                        "One or more fields are invalid.");

        problem.setType(URI.create(
                "https://api.example.com/problems/validation"));
        problem.setTitle("Validation failed");

        List<Map<String, String>> errors =
                ex.getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "message",
                                error.getDefaultMessage() == null
                                        ? "Invalid value"
                                        : error.getDefaultMessage()))
                        .toList();

        problem.setProperty("errors", errors);

        return handleExceptionInternal(
                ex, problem, headers, status, exchange);
    }

    @ExceptionHandler(OrderConflictException.class)
    public Mono<ResponseEntity<Object>> handleOrderConflict(
            OrderConflictException ex,
            ServerWebExchange exchange) {

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.CONFLICT,
                        "Order cannot be changed in its current state.");

        problem.setType(URI.create(
                "https://api.example.com/problems/order-conflict"));
        problem.setTitle("Order conflict");
        problem.setProperty("code", "ORDER_STATE_CONFLICT");

        return handleExceptionInternal(
                ex,
                problem,
                new HttpHeaders(),
                HttpStatus.CONFLICT,
                exchange);
    }

    @Override
    protected Mono<ResponseEntity<Object>> createResponseEntity(
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            ServerWebExchange exchange) {

        if (body instanceof ProblemDetail problem) {
            problem.setProperty(
                    "path",
                    exchange.getRequest().getPath().value());
            problem.setProperty(
                    "requestId",
                    exchange.getRequest().getId());
        }

        return super.createResponseEntity(
                body, headers, status, exchange);
    }
}
```

Trong code trên:

- Validation error giữ status và headers mà Spring đã chọn.
- Business conflict được ánh xạ thành 409.
- Cả hai đi qua `handleExceptionInternal` và `createResponseEntity`, vì vậy có metadata path/requestId thống nhất.
- `requestId` ở ví dụ là ID của request abstraction, không phải trace ID phân tán.
- Không đưa message exception nội bộ hoặc rejected value vào body.

### 12.8. ErrorHandlingIntegrationTest.java

```java
package demo;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ErrorHandlingIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void invalidBodyReturnsProblemDetail() {
        client.post()
                .uri("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "customerId", "",
                        "quantity", 0))
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("Validation failed")
                .jsonPath("$.status")
                .isEqualTo(400)
                .jsonPath("$.errors")
                .exists()
                .jsonPath("$.path")
                .isEqualTo("/orders");
    }

    @Test
    void businessConflictReturns409() {
        client.post()
                .uri("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "customerId", "blocked",
                        "quantity", 1))
                .exchange()
                .expectStatus().isEqualTo(409)
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("Order conflict")
                .jsonPath("$.code")
                .isEqualTo("ORDER_STATE_CONFLICT");
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn test
```

Hai test xác nhận:

1. Body không hợp lệ tạo HTTP 400 với media type Problem Details, title, status, errors và path.
2. Exception nghiệp vụ được chuyển thành HTTP 409 với mã lỗi ổn định.

Đây là integration test qua embedded WebFlux server. Nó kiểm tra việc argument validation, advice dispatch và response serialization phối hợp với nhau; không chỉ gọi trực tiếp method protected.

## 13. Kiểm thử những tình huống cần thiết

Một error handler production nên có test cho các nhóm:

| Trường hợp | Điều cần xác nhận |
|---|---|
| JSON malformed | Status 400, detail không lộ parser internals |
| Field validation fail | 400 và danh sách lỗi field |
| Method không hỗ trợ | 405 và giữ header `Allow` |
| Media type không hỗ trợ | 415 và headers liên quan |
| Accept không phù hợp | 406 |
| Resource không tồn tại | 404 theo contract |
| Domain conflict | 409 và business error code ổn định |
| Lỗi bất ngờ | 500 với detail tổng quát, log có correlation ID |
| Exception sau khi response commit | Không cố ghi thêm response body mới |
| Client disconnect | Cancellation/cleanup đúng, không biến thành lỗi nghiệp vụ giả |

Dùng `WebTestClient` để kiểm tra status, headers và body. Với logic thuần tạo ProblemDetail, có thể unit test riêng; nhưng ít nhất một integration test cần đi qua WebFlux handler mapping và codec thực tế.

Không chỉ assert status. Một response 400 có thể vẫn sai contract nếu thiếu media type, mất header cần thiết hoặc lộ dữ liệu nội bộ.

## 14. Những lỗi thường gặp

1. **Import nhầm lớp Spring MVC.** WebFlux phải dùng package `org.springframework.web.reactive.result.method.annotation`.
2. **Override với return type đồng bộ.** Protected handler của WebFlux trả `Mono<ResponseEntity<Object>>`.
3. **Cố override `handleException`.** Đây là method final; override các method protected chuyên biệt hoặc method chung.
4. **Tạo catch-all @ExceptionHandler trùng với lớp nền.** Có thể gây ambiguous mapping hoặc làm mất dispatch built-in.
5. **Bỏ headers được truyền vào.** Có thể làm mất `Allow`, media type hỗ trợ hoặc metadata HTTP quan trọng.
6. **Hard-code status 400 cho mọi lỗi.** Giữ status được framework truyền vào; validation, 404, 405, 406, 415 và lỗi server khác nhau.
7. **Chỉ sửa body ở một method chuyên biệt.** Nếu mọi ProblemDetail cần path/request ID, cân nhắc `createResponseEntity`.
8. **Override handleExceptionInternal nhưng không gọi super.** Có thể bỏ logic xử lý response đã commit và body từ ErrorResponse.
9. **Trả exception.getMessage() cho mọi lỗi.** Có thể lộ SQL, path nội bộ, token hoặc thông tin hạ tầng.
10. **Đưa rejectedValue vào validation body.** Giá trị có thể là dữ liệu nhạy cảm; chỉ trả field và thông báo cần thiết.
11. **Tùy biến status trong createResponseEntity mà không có quy tắc.** Status phải theo API contract và headers tương ứng.
12. **Cho rằng @RestControllerAdvice xử lý mọi lỗi WebFlux.** Filter, security, functional endpoint và transport error có thể ở tầng khác.
13. **Bật Boot Problem Details rồi thêm nhiều advice trùng nhau.** Cần hiểu thứ tự handler auto-configured và chọn một chiến lược rõ.
14. **Nhầm RFC 7807 với RFC 9457.** Spring Framework hiện hỗ trợ RFC 9457; hãy dùng media type và tài liệu đúng phiên bản.
15. **Bỏ qua MessageSource.** Thông báo hard-code khó quốc tế hóa; dùng message code cho title/detail khi cần.
16. **Không xử lý lỗi trong reactive chain.** Exception phát từ Mono/Flux vẫn cần được compose và trả về framework.
17. **Tạo response mới sau khi stream đã commit.** Không thể thay status/body đã gửi; cần protocol-level error hoặc log/connection handling.
18. **Dùng advice để xử lý exception từ RouterFunction mà không kiểm tra scope.** Functional routing có cơ chế handler/error khác annotated controller.
19. **Log toàn bộ body hoặc exception detail nhạy cảm.** Giới hạn log và mask dữ liệu theo policy.
20. **Không test headers và content type.** Body đúng nhưng header sai vẫn là API response sai.

## 15. Checklist thiết kế

Trước khi tùy biến, hãy xác định:

- Ứng dụng dùng WebFlux annotated controller hay WebFlux.fn?
- Exception phát sinh ở argument resolution, controller/service, filter hay server layer?
- Đây là exception built-in của Spring hay exception nghiệp vụ?
- Có thể dùng mặc định ProblemDetail trước khi viết handler riêng không?
- Cần override một `handleXxx`, `handleExceptionInternal` hay `createResponseEntity`?
- Status và headers gốc có được bảo toàn không?
- ProblemDetail có type/title/status/detail/instance phù hợp không?
- Extension fields có ổn định và không làm lộ dữ liệu nhạy cảm không?
- Có cần MessageSource/i18n hoặc ErrorResponse interceptor không?
- Spring Boot có bật `spring.webflux.problemdetails.enabled` và đăng ký handler khác không?
- Response đã commit chưa? Có thể còn thay đổi status/body không?
- Đã test WebTestClient qua embedded server, validation, custom exception và headers chưa?

**Ghi nhớ:** `ResponseEntityExceptionHandler` là nền tảng reactive cho exception handling của annotated controllers. Override `handleXxx` để xử lý một loại lỗi, `handleExceptionInternal` cho chính sách chung, và `createResponseEntity` cho metadata ở bước cuối. Dùng `ProblemDetail` theo RFC 9457, giữ status/headers hợp lý, thêm custom field an toàn, dùng `@ExceptionHandler` cho lỗi nghiệp vụ và kiểm tra phạm vi khi làm việc với WebFlux.fn, filter hoặc Spring Boot auto-configuration.

## Tài liệu tham khảo

- Spring Framework — [Error Responses in WebFlux: ProblemDetail, ErrorResponse, ResponseEntityExceptionHandler](https://docs.spring.io/spring/reference/web/webflux/ann-rest-exceptions.html).
- Spring Framework — [ResponseEntityExceptionHandler Javadoc (Reactive WebFlux)](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html).
- Spring Framework — [WebFlux Controller Exception Handling](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-exceptions.html).
- Spring Boot — [Reactive Web Applications and Problem Details configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html).
- IETF — [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html).
