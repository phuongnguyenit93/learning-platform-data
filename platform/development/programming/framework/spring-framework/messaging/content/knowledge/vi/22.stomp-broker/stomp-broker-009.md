# ACK, receipt, transaction và độ bền theo broker thực tế trong Spring STOMP

## Mục tiêu

STOMP cung cấp các frame để client gửi message, nhận message và điều khiển việc xác nhận xử lý. Bốn khái niệm thường bị nhầm lẫn là:

- **ACK/NACK**: consumer xác nhận đã xử lý hoặc từ chối một message đã nhận.
- **Receipt**: client yêu cầu server xác nhận một frame gửi lên đã được server xử lý.
- **Transaction**: nhóm thao tác SEND và ACK/NACK để broker xử lý theo một đơn vị giao dịch.
- **Durability/persistence**: khả năng giữ message hoặc subscription qua thời gian không có consumer hoặc qua lần khởi động lại broker.

Spring WebSocket STOMP có thể dùng simple broker tích hợp hoặc chuyển tiếp tới một broker bên ngoài. Các tính năng ACK, receipt, transaction và lưu bền phụ thuộc vào STOMP broker thực tế. Không thể suy ra mức bảo đảm chỉ từ việc destination có tên **/queue** hoặc **/topic**.

Các đoạn Java trong bài là trích đoạn cấu hình hoặc logic minh họa. Imports, DTO, service, cấu hình xác thực và phần khởi tạo broker được lược bỏ khi không trực tiếp liên quan đến khái niệm đang giải thích. Đoạn consumer ở phần idempotency được đánh dấu là pseudocode, không phải một STOMP listener hoàn chỉnh.

## 1. Xác định tầng nào đang cung cấp tính năng

Một ứng dụng Spring STOMP thường có ba tầng:

1. **Client STOMP** gửi các frame như SEND, SUBSCRIBE, ACK, NACK, BEGIN, COMMIT và DISCONNECT.
2. **Spring WebSocket messaging** nhận frame qua WebSocket, xác thực, áp dụng interceptor và định tuyến theo destination.
3. **Broker** quản lý subscription, hàng đợi, giao nhận, xác nhận và lưu trữ message.

Cấu hình simple broker:

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
    }
}
~~~

Simple broker của Spring lưu thông tin subscription trong bộ nhớ và phát message tới các client đang kết nối. Nó chỉ hỗ trợ một phần STOMP; các tính năng như ACK và receipt không được hỗ trợ. Nó cũng không phải một broker lưu bền hoặc broker phân tán để triển khai clustering.

Khi cần những khả năng đầy đủ hơn, Spring có thể relay STOMP tới broker ngoài:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("localhost")
            .setRelayPort(61613);
}
~~~

Trong cấu hình relay, Spring chuyển tiếp các frame STOMP giữa WebSocket client và broker bên ngoài. Broker bên ngoài quyết định hỗ trợ ACK, NACK, receipt, transaction, queue bền vững, durable subscription, retry, dead-letter và replication như thế nào. Relay không tự tạo ra các bảo đảm đó nếu broker không cung cấp.

## 2. ACK và NACK: xác nhận việc tiêu thụ message

### Chế độ ACK trên SUBSCRIBE

Client chọn chế độ xác nhận bằng header **ack** trong frame SUBSCRIBE. STOMP 1.2 định nghĩa ba giá trị:

| Chế độ | Ý nghĩa |
|---|---|
| **auto** | Server/broker coi message đã được xác nhận khi gửi MESSAGE cho client; client không cần gửi ACK. |
| **client** | Client phải gửi ACK/NACK. ACK có tính cộng dồn: xác nhận message được chỉ định và các message trước đó trên subscription chưa được xác nhận. |
| **client-individual** | Client xác nhận từng message riêng lẻ; ACK một message không tự xác nhận các message trước đó. |

Nếu không chỉ định **ack**, STOMP mặc định là **auto**. Với luồng cần xác nhận sau khi ứng dụng xử lý xong, thường chọn **client-individual** để mỗi message có quyết định độc lập.

Ví dụ đăng ký subscription thủ công:

~~~text
SUBSCRIBE
id:orders-sub
destination:/queue/orders
ack:client-individual

^@
~~~

Ký hiệu **^@** trong các ví dụ là ký hiệu minh họa byte NUL kết thúc frame STOMP. Khi gửi thực tế, thư viện STOMP tự mã hóa byte kết thúc frame.

