# WebSocket, đăng xuất và thời gian đóng các kết nối liên quan

## Mục tiêu bài học

WebSocket tạo một kết nối hai chiều tồn tại lâu hơn một HTTP request. Sau khi handshake thành công, client có thể gửi và nhận nhiều message trên cùng kết nối mà không tạo lại HTTP request cho từng message. Nếu ứng dụng dùng Spring Security và Spring Session, kết nối WebSocket thường được thiết lập trong ngữ cảnh của một HttpSession đã xác thực.

Điều này tạo ra một yêu cầu vòng đời quan trọng: khi HttpSession còn hoạt động, WebSocket có thể tiếp tục phục vụ người dùng; khi session bị đăng xuất, bị xóa hoặc hết hạn, các WebSocket gắn với session đó cần được đóng để danh tính đã hết hiệu lực không tiếp tục sử dụng một kết nối đang mở.

Spring Session cung cấp tích hợp với Spring WebSocket và Spring Messaging để liên kết session với các kết nối WebSocket, cập nhật thời điểm truy cập khi nhận message từ client và đóng kết nối khi session bị hủy. Việc đóng kết nối phụ thuộc vào repository có phát sự kiện session phù hợp hay không. Với Redis indexed repository, sự kiện xóa và hết hạn được chuyển từ Redis keyspace notification thành Spring Session events. Repository JDBC tiêu chuẩn hiện không hỗ trợ phát các sự kiện này, nên cần thiết kế cơ chế đóng kết nối riêng nếu dùng JDBC.

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa HTTP handshake, HttpSession và WebSocketSession.
- Cấu hình Spring Session WebSocket integration cho STOMP endpoint.
- Hiểu vai trò của AbstractSessionWebSocketMessageBrokerConfigurer.
- Phân biệt SessionRepositoryMessageInterceptor, WebSocketConnectHandlerDecoratorFactory và WebSocketRegistryListener.
- Giải thích message inbound nào làm mới thời gian truy cập session.
- Kiểm thử đăng xuất khi một hoặc nhiều WebSocket đang mở.
- Kiểm thử session expiration và thời điểm đóng kết nối theo kiểu eventual.
- Cấu hình Redis indexed repository và keyspace notifications để phát sự kiện.
- Nhận biết giới hạn event của JdbcIndexedSessionRepository.
- Thiết kế cơ chế broadcast/close riêng khi repository không phát SessionDestroyedEvent.
- Kiểm thử trên nhiều instance, nhiều tab và nhiều WebSocket connection.
- Xử lý reconnect, cookie, CSRF, origin và quyền truy cập sau logout.

## 1. Vì sao WebSocket cần gắn với Spring Session?

Trong ứng dụng web thông thường, trình duyệt gửi HTTP request, server xác thực cookie session rồi xử lý request. Khi người dùng logout, Spring Security có thể invalidate HttpSession và xóa SecurityContext.

WebSocket hoạt động khác: sau handshake, kết nối được giữ mở. Một WebSocket có thể tiếp tục truyền message ngay cả khi không có HTTP request mới. Nếu chỉ invalidate HttpSession mà không đóng socket đang tồn tại, client có thể vẫn giữ một đường truyền đã được xác thực trước đó.

Ví dụ ứng dụng chat:

1. Alice đăng nhập qua HTTP.
2. Server tạo HttpSession và lưu SecurityContext.
3. Trình duyệt dùng cookie session để mở WebSocket.
4. Alice gửi và nhận tin nhắn trên WebSocket trong nhiều phút.
5. Alice bấm logout ở một tab khác.
6. Server invalidate session.
7. Các WebSocket gắn với session phải được đóng.
8. Nếu client muốn kết nối lại, nó phải xác thực lại bằng một session hợp lệ.

Nếu bước 7 không xảy ra, ứng dụng có thể giữ kết nối và subscription sau khi phiên đăng nhập đã kết thúc. Vì vậy, đóng socket là một phần của việc thu hồi trạng thái xác thực.

### Hai định danh khác nhau

Trong luồng này có hai loại ID:

| Định danh | Đại diện cho | Vòng đời |
|---|---|---|
| Spring Session ID | Phiên HTTP của người dùng | Theo session timeout, logout, invalidate và repository |
| WebSocketSession ID | Một kết nối WebSocket cụ thể | Từ handshake thành công đến khi socket đóng |

Một HttpSession có thể gắn với nhiều WebSocket connection, ví dụ người dùng mở hai tab hoặc nhiều cửa sổ. Khi session bị hủy, cần đóng tất cả connection được đăng ký dưới Spring Session ID đó.

Không dùng WebSocketSession ID thay cho Session ID và không tin Session ID do client tự gửi trong STOMP payload. Spring Session integration lấy định danh từ handshake đã được server xử lý.

## 2. Luồng handshake và liên kết session

WebSocket bắt đầu bằng HTTP handshake. Trình duyệt gửi cookie session cùng request nâng cấp giao thức. Spring Session đọc cookie, tải HttpSession từ repository và cung cấp session cho các thành phần Servlet/WebSocket.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant A as Application
    participant R as Redis Session Repository
    participant W as WebSocket Registry

    C->>A: HTTP handshake + SESSION cookie
    A->>R: Load HttpSession by ID
    R-->>A: Session + SecurityContext
    A->>A: Authenticate handshake
    A->>W: Register WebSocketSession under Session ID
    A-->>C: 101 Switching Protocols
    C->>A: STOMP CONNECT / MESSAGE
    A->>R: Refresh lastAccessedTime
    R-->>A: Session updated
