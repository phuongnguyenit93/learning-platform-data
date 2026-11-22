# STOMP, destination và luồng thông điệp qua các channel của Spring

## 1. Mục tiêu và bức tranh tổng quan

**WebSocket** cung cấp kết nối song công lâu dài giữa client và server, nhưng chỉ định nghĩa cách vận chuyển dữ liệu; nó không tự quy định message phải gửi đến ai, client đăng ký nhận như thế nào, hay nội dung mang cấu trúc gì. **STOMP (Simple Text Oriented Messaging Protocol)** bổ sung một giao thức nhắn tin dựa trên *frame*, gồm command, headers và body. Spring Framework hỗ trợ **STOMP over WebSocket** bằng cách ánh xạ các frame thành **Spring Message**, định tuyến qua các **MessageChannel**, gọi phương thức **@MessageMapping**, rồi gửi kết quả tới broker và các client đăng ký.

Trong bài này cần phân biệt **ba loại địa chỉ** thường bị gọi chung là endpoint:

1. **WebSocket handshake endpoint**, ví dụ **/ws**: URL mà browser dùng để mở kết nối WebSocket.
2. **Application destination**, ví dụ **/app/chat.send**: STOMP destination được Spring chuyển tới **@MessageMapping("/chat.send")**.
3. **Broker destination**, ví dụ **/topic/chat**: tên nơi client **SUBSCRIBE** để broker phân phối tin tới subscriber.

Ba tên trên đều do ứng dụng cấu hình. Chúng phục vụ ba giai đoạn khác nhau; **/ws không phải nơi client SEND tin nhắn STOMP**, và **/topic/chat không tự gọi controller** khi tiền tố đã tách đúng.

### Những câu hỏi cần tự trả lời sau bài

- Vì sao hai frame **SEND** và **SUBSCRIBE** có thể đi qua cùng WebSocket nhưng được xử lý bởi các thành phần khác nhau?
- Ý nghĩa của **/app**, **/topic**, **/queue**, **/user** là gì, và phần nào do Spring quy định qua cấu hình?
- Một tin từ browser đến **@MessageMapping** đi qua channel nào, và phản hồi đến subscriber đi qua channel nào?
- **clientInboundChannel**, **brokerChannel**, **clientOutboundChannel** có nhiệm vụ gì? Tại sao tên channel không nên nhầm với STOMP destination?
- Khác biệt của **simple broker** và **STOMP broker relay**, cách theo dõi luồng, thứ tự và lỗi.

## 2. STOMP frame: message ở cấp giao thức

Một STOMP frame có dạng:

~~~text
COMMAND
header-1:value
header-2:value

BODY<NUL>
~~~

**<NUL>** trong sơ đồ chỉ ký tự kết thúc frame có mã byte **0x00**, không phải chuỗi chữ NUL. Cấu trúc thực gồm dòng command, các dòng header, một dòng trống, body (nếu có) và ký tự NUL kết thúc. Body có thể là text hoặc binary; với JSON nên có content-type thích hợp.

### Ví dụ tiến trình kết nối và gửi tin

Client kết nối WebSocket tới **ws://localhost:8080/ws**, sau đó gửi STOMP **CONNECT**:

~~~text
CONNECT
accept-version:1.2
heart-beat:10000,10000

<NUL>
~~~

Server trả **CONNECTED** nếu phiên STOMP được chấp nhận:

~~~text
CONNECTED
version:1.2
heart-beat:0,0

<NUL>
~~~

Client muốn nhận dữ liệu chat gửi **SUBSCRIBE**:

~~~text
SUBSCRIBE
id:sub-chat-1
destination:/topic/chat

<NUL>
~~~

Cùng client, hoặc một client khác, muốn phát tin cho server xử lý gửi **SEND**:

~~~text
SEND
destination:/app/chat.send
content-type:application/json

{"from":"An","text":"Chào mọi người"}<NUL>
~~~

Nếu controller trả kết quả tới **/topic/chat** thì broker gửi STOMP **MESSAGE** đến từng subscription phù hợp:

~~~text
MESSAGE
subscription:sub-chat-1
destination:/topic/chat
message-id:msg-1
content-type:application/json

{"from":"An","text":"Chào mọi người"}<NUL>
~~~

Các frame minh họa có thể khác headers, message-id, heartbeat thực tế tùy broker/thư viện; ví dụ **msg-1** chỉ để dễ đọc, không phải giá trị Spring luôn tạo. STOMP còn có **UNSUBSCRIBE**, **DISCONNECT**, **ACK**, **NACK**, **RECEIPT**, **ERROR**; không phải broker nào cũng hỗ trợ trọn bộ tính năng.

