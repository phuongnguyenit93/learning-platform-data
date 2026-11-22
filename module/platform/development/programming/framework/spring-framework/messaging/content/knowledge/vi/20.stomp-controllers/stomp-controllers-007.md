# Giá trị trả về, đích mặc định và tùy chỉnh bằng @SendTo

> Phạm vi: Spring Framework STOMP over WebSocket, Java 17+. Các ví dụ giả định ứng dụng đã bật WebSocket message broker và cấu hình prefix như phần dưới. Mã là các đoạn trong một ứng dụng Spring, không phải chương trình Java độc lập có thể chạy bằng javac/java mà không có dependency và cấu hình Spring.

## 1. Một phương thức @MessageMapping trả về điều gì?

Trong STOMP, client gửi frame SEND đến một destination của ứng dụng. Spring định tuyến frame đó đến phương thức được đánh dấu bằng @MessageMapping. Nếu phương thức trả về một giá trị, Spring xử lý giá trị đó như payload của một message mới, chuyển đổi payload bằng MessageConverter phù hợp rồi gửi message qua brokerChannel. Message broker phân phối message đến các client đang SUBSCRIBE destination tương ứng.

Vì vậy, giá trị return không phải là một HTTP response và cũng không phải là một lời gọi trả kết quả trực tiếp cho riêng client gửi SEND. Đó là payload của một message outbound. Client gửi yêu cầu cũng nhận được message nếu nó đang subscribe destination đầu ra; các client khác subscribe cùng destination cũng có thể nhận được.

Luồng điển hình:

1. Client mở kết nối WebSocket đến endpoint STOMP, ví dụ /ws.
2. Client gửi STOMP SEND đến /app/rooms/42/messages.
3. Prefix /app đưa message đến controller; Spring bỏ prefix này khi tìm mapping.
4. @MessageMapping("/rooms/{roomId}/messages") xử lý payload.
5. Giá trị return được chuyển thành payload của message mới và gửi đến brokerChannel.
6. Broker phân phối message đến các subscription khớp destination đầu ra, ví dụ /topic/rooms/42/messages.

## 2. Cấu hình prefix quyết định đường đi

Một cấu hình phổ biến tách destination dành cho controller và destination dành cho broker:

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
        // Client SEND đến /app/... sẽ được định tuyến đến @MessageMapping.
        registry.setApplicationDestinationPrefixes("/app");

        // Broker nhận các destination outbound và các subscription này.
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Ba nhóm prefix có vai trò khác nhau:

| Prefix | Vai trò |
|---|---|
| /app | Prefix inbound dành cho message của ứng dụng; Spring định tuyến đến @MessageMapping. |
| /topic | Destination thường dùng cho message broadcast đến nhiều subscriber. |
| /queue | Destination thường dùng cho message theo hàng đợi hoặc luồng riêng, tùy broker và thiết kế ứng dụng. |

Prefix /app không phải destination mà client thường subscribe để nhận kết quả. /topic và /queue phải khớp với prefix mà broker được cấu hình xử lý. Nếu dùng STOMP broker relay thay cho simple broker, broker bên ngoài cũng phải được cấu hình để nhận các destination cần thiết.

## 3. Destination phản hồi mặc định

Khi phương thức @MessageMapping trả về giá trị và không khai báo @SendTo, Spring tạo destination phản hồi mặc định bằng cách dùng phần destination ứng dụng sau khi bỏ application prefix, rồi thêm prefix phản hồi mặc định /topic.

Ví dụ với cấu hình ở trên:

| Hoạt động | Destination |
|---|---|
| Client SEND | /app/rooms/42/messages |
| Mapping trong controller | /rooms/{roomId}/messages |
| Destination phản hồi mặc định | /topic/rooms/42/messages |
| Client SUBSCRIBE để nhận kết quả | /topic/rooms/42/messages |

Điều này giúp client và server có quy ước rõ ràng: client gửi lệnh vào /app, còn message được phát ra trên /topic. Destination phản hồi được suy ra từ destination inbound thực tế, nên phần biến đường dẫn như 42 vẫn được giữ lại.

Ví dụ controller:

~~~java
import java.time.Instant;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    public record ChatRequest(String text) {}

    public record ChatMessage(String roomId, String text, Instant sentAt) {}

    @MessageMapping("/rooms/{roomId}/messages")
    public ChatMessage publish(
            @DestinationVariable String roomId,
            @Payload ChatRequest request) {

        return new ChatMessage(roomId, request.text(), Instant.now());
    }
}
~~~

Khi client gửi đến /app/rooms/42/messages, Spring lấy roomId là "42", chuyển payload thành ChatRequest, gọi publish rồi gửi ChatMessage đến /topic/rooms/42/messages theo quy tắc mặc định.

Client có thể subscribe và publish bằng STOMP.js như sau:

~~~javascript
client.subscribe("/topic/rooms/42/messages", frame => {
    const message = JSON.parse(frame.body);
    console.log(message);
});

client.publish({
    destination: "/app/rooms/42/messages",
    body: JSON.stringify({ text: "Xin chào" })
});
~~~

Trong ứng dụng thực tế, nên thiết lập subscription trước khi publish nếu client cần nhận ngay message phản hồi. Simple broker không lưu message để phát lại cho subscriber đăng ký sau.

## 4. Spring chuyển đổi giá trị return thành payload

Spring không gửi trực tiếp object Java qua WebSocket. Một MessageConverter phù hợp sẽ chuyển giá trị return thành payload của Spring Message:

- String thường được chuyển thành payload văn bản.
- DTO hoặc record có thể được chuyển thành JSON khi ứng dụng có và cấu hình Jackson-based message converter phù hợp.
- Kiểu dữ liệu khác cần converter tương ứng; nếu không có converter hỗ trợ, việc xử lý return value có thể thất bại.

Ví dụ phương thức trả về ChatMessage ở trên. Client nhận frame STOMP MESSAGE có body JSON tương ứng với các thuộc tính của record, nếu Jackson converter được cấu hình. Không cần tự gọi ObjectMapper để biến DTO thành chuỗi JSON trong controller.

Một phương thức có thể trả về CompletableFuture hoặc CompletionStage để xử lý bất đồng bộ. Spring đợi kết quả hoàn tất rồi xử lý giá trị đó như return value thông thường. Với tác vụ tốn thời gian hoặc có I/O, hãy dùng executor được quản lý phù hợp thay vì mặc định đẩy công việc tùy ý vào common pool.

Nếu phương thức trả về void, không có payload return tự động để Spring phát đi. Khi cần gửi message trong lúc xử lý hoặc gửi từ service, hãy dùng SimpMessagingTemplate.

## 5. Dùng @SendTo để chọn destination khác

@SendTo thuộc package org.springframework.messaging.handler.annotation. Annotation này chỉ định destination outbound cho giá trị return của phương thức. Destination được khai báo phải là destination mà broker có thể xử lý.

Ví dụ gửi kết quả đến một topic cố định:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class AnnouncementController {

    public record AnnouncementRequest(String text) {}
    public record Announcement(String text) {}

    @MessageMapping("/announcements")
    @SendTo("/topic/announcements")
    public Announcement announce(@Payload AnnouncementRequest request) {
        return new Announcement(request.text());
    }
}
~~~

Client gửi đến /app/announcements và subscribe /topic/announcements. Dù destination inbound là /app/announcements, kết quả sẽ đi đến /topic/announcements vì @SendTo đã chỉ định destination cụ thể.

### Gửi cùng payload đến nhiều destination

Thuộc tính value của @SendTo nhận một mảng String. Spring gửi một bản sao message đến từng destination:

~~~java
@MessageMapping("/announcements")
@SendTo({"/topic/announcements", "/topic/audit"})
public Announcement announce(AnnouncementRequest request) {
    return new Announcement(request.text());
}
~~~

Subscriber của /topic/announcements và subscriber của /topic/audit đều nhận payload. Cách này hữu ích khi cùng một sự kiện cần được phân phối cho nhiều nhóm consumer. Hãy cân nhắc quyền truy cập và dữ liệu trong payload vì tất cả subscriber của mỗi destination đều có thể nhận message.

