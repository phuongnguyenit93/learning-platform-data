# HandshakeInterceptor, thuộc tính phiên và Principal

> Mục tiêu: hiểu vòng đời HTTP WebSocket handshake, dùng `HandshakeInterceptor` để kiểm tra request và truyền dữ liệu vào `WebSocketSession`, phân biệt handshake attributes với HTTP session attributes và `Principal`, đồng thời bảo vệ danh tính người dùng trong WebSocket/STOMP.

## 1. WebSocket bắt đầu bằng HTTP handshake

Một kết nối WebSocket thông thường bắt đầu bằng HTTP request có yêu cầu nâng cấp protocol (`Upgrade: websocket`). Server kiểm tra request, thương lượng protocol nếu có và chuyển kết nối sang WebSocket. Sau khi handshake thành công, client và server trao đổi frame hai chiều trên cùng kết nối lâu dài.

Spring WebSocket cung cấp hai lớp xử lý chính:

- `HandshakeInterceptor`: chạy quanh bước bắt tay HTTP, có thể kiểm tra request, từ chối kết nối hoặc chuẩn bị attributes cho session.
- `WebSocketHandler`: xử lý vòng đời kết nối và frame sau khi handshake thành công, ví dụ `afterConnectionEstablished`, `handleTextMessage` và `afterConnectionClosed`.

Nếu dùng STOMP trên WebSocket, Spring còn có messaging endpoint, channel và `ChannelInterceptor` để xử lý các frame STOMP như `CONNECT`, `SUBSCRIBE` và `SEND`. `HandshakeInterceptor` và `ChannelInterceptor` thuộc hai giai đoạn khác nhau.

Luồng cơ bản:

```text
Browser / WebSocket client
          |
          | HTTP Upgrade request
          v
   HandshakeInterceptor
       beforeHandshake()
          |
          v
   HandshakeHandler / server
          |
          | Upgrade thành công
          v
      WebSocketSession
       /           \
      v             v
 WebSocketHandler  STOMP messaging
      |             |
      v             v
  WebSocket frame  ChannelInterceptor
                    và @MessageMapping
```

## 2. HandshakeInterceptor là gì?

`org.springframework.web.socket.server.HandshakeInterceptor` là interface cho phép can thiệp trước và sau khi Spring xử lý WebSocket handshake. Interface có hai phương thức:

```java
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
```

`beforeHandshake` được gọi trước khi handshake được xử lý:

- Trả về `true`: cho phép quy trình handshake tiếp tục.
- Trả về `false`: từ chối handshake.
- Có thể ghi dữ liệu vào `attributes`; Spring sao chép các giá trị này vào attributes của `WebSocketSession` được tạo.
- Có thể ném exception nếu quá trình kiểm tra gặp lỗi cần dừng handshake.

`afterHandshake` được gọi sau khi quá trình handshake kết thúc. Tham số `exception` cho biết exception phát sinh trong quá trình đó; giá trị `null` nghĩa là không có exception được truyền vào callback. Đây là callback kết thúc handshake, không phải callback khi WebSocket session đóng.

## 3. Triển khai HandshakeInterceptor tùy chỉnh

Ví dụ sau yêu cầu request đã được xác thực, nhận tenant ID từ header và kiểm tra người dùng có quyền truy cập tenant đó hay không. Chỉ sau khi kiểm tra thành công, interceptor mới đưa tenant ID vào handshake attributes.

```java
import java.security.Principal;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

@Component
class TenantHandshakeInterceptor implements HandshakeInterceptor {

    private final TenantAccessService tenantAccessService;

    TenantHandshakeInterceptor(TenantAccessService tenantAccessService) {
        this.tenantAccessService = tenantAccessService;
    }

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes) {

        Principal principal = request.getPrincipal();
        if (principal == null) {
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return false;
        }

        String tenantId = request.getHeaders().getFirst("X-Tenant-ID");
        if (tenantId == null || tenantId.isBlank()
                || !tenantAccessService.canAccess(principal.getName(), tenantId)) {
            response.setStatusCode(HttpStatus.FORBIDDEN);
            return false;
        }

        attributes.put("tenantId", tenantId);
        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Exception exception) {
        if (exception != null) {
            // Ghi log handshake failure; không ghi token hoặc dữ liệu nhạy cảm.
        }
    }
}
```

