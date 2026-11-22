# Đăng ký endpoint và cấu hình handshake

## Mục tiêu

Trong Spring Framework, WebSocket endpoint là URL mà client dùng để bắt đầu kết nối WebSocket. Spring ánh xạ URL đó tới một WebSocketHandler, chạy các bước bắt tay HTTP (handshake), kiểm tra nguồn truy cập, thương lượng sub-protocol nếu có, rồi nâng cấp kết nối thành một phiên WebSocket hai chiều.

Spring hỗ trợ hai kiểu cấu hình thường gặp:

- **Raw WebSocket:** dùng @EnableWebSocket, WebSocketConfigurer, WebSocketHandlerRegistry và WebSocketHandler. Ứng dụng tự định nghĩa cấu trúc message và cách xử lý.
- **STOMP over WebSocket:** dùng @EnableWebSocketMessageBroker, WebSocketMessageBrokerConfigurer và StompEndpointRegistry. STOMP bổ sung command, destination, subscription và message routing.

Bài này tập trung vào đăng ký endpoint và handshake; đồng thời chỉ ra ranh giới giữa raw WebSocket và STOMP để chọn đúng API.

Sau bài này, bạn có thể:

- Đăng ký một hoặc nhiều WebSocket endpoint bằng Java configuration.
- Ánh xạ URL endpoint tới TextWebSocketHandler hoặc BinaryWebSocketHandler.
- Mô tả các bước HTTP Upgrade và phản hồi 101 Switching Protocols.
- Dùng HandshakeInterceptor để kiểm tra request và truyền thuộc tính sang WebSocket session.
- Cấu hình DefaultHandshakeHandler, allowed origins và sub-protocol.
- Phân biệt endpoint URL với STOMP destination.
- Bật SockJS fallback khi cần.
- Xử lý xác thực, quyền truy cập, session lifecycle, concurrency và giới hạn message.
- Xây dựng ứng dụng Spring Boot Java 17+ có endpoint echo chạy được.

## 1. Endpoint WebSocket là gì?

WebSocket tạo một kết nối hai chiều (full-duplex) lâu dài giữa client và server trên một TCP connection. Client và server có thể chủ động gửi message sau khi kết nối được thiết lập; mỗi message không cần tạo một HTTP request mới.

Một WebSocket endpoint là URL dùng cho lần kết nối ban đầu, ví dụ:

~~~text
ws://localhost:8080/ws/echo
wss://api.example.com/ws/echo
~~~

- ws:// là WebSocket không mã hóa ở tầng transport.
- wss:// là WebSocket chạy qua TLS, phù hợp cho production.
- Đường dẫn /ws/echo được Spring ánh xạ tới một handler cụ thể.

WebSocket protocol chỉ định cách đóng khung text/binary frame và điều khiển kết nối. Nó không quy định cấu trúc nội dung nghiệp vụ. Client và server phải thống nhất message format, ví dụ plain text, JSON envelope hoặc một sub-protocol như STOMP.

### Endpoint URL khác message destination

Với raw WebSocket, thường có một URL để kết nối. Sau handshake, các message tiếp tục chạy trên cùng session đó; ứng dụng tự định nghĩa cách phân loại và định tuyến nội dung.

Với STOMP over WebSocket, có hai lớp địa chỉ:

- Endpoint URL, ví dụ /ws: dùng để mở kết nối WebSocket và bắt đầu STOMP session.
- STOMP destination, ví dụ /app/orders, /topic/prices: dùng để định tuyến các STOMP frame sau khi kết nối đã mở.

Không gửi một STOMP destination vào WebSocketHandlerRegistry. Nó không phải URL handshake.

## 2. Raw WebSocket và STOMP dùng hai bộ cấu hình khác nhau

| Mục đích | Raw WebSocket | STOMP over WebSocket |
|---|---|---|
| Bật hạ tầng | @EnableWebSocket | @EnableWebSocketMessageBroker |
| Callback cấu hình | WebSocketConfigurer | WebSocketMessageBrokerConfigurer |
| Registry | WebSocketHandlerRegistry | StompEndpointRegistry |
| Đăng ký | registerWebSocketHandlers(...) | registerStompEndpoints(...) |
| Đối tượng xử lý | WebSocketHandler | STOMP message handler, controller hoặc broker |
| Routing message | Do ứng dụng tự định nghĩa | Dựa trên STOMP command và destination |
| Ví dụ URL | /ws/echo | /ws |
| Ví dụ routing | JSON có trường type | /app/chat, /topic/room-1 |

