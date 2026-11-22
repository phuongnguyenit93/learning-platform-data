# WebSocket và giao tiếp hai chiều trên kết nối lâu dài

## 1. WebSocket giải quyết vấn đề gì?

WebSocket là giao thức cho phép client và server trao đổi dữ liệu hai chiều trên một kết nối TCP duy nhất tồn tại lâu dài. Sau khi kết nối được thiết lập, cả hai phía đều có thể chủ động gửi message mà không cần tạo một HTTP request mới cho từng lần trao đổi.

Với HTTP request/response thông thường, client gửi request và server trả response. Nếu server có dữ liệu mới sau khi response đã kết thúc, client phải gửi request khác, polling hoặc dùng một kỹ thuật streaming. WebSocket phù hợp với ứng dụng cần cập nhật nhanh, thường xuyên và có luồng dữ liệu đi từ cả client tới server lẫn server tới client.

Một số trường hợp sử dụng:

- Chat, cộng tác trực tuyến và trạng thái người dùng.
- Bảng giá, dashboard, theo dõi đơn hàng hoặc trạng thái tác vụ gần thời gian thực.
- Game nhiều người chơi và ứng dụng tương tác.
- Điều khiển thiết bị hoặc giám sát cần phản hồi liên tục.
- Giao diện cần nhận thông báo ngay khi server có sự kiện mới.

WebSocket không phải lựa chọn mặc định cho mọi API. Nếu client chỉ cần đọc dữ liệu thỉnh thoảng, REST, Server-Sent Events hoặc polling có thể dễ vận hành hơn. Kết nối lâu dài cũng giữ socket, bộ nhớ và trạng thái trên server trong suốt thời gian client kết nối.

## 2. Bắt tay HTTP Upgrade và vòng đời kết nối

WebSocket bắt đầu bằng một HTTP request có các header yêu cầu nâng cấp giao thức:

~~~http
GET /ws/echo HTTP/1.1
Host: api.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <random-key>
Sec-WebSocket-Version: 13
Origin: https://app.example.com
~~~

Nếu server chấp nhận, nó trả về HTTP 101 Switching Protocols, cùng các header xác nhận WebSocket handshake. Sau đó, TCP connection được giữ mở và hai phía trao đổi WebSocket frame trên cùng socket.

~~~text
Browser / Java client                  Spring application
        |                                      |
        |------ HTTP Upgrade request --------->|
        |<----- 101 Switching Protocols -------|
        |                                      |
        |<========= WebSocket connection =====>|
        |                                      |
        |------ Text / Binary message -------->|
        |<----- Text / Binary message ---------|
        |------ Text / Binary message -------->|
        |<----- Server push -------------------|
        |                                      |
        |------ Close frame ------------------>|
        |<----- Close frame -------------------|
        |                                      |
        |---------- TCP socket closed ---------|
~~~

Các trạng thái thường gặp:

1. **CONNECTING:** client đang thực hiện handshake.
2. **OPEN:** handshake thành công; hai phía có thể gửi và nhận message.
3. **CLOSING:** một phía đã bắt đầu WebSocket closing handshake.
4. **CLOSED:** kết nối đã đóng hoặc không thể được thiết lập.

Handshake chỉ xảy ra lúc kết nối ban đầu. Các message tiếp theo không phải những HTTP request độc lập và không được định tuyến bằng HTTP method như GET/POST.

### 2.1. Frame và message

WebSocket định nghĩa các loại frame chính:

- **Text:** dữ liệu văn bản UTF-8; thường dùng JSON hoặc một giao thức text như STOMP.
- **Binary:** dữ liệu nhị phân như protobuf, ảnh hoặc dữ liệu ứng dụng tùy định dạng.
- **Ping/Pong:** frame điều khiển để kiểm tra kết nối và keepalive.
- **Close:** bắt đầu hoặc phản hồi quy trình đóng kết nối.

Một message có thể được chia thành nhiều frame (fragmentation). Thư viện WebSocket thường ghép các frame thành message hoàn chỉnh trước khi chuyển cho handler. Ứng dụng nên đặt giới hạn kích thước message và không giả định payload có thể lớn tùy ý.

Ping/Pong thuộc tầng giao thức, không phải message nghiệp vụ. Browser WebSocket API không cung cấp hàm JavaScript để tự gửi control Ping; runtime xử lý control frame theo giao thức. Nếu ứng dụng cần heartbeat nghiệp vụ, có thể định nghĩa message riêng hoặc dùng heartbeat của STOMP.

