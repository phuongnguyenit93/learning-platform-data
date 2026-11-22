# @ExceptionHandler, @ControllerAdvice và phạm vi bắt lỗi

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Lỗi HTTP

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cách Spring WebFlux chuyển exception phát sinh trong controller hoặc reactive publisher thành HTTP response.
2. Dùng `@ExceptionHandler` trong controller để xử lý lỗi cục bộ.
3. Dùng `@ControllerAdvice` và `@RestControllerAdvice` để xử lý lỗi dùng chung, đồng thời giới hạn phạm vi theo package, annotation hoặc loại controller.
4. Điều khiển thứ tự advice bằng `@Order` và hiểu cách Spring chọn handler phù hợp trong exception/cause chain.
5. Trả `ResponseEntity`, `ProblemDetail` hoặc reactive return type với status và error body nhất quán.
6. Phân biệt lỗi từ controller, WebFilter, functional endpoint, codec và Spring Security để chọn đúng ranh giới xử lý.
7. Kiểm thử lỗi nghiệp vụ, lỗi đầu vào và lỗi ngoài dự kiến bằng `WebTestClient` mà không làm lộ thông tin nội bộ.

## 1. Exception trở thành HTTP response như thế nào?

Một request WebFlux đi qua server adapter, WebFilter chain, handler mapping và controller. Khi controller trả `Mono<T>` hoặc `Flux<T>`, việc xử lý tiếp tục trong reactive pipeline. Nếu pipeline phát `onError`, Spring có thể chuyển exception đó vào cơ chế xử lý exception của annotated controller.

`@ExceptionHandler` đánh dấu method có thể xử lý loại exception nhất định. Method có thể nằm ngay trong controller hoặc trong một bean advice dùng chung. Sau khi chọn method, Spring xử lý return value của nó theo cơ chế return value handler thông thường để tạo response.

```text
HTTP request
     |
     v
WebFilter chain
     |
     v
Controller method
     |
     +---- publisher thành công ----> encode body ----> HTTP response
     |
     +---- throw exception / onError
                    |
                    v
       Exception handler resolution
                    |
           +--------+--------+
           |                 |
           v                 v
   @ExceptionHandler    ControllerAdvice
   trong controller    theo thứ tự @Order
           |                 |
           +--------+--------+
                    |
                    v
        ResponseEntity / ProblemDetail
                    |
                    v
             HTTP error response
```

Có hai thời điểm phát sinh lỗi cần phân biệt:

- **Exception đồng bộ:** method controller ném exception ngay khi được gọi, trước khi trả publisher.
- **Reactive error:** method trả publisher, nhưng publisher phát `onError` khi được tiêu thụ.

Ví dụ reactive error:

```java
@GetMapping("/orders/{id}")
public Mono<Order> find(@PathVariable long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)));
}
```

Exception không nhất thiết phải được ném bằng `throw` trong controller. Khi publisher phát lỗi, WebFlux vẫn có thể chuyển lỗi đến exception handler của controller/advice. Điều kiện quan trọng là publisher thuộc request lifecycle và được framework tiêu thụ.

Không gọi `subscribe()` riêng trong controller để chạy công việc rồi return response khác. Subscription tách rời khiến lỗi không còn nằm trong request pipeline; `@ExceptionHandler` không thể xử lý lỗi đã bị tách khỏi lifecycle đó.

## 2. @ExceptionHandler trong controller: xử lý cục bộ

`@ExceptionHandler` có thể đặt trên method cùng controller với endpoint. Method đó xử lý exception phát sinh từ các handler method trong controller tương ứng.

```java
@RestController
@RequestMapping("/exports")
public class ExportController {

    @GetMapping("/{id}")
    public Mono<String> get(@PathVariable long id) {
        if (id == 0) {
            return Mono.error(new ExportLockedException(id));
        }
        return Mono.just("export-" + id);
    }

    @ExceptionHandler(ExportLockedException.class)
    public ResponseEntity<ApiError> handleLocked(
            ExportLockedException exception) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "EXPORT_LOCKED",
                        "Export is currently locked"));
    }

    public record ApiError(String code, String message) {}
}
```

Đây là **đoạn minh họa controller**; `ExportLockedException` là exception nghiệp vụ do ứng dụng định nghĩa. Khi `GET /exports/0` phát lỗi, method `handleLocked` trong cùng controller có thể chuyển lỗi thành HTTP 409 Conflict.

