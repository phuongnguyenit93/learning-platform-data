# Kiểm thử user destination với nhiều người dùng và nhiều phiên

## 1. User destination giải quyết vấn đề gì?

Trong Spring STOMP over WebSocket, client có thể đăng ký nhận thông báo riêng bằng destination bắt đầu với `/user/`. Ví dụ:

```text
SUBSCRIBE /user/queue/notifications
```

Client không cần biết session ID nội bộ. Spring nhận subscription này qua `UserDestinationMessageHandler` và chuyển nó thành một destination riêng cho session đang kết nối, ví dụ:

```text
/user/queue/notifications
        |
        | UserDestinationMessageHandler
        v
/queue/notifications-userA1
```

Một session khác của cùng người dùng cũng đăng ký `/user/queue/notifications`, nhưng Spring tạo destination vật lý khác, ví dụ `/queue/notifications-userA2`. Vì vậy, hai session có thể dùng cùng tên destination logic mà không nhận nhầm thông báo của nhau.

Ở chiều gửi, ứng dụng có thể gửi tới `/user/{username}/queue/notifications`. Spring tìm các session đang hoạt động của user đó trong `SimpUserRegistry`, sau đó chuyển thành một destination cho mỗi session.

```text
/user/alice/queue/notifications
        |
        +--> /queue/notifications-userA1
        |
        +--> /queue/notifications-userA2
```

Các tên có hậu tố session ở trên chỉ minh họa. Không nên viết test phụ thuộc vào chính xác chuỗi hậu tố do Spring sinh ra. Hãy kiểm tra session nào nhận được message và session nào không nhận được.

## 2. Phân biệt nhiều người dùng và nhiều session

Một user có thể mở nhiều tab trình duyệt, đăng nhập trên nhiều thiết bị hoặc tạo nhiều WebSocket connection. Mỗi connection tạo một session riêng, nhưng nhiều session vẫn có thể thuộc cùng một principal.

Ví dụ trạng thái đang hoạt động:

| User | Session | Subscription |
|---|---|---|
| alice | alice-1 | `/user/queue/notifications` |
| alice | alice-2 | `/user/queue/notifications` |
| bob | bob-1 | `/user/queue/notifications` |
| charlie | charlie-1 | `/user/queue/notifications` |

Khi ứng dụng gửi tới user `alice`, chỉ hai session `alice-1` và `alice-2` được chọn. Session của `bob` và `charlie` không nhận được message dù đăng ký cùng destination logic.

Cần kiểm thử riêng hai chiều:

- **Cách ly giữa người dùng:** message gửi cho Alice không được đến Bob.
- **Fan-out trong cùng người dùng:** message gửi cho Alice được chuyển đến mọi session Alice đang đăng ký destination tương ứng.

`SimpUserRegistry` là nguồn thông tin về user và các session đang kết nối. `DefaultUserDestinationResolver` dùng registry này để tìm session và tạo destination đích. Các API `SimpUser.getSessions()`, `SimpSession.getSubscriptions()` và `SimpSubscription.getDestination()` hữu ích khi kiểm tra trạng thái kết nối trong test.

## 3. Quy tắc broadcast của @SendToUser

`@SendToUser` mặc định có `broadcast = true`. Nếu một người dùng có nhiều session, phản hồi được gửi tới tất cả session của người đó đang subscribe destination tương ứng.

```java
@Controller
public class NotificationController {

    @MessageMapping("/notify-all")
    @SendToUser("/queue/notifications")
    public String notifyAllSessions(String message, Principal principal) {
        return principal.getName() + ":" + message;
    }

    @MessageMapping("/notify-current")
    @SendToUser(value = "/queue/notifications", broadcast = false)
    public String notifyCurrentSession(String message, Principal principal) {
        return principal.getName() + ":" + message;
    }
}
```

Với hai session của Alice:

- Gửi `/app/notify-all` từ `alice-1`: cả `alice-1` và `alice-2` nhận phản hồi nếu cả hai subscribe `/user/queue/notifications`.
- Gửi `/app/notify-current` từ `alice-1`: chỉ `alice-1` nhận phản hồi. `alice-2` không nhận.

