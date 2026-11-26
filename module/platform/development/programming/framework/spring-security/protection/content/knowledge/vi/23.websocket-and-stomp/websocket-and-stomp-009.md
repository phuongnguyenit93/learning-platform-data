# Phân biệt kiểm tra CONNECT với phân quyền SEND, SUBSCRIBE

## 1. Vấn đề: CONNECTED không có nghĩa được gửi và nghe mọi thông điệp

Giả sử Alice đăng nhập tại `https://app.example.com` rồi mở một kênh realtime đến `wss://api.example.com/ws`. Trình duyệt gửi session cookie trong HTTP handshake; server xác thực Alice và chấp nhận WebSocket. Sau đó một STOMP client gửi `CONNECT` hợp lệ và nhận `CONNECTED`.

Alice có được phép thực hiện những hành động sau không?

- `SEND /app/orders.lookup` để xem đơn hàng 1001 thuộc Alice.
- `SEND /topic/admin` để giả mạo thông báo của hệ thống.
- `SUBSCRIBE /topic/orders/2002` để theo dõi đơn hàng của Bob.
- `SUBSCRIBE /user/queue/order-results` để nhận kết quả dành riêng cho Alice.

Câu trả lời **khác nhau cho từng hành động**. STOMP `CONNECT` chỉ mở một phiên giao tiếp ở lớp messaging theo chính sách xác thực và CSRF; nó không cấp quyền vô hạn lên mọi destination. Quyền **gửi lệnh** và quyền **đăng ký nhận dữ liệu** phải được kiểm tra bằng message authorization, đồng thời quyền đối với từng đối tượng như `orderId` hoặc `tenantId` cần được kiểm tra ở tầng nghiệp vụ.

Bài này thuộc chương **WebSocket và STOMP** của mô-đun **SPRING_SECURITY_HTTP_PROTECTION**, với mục tiêu triển khai các lớp phòng vệ HTTP và trình duyệt trong Spring Security — từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session, cho cả Servlet và Reactive. Trọng tâm chính là phân biệt **STOMP CONNECT**, **STOMP SEND** và **STOMP SUBSCRIBE** trong **Spring WebSocket Message Broker trên Servlet**; phần cuối đối chiếu **WebFlux native WebSocket**, nơi những command STOMP không mặc nhiên tồn tại.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt HTTP WebSocket handshake với STOMP `CONNECT`, `SEND` và `SUBSCRIBE`.
2. Giải thích kiểm tra principal, token và CSRF tại CONNECT khác message authorization tại SEND/SUBSCRIBE.
3. Hiểu cách Spring ánh xạ STOMP `SEND` thành `SimpMessageType.MESSAGE` và `SUBSCRIBE` thành `SimpMessageType.SUBSCRIBE`.
4. Cấu hình `@EnableWebSocketSecurity` cùng `AuthorizationManager<Message<?>>` và các matchers theo **thứ tự an toàn**.
5. Ngăn client SEND trực tiếp tới broker destinations `/topic/**` hoặc `/queue/**`.
6. Giới hạn SUBSCRIBE vào public, admin, user-specific và object-specific destinations theo mức độ nhạy cảm.
7. Sử dụng principal server-side và object/tenant ACL để tránh BOLA/IDOR.
8. Không nhầm việc bảo vệ inbound messages với bảo vệ dữ liệu outbound và vòng đời connection.
9. Kiểm thử các trường hợp CONNECT hợp lệ nhưng SEND/SUBSCRIBE trái quyền, bao gồm việc **không rò rỉ dữ liệu**.
10. Nhận biết các khác biệt trong SockJS HTTP fallback và WebFlux native WebSocket.

Các domain `example.com`, đơn hàng và tên role chỉ là ví dụ. Code minh họa hướng tới Spring Security Messaging sử dụng `@EnableWebSocketSecurity`; API/thứ tự config cụ thể cần được xác minh với phiên bản trong dự án.

## 2. Bốn mốc khác nhau của một phiên realtime

Một ứng dụng STOMP-over-WebSocket có những mốc:

| Mốc | Giao thức | Câu hỏi cần trả lời | Công cụ kiểm tra |
| --- | --- | --- | --- |
| **HTTP handshake** | `GET /ws` và WebSocket Upgrade | Client có được mở transport và HTTP principal là ai? | `SecurityFilterChain`, HTTP authentication, Origin validation |
| **STOMP CONNECT** | Inbound `CONNECT` frame | Client được thiết lập phiên STOMP này không? Có CSRF/credentials phù hợp không? | `CsrfChannelInterceptor`, CONNECT authentication và message security |
| **STOMP SEND** | Inbound `SEND` frame, được Spring ánh xạ thành message type `MESSAGE` | Client được gửi lệnh tới destination này không? Payload/object có hợp quyền không? | Message `AuthorizationManager`, `@MessageMapping`, business ACL |
| **STOMP SUBSCRIBE** | Inbound `SUBSCRIBE` frame | Client được tạo subscription để nhận dữ liệu tại destination này không? | Subscription matchers, topic/object ACL, broker/user routing |

**Không đảo ngược mối quan hệ:** nếu CONNECT bị từ chối thì không được phép có luồng gửi/đăng ký message ứng dụng hợp lệ. Nhưng CONNECT được chấp nhận **không bảo đảm** mọi SEND/SUBSCRIBE về sau đều hợp lệ.

### 2.1. Minh họa hành trình từ browser tới service

~~~mermaid
sequenceDiagram
    participant UI as Browser/STOMP client
    participant HTTP as Spring Security HTTP
    participant STOMP as STOMP inbound channel
    participant POLICY as Message AuthorizationManager
    participant APP as Service / Broker
    UI->>HTTP: GET /ws + Upgrade + Origin + Cookie
    HTTP->>HTTP: HTTP auth + Origin policy
    HTTP-->>UI: 101 Switching Protocols
    UI->>STOMP: STOMP CONNECT + native CSRF header
    STOMP->>STOMP: Kiểm tra CONNECT principal/CSRF
    STOMP-->>UI: CONNECTED nếu hợp lệ
    UI->>STOMP: SEND /app/orders.lookup
    STOMP->>POLICY: MESSAGE + destination + authorities
    POLICY->>APP: Cho qua khi rule hợp lệ
    APP->>APP: Kiểm tra Alice có quyền với orderId
    APP-->>UI: Kết quả đến user destination hợp lệ
    UI->>STOMP: SUBSCRIBE /topic/orders/2002
    STOMP->>POLICY: SUBSCRIBE + destination + Alice
    POLICY-->>UI: Từ chối nếu Alice không sở hữu order 2002
~~~

Sơ đồ thể hiện luồng logic, không khẳng định mọi lỗi đều tạo cùng một frame `ERROR` hoặc cùng một mã đóng WebSocket. Khi test, cần kiểm tra **quyết định truy cập và dữ liệu thực tế**, không suy đoán chỉ từ HTTP status.

### 2.2. Mỗi bước khác một loại danh tính hoặc quyền

- **Authentication:** xác minh ai đang kết nối, thường lấy từ HTTP session hoặc một bearer token đã được kiểm chứng tại CONNECT.
- **CSRF CONNECT:** kiểm tra token phù hợp nhằm chống việc một website lạ lợi dụng browser-managed credentials để mở kênh STOMP.
- **Message authorization:** kiểm tra principal được quyền gửi/đăng ký **loại message và destination nào**.
- **Object authorization:** kiểm tra principal được quyền thao tác/nhận **tài nguyên cụ thể** nào.
- **Outbound authorization/routing:** server chỉ phát dữ liệu cho user/subscription có quyền tại thời điểm thích hợp.

Mỗi bước giải quyết một câu hỏi khác; không thay thế nhau.

## 3. HTTP handshake chỉ mở transport

Từ `https://app.example.com`, frontend mở WebSocket đến `wss://api.example.com/ws`. Trong trường hợp HTTP/1.1 điển hình:

~~~http
GET /ws HTTP/1.1
Host: api.example.com
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com
Cookie: SESSION=<session-if-browser-allows>
~~~

Nếu được chấp nhận, response có thể là:

~~~http
HTTP/1.1 101 Switching Protocols
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Accept: <server-generated-value>
~~~

Spring Security HTTP có thể xác thực session hoặc bearer credentials tại handshake. WebSocket endpoint phải kiểm tra browser Origin phù hợp; `https://app.example.com` là **origin của trang chạy script**, không phải `wss://api.example.com` và không phải user ID.

**Giới hạn quan trọng:**

- `101` chỉ chứng minh transport được mở, chưa có STOMP CONNECTED.
- HTTP `authorizeHttpRequests` không chạy lại trên từng STOMP SEND/SUBSCRIBE như những HTTP requests mới.
- Native WebSocket không sử dụng Fetch CORS preflight OPTIONS/ACAO làm cơ chế kiểm soát frames.
- Browser `new WebSocket(...)` không hỗ trợ tùy ý đặt HTTP `Authorization` hoặc `X-CSRF-TOKEN` header.
- Một non-browser WebSocket client có thể giả Origin; Origin **không** phải authentication.

Nếu HTTP handshake bị từ chối 401, 403 hoặc do proxy/TLS/CSP, CONNECT chưa được gửi đến messaging layer. Không dùng thất bại HTTP để kết luận một rule STOMP SEND/SUBSCRIBE hoạt động.