Handler cục bộ phù hợp với quy tắc chỉ có ý nghĩa trong một controller. Ví dụ controller xuất báo cáo có thể xử lý `ExportLockedException` theo cách riêng mà các controller khác không cần biết.

Nếu nhiều controller phải lặp lại cùng cách chuyển exception thành response, code sẽ phân tán. Khi quy tắc thực sự dùng chung, chuyển nó vào controller advice.

### 2.1. Một method xử lý nhiều exception

`@ExceptionHandler` nhận một hoặc nhiều exception class:

```java
@ExceptionHandler({
        InvalidOrderException.class,
        IllegalArgumentException.class
})
public ResponseEntity<ApiError> handleInvalid(Exception exception) {
    return ResponseEntity.badRequest()
            .body(new ApiError(
                    "INVALID_REQUEST",
                    "Request parameters are invalid"));
}
```

Nếu không khai báo class trong annotation, Spring có thể suy ra loại exception từ tham số exception của method. Khai báo rõ loại lỗi thường giúp người đọc thấy ngay phạm vi xử lý.

Không gom các exception có semantics khác nhau vào một method chỉ để giảm số dòng. Lỗi xác thực có thể là 401/403, tài nguyên không tồn tại là 404, dữ liệu xung đột là 409 và lỗi nội bộ là 500.

### 2.2. Exception trong cause chain

Một exception có thể bọc exception khác:

```java
throw new OrderProcessingException(
        "Could not load order",
        new OrderNotFoundException(orderId));
```

Spring có thể xét cả exception được ném ra và các cause lồng bên trong khi tìm handler. Điều này hữu ích khi service/repository bọc lỗi kỹ thuật bằng exception nghiệp vụ.

Không nên dựa vào cause matching để thay thế thiết kế exception rõ ràng. Nếu wrapper có nghĩa là lỗi hệ thống, bắt cause bên trong rồi trả 404 có thể che mất ngữ cảnh. Hãy quyết định exception nào đại diện cho contract HTTP của API.

## 3. @ControllerAdvice: xử lý exception dùng chung

`@ControllerAdvice` là component chứa các method xử lý exception, binder hoặc model attribute có thể áp dụng cho nhiều controller. Mặc định, advice có phạm vi rộng tới các annotated controller phù hợp trong application context.

```java
@ControllerAdvice
public class GlobalExceptionAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(
            OrderNotFoundException exception) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        "Order was not found"));
    }
}
```

Đây là **đoạn minh họa**. Method trong advice xử lý lỗi từ nhiều controller mà không cần mỗi controller tự khai báo handler. Điều này giúp API thống nhất status, error code, logging và cấu trúc body.

`@ControllerAdvice` không tự có nghĩa mọi return value đều là response body. Nếu muốn DTO được serialize, dùng `@ResponseBody` trên method/class hoặc dùng `@RestControllerAdvice`.

### 3.1. @RestControllerAdvice

`@RestControllerAdvice` là tổ hợp tiện dụng của `@ControllerAdvice` và `@ResponseBody`. Nó phù hợp khi advice chủ yếu tạo JSON/XML hoặc representation khác qua message converter:

```java
@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            OrderNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        "Order was not found"));
    }
}
```

Với `@RestControllerAdvice`, body của `ResponseEntity` được encode theo content negotiation và codec phù hợp. Không cần tự gọi `response.writeWith` cho JSON thông thường.

### 3.2. Chọn phạm vi advice

Có thể giới hạn advice bằng selector:

| Thuộc tính | Chọn controller theo |
| --- | --- |
| `basePackages` / `value` | Tên package hoặc package con. |
| `basePackageClasses` | Package chứa các class marker được chỉ định. |
| `assignableTypes` | Controller thuộc type hoặc subtype cụ thể. |
| `annotations` | Controller được gắn annotation cụ thể. |

Ví dụ chỉ áp dụng cho controller trong package order:

```java
@RestControllerAdvice(basePackages = "demo.orders")
public class OrderExceptionAdvice {
    // @ExceptionHandler methods
}
```

Hoặc chọn theo annotation:

```java
@RestControllerAdvice(annotations = PublicApiController.class)
public class PublicApiExceptionAdvice {
    // @ExceptionHandler methods
}
```

