# SimpMessageSendingOperations và SimpMessagingTemplate

## Mục tiêu

Trong Spring Messaging, `SimpMessageSendingOperations` và `SimpMessagingTemplate` cung cấp API để gửi message tới một destination trong hệ thống messaging. Khi ứng dụng dùng STOMP qua WebSocket, hai thành phần này thường được dùng để gửi dữ liệu từ service, event listener hoặc controller tới các client đang kết nối.

Bài này tập trung vào trường hợp gửi message riêng cho một người dùng: cách chọn interface hay implementation, cách định tuyến bằng user destination, cấu hình broker, truyền header và xử lý các lỗi thường gặp.

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa `SimpMessageSendingOperations` và `SimpMessagingTemplate`.
- Gửi message tới destination chung bằng `convertAndSend`.
- Gửi message tới một người dùng bằng `convertAndSendToUser`.
- Cấu hình và sử dụng destination dạng `/user/queue/...` trong STOMP.
- Chọn đúng user identity, truyền header và kiểm tra lỗi gửi message.

## 1. Bối cảnh: message, channel và destination

Spring Messaging mô hình hóa dữ liệu được gửi trong ứng dụng bằng `Message<T>`. Một message gồm payload và headers:

- **Payload** là dữ liệu nghiệp vụ, ví dụ một `Notification`, `OrderStatus` hoặc chuỗi văn bản.
- **Headers** chứa metadata như destination, content type, session ID và các native header của giao thức.
- **MessageChannel** là kênh để chuyển message giữa các thành phần trong hệ thống.
- **MessageConverter** chuyển đổi object Java thành dạng dữ liệu mà giao thức hoặc client có thể nhận, thường là JSON khi ứng dụng đã cấu hình Jackson.

Trong STOMP over WebSocket, destination là tên đích logic mà client đăng ký nhận hoặc server gửi tới. Một số destination thường gặp:

| Destination | Mục đích thường dùng |
| --- | --- |
| `/topic/...` | Nhóm subscriber nhận cùng một luồng message, thường dùng cho broadcast |
| `/queue/...` | Luồng message dạng queue hoặc điểm nhận cụ thể, tùy broker |
| `/user/queue/...` | Destination logic dành cho user đang đăng nhập |
| `/app/...` | Prefix cho message client gửi vào các method `@MessageMapping` |

Destination chỉ là địa chỉ định tuyến. Nó không tự xác thực người gửi, không tự cấp quyền truy cập và cũng không đảm bảo client đã đọc message.

## 2. `SimpMessageSendingOperations` là gì?

`SimpMessageSendingOperations` thuộc package:

```java
org.springframework.messaging.simp.SimpMessageSendingOperations
```

Đây là **interface** chuyên biệt hóa `MessageSendingOperations<String>` cho mô hình messaging đơn giản của Spring, bao gồm hỗ trợ STOMP. Tham số generic `String` thể hiện destination được biểu diễn bằng chuỗi.

Interface này kế thừa các thao tác gửi chung như:

- `convertAndSend(destination, payload)`: chuyển object payload thành message rồi gửi tới destination.
- Các overload của `convertAndSend` nhận thêm headers hoặc `MessagePostProcessor`.
- `send(message)`: gửi một `Message<?>` đã được tạo sẵn, thường cần có destination header.

Điểm riêng quan trọng của `SimpMessageSendingOperations` là nhóm overload `convertAndSendToUser(...)`. Nhóm method này cho phép gửi message tới một user thông qua cơ chế user destination của Spring.

### Các overload `convertAndSendToUser`

Các overload chính gồm:

```java
void convertAndSendToUser(
        String user, String destination, Object payload);

void convertAndSendToUser(
        String user, String destination, Object payload,
        Map<String, Object> headers);

void convertAndSendToUser(
        String user, String destination, Object payload,
        MessagePostProcessor postProcessor);

void convertAndSendToUser(
        String user, String destination, Object payload,
        Map<String, Object> headers,
        MessagePostProcessor postProcessor);
```

Ý nghĩa tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `user` | Tên user mà Spring dùng để tìm các WebSocket session tương ứng |
| `destination` | Destination đích bên trong user destination, ví dụ `/queue/notifications` |
| `payload` | Object cần gửi; có thể được chuyển đổi bởi message converter |
| `headers` | Metadata bổ sung cho message |
| `postProcessor` | Callback để chỉnh sửa message sau khi được tạo và trước khi gửi |

`user` phải khớp với identity mà Spring gắn vào WebSocket session. Với ứng dụng xác thực thông thường, giá trị đó thường là `Principal.getName()`.

Ví dụ gọi API:

```java
messagingOperations.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        notification
);
```

Với user `alice`, Spring xử lý destination theo user destination prefix đã cấu hình, mặc định là `/user/`. Client của Alice đăng ký:

```javascript
stompClient.subscribe("/user/queue/notifications", (frame) => {
    const notification = JSON.parse(frame.body);
    console.log(notification);
});
```

Phía server truyền destination `/queue/notifications` vào `convertAndSendToUser`. Client đăng ký `/user/queue/notifications`. Không tự ghép `/user/alice` vào tham số `destination` khi gọi method này; phần user prefix và user name được template xử lý.

## 3. `SimpMessagingTemplate` là gì?

`SimpMessagingTemplate` là **implementation** của `SimpMessageSendingOperations`. Class này thuộc package:

```java
org.springframework.messaging.simp.SimpMessagingTemplate
```

Template đóng vai trò facade để gửi message vào message channel mà Spring STOMP cấu hình cho broker. Nó kế thừa cơ chế chuyển đổi payload và gửi message từ `AbstractMessageSendingTemplate<String>`, đồng thời triển khai các thao tác đặc thù của simple messaging protocol.

Một số đặc điểm cần nhớ:

- Constructor nhận một `MessageChannel`.
- User destination prefix mặc định là `/user/`.
- Có thể cấu hình send timeout bằng `setSendTimeout(long)`.
- Có thể cấu hình `MessageHeaderInitializer` để khởi tạo headers cho message được tạo qua template.
- Có `convertAndSend`, `convertAndSendToUser` và `send`.

Trong ứng dụng Spring có bật STOMP message broker, Spring tạo và quản lý template tương ứng. Bean thường có tên `brokerMessagingTemplate`. Thông thường nên inject bean qua Spring thay vì tự tạo `new SimpMessagingTemplate(...)`, bởi template cần đúng message channel do messaging configuration quản lý.

### Nên inject interface hay class?

Trong service nghiệp vụ, ưu tiên inject `SimpMessageSendingOperations`:

```java
@Service
public class NotificationSender {

    private final SimpMessageSendingOperations messaging;

    public NotificationSender(
            SimpMessageSendingOperations messaging) {
        this.messaging = messaging;
    }
}
```

Cách này giúp service phụ thuộc vào hợp đồng gửi message. Khi cần cấu hình riêng chỉ có trên `SimpMessagingTemplate`, hoặc cần gọi API đặc thù của implementation, có thể inject trực tiếp `SimpMessagingTemplate`.

Nếu trong ApplicationContext có nhiều bean cùng implement interface, hãy dùng `@Qualifier` để chỉ rõ bean. Với cấu hình STOMP tiêu chuẩn, tên bean do Spring tạo thường là `brokerMessagingTemplate`.

## 4. Cấu hình STOMP user destination

Để `convertAndSendToUser` hoạt động, ứng dụng phải bật STOMP message broker và cấu hình destination prefix phù hợp.

