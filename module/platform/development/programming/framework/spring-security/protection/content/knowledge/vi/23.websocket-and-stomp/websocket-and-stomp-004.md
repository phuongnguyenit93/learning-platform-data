# Kế thừa danh tính từ kết nối HTTP

## 1. Bài toán: user đã đăng nhập HTTP thì WebSocket biết họ là ai bằng cách nào?

Trong một hệ thống theo dõi đơn hàng, Alice đăng nhập qua HTTPS. Trình duyệt có session cookie do server phát. Sau đó frontend mở một kết nối realtime:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");
~~~

Alice không gửi username trong câu lệnh trên, nhưng server có thể biết socket thuộc về Alice. Cơ chế phổ biến của Spring là:

1. Browser gửi session cookie phù hợp vào **HTTP WebSocket handshake**.
2. Spring Security xử lý request HTTP, xác thực session và tạo một `Authentication`/`Principal`.
3. Spring WebSocket lấy principal của HTTP request đã xác thực và gắn với **WebSocket session**.
4. Khi dùng Spring STOMP Messaging, principal này được truyền vào **inbound message context**.
5. Ứng dụng có thể nhận `Principal` trong phương thức `@MessageMapping` và dùng nó kiểm tra quyền trên dữ liệu.

Nhưng kế thừa danh tính **không** có nghĩa kết nối được phép làm tất cả:

- HTTP 101 chỉ cho thấy WebSocket transport được thiết lập.
- STOMP `CONNECT` còn có kiểm tra riêng, trong đó Spring Security Messaging có thể yêu cầu CSRF token.
- STOMP `SEND` và `SUBSCRIBE` phải có message authorization theo type/destination.
- Việc sửa một đơn hàng phải được kiểm tra theo principal, object ID và tenant ở backend.
- Một WebSocket đã mở từ trước không mặc nhiên cập nhật principal/quyền ngay khi user logout hoặc role thay đổi.

Đây là bài thuộc chương **WebSocket và STOMP** của `SPRING_SECURITY_HTTP_PROTECTION`. Trong phạm vi mô-đun bảo vệ HTTP và trình duyệt, bài liên hệ authentication, CSRF, CORS và kiểm tra Origin, session protection, HTTP security headers, CSP, HSTS/TLS và HTTP firewall. Ví dụ chính dùng **Spring Security Servlet + STOMP**, đồng thời đối chiếu **WebFlux native WebSocket**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả luồng `HttpServletRequest.getUserPrincipal()` → WebSocket session → STOMP messages → `@MessageMapping Principal`.
2. Hiểu điều kiện để Spring kế thừa authentication tại HTTP handshake, kể cả session cookie và proxy.
3. Phân biệt danh tính được **kế thừa từ HTTP** với việc **xác thực token trong STOMP CONNECT**.
4. Giải thích vì sao `login`, `passcode` hoặc `userId` do client khai trong frame không tự trở thành Spring Security principal.
5. Dùng `Principal` và `SimpMessagingTemplate.convertAndSendToUser(...)` để gửi thông báo đúng người.
6. Tách HTTP handshake authentication, CSRF CONNECT, message authorization và object-level authorization.
7. Kiểm tra logout, role revocation, expiry, reconnect và an toàn của các phiên WebSocket dài hạn.
8. Áp dụng tương tự trên Reactive bằng `WebSocketSession.getHandshakeInfo().getPrincipal()`, không đồng nhất WebFlux native với STOMP broker Servlet.
9. Thiết kế kiểm thử positive/negative cho identity inheritance, forged user headers và quyền truy cập dữ liệu.

Tên miền `example.com` trong tài liệu là minh họa, không phải endpoint có sẵn.

## 2. Bốn khái niệm cần phân biệt

| Khái niệm | Vai trò | Có được kế thừa tự động không? |
| --- | --- | --- |
| **HTTP authentication** | Xác minh danh tính trên request bắt tay, thông qua session cookie, HTTP credentials hoặc cơ chế khác đã cấu hình | Là nguồn chính của principal trong mô hình mặc định |
| **WebSocket session principal** | Danh tính gắn với WebSocket connection sau handshake | Spring WebSocket thường lấy từ authenticated HTTP request |
| **STOMP message principal** | Danh tính mà Spring Messaging nhìn thấy khi xử lý inbound frames | Thường gắn với principal của WebSocket session, trừ khi có cơ chế CONNECT authentication tùy biến |
| **Authorization** | Kiểm tra user được SEND/SUBSCRIBE và truy cập object nào | **Không được cấp tất cả chỉ vì principal tồn tại** |

**Authentication** trả lời “đây là ai?”. **Authorization** trả lời “người đó được làm gì?”. Principal được truyền từ HTTP giúp tránh phải tin user ID trong từng message, nhưng quyền vẫn phải được kiểm tra đúng tầng.

### 2.1. Danh tính là server-side, không phải một header tự khai

Một STOMP client có thể gửi:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
login:admin
passcode:secret

^@
~~~

Với cấu hình Spring WebSocket Message Broker mặc định, `login` và `passcode` **không tự xác thực user của ứng dụng**. Các trường này có thể liên quan tới giao thức hoặc cấu hình broker relay, nhưng không được coi là bằng chứng caller có role ADMIN. Spring cần một authentication thực sự đã được xác minh.

Tương tự, client gửi JSON:

~~~json
{"username":"bob","orderId":2002}
~~~

không làm connection chuyển principal từ Alice sang Bob. Username trong payload là **dữ liệu không tin cậy**.

## 3. Luồng kế thừa danh tính qua HTTP handshake

Khi frontend mở WebSocket, browser tạo HTTP handshake (ví dụ HTTP/1.1):

~~~http
GET /ws HTTP/1.1
Host: api.example.com
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Origin: https://app.example.com
Cookie: SESSION=<alice-session-if-browser-allows>
~~~

Luồng logic của Spring có thể hình dung như sau:

~~~mermaid
sequenceDiagram
    participant UI as Browser ở app.example.com
    participant SEC as Spring Security HTTP
    participant HS as WebSocket Handshake
    participant MSG as Spring Messaging / STOMP
    participant APP as @MessageMapping / Service
    UI->>SEC: GET /ws + Upgrade + Origin + Cookie
    SEC->>SEC: Đọc session và xác thực Alice
    SEC->>HS: Request đã có Principal Alice
    HS->>HS: Kiểm tra Origin + tạo WebSocket session
    HS-->>UI: 101 Switching Protocols
    UI->>MSG: STOMP CONNECT + CSRF native header
    MSG->>MSG: Nhận principal Alice và kiểm tra CONNECT
    MSG-->>UI: CONNECTED nếu hợp lệ
    UI->>MSG: SEND /app/orders.lookup, orderId=1001
    MSG->>MSG: Kiểm tra quyền message theo destination
    MSG->>APP: Principal Alice + payload
    APP->>APP: Kiểm tra Alice có quyền với order 1001
    APP-->>UI: Gửi kết quả tới user destination của Alice
~~~

### 3.1. Từng chặng có trách nhiệm khác nhau

**Chặng A — HTTP request:** request `GET /ws` đi qua các HTTP filters của Spring Security. Nếu ứng dụng dùng session và cookie hợp lệ, Spring Security có thể xác thực user bằng session có sẵn. Nếu dùng bearer HTTP authentication, cơ chế xác thực token cũng phải chạy ở handshake.

**Chặng B — WebSocket handshake:** Spring WebSocket xử lý upgrade. `DefaultHandshakeHandler` thường sử dụng `Principal` có sẵn của request, thay vì lấy một username tự khai trong STOMP frame. Origin validation của endpoint cũng phải được áp dụng.

**Chặng C — WebSocket session:** principal gắn với session WebSocket. WebSocket có thể sống qua nhiều message mà không tái thực hiện HTTP authentication cho từng frame.