Các selector có thể kết hợp; khi có nhiều selector, điều kiện phù hợp được kết hợp theo logic OR. Thêm selector vì vậy có thể mở rộng phạm vi hơn dự định. Hãy xác định rõ controller nào sẽ nhận advice, đặc biệt trong ứng dụng chia package theo domain hoặc API version.

## 4. Thứ tự advice và cách Spring chọn handler

Một ứng dụng có thể có nhiều advice: advice cho lỗi nghiệp vụ, validation, API public hoặc package riêng. Khi nhiều advice cùng có khả năng xử lý exception, thứ tự rất quan trọng.

`@Order` hoặc `Ordered` xác định thứ tự ưu tiên:

```java
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiSpecificAdvice {
    // Các handler cần ưu tiên
}

@RestControllerAdvice
@Order(Ordered.LOWEST_PRECEDENCE)
public class FallbackAdvice {
    // Handler dự phòng
}
```

Giá trị order nhỏ hơn có độ ưu tiên cao hơn; `HIGHEST_PRECEDENCE` được xét trước `LOWEST_PRECEDENCE`. Nếu không khai báo, advice dùng thứ tự mặc định theo cơ chế sắp xếp bean của Spring.

Một số quy tắc hữu ích:

1. Handler cục bộ trong controller được xét trước global controller advice.
2. Trong một controller/advice, Spring ưu tiên exception type phù hợp cụ thể hơn khi phân giải handler.
3. Spring có thể xét cả exception cause chain; handler có thể khớp exception bọc hoặc cause bên trong.
4. Giữa các global advice, thứ tự advice ảnh hưởng advice nào được xét trước. Một advice ưu tiên cao có handler khớp cause có thể được chọn trước handler khớp root exception ở advice ưu tiên thấp hơn.
5. Handler tổng quát như `@ExceptionHandler(Exception.class)` nên nằm trong advice dự phòng có độ ưu tiên thấp.

Không tạo nhiều advice có cùng phạm vi, cùng order và các handler chồng lấn mà không có lý do. Khi quy tắc chọn handler khó dự đoán, hãy thu hẹp selector hoặc thiết kế phân cấp exception rõ ràng.

## 5. Tham số và kiểu trả về của exception handler

Method `@ExceptionHandler` trong WebFlux có thể nhận exception cùng thông tin request cần thiết:

```java
@ExceptionHandler(OrderNotFoundException.class)
public Mono<ResponseEntity<ApiError>> handle(
        OrderNotFoundException exception,
        ServerWebExchange exchange) {

    String path = exchange.getRequest().getPath().value();

    return Mono.just(ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                    "ORDER_NOT_FOUND",
                    "Order was not found at " + path)));
}
```

Các tham số thường dùng gồm exception được xử lý, `ServerWebExchange`, `ServerHttpRequest` và `ServerHttpResponse` cùng các argument được WebFlux hỗ trợ. Chỉ nhận dữ liệu cần thiết; tránh đưa toàn bộ request body vào log hoặc response.

Return type có thể là:

- `ResponseEntity<T>` để kiểm soát status, headers và body.
- `Mono<ResponseEntity<T>>` khi tạo error response cần reactive work.
- `ProblemDetail` hoặc `ErrorResponse` theo cơ chế error response của Spring.
- DTO hoặc `Mono<DTO>` khi status mặc định phù hợp.
- `Mono<Void>` khi method hoàn tất response theo API được hỗ trợ.

Với API thông thường, `ResponseEntity<ApiError>` hoặc `ProblemDetail` dễ đọc. Nếu error body cần gọi dịch vụ bất đồng bộ, trả `Mono<...>` và compose publisher. Không gọi `block()` trong exception handler.

## 6. Thiết kế HTTP error response

### 6.1. ResponseEntity và error DTO

Một error DTO có thể chứa mã ổn định, thông điệp công khai và đường dẫn request:

```java
public record ApiError(
        String code,
        String message,
        String path) {}
```

Handler:

```java
@ExceptionHandler(OrderNotFoundException.class)
public ResponseEntity<ApiError> handleNotFound(
        OrderNotFoundException exception,
        ServerWebExchange exchange) {

    ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            "Order was not found",
            exchange.getRequest().getPath().value());

    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
}
```

`code` nên ổn định để client xử lý bằng logic; `message` dành cho người đọc và có thể được dịch; `path` giúp xác định endpoint gây lỗi. Không trả raw exception message nếu nó có thể chứa SQL, hostname nội bộ, token hoặc dữ liệu cá nhân.

