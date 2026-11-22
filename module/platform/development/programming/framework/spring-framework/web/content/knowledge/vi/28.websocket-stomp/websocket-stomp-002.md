# WebSocket handshake, subprotocol và vòng đời kết nối trong Spring Framework

## 1. Mục tiêu bài học và phạm vi

WebSocket tạo một kênh giao tiếp **hai chiều (full-duplex), duy trì lâu dài** giữa client và server. Khác với một HTTP request thông thường kết thúc sau khi trả response, kết nối WebSocket bắt đầu bằng **HTTP handshake**, sau đó chuyển sang trao đổi **WebSocket frames** qua cùng kết nối. Nếu hai phía dùng giao thức ứng dụng như **STOMP**, họ còn thương lượng **subprotocol** trong handshake và trao đổi STOMP frames trên WebSocket.

Sau bài này, bạn có thể:

- Diễn giải từng bước HTTP/1.1 Upgrade handshake và ý nghĩa các header `Upgrade`, `Connection`, `Sec-WebSocket-Key`, `Sec-WebSocket-Accept`, `Sec-WebSocket-Version`, `Origin`, `Sec-WebSocket-Protocol`.
- Phân biệt **handshake HTTP**, **WebSocket connection**, **WebSocket subprotocol**, **STOMP CONNECT**, **STOMP subscription** và **SockJS fallback**.
- Cấu hình endpoint bằng `@EnableWebSocket` / `WebSocketConfigurer` hoặc `@EnableWebSocketMessageBroker` / `WebSocketMessageBrokerConfigurer`, kiểm tra handshake bằng `HandshakeInterceptor` và đàm phán subprotocol thông qua `SubProtocolCapable`/`HandshakeHandler`.
- Theo dõi vòng đời `CONNECTING → OPEN → CLOSING → CLOSED`, callback của Spring, trạng thái close, lỗi vận chuyển, heartbeat và cleanup tài nguyên.
- Chạy ví dụ Java 17+ dùng Spring Boot, server raw WebSocket và Java JDK WebSocket client; đối chiếu handshake, subprotocol được chọn, nhận/gửi message và close.

**Phiên bản tham chiếu:** Java 17+, Spring Framework 6.1/Spring Boot 3.3. Cú pháp ví dụ áp dụng cho **Servlet stack (Spring MVC)** với `spring-websocket`. Spring WebFlux có API reactive khác, nêu riêng ở mục 10. WebSocket tuân theo RFC 6455; nâng cấp HTTP/1.1 là đường phổ biến được minh họa ở đây. HTTP/2 có cơ chế extended CONNECT theo RFC 8441, không dùng chính xác chuỗi header HTTP/1.1 ở các ví dụ bên dưới.

## 2. Tại sao cần handshake trước khi gửi dữ liệu?

Một WebSocket client chưa thể gửi text message tùy ý tới URL `ws://...`. Nó phải thiết lập kết nối mạng/TLS nếu cần, gửi yêu cầu mở kết nối đúng protocol, được server chấp nhận, rồi mới dùng WebSocket frames.

Ví dụ HTTP/1.1 request mở kết nối (giá trị key minh họa):

```http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Protocol: demo.v1, chat.v2
Origin: http://localhost:3000
```

Nếu chấp nhận, server có thể trả:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
Sec-WebSocket-Protocol: demo.v1
```

Đây là **ví dụ handshake với key mẫu trong RFC 6455**; những key thật phải được tạo ngẫu nhiên cho từng lần bắt tay. Không sao chép nguyên key mẫu để xây client production. Header `Origin` được browser thêm khi phù hợp; Java native client và các client không phải browser có thể không gửi.

Luồng tổng quát:

```text
Browser/JDK/JS client                 Spring + HTTP server
       |                                        |
       |  TCP connect / TLS nếu dùng wss       |
       |--------------------------------------->|
       |  GET /ws/echo + Upgrade: websocket    |
       |  Sec-WebSocket-Key + protocol offers  |
       |--------------------------------------->|
       |                         kiểm tra method,
       |                         version, key, Origin,
       |                         security/interceptor
       |                        chọn subprotocol
       |  101 + Sec-WebSocket-Accept + protocol |
       |<---------------------------------------|
       | ======= WebSocket OPEN ============== |
       |  frame TEXT / BINARY / PING / PONG    |
       |<======================================>|
       |  CLOSE frame (code + reason)          |
       |<-------------------------------------->|
       |  TCP/TLS connection closed            |
       |---------------------------------------X
```

### Ý nghĩa từng header

| Header/status | Ai gửi? | Ý nghĩa thực tế |
| --- | --- | --- |
| `GET ... HTTP/1.1` | Client | Mở handshake trên endpoint HTTP đang hỗ trợ WebSocket. |
| `Upgrade: websocket` | Client và server | Đề nghị/xác nhận chuyển sang WebSocket. |
| `Connection: Upgrade` | Client và server | Cho biết token `Upgrade` là tùy chọn dành cho hop HTTP hiện tại. |
| `Sec-WebSocket-Version: 13` | Client | Phiên bản wire protocol tiêu chuẩn RFC 6455. |
| `Sec-WebSocket-Key` | Client | Nonce ngẫu nhiên được Base64 encode; **không phải password hay token đăng nhập**. |
| `Sec-WebSocket-Accept` | Server | Chứng minh response gắn với request key, tính theo thuật toán RFC 6455. |
| `Origin` | Thường là browser | Giúp server thực thi chính sách nguồn; **không thay thế xác thực**. |
| `Sec-WebSocket-Protocol` | Client đề xuất; server chọn | Chọn **một** subprotocol ứng dụng mà hai bên cùng hỗ trợ. |
| `Sec-WebSocket-Extensions` | Hai phía thương lượng | Extension ở mức wire protocol, ví dụ compression `permessage-deflate`; không phải subprotocol. |
| `101 Switching Protocols` | Server | Handshake Upgrade thành công; về sau là WebSocket frames, không còn HTTP request/response tương ứng từng message. |

Với key ví dụ `dGhlIHNhbXBsZSBub25jZQ==`, server tính:

```text
Sec-WebSocket-Accept =
  Base64(SHA-1(
    Sec-WebSocket-Key
    + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))
