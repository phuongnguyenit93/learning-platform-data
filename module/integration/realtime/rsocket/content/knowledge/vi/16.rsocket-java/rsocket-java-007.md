# Cài đặt phía xử lý cho requestResponse, fireAndForget, requestStream, requestChannel

RSocket định nghĩa bốn kiểu tương tác cốt lõi: request-response, fire-and-forget, request-stream và request-channel. Ở phía server, Spring Boot ánh xạ các request này tới method được đánh dấu bằng **@MessageMapping**. Kiểu tham số và giá trị trả về của method thể hiện cách server nhận payload và phát response.

Khi triển khai, cần chọn đúng chữ ký handler cho từng kiểu tương tác, trả về publisher reactive phù hợp và để framework quản lý subscription. Handler không nên tự gọi **subscribe()** hoặc chặn thread bằng **block()**. Cách viết này giúp RSocket và Reactor phối hợp demand, cancellation, lỗi và vòng đời stream.

## 1. Cách Spring ánh xạ request tới handler

Một controller RSocket thường được khai báo bằng **@Controller**. Mỗi method **@MessageMapping** gắn với một route mà client gọi bằng **RSocketRequester.route(...)**.

Ví dụ route orders.find:

~~~java
@Controller
public class OrderRSocketController {

    private final OrderService orderService;

    public OrderRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<OrderView> find(@Payload FindOrderRequest request) {
        return orderService.find(request.orderId());
    }
}
~~~

Client gửi request tới route:

~~~java
Mono<OrderView> result = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);
~~~

Spring chọn handler theo route và chuyển payload đã decode thành kiểu tham số. Kiểu trả về quyết định response mà server phát. Với publisher reactive, framework đăng ký và quản lý quá trình tiêu thụ publisher để thực hiện tương tác RSocket.

Một hợp đồng route nên thống nhất giữa client và server:

- Tên route và ý nghĩa nghiệp vụ.
- Kiểu request và response.
- MIME type và codec được hai bên hỗ trợ.
- Interaction model mà client sử dụng.
- Quy tắc lỗi, timeout, xác thực và quyền truy cập.

## 2. Request-response: nhận một request, trả một kết quả

Request-response phù hợp khi server xử lý một yêu cầu và trả về tối đa một response. Handler thường nhận một DTO và trả về **Mono<Response>** hoặc một giá trị đồng bộ nếu thao tác thực sự ngắn và không blocking.

~~~java
public record FindOrderRequest(String orderId) {}

public record OrderView(
    String orderId,
    String status,
    BigDecimal total
) {}

@Controller
public class OrderQueryController {

    private final OrderService orderService;

    public OrderQueryController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<OrderView> find(@Payload FindOrderRequest request) {
        return orderService.find(request.orderId())
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(request.orderId())));
    }
}
~~~

**Mono<OrderView>** có thể phát một giá trị rồi hoàn tất, hoặc hoàn tất rỗng nếu nghiệp vụ cho phép không có kết quả. Nếu publisher phát lỗi, tương tác request-response kết thúc bằng lỗi. Không nên biến lỗi không tìm thấy thành object rỗng nếu hợp đồng API cần phân biệt rõ kết quả không tồn tại.

Client gọi bằng retrieveMono:

~~~java
Mono<OrderView> order = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);
~~~

Một số lưu ý:

- Dùng DTO riêng cho request và response, tránh trả trực tiếp entity persistence.
- Kiểm tra định dạng ID, quyền truy cập và tenant ở server.
- Đặt timeout phù hợp ở client và các dependency phía server.
- Không dùng request-response cho dữ liệu cần phát nhiều lần theo thời gian; hãy cân nhắc request-stream.

## 3. Fire-and-forget: gửi lệnh không chờ response

Fire-and-forget phù hợp khi client gửi một sự kiện hoặc lệnh mà không cần response ở cấp giao thức. Handler thường nhận một payload và trả về **Mono<Void>** hoặc **void**. Nếu cần thực hiện công việc bất đồng bộ, Mono<Void> giúp biểu diễn quá trình xử lý bằng reactive pipeline.

