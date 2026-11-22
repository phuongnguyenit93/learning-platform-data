# clientInboundChannel và ranh giới bảo vệ dữ liệu gửi ra trong Spring Security STOMP

## 1. Vấn đề: kiểm soát lệnh đầu vào chưa bảo đảm dữ liệu đầu ra an toàn

Một ứng dụng Spring Boot dùng WebSocket và STOMP để đẩy tin nhắn hoặc thông báo thời gian thực. Alice được phép xem phòng 42 thuộc tenant A; Bob chỉ được phép xem phòng 77; Carol thuộc tenant B. Cả ba người được đăng ký nhận thông báo chung ở `/topic/public`.

Hệ thống bật `@EnableWebSocketSecurity` và cấu hình `AuthorizationManager<Message<?>>` kiểm tra từng `SEND` hoặc `SUBSCRIBE` từ client. Nhưng một job định kỳ vô tình gọi:

```java
messagingTemplate.convertAndSend("/topic/public", privatePayrollReport);
```

Khi đó Alice, Bob, Carol đều có thể nhận báo cáo lương của tenant A. **Inbound authorization có thể đã chạy hoàn toàn đúng**: những client này thực sự có quyền nghe public topic. Lỗi xuất phát từ **server chọn sai nơi gửi dữ liệu**.

Tài liệu Spring Security khẳng định cơ chế bảo mật STOMP tích hợp bảo vệ **`clientInboundChannel`**, không tự áp dụng kiểm quyền cho từng frame trên **`clientOutboundChannel`**. Một inbound message có thể tạo rất nhiều outbound messages, nên framework khuyến khích bảo vệ subscription thay vì mặc định tái kiểm toàn bộ fanout.

Điều đó không có nghĩa outbound được phép thiếu bảo mật. Cần phối hợp nhiều ranh giới:

1. Client được kết nối và xác thực như thế nào?
2. Client được gửi lệnh hoặc đăng ký destination nào?
3. Server có quyền tạo event và phát nó tới destination nào?
4. Payload có phải dữ liệu của đúng tenant, resource và người nhận không?
5. Khi quyền bị thu hồi, subscriptions đang tồn tại có được hủy hoặc kiểm tra lại không?

**Nguyên tắc:** một `SUBSCRIBE` hợp lệ không cấp quyền vĩnh viễn đối với mọi nội dung server sẽ phát ra trong tương lai.

## 2. Ba channel của Spring Messaging

| Thành phần | Chiều chính | Chức năng |
| --- | --- | --- |
| `clientInboundChannel` | Client → server | Nhận STOMP `CONNECT`, `SEND`, `SUBSCRIBE`, `UNSUBSCRIBE`... |
| `brokerChannel` | Application → broker | Nhận message do `@MessageMapping`, service, HTTP controller, cron job tạo |
| `clientOutboundChannel` | Broker → client | Đưa STOMP `MESSAGE` tới các WebSocket sessions đã đăng ký |

Sơ đồ:

```text
WebSocket client
      |
      | STOMP SEND /app/chat.send
      | STOMP SUBSCRIBE /topic/rooms/42
      v
clientInboundChannel
      |
      +--> Message AuthorizationManager
      |        +--> DENY: không xử lý tiếp
      |        +--> ALLOW
      v
@MessageMapping / broker subscription
      |
      +--> Domain service, resource ACL
      +--> Chọn data, audience, DTO
      |
      v
SimpMessagingTemplate
      |
      v
brokerChannel <----- cron, HTTP, Kafka, outbox...
      |
      v
Message broker
      |
      +--> xác định các subscriptions khớp
      v
clientOutboundChannel
      |
      v
Các WebSocket clients nhận STOMP MESSAGE
```

Sơ đồ là mô hình logic; Spring Framework có các handlers khác nhau cho simple broker và STOMP broker relay. Điểm quan trọng: **`SimpMessagingTemplate` được gọi bên trong server không tự phát sinh một inbound STOMP SEND để được Spring Security kiểm lại**.

### Đừng nhầm các loại MESSAGE

Lệnh STOMP `SEND` của client thường biểu diễn thành `SimpMessageType.MESSAGE` trên inbound channel. Lệnh STOMP `MESSAGE` do broker phát về client là outbound traffic. `simpMessageDestMatchers(...)` không tự biến thành bộ lọc nội dung mọi STOMP MESSAGE server gửi ra.

