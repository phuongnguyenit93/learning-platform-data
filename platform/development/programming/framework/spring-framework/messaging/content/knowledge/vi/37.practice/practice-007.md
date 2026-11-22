# Thực nghiệm thông báo riêng cho người dùng có nhiều phiên

Một người dùng có thể đăng nhập cùng lúc trên nhiều nơi: hai tab trình duyệt, laptop và điện thoại, hoặc nhiều cửa sổ ứng dụng. Mỗi kết nối WebSocket/STOMP tạo một session riêng, nhưng các session đó có thể cùng gắn với một Principal đã xác thực. Khi server gửi thông báo tới người dùng, Spring cần xác định gửi tới tất cả session của người đó hay chỉ session đang thực hiện một thao tác.

Spring STOMP hỗ trợ user destination qua tiền tố `/user/`. Cơ chế này cho phép client subscribe một destination tổng quát như `/user/queue/notifications`; Spring chuyển nó thành destination riêng cho từng session. Phía server có thể gửi tới user bằng `SimpMessagingTemplate.convertAndSendToUser(...)` hoặc `@SendToUser`.

Thực nghiệm dưới đây tạo hai kết nối cho cùng user `alice`, thêm một kết nối của `bob` để kiểm tra cách ly. Bài test xác nhận ba hành vi: thông báo service gửi cho Alice tới cả hai session đã subscribe; `@SendToUser` mặc định broadcast tới các session của Alice; `broadcast=false` chỉ gửi về session đã phát sinh request.

## 1. Mô hình nhiều session của cùng một user

Cần phân biệt ba định danh:

- **Principal / username:** danh tính đã xác thực của người dùng, ví dụ `alice`.
- **WebSocket session ID:** định danh của từng kết nối WebSocket. Mỗi tab hoặc thiết bị thường có một session ID khác nhau.
- **STOMP subscription ID:** định danh subscription trong một STOMP session. Một session có thể subscribe nhiều destination.

Ví dụ Alice đăng nhập trên trình duyệt và điện thoại:

~~~text
Principal: alice
  |
  +-- WebSocket session: ws-101
  |     +-- STOMP subscription: /user/queue/notifications
  |     +-- STOMP subscription: /user/queue/orders
  |
  +-- WebSocket session: ws-202
        +-- STOMP subscription: /user/queue/notifications

Principal: bob
  |
  +-- WebSocket session: ws-303
        +-- STOMP subscription: /user/queue/notifications
~~~

Cả `ws-101` và `ws-202` có cùng Principal `alice`, nhưng là hai kết nối độc lập. Session `ws-303` thuộc `bob` nên không được nhận thông báo riêng của Alice.

### 1.1. User destination được Spring phân giải thế nào?

Client subscribe destination logic:

~~~text
/user/queue/notifications
~~~

`UserDestinationMessageHandler` nhận destination có tiền tố `/user/` và phân giải nó thành destination vật lý riêng theo session, ví dụ:

~~~text
Alice / ws-101 -> /queue/notifications-user101
Alice / ws-202 -> /queue/notifications-user202
Bob   / ws-303 -> /queue/notifications-user303
~~~

Tên hậu tố ở trên chỉ minh họa; không nên phụ thuộc vào cách Spring tạo tên nội bộ. Ý nghĩa quan trọng là subscription của mỗi session được tách biệt. Nhiều người cùng subscribe `/user/queue/notifications` không bị nhận nhầm message của nhau.

Khi server gửi tới user `alice`, Spring tìm các session đang đăng ký của Alice rồi chuyển message tới destination tương ứng. Chỉ các session đã subscribe destination đích mới nhận được message. Một session đang kết nối nhưng chưa subscribe `/user/queue/notifications` sẽ không tự động nhận thông báo đó.

### 1.2. User destination không phải hộp thư offline

User destination định tuyến tới các session đang hoạt động và đã subscribe. Nếu Alice không còn session nào, thông báo không tự được lưu thành hộp thư để giao khi cô ấy đăng nhập lại.

