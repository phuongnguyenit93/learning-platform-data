# SEND, SUBSCRIBE, UNSUBSCRIBE và MESSAGE trong STOMP

## Mục tiêu

Sau bài này, bạn có thể:

- Mô tả cấu trúc STOMP frame gồm command, headers, body và byte kết thúc.
- Phân biệt SEND, SUBSCRIBE, UNSUBSCRIBE là frame client gửi và MESSAGE là frame server gửi.
- Xác định header bắt buộc, tùy chọn theo STOMP 1.2.
- Theo dõi subscription bằng id và hiểu các chế độ acknowledgement.
- Phân biệt message-id với ack token dùng trong ACK/NACK.
- Hiểu receipt xác nhận điều gì và không xác nhận điều gì.
- Áp dụng các frame trong Spring STOMP over WebSocket với @MessageMapping, @SendTo và broker.
- Tránh nhầm quy ước destination của broker với quy tắc chung của STOMP.

## 1. Cấu trúc một STOMP frame

STOMP (Simple Text Oriented Messaging Protocol) là giao thức truyền message theo frame. Nó chạy trên một kết nối streaming hai chiều đáng tin cậy như TCP hoặc WebSocket. Dù tên giao thức có chữ Text, body vẫn có thể chứa dữ liệu nhị phân.

Cấu trúc tổng quát:

~~~text
COMMAND
header-name:header-value
another-header:another-value

message body^@
~~~

Một frame gồm:

1. **Command:** tên lệnh như SEND, SUBSCRIBE, UNSUBSCRIBE hoặc MESSAGE.
2. **Headers:** các dòng key:value; mỗi dòng kết thúc bằng EOL.
3. **Dòng trống:** đánh dấu kết thúc headers và bắt đầu body.
4. **Body:** nội dung message nếu command cho phép có body.
5. **NULL octet:** byte có giá trị 0, kết thúc frame.

Trong ví dụ, ^@ biểu diễn byte NULL (0x00). Khi truyền thật, client phải gửi byte NULL, không gửi hai ký tự dấu mũ và @.

STOMP 1.2 cho phép EOL là LF hoặc CRLF. Command và header name phân biệt chữ hoa chữ thường: SEND khác send; content-type khác Content-Type.

### Body và content headers

Theo STOMP 1.2, chỉ SEND, MESSAGE và ERROR được phép có body. SUBSCRIBE và UNSUBSCRIBE không có body.

Hai header thường dùng:

- content-type: MIME type mô tả body, ví dụ text/plain hoặc application/json.
- content-length: độ dài body tính bằng octet/byte, không phải số ký tự Unicode.

Nếu body có byte NULL ở giữa, frame bắt buộc phải có content-length để parser biết body kết thúc ở đâu. Với body thông thường, specification khuyến nghị gửi content-type và content-length khi phù hợp. STOMP mặc định hỗ trợ UTF-8.

## 2. Vai trò của bốn frame

| Frame | Hướng truyền | Vai trò | Header bắt buộc theo STOMP 1.2 |
|---|---|---|---|
| SEND | Client → Server | Gửi message tới destination | destination |
| SUBSCRIBE | Client → Server | Đăng ký nhận message từ destination | id, destination |
| UNSUBSCRIBE | Client → Server | Hủy một subscription đã đăng ký | id |
| MESSAGE | Server → Client | Chuyển message tới client qua subscription | destination, message-id, subscription |

Một client có thể vừa gửi SEND, vừa đăng ký SUBSCRIBE trên cùng kết nối. Server dùng MESSAGE để chuyển message phù hợp tới subscription đã đăng ký.

Không được nhầm MESSAGE với lệnh client gửi lên server. Đây là frame phía server, thường phát sinh khi broker giao một message cho subscription.

## 3. SEND: gửi message tới destination

SEND đưa một message vào messaging system. Header bắt buộc là destination; body chứa nội dung cần gửi.

Ví dụ gửi text:

~~~text
SEND
destination:/queue/orders
content-type:text/plain
content-length:8

ORD-1001^@
~~~

Ví dụ gửi JSON:

~~~text
SEND
destination:/queue/orders
content-type:application/json
event-type:OrderCreated
correlation-id:checkout-9001

