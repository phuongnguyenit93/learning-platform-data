# User destination khi chưa có xác thực hoặc khi chạy nhiều server

Spring WebSocket hỗ trợ gửi message đến một người dùng thông qua user destination. Client subscribe một destination logic như /user/queue/notifications; server gửi message đến một principal bằng SimpMessagingTemplate hoặc trả về từ controller có @SendToUser. Spring phân giải destination logic thành destination vật lý gắn với session WebSocket tương ứng.

Cơ chế này cần được hiểu theo hai tình huống khác nhau:

- Khi client đã có Principal, Spring có thể gom nhiều session của cùng một người dùng và gửi đến một hoặc tất cả session theo chính sách.
- Khi client chưa được xác thực, Spring vẫn có thể gửi phản hồi về chính session đã gửi request. Muốn chủ động push đến một guest về sau, ứng dụng cần cấp một định danh session/guest do server kiểm soát.
- Khi ứng dụng chạy trên nhiều server, mỗi server chỉ biết các session mà nó đang quản lý. Cần chia sẻ thông tin user registry và chuyển tiếp message chưa phân giải qua một broker dùng chung.

## 1. User destination giải quyết vấn đề gì?

Giả sử Alice mở website trên hai tab. Cả hai tab đều subscribe /user/queue/notifications. Một service gửi thông báo đến Alice:

~~~java
messagingTemplate.convertAndSendToUser(
    "alice",
    "/queue/notifications",
    notification
);
~~~

Ứng dụng không cần tự ghép session ID vào destination. Spring tra cứu các session đang thuộc về user alice và chuyển destination logic thành destination riêng cho từng session. Một dạng destination vật lý có thể trông như /queue/notifications-user{sessionId}; phần hậu tố cụ thể do Spring tạo và quản lý.

Client luôn subscribe destination logic:

~~~javascript
client.subscribe("/user/queue/notifications", (frame) => {
  const notification = JSON.parse(frame.body);
  renderNotification(notification);
});
~~~

Client không cần biết session ID hay destination vật lý. Không nên hard-code tên destination sau khi Spring phân giải, vì nó phụ thuộc session và cơ chế nội bộ của framework.

User destination khác với topic công khai. Một message gửi đến /topic/announcements được định tuyến đến các subscriber của topic đó. Một message gửi đến /user/queue/notifications được phân giải dựa trên danh tính người dùng và các session đang hoạt động của họ.

## 2. Cấu hình user destination cơ bản

Ví dụ cấu hình một ứng dụng Spring WebSocket dùng Simple Broker:

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
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }
}
~~~

Các prefix có vai trò khác nhau:

- /app: message từ client được chuyển đến các handler ứng dụng như @MessageMapping.
- /topic và /queue: destination do broker xử lý.
- /user: prefix logic để Spring nhận diện và phân giải user destination.
- /ws: endpoint HTTP được dùng để bắt đầu kết nối WebSocket/STOMP.

Simple Broker phù hợp với ví dụ hoặc triển khai một node có yêu cầu đơn giản. Nó giữ subscription trong bộ nhớ của ứng dụng và không chia sẻ trạng thái giữa nhiều instance. Cấu hình nhiều server sẽ được trình bày ở phần sau.

## 3. Gửi đến người dùng đã xác thực

Trong luồng WebSocket thông thường, Spring sử dụng Principal đã gắn với HTTP handshake để xác định người dùng. Principal này thường đến từ cơ chế xác thực HTTP của ứng dụng. Khi message STOMP được xử lý, controller có thể nhận Principal làm tham số.

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class PrivateMessageController {

    @MessageMapping("/profile.refresh")
    @SendToUser("/queue/replies")
    public ProfileReply refresh(ProfileRequest request, Principal principal) {
        return new ProfileReply(
            principal.getName(),
            request.requestId(),
            "REFRESH_ACCEPTED"
        );
    }

    public record ProfileRequest(String requestId) {}

    public record ProfileReply(
        String username,
        String requestId,
        String status
    ) {}
}
~~~

Client gửi request đến /app/profile.refresh và subscribe /user/queue/replies. Với Principal đã xác thực, @SendToUser mặc định gửi đến tất cả session đang hoạt động gắn với cùng người dùng. Nếu Alice đang mở hai tab, cả hai tab có thể nhận phản hồi.