~~~

Spring Session lưu mapping từ Spring Session ID đến WebSocketSession. Khi session kết thúc, listener tìm các WebSocketSession liên quan và đóng chúng.

### Spring Session WebSocket hỗ trợ loại nào?

Tích hợp này hoạt động với Spring WebSocket và Spring Messaging, đặc biệt là STOMP message broker. Nó không hỗ trợ trực tiếp JSR-356 thuần vì JSR-356 không cung cấp cơ chế tương ứng để Spring Session chặn các inbound message và cập nhật session.

Nếu ứng dụng dùng endpoint JSR-356 trực tiếp, cần tự xây dựng liên kết session, theo dõi connection và cơ chế đóng khi logout/expiration. Không giả định chỉ bật Spring Session là các socket JSR-356 được quản lý tự động.

## 3. Cấu hình Spring Session WebSocket integration

Trong ứng dụng STOMP thông thường, cấu hình có thể implement WebSocketMessageBrokerConfigurer. Để tích hợp Spring Session, kế thừa AbstractSessionWebSocketMessageBrokerConfigurer và đổi phương thức đăng ký endpoint từ registerStompEndpoints sang configureStompEndpoints.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.session.Session;
import org.springframework.session.web.socket.config.annotation.AbstractSessionWebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;

@Configuration
@EnableScheduling
@EnableWebSocketMessageBroker
public class WebSocketConfig
        extends AbstractSessionWebSocketMessageBrokerConfigurer<Session> {

    @Override
    protected void configureStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/messages")
                .setAllowedOriginPatterns("https://app.example.com")
                .withSockJS();
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/queue/", "/topic/");
        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Ví dụ dùng Spring WebSocket STOMP và SockJS. Nếu ứng dụng không dùng SockJS, có thể đăng ký endpoint WebSocket trực tiếp. Origin phải được giới hạn theo domain frontend thực tế; không mở wildcard trong production chỉ để tránh lỗi handshake.

### Những gì abstract configurer thiết lập

AbstractSessionWebSocketMessageBrokerConfigurer tự động kết nối một số thành phần:

1. **WebSocketConnectHandlerDecoratorFactory** được thêm vào WebSocket transport. Nó phát một SessionConnectEvent đặc biệt chứa WebSocketSession để listener có thể liên kết socket với Spring Session.
2. **SessionRepositoryMessageInterceptor** được thêm làm HandshakeInterceptor cho STOMP endpoint. Nó đưa Session ID vào thuộc tính WebSocket để các message sau có thể tìm lại session.
3. **SessionRepositoryMessageInterceptor** được thêm làm ChannelInterceptor vào inbound channel. Nó cập nhật lastAccessedTime khi nhận các message phù hợp và ngăn message tiếp tục nếu session đã hết hạn.
4. **WebSocketRegistryListener** được tạo thành Spring bean. Nó duy trì mapping Session ID đến các WebSocket connection và đóng các connection khi nhận SessionDestroyedEvent.

Do đó, với cấu hình Spring WebSocket STOMP, không cần tự đăng ký từng thành phần này nếu đã dùng abstract configurer. Nếu tự implement WebSocketMessageBrokerConfigurer, phải tự bảo đảm các interceptor, decorator và registry listener cần thiết được đăng ký đúng.

## 4. SessionRepositoryMessageInterceptor cập nhật thời gian truy cập ra sao?

Một session có max inactive interval. Nếu người dùng không hoạt động đủ lâu, session hết hạn. Tuy nhiên, trong ứng dụng chat, người dùng có thể đang hoạt động qua WebSocket mà không gửi HTTP request.

SessionRepositoryMessageInterceptor giải quyết việc này bằng cách giữ Session ID trong WebSocket properties và cập nhật lastAccessedTime khi có inbound message từ client.

Các message STOMP mặc định được interceptor theo dõi gồm:

- CONNECT
- MESSAGE
- SUBSCRIBE
- UNSUBSCRIBE

Khi một inbound message phù hợp đến, interceptor tải session, xác minh session chưa hết hạn và cập nhật thời gian truy cập. Nếu session đã hết hạn, message không được chuyển tiếp như message hợp lệ.

### Inbound và outbound không giống nhau

Chỉ message do client gửi mới biểu thị hoạt động của người dùng và làm mới session theo cơ chế mặc định. Message server gửi đến client không làm mới session.

Ví dụ:

| Hoạt động | Có làm mới session theo mặc định? |
|---|---|
| Client gửi STOMP MESSAGE | Có |
| Client gửi SUBSCRIBE | Có |
| Client gửi UNSUBSCRIBE | Có |
| Client gửi CONNECT | Có |
| Server đẩy thông báo đến client | Không |
| Client chỉ nhận thông báo nhưng không gửi gì | Không |
| HTTP request hợp lệ có sử dụng session | Có thể cập nhật theo HttpSession flow |

Điều này quan trọng với ứng dụng chỉ đẩy dữ liệu một chiều. Nếu server gửi giá chứng khoán hoặc thông báo liên tục nhưng client không gửi inbound message, session vẫn có thể hết hạn theo idle timeout. Khi đó, socket sẽ bị đóng khi Spring Session xử lý sự kiện session hết hạn.

Nếu cần heartbeat hoặc hoạt động ứng dụng để giữ session, hãy xác định message type nào thực sự đại diện cho user activity và cấu hình matching message types có chủ đích. Không coi heartbeat giao thức hoặc server push là hoạt động người dùng nếu interceptor không theo dõi chúng.

### Cấu hình matching message types

SessionRepositoryMessageInterceptor cho phép thay đổi tập SimpMessageType được theo dõi. Nếu cần tùy chỉnh, có thể cung cấp bean hoặc custom config phù hợp với phiên bản Spring Session đang dùng:

~~~java
@Bean
SessionRepositoryMessageInterceptor<Session> sessionRepositoryMessageInterceptor(
        SessionRepository<Session> sessionRepository
) {
    SessionRepositoryMessageInterceptor<Session> interceptor =
            new SessionRepositoryMessageInterceptor<>(sessionRepository);

    interceptor.setMatchingMessageTypes(Set.of(
            SimpMessageType.CONNECT,
            SimpMessageType.MESSAGE,
            SimpMessageType.SUBSCRIBE,
            SimpMessageType.UNSUBSCRIBE
    ));

    return interceptor;
}
~~~

Đây là ví dụ cấu hình interceptor riêng. Khi tự khai báo bean, cần kiểm tra abstract configurer có dùng lại bean đó hay không để tránh đăng ký trùng hoặc hai interceptor với policy khác nhau. Thông thường, giữ default matching types là đủ.

## 5. Đăng xuất phải invalidate HttpSession

Với Servlet và Spring Security, logout mặc định thực hiện nhiều thao tác:

- Invalidate HttpSession thông qua SecurityContextLogoutHandler.
- Xóa SecurityContext khỏi SecurityContextHolderStrategy.
- Xóa SecurityContextRepository.
- Xóa Remember-Me authentication nếu có.
- Xóa CSRF token đã lưu.
- Phát LogoutSuccessEvent.

Khi CSRF protection được bật, client thường gửi POST /logout cùng CSRF token. GET /logout có thể hiển thị trang xác nhận và token; không dùng GET như một thao tác thay đổi trạng thái nếu policy ứng dụng yêu cầu POST.

Ví dụ cấu hình:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                    .invalidateHttpSession(true)
                    .clearAuthentication(true)
                    .deleteCookies("SESSION")
            )
            .build();
}
~~~

