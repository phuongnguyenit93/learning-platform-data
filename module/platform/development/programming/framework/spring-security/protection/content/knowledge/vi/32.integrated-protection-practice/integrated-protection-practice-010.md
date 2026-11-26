# Bảo vệ STOMP CONNECT và kiểm tra message trên kết nối

## 1. Bối cảnh thực hành và kết quả cần đạt

Bài thuộc chương **Thực hành tổng hợp** của mô-đun **SPRING_SECURITY_HTTP_PROTECTION**. Bên cạnh bảo vệ các HTTP request bằng CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và session, ứng dụng Spring Security còn phải kiểm soát **kết nối WebSocket và từng STOMP frame đi qua kết nối đó**.

Tình huống: portal phục vụ tại `https://portal.example.test` có chức năng chat và thông báo thời gian thực. Người dùng đăng nhập bằng session cookie, mở WebSocket tại `wss://portal.example.test/ws`, gửi dữ liệu đến `/app/chat.send`, theo dõi thông báo công khai cho người đã đăng nhập tại `/topic/general` và nhận phản hồi riêng tại `/user/queue/replies`. Máy chủ dùng Spring MVC và Spring Messaging với STOMP. Các tên miền `example.test` chỉ dùng minh họa.

**Mục tiêu học tập:**

1. Phân biệt HTTP handshake, STOMP `CONNECT` và STOMP `SEND`/`SUBSCRIBE`; xác định mỗi bước do thành phần nào bảo vệ.
2. Áp dụng xác thực người dùng từ HTTP session, hạn chế Origin và kiểm tra CSRF token trong **STOMP CONNECT native headers**.
3. Sử dụng `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>` để chỉ cho phép đúng thao tác gửi/đăng ký kênh.
4. Ngăn client gửi trực tiếp đến broker destination, đọc queue không thuộc quyền và giả mạo người gửi trong payload.
5. Thiết kế bài kiểm thử có cả frame hợp lệ lẫn frame bị từ chối, bao gồm handshake thực, CONNECT, gửi message và subscribe.
6. Chẩn đoán các lỗi thường gặp khi phối hợp HTTP CSRF, SockJS, proxy, session, CORS/CSP và đường đi Reactive.

**Tiêu chí hoàn thành:** trình duyệt hợp lệ có thể kết nối, gửi và nhận đúng dữ liệu; người chưa xác thực, Origin lạ, CONNECT thiếu/sai CSRF và các destination trái phép không vượt qua được lớp kiểm soát tương ứng. Kết luận dựa trên bằng chứng quan sát được ở HTTP, STOMP và trạng thái nghiệp vụ.

## 2. Vì sao WebSocket cần bảo vệ riêng?

Trong HTTP thông thường, mỗi request được Spring Security xử lý qua một filter chain. Với WebSocket, server xử lý HTTP handshake ban đầu, sau đó kênh hai chiều duy trì lâu dài và trao đổi nhiều STOMP frames. Việc nhận response `101 Switching Protocols` chứng minh WebSocket upgrade thành công; **chưa chứng minh STOMP CONNECT đã được chấp nhận**.

~~~mermaid
sequenceDiagram
    participant Browser as Trình duyệt
    participant HTTP as HTTP Security / Handshake
    participant Inbound as clientInboundChannel
    participant Auth as Spring Messaging Security
    participant Handler as @MessageMapping
    participant Broker as Broker / Outbound

    Browser->>HTTP: GET /ws (Upgrade, Cookie, Origin)
    HTTP-->>Browser: HTTP 101 nếu handshake hợp lệ
    Browser->>Inbound: STOMP CONNECT + CSRF native header
    Inbound->>Auth: Kiểm tra principal + CSRF + quyền
    Auth-->>Browser: STOMP CONNECTED nếu hợp lệ
    Browser->>Inbound: SUBSCRIBE /topic/general
    Inbound->>Auth: Kiểm tra quyền SUBSCRIBE
    Auth->>Broker: Đăng ký nếu được cho phép
    Browser->>Inbound: SEND /app/chat.send
    Inbound->>Auth: Kiểm tra quyền MESSAGE
    Auth->>Handler: Gọi @MessageMapping
    Handler->>Broker: Gửi event có sender lấy từ Principal
    Broker-->>Browser: STOMP MESSAGE cho subscription hợp lệ
~~~

### 2.1. Ba điểm kiểm soát khác nhau

| Giai đoạn | Dữ liệu nhận | Lớp bảo vệ | Điều phải chứng minh |
|---|---|---|---|
| HTTP handshake | `GET /ws`, `Upgrade`, `Origin`, cookie | HTTP SecurityFilterChain, xác thực HTTP, endpoint allowed origins, TLS/proxy | Người/Origin không phù hợp không được cấp kết nối trái phép |
| STOMP `CONNECT` | Frame có `accept-version` và native header CSRF | Interceptor của Spring Security Messaging trên `clientInboundChannel` | CONNECT thiếu/sai CSRF không đạt `CONNECTED`; principal gắn đúng phiên |
| STOMP `SEND`/`SUBSCRIBE` | Command, destination, payload, headers | `AuthorizationManager<Message<?>>`, controller và kiểm tra nghiệp vụ | Không thể gửi giả mạo, subscribe dữ liệu riêng hoặc bypass role/room membership |

**HTTP CSRF và STOMP CSRF là hai bước khác nhau.** CSRF filter của HTTP chủ yếu xử lý request HTTP; khi cấu hình Spring Security cho STOMP qua `@EnableWebSocketSecurity`, CONNECT còn được kiểm tra CSRF ở tầng messaging. Với SockJS fallback gửi POST, cần điều chỉnh HTTP CSRF **riêng transport endpoint** mà vẫn giữ yêu cầu token ở STOMP CONNECT.

### 2.2. Mô hình nguy cơ

