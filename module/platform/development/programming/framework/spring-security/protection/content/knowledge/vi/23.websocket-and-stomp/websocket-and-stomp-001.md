# Ranh giới bảo vệ tại HTTP handshake và tại lớp message

## 1. Bài toán: bắt tay thành công chưa có nghĩa mọi message đều được phép

Một hệ thống có giao diện `https://app.example.com` và API thời gian thực tại `wss://api.example.com/ws`. Người dùng đã đăng nhập bằng session cookie, mở kết nối WebSocket để nhận thông báo đơn hàng và gửi yêu cầu tra cứu trạng thái đơn.

Một nhóm phát triển kiểm tra HTTP handshake thành công, thấy `101 Switching Protocols` rồi kết luận “WebSocket đã được Spring Security bảo vệ”. Kết luận đó **chưa đủ**:

- Một kết nối đã được mở có thể gửi **nhiều thông điệp** mà không tạo lại HTTP request cho mỗi thông điệp.
- Client có thể thử `SEND` đến đích không được phép hoặc `SUBSCRIBE` vào topic chứa dữ liệu của người khác.
- Một WebSocket được mở bằng cookie phiên có thể bị trang không tin cậy lợi dụng nếu server không kiểm tra nguồn gốc kết nối và không bảo vệ lớp STOMP.
- `HttpSecurity.authorizeHttpRequests(...)` chỉ kiểm tra HTTP requests, **không tự biến thành quy tắc phân quyền cho từng STOMP frame**.
- Nếu sử dụng WebFlux WebSocket native, ứng dụng cần kiểm tra quyền trong logic xử lý từng message; không được giả định cấu hình message broker STOMP của Servlet tự áp dụng.

Trong mô-đun **SPRING_SECURITY_HTTP_PROTECTION**, cần nhìn đồng thời các lớp CSRF, CORS và origin checks, security headers, CSP, HSTS/TLS, HTTP firewall và bảo vệ session. Bài này tập trung vào ranh giới **HTTP handshake** so với **lớp message** ở WebSocket/STOMP, có ví dụ cấu hình Spring Security Servlet và đối chiếu với Reactive.

### Sau bài học, người học có thể

1. Phân biệt HTTP `GET Upgrade`, WebSocket connection và các STOMP frame `CONNECT`, `SEND`, `SUBSCRIBE`.
2. Hiểu trách nhiệm của `SecurityFilterChain` đối với handshake và `AuthorizationManager<Message<?>>` đối với thông điệp inbound.
3. Giải thích vì sao kiểm tra `Origin` cho WebSocket quan trọng nhưng **không phải** CORS preflight thông thường.
4. Phân tích Cross-Site WebSocket Hijacking (CSWSH), session cookie và CSRF token trên STOMP `CONNECT`.
5. Viết quy tắc *deny by default* cho những destination mà client được gửi hoặc đăng ký.
6. Kiểm tra quyền truy cập đối tượng/tenant trong business service thay vì chỉ dựa vào tên destination.
7. Thiết kế bài test âm/dương cho handshake, CONNECT, SEND, SUBSCRIBE, mất phiên và thay đổi quyền giữa chừng.
8. Biết những phần cấu hình riêng cho Spring WebSocket Messaging (thường dùng Servlet) và WebFlux WebSocketHandler native.

Các URL trong bài thuộc `example.com` là minh họa. Tên lớp, API và giả định về security context cần được kiểm tra với phiên bản Spring sử dụng khi triển khai thực tế.

## 2. WebSocket, STOMP và ba thời điểm kiểm tra

**WebSocket** là giao thức giữ kết nối hai chiều sau khi thiết lập. **STOMP** là giao thức thông điệp có kiểu frame, destination và subscription, có thể được truyền bên trong WebSocket. Hai giao thức không phải một: WebSocket có thể mang JSON tùy biến mà **không hề dùng STOMP**.

Một luồng STOMP trên WebSocket điển hình:

~~~text
(1) HTTP GET /ws + Upgrade: websocket
    -> server kiểm tra HTTP/authentication/Origin
    <- HTTP 101 Switching Protocols nếu chấp nhận

(2) Trên cùng WebSocket connection:
    STOMP CONNECT với native headers
    -> kiểm tra danh tính/ngữ cảnh, CSRF CONNECT nếu áp dụng
    <- CONNECTED khi hợp lệ

(3) Client gửi nhiều frame:
    SUBSCRIBE destination:/user/queue/order-results
    SEND destination:/app/orders.lookup
    -> message authorization + business authorization

(4) Server phát MESSAGE tới những subscription hợp lệ
    -> client nhận dữ liệu theo quyền đã thiết kế
~~~

### 2.1. Sơ đồ ranh giới

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant H as HTTP Security / Handshake
    participant M as STOMP inbound security
    participant A as Application / Broker
    B->>H: GET /ws, Upgrade, Origin, Cookie nếu được phép
    H->>H: Kiểm tra Origin, authentication, HTTP path
    alt Handshake bị từ chối
        H-->>B: 401/403 hoặc HTTP error
    else Handshake thành công
        H-->>B: 101 Switching Protocols
        B->>M: STOMP CONNECT + CSRF token nếu yêu cầu
        M->>M: Xác thực ngữ cảnh và kiểm tra CONNECT
        alt CONNECT bị từ chối
            M-->>B: ERROR/đóng kết nối
        else CONNECT hợp lệ
            M-->>B: CONNECTED
            B->>M: SUBSCRIBE /user/queue/order-results
            M->>M: Kiểm tra quyền SUBSCRIBE
            B->>M: SEND /app/orders.lookup
            M->>M: Kiểm tra quyền MESSAGE theo destination
            M->>A: Đưa đến @MessageMapping
            A->>A: Kiểm tra chủ sở hữu đơn hàng/tenant
            A-->>B: MESSAGE được gửi đến subscription hợp lệ
        end
    end
~~~

Sơ đồ là luồng logic. Trên wire, server và broker có thể xử lý `ERROR`, heartbeat, disconnect và các trường hợp session invalid khác nhau. Mã HTTP 101 chỉ thuộc bước handshake; nó **không** có nghĩa STOMP `CONNECT` hoặc bất kỳ `SEND` nào được chấp nhận.

### 2.2. Bảng phân công trách nhiệm

| Ranh giới | Dữ liệu đầu vào | Kiểm tra chính | Điều **không** được bảo đảm |
| --- | --- | --- | --- |
| HTTP handshake | URL `/ws`, method GET/Upgrade, Origin, cookie/token nếu có | HTTP authentication, path policy, Origin allowlist, TLS | Không kiểm tra quyền cho mọi STOMP destination về sau |
| STOMP CONNECT | Frame CONNECT và native headers | Danh tính STOMP session, CSRF token khi áp dụng, thiết lập messaging session | Không chứng minh người dùng có quyền xem mọi topic |
| STOMP SEND | Message type MESSAGE, destination, payload, principal | Chỉ cho đích gửi hợp lệ, kiểm tra role và dữ liệu đầu vào | Không tự bảo đảm quyền trên object ID trong payload |
| STOMP SUBSCRIBE | Message type SUBSCRIBE, destination, principal | Chỉ được đăng ký đích hợp lệ, chặn nghe lén | Không bảo đảm mọi bản tin sau này đúng tenant nếu server route sai |
| Business service/broker | Principal, object ID, tenant, thông tin nghiệp vụ | Kiểm tra ownership/tenant; phát đến đích được phép | Không nên dựa vào Origin hay destination do client khai báo |
| Connection lifecycle | Session, logout, token expiry, heartbeat | Đóng/revalidate khi cần, quota/rate limit | Handshake thành công không bảo đảm quyền không đổi mãi mãi |