```

Kết quả là `s3pPLMBiTxaQ9kYGzzhZRbK+xOo=`. GUID là hằng số của RFC; SHA-1 ở đây dùng **để xác nhận handshake**, không phải mật mã để xác thực danh tính hoặc bảo vệ payload. An toàn truyền tải đến từ `wss://` (TLS), xác thực và authorization của ứng dụng.

### Khi nào handshake thất bại?

Một số nhóm lỗi cần tách biệt:

1. **Trước HTTP:** DNS, TCP connect, TLS certificate/handshake, proxy/firewall. Không có response HTTP 101.
2. **HTTP handshake bị từ chối:** endpoint không tồn tại (404), user chưa xác thực (401/403 theo security), Origin không hợp lệ (403), sai method/header/version, hoặc server/proxy không hỗ trợ Upgrade.
3. **101 được trả nhưng header không hợp lệ:** client chuẩn RFC phải xác minh `Sec-WebSocket-Accept` và subprotocol được chọn. Nếu không hợp lệ, client hủy kết nối.
4. **Handshake đã thành công nhưng WebSocket/ứng dụng lỗi:** đây là lỗi sau khi OPEN; quan sát qua WebSocket close/error, không thể “trả HTTP 500” cho một message như request HTTP thông thường.

Không coi mọi lỗi “WebSocket connection failed” là lỗi message handler; nhiều trường hợp request chưa hề đến `afterConnectionEstablished`.

## 3. Subprotocol: lớp giao ước nằm trên WebSocket

RFC 6455 định nghĩa **frame TEXT/BINARY và control frames**, còn ý nghĩa business của text/binary là việc của ứng dụng. **Subprotocol** là một quy ước cụ thể để mã hóa và hiểu message, chẳng hạn `chat.v1`, `graphql-transport-ws` hoặc các phiên bản của STOMP (`v10.stomp`, `v11.stomp`, `v12.stomp`).

Client có thể gửi:

```http
Sec-WebSocket-Protocol: chat.v2, chat.v1
```

Server chỉ được chọn **một giá trị đã được client đề nghị**, ví dụ:

```http
Sec-WebSocket-Protocol: chat.v1
```

Nếu không có giao thức chung, server **không được trả tên subprotocol chưa được đề nghị**. Server có thể không chọn subprotocol và vẫn cho phép WebSocket nếu ứng dụng chấp nhận chế độ không có subprotocol; nếu nghiệp vụ **bắt buộc** dùng STOMP/chat phiên bản xác định, cần thực thi điều kiện từ chối hoặc đóng kết nối ở lớp thích hợp. Đừng mặc định rằng có danh sách đề nghị nhưng không khớp sẽ luôn bị từ chối tự động.

**Subprotocol ≠ WebSocket URL:** `/ws/chat` là endpoint; `chat.v1` là cú pháp và semantics của messages chạy trên kết nối đó. Cùng endpoint có thể hỗ trợ nhiều phiên bản giao thức nếu handler định nghĩa rõ.

**Subprotocol ≠ HTTP Content-Type:** Sau `101`, payload đi trong frame WebSocket, không phải body HTTP của từng lần GET/POST. Subprotocol chọn định dạng ứng dụng; có thể kết hợp text JSON hay binary protobuf theo thỏa thuận riêng.

**Subprotocol ≠ extension:** `permessage-deflate` điều chỉnh nén frame, không xác định cấu trúc message hay routing.

### STOMP có phải subprotocol không?

Có. Spring hỗ trợ **STOMP over WebSocket**: WebSocket đảm nhận transport; STOMP định nghĩa lệnh `CONNECT`, `CONNECTED`, `SEND`, `SUBSCRIBE`, `MESSAGE`, `DISCONNECT` và headers `destination`, `subscription`, `receipt`, `heart-beat`. Browser chọn STOMP trong `Sec-WebSocket-Protocol` nếu client gửi danh sách phù hợp và server hỗ trợ.

Có **hai bước khác nhau**:

1. **HTTP/WebSocket handshake** hoàn tất: server trả 101; WebSocket OPEN.
2. **STOMP handshake ở tầng ứng dụng**: client gửi frame `CONNECT` hoặc `STOMP`; server/broker trả `CONNECTED` rồi mới xử lý các subscription/message tương ứng.

Ví dụ sau khi WebSocket OPEN:

```text
CONNECT
accept-version:1.2
heart-beat:10000,10000

^@
```

`^@` đại diện byte NUL (0x00) kết thúc STOMP frame, không phải hai ký tự literal caret/at. Server phản hồi frame `CONNECTED` nếu STOMP CONNECT được chấp nhận. **HTTP 101 không có nghĩa STOMP CONNECT đã thành công**, và cũng chưa có bất kỳ `SUBSCRIBE` nào.

Raw WebSocket handler tự chọn subprotocol `demo.v1` là cách đơn giản để học đàm phán. STOMP handler của Spring phức tạp hơn vì còn channel, controller, broker và STOMP frame handling.

## 4. Spring MVC: cấu hình endpoint raw WebSocket và handshake

Trong Servlet stack, dùng `spring-websocket`, `@EnableWebSocket` và `WebSocketConfigurer`. Bạn đăng ký:

- **URL endpoint:** ví dụ `/ws/echo`.
- **`WebSocketHandler`:** callback khi kết nối mở/đóng, nhận message, xảy ra transport error.
- **`HandshakeInterceptor`:** logic trước/sau handshake; có thể từ chối trước 101 hoặc lưu attribute.
- **`HandshakeHandler`:** xử lý kiểm tra protocol/Origin/extensions và nhờ server container upgrade; mặc định Spring dùng `DefaultHandshakeHandler` khi phù hợp.
- **Origin policy:** `setAllowedOrigins(...)`/`setAllowedOriginPatterns(...)`, nhất là browser khác origin.

Mẫu cấu hình tối thiểu:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
class RawWebSocketConfiguration implements WebSocketConfigurer {
    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(new EchoHandler(), "/ws/echo")
                .addInterceptors(new ConnectionMetadataInterceptor())
                .setAllowedOriginPatterns("http://localhost:*");
    }
}
```

Đây là **fragment**; `EchoHandler` và `ConnectionMetadataInterceptor` là các class cần định nghĩa. Ví dụ chạy đầy đủ ở mục 8. Trong production, đưa origin được phép vào cấu hình theo môi trường và kết hợp Spring Security phù hợp; dấu `*` chỉ là glob matching trong ví dụ local dev, không tự cấp quyền đăng nhập.

### HandshakeInterceptor: tác động trước Upgrade

Interface `HandshakeInterceptor` định nghĩa:

```java
boolean beforeHandshake(
    ServerHttpRequest request,
    ServerHttpResponse response,
    WebSocketHandler wsHandler,
    Map<String, Object> attributes);

void afterHandshake(
    ServerHttpRequest request,
    ServerHttpResponse response,
    WebSocketHandler wsHandler,
    Exception exception);
```

Đây là chữ ký API đã đơn giản hóa. `beforeHandshake` có thể đọc method, URI, headers, user principal, HTTP session; nếu không được phép, set HTTP status thích hợp và trả `false`. Các phần tử đặt vào `attributes` được chuyển sang attributes của `WebSocketSession` khi handshake thành công, ví dụ correlation ID hoặc user ID an toàn. Đừng đưa raw password/access token vào `attributes` hoặc log.

**Không nhầm:** `afterHandshake` là callback sau quá trình xử lý handshake; không phải bằng chứng rằng STOMP đã CONNECTED, cũng không thay `afterConnectionEstablished`. Để quan sát session mở thật, dùng lifecycle callback của `WebSocketHandler` hoặc event STOMP thích hợp.

### HandshakeHandler và subprotocol negotiation

`DefaultHandshakeHandler` sẽ kiểm tra yêu cầu WebSocket, origin và subprotocol rồi ủy quyền upgrade tới container. Với raw `WebSocketHandler`, Spring có thể lấy supported subprotocols từ handler nếu handler implements `SubProtocolCapable`:

```java
import java.util.List;
import org.springframework.web.socket.SubProtocolCapable;
import org.springframework.web.socket.handler.TextWebSocketHandler;

class EchoHandler extends TextWebSocketHandler
        implements SubProtocolCapable {

    @Override
    public List<String> getSubProtocols() {
        return List.of("demo.v1");
    }
}
```

Nếu client đề nghị `demo.v1` và server chọn nó, Spring `WebSocketSession.getAcceptedProtocol()` cho biết tên được thương lượng (ở thời điểm session đã mở). Nếu handler chỉ hỗ trợ raw messages mà không cần subprotocol, không bắt buộc phải implement `SubProtocolCapable`; hai bên phải có định dạng message chung qua quy ước ứng dụng khác.

**Khi nào tùy biến `DefaultHandshakeHandler`?** Khi cần luật chọn subprotocol hoặc kiểm soát handshake mà hook mặc định không đáp ứng; lưu ý mọi tùy biến cần tôn trọng RFC và chính sách security. Các kiểm tra business đơn giản nên đặt vào interceptor thay vì viết lại toàn bộ cơ chế upgrade.

## 5. Vòng đời WebSocket: từ kết nối TCP đến cleanup

### 5.1 Các trạng thái

```text
             TCP/TLS kết nối + HTTP handshake
    ┌─────────────────────────────────────────┐
    │                                         ▼
CONNECTING -------------------------------> OPEN
    │       handshake failed                   │
    ▼                                          │ send/receive TEXT/BINARY
  CLOSED                                       │ PING/PONG
                                               ▼
                                            CLOSING
                                         close frame exchange
                                               ▼
                                             CLOSED