~~~java
public record AuditEvent(
    String actorId,
    String action,
    Instant occurredAt
) {}

@Controller
public class AuditRSocketController {

    private final AuditService auditService;

    public AuditRSocketController(AuditService auditService) {
        this.auditService = auditService;
    }

    @MessageMapping("audit.record")
    public Mono<Void> record(@Payload AuditEvent event) {
        return auditService.append(event);
    }
}
~~~

Client gửi bằng send():

~~~java
Mono<Void> sent = requester
    .route("audit.record")
    .data(event)
    .send();
~~~

**send()** hoàn tất khi phía client đã hoàn tất thao tác gửi theo API của requester. Nó không phải xác nhận nghiệp vụ rằng server đã lưu bền vững hoặc xử lý thành công sự kiện. Fire-and-forget không cung cấp response payload cho client.

Nếu nghiệp vụ cần xác nhận server đã tiếp nhận hoặc xử lý, hãy dùng request-response với một response acknowledgement. Với sự kiện có tác dụng phụ, cân nhắc event ID/idempotency key để xử lý request trùng và thiết kế retry có kiểm soát.

Không nên bỏ publisher xử lý bằng cách gọi subscribe() bên trong handler rồi trả về ngay. Cách đó tách công việc khỏi vòng đời request, làm lỗi khó quan sát và khiến framework không thể quản lý cancellation hoặc hoàn tất của tác vụ.

## 4. Request-stream: một request, nhiều response

Request-stream phù hợp khi client gửi một request ban đầu và server phát nhiều phần tử theo thời gian. Handler nhận một DTO và trả về **Flux<Response>**.

Ví dụ theo dõi giá:

~~~java
public record PriceSubscription(String symbol) {}

public record PriceTick(
    String symbol,
    BigDecimal price,
    Instant timestamp
) {}

@Controller
public class PriceRSocketController {

    private final PriceService priceService;

    public PriceRSocketController(PriceService priceService) {
        this.priceService = priceService;
    }

    @MessageMapping("prices.watch")
    public Flux<PriceTick> watch(@Payload PriceSubscription request) {
        return priceService.watch(request.symbol())
            .doOnCancel(() ->
                log.debug("Price stream cancelled: {}", request.symbol()));
    }
}
~~~

Client nhận stream bằng retrieveFlux:

~~~java
Flux<PriceTick> ticks = requester
    .route("prices.watch")
    .data(new PriceSubscription("ACME"))
    .retrieveFlux(PriceTick.class);
~~~

Server không cần tự tạo vòng lặp gửi từng response. Nó trả về một Flux; framework và RSocket quản lý việc phát payload theo demand của requester.

### Demand và backpressure

Khi client chỉ yêu cầu một số phần tử nhất định, server chỉ được phát trong phạm vi demand đã cấp. Với request-stream, RSocket sử dụng initial request N và các frame REQUEST_N để bổ sung nhu cầu. Nếu consumer chậm, responder phải chờ thêm credit thay vì phát vượt nhu cầu.

Điều này không tự giới hạn mọi buffer trong ứng dụng. Các operator như publishOn, flatMap hoặc adapter tới nguồn không reactive vẫn có thể tạo queue. Cần chọn prefetch/concurrency phù hợp, giới hạn payload size và quan sát backlog.

### Cancellation và cleanup

Khi client hủy subscription hoặc dừng theo dõi, cancellation được truyền xuống stream đang hoạt động. Server nên dùng publisher hỗ trợ cancellation và giải phóng tài nguyên như cursor, subscription tới event source hoặc buffer tạm.

~~~java
@MessageMapping("telemetry.stream")
public Flux<Telemetry> stream(@Payload DeviceQuery query) {
    return telemetryService.stream(query.deviceId())
        .doOnCancel(() ->
            log.info("Telemetry subscription cancelled: {}", query.deviceId()))
        .doFinally(signal ->
            log.debug("Telemetry stream finished: {}", signal));
}
~~~

