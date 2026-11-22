# @EnableWebSocketMessageBroker và WebSocketMessageBrokerConfigurer

## Mục tiêu

Spring Framework hỗ trợ STOMP chạy trên WebSocket để xây dựng ứng dụng giao tiếp hai chiều theo mô hình publish/subscribe. Annotation @EnableWebSocketMessageBroker bật hạ tầng xử lý STOMP; interface WebSocketMessageBrokerConfigurer cho phép ứng dụng đăng ký endpoint, chọn message broker, cấu hình các channel, transport, converter và các điểm mở rộng khác.

Sau bài này, bạn có thể:

- Giải thích vai trò của @EnableWebSocketMessageBroker và WebSocketMessageBrokerConfigurer.
- Đăng ký STOMP endpoint qua StompEndpointRegistry.
- Phân biệt URL handshake với STOMP destination.
- Cấu hình application destination prefix và broker destination prefix.
- Hiểu message flow qua clientInboundChannel, brokerChannel và clientOutboundChannel.
- Viết @Controller với @MessageMapping, @SubscribeMapping, @SendTo và @SendToUser.
- Chọn simple broker hoặc external STOMP broker relay.
- Gửi message từ service bằng SimpMessagingTemplate.
- Cấu hình user destination, heartbeat, SockJS, authentication, authorization và ChannelInterceptor.
- Điều chỉnh message converter, channel executor, thứ tự xử lý và giới hạn transport.
- Chạy ví dụ chat broadcast bằng Java 17+, Spring Boot 4.1.2 và STOMP.js.

## 1. STOMP là gì và vì sao dùng trên WebSocket?

WebSocket tạo một kết nối hai chiều giữa client và server. Bản thân WebSocket chỉ định nghĩa cách gửi text frame, binary frame và điều khiển connection; nó không quy định nội dung ứng dụng bên trong frame.

STOMP (Simple Text Oriented Messaging Protocol) là một messaging sub-protocol có thể chạy trên WebSocket. STOMP định nghĩa command, header, body và destination để client gửi, đăng ký nhận và trao đổi message theo một giao thức chung.

Một STOMP frame có cấu trúc khái quát:

~~~text
COMMAND
header-name:header-value
another-header:value

message body
^@
~~~

Ký hiệu ^@ ở cuối biểu thị byte null kết thúc frame STOMP. Ví dụ command thường gặp:

| Command | Hướng | Ý nghĩa |
|---|---|---|
| CONNECT hoặc STOMP | Client → Server | Mở STOMP session. |
| CONNECTED | Server → Client | Xác nhận STOMP session đã được mở. |
| SEND | Client → Server | Gửi message tới destination. |
| SUBSCRIBE | Client → Server | Đăng ký nhận message từ destination. |
| MESSAGE | Server → Client | Gửi message tới subscriber. |
| UNSUBSCRIBE | Client → Server | Hủy subscription. |
| DISCONNECT | Client → Server | Đóng STOMP session một cách chủ động. |
| RECEIPT | Server → Client | Xác nhận một frame khi broker hỗ trợ receipt. |
| ERROR | Server → Client | Báo lỗi STOMP protocol hoặc xử lý. |

STOMP giúp ứng dụng có quy ước rõ ràng cho routing và subscription. Client có thể dùng thư viện STOMP có sẵn thay vì tự thiết kế một protocol JSON riêng trên raw WebSocket.

### WebSocket endpoint và STOMP destination là hai khái niệm khác nhau

Một ứng dụng STOMP thường có endpoint URL và nhiều destination:

| Giá trị | Loại | Mục đích |
|---|---|---|
| /ws | WebSocket endpoint URL | Client mở kết nối và thực hiện HTTP Upgrade handshake tại đây. |
| /app/chat | Application destination | SEND tới đây được định tuyến vào method @MessageMapping. |
| /topic/chat | Broker destination | Client SUBSCRIBE để nhận các message broadcast. |
| /queue/notifications | Broker destination | Một quy ước destination dạng queue, tùy broker. |
| /user/queue/alerts | User destination | Spring chuyển thành destination riêng theo user/session. |

Client kết nối tới ws://localhost:8080/ws. Sau khi WebSocket mở, client gửi STOMP frame tới /app/chat hoặc đăng ký /topic/chat. Những destination này nằm trong header destination của STOMP frame; chúng không phải các URL handshake riêng.

## 2. @EnableWebSocketMessageBroker làm gì?

Annotation @EnableWebSocketMessageBroker bật hạ tầng STOMP messaging trên WebSocket cho ứng dụng Spring MVC.

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {
}
~~~

Khi annotation này được sử dụng, Spring đăng ký các thành phần cần thiết để:

- Ánh xạ HTTP/WebSocket endpoint.
- Thương lượng và xử lý STOMP sub-protocol.
- Chuyển STOMP frame thành Spring Message.
- Định tuyến message vào controller hoặc message broker.
- Gửi message từ broker về các WebSocket session.
- Quản lý subscription, user destination và lifecycle event.
- Cung cấp các channel để mở rộng xử lý message.

STOMP support thuộc hai module chính của Spring Framework:

- spring-messaging: abstraction Message, MessageChannel, MessageHandler và messaging annotation.
- spring-websocket: WebSocket transport, STOMP sub-protocol handling và endpoint integration.

Trong Spring Boot 4.1.2, có thể thêm spring-boot-starter-websocket để sử dụng WebSocket/STOMP trong ứng dụng MVC.

### Không nhầm với @EnableWebSocket

| Annotation | Hạ tầng | Cách xử lý |
|---|---|---|
| @EnableWebSocket | Raw WebSocket | WebSocketConfigurer, WebSocketHandlerRegistry và WebSocketHandler. |
| @EnableWebSocketMessageBroker | STOMP over WebSocket | WebSocketMessageBrokerConfigurer, StompEndpointRegistry, message channels, broker và @MessageMapping. |