### 6.2. ProblemDetail và RFC 9457

Spring Framework 6 hỗ trợ `ProblemDetail` theo chuẩn RFC 9457. Representation này có các thuộc tính như `type`, `title`, `status`, `detail` và `instance`; ứng dụng có thể thêm extension property.

Ví dụ:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Order was not found");

problem.setTitle("Order not found");
problem.setProperty("code", "ORDER_NOT_FOUND");

return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
```

Với WebFlux, Spring có thể serialize `ProblemDetail` qua message converter phù hợp. Dùng `ProblemDetail` nếu muốn contract lỗi theo chuẩn chung; dùng DTO riêng nếu API đã có schema ổn định. Không đưa stack trace hoặc exception class name vào `detail` công khai.

### 6.3. @ResponseStatus và ResponseStatusException

Với lỗi đơn giản có status cố định, có thể gắn `@ResponseStatus` lên exception class:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(String id) {
        super("Customer was not found");
    }
}
```

Hoặc phát `ResponseStatusException` trong pipeline:

```java
return repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Customer was not found")));
```

Hai cách này hữu ích khi chỉ cần ánh xạ status. Nếu API cần error code, body chuẩn, logging hoặc mapping dùng chung, `@RestControllerAdvice` thường dễ quản lý hơn. Kiểm soát thông điệp đưa ra ngoài; exception message nội bộ không phải lúc nào cũng phù hợp cho client.

## 7. Những exception WebFlux thường gặp

Ngoài exception nghiệp vụ, WebFlux và Spring Security có thể phát exception từ các bước xử lý HTTP khác nhau.

| Exception/nhóm lỗi | Tình huống thường gặp | HTTP status thường dùng |
| --- | --- | --- |
| `WebExchangeBindException` | DTO body hoặc model attribute vi phạm Bean Validation | 400 Bad Request |
| `HandlerMethodValidationException` | Constraint trên controller method parameter/return value | 400 hoặc 5xx tùy vị trí và loại lỗi |
| `ServerWebInputException` | Input không đọc/giải mã được hoặc request body không phù hợp | 400 Bad Request |
| `UnsupportedMediaTypeStatusException` | Content-Type không được hỗ trợ | 415 Unsupported Media Type |
| `NotAcceptableStatusException` | Không có representation phù hợp với Accept | 406 Not Acceptable |
| `ResponseStatusException` | Ứng dụng chủ động gắn status cho exception | Status được chỉ định |
| `AccessDeniedException` | Người dùng đã xác thực nhưng không có quyền | Thường 403 Forbidden |
| `AuthenticationException` | Xác thực thất bại | Thường 401 Unauthorized |

Đây là nhóm lỗi minh họa, không phải bảng thay thế contract của từng endpoint. Một số exception được framework xử lý sẵn. Khi muốn tùy chỉnh lỗi built-in, có thể kế thừa `ResponseEntityExceptionHandler` thuộc package WebFlux `org.springframework.web.reactive.result.method.annotation` và override hook phù hợp với phiên bản Spring đang dùng.

Không map tất cả exception thành 400. Lỗi decode/validation là lỗi request; lỗi database, bug hoặc dependency outage thường là lỗi server. Trả sai status khiến client retry sai cách và làm metric vận hành mất ý nghĩa.

### 7.1. Validation và lỗi đọc body

Với annotated controller, validation DTO có thể phát `WebExchangeBindException`; method validation có thể phát `HandlerMethodValidationException`. JSON sai cú pháp hoặc không chuyển đổi được sang kiểu Java thường thuộc nhóm input/decoding như `ServerWebInputException`.

Nếu API muốn một error schema thống nhất, hãy xử lý từng loại exception và chuyển chúng về cùng cấu trúc response. Giữ status và phân biệt code lỗi để client biết nên sửa payload, đăng nhập, xin quyền hay thử lại sau.

### 7.2. Spring Security

Exception xác thực/ủy quyền thường được xử lý trong Spring Security WebFilter chain qua authentication entry point và access denied handler. `@ControllerAdvice` không phải điểm xử lý duy nhất cho security failure, đặc biệt khi lỗi xảy ra trước khi request đến controller.

Hãy cấu hình reactive security error handling ở đúng security boundary. Không dùng advice tổng quát để vô tình biến lỗi 401/403 thành 500 hoặc làm mất header challenge cần thiết.

