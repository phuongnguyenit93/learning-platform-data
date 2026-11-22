# Lựa chọn JMS, STOMP hoặc RSocket theo đối tượng giao tiếp

JMS, STOMP và RSocket đều giúp các thành phần trao đổi message, nhưng chúng phục vụ những kiểu giao tiếp khác nhau. Chọn đúng công nghệ bắt đầu từ câu hỏi **ai đang nói chuyện với ai, cần tương tác theo kiểu nào, và message phải sống được bao lâu**.

- Chọn **JMS** khi các ứng dụng backend cần gửi lệnh hoặc sự kiện qua broker, tách producer khỏi consumer, xử lý bất đồng bộ, queue/topic, acknowledgement và transaction theo khả năng của provider.
- Chọn **STOMP** khi server cần trao đổi message với browser hoặc mobile client qua WebSocket, quản lý subscription và phát sự kiện tới nhiều session/destination.
- Chọn **RSocket** khi hai service hoặc client/server cần giao tiếp hai chiều, request-response hoặc stream với Reactive Streams backpressure qua một kết nối lâu dài.

Không nên chọn chỉ theo tiêu chí tốc độ. Hãy xác định trước yêu cầu về offline delivery, durability, fan-out, request/reply, streaming, backpressure, số lượng client và khả năng vận hành broker.

## 1. Phân biệt protocol, API và broker

Ba tên gọi này không nằm cùng một tầng:

| Công nghệ | Bản chất | Spring API thường dùng | Hạ tầng giao tiếp |
| --- | --- | --- | --- |
| JMS | Java/Jakarta messaging API và programming model chuẩn hóa | `JmsTemplate`, `JmsClient` (Spring Framework 7), `@JmsListener` | JMS provider/broker như ActiveMQ Artemis hoặc IBM MQ |
| STOMP | Text-based messaging protocol với frame `CONNECT`, `SEND`, `SUBSCRIBE`, `MESSAGE`, `ACK`... | Spring WebSocket/STOMP, `@MessageMapping`, `SimpMessagingTemplate` | WebSocket endpoint và simple broker hoặc external STOMP broker relay |
| RSocket | Binary application protocol cho multiplexed, duplex messaging | `RSocketRequester`, `@MessageMapping`, `@ConnectMapping` | TCP, WebSocket hoặc byte-stream transport tương thích; thường kết nối trực tiếp requester-responder |

JMS là API mà ứng dụng Java dùng để làm việc với provider; broker thực hiện lưu trữ, định tuyến và giao message. STOMP định nghĩa format và semantics của frame; WebSocket chỉ cung cấp kênh hai chiều để truyền frame. RSocket định nghĩa protocol tương tác và flow control trên một transport dạng byte stream. Spring cung cấp programming model cho từng lựa chọn, nhưng không biến chúng thành cùng một loại hạ tầng.

## 2. Bảng quyết định nhanh

| Đối tượng giao tiếp / nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Backend service gửi command cho worker xử lý sau | JMS Queue | Producer và consumer tách rời; broker giữ message theo cấu hình provider khi consumer chưa sẵn sàng |
| Nhiều backend service cần nhận cùng một business event | JMS Topic hoặc broker pub/sub | Mỗi subscription có thể nhận bản sao theo semantics của provider |
| Ứng dụng cần request/reply nhưng vẫn muốn đi qua broker | JMS request/reply | Có thể dùng reply-to destination và correlation id; cần quản lý timeout và temporary/durable reply destination |
| Browser cần nhận notification hoặc cập nhật UI trực tiếp | STOMP over WebSocket | Browser duy trì session, subscribe destination và nhận server push |
| Nhiều browser cần nhận cùng một sự kiện realtime | STOMP topic/destination | Broker fan-out tới các subscription đang hoạt động |
| Browser gửi command lên Spring server qua message destination | STOMP over WebSocket | `@MessageMapping`, destination routing và Spring Security message authorization |
| Service cần gọi service khác và nhận một kết quả | RSocket Request-Response hoặc HTTP | RSocket hỗ trợ async request/reply qua connection; HTTP thường đơn giản hơn nếu không cần connection messaging |
| Service cần nhận một stream dữ liệu với backpressure | RSocket Request-Stream | Demand được truyền qua Reactive Streams boundary |
| Hai phía cần vừa gửi vừa nhận stream | RSocket Channel | Hỗ trợ request stream hai chiều trên cùng interaction |
| Công việc phải được giữ khi consumer offline hoặc restart | JMS với persistence/transaction phù hợp | RSocket và STOMP session messaging không tự cung cấp durable work queue mặc định |
| Cần phát telemetry realtime tới client nhưng vẫn lưu event bền vững cho backend | JMS + STOMP | JMS xử lý event backend; một service phát notification qua STOMP tới các client đang online |