Nếu nghiệp vụ yêu cầu thông báo offline, cần lưu notification trong database hoặc một message store bền vững, sau đó đồng bộ lại khi client kết nối. WebSocket push nên được xem là kênh cập nhật tức thời; trạng thái đã đọc, lịch sử và khả năng giao lại phải được quản lý ở tầng nghiệp vụ.

## 2. Cấu hình STOMP endpoint và broker

Spring WebSocket cần hai nhóm destination:

- `/app`: message client gửi lên ứng dụng để được xử lý bởi `@MessageMapping`.
- `/queue` hoặc `/topic`: destination do broker quản lý để gửi tới subscriber.

Ví dụ cấu hình đơn giản dùng built-in simple broker:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/queue", "/topic");
    }
}
~~~

Client kết nối WebSocket tới `/ws`, sau đó gửi STOMP frame. Message có destination bắt đầu bằng `/app` được định tuyến tới controller; message bắt đầu bằng `/queue` hoặc `/topic` được chuyển tới broker.

Simple broker phù hợp cho thử nghiệm và ứng dụng đơn giản. Nó lưu subscription trong bộ nhớ của process, không phải broker phân tán và không cung cấp durability như broker chuyên dụng. Khi triển khai nhiều application node hoặc cần broker đầy đủ tính năng, dùng STOMP broker relay tới broker hỗ trợ STOMP.

### 2.1. Prefix phải được cấu hình đúng

User destination được xử lý bởi `UserDestinationMessageHandler`. Nếu để broker nhận trực tiếp destination `/user/**`, broker có thể xử lý sai message chưa được Spring phân giải. Hãy bảo đảm `/user` không bị cấu hình như một broker prefix thông thường.

Client subscribe `/user/queue/notifications`; khi gửi từ service, truyền username và destination logic `/queue/notifications` vào `convertAndSendToUser`. Không tự thêm `/user/{username}` vào destination thứ hai.

## 3. Gửi thông báo tới tất cả session của một user

Từ một service bất kỳ, có thể inject `SimpMessagingTemplate`:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String username, String message) {
        this.messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                message);
    }
}
~~~

Khi gọi:

~~~java
notificationService.notifyUser("alice", "Đơn hàng đã được giao");
~~~

Spring tìm các session hiện tại của `alice` và gửi tới các session có subscription `/user/queue/notifications`. Nếu Alice đang mở trình duyệt và điện thoại, cả hai đều nhận được thông báo. Session của Bob không nhận được.

`convertAndSendToUser` phù hợp cho thông báo phát sinh từ service, scheduled job, event listener hoặc kết quả xử lý nghiệp vụ. Nơi gọi không cần biết session ID của từng tab.

### 3.1. Không gửi bằng username do client tự khai báo

Username truyền vào `convertAndSendToUser` phải đến từ trạng thái xác thực hoặc dữ liệu nghiệp vụ phía server. Không lấy một username tùy ý trong payload của client rồi dùng nó làm đích gửi.

Một client không được tự nhận là Alice bằng cách gửi STOMP header `login: alice` hoặc gửi message tới một destination của user khác. Trong ứng dụng WebSocket, Spring dùng Principal gắn với HTTP handshake; thông tin đăng nhập trong STOMP CONNECT không thay thế xác thực phía server.

## 4. @SendToUser: broadcast mặc định và broadcast=false

`@SendToUser` gửi kết quả của một phương thức `@MessageMapping` tới user gắn với message đầu vào.

### 4.1. Mặc định: gửi tới các session của user

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
class NotificationController {

    @MessageMapping("/notify-all")
    @SendToUser("/queue/notifications")
    public String notifyAllSessions(String message) {
        return message;
    }
}
~~~

Client Alice gửi tới `/app/notify-all`. Kết quả trả về được gửi tới các session của Alice đã subscribe `/user/queue/notifications`. Theo mặc định, `broadcast` của `@SendToUser` là `true`, nên nhiều session của cùng user đều có thể nhận kết quả.

Đây là hành vi phù hợp khi một thao tác ở thiết bị này cần cập nhật các thiết bị khác, ví dụ trạng thái đơn hàng, thay đổi hồ sơ, số dư hoặc thông báo đăng nhập.

