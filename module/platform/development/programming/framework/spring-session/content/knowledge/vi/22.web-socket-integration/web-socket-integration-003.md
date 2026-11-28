# AbstractSessionWebSocketMessageBrokerConfigurer và cấu hình tích hợp

WebSocket tạo một kết nối hai chiều tồn tại lâu giữa trình duyệt và máy chủ. Trong ứng dụng Spring, người dùng thường đăng nhập qua HTTP trước rồi mở WebSocket để chat, nhận thông báo hoặc cập nhật dữ liệu trực tiếp. Nếu ứng dụng dùng Spring Session, phiên HTTP có thể được lưu trong Redis hoặc JDBC và có thời hạn không hoạt động. Khi WebSocket tiếp tục truyền dữ liệu nhưng không có request HTTP mới, session có nguy cơ hết hạn dù người dùng vẫn đang hoạt động.

Spring Session cung cấp `AbstractSessionWebSocketMessageBrokerConfigurer` để kết nối vòng đời `HttpSession` với WebSocket STOMP của Spring. Lớp cấu hình này tự đăng ký interceptor và listener cần thiết để thông điệp WebSocket từ client cập nhật thời điểm truy cập session, đồng thời đóng các WebSocket còn mở khi Spring Session kết thúc. Nhờ vậy, session và kết nối WebSocket không bị lệch vòng đời trong các ứng dụng dùng Spring WebSocket message broker.

## 1. Vì sao WebSocket cần tích hợp với Spring Session?

HTTP thông thường có request và response riêng. Khi request kết thúc, Spring Session có thể cập nhật thời điểm truy cập cuối cùng. WebSocket khác ở chỗ client và server giữ một kết nối mở để gửi nhiều thông điệp mà không tạo request HTTP mới cho từng thông điệp.

Hãy xét một ứng dụng chat:

1. Người dùng đăng nhập qua HTTP và nhận cookie chứa session ID.
2. Trình duyệt mở kết nối WebSocket và gửi cookie session trong quá trình handshake.
3. Người dùng gửi và nhận tin nhắn qua STOMP.
4. Nếu chỉ có WebSocket hoạt động, không có request HTTP mới để làm mới thời điểm truy cập của HttpSession.
5. Session có thể hết hạn theo idle timeout trong khi WebSocket vẫn đang mở.

Nếu session hết hạn nhưng socket vẫn tiếp tục được giữ, kết nối có thể tồn tại với một trạng thái xác thực đã không còn hợp lệ. Ngược lại, nếu socket bị đóng không đúng lúc, người dùng có thể mất cuộc trò chuyện dù vẫn đang hoạt động.

Tích hợp Spring Session giải quyết hai vấn đề:

- **Gia hạn session theo hoạt động của client:** thông điệp STOMP inbound phù hợp cập nhật thời điểm truy cập cuối cùng của Spring Session.
- **Đóng kết nối theo vòng đời session:** khi Spring Session bị kết thúc, các WebSocket liên kết với session đó được đóng.

Spring Session WebSocket support làm việc với Spring WebSocket. Tích hợp này không áp dụng trực tiếp cho JSR-356 thuần vì JSR-356 không cung cấp cơ chế Spring cần để chặn các thông điệp WebSocket inbound.

## 2. Điều kiện trước khi cấu hình

Trước khi thêm WebSocket integration, cần có các thành phần sau:

| Thành phần | Vai trò |
|---|---|
| Spring WebSocket | Cung cấp WebSocket và message broker abstraction của Spring |
| STOMP message broker support | Ánh xạ endpoint, destination và xử lý thông điệp |
| Spring Session HttpSession integration | Thay HttpSession mặc định bằng session repository |
| SessionRepository | Lưu session trong Redis, JDBC hoặc kho tương ứng |
| Scheduling | Chạy tác vụ nền hỗ trợ dọn kết nối gắn với session đã hết hạn |