| Command | Hướng điển hình | Ý nghĩa |
| --- | --- | --- |
| CONNECT | Client → server | Bắt đầu phiên STOMP trên kết nối đã mở |
| CONNECTED | Server → client | Thông báo phiên STOMP đã thiết lập |
| SUBSCRIBE | Client → server | Đăng ký một destination; cần header id |
| SEND | Client → server | Gửi payload đến destination |
| MESSAGE | Server/broker → client | Chuyển thông điệp đến subscription |
| UNSUBSCRIBE | Client → server | Bỏ đăng ký theo subscription id |
| DISCONNECT | Client → server | Kết thúc phiên theo giao thức |
| ACK/NACK | Client → broker | Xác nhận/từ chối giao nhận nếu broker/mode hỗ trợ |
| ERROR | Server/broker → client | Báo lỗi cấp giao thức |
| RECEIPT | Server/broker → client | Phản hồi yêu cầu receipt khi được hỗ trợ |

**Quan trọng:** WebSocket message, STOMP frame và Spring **Message<?>** không đồng nhất. Ở server, tầng WebSocket/STOMP giải mã frame, chuẩn hóa headers/payload thành Spring Message và đưa lên hệ thống channel nội bộ. Message converter có thể chuyển byte JSON thành một Java DTO khi handler chạy.

## 3. Cấu hình STOMP trong Spring

Một cấu hình tối thiểu Spring Boot/Spring Framework dùng **@EnableWebSocketMessageBroker**:

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

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
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

Giải thích từng cấu hình:

- **registry.addEndpoint("/ws")** mở đường dẫn HTTP handshake nâng cấp lên WebSocket; browser kết nối qua **ws://host/ws** hoặc **wss://host/ws** khi dùng TLS. Chưa nói gì về **destination** của frame STOMP.
- **setApplicationDestinationPrefixes("/app")** xác định nhóm destination chuyển tới **SimpAnnotationMethodMessageHandler**, tức các phương thức **@MessageMapping** hoặc **@SubscribeMapping**. Spring thường loại bỏ tiền tố **/app** trước khi so khớp mapping.
- **enableSimpleBroker("/topic", "/queue")** bật broker bộ nhớ của Spring để quản lý subscription và gửi message ở các destination có tiền tố này. Broker không tự hiểu nghiệp vụ: nó không gọi **@MessageMapping** cho **/topic/chat**.
- **setUserDestinationPrefix("/user")** cấu hình tiền tố cho **UserDestinationMessageHandler**, hỗ trợ ánh xạ subscription theo từng phiên/người dùng. Đây không phải broker destination vật lý.
- **@EnableWebSocketMessageBroker** đăng ký các handler, message channels, converters và thành phần broker cần thiết.

Các tên **/app**, **/topic**, **/queue**, **/user** là **quy ước thông dụng do cấu hình quyết định**, không phải toàn bộ STOMP protocol bắt buộc phải dùng đúng tên này. Có thể chọn tiền tố khác, nhưng client và server phải thống nhất. Nên chọn các tiền tố không chồng lấn để một frame không bị nhiều handler xử lý ngoài ý muốn.

### Phân biệt endpoint HTTP và destination STOMP

| Địa chỉ | Nằm ở đâu | Ai xử lý | Client thực hiện |
| --- | --- | --- | --- |
| **/ws** | URL handshake HTTP/WebSocket | WebSocket handshake handler | new WebSocket("ws://.../ws") hoặc STOMP client |
| **/app/chat.send** | Header destination của SEND frame | Spring annotated controller | STOMP publish/SEND |
| **/topic/chat** | Header destination của SUBSCRIBE và MESSAGE | Broker | STOMP subscribe |
| **/queue/notifications** | Broker destination theo quy ước | Broker | Thường subscribe cho luồng thông báo |
| **/user/queue/notifications** | Logical user destination | UserDestinationMessageHandler → broker destination phiên | Subscribe riêng cho phiên/người dùng |

**/queue** theo tên gọi thường gợi ý point-to-point trong broker bên ngoài, nhưng **simple broker của Spring không tự cung cấp hàng đợi bền vững hay semantics competing consumers**; nó quản lý subscription trong bộ nhớ và phát cho các subscription khớp. Không dựa vào tên "/queue" để suy ra message delivery có persistence, ACK hay chỉ một consumer.

## 4. Ba message channel chính của Spring

Spring Messaging cung cấp các abstraction:

- **Message<T>**: payload kiểu T kèm headers, ví dụ destination, content-type, sessionId, simpMessageType.
- **MessageHandler**: thành phần xử lý message.
- **MessageChannel**: điểm gửi message, tách producer khỏi consumer.
- **SubscribableChannel**: message channel cho các handler đăng ký nhận.
- **ExecutorSubscribableChannel**: dạng channel chuyển việc tới executor/thread pool.

Cấu hình STOMP của Spring dùng ba tên channel quan trọng:

| Channel | Tín hiệu đi qua | Nhiệm vụ |
| --- | --- | --- |
| **clientInboundChannel** | Từ client WebSocket vào server | Nhận Spring Message đã giải mã STOMP frame và đưa đến controller, broker hoặc các handler phù hợp |
| **brokerChannel** | Từ mã ứng dụng trong server đến broker | Truyền message do controller, SimpMessagingTemplate hoặc thành phần server tạo để broker phân phối |
| **clientOutboundChannel** | Từ broker/handler server ra client | Đưa message đến WebSocket session rồi mã hóa thành STOMP MESSAGE/frame để gửi đi |