| ID | Khả năng của attacker | Rủi ro | Điều kiện phòng vệ |
|---|---|---|---|
| W01 | Điều khiển trang web ở Origin khác trong khi nạn nhân đã đăng nhập portal | Cross-Site WebSocket Hijacking: trình duyệt tự gửi cookie khi mở kết nối | Hạn chế Origin ở handshake và yêu cầu CSRF token trong CONNECT |
| W02 | Có một TCP/WebSocket connection nhưng chưa gửi CONNECT hợp lệ | Gửi frame STOMP nhằm bỏ qua xác thực messaging | Không có `CONNECTED` và không xử lý SEND/SUBSCRIBE |
| W03 | Gửi CONNECT không có token hoặc token từ phiên khác | Vượt qua ranh giới phiên người dùng | Reject CONNECT; không tạo subscription hay thực thi lệnh |
| W04 | Sửa `login`/`passcode` hay trường `sender` trong payload | Mạo danh user khác | Principal đáng tin từ HTTP/authenticator; sender do server quyết định |
| W05 | Gửi `SEND destination:/topic/general` | Giả danh thông báo của server đến toàn bộ subscriber | Chặn client MESSAGE vào broker prefixes; chỉ cho phép `/app/**` được định nghĩa |
| W06 | Subscribe trực tiếp `/queue/**` hoặc queue của người khác | Đọc tin nhắn riêng | Chỉ cho phép user destination hợp lệ; deny các broker destination khác |
| W07 | Đăng ký một room mà user không là thành viên | Lộ dữ liệu room | Quyền theo room trong inbound subscription rule |
| W08 | Gửi JSON quá lớn, dữ liệu lỗi hoặc nhồi tin liên tục | Làm cạn tài nguyên hoặc gây lỗi handler | Giới hạn kích thước, validation, rate limit, timeout và monitoring |
| W09 | Session HTTP đã logout nhưng WebSocket cũ còn sống | Tiếp tục phát/nhận thông tin sau khi mất quyền | Chính sách đóng socket khi logout/hết hạn, hoặc kiểm tra lại quyền phù hợp |
| W10 | Proxy/CDN xử lý Origin, TLS hoặc Upgrade sai | Kết nối không an toàn hoặc kiểm soát bị bỏ qua | Test qua WSS ở response cuối cùng và kiểm tra proxy thực tế |

Việc trình duyệt áp dụng same-origin policy cho `fetch` **không có nghĩa** WebSocket tự bị same-origin policy chặn. Server phải chủ động xem xét Origin. Header `Origin` cũng có thể bị giả mạo từ client phi trình duyệt, nên **không sử dụng Origin như cơ chế xác thực người dùng**.

## 3. Phân biệt xác thực handshake và quyền STOMP

Đối với ứng dụng Spring MVC đăng nhập bằng form:

1. Browser đăng nhập qua HTTP và có session cookie.
2. Browser mở `wss://portal.example.test/ws`, gửi cookie theo chính sách trình duyệt và session.
3. Spring Security xác thực HTTP request và gắn `Principal` của HTTP vào WebSocket session.
4. Spring Messaging chuyển principal đó tới các message trên session, để security policy và `@MessageMapping` sử dụng.

Các header STOMP `login` và `passcode` vốn dành cho STOMP broker (như STOMP over TCP); **Spring STOMP over WebSocket không mặc định dùng các header này để xác thực người dùng**. Nếu ứng dụng quyết định dùng bearer token trong CONNECT thay cho HTTP cookie, phải đăng ký `ChannelInterceptor` xác thực token, đặt `accessor.setUser(authenticatedPrincipal)` trước interceptor phân quyền, đồng thời thiết kế lại yêu cầu CSRF theo threat model. Chỉ đặt `Authorization: Bearer ...` vào CONNECT mà không có interceptor kiểm tra thì không có giá trị xác thực.

**Session và authorization:** authorization theo destination không tự thay thế kiểm tra quyền trên dữ liệu. Role `USER` có thể đủ để subscribe `/topic/general`, nhưng không chứng minh user được phép subscribe `/topic/rooms/other-team` hoặc gửi hành động lên đơn hàng của người khác. Các trường hợp này cần ràng buộc bằng dữ liệu nghiệp vụ và principal thực.

## 4. Cấu hình endpoint STOMP và broker trên Servlet

Ví dụ Spring Framework dùng `@EnableWebSocketMessageBroker` và `WebSocketMessageBrokerConfigurer`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class ChatWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://portal.example.test");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

Ý nghĩa:

- `/ws` là HTTP/WebSocket handshake endpoint, **không phải** STOMP destination để client gửi chat.
- `/app/chat.send` chuyển tới controller có `@MessageMapping("/chat.send")`.
- `/topic/general` và `/queue/**` thuộc broker; server đưa sự kiện tới broker để phát cho người subscribe.
- `/user/queue/replies` là user destination do Spring giải quyết dựa vào session/người dùng, không cấp phép client subscribe tùy ý vào queue vật lý của người khác.
- `setAllowedOrigins(...)` giới hạn Origin của browser handshake; giá trị là **HTTP(S) origin** của trang gọi (ví dụ `https://...`), không phải `wss://...`.
- Không thay `setAllowedOrigins(...)` bằng wildcard `*` trong ứng dụng sử dụng cookie đăng nhập. Tại staging, xác minh host và proxy thực tế khớp origin dự kiến.

Nếu chỉ có client hiện đại, có thể dùng WebSocket thuần như trên. Thêm `.withSockJS()` chỉ khi sản phẩm thật cần fallback transports và đã kiểm tra các ngoại lệ HTTP CSRF/iframe liên quan.

## 5. HTTP SecurityFilterChain cho handshake và token endpoint