Ví dụ cấu hình Java:

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {

        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
```

Các cấu hình có vai trò khác nhau:

- `registerStompEndpoints`: đăng ký endpoint HTTP/WebSocket để client bắt đầu kết nối, ở đây là `/ws`.
- `setApplicationDestinationPrefixes("/app")`: xác định prefix cho message từ client đi vào các handler `@MessageMapping`.
- `enableSimpleBroker("/topic", "/queue")`: bật simple broker để xử lý các destination được khai báo.
- `setUserDestinationPrefix("/user")`: khai báo prefix mà `UserDestinationMessageHandler` dùng để nhận diện user destination.

Trong ví dụ này, client có thể gửi message vào `/app/...`, đăng ký nhận broadcast ở `/topic/...`, hoặc đăng ký destination riêng ở `/user/queue/...`.

Simple broker phù hợp cho ứng dụng và tải phù hợp với khả năng của nó. Khi cần broker độc lập hoặc khả năng mở rộng theo hạ tầng, có thể cấu hình STOMP broker relay. Cơ chế user destination vẫn cần được định tuyến đúng trong cả hai trường hợp.

## 5. Luồng gửi message tới một user

Giả sử Alice đã đăng nhập và WebSocket handshake tạo một `Principal` có `getName()` trả về `"alice"`.

Luồng gửi message có thể hình dung như sau:

1. Client của Alice kết nối tới endpoint `/ws`.
2. Client đăng ký `/user/queue/notifications`.
3. Một service trong ứng dụng cần gửi thông báo cho Alice.
4. Service gọi `convertAndSendToUser("alice", "/queue/notifications", payload)`.
5. `SimpMessagingTemplate` tạo message và gửi vào broker channel.
6. `UserDestinationMessageHandler` phân giải user destination thành destination thực tế gắn với session của Alice.
7. Broker chuyển message tới các session đang đăng ký destination tương ứng.

`/user/queue/notifications` là destination logic. Spring phân giải nó thành destination riêng cho session để hai người dùng có thể cùng đăng ký `/user/queue/notifications` mà không nhận nhầm message của nhau.

Nếu một user có nhiều WebSocket session, mặc định user destination hướng tới các session tương ứng của user đó. Đây là điểm khác với việc gửi tới một session ID duy nhất.

## 6. Ví dụ sử dụng từ service

### DTO

Dùng một record Java 17 để biểu diễn notification:

```java
import java.time.Instant;

public record Notification(
        String id,
        String message,
        Instant createdAt
) {
}
```

### Service gửi notification

```java
import org.springframework.messaging.simp.SimpMessageSendingOperations;
import org.springframework.stereotype.Service;

@Service
public class NotificationSender {

    private final SimpMessageSendingOperations messaging;

    public NotificationSender(
            SimpMessageSendingOperations messaging) {
        this.messaging = messaging;
    }

    public void sendToUser(
            String username,
            Notification notification) {

        messaging.convertAndSendToUser(
                username,
                "/queue/notifications",
                notification
        );
    }
}
```

Khi service khác cần thông báo cho user:

```java
notificationSender.sendToUser(
        "alice",
        new Notification(
                "notice-1001",
                "Đơn hàng của bạn đã được xác nhận.",
                Instant.now()
        )
);
```

Nếu ứng dụng đang xử lý một request hoặc message có `Principal`, hãy lấy user từ security context hoặc từ `Principal` đã được Spring cung cấp. Ví dụ trong một method `@MessageMapping`:

```java
@MessageMapping("/orders")
public void handleOrder(
        OrderRequest request,
        Principal principal) {

    // Xử lý nghiệp vụ và tạo notification.
    Notification notification = new Notification(
            "order-confirmed",
            "Đơn hàng đã được xác nhận.",
            Instant.now()
    );

    notificationSender.sendToUser(
            principal.getName(),
            notification
    );
}
```

Ví dụ trên minh họa cách lấy user từ kết nối đã xác thực. Trong ứng dụng thực tế, cần xử lý trường hợp `principal` không tồn tại theo chính sách xác thực của ứng dụng.

## 7. Gửi tới destination chung và gửi tới user

Dùng `convertAndSend` khi tất cả client đăng ký cùng destination cần nhận message:

```java
messaging.convertAndSend(
        "/topic/system-announcements",
        announcement
);
```

Dùng `convertAndSendToUser` khi message chỉ dành cho user đích:

```java
messaging.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        notification
);
```

So sánh:

| Tiêu chí | `convertAndSend` | `convertAndSendToUser` |
| --- | --- | --- |
| Địa chỉ | Destination thông thường | User và destination |
| Mục đích | Broadcast hoặc gửi tới nhóm subscriber | Gửi riêng theo user identity |
| Ví dụ server | `/topic/news` | User `alice`, `/queue/notifications` |
| Ví dụ client subscribe | `/topic/news` | `/user/queue/notifications` |
| Cơ chế phân giải user | Không | Có, qua user destination handler |

Không nên gửi dữ liệu riêng tư tới `/topic/...` nếu nhiều client có thể đăng ký destination đó.

## 8. Truyền headers và xử lý message trước khi gửi

Các overload nhận `headers` hữu ích khi cần bổ sung metadata cho message. Ví dụ, có thể đặt content type hoặc native STOMP header.

Nên dùng `SimpMessageHeaderAccessor` khi muốn tạo Spring messaging headers rõ ràng:

```java
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.util.MimeTypeUtils;

SimpMessageHeaderAccessor accessor =
        SimpMessageHeaderAccessor.create();

accessor.setContentType(MimeTypeUtils.APPLICATION_JSON);
accessor.setNativeHeader("trace-id", traceId);
accessor.setLeaveMutable(true);

MessageHeaders headers = accessor.getMessageHeaders();

