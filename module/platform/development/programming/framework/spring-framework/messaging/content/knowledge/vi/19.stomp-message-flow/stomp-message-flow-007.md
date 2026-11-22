# Đường đi của thông điệp phát từ server tới subscriber

## Mục tiêu

Sau bài này, bạn có thể:

- Mô tả toàn bộ đường đi của một thông điệp do server phát tới các STOMP subscriber.
- Phân biệt `brokerChannel`, `clientOutboundChannel` và `clientInboundChannel`.
- Dùng `SimpMessagingTemplate` để gửi thông điệp từ service, HTTP endpoint hoặc tác vụ nền.
- Hiểu cách giá trị trả về từ `@MessageMapping` đi qua broker và tới subscriber.
- Phân biệt broadcast tới destination chung với gửi tới một user qua `/user/`.
- Theo dõi khác biệt giữa simple broker và STOMP broker relay.
- Hiểu vai trò của subscription registry, outbound executor, thứ tự gửi và trạng thái broker.
- Xác định vì sao gửi thành công vào channel chưa đồng nghĩa với subscriber đã xử lý thông điệp.

## 1. Bức tranh tổng thể

Trong Spring STOMP over WebSocket, server không tự tìm từng WebSocket session để ghi dữ liệu. Server tạo một Spring `Message<?>`, gửi message tới broker channel; broker tìm những subscription khớp destination và phát STOMP `MESSAGE` tới các client tương ứng.

Luồng server phát tới một destination chung:

~~~text
Service / HTTP controller / scheduled task
                 |
                 v
       SimpMessagingTemplate
                 |
                 v
       Spring Message<?>
       destination + headers + payload
                 |
                 v
           brokerChannel
                 |
                 v
       Simple broker handler
       hoặc STOMP broker relay
                 |
                 v
       Tìm subscription khớp destination
                 |
                 v
       clientOutboundChannel
                 |
                 v
       STOMP encode / WebSocket handler
                 |
                 v
          WebSocket session
                 |
                 v
          Client nhận MESSAGE
~~~

Nếu message gửi tới destination dạng `/user/`, Spring xử lý thêm bước phân giải user destination trước khi broker định tuyến:

~~~text
SimpMessagingTemplate
        |
        v
   brokerChannel
        |
        v
UserDestinationMessageHandler
        |
        v
Destination riêng theo user/session
        |
        v
       Broker
        |
        v
clientOutboundChannel -> WebSocket -> client
~~~

Spring dùng ba channel chính:

| Channel | Hướng | Vai trò |
|---|---|---|
| `clientInboundChannel` | Client → server | Nhận các STOMP frame từ WebSocket client sau khi decode |
| `brokerChannel` | Server → broker | Nhận message được phát từ code server để broker xử lý |
| `clientOutboundChannel` | Server → client | Chuyển message từ broker tới WebSocket session tương ứng |

Các channel này tạo ranh giới giữa nơi tạo message, nơi định tuyến và nơi ghi message xuống kết nối client. Đây là phần cốt lõi của server-side message flow trong Spring Framework 7.0.10.

## 2. Subscriber phải đăng ký trước

Trước khi server phát message, client thường đã kết nối STOMP và gửi `SUBSCRIBE` tới destination muốn nhận.

Ví dụ client đăng ký nhận cập nhật giá:

~~~text
SUBSCRIBE
id:quotes-ui
destination:/topic/quotes
ack:auto

^@
~~~

Spring nhận frame qua WebSocket, decode thành Spring `Message<?>` và gửi vào `clientInboundChannel`. Broker handler xử lý yêu cầu subscribe và lưu subscription trong registry của broker.

Sau khi subscription được đăng ký, broker mới có thông tin để định tuyến message tới client. Một client có thể đăng ký nhiều destination hoặc nhiều subscription cho cùng destination; mỗi subscription có ID riêng.

Điểm quan trọng: server phát message tới destination, còn broker chịu trách nhiệm tìm subscriber phù hợp. Code nghiệp vụ thường không cần biết session ID hoặc WebSocket connection cụ thể của từng subscriber.

## 3. Phát message từ bất kỳ thành phần server nào

Cách phổ biến nhất là inject `SimpMessagingTemplate` và gọi `convertAndSend`.

~~~java
@Service
public class QuotePublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public QuotePublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(QuoteUpdate update) {
        messagingTemplate.convertAndSend("/topic/quotes", update);
    }
}
~~~

