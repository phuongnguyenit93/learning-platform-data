# WebSocketHandler thuần và mô hình thông điệp cấp cao trong Spring

## 1. WebSocket là kênh truyền hai chiều, không phải giao thức nghiệp vụ

WebSocket tạo một kết nối hai chiều full-duplex giữa client và server trên một TCP connection. Quá trình bắt đầu bằng HTTP handshake có Upgrade header; sau khi server trả về 101 Switching Protocols, hai phía tiếp tục gửi và nhận frame trên cùng kết nối.

WebSocket chỉ quy định cách truyền frame. Nó không quy định nội dung frame có ý nghĩa gì, ai là người nhận, một message có phải lệnh hay sự kiện, cách đăng ký nhận thông báo, hoặc cách xác nhận xử lý. Client và server phải thống nhất những quy tắc đó.

Spring Framework cung cấp hai mức lập trình chính:

- **WebSocketHandler thuần:** làm việc trực tiếp với WebSocketSession và WebSocketMessage. Ứng dụng tự định nghĩa định dạng payload, loại message, routing, subscription, lỗi và trạng thái phiên.
- **Mô hình messaging cấp cao:** thường dùng STOMP làm sub-protocol trên WebSocket. Spring giải mã STOMP frame thành Message có headers và payload, định tuyến qua MessageChannel, ánh xạ tới @MessageMapping và broker để quản lý subscription, publish và broadcast.

Hai mô hình cùng sử dụng WebSocket transport nhưng cung cấp mức abstraction khác nhau. Chọn mô hình theo nhu cầu về routing và messaging semantics, không chỉ theo việc ứng dụng có cần kết nối real-time hay không.

## 2. So sánh nhanh hai mô hình

| Tiêu chí | WebSocketHandler thuần | Messaging cấp cao với STOMP |
| --- | --- | --- |
| Đơn vị xử lý | WebSocketMessage: text, binary, ping/pong | Spring Message gồm payload và headers, được tạo từ STOMP frame |
| Điểm vào server | Handler được map vào URL WebSocket | STOMP endpoint và message broker infrastructure |
| Routing | Ứng dụng tự thiết kế và triển khai | Destination prefix, @MessageMapping và broker |
| Publish/subscribe | Tự quản lý danh sách session và subscription | Client gửi SUBSCRIBE; broker quản lý subscription |
| Gửi tới client | Gọi WebSocketSession.sendMessage | SimpMessagingTemplate hoặc return value từ @MessageMapping |
| Giao thức ứng dụng | Tự định nghĩa envelope và quy ước | STOMP có CONNECT, SEND, SUBSCRIBE, MESSAGE, DISCONNECT |
| Xác nhận, heartbeat | Tự thiết kế hoặc dùng giao thức riêng | Có cấu trúc STOMP; mức hỗ trợ phụ thuộc broker |
| Mức kiểm soát | Cao, phù hợp giao thức chuyên biệt | Cao về messaging semantics nhưng theo mô hình STOMP/Spring |

WebSocketHandler thuần phù hợp khi giao thức client-server đã được xác định riêng, payload có cấu trúc đặc thù, hoặc cần xử lý frame ở mức thấp. STOMP phù hợp khi ứng dụng cần publish/subscribe, destination routing, controller method, user destination và tích hợp message broker.

## 3. WebSocketHandler thuần hoạt động như thế nào?

Interface WebSocketHandler nhận các callback theo vòng đời kết nối:

- afterConnectionEstablished: được gọi khi handshake thành công và session đã mở.
- handleMessage: nhận WebSocketMessage từ client.
- handleTransportError: thông báo lỗi transport.
- afterConnectionClosed: được gọi khi kết nối đóng.
- supportsPartialMessages: cho biết handler có xử lý message được chia thành nhiều phần hay không.

Trong thực tế, thường mở rộng AbstractWebSocketHandler, TextWebSocketHandler hoặc BinaryWebSocketHandler thay vì tự triển khai tất cả method.

### 3.1. TextWebSocketHandler

TextWebSocketHandler là lớp tiện ích dành cho ứng dụng xử lý text frame. Nó cung cấp callback handleTextMessage để nhận TextMessage cùng WebSocketSession.