### ACK phải dùng đúng id

Với chế độ ACK thủ công, broker gửi frame MESSAGE có header **ack**. Client phải dùng giá trị của header **ack** này trong frame ACK, không được tự lấy **message-id** thay thế.

Ví dụ MESSAGE:

~~~text
MESSAGE
subscription:orders-sub
message-id:msg-901
ack:ack-901
destination:/queue/orders
content-type:application/json

{"orderId":"ORD-901"}
^@
~~~

Sau khi ứng dụng xử lý thành công:

~~~text
ACK
id:ack-901

^@
~~~

Header **id** trong ACK khớp với giá trị **ack** trên MESSAGE. Đây là thay đổi đáng chú ý của STOMP 1.2: ACK dùng header id chuyên biệt tương ứng với ack token của message.

### NACK và xử lý thất bại

NACK báo cho broker rằng consumer không xử lý được message. Broker có thể gửi lại message, đưa message sang consumer khác, loại bỏ hoặc chuyển vào dead-letter queue. Hành vi chính xác tùy broker và cấu hình.

~~~text
NACK
id:ack-902

^@
~~~

Không nên hiểu NACK luôn đồng nghĩa với retry ngay lập tức. Ví dụ, RabbitMQ STOMP plugin hỗ trợ header **requeue** trên NACK để điều khiển việc đưa message trở lại queue hay loại bỏ/dead-letter theo cấu hình. Broker khác có thể có chính sách khác.

### Thời điểm ACK trong ứng dụng

Một consumer nên ACK sau khi đã hoàn thành bước xử lý mà ứng dụng coi là thành công:

1. Nhận MESSAGE.
2. Kiểm tra payload và quyền xử lý.
3. Thực hiện nghiệp vụ, ghi dữ liệu hoặc lưu kết quả.
4. Chỉ sau khi bước cần bảo đảm đã hoàn tất mới gửi ACK.
5. Nếu xử lý thất bại, áp dụng chính sách retry/NACK phù hợp.

Nếu ACK trước khi ghi dữ liệu, ứng dụng có thể mất message khi tiến trình gặp sự cố sau ACK nhưng trước khi hoàn tất nghiệp vụ. Nếu ghi dữ liệu xong rồi mất kết nối trước ACK, broker có thể giao lại message và nghiệp vụ có nguy cơ chạy hai lần. Vì vậy, consumer cần xử lý lặp an toàn bằng idempotency key, unique constraint, bảng inbox hoặc cơ chế deduplication.

ACK chỉ xác nhận trạng thái giao nhận với broker. Nó không tự chứng minh rằng giao dịch cơ sở dữ liệu của ứng dụng đã commit, rằng email đã được gửi, hoặc rằng một hệ thống bên ngoài đã hoàn thành công việc.

## 3. Receipt: xác nhận frame đã được server xử lý

Receipt là cơ chế client yêu cầu xác nhận cho một frame gửi tới server. Client thêm header **receipt** với một giá trị duy nhất vào frame, ví dụ SEND:

~~~text
SEND
destination:/queue/orders
receipt:send-901
content-type:application/json

{"orderId":"ORD-901"}
^@
~~~

Khi server xử lý frame có yêu cầu receipt, server trả về:

~~~text
RECEIPT
receipt-id:send-901

^@
~~~

Giá trị **receipt-id** phải khớp với giá trị **receipt** mà client đã gửi. Ứng dụng client nên giữ bảng các yêu cầu đang chờ receipt để đối chiếu đúng frame, đặt timeout và xử lý trường hợp nhận ERROR hoặc không nhận được receipt.

### Receipt xác nhận điều gì?

Theo STOMP 1.2, RECEIPT xác nhận server đã xử lý frame tương ứng. Vì STOMP truyền dữ liệu theo luồng, receipt còn là xác nhận cộng dồn rằng các frame trước đó đã được server nhận. Tuy nhiên, các frame trước đó có thể chưa được xử lý hoàn tất.

Do đó, receipt của SEND không tự chứng minh rằng:

- Một consumer đã nhận MESSAGE.
- Consumer đã xử lý nghiệp vụ thành công.
- Dữ liệu nghiệp vụ đã commit vào database của ứng dụng.
- Message chắc chắn sẽ tồn tại qua mọi lỗi phần cứng hoặc cấu hình broker.
- Tất cả subscriber đã nhận được bản sao.