Nếu chỉ cần trao đổi frame text/binary tùy chỉnh, raw WebSocket đơn giản hơn. Nếu cần publish/subscribe, routing, acknowledgement và request/reply theo giao thức có sẵn, STOMP thường phù hợp hơn.

Không bật hai bộ cấu hình cho cùng một endpoint với kỳ vọng chúng tự động hợp nhất. Chọn một mô hình xử lý rõ ràng cho từng đường dẫn.

## 3. Đăng ký raw endpoint với @EnableWebSocket

Spring cung cấp annotation @EnableWebSocket để bật hạ tầng WebSocket trong Spring MVC application.

Một class cấu hình implement WebSocketConfigurer và override:

~~~java
void registerWebSocketHandlers(WebSocketHandlerRegistry registry);
~~~

Ví dụ tối thiểu:

~~~java
@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoWebSocketHandler echoHandler;

    public WebSocketConfiguration(EchoWebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo");
    }
}
~~~

Các thành phần:

- @Configuration: đăng ký class làm cấu hình Spring.
- @EnableWebSocket: bật WebSocket request handling.
- WebSocketConfigurer: callback để ứng dụng đăng ký handler.
- WebSocketHandlerRegistry: nơi khai báo URL và handler tương ứng.
- addHandler(handler, path): ánh xạ một handler vào một hoặc nhiều path.

Handler nên được khai báo thành Spring bean để có thể inject service, repository hoặc thành phần bảo mật cần thiết. Trong ví dụ trên, Spring inject EchoWebSocketHandler qua constructor.

### Đăng ký nhiều endpoint

Một registry có thể ánh xạ nhiều handler:

~~~java
@Override
public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
    registry.addHandler(chatHandler, "/ws/chat");
    registry.addHandler(notificationHandler, "/ws/notifications");
    registry.addHandler(binaryHandler, "/ws/files");
}
~~~

Mỗi path cần một mục đích và handler rõ ràng. Endpoint là URL handshake; nó không tự tạo queue, topic hay broker destination.

### Handler có thể dùng nhiều path

Một handler có thể được ánh xạ tới nhiều URL:

~~~java
registry.addHandler(echoHandler, "/ws/echo", "/ws/echo-v2");
~~~

Nếu hai mapping xung đột, request có thể không được dispatch như dự định. Hãy dùng path rõ ràng và tránh đăng ký hai handler cho cùng một URL.

## 4. Chọn WebSocketHandler phù hợp

Spring cung cấp interface WebSocketHandler và các base class thuận tiện:

| Kiểu | Dùng khi |
|---|---|
| WebSocketHandler | Cần tự xử lý tất cả loại WebSocket message và lifecycle callback. |
| TextWebSocketHandler | Ứng dụng trao đổi text, JSON hoặc protocol text. |
| BinaryWebSocketHandler | Ứng dụng trao đổi dữ liệu nhị phân. |
| AbstractWebSocketHandler | Muốn kế thừa base class và tự override các callback cần thiết. |

Ví dụ handler text:

~~~java
@Component
public class EchoWebSocketHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {

        session.sendMessage(new TextMessage(
                "echo:" + message.getPayload()
        ));
    }
}
~~~

TextWebSocketHandler gọi handleTextMessage khi nhận text frame. Nếu ứng dụng cần nhận binary frame, hãy dùng BinaryWebSocketHandler hoặc implement WebSocketHandler trực tiếp. Không nên coi mọi message đều là String.

### Các callback trong vòng đời session

Một handler có thể quan tâm tới các callback:

- afterConnectionEstablished(session): handshake thành công và session được mở.
- handleMessage(session, message): nhận message; base class có thể phân luồng sang text/binary callback.
- handleTextMessage(session, message): xử lý text frame.
- handleBinaryMessage(session, message): xử lý binary frame.
- handleTransportError(session, exception): xử lý lỗi transport.
- afterConnectionClosed(session, status): session đã đóng.
- supportsPartialMessages(): khai báo handler có hỗ trợ message fragment hay không.

Handler thường dùng session.getId(), session.getPrincipal(), session.getAttributes() và session.getUri() để truy cập thông tin phiên.

### Handler bean thường là singleton

Một handler được đăng ký làm Spring bean thường được chia sẻ giữa nhiều WebSocket session. Không lưu dữ liệu riêng của một client trong mutable field dùng chung.

Nếu cần lưu trạng thái theo client:

- Dùng WebSocketSession.getAttributes() cho dữ liệu gắn với session.
- Dùng một registry thread-safe được khóa theo session ID và xóa entry khi afterConnectionClosed được gọi.
- Dùng PerConnectionWebSocketHandler nếu cần một handler instance cho từng connection.

Không giữ một collection session vô thời hạn. Khi client disconnect, phải giải phóng state và subscription liên quan.

## 5. HTTP WebSocket handshake diễn ra như thế nào?

Một WebSocket connection bắt đầu bằng HTTP request. Client yêu cầu server nâng cấp giao thức từ HTTP sang WebSocket bằng các header Upgrade.

Request minh họa:

~~~http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: http://localhost:3000
~~~

Các header quan trọng:

| Header | Vai trò |
|---|---|
| Upgrade: websocket | Yêu cầu chuyển giao thức sang WebSocket. |
| Connection: Upgrade | Cho biết request đang yêu cầu nâng cấp connection. |
| Sec-WebSocket-Key | Nonce do client tạo để server xác nhận handshake. |
| Sec-WebSocket-Version | Phiên bản WebSocket protocol mà client yêu cầu. |
| Origin | Nguồn của trang browser khởi tạo kết nối; dùng cho origin validation. |
| Sec-WebSocket-Protocol | Danh sách sub-protocol client muốn thương lượng, nếu có. |

Nếu handshake hợp lệ, server trả về status 101 Switching Protocols cùng các header như Upgrade, Connection và Sec-WebSocket-Accept. Nếu có sub-protocol được chọn, server cũng trả về Sec-WebSocket-Protocol.

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
~~~

Sau phản hồi 101, kết nối TCP vẫn mở và được dùng để gửi/nhận WebSocket frame. Các message sau đó không phải những HTTP request độc lập.

### Chuỗi xử lý ở Spring

~~~mermaid
sequenceDiagram
    participant C as WebSocket Client
    participant M as Spring Handler Mapping
    participant I as HandshakeInterceptor
    participant H as HandshakeHandler
    participant W as WebSocketHandler

    C->>M: HTTP GET /ws/echo + Upgrade
    M->>I: beforeHandshake()
    I-->>M: true / false
    M->>H: doHandshake()
    H->>H: Validate headers, Origin, protocol
    H-->>C: 101 Switching Protocols
    H->>W: Create WebSocket session
    I->>I: afterHandshake()
    C->>W: WebSocket frames
    W-->>C: WebSocket frames
~~~

Ở mức triển khai, Spring map URL handshake tới handler, chạy interceptor trước handshake, dùng handshake handler để kiểm tra/thương lượng và nhờ server-specific upgrade strategy thực hiện protocol upgrade. Khi kết nối thành công, Spring tạo WebSocketSession cho handler.

## 6. HandshakeInterceptor

HandshakeInterceptor cho phép chạy logic trước và sau khi handshake.

Interface nằm trong package:

~~~java
org.springframework.web.socket.server.HandshakeInterceptor
~~~

Có hai phương thức:

~~~java
boolean beforeHandshake(
        ServerHttpRequest request,
        ServerHttpResponse response,
        WebSocketHandler wsHandler,
        Map<String, Object> attributes
) throws Exception;

void afterHandshake(
        ServerHttpRequest request,
        ServerHttpResponse response,
        WebSocketHandler wsHandler,
        Exception exception
);
~~~

### beforeHandshake

Được gọi trước khi Spring thực hiện protocol upgrade. Có thể:

- Kiểm tra header hoặc thông tin request.
- Kiểm tra Principal đã được xác thực.
- Từ chối handshake bằng cách trả về false.
- Đưa dữ liệu cần thiết vào attributes để handler dùng sau khi session được tạo.

Ví dụ interceptor gắn username từ Principal:

~~~java
public class UserHandshakeInterceptor implements HandshakeInterceptor {

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler handler,
            Map<String, Object> attributes) {

        Principal principal = request.getPrincipal();

        if (principal != null) {
            attributes.put("username", principal.getName());
        }

        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler handler,
            Exception exception) {
        // Ghi nhận kết quả handshake nếu cần.
    }
}
~~~

Nếu muốn bắt buộc người dùng đã đăng nhập, interceptor có thể trả về false khi không có Principal. Tuy nhiên, nên thực hiện xác thực HTTP bằng Spring Security filter chain trước khi handshake và dùng interceptor cho các kiểm tra bổ sung.