**Chặng D — STOMP CONNECT:** Spring Messaging chuyển frame thành message inbound. Với Spring Security WebSocket Messaging, CONNECT còn chịu cơ chế CSRF và authorization phù hợp; việc HTTP 101 thành công không đủ để kết luận CONNECT được phép.

**Chặng E — SEND/SUBSCRIBE:** message được kiểm tra quyền theo destination/type. Controller/service nhận principal server-side và tự thực hiện object/tenant authorization.

**Chặng F — phát dữ liệu:** application/broker phải gửi message tới đúng session/user/subscription, không vô tình phát dữ liệu cá nhân lên topic mà user khác có thể subscribe.

### 3.2. HTTP 101 không chứng minh STOMP đã authenticated

Một response:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <server-generated-value>
~~~

chỉ kết thúc bước nâng cấp giao thức WebSocket. Sau đó client còn phải nói STOMP đúng cách, chẳng hạn gửi `CONNECT`; nếu CSRF token hoặc quyền không hợp lệ, server có thể phản hồi STOMP `ERROR` hoặc đóng kết nối.

**Phân biệt ba kết quả:** “socket mở”, “STOMP CONNECTED” và “lệnh nghiệp vụ được xử lý thành công” là ba mốc khác nhau.

## 4. Cookie và authentication trong HTTP handshake

### 4.1. Một session cookie có thể đủ để nhận diện user

Sau khi đăng nhập thành công, server có thể phát:

~~~http
Set-Cookie: SESSION=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Khi browser kết nối `wss://api.example.com/ws`, cookie được gửi **nếu** phù hợp với Domain/Path, `Secure`, `SameSite` và các hạn chế riêng tư của browser.

- `HttpOnly` ngăn script lấy cookie qua `document.cookie`; nó **không ngăn** browser gửi cookie.
- `Secure` hỗ trợ giới hạn cookie vào kết nối bảo mật phù hợp.
- `SameSite=Lax` thường không ngăn request **same-site** phù hợp giữa hai subdomain HTTPS thuộc `example.com`.
- Nếu frontend và API nằm ở **cross-site** khác nhau, browser có thể chặn third-party cookies hoặc yêu cầu thuộc tính cookie phù hợp.
- `Origin` của handshake mô tả trang khởi tạo script, **không phải** một user ID.

Một cookie có thể được browser gửi mà frontend JavaScript **không đọc được**. Đây là hành vi mong muốn với session cookie `HttpOnly`.

### 4.2. Browser WebSocket constructor không có credentials option như Fetch

Với HTTP Fetch cross-origin:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Nhưng WebSocket constructor **không** nhận một object `credentials` hoặc `headers` tùy ý:

~~~javascript
// Không phải API WebSocket chuẩn trong browser:
new WebSocket("wss://api.example.com/ws", {
  credentials: "include",
  headers: {
    Authorization: "Bearer <access-token>"
  }
});
~~~

Browser quản lý cookie handshake theo policy của nó. Nếu không nhận được principal, đừng “sửa” bằng một WebSocket option không tồn tại; hãy kiểm tra cookie, HTTP auth, TLS, proxy và SecurityFilterChain.

### 4.3. Same-origin khác same-site

Trang `https://app.example.com` và API `https://api.example.com`:

- **Khác origin** vì host khác.
- Thường **same-site** vì cùng scheme HTTPS và registrable domain.
- Có thể chia sẻ browser-managed credentials theo cookie policy, nhưng **không** mặc nhiên cùng mức độ tin cậy.

Một trang không tin cậy tại `https://usercontent.example.com` cũng có thể cùng site. Vì vậy `SameSite=Lax` không thay thế **Origin allowlist ở WebSocket handshake**, CSRF CONNECT và object authorization.

### 4.4. Không đưa session ID vào URL để tránh cấu hình cookie

Phản ví dụ:

~~~javascript
// Không khuyến nghị:
new WebSocket(
  "wss://api.example.com/ws?sessionId=<sensitive-session-id>"
);
~~~

Token hoặc session ID trong query string dễ bị log ở reverse proxy, access logs, monitoring và hệ thống tracing. Nếu hệ thống sử dụng ticket ngắn hạn cho WebSocket, phải thiết kế phát hành, TTL, dùng một lần, binding và redaction logs rất chặt, không thay bằng session ID dài hạn.

## 5. Spring Security Servlet: yêu cầu authentication tại handshake

