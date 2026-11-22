# Xử lý đích người dùng chưa phân giải được trong cụm

## Mục tiêu

Trong ứng dụng Spring STOMP chạy trên nhiều application instance, một WebSocket session chỉ được kết nối trực tiếp với một instance tại một thời điểm. Ví dụ, người dùng `alice` kết nối vào node B, nhưng một tác vụ nghiệp vụ được xử lý trên node A lại gọi `convertAndSendToUser("alice", ...)`.

Nếu node A chỉ tra cứu danh sách session cục bộ, nó có thể không tìm thấy `alice`. Spring gọi tình huống này là user destination chưa được phân giải (unresolved user destination). Spring hỗ trợ hai cơ chế phối hợp qua broker relay để xử lý:

- **User registry broadcast** chia sẻ thông tin user/session giữa các application instance.
- **Unresolved user destination broadcast** chuyển tiếp message chưa phân giải để các instance khác thử phân giải.

Hai cơ chế này giúp gửi message tới session đang kết nối trên node khác. Chúng không tạo hộp thư bền vững cho người dùng offline.

## 1. Vì sao user destination có thể chưa phân giải?

Client thường subscribe destination logic:

~~~javascript
client.subscribe('/user/queue/notifications', (frame) => {
  const notification = JSON.parse(frame.body);
  console.log(notification.message);
});
~~~

Tiền tố `/user` được Spring xử lý bởi `UserDestinationMessageHandler`. Spring chuyển destination logic thành destination vật lý riêng cho session, ví dụ:

~~~text
/user/queue/notifications
        |
        | UserDestinationMessageHandler
        v
/queue/notifications-user123
~~~

Tên đích vật lý là chi tiết nội bộ. Client chỉ cần subscribe destination logic `/user/queue/notifications`; không tự tạo hoặc đoán hậu tố session.

Ở phía gửi, service có thể dùng:

~~~java
messagingTemplate.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        payload
);
~~~

Spring tra cứu user trong `SimpUserRegistry` của application. Trong một instance đơn, registry đó thường chứa các user/session kết nối với chính instance ấy.

Trong cụm nhiều node, tình huống có thể như sau:

- Node A nhận sự kiện nghiệp vụ và cần gửi cho `alice`.
- Node B đang giữ WebSocket session của `alice`.
- Registry cục bộ ở node A chưa biết session trên node B.
- Node A không thể tạo destination vật lý tương ứng chỉ từ registry cục bộ.

Nếu không cấu hình chia sẻ registry hoặc broadcast message chưa phân giải, message có thể không tới được session trên node B.

## 2. Hai cơ chế broadcast giải quyết hai việc khác nhau

Spring cung cấp hai cấu hình trên `StompBrokerRelayRegistration`, đối tượng được trả về từ `MessageBrokerRegistry.enableStompBrokerRelay(...)`.

| Cơ chế | Cấu hình | Mục đích |
|---|---|---|
| Chia sẻ user registry | `setUserRegistryBroadcast(...)` | Phát thông tin registry cục bộ và nhận thông tin registry từ các node khác |
| Chuyển tiếp message chưa phân giải | `setUserDestinationBroadcast(...)` | Phát message chưa phân giải để node khác có cơ hội tìm session phù hợp |

**User registry broadcast** cho phép mỗi node biết thêm user/session đang kết nối ở các node khác. Spring kết hợp registry cục bộ và registry từ xa thông qua `MultiServerUserRegistry`, giúp bộ phân giải user destination có thông tin trên phạm vi cụm.

**Unresolved destination broadcast** là đường dự phòng cho message mà node hiện tại không thể phân giải. Message được gửi tới một broker destination chung; các node khác nhận message và có cơ hội xử lý bằng registry cục bộ của mình.

Hai destination broadcast là các kênh nội bộ giữa application instance. Chúng cần được broker relay phân phối tới tất cả node tham gia cụm.

## 3. Cấu hình broker relay cho cụm