Ví dụ dùng cookie name SESSION của Spring Session. Nếu ứng dụng tùy chỉnh tên cookie, phải dùng tên thực tế. Cấu hình deleteCookies chỉ xóa cookie phía client; việc invalidate session phía server mới là điều kiện để thu hồi trạng thái xác thực.

### Logout không tự đóng socket nếu thiếu event bridge

Invalidate HttpSession là bước server-side. WebSocket connection là kết nối riêng đã được thiết lập trước đó. Spring Session WebSocket integration dùng SessionDestroyedEvent và WebSocketRegistryListener để nối hai vòng đời này.

Nếu repository không phát event, hoặc event listener không hoạt động, cookie bị xóa vẫn không bảo đảm socket đang mở được đóng. Vì vậy, cần kiểm tra cả:

1. Logout đã invalidate session.
2. Repository đã phát sự kiện session destroyed.
3. Node giữ WebSocket đã nhận sự kiện.
4. WebSocketRegistryListener đã đóng connection.
5. Client nhận close và không thể tiếp tục dùng socket cũ.
6. Request hoặc handshake mới cần xác thực lại.

## 6. SessionDestroyedEvent, SessionDeletedEvent và SessionExpiredEvent

Spring Session có các event vòng đời:

| Event | Ý nghĩa |
|---|---|
| SessionCreatedEvent | Session được tạo |
| SessionDeletedEvent | Session bị hủy do thao tác xóa |
| SessionExpiredEvent | Session hết hạn |
| SessionDestroyedEvent | Event cơ sở cho các trường hợp session kết thúc |

SessionDeletedEvent và SessionExpiredEvent là các dạng SessionDestroyedEvent. WebSocketRegistryListener nghe sự kiện hủy session để đóng các WebSocket đang gắn với session đó.

Trong luồng logout, session thường bị delete/invalidate nên cần event xóa. Trong luồng idle timeout, session hết hạn nên cần event expiration.

Không nhầm LogoutSuccessEvent của Spring Security với SessionDestroyedEvent của Spring Session. LogoutSuccessEvent cho biết logout flow đã thành công ở Spring Security. SessionDestroyedEvent là tín hiệu vòng đời session mà WebSocketRegistryListener sử dụng. Một ứng dụng có thể quan sát cả hai, nhưng chúng có mục đích khác nhau.

### Event listener tùy chỉnh

Có thể dùng ApplicationListener hoặc @EventListener để ghi nhận vòng đời:

~~~java
@Component
public class SessionLifecycleAudit {

    @EventListener
    public void onSessionDeleted(SessionDeletedEvent event) {
        // Record that the session was explicitly deleted.
    }

    @EventListener
    public void onSessionExpired(SessionExpiredEvent event) {
        // Record that the session expired.
    }
}
~~~

Không log Session ID đầy đủ hoặc thuộc tính session nhạy cảm. Nếu cần correlation, dùng mã đã che hoặc hash theo policy. Listener nên thực hiện công việc ngắn, không chặn event thread bằng thao tác mạng dài.

## 7. Redis indexed repository và keyspace notifications

Để Spring Session Redis phát các event xóa và hết hạn, cần dùng indexed repository và Redis keyspace notifications phù hợp.

Với Servlet HttpSession:

~~~java
@Configuration
@EnableRedisIndexedHttpSession
public class SessionConfig {
}
~~~

Hoặc với Spring Boot, có thể chọn repository type indexed theo property mà phiên bản Boot hỗ trợ.

