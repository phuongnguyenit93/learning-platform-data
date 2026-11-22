# convertAndSendToUser với tên Principal

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cách Spring gửi message đến một người dùng cụ thể qua user destination.
- Lấy đúng tên định danh từ `java.security.Principal#getName()` để làm khóa định tuyến.
- Phân biệt destination phía client đăng ký với destination phía server truyền cho `convertAndSendToUser`.
- Cấu hình broker và tiêm `SimpMessagingTemplate` vào service/controller.
- Hiểu cách Spring tìm các session đang hoạt động của user và xử lý trường hợp không có session.
- Tránh dùng username hoặc header do client tự khai báo làm căn cứ xác thực, phân quyền.

## 1. Bài toán gửi message đến một user

Trong ứng dụng WebSocket/STOMP, `/topic` thường dùng cho message phát đến nhiều subscriber, còn `/queue` thường dùng cho message theo luồng riêng. Tuy nhiên, chỉ chọn một destination như `/queue/notifications` chưa đủ để Spring biết phải gửi đến phiên kết nối của ai.

Spring Messaging cung cấp **user destination** để định tuyến message theo người dùng đã gắn với phiên WebSocket. Ứng dụng có thể gửi một thông báo riêng đến người dùng có tên Principal là `alice` mà không cần tự tạo destination vật lý cho từng session.

Hai phía sử dụng hai dạng destination khác nhau:

- Client đăng ký nhận message tại `/user/queue/notifications`.
- Server gọi `convertAndSendToUser("alice", "/queue/notifications", payload)`.

Tiền tố `/user` cho client biết đây là user destination. Khi xử lý, Spring phân giải user destination thành destination nội bộ gắn với một hoặc nhiều session đang hoạt động của user đó. Vì thế, server truyền phần destination phía sau tiền tố user, ví dụ `/queue/notifications`.

Đây là cơ chế định tuyến ở tầng messaging. Nó không tự xác thực user, không lưu message thành hộp thư offline và cũng không thay thế quy tắc phân quyền của ứng dụng.

## 2. `Principal` và tên định danh dùng để định tuyến

`java.security.Principal` biểu diễn danh tính của thực thể đang được xác thực trong một kết nối. Phương thức quan trọng nhất là:

```java
String getName();
```

Trong Spring WebSocket/STOMP, Principal thường được liên kết với WebSocket session thông qua quá trình xác thực của ứng dụng, ví dụ xác thực HTTP handshake hoặc cơ chế tích hợp Spring Security. Spring dùng Principal gắn với session để xác định user khi xử lý user destination.

Khi gửi message, tham số đầu tiên của `convertAndSendToUser` là **tên user dưới dạng String**. Vì vậy, lấy tên bằng `principal.getName()`:

```java
Principal principal = ...;

String username = principal.getName();
messagingTemplate.convertAndSendToUser(
        username,
        "/queue/notifications",
        notification
);
```

Không truyền trực tiếp đối tượng Principal vào tham số user. Không dùng `principal.toString()`, tên hiển thị, email tự suy đoán hoặc một header tùy ý do client gửi. Giá trị cần dùng là tên định danh mà hệ thống xác thực đã gắn với Principal.

Tên phải khớp với user đã đăng ký trong Spring user registry của các WebSocket session đang hoạt động. Ví dụ, nếu session của user được đăng ký với `Principal#getName() = "alice"` thì lời gọi gửi đến `"alice"` mới định tuyến đến các session tương ứng.

### Principal có thể vắng mặt

Một handler chỉ cho phép user đã xác thực nên được bảo vệ bằng cấu hình bảo mật của ứng dụng. Dù vậy, khi viết mã, vẫn nên xử lý trường hợp Principal không có hoặc tên rỗng, đặc biệt nếu handler còn được gọi từ các luồng không yêu cầu đăng nhập.

```java
private String requireUsername(Principal principal) {
    if (principal == null || principal.getName() == null
            || principal.getName().isBlank()) {
        throw new IllegalStateException(
                "An authenticated Principal is required"
        );
    }
    return principal.getName();
}
```

Trong ứng dụng thực tế, có thể dùng exception và response phù hợp với quy ước bảo mật của dự án. Đừng biến một Principal vắng mặt thành user mặc định hoặc dùng tên do client gửi để thay thế.