Không phải tác vụ blocking nào cũng dừng ngay khi cancellation đến. Nếu gọi thư viện blocking hoặc hệ thống ngoài không hỗ trợ hủy, cần có timeout, giới hạn tài nguyên và điểm kiểm tra dừng phù hợp.

## 5. Request-channel: nhận và phát stream hai chiều

Request-channel cho phép client gửi một stream request trong khi server đồng thời trả về một stream response. Phía server nhận **Flux<Input>** và trả về **Flux<Output>**.

Ví dụ client gửi các lệnh trong một phiên tương tác và nhận sự kiện xử lý:

~~~java
public record OrderCommand(
    String commandId,
    String orderId,
    String action
) {}

public record OrderEvent(
    String orderId,
    String state,
    Instant changedAt
) {}

@Controller
public class OrderChannelController {

    private final OrderCommandService commandService;

    public OrderChannelController(OrderCommandService commandService) {
        this.commandService = commandService;
    }

    @MessageMapping("orders.commands")
    public Flux<OrderEvent> commands(
            @Payload Flux<OrderCommand> commands) {

        return commands
            .concatMap(command -> commandService.handle(command))
            .doOnCancel(() ->
                log.info("Order command channel cancelled"))
            .doFinally(signal ->
                log.debug("Order command channel finished: {}", signal));
    }
}
~~~

Ở đây concatMap xử lý lệnh theo thứ tự nhận: nó chờ publisher xử lý lệnh hiện tại hoàn tất rồi mới chuyển sang lệnh tiếp theo. Nếu nghiệp vụ cho phép xử lý song song, có thể dùng flatMap với concurrency được giới hạn; cần cân nhắc thứ tự sự kiện và khả năng ghi đồng thời.

Client gửi một publisher và nhận publisher response:

~~~java
Flux<OrderCommand> commands = Flux.just(
    new OrderCommand("CMD-1", "ORD-1001", "CONFIRM"),
    new OrderCommand("CMD-2", "ORD-1001", "PACK")
);

Flux<OrderEvent> events = requester
    .route("orders.commands")
    .data(commands)
    .retrieveFlux(OrderEvent.class);
~~~

Client có thể tiêu thụ events trong khi nguồn commands tiếp tục phát. Trong channel, hai hướng có demand riêng. Việc một phía hoàn tất gửi không nhất thiết có nghĩa phía còn lại cũng đã hoàn tất.

### Chọn cách kết hợp dữ liệu vào/ra

Có hai kiểu xử lý phổ biến:

- **Response gắn với từng request:** dùng concatMap hoặc flatMap để biến mỗi lệnh thành một hay nhiều kết quả.
- **Response từ nguồn độc lập:** kết hợp stream lệnh với stream sự kiện khác bằng các operator như merge hoặc switchMap, nhưng phải quy định rõ cách kết thúc và xử lý cancellation.

Tránh dùng operator không giới hạn concurrency khi mỗi lệnh có thể gọi database hoặc dịch vụ downstream. Giới hạn số tác vụ đang chạy để tránh làm cạn connection pool và bộ nhớ.

## 6. Bảng chọn chữ ký handler

| Interaction model | Dữ liệu đầu vào phía server | Kiểu trả về điển hình | Ý nghĩa |
|---|---|---|---|
| Request-response | Một DTO | Mono<Response> | Một kết quả |
| Fire-and-forget | Một DTO | Mono<Void> hoặc void | Không có response payload |
| Request-stream | Một DTO | Flux<Response> | Nhiều response theo thời gian |
| Request-channel | Flux<Request> | Flux<Response> | Hai phía trao đổi stream |

Kiểu method không tự biến một request thành interaction model khác. Client khởi tạo kiểu tương tác bằng API RSocket tương ứng; handler phải có chữ ký tương thích với kiểu dữ liệu được gửi và trả về.