`broadcast = false` hữu ích cho phản hồi gắn với thao tác hoặc lỗi của một tab cụ thể. Ví dụ, tab gửi lệnh cập nhật hồ sơ cần nhận lỗi validation, trong khi tab khác đang mở cùng tài khoản không cần nhận lỗi đó.

Với session không gắn principal đã xác thực, Spring vẫn hỗ trợ user destination theo session ID. Trong trường hợp đó, hành vi `@SendToUser` tương đương gửi cho riêng session hiện tại, giống `broadcast = false`.

## 4. Gửi thông báo từ service bằng SimpMessagingTemplate

Không phải thông báo nào cũng xuất phát từ một `@MessageMapping` handler. Service, scheduler hoặc event listener có thể gửi trực tiếp cho một user bằng `SimpMessagingTemplate`.

```java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String username, String message) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                message
        );
    }
}
```

Tham số đầu tiên là tên user trong `Principal.getName()`. Destination thứ hai là phần queue logic, ví dụ `/queue/notifications`; không thêm `/user/{username}` vào tham số này vì `convertAndSendToUser` tự áp dụng user destination prefix.

Khi Alice có hai session cùng subscribe queue, lời gọi `notifyUser("alice", "...")` sẽ gửi tới cả hai session. Khi Bob có cùng subscription, Bob vẫn không nhận message.

Tên user phải ổn định và duy nhất trong phạm vi registry. Nếu nhiều tenant có thể có cùng username, cần dùng định danh toàn cục như `tenantId:userId` hoặc triển khai `DestinationUserNameProvider` để cung cấp tên destination duy nhất. Không dùng display name có thể trùng nhau làm định danh routing.

## 5. Cấu hình STOMP endpoint và broker cho test

Các test user destination cần có STOMP endpoint, application prefix, user prefix và broker prefix. Cấu hình ví dụ:

```java
import java.security.Principal;
import java.util.Map;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.server.support.DefaultHandshakeHandler;
import org.springframework.web.util.UriComponentsBuilder;

@Configuration
@EnableWebSocketMessageBroker
public class StompTestConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.setPreserveReceiveOrder(true);

        registry.addEndpoint("/ws")
                .setHandshakeHandler(new DefaultHandshakeHandler() {
                    @Override
                    protected Principal determineUser(
                            ServerHttpRequest request,
                            WebSocketHandler wsHandler,
                            Map<String, Object> attributes) {

                        String username = UriComponentsBuilder
                                .fromUri(request.getURI())
                                .build()
                                .getQueryParams()
                                .getFirst("testUser");

                        return (username != null ? () -> username : null);
                    }
                });
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/queue", "/topic");
    }
}
```

Giải thích:

- `/ws` là URL của WebSocket handshake.
- `/app` là prefix cho message được chuyển tới các phương thức `@MessageMapping`.
- `/queue` và `/topic` là các prefix do simple broker xử lý.
- `/user` là prefix được `UserDestinationMessageHandler` xử lý trước khi gửi tới broker.
- `setPreserveReceiveOrder(true)` yêu cầu Spring xử lý message đến từ cùng một WebSocket session theo thứ tự nhận được. Tính năng này có từ Spring Framework 6.1.

`determineUser` trong ví dụ đọc query parameter để gán principal khác nhau cho các client test. Đây chỉ là cách tạo danh tính giả lập cho integration test. Ứng dụng thật phải lấy principal từ quá trình xác thực HTTP handshake hoặc cơ chế xác thực STOMP đã được bảo vệ; không tin username do client tự khai báo trong query parameter.

Không đưa `/user` vào danh sách prefix của broker. Nếu broker nhận trực tiếp destination `/user/...`, `UserDestinationMessageHandler` không thể thực hiện đúng bước chuyển đổi destination logic thành destination theo session.

## 6. Tạo controller dùng trong integration test

Controller sau có ba handler: một handler gửi tới tất cả session của user, một handler gửi riêng session nguồn và một handler xác nhận subscription đã sẵn sàng.