## 3. `SimpMessagingTemplate.convertAndSendToUser`

`org.springframework.messaging.simp.SimpMessagingTemplate` là abstraction để gửi message qua message channel của Spring. Nó hỗ trợ gửi message đến destination thông thường và đến user destination.

Cách gọi cơ bản:

```java
messagingTemplate.convertAndSendToUser(
        username,
        "/queue/notifications",
        payload
);
```

Ba đối số có ý nghĩa:

| Đối số | Ý nghĩa |
|---|---|
| `user` | Tên định danh của người nhận, thường là `Principal#getName()` |
| `destination` | Destination phía ứng dụng, ví dụ `/queue/notifications` |
| `payload` | Đối tượng dữ liệu sẽ được message converter chuyển thành message |

Phương thức `convertAndSendToUser` thực hiện việc chuyển đổi payload thành message rồi gửi đến user destination. Lớp template cũng có overload nhận map headers và message post-processor khi ứng dụng cần bổ sung metadata hoặc xử lý message trước khi gửi. Chỉ thêm header khi có nhu cầu rõ ràng; không dùng header do client cung cấp làm căn cứ xác thực.

Ví dụ một service gửi thông báo:

```java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(
            SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(
            String username,
            Notification notification) {

        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                notification
        );
    }
}

public record Notification(String title, String message) {}
```

Service nhận username đã được xác định từ nguồn đáng tin cậy. Nó không tự suy ra người nhận từ dữ liệu tùy ý trong payload.

## 4. Destination ở client và server

Đây là phần dễ nhầm nhất khi mới dùng user destination.

Giả sử broker được cấu hình nhận các destination `/queue` và `/topic`, còn tiền tố user destination là `/user`.

Client của Alice đăng ký:

```javascript
stompClient.subscribe(
    "/user/queue/notifications",
    (frame) => {
        const notification = JSON.parse(frame.body);
        console.log(notification.title, notification.message);
    }
);
```

Server gửi:

```java
messagingTemplate.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        new Notification(
                "Đơn hàng đã xác nhận",
                "Đơn hàng ORD-100 đã được tiếp nhận."
        )
);
```

Spring ghép user name với user destination prefix để tạo user destination nội bộ, sau đó phân giải destination đó đến các session của Alice. Client không cần biết destination vật lý riêng cho session của mình.

**Không thêm `/user` vào đối số destination của `convertAndSendToUser`.** Trong cấu hình mặc định, hãy truyền `/queue/notifications` ở phía server và để client đăng ký `/user/queue/notifications`. Nếu truyền nhầm `/user/queue/notifications` vào đối số destination, bạn đang đưa tiền tố user vào phần destination vốn đã được template xử lý, dẫn đến đường dẫn sai.

Nếu ứng dụng đổi tiền tố bằng `setUserDestinationPrefix`, cả destination mà client đăng ký và cách định tuyến của ứng dụng phải tuân theo tiền tố mới. Không mặc định mọi ứng dụng đều sử dụng `/user` nếu cấu hình đã thay đổi.

## 5. Cấu hình message broker

Một cấu hình STOMP tối thiểu thường khai báo endpoint WebSocket, application destination prefix và broker destination prefix:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

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
        // User destination prefix mặc định là "/user".
    }
}
```

Ý nghĩa:

- Client gửi message đầu vào đến destination có prefix `/app`; Spring định tuyến đến `@MessageMapping`.
- Broker xử lý destination có prefix `/topic` hoặc `/queue` theo cấu hình.
- User destination mặc định có prefix `/user` và được Spring phân giải trước khi message đến broker.
- `SimpMessagingTemplate` được cung cấp trong hạ tầng message broker đã bật bằng `@EnableWebSocketMessageBroker` và có thể được tiêm vào bean Spring.

Nếu ứng dụng dùng broker relay thay cho simple broker, vẫn cần cấu hình các destination prefix phù hợp và bảo đảm broker relay nhận được destination sau khi Spring phân giải user destination.

## 6. Lấy Principal trong `@MessageMapping` và gửi cho chính user đó

Spring có thể phân giải `Principal` của phiên hiện tại thành tham số trong handler. Ví dụ sau gửi thông báo phản hồi riêng cho người đang gửi yêu cầu:

```java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class NotificationController {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationController(
            SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/notifications.request")
    public void requestNotification(
            @Payload NotificationRequest request,
            Principal principal) {

        String username = requireUsername(principal);

        Notification response = new Notification(
                "Đã nhận yêu cầu",
                "Yêu cầu " + request.reference() + " đã được tiếp nhận."
        );

        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                response
        );
    }

    private String requireUsername(Principal principal) {
        if (principal == null || principal.getName() == null
                || principal.getName().isBlank()) {
            throw new IllegalStateException(
                    "An authenticated Principal is required"
            );
        }
        return principal.getName();
    }
}

