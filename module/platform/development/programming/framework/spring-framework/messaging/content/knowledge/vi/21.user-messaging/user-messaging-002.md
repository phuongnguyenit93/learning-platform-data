# Phát thông điệp từ service bằng `convertAndSend`

## Mục tiêu

Trong ứng dụng Spring dùng STOMP over WebSocket, một service có thể chủ động đẩy dữ liệu tới các client đang kết nối mà không cần client gửi request trước. Cách phổ biến là inject `SimpMessagingTemplate` rồi gọi `convertAndSend(destination, payload)`.

Ví dụ: sau khi đơn hàng được thanh toán, service phát một thông báo lên `/topic/notifications`. Các trình duyệt đã subscribe destination này sẽ nhận được thông điệp gần như ngay lập tức qua kết nối WebSocket.

Bài này tập trung vào gửi thông điệp từ server tới client bằng Spring Messaging/STOMP. Đây là luồng push thời gian thực; nó không tự tạo lịch sử thông báo hay bảo đảm client đã đọc thông điệp.

## 1. Các thành phần trong luồng gửi

- **Service nghiệp vụ** quyết định khi nào cần phát thông điệp, ví dụ khi đơn hàng đổi trạng thái.
- **`SimpMessagingTemplate`** nhận destination và object payload. Phương thức `convertAndSend` dùng `MessageConverter` đang được cấu hình để chuyển object thành Spring `Message`.
- **`brokerChannel` và message broker** nhận thông điệp gửi đi, tìm các subscription khớp destination.
- **`clientOutboundChannel`** chuyển thông điệp tới các WebSocket session tương ứng.
- **STOMP client** nhận frame `MESSAGE` và xử lý payload.

Điểm quan trọng: service gửi vào destination mà broker quản lý. Với cấu hình thường gặp, `/topic` dùng cho luồng broadcast và `/queue` dùng theo quy ước cho luồng một-nhiều hoặc điểm-điểm. Với simple broker tích hợp, hai tiền tố này chỉ là quy ước đặt tên; broker không tự áp đặt ngữ nghĩa queue của một message broker đầy đủ.

## 2. Cấu hình STOMP/WebSocket tối thiểu

Cần có các module `spring-messaging` và `spring-websocket`. Với Spring Boot, có thể dùng các starter sau; phiên bản nên được quản lý bởi Spring Boot dependency management/BOM của dự án.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-websocket</artifactId>
    </dependency>
</dependencies>
~~~

Khai báo một STOMP endpoint để client bắt tay WebSocket và cấu hình các tiền tố destination:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        // Client gửi MESSAGE tới /app/... sẽ được định tuyến tới @MessageMapping.
        registry.setApplicationDestinationPrefixes("/app");

        // Client SUBSCRIBE các destination này; server cũng có thể gửi vào đây.
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Ý nghĩa của các đường dẫn:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| WebSocket handshake endpoint | `/ws` | URL client dùng để mở kết nối WebSocket |
| Application prefix | `/app` | Tiền tố cho thông điệp client gửi vào controller có `@MessageMapping` |
| Broker prefix | `/topic`, `/queue` | Destination được broker xử lý và phân phối tới subscriber |

Không ghép `/app` vào destination của lệnh gửi broadcast bằng `convertAndSend`. `/app` dành cho chiều client → application; ví dụ server gửi ra `/topic/notifications`.

Nếu client cần SockJS fallback, đăng ký endpoint bằng `registry.addEndpoint("/ws").withSockJS()` và dùng SockJS client tương ứng. Không bật SockJS ở server nếu client chỉ kết nối WebSocket thuần theo cấu hình hiện tại.

## 3. Tạo payload có cấu trúc

Nên gửi DTO có cấu trúc thay vì ghép một chuỗi khó mở rộng. Ví dụ dùng Java 17 record:

~~~java
import java.time.Instant;

public record NotificationMessage(
        String type,
        String title,
        String body,
        Instant createdAt
) {
}
~~~

Khi Jackson có trên classpath và message converter JSON phù hợp được cấu hình, DTO có thể được serialize thành JSON. Client nhận payload JSON và có thể đọc các trường `type`, `title`, `body`, `createdAt`.