```java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class UserDestinationTestController {

    @MessageMapping("/ready")
    @SendToUser(value = "/queue/replies", broadcast = false)
    public String ready(String value) {
        return "READY:" + value;
    }

    @MessageMapping("/broadcast")
    @SendToUser("/queue/replies")
    public String broadcast(String value, Principal principal) {
        return principal.getName() + ":" + value;
    }

    @MessageMapping("/session-only")
    @SendToUser(value = "/queue/replies", broadcast = false)
    public String sessionOnly(String value, Principal principal) {
        return principal.getName() + ":" + value;
    }
}
```

Handler `/ready` tạo một response chỉ gửi lại session hiện tại. Test sẽ subscribe trước, sau đó gửi `/app/ready`. Khi nhận được `READY:ready`, test biết subscription đã được xử lý và sẵn sàng nhận các message tiếp theo.

Barrier này hữu ích với simple broker vì simple broker không hỗ trợ STOMP receipt. `setPreserveReceiveOrder(true)` bảo đảm frame `SUBSCRIBE` và frame `SEND` tiếp theo của cùng session được xử lý theo thứ tự. Với external broker có hỗ trợ receipt, có thể dùng receipt của lệnh `SUBSCRIBE` để xác nhận broker đã xử lý subscription.

## 7. Integration test với hai người dùng và ba session

Một integration test thực tế nên mở ít nhất ba connection:

- Alice mở hai session để mô phỏng hai tab hoặc hai thiết bị.
- Bob mở một session để kiểm tra cách ly giữa các user.
- Cả ba cùng subscribe `/user/queue/replies`.

