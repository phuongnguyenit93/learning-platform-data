# Chuyển yêu cầu HTTP thành lời gọi RSocket và quản lý hủy

Một API gateway có thể nhận HTTP từ trình duyệt hoặc mobile app rồi gọi dịch vụ nội bộ bằng RSocket. Gateway chuyển path, query, body và một số header được chọn thành route, data và metadata của RSocket. Kết quả từ RSocket được chuyển thành HTTP response.

Khi HTTP endpoint trả về `Mono` hoặc `Flux` trực tiếp, WebFlux quản lý subscription của response. Nếu HTTP client ngắt kết nối hoặc hủy việc đọc stream, tín hiệu cancellation có thể truyền ngược qua Reactor tới lời gọi RSocket. RSocket client khi đó gửi frame `CANCEL` cho interaction tương ứng; responder nhận frame và hủy subscription của stream.

Để cơ chế này hoạt động, gateway phải giữ lời gọi trong cùng reactive pipeline. Nếu tự `subscribe()`, `block()`, cache stream hoặc tách công việc thành tác vụ nền, vòng đời của lời gọi RSocket có thể không còn gắn với HTTP request.

## 1. Kiến trúc HTTP-to-RSocket gateway

Gateway có hai trách nhiệm:

- Chuyển đổi hợp đồng HTTP thành hợp đồng route và payload RSocket.
- Quản lý thời gian sống của lời gọi downstream theo HTTP request, bao gồm timeout, cancellation và cleanup.

Ví dụ hệ thống có HTTP API cho đơn hàng và dịch vụ Order phía sau:

~~~text
HTTP Client
    |
    | GET /api/orders/42/events
    v
Spring WebFlux Gateway
    |
    | route("orders.events")
    | data(OrderEventsQuery)
    v
RSocketRequester
    |
    | REQUEST_STREAM
    v
Order Service
    |
    | Flux<OrderEvent>
    v
RSocketRequester
    |
    | Flux<OrderEvent>
    v
WebFlux HTTP response (NDJSON)
    |
    v
HTTP Client
~~~

Một HTTP request thường tương ứng với một RSocket interaction trên connection dùng chung. Connection RSocket có thể phục vụ nhiều HTTP request đồng thời; mỗi interaction có stream ID riêng.

## 2. Chọn interaction model phù hợp với HTTP

Spring `RSocketRequester` xác định interaction dựa trên số lượng phần tử đầu vào và kiểu kết quả. Chọn đúng cardinality giúp gateway giữ được semantics của HTTP:

| HTTP API | RSocket interaction | Spring API | Mục đích |
| --- | --- | --- | --- |
| GET một tài nguyên | Request-Response | `retrieveMono(Type.class)` | Một request, tối đa một response. |
| GET event feed hoặc kết quả liên tục | Request-Stream | `retrieveFlux(Type.class)` | Một request, nhiều response. |
| POST luồng dữ liệu và nhận kết quả từng phần | Request-Channel | `data(inputFlux, Item.class).retrieveFlux(...)` | Luồng request và response hai chiều. |
| Gửi thông báo không cần xác nhận | Fire-and-Forget | `send()` | Gửi một chiều theo best-effort. |

Không dùng Fire-and-Forget cho endpoint cần xác nhận nghiệp vụ. `send()` hoàn tất khi message được gửi theo API, không chứng minh responder đã xử lý hoặc commit dữ liệu. Nếu HTTP cần trả kết quả chắc chắn hơn, hãy dùng Request-Response với response acknowledgement do ứng dụng định nghĩa.

Ví dụ endpoint chỉ phát một thông báo best-effort:

Giả sử controller đã được inject một requester tới Notification Service:

~~~java
public record Notification(String recipient, String message) {}

@PostMapping("/api/notifications")
Mono<ResponseEntity<Void>> notify(
        @RequestBody Notification notification) {

    return notificationRequester
        .route("notifications.publish")
        .data(notification)
        .send()
        .thenReturn(ResponseEntity.accepted().<Void>build());
}
~~~

