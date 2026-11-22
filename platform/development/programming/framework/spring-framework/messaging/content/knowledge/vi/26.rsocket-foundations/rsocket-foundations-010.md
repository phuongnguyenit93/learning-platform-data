# Phân biệt RSocket với STOMP, HTTP và hàng đợi bền vững

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt giao thức truyền tải, giao thức messaging và cơ chế lưu trữ message.
- Giải thích RSocket cung cấp bốn interaction model: Request-Response, Request-Stream, Channel và Fire-and-Forget.
- So sánh RSocket với HTTP request/response và STOMP over WebSocket.
- Hiểu backpressure, multiplexing, metadata, routing và session resumption của RSocket.
- Phân biệt kết nối realtime với hàng đợi có persistence, acknowledgement và retry.
- Chọn công nghệ phù hợp cho RPC, streaming, broadcast, giao tiếp client-server và xử lý công việc nền.
- Kết hợp RSocket, HTTP, STOMP và durable queue trong cùng một kiến trúc khi mỗi công nghệ giải quyết một nhu cầu riêng.

## 1. Bốn khái niệm thường bị nhầm lẫn

RSocket, STOMP, HTTP và durable queue thường được đặt cạnh nhau khi thiết kế giao tiếp giữa các thành phần. Tuy nhiên, chúng giải quyết những vấn đề ở các lớp khác nhau.

- **HTTP** là giao thức client/server theo mô hình request/response. Client gửi request, server trả response. HTTP được thiết kế stateless: ý nghĩa của mỗi request có thể được hiểu độc lập.
- **STOMP** là giao thức messaging dạng frame. Nó định nghĩa command như CONNECT, SEND, SUBSCRIBE, MESSAGE, UNSUBSCRIBE và DISCONNECT, cùng destination và header. Trong Spring, STOMP thường chạy trên WebSocket.
- **RSocket** là giao thức ứng dụng cho giao tiếp hai chiều, bất đồng bộ, hỗ trợ nhiều kiểu tương tác và Reactive Streams semantics. Nó có thể chạy trên TCP, WebSocket và các byte-stream transport khác.
- **Durable queue** là một khả năng của hệ thống message broker: message và queue có thể được lưu bền vững, để message còn tồn tại qua một số sự cố hoặc thời gian consumer offline. Độ bền thực tế phụ thuộc cấu hình broker, message persistence, replication và acknowledgement.

Điểm quan trọng: WebSocket là transport, STOMP và RSocket là giao thức ứng dụng, còn durable queue là một khả năng lưu trữ và phân phối của broker. Không nên xem chúng là bốn giao thức thay thế trực tiếp cho nhau.

## 2. Bản đồ các lớp giao tiếp

~~~text
Application behavior
   |
   +-- HTTP API: request / response
   |
   +-- STOMP messaging: SEND / SUBSCRIBE / destination
   |       |
   |       +-- WebSocket transport hoặc SockJS fallback
   |       +-- Simple Broker hoặc external STOMP broker
   |
   +-- RSocket: request-response / stream / channel / fire-and-forget
           |
           +-- TCP, WebSocket hoặc byte-stream transport khác

Durable messaging:
   Publisher --> durable broker/queue --> consumer
                 persistence, ack, retry, replication
~~~

Một số hệ thống dùng WebSocket cho transport của RSocket. Điều đó không biến RSocket thành STOMP. Hai giao thức có framing, interaction model, flow control và semantics riêng, dù cùng chạy trên một kết nối WebSocket.

Tương tự, STOMP có thể được relay tới RabbitMQ hoặc ActiveMQ. Việc có external broker không tự động làm mọi destination thành durable queue; queue, subscription, persistence và acknowledgement phải được cấu hình theo broker và giao thức cụ thể.

## 3. HTTP: request/response cho API và tài nguyên

HTTP phù hợp khi client muốn yêu cầu một hành động hoặc biểu diễn tài nguyên rồi nhận kết quả:

- Lấy hồ sơ người dùng.
- Tạo đơn hàng.
- Cập nhật trạng thái.
- Tải báo cáo hoặc file.
- Tìm kiếm theo điều kiện và phân trang.