{"orderId":"ORD-1001","status":"CREATED"}^@
~~~

Trong ví dụ thứ hai:

- destination chọn nơi nhận message.
- content-type cho biết body là JSON.
- event-type và correlation-id là application headers do ứng dụng tự định nghĩa.
- Body chứa dữ liệu nghiệp vụ.

### Destination là chuỗi do server diễn giải

STOMP specification xem destination là một chuỗi opaque. Bản thân giao thức không quy định /queue/orders phải có semantics point-to-point hoặc /topic/orders phải broadcast.

Nhiều broker dùng convention:

- /queue/...: thường là point-to-point.
- /topic/...: thường là publish-subscribe.

Đây là convention phổ biến, không phải bảo đảm chung của STOMP. Cú pháp destination, quyền truy cập, durability, routing và delivery semantics phụ thuộc broker hoặc STOMP server đang dùng.

### Header bổ sung, transaction và receipt

SEND có thể chứa các header do ứng dụng định nghĩa. Server phải chuyển tiếp user-defined headers này trong frame MESSAGE tương ứng, ngoài các header riêng do server thêm vào.

SEND cũng hỗ trợ header transaction để gắn thao tác gửi vào một STOMP transaction đã mở bằng BEGIN. Khi cần server xác nhận đã xử lý frame, client có thể thêm header receipt; server có thể trả frame RECEIPT nếu hỗ trợ.

Nếu server không thể xử lý SEND, theo STOMP 1.2 server gửi ERROR rồi đóng kết nối. Ứng dụng nên xử lý cả lỗi protocol và lỗi transport ở client.

## 4. SUBSCRIBE: đăng ký nhận message

SUBSCRIBE yêu cầu server đăng ký client nhận message từ một destination. Hai header bắt buộc:

- destination: nơi client muốn nghe.
- id: định danh subscription.

Ví dụ:

~~~text
SUBSCRIBE
id:orders-live
destination:/topic/orders
ack:auto

^@
~~~

Sau khi đăng ký, các message được broker định tuyến tới subscription sẽ được gửi về client dưới dạng frame MESSAGE.

### Subscription ID

Một kết nối STOMP có thể mở nhiều subscription, kể cả nhiều subscription cùng destination. Vì vậy:

- Mỗi SUBSCRIBE phải có id.
- Các id phải khác nhau trong cùng một connection.
- Server dùng id để điền header subscription trong frame MESSAGE.
- Client dùng đúng id đó khi gửi UNSUBSCRIBE.

Ví dụ cùng một connection đăng ký hai subscription:

~~~text
SUBSCRIBE
id:orders-all
destination:/topic/orders

^@

SUBSCRIBE
id:orders-priority
destination:/topic/orders
ack:client-individual

^@
~~~

Hai subscription có thể nhận message từ cùng destination nhưng có ID và acknowledgement policy riêng. Nếu server hỗ trợ selector hoặc subscription options khác, chúng thường được truyền qua header riêng của broker; hãy kiểm tra tài liệu broker vì các header đó không nhất thiết thuộc STOMP chuẩn.

### ack mode: auto, client và client-individual

Header ack điều khiển cách client xác nhận đã xử lý message. Nếu bỏ qua, mặc định là auto.

| Mode | Cách hoạt động | Hệ quả |
|---|---|---|
| auto | Client không cần gửi ACK; server coi message đã được nhận khi gửi tới client | Đơn giản, nhưng message có thể bị mất nếu client hỏng trước khi xử lý xong |
| client | Client gửi ACK hoặc NACK; xác nhận có tính cumulative | ACK một message xác nhận cả các message trước đó trên subscription |
| client-individual | Client gửi ACK hoặc NACK cho từng message | Xác nhận độc lập, phù hợp khi xử lý song song hoặc hoàn tất không theo thứ tự |

Với client và client-individual, server chưa coi message đã tiêu thụ cho đến khi nhận ACK. Nếu kết nối mất trước ACK, server có thể giao lại message. Hành vi cuối cùng khi NACK—giao cho consumer khác, bỏ message hay đưa vào dead-letter queue—phụ thuộc broker.

### ACK dùng header nào?

Với STOMP 1.2, nếu subscription yêu cầu explicit acknowledgement, frame MESSAGE phải có header ack. Giá trị này là token để client dùng trong frame ACK hoặc NACK.