HTTP 202 ở đây chỉ cho biết gateway đã hoàn tất thao tác gửi theo API RSocket. Nó không phải acknowledgement rằng dịch vụ nhận đã lưu hoặc xử lý thông báo.

## 3. Cấu hình RSocketRequester dùng chung

Gateway cần dependency WebFlux và RSocket. Khi dùng Spring Boot dependency management, để BOM quản lý các phiên bản Spring và Reactor:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-rsocket</artifactId>
    </dependency>
</dependencies>
~~~

Tạo `RSocketStrategies` với codec cho DTO và một requester tới dịch vụ Order:

~~~java
@Configuration
public class RSocketClientConfiguration {

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(new Jackson2JsonEncoder()))
            .decoders(decoders ->
                decoders.add(new Jackson2JsonDecoder()))
            .build();
    }

    @Bean
    RSocketRequester orderRequester(
            RSocketStrategies strategies,
            Environment environment) {

        String host = environment.getRequiredProperty(
            "services.order.rsocket.host"
        );
        int port = environment.getRequiredProperty(
            "services.order.rsocket.port",
            Integer.class
        );

        return RSocketRequester.builder()
            .rsocketStrategies(strategies)
            .tcp(host, port);
    }
}
~~~

Ví dụ dùng TCP. Có thể dùng `webSocket(URI)` nếu dịch vụ đích mở RSocket qua WebSocket. `RSocketRequester` được cấu hình một lần và có thể được inject vào nhiều controller; kết nối được thiết lập khi có request đầu tiên, sau đó được tái sử dụng.

Properties:

~~~yaml
services:
  order:
    rsocket:
      host: order-service
      port: 7000
~~~

Nếu ứng dụng cần thêm CBOR, metadata codec, tracing hoặc authentication encoder, hãy bổ sung chúng vào cùng `RSocketStrategies`. Client và server phải thống nhất MIME type và schema của payload.

## 4. Chuyển HTTP GET thành Request-Response

Giả sử HTTP API:

~~~http
GET /api/orders/42
Accept: application/json
~~~

Gateway lấy order ID từ path, tạo request DTO rồi gọi route `orders.get`:

~~~java
public record GetOrder(UUID orderId) {}

public record OrderView(
    UUID id,
    String status,
    BigDecimal total
) {}

@RestController
@RequestMapping("/api/orders")
public class OrderGatewayController {

    private final RSocketRequester orderRequester;

    public OrderGatewayController(RSocketRequester orderRequester) {
        this.orderRequester = orderRequester;
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> getOrder(
            @PathVariable UUID id) {

        return orderRequester
            .route("orders.get")
            .data(new GetOrder(id))
            .retrieveMono(OrderView.class)
            .timeout(Duration.ofSeconds(3))
            .map(ResponseEntity::ok)
            .onErrorMap(
                TimeoutException.class,
                error -> new ResponseStatusException(
                    HttpStatus.GATEWAY_TIMEOUT,
                    "Order service timed out",
                    error
                )
            );
    }
}
~~~

Ở dịch vụ Order, route có thể được xử lý bằng `@MessageMapping`:

~~~java
@Controller
public class OrderRSocketController {

    private final OrderService orderService;

