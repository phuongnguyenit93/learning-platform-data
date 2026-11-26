# @EnableWebSocketSecurity và lớp kiểm tra message

## 1. Mục tiêu: bảo vệ từng thông điệp sau khi WebSocket đã mở

Một hệ thống giao dịch dùng Spring Security cho HTTP và Spring WebSocket/STOMP để cập nhật dữ liệu thời gian thực. Alice đã đăng nhập bằng session cookie rồi mở `wss://api.example.com/ws` từ `https://app.example.com`. Spring Security cho phép HTTP handshake và server trả `101 Switching Protocols`.

Vậy Alice có thể gửi `SEND` đến `/topic/admin` hoặc `SUBSCRIBE` vào một topic của Bob không? **Không**, nếu hệ thống được thiết kế đúng. Nhưng HTTP `SecurityFilterChain` **không tự kiểm tra quyền của từng frame STOMP** sau handshake. Đó là công việc của lớp bảo mật **message** và các kiểm tra nghiệp vụ theo tài nguyên.

Với ứng dụng **Spring WebSocket Message Broker / STOMP trên stack Servlet**, `@EnableWebSocketSecurity` là điểm cấu hình quan trọng giúp tích hợp Spring Security với **client inbound messaging channel**. Nó phối hợp với một `AuthorizationManager<Message<?>>` để đánh giá type, destination và principal của những thông điệp do client gửi.

Bài học này thuộc chương **WebSocket và STOMP** của mô-đun **SPRING_SECURITY_HTTP_PROTECTION**, nơi người học áp dụng CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session, trên Servlet và Reactive. Nội dung chính là **lớp kiểm tra message**, nhưng các ví dụ cũng chỉ ra những ranh giới HTTP handshake, CSRF tại STOMP CONNECT và bảo mật của WebFlux native WebSocket.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích `@EnableWebSocketSecurity` thiết lập message security khác `HttpSecurity` ở điểm nào.
2. Dùng `MessageMatcherDelegatingAuthorizationManager.Builder` để xây policy **deny by default**.
3. Phân biệt `CONNECT`, `MESSAGE/SEND`, `SUBSCRIBE`, `UNSUBSCRIBE`, `DISCONNECT` và loại message không có destination.
4. Chọn đúng `simpDestMatchers`, `simpSubscribeDestMatchers`, `simpTypeMatchers` và `nullDestMatcher`; hiểu tác động của thứ tự matcher.
5. Ngăn client tự phát vào broker destinations và đăng ký các topic riêng tư trái quyền.
6. Kết hợp principal kế thừa từ HTTP handshake, CSRF token tại CONNECT và authentication tùy biến tại CONNECT khi có yêu cầu đặc biệt.
7. Kiểm tra quyền theo **object ID/tenant** ở service thay vì chỉ role/destination.
8. Hiểu ranh giới bảo vệ **inbound**, rủi ro outbound và thay đổi quyền trong kết nối dài hạn.
9. Thiết kế kiểm thử integration, negative cases, sự cố SockJS, proxy và WebFlux.

Các domain, endpoint và entity trong bài là ví dụ minh họa, không phải ứng dụng hoàn chỉnh. Ví dụ hướng tới Spring Security với API `@EnableWebSocketSecurity` và cần đối chiếu phiên bản dùng trong dự án thực tế.

## 2. Threat model: ai gửi, ai nghe và ai được nhận dữ liệu?

Giả sử ứng dụng có hai người dùng Alice/Bob, một trang quản trị, và những destinations:

| Destination | Vai trò dự kiến | Client được làm gì? |
| --- | --- | --- |
| `/app/orders.lookup` | Nhận lệnh tra cứu qua `@MessageMapping` | User hợp lệ có thể `SEND`, nhưng service phải kiểm tra order ownership |
| `/app/chat.send` | Nhận lệnh gửi chat | User có quyền phòng chat mới được `SEND` |
| `/topic/public` | Phát tin chung do **server** quyết định | Client có thể `SUBSCRIBE` theo policy; không được tự `SEND` vào broker |
| `/topic/admin` | Thông báo quản trị | Chỉ admin có quyền mới được `SUBSCRIBE` |
| `/topic/orders/2002` | Cập nhật order cụ thể | Chỉ người có quyền đối với order 2002 được nghe |
| `/user/queue/order-results` | Kết quả riêng theo principal/session | User đã xác thực có thể `SUBSCRIBE` vào user destination hợp lệ |
| `/queue/**` | Broker queue destinations | Không mở wildcard cho mọi client nếu có private messages |

Ba nhóm tấn công cần quan tâm:

- **Gửi lệnh trái phép:** attacker được kết nối rồi `SEND` tới một application destination nhạy cảm hoặc trực tiếp vào broker `/topic/**`, cố giả mạo thông báo.
- **Nghe lén qua subscription:** client `SUBSCRIBE` vào `/topic/admin`, `/topic/orders/{id}` hoặc một destination khác không thuộc quyền mình.
- **Lạm dụng danh tính/dữ liệu:** client gửi `userId:"bob"`, `role:"ADMIN"` hay `orderId` của người khác trong payload và hi vọng server tin dữ liệu tự khai.

Cấu hình `@EnableWebSocketSecurity` giúp bảo vệ **những messages từ client đi vào application**, nhưng ứng dụng vẫn phải kiểm tra nghiệp vụ và đảm bảo không tự phát dữ liệu nhầm user.

### 2.1. Ranh giới kiểm soát nhiều lớp

~~~mermaid
flowchart TD
    A["Browser/STOMP client"] --> B["HTTP handshake /ws"]
    B --> C["HTTP Authentication + Origin validation"]
    C --> D["WebSocket session và Principal"]
    D --> E["STOMP CONNECT"]
    E --> F["CSRF CONNECT + message authentication/authorization"]
    F --> G{"Frame từ client"}
    G --> H["SEND /app/**"]
    G --> I["SUBSCRIBE broker/user destination"]
    H --> J["AuthorizationManager: MESSAGE + destination + role"]
    I --> K["AuthorizationManager: SUBSCRIBE + destination + role"]
    J --> L["@MessageMapping"]
    L --> M["Service: object/tenant ACL, payload validation"]
    M --> N["Server dùng SimpMessagingTemplate"]
    K --> O["Chỉ đăng ký destinations được phép"]
    N --> P["Broker → subscription/session đúng"]
    O --> P
~~~

Sơ đồ mô tả trách nhiệm logic, không mô tả mọi internal thread, interceptor hoặc đường đi của external broker. Một frame có thể bị từ chối trước khi tới handler. Đường **server → broker → client** phải được bảo vệ bằng thiết kế routing/dữ liệu và quyền subscribe, chứ không được giả định luôn đi qua cùng một inbound policy.

## 3. HTTP Security và WebSocket Message Security khác nhau

### 3.1. HTTP handshake được xử lý một lần

Browser có thể gửi:

~~~http
GET /ws HTTP/1.1
Host: api.example.com
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com
Cookie: SESSION=<session-if-allowed>
~~~

Spring Security HTTP kiểm tra session/token tại request này. Spring WebSocket endpoint còn cần xác minh Origin. Nếu được phép, server có thể trả:

~~~http
HTTP/1.1 101 Switching Protocols
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Accept: <server-generated-value>
~~~

Từ đó, WebSocket connection tồn tại và có thể mang rất nhiều STOMP frames. **HTTP `authorizeHttpRequests` không chạy lại như một HTTP request cho từng STOMP frame**.

### 3.2. STOMP CONNECT là bước thứ hai

Sau handshake, client truyền một STOMP frame:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
X-CSRF-TOKEN:<valid-token>

^@
~~~

Nếu CONNECT được chấp nhận, client có thể nhận `CONNECTED`. Sau đó client có thể gửi:

~~~text
SUBSCRIBE
id:sub-1
destination:/user/queue/order-results

^@
~~~

hoặc:

~~~text
SEND
destination:/app/orders.lookup
content-type:application/json

{"orderId":1001}
^@
~~~

Trong các ví dụ, `^@` biểu diễn byte NUL kết thúc frame STOMP. Các header trong STOMP frame **không phải** HTTP headers của GET Upgrade.

### 3.3. So sánh các lớp

| Lớp | Cấu hình Spring thường dùng | Đầu vào kiểm tra | Điều không được bảo đảm |
| --- | --- | --- | --- |
| HTTP handshake | `SecurityFilterChain` / `HttpSecurity` | URL, session/credentials, HTTP principal | Quyền gửi/đăng ký mọi STOMP destination |
| Origin ở WebSocket endpoint | `setAllowedOrigins`, `setAllowedOriginPatterns` | Origin frontend browser | Identity/role của client |
| CSRF ở STOMP CONNECT | Tích hợp Spring Security Messaging | Token CONNECT thuộc ngữ cảnh hợp lệ | Quyền truy cập mọi order/topic |
| Inbound message authorization | `@EnableWebSocketSecurity` + `AuthorizationManager<Message<?>>` | STOMP message type/destination/principal | Object ownership nếu policy chỉ xét path/role |
| Business authorization | Service, method security hoặc ACL tùy biến | Principal, action, object/tenant | Đúng routing nếu gửi broker sai destination |
| Outbound/broker | Broker config và code phát message | Destination, subscription, người nhận | Bảo mật tự động chỉ vì inbound chain đã chặn |

CORS của HTTP Fetch và CSP `connect-src` là các lớp bổ sung khác; chúng không thay thế message authorization.

## 4. Những thành phần Spring cần để thực thi message authorization

Với Spring WebSocket Messaging, các khái niệm chính là:

- `@EnableWebSocketMessageBroker`: kích hoạt phần hạ tầng STOMP message broker của Spring.
- `WebSocketMessageBrokerConfigurer`: đăng ký STOMP endpoints, application destination prefixes và broker destinations.
- `@EnableWebSocketSecurity`: tích hợp Spring Security cho inbound messaging.
- `AuthorizationManager<Message<?>>`: quyết định cấp hay từ chối quyền cho message.
- `MessageMatcherDelegatingAuthorizationManager.Builder`: xây một chuỗi matcher và quyết định tương ứng.
- `SimpMessageType`: biểu diễn loại thông điệp do STOMP mapping trong Spring, chẳng hạn `CONNECT`, `MESSAGE`, `SUBSCRIBE`.
- `MessageHeaderAccessor` / `StompHeaderAccessor`: truy cập headers, command, destination và principal của message.
- `SecurityContextChannelInterceptor` và thành phần authorization channel tương ứng: hỗ trợ xử lý security context/quyền trên inbound channel.

Trong mô hình thông thường, application cấu hình bean `AuthorizationManager<Message<?>>`. Security infrastructure do annotation thiết lập sử dụng bean đó; lập trình viên **không cần tự thêm một authorization interceptor thứ hai** chỉ để đạt cùng mục đích, vì làm vậy có thể trùng kiểm tra hoặc gây lỗi thứ tự.

### 4.1. Inbound message không đồng nghĩa outbound message

Khi client gửi `SEND` hoặc `SUBSCRIBE`, message đi vào **client inbound channel** và có thể bị kiểm tra. Khi server dùng `SimpMessagingTemplate` phát một thông báo tới broker, đó không đơn thuần là một client inbound message giống `SEND` từ browser.

Nếu server tự phát dữ liệu nhạy cảm vào `/topic/public`, Spring Security inbound policy không tự ngăn được dữ liệu bị phát nhầm. Phải thiết kế an toàn:

1. Không cho client SEND trực tiếp vào broker destinations.
2. Phân quyền SUBSCRIBE vào protected destinations.
3. Phân quyền object/tenant trước khi server phát dữ liệu.
4. Chỉ gửi đến user/session/topic thực sự được phép.
5. Khi quyền thay đổi, thu hồi hoặc revalidate subscriptions/connections theo yêu cầu.

## 5. Cấu hình STOMP endpoint và HTTP Security trước message layer

Ví dụ một ứng dụng Spring MVC/Servlet dùng session login và frontend `https://app.example.com`.

### 5.1. Đăng ký endpoint và routing

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class WebSocketEndpointConfiguration
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

**Giải thích:**

- `/ws` là HTTP handshake endpoint.
- `setAllowedOrigins` cho phép đúng browser origin `https://app.example.com`; không dùng `wss://api.example.com` làm Origin.
- `/app` là nơi client gửi command để application xử lý qua `@MessageMapping`.
- `/topic` và `/queue` là broker destinations, **không đồng nghĩa tất cả user được subscribe**.
- `/user` là user destination prefix; không tự bảo vệ object ownership.

### 5.2. HTTP SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HttpHandshakeSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurityChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/ws", "/ws/**").authenticated()
                .requestMatchers("/api/csrf").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

Ví dụ dùng session/form login. Ứng dụng thực cần user store và cấu hình login phù hợp. Nếu muốn dùng bearer token chỉ **trong STOMP CONNECT** thì HTTP handshake chưa có principal; rule `authenticated()` trên `/ws` sẽ chặn kết nối trước CONNECT. Đây là hai kiến trúc khác nhau, phải lựa chọn rõ.

Không tắt CSRF HTTP hoặc mở mọi HTTP paths chỉ để STOMP hoạt động. Nếu dùng SockJS fallback, những POST transport URLs cần chính sách CSRF HTTP cụ thể, được đánh giá riêng.

## 6. @EnableWebSocketSecurity và AuthorizationManager<Message<?>>

Phần cốt lõi của bài là định nghĩa **quy tắc truy cập inbound messages**.

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
            // Các message không có destination (CONNECT, DISCONNECT,...)
            // vẫn cần authenticated principal trong ví dụ này.
            .nullDestMatcher().authenticated()

            // Client không được SUBSCRIBE vào app destinations.
            .simpSubscribeDestMatchers("/app/**").denyAll()

            // Chỉ một số broker/user destinations được SUBSCRIBE.
            .simpSubscribeDestMatchers(
                "/topic/public",
                "/user/queue/order-results"
            ).authenticated()

            // SEND tới @MessageMapping phải có role USER.
            .simpDestMatchers("/app/orders.lookup").hasRole("USER")

            // Những MESSAGE/SUBSCRIBE còn lại bị từ chối.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()

            // Mọi loại message khác cũng bị từ chối.
            .anyMessage().denyAll()
            .build();
    }
}
~~~

### 6.1. Tại sao phải cấu hình deny by default?

Nếu không có rule cuối **`anyMessage().denyAll()`**, một policy bị bỏ sót có thể khiến các message type/destination mới không được đánh giá theo ý định. Dạng deny-by-default tạo một quy trình rõ ràng: muốn mở destination mới thì phải **thêm rule cụ thể và test case âm/dương tương ứng**.

Ví dụ, Alice gửi:

~~~text
SEND
destination:/topic/public
content-type:text/plain

Tôi là quản trị viên
^@
~~~

Rule `simpDestMatchers("/app/orders.lookup")` không match. Sau đó `simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()` bắt message `MESSAGE` và từ chối. Nhờ vậy client không tự phát thông báo lên broker.

### 6.2. Role không phải object-level permission

`hasRole("USER")` thường kiểm tra authority theo quy ước role prefix như `ROLE_USER`. Nó cho biết principal có role phù hợp, **không** cho biết user sở hữu order ID nào.

Bởi vậy, `SEND /app/orders.lookup` của Alice có thể vượt message rule, nhưng service vẫn phải từ chối payload `{"orderId":2002}` khi order 2002 thuộc Bob.

