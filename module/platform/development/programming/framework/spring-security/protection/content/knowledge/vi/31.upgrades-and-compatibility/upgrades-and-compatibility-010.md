# Chuyển cấu hình WebSocket cũ sang mô hình được hỗ trợ

## 1. Bối cảnh của việc nâng cấp

Bài học thuộc chương **Nâng cấp và tương thích** của module **SPRING_SECURITY_HTTP_PROTECTION**. Module tập trung vào các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS, HTTP firewall đến session, trên cả Servlet và Reactive. Trong chủ đề này, bài toán cụ thể là **nâng cấp bảo mật WebSocket/STOMP của ứng dụng Servlet**, đồng thời bảo toàn các quy tắc xác thực, phân quyền và chống truy cập chéo origin đã hoạt động trước đó.

Nhiều dự án Spring MVC từng bảo vệ STOMP bằng cách kế thừa **AbstractSecurityWebSocketMessageBrokerConfigurer** và ghi quy tắc trong **MessageSecurityMetadataSourceRegistry**. Spring Security 5.8 bổ sung cách cấu hình bằng **AuthorizationManager**, kết hợp annotation **@EnableWebSocketSecurity** và bean **AuthorizationManager<Message<?>>**. API cũ đã bị loại bỏ ở Spring Security 7, nên mã kế thừa cấu hình cũ không còn là đường nâng cấp phù hợp.

Mục tiêu của việc chuyển đổi là giữ nguyên hợp đồng bảo mật ở những ranh giới sau:

1. Request HTTP mở đầu **WebSocket handshake** phải được xác thực, và chỉ origin phù hợp được chấp nhận.
2. STOMP **CONNECT** phải mang thông tin xác thực được kế thừa đúng từ HTTP và CSRF token hợp lệ theo mặc định.
3. Mỗi frame **SEND/MESSAGE** hoặc **SUBSCRIBE** phải được kiểm tra theo loại frame, destination và vai trò/nguồn lực mà người dùng được truy cập.
4. Không để client gửi trực tiếp tới các destination chỉ dành cho broker hoặc đăng ký nhận dữ liệu của người khác.
5. Các bước bảo vệ session, cookie, HTTPS, reverse proxy và frontend vẫn vận hành khi đổi cơ chế authorization.

**Giới hạn phạm vi:** cấu hình Spring Security WebSocket dạng message broker này dành cho **Spring Messaging/STOMP qua WebSocket trong Servlet stack**. Nó không bảo vệ tự động mọi handler WebSocket thuần JSR-356, WebFlux WebSocketHandler hoặc một broker ngoài ứng dụng được kết nối bằng giao thức riêng. Các môi trường này cần đánh giá phương án bảo vệ tương ứng.

## 2. Nhận diện API cũ và đích nâng cấp

| Tình trạng dự án | API thường gặp | Hướng xử lý |
|---|---|---|
| Ứng dụng đời cũ trước Spring Security 5.8 | AbstractSecurityWebSocketMessageBrokerConfigurer, configureInbound, MessageSecurityMetadataSourceRegistry | Chuyển các quy tắc sang AuthorizationManager và kiểm thử lại |
| Spring Security 5.8 và các bản 6.x | API cũ đã deprecated, API AuthorizationManager và @EnableWebSocketSecurity đã sẵn có | Ưu tiên chuyển dần trước lần nâng cấp lớn tiếp theo |
| Spring Security 7 trở lên | Hai lớp cấu hình legacy đã bị loại bỏ | Dùng @EnableWebSocketSecurity và AuthorizationManager<Message<?>> hoặc cách mở rộng messaging được tài liệu hỗ trợ |
| WebSocket thuần không dùng STOMP/Spring Messaging | WebSocketHandler/JSR-356 hoặc xử lý frame tự viết | Thiết kế kiểm soát handshake và message riêng; không áp dụng máy móc cấu hình STOMP |

Các mốc trên nói về **Spring Security**, không đồng nghĩa mọi phiên bản Spring Boot đều tương thích mọi phiên bản Spring Security. Khi nâng cấp, phải chọn một bộ dependency và Java/Jakarta phù hợp với BOM hoặc hướng dẫn tương thích chính thức của phiên bản đang triển khai.

### Hai lớp bảo vệ độc lập

Một kết nối STOMP sử dụng WebSocket có ít nhất hai lần đánh giá bảo mật khác nhau:

~~~mermaid
sequenceDiagram
    actor U as Trình duyệt
    participant H as HTTP SecurityFilterChain
    participant W as WebSocket / STOMP
    participant M as Spring Messaging inbound
    U->>H: HTTP GET /ws + cookie + Origin (Upgrade)
    H->>H: Kiểm tra xác thực và chính sách HTTP
    H->>W: Chấp nhận handshake khi hợp lệ
    U->>W: STOMP CONNECT với CSRF native header
    W->>M: Kiểm tra CSRF CONNECT và Principal
    M-->>U: STOMP CONNECTED khi được chấp nhận
    U->>M: STOMP SEND /app/chat.send
    M->>M: AuthorizationManager cho MESSAGE
    U->>M: STOMP SUBSCRIBE /topic/rooms/general
    M->>M: AuthorizationManager cho SUBSCRIBE
