# Lỗi xảy ra trước và sau khi phản hồi đã được gửi trong Spring WebFlux

## 1. Vì sao thời điểm xảy ra lỗi lại quan trọng?

Trong một ứng dụng Spring WebFlux, request được xử lý theo pipeline reactive. Controller hoặc functional handler có thể trả về Mono/Flux; dữ liệu được ghi dần xuống HTTP response khi publisher phát tín hiệu.

Điều này tạo ra một khác biệt quan trọng: lỗi xảy ra **trước khi response được commit** có thể được chuyển thành một HTTP error response mới; lỗi xảy ra **sau khi response đã commit** thường không thể thay status, headers hoặc body đã gửi. Server chỉ có thể kết thúc stream/connection, ghi log và thực hiện cleanup phù hợp.

Ví dụ:

- Một service ném lỗi trước khi controller ghi bất kỳ byte nào: server vẫn có thể trả **500 Internal Server Error** cùng JSON mô tả lỗi.
- Một endpoint SSE đã gửi hai event rồi publisher phát onError: status **200 OK** và các event đã gửi không thể bị thu hồi. Server không thể thay response đó bằng JSON 500; client có thể nhận stream bị kết thúc bất thường.
- Một endpoint chủ động chuyển lỗi nghiệp vụ thành event SSE tên error rồi complete: status vẫn là 200, nhưng client nhận được thông điệp lỗi ở cấp ứng dụng.

Để hiểu chính xác, cần phân biệt ba mốc:

1. **Request handling bắt đầu:** server nhận request và Spring bắt đầu chạy filter/handler.
2. **Response committed:** status, headers, cookies và phần body đầu tiên được áp dụng/ghi xuống transport. Sau mốc này, metadata HTTP không thể thay đổi.
3. **Response hoàn tất:** publisher ghi body hoàn tất và server kết thúc response bình thường.

Response có thể đã commit nhưng body vẫn đang stream. Vì vậy, khái niệm quan trọng là **committed**, không phải chỉ là "đã gửi xong toàn bộ body".

## 2. Response commit là gì?

Trong WebFlux, **ServerHttpResponse** là abstraction cho HTTP response phía server. Nó cho phép đặt status, headers, cookies và ghi body theo kiểu reactive.

Các API quan trọng:

| API | Vai trò |
| --- | --- |
| **isCommitted()** | Cho biết response đã commit hay chưa |
| **setStatusCode(status)** | Đặt HTTP status; trả false nếu status không thể đổi vì response đã commit |
| **getHeaders()** | Truy cập response headers; thay đổi chỉ có hiệu lực trước khi headers được commit |
| **addCookie(cookie)** | Thêm cookie; có thể ném IllegalStateException nếu response đã commit |
| **beforeCommit(action)** | Đăng ký hành động chạy ngay trước khi response commit |
| **writeWith(body)** | Ghi body từ Publisher<DataBuffer> |
| **writeAndFlushWith(body)** | Ghi các nhóm DataBuffer và flush sau từng nhóm |
| **setComplete()** | Hoàn tất response, kể cả response không có body |

### 2.1. Điều gì được xem là commit?

Response thường commit khi framework cần gửi status/headers và bắt đầu ghi body xuống HTTP server. Với response stream, việc commit có thể xảy ra rất sớm, chẳng hạn khi event đầu tiên được flush.

Một số tình huống:

- Controller trả JSON object nhỏ: response thường được commit khi writer bắt đầu ghi body.
- Controller trả Flux với media type streaming như text/event-stream: mỗi event có thể được flush; response commit ngay khi event đầu tiên được ghi.
- Controller trả response không có body và gọi setComplete(): response vẫn phải commit status/headers.
- Filter hoặc handler chủ động flush response: commit có thể xảy ra trước khi toàn bộ logic nghiệp vụ hoàn tất.

Thời điểm chính xác phụ thuộc message writer, server adapter và transport. Không nên suy luận chỉ từ việc method controller đã return. Hãy kiểm tra **response.isCommitted()** ở đúng điểm xử lý lỗi.

### 2.2. Sau commit, status và headers không thể thay đổi

Ví dụ:

~~~java
boolean changed = exchange.getResponse()
    .setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);

if (!changed) {
    // Response đã commit, status không thể thay đổi.
}
~~~

Nếu response đã commit, setStatusCode trả false. Thêm cookie sau commit có thể ném IllegalStateException. Body đã gửi cũng không thể bị thay thế bằng một JSON error document.

Không cố đặt status 500 sau khi đã gửi một phần response 200. Cách đó không thể sửa status trên wire và có thể tạo thêm lỗi thứ cấp.

### 2.3. beforeCommit dùng khi nào?

**beforeCommit(...)** đăng ký một hành động chạy ngay trước khi response commit. Nó hữu ích khi cần thêm header cuối cùng, correlation ID hoặc metadata mà chỉ được xác định ở giai đoạn chuẩn bị response.