Dùng @EnableWebSocket khi ứng dụng muốn tự định nghĩa protocol và xử lý frame trực tiếp. Dùng @EnableWebSocketMessageBroker khi muốn STOMP command, destination, subscription và message routing.

Không cần bật đồng thời hai annotation cho cùng endpoint nếu không có thiết kế tích hợp riêng.

## 3. WebSocketMessageBrokerConfigurer

WebSocketMessageBrokerConfigurer là interface để tùy chỉnh cấu hình do @EnableWebSocketMessageBroker tạo ra.

~~~java
public interface WebSocketMessageBrokerConfigurer {
    void registerStompEndpoints(StompEndpointRegistry registry);

    void configureMessageBroker(MessageBrokerRegistry registry);

    // Các callback mở rộng khác có default implementation.
}
~~~

Hai callback quan trọng nhất:

- registerStompEndpoints: đăng ký endpoint URL để client kết nối.
- configureMessageBroker: chọn broker và quy tắc định tuyến destination.

Các callback mở rộng thường dùng:

| Callback | Mục đích |
|---|---|
| configureClientInboundChannel | Cấu hình channel nhận message từ client; thường dùng để đăng ký ChannelInterceptor hoặc executor. |
| configureClientOutboundChannel | Cấu hình channel gửi message tới client. |
| configureBrokerChannel | Cấu hình channel gửi message từ code phía server tới broker. |
| configureWebSocketTransport | Cấu hình message size, send timeout, send buffer và thời gian chờ frame đầu tiên. |
| configureMessageConverters | Thêm hoặc tùy chỉnh MessageConverter cho payload. |
| addArgumentResolvers | Thêm argument resolver cho method được ánh xạ bằng annotation. |
| addReturnValueHandlers | Thêm handler cho kiểu return value tùy chỉnh. |

Có thể chỉ override những callback cần thiết. Các cấu hình mặc định của Spring vẫn được áp dụng cho phần còn lại.

## 4. Đăng ký STOMP endpoint bằng StompEndpointRegistry

Endpoint được đăng ký trong registerStompEndpoints:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
}
~~~

/ws là URL client dùng để bắt đầu WebSocket handshake. Sau khi handshake thành công, STOMP CONNECT được gửi trên cùng kết nối.

Có thể đăng ký nhiều endpoint:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws/chat");
    registry.addEndpoint("/ws/notifications");
}
~~~

Mỗi endpoint có thể có origin policy, interceptor, handshake handler hoặc SockJS setting riêng.

### Allowed origins

Ví dụ chỉ cho phép frontend tại một origin:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.com");
~~~

Có thể cho phép nhiều origin:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOrigins(
                "https://app.example.com",
                "https://admin.example.com"
        );
~~~

Hoặc dùng origin patterns khi cần:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOriginPatterns("https://*.example.com");
~~~

Origin gồm scheme, host và port nếu có. Chỉ cho phép các origin thực sự cần kết nối. Origin validation bảo vệ browser client trước một số tình huống cross-site WebSocket hijacking; nó không thay thế authentication hoặc authorization vì non-browser client có thể tự gửi header Origin.

### Handshake interceptor

Endpoint registration hỗ trợ handshake interceptor:

~~~java
registry.addEndpoint("/ws")
        .addInterceptors(handshakeInterceptor);
~~~

Interceptor chạy ở HTTP handshake, trước khi STOMP CONNECT được xử lý. Có thể dùng nó để kiểm tra request, truyền thuộc tính từ HTTP session hoặc ghi nhận metadata của connection.

Nếu cần kiểm tra từng STOMP frame như CONNECT, SEND hoặc SUBSCRIBE, hãy dùng ChannelInterceptor ở inbound channel. Handshake interceptor và ChannelInterceptor xử lý hai giai đoạn khác nhau.

### SockJS fallback

Có thể bật SockJS:

~~~java
registry.addEndpoint("/ws")
        .withSockJS();
~~~

Khi bật SockJS, client phải dùng SockJS client kết hợp STOMP client. Endpoint sẽ hỗ trợ các transport fallback như HTTP streaming hoặc long polling khi native WebSocket không khả dụng.

Nếu dùng native WebSocket client, không cấu hình server endpoint với SockJS rồi kết nối như thể đó là một endpoint WebSocket thuần.

## 5. configureMessageBroker và destination prefix

configureMessageBroker quyết định message nào đi vào application controller và message nào được chuyển thẳng tới broker.

Ví dụ phổ biến:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Cấu hình này tạo hai nhóm destination:

- /app: message client gửi tới đây được định tuyến vào method @MessageMapping.
- /topic và /queue: message được chuyển tới simple broker để quản lý subscription và broadcast.

Ví dụ:

~~~text
Client SEND /app/chat
        |
        v
Spring tìm @MessageMapping("/chat")
        |
        v
Controller xử lý
        |
        v
Controller trả kết quả tới /topic/chat
        |
        v
Broker tìm subscriber
        |
        v
Client nhận MESSAGE /topic/chat
~~~

### Application destination prefix

~~~java
registry.setApplicationDestinationPrefixes("/app");
~~~

Prefix /app giúp Spring phân biệt message gửi vào application code. Khi client gửi destination /app/chat, Spring loại bỏ prefix /app trước khi tìm mapping /chat.

Controller:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat")
    public void handle(ChatMessage message) {
        // Xử lý message tại đây.
    }
}
~~~

Client phải SEND tới /app/chat để gọi method trên.

Có thể đặt nhiều prefix:

~~~java
registry.setApplicationDestinationPrefixes("/app", "/service");
~~~

Dùng nhiều prefix khi ứng dụng muốn phân vùng namespace cho các nhóm controller.

### Broker destination prefix

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Các message có destination bắt đầu bằng những prefix này được chuyển tới broker. Client thường SUBSCRIBE /topic/chat để nhận broadcast.

Với simple broker tích hợp, /topic và /queue chỉ là quy ước đặt tên. Simple broker không áp đặt semantics queue/topic như một message broker đầy đủ. Khi dùng external broker, destination semantics phụ thuộc broker và cấu hình của nó.