## 4. CONNECT: cấp phép tham gia phiên STOMP, không cấp toàn bộ quyền dữ liệu

### 4.1. Cấu trúc một frame CONNECT

Sau handshake, STOMP client gửi:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
X-CSRF-TOKEN:<csrf-token-for-current-context>

^@
~~~

`^@` ký hiệu byte NUL kết thúc frame. Nếu được chấp nhận:

~~~text
CONNECTED
version:1.2

^@
~~~

STOMP `CONNECT` thường không có destination. Do đó một rule `simpDestMatchers("/app/**")` không thể được dùng thay toàn bộ bảo vệ CONNECT.

### 4.2. Hai mô hình authentication phổ biến

| Mô hình | Principal tới từ đâu? | HTTP handshake | CONNECT |
| --- | --- | --- | --- |
| **HTTP session inheritance** | Spring Security xác thực cookie/session trên HTTP `GET /ws` rồi Spring WebSocket giữ `Principal` | `/ws` thường yêu cầu authenticated | Gửi native CSRF token khi Spring Messaging yêu cầu |
| **Bearer tại STOMP CONNECT** | Custom `ChannelInterceptor` xác minh native `Authorization: Bearer ...` rồi gắn `Authentication` | Có thể chưa có principal; handshake path phải được giới hạn và kiểm soát riêng | Phải xác thực bearer **trước** authorization, đồng thời giải quyết chính sách CSRF CONNECT hiện hành |

Không thể lấy cấu hình HTTP `/ws authenticated()` của mô hình session rồi chuyển bearer token **chỉ** sang STOMP CONNECT mà vẫn trông đợi handshake được phép. HTTP authentication đã chạy trước khi CONNECT frame tồn tại.

### 4.3. CSRF CONNECT là kiểm tra độc lập

Spring Security WebSocket Messaging dùng `@EnableWebSocketSecurity` có cơ chế kiểm tra CSRF token ở inbound `CONNECT`, thường qua `CsrfChannelInterceptor` và thông tin expected token được chuẩn bị theo HTTP/handshake context.

- Token phải xuất hiện trong **native STOMP CONNECT header**.
- Đây không phải HTTP header của GET Upgrade.
- CSRF token **không** chứng minh role USER/ADMIN hay quyền xem một order.
- Bearer access token (JWT) **không tự được coi là CSRF token**.
- Nếu dùng bearer-only CONNECT không có HTTP session, phải thiết kế CSRF strategy rõ ràng theo phiên bản Spring Security và threat model; không mặc định JWT làm cơ chế CONNECT CSRF biến mất.
- Nếu token thiếu/sai, CONNECT bị từ chối dù HTTP 101 đã thành công.

### 4.4. STOMP login/passcode không phải principal mặc định

Client có thể tự khai:

~~~text
CONNECT
login:admin
passcode:whatever

^@
~~~

Các trường `login`/`passcode` thuộc giao thức STOMP/broker relay theo cấu hình phù hợp; chúng **không tự xác thực user ứng dụng Spring Security**. Không gán role ADMIN chỉ bằng header do client tự gửi.

### 4.5. CONNECTED có thể làm được gì?

Khi nhận CONNECTED, client có thể **thử** gửi những SEND/SUBSCRIBE tiếp theo. Nhưng server phải kiểm tra từng message:

~~~text
CONNECTED
    |
    +-- SEND /app/orders.lookup -> kiểm tra MESSAGE + role + order ACL
    |
    +-- SEND /topic/admin      -> chặn client publish thẳng broker
    |
    +-- SUBSCRIBE /topic/public -> theo rule public
    |
    +-- SUBSCRIBE /topic/orders/2002 -> ownership/tenant ACL
~~~

**CONNECTED ≠ authorized SEND ≠ authorized SUBSCRIBE.**

## 5. SEND: phân quyền hành động và đích nhận lệnh

### 5.1. SEND trong STOMP trở thành MESSAGE trong Spring

Một STOMP client gửi:

~~~text
SEND
destination:/app/orders.lookup
content-type:application/json

{"orderId":1001}
^@
~~~

Trong inbound Spring Messaging, STOMP `SEND` thường tương ứng `SimpMessageType.MESSAGE`. Vì vậy khi viết catch-all rule cần dùng:

~~~java
.simpTypeMatchers(SimpMessageType.MESSAGE).denyAll()
~~~

không phải một enum tên `SEND`. Đây là bẫy dễ gặp khi lập trình viên suy luận message types từ tên command STOMP.

### 5.2. `/app/**` và `/topic/**` có chức năng khác nhau

Một cấu hình broker phổ biến:

~~~text
/app/orders.lookup   -> Spring @MessageMapping / service
/topic/public        -> broker broadcast destination
/queue/updates       -> broker queue destination
/user/queue/updates  -> Spring user destination prefix
~~~

Client thường nên SEND tới **application destinations** để controller và service kiểm tra payload/auth, rồi server mới publish tới broker.

Luồng an toàn:

~~~mermaid
flowchart TD
    A["Client SEND /app/orders.lookup"] --> B["Inbound MESSAGE authorization"]
    B --> C["@MessageMapping"]
    C --> D["Service kiểm tra order/tenant"]
    D --> E["Server publish kết quả tới user destination"]
    E --> F["Broker route đúng subscription"]
~~~

Phản ví dụ:

~~~text
SEND
destination:/topic/orders/2002
content-type:application/json

{"status":"DELIVERED"}
^@
~~~

Nếu server cho client SEND trực tiếp tới broker và broker phát payload, Alice có thể giả mạo trạng thái hoặc thông báo được server chứng thực. **Cấm client SEND tới `/topic/**`/`/queue/**`** trừ khi nghiệp vụ thực sự yêu cầu và có cơ chế validation/ACL không kém an toàn.

### 5.3. Role check không đủ để bảo vệ orderId

Giả sử rule cho mọi user role USER SEND `/app/orders.lookup`. Alice có role USER nhưng gửi:

~~~json
{"orderId":2002}
~~~

Order 2002 thuộc Bob. Message layer có thể cho phép **đi vào handler**, nhưng service phải kiểm tra Alice có quyền đọc order đó. Nếu không, đó là Broken Object Level Authorization (BOLA)/IDOR.

**Phân quyền SEND có ít nhất hai cấp:**

1. *Cấp destination/action*: Alice có quyền gửi lệnh lookup không?
2. *Cấp object/tenant*: Alice được tra cứu **order 2002** không?

Không dùng một rule `hasRole("USER")` để tuyên bố đã có object ACL.

### 5.4. Input validation và rate limiting vẫn cần thiết

Dù người dùng có quyền SEND:

- Validate schema, kiểu dữ liệu, kích thước payload và số trường.
- Giới hạn tần suất command, kích thước STOMP frame, số lệnh đồng thời.
- Tránh xử lý lặp/side effects khi client reconnect/retry; dùng idempotency khi nghiệp vụ yêu cầu.
- Không để client tự gửi `role`, `tenantId` hoặc `userId` rồi tin đó là identity.
- Log metadata cần thiết mà không ghi bearer/CSRF token hoặc dữ liệu riêng tư.
- Tránh gửi message tới broker trước khi transaction/authorization hoàn thành.

## 6. SUBSCRIBE: phân quyền ai được nghe dữ liệu nào

### 6.1. SUBSCRIBE không phải SEND

Một client tạo subscription:

~~~text
SUBSCRIBE
id:orders-2002
destination:/topic/orders/2002

^@
~~~

Trong Spring Messaging, đây là `SimpMessageType.SUBSCRIBE`. Nó không xử lý lệnh cập nhật như `SEND /app/...`, nhưng có thể tạo quyền **nghe dữ liệu về sau**. Nếu topic chứa dữ liệu cá nhân, SUBSCRIBE trái quyền có thể nghiêm trọng như đọc một API REST không có kiểm tra ownership.

### 6.2. Bốn loại subscription thường gặp

| Destination | Chính sách minh họa | Rủi ro khi rule quá rộng |
| --- | --- | --- |
| `/topic/public` | Có thể cho authenticated user (hoặc public thực sự nếu CONNECT policy hỗ trợ) | Công khai nhầm dữ liệu riêng |
| `/topic/admin` | Chỉ role ADMIN, còn phải xét đúng dữ liệu | User thường nghe thông báo quản trị |
| `/user/queue/order-results` | User đã xác thực; server route theo principal/session | Server phát nhầm nội dung hoặc username |
| `/topic/orders/{id}` | Kiểm tra principal có quyền với đúng order/tenant tại lúc đăng ký | Alice nghe order 2002 của Bob |

**Không** dùng:

~~~java
// Phản ví dụ khi /topic/orders/** mang dữ liệu riêng:
.simpSubscribeDestMatchers("/topic/orders/**")
    .authenticated()
~~~

Vì mọi user đã login đều có thể nghe các order IDs khác nhau, trừ khi có một ACL khác được thiết kế và thực thi chắc chắn.

### 6.3. SUBSCRIBE có thể cần quyền động

Đối với `/topic/orders/2002`, một `AuthorizationManager<Message<?>>` chuyên biệt có thể:

1. Nhận authenticated principal của message.
2. Đọc destination đã được Spring xác định.
3. Parse order ID theo pattern chặt; từ chối destination không hợp lệ.
4. Truy vấn chính sách tenant/ownership/membership hiện hành.
5. Chỉ cho phép subscription khi user có quyền.
6. Audit quyết định mà không lộ dữ liệu nhạy cảm.