Ứng dụng portal tiếp tục dùng Spring Security Servlet để bảo vệ đường đăng nhập, cấp CSRF token và bắt đầu WebSocket handshake.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/css/**", "/js/**", "/error")
                    .permitAll()
                .requestMatchers("/csrf", "/ws", "/ws/**")
                    .authenticated()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là ví dụ tối giản cho portal dùng session. Nếu hệ thống có nhiều SecurityFilterChain hoặc servlet context path khác, cần xác nhận handshake request và `GET /csrf` đi qua chain được định nghĩa. Đừng tắt HTTP CSRF toàn ứng dụng để làm STOMP kết nối được.

Các lớp bảo vệ HTTP đã học vẫn có vai trò:

| Lớp bảo vệ | Tác dụng trong bài | Giới hạn |
|---|---|---|
| TLS và HSTS | Browser phải truy cập portal bằng HTTPS và WebSocket bằng WSS | HSTS không thay thế xác thực hoặc quyền STOMP |
| Session cookie `Secure`/`HttpOnly`/`SameSite` | Hạn chế đường bị lộ hoặc tự gửi cookie không mong muốn | Cookie hợp lệ trong handshake chưa đủ để cho mọi message |
| Allowed Origin ở handshake | Ngăn browser Origin khác mở WebSocket trái chính sách | Origin không thay thế token và principal |
| HTTP CSRF | Chống HTTP POST làm thay đổi dữ liệu; liên quan SockJS fallback | Không tương đương CSRF của STOMP CONNECT |
| CSP `connect-src` | Có thể hạn chế JavaScript trong trang mở kết nối tới WSS ngoài dự kiến | Không bảo vệ server trước client tùy ý |
| HTTP firewall | Kiểm soát đường dẫn/request handshake ở Servlet | Không thay thế phân quyền destination trong STOMP |

Ví dụ, CSP trên trang portal có thể cần `connect-src 'self' wss://portal.example.test`. Kiểm tra browser thật vì cách đối chiếu `'self'` và scheme WebSocket khác nhau theo môi trường, và header của tài liệu HTML mới là nơi áp dụng CSP cho script.

## 6. Bảo vệ STOMP CONNECT bằng CSRF token

### 6.1. CSRF phải nằm trong STOMP CONNECT native headers

Khi dùng `@EnableWebSocketSecurity`, Spring Security yêu cầu CSRF token hợp lệ cho STOMP CONNECT theo cơ chế bảo vệ same origin. Token được tạo/xác minh trong HTTP security context tương ứng, nhưng **client phải gửi token trong header của frame STOMP CONNECT**, không chỉ trong header HTTP Upgrade.

Ví dụ frame hợp lệ ở mức giao thức (tên token/header thay theo cấu hình ứng dụng):

~~~text
CONNECT
accept-version:1.2
host:portal.example.test
X-CSRF-TOKEN:<token-cua-dung-session>

^@
~~~

Ký hiệu `^@` biểu diễn byte kết thúc STOMP frame `NUL (0x00)`, không phải hai ký tự `^` và `@` gửi thật trên mạng. Trong client, dùng thư viện STOMP để tạo frame thay vì tự tạo chuỗi thủ công.

Frame không có token, token không khớp hoặc từ session khác **không được đạt trạng thái STOMP CONNECTED**. Tùy phiên bản và cách đóng transport, client có thể nhận frame `ERROR`, sự kiện close, handshake lỗi hoặc exception; không nhất thiết có HTTP 403 ở bước này, vì HTTP handshake có thể đã trả 101 trước đó.

### 6.2. Cấp token cho JavaScript từ HTTP endpoint

Một cách dễ kiểm chứng là dùng endpoint JSON chỉ phục vụ người đã đăng nhập:

~~~java
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfTokenController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
~~~

Spring Security có thể trả JSON gồm `headerName`, `parameterName` và `token`. Client cần dùng tên header thực tế, vì tên có thể thay đổi theo `CsrfTokenRepository`.

Yêu cầu bảo mật cho endpoint:

- Chỉ người đã xác thực sử dụng nếu nghiệp vụ yêu cầu, không cấp quyền CORS cho Origin lạ đọc token.
- Response chứa token không được lưu ở shared cache; cấu hình cache phù hợp và kiểm tra response thực qua proxy.
- Không đưa token vào query string, URL WebSocket, log, telemetry hay source được phát hành.
- Khi login/logout hoặc CSRF token xoay vòng, client phải lấy token mới trước lần CONNECT tiếp theo.

### 6.3. Browser STOMP client lấy token trước mỗi lần CONNECT

Ví dụ dùng thư viện `@stomp/stompjs`:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "wss://portal.example.test/ws",
  reconnectDelay: 5000,

  // Được gọi trước cả CONNECT đầu tiên và các lần reconnect.
  beforeConnect: async () => {
    const response = await fetch("/csrf", {
      credentials: "same-origin",
      cache: "no-store"
    });
    if (!response.ok) {
      throw new Error("Không lấy được CSRF token cho STOMP CONNECT");
    }

    const csrf = await response.json();
    client.connectHeaders = {
      [csrf.headerName]: csrf.token
    };
  },

  onConnect: () => {
    client.subscribe("/topic/general", (frame) => {
      // Parse dữ liệu đã validate, hiển thị bằng textContent.
      console.log("Đã nhận message", frame.headers["message-id"]);
    });
  },

  onStompError: (frame) => {
    console.error("STOMP bị từ chối", frame.headers.message);
  },

  onWebSocketClose: () => {
    console.info("WebSocket đã đóng");
  }
});

client.activate();
~~~

Code trên cho thấy **thứ tự** quan trọng: client phải có session HTTP hợp lệ → lấy token cùng phiên → đưa token vào `connectHeaders` → gửi CONNECT → chờ callback `onConnect` rồi mới SUBSCRIBE/SEND.

`onStompError` không bảo đảm được gọi cho mọi lỗi: một server/proxy có thể đóng WebSocket mà không phát frame ERROR. Trong kiểm thử phải ghi nhận cả STOMP ERROR, close event, failed connection và trạng thái handler không được chạy.

Với SockJS client, có thể thay `brokerURL` bằng `webSocketFactory: () => new SockJS("/ws")` và giữ việc gửi CSRF ở `connectHeaders`. Không cố gắn CSRF token vào HTTP Upgrade hoặc URL query để giải quyết CSRF CONNECT.

## 7. Phân quyền MESSAGE và SUBSCRIBE ở clientInboundChannel

### 7.1. Cấu hình `AuthorizationManager<Message<?>>`

Spring Security có hỗ trợ authorizing message theo loại STOMP command và destination. Với mô hình chat:

~~~java
import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept
        .MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class MessagingSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/chat.send").hasRole("USER")
            .simpSubscribeDestMatchers(
                "/topic/general",
                "/user/queue/replies"
            ).hasRole("USER")
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Giải thích:

- `nullDestMatcher().authenticated()` yêu cầu principal đã xác thực với các message không có destination, trong đó có các command điều khiển kết nối; CSRF CONNECT được kiểm tra riêng bởi lớp messaging CSRF.
- `simpDestMatchers("/app/chat.send")` cho phép chủ thể có `ROLE_USER` gửi tới application destination cụ thể. Endpoint thực tế trong ví dụ không dùng đường khác, nên không cấp `/app/**` tùy ý.
- `simpSubscribeDestMatchers(...)` cấp quyền subscribe hai destination được liệt kê. Không đồng nghĩa cho phép SEND tới các destination đó.
- `simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()` chặn mọi SEND/SUBSCRIBE còn lại, đặc biệt client SEND thẳng vào `/topic/**` hoặc SUBSCRIBE `/queue/**`.
- `anyMessage().denyAll()` là fallback từ chối command không được định nghĩa. Khi đưa thêm `UNSUBSCRIBE`/receipt/command hợp lệ vào sản phẩm cần thiết kế các quy tắc phù hợp, không mở toàn bộ quyền.

**Thứ tự matcher rất quan trọng:** các rule cụ thể được áp dụng trước fallback deny. Việc thêm `.anyMessage().permitAll()` để sửa lỗi “không subscribe được” có thể vô tình mở các loại message ngoài ý muốn.

Spring Security chỉ trực tiếp bảo vệ **clientInboundChannel**. Nó không tự chặn từng frame ở `clientOutboundChannel`. Vì vậy **quyền SUBSCRIBE phải đúng** ngay từ đầu; nếu client đã subscribe được vào broker destination nhạy cảm, chờ chặn khi message được phát ra là quá muộn.

### 7.2. Broker destination và user destination

| Client frame | Destination | Quyết định trong policy ví dụ | Lý do |
|---|---|---|---|
| `SEND` | `/app/chat.send` | Cho phép với ROLE_USER | Dữ liệu đi qua controller |
| `SUBSCRIBE` | `/topic/general` | Cho phép với ROLE_USER | Topic dùng chung cho thành viên hợp lệ |
| `SUBSCRIBE` | `/user/queue/replies` | Cho phép với ROLE_USER | User destination cho phản hồi cá nhân |
| `SEND` | `/topic/general` | Từ chối | Client không thể đóng giả server để broadcast |
| `SEND` | `/queue/replies` | Từ chối | Không cho phép gửi thẳng vào broker queue |
| `SUBSCRIBE` | `/queue/replies` | Từ chối | Broker prefix trực tiếp không thuộc client |
| `SUBSCRIBE` | `/topic/admin` | Từ chối | Chưa có rule cho topic nhạy cảm |
| `SEND` | `/app/admin.reset` | Từ chối | Controller không được mở qua quyền chung |
| `SUBSCRIBE` | `/topic/rooms/secret` | Từ chối | Room động chưa có quyền riêng |

Nếu hệ thống cần các kênh như `/topic/rooms/{roomId}`, không đủ để viết `.simpSubscribeDestMatchers("/topic/rooms/**").authenticated()`. Cần kiểm tra **principal có là thành viên của room đó không**, thông qua authorization manager theo destination hoặc interceptor đáng tin, trước khi tạo subscription. Khi người dùng bị thu hồi quyền trong lúc đang kết nối, cần chính sách hủy subscription/đóng session hoặc tái đánh giá quyền thích hợp.

## 8. Xử lý message phải kiểm tra dữ liệu nghiệp vụ

Chặn destination ở tầng messaging ngăn nhiều kiểu bypass, nhưng vẫn cần validate payload và xác định người gửi bằng principal thật:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

record ChatCommand(
    @NotBlank @Size(max = 500) String text
) {}

record ChatEvent(String sender, String text) {}

@Controller
public class ChatController {

    private final SimpMessagingTemplate messaging;

    public ChatController(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    @MessageMapping("/chat.send")
    public void send(@Valid @Payload ChatCommand input,
                     Principal principal) {
        String sender = principal.getName();
        ChatEvent event = new ChatEvent(sender, input.text());
        messaging.convertAndSend("/topic/general", event);
    }
}
~~~

Thêm dependency validation tương ứng nếu ứng dụng chưa có. Kiểm tra giới hạn nội dung, logic anti-spam/rate-limit và dữ liệu đầu vào ở server; chỉ áp dụng chức năng hiển thị an toàn ở client (ví dụ gán `textContent`) với chuỗi do người dùng nhập.

**Không tin các trường `sender`, `userId`, `roomId` do client cung cấp để xác định quyền**. Nếu frame payload chứa `{"sender":"admin","text":"..."}`, server không được gửi đi với sender từ payload. Với room riêng, controller kiểm tra thành viên lại khi gửi, còn quyền SUBSCRIBE phải được chặn ở inbound **trước khi broker nhận subscription**.

Nếu gửi riêng cho người dùng:

~~~java
messaging.convertAndSendToUser(
    recipientUsername,
    "/queue/replies",
    replyPayload
);
~~~

Client nhận từ `/user/queue/replies`; không bao giờ cho phép client tự tạo subscription tới queue vật lý chứa session ID của người khác. Đối với dữ liệu nhiều bên thuê (multi-tenant), principal, tenant ID và room ID đều phải được kiểm tra, không suy từ prefix đường dẫn.

## 9. SockJS fallback và xung đột CSRF HTTP

Nếu cần browser/transport cũ, cấu hình endpoint:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setAllowedOrigins("https://portal.example.test")
            .withSockJS();
}
~~~

SockJS có thể dùng nhiều HTTP POST để gửi frame thay vì WebSocket thuần. POST đó đi qua **HTTP CSRF filter** và có thể bị chặn trước khi frame STOMP được phân tích, do SockJS browser client không dễ đặt một HTTP CSRF header riêng vào mọi transport request.

Khi **thật sự dùng SockJS**, tài liệu Spring Security hướng dẫn chỉ bỏ qua HTTP CSRF cho đường transport SockJS, vì CSRF của STOMP CONNECT vẫn được yêu cầu:

~~~java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/ws/**")
);
~~~

Đoạn này là **ngoại lệ có phạm vi hẹp** cho SockJS transport tại `/ws/**`; phải bảo đảm mọi route dưới prefix đó chỉ phục vụ SockJS, không lẫn REST endpoint thay đổi trạng thái. Không dùng `csrf.disable()` cho toàn bộ portal và không vô hiệu hóa CSRF trong STOMP CONNECT chỉ để tránh lỗi kết nối.

Một số SockJS fallback dùng iframe cùng origin. Nếu hỗ trợ các transport đó, `X-Frame-Options: DENY` hoặc CSP `frame-ancestors 'none'` có thể chặn iframe. Chỉ điều chỉnh sang `SAMEORIGIN` / `frame-ancestors 'self'` khi kiến trúc thật sự cần, sau khi đánh giá clickjacking. Không tự mở iframe cho Origin bên ngoài.

**Điểm cần kiểm thử:** WebSocket native thành công không chứng minh fallback SockJS POST/iframe thành công. Hãy ép chạy một transport fallback trên staging hoặc kiểm thử trình duyệt tương ứng, rồi quan sát HTTP status, CSRF CONNECT, frame security và chính sách frame.

## 10. Nếu ứng dụng dùng bearer token ở STOMP CONNECT

Một số ứng dụng SPA/mobile không dùng session cookie. Browser WebSocket API không cho JavaScript tự đặt tùy ý header HTTP `Authorization` trong handshake; STOMP library lại cho phép đặt native header trong CONNECT. Khi đó có thể tạo `ChannelInterceptor` xử lý riêng CONNECT:

~~~java
// Mã khung minh họa cơ chế, không phải bộ xác thực JWT đầy đủ.
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    StompHeaderAccessor accessor =
        MessageHeaderAccessor.getAccessor(message, StompHeaderAccessor.class);

    if (accessor != null &&
            StompCommand.CONNECT.equals(accessor.getCommand())) {
        String authorization =
            accessor.getFirstNativeHeader("Authorization");

        // Bắt buộc kiểm tra cấu trúc, chữ ký, issuer, audience,
        // thời hạn, quyền và khả năng thu hồi theo chính sách.
        Authentication authentication =
            authenticateBearerToken(authorization);

        accessor.setUser(authentication);
    }
    return message;
}
~~~

Đây là **phác thảo**: `authenticateBearerToken(...)` là nghiệp vụ bắt buộc tự triển khai/tích hợp bằng JWT decoder hay AuthenticationManager phù hợp. Không sử dụng chuỗi token chưa xác minh để tạo Principal. Nếu đăng ký interceptor xác thực, cần đặt **trước interceptor phân quyền của Spring Security**, chẳng hạn theo hướng dẫn đăng ký một `WebSocketMessageBrokerConfigurer` độc lập có `@Order(Ordered.HIGHEST_PRECEDENCE + 99)`.

**Ranh giới CSRF:** `@EnableWebSocketSecurity` vẫn mặc định yêu cầu CSRF cho CONNECT. Ở các bản Spring Security được tài liệu hóa, việc tắt yêu cầu CSRF qua annotation này không có tùy chọn cấu hình đơn giản; nếu ứng dụng bearer-only có lý do chuyên môn để bỏ CSRF CONNECT thì cần cấu hình messaging security thủ công theo tài liệu chính thức và đánh giá lại Origin, token handling, cách lưu token, quyền và session. Không bỏ CSRF hoặc nới Origin chỉ vì client gặp lỗi.

Không đưa bearer token vào URL query WebSocket; URL có thể xuất hiện ở access log, proxy và monitoring. Không ghi full token ở frame debug logs.

## 11. Thiết kế bộ kiểm thử theo ba lớp

Đánh giá kỹ thuật phải qua cả **HTTP handshake**, **STOMP CONNECT** và **message authorization**. Mock HTTP endpoint có thể xác nhận bảo vệ login và Origin nhưng không chứng minh handler STOMP được bảo vệ. Ngược lại, test mỗi rule AuthorizationManager riêng không chứng minh client đã gửi đúng token từ browser.

### 11.1. Ma trận test âm tính và dương tính

| ID | Tiền điều kiện / hành động | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| H01 | User đã đăng nhập, đúng Origin, mở `wss://portal.example.test/ws` | HTTP handshake thành công, thường 101 | Network handshake, cookie/Origin đã che dữ liệu |
| H02 | Chưa đăng nhập, mở `/ws` | Không cấp quyền như user hợp lệ (có thể 302/401/403 tùy HTTP chain) | HTTP response và không có STOMP CONNECTED |
| H03 | Trang Origin lạ cố mở WS với cookie nạn nhân | Handshake bị từ chối theo allowed origins | Browser/HTTP response, kết nối không được thiết lập |
| C01 | Handshake hợp lệ, STOMP CONNECT thiếu CSRF | Không nhận `CONNECTED` | STOMP ERROR/close và log không chứa token |
| C02 | CONNECT mang CSRF token sai | Không nhận `CONNECTED` | ERROR/close |
| C03 | CONNECT mang token từ phiên khác | Không nhận `CONNECTED` | ERROR/close; kiểm tra phiên trước |
| C04 | CONNECT mang token đúng của phiên đăng nhập | Nhận STOMP `CONNECTED` | Sự kiện connected và principal mong đợi |
| A01 | `ROLE_USER` subscribe `/topic/general` | Cho phép, nhận message hợp lệ | Callback nhận tin |
| A02 | `ROLE_USER` subscribe `/user/queue/replies` | Cho phép, chỉ nhận tin gửi cho mình | Callback user A và B |
| A03 | `ROLE_USER` send `/app/chat.send` hợp lệ | Handler chạy, message phát với sender thật | Event được broker phát và audit |
| A04 | Client SEND trực tiếp `/topic/general` | Bị từ chối, không tạo broadcast | Không có side effect tại subscriber |
| A05 | Client SUBSCRIBE trực tiếp `/queue/replies` | Bị từ chối, không đọc queue vật lý | Không nhận message riêng |
| A06 | Client subscribe `/topic/admin` | Bị từ chối | ERROR/close hoặc không có subscription |
| A07 | Payload khai `sender=admin` nhưng principal là user thường | Event sender vẫn bằng principal thật | Payload nhận được, log kiểm thử |
| A08 | Gửi payload rỗng/quá dài hoặc sai JSON | Validation từ chối; không phát message lỗi | Exception/error handler + không có side effect |
| A09 | User A cố subscribe room của user B | Bị từ chối theo membership | Không nhận sự kiện của B |
| S01 | Logout/hết hạn trong khi WebSocket còn mở | Theo chính sách: đóng session hoặc không còn được gửi/nhận nội dung nhạy cảm | Session lifecycle + request và frames sau logout |
| K01 | SockJS fallback nếu bật | HTTP transport hợp lệ, CONNECT còn kiểm tra token | Network HTTP POST + STOMP frames |
| P01 | Qua proxy WSS và reverse proxy thật | Upgrade/Origin/TLS/session đúng, frame policy vẫn hoạt động | Response cuối cùng và logs theo request ID |

**Cách đọc status:** H03 có thể kết thúc bằng HTTP 403 hoặc handshake failure. C01–C03 xảy ra **sau** handshake thành công, nên không cố chờ một HTTP 403 ở STOMP CONNECT; kiểm tra loại frame và việc handler/subscription không được thực thi. Khi một error đóng toàn bộ session, tạo kết nối mới cho từng negative case để kiểm thử độc lập.

### 11.2. Kiểm thử HTTP handshake và token endpoint

Dùng browser DevTools Network hoặc công cụ WebSocket có khả năng gửi Origin/cookie và STOMP frames. Để kiểm chứng token endpoint có đúng quyền và không bị cache dùng chung:

~~~bash
curl -i "https://portal.example.test/csrf"
~~~

Kỳ vọng khi **không có session đăng nhập** là endpoint không cung cấp token theo chính sách ở mục 5 (có thể redirect sang login hoặc trả 401). Khi đã đăng nhập trong môi trường test, gọi cùng cookie jar để lấy token; không in/ghi token vào CI logs hay lưu credential vào repo.

Đừng dùng `curl -H "Origin: ..."` làm bằng chứng cuối cùng của trình duyệt: client HTTP có thể tự đặt Origin giả. Quan sát handshake trực tiếp trong browser của hai origin và xác nhận policy hoạt động.

### 11.3. Integration test bằng Spring WebSocketStompClient

Spring Framework cung cấp `WebSocketStompClient` để gửi STOMP CONNECT đến server đang chạy. Mẫu cấu trúc kiểm thử với Spring Framework 6+:

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.http.HttpHeaders;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;
import org.springframework.web.socket.WebSocketHttpHeaders;

// Trong integration test chạy server thật, lấy cookie/token bằng
// HTTP login test account trước khi khởi tạo STOMP client.
WebSocketStompClient stomp =
    new WebSocketStompClient(new StandardWebSocketClient());

WebSocketHttpHeaders handshake = new WebSocketHttpHeaders();
handshake.add(HttpHeaders.COOKIE, sessionCookieHeader);
handshake.setOrigin("https://portal.example.test");

StompHeaders connect = new StompHeaders();
connect.add(csrfHeaderName, csrfToken);

StompSession session = stomp.connectAsync(
    "ws://localhost:" + port + "/ws",
    handshake,
    connect,
    new StompSessionHandlerAdapter() {}
).get(5, TimeUnit.SECONDS);

// Future hoàn tất khi STOMP CONNECTED đã đến.
assert session.isConnected();
session.disconnect();
~~~

Đoạn minh họa giả định các biến `sessionCookieHeader`, `csrfHeaderName`, `csrfToken` và `port` được chuẩn bị từ bước login HTTP thực. Kết nối `ws://localhost` chỉ dành cho integration test nội bộ; staging/production phải kiểm tra `wss://` qua proxy. Có thể cần custom message converter/handler và một test timeout phù hợp với ứng dụng.

Các phép thử âm tính lặp lại phần khởi tạo với `connect` rỗng, token sai và token của session khác. Với negative case, ghi nhận `ERROR`, đóng WebSocket hoặc future thất bại. Kết quả âm tính chỉ PASS khi **không nhận CONNECTED và không có side effect**; không chấp nhận “timeout do server không chạy” làm PASS.

### 11.4. Kiểm thử message có hai người dùng

Một bài test thực tế dùng hai phiên độc lập A và B:

1. A đăng nhập, lấy token, STOMP CONNECTED và subscribe `/topic/general`, `/user/queue/replies`.
2. B đăng nhập bằng phiên riêng, CONNECTED và subscribe các kênh tương ứng.
3. A SEND `/app/chat.send` với payload hợp lệ. Xác nhận thông báo chung đến subscriber và sender được server tạo từ principal A.
4. A thử SEND trực tiếp `/topic/general`. Xác nhận không có message mới được broadcast từ đường gửi trái phép.
5. Server gửi private event cho B bằng `convertAndSendToUser("B", "/queue/replies", event)`. B nhận, A không nhận.
6. A thử SUBSCRIBE `/queue/replies` hoặc một destination private thuộc B. Kiểm tra không có event lộ ra.
7. A gửi payload giả `sender: "B"`. Kiểm tra sender ở event đầu ra vẫn bằng A hoặc request bị validation từ chối.
8. Nếu có room riêng, A thử subscribe room mà B sở hữu. Kiểm tra quyền theo membership trước khi message nhạy cảm được broadcast.

Để tránh false PASS, mỗi sự kiện test nên có **ID duy nhất**, assertion theo ID và một khoảng chờ có timeout cụ thể. “Không nhận message trong 1 ms” không đủ để chứng minh không rò rỉ; kiểm tra cả subscription có bị từ chối, broker không đăng ký trái phép và sự kiện đã thực sự được phát cho recipient hợp lệ.

### 11.5. Trình duyệt thật và trang Origin lạ

Tạo trang kiểm thử tại `https://attacker.example.test/ws-check`:

~~~html
<button id="probe">Thử WebSocket cross-origin</button>
<script>
document.getElementById("probe").onclick = () => {
  const ws = new WebSocket("wss://portal.example.test/ws");
  ws.onopen = () => console.log("UNEXPECTED: handshake opened");
  ws.onerror = () => console.log("WebSocket rejected");
  ws.onclose = (event) => console.log("closed", event.code);
};
</script>
~~~

Truy cập trang này trên browser đã có phiên đăng nhập portal; xác nhận server từ chối Origin ngoài allowlist. Trang fixture phải cho phép outbound WSS trong **CSP của chính nó**, nếu không browser chặn ngay ở `connect-src` và tạo ra một PASS giả về Origin restriction của server.

Lưu ý: một trang độc hại cùng origin do XSS có thể truy cập token hợp lệ; bảo vệ CSRF/Origin không thay thế phòng chống XSS. Trên portal phải tiếp tục áp dụng CSP, output encoding và validation.

### 11.6. Kiểm tra quyền ở tầng AuthorizationManager

Ngoài integration test, có thể kiểm thử từng rule của bean `AuthorizationManager<Message<?>>` bằng các `Message<?>` giả lập có `SimpMessageType`, destination và authentication tương ứng. Cần xác nhận:

- Một message loại `MESSAGE` tới `/app/chat.send` với `ROLE_USER` được cấp quyền.
- Message loại `SUBSCRIBE` tới `/topic/general` hoặc `/user/queue/replies` với `ROLE_USER` được cấp quyền.
- Message loại `MESSAGE` tới `/topic/general` bị từ chối.
- Subscribe trực tiếp `/queue/**` hoặc `/topic/admin` bị từ chối.
- Authentication bị thiếu/anonymous không được chấp nhận khi chính sách yêu cầu đăng nhập.

Unit test của manager giúp phát hiện lỗi thứ tự matcher. **Nó không chứng minh CSRF CONNECT** hoặc principal có được lấy đúng từ HTTP session; những đường đó cần integration test với WebSocketStompClient/browser.

## 12. Reactive/WebFlux: giới hạn phạm vi áp dụng

Ví dụ trong bài dùng Spring MVC/Servlet và Spring Messaging broker với `@EnableWebSocketMessageBroker`, `@EnableWebSocketSecurity`. Không tự gắn mẫu này lên ứng dụng WebFlux chỉ dùng `org.springframework.web.reactive.socket.WebSocketHandler` rồi mặc định cho rằng đã có STOMP authorization.

Nếu hệ thống Reactive sử dụng WebSocketHandler nhận frame riêng hoặc tự triển khai STOMP:

- HTTP handshake đi qua `SecurityWebFilterChain` và security context Reactive theo cách triển khai.
- Cần xác thực người dùng/kênh, kiểm tra Origin và thiết kế CSRF phù hợp với việc browser tự gửi cookie.
- Handler phải kiểm tra quyền theo **từng loại message và destination nghiệp vụ**, đồng thời tránh để client chọn người nhận tùy ý.
- Những class/rule dành riêng cho `clientInboundChannel` của Spring Messaging STOMP không tự tồn tại trong một raw WebFlux WebSocketHandler.
- Dùng `WebTestClient` để kiểm tra HTTP route và reactive filter chain; dùng WebSocket client chạy qua mạng để xác minh handshake và message thực, tương tự phần kiểm thử Servlet.

Nếu dự án vận hành Spring Messaging STOMP qua một lớp tích hợp khác, trước tiên xác định công nghệ xử lý STOMP thật sự và middleware nào quyết định quyền, rồi viết kiểm thử cho **đúng đường đi**. CORS của HTTP và kiểm tra Origin khi WebSocket handshake không phải là cùng một cơ chế.

## 13. Chẩn đoán các lỗi hay gặp

| Hiện tượng | Giả thuyết chính | Cách kiểm tra |
|---|---|---|
| HTTP handshake trả 101 nhưng `onConnect` không chạy | CONNECT thiếu/sai CSRF, user chưa xác thực ở messaging, frame sai format | Network → WebSocket frames, token/session, security logs |
| Chỉ kết nối được khi tắt CSRF toàn ứng dụng | Client không gửi token trong STOMP CONNECT hoặc SockJS POST bị HTTP CSRF chặn | Tách rõ HTTP POST và STOMP CONNECT, kiểm tra `connectHeaders` |
| CONNECT có `Authorization` nhưng principal là anonymous | Spring không mặc định xác thực native bearer header | Kiểm tra `ChannelInterceptor` xác thực token và thứ tự interceptor |
| Bị từ chối khi subscribe `/topic/general` dù đã kết nối | Rule SUBSCRIBE, role, destination hoặc matcher bị sai | Kiểm tra message type và principal, rule trước `denyAll` |
| SEND `/topic/general` thành công và client khác nhận tin | Rule mở broker prefix quá rộng | Chặn MESSAGE tới `/topic/**` và `/queue/**`, chỉ mở controller destination |
| A đọc được queue của B | Cho phép subscription broker queue trực tiếp hoặc membership sai | Chặn subscribe trực tiếp `/queue/**`, dùng user destination và test hai tài khoản |
| Cross-origin browser vẫn mở được WS | `setAllowedOrigins("*")`, proxy làm sai Origin, endpoint khác cấu hình | Kiểm tra request Origin và endpoint được matcher thực sự |
| SockJS fallback POST nhận 403 HTTP | HTTP CSRF chặn POST SockJS trước STOMP | Ngoại lệ hẹp cho `/ws/**` khi dùng SockJS, vẫn giữ CSRF CONNECT |
| SockJS iframe bị chặn | `X-Frame-Options` hoặc `frame-ancestors` không phù hợp | Chỉ cho same-origin frame nếu transport thực sự cần |
| WSS hỏng qua proxy nhưng WS local chạy | Upgrade/Connection headers, timeout, TLS, sticky session | Quan sát response edge, proxy logs và HTTP session continuity |
| Sau logout socket cũ vẫn nhận message | Session WS sống riêng, chưa có chính sách đóng/hủy quyền | Test logout trong khi socket mở; thiết kế close/revocation |
| CSP báo lỗi `connect-src` | HTML policy không cho phép WSS hoặc Origin socket | Kiểm tra CSP của tài liệu HTML, WSS URL |
| Test đôi khi PASS đôi khi FAIL | Race khi subscribe, sự kiện gửi trước khi subscribe xong, timeout quá thấp | Đồng bộ theo callback/receipt phù hợp và correlation ID |

**Chú ý xử lý lỗi:** một số server đóng socket ngay sau frame bị từ chối, nên không thể mặc định mong một frame STOMP ERROR. Khi kết nối lỗi, kiểm tra lần lượt HTTP handshake, Origin/cookie, STOMP CONNECT frame, CSRF, principal, authorization matcher, handler và broker thay vì đổi cấu hình ngẫu nhiên.

## 14. Thực hành đánh giá kết quả và rủi ro còn lại

Một phiếu báo cáo cho từng case:

~~~yaml
testId: "C01"
threatId: "W03"
environment: "staging"
buildRevision: "<app-build>"
configurationRevision: "<security-config>"
session: "Đã login với user A; cookie được ẩn"
action: "STOMP CONNECT thiếu header CSRF"
expected:
  stompConnected: false
  handlerExecuted: false
observed:
  stompConnected: "<true-or-false>"
  connectionEvent: "<ERROR|CLOSE|TIMEOUT|CONNECTED>"
  handlerExecuted: "<true-or-false>"
evidence:
  - "stomp-frames-redacted.txt"
  - "authorization-logs-redacted.txt"
verdict: "<PASS|FAIL|INCONCLUSIVE>"
residualRisk: "<mo-ta-rui-ro-con-lai>"
~~~

**Không đánh dấu PASS từ kết quả kỳ vọng.** Một timeout do proxy mất kết nối, server chưa khởi động hoặc fixture không có session là `INCONCLUSIVE`. Một positive case không hoạt động cũng là lỗi cần điều tra. Kết quả thực phải ghi rõ bản build/config và đường đi qua network.

Bằng chứng nên gồm:

1. Handshake request/response đã che cookie và token.
2. Tóm tắt STOMP CONNECT/CONNECTED/ERROR/CLOSE, loại frame và destination (không lưu secret/token).
3. Principal/role đã xác nhận (hoặc nhãn vô danh), quyền subscription và lý do từ chối.
4. Correlation ID cho message gửi/nhận và dữ liệu trước/sau handler khi có side effect.
5. Test với hai session độc lập để chứng minh private queue không lộ.
6. Kết quả kiểm thử Origin lạ từ browser thật và WSS qua proxy.

### 14.1. Tiêu chí nghiệm thu

Có thể xem bài thực hành đạt khi thỏa tất cả điều kiện áp dụng:

- Handshake chỉ chấp nhận origin và người dùng phù hợp; không dùng Origin thay cho authentication.
- CONNECT thiếu, sai hoặc dùng CSRF token của phiên khác không được nhận `CONNECTED`; CONNECT hợp lệ đạt `CONNECTED`.
- Chính sách phân quyền chặn client gửi tới broker destination và subscribe channel chưa được phê duyệt.
- Handler không tin sender do client khai báo, dùng principal đáng tin và validate payload.
- Private message chỉ đến người được phép; nếu có room/tenant riêng phải kiểm tra membership.
- Test có cả trường hợp hợp lệ và bất hợp lệ, đánh giá side effect và không dựa vào status/timeout đơn lẻ.
- Nếu dùng SockJS, HTTP POST fallback vẫn hoạt động trong phạm vi ngoại lệ hẹp và STOMP CONNECT còn được bảo vệ.
- Hành vi logout, hết hạn session và lỗi WSS/proxy được đánh giá theo chính sách rõ ràng.
- Không bỏ qua CSRF trên các HTTP endpoint nghiệp vụ, không cấp wildcard broker subscription, không ghi token ra log.

## 15. Bài tập tự kiểm tra

**Bài tập 1 — Bảo vệ CONNECT.** Trên môi trường test, đăng nhập portal bằng hai phiên A/B. Lấy CSRF token của phiên A, thử CONNECT lần lượt không token, token giả, token A và token A với cookie B. Ghi lại HTTP handshake, STOMP kết quả và lý do. Giải thích tại sao handshake 101 không đồng nghĩa CONNECT thành công.

**Bài tập 2 — Phân quyền broker destination.** Tạo hai STOMP client đã xác thực. Cho A subscribe `/topic/general` và `/user/queue/replies`, sau đó gửi `SEND /app/chat.send`. Thử gửi `SEND /topic/general` và subscribe `/queue/**`; xác minh không có broadcast hoặc rò rỉ trái phép.

**Bài tập 3 — Phát hiện giả mạo người gửi.** Gửi JSON có `sender=admin` từ tài khoản thường; chứng minh server sử dụng principal thật. Thêm trường hợp payload quá dài và message tới room không thuộc quyền rồi kiểm tra dữ liệu nghiệp vụ không bị tác động.

**Bài tập 4 — SockJS và trình duyệt.** Nếu sản phẩm bật SockJS, ép dùng fallback POST hoặc iframe trên staging. Chẩn đoán chỗ nào là HTTP CSRF, STOMP CSRF, `X-Frame-Options` hoặc CSP. Chỉ cấu hình ngoại lệ có phạm vi thật sự cần thiết.

**Bài tập 5 — Phân tích vòng đời phiên.** Đang kết nối STOMP thì thực hiện logout HTTP, thu hồi quyền user hoặc hết hạn session. Kiểm tra socket có bị đóng và message nhạy cảm còn có thể được gửi/nhận hay không. Đề xuất test hồi quy và chính sách thu hồi phù hợp với sản phẩm.

## 16. Tài liệu tham khảo

- [Spring Security — WebSocket Security (Servlet)](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework — Token Authentication cho STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework — Annotated Controllers và @MessageMapping](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [OWASP — Cross-Site WebSocket Hijacking (WebSocket Security Cheat Sheet)](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)