Redis indexed repository dùng Redis keyspace events để nhận biết key expiration và delete. Các nhóm event cần thiết gồm:

- Generic command events, bao gồm delete.
- Expired events, bao gồm key hết TTL.

Trong ví dụ Redis, cấu hình tương ứng thường được biểu diễn bằng:

~~~text
notify-keyspace-events Egx
~~~

Trong đó E bật keyevent notification, g bao gồm generic command events và x bao gồm expired events.

Spring Session có thể tự cấu hình Redis keyspace notifications nếu Redis cho phép CONFIG. Trong môi trường Redis được quản lý hoặc bảo mật chặt, tài khoản ứng dụng có thể không có quyền CONFIG SET. Khi đó, cung cấp ConfigureRedisAction.NO_OP để Spring Session không cố thay đổi cấu hình server:

~~~java
@Bean
ConfigureRedisAction configureRedisAction() {
    return ConfigureRedisAction.NO_OP;
}
~~~

Khi dùng NO_OP, quản trị viên Redis phải cấu hình keyspace notifications ngoài ứng dụng. Không cấp quyền CONFIG SET cho runtime chỉ để Spring Session tự thay đổi cấu hình production.

### Vì sao phải dùng indexed repository?

Repository Redis cơ bản chủ yếu tải session theo Session ID. Indexed repository bổ sung index và hỗ trợ các event session cần cho quản lý vòng đời. Spring Session WebSocket integration dựa vào sự kiện session destroyed để đóng connection.

Không giả định mọi repository Redis đều phát đầy đủ SessionDeletedEvent và SessionExpiredEvent. Hãy kiểm tra đúng repository type, version và cấu hình listener trong ứng dụng.

### Redis Cluster và event propagation

Trong Redis Cluster, cần kiểm tra cách repository đăng ký keyspace listener và node nào phát event. Tài liệu Spring Session cảnh báo indexed repository có thể chỉ subscribe event từ một node ngẫu nhiên trong cluster, làm một số index không được cleanup nếu event phát ở node khác.

Nếu triển khai Redis Cluster, kiểm thử việc nhận event trên topology thực tế. Không suy ra rằng một test chạy với Redis standalone chứng minh event propagation của Redis Cluster.

## 8. Thời gian đóng socket khi session hết hạn

TTL session và thời điểm socket đóng không nhất thiết trùng nhau chính xác.

Redis expiration event không được bảo đảm phát đúng ngay tại millisecond TTL chạm 0. Spring Session dùng expiration tracking và background cleanup để truy cập các session đến hạn, giúp Redis phát expiration event trong khoảng thời gian hợp lý hơn.

Vì vậy:

- Session có thể đã không còn hợp lệ trước khi listener nhận event.
- WebSocket có thể đóng trễ hơn thời điểm maxInactiveInterval.
- Test không nên đòi socket đóng chính xác tại giây TTL kết thúc.
- Hãy dùng eventual assertion với timeout đủ lớn theo cleanup schedule và môi trường test.
- Khi nhận message sau khi session đã hết hạn, SessionRepositoryMessageInterceptor cũng kiểm tra trạng thái và có thể chặn message.

Trong sample Spring Session, session timeout một phút có thể cần chờ đến khoảng hai phút để quan sát socket đóng do Redis expiration event và cleanup task. Đây là ví dụ về độ trễ cleanup, không phải SLA cố định cho mọi cấu hình.

### Logout và expiration có độ trễ khác nhau

Logout chủ động xóa session và có thể tạo delete event nhanh hơn so với chờ TTL. Tuy nhiên, event vẫn đi qua repository, Redis listener và Spring application event pipeline. Vì vậy, socket close vẫn là thao tác bất đồng bộ so với HTTP logout response.

Ứng dụng nên đảm bảo sau khi session invalidated, mọi request mới bị từ chối ngay cả khi WebSocket close event chưa được xử lý. Event đóng socket là bước dọn dẹp kết nối; authorization ở server vẫn phải kiểm tra session và trạng thái truy cập.

## 9. WebSocketRegistryListener quản lý nhiều kết nối

WebSocketRegistryListener duy trì mapping giữa Spring Session ID và WebSocketSession. Khi nhận SessionDestroyedEvent, nó tìm các WebSocket connection thuộc session và đóng chúng.

Một session có thể có:

- Một socket cho tab chat.
- Một socket cho notification.
- Một socket cho dashboard.
- Nhiều socket do nhiều tab hoặc nhiều cửa sổ.
- Các SockJS session hoặc transport connection theo cách triển khai.

Khi session bị hủy, tất cả socket được đăng ký cho session đó phải được kết thúc. Đóng một socket không được làm ảnh hưởng socket của người dùng khác hoặc session khác.

### WebSocketRegistryListener là registry kết nối

Nó không thay thế Spring Session repository. Repository lưu trạng thái session; registry listener theo dõi connection đang mở trong application instance.

Không lưu object WebSocketSession vào Redis như một object Java để chia sẻ trực tiếp giữa các node. WebSocketSession gắn với transport và runtime local của node. Khi cần đóng socket ở node khác, node đó phải nhận event/broadcast và đóng connection local của nó.

### Client phải xử lý close

Sau khi server đóng socket:

- Client nhận close event.
- UI chuyển trạng thái sang disconnected.
- Các subscription được xem là đã kết thúc.
- Client không gửi tiếp message trên socket cũ.
- Không tự động reconnect bằng cookie session đã bị invalidate.
- Nếu reconnect được phép, client cần xác thực lại và thiết lập connection mới.