Simple broker tích hợp của Spring lưu subscription trong bộ nhớ của một application instance. Nó phù hợp cho phát triển hoặc triển khai đơn giản, nhưng không cung cấp cơ chế chia sẻ user registry và unresolved destination broadcast giữa nhiều instance.

Để dùng các cơ chế broadcast này, cấu hình STOMP broker relay trỏ tới một message broker bên ngoài. Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class ClusterWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setUserDestinationBroadcast(
                        "/topic/internal/unresolved-user-destination")
                .setUserRegistryBroadcast(
                        "/topic/internal/user-registry");
    }
}
~~~

Trong ví dụ:

- `/topic` và `/queue` là các broker destination prefix được relay xử lý.
- `/topic/internal/unresolved-user-destination` là kênh chuyển tiếp message chưa phân giải.
- `/topic/internal/user-registry` là kênh chia sẻ registry.
- Hai destination nội bộ phải giống nhau trên mọi application instance trong cùng cụm.

Ví dụ tập trung vào phần cấu hình broadcast. Trong môi trường thực tế, cần cấu hình thêm relay host, port và thông tin xác thực theo message broker đang dùng. Không đặt mật khẩu broker trực tiếp trong mã nguồn; lấy thông tin xác thực từ cấu hình bảo mật hoặc biến môi trường.

Các destination broadcast phải được broker hỗ trợ theo kiểu publish/subscribe để message từ một node được phân phối tới các node còn lại. Chỉ trỏ các instance vào những broker độc lập, không chia sẻ cùng hệ thống routing, thì chưa tạo thành một cụm messaging có thể định tuyến user destination xuyên node.

## 4. Luồng xử lý khi user kết nối ở node khác

Giả sử cụm có node A và node B cùng kết nối tới một STOMP broker:

~~~text
                  STOMP broker dùng chung
                 /                       \
          Node A                           Node B
      (service phát)                  (giữ session alice)
           |                                 |
           |                                 | WebSocket client
           |                                 | SUBSCRIBE /user/queue/notifications
           |                                 |
           +---- user registry broadcast ---+
           |
           +---- unresolved destination ----> các node trong cụm
~~~

Luồng tổng quát:

1. Client của `alice` kết nối WebSocket tới node B và subscribe `/user/queue/notifications`.
2. Node B ghi nhận user/session trong registry cục bộ.
3. Node B phát thông tin registry qua destination được cấu hình bằng `setUserRegistryBroadcast`. Các node khác nhận thông tin và có thể cập nhật registry tổng hợp.
4. Service trên node A gọi `convertAndSendToUser("alice", "/queue/notifications", payload)`.
5. Spring tìm session của `alice` bằng registry có sẵn. Khi tìm được session từ xa, message được chuyển thành destination vật lý tương ứng và gửi qua broker.
6. Nếu node A vẫn không phân giải được user destination, `setUserDestinationBroadcast` cho phép phát message chưa phân giải để các node khác thử xử lý.
7. Node giữ session phù hợp có thể phân giải message bằng registry cục bộ và gửi tới destination vật lý. Broker chuyển message tới WebSocket session đã subscribe.

Registry broadcast giúp node gửi có thêm thông tin về user từ xa. Unresolved broadcast giúp node giữ session có cơ hội xử lý khi node gửi chưa tìm được đích. Đây là hai cơ chế bổ trợ nhau.

## 5. Gửi tới user từ service

Service nghiệp vụ vẫn gửi bằng `SimpMessagingTemplate`. Không cần tự chọn node đang giữ session và cũng không cần tự tạo destination vật lý:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String username, NotificationPayload payload) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                payload
        );
    }
}
~~~

Client subscribe destination logic:

~~~javascript
client.subscribe('/user/queue/notifications', (frame) => {
  const payload = JSON.parse(frame.body);
  renderNotification(payload);
});
~~~