Ngoại lệ: mất mạng đột ngột có thể dẫn đến CLOSED/abnormal
mà không có đủ close frames đúng chuẩn.
```

`CONNECTING`, `OPEN`, `CLOSING`, `CLOSED` là cách mô tả trạng thái phổ biến trên WebSocket browser/client API. Spring server thể hiện vòng đời qua callbacks và `WebSocketSession.isOpen()`; không phải cùng một enum public bắt buộc trong mọi API server.

Tại **OPEN**, hai bên có thể gửi frame theo giao thức WebSocket. Có hai loại data frame: TEXT và BINARY; message có thể bị chia thành nhiều frames, và handler có thể hỗ trợ partial messages tùy cấu hình/server. Ping/Pong và Close là **control frames** riêng, không phải text message bình thường.

### 5.2 Callback ở WebSocketHandler của Spring

| Thời điểm | Callback API | Việc phù hợp |
| --- | --- | --- |
| Sau handshake thành công, WebSocket sẵn sàng | `afterConnectionEstablished(WebSocketSession)` | Ghi metric OPEN, khởi tạo state theo session, kiểm tra protocol/attribute |
| Khi nhận message | `handleMessage(...)`; thường override `handleTextMessage(...)` ở `TextWebSocketHandler` | Parse và xử lý payload theo hợp đồng; trả lời có kiểm soát |
| Khi lỗi vận chuyển | `handleTransportError(WebSocketSession, Throwable)` | Log lỗi phù hợp, cleanup, close nếu session còn mở |
| Sau đóng kết nối | `afterConnectionClosed(WebSocketSession, CloseStatus)` | Xóa state/registries, decrement metric, tránh gửi thêm message |
| Khi nhận Pong | `handlePongMessage(...)` (handler hỗ trợ) | Theo dõi heartbeat/round-trip của transport nếu cần |

Ví dụ sự kiện hợp lý:

```text
HTTP handshake accepted
afterConnectionEstablished(session)
handleTextMessage(session, "hello")
sendTextMessage(session, "echo:hello")
close frame exchanged / underlying transport closed
afterConnectionClosed(session, CloseStatus.NORMAL)
```

**Không bảo đảm thứ tự mọi callback trong mọi lỗi mạng.** Ví dụ kết nối rớt bất ngờ có thể gọi `handleTransportError` và `afterConnectionClosed` với thông tin khác nhau; logic giải phóng phải **idempotent** (xóa nhiều lần không làm sai state). Nếu handshake chưa thành công, chưa tạo WebSocketSession hợp lệ để dùng như OPEN; đừng đợi `afterConnectionClosed` mới dọn resource đã tạo ở interceptor trước khi Upgrade.

### 5.3 Close handshake và status code

Đóng chuẩn WebSocket là **gửi control frame CLOSE**, đầu kia thường phản hồi CLOSE (nếu chưa gửi) rồi transport đóng. Ở Spring:

```java
session.close(CloseStatus.NORMAL);     // code 1000
```

Một số mã quan trọng:

| Code | Nghĩa | Khi nào quan sát |
| --- | --- | --- |
| `1000` | Normal closure | Client/user hoàn tất phiên, server chủ động kết thúc bình thường |
| `1001` | Going away | Server tắt, endpoint điều hướng/đóng ứng dụng |
| `1002` | Protocol error | WebSocket framing/handshake protocol vi phạm |
| `1003` | Unsupported data | Gửi loại dữ liệu không được handler hỗ trợ |
| `1006` | Abnormal closure (**không gửi trên wire**) | API quan sát connection chết mà không nhận close frame chuẩn |
| `1008` | Policy violation | Vi phạm chính sách ứng dụng |
| `1009` | Message too big | Message vượt giới hạn |
| `1011` | Internal server error | Lỗi server khi đang xử lý message |
| `1012` / `1013` | Service restart / Try again later | Các ngữ cảnh vận hành tương ứng nếu endpoint hỗ trợ |

**1005 và 1006 là các giá trị dành cho biểu diễn trạng thái, không được đặt vào Close frame trên wire.** Không cố ép gửi `1006` bằng `session.close(...)`; dùng code hợp lệ như 1000/1008/1011, và log nguyên nhân khi kết nối mất bất thường. Reason string không nên chứa thông tin nhạy cảm, phải tuân giới hạn byte UTF-8 của close control frame. Kết nối TCP bị reset không đồng nghĩa bên kia đã nhận close frame của ứng dụng.

### 5.4 Ping/Pong và heartbeat

- **WebSocket Ping/Pong:** control frames mức RFC 6455; giúp phát hiện tính sống của transport theo chính sách runtime. Endpoint nhận Ping phải xử lý Pong theo RFC; browser JavaScript WebSocket API không expose hàm ping/pong thô cho ứng dụng.
- **STOMP heart-beat:** nhịp heartbeat ở tầng STOMP, thương lượng trong `CONNECT`/`CONNECTED` qua header `heart-beat`; **không phải** WebSocket Ping/Pong. Có thể phát hiện client/broker bất hoạt ngay cả khi TCP connection nhìn bề ngoài còn sống.
- **TCP keepalive:** tùy chọn socket/OS ở tầng mạng, không thay thế timeout ứng dụng. Proxy/firewall/load balancer có idle timeout riêng.
- **SockJS heartbeat:** khi dùng fallback, cơ chế keepalive có thể khác với raw WebSocket và chịu tác động của STOMP heartbeat configuration.

Đặt heartbeat hợp lý: quá ngắn gây traffic không cần thiết, quá dài làm lỗi mất mạng được phát hiện muộn. Với mỗi phương thức, cần đo timeout ở proxy, engine, broker và ứng dụng. Đừng tự viết một vòng ping blocking/sleep trên thread I/O.

## 6. STOMP over WebSocket: endpoint và các mốc lifecycle riêng

Để dùng STOMP messaging thay vì tự parse raw text, trong Spring MVC có thể cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws/stomp")
                .setAllowedOriginPatterns("https://app.example.org");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Đây là **đoạn cấu hình minh họa**, độc lập với raw WebSocket demo ở mục 8. `/ws/stomp` là HTTP endpoint mở WebSocket; `/app/...` và `/topic/...` là **STOMP destination prefixes**, không phải URL của HTTP handshake. `/app` thường chuyển `SEND` tới `@MessageMapping` trong controller, còn `/topic`/`/queue` được simple broker xử lý theo cấu hình trên. Với simple broker, hai prefix này chỉ là quy ước routing, không tự đảm bảo message persistence hay semantics của queue doanh nghiệp.

Ví dụ luồng:

```text
Client                             Spring STOMP messaging
  GET /ws/stomp + WebSocket Upgrade   → HTTP 101
  STOMP CONNECT                       → STOMP CONNECTED
  STOMP SUBSCRIBE /topic/updates      → broker lưu subscription
  STOMP SEND /app/notify              → @MessageMapping xử lý
                                      → broker gửi MESSAGE /topic/updates
  STOMP DISCONNECT                    → cleanup STOMP session
  WebSocket CLOSE                     → đóng transport