## 3. Ranh giới HTTP handshake được Spring Security bảo vệ như thế nào?

### 3.1. Handshake bắt đầu như một HTTP request

Với WebSocket qua HTTP/1.1, browser thường gửi request dạng:

~~~http
GET /ws HTTP/1.1
Host: api.example.com
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Origin: https://app.example.com
Cookie: SESSION=<session-cookie-if-browser-allows>
~~~

Server có thể chấp nhận:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <server-generated-value>
~~~

Hoặc từ chối bằng HTTP status thích hợp nếu chưa authenticated, Origin không được phép, request sai cấu trúc hoặc chính sách route không cho phép. Handshake phải đi qua reverse proxy và security chain thật thì mới kiểm chứng được hành vi này.

**Điểm cốt lõi:** sau khi nâng cấp kết nối, các STOMP frames **không còn là HTTP GET/POST mới**. Vì vậy HTTP URL authorization, CSRF trên POST hay header kiểm soát response **không tự động được thực hiện lại cho mỗi frame**.

### 3.2. Authentication ở handshake

Khi dùng session cookie:

1. Người dùng đăng nhập qua HTTP trước.
2. Browser quyết định có gửi cookie tới `wss://api.example.com/ws` dựa trên host, `Secure`, `SameSite`, chính sách cookie và ngữ cảnh trang.
3. Spring Security HTTP xác thực session trên request handshake.
4. Principal được gắn với WebSocket session và có thể được truyền vào tầng Spring Messaging.

Khi frontend và API khác origin nhưng cùng site, cookie `SameSite=Lax` **có thể** vẫn được gửi nếu đáp ứng điều kiện khác. Khi frontend ở site khác, browser có thể hạn chế cookie bên thứ ba dù handshake URL và cấu hình origin đúng.

Không đặt cookie/session ID trong query string chỉ để “làm WebSocket kết nối được”; query string thường xuất hiện ở access logs, tracing hoặc lịch sử quan sát. Với hệ thống dùng bearer token, cần một thiết kế xác thực handshake/CONNECT riêng, được kiểm thử và tránh lộ token.

### 3.3. HTTP SecurityFilterChain chỉ bảo vệ request bắt tay