### 4.2. Chỉ trả lời session phát sinh request: broadcast=false

Đôi khi message chỉ dành cho tab đã gửi request, ví dụ:
- Kết quả validation của một biểu mẫu đang mở.
- Lỗi của một thao tác cụ thể.
- Phản hồi tạm thời của một lệnh điều khiển giao diện.
- Kết quả autocomplete hoặc truy vấn chỉ phục vụ màn hình hiện tại.

Có thể dùng:

~~~java
@MessageMapping("/notify-current")
@SendToUser(
        destinations = "/queue/notifications",
        broadcast = false)
public String notifyCurrentSession(String message) {
    return message;
}
~~~

Nếu Alice gửi `/app/notify-current` từ session `ws-101`, chỉ session đã gửi message đó nhận kết quả. Session `ws-202` của Alice và session của Bob không nhận được.

`broadcast=false` đặc biệt hữu ích cho `@MessageExceptionHandler`: lỗi của một message chỉ trả về đúng client session đã tạo ra lỗi đó, tránh việc tab khác nhận một thông báo lỗi không liên quan.

~~~java
@MessageMapping("/update-profile")
public void updateProfile(ProfileCommand command) {
    // Validate và cập nhật hồ sơ.
}

@MessageExceptionHandler
@SendToUser(
        destinations = "/queue/errors",
        broadcast = false)
public ApplicationError handleProfileError(ProfileValidationException ex) {
    return new ApplicationError("INVALID_PROFILE", ex.getMessage());
}
~~~

`broadcast=false` dựa trên session của message đang được xử lý. Một background job không có session gửi request ban đầu; do đó không nên dùng nó như một cơ chế chọn thiết bị từ một service chạy nền. Nếu nghiệp vụ cần gửi riêng tới một thiết bị, hãy thiết kế định danh thiết bị/session và cơ chế định tuyến rõ ràng ở tầng ứng dụng.

### 4.3. Session không có Principal

Spring vẫn cho phép một WebSocket session chưa gắn với authenticated user subscribe user destination. Tuy nhiên, `@SendToUser` trong trường hợp không có user được định danh sẽ hành xử như `broadcast=false`: chỉ session đã gửi message được nhắm tới.

Nếu cần gửi tới tất cả thiết bị của một người dùng, hãy bảo đảm mỗi session được gắn với cùng một Principal đã xác thực.

## 5. Thực nghiệm end-to-end với hai session của Alice

Mục tiêu của bài thử:

1. Tạo hai kết nối STOMP độc lập cùng xác thực thành `alice`.
2. Tạo một kết nối thứ ba xác thực thành `bob`.
3. Cả ba subscribe `/user/queue/notifications`.
4. Gửi thông báo từ `SimpMessagingTemplate` tới Alice và xác nhận cả hai session của Alice nhận được.
5. Gửi message qua `@SendToUser` mặc định và xác nhận cả hai session nhận được.
6. Gửi message qua `broadcast=false` và xác nhận chỉ session nguồn nhận được.
7. Ngắt một session của Alice, xác nhận registry còn một session và push tiếp chỉ tới session còn lại.

Dùng client thật và server nhúng để kiểm tra toàn bộ đường đi WebSocket/STOMP, thay vì chỉ gọi trực tiếp method controller. Spring phân biệt server-side test với end-to-end test; bài này cần end-to-end vì hành vi nhiều session phụ thuộc handshake Principal, session registry, subscription và user-destination resolver.

### 5.1. Dependencies cho test

Ví dụ dùng Java 17+, Spring Boot 3.4+ / Spring Framework 6.2+ và JUnit 5. Trong Maven, dùng dependency management của Spring Boot:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-websocket</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.awaitility</groupId>
        <artifactId>awaitility</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Boot quản lý version tương thích của Spring Framework, WebSocket và JUnit. Awaitility được dùng để chờ subscription xuất hiện trong registry mà không dùng `Thread.sleep`.

### 5.2. Test application: cấp Principal riêng cho từng handshake

