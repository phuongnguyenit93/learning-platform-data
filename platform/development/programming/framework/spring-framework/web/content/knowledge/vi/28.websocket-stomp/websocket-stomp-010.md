# Xác thực, phân quyền destination, heartbeat và phục hồi kết nối với WebSocket/STOMP

## 1. Bối cảnh và bốn lớp trách nhiệm

Khi xây dựng ứng dụng trò chuyện, thông báo hay bảng số liệu thời gian thực bằng Spring WebSocket và STOMP, mở được kết nối chỉ là bước đầu. Hệ thống cần trả lời bốn câu hỏi xuyên suốt vòng đời kết nối:

1. **Xác thực (authentication):** Ai đang kết nối? Danh tính nào có thể tin cậy?
2. **Phân quyền (authorization):** Danh tính đó được gửi (`SEND`) và đăng ký nhận (`SUBSCRIBE`) những destination nào?
3. **Heartbeat:** Làm sao phát hiện kết nối không còn trao đổi dữ liệu, đặc biệt khi TCP/WebSocket chưa báo đóng ngay?
4. **Phục hồi kết nối (reconnection):** Sau mất mạng, client có thể kết nối, xác thực, đăng ký nhận lại như thế nào, và làm sao tránh mất/trùng dữ liệu?

Trong STOMP over WebSocket, mỗi lớp diễn ra ở một giai đoạn khác nhau:

```text
Browser / ứng dụng client
       |
       | HTTP GET /ws, Upgrade: websocket, Cookie/Origin
       v
[HTTP Security + Origin + WebSocket handshake]
       |
       | WebSocket mở, có thể đã gắn Principal từ HTTP
       v
[STOMP CONNECT: phiên STOMP, heartbeat negotiation, CSRF/token nếu cấu hình]
       |
       | CONNECTED
       v
[STOMP SEND, SUBSCRIBE, UNSUBSCRIBE]
       |                 |
       v                 v
/app/** -> Controller    /topic/**, /queue/** -> Message broker
       |
       v
[Message authorization: kiểm tra loại frame + destination + Principal]
       |
       v
[Heartbeats & giám sát phiên]
       |
       | mất kết nối / broker lỗi / auth hết hạn
       v
[Client reconnect -> CONNECT mới -> xác thực lại -> SUBSCRIBE lại]
```

Cần giữ các ranh giới rõ ràng:

- **HTTP handshake được phép** không có nghĩa được gửi/nhận mọi message.
- **Principal đã xác thực** không có nghĩa được truy cập dữ liệu thuộc tài khoản khác.
- **Heartbeat phát hiện sự im lặng/kết nối chết**, không thay thế xác thực, xác nhận giao hàng hay transaction.
- **Kết nối lại thành công** không có nghĩa mọi message trong lúc mất mạng đã được khôi phục.

Bài này dùng Spring Framework với STOMP message broker trên stack Servlet (Spring MVC/Spring Security 6, Java 17+) làm ví dụ. Raw WebSocket hoặc WebFlux không dùng STOMP sẽ có API và quy trình bảo mật khác. Với môi trường phát triển mới, áp dụng phiên bản Spring/Spring Security phù hợp bộ dependency của dự án.

## 2. Xác thực ở HTTP handshake và STOMP CONNECT

### 2.1 Trường hợp thông dụng: HTTP authentication được mang sang STOMP session

STOMP over WebSocket bắt đầu bằng HTTP handshake. Nếu ứng dụng xác thực người dùng qua Spring Security bằng cookie/session, Spring có thể lấy `Principal` từ request HTTP, liên kết nó với WebSocket session, rồi đưa Principal vào các message STOMP của phiên đó.

```text
HTTP login (Spring Security) -> HTTP session/cookie
          |
          v
GET /ws (WebSocket upgrade)
          |
          v
Spring Security xác thực request, lấy Principal
          |
          v
Spring WebSocket lưu người dùng cho WebSocket/STOMP session
          |
          v
STOMP SEND / SUBSCRIBE -> user header -> authorization
```

Ví dụ: Alice đã đăng nhập, kết nối `wss://api.example.com/ws` từ trang được phép. Các frame của phiên có thể được Spring liên kết với `Principal` Alice. Ở `@MessageMapping`, controller có thể nhận tham số `java.security.Principal` hoặc `Authentication` theo tích hợp Security.

Chú ý: STOMP định nghĩa native headers `login` và `passcode` cho CONNECT, nhưng Spring mặc định **không dùng** chúng để xác thực lại phiên STOMP over WebSocket khi hệ thống dựa vào HTTP authentication. Không được tin giá trị client tự đặt ở `login` hoặc `X-User-Id` nếu server chưa kiểm chứng.

### 2.2 Ví dụ bảo vệ endpoint WebSocket ở HTTP layer

**Tệp `HttpSecurityConfig.java`:**

```java
package com.example.chat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class HttpSecurityConfig {

    @Bean
    SecurityFilterChain httpSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/ws", "/ws/**").authenticated()
                .anyRequest().authenticated());
        http.formLogin(withDefaults());
        return http.build();
    }
}
```

Đây là ví dụ cấu hình Spring Security cho Servlet/MVC, không phải chương trình Java độc lập và không phải `SecurityWebFilterChain` của WebFlux. Nó yêu cầu người dùng đã xác thực đối với `/ws` và toàn bộ route khác (đây là chính sách mặc định **minh họa**, cần điều chỉnh route công khai trong ứng dụng thực). `formLogin` thể hiện trường hợp đăng nhập dựa trên session; một sản phẩm API dùng OAuth2/JWT hoặc SSO cần cơ chế xác thực tương ứng.

Không vô hiệu hóa CSRF trên toàn hệ thống chỉ vì có WebSocket. Tùy cách bật Spring Security WebSocket, CONNECT có thể phải mang CSRF token để chống tấn công từ trang khác. Đối với SockJS fallback, nếu cần ngoại lệ HTTP CSRF cho các transport POST, giới hạn ngoại lệ vào endpoint cần thiết và duy trì bảo vệ STOMP CONNECT.

### 2.3 Vai trò của Origin và giới hạn của nó

Origin là nguồn gốc trang web trong browser, ví dụ `https://app.example.com`. Browser không đơn giản áp dụng quy tắc same-origin cho WebSocket như cho XMLHttpRequest; server phải giới hạn Origin được phép, đặc biệt khi cookie/session được gửi tự động.