messaging.convertAndSendToUser(
        username,
        "/queue/notifications",
        notification,
        headers
);
```

Lưu ý về header:

- Với một `Map<String, Object>` thông thường, `SimpMessagingTemplate` mặc định diễn giải các giá trị như native headers và đặt chúng dưới key `nativeHeaders`.
- Nếu map đã có key `nativeHeaders`, hoặc headers được tạo bằng `SimpMessageHeaderAccessor`, template sử dụng headers theo cấu trúc đó.
- `setContentType` đặt content type ở cấp Spring message; `setNativeHeader` đặt native header của giao thức.
- Message converter cần hỗ trợ kiểu payload và content type được sử dụng.

Có thể dùng `MessagePostProcessor` để chỉnh sửa message sau khi template tạo message nhưng trước khi gửi:

```java
messaging.convertAndSendToUser(
        username,
        "/queue/notifications",
        notification,
        message -> {
            // Có thể bổ sung hoặc điều chỉnh header phù hợp tại đây.
            return message;
        }
);
```

Post processor nên thực hiện thay đổi metadata cần thiết, tránh đưa logic nghiệp vụ phức tạp vào callback này.

## 9. Trường hợp session chưa có authenticated user

Thông thường `user` truyền vào `convertAndSendToUser` là tên của authenticated user gắn với WebSocket session. Spring cũng hỗ trợ trường hợp session không có authenticated principal: có thể dùng session ID làm giá trị `user`, nhưng phải truyền headers có `sessionId` tương ứng.

Ví dụ nâng cao:

```java
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;

SimpMessageHeaderAccessor accessor =
        SimpMessageHeaderAccessor.create();

accessor.setSessionId(sessionId);
accessor.setLeaveMutable(true);

MessageHeaders headers = accessor.getMessageHeaders();

messaging.convertAndSendToUser(
        sessionId,
        "/queue/replies",
        payload,
        headers
);
```

Cách này nhắm tới session đã biết. Nó không thay thế cơ chế xác thực và phân quyền. Chỉ dùng session ID khi ứng dụng đã có cơ sở tin cậy để xác định session đích.

## 10. `@SendToUser` và `convertAndSendToUser`

Spring còn cung cấp annotation `@SendToUser` cho method xử lý message. Annotation này phù hợp khi muốn gửi giá trị trả về của một `@MessageMapping` method tới user đã gửi message.

Ví dụ:

```java
@Controller
public class PortfolioController {

    @MessageMapping("/trade")
    @SendToUser("/queue/position-updates")
    public TradeResult executeTrade(Trade trade) {
        return tradeService.execute(trade);
    }
}
```

Có thể cấu hình `broadcast = false` khi chỉ muốn gửi phản hồi tới session đã gửi message:

```java
@MessageExceptionHandler
@SendToUser(
        destinations = "/queue/errors",
        broadcast = false
)
public ApplicationError handleException(
        MyBusinessException exception) {

    return new ApplicationError(exception.getMessage());
}
```

Phân biệt hai cách:

- `@SendToUser`: khai báo destination ngay trên method; Spring gửi giá trị trả về tới user gắn với message đang được xử lý.
- `convertAndSendToUser`: chủ động gửi message từ bất kỳ component nào có quyền truy cập messaging operations, chẳng hạn service, event listener hoặc scheduled task.

Dùng annotation khi message là phản hồi trực tiếp của handler. Dùng template khi thời điểm gửi hoặc nơi phát sinh message nằm ngoài luồng xử lý `@MessageMapping`.

## 11. Kiểm thử service gửi message

Có thể unit test service bằng cách mock `SimpMessageSendingOperations`, rồi xác nhận service gọi đúng user, destination và payload.

Ví dụ với JUnit 5 và Mockito:

```java
@ExtendWith(MockitoExtension.class)
class NotificationSenderTest {

    @Mock
    private SimpMessageSendingOperations messaging;

    private NotificationSender sender;

    @BeforeEach
    void setUp() {
        sender = new NotificationSender(messaging);
    }