### 2.2. WebSocket không định nghĩa cấu trúc nghiệp vụ

WebSocket chỉ định nghĩa cách truyền frame, không quy định nội dung message có nghĩa gì. Client và server phải thống nhất định dạng payload, ví dụ:

~~~json
{
  "type": "order-status",
  "messageId": "m-1042",
  "sentAt": "2026-11-07T10:00:00Z",
  "payload": {
    "orderId": "O-1001",
    "status": "SHIPPED"
  }
}
~~~

Ứng dụng cần tự định nghĩa:

- Các loại message hợp lệ và schema payload.
- Cách xác thực, phân quyền và kiểm tra dữ liệu.
- Correlation ID, message ID, sequence number nếu cần.
- Quy tắc retry, duplicate, acknowledgment và xử lý message sai định dạng.
- Phiên bản giao thức khi client và server được triển khai độc lập.

Không nên coi việc gửi thành công một WebSocket frame là bằng chứng nghiệp vụ ở phía nhận đã xử lý hoặc lưu dữ liệu thành công.

## 3. WebSocket trong Spring Framework

Spring Framework hỗ trợ WebSocket ở Servlet stack thông qua module `spring-websocket`. Có hai cách lập trình phổ biến:

| Cách tiếp cận | Khi phù hợp | Thành phần chính |
|---|---|---|
| Raw WebSocket | Ứng dụng tự định nghĩa message format và routing | `WebSocketHandler`, `TextWebSocketHandler`, `WebSocketSession` |
| STOMP over WebSocket | Cần publish/subscribe, destination, controller và broker | `@EnableWebSocketMessageBroker`, `@MessageMapping`, `SimpMessagingTemplate` |

Cả hai cách đều sử dụng WebSocket làm transport. STOMP là giao thức tầng ứng dụng chạy trên WebSocket, cung cấp cấu trúc message, command, destination và subscription.

Spring WebSocket Servlet stack và Spring WebFlux WebSocket là hai API khác nhau. WebFlux sử dụng kiểu reactive Mono/Flux; ví dụ trong bài này dùng Spring WebSocket trên Servlet stack với Java 17 và Spring Framework 6.2.

## 4. Raw WebSocket với WebSocketHandler

Spring cung cấp interface `WebSocketHandler`. Với message text, thường kế thừa `TextWebSocketHandler`; với message binary, dùng `BinaryWebSocketHandler`.

Một handler nhận các callback chính:

| Callback | Thời điểm |
|---|---|
| `afterConnectionEstablished(session)` | Handshake thành công, session đã mở |
| `handleMessage(session, message)` | Nhận message từ client |
| `handleTransportError(session, exception)` | Lỗi transport hoặc lỗi xử lý ở tầng WebSocket |
| `afterConnectionClosed(session, status)` | Kết nối đã đóng |
| `supportsPartialMessages()` | Cho biết handler có xử lý message phân mảnh từng phần hay không |

Ví dụ handler echo:

~~~java
public class EchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {

        String payload = message.getPayload();
        session.sendMessage(new TextMessage("echo:" + payload));
    }
}
~~~

`WebSocketSession` đại diện cho một kết nối cụ thể. Nó cung cấp session ID, URI, handshake headers, attributes, Principal, địa chỉ local/remote, trạng thái open/closed và phương thức gửi message.

Handler thường là Spring singleton bean. Không lưu dữ liệu riêng của một client vào field đơn lẻ dùng chung cho mọi client. Nếu cần quản lý nhiều session, dùng collection thread-safe được khóa theo session ID và xóa session khi kết nối đóng.

## 5. Đăng ký endpoint bằng @EnableWebSocket

Spring cho phép ánh xạ handler tới URL bằng `@EnableWebSocket` và `WebSocketConfigurer`.

~~~java
@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoHandler echoHandler;

    public WebSocketConfiguration(EchoHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {

        registry.addHandler(echoHandler, "/ws/echo")
                .setAllowedOrigins("https://app.example.com");
    }
}

@Component
public class EchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {

        session.sendMessage(
            new TextMessage("echo:" + message.getPayload())
        );
    }
}
~~~