Receipt là xác nhận ở ranh giới giao thức/broker. Muốn biết nghiệp vụ đã hoàn tất, ứng dụng cần một phản hồi ở tầng nghiệp vụ, ví dụ event OrderProcessed hoặc kết quả request-response riêng.

### Receipt và DISCONNECT

Để ngắt kết nối có trật tự, client có thể gửi DISCONNECT kèm receipt, chờ RECEIPT tương ứng rồi mới đóng socket:

~~~text
DISCONNECT
receipt:disconnect-17

^@
~~~

Server phản hồi:

~~~text
RECEIPT
receipt-id:disconnect-17

^@
~~~

Cách này giúp client biết server đã nhận và xử lý frame DISCONNECT cùng các frame trước đó theo ngữ nghĩa của receipt. Việc đóng socket ngay sau DISCONNECT mà không chờ receipt có thể làm client không nhận được xác nhận cuối cùng.

Simple broker tích hợp của Spring không hỗ trợ receipt. Khi dùng broker relay, khả năng receipt phụ thuộc broker STOMP bên ngoài và các frame có được broker xử lý thành công hay không.

## 4. Transaction của STOMP

STOMP 1.2 định nghĩa các frame:

- **BEGIN**: bắt đầu transaction.
- **COMMIT**: commit transaction.
- **ABORT**: hủy transaction.
- **SEND**, **ACK**, **NACK**: có thể gắn header **transaction** để tham gia transaction đang mở.

Transaction ID phải duy nhất trong phạm vi một kết nối. Các thao tác tham gia transaction phải dùng đúng ID đó.

Ví dụ gửi nhiều message trong một transaction:

~~~text
BEGIN
transaction:batch-01

^@

SEND
destination:/queue/a
transaction:batch-01

message A
^@

SEND
destination:/queue/b
transaction:batch-01

message B
^@

COMMIT
transaction:batch-01

^@
~~~

Nếu client gửi ABORT thay cho COMMIT, broker hủy các thao tác nằm trong transaction theo khả năng mà broker triển khai. Transaction chưa commit sẽ bị hủy ngầm khi client DISCONNECT hoặc kết nối TCP bị mất theo đặc tả STOMP.

### Transaction có thể bao gồm ACK

STOMP cho phép ACK/NACK cũng tham gia transaction. Điều này hữu ích khi consumer vừa xác nhận message đầu vào vừa gửi một hoặc nhiều message đầu ra trong cùng transaction broker:

~~~text
BEGIN
transaction:process-901

^@

ACK
id:ack-901
transaction:process-901

^@

SEND
destination:/queue/order-events
transaction:process-901
content-type:application/json

{"orderId":"ORD-901","status":"PROCESSED"}
^@

COMMIT
transaction:process-901

^@
~~~

Ý định là để broker xử lý việc xác nhận message đầu vào và phát message đầu ra như một đơn vị transaction. Nếu broker hỗ trợ đầy đủ, việc commit thành công áp dụng các thao tác đã tham gia transaction; abort hủy chúng theo semantics của broker.

### Giới hạn quan trọng

STOMP transaction là transaction do broker quản lý. Nó không tự động bao gồm:

- Transaction cơ sở dữ liệu JDBC/JPA của ứng dụng.
- Giao dịch HTTP với dịch vụ khác.
- Gửi email, ghi file hoặc gọi API bên ngoài.
- Nhiều broker độc lập cùng lúc.
- Mọi thao tác trong phương thức **@Transactional** của Spring.

Ví dụ, **@Transactional** trên service có thể commit database nhưng không tự động đưa một frame STOMP SEND từ client vào cùng transaction. Ngược lại, COMMIT của STOMP broker không tự commit dữ liệu trong database của ứng dụng.

Nếu cần phối hợp ghi database và phát event mà không mất event, cân nhắc **Transactional Outbox**: ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction database, sau đó publisher đọc outbox và gửi tới broker; publisher đánh dấu đã phát theo một quy trình có thể retry. Consumer vẫn cần idempotency vì gửi lại là khả năng bình thường trong hệ thống phân tán.

Không giả định simple broker hỗ trợ BEGIN/COMMIT/ABORT với ngữ nghĩa transaction đầy đủ. Simple broker của Spring chỉ là implementation STOMP một phần; nếu cần transaction, hãy xác nhận rõ hỗ trợ của broker ngoài và kiểm thử trên đúng phiên bản đang chạy.

## 5. Độ bền của message và subscription

Có hai khái niệm khác nhau:

- **Message persistence**: bản thân message được broker lưu bền để có thể phục hồi sau khi broker khởi động lại hoặc gặp sự cố theo cấu hình.
- **Durable subscription/queue**: nơi lưu các message dành cho subscriber có thể vẫn tồn tại khi subscriber ngắt kết nối.

Một message persistent gửi tới một queue tạm thời không tự tạo ra durable subscription. Một durable queue cũng không có nghĩa mọi message gửi vào đó đều được lưu bền nếu message được gửi với chế độ không persistent hoặc broker không bật cơ chế lưu trữ phù hợp.

### STOMP không định nghĩa semantics cho tên destination

STOMP xem giá trị header **destination** như một chuỗi do broker diễn giải. Tên **/queue/orders** không tự bảo đảm queue bền vững; **/topic/news** cũng không tự bảo đảm lưu message khi không có subscriber.

Broker có thể quy định:

- Destination nào là queue, topic, exchange hoặc stream.
- Queue có được tạo tự động hay phải tạo trước.
- Queue có durable, exclusive hoặc auto-delete không.
- Topic subscription là transient hay durable.
- Message có persistent, TTL, priority hoặc dead-letter hay không.
- Khi consumer offline, message được giữ, loại bỏ hay chuyển tới nơi khác.
- Khi broker restart hoặc mất node, dữ liệu nào được phục hồi.

Vì vậy, phải đọc tài liệu đúng broker, đúng plugin STOMP và đúng phiên bản. Không lấy quy ước của RabbitMQ áp dụng cho ActiveMQ hoặc broker khác.

## 6. Ví dụ cụ thể với RabbitMQ STOMP plugin

RabbitMQ cung cấp STOMP plugin và hỗ trợ các destination như **/queue**, **/amq/queue**, **/topic** và **/exchange**. Đây là semantics của RabbitMQ STOMP adapter, không phải quy tắc chung của STOMP.

### Queue destination

Với **/queue/orders**, RabbitMQ tạo queue được quản lý qua STOMP gateway. Nếu không truyền tham số queue, mặc định queue được xem là durable, non-exclusive và non-auto-delete. Message gửi tới queue có thể được giữ lại khi không có subscriber, tùy cấu hình queue và message.

Ví dụ SEND persistent:

~~~text
SEND
destination:/queue/orders
persistent:true
receipt:order-send-901
content-type:application/json

{"orderId":"ORD-901"}
^@
~~~

Header **persistent:true** là hỗ trợ của RabbitMQ STOMP plugin. Với SEND persistent, RabbitMQ chỉ gửi RECEIPT sau khi nhận publisher confirm tương ứng từ broker. Điều này mạnh hơn việc chỉ nhận frame ở socket, nhưng vẫn không có nghĩa consumer đã xử lý message.

### Topic và durable subscription

Với **/topic/orders**, subscription thông thường của RabbitMQ là queue tạm thời, không durable và auto-delete. Message gửi khi không có subscriber phù hợp có thể bị loại bỏ.

Để tạo durable topic subscription, RabbitMQ STOMP plugin hỗ trợ header **durable:true** (có alias **persistent:true** cho tương thích cũ) và yêu cầu **auto-delete:false** để queue backing subscription không bị xóa khi subscriber cuối cùng ngắt kết nối. Subscription cũng cần ID.

~~~text
SUBSCRIBE
id:orders-durable
destination:/topic/orders
ack:client-individual
durable:true
auto-delete:false

^@
~~~

Durable subscription giúp subscriber ngắt kết nối rồi kết nối lại mà vẫn nhận được message đã được định tuyến vào queue bền vững của subscription. Cần cấu hình message persistence và queue durability phù hợp nếu muốn dữ liệu sống qua broker restart. Hãy kiểm tra thêm publisher confirm, queue type, replication, disk alarm và chính sách retention trong môi trường triển khai.

### ACK và NACK trong RabbitMQ

RabbitMQ STOMP plugin hỗ trợ **auto**, **client** và **client-individual**. NACK có thể dùng header **requeue** để điều khiển message có được đưa lại queue hay không; mặc định của plugin là requeue. Nếu dùng dead-letter exchange, cần cấu hình queue và routing tương ứng. Không nên NACK vô hạn mà không có giới hạn retry hoặc dead-letter policy vì có thể tạo vòng lặp xử lý.