```java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com");
}
```

Đoạn này thuộc `WebSocketMessageBrokerConfigurer` (cấu hình đầy đủ ở phần sau). `setAllowedOrigins` kiểm tra Origin ở handshake; không phân quyền `/topic/private` hay xác thực danh tính. Client ngoài browser có thể tự đặt Origin, vì vậy **Origin không phải cơ chế xác thực**. Với site nhiều origin, khai báo allowlist cụ thể; tránh `*` cho endpoint cần session/cookie. Nếu dùng proxy, cần thiết lập forwarded headers đáng tin cậy để không sai scheme/host.

### 2.4 Trường hợp token nằm trong STOMP CONNECT

Browser `WebSocket` API thường không cho ứng dụng JavaScript tùy ý gắn HTTP Authorization header cho handshake. Một số hệ thống xác thực ở frame STOMP CONNECT bằng header `Authorization: Bearer ...` do thư viện STOMP gửi **sau khi WebSocket đã mở**.

Quy trình đúng:

1. Client lấy token từ nguồn đáng tin cậy và đưa token vào native STOMP CONNECT header, không đặt user ID tùy ý rồi tin nó.
2. `ChannelInterceptor` được đăng ký trên `clientInboundChannel` đọc token của frame CONNECT.
3. Server kiểm chứng chữ ký/issuer/audience/thời hạn/trạng thái tài khoản bằng cơ chế authentication thực.
4. Chỉ khi token hợp lệ, tạo `Authentication` phù hợp và gọi `StompHeaderAccessor.setUser(authentication)` trên CONNECT.
5. Spring ghi nhận Principal đó cho những STOMP message tiếp theo cùng phiên; message authorization dùng Principal đã xác thực.
6. Cần bảo đảm interceptor xác thực chạy **trước** interceptor Spring Security dùng để phân quyền.

**Mẫu code minh họa tích hợp một bộ kiểm chứng có thật (không tự chứa logic kiểm chứng JWT):**

```java
package com.example.chat;

import java.util.List;
import java.util.function.Function;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;

public final class BearerConnectInterceptor implements ChannelInterceptor {

    private final Function<String, Authentication> tokenVerifier;

    public BearerConnectInterceptor(
            Function<String, Authentication> tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor =
                MessageHeaderAccessor.getAccessor(
                        message, StompHeaderAccessor.class);

        if (accessor == null
                || accessor.getCommand() != StompCommand.CONNECT) {
            return message;
        }

        List<String> values =
                accessor.getNativeHeader("Authorization");

        if (values == null || values.size() != 1
                || !values.get(0).startsWith("Bearer ")) {
            throw new BadCredentialsException("Missing bearer token");
        }

        String token = values.get(0).substring("Bearer ".length());
        if (token.isBlank()) {
            throw new BadCredentialsException("Empty bearer token");
        }

        Authentication authentication = tokenVerifier.apply(token);
        if (authentication == null || !authentication.isAuthenticated()) {
            throw new BadCredentialsException("Invalid bearer token");
        }

        accessor.setUser(authentication);
        return message;
    }
}
```

Code trên hoàn chỉnh về cấu trúc Java, nhưng **không tự xác thực một token**: tham số `tokenVerifier` phải là hàm đã được cấp bởi dịch vụ bảo mật có thật, kiểm tra signature, expiry, issuer/audience và trạng thái người dùng. Không dùng `token -> new UsernamePasswordAuthenticationToken("alice", ... )` như một hàm xác thực sản phẩm. Khi token sai, ví dụ ném `BadCredentialsException` để server từ chối CONNECT theo pipeline.

Đăng ký interceptor trong một class cấu hình riêng có thứ tự cao nếu tích hợp message authorization của Spring Security:

```java
@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
class StompAuthChannelConfig
        implements WebSocketMessageBrokerConfigurer {

    private final BearerConnectInterceptor interceptor;

    StompAuthChannelConfig(BearerConnectInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void configureClientInboundChannel(
            ChannelRegistration registration) {
        registration.interceptors(interceptor);
    }
}
```

Đây là đoạn class **bổ sung**; cần import `Configuration`, `Order`, `Ordered`, `ChannelRegistration` và `WebSocketMessageBrokerConfigurer`. Phải có Spring bean `BearerConnectInterceptor` do ứng dụng tạo cùng verifier. Cách đăng ký theo `@Order` thể hiện nhu cầu chạy trước message security, không tự đảm bảo trình tự nếu ứng dụng có nhiều cấu hình không kiểm soát. Một thiết kế cookie/session thường không cần interceptor bearer này.

**Lưu ý quan trọng về CSRF:** `@EnableWebSocketSecurity` của Spring Security có chính sách kiểm tra CSRF trong CONNECT. Kể cả token xác thực hợp lệ, CONNECT có thể bị từ chối nếu thiếu CSRF token theo cấu hình. Tích hợp cookie/session và cấu hình token-based phải thiết kế cùng chính sách an ninh; không tự tắt bảo vệ mà chưa phân tích mô hình đe dọa.

## 3. Phân quyền theo message type và destination

### 3.1 Destination của STOMP là gì?

Với broker được cấu hình:

- `/ws` là **HTTP URL bắt đầu WebSocket/STOMP session**.
- `/app/**` là **application destination**, thường chuyển message `SEND` đến `@MessageMapping` trong ứng dụng.
- `/topic/**` là convention cho nơi phát tin đến nhiều subscriber khi dùng simple broker.
- `/queue/**` là convention thường dùng cho kênh hàng đợi/thông điệp riêng; với Spring simple broker, tiền tố không tự mang bảo đảm point-to-point như một message broker chuyên dụng.
- `/user/**` là **cú pháp user destination của Spring**, thường chuyển các subscription thành destination riêng của từng WebSocket session hoặc user sau khi qua resolver.

Client gửi `SEND /app/chat` và `SUBSCRIBE /topic/announcements` là hai hành động khác nhau, dù đều có `destination`. Không được phân quyền chỉ bằng tiền tố đường dẫn mà quên **loại message**.

Ví dụ:

```text
SEND       /app/chat                   -> controller message
SEND       /topic/announcements        -> phải bị chặn với client thường
SUBSCRIBE  /topic/announcements        -> có thể cho phép
SUBSCRIBE  /user/queue/notifications   -> yêu cầu user xác thực
SUBSCRIBE  /topic/admin                -> chỉ dành role ADMIN
```