### 6.3. Nên làm gì khi có public subscription?

Nếu nghiệp vụ cho khách chưa đăng nhập xem một topic thông tin công khai, việc cấu hình `.simpSubscribeDestMatchers("/topic/public").permitAll()` có thể hợp lý **chỉ khi** HTTP/CONNECT authentication policy và CSRF CONNECT cũng được thiết kế cho khách đó. Đừng nghĩ `permitAll()` ở SUBSCRIBE tự cho anonymous CONNECT vượt qua những rule trước đó.

Ví dụ chính của bài chọn `authenticated()` cho `/topic/public` để giữ nhất quán với HTTP handshake bắt buộc login.

## 7. Hiểu chính xác matcher: type, destination và thứ tự

`MessageMatcherDelegatingAuthorizationManager.Builder` hỗ trợ nhiều nhóm matcher. Cách lựa chọn quyết định chính sách thực tế.

| Matcher | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `nullDestMatcher()` | Message không có destination | `CONNECT`, `DISCONNECT` và một số loại control frames |
| `simpTypeMatchers(SimpMessageType.MESSAGE)` | Inbound message có loại MESSAGE (thường từ STOMP SEND) | Chặn mọi SEND chưa được liệt kê |
| `simpTypeMatchers(SimpMessageType.SUBSCRIBE)` | Inbound subscription | Chặn mọi SUBSCRIBE chưa được liệt kê |
| `simpSubscribeDestMatchers(patterns)` | Chỉ khớp SUBSCRIBE đến các destinations chỉ định | Cho `SUBSCRIBE /topic/public` |
| `simpDestMatchers(patterns)` | Khớp destination, không tự thay kiểm tra type cụ thể | Cho SEND vào `/app/orders.lookup` với role |
| `anyMessage()` | Fallback đối với message chưa khớp rule trước | `denyAll()` |

### 7.1. Matcher có thứ tự ưu tiên theo khai báo

Một cách hiểu đúng là **rule khớp đầu tiên** trong cấu hình là quyết định được áp dụng. Vì vậy những matcher cụ thể/deny quan trọng phải được đặt trước matcher tổng quát.

Cẩn trọng với anti-pattern:

~~~java
// KHÔNG nên dùng dạng chung cho dữ liệu nhạy cảm:
messages
    .simpDestMatchers("/topic/**").authenticated()
    .simpTypeMatchers(
        SimpMessageType.MESSAGE,
        SimpMessageType.SUBSCRIBE
    ).denyAll();
~~~

Nếu client gửi MESSAGE trực tiếp tới broker `/topic/admin`, một destination-only matcher quá rộng có thể bắt message **trước** rule cấm type phía sau. Kết quả: client đã authenticated có thể vượt chính sách dự kiến.

Dạng an toàn hơn là **chỉ cho SUBSCRIBE** vào destinations được duyệt, cấm MESSAGE ngoài `/app/**`:

~~~java
messages
    .simpSubscribeDestMatchers("/topic/public")
        .authenticated()
    .simpDestMatchers("/app/orders.lookup")
        .hasRole("USER")
    .simpTypeMatchers(
        SimpMessageType.MESSAGE,
        SimpMessageType.SUBSCRIBE
    ).denyAll()
    .anyMessage().denyAll();
~~~

Nếu `/topic/admin` chứa dữ liệu nhạy cảm, cần rule `simpSubscribeDestMatchers("/topic/admin").hasRole("ADMIN")` **trước** fallback deny, cùng test bảo đảm user thường không SUBSCRIBE được.

### 7.2. Không phải mọi STOMP frame đều có destination

STOMP `CONNECT`, `DISCONNECT`, `UNSUBSCRIBE` hoặc heartbeat có thể không mang destination. Nếu chỉ định nghĩa `simpDestMatchers("/app/**")` rồi không có fallback phù hợp, các frame không có destination chưa được kiểm soát rõ.

Rule `nullDestMatcher().authenticated()` giúp diễn đạt yêu cầu principal cho các messages không có destination trong ví dụ. Không suy diễn nó là toàn bộ logic xác thực token: `CONNECT` còn có CSRF và có thể có custom authentication.

### 7.3. STOMP command và SimpMessageType không giống chữ HTTP method

| STOMP frame | SimpMessageType thường dùng | Ghi chú |
| --- | --- | --- |
| `CONNECT` | `CONNECT` | Tạo STOMP session logic sau HTTP handshake |
| `SEND` | `MESSAGE` | Gửi payload từ client |
| `SUBSCRIBE` | `SUBSCRIBE` | Đăng ký nhận broker messages |
| `UNSUBSCRIBE` | `UNSUBSCRIBE` | Hủy subscription |
| `DISCONNECT` | `DISCONNECT` | Đóng phiên messaging |
| Heartbeat | `HEARTBEAT` | Duy trì/giám sát kết nối tùy transport |

Đừng viết HTTP `requestMatchers(HttpMethod.POST, "/topic/**")` và tin nó kiểm soát STOMP `SEND`. Một WebSocket connection mang frames, không phát HTTP POST mới cho mỗi command.

### 7.4. Destination pattern và biến đường dẫn

Một destination như `/topic/orders/2002` có thể khớp `/topic/orders/*` theo cấu hình matcher nhưng **không** có nghĩa user được truy cập order 2002. Destination có thể bị client tự chọn. Muốn phân quyền theo object ID, cần kiểm tra:

- Principal server-side.
- ID được trích xuất và chuẩn hóa đúng.
- Role/scope và tenant.
- Quyền sở hữu/ACL hiện tại của tài nguyên.
- Không có biến thể destination làm trượt rule.
- Quyền còn hợp lệ tại thời điểm dữ liệu được phát.

## 8. Không cho client gửi trực tiếp vào broker

### 8.1. Lỗ hổng giả mạo thông báo

Giả sử client được phép:

~~~text
SEND
destination:/topic/orders/2002

{"status":"DELIVERED"}
^@
~~~

Nếu broker phát payload cho subscribers mà không qua `@MessageMapping`/service, client có thể giả mạo trạng thái đơn hàng. Đó là lý do một thiết kế an toàn thường yêu cầu:

~~~text
Client SEND /app/orders.update
           |
           v
Message Authorization
           |
           v
@MessageMapping + service kiểm tra quyền/validation
           |
           v
Server publish /topic/orders/{id}
           |
           v
Broker gửi tới authorized subscribers
~~~

Không mở `MESSAGE` tới `/topic/**` hoặc `/queue/**` cho clients chỉ vì `/topic` nghe giống “public”.

### 8.2. External broker relay không thay Spring Security

Khi dùng broker relay (ví dụ một message broker bên ngoài), còn phải xét:

- Quyền kết nối giữa application và broker.
- Credentials và TLS tới broker.
- Destination/queue/topic ACL ở broker nếu có.
- Multi-tenant routing và isolation.
- Không để client STOMP tự ý tạo destination được broker phát rộng.
- Quotas, fan-out và backpressure.

Message authorization tại Spring là một lớp cần thiết, nhưng không tự bảo vệ mọi cấu hình external broker.

## 9. Kết hợp @MessageMapping và phân quyền ở service

Ví dụ lệnh tra cứu đơn hàng do Alice gửi:

~~~text
SEND
destination:/app/orders.lookup
content-type:application/json

{"orderId":1001}
^@
~~~

Spring `@MessageMapping` nhận principal đã xác thực:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

record OrderLookup(long orderId) {}
record OrderView(long orderId, String status) {}

interface OrderQueryService {
    // Implementation phải kiểm tra principal/tenant/ownership.
    OrderView findVisibleOrder(String username, long orderId);
}

@Controller
class OrderMessageController {