Trong production, Principal phải đến từ authentication thật, thường là HTTP handshake được Spring Security bảo vệ. Trong test, ta dùng một header chỉ dành cho test để mô phỏng ba client có hai username khác nhau.

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.support.DefaultHandshakeHandler;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@SpringBootConfiguration
@EnableAutoConfiguration
@EnableWebSocketMessageBroker
static class TestApplication implements WebSocketMessageBrokerConfigurer {

    @Bean
    NotificationController notificationController() {
        return new NotificationController();
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setHandshakeHandler(new DefaultHandshakeHandler() {
                    @Override
                    protected Principal determineUser(
                            ServerHttpRequest request,
                            WebSocketHandler wsHandler,
                            Map<String, Object> attributes) {

                        String username =
                                request.getHeaders().getFirst("X-Test-User");

                        if (username == null || username.isBlank()) {
                            return null;
                        }

                        return () -> username;
                    }
                });
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/queue");
    }
}
~~~

Đây là cấu hình dành riêng cho test. Không dùng header `X-Test-User` làm cơ chế xác thực production: client có thể tự đặt giá trị đó. Trong ứng dụng thật, dùng Principal được xác minh ở HTTP handshake, session hoặc token authentication theo cấu hình bảo mật.

### 5.3. Controller có hai kiểu gửi

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
class NotificationController {

    @MessageMapping("/notify-all")
    @SendToUser("/queue/notifications")
    public String notifyAllSessions(String message) {
        return message;
    }

    @MessageMapping("/notify-current")
    @SendToUser(
            destinations = "/queue/notifications",
            broadcast = false)
    public String notifyCurrentSession(String message) {
        return message;
    }
}
~~~

Hai method chỉ khác nhau ở `broadcast`. Method đầu gửi tới tất cả session của Principal đang xử lý message; method thứ hai giới hạn kết quả vào session đã gửi message.

### 5.4. Integration test với WebSocketStompClient

Test dưới đây tạo ba STOMP client session. Hai session đầu có Principal `alice`; session thứ ba có Principal `bob`.

~~~java
import java.lang.reflect.Type;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.messaging.simp.user.SimpUser;
import org.springframework.messaging.simp.user.SimpUserRegistry;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.junit.jupiter.api.Assertions.*;

import static org.awaitility.Awaitility.await;

