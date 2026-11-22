# Phân biệt quyền gửi MESSAGE với quyền SUBSCRIBE trong Spring Security

## 1. Tình huống: đọc được thông báo không có nghĩa được phát thông báo

Một ứng dụng Spring WebSocket/STOMP cho phép người dùng theo dõi thông báo hệ thống ở `/topic/system/announcements`. Người dùng **được phép nhận** thông báo từ server, nhưng không được **giả mạo server để phát** thông báo đến những người đang theo dõi.

Hai thao tác STOMP từ client thường gặp:

```text
SUBSCRIBE
id:sub-1
destination:/topic/system/announcements

^@
```

và:

```text
SEND
destination:/topic/system/announcements
content-type:text/plain

Thông báo giả mạo từ client^@
```

`^@` ở đây chỉ ký hiệu vị trí null terminator của một frame STOMP; nó không phải escape sequence chính thức để đưa nguyên văn vào request. Điểm quan trọng là **cùng một destination nhưng loại thao tác khác nhau**. Một chính sách chỉ kiểm tra destination, ví dụ `"/topic/**".hasRole("USER")` mà không ràng buộc message type, có thể vô tình cho client gửi trực tiếp vào topic chỉ được dành cho server publish.

**Quy tắc:** quyền **gửi** (`STOMP SEND`, phía inbound Spring thường được biểu diễn bằng `SimpMessageType.MESSAGE`) và quyền **đăng ký nhận** (`STOMP SUBSCRIBE`, `SimpMessageType.SUBSCRIBE`) là **hai quyết định riêng**. Không suy luận rằng ai có quyền đọc một topic cũng có quyền gửi vào topic, hoặc ai gửi được vào một endpoint nghiệp vụ thì có quyền subscribe mọi kênh trả dữ liệu.

Bài học tập trung vào **phân quyền thông điệp** trong Spring Security, Spring Messaging và WebSocket/STOMP. Các ví dụ minh họa nhánh Spring Boot 3.5.x / Spring Security 6.5; khi dùng 7.x phải kiểm tra sự thay đổi API và migration guide tương ứng.

## 2. Bản đồ khái niệm: SEND, MESSAGE và SUBSCRIBE

| Thuật ngữ | Ai dùng? | Ý nghĩa |
| --- | --- | --- |
| STOMP `CONNECT` | Client → server | Mở phiên STOMP sau HTTP/WebSocket handshake |
| STOMP `SEND` | Client → server | Gửi nội dung đến một destination |
| Spring `SimpMessageType.MESSAGE` | Ở clientInboundChannel | Thường biểu diễn lệnh SEND từ client |
| STOMP `SUBSCRIBE` | Client → server | Đăng ký nhận các thông điệp ở destination |
| Spring `SimpMessageType.SUBSCRIBE` | Ở clientInboundChannel | Yêu cầu subscription của client |
| STOMP `MESSAGE` | Broker/server → client | Frame dữ liệu server/broker phát cho subscriber |
| STOMP `UNSUBSCRIBE` | Client → server | Hủy một đăng ký trước đó |
| STOMP `DISCONNECT` | Client → server | Kết thúc phiên |
| `@MessageMapping` | Spring controller | Xử lý thông điệp gửi đến application destination |
| `SimpMessagingTemplate` | Server | Publish tới broker destination hoặc user destination |

Tên **MESSAGE** dễ gây nhầm: STOMP có frame outbound tên `MESSAGE`, còn Spring dùng `SimpMessageType.MESSAGE` cho inbound application message tương ứng với client `SEND`. Khi phân quyền bằng `MessageMatcherDelegatingAuthorizationManager`, ta đang kiểm tra **thông điệp đi vào server**, không phải mỗi server-generated outbound STOMP MESSAGE.

### Ví dụ chức năng chat

```text
Alice, quyền CHAT_SEND:
  SEND /app/chat.send
    -> @MessageMapping("/chat.send")
    -> service kiểm tra nội dung/tenant/policy
    -> SimpMessagingTemplate.convertAndSend("/topic/chat.public", ...)
    -> broker chuyển MESSAGE tới những ai đã subscribe hợp lệ

Bob, quyền CHAT_READ:
  SUBSCRIBE /topic/chat.public
    -> broker đăng ký
    -> nhận các MESSAGE do server gửi

Bob thử:
  SEND /topic/chat.public
    -> DENY, dù Bob có CHAT_READ
```

Một user có thể đồng thời có `CHAT_SEND` và `CHAT_READ`. Nhưng server vẫn cần chặn gửi trực tiếp vào broker destination trừ khi đó là một endpoint publish được thiết kế đặc biệt với kiểm tra tương ứng.

## 3. Ba nhóm destination cần tách rõ

Trong cấu hình phổ biến của Spring Framework:

```java
registry.setApplicationDestinationPrefixes("/app");
registry.enableSimpleBroker("/topic", "/queue");
registry.setUserDestinationPrefix("/user");
```

Các prefix có ý nghĩa khác nhau:

| Destination | Dùng để làm gì? | Policy gợi ý |
| --- | --- | --- |
| `/app/chat.send` | Client gửi action cho controller | Chỉ `MESSAGE` nếu có CHAT_SEND |
| `/app/documents.update` | Client yêu cầu cập nhật dữ liệu | `MESSAGE` + quyền cập nhật và object policy |
| `/topic/chat.public` | Broker phát chat chung | Chỉ `SUBSCRIBE` nếu có CHAT_READ |
| `/topic/system/announcements` | Server phát thông báo hệ thống | `SUBSCRIBE` theo policy, không client SEND |
| `/topic/tenants/alpha/events` | Broker topic theo tenant | `SUBSCRIBE` phải kiểm tra membership tenant |
| `/user/queue/messages` | Logical user destination | `SUBSCRIBE` cho đúng user/session |
| `/queue/**` | Broker destination vật lý | Deny client SUBSCRIBE trực tiếp nếu không có exception có chủ đích |
| Không destination (CONNECT, DISCONNECT...) | Điều khiển session | Authentication/CSRF, protocol policy riêng |

`setApplicationDestinationPrefixes("/app")` nghĩa là STOMP client gửi `/app/chat.send` có thể được dispatch đến `@MessageMapping("/chat.send")`, vì Spring xử lý prefix `/app` ở trước controller.

`enableSimpleBroker("/topic", "/queue")` nghĩa là broker xử lý các destination tương ứng. **Không đồng nhất routing với authorization**: broker prefix không phải hàng rào bảo mật. Nếu không chặn client SEND vào broker namespace, client có thể bỏ qua validation nghiệp vụ trong `@MessageMapping`.

### Khi nào SUBSCRIBE được coi là “đọc”?

Một subscription cho phép broker **gửi các thông điệp tương lai** đến client ở destination đó. Đây không chỉ là một request GET một lần: kết nối có thể sống rất lâu và tiếp tục nhận sự kiện sau khi quyền trong database thay đổi. Vì vậy subscription authorization cần xét cả vấn đề **revocation, tenant isolation và thông tin nhạy cảm theo thời gian**.

