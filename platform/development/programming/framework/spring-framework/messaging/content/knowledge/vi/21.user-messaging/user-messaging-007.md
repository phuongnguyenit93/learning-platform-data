# Broadcast và lựa chọn một phiên hoặc nhiều phiên của cùng người dùng

> Phạm vi: Spring Framework STOMP over WebSocket, Java 17+. Bài này tập trung vào user destination, cách Spring gửi message đến nhiều WebSocket session của cùng một user và cách giới hạn phản hồi vào session đã gửi yêu cầu. Các đoạn Java là code tích hợp trong ứng dụng Spring đã cấu hình STOMP, không phải chương trình độc lập.

## 1. “Gửi tới người dùng” nghĩa là gì?

Trong ứng dụng WebSocket, một người dùng có thể mở nhiều kết nối đồng thời: nhiều tab trình duyệt, nhiều cửa sổ, máy tính và điện thoại. Mỗi kết nối WebSocket/STOMP có session riêng, nhưng các session đã xác thực có thể cùng đại diện cho một tài khoản.

Spring hỗ trợ **user destination** để gửi message đến các session gắn với một user. Client đăng ký một destination logic, ví dụ:

~~~javascript
stompClient.subscribe("/user/queue/notifications", frame => {
    const notification = JSON.parse(frame.body);
    console.log(notification);
});
~~~

Client không cần biết username hoặc destination vật lý của từng session. Khi gửi message, server chỉ định user và destination đích. Spring phân giải user destination thành một hoặc nhiều destination dành riêng cho session đang kết nối.

Điểm quan trọng: “broadcast tới user” nghĩa là gửi tới các session của **một user cụ thể**. Nó không có nghĩa là phát cho mọi user đang kết nối như một topic công khai.

## 2. Cấu hình user destination

Một cấu hình STOMP thường có application prefix cho message gửi vào controller, broker prefix cho message được phân phối, và user destination prefix:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
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

`/user` là prefix mặc định của Spring cho user destination; khai báo tường minh giúp cấu hình dễ đọc. `/app` định tuyến message inbound đến `@MessageMapping`. `/topic` và `/queue` là các prefix broker xử lý.

Một client subscribe `/user/queue/notifications`. Khi server gửi đến user `alice` với destination `/queue/notifications`, Spring xử lý user destination và chuyển message đến destination thực tế của các session thuộc `alice`. Các destination nội bộ có thể chứa session identifier; client không cần tạo hay đoán các tên đó.

Luồng khái quát:

~~~text
Client SUBSCRIBE /user/queue/notifications
                 |
                 v
        User destination handler
                 |
          session A, session B

Server gửi đến user "alice"
                 |
                 v
 /user/alice/queue/notifications
                 |
          User destination resolver
                 |
       +---------+---------+
       |                   |
  destination A       destination B
       |                   |
    session A           session B
~~~

Sơ đồ trên thể hiện trường hợp gửi đến tất cả session của user. Nếu giới hạn vào session nguồn, Spring chỉ tạo đích cho session đã gửi message inbound.

## 3. @SendToUser: gửi kết quả về các session của user

`@SendToUser` được dùng trên phương thức xử lý message để gửi giá trị return đến user gắn với message inbound. Import đúng là:

~~~java
import org.springframework.messaging.simp.annotation.SendToUser;
~~~

Ví dụ, giả sử người dùng đã đăng nhập và Spring có thể xác định `Principal` của kết nối:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class PrivateReplyController {

    public record PingRequest(String text) {}
    public record PrivateReply(String username, String text) {}

    @MessageMapping("/account/ping")
    @SendToUser("/queue/replies")
    public PrivateReply reply(PingRequest request, Principal principal) {
        return new PrivateReply(
            principal.getName(),
            "Server received: " + request.text()
        );
    }
}
~~~

Client gửi đến `/app/account/ping`. Spring bỏ application prefix `/app` để tìm `@MessageMapping("/account/ping")`. Giá trị return được chuyển thành payload message và gửi đến user destination `/queue/replies`.

Client subscribe `/user/queue/replies` để nhận phản hồi. Không thêm username vào destination subscribe và không viết `/user/{username}` trong giá trị của `@SendToUser`; Spring xử lý phần đó.

