# Vai trò của @Controller và @MessageMapping trong xử lý RSocket

Trong Spring, RSocket handler được khai báo bằng các controller chuyên xử lý message. Annotation **@Controller** đánh dấu một Spring bean có thể tham gia xử lý message; **@MessageMapping** gắn một route RSocket với method cụ thể. Khi request đến, Spring tìm method phù hợp, chuyển payload và metadata thành tham số, gọi handler, rồi chuyển giá trị hoặc publisher mà handler trả về thành kết quả của interaction.

Hai annotation có vai trò khác nhau: @Controller giúp Spring phát hiện và quản lý handler; @MessageMapping xác định request nào được chuyển đến method. Chúng không phải annotation HTTP như @GetMapping hay @PostMapping. Route RSocket là địa chỉ message ở tầng giao thức, được client gửi trong routing metadata.

## 1. Luồng xử lý từ client tới controller

Một ứng dụng Spring RSocket thường có các thành phần:

- RSocket server nhận kết nối và frame từ transport TCP hoặc WebSocket.
- RSocketMessageHandler phát hiện các method được đánh dấu để xử lý message.
- Spring mapping chọn method dựa trên route.
- Argument resolver chuyển payload, route variable và metadata thành tham số method.
- Handler thực hiện nghiệp vụ và trả về giá trị hoặc reactive publisher.
- Message handler chuyển kết quả thành payload hoặc stream response tương ứng.

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant T as RSocket Transport
    participant M as Spring Message Handler
    participant H as @Controller Handler
    participant S as Service
    C->>T: Request + routing metadata
    T->>M: RSocket message
    M->>M: Match @MessageMapping route
    M->>H: Resolve arguments and invoke method
    H->>S: Call business service
    S-->>H: Value / Mono / Flux
    H-->>M: Return result
    M-->>T: Encode response or stream
    T-->>C: Response payload(s)
~~~

Với publisher reactive, framework quản lý việc subscribe để thực hiện interaction. Handler nên trả về Mono hoặc Flux thay vì tự gọi subscribe() bên trong method. Nhờ đó framework có thể quan sát tín hiệu hoàn tất, lỗi và cancellation.

## 2. @Controller đăng ký một message handler

**@Controller** là stereotype của Spring, được phát hiện trong component scanning giống các controller khác. Một class có annotation này trở thành bean trong ApplicationContext. Spring RSocket infrastructure tìm các method mapping trên bean đó để đăng ký route.

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import reactor.core.publisher.Mono;

@Controller
public class GreetingController {

    @MessageMapping("greetings.say")
    public Mono<GreetingReply> say(
            @Payload GreetingRequest request) {
        return Mono.just(new GreetingReply(
            "Hello, " + request.name()));
    }
}
~~~

Trong ví dụ:

- @Controller đánh dấu GreetingController là bean do Spring quản lý.
- @MessageMapping("greetings.say") gắn route greetings.say với method say.
- @Payload cho biết tham số lấy từ phần data của message.
- Mono<GreetingReply> biểu diễn một response bất đồng bộ.

Nếu class không được Spring phát hiện hoặc không được đăng ký trong ApplicationContext, route sẽ không được đăng ký và client có thể gặp lỗi không tìm thấy handler. Vì vậy, cần đặt controller trong phạm vi component scan hoặc cấu hình bean tường minh.

Không cần thêm @RestController chỉ để xử lý RSocket. @RestController hướng tới HTTP response body; với message handling, @Controller là stereotype phù hợp.

## 3. @MessageMapping ánh xạ route RSocket

@MessageMapping khai báo route mà client có thể gọi. Route là một chuỗi định danh trong routing metadata, ví dụ:

- greetings.say
- orders.find
- prices.watch
- telemetry.channel

Client tạo request bằng RSocketRequester:

~~~java
Mono<GreetingReply> reply = requester
    .route("greetings.say")
    .data(new GreetingRequest("Lan"))
    .retrieveMono(GreetingReply.class);
~~~