Đây là quy tắc định hướng. Một công nghệ có thể hỗ trợ nhiều kiểu giao tiếp, nhưng cần cấu hình và hợp đồng ứng dụng phù hợp. Ví dụ JMS cũng có request/reply, STOMP có broker relay, và RSocket có Fire-and-Forget; điều đó không làm các công nghệ có cùng semantics về durability hoặc fan-out.

## 3. JMS: giao tiếp backend qua broker

### 3.1. Khi nào nên chọn JMS?

JMS phù hợp khi đối tượng giao tiếp là các ứng dụng Java/backend hoặc worker chạy độc lập và message cần được broker quản lý. Producer có thể gửi message rồi tiếp tục công việc; consumer nhận và xử lý khi có năng lực. Điều này hữu ích cho:

- Lệnh xử lý đơn hàng, gửi email, tạo hóa đơn hoặc chạy tác vụ nền.
- Tích hợp hệ thống doanh nghiệp qua broker dùng chung.
- Phát business event tới nhiều consumer bằng Topic.
- Queue công việc với competing consumers để tăng throughput.
- Request/reply bất đồng bộ qua queue khi hai hệ thống cần correlation và timeout rõ ràng.

JMS định nghĩa hai mô hình destination cơ bản:

| Destination | Cách giao nhận | Trường hợp thường dùng |
| --- | --- | --- |
| Queue (point-to-point) | Mỗi message được một consumer trong nhóm nhận xử lý; nhiều consumer cạnh tranh lấy việc | Work queue, command, job |
| Topic (publish-subscribe) | Mỗi subscription phù hợp nhận một bản sao của message | Domain event cần nhiều hệ thống quan tâm |

Topic subscription có thể là non-durable hoặc durable tùy provider và cấu hình. Durable subscription cho phép subscriber nhận message được publish trong thời gian nó offline, theo chính sách lưu trữ của broker. Cần định danh subscription/client phù hợp và cấu hình retention, expiration, quota của broker.

### 3.2. Spring JMS API

`JmsTemplate` là API trung tâm để gửi và nhận message; `@JmsListener` khai báo consumer. Spring Framework 7 còn có `JmsClient` với API fluent cho send/receive và tích hợp message conversion. Ví dụ gửi một command:

```java
jmsTemplate.convertAndSend("orders.commands", command);
```

Ví dụ listener xử lý command:

```java
@Component
public class OrderCommandListener {

    @JmsListener(destination = "orders.commands",
                 containerFactory = "ordersListenerFactory")
    public void handle(OrderCommand command) {
        orderService.process(command);
    }
}
```

Đây là các snippet minh họa; `OrderCommand`, `orderService` và `ordersListenerFactory` là thành phần ứng dụng. `DefaultJmsListenerContainerFactory` thường được dùng để cấu hình listener container, concurrency, transaction và acknowledgement.

```java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        return factory;
    }
}
```

`sessionTransacted=true` làm mỗi lần listener invocation chạy trong một JMS local transaction. Nếu listener ném exception trước khi commit, việc nhận message có thể rollback và provider có thể redeliver theo policy. Đây không tự động tạo transaction phân tán nguyên tử với database hoặc HTTP service; cần thiết kế outbox, idempotency hoặc XA nếu thực sự cần phối hợp nhiều resource.