Các thuộc tính được thêm vào map sẽ được copy vào WebSocketSession.getAttributes(). Handler có thể đọc:

~~~java
Object username = session.getAttributes().get("username");
~~~

Không đưa password, access token hoặc secret dài hạn vào session attributes chỉ để tiện truy cập. Chỉ truyền thông tin cần thiết cho vòng đời kết nối.

### afterHandshake

Được gọi sau khi handshake hoàn tất hoặc thất bại. Tham số exception cho biết lỗi handshake nếu có; response chứa status/header phản ánh kết quả.

Phương thức này thường dùng để log, metrics hoặc cleanup dữ liệu tạm tạo trong quá trình handshake. Nó không phải callback xử lý WebSocket message.

### Đăng ký interceptor

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .addInterceptors(new UserHandshakeInterceptor());
~~~

Có thể đăng ký nhiều interceptor. Nếu một interceptor trả false, chuỗi handshake bị dừng và handler không được mở session.

### HttpSessionHandshakeInterceptor

Spring có sẵn HttpSessionHandshakeInterceptor. Nó chuyển các HTTP session attributes được cấu hình sang WebSocket session attributes.

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .addInterceptors(new HttpSessionHandshakeInterceptor());
~~~

Cách này hữu ích khi ứng dụng dùng cookie-based HTTP session và cần một số dữ liệu session trong handler. Hãy chỉ sao chép dữ liệu cần thiết; đừng coi việc copy attribute là cơ chế cấp quyền truy cập cho mọi message.

## 7. HandshakeHandler và DefaultHandshakeHandler

HandshakeHandler là contract chịu trách nhiệm thực hiện handshake. Implementation mặc định là DefaultHandshakeHandler.

Nó xử lý các bước như:

- Kiểm tra các header bắt buộc của WebSocket handshake.
- Xác nhận Origin theo cấu hình.
- Thương lượng sub-protocol và WebSocket extension.
- Xác định user cho WebSocket session.
- Ủy quyền thao tác upgrade cho một RequestUpgradeStrategy phù hợp với server runtime.

Trong hầu hết ứng dụng, default handshake handler đã đủ. Chỉ cấu hình custom handler khi cần thay đổi logic negotiation, xác định Principal đặc biệt hoặc tùy chỉnh server-specific upgrade strategy.

Có thể gắn handler riêng:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setHandshakeHandler(new DefaultHandshakeHandler());
~~~

Đoạn trên dùng implementation mặc định tường minh. Nếu không gọi setHandshakeHandler, Spring cũng dùng default handshake handler.

### Sub-protocol negotiation

WebSocket frame chỉ chứa text hoặc binary. Một sub-protocol xác định ý nghĩa và định dạng của các frame. STOMP là một ví dụ.

Client có thể gửi:

~~~http
Sec-WebSocket-Protocol: v12.stomp
~~~

Server chỉ nên chọn một protocol mà cả hai phía hỗ trợ. DefaultHandshakeHandler có thể thương lượng protocol dựa trên protocol mà handler hỗ trợ hoặc danh sách protocol được cấu hình.

Ví dụ minh họa:

~~~java
DefaultHandshakeHandler handshakeHandler = new DefaultHandshakeHandler();
handshakeHandler.setSupportedProtocols("v12.stomp");

registry.addHandler(stompAwareHandler, "/ws")
        .setHandshakeHandler(handshakeHandler);
~~~

Với Spring STOMP support, framework đã cung cấp handler hỗ trợ STOMP; thường không cần tự tạo DefaultHandshakeHandler chỉ để bật STOMP.

### RequestUpgradeStrategy

Sau khi handshake được chấp nhận, Spring cần nâng cấp HTTP connection bằng API của server runtime. RequestUpgradeStrategy trừu tượng hóa phần phụ thuộc vào container.

Nếu chạy trên một server engine hoặc version đặc biệt, có thể truyền strategy phù hợp vào DefaultHandshakeHandler. Với Tomcat/Jetty/Jakarta WebSocket runtime thông thường, hãy ưu tiên cấu hình mặc định và chỉ thay strategy khi có yêu cầu deployment cụ thể.

## 8. Allowed origins và bảo vệ handshake

Spring WebSocket mặc định chỉ chấp nhận request cùng origin. Nếu frontend nằm ở origin khác, phải khai báo rõ origin được phép.

Ví dụ:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setAllowedOrigins("https://app.example.com");
~~~