Ứng dụng cần chạy trong một môi trường HTTP Servlet hỗ trợ WebSocket, ví dụ Tomcat, Jetty hoặc Undertow tương thích với phiên bản Spring. Cấu hình WebSocket phải được đăng ký trong web application context xử lý handshake.

Không cần `@EnableWebSocketMessageBroker` nếu chỉ dùng raw handler. Annotation đó dành cho cấu hình STOMP message broker ở phần sau.

### 5.1. HandshakeInterceptor và session attributes

`HandshakeInterceptor` chạy trước và sau HTTP handshake. Nó có thể:

- Từ chối kết nối nếu request không đáp ứng điều kiện.
- Đọc thông tin request đã được xác thực.
- Đưa các giá trị cần thiết vào attributes của `WebSocketSession`.
- Ghi nhận metadata phục vụ logging hoặc theo dõi kết nối.

Ví dụ dùng interceptor có sẵn để sao chép HTTP session attributes:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .addInterceptors(new HttpSessionHandshakeInterceptor())
        .setAllowedOrigins("https://app.example.com");
~~~

Các attributes được truyền vào `WebSocketSession.getAttributes()`. Nếu cần tùy chỉnh handshake sâu hơn, có thể triển khai `HandshakeInterceptor` hoặc cung cấp `DefaultHandshakeHandler`.

`HandshakeInterceptor` không thay thế xác thực. Nó chỉ kiểm tra request và truyền metadata; xác thực nên được thực hiện bởi Spring Security hoặc cơ chế xác thực HTTP phù hợp trước khi nâng cấp kết nối.

## 6. Client browser dùng WebSocket API

Browser có WebSocket API chuẩn:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws/echo");

socket.addEventListener("open", () => {
    console.log("connected");
    socket.send("hello from browser");
});

socket.addEventListener("message", (event) => {
    console.log("server:", event.data);
});

socket.addEventListener("error", () => {
    console.error("websocket error");
});

socket.addEventListener("close", (event) => {
    console.log("closed:", event.code, event.reason, event.wasClean);
});
~~~

Một số điểm cần chú ý:

- Dùng `wss://` khi trang web được phục vụ qua HTTPS.
- Chỉ gọi `send()` sau khi `readyState === WebSocket.OPEN`.
- Payload có thể là string, Blob hoặc ArrayBuffer tùy định dạng.
- Sự kiện `message` nhận dữ liệu từ server; server có thể gửi message bất kỳ lúc nào khi socket còn mở.
- Browser API không có backpressure tích hợp. Ứng dụng cần giới hạn tốc độ gửi và tránh xếp hàng dữ liệu không giới hạn ở phía client.

Nếu client cần tự reconnect, hãy dùng exponential backoff có jitter, giới hạn số lần thử hoặc thời gian retry, và khôi phục subscription/state sau khi kết nối lại. Không reconnect liên tục với khoảng thời gian rất ngắn khi server đang lỗi.

## 7. Gửi message từ server tới client

Một lợi ích quan trọng của WebSocket là server có thể chủ động gửi message sau khi handshake, không cần chờ một request mới. Ví dụ server gửi cập nhật tiến độ, notification hoặc kết quả xử lý nền.

Một handler có thể lưu session theo ID:

~~~java
public class NotificationHandler extends TextWebSocketHandler {

    private final Map<String, WebSocketSession> sessions =
        new ConcurrentHashMap<>();

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        WebSocketSession safeSession =
            new ConcurrentWebSocketSessionDecorator(
                session, 10_000, 512 * 1024
            );

        sessions.put(session.getId(), safeSession);
    }

    public void notifyClient(String sessionId, String text)
            throws IOException {

        WebSocketSession session = sessions.get(sessionId);
        if (session != null && session.isOpen()) {
            session.sendMessage(new TextMessage(text));
        }
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session,
            CloseStatus status) {

        sessions.remove(session.getId());
    }
}
~~~

Trong ứng dụng thật, cần xử lý thêm lỗi khi gửi, xóa session khi transport error, xác định user được phép nhận notification và giới hạn số lượng session. Có thể dùng `Principal` từ `WebSocketSession` để liên kết kết nối với người dùng đã xác thực.

Không gửi notification cho mọi session chỉ vì biết session ID. Session ID là định danh transport, không phải cơ chế phân quyền.

## 8. Đồng bộ khi nhiều thread cùng gửi