Không gửi entity JPA trực tiếp nếu entity có quan hệ lazy, dữ liệu nhạy cảm hoặc cấu trúc nội bộ không dành cho client. Hãy tạo DTO chỉ chứa các trường được phép công khai.

## 4. Inject template vào service và gọi convertAndSend

Spring tạo `SimpMessagingTemplate` khi bật STOMP message broker. Có thể inject bằng constructor vào bất kỳ Spring bean nào, chẳng hạn `@Service`.

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private static final String DESTINATION = "/topic/notifications";

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(NotificationMessage notification) {
        messagingTemplate.convertAndSend(DESTINATION, notification);
    }
}
~~~

Cách gọi từ một service nghiệp vụ:

~~~java
import java.time.Instant;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final NotificationService notificationService;

    public OrderApplicationService(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    public void markOrderPaid(long orderId) {
        // Thực hiện các bước nghiệp vụ và cập nhật trạng thái đơn hàng ở đây.

        NotificationMessage message = new NotificationMessage(
                "ORDER_PAID",
                "Thanh toán thành công",
                "Đơn hàng #" + orderId + " đã được thanh toán.",
                Instant.now()
        );

        notificationService.publish(message);
    }
}
~~~

Khi `markOrderPaid` gọi `publish`, Spring chuyển DTO thành message rồi gửi tới broker ở destination `/topic/notifications`. Mọi client đang subscribe đúng destination và được phép nhận sẽ nhận thông điệp đó. Client kết nối sau thời điểm phát không tự nhận lại thông điệp cũ từ simple broker.

Có thể inject interface `SimpMessageSendingOperations` thay cho lớp cụ thể nếu muốn phụ thuộc vào abstraction. `SimpMessagingTemplate` là implementation thông dụng trong cấu hình STOMP.

## 5. Client phải subscribe đúng destination

Ví dụ client JavaScript dùng package `@stomp/stompjs` và kết nối trực tiếp tới endpoint `/ws`:

~~~javascript
import { Client } from '@stomp/stompjs';

const client = new Client({
  brokerURL: 'ws://localhost:8080/ws',
  reconnectDelay: 5000,

  onConnect: () => {
    client.subscribe('/topic/notifications', (frame) => {
      const notification = JSON.parse(frame.body);

      console.log(notification.title);
      console.log(notification.body);
    });
  },
});

client.activate();
~~~

Trình tự cần có:

1. Client mở kết nối tới `/ws`.
2. Sau khi STOMP CONNECT thành công, client gửi SUBSCRIBE tới `/topic/notifications`.
3. Service gọi `convertAndSend("/topic/notifications", payload)`.
4. Broker tìm các subscription khớp destination và gửi frame tới client.

Trong production, dùng `wss://` khi trang được phục vụ qua HTTPS và cấu hình origin phù hợp. Đường dẫn WebSocket endpoint và destination subscription là hai giá trị khác nhau: `/ws` là endpoint kết nối, còn `/topic/notifications` là destination nhận thông điệp.

## 6. Broadcast và gửi riêng cho một người dùng

`convertAndSend(destination, payload)` gửi tới destination chung. Tất cả session đã subscribe destination đó và được phép nhận đều có thể nhận cùng payload.

Nếu cần gửi riêng cho một user, dùng `convertAndSendToUser`:

~~~java
public void publishToUser(String username, NotificationMessage notification) {
    messagingTemplate.convertAndSendToUser(
            username,
            "/queue/notifications",
            notification
    );
}
~~~

Client của user đó subscribe destination logic:

~~~javascript
client.subscribe('/user/queue/notifications', (frame) => {
  const notification = JSON.parse(frame.body);
  console.log(notification.title);
});
~~~

Spring xử lý tiền tố `/user` và chuyển destination logic thành destination riêng cho session của user. Tên truyền vào `convertAndSendToUser` phải khớp với tên user trong `Principal` của WebSocket session. Với một user có nhiều session, mặc định các session phù hợp đều có thể được nhắm tới.

Không lấy `username` tùy ý từ request của client để quyết định người nhận. Hãy lấy danh tính từ ngữ cảnh đã xác thực ở server và kiểm tra quyền trước khi phát thông báo.