## 8. Phạm vi thực tế: controller, filter và functional endpoint

### 8.1. @ControllerAdvice xử lý controller nào?

Controller advice áp dụng cho annotated controllers phù hợp với selector. Handler cục bộ trong controller được ưu tiên trước advice. Một global advice có thể áp dụng cho nhiều controller, nhưng không nên mặc định nó là nơi bắt mọi exception của server.

Exception từ `WebFilter` có thể phát sinh trước khi handler/controller được gọi. Filter có thể xử lý lỗi của chain mà nó bao quanh bằng `onErrorResume` nếu đó là concern của filter:

```java
return chain.filter(exchange)
        .onErrorResume(UpstreamUnavailableException.class, error ->
                writeServiceUnavailable(exchange));
```

Đây là **đoạn minh họa WebFilter**; `writeServiceUnavailable` phải trả `Mono<Void>` và kiểm tra response chưa commit. Không gọi `subscribe()` trong nhánh phục hồi.

### 8.2. Functional endpoint không dùng @ControllerAdvice như annotated controller

WebFlux.fn dùng `RouterFunction`, `HandlerFunction` và `ServerRequest`. Nó không đi qua annotated controller exception handler resolution theo cùng cách `@RestController`. Vì vậy, không nên kỳ vọng `@ExceptionHandler` trong `@RestControllerAdvice` tự động xử lý mọi exception từ `HandlerFunction`.

Với functional endpoint, có thể xử lý lỗi trong handler bằng `onErrorResume` hoặc gắn `HandlerFilterFunction` để bao quanh các handler trong router:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> errorFilter =
        (request, next) -> next.handle(request)
                .onErrorResume(OrderNotFoundException.class, error ->
                        ServerResponse.notFound().build());
```

Đây là **đoạn minh họa**; cần import functional server API và gắn filter vào router bằng `.filter(errorFilter)`. Với lỗi ở phạm vi rộng hơn của WebFlux server, có thể triển khai `WebExceptionHandler` nhận `ServerWebExchange` và `Throwable`, đồng thời trả `Mono<Void>`.

### 8.3. WebExceptionHandler là ranh giới rộng hơn

`WebExceptionHandler` tham gia xử lý exception trong WebFlux WebHandler chain. Nó phù hợp cho lỗi ở tầng server/filter hoặc cơ chế xử lý lỗi toàn cục cần bao phủ cả functional endpoint. Khi tự triển khai, cần:

- Kiểm tra `exchange.getResponse().isCommitted()` trước khi đổi status hoặc ghi body.
- Chọn đúng status và representation.
- Return publisher ghi response để lifecycle được quản lý.
- Nếu không xử lý được exception, truyền lỗi tiếp theo theo contract của `WebExceptionHandler`.
- Đặt order phù hợp để không xung đột với security hoặc error handler mặc định.

Spring Boot WebFlux cũng có error handling ở tầng server thông qua `ErrorWebExceptionHandler`/`DefaultErrorWebExceptionHandler`. Chỉ thay thế khi cần error contract ở phạm vi server; với lỗi nghiệp vụ của annotated controller, controller advice thường đơn giản hơn.

## 9. Response đã commit và lỗi trong streaming

Một response chỉ có thể đổi status/header trước khi commit. Khi server đã gửi response headers hoặc bắt đầu ghi body, không thể quay lại đổi HTTP 200 thành 500 và gửi JSON error body mới như thể response chưa bắt đầu.

Ví dụ một `Flux<Event>` đã stream nhiều event rồi phát `onError`. Client đã nhận status và một phần body. Exception handler không thể xóa các byte đã gửi. Với SSE hoặc streaming protocol, nếu cần biểu diễn lỗi giữa luồng, hãy thiết kế event lỗi trong protocol hoặc kết thúc stream theo contract đã thống nhất.

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<Event> events() {
    return eventService.stream()
            .onErrorResume(error ->
                    Flux.just(Event.error("STREAM_FAILED")));
}
```

Đây là **đoạn minh họa**. Cách biến lỗi thành event chỉ phù hợp khi schema stream định nghĩa event lỗi. Không nuốt lỗi âm thầm hoặc phát nội dung exception nội bộ cho client.

Cancellation cũng không đồng nghĩa với exception. Client có thể ngắt kết nối hoặc operator có thể hủy upstream; cancellation là tín hiệu lifecycle riêng, không nên tự động map thành HTTP 500.