Có thể dùng nhiều origin:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setAllowedOrigins(
                "https://app.example.com",
                "https://admin.example.com"
        );
~~~

Hoặc dùng pattern:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setAllowedOriginPatterns("https://*.example.com");
~~~

Lưu ý:

- Origin gồm scheme, host và port khi có.
- Chỉ thêm origin thực sự được phép kết nối.
- Không bật wildcard cho production nếu không có lý do rõ ràng.
- Origin check chủ yếu bảo vệ browser client. Non-browser client có thể tự đặt header Origin, vì vậy Origin không phải cơ chế authentication.
- Cấu hình origin cho WebSocket/SockJS không thay thế xác thực và phân quyền ở tầng ứng dụng.

### Authentication và authorization

Handshake là một HTTP request, vì vậy có thể dùng cơ chế xác thực HTTP hiện có. Nếu user đã được Spring Security xác thực, Principal có thể được liên kết với WebSocket session.

Các nguyên tắc:

1. Bảo vệ đường dẫn handshake bằng Spring Security.
2. Dùng cookie/HTTP session hoặc cơ chế xác thực phù hợp với client.
3. Kiểm tra quyền cho từng thao tác/message quan trọng sau khi kết nối mở.
4. Không coi Origin là danh tính người dùng.
5. Dùng wss:// khi triển khai qua mạng không tin cậy.
6. Khi user logout hoặc bị thu hồi quyền, đóng các session liên quan theo policy ứng dụng.

WebSocket connection có thể tồn tại lâu sau HTTP handshake. Do đó, quyền có thể thay đổi trong khi session đang mở; ứng dụng cần chính sách cập nhật/đóng session phù hợp.

## 9. SockJS fallback

Không phải môi trường client hoặc proxy nào cũng hỗ trợ native WebSocket tốt. Spring hỗ trợ SockJS để cung cấp fallback transport qua HTTP khi WebSocket không khả dụng.

Đăng ký endpoint:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .withSockJS();
~~~

Client phải dùng SockJS client tương ứng. Không dùng native JavaScript new WebSocket(...) để kết nối vào endpoint đã bật SockJS như thể đó là endpoint WebSocket thuần.

SockJS có thể chọn transport phù hợp với browser/server, ví dụ WebSocket, HTTP streaming hoặc long polling. Vì vậy, endpoint SockJS có thêm các URL transport nội bộ dưới path đã đăng ký.

### Khi nào nên bật SockJS?

- Ứng dụng cần hỗ trợ môi trường cũ hoặc proxy chặn WebSocket.
- Client library đã tích hợp SockJS.
- Có yêu cầu fallback HTTP transport.

Nếu hệ thống chỉ hỗ trợ browser hiện đại và hạ tầng cho phép WebSocket, native WebSocket thường đơn giản hơn.

Khi giới hạn allowed origins, một số fallback transport không thể kiểm tra Origin như iframe-based transport sẽ bị vô hiệu hóa. Cần kiểm thử transport thực tế nếu bật SockJS.

## 10. Đăng ký STOMP endpoint

Nếu ứng dụng dùng STOMP, cấu hình endpoint qua StompEndpointRegistry, không qua WebSocketHandlerRegistry.