~~~java
import java.io.IOException;

import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.stereotype.Component;

@Component
public class EchoWebSocketHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws Exception {

        String reply = "echo: " + message.getPayload();

        if (session.isOpen()) {
            session.sendMessage(new TextMessage(reply));
        }
    }
}
~~~

Handler nhận text payload và gửi lại một text frame. Đây là ví dụ về transport-level echo; nó chưa có destination, subscription hay message broker.

Nếu ứng dụng cần binary payload, hãy mở rộng BinaryWebSocketHandler hoặc xử lý WebSocketMessage phù hợp. Không giả định mọi client đều gửi text JSON; cần thống nhất kiểu frame và giới hạn kích thước message.

### 3.2. Đăng ký handler vào một URL

Dùng @EnableWebSocket và WebSocketConfigurer để map handler vào endpoint:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RawWebSocketConfiguration implements WebSocketConfigurer {

    private final EchoWebSocketHandler echoHandler;

    public RawWebSocketConfiguration(EchoWebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/raw")
                .setAllowedOrigins("https://app.example.com");
    }
}
~~~

Client thực hiện WebSocket handshake đến URL /ws/raw. Sau khi kết nối thành công, tất cả frame ứng dụng được chuyển đến EchoWebSocketHandler.

Trong ứng dụng thật, thay origin ví dụ bằng domain frontend đã được cho phép. Không mở wildcard origin nếu không có lý do và kiểm soát bảo mật tương ứng. WebSocket handshake vẫn cần xác thực người dùng và kiểm tra origin theo chính sách ứng dụng.

Spring WebSocket không bắt buộc phải chạy cùng Spring MVC. Trong ứng dụng Servlet stack, handler thường được đăng ký qua WebSocketConfigurer; môi trường HTTP khác có thể tích hợp WebSocketHandler thông qua WebSocketHttpRequestHandler.

`EchoWebSocketHandler` được đánh dấu `@Component`; bảo đảm package của handler nằm trong component scan để constructor injection của `RawWebSocketConfiguration` hoạt động.

## 4. WebSocketSession và trạng thái kết nối

WebSocketSession đại diện cho một kết nối cụ thể. Những thông tin thường dùng:

| API | Mục đích |
| --- | --- |
| getId() | Lấy session ID |
| getUri() | Lấy URI kết nối |
| getPrincipal() | Lấy người dùng đã được xác thực nếu có |
| getAttributes() | Đọc các thuộc tính được gắn trong handshake |
| isOpen() | Kiểm tra kết nối còn mở |
| sendMessage(message) | Gửi text hoặc binary message |
| close(status) | Đóng kết nối với CloseStatus |
| setTextMessageSizeLimit(...) | Đặt giới hạn kích thước text message |
| setBinaryMessageSizeLimit(...) | Đặt giới hạn kích thước binary message |

Có thể dùng HandshakeInterceptor để kiểm tra hoặc bổ sung thuộc tính trước và sau handshake. Ví dụ HttpSessionHandshakeInterceptor chuyển một số thuộc tính từ HTTP session sang WebSocketSession attributes.

Không nên lưu trạng thái của mọi kết nối vào field mutable của một handler singleton mà không có đồng bộ. Nếu cần quản lý phiên, có thể dùng một registry thread-safe theo session ID, lưu thông tin người dùng và subscription, rồi xóa dữ liệu trong afterConnectionClosed.

Ví dụ quản lý vòng đời:

~~~java
@Override
public void afterConnectionEstablished(WebSocketSession session) {
    sessions.put(session.getId(), session);
}

@Override
public void afterConnectionClosed(
        WebSocketSession session,
        CloseStatus status) {

    sessions.remove(session.getId());
}
~~~

Đoạn code giả định sessions là một registry thread-safe được khai báo và quản lý riêng. Cần xử lý cả trường hợp handshake thành công nhưng client ngắt ngay sau đó, lỗi transport, timeout và việc ứng dụng shutdown.

## 5. Gửi message đồng thời và giới hạn của session

Một WebSocket session tiêu chuẩn không cho phép nhiều thread gọi send đồng thời. Nếu một thread xử lý message và một scheduled task cùng gửi đến một session, việc gọi sendMessage cần được tuần tự hóa.