Hình luồng với simple broker:

~~~text
                 WebSocket clients
                 (STOMP frames)
                        │
            CONNECT / SUBSCRIBE / SEND
                        │
                        ▼
              WebSocket transport
              + STOMP frame decoder
                        │
                        ▼
               clientInboundChannel
                    /         \
                   /           \
       /app/chat.send        /topic/chat
             │               SUBSCRIBE
             ▼                  │
  SimpAnnotationMethod        Simple
     MessageHandler           Broker
             │                  ▲
     @MessageMapping            │
       @Controller              │
             │                  │
       @SendTo result ──► brokerChannel
                                │
                                ▼
                          Simple Broker
                                │
                                ▼
                       clientOutboundChannel
                                │
                       STOMP frame encoder
                                │
                                ▼
                     WebSocket subscribers
~~~

**Chỉnh cách đọc sơ đồ:** broker nhận subscription trực tiếp từ **clientInboundChannel**; message **@SendTo** từ controller đi qua **brokerChannel**. Ở bên ra, broker gửi các message đến **clientOutboundChannel**. Đây là mô hình luồng logic: việc chạy thread và dispatch thực tế phụ thuộc executor/handler của Spring. Không phải mọi message inbound đều luôn đi qua brokerChannel.

### Dòng thời gian cụ thể: một câu chat

Giả sử hai browser A và B đã kết nối tới **/ws**:

1. **A SUBSCRIBE /topic/chat** với subscription id **a1**. WebSocket transport giải mã và gửi Spring Message vào **clientInboundChannel**; simple broker nhận và lưu subscription của A.
2. **B SUBSCRIBE /topic/chat** với id **b1**. Broker lưu thêm subscription của B.
3. **A SEND /app/chat.send** với JSON **{"from":"An","text":"Xin chào"}**. Frame được giải mã, chuyển vào **clientInboundChannel**.
4. **SimpAnnotationMethodMessageHandler** nhận vì tiền tố **/app** thuộc ứng dụng; nó loại tiền tố để tìm method **@MessageMapping("/chat.send")** trong controller.
5. Spring **MessageConverter** biến JSON payload thành DTO Java. Controller kiểm tra/biến đổi theo nghiệp vụ và trả một object.
6. **@SendTo("/topic/chat")** biến kết quả thành message outbound với destination **/topic/chat**, chuyển message đó qua **brokerChannel** tới simple broker.
7. Broker đối chiếu destination với các subscription và gửi bản sao cho cả A, B qua **clientOutboundChannel**.
8. WebSocket transport chuyển từng Spring Message thành STOMP **MESSAGE** frame phù hợp với subscription id/session và đẩy qua WebSocket.

**Chú ý:** A cũng nhận tin của chính mình nếu A đã subscribe /topic/chat. Nếu không có subscription nào, broker không tự lưu tin để gửi lại sau này. Nếu client SEND đến destination **/topic/chat** thay vì **/app/chat.send**, simple broker có thể xử lý trực tiếp; controller **@MessageMapping("/chat.send")** sẽ không được gọi. Đây là nguyên nhân phổ biến khiến người dùng thấy tin được broadcast nhưng validation/nghiệp vụ bị bỏ qua.

## 5. @MessageMapping, @SendTo và SimpMessagingTemplate

Controller nhận message **/app/chat.send**:

~~~java
package demo;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    public record ChatInput(String from, String text) {}
    public record ChatEvent(String from, String text) {}

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatEvent send(ChatInput input) {
        return new ChatEvent(input.from(), input.text());
    }
}
~~~

Tính chất:
- **@Controller** dùng với Spring Messaging annotation handler; không phải **@RestController** HTTP mapping.
- **@MessageMapping("/chat.send")** map destination sau khi bỏ prefix **/app**. Nó không cần **@PostMapping**.
- **ChatInput** được chuyển từ JSON bằng message converter thích hợp (Jackson khi được cấu hình).
- **@SendTo("/topic/chat")** chỉ rõ nơi publish **giá trị trả về**. Không có **@SendTo**, Spring có quy tắc destination phản hồi mặc định (theo cấu hình broker prefix); tuy nhiên khai báo tường minh giúp người đọc chắc chắn client phải subscribe ở đâu.
- Khi method trả **void**, không có outbound return value tự động. Muốn gửi message hãy inject **SimpMessagingTemplate** hoặc thực hiện side effect khác.
- **@DestinationVariable** ánh xạ biến trên đường destination như **@MessageMapping("/rooms/{roomId}")**; tương tự **@Header**, **@Payload**, **Principal** có thể dùng trong method parameters.

### Server chủ động publish mà không chờ STOMP SEND

Ứng dụng có thể phát thông điệp từ HTTP endpoint, scheduled job hoặc message queue consumer bằng **SimpMessagingTemplate**:

~~~java
@RestController
public class AnnouncementController {

    public record Announcement(String text) {}

    private final SimpMessagingTemplate messaging;

    public AnnouncementController(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    @PostMapping("/api/announcements")
    public ResponseEntity<Void> publish(@RequestParam("text") String text) {
        messaging.convertAndSend(
            "/topic/announcements", new Announcement(text));
        return ResponseEntity.accepted().build();
    }
}
~~~

Các import cần là **org.springframework.messaging.simp.SimpMessagingTemplate**, **org.springframework.web.bind.annotation.RestController**, **PostMapping**, **RequestParam**, và **org.springframework.http.ResponseEntity**. Đây là fragment ứng dụng HTTP + WebSocket; phần mã runnable đầy đủ sẽ được trình bày ở mục 10.

**convertAndSend** chuyển object sang Spring Message và đưa qua **brokerChannel**; broker gửi tới subscriber của **/topic/announcements**. Không cần client nào SEND vào **/app** trước. Return HTTP **202 Accepted** ở ví dụ xác nhận endpoint đã xử lý yêu cầu publish ở tầng ứng dụng; nó không bảo đảm mọi browser subscriber đã nhận và xử lý thành công thông báo.

### @SubscribeMapping: đường rẽ khác với @MessageMapping

**@SubscribeMapping("/snapshot")** xử lý một **SUBSCRIBE /app/snapshot** ở annotated controller. Giá trị trả về mặc định đi **trực tiếp qua clientOutboundChannel** đến client vừa subscribe, **không đi brokerChannel** để broadcast hay đăng ký một subscription kéo dài. Điều này hữu ích để gửi snapshot ban đầu khi trang vừa mở:

~~~java
@SubscribeMapping("/snapshot")
public Snapshot initialState() {
    return service.currentSnapshot();
}
~~~

Nếu áp dụng **@SendTo** hoặc **@SendToUser**, hành vi trả kết quả có thể đi qua broker thay vì đường trả trực tiếp mặc định. Đừng dùng SUBSCRIBE **/app/snapshot** như cơ chế thay thế cho đăng ký dài hạn **/topic/updates** nếu cần stream thay đổi liên tục.

## 6. User destination: /user khác /queue thế nào?

Đôi khi server cần gửi thông báo riêng cho một tài khoản hoặc đúng một WebSocket session. Spring hỗ trợ **UserDestinationMessageHandler**, ánh xạ destination logic có tiền tố **/user** thành destination cụ thể cho từng session.

Client subscribe:

~~~text
SUBSCRIBE
id:me-1
destination:/user/queue/notifications

<NUL>
~~~

Ứng dụng gửi tới người dùng đã xác thực:

~~~java
messaging.convertAndSendToUser(
    username,
    "/queue/notifications",
    new Notification("Đã xử lý xong"));
~~~

Với **@MessageMapping**, có thể trả kết quả bằng **@SendToUser("/queue/notifications")**. Server sẽ ánh xạ destination tới một hoặc nhiều phiên của user theo các quy tắc riêng, ví dụ destination vật lý mang session suffix.

**Phân biệt rõ**:
- Client thường **SUBSCRIBE /user/queue/notifications** mà **không điền username** trong subscription destination.
- Mã server dùng **convertAndSendToUser(username, "/queue/notifications", payload)** hoặc **@SendToUser**.
- **/user** là tiền tố logic để Spring giải quyết người nhận, không phải bảo đảm phân quyền.
- Theo mặc định, khi một người dùng có nhiều phiên, thông điệp tới user có thể được phát tới nhiều phiên; **@SendToUser(broadcast=false)** có thể giới hạn trả lời cho phiên phát message khi phù hợp.
- Với một WebSocket session chưa gắn tài khoản, **@SendToUser** vẫn có thể gửi tới session đó khi broadcast=false; hành vi này không thay thế yêu cầu authentication thực sự.
- Khi triển khai nhiều instance và external broker, các user session phân tán cần được cấu hình/định tuyến phù hợp; không mặc định user đích ở instance khác luôn resolve được.

Chỉ định **/queue** trong user destination giúp biểu đạt ý định nhận thông báo cá nhân; không có nghĩa simple broker ghi thông báo bền vững vào ổ đĩa.

## 7. Simple broker và broker relay: đường đi giống và khác

### Simple broker tích hợp

Cấu hình:

~~~java
registry.setApplicationDestinationPrefixes("/app");
registry.enableSimpleBroker("/topic", "/queue");
~~~

Simple broker giữ thông tin subscription trong **bộ nhớ của ứng dụng Spring** và broadcast tin tới session đang kết nối. Nó phù hợp với demo, ứng dụng ít node hoặc hệ thống không đòi hỏi broker mạnh. Nó **không phải message broker đầy đủ**: không cung cấp toàn bộ chức năng STOMP như ACK, receipts, persistence, clustering hay phân phối durable theo kiểu enterprise broker.

Luồng nhận SEND /app → controller → brokerChannel → simple broker → clientOutboundChannel như đã phân tích. Với một SUBSCRIBE /topic, broker giữ subscription từ clientInboundChannel. Với nhiều instance Spring đứng sau load balancer, subscription đơn giản trên node A không được node B biết một cách tự động.

### STOMP broker relay

Khi cần broker thực thụ (ví dụ RabbitMQ/ActiveMQ có bật STOMP), Spring có thể dùng **relay**:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("127.0.0.1")
        .setRelayPort(61613)
        .setClientLogin("guest")
        .setClientPasscode("guest")
        .setSystemLogin("guest")
        .setSystemPasscode("guest");
}
~~~