Quyền động này là **điểm bổ sung** cho rule role/destination tổng quát. Nếu Alice mất quyền với order 2002 **sau khi subscribe**, cần cơ chế hủy subscription, ngăn publisher gửi hoặc revalidate trước phát. Không coi một lần SUBSCRIBE được chấp thuận là quyền vĩnh viễn.

### 6.4. User destinations không loại bỏ business ACL

Client thường subscribe:

~~~text
SUBSCRIBE
id:my-results
destination:/user/queue/order-results

^@
~~~

Server gửi:

~~~java
messaging.convertAndSendToUser(
    principal.getName(),
    "/queue/order-results",
    result
);
~~~

Spring hỗ trợ user destination resolution theo principal/session, nhưng:

- Publisher vẫn có thể gửi sai username hoặc payload sai quyền.
- Một user có thể có nhiều WebSocket sessions, ở nhiều tab hay thiết bị.
- Nhiều server nodes và broker relay cần cấu hình routing/user registry phù hợp.
- Quyền truy cập object vẫn phải kiểm tra trước khi server phát dữ liệu.
- Một subscription hợp lệ không có nghĩa user còn được nghe sau khi role/membership bị thu hồi.

## 7. Đặt policy ở đúng lớp Spring Security

Spring Servlet/STOMP có một số thành phần khác nhau:

| Thành phần | Chức năng |
| --- | --- |
| `SecurityFilterChain` / `HttpSecurity` | Bảo vệ HTTP handshake path, HTTP authentication/session/CSRF/CORS |
| `StompEndpointRegistry#setAllowedOrigins` | Giới hạn browser origins được bắt tay WebSocket/SockJS |
| `@EnableWebSocketMessageBroker` | Bật hạ tầng STOMP Message Broker |
| `@EnableWebSocketSecurity` | Kích hoạt tích hợp Spring Security cho client inbound messaging |
| `CsrfChannelInterceptor` | Kiểm tra CSRF token trên inbound STOMP CONNECT theo integration |
| `AuthorizationManager<Message<?>>` | Quyết định quyền trên inbound messages theo principal, type và destination |
| `@MessageMapping`/service | Parse command, validate payload, kiểm tra object-level permissions |
| `SimpMessagingTemplate`/broker | Phát dữ liệu đúng user/subscription và quản lý routing |
| Application lifecycle/revocation | Đóng hoặc kiểm tra lại connection/subscriptions khi quyền thay đổi |

**Nguyên tắc:** không cài thêm một interceptor trùng chức năng security do `@EnableWebSocketSecurity` đã cấp chỉ để “an toàn hơn”. Thứ tự kiểm tra và nguồn principal/token phải nhất quán.

## 8. Cấu hình Servlet/STOMP từ endpoint tới HTTP security

### 8.1. Cấu hình STOMP endpoint

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

`/ws` là HTTP handshake endpoint. `/app` xử lý SEND qua application; `/topic`/`/queue` là broker destinations; `/user` dành cho user-based routing. Cấu hình này **chưa** phân quyền messages.

### 8.2. HTTP SecurityFilterChain với session login

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HttpHandshakeSecurityConfiguration {

    @Bean
    SecurityFilterChain securityChain(HttpSecurity http)
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

Đây là mô hình dùng HTTP session: browser gửi cookie trong handshake, HTTP Security xác thực principal, Spring WebSocket kế thừa principal vào messaging session. Production cần user store, entry point/login form, CORS HTTP cho REST APIs và cấu hình session phù hợp.

Rule `authenticated()` trên `/ws` **không cấp quyền SEND/SUBSCRIBE**. Nó cũng chặn mô hình bearer-only CONNECT nếu browser **không** mang credential trên HTTP handshake: token trong STOMP CONNECT chưa có cơ hội được gửi. Hai kiến trúc phải được lựa chọn nhất quán.

### 8.3. Origin và CSRF là hai phòng vệ khác nhau

`setAllowedOrigins("https://app.example.com")` kiểm soát browser origin tại handshake. Khi session cookie được browser tự gửi, Spring Security Messaging có thể yêu cầu native CSRF token tại STOMP CONNECT để giảm rủi ro CSWSH.

Browser WebSocket API không gửi Fetch CORS preflight OPTIONS như một HTTP Fetch khác origin; CORS của REST không tự bảo vệ WebSocket. Đồng thời, Origin không xác thực principal và token CSRF không xác nhận role. Mỗi lớp giữ đúng nhiệm vụ.

## 9. Message AuthorizationManager: tách SEND và SUBSCRIBE an toàn

### 9.1. Policy deny-by-default hoàn chỉnh ở mức destination

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
class RealtimeMessageSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        return messages
            // CONNECT và control messages không có destination
            // trong ví dụ đều đòi principal đã xác thực.
            .nullDestMatcher().authenticated()

            // Không cho client SUBSCRIBE vào application destinations.
            .simpSubscribeDestMatchers("/app/**").denyAll()

            // Một destination admin: không cho USER thông thường.
            .simpSubscribeDestMatchers("/topic/admin")
                .hasRole("ADMIN")

            // Những subscription user/public đã được phê duyệt.
            .simpSubscribeDestMatchers(
                "/topic/public",
                "/user/queue/order-results"
            ).authenticated()

            // Những SEND command được phê duyệt.
            .simpDestMatchers("/app/orders.lookup")
                .hasRole("USER")
            .simpDestMatchers("/app/orders.cancel")
                .hasRole("USER")

            // Không cho SEND trực tiếp broker hoặc SUBSCRIBE khác.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()

            // Các message/control types còn lại chưa khai báo -> deny.
            .anyMessage().denyAll()
            .build();
    }
}
~~~

Cấu hình trên minh họa quyền **theo destination**. Với private order topics, cần thêm dynamic ACL; do đó chúng **chưa** được mở bằng một wildcard tổng quát. Chú ý role convention: `hasRole("USER")` thường trông đợi authority dạng `ROLE_USER` (tùy cấu hình role prefix).

### 9.2. Giải thích từng nhóm matcher

- `nullDestMatcher().authenticated()`: xác thực principal cho messages không có destination, bao gồm CONNECT và một số control messages. Bước này **không** thay CSRF CONNECT.
- `simpSubscribeDestMatchers("/app/**").denyAll()`: chặn client SUBSCRIBE application destinations.
- `simpSubscribeDestMatchers("/topic/admin").hasRole("ADMIN")`: chỉ áp dụng cho **SUBSCRIBE**, không phải cho SEND admin messages.
- `simpSubscribeDestMatchers("/topic/public").authenticated()`: xác định quyền **nghe**, không tự cho client **phát** vào public topic.
- `simpDestMatchers("/app/orders.lookup").hasRole("USER")`: cho phép message có destination này theo matcher; đặt rule SUBSCRIBE /app deny **trước** để tránh vô tình cấp SUBSCRIBE vào application destinations.
- `simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()`: từ chối mọi SEND/SUBSCRIBE chưa được phê duyệt.
- `anyMessage().denyAll()`: đóng phần còn lại theo nguyên tắc allowlist.

### 9.3. Thứ tự matcher ảnh hưởng trực tiếp kết quả

Các matchers thường được đánh giá theo **thứ tự khai báo**, dùng quyết định của matcher khớp đầu tiên. Phản ví dụ:

~~~java
// Sai khi /topic/** chứa broker destinations:
messages
    .simpDestMatchers("/topic/**").authenticated()
    .simpTypeMatchers(
        SimpMessageType.MESSAGE,
        SimpMessageType.SUBSCRIBE
    ).denyAll();
~~~

Một inbound SEND tới `/topic/admin` có thể match `simpDestMatchers("/topic/**")` **trước** rule deny MESSAGE. Một user authenticated có thể được phép gửi trực tiếp vào broker trái chủ đích.

Thay bằng rule **subscribe-specific**:

~~~java
messages
    .simpSubscribeDestMatchers("/topic/public")
        .authenticated()
    .simpTypeMatchers(
        SimpMessageType.MESSAGE,
        SimpMessageType.SUBSCRIBE
    ).denyAll()
    .anyMessage().denyAll();
~~~

Và chỉ cho SEND tới những `/app/**` destinations có handler/authorization phù hợp. Test regression mỗi khi thêm mới pattern.

### 9.4. Vì sao không dùng chung một rule cho SEND và SUBSCRIBE?

Một destination có thể được client khai theo nhiều message types. Viết rule destination-only quá rộng dễ vô tình cho phép hành động khác mong đợi. Lý tưởng, chính sách cần nêu rõ:

| Hành động | Destination | Policy |
| --- | --- | --- |
| SEND | `/app/orders.lookup` | USER + object ACL |
| SEND | `/app/orders.cancel` | USER + state/ownership check |
| SEND | `/topic/public` | Deny |
| SEND | `/topic/admin` | Deny |
| SUBSCRIBE | `/topic/public` | Authenticated theo ví dụ |
| SUBSCRIBE | `/topic/admin` | ADMIN |
| SUBSCRIBE | `/app/orders.lookup` | Deny |
| SUBSCRIBE | `/topic/orders/{id}` | Dynamic object/tenant ACL nếu hỗ trợ |

**Một destination path giống nhau không có nghĩa SEND và SUBSCRIBE có cùng quyền.**