Trong Spring, các method handler thường nhận payload đã decode. Có thể dùng @Payload để làm rõ tham số nào là nội dung request. Nếu cần truyền route variable hoặc metadata, hãy dùng cơ chế argument resolver phù hợp với phiên bản Spring và quy ước của ứng dụng.

## 7. Cấu hình transport cho server

Spring Boot có thể khởi chạy RSocket server qua TCP hoặc WebSocket. Ví dụ cấu hình TCP:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

Với WebSocket, cấu hình transport và mapping path theo phiên bản Spring Boot đang dùng, ví dụ:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
      port: 8080
~~~

Đây là hai cấu hình thay thế nhau cho các profile hoặc môi trường khác nhau. Tên thuộc tính và cách cấu hình cụ thể có thể thay đổi theo phiên bản Spring Boot; hãy đối chiếu reference documentation của phiên bản dự án.

Transport chỉ quyết định cách peer kết nối và chuyển frame. Các route @MessageMapping và chữ ký handler cho bốn interaction model vẫn là hợp đồng ở tầng ứng dụng.

## 8. Validation và bảo mật tại handler

Payload được gửi từ peer cần được kiểm tra trước khi thực hiện nghiệp vụ. Dùng DTO chuyên biệt, giới hạn kích thước chuỗi và collection, kiểm tra enum/ID, sau đó kiểm tra các quy tắc phụ thuộc dữ liệu hiện tại trong service hoặc domain layer.

Ví dụ DTO có constraint:

~~~java
public record FindOrderRequest(
    @NotBlank
    @Size(max = 40)
    String orderId
) {}
~~~

Có thể dùng Jakarta Bean Validation cùng cơ chế validation mà phiên bản Spring đang sử dụng hỗ trợ. Dù payload decode thành DTO thành công, server vẫn phải kiểm tra quyền của principal hiện tại đối với order được yêu cầu. Không tin userId, tenantId hoặc role chỉ vì client gửi trong data hay metadata.

Các nguyên tắc bảo mật quan trọng:

- Dùng TLS khi transport đi qua mạng không tin cậy.
- Xác thực peer và phân quyền theo route.
- Giới hạn kích thước data và metadata.
- Không ghi token hoặc payload nhạy cảm vào log.
- Giới hạn số stream đồng thời và tốc độ gọi route nhạy cảm.
- Đặt timeout cho dependency và xử lý cancellation để giải phóng tài nguyên.

## 9. Xử lý lỗi ở bốn kiểu tương tác

Lỗi trong publisher của handler thường kết thúc tương tác hiện tại bằng lỗi RSocket. Cần phân biệt lỗi validation, lỗi nghiệp vụ, lỗi quyền truy cập và lỗi hạ tầng để client có thể xử lý đúng.

| Kiểu tương tác | Khi handler phát lỗi | Gợi ý xử lý |
|---|---|---|
| Request-response | Request kết thúc bằng lỗi | Chuẩn hóa mã lỗi và thông điệp |
| Fire-and-forget | Không có response payload để xác nhận | Ghi nhận lỗi phía server, dùng acknowledgement nếu client cần xác nhận |
| Request-stream | Stream response kết thúc bằng lỗi | Chỉ retry lỗi tạm thời; xác định cursor nếu cần replay |
| Request-channel | Tương tác channel bị lỗi theo quy tắc stream | Xác định ảnh hưởng tới hai hướng và dọn tài nguyên |

Không nên bắt mọi exception rồi chuyển thành response thành công giả. Với request-stream hoặc channel, nếu lỗi của một phần tử không nên kết thúc toàn bộ tương tác, có thể biểu diễn kết quả từng phần tử bằng DTO có trạng thái thành công/thất bại và xử lý lỗi bên trong operator.

## 10. Không tự subscribe hoặc block trong handler

Handler nên trả publisher cho framework. Hai cách sau thường gây vấn đề:

~~~java
// Không nên: tách tác vụ khỏi lifecycle của request
@MessageMapping("audit.bad")
public void bad(AuditEvent event) {
    auditService.append(event).subscribe();
}
~~~

~~~java
// Không nên: chặn thread để chờ kết quả
@MessageMapping("orders.bad")
public OrderView bad(String id) {
    return orderService.find(id).block();
}
~~~

Hãy trả publisher:

~~~java
@MessageMapping("audit.record")
public Mono<Void> record(AuditEvent event) {
    return auditService.append(event);
}
~~~

Khi trả publisher, framework có thể theo dõi hoàn tất, lỗi và cancellation. Nếu cần gọi API blocking, hãy cô lập nó trên scheduler phù hợp và đặt giới hạn concurrency; ưu tiên client non-blocking khi có thể.

## 11. Kiểm thử handler và interaction model

Có thể kiểm tra logic handler bằng unit test với Reactor Test, sau đó bổ sung integration test qua RSocket client/server thật.

### Kiểm tra request-response

~~~java
StepVerifier.create(controller.find(
        new FindOrderRequest("ORD-1001")))
    .expectNextMatches(order ->
        order.orderId().equals("ORD-1001"))
    .verifyComplete();
~~~

### Kiểm tra fire-and-forget handler

~~~java
StepVerifier.create(controller.record(event))
    .verifyComplete();
~~~

Test này xác nhận publisher xử lý hoàn tất. Integration test cần xác nhận client gọi route bằng fire-and-forget và không mong đợi response payload.

### Kiểm tra request-stream

~~~java
StepVerifier.create(controller.watch(
        new PriceSubscription("ACME")))
    .expectNextCount(2)
    .thenCancel()
    .verify();
~~~

Bài test xác nhận stream phát phần tử và có thể bị hủy. Nên bổ sung assertion để xác nhận nguồn dữ liệu được cleanup khi cancellation.

### Kiểm tra request-channel

~~~java
Flux<OrderCommand> input = Flux.just(
    new OrderCommand("CMD-1", "ORD-1001", "CONFIRM"),
    new OrderCommand("CMD-2", "ORD-1001", "PACK")
);

StepVerifier.create(controller.commands(input))
    .expectNextCount(2)
    .verifyComplete();
~~~

Ở mức integration, cần kiểm tra cả hai hướng hoạt động đồng thời, demand/backpressure, hoàn tất một hướng, cancellation và lỗi giữa channel.

## 12. Checklist trước khi đưa handler vào sử dụng

- Route có tên ổn định và không trùng với handler khác.
- DTO request/response có schema rõ ràng và giới hạn kích thước.
- Chọn đúng kiểu Mono, Flux hoặc Mono<Void> theo interaction model.
- Fire-and-forget không được hiểu nhầm là acknowledgement nghiệp vụ.
- Stream và channel có chính sách demand, concurrency và buffer phù hợp.
- Cancellation dừng publisher và giải phóng tài nguyên có thể hủy.
- Lỗi được phân loại và không làm lộ chi tiết nội bộ.
- Timeout, xác thực và authorization được cấu hình.
- Client và server thống nhất MIME type, codec và route.
- Unit test và integration test bao phủ bốn interaction model.

## 13. Kết luận

Phía server trong Spring RSocket dùng @MessageMapping để khai báo route và dùng kiểu tham số/giá trị trả về để biểu đạt cách xử lý. Request-response thường nhận một DTO và trả Mono<Response>; fire-and-forget nhận một DTO và trả Mono<Void> hoặc void; request-stream nhận một DTO và trả Flux<Response>; request-channel nhận Flux<Request> và trả Flux<Response>.

Hãy để framework quản lý subscription, tránh gọi subscribe() hoặc block() trong handler, và thiết kế validation, backpressure, cancellation, timeout cùng xử lý lỗi ngay từ đầu. Khi bốn interaction model được ánh xạ đúng vào chữ ký handler và hợp đồng route, các dịch vụ Java có thể giao tiếp realtime rõ ràng và dễ vận hành hơn.