Không dựa vào việc browser tự đóng WebSocket khi cookie hết hạn. Cookie chỉ được dùng lúc handshake; kết nối đã mở không tự thực hiện handshake lại khi cookie thay đổi.

## 10. Nhiều instance: event phải đến node đang giữ socket

Trong deployment nhiều instance, một người dùng có thể mở WebSocket tại node A nhưng gửi HTTP logout đến node B.

Mô hình:

~~~text
Browser
  |
  +-- WebSocket handshake --> Node A
  |                              |
  |                         Local WebSocketRegistry
  |
  +-- POST /logout ----------> Node B
                                 |
                           Shared Redis Session
                                 |
                       Keyspace delete notification
                           /             \
                          v               v
                   Listener A        Listener B
                       |                 |
                 Registry A         Registry B
                       |                 |
                 Close socket       Close local sockets
~~~

Mỗi node có WebSocketRegistryListener cục bộ và đăng ký listener cho session events từ kho dùng chung. Khi Redis phát delete event và mọi node nhận được, mỗi node đóng các socket mà chính nó đang giữ cho Session ID đó.

Điều kiện để hoạt động:

- Các node dùng cùng Redis endpoint và namespace.
- Mọi node dùng indexed repository và event listener phù hợp.
- Redis keyspace notifications được bật đúng.
- Các node có cùng cấu hình Spring Session/WebSocket tương thích.
- Không có node nào chỉ dùng local repository khác.
- Network và Redis Pub/Sub cho phép các listener nhận event.
- Redis Cluster topology được kiểm thử riêng.

Nếu chỉ node B nhận được event, node A có thể vẫn giữ socket mở. Vì vậy, test multi-node phải chứng minh event đến node sở hữu socket, không chỉ kiểm tra Redis key đã bị xóa.

## 11. Giới hạn quan trọng của JDBC repository

Không phải mọi Spring Session repository đều phát session events. API hiện tại của JdbcIndexedSessionRepository ghi rõ implementation này không hỗ trợ publishing session events.

Điều đó có nghĩa:

- JDBC có thể lưu và invalidate HttpSession.
- Spring Security có thể xóa session khi logout.
- Bảng session có thể không còn hàng hợp lệ.
- Nhưng WebSocketRegistryListener không thể tự đóng socket dựa vào SessionDestroyedEvent nếu repository không phát event đó.

Không kết luận rằng dùng JDBC thì WebSocket logout luôn đóng socket tự động. Hãy kiểm tra event support của repository/version thực tế.

### Cách thiết kế khi dùng JDBC

Nếu cần đóng WebSocket ngay sau logout hoặc expiration, có thể thiết kế cơ chế riêng:

1. Logout handler hoặc service thực hiện invalidate session.
2. Sau khi thao tác session được xác nhận, phát một application event hoặc command chứa session identifier đã được bảo vệ.
3. Gửi command qua broker hoặc kênh broadcast dùng chung đến mọi instance.
4. Mỗi instance tìm các WebSocket connection local gắn với session identifier.
5. Mỗi instance đóng các connection local.
6. Ghi nhận kết quả và xử lý retry nếu node tạm thời không nhận được command.

Với expiration, cần một job hoặc cơ chế phát event khi session bị cleanup. Không dùng trigger database như một event broadcast hoàn chỉnh nếu ứng dụng không có thành phần nhận và phân phối sự kiện đến các node.

Một cách khác là dùng một session repository có hỗ trợ event phù hợp với yêu cầu, sau khi đánh giá dữ liệu, vận hành và khả năng migration. Không thay repository chỉ để lấy event nếu các yêu cầu transaction, persistence hoặc kiến trúc không phù hợp.

### Không dùng event cục bộ cho nhiều node

Một Spring ApplicationEvent chỉ được phát trong application context hiện tại. Nếu logout ở node B và chỉ publish local event, node A không tự nhận được.

Cần một kênh phân phối dùng chung như Redis Pub/Sub, message broker hoặc event stream. Mỗi node phải subscribe và đóng socket của chính nó.

## 12. Đóng tất cả phiên của người dùng

Một người dùng có thể đăng nhập trên nhiều thiết bị hoặc trình duyệt. Logout hiện tại thường kết thúc session đang được request sử dụng. Nếu yêu cầu bảo mật là đăng xuất khỏi mọi thiết bị, cần tìm và invalidate mọi session của principal.

Với indexed repository, có thể tìm session theo principal:

~~~java
Collection<? extends Session> sessions =
        sessionRepository.findByPrincipalName(principal.getName()).values();

for (Session session : sessions) {
    sessionRepository.deleteById(session.getId());
}
~~~

Đây là ví dụ ý tưởng cho indexed SessionRepository. Kiểm tra kiểu repository và API đúng với version đang dùng. Mỗi lần xóa cần tạo event phù hợp để WebSocketRegistryListener đóng các connection gắn với session tương ứng.

Không cung cấp endpoint cho người dùng nhập tùy ý Session ID rồi xóa. Endpoint quản trị phải kiểm tra quyền, ownership, tenant và audit.

### Thu hồi theo thiết bị

Nếu giao diện cho phép người dùng xem danh sách thiết bị:

- Hiển thị metadata an toàn như thời gian đăng nhập, thiết bị và lần hoạt động gần nhất.
- Không hiển thị Session ID đầy đủ.
- Khi người dùng thu hồi một thiết bị, kiểm tra session thuộc đúng principal hiện tại.
- Xóa session qua repository API.
- Đợi hoặc theo dõi event đóng WebSocket.
- Không cho session cũ tiếp tục tạo connection mới.