Tên user truyền vào `convertAndSendToUser` phải khớp với danh tính mà Spring gắn vào WebSocket session, thường là `Principal.getName()`. Tất cả node phải dùng cùng quy tắc xác thực và ánh xạ danh tính. Nếu một node dùng email còn node khác dùng username, registry có thể tồn tại nhưng việc tra cứu theo tên vẫn thất bại.

Mặc định, nếu một user có nhiều session cùng subscribe destination, Spring có thể gửi tới tất cả session phù hợp, chẳng hạn nhiều tab trình duyệt đang đăng nhập cùng tài khoản.

## 6. Phân biệt cấu hình với simple broker

Cấu hình sau chỉ bật broker trong bộ nhớ của từng instance:

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Khi chạy hai instance độc lập, mỗi simple broker có danh sách subscription riêng. Một node không tự biết các session thuộc node còn lại. Cấu hình trên không cung cấp cơ chế multi-server user registry broadcast hoặc unresolved destination broadcast.

Để xử lý user destination xuyên node, dùng broker relay và cấu hình các destination broadcast trên đối tượng trả về từ `enableStompBrokerRelay`:

~~~java
registry.enableStompBrokerRelay("/topic", "/queue")
        .setUserDestinationBroadcast(
                "/topic/internal/unresolved-user-destination")
        .setUserRegistryBroadcast(
                "/topic/internal/user-registry");
~~~

Không thể chỉ đổi tên tiền tố `/topic` hoặc bật sticky session ở load balancer để thay thế cơ chế này. Sticky session giúp các request/kết nối của một client tiếp tục đi tới cùng node, nhưng không chuyển message do một node khác phát tới node đang giữ WebSocket session.

## 7. Yêu cầu đối với message broker và toàn cụm

Để broadcast hoạt động, kiểm tra các điều kiện sau:

- Mọi application instance dùng cùng một broker hoặc một hệ thống broker có routing liên thông.
- Mọi instance dùng cùng destination cho user registry broadcast và unresolved destination broadcast.
- Các destination broadcast nằm trong phạm vi destination mà broker relay xử lý.
- Broker hỗ trợ phân phối publish/subscribe tới tất cả node đang subscribe các destination nội bộ.
- Relay system connection của mỗi instance có quyền subscribe và publish các destination nội bộ.
- Tên user trong `Principal` nhất quán giữa các instance.
- Client subscribe destination logic `/user/...`, không subscribe destination vật lý do Spring tạo.
- Quy tắc bảo mật không cho client tùy ý đọc hoặc ghi vào các destination nội bộ.

`userRegistryBroadcast` mang thông tin về user/session của node. `userDestinationBroadcast` có thể mang nội dung message cần chuyển tiếp. Hãy giới hạn quyền truy cập các destination này bằng broker ACL và quy tắc authorization ở ứng dụng. Chỉ các kết nối server phù hợp mới được phép sử dụng các kênh nội bộ.

## 8. Khi user thực sự offline

Unresolved destination broadcast chỉ cho các node khác cơ hội tìm một session đang tồn tại. Nếu không có node nào giữ session của user, sẽ không có đích WebSocket để phân phối message.

Các cơ chế broadcast này không phải hàng đợi lưu trữ thông báo offline. Nếu nghiệp vụ yêu cầu user đăng nhập lại vẫn xem được thông báo đã phát:

1. Lưu thông báo vào database hoặc một kho lưu trữ bền vững.
2. Ghi nhận user nhận, nội dung, thời điểm tạo và trạng thái đã đọc.
3. Dùng `convertAndSendToUser` để báo realtime cho session đang online.
4. Khi client kết nối lại, tải thông báo chưa đọc qua API.
5. Cập nhật trạng thái đã đọc bằng thao tác nghiệp vụ riêng.

Nếu cần bảo đảm một sự kiện nghiệp vụ không bị mất giữa lúc commit database và lúc publish, cân nhắc Transactional Outbox hoặc cơ chế phát lại tương đương. Broker relay và user destination broadcast không tự cung cấp bảo đảm exactly-once cho toàn bộ nghiệp vụ.