Giá trị truyền vào route(...) phải khớp với mapping ở server. Route được truyền như metadata của giao thức RSocket, không phải URL HTTP. Nó không có nghĩa server sẽ tạo endpoint REST như /greetings/say.

Một method có thể được gọi từ nhiều client nếu các client cùng tuân thủ hợp đồng route, payload, MIME type và interaction model. Vì thế route là một phần của API công khai giữa hai peer; nên đặt tên ổn định, có quy ước namespace và tránh thay đổi tùy tiện.

### Route template và biến đích

Khi cần lấy một phần của route, có thể khai báo template variable và nhận bằng @DestinationVariable. Cú pháp phân đoạn route phụ thuộc RouteMatcher được cấu hình; client và server phải dùng cùng quy ước phân tách.

Ví dụ khái niệm:

~~~java
@Controller
public class RoomController {

    @MessageMapping("rooms.{roomId}.info")
    public Mono<RoomInfo> info(
            @DestinationVariable String roomId) {
        return roomService.findRoom(roomId);
    }
}
~~~

Client gọi route cụ thể tương ứng, chẳng hạn rooms.team-a.info. Nếu ứng dụng dùng route matcher tùy chỉnh, hãy kiểm tra cách matcher diễn giải dấu phân tách và template variable trước khi công bố route.

## 4. Phân biệt route, payload và metadata

Một message RSocket có thể mang data và metadata. Spring ánh xạ chúng vào những tham số khác nhau:

| Thành phần | Vai trò | Cách nhận trong handler |
|---|---|---|
| Route | Chọn handler | @MessageMapping |
| Data payload | Nội dung nghiệp vụ | @Payload hoặc tham số payload |
| Destination variable | Một phần của route template | @DestinationVariable |
| Metadata/header | Thông tin phụ trợ đã được cấu hình để ánh xạ | @Header hoặc @Headers |

Ví dụ nhận payload và một header:

~~~java
@MessageMapping("orders.find")
public Mono<OrderView> find(
        @Payload FindOrderRequest request,
        @Header("traceId") String traceId) {

    return orderService.find(request.orderId(), traceId);
}
~~~

Header chỉ có mặt nếu metadata tương ứng được gửi và được cấu hình để Spring ánh xạ. Nếu header là bắt buộc, hãy kiểm tra trường hợp thiếu hoặc sai định dạng thay vì giả định mọi peer đều gửi đủ.

Không dùng metadata do client tự khai báo làm bằng chứng quyền truy cập. Các giá trị như userId, tenantId hoặc role phải được xác thực bằng cơ chế bảo mật của phiên và kiểm tra quyền ở tầng nghiệp vụ.

## 5. Request-response: một request, một response

Với request-response, method nhận một payload và trả về tối đa một kết quả. Kiểu trả về thường là Mono<Response> hoặc một giá trị đơn giản.

~~~java
public record FindOrderRequest(String orderId) {}

public record OrderView(
    String orderId,
    String status
) {}

@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<OrderView> find(
            @Payload FindOrderRequest request) {
        return orderService.find(request.orderId());
    }
}
~~~

Client nhận bằng retrieveMono:

~~~java
Mono<OrderView> order = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);
~~~

Nếu không có dữ liệu, service có thể trả Mono.empty() nếu hợp đồng cho phép response rỗng; hoặc phát lỗi nghiệp vụ nếu client cần phân biệt không tìm thấy. Hãy thống nhất cách biểu diễn kết quả giữa client và server.

## 6. Fire-and-forget: nhận request mà không trả response payload

Fire-and-forget dùng khi client gửi một sự kiện hoặc lệnh mà không cần response payload ở cấp giao thức. Handler thường trả về Mono<Void> hoặc void.

~~~java
public record AuditEvent(
    String eventId,
    String action,
    Instant occurredAt
) {}

@Controller
public class AuditController {

    private final AuditService auditService;

    public AuditController(AuditService auditService) {
        this.auditService = auditService;
    }