    private final OrderQueryService orders;
    private final SimpMessagingTemplate messaging;

    OrderMessageController(
        OrderQueryService orders,
        SimpMessagingTemplate messaging
    ) {
        this.orders = orders;
        this.messaging = messaging;
    }

    @MessageMapping("/orders.lookup")
    void lookup(@Payload OrderLookup request, Principal principal) {
        // Danh tính lấy từ security context, không từ payload.
        String username = principal.getName();

        OrderView view = orders.findVisibleOrder(
            username, request.orderId()
        );

        messaging.convertAndSendToUser(
            username,
            "/queue/order-results",
            view
        );
    }
}
~~~

### 9.1. Điều gì phải xảy ra trong OrderQueryService?

Pseudocode nghiệp vụ:

~~~java
Order order = repository.findById(orderId)
    .orElseThrow(NotFoundException::new);

if (!order.ownerUsername().equals(authenticatedUsername)) {
    throw new AccessDeniedException("Forbidden");
}

return new OrderView(order.id(), order.status());
~~~

Các lớp repository/exception thực tế tùy dự án. Điểm cốt lõi là kiểm tra quyền **theo order ID thực và principal đã xác thực**.

**Sai lầm:** cho mọi user role USER chạy `/app/orders.lookup` rồi trả bất cứ order ID nào. Đây là Broken Object Level Authorization (BOLA)/IDOR; CORS, Origin, CSRF và `hasRole("USER")` không tự ngăn.

### 9.2. User destinations có ích, nhưng không tự phân quyền nội dung

Client đăng ký:

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
    view
);
~~~

Spring giải quyết `/user` destinations theo user/session. Tuy nhiên:

- Server vẫn có thể vô tình phát sai username.
- Một user có thể có **nhiều connections**; phương thức gửi theo user có thể tác động nhiều sessions tùy routing.
- Cluster hoặc broker relay có thể đòi cấu hình user destination routing riêng.
- Nếu view chứa dữ liệu trái quyền, routing “đúng Alice” không xóa lỗi authorization.
- Với order-specific topic, việc SUBSCRIBE cần kiểm tra ACL theo order/tenant, không chỉ role USER.

## 10. Phân quyền SUBSCRIBE cho dữ liệu riêng tư

### 10.1. Vì sao authenticated() chưa đủ?

Giả sử ứng dụng phát trạng thái vào `/topic/orders/2002`. Policy sau là rủi ro:

~~~java
// Phản ví dụ: mọi người đã login đều nghe được mọi order.
messages.simpSubscribeDestMatchers("/topic/orders/*")
    .authenticated();
~~~

Alice có thể thử subscribe order 2002 của Bob. Browser origin của Alice hợp lệ và STOMP CONNECT có CSRF token đúng, nhưng không có quyền với order đó.

### 10.2. Các thiết kế an toàn hơn

Tùy nghiệp vụ:

1. **User-specific destination:** server chuyển kết quả cho `/user/queue/order-results`; client chỉ nhận dữ liệu của principal đã xác thực, service vẫn kiểm tra order.
2. **Custom message AuthorizationManager:** đọc `SimpMessageHeaderAccessor`, destination và `Authentication` để kiểm tra membership/ACL đối với order hoặc room đang được SUBSCRIBE.
3. **Broker ACL/tenant isolation:** nếu dùng external broker có khả năng phân quyền, cấu hình quyền đúng ở broker **và** ở application.
4. **Tách nhãn public/private:** `/topic/public` có thể mở theo policy, nhưng không gộp `/topic/admin` hoặc `/topic/orders/**` vào cùng wildcard.
5. **Thu hồi subscription:** khi membership thay đổi, hủy subscription/đóng connection hoặc kiểm tra quyền tại thời điểm phát.

Với ACL phức tạp, một rule destination tổng quát nên đóng vai trò lớp đầu; quyết định theo object/tenant cần áp dụng tại chỗ có đủ dữ liệu và khả năng kiểm soát.

### 10.3. Điều không nên làm

- Không dựa vào `Origin: https://admin.example.com` để cấp SUBSCRIBE admin.
- Không tin `userId`/`tenantId` trong native headers do client tự gửi.
- Không coi một `SUBSCRIBE` từng được cho phép là quyền vĩnh viễn.
- Không chỉ kiểm tra role để bảo vệ topic có dữ liệu của từng user.
- Không nhầm tên `/user/queue/**` với quyền wildcard của tất cả users.

## 11. CSRF trên STOMP CONNECT là một kiểm tra riêng

### 11.1. Vì sao cần CSRF CONNECT?

Nếu người dùng đăng nhập bằng session cookie, browser có thể tự gửi cookie trong HTTP WebSocket handshake (tùy chính sách cookie). Website không tin cậy có thể cố mở kết nối với API của nạn nhân. Đây là rủi ro Cross-Site WebSocket Hijacking.

Native WebSocket **không dùng Fetch CORS preflight OPTIONS**. Spring Security WebSocket Messaging với `@EnableWebSocketSecurity` yêu cầu **CSRF token hợp lệ ở inbound STOMP CONNECT** theo cơ chế bảo vệ tương ứng, để tăng khả năng ngăn site không tin cậy lợi dụng phiên.

Điểm cần nhớ:

- HTTP 101 **không** có nghĩa CSRF CONNECT đã qua.
- `Origin` check của WebSocket handshake và CSRF CONNECT bảo vệ những khía cạnh khác nhau.
- CSRF token phải được gửi trong **native STOMP CONNECT header**, không phải chỉ trong HTTP request khác.
- Việc tự ý bỏ CSRF toàn hệ thống để CONNECT thành công có thể làm lộ các HTTP POST/PUT nghiệp vụ.

### 11.2. Endpoint HTTP để frontend lấy CSRF token

Một ứng dụng có thể tự triển khai:

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

**Đây không phải endpoint mặc định của mọi ứng dụng Spring Boot.** Phải triển khai và bảo vệ nó. Nếu frontend khác origin, HTTP `/api/csrf` cần CORS allowlist riêng cho frontend tin cậy; `setAllowedOrigins` của WebSocket endpoint không tự tạo CORS cho API này.

Token phải tương thích `CsrfTokenRepository`, `CsrfTokenRequestHandler`, deferred/masked token và session lifecycle của ứng dụng. Không để response token bị CDN cache dùng chung hoặc ghi vào log.

### 11.3. JavaScript gửi native STOMP header

Ví dụ `@stomp/stompjs`:

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

`connectHeaders` nằm trong **STOMP CONNECT frame**, không phải một object HTTP headers mà browser dùng trên WebSocket handshake. Browser WebSocket API không hỗ trợ arbitrary `Authorization`/`X-CSRF-TOKEN` HTTP handshake headers giống Fetch.

Khi reconnect sau logout/login hoặc token rotation, client cần lấy token mới theo thiết kế, không dùng token cũ vô hạn.

### 11.4. Tích hợp bảo vệ CONNECT không phải một rule .simpDestMatchers

`STOMP CONNECT` thường không có destination. Bởi vậy `simpDestMatchers("/app/**")` không thay thế kiểm tra CSRF token tại CONNECT. `nullDestMatcher().authenticated()` có thể kiểm tra principal cho message không có destination, nhưng token CSRF phải được xử lý bằng cơ chế CONNECT security tương ứng.

Nếu CONNECT thất bại, phân biệt lỗi **CSRF token**, **principal/authentication**, **rule authorization** và **transport/session**. Không chỉnh destination allowlist trước khi biết bước nào từ chối.

## 12. Xác thực tại STOMP CONNECT và thứ tự ChannelInterceptor

### 12.1. Mặc định: principal được kế thừa từ HTTP handshake

Với session login:

~~~text
HTTP login -> session cookie
    -> GET /ws, Spring Security HTTP xác thực Alice
    -> WebSocket session giữ Principal Alice
    -> STOMP CONNECT/SEND/SUBSCRIBE dùng Principal Alice
    -> AuthorizationManager xét type/destination/authorities
~~~

STOMP headers `login`/`passcode` hoặc `username` trong payload **không tự thay thế** principal đã xác thực.

### 12.2. Khi SPA chỉ có bearer token trong JavaScript

Browser WebSocket constructor không cho đặt HTTP `Authorization` header tùy ý. Một số kiến trúc chọn truyền bearer token trong **STOMP CONNECT native header** và tự xác thực ở `ChannelInterceptor`.

Đây là một **mô hình xác thực khác** HTTP inheritance:

- Nếu HTTP `/ws` yêu cầu authenticated nhưng token chỉ được gửi ở CONNECT, handshake sẽ bị chặn trước.
- Nếu HTTP handshake được cho phép để chờ CONNECT, toàn bộ SEND/SUBSCRIBE phải bị chặn cho đến khi token được xác minh và principal được gắn.
- `@EnableWebSocketSecurity` mặc định có yêu cầu CSRF tại CONNECT; thiết kế bearer-token-only phải xử lý yêu cầu này một cách phù hợp với Spring Security version và threat model. **Không** giả định một `Authorization` native header tự tắt CSRF CONNECT.
- Phải chọn chính sách reconnect, expiry/revocation và giới hạn anonymous handshake.

### 12.3. Mẫu ChannelInterceptor minh họa

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.core.Authentication;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

interface VerifiedConnectTokenService {
    // Implementation bắt buộc kiểm tra signature/issuer/audience/
    // expiry/revocation và các authorities.
    Authentication authenticate(String bearerHeader);
}

class ConnectBearerAuthenticationInterceptor
        implements ChannelInterceptor {

    private final VerifiedConnectTokenService tokens;

    ConnectBearerAuthenticationInterceptor(
        VerifiedConnectTokenService tokens
    ) {
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
            String bearer = accessor.getFirstNativeHeader("Authorization");

            // Dịch vụ phải ném lỗi khi thiếu hoặc sai token.
            Authentication authenticated = tokens.authenticate(bearer);
            accessor.setUser(authenticated);
        }
        return message;
    }
}
~~~

Mã này **chỉ là skeleton** về nơi xác minh và gắn principal: chưa có token verifier thực tế, error mapping, CSRF strategy, expiry handling hoặc cấu hình interceptor. Đừng tin raw `login`, `role`, `userId`; chỉ `setUser(...)` sau khi **xác thực token thực**.

### 12.4. Thứ tự interceptor là một phần của bảo mật

Nếu interceptor xác thực CONNECT chạy **sau** Spring Security message authorization, quyền có thể bị đánh giá khi principal chưa được gắn. Tệ hơn, nếu một thành phần tự tin rằng authorization đã chạy, có thể xảy ra luồng xử lý không nhất quán.

Cần đăng ký CONNECT authentication interceptor vào **client inbound channel** sớm hơn Security interceptors. Với cấu hình Servlet Messaging, một mô hình thường dùng là một `WebSocketMessageBrokerConfigurer` được đặt ưu tiên cao và thêm interceptor tại `configureClientInboundChannel(...)`, nhưng **thứ tự cụ thể phụ thuộc phiên bản và các configurers hiện hữu**. Test end-to-end phải xác minh rằng CONNECT sai token bị từ chối, CONNECT đúng có principal mong muốn, và không có MESSAGE nào chạy trước authentication.

Không tạo nhiều `ChannelInterceptor` cùng sửa principal bằng các nguồn khác nhau mà không có quy tắc kiểm chứng và ưu tiên rõ ràng.

## 13. SecurityContext, principal và tác vụ bất đồng bộ

Spring Security Messaging có thể cung cấp authentication vào security context khi inbound messages được xử lý. Tuy nhiên:

- `SecurityContextHolder` sử dụng ngữ cảnh gắn với thread trong nhiều trường hợp Servlet; không nên giả định các thread bất đồng bộ khác tự có cùng authentication.
- `@MessageMapping` có thể nhận `Principal` trực tiếp; đó là cách tường minh và dễ kiểm thử.
- Service có thể bật method security với `@EnableMethodSecurity` khi phù hợp, nhưng cần xác minh lời gọi qua Spring proxy, truyền context và ACL nghiệp vụ.
- `@Async`, executor hoặc scheduled jobs cần cơ chế truyền principal/context phù hợp, không lấy username từ một biến singleton.
- Nếu principal/authorities thay đổi khi socket còn mở, không mặc nhiên tin security context được cập nhật.

Ưu tiên truyền principal/identity đã xác thực **rõ ràng** vào các service kiểm tra quyền. Không giữ “currentUser” như biến dùng chung giữa nhiều WebSocket sessions.

## 14. Session lifetime, logout và phân quyền ở thời điểm phát

WebSocket có thể tồn tại lâu hơn một HTTP request. Alice có thể mở socket khi đang có role USER, sau đó:

- Logout tại frontend.
- Session HTTP bị invalidate.
- JWT hết hạn.
- Role ADMIN bị thu hồi.
- Alice rời một room hoặc không còn thuộc tenant.
- Server chuyển node khi triển khai/load balancing.

**Không** coi principal gắn lúc handshake là quyền vĩnh viễn.

Một chiến lược phù hợp với dữ liệu nhạy cảm:

1. **Khi logout:** đóng WebSocket sessions liên quan nếu hạ tầng hỗ trợ; hoặc đánh dấu quyền bị thu hồi để ngăn message/đầu ra sau đó.
2. **Khi role/ACL đổi:** revalidate khi SEND/SUBSCRIBE và trước khi server phát dữ liệu.
3. **Khi JWT hết hạn:** yêu cầu reconnect hoặc reauthentication theo thiết kế; không tiếp tục vô hạn dựa trên principal ban đầu.
4. **Khi membership thay đổi:** hủy subscriptions của room/tenant, hoặc áp dụng quyền tại thời điểm publish.
5. **Khi dùng multi-node:** bảo đảm session/user registry và broker routing đồng bộ; không dựa vào dữ liệu cục bộ sai phạm vi.
6. **Khi đóng/timeout:** giải phóng subscriptions, counters, rate limiter state và tài nguyên mạng.

Spring Session có thể hỗ trợ các kịch bản session WebSocket trong cấu hình tương ứng; không mặc định mọi Spring Security application tự đóng tất cả connections ngay khi HTTP logout.

## 15. SockJS fallback và HTTP CSRF: đừng sửa nhầm tầng

Nếu endpoint được bật SockJS:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.com")
        .withSockJS();
}
~~~

SockJS có thể dùng native WebSocket hoặc HTTP fallback như XHR streaming/polling.

| Đường đi | Cơ chế liên quan |
| --- | --- |
| Native WebSocket handshake | Origin validation, HTTP authentication, TLS/proxy |
| SockJS `/ws/info` | HTTP routing/auth, Origin/CORS tùy transport |
| SockJS XHR `POST /ws/.../xhr_send` | HTTP CORS, cookie, CSRF HTTP theo policy |
| STOMP CONNECT bên trong SockJS | CSRF CONNECT, authentication và messaging security |
| STOMP SEND/SUBSCRIBE bên trong SockJS | Message authorization và object/tenant ACL |

### 15.1. Hai loại CSRF khác nhau

Nếu SockJS dùng HTTP POST transport, Spring Security HTTP CSRF filter có thể chặn request transport đó vì nó không mang HTTP CSRF token theo cách API nghiệp vụ dùng. STOMP CONNECT lại mang token **bên trong STOMP frame**.

