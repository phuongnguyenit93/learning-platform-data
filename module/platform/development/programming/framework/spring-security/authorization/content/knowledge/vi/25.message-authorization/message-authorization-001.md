# Phân biệt bảo vệ HTTP handshake với bảo vệ thông điệp STOMP trong Spring Security

## 1. Bài toán: WebSocket kết nối thành công không đồng nghĩa được làm mọi việc

Giả sử một ứng dụng chat nội bộ dùng Spring Boot, Spring WebSocket và STOMP:

- Người dùng Alice truy cập `/ws` để thiết lập kết nối WebSocket.
- Alice gửi tin nhắn bằng lệnh STOMP `SEND` tới `/app/chat.send`.
- Alice đăng ký nhận thông báo bằng `SUBSCRIBE` tới `/user/queue/messages`.
- Một hệ thống quản trị phát thông báo tới `/topic/system`.
- Những phòng chat riêng của tenant A chỉ dành cho thành viên tenant A.

Nếu Spring Security chỉ kiểm tra HTTP:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/ws", "/ws/**").authenticated()
    .anyRequest().denyAll()
);
```

thì điều này giúp bảo vệ đường HTTP dùng để bắt tay, **không phải một chính sách đầy đủ cho mọi frame STOMP về sau**. Một WebSocket đã nâng cấp kết nối có thể tồn tại lâu; các frame `SEND`, `SUBSCRIBE`, `UNSUBSCRIBE` và `DISCONNECT` đi qua hệ thống xử lý thông điệp, không phải mỗi lần tạo một HTTP request mới cho `SecurityFilterChain`.

Ví dụ attacker có tài khoản hợp lệ nhưng không thuộc phòng `finance` vẫn có thể thử:

```text
SUBSCRIBE
id:sub-1
destination:/topic/rooms/finance

^@
```

hoặc gửi vào kênh mà ứng dụng chỉ dự định **server** được phép phát:

```text
SEND
destination:/topic/system
content-type:text/plain

Fake emergency notice^@
```

Nếu thiếu **message-level authorization**, thành công ở handshake có thể dẫn tới đọc hoặc phát dữ liệu sai quyền. Ký hiệu `^@` ở trên chỉ minh họa STOMP frame terminator (byte NUL), không phải ký tự literal bắt buộc gõ trong client.

**Thông điệp trọng tâm:** HTTP handshake bảo vệ **việc thiết lập transport và danh tính ban đầu**; authorization STOMP bảo vệ **từng loại thông điệp, đích đến, resource và ngữ cảnh**. Hai tầng phải phối hợp chứ không thay thế nhau.

### Mục tiêu

Sau bài này, bạn có thể:

1. Mô tả đường đi `HTTP handshake → STOMP CONNECT → SEND/SUBSCRIBE → broker → client`.
2. Phân biệt `SecurityFilterChain` của Servlet HTTP với `AuthorizationManager<Message<?>>` của Spring Messaging.
3. Hiểu `Principal` được truyền từ HTTP sang STOMP session như thế nào, và trường hợp token-based authentication cần `ChannelInterceptor` riêng.
4. Phân biệt destination `/app/**`, `/topic/**`, `/queue/**` và `/user/**`.
5. Viết cấu hình `@EnableWebSocketSecurity` có thứ tự matcher rõ, mặc định deny.
6. Không cho client SEND trực tiếp vào broker destination để giả mạo server.
7. Không cho SUBSCRIBE vào private tenant/user destinations ngoài quyền.
8. Hiểu Same Origin, Origin allowlist, CSRF ở STOMP CONNECT và các vấn đề SockJS.
9. Kiểm thử handshake **và** STOMP frames, kể cả lỗi không được chuyển sang broker.
10. Chạy một ví dụ Java 17 độc lập mô phỏng sự khác biệt giữa hai tầng.

## 2. Từ HTTP đến STOMP: hai giao thức, hai điểm cưỡng chế

Một luồng có thể gồm:

```text
Browser                                  Spring Boot / Spring Security
   |
   |  1. GET /ws + Upgrade: websocket
   +--------------------------------------> SecurityFilterChain (HTTP)
   |                                             |
   |                          authentication, URL authorization, origin/CSRF
   |                                             |
   |  2. HTTP 101 Switching Protocols <----------+
   |       (nếu được chấp nhận)
   |
   |  3. STOMP CONNECT frame
   +--------------------------------------> clientInboundChannel
   |                                             |
   |                             CONNECT authentication / CSRF / security
   |                                             |
   |  4. STOMP CONNECTED <------------------------+
   |
   |  5. STOMP SUBSCRIBE /user/queue/messages
   +--------------------------------------> message AuthorizationManager
   |                                             |
   |                              authorization per type + destination
   |                                             |
   |  6. STOMP SEND /app/chat.send
   +--------------------------------------> @MessageMapping + domain policy
   |                                             |
   |                              SimpMessagingTemplate / message broker
   |                                             |
   |  7. STOMP MESSAGE <--------------------------+
```

Điểm cần lưu ý: `101 Switching Protocols` là phản hồi thành công của native WebSocket handshake; với SockJS fallback transport, HTTP request/response có thể khác. `STOMP CONNECTED` là xác nhận ở **lớp giao thức STOMP**, không phải HTTP 101.

### Bảng ranh giới

| Sự kiện | Điểm xử lý chính | Vấn đề được giải quyết |
| --- | --- | --- |
| HTTP GET tới `/ws` | Servlet `SecurityFilterChain` | Có cho yêu cầu kết nối HTTP đi qua không? |
| HTTP Upgrade | WebSocket handshake pipeline | Protocol/origin/upgrade rules |
| STOMP `CONNECT` | Inbound message channel | Thiết lập phiên STOMP, identity, CSRF/command policy |
| STOMP `SEND` | Inbound channel + handler | Ai được gửi tới destination nào? Payload có được thao tác? |
| STOMP `SUBSCRIBE` | Inbound channel + broker | Ai được đăng ký nhận dữ liệu từ destination nào? |
| STOMP `UNSUBSCRIBE` | Inbound channel | Dừng một subscription; lifecycle rules |
| STOMP `DISCONNECT` | Inbound channel/lifecycle | Kết thúc session và cleanup |
| Broker tạo STOMP `MESSAGE` | Outbound channel | Delivery tới subscriber đã được phép và đúng room/user |
| App đọc database khi xử lý SEND | Service/repository | Quyền trên tài nguyên và tenant thật |

**Tầng transport chỉ là cửa vào.** Một người đã đăng nhập vẫn có thể thiếu quyền gửi tin nhắn, xem phòng riêng, gửi thông báo toàn công ty hoặc nhận dữ liệu tenant khác.

## 3. Các thành phần Spring cần nhận diện

| API/thành phần | Stack | Vai trò |
| --- | --- | --- |
| `HttpSecurity` và `SecurityFilterChain` | Spring Security Servlet | Bảo vệ HTTP handshake/SockJS transport requests |
| `@EnableWebSocketMessageBroker` | Spring Framework WebSocket STOMP | Bật STOMP message broker infrastructure |
| `StompEndpointRegistry` | Spring Framework | Đăng ký endpoint HTTP/WebSocket như `/ws` |
| `MessageBrokerRegistry` | Spring Framework | Application/broker/user destination prefixes |
| `@MessageMapping` | Spring Messaging | Xử lý inbound SEND gửi tới application prefix |
| `SimpMessagingTemplate` | Spring Messaging | Ứng dụng gửi thông điệp tới broker hoặc user |
| `clientInboundChannel` | Spring Messaging | Nơi các message **từ client đi vào** được xử lý |
| `clientOutboundChannel` | Spring Messaging | Nơi message đi từ broker/application ra client |
| `ChannelInterceptor` | Spring Messaging | Chặn/biến đổi inbound message, có thể làm auth tùy biến |
| `@EnableWebSocketSecurity` | Spring Security Messaging | Bật authorization/security integration cho STOMP |
| `AuthorizationManager<Message<?>>` | Spring Security Messaging | Quyết định cấp quyền cho từng inbound Message |
| `MessageMatcherDelegatingAuthorizationManager.Builder` | Spring Security Messaging | Định tuyến chính sách theo type/destination |
| `SimpMessageType` | Spring Messaging | MESSAGE, SUBSCRIBE, CONNECT, DISCONNECT... |
| `StompHeaderAccessor` | Spring Messaging | Đọc command/destination/user/session metadata |

### Không lẫn WebSocket STOMP với raw WebSocket

Spring Security WebSocket messaging authorization trong tài liệu chính thức là tích hợp với **Spring Messaging/STOMP**. Nếu ứng dụng dùng raw `WebSocketHandler`, Jakarta WebSocket/JSR-356, Socket.IO hay một giao thức message tùy biến, **không mặc định** `@EnableWebSocketSecurity` sẽ tự chặn mọi payload của các công nghệ đó. Raw WebSocket cần kiểm tra mỗi message theo kiến trúc riêng.

Bài này tập trung vào **Spring MVC/Servlet + STOMP-over-WebSocket**, đúng phạm vi tài liệu `Spring Security — WebSocket Security`. Một ứng dụng thuần WebFlux với `WebSocketHandler` không thể copy nguyên `HttpSecurity`/Servlet message broker configuration và mong nó hoạt động tương đương.

## 4. HTTP handshake xác thực cái gì?

Trình duyệt mở kết nối:

```http
GET /ws HTTP/1.1
Host: app.example.test
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <base64-client-key>
Origin: https://app.example.test
Cookie: SESSION=<session-cookie>
```

Đây là **request minh họa**, không phải đoạn HTTP đầy đủ có thể copy gửi như API thông thường. Trình duyệt có thể tự gửi cookie theo chính sách cookie/origin tương ứng; server vẫn phải xác thực và kiểm tra origin.

Nếu ứng dụng sử dụng login session hoặc HTTP authentication, Spring Security xác định `Principal` tại HTTP request. Theo Spring Framework, WebSocket session có thể **kế thừa authenticated user của HTTP handshake**, để STOMP messages về sau mang user trong Spring message header.

Ví dụ HTTP security:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HandshakeHttpSecurity {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/ws", "/ws/**").authenticated()
                .anyRequest().denyAll()
            );
        return http.build();
    }
}
```

Đây là **một cấu hình ứng dụng Servlet Spring Security**, cần cơ chế login/session/HTTP authentication thật và endpoint `/ws`. Nó chỉ thể hiện **HTTP authorization**; không chứa `AuthorizationManager<Message<?>>`. Một request khác ngoài `/ws` sẽ bị DENY trong chain này trừ khi ứng dụng thêm các rule phù hợp.

### Handshake thành công khẳng định điều gì?

Với cấu hình trên, nó cho biết request đã qua **điều kiện HTTP** và handshake WebSocket hợp lệ về mặt protocol. Nó **không** tự khẳng định:

- Caller có role `CHAT_USER`/`ADMIN` cho mọi STOMP destination.
- Caller có quyền SUBSCRIBE vào `/topic/tenants/B`.
- Caller có quyền SEND vào `/topic/system`.
- JSON payload không chứa người gửi giả.
- User còn membership khi stream chạy sau 30 phút.
- Broker sẽ lọc mọi outbound message theo ACL.

## 5. STOMP CONNECT là một frame riêng, không phải HTTP handshake

Sau khi WebSocket mở, client có thể gửi:

```text
CONNECT
accept-version:1.2
heart-beat:10000,10000

^@
```

Server trả, nếu kết nối STOMP được chấp nhận:

```text
CONNECTED
version:1.2

^@
```

Một frame CONNECT có thể đi kèm CSRF token ở native STOMP headers tùy cấu hình Spring Security và auth model. **STOMP CONNECT không phải HTTP GET Upgrade** và cũng **không phải lệnh OAuth2 token exchange**.

### STOMP login/passcode có xác thực browser user không?

Spring Framework giải thích rằng STOMP có các header `login` và `passcode` vốn xuất phát từ STOMP-over-TCP. Nhưng với STOMP over WebSocket trong cấu hình mặc định, Spring **không tự dùng hai header ấy để xác thực user**, mà mong đợi user đã được xác thực ở HTTP handshake và được truyền trong WebSocket session.

Vì vậy một client gửi:

```text
CONNECT
login:alice
passcode:my-password

^@
```

**không có nghĩa** Spring Security tự xác minh `alice` trong ứng dụng WebSocket. Nếu muốn cơ chế xác thực tại STOMP CONNECT, cần một **trusted authentication ChannelInterceptor** và phân tích token/credentials bằng hệ thống xác thực hợp lệ.

Không bao giờ lấy `login`/`passcode` hoặc `X-User-Id` từ STOMP headers rồi gắn vào principal mà không xác minh.

## 6. SEND, SUBSCRIBE và MESSAGE có ý nghĩa khác nhau

| STOMP command / Spring type | Ai khởi tạo trong tình huống điển hình? | Ý nghĩa bảo mật |
| --- | --- | --- |
| `CONNECT` | Client | Khai báo bắt đầu phiên STOMP |
| `SUBSCRIBE` | Client | Xin được nhận messages từ destination |
| `SEND`, thường ánh xạ `SimpMessageType.MESSAGE` inbound | Client | Gửi payload tới application/broker |
| `MESSAGE` outbound | Broker/application | Chuyển payload cho subscriber |
| `UNSUBSCRIBE` | Client | Dừng subscription |
| `DISCONNECT` | Client hoặc lifecycle xử lý | Kết thúc session |
| `HEARTBEAT` | Hai phía | Giữ kết nối; không đại diện business action |

Trong `MessageMatcherDelegatingAuthorizationManager`, `simpMessageDestMatchers(...)` thường dành cho inbound `SimpMessageType.MESSAGE`, tức message từ client gửi tới một destination. `simpSubscribeDestMatchers(...)` là matcher dành riêng cho SUBSCRIBE. `simpDestMatchers(...)` kiểm tra destination **không phân biệt message type**.

**Lỗi thường gặp:** cho `SUBSCRIBE /topic/system` thì vô tình cho cả `SEND /topic/system` bởi dùng matcher quá rộng, khiến client giả mạo thông báo hệ thống.

## 7. /app, /topic, /queue, /user: destination không phải URL HTTP

Một cấu hình STOMP phổ biến:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class MessagingTransportConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry
            .addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.test");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
    }
}
```

Đây là **Spring Boot STOMP infrastructure class**: cần `spring-boot-starter-websocket`, messaging dependencies và một server HTTP. Domain `app.example.test` chỉ là ví dụ. Quy tắc origin phải đúng các website được phép; không copy `*` vào production. Cấu hình không tạo controller hoặc tài nguyên chat tự động.

### Ý nghĩa các prefix

- `/ws`: **HTTP endpoint** cho handshake, *không* phải một STOMP destination để client SEND business message.
- `/app/**`: client gửi tới handler trong ứng dụng, ví dụ `@MessageMapping("/chat.send")`.
- `/topic/**`: broker destination hay dùng cho broadcast/many subscribers.
- `/queue/**`: broker destination thường dùng cho point-to-point/queue semantics (phụ thuộc broker).
- `/user/**`: Spring user-destination abstraction, chuyển tới destination riêng cho user/session, như `/user/queue/messages`.

Một ứng dụng có thể chọn prefix khác, vì đây là **cấu hình**, không phải các path cố định của giao thức STOMP. Một broker relay bên ngoài có topology và permission model khác simple in-memory broker.

### Bảng ví dụ theo cấu hình trên

| Đường/đích | Loại | Tác dụng dự kiến |
| --- | --- | --- |
| `GET /ws` | HTTP handshake | Mở kết nối transport |
| `SEND /app/chat.send` | STOMP message | Gọi `@MessageMapping("/chat.send")` |
| `SUBSCRIBE /topic/public` | STOMP subscription | Nhận broadcast công khai theo chính sách |
| `SUBSCRIBE /topic/rooms/42` | STOMP subscription | Nhận phòng 42, cần kiểm membership/ACL |
| `SUBSCRIBE /user/queue/messages` | STOMP subscription | Nhận queue user riêng |
| `SEND /topic/system` | STOMP message | **Phải từ chối client** nếu đây là kênh server-only |
| `SUBSCRIBE /queue/**` | STOMP subscription | Thường nên deny direct broker queues ngoại trừ trường hợp được chứng minh |
| `SEND /user/**` | STOMP message | Không mặc định cho phép giả lập người gửi/recipient |

**Ranh giới bảo mật:** việc một destination được Spring broker nhận dạng **không tự có nghĩa user được phép subscribe hay send**. Broker routing và message authorization là hai nhiệm vụ khác nhau.

## 8. Spring Security bảo vệ những message nào?

Tài liệu Spring Security nêu rõ tích hợp STOMP security **chặn ở `clientInboundChannel`**. Nó **không cố bảo vệ tất cả outgoing messages tại `clientOutboundChannel`**, phần lớn vì chi phí và lượng message outbound thường rất lớn.

Vì vậy:

```text
Client SEND/SUBSCRIBE
      |
      v
clientInboundChannel
      |
      +--> Authentication/SecurityContext setup
      +--> AuthorizationChannelInterceptor
      |
      v
@MessageMapping / message broker
      |
      v
clientOutboundChannel
      |
      v
WebSocket client
```

**Hệ quả quan trọng:** phải bảo vệ subscription **trước khi** đăng ký; đồng thời nguồn ứng dụng **phải gửi đúng dữ liệu cho đúng đích**. Nếu một service publish private data vào `/topic/public`, inbound subscription guard không biến nội dung đó thành private.

Cũng cần xác định yêu cầu revoke:

- Lúc Alice subscribe vào phòng A, quyền được kiểm tra.
- Sau đó admin xóa Alice khỏi phòng.
- Một subscription đang sống **không tự bị Spring Security chấm dứt theo ACL mới** chỉ vì data permission đã đổi.
- Nếu nghiệp vụ cần revoke trong vài giây, ứng dụng phải thiết kế unsubscribe/disconnect/revalidation và routing phù hợp.

Không mô tả WebSocket/STOMP message authorization như một firewall tự lọc từng outbound byte theo user ACL.

## 9. @EnableWebSocketSecurity và AuthorizationManager<Message<?>>

Từ Spring Security 5.8, Spring Security WebSocket authorization có thể dùng API `AuthorizationManager`. Mẫu Java Config:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class StompMessageSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            // CONNECT, DISCONNECT, HEARTBEAT... thường không có destination.
            .nullDestMatcher().authenticated()

            // Chỉ những inbound SEND tới application handler này.
            .simpMessageDestMatchers("/app/chat.send")
                .hasAuthority("CHAT_SEND")

            // Người đã đăng nhập được nhận một kênh system public-to-users.
            .simpSubscribeDestMatchers("/topic/public")
                .authenticated()

            // User destination: không cho đăng ký trực tiếp broker queue raw.
            .simpSubscribeDestMatchers("/user/queue/messages")
                .authenticated()

            // Chặn mọi inbound SEND/SUBSCRIBE chưa được cấp tường minh.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()

            // Chặn các message types còn lại nếu không match phía trước.
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

**Đây là class cấu hình Spring Security**, không chạy riêng bằng `javac` vì cần Spring Framework/Messaging/Security dependencies và broker configuration. Cùng với `MessagingTransportConfig` ở mục trước và HTTP security, nó minh họa **ba lớp riêng**.

Phân tích:

1. `@EnableWebSocketSecurity` bật integration kiểm soát inbound messages.
2. `AuthorizationManager<Message<?>>` đánh giá theo message type/destination.
3. `nullDestMatcher().authenticated()` bảo vệ những message không có destination (bao gồm CONNECT, DISCONNECT tùy pipeline). **Spring Security vẫn có CSRF requirement cho CONNECT theo cấu hình tương ứng**.
4. `simpMessageDestMatchers("/app/chat.send")` dành cho SEND/MESSAGE inbound tại application destination; yêu cầu `CHAT_SEND`.
5. `simpSubscribeDestMatchers("/topic/public")` cấp SUBSCRIBE, **không tự cấp quyền SEND** đến `/topic/public`.
6. `/user/queue/messages` là user destination; Spring chuyển thành đích theo session/user, nhưng nghiệp vụ vẫn phải bảo đảm server gửi dữ liệu thuộc user tương ứng.
7. `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` chặn SEND vào `/topic/**` hoặc SUBSCRIBE vào room chưa khai báo.
8. `anyMessage().denyAll()` bảo đảm policy fail closed với message type không được chấp nhận.

**Đặc biệt:** ví dụ này chưa cấp subscription vào rooms private. Không thêm `.simpSubscribeDestMatchers("/topic/rooms/**").authenticated()` một cách vô điều kiện, vì điều đó chỉ chứng minh user có tài khoản, **không chứng minh membership của room**.

### Tại sao rule thứ tự quan trọng?

Các builder matchers được xét theo thứ tự đã đăng ký; rule đặc thù phải đứng trước catch-all.

**Sai:**

```java
messages
    .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll()
    .simpSubscribeDestMatchers("/topic/public").authenticated();
```

Rule SUBSCRIBE đầu quá rộng làm public subscribe bị deny. Tương tự, nếu một rule `simpDestMatchers("/**").permitAll()` đứng trước deny, nhiều frame có destination có thể vượt các kiểm tra cụ thể. Đặt default deny ở cuối.

### Không áp rule HTTP vào STOMP destination

`http.authorizeHttpRequests(...requestMatchers("/topic/**")...)` chỉ match **HTTP URLs**, không match STOMP destination `/topic/**` bên trong một kết nối WebSocket. Đừng tưởng `anyRequest().denyAll()` của HTTP sau handshake sẽ chặn client gửi `SEND /topic/system`.

## 10. Cách tổ chức quyền theo STOMP message type và destination

Một ma trận quyền có thể như sau:

| Inbound frame | Destination | Quyền cần | Kết quả |
| --- | --- | --- | --- |
| CONNECT | none | Authenticated HTTP principal + CSRF/identity policy | Chấp nhận hoặc từ chối |
| SEND | `/app/chat.send` | CHAT_SEND + room membership trong service | Cho xử lý nếu đủ |
| SEND | `/topic/public` | Không cho client publish trực tiếp | DENY |
| SEND | `/topic/system` | Kênh server-only | DENY |
| SUBSCRIBE | `/topic/public` | Authenticated | ALLOW |
| SUBSCRIBE | `/topic/rooms/42` | Member của room 42 / đúng tenant | Chỉ ALLOW nếu kiểm chứng |
| SUBSCRIBE | `/topic/rooms/99` | Không membership | DENY |
| SUBSCRIBE | `/user/queue/messages` | Authenticated + user routing phù hợp | ALLOW |
| SUBSCRIBE | `/queue/internal` | Không cho raw broker subscription | DENY |
| SEND | `/app/admin.command` | Admin app action + data/context policy | Policy riêng |
| SUBSCRIBE | `/app/chat.send` | Application handler không phải broadcast stream | DENY |
| UNSUBSCRIBE | no destination | Lifecycle policy | Cho nếu session phù hợp |
| DISCONNECT | no destination | Cleanup idempotent | Theo session policy |

Một app có thể chọn quy tắc CONNECT và disconnect khác; **không dùng permitAll toàn bộ inbound** chỉ để giảm lỗi test. Quy tắc public ở đây có nghĩa "cho mọi authenticated user" — không phải người vô danh. Nếu ứng dụng cho anonymous public topics, phải thiết kế phiên anonymous, origin, abuse controls và privacy riêng.

## 11. Gắn Principal từ HTTP session vào STOMP

Với Servlet app dùng session login:

```text
1. Alice login qua HTTP -> SecurityContext có user Alice
2. Browser GET /ws gửi session cookie
3. SecurityFilterChain xác minh session và Principal
4. Spring WebSocket gắn Principal với session
5. Các inbound STOMP Message mang simpUser của Alice
6. Message authorization dùng Authentication/GrantedAuthority
7. @MessageMapping có thể inject Principal để xác định người gửi
```

Trong handler:

```java
import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {
    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @MessageMapping("/chat.send")
    public void send(ChatInput input, Principal principal) {
        // Dùng verified principal; không tin senderId do client khai.
        chatService.sendFromAuthenticatedUser(
            principal.getName(),
            input.roomId(),
            input.text()
        );
    }
}
```

Đây là **component fragment**: `ChatService` và `ChatInput` là domain types phải định nghĩa; cần validate input/size/rate limits và đọc quyền room tenant ở service. `Principal.getName()` có thể là username, không nhất thiết là stable user ID; dùng identity mapper đáng tin nếu ứng dụng có nhiều issuer/tenants.

Nếu client gửi `{"senderId":"admin", "text":"..."}` trong payload, ứng dụng **không** được tin `senderId` làm người gửi. Gán sender từ `Principal` đã xác minh; nếu service impersonation hợp lệ, phải có quy trình ủy quyền và audit riêng.

## 12. Token-based authentication ở STOMP CONNECT: trường hợp đặc biệt

Ứng dụng không dùng cookie session, ví dụ mobile client với JWT hoặc SPA muốn token-only WebSocket, có thể gặp khó khăn: browser `WebSocket` API **không cho set tùy ý HTTP Authorization header** cho native handshake giống `fetch`. SockJS browser client cũng có hạn chế về request headers.

Spring Framework mô tả một hướng: gửi token bằng **STOMP CONNECT native headers** rồi xác minh tại `ChannelInterceptor`:

```text
Client: WebSocket handshake (transport)
   -> STOMP CONNECT with Authorization: Bearer ...
   -> server interceptor validates JWT and sets authenticated user
   -> Spring Security message AuthorizationManager evaluates
```

Đây là một **kiến trúc khác với HTTP-session authentication**. Không thể đồng thời yêu cầu `GET /ws` HTTP authenticated bằng JWT header không gửi được từ browser, rồi mong token ở STOMP CONNECT cứu được handshake. Phải thiết kế HTTP handshake policy chấp nhận transport theo trust boundary, sau đó **chặn mọi business messages đến khi CONNECT token được xác minh**.

### ChannelInterceptor xác thực CONNECT

Cấu trúc minh họa:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.core.Authentication;

public final class StompConnectAuthInterceptor
        implements ChannelInterceptor {

    private final TrustedStompTokenVerifier verifier;

    public StompConnectAuthInterceptor(TrustedStompTokenVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public Message<?> preSend(
            Message<?> message, MessageChannel channel) {

        StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message, StompHeaderAccessor.class);

        if (accessor != null
                && StompCommand.CONNECT.equals(accessor.getCommand())) {

            String bearer = accessor.getFirstNativeHeader("Authorization");
            Authentication trusted = verifier.verifyBearer(bearer);

            if (trusted == null || !trusted.isAuthenticated()) {
                throw new org.springframework.security.access
                    .AccessDeniedException("STOMP authentication failed");
            }
            accessor.setUser(trusted);
        }

        return message;
    }
}
```

**Đây là Spring component fragment**, cần `TrustedStompTokenVerifier` do ứng dụng triển khai dùng JWT decoder/issuer/audience/expiry validation thực, không phải code tự chạy. Trong production phải kiểm tra token type, scopes, revoked accounts, principal mapping và trả lỗi không lộ credentials. Nếu không xác minh được, không cho frame đi tiếp.

### Thứ tự interceptor là vấn đề bảo mật

Spring Framework ghi rõ custom authentication `ChannelInterceptor` cần chạy **trước** Spring Security authorization interceptor trên inbound channel. Có thể đăng ký cấu hình riêng với `@Order(Ordered.HIGHEST_PRECEDENCE + 99)` theo hướng dẫn của Spring Framework; phải chạy integration tests đúng version để bảo đảm `SecurityContextChannelInterceptor` và authorization thấy principal đã xác minh.

Không tự thiết kế một interceptor "đặt user từ token" chạy sau authorization; khi đó authorization có thể thấy anonymous/old principal hoặc chặn sai.

### HTTP handshake công khai có an toàn không?

Nếu handshake `/ws` được permit cho browser để cho phép STOMP token auth, đó **không tự là lỗ hổng cấp quyền business** nếu:

- CONNECT bị bắt buộc có JWT hợp lệ và CSRF/origin policy phù hợp.
- Không business SEND/SUBSCRIBE được xử lý trước khi xác thực.
- Có connection/handshake rate limits, timeouts và tài nguyên giới hạn.
- Không có alternate code path bỏ qua inbound interceptor.
- Không dùng `permitAll()` cho toàn bộ message rules.

Nhưng chính sách này tăng bề mặt DoS/connection exhaustion; nếu có thể authenticate ở handshake đáng tin, thường sẽ đơn giản hơn.

### Tránh token trên query string

URL như `wss://.../ws?token=...` có rủi ro token lọt vào access logs, tracing, browser history, referrer hoặc proxy logs tùy môi trường. Không chọn query token chỉ vì dễ làm; nếu bắt buộc, dùng credential cực ngắn hạn, một lần, scoped rõ và log redaction, theo threat model. Với session cookies, cần SameSite/CSRF/origin policy để chống cross-site hijacking.

## 13. Same Origin, CORS và WebSocket khác nhau

Một hiểu nhầm phổ biến: browser tự áp Same Origin Policy cho WebSocket giống như `fetch`.

Spring Security nhấn mạnh **WebSocket không tự được trình duyệt bảo vệ bởi Same Origin Policy giống XMLHttpRequest/fetch**. Một website độc hại có thể thử mở WebSocket đến domain của ứng dụng, và cookies có thể được trình duyệt gửi theo các quy tắc cookie tương ứng. Đây là nền tảng của **Cross-Site WebSocket Hijacking (CSWSH)**.

Phòng vệ:

1. **Origin allowlist** tại STOMP handshake endpoint, chỉ các origin có quyền sử dụng.
2. **CSRF token trong STOMP CONNECT** theo Spring Security WebSocket integration khi dùng session/cookie.
3. Cookie `SameSite`, `Secure`, `HttpOnly` và session management phù hợp.
4. Authentication và authorization cho CONNECT/SEND/SUBSCRIBE.
5. Không nhầm CORS policy HTTP thông thường với toàn bộ WebSocket origin policy.
6. Không dùng `setAllowedOrigins("*")` cho endpoint nhạy cảm.
7. Kiểm tra reverse proxy/gateway có giữ/kiểm tra origin và TLS thật không.

### CSRF tại CONNECT

Tài liệu Spring Security nêu rằng khi sử dụng `@EnableWebSocketSecurity`, inbound STOMP `CONNECT` được yêu cầu CSRF token theo cách bảo vệ same-origin. Client có thể lấy token từ một endpoint HTTP được bảo vệ, sau đó gửi dưới native STOMP header khi CONNECT.

Ví dụ minh họa client:

```javascript
const token = await obtainCsrfTokenFromTrustedHttpEndpoint();
const headers = {};
headers[token.headerName] = token.token;
stompClient.connect(headers, onConnected, onError);
```

Đây là **client pseudocode**; `obtainCsrfTokenFromTrustedHttpEndpoint` phải được xây dựng đúng origin/session/auth; API kết nối STOMP cụ thể phụ thuộc client library/version. Mục đích là cho thấy CSRF header được gửi trong **STOMP CONNECT**, không phải tự động trong HTTP Upgrade.

**Không** xem việc tắt HTTP CSRF trên `/ws/**` đồng nghĩa tắt CSRF cho STOMP CONNECT. Đó là hai điểm kiểm soát khác nhau.

### SockJS

SockJS fallback có thể sử dụng nhiều HTTP requests (kể cả POST) cho transport. Spring Security docs đề cập có trường hợp phải **nới HTTP CSRF tại đúng SockJS connect path**, trong khi giữ **STOMP CONNECT CSRF**; một số fallback dùng iframe, cần security header `X-Frame-Options: SAMEORIGIN` nếu được phép.

Không tắt CSRF toàn ứng dụng chỉ để "SockJS hoạt động". Với `@EnableWebSocketSecurity`, khả năng cấu hình/tắt STOMP CONNECT CSRF khác nhau theo Spring Security version; tài liệu chính thức ở dòng 7.1 vẫn ghi không cấu hình trực tiếp việc tắt qua annotation, và có hướng cấu hình thủ công khi buộc phải làm. Tránh tự viết lời khuyên tắt CSRF nếu không có phân tích same-origin/CSWSH nghiêm túc.

## 14. /topic không phải nơi client được tùy ý SEND

Một trường hợp kinh điển:

```text
Server muốn phát:
  MESSAGE /topic/system -> "System maintenance at 2AM"

Attacker có WebSocket authenticated gửi:
  SEND /topic/system -> "Click malicious link now"
```

Nếu broker nhận SEND trực tiếp tới `/topic/system`, attacker có thể giả mạo thông báo hệ thống mà không đi qua `@MessageMapping` kiểm tra nghiệp vụ.

Quy tắc Spring Security khuyến nghị: **deny mọi client inbound MESSAGE gửi đến broker prefix** `/topic/**`, `/queue/**`, trừ các ngoại lệ cực kỳ cụ thể đã được bảo vệ.

Thay vào đó client gửi:

```text
SEND /app/chat.send
{"roomId":"42","text":"Xin chào"}
```

`@MessageMapping("/chat.send")` nhận request, xác minh sender/room membership/rate limit, tạo message server-side, rồi dùng `SimpMessagingTemplate.convertAndSend("/topic/rooms/42", ...)` nếu đúng quyền.

**Lưu ý:** `@MessageMapping` không tự bảo vệ khỏi việc client dùng ownerId/roomId giả. Nó là routing point; cần domain policy.

## 15. SUBSCRIBE vào private topic: kiểm tra object-level permission

Một user ở tenant A thử:

```text
SUBSCRIBE
id:sub-secret
destination:/topic/tenants/B/rooms/99

^@
```

Một rule `simpSubscribeDestMatchers("/topic/**").authenticated()` chỉ yêu cầu user có Authentication hợp lệ. Nó **không** biết user thuộc tenant B hay room 99. Đó là lỗi BOLA/IDOR ở message subscription layer.

Cần chính sách kiểu:

```text
ALLOW SUBSCRIBE /topic/tenants/{tenant}/rooms/{room} nếu
   authenticated principal
   AND verified membership(subject, tenant)
   AND room.tenantId == tenant
   AND active room membership / ACL
   AND room not deleted or locked
   AND subscription policy allows current context
```

Đối với broker chung, một unauthorized SUBSCRIBE có thể làm rò **mọi message sau đó** của topic, không chỉ một HTTP response.

### Custom authorization manager

Một hướng là viết `AuthorizationManager<Message<?>>` riêng và gắn vào matcher `simpSubscribeDestMatchers(...)`:

```java
@Bean
AuthorizationManager<Message<?>> privateRoomAuthorization(
        RoomSubscriptionPolicy policy) {

    return (authenticationSupplier, message) -> {
        Authentication auth = authenticationSupplier.get();

        SimpMessageHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message, SimpMessageHeaderAccessor.class);

        String destination = accessor == null
            ? null : accessor.getDestination();

        boolean allowed = auth != null
            && auth.isAuthenticated()
            && policy.canSubscribe(auth, destination);

        return new org.springframework.security.authorization
            .AuthorizationDecision(allowed);
    };
}
```

Đây là **Spring configuration fragment**, cần imports `Message`, `Authentication`, `AuthorizationManager`, `SimpMessageHeaderAccessor`, và `RoomSubscriptionPolicy` là service ứng dụng. `policy.canSubscribe` phải parse destination an toàn, tải room thật từ server, verify tenant/room membership, explicit deny khi không có bằng chứng. Đối với API Spring Security 7, `AuthorizationDecision` là một `AuthorizationResult` hợp lệ và method `authorize(...)` được dùng; code trên viết theo target typing của interface tương ứng, cần biên dịch theo dependency version thực.

Kết hợp vào builder:

```java
messages
    .simpSubscribeDestMatchers(
        "/topic/tenants/{tenant}/rooms/{roomId}"
    ).access(privateRoomAuthorization)
    .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
```

Đây là **fragment** của bean `messageAuthorizationManager`, không viết thành bean xung đột với cấu hình có `@EnableWebSocketSecurity` mà chưa hợp nhất rule. Cần kiểm tra destination extraction/version/path variables thực tế, và đảm bảo custom policy không tin String tenant từ destination như bằng chứng membership.

### Blocking database access trong manager

Servlet/STOMP inbound channel thường chạy qua thread executor của Spring Messaging, nhưng **không có nghĩa** bạn được phép tra JDBC nặng không giới hạn trên mỗi SUBSCRIBE. Xem xét DB pool, timeout, cache/revocation, bounded queue và rate limits; khi muốn dùng non-blocking data source, đừng gọi `Mono.block()` bừa bãi trong pipeline. `AuthorizationManager<Message<?>>` là abstraction quyết định dạng đồng bộ ở phiên bản này; nếu permission store chỉ có reactive API, cần thiết kế bridge/boundary rõ thay vì giả vờ message AuthorizationManager tự reactive.

Ở ứng dụng WebFlux raw WebSocket, cách bảo vệ mỗi message có thể khác và dùng Reactor operators; không bê nguyên Spring STOMP manager từ Servlet vào.

## 16. User destination và tránh đọc queue của người khác

Spring Framework hỗ trợ `/user/**` để ánh xạ subscription vào destination đặc thù cho user hoặc session.

Ví dụ:

```text
Client Alice subscribes:
  /user/queue/messages

Server sends:
  convertAndSendToUser("alice", "/queue/messages", payload)

Spring routes to:
  an internal queue destination unique to Alice's session(s)
```

Cụ thể internal destination name phụ thuộc implementation, có thể chứa session ID. **Không** đặt tên internal queue đã dịch thành API công khai để client tùy ý SUBSCRIBE.

Quy tắc thường dùng:

- Cho user SUBSCRIBE `/user/queue/messages` sau khi authenticated.
- Deny client SUBSCRIBE trực tiếp `/queue/**` trừ exception được review.
- Không cho client SEND trực tiếp tới `/user/**` nếu không có business command policy.
- Khi dùng `convertAndSendToUser`, recipient ID phải được server xác minh và đúng ngữ cảnh.
- Khi client có nhiều sessions/tabs, hiểu cơ chế phát tới nhiều session và yêu cầu giới hạn dữ liệu.

**Cảnh báo:** bảo vệ user destination routing **không tự bảo vệ payload** nếu application gửi thông tin của Bob vào queue Alice. Publisher/service vẫn phải kiểm tra đúng recipient, tenant và dữ liệu.

## 17. Vì sao outbound không được Spring Security kiểm soát tự động?

Theo tài liệu Spring Security, WebSocket message security không bảo vệ `clientOutboundChannel` theo cách chặn inbound, phần lớn do hiệu suất.

Giả sử user Alice có một subscription đang được phép vào `/topic/rooms/42`. Khi admin revoke Alice khỏi room, một số message mới có thể vẫn đi tới subscription cũ nếu hệ thống không xử lý revoke. Điều đó không mâu thuẫn với việc inbound `SUBSCRIBE` ban đầu đã được phép: quyền đã **thay đổi sau đó**.

Các chiến lược:

1. **Re-evaluate khi subscribe**; phù hợp cho quyền tương đối ổn định và session ngắn.
2. **Short-lived subscriptions / reconnect lease**; buộc refresh permission định kỳ.
3. **Revoke event-driven**; khi membership/ACL đổi, chủ động unsubscribe/close sessions liên quan.
4. **App-layer fanout per authorized recipient**; chỉ gửi đến những user đã xác minh ở thời điểm publish.
5. **Topic partition theo tenant/resource** với broker ACL phù hợp nếu dùng external broker.
6. **Data minimization**; tránh publish private payload vào broad public topic.
7. **Invalidate cached permission** khi user rời tenant/room.

Các phương án có trade-off độ trễ, sức tải và consistency. Cần công bố SLA revoke (ví dụ tối đa 30 giây) và **kiểm thử trên kết nối đang sống**, không chỉ kết nối mới.

### Một lỗ hổng vẫn có thể xảy ra dù inbound guard đúng

```text
Alice SUBSCRIBE /topic/public -> ALLOW
Server mistakenly publishes payroll data to /topic/public
Alice receives payroll data
```

Message authorization không cứu được nếu **ứng dụng publish sai destination**. Dữ liệu nhạy cảm cần user-/tenant-scoped publishing và output policy đúng, không chỉ subscription auth.

## 18. @MessageMapping cần kiểm tra business action

Một STOMP SEND có thể kích hoạt side effects: tạo chat message, chỉnh trạng thái đơn hàng, chuyển tiền, gửi lời mời, phê duyệt công việc.

Ví dụ ứng dụng:

```java
@Controller
public class RoomMessageController {
    private final RoomService rooms;
    private final SimpMessagingTemplate messaging;

    public RoomMessageController(
            RoomService rooms, SimpMessagingTemplate messaging) {
        this.rooms = rooms;
        this.messaging = messaging;
    }

    @MessageMapping("/rooms.post")
    public void post(RoomPostRequest request, Principal principal) {
        var actor = rooms.verifyAuthenticatedActor(principal);
        var room = rooms.requireWritableRoom(
            actor, request.tenantId(), request.roomId());

        var saved = rooms.saveMessage(
            room, actor, request.text());

        messaging.convertAndSend(
            "/topic/tenants/" + room.tenantId()
                + "/rooms/" + room.id(),
            saved.toClientDto());
    }
}
```

Đây là **fragment ứng dụng**: `RoomService`, `RoomPostRequest`, `RoomPostRequest.tenantId()`, `saved.toClientDto()` đều là domain APIs cần triển khai. `Principal` đã xác minh bởi session/CONNECT auth; tên username phải được map về stable subject ID nếu cần. Input cần validation, giới hạn độ dài và chống HTML/script injection tùy client rendering.

Quy trình đúng:

1. Chỉ cho inbound SEND đến `/app/rooms.post` qua message manager.
2. Xác minh principal/tenant membership/room permission ở **service**.
3. Đọc resource thật và kiểm trạng thái room.
4. Ghi database trong transaction thích hợp.
5. Chỉ sau thành công publish tới destination đúng tenant/resource.
6. Nếu cần exactly-once/idempotency hoặc transaction boundary với message broker, dùng outbox/retry protocol phù hợp.

Không chỉ dựa vào `hasAuthority('CHAT_SEND')` để cho phép gửi tới **mọi** room. Quyền chức năng và resource-level entitlement cần phối hợp.

## 19. Nếu message có "sender", hãy lấy từ Principal

Payload từ client:

```json
{
  "senderId": "admin",
  "tenantId": "tenant-a",
  "roomId": "42",
  "text": "Tin nhắn cần gửi"
}
```

Kẻ tấn công có thể đổi `senderId` và `tenantId`. Server không được tin những field này làm căn cứ phân quyền.

Thiết kế:

```text
actorId = verified Principal / Authentication mapping
requestedTenantId = selector from payload/destination
room = DB lookup by requested room ID + verified tenant scope
ALLOW only if actor has active membership and SEND action
persist senderId=actorId (never senderId from client)
publish DTO with server-proven senderId
```

Một `roomId` dạng UUID khó đoán vẫn không thay thế object-level access check. Tương tự, nếu attacker đoán được user destination nội bộ, raw `/queue/**` subscription phải bị chặn thay vì dựa vào tên queue khó đoán.

## 20. HTTP CSRF và STOMP CONNECT CSRF không thể thay nhau

Với form/cookie session, HTTP CSRF bảo vệ các HTTP state-changing requests. WebSocket handshake thường dùng HTTP GET/Upgrade, nhưng client có thể gắn cookie tự động theo browser policy.

Spring Security áp dụng CSRF tại **inbound STOMP CONNECT** để giảm cross-site WebSocket hijacking; token ở **STOMP headers**, không chỉ HTTP request headers.

Nếu dùng SockJS fallback transport với POST, framework có thể yêu cầu điều chỉnh HTTP CSRF matcher cho **connect URLs**; tuy nhiên đừng tắt toàn bộ HTTP CSRF cho các business endpoints. Khi có nhu cầu mở cross-origin WebSocket, phải phân tích rõ origin policy, cookie SameSite và CSRF. "CORS enabled" không đồng nghĩa CSWSH đã được giải quyết.

### Cách test CSRF

- Browser đúng origin, có session và STOMP CONNECT CSRF hợp lệ → kết nối STOMP thành công.
- Browser đúng origin nhưng thiếu/CSRF sai → không được quyền CONNECT khi policy yêu cầu.
- Origin không trong allowlist → handshake bị từ chối ở transport.
- Attacker dùng STOMP login/passcode giả → không trở thành Alice.
- SockJS fallback → test transport-specific path và HTTP CSRF exception có phạm vi hẹp.
- Kết nối tồn tại nhưng gửi SEND không có role → STOMP authorization vẫn từ chối.

Không sửa lỗi "CONNECT denied" bằng cách mở `permitAll()` cho mọi inbound MESSAGE.

## 21. Phân biệt lỗi: HTTP 401/403 khác STOMP ERROR và connection close

Trong HTTP REST, client quen nhìn status `401`, `403`, `404`. Nhưng sau WebSocket Upgrade, frame STOMP không có HTTP response code cho từng SEND/SUBSCRIBE.

Các tín hiệu có thể quan sát:

| Giai đoạn | Kết quả khi bị từ chối | Khác biệt |
| --- | --- | --- |
| HTTP handshake chưa upgrade | 401/403/3xx tùy entry point/origin | Vẫn là HTTP |
| STOMP CONNECT | ERROR frame hoặc connection đóng tùy cấu hình | Không phải HTTP 403 mới |
| STOMP SEND | ERROR/close/handling failure tùy broker/framework | Phải test **không side effect** |
| STOMP SUBSCRIBE | Subscription không được chấp nhận, có thể ERROR/close | Phải test **không có message trái quyền** |
| STOMP MESSAGE đã phát | Không thể "thu hồi" bytes client đã nhận | Cần revoke policy trước emission |

Không viết test chỉ kỳ vọng `.expectStatus().isForbidden()` sau khi WebSocket đã nâng cấp để chứng minh `SUBSCRIBE` bị chặn. Cần dùng STOMP client, capture ERROR, subscription state, broker outputs và side effects.

Một số client có auto-reconnect. Nếu token/CSRF invalid, reconnect liên tục có thể tạo load; triển khai backoff và không log token. Tách authentication failure, policy deny và hạ tầng broker outage để đo lường.

## 22. Java 17 chạy độc lập: handshake OK vẫn có thể bị STOMP deny

Chương trình sau **không phụ thuộc Spring Security**; nó mô phỏng hai điểm quyết định riêng:

1. HTTP handshake: request có principal đã authenticated và origin được phép.
2. STOMP message: kiểm tra type, destination, role, tenant/room membership, deny direct SEND tới broker.

Mục đích là chứng minh "đã có session" không tương đương "được SUBSCRIBE/SEND tới mọi destination".

Lưu file `HandshakeVsStompAuthorizationDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class HandshakeVsStompAuthorizationDemo {

    enum Type { CONNECT, SEND, SUBSCRIBE, DISCONNECT }

    record User(
        String id,
        boolean authenticated,
        Set<String> roles,
        Set<String> roomKeys
    ) {}

    record Request(
        Type type,
        String destination,
        String tenant,
        String roomId
    ) {}

    static final Set<String> ALLOWED_ORIGINS =
        Set.of("https://app.example.test");

    static boolean handshake(User user, String origin) {
        return user != null && user.authenticated()
            && ALLOWED_ORIGINS.contains(origin);
    }

    static String decision(
            User user,
            boolean websocketEstablished,
            Request req) {

        if (!websocketEstablished || user == null
                || !user.authenticated() || req == null) {
            return "DENY";
        }

        if (req.type() == Type.CONNECT
                || req.type() == Type.DISCONNECT) {
            return "ALLOW";
        }

        if (req.destination() == null
                || req.destination().isBlank()) {
            return "DENY";
        }

        // Direct client SEND to broker destinations is forbidden.
        if (req.type() == Type.SEND
                && (req.destination().startsWith("/topic/")
                 || req.destination().startsWith("/queue/"))) {
            return "DENY";
        }

        if (req.type() == Type.SEND
                && "/app/chat.send".equals(req.destination())) {
            return user.roles().contains("CHAT_SEND")
                && allowedRoom(user, req) ? "ALLOW" : "DENY";
        }

        if (req.type() == Type.SUBSCRIBE
                && "/topic/public".equals(req.destination())) {
            return "ALLOW";
        }

        if (req.type() == Type.SUBSCRIBE
                && "/user/queue/messages".equals(req.destination())) {
            return "ALLOW";
        }

        if (req.type() == Type.SUBSCRIBE
                && req.destination().startsWith("/topic/tenants/")) {
            String expected =
                "/topic/tenants/" + req.tenant()
                    + "/rooms/" + req.roomId();

            return expected.equals(req.destination())
                && allowedRoom(user, req) ? "ALLOW" : "DENY";
        }

        return "DENY";
    }

    static boolean allowedRoom(User user, Request req) {
        if (req.tenant() == null || req.roomId() == null) {
            return false;
        }

        String roomKey = req.tenant() + "|" + req.roomId();
        return user.roomKeys().contains(roomKey);
    }

    static void show(
            String label, User user,
            boolean connected, Request request) {
        System.out.println(label + ": "
            + decision(user, connected, request));
    }

    public static void main(String[] args) {
        User alice = new User(
            "alice", true,
            Set.of("CHAT_SEND"),
            Set.of("tenant-a|42")
        );
        User bob = new User(
            "bob", true,
            Set.of(),
            Set.of("tenant-a|77")
        );
        User guest = new User(
            "guest", false,
            Set.of(), Set.of()
        );

        boolean aliceConnected =
            handshake(alice, "https://app.example.test");

        System.out.println("Alice HTTP handshake: "
            + (aliceConnected ? "ALLOW" : "DENY"));
        System.out.println("Wrong Origin handshake: "
            + (handshake(alice, "https://evil.example.test")
                ? "ALLOW" : "DENY"));
        System.out.println("Guest HTTP handshake: "
            + (handshake(guest, "https://app.example.test")
                ? "ALLOW" : "DENY"));

        show("Alice STOMP CONNECT",
            alice, aliceConnected,
            new Request(Type.CONNECT, null, null, null));
        show("Alice public SUBSCRIBE",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/topic/public", null, null));
        show("Alice own room SUBSCRIBE",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/topic/tenants/tenant-a/rooms/42",
                "tenant-a", "42"));
        show("Alice other room SUBSCRIBE",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/topic/tenants/tenant-a/rooms/77",
                "tenant-a", "77"));
        show("Alice cross-tenant SUBSCRIBE",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/topic/tenants/tenant-b/rooms/42",
                "tenant-b", "42"));
        show("Alice chat SEND",
            alice, aliceConnected,
            new Request(Type.SEND,
                "/app/chat.send", "tenant-a", "42"));
        show("Alice direct broker SEND",
            alice, aliceConnected,
            new Request(Type.SEND,
                "/topic/public", null, null));
        show("Alice private queue SUBSCRIBE",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/queue/private", null, null));
        show("Bob chat SEND no role",
            bob, handshake(bob, "https://app.example.test"),
            new Request(Type.SEND,
                "/app/chat.send", "tenant-a", "77"));
        show("Disconnected Alice SUBSCRIBE",
            alice, false,
            new Request(Type.SUBSCRIBE,
                "/topic/public", null, null));
        show("Unknown destination",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/topic/internal", null, null));
    }
}
```

Biên dịch và chạy JDK 17+:

```bash
javac HandshakeVsStompAuthorizationDemo.java
java HandshakeVsStompAuthorizationDemo
```

Stdout chính xác:

```text
Alice HTTP handshake: ALLOW
Wrong Origin handshake: DENY
Guest HTTP handshake: DENY
Alice STOMP CONNECT: ALLOW
Alice public SUBSCRIBE: ALLOW
Alice own room SUBSCRIBE: ALLOW
Alice other room SUBSCRIBE: DENY
Alice cross-tenant SUBSCRIBE: DENY
Alice chat SEND: ALLOW
Alice direct broker SEND: DENY
Alice private queue SUBSCRIBE: DENY
Bob chat SEND no role: DENY
Disconnected Alice SUBSCRIBE: DENY
Unknown destination: DENY
```

**Giải thích:**

- Alice vượt HTTP handshake vì đã authenticated và origin đúng.
- Điều đó chỉ cho phép thiết lập transport; chính sách room 42/77 vẫn được xét tại STOMP.
- Bob có HTTP session hợp lệ nhưng thiếu `CHAT_SEND` nên không thể gửi chat.
- Gửi trực tiếp `/topic/public` bị từ chối dù Alice được subscribe kênh đó.
- Subscription `/queue/private` không được whitelist nên DENY.
- Tenant B không được dùng membership của tenant A.
- Không có WebSocket đã thiết lập thì không có quyền STOMP trong mô hình.

**Giới hạn minh bạch:** chương trình này không mở socket, không xác thực cookie/JWT, không kiểm CSRF, không phân tích STOMP frames hoặc gọi Spring Messaging. `roomKeys` và `roles` là test fixtures đã "tin cậy" trong bộ nhớ. Trong production phải lấy membership, room state và principal từ nguồn đã xác minh, kiểm token/CSRF/origin theo stack thật và áp quyết định vào `clientInboundChannel`. `Map` được import để minh họa có thể dùng mapping rộng hơn, nhưng demo chỉ cần Set; có thể bỏ import `Map` mà output vẫn không đổi.

## 23. Kiểm thử HTTP handshake: cả allowed lẫn denied

Một integration test không nên chỉ mở WebSocket rồi assert "CONNECTED". Cần ít nhất:

| Handshake scenario | Kỳ vọng |
| --- | --- |
| Alice có session hợp lệ, origin được phép | Upgrade/transport thành công |
| Không có session với endpoint yêu cầu authenticated | 401/redirect/deny theo entry point |
| Session invalid/expired | Không tạo phiên authorized |
| Origin từ website không trong allowlist | Không chấp nhận kết nối |
| Cookie session A dùng từ tenant B trái chính sách | Không cho chuyển tenant chỉ bằng URL |
| Reverse proxy xóa/đổi origin hoặc upgrade headers | Policy vẫn đúng sau deploy |
| SockJS fallback dùng POST | HTTP/CSRF policy theo đúng endpoint, không mở toàn app |
| Browser chưa có authentication nhưng gửi STOMP header | Không vượt được HTTP handshake nếu policy không cho |
| JWT ở query string | Không có token leak trong logs/traces nếu kiến trúc cho phép |
| Handshake flood/concurrent limits | Không cạn connection/thread pool |

Với Spring Boot, một test STOMP có thể dùng `WebSocketStompClient` / `SockJsClient` kết nối tới server chạy thật. `MockMvc` tốt cho HTTP nhưng không thay thế một test **WebSocket Upgrade + STOMP exchange** trên wire. Nếu dùng session authentication, cần cookie/csrf đúng người dùng; nếu dùng STOMP JWT authentication, phải test interceptor order riêng.

## 24. Kiểm thử message authorization: capture frame và side effects

Ma trận tối thiểu:

| Caller | STOMP type | Destination | Kỳ vọng |
| --- | --- | --- | --- |
| Alice | CONNECT | none | Được nếu identity/CSRF policy hợp lệ |
| Anonymous | CONNECT | none | Bị chặn theo chính sách |
| Alice | SEND | `/app/chat.send` | Chỉ được nếu có role và room membership |
| Alice | SEND | `/topic/public` | DENY |
| Alice | SEND | `/topic/system` | DENY |
| Alice | SUBSCRIBE | `/topic/public` | ALLOW theo policy |
| Alice | SUBSCRIBE | `/topic/tenants/A/rooms/42` | ALLOW nếu thuộc room |
| Alice | SUBSCRIBE | `/topic/tenants/B/rooms/42` | DENY nếu không membership B |
| Alice | SUBSCRIBE | `/queue/admin` | DENY |
| Alice | SUBSCRIBE | `/user/queue/messages` | ALLOW, nhận đúng user payload |
| Bob | SUBSCRIBE | `/topic/rooms/42` | DENY nếu không member |
| Bob | SEND | `/app/admin.command` | DENY nếu thiếu admin grant |
| Alice | SEND | `/app/chat.send` với `senderId=admin` | Server vẫn gán actor Alice |
| Alice | SUBSCRIBE | Destination chưa biết | DENY |
| Alice sau revoke | Subscribe mới | DENY |
| Alice sau revoke | Subscription còn sống | Revoke/cancel/delivery policy đúng SLA |

### Assert cần có

- Inbound SEND bị từ chối **không ghi DB và không publish message**.
- Inbound SUBSCRIBE bị từ chối **không nhận private message** dù broker đang phát.
- User A không nhận thông điệp gửi cho `convertAndSendToUser("bob", ...)`.
- Token/CSRF không được log trong payload error.
- Sau khi đổi membership, test cả **kết nối mới và kết nối đang sống**.
- Test client auto-reconnect/re-subscribe có được kiểm tra lại không.
- Nếu broker relay có ACL riêng, test cấu hình broker cũng không cho bypass.

### Đừng chỉ assert HTTP status

Một STOMP ERROR frame hoặc connection close sau Upgrade không được kiểm tra bằng HTTP `expectStatus().isForbidden()` trên cùng socket. Dùng STOMP session handlers để quan sát frames/receipts/errors, và fake broker/subscriber để xác nhận dữ liệu không tới client.

## 25. AuthorizationManager unit tests cần cả type và destination

Với unit test message manager, có thể tạo Message bằng Spring Messaging:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;

SimpMessageHeaderAccessor headers =
    SimpMessageHeaderAccessor.create(SimpMessageType.SUBSCRIBE);
headers.setDestination("/topic/public");
headers.setLeaveMutable(true);

Message<byte[]> subscribe = MessageBuilder.createMessage(
    new byte[0], headers.getMessageHeaders()
);
```

Đây là **JUnit test fixture fragment**, không phải chương trình độc lập. Test phải cung cấp `Authentication` có authorities phù hợp và gọi `AuthorizationManager<Message<?>>` theo API phiên bản Spring Security (ví dụ `authorize(() -> auth, subscribe)` trong dòng mới).

Test tối thiểu:

1. `MESSAGE /topic/public` → DENY.
2. `SUBSCRIBE /topic/public` → ALLOW với user authenticated.
3. `SUBSCRIBE /queue/internal` → DENY.
4. `MESSAGE /app/chat.send` → chỉ ALLOW nếu `CHAT_SEND`.
5. Unknown type/destination → DENY.
6. Null destination CONNECT → yêu cầu authenticated + separate CSRF validation.
7. Với private room matcher, xác nhận từng path variable/tenant được kiểm chứng.

Một `AuthorizationManager` đơn vị **không tự kiểm tra** handshake, STOMP frame decoding, CSRF token handshake/session propagation hoặc outbound delivery. Integration test qua WebSocket STOMP client mới bao phủ được toàn bộ đường đi.

## 26. Broker relay và external message broker không xóa trách nhiệm của ứng dụng

Một ứng dụng có thể dùng simple broker in-memory hoặc relay tới RabbitMQ/ActiveMQ/đích STOMP bên ngoài.

Với relay:

```text
Client STOMP WebSocket
       |
       v
Spring clientInboundChannel -> security checks
       |
       v
STOMP broker relay
       |
       v
External broker
       |
       v
Outbound data to client subscriptions
```

Cần đánh giá:

- Broker đang thấy identity của client hay chỉ service-level credentials?
- Client có thể kết nối **trực tiếp** tới external broker bỏ qua Spring không?
- Broker destinations có ACL theo tenant/user không?
- Có người publish trực tiếp vào `/topic/tenants/A` mà không qua service policy không?
- Broker relay reconnect có tạo lại subscriptions bằng identity/stale grants không?
- User destination transformations có đúng khi scale nhiều Spring nodes không?
- Application có lọc sensitive payload trước khi fanout không?

**Không** dùng một service credential mạnh cho broker rồi coi mọi subscriber được phép đọc mọi topic. Spring inbound guard chỉ áp trên đường **đi qua Spring**; nếu client có cổng trực tiếp tới broker, phải bảo vệ ở broker/network.

## 27. Hiệu năng, giới hạn tài nguyên và rate limiting

WebSocket kết nối lâu, nên chi phí không chỉ là một HTTP request:

- Mỗi socket chiếm memory, heartbeat timers, session metadata.
- Mỗi SUBSCRIBE tạo broker state.
- Mỗi SEND có thể kích hoạt database write, validation và fanout.
- Mỗi subscription private cần kiểm membership/ACL.
- Mỗi broadcast có thể nhân thành hàng nghìn outbound messages.
- Client có thể gửi quá nhiều frame hoặc payload lớn để gây DoS.

Nên áp dụng:

1. Giới hạn connections/IP/user/tenant và số subscriptions/session.
2. Giới hạn frame/message size, send buffer và thời gian chờ.
3. Rate limit SEND theo user/room/action.
4. Bounded thread pools/queues cho inbound channel, DB connection pool.
5. Đặt timeout hợp lý cho ACL/membership query; **không fail open khi timeout**.
6. Tránh tra ACL đồng bộ N lần cho cùng một message nếu có caching có phạm vi.
7. Cache key gồm subject, tenant, destination/resource, action, ACL/policy version.
8. Invalidate permission cache sau revoke, không giữ positive decisions quá lâu.
9. Giới hạn số lượng destinations mà attacker có thể yêu cầu.
10. Kiểm thử backpressure và slow clients trên outbound path theo broker/framework behavior.

**Hiệu năng không phải lý do mở `/topic/**` bằng permitAll**. Nếu kiểm membership quá tốn, cần cải thiện query, materialized grants hoặc subscription lease chứ không loại bỏ kiểm quyền.

## 28. Những lỗi phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Chỉ bảo vệ `GET /ws` | Mọi STOMP SEND/SUBSCRIBE có thể thiếu policy | Thêm message AuthorizationManager |
| Nghĩ HTTP `anyRequest().denyAll()` chặn `/topic/**` | STOMP destinations không phải URLs | Dùng Spring Messaging security matchers |
| Dùng `simpDestMatchers("/topic/**").authenticated()` | Có thể cho cả SEND vào broker | Dùng `simpSubscribeDestMatchers` và deny SEND |
| Cho client SEND tới `/topic/system` | Giả mạo thông báo server | Chỉ gửi tới `/app/**` handler đã bảo vệ |
| Cho SUBSCRIBE `/topic/rooms/**` chỉ vì authenticated | BOLA/room data leak | Kiểm tenant/room membership |
| Cho SUBSCRIBE raw `/queue/**` | Có thể lộ user queues khác | Dùng `/user/queue/**` và deny raw queues |
| Tin `senderId` từ JSON | Giả mạo người gửi | Dùng verified Principal |
| Tin STOMP `login`/`passcode` tự động xác thực | Spring WebSocket mặc định không làm vậy | HTTP auth hoặc custom authenticated CONNECT interceptor |
| Token từ STOMP CONNECT được gắn user trước verification | Identity spoofing | Trusted JWT decoder + đúng interceptor order |
| Require HTTP JWT header từ browser WebSocket rồi không gửi được | Handshake fail, workaround thiếu an toàn | Chọn auth flow hợp browser, tách transport/CONNECT |
| Đưa token vào URL/query string | Rò qua logs/proxies | Tránh; nếu bắt buộc dùng token ngắn hạn và redaction |
| `setAllowedOrigins("*")` với cookie session | Cross-site connection/hijack | Strict origin allowlist + CSRF |
| Vô hiệu CSRF toàn bộ app để sửa SockJS | CSRF trên HTTP business endpoints | Chỉ điều chỉnh transport path cần thiết |
| Dùng `@EnableWebSocketSecurity` rồi nghĩ CSRF tự hết | CONNECT có CSRF requirement | Cấp token đúng STOMP header |
| Chỉ test HTTP 101 | Không biết message-level policy đúng không | Test STOMP SEND/SUBSCRIBE/ERROR |
| Chỉ test role, không test resource ID | Tenant/room khác bị truy cập | Object-level policy |
| Không chặn outbound private data publish sai topic | Inbound guard không cứu được data leak | Destination/data selection trong publisher |
| Nghĩ Spring Security chặn mọi outbound message | Theo tài liệu chủ yếu chỉ inbound | Guard subscriptions, explicit revoke policy |
| Không xử lý membership revoke trên socket sống | Stale subscriptions tiếp tục nhận | Disconnect/unsubscribe/lease/re-eval |
| Broker ngoài có public port | Bypass Spring inbound security | Broker ACL/network isolation |
| Dùng `@MessageMapping` như proxy tự kiểm quyền | Controller routing không thay business policy | Service/DB checks |
| Ghi DB trước khi hậu kiểm | Side effect đã xảy ra | Preauthorize + transactional conditional writes |
| Đặt allow-all matcher trước deny | Rule security phía sau không được xét | Specific-before-general, default deny |
| Sử dụng `AbstractSecurityWebSocketMessageBrokerConfigurer` trên Spring Security 7 | API cũ đã bị loại bỏ | `@EnableWebSocketSecurity` + AuthorizationManager |
| Log raw STOMP headers | Có thể chứa JWT/CSRF/PII | Log redaction, limited audit |
| Không kiểm mismatch HTTP principal/STOMP token | Session identity confusion | Explicit identity binding/trust policy |
| Không test SockJS fallback/Origin | Lỗ hổng cross-origin | End-to-end protocol tests |

## 29. Quy trình chẩn đoán khi CONNECT thành công nhưng SEND/SUBSCRIBE lỗi

1. Xác định client đang dùng **native WebSocket**, SockJS hay broker relay.
2. Kiểm tra HTTP handshake có qua đúng `SecurityFilterChain` không.
3. Kiểm tra response 101/fallback status và Origin policy.
4. Đọc authenticated user ở HTTP request/session.
5. Xác nhận `@EnableWebSocketMessageBroker` đã đăng ký `/ws`.
6. Kiểm tra `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>` bean.
7. Nếu dùng STOMP JWT, xác nhận token được xác minh và interceptor chạy **trước** authorization.
8. Kiểm tra CONNECT CSRF token ở STOMP native headers.
9. Xác nhận loại inbound message là MESSAGE hay SUBSCRIBE, không nhầm MESSAGE outbound.
10. Kiểm tra destination mà Spring nhận có cùng broker/application prefixes không.
11. Kiểm thứ tự matchers trong `MessageMatcherDelegatingAuthorizationManager`.
12. Kiểm authenticated principal có authority thực tế theo hệ thống role mapping không.
13. Nếu private room, kiểm membership, tenant và room state từ database.
14. Kiểm handler `@MessageMapping` có xử lý SEND hay chưa.
15. Nếu SUBSCRIBE được phép nhưng không nhận data, kiểm publisher destination và user-destination transformation.
16. Nếu ERROR sau Upgrade, đừng nhìn HTTP status như REST.
17. Test với một user A và user B khác tenant để xác định có data leakage không.
18. Kiểm log/metrics đã redaction và không lộ token/CSRF.
19. Nếu quyền bị revoke, kiểm socket cũ có bị đóng/huỷ subscription không.
20. Thêm regression test cho chính message type + destination + principal + context gây lỗi.

**Quan trọng:** nếu một test chỉ kiểm "kết nối được" mà chưa gửi bất kỳ STOMP frame nào, nó mới chứng minh tầng transport, không chứng minh các policy ở message layer.

## 30. Checklist review bảo mật trước khi triển khai STOMP

1. HTTP handshake đã xác thực đúng caller hoặc có kiến trúc STOMP CONNECT auth rõ ràng chưa?
2. Browser có gửi được kiểu credential mong đợi không, hay backend trông chờ Authorization header không hỗ trợ?
3. Origin allowlist được cấu hình đúng và đã test cross-origin chưa?
4. STOMP CONNECT có xác minh CSRF/identity theo chính sách hiện hành không?
5. STOMP `login`/`passcode` có bị hiểu nhầm là user authentication không?
6. Có bean `AuthorizationManager<Message<?>>` với `@EnableWebSocketSecurity` không?
7. Các matcher phân biệt `MESSAGE`/SEND và `SUBSCRIBE` chưa?
8. Client có bị cấm SEND trực tiếp `/topic/**` hoặc `/queue/**` không?
9. Client có bị cấm SUBSCRIBE raw `/queue/**` không?
10. `/user/queue/**` được route tới đúng user/session không?
11. Các room private có membership check theo tenant và room ID thật không?
12. Có authority riêng cho user SEND, admin commands và SUBSCRIBE sensitive topic không?
13. Destination chưa biết có bị `denyAll` mặc định không?
14. Payload sender/tenant có được xác minh lại, không lấy nguyên JSON client không?
15. Service xử lý `@MessageMapping` có bảo vệ mutation và domain resource không?
16. Publisher/broker có thể vô tình phát private data vào public topic không?
17. Session đang sống sau revoke có quy trình hủy/refresh quyền không?
18. SockJS HTTP POST fallback đã được thiết kế CSRF hẹp chưa?
19. External broker có public endpoint/ACL khiến client bypass inbound security không?
20. Có hạn chế subscription count, frame size, rate, memory và timeout không?
21. Có test handshake deny, STOMP CONNECT deny, SEND deny, SUBSCRIBE deny riêng không?
22. Có test nhiều users/tenants cùng lúc và các user destinations không?
23. Có test origin spoofing, token replay/expiry, JWT claims và role mapping không?
24. Có audit decisions nhưng không ghi raw JWT/CSRF/password không?
25. Với Spring Security upgrade, đã kiểm API cũ bị loại bỏ và compile/config tests chưa?

**Kết luận:** Bảo vệ WebSocket/STOMP trong Spring Security gồm **ít nhất hai ranh giới độc lập**. HTTP `SecurityFilterChain` bảo vệ handshake và tạo danh tính ban đầu; `@EnableWebSocketSecurity` cùng `AuthorizationManager<Message<?>>` bảo vệ **inbound STOMP message types/destinations**. Handshake authenticated không tự cấp quyền SEND/SUBSCRIBE, và một SUBSCRIBE được phép lúc đầu không đảm bảo quyền được giữ mãi khi ACL thay đổi. Hãy chặn client SEND trực tiếp tới broker, kiểm room/user/tenant ở service, kiểm Origin/CSRF, quản lý subscription revoke, và test end-to-end cả transport lẫn thông điệp.

## Tài liệu tham khảo chính thức

- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): HTTP principal propagation, `@EnableWebSocketSecurity`, `AuthorizationManager<Message<?>>`, inbound-only enforcement, SEND/SUBSCRIBE destination rules, Same Origin/CSRF/SockJS.
- [Spring Security API — EnableWebSocketSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/socket/EnableWebSocketSecurity.html): annotation tích hợp authorization manager cho messages.
- [Spring Security API — MessageMatcherDelegatingAuthorizationManager.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html): `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `simpDestMatchers`, `simpTypeMatchers`, `nullDestMatcher` và `anyMessage`.
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): HTTP identity propagation và mặc định STOMP login/passcode không xác thực browser user.
- [Spring Framework — Token Authentication for STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): token ở STOMP CONNECT, `ChannelInterceptor`, thứ tự interceptor.
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): endpoint `/ws`, application destination prefixes, simple broker/broker relay.
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): `/user/**`, session-specific destination translation.
- [Spring Framework — Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): inbound/broker/outbound channels và messaging pipeline.
- [Spring Framework — STOMP Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html): `ChannelInterceptor` và lifecycle considerations.
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): CSWSH, origin validation, authentication/authorization per message, logging, DoS/rate limits.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default và object-level authorization.