    public OrderRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.get")
    Mono<OrderView> getOrder(GetOrder request) {
        return orderService.findById(request.orderId());
    }
}
~~~

`retrieveMono` giữ lời gọi ở dạng reactive. Nếu HTTP request bị hủy trong khi RSocket response chưa về, cancellation có thể được truyền xuống interaction đang chờ. Nếu downstream timeout, Reactor hủy subscription upstream rồi phát `TimeoutException` cho gateway để ánh xạ thành HTTP 504.

## 5. Chuyển HTTP GET stream thành Request-Stream

Với event feed, HTTP client cần nhận từng event ngay khi có dữ liệu. Dùng NDJSON hoặc Server-Sent Events thay vì đợi toàn bộ danh sách:

~~~http
GET /api/orders/42/events
Accept: application/x-ndjson
~~~

Gateway trả `Flux` từ RSocket trực tiếp:

~~~java
public record OrderEventsQuery(UUID orderId) {}

public record OrderEvent(
    UUID eventId,
    UUID orderId,
    String type,
    Instant occurredAt
) {}

@GetMapping(
    value = "/{id}/events",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
Flux<OrderEvent> orderEvents(@PathVariable UUID id) {
    return orderRequester
        .route("orders.events")
        .data(new OrderEventsQuery(id))
        .retrieveFlux(OrderEvent.class)
        .doOnCancel(() ->
            log.info("HTTP consumer cancelled order event stream: {}", id))
        .doFinally(signal ->
            log.debug("Order event stream ended: orderId={}, signal={}",
                id, signal));
}
~~~

Responder:

~~~java
@MessageMapping("orders.events")
Flux<OrderEvent> orderEvents(OrderEventsQuery query) {
    return orderService.watchEvents(query.orderId());
}
~~~

Vì request đầu vào là một object và kết quả là `Flux`, Spring chọn Request-Stream. WebFlux ghi các phần tử khi chúng đến thay vì yêu cầu gateway gom toàn bộ stream vào bộ nhớ.

Với `text/event-stream`, có thể trả `Flux<ServerSentEvent<OrderEvent>>` để có event ID, event name và comment heartbeat. Nếu dùng NDJSON, mỗi event được encode thành một JSON object trên một dòng.

## 6. Chuyển HTTP body stream thành Request-Channel

Một số API nhận luồng dữ liệu lớn, ví dụ upload file theo chunk hoặc nhập dữ liệu cảm biến. WebFlux có thể giải mã request body thành `Flux<UploadChunk>`, sau đó gateway gửi luồng này tới RSocket:

~~~http
POST /api/uploads
Content-Type: application/x-ndjson
Accept: application/x-ndjson

{"uploadId":"u-42","sequence":0,"content":"..."}
{"uploadId":"u-42","sequence":1,"content":"..."}
{"uploadId":"u-42","sequence":2,"content":"..."}
~~~

Gateway:

~~~java
public record UploadChunk(
    UUID uploadId,
    long sequence,
    byte[] content
) {}

public record UploadAck(
    UUID uploadId,
    long sequence,
    String status
) {}

@PostMapping(
    value = "/api/uploads",
    consumes = MediaType.APPLICATION_NDJSON_VALUE,
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
Flux<UploadAck> upload(
        @RequestBody Flux<UploadChunk> chunks) {

    return orderRequester
        .route("files.upload")
        .data(chunks, UploadChunk.class)
        .retrieveFlux(UploadAck.class)
        .doOnCancel(() -> log.info("Upload HTTP stream cancelled"))
        .doFinally(signal ->
            log.debug("Upload channel terminated: {}", signal));
}
~~~

Responder:

~~~java
@MessageMapping("files.upload")
Flux<UploadAck> upload(Flux<UploadChunk> chunks) {
    return chunks.concatMap(fileService::acceptChunk);
}
~~~

Input và output đều là stream nên đây là Request-Channel. `concatMap` xử lý từng chunk theo thứ tự và chờ kết quả chunk trước khi chuyển sang chunk tiếp theo. Nếu cần xử lý song song, có thể dùng `flatMap` với concurrency hữu hạn và phải định nghĩa cách bảo đảm thứ tự/ghi nhận chunk.

Để HTTP body thực sự được đọc theo luồng, client phải gửi định dạng streaming như NDJSON và server phải giữ `Flux` thay vì chuyển body thành `List` hoặc `collectList()`. Giới hạn kích thước chunk, tổng upload, thời gian và số upload đồng thời ở gateway lẫn dịch vụ đích.

## 7. Cancellation đi từ HTTP tới RSocket như thế nào?

Khi HTTP client đóng kết nối hoặc hủy subscription đọc response, WebFlux phát hiện việc ghi response không thể tiếp tục và hủy subscription của publisher do controller trả về. Nếu publisher đó trực tiếp bao quanh `RSocketRequester`, Reactor truyền cancellation ngược lên RSocket client.

~~~text
HTTP Client          WebFlux Gateway       RSocket Client       RSocket Server
    |                       |                     |                    |
    | GET /events           |                     |                    |
    |---------------------->|                     |                    |
    |                       | retrieveFlux()      |                    |
    |                       |-------------------->| REQUEST_STREAM     |
    |                       |                     |------------------->|
    |                       |                     |                    |
    |<----------------------|<--------------------|<----- PAYLOAD ------|
    |<----------------------|<--------------------|<----- PAYLOAD ------|
    |                       |                     |                    |
    X client disconnect     |                     |                    |
    |                       | cancel subscription |                    |
    |                       |-------------------->| CANCEL             |
    |                       |                     |------------------->|
    |                       |                     |   cancel publisher |
    |                       |                     |                    |
~~~

RSocket dùng frame `CANCEL` (type `0x09`) để hủy một stream đang hoạt động. Với Request-Stream, responder nhận CANCEL thì stream đó kết thúc. Với Request-Response, requester cũng có thể gửi CANCEL nếu chưa nhận response. Với Request-Channel, cancellation kết thúc interaction hai chiều.

Các điểm cần nhớ:

- CANCEL gắn với stream ID của một interaction, không đóng toàn bộ RSocket connection.
- Nhiều HTTP request có thể dùng chung một RSocket connection; hủy một HTTP request chỉ nên hủy stream RSocket tương ứng.
- Cancellation là tín hiệu hợp tác. Nó yêu cầu publisher dừng phát dữ liệu và giải phóng tài nguyên; nó không hoàn tác side effect đã xảy ra.
- Nếu có proxy hoặc gateway HTTP buffering response, server có thể phát hiện client disconnect chậm hơn.
- Nếu downstream đã hoàn tất trước khi HTTP client ngắt kết nối, không còn stream để hủy.

## 8. Xử lý cancellation ở phía RSocket responder

Reactive publisher nên tôn trọng cancellation và giải phóng subscription hoặc tài nguyên được mở riêng cho mỗi request. Có thể dùng `doOnCancel` để quan sát cancellation và `doFinally` để ghi nhận mọi kiểu kết thúc:

~~~java
@MessageMapping("orders.events")
Flux<OrderEvent> orderEvents(OrderEventsQuery query) {
    return orderService.watchEvents(query.orderId())
        .doOnCancel(() ->
            log.info("RSocket stream cancelled: {}", query.orderId()))
        .doFinally(signal ->
            metrics.recordStreamTermination(signal.name()));
}
~~~

`doOnCancel` chỉ chạy khi subscription bị hủy. `doFinally` chạy khi stream hoàn tất, lỗi hoặc bị hủy và nhận `SignalType` tương ứng. Callback cleanup cần nhanh, an toàn khi gọi lặp và không thực hiện thao tác blocking trên event-loop.

Nếu stream mở một tài nguyên bất đồng bộ riêng như subscription tới broker, cursor hoặc watcher, hãy quản lý tài nguyên bằng `usingWhen`:

~~~java
Flux<OrderEvent> watch(UUID orderId) {
    return Flux.usingWhen(
        watcherRegistry.open(orderId),
        WatchHandle::events,
        WatchHandle::close,
        (handle, error) -> handle.close(),
        WatchHandle::close
    );
}
~~~

`WatchHandle` là abstraction do ứng dụng định nghĩa; `close()` trả về `Publisher<Void>`. `usingWhen` gọi cleanup khi hoàn tất, lỗi hoặc cancellation. Đây là cách phù hợp hơn việc tự mở resource rồi chỉ ghi log trong `doOnCancel`.

Không khởi chạy một `subscribe()` độc lập trong responder để tiếp tục xử lý stream sau khi handler trả về. Subscription tách rời không còn được RSocket quản lý; CANCEL có thể dừng stream response nhưng không dừng tác vụ nền đó.

## 9. Hủy stream giao thức và hủy tác vụ nghiệp vụ là hai việc khác nhau

RSocket CANCEL dừng một interaction đang hoạt động trên connection. Nó không phải lệnh hủy một công việc bền vững đã được đưa vào queue hoặc lưu trong database.

Ví dụ:

- Client đang nghe stream tiến độ upload và đóng tab: hủy stream cập nhật tiến độ là hợp lý.
- Client đã gửi yêu cầu tạo báo cáo, server đã đưa job vào hàng đợi rồi HTTP request kết thúc: CANCEL của request ban đầu không tự xóa job đã lưu.
- Người dùng muốn dừng job đang chạy sau khi đã nhận HTTP 202: cần API nghiệp vụ riêng để hủy job.

Có thể thiết kế endpoint:

~~~http
DELETE /api/jobs/9f2a
~~~

Gateway gửi command tới route riêng:

~~~java
public record CancelJob(UUID jobId) {}

public record CancelJobResult(
    UUID jobId,
    boolean accepted
) {}

@DeleteMapping("/api/jobs/{id}")
Mono<ResponseEntity<CancelJobResult>> cancelJob(
        @PathVariable UUID id) {

    return orderRequester
        .route("jobs.cancel")
        .data(new CancelJob(id))
        .retrieveMono(CancelJobResult.class)
        .map(result -> ResponseEntity.accepted().body(result));
}
~~~

Đây là request nghiệp vụ có định danh job và có kết quả xác nhận. Nó khác với frame CANCEL tự động gắn với subscription của một stream. Dịch vụ phải kiểm tra quyền hủy, trạng thái hiện tại và tính idempotent của command.

## 10. Timeout cũng có thể kích hoạt cancellation

Timeout của gateway nên được phân biệt theo phạm vi:

| Loại timeout | Ví dụ | Tác động |
| --- | --- | --- |
| Kết nối RSocket | Không thiết lập được transport hoặc SETUP | Không có request stream nghiệp vụ được duy trì. |
| Request-Response deadline | Chờ `orders.get` quá 3 giây | `Mono.timeout` hủy lời gọi đang chờ và phát TimeoutException. |
| Stream idle timeout | Không có event mới trong 30 giây | `Flux.timeout` hủy interaction nếu khoảng chờ giữa các tín hiệu vượt ngưỡng. |
| HTTP client timeout | Client không muốn chờ thêm | Client hủy response subscription; cancellation có thể truyền tới RSocket. |
| Business job deadline | Job phải kết thúc trong 10 phút | Cần deadline và cơ chế dừng job ở tầng nghiệp vụ. |

Ví dụ Request-Response:

~~~java
Mono<OrderView> getOrder(UUID id) {
    return orderRequester
        .route("orders.get")
        .data(new GetOrder(id))
        .retrieveMono(OrderView.class)
        .timeout(Duration.ofSeconds(3));
}
~~~

Với `Flux`, `timeout(Duration)` thường được dùng làm giới hạn thời gian chờ giữa các tín hiệu, bao gồm thời gian chờ phần tử đầu tiên. Nó không phải tổng thời lượng tối đa của stream. Nếu API cần giới hạn thời lượng toàn bộ stream, hãy thiết kế deadline riêng và xác định rõ việc kết thúc stream khi hết hạn.

Không retry tự động chỉ vì HTTP client đã cancel. Retry sau cancellation sẽ tạo thêm công việc mà người dùng không còn chờ. Với lỗi timeout của request có side effect, cũng không thể kết luận server chưa xử lý; dùng idempotency key nếu client hoặc gateway có thể gửi lại command.

## 11. Backpressure khi nối HTTP stream với RSocket

WebFlux và RSocket đều dùng Reactive Streams. Khi HTTP response consumer đọc chậm, demand có thể truyền ngược qua publisher tới RSocket requester; RSocket dùng `REQUEST_N` để điều tiết số payload responder được phép gửi.

~~~text
HTTP Client đọc chậm
        |
        v
WebFlux response subscriber giảm demand
        |
        v
Flux từ RSocketRequester giảm request
        |
        v
RSocket gửi REQUEST_N phù hợp
        |
        v
RSocket responder giảm tốc độ phát
~~~

Backpressure giúp giảm việc phải đệm vô hạn, nhưng không có nghĩa toàn tuyến không có buffer. Codec, transport, proxy, kernel và operator có thể giữ một lượng dữ liệu đang chờ. Hãy:

- Giữ response ở dạng `Flux` thay vì `collectList()` khi stream lớn hoặc dài hạn.
- Tránh `onBackpressureBuffer()` không giới hạn.
- Giới hạn concurrency khi dùng `flatMap`.
- Đặt quota cho số stream đồng thời và kích thước payload.
- Dùng `limitRate` khi cần điều chỉnh demand ở một đoạn pipeline, sau khi đo tải thực tế.
- Kiểm tra cả hành vi khi client đọc chậm và khi client ngừng đọc.

Với Request-Channel, backpressure áp dụng cho cả luồng request và response. Nếu HTTP client dừng gửi body, gateway cần ngừng phát chunk tới RSocket; nếu HTTP client dừng đọc response, gateway cần hủy interaction channel theo chính sách.

## 12. Ánh xạ header và metadata có chọn lọc

HTTP header có thể chứa dữ liệu phục vụ tracing, correlation, tenant hoặc xác thực. Gateway nên chuyển các giá trị được cho phép thành metadata RSocket theo MIME type đã thống nhất.

Ví dụ truyền correlation ID:

~~~java
private static final MimeType TRACE_MIME =
    MimeType.valueOf("message/x.example-trace.v1");

Flux<OrderEvent> orderEvents(
        UUID id,
        @RequestHeader("X-Correlation-Id") String correlationId) {

    return orderRequester
        .route("orders.events")
        .metadata(correlationId, TRACE_MIME)
        .data(new OrderEventsQuery(id))
        .retrieveFlux(OrderEvent.class);
}
~~~

Đây là MIME type ví dụ do ứng dụng định nghĩa; cần đăng ký encoder/decoder hoặc metadata extractor tương ứng ở hai phía. Không chuyển toàn bộ HTTP header thành metadata một cách tự động.

Đối với xác thực:

- Xác minh HTTP principal tại gateway trước khi gọi dịch vụ.
- Chọn token hoặc credential được phép chuyển tiếp; có thể dùng service credential hoặc delegated access token tùy kiến trúc.
- Dùng authentication metadata extension đúng chuẩn và encoder tương ứng.
- Không chuyển cookie, header tùy ý hoặc token chưa được kiểm tra sang dịch vụ đích.
- Nếu requester dùng chung connection đã xác thực ở SETUP, cần hiểu principal gắn với connection. Với nhiều người dùng HTTP cùng dùng một connection, xác thực theo từng request hoặc dùng requester/connection riêng theo principal.
- Dùng TLS cho TCP hoặc WSS cho WebSocket trên đường truyền.

## 13. Ánh xạ lỗi RSocket thành HTTP status

Gateway là ranh giới giữa hai giao thức. Nó cần chuyển lỗi downstream thành HTTP status và response body có ý nghĩa cho caller:

| Tình huống | HTTP response gợi ý | Ghi chú |
| --- | --- | --- |
| HTTP request thiếu hoặc sai dữ liệu | 400 Bad Request | Kiểm tra trước khi gọi RSocket. |
| Không tìm thấy tài nguyên | 404 Not Found | Dựa trên lỗi domain đã được ánh xạ rõ ràng. |
| Conflict nghiệp vụ | 409 Conflict | Ví dụ trạng thái đơn hàng không cho phép thao tác. |
| RSocket service không sẵn sàng | 502 hoặc 503 | Chọn theo hợp đồng gateway và nguyên nhân. |
| Downstream timeout | 504 Gateway Timeout | Dùng deadline có giới hạn. |
| Caller không có quyền | 401 hoặc 403 | Giữ đúng semantics xác thực/phân quyền. |
| HTTP client ngắt kết nối | Không còn response để gửi | Ghi nhận cancellation, không coi như lỗi nghiệp vụ. |

Có thể dùng `@RestControllerAdvice` để ánh xạ lỗi RSocket/domain thành `ProblemDetail`. Không trả nguyên exception message hoặc stack trace từ dịch vụ nội bộ ra HTTP client.

Với stream NDJSON/SSE, nếu lỗi xảy ra sau khi response đã được commit và một phần dữ liệu đã gửi, server không thể đổi status code thành 5xx. Stream có thể kết thúc giữa chừng. Nếu client cần phân biệt lỗi nghiệp vụ trong stream, hãy định nghĩa một event lỗi ở tầng ứng dụng, ví dụ `StreamError`, hoặc dùng SSE event name riêng.

## 14. Những anti-pattern làm mất cancellation

| Anti-pattern | Tác động | Cách sửa |
| --- | --- | --- |
| Gọi `block()` trong WebFlux controller | Chặn event-loop và tách lời gọi khỏi reactive flow. | Trả `Mono` hoặc `Flux` trực tiếp. |
| Gọi `subscribe()` trong controller rồi trả HTTP response riêng | Subscription RSocket chạy độc lập; HTTP cancel không còn điều khiển nó. | Compose publisher bằng `map`, `flatMap`, `then` và trả publisher. |
| Gọi `collectList()` cho stream dài | Buffer toàn bộ dữ liệu, mất streaming và tăng memory. | Trả `Flux` hoặc ghi dữ liệu theo batch có giới hạn. |
| Dùng `cache()` cho stream cần hủy theo từng HTTP client | Cache có thể tiếp tục upstream và chia sẻ kết quả ngoài vòng đời một request. | Dùng publisher riêng cho request hoặc thiết kế multicast có lifecycle rõ ràng. |
| Dùng `onBackpressureBuffer()` không giới hạn | Client đọc chậm làm bộ nhớ tăng không giới hạn. | Giới hạn buffer, concurrency và quota. |
| Bắt lỗi rồi trả `Flux.empty()` cho mọi trường hợp | Caller tưởng stream kết thúc bình thường dù downstream lỗi. | Ánh xạ lỗi theo hợp đồng HTTP hoặc event lỗi trong stream. |
| Hủy subscription rồi kỳ vọng rollback side effect | CANCEL không hoàn tác transaction đã commit. | Dùng command bù trừ hoặc API hủy job nghiệp vụ. |
| Retry tự động sau client disconnect | Tạo công việc không còn người tiêu thụ. | Không retry cancellation; chỉ retry lỗi tạm thời theo chính sách rõ ràng. |

## 15. Kiểm thử cancellation xuyên HTTP và RSocket

Nên kiểm thử từng tầng và ít nhất một kịch bản end-to-end:

| Ca kiểm thử | Cách thực hiện | Kết quả cần xác nhận |
| --- | --- | --- |
| HTTP Request-Response thành công | Gọi GET tài nguyên | Gateway map đúng route, DTO và response. |
| HTTP Request-Stream thành công | Đọc NDJSON hoặc SSE | Event được phát dần, không gom toàn bộ. |
| HTTP Request-Channel | POST body dạng NDJSON | Input chunk và output acknowledgement được truyền hai chiều. |
| HTTP caller hủy stream | Đọc một vài phần tử rồi cancel subscription | Gateway nhận cancellation và RSocket interaction bị hủy. |
| RSocket responder nhận CANCEL | Gắn `doOnCancel` hoặc resource cleanup ở responder | Subscription nguồn được hủy và resource được đóng. |
| Downstream timeout | Làm responder không trả kết quả đúng hạn | Gateway trả 504 nếu response chưa commit và subscription bị hủy. |
| Client đọc chậm | Giảm tốc độ tiêu thụ HTTP body | Demand được điều tiết, không có buffer tăng vô hạn. |
| Một HTTP request bị hủy | Có nhiều HTTP request trên cùng RSocket connection | Chỉ interaction tương ứng bị hủy; request khác vẫn chạy. |
| Business job đã detach | Ngắt HTTP sau khi job được tạo | Job vẫn chạy theo chính sách; DELETE cancel command mới dừng job. |

Unit test publisher cancellation với StepVerifier:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(100))
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectNext(0L)
    .thenCancel()
    .verify();

assertThat(cancelled).isTrue();
~~~

Ở integration test, dùng một RSocket responder có `doOnCancel` để quan sát frame CANCEL. Sau đó mở HTTP stream qua WebClient và hủy subscription sau một vài phần tử. Xác nhận responder đã nhận cancellation, resource đã được cleanup và một request khác trên cùng connection vẫn tiếp tục bình thường.

Để kiểm thử trường hợp mất kết nối thật, dùng HTTP client/transport integration test có thể đóng response connection. `StepVerifier.thenCancel()` kiểm thử cancellation ở tầng Publisher; nó không thay thế hoàn toàn việc kiểm tra phát hiện disconnect của HTTP server và proxy thực tế.

## 16. Checklist triển khai

- [ ] Ánh xạ HTTP path/query/body thành route và data RSocket có hợp đồng rõ ràng.
- [ ] Chọn Request-Response, Request-Stream, Request-Channel hoặc FNF theo cardinality.
- [ ] Dùng `RSocketRequester` được quản lý bởi Spring và tái sử dụng connection hợp lý.
- [ ] Trả `Mono`/`Flux` trực tiếp từ WebFlux controller.
- [ ] Dùng NDJSON hoặc SSE cho response stream.
- [ ] Chuyển request body thành `Flux` khi cần Request-Channel.
- [ ] Quan sát cancellation bằng `doOnCancel` và `doFinally`.
- [ ] Đóng tài nguyên bằng cơ chế reactive cleanup như `usingWhen`.
- [ ] Phân biệt RSocket CANCEL với command hủy job nghiệp vụ.
- [ ] Đặt timeout, quota, concurrency và buffer có giới hạn.
- [ ] Không gọi `block()` hoặc `subscribe()` tách rời trong controller.
- [ ] Ánh xạ lỗi downstream thành HTTP status và response body phù hợp.
- [ ] Chỉ chuyển tiếp metadata/header được cho phép.
- [ ] Kiểm thử client disconnect, timeout, cancellation, backpressure và nhiều stream trên một connection.

## 17. Ghi nhớ

- HTTP gateway có thể chuyển một request thành RSocket interaction bằng `route`, `data`, `retrieveMono` hoặc `retrieveFlux`.
- Một input và một output là Request-Response; một input và nhiều output là Request-Stream; input/output dạng Flux là Request-Channel.
- WebFlux hỗ trợ trả `Mono` và `Flux`; trả publisher trực tiếp giúp giữ cancellation và backpressure trong cùng pipeline.
- Khi HTTP response bị hủy, Reactor truyền cancellation upstream; RSocket client có thể gửi frame `CANCEL` cho stream tương ứng.
- CANCEL chỉ hủy interaction trên stream ID đó, không đóng connection RSocket dùng chung.
- `doOnCancel` quan sát cancellation; `doFinally` quan sát complete, error và cancel.
- Cancellation không rollback side effect và không tự dừng job đã được tách thành tác vụ nền.
- Dùng endpoint nghiệp vụ riêng để hủy job bền vững; dùng RSocket CANCEL để dừng interaction đang hoạt động.
- Timeout, buffering, cache, manual subscribe và blocking có thể làm thay đổi hoặc phá vỡ hành vi cancellation.
- Kiểm thử cả HTTP disconnect lẫn RSocket responder để xác nhận cleanup thực sự diễn ra.

## Tài liệu tham khảo

- [Spring Framework — RSocketRequester và Requests](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [RSocket Protocol — CANCEL Frame và Stream Sequences](https://rsocket.io/about/protocol/)
- [Reactor Core — Mono doOnCancel và doFinally API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Reactor Core — Error Handling, Resource Cleanup và doFinally](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