    @MessageMapping("audit.record")
    public Mono<Void> record(@Payload AuditEvent event) {
        return auditService.append(event);
    }
}
~~~

Client gọi:

~~~java
Mono<Void> sent = requester
    .route("audit.record")
    .data(event)
    .send();
~~~

Fire-and-forget không cung cấp response payload để xác nhận server đã lưu thành công. Việc Mono<Void> hoàn tất trong handler chỉ là vòng đời xử lý phía server; client send() không phải acknowledgement nghiệp vụ rằng công việc đã được commit. Nếu cần xác nhận tiếp nhận hoặc kết quả xử lý, dùng request-response với một DTO acknowledgement.

## 7. Request-stream: một request, nhiều response

Request-stream nhận một request ban đầu rồi phát nhiều phần tử response. Handler thường nhận DTO và trả về Flux<Response>.

~~~java
public record PriceSubscription(String symbol) {}

public record PriceTick(
    String symbol,
    BigDecimal price,
    Instant time
) {}

@Controller
public class PriceController {

    private final PriceService priceService;

    public PriceController(PriceService priceService) {
        this.priceService = priceService;
    }

    @MessageMapping("prices.watch")
    public Flux<PriceTick> watch(
            @Payload PriceSubscription request) {
        return priceService.watch(request.symbol());
    }
}
~~~

Client nhận bằng retrieveFlux:

~~~java
Flux<PriceTick> ticks = requester
    .route("prices.watch")
    .data(new PriceSubscription("ACME"))
    .retrieveFlux(PriceTick.class);
~~~

Spring chuyển các phần tử Flux thành các payload response. RSocket sử dụng demand/REQUEST_N để điều tiết số phần tử responder được phép phát. Nếu client chậm, responder phải tuân thủ demand thay vì phát vượt số credit đã cấp.

Handler cũng cần phản ứng với cancellation. Khi client hủy subscription, publisher phía server nên dừng nguồn dữ liệu và giải phóng tài nguyên như cursor, listener hoặc buffer.

## 8. Request-channel: hai hướng đều là stream

Request-channel cho phép client gửi nhiều request trong khi server phát nhiều response. Phía server thường nhận Flux<Request> và trả về Flux<Response>.

~~~java
public record SensorCommand(
    String deviceId,
    String operation
) {}

public record SensorResult(
    String deviceId,
    String status
) {}

@Controller
public class SensorChannelController {

    private final SensorService sensorService;

    public SensorChannelController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @MessageMapping("sensors.channel")
    public Flux<SensorResult> channel(
            @Payload Flux<SensorCommand> commands) {

        return commands.concatMap(
            command -> sensorService.execute(command));
    }
}
~~~

Client gửi publisher và nhận publisher response:

~~~java
Flux<SensorCommand> commands = commandSource();

Flux<SensorResult> results = requester
    .route("sensors.channel")
    .data(commands)
    .retrieveFlux(SensorResult.class);
~~~

Trong channel, demand ở hai hướng được quản lý độc lập. Client cấp nhu cầu cho response stream; server cấp nhu cầu cho request stream mà nó nhận. Việc một phía hoàn tất gửi không nhất thiết kết thúc hướng còn lại.

Dùng concatMap khi cần giữ thứ tự xử lý. Nếu dùng flatMap, hãy giới hạn concurrency và xác định rõ thứ tự response có còn quan trọng hay không. Không nên tạo queue hoặc số tác vụ đồng thời không giới hạn.

## 9. Cách Spring chọn method và chuyển tham số

Khi message đến, Spring dùng route để tìm method mapping. Sau đó các argument resolver xử lý tham số method dựa trên annotation và kiểu dữ liệu.

Các tham số thường gặp:

- @Payload: lấy nội dung data sau khi được codec/message converter giải mã.
- @DestinationVariable: lấy giá trị từ route template.
- @Header: lấy một header/metadata đã được ánh xạ.
- @Headers: lấy tập header được ánh xạ vào Map hoặc kiểu tương thích.
- Principal: lấy danh tính đã được security infrastructure cung cấp nếu ứng dụng đã cấu hình xác thực.