Một WebSocket session chuẩn không cho phép nhiều thread ghi đồng thời. Nếu nhiều thread cùng gọi `sendMessage()` trên cùng session, frame có thể bị lỗi hoặc việc gửi có thể không an toàn.

Khi dùng raw `WebSocketHandler`, hãy tuần tự hóa thao tác gửi. Spring cung cấp `ConcurrentWebSocketSessionDecorator` để bọc session, khóa thao tác send và quản lý giới hạn thời gian/buffer.

~~~java
WebSocketSession safeSession =
    new ConcurrentWebSocketSessionDecorator(
        session,
        10_000,       // send time limit, milliseconds
        512 * 1024    // maximum buffered bytes
    );
~~~

Nếu gửi chậm hơn tốc độ tạo message, buffer sẽ tăng. Đặt giới hạn hữu hạn và quyết định cách xử lý client chậm: giảm tần suất cập nhật, gộp state mới nhất, bỏ message không quan trọng hoặc đóng session khi vượt ngưỡng.

STOMP message broker configuration của Spring đã xử lý việc tuần tự hóa gửi tới từng session. Tuy nhiên, vẫn cần cấu hình send time limit và send buffer size limit để tránh một client chậm làm tích tụ bộ nhớ.

## 9. STOMP over WebSocket

WebSocket truyền text/binary frame nhưng không quy định ý nghĩa payload. STOMP bổ sung command và destination để client gửi, subscribe và nhận message theo mô hình messaging.

Các command STOMP thường gặp:

- `CONNECT`: bắt đầu STOMP session.
- `CONNECTED`: server xác nhận kết nối STOMP.
- `SEND`: gửi message tới destination.
- `SUBSCRIBE`: đăng ký nhận message từ destination.
- `MESSAGE`: server gửi message tới subscriber.
- `UNSUBSCRIBE`: hủy subscription.
- `DISCONNECT`: kết thúc STOMP session.

Một STOMP frame có command, headers và body. Vì vậy, ứng dụng không cần tự thiết kế toàn bộ quy tắc routing, subscription và broadcast như raw WebSocket.

### 9.1. Cấu hình STOMP endpoint

Dùng `@EnableWebSocketMessageBroker`:

~~~java
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

Ý nghĩa:

- Client kết nối WebSocket tới endpoint `/ws`.
- Message có destination bắt đầu bằng `/app` được chuyển tới các method `@MessageMapping`.
- Message có destination bắt đầu bằng `/topic` hoặc `/queue` được chuyển tới simple broker để phân phối cho subscriber.

Với simple broker tích hợp, `/topic` và `/queue` chỉ là quy ước prefix do ứng dụng chọn; chúng không tự có semantics đặc biệt ở tầng WebSocket. Broker bên ngoài có thể định nghĩa destination và semantics khác.

### 9.2. Controller nhận và phát message

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

Client gửi tới `/app/chat.send`. Spring gọi method `send`, sau đó phát kết quả tới `/topic/chat`. Các client đã subscribe destination này sẽ nhận message.

Nếu cần gửi từ service hoặc tác vụ nền, dùng `SimpMessagingTemplate`:

~~~java
@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishStatus(OrderStatus status) {
        messagingTemplate.convertAndSend("/topic/orders", status);
    }
}
~~~

Có thể gửi riêng cho user bằng user destination, ví dụ `/user/queue/notifications`. Spring ánh xạ destination này tới session của người dùng đã xác thực.

### 9.3. Browser client với STOMP.js

STOMP.js là thư viện JavaScript thường dùng cho STOMP over WebSocket:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    reconnectDelay: 5000,

    onConnect: () => {
        client.subscribe("/topic/chat", (frame) => {
            console.log("chat:", frame.body);
        });

        client.publish({
            destination: "/app/chat.send",
            body: JSON.stringify({ text: "hello" })
        });
    },

    onStompError: (frame) => {
        console.error("broker error:", frame.headers["message"]);
    }
});

client.activate();
~~~

Sau reconnect, STOMP client cần subscribe lại trong `onConnect`. Nếu dùng token hoặc custom authentication, thiết kế handshake/CONNECT interceptor theo cơ chế xác thực của server; không gửi credential trong URL query string vì URL có thể xuất hiện trong access log, proxy log hoặc telemetry.

## 10. Simple broker và external broker relay

Spring cung cấp simple broker để giữ subscription và phát message trong bộ nhớ của một application instance. Nó phù hợp với ứng dụng nhỏ, demo hoặc trường hợp không cần broker độc lập.