Spring Session phải được tích hợp với HttpSession trước. Ví dụ, nếu dùng Redis, ứng dụng cần cấu hình Spring Session Redis và kết nối Redis hoạt động. Nếu dùng JDBC, schema và repository JDBC phải sẵn sàng. WebSocket integration bổ sung hành vi cho session đã được quản lý; nó không tự tạo kho lưu trữ session thay cho cấu hình Redis/JDBC.

Tích hợp trong bài này dành cho ứng dụng Servlet dùng Spring WebSocket message broker và STOMP. Nó không phải cấu hình cho WebFlux WebSocket handler hoặc cho endpoint JSR-356 độc lập.

## 3. AbstractSessionWebSocketMessageBrokerConfigurer là gì?

`AbstractSessionWebSocketMessageBrokerConfigurer<S extends Session>` là lớp cấu hình trừu tượng của Spring Session, triển khai `WebSocketMessageBrokerConfigurer`. Tham số generic `S` là kiểu session của Spring Session repository.

Thay vì tự triển khai `WebSocketMessageBrokerConfigurer` rồi tự nối tất cả interceptor, ứng dụng kế thừa lớp này. Lớp cha thiết lập các thành phần tích hợp session; ứng dụng tập trung vào endpoint STOMP và message broker.

Hai điểm thay đổi chính so với cấu hình WebSocket STOMP thông thường:

1. Kế thừa `AbstractSessionWebSocketMessageBrokerConfigurer<Session>` thay cho việc chỉ implements `WebSocketMessageBrokerConfigurer`.
2. Đăng ký endpoint trong `configureStompEndpoints` thay cho `registerStompEndpoints`. Lớp cha cung cấp phương thức đăng ký cuối cùng và tự gắn interceptor Spring Session vào các endpoint STOMP.

Phương thức `configureStompEndpoints` là phương thức abstract mà ứng dụng phải override. Các phương thức như `configureMessageBroker` vẫn có thể override như trong cấu hình Spring WebSocket thông thường.

## 4. Cấu hình WebSocket STOMP với Spring Session

Ví dụ cấu hình dưới đây đăng ký endpoint `/messages`, bật SockJS fallback, sử dụng simple broker cho topic/queue và định tuyến thông điệp ứng dụng qua tiền tố `/app`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.session.Session;
import org.springframework.session.web.socket.config.annotation.AbstractSessionWebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;

@Configuration
@EnableScheduling
@EnableWebSocketMessageBroker
public class WebSocketConfig
        extends AbstractSessionWebSocketMessageBrokerConfigurer<Session> {

    @Override
    protected void configureStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/messages").withSockJS();
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/queue/", "/topic/");
        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Các annotation có ý nghĩa:

- `@Configuration` đăng ký lớp làm cấu hình Spring.
- `@EnableWebSocketMessageBroker` bật message broker support của Spring WebSocket.
- `@EnableScheduling` bật scheduler cho tác vụ nền mà tích hợp WebSocket session sử dụng để dọn kết nối gắn với session hết hạn.

`withSockJS()` bật SockJS fallback cho môi trường mà WebSocket native không khả dụng. Nếu client và hạ tầng chỉ hỗ trợ WebSocket native, có thể bỏ SockJS và đăng ký endpoint trực tiếp.

## 5. Cấu hình message broker

`configureMessageBroker` vẫn dùng API chuẩn của Spring:

- `enableSimpleBroker("/queue/", "/topic/")` bật broker đơn giản trong bộ nhớ cho các destination có tiền tố tương ứng.
- `setApplicationDestinationPrefixes("/app")` định tuyến thông điệp gửi đến `/app` vào các handler phía ứng dụng, thường là phương thức có `@MessageMapping`.

Ví dụ handler:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat")
    @SendTo("/topic/messages")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}

public record ChatMessage(String sender, String content) {
}
~~~

Client gửi STOMP message đến `/app/chat`; handler xử lý và kết quả được gửi đến `/topic/messages`. Việc tích hợp Spring Session diễn ra quanh handshake và inbound channel, nên controller không cần tự cập nhật last accessed time.

## 6. Những thành phần được đăng ký tự động