Các dependency test thường cần:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-starter-websocket")
}
```

Ví dụ dưới đây dùng `WebSocketStompClient` để kết nối vào server đang chạy ở random port. Test giả định ứng dụng test đã import `StompTestConfig` và `UserDestinationTestController`.

```java
import java.lang.reflect.Type;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.messaging.simp.user.SimpUser;
import org.springframework.messaging.simp.user.SimpUserRegistry;
import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import({StompTestConfig.class, UserDestinationTestController.class})
class UserDestinationIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    SimpUserRegistry userRegistry;

    @Autowired
    SimpMessagingTemplate messagingTemplate;

    private WebSocketStompClient stompClient;

    private final List<StompSession> sessions =
            new CopyOnWriteArrayList<>();

    @BeforeEach
    void setUp() {
        stompClient = new WebSocketStompClient(
                new StandardWebSocketClient());
        stompClient.setMessageConverter(new StringMessageConverter());
    }

    @AfterEach
    void tearDown() {
        sessions.forEach(session -> {
            if (session.isConnected()) {
                session.disconnect();
            }
        });
        stompClient.stop();
    }

    @Test
    void routesMessagesToCorrectUsersAndSessions() throws Exception {
        StompSession alice1 = connect("alice");
        StompSession alice2 = connect("alice");
        StompSession bob1 = connect("bob");

        BlockingQueue<String> alice1Messages =
                subscribeAndConfirm(alice1);
        BlockingQueue<String> alice2Messages =
                subscribeAndConfirm(alice2);
        BlockingQueue<String> bobMessages =
                subscribeAndConfirm(bob1);

        // Default broadcast: both sessions belonging to Alice receive it.
        alice1.send("/app/broadcast", "fan-out");

        assertThat(alice1Messages.poll(5, SECONDS))
                .isEqualTo("alice:fan-out");
        assertThat(alice2Messages.poll(5, SECONDS))
                .isEqualTo("alice:fan-out");
        assertNoMessage(bobMessages);

        // broadcast=false: only the session that sent the request receives it.
        alice1.send("/app/session-only", "private-reply");

        assertThat(alice1Messages.poll(5, SECONDS))
                .isEqualTo("alice:private-reply");
        assertNoMessage(alice2Messages);
        assertNoMessage(bobMessages);

        // A service can also send to all active sessions of a user.
        messagingTemplate.convertAndSendToUser(
                "alice", "/queue/replies", "service-event");

        assertThat(alice1Messages.poll(5, SECONDS))
                .isEqualTo("service-event");
        assertThat(alice2Messages.poll(5, SECONDS))
                .isEqualTo("service-event");
        assertNoMessage(bobMessages);

        // After one Alice session disconnects, only the remaining one is active.
        alice2.disconnect();

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
            SimpUser alice = userRegistry.getUser("alice");
            assertThat(alice).isNotNull();
            assertThat(alice.getSessions()).hasSize(1);
        });

        messagingTemplate.convertAndSendToUser(
                "alice", "/queue/replies", "after-disconnect");

        assertThat(alice1Messages.poll(5, SECONDS))
                .isEqualTo("after-disconnect");
        assertNoMessage(bobMessages);
    }

    private StompSession connect(String username) throws Exception {
        String url = "ws://localhost:" + port
                + "/ws?testUser=" + username;

        StompSession session = stompClient.connectAsync(
                url,
                new StompSessionHandlerAdapter() {
                }
        ).get(5, SECONDS);

        sessions.add(session);
        return session;
    }

    private BlockingQueue<String> subscribeAndConfirm(
            StompSession session) throws Exception {

        BlockingQueue<String> messages = new LinkedBlockingQueue<>();

        session.subscribe("/user/queue/replies", new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return String.class;
            }

            @Override
            public void handleFrame(StompHeaders headers, Object payload) {
                messages.add((String) payload);
            }
        });

        // Receive-order preservation ensures SUBSCRIBE is processed before SEND.
        session.send("/app/ready", "ready");

        assertThat(messages.poll(5, SECONDS))
                .isEqualTo("READY:ready");

        return messages;
    }

    private void assertNoMessage(BlockingQueue<String> messages)
            throws InterruptedException {

        assertThat(messages.poll(500, TimeUnit.MILLISECONDS)).isNull();
    }
}
```

Điểm quan trọng của test:

1. `connect("alice")` được gọi hai lần. Hai connection dùng cùng principal name `alice` nhưng có session ID riêng.
2. Bob có principal name khác nên được lưu thành user khác trong registry.
3. Cả ba session subscribe cùng destination logic. Spring tự phân giải thành các destination nội bộ riêng theo session.
4. Message gửi tới `/app/broadcast` được handler trả về bằng `@SendToUser` mặc định, nên cả hai session Alice nhận được.
5. Message gửi tới `/app/session-only` chỉ trả về session Alice đã gửi request.
6. `convertAndSendToUser` kiểm tra đường gửi từ service, không phụ thuộc vào controller.
7. Sau khi Alice-2 disconnect, registry chỉ còn một session. Thông báo gửi tiếp theo chỉ được chuyển tới Alice-1.

Barrier `/app/ready` giúp test không gửi message nghiệp vụ trước khi subscription sẵn sàng. Trong dự án có Awaitility, dùng `await().untilAsserted(...)` để chờ registry cập nhật thay vì dựa vào một khoảng chờ cố định.

## 8. Kiểm thử trực tiếp SimpUserRegistry và UserDestinationResolver

Integration test xác nhận hành vi đầu cuối. Khi cần tìm nguyên nhân lỗi ở tầng phân giải destination, có thể kiểm tra riêng `SimpUserRegistry` và `UserDestinationResolver`.

Các thông tin có thể xác minh:

- `userRegistry.getUser("alice")` trả về user Alice khi có session đang hoạt động.
- `user.getSessions()` trả về các session hiện tại của Alice.
- `session.getSubscriptions()` cho biết các subscription của session.
- `subscription.getDestination()` cho biết destination mà session đã đăng ký.
- `DefaultUserDestinationResolver.resolveDestination(...)` tạo `UserDestinationResult` chứa source destination, các target destination và session ID tương ứng.

Ví dụ dữ liệu mong đợi về mặt logic:

| Kiểm tra | Kết quả |
|---|---|
| Alice có hai session | `getSessions().size() == 2` |
| Bob có một session | `getSessions().size() == 1` |
| Gửi tới Alice | Hai target destination |
| Gửi tới Bob | Một target destination |
| Gửi tới user offline | Không có target session cục bộ |
| Alice-2 disconnect | Registry còn một session |

Khi test resolver, hãy kiểm tra số target destination và tập session ID. Không so sánh với chuỗi suffix được sinh tự động vì chi tiết đó có thể thay đổi giữa các lần chạy hoặc phiên bản framework.

Để tạo unit test resolver, chuẩn bị message có destination `/user/alice/queue/replies`, khởi tạo registry với các user/session giả lập, rồi gọi `resolveDestination`. Nếu chỉ muốn kiểm tra hành vi của controller, nên dùng `clientInboundChannel` với Spring TestContext để Spring xử lý annotation `@MessageMapping` và `@SendToUser` như lúc chạy thật.

## 9. Kiểm thử khi user có nhiều session nhưng chỉ một session đăng ký queue

Fan-out được áp dụng tới các session có subscription khớp destination. Việc một user có ba session không đồng nghĩa cả ba đều nhận mọi thông báo.

Ví dụ:

| Session | Có subscribe `/user/queue/alerts`? |
|---|---|
| alice-1 | Có |
| alice-2 | Không |
| alice-3 | Có |

Khi gửi tới Alice ở queue `alerts`, chỉ `alice-1` và `alice-3` nhận được message.

Nên có test riêng cho trường hợp này:

1. Kết nối ba session cùng principal `alice`.
2. Chỉ session 1 và session 3 subscribe `/user/queue/alerts`.
3. Gửi `convertAndSendToUser("alice", "/queue/alerts", ...)`.
4. Xác minh session 1 và session 3 nhận được message.
5. Xác minh session 2 không nhận được message.

Đây là điểm quan trọng khi ứng dụng có nhiều màn hình hoặc nhiều tab nhưng mỗi màn hình chỉ đăng ký một nhóm thông báo khác nhau.

## 10. Kiểm thử nhiều application server

Khi chạy nhiều instance Spring, mỗi instance thường chỉ biết các user session được kết nối cục bộ. Nếu Alice kết nối vào node A nhưng một service trên node B gửi thông báo cho Alice, node B cần biết session đó tồn tại trên node A.

Với STOMP broker relay và một broker dùng chung, có thể cấu hình broadcast user registry và unresolved user destination:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setUserRegistryBroadcast("/topic/simp-user-registry")
            .setUserDestinationBroadcast(
                    "/topic/unresolved-user-destination");
}
```