```

Tại sao cần phân biệt? Một WebSocket có thể **OPEN** nhưng STOMP chưa `CONNECTED` (client chưa gửi frame CONNECT, bị reject hoặc đang đợi broker). Kiểm tra ứng dụng chỉ theo callback WebSocket mà coi người dùng đã “subscribe” là không chính xác.

### Event lifecycle phía STOMP

Spring publish các ApplicationEvent hữu ích:

- `SessionConnectEvent`: server nhận STOMP CONNECT từ client; chưa chắc broker đã xác nhận kết nối.
- `SessionConnectedEvent`: phiên STOMP được báo đã connected sau khi xử lý CONNECT thành công.
- `SessionSubscribeEvent` / `SessionUnsubscribeEvent`: đăng ký/hủy subscription STOMP.
- `SessionDisconnectEvent`: thông báo kết thúc phiên STOMP; có thể xảy ra nhiều lần với cùng session trong một số luồng, do đó cleanup cần idempotent.

Ví dụ listener quan sát:

```java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
class StompSessionEvents {
    @EventListener
    void onConnected(SessionConnectedEvent event) {
        StompHeaderAccessor accessor =
                StompHeaderAccessor.wrap(event.getMessage());
        System.out.println("STOMP CONNECTED: " + accessor.getSessionId());
    }

    @EventListener
    void onDisconnected(SessionDisconnectEvent event) {
        System.out.println("STOMP DISCONNECTED: " + event.getSessionId());
        // Dọn map state theo sessionId bằng thao tác idempotent.
    }
}
```

Đây là **Spring bean fragment**, không phải Java file độc lập. Tùy loại event, native/STOMP headers có thể khác nhau; tránh dựa vào event listener để lấy credential chưa được bảo đảm tồn tại. Khi bật broker relay, các giai đoạn CONNECT có thể còn phụ thuộc kết nối broker bên ngoài. **Simple broker** thích hợp học tập/ứng dụng nhỏ, không có tất cả tính năng của broker đầy đủ (ACK/receipt đầy đủ, clustering, persistence...).

### STOMP authentication so với HTTP handshake authentication

Spring thường liên kết `Principal` của HTTP handshake với session WebSocket/STOMP. Với cookie-based authentication, trình duyệt gửi cookie trên handshake phù hợp chính sách; Spring Security có thể xác thực trước upgrade. STOMP `login`/`passcode` mặc định **không tự thay thế** cơ chế HTTP authentication trong Spring WebSocket; nếu ứng dụng dùng token trong STOMP `CONNECT`, phải thiết kế interceptor trên inbound channel và xác thực/ràng buộc Principal rõ ràng, cùng chính sách authorization cho destination.

Một kết nối đã handshake thành công **không tự có quyền gửi tới mọi `/app/...` hoặc subscribe mọi `/topic/...`**. Authorization phải kiểm tra cả connection và message destinations. Với trình duyệt và cookie, nhớ xét origin policy và CSRF/security trên STOMP CONNECT theo stack đang dùng.

## 7. SockJS: tại sao luồng handshake có thể khác?

`SockJS` cung cấp fallback transport khi môi trường không hỗ trợ WebSocket chuẩn hoặc proxy chặn Upgrade. Có thể bật bằng:

```java
registry.addEndpoint("/ws/stomp")
        .setAllowedOriginPatterns("https://app.example.org")
        .withSockJS();
```

Client SockJS sẽ trao đổi thêm request HTTP (ví dụ `/info` và đường dẫn transport), rồi chọn WebSocket hoặc XHR streaming/polling tùy khả năng. **Không thể lấy một request SockJS fallback và mặc định nó tuân theo handshake `101 Switching Protocols` của raw WebSocket**. STOMP frame có thể chạy trên transport fallback nên STOMP session lifecycle và transport lifecycle cần quan sát riêng.

Không gửi browser native `new WebSocket("ws://host/ws/stomp")` tới SockJS URL biến thể rồi kỳ vọng client ấy tự hiểu các đường dẫn/frames của SockJS. Nếu phía server hỗ trợ WebSocket native trên endpoint STOMP, dùng STOMP library với `brokerURL` thích hợp; nếu muốn SockJS fallback, dùng SockJS client + StompJS cấu hình `webSocketFactory`. Chọn thống nhất với server.

## 8. Ví dụ chạy được: raw WebSocket handshake, subprotocol và close

Ví dụ này cố ý dùng **raw WebSocket** để quan sát handshake và lifecycle rõ ràng. Sau đó có thể mở rộng sang STOMP qua cấu hình riêng ở mục 6. Runtime: Java 17+, Gradle, Spring Boot 3.3.x. JDK có sẵn `java.net.http.WebSocket` nên client không cần npm hay browser.

### 8.1 Tạo dự án

Cấu trúc:

```text
websocket-lifecycle-demo/
├── build.gradle
└── src/main/java/demo/
    ├── WsLifecycleApplication.java
    └── WsClientApp.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}

springBoot {
    mainClass = 'demo.WsLifecycleApplication'
}

tasks.register('runClient', JavaExec) {
    group = 'application'
    description = 'Connect the JDK WebSocket client to the local server'
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'demo.WsClientApp'
}
```

`spring-boot-starter-websocket` kéo các dependency WebSocket cần thiết cùng Servlet server mặc định trong Spring Boot. Plugin Boot quản lý dependency versions, tránh trộn thủ công Spring Framework và Tomcat không tương thích.

### 8.2 Server: WsLifecycleApplication.java

```java
package demo;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.SubProtocolCapable;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

@SpringBootApplication
public class WsLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(WsLifecycleApplication.class, args);
    }
}

@Configuration
@EnableWebSocket
class WebSocketConfiguration implements WebSocketConfigurer {

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(new EchoHandler(), "/ws/echo")
                .addInterceptors(new DemoHandshakeInterceptor())
                .setAllowedOriginPatterns("http://localhost:*");
    }
}

class DemoHandshakeInterceptor implements HandshakeInterceptor {

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler handler,
            Map<String, Object> attributes) {

        // Điều kiện chỉ để demo; không dùng query làm credential.
        if (!"client=cli".equals(request.getURI().getRawQuery())) {
            response.setStatusCode(HttpStatus.FORBIDDEN);
            return false;
        }

        attributes.put("client", "cli");
        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler handler,
            Exception exception) {
        // Có thể ghi metrics/trace không nhạy cảm sau handshake.
    }
}