    @Test
    void sendsNotificationToExpectedUserDestination() {
        Notification notification = new Notification(
                "notice-1001",
                "Đơn hàng đã được xác nhận.",
                Instant.parse("2026-01-01T10:00:00Z")
        );

        sender.sendToUser("alice", notification);

        verify(messaging).convertAndSendToUser(
                "alice",
                "/queue/notifications",
                notification
        );
    }
}
```

Test này kiểm tra logic gọi API ở tầng service. Nó không chứng minh WebSocket handshake, user destination resolution, broker routing hoặc client subscription hoạt động. Muốn kiểm tra toàn bộ luồng, cần integration test với messaging infrastructure và client STOMP phù hợp.

## 12. Lỗi thường gặp và cách xử lý

### User không nhận được message

Kiểm tra lần lượt:

1. `username` truyền vào có khớp với `Principal.getName()` của WebSocket session không?
2. Client đã subscribe đúng `/user/queue/notifications` chưa?
3. Server có truyền destination `/queue/notifications` vào `convertAndSendToUser` không?
4. `setUserDestinationPrefix("/user")` đã được cấu hình nhất quán chưa?
5. Broker có xử lý các prefix `/queue` hoặc destination tương ứng không?
6. User có session đang kết nối và subscription còn hiệu lực không?

`convertAndSendToUser` không phải hàng đợi lưu trữ offline. Nếu user không có session phù hợp, message có thể không tới được client. Nếu cần thông báo bền vững, hãy lưu notification trong database hoặc dùng cơ chế lưu trữ/message delivery riêng rồi đồng bộ khi user kết nối lại.

### Gửi nhầm destination hoặc prefix bị lặp

Với cấu hình prefix `/user`, lời gọi:

```java
messaging.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        payload
);
```

đã cung cấp destination đúng cho API. Không truyền `/user/alice/queue/notifications` làm tham số `destination`, vì API đã nhận riêng `user` và tự xử lý user destination prefix.

### User nhận message ở nhiều tab hoặc thiết bị

Mặc định, user destination có thể được phân giải tới các session đang hoạt động của cùng user. Nếu yêu cầu nghiệp vụ là chỉ gửi tới một session, cần thiết kế định tuyến session cụ thể và quản lý session ID một cách an toàn. Với phản hồi trong luồng xử lý message, `@SendToUser(broadcast = false)` là lựa chọn dành cho session gửi message đó.

### Broker xử lý `/user/...` như destination thông thường

Kiểm tra user destination prefix và cấu hình broker. Prefix `/user` cần được Spring user destination handler xử lý. Broker nên được cấu hình với các prefix thực tế như `/topic` và `/queue`, thay vì nhận trực tiếp prefix `/user` như một destination broker thông thường.

### Send bị lỗi hoặc timeout

Các thao tác gửi có thể phát sinh `MessagingException` hoặc lỗi liên quan đến message channel. `SimpMessagingTemplate` cung cấp `setSendTimeout(long)` để cấu hình thời gian chờ gửi trong mili giây. Cần xem log và trạng thái channel/broker khi gặp lỗi. Một lời gọi gửi thành công cũng không đồng nghĩa client đã nhận, hiển thị hoặc xử lý payload.

### Message có sai định dạng

Kiểm tra message converter, kiểu payload và content type. Nếu client mong JSON, bảo đảm ứng dụng có converter JSON phù hợp và payload có thể serialize. Khi truyền headers, phân biệt Spring message headers với native STOMP headers.

## 13. Nguyên tắc sử dụng trong ứng dụng thực tế

- Inject `SimpMessageSendingOperations` vào service để giảm phụ thuộc vào implementation.
- Dùng `Principal.getName()` hoặc identity do server xác thực làm user key; không tin username tùy ý do client gửi lên.
- Dùng `convertAndSendToUser` cho message riêng tư và `convertAndSend` cho broadcast.
- Đảm bảo client subscribe đúng user destination và broker được cấu hình đúng prefix.
- Chỉ đưa dữ liệu mà user đích được phép xem vào payload; destination không phải lớp phân quyền.
- Giữ payload rõ ràng, có cấu trúc và tương thích với message converter.
- Với notification quan trọng cần đảm bảo lưu trữ, retry hoặc xem lại, lưu trạng thái trong hệ thống nghiệp vụ; WebSocket chỉ nên là kênh đẩy realtime.
- Theo dõi lỗi channel, broker và trạng thái kết nối; không xem lời gọi `convertAndSendToUser` là bằng chứng client đã xử lý message.
- Khi dùng external broker, kiểm tra chính sách dọn các destination/queue được tạo cho user session đã ngừng hoạt động.

## 14. Tổng kết kiến thức

`SimpMessageSendingOperations` là abstraction để gửi message theo destination và user destination trong Spring Messaging. `SimpMessagingTemplate` là implementation thường được Spring cấu hình và cung cấp cho ứng dụng STOMP.

Với nhu cầu gửi message riêng cho một người dùng, mẫu gọi cốt lõi là:

```java
messaging.convertAndSendToUser(
        principal.getName(),
        "/queue/notifications",
        notification
);
```

Client đăng ký destination logic:

```javascript
stompClient.subscribe("/user/queue/notifications", onNotification);
```

Spring dùng user destination handler để phân giải destination logic thành destination riêng cho các session tương ứng. Để luồng này hoạt động, cần cấu hình STOMP broker, user destination prefix, identity của user và subscription phía client nhất quán.

## Tài liệu tham khảo

- [Spring Framework Reference — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework Reference — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Framework Javadoc — SimpMessageSendingOperations](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/SimpMessageSendingOperations.html)
- [Spring Framework Javadoc — SimpMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/SimpMessagingTemplate.html)