Hai kênh broadcast có mục đích khác nhau:

- `setUserRegistryBroadcast` phát thông tin user registry cục bộ để các node khác cập nhật nhận thức về session từ xa.
- `setUserDestinationBroadcast` chuyển những user destination chưa phân giải được ở node hiện tại để node khác có cơ hội xử lý.

Test cluster cần ít nhất hai application instance và một STOMP broker dùng chung:

1. Kết nối hai session của Alice vào node A.
2. Kết nối Bob vào node B.
3. Chờ user registry broadcast được cập nhật.
4. Gửi thông báo cho Alice từ service đang chạy trên node B.
5. Xác minh hai session Alice nhận được, Bob không nhận.
6. Ngắt một session Alice và xác minh registry từ xa được cập nhật.
7. Gửi lại thông báo để xác minh chỉ session Alice còn hoạt động nhận được.

Simple in-memory broker không phù hợp để kiểm thử cluster vì subscription và message của nó chỉ nằm trong bộ nhớ của từng application instance. Hãy dùng broker relay với broker hỗ trợ STOMP cho integration test nhiều node.

Nếu cần kiểm tra offline user hoặc message được gửi khi không có session, phải thiết kế persistence riêng. User destination tự nó không phải hàng đợi lưu trữ tin nhắn cho người dùng offline.