Để chỉ gửi phản hồi về session đã gửi request, đặt broadcast=false:

~~~java
@MessageMapping("/profile.refresh")
@SendToUser(value = "/queue/replies", broadcast = false)
public ProfileReply refreshCurrentTab(ProfileRequest request) {
    return new ProfileReply(
        request.requestId(),
        "REFRESH_ACCEPTED"
    );
}

public record ProfileRequest(String requestId) {}

public record ProfileReply(String requestId, String status) {}
~~~

Hai cách dùng có ý nghĩa khác nhau:

| Cấu hình | Phạm vi nhận |
|---|---|
| @SendToUser("/queue/replies") | Mọi session của Principal hiện tại |
| @SendToUser(value="/queue/replies", broadcast=false) | Chỉ session gửi message đang được xử lý |

Hãy chọn theo mục đích nghiệp vụ. Phản hồi xác nhận một thao tác trên tab hiện tại thường phù hợp với broadcast=false. Thông báo thay đổi hồ sơ hoặc trạng thái tài khoản có thể cần gửi đến mọi session của người dùng.

## 4. Gửi message chủ động từ service

Khi service cần gửi notification mà không nằm trong luồng trả về của một @MessageMapping handler, dùng SimpMessagingTemplate.

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String principalName, Notification event) {
        messagingTemplate.convertAndSendToUser(
            principalName,
            "/queue/notifications",
            event
        );
    }

    public record Notification(String eventId, String message) {}
}
~~~

Giá trị principalName phải khớp với Principal.getName() của người nhận. Trong ứng dụng thực tế, service nên lấy tên principal từ ngữ cảnh đã xác thực hoặc từ dữ liệu nghiệp vụ đã được kiểm tra. Không nhận một username tùy ý từ payload của client rồi gửi message đến tài khoản đó; điều này có thể tạo lỗ hổng gửi message chéo người dùng.

Client subscribe:

~~~javascript
client.subscribe("/user/queue/notifications", (frame) => {
  const event = JSON.parse(frame.body);
  showToast(event.message);
});
~~~

convertAndSendToUser gửi đến các session đang được registry liên kết với principal. Lời gọi này không chứng minh trình duyệt đã nhận frame hoặc callback đã xử lý xong. Nếu nghiệp vụ cần xác nhận, hãy định nghĩa ACK riêng và lưu trạng thái tương ứng.

## 5. User destination khi chưa có xác thực

Một kết nối không có Principal vẫn có thể cần nhận phản hồi riêng, ví dụ:

- Trang đăng nhập gửi yêu cầu kiểm tra trạng thái trước khi người dùng đăng nhập.
- Một guest gửi yêu cầu xem trước dữ liệu công khai.
- Client gửi một command tạm thời và cần nhận kết quả trên đúng tab đó.
- Một thiết bị chưa đăng nhập cần nhận kết quả của thao tác vừa gửi.

Với một message đến từ chính session đó, có thể dùng @SendToUser với broadcast=false:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class GuestMessageController {

    @MessageMapping("/guest.preview")
    @SendToUser(value = "/queue/replies", broadcast = false)
    public PreviewReply preview(PreviewRequest request) {
        return new PreviewReply(
            request.requestId(),
            "PREVIEW_READY"
        );
    }

    public record PreviewRequest(String requestId) {}

    public record PreviewReply(String requestId, String status) {}
}
~~~

Client subscribe /user/queue/replies trước khi gửi message đến /app/guest.preview. Spring có thể định tuyến phản hồi về session gửi request dù session chưa có người dùng đã xác thực. Với anonymous session, @SendToUser được xử lý theo phạm vi session, tương đương broadcast=false; ghi rõ broadcast=false trong code giúp thể hiện chủ đích và tránh nhầm lẫn khi đọc.

Điểm quan trọng là session chưa xác thực không có một username đáng tin cậy để service dùng làm định danh người nhận lâu dài. Vì vậy:

- Phản hồi trực tiếp cho request đang xử lý có thể dùng @SendToUser(broadcast=false).
- Không dùng username do client tự khai báo để gọi convertAndSendToUser.
- Không xem session ID là danh tính người dùng đã xác thực.
- Nếu cần gửi message chủ động cho guest sau khi request ban đầu kết thúc, ứng dụng cần quản lý một định danh guest/session do server cấp và gắn với WebSocket session.