### 3.3. Durability và delivery guarantee không tự động

Không nên suy ra “dùng JMS là chắc chắn không mất message”. Kết quả phụ thuộc delivery mode, persistence, broker policy, acknowledgement, transaction và cách consumer xử lý:

- Message persistent yêu cầu provider lưu message theo semantics của provider; message non-persistent có thể không được giữ khi broker dừng.
- Với `AUTO_ACKNOWLEDGE`, Spring cảnh báo có thể mất message khi listener lỗi hoặc container dừng trong một số trường hợp. Nếu cần reliability cho queue hoặc durable topic subscription, cân nhắc transacted session hoặc acknowledgement mode phù hợp.
- Transactional receive giúp rollback message khi listener thất bại, nhưng có thể tạo duplicate khi JVM chết ở ranh giới commit/ack. Consumer vẫn cần idempotency.
- `DefaultMessageListenerContainer` hỗ trợ recovery khi broker dừng; mặc định sử dụng backoff đơn giản, có thể cấu hình `BackOff` riêng.
- Dead-letter, retry limit, TTL, redelivery delay và poison-message handling thường là cấu hình provider/broker.

Chọn JMS khi cần broker quản lý công việc và có thể vận hành broker, schema, queue/topic, retention, transaction và monitoring. Nếu chỉ cần một lệnh đồng bộ đơn giản giữa hai service, HTTP có thể ít phức tạp hơn.

## 4. STOMP: giao tiếp với browser và client session

### 4.1. Khi nào nên chọn STOMP?

STOMP thường phù hợp khi đối tượng giao tiếp là browser hoặc mobile app đang giữ kết nối realtime với server. WebSocket tạo kênh hai chiều lâu dài; STOMP bổ sung protocol frame và destination để client gửi, subscribe và nhận message mà không phải tự thiết kế một protocol riêng.

Ví dụ:

- Dashboard nhận cập nhật trạng thái đơn hàng hoặc telemetry.
- Chat, collaboration, presence và notification.
- Client subscribe `/topic/rooms/42` để nhận sự kiện của một room.
- Client gửi command tới `/app/orders.create` để Spring route tới `@MessageMapping`.
- Server gửi notification tới `/user/queue/notifications` cho session/user cụ thể.

### 4.2. Luồng message trong Spring

```text
Browser / Mobile
      | WebSocket + STOMP frames
      v
clientInboundChannel
      |
      +-- /app/... --> @MessageMapping controller
      |                    |
      |                    v
      |               brokerChannel
      |                    |
      +----------------> Message broker
                           |
                           v
                    clientOutboundChannel
                           |
                           v
                    WebSocket sessions
```