`SimpMessagingTemplate` chuyển payload thành Spring `Message<?>` bằng message converter phù hợp, gắn destination và gửi message tới `brokerChannel`.

Đoạn code này có thể được gọi từ:

- Service sau khi nghiệp vụ cập nhật thành công.
- HTTP controller sau khi nhận REST request.
- Scheduled task phát dữ liệu định kỳ.
- Application event listener sau khi một domain event xảy ra.
- Một thành phần xử lý dữ liệu nền hoặc nhận kết quả từ hệ thống khác.

Ví dụ gọi từ HTTP endpoint:

~~~java
@RestController
@RequestMapping("/api/quotes")
public class QuoteRestController {

    private final QuotePublisher publisher;

    public QuoteRestController(QuotePublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping
    public ResponseEntity<Void> publish(@RequestBody QuoteUpdate update) {
        publisher.publish(update);
        return ResponseEntity.accepted().build();
    }
}
~~~

Khi REST request hoàn tất, message đã được gửi qua messaging infrastructure theo cấu hình. HTTP response `202 Accepted` trong ví dụ chỉ là quyết định của endpoint; nó không chứng minh trình duyệt đã nhận hoặc xử lý message.

### convertAndSend và send

Dùng `convertAndSend(destination, payload)` khi muốn Spring chuyển một object thành message.

~~~java
messagingTemplate.convertAndSend(
        "/topic/orders",
        new OrderUpdate("ORD-1001", "SHIPPED")
);
~~~

Dùng `send(Message<?>)` khi đã có Spring `Message<?>` và muốn kiểm soát header:

~~~java
Message<OrderUpdate> message = MessageBuilder
        .withPayload(new OrderUpdate("ORD-1001", "SHIPPED"))
        .setHeader("eventType", "OrderShipped")
        .build();

messagingTemplate.send(
        MessageBuilder.fromMessage(message)
                .setHeader(SimpMessageHeaderAccessor.DESTINATION_HEADER, "/topic/orders")
                .build()
);
~~~

Với message đã tạo sẵn, header destination phải có giá trị hợp lệ. Có thể dùng `SimpMessageHeaderAccessor` để tạo và thiết lập các header messaging chuyên dụng thay vì tự đặt tên header tùy ý.

## 4. BrokerChannel làm gì?

`brokerChannel` là `MessageChannel` mà server-side application code dùng để gửi message tới broker. `SimpMessagingTemplate` được Spring cấu hình để gửi vào channel này.

Khi message đi vào `brokerChannel`:

1. Spring chuyển payload thành Spring `Message<?>` và gắn destination.
2. Các broker-side handler nhận message từ channel.
3. Nếu destination là user destination, `UserDestinationMessageHandler` phân giải destination trước khi broker xử lý.
4. Simple broker hoặc broker relay tiếp nhận message đã định tuyến.
5. Broker tìm các subscription khớp destination.
6. Broker phát message tới `clientOutboundChannel` cho từng subscriber phù hợp.

`brokerChannel` không phải WebSocket channel và cũng không phải nơi lưu message cho client. Nó là điểm chuyển message từ code server sang cơ chế định tuyến của broker.

### Message có thể đến từ controller hoặc service

Một HTTP controller và một service nền có thể gửi cùng destination:

~~~java
messagingTemplate.convertAndSend("/topic/system-status", status);
~~~

Điều này cho phép các nguồn phát khác nhau dùng cùng cơ chế định tuyến. Subscriber không cần biết message đến từ HTTP request, scheduler hay một service khác.

## 5. Giá trị trả về từ @MessageMapping cũng đi qua broker

Một nguồn server-side message khác là giá trị trả về từ method có `@MessageMapping`.

~~~java
@Controller
public class GreetingController {