## 13. Bảo mật handshake và STOMP message

WebSocket handshake thường dùng cookie session. Vì vậy, các chính sách bảo mật HTTP và WebSocket phải nhất quán.

Các điểm cần kiểm tra:

- Chỉ cho phép origin frontend hợp lệ.
- Handshake phải được xác thực nếu endpoint yêu cầu đăng nhập.
- STOMP CONNECT và destination cần được authorization theo principal.
- Không tin username hoặc role do client gửi trong header/message.
- Xác minh quyền subscription, gửi message và truy cập queue/topic.
- Áp dụng CSRF protection cho luồng STOMP phù hợp cấu hình Spring Security.
- Không đưa Session ID vào STOMP payload.
- Không log cookie hoặc credential.
- Khi session bị invalidate, message mới không được tiếp tục được chấp nhận.

Một WebSocket đã mở không được coi là bằng chứng authorization vô thời hạn. Nếu policy yêu cầu kiểm tra quyền ở mỗi message, hãy bảo đảm inbound channel security và session expiration được thực thi. Đóng socket khi session destroyed là lớp thu hồi connection; authorization cho từng destination vẫn cần thiết.

## 14. Kiểm thử tích hợp: session còn hoạt động khi có inbound message

Một test nên dùng Spring Boot context đầy đủ, Spring Session Redis indexed repository và WebSocket STOMP endpoint.

Kịch bản:

1. Login qua HTTP bằng user hợp lệ.
2. Lấy cookie SESSION từ response.
3. Kết nối WebSocket/STOMP với cookie đó.
4. Gửi CONNECT, SUBSCRIBE hoặc MESSAGE từ client.
5. Xác minh session lastAccessedTime được cập nhật.
6. Chờ quá một khoảng idle ngắn nhưng tiếp tục gửi inbound message theo chu kỳ.
7. Xác minh session vẫn có thể được khôi phục qua HTTP request.
8. Dừng inbound message.
9. Chờ session hết hạn theo test timeout.
10. Xác minh WebSocket được đóng sau khi repository phát event.

Không chỉ dùng server push để giữ session trong test. Inbound message mới là hoạt động được interceptor theo dõi mặc định.

### Đo lastAccessedTime

Có thể đọc session qua repository trong test và so sánh lastAccessedTime trước/sau inbound message. Không dựa vào thời gian của một request quá ngắn nếu precision hoặc flush timing khiến hai timestamp giống nhau; có thể chờ một khoảng đủ để phân biệt và dùng clock/test configuration phù hợp.

Test không nên đọc key nội bộ Redis làm assertion duy nhất. Ưu tiên SessionRepository API; nếu cần kiểm tra key/TTL thì gắn với phiên bản repository cụ thể.

## 15. Kiểm thử logout khi WebSocket đang mở

Đây là test quan trọng nhất cho chủ đề.

Kịch bản cơ bản:

1. Login Alice qua HTTP.
2. Giữ cookie session.
3. Mở hai WebSocket connection bằng cùng cookie, mô phỏng hai tab.
4. Xác minh cả hai socket nhận message.
5. Gửi POST /logout bằng cookie và CSRF token hợp lệ.
6. Xác minh HTTP session bị invalidate.
7. Xác minh repository phát SessionDeletedEvent/SessionDestroyedEvent nếu repository hỗ trợ.
8. Chờ cả hai WebSocket nhận close.
9. Gửi request HTTP mới bằng cookie cũ và xác minh bị từ chối hoặc yêu cầu login.
10. Thử handshake WebSocket mới bằng cookie cũ và xác minh không được xác thực.

Dùng eventual assertion cho việc socket đóng vì event listener và transport cleanup là bất đồng bộ. Không yêu cầu close frame xuất hiện trước HTTP logout response trừ khi ứng dụng đã thiết kế thứ tự đó.

### Kiểm tra nhiều node

Mở WebSocket tại node A, sau đó gửi logout đến node B. Test phải xác minh socket trên A cũng được đóng. Đây là cách phát hiện event chỉ được xử lý local hoặc Redis listener không nhận được keyspace event.

Có thể mở thêm một socket trên B để xác minh cả hai registry local đều dọn connection của mình.

## 16. Kiểm thử expiration và thời gian đóng kết nối

Dùng timeout ngắn trong profile test, ví dụ một phút hoặc thấp hơn nếu repository hỗ trợ. Sau khi không có inbound activity:

1. Đợi maxInactiveInterval.
2. Xác minh session không còn hợp lệ khi truy cập repository/API.
3. Chờ event expiration và cleanup task.
4. Xác minh WebSocket đóng trong timeout quan sát được.
5. Xác minh request mới bằng cookie cũ không khôi phục Authentication.

Redis không bảo đảm expiration notification được gửi chính xác ngay tại TTL. Spring Session có expiration tracking/background cleanup để làm event phát ra ổn định hơn, nhưng vẫn phải kiểm thử theo thời gian eventual.

Không dùng sleep cố định rồi giả định mọi môi trường sẽ đóng socket đúng thời điểm. Dùng Awaitility hoặc polling có timeout:

~~~java
await()
    .atMost(Duration.ofMinutes(2))
    .untilAsserted(() -> assertThat(webSocketSession.isOpen()).isFalse());
~~~

Thời gian hai phút chỉ là ví dụ minh họa từ một cấu hình cleanup; chọn timeout theo repository, cleanup schedule, Redis topology và môi trường CI.

## 17. Kiểm thử với JDBC hoặc repository không phát event