`AbstractSessionWebSocketMessageBrokerConfigurer` kết hợp ba thành phần chính:

| Thành phần | Điểm được gắn vào | Vai trò |
|---|---|---|
| `SessionRepositoryMessageInterceptor` | STOMP handshake và inbound channel | Gắn session ID vào thuộc tính WebSocket và cập nhật last accessed time khi có thông điệp inbound phù hợp |
| `WebSocketConnectHandlerDecoratorFactory` | WebSocket transport | Phát sự kiện kết nối chứa WebSocketSession để ánh xạ socket với Spring Session |
| `WebSocketRegistryListener` | Spring application context | Theo dõi quan hệ session ID và WebSocket connection; đóng socket khi session kết thúc |

Lớp cấu hình tự đăng ký các thành phần này. Trong cấu hình thông thường, không cần tự tạo thêm interceptor hoặc listener cùng chức năng. Nếu tự thêm lần nữa, có thể gây cập nhật session lặp, đăng ký listener trùng hoặc hành vi khó chẩn đoán.

## 7. SessionRepositoryMessageInterceptor hoạt động ra sao?

`SessionRepositoryMessageInterceptor` có hai vai trò: `HandshakeInterceptor` và `ChannelInterceptor`.

### 7.1. Trong quá trình handshake

Khi client mở kết nối STOMP qua WebSocket endpoint, interceptor được gọi trong handshake. Nó liên kết session ID của Spring Session với thuộc tính của WebSocket session. Thông tin này giúp các thông điệp STOMP sau đó tìm lại đúng session repository record.

Điều kiện quan trọng là handshake phải đi cùng HTTP session hợp lệ. Trình duyệt thường gửi cookie session trong request handshake. Nếu cookie bị thiếu do cấu hình domain, path, Secure, SameSite, proxy hoặc origin không phù hợp, WebSocket có thể được tạo trong trạng thái không gắn với session mong muốn.

### 7.2. Trong inbound channel

Interceptor được thêm vào inbound channel để xử lý thông điệp từ client. Khi nhận một loại STOMP message được cấu hình để khớp, interceptor:

1. Đọc session ID đã gắn trong thuộc tính WebSocket.
2. Tìm session tương ứng qua SessionRepository.
3. Kiểm tra session còn hợp lệ hay đã hết hạn.
4. Cập nhật thời điểm truy cập cuối cùng nếu session còn hợp lệ.
5. Nếu session đã hết hạn, chặn thông điệp không cho tiếp tục đi vào message flow.

Theo API hiện tại, các loại message mặc định được theo dõi gồm `CONNECT`, `MESSAGE`, `SUBSCRIBE` và `UNSUBSCRIBE`. Có thể cấu hình tập loại message khớp khi tự quản lý interceptor, nhưng khi dùng configurer tích hợp, nên giữ mặc định trừ khi có yêu cầu cụ thể và đã kiểm thử.

### 7.3. Chỉ thông điệp từ client mới gia hạn session

Một điểm dễ hiểu nhầm: thông điệp server gửi về client không chứng minh người dùng đang hoạt động. Vì vậy, các thông điệp outbound như thông báo mới, broadcast hoặc server push không làm mới idle timeout theo cơ chế interceptor này.

Ví dụ:

- Người dùng gửi chat message: inbound MESSAGE được xử lý và có thể cập nhật last accessed time.
- Người dùng đăng ký topic: inbound SUBSCRIBE được xử lý và có thể cập nhật thời gian truy cập.
- Server đẩy một thông báo đến client: outbound message không được tính là hoạt động từ người dùng.
- Client không gửi gì trong thời gian dài: session vẫn có thể hết hạn dù socket còn nhận dữ liệu server push.

Quy tắc này ngăn một kết nối mở nhưng không có hoạt động client giữ session sống vô thời hạn chỉ vì server liên tục gửi dữ liệu.

## 8. WebSocketConnectHandlerDecoratorFactory và sự kiện kết nối