Ví dụ:

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
    public void configureMessageBroker(MessageBrokerRegistry config) {
        config.setApplicationDestinationPrefixes("/app");
        config.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Trong cấu hình trên:

- /ws là endpoint URL cho handshake.
- /app là prefix của message client gửi tới application handler.
- /topic và /queue là prefix destination do simple broker xử lý.
- STOMP client thương lượng sub-protocol v12.stomp hoặc phiên bản STOMP được hỗ trợ.

Client mở WebSocket tới ws://host/ws, sau đó gửi STOMP frame như CONNECT, SUBSCRIBE và SEND. Các destination trong frame không phải endpoint URL.

### SockJS với STOMP

Có thể bật SockJS trên STOMP endpoint:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.com")
        .withSockJS();
~~~

Khi đó client phải dùng STOMP client kết hợp SockJS client. Handshake và fallback được quản lý bởi STOMP WebSocket infrastructure.

### Handshake interceptor cho STOMP

STOMP endpoint registration cũng hỗ trợ handshake interceptor và handshake handler. Điều này cho phép tái sử dụng logic Origin, HTTP session, Principal và thuộc tính handshake đã mô tả ở trên.

Tuy nhiên, interceptor chỉ chạy trong handshake HTTP. Nếu cần kiểm tra STOMP CONNECT, SUBSCRIBE hoặc SEND frame, dùng cơ chế inbound channel interceptor của STOMP messaging infrastructure.

## 11. Cấu hình giới hạn message và server container

WebSocket connection có thể giữ nhiều dữ liệu trong bộ nhớ. Cần cấu hình giới hạn message size và idle timeout phù hợp với ứng dụng.

Với Jakarta WebSocket server, Spring cung cấp ServletServerContainerFactoryBean:

~~~java
@Bean
ServletServerContainerFactoryBean webSocketContainer() {
    ServletServerContainerFactoryBean container =
            new ServletServerContainerFactoryBean();

    container.setMaxTextMessageBufferSize(16 * 1024);
    container.setMaxBinaryMessageBufferSize(16 * 1024);

    return container;
}
~~~

Các giới hạn trên là ví dụ 16 KiB cho text/binary buffer; chọn giá trị theo payload thực tế. Container runtime có thể có thêm giới hạn riêng.

Đối với Jetty hoặc server engine khác, có thể cấu hình request upgrade strategy phù hợp để đặt buffer size, idle timeout và các thông số runtime.

Với STOMP, còn có transport-level properties riêng như message size limit và thời gian chờ message đầu tiên. Không nhầm giới hạn của WebSocket server container với giới hạn của STOMP message transport.

## 12. Gửi message an toàn khi có nhiều thread

WebSocket session chuẩn không cho phép nhiều thread gửi message đồng thời trên cùng session. Nếu handler gửi trực tiếp từ nhiều thread, cần serialize các thao tác send.

Spring cung cấp ConcurrentWebSocketSessionDecorator để bọc session và giới hạn việc gửi đồng thời:

~~~java
WebSocketSession safeSession =
        new ConcurrentWebSocketSessionDecorator(
                session,
                10_000,
                512 * 1024
        );
~~~

Các tham số là send-time limit và send-buffer-size limit. Hãy chọn theo latency và kích thước message dự kiến.

Decorator không thay thế thiết kế backpressure. Nếu client đọc chậm, buffer có thể đầy; ứng dụng cần policy rõ ràng như giới hạn queue, loại bỏ message cũ hoặc đóng session.

Đừng broadcast đồng thời tới nhiều session bằng cách gọi sendMessage không đồng bộ trên cùng một session mà không có cơ chế đồng bộ phù hợp.

## 13. Reverse proxy và deployment

Nếu ứng dụng chạy sau nginx, load balancer hoặc API gateway, proxy phải chuyển tiếp WebSocket Upgrade request.

Cần kiểm tra:

- Proxy chuyển tiếp header Upgrade và Connection.
- Idle timeout của proxy lớn hơn thời gian kết nối dự kiến hoặc có heartbeat.
- TLS termination và scheme wss:// được cấu hình đúng.
- Sticky session nếu ứng dụng giữ WebSocket session trong bộ nhớ và chạy nhiều instance mà không có routing layer phù hợp.
- Health check không coi một WebSocket session đang mở là HTTP request thông thường.
- Khi deploy/restart, client có cơ chế reconnect và resubscribe.

WebSocket connection là kết nối lâu dài. Scale ngang cần tính đến số session mỗi instance, bộ nhớ session, broadcast giữa instance và việc reconnect sau khi node bị thay thế.

## 14. Ví dụ Java 17+ chạy được: đăng ký endpoint echo

Ví dụ dùng Spring Boot 4.1.2, Spring MVC WebSocket và embedded Tomcat. Một endpoint /ws/echo nhận text message rồi trả về nội dung có prefix echo:.

### Cấu trúc project

~~~text
spring-websocket-handshake-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          WebSocketDemoApplication.java
          EchoWebSocketHandler.java
          WebSocketConfiguration.java
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
    <artifactId>spring-websocket-handshake-demo</artifactId>
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

### WebSocketDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketDemoApplication.class, args);
    }
}
~~~

### EchoWebSocketHandler.java

~~~java
package demo;

import java.io.IOException;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class EchoWebSocketHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {

        String payload = message.getPayload();
        session.sendMessage(new TextMessage("echo:" + payload));
    }
}
~~~

### WebSocketConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.server.support.HttpSessionHandshakeInterceptor;
import org.springframework.web.socket.server.support.DefaultHandshakeHandler;