Nếu dùng JdbcIndexedSessionRepository, test cần xác minh hai hành vi tách biệt:

- Logout làm session mất hiệu lực trong repository.
- WebSocket có được đóng hay không theo cơ chế bổ sung của ứng dụng.

Nếu chưa có custom broadcast/close mechanism, test có thể phát hiện session bị xóa nhưng WebSocket vẫn mở. Đây không nhất thiết là lỗi của WebSocketRegistryListener; repository không phát event cần thiết để listener hoạt động.

Sau khi bổ sung cơ chế riêng, test:

1. Mở socket trên node A.
2. Logout ở node B.
3. Xác minh logout transaction hoàn tất.
4. Xác minh command close được broadcast.
5. Xác minh A nhận command.
6. Xác minh A đóng socket.
7. Xác minh node B cũng đóng socket local nếu có.
8. Xác minh duplicate close command không làm lỗi xử lý.

Thiết kế command phải idempotent: đóng một socket đã đóng hoặc session đã bị xóa không được gây side effect nguy hiểm.

## 18. Race condition giữa logout, message và reconnect

Logout có thể xảy ra cùng lúc client đang gửi message. Một message có thể đã được chấp nhận trước khi session bị invalidate; message khác đến sau khi session đã hết hạn phải bị chặn theo interceptor/security policy.

Hãy xác định thứ tự và invariant:

- Sau khi logout hoàn tất, không có request mới nào được xác thực bằng session cũ.
- Sau khi session bị destroy, WebSocket connection phải được đóng khi event/close command được xử lý.
- Message đã được xử lý trước thời điểm logout có thể đã tạo side effect; cần transaction/idempotency nếu nghiệp vụ yêu cầu.
- Message đến sau khi session hết hạn không được tiếp tục như user đã xác thực.
- Client không reconnect tự động bằng cookie đã bị thu hồi.
- Reconnect sau login mới phải tạo connection mới với principal mới.

Nếu client tự động reconnect, server vẫn phải xác thực handshake và STOMP authorization. Không dựa vào JavaScript để bảo đảm bảo mật.

## 19. Quan sát và xử lý lỗi vận hành

Các chỉ số hữu ích:

- Số WebSocket connection đang mở theo node.
- Số connection theo session hoặc principal đã được che.
- Số SessionConnectEvent và SessionDisconnectEvent.
- Số SessionDeletedEvent và SessionExpiredEvent.
- Thời gian từ session destroy đến WebSocket close.
- Số socket đóng do logout, expiration hoặc transport error.
- Số inbound message bị chặn vì session expired.
- Redis keyspace notification listener health.
- Số lần reconnect sau logout.
- Số session không có registry mapping hoặc socket mapping còn sót.

Log cần có node ID, correlation ID, event type, thời điểm và lý do close. Không log cookie, Session ID đầy đủ, STOMP Authorization header hoặc payload nhạy cảm.

### Một số triệu chứng và hướng điều tra

| Triệu chứng | Hướng kiểm tra |
|---|---|
| Logout thành công nhưng socket vẫn mở | Repository có phát SessionDestroyedEvent không; listener có được đăng ký không |
| Session Redis bị xóa nhưng không có close event | Indexed repository, keyspace notifications, Redis listener và CONFIG policy |
| Socket đóng dù người dùng đang chat | Inbound message interceptor có được cài không; client có gửi message phù hợp không |
| Server push liên tục nhưng session hết hạn | Outbound message không làm mới lastAccessedTime; cần inbound activity nếu policy cho phép |
| Node A không đóng socket khi logout ở B | Redis event có đến A không; registry mapping có chứa session ID không |
| Chỉ một trong nhiều tab bị đóng | Kiểm tra registry mapping và từng WebSocketSession |
| JDBC logout không đóng socket | JdbcIndexedSessionRepository không phát session events; cần broadcast/close riêng |
| Socket đóng quá trễ sau TTL | Redis expiration event và cleanup schedule có độ trễ; kiểm tra timeout eventual |
| Socket JSR-356 không tự đóng | Tích hợp Spring Session WebSocket không hỗ trợ JSR-356 trực tiếp |

## 20. Checklist trước khi phát hành

### Cấu hình tích hợp

- HttpSession được Spring Session quản lý trước khi bật WebSocket support.
- Ứng dụng dùng Spring WebSocket/STOMP nếu muốn dùng tích hợp tự động.
- WebSocketConfig kế thừa AbstractSessionWebSocketMessageBrokerConfigurer.
- SessionRepositoryMessageInterceptor được đăng ký ở handshake và inbound channel.
- WebSocketConnectHandlerDecoratorFactory phát SessionConnectEvent.
- WebSocketRegistryListener tồn tại trong application context.
- Origin được giới hạn theo frontend.
- Security authorization áp dụng cho handshake và STOMP destinations.

### Logout và expiration

- POST logout dùng CSRF token khi CSRF bật.
- Logout invalidate HttpSession và clear SecurityContext.
- Cookie session được xóa theo tên và path cấu hình.
- Repository hỗ trợ SessionDestroyedEvent.
- Redis indexed repository và keyspace notification được bật nếu dùng Redis event bridge.
- Redis managed service dùng ConfigureRedisAction.NO_OP khi runtime không có CONFIG, và admin cấu hình notifications ngoài ứng dụng.
- Test socket đóng khi logout.
- Test socket đóng sau expiration với eventual timeout.
- Test cookie cũ không thể mở connection đã xác thực.

### Nhiều node và repository