Nếu cho client `SEND` trực tiếp đến `/topic/admin`, client có thể phát thông điệp giả như đến từ server, tùy cấu hình broker. Nếu cho user thường `SUBSCRIBE /topic/admin`, họ có thể thấy thông tin không thuộc quyền. Vì vậy phải viết chính sách riêng cho SEND và SUBSCRIBE, mặc định từ chối trường hợp chưa liệt kê.

### 3.2 Spring Security: AuthorizationManager cho STOMP messages

Spring Security hỗ trợ `@EnableWebSocketSecurity` và `MessageMatcherDelegatingAuthorizationManager` để phân quyền các message inbound. Một cấu hình minh họa:

**Tệp `StompMessageSecurityConfig.java`:**

```java
package com.example.chat;

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
            .nullDestMatcher().authenticated()
            .simpSubscribeDestMatchers("/topic/admin/**")
                .hasRole("ADMIN")
            .simpSubscribeDestMatchers(
                    "/topic/announcements",
                    "/user/queue/notifications")
                .hasRole("USER")
            .simpDestMatchers("/app/**").hasRole("USER")
            .simpTypeMatchers(
                    SimpMessageType.MESSAGE,
                    SimpMessageType.SUBSCRIBE)
                .denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

**Giải thích thứ tự:**

1. `nullDestMatcher().authenticated()` đòi hỏi người dùng đã xác thực đối với message không có destination. Những message mang ý nghĩa phiên như CONNECT/DISCONNECT thường thuộc nhóm này.
2. `simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")` đặt trước rule rộng hơn để tránh cấp nhầm quyền nhận tin quản trị.
3. `simpSubscribeDestMatchers("/topic/announcements", "/user/queue/notifications").hasRole("USER")` cho ROLE_USER đăng ký hai vùng đã phê duyệt.
4. `simpDestMatchers("/app/**").hasRole("USER")` áp dụng cho destination ứng dụng; nếu cần chỉ cho phép `SEND`, hãy bổ sung matcher/rule cụ thể tương ứng và kiểm thử loại message.
5. Các `MESSAGE` hoặc `SUBSCRIBE` còn lại bị từ chối; cuối cùng từ chối mọi loại message không được liệt kê.

Chính sách minh họa yêu cầu **ROLE_USER** cho `/user/queue/notifications` và `/topic/announcements`; tài khoản có đúng ROLE_ADMIN nhưng không có ROLE_USER sẽ chỉ đạt những rule dành ADMIN, trừ khi hệ thống quy định role hierarchy. Vì vậy cần thiết kế role rõ ràng; không tự giả định ADMIN đương nhiên bao gồm USER.

**Điểm kỹ thuật:** `@EnableWebSocketSecurity` bảo vệ STOMP inbound, không phải thay cho cấu hình Spring Security trên HTTP handshake. Các interceptor có thứ tự xử lý; nếu xác thực bằng STOMP CONNECT token, đặt authentication interceptor trước authorization interceptor. Khi Spring Security kiểm tra CSRF trên CONNECT, client phải gửi token theo hợp đồng bảo mật tương ứng.

### 3.3 Những điều matcher destination chưa làm thay bạn

Một rule `.simpSubscribeDestMatchers("/topic/rooms/**").hasRole("USER")` chỉ chứng minh người dùng có role USER; nó **không tự chứng minh** người dùng thuộc từng phòng cụ thể. Nếu dữ liệu có phạm vi `tenantId`, `roomId` hoặc `documentId`, authorization phải kiểm tra quyền đối với đối tượng đó.

Ví dụ `/topic/rooms/123`: người dùng Alice có ROLE_USER nhưng không nằm trong phòng 123 phải bị từ chối. Có thể xây `AuthorizationManager<Message<?>>` tùy biến để lấy thông tin Principal, message type, destination, kiểm tra membership qua dịch vụ tin cậy rồi trả quyết định. Không chấp nhận `roomId` hoặc `userId` do client đưa lên như chứng cứ quyền. Có thể thiết kế để client `SUBSCRIBE` một user destination, còn server chỉ phát những sự kiện mà user được phép xem.

Khi dùng user destinations, `/user/queue/notifications` là địa chỉ client subscribe; `SimpMessagingTemplate.convertAndSendToUser(username, "/queue/notifications", payload)` là một cách server gửi đến người dùng. Resolver có thể chuyển thành destination cụ thể của session. **Đừng coi chuỗi tên user trong địa chỉ là bằng chứng quyền truy cập.**

### 3.4 Kiểm tra quyền SEND còn quan trọng trong controller

Trong controller, kiểm tra user hoặc `Authentication` theo chính sách nghiệp vụ. Ví dụ mã minh họa đã có `Principal` từ HTTP/STOMP security:

**Tệp `ChatMessageController.java`:**

```java
package com.example.chat;

import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class ChatMessageController {

    @MessageMapping("/echo")
    @SendToUser("/queue/echo")
    public String echo(String body, Principal principal) {
        if (principal == null) {
            throw new IllegalStateException("Authentication required");
        }
        return principal.getName() + ": " + body;
    }
}
```

Khi `setApplicationDestinationPrefixes("/app")`, client `SEND /app/echo` sẽ đến phương thức có `@MessageMapping("/echo")` nếu message authorization cho phép. Với `@SendToUser("/queue/echo")`, client phù hợp thường subscribe `/user/queue/echo`. Nếu áp dụng đúng cấu hình authorization ở mục 3.2, cần **bổ sung rule** cho `/user/queue/echo` trước khi test, vì rule minh họa chỉ cho `/user/queue/notifications`; mặc định sẽ từ chối địa chỉ khác. Đây là tính năng bảo vệ có chủ đích của chiến lược deny-by-default, không phải lỗi broker.

Ví dụ echo không thể thay thế kiểm tra membership đối với nghiệp vụ chat thực: nếu body chứa room ID, controller/service vẫn phải xác minh user là thành viên trước khi gửi tin vào phòng đó.

## 4. Cấu hình broker và endpoint đồng bộ với bảo mật

**Tệp `ChatWebSocketConfig.java`:**