## 3. Bốn thời điểm cần xác định quyền

Giả sử:

```text
10:00 Alice HTTP handshake + STOMP CONNECT thành công
10:01 Alice SUBSCRIBE room42, membership được xác minh → ALLOW
10:05 Server phát một event đúng của room42
10:10 Admin revoke Alice khỏi room42 trong database
10:11 Server phát một event mới của room42
```

Có bốn quyết định khác nhau:

- **Connection authorization:** có cho Alice mở WebSocket/STOMP session không?
- **Inbound authorization:** Alice có được yêu cầu `SUBSCRIBE` room42 tại 10:01 không?
- **Publication authorization:** event mới có đúng phòng/tenant và có thể được phát vào topic đó không?
- **Delivery/revocation:** Alice còn được nhận event lúc 10:11 không?

Nếu broker vẫn giữ subscription của Alice, event tại 10:11 **có thể** được chuyển tới Alice. Việc ACL trong database đã thay đổi không tự khiến Spring Security outbound lọc người nhận theo phiên bản ACL mới.

Vì vậy chính sách phải định nghĩa rõ quyền được kiểm tại lúc đăng ký, lúc phát, lúc giao hoặc ở nhiều thời điểm; thời hạn revoke có hiệu lực và cách xử lý race.

## 4. Cấu hình STOMP broker tối thiểu