@SpringBootTest(
        classes = UserDestinationMultiSessionTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UserDestinationMultiSessionTest {

    @LocalServerPort
    int port;

    @Autowired
    SimpMessagingTemplate messagingTemplate;

    @Autowired
    SimpUserRegistry userRegistry;

    private WebSocketStompClient stompClient;
    private final List<StompSession> sessions = new ArrayList<>();

    @BeforeEach
    void setUp() {
        stompClient = new WebSocketStompClient(
                new StandardWebSocketClient());
        stompClient.setMessageConverter(new StringMessageConverter());
        stompClient.start();
    }

    @AfterEach
    void tearDown() {
        for (StompSession session : sessions) {
            if (session.isConnected()) {
                session.disconnect();
            }
        }
        stompClient.stop();
    }

    @Test
    void sendsToAllUserSessionsAndCanReplyOnlyToOrigin() throws Exception {
        StompSession aliceBrowser = connect("alice");
        StompSession aliceMobile = connect("alice");
        StompSession bobBrowser = connect("bob");

        BlockingQueue<String> browserInbox = new LinkedBlockingQueue<>();
        BlockingQueue<String> mobileInbox = new LinkedBlockingQueue<>();
        BlockingQueue<String> bobInbox = new LinkedBlockingQueue<>();

        aliceBrowser.subscribe(
                "/user/queue/notifications", frameHandler(browserInbox));
        aliceMobile.subscribe(
                "/user/queue/notifications", frameHandler(mobileInbox));
        bobBrowser.subscribe(
                "/user/queue/notifications", frameHandler(bobInbox));

        // Wait until all three sessions and their subscriptions are registered.
        await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
            assertUserReady("alice", 2);
            assertUserReady("bob", 1);
        });

        // 1. A service push to Alice reaches both Alice sessions.
        messagingTemplate.convertAndSendToUser(
                "alice", "/queue/notifications", "service-push");

        assertEquals("service-push", browserInbox.poll(5, SECONDS));
        assertEquals("service-push", mobileInbox.poll(5, SECONDS));
        assertNull(bobInbox.poll(300, TimeUnit.MILLISECONDS));

        // 2. Default @SendToUser also reaches all subscribed Alice sessions.
        aliceBrowser.send("/app/notify-all", "controller-broadcast");

        assertEquals("controller-broadcast", browserInbox.poll(5, SECONDS));
        assertEquals("controller-broadcast", mobileInbox.poll(5, SECONDS));
        assertNull(bobInbox.poll(300, TimeUnit.MILLISECONDS));

        // 3. broadcast=false returns only to the originating session.
        aliceBrowser.send("/app/notify-current", "current-session-only");

        assertEquals("current-session-only", browserInbox.poll(5, SECONDS));
        assertNull(mobileInbox.poll(500, TimeUnit.MILLISECONDS));
        assertNull(bobInbox.poll(500, TimeUnit.MILLISECONDS));

        // 4. After the mobile session disconnects, the registry has one Alice session.
        aliceMobile.disconnect();

        await().atMost(Duration.ofSeconds(5)).untilAsserted(
                () -> assertUserReady("alice", 1));

        messagingTemplate.convertAndSendToUser(
                "alice", "/queue/notifications", "after-disconnect");

        assertEquals("after-disconnect", browserInbox.poll(5, SECONDS));
        assertNull(bobInbox.poll(300, TimeUnit.MILLISECONDS));
    }

    private StompSession connect(String username) throws Exception {
        WebSocketHttpHeaders headers = new WebSocketHttpHeaders();
        headers.add("X-Test-User", username);

        StompSession session = stompClient.connectAsync(
                "ws://localhost:" + port + "/ws",
                headers,
                new StompSessionHandlerAdapter() {
                }).get(5, SECONDS);

        sessions.add(session);
        return session;
    }

    private void assertUserReady(String username, int expectedSessions) {
        SimpUser user = userRegistry.getUser(username);

        assertNotNull(user);
        assertEquals(expectedSessions, user.getSessions().size());
        assertTrue(user.getSessions().stream()
                .allMatch(session -> session.getSubscriptions().size() == 1));
    }

    private StompFrameHandler frameHandler(BlockingQueue<String> inbox) {
        return new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return String.class;
            }

            @Override
            public void handleFrame(StompHeaders headers, Object payload) {
                inbox.add((String) payload);
            }
        };
    }
}
~~~

Đây là một integration test class cho Spring Boot 3.4+ / Spring Framework 6.2+, không phải Java file chạy bằng `javac` đơn lẻ. Test cần embedded WebSocket server và các dependency ở mục 5.1. Có thể chạy trong Maven project bằng:

~~~bash
mvn -Dtest=UserDestinationMultiSessionTest test
~~~

Bài test không dùng `Thread.sleep`. Awaitility đợi user registry ghi nhận đủ session/subscription; `BlockingQueue.poll(timeout)` chờ message với thời hạn rõ ràng. Với negative assertion, khoảng chờ ngắn xác nhận session khác không nhận được frame trong cửa sổ quan sát.

Simple broker không hỗ trợ STOMP RECEIPT để xác nhận SUBSCRIBE đã được broker xử lý. Vì vậy, test chờ `SimpUserRegistry` thấy subscription trước khi gửi. Nếu dùng broker relay có hỗ trợ receipt, có thể bật receipt ở client và chờ callback của `StompSession.Subscription` thay cho registry polling.

### 5.5. Kết quả mong đợi

| Thao tác | Alice browser | Alice mobile | Bob browser |
|---|---|---|---|
| `convertAndSendToUser("alice", ...)` | Nhận | Nhận | Không nhận |
| `@SendToUser` mặc định | Nhận | Nhận | Không nhận |
| `@SendToUser(broadcast=false)` từ browser | Nhận | Không nhận | Không nhận |
| Sau khi mobile disconnect | Nhận push mới | Đã ngắt kết nối | Không nhận |