### Hành vi mặc định: broadcast = true

Thuộc tính `broadcast` của `@SendToUser` mặc định là `true`. Vì vậy, khi user đã xác thực có nhiều session đang kết nối, message được gửi đến tất cả session của user đó có đăng ký destination tương ứng.

Ví dụ, cùng một tài khoản `alice` đang mở:

- Tab A trên máy tính và đã subscribe `/user/queue/replies`.
- Tab B trên cùng máy tính và đã subscribe `/user/queue/replies`.
- Ứng dụng trên điện thoại và đã subscribe `/user/queue/replies`.

Khi một session của `alice` gửi `/app/account/ping`, cả ba session có subscription phù hợp đều có thể nhận message phản hồi. Điều kiện “đã subscribe” rất quan trọng: Spring không tự tạo subscription cho client và broker không gửi lại message cũ cho một session đăng ký sau.

Đây là broadcast trong phạm vi một user. Các tài khoản khác, chẳng hạn `bob`, không nhận message chỉ vì họ cũng đang subscribe `/user/queue/replies`; Spring phân giải đích theo danh tính user.

### Chỉ gửi về session đã gửi yêu cầu: broadcast = false

Nếu phản hồi chỉ dành cho tab hoặc thiết bị vừa gửi message, đặt `broadcast = false`:

~~~java
@MessageMapping("/account/ping-current-session")
@SendToUser(value = "/queue/replies", broadcast = false)
public PrivateReply replyOnlyToOriginatingSession(
        PingRequest request,
        Principal principal) {

    return new PrivateReply(
        principal.getName(),
        "Reply for the session that sent this request"
    );
}
~~~

Giả sử Tab A và Tab B cùng đăng nhập bằng tài khoản `alice`. Nếu Tab A gửi message đến `/app/account/ping-current-session`, chỉ session của Tab A nhận phản hồi. Tab B vẫn có thể subscribe cùng `/user/queue/replies`, nhưng không nhận message của lần xử lý này.

`broadcast = false` có nghĩa là **chỉ session đã gửi message inbound đang được xử lý**. Nó không phải tham số để chọn tùy ý một session khác bằng session ID. Nếu một service cần chủ động nhắm đến một session bất kỳ, ứng dụng cần thiết kế cơ chế định tuyến session riêng và quản lý vòng đời session phù hợp.

Khi user chỉ có một session, `broadcast = true` và `broadcast = false` thường cho kết quả quan sát giống nhau. Khác biệt chỉ rõ khi cùng user có nhiều session.

## 4. Bảng so sánh các cách gửi

| Cách gửi | Phạm vi người nhận | Dùng khi |
|---|---|---|
| `@SendTo("/topic/events")` | Mọi subscriber được phép trên topic | Phát sự kiện chung cho nhiều user. |
| `@SendToUser("/queue/replies")` | Mọi session phù hợp của user gửi message; mặc định `broadcast = true` | Đồng bộ phản hồi hoặc trạng thái tới các thiết bị của cùng user. |
| `@SendToUser(value = "/queue/replies", broadcast = false)` | Chỉ session đã gửi message inbound | Phản hồi riêng cho tab hoặc thiết bị đang thao tác. |
| `SimpMessagingTemplate.convertAndSendToUser(...)` | Các session của username được chỉ định | Gửi chủ động từ service hoặc tác vụ nền đến một user. |

Không dùng `/topic` chỉ vì muốn gửi tới nhiều tab của cùng một user. `/topic` phân phối theo subscription của destination chung; user destination phân phối theo danh tính user và các session của user đó.

## 5. Gửi chủ động bằng SimpMessagingTemplate

Không phải message nào cũng được gửi từ return value của `@MessageMapping`. Service có thể cần phát thông báo sau khi xử lý nghiệp vụ, sau khi lưu dữ liệu hoặc khi một tác vụ nền hoàn tất. Khi đó, dùng `SimpMessagingTemplate`:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserNotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public UserNotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String username, Notification notification) {
        messagingTemplate.convertAndSendToUser(
            username,
            "/queue/notifications",
            notification
        );
    }

    public record Notification(String title, String message) {}
}
~~~