Đừng tắt CSRF cho toàn bộ HTTP application. Nếu framework và transport thực sự cần một exception, giới hạn **chính xác** những transport URLs được kiểm soát, giữ CSRF cho REST POST/PUT và bảo vệ STOMP CONNECT.

### 15.2. Allowed origins và security headers còn ảnh hưởng SockJS

Một số SockJS legacy transports dựa trên iframe có thể bị `X-Frame-Options` hoặc CSP `frame-ancestors` hạn chế. XHR fallback còn chịu CORS. Browser có thể bị CSP `connect-src` chặn trước khi HTTP/WebSocket request tới server.

Khi gặp lỗi, kiểm tra transport cụ thể, headers và Origin policy. Không nới `X-Frame-Options`, CSP hay CORS trên **toàn hệ thống** chỉ để phục vụ một fallback chưa chứng minh là cần thiết.

## 16. Reactive/WebFlux: message security không dùng nguyên annotation Servlet

Spring WebFlux native sử dụng `WebSocketHandler`, `WebSocketSession` và Reactor. Nó **không tự là Spring STOMP Message Broker** với `@EnableWebSocketMessageBroker` và `@EnableWebSocketSecurity` giống ví dụ Servlet.

Với WebFlux native:

- `ServerHttpSecurity` bảo vệ **HTTP handshake route**.
- Origin cần được kiểm tra ở handshake bằng adapter/handler/WebFilter phù hợp.
- `WebSocketSession.getHandshakeInfo().getPrincipal()` cung cấp principal theo mô hình Reactive.
- Handler/service cần **parse, validate và authorize từng message** (text/binary) theo principal và nội dung.
- Nếu ứng dụng thực sự triển khai STOMP trên Reactive thông qua một giải pháp riêng, hãy áp dụng security API của chính stack đó; không mặc định copy annotation Servlet là đủ.

### 16.1. HTTP handshake với ServerHttpSecurity

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveHandshakeSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/ws").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Cấu hình trên không tự kiểm tra Origin hoặc message JSON sau handshake.

### 16.2. Mẫu WebSocketHandler phân quyền từng message

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface RealtimeCommandService {
    // Phải parse, validate và kiểm tra object/tenant/action ACL.
    Mono<Void> validateAuthorizeAndHandle(
        Principal principal,
        String payload
    );
}

class AuthorizedReactiveWebSocketHandler {

    static WebSocketHandler create(RealtimeCommandService commands) {
        return session -> session.getHandshakeInfo()
            .getPrincipal()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")))
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

Đây là **khung minh họa**, chưa gồm đăng ký `HandlerMapping`/`WebSocketHandlerAdapter`, gửi outbound frames, backpressure, kích thước payload hay error handling. Điểm chính: principal được xác thực ở handshake **không thay thế kiểm tra quyền từng thông điệp**.

Không sử dụng `SecurityContextHolder` của Servlet như nguồn duy nhất cho Reactive pipeline; hãy truyền principal/context đúng cách.

## 17. Ma trận kiểm thử cho @EnableWebSocketSecurity

### 17.1. Test theo message type và destination

| Ca | Đầu vào | Principal | Kỳ vọng |
| --- | --- | --- | --- |
| H1 | HTTP handshake `/ws` từ app origin | Alice authenticated | WebSocket được mở nếu HTTP/Origin hợp lệ |
| H2 | HTTP handshake không session | Anonymous | Bị HTTP auth từ chối |
| H3 | Handshake từ origin evil với session hợp lệ | Alice | Bị Origin policy từ chối |
| C1 | STOMP CONNECT có CSRF token hợp lệ | Alice | CONNECTED nếu policy hợp lệ |
| C2 | STOMP CONNECT thiếu/sai CSRF token | Alice | Không được CONNECTED khi CSRF CONNECT yêu cầu |
| C3 | CONNECT với bearer token tự khai nhưng verifier từ chối | Anonymous/invalid | Không gắn principal, không cho message |
| M1 | SEND `/app/orders.lookup` | Alice có role USER | Qua message rule, service tiếp tục kiểm tra order |
| M2 | SEND `/topic/public` | Alice | Từ chối |
| M3 | SEND `/app/orders.lookup` | Bob không có role USER | Từ chối |
| M4 | SEND `/app/admin.execute` | Alice role USER | Từ chối |
| S1 | SUBSCRIBE `/topic/public` | Alice authenticated | Cho phép theo policy ví dụ |
| S2 | SUBSCRIBE `/user/queue/order-results` | Alice | Cho phép theo policy ví dụ |
| S3 | SUBSCRIBE `/app/orders.lookup` | Alice | Từ chối |
| S4 | SUBSCRIBE `/topic/admin` | Alice | Từ chối |
| S5 | SUBSCRIBE topic order của Bob | Alice | Bị ACL/object authorization từ chối |
| B1 | SEND lookup order Bob với role USER | Alice | Service từ chối, **không có data leak** |
| L1 | Role của Alice bị thu hồi sau CONNECT | Alice trên socket cũ | Chính sách thu hồi/revalidate hoạt động |
| R1 | WebFlux native gửi JSON command trái quyền | Authenticated | Handler/service từ chối |

Đừng chỉ dựa vào HTTP status `101`; nó không chứng minh các ca C/M/S đã qua.

### 17.2. Test hành vi từ chối và tác động nghiệp vụ

Khi thử đọc order Bob từ socket Alice, test cần xác minh:

1. Handler/service nhận đúng principal **Alice**, không tin `userId:bob`.
2. Request bị từ chối trước khi dữ liệu riêng tư được phát.
3. Không có message lộ nội dung order Bob tới user destination của Alice.
4. Không có side effect thay đổi dữ liệu Bob.
5. Logs/audit ghi nhận từ chối mà không lộ session token/CSRF token.
6. Các user khác không bị ảnh hưởng bởi sự từ chối đó.

Một STOMP `ERROR` xuất hiện sau khi dữ liệu đã bị phát nhầm **không phải** kết quả an toàn.

## 18. Kiểm thử tích hợp: MockMvc không thay WebSocketStompClient

### 18.1. Phân lớp công cụ kiểm thử

| Công cụ | Kiểm thử tốt | Không thay thế |
| --- | --- | --- |
| `MockMvc` | HTTP login, CORS/CSRF endpoint, SecurityFilterChain matchers | Toàn bộ WebSocket upgrade và STOMP frames |
| `WebSocketStompClient` + test server | Handshake thực, CONNECT, SEND, SUBSCRIBE, STOMP ERROR | Browser SOP/cookie/CSP 100% |
| Browser DevTools | Origin, Cookie, HTTP 101, Frames/Messages, CSP/TLS | Test quyền ở server chỉ bằng quan sát UI |
| Non-browser WebSocket client | Header Origin tự đặt, auth/bearer, protocol edge cases | Hành vi SOP của browser |
| Service/unit tests | Object/tenant ACL, validation, read/write side effects | Pipeline Message/Handshake đúng wiring |
| `WebTestClient` / Reactive WebSocket client | HTTP Reactive và native WebSocket integration tùy harness | STOMP broker Servlet không tồn tại trong WebFlux native |

### 18.2. Kịch bản tích hợp Servlet end-to-end

Một test server với principal Alice nên chạy theo trình tự:

~~~text
Given:
  - Spring Boot test server đang chạy cổng thử nghiệm.
  - User Alice authenticated qua HTTP và có session cookie.
  - Có token CSRF từ đúng session.
  - Server dùng @EnableWebSocketMessageBroker và @EnableWebSocketSecurity.
  - Endpoint /ws chỉ nhận https://app.example.com.
  - Alice sở hữu order 1001; Bob sở hữu order 2002.

Positive:
  1) Kết nối WebSocket với Origin app + Cookie Alice.
  2) Gửi STOMP CONNECT với CSRF native header hợp lệ.
  3) Đợi STOMP CONNECTED.
  4) SUBSCRIBE /user/queue/order-results.
  5) SEND /app/orders.lookup với {"orderId":1001}.
  6) Assert nhận OrderView của Alice ở user destination.