Bài test cũng kiểm tra rằng khi mobile session đóng, `SimpUserRegistry` còn một session của Alice. Khi gửi push tiếp theo, chỉ session còn hoạt động nhận được message.

## 6. Vì sao phải đợi subscription sẵn sàng?

Gọi `session.subscribe(...)` chỉ gửi một STOMP SUBSCRIBE frame. Nó không đồng nghĩa broker đã đăng ký xong subscription tại đúng thời điểm dòng code tiếp theo chạy.

Nếu gửi thông báo ngay sau subscribe, test có thể gặp race condition:
- Test gửi push trước khi broker xử lý SUBSCRIBE.
- Một session nhận message nhưng session kia chưa kịp đăng ký.
- Test lúc pass, lúc fail tùy tốc độ máy và scheduler.

Với built-in simple broker, STOMP RECEIPT không được hỗ trợ. Có thể đợi `SimpUserRegistry` thấy session và subscription như ví dụ trên, hoặc dùng `ExecutorChannelInterceptor` ở broker channel để phát tín hiệu sau khi subscription được xử lý.

Không giải quyết race bằng `Thread.sleep(500)`. Sleep không chứng minh subscription đã sẵn sàng và làm test phụ thuộc vào thời gian thực.

## 7. Quan sát vòng đời session

Spring phát các ApplicationContext event hữu ích cho việc theo dõi session:

- `SessionConnectEvent`: nhận STOMP CONNECT; event có session ID và user information nếu có.
- `SessionConnectedEvent`: broker đã trả CONNECTED; STOMP session được xem là thiết lập hoàn chỉnh.
- `SessionSubscribeEvent`: client tạo subscription.
- `SessionUnsubscribeEvent`: client hủy subscription.
- `SessionDisconnectEvent`: STOMP session kết thúc.

Có thể dùng các event này để cập nhật số session online, thiết bị đang hoạt động, thời điểm kết nối và trạng thái subscription. `SessionDisconnectEvent` có thể được phát nhiều lần cho cùng session trong một số trường hợp; logic dọn dẹp phải idempotent.

Ví dụ listener ghi nhận session:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
class StompSessionAudit {

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        var accessor =
                SimpMessageHeaderAccessor.wrap(event.getMessage());

        String sessionId = accessor.getSessionId();
        String username = accessor.getUser() != null
                ? accessor.getUser().getName()
                : "anonymous";

        // Ghi nhận sessionId, username và connectedAt.
    }

    @EventListener
    public void onDisconnected(SessionDisconnectEvent event) {
        var accessor =
                SimpMessageHeaderAccessor.wrap(event.getMessage());

        String sessionId = accessor.getSessionId();

        // Xóa session nếu còn tồn tại; thao tác phải idempotent.
    }
}
~~~

Không tự duy trì một registry khác nếu `SimpUserRegistry` đã đáp ứng yêu cầu. Nếu cần lưu thiết bị, tên trình duyệt hoặc device ID, lưu metadata riêng có xác thực và gắn với session ID; không dùng device ID do client gửi làm bằng chứng danh tính.

## 8. Nhiều application node và broker relay

Trong một application instance, `DefaultSimpUserRegistry` biết các user session kết nối tới instance đó. Khi triển khai nhiều node, Alice có thể kết nối vào node A bằng trình duyệt và node B bằng điện thoại. Nếu node gửi message chỉ biết local registry, nó có thể không tìm thấy session nằm trên node khác.

Với STOMP broker relay, Spring hỗ trợ chia sẻ registry và chuyển tiếp user destination chưa phân giải:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setUserRegistryBroadcast("/topic/simp-user-registry")
            .setUserDestinationBroadcast("/topic/unresolved-user-destination");
}
~~~

- `setUserRegistryBroadcast`: broadcast thông tin user registry local và nhận registry từ các node khác, giúp mỗi node biết session user đang nằm ở đâu.
- `setUserDestinationBroadcast`: broadcast message user destination chưa được node hiện tại phân giải để node khác có cơ hội xử lý.