## 4. Phân quyền phải xét cả loại message và destination

Giả sử policy:

- Người có `CHAT_SEND` được `SEND /app/chat.send`.
- Người có `CHAT_READ` được `SUBSCRIBE /topic/chat.public`.
- Người đã xác thực được `SUBSCRIBE /user/queue/errors` để nhận lỗi riêng.
- Client không được `MESSAGE` tới `/topic/**` hoặc `/queue/**`.
- Không được `SUBSCRIBE` tới `/app/**`.
- Những lệnh và destination còn lại bị từ chối trừ control frames được liệt kê.

Truth table:

| Caller | STOMP frame | Destination | Kỳ vọng |
| --- | --- | --- | --- |
| CHAT_SEND | SEND | `/app/chat.send` | **PERMIT** |
| CHAT_SEND | SUBSCRIBE | `/topic/chat.public` | DENY nếu không CHAT_READ |
| CHAT_READ | SUBSCRIBE | `/topic/chat.public` | **PERMIT** |
| CHAT_READ | SEND | `/topic/chat.public` | **DENY** |
| CHAT_READ | SEND | `/app/chat.send` | DENY |
| CHAT_SEND+CHAT_READ | SEND | `/app/chat.send` | **PERMIT** |
| CHAT_SEND+CHAT_READ | SUBSCRIBE | `/topic/chat.public` | **PERMIT** |
| CHAT_SEND+CHAT_READ | SEND | `/topic/chat.public` | **DENY** |
| Authenticated | SUBSCRIBE | `/user/queue/errors` | **PERMIT** |
| Authenticated | SUBSCRIBE | `/queue/private` | DENY |
| Authenticated | SUBSCRIBE | `/app/chat.send` | DENY |
| Anonymous | CONNECT | không destination | DENY (đối với protected app) |
| Authenticated | CONNECT | không destination | Điều kiện auth đạt; còn CSRF/STOMP security |

Một thứ tự matcher tốt là: **các loại control frames cụ thể → MESSAGE/SUBSCRIBE destination được cho phép → deny các loại MESSAGE/SUBSCRIBE còn lại → deny mọi thứ còn lại**.

## 5. Vì sao chỉ dùng simpDestMatchers có thể quá rộng?

`MessageMatcherDelegatingAuthorizationManager.Builder` hỗ trợ nhiều matcher. Quan trọng nhất:

```java
// Chỉ xét destination, không ràng buộc SimpMessageType.
messages.simpDestMatchers("/topic/chat.public")
        .hasAuthority("CHAT_READ");

// Chỉ match SimpMessageType.MESSAGE + destination.
messages.simpMessageDestMatchers("/app/chat.send")
        .hasAuthority("CHAT_SEND");

// Chỉ match SimpMessageType.SUBSCRIBE + destination.
messages.simpSubscribeDestMatchers("/topic/chat.public")
        .hasAuthority("CHAT_READ");
```

Đây là **các snippet độc lập minh họa lựa chọn API**, không nên copy cả ba vào một policy như trên. Matcher đầu tiên có thể match cả client SEND/MESSAGE và SUBSCRIBE cho cùng topic, nên không phù hợp khi chỉ muốn cấp **quyền nhận**.

Cách chính xác hơn:

- `simpMessageDestMatchers` cho những application SEND routes được thiết kế.
- `simpSubscribeDestMatchers` cho những kênh client được phép theo dõi.
- `simpTypeMatchers` cho các loại frame như CONNECT/DISCONNECT hoặc deny catch-all MESSAGE/SUBSCRIBE.
- `anyMessage().denyAll()` để từ chối những message không được rule trước match.

Tài liệu Spring Security 6.5 JavaDoc phân biệt rõ `simpMessageDestMatchers` với `simpSubscribeDestMatchers` theo `SimpMessageType`. Các matcher được xử lý theo chính sách đã đăng ký; không đặt một rule rộng `/topic/**` ở trước một rule chặn chi tiết.

### Phản ví dụ: destination-only rule cho topic

```java
messages
    .simpDestMatchers("/topic/**").hasRole("USER")
    .anyMessage().denyAll();
```

Nếu ứng dụng dùng cùng broker prefix cho publish và subscribe, một user ROLE_USER có thể qua guard cho `MESSAGE` tới topic. **Không dùng cấu hình này để nói rằng “USER chỉ được xem”**.

### Cách sửa

```java
messages
    .simpSubscribeDestMatchers("/topic/chat.public")
        .hasAuthority("CHAT_READ")
    .simpMessageDestMatchers("/app/chat.send")
        .hasAuthority("CHAT_SEND")
    .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
```

Trong ví dụ trên cần imports `SimpMessageType.MESSAGE`, `SimpMessageType.SUBSCRIBE`. Các control frames muốn cho phép phải được liệt kê trước các rule deny; phiên bản hoàn chỉnh nằm ở mục 9.

## 6. Hành trình message đi qua các channel của Spring

```text
CLIENT SEND /app/chat.send
    |
    v
WebSocket/STOMP transport
    |
    v
clientInboundChannel  <---- Spring Security authorization checks
    |
    v
SimpAnnotationMethodMessageHandler
    |
    v
@MessageMapping("/chat.send")
    |
    v
SimpMessagingTemplate -> brokerChannel
    |
    v
SimpleBroker hoặc external broker relay
    |
    v
clientOutboundChannel
    |
    v
SUBSCRIBERS đã được chấp nhận
```

Với SUBSCRIBE:

```text
CLIENT SUBSCRIBE /topic/chat.public
    |
    v
clientInboundChannel  <---- SUBSCRIBE authorization
    |
    v
Broker đăng ký subscription của session
    |
    v
Khi server publish, broker đưa MESSAGE tới session
```

Theo tài liệu Spring Security, WebSocket authorization bảo vệ **`clientInboundChannel`**. Nó **không tự kiểm soát từng message trên `clientOutboundChannel`**, chủ yếu vì chi phí khi một thông điệp được phát cho nhiều subscribers. Do vậy, **cửa kiểm soát subscription rất quan trọng**.

Không suy luận rằng một server event vừa được gửi ra đã đi qua cùng manager `simpSubscribeDestMatchers` lần nữa. Nếu dữ liệu thay đổi độ nhạy, phải kiểm soát ở nguồn publish và subscription lifecycle.

### Simple broker và external broker relay

Simple broker của Spring phù hợp ví dụ học tập. Nếu dùng RabbitMQ/ActiveMQ/STOMP relay, vẫn cần giới hạn **clientInboundChannel** và cấu hình broker account/routing phù hợp. Một external broker không biến `/topic/**` thành an toàn nếu client có thể publish hoặc subscribe trái phép ở một đường khác.

## 7. Authentication: kết nối được chưa chắc MESSAGE/SUBSCRIBE được phép

WebSocket session thường bắt đầu bằng HTTP handshake. Trong ứng dụng Servlet, Spring có thể lấy `Principal` từ request đã được Spring Security xác thực, rồi gắn user vào STOMP messages của session.