Thông số host, port, account ở đoạn này **chỉ minh họa**, phải lấy từ hệ thống broker được triển khai và bảo vệ secrets trong cấu hình môi trường. **Spring không tự khởi động RabbitMQ/ActiveMQ** khi bật relay.

Luồng khác đi như sau:

~~~text
Client SEND /app/action
       |
       v
clientInboundChannel
       |
 @MessageMapping
       |
 brokerChannel
       |
  STOMP broker relay ──TCP──> External broker
                                 |
                          subscribers matched
                                 |
                         TCP reply to relay
                                 |
                       clientOutboundChannel
                                 |
                            WebSocket clients
~~~

Đối với SUBSCRIBE /topic, relay chuyển subscription đến broker bên ngoài qua TCP. Với SEND vào destination do broker quản lý, relay cũng chuyển lên broker. **@MessageMapping** vẫn chạy trong Spring đối với application destinations như /app.

Relay duy trì TCP connections đến broker, có connection hệ thống và các connection đại diện cho WebSocket clients theo cơ chế relay. Khi broker mất kết nối, cần quản lý reconnect/availability và theo dõi **BrokerAvailabilityEvent**; không coi relay như một queue vô hạn trong bộ nhớ. External broker có thể hỗ trợ ACK, receipts, heartbeat, durable subscriptions và routing nâng cao, nhưng **chỉ khi broker và cách cấu hình thực sự hỗ trợ**.

## 8. Ordering, executor và các vấn đề vận hành

Thông thường **clientInboundChannel** và **clientOutboundChannel** sử dụng executor. Điều này tăng throughput nhưng có hệ quả: message từ một phiên có thể được xử lý/gửi trong thread khác nhau; thứ tự thực tế có thể không trùng thứ tự frame được nhận hoặc thứ tự message được publish.

Nếu thứ tự là yêu cầu nghiệp vụ (ví dụ các bản cập nhật tuần tự trong một phiên), Spring cung cấp lựa chọn:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
    registry.setPreserveReceiveOrder(true);
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

- **setPreserveReceiveOrder(true)** giúp Spring xử lý các message inbound trong cùng WebSocket session theo thứ tự nhận trên **clientInboundChannel**.
- **setPreservePublishOrder(true)** giúp các message outbound trong cùng session được publish tới **clientOutboundChannel** theo thứ tự.
- Hai tùy chọn có chi phí hiệu năng và **không hứa bảo đảm thứ tự toàn cục giữa mọi session, instance hay external broker**. Cần sequence number ở payload nếu ứng dụng cần so sánh/thứ tự nghiệp vụ cross-node.

### Interceptor và observability

Để quan sát/kiểm tra frame STOMP inbound, dùng **ChannelInterceptor** gắn qua **configureClientInboundChannel**:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message, MessageChannel channel) {
            StompHeaderAccessor stomp =
                MessageHeaderAccessor.getAccessor(
                    message, StompHeaderAccessor.class);
            if (stomp != null) {
                System.out.println("STOMP " + stomp.getCommand()
                    + " -> " + stomp.getDestination());
            }
            return message;
        }
    });
}
~~~

Để fragment trên biên dịch, cần import **ChannelRegistration**, **ChannelInterceptor**, **Message**, **MessageChannel**, **MessageHeaderAccessor**, **StompHeaderAccessor**. Đây là ví dụ chẩn đoán **có thể in frame metadata**, không phải cơ chế bảo mật hoàn chỉnh. Chỉ log command/destination cần thiết, không in payload/authorization token. Với kiểm thử production, dùng structured logging/metrics và theo dõi thread pool, size, queue, queue saturation, hủy kết nối và thời gian xử lý.

### Authentication và authorization