Ví dụ Spring MVC:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public OrderDto getOrder(@PathVariable long id) {
        return orderService.findById(id);
    }

    @PostMapping
    public ResponseEntity<OrderDto> createOrder(
            @RequestBody CreateOrderRequest request) {

        OrderDto created = orderService.create(request);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(created);
    }
}
~~~

HTTP cung cấp semantics rõ ràng qua method, status code, header, cache và conditional request. Request/response cũng dễ tích hợp với browser, API gateway, proxy, CDN và công cụ quan sát.

HTTP không mặc định là một luồng message hai chiều lâu dài. Server thường trả lời request hiện tại; nếu client muốn cập nhật mới, nó có thể gửi request tiếp theo, dùng polling, Server-Sent Events, WebSocket hoặc một giao thức streaming phù hợp.

HTTP stateless cũng không có nghĩa ứng dụng không thể có session hoặc authentication. Nó có nghĩa semantics của từng request được thiết kế để có thể hiểu độc lập, còn trạng thái ứng dụng được quản lý ở tầng cao hơn.

## 4. STOMP: messaging theo destination và subscription

STOMP là giao thức messaging dạng frame. Client có thể:

- Gửi `SEND` tới một destination để yêu cầu ứng dụng xử lý.
- Gửi `SUBSCRIBE` tới destination để nhận message.
- Hủy subscription bằng `UNSUBSCRIBE`.
- Kết thúc phiên bằng `DISCONNECT`.

Trong Spring, STOMP thường chạy trên WebSocket. WebSocket cung cấp kênh hai chiều; STOMP quy định cách gửi message và định tuyến theo destination.

Cấu hình cơ bản:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Controller:

~~~java
@Controller
public class NotificationController {

    @MessageMapping("/notifications/read")
    public NotificationResult markRead(
            ReadNotificationRequest request) {
        return new NotificationResult(
                request.notificationId(), true);
    }

    public record ReadNotificationRequest(long notificationId) {}

    public record NotificationResult(long notificationId,
                                     boolean read) {}
}
~~~

Client có thể gửi `SEND /app/notifications/read` và đăng ký `SUBSCRIBE /topic/notifications`.

Spring định tuyến destination bắt đầu bằng `/app` tới controller. Destination bắt đầu bằng `/topic` hoặc `/queue` có thể được chuyển tới message broker theo cấu hình.

### 4.1 Điểm mạnh của STOMP

- Mô hình pub/sub và destination dễ hiểu.
- Hỗ trợ browser và các STOMP client đa ngôn ngữ.
- Tích hợp trực tiếp với Spring `@MessageMapping`, `SimpMessagingTemplate` và user destinations.
- Phù hợp cho notification, dashboard, chat và cập nhật UI.
- Có thể dùng SockJS fallback khi WebSocket không khả dụng.
- Có thể relay tới một external STOMP broker để phân phối giữa nhiều node.

### 4.2 Simple Broker và external broker

Spring Simple Broker giữ subscription trong bộ nhớ và phát message tới các client đang kết nối có destination khớp. Nó phù hợp để bắt đầu, nhưng không hỗ trợ đầy đủ các STOMP command như ACK và RECEIPT, không phải broker cluster và không cung cấp durable queue.

Khi cần broker đầy đủ hơn, Spring có thể dùng STOMP Broker Relay để chuyển message qua TCP tới external broker. Khả năng durable queue, persistence, retry, acknowledgement và clustering vẫn phụ thuộc broker bên ngoài, plugin STOMP và cấu hình thực tế.

Tên destination `/queue/orders` tự nó không đảm bảo một message chỉ được một consumer nhận hoặc được lưu khi consumer offline. Ngữ nghĩa destination phụ thuộc broker.

## 5. RSocket: giao thức tương tác hai chiều và streaming

RSocket là giao thức ứng dụng cho giao tiếp multiplexed và duplex trên TCP, WebSocket hoặc các byte-stream transport khác.