`convertAndSendToUser(username, destination, payload)` nhận tên user, destination tương đối của user và payload. Với cấu hình user destination thông thường, message được phân giải đến các session đang hoạt động của username đó có đăng ký destination tương ứng.

Ví dụ, nếu `username` là `alice`, client của `alice` vẫn subscribe `/user/queue/notifications`. Service không gửi trực tiếp đến `/user/alice/queue/notifications`; template tạo user destination để Spring xử lý.

`convertAndSendToUser` hữu ích khi gửi chủ động và mặc định hướng đến các session của user. Nó không có tham số `broadcast=false` tương tự annotation. Nếu cần giới hạn phản hồi vào session đã gửi message inbound, `@SendToUser(..., broadcast = false)` là cách khai báo trực tiếp trong handler. Nếu cần chọn một session cụ thể từ service, hãy xây dựng một chiến lược session-aware riêng thay vì tự ghép tên destination nội bộ mà Spring tạo ra.

Tên user truyền cho template phải khớp với danh tính mà ứng dụng gắn vào `Principal`. Không nên lấy username đích từ một trường payload do client tùy ý gửi rồi dùng nó để định tuyến thông báo riêng tư; hãy xác định người nhận từ ngữ cảnh xác thực và quy tắc nghiệp vụ phía server.

## 6. Trường hợp session chưa xác thực

Với kết nối đã xác thực, Spring dùng `Principal` để nhóm nhiều session thuộc cùng một user. Với session ẩn danh không có `Principal`, `@SendToUser` vẫn có thể gửi phản hồi, nhưng Spring coi session hiện tại là đích và chỉ gửi về session đã gửi message. Không có danh tính user chung để broadcast đến các tab hoặc thiết bị khác.

Vì vậy, nếu ứng dụng mong muốn đồng bộ nhiều thiết bị của cùng một tài khoản, cần bảo đảm quá trình xác thực WebSocket/STOMP gắn cùng một danh tính `Principal` vào các kết nối của tài khoản đó. Nếu mỗi kết nối thiếu Principal hoặc được gắn danh tính khác nhau, Spring không thể tự suy ra chúng thuộc cùng một user.

Cũng cần phân biệt user với session:

- **User** là danh tính ứng dụng, thường được biểu diễn bởi `Principal.getName()`.
- **Session** là một kết nối WebSocket/STOMP cụ thể.
- Một user đã đăng nhập có thể sở hữu nhiều session.
- Một session chưa xác thực vẫn có thể nhận phản hồi riêng của session qua cơ chế user destination, nhưng không có broadcast theo tài khoản.

## 7. Ví dụ đầy đủ về hai lựa chọn

Controller sau cung cấp hai endpoint: một endpoint gửi về mọi session của user, một endpoint chỉ gửi về session nguồn.

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class SessionReplyController {

    public record Request(String action) {}
    public record Reply(String user, String message) {}

    // Mặc định broadcast = true: gửi tới mọi session của user.
    @MessageMapping("/session/all")
    @SendToUser("/queue/session-replies")
    public Reply replyToAllSessions(Request request, Principal principal) {
        return new Reply(
            principal.getName(),
            "Action processed: " + request.action()
        );
    }

    // broadcast = false: chỉ gửi về session đã gửi message này.
    @MessageMapping("/session/current")
    @SendToUser(value = "/queue/session-replies", broadcast = false)
    public Reply replyToCurrentSession(Request request, Principal principal) {
        return new Reply(
            principal.getName(),
            "Action processed in the originating session: " + request.action()
        );
    }
}
~~~

Client ở mỗi tab hoặc thiết bị subscribe cùng destination logic:

~~~javascript
stompClient.subscribe("/user/queue/session-replies", frame => {
    const reply = JSON.parse(frame.body);
    console.log(reply.message);
});
~~~

Tab A gửi đến `/app/session/all`: các session của cùng user đã subscribe nhận cùng kết quả. Tab A gửi đến `/app/session/current`: chỉ Tab A nhận kết quả của lần gọi đó.