Ví dụ MESSAGE:

~~~text
MESSAGE
subscription:orders-priority
message-id:msg-9001
ack:ack-token-9001
destination:/topic/orders
content-type:application/json

{"orderId":"ORD-1001","status":"CREATED"}^@
~~~

Client xác nhận bằng:

~~~text
ACK
id:ack-token-9001

^@
~~~

Header id của frame ACK phải khớp với giá trị ack trong frame MESSAGE. Đừng lấy message-id thay cho ack: hai header có vai trò khác nhau.

Nếu client không xử lý được message, có thể gửi:

~~~text
NACK
id:ack-token-9001

^@
~~~

NACK báo server rằng client không tiêu thụ message thành công. Cách broker retry, chuyển message hoặc đưa vào DLQ là implementation-specific.

## 5. UNSUBSCRIBE: hủy subscription

UNSUBSCRIBE kết thúc một subscription đang tồn tại. Header bắt buộc là id, phải khớp chính xác ID đã dùng khi SUBSCRIBE.

~~~text
UNSUBSCRIBE
id:orders-live

^@
~~~

Sau khi server xử lý việc hủy, connection không còn nhận message qua subscription đó.

Lưu ý:

- Không cần gửi lại destination; server xác định subscription bằng id.
- Nếu connection có nhiều subscription, hủy một ID không đồng nghĩa hủy các subscription còn lại.
- Dùng ID không tồn tại hoặc ID không thuộc connection hiện tại có thể khiến server báo lỗi.
- Có thể thêm receipt để yêu cầu xác nhận server đã xử lý frame hủy, nếu server hỗ trợ.

Ví dụ:

~~~text
UNSUBSCRIBE
id:orders-live
receipt:unsubscribe-42

^@
~~~

Server có thể trả:

~~~text
RECEIPT
receipt-id:unsubscribe-42

^@
~~~

RECEIPT xác nhận frame tương ứng đã được server xử lý. Nó không phải bằng chứng message nghiệp vụ cuối cùng đã được consumer xử lý xong.

## 6. MESSAGE: server chuyển message tới subscription

MESSAGE là frame server gửi cho client khi một message được giao qua subscription. Theo STOMP 1.2, ba header bắt buộc là:

- destination: destination nguồn của message.
- message-id: ID duy nhất của message do server cung cấp.
- subscription: ID của subscription nhận message.

Nếu subscription dùng ack:auto, header ack không bắt buộc. Nếu dùng ack:client hoặc ack:client-individual, frame phải có thêm ack token.

Ví dụ:

~~~text
MESSAGE
destination:/topic/orders
message-id:msg-9001
subscription:orders-live
content-type:application/json
event-type:OrderCreated

{"orderId":"ORD-1001","status":"CREATED"}^@
~~~

Client dùng header subscription để biết message đến từ đăng ký nào. Điều này quan trọng khi một connection có nhiều subscription cùng destination hoặc các subscription dùng acknowledgement mode khác nhau.

### Server không gửi MESSAGE tùy ý

Theo STOMP, server không gửi message tự phát tới một client bất kỳ. Message server gửi phải gắn với một subscription cụ thể, và header subscription phải khớp ID trong frame SUBSCRIBE ban đầu.

Broker có thể bổ sung các header riêng của server. Các user-defined headers từ frame SEND cũng được chuyển tiếp trong frame MESSAGE. Vì vậy, consumer có thể nhận cả metadata do producer gửi và metadata do broker tạo.

## 7. Vòng đời hoàn chỉnh: SEND → MESSAGE → ACK → UNSUBSCRIBE

Xét client đăng ký nhận đơn hàng, producer gửi một sự kiện, broker giao message và consumer xác nhận sau khi xử lý:

~~~text
Client                                      STOMP Server / Broker
  |                                                   |
  |---- SUBSCRIBE id:orders-1 ----------------------->|
  |     destination:/queue/orders                     |
  |     ack:client-individual                         |
  |                                                   |
  |<--- RECEIPT (nếu đã yêu cầu và broker hỗ trợ) ----|
  |                                                   |
  |<--- MESSAGE --------------------------------------|
  |     subscription:orders-1                         |
  |     message-id:msg-101                            |
  |     ack:ack-101                                   |
  |     destination:/queue/orders                    |
  |     body: OrderCreated                            |
  |                                                   |
  |---- ACK id:ack-101 ------------------------------>|
  |                                                   |
  |---- UNSUBSCRIBE id:orders-1 --------------------->|
  |                                                   |