Spring cung cấp ConcurrentWebSocketSessionDecorator để bọc WebSocketSession. Decorator bảo đảm chỉ một thread gửi tại một thời điểm; các lần gửi khác có thể được buffer trong khi send hiện tại hoàn tất. Nếu giới hạn buffer hoặc thời gian gửi bị vượt quá, session có thể bị đóng theo overflow strategy.

~~~java
WebSocketSession safeSession =
    new ConcurrentWebSocketSessionDecorator(
        session,
        10_000,
        512 * 1024
    );

safeSession.sendMessage(new TextMessage("notification"));
~~~

Trong ví dụ, 10.000 là giới hạn thời gian gửi tính bằng mili giây và 512 KiB là giới hạn buffer. Chọn giới hạn theo khả năng của client và kích thước payload thực tế; không tăng buffer vô hạn vì client chậm có thể làm tiêu thụ bộ nhớ của server.

Nếu dùng STOMP messaging support, Spring cũng có cơ chế xử lý session send concurrency. Tuy vậy, ứng dụng vẫn cần kiểm soát lượng message phát ra, tốc độ tiêu thụ và hành vi khi client không đọc kịp.

## 6. Những việc ứng dụng phải tự xây dựng với handler thuần

WebSocketHandler thuần chỉ cung cấp callback và session API. Để có một hệ thống messaging hoàn chỉnh, ứng dụng phải tự thiết kế thêm các thành phần sau:

1. **Message envelope:** quy ước JSON hoặc binary schema, ví dụ type, id, timestamp, payload và correlationId.
2. **Routing:** xác định message nào là command, event, response hoặc notification và chuyển tới service tương ứng.
3. **Subscription:** lưu session nào đang đăng ký loại sự kiện hoặc channel nào.
4. **Broadcast:** chọn các session phù hợp và gửi message cho từng session.
5. **User routing:** ánh xạ người dùng đã xác thực tới một hoặc nhiều session đang mở.
6. **Heartbeat và timeout:** phát hiện kết nối chết hoặc client không còn phản hồi.
7. **Error protocol:** thống nhất mã lỗi, message lỗi và hành vi đóng kết nối.
8. **Backpressure:** giới hạn hàng đợi gửi, kích thước message và tốc độ phát.
9. **Reconnect và resubscribe:** xử lý client kết nối lại sau khi mạng bị gián đoạn.
10. **Authorization:** kiểm tra người dùng có quyền gửi lệnh hoặc đăng ký nhận dữ liệu hay không.

Ví dụ envelope do ứng dụng tự định nghĩa:

~~~json
{
  "type": "chat.send",
  "id": "msg-1024",
  "correlationId": "request-81",
  "payload": {
    "room": "engineering",
    "text": "Xin chào"
  }
}
~~~

Server phải parse envelope, validate type và payload, kiểm tra quyền truy cập room, rồi chọn session nhận kết quả. WebSocket protocol không tự hiểu các trường type, room hay correlationId.

## 7. Mô hình thông điệp cấp cao của Spring

Khi dùng STOMP over WebSocket, Spring đưa thêm một tầng messaging vào giữa frame và code nghiệp vụ.

Các abstraction nền tảng trong spring-messaging:

- **Message:** biểu diễn message gồm payload và headers.
- **MessageHandler:** hợp đồng xử lý message.
- **MessageChannel:** hợp đồng gửi message, giúp tách producer khỏi consumer.
- **SubscribableChannel:** MessageChannel có các MessageHandler đăng ký.
- **ExecutorSubscribableChannel:** SubscribableChannel sử dụng Executor để dispatch message.

Khi client gửi STOMP frame, Spring giải mã frame thành Spring Message rồi chuyển qua clientInboundChannel. Destination prefix quyết định message được chuyển tới controller hay broker.

Mô hình messaging cấp cao giúp ứng dụng tập trung vào payload và nghiệp vụ. Spring xử lý việc ánh xạ destination, gọi controller, quản lý subscription và gửi message trở lại WebSocket session.

## 8. STOMP là gì và STOMP chạy trên WebSocket ra sao?