```java
package com.example.chat;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class ChatWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Đây là cấu hình cơ sở cho ứng dụng Spring MVC + WebSocket message broker. Khai báo `enableSimpleBroker` tạo broker đơn giản trong bộ nhớ, phù hợp đào tạo và các hệ thống nhỏ; nó **không tương đương** RabbitMQ/ActiveMQ về lưu trữ, phân phối nhiều node, xác nhận giao hàng, độ bền message hay quản lý offline.

Các class bảo mật ở phần 2–3 bổ sung theo nhu cầu. Cần quyết định **một** chiến lược authentication chính ở HTTP hay CONNECT token, rồi kiểm soát các channel và CSRF nhất quán. Khi tích hợp nhiều `WebSocketMessageBrokerConfigurer`, hãy hiểu thứ tự đăng ký interceptor và cài đặt cấu hình theo ứng dụng.

Dùng Spring Boot 3.x, Java 17+ và Gradle với Spring dependency management, dependencies điển hình:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-messaging'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đặt các tệp Java vào đúng package và source set. Chúng là những thành phần cấu hình cho một ứng dụng Spring Boot có entry point; không thể chạy riêng bằng `javac ChatWebSocketConfig.java` nếu thiếu classpath Spring. Với dự án có Spring Boot dependency management, phiên bản của thư viện Spring nên được quản lý đồng bộ thay vì trộn các JAR không tương thích.

## 5. STOMP heartbeat: thương lượng thời gian và phát hiện kết nối chết

### 5.1 Heartbeat của STOMP là gì?

Kể từ STOMP 1.1, frame `CONNECT`/`CONNECTED` có thể khai báo header `heart-beat: x,y` theo mili giây. Thông thường:

- Phía client `CONNECT heart-beat: cx,cy`: `cx` là thời gian tối thiểu mong muốn giữa các lần client **có thể gửi** heartbeat; `cy` là thời gian tối thiểu client **muốn nhận** dữ liệu/heartbeat từ server.
- Phía server `CONNECTED heart-beat: sx,sy`: `sx` là thời gian tối thiểu server **có thể gửi**; `sy` là thời gian tối thiểu server **muốn nhận** từ client.
- Nếu một phía khai báo `0` cho một chiều gửi hoặc nhận tương ứng, chiều đó có thể không được bật heartbeat.
- Khi cả hai phía đồng ý, khoảng dự kiến **client → server** là `max(cx, sy)`; **server → client** là `max(sx, cy)`.

Ví dụ:

```text
Client: CONNECT   heart-beat:10000,10000
Server: CONNECTED heart-beat:10000,20000

client -> server: max(10000, 20000) = 20000 ms
server -> client: max(10000, 10000) = 10000 ms
```

Đây là **khoảng hoạt động trao đổi dự kiến**, không phải cam kết hệ điều hành sẽ gửi đúng từng mili giây. Khi có frame dữ liệu được gửi thường xuyên, không nhất thiết phát thêm heartbeat riêng. Khi luồng im lặng, heartbeat (một byte xuống dòng theo giao thức) giúp phía nhận nhận thấy kênh còn hoạt động.

**Không phải giao thức xác nhận giao hàng:** heartbeat không xác nhận rằng một `SEND` đã được xử lý, ghi database hoặc tới subscriber. Dùng receipt/ACK và cơ chế nghiệp vụ phù hợp nếu cần biết kết quả.

### 5.2 Ví dụ Java chạy độc lập: tính khoảng heartbeat

Mã sau không dùng Spring, chỉ trình bày cách thương lượng thời gian. Chạy được bằng Java 17+:

**Tệp `HeartbeatNegotiationDemo.java`:**

```java
public class HeartbeatNegotiationDemo {

    static long agreedInterval(long senderCanSend,
                               long receiverWantsReceive) {
        if (senderCanSend == 0 || receiverWantsReceive == 0) {
            return 0;
        }
        return Math.max(senderCanSend, receiverWantsReceive);
    }

    public static void main(String[] args) {
        long clientSend = 10_000;
        long clientReceive = 10_000;
        long serverSend = 10_000;
        long serverReceive = 20_000;

        long clientToServer = agreedInterval(
                clientSend, serverReceive);
        long serverToClient = agreedInterval(
                serverSend, clientReceive);

        System.out.println("client -> server: " + clientToServer + " ms");
        System.out.println("server -> client: " + serverToClient + " ms");
        System.out.println("disabled direction: "
                + agreedInterval(0, 10_000) + " ms");
    }
}
```

Lệnh:

```bash
javac HeartbeatNegotiationDemo.java
java HeartbeatNegotiationDemo
```

**Stdout chính xác:**

```text
client -> server: 20000 ms
server -> client: 10000 ms
disabled direction: 0 ms
```

Chương trình giả định các khoảng không âm và không xác minh wire protocol; nó làm rõ quy tắc STOMP heartbeat. Không nên nhầm hàm tính interval này với scheduler thực của client/server.

### 5.3 Bật heartbeat cho Spring simple broker

Simple broker của Spring có thể gửi STOMP heartbeats khi được gắn `TaskScheduler`. Nếu không có scheduler thích hợp, chỉ đặt kỳ vọng heartbeat mà không cấu hình bộ phát có thể khiến client hiểu nhầm phiên bị chết.

Cấu hình mẫu bên dưới là **biến thể** của phương thức `configureMessageBroker`, thay vì cài đồng thời với đoạn `configureMessageBroker` ở phần 4:

```java
package com.example.chat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class HeartbeatWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    private final TaskScheduler scheduler;

    public HeartbeatWebSocketConfig(
            @org.springframework.beans.factory.annotation.Lazy
            TaskScheduler brokerHeartbeatScheduler) {
        this.scheduler = brokerHeartbeatScheduler;
    }

    @Bean
    TaskScheduler brokerHeartbeatScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        return scheduler;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[] {10_000, 20_000})
                .setTaskScheduler(scheduler);
    }
}
```

Khi đưa vào dự án, chọn cấu hình broker **duy nhất**: dùng `HeartbeatWebSocketConfig` **thay cho** `ChatWebSocketConfig` phần 4, không đăng ký hai lớp song song cùng endpoint. Dùng `@Lazy` trong ví dụ vì việc inject `TaskScheduler` vào `WebSocketMessageBrokerConfigurer` có thể gây vòng phụ thuộc ở một số cách tự cấu hình của Spring. Spring cũng có thể cung cấp scheduler riêng; cần kiểm tra các bean hiện hữu và chỉnh qualifier/naming nếu ứng dụng có nhiều scheduler để bảo đảm đúng scheduler được dùng. Bộ nhớ/tài nguyên scheduler phải được Spring quản lý theo vòng đời ứng dụng.

`setHeartbeatValue(new long[]{10000, 20000})` tương ứng khả năng gửi/nhận mong muốn của phía broker. Chu kỳ thật còn phụ thuộc thương lượng với client, scheduler, traffic và thời gian ngưỡng timeout của phía nhận.

### 5.4 Simple broker và broker relay không giống nhau

Với simple broker, message subscriptions nằm trong bộ nhớ ứng dụng; heartbeat do Spring phối hợp scheduler và các phiên WebSocket. Nếu nhiều instance server độc lập, simple broker trên instance A không tự phân phối message đến subscriber trên instance B.

Với external broker relay (RabbitMQ/ActiveMQ tương thích STOMP), ứng dụng chuyển message tới broker bên ngoài. Relay quản lý kết nối **system** tới broker và các kết nối đại diện client; các heartbeat trên kết nối giữa Spring và broker là một tầng khác với việc client nhận STOMP heartbeat qua WebSocket.

Spring broker relay có thể tự thử nối lại **system connection** khi broker mất mạng (tài liệu mô tả khoảng retry mặc định 5 giây), nhưng việc đó **không tự nối lại WebSocket session của client**. Client vẫn cần logic reconnect, xác thực và đăng ký nhận lại. Khi mất kết nối system, server có thể phát `BrokerAvailabilityEvent` để thành phần phát tin biết broker tạm không sẵn sàng.

## 6. Phục hồi kết nối: trạng thái và quy trình chuẩn

### 6.1 Vì sao cần reconnect logic tại client?

Mất Wi-Fi, điện thoại chuyển mạng, proxy idle timeout, server khởi động lại hoặc broker gặp sự cố đều có thể làm WebSocket/STOMP session đóng. WebSocket API không bảo đảm mọi mạng lỗi đều phát một tín hiệu ngay lập tức; heartbeat và transport timeout giúp phát hiện tình huống im lặng.

Một chu trình client điển hình:

```text
DISCONNECTED
     |
     | connect WebSocket
     v