- Mọi node dùng cùng repository và namespace.
- Event đến tất cả node giữ WebSocket.
- Test logout ở B đóng socket đang mở ở A.
- Redis Cluster được kiểm thử event propagation riêng.
- Nếu dùng JDBC, có custom broadcast/close mechanism hoặc chấp nhận giới hạn đã được thiết kế rõ.
- Không dựa vào local Spring ApplicationEvent để broadcast giữa JVM.
- Client không reconnect bằng session cũ.
- Metrics và logs không làm lộ Session ID hoặc credential.

## 21. Tự kiểm tra

1. Vì sao WebSocket có thể còn mở sau khi HttpSession đã invalidate?
2. Spring Session WebSocket integration hỗ trợ Spring WebSocket nào và không hỗ trợ trực tiếp cơ chế nào?
3. AbstractSessionWebSocketMessageBrokerConfigurer tự đăng ký những thành phần nào?
4. SessionRepositoryMessageInterceptor làm nhiệm vụ gì ở handshake?
5. Những inbound STOMP message type nào được theo dõi mặc định?
6. Vì sao server-to-client message không làm mới session theo mặc định?
7. Spring Security logout mặc định thực hiện những thao tác nào?
8. SessionDeletedEvent khác LogoutSuccessEvent như thế nào?
9. WebSocketRegistryListener dùng mapping nào để đóng connection?
10. Vì sao cần Redis indexed repository và keyspace notification?
11. notify-keyspace-events Egx có ý nghĩa gì?
12. Tại sao session expiration và socket close không xảy ra đúng cùng một millisecond?
13. Vì sao JdbcIndexedSessionRepository cần cơ chế đóng socket riêng?
14. Vì sao application event local không đủ cho nhiều node?
15. Làm thế nào kiểm thử logout ở node B đóng socket tại node A?
16. Vì sao test cần giữ nhiều WebSocket connection cho cùng một session?
17. Client nên làm gì khi nhận close sau logout?
18. Những metric nào giúp phát hiện WebSocket connection bị rò rỉ?

### Gợi ý trả lời

1. WebSocket là kết nối transport riêng sau handshake; cookie/session không được kiểm tra lại ở mỗi frame nếu ứng dụng không có cơ chế liên kết và đóng connection.
2. Tích hợp tự động làm việc với Spring WebSocket/Spring Messaging; không hỗ trợ trực tiếp JSR-356 thuần.
3. WebSocketConnectHandlerDecoratorFactory, SessionRepositoryMessageInterceptor ở handshake/inbound channel và WebSocketRegistryListener.
4. Lưu Spring Session ID vào WebSocket properties để interceptor tìm session khi nhận message.
5. CONNECT, MESSAGE, SUBSCRIBE và UNSUBSCRIBE.
6. Vì chỉ inbound activity từ client được coi là user activity trong interceptor mặc định.
7. Invalidate HttpSession, clear SecurityContext và repository, cleanup Remember-Me/CSRF, phát LogoutSuccessEvent rồi chạy success handler.
8. LogoutSuccessEvent phản ánh logout flow; SessionDeletedEvent/SessionDestroyedEvent phản ánh vòng đời session và được WebSocketRegistryListener dùng.
9. Mapping Spring Session ID đến một hoặc nhiều WebSocketSession.
10. Indexed repository hỗ trợ session events; Redis keyspace notifications giúp listener nhận delete/expired event.
11. E bật keyevent, g gồm generic command events, x gồm expired events.
12. Redis expiration notification và cleanup task có thể bất đồng bộ; event đến trễ hơn TTL.
13. API JdbcIndexedSessionRepository hiện không hỗ trợ publish session events, nên listener không nhận được tín hiệu destroy từ repository đó.
14. ApplicationEvent chỉ nằm trong một application context; node khác không tự nhận.
15. Mở socket ở A, logout qua B, dùng Redis shared repository và event listener ở cả hai node, chờ socket A đóng.
16. Một HttpSession có thể có nhiều tab/socket; cần bảo đảm tất cả connection đều được đóng.
17. Dừng gửi message, cập nhật UI disconnected và chỉ reconnect sau khi xác thực lại.
18. Active connection count, SessionDestroyedEvent, close latency, listener health, stale mapping và reconnect sau logout.

## Kết luận

WebSocket tồn tại độc lập với từng HTTP request, vì vậy việc invalidate HttpSession cần được nối với vòng đời của các WebSocket connection đã mở. Spring Session cung cấp tích hợp cho Spring WebSocket/STOMP qua AbstractSessionWebSocketMessageBrokerConfigurer: interceptor lưu Session ID vào handshake properties và cập nhật lastAccessedTime khi nhận inbound message; registry listener theo dõi mapping session-to-socket và đóng socket khi nhận SessionDestroyedEvent.

Với Redis, dùng indexed repository và cấu hình keyspace notifications để phát SessionDeletedEvent hoặc SessionExpiredEvent. Event và cleanup là bất đồng bộ, nên socket có thể đóng sau thời điểm TTL chạm ngưỡng; hãy kiểm thử bằng eventual assertion. JdbcIndexedSessionRepository tiêu chuẩn không hỗ trợ phát session events, vì vậy cần broadcast/close mechanism riêng nếu yêu cầu đóng socket sau logout hoặc expiration. Trong hệ thống nhiều node, event phải đến mọi node đang giữ connection. Luôn kiểm tra cả logout HTTP, session repository, event propagation, socket close và hành vi reconnect của client; xóa cookie đơn thuần không thu hồi một WebSocket đã mở.