Ví dụ Spring Security Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSocketHandshakeSecurity {

    @Bean
    SecurityFilterChain httpSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/ws", "/ws/**").authenticated()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .build();
    }
}
~~~

**Giới hạn của đoạn code:**

- `requestMatchers("/ws", "/ws/**")` kiểm tra HTTP request vào endpoint, bao gồm các đường dẫn SockJS fallback nếu bật ở nơi khác.
- `authenticated()` yêu cầu principal tại **HTTP handshake**. Nếu API dùng bearer token chỉ có trong STOMP CONNECT mà HTTP handshake không có auth, thiết kế này sẽ chặn handshake trước khi token được xử lý; phải thống nhất kiến trúc xác thực.
- Rule `authenticated()` **không** bảo vệ `SEND destination:/app/orders.lookup` hoặc `SUBSCRIBE destination:/topic/private`. Cần cấu hình message authorization riêng.
- Đây là khung bảo vệ HTTP; ứng dụng thật phải thêm cơ chế login/session hoặc bearer auth, chính sách CSRF/CORS cho HTTP routes và các exception phù hợp.
- HTTP firewall, TLS/HSTS và security headers vẫn là lớp bảo vệ HTTP; không thay thế quyền ở message layer.

### 3.4. Khi triển khai sau proxy

WebSocket over TLS dùng `wss://`. Proxy phải hỗ trợ upgrade/connection và chuyển thông tin cần thiết; với các biến thể transport khác, cách bắt tay có thể khác HTTP/1.1 Upgrade.

Cần kiểm tra **Origin mà browser gửi**, URL bên ngoài và path backend sau khi proxy rewrite. Nếu gateway trả 401/403 trước Spring, việc sửa riêng `SecurityFilterChain` không đủ. Đồng thời, gateway không được vô tình cho qua mọi origin trên một nhánh WebSocket trong khi HTTP API được kiểm soát chặt.

## 4. WebSocket cross-origin khác CORS của Fetch

Một ngộ nhận nguy hiểm là: “Chúng ta đã cấu hình `http.cors(...)` cho REST API, vậy WebSocket tự được bảo vệ khỏi mọi trang lạ”.

**Không đúng.** Native WebSocket handshake của browser không hoạt động giống Fetch CORS preflight OPTIONS:

- JavaScript trên một website có thể thử tạo `new WebSocket("wss://api.example.com/ws")` tới origin khác.
- Browser thường gửi header `Origin` trên handshake để server đánh giá, nhưng **không áp dụng cơ chế `Access-Control-Allow-Origin`/preflight như Fetch**.
- Server cần **tự từ chối origin không được tin cậy**, ví dụ bằng cấu hình endpoint Spring WebSocket hoặc filter/interceptor phù hợp.
- `Access-Control-Allow-Credentials` không phải cơ chế cấp quyền cho native WebSocket frames.
- Client ngoài browser có thể tự đặt/giả header `Origin`; do đó Origin validation **không thay authentication và authorization**.

### 4.1. Cross-Site WebSocket Hijacking (CSWSH)

Giả sử Alice đang đăng nhập `api.example.com`. Trang do kẻ tấn công kiểm soát chạy:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");

socket.addEventListener("open", () => {
  // Kẻ tấn công sẽ cố nói giao thức ứng dụng sau khi handshake.
});
~~~

Nếu browser gửi cookie phiên tới API trong ngữ cảnh đó và server không kiểm tra Origin/CSRF/message permissions, kết nối có thể bị sử dụng thay mặt Alice. Khi sử dụng STOMP, kẻ tấn công còn phải gửi các frame hợp lệ; nếu thiếu kiểm soát, họ có thể thử đăng ký topic hoặc gửi lệnh.

Đây là **CSWSH**: request mang credentials do browser tự gửi có thể thiết lập một kênh hai chiều mà script tại trang không tin cậy đọc/ghi được **nếu handshake được server chấp nhận**. Việc HTTP REST có CORS allowlist không tự ngăn kiểu truy cập này.

### 4.2. Kiểm tra Origin trong Spring WebSocket endpoint

Ví dụ Spring MVC/Servlet với WebSocket message broker:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class RealtimeEndpointConfiguration
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

Ý nghĩa:

- `addEndpoint("/ws")` tạo endpoint HTTP handshake cho STOMP-over-WebSocket.
- `setAllowedOrigins("https://app.example.com")` xác định những browser origins được chấp nhận tại endpoint; **không** phải rule dành cho REST API `/api/**`.
- `/app` là prefix để client gửi message tới application controller có `@MessageMapping`.
- `/topic` và `/queue` là prefix của simple broker minh họa, dành cho phân phối message; chúng **không tự được bảo vệ** nếu không có rule SUBSCRIBE/SEND.
- `/user` hỗ trợ user destinations; quyền subscribe và nội dung phát tới từng user vẫn phải kiểm soát.

**Không** thay `setAllowedOrigins(...)` bằng allow-all wildcard chỉ để kết nối được từ bất kỳ website nào khi API dùng session cookie. Nếu cần nhiều frontend, thêm từng origin đã được xác minh hoặc dùng pattern trong phạm vi quản trị chặt, rồi test negative cases.

### 4.3. Origin là tín hiệu chống cross-site, không phải danh tính

Một native WebSocket client ngoài browser có thể cố tình gửi `Origin: https://app.example.com` dù nó không chạy ở frontend này. Vì vậy:

- Kiểm tra Origin giúp bảo vệ trước website độc hại trong browser.
- HTTP authentication hoặc token verification quyết định client có danh tính nào.
- Message authorization và business service quyết định danh tính đó được làm gì.
- Rate limiting, payload validation và resource limits giảm lạm dụng, kể cả từ client đã authenticated.

## 5. STOMP là một lớp giao thức khác sau HTTP handshake

STOMP sử dụng các frame có command, native headers và body. Trong Spring WebSocket Messaging, frame từ client được chuyển thành `Message<?>` để qua các inbound channel interceptors và security.

### 5.1. Những loại frame thường gặp

| STOMP frame của client | Spring messaging type điển hình | Dữ liệu quan trọng | Điều phải kiểm soát |
| --- | --- | --- | --- |
| `CONNECT` | `SimpMessageType.CONNECT` | Native headers, session/principal, CSRF CONNECT khi áp dụng | Chỉ cho mở session messaging hợp lệ |
| `SEND` | `SimpMessageType.MESSAGE` | `destination`, payload, principal | Đích gửi, quyền thao tác và nội dung |
| `SUBSCRIBE` | `SimpMessageType.SUBSCRIBE` | `destination`, subscription id, principal | Được phép nghe dữ liệu ở đích đó không |
| `UNSUBSCRIBE` | `SimpMessageType.UNSUBSCRIBE` | Subscription id | Ngữ cảnh session và cleanup |
| `DISCONNECT` | `SimpMessageType.DISCONNECT` | Session | Đóng/cleanup/audit; có thể phát nhiều event |
| Heartbeat | `SimpMessageType.HEARTBEAT` | Nhịp kết nối | Timeout, tránh tài nguyên rò rỉ |

**STOMP CONNECT không phải HTTP `CONNECT` hoặc HTTP `GET Upgrade`.** Nó là frame được truyền **sau khi WebSocket đã mở**. HTTP security filter không nhìn STOMP CONNECT như một HTTP request mới.

### 5.2. Minh họa các frame

STOMP CONNECT có thể mang token CSRF dưới dạng **native STOMP header**:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
X-CSRF-TOKEN:<csrf-token>

^@
~~~

Một subscription:

~~~text
SUBSCRIBE
id:sub-1
destination:/user/queue/order-results

^@
~~~

Một message do client gửi:

~~~text
SEND
destination:/app/orders.lookup
content-type:application/json

{"orderId":2002}
^@
~~~

Trong các ví dụ trên, `^@` biểu diễn byte NUL kết thúc frame STOMP. Những header này nằm **bên trong WebSocket payload**, không phải HTTP request headers của handshake.

**Không tin** các giá trị `username`, `role`, `userId` hay `destination` do client tự điền. Spring phải lấy principal từ ngữ cảnh đã được xác thực; server còn phải kiểm tra quyền đối với `orderId` thật.

## 6. Bảo vệ STOMP inbound message bằng Spring Security

Với Spring WebSocket Message Broker (thường là stack Servlet), Spring Security có thể áp dụng authorization trên **client inbound channel**.

Ví dụ theo hướng cấu hình `@EnableWebSocketSecurity`:

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
class StompMessageSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        return messages
            // Các message không có destination (ví dụ CONNECT)
            // vẫn cần principal đã được xác thực.
            .nullDestMatcher().authenticated()

            // Không cho client SUBSCRIBE vào application destinations.
            .simpSubscribeDestMatchers("/app/**").denyAll()

            // Chỉ cho subscription vào các đích được phê duyệt.
            .simpSubscribeDestMatchers(
                "/topic/public",
                "/user/queue/order-results"
            ).authenticated()

            // Client SEND vào @MessageMapping đã chỉ định.
            .simpDestMatchers("/app/orders.lookup").hasRole("USER")

            // Các MESSAGE/SUBSCRIBE còn lại đều bị từ chối.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()

            // Không tự cho phép những loại frame khác.
            .anyMessage().denyAll()
            .build();
    }
}
~~~

### 6.1. Đọc policy theo thứ tự từ trên xuống

Các matcher được xét **theo thứ tự khai báo**. Với policy trên:

- `CONNECT` không có destination được xử lý bởi `nullDestMatcher().authenticated()` khi principal đã tồn tại; lớp CSRF cho CONNECT còn được Spring Security Messaging áp dụng theo cơ chế phù hợp.
- `SUBSCRIBE /app/orders.lookup` bị từ chối ở rule `simpSubscribeDestMatchers("/app/**").denyAll()`.
- `SUBSCRIBE /topic/public` hoặc `/user/queue/order-results` yêu cầu authenticated user.
- `SEND /app/orders.lookup` yêu cầu role `USER`.
- `SEND /topic/public` không được phép chỉ vì topic là public; nó rơi vào rule `simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()`.
- `SUBSCRIBE /topic/admin` bị từ chối vì không có rule cho phép tương ứng.
- Các message còn lại bị deny by default.

Một policy dạng `.simpDestMatchers("/topic/**").permitAll()` có thể vô tình cho client **gửi** trực tiếp vào broker destinations, không chỉ subscribe. Vì vậy cần phân biệt *message type* và *destination*, tránh mở rộng quyền không cần thiết.

### 6.2. Đừng cho client gửi trực tiếp vào broker destination

Nếu client được `SEND destination:/topic/private`, nội dung có thể được broker phát cho những subscription đang nghe topic đó mà **không đi qua handler nghiệp vụ `@MessageMapping` mong muốn**. Với chat hoặc notification, đây là nguy cơ giả mạo thông báo hoặc spam.

Thiết kế thông thường:

- Client gửi lệnh tới `/app/**`.
- Message security kiểm tra `SEND` thuộc endpoint được phép.
- `@MessageMapping` và service xác thực quyền và dữ liệu.
- **Server** mới dùng `SimpMessagingTemplate` để phát đến `/topic/**`, `/queue/**` hoặc `/user/**` phù hợp.

Quyền client `SUBSCRIBE` vào broker destinations được quản lý **riêng**. Broker simple/relay không tự biết ownership của từng user nếu ứng dụng không thiết kế kiểm tra.

### 6.3. Vì sao bảo vệ inbound channel là trọng tâm?

Spring Security Messaging chủ yếu xác thực/phân quyền **thông điệp đi vào từ client**. Không nên dựa vào giả định mọi **outbound MESSAGE** đều được kiểm tra lại bằng cùng những matcher.

Hệ quả:

1. Chặn subscription trái phép ngay tại inbound `SUBSCRIBE`.
2. Không cho client SEND trực tiếp vào protected broker destinations.
3. Trước khi server phát dữ liệu, kiểm tra danh tính và quyền với tài nguyên.
4. Nếu quyền thay đổi giữa chừng, có chiến lược thu hồi subscription/đóng connection hoặc lọc dữ liệu theo quyền ở nơi phát.
5. Nếu dùng external broker relay, cấu hình quyền và credentials ở broker riêng; Spring Security không thay thế bảo mật của broker bên ngoài.

## 7. Message authorization theo đích chưa đủ: phải kiểm tra object/tenant

Giả sử client được gửi `/app/orders.lookup`. Alice gửi:

~~~json
{"orderId":2002}
~~~

Nhưng đơn hàng 2002 thuộc Bob. Rule `hasRole("USER")` chỉ chứng minh Alice có role USER; nó **không** xác minh Alice được xem đơn hàng 2002.

### 7.1. Controller phải dùng principal server-side

Ví dụ message handler:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

record OrderLookup(long orderId) {}
record OrderSummary(long orderId, String state) {}

interface OrderService {
    // Phải kiểm tra ownership/tenant trong implementation.
    OrderSummary findVisibleOrder(String username, long orderId);
}

@Controller
class OrderMessageController {

    private final OrderService orders;
    private final SimpMessagingTemplate messaging;

    OrderMessageController(
        OrderService orders,
        SimpMessagingTemplate messaging
    ) {
        this.orders = orders;
        this.messaging = messaging;
    }

    @MessageMapping("/orders.lookup")
    void lookup(@Payload OrderLookup input, Principal principal) {
        // Không dùng userId/role tự khai trong STOMP payload.
        OrderSummary order = orders.findVisibleOrder(
            principal.getName(), input.orderId()
        );

        // Chỉ phát kết quả tới user đã xác thực này.
        messaging.convertAndSendToUser(
            principal.getName(),
            "/queue/order-results",
            order
        );
    }
}
~~~

`OrderService.findVisibleOrder` là giao diện minh họa; implementation thật phải **từ chối hoặc không tìm thấy** khi principal không có quyền trên đơn hàng/tenant, tránh lộ nội dung hoặc thông tin nhạy cảm. Đừng chỉ xem message handler là an toàn vì đã có `@MessageMapping` hoặc role USER.

### 7.2. User destinations và subscriptions

Client đăng ký:

~~~text
SUBSCRIBE
destination:/user/queue/order-results
id:my-results

^@
~~~

`/user/queue/order-results` là **user destination** được Spring ánh xạ theo principal/session. Với thiết kế đúng, server dùng `convertAndSendToUser(principal.getName(), ...)` thay vì để client tự chọn username đích.

Tuy vậy, nếu dữ liệu được phát sai user hoặc service trả dữ liệu trái quyền, prefix `/user` không tự sửa lỗ hổng. Phải kiểm tra quyền trước khi phát.

### 7.3. Topic theo phòng/tenant cần authorization riêng cho SUBSCRIBE

Giả sử ứng dụng có `/topic/orders/2002` và `/topic/orders/1001`. Một rule chung:

~~~java
// Rủi ro nếu mỗi order/topic có dữ liệu riêng tư:
messages.simpSubscribeDestMatchers("/topic/orders/*").authenticated();
~~~

chỉ yêu cầu user đăng nhập, **không kiểm tra quyền theo orderId**. Alice có thể thử subscribe vào topic đơn hàng của Bob.

Với topic riêng tư, nên:

- Có một `AuthorizationManager<Message<?>>` tùy biến kiểm tra message destination và principal với ACL/tenant membership, hoặc một luồng tạo subscription được kiểm soát theo quyền.
- Xác minh số lượng, pattern và phân đoạn destination, tránh path biến thể làm bỏ qua matcher.
- Đóng hoặc thu hồi các subscription không còn quyền; xem xét quyền thay đổi sau khi kết nối tồn tại lâu.
- Ưu tiên user destinations khi nghiệp vụ thực sự là dữ liệu riêng cho từng principal.

Không đưa một ví dụ `permitAll("/topic/**")` vào production nếu các topic chứa dữ liệu cá nhân.

## 8. CSRF trên STOMP CONNECT: khác CSRF HTTP

### 8.1. Vì sao STOMP CONNECT cần bảo vệ?

Một WebSocket handshake dùng session cookie có thể được browser tự gửi. Nếu không kiểm soát cross-site origin và lớp message, một website độc hại có thể cố mở socket bằng phiên của nạn nhân.

Trong cấu hình Spring Security WebSocket Messaging với `@EnableWebSocketSecurity`, tài liệu/cơ chế Spring Security yêu cầu **CSRF token hợp lệ ở inbound STOMP `CONNECT`** để bảo vệ cùng-origin. Đây là một ranh giới **sau HTTP handshake**: preflight CORS thông thường không được dùng để bảo vệ native WebSocket handshake.

Token phải nằm trong **STOMP native header** của frame CONNECT. Nó không nhất thiết xuất hiện trong HTTP GET Upgrade vì browser WebSocket API không cho JavaScript đặt arbitrary HTTP request headers.

### 8.2. Lấy CSRF token bằng kênh HTTP được bảo vệ

Một SPA có thể lấy CSRF token qua endpoint HTTP do ứng dụng triển khai:

~~~java
import java.util.Map;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenEndpoint {

    @GetMapping("/api/csrf")
    Map<String, String> token(
        @RequestAttribute("_csrf") CsrfToken token
    ) {
        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        );
    }
}
~~~

Điều kiện vận hành:

- Endpoint `/api/csrf` **phải được triển khai và có quyền truy cập phù hợp**; Spring không tự tạo sẵn endpoint này chỉ vì bật WebSocket.
- Với frontend khác origin, HTTP CORS cho `/api/csrf` phải cho phép origin tin cậy đọc response; **điều này khác** allowlist của WebSocket endpoint.
- Token gắn với ngữ cảnh session và cơ chế CSRF repository/request handler đã chọn. Với token deferred/masked, cần kiểm thử cách phát token tương ứng phiên bản Spring Security.
- Không log token hoặc cho origin không tin cậy đọc response chứa token.
- Nếu token/session thay đổi sau login/logout, client cần lấy token mới hoặc kết nối lại theo cơ chế thiết kế.

### 8.3. JavaScript STOMP gửi token ở CONNECT

Ví dụ sử dụng API phổ biến của thư viện `@stomp/stompjs`:

~~~javascript
import { Client } from "@stomp/stompjs";

async function openRealtime() {
  const response = await fetch(
    "https://api.example.com/api/csrf",
    { credentials: "include" }
  );

  if (!response.ok) {
    throw new Error("Không lấy được CSRF token");
  }

  const { headerName, token } = await response.json();

  const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    connectHeaders: {
      [headerName]: token
    },
    reconnectDelay: 3000,

    onConnect: () => {
      client.subscribe(
        "/user/queue/order-results",
        frame => {
          const data = JSON.parse(frame.body);
          console.log("Kết quả đơn hàng:", data);
        }
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

**Điểm phân biệt quan trọng:** `connectHeaders` là **STOMP CONNECT native headers**, không phải HTTP request headers của WebSocket handshake. `Origin` của HTTP handshake do browser tạo theo origin trang đang chạy; script không thể tùy ý đặt header HTTP `Origin` để tự vượt allowlist.

Đoạn frontend giả định ứng dụng có endpoint `/api/csrf`, người dùng đã đăng nhập, cookie policy cho phép gửi phiên và Spring backend đã bật STOMP/security thích hợp. Bản mẫu không bao gồm UI, cơ chế logout, xử lý reconnect sau token đổi hay retry backoff đầy đủ.

### 8.4. Không “sửa” CONNECT thất bại bằng cách tắt toàn bộ CSRF

Nếu HTTP handshake thành công nhưng STOMP CONNECT bị từ chối, cần phân biệt:

- Token có được cấp cho đúng session chưa?
- Token đã được đặt **đúng STOMP native header** chưa?
- CSRF repository/request handler và STOMP security có cùng ngữ cảnh không?
- Connection có principal đã xác thực chưa?
- Frontend ở origin được phép và cookie có được browser gửi không?
- Một gateway/broker relay có xử lý header/protocol khác dự kiến không?

Tắt CSRF trên mọi HTTP endpoint chỉ để làm kết nối thành công có thể tạo nguy cơ với các POST/PUT API khác. Nếu sử dụng SockJS fallback, các HTTP requests do transport tạo có đặc thù riêng; cần ngoại lệ CSRF **rất hẹp** khi thật sự cần, trong khi vẫn bảo vệ STOMP CONNECT theo thiết kế. Không xem một exception HTTP là việc tắt message-layer CSRF.

## 9. Principal và bearer token ở lớp nào?

### 9.1. Spring mặc định thường dùng principal của HTTP handshake

Trong mô hình session:

~~~text
HTTP login -> session cookie
    -> WebSocket GET /ws, Spring Security xác thực HTTP
    -> Principal gắn với WebSocket session
    -> inbound STOMP CONNECT/SEND/SUBSCRIBE dùng principal đó
~~~

Native STOMP headers như `login` và `passcode` do client gửi **không mặc nhiên là Spring Security authentication** cho ứng dụng. Không được lấy `login:admin` hay `userId:42` trong frame làm bằng chứng đã xác thực.

### 9.2. Bearer token trong STOMP CONNECT là một thiết kế khác

Browser WebSocket API không cho script thêm arbitrary HTTP `Authorization` header vào handshake. Một số ứng dụng gửi bearer token trong **STOMP CONNECT header**, rồi dùng một `ChannelInterceptor` tùy biến để:

1. Trích xuất token từ frame CONNECT.
2. Xác thực chữ ký, issuer, audience, expiry và các điều kiện token.
3. Tạo principal đã được kiểm tra.
4. Gắn principal/authority đúng cách vào messaging session trước khi Spring Security kiểm tra quyền.
5. Xác định thứ tự interceptors để không xảy ra trường hợp authorization chạy trước xác thực.
6. Xử lý token hết hạn, logout và reconnect.

Đây không phải một khả năng được bật tự động chỉ bằng `.authenticated()` trên HTTP `/ws`. Nếu handshake yêu cầu authenticated nhưng bearer token chỉ đến ở STOMP CONNECT, handshake sẽ bị chặn trước; cần thiết kế nhất quán.

Không nên truyền access token qua URL query string hoặc STOMP `login` dưới giả định Spring tự xác thực. Hãy bảo vệ log/metrics và đường kết nối TLS.

### 9.3. Authentication ban đầu không đồng nghĩa quyền vĩnh viễn

WebSocket có thể tồn tại nhiều giờ. User có thể bị khóa, role bị thu hồi, token hết hạn hoặc quyền vào một phòng/tenant thay đổi. Nếu chỉ kiểm tra một lần lúc handshake, connection cũ có thể tiếp tục nhận dữ liệu.

Một hệ thống nhạy cảm cần cân nhắc:

- Kiểm tra quyền ở những hành động message quan trọng và thời điểm phát dữ liệu.
- Đóng connection hoặc hủy subscription khi logout/thu hồi phiên/quyền.
- Giới hạn thời lượng phiên, thời gian không hoạt động, heartbeat và tốc độ gửi message.
- Tránh lưu `SecurityContext`/principal sai phạm vi giữa các session.
- Định nghĩa rõ cách reconnect xác thực lại sau token hết hạn.

## 10. Kiểm thử hai ranh giới bằng ma trận âm/dương

Một bộ test WebSocket/STOMP có ích phải có **ít nhất hai tầng assertion**: handshake và message layer.

| Mã | Tình huống | Kỳ vọng | Lớp xử lý |
| --- | --- | --- | --- |
| H1 | Origin app, session hợp lệ, GET Upgrade đúng | Handshake được chấp nhận | HTTP + handshake |
| H2 | Không authenticated, GET `/ws` | Bị chặn nếu policy HTTP yêu cầu login | HTTP Security |
| H3 | Origin `https://evil.example.org`, session hợp lệ | Handshake bị từ chối bởi origin policy | Handshake |
| H4 | Origin gần giống `https://app.example.com.evil.example.org` | Bị từ chối | Handshake |
| H5 | Origin app nhưng HTTP thay `http`/port khác | Bị từ chối nếu không thuộc allowlist | Origin policy |
| H6 | Client ngoài browser tự đặt Origin hợp lệ nhưng không có token/session | Không vượt authentication | HTTP Security |
| M1 | Handshake thành công, STOMP CONNECT có CSRF token hợp lệ | CONNECTED khi principal/security hợp lệ | STOMP CONNECT security |
| M2 | Handshake thành công, CONNECT thiếu/sai CSRF token | Bị từ chối khi CSRF CONNECT được bật | STOMP CONNECT security |
| M3 | SEND `/app/orders.lookup` có role USER | Qua destination authorization; vẫn phải kiểm tra object | Inbound MESSAGE + business |
| M4 | SEND `/topic/public` từ client | Bị từ chối | Inbound MESSAGE |
| M5 | SUBSCRIBE `/topic/public` khi authenticated | Được phép theo ví dụ policy | Inbound SUBSCRIBE |
| M6 | SUBSCRIBE `/topic/admin` | Bị từ chối | Inbound SUBSCRIBE |
| M7 | SUBSCRIBE `/app/orders.lookup` | Bị từ chối | Inbound SUBSCRIBE |
| M8 | Alice lookup order của Bob | Bị business authorization từ chối, không phát dữ liệu Bob | Business service |
| M9 | User logout/role bị thu hồi, connection còn mở | Policy thu hồi/đóng connection có hiệu lực theo thiết kế | Lifecycle |
| R1 | Kết nối WebFlux native, message trái quyền | Bị handler/service từ chối; không dựa vào STOMP annotations | Reactive message handling |

Cần có **test kết quả âm**: không chỉ kiểm tra `SEND` trả `ERROR`, mà còn xác minh **không có dữ liệu nhạy cảm nào được phát đến subscription** và không có side effect nghiệp vụ.

## 11. Kiểm tra HTTP handshake bằng công cụ HTTP và WebSocket thật

### 11.1. Curl chỉ mô phỏng HTTP Upgrade

Một lệnh kiểm tra header/route ở tầng HTTP/1.1:

~~~bash
curl -i --http1.1 "https://api.example.com/ws" \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Origin: https://evil.example.org"
~~~

**Chú ý:**

- Ví dụ không mang phiên, nên HTTP authentication có thể từ chối **trước** khi origin policy được đánh giá; một 401 chưa chứng minh kiểm tra Origin hoạt động.
- `curl` không trở thành một STOMP/WebSocket client đầy đủ; nó không tự gửi/đọc frame theo giao thức ứng dụng như thư viện WebSocket.
- Không kết luận HTTP 101 đồng nghĩa `CONNECT` hoặc `SUBSCRIBE` đã được phép.
- Trên Windows PowerShell cũ, dùng `curl.exe` nếu `curl` là alias của `Invoke-WebRequest`.

Để test origin bị từ chối độc lập với auth, cần một tài khoản thử nghiệm có session hợp lệ hoặc môi trường test cấu hình xác thực phù hợp và kiểm tra response thực tế.

### 11.2. Test handshake từ hai browser origins

Chuẩn bị hai trang thử nghiệm do nhóm sở hữu:

- `https://app.example.com`: được phép.
- `https://evil.example.org`: không được phép.

Mỗi trang chạy:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");

socket.addEventListener("open", () => {
  console.log("HTTP handshake/WebSocket đã mở");
});

socket.addEventListener("error", event => {
  console.error("Kết nối bị từ chối/lỗi mạng", event);
});

socket.addEventListener("close", event => {
  console.log("Đóng kết nối:", event.code, event.reason);
});
~~~

Code trên chỉ kiểm tra **WebSocket handshake**, không thực hiện STOMP CONNECT. Do đó có thể thấy socket mở rồi nhanh chóng đóng do server đang chờ STOMP frame hoặc timeout. Muốn chứng minh end-to-end STOMP, dùng `@stomp/stompjs` và gửi CONNECT với token thích hợp.

Trong DevTools, xem request WebSocket `/ws`, response 101/401/403 và `Origin`. Khi đã mở, xem tab Messages/Frames để xác minh `CONNECT`, `CONNECTED`, `SUBSCRIBE`, `SEND` và `ERROR`. Không dùng dữ liệu production thật.

### 11.3. Test tự động bằng WebSocket STOMP client

Trong môi trường tích hợp Servlet, nên dùng một client test thực hiện HTTP handshake và STOMP frames, ví dụ `WebSocketStompClient` với `StandardWebSocketClient`. Các assertion nên gồm:

1. Handshake không authenticated bị từ chối theo policy HTTP.
2. Origin không được phép bị từ chối **dù có session thử nghiệm hợp lệ**.
3. Session hợp lệ + CSRF CONNECT đúng có `CONNECTED`.
4. CONNECT thiếu/sai CSRF không được chấp nhận.
5. SEND tới `/topic/public` bị từ chối.
6. SUBSCRIBE `/topic/admin` bị từ chối.
7. SUBSCRIBE vào user destination phù hợp và SEND `/app/orders.lookup` cho order của chính user trả kết quả đúng.
8. Truy vấn order user khác không trả thông tin và không tạo side effect.

Các assertion ở lớp STOMP thường cần timeout, handler cho `ERROR`, trạng thái đóng connection và cơ chế đồng bộ bất đồng bộ; **không** dùng HTTP 200/101 thay cho kết quả của frame.

`MockMvc` hữu ích để test HTTP authentication, CSRF endpoint và request matcher trong ứng dụng Servlet, nhưng chỉ `MockMvc GET /ws` **không mô phỏng đầy đủ WebSocket upgrade và mọi STOMP frame**. Cần integration test qua WebSocket client.

## 12. STOMP/SockJS fallback và HTTP CSRF: ngoại lệ cần kiểm soát

Một số frontend dùng SockJS để hỗ trợ các transport fallback, ví dụ XHR streaming/polling. Khi bật `.withSockJS()` ở endpoint:

- Đường dẫn thực tế có thể là `/ws/info`, `/ws/{server}/{session}/{transport}` và các request HTTP khác.
- Một số transport dùng **HTTP POST**, khiến Spring Security HTTP CSRF protection có thể từ chối nếu nó coi đó là POST thay đổi trạng thái.
- Browser CORS đối với XHR fallback **có thể** liên quan, khác native WebSocket handshake.
- `setAllowedOrigins(...)`/SockJS origin policy cần được đánh giá cho cả WebSocket và fallback transports.
- Cookie, SameSite, CORS và proxy headers có thể khác nhau giữa transports.

**Không tắt CSRF cho mọi URL** chỉ để SockJS hoạt động. Nếu thiết kế bắt buộc bỏ CSRF ở những HTTP transport URLs do SockJS tạo, ngoại lệ phải giới hạn **đúng endpoint/transport** và phải tiếp tục bảo vệ **STOMP CONNECT** cùng message authorization.

Tương tự, việc bật CSRF HTTP mặc định không chứng minh các STOMP `SEND` đã được CSRF/authorization kiểm tra. Cần kiểm thử đúng tầng.

Với chính sách bảo mật mới hoặc môi trường kiểm soát tốt, có thể đánh giá khả năng chỉ hỗ trợ native WebSocket để đơn giản hóa bề mặt; quyết định dựa trên yêu cầu client thực tế.

## 13. Đối chiếu Reactive WebFlux: native WebSocket không phải STOMP broker Servlet

Spring WebFlux cung cấp `WebSocketHandler` với `WebSocketSession` và các API Reactive. Đây là giao diện xử lý WebSocket messages dạng text/binary, **không tự cung cấp STOMP broker routing theo `@EnableWebSocketMessageBroker`** như cấu hình Servlet ở trên.

Nếu ứng dụng WebFlux dùng native WebSocket:

- `ServerHttpSecurity` bảo vệ HTTP handshake route.
- Origin allowlist phải được thực thi tại handshake hoặc WebFilter/adapter thích hợp.
- `WebSocketHandler` phải **parse, validate và authorize từng message**, bao gồm loại hành động, đối tượng và giới hạn tài nguyên.
- Nếu ứng dụng cần STOMP semantics trên Reactive, phải lựa chọn triển khai thư viện/broker/bridge tương ứng và xây dựng security policy message riêng; không sao chép `@EnableWebSocketSecurity` của Servlet rồi giả định áp dụng.
- `CorsWebFilter` và `ServerHttpSecurity.cors(...)` phục vụ CORS cho HTTP/WebFlux routes khi phù hợp; **không phải** cơ chế tự động kiểm tra tất cả native WebSocket messages.

### 13.1. Cấu hình HTTP handshake security cho WebFlux

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveWebSocketHandshakeSecurity {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/ws").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Giống Servlet, `authenticated()` yêu cầu thông tin đăng nhập ở HTTP handshake. Nó **không kiểm tra quyền trong từng text/binary frame** sau khi kết nối đã được thiết lập.

### 13.2. Ví dụ WebFilter chặn Origin ngoài allowlist

Một ví dụ minh họa cho route `/ws` chỉ phục vụ browser ở một origin được tin cậy:

~~~java
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.WebFilter;

@Configuration
class ReactiveWebSocketOriginSecurity {

    private static final Set<String> ALLOWED_ORIGINS =
        Set.of("https://app.example.com");

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter webSocketOriginFilter() {
        return (exchange, chain) -> {
            String path = exchange.getRequest().getPath().value();

            if ("/ws".equals(path)) {
                String origin =
                    exchange.getRequest().getHeaders().getOrigin();

                if (origin == null || !ALLOWED_ORIGINS.contains(origin)) {
                    exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
                    return exchange.getResponse().setComplete();
                }
            }

            return chain.filter(exchange);
        };
    }
}
~~~

Đây là **một lựa chọn minh họa**, không phải cơ chế Origin validation duy nhất của WebFlux. Nó giả định route `/ws` chỉ dành cho browser WebSocket, nên từ chối cả request không có Origin. Hệ thống thực cần kiểm tra routing sau proxy, normalization của Origin, các transport được hỗ trợ và thứ tự WebFilter. Non-browser clients vẫn có thể giả Origin; **authentication bắt buộc**.

Không dùng cách so chuỗi con như `origin.contains("example.com")` vì có thể cho lọt host gần giống. Khi hệ thống có nhiều origin hợp lệ, hãy quản trị allowlist hữu hạn.

### 13.3. Mẫu handler kiểm tra từng message

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface RealtimeCommandService {
    // Implementation phải parse, validate và authorize mỗi command
    // theo principal + object/tenant được yêu cầu.
    Mono<Void> validateAuthorizeAndHandle(
        Principal principal,
        String payload
    );
}

class AuthorizedWebSocketHandlers {

    static WebSocketHandler handler(RealtimeCommandService commands) {
        return session ->
            session.getHandshakeInfo().getPrincipal()
                .switchIfEmpty(Mono.error(
                    new AccessDeniedException("Login required")))
                .flatMap(principal ->
                    session.receive()
                        .concatMap(message ->
                            commands.validateAuthorizeAndHandle(
                                principal,
                                message.getPayloadAsText()
                            ))
                        .then()
                );
    }
}
~~~

Ví dụ tập trung vào điểm kiểm tra: **mỗi message phải được service xác thực cú pháp, giới hạn kích thước/tần suất và phân quyền theo principal + dữ liệu đích**. `RealtimeCommandService` là giao diện minh họa chưa có implementation; đoạn mã cần được tích hợp với `HandlerMapping` và `WebSocketHandlerAdapter` tương ứng trong ứng dụng thật.

Khi phát message lại cho client, phải kiểm tra quyền và không phát dữ liệu sang session khác do route sai. Với endpoint có dữ liệu nhạy cảm, cần thêm cách đóng connection khi phát hiện vi phạm và kiểm soát backpressure/rate limiting.

## 14. Những lỗi triển khai thường gặp

| Triệu chứng | Lớp cần điều tra | Cách chẩn đoán |
| --- | --- | --- |
| HTTP handshake 401/302 | HTTP authentication | Cookie/token có được gửi? `/ws` có nằm trong SecurityFilterChain đúng không? |
| HTTP handshake 403 từ browser origin lạ | Origin policy | Kiểm tra `Origin` và `setAllowedOrigins`/WebFilter |
| Handshake 101 rồi STOMP CONNECT bị từ chối | Message security/CSRF CONNECT | Xem CONNECT frame, principal và CSRF native header |
| STOMP CONNECT hợp lệ nhưng SEND bị deny | Destination/role matcher | Đọc `simpDestMatchers` và thứ tự rule |
| Client gửi được trực tiếp vào `/topic/**` | Inbound MESSAGE policy quá rộng | Chặn SEND tới broker destinations |
| User thường subscribe được `/topic/admin` | SUBSCRIBE policy quá rộng | Chỉ cho destination có chủ đích, kiểm tra tenant |
| User A nhận order của user B | Business authorization/routing | Kiểm tra ownership trước phát và user destination |
| Sau logout socket vẫn nhận message | Session lifecycle/revocation | Đóng session, thu hồi subscription và revalidate quyền |
| Browser REST CORS đúng nhưng WebSocket từ origin lạ vẫn mở | Nhầm CORS với WebSocket Origin validation | Kiểm tra handshake Origin độc lập với ACAO |
| SockJS fallback 403 nhưng native WebSocket hoạt động | HTTP CSRF/CORS trên transport fallback | Kiểm tra transport POST, cookies, Origin và ngoại lệ hẹp |
| Browser không gửi session cookie khi bắt tay | Cookie policy | SameSite, Secure, domain/path, cross-site restrictions |
| Proxy trả 400/426 hoặc không lên 101 | WebSocket upgrade/routing | Upgrade headers, TLS termination, HTTP version |
| STOMP auth dùng `login:admin` không được nhận | Tin nhầm native headers | Xác thực principal từ HTTP hoặc interceptor kiểm tra bearer thật |
| WebFlux handler đã được HTTP auth nhưng nhận lệnh trái quyền | Thiếu per-message authorization | Parse, validate và authorize mỗi message trong service |
| Kết nối bị đóng do frame quá lớn | Message size/resource limits | Kiểm tra kích thước, send buffer, timeout và rate limiting |
| Browser console có CSP `connect-src` violation | CSP frontend | Bổ sung `wss://api.example.com` nếu được phép |
| Có thông báo giả dù user không có quyền gửi | Server cho client publish trực tiếp broker | Định tuyến qua `/app/**` và business handler |
| Cross-origin WebSocket từ non-browser vẫn kết nối với Origin giả | Origin không phải authentication | Bắt token/session hợp lệ và phân quyền server-side |

### 14.1. Gợi ý chẩn đoán theo thời điểm

1. **Chưa có 101:** kiểm tra handshake HTTP, TLS/proxy, Origin policy và HTTP authentication.
2. **Có 101, chưa có CONNECTED:** kiểm tra STOMP CONNECT, native CSRF header, principal và inbound interceptors.
3. **Có CONNECTED, SEND bị từ chối:** kiểm tra MESSAGE destination, role và business authorization.
4. **Có CONNECTED, SUBSCRIBE bị từ chối:** kiểm tra SUBSCRIBE destination/tenant permissions.
5. **SUBSCRIBE thành công nhưng nhận sai dữ liệu:** kiểm tra routing server, owner/tenant, outbound data isolation và lifecycle.
6. **Chỉ lỗi sau proxy/SockJS:** kiểm tra transport, HTTP route, Origin/cookie forwarding và gateway timeouts.

Không giải quyết lỗi ở một giai đoạn bằng cách tắt bảo mật ở giai đoạn khác.

## 15. Kết hợp với các lớp HTTP protection khác

| Cơ chế | Ranh giới trách nhiệm |
| --- | --- |
| **CORS cho HTTP REST** | Browser được đọc cross-origin response của các HTTP requests; không tự bảo vệ WebSocket native |
| **Origin validation ở handshake** | Hạn chế website nào được browser dùng để mở WebSocket; không thay identity |
| **CSRF trên STOMP CONNECT** | Bảo vệ việc thiết lập messaging session khi browser có thể tự gửi credentials |
| **Message authorization** | Giới hạn `SEND`/`SUBSCRIBE` theo type, destination, principal |
| **Business authorization** | Ownership, role, scope, tenant, quyền đối với object thật |
| **HTTP authentication/session** | Xác minh danh tính trên handshake khi dùng session/token HTTP |
| **CSP `connect-src`** | Frontend chỉ kết nối tới những endpoint `wss://`/HTTP được phép; không là server-side authorization |
| **TLS/WSS, HSTS** | Bảo vệ đường truyền và chính sách HTTPS; WSS tránh gửi dữ liệu qua kết nối WebSocket không mã hóa |
| **HTTP firewall** | Từ chối HTTP handshake malformed; không trực tiếp parse mọi STOMP payload |
| **Cookie attributes** | `Secure`, `HttpOnly`, `SameSite`, Domain/Path giúp giới hạn sử dụng session cookie |
| **Rate limit/quotas** | Giảm spam SEND, subscription fan-out, memory exhaustion, slow clients |
| **Cache-Control** | Bảo vệ response HTTP mang session/CSRF token; không thay message-layer authorization |

**XSS là rủi ro đặc biệt:** nếu kẻ tấn công chạy JavaScript ngay trong frontend được tin cậy, script có thể dùng quyền WebSocket/STOMP của user đó. CSP và chống XSS giúp giảm rủi ro, còn backend vẫn phải kiểm tra quyền theo object/action.

## 16. Checklist triển khai bảo mật WebSocket/STOMP

- [ ] HTTP handshake có authentication và matcher đúng route `/ws`, bao gồm đường dẫn fallback nếu bật SockJS.
- [ ] Native WebSocket endpoint có Origin allowlist chính xác; không nhầm với ACAO của HTTP REST.
- [ ] Browser chỉ dùng `wss://` khi triển khai production qua TLS; proxy hỗ trợ upgrade và giữ route/Origin cần thiết.
- [ ] Session cookie có `Secure`, `HttpOnly`, `SameSite`/Domain/Path phù hợp; không dùng query token không kiểm soát.
- [ ] STOMP CONNECT được bảo vệ CSRF theo cấu hình Spring Messaging đang sử dụng, và client gửi token ở native STOMP header đúng.
- [ ] Nếu xác thực bằng bearer token trong STOMP CONNECT, có interceptor kiểm tra token, gắn principal đúng thứ tự và xử lý token expiry.
- [ ] Các rule MESSAGE/SUBSCRIBE là **deny by default**, không cho client SEND trực tiếp vào broker destinations.
- [ ] `SUBSCRIBE` tới private topic/user destination được giới hạn theo principal và ownership/tenant phù hợp.
- [ ] `@MessageMapping`/service xác minh role, action, object ID và tenant theo dữ liệu server.
- [ ] Không sử dụng `Origin`, STOMP `login` hoặc `userId` trong payload như bằng chứng danh tính.
- [ ] Có phương án đóng session/hủy subscription khi logout, thu hồi quyền hoặc token hết hạn.
- [ ] Có giới hạn payload, rate, subscription count, heartbeat, timeout và kiểm soát backpressure.
- [ ] Với external broker relay, ACL/credentials và routing của broker cũng được đánh giá.
- [ ] Test riêng HTTP 101/401/403, STOMP CONNECT/ERROR, SEND/SUBSCRIBE và dữ liệu nhận thực tế.
- [ ] Test origin lạ, client ngoài browser giả Origin, role thiếu, object của người khác và session bị thu hồi.
- [ ] WebFlux native WebSocket được bảo vệ bằng `ServerHttpSecurity` **và** kiểm tra từng message trong handler/service, không mặc định dùng được `@EnableWebSocketSecurity` của Servlet.
- [ ] CSP `connect-src`, TLS/HSTS, CSRF HTTP, HTTP firewall và security headers khác không bị nới lỏng tùy tiện để khắc phục một lỗi handshake.

## 17. Câu hỏi tình huống và lời giải

**Tình huống 1 — Chỉ kiểm tra 101.** User đã đăng nhập mở WebSocket thành công; nhóm dev thấy HTTP 101 và tuyên bố mọi message an toàn. Thiếu gì?

**Lời giải:** Thiếu xác minh STOMP CONNECT, CSRF ở CONNECT khi áp dụng, inbound SEND/SUBSCRIBE authorization, business ownership/tenant và lifecycle của connection.

**Tình huống 2 — REST có CORS allowlist.** `http.cors(...)` cho HTTP REST chỉ chấp nhận app origin. Trang lạ vẫn thử `new WebSocket(...)` tới `/ws`. Vì sao phải kiểm tra thêm Origin?

**Lời giải:** Native WebSocket handshake không được browser bảo vệ bằng Fetch CORS preflight/ACAO như HTTP API. Server cần Origin validation riêng để chống CSWSH, bên cạnh authentication và message authorization.

**Tình huống 3 — Header giả.** Non-browser client gửi `Origin: https://app.example.com` trong handshake dù không phải trang app. Có được xác thực không?

**Lời giải:** Không. Origin là tín hiệu nguồn gốc giúp chặn website độc hại trong browser; client ngoài browser có thể giả. Phải xác thực token/session và kiểm tra quyền ở server.

**Tình huống 4 — CSRF CONNECT.** Handshake HTTP 101, nhưng STOMP CONNECT bị từ chối. Client đã gửi `X-CSRF-TOKEN` trong một request HTTP Fetch khác. Đủ chưa?

**Lời giải:** Chưa. Khi Spring Security Messaging yêu cầu CSRF ở STOMP CONNECT, client phải gửi token hợp lệ dưới dạng **native STOMP CONNECT header** gắn đúng phiên; token ở request khác không tự xuất hiện trong frame.

**Tình huống 5 — Gửi trực tiếp topic.** Client SEND tới `/topic/public` và mọi subscriber nhận message như thể server thông báo. Lỗi ở đâu?

**Lời giải:** Message authorization cho phép SEND trực tiếp vào broker destination. Chỉ cho client SEND các `/app/**` được chỉ định, để handler/business service kiểm tra rồi server mới phát.

**Tình huống 6 — Subscribe dữ liệu người khác.** Alice có role USER và được subscribe `/topic/orders/*`; Alice chọn order của Bob. Vì sao role-only chưa đủ?

**Lời giải:** Role USER không chứng minh ownership đối với order ID. Phải phân quyền subscription theo order/tenant và kiểm tra dữ liệu trước phát, hoặc dùng user destinations có routing an toàn.

**Tình huống 7 — Logout rồi vẫn nhận thông báo.** Alice logout HTTP nhưng WebSocket đã mở vẫn nhận messages. CORS có khắc phục không?

**Lời giải:** Không. Connection có vòng đời riêng; cần cơ chế đóng/revalidate session, thu hồi subscription và kiểm tra quyền tại thời điểm phát.

**Tình huống 8 — Browser không cho Authorization handshake.** SPA có bearer token và muốn thêm HTTP Authorization header vào `new WebSocket(...)`. Vì sao không làm như Fetch?

**Lời giải:** Browser WebSocket API không hỗ trợ tùy ý đặt request headers như Fetch. Cần một thiết kế xác thực rõ ràng (session cookie ở HTTP handshake, hoặc token được kiểm tra trong STOMP CONNECT/transport phù hợp) và tránh lộ token qua URL.

**Tình huống 9 — SockJS POST bị 403.** Native WebSocket thành công, SockJS fallback XHR POST bị CSRF HTTP chặn. Có nên tắt toàn bộ CSRF không?

**Lời giải:** Không. Phải phân biệt HTTP transport requests với STOMP CONNECT, giới hạn ngoại lệ chính xác khi cần và tiếp tục bảo vệ HTTP POST nghiệp vụ, CONNECT và message authorization.

**Tình huống 10 — WebFlux native handler.** WebFlux đã cấu hình `ServerHttpSecurity.pathMatchers("/ws").authenticated()`, nhưng client gửi text JSON lệnh xóa tài khoản khác. Có được bảo vệ tự động không?

**Lời giải:** Không. Security chain bảo vệ handshake, còn mỗi WebSocket message phải được handler/service parse, validate và authorize theo principal, action và tài nguyên đích.

**Tình huống 11 — CSP.** Frontend có CSP `connect-src 'self'` và JavaScript không mở được `wss://api.example.com/ws` dù server cho Origin. Cần sửa gì?

**Lời giải:** CSP ở frontend có thể chặn kết nối trước khi handshake. Chỉ thêm endpoint `wss://api.example.com` vào `connect-src` khi thực sự tin cậy; không bỏ Origin/auth/message authorization ở backend.

**Tình huống 12 — Client tự khai role.** STOMP SEND có body `{"role":"ADMIN","orderId":2002}` từ Alice. Có được dựa vào role này để cấp dữ liệu admin không?

**Lời giải:** Không. Role và principal phải từ ngữ cảnh server đã xác thực; service kiểm tra permission trên order/tenant thật. Payload là dữ liệu không tin cậy.

---

**Ghi nhớ:** **HTTP handshake chỉ quyết định có mở kênh WebSocket và gắn danh tính ban đầu hay không; STOMP CONNECT và các frame SEND/SUBSCRIBE có ranh giới bảo mật riêng.** CORS của REST không tự bảo vệ native WebSocket, Origin validation không thay authentication, và `authenticated()` trên `/ws` không thay authorization tại message/object layer. Dùng Spring Security WebSocket Messaging với CSRF CONNECT và allowlist destination chặt cho Servlet STOMP; với WebFlux native WebSocket, kiểm tra handshake **và từng message** trong pipeline Reactive. Luôn phối hợp TLS/WSS, cookie/session, CSRF, CSP, HTTP firewall và kiểm thử end-to-end.