```text
HTTP GET /ws (Upgrade: websocket)
  -> HTTP SecurityFilterChain authenticate
  -> WebSocket session giữ Principal
  -> STOMP CONNECT
  -> STOMP SEND/SUBSCRIBE
  -> inbound authorization theo message type + destination
```

Một user authenticated có thể **CONNECT hợp lệ** nhưng vẫn không có `CHAT_SEND` hoặc `CHAT_READ`. Ngược lại, một rule permit cho STOMP CONNECT không đồng nghĩa cho phép gửi/nhận ở mọi topic.

### STOMP CONNECT có CSRF riêng

Theo tài liệu Spring Security 6.5, `@EnableWebSocketSecurity` áp dụng kiểm tra CSRF đối với inbound STOMP CONNECT như lớp bảo vệ cùng nguồn. Browser không áp dụng Same Origin Policy cho WebSocket giống fetch/XHR, nên cần origin restrictions và chính sách CSRF phù hợp. Thông thường token CSRF được gửi qua **STOMP native headers** ở CONNECT, không phải cứ đưa vào query parameter là an toàn.

**Đừng tắt CSRF toàn ứng dụng** để “chạy được WebSocket”. Với SockJS fallback có thể cần điều chỉnh CSRF của các transport URLs chính xác, nhưng vẫn giữ kiểm tra cùng nguồn/token ở nơi cần.

### JWT trong CONNECT header không tự được xác thực

Spring Framework mặc định không coi STOMP `login`/`passcode` headers là HTTP authentication credentials. Nếu muốn bearer token ở STOMP CONNECT, phải có custom `ChannelInterceptor` xử lý token và `accessor.setUser(authentication)` sau khi verify. Cần bảo đảm interceptor authentication chạy **trước** interceptor authorization, ví dụ dùng ordering phù hợp theo tài liệu.

Không coi raw `Authorization: Bearer ...` trong STOMP headers là quyền đã được cấp khi chưa có component verify chữ ký/issuer/audience/expiry, và không gửi token trong query URL nếu có thể tránh vì logs/history có thể lưu lại.

## 8. Policy lớp thứ hai: SEND được route chưa có nghĩa nội dung hợp lệ

Ngay cả nếu frame `MESSAGE /app/chat.send` vượt qua một rule `hasAuthority("CHAT_SEND")`, controller vẫn phải kiểm tra:

- Principal thực từ session, không tin `from` trong payload.
- User đang thuộc room/tenant nếu request chỉ định room.
- Độ dài và định dạng payload; chống spam/DoS, injection.
- Object-level policy cho room/document/action.
- Thời điểm/capability phù hợp với transaction.
- Hạn mức gửi, audit và moderation theo nghiệp vụ.
- Không dùng userId/client header để giả danh sender.

Phản ví dụ:

```json
{
  "from": "system-admin",
  "roomId": "alpha",
  "text": "Đây là thông báo chính thức"
}
```

Nếu controller nhận `from` từ JSON và phát đi như lời của admin, quyền `CHAT_SEND` chung bị biến thành khả năng giả mạo. Dùng `Principal.getName()` và giữ luồng system announcement riêng với policy mạnh hơn.

Phân quyền messaging nên có hai tầng:

```text
MESSAGE access:
  frame type + destination + baseline authority

Business access:
  authenticated principal + tenant + room/member + object state + payload
```

## 9. Cấu hình Spring Security 6.5: rule riêng cho MESSAGE và SUBSCRIBE

Tệp `MessageSecurityConfig.java` trong project ví dụ:

```java
package demo.stomp;

import static org.springframework.messaging.simp.SimpMessageType.CONNECT;
import static org.springframework.messaging.simp.SimpMessageType.DISCONNECT;
import static org.springframework.messaging.simp.SimpMessageType.HEARTBEAT;
import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;
import static org.springframework.messaging.simp.SimpMessageType.UNSUBSCRIBE;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class MessageSecurityConfig {

    @Bean
    public AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        return configureRules(messages);
    }

    // Package-private để unit tests sử dụng đúng một policy.
    static AuthorizationManager<Message<?>> configureRules(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
                // Control frames: không tự cấp quyền SEND/SUBSCRIBE.
                .simpTypeMatchers(
                        CONNECT, DISCONNECT, UNSUBSCRIBE, HEARTBEAT)
                    .authenticated()

                // SEND to application controller: phải có CHAT_SEND.
                .simpMessageDestMatchers("/app/chat.send")
                    .hasAuthority("CHAT_SEND")

                // SUBSCRIBE to broker topic: phải có CHAT_READ.
                .simpSubscribeDestMatchers("/topic/chat.public")
                    .hasAuthority("CHAT_READ")

                // Kênh phản hồi cá nhân; yêu cầu authentication.
                .simpSubscribeDestMatchers("/user/queue/errors")
                    .authenticated()

                // Mọi SEND/SUBSCRIBE khác đều bị từ chối.
                .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()

                // Mọi loại message còn lại đều bị từ chối.
                .anyMessage().denyAll();

        return messages.build();
    }
}
```

**Ý nghĩa từng rule:**

1. CONNECT/DISCONNECT/UNSUBSCRIBE/HEARTBEAT chỉ yêu cầu authenticated. Điều này **không thay** CSRF protection mặc định của `@EnableWebSocketSecurity` đối với CONNECT.
2. `simpMessageDestMatchers("/app/chat.send")` chỉ match `SimpMessageType.MESSAGE`, tương ứng client SEND.
3. `simpSubscribeDestMatchers("/topic/chat.public")` chỉ match `SimpMessageType.SUBSCRIBE`.
4. `/user/queue/errors` có quy tắc subscribe riêng; không mở toàn `/queue/**`.
5. Catch-all `MESSAGE, SUBSCRIBE` deny bảo vệ các destinations không được liệt kê.
6. `anyMessage().denyAll()` ngăn policy rơi vào trạng thái allow ngoài dự kiến.

Đây là policy mẫu **theo authority CHAT_SEND/CHAT_READ đã được cấp qua authentication**. Trong hệ thống có role/authority khác, phải map rõ đúng nguồn; không tạo `CHAT_SEND` chỉ vì client khai một header tùy ý.

### Vì sao không cho client SEND vào /topic/chat.public?

Với cấu hình này, client chỉ SEND vào `/app/chat.send`. Controller xác thực nội dung, rồi server dùng `SimpMessagingTemplate` publish `/topic/chat.public`. Điều này ngăn client bypass controller và impersonate server publisher.

### Vì sao không cho SUBSCRIBE /app/chat.send?

`/app` dành cho application message handler, không phải broker subscription. Nếu client SUBSCRIBE trực tiếp vào `/app/chat.send`, policy không có rule cho phép nên bị deny. Một user có `CHAT_SEND` cũng không tự trở thành subscriber.

## 10. WebSocketMessageBrokerConfigurer: routing và origin restrictions

Tệp `WebSocketConfig.java`:

```java
package demo.stomp;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry endpoints) {
        endpoints.addEndpoint("/ws")
                .setAllowedOrigins("https://chat.example.org");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry broker) {
        broker.setApplicationDestinationPrefixes("/app");
        broker.enableSimpleBroker("/topic", "/queue");
        broker.setUserDestinationPrefix("/user");
    }
}
```

**Lưu ý:** `https://chat.example.org` là origin minh họa. Để chạy demo local cần cấu hình đúng origin local hoặc dùng client nonbrowser cho phép handshake; **không** thay bằng `setAllowedOriginPatterns("*")` ở production chỉ để tránh lỗi CORS/Origin. Origin allowlist và CSRF bảo vệ những vấn đề khác nhau; không dùng một cơ chế làm cớ bỏ cơ chế kia.

Broker prefix `/topic`/`/queue` giúp routing, **không tự cấm SEND từ client**. Chính `MessageSecurityConfig` ở mục 9 thực thi inbound authorization.

### Kiểm tra destination với dấu phân tách

Ở một số cấu hình, broker/matcher có thể dùng separator dạng `.` thay vì `/`. Phải kiểm tra pattern matching và prefix thực, nhất là khi dùng broker relay/custom `PathMatcher`. Một rule `/topic/**` không bảo vệ destination `topic.foo` nếu router vẫn cho phép alias khác. Cần test mọi destination được expose trong production.

## 11. Controller minh họa: chỉ server publish vào broker topic

Tệp `ChatController.java`:

```java
package demo.stomp;

import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    private final SimpMessagingTemplate messaging;

    public ChatController(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    @MessageMapping("/chat.send")
    public void send(ChatInput input, Principal principal) {
        if (principal == null) {
            throw new IllegalArgumentException("No authenticated sender");
        }
        if (input == null || input.text() == null
                || input.text().isBlank()
                || input.text().length() > 500) {
            throw new IllegalArgumentException("Invalid chat text");
        }

        ChatEvent event = new ChatEvent(
                principal.getName(), input.text().trim());
        messaging.convertAndSend("/topic/chat.public", event);
    }

    public record ChatInput(String text) {}
    public record ChatEvent(String sender, String text) {}
}
```

Client SEND `/app/chat.send` với body JSON dạng:

```json
{"text":"Chào mọi người"}
```

Nếu đã qua inbound authority `CHAT_SEND` và controller validation, server publish một event:

```json
{"sender":"alice","text":"Chào mọi người"}
```

Đây là **schema minh họa**, không phải lời khẳng định payload thực khi chưa test serialization. Quan trọng là client không được đưa một thuộc tính `sender` để tự giả danh, vì server sử dụng Principal của session.

Nếu có tenant/room riêng, cần kiểm tra membership trong controller/service trước khi publish và đặt topic tenant-bound. Với WebSocket connection dài, không mặc định membership còn hiệu lực vĩnh viễn chỉ vì handshake ban đầu thành công.

### Bảo mật thông báo hệ thống

Đừng dùng cùng endpoint `/app/chat.send` cho thông báo của hệ thống mà chỉ dựa vào `CHAT_SEND`. Một endpoint `/app/system.announce` cần authority/policy cao hơn (ví dụ `SYSTEM_ANNOUNCE`) và chỉ server/service trusted nên có quyền publish. Client SEND trực tiếp tới `/topic/system/announcements` luôn bị deny theo policy inbound.

## 12. Cấu hình HTTP security cho handshake

Trong ví dụ Servlet, HTTP handshake `GET /ws` vẫn phải có authentication thích hợp.

Tệp `StompDemoApplication.java`:

```java
package demo.stomp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class StompDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StompDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/ws").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    InMemoryUserDetailsManager users() {
        UserDetails writer = User.withUsername("writer")
                .password("{noop}pass")
                .authorities("CHAT_SEND")
                .build();

        UserDetails reader = User.withUsername("reader")
                .password("{noop}pass")
                .authorities("CHAT_READ")
                .build();

        UserDetails both = User.withUsername("both")
                .password("{noop}pass")
                .authorities("CHAT_SEND", "CHAT_READ")
                .build();

        return new InMemoryUserDetailsManager(writer, reader, both);
    }
}
```

**Không dùng `{noop}pass` ở production.** Demo chỉ minh họa authority trên authenticated session. Browser WebSocket API không cho tùy ý thêm Authorization HTTP header trong handshake; nếu app browser dùng Basic/cookie login, cần authentication HTTP phù hợp trước khi WebSocket kết nối, đồng thời đặt cookie SameSite và CSRF/origin rules. Một STOMP client Java có thể gửi HTTP headers theo thư viện của nó.

**Lưu ý về CSRF:** `@EnableWebSocketSecurity` vẫn yêu cầu CSRF token hợp lệ ở inbound STOMP CONNECT theo Spring Security docs. Vì vậy **chỉ có HTTP Basic credentials là chưa đủ để chứng minh một end-to-end browser STOMP CONNECT sẽ thành công**; client và session/token flow phải được cấu hình tương ứng.

## 13. Maven Java 17: project ví dụ và dependencies

Để chạy cấu hình Spring phía trên, có thể tạo project:

```text
stomp-send-subscribe-security/
├── pom.xml
└── src/
    ├── main/java/demo/stomp/
    │   ├── StompDemoApplication.java
    │   ├── WebSocketConfig.java
    │   ├── MessageSecurityConfig.java
    │   └── ChatController.java
    └── test/java/demo/stomp/
        └── MessageSecurityRulesTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>stomp-send-subscribe-security</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-messaging</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**Phân biệt thư viện:** `spring-boot-starter-websocket` cung cấp WebSocket/STOMP framework, còn `spring-security-messaging` chứa các authorization components để bảo vệ message. `spring-boot-starter-security` cung cấp authentication/SecurityFilterChain. Không có module messaging security thì chỉ bật WebSocket routing không tạo policy SEND/SUBSCRIBE.

Spring Boot 3.5.16 là một release 3.5 đã được công bố; ở production mới cần chọn maintenance branch còn được hỗ trợ. Project ví dụ nhắm API của Spring Security 6.5; nếu dùng Spring Security 7.x, kiểm tra API builder và migration guide.

### Chạy unit tests trước khi mở server

```bash
java -version
mvn -version
mvn -q clean test
```

Các tests ở mục tiếp theo kiểm tra trực tiếp `AuthorizationManager<Message<?>>`. Chúng **không tạo STOMP WebSocket connection thực** và không chứng minh CSRF/origin/JWT transport đã được kiểm thử. Muốn kiểm tra end-to-end, thêm STOMP client tests với authenticated handshake và token CSRF hợp lệ.

## 14. Unit tests trực tiếp MESSAGE vs SUBSCRIBE bằng Spring Security

Tệp `MessageSecurityRulesTest.java`:

```java
package demo.stomp;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

class MessageSecurityRulesTest {

    private final AuthorizationManager<Message<?>> rules =
            MessageSecurityConfig.configureRules(
                    MessageMatcherDelegatingAuthorizationManager.builder());