## 6. Cấp định danh guest do server kiểm soát

Một số ứng dụng cần gửi notification cho guest mà không yêu cầu tài khoản. Có thể gắn một Principal tạm thời cho mỗi WebSocket session. Principal này không chứng minh danh tính thật; nó chỉ là khóa định tuyến do server tạo.

Ví dụ handshake handler giữ Principal có sẵn nếu request đã được xác thực, còn kết nối guest được cấp một ID ngẫu nhiên:

~~~java
import java.security.Principal;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.server.ServerHttpRequest;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.support.DefaultHandshakeHandler;

public class GuestAwareHandshakeHandler extends DefaultHandshakeHandler {

    @Override
    protected Principal determineUser(
            ServerHttpRequest request,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes) {

        Principal authenticated = request.getPrincipal();
        if (authenticated != null) {
            return authenticated;
        }

        String guestId = "guest-" + UUID.randomUUID();
        return () -> guestId;
    }
}
~~~

Đăng ký handler trên endpoint:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
        .setHandshakeHandler(new GuestAwareHandshakeHandler());
}
~~~

Sau handshake, service có thể dùng tên Principal guest đã được gắn với session:

~~~java
messagingTemplate.convertAndSendToUser(
    guestPrincipalName,
    "/queue/notifications",
    guestNotification
);
~~~

guestPrincipalName ở đây phải được lấy từ Principal hoặc từ mapping phía server, không phải từ một trường username tùy ý trong message của client.

Một UUID mới sau mỗi lần kết nối có nghĩa guest identity chỉ tồn tại cho session đó. Khi reconnect, client sẽ có ID mới. Nếu sản phẩm cần guest giữ trạng thái qua reconnect, hãy dùng một token guest ngẫu nhiên có chữ ký hoặc một mã opaque được server cấp, xác minh token trước handshake rồi ánh xạ nó thành Principal. Không dùng email, số điện thoại hoặc ID do client tự chọn làm khóa định tuyến nếu chưa có xác minh và kiểm soát quyền truy cập.

Định danh guest cũng phải được giới hạn quyền. Một guest Principal không nên tự động có quyền đọc dữ liệu riêng tư, subscribe destination của người dùng khác hoặc gửi message đến destination quản trị.

## 7. Vì sao cấu hình một server không đủ khi chạy nhiều server?

Giả sử hệ thống có hai instance:

- Alice kết nối WebSocket đến Server A.
- Một tác vụ nền chạy trên Server B gọi convertAndSendToUser("alice", ...).
- Server B không có session của Alice trong user registry cục bộ.

Nếu chỉ dùng registry trong bộ nhớ của từng node, Server B có thể không phân giải được user destination. Dù cả hai node cùng trỏ đến một broker, broker cũng không tự biết principal alice đang kết nối ở instance nào nếu ứng dụng không chia sẻ thông tin định tuyến user.

Một hệ thống nhiều node cần hai khả năng:

1. Chia sẻ thông tin user/session đang kết nối giữa các node để node gửi có thể tìm ra nơi nhận.
2. Chuyển tiếp message user destination chưa được node hiện tại phân giải để node khác có cơ hội xử lý.

Spring hỗ trợ hai broadcast destination cho việc này: user registry broadcast và unresolved user destination broadcast.

## 8. Cấu hình nhiều server với broker relay

Các instance cần dùng chung một STOMP broker bên ngoài, chẳng hạn broker hỗ trợ STOMP relay. Mỗi instance cấu hình cùng broker prefixes và hai broadcast destination.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.config.StompBrokerRelayRegistration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class ClusterWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");

        StompBrokerRelayRegistration relay =
            registry.enableStompBrokerRelay("/topic", "/queue");

        relay.setUserRegistryBroadcast("/topic/simp-user-registry");
        relay.setUserDestinationBroadcast("/topic/unresolved-user");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }
}
~~~

Hai destination broadcast có nhiệm vụ riêng:

- **userRegistryBroadcast** phát thông tin registry của node để các node khác biết những user/session đang kết nối ở đâu. Spring kết hợp thông tin cục bộ và thông tin nhận từ các node khác để phân giải user destination.
- **userDestinationBroadcast** chuyển tiếp message mà node hiện tại không phân giải được đến các node khác. Node đang giữ session của người nhận có thể phân giải message đó thành destination vật lý tương ứng.

Các node phải dùng cùng broker và thống nhất tên broadcast destination. Broker relay phải được cấu hình host, port, thông tin đăng nhập và quyền truy cập phù hợp với môi trường. Thông tin bí mật nên lấy từ cấu hình bảo mật hoặc secret store, không hard-code trong source code.

Hai broadcast destination là kênh nội bộ giữa các application node. Không cấp quyền subscribe hoặc publish tùy ý cho browser client vào /topic/simp-user-registry hay /topic/unresolved-user. Hãy cấu hình broker ACL và Spring Security để bảo vệ chúng.

## 9. Luồng định tuyến khi user kết nối ở node khác

Giả sử Alice đang kết nối với Server B, nhưng một nghiệp vụ trên Server A muốn gửi thông báo:

1. Alice mở WebSocket đến Server B và subscribe /user/queue/notifications.
2. Server B ghi nhận Principal và session trong user registry cục bộ.
3. Thông tin registry của Server B được phát qua userRegistryBroadcast.
4. Server A nhận bản cập nhật và có thể biết Alice đang có session trên Server B.
5. Server A gửi message đến logical user destination của Alice.
6. User destination handler phân giải message thành destination riêng cho session của Alice.
7. Broker relay chuyển message qua broker dùng chung đến kết nối do Server B quản lý.
8. Server B gửi STOMP MESSAGE đến client.

Nếu Server A chưa có thông tin đủ để phân giải người nhận, userDestinationBroadcast cho phép phát message chưa phân giải để các node khác thử xử lý. Nếu không node nào có session phù hợp, message không có người nhận. User destination không tự tạo một mailbox bền vững cho người dùng offline.

Thông tin registry được trao đổi giữa các node có thể có độ trễ. Vì vậy, kết nối vừa tạo hoặc vừa đóng có thể tạo ra một khoảng thời gian registry chưa phản ánh trạng thái mới nhất. Với thông báo nghiệp vụ quan trọng, hãy lưu event ở database/outbox và có cơ chế retry hoặc đồng bộ lại thay vì coi broadcast là bảo đảm giao hàng cuối cùng.

## 10. Phân biệt Simple Broker, broker relay và user registry

| Thành phần | Vai trò | Giới hạn cần nhớ |
|---|---|---|
| Spring Simple Broker | Quản lý subscription và định tuyến trong một ứng dụng | Trạng thái trong bộ nhớ; không chia sẻ subscription giữa các server |
| STOMP broker relay | Chuyển message từ Spring đến broker bên ngoài và ngược lại | Cần vận hành broker, cấu hình kết nối và quyền truy cập |
| SimpUserRegistry | Theo dõi Principal và session mà node biết | Registry cục bộ không tự biết session của node khác |
| userRegistryBroadcast | Chia sẻ thông tin user/session giữa các node | Thông tin phân tán có độ trễ |
| userDestinationBroadcast | Chuyển tiếp user destination mà node hiện tại không phân giải được | Không tạo lưu trữ bền vững cho user offline |

Không thể đạt định tuyến user destination xuyên nhiều instance chỉ bằng cách đặt các instance sau một load balancer. Sticky session có thể giữ kết nối của một client trên cùng node, nhưng không giúp một node khác biết session nằm ở đâu khi nó gửi notification. Hệ thống vẫn cần cơ chế định tuyến hoặc một tầng lưu trữ/dispatch được thiết kế rõ ràng.

## 11. Bảo mật và các lỗi thiết kế thường gặp

**Dùng tên người dùng do client gửi lên.** Client có thể giả mạo username trong payload. Hãy lấy danh tính từ Principal đã xác thực hoặc guest identity do server cấp.

**Nhầm broadcast=true với gửi riêng một tab.** Một người dùng có thể có nhiều session trên nhiều thiết bị. Dùng broadcast=false cho phản hồi chỉ thuộc request/session hiện tại.