record NotificationRequest(String reference) {}

record Notification(String title, String message) {}
```

Client gửi request đến `/app/notifications.request` và đã đăng ký `/user/queue/notifications`. Khi handler chạy, Spring cung cấp Principal của session hiện tại. Controller lấy tên Principal rồi gửi response đến đúng user destination.

Đây là ví dụ tích hợp trong ứng dụng Spring đã cấu hình WebSocket/STOMP, message broker và xác thực. Các record được đặt cùng ví dụ để minh họa cấu trúc DTO; đoạn mã không phải chương trình độc lập có thể chạy chỉ bằng `javac`.

## 7. Gửi cho một user khác

Nhiều nghiệp vụ cần gửi đến người nhận khác với người đang thực hiện request, ví dụ thông báo cho nhân viên phụ trách khi đơn hàng được tạo.

Khi đó, service nhận tên user đích từ nguồn đáng tin cậy, thường là kết quả tra cứu từ dữ liệu nghiệp vụ:

```java
public void notifyAssignee(
        Order order,
        String assigneeUsername) {

    Notification notification = new Notification(
            "Có đơn hàng mới",
            "Bạn được phân công xử lý " + order.getNumber()
    );

    messagingTemplate.convertAndSendToUser(
            assigneeUsername,
            "/queue/notifications",
            notification
    );
}
```

Trong ví dụ này, `assigneeUsername` phải đến từ kết quả phân công đã được server kiểm tra. Không nhận username từ payload rồi gửi tùy ý mà không xác thực người gửi có quyền thực hiện hành động đó.

Cần phân biệt hai giá trị:

- **Principal của người gửi**: danh tính đã xác thực của session đang thực hiện request.
- **Username của người nhận**: user mà nghiệp vụ muốn gửi message đến.

Hai giá trị này có thể giống hoặc khác nhau. `convertAndSendToUser` chỉ thực hiện định tuyến theo tên user được truyền vào; nó không quyết định người gửi có quyền gửi cho người nhận hay không.

## 8. Spring xử lý user destination như thế nào?

Luồng tổng quát:

1. Client kết nối WebSocket và được gắn Principal đã xác thực.
2. Spring đăng ký session cùng tên user vào user registry.
3. Client đăng ký `/user/queue/notifications`.
4. Server gọi `convertAndSendToUser("alice", "/queue/notifications", payload)`.
5. Spring tạo message gửi đến user destination chứa tên Alice.
6. `UserDestinationMessageHandler` và cơ chế phân giải user destination tìm các session tương ứng.
7. Spring chuyển message đến destination nội bộ gắn với session phù hợp.
8. Broker chuyển message đến client đã đăng ký nhận.

User destination cho phép nhiều session cùng gắn với một Principal name. Theo hành vi mặc định, message gửi đến user có thể được phân giải đến tất cả session đang hoạt động của user đó. Ví dụ, Alice mở ứng dụng trên hai tab đã đăng nhập cùng tài khoản thì cả hai session có thể nhận thông báo.

Nếu nghiệp vụ cần chỉ gửi đến một session cụ thể, cần thiết kế rõ cơ chế chọn session và metadata session tương ứng. Không nên nhầm việc gửi đến một user với việc gửi đến duy nhất một tab hoặc một thiết bị.

User registry theo dõi các session đang hoạt động. Nếu user không có session phù hợp, message không tự động trở thành một bản ghi hộp thư để user đọc khi đăng nhập lại. Với thông báo cần lưu bền vững, hãy ghi sự kiện/thông báo vào cơ sở dữ liệu hoặc hàng đợi bền vững, rồi dùng WebSocket để báo cho client có dữ liệu mới.

### Ứng dụng chạy trên nhiều node

Trong triển khai nhiều instance, mỗi node có thể chỉ biết các session kết nối với node đó. Nếu cần định tuyến user destination xuyên node, phải cấu hình cơ chế chia sẻ/broadcast user registry và thông báo destination chưa phân giải theo mô hình Spring hỗ trợ. Cấu hình cụ thể phụ thuộc kiến trúc broker và topology của ứng dụng; không giả định simple broker cục bộ tự đồng bộ session giữa các node.

## 9. Phân biệt với `@SendToUser`

Spring còn có annotation `@SendToUser` để gửi giá trị trả về của handler đến user destination. Ví dụ:

```java
@MessageMapping("/profile.refresh")
@SendToUser("/queue/profile")
public ProfileView refreshProfile(Principal principal) {
    return profileService.load(principal.getName());
}
```

Hai cách có mục đích gần nhau nhưng cách sử dụng khác nhau:

| Cách | Phù hợp khi |
|---|---|
| `@SendToUser` | Muốn định tuyến giá trị trả về của một handler đến user hiện tại |
| `convertAndSendToUser` | Muốn chủ động gửi message từ controller, service hoặc thành phần nghiệp vụ đến user được chỉ định |

`convertAndSendToUser` hữu ích khi sự kiện phát sinh ngoài vòng đời của một handler STOMP, ví dụ sau khi service xử lý đơn hàng, hoàn tất tác vụ nền hoặc nhận kết quả từ hệ thống khác.

Với `@SendToUser`, thuộc tính `broadcast` mặc định là `true`. Có thể đặt `broadcast = false` nếu chỉ muốn gửi đến session đang xử lý message đầu vào. Quy tắc đó thuộc annotation; đừng mặc định rằng mọi lời gọi template đều có cùng cấu hình annotation.

## 10. Bảo mật khi định tuyến theo Principal

User destination dựa trên Principal đã gắn với session, nhưng bản thân lời gọi template không phải cơ chế cấp quyền.

Các nguyên tắc nên áp dụng:

- **Xác thực trước khi gắn danh tính.** Principal phải đến từ cơ chế xác thực đáng tin cậy của ứng dụng, thường là HTTP handshake/Spring Security.
- **Không tin header định danh do client gửi.** Header như `user`, `username`, `x-user-id` hoặc `role` có thể bị giả mạo. Không dùng chúng thay cho `Principal#getName()`.
- **Kiểm tra quyền gửi cho user khác.** Một user chỉ được gửi đến người nhận mà nghiệp vụ cho phép, ví dụ assignee đã được server xác định.
- **Bảo vệ inbound destination.** Dùng Spring Security message authorization để giới hạn ai được gửi đến `/app/**` và ai được đăng ký vào các destination phù hợp.
- **Không để client đăng ký destination nội bộ.** Client nên đăng ký user destination công khai như `/user/queue/notifications`; không cấp quyền tùy tiện cho các destination vật lý sau khi phân giải.
- **Dùng tên Principal nhất quán.** Authentication provider, user registry và lời gọi template phải dùng cùng quy ước tên, bao gồm cả cách chuẩn hóa chữ hoa/thường nếu hệ thống có quy định.
- **Không đưa bí mật vào payload hoặc log.** Thông báo nên chứa dữ liệu tối thiểu; tránh ghi token, session secret hoặc thông tin cá nhân nhạy cảm.