Kết nối WebSocket bắt đầu bằng HTTP handshake; principal có thể được kế thừa từ phiên HTTP/authentication ở handshake. STOMP CONNECT, SUBSCRIBE, SEND là các thao tác messaging cần được **phân quyền** riêng. Ví dụ người dùng có quyền đọc **/topic/public** chưa chắc có quyền SEND thẳng vào broker hoặc subscribe **/user/** của người khác.

Trong Spring Security nên có quy tắc ủy quyền message **theo STOMP type và destination**, áp dụng bảo vệ CSRF/origin phù hợp với ứng dụng browser, xác định danh tính trước khi gửi user destination. Không chỉ dựa vào tiền tố **/app** hoặc một trường username trong JSON do client nhập. Một pattern an toàn là giới hạn client SEND đến **/app/** để controller kiểm tra nghiệp vụ; không cho client tự do gửi trực tiếp vào những destination chỉ server được publish.

### Lifecycle và độ tin cậy

- **STOMP heartbeat** phát hiện kết nối im lặng nhưng không thay thế cơ chế phục hồi trạng thái sau reconnect.
- **Connection lost** có thể làm mất subscription của phiên cũ; STOMP client thường phải kết nối và subscribe lại.
- **WebSocket reconnect** không tự replay toàn bộ tin đã phát khi client offline với simple broker.
- Với dữ liệu nghiệp vụ cần không mất, lưu sự kiện/trạng thái vào DB hoặc broker durable, dùng định danh message, acknowledgement và đồng bộ sau reconnect. STOMP over WebSocket tự thân không bảo đảm exactly-once delivery.
- **@MessageExceptionHandler** hỗ trợ ánh xạ lỗi trong controller thành thông điệp; lựa chọn destination lỗi cần rõ ràng. Đừng trả stack trace/bí mật cho client.
- Khi kênh outbound chậm, kiểm soát giới hạn buffer/send timeout, payload size, số subscription và tốc độ phát. Một subscriber chậm có thể gây áp lực tài nguyên.

## 9. Một luồng khác: thông báo từ REST endpoint tới WebSocket

Dòng chat ở mục 4 là **client SEND** → **@MessageMapping**. Nhưng sự kiện trong hệ thống cũng có thể bắt đầu từ HTTP request hoặc scheduled task:

~~~text
HTTP POST /api/announcements
        |
        v
@RestController / service
        |
SimpMessagingTemplate.convertAndSend(
    "/topic/announcements", object)
        |
        v
    brokerChannel
        |
     broker
        |
  clientOutboundChannel
        |
STOMP MESSAGE tới mọi client đã SUBSCRIBE /topic/announcements
~~~

Trong nhánh này **không có STOMP SEND từ client**, nên message do service tạo **không cần đi qua clientInboundChannel**. Đây là ranh giới rất quan trọng khi truy dấu luồng: nhìn vào subscriber nhận được MESSAGE chưa đủ để biết dữ liệu có nguồn từ STOMP controller, REST API, database change event hay scheduler.

## 10. Demo chạy được: chat + announcement với Spring Boot 3, Java 17

Demo chứa **một Spring Boot server** với WebSocket/STOMP endpoint **/ws**, controller nhận **/app/chat.send**, và browser subscribe hai broker destinations **/topic/chat**, **/topic/announcements**. Một HTTP endpoint kích hoạt publish qua **SimpMessagingTemplate**. Với hai tab browser, quan sát được subscription và broadcast trong một JVM.

Cần **JDK 17+**, Maven và Internet để tải dependencies/CDN của STOMP browser client. Demo dùng Spring Boot **3.5.0** để các API tương thích Spring Framework 6.2.x.

Cấu trúc dự án:

~~~text
stomp-channels-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── MessagingDemoApplication.java
    │   ├── WebSocketConfig.java
    │   ├── ChatController.java
    │   └── AnnouncementController.java
    └── resources/static/index.html
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>stomp-channels-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
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

**src/main/java/demo/MessagingDemoApplication.java**:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessagingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/WebSocketConfig.java**:

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

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
~~~

**src/main/java/demo/ChatController.java**:

~~~java
package demo;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {
    public record ChatInput(String from, String text) {}
    public record ChatEvent(String from, String text) {}

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatEvent send(ChatInput input) {
        return new ChatEvent(input.from(), input.text());
    }
}
~~~

**src/main/java/demo/AnnouncementController.java**:

~~~java
package demo;