Ví dụ:

~~~java
String requestId = "req-42";

exchange.getResponse().beforeCommit(() ->
    Mono.fromRunnable(() ->
        exchange.getResponse().getHeaders()
            .set("X-Request-Id", requestId)
    )
);
~~~

Hành động phải được defer đúng cách bằng Mono.defer, Mono.fromRunnable hoặc một Publisher tương ứng. Không thực hiện thay đổi headers sau khi response đã commit và không dùng beforeCommit để cố sửa response sau khi body đã bắt đầu ghi.

## 3. Lỗi trước commit: có thể tạo error response mới

Khi lỗi xảy ra trước commit, Spring vẫn có cơ hội chọn status, headers và body cho response. Đây là trường hợp phù hợp để:

- Chuyển exception thành 4xx/5xx.
- Trả JSON hoặc ProblemDetail.
- Thêm correlation ID.
- Chuẩn hóa mã lỗi và thông báo.
- Ghi log và metrics.

Lỗi có thể phát sinh ở nhiều nơi:

- Controller ném exception trước khi trả về Publisher.
- Mono/Flux phát onError trước khi writer ghi body.
- Service reactive thất bại trước khi có dữ liệu response.
- WebFilter từ chối request hoặc phát sinh lỗi.
- Handler mapping hoặc argument resolution thất bại.

Dù lỗi là synchronous hay asynchronous, nếu response chưa commit thì error handling vẫn có thể tạo response mới.

### 3.1. Dùng @ExceptionHandler trong controller

Ví dụ:

~~~java
@RestController
@RequestMapping("/api")
public class OrderController {

    @GetMapping("/orders/{id}")
    public Mono<Order> find(@PathVariable String id) {
        return orderService.findById(id)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(id)
            ));
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
        OrderNotFoundException ex
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "The requested order does not exist."
        );

        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

Đây là snippet minh họa, giả định có Order, OrderService và OrderNotFoundException. **@ExceptionHandler** xử lý lỗi phát sinh từ handler method trong phạm vi controller. Với nhiều controller, có thể đặt handler trong **@RestControllerAdvice**.

Response có thể dùng định dạng **Problem Details** theo RFC 9457:

~~~json
{
  "type": "about:blank",
  "title": "Order not found",
  "status": 404,
  "detail": "The requested order does not exist.",
  "code": "ORDER_NOT_FOUND"
}
~~~

Các field mở rộng như code có thể được thêm vào properties của ProblemDetail. Thông báo trả cho client nên ổn định và không chứa stack trace, SQL, đường dẫn nội bộ hoặc dữ liệu nhạy cảm.

### 3.2. Dùng @RestControllerAdvice cho toàn ứng dụng

~~~java
@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> handleBadInput(
        IllegalArgumentException ex
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "The request contains an invalid value."
        );

        problem.setTitle("Invalid request");
        problem.setProperty("code", "INVALID_INPUT");

        return ResponseEntity.badRequest()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

Controller advice phù hợp để chuẩn hóa lỗi cho nhiều endpoint. Có thể bổ sung handler cho exception nghiệp vụ, lỗi validation và lỗi không mong đợi.

Không nên bắt Throwable rồi biến mọi thứ thành 400. Phân loại lỗi theo contract:

- 400 cho dữ liệu request không hợp lệ.
- 401/403 cho xác thực hoặc quyền truy cập.
- 404 cho tài nguyên không tồn tại.
- 409 cho xung đột nghiệp vụ.
- 429 cho giới hạn tần suất.
- 5xx cho lỗi phía server hoặc dependency.

Không để client quyết định status tùy ý bằng cách gửi tên exception hoặc mã lỗi trong request.

### 3.3. ProblemDetail và ResponseEntityExceptionHandler

Spring Framework hỗ trợ **ProblemDetail**, **ErrorResponse** và **ErrorResponseException** theo RFC 9457. Có thể mở rộng **ResponseEntityExceptionHandler** trong một @ControllerAdvice để xử lý các exception WebFlux chuẩn và ErrorResponseException.

Với Spring Boot, thuộc tính:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

có thể bật cấu hình Problem Details cho các exception tích hợp. Khi cần ghi đè cách xử lý một exception cụ thể, phải chú ý thứ tự của ControllerAdvice để handler tùy biến được chọn trước handler auto-configured.

ProblemDetail giúp response lỗi nhất quán giữa endpoint, nhưng nó vẫn chỉ có thể được ghi khi response chưa commit.

## 4. Lỗi sau commit: không thể thay thế response

Khi response đã commit:

- Status HTTP đã được gửi.
- Headers đã được gửi.
- Cookie đã được gửi.
- Một phần hoặc toàn bộ body có thể đã được truyền.
- Framework không thể quay lại và tạo response 500 mới trên cùng exchange.

Ví dụ một stream:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: started

event: progress
data: halfway