Sau khi kết nối được thiết lập, hai phía đều có thể khởi tạo request. Vì vậy, RSocket dùng khái niệm requester và responder thay vì cố định một phía luôn là client và phía còn lại luôn là server.

RSocket định nghĩa bốn interaction model:

| Interaction | Đầu vào | Đầu ra | Ví dụ |
|---|---|---|---|
| Request-Response | Một message | Một message | Lấy chi tiết tài khoản |
| Request-Stream | Một message | Một stream nhiều message | Theo dõi giá hoặc telemetry |
| Channel | Một stream | Một stream hai chiều | Trao đổi liên tục giữa hai phía |
| Fire-and-Forget | Một message | Không có response payload | Gửi tín hiệu không cần phản hồi |

### 5.1 Request-Response

Một request nhận một response. Mô hình này gần với RPC hoặc HTTP request/response, nhưng dùng RSocket connection và protocol framing.

Ví dụ: service A yêu cầu service B trả về thông tin khách hàng.

### 5.2 Request-Stream

Requester gửi một request và nhận nhiều response theo thời gian. Đây là lựa chọn tự nhiên cho telemetry, giá thị trường hoặc dữ liệu liên tục.

### 5.3 Channel

Hai phía trao đổi stream message theo cả hai hướng trên cùng interaction. Ví dụ một client gửi chuỗi vị trí và đồng thời nhận chỉ dẫn điều hướng.

### 5.4 Fire-and-Forget

Requester gửi một message mà không yêu cầu response payload. Mô hình này phù hợp với tín hiệu một chiều khi caller không cần kết quả trả về.

Cần hiểu chính xác semantics: trong Spring, `RSocketRequester.send()` trả về `Mono<Void>` biểu thị việc gửi message hoàn tất. Nó không chứng minh responder đã thực hiện xong nghiệp vụ hoặc dữ liệu đã được lưu bền vững.

## 6. Backpressure và multiplexing của RSocket

Một điểm nổi bật của RSocket là Reactive Streams semantics có thể đi qua ranh giới mạng.

Với Request-Stream và Channel:

- Requester phát tín hiệu demand cho số lượng phần tử muốn nhận.
- Responder cần tôn trọng demand.
- Requester có thể yêu cầu thêm phần tử khi đã xử lý xong phần trước.
- Producer có thể giảm tốc độ phát từ nguồn khi consumer không theo kịp.

Điều này giúp kiểm soát luồng dữ liệu và giảm nhu cầu buffer vô hạn. Tuy nhiên, backpressure chỉ có tác dụng khi các thành phần trong pipeline thực sự hỗ trợ và truyền demand đúng cách. Nếu ứng dụng gom toàn bộ dữ liệu vào một list hoặc dùng API blocking không giới hạn, lợi ích backpressure có thể bị mất.

RSocket cũng hỗ trợ multiplexing nhiều request trên một connection. Điều này cho phép nhiều interaction độc lập chia sẻ một kết nối, thay vì cần một kết nối riêng cho mỗi request stream.

Không nên hiểu multiplexing là không có giới hạn tài nguyên. Connection vẫn tiêu thụ bộ nhớ, buffer, CPU, stream state và tài nguyên xử lý. Cần đặt timeout, giới hạn concurrency, theo dõi số stream và quản lý cancellation.

## 7. RSocket có session resumption, nhưng không phải durable queue

RSocket có tính năng session resumption để hỗ trợ khôi phục các stream dài khi kết nối transport bị mất rồi được thiết lập lại. Cơ chế này cần giữ một lượng state cho việc resume và có thể kết hợp với backpressure để giảm lượng dữ liệu phải giữ.

Cần phân biệt:

- **Session resumption:** khôi phục trạng thái protocol/session trong phạm vi khả năng và cấu hình của RSocket.
- **Durable queue:** lưu message ở broker để tồn tại qua thời gian consumer offline hoặc một số sự cố.
- **Business persistence:** lưu dữ liệu nghiệp vụ hoặc event vào database/event store.
- **Acknowledgement:** xác nhận một message đã được nhận hoặc xử lý theo semantics của broker/protocol.