Negative:
  A) SEND /topic/public trực tiếp -> bị từ chối.
  B) SUBSCRIBE /app/orders.lookup -> bị từ chối.
  C) SUBSCRIBE /topic/admin -> bị từ chối.
  D) SEND /app/orders.lookup nhưng orderId=2002 -> bị service từ chối.
  E) CONNECT thiếu/sai CSRF -> không CONNECTED.
  F) Cookie Alice hợp lệ nhưng Origin evil -> handshake bị từ chối.
  G) Không Cookie nhưng Origin app -> bị HTTP authentication từ chối.
  H) Role/permission bị thu hồi -> không tiếp tục phát dữ liệu trái quyền.
~~~

Các STOMP operations bất đồng bộ cần timeout, frame handler, lắng nghe ERROR/connection close và state isolation trong test. Đây là **test design**, không phải một bộ test đã chạy trong dự án.

### 18.3. Khởi tạo client test minh họa

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

// Phần chuẩn bị trong integration test, chưa phải test độc lập:
WebSocketStompClient client = new WebSocketStompClient(
    new StandardWebSocketClient()
);

WebSocketHttpHeaders handshakeHeaders = new WebSocketHttpHeaders();
handshakeHeaders.setOrigin("https://app.example.com");
handshakeHeaders.add(
    HttpHeaders.COOKIE, "SESSION=" + validTestSessionCookie
);

StompHeaders connectHeaders = new StompHeaders();
connectHeaders.add("X-CSRF-TOKEN", validCsrfToken);

// Cần handler, URI test server và completion/timeout assertions:
// client.connectAsync(uri, handshakeHeaders, connectHeaders, handler);
~~~

`validTestSessionCookie` và `validCsrfToken` là placeholders được test setup cấp từ **cùng session**. Muốn code chạy cần khai báo chúng, khởi động test server, xử lý SessionHandler, đăng ký subscriptions và kiểm tra kết quả. Tên API client có thể khác theo phiên bản Spring Framework; hãy đối chiếu project thực tế.

### 18.4. Test matcher order có thể phát hiện policy bypass

Hãy cố ý thử một client `SEND /topic/admin` trong khi principal có role USER, đồng thời test `SUBSCRIBE /topic/public`. Nếu rule destination-only quá rộng đứng trước `simpTypeMatchers(MESSAGE).denyAll()`, bài test sẽ phát hiện khả năng cho client publish trái ý định.

Đây là kiểm thử regression quan trọng nhất sau mỗi lần thêm destination pattern mới.

## 19. Gỡ lỗi theo giai đoạn: handshake, CONNECT, MESSAGE, SUBSCRIBE

| Triệu chứng | Lớp cần xem | Hướng điều tra |
| --- | --- | --- |
| WebSocket không có HTTP 101 | HTTP handshake, Origin, session, proxy/TLS/CSP | Xem HTTP status, Cookie, `Origin`, CSP `connect-src` |
| HTTP 101 nhưng CONNECT thất bại | CSRF CONNECT hoặc principal | Xem native STOMP headers và source token |
| CONNECT được nhưng SEND `/app/**` bị từ chối | Message type/destination/role rule | Xem `simpDestMatchers`, authorities và matcher order |
| SUBSCRIBE `/topic/admin` được phép cho USER | Subscribe rule quá rộng | Xem `simpSubscribeDestMatchers`, tránh `/topic/**` blanket |
| Client SEND trực tiếp broker và message được phát | Destination-only matcher sai | Cấm MESSAGE tới broker destinations |
| Alice đọc được order Bob | Object/tenant authorization thiếu | Kiểm tra service, test data không bị phát |
| Message thất bại khi principal là anonymous | HTTP handshake không xác thực hoặc CONNECT verifier chưa setUser | Xem session và interceptor order |
| Principal biến mất trong async task | Context không được propagate | Truyền Principal/SecurityContext đúng cách |
| Origin evil có thể mở socket | Endpoint allowedOrigins rộng | Siết WebSocket handshake Origin |
| Browser báo ACAO khi SockJS fallback | HTTP CORS của XHR transport | Xem SockJS path, OPTIONS, gateway/CorsFilter |
| SockJS XHR POST bị 403 | HTTP CSRF cho transport hoặc CORS | Kiểm tra matcher hẹp, giữ REST CSRF |
| Anonymous client không CONNECTED | HTTP auth, CSRF CONNECT hoặc message nullDest rule | Xác định chính xác tầng từ chối |
| Server tự phát private data ra `/topic/public` | Outbound routing/data isolation | Sửa publisher/business logic, inbound rule không đủ |
| Role đổi nhưng socket cũ vẫn dùng quyền | Session principal stale/lifecycle | Đóng/revalidate connection, kiểm tra quyền lúc publish |
| Đăng nhập lại nhưng old socket anonymous | Không tự nâng principal sau login | Reconnect hoặc protocol reauth riêng |
| Multiple nodes nhận user destinations lệch | User registry/broker route/affinity | Kiểm tra cluster setup |
| Mọi frame đều bị deny sau khi thêm rule | Matcher order hoặc catch-all sớm | Đặt specific allows trước `anyMessage().denyAll()` |
| Resource leak khi spam SUBSCRIBE | Quota/rate limits thiếu | Giới hạn sessions, destinations, payload, timeouts |
| Spring REST CORS hợp lệ nhưng WS origin vẫn bị chặn | Hai chính sách origin độc lập | Xem `setAllowedOrigins` ở endpoint |
| WebFlux native không áp dụng annotation | Dùng nhầm Servlet messaging integration | Viết per-message auth trên Reactive handler |

### 19.1. Quy trình debug nhanh

~~~mermaid
flowchart TD
    A["Client báo lỗi realtime"] --> B{"Có HTTP handshake thành công?"}
    B -- "Không" --> C["HTTP auth, Cookie, Origin, TLS, CSP, Gateway"]
    B -- "Có" --> D{"Có STOMP CONNECTED?"}
    D -- "Không" --> E["CSRF CONNECT, Principal, inbound interceptor order"]
    D -- "Có" --> F{"SEND hay SUBSCRIBE thất bại?"}
    F -- "SEND" --> G["MESSAGE matcher, destination, role + service ACL"]
    F -- "SUBSCRIBE" --> H["SUBSCRIBE matcher, topic ACL + user destination"]
    F -- "Không, nhưng dữ liệu sai" --> I["Publisher, outbound routing, ownership, lifecycle"]
~~~

Không sửa lỗi một tầng bằng cách tắt toàn bộ Spring Security, mở Origin `*` hoặc bỏ CSRF ứng dụng.

## 20. Checklist triển khai production