## 11. Các lỗi thường gặp khi kiểm thử

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Alice-1 nhận nhưng Alice-2 không nhận | Hai session có principal name khác nhau hoặc Alice-2 chưa subscribe | Kiểm tra `Principal.getName()` và registry |
| Bob nhận được thông báo của Alice | Các principal bị gán cùng tên hoặc service gửi sai username | Kiểm tra danh tính user trong handshake và tên truyền vào template |
| Không có message nào tới user | Broker xử lý `/user` trước `UserDestinationMessageHandler` hoặc cấu hình prefix sai | Kiểm tra user destination prefix và broker prefixes |
| Test đôi lúc thất bại do không nhận message | Gửi trước khi subscription được xử lý | Dùng STOMP receipt nếu broker hỗ trợ hoặc dùng barrier response với receive order |
| Phản hồi xuất hiện trên mọi tab | Dùng `@SendToUser` mặc định trong tình huống cần phản hồi riêng session | Đặt `broadcast = false` |
| Sau disconnect vẫn gửi đến session cũ | Disconnect chưa được xử lý hoặc test chưa chờ registry cập nhật | Chờ `SimpUserRegistry` phản ánh session mới |
| User không kết nối vẫn không nhận thông báo | User destination không lưu message offline | Dùng persistence/notification inbox riêng |
| Test đơn node chạy nhưng cluster thất bại | User registry chỉ chứa session cục bộ | Cấu hình user registry broadcast và broker relay |
| Nhiều tenant có cùng username bị trộn session | `Principal.getName()` không duy nhất | Dùng định danh toàn cục hoặc `DestinationUserNameProvider` |

Các lưu ý khi viết test:

1. Mỗi test nên dùng username và payload riêng để tránh nhận nhầm message từ test khác.
2. Dùng `BlockingQueue`, `CountDownLatch` hoặc Reactor `StepVerifier` để đồng bộ nhận message.
3. Không dùng `Thread.sleep` tùy tiện làm cơ chế xác nhận subscription đã sẵn sàng.
4. Luôn disconnect session và dừng client trong `@AfterEach`.
5. Test cả trường hợp một user có nhiều session và nhiều user cùng subscribe một destination logic.
6. Kiểm tra cả trường hợp session không subscribe destination đang được gửi.
7. Với broker relay, kiểm tra broker availability và cấu hình heartbeat khi test kéo dài.
8. Khi chạy hàng nghìn client giả lập, cân nhắc tắt heartbeat trong performance test nếu không đo hành vi heartbeat; mỗi client có thể tạo tác vụ heartbeat riêng.
9. Simple broker không hỗ trợ STOMP ACK và receipt. Nếu test phụ thuộc các tính năng này, hãy dùng external broker.
10. Không đưa token, cookie hoặc thông tin xác thực thật vào test log.

## 12. Checklist kiểm thử

- [ ] User destination prefix `/user` được cấu hình và xử lý bởi Spring.
- [ ] Application prefix `/app` và broker prefix `/queue`, `/topic` không bị chồng lấn.
- [ ] Mỗi user có principal name ổn định và duy nhất.
- [ ] Hai session của cùng user được registry gom về cùng một user.
- [ ] Hai user khác nhau không dùng chung session identity.
- [ ] Các session cùng subscribe một destination logic không bị trộn message.
- [ ] `@SendToUser` mặc định gửi tới các session đã subscribe của user.
- [ ] `broadcast = false` chỉ gửi tới session phát sinh request.
- [ ] `SimpMessagingTemplate.convertAndSendToUser` gửi đúng user.
- [ ] Session không subscribe destination không nhận được message.
- [ ] Disconnect cập nhật user registry.
- [ ] Test chờ subscription sẵn sàng trước khi publish.
- [ ] Cluster test dùng external broker và user registry broadcast nếu có nhiều node.
- [ ] Offline notification được xử lý bằng cơ chế persistence riêng nếu yêu cầu nghiệp vụ cần lưu.

## Tài liệu tham khảo

- [Spring Framework Reference — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework Reference — Testing STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html)
- [Spring Framework Reference — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework 6.1 API — DefaultUserDestinationResolver](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/messaging/simp/user/DefaultUserDestinationResolver.html)
- [Spring Framework 6.1 API — SimpUserRegistry](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/simp/user/SimpUserRegistry.html)
- [Spring Framework 6.1 API — SendToUser](https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/messaging/simp/annotation/SendToUser.html)
- [Spring Framework 6.1 API — WebSocketStompClient](https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html)