<publisher phát onError>
<response stream kết thúc bất thường>
~~~

Client đã nhận status 200 và hai event. Nếu server cố đổi status thành 500, thay đổi đó không thể ghi đè status đã gửi.

Tùy HTTP version và server runtime, client có thể quan sát:

- Body bị thiếu so với Content-Length.
- Chunked response kết thúc mà không có terminal chunk hợp lệ.
- HTTP/2 stream bị reset.
- Client báo premature close, incomplete response hoặc lỗi đọc body.
- SSE client nhận các event đã có rồi kết nối bị đóng.

Không phải mọi transport đều thể hiện cùng một exception. Hãy xem đây là lỗi của phần stream/transport sau commit, không phải một error response mới có status khác.

### 4.1. WebExceptionHandler không thể đảo ngược commit

**WebExceptionHandler** là contract xử lý exception trong chuỗi WebFlux gồm WebFilter và WebHandler. Method có dạng:

~~~java
Mono<Void> handle(
    ServerWebExchange exchange,
    Throwable ex
);
~~~

Quy ước:

- Publisher hoàn tất bình thường: exception được xem là đã xử lý.
- Publisher phát onError: exception vẫn chưa được xử lý và được truyền tiếp.

Một handler ở tầng thấp có thể kiểm tra:

~~~java
if (exchange.getResponse().isCommitted()) {
    return Mono.error(ex);
}
~~~

Khi response đã commit, trả lại lỗi để chain tiếp tục xử lý/logging theo cơ chế runtime. Không trả Mono.empty() chỉ để che exception nếu thực tế chưa thể hoàn thành error response.

**ResponseStatusExceptionHandler** có thể ánh xạ ResponseStatusException thành status HTTP khi response chưa commit. Nếu response đã commit, lỗi vẫn unresolved và được propagate.

### 4.2. Spring Boot có error handler mặc định

Spring Boot cung cấp một **WebExceptionHandler** để xử lý lỗi theo cấu hình mặc định:

- Machine client thường nhận JSON gồm thông tin lỗi và status.
- Browser có thể nhận trang lỗi dạng HTML.
- Có thể tùy biến ErrorAttributes.
- Có thể triển khai ErrorWebExceptionHandler.
- **AbstractErrorWebExceptionHandler** giúp xây dựng error handler theo functional routing.

Các cơ chế trên phù hợp với lỗi có thể tạo response. Chúng không thể thay thế body/status đã commit. Nếu error handler mặc định cũng không thể ghi response, lỗi sẽ tiếp tục được truyền tới server runtime và được ghi nhận theo cơ chế của nó.

### 4.3. @ExceptionHandler sau commit

Một exception phát ra từ publisher mà controller đã trả về vẫn có thể đi qua cơ chế exception resolution. Tuy nhiên, nếu response đã commit, handler không thể ghi một response mới như lúc chưa commit.

Nếu có custom advice/handler, hãy kiểm tra trạng thái response:

~~~java
@ExceptionHandler(IllegalStateException.class)
public Mono<ResponseEntity<ProblemDetail>> handle(
    IllegalStateException ex,
    ServerWebExchange exchange
) {
    if (exchange.getResponse().isCommitted()) {
        return Mono.error(ex);
    }

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.INTERNAL_SERVER_ERROR,
        "The request could not be completed."
    );

    problem.setTitle("Internal server error");

    return Mono.just(
        ResponseEntity.internalServerError().body(problem)
    );
}
~~~

Đây là snippet minh họa. Khi response chưa commit, handler trả ProblemDetail. Khi đã commit, handler để exception tiếp tục propagate thay vì cố ghi JSON vào response đã gửi.

## 5. Streaming: lỗi sau event đầu tiên

Streaming là tình huống dễ thấy nhất của lỗi sau commit. Một Flux có thể phát nhiều phần tử trong một khoảng thời gian dài. Với media type streaming, server có thể flush từng phần tử để client nhận ngay.

Ví dụ SSE:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<String>> events() {
    return Flux.concat(
        Flux.just(
            ServerSentEvent.builder("started")
                .id("1")
                .event("progress")
                .build(),
            ServerSentEvent.builder("halfway")
                .id("2")
                .event("progress")
                .build()
        ),
        Flux.error(
            new IllegalStateException("simulated stream failure")
        )
    );
}
~~~

Hai event đầu có thể được flush xuống client trước khi publisher phát lỗi. Khi lỗi xảy ra, HTTP response đã có status 200 và hai event đã gửi.

### 5.1. Không thể gửi JSON error body thay cho event đã gửi

Nếu client đang đọc text/event-stream, sau hai event server không thể đột nhiên đổi Content-Type thành application/problem+json rồi ghi một JSON document như một response mới. Cùng một HTTP response chỉ có một status/header set đã commit.

Nếu muốn stream có thông báo lỗi ở cấp ứng dụng, hãy định nghĩa protocol rõ ràng và chuyển lỗi nguồn thành một event cuối:

~~~java
public Flux<ServerSentEvent<String>> recoverableEvents() {
    return Flux.concat(
        Flux.just("started", "halfway")
            .map(value -> ServerSentEvent.builder(value)
                .event("progress")
                .build()),
        Flux.<String>error(
            new IllegalStateException("source failed")
        )
    )
    .onErrorResume(ex ->
        Flux.just(
            ServerSentEvent.builder(
                "The stream could not finish. Retry the operation."
            )
            .event("error")
            .build()
        )
    );
}
~~~

Trong ví dụ này, lỗi nguồn được xử lý trước khi đi tới HTTP writer. Client nhận hai event progress, một event error rồi stream hoàn tất bình thường. HTTP status vẫn là 200 vì response đã commit.

Điều này chỉ áp dụng khi ứng dụng chủ động thiết kế event error. Nó không khôi phục được lỗi ở tầng socket, codec hoặc response writer sau khi quá trình ghi đã thất bại.

### 5.2. Định nghĩa protocol cho stream

Với SSE, có thể quy định các event:

| Event | Ý nghĩa | Client xử lý |
| --- | --- | --- |
| **progress** | Công việc đang chạy | Cập nhật giao diện/trạng thái |
| **result** | Có kết quả cuối cùng | Lưu kết quả và đóng UI |
| **error** | Công việc kết thúc với lỗi nghiệp vụ | Hiển thị thông báo, quyết định retry |
| **complete** | Công việc hoàn tất theo protocol | Kết thúc theo dõi |

Không nhầm event error của ứng dụng với HTTP status 500. Event error là dữ liệu trong một stream đã có status; HTTP status thường vẫn giữ nguyên giá trị lúc commit.

### 5.3. Với NDJSON hoặc streaming JSON

Nếu API dùng NDJSON, có thể định nghĩa một schema event chung:

~~~json
{"type":"progress","data":{"percent":50}}
{"type":"error","code":"SOURCE_FAILED","message":"The stream could not finish"}
~~~

Client đọc từng dòng và xử lý theo type. Không gửi một JSON object lỗi tùy ý nếu protocol ban đầu yêu cầu mỗi dòng có schema khác.

Với một JSON array thông thường, lỗi sau khi đã gửi dấu mở array và một số phần tử có thể khiến body không còn là JSON hợp lệ. Nếu cần stream có thể phục hồi, chọn NDJSON/SSE hoặc một framing protocol có thông điệp lỗi kết thúc rõ ràng.

## 6. Phân biệt exception, cancellation và lỗi ghi response

Không phải mọi kết thúc bất thường đều là cùng một loại lỗi.

| Trường hợp | Tín hiệu thường gặp | Ý nghĩa |
| --- | --- | --- |
| Business/service failure | onError | Logic hoặc dependency phát lỗi |
| Timeout | TimeoutException hoặc lỗi tương ứng | Một thao tác vượt thời gian cho phép |
| Client disconnect | Cancellation hoặc lỗi transport | Client ngừng nhận hoặc đóng kết nối |
| Response write failure | IOException/transport exception | Server không ghi được body xuống socket |
| Serialization failure | Codec/encoder exception | Dữ liệu không thể encode theo media type |
| Application cancellation | SignalType.CANCEL | Subscription bị hủy theo vòng đời reactive |

### 6.1. Cancellation không phải onError

Khi client đóng kết nối, publisher có thể nhận cancellation. Đây không nhất thiết là một exception nghiệp vụ. Không cố gửi một error response tới client đã ngắt kết nối.

Có thể quan sát vòng đời bằng doFinally:

~~~java
return service.stream()
    .doFinally(signalType -> {
        log.info("Stream finished with signal {}", signalType);
    });
~~~

Signal có thể là ON_COMPLETE, ON_ERROR hoặc CANCEL. Dùng nó để cleanup tài nguyên, dừng tác vụ phụ hoặc ghi metric. Không giả định doFinally luôn có nghĩa là công việc nghiệp vụ thành công.

### 6.2. Timeout trước và sau commit

Timeout xảy ra trước commit: ứng dụng có thể chuyển nó thành 504 Gateway Timeout hoặc status phù hợp theo hợp đồng API.

Timeout xảy ra sau commit: status và headers đã gửi không thể đổi. Stream bị kết thúc; client phải phát hiện body không hoàn chỉnh hoặc nhận một event lỗi theo protocol.

Đặt timeout ở đúng tầng:
- Timeout cho kết nối database/service.
- Timeout cho toàn bộ request nếu có thể xác định trước.
- Timeout cho idle stream nếu cần phát hiện nguồn bị treo.
- Heartbeat cho SSE nếu client/proxy có thể đóng kết nối nhàn rỗi.

Timeout không thay thế cancellation và không bảo đảm mọi thư viện blocking sẽ dừng ngay khi subscription bị hủy.

