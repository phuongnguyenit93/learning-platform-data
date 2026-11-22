# Ranh giới giữa hoàn tất controller và client nhận được kết quả

Trong ứng dụng Spring dùng WebSocket và STOMP, một phương thức controller kết thúc không có nghĩa client đã nhận hoặc xử lý được thông điệp. Giữa hai thời điểm đó còn nhiều bước: Spring xử lý giá trị trả về, chuyển đổi payload, gửi thông điệp đến message broker, broker tìm các subscription phù hợp, server ghi STOMP frame lên kết nối WebSocket và client xử lý frame vừa nhận.

Khi thiết kế API realtime, cần gọi đúng tên từng mốc. “Controller đã chạy xong”, “server đã publish”, “broker đã xử lý”, “client đã nhận” và “nghiệp vụ phía client đã hoàn tất” là những trạng thái khác nhau.

## 1. Sáu mốc hoàn tất cần phân biệt

| Mốc | Điều đã xảy ra | Điều chưa thể kết luận |
|---|---|---|
| Phương thức controller trả về | Phần thân phương thức đã chạy xong và tạo ra giá trị trả về, hoặc kết thúc mà không trả payload | Message converter đã chuyển đổi thành công; broker đã nhận; client đã nhận |
| Spring xử lý giá trị trả về | Return-value handler áp dụng quy tắc như @SendTo, chuyển payload thành message và gửi vào brokerChannel | Mọi subscriber đều đã nhận message |
| Broker xử lý message | Broker nhận message, tìm subscription phù hợp và định tuyến message | Frame đã đến trình duyệt hoặc client đã xử lý nghiệp vụ |
| Server gửi frame ra kết nối | Message được chuyển qua clientOutboundChannel và transport WebSocket thực hiện việc ghi frame | JavaScript callback đã chạy hoặc UI đã cập nhật |
| Client nhận STOMP MESSAGE | Thư viện STOMP phía client đã nhận frame và có thể gọi callback | Logic nghiệp vụ phía client đã lưu hoặc hoàn thành tác vụ |
| Client gửi xác nhận nghiệp vụ | Client gửi một thông điệp xác nhận theo hợp đồng ứng dụng; server có thể ghi nhận xác nhận đó | Tác động bên ngoài được thực hiện đúng một lần, trừ khi ứng dụng có cơ chế idempotency và kiểm soát lỗi phù hợp |

Phương thức controller thường chỉ kiểm soát trực tiếp phần xử lý nghiệp vụ và giá trị trả về. Các bước tiếp theo thuộc pipeline messaging và transport, có thể chạy bất đồng bộ qua các channel hoặc executor.

## 2. Luồng xử lý từ STOMP SEND đến client

Giả sử client gửi một STOMP SEND đến destination ứng dụng. Spring định tuyến message vào controller được đánh dấu bằng @MessageMapping. Khi phương thức trả về, Spring tiếp tục xử lý giá trị đó theo cấu hình gửi message.

~~~mermaid
sequenceDiagram
    participant C as STOMP client
    participant W as WebSocket transport
    participant I as clientInboundChannel
    participant H as @MessageMapping handler
    participant B as brokerChannel và broker
    participant O as clientOutboundChannel

    C->>W: SEND /app/orders.confirm
    W->>I: Giải mã frame và dispatch message
    I->>H: Gọi controller
    H-->>I: Trả về OrderConfirmed
    I->>B: Convert payload và publish /topic/orders
    B->>O: Định tuyến đến subscription đang hoạt động
    O->>W: Gửi STOMP MESSAGE frame
    W-->>C: Frame đến qua WebSocket
    C->>C: Callback và xử lý ứng dụng
~~~

Các thành phần chính:

- **clientInboundChannel** nhận message từ client và chuyển chúng đến các handler của Spring hoặc broker.
- **SimpAnnotationMethodMessageHandler** tìm phương thức phù hợp với @MessageMapping và gọi controller.
- **Return-value handler** xử lý giá trị trả về. @SendTo hoặc @SendToUser xác định destination; message converter chuyển payload thành dạng message phù hợp.
- **brokerChannel** chuyển message do ứng dụng gửi đến message broker.
- **Message broker** quản lý subscription và định tuyến message đến các client đang đăng ký destination tương ứng.
- **clientOutboundChannel** chuyển message từ broker về các kết nối client.
- **WebSocket transport** ghi frame ra kết nối. Thư viện STOMP ở trình duyệt giải mã frame và gọi callback của ứng dụng.