Simple broker có các giới hạn:

- Subscription state nằm trong bộ nhớ của process.
- Không tự chia sẻ subscription giữa nhiều instance Spring.
- Không cung cấp đầy đủ tính năng lưu trữ, durability hoặc routing chuyên sâu của message broker.
- Restart instance có thể làm mất trạng thái subscription hiện tại.

Khi cần scale nhiều application instance hoặc dùng khả năng broker chuyên dụng, cấu hình STOMP broker relay:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.example.com")
            .setRelayPort(61613)
            .setClientLogin("web-client")
            .setClientPasscode("replace-with-secret");
}
~~~

Broker relay duy trì kết nối TCP tới broker. Có kết nối hệ thống cho message từ server application và các kết nối riêng thay mặt cho client WebSocket. Cần cấu hình credentials, TLS/network policy, connection quota và destination permissions theo broker.

Không nhúng mật khẩu thật trong source code. Dùng secret manager hoặc cấu hình môi trường an toàn.

## 11. SockJS khi WebSocket không khả dụng

Một số proxy, firewall hoặc load balancer không chuyển tiếp header `Upgrade`, hoặc đóng kết nối lâu không có traffic. SockJS cung cấp cơ chế emulation: thử WebSocket trước, sau đó fallback sang HTTP streaming hoặc long polling khi cần.

Raw handler có thể bật SockJS:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .withSockJS();
~~~

Với STOMP endpoint:

~~~java
registry.addEndpoint("/ws")
        .withSockJS();
~~~

Client sử dụng `sockjs-client` thay cho browser WebSocket API trực tiếp. SockJS cung cấp API gần giống WebSocket nhưng có thể sử dụng nhiều HTTP request cho streaming/polling transport.

Cần lưu ý:

- SockJS không biến HTTP polling thành một TCP WebSocket connection thật; nó mô phỏng semantics giao tiếp.
- HTTP streaming và polling tạo thêm request, overhead và yêu cầu cấu hình proxy khác.
- Nếu ứng dụng phụ thuộc cookie session hoặc sticky session, kiểm tra cách load balancer định tuyến các request SockJS.
- SockJS có heartbeat mặc định để tránh proxy coi kết nối idle là đã chết; có thể cấu hình theo nhu cầu.
- Chỉ bật fallback khi môi trường client/proxy thực sự cần nó.

## 12. Xác thực, Origin và phân quyền

Kết nối WebSocket vẫn cần xác thực và authorization. Việc handshake thành công không có nghĩa client được phép gửi mọi message hoặc subscribe mọi destination.

Các nguyên tắc quan trọng:

1. **Dùng TLS:** browser production nên kết nối bằng `wss://`; bảo vệ cả dữ liệu và cookie/token khi truyền.
2. **Kiểm tra Origin:** Spring WebSocket mặc định chỉ chấp nhận same-origin. Nếu frontend ở origin khác, khai báo allowlist cụ thể bằng `setAllowedOrigins(...)`.
3. **Origin không phải authentication:** client không phải browser có thể tự đặt header Origin. Vẫn phải xác thực danh tính và phân quyền.
4. **Tận dụng HTTP authentication:** với STOMP, Spring có thể liên kết Principal đã xác thực ở HTTP handshake với WebSocket/STOMP session.
5. **Không tin user ID từ payload:** dùng `Principal` của session để xác định người gửi; client không được tự khai báo danh tính người khác.
6. **Phân quyền theo message type và destination:** kiểm tra cả SEND và SUBSCRIBE. Một client có thể được phép subscribe `/topic/notifications` nhưng không được phép publish trực tiếp vào destination hệ thống.
7. **Chống CSWSH/CSRF:** nếu dùng cookie-based authentication, kiểm tra Origin và cấu hình Spring Security phù hợp. Với Spring Security STOMP, CONNECT thường cần CSRF token.
8. **Giới hạn dữ liệu:** kiểm tra schema, độ dài, tốc độ message và quyền truy cập trước khi thực hiện nghiệp vụ.

Với token authentication ở STOMP CONNECT, có thể đăng ký `ChannelInterceptor` trên inbound channel để xác thực header và gắn `Principal` bằng `StompHeaderAccessor.setUser(...)`. Cấu hình interceptor xác thực phải chạy trước interceptor authorization của Spring Security.