## 7. Các overload thường dùng

Các dạng gọi phổ biến gồm:

~~~java
// Payload được chuyển đổi bằng MessageConverter.
messagingTemplate.convertAndSend("/topic/events", event);

// Gửi kèm headers.
messagingTemplate.convertAndSend("/topic/events", event, headers);

// Gửi kèm MessagePostProcessor để điều chỉnh message sau khi convert.
messagingTemplate.convertAndSend("/topic/events", event, postProcessor);
~~~

- `destination`: destination mà broker có thể xử lý, ví dụ `/topic/events`.
- `payload`: object cần gửi; có thể là String, DTO hoặc kiểu được converter hỗ trợ.
- `headers`: metadata của message. Với `SimpMessagingTemplate`, map header mặc định được diễn giải như native headers khi gửi ra STOMP, trừ khi đã được chuẩn bị qua `SimpMessageHeaderAccessor` hoặc chứa cấu trúc native headers tương ứng.
- `MessagePostProcessor`: callback cho phép chỉnh message sau bước convert và trước khi gửi.

`convertAndSend` nhận object và thực hiện chuyển đổi. Nếu đã có sẵn một Spring `Message<?>` hoàn chỉnh, dùng `send(destination, message)` để gửi message đó.

## 8. Gửi sau khi transaction commit

Nếu thông báo phụ thuộc vào dữ liệu vừa ghi trong transaction, tránh phát trước khi transaction commit. Nếu transaction rollback, client có thể đã nhận thông báo cho một thay đổi không tồn tại.