Nếu message converter lỗi, destination không hợp lệ hoặc channel từ chối việc gửi, pipeline có thể thất bại sau khi phần thân controller đã trả về. Vì vậy, chỉ nhìn thấy log “controller completed” chưa đủ để kết luận message đã được publish.

## 3. Ví dụ Spring Framework

Cấu hình sau dùng application prefix /app, broker prefix /topic và /queue, cùng WebSocket endpoint /ws.

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
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }
}
~~~

Controller nhận command và trả về một kết quả được gửi đến topic.

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMessageController {

    @MessageMapping("/orders.confirm")
    @SendTo("/topic/orders")
    public OrderConfirmed confirm(ConfirmOrder command) {
        return new OrderConfirmed(command.orderId(), "CONFIRMED");
    }

    public record ConfirmOrder(String orderId) {}

    public record OrderConfirmed(String orderId, String status) {}
}
~~~

Với cấu hình trên:

1. Client gửi command đến /app/orders.confirm.
2. Spring gọi confirm.
3. Phương thức trả về OrderConfirmed.
4. Spring chuyển đổi đối tượng thành message và gửi đến /topic/orders.
5. Broker định tuyến message đến các client đang subscribe /topic/orders.

@SendTo("/topic/orders") gửi đến destination chung. Mọi subscriber đang hoạt động trên destination đó đều có thể nhận message; đây không phải phản hồi riêng cho client đã gửi command. Nếu cần gửi đến người dùng cụ thể, có thể dùng @SendToUser hoặc SimpMessagingTemplate.convertAndSendToUser(...).

Client đăng ký nhận message bằng thư viện STOMP, ví dụ @stomp/stompjs:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  reconnectDelay: 5000,
});

client.onConnect = () => {
  client.subscribe("/topic/orders", (frame) => {
    const event = JSON.parse(frame.body);
    console.log("Client đã nhận:", event);
  });
};

client.activate();
~~~

Callback trên chỉ chạy khi thư viện STOMP nhận được frame MESSAGE. Nếu callback tiếp tục gọi API, cập nhật IndexedDB hoặc thay đổi trạng thái giao diện, những thao tác đó vẫn có thể thất bại riêng. Cần xác định rõ ứng dụng coi “đã nhận” hay “đã xử lý xong” là mốc hoàn tất.

## 4. @SendTo, broker và xác nhận STOMP có ý nghĩa gì?

### @SendTo không phải delivery acknowledgement

@SendTo chỉ khai báo destination cho giá trị trả về của handler. Annotation này không yêu cầu Spring chờ tất cả subscriber xác nhận đã nhận message. Nó cũng không biến một message publish thành một lời gọi request-response có bảo đảm đầu cuối.

Tương tự, việc gọi SimpMessagingTemplate.convertAndSend(...) thể hiện ý định gửi message vào messaging infrastructure. Kết quả của lời gọi không chứng minh trình duyệt đã xử lý payload.

### STOMP RECEIPT

Một STOMP frame có thể mang header receipt. Nếu broker hỗ trợ receipt, server gửi frame RECEIPT để báo frame tương ứng đã được xử lý theo hợp đồng của broker. Receipt của SEND không chứng minh mọi subscriber đã nhận MESSAGE, càng không chứng minh code nghiệp vụ trong trình duyệt đã chạy.

### STOMP ACK

Với subscription sử dụng acknowledgement mode được broker hỗ trợ, client có thể gửi frame ACK sau khi nhận một MESSAGE. Đây là xác nhận ở tầng STOMP/broker. Nó không tự động chứng minh một giao dịch nghiệp vụ trong ứng dụng đã commit hoặc một tác động bên ngoài đã hoàn tất.