`WebSocketConnectHandlerDecoratorFactory` được thêm vào `WebSocketTransportRegistration`. Nó bọc WebSocket handler để phát một sự kiện Spring Session đặc biệt là `SessionConnectEvent` có chứa `WebSocketSession`.

Sự kiện này cung cấp cả thông tin kết nối WebSocket và session liên quan. Spring Session dùng nó để đăng ký quan hệ giữa session ID và WebSocket connection. Khi session kết thúc, hệ thống có thể tìm các socket liên quan và đóng chúng.

Nếu chỉ có session repository mà không có mapping WebSocket, việc xóa session trong Redis/JDBC không tự động đóng một socket TCP đang mở. Tích hợp decorator và registry bổ sung phần liên kết giữa hai vòng đời.

Ứng dụng không cần tự phát `SessionConnectEvent` trong cấu hình thông thường. Nếu viết custom WebSocket transport decorator hoặc thay thế cách đăng ký transport, cần bảo đảm decorator Spring Session vẫn được áp dụng.

## 9. WebSocketRegistryListener và đóng kết nối khi session kết thúc

`WebSocketRegistryListener` là Spring bean theo dõi các sự kiện kết nối và kết thúc session. Nó duy trì mapping giữa Spring Session ID và các WebSocket connection tương ứng.

Khi session bị invalidate, hết hạn hoặc kết thúc theo event mà repository phát ra, listener tìm các socket gắn với session và đóng chúng. Điều này đặc biệt quan trọng với ứng dụng chat hoặc dashboard: người dùng đã logout không nên tiếp tục giữ một kết nối được xác thực bằng session cũ.

Vòng đời có thể hình dung:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant W as Spring WebSocket/STOMP
    participant I as SessionRepositoryMessageInterceptor
    participant R as Spring Session Repository
    participant L as WebSocketRegistryListener

    B->>W: HTTP handshake kèm session cookie
    W->>I: HandshakeInterceptor
    I->>R: Xác định session
    I-->>W: Gắn session ID vào WebSocket attributes
    W-->>L: SessionConnectEvent chứa WebSocketSession
    L->>L: Lưu mapping session ID -> socket
    B->>W: STOMP MESSAGE / SUBSCRIBE
    W->>I: Inbound ChannelInterceptor
    I->>R: Kiểm tra session và cập nhật last access
    R-->>I: Session hợp lệ
    I-->>W: Cho phép message tiếp tục
    Note over R,L: Session bị invalidate hoặc hết hạn
    R-->>L: Sự kiện session kết thúc
    L->>W: Đóng WebSocket liên quan
    W-->>B: Kết nối bị đóng
~~~

Đóng socket không thay thế việc kiểm tra quyền ở từng message. Ứng dụng vẫn phải bảo vệ các destination STOMP, kiểm tra principal và quyền truy cập. Tích hợp session bảo đảm liên kết vòng đời; authorization vẫn thuộc Spring Security và logic ứng dụng.

## 10. Vì sao cần @EnableScheduling?

Thông báo hết hạn từ kho lưu trữ không phải lúc nào cũng đến đúng thời điểm TTL. Với Redis, keyspace expiration notification phụ thuộc cấu hình và cơ chế phát sự kiện; thông báo có thể đến trễ hoặc bị bỏ lỡ trong một số tình huống.

Spring Session WebSocket support dùng một tác vụ nền định kỳ để dọn các WebSocket gắn với session đã hết hạn. Cấu hình mẫu bật `@EnableScheduling`. Theo hướng dẫn Spring Session, tác vụ này chạy mỗi phút tại giây 00 để đóng các kết nối còn mở của session hết hạn ngay cả khi notification không được chuyển đến kịp thời.

Điều đó có nghĩa:

- TTL của session vẫn quyết định thời điểm session hết hạn về mặt repository.
- Notification có thể giúp đóng socket sớm hơn.
- Scheduled cleanup là lớp dự phòng để phát hiện và đóng kết nối còn sót.
- Không nên kỳ vọng socket luôn bị đóng chính xác tại mili giây session hết hạn.