@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoWebSocketHandler echoHandler;

    public WebSocketConfiguration(EchoWebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo")
                .addInterceptors(new HttpSessionHandshakeInterceptor())
                .setAllowedOrigins(
                        "http://localhost:3000",
                        "http://127.0.0.1:3000"
                )
                .setHandshakeHandler(new DefaultHandshakeHandler());
    }
}
~~~

Chạy từ thư mục project bằng Java 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Server khởi động tại:

~~~text
http://localhost:8080
~~~

Mở một trang frontend tại http://localhost:3000, sau đó chạy JavaScript sau trong browser console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.addEventListener("open", () => {
    socket.send("hello");
});

socket.addEventListener("message", event => {
    console.log(event.data);
});
~~~

Kết quả trong browser console:

~~~text
echo:hello
~~~

Đoạn JavaScript này cần chạy từ trang có origin nằm trong allowlist, ví dụ http://localhost:3000. Nếu chạy từ origin khác, Spring từ chối handshake theo cấu hình hiện tại.

### Luồng chạy của ví dụ

1. Spring Boot khởi động embedded Tomcat và Spring application context.
2. @EnableWebSocket bật WebSocket infrastructure.
3. WebSocketConfigurer đăng ký EchoWebSocketHandler tại /ws/echo.
4. Client gửi HTTP Upgrade request tới URL đó.
5. HttpSessionHandshakeInterceptor chuyển các HTTP session attributes phù hợp sang WebSocket session.
6. Origin được kiểm tra với allowlist.
7. DefaultHandshakeHandler xử lý handshake và server nâng cấp connection.
8. Client gửi text frame hello.
9. TextWebSocketHandler.handleTextMessage nhận payload và gửi lại echo:hello.
10. Khi client đóng socket, WebSocket session được đóng và callback lifecycle tương ứng được gọi.

Ví dụ này dùng raw WebSocket, không dùng STOMP. Message là text thuần và ứng dụng tự định nghĩa prefix response.

## 15. Kiểm thử handshake và endpoint

Khi kiểm thử, hãy tách handshake khỏi message handling:

### Handshake

- Đúng URL path.
- Request có header Upgrade/Connection hợp lệ.
- WebSocket version được server hỗ trợ.
- Origin nằm trong allowlist.
- User đã được xác thực nếu endpoint yêu cầu đăng nhập.
- Sub-protocol được thương lượng đúng nếu có.
- Proxy chuyển tiếp Upgrade request.

### Message handling

- Text frame tới đúng TextWebSocketHandler.
- Binary frame được xử lý hoặc từ chối đúng cách.
- Payload lớn hơn giới hạn bị xử lý theo policy.
- Transport error và close callback giải phóng session state.
- Nhiều client kết nối đồng thời không làm rò rỉ state.
- Gửi đồng thời được serialize theo yêu cầu của WebSocket session.

### Kiểm thử STOMP

Nếu endpoint dùng STOMP, kiểm tra thêm:

- Client gửi CONNECT với sub-protocol phù hợp.
- SUBSCRIBE đúng destination.
- SEND tới application prefix được route tới controller.
- Broker prefix được xử lý bởi simple broker hoặc external broker relay.
- Authentication/authorization được áp dụng cho STOMP frame, không chỉ handshake.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| HTTP 404 khi mở WebSocket | URL không được đăng ký hoặc sai context path | Kiểm tra addHandler và URL client |
| HTTP 400 hoặc handshake thất bại | Thiếu Upgrade header, sai version hoặc server không hỗ trợ upgrade | Kiểm tra request, servlet container và proxy |
| Origin bị từ chối | Frontend origin không nằm trong allowlist | Thêm đúng scheme/host/port cần thiết |
| Browser kết nối được cùng origin nhưng fail cross-origin | Mặc định chỉ cho same-origin | Cấu hình setAllowedOrigins hoặc pattern cụ thể |
| Handshake thành công nhưng message không được xử lý | Handler sai loại message hoặc protocol không khớp | Kiểm tra Text/Binary handler và sub-protocol |
| Client mong STOMP nhưng server dùng raw WebSocket | Dùng nhầm @EnableWebSocket thay cho message broker config | Chuyển sang @EnableWebSocketMessageBroker và đăng ký STOMP endpoint |
| SockJS client không kết nối được endpoint raw | Client/server không thống nhất SockJS fallback | Dùng native WebSocket hoặc bật withSockJS cùng SockJS client |
| Nhiều thread gửi cùng session gây lỗi | WebSocket session không hỗ trợ concurrent send | Dùng ConcurrentWebSocketSessionDecorator hoặc serialize send |
| Session state tăng liên tục | Không xóa state khi disconnect | Cleanup trong afterConnectionClosed |
| Kết nối bị proxy đóng sau một khoảng thời gian | Idle timeout hoặc proxy không hỗ trợ WebSocket Upgrade | Cấu hình proxy timeout, heartbeat và reconnect |
| Origin allowlist nhưng client lạ vẫn thử kết nối | Origin không phải authentication | Bảo vệ handshake bằng Spring Security và kiểm tra quyền |
| Payload lớn bị đóng kết nối | Buffer/message limit quá nhỏ | Điều chỉnh giới hạn và giới hạn payload ở tầng ứng dụng |