Spring Simple Broker chỉ hỗ trợ một phần STOMP và không cung cấp các tính năng nâng cao như ACK, RECEIPT hoặc durable subscription. Không được giả định những cơ chế này hoạt động khi cấu hình bằng enableSimpleBroker(...). Nếu cần các tính năng đó, phải chọn broker phù hợp và cấu hình, kiểm thử đúng khả năng của broker đang sử dụng.

### Xác nhận nghiệp vụ của ứng dụng

Nếu yêu cầu là biết client đã xử lý một sự kiện, hãy định nghĩa một message xác nhận riêng. Ví dụ client gửi event ID về destination ứng dụng sau khi hoàn thành bước xử lý được quy định:

- Client nhận event có eventId.
- Client thực hiện xử lý và lưu trạng thái cần thiết.
- Client gửi ACK nghiệp vụ kèm eventId.
- Server xác thực người gửi, kiểm tra event và lưu trạng thái đã xác nhận.
- Server có thể retry các event còn pending; client phải xử lý lặp an toàn bằng idempotency key.

ACK nghiệp vụ chỉ có giá trị theo đúng thời điểm client gửi nó. Nếu client gửi ACK trước khi lưu kết quả hoặc hoàn tất side effect, server có thể ghi nhận một xác nhận quá sớm. Hãy quy định rõ ACK có nghĩa là “đã nhận”, “đã cập nhật UI” hay “đã lưu kết quả nghiệp vụ”.

## 5. Những giới hạn của WebSocket và message broker

WebSocket cung cấp kết nối hai chiều và truyền frame có thứ tự trên một kết nối đang hoạt động. Điều đó không tạo ra bảo đảm rằng một message sẽ được lưu lại và giao cho client sau khi mất kết nối.

Với Spring Simple Broker:

- Subscription được quản lý trong bộ nhớ của ứng dụng.
- Message được định tuyến đến subscriber đang hoạt động tại thời điểm broker xử lý.
- Client mất kết nối có thể bỏ lỡ message được publish trong khoảng thời gian offline.
- Reconnect không tự động phát lại các message đã bỏ lỡ.
- Simple Broker không phải message broker bền vững và không thích hợp cho yêu cầu cần lưu trữ, replay hoặc clustering.

Khi dùng broker relay với broker bên ngoài, khả năng lưu trữ, durable subscription, acknowledgement và retry phụ thuộc vào broker, loại destination và cấu hình subscription. Chỉ bật broker relay không tự động tạo ra bảo đảm giao hàng đầu cuối.

Nếu một sự kiện quan trọng phải được client nhìn thấy sau khi reconnect, hãy lưu trạng thái hoặc event ở nơi bền vững. Client có thể đồng bộ lại qua REST/API hoặc yêu cầu replay theo event ID, sequence hoặc cursor. WebSocket nên đóng vai trò kênh thông báo nhanh, còn dữ liệu bền vững phải có nguồn lưu trữ có thể truy vấn lại.

## 6. Ranh giới transaction và thời điểm publish

Một trường hợp dễ gây lỗi là gửi thông báo “đơn hàng đã xác nhận” trước khi transaction ghi đơn hàng commit. Client có thể nhận thông báo rồi truy vấn dữ liệu trong khi transaction vẫn chưa hoàn tất hoặc sau đó bị rollback.

Ví dụ, nếu gọi SimpMessagingTemplate.convertAndSend(...) ngay bên trong một phương thức đang mở transaction, message có thể được publish trước khi transaction commit. Khi thông báo chỉ hợp lệ sau commit, hãy phát event sau commit, chẳng hạn dùng @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT), hoặc dùng transactional outbox nếu cần độ tin cậy cao hơn.

Transactional outbox lưu thay đổi nghiệp vụ và bản ghi event trong cùng transaction. Một tiến trình riêng đọc outbox và publish event; event chưa gửi thành công có thể được retry. Vì retry có thể tạo bản gửi trùng, consumer vẫn cần idempotency.

## 7. Thiết kế delivery có thể kiểm chứng

Nếu ứng dụng chỉ cần cập nhật giao diện tạm thời, publish đến topic và xử lý callback có thể đã đủ. Nếu nghiệp vụ cần biết client đã nhận hoặc xử lý, hãy thiết kế thêm các cơ chế sau:

1. **Định danh event:** Mỗi event có eventId duy nhất, correlationId, thời điểm tạo và mã đối tượng nghiệp vụ. Không dùng nội dung payload làm định danh.
2. **Lưu trạng thái cần bảo đảm:** Lưu event hoặc trạng thái nghiệp vụ ở database trước khi yêu cầu client xử lý. Không dựa vào một message WebSocket duy nhất làm nơi lưu dữ liệu.
3. **ACK theo hợp đồng:** Client gửi ACK nghiệp vụ sau đúng mốc cần xác nhận. Server kiểm tra quyền sở hữu event và lưu ACK.
4. **Retry có giới hạn:** Server retry event chưa được xác nhận theo timeout và chính sách số lần thử. Hết số lần thử phải có trạng thái để vận hành kiểm tra.
5. **Idempotency:** Client và server xử lý event trùng một cách an toàn. Việc nhận lại cùng eventId không được tạo thêm side effect ngoài ý muốn.
6. **Khôi phục sau reconnect:** Client đăng ký lại subscription rồi đồng bộ các event hoặc trạng thái bị bỏ lỡ từ nguồn lưu trữ bền vững.
7. **Quan sát theo từng chặng:** Log cùng eventId tại lúc controller hoàn tất, lúc publish, lúc broker định tuyến nếu có thể quan sát, lúc client nhận và lúc ACK nghiệp vụ được lưu. Không ghi toàn bộ payload nhạy cảm vào log.

Không nên dùng một log duy nhất như “sent successfully” cho mọi mốc. Hãy đặt tên sự kiện phản ánh chính xác điều đã xảy ra, chẳng hạn controller_completed, message_published, client_message_received và business_ack_recorded.

## 8. Kiểm thử đúng ranh giới cần bảo đảm

- **Unit test controller:** Kiểm tra logic nghiệp vụ và giá trị trả về. Test này không chứng minh message đã đến client.
- **Test message handler:** Kiểm tra destination, message conversion và việc Spring chuyển message vào broker channel.
- **Integration test STOMP/WebSocket:** Dùng client STOMP thật kết nối đến endpoint, subscribe destination, gửi command và chờ message với timeout hữu hạn. Test này xác minh đường đi qua messaging infrastructure trong môi trường test.
- **Test mất kết nối:** Ngắt kết nối trong lúc publish, reconnect và kiểm tra hành vi replay hoặc đồng bộ lại mà ứng dụng đã cam kết.
- **Test ACK và retry:** Kiểm tra ACK hợp lệ, ACK sai event, ACK trùng, client không ACK và event được gửi lại.
- **Test transaction:** Kiểm tra event không được công bố như một thay đổi đã commit khi transaction rollback.

Tránh dùng Thread.sleep(...) cố định để kết luận message đã đến. Hãy chờ một điều kiện cụ thể bằng latch, future hoặc assertion có timeout; cách này giúp test ổn định và xác định rõ đang kiểm tra mốc nào.

## 9. Checklist khi đọc log hoặc xử lý lỗi

- Controller có thực sự được gọi và trả về payload như mong đợi không?
- Return-value handler hoặc SimpMessagingTemplate có chuyển đổi và publish message thành công không?
- Destination có đúng prefix và đúng với destination client subscribe không?
- Broker đang dùng là Simple Broker hay broker relay? Nó hỗ trợ những tính năng STOMP nào?
- Client đã kết nối, subscribe đúng destination và còn giữ kết nối tại thời điểm publish không?
- Callback nhận message có chạy không? Nếu chạy, xử lý payload hoặc cập nhật UI có lỗi không?
- Nếu cần xác nhận nghiệp vụ, ACK có được gửi và server có lưu ACK không?
- Nếu client offline, ứng dụng có nguồn dữ liệu bền vững để đồng bộ lại không?

Khi báo lỗi “controller đã hoàn tất nhưng client không thấy kết quả”, hãy xác định chặng đầu tiên không có bằng chứng thành công. Việc phân tách các mốc này giúp khoanh vùng lỗi giữa controller, message converter, channel, broker, WebSocket transport và code phía client mà không nhầm lẫn một lần publish với một lần xử lý nghiệp vụ hoàn tất.