## 10. Đối chiếu STOMP command với SimpMessageType

Không nhầm các command STOMP với HTTP verbs hoặc enum của Spring:

| STOMP command từ client | Spring `SimpMessageType` thường tương ứng | Kiểm tra cần chú ý |
| --- | --- | --- |
| `CONNECT` / `STOMP` | `CONNECT` | Principal, CSRF CONNECT, authentication strategy |
| `SEND` | `MESSAGE` | Destination/action role và object ACL |
| `SUBSCRIBE` | `SUBSCRIBE` | Topic/user/object ACL |
| `UNSUBSCRIBE` | `UNSUBSCRIBE` | Subscription lifecycle và control policy |
| `DISCONNECT` | `DISCONNECT` | Cleanup/control policy |
| Heartbeat | `HEARTBEAT` | Connection lifecycle và rate/resource limits |

Một số control messages không có destination. Đừng tưởng `simpDestMatchers("/app/**")` bao phủ CONNECT hoặc DISCONNECT. Ngược lại, đừng tưởng `simpTypeMatchers(MESSAGE).denyAll()` sẽ từ chối SUBSCRIBE: cần chỉ định cả MESSAGE và SUBSCRIBE nếu muốn chặn cả hai.

Spring Messaging sử dụng `SimpMessageType.MESSAGE` cho inbound STOMP SEND là chi tiết quyết định trong cấu hình security phổ biến.

## 11. Phân quyền động SUBSCRIBE theo orderId và tenant

### 11.1. Hạn chế của static path matcher

Ví dụ:

~~~text
/topic/orders/1001  -> Alice sở hữu
/topic/orders/2002  -> Bob sở hữu
/topic/orders/3003  -> Chỉ thành viên tenant B được xem
~~~

Một pattern `/topic/orders/*` chỉ kiểm tra **hình dạng đường dẫn**, không biết order thuộc về ai. `hasRole("USER")` cũng không biết Alice thuộc tenant B hay không.

Nếu hệ thống muốn cho phép subscribe từng order topic, cần dynamic authorization.

### 11.2. Skeleton AuthorizationManager<Message<?>> cho subscription

Ví dụ dưới đây minh họa cách đọc destination và kiểm tra ACL theo principal. `OrderVisibilityService` là interface **ứng dụng phải hiện thực**, thường hỏi database/policy service về quyền subscribe order tương ứng.

~~~java
import java.util.function.Supplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;

interface OrderVisibilityService {
    boolean canSubscribe(Authentication user, long orderId);
}

final class OrderSubscriptionAuthorizationManager
        implements AuthorizationManager<Message<?>> {

    private static final Pattern DESTINATION =
        Pattern.compile("^/topic/orders/([1-9][0-9]{0,17})$");

    private final OrderVisibilityService orders;

    OrderSubscriptionAuthorizationManager(OrderVisibilityService orders) {
        this.orders = orders;
    }

    @Override
    public AuthorizationDecision check(
        Supplier<Authentication> authentication,
        Message<?> message
    ) {
        Authentication user = authentication.get();

        if (user == null || !user.isAuthenticated()
                || user instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        String destination =
            SimpMessageHeaderAccessor.getDestination(
                message.getHeaders()
            );

        Matcher m = DESTINATION.matcher(
            destination == null ? "" : destination
        );

        if (!m.matches()) {
            return new AuthorizationDecision(false);
        }

        long orderId = Long.parseLong(m.group(1));

        return new AuthorizationDecision(
            orders.canSubscribe(user, orderId)
        );
    }
}
~~~

Đoạn code có chủ đích là **khung minh họa**, chưa bao gồm timeout, caching, persistence ACL, exception mapping hoặc tối ưu cho event-loop/thread model. Nó đọc destination **đã được xác định trong Spring message headers**, không lấy một `userId` tự khai trong payload. Regex được anchor để tránh khớp hậu tố giả và giới hạn dạng số. AuthorizationManager trên inbound channel cần có mức thời gian phản hồi phù hợp và không gây quá tải database khi client spam SUBSCRIBE.

### 11.3. Gắn dynamic manager sau các rule cụ thể khác

Một cách tổ chức:

~~~java
@Bean
AuthorizationManager<Message<?>> messageAuthorizationManager(
    MessageMatcherDelegatingAuthorizationManager.Builder messages,
    OrderVisibilityService orders
) {
    return messages
        .nullDestMatcher().authenticated()
        .simpSubscribeDestMatchers("/app/**").denyAll()
        .simpSubscribeDestMatchers("/topic/public")
            .authenticated()
        .simpSubscribeDestMatchers("/topic/orders/*")
            .access(new OrderSubscriptionAuthorizationManager(orders))
        .simpDestMatchers("/app/orders.lookup")
            .hasRole("USER")
        .simpTypeMatchers(
            SimpMessageType.MESSAGE,
            SimpMessageType.SUBSCRIBE
        ).denyAll()
        .anyMessage().denyAll()
        .build();
}
~~~

Ví dụ này là **phương án thay thế** cho bean message authorization ở mục 9, không đăng ký đồng thời hai beans cùng vai trò. Trong source thật phải có imports đầy đủ, bean/service hiện thực, version API tương ứng và integration tests.

Cách đọc rule:

1. SUBSCRIBE `/topic/orders/2002` được kiểm tra ACL bằng `orders.canSubscribe(Alice, 2002)`.
2. SEND `/topic/orders/2002` **không** match subscription-specific rule; bị fallback deny MESSAGE.
3. SUBSCRIBE malformed path bị deny.
4. SEND `/app/orders.lookup` vẫn cần service-level check theo order ID trong payload.

### 11.4. Kiểm tra quyền ở thời điểm nào?

Dynamic authorization trên SUBSCRIBE diễn ra lúc **đăng ký**. Nếu order 2002 đổi owner hoặc user mất membership 5 phút sau, subscription có thể vẫn tồn tại. Tùy mức độ nhạy cảm, cần:

- Thu hồi/hủy subscription hoặc đóng WebSocket khi quyền thay đổi.
- Kiểm tra quyền ngay trước khi publisher phát dữ liệu.
- Chọn user-specific destinations thay vì public topic chứa object IDs.
- Dùng broker/tenant isolation khi cần.
- Có audit và integration tests cho role/ownership changes giữa chừng.

**Subscription authorization không phải biện pháp đảm bảo quyền vĩnh viễn.**

## 12. @MessageMapping: kiểm tra quyền nghiệp vụ sau SEND

### 12.1. Handler nhận Principal từ server

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

record OrderLookupCommand(long orderId) {}
record OrderView(long orderId, String state) {}

interface OrderQueryService {
    // Implementation kiểm tra user/tenant/ownership.
    OrderView findVisibleOrder(String username, long orderId);
}

@Controller
class OrderRealtimeController {

    private final OrderQueryService orders;
    private final SimpMessagingTemplate messaging;

    OrderRealtimeController(
        OrderQueryService orders,
        SimpMessagingTemplate messaging
    ) {
        this.orders = orders;
        this.messaging = messaging;
    }

    @MessageMapping("/orders.lookup")
    void lookup(@Payload OrderLookupCommand command, Principal principal) {
        // Principal được xác thực server-side, không từ payload.
        String username = principal.getName();

        // Service phải từ chối khi order không thuộc quyền username.
        OrderView result = orders.findVisibleOrder(
            username,
            command.orderId()
        );

        messaging.convertAndSendToUser(
            username,
            "/queue/order-results",
            result
        );
    }
}
~~~

Mã dùng Java records (phù hợp Java 17+); `OrderQueryService` là interface minh họa. Controller chỉ xử lý sau khi message được message authorization cho phép và principal đã được thiết lập.

### 12.2. Không tin username/tenantId/role từ client

Phản ví dụ:

~~~json
{
  "orderId": 2002,
  "username": "bob",
  "role": "ADMIN",
  "tenantId": "other-tenant"
}
~~~

Alice có thể tự gửi payload như vậy. Tầng service phải xác định danh tính từ `Principal`/`Authentication`, tra đúng order và tenant từ dữ liệu server-side, rồi quyết định cho/không cho. Không sử dụng `username` trong JSON để chọn người gửi hoặc người nhận mà thiếu kiểm tra.

### 12.3. Service object ACL

Pseudocode:

~~~java
Order order = ordersRepository.findById(orderId)
    .orElseThrow(NotFoundException::new);

if (!order.tenantId().equals(currentTenantId(principal))
        || !order.canBeViewedBy(principal)) {
    throw new AccessDeniedException("Forbidden");
}

return new OrderView(order.id(), order.state());
~~~

Nếu một user có quyền SEND `/app/orders.lookup` nhưng không có quyền với order cụ thể, service phải từ chối **trước khi** server phát bất kỳ dữ liệu riêng nào. Khi xử lý bất đồng bộ, cần đảm bảo publish xảy ra sau cả authorization và transaction checks.

### 12.4. Method security có vai trò nhưng không thay matcher

`@PreAuthorize`/method security có thể tăng cường quyền tại service khi thiết kế đúng, nhưng không tự thay:

- CONNECT authentication và CSRF.
- Quyền SUBSCRIBE vào private broker destinations.
- Chặn direct SEND tới broker.
- Origin validation.
- Outbound routing và revocation.

Các lớp hoạt động cộng dồn.

## 13. CONNECT CSRF: cấp và truyền token đúng nơi

### 13.1. Token trong CONNECT không phải token của HTTP Upgrade

Browser API:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");
~~~

không có tùy chọn đặt arbitrary HTTP `X-CSRF-TOKEN` header. Với `@stomp/stompjs`, dùng `connectHeaders` để truyền native STOMP header:

~~~text
CONNECT
X-CSRF-TOKEN:<valid-session-token>

^@
~~~

Đây là token được Spring Messaging kiểm tra ở CONNECT khi bảo vệ được bật, không phải token tự động được dùng cho mọi SEND.

### 13.2. HTTP endpoint cấp CSRF token

Ứng dụng có thể tạo controller:

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

`/api/csrf` là endpoint **do ứng dụng tạo** chứ không mặc định được Spring Boot phát ra. Trong ví dụ session-based, nó phải được xác thực, trả token từ đúng session, có CORS HTTP phù hợp cho frontend khác origin và không để shared proxy cache hoặc log token.

Các cấu hình `CsrfTokenRepository`, deferred/masked tokens và `CsrfTokenRequestHandler` có thể ảnh hưởng token được expose so với expected token được messaging layer kiểm tra; phải test thực bằng STOMP client cùng phiên.

### 13.3. JavaScript client: chỉ sau CONNECTED mới SEND/SUBSCRIBE

~~~javascript
import { Client } from "@stomp/stompjs";

async function connectRealtime() {
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

    // Chỉ đăng ký/gửi lệnh khi nhận CONNECTED.
    onConnect: () => {
      client.subscribe("/user/queue/order-results", message => {
        console.log("Kết quả:", message.body);
      });

      client.publish({
        destination: "/app/orders.lookup",
        body: JSON.stringify({ orderId: 1001 })
      });
    },

    onStompError: frame => {
      console.error("STOMP bị từ chối:", frame.headers.message);
    },

    onWebSocketClose: event => {
      console.log("WebSocket đóng:", event.code);
    }
  });

  client.activate();
  return client;
}
~~~