STOMP là một text-oriented, frame-based messaging protocol. Nó định nghĩa các command phổ biến như:

| Command | Mục đích |
| --- | --- |
| CONNECT | Bắt đầu STOMP session |
| CONNECTED | Server xác nhận STOMP session |
| SEND | Gửi message đến destination |
| SUBSCRIBE | Đăng ký nhận message từ destination |
| UNSUBSCRIBE | Hủy subscription |
| MESSAGE | Broker gửi message tới subscriber |
| RECEIPT | Xác nhận một frame khi broker hỗ trợ |
| ACK / NACK | Xác nhận hoặc từ chối message khi broker hỗ trợ |
| DISCONNECT | Đóng STOMP session |

Một STOMP frame có command, các header, dòng trống phân cách và body. Ví dụ client gửi:

~~~text
SEND
destination:/app/chat.send
content-type:application/json

{"text":"Xin chào"}
^@
~~~

Một subscriber đăng ký:

~~~text
SUBSCRIBE
id:chat-sub-1
destination:/topic/chat

^@
~~~

WebSocket là transport; STOMP là messaging protocol nằm bên trên. Một kết nối WebSocket có thể mang STOMP frame sau khi client và server thương lượng sub-protocol trong handshake. Nếu không dùng STOMP, client và server phải tự thống nhất quy ước frame như phần WebSocketHandler thuần.

## 9. Cấu hình STOMP endpoint trong Spring

Dùng @EnableWebSocketMessageBroker và WebSocketMessageBrokerConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Hai loại destination prefix có vai trò khác nhau:

- /app: message gửi đến prefix này được định tuyến tới các method @MessageMapping trong controller.
- /topic và /queue: message gửi đến các prefix này được chuyển đến broker để phân phối cho subscription phù hợp.

Với simple broker tích hợp, /topic và /queue chỉ là quy ước đặt tên để phân biệt pub-sub và point-to-point; chúng không có ý nghĩa đặc biệt bắt buộc trong STOMP specification. Khi dùng external broker, hãy kiểm tra quy tắc destination của broker đó.

## 10. Luồng message qua controller và broker

Giả sử client kết nối /ws, subscribe /topic/chat và gửi message đến /app/chat.send.