class EchoHandler extends TextWebSocketHandler implements SubProtocolCapable {

    @Override
    public List<String> getSubProtocols() {
        return List.of("demo.v1");
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        System.out.println("OPEN protocol=" + session.getAcceptedProtocol()
                + " client=" + session.getAttributes().get("client"));
    }

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {
        session.sendMessage(new TextMessage("echo:" + message.getPayload()));
    }

    @Override
    public void handleTransportError(
            WebSocketSession session,
            Throwable exception) throws Exception {
        System.err.println("Transport error: "
                + exception.getClass().getSimpleName());
        if (session.isOpen()) {
            session.close(CloseStatus.SERVER_ERROR);
        }
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session,
            CloseStatus status) {
        System.out.println("CLOSED code=" + status.getCode());
    }
}
```

Điều quan sát được:

- `@EnableWebSocket` mở infrastructure đăng ký handler tại `/ws/echo`.
- `beforeHandshake` kiểm tra query `?client=cli` và đưa một attribute đã kiểm tra vào session. Trả `false` nếu thiếu, response `403` **trước** WebSocket OPEN. Đây chỉ là **bài tập phân biệt lifecycle**, không phải cách xác thực production.
- `EchoHandler.getSubProtocols()` cung cấp `demo.v1` cho negotiation; `session.getAcceptedProtocol()` cho biết protocol đã chọn.
- `afterConnectionEstablished` chạy khi handshake thành công, và `handleTextMessage` gửi phản hồi.
- `afterConnectionClosed` ghi status. `handleTransportError` xử lý lỗi transport bằng cách đóng session nếu vẫn open.

Trong ứng dụng nhiều client, đừng duy trì một biến mutable không đồng bộ ở handler singleton; dùng state theo `session.getId()` trong concurrent map, kiểm soát tài nguyên, xóa idempotent. Gửi đồng thời từ nhiều thread đến một session cần cơ chế đồng bộ hoặc `ConcurrentWebSocketSessionDecorator`, cùng giới hạn thời gian/đệm phù hợp; một WebSocketSession không phải hàng đợi vô hạn.

### 8.3 Client: WsClientApp.java (Java 17)

```java
package demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public class WsClientApp {

    public static void main(String[] args) throws Exception {
        CompletableFuture<String> reply = new CompletableFuture<>();
        StringBuilder partial = new StringBuilder();

        WebSocket.Listener listener = new WebSocket.Listener() {
            @Override
            public void onOpen(WebSocket socket) {
                socket.request(1);
            }

            @Override
            public CompletionStage<?> onText(
                    WebSocket socket, CharSequence data, boolean last) {
                partial.append(data);
                if (last) {
                    reply.complete(partial.toString());
                }
                socket.request(1);
                return CompletableFuture.completedFuture(null);
            }

            @Override
            public void onError(WebSocket socket, Throwable error) {
                reply.completeExceptionally(error);
            }
        };

        HttpClient client = HttpClient.newHttpClient();
        WebSocket socket = client.newWebSocketBuilder()
                .subprotocols("demo.v1")
                .buildAsync(
                        URI.create("ws://localhost:8080/ws/echo?client=cli"),
                        listener)
                .get(5, TimeUnit.SECONDS);

        System.out.println("selected=" + socket.getSubprotocol());

        socket.sendText("hello", true).join();
        System.out.println("received=" + reply.get(5, TimeUnit.SECONDS));

        socket.sendClose(WebSocket.NORMAL_CLOSURE, "done").join();
    }
}
```

Client gửi đề xuất `Sec-WebSocket-Protocol: demo.v1`; kết nối tới endpoint qua WebSocket handshake do `HttpClient` thực hiện. Listener yêu cầu cấp tiếp thông báo với `request(1)` để đáp ứng cơ chế demand của Java WebSocket client, ghép các phần text tới `last=true`, rồi trả result cho main thread. `sendClose(...)` bắt đầu close handshake bình thường.

### 8.4 Cách chạy, kết quả và thí nghiệm

Trong thư mục dự án, terminal thứ nhất chạy server:

```bash
gradle bootRun
```

Khi Spring Boot báo server đã mở port 8080, dùng terminal thứ hai:

```bash
gradle runClient
```

Nếu có Gradle Wrapper: `./gradlew bootRun` và `./gradlew runClient` trên macOS/Linux, hoặc `.\gradlew.bat bootRun` và `.\gradlew.bat runClient` trên PowerShell Windows. **Không mặc định có sẵn `gradlew`** trong dự án tự tạo; tạo Gradle Wrapper hoặc dùng Gradle đã cài. Các lệnh trên được viết cho hai terminal riêng: server phải tiếp tục chạy khi client kết nối.

**Hai dòng do client tự in**, nếu server chạy ở port 8080 và handshake thành công:

```text
selected=demo.v1
received=echo:hello
```

Gradle và HTTP/Tomcat/Spring có thể in thêm log, không phải một phần hai dòng từ `System.out.println` trên. Server cũng sẽ in dòng dạng `OPEN protocol=demo.v1 client=cli` và `CLOSED code=1000` khi phiên kết thúc bình thường; thứ tự log giữa hai terminal không cố định. Nếu server còn giữ port 8080 cho ứng dụng khác, cần cấu hình `server.port` và sửa URL trong client cho khớp.

**Thử nghiệm A – từ chối trước handshake:** đổi URL trong client thành `ws://localhost:8080/ws/echo` (bỏ `?client=cli`). `beforeHandshake` trả 403; `buildAsync(...)` thất bại, không có `afterConnectionEstablished`. Điều này khác với mở kết nối thành công rồi bị close code 1008.

