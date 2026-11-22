# @EnableWebSocketSecurity và AuthorizationManager<Message<?>>

> **Spring Security – authorization · Phân quyền thông điệp.** Bài Knowledge hướng dẫn bảo vệ **STOMP over WebSocket của Spring Messaging** bằng `@EnableWebSocketSecurity` và một bean `AuthorizationManager<Message<?>>`. Chủ đề tập trung vào **clientInboundChannel**: phân biệt frame `CONNECT`/`SUBSCRIBE`/`SEND`, đường đích `/app`, `/topic`, `/queue`, `/user`, xác thực từ HTTP handshake, CSRF ở STOMP CONNECT, matcher theo message type, rule ordering, deny-by-default và kiểm thử chính sách. Ví dụ Spring sử dụng **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x**, Servlet + Spring WebSocket Message Broker. Phần Java 17 thuần ở cuối là mô phỏng policy độc lập, **không phải** WebSocket server.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao WebSocket **đã nâng cấp HTTP** vẫn cần một lớp phân quyền riêng cho **mỗi STOMP frame** đến từ client.
2. Biết `@EnableWebSocketSecurity` tích hợp Spring Security Messaging và nhận bean `AuthorizationManager<Message<?>>` từ Spring Context.
3. Dùng `MessageMatcherDelegatingAuthorizationManager.Builder`, `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `simpTypeMatchers`, `nullDestMatcher` và `anyMessage` chính xác.
4. Phân biệt **STOMP MESSAGE** (message được server/broker gửi đi) với giá trị `SimpMessageType.MESSAGE` của Spring cho client **SEND** đi vào.
5. Chặn client tự `SEND` đến `/topic/**` hoặc `/queue/**` nhằm giả mạo thông báo của server.
6. Hạn chế `SUBSCRIBE` đến các topic/queue được cho phép, đặc biệt không mở wildcard `/queue/**` có thể lộ bản tin của người dùng khác.
7. Lấy identity từ `Principal` đã authenticated trong HTTP handshake/việc xác thực STOMP có kiểm soát; không tin `from`, `user` hoặc role do client ghi trong payload/header.
8. Bảo vệ STOMP `CONNECT` bằng CSRF token và Origin/Same-Origin policy, không coi WebSocket tự có trình duyệt Same Origin giống HTTP AJAX.
9. Viết Spring Boot/STOMP demo có một policy cho messages inbound, controller gửi thông báo hợp lệ và error queue riêng.
10. Unit test `AuthorizationManager<Message<?>>` bằng `MessageBuilder` + `SimpMessageHeaderAccessor`, phân biệt authentication thật/anonymous, role USER/ADMIN, MESSAGE/SUBSCRIBE và route không được khai báo.
11. Nhận diện tình huống phải thêm object-level/tenant-level policy vào custom `AuthorizationManager<MessageAuthorizationContext<?>>` thay vì chỉ kiểm role chung.
12. Xác định giới hạn inbound security: outgoing messages không được kiểm tự động; nếu client subscribe sai scope, nội dung nhạy cảm đã có thể bị lộ.
13. Lập ma trận integration tests cho handshake, CSRF, broker routing, session identity, revoke và resource/tenant boundaries.
14. Chạy một ví dụ Java 17 độc lập có stdout chính xác để tự đánh giá policy deny-by-default.

## 2. Kiến trúc STOMP trên Spring WebSocket

Một kết nối WebSocket chỉ là kênh truyền hai chiều. STOMP tạo một giao thức message-based chạy bên trong kênh đó: một client có thể gửi frame `CONNECT`, `SUBSCRIBE`, `SEND` và `DISCONNECT`; server/broker có thể phát `MESSAGE` và các frame quản lý phiên.

~~~text
Browser / STOMP client
   |
   | HTTP GET /ws, Upgrade: websocket
   | HTTP authentication + Origin policy
   v
WebSocket session, bound Principal
   |
   | STOMP CONNECT [CSRF in native STOMP header]
   | STOMP SUBSCRIBE /topic/announcements
   | STOMP SEND /app/chat.send
   v
Spring clientInboundChannel
   |
   +-- SecurityContextChannelInterceptor
   +-- AuthorizationChannelInterceptor
   |      AuthorizationManager<Message<?>>
   |       - type?
   |       - destination?
   |       - authenticated Principal/authorities?
   |       - allowed to SEND/SUBSCRIBE?
   |
   +-- on MESSAGE /app/* --> @MessageMapping controller
   |                             |
   |                             v
   |                        application service
   |                             |
   |                        SimpMessagingTemplate
   |                             |
   +--------------------------> broker
                                 |
                                 v
                         clientOutboundChannel
                                 |
                                 v
                       subscribed client sessions
~~~

**Điểm mấu chốt:** Spring Security WebSocket authorization của cấu hình này kiểm **clientInboundChannel**, không tự kiểm mọi frame ở `clientOutboundChannel`. Vì vậy phải bảo vệ việc **SUBSCRIBE** đúng destination trước khi một client có thể nhận dữ liệu; đừng đợi đến lúc server đã broadcast rồi mới lọc nhạy cảm. Nếu message được phát qua một broker relay ngoài, còn phải xét security của broker, relay identity và routing.

### 2.1. Destination có nhiều lớp nghĩa

| Chuỗi | Thường dùng cho | Được ai gửi/nhận? |
| --- | --- | --- |
| `/ws` | URL HTTP WebSocket handshake | Browser/client kết nối, không phải STOMP destination |
| `/app/chat.send` | Client gửi dữ liệu tới application handler | Inbound `SEND`, Spring bỏ prefix `/app` để tìm `@MessageMapping("/chat.send")` |
| `/topic/announcements` | Broker broadcast notification | Client `SUBSCRIBE`, application/server `convertAndSend` |
| `/topic/admin` | Broker stream chỉ cho admin | Client ADMIN mới được subscribe; client không được tự SEND trực tiếp |
| `/queue/**` | Broker destinations mang tính queue | Không nên cho client wildcard subscribe |
| `/user/queue/errors` | Client subscribe vào user destination cá nhân | Spring resolve thành queue dành cho session/user |
| `/user/{username}/queue/x` | App gửi đến user cụ thể (server-side) | Qua `convertAndSendToUser`, không phải quyền client tự chọn user khác |

**Chú ý:** `/topic` và `/queue` là quy ước khi dùng simple broker, không tự làm mọi message được bảo mật. Một destination string không chứng minh principal có quyền truy cập. Đối với multi-tenant, `/topic/tenant/alpha` cần membership-check alpha, không chỉ matcher `/topic/**. 

### 2.2. MESSAGE và SUBSCRIBE là hai quyền riêng

Spring `SimpMessageType.MESSAGE` thường mô tả inbound message có payload, tương ứng client STOMP `SEND`; `SimpMessageType.SUBSCRIBE` mô tả client đăng ký nhận. Cùng destination có thể bị đánh giá khác nhau tùy type.

Ví dụ một client USER:
- `SUBSCRIBE /topic/announcements`: cho nhận thông báo.
- `SEND /topic/announcements`: **deny** để client không giả mạo thông báo máy chủ.
- `SEND /app/chat.send`: cho gọi controller xử lý.
- `SUBSCRIBE /app/chat.send`: **deny** vì đây không phải kênh phát.
- `SUBSCRIBE /queue/user/private`: **deny**, dù string trông giống user queue.

Không viết matcher `simpDestMatchers("/topic/**").authenticated()` nếu mục tiêu chỉ là cho SUBSCRIBE: matcher đó **không giới hạn theo loại MESSAGE/SUBSCRIBE** và có thể cho phép SEND đến broker prefix.

## 3. @EnableWebSocketSecurity và AuthorizationManager<Message<?>>

Từ Spring Security 5.8, cách cấu hình mới dựa trên `AuthorizationManager`; với Spring Security 6.5 dùng annotation:

~~~java
@Configuration
@EnableWebSocketSecurity
class SocketMessageSecurity {
    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
                .simpSubscribeDestMatchers("/topic/announcements")
                    .hasRole("USER")
                .simpMessageDestMatchers("/app/chat.send")
                    .hasRole("USER")
                .simpTypeMatchers(
                    SimpMessageType.MESSAGE,
                    SimpMessageType.SUBSCRIBE)
                    .denyAll()
                .nullDestMatcher().authenticated()
                .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Đây là trích đoạn thuộc class configuration; imports và full application ở mục 6. Bean `AuthorizationManager<Message<?>>` được Spring Security dùng để kiểm các message ở inbound channel. Generic `Message<?>` là Spring Messaging `org.springframework.messaging.Message<?>`, không phải `javax.websocket.Message` và cũng không phải `HttpServletRequest`.

### 3.1. Builder và thứ tự matcher

`MessageMatcherDelegatingAuthorizationManager.Builder` duyệt các rule theo thứ tự khai báo; một message được xử lý bởi rule phù hợp đầu tiên. Vì vậy đi từ **ngoại lệ cụ thể → rule chung → deny**.

| Matcher | Dựa trên điều gì | Lưu ý |
| --- | --- | --- |
| `simpMessageDestMatchers("/app/chat.send")` | Type MESSAGE + destination | Dành riêng cho inbound SEND |
| `simpSubscribeDestMatchers("/topic/announcements")` | Type SUBSCRIBE + destination | Dành riêng cho việc đăng ký nghe |
| `simpDestMatchers("/app/**")` | Destination, **bất kể type** | Dễ quá rộng nếu không kiểm type |
| `simpTypeMatchers(MESSAGE,SUBSCRIBE)` | Message type | Deny các frame dữ liệu chưa match |
| `nullDestMatcher()` | Destination null | CONNECT/UNSUBSCRIBE/DISCONNECT thường không có dest; không đồng nghĩa chỉ CONNECT |
| `anyMessage()` | Mọi message còn lại | Luôn `denyAll()` ở policy chặt |
| `matchers(customMatcher)` | Tự định nghĩa | Dùng khi cần rule phi chuẩn, phải test độ ưu tiên |

**Tại sao đặt `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` trước `nullDestMatcher().authenticated()`?** Vì `nullDestMatcher` chỉ xét destination null, nên một message malformed kiểu MESSAGE nhưng thiếu destination có thể match nếu không bị chặn trước. Rule chặt xử lý mọi SEND/SUBSCRIBE không hợp lệ trước khi cấp quyền cho các frame điều khiển không có destination. Một số ví dụ trong tài liệu để `nullDestMatcher` lên trước; khi xây chính sách phòng thủ cho ứng dụng thực, việc test malformed frame giúp quyết định thứ tự an toàn hơn.

### 3.2. AuthorizationManager nhận Authentication ra sao?

Interface chung `AuthorizationManager<T>` cho phép đánh giá một secured object dựa trên `Supplier<Authentication>`:

~~~java
// Spring Security 6.5 conceptual signature:
AuthorizationDecision check(
        Supplier<Authentication> authentication,
        Message<?> message);
~~~

Trong Spring Security 6.5, `check` có thể được đánh dấu deprecated để khuyến khích dùng `authorize` trả `AuthorizationResult`, nhưng vẫn có sẵn trong nhánh 6.5 và được dùng để minh họa/unit test. Khi nâng cấp 7.x, kiểm chữ ký API thực tế và đổi method test tương ứng. Không gán nhầm `AuthorizationManager<MethodInvocation>` (method security) hoặc `ReactiveAuthorizationManager<AuthorizationContext>` (WebFlux HTTP) cho inbound STOMP messaging.

### 3.3. GRANT/DENY/ABSTAIN

- `AuthorizationDecision(true)`: rule cho phép message.
- `AuthorizationDecision(false)`: rule từ chối.
- `null` từ manager: có thể là **không có quyết định** (abstain). Không coi null là true.
- Exception từ custom manager: lỗi kiểm quyền/nguồn dữ liệu, không phải đường đi để permit.
- Với deny-by-default, cả miss và error phải **không cho protected event chạy**; đặt `anyMessage().denyAll()` tránh unmatched message bị lọt.

Một custom `AuthorizationManager` có thể có side effect không mong muốn nếu truy vấn DB trong `check`. Cần nguồn dữ liệu tin cậy, bounds/timeouts, caching theo actor/tenant/topic và audit; không dùng boolean do client đính trong native headers làm kết quả.

## 4. STOMP authentication bắt đầu trước authorization

### 4.1. HTTP handshake cung cấp Principal

Theo luồng mặc định Spring WebSocket/Spring Security, Principal của HTTP request đã authenticated khi WebSocket handshake có thể được gắn với WebSocket session và các STOMP messages tiếp theo. Để bảo vệ `/ws`:
- HTTP SecurityFilterChain yêu cầu authentication.
- Same-origin/cookie/session và HTTPS/WSS phải có cấu hình.
- Nếu dùng Spring Security HTTP Session, authentication từ session được tái sử dụng sau nâng cấp.
- Với client ngoài browser dùng HTTP Basic trong demo, Basic phải được gửi ở **HTTP handshake**, không phải tùy tiện coi STOMP `login/passcode` là credential được Spring Security xác minh.

**Không tin client tự gửi:**

~~~text
CONNECT
login:admin
passcode:topsecret
x-user:alice
x-roles:ROLE_ADMIN
~~~

Spring không tự coi các native STOMP headers này là Authentication đã xác minh của Spring Security. Nếu kiến trúc cần authenticate bearer token trong STOMP CONNECT (thường gặp với SPA), phải xây một `ChannelInterceptor` xác minh token trước authorization, gắn Principal qua `StompHeaderAccessor#setUser(...)` theo framework contract, kiểm thứ tự interceptor, issuer/audience/expiry và chính sách token rotation. Không chỉ parse JWT payload bằng Base64 rồi set `ROLE_ADMIN`.

### 4.2. Role prefix của Spring vẫn áp dụng

`hasRole("USER")` mặc định nhắm authority `ROLE_USER`; `hasRole("ADMIN")` nhắm `ROLE_ADMIN`. Nếu Spring Resource Server JWT cấp `SCOPE_chat.write` chứ không cấp `ROLE_USER` thì `hasRole("USER")` sẽ deny. Có thể viết `hasAuthority("SCOPE_chat.write")` hoặc converter được review; không map mọi OAuth scope thành role admin vì tiện.

### 4.3. WebSocket kết nối lâu dài và quyền thay đổi

Một session được authenticated lúc handshake không tự cập nhật Principal/authorities ngay khi admin gỡ role trong DB. Đối với phòng chat bảo mật, cần chính sách reauthorization theo message, kiểm membership/ACL ở service hoặc disconnect khi revoke, có TTL/lifecycle và metrics. Không cho rằng một HTTP login ban đầu bảo vệ mọi subscription vô thời hạn nếu permissions động.

## 5. CONNECT CSRF, Origin và TLS: không được bỏ qua

WebSocket browser API không áp dụng Same-Origin Policy theo cách fetch/XHR tự chặn cross-origin data như nhiều người lầm tưởng. Cookie có thể đi trong handshake nếu chính sách browser cho phép; nếu server cho phép origin lạ, trang độc hại có thể dùng phiên người dùng để mở WebSocket và subscribe.

Spring Security mặc định yêu cầu **CSRF token trong STOMP CONNECT** khi bật `@EnableWebSocketSecurity`, đồng thời Spring WebSocket/SockJS có cơ chế allowed origins. Đây là lớp phòng vệ chiều sâu, không thay thế HTTP session authentication.

### 5.1. CSRF token phải đi trong native STOMP headers

Ví dụ controller lấy token ở HTTP context:

~~~java
@RestController
class CsrfEndpoint {
    @GetMapping("/csrf")
    CsrfToken csrf(CsrfToken token) {
        return token;
    }
}
~~~

Browser cùng origin và cùng authenticated session gọi `GET /csrf`, nhận `headerName` và `token` (dạng JSON). Sau đó gắn vào **STOMP CONNECT native headers**:

~~~javascript
// Pseudocode dùng STOMP client thư viện đã cài và same-origin session.
// csrf là response từ endpoint cùng origin (giữ cookie/session).
const connectHeaders = {
  [csrf.headerName]: csrf.token
};
stompClient.connect(connectHeaders, onConnected, onError);
~~~

**Không** chỉ gửi CSRF token ở HTTP Upgrade header rồi cho rằng nó sẽ tự được copy sang STOMP CONNECT. Với SockJS XHR fallback, nhiều transport bị hạn chế custom HTTP headers; native STOMP header là cách phù hợp. Khi dùng một Java STOMP client, cần giữ cookie/session hoặc handshake credentials cùng identity với token CSRF và CONNECT frame.

### 5.2. Có nên disable CSRF STOMP CONNECT?

Trong Spring Security 6.5, tài liệu nêu `@EnableWebSocketSecurity` chưa cung cấp tùy chọn cấu hình trực tiếp để disable yêu cầu CSRF CONNECT; tài liệu có hướng dẫn thay thế bằng wiring riêng/XML nếu tổ chức chấp nhận mô hình bảo vệ khác. **Không** tự tắt CSRF HTTP toàn ứng dụng để STOMP chạy được. Nếu cần cross-origin hợp lệ, thiết kế token-based authentication, allowed origin, CSRF strategy và threat model có review; duy trì kiểm phiên/recipient.

### 5.3. Cấu hình origins và scheme

Giữ mặc định same-origin trong demo. Khi triển khai:
- Dùng `wss://` trên production; tránh gửi token/cookie qua `ws://` trên mạng công cộng.
- Giới hạn trusted origins, không mặc định `setAllowedOriginPatterns("*")` với cookie-based auth.
- CORS HTTP và WebSocket handshake Origin là hai lớp cần kiểm riêng; non-browser client có thể gửi Origin giả, nên Origin không thay authentication.
- Nếu dùng SockJS, cân nhắc frame-options, HTTP fallback, CSRF trên transport và path-matchers chính xác.
- Giới hạn số connection, subscriptions/session, message size, rate per user/tenant và heartbeat timeouts để tránh abuse.

## 6. Spring Boot 3.5 demo: end-to-end message authorization

Demo bảo vệ một topic công cộng trong phạm vi user authenticated và một topic admin. Vai trò:
- `alice`: `ROLE_USER`. Có thể SEND `/app/chat.send` và SUBSCRIBE `/topic/announcements`.
- `admin`: `ROLE_USER` + `ROLE_ADMIN`. Ngoài quyền Alice, có thể SEND `/app/admin.broadcast` và SUBSCRIBE `/topic/admin`.
- `viewer`: `ROLE_VIEWER`. HTTP handshake có thể authenticated nhưng bị từ chối mọi SEND/SUBSCRIBE dữ liệu trong demo.

Các message đi tới `/app/**` được xử lý bởi application controller. Chỉ server sử dụng `SimpMessagingTemplate` phát dữ liệu ra `/topic/**`; client gửi trực tiếp tới broker prefix bị DENY.

### 6.1. Cấu trúc tệp

~~~text
src/main/java/demo/socket/SocketSecurityApplication.java
src/test/java/demo/socket/MessageAuthorizationRulesTest.java
~~~

Tạo Spring Boot **3.5.x** project Java 17+ và sử dụng dependencies ở phần 6.3. Một Java file chứa public class và các class package-private để dễ thực hành; production nên tách configuration, controller, payload DTO, authorization policies và domain service.

### 6.2. File SocketSecurityApplication.java

~~~java
package demo.socket;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendToUser;
import org.springframework.messaging.simp.SimpMessageSendingOperations;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.messaging.access.intercept
        .MessageMatcherDelegatingAuthorizationManager;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@SpringBootApplication
public class SocketSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(SocketSecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/ws", "/csrf").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .roles("USER")
                    .build(),
                User.withUsername("admin")
                    .password("{noop}demo")
                    .roles("USER", "ADMIN")
                    .build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .roles("VIEWER")
                    .build());
        // {noop} & HTTP Basic chỉ để demo, không dùng production.
    }
}

@Configuration
@EnableWebSocketMessageBroker
class StompBrokerConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        // Giữ mặc định hạn chế Origin, không thêm wildcard.
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}

@Configuration
@EnableWebSocketSecurity
class SocketMessageSecurity {
    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
                // User error queue: phải có Authentication.
                .simpSubscribeDestMatchers("/user/queue/errors")
                    .authenticated()

                // Client chỉ nghe đúng các broker streams được cấp.
                .simpSubscribeDestMatchers("/topic/announcements")
                    .hasRole("USER")
                .simpSubscribeDestMatchers("/topic/admin")
                    .hasRole("ADMIN")

                // Client chỉ được SEND đến app handlers đã định danh.
                .simpMessageDestMatchers("/app/chat.send")
                    .hasRole("USER")
                .simpMessageDestMatchers("/app/admin.broadcast")
                    .hasRole("ADMIN")

                // Chặn mọi SEND/SUBSCRIBE chưa match, bao gồm
                // client gửi trực tiếp /topic/** hoặc /queue/**.
                .simpTypeMatchers(
                    SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE)
                    .denyAll()

                // CONNECT, UNSUBSCRIBE, DISCONNECT... thường không có dest.
                .nullDestMatcher().authenticated()

                // Đóng mọi frame khác theo default.
                .anyMessage().denyAll();

        return messages.build();
    }
}

record ChatRequest(String text, String from) {}
record ChatEvent(String author, String text) {}
record AdminRequest(String text) {}
record ErrorFrame(String code) {}

@Controller
class ChatController {
    private final SimpMessageSendingOperations broker;

    ChatController(SimpMessageSendingOperations broker) {
        this.broker = broker;
    }

    @MessageMapping("/chat.send")
    public void send(ChatRequest request, Principal principal) {
        String message = validatedText(
                request == null ? null : request.text());

        if (principal == null) {
            throw new IllegalArgumentException("Authentication required");
        }

        // KHÔNG tin request.from(), luôn lấy principal đã xác thực.
        broker.convertAndSend(
                "/topic/announcements",
                new ChatEvent(principal.getName(), message));
    }

    @MessageMapping("/admin.broadcast")
    public void adminBroadcast(AdminRequest request, Principal principal) {
        String message = validatedText(
                request == null ? null : request.text());

        if (principal == null) {
            throw new IllegalArgumentException("Authentication required");
        }

        // @EnableWebSocketSecurity policy đảm bảo ROLE_ADMIN
        // ở inbound MESSAGE /app/admin.broadcast.
        broker.convertAndSend(
                "/topic/admin",
                new ChatEvent(principal.getName(), message));
    }

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public ErrorFrame invalidPayload(IllegalArgumentException error) {
        // Không phát exception message/stack trace ra cho client.
        return new ErrorFrame("INVALID_PAYLOAD");
    }

    private static String validatedText(String text) {
        if (text == null || text.isBlank() || text.length() > 240) {
            throw new IllegalArgumentException("Invalid message text");
        }
        return text.trim();
    }
}

@RestController
class CsrfEndpoint {
    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken token) {
        // Chỉ authenticated caller mới lấy token theo HTTP rules.
        return token;
    }
}
~~~

**Lưu ý cú pháp import quan trọng:** Dòng import `MessageMatcherDelegatingAuthorizationManager` ở trên được xuống dòng để bài không quá rộng, nhưng **Java import không cho xuống dòng giữa package và tên class khi biên dịch**. Trong file thực, hãy thay hai dòng:

~~~java
import org.springframework.security.messaging.access.intercept
        .MessageMatcherDelegatingAuthorizationManager;
~~~

bằng import **một dòng**:

~~~java
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
~~~

Không giữ cả hai. Ngoài chi tiết định dạng đó, các file/classes phụ thuộc vào Spring Boot 3.5.x/Security 6.5.x và setup Gradle ở dưới. Nếu dùng IDE, nên để IDE tự chuẩn hóa imports; không thêm dependency WebFlux cho bản Servlet/STOMP này.

### 6.3. Dependencies Gradle

Đây là phần `dependencies` của build Gradle đã có Spring Boot plugin, dependency management, repositories và Java 17:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Với Spring Security 6.5, `spring-boot-starter-security` và WebSocket starter trong Spring Boot-managed dependency graph cung cấp module messaging/security cần thiết; nếu class `org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager` không có trong classpath, cần kiểm `spring-security-messaging` ở dependency tree và khai báo module này rõ ràng nếu chưa được kéo vào. Ví dụ:

~~~groovy
implementation 'org.springframework.security:spring-security-messaging'
~~~

Không tự trộn versions Spring Security ngoài BOM. Trong project thật hãy kiểm `./gradlew dependencies --configuration runtimeClasspath` để xác nhận module messaging tồn tại.

### 6.4. Chạy demo

Tại thư mục project:

~~~bash
./gradlew bootRun
~~~

Server có handshake endpoint `ws://localhost:8080/ws`. Với browser dùng same-origin **session/cookie auth** do HTTP layer quản lý; HTTP Basic ở demo chủ yếu dành cho Java tool/client có khả năng gửi credentials trong handshake. **Browser WebSocket API không cung cấp tùy chọn đặt arbitrary Authorization header**; một browser app thực tế nên dùng session login hoặc một token handshake/STOMP strategy đã được thiết kế riêng.

Quy trình test end-to-end:
1. Authenticate HTTP cùng session với `/ws` handshake.
2. Đọc CSRF token từ HTTP `GET /csrf` với session đó.
3. Upgrade WebSocket tại `/ws` theo allowed origin.
4. Gửi STOMP `CONNECT` cùng csrf header value/name đã nhận.
5. Khi `CONNECTED`, gửi `SUBSCRIBE` đến topic hợp lệ và `SEND` đến `/app/chat.send`.
6. Không dùng `login:admin`/`passcode` trong STOMP để giả vờ được cấp quyền; chúng không thay Spring Principal.
7. Kiểm event `ChatEvent("alice", text)` xuất hiện trên `/topic/announcements`, bất kể payload client viết `from:"admin"`.

### 6.5. STOMP frame minh họa (không phải lệnh shell)

~~~text
CONNECT
accept-version:1.2
host:localhost
X-CSRF-TOKEN:<token-from-GET-csrf>

^@
SUBSCRIBE
id:sub-1
destination:/topic/announcements

^@
SEND
destination:/app/chat.send
content-type:application/json

{"text":"Hello","from":"admin"}
^@
~~~

Dấu `^@` biểu diễn kết thúc frame NUL trong STOMP ở dạng dễ nhìn, **không** phải ba ký tự thực `^`, `@`, xuống dòng. Tên CSRF header phải lấy từ `CsrfToken.getHeaderName()` thực tế (có thể khác `X-CSRF-TOKEN`). Demo xử lý payload text/username, server broadcast `author` là username được xác thực, không phải `from` do client tự khai.

### 6.6. Bảng hành vi dự kiến

| Actor | Inbound frame | Destination | Kết quả authorization |
| --- | --- | --- | --- |
| Alice USER | CONNECT (không dest) | null | authenticated rule, nhưng **còn phải có CSRF** |
| Alice USER | SEND/MESSAGE | `/app/chat.send` | GRANT |
| Alice USER | SUBSCRIBE | `/topic/announcements` | GRANT |
| Alice USER | SEND/MESSAGE | `/topic/announcements` | DENY |
| Alice USER | SUBSCRIBE | `/topic/admin` | DENY |
| Admin ADMIN+USER | SEND/MESSAGE | `/app/admin.broadcast` | GRANT |
| Admin ADMIN+USER | SUBSCRIBE | `/topic/admin` | GRANT |
| Admin ADMIN+USER | SEND/MESSAGE | `/topic/admin` | DENY |
| Viewer VIEWER | SEND/MESSAGE | `/app/chat.send` | DENY |
| Alice USER | SUBSCRIBE | `/queue/anything` | DENY |
| Alice USER | SUBSCRIBE | `/user/queue/errors` | GRANT |
| Anonymous | CONNECT | null | DENY bởi authn/authz (kể cả khi trình gửi có token CSRF ngẫu nhiên) |
| Alice USER | SEND/MESSAGE | `/app/unknown` | DENY |
| Alice USER | SUBSCRIBE | `/topic/unknown` | DENY |

Một unit test chỉ kiểm `CONNECT` authorized không chứng minh CSRF đã qua; CSRF là interceptor/handshake check khác, cần integration test.

## 7. Unit test AuthorizationManager<Message<?>> trực tiếp

Mục tiêu: test đúng **manager policy** mà không cần mở WebSocket server. Tạo Spring message với type và destination cụ thể, truyền supplier Authentication thật. Dùng JUnit 5.

Lưu `src/test/java/demo/socket/MessageAuthorizationRulesTest.java`:

~~~java
package demo.socket;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class MessageAuthorizationRulesTest {
    @Autowired AuthorizationManager<Message<?>> rules;

    private static Authentication user(String name, String... roles) {
        return UsernamePasswordAuthenticationToken.authenticated(
                name, "unused",
                java.util.Arrays.stream(roles)
                    .map(r -> new SimpleGrantedAuthority("ROLE_" + r))
                    .toList());
    }

    private static Authentication anonymous() {
        return new AnonymousAuthenticationToken(
                "test-key", "anonymous",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
    }

    private static Message<byte[]> inbound(
            SimpMessageType type, String destination) {
        SimpMessageHeaderAccessor accessor =
                SimpMessageHeaderAccessor.create(type);
        if (destination != null) {
            accessor.setDestination(destination);
        }
        return MessageBuilder.createMessage(
                new byte[0], accessor.getMessageHeaders());
    }

    @SuppressWarnings("deprecation") // Spring Security 6.5 check()
    private boolean allowed(Authentication actor, SimpMessageType type,
                            String destination) {
        AuthorizationDecision decision =
                rules.check(() -> actor, inbound(type, destination));
        return decision != null && decision.isGranted();
    }

    @Test
    void userMaySendToAppButNotBroker() {
        Authentication alice = user("alice", "USER");

        assertTrue(allowed(alice, SimpMessageType.MESSAGE,
                "/app/chat.send"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/topic/announcements"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/queue/private"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/app/unknown"));
    }

    @Test
    void subscribeIsDifferentFromSend() {
        Authentication alice = user("alice", "USER");

        assertTrue(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/announcements"));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/app/chat.send"));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/admin"));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/queue/user/private"));
        assertTrue(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/user/queue/errors"));
    }

    @Test
    void adminPrivilegesDoNotPermitDirectTopicSend() {
        Authentication admin = user("admin", "USER", "ADMIN");

        assertTrue(allowed(admin, SimpMessageType.MESSAGE,
                "/app/admin.broadcast"));
        assertTrue(allowed(admin, SimpMessageType.SUBSCRIBE,
                "/topic/admin"));
        assertFalse(allowed(admin, SimpMessageType.MESSAGE,
                "/topic/admin"));
    }

    @Test
    void viewerCannotSendOrSubscribeToPrivateTopic() {
        Authentication viewer = user("viewer", "VIEWER");

        assertFalse(allowed(viewer, SimpMessageType.MESSAGE,
                "/app/chat.send"));
        assertFalse(allowed(viewer, SimpMessageType.SUBSCRIBE,
                "/topic/announcements"));
    }

    @Test
    void authenticatedControlFrameAllowedButAnonymousDenied() {
        Authentication alice = user("alice", "USER");

        assertTrue(allowed(alice, SimpMessageType.CONNECT, null));
        assertTrue(allowed(alice, SimpMessageType.DISCONNECT, null));
        assertFalse(allowed(anonymous(), SimpMessageType.CONNECT, null));
    }

    @Test
    void malformedOrUnknownMessagesAreDenied() {
        Authentication alice = user("alice", "USER");

        assertFalse(allowed(alice, SimpMessageType.MESSAGE, null));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE, null));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/topic/admin"));
        assertFalse(allowed(alice, SimpMessageType.OTHER,
                "/topic/announcements"));
    }
}
~~~

Những phép thử này chứng minh:
- Builder có **phân biệt type** và destination.
- Admin role không mở quyền client SEND trực tiếp broker topic.
- Rule fallthrough `anyMessage().denyAll()` hoạt động.
- `nullDestMatcher` không vô tình cho malformed MESSAGE/SUBSCRIBE vì đã đặt type deny trước.
- Một AnonymousAuthenticationToken có `isAuthenticated() == true` trong cách biểu diễn của nó, nhưng `authenticated()` dùng trust resolver nên không được xem là user đăng nhập hợp lệ.

**Chưa được chứng minh bằng unit test này:** CSRF token ở CONNECT, WebSocket Origin, HTTP handshake authentication, broker relay, session cookies, actual STOMP message routing và việc server phát message ra subscriber. Các mục đó cần integration tests riêng.

## 8. Kế hoạch integration test với WebSocketStompClient

Một integration test hiệu quả nên dùng server chạy ở random port và STOMP client thật:
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` với `@LocalServerPort`.
- `WebSocketStompClient` + `StandardWebSocketClient` (hoặc transport đã được chọn), cùng session/cookie hoặc HTTP handshake credential với user test.
- `StompHeaders` chứa CSRF header name/value ở `CONNECT` lấy từ HTTP API bằng **cùng session**.
- Handler subscribe tới destination được phép; gửi JSON `{"text":"ok","from":"admin"}` vào `/app/chat.send` và verify server event có `author:"alice"`.
- Repeated test với role VIEWER, ADMIN, wrong topic, missing CSRF, wrong Origin, malformed token và revoked membership.

Pseudo-code cho phần gửi/nhận:

~~~java
// Trích đoạn trong integration test; không phải file độc lập.
// Trước đó HTTP handshake đã được authenticated; CSRF
// lấy qua GET /csrf cùng session và gắn vào CONNECT headers.
StompHeaders connect = new StompHeaders();
connect.add(csrfHeaderName, csrfTokenValue);

StompSession session = client
        .connectAsync(wsUrl, webSocketHeaders, connect, handler)
        .get(5, TimeUnit.SECONDS);

// Sau khi CONNECTED:
session.subscribe("/topic/announcements", subscriptionHandler);
session.send("/app/chat.send",
        "{\"text\":\"Hello\",\"from\":\"admin\"}".getBytes(UTF_8));

// subscriptionHandler phải nhận ChatEvent.author == "alice".
~~~

Tham số/method `connectAsync` có thể khác giữa các version Spring Framework/WebSocketStompClient; đối chiếu overload với dependency được chọn. Đặc biệt, `WebSocketStompClient` có cả HTTP handshake headers và STOMP CONNECT headers: đặt CSRF vào **STOMP** header, không nhầm hai phần. Không viết integration tests chỉ gửi CONNECT rồi coi toàn bộ MESSAGE/SUBSCRIBE routing đã được kiểm.

### 8.1. Vì sao chỉ test /ws handshake là chưa đủ?

HTTP GET `/ws` có thể trả 101 Switching Protocols cho một user đã authenticated, nhưng sau đó:
- STOMP CONNECT có thể thiếu CSRF và bị từ chối;
- client có thể thử SEND đến broker prefix;
- user có thể subscribe một topic không được phép;
- bearer token gửi trong STOMP header không tự được Authentication filter của HTTP parse;
- session có thể còn tồn tại sau khi role bị revoke.

Cần test cả **HTTP authn, STOMP CONNECT, inbound authorization, application business authorization và outbound visibility**.

### 8.2. 403 không nhất thiết hiển thị như HTTP 403

Một STOMP frame bị deny **sau khi WebSocket đã upgrade** không còn là HTTP request mới. Client có thể thấy STOMP ERROR frame, đóng connection hoặc lỗi trong session tùy Spring configuration/error handling. Đừng viết test kỳ vọng HTTP 403 cho mọi unauthorized SUBSCRIBE/SEND. Trạng thái HTTP 401/403 áp tại handshake; sau upgrade phải assert STOMP/session behavior và không nhận dữ liệu nhạy cảm.

### 8.3. Đo message side effect

Khi client SEND không được phép tới `/app/admin.broadcast`, test nên đảm bảo:
1. Không có server-side business handler execution.
2. Không có `SimpMessagingTemplate.convertAndSend("/topic/admin",...)`.
3. Không subscriber nào nhận event.
4. Security deny/audit metrics đúng role/destination/type.
5. Session error handling theo contract và không lộ stack trace/token.

Test chỉ assert không có HTTP response 200 chưa chứng minh đủ, vì WebSocket và STOMP có mô hình phản hồi khác.

## 9. Phân quyền theo room/tenant: custom AuthorizationManager<MessageAuthorizationContext<?>>

Role USER phù hợp cho demo nhưng thường **không đủ** với chat rooms/tenant. Nếu destination là `/topic/rooms/{roomId}`, cần kiểm mỗi actor là thành viên của room đó.

### 9.1. Ví dụ custom manager (trích đoạn class)

~~~java
package demo.socket;

import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.messaging.access.intercept.MessageAuthorizationContext;

// PIP giả định ở application server, không từ client headers.
interface RoomMemberships {
    boolean canSubscribe(String principalId, String roomId);
}

final class RoomSubscribeManager
        implements AuthorizationManager<MessageAuthorizationContext<?>> {
    private final RoomMemberships membership;

    RoomSubscribeManager(RoomMemberships membership) {
        this.membership = membership;
    }

    @Override
    @SuppressWarnings("deprecation")
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            MessageAuthorizationContext<?> context) {

        Authentication actor = authentication.get();
        String roomId = context.getVariables().get("roomId");
        if (actor == null || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken
                || roomId == null
                || !roomId.matches("[a-zA-Z0-9-]{1,48}")) {
            return new AuthorizationDecision(false);
        }

        try {
            return new AuthorizationDecision(
                    membership.canSubscribe(actor.getName(), roomId));
        } catch (RuntimeException failure) {
            // Real system: metric + alert; never fail open.
            return new AuthorizationDecision(false);
        }
    }
}
~~~

Đây là file tùy chọn riêng: interface `RoomMemberships` trong production lấy dữ liệu từ source được quản trị, có tenant scope, TTL và giới hạn độ trễ. Các imports `Map`, `Set` trong đoạn này không cần thiết và có thể được IDE loại bỏ; không ảnh hưởng compile. Khi áp dụng rule:

~~~java
// Trích đoạn trong messageAuthorizationManager Builder:
messages
    .simpSubscribeDestMatchers("/topic/rooms/{roomId}")
        .access(new RoomSubscribeManager(roomMemberships))
    .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
~~~

Đặt rule cụ thể **trước** deny chung. `MessageAuthorizationContext#getVariables()` lấy giá trị path variable đã match; đừng tự tách destination bằng `split("/")` mà không validate và chỉ mục. Đối với MESSAGE gửi tới room, cần policy tương ứng cho `/app/rooms/{roomId}/send` và kiểm owner/moderator trong application service.

### 9.2. Ranh giới của manager đồng bộ

`AuthorizationManager<Message<?>>` là synchronous authorization interface. Nếu room membership cần gọi DB/remote PIP, **không** đặt blocking network call không timeout trên inbound executor. Có thể dùng trusted cache với TTL/invalidation nghiêm, hoặc kiến trúc message/service layer phù hợp cho async verification trước side effect. Nếu quyền cần chính xác tại từng SEND, service nên kiểm lại trạng thái/tenant/ACL trước khi publish. Không dùng `CompletableFuture.runAsync(...); return true` hoặc `subscribe()` fire-and-forget bên trong manager.

### 9.3. Tenant ID trong destination không tự chứng minh membership

`SUBSCRIBE /topic/tenant/beta` là request do client tự chọn. Nếu Alice chỉ có membership alpha, matcher `/topic/tenant/**.authenticated()` là sai. Manager phải lấy actor từ authenticated principal và kiểm membership trong tenant beta từ nguồn tin cậy. Khi broker thực sự broadcast thông báo nhạy cảm, dùng per-tenant destinations, authorization tại subscription, isolation ở server producer và data-retention policy.

### 9.4. Không trust custom STOMP headers

Các native headers `x-tenant`, `role`, `userId`, `isAdmin`, `subscription-owner` có thể bị client giả. Chúng chỉ là selectors/metadata chưa được chứng minh. `SimpMessageHeaderAccessor#getUser()` đáng tin khi Spring đã liên kết Principal từ verified handshake hoặc interceptor token verification được triển khai đúng. Tránh set user từ body.

## 10. User destinations và bảo mật queue riêng

Spring hỗ trợ prefix `/user/` cho user-specific destinations:
- Client Alice đăng ký `/user/queue/errors`.
- Controller có `@SendToUser(value="/queue/errors",broadcast=false)` hoặc server dùng `convertAndSendToUser(username, "/queue/messages", payload)`.
- Spring resolves thành đích broker theo session/user thực tế, không đơn thuần một topic `/queue/errors` chung cho mọi người.

Đặc biệt:
- Không cho client subscribe trực tiếp `/queue/**`, vì path internal của broker có thể có private queue của user khác.
- Không cấp quyền dựa trên username trong STOMP `destination` nếu username đó do client tự ghi.
- `/user/**.permitAll()` có thể quá rộng; cần authenticate và giới hạn từng destination hoặc kiểm object permission nếu chứa dữ liệu nhạy cảm.
- Khi cần nhận thông báo dưới nhiều devices/sessions, hãy xác định fanout, offline notification, data retention và user-session mapping.
- Với broker relay bên ngoài, kiểm cấu hình user-destination prefix, queue TTL/cleanup và broker ACL; Spring inbound deny không tự là broker ACL.

### 10.1. Có được dùng @SendToUser làm lớp authorization duy nhất?

Không. `@SendToUser` giúp route response đến user/session nhưng không thay thế kiểm quyền của action gửi message, không thay tenant/resource ACL và không bảo vệ mọi broker topic đã được subscribe. Phân quyền inbound, nghiệp vụ và routing đều cần đúng.

### 10.2. Tránh gửi internal exception details

Một `@MessageExceptionHandler` có thể phản hồi mã lỗi gọn như `INVALID_PAYLOAD`. Không trả message chứa SQL, bearer token, stacktrace hoặc thông tin room của tenant khác. Phân biệt lỗi input validation và authorization failure, tránh báo chi tiết khiến attacker suy đoán sự tồn tại của private rooms/users.

## 11. AuthorizationManager tự viết và default-deny

Ngoài Builder, có thể tự viết toàn bộ:

~~~java
AuthorizationManager<Message<?>> gate = (authentication, message) -> {
    Authentication actor = authentication.get();
    SimpMessageType type =
            SimpMessageHeaderAccessor.getMessageType(
                    message.getHeaders());
    String destination =
            SimpMessageHeaderAccessor.getDestination(
                    message.getHeaders());

    boolean allowed = actor != null
            && actor.isAuthenticated()
            && type == SimpMessageType.MESSAGE
            && "/app/chat.send".equals(destination)
            && actor.getAuthorities().stream().anyMatch(
                a -> "ROLE_USER".equals(a.getAuthority()));

    return new AuthorizationDecision(allowed);
};
~~~

Đây là **trích đoạn**, không phải thay thế an toàn hoàn chỉnh: check `actor.isAuthenticated()` cần phân biệt anonymous, xét CONNECT/SUBSCRIBE/control frames và CSRF. Viết custom full manager khi cần logic khó biểu đạt bằng matchers; tốt nhất bắt đầu từ Builder để có default-deny và rule dễ đọc/test. Trong 6.5, lambda phù hợp functional contract của `AuthorizationManager`; khi nâng cấp phiên bản, xem Javadoc và warning deprecation.

### 11.1. Policy không có rule trùng lặp không cần thiết

Ví dụ:

~~~java
messages
    .simpDestMatchers("/topic/**").authenticated()
    .simpSubscribeDestMatchers("/topic/admin").hasRole("ADMIN")
    .anyMessage().denyAll();
~~~

**Sai:** rule đầu đã match SUBSCRIBE `/topic/admin` và có thể match cả SEND, nên rule ADMIN phía sau không còn hiệu lực. Thứ tự phải đặt specific first và dùng `simpSubscribeDestMatchers` cho subscribe; tránh wildcard broker prefixes.

### 11.2. Một deny rule rõ ràng thắng thói quen anyMessage.authenticated()

`anyMessage().authenticated()` cho authenticated client gửi mọi MESSAGE/SUBSCRIBE chưa khai báo, bao gồm cả broker topics. Một feature mới xuất hiện có thể trở thành accessible mà không ai nhớ bổ sung rule. Dùng `anyMessage().denyAll()`, mở thêm destinations bằng review/test cụ thể.

### 11.3. Session CONNECT không phải giấy phép phát mọi message

CSRF/Origin và authentication ở CONNECT chứng minh điều kiện thiết lập phiên, không biến mọi SUBSCRIBE hay SEND thành hợp lệ. Một actor có thể được CONNECT nhưng thiếu role để subscribe admin topic; policy phải kiểm từng inbound frame.

## 12. So sánh với HTTP và method security

| Lớp | Đầu vào authorize | Dùng để bảo vệ |
| --- | --- | --- |
| HTTP request security | `HttpServletRequest` | URL handshake `/ws`, HTTP login, CSRF endpoint |
| WebSocket message security | `Message<?>` với type/destination/Principal | STOMP SEND/SUBSCRIBE/CONNECT đi vào |
| Method security | `MethodInvocation`, `@PreAuthorize` | Service method được gọi qua proxy |
| Object/tenant ACL | Principal + resource owner/membership | Tài nguyên cụ thể ở repository/business logic |
| Broker ACL | Broker identity, destination rules | Trực tiếp message queue/topic ở external broker |
| Outbound message filtering | Application event/routing policy | Recipient thật sự được nhận payload nào |

Phải có **nhiều lớp**: HTTP authorization không tự suy ra STOMP authorization; STOMP role matcher không tự chứng minh room membership; `@MessageMapping` được gọi sau inbound authorization nhưng business action vẫn cần validation/transaction; broker relay có thể chấp nhận message từ nguồn khác nếu cấu hình sai.

### 12.1. Đừng nhầm Spring WebFlux WebSocket handler

`@EnableWebSocketSecurity` trong bài dựa trên **Spring Messaging/STOMP của Servlet WebSocket message broker**, không phải một `WebSocketHandler` thuần kiểu WebFlux/reactive stream. Nếu ứng dụng dùng reactive WebFlux WebSocketHandler không dùng Spring STOMP broker, cần policy/authentication tích hợp riêng tại handshake và message stream; đừng tin annotation này sẽ tự bảo vệ mọi raw WebSocket payload.

### 12.2. Đừng nhầm Spring Integration messaging

`AuthorizationManager<Message<?>>` với Spring Security Messaging dựa trên Spring Messaging inbound channel cho STOMP, không phải bảo đảm Spring Security sẽ intercept mọi Spring Integration channel/JMS/Kafka message. Các transport khác cần authorization ở consumer/producer và broker ACL thích hợp.

## 13. Chạy Java 17 độc lập để nhìn rõ policy

Chương trình thuần JDK dưới đây mô phỏng policy của demo. Nó không mở socket/không có CSRF/không có AOP hay Spring Security. Chúng ta tách actor, type và destination để thấy một **role và một destination** vẫn chưa đủ; phải xét thêm **message type**.

Lưu `StompPolicyDemo.java`:

~~~java
import java.util.Set;

public class StompPolicyDemo {
    enum Type { CONNECT, DISCONNECT, SEND, SUBSCRIBE, OTHER }

    record Actor(String name, Set<String> roles, boolean authenticated) {}
    record Frame(Type type, String destination) {}

    static boolean allowed(Actor actor, Frame frame) {
        if (actor == null || !actor.authenticated()
                || frame == null || frame.type() == null) {
            return false;
        }
        String to = frame.destination();

        if (frame.type() == Type.SEND) {
            return ("/app/chat.send".equals(to)
                        && actor.roles().contains("USER"))
                    || ("/app/admin.broadcast".equals(to)
                        && actor.roles().contains("ADMIN"));
        }
        if (frame.type() == Type.SUBSCRIBE) {
            return ("/topic/announcements".equals(to)
                        && actor.roles().contains("USER"))
                    || ("/topic/admin".equals(to)
                        && actor.roles().contains("ADMIN"))
                    || "/user/queue/errors".equals(to);
        }
        if (frame.type() == Type.CONNECT
                || frame.type() == Type.DISCONNECT) {
            // Chỉ mô phỏng AUTHN, chưa kiểm CSRF của CONNECT.
            return to == null;
        }
        return false;
    }

    private static void show(String label, Actor actor, Frame frame) {
        System.out.println(label + "=" + allowed(actor, frame));
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", Set.of("USER"), true);
        Actor admin = new Actor(
                "admin", Set.of("USER", "ADMIN"), true);
        Actor viewer = new Actor("viewer", Set.of("VIEWER"), true);
        Actor anonymous = new Actor("anonymous", Set.of(), false);

        show("alice-connect", alice,
                new Frame(Type.CONNECT, null));
        show("alice-send-chat", alice,
                new Frame(Type.SEND, "/app/chat.send"));
        show("alice-subscribe-news", alice,
                new Frame(Type.SUBSCRIBE, "/topic/announcements"));
        show("alice-send-topic", alice,
                new Frame(Type.SEND, "/topic/announcements"));
        show("alice-subscribe-admin", alice,
                new Frame(Type.SUBSCRIBE, "/topic/admin"));
        show("admin-subscribe-admin", admin,
                new Frame(Type.SUBSCRIBE, "/topic/admin"));
        show("admin-send-topic", admin,
                new Frame(Type.SEND, "/topic/admin"));
        show("viewer-send-chat", viewer,
                new Frame(Type.SEND, "/app/chat.send"));
        show("alice-private-queue", alice,
                new Frame(Type.SUBSCRIBE, "/queue/private"));
        show("anonymous-connect", anonymous,
                new Frame(Type.CONNECT, null));
        show("alice-unknown", alice,
                new Frame(Type.OTHER, "/app/chat.send"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 StompPolicyDemo.java
java StompPolicyDemo
~~~

**stdout chính xác:**

~~~text
alice-connect=true
alice-send-chat=true
alice-subscribe-news=true
alice-send-topic=false
alice-subscribe-admin=false
admin-subscribe-admin=true
admin-send-topic=false
viewer-send-chat=false
alice-private-queue=false
anonymous-connect=false
alice-unknown=false
~~~

Tại sao kết quả đáng chú ý?
- Admin có thể subscribe `/topic/admin` nhưng **không được tự SEND** đến broker topic đó; admin gửi qua `/app/admin.broadcast`.
- Alice có thể gửi chat qua app controller và subscribe thông báo thường; không thể nghe topic admin.
- Viewer authenticated vẫn không có `ROLE_USER`.
- Client có thể thử gửi tên destination lạ, nhưng policy mặc định deny.
- `CONNECT=true` ở chương trình chỉ mô phỏng authentication; **STOMP CONNECT thật còn cần CSRF token và checks của framework**.
- Bộ mô phỏng này không kiểm Principal từ handshake; full Spring test phải làm việc đó.

## 14. Multi-tenant, ownership và broker-level isolation

Giả sử tenant alpha và beta cùng có room ID `7`. Một destination chung `/topic/rooms/7` có thể trộn sự kiện nếu server chỉ phân biệt roomId mà không phân biệt tenant. Cách tốt hơn:
- Dùng key canonical `(tenantId, roomId)` cho DB/repository/topic routing (ví dụ `/topic/tenants/alpha/rooms/7`).
- Ở SUBSCRIBE, kiểm authenticated principal có membership tenant alpha và quyền đọc room 7; mọi ID trong path chỉ là selectors.
- Ở SEND `/app/tenants/alpha/rooms/7`, kiểm lại membership và quyền gửi; không tin `fromUser` trong payload.
- Khi server broadcast, bảo đảm chỉ phát dữ liệu của alpha vào topic alpha. Bảo vệ cả producer, không chỉ subscriber.
- Với role revocation/tenant switch, cần invalidate/disconnect subscriptions hoặc event policy, không giữ stale ALLOW vô hạn.
- Trong cluster, consistent hashing/broker relay session destinations và routing phải giữ tenant isolation; mọi instance dùng cùng security contract.

### 14.1. Private subscription theo object cần per-object ACL

Một user thuộc tenant alpha không mặc nhiên được xem tài liệu confidential alpha:7. Custom subscription manager cần kiểm record ACL/owner/classification; với high-impact data, server có thể cấp dedicated user queue thay vì shared topic. `/user/queue/**` không tự chứng minh object-level permission.

### 14.2. Không chuyển payload nhạy cảm sang topic công cộng rồi hy vọng filter

Vì Spring Security inbound-only, một broadcast nhầm `/topic/announcements` có thể đến tất cả authorized subscribers của topic. Phải làm data classification/redaction/recipient selection **trước publish**. Với tài liệu, cân nhắc chỉ publish “document updated” kèm opaque ID rồi client gọi REST API đã authorize để tải nội dung.

## 15. CSRF/Origin thực tế và SockJS

| Tình huống | Điều cần kiểm |
| --- | --- |
| Browser same-origin session | GET /csrf, STOMP CONNECT đúng native token, cookie/session được giữ |
| Origin lạ, session cookie có thể được gửi | Handshake Origin allowlist + STOMP CONNECT CSRF |
| SockJS fallback XHR | Endpoint HTTP paths và CSRF/Frame headers, không bỏ bảo vệ toàn site |
| Java non-browser client | Origin có thể giả, cần authenticated handshake/token, không dựa Origin đơn độc |
| JWT ở HTTP handshake | Validate đúng access token và bind Principal cho session |
| JWT ở STOMP CONNECT | Custom ChannelInterceptor verify token trước message authz |
| CSRF token sai/hết hạn hoặc session khác | CONNECT bị từ chối, không có quyền subscribe |
| TLS offload ở ingress | Proxy routing, forwarded headers và WSS đúng; tránh mixed-content |
| Cross-origin cần hỗ trợ chính thức | Threat model riêng, không wildcard + cookie + disable CSRF |
| Session reconnect | Re-authenticate/recheck permissions, không reuse stale authorization |

Đối với server-side rendered app, có thể lấy CsrfToken từ request attribute hoặc API token endpoint; với SPA, cách lấy token phụ thuộc session/cookie/CORS và CSRF repository. Không đưa CSRF token vào third-party analytics hay logs; mặc dù CSRF token không giống access token, nó vẫn là security-sensitive token trong session lifecycle.

## 16. Observability, lỗi và khả năng vận hành

Những sự kiện nên theo dõi:
- `WebSocketSessionConnectedEvent`/`SessionConnectEvent`/`SessionSubscribeEvent`/`SessionDisconnectEvent` (tên event phụ thuộc tầng và phiên bản) để quan sát lifecycle, không thay authorization logic.
- Rate message theo actor/tenant/destination; số subscriptions mỗi session, số frames bị deny.
- Authn handshake failure, CSRF CONNECT deny, Origin reject, message rule deny, PIP/ACL error và broker disconnect được phân loại riêng.
- Correlation ID từ HTTP handshake → STOMP session ID → message ID, không log raw JWT/cookie/CSRF tokens.
- Broker relay up/down, user registry state, fanout size, message queue lag, backpressure và cleanup stale subscriptions.
- Không log full chat/document payload theo mặc định; che PII/tenant secrets, chỉ log thuộc tính cần cho audit.

Một STOMP authorization exception thường không có HTTP response mới; tuỳ handler, client nhận ERROR frame hoặc connection close. Nếu cần mã lỗi nghiệp vụ thân thiện, đừng lộ cụ thể “room của người khác tồn tại nhưng bạn không được xem”. Sử dụng deny reason nội bộ và client-facing code ổn định.

### 16.1. Một sự cố broker không được mở quyền

Nếu backend ACL/PIP không truy cập được, custom manager nên deny/error-closed; không `catch (...) { return new AuthorizationDecision(true); }`. Có thể trả lỗi transient để client reconnect có giới hạn, nhưng không bypass subscription permission. Các danh sách quyền cache phải có TTL, version và revoke strategy.

### 16.2. Reconnect không mang toàn bộ quyền cũ

Khi WebSocket session ngắt và kết nối mới, xác thực handshake lại theo token/cookie hiện tại; quyền user/room có thể đã đổi. Nếu sử dụng STOMP auto-reconnect, client cần lấy CSRF/session/token mới khi cần; không giữ credential hết hạn và retry vô hạn khiến lockout/rate limiting.

## 17. Ma trận QA trước khi triển khai

| Case | Kỳ vọng |
| --- | --- |
| Alice authenticated + CSRF hợp lệ CONNECT | CONNECTED |
| CONNECT không có CSRF hoặc sai session | Bị từ chối trước SUBSCRIBE |
| HTTP handshake không authenticated | Handshake 401/redirect theo entrypoint |
| Handshake Origin lạ | Rejected theo allowlist |
| Alice SEND /app/chat.send | Handler chạy, author = Alice |
| Alice payload from="admin" | Author vẫn Alice |
| Alice SUBSCRIBE /topic/announcements | Allowed |
| Alice SEND /topic/announcements | Denied, không broker publish |
| Alice SUBSCRIBE /topic/admin | Denied, không nhận event |
| Admin SUBSCRIBE /topic/admin | Allowed |
| Admin SEND /app/admin.broadcast | Allowed; server publish topic admin |
| Admin SEND /topic/admin trực tiếp | Denied dù có ROLE_ADMIN |
| Viewer SEND /app/chat.send | Denied |
| Client SUBSCRIBE /queue/private | Denied |
| Client SUBSCRIBE /user/queue/errors | Authenticated; user destination scoped |
| Client SUBSCRIBE /app/chat.send | Denied, không nhầm MESSAGE |
| Unknown destination SEND/SUBSCRIBE | Deny by default |
| Missing destination MESSAGE/SUBSCRIBE | Denied trước nullDestMatcher |
| Anonymous CONNECT | Denied |
| Role USER nhưng thiếu room membership | Denied bởi custom manager |
| Tenant beta chọn destination alpha | Denied |
| User role bị revoke khi session còn live | Theo reauthorization/disconnect SLA |
| Broken broker/ACL service | No fail open |
| Invalid oversized/malformed message | Không crash, không vượt quyền, rate limit |
| Remote broker gửi message trái policy | Broker ACL/server producer boundary |
| @MessageMapping self-call/side effect | Business checks trước publish |
| Incorrect role prefix ROLE_ | Negative authority tests phát hiện |
| WebFlux handler không dùng STOMP | Không tự nhận bảo vệ từ annotation này |
| Unit policy tests pass | Không thay CSRF/Origin real integration |
| STOMP ERROR frame | Không lộ SQL/stack/JWT |
| Subscriber có permission nhưng event chứa tenant khác | Producer validation bắt buộc |

### 17.1. Mutation tests

Trong một test branch, thử:
1. Đổi `simpMessageDestMatchers("/app/chat.send")` thành `simpDestMatchers("/**")` → negative direct broker SEND test phải đỏ.
2. Bỏ `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` → unknown destination test phải đỏ hoặc policy phải có `anyMessage().denyAll()` vẫn bảo vệ.
3. Đổi `anyMessage().denyAll()` thành `authenticated()` → các test unexpected message phải đỏ.
4. Cho `/topic/admin` subscribe bằng `authenticated()` → Alice negative test phải đỏ.
5. Lấy `ChatRequest.from()` thay `principal.getName()` → spoof-author integration test phải đỏ.
6. Bỏ CSRF CONNECT interceptor ở test environment → missing-CSRF integration test phải đỏ.
7. Bỏ predicate tenant của PIP room → cross-tenant subscription test phải đỏ.
8. Cho CLIENT SEND trực tiếp `/topic/**` → broker impersonation test phải đỏ.

Nếu test không phát hiện các mutation này, suite chưa chứng minh được ranh giới inbound messaging.

## 18. Lỗi thường gặp

### Lỗi 1 — Chỉ cấu hình HTTP SecurityFilterChain
Handshake authenticated không đồng nghĩa mọi SEND/SUBSCRIBE được phép. Cần `@EnableWebSocketSecurity` và bean `AuthorizationManager<Message<?>>`.

### Lỗi 2 — Dùng simpDestMatchers("/topic/**").authenticated()
Không giới hạn message type; client có thể tự gửi broker topic. Dùng `simpSubscribeDestMatchers` và deny SEND broker prefixes.

### Lỗi 3 — PermitAll cho every CONNECT vì tưởng chỉ là handshake
CONNECT còn cần authenticated Principal và CSRF đúng session; anonymous/Origin lạ không được có quyền subscribe.

### Lỗi 4 — Tin header "role=ADMIN" hoặc "user=alice"
Các native STOMP headers/payload do client khai không tự là authority. Principal lấy từ verified HTTP auth hoặc interceptor token validation đáng tin.

### Lỗi 5 — Cho SUBSCRIBE /queue/**
Có thể nghe queue private hoặc đường nội bộ broker. Chỉ cho `/user/queue/<approved>` hoặc topic được check ACL.

### Lỗi 6 — Dùng /user/{otherUsername} do client nhập
User destination xử lý routing nhưng không phải chỗ cho client chọn identity khác. Server gửi tới user bằng trusted principal.

### Lỗi 7 — Đặt broad matcher trước role-specific rule
First match wins; một `authenticated()` quá rộng có thể làm `hasRole("ADMIN")` không còn ý nghĩa.

### Lỗi 8 — anyMessage().authenticated()
Mở tất cả message chưa khai báo cho mọi user đăng nhập. Dùng `denyAll` mặc định.

### Lỗi 9 — Tưởng outbound bị Spring Security tự intercept
Tài liệu Spring Security nói inbound-only. Quyền subscribe và producer data-scoping là ranh giới chính.

### Lỗi 10 — Tắt CSRF toàn site cho SockJS
Relax HTTP CSRF/frames nếu cần phải giới hạn đúng endpoint và duy trì CONNECT token/Origin strategy; không tắt global.

### Lỗi 11 — Dùng WS thay WSS ở production
Cookie/token/plain traffic bị lộ; dùng TLS, proxy cấu hình đúng.

### Lỗi 12 — Chỉ dùng Origin như authentication
Non-browser clients có thể giả Origin; identity và authorization vẫn bắt buộc.

### Lỗi 13 — STOMP login/passcode được coi là Spring user
Mặc định HTTP handshake Principal là nguồn authn; nếu muốn STOMP-level auth phải cấu hình xác thực riêng.

### Lỗi 14 — Một user authenticated có thể subscribe mọi tenant
Tenant trong destination là input client. Cần membership/object ACL từ nguồn tin cậy, không chỉ `hasRole("USER")`.

### Lỗi 15 — Không kiểm owner/source trong payload
Tin `from` gây giả mạo người gửi. Dùng Principal từ server, không tự copy userId.

### Lỗi 16 — Chỉ kiểm một Unit Test cho @MessageMapping
Có thể bypass inbound manager/CSRF/routing. Cần test message manager riêng và STOMP integration qua network.

### Lỗi 17 — Kỳ vọng 403 HTTP cho mọi denied STOMP frame
Sau upgrade là protocol STOMP, không phải HTTP request mới; assert ERROR/close/no delivery theo contract.

### Lỗi 18 — Role bị revoke nhưng session kéo dài mãi
Cần quyền/revocation freshness, recheck các messages quan trọng và disconnect/invalidate theo SLA.

### Lỗi 19 — Trộn Servlet STOMP với raw WebFlux WebSocket Handler
Annotation theo Spring Messaging inbound không bao phủ mọi transport/handler; chọn đúng security integration.

### Lỗi 20 — Đọc mọi resource global theo ID trong @MessageMapping
Dù message AUTHORIZED về role, DB query vẫn phải tenant-scoped/object-specific, không bao giờ lộ record tenant khác.

## 19. Checklist triển khai

- [ ] App thực sự dùng Spring STOMP over WebSocket message broker trên Servlet, đúng Spring Boot/Security versions.
- [ ] `@EnableWebSocketMessageBroker` đăng ký `/ws`, `/app`, `/topic`, `/queue`, `/user` theo routing thật.
- [ ] HTTP handshake `/ws` được authenticate và có Origin allowlist; production dùng WSS.
- [ ] `@EnableWebSocketSecurity` cùng bean `AuthorizationManager<Message<?>>` được Spring nạp.
- [ ] `simpMessageDestMatchers` chỉ dành cho client SEND vào `/app/...` đã cấp.
- [ ] `simpSubscribeDestMatchers` chỉ cho phép subscribe đúng topic/user destination có quyền.
- [ ] Không cho client trực tiếp SEND broker `/topic/**`, `/queue/**`.
- [ ] Rule specific trước, deny unmatched MESSAGE/SUBSCRIBE và `anyMessage().denyAll()`.
- [ ] CONNECT frame kiểm authenticated Principal và CSRF token cùng session.
- [ ] Không tin STOMP native headers/payload làm identity/role/tenant.
- [ ] `hasRole("USER"/"ADMIN")` khớp authority `ROLE_USER`/`ROLE_ADMIN` của Authentication provider.
- [ ] @MessageMapping chỉ dùng Principal từ server và validate body/length/type.
- [ ] Server publish đúng tenant/topic/recipient; outbound không được framework tự authorize.
- [ ] Room/tenant subscription kiểm membership/ACL/revocation, không dựa role global.
- [ ] Broker relay, user destinations, session registry và production transport đã có threat model.
- [ ] Integration tests handshake/CONNECT-CSRF/SUBSCRIBE/SEND/denied delivery chạy thật.
- [ ] Unit tests manager dùng MESSAGE vs SUBSCRIBE, unknown, admin, anonymous và malformed destinations.
- [ ] Logging/metrics tránh raw token, cookie, CSRF, private chat contents; theo dõi deny/errors.
- [ ] Không dùng legacy AbstractSecurityWebSocketMessageBrokerConfigurer nếu đang áp mô hình mới mà chưa migration.
- [ ] Không tuyên bố unit test thay chữ ký, CSRF, Origin/broker end-to-end tests.

## 20. Câu hỏi ôn tập

**Câu 1.** Vì sao `simpDestMatchers("/topic/**").hasRole("USER")` không tương đương với `simpSubscribeDestMatchers("/topic/**").hasRole("USER")`?

**Đáp án:** Matcher đầu không giới hạn loại message, nên một client có ROLE_USER có thể được phép SEND trực tiếp tới broker topic. Matcher thứ hai chỉ cho frame SUBSCRIBE, còn SEND không match và bị deny bởi fallthrough rules.

**Câu 2.** User có ROLE_ADMIN được SUBSCRIBE `/topic/admin`. Có nên cho SEND thẳng destination đó?

**Đáp án:** Không. Ngay cả admin cũng nên gọi một `/app/admin.broadcast` handler được validate, còn broker notification do server phát. Quyền subscribe không tự là quyền publish.

**Câu 3.** WebSocket đã handshake thành công có thể bỏ STOMP CONNECT CSRF không?

**Đáp án:** Không trong cấu hình `@EnableWebSocketSecurity` mặc định được mô tả ở đây. Browser cross-origin và cookie session có nguy cơ CSWSH; token trong STOMP CONNECT cùng Origin policy là lớp quan trọng.

**Câu 4.** Tại sao `x-user:alice` trong STOMP SEND không dùng làm author?

**Đáp án:** Client có thể tự ghi bất kỳ giá trị nào. Controller phải dùng Principal mà Spring Security đã xác thực từ handshake/authorized interceptor.

**Câu 5.** `AuthorizationManager<Message<?>>` có tự lọc mọi outbound event cho từng subscriber không?

**Đáp án:** Không. Spring Security Messaging tập trung inbound; SUBSCRIBE authorization, broker routing và data-producer validation phải được thiết kế để dữ liệu sai scope không được phát.

**Câu 6.** Khi role ADMIN bị thu hồi giữa một WebSocket session kéo dài, chuyện gì xảy ra?

**Đáp án:** Authentication/authorities từ handshake có thể stale. Cần chính sách reauthorization, ACL lookup, disconnect/reconnect và revoke SLA; không giả định role tự cập nhật.

**Câu 7.** Một frame inbound MESSAGE không có destination có nên được `nullDestMatcher().authenticated()` cho phép không?

**Đáp án:** Không trong policy chặt. Đặt `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` trước `nullDestMatcher` để loại malformed data frames.

**Câu 8.** Có thể dùng `@EnableWebSocketSecurity` để bảo vệ mọi raw WebSocketHandler của WebFlux không?

**Đáp án:** Không. Đây là integration cho Spring Messaging/STOMP. Raw WebSocket/WebFlux cần authentication và message authorization riêng.

**Câu 9.** Vì sao unit test chỉ gọi builder.check không chứng minh CONNECT CSRF hoạt động?

**Đáp án:** CSRF được kiểm ở interceptor trong flow STOMP/handshake thực, không phải bởi từng rule role/destination; cần STOMP integration test.

**Câu 10.** Khi hai tenant có cùng roomId 7, vì sao không thể subscribe tất cả `/topic/rooms/7`?

**Đáp án:** ID không duy nhất theo tenant; phải dùng tenant-scoped resource identities, membership và routing. Nếu không, một tenant có thể nghe thông báo của tenant khác.

## 21. Kết luận

**WebSocket message authorization là bài toán theo bộ ba: actor đã xác thực + message type + destination được phép.** Với Spring Security 6.5, `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>` cho phép diễn đạt chính sách này bằng các matcher rõ ràng:

~~~text
Authenticated HTTP handshake + allowed Origin + WSS
     |
     v
STOMP CONNECT + CSRF token
     |
     v
clientInboundChannel
     |
     v
AuthorizationManager<Message<?>>
     |
     +-- CONNECT/control frame: authenticated
     +-- MESSAGE /app/...: explicit role/action permission
     +-- SUBSCRIBE /topic/...: explicit role/room ACL permission
     +-- MESSAGE /topic/** or /queue/**: DENY
     +-- unknown/malformed: DENY
     |
     v
@MessageMapping business verification
     |
     v
Server-side broker publish with trusted actor/tenant/recipient
     |
     v
Only authorized subscriptions receive data
~~~

Hãy nhớ: `/ws` là URL handshake; `/app/**` là application destination; `/topic/**` và `/queue/**` là broker destinations; `/user/**` là user-destination routing. Đừng đánh đồng quyền **gửi** với quyền **đăng ký nghe**; đừng coi HTTP authentication là đủ cho mọi STOMP frame; đừng kỳ vọng Spring tự lọc outbound message. **Bắt đầu bằng DENY, mở đúng loại frame và đúng destination, rồi kiểm thêm tenant/object policy tại ranh giới nghiệp vụ.**

## Tài liệu chính thức

- [Spring Security 6.5 – WebSocket Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html): annotation, message manager, inbound types, CSRF, origins, user destinations và outbound notes.
- [Spring Security – @EnableWebSocketSecurity Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/socket/EnableWebSocketSecurity.html): khai báo bean `AuthorizationManager<Message<?>>`.
- [Spring Security 6.5 – MessageMatcherDelegatingAuthorizationManager.Builder Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html): `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `nullDestMatcher`, `anyMessage`.
- [Spring Security 6.5 – MessageAuthorizationContext Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageAuthorizationContext.html): `getMessage()` và `getVariables()`.
- [Spring Framework – STOMP Message Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): endpoints, application destination prefixes, broker prefixes.
- [Spring Framework – STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): handshake Principal, STOMP headers và ChannelInterceptor.
- [Spring Framework – User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): `/user`, `@SendToUser`, `convertAndSendToUser`.
- [Spring Framework – WebSocket Allowed Origins](https://docs.spring.io/spring-framework/reference/web/websocket/server.html#websocket-server-allowed-origins): origin restriction và browser/non-browser boundary.
- [Spring Security – CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF token lifecycle.