### 6.3. Lỗi serialization sau khi đã phát một phần

Một Flux có thể phát phần tử hợp lệ đầu tiên, rồi phần tử sau không serialize được. Nếu response đã commit, server không thể thay body bằng error JSON. Vì vậy:

- Validate/chuẩn hóa dữ liệu trước khi đưa vào stream nếu chi phí cho phép.
- Dùng DTO có schema ổn định.
- Xử lý lỗi từng phần tử nếu protocol cho phép.
- Ghi metric cho lỗi encode.
- Kiểm thử dữ liệu biên và lỗi codec.

## 7. Thiết kế error handling theo vòng đời response

Một chiến lược thực tế có thể chia thành các giai đoạn.

### 7.1. Trước khi gọi writer

- Validate request và quyền truy cập.
- Kiểm tra dependency cần thiết.
- Lấy metadata cần cho status/headers.
- Tạo correlation ID.
- Chuẩn bị response model.
- Nếu có lỗi, chuyển thành exception hoặc error response trước commit.

### 7.2. Ngay trước commit

- Đặt status cuối cùng.
- Đặt Content-Type, Cache-Control và các header khác.
- Đặt cookie nếu cần.
- Đăng ký beforeCommit cho metadata cần thêm ở bước cuối.
- Không trì hoãn các quyết định status/header tới sau khi stream bắt đầu.

### 7.3. Sau commit

- Không cố đổi status/header.
- Ghi log lỗi với request ID và thông tin stream.
- Dừng nguồn dữ liệu và giải phóng resource khi cần.
- Nếu protocol hỗ trợ, gửi một event kết thúc có schema rõ ràng trước khi publisher hoàn tất.
- Nếu lỗi ở tầng transport/write, để stream/connection kết thúc và cho client cơ chế retry/resume.
- Không ghi stack trace hoặc thông tin nội bộ vào phần body còn lại.

### 7.4. Retry phải an toàn

Client có thể retry khi stream bị ngắt, nhưng server cần xác định thao tác có idempotent hay không. Một request GET đọc dữ liệu thường có thể retry; một request POST tạo đơn hàng không nên tự động gửi lại nếu client không biết giao dịch trước đã commit hay chưa.

Với tác vụ dài, cân nhắc:
- Job ID để client truy vấn trạng thái.
- Idempotency key cho thao tác tạo.
- Event ID và replay/resume cho SSE.
- Checkpoint/offset cho stream.
- Checksum hoặc content length để phát hiện file tải dở.

Không coi việc retry kết nối là rollback cho một side effect đã thực hiện.

## 8. Ví dụ hoàn chỉnh: lỗi trước commit và sau commit

Ví dụ dùng **Java 17**, **Spring Boot 3.3.5** và Maven. Có ba endpoint:

- **/api/before-commit**: phát lỗi ngay lập tức; ControllerAdvice trả ProblemDetail 500.
- **/api/after-commit**: gửi hai SSE event rồi phát onError; client nhận status 200 và stream kết thúc bất thường.
- **/api/recovered-stream**: xử lý lỗi nguồn thành một event error cuối; stream kết thúc bình thường theo protocol ứng dụng.

Cấu trúc:

~~~text
webflux-response-error-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/responseerror/
    │   │       ├── ResponseErrorApplication.java
    │   │       ├── FailureController.java
    │   │       └── ApiExceptionAdvice.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/responseerror/
                └── FailureControllerTest.java
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-response-error-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
~~~

Spring Boot parent quản lý các phiên bản dependency tương thích. Starter WebFlux cung cấp reactive server; reactor-test hỗ trợ StepVerifier trong test.

### 8.2. Application class

Tệp **ResponseErrorApplication.java**:

~~~java
package com.example.responseerror;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResponseErrorApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ResponseErrorApplication.class,
            args
        );
    }
}
~~~

### 8.3. Controller

Tệp **FailureController.java**:

~~~java
package com.example.responseerror;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class FailureController {

    @GetMapping("/before-commit")
    public Mono<String> beforeCommit() {
        return Mono.error(
            new IllegalStateException("simulated pre-commit failure")
        );
    }

    @GetMapping(
        value = "/after-commit",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> afterCommit() {
        return Flux.concat(
            Flux.just(
                progress("1", "started"),
                progress("2", "halfway")
            ),
            Flux.<ServerSentEvent<String>>error(
                new IllegalStateException("simulated post-commit failure")
            )
        );
    }

    @GetMapping(
        value = "/recovered-stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> recoveredStream() {
        return Flux.concat(
            Flux.just(
                progress("1", "started"),
                progress("2", "halfway")
            ),
            Flux.<ServerSentEvent<String>>error(
                new IllegalStateException("simulated source failure")
            )
        )
        .onErrorResume(ex ->
            Flux.just(
                ServerSentEvent.builder(
                    "The stream could not finish. Retry the operation."
                )
                .event("error")
                .build()
            )
        );
    }

    private ServerSentEvent<String> progress(
        String id,
        String data
    ) {
        return ServerSentEvent.builder(data)
            .id(id)
            .event("progress")
            .build();
    }
}
~~~

Giải thích:

- Endpoint before-commit phát onError trước khi có body; advice có thể tạo response ProblemDetail.
- Endpoint after-commit dùng text/event-stream; hai event progress được gửi trước khi nguồn phát lỗi.
- Endpoint recovered-stream bắt lỗi của nguồn bằng onErrorResume và phát event error cuối.
- **onErrorResume** ở đây xử lý lỗi của publisher nguồn. Nếu chính thao tác ghi socket/codec thất bại, recovery trong nguồn không thể sửa lỗi transport đó.

### 8.4. ControllerAdvice

Tệp **ApiExceptionAdvice.java**:

~~~java
package com.example.responseerror;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(IllegalStateException.class)
    public Mono<ResponseEntity<ProblemDetail>> handleIllegalState(
        IllegalStateException ex,
        ServerWebExchange exchange
    ) {
        if (exchange.getResponse().isCommitted()) {
            return Mono.error(ex);
        }

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "The request could not be completed."
        );

        problem.setTitle("Internal server error");
        problem.setProperty("code", "REQUEST_FAILED");

        return Mono.just(
            ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem)
        );
    }
}
~~~

Điểm quan trọng là kiểm tra **isCommitted()**:

- Chưa commit: trả ProblemDetail với 500.
- Đã commit: trả lại lỗi để exception tiếp tục propagate; không cố ghi response thứ hai.

Thông báo client không chứa exception message nội bộ. Exception message vẫn có thể được ghi vào log ở môi trường server với request ID và chính sách bảo vệ dữ liệu phù hợp.

### 8.5. application.properties

~~~properties
spring.application.name=webflux-response-error-demo
server.port=8080
logging.level.com.example.responseerror=INFO
~~~

### 8.6. Test bằng WebTestClient và StepVerifier

Tệp **FailureControllerTest.java**:

~~~java
package com.example.responseerror;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class FailureControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void mapsFailureBeforeCommitToProblemDetail() {
        client.get()
            .uri("/api/before-commit")
            .exchange()
            .expectStatus().isEqualTo(
                HttpStatus.INTERNAL_SERVER_ERROR
            )
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON
                )
            .expectBody()
            .jsonPath("$.title")
                .isEqualTo("Internal server error")
            .jsonPath("$.status").isEqualTo(500)
            .jsonPath("$.code").isEqualTo("REQUEST_FAILED");
    }

    @Test
    void postCommitFailureTerminatesTheSseBody() {
        FluxExchangeResult<ServerSentEvent<String>> result =
            client.get()
                .uri("/api/after-commit")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM
                    )
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<String>
                    >() {}
                );

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                "progress".equals(event.event())
                    && "started".equals(event.data())
            )
            .expectNextMatches(event ->
                "progress".equals(event.event())
                    && "halfway".equals(event.data())
            )
            .expectError()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void sourceErrorCanBecomeAnApplicationLevelSseEvent() {
        FluxExchangeResult<ServerSentEvent<String>> result =
            client.get()
                .uri("/api/recovered-stream")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<String>
                    >() {}
                );

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                "progress".equals(event.event())
                    && "started".equals(event.data())
            )
            .expectNextMatches(event ->
                "progress".equals(event.event())
                    && "halfway".equals(event.data())
            )
            .expectNextMatches(event ->
                "error".equals(event.event())
                    && event.data().contains("could not finish")
            )
            .verifyComplete();
    }
}
~~~

Test đầu tiên xác nhận lỗi trước commit trở thành response 500 Problem Details. Test thứ hai xác nhận status 200 đã được nhận, hai SSE event đến trước rồi body publisher kết thúc bằng lỗi. Loại exception transport cụ thể có thể khác theo HTTP client và server runtime. Test thứ ba xác nhận lỗi nguồn được chuyển thành event error và stream hoàn tất bình thường.

### 8.7. Chạy ứng dụng

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Gọi lỗi trước commit:

~~~bash
curl -i http://localhost:8080/api/before-commit
~~~

Response chính:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
~~~

Body:

~~~json
{
  "type": "about:blank",
  "title": "Internal server error",
  "status": 500,
  "detail": "The request could not be completed.",
  "code": "REQUEST_FAILED"
}
~~~

Gọi stream lỗi sau commit:

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/after-commit
~~~

Client có thể nhận:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

id:1
event:progress
data:started

id:2
event:progress
data:halfway
~~~

Sau hai event, stream bị kết thúc bất thường. Curl có thể báo lỗi truyền tải vì body chưa hoàn tất; nội dung và thông báo cụ thể phụ thuộc HTTP version, server và client.