SOCKET_OPEN
     |
     | STOMP CONNECT (+ credential/CSRF + heart-beat)
     v
STOMP_CONNECTED
     |
     | SUBSCRIBE lại các destination được phép
     | đồng bộ lại dữ liệu từ HTTP snapshot + cursor/sequence
     v
READY
     |
     | mất mạng / server close / heartbeat lost
     v
DISCONNECTED
     |
     | trì hoãn retry có giới hạn + jitter/backoff
     +-----> connect lại
```

Khi reconnect thành công, **phiên STOMP mới** thường có session ID mới; các subscription của phiên cũ không còn. Client phải tạo lại subscription sau `CONNECTED`, và server phải kiểm tra lại quyền của user trên phiên mới.

Không nên gửi dữ liệu nghiệp vụ khi ứng dụng chưa biết phiên có khả năng nhận được. Với message có thể gây tác dụng phụ (thanh toán, thao tác quan trọng), cần idempotency key, correlation ID và API xác nhận kết quả, thay vì phát lại mọi `SEND` mù quáng mỗi lần mạng chập chờn.

### 6.2 Browser client với @stomp/stompjs

Thư viện JavaScript `@stomp/stompjs` có cấu hình heartbeat, reconnect delay và callback trạng thái. Ví dụ sau dùng xác thực qua HTTP cookie/session (do trình duyệt gửi theo chính sách cookie thích hợp) và danh sách destination đã được server cho phép.

**Tệp `stomp-client.js`:**

```javascript
import { Client, ReconnectionTimeMode } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "wss://api.example.com/ws",
  reconnectDelay: 1000,
  reconnectTimeMode: ReconnectionTimeMode.EXPONENTIAL,
  maxReconnectDelay: 15000,
  heartbeatOutgoing: 10000,
  heartbeatIncoming: 10000,

  onConnect: () => {
    console.log("STOMP connected");

    // Đăng ký lại mỗi khi có CONNECTED mới.
    client.subscribe("/user/queue/notifications", (message) => {
      const event = JSON.parse(message.body);
      handleNotification(event);
    });
  },

  onStompError: (frame) => {
    console.error("STOMP error:", frame.headers["message"]);
  },

  onWebSocketClose: () => {
    console.info("WebSocket closed; client may reconnect");
  }
});

function handleNotification(event) {
  // Đối chiếu event.id / sequence trước khi cập nhật UI hoặc state.
  console.log("Event received:", event);
}

client.activate();