### Khai báo destination mặc định ở cấp class

Có thể đặt @SendTo trên class để dùng chung destination cho các phương thức xử lý message trong class:

~~~java
@Controller
@SendTo("/topic/events")
public class EventController {

    @MessageMapping("/events/created")
    public Event created(EventRequest request) {
        return buildCreatedEvent(request);
    }

    @MessageMapping("/events/important")
    @SendTo("/topic/important-events")
    public Event important(EventRequest request) {
        return buildImportantEvent(request);
    }
}
~~~

Đây là đoạn minh họa rút gọn; Event, EventRequest và các hàm build... đại diện cho DTO và logic nghiệp vụ của ứng dụng. Phương thức created dùng destination ở cấp class là /topic/events. Phương thức important có @SendTo ở cấp method nên destination /topic/important-events ghi đè giá trị ở cấp class. Quy tắc tương tự áp dụng cho @SendToUser khi dùng annotation ở cấp class.

## 6. Phân biệt broadcast, gửi cho một user và gửi chủ động

### @SendTo và @SendToUser

@SendTo thường dùng để phát message đến một destination broker chung. Mọi client đang subscribe destination đó và được phép nhận message đều có thể nhận payload.

@SendToUser dùng để gửi đến user gắn với message inbound. Ví dụ:

~~~java
@MessageMapping("/orders/{orderId}/confirm")
@SendToUser("/queue/order-confirmations")
public OrderConfirmation confirm(
        @DestinationVariable String orderId,
        OrderRequest request,
        Principal principal) {

    return orderService.confirm(orderId, principal.getName());
}
~~~

Client nhận kết quả bằng cách subscribe destination logic /user/queue/order-confirmations. Spring chuyển destination /user thành destination riêng theo user/session, tránh việc các user cùng subscribe một tên queue nhận nhầm message của nhau.

Nếu cùng một user có nhiều WebSocket session, mặc định các session của user đó đang subscribe destination có thể đều nhận message. Đặt broadcast = false trên @SendToUser khi chỉ muốn gửi về session đã gửi message đang được xử lý. User destination thường đi cùng xác thực, nhưng Spring cũng hỗ trợ session chưa gắn Principal; trong trường hợp đó message được giới hạn vào session hiện tại.

### Dùng SimpMessagingTemplate khi cần kiểm soát động

@SendTo phù hợp khi destination cố định và payload chính là kết quả của handler. Nếu destination phụ thuộc vào dữ liệu runtime, cần gửi từ service, cần phát nhiều message ở các thời điểm khác nhau, hoặc handler trả về void, hãy inject SimpMessagingTemplate:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class ChatNotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public ChatNotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishToRoom(String roomId, ChatMessage message) {
        String destination = "/topic/rooms/" + roomId + "/messages";
        messagingTemplate.convertAndSend(destination, message);
    }
}
~~~

convertAndSend nhận destination và object payload; template dùng cơ chế message conversion để tạo message gửi qua broker. Để gửi cho user cụ thể, có thể dùng convertAndSendToUser(username, "/queue/notifications", payload).

@SendTo và @SendToUser là cách khai báo thuận tiện cho việc gửi return value. SimpMessagingTemplate cung cấp quyền kiểm soát trực tiếp hơn. Nếu vừa gửi bằng template vừa return một giá trị có @SendTo, hãy kiểm tra xem có vô tình phát hai message cho cùng một sự kiện hay không.

## 7. Lưu ý về @SubscribeMapping

@SubscribeMapping xử lý STOMP SUBSCRIBE thay vì SEND. Giá trị return của phương thức @SubscribeMapping mặc định được gửi trực tiếp về client đã gửi subscription thông qua clientOutboundChannel, không đi qua brokerChannel để broadcast đến mọi subscriber.

Cách này hữu ích khi client vừa mở màn hình và cần lấy dữ liệu ban đầu một lần. Nếu thêm @SendTo hoặc @SendToUser, Spring chuyển sang gửi kết quả qua broker theo destination đã khai báo. Không nên nhầm hành vi mặc định của @SubscribeMapping với @MessageMapping.