    private static Authentication user(
            String username, String... authorities) {

        return new UsernamePasswordAuthenticationToken(
                username, "n/a",
                AuthorityUtils.createAuthorityList(authorities));
    }

    private static Message<?> message(
            SimpMessageType type, String destination) {

        SimpMessageHeaderAccessor accessor =
                SimpMessageHeaderAccessor.create(type);

        if (destination != null) {
            accessor.setDestination(destination);
        }
        accessor.setLeaveMutable(true);
        return MessageBuilder.createMessage(
                new byte[0], accessor.getMessageHeaders());
    }

    private boolean permitted(
            Authentication user,
            SimpMessageType type,
            String destination) {

        AuthorizationResult result = rules.authorize(
                () -> user, message(type, destination));

        assertNotNull(result, "No authorization decision");
        return result.isGranted();
    }

    @Test
    void writerCanSendToApplicationRoute() {
        assertTrue(permitted(user("writer", "CHAT_SEND"),
                SimpMessageType.MESSAGE, "/app/chat.send"));
    }

    @Test
    void readerCannotSendToApplicationRoute() {
        assertFalse(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.MESSAGE, "/app/chat.send"));
    }

    @Test
    void readerCanSubscribeToChatTopic() {
        assertTrue(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.SUBSCRIBE, "/topic/chat.public"));
    }

    @Test
    void writerWithoutReadAuthorityCannotSubscribe() {
        assertFalse(permitted(user("writer", "CHAT_SEND"),
                SimpMessageType.SUBSCRIBE, "/topic/chat.public"));
    }

    @Test
    void readerCannotPublishDirectlyToBrokerTopic() {
        assertFalse(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.MESSAGE, "/topic/chat.public"));
    }

    @Test
    void evenWriterCannotPublishDirectlyToBrokerTopic() {
        assertFalse(permitted(user("both", "CHAT_SEND", "CHAT_READ"),
                SimpMessageType.MESSAGE, "/topic/chat.public"));
    }

    @Test
    void subscriptionToAppDestinationIsRejected() {
        assertFalse(permitted(user("both", "CHAT_SEND", "CHAT_READ"),
                SimpMessageType.SUBSCRIBE, "/app/chat.send"));
    }

    @Test
    void subscriptionToRawQueueIsRejected() {
        assertFalse(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.SUBSCRIBE, "/queue/private"));
    }

    @Test
    void authenticatedUserCanSubscribeToOwnErrorDestination() {
        assertTrue(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.SUBSCRIBE, "/user/queue/errors"));
    }

    @Test
    void authenticatedUserCanConnectAtAuthorizationLayer() {
        assertTrue(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.CONNECT, null));
    }

    @Test
    void unknownSendDestinationIsDenied() {
        assertFalse(permitted(user("writer", "CHAT_SEND"),
                SimpMessageType.MESSAGE, "/app/unlisted"));
    }

    @Test
    void missingDestinationForMessageIsDenied() {
        assertFalse(permitted(user("writer", "CHAT_SEND"),
                SimpMessageType.MESSAGE, null));
    }
}
```

Đây là **12 phương thức test JUnit 5** kiểm tra trực tiếp message policy. Authentication trong tests được tạo như một principal đã xác thực (constructor ba đối số), không phải HTTP login thực.

**Điểm mạnh của test:** cùng destination `/topic/chat.public` có SUBSCRIBE permit cho reader, nhưng MESSAGE deny cho mọi client, kể cả user có cả CHAT_SEND và CHAT_READ. Điều đó chứng minh chính sách **không grant dựa vào destination đơn lẻ**.

### Một điểm về API phiên bản

Trong Spring Security 6.5, `AuthorizationManager.authorize(...)` có từ 6.4 và trả `AuthorizationResult`; `AuthorizationResult.isGranted()` cho biết quyết định. JavaDoc 6.5 ghi `check(...)` đã deprecated để ưu tiên `authorize(...)`. Trước khi copy sang Spring Security 5.8 hoặc 7.x, kiểm tra interface/builder API tương ứng, đặc biệt compile và chạy tests.

### Test chưa chứng minh điều gì?

Nó chỉ test `MessageMatcherDelegatingAuthorizationManager` thuần. Nó **không** kiểm tra:

- `@EnableWebSocketSecurity` đã cài inbound ChannelInterceptor đúng order.
- HTTP handshake authentication/JWT/cookie.
- STOMP CONNECT CSRF token và origin restrictions.
- Broker routing, controller invocation, JSON serialization.
- User destination transformation, token expiry hoặc dynamic room membership.
- Broker relay authentication và ACL ở external broker.

Để có bằng chứng end-to-end, dùng STOMP client chạy trong test context và kiểm tra có/không nhận MESSAGE thực từ server.

## 15. Java 17 thuần: mô phỏng policy SEND và SUBSCRIBE

Nếu chưa muốn khởi động Maven, ví dụ Java 17 độc lập dưới đây làm rõ **logic quyết định**. Nó không phải Spring Security implementation và không mô phỏng handshake/CSRF/broker; nó được thiết kế để có stdout xác định.

Tệp `StompPolicyLab.java`:

```java
import java.util.Set;

public final class StompPolicyLab {

    enum Type { CONNECT, MESSAGE, SUBSCRIBE, DISCONNECT }

    record User(boolean authenticated, Set<String> authorities) {
        boolean has(String authority) {
            return authenticated && authorities.contains(authority);
        }
    }

    record Frame(Type type, String destination) {}

    private static boolean allowed(User user, Frame frame) {
        if (!user.authenticated()) {
            return false;
        }

        if (frame.type() == Type.CONNECT
                || frame.type() == Type.DISCONNECT) {
            return true;
        }

        if (frame.type() == Type.MESSAGE
                && "/app/chat.send".equals(frame.destination())) {
            return user.has("CHAT_SEND");
        }

        if (frame.type() == Type.SUBSCRIBE
                && "/topic/chat.public".equals(frame.destination())) {
            return user.has("CHAT_READ");
        }

        if (frame.type() == Type.SUBSCRIBE
                && "/user/queue/errors".equals(frame.destination())) {
            return true;
        }

        // Tất cả destination/loại message chưa được liệt kê: DENY.
        return false;
    }

    private static void example(
            String label, User user, Type type, String destination) {

        System.out.println(label + "="
                + allowed(user, new Frame(type, destination)));
    }