~~~

Luồng diễn ra như sau:

1. Client gửi SUBSCRIBE với ID orders-1.
2. Broker lưu subscription và định tuyến message phù hợp tới nó.
3. Server gửi frame MESSAGE; header subscription chỉ ra message thuộc subscription nào.
4. Vì dùng client-individual, client xử lý xong message rồi gửi ACK với token từ header ack.
5. Client gửi UNSUBSCRIBE với ID ban đầu khi không còn muốn nhận message.

Nếu bước xử lý thất bại, client có thể gửi NACK. Nếu client ngắt kết nối trước ACK, broker có thể redeliver theo delivery policy. Do đó, ứng dụng vẫn nên xử lý duplicate an toàn khi broker hỗ trợ redelivery.

## 8. RECEIPT, ACK và MESSAGE khác nhau như thế nào?

Ba khái niệm thường bị nhầm:

| Thành phần | Ý nghĩa | Không chứng minh điều gì |
|---|---|---|
| RECEIPT | Server đã xử lý frame client yêu cầu receipt | Không chứng minh business handler đã hoàn tất hoặc consumer đã xử lý message |
| MESSAGE | Server đang chuyển một message tới subscription | Không tự chứng minh client đã xử lý xong |
| ACK | Client xác nhận đã tiêu thụ message theo ack mode | Không phải xác nhận producer đã gửi message thành công |

Một client có thể thêm header receipt vào frame SEND, SUBSCRIBE hoặc UNSUBSCRIBE để yêu cầu receipt. Server trả RECEIPT với receipt-id khớp giá trị đó.

Do STOMP truyền frame theo stream, receipt còn xác nhận các frame trước đó đã được server nhận. Tuy nhiên, các frame trước có thể chưa hoàn tất xử lý. Vì thế, nếu cần xác nhận nghiệp vụ, hãy thiết kế một response/event riêng với correlation ID thay vì coi receipt là kết quả xử lý nghiệp vụ.

## 9. SEND và SUBSCRIBE trong Spring STOMP over WebSocket

Spring hỗ trợ STOMP trên WebSocket qua hai module spring-messaging và spring-websocket. Khi bật STOMP message broker support, Spring nhận frame từ WebSocket, chuyển thành Spring Message<?> rồi đưa vào message channel nội bộ.

Cấu hình cơ bản:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        // HTTP/WebSocket handshake endpoint.
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        // SEND tới /app/... được route tới @MessageMapping.
        registry.setApplicationDestinationPrefixes("/app");

        // SUBSCRIBE và SEND tới các prefix này được broker xử lý.
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Hai loại destination có vai trò thường gặp:

- /app: prefix ứng dụng; client gửi SEND tới đây để gọi controller @MessageMapping.
- /topic và /queue: prefix broker; client thường SUBSCRIBE ở đây để nhận broadcast hoặc queue message.

Trong Spring, các prefix trên là cấu hình routing của ứng dụng. Chúng không phải quy tắc chung của STOMP protocol.

### SEND tới @MessageMapping

Controller:

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders")
    @SendTo("/topic/order-events")
    public OrderEvent createOrder(OrderCommand command) {
        // Thực hiện kiểm tra và xử lý nghiệp vụ.
        return new OrderEvent(
                command.orderId(),
                "CREATED"
        );
    }
}

public record OrderCommand(String orderId) {}

public record OrderEvent(String orderId, String status) {}
~~~

Client gửi:

~~~text
SEND
destination:/app/orders
content-type:application/json

{"orderId":"ORD-1001"}^@
~~~

Spring bỏ prefix /app, route phần /orders tới @MessageMapping("/orders"), chuyển JSON payload thành OrderCommand bằng message converter phù hợp và gọi controller.

Giá trị trả về được chuyển thành Spring Message rồi gửi qua brokerChannel. Với @SendTo("/topic/order-events"), broker phát message tới các subscription khớp destination. Client nhận được frame MESSAGE trên WebSocket.