Raw WebSocket không có STOMP inbound channel. Với raw handler, thực hiện authorization trực tiếp trong handler/service và sử dụng Principal hoặc session attributes đáng tin cậy.

## 13. Heartbeat, timeout và đóng kết nối

WebSocket connection tồn tại lâu nên cần quản lý trạng thái mạng:

- TCP có thể bị ngắt mà ứng dụng không nhận thông báo ngay lập tức.
- Reverse proxy có thể đóng kết nối idle sau một khoảng thời gian.
- Server hoặc browser có thể sleep, chuyển mạng hoặc mất kết nối.
- Client có thể đóng tab mà không gửi message nghiệp vụ cuối cùng.

Các cơ chế thường dùng:

- **WebSocket Ping/Pong:** control frame ở tầng protocol để kiểm tra peer và giữ kết nối hoạt động.
- **STOMP heartbeat:** client và server thỏa thuận chu kỳ gửi heartbeat khi không có message.
- **SockJS heartbeat:** giúp HTTP fallback không bị proxy coi là idle.
- **Application heartbeat:** message nghiệp vụ nếu ứng dụng cần đo trạng thái hoặc đồng bộ tiến độ.

Đặt timeout phù hợp ở cả WebSocket container, reverse proxy, load balancer và client. Một timeout ở proxy ngắn hơn heartbeat có thể khiến kết nối bị đóng dù ứng dụng vẫn hoạt động.

Khi đóng kết nối, hai phía thực hiện closing handshake. Một số mã trạng thái phổ biến:

| Mã | Ý nghĩa |
|---|---|
| `1000` | Đóng bình thường |
| `1001` | Endpoint đang rời đi, ví dụ server shutdown |
| `1002` | Lỗi protocol |
| `1003` | Không hỗ trợ loại dữ liệu nhận được |
| `1008` | Vi phạm policy |
| `1009` | Message quá lớn |
| `1011` | Lỗi nội bộ server |

Không gửi các mã dành riêng cho trạng thái nội bộ như `1005` hoặc `1006` trong Close frame. Chúng được dùng để biểu diễn tình trạng không có close status hoặc đóng bất thường.

## 14. Giới hạn message, buffer và client chậm

Một client chậm có thể nhận dữ liệu chậm hơn tốc độ server tạo message. Nếu server cứ thêm message vào queue không giới hạn, bộ nhớ sẽ tăng cho tới khi gây ảnh hưởng toàn hệ thống.

Cần cấu hình:

- Kích thước tối đa của text và binary message.
- Input buffer và idle timeout của WebSocket container.
- Send timeout và giới hạn byte được buffer.
- Số lượng kết nối đồng thời và giới hạn tốc độ message.
- Bounded queue cho tác vụ gửi bất đồng bộ.
- Chính sách đóng session hoặc bỏ message khi client không theo kịp.

Với raw Spring handler, `ConcurrentWebSocketSessionDecorator` hỗ trợ đồng bộ send và giới hạn thời gian/buffer. Với STOMP, cấu hình `WebSocketTransportRegistration` có thể đặt `setMessageSizeLimit`, `setSendTimeLimit` và `setSendBufferSizeLimit`.

Không giữ toàn bộ lịch sử event trong bộ nhớ session. Nếu client cần dữ liệu cũ sau reconnect, lưu state/event ở database hoặc broker và cung cấp cơ chế đồng bộ lại bằng API riêng.

## 15. Scale nhiều instance và reverse proxy

WebSocket là kết nối TCP lâu dài nên mỗi client đang kết nối thường gắn với một application instance trong suốt vòng đời socket. Khi chạy nhiều instance:

- Load balancer phải hỗ trợ WebSocket Upgrade và giữ kết nối lâu.
- Proxy cần chuyển tiếp header `Upgrade` và `Connection`.
- Timeout idle của proxy phải tương thích với heartbeat.
- Sticky session có thể cần thiết cho state cục bộ hoặc SockJS HTTP transports.
- Broadcast giữa các instance cần broker hoặc pub/sub dùng chung.
- Khi instance restart, client phải reconnect và khôi phục subscription/state.

Với raw WebSocket, map session trong một JVM chỉ nhìn thấy session của instance đó. Nếu một instance cần gửi message tới client đang kết nối ở instance khác, phải có routing/broker hoặc một lớp phân phối sự kiện liên instance.