Các destination broadcast này phải được bảo vệ và dành riêng cho hạ tầng. Không để client tùy ý publish vào chúng. Broker relay cần cấu hình thông tin kết nối, credentials và heartbeat phù hợp với broker thực tế.

Built-in simple broker phù hợp thử nghiệm trong một process; nó không tự đồng bộ session registry giữa nhiều node. Không coi việc đặt ứng dụng sau load balancer là đủ để user destination tự động tìm session trên mọi instance.

### 8.1. Quản lý queue theo session ở external broker

Khi dùng external broker, user destination có thể được ánh xạ thành destination riêng theo session. Cần xem tài liệu broker về việc xóa queue không còn consumer hoặc session đã đóng. Ví dụ một số cách cấu hình RabbitMQ dùng auto-delete queue; ActiveMQ có cơ chế purge destination không hoạt động.

Nếu queue riêng theo session không được dọn, broker có thể tích lũy destination rác. Nếu dọn quá sớm, message đang được xử lý hoặc session reconnect có thể bị ảnh hưởng. Chọn policy theo semantics và retention của broker.

## 9. Phân quyền và bảo mật

User destination không thay thế authorization.

1. **Principal phải đến từ xác thực phía server.** Trong ứng dụng HTTP/WebSocket, Spring dùng Principal gắn với handshake. Đừng tin username trong payload hoặc một STOMP header tùy ý.
2. **Không cho client gửi tới user destination của người khác.** Cấu hình Spring Security message authorization để kiểm tra destination, command và quyền user.
3. **Service chỉ định đúng username.** `convertAndSendToUser` nên nhận username lấy từ domain event hoặc kết quả xác thực, không lấy từ request field chưa kiểm tra.
4. **Không phát dữ liệu nhạy cảm vào mọi session nếu không cần.** Broadcast mặc định phù hợp cho đồng bộ trạng thái; thông tin nhạy cảm theo thao tác nên giới hạn session hoặc thiết kế destination riêng.
5. **Kiểm soát subscription.** Client không được subscribe một destination chỉ vì biết tên user hoặc queue.
6. **Bảo vệ destination nội bộ.** Các destination user-registry broadcast và unresolved-destination broadcast phải dành riêng cho broker relay.
7. **Giới hạn session và rate.** Một tài khoản có thể mở nhiều session; áp dụng giới hạn hợp lý để tránh lạm dụng tài nguyên và giữ kiểm soát số thiết bị.

Spring Security hỗ trợ authorization cho WebSocket sub-protocol thông qua `ChannelInterceptor`. Hãy kiểm tra cả CONNECT, SUBSCRIBE, SEND và message tới các prefix ứng dụng/broker theo chính sách của hệ thống.

## 10. Chẩn đoán khi nhiều session không nhận đúng message

### 10.1. Chỉ một trong hai session của Alice nhận được

Kiểm tra:
- Cả hai handshake có cùng Principal name không?
- Hai session có thực sự còn kết nối không?
- Cả hai đã subscribe đúng `/user/queue/notifications` chưa?
- Message gửi từ `convertAndSendToUser` có đúng username và destination không?
- Session thứ hai có nằm ở node khác không, và user registry broadcast đã cấu hình chưa?

### 10.2. Bob cũng nhận được thông báo của Alice

Kiểm tra:
- Có đang gửi nhầm `/topic/notifications` thay cho user destination không?
- User destination có bị broker xử lý trực tiếp do prefix configuration sai không?
- Principal của các kết nối có bị gán chung hoặc bị giả mạo không?
- Service có gửi broadcast tới destination công khai không?

### 10.3. broadcast=false vẫn gửi tới thiết bị khác

Kiểm tra annotation có thật sự được đặt trên method đang xử lý message không; response có đang được gửi bằng một `SimpMessagingTemplate.convertAndSendToUser` riêng trong service không? `broadcast=false` chỉ giới hạn message được gửi theo ngữ cảnh session của message đang xử lý, không tự động giới hạn mọi push khác trong cùng nghiệp vụ.