~~~

**SecurityFilterChain** bảo vệ phần HTTP và handshake; **WebSocket message authorization** bảo vệ các frame đi vào sau khi kết nối đã được nâng cấp. Một request handshake thành công không tự cấp quyền gửi hoặc đăng ký mọi destination.

## 3. Ví dụ cấu hình cũ trước khi chuyển đổi

Đây là ví dụ **lịch sử**, chỉ dùng để nhận diện cấu trúc cần di trú. Không sao chép nó vào dự án Spring Security 7:

~~~java
// Mã legacy: minh họa cấu hình trước khi chuyển sang AuthorizationManager.
@Configuration
public class LegacyWebSocketSecurityConfig
        extends AbstractSecurityWebSocketMessageBrokerConfigurer {

    @Override
    protected void configureInbound(
            MessageSecurityMetadataSourceRegistry messages) {
        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/chat.send").hasRole("USER")
            .simpSubscribeDestMatchers(
                "/topic/rooms/*", "/user/queue/**"
            ).hasRole("USER")
            .simpTypeMatchers(
                SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE
            ).denyAll()
            .anyMessage().denyAll();
    }
}
~~~

Hãy đọc quy tắc cũ **theo thứ tự** vì matcher đầu tiên phù hợp có thể quyết định kết quả. Ví dụ trên yêu cầu người gửi/đăng ký thuộc ROLE_USER và từ chối những frame MESSAGE/SUBSCRIBE không nằm trong danh sách cho phép.

Những phần thường cần kiểm kê trước khi thay thế:

- Đường dẫn handshake như /ws, /chat, /socket hoặc đường dẫn SockJS /ws/**.
- Prefix phía ứng dụng như /app/**, prefix broker như /topic/** và /queue/**, prefix user destination /user/**.
- Các luật sử dụng nullDestMatcher, simpDestMatchers, simpSubscribeDestMatchers, simpTypeMatchers, anyMessage.
- Những biểu thức SpEL, custom PermissionEvaluator hoặc SecurityExpressionHandler của cấu hình cũ.
- Cơ chế chứng thực từ session cookie, SSO, token và phần xử lý login/logout của HTTP.
- Client gửi CSRF token trong frame CONNECT, kể cả khi dùng SockJS fallback transport.
- Các endpoint cross-origin được phép, reverse proxy, WSS và đường đi của broker relay.

Đừng chỉ tìm class deprecated rồi xóa. Cần giữ bằng chứng về **quyền của từng loại frame**, vì chuyển nhầm một matcher có thể cho phép client gửi message tới broker topic hoặc theo dõi queue không thuộc quyền.

## 4. Tách cấu hình STOMP transport khỏi cấu hình bảo mật

Spring Framework chịu trách nhiệm đăng ký STOMP endpoint, application destination và broker prefix. Spring Security chịu trách nhiệm xác thực/ủy quyền. Khi bỏ kế thừa cấu hình bảo mật cũ, vẫn phải giữ phần định tuyến STOMP ở một cấu hình Spring Messaging.

Ví dụ ứng dụng trò chuyện với endpoint handshake /ws:

~~~java
package example.chat;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompTransportConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        // Không mở wildcard origin theo thói quen.
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

Trong cấu hình này:

- Client mở WebSocket qua /ws, sau đó gửi frame STOMP.
- Frame SEND tới /app/chat.send được định tuyến đến handler ứng dụng có @MessageMapping("/chat.send").
- Các đích /topic/** và /queue/** được simple broker xử lý; client thường **SUBSCRIBE** vào đó nếu được cấp quyền.
- User destination /user/queue/** giúp định tuyến thông điệp riêng đến phiên/người dùng phù hợp; việc sử dụng prefix này **không thay thế** kiểm tra quyền subscribe.
- Simple broker phù hợp môi trường cơ bản, không phải giải pháp bảo đảm phân tán/cluster hoặc đầy đủ mọi tính năng của broker ngoài.

Nếu cần SockJS, thay đăng ký tương ứng bằng cấu hình sau, rồi thử lại chính sách HTTP CSRF và frame policy:

~~~java
registry.addEndpoint("/ws").withSockJS();
~~~

**Chú ý origin:** endpoint mặc định hạn chế các origin theo chính sách của Spring WebSocket. Nếu sản phẩm thật sự cần frontend khác origin, cấu hình rõ danh sách origin/pattern được tin cậy, ví dụ setAllowedOriginPatterns("https://app.example.test") trên endpoint; đồng thời kiểm thử handshake thật. Không đồng nhất kiểm tra Origin của WebSocket với CORS preflight của fetch thông thường.

## 5. Chuyển sang @EnableWebSocketSecurity và AuthorizationManager

Phiên bản hỗ trợ dùng bean AuthorizationManager<Message<?>> cùng MessageMatcherDelegatingAuthorizationManager.Builder:

~~~java
package example.chat;

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
            .simpMessageDestMatchers("/app/chat.send").hasRole("USER")
            .simpSubscribeDestMatchers(
                "/topic/rooms/*", "/user/queue/**"
            ).hasRole("USER")
            .simpTypeMatchers(
                SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE
            ).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Ở đây, matcher và cách xử lý:

| Cấu hình mới | Frame được bao phủ | Ý nghĩa |
|---|---|---|
| nullDestMatcher().authenticated() | CONNECT/DISCONNECT và frame không mang destination phù hợp | Yêu cầu người dùng có Authentication; CSRF trên CONNECT còn được kiểm tra bởi lớp bảo vệ STOMP |
| simpMessageDestMatchers("/app/chat.send").hasRole("USER") | MESSAGE gửi tới ứng dụng | Chỉ ROLE_USER được gửi nội dung trò chuyện tới handler |
| simpSubscribeDestMatchers("/topic/rooms/*", "/user/queue/**").hasRole("USER") | SUBSCRIBE | Chỉ ROLE_USER đăng ký được các đích cho phép |
| simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll() | MESSAGE hoặc SUBSCRIBE còn lại | Từ chối gửi hoặc đăng ký đích không công bố |
| anyMessage().denyAll() | Mọi frame khác chưa khớp | Chính sách dự phòng kiểu deny by default |

**Vì sao dùng simpMessageDestMatchers thay vì simpDestMatchers?** simpDestMatchers khớp destination mà không xét SimpMessageType, còn simpMessageDestMatchers chỉ khớp MESSAGE. Với các đích /app/** dành cho client SEND, matcher chặt theo loại frame giảm nguy cơ cho phép SUBSCRIBE ngoài ý muốn. Nếu mục tiêu là giữ nguyên chính xác quy tắc legacy cho cả MESSAGE và SUBSCRIBE, cần giữ simpDestMatchers và có test xác minh tác động; việc đổi loại matcher là một thay đổi chính sách cần review.

**Thứ tự rule có ý nghĩa.** Nếu đặt anyMessage().authenticated() ở đầu, các rule denyAll phía sau sẽ không phát huy tác dụng. Nếu đặt simpDestMatchers("/topic/**").authenticated() quá rộng, client có thể SEND trực tiếp vào prefix broker; cách an toàn phổ biến là chỉ cho phép SUBSCRIBE vào topic cần thiết và deny MESSAGE trực tiếp tới broker.

### Xác thực HTTP handshake vẫn là cấu hình riêng

Đối với mô hình session/form login, một SecurityFilterChain đơn giản có thể yêu cầu người dùng xác thực tại endpoint:

~~~java
package example.chat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login").permitAll()
                .requestMatchers("/ws", "/ws/**").authenticated()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Mã trên là một ví dụ dựa vào phiên cookie. Phản hồi từ Spring Security sau login được browser lưu dưới dạng cookie theo cấu hình server/container; khi mở WebSocket, request handshake mang cookie hợp lệ và Spring WebSocket kế thừa Principal từ HttpServletRequest. Không kỳ vọng chỉ gửi các native STOMP header login/passcode là đủ để Spring Security tự tạo Authentication: chúng không tự thay thế login HTTP đã được cấu hình.

Đối với stateless Bearer token, OAuth2 hoặc token ở frontend, phải thiết kế riêng cách chứng thực ở handshake/channel. WebSocket API của browser không hỗ trợ tùy ý đặt HTTP Authorization header cho thao tác handshake giống fetch; nếu dùng STOMP CONNECT token, cần cơ chế xác thực interceptor do hệ thống định nghĩa và kiểm thử ranh giới tin cậy. Không đặt JWT nhạy cảm trong query string chỉ để truyền qua URL WebSocket.

## 6. Giữ bảo vệ CSRF ở STOMP CONNECT

Khác với fetch thông thường, WebSocket không được trình duyệt bảo vệ bởi đầy đủ các ràng buộc Same Origin Policy theo cùng cách. Một trang khác origin có thể thử mở WebSocket tới server, và trình duyệt có thể tự gửi cookie phù hợp với chính sách cookie. Vì vậy **kiểm soát Origin tại handshake và CSRF token trong STOMP CONNECT** là hai lớp cần phối hợp.

Khi dùng @EnableWebSocketSecurity theo cấu hình thông dụng, Spring Security yêu cầu **CSRF token hợp lệ trong native STOMP headers của frame CONNECT**. Nó không đồng nghĩa một header HTTP của request handshake đã thay thế được STOMP CSRF.

Với ứng dụng SPA, server có thể cung cấp endpoint cùng origin cho người dùng đã xác thực để lấy token hiện hành:

~~~java
package example.chat;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfEndpoint {
    @GetMapping("/csrf")
    CsrfToken csrf(CsrfToken token) {
        return token;
    }
}
~~~

Ví dụ frontend dùng STOMP client của thư viện @stomp/stompjs:

~~~javascript
async function connectStomp() {
    const response = await fetch("/csrf", {
        credentials: "same-origin",
        cache: "no-store"
    });
    if (!response.ok) {
        throw new Error("Không lấy được CSRF token");
    }
    const csrf = await response.json();

    const client = new StompJs.Client({
        brokerURL: "wss://" + window.location.host + "/ws",
        connectHeaders: {
            [csrf.headerName]: csrf.token
        },
        reconnectDelay: 5000
    });

    client.onConnect = () => {
        client.subscribe("/topic/rooms/general", onMessageReceived);
    };
    client.activate();
    return client;
}
~~~

Đây là đoạn tích hợp minh họa: StompJs và onMessageReceived là thành phần frontend cần cung cấp. Endpoint /csrf phải được bảo vệ, chỉ phản hồi cho origin và người dùng được phép, không bị cache công khai. Cần kết hợp với chính sách cấp token của CsrfTokenRepository, CSRF request handler, cơ chế xoay token khi login/logout và hành vi reconnect. Nếu frontend nằm trên origin khác, phải thiết kế cách trao token an toàn theo ranh giới cross-origin và CORS/credentials hợp lệ.

**Ba ranh giới CSRF cần phân biệt:**

1. HTTP POST/PUT/DELETE qua Servlet CSRF filter vẫn được bảo vệ theo HttpSecurity.
2. STOMP CONNECT được xác minh CSRF ở lớp messaging khi bật WebSocket Security.
3. Với **SockJS HTTP fallback**, các request POST do transport sử dụng có thể cần ngoại lệ CSRF HTTP **chỉ cho đường dẫn transport**, trong khi vẫn giữ yêu cầu CSRF ở STOMP CONNECT.

Một ngoại lệ Servlet có phạm vi hẹp, khi SockJS thực sự yêu cầu:

~~~java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/ws/**")
);
~~~

Ngoại lệ này **không phải mặc định cho mọi ứng dụng WebSocket**; chỉ áp dụng sau khi kiểm chứng đường dẫn SockJS cụ thể. Không dùng csrf.disable() cho toàn ứng dụng và không mở ngoại lệ tới controller nghiệp vụ khác. Nếu ứng dụng có thể dùng WebSocket chuẩn mà không cần fallback, nên cân nhắc không dùng SockJS để giảm phức tạp.

Theo hướng dẫn Spring Security, phiên bản dùng @EnableWebSocketSecurity có thể chưa cung cấp trực tiếp một công tắc Java config để tắt **STOMP CONNECT CSRF**. Khi gặp yêu cầu kết nối chéo origin đặc biệt, phải kiểm tra phiên bản cụ thể và phương án mở rộng chính thức; không tự giả định một method sameOriginDisabled() từ lớp legacy vẫn còn hoạt động. Tắt hoặc thay thế CSRF CONNECT phải kèm biện pháp xác minh origin/chứng thực mạnh và kiểm thử tấn công cross-site WebSocket hijacking.

## 7. Kiểm soát đúng SEND, SUBSCRIBE và user destinations

Việc di trú API mà vẫn giữ rule sơ sài như “anyMessage().authenticated()” có thể khiến người dùng có tài khoản gửi nội dung tới destination không dành cho client hoặc nhận dữ liệu ngoài phạm vi quyền.

Với ví dụ chat:

| Client STOMP frame | Destination | Quyền trong ví dụ | Vì sao |
|---|---|---|---|
| CONNECT | Không có destination | Đã xác thực + CSRF hợp lệ | Thiết lập kết nối với Principal được tin cậy |
| SEND | /app/chat.send | ROLE_USER | Chuyển message cho controller ứng dụng |
| SUBSCRIBE | /topic/rooms/general | ROLE_USER | Theo dõi kênh mà chính sách ví dụ cho phép |
| SUBSCRIBE | /user/queue/notifications | ROLE_USER | Theo dõi hàng đợi theo user destination |
| SEND | /topic/rooms/general | Bị từ chối | Client không được tự phát dưới danh nghĩa broker |
| SUBSCRIBE | /queue/private-user | Bị từ chối | Không cho client đi đường vòng qua broker prefix |
| SEND | /app/admin.delete | Bị từ chối | Chưa được cho phép, tránh lộ handler ngoài phạm vi |
| SUBSCRIBE | /topic/rooms/general khi chưa xác thực | Bị từ chối | Không có ROLE_USER |

**Hết sức lưu ý về authorization theo dữ liệu:** rule ROLE_USER cho /topic/rooms/* trong ví dụ chỉ minh họa role, **chưa kiểm tra thành viên của từng phòng**. Nếu phòng X là riêng tư, phải kiểm tra quyền của user với X bằng AuthorizationManager chuyên biệt hoặc nghiệp vụ tương ứng. Không dựa vào chuỗi destination do client cung cấp như bằng chứng người đó có quyền đọc phòng.

Ví dụ controller lấy danh tính người gửi từ Principal thay vì tin vào trường username của payload:

~~~java
package example.chat;

import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
class ChatMessageController {

    @MessageMapping("/chat.send")
    void send(ChatRequest body, Principal principal) {
        // Lấy danh tính đã xác thực từ principal.getName().
        // Kiểm tra quyền truy cập phòng theo dữ liệu trên server.
        // Không tin senderName hoặc role do client gửi trong body.
    }
}
~~~

ChatRequest là kiểu DTO do ứng dụng định nghĩa. Đây là khung minh họa vị trí đặt kiểm tra nghiệp vụ; chưa bao gồm logic lưu và phát thông điệp.

Spring Security áp dụng message authorization trên **clientInboundChannel**. Nó không tự phân quyền lại mọi message đi ra qua clientOutboundChannel. Hãy bảo vệ bước SUBSCRIBE, kiểm soát destination và lựa chọn người nhận khi server phát message. Thử đăng ký trực tiếp vào broker prefix và subscribe user queue của tài khoản khác để phát hiện cấu hình quá rộng.

## 8. Chuyển các biểu thức SpEL và custom permission

Những ứng dụng cũ có thể dùng access expression như hasRole('ADMIN'), hasPermission(...), hoặc một custom SecurityExpressionHandler trên registry legacy. Khi đổi sang AuthorizationManager, phải phân biệt:

- **Rule đơn giản:** dùng trực tiếp hasRole, hasAuthority, authenticated, permitAll, denyAll trên builder.
- **Rule dựa vào destination động hoặc dữ liệu nghiệp vụ:** viết AuthorizationManager<MessageAuthorizationContext<?>> kiểm tra tài nguyên và Principal theo dữ liệu server, có unit test riêng.
- **Biểu thức SpEL khó thay ngay:** dùng cách tích hợp expression được tài liệu của **phiên bản đang chạy** hỗ trợ làm bước chuyển tiếp, sau đó chuyển sang implementation rõ ràng có thể kiểm thử độc lập.

Ví dụ yêu cầu có vai trò ROLE_ADMIN cho subscription:

~~~java
messages
    .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
    .simpSubscribeDestMatchers("/topic/rooms/*").hasRole("USER")
    .simpTypeMatchers(
        SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE
    ).denyAll();
~~~

Với subscription /topic/rooms/{roomId}, nếu chính sách đòi quyền **thành viên phòng**, rule hasRole("USER") không đủ. AuthorizationManager tùy chỉnh có thể lấy principal và biến roomId, kiểm tra membership trên server rồi trả về quyết định cho phép/từ chối. Cần định nghĩa ứng xử khi người dùng bị khóa tài khoản, xóa khỏi phòng hoặc session còn mở sau khi quyền đổi.

Đặc biệt, các extension kế thừa AbstractSecurityExpressionHandler và override createEvaluationContextInternal hoặc createSecurityExpressionRoot không được gọi theo cách cũ khi dùng AuthorizationManager. Di trú loại này cần thiết kế lại logic đánh giá; không chỉ sửa import của lớp cấu hình.

## 9. Đừng nhầm Servlet STOMP với Reactive WebSocket

Module Spring Security HTTP Protection cũng đề cập Reactive. Nhưng mô hình dưới đây **không phải một cấu hình có thể gắn y nguyên vào WebFlux**:

| Nền tảng | Cách tiếp cận tiêu biểu | Điểm không thể sao chép nguyên |
|---|---|---|
| Spring MVC + Spring Messaging/STOMP | EnableWebSocketMessageBroker + EnableWebSocketSecurity + AuthorizationManager<Message<?>> | Đây là mô hình của bài |
| Spring MVC WebSocketHandler thô | HTTP handshake + handshake interceptor + quy tắc frame do app định nghĩa | Không tự có STOMP destination/message matcher |
| JSR-356 WebSocket endpoint | Bảo vệ handshake và thông điệp theo tích hợp riêng | Spring Security không cấp message authorization trực tiếp cho mọi endpoint JSR-356 |
| Spring WebFlux WebSocketHandler | SecurityWebFilterChain bảo vệ HTTP, logic Reactive WebSocket riêng | Không dùng HttpSecurity/AbstractSecurityWebSocketMessageBrokerConfigurer của Servlet |
| Broker ngoài qua relay | Bảo vệ inbound STOMP ở ứng dụng và quyền broker tương ứng | Broker có cơ chế tài khoản, destination và kết nối riêng |

Người học nên xác định rõ giao thức, framework và điểm thực thi authorization trước khi chọn cấu hình. Nếu hệ thống sử dụng RSocket, GraphQL subscriptions hoặc messaging khác, cần tham khảo cơ chế bảo mật riêng của từng công nghệ.

## 10. Những thay đổi đi kèm khi nâng cấp hệ thống

### 10.1. Spring Boot, Java và Jakarta

Đổi major version của Spring Security có thể đồng thời kéo theo thay đổi Spring Framework, Spring Boot, Servlet API (javax.servlet so với jakarta.servlet ở các thế hệ liên quan), Java baseline và test dependencies. Hãy quản lý phiên bản nhất quán theo BOM của dự án. Tránh sửa class deprecated WebSocket rồi trộn dependency 5.x, 6.x và 7.x thủ công khiến classpath mâu thuẫn.

### 10.2. HTTP security và CSRF vẫn phải tồn tại

Đổi cấu hình inbound messaging không thay thế HttpSecurity cho login, logout, session fixation, security headers, redirect HTTPS, HSTS, CSP, CORS, cookie và HTTP firewall. Với cookie session, HTTP handshake phải dùng cùng cơ chế xác thực và session store đáng tin cậy. STOMP CONNECT CSRF tiếp tục là lớp bổ sung chứ không thay cho bảo vệ HTTP endpoints.

### 10.3. Reverse proxy phải hỗ trợ upgrade

Proxy cần chuyển tiếp HTTP Upgrade/Connection phù hợp, đồng thời cấu hình host, scheme và cổng công khai. Người dùng nên kết nối bằng **wss://** trên trang HTTPS. Sai xử lý Forwarded, X-Forwarded-Proto hoặc timeout có thể làm kết nối lỗi hay lặp redirect, ngay cả khi rule authorization ở MockMvc đúng.

### 10.4. Session và kết nối tồn tại lâu

WebSocket giữ kết nối sau handshake; thay đổi trạng thái login, logout hoặc quyền truy cập trong lúc kết nối đang mở có thể không được phản ánh tức thì vào Principal đã được lưu. Ứng dụng cần kế hoạch đóng kết nối khi logout, xử lý refresh/reauth ở reconnect và kiểm tra quyền nghiệp vụ ở mỗi message quan trọng, không chỉ xác thực một lần lúc bắt đầu.

### 10.5. SockJS fallback và frame options

Một số SockJS transport cũ dựa trên iframe. Nếu thực sự dùng chúng, CSP frame-ancestors hoặc X-Frame-Options mặc định có thể chặn chính trang SockJS hợp lệ. Chỉ khi cần mới điều chỉnh SAMEORIGIN hoặc cấu hình CSP thích hợp, kèm test clickjacking. Không tắt toàn bộ frame protection vì một lỗi tải fallback chưa được chẩn đoán.

## 11. Chiến lược kiểm thử trước và sau khi di trú

Không thể kết luận “WebSocket đã an toàn” chỉ bằng việc project compile với @EnableWebSocketSecurity. Cần một **ma trận hành vi** chạy trên bản cũ và bản mới:

| ID | Thao tác | Kỳ vọng |
|---|---|---|
| W01 | Handshake /ws không có phiên hợp lệ | Bị chặn theo chính sách HTTP, không cấp kết nối STOMP có quyền |
| W02 | Handshake với session hợp lệ | Có Principal đúng; Origin hợp lệ được chấp nhận |
| W03 | Handshake với Origin không được phép | Bị từ chối theo cấu hình endpoint |
| W04 | STOMP CONNECT thiếu CSRF native header | Không kết nối thành công theo chính sách mặc định |
| W05 | STOMP CONNECT với CSRF sai hoặc đã hết hạn | Bị từ chối; không có subscription hoạt động |
| W06 | STOMP CONNECT với CSRF/token phiên hợp lệ | CONNECTED, sau đó quyền được kiểm tra theo frame |
| W07 | ROLE_USER SEND /app/chat.send | Qua authorization; controller được gọi nếu payload hợp lệ |
| W08 | ROLE_USER SUBSCRIBE /topic/rooms/general | Được chấp nhận theo policy ví dụ |
| W09 | Anonymous SUBSCRIBE /topic/rooms/general | Bị từ chối |
| W10 | Client SEND /topic/rooms/general | Bị từ chối (broker prefix không dành cho client gửi) |
| W11 | Client SUBSCRIBE /queue/private-user | Bị từ chối |
| W12 | Client SEND /app/admin.delete | Bị từ chối vì không nằm trong allowlist |
| W13 | User A cố SUBSCRIBE queue riêng của user B | Không nhận được message của B |
| W14 | User chưa thuộc room cố subscribe room riêng tư | Bị từ chối theo kiểm tra membership bổ sung |
| W15 | Logout rồi thử reconnect bằng phiên cũ | Không được xác thực; token và session được thu hồi theo thiết kế |
| W16 | SockJS HTTP fallback, nếu hỗ trợ | Kết nối hợp lệ thành công với STOMP CSRF; HTTP CSRF vẫn bật cho API thường |
| W17 | WSS sau reverse proxy | Upgrade, Origin, cookie và scheme công khai đúng |
| W18 | Những path không có policy khớp | Bị deny; không có destination mặc định được mở quá rộng |

### Tầng kiểm thử thích hợp

**Unit test của AuthorizationManager:** dựng message với SimpMessageType và destination tương ứng, cung cấp Authentication có hoặc không có ROLE_USER, rồi kiểm tra quyết định. Nên kiểm tra từng matcher và thứ tự; test này không cần mở socket.

**Integration test của Spring Messaging:** khởi động ứng dụng với broker test, kết nối bằng WebSocketStompClient và một session đăng nhập thật, gửi CONNECT có/không có CSRF token, thử SEND và SUBSCRIBE. Quan sát kết quả ở controller, subscription và event bảo mật. Không chỉ dựa vào handshake HTTP 101 vì một handshake thành công chưa chứng minh CONNECT STOMP và phân quyền inbound thành công.

**Browser end-to-end:** đăng nhập qua UI, lấy CSRF token như client thật, kết nối wss://, subscribe, reload/reconnect, logout và thử truy cập lại. Kiểm tra cả cookie/SameSite/Secure, Network và Origin.

**Tích hợp qua proxy/broker:** chạy qua TLS termination và đường đi public giống production. Với broker relay, cần kiểm tra thêm credential broker, quy tắc publish/subscribe, lỗi mạng và khả năng reconnect. Spring Security trên clientInboundChannel không kiểm chứng mọi quyền của broker ngoài.

### Kiểm thử cùng ma trận ở hai bản

Khi còn chạy được nhánh legacy, lưu status và log đầu vào/đầu ra của các ca W01–W18. Chạy lại trên nhánh migration, đối chiếu thay đổi. Nếu một ca “trước được phép, sau bị chặn”, xác định đây là quyết định siết policy hay lỗi migration; nếu “trước bị chặn, sau được phép”, coi là lỗi cần điều tra trước khi triển khai.

## 12. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xác minh và xử lý |
|---|---|---|
| Compile lỗi không tìm thấy AbstractSecurityWebSocketMessageBrokerConfigurer | Đã nâng Spring Security 7 nhưng còn API legacy | Chuyển sang @EnableWebSocketSecurity và AuthorizationManager |
| Có HTTP 101 nhưng STOMP CONNECT thất bại | Thiếu/sai CSRF native header, Principal không hợp lệ | Xem STOMP CONNECT headers và session; không chỉ xem handshake |
| Kết nối từ frontend ngoài origin bị từ chối | Origin policy khác CORS API thông thường | Kiểm tra Origin thực tế, allowed origins và thiết kế cross-site |
| Mock request qua HTTP API được nhưng WebSocket không authenticated | HTTP handshake không mang cookie/Principal hoặc client dựa vào STOMP login | Kiểm tra SecurityFilterChain và request handshake thật |
| SEND /app/chat.send bị từ chối | Matcher type/destination sai, role không có, prefix app khác | Xem SimpMessageType, destination và authority trong session |
| SUBSCRIBE /topic/rooms/general bị từ chối | Thiếu simpSubscribeDestMatchers hoặc pattern khác | Kiểm tra rule order, destination và type SUBSCRIBE |
| User có thể SEND thẳng /topic/** | Policy chỉ kiểm tra authenticated mà không phân loại frame | Chỉ allow MESSAGE tới /app/**; deny MESSAGE vào broker prefix |
| User A nhìn thấy message của B | Subscribe quá rộng, không kiểm tra user destination hoặc membership | Giới hạn subscription, lọc quyền theo user/tài nguyên tại server |
| SockJS fallback POST trả 403 | CSRF HTTP áp vào transport hoặc thiếu CSRF STOMP | Tách hai tầng; nếu cần, ngoại lệ HTTP chỉ ở SockJS path |
| WSS ở production thất bại sau proxy | Upgrade headers, TLS, forwarded scheme/host, timeout | Kiểm tra request qua proxy và log upgrade tại container |
| Kết nối cũ vẫn nhận tin sau logout | Session WebSocket tồn tại lâu và chưa bị đóng | Đóng phiên liên quan, tái xác thực và kiểm tra quyền liên tục |
| Rule custom SpEL không còn chạy như trước | Extension phụ thuộc expression handler legacy | Viết AuthorizationManager chuyên biệt hoặc adapter được hỗ trợ |
| Test xanh khi dùng mock Principal nhưng trình duyệt lỗi | Test bỏ qua login, cookie, CSRF thực tế | Thêm WebSocketStompClient/browser test với phiên thật |

Khi chẩn đoán, ghi rõ lỗi xảy ra ở **HTTP handshake, STOMP CONNECT, MESSAGE, SUBSCRIBE hay phản hồi broker**. Mỗi điểm có cơ chế bảo vệ và bằng chứng khác nhau; cùng một triệu chứng “WebSocket không kết nối” có thể bắt nguồn từ TLS, origin, authentication hoặc CSRF.

## 13. Quy trình chuyển đổi có thể kiểm soát

1. **Chốt phiên bản đích:** kiểm tra compatibility matrix Spring Boot/Spring Security/Spring Framework và module spring-messaging/spring-websocket tương ứng.
2. **Đóng băng hợp đồng:** ghi các URL handshake, prefixes, message types, role, expression tùy chỉnh, room membership và yêu cầu Origin/CSRF; lập ma trận kiểm thử baseline.
3. **Tách cấu hình transport:** dùng WebSocketMessageBrokerConfigurer quản lý endpoint và broker; đảm bảo không vô tình bỏ registration khi loại class security cũ.
4. **Thay security API:** bỏ AbstractSecurityWebSocketMessageBrokerConfigurer; thêm @EnableWebSocketSecurity và bean AuthorizationManager<Message<?>>; chuyển rule theo thứ tự, tối ưu theo loại frame khi có chủ đích.
5. **Chuyển custom expression:** chuyển rule đơn giản sang builder; xây AuthorizationManager có unit test cho quyền dữ liệu động.
6. **Giữ handshake authentication và STOMP CSRF:** xác minh session cookie/Principal, endpoint lấy CSRF token, native CONNECT header và các ngoại lệ SockJS HTTP thật sự cần.
7. **Chạy kiểm thử đủ tầng:** unit AuthorizationManager, integration messaging, browser có cookie/CSRF, môi trường WSS/proxy và trường hợp broker relay.
8. **Triển khai có quan sát:** theo dõi số handshake thất bại, CONNECT bị từ chối, 403 HTTP, authorization denied, tỷ lệ reconnect và log với danh tính đã được bảo vệ dữ liệu.
9. **Rollback có chuẩn bị:** giữ khả năng quay lại phiên bản ứng dụng và bộ dependency tương thích; không coi việc bật lại class đã bị loại bỏ trong runtime mới là một rollback hợp lệ.

### Kiểm tra cấu hình sau khi chuyển đổi

Một checklist review nên trả lời đủ các câu hỏi:

- Chỉ còn **một cơ chế đăng ký** authorization cho cùng inbound channel hay không?
- SecurityFilterChain có bao phủ chính xác handshake URL, kể cả các đường dẫn SockJS?
- STOMP CONNECT có yêu cầu CSRF và client có gửi native header theo chính sách token hiện hành?
- MESSAGE có thể đi đến những application destination nào? Broker prefix có bị từ chối SEND trực tiếp?
- SUBSCRIBE có tách user/topic và kiểm tra membership ở vùng dữ liệu riêng tư?
- Những message không khớp bất kỳ rule nào có bị deny theo chính sách đã chọn?
- Frontend có xử lý reconnect, logout, session expiry và lỗi 403/close event rõ ràng?
- Proxy có truyền đúng HTTPS/wss, Origin và Upgrade; các session cookie có attribute phù hợp?

## 14. Bài thực hành nâng cấp cấu hình chat cũ

**Bối cảnh:** một ứng dụng Spring MVC đang chạy Spring Security cũ, có cấu hình kế thừa AbstractSecurityWebSocketMessageBrokerConfigurer. Client chat dùng cookie session, endpoint /ws (có SockJS fallback), gửi tới /app/chat.send và đăng ký /topic/rooms/{roomId}, /user/queue/notifications. Nhóm phát triển chuẩn bị nâng lên Spring Security 7; phòng chat có thể là công khai trong nội bộ hoặc phòng riêng yêu cầu membership.

**Nhiệm vụ:**

1. Viết lại SecurityFilterChain cho handshake và tách cấu hình WebSocketMessageBrokerConfigurer.
2. Thay cấu hình legacy bằng @EnableWebSocketSecurity và bean AuthorizationManager<Message<?>>.
3. Chỉ cho ROLE_USER gửi MESSAGE đến /app/chat.send; không cho SEND trực tiếp vào /topic/** hoặc /queue/**.
4. Chỉ cho ROLE_USER SUBSCRIBE tới /user/queue/notifications; với phòng riêng, bổ sung AuthorizationManager kiểm tra membership theo roomId.
5. Giữ STOMP CONNECT CSRF. Với SockJS, đánh giá ngoại lệ HTTP CSRF có phạm vi /ws/** mà không làm mất CSRF của các API khác.
6. Tạo kịch bản khách chưa xác thực, role không đủ, token CSRF sai, subscription phòng khác, logout/reconnect và kết nối qua reverse proxy.
7. So sánh kết quả bảo mật trước và sau nâng cấp, giải thích mọi thay đổi có chủ đích.

**Tiêu chí hoàn thành:** cấu hình mới không phụ thuộc hai lớp legacy đã bị loại bỏ, không để client SEND trực tiếp tới broker destination, chỉ cho phép subscription được cấp quyền, CONNECT có CSRF đúng, handshake dùng Principal hợp lệ và ma trận kiểm thử qua STOMP/browser/proxy khớp chính sách. Không coi biên dịch thành công là bằng chứng thay thế cho kiểm thử hành vi.

## Tài liệu tham khảo để kiểm tra theo phiên bản

- [Spring Security Reference – WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): xác thực HTTP, inbound authorization, CSRF CONNECT, SockJS và migration.
- [Spring Security API – EnableWebSocketSecurity](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/config/annotation/web/socket/EnableWebSocketSecurity.html): annotation và bean AuthorizationManager.
- [Spring Security API – MessageMatcherDelegatingAuthorizationManager.Builder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html): các matcher phân biệt destination và message type.
- [Spring Framework Reference – Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): cấu hình endpoint và broker routing.

Khi sử dụng tài liệu, mở đúng nhánh reference trùng với phiên bản đang triển khai vì API và ví dụ migration có thể khác nhau giữa 5.8, 6.x và 7.x.