`TenantAccessService` là service nghiệp vụ do ứng dụng cung cấp. Header `X-Tenant-ID` do client gửi nên vẫn là dữ liệu không đáng tin cậy; service phải xác minh người dùng hiện tại có quyền truy cập tenant được yêu cầu. Không dùng riêng giá trị header để cấp quyền.

Ví dụ đăng ký interceptor:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
class WebSocketConfig implements WebSocketConfigurer {

    private final WebSocketHandler chatHandler;
    private final TenantHandshakeInterceptor tenantInterceptor;

    WebSocketConfig(
            WebSocketHandler chatHandler,
            TenantHandshakeInterceptor tenantInterceptor) {
        this.chatHandler = chatHandler;
        this.tenantInterceptor = tenantInterceptor;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(chatHandler, "/ws/chat")
                .addInterceptors(tenantInterceptor)
                .setAllowedOrigins("https://app.example.com");
    }
}
```

Đây là cấu hình raw WebSocket dùng `@EnableWebSocket`. Ứng dụng cần cung cấp bean `chatHandler`. Danh sách allowed origins nên là các origin thực tế của frontend. Nếu dùng STOMP, cấu hình endpoint qua `@EnableWebSocketMessageBroker` và `StompEndpointRegistry`, sau đó đăng ký interceptor trên endpoint tương ứng.

## 4. Handshake attributes và WebSocketSession

Tham số `attributes` trong `beforeHandshake` là nơi đưa dữ liệu server đã xác minh vào WebSocket session. Spring sao chép map này khi tạo session. Sau handshake, handler đọc dữ liệu bằng `WebSocketSession.getAttributes()`.

Ví dụ:

```java
import java.security.Principal;

import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

class ChatHandler extends TextWebSocketHandler {

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        Principal principal = session.getPrincipal();
        String tenantId = (String) session.getAttributes().get("tenantId");

        String username = principal != null ? principal.getName() : "anonymous";
        System.out.println("Connected user=" + username + ", tenant=" + tenantId);
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session,
            org.springframework.web.socket.CloseStatus status) {
        // Giải phóng tài nguyên gắn với session tại đây nếu cần.
    }
}
```

Đoạn mã minh họa cách đọc hai nguồn thông tin khác nhau: `getPrincipal()` trả về danh tính đã xác thực nếu có; `getAttributes()` trả về dữ liệu ứng dụng đã được gắn vào session trong handshake. `System.out.println` chỉ dùng để minh họa; ứng dụng thực tế nên dùng logger có cấu trúc.

Attributes thường phù hợp với dữ liệu nhỏ, ổn định trong suốt vòng đời kết nối như `tenantId`, locale, mã workspace hoặc feature context đã được kiểm tra. Không nên lưu toàn bộ request, servlet session object, token bí mật, object lớn hoặc mutable state dùng chung vào map này.

## 5. HttpSessionHandshakeInterceptor

Spring cung cấp `HttpSessionHandshakeInterceptor` để sao chép một phần hoặc toàn bộ thuộc tính từ HTTP session vào handshake attributes. Các giá trị đó sau đó có thể đọc qua `WebSocketSession.getAttributes()`.

Hai cách khởi tạo phổ biến:

```java
import java.util.List;

import org.springframework.web.socket.server.support.HttpSessionHandshakeInterceptor;

// Constructor mặc định: copy tất cả HTTP session attributes và session ID.
var copyEverything = new HttpSessionHandshakeInterceptor();

// Constructor có danh sách: chỉ copy các attribute được chỉ định.
var copySelected = new HttpSessionHandshakeInterceptor(
        List.of("locale", "preferredTheme")
);
copySelected.setCopyHttpSessionId(false);
```

Constructor mặc định copy tất cả HTTP session attributes và HTTP session ID. Constructor nhận collection chỉ copy các attribute được chỉ định; mặc định vẫn copy HTTP session ID. Có thể tắt việc copy ID bằng `setCopyHttpSessionId(false)`. `setCreateSession(false)` là mặc định, nghĩa là interceptor không yêu cầu tạo HTTP session mới chỉ để đọc dữ liệu.

Ví dụ đăng ký interceptor có allowlist:

```java
registry.addHandler(chatHandler, "/ws/chat")
        .addInterceptors(copySelected);