Hai endpoint trả về cùng kiểu DTO và dùng cùng destination subscribe. Quyết định số session nhận message nằm ở `broadcast`, không nằm ở cấu trúc payload.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không session nào nhận được message | Client subscribe `/queue/...` thay vì `/user/queue/...` | Subscribe destination logic bắt đầu bằng `/user`. |
| Chỉ tab gửi yêu cầu nhận được | `broadcast = false` hoặc kết nối không có Principal | Kiểm tra giá trị `broadcast` và xác thực STOMP. |
| Tất cả thiết bị cùng tài khoản nhận phản hồi ngoài ý muốn | `broadcast` mặc định là `true` | Đặt `broadcast = false` nếu chỉ cần session nguồn. |
| Các user khác cũng nhận message | Đang gửi đến topic chung thay vì user destination | Dùng `@SendToUser` hoặc `convertAndSendToUser`. |
| Một tài khoản có nhiều kết nối nhưng chỉ được xem là một user khác nhau | Principal giữa các kết nối không nhất quán | Kiểm tra cách xác thực và giá trị `Principal.getName()`. |
| `convertAndSendToUser` không định tuyến đến ai | Username không khớp danh tính trong user registry hoặc không có session phù hợp | Dùng đúng username từ ngữ cảnh xác thực; kiểm tra session và subscription. |
| Service muốn gửi cho một tab cụ thể nhưng các tab đều nhận | Đang dùng `convertAndSendToUser`, vốn gửi theo user | Thiết kế định tuyến session riêng; không nhầm nó với `broadcast = false` trong handler. |
| Client kết nối sau không thấy thông báo trước đó | Broker không lưu trữ message để phát lại | Lưu trạng thái/sự kiện cần thiết trong ứng dụng và cung cấp API đồng bộ khi client kết nối. |

Khi debug, kiểm tra theo thứ tự:

1. Kết nối STOMP đã được xác thực chưa và `Principal.getName()` là gì?
2. Các tab/thiết bị có thực sự cùng một user identity không?
3. Client có subscribe `/user/queue/...` trước khi message được gửi không?
4. Handler có dùng `@SendToUser` đúng destination không?
5. `broadcast` đang là `true` hay `false`?
6. Nếu gửi từ service, username trong `convertAndSendToUser` có khớp với user registry không?

## 9. Quy tắc chọn nhanh

- Muốn mọi subscriber của một topic nhận message: dùng `@SendTo`.
- Muốn tất cả session của một tài khoản nhận phản hồi: dùng `@SendToUser` với mặc định `broadcast = true`.
- Muốn chỉ tab/thiết bị vừa gửi yêu cầu nhận phản hồi: dùng `@SendToUser(..., broadcast = false)`.
- Muốn service gửi thông báo đến một tài khoản: dùng `SimpMessagingTemplate.convertAndSendToUser`.
- Muốn nhắm đến một session tùy chọn từ tác vụ nền: thiết kế định tuyến session riêng; `broadcast = false` chỉ xác định session nguồn của message đang được xử lý.

## 10. Tự kiểm tra

1. Một user đăng nhập trên laptop và điện thoại. Cả hai session subscribe `/user/queue/alerts`. Handler dùng `@SendToUser("/queue/alerts")`. Có bao nhiêu session có thể nhận message?
2. Cùng tình huống trên, handler dùng `@SendToUser(value = "/queue/alerts", broadcast = false)` và laptop gửi yêu cầu. Session nào nhận phản hồi?
3. `broadcast = false` có cho phép server chọn một session bất kỳ bằng ID không?
4. Client nên subscribe `/user/queue/alerts` hay `/user/alice/queue/alerts`?
5. Một session không có Principal gửi message đến handler có `@SendToUser`. Spring có thể gửi phản hồi về đâu?

Đáp án:

1. Cả laptop và điện thoại, nếu cả hai session đang hoạt động và đã subscribe destination đó.
2. Chỉ session laptop đã gửi yêu cầu.
3. Không. Nó giới hạn phản hồi vào session nguồn của message inbound.
4. `/user/queue/alerts`; Spring tự phân giải username và session.
5. Về session ẩn danh đã gửi message; không có broadcast theo danh tính tài khoản.

## Tài liệu tham khảo

- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): user destination, `@SendToUser`, broadcast đến nhiều session và session ẩn danh.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): cách xử lý return value và các annotation gửi message từ controller.
- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html): gửi message chủ động qua `SimpMessagingTemplate`.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): luồng message qua các channel của Spring STOMP.