Nếu method có một tham số payload đơn giản, Spring có thể suy ra payload argument mà không cần viết @Payload trong mọi trường hợp. Tuy nhiên, dùng @Payload tường minh giúp chữ ký dễ đọc khi có nhiều tham số.

Các kiểu Java trong method phải tương thích với codec hai phía. Nếu client gửi JSON nhưng server cấu hình MIME type hoặc codec không phù hợp, lỗi có thể xuất hiện trước khi method được gọi.

## 10. Giá trị trả về quyết định response

Spring hỗ trợ giá trị đơn và reactive publisher. Kiểu trả về cần phù hợp interaction model mà client khởi tạo.

| Giá trị trả về | Cách hiểu thường dùng |
|---|---|
| Một object | Một response đồng bộ |
| Mono<T> | Tối đa một response bất đồng bộ |
| Flux<T> | Nhiều response theo thời gian |
| void | Không có response payload |
| Mono<Void> | Hoàn tất xử lý bất đồng bộ, không có response payload |

Với publisher, framework quản lý subscription. Không gọi subscribe() trong handler rồi trả về void, vì như vậy công việc bị tách khỏi request lifecycle và lỗi không được gắn đúng với interaction.

Không gọi block() trên event-loop hoặc trong reactive request path. Nếu phải dùng API blocking, cô lập tác vụ trên scheduler phù hợp, đặt concurrency limit và timeout.

## 11. Xử lý lỗi bằng @MessageExceptionHandler

Một controller có thể khai báo @MessageExceptionHandler để chuyển exception từ handler thành phản hồi lỗi có cấu trúc hoặc thông điệp phù hợp với hợp đồng ứng dụng.

~~~java
public record ErrorReply(String code, String message) {}

@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<OrderView> find(@Payload FindOrderRequest request) {
        return orderService.find(request.orderId())
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(request.orderId())));
    }

    @MessageExceptionHandler
    public ErrorReply handle(OrderNotFoundException error) {
        return new ErrorReply(
            "ORDER_NOT_FOUND",
            "Không tìm thấy đơn hàng");
    }
}
~~~

Exception handler cần tránh trả stack trace, câu SQL, token hoặc thông tin nội bộ. Có thể dùng @ControllerAdvice cho xử lý chung nếu phiên bản Spring và cấu hình message handler của ứng dụng hỗ trợ phạm vi đó.

Lỗi trong request-response thường kết thúc request hiện tại. Lỗi trong request-stream hoặc request-channel có thể kết thúc stream tương ứng. Nếu lỗi của một phần tử không nên kết thúc cả stream, hãy chuyển lỗi thành một DTO kết quả thất bại bên trong pipeline.

## 12. @ConnectMapping dành cho giai đoạn SETUP

@ConnectMapping là annotation khác, dùng cho message ở giai đoạn thiết lập kết nối RSocket. Nó có thể nhận thông tin setup metadata/payload để xác thực, khởi tạo ngữ cảnh kết nối hoặc gắn thông tin peer với phiên.

~~~java
@Controller
public class ConnectionController {

    @ConnectMapping
    public Mono<Void> onConnect(
            @Payload ClientSetup setup,
            RSocketRequester requester) {
        return connectionService.register(setup, requester);
    }
}
~~~

@ConnectMapping không thay thế @MessageMapping. Dùng @ConnectMapping cho setup/connection lifecycle; dùng @MessageMapping cho các route message nghiệp vụ sau khi phiên đã sẵn sàng. Chữ ký chính xác và các tham số được hỗ trợ cần đối chiếu phiên bản Spring đang dùng.

## 13. Kiểm thử route và controller

Có thể kiểm tra method handler bằng unit test với StepVerifier:

~~~java
StepVerifier.create(
        controller.find(new FindOrderRequest("ORD-1001")))
    .expectNextMatches(order ->
        order.orderId().equals("ORD-1001"))
    .verifyComplete();