// Khi người dùng đăng xuất hoặc trang thực sự không cần kết nối:
// await client.deactivate();
```

Đây là mã dùng trong môi trường JavaScript/browser có bundler và đã cài `@stomp/stompjs`. URL phải đổi sang endpoint thực, `wss` cho môi trường HTTPS. Hàm `handleNotification` chỉ demo log sự kiện; ứng dụng thực phải kiểm tra cấu trúc JSON, độ tin cậy và thứ tự nhận tin.

Giải thích các lựa chọn:

- `heartbeatOutgoing`: client đề xuất khoảng gửi heartbeat; `heartbeatIncoming`: mong đợi khoảng nhận.
- `reconnectDelay` kết hợp `ReconnectionTimeMode.EXPONENTIAL`: chờ ban đầu, tăng thời gian khi lỗi lặp, giới hạn bởi `maxReconnectDelay`; giảm nguy cơ nhiều client cùng thử lại liên tục.
- `onConnect` chạy sau mỗi CONNECTED mới; đặt `subscribe` trong callback để subscription được đăng ký lại.
- `onStompError` xử lý STOMP ERROR frame; không thể coi mọi lỗi là lỗi mạng tạm thời. Nếu xác thực thất bại hoặc tài khoản bị vô hiệu hóa, client nên ngừng thử hoặc yêu cầu đăng nhập mới theo chính sách UI.
- `onWebSocketClose` cho biết transport đóng; reconnect phụ thuộc trạng thái client và cấu hình. Không đặt một `setInterval` retry riêng song song với cơ chế thư viện.

Khi component bị hủy hoặc user logout, gọi `await client.deactivate()` để đóng và dừng vòng reconnect. Tránh tạo nhiều `Client` và giữ chúng hoạt động sau khi rời trang gây subscription trùng và tài nguyên bị giữ.

### 6.3 Dùng token trong CONNECT khi reconnect

Với chiến lược token-based, client cần token hợp lệ cho **mỗi** STOMP CONNECT mới. Nếu token ngắn hạn đã hết, phải làm mới từ luồng xác thực an toàn trước khi reconnect. Thư viện cho phép cập nhật `connectHeaders` hoặc `beforeConnect` tùy API.

Mảnh minh họa:

```javascript
client.beforeConnect = async () => {
  const token = await trustedTokenProvider(); // Hàm ứng dụng cung cấp.
  client.connectHeaders = {
    Authorization: "Bearer " + token
  };
};
```

`trustedTokenProvider` ở đây là **giao diện ứng dụng phải cung cấp**, không phải hàm có sẵn hoặc ví dụ tự chạy độc lập. Nó phải quản lý bí mật an toàn, không log token. Nếu Spring Security đang bật CSRF kiểm tra CONNECT, phải bổ sung CSRF token đúng quy trình xác thực; chỉ đặt Bearer không bảo đảm CONNECT thành công.

Không đưa access token dài hạn vào `brokerURL` query string nếu có cách an toàn hơn: URL có thể bị ghi log ở proxy hoặc hệ thống giám sát. Không lấy token từ input người dùng rồi mặc định tin nội dung chưa xác minh.

### 6.4 Khi nào cần ngừng tự động thử lại?

Các lỗi tạm thời như mất mạng hoặc server bảo trì có thể retry với exponential backoff và jitter. Các lỗi khó có thể phục hồi tự động như thông tin đăng nhập sai, người dùng bị khóa, phiên đã logout hoặc destination không được phép cần biểu diễn lỗi trên UI và dừng retry đến khi trạng thái thay đổi.

Giới hạn thử lại phù hợp UX: ví dụ sau nhiều lần thất bại hiển thị “Mất kết nối, thử lại” và vẫn có hành vi backoff nền khi được phép. Không giả định người dùng luôn online hoặc tab luôn ở foreground; trình duyệt có thể hạn chế timer trong tab nền, vì vậy đo thời gian thực cần chấp nhận sai số.

## 7. Đồng bộ dữ liệu sau reconnect: bảo đảm nào thuộc STOMP?

### 7.1 Heartbeat, receipt, ACK và độ bền message là các khái niệm khác

| Cơ chế | Trả lời câu hỏi | Không bảo đảm |
| --- | --- | --- |
| Heartbeat | Hai phía còn có hoạt động truyền dữ liệu không? | Message đã xử lý thành công hoặc lưu bền |
| STOMP RECEIPT | Broker/đầu nhận đã xử lý frame theo ngữ nghĩa receipt được hỗ trợ chưa? | Nghiệp vụ đã commit database hoặc người dùng đã đọc |
| ACK/NACK | Subscriber có xác nhận xử lý message theo chế độ ack tương ứng không? | “Đúng một lần” cho tác dụng phụ bên ngoài nếu thiếu idempotency |
| Correlation ID | Log/sự kiện thuộc yêu cầu nào? | Tin được bảo mật, đã gửi thành công hay được phân quyền |
| Sequence/cursor | Có sự kiện nào bị bỏ lỡ/trùng thứ tự không? | Tự động đồng bộ lại nếu server không lưu lịch sử |
| Idempotency key | Yêu cầu lặp có thể được xử lý an toàn theo chính sách server không? | Tính nhất quán nếu key bị dùng sai/không được lưu đúng cách |

Với simple broker trong bộ nhớ, client đang mất kết nối thường **không nhận lại** các broadcast trong khoảng offline chỉ vì reconnect. Nếu ứng dụng cần không bỏ sót, phải thiết kế bộ lưu event/history hoặc một message broker hỗ trợ bền vững phù hợp và cơ chế replay.

### 7.2 Mẫu đồng bộ lại có sequence ID

Giả sử server gắn `eventId` tăng dần trong phạm vi từng stream. Client giữ `lastSeenEventId` và sau reconnect:

1. Thiết lập socket và hoàn thành STOMP CONNECT.
2. Đăng ký lại những destination cần thiết.
3. Gọi HTTP API đồng bộ hoặc request replay từ `lastSeenEventId` bằng cơ chế server hỗ trợ.
4. Hợp nhất snapshot/replay với những event nhận trong lúc đồng bộ, loại bỏ trùng theo `eventId` và sắp thứ tự theo contract.
5. Chỉ cập nhật mốc `lastSeenEventId` khi event đã được xử lý/lưu theo tiêu chí client đặt ra.

Cần xử lý **khoảng đua** giữa lúc đăng ký và snapshot; có thể subscribe trước rồi queue sự kiện tạm thời trong khi nạp snapshot theo cursor, hoặc dùng protocol đặc thù của server để lấy snapshot + stream với ranh giới xác định. Không chỉ “refetch một lần” rồi giả định không có message mới trong quá trình đồng bộ.

Với chat gửi tin, dùng `clientMessageId` độc nhất và server-side deduplication để khi client không biết `SEND` trước đó thành công hay chưa, có thể retry mà không tạo hai tin trùng. Nếu message nhạy cảm, xác minh quyền đọc lại trong API replay, không chỉ dựa vào subscription đã qua kiểm tra.

### 7.3 Thận trọng với tính “exactly once”

STOMP chỉ là protocol truyền frame; không tự mang lại exactly-once end-to-end qua nhiều dịch vụ/database/UI. Ngay cả khi broker hỗ trợ ACK và lưu bền, ứng dụng có thể nhận lại sau lỗi giữa xử lý và ACK. Mục tiêu thực tế là **at-least-once + idempotency/deduplication** hoặc cơ chế nghiệp vụ tương đương, tùy yêu cầu.

## 8. Quan sát kết nối ở server: session event và broker availability

Spring phát những sự kiện giúp ứng dụng theo dõi kết nối:

| Event | Khi nào xảy ra? |
| --- | --- |
| `SessionConnectEvent` | Server nhận STOMP CONNECT |
| `SessionConnectedEvent` | Server đã gửi CONNECTED; phiên STOMP được xem là kết nối hoàn tất |
| `SessionSubscribeEvent` | Nhận SUBSCRIBE |
| `SessionUnsubscribeEvent` | Nhận UNSUBSCRIBE |
| `SessionDisconnectEvent` | STOMP session kết thúc; có thể từ DISCONNECT hoặc WebSocket close |
| `BrokerAvailabilityEvent` | Trạng thái sẵn sàng của broker relay thay đổi, thường liên quan system connection |

Một sự kiện `SessionDisconnectEvent` có thể được phát **nhiều hơn một lần cho cùng phiên**, nên mã dọn dẹp phải idempotent.

Ví dụ nhận sự kiện đóng kết nối và ghi log metadata:

**Tệp `StompSessionEvents.java`:**

```java
package com.example.chat;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
public class StompSessionEvents {

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        SimpMessageHeaderAccessor headers =
                SimpMessageHeaderAccessor.wrap(event.getMessage());
        System.out.println("STOMP connected session="
                + headers.getSessionId());
    }

    @EventListener
    public void onDisconnected(SessionDisconnectEvent event) {
        System.out.println("STOMP disconnected session="
                + event.getSessionId());
    }
}
```

Đây là thành phần Spring dùng để minh họa sự kiện; trong sản phẩm thật thay `System.out` bằng logger có giới hạn và dùng operation idempotent khi dọn trạng thái. Một message CONNECTED có thể kèm hoặc không kèm metadata khác; đừng phụ thuộc vào việc đọc cookie/token từ event và không ghi credentials vào log.

Nếu lưu trạng thái presence (“online/offline”), một user có thể có **nhiều session** (nhiều tab/thiết bị). Disconnect của một session không đồng nghĩa toàn bộ user offline. Với hệ thống đa node, cần bộ lưu presence phân tán và TTL/heartbeat ở phạm vi ứng dụng nếu muốn trạng thái toàn hệ thống chính xác.

## 9. Kiểm thử xác thực, phân quyền, heartbeat và reconnect

### 9.1 Ma trận kiểm thử bảo mật

Nên tách kiểm thử theo lớp để thấy lỗi bắt nguồn ở đâu:

| Trường hợp | Kỳ vọng |
| --- | --- |
| HTTP handshake không có user trong chế độ cookie auth | Bị chặn ở HTTP security/handshake |
| Browser Origin ngoài allowlist | Không thể hoàn thành handshake theo policy |
| User hợp lệ, STOMP CONNECT thiếu CSRF khi security yêu cầu | CONNECT bị từ chối; HTTP 101 không đồng nghĩa STOMP session thành công |
| STOMP token sai/đã hết hạn | Authentication interceptor từ chối CONNECT |
| ROLE_USER SEND `/app/echo` | Được chuyển đến controller nếu các điều kiện khác hợp lệ |
| ROLE_USER SEND trực tiếp `/topic/admin/alerts` | Bị chặn, không thể giả danh server phát broadcast |
| ROLE_USER SUBSCRIBE `/topic/admin/**` | Bị chặn |
| ROLE_ADMIN SUBSCRIBE `/topic/admin/**` | Được cho phép nếu đã xác thực và phù hợp role |
| ROLE_USER SUBSCRIBE `/topic/rooms/secret` mà không là thành viên | Bị chặn bởi kiểm tra quyền theo room/user (không chỉ role) |
| User logout rồi reconnect bằng token cũ | Không được quay lại với quyền đã thu hồi |
| Frame CONNECT gửi một user ID tự đặt | Không được ghi đè Principal được xác thực |

Test HTTP handshake và STOMP CONNECT là hai bước riêng: test HTTP có thể nhận status 101 nhưng STOMP CONNECT vẫn gặp ERROR. Một integration test thường dùng một STOMP client thật với server embedded và tài khoản thử nghiệm; không “mock mọi thứ” khi muốn kiểm chứng đường đi giữa HTTP security, channel interceptor và broker.

### 9.2 Test heartbeat khi ít traffic

Dùng hai phía đều hỗ trợ heartbeat, cấu hình khoảng nhỏ **chỉ trong môi trường test** rồi theo dõi:

- CONNECT/CONNECTED thương lượng interval đúng hướng.
- Khi không có frame ứng dụng, heartbeat vẫn được gửi theo interval.
- Khi server/broker ngừng phát dữ liệu, phía client phát hiện sau **ngưỡng dung sai**, không ngay chính xác mili giây đầu tiên.
- Sau phát hiện, ứng dụng đánh dấu disconnected, dừng gửi tác vụ tạm thời và kích hoạt quy trình reconnect.
- Khi reconnect, listener/handler/subscription không được nhân đôi.

Tránh kiểm thử heartbeat chỉ bằng `Thread.sleep(10000)` rồi khẳng định “sau đúng 10 giây sẽ đóng”; scheduler, mạng, hệ điều hành và browser throttling gây sai lệch. Dùng thời hạn tối đa có độ dung sai hợp lý và thu thập signal/connection state.

### 9.3 Test reconnect khi đang có message

Thiết lập một client đã subscribe, gửi vài event có `eventId`, tạm ngắt kết nối trước event tiếp theo, cho client nối lại, rồi phát lại dữ liệu qua API snapshot/replay của ứng dụng. Kiểm tra:

- Client không tồn tại subscription cũ trên session mới nhưng đã **subscribe lại**.
- Event trong khoảng offline được khôi phục bởi cơ chế replay của ứng dụng (nếu có).
- Event nhận trùng được loại bỏ; không có tác dụng phụ hai lần.
- Phân quyền được kiểm tra lại; user bị rút quyền trong lúc offline không thể subscribe hoặc replay dữ liệu cũ.
- Nếu server liên tục từ chối auth, reconnect dừng hoặc yêu cầu đăng nhập theo chính sách.

Với broker relay, test mất broker riêng với test mất WebSocket browser, vì relay system connection và client session có vòng đời khác.

### 9.4 Kiểm thử unit Java cho bộ quyết định retry

Ví dụ một chiến lược tính delay đơn giản, **không thay thế** thư viện @stomp/stompjs nhưng giúp kiểm tra quy tắc backoff:

**Tệp `ReconnectBackoffDemo.java` (Java 17+, không phụ thuộc Spring):**

```java
public class ReconnectBackoffDemo {

    static long retryDelayMillis(int failureCount) {
        long delay = 1000;
        for (int attempt = 1; attempt < failureCount; attempt++) {
            delay = Math.min(delay * 2, 16_000);
        }
        return delay;
    }

    public static void main(String[] args) {
        System.out.println("attempt 1: "
                + retryDelayMillis(1) + " ms");
        System.out.println("attempt 2: "
                + retryDelayMillis(2) + " ms");
        System.out.println("attempt 3: "
                + retryDelayMillis(3) + " ms");
        System.out.println("attempt 6: "
                + retryDelayMillis(6) + " ms");
    }
}
```

Chạy:

```bash
javac ReconnectBackoffDemo.java
java ReconnectBackoffDemo
```

**Stdout chính xác:**

```text
attempt 1: 1000 ms
attempt 2: 2000 ms
attempt 3: 4000 ms
attempt 6: 16000 ms
```

Bản demo bỏ qua jitter, giới hạn số lần thử và độ trễ do browser; những yếu tố đó cần có trong chiến lược reconnect thực khi rất nhiều client cùng bị ngắt, để tránh tạo “thundering herd” lên server.

## 10. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Điều có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| HTTP handshake thành công thì cho mọi frame | User hợp lệ truy cập/tự gửi message trái quyền | Message authorization theo frame/destination, deny-by-default |
| Coi STOMP `login`/`passcode` là xác thực trong Spring | Client có thể giả tên bất kỳ | Dùng HTTP Principal hoặc xác thực CONNECT token thật |
| Chỉ kiểm tra Role mà không kiểm tra room/tenant | User đọc room khác cùng ROLE_USER | Kiểm tra quyền theo đối tượng tại server |
| Cho phép SEND trực tiếp tới `/topic/**` | Client giả danh server broadcast | Deny MESSAGE đến broker destination, chỉ mở `/app/**` cần thiết |
| Cho phép SUBSCRIBE `/topic/private/**` không giới hạn | Lộ dữ liệu nội bộ | Giới hạn destination và kiểm tra membership |
| Dùng wildcard Origin với cookie/session | Mất lớp bảo vệ nguồn trang trình duyệt | Allowlist Origin chặt, xác thực/CSRF tương ứng |
| Tắt CSRF toàn site cho SockJS | Mở lỗ hổng CSRF ở các route khác | Ngoại lệ HTTP rất hẹp và bảo vệ CONNECT |
| Bật heartbeat trên client nhưng không cấu hình server | Client hiểu sai server chết hoặc không detect đúng | Bật heartbeat theo broker, scheduler và thương lượng STOMP |
| Cho rằng heartbeat xác nhận message đã lưu | Thất lạc dữ liệu khi reconnect | Thiết kế ACK/receipt/snapshot/replay phù hợp |
| Broker relay tự reconnect nên browser cũng sẽ reconnect | UI mắc kẹt offline | Thiết lập reconnect trong từng STOMP client |
| Chỉ tạo `subscribe` lần đầu | Sau reconnect không nhận message | Subscribe lại sau mỗi CONNECTED |
| Reconnect liên tục không backoff | Server quá tải khi mất mạng diện rộng | Backoff + jitter + giới hạn, phân biệt lỗi auth |
| Tự động replay mọi SEND sau đứt kết nối | Gây thao tác lặp, trùng tiền/đơn | Idempotency key, tra cứu trạng thái kết quả |
| Xem mỗi user chỉ có một socket | Disconnect một tab làm user bị đánh offline | Theo dõi nhiều session trên mỗi user |
| Dọn phiên theo mỗi `SessionDisconnectEvent` không idempotent | Chạy cleanup lặp, dữ liệu sai | Cleanup an toàn khi nhận nhiều event |
| Dựa vào SimpleBroker để lưu message offline | Mất thông báo giữa lúc không online | Dùng lịch sử/replay hoặc broker có durability phù hợp |
| Ghi token/raw STOMP frame vào log | Rò thông tin xác thực và dữ liệu riêng | Ghi metadata đã lọc, tuyệt đối không log secret |

## 11. Checklist triển khai

Trước khi đưa tính năng WebSocket/STOMP vào môi trường thực:

1. **Xác thực:** xác định HTTP session hay CONNECT token làm nguồn danh tính; kiểm thử danh tính sau reconnect và khi token hết hạn.
2. **Origin/CSRF:** allowlist Origin, hiểu cookie/SameSite/proxy và chính sách CSRF của STOMP CONNECT/SockJS.
3. **Destination:** liệt kê SEND và SUBSCRIBE được phép, từ chối destination không khai báo, kiểm tra quyền tài nguyên riêng.
4. **Heartbeat:** bật scheduler cho simple broker hoặc cấu hình broker relay, thương lượng khoảng thực tế với client, áp dụng dung sai timeout.
5. **Reconnection:** dùng một client instance đúng vòng đời, exponential backoff (có jitter khi cần), resubscribe trong `onConnect` và ngừng retry khi user logout.
6. **Đồng bộ:** lưu cursor/sequence và cung cấp API replay/snapshot nếu không được mất dữ liệu; deduplicate event và dùng idempotency key cho thao tác có tác dụng phụ.
7. **Quan sát:** theo dõi session, connected/disconnected, broker availability, auth failure, retry count, heartbeat-lost, và lý do không nhận message; bảo vệ thông tin cá nhân trong log.
8. **Kiểm thử:** kết hợp test unit matcher/chính sách với integration test HTTP handshake + CONNECT + SUBSCRIBE/SEND + ngắt mạng thật.

Một câu hỏi chẩn đoán hữu ích khi user báo “WebSocket đang connected nhưng không nhận thông báo”: **HTTP socket đã mở hay STOMP CONNECTED rồi? User có đúng Principal? SUBSCRIBE có được phép, đến đúng destination và trên phiên hiện tại? Broker có sẵn sàng? Có event mới hay cần replay sự kiện đã bỏ lỡ?** Trả lời theo từng tầng giúp xác định lỗi chính xác.

## 12. Tài liệu tham khảo

- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): HTTP Principal và `login/passcode` của STOMP.
- [Spring Framework — STOMP Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): xác thực token trong CONNECT bằng `ChannelInterceptor`, thứ tự trước authorization.
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): `@EnableWebSocketSecurity`, destination matchers, CSRF/same-origin.
- [Spring Framework — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html): kiểm tra quyền ở client inbound channel.
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html): `TaskScheduler` và heartbeat của broker đơn giản.
- [Spring Framework — Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html): heartbeat và system connection của external broker.
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): `WebSocketStompClient`, heartbeat và receipts.
- [Spring Framework — STOMP Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html): sự kiện connect/disconnect, reconnect trách nhiệm client.
- [@stomp/stompjs — Client API](https://stomp-js.github.io/api-docs/latest/classes/Client.html): reconnect/backoff, heartbeat và vòng đời client.