Đặc biệt, việc biết username không có nghĩa là caller có quyền gửi message cho user đó. Kiểm tra quyền phải diễn ra ở tầng nghiệp vụ hoặc bảo mật trước khi gọi template.

## 11. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
|---|---|---|
| Client subscribe đúng nhưng không nhận message | Đối số user không khớp với Principal name của session | Log có kiểm soát `Principal#getName()` khi handshake/handler và so sánh tên truyền vào template |
| Client không nhận vì destination sai | Server truyền `/user/queue/...` thay vì phần destination `/queue/...` | Dùng `/user/queue/...` ở client và `/queue/...` ở server |
| Dùng Principal nhưng bị null | Session chưa được xác thực hoặc Principal chưa được gắn vào WebSocket session | Kiểm tra handshake, cấu hình authentication và chính sách cho phép anonymous |
| Message gửi nhầm người | Dùng username từ payload/header do client kiểm soát | Lấy danh tính từ Principal hoặc tra cứu người nhận bằng nghiệp vụ phía server |
| Chỉ một số tab nhận được message | Các session không có cùng Principal name hoặc session không còn hoạt động | Kiểm tra user registry và danh tính gắn với từng session |
| Message mất khi user offline | User destination không phải hàng đợi lưu bền vững | Lưu notification vào persistence/queue bền vững và gửi sự kiện khi user online |
| Chạy nhiều node nhưng user ở node khác không nhận | User registry không được chia sẻ hoặc broadcast phù hợp | Cấu hình user registry broadcast và unresolved destination broadcast theo kiến trúc |
| Template không có bean để tiêm | Message broker chưa được bật/cấu hình trong context | Kiểm tra `@EnableWebSocketMessageBroker` và cấu hình WebSocket |