Ví dụ Java Config với Spring MVC/Servlet và STOMP-over-WebSocket:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class MessagingConfiguration
        implements WebSocketMessageBrokerConfigurer {

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
```

Đây là **class cấu hình Spring**, không phải chương trình chạy bằng `javac` thuần. Cần Spring WebSocket/Messaging, authentication/session setup và server. Domain `example.test` là minh họa, thay bằng origin thực sự tin cậy.

Ở cấu hình này:

- `GET /ws`: HTTP handshake endpoint, không phải destination để STOMP SEND.
- `/app/**`: thông điệp gửi vào application handlers như `@MessageMapping`.
- `/topic/**`: broker broadcast destinations.
- `/queue/**`: broker queue destinations, tùy broker semantics.
- `/user/**`: Spring user destination abstraction, ánh xạ tới user/session cụ thể.

Các prefix **không tự tạo object-level ACL**. Một destination tên `/topic/tenants/a/rooms/42` không chứng minh người dùng thuộc tenant A.

## 5. Bảo vệ các lệnh đi vào

Spring Security từ 5.8 hỗ trợ WebSocket message authorization với `AuthorizationManager`. Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class MessageSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpMessageDestMatchers("/app/chat.send")
                .hasAuthority("CHAT_SEND")
            .simpSubscribeDestMatchers("/topic/public")
                .authenticated()
            .simpSubscribeDestMatchers("/user/queue/notifications")
                .authenticated()
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

Đây là **Spring component** đòi dependencies tương thích; phải cấu hình authentication, CONNECT CSRF, broker và business policy riêng.

Ý nghĩa:

1. Các frame không có destination được yêu cầu authenticated theo `nullDestMatcher`. STOMP CONNECT còn có các yêu cầu CSRF/Same Origin từ Spring Security ở cấu hình tương ứng.
2. Chỉ inbound `MESSAGE`/STOMP SEND tới `/app/chat.send` mới được phép khi có authority `CHAT_SEND`.
3. Chỉ SUBSCRIBE tới `/topic/public` hoặc `/user/queue/notifications` được mở trong ví dụ.
4. SEND thẳng tới `/topic/public`, `/topic/system` hay `/queue/private` bị catch-all từ chối.
5. Các destinations/types khác mặc định DENY.
6. Matcher được xét theo thứ tự: rule cụ thể phải đứng trước rule rộng.

Ví dụ **chưa cấp quyền subscribe private room**. Để mở `/topic/tenants/{tenant}/rooms/{room}`, cần manager riêng kiểm active tenant membership, room membership, resource state và action.

### Tại sao không dùng simpDestMatchers rộng?

Đoạn:

```java
messages.simpDestMatchers("/topic/**").authenticated();
```

có thể cấp quyền quá rộng đối với messages có destination, thay vì chỉ SUBSCRIBE. Nếu client được SEND trực tiếp tới broker prefix, kẻ tấn công có thể giả mạo thông báo mà server dự định độc quyền phát. Với private topics, chỉ kiểm `authenticated()` còn có nguy cơ BOLA/IDOR.

## 6. HTTP handshake không phải phân quyền dữ liệu gửi ra

HTTP `SecurityFilterChain` có thể xác thực Principal khi upgrade. Spring chuyển Principal từ HTTP sang WebSocket/STOMP session trong mô hình tích hợp tiêu chuẩn.

Nhưng:

- HTTP 101 nghĩa là transport đã nâng cấp thành công, không phải mọi STOMP command được phép.
- STOMP `CONNECT` là bước riêng; Spring Security còn yêu cầu CSRF token trong CONNECT theo cơ chế same-origin, tùy cấu hình.
- Một STOMP `SUBSCRIBE` được phép chỉ xác nhận quyền đăng ký tại thời điểm được xét.
- Sau upgrade, không có HTTP `SecurityFilterChain` mới cho mỗi frame MESSAGE outbound.
- Nếu dùng raw `WebSocketHandler` hoặc giao thức không phải Spring Messaging/STOMP, `@EnableWebSocketSecurity` không tự bảo vệ từng raw frame.

Hãy test từng lớp thay vì chỉ test HTTP status/CONNECTED.

## 7. Đúng subscription, sai dữ liệu: lỗ hổng từ publisher

Một public topic được đăng ký hợp lệ có thể nhận payload bí mật do publisher nhầm:

```java
messaging.convertAndSend("/topic/public", payrollEntity);
```

Điều này là leak, dù inbound SUBSCRIBE rule hoạt động chính xác.

Một publisher phải xác minh:

- Nguồn phát event là service/actor tin cậy.
- Tenant, room và resource của event đến từ nguồn tin cậy.
- Classification của payload phù hợp destination.
- Recipient/audience được phép xem loại dữ liệu đó.
- Chỉ có fields cần thiết được serialize.
- Transaction đã commit hoặc có cơ chế outbox phù hợp.
- ACL/revoke policy được đáp ứng theo contract.

### Contract phân loại dữ liệu

| Classification | Đích ví dụ | Điều kiện chính |
| --- | --- | --- |
| PUBLIC | `/topic/public` | DTO thực sự an toàn cho toàn audience public |
| TENANT_PRIVATE | `/topic/tenants/a/updates` | Event thuộc tenant A và subscriber được phép |
| ROOM_PRIVATE | `/topic/tenants/a/rooms/42` | Event thuộc đúng phòng 42; ACL room |
| USER_PRIVATE | `convertAndSendToUser(recipient,...)` | Recipient và contents đã kiểm chứng |
| UNKNOWN | Không gửi | Mặc định DENY, audit |

Không coi nhãn classification do client gửi là bằng chứng. Server phải phân loại từ resource facts và workflow đã xác minh.

### Một publisher service minh họa

```java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class RoomEventPublisher {
    private final TrustedEventRepository events;
    private final PublishPolicy policy;
    private final SimpMessagingTemplate messaging;

    public RoomEventPublisher(
            TrustedEventRepository events,
            PublishPolicy policy,
            SimpMessagingTemplate messaging) {
        this.events = events;
        this.policy = policy;
        this.messaging = messaging;
    }

    public void publish(VerifiedServiceActor actor, long eventId) {
        RoomEvent event = events.findRequired(eventId);
        policy.requireCanPublish(actor, event);

        String destination = "/topic/tenants/" + event.tenantId()
            + "/rooms/" + event.roomId();

        RoomEventDto safeDto = new RoomEventDto(
            event.publicId(),
            event.displayText(),
            event.createdAt()
        );

        messaging.convertAndSend(destination, safeDto);
    }
}
```

Đây là **component fragment**, không chạy độc lập: `TrustedEventRepository`, `PublishPolicy`, `VerifiedServiceActor`, `RoomEvent`, `RoomEventDto` là types do ứng dụng triển khai. `event.tenantId()`/`roomId()` phải lấy từ resource thật được verify, không tin header/body do client tự đặt.

Sai lầm cần tránh:

```java
messaging.convertAndSend(request.destination(), request.payload());
```

Ở đây client có thể điều hướng nội dung tới topic nhạy cảm hoặc topic của người khác. Thay bằng destination do server tự xác định từ facts đáng tin.

## 8. Dữ liệu gửi ra phải đúng recipient và đúng field

Hai lỗi khác nhau:

1. **Routing sai:** Bob không thuộc room42 nhưng broker cho Bob subscribe room42.
2. **Content sai:** Alice thuộc room42 hợp lệ nhưng publisher đưa vào topic đó một record của Bob/tenant B.

Bảo vệ thứ nhất bằng subscription ACL/broker isolation. Bảo vệ thứ hai bằng domain/publisher policy, DTO projection và source query phù hợp.

Một entity có thể chứa:

```text
id, tenantId, ownerId, title, description,
privateNotes, accessToken, internalFlag, salary
```

Ngay cả khi frontend không hiển thị `privateNotes`, serializer có thể gửi field này nếu server truyền nguyên entity. Dùng DTO nhỏ chỉ gồm thuộc tính được phép.

Với field-level access khác nhau giữa subscribers, cân nhắc **per-user fanout** hoặc push tối thiểu ID rồi bắt client gọi REST detail API có object-level authorization.

## 9. User destinations không tự giải quyết quyền trên payload

Client:

```text
SUBSCRIBE
id:personal
destination:/user/queue/notifications
```

Server:

```java
messagingTemplate.convertAndSendToUser(
    verifiedRecipientName,
    "/queue/notifications",
    safeNotification);
```

Spring Framework dịch user destination sang queue theo user/session. Với một user có nhiều sessions, thông điệp gửi theo username có thể đến nhiều phiên; `@SendToUser(broadcast = false)` có thể dùng khi muốn một phiên cụ thể trong xử lý message handler.

Các rủi ro:

- Gửi dữ liệu private của Bob vào queue Alice.
- Dùng username trùng giữa tenants/IdPs khi hệ thống cần stable subject.
- Client subscribe trực tiếp raw `/queue/**` thay vì `/user/queue/**`.
- Một session có scope tenant khác nhưng cùng username nhận event không phù hợp.
- Queue của broker giữ messages sau logout/revoke.
- Multi-node user destination chưa đồng bộ hoặc đích không resolve.

**Routing đến đúng user queue không chứng minh dữ liệu thuộc user đó.** Policy phải kiểm recipient–resource–action.

## 10. Thu hồi quyền sau khi subscription đã tồn tại

Ví dụ:

```text
10:00 Alice SUBSCRIBE room42: ALLOW
10:05 Broker có active subscription Alice-room42
10:10 Admin revoke Alice membership
10:11 Server publish event room42
```

Spring Security không tự lặp lại inbound authorization trên mỗi outgoing frame. Nếu subscription chưa bị xóa, Alice có thể vẫn nhận message.

Các chiến lược:

| Chiến lược | Cách hoạt động | Điểm cần kiểm |
| --- | --- | --- |
| Disconnect/unsubscribe | Chủ động hủy session/subscription bị revoke | User-session map và đồng bộ đa node |
| Subscription lease | Giới hạn TTL, bắt renew grant | Staleness trong cửa sổ TTL |
| Grant/policy epoch | Khi ACL đổi, invalidate subscriptions cũ | Version propagation nhất quán |
| Publish-time recipient check | Chỉ chọn users còn grant | Load/p99 latency và TOCTOU |
| Per-user fanout | Gửi riêng theo recipient list từ trusted ACL | Nhiều messages, chi phí cao |
| Minimal push + fetch | Chỉ gửi ID, detail GET kiểm lại | Metadata vẫn cần bảo mật |

JWT hết hạn **không tự động** làm WebSocket đang mở bị đóng nếu app không có cơ chế session expiry/re-authentication. Muốn revoke có hiệu lực trong khoảng thời gian cụ thể, phải thiết kế và kiểm thử SLA đó.

### Race TOCTOU

Có thể xảy ra:

```text
T1 publisher: check Alice grant = true
T2 admin: revoke Alice grant
T1 broker: deliver message
```

Không có phép kiểm đơn lẻ nào tự đảm bảo atomicity giữa database, application nodes, broker và socket. Cần contract về thời điểm xét quyền, ordering/epoch hoặc độ trễ cho phép.

## 11. Nguồn phát khác clientInboundChannel

Những code path có thể phát messages mà không đi qua một inbound STOMP SEND mới:

- HTTP controller xử lý POST.
- Scheduled job.
- Kafka/RabbitMQ consumer.
- Transactional outbox relay.
- Application event listener.
- Database change stream.
- Admin tool hoặc internal service.
- External STOMP broker publisher.

Vì vậy nếu chỉ đặt quyền tại `@MessageMapping`, một cron job vẫn có thể bypass. Đặt chính sách publication trong **một domain/publisher service dùng chung** hoặc trust boundary tương đương.

### Background jobs không tự có HTTP Principal

Đừng lấy `SecurityContextHolder.getContext()` trong worker thread rồi mặc định đó là user đã yêu cầu công việc. Phải phân biệt **verified service actor**, **initiating user** (nếu đã chứng minh) và **resource tenant/owner**. `initiatedBy=alice` trong event body tự nó không tạo delegated user permission.

### Transaction và outbox

Một publisher gửi event trước khi DB commit có thể thông báo dữ liệu chưa tồn tại nếu transaction rollback. Dùng transactional outbox, after-commit hoặc workflow idempotent tùy kiến trúc. Không dựa vào hậu kiểm sau khi publish để thu hồi message đã gửi.

## 12. External broker relay và các đường bypass

Khi dùng RabbitMQ/ActiveMQ hoặc STOMP relay:

```text
Client -> Spring clientInboundChannel -> Spring message security
       -> Broker relay -> External broker
       -> Spring clientOutboundChannel -> Client
```

Nếu broker có public/direct connection, client hoặc một integration khác có thể subscribe/publish **không qua Spring inbound security**. Phải bảo vệ tại broker/network:

- TLS và broker authentication.
- Destination ACL.
- Service credentials theo least privilege.
- Không mở management/queue endpoints trái phép.
- Retention, durable subscriptions và replay policy.
- Network isolation và rate limits.
- Multi-node user destinations và revoke propagation.

Không mặc định external broker biết domain ACL owner/tenant của ứng dụng.

## 13. Custom outbound interceptor có phải giải pháp mặc định?

Spring Messaging có `ChannelInterceptor` và có thể tùy biến outbound processing. Nhưng **Spring Security WebSocket message authorization tiêu chuẩn không tự cung cấp general authorization manager cho mỗi outgoing message**.

Nếu tự viết outbound checker, cần giải quyết:

- Làm sao lấy đúng user/session/resource context?
- Một incoming event có thể nhân ra 10.000 outgoing deliveries; có query 10.000 lần?
- Queues, thread pools và slow clients chịu được không?
- Event đã được publish vào broker/buffer trước checker chưa?
- Interceptor có chạy trên mọi đường/relay/node không?
- Nếu bytes đã rời server thì không thể thu hồi.

Thiết kế có thể dùng outbound interception như defense in depth, nhưng **không mở inbound subscriptions hoặc publishers rộng hơn chỉ vì hy vọng interceptor sẽ cứu**.

## 14. Thứ tự, buffer và revoke

Theo Spring Framework, inbound/outbound channels dùng executors; các messages có thể được xử lý/nhận khác thứ tự publish trong một số cấu hình. Có `setPreserveReceiveOrder(true)` và `setPreservePublishOrder(true)` khi yêu cầu bảo toàn thứ tự trong session, đổi lại một số chi phí hiệu năng.

Các flags này **không phải authorization primitive**. Chúng không tự đồng bộ:

```text
DB revoke -> Kafka event -> node A -> node B -> broker queues -> clients
```

Nếu tenant A revoke một subscription trên node A, node B có thể tiếp tục publish event trước khi nhận thông báo. Cần cơ chế quản lý permission consistency, revoke epoch, queue purge hoặc SLA phù hợp.

Các slow consumers có thể giữ buffered private messages lâu hơn dự kiến; test latency, send time limits, message size, subscription counts và broker retention.

## 15. Java 17 độc lập: chứng minh sự khác nhau giữa cấp quyền subscribe và giao dữ liệu

Ví dụ dùng Java 17 thuần, không cần Spring/JWT/broker. Nó giả lập quyền SUBSCRIBE, SEND, nguồn publisher và quyết định giao khi ACL bị revoke.

Tạo file `InboundOutboundBoundaryDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class InboundOutboundBoundaryDemo {
    static final String PUBLIC = "/topic/public";
    static final String ROOM_A = "/topic/tenants/a/rooms/42";
    static final String ROOM_B = "/topic/tenants/a/rooms/77";

    record User(String id, boolean authenticated) {}
    record Subscription(String userId, String destination) {}
    enum Visibility { PUBLIC, ROOM }

    static boolean maySubscribe(
            User user, String destination, Set<String> grants) {
        if (user == null || !user.authenticated()) {
            return false;
        }
        return PUBLIC.equals(destination)
            || grants.contains(user.id() + "|" + destination);
    }

    static boolean maySend(User user, String destination) {
        return user != null && user.authenticated()
            && "/app/chat.send".equals(destination);
    }

    static boolean mayPublish(
            Visibility classification, String destination,
            String expectedRoom) {
        return switch (classification) {
            case PUBLIC -> PUBLIC.equals(destination);
            case ROOM -> expectedRoom != null
                && expectedRoom.equals(destination)
                && destination.startsWith("/topic/tenants/");
        };
    }

    static void subscribe(
            List<Subscription> active,
            User user, String destination, Set<String> grants) {
        if (maySubscribe(user, destination, grants)) {
            active.add(new Subscription(user.id(), destination));
        }
    }

    static List<String> recipients(
            List<Subscription> subscriptions,
            String destination, Set<String> grants,
            boolean checkCurrentGrants) {
        return subscriptions.stream()
            .filter(s -> s.destination().equals(destination))
            .filter(s -> !checkCurrentGrants
                || PUBLIC.equals(destination)
                || grants.contains(s.userId() + "|" + destination))
            .map(Subscription::userId)
            .distinct()
            .sorted()
            .toList();
    }

    static String label(boolean allowed) {
        return allowed ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        User alice = new User("alice", true);
        User bob = new User("bob", true);
        User carol = new User("carol", true);
        User guest = new User("guest", false);

        Set<String> grants = new HashSet<>();
        grants.add("alice|" + ROOM_A);
        grants.add("bob|" + ROOM_B);

        System.out.println("Alice room A SUBSCRIBE: "
            + label(maySubscribe(alice, ROOM_A, grants)));
        System.out.println("Bob room A SUBSCRIBE: "
            + label(maySubscribe(bob, ROOM_A, grants)));
        System.out.println("Guest public SUBSCRIBE: "
            + label(maySubscribe(guest, PUBLIC, grants)));
        System.out.println("Alice broker SEND: "
            + label(maySend(alice, PUBLIC)));
        System.out.println("Alice app SEND: "
            + label(maySend(alice, "/app/chat.send")));

        List<Subscription> active = new ArrayList<>();
        subscribe(active, alice, PUBLIC, grants);
        subscribe(active, bob, PUBLIC, grants);
        subscribe(active, carol, PUBLIC, grants);
        subscribe(active, alice, ROOM_A, grants);
        subscribe(active, bob, ROOM_B, grants);

        System.out.println("Public recipients: "
            + recipients(active, PUBLIC, grants, false));
        System.out.println("Room A recipients: "
            + recipients(active, ROOM_A, grants, false));
        System.out.println("Private event on public topic: "
            + label(mayPublish(Visibility.ROOM, PUBLIC, ROOM_A)));

        grants.remove("alice|" + ROOM_A);

        System.out.println("Old subscription after revoke: "
            + recipients(active, ROOM_A, grants, false));
        System.out.println("Rechecked delivery after revoke: "
            + recipients(active, ROOM_A, grants, true));
        System.out.println("Room publisher destination: "
            + label(mayPublish(Visibility.ROOM, ROOM_A, ROOM_A)));
        System.out.println("Public publisher destination: "
            + label(mayPublish(Visibility.PUBLIC, PUBLIC, null)));
    }
}
```

Biên dịch, chạy:

```bash
javac InboundOutboundBoundaryDemo.java
java InboundOutboundBoundaryDemo
```

Stdout chính xác:

```text
Alice room A SUBSCRIBE: ALLOW
Bob room A SUBSCRIBE: DENY
Guest public SUBSCRIBE: DENY
Alice broker SEND: DENY
Alice app SEND: ALLOW
Public recipients: [alice, bob, carol]
Room A recipients: [alice]
Private event on public topic: DENY
Old subscription after revoke: [alice]
Rechecked delivery after revoke: []
Room publisher destination: ALLOW
Public publisher destination: ALLOW
```

Giải thích:

- Alice có room grant, Bob chỉ có grant của room B.
- Gửi trực tiếp tới broker prefix bị từ chối, dù Alice có thể gửi application command.
- Tất cả authenticated users được nhận public events.
- Event riêng của room không được publish vào public destination.
- Revoke chỉ thay nguồn ACL, không tự xóa subscriptions đã đăng ký; nếu không recheck, Alice vẫn nằm trong tập recipient.
- Kiểm current grants lúc delivery giúp loại Alice, hoặc ứng dụng có thể ngắt session/hủy subscription.
- Mã là mô phỏng in-memory, **không** thực thi Spring MessageChannels, STOMP frames, JWT, CSRF, R2DBC hay external broker. Trong production phải xác minh event source, DTO fields, user/tenant/resource, timeout và consistency.

## 16. Kiểm thử inbound đúng hướng

Dùng Spring Messaging tạo fixture:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;

SimpMessageHeaderAccessor headers =
    SimpMessageHeaderAccessor.create(SimpMessageType.SUBSCRIBE);
headers.setDestination("/topic/public");
headers.setLeaveMutable(true);

Message<byte[]> subscribe = MessageBuilder.createMessage(
    new byte[0], headers.getMessageHeaders());
```

Đây là JUnit fragment; cần manager và `Authentication` fixture. Tùy version, gọi `authorizationManager.authorize(() -> auth, subscribe)` rồi kiểm kết quả `isGranted()`.

| Inbound message | Kỳ vọng |
| --- | --- |
| SEND `/app/chat.send`, có CHAT_SEND | ALLOW |
| SEND `/topic/public` | DENY |
| SEND `/topic/system` | DENY |
| SUBSCRIBE `/topic/public`, authenticated | ALLOW |
| SUBSCRIBE private room, active membership | ALLOW theo custom policy |
| SUBSCRIBE private room, wrong tenant | DENY |
| SUBSCRIBE raw `/queue/other-session` | DENY |
| SUBSCRIBE destination lạ | DENY |
| CONNECT thiếu/CSRF sai trong policy bắt buộc | Không cho business messaging |

Các tests này chỉ chứng minh **inbound manager**, không kiểm nội dung mà server gửi ra.

## 17. Kiểm thử outbound: người không có quyền không được nhận event

Một integration test WebSocket/STOMP nên chạy server thật hoặc Spring channels/broker test harness với Alice/Bob/Carol, hai tenants và nhiều rooms. Cần kiểm:

1. Bob không nhận event room42 ngay cả khi cố SUBSCRIBE.
2. Event classification ROOM_PRIVATE không được publish vào `/topic/public`; `convertAndSend` không được gọi.
3. Alice nhận đúng safe DTO, không có privateNotes/token/salary ngoài phạm vi.
4. App không gửi dữ liệu Bob vào user queue Alice.
5. Sau revoke, Alice đang giữ socket không nhận event mới theo SLA, và subscribe lại phải DENY.
6. Các producers từ cron, HTTP, Kafka/outbox vẫn chịu cùng publisher policy.
7. External broker không cho direct subscribe/publish vượt Spring.
8. Broker replay, multi-node và reconnect không gửi lại data trái quyền.
9. Transaction rollback không có event thể hiện state đã commit.
10. Slow-client/outbound buffers được giới hạn và không phá tenant isolation.

### Test publisher độc lập

```text
Given:
  event.kind = ROOM_PRIVATE
  event.tenant = tenant-a
  event.room = room42
  destination proposed = /topic/public
When:
  publisher.publish(event)
Then:
  DENY
  SimpMessagingTemplate.convertAndSend not called
  audit.reason = DESTINATION_CLASSIFICATION_MISMATCH
```

Không chỉ assert HTTP 101 hay STOMP CONNECTED. Sau Upgrade, một lỗi STOMP có thể thành ERROR frame/connection close; phải kiểm **recipient, exact payload, absence của message nhạy cảm và side effects**.

## 18. Quan sát, hiệu năng và dữ liệu riêng tư

Các chỉ số phù hợp:

- Inbound ALLOW/DENY theo message type và destination template.
- Active subscriptions theo tenant/room/user (với cardinality an toàn).
- Số publish bị chặn do classification/tenant/recipient mismatch.
- Revocation propagation latency.
- Outbound queue depth, slow consumers, broker latency.
- Số unintended delivery trong các security tests.
- Permission DB/PDP timeout và invalidation errors.

Giới hạn connections, subscriptions, frame size, SEND rate, memory và broker retention. Nếu một event phát tới 10.000 subscribers, việc query ACL riêng cho từng delivery có thể cực kỳ tốn; cân nhắc subscriptions leases, indexed/batched grants hoặc per-user fanout có giới hạn.

Log audit nên chứa event ID, caller kind, verified tenant, resource type, policy version, destination template, decision và reason; không ghi raw JWT, STOMP CSRF, private payload hay cookies.

## 19. Lỗi thường gặp

| Lỗi | Hậu quả | Sửa |
| --- | --- | --- |
| Coi inbound manager bảo vệ outbound | Data leak dù subscription đúng | Publisher/data/audience policy |
| Chỉ bảo vệ HTTP handshake | SEND/SUBSCRIBE thiếu guard | STOMP AuthorizationManager |
| Cho SEND thẳng broker topic | Giả mạo server | Deny broker-prefix SEND |
| Cho SUBSCRIBE mọi room bằng authenticated | Cross-room/tenant BOLA | Room membership ACL |
| Tin destination/senderId từ payload | Arbitrary routing/identity spoof | Verified Principal và resource facts |
| Publish raw entity | Sensitive field leakage | Safe DTO |
| Tin user queue tự bảo vệ payload | Recipient mismatch | User/resource/payload policy |
| Revoke nhưng giữ subscriptions cũ | Stale delivery | Disconnect/invalidate/recheck |
| Tin JWT expiry tự đóng socket | Old session còn sống | Session lifetime strategy |
| Broker relay có direct client access | Bypass Spring inbound | Broker ACL/network |
| Job nền gọi broker ngoài policy | Bypass domain authorization | Shared publisher service |
| Event phát trước transaction commit | Incorrect state/event | Outbox/after-commit |
| Replay event private sau revoke | Historical data leak | Replay authorization |
| Test chỉ HTTP status/CONNECTED | Không thấy outbound leak | Assert absent recipients/message |
| Query ACL không giới hạn ở mỗi outbound | Fanout quá tải | Batch/lease/index/limits |

## 20. Checklist trước production

- [ ] Phân biệt `clientInboundChannel`, `brokerChannel`, `clientOutboundChannel`.
- [ ] Có authentication, Origin/CSRF policy cho handshake/CONNECT.
- [ ] Inbound message manager phân biệt SEND và SUBSCRIBE, default DENY.
- [ ] Deny client SEND tới `/topic/**` và raw `/queue/**`.
- [ ] SUBSCRIBE private theo verified tenant/room/object ACL.
- [ ] Publisher xác minh nguồn event, classification, audience, destination.
- [ ] Không tin `senderId`, `recipientId`, `tenantId`, `destination` chưa xác minh.
- [ ] Chỉ gửi DTO đúng trường được phép; không publish raw entity.
- [ ] Có user-specific routing và kiểm đúng nội dung cho recipient.
- [ ] Background jobs, HTTP handlers, Kafka/outbox dùng cùng domain policy.
- [ ] Có revoke plan với subscriptions đang sống và multi-node.
- [ ] External broker có TLS/authentication/destination ACL.
- [ ] Có test stale sessions, broker replay, wrong audience, wrong tenant.
- [ ] Negative tests chứng minh client trái quyền **không nhận message**.
- [ ] Log/metrics không chứa credential hay private payload.

**Kết luận:** `clientInboundChannel` là điểm Spring Security kiểm **lệnh STOMP từ client**, trong khi `clientOutboundChannel` là đường broker/server gửi **dữ liệu** cho client mà message authorization tiêu chuẩn không tự kiểm từng frame. Vì vậy phải bảo vệ **cả quyền SUBSCRIBE lẫn nguồn phát, destination, payload, recipient, revocation và broker trust boundary**. Một kết nối hoặc subscription hợp lệ không tự cho phép mọi dữ liệu được phát về sau.

## Tài liệu tham khảo chính thức

- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): inbound-only enforcement, SEND vs SUBSCRIBE, user destinations, CSRF.
- [Spring Security API — MessageMatcherDelegatingAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.html): API message authorization.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): ba channel và message routing.
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): per-user/per-session và multi-node.
- [Spring Framework — Ordered Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html): message ordering và executor.
- [Spring Framework — Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): external broker boundary.
- [Spring Framework — Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html): resource limits.
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): message authorization, lifecycle và privacy.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege và deny-by-default.