RabbitMQ cũng hỗ trợ **prefetch-count** trên SUBSCRIBE để giới hạn số message chưa được xác nhận mà consumer nhận cùng lúc. Đây là header riêng của RabbitMQ, không phải header bắt buộc của STOMP.

## 7. Ví dụ với ActiveMQ Classic và khác biệt giữa broker

ActiveMQ Classic hỗ trợ STOMP và có quy ước riêng cho destination. Theo tài liệu ActiveMQ Classic, message STOMP mặc định không persistent; client cần thêm header **persistent:true** trên SEND nếu muốn dùng persistent delivery.

~~~text
SEND
destination:/queue/ORDERS
persistent:true
receipt:orders-001
content-type:application/json

{"orderId":"ORD-001"}
^@
~~~

Với ActiveMQ Classic, prefix **/queue/** hoặc **/topic/** được ánh xạ sang destination JMS tương ứng. Tuy nhiên, semantics của queue, topic, persistence, transaction, prefetch, redelivery và dead-letter cần kiểm tra trong tài liệu phiên bản ActiveMQ cụ thể.

Một điểm cần đặc biệt cẩn trọng: đừng lấy ví dụ header hoặc hành vi của ActiveMQ Apollo, ActiveMQ Classic và ActiveMQ Artemis làm một. Đây là các sản phẩm/dòng broker khác nhau, có thể khác nhau về hỗ trợ STOMP, mapping và cấu hình.

## 8. Bảng so sánh các cơ chế xác nhận

| Cơ chế | Ai gửi? | Xác nhận điều gì? | Không xác nhận điều gì? |
|---|---|---|---|
| ACK | Consumer client | Consumer báo broker message đã được xử lý theo subscription ack mode | Không tự chứng minh database hoặc API ngoài đã commit |
| NACK | Consumer client | Consumer báo không xử lý message; broker áp dụng chính sách tương ứng | Không bảo đảm retry theo cùng một cách ở mọi broker |
| RECEIPT | Server/broker trả về khi frame yêu cầu receipt được xử lý | Frame đã được server xử lý; receipt cũng xác nhận các frame trước đã được nhận | Không bảo đảm subscriber đã nhận hoặc nghiệp vụ hoàn tất |
| COMMIT | Client gửi tới broker | Hoàn tất các thao tác tham gia STOMP transaction theo broker | Không commit transaction database của ứng dụng |
| Persistence confirm | Broker-specific | Theo cơ chế broker, xác nhận SEND persistent đã được broker xác nhận/lưu theo semantics của nó | Không thay thế ACK của consumer hoặc xác nhận nghiệp vụ |

Các cơ chế này giải quyết những ranh giới khác nhau. Một luồng tin cậy thường kết hợp publisher confirm/receipt, persistent message, durable queue hoặc subscription, manual ACK, retry có giới hạn, dead-letter và xử lý idempotent ở consumer. Không có một header duy nhất cung cấp bảo đảm end-to-end.

## 9. Thiết kế consumer an toàn khi có retry và redelivery

Khi một consumer mất kết nối, broker có thể giao lại message chưa ACK nếu broker và ack mode hỗ trợ hành vi đó. Điều này có thể dẫn tới message được xử lý nhiều lần. Ứng dụng nên thiết kế theo hướng **at-least-once delivery** khi broker có thể redeliver, thay vì mặc định mọi message chỉ được xử lý đúng một lần.

Một mẫu xử lý:

~~~java
public void handle(OrderEvent event) {
    transactionTemplate.executeWithoutResult(status -> {
        if (inboxRepository.existsByEventId(event.eventId())) {
            return;
        }

        inboxRepository.save(new InboxRecord(event.eventId()));
        orderService.apply(event);
    });

    // Gửi ACK sau khi transaction nghiệp vụ đã commit thành công.
}
~~~

Đây là pseudocode minh họa ranh giới xử lý, không phải consumer STOMP hoàn chỉnh. Cách lấy ACK token và gửi frame ACK phụ thuộc STOMP client library đang dùng. Cần đặt unique constraint trên event ID trong inbox table và bảo đảm kiểm tra inbox, ghi inbox và cập nhật nghiệp vụ nằm trong cùng transaction database. Nếu hai delivery đồng thời cùng vượt qua bước exists check, unique constraint sẽ ngăn ghi nhận trùng; consumer cần xử lý lỗi duplicate theo chính sách của ứng dụng rồi ACK khi đã xác định event đó được xử lý hoặc đã xử lý trước đó.

Các nguyên tắc triển khai:

- Mỗi event có một ID ổn định, duy nhất từ producer.
- Consumer ghi nhận ID đã xử lý trong cùng transaction với thay đổi nghiệp vụ.
- Chỉ ACK sau khi transaction nghiệp vụ thành công.
- Với lỗi tạm thời, dùng retry có backoff và giới hạn số lần thử.
- Với lỗi không thể khôi phục, chuyển message tới dead-letter queue hoặc lưu bản ghi lỗi để xử lý thủ công.
- Theo dõi số lần redelivery, độ dài queue, số message chưa ACK và tuổi message lâu nhất.
- Không giả định reconnect tự khôi phục một phản hồi đã gửi khi session trước đó không còn tồn tại.

## 10. Kiểm tra khi triển khai Spring với broker relay

Khi bật broker relay, cần kiểm tra các cấu hình và trạng thái sau:

1. Broker đã bật STOMP listener đúng host/port và cho phép kết nối từ Spring.
2. Credentials của system connection và các client connection được cấu hình theo môi trường, không dùng tài khoản guest mặc định ở production.
3. Prefix relay trong Spring khớp với destination mà broker hiểu.
4. Broker có bật persistence, queue durability, durable subscription và replication theo yêu cầu nghiệp vụ.
5. ACK/NACK, receipt, transaction và các header mở rộng được kiểm thử trực tiếp qua STOMP client thật.
6. Broker restart, network interruption, client disconnect, consumer crash và redelivery được mô phỏng trong môi trường thử nghiệm.
7. Ứng dụng theo dõi trạng thái broker relay. Spring phát **BrokerAvailabilityEvent** khi broker khả dụng hoặc mất kết nối; thành phần gửi message nên sẵn sàng xử lý **MessageDeliveryException** khi broker không khả dụng.
8. Có timeout cho receipt và xử lý trường hợp không nhận được receipt; không chờ vô hạn.
9. Dữ liệu nghiệp vụ có cơ chế đối soát hoặc phát lại nếu cần khôi phục sau sự cố.

Không nên chỉ kiểm tra happy path bằng cách gửi một message và thấy client nhận được. Hãy thử cả trường hợp broker dừng giữa lúc gửi, consumer dừng trước ACK, consumer dừng sau khi ghi database nhưng trước ACK, và publisher không nhận được receipt.

## 11. Checklist chọn cơ chế theo yêu cầu

| Yêu cầu | Cơ chế nên đánh giá |
|---|---|
| Client cần biết broker đã xử lý frame SEND | Header **receipt** và RECEIPT từ broker |
| Consumer chỉ xác nhận sau khi xử lý xong | SUBSCRIBE với **ack:client-individual** hoặc mode phù hợp |
| Consumer muốn báo xử lý thất bại | **NACK**, kết hợp retry/requeue/dead-letter theo broker |
| Nhiều SEND và ACK phải commit cùng nhau tại broker | **BEGIN/COMMIT/ABORT**, nếu broker hỗ trợ transaction |
| Giữ message khi consumer offline | Durable queue hoặc durable subscription |
| Giữ message qua broker restart | Persistent message cùng durable storage/queue và cấu hình broker phù hợp |
| Không mất event khi DB commit nhưng broker gửi lỗi | Transactional Outbox hoặc cơ chế tích hợp giao dịch tương đương |
| Chịu được redelivery và duplicate | Idempotency, inbox/deduplication và retry policy |
| Dùng Spring simple broker | Chỉ dùng cho luồng messaging cơ bản; không dựa vào ACK/receipt hoặc lưu bền |

Trước khi chốt kiến trúc, hãy viết rõ cần bảo đảm điều gì: frame đã tới broker, message đã được lưu, consumer đã nhận, consumer đã xử lý, hay database và message broker cùng commit. Mỗi yêu cầu nằm ở một ranh giới khác nhau và có thể cần một cơ chế riêng.

## Tài liệu tham khảo

- STOMP Protocol Specification 1.2 — ACK, NACK, RECEIPT và transaction frames: https://stomp.github.io/stomp-specification-1.2.html
- Spring Framework — External Broker và giới hạn simple broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html
- Spring Framework — Broker Availability Events: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html
- RabbitMQ — STOMP Plugin, destinations, persistence, durable subscriptions, ACK/NACK: https://www.rabbitmq.com/docs/stomp
- ActiveMQ Classic — STOMP protocol và persistent messages: https://activemq.apache.org/components/classic/documentation/stomp