### SUBSCRIBE tới broker

Client đăng ký:

~~~text
SUBSCRIBE
id:order-events-ui
destination:/topic/order-events
ack:auto

^@
~~~

Frame này được đưa vào clientInboundChannel và chuyển tới broker để lưu subscription. Khi controller hoặc một thành phần server gửi message tới /topic/order-events, broker tìm các subscriber phù hợp và phát frame MESSAGE qua clientOutboundChannel.

### MESSAGE từ server tới client

Có thể chủ động gửi message từ service bằng SimpMessagingTemplate:

~~~java
@Service
public class OrderEventPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(OrderEvent event) {
        messagingTemplate.convertAndSend("/topic/order-events", event);
    }
}
~~~

Broker sẽ chuyển payload tới các subscription phù hợp và Spring encode thành STOMP MESSAGE frame trên kết nối WebSocket.

### SUBSCRIBE một lần với @SubscribeMapping

@SubscribeMapping xử lý một frame đăng ký theo destination ứng dụng. Mặc định, giá trị trả về được gửi trực tiếp tới client đã subscribe qua clientOutboundChannel, không được gửi vào broker để broadcast.

Điều này hữu ích khi UI cần tải snapshot ban đầu, ví dụ trạng thái đơn hàng hiện tại. Sau snapshot, client vẫn có thể subscribe /topic/order-events để nhận các cập nhật tiếp theo.

Không nhầm @SubscribeMapping với một broker subscription lâu dài: response mặc định chỉ là phản hồi cho lần subscribe đó.

## 10. Destination, broker và broker relay

Spring có thể dùng simple in-memory broker hoặc relay tới một STOMP broker bên ngoài.

**Simple broker** lưu subscription trong bộ nhớ của ứng dụng Spring và phát message tới subscriber phù hợp. Nó phù hợp cho các trường hợp đơn giản, nhưng không cung cấp toàn bộ tính năng của một message broker chuyên dụng.

**Broker relay** duy trì kết nối TCP từ Spring tới một broker STOMP bên ngoài như RabbitMQ hoặc ActiveMQ. Spring chuyển frame lên broker và chuyển frame broker trả về xuống các WebSocket client.

Một số điểm cần xác định theo broker:

- Quy tắc đặt destination.
- Queue/topic semantics và durability.
- Selector hoặc header riêng.
- Acknowledgement, redelivery và dead-letter behavior.
- Hỗ trợ transaction và receipt.
- Kích thước frame tối đa và giới hạn header.

Không giả định một destination hoặc header riêng của broker sẽ hoạt động giống nhau trên mọi STOMP server.

## 11. Quy tắc encoding và lỗi thường gặp

STOMP 1.2 có các quy tắc encoding quan trọng:

- Command và header name phân biệt hoa thường.
- Header values không được server/client tự ý trim hoặc pad khoảng trắng.
- Với các frame ngoài CONNECT và CONNECTED, header value cần escape các ký tự đặc biệt: \r, \n, \c cho dấu hai chấm và \\ cho dấu gạch chéo ngược.
- content-length đếm byte, không đếm ký tự.
- Nếu body chứa byte NULL, phải có content-length.
- Nếu một header xuất hiện nhiều lần, STOMP 1.2 khuyến nghị dùng giá trị đầu tiên.

Các lỗi phổ biến:

1. **Gửi SEND thiếu destination.** Server không biết nơi định tuyến message; frame không hợp lệ và server có thể trả ERROR rồi đóng kết nối.
2. **Gửi SUBSCRIBE thiếu id.** Mỗi subscription cần ID duy nhất trong connection.
3. **Dùng lại subscription ID trong cùng connection.** Server không thể phân biệt các subscription.
4. **UNSUBSCRIBE bằng destination thay vì id.** STOMP 1.2 yêu cầu ID của subscription đã tạo.
5. **Cho rằng MESSAGE là frame client gửi.** Đây là frame server gửi tới client theo subscription.
6. **Nhầm message-id với ack token.** ACK/NACK dùng giá trị header ack của MESSAGE.
7. **Để ack:auto cho xử lý quan trọng mà không chấp nhận rủi ro mất message.** Với explicit ack, chọn client hoặc client-individual theo cách xử lý và thứ tự hoàn tất.
8. **Cho rằng client ack luôn độc lập.** client là cumulative; client-individual mới xác nhận từng message.
9. **Coi receipt là business success.** Receipt xác nhận server đã xử lý frame ở tầng protocol.
10. **Giả định /queue và /topic có semantics chuẩn.** STOMP để destination semantics cho server quyết định.
11. **Dùng content-length theo số ký tự.** Với UTF-8 hoặc binary, cần tính số byte.
12. **Gửi header value chứa newline hoặc colon mà không escape.** Parser có thể diễn giải sai cấu trúc frame.
13. **Giữ subscription không cần thiết.** Hủy bằng UNSUBSCRIBE khi UI rời màn hình hoặc không còn cần nhận dữ liệu.
14. **Không xử lý ERROR và mất kết nối.** Client cần quan sát cả STOMP ERROR frame lẫn lỗi WebSocket/transport.

## 12. Checklist kiểm thử

- [ ] Kết nối STOMP và thương lượng đúng phiên bản protocol.
- [ ] Gửi SEND với destination hợp lệ và body đúng content type.
- [ ] Kiểm tra user-defined headers có được giữ trong MESSAGE không.
- [ ] Đăng ký nhiều subscription với ID khác nhau.
- [ ] Kiểm tra MESSAGE.subscription khớp ID đã đăng ký.
- [ ] Kiểm thử ack:auto, ack:client và ack:client-individual.
- [ ] Xác nhận ACK dùng token từ header ack, không dùng nhầm message-id.
- [ ] Gửi NACK và quan sát broker redelivery/DLQ behavior.
- [ ] Hủy đúng subscription bằng UNSUBSCRIBE id.
- [ ] Kiểm tra receipt nếu broker hỗ trợ.
- [ ] Kiểm thử payload UTF-8, binary và body có byte NULL.
- [ ] Xác nhận Spring route /app tới @MessageMapping, còn /topic và /queue tới broker.
- [ ] Kiểm thử cả simple broker và broker relay nếu ứng dụng hỗ trợ hai chế độ.
- [ ] Xử lý ERROR frame, timeout và WebSocket disconnect.

## 13. Kết luận

SEND đưa message vào một destination; SUBSCRIBE tạo đăng ký nhận message có ID duy nhất; UNSUBSCRIBE kết thúc đăng ký đó; MESSAGE là frame server gửi về client qua một subscription cụ thể. Header destination xác định nơi gửi hoặc nguồn message, subscription liên kết MESSAGE với SUBSCRIBE, còn ack token liên kết MESSAGE với ACK/NACK khi dùng explicit acknowledgement. Trong Spring STOMP over WebSocket, SEND tới prefix /app được route tới @MessageMapping, trong khi subscription tới prefix broker như /topic được broker lưu và phục vụ. Luôn kiểm tra destination semantics, acknowledgement và receipt theo đúng broker đang triển khai.

## Tài liệu tham khảo chính thức

- [STOMP Protocol Specification 1.2](https://stomp.github.io/stomp-specification-1.2.html) — frame grammar, SEND, SUBSCRIBE, UNSUBSCRIBE, MESSAGE, ACK/NACK, receipt và header rules.
- [Spring Framework 7.0.10 Reference: STOMP Overview](https://www.springframework.org/spring/reference/web/websocket/stomp/overview.html) — STOMP frame model, destination, Spring broker và broker relay.
- [Spring Framework 7.0.10 Reference: Flow of Messages](https://springframework.org/spring-framework/reference/web/websocket/stomp/message-flow.html) — clientInboundChannel, brokerChannel, clientOutboundChannel, @MessageMapping và broker routing.
- [Spring Framework 7.0 Reference: Annotated Controllers](https://www.springframework.org/spring/reference/7.0/web/websocket/stomp/handle-annotations.html) — @MessageMapping, @SubscribeMapping, @SendTo và return values.
- [Spring Framework 7.0 Reference: Enable STOMP](https://www.springframework.org/spring/reference/7.0/web/websocket/stomp/enable.html) — đăng ký WebSocket STOMP endpoint và cấu hình destination prefixes.