    @MessageMapping("/greeting")
    @SendTo("/topic/greetings")
    public GreetingReply greet(GreetingRequest request) {
        return new GreetingReply(
                request.name(),
                "Hello, " + request.name()
        );
    }
}
~~~

Client gửi request tới destination ứng dụng:

~~~text
SEND
destination:/app/greeting
content-type:application/json

{"name":"Lan"}^@
~~~

Luồng xử lý:

1. Frame được decode và chuyển vào `clientInboundChannel`.
2. Prefix `/app` định tuyến message tới annotated controller.
3. Spring gọi `GreetingController.greet(...)`.
4. Giá trị trả về được message converter chuyển thành payload.
5. `@SendTo("/topic/greetings")` đặt destination outbound.
6. Spring gửi message qua `brokerChannel`.
7. Broker tìm các subscription ở `/topic/greetings`.
8. Broker phát STOMP `MESSAGE` qua `clientOutboundChannel` tới các subscriber.

Nếu không dùng `@SendTo`, Spring có thể suy ra destination mặc định từ destination đầu vào: ví dụ `/app/greeting` được ánh xạ thành `/topic/greeting`. Dùng `@SendTo` khi muốn khai báo rõ destination hoặc phát tới nhiều destination.

`@SendTo` là tiện ích dựa trên cơ chế gửi message tương tự `SimpMessagingTemplate`. Với logic phức tạp, controller có thể inject template và chủ động phát message từ method.

### @SubscribeMapping có đường đi khác

`@SubscribeMapping` xử lý một frame subscribe tới destination ứng dụng. Theo mặc định, giá trị trả về được gửi trực tiếp tới client qua `clientOutboundChannel`, không đi qua `brokerChannel` để broadcast và không được lưu thành một subscription broker lâu dài.

Ví dụ:

~~~java
@Controller
public class DashboardController {

    @SubscribeMapping("/dashboard/snapshot")
    public DashboardSnapshot snapshot() {
        return dashboardService.currentSnapshot();
    }
}
~~~

Client subscribe tới `/app/dashboard/snapshot` để nhận snapshot ban đầu. Sau đó, client có thể subscribe tới `/topic/dashboard-updates` để nhận các cập nhật liên tục qua broker.

Dùng cách này khi cần phản hồi một lần cho subscriber. Nếu muốn gửi tới broker và broadcast, có thể kết hợp `@SendTo` hoặc dùng `SimpMessagingTemplate`.

## 6. Gửi tới một user bằng /user/

Broadcast destination như `/topic/quotes` gửi message tới mọi subscription phù hợp. Khi cần gửi dữ liệu riêng cho một user, Spring cung cấp user destination.

Client subscribe:

~~~text
SUBSCRIBE
id:private-alerts
destination:/user/queue/alerts
ack:auto

^@
~~~

Server gửi tới user có tên `alice`:

~~~java
messagingTemplate.convertAndSendToUser(
        "alice",
        "/queue/alerts",
        new Alert("Your report is ready")
);
~~~

Spring nhận destination logic `/user/alice/queue/alerts`, tìm các session đang hoạt động của user đó và chuyển thành destination vật lý riêng theo session, ví dụ:

~~~text
/user/alice/queue/alerts
          |
          v
/queue/alerts-user-sessionA
/queue/alerts-user-sessionB
~~~

Client vẫn subscribe bằng destination chung `/user/queue/alerts`; client không cần biết suffix nội bộ.

Theo mặc định, nếu một user có nhiều session, các session đang subscribe destination đó đều có thể nhận message. Với `@SendToUser`, có thể đặt `broadcast = false` để chỉ gửi về session đã phát request hiện tại.

User destination thường dựa trên `Principal` được xác định khi WebSocket handshake. Vì vậy cần cấu hình authentication và đảm bảo tên user mà server truyền cho `convertAndSendToUser` khớp với identity mà Spring quản lý.

### User destination trong nhiều server

Nếu ứng dụng chạy nhiều node, user có thể kết nối vào node khác với node đang phát message. Có thể cấu hình `userDestinationBroadcast` để phát các user destination chưa phân giải cho các node khác thử xử lý.

Khi dùng external broker, cần xem chính sách dọn destination/queue riêng theo session của broker để tránh giữ lại queue không còn hoạt động.

## 7. Simple broker và broker relay

Spring có hai cách chính để xử lý subscription và broadcast.

| Đặc điểm | Simple broker | STOMP broker relay |
|---|---|---|
| Subscription registry | Trong bộ nhớ của ứng dụng Spring | Do broker bên ngoài quản lý |
| Định tuyến | Spring simple broker handler | Relay qua STOMP/TCP tới broker |
| Phạm vi | Phù hợp ứng dụng đơn giản, một node | Phù hợp broker chuyên dụng và triển khai nhiều node |
| Tính năng STOMP | Chỉ hỗ trợ một phần protocol | Phụ thuộc broker bên ngoài |
| Lưu trữ và redelivery | Không cung cấp message persistence như broker chuyên dụng | Theo cấu hình và khả năng của broker |

### Simple broker

Cấu hình:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Simple broker lưu subscription trong bộ nhớ và phát message tới các client đang kết nối có destination khớp. Nó hỗ trợ destination dạng path và pattern. Subscription registry mất khi ứng dụng dừng.

Simple broker phù hợp cho ứng dụng nhỏ hoặc khi cần bắt đầu nhanh. Nó chỉ hỗ trợ một phần STOMP; các tính năng như ACK, receipt và clustering cần được kiểm tra theo tài liệu phiên bản Spring đang dùng.

### STOMP broker relay

Khi dùng broker bên ngoài, cấu hình thay bằng:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("localhost")
            .setRelayPort(61613)
            .setSystemLogin("system")
            .setSystemPasscode("system-secret")
            .setClientLogin("web")
            .setClientPasscode("web-secret");
}
~~~