## 9. Kiểm thử cấu hình nhiều node

Một unit test chỉ xác minh service gọi `convertAndSendToUser` không chứng minh routing xuyên node hoạt động. Cần integration test với ít nhất hai application instance và cùng một broker.

Kịch bản kiểm thử:

1. Khởi động broker STOMP dùng chung.
2. Khởi động node A và node B với cùng cấu hình relay và hai destination broadcast.
3. Kết nối một STOMP client tới node B bằng user `alice`.
4. Đợi CONNECT thành công và subscribe `/user/queue/notifications`.
5. Chờ registry broadcast được xử lý.
6. Gọi service trên node A để gửi notification cho `alice`.
7. Xác nhận client kết nối qua node B nhận đúng payload.
8. Thử gửi khi `alice` không còn session ở bất kỳ node nào và xác nhận ứng dụng không coi broadcast là nơi lưu thông báo offline.

Nên chạy thêm tình huống node B vừa khởi động hoặc registry chưa kịp cập nhật để kiểm tra unresolved destination broadcast. Có thể kiểm tra log và broker subscription để xác nhận các system connection đã đăng ký đúng destination nội bộ.

## 10. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Gửi từ node A nhưng client ở node B không nhận | Các node dùng broker khác nhau hoặc broker không phân phối topic giữa chúng | Kiểm tra relay host, virtual host, broker cluster và subscription |
| User có session nhưng node gửi báo unresolved | Registry broadcast chưa bật, chưa cập nhật hoặc tên user không khớp | Kiểm tra `setUserRegistryBroadcast`, registry tổng hợp và `Principal.getName()` |
| Unresolved message không tới node khác | Chưa cấu hình `setUserDestinationBroadcast` hoặc broker ACL chặn destination | Kiểm tra destination và quyền publish/subscribe của system connection |
| Cấu hình broadcast nhưng chạy simple broker vẫn không hoạt động | Simple broker là broker trong bộ nhớ theo từng instance | Chuyển sang `enableStompBrokerRelay` và broker dùng chung |
| Client kết nối nhưng không nhận thông báo | Client subscribe sai destination hoặc chưa SUBSCRIBE thành công | Dùng `/user/queue/notifications` và kiểm tra frame STOMP |
| User nhận nhiều thông báo ở nhiều tab | User có nhiều session cùng subscribe destination | Kiểm tra các session đang hoạt động; đây có thể là hành vi mặc định |
| User offline không nhận lại thông báo | Không có session nào để phân giải destination | Lưu thông báo bền vững và tải lại khi client reconnect |
| Node không nhận registry broadcast | System connection thiếu quyền hoặc broker không chuyển tiếp destination nội bộ | Kiểm tra broker ACL, log relay và subscription của node |

## Ghi nhớ

- User destination `/user/...` là destination logic; Spring chuyển nó thành destination vật lý riêng cho session.
- Registry cục bộ của một node không mặc nhiên chứa session trên các node khác.
- `setUserRegistryBroadcast` chia sẻ thông tin user/session giữa các node.
- `setUserDestinationBroadcast` chuyển tiếp message chưa phân giải để node khác thử xử lý.
- Hai cấu hình được đặt trên `StompBrokerRelayRegistration` trả về từ `enableStompBrokerRelay`.
- Simple broker không cung cấp hai cơ chế broadcast multi-server này.
- Mọi node cần dùng chung broker, destination nội bộ và quy tắc định danh user.
- Broadcast chỉ giúp định tuyến tới session đang online; muốn hỗ trợ offline phải lưu thông báo bền vững.

## Tài liệu tham khảo

- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/user-destination.html)
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/enable.html)
- [StompBrokerRelayRegistration API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)
- [UserDestinationMessageHandler API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/simp/user/UserDestinationMessageHandler.html)