**Dùng @SendToUser mặc định cho anonymous request.** Anonymous session không có danh tính user ổn định. Hãy ghi rõ broadcast=false để phản hồi chỉ quay về session gửi request.

**Dùng convertAndSendToUser cho guest không có Principal.** Service không có username đáng tin cậy để tra cứu. Hãy dùng phản hồi theo session hoặc cấp guest Principal/mapping do server quản lý.

**Dùng Simple Broker cho nhiều node.** Mỗi node có registry và subscription riêng. Dùng broker relay với broker dùng chung và cấu hình broadcast cần thiết.

**Cho browser truy cập broadcast destination nội bộ.** User registry và unresolved message chứa thông tin định tuyến nội bộ. Bảo vệ destination bằng ACL và authorization.

**Cho rằng user destination bảo đảm giao hàng.** Nếu user offline, không có session để phân giải. Lưu event cần thiết và cung cấp cơ chế đồng bộ/replay.

**Không xử lý nhiều session.** Một tài khoản có thể mở nhiều tab hoặc thiết bị. Xác định rõ gửi đến mọi session hay chỉ session đã gửi request.

**Không xử lý reconnect.** Session ID mới có thể được tạo sau reconnect; guest identity ngẫu nhiên theo session cũng thay đổi. Cần đăng ký lại subscription và đồng bộ dữ liệu cần thiết.

## 12. Kiểm thử các tình huống quan trọng

Một bộ integration test nên kiểm tra các trường hợp sau:

1. User đã xác thực subscribe /user/queue/notifications và nhận được message gửi bằng convertAndSendToUser.
2. Cùng một user mở hai session; broadcast mặc định gửi đến cả hai.
3. Handler dùng broadcast=false; chỉ session phát request nhận phản hồi.
4. Anonymous client gửi request và nhận phản hồi qua @SendToUser(broadcast=false).
5. Anonymous client không thể chọn Principal name hoặc username của người khác bằng payload.
6. Guest Principal do server cấp chỉ nhận được notification gắn với guest session tương ứng.
7. User kết nối ở Server B nhưng message được phát từ Server A; registry broadcast giúp tìm đúng node.
8. Node không phân giải được user destination phát unresolved message và node có session xử lý được.
9. User disconnect trước khi gửi; hệ thống ghi nhận không có session nhận và dữ liệu quan trọng vẫn có thể đồng bộ lại.
10. Reconnect tạo session mới; client subscribe lại và khôi phục trạng thái theo hợp đồng ứng dụng.

Trong test đa node, phải chạy ít nhất hai application instance cùng broker relay thực sự. Một unit test trên một Simple Broker không chứng minh user registry broadcast hoặc unresolved destination broadcast hoạt động giữa các server.

## 13. Checklist chẩn đoán

Khi user không nhận được message, kiểm tra theo thứ tự:

- Client có subscribe đúng logical destination /user/queue/... trước khi server gửi không?
- Handshake có Principal không? Principal.getName() có đúng giá trị mà service truyền vào convertAndSendToUser không?
- Message có được gửi đến đúng destination phụ, ví dụ /queue/notifications, không thêm /user vào tham số destination của convertAndSendToUser không?
- Nếu anonymous, message có được trả về từ inbound handler với broadcast=false không?
- Nếu guest cần nhận push chủ động, guest Principal/session mapping có còn hiệu lực và do server kiểm soát không?
- Ứng dụng có đang chạy nhiều node nhưng vẫn dùng Simple Broker không?
- Tất cả node có dùng chung broker relay và cùng broadcast destination không?
- Broker ACL có cho phép các application node publish/subscribe các destination nội bộ không?
- User registry có chứa session đang hoạt động không? Có độ trễ do connect/disconnect hoặc reconnect không?
- Có event ID và log theo từng chặng để phân biệt lỗi phân giải destination với lỗi transport/client callback không?

User destination giúp ứng dụng gửi message theo danh tính hoặc session thay vì tự quản lý destination vật lý. Với anonymous session, hãy giới hạn phản hồi vào session hoặc cấp guest identity do server quản lý. Với nhiều server, hãy kết hợp broker relay, user registry broadcast và unresolved destination broadcast; các thông báo cần bảo đảm phải có lưu trữ và cơ chế khôi phục riêng.