```

Hãy chọn attribute cần thiết thay vì copy toàn bộ session. HTTP session thường chứa thông tin xác thực, CSRF state, dữ liệu người dùng hoặc object nội bộ. Sao chép mọi thứ làm tăng dữ liệu tồn tại trong WebSocket session và có thể để lộ thông tin nếu handler ghi log hoặc trả dữ liệu sai cách.

## 6. Phân biệt HTTP session, WebSocket session attributes và Principal

Ba khái niệm này có liên quan nhưng phục vụ các mục đích khác nhau:

| Thành phần | Nội dung | Cách truy cập |
|---|---|---|
| HTTP session | Trạng thái server-side gắn với các HTTP request qua cookie/session ID | `HttpSession` trong Servlet application |
| WebSocket session attributes | Dữ liệu ứng dụng được gắn vào một kết nối WebSocket trong handshake | `WebSocketSession.getAttributes()` |
| `Principal` | Danh tính người dùng đã được xác thực | `request.getPrincipal()`, `WebSocketSession.getPrincipal()` hoặc tham số `Principal` trong STOMP controller |

`HttpSessionHandshakeInterceptor` chỉ sao chép những attribute được chọn từ HTTP session sang WebSocket session attributes. Nó không biến các giá trị đó thành `Principal` và không thực hiện xác thực người dùng.

Với một ứng dụng Spring Security thông thường, HTTP request handshake đã được xác thực trước khi nâng cấp protocol. Spring tự động liên kết `Principal` của HTTP request với WebSocket/SockJS session. Khi dùng STOMP, danh tính đó tiếp tục được gắn vào các message dưới dạng user header.

Vì vậy, hãy dùng `Principal` làm nguồn danh tính đã xác thực. Dùng handshake attributes cho context ứng dụng như tenant hoặc locale sau khi đã xác minh. Việc người dùng có thể truy cập một destination hoặc thao tác cụ thể vẫn cần authorization.

## 7. Principal trong raw WebSocket handler

Với raw WebSocket API, handler có thể đọc danh tính qua `WebSocketSession.getPrincipal()`: 

```java
import java.security.Principal;

import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

class PrivateChatHandler extends TextWebSocketHandler {

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        Principal principal = session.getPrincipal();
        if (principal == null) {
            // Chỉ cho phép anonymous nếu chính sách ứng dụng quy định.
            return;
        }

        registerConnection(principal.getName(), session.getId());
    }
}
```

`Principal` có thể là `null` nếu request chưa được xác thực. Nếu endpoint chỉ dành cho người dùng đăng nhập, hãy bảo vệ handshake bằng Spring Security hoặc từ chối kết nối trong interceptor. Không lấy username do client gửi trong query string hay message body làm danh tính thay cho `Principal`.

## 8. Principal trong STOMP và @MessageMapping

Khi dùng STOMP trên WebSocket, Spring tự động truyền `Principal` đã xác thực từ HTTP handshake vào WebSocket/SockJS session và các message tiếp theo. Controller có thể nhận `Principal` trực tiếp:

```java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
class ChatController {

    private final ChatService chatService;

    ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @MessageMapping("/chat.send")
    public void send(ChatMessage message, Principal principal) {
        chatService.sendFrom(principal.getName(), message);
    }
}
```

Ví dụ giả định endpoint đã yêu cầu xác thực và `principal` không null. `ChatMessage` là DTO của ứng dụng; `ChatService` chịu trách nhiệm kiểm tra quyền gửi, lưu nội dung và định tuyến message. Không chỉ dựa vào việc client có thể gửi đến `/app/chat.send` để kết luận người đó được phép gửi vào một phòng chat bất kỳ.

Mặc định, Spring bỏ qua các header STOMP `login` và `passcode` trên frame `CONNECT` khi STOMP chạy trên WebSocket. Spring kỳ vọng danh tính đã được xác thực ở HTTP transport. Hai header đó vẫn có ý nghĩa trong một số mô hình STOMP over TCP, nhưng không nên coi chúng là cơ chế đăng nhập mặc định cho STOMP over WebSocket.

## 9. Xác thực bằng token trong STOMP CONNECT

Một số ứng dụng không dùng cookie hoặc HTTP session, ví dụ mobile app hoặc hệ thống stateless dùng JWT. Khi đó có thể gửi token trong native header của STOMP `CONNECT` và xác thực bằng `ChannelInterceptor`.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompTokenAuthenticationConfig implements WebSocketMessageBrokerConfigurer {

    private final TokenAuthenticationService tokenAuthenticationService;

    StompTokenAuthenticationConfig(TokenAuthenticationService service) {
        this.tokenAuthenticationService = service;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor = MessageHeaderAccessor.getAccessor(
                        message, StompHeaderAccessor.class);

                if (accessor != null && StompCommand.CONNECT.equals(accessor.getCommand())) {
                    String token = accessor.getFirstNativeHeader("Authorization");
                    var authentication = tokenAuthenticationService.authenticate(token);
                    accessor.setUser(authentication);
                }
                return message;
            }
        });
    }
}
```