`connectHeaders` là STOMP native headers; HTTP handshake không tự có `X-CSRF-TOKEN` tương ứng. Trong session-based model, browser cookie gửi trên handshake theo cookie policy. Nếu frontend và API khác origin, CORS của HTTP `/api/csrf` cũng phải đúng.

### 13.4. Thứ tự subscribe và send trong client cũng quan trọng

Trong ví dụ, client đăng ký `/user/queue/order-results` rồi mới gửi lookup command. Dù làm vậy, broker/client vẫn xử lý bất đồng bộ: ứng dụng có thể cần `RECEIPT` hoặc một protocol acknowledgment phù hợp nếu phải chắc chắn subscription đã được server đăng ký trước khi publish dữ liệu.

Một STOMP `RECEIPT` có semantics xác nhận frame đã được phía nhận xử lý theo protocol/implementation, **không thay** nghiệp vụ đã commit hoặc quyền trên object. Không dùng thời điểm một callback ở frontend làm bằng chứng server đã cấp quyền subscribe nếu chưa có test và quan sát behavior thực.

## 14. Token-authentication tại CONNECT: không thay CSRF hoặc MESSAGE ACL

### 14.1. Khi HTTP handshake chưa có principal

Một SPA có thể chỉ giữ JWT bearer trong JavaScript. Browser WebSocket constructor không cho thêm arbitrary HTTP Authorization; token sẽ được gửi qua native STOMP CONNECT:

~~~text
CONNECT
Authorization:Bearer <access-token>
X-CSRF-TOKEN:<csrf-token-if-required-by-policy>

^@
~~~

Spring **không** mặc định coi STOMP `Authorization` header là authentication đã xác minh. Cần custom `ChannelInterceptor` có token verifier, gọi `StompHeaderAccessor#setUser(Authentication)` sau khi xác minh token và bảo đảm interceptor chạy **trước** security interceptors cần principal.

### 14.2. Skeleton xác thực CONNECT

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.core.Authentication;

interface VerifiedTokenService {
    Authentication verifyBearer(String nativeAuthorization);
}

final class ConnectAuthenticationInterceptor implements ChannelInterceptor {

    private final VerifiedTokenService tokens;

    ConnectAuthenticationInterceptor(VerifiedTokenService tokens) {
        this.tokens = tokens;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message, StompHeaderAccessor.class
            );

        if (accessor != null
                && StompCommand.CONNECT.equals(accessor.getCommand())) {
            Authentication auth = tokens.verifyBearer(
                accessor.getFirstNativeHeader("Authorization")
            );

            if (auth == null || !auth.isAuthenticated()) {
                throw new org.springframework.security
                    .authentication.BadCredentialsException(
                        "Invalid STOMP credentials"
                    );
            }

            accessor.setUser(auth);
        }

        return message;
    }
}
~~~

Đây là **skeleton giải thích**, không phải token verifier hoàn chỉnh: production phải kiểm tra chữ ký, issuer, audience, expiry, token type/scopes, revocation, native header duplicates, error handling và giới hạn tài nguyên. `@EnableWebSocketSecurity` không tự bỏ CSRF CONNECT khi thấy JWT; thiết kế bearer-only cần CSRF strategy được hỗ trợ và kiểm thử theo framework version/threat model.

### 14.3. Authentication ở CONNECT và authorization ở SEND/SUBSCRIBE độc lập

Ngay cả khi interceptor xác thực được Alice:

~~~text
CONNECT Authorization:Bearer validAliceToken -> Principal Alice
SEND /app/orders.lookup                  -> kiểm tra MESSAGE + role + order ACL
SUBSCRIBE /topic/admin                   -> kiểm tra SUBSCRIBE + ADMIN
SEND /topic/public                       -> chặn direct broker publish
~~~

Một verified token không thay quyền đối với order của Bob; cũng không thay việc chặn direct broker SEND.

### 14.4. Không cho SEND/SUBSCRIBE trước verified CONNECT

Trong token-only model, HTTP handshake có thể được cho phép với phạm vi hẹp vì token chưa tới. Nhưng server phải:

- Chặn mọi business MESSAGE/SUBSCRIBE khi principal chưa được xác thực.
- Xác thực bearer trên CONNECT, không tin STOMP `login`/`userId` tự khai.
- Giữ Origin allowlist hẹp và giới hạn anonymous handshake/CONNECT rate.
- Xử lý CSRF CONNECT theo policy được chọn, không disable tùy tiện.
- Kiểm tra thứ tự custom interceptor với `@EnableWebSocketSecurity` bằng integration tests.

## 15. Outbound messages không tự được bảo vệ như inbound

Spring Security Messaging tập trung bảo vệ **client inbound channel**. Dữ liệu server gửi ra có thể đi qua broker/outbound infrastructure khác. Nếu server tự publish:

~~~java
messaging.convertAndSend("/topic/public", secretOrderDetails);
~~~

thì rule chặn client SEND `/topic/public` không tự sửa lỗi. Một user được subscribe public có thể nhận dữ liệu riêng tư đã bị server phát nhầm.

Thiết kế outbound phải xét:

1. Publisher chỉ phát dữ liệu đã được phép, không lộ field không cần.
2. Chọn đúng destination: public, tenant, order-specific hay user-specific.
3. Subscriber authorization tương ứng mức riêng tư của destination.
4. Quyền thay đổi sau subscribe phải được phản ánh trước khi phát dữ liệu tiếp.
5. External broker relay/cluster có TLS, credentials, ACL và routing isolation.
6. Số sessions của một username và multi-node propagation.
7. Không log raw payload/token nhạy cảm ở broker hoặc tracing.

**Kiểm tra SEND, kiểm tra SUBSCRIBE và kiểm tra publish là ba trách nhiệm khác nhau.**

## 16. Logout, role revocation và kết nối dài hạn

### 16.1. Một CONNECT hợp lệ có thể tồn tại lâu

Giả sử Alice CONNECTED lúc 09:00. Đến 10:00:

- Alice logout HTTP.
- JWT hết hạn.
- Role ADMIN bị thu hồi.
- Alice rời tenant hoặc room.
- Order chuyển sang user khác.

Không được mặc định Spring tự đóng tất cả WebSocket connections ngay khi HTTP session thay đổi, hay `Authentication` đang gắn với socket tự cập nhật authorities sau mỗi thay đổi.

### 16.2. Tách chính sách lifecycle

| Sự kiện | CONNECT đã qua có còn ý nghĩa gì? | Điều cần làm |
| --- | --- | --- |
| Logout/session invalidation | Không được xem là quyền vĩnh viễn | Close/expire/revalidate socket và subscriptions |
| JWT hết hạn | Token từng hợp lệ không bảo đảm vẫn hợp lệ | Bound connection TTL hoặc reconnect/revalidate |
| Role USER → không còn USER | Matcher có thể nhìn authorities cũ | Thu hồi và kiểm tra quyền hiện thời |
| Rời room/tenant | SUBSCRIBE từng được duyệt có thể vẫn còn | Hủy subscription/stop publish/recheck ACL |
| Đổi owner order | Topic dynamic ACL cũ có thể lỗi thời | Kiểm tra trước publish và thu hồi liên quan |
| Nhiều tab/devices | Có nhiều sessions cùng principal | Thu hồi tất cả sessions đúng phạm vi |
| Multi-node broker | Registry và ACL thay đổi giữa nodes | Đồng bộ session/ACL và routing |