Session resumption không tự biến RSocket thành hệ thống lưu trữ message vô thời hạn. Nó không thay thế durable queue, database hoặc outbox. Nó cũng không tự chứng minh một transaction nghiệp vụ đã commit.

Nếu message phải được xử lý kể cả khi service đích offline lâu dài, hãy lưu message vào broker hoặc store bền vững trước khi giao. Dùng RSocket có thể là kênh tương tác realtime giữa các service đang hoạt động, nhưng cơ chế durability phải được thiết kế riêng.

## 8. Durable queue: lưu message và xác nhận giao nhận

Durable queue là mô hình message broker có thể lưu metadata queue và message theo cấu hình persistence. Một queue bền vững thường cần kết hợp nhiều yếu tố:

- Queue được khai báo durable.
- Message được publish với chế độ persistent nếu giao thức/broker yêu cầu.
- Broker có cơ chế ghi bền vững và replication phù hợp.
- Publisher xác nhận broker đã chấp nhận message.
- Consumer xác nhận message sau khi xử lý thành công.
- Retry và dead-letter policy được cấu hình để xử lý lỗi.

Ví dụ với RabbitMQ, queue durable và persistent message giúp message có thể được phục hồi sau restart theo cấu hình. Publisher confirms và consumer acknowledgements giải quyết hai hướng xác nhận khác nhau:

- Publisher confirm: broker xác nhận việc publish đã được chấp nhận theo semantics của broker.
- Consumer acknowledgement: consumer xác nhận delivery đã được xử lý để broker có thể đánh dấu message phù hợp cho việc xóa.

Hai cơ chế này độc lập. Publisher confirm không chứng minh consumer đã xử lý message; consumer acknowledgement không chứng minh publisher đã nhận confirm.

### 8.1 At-least-once và idempotency

Với retry và redelivery, consumer có thể nhận cùng một message nhiều lần. Vì vậy, xử lý nghiệp vụ nên idempotent:

- Gắn event ID duy nhất cho message.
- Lưu trạng thái đã xử lý hoặc unique constraint.
- Kiểm tra event ID trước khi áp dụng thay đổi.
- Chỉ ACK sau khi xử lý nghiệp vụ đã thành công theo thiết kế.

Không nên giả định retry luôn tạo ra exactly-once processing. Exactly-once end-to-end thường cần phối hợp transaction, deduplication và semantics của hệ thống lưu trữ.

### 8.2 Không nhầm STOMP receipt với consumer acknowledgement

STOMP RECEIPT xác nhận broker đã xử lý một frame có yêu cầu receipt. Nó không đồng nghĩa với việc một subscriber đã hoàn tất xử lý nghiệp vụ.

ACK của STOMP có semantics riêng tùy chế độ acknowledgement và broker. Simple Broker của Spring không hỗ trợ ACK và RECEIPT đầy đủ. External broker có thể hỗ trợ một phần hoặc toàn bộ, nhưng phải kiểm tra plugin STOMP và tài liệu đúng phiên bản.

Nếu sử dụng RabbitMQ, đừng suy luận rằng publisher confirms và consumer acknowledgements của AMQP 0-9-1 tự động có cùng API hoặc semantics khi client kết nối qua STOMP plugin. Phải kiểm tra khả năng của giao thức đang dùng.

## 9. Bảng so sánh tổng thể