`TokenAuthenticationService` là service do ứng dụng triển khai để kiểm tra chữ ký, issuer, audience, expiration và quyền của token rồi trả về một `Authentication` hợp lệ. Khi token không hợp lệ, service cần ném authentication exception để từ chối frame `CONNECT`. Sau khi gọi `accessor.setUser(authentication)`, Spring lưu user cho STOMP session và gắn danh tính đó vào các message tiếp theo.

Trình duyệt không cho JavaScript WebSocket API tùy ý thêm HTTP headers vào handshake. Nếu dùng cookie/session, hãy dựa vào HTTP authentication. Nếu cần token stateless cho browser, STOMP CONNECT native header có thể phù hợp hơn; tránh đưa token vào query string vì URL có thể xuất hiện trong access log, proxy log, lịch sử hoặc hệ thống giám sát.

Nếu Spring Security bảo vệ message channel, interceptor xác thực CONNECT phải chạy trước interceptor authorization của Spring Security để user đã được gắn trước khi kiểm tra quyền. Tách cấu hình interceptor xác thực riêng và đặt thứ tự theo hướng dẫn của phiên bản Spring Security đang dùng.

## 10. HandshakeInterceptor và ChannelInterceptor khác nhau

| Tiêu chí | `HandshakeInterceptor` | `ChannelInterceptor` |
|---|---|---|
| Thời điểm | Trước/sau HTTP WebSocket handshake | Trước/sau khi message đi qua Spring messaging channel |
| Đối tượng | `ServerHttpRequest`, `ServerHttpResponse`, `WebSocketHandler`, handshake attributes | `Message<?>`, `MessageChannel`, STOMP headers/accessor |
| Việc thường làm | Kiểm tra request, từ chối kết nối, thêm tenant/locale/session context | Xác thực STOMP CONNECT, authorization, logging hoặc kiểm tra SEND/SUBSCRIBE |
| Phạm vi | Một lần khi tạo kết nối/transport handshake | Nhiều message trong vòng đời STOMP session |
| Ví dụ | Chặn user chưa đăng nhập hoặc tenant không hợp lệ | Kiểm tra token trong CONNECT, chặn subscribe vào destination trái phép |

Không dùng `HandshakeInterceptor` để kiểm tra từng message STOMP vì interceptor chỉ chạy ở giai đoạn handshake. Ngược lại, `ChannelInterceptor` không thay thế việc xác thực HTTP handshake và kiểm tra origin.

## 11. Origin, CSRF và authorization

Handshake interceptor có thể từ chối request, nhưng bảo mật WebSocket cần nhiều lớp:

- **Authentication:** xác định người dùng qua HTTP Security hoặc token authentication trong STOMP CONNECT.
- **Origin validation:** giới hạn origin được phép kết nối để giảm nguy cơ website ngoài domain mở kết nối bằng cookie của người dùng. Cấu hình allowed origins trên endpoint và cân nhắc proxy/load balancer.
- **Authorization:** kiểm tra user có quyền gửi đến destination, subscribe topic hoặc thao tác với resource cụ thể. Với STOMP, Spring Security cung cấp message authorization dựa trên user header.
- **CSRF:** khi dùng cookie-based authentication, cấu hình Spring Security WebSocket/STOMP theo chính sách CSRF của ứng dụng; không tắt bảo vệ chỉ để làm CONNECT hoạt động.
- **Tenant isolation:** tenant ID phải được đối chiếu với `Principal` ở server; không tin giá trị tenant do client tự khai báo.