### 10.4. Session đã đóng nhưng registry vẫn còn

Kiểm tra WebSocket close có được phát hiện không, listener xử lý `SessionDisconnectEvent` có chạy không và có exception trong cleanup không. Event có thể được phát nhiều lần, vì vậy cleanup cần idempotent và không được trừ/xóa trạng thái nhiều lần.

### 10.5. Gửi được khi chạy một node nhưng thất bại khi scale ngang

Kiểm tra `SimpUserRegistry` local và multi-server registry, broker relay, `userRegistryBroadcast`, `userDestinationBroadcast`, destination ACL và topology của broker. Thử kết nối hai client cùng user vào hai application instance khác nhau để tái hiện lỗi.

## 11. Mở rộng bộ kiểm thử

Sau bài test cơ bản, nên bổ sung các trường hợp:

- Một user có 1, 2, 5 hoặc nhiều session; xác nhận số session thực tế và fan-out.
- Hai user cùng subscribe một destination logic; xác nhận không nhận chéo.
- Một session unsubscribe nhưng vẫn còn kết nối; session đó không nhận message ở destination đã hủy.
- Một session disconnect; registry cập nhật số session còn lại.
- Tất cả session disconnect; user không còn trong registry.
- User chưa kết nối; kiểm tra service push không được hiểu nhầm là message đã được lưu offline.
- Một session reconnect với session ID mới; kiểm tra registry không giữ session cũ.
- Exception handler trả lỗi bằng `broadcast=false`; chỉ client gây lỗi nhận thông báo.
- Broker relay mất kết nối; kiểm tra `BrokerAvailabilityEvent`, lỗi gửi và reconnect behavior.
- Hai application node; kiểm tra registry broadcast và unresolved destination routing.
- Nhiều session gửi đồng thời; kiểm tra message ID/correlation ID và tính idempotent của handler.

Với end-to-end test nhiều client, hãy đóng session, unsubscribe và dừng `WebSocketStompClient` trong cleanup để không để lại connection hoặc heartbeat task giữa các test.

## 12. Checklist production

- [ ] Mỗi WebSocket session được gắn với Principal đã xác thực.
- [ ] Client subscribe user destination logic như `/user/queue/notifications`.
- [ ] Server gửi user push bằng `convertAndSendToUser(username, destination, payload)`.
- [ ] Đã quyết định rõ notification cần tới mọi session hay chỉ session nguồn.
- [ ] `@SendToUser` mặc định broadcast tới mọi session đã subscribe.
- [ ] Dùng `broadcast=false` cho phản hồi chỉ dành cho session đang xử lý request.
- [ ] Không coi user destination là offline inbox hoặc durable notification store.
- [ ] Có chính sách authorization cho CONNECT, SUBSCRIBE và SEND.
- [ ] Có giới hạn session/concurrency và giám sát connection lifecycle.
- [ ] Cleanup session idempotent khi nhận disconnect event.
- [ ] Nếu scale nhiều node, đã cấu hình user registry broadcast và unresolved destination broadcast với broker relay.
- [ ] Broker dọn destination/queue riêng theo session khi không còn sử dụng.
- [ ] Có integration test với hai session cùng Principal và một user khác làm isolation control.

## Tài liệu tham khảo

- Spring Framework Reference — User Destinations, multi-session behavior, `@SendToUser` và `convertAndSendToUser`: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Framework Reference — Enable STOMP, application/broker prefixes và endpoint configuration: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Framework Reference — Testing STOMP over WebSocket, server-side và end-to-end tests: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html
- Spring Framework Reference — STOMP Client và `WebSocketStompClient`: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html
- Spring Framework Reference — Annotated Controllers, `@MessageMapping`, `@SendToUser` và exception handlers: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework Reference — STOMP ApplicationContext Events: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html
- Spring Framework Javadoc — `SimpUserRegistry`, `SimpUser`, `SimpSession` và `SimpSubscription`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/package-summary.html
- Spring Framework Javadoc — `StompBrokerRelayRegistration` multi-server registry broadcast: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html