| Tiêu chí | HTTP | STOMP over WebSocket | RSocket | Durable queue |
|---|---|---|---|---|
| Vai trò chính | API request/response | Messaging pub/sub theo destination | Request/response và streaming hai chiều | Lưu và phân phối message bền vững |
| Giao thức | HTTP | STOMP | RSocket | Phụ thuộc broker/protocol |
| Transport | TCP/TLS, HTTP/2 hoặc HTTP/3 tùy stack | WebSocket, có thể SockJS fallback | TCP, WebSocket và byte-stream transport | TCP hoặc transport broker hỗ trợ |
| Interaction | Request/response | SEND, SUBSCRIBE, MESSAGE | Request-Response, Request-Stream, Channel, Fire-and-Forget | Publish/consume, queue, ack |
| Streaming | Có thể qua API/extension như SSE hoặc streaming response | Message liên tục qua subscription | Native Request-Stream và Channel | Consumer nhận chuỗi message |
| Backpressure | Phụ thuộc API/streaming model | Không có Reactive Streams demand end-to-end mặc định | Reactive Streams demand xuyên mạng | Prefetch/flow control theo broker |
| Routing | URL, method, header | STOMP destination | Route metadata | Exchange, queue, routing key hoặc subscription |
| Durability | Không tự lưu request/response | Không tự có; phụ thuộc broker | Không tự là durable queue | Có thể có nếu cấu hình persistence |
| Offline consumer | Client phải request lại | Simple Broker không giữ message cho client offline | Session resumption có phạm vi riêng | Có thể giữ message trong queue |
| Phù hợp | CRUD, API, tài nguyên | UI realtime, notification, chat | RPC reactive, stream, duplex service | Job, event, retry và consumer độc lập |

## 10. Ví dụ Spring RSocket server

Spring Framework hỗ trợ RSocket responder qua `@MessageMapping` và `@ConnectMapping`. Spring Boot có thể tự cấu hình `RSocketMessageHandler` và `RSocketStrategies` khi dùng starter phù hợp.

Một handler Request-Response:

~~~java
@Controller
public class UserRSocketController {

    @MessageMapping("users.find")
    public Mono<UserView> findUser(UserQuery query) {
        return userService.findById(query.userId());
    }

    public record UserQuery(long userId) {}

    public record UserView(long id, String name) {}
}
~~~

Nếu method nhận một payload và trả về `Mono<T>`, đây là mô hình một input và một output, phù hợp với Request-Response.

Handler Request-Stream:

~~~java
@Controller
public class TelemetryRSocketController {

    @MessageMapping("devices.telemetry")
    public Flux<TelemetrySample> telemetry(DeviceQuery query) {
        return telemetryService.stream(query.deviceId());
    }

    public record DeviceQuery(String deviceId) {}
}
~~~

Một payload đầu vào và `Flux<T>` đầu ra tạo ra Request-Stream. Khi requester giảm demand hoặc cancel subscription, responder cần tôn trọng lifecycle của publisher và giải phóng tài nguyên liên quan.

### Cấu hình Spring Boot

Với ứng dụng WebFlux muốn expose RSocket qua WebSocket, có thể cấu hình:

~~~properties
spring.rsocket.server.mapping-path=/rsocket
spring.rsocket.server.transport=websocket
~~~

Spring Boot cũng hỗ trợ RSocket server độc lập qua TCP hoặc WebSocket tùy cấu hình. Nếu dùng TCP server độc lập, có thể cấu hình port, ví dụ:

~~~properties
spring.rsocket.server.port=9898
~~~

Việc nhúng RSocket vào WebFlux web server qua WebSocket cần Reactor Netty theo cấu hình Spring Boot. Hãy kiểm tra dependency và application type trước khi chọn chế độ triển khai.

## 11. Ví dụ Spring RSocket client với RSocketRequester

`RSocketRequester` cung cấp API fluent để tạo request, mã hóa payload và metadata.

Kết nối TCP:

~~~java
RSocketRequester requester =
        RSocketRequester.builder()
                .tcp("localhost", 9898);
~~~

Gọi Request-Response:

~~~java
Mono<UserView> user = requester
        .route("users.find")
        .data(new UserQuery(42L))
        .retrieveMono(UserView.class);
~~~

Gọi Request-Stream:

~~~java
Flux<TelemetrySample> samples = requester
        .route("devices.telemetry")
        .data(new DeviceQuery("device-17"))
        .retrieveFlux(TelemetrySample.class);
~~~

Gửi Fire-and-Forget:

~~~java
Mono<Void> sent = requester
        .route("audit.record")
        .data(new AuditEvent("USER_LOGIN", "user-42"))
        .send();
~~~