Origin không phải danh tính người dùng. Một request có origin hợp lệ vẫn cần authentication và authorization. Tương tự, có `Principal` không có nghĩa người dùng được quyền subscribe mọi destination.

## 12. Vòng đời và dọn dẹp session

Cần phân biệt callback của handshake với callback đóng WebSocket:

- `beforeHandshake`: kiểm tra request và chuẩn bị attributes.
- `afterHandshake`: quan sát kết quả xử lý handshake.
- `WebSocketHandler.afterConnectionEstablished`: chạy khi WebSocket session được mở.
- `WebSocketHandler.afterConnectionClosed`: chạy khi session đóng.
- Với STOMP, có thể lắng nghe `SessionConnectEvent`, `SessionConnectedEvent`, `SessionSubscribeEvent` và `SessionDisconnectEvent` tùy mục đích.

Không dùng `afterHandshake` để xóa trạng thái kết nối vì lúc đó session có thể vừa được tạo và còn hoạt động. Đăng ký tài nguyên theo session nên được giải phóng khi `afterConnectionClosed` hoặc sự kiện disconnect tương ứng xảy ra. Việc disconnect có thể được phát nhiều lần tùy transport; thao tác cleanup nên idempotent.

Nếu cần quản lý danh sách session theo user, dùng cấu trúc thread-safe và xóa entry khi disconnect. Cần xử lý reconnect, nhiều tab/trình duyệt của cùng user và session hết hạn. Với STOMP user destination, ưu tiên cơ chế user registry của Spring thay vì tự giả định mỗi user chỉ có một kết nối.

## 13. HttpSession và tuổi thọ WebSocket

HTTP session và WebSocket session có vòng đời khác nhau. WebSocket là kết nối lâu dài; HTTP session có thể hết hạn trong khi socket vẫn mở. Nếu ứng dụng dựa vào HTTP session, cần quyết định cách xử lý khi session hết hạn hoặc user logout:

- Đóng WebSocket session khi người dùng logout hoặc bị thu hồi quyền.
- Kiểm tra quyền ở các message nhạy cảm, đặc biệt nếu quyền có thể thay đổi trong lúc kết nối còn mở.
- Cân nhắc Spring Session WebSocket integration nếu cần phối hợp tuổi thọ HTTP session với WebSocket session.
- Không coi handshake authentication là giấy phép vô thời hạn; token/session có thể hết hạn hoặc bị thu hồi.

Sao chép một giá trị từ HTTP session vào WebSocket attributes không làm giá trị đó tự cập nhật khi HTTP session thay đổi. Nếu dữ liệu có thể thay đổi, hãy đọc từ nguồn trạng thái phù hợp hoặc phát cơ chế cập nhật/thu hồi.

## 14. Kiểm thử HandshakeInterceptor và Principal

Một bộ kiểm thử nên bao phủ cả handshake lẫn các message sau khi kết nối:

1. Request có Principal hợp lệ và tenant được phép: handshake thành công, `tenantId` có trong `WebSocketSession.getAttributes()`.
2. Request không có Principal: handshake bị từ chối với trạng thái phù hợp.
3. Principal không có quyền với tenant được yêu cầu: handshake bị từ chối.
4. Tenant header thiếu, rỗng hoặc sai định dạng: không tạo session.
5. HTTP session interceptor chỉ copy các attribute trong allowlist và không copy session ID khi đã tắt tùy chọn.
6. Raw WebSocket handler nhận đúng `session.getPrincipal()`.
7. STOMP controller nhận đúng Principal của HTTP-authenticated user.
8. Token CONNECT hợp lệ được gắn user; token sai bị từ chối.
9. User không có quyền không thể SEND hoặc SUBSCRIBE destination bị cấm.
10. Disconnect dọn dẹp session/resource đúng một lần về mặt nghiệp vụ.

Unit test có thể gọi trực tiếp `beforeHandshake` với request/response giả để kiểm tra nhánh cho phép và từ chối. Integration test với WebSocket client và server thực tế giúp xác nhận upgrade, cookie, Principal propagation, session attributes và STOMP channel security hoạt động cùng nhau.

## 15. Lỗi thường gặp