Spring thường cấu hình application prefix `/app` và broker prefixes như `/topic` hoặc `/queue`. Message gửi tới `/app/...` được route tới annotated controller; message gửi tới broker destination được broker xử lý theo subscription. `SimpMessagingTemplate` cho phép gửi message từ bất kỳ component server-side nào.

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

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
```

Controller nhận command và phát kết quả:

```java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/rooms")
    public ChatMessage send(ChatMessage message) {
        return chatService.accept(message);
    }
}
```

Đoạn code là ví dụ minh họa; trong ứng dụng thực tế cần xác thực người gửi, kiểm tra quyền tham gia room và validate payload. Client có thể subscribe `/topic/rooms` và gửi tới `/app/chat.send`.

### 4.3. Simple broker hay external broker relay?

Spring có hai lựa chọn broker phổ biến:

| Lựa chọn | Đặc điểm | Khi dùng |
| --- | --- | --- |
| Simple broker | Chạy trong bộ nhớ của một Spring application instance; hỗ trợ các tính năng STOMP cơ bản | Demo, development hoặc ứng dụng nhỏ một node với nhu cầu đơn giản |
| External broker relay | Spring relay STOMP frames tới broker ngoài như RabbitMQ hoặc ActiveMQ | Production nhiều node, broker subscriptions, clustering và broker-specific delivery features |

Simple broker không phải durable queue cluster và không chia sẻ subscription state giữa nhiều application server. Nếu cần scale nhiều node hoặc broker-managed destination, dùng external broker relay và cấu hình broker tương ứng. Dù có broker ngoài, cần kiểm tra cụ thể ACK mode, durable subscription, receipts, retention và reconnect behavior; STOMP protocol tự nó không hứa mọi message sẽ được lưu cho client offline.

### 4.4. User destination, session và bảo mật

`/user/queue/...` là destination logic mà Spring phân giải theo user/session. `convertAndSendToUser` hoặc `@SendToUser` có thể gửi notification tới các session phù hợp. Đây là lựa chọn tốt cho server push cá nhân hóa, nhưng user destination chỉ định tuyến tới session đang hoạt động; nếu notification phải còn sau khi user offline, lưu nó bền vững ở database hoặc broker và cho client truy vấn lại.

STOMP cần bảo mật cả HTTP handshake lẫn message destinations. Dùng Spring Security để xác thực session, giới hạn ai được `SEND` hoặc `SUBSCRIBE` tới destination nào, kiểm tra quyền user/tenant và bảo vệ broker relay credentials. Không coi destination name là cơ chế authorization.

### 4.5. Giới hạn cần cân nhắc

- WebSocket là kết nối lâu dài; proxy, load balancer, mobile network hoặc browser sleep có thể ngắt kết nối. Cần heartbeat, reconnect và khôi phục subscription.
- Simple broker giữ state trong memory; node restart làm mất subscription và broker state.
- Topic broadcast thường nhắm tới subscriber đang hoạt động; offline delivery phải thiết kế riêng.
- Nhiều session và subscriber tạo chi phí connection, memory và outbound fan-out.
- Nếu chỉ có vài cập nhật mỗi phút, HTTP polling hoặc Server-Sent Events có thể đơn giản hơn WebSocket.

## 5. RSocket: giao tiếp hai chiều và reactive streaming

### 5.1. Khi nào nên chọn RSocket?

RSocket phù hợp khi hai phía cần giao tiếp trực tiếp qua một connection lâu dài, có nhiều request đang hoạt động đồng thời hoặc cần stream dữ liệu với backpressure. Nó hữu ích cho:

- Service-to-service request-response bất đồng bộ.
- Server trả stream dữ liệu theo nhu cầu consumer, thay vì đẩy vô hạn.
- Hai bên vừa gửi vừa nhận stream command/event qua Channel.
- Client hoặc server cần khởi tạo request; hai phía không bị khóa vào vai trò client/server sau khi connection thiết lập.
- Ứng dụng reactive muốn truyền demand qua network boundary và hạn chế buffer.

RSocket là application protocol chạy trên TCP, WebSocket hoặc transport dạng byte stream khác. Nó hỗ trợ multiplexing và duplex interactions trên một connection. Các interaction model chính:

| Interaction | Hướng giao tiếp | Spring/Reactor biểu diễn | Ví dụ |
| --- | --- | --- | --- |
| Request-Response | Một request, một response | `Mono<T>` | Lấy thông tin quote hiện tại |
| Request-Stream | Một request, nhiều response | `Flux<T>` | Stream giá hoặc telemetry |
| Channel | Stream request và stream response hai chiều | `Flux` hai phía | Trao đổi trạng thái realtime hai chiều |
| Fire-and-Forget | Gửi một message không chờ response nghiệp vụ | `Mono<Void>` khi gửi | Gửi tín hiệu không cần kết quả trực tiếp |

Reactive Streams semantics cho phép requester gửi demand (`request(n)`) để responder không phát nhiều phần tử hơn consumer có thể nhận. Đây là backpressure xuyên qua network boundary, khác với việc chỉ tăng queue buffer ở một bên.

### 5.2. Spring RSocket responder

Spring hỗ trợ annotated responder bằng `@MessageMapping` và `@ConnectMapping`. `@MessageMapping` xử lý request riêng lẻ; `@ConnectMapping` xử lý sự kiện ở cấp connection như setup/metadata push.

```java
@Controller
public class QuoteRSocketController {