Với STOMP, external broker relay giúp nhiều Spring instance chia sẻ broker destination. Tuy nhiên, cần thiết kế riêng connection quota, routing, failover, authorization và observability.

## 16. Ví dụ Java 17+ kiểm tra TextWebSocketHandler

Ví dụ này kiểm tra logic callback của Spring handler bằng một WebSocketSession giả lập ghi lại message đã gửi. Nó không mở TCP socket hoặc thực hiện HTTP Upgrade; phần đăng ký endpoint và browser client đã được minh họa ở các mục trước.

**Cấu trúc dự án**

~~~text
websocket-handler-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          WebSocketHandlerDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>websocket-handler-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-websocket</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/WebSocketHandlerDemo.java**

~~~java
package demo;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.security.Principal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketExtension;
import org.springframework.web.socket.WebSocketMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

public class WebSocketHandlerDemo {

    public static void main(String[] args) throws Exception {
        RecordingSession session = new RecordingSession();
        EchoHandler handler = new EchoHandler();

        handler.afterConnectionEstablished(session);
        handler.handleMessage(session, new TextMessage("hello"));
        handler.handleMessage(session, new TextMessage("spring"));

        System.out.println("messagesSent=" + session.messages().size());
        System.out.println(
            "firstReply=" + ((TextMessage) session.messages().get(0)).getPayload()
        );
        System.out.println(
            "secondReply=" + ((TextMessage) session.messages().get(1)).getPayload()
        );

        handler.afterConnectionClosed(session, CloseStatus.NORMAL);
    }

    static class EchoHandler extends TextWebSocketHandler {

        @Override
        protected void handleTextMessage(
                WebSocketSession session,
                TextMessage message) throws IOException {

            String payload = message.getPayload().trim();
            if (!payload.isEmpty()) {
                session.sendMessage(new TextMessage("echo:" + payload));
            }
        }
    }

    static class RecordingSession implements WebSocketSession {
        private final List<WebSocketMessage<?>> messages = new ArrayList<>();
        private final Map<String, Object> attributes = new HashMap<>();
        private boolean open = true;
        private int textMessageSizeLimit = 64 * 1024;
        private int binaryMessageSizeLimit = 64 * 1024;

        @Override public String getId() { return "demo-session"; }
        @Override public URI getUri() {
            return URI.create("ws://localhost/echo");
        }
        @Override public HttpHeaders getHandshakeHeaders() {
            return new HttpHeaders();
        }
        @Override public Map<String, Object> getAttributes() {
            return attributes;
        }
        @Override public Principal getPrincipal() { return null; }
        @Override public InetSocketAddress getLocalAddress() { return null; }
        @Override public InetSocketAddress getRemoteAddress() { return null; }
        @Override public String getAcceptedProtocol() { return null; }
        @Override public List<WebSocketExtension> getExtensions() {
            return List.of();
        }

        @Override
        public void sendMessage(WebSocketMessage<?> message) {
            if (!open) {
                throw new IllegalStateException("Session is closed");
            }
            messages.add(message);
        }

        @Override public boolean isOpen() { return open; }
        @Override public void close() { open = false; }
        @Override public void close(CloseStatus status) { open = false; }

        @Override
        public int getTextMessageSizeLimit() {
            return textMessageSizeLimit;
        }

        @Override
        public void setTextMessageSizeLimit(int messageSizeLimit) {
            this.textMessageSizeLimit = messageSizeLimit;
        }

        @Override
        public int getBinaryMessageSizeLimit() {
            return binaryMessageSizeLimit;
        }

        @Override
        public void setBinaryMessageSizeLimit(int messageSizeLimit) {
            this.binaryMessageSizeLimit = messageSizeLimit;
        }

        List<WebSocketMessage<?>> messages() {
            return List.copyOf(messages);
        }
    }
}
~~~