    public static void main(String[] args) {
        User writer = new User(true, Set.of("CHAT_SEND"));
        User reader = new User(true, Set.of("CHAT_READ"));
        User both = new User(true, Set.of("CHAT_SEND", "CHAT_READ"));
        User anonymous = new User(false, Set.of());

        example("writer_send_app", writer,
                Type.MESSAGE, "/app/chat.send");
        example("writer_subscribe_topic", writer,
                Type.SUBSCRIBE, "/topic/chat.public");
        example("reader_subscribe_topic", reader,
                Type.SUBSCRIBE, "/topic/chat.public");
        example("reader_send_topic", reader,
                Type.MESSAGE, "/topic/chat.public");
        example("reader_send_app", reader,
                Type.MESSAGE, "/app/chat.send");
        example("both_send_app", both,
                Type.MESSAGE, "/app/chat.send");
        example("both_subscribe_topic", both,
                Type.SUBSCRIBE, "/topic/chat.public");
        example("both_send_topic", both,
                Type.MESSAGE, "/topic/chat.public");
        example("reader_subscribe_raw_queue", reader,
                Type.SUBSCRIBE, "/queue/private");
        example("reader_subscribe_app", reader,
                Type.SUBSCRIBE, "/app/chat.send");
        example("reader_connect", reader,
                Type.CONNECT, null);
        example("anonymous_connect", anonymous,
                Type.CONNECT, null);
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac StompPolicyLab.java
java StompPolicyLab
```

Stdout theo logic chương trình:

```text
writer_send_app=true
writer_subscribe_topic=false
reader_subscribe_topic=true
reader_send_topic=false
reader_send_app=false
both_send_app=true
both_subscribe_topic=true
both_send_topic=false
reader_subscribe_raw_queue=false
reader_subscribe_app=false
reader_connect=true
anonymous_connect=false
```

Lý do:

- Writer chỉ có `CHAT_SEND`: gửi vào `/app/chat.send` hợp lệ, subscribe topic không hợp lệ.
- Reader chỉ có `CHAT_READ`: subscribe topic hợp lệ, SEND tới topic bị deny.
- User có cả hai authorities vẫn **không SEND trực tiếp vào broker topic**.
- `/queue/private` và `/app/chat.send` không phải subscription được liệt kê nên deny.
- Authenticated CONNECT đạt authorization logic trong mô phỏng; **chưa** có CSRF/origin/token checks.
- Anonymous CONNECT bị deny theo chính sách ví dụ.

Với Spring Security thật, dùng các matcher trong mục 9 để thực thi cùng ý tưởng, rồi chạy test mục 14 thay vì tin vào logic mô phỏng này.

## 16. SUBSCRIBE /user/queue khác với SUBSCRIBE /queue trực tiếp

Spring hỗ trợ **user destinations** để gửi response tới đúng người.

Ví dụ server:

```java
messaging.convertAndSendToUser(
        recipientUsername, "/queue/messages", payload);
```

Client thường subscribe:

```text
SUBSCRIBE
id:private-1
destination:/user/queue/messages
```

Framework có thể chuyển logical user destination thành physical broker destination chứa session-specific suffix. Một destination vật lý dạng `/queue/...-sessionid` không nên cho phép client tự subscribe trực tiếp chỉ vì client biết/đoán tên.

**Điểm bảo mật:** cho phép `simpSubscribeDestMatchers("/user/queue/messages")` cho user đã xác thực, nhưng **không** mở `simpSubscribeDestMatchers("/queue/**").permitAll()`.

Tuy nhiên, `/user/queue/messages` không tự bảo đảm payload gửi đúng người nếu application chọn sai username. Nguồn dữ liệu phải:

- Xác định recipient từ identity/membership được server xác thực.
- Không lấy `recipientUsername` bất kỳ từ client và gửi bí mật không kiểm tra quyền.
- Đảm bảo tenant isolation với tên username có thể trùng giữa tenants/issuers.
- Kiểm tra số lượng sessions của user, policy multi-device và logout/revocation.
- Không cho client SEND tới `/user/queue/messages` trừ một endpoint action riêng đã được bảo vệ.

Với ứng dụng chat private, thường phân biệt `/app/private.send` dành cho sender và `/user/queue/messages` dành cho receiver.

## 17. Topic theo phòng hoặc tenant: destination pattern chưa đủ

Một app có:

```text
/topic/rooms/42
/topic/rooms/43
/topic/tenants/alpha/events
/topic/tenants/beta/events
```

Viết:

```java
messages
    .simpSubscribeDestMatchers("/topic/rooms/**")
    .authenticated();
```

cho mọi user authenticated có thể subscribe tất cả các rooms nếu không có policy bổ sung. Đó là **Broken Object Level Authorization** ở tầng messaging.

Phải kiểm tra **room membership/tenant**:

```text
ALLOW SUBSCRIBE /topic/rooms/{roomId}
  iff authenticated
  AND membership(subject, roomId) ACTIVE
  AND room.tenantId in subject.authorizedTenants
  AND room.visibility allows subscription
```

Và riêng quyền SEND:

```text
ALLOW MESSAGE /app/rooms/{roomId}/send
  iff authenticated
  AND senderCanPost(subject, roomId)
  AND room writable
  AND payload/content valid
```

Có thể có read-only members được SUBSCRIBE nhưng không được SEND, moderators được SEND nhưng không xem một số restricted channels, và system service được publish nhưng không có user room membership.

### Custom AuthorizationManager khi có path variables

Builder `.access(...)` nhận `AuthorizationManager<MessageAuthorizationContext<?>>` để tạo policy động. Hãy dùng context destination variables (nếu matcher hỗ trợ) và Authentication từ supplier để kiểm tra membership **server-side**.

Pseudocode (đây **không phải class hoàn chỉnh**):

```java
messages
    .simpSubscribeDestMatchers("/topic/rooms/{roomId}")
    .access((authentication, context) -> {
        String roomId = context.getVariables().get("roomId");
        boolean permitted = roomPolicy.canSubscribe(
                authentication.get(), roomId);
        return new AuthorizationDecision(permitted);
    });
```

Nếu `roomPolicy.canSubscribe` truy vấn database đồng bộ, cần tính toán hiệu năng vì authorization message thường chạy trong interceptor; dùng cache/transaction boundaries đúng và không blocking vô hạn. Không lấy roomId từ payload chưa validate, phải canonicalize và đối chiếu tenant. Với custom manager, **null/abstain hoặc lỗi** không được đổi thành PERMIT.

## 18. Vì sao revoke quyền cần xử lý subscription đang tồn tại?

Giả sử Alice subscribe `/topic/tenants/alpha/events` lúc 10:00 khi membership ACTIVE. Đến 10:15, admin thu hồi membership. Nếu kết nối còn sống, broker có thể tiếp tục gửi event cho session cũ trừ khi app có cơ chế xử lý.

Tài liệu Spring Security xác nhận authorization áp dụng tại **clientInboundChannel**; nó không tự tái xét tất cả outgoing messages. Do đó:

- Thu hồi membership không nhất thiết tự làm broker hủy một subscription đã cấp.
- Khi cần revoke nhanh, ứng dụng cần chủ động hủy subscription/session hoặc kiểm soát publisher-side audience.
- Có thể phát event revoke, disconnect session hoặc duy trì subscription registry gắn user/tenant/room.
- Với dữ liệu cực kỳ nhạy cảm, không chỉ rely vào quyền lúc SUBSCRIBE; cần cân nhắc kiểm soát khả năng gửi/nhận theo phiên bản entitlement.
- Một token JWT hết hạn trong khi socket còn mở cần policy session lifetime/re-authentication, không mặc định đã tự hết mọi quyền nếu không có cơ chế.

Điểm này là khác biệt lớn so với HTTP request ngắn: **SUBSCRIBE tạo trạng thái được duy trì**. Chỉ nhìn một successful SUBSCRIBE test ban đầu không đủ khi hệ thống có đổi quyền theo thời gian.

## 19. Phân biệt quyền publish của server và SEND từ client

Server có thể phát:

```java
messaging.convertAndSend(
        "/topic/system/announcements",
        new Announcement("Bảo trì hệ thống"));
```

Việc này đi theo đường application/broker, không đồng nghĩa client `MESSAGE` tới cùng topic được phép. Để chống giả mạo:

1. Chặn inbound `MESSAGE /topic/system/**`.
2. Chỉ các server components trusted có thể gọi publisher.
3. Nếu có admin-originated announcements, tạo `/app/system.announce` và guard cao hơn.
4. Ở method/service, kiểm tra role/scope và audit người đã thực hiện.
5. Không trông vào `sender` trong payload để phân biệt system message với user message.
6. Nếu broker external expose credentials, hạn chế broker publisher account theo namespace.
7. Các subscribers phải được cấp read permission riêng; thông báo không public thì không dùng `permitAll()`.

**Bảo vệ một topic cần bảo vệ cả chiều publish lẫn chiều subscribe**; đó là hai quy tắc khác nhau. Nếu nguồn publish là scheduled job, REST controller hoặc service event, phải đánh giá quyền ở **nguồn dữ liệu** tương ứng.

## 20. Test end-to-end bằng STOMP client: cần thêm gì ngoài unit tests?

Một test end-to-end có thể dùng `WebSocketStompClient`, `SockJsClient` hoặc client STOMP hỗ trợ handshake credentials. Quy trình:

1. Start Spring application trên random port, cấu hình identity test.
2. Client A handshake với principal CHAT_READ và CSRF policy hợp lệ.
3. Client A gửi SUBSCRIBE `/topic/chat.public`.
4. Client B handshake với principal CHAT_SEND, gửi SEND `/app/chat.send`.
5. Assert client A nhận đúng MESSAGE do server tạo với `sender` là principal của B.
6. Client A thử SEND `/topic/chat.public` và xác nhận **không** có fake MESSAGE được phát cho subscribers.
7. Client B không có CHAT_READ thử SUBSCRIBE topic, assert denied.
8. Test anonymous CONNECT và malicious Origin, invalid/missing STOMP CSRF.
9. Test socket re-connect, session cleanup và permission revoke.
10. Dùng timeout hữu hạn/cancellation, không để tests treo.

Ví dụ giả mã test client (không phải file tự chạy độc lập):

```java
StompSession reader = connectAuthenticated("reader");
StompSession writer = connectAuthenticated("writer");

subscribe(reader, "/topic/chat.public");
send(writer, "/app/chat.send", "{\"text\":\"hello\"}");
assertReceivedFromServer("writer", "hello");

send(reader, "/topic/chat.public", "{\"sender\":\"system\"}");
assertNoForgedBroadcast();
```

Helpers như `connectAuthenticated`/`assertNoForgedBroadcast` phải được implement với token CSRF/origin/session phù hợp; đừng coi pseudocode là integration test đã chạy.

### Vì sao unit tests mục 14 vẫn cần?

End-to-end tests phụ thuộc port, scheduler, transport và session state nên khó debug khi thất bại. Unit tests của `AuthorizationManager<Message<?>>` cho phép xác nhận ma trận type+destination nhanh và rõ. Sau đó integration tests kiểm tra đường wiring thực và CSRF/transport.

## 21. Các anti-pattern nghiêm trọng

**1. Dùng `simpDestMatchers("/topic/**").hasRole("USER")` để cấp quyền đọc.** Matcher không giới hạn SUBSCRIBE, dễ mở inbound MESSAGE.

**2. Cho client SEND trực tiếp tới broker prefix.** Có thể bypass controller validation và giả mạo nguồn phát.

**3. Nghĩ rằng server STOMP MESSAGE và inbound SimpMessageType.MESSAGE là cùng một hướng.** Dễ đặt sai matcher.

**4. Dùng `simpMessageDestMatchers` cho quyền subscribe.** Không match SUBSCRIBE; subscription có thể rơi vào rule khác ngoài dự kiến.

**5. Dùng `simpSubscribeDestMatchers` cho quyền gửi.** SEND không được kiểm tra bởi matcher chỉ dành cho SUBSCRIBE.

**6. Thiếu `anyMessage().denyAll()`.** Dễ bỏ sót destination/types khi thêm chức năng.

**7. Đặt một rule `permitAll()` rộng trước deny rules.** Catch-all phía sau không còn hiệu lực cho các messages đã match.

**8. Cho phép `SUBSCRIBE /queue/**` trực tiếp.** Có thể vượt ranh giới user destination/session.

**9. Cho phép subscribe mọi room khi chỉ authenticated.** Không có room membership/tenant check.

**10. Chỉ bảo vệ CONNECT và cho rằng các SEND/SUBSCRIBE đều được phép.** CONNECT là authentication/protocol, không phải quyền business.

**11. Dựa vào STOMP `login/passcode` mà chưa bật custom authentication interceptor.** Mặc định Spring dựa vào HTTP Principal.

**12. Dùng bearer token trong URL query.** Có thể lộ trong logs/referrer/monitoring; thiết kế trusted channel phù hợp.

**13. Vô hiệu hóa CSRF toàn app để SockJS hoạt động.** Tăng nguy cơ cross-site WebSocket hijacking.

**14. Cho browser WebSocket từ mọi origin mà không có policy.** Không có same-origin enforcement giống fetch tự động.

**15. Tin `from/username/tenant` trong JSON client.** Có thể giả mạo sender và routing cross-tenant.

**16. Revoke quyền nhưng giữ subscription cũ vô hạn.** Broker có thể tiếp tục đẩy dữ liệu.

**17. Để hệ thống broadcast vào topic nhạy cảm mà không kiểm tra người subscribe.** Outbound channel không mặc định reauthorize từng message.

**18. Test chỉ happy path SEND thành công.** Không phát hiện reader SEND vào topic hoặc writer SUBSCRIBE ngoài quyền.

**19. Dùng Spring MVC `@PreAuthorize` cho một controller nhưng quên inbound broker authorization.** Client có thể bypass controller qua broker route.

**20. Đưa role SEND và SUBSCRIBE thành một `ROLE_USER` chung khi policy khác nhau.** Không thể biểu diễn read-only và write-only members.

## 22. Ma trận kiểm thử production

| # | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 1 | CHAT_SEND MESSAGE /app/chat.send | PERMIT |
| 2 | CHAT_SEND SUBSCRIBE /topic/chat.public | DENY nếu không CHAT_READ |
| 3 | CHAT_READ SUBSCRIBE /topic/chat.public | PERMIT |
| 4 | CHAT_READ MESSAGE /topic/chat.public | DENY |
| 5 | CHAT_READ MESSAGE /app/chat.send | DENY |
| 6 | CHAT_SEND+CHAT_READ MESSAGE /topic/chat.public | DENY |
| 7 | CHAT_SEND+CHAT_READ SUBSCRIBE /topic/chat.public | PERMIT |
| 8 | CHAT_SEND+CHAT_READ MESSAGE /app/chat.send | PERMIT |
| 9 | Authenticated SUBSCRIBE /user/queue/errors | PERMIT nếu đúng contract |
| 10 | Authenticated SUBSCRIBE /queue/private | DENY |
| 11 | SUBSCRIBE /app/chat.send | DENY |
| 12 | MESSAGE /app/unknown | DENY |
| 13 | MESSAGE/SUBSCRIBE thiếu destination | DENY |
| 14 | Anonymous CONNECT | DENY |
| 15 | Authenticated CONNECT thiếu CSRF | Từ chối theo STOMP CSRF policy |
| 16 | Handshake Origin không nằm allowlist | Từ chối |
| 17 | Payload giả `sender=system` | Server gán principal thật hoặc deny |
| 18 | Tenant alpha SUBSCRIBE topic beta | DENY |
| 19 | Read-only room member SEND room | DENY |
| 20 | Write-only room member SUBSCRIBE room | DENY nếu policy không cho đọc |
| 21 | Membership bị revoke lúc socket mở | Ngừng nhận dữ liệu theo revocation SLA |
| 22 | Admin logout/token expires | Session/policy không tiếp tục grant vô hạn |
| 23 | External broker relay credentials sai | Không có unauthorized publish/subscribe |
| 24 | Server emits announcement | Chỉ subscribers được phép nhận |
| 25 | Client SEND vào /topic/system/** | Không giả mạo được announcement |

Một test chỉ assert `AuthorizationManager` trả false chưa chứng minh toàn bộ outbound leak đã bị ngăn. Khi cần bảo vệ dữ liệu nhạy cảm, assert **client không nhận message không được phép** và kiểm tra broker/session cleanup.

## 23. Cách debug khi SEND hoặc SUBSCRIBE trả lỗi

Câu hỏi đầu tiên không phải “user có ROLE_USER không?” mà là:

1. **Frame type là gì?** STOMP SEND → inbound `SimpMessageType.MESSAGE`; SUBSCRIBE → `SimpMessageType.SUBSCRIBE`.
2. **Destination là gì?** `/app/chat.send` hay `/topic/chat.public`? Có prefix biến đổi trước matcher không?
3. **Message đi vào channel nào?** `clientInboundChannel` hay server `brokerChannel`?
4. **User được xác thực chưa?** HTTP handshake Principal hoặc custom CONNECT interceptor?
5. **Authorities thực tế là gì?** `CHAT_SEND`/`CHAT_READ`/roles/scopes đúng contract?
6. **Matcher nào đứng trước?** Một `simpDestMatchers` rộng có thể match cả hai types.
7. **Default deny?** Unmatched message có bị deny thay vì abstain?
8. **CSRF/origin?** CONNECT có được reject trước khi đến MESSAGE/SUBSCRIBE?
9. **Controller có được gọi?** SEND vào `/app` có match `@MessageMapping`?
10. **Broker có subscription?** SUBSCRIBE đã được chấp nhận nhưng broker chưa có event để phát?
11. **User destination?** Client subscribe `/user/queue/...` đúng logical prefix?
12. **Tenant/room membership?** Destination đúng format nhưng user không được subscribe room đó?
13. **Subscription đang cũ?** Entitlement đã đổi nhưng socket chưa bị đóng?
14. **Broker relay?** Broker account/routing/permissions có khác simple broker không?

Logs/metrics cần chứa tối thiểu: user alias, STOMP type, canonical destination (có thể hash tenant/room), policy rule ID, permit/deny, session ID alias và reason code. Không log bearer tokens, STOMP credentials hoặc payload chứa PII. Tránh các metric labels theo raw roomId/sessionId vì cardinality cao.

## 24. Checklist cấu hình an toàn

- [ ] Hiểu STOMP SEND là `SimpMessageType.MESSAGE` inbound, SUBSCRIBE là `SimpMessageType.SUBSCRIBE`.
- [ ] `simpMessageDestMatchers` dùng cho SEND/application actions.
- [ ] `simpSubscribeDestMatchers` dùng cho nhận dữ liệu/broker topics.
- [ ] Không dùng `simpDestMatchers` chung cho một topic read-only mà quên type guard.
- [ ] Chặn client MESSAGE đến `/topic/**` và `/queue/**` khi broker publish là server-only.
- [ ] Chặn client SUBSCRIBE trực tiếp tới physical `/queue/**` không có policy.
- [ ] `/app/**` chỉ mở các action được controller/service bảo vệ.
- [ ] Có catch-all deny cho unmatched MESSAGE/SUBSCRIBE và message types.
- [ ] Handshake và STOMP CONNECT có authentication/CSRF/origin rules được test.
- [ ] Không tin STOMP login/passcode hoặc bearer header chưa verify.
- [ ] Không lấy sender/recipient/tenant từ JSON client làm nguồn identity.
- [ ] Các SEND actions kiểm tra object/tenant policy và payload trước khi publish.
- [ ] SUBSCRIBE room/tenant/private queues kiểm tra membership thực tế.
- [ ] Subscription cũ được revoke/hủy khi entitlement đổi theo SLA.
- [ ] Simple broker hoặc external relay không cấp client quyền publish ngoài dự kiến.
- [ ] Unit test đúng ma trận MESSAGE/SUBSCRIBE trên cùng destination.
- [ ] Integration test dùng STOMP client xác nhận không có fake broadcast/data leak.
- [ ] Có tests token expiration, disconnect, reconnect, SockJS/CSRF/origin.
- [ ] Monitoring tách auth failure, SEND deny, SUBSCRIBE deny, broker error.

**Kết luận:** Spring Security message authorization không thể chỉ hỏi **“đích là /topic/chat.public?”**. Câu hỏi đúng là **“caller đang gửi MESSAGE hay đăng ký SUBSCRIBE tới destination nào, với quyền và dữ liệu nào?”**. Cho phép SUBSCRIBE không cấp quyền SEND, cho phép SEND vào application endpoint không cấp quyền publish trực tiếp vào broker, và CONNECT thành công không thay thế kiểm tra object/tenant cho từng hành động. Tách chính xác loại thông điệp và destination, áp dụng default deny, rồi kiểm thử cả hai chiều để ngăn giả mạo sự kiện và rò dữ liệu.

## Tài liệu chính thức

- [Spring Security 6.5 — WebSocket Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html)
- [Spring Security — WebSocket Security (current)](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [Spring Security 6.5 — MessageMatcherDelegatingAuthorizationManager.Builder JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html)
- [Spring Security 6.5 — AuthorizationManager JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Framework — STOMP Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework — STOMP Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Framework — STOMP User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html)