Khi debug, kiểm tra lần lượt: Principal của session, username truyền vào, destination server, destination client subscribe, broker prefix và trạng thái kết nối. Không log toàn bộ frame nếu frame có thể chứa thông tin nhạy cảm.

## 12. Bài tập tự kiểm tra

Một ứng dụng có hai người dùng đã đăng nhập là Alice và Bob. Mỗi người đăng ký nhận thông báo tại `/user/queue/notifications`. Sau khi Bob được phân công xử lý một đơn hàng, server cần gửi một notification riêng cho Bob.

Hãy trả lời:

1. Giá trị nào nên truyền vào đối số user của `convertAndSendToUser`?
2. Destination nào được truyền vào template?
3. Client Bob đăng ký destination nào?
4. Có thể lấy username của Bob từ một header `x-user-name` do client Alice gửi không?
5. Nếu Bob đang đăng nhập trên hai tab với cùng Principal name, điều gì có thể xảy ra?

Một lời gọi phù hợp sau khi server đã xác định người được phân công:

```java
messagingTemplate.convertAndSendToUser(
        bobUsername,
        "/queue/notifications",
        new Notification(
                "Đơn hàng mới",
                "Bạn được phân công xử lý ORD-100."
        )
);
```

Đáp án:

1. Tên định danh của Bob trong user registry, thường là `Principal#getName()` của session Bob hoặc username đã được server tra cứu từ nguồn đáng tin cậy.
2. `/queue/notifications`.
3. `/user/queue/notifications`.
4. Không. Alice có thể tự đặt header đó; server phải dùng Principal đã xác thực hoặc dữ liệu phân công phía server.
5. Cả hai session của Bob có thể nhận message theo hành vi phân giải user destination mặc định.

## 13. Ghi nhớ

- `Principal#getName()` cung cấp tên định danh để Spring định tuyến đến các session của user.
- `convertAndSendToUser(userName, destination, payload)` gửi payload đã chuyển đổi đến user destination.
- Client đăng ký `/user/queue/notifications`; server truyền `/queue/notifications` vào template.
- User destination được Spring phân giải thành destination nội bộ cho các session đang hoạt động của user.
- User destination không phải hộp thư offline và không tự thực hiện authorization.
- Dùng Principal đã xác thực; kiểm tra quyền nghiệp vụ trước khi gửi cho user khác.
- Dùng cơ chế persistence riêng nếu thông báo phải được giữ lại khi người nhận offline.

## Tài liệu tham khảo

- Spring Framework Reference — [User Destinations](https://docs.spring.io/spring/reference/web/websocket/stomp/user-destination.html)
- Spring Framework Reference — [STOMP Message Flow](https://docs.spring.io/spring/reference/web/websocket/stomp/message-flow.html)
- Spring Framework Javadoc — [SimpMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/SimpMessagingTemplate.html)
- Spring Framework Javadoc — [UserDestinationMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/UserDestinationMessageHandler.html)
- Spring Framework Javadoc — [Principal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Principal.html)