Giả sử ứng dụng dùng Spring MVC, Spring Security và session-based login. Một `SecurityFilterChain` đơn giản:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HttpHandshakeSecurityConfiguration {

    @Bean
    SecurityFilterChain httpSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/ws", "/ws/**").authenticated()
                .requestMatchers("/api/csrf").authenticated()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

### 5.1. Những gì rule này bảo đảm

- HTTP handshake tới `/ws` yêu cầu user được Spring Security xác thực.
- Nếu bật SockJS, matcher `/ws/**` giúp bao phủ những HTTP transport paths nằm dưới endpoint.
- API lấy CSRF token `/api/csrf` trong ví dụ cũng yêu cầu authenticated user.
- `formLogin` là một mô hình đăng nhập dựa trên phiên; một ứng dụng thật còn cần user store, login UI và cấu hình HTTP CORS cho REST endpoints khác origin.

### 5.2. Những gì rule này không bảo đảm

- `authenticated()` không tạo WebSocket origin allowlist.
- HTTP authorization không quyết định user được `SEND` hoặc `SUBSCRIBE` tới destination nào.
- Nó không làm CSRF token tự xuất hiện trong STOMP CONNECT.
- Nó không ngăn user hợp lệ truy vấn order của người khác.
- Nó không bảo đảm socket bị đóng tức thì khi user logout trên một HTTP request khác.

**HTTP authentication là bước đầu để có principal, không phải hệ thống phân quyền realtime hoàn chỉnh.**

### 5.3. Khi handshake không đi qua đúng SecurityFilterChain

Nếu có nhiều `SecurityFilterChain` dùng `securityMatcher`, cấu hình `@Order`, hoặc một gateway trả response trước Spring Security, request `GET /ws` có thể đi qua một policy khác dự kiến.

Hãy kiểm tra HTTP method/path **thực tế** của handshake và SockJS fallback; không chỉ xem tên endpoint trong code. Một cấu hình sai có thể tạo HTTP 101 từ một connection anonymous, dẫn đến `Principal` trong STOMP bị null.

## 6. Spring STOMP endpoint: giữ principal gắn với WebSocket session

Đăng ký endpoint dùng STOMP broker:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class RealtimeWebSocketConfiguration
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
~~~

### 6.1. DefaultHandshakeHandler sử dụng principal từ request

Trong mô hình mặc định, Spring WebSocket xác định user của WebSocket session từ `Principal` đã gắn với HTTP request. Vì vậy khi Spring Security xác thực Alice tại HTTP handshake, WebSocket session thường mang principal Alice.

Không cần gửi lại một trường `username:alice` trong mỗi frame để “truyền danh tính”. Làm vậy còn nguy hiểm nếu server tin dữ liệu do client tự khai.

Nếu cần tùy biến handshake, hãy phân biệt:

- **HandshakeInterceptor**: thường dùng để kiểm tra/đưa thêm attributes vào handshake; attributes không tự biến thành authenticated principal.
- **DefaultHandshakeHandler#determineUser(...)**: có thể được tùy biến để xác định principal, nhưng nên giữ nguồn danh tính được xác thực, không tin raw headers/query parameters.
- **ChannelInterceptor** trên STOMP inbound: có thể được dùng cho authentication tại CONNECT theo kiến trúc riêng.

**Không tùy tiện override principal từ request đã xác thực** khi không có lý do và kiểm chứng rõ ràng.

### 6.2. Có được coi Origin là principal không?

Không. `Origin: https://app.example.com` là nguồn trang chạy script trong browser. Một non-browser WebSocket client có thể giả Origin. Vì vậy Origin allowlist giúp chống CSWSH nhưng không chứng minh user nào đã đăng nhập, có quyền quản trị hay có quyền đọc tài nguyên.

### 6.3. Không tự cho phép mọi origin để “sửa lỗi identity null”

Nếu browser không gửi session cookie, việc thay:

~~~java
.setAllowedOrigins("https://app.example.com")
~~~

bằng:

~~~java
.setAllowedOrigins("*")
~~~

không làm principal tự xuất hiện. Nó còn tăng bề mặt tấn công CSWSH. Cần kiểm tra session, cookie và authentication path riêng.

## 7. Principal đi vào STOMP message controller như thế nào?

Sau handshake, Spring Messaging xử lý các inbound STOMP frames qua client inbound channel. Nếu WebSocket session có principal, messaging context cho phép handler lấy user đã được xác thực.

Ví dụ client gửi:

~~~text
SEND
destination:/app/orders.lookup
content-type:application/json

{"orderId":1001}
^@
~~~

Server nhận `Principal` như một tham số của `@MessageMapping`:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

record OrderLookup(long orderId) {}
record OrderView(long orderId, String state) {}

interface OrderService {
    // Implementation xác minh principal được xem order này.
    OrderView findVisibleOrder(String username, long orderId);
}

@Controller
class OrderRealtimeController {

    private final OrderService orders;
    private final SimpMessagingTemplate messaging;

    OrderRealtimeController(
        OrderService orders,
        SimpMessagingTemplate messaging
    ) {
        this.orders = orders;
        this.messaging = messaging;
    }

    @MessageMapping("/orders.lookup")
    void lookup(@Payload OrderLookup request, Principal principal) {
        // Principal lấy từ ngữ cảnh WebSocket/STOMP đã xác thực.
        String username = principal.getName();

        // Tầng service phải kiểm tra quyền theo orderId/tenant.
        OrderView order = orders.findVisibleOrder(
            username, request.orderId()
        );

        messaging.convertAndSendToUser(
            username,
            "/queue/order-results",
            order
        );
    }
}
~~~

### 7.1. Điều gì không được tin?

Không dùng:

~~~java
// Phản ví dụ: client có thể tự khai username bất kỳ.
@MessageMapping("/orders.lookup")
void lookup(OrderLookupWithUser request) {
    String username = request.username(); // Không đáng tin.
}
~~~

Client có thể thay payload, JSON fields hoặc native STOMP headers. **Principal** phải đến từ HTTP authentication hoặc token được kiểm chứng tại CONNECT; service dùng principal đó để kiểm tra quyền trên dữ liệu thật.

### 7.2. Role USER không giải quyết object ownership

Một Alice hợp lệ có thể cố gửi:

~~~json
{"orderId":2002}
~~~

trong khi order 2002 thuộc Bob. Dù Alice có role `USER` và được phép SEND tới `/app/orders.lookup`, service vẫn phải từ chối đọc dữ liệu Bob.

Ví dụ điều kiện nghiệp vụ:

~~~java
// Pseudocode phần implementation của OrderService:
Order order = repository.findById(orderId)
    .orElseThrow(NotFoundException::new);

if (!order.ownerUsername().equals(username)) {
    throw new AccessDeniedException("Forbidden");
}

return new OrderView(order.id(), order.state());
~~~

Đây là **object-level authorization (BOLA/IDOR prevention)**, không phải trách nhiệm của Origin allowlist hay CSRF token.

### 7.3. User destinations và convertAndSendToUser

Client của Alice có thể subscribe:

~~~text
SUBSCRIBE
id:my-orders
destination:/user/queue/order-results

^@
~~~

Server dùng:

~~~java
messaging.convertAndSendToUser(
    principal.getName(),
    "/queue/order-results",
    orderView
);
~~~

Spring sử dụng user destination mechanism để giải quyết routing theo principal/session. `SimpUserRegistry` có thể cung cấp thông tin về users và sessions được biết tới trong messaging infrastructure.

Tuy nhiên:

- User destinations không tự sửa một service trả dữ liệu trái quyền.
- Đừng phát dữ liệu user riêng vào `/topic/public`.
- Với nhiều WebSocket connections cùng username, user destination có thể liên quan đến nhiều sessions; cần hiểu semantics phát message của ứng dụng.
- Với nhiều server instances/external broker, cần cấu hình routing/user registry phù hợp và kiểm thử cluster, không chỉ kiểm thử single-node.
- Khi gửi dữ liệu riêng, nên xác định rõ gửi **toàn bộ connections của user** hay chỉ một session cụ thể.

## 8. Phân quyền inbound messages bằng Spring Security Messaging

Principal đã có là điều kiện cần, nhưng vẫn phải quyết định các STOMP destinations nào được phép sử dụng.

Ví dụ cấu hình deny-by-default:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
class StompAuthorizationConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        return messages
            .nullDestMatcher().authenticated()
            .simpSubscribeDestMatchers("/app/**").denyAll()
            .simpSubscribeDestMatchers(
                "/user/queue/order-results",
                "/topic/public"
            ).authenticated()
            .simpDestMatchers("/app/orders.lookup")
                .hasRole("USER")
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()
            .anyMessage().denyAll()
            .build();
    }
}
~~~

### 8.1. Đọc các matcher theo thứ tự

- `nullDestMatcher().authenticated()` yêu cầu principal cho những messages không có destination, ví dụ CONNECT khi đã được xác thực ở handshake.
- `simpSubscribeDestMatchers("/app/**").denyAll()` chặn client SUBSCRIBE application destinations.
- `simpSubscribeDestMatchers("/user/queue/order-results")` chỉ cho authenticated subscriptions vào user destination phù hợp.
- `simpDestMatchers("/app/orders.lookup").hasRole("USER")` chỉ cho SEND tới application command khi role phù hợp.
- `simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()` chặn các client MESSAGE/SUBSCRIBE còn lại.
- `anyMessage().denyAll()` tránh việc vô tình cho qua các loại message chưa được xét.

**Điểm bảo mật:** không cho client `SEND` thẳng tới broker destination như `/topic/**` nếu message đó phải được handler/service kiểm tra. Cũng không mở toàn bộ `/topic/orders/**` cho mọi authenticated user khi từng topic mang dữ liệu riêng theo order/tenant.

### 8.2. Inbound channel security không tự bảo vệ mọi outbound message

Spring Security Messaging bảo vệ messages **đi vào từ client**. Nếu application tự gửi dữ liệu cá nhân lên một public topic, một rule chặn SEND của client chưa giải quyết việc dữ liệu bị phát nhầm.

Do đó:

1. Kiểm tra quyền khi SUBSCRIBE vào private destinations.
2. Kiểm tra quyền và dữ liệu trong `@MessageMapping`/service.
3. Kiểm soát routing khi server phát message.
4. Xử lý quyền thay đổi sau khi subscription đã được tạo.

### 8.3. SecurityContext ở message handling

Trong Spring Security Messaging, principal của inbound message có thể được kết nối với security context phục vụ authorization trên message thread. Nhưng không nên giả định `SecurityContextHolder` của **HTTP request thread** vẫn còn nguyên trong một công việc bất đồng bộ tùy ý.

Ưu tiên:

- Nhận `Principal` hoặc `Authentication` hợp lệ trong handler khi framework hỗ trợ.
- Truyền danh tính/authorization context một cách tường minh xuống service.
- Với `@Async`, executor hoặc Reactor, dùng chiến lược truyền security context phù hợp stack, tránh các ThreadLocal cũ hoặc bị tái sử dụng sai.
- Không tạo một singleton lưu “current username” dùng chung cho mọi WebSocket sessions.

## 9. CSRF tại STOMP CONNECT và tính liên tục của session

Trong mô hình Spring Security WebSocket Messaging với `@EnableWebSocketSecurity`, inbound **STOMP CONNECT** cần CSRF token hợp lệ theo cơ chế bảo vệ mặc định tương ứng. Điều này giúp chống một site không tin cậy mở messaging session sử dụng credentials mà browser tự gửi.

### 9.1. Hai bước khác nhau

**Bước 1 — HTTP handshake:**

~~~http
GET /ws HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: SESSION=<alice-session>
Upgrade: websocket
Connection: Upgrade
~~~

Spring Security nhận diện Alice dựa vào cookie/session.

**Bước 2 — STOMP CONNECT:**

~~~text
CONNECT
accept-version:1.2
host:api.example.com
X-CSRF-TOKEN:<valid-token>

^@
~~~

Token trong CONNECT là **STOMP native header** nằm bên trong WebSocket frame, không phải HTTP request header của handshake. Việc có principal Alice ở handshake không có nghĩa CONNECT không cần CSRF.

### 9.2. Cấp token qua một HTTP endpoint được bảo vệ

Ví dụ một ứng dụng tự tạo endpoint lấy CSRF token để SPA dùng:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenController {

    @GetMapping("/api/csrf")
    ResponseEntity<Map<String, String>> token(
        @RequestAttribute("_csrf") CsrfToken csrfToken
    ) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", csrfToken.getHeaderName(),
                "token", csrfToken.getToken()
            ));
    }
}
~~~

Lưu ý:

- `/api/csrf` **không tự tồn tại** chỉ vì bật WebSocket; ví dụ phải được triển khai trong ứng dụng.
- Nếu frontend khác origin, HTTP API cấp token cần có **CORS allowlist độc lập** chỉ cho frontend tin cậy; cấu hình WebSocket `setAllowedOrigins(...)` không tự cấp CORS cho GET này.
- Token phải lấy từ **đúng session/ngữ cảnh** sẽ dùng cho WebSocket.
- Spring Security có thể dùng deferred hoặc masked CSRF tokens. Cách phát/đọc token phải phù hợp `CsrfTokenRepository` và `CsrfTokenRequestHandler` thực tế.
- Không ghi CSRF token/session ID vào logs hoặc để CDN cache dùng chung.

### 9.3. Client STOMP gửi token đúng chỗ

Ví dụ frontend dùng `@stomp/stompjs`:

~~~javascript
import { Client } from "@stomp/stompjs";

async function connectRealtime() {
  const res = await fetch(
    "https://api.example.com/api/csrf",
    { credentials: "include" }
  );

  if (!res.ok) {
    throw new Error("Không nhận được CSRF token");
  }

  const { headerName, token } = await res.json();

  const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    connectHeaders: {
      [headerName]: token
    },
    reconnectDelay: 3000,

    onConnect: () => {
      client.subscribe(
        "/user/queue/order-results",
        frame => console.log(JSON.parse(frame.body))
      );

      client.publish({
        destination: "/app/orders.lookup",
        body: JSON.stringify({ orderId: 1001 })
      });
    },

    onStompError: frame => {
      console.error("STOMP ERROR:", frame.headers.message);
    }
  });

  client.activate();
  return client;
}
~~~

**`connectHeaders` không thêm HTTP headers vào WebSocket handshake.** Nó tạo các native STOMP headers trong CONNECT frame. Browser vẫn tự xử lý Cookie trên handshake.

Trong ứng dụng thật còn phải xử lý reconnect sau token rotation, logout/session expiry và lỗi nhận CSRF token, không tái sử dụng token cũ vô hạn.

### 9.4. Không tắt toàn bộ CSRF để “làm WebSocket chạy”

Nếu handshake 101 nhưng CONNECT bị từ chối, hãy kiểm tra token, principal, repository và thứ tự interceptors. Việc tắt HTTP CSRF cho mọi POST/PUT không phải cách đúng để sửa STOMP CONNECT.

Nếu ứng dụng dùng **SockJS XHR fallback**, một số transport dùng HTTP POST và có thể cần chính sách HTTP CSRF transport riêng. Nếu phải tạo exception, chỉ giới hạn đúng transport paths và **giữ bảo vệ STOMP CONNECT cùng các API nghiệp vụ**.

## 10. Khi không có principal ở HTTP handshake

Không phải mọi hệ thống đều dùng session login. Nhiều SPA chỉ có bearer token trong bộ nhớ JavaScript, không có session cookie.

Browser không cho JavaScript tùy ý thêm HTTP `Authorization` header trong WebSocket constructor:

~~~javascript
// Không phải API WebSocket browser chuẩn:
new WebSocket("wss://api.example.com/ws", {
  headers: { Authorization: "Bearer <token>" }
});
~~~

Nếu token chỉ được gửi qua STOMP `CONNECT` thì HTTP handshake **chưa có credential để xác thực**.

### 10.1. Hai mô hình cần chọn rõ

| Mô hình | Danh tính đến từ đâu? | Điểm cần kiểm soát |
| --- | --- | --- |
| **Kế thừa HTTP** | Spring Security xác thực session/token ngay tại handshake | HTTP `/ws` yêu cầu authenticated; principal tự được dùng trong messaging |
| **Xác thực tại STOMP CONNECT** | Client gửi bearer token trong native CONNECT header; interceptor kiểm chứng và gắn principal | HTTP handshake policy có thể phải cho qua một phạm vi hẹp trước auth; CONNECT phải bị từ chối nếu token không hợp lệ, trước khi xử lý SEND/SUBSCRIBE |
| **Vé kết nối riêng** | Server cấp short-lived/one-time ticket theo luồng đã xác thực | TTL, binding, log redaction, replay prevention, verification trước cấp quyền realtime |

**Không được trộn vô thức:** nếu HTTP `SecurityFilterChain` yêu cầu `/ws` authenticated mà client chỉ gửi token ở STOMP CONNECT, connection sẽ bị chặn **trước khi token đến**. Ngược lại, nếu mở anonymous handshake để chờ CONNECT, phải đảm bảo không có message/subscription nhạy cảm nào được chấp nhận trước khi token được xác minh.

### 10.2. Một ChannelInterceptor xác thực CONNECT cần làm gì?

Nếu ứng dụng thật sự chọn bearer-token CONNECT, interceptor phải:

1. Chỉ xử lý inbound `CONNECT` đúng message type.
2. Trích xuất native header chứa token mà không log token.
3. Xác minh chữ ký hoặc kiểm tra token tại trusted issuer/introspection, audience, expiry, revocation và scopes.
4. Tạo một `Authentication` hợp lệ từ kết quả xác minh.
5. Gắn principal bằng cơ chế tương thích messaging, ví dụ `StompHeaderAccessor#setUser(authentication)`.
6. Đăng ký interceptor **trước** Spring Security message authorization và CONNECT processing liên quan.
7. Chặn CONNECT thiếu/sai token bằng lỗi phù hợp.
8. Xác định rõ cách hết hạn/thu hồi token trên connection lâu dài.

Pseudo-code mô tả phần lõi, **không phải bản triển khai để copy vào production**:

~~~java
// PSEUDOCODE: tokenVerifier cần do ứng dụng triển khai an toàn.
Message<?> preSend(Message<?> message, MessageChannel channel) {
    StompHeaderAccessor accessor =
        MessageHeaderAccessor.getAccessor(
            message, StompHeaderAccessor.class
        );

    if (accessor != null &&
            StompCommand.CONNECT.equals(accessor.getCommand())) {
        String raw = accessor.getFirstNativeHeader("Authorization");

        Authentication authenticated =
            tokenVerifier.verifyAndAuthenticate(raw);

        accessor.setUser(authenticated);
    }

    return message;
}
~~~

Để biến thành Java chạy được, cần import các lớp Messaging/Security, triển khai `tokenVerifier`, xác định error handling và đăng ký `ChannelInterceptor` thông qua `configureClientInboundChannel` của `WebSocketMessageBrokerConfigurer` với thứ tự phù hợp. Không chấp nhận `login:admin`, `userId` hoặc raw token mà chưa xác minh.

### 10.3. Sự kế thừa HTTP không “thất bại” nếu kiến trúc cố ý xác thực ở CONNECT

Ở mô hình token-only, việc handshake không mang principal là **một quyết định kiến trúc**, không phải bằng chứng Spring WebSocket bị lỗi. Điều quan trọng là:

- Message layer bắt buộc xác thực trước khi cấp quyền.
- Kết nối chưa authenticated không được đọc/gửi dữ liệu.
- Spring Security Messaging phải nhìn thấy `Authentication` đã được kiểm tra.
- Non-browser client giả Origin không thể vượt qua bước xác thực.

## 11. Logout, đổi role và session WebSocket dài hạn

Đây là phần rất dễ bị hiểu sai khi nói “kế thừa danh tính”.

### 11.1. Principal được gắn lúc thiết lập kết nối

Giả sử Alice mở WebSocket lúc 09:00. Đến 10:00, admin thu hồi role của Alice hoặc Alice logout HTTP. WebSocket có thể vẫn đang mở và mang principal ban đầu.

Không được mặc định rằng mọi thay đổi ở HTTP session sẽ:

- Tự đóng WebSocket tức thì.
- Tự cập nhật authorities trong principal đang gắn với connection.
- Tự thu hồi mọi subscription đã tạo.
- Tự kiểm tra lại quyền trước mỗi outbound MESSAGE.

### 11.2. Cần chiến lược thu hồi

Tùy mức độ nhạy cảm, hệ thống có thể:

1. Khi logout/session invalidation, chủ động đóng WebSocket sessions tương ứng nếu infrastructure hỗ trợ.
2. Khi quyền phòng/tenant thay đổi, hủy subscription hoặc từ chối những message mới.
3. Kiểm tra authorization với **quyền hiện tại** ở service trước mỗi hành động nghiệp vụ quan trọng.
4. Kiểm tra quyền ngay trước khi server phát dữ liệu nhạy cảm, không chỉ lúc SUBSCRIBE.
5. Giới hạn tuổi connection, thời gian không hoạt động và token TTL.
6. Buộc reconnect/reauthenticate khi phiên hoặc token hết hiệu lực.
7. Xử lý multiple sessions của cùng username và cluster node phù hợp.

Spring Session có các khả năng tích hợp với WebSocket trong một số cấu hình, nhưng không nên tuyên bố mọi ứng dụng Spring Security tự đóng socket khi session HTTP hết hạn. Phải cấu hình và test theo kiến trúc thật.

### 11.3. Login lại không tự đổi principal của connection cũ

Nếu browser kết nối WebSocket khi chưa login (trong hệ thống có cho anonymous handshake), rồi user login qua HTTP ở một tab khác, connection cũ **không tự biến thành kết nối authenticated**. Tùy mô hình, cần đóng và mở kết nối mới hoặc một giao thức reauthentication được thiết kế rõ ràng.

Cũng không nên tái sử dụng một `SecurityContext` cũ trong background executor sau khi quyền đã bị thu hồi.

## 12. SockJS fallback: nhiều HTTP requests nhưng cùng mục tiêu identity

Khi bật:

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins("https://app.example.com")
    .withSockJS();
~~~

SockJS có thể dùng WebSocket hoặc HTTP fallback như XHR streaming/polling. Các đường dẫn có thể gồm:

~~~text
GET  /ws/info
GET  /ws/<server-id>/<session-id>/websocket
POST /ws/<server-id>/<session-id>/xhr_send
GET  /ws/<server-id>/<session-id>/xhr_streaming
...
~~~

Điểm khác native WebSocket: fallback có thể gồm **nhiều HTTP requests**, nên cookies, CORS, CSRF HTTP và authentication của từng transport request có thể ảnh hưởng.

### 12.1. Những nguy cơ đối với identity continuity

- Cookie không được browser gửi trên XHR fallback dù native WebSocket vẫn hoạt động.
- Một gateway yêu cầu auth trên `/ws/info` hoặc POST transport theo cách khác `/ws`.
- Load balancer điều phối request của cùng SockJS session tới nhiều nodes không chia sẻ trạng thái phù hợp.
- Một custom HTTP filter tạo principal khác nhau giữa các transport paths.
- Logout/session invalidation xảy ra khi transport đang hoạt động.
- HTTP CORS processor ở gateway chặn preflight của SockJS trước khi Spring nhận request.

Vì vậy phải test cả **transport path thực tế** và principal trong message handler, không chỉ HTTP 101 trên native WebSocket.

### 12.2. CORS/XHR không phải authentication

SockJS HTTP fallback có thể cần `Access-Control-Allow-Origin` và `Access-Control-Allow-Credentials` hợp lệ để browser sử dụng XHR. Nhưng việc ACAO đúng **không chứng minh** request có authenticated principal. Cookie policy, HTTP Security và message authorization vẫn là các lớp độc lập.

### 12.3. Nếu cần ngoại lệ HTTP CSRF cho SockJS

Một số SockJS HTTP transports dùng POST. Nếu Spring Security CSRF HTTP bảo vệ POST đó và gây xung đột, phải chỉ tạo ngoại lệ cho **đúng SockJS transport URLs** khi được chứng minh cần thiết. Không tắt toàn bộ HTTP CSRF chỉ để client kết nối được. STOMP CONNECT vẫn cần CSRF tương ứng và mọi message vẫn cần authorization.

## 13. WebFlux native WebSocket: principal từ Reactive handshake

Spring WebFlux có `WebSocketHandler`, `WebSocketSession` và `HandshakeInfo`. Đây là mô hình **native WebSocket**; nó không mặc định sử dụng STOMP broker, `@EnableWebSocketMessageBroker` và `@EnableWebSocketSecurity` như ví dụ Servlet.

### 13.1. ServerHttpSecurity bảo vệ HTTP handshake

Ví dụ yêu cầu authentication cho route:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveHandshakeSecurityConfiguration {

    @Bean
    SecurityWebFilterChain webSecurityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/ws").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Ứng dụng phải cấu hình authentication mechanism phù hợp (ví dụ session login) và handler mapping/adapter cho `/ws`. Rule trên **không tự xác minh origin** hoặc message-level permissions.

### 13.2. Nhận principal trong WebSocketHandler

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface ReactiveOrderCommands {
    // Parse, validate và kiểm tra quyền theo principal/object.
    Mono<Void> validateAuthorizeAndHandle(
        Principal principal,
        String messageText
    );
}

class AuthorizedReactiveWebSocketHandler {

    static WebSocketHandler create(ReactiveOrderCommands commands) {
        return session -> session.getHandshakeInfo()
            .getPrincipal()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Login required")))
            .flatMap(principal ->
                session.receive()
                    .concatMap(message ->
                        commands.validateAuthorizeAndHandle(
                            principal, message.getPayloadAsText()
                        ))
                    .then()
            );
    }
}
~~~

`session.getHandshakeInfo().getPrincipal()` trả về principal của handshake trong mô hình WebFlux phù hợp. Không dùng một `ThreadLocal` Servlet để suy ra danh tính trong Reactive pipeline.

Đây là **khung minh họa** chưa gồm `HandlerMapping`, `WebSocketHandlerAdapter`, response `session.send(...)`, backpressure và giới hạn payload. `ReactiveOrderCommands` phải kiểm tra quyền từng message, không chỉ dựa vào authenticated principal.

### 13.3. Origin validation vẫn là cơ chế độc lập

Một WebFlux endpoint native nên kiểm tra Origin handshake qua cơ chế phù hợp của stack, ví dụ một WebFilter cho route riêng, và thực thi HTTP authentication.

~~~java
// Policy minh họa, không phải authentication:
boolean acceptedOrigin =
    "https://app.example.com".equals(origin);
~~~

Nếu có user-controlled subdomain hoặc client không phải browser, hãy thiết kế trust boundary thích hợp; đừng phản chiếu Origin tùy ý, và đừng coi Origin hợp lệ đồng nghĩa principal tồn tại.

### 13.4. Reactive security context không phải Servlet ThreadLocal

Với Reactor, security context được truyền qua reactive context theo cơ chế Spring Security Reactive, không nên dựa vào `SecurityContextHolder` của thread HTTP Servlet. Khi thiết kế handler, nhận principal qua `HandshakeInfo` và truyền vào service là một cách trực quan, giúp tránh nhầm principal giữa requests và threads.

## 14. Ma trận kiểm thử việc kế thừa danh tính

Một bộ test tốt cần chứng minh **đúng principal xuất hiện** và **principal không bị client thay thế**, đồng thời kiểm tra authorization độc lập.

| Mã | Tình huống | Kỳ vọng |
| --- | --- | --- |
| H1 | User Alice đăng nhập HTTP, handshake cùng cookie hợp lệ | Socket được mở; principal của connection là Alice |
| H2 | Anonymous handshake khi `/ws` yêu cầu auth | Bị từ chối HTTP (401/redirect tùy entry point) |
| H3 | Cookie hết hạn/không hợp lệ | Không có authenticated principal; handshake bị từ chối nếu yêu cầu |
| H4 | Origin lạ, cookie Alice hợp lệ | Bị WebSocket Origin policy từ chối |
| H5 | Origin app nhưng non-browser client không có auth | Không được dùng Origin để bypass HTTP authentication |
| C1 | Handshake Alice, CONNECT có CSRF đúng | CONNECTED theo policy |
| C2 | Handshake Alice, CONNECT thiếu/sai CSRF token | CONNECT bị từ chối khi protection bật |
| M1 | Alice gửi SEND hợp lệ tới `/app/orders.lookup` | `@MessageMapping Principal#getName()` là Alice |
| M2 | Alice gửi `username:bob` trong payload/STOMP header | Principal vẫn là Alice, không được xem order của Bob |
| M3 | Alice SEND tới broker `/topic/**` trực tiếp | Bị inbound message authorization từ chối |
| M4 | Alice SUBSCRIBE private destination của Bob | Bị subscription/object ACL từ chối |
| M5 | Alice hỏi order 2002 của Bob dù role USER | Bị service ownership check từ chối |
| L1 | Alice logout HTTP, connection cũ còn mở | Thu hồi/đóng hoặc revalidate quyền theo chính sách, không phát dữ liệu trái quyền |
| L2 | Role của Alice bị thu hồi | Quyền mới có hiệu lực với hành động/phát dữ liệu nhạy cảm |
| L3 | Login mới ở tab khác khi socket cũ anonymous | Socket cũ không tự kế thừa principal mới |
| S1 | SockJS XHR fallback với session hợp lệ | Messaging principal đúng như HTTP identity; CORS/CSRF HTTP xử lý đúng |
| R1 | WebFlux WebSocket authenticated | `HandshakeInfo#getPrincipal()` cung cấp principal phù hợp |
| R2 | WebFlux message chứa userId giả | Handler/service vẫn dùng principal server-side |

### 14.1. Test cần kiểm tra dữ liệu, không chỉ status

Một test SEND tới order của Bob cần khẳng định:

1. Server không trả private order data cho Alice.
2. Không có thông điệp được phát nhầm đến topic/session của Alice.
3. Không có side effect làm sửa dữ liệu Bob.
4. Audit/log nhận diện đúng principal Alice và request bị từ chối.

Chỉ nhận STOMP `ERROR` nhưng vẫn đã phát dữ liệu ra broker là một thất bại bảo mật.

## 15. Kiểm thử tích hợp Servlet: handshake và STOMP frames

### 15.1. MockMvc không thay thế WebSocketStompClient

`MockMvc` có thể giúp test HTTP login, HTTP SecurityFilterChain và endpoint cấp CSRF token. Nhưng nó không mô phỏng đầy đủ WebSocket handshake upgrade cùng STOMP CONNECT/SEND/SUBSCRIBE.

Để kiểm thử kế thừa identity end-to-end, dùng ứng dụng chạy trên test port với client như `WebSocketStompClient` + `StandardWebSocketClient`, truyền session cookie trong handshake và CSRF token trong STOMP CONNECT.

Ví dụ phần khởi tạo request test minh họa:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.messaging.WebSocketStompClient;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.messaging.simp.stomp.StompHeaders;

// Pseudocode minh họa dữ liệu đầu vào test:
// sessionCookie và csrfToken phải được cấp từ cùng phiên test.
WebSocketStompClient client = new WebSocketStompClient(
    new StandardWebSocketClient()
);

WebSocketHttpHeaders handshakeHeaders = new WebSocketHttpHeaders();
handshakeHeaders.setOrigin("https://app.example.com");
handshakeHeaders.add(HttpHeaders.COOKIE, "SESSION=" + sessionCookie);

StompHeaders connectHeaders = new StompHeaders();
connectHeaders.add("X-CSRF-TOKEN", csrfToken);

// connectAsync(uri, handshakeHeaders, connectHeaders, handler)
// rồi chờ CONNECTED/ERROR, xác minh Principal trong @MessageMapping.
~~~

Đoạn code trên là **skeleton tích hợp**, không phải một test có thể chạy ngay: cần tạo server thật, handler STOMP, session/token hợp lệ, timeout và assertions. Khi test trên nhiều framework versions, phương thức connect/cấu hình client có thể khác.

### 15.2. Trình tự test có ý nghĩa

~~~text
Given: user alice đăng nhập ở HTTP, có session cookie và CSRF token.
When:
  1) Mở WebSocket với Origin app và Cookie phiên Alice.
  2) STOMP CONNECT với CSRF token tương ứng.
  3) Client SEND tới /app/orders.lookup với orderId của Alice.
Then:
  - HTTP handshake thành công.
  - STOMP CONNECTED.
  - Handler nhìn thấy Principal alice.
  - Result được route đúng tới user destination Alice.

Negative:
  4) Cùng handshake Alice nhưng client khai username=bob.
     -> Principal không đổi; không đọc được data Bob.
  5) Handshake không Cookie.
     -> Bị HTTP authentication chặn.
  6) Cookie hợp lệ nhưng Origin bị từ chối.
     -> Bị handshake origin policy chặn.
  7) CONNECT sai CSRF.
     -> Không CONNECTED.
  8) SUBSCRIBE/SEND trái destination/role.
     -> Bị message authorization chặn.
~~~

Quan trọng: test Origin negative **với phiên hợp lệ** nếu cần chứng minh Origin validator thật sự hoạt động. Một 401 vì không có cookie chưa chứng minh origin không được phép.

### 15.3. Xác minh principal không bị giả mạo

Trong môi trường test, một handler có thể xuất username từ principal của message để so với HTTP user đã login. Tránh xuất principal đầy đủ hoặc dữ liệu nhạy cảm ra public topic; chỉ dùng test destination riêng, hoặc assertions bên trong integration test.

Kiểm tra rằng `SimpMessagingTemplate` không gửi dữ liệu Bob khi Alice cố thay userId trong frame, và không tin STOMP `login`/`passcode` làm role ứng dụng.

## 16. Kiểm thử bằng browser và DevTools

### 16.1. Chuẩn bị đúng nguồn của cookie và CSRF token

Ở frontend `https://app.example.com`, login API bằng cơ chế session hợp lệ, sau đó lấy CSRF token từ endpoint HTTP tin cậy và kết nối STOMP như mục 9.3.

Với browser Developer Tools:

1. Mở tab **Network**, tìm `/api/csrf` và request WebSocket `/ws`.
2. Xác minh HTTP API cấp token chỉ cho Origin tin cậy (CORS riêng).
3. Xác minh request handshake có `Origin: https://app.example.com`.
4. Kiểm tra Cookie có được đính kèm không; nếu vắng, xem SameSite/Secure/Domain/Path và privacy restrictions.
5. Xem response handshake là `101` hay 401/403.
6. Sau 101, xem STOMP `CONNECT` và `CONNECTED`/`ERROR` trong tab Frames/Messages.
7. Kiểm tra native STOMP CSRF header có đúng không (tránh lưu token vào log chia sẻ).
8. Gửi thử SEND/SUBSCRIBE đúng và sai quyền, quan sát kết quả.
9. Đăng xuất rồi thử lại connection mới và connection cũ theo chính sách thu hồi.

### 16.2. Dùng hai tài khoản thử nghiệm

Tạo Alice và Bob với order riêng:

| Test | Kỳ vọng |
| --- | --- |
| Login Alice, socket Alice, gửi order của Alice | Thành công khi đủ role và token |
| Login Bob, socket Bob, gửi order của Bob | Thành công |
| Socket Alice, payload tự khai Bob | Server vẫn nhận principal Alice |
| Socket Alice, request order của Bob | Từ chối |
| Socket Bob, SUBSCRIBE destination riêng của Alice | Từ chối hoặc không nhận data |
| Logout Alice, giữ socket cũ | Thu hồi/đóng/revalidate theo policy; không tiếp tục phát data riêng trái quyền |

Không dùng session/dữ liệu thật của người dùng sản xuất hoặc copy cookie/token vào báo cáo công khai.

### 16.3. Curl và non-browser clients

Một HTTP client có thể tự đặt `Origin` trong WebSocket handshake, nên không dùng Origin làm identity. Ví dụ quan sát một phần HTTP handshake:

~~~bash
curl -i --http1.1 "https://api.example.com/ws" \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Origin: https://app.example.com"
~~~

Lệnh này **không** thực hiện STOMP CONNECT và cũng không có session cookie. Nếu HTTP Security trả 401/redirect, đó là kết quả authentication, không phải phép thử STOMP. Dùng client WebSocket/STOMP hoàn chỉnh để xác minh việc principal được kế thừa.

## 17. Chẩn đoán sự cố principal và quyền

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Handshake HTTP 401/302 khi frontend đã login | Cookie không được gửi, session store khác, auth chain sai | DevTools Cookie, session, SecurityFilterChain |
| Handshake 101 nhưng `Principal` null | HTTP handshake anonymous, custom handler làm mất identity, xác thực token chỉ ở CONNECT | Xem HTTP user principal và handshake handler |
| Browser gửi cookie nhưng server vẫn anonymous | Session không hợp lệ, cookie sai host/path, proxy/backend dùng session store khác | Tracing phiên theo cách không lộ ID, Spring Session/config |
| Handshake 403 khi Origin app | Origin allowlist thiếu app hoặc proxy sửa Origin | Kiểm tra WebSocket endpoint policy và Origin thực |
| STOMP CONNECT bị từ chối dù HTTP 101 | CSRF CONNECT thiếu/sai, principal không hợp lệ, interceptor thứ tự sai | Xem native CONNECT headers, security logs |
| STOMP `login:admin` không cấp role | Đây không phải Spring Security authentication mặc định | Dùng HTTP principal hoặc CONNECT auth interceptor xác thực thật |
| Cookie SameSite làm app cross-site không vào | Browser cookie policy hạn chế | Kiểm tra SameSite/Secure/third-party restrictions |
| `@MessageMapping Principal` đúng nhưng lấy được order user khác | Thiếu object-level ACL | Kiểm tra service với principal và orderId |
| Inbound SEND tới `/topic/private` được broker phát | MESSAGE rule quá rộng | Deny broker destinations cho client |
| User destination gửi nhầm session/user | Routing theo username/session hoặc cluster config sai | Kiểm tra SimpUserRegistry, destinations và server nodes |
| Logout nhưng socket còn hoạt động | Session WebSocket dài hạn chưa bị thu hồi | Đóng/revalidate connection/subscriptions |
| Role bị thu hồi nhưng old socket vẫn dùng role cũ | Principal/authorities gắn từ handshake chưa được làm mới | Kiểm tra quyền hiện tại ở service, reconnect/close |
| Async handler báo sai principal | SecurityContext ThreadLocal không được truyền đúng | Dùng Principal rõ ràng, cấu hình executor context an toàn |
| SockJS native tốt, XHR fallback lỗi 401/403 | Nhiều HTTP requests, CORS/CSRF/session path khác | Kiểm tra /ws/info, xhr transport, proxy và CSRF policy |
| Backend A xác thực được, backend B không | Session không chia sẻ hoặc affinity không phù hợp | Spring Session/shared store, LB routing |
| WebFlux `HandshakeInfo.getPrincipal()` rỗng | Handshake chưa có auth hoặc security filter không chạy | Kiểm tra ServerHttpSecurity và principal |
| WebFlux sau `@Async` hoặc subscribe khác thread mất auth | Reactor Context bị xử lý sai | Truyền principal/context an toàn theo pipeline |
| Một HTTP request login thành công nhưng socket cũ vẫn anonymous | WebSocket không tự nâng danh tính sau login | Reconnect hoặc giao thức reauthentication riêng |
| CORS REST đúng nhưng WebSocket origin lạ kết nối | REST CORS không kiểm soát native WebSocket | Origin validation tại handshake |
| Browser CSP chặn socket trước HTTP | `connect-src` thiếu `wss://` endpoint | Điều chỉnh CSP hẹp, giữ server security |

### 17.1. Chẩn đoán theo từng mốc

~~~text
Mốc 1: Không có 101
  -> TLS/CSP/Origin/proxy/HTTP auth và Cookie.

Mốc 2: Có 101, không CONNECTED
  -> Principal, CSRF native STOMP CONNECT, interceptor order.

Mốc 3: CONNECTED, SEND/SUBSCRIBE bị chặn
  -> Role/message destination authorization.

Mốc 4: SEND/SUBSCRIBE được phép nhưng sai dữ liệu
  -> Object/tenant ACL, user destinations, broker routing.

Mốc 5: Sau logout/thu hồi quyền vẫn nhận dữ liệu
  -> Connection lifecycle và revalidation/revocation.
~~~

Không sửa lỗi ở một tầng bằng cách mở wildcard hoặc tắt CSRF/authorization ở tầng khác.

## 18. Checklist production

- [ ] HTTP `/ws` và các paths SockJS cần thiết đi qua đúng Spring Security HTTP chains.
- [ ] Mô hình authentication đã được quyết định rõ: **HTTP handshake principal** hay **STOMP CONNECT token**.
- [ ] Với mô hình HTTP inheritance, Cookie/token có thể được xác thực trong handshake.
- [ ] `DefaultHandshakeHandler`/WebSocket session giữ principal từ authenticated HTTP request; không lấy raw username từ client.
- [ ] Origin allowlist WebSocket/SockJS chỉ cho những frontend tin cậy; không đồng nhất với REST CORS.
- [ ] Cookie có `Secure`, `HttpOnly`, `SameSite`, Domain/Path đúng mô hình, không lộ session trong URL/log.
- [ ] CSRF native STOMP CONNECT được kiểm tra theo Spring Security Messaging và session phù hợp.
- [ ] Nếu tự xác thực token tại CONNECT, interceptor được đăng ký đúng thứ tự và không tin raw token trước kiểm chứng.
- [ ] Inbound SEND/SUBSCRIBE được phân quyền deny by default, không cho client publish trực tiếp protected broker destinations.
- [ ] `@MessageMapping` nhận server-side `Principal` và không tin userId/role trong payload.
- [ ] Service kiểm tra object/tenant ACL trước khi trả hoặc phát dữ liệu.
- [ ] `convertAndSendToUser` và user destinations được kiểm tra với nhiều WebSocket sessions/nodes.
- [ ] Logout, session expiry, token expiry, role revocation có cơ chế đóng/revalidate connection/subscription.
- [ ] Các tác vụ async/Reactive không phụ thuộc ThreadLocal request đã kết thúc; principal được truyền an toàn.
- [ ] SockJS fallback được kiểm thử riêng cho cookies, CORS, HTTP CSRF và affinity/session.
- [ ] CSP `connect-src`, TLS/WSS, HSTS, HTTP firewall và security headers được kiểm tra độc lập.
- [ ] Có giới hạn message size, send rate, subscriptions, idle time, heartbeat và connection count.
- [ ] Có kiểm thử end-to-end với Alice/Bob để chứng minh không có BOLA/IDOR hay rò rỉ message.
- [ ] Logs không chứa session ID, CSRF token, bearer token hoặc dữ liệu cá nhân không cần thiết.

## 19. Câu hỏi vận dụng và đáp án

**Tình huống 1 — Alice đăng nhập HTTP.** Khi Alice mở `wss://api.example.com/ws` và browser gửi cookie phiên, Spring lấy user cho WebSocket từ đâu?

**Đáp án:** Spring Security xác thực HTTP handshake thành principal Alice. Spring WebSocket thường dùng principal của HTTP request để gắn cho WebSocket session; Spring Messaging có thể đưa principal đó vào STOMP handler.

**Tình huống 2 — HTTP 101.** Browser nhận `101 Switching Protocols`. Có chắc STOMP CONNECT và SEND được phép chưa?

**Đáp án:** Chưa. 101 chỉ xác nhận transport; CONNECT còn có CSRF/security, SEND/SUBSCRIBE có authorization riêng.

**Tình huống 3 — Client khai user Bob.** Alice đã login HTTP nhưng gửi frame chứa `username:bob`. `@MessageMapping` nên dùng giá trị nào?

**Đáp án:** Dùng server-side `Principal` đã xác thực là Alice; không tin giá trị Bob từ client.

**Tình huống 4 — Role USER nhưng đọc order Bob.** Alice có role USER, CSRF CONNECT đúng, SEND tới endpoint được phép, và yêu cầu order 2002 của Bob. Điều gì phải chặn?

**Đáp án:** Service/business object-level authorization phải kiểm tra Alice không sở hữu/không có quyền order 2002 và từ chối trả dữ liệu.

**Tình huống 5 — Bearer chỉ ở CONNECT.** HTTP `/ws` yêu cầu authenticated nhưng browser không thể thêm arbitrary Authorization header, nên handshake 401. Có phải framework lỗi?

**Đáp án:** Không. Mô hình xác thực chưa nhất quán. Có thể dùng HTTP session hoặc thiết kế handshake giới hạn kết hợp CONNECT authentication interceptor kiểm chứng token thật trước message authorization.

**Tình huống 6 — Login header.** STOMP client gửi `login:admin`, `passcode:123`. Có trở thành Spring Security ADMIN không?

**Đáp án:** Không mặc định. Client-declared STOMP headers không phải principal ứng dụng; server phải xác minh authentication riêng.

**Tình huống 7 — CSRF CONNECT.** Handshake với session Alice thành công nhưng STOMP CONNECT thiếu `X-CSRF-TOKEN` bị từ chối. Có nên tắt HTTP CSRF toàn ứng dụng?

**Đáp án:** Không. CONNECT có lớp CSRF riêng. Cần lấy token phù hợp và gửi ở native STOMP CONNECT header; không nới HTTP POST protections một cách tổng quát.

**Tình huống 8 — Logout.** Alice logout HTTP nhưng WebSocket vẫn mở và tiếp tục nhận thông báo. Origin allowlist có sửa được không?

**Đáp án:** Không. Phải thiết kế đóng/revalidate connection, hủy subscription và kiểm tra quyền lúc phát. Origin không quản lý session lifetime.

**Tình huống 9 — User destination.** Server dùng `convertAndSendToUser("alice", "/queue/order-results", ...)`. Có tự đảm bảo payload đúng order của Alice không?

**Đáp án:** Không. Nó giúp routing theo username/session; service vẫn phải kiểm tra quyền đối với order trước khi gửi.

**Tình huống 10 — Same-site.** Frontend app và API khác subdomain nhưng cùng site. Cookie `SameSite=Lax` có nghĩa mọi subdomain đều được tin cậy không?

**Đáp án:** Không. Same-site không đồng nghĩa same-origin hoặc cùng quyền. Vẫn cần WebSocket Origin allowlist, CSRF CONNECT và authorization.

**Tình huống 11 — Async worker.** Một `@MessageMapping` khởi tạo công việc ở executor khác rồi đọc `SecurityContextHolder`, nhưng không thấy Alice. Có nên lấy username từ payload thay không?

**Đáp án:** Không. Cần truyền principal/security context an toàn theo cơ chế executor/Reactive phù hợp, không tin user ID do client gửi.

**Tình huống 12 — SockJS XHR.** Native WebSocket có principal Alice, nhưng SockJS XHR fallback không authenticated. Kiểm tra gì?

**Đáp án:** Kiểm tra cookies trên từng HTTP transport request, SameSite/CORS, SecurityFilterChain path, CSRF HTTP, session store và load balancer affinity.

**Tình huống 13 — WebFlux.** Handler WebFlux nhận một WebSocket connection qua HTTP authentication. Lấy principal bằng cách nào?

**Đáp án:** Dùng `WebSocketSession.getHandshakeInfo().getPrincipal()` và truyền principal vào handler/service để authorize từng message, không dựa vào Servlet ThreadLocal.

**Tình huống 14 — Principal bị đổi khi có CONNECT.** Một custom ChannelInterceptor gọi `setUser(...)` bằng raw username chưa được xác minh. Rủi ro?

**Đáp án:** Kẻ tấn công có thể giả mạo danh tính; chỉ gắn `Authentication` sau khi xác minh token/credential thực và đăng ký interceptor đúng thứ tự với message security.

**Tình huống 15 — Role bị thu hồi.** Khi role ADMIN của một người bị gỡ, một WebSocket đã mở trước đó vẫn có principal chứa authorities cũ. Phải làm gì?

**Đáp án:** Thiết kế thu hồi/đóng/reconnect connection và kiểm tra quyền hiện thời ở các tác vụ nhạy cảm cũng như lúc phát dữ liệu; không cho rằng authorities cũ được cập nhật tự động.

---

**Ghi nhớ:** **Spring WebSocket thường kế thừa `Principal` đã được Spring Security xác thực tại HTTP handshake**, sau đó Spring Messaging dùng danh tính đó cho STOMP handlers. Kế thừa principal **không phải** kế thừa mọi quyền, không tự xác thực native headers do client gửi, và không tự cập nhật connection cũ khi session/role thay đổi. Hãy bảo vệ **HTTP handshake, Origin, CSRF tại STOMP CONNECT, SEND/SUBSCRIBE, object-level ACL và vòng đời kết nối**; với WebFlux native, lấy principal từ `HandshakeInfo` rồi kiểm tra quyền từng message.