CONNECT CSRF và authentication diễn ra tại thời điểm thiết lập; message authorization và business ACL phải còn phù hợp khi dữ liệu được xử lý hoặc phát.

### 16.3. Những rule “authenticated()” cũ có thể chưa đủ

Principal trên WebSocket session có thể chứa authorities tại thời điểm handshake. Với nghiệp vụ nhạy cảm, không chỉ dựa vào role snapshot đó nếu quyền có thể thay đổi trong thời gian dài. Hãy cân nhắc kiểm tra quyền hiện tại trong service và cơ chế revoke connection/subscription.

Spring Session có khả năng hỗ trợ session lifecycle WebSocket ở những cấu hình tương ứng; không được khẳng định mọi ứng dụng tự đóng socket khi logout nếu chưa cấu hình và test.

## 17. SockJS fallback: HTTP transport và STOMP authorization vẫn khác nhau

Nếu bật:

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins("https://app.example.com")
    .withSockJS();
~~~

SockJS có thể chọn WebSocket hoặc HTTP XHR streaming/polling.

### 17.1. SockJS có HTTP requests riêng

Ví dụ các URL có thể gặp:

~~~text
GET  /ws/info
GET  /ws/<server-id>/<session-id>/websocket
POST /ws/<server-id>/<session-id>/xhr_send
GET  /ws/<server-id>/<session-id>/xhr_streaming
...
~~~

Trong XHR fallback, HTTP CORS và đôi khi HTTP CSRF có thể chặn requests **trước khi** STOMP CONNECT đến messaging pipeline. Native WebSocket không có Fetch CORS preflight giống XHR.

**Phân biệt:**

- HTTP `POST /ws/.../xhr_send` 403 có thể là Servlet `CsrfFilter`, HTTP auth hoặc gateway.
- HTTP 101 rồi STOMP `CONNECT` bị từ chối có thể là CSRF CONNECT/authentication.
- STOMP `CONNECTED` rồi SEND/SUBSCRIBE bị từ chối là message authorization hoặc business ACL.

### 17.2. Không sửa nhầm tầng

Nếu SockJS XHR POST gặp HTTP CSRF 403, không tắt CSRF cho mọi REST POST/PUT. Nếu cần ngoại lệ, chỉ giới hạn những SockJS transport URLs đúng theo ứng dụng và **giữ CSRF tại STOMP CONNECT**.

Nếu browser báo CSP `connect-src` hoặc `X-Frame-Options`/CSP `frame-ancestors` ở iframe fallback, không nới security headers toàn hệ thống chỉ để “được CONNECTED”. Hãy kiểm tra transport yêu cầu và alternative hiện đại.

### 17.3. Native headers vẫn là STOMP headers

Một `@stomp/stompjs` client dùng SockJS truyền `connectHeaders` bên trong STOMP frame, **không** tự thêm HTTP Authorization/CSRF headers vào tất cả XHR fallback requests. Thiết kế cookie/HTTP transport authentication vẫn phải nhất quán với server HTTP security chains.

## 18. WebFlux native: không tự có các command STOMP

Spring WebFlux native WebSocket cung cấp `WebSocketHandler` và `WebSocketSession` cho text/binary frames. Một ứng dụng WebFlux chỉ trao đổi JSON **không mặc định có**:

- STOMP CONNECT/SEND/SUBSCRIBE.
- `@EnableWebSocketMessageBroker` và `@EnableWebSocketSecurity` như trên Servlet.
- `CsrfChannelInterceptor` cho STOMP CONNECT.
- `simpSubscribeDestMatchers` để tự phân quyền mọi JSON topic.

### 18.1. Bảo vệ HTTP handshake bằng ServerHttpSecurity

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveHandshakeSecurity {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/ws").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Cấu hình này yêu cầu principal tại HTTP handshake, **không** tự kiểm tra JSON messages hay WebSocket Origin. Nếu hệ thống muốn first-message authentication, HTTP handshake policy và per-message state machine phải được thiết kế khác.

### 18.2. Native message authorization trong handler

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface ReactiveRealtimeService {
    // Implementation parse command, phân biệt subscribe/send,
    // kiểm tra quyền theo principal/object/tenant và xử lý message.
    Mono<Void> authorizeAndHandle(
        Principal principal,
        String payload
    );
}

class SecureReactiveHandler {

    static WebSocketHandler create(ReactiveRealtimeService service) {
        return session -> session.getHandshakeInfo()
            .getPrincipal()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")))
            .flatMap(principal ->
                session.receive()
                    .concatMap(frame ->
                        service.authorizeAndHandle(
                            principal,
                            frame.getPayloadAsText()
                        ))
                    .then()
            );
    }
}
~~~

Đây là skeleton, chưa có handler mapping, outbound sending, backpressure, schema validation hoặc limit handling. Nếu ứng dụng định nghĩa các command JSON `connect`/`publish`/`subscribe` của riêng mình, phải tự phân quyền từng command tương tự những nguyên tắc đã trình bày, **nhưng không gọi đó là STOMP Security mặc định**.

## 19. Ma trận kiểm thử: CONNECT, SEND, SUBSCRIBE phải được test riêng

### 19.1. Handshake và CONNECT

| Ca | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| H1 | HTTP handshake Origin app + session Alice hợp lệ | Transport được phép theo HTTP/Origin policy |
| H2 | Origin evil + **session Alice hợp lệ** | Origin validation từ chối |
| H3 | HTTP handshake không cookie với `/ws authenticated()` | HTTP auth từ chối |
| C1 | Handshake Alice, CONNECT có CSRF token đúng | CONNECTED theo policy |
| C2 | Handshake Alice, CONNECT thiếu CSRF token | CONNECT bị từ chối nếu CSRF yêu cầu |
| C3 | Handshake Alice, CONNECT token sai/khác phiên | CONNECT bị từ chối theo repository/context |
| C4 | Bearer-only CONNECT sai/expired token | CONNECT bị từ chối, không gắn principal |
| C5 | STOMP header `login:admin` từ user thường | Không tự cấp principal ADMIN |

Để chứng minh H2 là Origin guard, phải dùng **cùng session authenticated** khi đổi Origin. Nếu request không cookie nhận HTTP 401, chưa chứng minh Origin validation đã hoạt động.

### 19.2. SEND

| Ca | Principal | Frame | Kỳ vọng |
| --- | --- | --- | --- |
| M1 | Alice ROLE_USER | `SEND /app/orders.lookup` order 1001 của Alice | Message được xử lý; service cho phép |
| M2 | Alice ROLE_USER | `SEND /app/orders.lookup` order 2002 của Bob | Service từ chối, không phát dữ liệu |
| M3 | Alice ROLE_USER | `SEND /topic/public` | Message authorization từ chối |
| M4 | Alice ROLE_USER | `SEND /topic/admin` | Từ chối dù Alice đã CONNECTED |
| M5 | User không có role USER | `SEND /app/orders.lookup` | Message authorization từ chối |
| M6 | Alice | `SEND /app/unknown` | Fallback deny |
| M7 | Alice, payload tự khai `role:ADMIN` | Lệnh yêu cầu admin | Không nâng role từ client-provided data |
| M8 | Alice, payload quá lớn/malformed | Một command được cho SEND | Validation/limits từ chối an toàn |

### 19.3. SUBSCRIBE

| Ca | Principal | Frame | Kỳ vọng |
| --- | --- | --- | --- |
| S1 | Alice authenticated | `SUBSCRIBE /topic/public` | Cho theo policy |
| S2 | Alice ROLE_USER | `SUBSCRIBE /topic/admin` | Deny |
| S3 | Admin ROLE_ADMIN | `SUBSCRIBE /topic/admin` | Cho nếu còn điều kiện phù hợp |
| S4 | Alice | `SUBSCRIBE /app/orders.lookup` | Deny |
| S5 | Alice | `SUBSCRIBE /user/queue/order-results` | Cho theo policy; routing đúng user |
| S6 | Alice | `SUBSCRIBE /topic/orders/1001` | Cho nếu ACL xác nhận Alice sở hữu order |
| S7 | Alice | `SUBSCRIBE /topic/orders/2002` | Deny nếu order thuộc Bob |
| S8 | Alice bị thu hồi quyền sau subscription | Nhận MESSAGE tiếp theo | Không được nhận dữ liệu riêng trái quyền |
| S9 | Alice | Malformed private topic path | Deny, không regex prefix bypass |

### 19.4. Kiểm tra “không có dữ liệu” mới quan trọng

Khi test một lệnh trái phép, cần xác nhận:

1. User không nhận được data của user khác qua bất kỳ subscription nào.
2. Không có side effect thay đổi order/message của user khác.
3. Không có broker publish xảy ra trước khi service từ chối.
4. Audit ghi principal thực, không ghi role/userId do client tự khai.
5. Một client khác đã subscribe đúng không bị ảnh hưởng ngoài ý muốn bởi lỗi của client đang test.
6. Quyền bị thu hồi có hiệu lực với connections đang mở theo policy đã thiết kế.

Một STOMP `ERROR` sau khi dữ liệu đã bị phát nhầm **không phải** kết quả an toàn.

## 20. Kiểm thử tích hợp trên Servlet/STOMP

### 20.1. Công cụ kiểm thử và phạm vi

| Công cụ | Có ích cho | Không thay thế |
| --- | --- | --- |
| `MockMvc` | HTTP login, CORS/CSRF token endpoint, handshake route security matchers | STOMP CONNECT/SEND/SUBSCRIBE thực |
| `WebSocketStompClient` + test server | Handshake thật, STOMP frames, principal, subscriptions, ERROR/close | Browser SOP/CSP/cookie-policy edge cases |
| Browser DevTools | Origin, Cookie, `101`, Frames/Messages, CSP/TLS errors | Server-side ACL decision assertions |
| Unit test `AuthorizationManager` | Rule ordering, principal/destination decisions | Wiring và actual broker behavior |
| Service tests | Object/tenant ACL, side effects, output | WebSocket handshake/CSRF |
| Broker/integration tests | Routing, user destinations, multi-node behavior | Token verifier correctness nếu không được test riêng |

### 20.2. Khởi tạo STOMP test client

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

// Skeleton chuẩn bị integration test; cần test server và assertions.
WebSocketStompClient client = new WebSocketStompClient(
    new StandardWebSocketClient()
);

WebSocketHttpHeaders httpHeaders = new WebSocketHttpHeaders();
httpHeaders.setOrigin("https://app.example.com");
httpHeaders.add(
    HttpHeaders.COOKIE,
    "SESSION=" + testSessionCookie
);

StompHeaders connectHeaders = new StompHeaders();
connectHeaders.add(testCsrfHeaderName, testCsrfToken);

// client.connectAsync(uri, httpHeaders, connectHeaders, sessionHandler);
// Chờ CONNECTED/ERROR/close trước khi SEND/SUBSCRIBE.
~~~

Các biến test là placeholders phải được test setup cấp từ **cùng HTTP session**. Đoạn code không chạy độc lập: cần start server random port, session handler, message converters, asynchronous assertions, error callbacks và timeout. Overload của STOMP client có thể khác theo Spring version.

### 20.3. Kịch bản kiểm thử an toàn

~~~text
Given:
  - User Alice ROLE_USER, user Bob ROLE_USER, user Admin ROLE_ADMIN.
  - Alice sở hữu order 1001, Bob sở hữu order 2002.
  - /ws chỉ cho Origin https://app.example.com.
  - @EnableWebSocketSecurity và message AuthorizationManager đang bật.
  - CSRF token được cấp cho session Alice.

Connect:
  1) Kết nối WebSocket với Origin app và Cookie Alice.
  2) STOMP CONNECT native CSRF token đúng.
  3) Đợi CONNECTED.