Ví dụ hướng dẫn dùng session timeout một phút và cho thấy socket có thể cần tối đa khoảng hai phút mới bị đóng: tối đa một phút chờ notification/cleanup cộng với chu kỳ chạy tác vụ nền. Thời gian thực tế phụ thuộc scheduler, backend và cấu hình triển khai.

Nếu ứng dụng đã có scheduler riêng, vẫn cần bảo đảm tác vụ của Spring Session được kích hoạt theo cơ chế hỗ trợ. Không tự viết một job thứ hai quét toàn bộ session nếu không hiểu chi phí và cách phối hợp với listener có sẵn.

## 11. Cấu hình Spring Session trước WebSocket

Ví dụ với Redis trong ứng dụng Servlet:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession
public class SessionConfig {
}
~~~

Sau đó mới thêm WebSocket config kế thừa `AbstractSessionWebSocketMessageBrokerConfigurer`. Nếu dùng JDBC, cấu hình JDBC session repository thay cho Redis và bảo đảm schema đã được tạo.

Không bật đồng thời hai cấu hình session repository độc lập cho cùng một HttpSession nếu không có thiết kế rõ ràng. Ứng dụng cần một nguồn session nhất quán để WebSocket handshake, HTTP request và logout cùng tham chiếu một session ID.

Trong Spring Boot, có thể dùng auto-configuration thay vì khai báo annotation thủ công. Hãy kiểm tra cách ứng dụng đang bật Spring Session để tránh tạo repository hoặc filter trùng lặp.

## 12. Cấu hình STOMP endpoint, SockJS và origin

Endpoint STOMP được đăng ký trong `configureStompEndpoints`:

~~~java
@Override
protected void configureStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/messages").withSockJS();
}
~~~

`withSockJS()` bật SockJS fallback cho môi trường mà WebSocket native không khả dụng. Nếu client và hạ tầng chỉ hỗ trợ WebSocket native, có thể bỏ SockJS và đăng ký endpoint trực tiếp.

Các điểm cần kiểm tra:

- Origin frontend phải được cho phép chính xác.
- Cookie session cần được gửi trong handshake theo domain/path và chính sách SameSite phù hợp.
- Reverse proxy phải hỗ trợ HTTP Upgrade và chuyển tiếp kết nối WebSocket.
- Nếu dùng HTTPS, proxy và backend phải xử lý scheme/forwarded headers nhất quán.
- Endpoint handshake cần được bảo vệ bởi Spring Security theo chính sách xác thực.

Không dùng wildcard origin như một cách chữa lỗi cookie hoặc CORS. Hãy xác định origin thực tế và giới hạn rõ ràng.

## 13. Kết hợp với Spring Security

Thông thường, người dùng xác thực bằng HTTP trước khi mở WebSocket. Handshake sử dụng session cookie để gắn kết nối với cùng HttpSession. Spring Security có thể cung cấp Principal cho WebSocket message handler và áp dụng authorization trên inbound STOMP channel.

Một số nguyên tắc:

- Bảo vệ endpoint handshake theo yêu cầu ứng dụng.
- Xác thực quyền trên các destination như `/app/chat`, `/topic/room` và `/user/queue`.
- Không tin dữ liệu sender/userId do client gửi trong message body; lấy principal từ security context.
- Khi logout, invalidate HttpSession để Spring Session phát sự kiện kết thúc và listener đóng các WebSocket liên quan.
- Với CSRF protection cho STOMP CONNECT, cấu hình token theo Spring Security WebSocket guidance của phiên bản dự án.

Đóng socket khi session kết thúc là lớp bảo vệ vòng đời. Nó không thay thế authorization cho mỗi thao tác gửi/nhận thông điệp, cũng không thay thế kiểm tra quyền theo room hoặc tài nguyên nghiệp vụ.

## 14. Tích hợp trong nhiều instance

Trong hệ thống có nhiều instance, HTTP request có thể đến node A còn WebSocket connection được giữ trên node B. Session repository dùng chung giúp cả hai node nhìn thấy cùng trạng thái session, nhưng mỗi WebSocket connection vẫn được quản lý tại node đang giữ socket.