**Thử nghiệm B – subprotocol khác:** đổi `.subprotocols("demo.v1")` thành `.subprotocols("unknown.v1")`. Server ở mẫu chỉ hỗ trợ `demo.v1`, nên không thể chọn `unknown.v1`. Tùy container/client, upgrade có thể diễn ra **không có subprotocol được chọn**, hoặc client từ chối do yêu cầu cụ thể của ứng dụng; hãy kiểm tra `getSubprotocol()` và handshake thực tế. Nếu ứng dụng muốn *bắt buộc* một protocol, thêm luật kiểm tra/thực thi rõ ràng.

**Thử nghiệm C – đóng hợp lệ và bất thường:** chạy client như bình thường để quan sát 1000. Sau đó tắt đột ngột mạng/process trong phiên để thấy transport error/abnormal termination có thể xuất hiện mà không có close frame bình thường. Không kết luận có lỗi business chỉ từ code 1006.

### 8.5 HTTP handshake có thể quan sát bằng cách nào?

Browser DevTools → **Network** → **WS** (hoặc WebSocket) → chọn `/ws/echo`; kiểm tra request/response handshake headers, negotiated protocol và Frames/Messages. Với Chrome/Firefox, giao diện hiển thị khác nhau; quan sát header `Sec-WebSocket-Protocol` và response status 101 khi dùng HTTP/1.1 Upgrade.

Trên JDK client, `WebSocket.getSubprotocol()` phản ánh server lựa chọn (chuỗi rỗng nếu không có subprotocol). Để đo transport-level handshake, bật debug logging cho client/server hoặc dùng packet capture **chỉ trong môi trường kiểm thử có quyền**, tránh ghi cookies/token. Một WebSocket client thông thường không tự expose mọi response header từ handshake sau khi kết nối thành công.

## 9. Xác thực, Origin, proxy, tài nguyên và vận hành

### 9.1 WebSocket không tự bỏ qua Spring Security

- HTTP handshake là request tới endpoint và có thể đi qua security filter chain; cần quyết định user nào được mở `/ws/...`.
- Xác thực qua cookie/session hay bearer token phải phù hợp môi trường. Browser WebSocket API không cho tùy ý đặt mọi HTTP header giống `fetch()`; nhiều ứng dụng dùng cookie, hoặc thiết kế authentication ở STOMP CONNECT qua channel interceptor. Không chuyển token bí mật sang query URL chỉ để “dễ debug”.
- `Origin` khác CORS: WebSocket không dùng preflight CORS thông thường giống `fetch`, nhưng Spring có origin checks riêng. Non-browser client có thể tự gửi Origin giả; **Origin chỉ là defense bổ sung chống cross-site WebSocket hijacking**, không phải chứng thực danh tính.
- Với STOMP, xác thực phiên và authorization từng destination `SEND`/`SUBSCRIBE` cũng cần được kiểm tra, kể cả khi HTTP 101 đã hợp lệ.
- Giới hạn số kết nối theo user/IP, kích thước message, thời gian rảnh, fan-out và tốc độ gửi; không cấp bộ đệm không giới hạn.

### 9.2 Reverse proxy và load balancer

Nếu sử dụng nginx hoặc một reverse proxy khác, cần chuyển tiếp HTTP Upgrade và Connection headers, cho phép timeout dài hơn HTTP request thông thường, đồng thời cấu hình TLS ở `wss://`. Ví dụ nginx cơ bản có thể gồm:

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;
}
```

Đây là fragment triển khai, không phải cấu hình reverse proxy hoàn chỉnh. Cấu hình `Connection` linh hoạt thường dùng map để tránh set Upgrade khi request không có header; trên hệ thống production, cần TLS/security headers/health checks theo hạ tầng. `proxy_read_timeout` và timeout của load balancer phải phù hợp heartbeat và chính sách tài nguyên.

Ứng dụng scale nhiều instance cần chú ý: WebSocket connection **gắn vào một node** trong đời sống kết nối; load balancer không chia một connection đang mở giữa nhiều server. Nếu gửi message đến user trên node khác, cần shared broker/pub-sub, STOMP broker relay hoặc hạ tầng phân phối phù hợp; sticky sessions một mình không tạo message bus phân tán.

### 9.3 Quản lý lifecycle đáng tin cậy

| Sự kiện | Nên làm | Tránh |
| --- | --- | --- |
| Trước handshake | Validate Origin/auth/path/limits; đặt metadata tối thiểu vào attributes | Coi nonce `Sec-WebSocket-Key` là authentication |
| Vừa OPEN | Ghi session ID/Principal, selected subprotocol, thời gian bắt đầu | Mặc định STOMP cũng CONNECTED |
| Nhận TEXT/BINARY | Parse, giới hạn payload, kiểm tra authorization, bắt lỗi phù hợp | Chạy blocking I/O lâu trên thread I/O |
| Gửi message | Kiểm tra session open, buffer/send time limits, backpressure | Nhiều thread send đồng thời không đồng bộ |
| Transport error | Log nguyên nhân an toàn, close khi có thể, cleanup idempotent | Giả sử luôn có close frame và code 1000 |
| Đóng bình thường | Gửi close code hợp lệ, xóa session map, metric decrement một lần | Gửi code reserved `1006` |
| Redeploy/shutdown | Drain/close sessions có kế hoạch, cho client reconnect có jitter | Để mọi client reconnect tức thì và gây thundering herd |

### 9.4 Checklist debug theo giai đoạn

1. **Không có request tới server:** kiểm tra URL `ws://`/`wss://`, DNS, TLS, port, proxy, path.
2. **Có request nhưng không được 101:** kiểm tra response status 400/401/403/404, HTTP Upgrade headers, Origin, security filters, `HandshakeInterceptor`, phiên bản WebSocket.
3. **101 rồi client từ chối:** soát `Sec-WebSocket-Accept`, subprotocol được chọn, extensions và thư viện client.
4. **WebSocket OPEN nhưng không có ứng dụng message:** kiểm tra client subscribe/demand, handler binding, message format TEXT/BINARY, STOMP CONNECTED và destination đúng.
5. **Kết nối tự rớt sau một khoảng idle:** kiểm tra heartbeat, idle timeout proxy/load balancer/container, shutdown và lỗi mạng; không đoán lỗi từ 1006 duy nhất.
6. **Memory/CPU tăng khi nhiều client:** theo dõi active connections, sessions, send buffers, event-loop/thread pool, số lượng subscription, tốc độ message và broker.
7. **Client reconnect liên tục:** backoff + jitter, kiểm tra auth hết hạn, protocol mismatch, rolling deployment, duplicate subscription/cleanup state.