SEND:
  4) Alice SEND /app/orders.lookup orderId=1001.
  5) Assert nhận đúng order qua /user/queue/order-results.
  6) Alice SEND /app/orders.lookup orderId=2002.
  7) Assert không có dữ liệu Bob và không side effect.
  8) Alice SEND /topic/public trực tiếp.
  9) Assert broker không phát message do Alice giả mạo.

SUBSCRIBE:
  10) Alice SUBSCRIBE /topic/public -> cho phép.
  11) Alice SUBSCRIBE /topic/admin -> deny.
  12) Alice SUBSCRIBE /topic/orders/2002 -> deny.
  13) Admin SUBSCRIBE /topic/admin -> cho phép nếu policy.
  14) Thu hồi membership Alice, kiểm tra subscription/outputs cũ.

Negative CONNECT:
  15) Dùng cùng cookie nhưng CONNECT thiếu CSRF.
  16) Dùng token sai/khác phiên, assert không CONNECTED.
~~~

Khi kiểm tra unauthorized SUBSCRIBE, **không chỉ chờ một ERROR frame**: tùy policy/broker/client, behavior từ chối có thể khác. Cần assert subscription trái quyền không thực sự nhận protected MESSAGE và không được tạo state trái phép.

### 20.4. Unit test rule ordering

Một test chỉ nhìn HTTP status sẽ bỏ qua lỗi nghiêm trọng:

~~~java
// Phản ví dụ:
.simpDestMatchers("/topic/**").authenticated()
.simpTypeMatchers(SimpMessageType.MESSAGE).denyAll()
~~~

Hãy test `MESSAGE /topic/admin` dưới principal USER và khẳng định **deny**. Nếu rule trên vô tình cho phép, cần chuyển sang `simpSubscribeDestMatchers` cho subscription allowlist và giữ deny MESSAGE fallback.

Kiểm tra cả `SUBSCRIBE /app/orders.lookup`; rule cho SEND application destination không được mở subscription vào đó.

## 21. Troubleshooting: tìm đúng lớp từ chối

| Triệu chứng | Nơi cần xem | Gợi ý điều tra |
| --- | --- | --- |
| Không có HTTP 101 | TLS/CSP/Origin/HTTP auth/proxy | Header Origin, Cookie, `connect-src`, Upgrade |
| HTTP 101 nhưng không CONNECTED | CSRF CONNECT, principal, token-auth interceptor | Native CONNECT headers, security logs |
| CONNECTED nhưng SEND `/app/**` bị deny | `SimpMessageType.MESSAGE`, destination/role | Kiểm tra matcher order/authorities |
| CONNECTED nhưng SUBSCRIBE `/topic/admin` bị deny | `SUBSCRIBE` rule | Kiểm tra role và destination policy |
| USER SEND `/topic/admin` và broker phát | Matcher destination-only quá rộng | Chặn client MESSAGE tới broker |
| User thấy data của order khác | Object ACL hoặc topic/subscription policy thiếu | Test owner/tenant, outbound routing |
| Client tự khai `login:admin` nhưng không nâng quyền | Đây không phải authentication mặc định | Principal HTTP hoặc verified CONNECT bearer |
| Token CSRF ở HTTP GET nhưng CONNECT vẫn bị từ chối | Token không nằm trong native CONNECT | Dùng `connectHeaders` |
| CORS HTTP token endpoint sai | REST/XHR CORS | Cấu hình riêng cho `/api/csrf` |
| SockJS XHR POST 403 trước CONNECT | HTTP CSRF/Origin/CORS/proxy | Kiểm tra transport paths |
| Native WebSocket từ origin lạ mở được | WebSocket Origin allowlist quá rộng | Siết `setAllowedOrigins` |
| Role thay đổi, subscription cũ vẫn nhận data | Lifecycle và revalidation thiếu | Thu hồi subscription/connection, check lúc publish |
| Server phát secret ra public topic | Outbound routing/data leak | Sửa publisher; inbound rule không đủ |
| Principal null trong message handler | HTTP handshake anonymous hoặc token CONNECT interceptor sai | Kiểm tra session/auth và interceptor order |
| `@Async` mất principal | SecurityContext không propagate | Truyền principal/context an toàn |
| `simpDestMatchers` mở quyền SUBSCRIBE ngoài ý định | Matcher không ràng buộc type | Đặt `simpSubscribeDestMatchers("/app/**").denyAll()` trước |
| Bad destination path lọt ACL | Parse/pattern quá rộng | Anchor regex; test malformed/encoded paths |
| Nhiều server nodes nhận message sai user | Broker routing/user registry không nhất quán | Kiểm tra cluster, session affinity |
| Outbound sau logout vẫn nhận | Token/session chính chỉ kiểm ở CONNECT | Revalidate/close old sockets |
| WebFlux native không có CONNECT/SUBSCRIBE matcher | Dùng nhầm Servlet STOMP API | Tự xây per-message security cho Reactive |

### 21.1. Quy trình chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["Client báo lỗi realtime"] --> B{"HTTP handshake thành công?"}
    B -- "Không" --> C["HTTP auth, Origin, Cookie, CSP, TLS, Gateway"]
    B -- "Có" --> D{"Nhận STOMP CONNECTED?"}
    D -- "Không" --> E["CSRF CONNECT, principal, token verifier"]
    D -- "Có" --> F{"Frame nào bị từ chối?"}
    F -- "SEND" --> G["MESSAGE matcher, role, service object ACL"]
    F -- "SUBSCRIBE" --> H["SUBSCRIBE matcher, object/tenant ACL"]
    F -- "Không, nhưng data sai" --> I["Publisher/outbound routing, lifecycle/revocation"]
~~~

Đừng sửa lỗi SEND hoặc SUBSCRIBE bằng cách tắt CONNECT CSRF. Đừng sửa lỗi CONNECT bằng cách mở mọi broker destinations. Xác định chính xác giai đoạn và nguồn bị từ chối.

## 22. Checklist triển khai và đánh giá bảo mật