import org.springframework.http.ResponseEntity;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AnnouncementController {
    public record Announcement(String text) {}

    private final SimpMessagingTemplate messaging;

    public AnnouncementController(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    @PostMapping("/api/announcements")
    public ResponseEntity<Void> publish(@RequestParam("text") String text) {
        messaging.convertAndSend(
            "/topic/announcements",
            new Announcement(text));
        return ResponseEntity.accepted().build();
    }
}
~~~

**src/main/resources/static/index.html** (vì cùng origin nên WebSocket handshake không đụng lỗi CORS do chạy từ file://):

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>STOMP channels demo</title>
</head>
<body>
  <h1>STOMP channels demo</h1>
  <p id="status">Đang kết nối...</p>
  <button id="send" disabled>Gửi tin chat</button>
  <ol id="feed"></ol>

  <script src="https://cdn.jsdelivr.net/npm/@stomp/stompjs@7/bundles/stomp.umd.min.js"></script>
  <script>
    const status = document.querySelector("#status");
    const feed = document.querySelector("#feed");
    const send = document.querySelector("#send");

    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const client = new StompJs.Client({
      brokerURL: scheme + "://" + location.host + "/ws",
      reconnectDelay: 5000,
      onConnect: () => {
        status.textContent = "STOMP CONNECTED";
        send.disabled = false;

        client.subscribe("/topic/chat", frame => {
          const chat = JSON.parse(frame.body);
          const li = document.createElement("li");
          li.textContent = "Chat " + chat.from + ": " + chat.text;
          feed.append(li);
        });

        client.subscribe("/topic/announcements", frame => {
          const event = JSON.parse(frame.body);
          const li = document.createElement("li");
          li.textContent = "Announcement: " + event.text;
          feed.append(li);
        });
      },
      onWebSocketClose: () => {
        status.textContent = "Mất kết nối, thử nối lại...";
        send.disabled = true;
      },
      onStompError: frame => {
        status.textContent = "STOMP ERROR: " + frame.headers.message;
      }
    });

    send.addEventListener("click", () => {
      client.publish({
        destination: "/app/chat.send",
        body: JSON.stringify({
          from: "An",
          text: "Xin chào qua STOMP"
        }),
        headers: { "content-type": "application/json" }
      });
    });

    client.activate();
  </script>
</body>
</html>
~~~

Ở đây dùng UMD bundle của **@stomp/stompjs** từ CDN để browser có global **StompJs**. Dự án production nên cài npm và bundle client của mình, cấu hình authentication/origin/CSP thích hợp; demo chưa triển khai kiểm tra quyền hoặc validate nội dung chat.

### Chạy và kiểm tra

Tại thư mục **stomp-channels-demo**:

~~~bash
mvn spring-boot:run
~~~

Đợi application khởi động và mở **http://localhost:8080/** trong **hai tab**. Hai tab nên hiển thị **STOMP CONNECTED** khi kết nối thành công.

1. Nhấn **Gửi tin chat** ở tab thứ nhất. Vì cả hai tab đã **SUBSCRIBE /topic/chat**, mỗi tab xuất hiện dòng **Chat An: Xin chào qua STOMP**.
2. Dùng terminal gửi HTTP POST đến REST endpoint:

~~~bash
curl -i -X POST --data-urlencode "text=Hệ thống sẵn sàng" http://localhost:8080/api/announcements
~~~

Response của endpoint là **HTTP 202 Accepted** và không có body. Cả hai tab đang subscribe sẽ thấy **Announcement: Hệ thống sẵn sàng**.

Đây là **kết quả có điều kiện**: nếu browser chưa kết nối/chưa subscribe, server chưa chạy, cổng 8080 đã bị chiếm hoặc CDN không tải được thư viện STOMP, kết quả sẽ khác. Spring Boot log tự sinh phụ thuộc môi trường nên không có stdout cố định cho server. Để chạy nhiều tab an toàn, phải đợi trạng thái CONNECTED trước khi gửi.

### Theo dấu chính xác trong demo

Khi browser gửi chat:

~~~text
Browser A
  publish("/app/chat.send", JSON)
    -> WebSocket /ws
    -> clientInboundChannel
    -> @MessageMapping("/chat.send")
    -> @SendTo("/topic/chat")
    -> brokerChannel
    -> simple broker
    -> clientOutboundChannel
    -> Browser A và B đã subscribe
~~~

Khi gọi HTTP POST announcement:

~~~text
curl -> HTTP @PostMapping("/api/announcements")
     -> SimpMessagingTemplate.convertAndSend("/topic/announcements")
     -> brokerChannel
     -> simple broker
     -> clientOutboundChannel
     -> Browser A và B đã subscribe
~~~

Quan sát rằng nhánh REST **không đi qua clientInboundChannel** và **không gọi @MessageMapping**. Đây chính là khác biệt cần hiểu khi debug event trong ứng dụng dùng cả HTTP và WebSocket.

## 11. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra và sửa |
| --- | --- | --- |
| WebSocket kết nối được nhưng controller không chạy | Client SEND thẳng /topic thay vì /app, hoặc mapping sai | Kiểm tra destination của SEND, application prefix, @MessageMapping |
| Client SUBSCRIBE /app/chat.send nhưng không thấy broadcast | /app dành cho handler; subscription broadcast nằm ở broker destination | Subscribe /topic/chat theo @SendTo |
| Client gửi tới /ws như một STOMP destination | Nhầm WebSocket handshake endpoint với destination | Connect tới ws://host/ws, sau đó publish vào /app/... |
| Tin tới controller nhưng không ai nhận | Không có subscription, @SendTo sai đích, không kết nối broker | Xác minh SUBSCRIBE /topic/... và broker prefix |
| Một user nhận nhiều bản sao | Mở nhiều session, subscription trùng hoặc gửi nhiều lần | Kiểm tra session/subscription id, user destination và reconnect |
| Dùng /queue mà không bảo đảm chỉ một consumer | Simple broker không phải durable queue | Sử dụng external broker phù hợp và đúng ack/routing |
| Thứ tự event bị đảo | Executor xử lý đồng thời | Chỉ bật preserveReceiveOrder/preservePublishOrder khi cần; thêm sequence |
| Sau reconnect bị thiếu tin | Simple broker không lưu offline messages | Đồng bộ từ DB, dùng replay/id, durable broker khi yêu cầu |
| WebSocket handshake trả 403 | Origin/CORS/CSRF/auth configuration | Kiểm tra origin cùng host, policy Spring Security, handshake |
| Có CONNECT nhưng SUBSCRIBE/SEND bị cấm | Messaging authorization riêng | Kiểm tra rule theo type/destination |
| JSON không được convert thành DTO | Payload/schema, content-type hoặc message converter | Gửi JSON hợp lệ và content-type thích hợp |
| Broker relay báo mất kết nối | Broker TCP offline, credentials hoặc mạng | Kiểm tra relay host/port, connection, BrokerAvailabilityEvent |
| Browser không thấy gì ở ví dụ | CDN script lỗi, chưa CONNECTED, không subscribe | Xem browser console/Network và trạng thái STOMP client |

### Debug theo thứ tự hợp lý

1. **Handshake**: WebSocket **/ws** có mở và browser nhận trạng thái CONNECTED không?
2. **Frame**: client thực sự gửi STOMP **SUBSCRIBE** hoặc **SEND** với destination gì?
3. **Routing**: prefix **/app** và **/topic** có đúng với cấu hình server không?
4. **Inbound**: message vào **clientInboundChannel** đã được annotated handler/broker nhận chưa?
5. **Business**: phương thức **@MessageMapping** có chạy, converter có decode DTO đúng không?
6. **Broker**: message có đi vào **brokerChannel** và broker có subscription khớp không?
7. **Outbound**: message có tới **clientOutboundChannel**, WebSocket còn mở, subscriber callback có xử lý JSON không?
8. **Vận hành**: có saturation thread pool, outbound buffer, relay offline, timeout, reconnect hay lỗi authorization không?

Nếu cần kiểm tra channel bằng interceptor, bắt đầu bằng **clientInboundChannel** để xem các frame CONNECT/SUBSCRIBE/SEND. Sau đó kiểm tra brokerChannel hoặc clientOutboundChannel theo nhánh đã xác định. Không kết luận chỉ từ console.log bên browser rằng controller đã được gọi.

## 12. Tóm tắt kiến thức trọng tâm và bài tập

- **STOMP** cung cấp command và headers như SEND, SUBSCRIBE, destination trên WebSocket.
- **Destination** là địa chỉ logic trong STOMP frame; **/ws** là HTTP/WebSocket handshake endpoint, thuộc lớp khác.
- **/app** thường định tuyến tới **@MessageMapping**; **/topic** và **/queue** thường dành cho broker; **/user** dùng ánh xạ destination theo người dùng/phiên.
- **clientInboundChannel** nhận message từ WebSocket clients; **brokerChannel** nhận message do ứng dụng server tạo gửi đến broker; **clientOutboundChannel** chuyển message tới WebSocket clients.
- **@SendTo** và **SimpMessagingTemplate** là hai cách gửi từ ứng dụng tới broker. **@SubscribeMapping** mặc định có thể trả trực tiếp tới client qua outbound channel.
- Simple broker quản lý subscription trong bộ nhớ; external STOMP broker relay chuyển việc broadcast đến broker chuyên dụng qua TCP.
- Executor, ordering, authentication, authorization, reconnect và chất lượng giao nhận đều ảnh hưởng hệ thống ngoài luồng happy path.

### Bài tập tự kiểm tra

1. Đổi **@MessageMapping("/chat.send")** thành **@MessageMapping("/rooms/{roomId}")** và dùng **@DestinationVariable String roomId**; gửi phản hồi đúng **/topic/rooms/{roomId}**. Tại sao có thể cần **SimpMessagingTemplate** thay vì @SendTo tĩnh?
2. Bổ sung **@SubscribeMapping("/snapshot")** trả trạng thái hiện tại, cho browser subscribe **/app/snapshot** rồi so với **/topic/chat**: message nào được broadcast?
3. Dùng **@SendToUser("/queue/errors")** để phản hồi validation errors tới đúng phiên. Thảo luận vì sao **username** do client đặt trong JSON không đủ để xác thực người nhận.
4. Thử client gửi vào **/topic/chat** mà không qua **/app/chat.send**; điều gì xảy ra với controller? Trong ứng dụng thật, rule authorization nào nên ngăn việc này?
5. Giải thích vì sao message phát từ REST **/api/announcements** bỏ qua clientInboundChannel nhưng vẫn tới subscriber.
6. Nếu nhiều instance Spring phục vụ người dùng qua load balancer, chọn simple broker hay broker relay? Muốn bảo đảm tin nhắn sau reconnect, cần thêm tầng lưu trữ/đồng bộ gì?

## Tài liệu tham khảo

- [Spring Framework – STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html)
- [Spring Framework – Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework – Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework – Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework – Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Framework – Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework – External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework – User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework – Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [Spring Framework – Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html)