## 10. Chương trình Spring Boot 3.3.5 chạy được

Ví dụ dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5** và `spring-boot-starter-webflux`. Controller phát lỗi qua reactive publisher; `@RestControllerAdvice` chuyển exception thành status và JSON body có cấu trúc.

Cấu trúc:

```text
webflux-exception-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ApiExceptionDemoApplication.java
    │   ├── OrderController.java
    │   ├── OrderExceptions.java
    │   └── ApiExceptionAdvice.java
    └── test/java/demo/
        └── OrderControllerTest.java
```

### 10.1. pom.xml

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
    <artifactId>webflux-exception-demo</artifactId>
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

### 10.2. ApiExceptionDemoApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiExceptionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiExceptionDemoApplication.class, args);
    }
}
```

### 10.3. OrderExceptions.java

```java
package demo;

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(long id) {
        super("Order " + id + " was not found");
    }
}

class InvalidOrderIdException extends RuntimeException {
    InvalidOrderIdException(long id) {
        super("Order id must be positive: " + id);
    }
}
```

Hai exception package-private cùng package với controller và advice nên không cần tạo thêm public class cho từng exception.

### 10.4. OrderController.java

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    public record Order(long id, String status) {}

    @GetMapping("/{id}")
    public Mono<Order> find(@PathVariable long id) {
        if (id <= 0) {
            return Mono.error(new InvalidOrderIdException(id));
        }

        if (id == 404) {
            return Mono.error(new OrderNotFoundException(id));
        }

        if (id == 500) {
            return Mono.error(
                    new IllegalStateException("simulated internal failure"));
        }

        return Mono.just(new Order(id, "READY"));
    }
}
```

Các nhánh lỗi được phát dưới dạng `Mono.error` để mô phỏng reactive error signal. ID 404 đại diện đơn hàng không tồn tại; ID 0 hoặc âm là input không hợp lệ; ID 500 mô phỏng lỗi ngoài dự kiến để kiểm tra fallback 500.

### 10.5. ApiExceptionAdvice.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

@RestControllerAdvice
public class ApiExceptionAdvice {
    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionAdvice.class);

    public record ApiError(
            String code,
            String message,
            String path) {}

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            OrderNotFoundException exception,
            ServerWebExchange exchange) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        "Order was not found",
                        exchange.getRequest().getPath().value()));
    }

    @ExceptionHandler(InvalidOrderIdException.class)
    public ResponseEntity<ApiError> invalidId(
            InvalidOrderIdException exception,
            ServerWebExchange exchange) {

        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_ORDER_ID",
                        "Order id must be positive",
                        exchange.getRequest().getPath().value()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> unexpected(
            Exception exception,
            ServerWebExchange exchange) {

        String path = exchange.getRequest().getPath().value();
        log.error("Unhandled request failure at {}", path, exception);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ApiError(
                        "INTERNAL_ERROR",
                        "An unexpected error occurred",
                        path));
    }
}
```

Advice có hai handler chuyên biệt và một handler dự phòng. Response không trả message nội bộ từ exception tổng quát; chi tiết đầy đủ chỉ được ghi vào log server. Ứng dụng thật nên bổ sung request/correlation ID và quy tắc log phù hợp để truy vết.

### 10.6. Chạy thử

Tại thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Request thành công:

```bash
curl -i http://localhost:8080/api/orders/12
```

Kết quả là HTTP **200 OK**:

```json
{
  "id": 12,
  "status": "READY"
}
```

Đơn hàng không tồn tại:

```bash
curl -i http://localhost:8080/api/orders/404
```

Kết quả là HTTP **404 Not Found**:

```json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Order was not found",
  "path": "/api/orders/404"
}
```

ID không hợp lệ:

```bash
curl -i http://localhost:8080/api/orders/0
```

Kết quả là HTTP **400 Bad Request**:

```json
{
  "code": "INVALID_ORDER_ID",
  "message": "Order id must be positive",
  "path": "/api/orders/0"
}
```

Lỗi ngoài dự kiến:

```bash
curl -i http://localhost:8080/api/orders/500
```

Kết quả là HTTP **500 Internal Server Error**:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "An unexpected error occurred",
  "path": "/api/orders/500"
}
```

Log server chứa stack trace của lỗi mô phỏng; client chỉ nhận error contract đã kiểm soát.

## 11. Kiểm thử bằng WebTestClient