Với Fire-and-Forget, cần subscribe vào `Mono<Void>` hoặc compose nó vào reactive pipeline để việc gửi thực sự được thực thi. Tín hiệu hoàn tất chỉ cho biết message đã được gửi theo semantics của client/protocol; nó không chứng minh handler đã xử lý hoặc database đã commit.

Có thể kết nối qua WebSocket:

~~~java
URI uri = URI.create("ws://localhost:8080/rsocket");

RSocketRequester requester =
        RSocketRequester.builder()
                .webSocket(uri);
~~~

Nếu cần timeout, authentication, keepalive, session resumption hoặc interceptors, cấu hình `RSocketRequester.Builder` và underlying `RSocketConnector` phù hợp với hệ thống.

## 12. Khi nào nên chọn công nghệ nào?

### Chọn HTTP khi

- Client cần đọc hoặc thay đổi tài nguyên theo request cụ thể.
- API cần dễ gọi từ browser, mobile app, partner hoặc công cụ HTTP.
- Cache, status code, pagination và idempotent method quan trọng.
- Request không cần giữ một stream hai chiều lâu dài.

### Chọn STOMP khi

- Browser cần subscribe nhận notification hoặc broadcast.
- Mô hình destination và pub/sub là trung tâm.
- Ứng dụng đã dùng Spring WebSocket messaging và cần `@MessageMapping`.
- Có thể chấp nhận giới hạn của Simple Broker hoặc đã có external STOMP broker phù hợp.

### Chọn RSocket khi

- Service cần request/response và streaming trên cùng một protocol.
- Cần giao tiếp duplex và nhiều interaction đồng thời trên một connection.
- Backpressure xuyên mạng là lợi ích quan trọng.
- Client và server đều có thể chủ động gửi request.
- Hệ thống chấp nhận mô hình reactive và có khả năng vận hành Reactor/Netty.

### Chọn durable queue khi

- Công việc phải được xử lý dù consumer offline.
- Cần retry, redelivery hoặc dead-letter queue.
- Cần publisher confirms, consumer acknowledgements hoặc persistence.
- Publisher và consumer cần tách vòng đời.
- Cần buffer tải khi tốc độ producer và consumer khác nhau.

## 13. Có thể kết hợp các công nghệ

Không nhất thiết chọn một giao thức duy nhất cho mọi nhu cầu.

Một kiến trúc phổ biến:

~~~text
Browser / Mobile
   |
   +---- HTTP API --------------------> Business service
   |
   +---- STOMP / WebSocket ----------> Realtime notification
                                          |
                                          v
                                    Spring application
                                          |
                                          v
                                   Durable message broker
                                          |
                                          v
                                   Background consumers

Internal reactive services
   |
   +---- RSocket request/stream/channel ----> Other services
~~~

Ví dụ quy trình đặt hàng:

1. Client gọi HTTP POST để tạo đơn hàng.
2. Service lưu đơn hàng trong database và ghi event vào outbox trong cùng transaction.
3. Publisher đọc outbox và gửi event tới durable broker.
4. Consumer xử lý các công việc nền như thanh toán hoặc gửi email.
5. Service phát notification tới STOMP topic để browser cập nhật giao diện.
6. Các service nội bộ có thể dùng RSocket cho truy vấn reactive hoặc streaming telemetry.

Vai trò của từng phần:

- HTTP là API nghiệp vụ đồng bộ.
- Durable broker là nơi giữ công việc/event cần xử lý độc lập với trạng thái kết nối client.
- STOMP là kênh realtime để giao diện nhận cập nhật.
- RSocket là kênh tương tác reactive giữa các service cần streaming hoặc duplex request.

Khi kết hợp, phải thiết kế correlation ID, event ID, idempotency, retry, timeout và observability xuyên các lớp.