## 10. WebFlux khác gì với Spring MVC WebSocket?

Bài dùng Servlet stack với `org.springframework.web.socket.WebSocketHandler` và `WebSocketSession`. WebFlux có interface ở namespace khác: `org.springframework.web.reactive.socket.WebSocketHandler` với method `Mono<Void> handle(WebSocketSession session)` và các publisher `session.receive()`, `session.send(...)`. Handshake trong WebFlux được điều phối bởi `HandshakeWebSocketService`/`WebSocketHandlerAdapter`, không đăng ký thông qua `@EnableWebSocket` + `WebSocketConfigurer` của MVC.

Ví dụ **fragment WebFlux**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.server.support.WebSocketHandlerAdapter;
import reactor.core.publisher.Mono;

import java.util.Map;

@Bean
HandlerMapping webSocketMapping() {
    WebSocketHandler echo = session ->
            session.send(session.receive()
                    .map(message -> session.textMessage(
                            "echo:" + message.getPayloadAsText())));

    SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
    mapping.setOrder(-1);
    mapping.setUrlMap(Map.of("/ws/reactive", echo));
    return mapping;
}

@Bean
WebSocketHandlerAdapter webSocketHandlerAdapter() {
    return new WebSocketHandlerAdapter();
}
```

Đoạn này đặt trong `@Configuration` class; không phải file độc lập. WebFlux không có cùng callback `afterConnectionEstablished`/`afterConnectionClosed` như MVC; lifecycle được mô hình hóa bằng reactive stream termination/completion và session methods. Tuy nhiên các quy tắc RFC 6455 về handshake, subprotocol, close và transport vẫn là cùng một giao thức nền. Không dùng lẫn import hai `WebSocketHandler` hoặc `WebSocketSession` thuộc MVC/WebFlux.

## 11. Câu hỏi kiểm tra và tình huống thực hành

**Câu 1.** Nhìn thấy HTTP response `101 Switching Protocols` đã đủ kết luận client STOMP subscribe thành công chưa?

**Trả lời:** Chưa. 101 chỉ xác nhận WebSocket Upgrade; client còn phải gửi STOMP CONNECT, nhận CONNECTED và gửi SUBSCRIBE tương ứng.

**Câu 2.** Server chỉ hỗ trợ `chat.v1` nhưng trả header `Sec-WebSocket-Protocol: chat.v2` trong khi client chỉ đề nghị `chat.v1`. Đúng RFC không?

**Trả lời:** Sai. Server chỉ được chọn subprotocol nằm trong danh sách client đề nghị; trong tình huống này `chat.v2` không được đề nghị.

**Câu 3.** Vì sao không nên dùng `Sec-WebSocket-Key` làm chứng cứ client đã đăng nhập?

**Trả lời:** Key là nonce dùng trong kiểm tra handshake, không phải credential, không ràng buộc người dùng hay quyền truy cập.

**Câu 4.** Cần kiểm tra cookie/token/Origin ở thời điểm nào nếu muốn từ chối trước 101?

**Trả lời:** Trong HTTP security chain và/hoặc `HandshakeInterceptor.beforeHandshake` / handshake handler, trước khi upgrade. Message authorization vẫn cần tiếp tục kiểm tra sau OPEN.

**Câu 5.** Thấy close code 1006 trong client logs có nghĩa server đã gửi `Close(1006)` không?

**Trả lời:** Không. 1006 là trạng thái abnormal closure được API báo, không được gửi trong close frame WebSocket.

**Câu 6.** STOMP heartbeat có giống WebSocket Ping/Pong không?

**Trả lời:** Không. STOMP heartbeat thuộc framing STOMP, còn WebSocket Ping/Pong là control frames RFC 6455. Chúng có thể cùng hỗ trợ phát hiện lỗi nhưng không thay thế trực tiếp cho nhau.

**Câu 7.** `HandshakeInterceptor.afterHandshake` có thay thế `afterConnectionEstablished` trong raw Spring WebSocket handler không?

**Trả lời:** Không. Interceptor quan sát quá trình handshake; handler callback chỉ chạy khi kết nối WebSocket đã được thiết lập.

**Bài thực hành mở rộng:** Từ ví dụ ở mục 8, thử ghi correlation ID không nhạy cảm vào session attributes, thêm timeout phát hiện idle, từ chối client có subprotocol không hỗ trợ và theo dõi OPEN/CLOSED active sessions bằng `ConcurrentHashMap` với cleanup idempotent. Chứng minh bằng log và request thực tế rằng kết nối bị từ chối trước 101 khác với kết nối đã OPEN rồi nhận Close frame.

## Tài liệu tham khảo chính thức

- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
- [RFC 8441 — Bootstrapping WebSockets with HTTP/2](https://www.rfc-editor.org/rfc/rfc8441)
- [Spring Framework — WebSocket Overview](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [Spring Framework — WebSocket Server API and Handshake](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [Spring Framework — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework — WebFlux WebSocket](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html)
- [Spring Framework 6.1 — SubProtocolCapable Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/socket/SubProtocolCapable.html)