### User destination prefix

Spring mặc định dùng /user cho destination riêng theo người dùng:

~~~text
/user/queue/alerts
~~~

Có thể tùy chỉnh:

~~~java
registry.setUserDestinationPrefix("/user");
~~~

Giữ prefix mặc định nếu không có lý do đổi. User destination được Spring chuyển thành destination cụ thể theo user hoặc session.

## 6. Simple broker và external broker relay

Spring có hai lựa chọn broker chính.

### Simple broker

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Simple broker được tích hợp trong Spring và lưu subscription trong bộ nhớ. Nó broadcast message tới các client đang kết nối và subscribe destination phù hợp.

Ưu điểm:

- Không cần cài thêm broker riêng.
- Dễ chạy local, demo và ứng dụng nhỏ.
- Phù hợp học luồng STOMP và kiểm thử chức năng cơ bản.
- Hỗ trợ destination dạng path và pattern.

Giới hạn:

- Subscription và trạng thái broker nằm trong bộ nhớ của application instance.
- Không phù hợp clustering nhiều instance.
- Chỉ hỗ trợ một phần STOMP command.
- Không hỗ trợ ACK, RECEIPT và một số khả năng nâng cao của STOMP.
- Không cung cấp durable messaging như broker chuyên dụng.
- Không nên dùng làm hạ tầng hàng đợi nghiệp vụ cần persistence và redelivery.

Simple broker phù hợp khi message chỉ cần broadcast tới client đang online và có thể mất khi server restart hoặc client disconnect.

### External STOMP broker relay

Khi cần broker đầy đủ, ứng dụng có thể relay message tới RabbitMQ, ActiveMQ hoặc broker hỗ trợ STOMP.

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue");
}
~~~

Broker relay là một MessageHandler của Spring. Nó mở TCP connection tới broker, chuyển message từ Spring tới broker và chuyển message từ broker về các WebSocket client.

Lợi ích:

- Broker quản lý subscription và broadcast.
- Có thể sử dụng ACK, RECEIPT và các STOMP command mà broker hỗ trợ.
- Hỗ trợ clustering và mở rộng qua broker.
- Có thể tận dụng persistence, security, routing và monitoring của broker.
- Nhiều application instance có thể kết nối cùng broker để phân phối message giữa các instance.

Broker relay cần cấu hình host, port, client/system login và passcode phù hợp. Broker phải bật STOMP protocol endpoint. Spring Framework yêu cầu các dependency TCP phù hợp, thường gồm Reactor Netty và Netty, khi sử dụng relay.

### So sánh

| Tiêu chí | Simple broker | Broker relay |
|---|---|---|
| Cài broker ngoài | Không | Có |
| Subscription | Lưu trong memory của Spring | Broker ngoài quản lý |
| ACK/RECEIPT | Không hỗ trợ đầy đủ | Theo khả năng broker |
| Durable messaging | Không | Có thể, tùy broker |
| Clustering | Không phù hợp | Hỗ trợ qua broker |
| Vận hành | Đơn giản | Cần quản lý broker và credentials |
| Use case | Demo, realtime broadcast đơn giản | Production, nhiều instance, broker features |

Không chuyển sang broker relay chỉ bằng cách đổi prefix. Cần cài broker, bật STOMP listener, cấu hình kết nối, credentials, destination policy và network access.

## 7. Luồng message bên trong Spring

Spring sử dụng các MessageChannel để tách việc nhận, xử lý và gửi message.

Ba channel quan trọng:

| Channel | Hướng | Vai trò |
|---|---|---|
| clientInboundChannel | Client → Spring | Nhận message sau khi STOMP frame được decode. |
| brokerChannel | Application → Broker | Gửi message từ controller hoặc service tới broker. |
| clientOutboundChannel | Broker/Spring → Client | Gửi message đã encode thành STOMP frame về WebSocket session. |

Luồng với simple broker:

~~~mermaid
flowchart TD
    A["Browser STOMP client"] --> B["WebSocket session"]
    B --> C["STOMP frame decoder"]
    C --> D["clientInboundChannel"]
    D --> E{"Destination prefix"}
    E -->|/app| F["@MessageMapping controller"]
    E -->|/topic hoặc /queue| G["Simple broker"]
    F --> H["brokerChannel"]
    H --> G
    G --> I["clientOutboundChannel"]
    I --> J["STOMP encoder"]
    J --> K["Subscribed WebSocket clients"]
~~~

Chi tiết:

1. Client kết nối tới endpoint /ws và gửi STOMP CONNECT.
2. Spring xác nhận STOMP session và gắn Principal nếu HTTP request đã xác thực.
3. Client gửi SEND hoặc SUBSCRIBE.
4. STOMP frame được decode thành Spring Message.
5. Message đi vào clientInboundChannel.
6. Destination /app được route tới method @MessageMapping.
7. Destination /topic hoặc /queue được chuyển tới broker.
8. Controller có thể trả về object; Spring dùng MessageConverter để serialize object thành payload.
9. Message được gửi qua brokerChannel.
10. Broker tìm các subscription phù hợp.
11. Message đi qua clientOutboundChannel và được encode thành STOMP MESSAGE frame.
12. Client nhận body và xử lý theo schema đã thống nhất.

Nếu dùng broker relay, bước broker sẽ chuyển message qua TCP tới external broker và nhận message broadcast trở lại.

## 8. @MessageMapping và annotated controller

Một class @Controller có thể khai báo các method xử lý STOMP message.

~~~java
@Controller
public class GreetingController {

    @MessageMapping("/greeting")
    @SendTo("/topic/greetings")
    public GreetingResponse greeting(GreetingRequest request) {
        return new GreetingResponse("Hello, " + request.name());
    }
}
~~~

Khi client SEND tới /app/greeting:

- Prefix /app được dùng để chọn application handler.
- Phần /greeting khớp @MessageMapping.
- Spring convert body thành GreetingRequest.
- Method xử lý và trả GreetingResponse.
- @SendTo định tuyến kết quả tới /topic/greetings.