- [ ] HTTP `/ws` đi qua đúng SecurityFilterChain và có authentication phù hợp.
- [ ] Origin của WebSocket endpoint chỉ chấp nhận frontend tin cậy; không nhầm với CORS REST.
- [ ] Có `@EnableWebSocketMessageBroker` và `@EnableWebSocketSecurity` trong stack Servlet/STOMP phù hợp.
- [ ] Bean `AuthorizationManager<Message<?>>` được đăng ký đúng context, không tạo interceptors trùng.
- [ ] `MessageMatcherDelegatingAuthorizationManager.Builder` quy định rule theo type và destination.
- [ ] Rules cụ thể đứng trước fallback `simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()` và `anyMessage().denyAll()`.
- [ ] Client chỉ SEND vào `/app/**` được phê duyệt, **không** SEND trực tiếp tới broker destinations.
- [ ] SUBSCRIBE vào `/topic/admin`/private destinations có role/object ACL thích hợp.
- [ ] `nullDestMatcher` và control frames có policy rõ ràng.
- [ ] STOMP CONNECT yêu cầu CSRF phù hợp với Spring Security Messaging và mô hình credentials.
- [ ] Nếu dùng token-auth tại CONNECT, interceptor xác thực token thật và chạy trước authorization; không bỏ CSRF CONNECT một cách ngầm định.
- [ ] Principal lấy từ authentication server-side, không tin `userId`/`login`/`role` trong payload/headers.
- [ ] Handler/service kiểm tra object/tenant ACL theo principal đối với mọi dữ liệu riêng.
- [ ] User destinations/`convertAndSendToUser` được kiểm tra đúng username/session và cluster routing.
- [ ] Broker relay, nếu có, có TLS/credentials/ACL và resource limits riêng.
- [ ] Logout/session expiry/role revocation có cơ chế đóng/revalidate connection và subscriptions.
- [ ] SockJS HTTP fallback được kiểm tra CORS, cookie, HTTP CSRF đúng route, CSP/frame headers.
- [ ] Với WebFlux native, handler kiểm tra từng message, không giả định annotation Servlet áp dụng.
- [ ] Có giới hạn payload, rate, subscription count, connection lifetime và heartbeat.
- [ ] Integration tests kiểm tra cả điều **không** xảy ra: không leak dữ liệu và không side effect trái quyền.
- [ ] Logs/audit không lưu raw bearer token, cookie session, CSRF token hoặc payload nhạy cảm không cần thiết.

## 21. Câu hỏi vận dụng và lời giải

**Tình huống 1 — HTTP 101 là đủ?** Frontend có HTTP 101 khi mở WebSocket. Có nghĩa `SEND /app/admin.execute` được phép không?

**Giải thích:** Không. HTTP 101 chỉ xác nhận transport; message authorization phải kiểm tra type/destination và role, business service kiểm tra quyền thực tế.

**Tình huống 2 — Chỉ bật @EnableWebSocketMessageBroker.** Ứng dụng có `@MessageMapping` và broker nhưng chưa có policy inbound. Có nên mặc định mọi topic được bảo vệ?

**Giải thích:** Không. Cần cấu hình Spring Security Messaging bằng `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>` phù hợp; còn kiểm tra quyền nghiệp vụ.

**Tình huống 3 — Destination matcher rộng.** Rule `simpDestMatchers("/topic/**").authenticated()` đứng trước rule cấm MESSAGE. Rủi ro?

**Giải thích:** Một MESSAGE/SEND tới broker destination có thể match rule đầu và được phép. Nên dùng `simpSubscribeDestMatchers` cho subscription và deny client MESSAGE tới broker destinations.

**Tình huống 4 — User có role USER.** Alice `SEND /app/orders.lookup` với order ID của Bob. Message rule cho qua vì Alice có USER. Có lỗi không?

**Giải thích:** Có nếu service trả dữ liệu Bob. Message authorization xét điểm vào, còn object/tenant authorization phải kiểm tra order ID thực sự theo principal.

**Tình huống 5 — Đăng ký topic admin.** Alice được `SUBSCRIBE /topic/public` nhưng cố SUBSCRIBE `/topic/admin`. Với cấu hình deny by default, điều gì xảy ra?

**Giải thích:** Rule public không match, fallback `simpTypeMatchers(SUBSCRIBE).denyAll()` sẽ chặn.

**Tình huống 6 — STOMP CONNECT thiếu CSRF.** Handshake HTTP xác thực Alice và trả 101, nhưng CONNECT không có token bị từ chối. Có phải role USER chưa đủ?

**Giải thích:** CSRF trên CONNECT là lớp độc lập. Phải gửi token hợp lệ trong native STOMP header từ cùng ngữ cảnh phiên.

**Tình huống 7 — Gửi X-CSRF-TOKEN ở HTTP WebSocket handshake.** Browser JS có thể tự đặt header HTTP này bằng `new WebSocket` không?

**Giải thích:** Không qua WebSocket API chuẩn; client STOMP dùng `connectHeaders` để gửi **native STOMP CONNECT header**.

**Tình huống 8 — Header login:admin.** Client thêm `login:admin` vào CONNECT rồi được cấp admin role. Có an toàn không?

**Giải thích:** Không. Native headers do client tự khai không phải authentication. Role phải đến từ session/token đã được xác minh.

**Tình huống 9 — Bearer chỉ ở CONNECT.** HTTP SecurityFilterChain yêu cầu authenticated tại `/ws`, nhưng không có cookie, bearer token chỉ được gửi trong CONNECT. Vì sao handshake thất bại?

**Giải thích:** Token chưa tới được HTTP layer. Cần chọn kiến trúc hợp lý, có CONNECT authentication interceptor và chặn messages khi chưa xác thực, đồng thời xử lý CSRF theo policy.

**Tình huống 10 — Đổi role.** Admin thu hồi role của Alice nhưng connection đã mở vẫn phát dữ liệu. `@EnableWebSocketSecurity` có tự đóng socket không?

**Giải thích:** Không nên mặc định như vậy. Cần cơ chế session/role revocation và kiểm tra quyền tại thời điểm phát dữ liệu nhạy cảm.

**Tình huống 11 — SockJS POST 403.** Native WebSocket hoạt động nhưng SockJS XHR POST bị CSRF HTTP chặn. Có nên bỏ toàn bộ CSRF?

**Giải thích:** Không. Phải điều tra HTTP transport paths và tạo ngoại lệ hẹp nếu thật sự cần, vẫn bảo vệ HTTP API khác và CSRF CONNECT.

**Tình huống 12 — WebFlux native.** Ứng dụng chỉ dùng WebFlux `WebSocketHandler` và thêm `@EnableWebSocketSecurity` từ ví dụ Servlet. Có tự phân quyền JSON messages không?

**Giải thích:** Không. WebFlux native không mặc định có STOMP broker pipeline tương ứng; cần bảo vệ handshake và mỗi message trong Reactive handler/service.

**Tình huống 13 — @MessageMapping sau async.** Handler chuyển việc xử lý sang executor rồi mất `SecurityContextHolder`. Có nên lấy username từ payload?

**Giải thích:** Không. Truyền principal/security context an toàn qua executor hoặc truyền explicit principal xuống service. Không tin client-provided username.

**Tình huống 14 — User destination.** `convertAndSendToUser("alice", "/queue/order-results", ...)` có ngăn dữ liệu Bob bị gửi cho Alice không?

**Giải thích:** Nó giúp routing theo user; service vẫn phải kiểm tra object ownership và nội dung trước khi phát.

**Tình huống 15 — Test không đủ.** Test thấy STOMP `ERROR` cho một lệnh trái phép. Có đủ chứng minh không leak dữ liệu không?

**Giải thích:** Chưa. Phải xác minh không có message nhạy cảm đã được phát đến subscription nào, và không có side effect nghiệp vụ, kể cả các trường hợp bất đồng bộ.

---

**Ghi nhớ:** **`@EnableWebSocketSecurity` bảo vệ client inbound messaging**, còn `AuthorizationManager<Message<?>>` quyết định những STOMP messages nào được phép dựa trên **type, destination và principal**. Hãy viết matcher đúng thứ tự, ưu tiên **deny by default**, không cho client SEND trực tiếp vào broker và giới hạn SUBSCRIBE vào private topics. HTTP handshake/Origin, CSRF ở STOMP CONNECT, object-level ACL, dữ liệu outbound và session lifecycle là **các ranh giới bổ sung không được bỏ qua**. Với **WebFlux native WebSocket**, cần xây pipeline authorization từng message riêng; không sao chép nguyên cấu hình STOMP Servlet rồi cho rằng được bảo vệ.