## 14. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
|---|---|
| RSocket là một loại durable queue | RSocket là protocol tương tác; durability cần broker/store riêng |
| RSocket chạy trên WebSocket nên giống STOMP | Cùng transport không có nghĩa cùng framing, routing hoặc interaction model |
| Request-Stream tự động lưu message cho client offline | Stream và backpressure không tự cung cấp queue persistence |
| Fire-and-Forget đảm bảo server đã xử lý xong | Nó không có response payload; completion của send không chứng minh nghiệp vụ đã hoàn tất |
| STOMP /queue luôn là queue point-to-point | Ý nghĩa phụ thuộc broker; Spring Simple Broker broadcast tới subscription phù hợp |
| STOMP RECEIPT là consumer acknowledgement | Receipt xác nhận broker xử lý frame, không xác nhận consumer hoàn tất nghiệp vụ |
| HTTP không thể streaming | HTTP có thể dùng SSE, streaming response và các cơ chế khác; semantics phụ thuộc API |
| Session resumption đồng nghĩa message persistence | Resumption khôi phục session/stream theo protocol state, không thay thế durable storage |
| Dùng RSocket là không cần timeout hoặc giới hạn concurrency | Reactive protocol vẫn cần giới hạn tài nguyên, timeout và giám sát |

## 15. Bảo mật và vận hành

Dù dùng giao thức nào, cần thiết kế authentication và authorization rõ ràng.

- Với HTTP, bảo vệ endpoint, kiểm tra quyền trên từng tài nguyên và dùng TLS.
- Với STOMP, xác thực kết nối và kiểm soát quyền SEND/SUBSCRIBE theo destination.
- Với RSocket, cấu hình authentication metadata, authorization theo route và TLS theo yêu cầu triển khai.
- Với durable broker, quản lý credential, vhost/namespace, quyền publish/consume và network access riêng.

Quan sát nên bao gồm:

- Số connection và stream đang hoạt động.
- Request rate, message rate và payload size.
- p50/p95/p99 latency.
- Timeout, cancellation, disconnect và reconnect.
- Backpressure/demand và số lượng phần tử được buffer.
- Queue depth, unacknowledged messages, redelivery và dead-letter rate.
- Tỷ lệ lỗi encode/decode và lỗi authentication/authorization.

Không log access token, mật khẩu, cookie hoặc payload nhạy cảm. Dùng correlation ID và trace ID để theo dõi request hoặc event xuyên các service.

## 16. Bài tập tự kiểm tra

### Bài 1

Một service cần gửi một request và nhận một object. Interaction model RSocket nào phù hợp?

**Đáp án:** Request-Response.

### Bài 2

Một client gửi một request rồi nhận liên tục hàng nghìn mẫu telemetry. Nên dùng mô hình nào?

**Đáp án:** Request-Stream. Nếu hai phía cùng gửi stream message, cân nhắc Channel.

### Bài 3

Một ứng dụng cần giữ job khi worker offline và xử lý lại sau khi worker kết nối. RSocket Fire-and-Forget có đủ không?

**Đáp án:** Không. Cần durable queue hoặc store có persistence và cơ chế acknowledgement/retry phù hợp.

### Bài 4

Một browser cần nhận notification khi đơn hàng đổi trạng thái. Công nghệ nào phù hợp?

**Đáp án:** STOMP over WebSocket là lựa chọn phù hợp cho pub/sub realtime. Trạng thái đơn hàng và lịch sử notification vẫn nên lưu ở backend.

### Bài 5

Một service nội bộ cần stream dữ liệu với backpressure xuyên mạng. Vì sao RSocket có thể phù hợp hơn một API HTTP request/response thông thường?

**Đáp án:** RSocket có Request-Stream và Channel với Reactive Streams demand được truyền qua ranh giới mạng, cho phép requester điều tiết tốc độ responder. HTTP vẫn có thể streaming, nhưng cần chọn cơ chế và semantics tương ứng.

### Bài 6

RabbitMQ publisher confirm đã nhận được. Điều đó có chứng minh consumer xử lý xong message không?

**Đáp án:** Không. Publisher confirm xác nhận broker đã chấp nhận publish theo semantics của nó; consumer acknowledgement là cơ chế riêng để xác nhận delivery đã được xử lý.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Framework — STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [RabbitMQ — Queues and Durability](https://www.rabbitmq.com/docs/queues)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