~~~

Unit test xác nhận logic publisher, nhưng chưa xác nhận route được đăng ký hay payload được encode/decode đúng. Integration test nên khởi chạy RSocket server và client thật để kiểm tra:

1. Route đã được Spring phát hiện và đăng ký.
2. Client gọi đúng route và nhận response đúng kiểu.
3. Request-stream phát nhiều phần tử và tuân thủ demand.
4. Request-channel nhận Flux đầu vào và trả Flux đầu ra.
5. Fire-and-forget không bị hiểu nhầm là acknowledgement.
6. Metadata/header được ánh xạ đúng.
7. Validation và @MessageExceptionHandler tạo lỗi phù hợp.
8. Cancellation dừng nguồn stream và giải phóng tài nguyên.
9. Controller không bị thiếu do component scanning hoặc bean registration.

## 14. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy route | Controller không được scan hoặc route không khớp | Kiểm tra bean và chuỗi @MessageMapping |
| Payload decode lỗi | MIME type hoặc codec không tương thích | Kiểm tra data MIME type và serializer |
| Handler nhận null/thiếu tham số | Payload/header không được gửi hoặc ánh xạ sai | Kiểm tra @Payload, @Header và metadata |
| Request-stream chỉ phát một phần tử | Handler trả Mono thay vì Flux hoặc nguồn đã hoàn tất | Kiểm tra kiểu trả về và publisher |
| Channel không nhận được request stream | Handler signature không nhận Flux<Request> | Kiểm tra interaction model và chữ ký method |
| Client nghĩ FNF đã được xử lý thành công | Nhầm send completion với acknowledgement nghiệp vụ | Dùng request-response nếu cần xác nhận |
| Stream tiếp tục chạy sau khi client rời đi | Nguồn không phản ứng với cancellation | Thêm doOnCancel, cleanup và API có thể hủy |

## 15. Checklist thiết kế annotated controller

- Controller được Spring quản lý qua component scanning hoặc bean registration.
- Mỗi route có tên rõ ràng và không xung đột.
- @MessageMapping khớp với route client gửi.
- Chữ ký handler phù hợp request-response, fire-and-forget, request-stream hoặc request-channel.
- Payload và metadata có MIME type/codec tương thích.
- Dùng DTO chuyên biệt và validation đầu vào.
- Quyền truy cập được kiểm tra theo principal và tài nguyên thực tế.
- Publisher được trả về framework; không tự subscribe hoặc block.
- Stream có chính sách demand, cancellation và cleanup.
- Lỗi được ánh xạ an toàn, có mã ổn định.
- Integration test xác nhận route thực sự hoạt động qua RSocket.

## 16. Kết luận

**@Controller** đăng ký một Spring bean có thể xử lý message; **@MessageMapping** liên kết route RSocket với method cụ thể. Spring tìm handler theo route, giải mã payload/metadata thành tham số, gọi method và chuyển giá trị trả về thành response hoặc stream.

Bốn interaction model được biểu đạt qua chữ ký method: request-response thường trả Mono<T>, fire-and-forget trả Mono<Void> hoặc void, request-stream trả Flux<T>, và request-channel nhận Flux<Request> rồi trả Flux<Response>. @ConnectMapping xử lý giai đoạn setup, tách biệt với các route nghiệp vụ.

Khi triển khai, hãy giữ route và DTO như một hợp đồng giữa client/server, để framework quản lý publisher, và thiết kế validation, lỗi, demand cùng cancellation ngay từ đầu. Đây là nền tảng để các ứng dụng Java dùng Spring RSocket xử lý giao tiếp bất đồng bộ và realtime có cấu trúc, dễ kiểm thử và vận hành.

Tài liệu tham khảo:
- [Spring Framework Reference – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference – Annotated Controllers](https://docs.spring.io/spring-framework/reference/rsocket-annotated-controllers.html)
- [Spring Framework Javadoc – MessageMapping](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html)