Relay chuyển message từ server tới broker qua một kết nối TCP dùng chung gọi là **system connection**. Kết nối này dành cho message phát sinh từ server-side application. Relay còn tạo kết nối TCP riêng cho mỗi WebSocket client để chuyển tiếp các frame của client tới broker và nhận message broker gửi lại.

Khi broker phát message tới client, relay chuyển frame về Spring, rồi message đi qua `clientOutboundChannel` và được ghi xuống WebSocket session phù hợp.

Broker relay có cơ chế reconnect system connection khi broker tạm thời mất kết nối. Tuy nhiên, WebSocket client vẫn cần logic reconnect của riêng nó. Broker bên ngoài phải bật STOMP support và cấu hình destination, credential, heartbeat, ACL và chính sách queue phù hợp.

## 8. clientOutboundChannel và thứ tự message

Sau khi broker tìm thấy subscriber, message được gửi vào `clientOutboundChannel`. Channel này phân phối message tới WebSocket session tương ứng; Spring chuyển message thành STOMP frame và ghi xuống socket.

Trong cấu hình mặc định, outbound channel được hỗ trợ bởi thread pool. Nhiều message có thể được xử lý trên các thread khác nhau, vì vậy thứ tự client quan sát được có thể khác thứ tự broker phát hành.

Nếu ứng dụng cần giữ thứ tự publish trong cùng một client session, bật:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

Khi bật, message trong cùng client session được publish qua `clientOutboundChannel` lần lượt theo thứ tự. Tùy chọn này có một chi phí hiệu năng nhỏ; chỉ bật khi thứ tự thực sự là yêu cầu nghiệp vụ.

Giữ thứ tự outbound không thay thế sequence number ở tầng nghiệp vụ. Nếu client cần phát hiện message bị thiếu, duplicate hoặc đến sai thứ tự do retry/reconnect ở hệ thống khác, hãy đưa sequence/version vào payload và để client kiểm tra.

## 9. Gửi message không đồng nghĩa subscriber đã xử lý

Các bước sau là những sự kiện khác nhau:

1. `SimpMessagingTemplate` gửi Spring message tới `brokerChannel`.
2. Broker nhận message và tìm subscriber.
3. Spring/broker chuyển STOMP `MESSAGE` xuống WebSocket.
4. Client nhận frame.
5. Ứng dụng client parse payload và xử lý nghiệp vụ.

Kết quả gửi thành công ở bước 1 không chứng minh bước 4 hoặc 5 đã hoàn tất. Nếu cần xác nhận nghiệp vụ, hãy thiết kế response/event có correlation ID hoặc một giao thức acknowledgement phù hợp.

Một số lưu ý:

- Simple broker phát cho subscription đang tồn tại; nó không phải kho message bền vững để client offline nhận lại sau.
- Với broker relay, durability, queue retention, redelivery và acknowledgement phụ thuộc broker cùng cấu hình subscription.
- Nếu destination không có subscriber khớp, không có client nào nhận message từ lần phát đó.
- Nếu payload cần JSON, cấu hình message converter phù hợp và kiểm tra schema giữa server/client.
- Tránh gửi object lớn hoặc phát tần suất quá cao; theo dõi kích thước frame, số subscriber, outbound queue và thời gian gửi.

## 10. BrokerAvailabilityEvent và lỗi gửi

Khi dùng broker relay, kết nối system tới broker có thể mất rồi được khôi phục. Spring phát `BrokerAvailabilityEvent` để ứng dụng biết broker đang available hay unavailable.