- [ ] Phân biệt HTTP `GET /ws` với STOMP `CONNECT`, `SEND`, `SUBSCRIBE`.
- [ ] HTTP handshake có authentication phù hợp và WebSocket Origin allowlist hẹp.
- [ ] STOMP CONNECT có CSRF token hợp lệ khi `@EnableWebSocketSecurity` yêu cầu.
- [ ] Nếu bearer ở CONNECT, verifier và `setUser(Authentication)` chạy trước message authorization, có CSRF strategy rõ.
- [ ] Không tin STOMP `login`/`passcode`, `userId`/`role`/`tenantId` do client tự khai.
- [ ] `AuthorizationManager<Message<?>>` có rules riêng cho MESSAGE/SEND và SUBSCRIBE.
- [ ] Không nhầm `StompCommand.SEND` với `SimpMessageType.MESSAGE`.
- [ ] `nullDestMatcher` có policy principal cho control messages; không coi đó là toàn bộ CONNECT CSRF.
- [ ] `simpSubscribeDestMatchers("/app/**").denyAll()` đứng trước destination-only SEND allows nếu cần.
- [ ] Không có matcher rộng `/topic/**` cho cả SEND và SUBSCRIBE.
- [ ] Các application SEND commands có role/scope và payload validation đúng.
- [ ] Client không SEND trực tiếp vào broker destinations cần server kiểm soát.
- [ ] Private subscriptions có object/tenant ACL, không chỉ `authenticated()`.
- [ ] Service kiểm tra principal đối với order/room/tenant ID trước khi xử lý.
- [ ] User destinations và `convertAndSendToUser` route đúng principal/session, kể cả multi-tab.
- [ ] Server không publish private data lên public topic hoặc sai tenant.
- [ ] Role/membership/logout/token expiry có cơ chế close/revalidate và hủy subscriptions.
- [ ] SockJS HTTP fallback, nếu dùng, có HTTP CORS/CSRF paths phù hợp.
- [ ] HTTP CSRF và STOMP CONNECT CSRF không bị tắt toàn bộ vì lỗi một transport.
- [ ] Browser CSP `connect-src`, TLS/WSS, HSTS, HTTP firewall được cấu hình đúng trách nhiệm.
- [ ] Có rate limits, message size/subscription count quotas và idle timeout.
- [ ] Log/audit redact cookie, bearer token, CSRF token và payload nhạy cảm.
- [ ] Integration test CONNECT hợp lệ nhưng SEND/SUBSCRIBE sai quyền.
- [ ] Negative tests assert **không rò rỉ dữ liệu và không có side effects**.
- [ ] Với WebFlux native, có per-message authentication/authorization riêng, không giả định dùng được annotation Servlet.

## 23. Câu hỏi vận dụng và lời giải

**Tình huống 1 — CONNECTED có nghĩa gì?** Alice nhận STOMP CONNECTED. Có được quyền nghe `/topic/admin` chưa?

**Đáp án:** Chưa. CONNECT chỉ cho phép phiên STOMP tồn tại. SUBSCRIBE `/topic/admin` cần quyền ADMIN hoặc policy tương ứng.

**Tình huống 2 — SEND được Spring gọi là gì?** Tại sao security rule lại sử dụng `SimpMessageType.MESSAGE` thay vì một `SimpMessageType.SEND`?

**Đáp án:** Spring Messaging ánh xạ STOMP SEND thành inbound message type MESSAGE. Catch-all deny SEND phải xét MESSAGE.

**Tình huống 3 — Chỉ có HTTP SecurityFilterChain.** `GET /ws` yêu cầu authenticated. Có tự chặn client `SEND /topic/admin` không?

**Đáp án:** Không. HTTP filter bảo vệ handshake; message authorization phải chặn SEND vào broker.

**Tình huống 4 — Token CSRF đúng.** Alice có token đúng trong CONNECT. Có thể đọc order 2002 của Bob không?

**Đáp án:** Không. CSRF chứng minh điều kiện CONNECT, không cấp quyền truy cập object. Service/subscription ACL phải từ chối.

**Tình huống 5 — Destination-only matcher.** Rule `simpDestMatchers("/topic/**").authenticated()` đứng trước deny MESSAGE. Nguy cơ gì?

**Đáp án:** Một MESSAGE từ STOMP SEND tới broker topic có thể match rule rộng và được phép. Dùng subscription-specific matcher và deny direct broker SEND.

**Tình huống 6 — Rule cho /app.** `simpDestMatchers("/app/orders.lookup").hasRole("USER")` có chắc không cho client SUBSCRIBE `/app/orders.lookup` không?

**Đáp án:** Không nếu matcher destination không ràng buộc type. Đặt `simpSubscribeDestMatchers("/app/**").denyAll()` trước và test.

**Tình huống 7 — Authenticated private topic.** Mọi user đã đăng nhập được SUBSCRIBE `/topic/orders/*`. Có an toàn không?

**Đáp án:** Không nếu mỗi topic chứa dữ liệu riêng. Cần kiểm tra principal có quyền với đúng order/tenant tại SUBSCRIBE và/hoặc trước publish.

**Tình huống 8 — User destination.** Server dùng `convertAndSendToUser("alice", "/queue/order-results", data)`. Có tự xác minh data thuộc Alice không?

**Đáp án:** Không. Phương thức hỗ trợ routing; service phải kiểm tra business ACL trước khi gửi.

**Tình huống 9 — Browser Origin khác site.** REST CORS đã cho phép app, nhưng WebSocket bị chặn. Có nên chỉ sửa REST `CorsFilter`?

**Đáp án:** Không. Native WebSocket Origin policy nằm ở WebSocket handshake; phải kiểm tra `setAllowedOrigins` và HTTP auth/cookie.

**Tình huống 10 — HTTP 101 rồi STOMP ERROR.** Một client gọi CONNECT thiếu CSRF và nhận ERROR, có phải SEND bị từ chối không?

**Đáp án:** Chưa tới SEND. Đây là vấn đề CONNECT/CSRF/principal, phải kiểm thử riêng.

**Tình huống 11 — Token chỉ ở STOMP CONNECT.** HTTP `/ws` bắt buộc authenticated nhưng client không có cookie/HTTP bearer. Vì sao HTTP 401 trước CONNECT?

**Đáp án:** HTTP auth chạy trước messaging. Cần chọn kiến trúc session inheritance hoặc handshake hẹp + verified CONNECT token cùng policy CSRF rõ.

**Tình huống 12 — Username trong payload.** Alice gửi `{"username":"bob"}` để gửi lệnh/nhận message thay Bob. Server có được đổi principal không?

**Đáp án:** Không. Principal lấy từ authentication đã xác minh, không lấy từ payload/native headers tùy ý.

**Tình huống 13 — Gửi giả notification.** Một client `SEND /topic/public` nhưng broker cho publish. Lớp nào bị thiếu?

**Đáp án:** Message authorization cho MESSAGE/SEND vào broker destinations. Chặn direct publish, bắt client đi qua `/app/**` handler/service.

**Tình huống 14 — Role đã thu hồi.** Alice từng SUBSCRIBE private order thành công, sau đó mất quyền nhưng vẫn nhận message. Có phải CONNECT CSRF sai?

**Đáp án:** Không. Đây là lifecycle/subscription/outbound authorization. Cần revalidate hoặc thu hồi subscriptions/connection.

**Tình huống 15 — SUBSCRIBE không nhận ERROR nhưng không có message.** Có đủ chứng minh policy deny không?

**Đáp án:** Chưa. Cần test có protected message được phát thật để xác minh client trái quyền không nhận, đồng thời kiểm tra broker/subscription state phù hợp.

**Tình huống 16 — SockJS XHR POST 403.** Native WebSocket chạy được nhưng SockJS XHR POST bị từ chối. Lỗi có chắc ở message SUBSCRIBE không?

**Đáp án:** Không. HTTP CSRF/CORS/transport auth có thể chặn trước cả CONNECT. Kiểm tra đúng request và tầng security.

**Tình huống 17 — WebFlux native.** Ứng dụng chỉ có `WebSocketHandler` nhận JSON `{"action":"subscribe"}`. `simpSubscribeDestMatchers` có tự chạy không?

**Đáp án:** Không. Đó không phải Spring Servlet STOMP inbound pipeline. Handler/service Reactive phải tự phân quyền từng action/object.

**Tình huống 18 — Test deny nhưng vẫn có side effect.** Một SEND của Alice bị trả ERROR sau khi order Bob bị cập nhật. Test có pass không?

**Đáp án:** Không. Authorization phải ngăn side effect trái quyền, không chỉ sinh thông báo lỗi.

**Tình huống 19 — Public topic.** Có nên mở `permitAll()` cho `/topic/public` trong hệ thống vốn yêu cầu authenticated ở HTTP handshake/CONNECT?

**Đáp án:** Chỉ khi thiết kế thực sự cho anonymous và các lớp CONNECT/CSRF/auth có policy nhất quán. `permitAll()` ở SUBSCRIBE không tự vượt những yêu cầu trước.

**Tình huống 20 — Phân quyền theo tenant.** Alice ở tenant A dùng role USER subscribe `/topic/orders/3003` của tenant B. Role USER đã đủ chưa?

**Đáp án:** Không. Dynamic ACL phải kiểm tra tenant/ownership của order 3003, chặn cross-tenant subscription và rò rỉ outbound.

---

**Ghi nhớ:** **CONNECT, SEND và SUBSCRIBE là ba quyết định bảo mật riêng**. CONNECT xác định phiên STOMP có đủ authentication/CSRF để tham gia hay không. SEND kiểm tra client được **gửi loại lệnh nào tới destination nào**, rồi service kiểm tra quyền đối với tài nguyên thực. SUBSCRIBE kiểm tra client được **nghe dữ liệu ở topic/user destination nào**, bao gồm object/tenant ACL khi cần. Hãy dùng `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>` với matcher đúng type, đúng thứ tự và **deny-by-default**; không cho client SEND trực tiếp vào broker, không mở wildcard subscriptions chứa dữ liệu riêng, và không coi inbound policy là bảo đảm outbound/lifecycle. Với SockJS, tách HTTP transport security khỏi STOMP security; với WebFlux native, tự triển khai nguyên tắc tương đương theo protocol thực tế.