Một cách phổ biến là publish domain event trong nghiệp vụ rồi lắng nghe sau commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {

    private final NotificationService notificationService;

    public OrderNotificationListener(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPaid(OrderPaidEvent event) {
        NotificationMessage message = new NotificationMessage(
                "ORDER_PAID",
                "Thanh toán thành công",
                "Đơn hàng #" + event.orderId() + " đã được thanh toán.",
                event.paidAt()
        );

        notificationService.publish(message);
    }
}
~~~

Ví dụ giả định ứng dụng có record `OrderPaidEvent(long orderId, Instant paidAt)` và phát event đó bên trong transaction. `AFTER_COMMIT` giúp chỉ phát sau khi transaction commit thành công. Đây vẫn là gửi realtime; nếu cần bảo đảm phát lại khi broker tạm ngừng, cần thiết kế lưu trữ/outbox và cơ chế retry riêng.

## 9. Bảo mật destination

WebSocket giữ kết nối lâu dài nên cần bảo vệ cả handshake, STOMP CONNECT, MESSAGE và SUBSCRIBE:

- Chỉ cho phép origin của frontend tin cậy; tránh cấu hình origin quá rộng trong môi trường production.
- Kiểm tra quyền SUBSCRIBE theo destination. Một user không nên tự động được đọc mọi topic chỉ vì đã đăng nhập.
- Thông thường, client có thể được phép SUBSCRIBE vào một broker destination nhất định nhưng không được phép gửi MESSAGE trực tiếp vào tiền tố broker như `/topic/**` hoặc `/queue/**`. Nếu cho phép, client có thể giả mạo thông báo hệ thống.
- Dùng `/app/**` cho message đi vào handler ứng dụng, rồi để server kiểm tra người gửi, dữ liệu và quyền trước khi phát tới broker.
- Với thông báo riêng, dùng user destination và danh tính `Principal` đã xác thực. Không coi ID người nhận do client cung cấp là bằng chứng quyền truy cập.

Cấu hình `SimpMessagingTemplate` không thay thế cấu hình authorization của Spring Security.

## 10. Giới hạn delivery và lựa chọn broker

`enableSimpleBroker` phù hợp để phát triển hoặc cho hệ thống nhỏ. Simple broker giữ subscription trong bộ nhớ của từng application instance; nó không phải hàng đợi lưu trữ bền vững và không phù hợp cho clustering. Khi client offline, message đã phát không tự được lưu để gửi lại sau.

Cân nhắc STOMP broker relay tới một broker đầy đủ khi cần khả năng mở rộng, clustering hoặc các tính năng giao thức nâng cao. Broker relay cần cấu hình kết nối và thông tin xác thực tới broker ngoài.

Nếu nghiệp vụ yêu cầu người dùng luôn xem được thông báo dù offline:

1. Lưu thông báo vào database cùng user nhận và thời điểm tạo.
2. Dùng `convertAndSend` hoặc `convertAndSendToUser` để báo cho client đang online rằng có dữ liệu mới.
3. Khi client kết nối lại hoặc mở trang thông báo, tải danh sách chưa đọc từ API/database.
4. Đánh dấu đã đọc bằng một request nghiệp vụ riêng.

Việc `convertAndSend` hoàn tất không chứng minh trình duyệt đã nhận, hiển thị hay người dùng đã đọc. Nếu cần xác nhận xử lý, thiết kế acknowledgement ở tầng ứng dụng.

## 11. Kiểm thử service

Có thể unit test rằng service gửi đúng destination và payload bằng Mockito. Test này xác minh lời gọi tới template; nó không thay thế integration test cho WebSocket handshake, broker hoặc client subscription.

~~~java
import static org.mockito.Mockito.verify;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.messaging.simp.SimpMessagingTemplate;

@ExtendWith(MockitoExtension.class)
class NotificationServiceTest {

    @Mock
    private SimpMessagingTemplate messagingTemplate;

    @InjectMocks
    private NotificationService notificationService;

    @Test
    void publishesNotificationToTopic() {
        NotificationMessage payload = new NotificationMessage(
                "INFO",
                "Thông báo",
                "Nội dung thử nghiệm",
                Instant.parse("2026-01-01T00:00:00Z")
        );

        notificationService.publish(payload);

        verify(messagingTemplate).convertAndSend(
                "/topic/notifications",
                payload
        );
    }
}
~~~

Để kiểm tra end-to-end, chạy ứng dụng, mở ít nhất một STOMP client, chờ SUBSCRIBE thành công rồi gọi endpoint hoặc thao tác nghiệp vụ kích hoạt service. Kiểm tra client nhận đúng JSON và destination. Có thể mở hai client để xác nhận broadcast tới mọi subscriber.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Client không nhận message | Client chưa SUBSCRIBE hoặc subscribe sai destination | So sánh chính xác destination ở client và `convertAndSend` |
| Gửi vào `/app/...` nhưng không thấy broadcast | `/app` được định tuyến tới handler ứng dụng | Gửi tới broker prefix như `/topic/...` khi muốn broadcast |
| Client gửi vào `/topic` nhưng bị từ chối | Quy tắc security chặn MESSAGE tới broker prefix | Kiểm tra authorization; client thường chỉ cần SUBSCRIBE |
| DTO không chuyển thành JSON | Không có converter phù hợp hoặc kiểu payload không được hỗ trợ | Kiểm tra Jackson và cấu hình message converters |
| Gửi riêng không tới đúng người | Giá trị user không khớp `Principal.getName()` hoặc client subscribe sai | Kiểm tra danh tính đã xác thực và subscribe `/user/queue/...` |
| Chỉ một instance nhận được message | Simple broker lưu subscription trong bộ nhớ của từng instance | Dùng broker relay và cấu hình chia sẻ phù hợp |
| Thông báo xuất hiện dù transaction rollback | Phát message trước khi transaction commit | Phát qua `@TransactionalEventListener(AFTER_COMMIT)` hoặc outbox |

## Ghi nhớ

- Inject `SimpMessagingTemplate` vào service bằng constructor.
- Dùng `convertAndSend("/topic/...", payload)` để phát tới mọi subscriber phù hợp.
- Client phải subscribe đúng destination sau khi STOMP CONNECT thành công.
- Dùng `convertAndSendToUser(username, "/queue/...", payload)` cho thông báo theo user.
- `/ws` là endpoint kết nối; `/app` là tiền tố inbound; `/topic` và `/queue` là broker destinations trong ví dụ.
- Simple broker không lưu message cho client offline và không bảo đảm người dùng đã đọc.

## Tài liệu tham khảo

- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Security — WebSocket Authorization](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