Có thể theo dõi event:

~~~java
@Component
public class BrokerStatusListener
        implements ApplicationListener<BrokerAvailabilityEvent> {

    @Override
    public void onApplicationEvent(BrokerAvailabilityEvent event) {
        if (event.isBrokerAvailable()) {
            log.info("STOMP broker is available");
        }
        else {
            log.warn("STOMP broker is unavailable");
        }
    }
}
~~~

Thành phần gửi message nên quan sát trạng thái này và vẫn xử lý `MessageDeliveryException` khi gọi template. Không giả định broker relay luôn sẵn sàng chỉ vì WebSocket client còn kết nối.

Các event khác hữu ích cho vận hành:

- `SessionConnectEvent`: client bắt đầu STOMP session.
- `SessionConnectedEvent`: broker đã trả CONNECTED.
- `SessionSubscribeEvent`: client đăng ký subscription.
- `SessionUnsubscribeEvent`: client hủy subscription.
- `SessionDisconnectEvent`: STOMP session kết thúc; event này có thể được phát nhiều lần cho cùng session, vì vậy xử lý phải idempotent.

## 11. Ví dụ tích hợp: server phát sự kiện đơn hàng

Các class dưới đây là các bean tích hợp trong ứng dụng Spring MVC + WebSocket đã bật STOMP. Đây là ví dụ cấu hình ứng dụng, không phải chương trình Java standalone.

Cấu hình endpoint và broker:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Payload:

~~~java
public record OrderUpdate(
        String orderId,
        String status,
        long version
) {}
~~~

Publisher:

~~~java
@Service
public class OrderEventPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(OrderUpdate update) {
        messagingTemplate.convertAndSend("/topic/order-updates", update);
    }

    public void publishForUser(String username, OrderUpdate update) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/order-updates",
                update
        );
    }
}
~~~