## 8. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Handler chạy nhưng client không thấy message | Client subscribe sai destination | Đối chiếu destination SEND, mapping và destination phản hồi. |
| Client subscribe /app/... nhưng không nhận được | /app thường là prefix inbound cho controller | Subscribe destination broker, ví dụ /topic/... hoặc /queue/.... |
| @SendTo không phát được message | Destination không nằm trong prefix broker xử lý | Kiểm tra enableSimpleBroker hoặc cấu hình broker relay. |
| Client nhận chuỗi thay vì JSON hoặc payload conversion lỗi | MessageConverter không phù hợp hoặc Jackson chưa được cấu hình | Kiểm tra converter và content type của message. |
| Chỉ client gửi lệnh nhận được hoặc không ai nhận | Hiểu nhầm broadcast và user destination | Dùng /topic cho subscriber chung; dùng @SendToUser cho user/session cụ thể. |
| Destination trả về vẫn là mặc định | @SendTo đặt ở class hoặc method chưa đúng handler | Kiểm tra annotation import, phạm vi class/method và method thực sự được gọi. |
| Message xuất hiện hai lần | Handler vừa gọi SimpMessagingTemplate vừa return payload có @SendTo | Chỉ giữ một đường gửi nếu chỉ cần một message. |
| Không có message khi handler hoàn tất | Handler trả về void hoặc không tạo return payload | Return DTO hoặc gửi chủ động bằng SimpMessagingTemplate. |

Khi debug, kiểm tra theo thứ tự: frame SEND của client, application prefix, mapping được chọn, giá trị return, destination outbound, broker prefix và subscription của client. Cần phân biệt lỗi định tuyến với lỗi chuyển đổi payload: handler có thể chạy đúng nhưng client vẫn không nhận được do destination hoặc converter.

## 9. Chọn cách gửi phù hợp

| Nhu cầu | Cách làm |
|---|---|
| Trả payload theo destination inbound đã được ánh xạ | Return giá trị từ @MessageMapping và dùng destination mặc định. |
| Gửi return value đến một topic/queue cố định | Thêm @SendTo ở method. |
| Gửi cùng payload đến nhiều destination | Dùng @SendTo với mảng destination. |
| Chia sẻ một destination mặc định cho nhiều handler | Đặt @SendTo ở cấp class; method-level có thể ghi đè. |
| Gửi phản hồi riêng cho user/session | Dùng @SendToUser và client subscribe /user/.... |
| Chọn destination từ roomId hoặc dữ liệu runtime | Dùng SimpMessagingTemplate.convertAndSend. |
| Gửi từ service hoặc gửi khi handler không return payload | Dùng SimpMessagingTemplate. |
| Trả dữ liệu ban đầu ngay khi client subscribe | Cân nhắc @SubscribeMapping. |

## 10. Tự kiểm tra

1. Với cấu hình application prefix /app và broker prefix /topic, client SEND đến /app/orders/23/changed. Nếu handler trả về object và không có @SendTo, client cần subscribe destination nào?
2. Nếu method có @SendTo({"/topic/a", "/topic/b"}), mỗi destination nhận payload gì?
3. Khi @SendTo ở cấp class là /topic/events nhưng method có @SendTo("/topic/alerts"), kết quả của method đi đến đâu?
4. Khi cần gửi kết quả riêng cho user đã gửi message, nên cân nhắc @SendTo hay @SendToUser?
5. Nếu destination cần được tạo từ roomId lấy trong payload, vì sao SimpMessagingTemplate thường phù hợp hơn @SendTo?

Đáp án: (1) /topic/orders/23/changed. (2) Cùng payload được gửi đến cả hai destination. (3) /topic/alerts. (4) @SendToUser. (5) Giá trị annotation là destination khai báo tĩnh; template cho phép tạo destination tại runtime.

## Tài liệu tham khảo

- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): return value, destination mặc định, @SendTo, @SendToUser và @SubscribeMapping.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): luồng clientInboundChannel, brokerChannel và clientOutboundChannel; ví dụ thay /app bằng /topic.
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): destination /user, @SendToUser và hành vi nhiều session.
- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html): gửi message chủ động bằng SimpMessagingTemplate.