Gọi stream đã chuyển lỗi thành event:

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/recovered-stream
~~~

Body có ba event:

~~~text
event:progress
data:started

event:progress
data:halfway

event:error
data:The stream could not finish. Retry the operation.
~~~

Trong trường hợp này publisher xử lý lỗi nguồn và complete bình thường; status vẫn là 200. Client cần hiểu event error theo protocol SSE của ứng dụng.

## 9. Kiểm thử và quan sát lỗi trong môi trường thật

### 9.1. Kiểm tra response commit trong log

Nên ghi các thông tin:

- Request ID/correlation ID.
- URI và HTTP method.
- Status đã chọn trước commit.
- Thời điểm commit nếu có instrumentation.
- Loại lỗi và tầng phát sinh.
- Response đã committed hay chưa.
- Tín hiệu cuối cùng: complete, error hoặc cancel.
- Số byte/event đã gửi nếu có thể đo an toàn.

Không ghi access token, cookie, password, raw request body nhạy cảm hoặc toàn bộ dữ liệu cá nhân vào log.

### 9.2. Metrics nên phân biệt hai nhóm

Có thể theo dõi:

- Số lỗi được ánh xạ thành 4xx/5xx trước commit.
- Số lỗi phát sinh sau commit.
- Số stream bị cancel.
- Số response write failure.
- Số timeout trước/sau commit.
- Số client retry và tỷ lệ tải tiếp thành công.

Nếu chỉ đếm HTTP 500, ứng dụng sẽ bỏ sót lỗi stream đã commit status 200 nhưng body bị ngắt.

### 9.3. Kiểm thử bằng transport thật

Mock handler test có thể kiểm tra logic response, nhưng lỗi sau commit còn phụ thuộc server adapter và transport. Với stream, nên có integration test khởi động server thật và dùng client thật hoặc WebTestClient trên cổng ngẫu nhiên.

Kiểm thử ít nhất:

1. Lỗi xảy ra trước event đầu tiên.
2. Lỗi sau event đầu tiên.
3. Lỗi sau nhiều event.
4. Client chủ động cancel.
5. Timeout nguồn dữ liệu.
6. Lỗi encode phần tử giữa stream.
7. Nguồn lỗi được chuyển thành event error.
8. Server shutdown khi stream còn hoạt động.

Không khẳng định mọi HTTP client đều ném cùng một loại exception khi stream bị cắt. Hãy kiểm tra hành vi thực tế của transport mà ứng dụng sử dụng.

## 10. Những lỗi thường gặp

| Hiện tượng / hiểu nhầm | Cách xử lý |
| --- | --- |
| Đổi status thành 500 sau khi SSE đã gửi event | Không thể thay status đã commit; kết thúc stream hoặc phát event error theo protocol |
| Ghi JSON error sau một phần body | Có thể làm response không hợp lệ; thiết kế framing/event schema ngay từ đầu |
| Nghĩ controller return nghĩa là response đã gửi xong | Publisher có thể tiếp tục phát dữ liệu sau khi method return |
| Nghĩ response chỉ commit khi body hoàn tất | Streaming có thể commit ngay ở event/byte đầu tiên |
| Gọi setStatusCode nhưng bỏ qua giá trị boolean | Kiểm tra false nghĩa là status không được cập nhật vì response đã commit |
| Thêm cookie sau commit | Có thể phát sinh IllegalStateException; thêm cookie trước commit |
| Dùng beforeCommit để sửa header sau khi ghi body | Hook chỉ chạy trước commit; đăng ký trước khi response được commit |
| Custom WebExceptionHandler trả Mono.empty dù chưa xử lý | Completion có nghĩa là đã xử lý; nếu chưa thể xử lý, propagate lỗi |
| Chỉ bắt WebExchangeBindException hoặc exception ở controller | Cần phân biệt controller exception, WebExceptionHandler, codec/write error và cancellation |
| Coi cancellation là lỗi nghiệp vụ | Cancellation là tín hiệu vòng đời riêng; cleanup bằng doFinally |
| Dùng onErrorResume sau khi socket đã lỗi để sửa response | Recovery ở nguồn chỉ xử lý lỗi nguồn; không sửa được lỗi transport/write |
| Client thấy status 200 nên nghĩ download thành công | Kiểm tra body completion, Content-Length, checksum hoặc terminal event |
| Retry mọi request POST khi stream bị ngắt | Có thể lặp side effect; dùng idempotency key/job ID |
| Trả stack trace cho client | Dùng mã lỗi và thông báo ổn định; log chi tiết ở server |
| Chỉ đếm status 5xx để theo dõi lỗi | Lỗi sau commit có thể giữ status 200; cần metric riêng cho stream failure |
| Test stream chỉ kiểm tra status 200 | Cần tiêu thụ body publisher và xác minh complete/error/cancel |
| Cho rằng error event đồng nghĩa HTTP 500 | Event là dữ liệu trong stream; status vẫn là giá trị lúc commit |