Để đóng kết nối đúng:

- Mọi node dùng cùng Spring Session store, namespace và serializer.
- Cấu hình WebSocket integration giống nhau trên các node.
- Session destruction event phải được phát và chuyển tới node đang giữ socket theo cơ chế backend hỗ trợ.
- Redis keyspace notifications hoặc cơ chế event tương ứng phải được cấu hình đúng nếu repository dựa vào chúng.
- Scheduled cleanup cần được bật để xử lý session hết hạn khi notification đến trễ hoặc không đến.

Không giả định một mapping Java trong bộ nhớ của node A tự nhìn thấy socket trên node B. `WebSocketRegistryListener` theo dõi các socket mà node đó quản lý; việc session kết thúc phải được phản ánh đến các node liên quan qua cơ chế event/cleanup của Spring Session.

Với Redis, kiểm tra cấu hình keyspace notification mà Spring Session cần và quyền Pub/Sub của Redis user. Với JDBC, kiểm tra event publication và cleanup của repository phiên bản đang dùng; không mặc định database tự phát event giống Redis.

## 15. Khi nào nên dùng cấu hình tích hợp này?

| Trường hợp | Cách tiếp cận |
|---|---|
| Spring STOMP message broker, session HTTP cần được gia hạn bởi inbound message | Dùng AbstractSessionWebSocketMessageBrokerConfigurer |
| Spring STOMP, cần đóng socket khi HttpSession kết thúc | Dùng configurer tích hợp và scheduling |
| WebSocket native không dùng STOMP broker | Cần đánh giá API Spring WebSocket handler và tự đăng ký các thành phần tương ứng; configurer STOMP này không phải điểm mở rộng trực tiếp |
| JSR-356 endpoint thuần | Không được tích hợp tự động theo cơ chế này |
| WebFlux WebSocket | Dùng reactive web stack phù hợp; không áp dụng configurer Servlet/STOMP này một cách máy móc |
| Chỉ dùng HTTP polling | Không cần WebSocket session integration |

Chọn đúng stack từ đầu giúp tránh cố gắng gắn HttpSession vào một loại WebSocket API không cung cấp hook cần thiết.

## 16. Kiểm thử tích hợp WebSocket và session

Không chỉ kiểm tra handshake thành công. Cần chứng minh cả gia hạn session và đóng socket khi session kết thúc.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Handshake có session | Đăng nhập HTTP, mở STOMP bằng cùng cookie | Kết nối gắn với session đã xác thực |
| Inbound message gia hạn session | Gửi MESSAGE/SUBSCRIBE trước idle timeout | Last accessed time được cập nhật |
| Chỉ nhận server push | Không gửi inbound message, chỉ nhận outbound | Không giả định session được gia hạn |
| Session hết hạn | Để session vượt idle timeout | Message tiếp theo bị chặn và socket được đóng theo event/cleanup |
| Logout | Invalidate HttpSession khi socket đang mở | WebSocket liên quan bị đóng |
| Nhiều socket cùng session | Mở nhiều kết nối từ cùng session | Khi session kết thúc, các kết nối liên quan đều được đóng |
| Cookie thiếu hoặc sai | Bỏ cookie trong handshake | Không gắn nhầm với session đã xác thực |
| Origin không hợp lệ | Gửi handshake từ origin không được phép | Handshake bị từ chối |
| Redis notification trễ | Mô phỏng event không đến ngay | Scheduled cleanup vẫn đóng kết nối hết hạn |
| Multi-instance | HTTP/login ở A, WebSocket ở B | Session được chia sẻ và event kết thúc được phản ánh tới socket |

### 16.1. Kiểm thử với thời gian timeout ngắn

Trong test, có thể đặt session timeout ngắn, ví dụ một phút, để quan sát hành vi hết hạn. Không dùng timeout ngắn trong production chỉ để tiện thử nghiệm.

Một quy trình kiểm thử:

1. Đăng nhập và lấy session cookie.
2. Mở WebSocket/STOMP endpoint với cookie đó.
3. Gửi message từ client theo chu kỳ ngắn hơn idle timeout và xác nhận kết nối vẫn hoạt động.
4. Dừng gửi inbound message, chỉ để server gửi outbound message nếu có.
5. Chờ session hết hạn và chu kỳ cleanup.
6. Xác nhận WebSocket bị đóng và request HTTP tiếp theo yêu cầu xác thực lại.

Kiểm thử phải tính đến độ trễ của scheduler và backend notification; không assert rằng socket chắc chắn đóng đúng tại thời điểm TTL vừa chạm 0.

## 17. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| WebSocket hoạt động nhưng session vẫn hết hạn khi chat | Interceptor không được gắn hoặc client chỉ nhận message outbound | Kế thừa configurer tích hợp, kiểm tra inbound STOMP traffic |
| Không đóng socket sau logout | Session event không tới listener, listener không được tạo hoặc socket không được map | Kiểm tra WebSocketRegistryListener, decorator và event repository |
| Endpoint STOMP không đăng ký | Override nhầm registerStompEndpoints thay vì configureStompEndpoints | Override configureStompEndpoints |
| Không có tác vụ cleanup nền | Thiếu @EnableScheduling hoặc scheduler không hoạt động | Bật scheduling và kiểm tra scheduler logs |
| Handshake không mang session | Cookie không được gửi hoặc domain/path/SameSite sai | Kiểm tra request handshake và cookie policy |
| Socket vẫn sống sau khi session hết hạn | Redis notification không bật hoặc cleanup chưa chạy | Kiểm tra keyspace events, scheduling và TTL |
| Chỉ một node đóng được socket | Session event không lan đến node giữ kết nối | Kiểm tra event propagation và kiến trúc multi-instance |
| Cấu hình listener bị chạy hai lần | Tự đăng ký thêm interceptor/listener cùng với configurer | Bỏ đăng ký trùng và dùng một đường tích hợp |
| JSR-356 không gia hạn session | API không cho Spring chặn inbound message theo cơ chế này | Dùng Spring WebSocket support hoặc tự thiết kế tích hợp khác |
| Server push giữ session sống mãi | Nhầm outbound message là hoạt động client | Chỉ tính inbound activity theo chính sách idle timeout |

## 18. Nguyên tắc triển khai

- Tích hợp Spring Session với HttpSession trước khi cấu hình WebSocket.
- Dùng Spring WebSocket STOMP message broker nếu muốn dùng AbstractSessionWebSocketMessageBrokerConfigurer.
- Kế thừa AbstractSessionWebSocketMessageBrokerConfigurer và override configureStompEndpoints.
- Giữ configureMessageBroker theo cấu hình broker của ứng dụng.
- Bật @EnableScheduling để tác vụ nền dọn WebSocket gắn với session hết hạn hoạt động.
- Để SessionRepositoryMessageInterceptor xử lý handshake và inbound channel; tránh đăng ký trùng.
- Hiểu chỉ thông điệp inbound phù hợp mới cập nhật last accessed time; outbound message không chứng minh client còn hoạt động.
- Để WebSocketRegistryListener theo dõi mapping session/socket và đóng kết nối khi session kết thúc.
- Đồng bộ session store, event configuration và WebSocket setup giữa các node.
- Bảo vệ origin, handshake, cookie và STOMP destination bằng cấu hình bảo mật phù hợp.
- Kiểm thử logout, expiration, event delay, nhiều socket và nhiều instance.

AbstractSessionWebSocketMessageBrokerConfigurer kết nối vòng đời Spring Session với STOMP WebSocket bằng cách tự gắn interceptor, transport decorator và registry listener. Inbound message từ client có thể gia hạn idle timeout; khi session kết thúc, các socket liên quan được đóng theo event và tác vụ cleanup dự phòng. Khi HttpSession repository, scheduler, cookie và WebSocket message broker được cấu hình nhất quán, ứng dụng có thể duy trì kết nối thời gian thực mà vẫn tôn trọng thời hạn và trạng thái xác thực của session.