## 17. Checklist triển khai

- [ ] Chọn raw WebSocket hay STOMP trước khi cấu hình endpoint.
- [ ] Với raw WebSocket, dùng @EnableWebSocket và WebSocketConfigurer.
- [ ] Đăng ký từng path bằng WebSocketHandlerRegistry.addHandler.
- [ ] Chọn TextWebSocketHandler hoặc BinaryWebSocketHandler đúng loại payload.
- [ ] Dùng HandshakeInterceptor cho kiểm tra/thu thập dữ liệu ở thời điểm handshake.
- [ ] Dùng DefaultHandshakeHandler trừ khi có yêu cầu custom negotiation/upgrade.
- [ ] Cấu hình allowed origins cụ thể cho frontend.
- [ ] Xác thực HTTP handshake và phân quyền thao tác sau khi kết nối.
- [ ] Không coi Origin là danh tính hoặc cơ chế xác thực.
- [ ] Dùng wss:// trong môi trường production.
- [ ] Chỉ bật SockJS khi cần fallback và client dùng SockJS.
- [ ] Nếu dùng STOMP, đăng ký bằng StompEndpointRegistry; phân biệt endpoint URL và STOMP destination.
- [ ] Giới hạn message size, idle time và số connection.
- [ ] Đồng bộ hóa việc gửi trên cùng WebSocketSession.
- [ ] Xóa session state khi disconnect.
- [ ] Kiểm tra reverse proxy, reconnect, timeout và scale ngang.

## Ghi nhớ

- @EnableWebSocket + WebSocketConfigurer + WebSocketHandlerRegistry dùng để đăng ký raw WebSocket handler.
- addHandler(handler, path) ánh xạ URL handshake tới một WebSocketHandler.
- Handshake bắt đầu bằng HTTP Upgrade; thành công trả về 101 Switching Protocols.
- HandshakeInterceptor.beforeHandshake có thể từ chối request hoặc đưa attributes vào WebSocket session; afterHandshake được gọi sau kết quả handshake.
- DefaultHandshakeHandler kiểm tra handshake, Origin, sub-protocol và ủy quyền protocol upgrade cho server strategy.
- Spring mặc định chỉ chấp nhận same-origin; cross-origin cần allowlist cụ thể.
- Origin validation không thay thế authentication hoặc authorization.
- withSockJS bật fallback transport; client cũng phải dùng SockJS.
- STOMP dùng @EnableWebSocketMessageBroker, WebSocketMessageBrokerConfigurer và StompEndpointRegistry.
- Endpoint URL dùng để mở kết nối; STOMP destination dùng để route message sau khi kết nối đã mở.
- WebSocket session cần cleanup, giới hạn payload và đồng bộ send khi có nhiều thread.

## Tài liệu chính thức

- [Spring Framework 7.0.10 Reference: WebSocket API](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/server.html)
- [Spring Framework 7.0.10 Reference: WebSocket Overview](https://docs.spring.io/spring-framework/reference/7.0/web/websocket.html)
- [Spring Framework 7.0.10 Reference: STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp.html)
- [Spring Framework 7.0.10 Reference: Enable STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/enable.html)
- [Spring Framework Javadoc: WebSocketConfigurer](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketConfigurer.html)
- [Spring Framework Javadoc: WebSocketHandlerRegistry](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketHandlerRegistry.html)
- [Spring Framework Javadoc: HandshakeInterceptor](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/server/HandshakeInterceptor.html)
- [Spring Framework Javadoc: DefaultHandshakeHandler](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/server/support/DefaultHandshakeHandler.html)
- [Spring Boot 4.1.2 Reference: WebSockets](https://docs.spring.io/spring-boot/reference/messaging/websockets.html)
- [Jakarta WebSocket Specification](https://jakarta.ee/specifications/websocket/2.2/)