~~~mermaid
flowchart TD
    C[WebSocket client] -->|STOMP CONNECT / SEND / SUBSCRIBE| I[WebSocket + STOMP decoder]
    I --> IN[clientInboundChannel]
    IN -->|/app/**| CTRL[@MessageMapping controller]
    IN -->|/topic/** hoặc /queue/**| B[Message broker]
    CTRL -->|return value hoặc SimpMessagingTemplate| BC[brokerChannel]
    BC --> B
    B --> OUT[clientOutboundChannel]
    OUT --> E[STOMP encoder]
    E -->|MESSAGE frame| C
~~~

Các bước cụ thể:

1. Client kết nối tới URL handshake /ws.
2. Client gửi STOMP CONNECT; server trả CONNECTED.
3. Client gửi SUBSCRIBE tới /topic/chat. Broker lưu subscription cho session đó.
4. Client gửi SEND tới /app/chat.send.
5. Spring chuyển frame thành Message và đưa vào clientInboundChannel.
6. Prefix /app khiến message được chuyển đến method @MessageMapping sau khi bỏ prefix.
7. Controller xử lý payload và trả kết quả hoặc gửi message qua SimpMessagingTemplate.
8. Message được đưa qua brokerChannel đến broker.
9. Broker tìm các subscription phù hợp và gửi MESSAGE frame qua clientOutboundChannel đến từng WebSocket session.

Ba channel thường được nhắc đến:

| Channel | Hướng và mục đích |
| --- | --- |
| clientInboundChannel | Nhận Spring Message được giải mã từ WebSocket client |
| brokerChannel | Gửi message từ code server-side tới broker |
| clientOutboundChannel | Gửi message từ broker về WebSocket client |

## 11. Xử lý message bằng @MessageMapping

Controller xử lý destination thuộc application prefix bằng @MessageMapping:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(@Payload ChatMessage message) {
        return message;
    }
}

record ChatMessage(String sender, String text) {
}
~~~

Nếu client gửi đến /app/chat.send, Spring gọi method send. Giá trị trả về được chuyển thành Spring Message và gửi tới /topic/chat nhờ @SendTo.

Trong ứng dụng thực tế, hãy lấy danh tính người gửi từ Principal đã được xác thực thay vì tin trường sender do client gửi. Controller nên validate payload, giới hạn độ dài nội dung và kiểm tra quyền tham gia room trước khi broadcast.

Có thể dùng @MessageExceptionHandler để chuyển lỗi nghiệp vụ thành response phù hợp hoặc cấu hình error handling ở tầng messaging. Không gửi stack trace hay thông tin nhạy cảm về client.

## 12. Gửi message từ service bằng SimpMessagingTemplate

Không phải message nào cũng xuất phát từ @MessageMapping. Một service, scheduled task hoặc HTTP controller cũng có thể gửi đến broker:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(String text) {
        messagingTemplate.convertAndSend(
            "/topic/notifications",
            new Notification(text)
        );
    }
}

public record Notification(String text) {
}
~~~

convertAndSend chuyển payload thành Spring Message và gửi vào brokerChannel. Broker phân phối message đến những client đã subscribe destination tương ứng.

Để gửi riêng cho người dùng, có thể dùng convertAndSendToUser với user name đã được Spring Security xác thực và một user destination, ví dụ /queue/notifications. Không lấy user name từ payload client rồi xem đó là danh tính đáng tin cậy.

## 13. Simple broker và external STOMP broker relay

Spring có thể sử dụng broker tích hợp hoặc chuyển tiếp tới một broker STOMP bên ngoài.

| Tiêu chí | Simple broker | Broker relay |
| --- | --- | --- |
| Triển khai | In-memory trong ứng dụng Spring | Spring chuyển frame tới broker STOMP bên ngoài |
| Subscription | Lưu trong bộ nhớ của application instance | Broker bên ngoài quản lý |
| Tính năng STOMP | Chỉ hỗ trợ một tập con command | Phụ thuộc broker, thường đầy đủ hơn |
| Clustering | Không phù hợp để chia sẻ subscription giữa nhiều node | Có thể dùng broker cluster theo sản phẩm |
| Vận hành | Dễ cấu hình để phát triển và thử nghiệm | Cần cài đặt, bảo mật, giám sát và vận hành broker |
| Quy mô | Phù hợp tải nhỏ hoặc ứng dụng đơn giản | Phù hợp nhu cầu phân phối message lớn và nhiều node |

Simple broker không hỗ trợ đầy đủ các tính năng như ACK, RECEIPT và không phù hợp cho clustering. Khi cần broker đầy đủ, có thể cấu hình relay:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue");
}
~~~

Broker relay duy trì TCP connection tới external STOMP broker, chuyển message từ Spring lên broker và chuyển message từ broker về các WebSocket client. Ứng dụng phải cấu hình host, port, credentials, virtual host, heartbeat và connection recovery phù hợp với broker cụ thể.

Không nhầm STOMP broker relay với việc Spring gửi JMS message. Đây là tích hợp STOMP qua TCP; muốn dùng RabbitMQ hoặc ActiveMQ cần bật STOMP plugin/protocol endpoint tương ứng trên broker.

## 14. SockJS fallback và khả năng tương thích client

Một số môi trường mạng hoặc trình duyệt có thể không hỗ trợ WebSocket đúng cách. Spring có thể bật SockJS fallback trên STOMP endpoint:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com")
            .withSockJS();
}
~~~

SockJS mô phỏng API WebSocket và có thể sử dụng các transport thay thế như XHR streaming hoặc long polling khi WebSocket không khả dụng. Client phải dùng SockJS client cùng STOMP client tương thích.

Nếu tất cả client hiện đại đều hỗ trợ WebSocket và hạ tầng cho phép Upgrade, có thể dùng WebSocket trực tiếp để giảm lớp transport fallback. SockJS không thay thế STOMP; một cái cung cấp fallback transport, cái kia cung cấp messaging protocol.

## 15. Handshake, authentication và authorization

WebSocket bắt đầu bằng HTTP handshake, vì vậy ứng dụng cần xử lý xác thực và origin ngay từ lúc kết nối.

- Dùng Spring Security hoặc cơ chế xác thực HTTP hiện có để xác định Principal.
- Giới hạn allowed origins theo domain frontend đáng tin cậy.
- Dùng HandshakeInterceptor khi cần chuyển thuộc tính HTTP session vào WebSocketSession.
- Với STOMP, kiểm tra quyền SEND và SUBSCRIBE theo destination trên inbound channel.
- Không tin user ID, role hoặc tenant ID do client tự gửi trong JSON payload hay STOMP header.
- Giới hạn kích thước message, số kết nối, tốc độ gửi và số subscription trên mỗi user.
- Dùng WSS trong môi trường production để mã hóa traffic.
- Đóng session khi token hết hạn hoặc quyền truy cập bị thu hồi theo chính sách hệ thống.

Trong Spring STOMP support, login/passcode trong STOMP CONNECT không phải nguồn xác thực người dùng thay thế cho HTTP authentication; thông tin đó có thể bị bỏ qua hoặc ghi đè theo cấu hình server. Hãy dựa vào Principal đã được xác thực và cấu hình Spring Security message authorization.

## 16. Quan sát, lỗi và vòng đời session

Với raw handler, các callback afterConnectionEstablished, handleTransportError và afterConnectionClosed là những điểm chính để ghi log và quản lý trạng thái session. Nên log session ID, user ID đã xác thực, close status và loại lỗi, nhưng tránh ghi payload nhạy cảm.

Với STOMP, Spring phát các application event liên quan đến kết nối, đăng ký và ngắt kết nối, chẳng hạn SessionConnectEvent, SessionConnectedEvent, SessionSubscribeEvent và SessionDisconnectEvent. Có thể dùng listener cho các event đó để cập nhật presence, số kết nối hoặc cleanup trạng thái.

Các lưu ý vận hành:

- Một user có thể mở nhiều tab, tức nhiều WebSocket session cùng lúc.
- Client có thể mất mạng mà không gửi DISCONNECT; cần heartbeat và timeout để dọn session.
- Server restart làm kết nối hiện tại bị ngắt; client cần reconnect và subscribe lại.
- Broker relay cần theo dõi connection tới broker và heartbeat hai chiều.
- Client chậm có thể làm outbound buffer tăng; đặt giới hạn và chính sách đóng session.
- Không giả định message gửi thành công đồng nghĩa client đã đọc hoặc xử lý xong payload.
- Với thông điệp quan trọng, cần acknowledgement hoặc lưu trạng thái nghiệp vụ ở tầng ứng dụng/broker phù hợp.

## 17. Bảo toàn thứ tự message

Spring dùng executor-backed channel cho một số đường gửi đến client. Nếu nhiều message được publish nhanh, các task có thể chạy trên nhiều thread và thứ tự client nhận không nhất thiết trùng với thứ tự publish.

Nếu ứng dụng cần giữ thứ tự publish cho từng WebSocket session, có thể cấu hình:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

Cấu hình này có thể giảm throughput do các message đến cùng session được xử lý tuần tự hơn. Chỉ bật khi nghiệp vụ thực sự phụ thuộc thứ tự. Nếu cần thứ tự theo từng room hoặc aggregate, cân nhắc partitioning theo khóa nghiệp vụ.

## 18. Chọn raw handler hay STOMP messaging?

Chọn WebSocketHandler thuần khi:

- Client và server dùng một protocol chuyên biệt đã được định nghĩa rõ.
- Cần kiểm soát trực tiếp binary frame hoặc envelope riêng.
- Không cần destination broker, subscription chuẩn hay controller mapping.
- Đội phát triển sẵn sàng tự xây dựng session registry, routing, backpressure và lifecycle.

Chọn STOMP messaging khi:

- Nhiều client cần subscribe/publish tới destination.
- Cần route message vào @MessageMapping controller.
- Muốn dùng SimpMessagingTemplate từ service hoặc HTTP controller.
- Cần user destination và broker relay.
- Muốn dựa trên các abstraction Message, MessageChannel và MessageHandler của Spring.

Không nên chọn raw handler chỉ vì payload hiện tại là JSON; STOMP cũng có thể mang JSON body. Ngược lại, không cần dùng STOMP nếu ứng dụng chỉ cần một giao thức request/event riêng và đã có cơ chế routing phù hợp.

## 19. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Handshake trả 404 | Endpoint chưa được map hoặc URL client sai | Kiểm tra addHandler/addEndpoint và context path |
| Handshake bị từ chối | Origin không nằm trong allow-list hoặc authentication thất bại | Kiểm tra allowed origins và security filter |
| WebSocket kết nối được nhưng @MessageMapping không chạy | Client gửi SEND sai destination prefix hoặc thiếu STOMP frame | Kiểm tra CONNECT, SEND và /app prefix |
| Client không nhận broadcast | Chưa SUBSCRIBE đúng destination hoặc broker prefix sai | Kiểm tra SUBSCRIBE và /topic, /queue |
| Gửi trực tiếp qua session bị lỗi concurrent send | Nhiều thread gửi cùng WebSocketSession | Tuần tự hóa send hoặc dùng ConcurrentWebSocketSessionDecorator |
| Session registry tăng mãi | Không cleanup khi connection đóng hoặc transport error | Xử lý afterConnectionClosed và lỗi kết nối |
| Simple broker không hoạt động giữa nhiều node | Subscription chỉ được giữ trong bộ nhớ từng instance | Dùng broker relay hoặc giải pháp broker dùng chung |
| Client nhận message sai thứ tự | Outbound channel xử lý trên nhiều thread | Cân nhắc setPreservePublishOrder(true) |
| Client gửi payload quá lớn | Chưa đặt message-size limit | Giới hạn text/binary size và validate payload |
| Client giả mạo user hoặc tenant | Tin dữ liệu nhận dạng trong payload/header do client gửi | Dùng Principal và authorization ở server |
| Kết nối bị rớt khi proxy idle | Proxy/load balancer không giữ kết nối hoặc thiếu heartbeat | Cấu hình timeout proxy và heartbeat phù hợp |
| Server gửi message nhưng client chưa xử lý | Gửi frame không phải acknowledgement nghiệp vụ | Thiết kế ACK/receipt hoặc trạng thái xử lý riêng nếu cần |

## 20. Checklist triển khai production

- [ ] Chọn rõ raw WebSocket protocol hay STOMP messaging.
- [ ] Khai báo endpoint và mapping URL chính xác.
- [ ] Xác thực handshake và giới hạn allowed origins.
- [ ] Xác định message schema, version và giới hạn payload.
- [ ] Nếu dùng raw handler, xây dựng routing, subscription, session registry và cleanup.
- [ ] Tuần tự hóa các lần gửi trên cùng WebSocketSession.
- [ ] Nếu dùng STOMP, cấu hình application prefix và broker destination prefix rõ ràng.
- [ ] Chọn simple broker hay external broker relay theo yêu cầu clustering và STOMP features.
- [ ] Cấu hình authorization cho SEND và SUBSCRIBE.
- [ ] Cấu hình heartbeat, reconnect và resubscribe.
- [ ] Đặt giới hạn outbound buffer và message size.
- [ ] Kiểm thử nhiều tab, client chậm, mất mạng, server restart và broker restart.
- [ ] Theo dõi số session, subscription, outbound queue, send latency, error rate và reconnect.

## 21. Tài liệu tham khảo

- [Spring Framework 7.0 — WebSockets overview](https://docs.spring.io/spring-framework/reference/7.0/web/websocket.html)
- [Spring Framework 7.0 — WebSocket API and WebSocketHandler](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/server.html)
- [Spring Framework 7.0 — Enable STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/enable.html)
- [Spring Framework 7.0 — Flow of Messages](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/message-flow.html)
- [Spring Framework 7.0 — Simple Broker](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework 7.0 — External Broker Relay](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework 7.0 — Sending Messages](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-send.html)
- [Spring Framework 7.0 — ConcurrentWebSocketSessionDecorator API](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html)
- [Spring Framework 7.0 — WebSocketHandler API](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/WebSocketHandler.html)
- [Spring Framework 7.0 — WebSocketSession API](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/WebSocketSession.html)