Chạy từ thư mục `websocket-handler-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.WebSocketHandlerDemo
~~~

**Output do chương trình in ra**

~~~text
messagesSent=2
firstReply=echo:hello
secondReply=echo:spring
~~~

Kết quả cho thấy `TextWebSocketHandler` nhận hai TextMessage và gửi lại hai TextMessage. Bài kiểm tra tập trung vào handler callback; cần thêm integration test trên Servlet container và WebSocket client thật để xác nhận handshake, proxy và transport của môi trường triển khai.

## 17. Lỗi thường gặp

1. **Dùng WebSocket cho mọi endpoint:** polling hoặc REST có thể đơn giản hơn nếu cập nhật không cần liên tục.
2. **Quên HTTP Upgrade ở reverse proxy:** client nhận 400/404/502 hoặc handshake thất bại dù handler đã được đăng ký.
3. **Nhầm raw WebSocket với STOMP:** raw handler tự định nghĩa message protocol; STOMP cung cấp command, destination và subscription.
4. **Không kiểm tra readyState:** client gọi send trước khi kết nối mở hoặc sau khi đã đóng.
5. **Gửi đồng thời trên cùng session:** cần serialize send hoặc dùng ConcurrentWebSocketSessionDecorator.
6. **Không xóa session khi đóng:** map giữ reference cũ và gây rò rỉ bộ nhớ.
7. **Chỉ dựa vào Origin để xác thực:** Origin có thể bị client không phải browser giả mạo; vẫn cần authentication.
8. **Cho phép mọi origin:** cấu hình allowlist rõ ràng theo môi trường.
9. **Không giới hạn message size:** payload lớn có thể tiêu thụ bộ nhớ và CPU.
10. **Không xử lý client chậm:** send buffer tăng liên tục nếu không có giới hạn và timeout.
11. **Không có heartbeat/timeout phù hợp:** proxy có thể đóng kết nối idle hoặc server phát hiện disconnect quá muộn.
12. **Giả định simple broker chia sẻ giữa nhiều node:** simple broker nằm trong bộ nhớ instance; dùng broker relay khi cần phân phối liên instance.
13. **Không khôi phục subscription sau reconnect:** STOMP client cần subscribe lại sau khi kết nối được thiết lập lại.
14. **Tin dữ liệu danh tính trong payload:** lấy danh tính từ Principal đã xác thực.
15. **Không phân biệt gửi thành công và xử lý thành công:** nếu cần acknowledgment nghiệp vụ, định nghĩa message/response protocol riêng.

## 18. Checklist trước khi đưa vào production

- Endpoint WebSocket đã được đăng ký trong Spring context xử lý HTTP handshake.
- Client và server thống nhất raw message schema hoặc STOMP subprotocol.
- TLS, authentication, Origin allowlist và authorization đã được cấu hình.
- Message size, send buffer, idle timeout và connection quota có giới hạn.
- Các lần gửi tới cùng session được tuần tự hóa.
- Client chậm có chính sách buffer/drop/close rõ ràng.
- Reconnect có backoff và khôi phục subscription/state.
- Reverse proxy và load balancer chuyển tiếp Upgrade và hỗ trợ kết nối lâu dài.
- Nhiều application instance có broker/pub-sub hoặc routing thích hợp.
- Có metric về số session đang mở, handshake failure, transport error, send timeout, message rate và reconnect.
- Có integration test với đúng servlet container, proxy và broker sẽ dùng trong production.

## 19. Kết luận

WebSocket cung cấp kênh giao tiếp hai chiều, full-duplex trên một kết nối TCP lâu dài. HTTP chỉ tham gia ở bước handshake; sau khi server trả 101 Switching Protocols, hai phía trao đổi text hoặc binary message qua cùng kết nối cho đến khi đóng.

Trong Spring Framework, raw `WebSocketHandler` phù hợp khi ứng dụng muốn tự định nghĩa message protocol. STOMP over WebSocket phù hợp khi cần destination, publish/subscribe, controller và broker. SockJS cung cấp fallback khi WebSocket bị proxy hoặc môi trường mạng chặn.

Một hệ thống WebSocket đáng tin cậy cần quản lý vòng đời session, đồng bộ gửi, xác thực, giới hạn buffer, heartbeat, reconnect và scale-out. Hãy kiểm thử không chỉ handler mà cả handshake, proxy và broker trên môi trường gần với production.

## 20. Tài liệu tham khảo

- [Spring Framework 6.2 — WebSockets](https://docs.spring.io/spring-framework/reference/6.2/web/websocket.html)
- [Spring Framework 6.2 — WebSocket API](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html)
- [Spring Framework 6.2 — Enable STOMP](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/enable.html)
- [Spring Framework 6.2 — SockJS Fallback](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html)
- [Spring Framework 6.2 — STOMP Authentication](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication.html)
- [Spring Framework 6.2 — STOMP WebSocket Transport](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/server-config.html)
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)