HTTP endpoint kích hoạt publish:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderUpdateController {

    private final OrderEventPublisher publisher;

    public OrderUpdateController(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/{orderId}/status")
    public ResponseEntity<Void> updateStatus(
            @PathVariable String orderId,
            @RequestBody StatusRequest request) {

        OrderUpdate update = new OrderUpdate(
                orderId,
                request.status(),
                request.version()
        );

        // Trong ứng dụng thật, gọi publisher sau khi business update commit.
        publisher.publish(update);

        return ResponseEntity.accepted().build();
    }
}

public record StatusRequest(String status, long version) {}
~~~

Client subscribe:

~~~text
SUBSCRIBE
id:order-updates-ui
destination:/topic/order-updates
ack:auto

^@
~~~

Khi HTTP endpoint gọi publisher, message đi qua `brokerChannel`, broker tìm subscription `order-updates-ui`, sau đó Spring gửi STOMP `MESSAGE` xuống WebSocket session:

~~~text
MESSAGE
destination:/topic/order-updates
subscription:order-updates-ui
message-id:broker-message-id
content-type:application/json

{"orderId":"ORD-1001","status":"SHIPPED","version":3}^@
~~~

Header `message-id` và cách biểu diễn header native phụ thuộc broker/protocol handler. Payload JSON được tạo từ `OrderUpdate` qua message converter đã cấu hình.

## 12. Lỗi thường gặp

1. **Gọi template nhưng client không nhận được.** Kiểm tra client đã SUBSCRIBE trước khi publish và destination có khớp hay không.
2. **Gửi nhầm prefix.** `/app` thường dành cho controller mapping; `/topic` và `/queue` thường dành cho broker theo cấu hình Spring.
3. **Cho rằng brokerChannel gửi thẳng tới socket.** Channel này chuyển message tới broker handler để định tuyến.
4. **Tự quản lý WebSocket session trong service.** Dùng `SimpMessagingTemplate` để broker chọn các session theo subscription.
5. **Dùng /topic để gửi riêng tư.** Dùng `convertAndSendToUser` và client subscribe `/user/queue/...`.
6. **Dùng /user nhưng broker nhận trực tiếp.** Cấu hình destination prefix để `UserDestinationMessageHandler` xử lý trước broker.
7. **Cho rằng @SubscribeMapping tạo subscription lâu dài.** Return value mặc định được gửi trực tiếp cho client như response một lần.
8. **Cho rằng @SendTo gửi trực tiếp qua WebSocket.** Return value vẫn đi qua brokerChannel và broker.
9. **Cho rằng mọi subscriber nhận message ngay cả khi offline.** Simple broker giữ subscription trong memory; delivery cho client offline phụ thuộc broker và durable subscription.
10. **Giả định thứ tự outbound luôn được giữ.** Bật `setPreservePublishOrder(true)` khi yêu cầu thứ tự theo session.
11. **Coi HTTP 202 hoặc template send thành công là client đã xử lý.** Muốn biết business processing hoàn tất, cần acknowledgement/event response riêng.
12. **Bỏ qua broker availability.** Với broker relay, theo dõi `BrokerAvailabilityEvent` và xử lý `MessageDeliveryException`.
13. **Cấu hình relay nhưng broker chưa bật STOMP.** Kiểm tra STOMP listener port, credentials, virtual host và heartbeat của broker.
14. **Không kiểm tra quyền subscribe và send.** Bảo vệ endpoint, destination và user destination theo identity của phiên WebSocket.
15. **Gửi payload không có schema ổn định.** Dùng DTO/record, version hoặc event type và kiểm thử converter ở cả hai phía.

## 13. Checklist kiểm thử

- [ ] Client kết nối đúng STOMP endpoint và nhận CONNECTED.
- [ ] Client gửi SUBSCRIBE tới destination dự kiến.
- [ ] Kiểm tra subscription đã được broker đăng ký trước khi publish.
- [ ] Gọi `SimpMessagingTemplate.convertAndSend` từ một service hoặc HTTP endpoint.
- [ ] Xác nhận message đi qua brokerChannel và tới broker handler.
- [ ] Xác nhận chỉ subscriber có destination khớp nhận STOMP MESSAGE.
- [ ] Kiểm tra payload converter, content type và headers.
- [ ] Kiểm thử `@MessageMapping` return value và `@SendTo`.
- [ ] Kiểm thử `@SubscribeMapping` response trực tiếp.
- [ ] Kiểm thử `convertAndSendToUser` với user có một và nhiều session.
- [ ] Kiểm thử simple broker và broker relay nếu ứng dụng hỗ trợ cả hai.
- [ ] Kiểm tra outbound ordering khi nhiều message được publish nhanh.
- [ ] Ngắt broker relay và xác nhận BrokerAvailabilityEvent cùng xử lý lỗi gửi.
- [ ] Kiểm thử trường hợp không có subscriber hoặc subscriber disconnect.
- [ ] Xác minh client reconnect và resubscribe sau khi WebSocket mất kết nối.

## 14. Kết luận

Thông điệp phát từ server bắt đầu ở service, controller hoặc tác vụ nền. `SimpMessagingTemplate` chuyển payload thành Spring `Message<?>` và gửi tới `brokerChannel`. Broker xử lý destination, tìm các subscription phù hợp và phát message qua `clientOutboundChannel`; Spring encode thành STOMP `MESSAGE` rồi ghi xuống WebSocket session. Với `/user/`, Spring phân giải destination thành địa chỉ riêng theo user/session trước khi broker định tuyến. Simple broker giữ subscription trong bộ nhớ; broker relay chuyển message qua kết nối TCP tới broker chuyên dụng. Cần kiểm tra thứ tự outbound, trạng thái broker và acknowledgement ở tầng ứng dụng để biết message đã tới subscriber và được xử lý đến đâu.

## Tài liệu tham khảo chính thức

- [Spring Framework 7.0.10 Reference: Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html) — ba channel, luồng từ controller tới broker và từ broker tới clientOutboundChannel.
- [Spring Framework 7.0.10 Reference: Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html) — dùng SimpMessagingTemplate từ bất kỳ application component nào.
- [Spring Framework 7.0.10 Reference: Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html) — return value, @SendTo, @SendToUser và @SubscribeMapping.
- [Spring Framework 7.0.10 Reference: User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html) — phân giải /user destination theo user/session.
- [Spring Framework 7.0.10 Reference: Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html) — lưu subscription trong memory và broadcast tới destination khớp.
- [Spring Framework 7.0.10 Reference: External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html) — broker relay và kết nối TCP.
- [Spring Framework 7.0.10 Reference: Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html) — system connection, client connections, heartbeat và reconnect.
- [Spring Framework 7.0.10 Reference: Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html) — thứ tự xử lý clientOutboundChannel và setPreservePublishOrder.
- [Spring Framework 7.0.10 Reference: Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html) — BrokerAvailabilityEvent và STOMP session lifecycle events.