### Tham số method thường dùng

| Tham số/annotation | Công dụng |
|---|---|
| @Payload | Lấy payload đã được MessageConverter chuyển đổi. |
| @Header | Lấy một header cụ thể. |
| @Headers | Lấy toàn bộ message headers dưới dạng Map. |
| @DestinationVariable | Lấy biến trong destination path. |
| Message<?> | Truy cập message và payload đầy đủ. |
| MessageHeaders | Đọc message headers. |
| SimpMessageHeaderAccessor | Truy cập typed Spring messaging headers. |
| StompHeaderAccessor | Đọc STOMP command/header. |
| Principal | Lấy user đã được xác thực tại HTTP handshake. |

Ví dụ dùng destination variable và header:

~~~java
@MessageMapping("/rooms/{roomId}/messages")
@SendTo("/topic/rooms/{roomId}")
public ChatMessage send(
        @DestinationVariable String roomId,
        @Header("simpSessionId") String sessionId,
        @Payload ChatMessage message) {

    return new ChatMessage(
            roomId,
            message.content(),
            sessionId
    );
}
~~~

Đối với message nghiệp vụ, nên dùng DTO rõ ràng. Không truyền entity database trực tiếp nếu nó chứa quan hệ lazy, trường nội bộ hoặc dữ liệu không nên gửi ra client.

### Validation và exception handling

Payload có thể dùng Jakarta Validation:

~~~java
@MessageMapping("/orders")
@SendTo("/topic/order-results")
public OrderResult createOrder(@Valid @Payload CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Nếu validator được cấu hình, payload không hợp lệ có thể tạo exception trong quá trình binding/validation.

Dùng @MessageExceptionHandler để chuyển lỗi thành response có cấu trúc:

~~~java
@MessageExceptionHandler
@SendToUser("/queue/errors")
public ApiError handleException(IllegalArgumentException exception) {
    return new ApiError("INVALID_REQUEST", exception.getMessage());
}
~~~

Không gửi stack trace hoặc thông tin nội bộ server về client. Response lỗi nên có error code ổn định và message phù hợp với người dùng.

## 9. @SubscribeMapping

@SubscribeMapping xử lý SUBSCRIBE frame cho một destination cụ thể.

~~~java
@Controller
public class InitialDataController {

    @SubscribeMapping("/dashboard")
    public DashboardSnapshot initialDashboard() {
        return dashboardService.snapshot();
    }
}
~~~

Nếu client SUBSCRIBE tới /app/dashboard, method có thể trả snapshot trực tiếp cho client qua clientOutboundChannel mà không gửi qua broker để lưu subscription hoặc broadcast.

Use case:

- Gửi initial state khi client mở màn hình.
- Trả dữ liệu khởi tạo một lần.
- Phản hồi một subscription request mà không cần tạo broadcast destination.

Nếu muốn kết quả đi qua broker, có thể kết hợp @SendTo hoặc @SendToUser. Không map cùng một prefix cho controller và broker nếu không có chủ đích vì cả hai có thể xử lý message song song.

## 10. @SendTo và @SendToUser

### @SendTo

@SendTo chỉ định destination mà kết quả method được gửi tới:

~~~java
@MessageMapping("/chat")
@SendTo("/topic/chat")
public ChatMessage chat(ChatMessage message) {
    return message;
}
~~~

Có thể gửi tới nhiều destination:

~~~java
@SendTo({"/topic/chat", "/topic/audit"})
~~~

Nếu không chỉ định @SendTo, Spring dùng destination mặc định theo quy tắc mapping của message handler.

### @SendToUser

@SendToUser gửi response tới user gắn với message hiện tại:

~~~java
@MessageMapping("/private-message")
@SendToUser("/queue/replies")
public PrivateReply reply(PrivateRequest request) {
    return new PrivateReply("Received");
}
~~~

Client subscribe:

~~~text
/user/queue/replies
~~~

Spring chuyển /user destination thành destination riêng cho session/user. Nếu user có nhiều session, mặc định các session phù hợp đều có thể nhận. Đặt broadcast=false khi chỉ muốn trả lời session gửi request.

### Gửi từ service bằng SimpMessagingTemplate

Không phải lúc nào cũng gửi message từ @MessageMapping. Service hoặc scheduled job có thể inject SimpMessagingTemplate:

~~~java
@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void broadcast(String text) {
        messagingTemplate.convertAndSend(
                "/topic/notifications",
                new Notification(text)
        );
    }

    public void notifyUser(String username, Notification notification) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                notification
        );
    }
}
~~~

Cách này hữu ích khi một HTTP request, scheduled task hoặc business service cần đẩy event tới WebSocket subscriber.

## 11. MessageConverter và định dạng payload

STOMP frame body là dữ liệu bytes/text. Spring dùng MessageConverter để chuyển body thành object cho controller và chuyển return object thành outbound payload.

Các dạng payload thường gặp:

- String: text đơn giản.
- JSON: DTO/record cho ứng dụng browser.
- Byte array: payload nhị phân hoặc dữ liệu đã encode.
- Custom format: converter riêng theo schema.

Với JSON, client gửi:

~~~json
{
  "content": "hello"
}
~~~

Controller nhận DTO:

~~~java
public record ChatMessage(String content) {
}
~~~

Spring chuyển JSON thành ChatMessage và serialize response object thành JSON khi gửi ra broker.

### Tùy chỉnh converter

WebSocketMessageBrokerConfigurer có callback configureMessageConverters để thêm converter. Khi tự cung cấp converter, cần hiểu giá trị boolean trả về điều khiển việc Spring có tiếp tục đăng ký converter mặc định hay không.

Ví dụ khung:

~~~java
@Override
public boolean configureMessageConverters(
        List<MessageConverter> messageConverters) {

    messageConverters.add(customMessageConverter);

    // true cho phép Spring đăng ký các converter mặc định còn lại.
    return true;
}
~~~