## 11. Checklist thiết kế endpoint có streaming

- Xác định thời điểm response có thể commit.
- Đặt status và headers trước khi stream phát dữ liệu đầu tiên.
- Xử lý các lỗi có thể dự đoán trước khi commit.
- Định nghĩa event/error schema nếu stream cần báo lỗi sau commit.
- Không dùng JSON error body để thay một stream đã bắt đầu.
- Có timeout và cancellation phù hợp.
- Cleanup resource trong doFinally hoặc cơ chế lifecycle tương ứng.
- Kiểm tra isCommitted trước khi custom handler cố ghi error response.
- Nếu handler đã xử lý lỗi, trả completion; nếu chưa xử lý được, propagate lỗi.
- Ghi log và metrics riêng cho post-commit failure.
- Cung cấp retry/resume hoặc idempotency khi nghiệp vụ yêu cầu.
- Kiểm thử bằng HTTP server thật với body publisher, không chỉ kiểm tra status.
- Không để error response lộ dữ liệu nội bộ.
- Theo dõi lỗi serialization và transport riêng với lỗi nghiệp vụ.

## 12. Bài tập thực hành

**Bài 1 — Lỗi trước commit:** Tạo endpoint trả Mono.error ngay lập tức. Dùng @RestControllerAdvice trả ProblemDetail 500. Kiểm tra status, Content-Type và body.

**Bài 2 — Lỗi sau commit:** Tạo Flux SSE phát ba event rồi onError. Dùng curl -N để quan sát client nhận các event trước khi stream bị ngắt.

**Bài 3 — Kiểm tra commit:** Đăng ký beforeCommit để thêm X-Request-Id. Ghi log isCommitted trước khi ghi body và sau khi event đầu tiên được flush.

**Bài 4 — Status không đổi:** Thử setStatusCode(500) sau commit. Quan sát giá trị boolean và response status thực tế trên client.

**Bài 5 — Error event:** Dùng onErrorResume chuyển lỗi nguồn thành event error cuối cùng. Viết client xử lý event progress, error và complete.

**Bài 6 — Cancellation:** Kết nối SSE rồi ngắt client sau event thứ hai. Quan sát doFinally nhận CANCEL và bảo đảm nguồn dữ liệu được cleanup.

**Bài 7 — Timeout:** Tạo một publisher chậm. Đặt timeout trước event đầu tiên rồi đặt timeout sau event đầu tiên; so sánh response.

**Bài 8 — Write failure:** Tạo test làm client ngắt kết nối khi server đang ghi body lớn. Phân biệt lỗi transport với lỗi từ service publisher.

**Bài 9 — ProblemDetail:** Bật spring.webflux.problemdetails.enabled và kiểm tra các exception WebFlux chuẩn. Thêm custom exception có mã lỗi ổn định.

**Bài 10 — Retry:** Tạo một tác vụ có Job ID. Khi stream bị ngắt, client reconnect để đọc trạng thái hoặc tiếp tục từ event ID mà không tạo tác vụ trùng.

## 13. Ghi nhớ

Điểm phân chia quan trọng trong WebFlux là **response commit**. Trước commit, Spring có thể thay status, headers và body để tạo error response. Sau commit, các phần đã gửi không thể bị thu hồi; lỗi chỉ có thể được propagate, ghi nhận, cleanup hoặc biểu diễn bằng một thông điệp cuối theo protocol streaming đã thiết kế.

Dùng **@ExceptionHandler**, **@RestControllerAdvice**, **WebExceptionHandler** và **ProblemDetail** cho lỗi có thể chuyển thành response. Dùng **isCommitted()** để biết response đã vượt qua ranh giới thay đổi metadata hay chưa. Với SSE/NDJSON, thiết kế event error rõ ràng nếu cần báo lỗi sau commit; với file download, dùng checksum, retry hoặc resume để phát hiện và xử lý nội dung chưa hoàn tất.

Đừng nhầm lỗi sau commit với lỗi trước commit, cũng đừng nhầm cancellation với onError. Hai khác biệt này quyết định cách server kết thúc response và cách client khôi phục.

## 14. Tài liệu tham khảo

- Spring Boot Reference — Reactive Web Applications / Error Handling: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework Reference — Reactive Core / Exceptions and WebExceptionHandler: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework Reference — WebFlux Error Responses and Problem Details: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Framework API — ServerHttpResponse: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html
- Spring Framework API — ReactiveHttpOutputMessage: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ReactiveHttpOutputMessage.html
- Spring Framework API — WebExceptionHandler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebExceptionHandler.html
- Spring Framework API — ResponseStatusExceptionHandler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/handler/ResponseStatusExceptionHandler.html
- Spring Framework API — ProblemDetail: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- Reactor Reference Guide — Error Handling and Cancellation: https://projectreactor.io/docs/core/release/reference/