    private final QuoteService quoteService;

    public QuoteRSocketController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("quotes.latest")
    public Mono<Quote> latest(QuoteRequest request) {
        return quoteService.latest(request);
    }

    @MessageMapping("quotes.stream")
    public Flux<Quote> stream(QuoteRequest request) {
        return quoteService.stream(request);
    }
}
```

### 5.3. Spring RSocket requester

`RSocketRequester` là fluent API để gửi object data/metadata và nhận object response:

```java
RSocketRequester requester = RSocketRequester.builder()
        .tcp("quotes.internal", 7000);

Mono<Quote> latest = requester.route("quotes.latest")
        .data(new QuoteRequest("VN-INDEX"))
        .retrieveMono(Quote.class);

Flux<Quote> stream = requester.route("quotes.stream")
        .data(new QuoteRequest("VN-INDEX"))
        .retrieveFlux(Quote.class);
```

Đây là snippet minh họa; `Quote`, `QuoteRequest` và `QuoteService` do ứng dụng định nghĩa. `RSocketRequester` có thể được tạo trước khi connection thực sự được thiết lập; connection được dùng khi request được thực hiện. Trong Spring Boot, `spring-boot-starter-rsocket` cung cấp auto-configuration cho requester builder, strategies và server handler theo cấu hình transport.

### 5.4. Những gì RSocket không tự cung cấp

RSocket không phải message broker. Protocol có connection, request stream, backpressure, keepalive và session resumption, nhưng không tự tạo một durable queue lưu business message khi responder offline. Nếu cần message tồn tại qua restart, retention, dead-letter, competing consumers hoặc fan-out tới nhiều subscriber độc lập, dùng broker như JMS hoặc một event platform; RSocket có thể bổ sung làm API realtime giữa service và client.

Session resumption giúp tiếp tục một RSocket session sau gián đoạn nếu hai phía cấu hình và duy trì state cần thiết. Nó không thay thế persistence của business event hoặc idempotency. Fire-and-Forget cũng không phải acknowledgement nghiệp vụ; nếu caller cần biết kết quả xử lý, dùng Request-Response hoặc một cơ chế acknowledgement riêng.

RSocket yêu cầu client/server cùng hỗ trợ protocol và codec, cấu hình authentication/authorization, timeout, reconnect/resume và observability. Browser có thể dùng RSocket over WebSocket nếu có client library phù hợp, nhưng STOMP thường có ecosystem và programming model phổ biến hơn cho web messaging.

## 6. So sánh sâu theo yêu cầu vận hành

| Tiêu chí | JMS | STOMP over WebSocket | RSocket |
| --- | --- | --- | --- |
| Đối tượng chính | Backend apps, workers, enterprise systems | Browser/mobile sessions và server push | Reactive services, clients và server endpoints |
| Kiểu tương tác | Queue, topic, request/reply | Send, subscribe, publish, user destination | Request-Response, Stream, Channel, Fire-and-Forget |
| Hạ tầng trung tâm | JMS provider/broker | WebSocket server; có thể có STOMP broker | RSocket server/connection; không cần broker mặc định |
| Durable/offline | Có thể, theo persistence, delivery mode, subscription và broker policy | Không tự có; phụ thuộc broker/client subscription configuration | Không có durable work queue mặc định |
| Fan-out | Topic/subscriptions | Broker topic và session subscriptions | Phải thiết kế interaction/service fan-out; không phải broker pub/sub mặc định |
| Backpressure | Thường qua consumer flow control/prefetch của provider | STOMP broker/client-specific flow control; không có Reactive Streams demand xuyên protocol mặc định | Reactive Streams backpressure là tính năng protocol |
| Kết nối | Thường broker connection do client/container quản lý | WebSocket connection lâu dài theo client session | Connection lâu dài, multiplexed |
| Request/reply | Có thể qua reply-to/correlation; thường cần timeout và quản lý reply destination | Có thể request/reply theo application convention và destination | Native Request-Response interaction |
| Browser support | Không phải lựa chọn trực tiếp thông thường cho browser | Rất phù hợp với browser qua WebSocket | Có thể qua WebSocket và client tương thích |
| Cluster/scaling | Scale broker/consumer theo provider | Scale WebSocket nodes và external broker relay | Scale connection endpoints; service discovery/load balancing riêng |
| Vận hành | Broker persistence, queue depth, consumer, DLQ, transaction | Session, subscription, heartbeat, broker relay, outbound fan-out | Connection, keepalive, lease, stream demand, resume, timeout |

Không có lựa chọn thắng ở mọi hàng. JMS thường tối ưu cho decoupling và broker-managed work; STOMP cho live client messaging; RSocket cho interaction reactive giữa hai endpoint.

## 7. Quy trình chọn công nghệ

Trả lời các câu hỏi theo thứ tự:

1. **Người nhận có thể offline trong lúc message được gửi không?** Nếu phải lưu và giao lại sau, bắt đầu từ JMS hoặc broker có durable semantics. Nếu chỉ cần cập nhật cho session online, STOMP có thể phù hợp.
2. **Có cần browser/mobile nhận push theo subscription không?** Nếu có, STOMP over WebSocket thường là lựa chọn tự nhiên.
3. **Có cần stream hai chiều và backpressure end-to-end không?** Nếu có, đánh giá RSocket.
4. **Có cần queue/topic, competing consumers, redelivery, DLQ hoặc transaction với broker không?** Nếu có, JMS/provider hoặc broker messaging phù hợp hơn.
5. **Có cần một kết quả duy nhất cho request, nhiều response theo stream hay stream hai chiều?** Request-response/stream/channel là điểm mạnh rõ ràng của RSocket; JMS/STOMP có thể xây dựng request/reply nhưng cần tự quản lý correlation và timeout theo contract.
6. **Hệ thống đã có broker nào?** Nếu doanh nghiệp đã vận hành JMS provider, tận dụng nó có thể giảm chi phí vận hành. Nếu có RabbitMQ và browser clients, STOMP broker relay có thể phù hợp. Nếu backend đã reactive và cần streaming, RSocket đáng đánh giá.
7. **Team có thể vận hành kết nối lâu dài, session và reconnect không?** STOMP/RSocket đòi hỏi quản lý lifecycle connection. JMS đòi hỏi vận hành broker, persistence, queue, DLQ và consumer health.
8. **Có cần giao tiếp qua network/proxy công cộng không?** WebSocket/RSocket over WebSocket có thể gặp proxy idle timeout; JMS broker connection thường dành cho network service-to-service được kiểm soát. Kiểm thử hạ tầng thực tế trước khi chốt.

## 8. Các kiến trúc kết hợp thường gặp

### 8.1. JMS cho backend, STOMP cho UI

Đây là mẫu phổ biến khi business event cần được xử lý bền vững nhưng người dùng cũng cần cập nhật realtime:

```text
Order Service
    |
    v