Chỉ thay converter khi có yêu cầu schema hoặc serialization rõ ràng. Nếu bỏ converter mặc định mà không thay thế, controller có thể không convert được payload String/JSON như mong muốn.

Client và server phải thống nhất content-type, JSON field, encoding, null handling và version schema.

## 12. Authentication và authorization

STOMP session bắt đầu bằng HTTP handshake hoặc các HTTP transport request nếu dùng SockJS. Trong ứng dụng web thông thường, Spring Security xác thực HTTP request và Spring tự liên kết Principal của request với WebSocket/SockJS session.

Khi đó, Principal có thể được truy cập trong @MessageMapping:

~~~java
@MessageMapping("/profile")
@SendToUser("/queue/profile")
public ProfileResponse profile(Principal principal) {
    return profileService.load(principal.getName());
}
~~~

### STOMP login/passcode không phải mặc định authentication cho WebSocket

STOMP protocol có header login và passcode trong CONNECT frame, nhưng với STOMP over WebSocket, Spring mặc định bỏ qua các header này và dựa trên user đã xác thực ở HTTP transport.

Vì vậy, nếu dùng cookie-based session:

1. User đăng nhập qua HTTP/Spring Security.
2. Browser gửi cookie trong WebSocket handshake cùng origin.
3. Spring lấy Principal từ HTTP request.
4. Principal được gắn với WebSocket/STOMP session.
5. Message từ session có user header tương ứng.

Nếu dùng JWT hoặc token authentication, có thể dùng ChannelInterceptor để đọc token từ STOMP CONNECT native header, xác thực token và gắn Authentication vào message accessor. Không log token hoặc lưu token dài hạn vào session metadata.

### Authorization theo destination và command

Authentication chỉ xác định ai đang kết nối. Authorization quyết định user được SEND hoặc SUBSCRIBE destination nào.

Ví dụ policy:

- User đã đăng nhập mới được CONNECT.
- Chỉ role ADMIN mới được SUBSCRIBE /topic/admin.
- Client chỉ được SEND tới /app/**.
- Client không được SEND trực tiếp tới /topic/** nếu server phải kiểm soát nội dung.
- User chỉ được nhận /user/queue/** của chính mình.

Spring Security cung cấp WebSocket message authorization qua ChannelInterceptor và authorization manager. Cấu hình security cho STOMP message cần kiểm tra cả message type và destination. Đặc biệt, SUBSCRIBE cũng là một hành động cần phân quyền; chỉ bảo vệ SEND là chưa đủ.

### ChannelInterceptor

Có thể đăng ký interceptor cho inbound channel:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new StompSecurityChannelInterceptor());
}
~~~

Trong preSend, dùng StompHeaderAccessor để đọc command, destination và native headers:

~~~java
public class StompSecurityChannelInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);

        StompCommand command = accessor.getCommand();
        String destination = accessor.getDestination();

        // Kiểm tra policy theo command, user và destination.
        return message;
    }
}
~~~

Interceptor có thể kiểm tra, bổ sung header hoặc từ chối message bằng cách trả null/throw exception theo policy. Với authentication token, cần bảo đảm interceptor chạy đúng thứ tự so với Spring Security interceptor.

## 13. Channel và executor

Spring sử dụng channel bất đồng bộ để tách các giai đoạn xử lý. clientInboundChannel và clientOutboundChannel thường được backing bởi thread pool.

Có thể cấu hình inbound channel:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.taskExecutor()
            .corePoolSize(4)
            .maxPoolSize(16)
            .queueCapacity(1000);
}
~~~

Các giá trị trên chỉ là ví dụ. Chọn thread pool theo loại workload:

- CPU-bound: số thread gần số processor.
- I/O-bound: có thể cần nhiều thread hơn nếu handler chờ database hoặc service ngoài.
- Blocking handler: kiểm soát queue capacity để không tích tụ message vô hạn.
- Message burst: theo dõi độ trễ queue và rejection.

Không tăng max pool size mà bỏ qua queue capacity. Với ThreadPoolExecutor, queue mặc định rất lớn có thể khiến executor không bao giờ scale vượt core pool size như mong đợi.

### Thứ tự message

Inbound/outbound channel chạy bất đồng bộ và dùng nhiều thread. Thứ tự xử lý có thể khác thứ tự frame được nhận hoặc message được publish.

Nếu ứng dụng cần giữ thứ tự inbound theo từng session:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.setPreserveReceiveOrder(true);
    registry.addEndpoint("/ws");
}
~~~

Nếu cần giữ thứ tự outbound theo từng session:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPreservePublishOrder(true);
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Hai setting này có chi phí hiệu năng. Chỉ bật khi logic nghiệp vụ phụ thuộc thứ tự.

## 14. Heartbeat và kết nối lâu dài

WebSocket/STOMP connection thường tồn tại lâu. Heartbeat giúp phát hiện connection chết, NAT/proxy timeout và client không còn hoạt động.

Simple broker hỗ trợ STOMP heartbeat khi được cấu hình TaskScheduler:

~~~java
registry.enableSimpleBroker("/topic", "/queue")
        .setHeartbeatValue(new long[] {10_000, 20_000})
        .setTaskScheduler(messageBrokerTaskScheduler);
~~~

Hai số biểu thị heartbeat interval theo milliseconds cho hai chiều gửi/nhận theo STOMP negotiation. Cần cấu hình TaskScheduler phù hợp để broker phát heartbeat và kiểm tra timeout.

Khi dùng external broker relay, heartbeat và connection policy còn phụ thuộc broker. Kiểm tra cả heartbeat giữa browser và Spring lẫn giữa Spring và broker.

Client STOMP.js có thể cấu hình:

~~~javascript
const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000,
    reconnectDelay: 5000
});
~~~

Heartbeat giúp phát hiện connection bất thường; reconnect logic vẫn cần được triển khai ở client. Sau reconnect, client phải subscribe lại các destination cần thiết và đồng bộ lại trạng thái nếu có message bị bỏ lỡ.

## 15. WebSocket transport và giới hạn message

STOMP message có thể lớn hơn một WebSocket frame. Spring có thể buffer và reassemble các phần message theo transport configuration.

Cấu hình:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration
            .setMessageSizeLimit(64 * 1024)
            .setSendTimeLimit(15_000)
            .setSendBufferSizeLimit(512 * 1024)
            .setTimeToFirstMessage(30_000);
}
~~~

Ý nghĩa:

| Setting | Ý nghĩa |
|---|---|
| setMessageSizeLimit | Giới hạn kích thước STOMP message sau khi nhận/reassemble. |
| setSendTimeLimit | Giới hạn thời gian gửi message tới client. |
| setSendBufferSizeLimit | Giới hạn dữ liệu outbound đang chờ gửi tới client. |
| setTimeToFirstMessage | Thời gian chờ message đầu tiên sau khi WebSocket session được thiết lập. |

Client chậm có thể làm outbound buffer tăng. Khi send timeout hoặc buffer limit bị vượt, Spring có thể đóng session theo transport policy.

Không đặt giới hạn quá lớn chỉ để tránh lỗi payload. Payload realtime nên nhỏ, có cấu trúc và tránh gửi dữ liệu nặng không cần thiết. Với file hoặc binary lớn, cân nhắc HTTP/object storage thay cho STOMP broadcast.

## 16. SockJS và fallback transport

SockJS cung cấp các transport fallback khi native WebSocket không hoạt động hoặc bị proxy chặn.

Server:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.com")
        .withSockJS();
~~~

Client phải dùng SockJS client làm WebSocket factory cho STOMP.js:

~~~javascript
const client = new Client({
    webSocketFactory: () => new SockJS("/ws"),
    reconnectDelay: 5000
});
~~~

SockJS có thể chọn WebSocket, streaming hoặc long polling. Các transport fallback tạo nhiều HTTP request dưới cùng endpoint path; security, cookie, CORS và proxy configuration phải phù hợp.

Nếu toàn bộ client hiện đại hỗ trợ WebSocket và proxy đã cấu hình đúng, native WebSocket đơn giản hơn. Bật SockJS khi có yêu cầu fallback thực tế.

## 17. User destinations

Spring hỗ trợ destination bắt đầu bằng /user để gửi message tới một user hoặc session cụ thể.

Client subscribe:

~~~text
/user/queue/notifications
~~~

Server gửi:

~~~java
messagingTemplate.convertAndSendToUser(
        username,
        "/queue/notifications",
        notification
);
~~~

Spring dùng UserDestinationMessageHandler chuyển logical destination thành destination nội bộ duy nhất cho user/session. Nhiều user có thể subscribe cùng tên logical destination mà không nhận nhầm message của nhau.

Dùng @SendToUser trong controller:

~~~java
@MessageMapping("/trade")
@SendToUser("/queue/trade-result")
public TradeResult trade(TradeRequest request, Principal principal) {
    return tradeService.execute(principal.getName(), request);
}
~~~

Nếu user có nhiều session, mặc định các session phù hợp đều có thể nhận. Dùng broadcast=false khi chỉ muốn gửi về session đã gửi message.

Với external broker, cần kiểm tra policy cleanup các queue/destination riêng được tạo cho user session. Trong nhiều instance, có thể cần cấu hình broadcast cho unresolved user destination để instance khác có cơ hội tìm session tương ứng.

## 18. Lifecycle event và cleanup

Spring phát application event khi STOMP session được tạo, kết nối, subscribe, unsubscribe hoặc disconnect.

Các event thường gặp:

| Event | Ý nghĩa |
|---|---|
| SessionConnectEvent | Client gửi STOMP CONNECT. |
| SessionConnectedEvent | STOMP CONNECT đã được xác nhận. |
| SessionSubscribeEvent | Client gửi SUBSCRIBE. |
| SessionUnsubscribeEvent | Client gửi UNSUBSCRIBE. |
| SessionDisconnectEvent | STOMP/WebSocket session kết thúc. |

Có thể lắng nghe:

~~~java
@Component
public class StompSessionEvents {

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        String sessionId = event.getSessionId();
        // Xóa trạng thái gắn với session.
    }
}
~~~

SessionDisconnectEvent có thể được phát nhiều lần trong một số tình huống, ví dụ client gửi DISCONNECT và transport đồng thời đóng. Cleanup phải idempotent: xóa subscription, presence hoặc session state nhiều lần vẫn an toàn.

Nếu cần kiểm tra từng message, dùng ChannelInterceptor. Event chỉ cung cấp lifecycle notification, không thay thế interceptor.

## 19. STOMP client với STOMP.js

Một browser client thường dùng package @stomp/stompjs.

Cài package:

~~~bash
npm install @stomp/stompjs
~~~

Ví dụ:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,
    onConnect: () => {
        client.subscribe("/topic/chat", frame => {
            console.log(frame.body);
        });

        client.publish({
            destination: "/app/chat",
            body: JSON.stringify({ content: "hello" })
        });
    },
    onStompError: frame => {
        console.error("STOMP error:", frame.headers["message"]);
        console.error(frame.body);
    },
    onWebSocketError: event => {
        console.error("WebSocket error:", event);
    }
});

client.activate();
~~~

Các bước:

1. Client mở WebSocket tới /ws.
2. STOMP.js gửi CONNECT frame.
3. Spring trả CONNECTED.
4. onConnect chạy sau khi STOMP session sẵn sàng.
5. Client subscribe /topic/chat.
6. Client publish JSON tới /app/chat.
7. Spring route tới @MessageMapping("/chat").
8. Controller trả response và @SendTo gửi tới /topic/chat.
9. Client nhận MESSAGE frame và đọc JSON body.

Trong ứng dụng thật, hãy chỉ publish sau khi subscription cần thiết đã được thiết lập. Nếu cần xác nhận subscription đã được broker xử lý, dùng STOMP RECEIPT với external broker hỗ trợ receipts; simple broker tích hợp không hỗ trợ receipts.

Khi component hoặc ứng dụng đóng, gọi client.deactivate() để đóng STOMP/WebSocket session và giải phóng timer/reconnect task.

## 20. Ví dụ Java 17+ chạy được: chat broadcast với Spring Boot 4.1.2

Ví dụ dùng simple broker tích hợp của Spring. Client kết nối tới /ws, subscribe /topic/chat và gửi message tới /app/chat. Controller trả message về topic; tất cả client đang subscribe nhận được broadcast.

### Cấu trúc project

~~~text
spring-stomp-chat-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          StompChatApplication.java
          WebSocketConfiguration.java
          ChatMessage.java
          ChatController.java
      resources/
        application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>spring-stomp-chat-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
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

### application.properties

~~~properties
server.port=8080
~~~

### StompChatApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompChatApplication {

    public static void main(String[] args) {
        SpringApplication.run(StompChatApplication.class, args);
    }
}
~~~

### WebSocketConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.setPreserveReceiveOrder(true);

        registry.addEndpoint("/ws")
                .setAllowedOrigins("http://localhost:8080");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
        registration
                .setMessageSizeLimit(64 * 1024)
                .setSendTimeLimit(15_000)
                .setSendBufferSizeLimit(512 * 1024);
    }
}
~~~

setPreserveReceiveOrder(true) giúp các message inbound từ cùng một session được xử lý theo thứ tự nhận. Trong ví dụ, điều này giữ thứ tự SUBSCRIBE rồi SEND khi client thực hiện hai thao tác liên tiếp.

### ChatMessage.java

~~~java
package demo;

public record ChatMessage(String content) {
}
~~~

### ChatController.java

~~~java
package demo;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;
import org.springframework.messaging.handler.annotation.SendTo;

@Controller
public class ChatController {

    @MessageMapping("/chat")
    @SendTo("/topic/chat")
    public ChatMessage chat(@Payload ChatMessage message) {
        System.out.println("handled=" + message.content());
        return new ChatMessage("server: " + message.content());
    }
}
~~~

### Chạy server

Yêu cầu Java 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Server lắng nghe tại:

~~~text
http://localhost:8080
~~~

### Client STOMP.js

Tạo một frontend JavaScript có cài @stomp/stompjs:

~~~bash
npm install @stomp/stompjs
~~~

Trong client module:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,
    onConnect: () => {
        client.subscribe("/topic/chat", frame => {
            console.log(frame.body);
        });

        client.publish({
            destination: "/app/chat",
            body: JSON.stringify({ content: "hello" })
        });
    }
});

client.activate();
~~~

Kết quả trên server console:

~~~text
handled=hello
~~~

Kết quả trên browser console:

~~~text
{"content":"server: hello"}
~~~

### Giải thích luồng chạy

1. Spring Boot khởi tạo ứng dụng MVC và WebSocket support.
2. @EnableWebSocketMessageBroker bật STOMP infrastructure.
3. registerStompEndpoints đăng ký URL /ws.
4. configureMessageBroker đặt /app cho controller và /topic, /queue cho simple broker.
5. Browser mở WebSocket tới /ws và gửi STOMP CONNECT.
6. Client SUBSCRIBE /topic/chat.
7. Client SEND JSON tới /app/chat.
8. Spring route phần /chat tới ChatController.chat.
9. MessageConverter chuyển JSON body thành ChatMessage.
10. Controller in handled=hello và trả ChatMessage mới.
11. @SendTo gửi response tới /topic/chat.
12. Simple broker tìm subscriber và gửi STOMP MESSAGE frame về browser.
13. Browser in JSON body trong console.

Ví dụ dùng simple broker nên chỉ broadcast tới các client đang kết nối và subscribe. Khi ứng dụng cần durable subscription, ACK/RECEIPT, clustering hoặc message broker persistence, hãy chuyển sang external broker relay.

## 21. Kiểm thử STOMP endpoint

Có thể kiểm thử bằng WebSocketStompClient và StompSessionHandler trong Java test.

Các tình huống cần kiểm tra:

- WebSocket handshake tới đúng endpoint.
- STOMP CONNECT được xác nhận.
- SUBSCRIBE được đăng ký đúng destination.
- SEND tới /app được route đúng controller.
- Controller trả message đúng schema và destination.
- Client khác subscribe cùng topic cũng nhận broadcast.
- Message gửi tới /user chỉ tới đúng user/session.
- Invalid payload tạo lỗi có cấu trúc.
- User không có quyền không thể SEND hoặc SUBSCRIBE destination bị cấm.
- Client disconnect giải phóng state.
- Reconnect thực hiện subscribe lại.
- Heartbeat phát hiện connection chết.
- Payload quá lớn bị từ chối theo transport limit.
- Broker relay reconnect sau broker restart nếu dùng external broker.

Với simple broker, không kiểm thử ACK/RECEIPT như thể broker có hỗ trợ đầy đủ. Hãy dùng broker thật khi kiểm thử tính năng phụ thuộc STOMP broker command.

## 22. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| HTTP 404 khi connect | Endpoint chưa đăng ký hoặc client sai URL | Kiểm tra registerStompEndpoints và context path |
| WebSocket mở nhưng STOMP CONNECT thất bại | Client/server không thống nhất STOMP sub-protocol hoặc frame | Dùng STOMP client tương thích và kiểm tra log |
| SEND /app không tới controller | Application prefix hoặc @MessageMapping sai | Đối chiếu destination /app + mapping |
| SUBSCRIBE không nhận message | Subscribe nhầm endpoint URL hoặc destination prefix | Subscribe /topic hoặc /queue đúng cấu hình |
| Controller chạy nhưng client không nhận | @SendTo sai destination hoặc client chưa subscribe | Kiểm tra broker prefix và subscriber |
| Client nhận JSON không parse được | Converter/content-type/schema không khớp | Kiểm tra MessageConverter và payload |
| Simple broker không gửi RECEIPT | Simple broker không hỗ trợ receipts | Dùng external broker relay nếu cần receipt |
| Simple broker mất subscription khi restart | Subscription lưu trong memory | Dùng broker chuyên dụng nếu cần durability |
| Nhiều instance không broadcast chéo | Simple broker chỉ quản lý subscription trong từng instance | Dùng external broker relay |
| Client có thể subscribe destination nhạy cảm | Chưa authorization SUBSCRIBE | Cấu hình Spring Security message authorization |
| Token trong STOMP CONNECT không có tác dụng | Spring mặc định bỏ qua login/passcode cho WebSocket transport | Xác thực HTTP hoặc viết CONNECT ChannelInterceptor |
| Client disconnect nhưng presence còn | Cleanup không idempotent hoặc bỏ sót event | Lắng nghe SessionDisconnectEvent và cleanup an toàn |
| Message đến sai thứ tự | Inbound/outbound channel xử lý bất đồng bộ | Cân nhắc setPreserveReceiveOrder và setPreservePublishOrder |
| Client chậm làm buffer tăng | Outbound client không tiêu thụ message kịp | Giới hạn send time, buffer size và payload |
| Heartbeat không hoạt động | Thiếu TaskScheduler hoặc cấu hình interval sai | Cấu hình scheduler và kiểm tra cả hai chiều |
| SockJS client lỗi | Server/client không cùng bật SockJS | Đồng bộ withSockJS và SockJS client |
| Broker relay không kết nối | Broker chưa bật STOMP TCP listener hoặc sai credentials/port | Kiểm tra broker STOMP endpoint và network |

## 23. Checklist triển khai

- [ ] Bật @EnableWebSocketMessageBroker trên class cấu hình.
- [ ] Implement WebSocketMessageBrokerConfigurer.
- [ ] Đăng ký endpoint URL bằng StompEndpointRegistry.
- [ ] Cấu hình allowed origins cụ thể.
- [ ] Chọn SockJS chỉ khi client cần fallback.
- [ ] Đặt application destination prefix như /app.
- [ ] Đặt broker prefix như /topic và /queue.
- [ ] Chọn simple broker hoặc external broker relay theo yêu cầu durability, ACK, receipts và clustering.
- [ ] Viết @MessageMapping controller với DTO rõ ràng.
- [ ] Dùng @SendTo, @SendToUser hoặc SimpMessagingTemplate cho outbound message.
- [ ] Kiểm tra JSON MessageConverter và schema payload.
- [ ] Xác thực HTTP handshake hoặc token CONNECT theo policy.
- [ ] Phân quyền cả SEND và SUBSCRIBE.
- [ ] Dùng ChannelInterceptor cho kiểm tra từng STOMP frame.
- [ ] Cấu hình heartbeat và reconnect ở client.
- [ ] Cấu hình message size, send time và send buffer limit.
- [ ] Chỉ bật preserve order nếu nghiệp vụ cần.
- [ ] Cleanup session/presence khi disconnect và xử lý duplicate event.
- [ ] Kiểm thử nhiều client, client chậm, reconnect, broker restart và payload lỗi.
- [ ] Theo dõi số session, subscription, inbound/outbound queue, send buffer, error và heartbeat timeout.

## Ghi nhớ

- @EnableWebSocketMessageBroker bật hạ tầng STOMP over WebSocket.
- WebSocketMessageBrokerConfigurer là điểm mở rộng để đăng ký endpoint và cấu hình broker/channel/transport.
- StompEndpointRegistry đăng ký URL handshake; STOMP destination nằm trong header của frame sau khi kết nối mở.
- /app thường route tới @MessageMapping; /topic và /queue route tới broker.
- Simple broker lưu subscription trong memory, phù hợp demo và broadcast cơ bản; nó không hỗ trợ đầy đủ ACK/RECEIPT và không phù hợp clustering.
- Broker relay chuyển STOMP message qua TCP tới external broker.
- @MessageMapping xử lý SEND; @SubscribeMapping xử lý subscription request; @SendTo và @SendToUser định tuyến kết quả.
- SimpMessagingTemplate cho phép service gửi message tới topic hoặc user destination.
- Authentication thường đến từ HTTP Principal; Spring mặc định bỏ qua login/passcode trong STOMP CONNECT trên WebSocket.
- ChannelInterceptor kiểm tra hoặc bổ sung từng STOMP message.
- Heartbeat, reconnect, message limit, send buffer và authorization là phần quan trọng khi vận hành.
- Simple broker và external broker có khả năng khác nhau; kiểm thử phải dùng đúng loại broker production.

## Tài liệu chính thức

- [Spring Framework 7.0.10 Reference: STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp.html)
- [Spring Framework 7.0.10 Reference: Enable STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/enable.html)
- [Spring Framework 7.0.10 Reference: Flow of Messages](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/message-flow.html)
- [Spring Framework 7.0.10 Reference: Annotated Controllers](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-annotations.html)
- [Spring Framework 7.0.10 Reference: Simple Broker](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework 7.0.10 Reference: External Broker Relay](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework 7.0.10 Reference: WebSocket Transport](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/server-config.html)
- [Spring Framework 7.0.10 Reference: Authentication](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/authentication.html)
- [Spring Framework 7.0.10 Reference: Authorization](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/authorization.html)
- [Spring Framework 7.0.10 Reference: User Destinations](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/user-destination.html)
- [Spring Framework 7.0.10 Reference: Interception](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/interceptors.html)
- [Spring Framework 7.0.10 Reference: Performance and Ordering](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/configuration-performance.html)
- [Spring Boot 4.1.2 Reference: WebSockets](https://docs.spring.io/spring-boot/4.1/reference/messaging/websockets.html)
- [Spring Getting Started Guide: STOMP over WebSocket](https://spring.io/guides/gs/messaging-stomp-websocket)
- [STOMP Protocol 1.2 Specification](https://stomp.github.io/stomp-specification-1.2.html)