- **Nhầm `afterHandshake` với sự kiện WebSocket đóng:** handshake đã hoàn tất không có nghĩa kết nối đã kết thúc; cleanup thuộc callback disconnect.
- **Không kiểm tra giá trị trả về của `beforeHandshake`:** trả `false` là cách từ chối handshake; cần đặt status phù hợp để client nhận được kết quả rõ ràng.
- **Tin tenant ID hoặc user ID từ client:** mọi giá trị client gửi phải được xác minh dựa trên Principal và quyền server-side.
- **Copy toàn bộ HTTP session một cách mặc định:** có thể đưa token, security state hoặc object nội bộ vào WebSocket attributes; ưu tiên allowlist.
- **Coi handshake attributes là Principal:** attributes là context ứng dụng; Principal là danh tính đã xác thực.
- **Dùng `HttpSessionHandshakeInterceptor` để xác thực:** interceptor này sao chép session data, không xác minh credential hoặc quyền truy cập.
- **Dùng `HandshakeInterceptor` để chặn từng STOMP SEND:** cần `ChannelInterceptor` hoặc Spring Security message authorization.
- **Tin STOMP login/passcode trên WebSocket:** Spring mặc định bỏ qua hai header đó và dùng danh tính từ HTTP handshake.
- **Đưa token vào query string:** token có thể xuất hiện trong log hoặc lịch sử URL.
- **Chỉ kiểm tra Origin:** origin allowlist không thay thế authentication và authorization.
- **Giả định Principal không bao giờ null:** endpoint cho anonymous cần xử lý riêng; endpoint private phải yêu cầu xác thực.
- **Không xử lý session hết hạn hoặc logout:** socket có thể tồn tại sau khi HTTP session thay đổi hoặc hết hạn.

## 16. Quy trình triển khai

1. Chọn raw WebSocket hay STOMP; xác định nơi xử lý handshake và nơi xử lý message.
2. Bảo vệ HTTP endpoint bằng Spring Security để xác thực request handshake.
3. Đăng ký `HandshakeInterceptor` cho kiểm tra bổ sung và chuẩn bị attributes đã xác minh.
4. Chỉ copy các HTTP session attributes thật sự cần thiết; cân nhắc tắt copy session ID.
5. Đọc `Principal` từ `WebSocketSession` hoặc tham số controller; dùng attributes cho tenant/locale/context.
6. Nếu dùng token trong STOMP CONNECT, xác thực bằng `ChannelInterceptor` và gắn user qua `accessor.setUser(...)`.
7. Cấu hình origin allowlist, CSRF và message authorization theo threat model.
8. Dọn dẹp tài nguyên ở callback disconnect hoặc sự kiện STOMP disconnect.
9. Kiểm thử handshake failure, Principal propagation, tenant isolation, token invalid, SEND/SUBSCRIBE authorization và session expiration.
10. Theo dõi số kết nối, handshake failure, disconnect, authentication failure và lỗi authorization mà không log credential.

## 17. Kết luận

`HandshakeInterceptor` can thiệp vào HTTP WebSocket handshake: `beforeHandshake` kiểm tra request và thêm attributes, còn `afterHandshake` quan sát kết quả của quá trình bắt tay. Các attributes được sao chép vào `WebSocketSession.getAttributes()` để handler sử dụng trong suốt kết nối.

`Principal` biểu diễn người dùng đã xác thực và được Spring tự động truyền từ HTTP request sang WebSocket/STOMP session trong mô hình HTTP authentication thông thường. `HttpSessionHandshakeInterceptor` chỉ sao chép dữ liệu HTTP session; cần allowlist để tránh mang dữ liệu nhạy cảm sang WebSocket. Với STOMP token authentication, dùng `ChannelInterceptor` ở frame CONNECT. Kết hợp authentication, origin validation, authorization, session cleanup và kiểm thử disconnect để bảo vệ toàn bộ vòng đời kết nối.

## Tài liệu tham khảo

- [Spring Framework Reference — WebSocket API and Handshake](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [Spring Framework Javadoc — HandshakeInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/server/HandshakeInterceptor.html)
- [Spring Framework Javadoc — HttpSessionHandshakeInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/server/support/HttpSessionHandshakeInterceptor.html)
- [Spring Framework Javadoc — WebSocketSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/WebSocketSession.html)
- [Spring Framework Reference — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework Reference — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Security Reference — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)