JMS queue/topic ----> Billing / Inventory / Audit consumers
    |
    v
Notification Service
    |
    v
STOMP broker relay
    |
    v
Browser sessions: /user/queue/notifications
```

JMS giữ business event theo chính sách broker; Notification Service chuyển một kết quả đã xử lý thành message phù hợp với client online. Nếu browser offline, notification service có thể lưu notification vào database để client lấy lại sau.

### 8.2. RSocket cho query/stream, JMS cho business event

Service có thể dùng RSocket để truy vấn trạng thái hoặc nhận stream realtime từ một service khác; khi có business event cần lưu bền vững và fan-out tới nhiều consumer, service publish event qua JMS. Như vậy interaction realtime và durable event distribution có contract riêng.

### 8.3. STOMP cho UI, HTTP cho thao tác CRUD

Không cần chuyển mọi thao tác web sang STOMP. HTTP/REST phù hợp cho form submit, truy vấn tài nguyên và CRUD thông thường; STOMP dùng cho push, presence, chat và live updates. Chọn protocol theo nhu cầu từng luồng, không ép một protocol bao phủ toàn bộ ứng dụng.

## 9. Những lựa chọn sai thường gặp

- Dùng STOMP simple broker làm durable queue cho business command quan trọng. Simple broker là broker đơn giản trong bộ nhớ; message/session state không có durability như broker chuyên dụng.
- Dùng RSocket Fire-and-Forget rồi coi việc gửi thành công là consumer đã commit dữ liệu. Fire-and-Forget không trả acknowledgement nghiệp vụ.
- Dùng JMS cho browser trực tiếp mà không có gateway/protocol adapter. Browser thường cần WebSocket/STOMP hoặc HTTP API.
- Dùng RSocket chỉ vì muốn tốc độ cao nhưng không có nhu cầu stream/backpressure hoặc duplex. HTTP có thể dễ vận hành hơn.
- Dùng STOMP topic như durable offline inbox. Subscription online và durable subscription là hai semantics khác nhau; cần xác minh broker/client hỗ trợ.
- Cho rằng JMS persistent message tự đảm bảo exactly-once business processing. Redelivery/duplicate vẫn có thể xảy ra; consumer cần idempotency.
- Coi WebSocket, STOMP và broker là cùng một thành phần. WebSocket là transport; STOMP là sub-protocol; broker xử lý destination/subscription.
- Chọn công nghệ mà không đo reconnect, timeout, queue backlog, consumer lag, connection count, fan-out và failure recovery.

## 10. Checklist trước khi triển khai

- Viết rõ producer, consumer và ai sở hữu message sau khi gửi.
- Chọn interaction contract: command, event, request/reply, stream hoặc notification.
- Định nghĩa message schema, versioning, content type, correlation id và idempotency key.
- Xác định persistence, TTL, acknowledgement, redelivery, retry, dead-letter và offline behavior.
- Xác định thứ tự cần giữ: global, per queue, per key, per user session hay per stream.
- Cấu hình authentication, authorization, broker ACL, TLS và bảo vệ thông tin xác thực.
- Kiểm thử broker restart, consumer crash, client disconnect, timeout, duplicate delivery và schema incompatibility.
- Theo dõi queue depth, oldest-message age, consumer lag, delivery failures, redelivery, connection count, subscription count và latency.
- Đặt giới hạn concurrency, prefetch/buffer, stream demand, connection idle timeout và retry backoff.
- Có runbook vận hành broker, relay, WebSocket sessions hoặc RSocket connections tương ứng.

## 11. Ghi nhớ

- **JMS:** backend-to-backend qua broker; chọn khi cần queue/topic, decoupling, persistence, transaction/acknowledgement và worker processing theo khả năng provider.
- **STOMP:** server-to-browser/mobile qua WebSocket; chọn khi cần destination, subscription, broadcast, user destination và live UI updates.
- **RSocket:** service/client-to-service với interaction hai chiều; chọn khi cần request-response, stream, channel và Reactive Streams backpressure.
- JMS durability phụ thuộc provider và cấu hình; STOMP broker/client semantics phụ thuộc broker; RSocket không tự là durable broker.
- Có thể kết hợp nhiều công nghệ: JMS lưu business event, STOMP cập nhật client, RSocket cung cấp query hoặc stream realtime.
- Chọn theo đối tượng giao tiếp, semantics của message và khả năng vận hành, không chỉ theo độ trễ.

## Tài liệu tham khảo

- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework Reference — Receiving JMS Messages and Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework Reference — STOMP Messaging](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework Reference — Benefits of STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/benefits.html)
- [Spring Framework Reference — Sending STOMP Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot Reference — RSocket Support](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html)