`WebTestClient` kiểm tra status và body mà HTTP client nhận, xác nhận advice được gọi khi reactive publisher phát lỗi.

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderControllerTest {
    @Autowired
    WebTestClient client;

    @Test
    void successReturnsOrder() {
        client.get()
                .uri("/api/orders/12")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(12)
                .jsonPath("$.status").isEqualTo("READY");
    }

    @Test
    void missingOrderReturnsNotFound() {
        client.get()
                .uri("/api/orders/404")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND")
                .jsonPath("$.path").isEqualTo("/api/orders/404");
    }

    @Test
    void invalidIdReturnsBadRequest() {
        client.get()
                .uri("/api/orders/0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_ORDER_ID");
    }

    @Test
    void unexpectedFailureDoesNotExposeInternalMessage() {
        client.get()
                .uri("/api/orders/500")
                .exchange()
                .expectStatus().is5xxServerError()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INTERNAL_ERROR")
                .jsonPath("$.message")
                    .isEqualTo("An unexpected error occurred");
    }
}
```

Chạy test:

```bash
mvn test
```

Bốn test kiểm tra response thành công, lỗi 404, lỗi 400 và fallback 500. Test tập trung vào HTTP contract thay vì chỉ gọi method advice trực tiếp.

## 12. Lỗi thường gặp và cách xử lý

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đặt `@ExceptionHandler` trong controller A và mong nó xử lý controller B | Handler cục bộ chỉ gắn với controller sở hữu nó | Dùng `@ControllerAdvice`/`@RestControllerAdvice` nếu cần dùng chung. |
| Dùng `@ControllerAdvice` nhưng quên `@ResponseBody` | DTO có thể bị diễn giải theo cơ chế view/controller thông thường | Dùng `@RestControllerAdvice` hoặc thêm `@ResponseBody`. |
| Nghĩ advice mặc định bắt mọi exception của toàn server | Lỗi filter, security hoặc functional route có thể ở ngoài controller handler resolution | Chọn đúng ranh giới WebFilter, security handler, HandlerFilterFunction hoặc WebExceptionHandler. |
| Tạo nhiều advice chồng phạm vi mà không khai báo order | Handler được chọn khó dự đoán | Thu hẹp selector và dùng `@Order` rõ ràng. |
| Đặt handler `Exception.class` ở advice ưu tiên cao | Có thể che handler chuyên biệt ở advice khác | Để fallback tổng quát ở ưu tiên thấp. |
| Chỉ bắt root exception và bỏ qua wrapper/cause | Lỗi được bọc có thể không đi vào handler mong muốn | Thiết kế exception chain rõ và kiểm tra cause matching. |
| Map mọi exception thành HTTP 400 | Lỗi server bị coi là lỗi client | Phân biệt 4xx và 5xx theo nguyên nhân. |
| Trả `exception.getMessage()` cho mọi lỗi | Có thể lộ SQL, host, token hoặc thông tin nội bộ | Dùng message công khai và log chi tiết phía server. |
| Gọi `block()` trong exception handler | Chặn event-loop | Trả/compose `Mono` hoặc dữ liệu có sẵn. |
| Gọi `subscribe()` để ghi log hoặc gửi response | Tách lỗi khỏi request lifecycle | Dùng `doOnError` cho side effect hoặc `onErrorResume` để phục hồi. |
| Dùng `@RestControllerAdvice` để bắt lỗi mọi functional endpoint | Functional route không đi qua annotated controller exception resolution | Xử lý trong handler/filter hoặc `WebExceptionHandler`. |
| Đổi status sau khi response commit | Client đã nhận status/header cũ | Xử lý lỗi trước commit hoặc định nghĩa error event cho stream. |
| Nuốt exception rồi trả 200 | Client nghĩ thao tác thành công | Chỉ phục hồi khi có kết quả hợp lệ và status đúng. |
| Bắt security exception trong advice nhưng bỏ qua security chain | Có thể mất status/header challenge hoặc thứ tự xử lý | Cấu hình authentication entry point/access denied handler reactive. |
| Gộp validation, decoding và lỗi hệ thống vào cùng một code | Client không biết cách sửa hoặc có nên retry | Giữ error code riêng cho từng nhóm lỗi. |
| Log cùng exception ở mọi tầng | Log trùng và khó truy vết | Chọn một boundary chịu trách nhiệm log, gắn correlation ID. |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `@ExceptionHandler` đặt trong controller xử lý lỗi ở phạm vi nào?  
**Đáp án:** Nó xử lý exception từ handler methods thuộc controller đó. Muốn dùng chung cho nhiều controller, dùng controller advice.

**Câu 2.** `@ControllerAdvice` và `@RestControllerAdvice` khác nhau thế nào?  
**Đáp án:** `@RestControllerAdvice` là tổ hợp của `@ControllerAdvice` và `@ResponseBody`, phù hợp với error response body được serialize.

**Câu 3.** Có thể giới hạn advice chỉ cho một package không?  
**Đáp án:** Có, dùng `basePackages`/`value`; cũng có thể chọn theo package marker class, controller type hoặc annotation.

**Câu 4.** `@Order(Ordered.HIGHEST_PRECEDENCE)` có ý nghĩa gì?  
**Đáp án:** Advice có độ ưu tiên cao được xét trước advice có order thấp hơn; giá trị order nhỏ hơn có ưu tiên cao hơn.

**Câu 5.** Nếu controller trả `Mono.error(...)`, `@ExceptionHandler` có xử lý được không?  
**Đáp án:** Có, nếu reactive error thuộc request lifecycle của annotated controller và exception khớp handler.

**Câu 6.** Vì sao không nên đặt `@ExceptionHandler(Exception.class)` ở advice ưu tiên cao?  
**Đáp án:** Handler tổng quát có thể bắt lỗi trước advice chuyên biệt và làm mất status/error contract cụ thể.

**Câu 7.** `ProblemDetail` dùng để làm gì?  
**Đáp án:** Nó biểu diễn HTTP error theo RFC 9457 với các thuộc tính chuẩn như type, title, status, detail và instance, có thể mở rộng thêm property.

**Câu 8.** `@ControllerAdvice` có tự bắt lỗi từ `WebFilter` không?  
**Đáp án:** Không nên dựa vào nó. Filter chạy ở ranh giới trước/ngoài annotated controller; dùng reactive filter error handling hoặc WebExceptionHandler phù hợp.

**Câu 9.** Functional endpoint có được xử lý tự động bởi `@ExceptionHandler` trong controller advice không?  
**Đáp án:** Không theo cơ chế annotated controller. Dùng `onErrorResume`, `HandlerFilterFunction` hoặc `WebExceptionHandler`.

**Câu 10.** Điều gì xảy ra nếu Flux streaming phát lỗi sau khi response commit?  
**Đáp án:** Không thể đổi status/header đã gửi hoặc thay body bằng JSON error response mới. Giao thức streaming cần định nghĩa event lỗi hoặc cách kết thúc stream.

## Ghi nhớ

- `@ExceptionHandler` trong controller xử lý lỗi cục bộ; `@ControllerAdvice`/`@RestControllerAdvice` chia sẻ cách xử lý trên các annotated controller phù hợp.
- `@RestControllerAdvice` tự áp dụng response body semantics; dùng selector để giới hạn package, controller type hoặc annotation.
- `@Order` điều khiển thứ tự global advice. Handler cục bộ được xét trước; exception type cụ thể và cause chain ảnh hưởng tới lựa chọn.
- Reactive error từ `Mono`/`Flux` vẫn có thể đi vào exception handler nếu publisher thuộc request lifecycle; không tự `subscribe()` hoặc `block()`.
- Dùng `ResponseEntity` hoặc `ProblemDetail` để trả status/body nhất quán. Không lộ exception message hoặc stack trace nội bộ.
- Controller advice dành cho annotated controllers. Functional endpoint, WebFilter và Spring Security có ranh giới xử lý riêng; lỗi sau response commit không thể thay status đã gửi.

### Tài liệu tham khảo

1. [Spring Framework – WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): exception handling, `@ExceptionHandler`, controller advice và RFC 9457.
2. [Spring Framework – @ControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-advice.html): phạm vi advice, selector, thứ tự và exception matching.
3. [Spring Framework – WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): `HandlerFunction`, router filter và functional error handling.
4. [Spring Framework – WebExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebExceptionHandler.html): ranh giới xử lý exception ở WebFlux WebHandler chain.
5. [Spring Framework – ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html): xử lý exception built-in cho annotated WebFlux controllers.
6. [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): cấu trúc lỗi HTTP chuẩn hóa.
7. [Spring Security – Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html): xử lý authentication và access denied trong reactive security chain.
