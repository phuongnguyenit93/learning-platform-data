# Hành trình của một thông điệp từ lúc gửi đến khi xử lý xong

## 1. Bối cảnh: vì sao cần nhìn toàn bộ vòng đời thông điệp?

Trong hệ thống bất đồng bộ, một dịch vụ có thể phát sự kiện **OrderPlaced** khi khách hàng đặt hàng, còn dịch vụ kho xử lý sự kiện đó sau vài mili giây, vài phút hoặc lâu hơn nếu đang quá tải. Hai dịch vụ không cần giữ cùng một kết nối HTTP trong suốt quá trình. **Apache ActiveMQ** đóng vai trò message broker: nhận thông điệp, lưu hoặc định tuyến theo cấu hình, rồi phân phối cho ứng dụng tiêu thụ.

Bài này theo dõi **một thông điệp cụ thể** từ khi producer tạo ra đến lúc consumer xử lý xong, bao gồm cả đường đi khi xảy ra lỗi. Các khái niệm được minh họa bằng **JMS (Java Message Service / Jakarta Messaging)**, **ActiveMQ Classic** và **ActiveMQ Artemis**. Trong cả hai broker, cần phân biệt ba sự kiện:

- **Producer gửi thành công:** phía gửi đã hoàn thành lời gọi gửi hoặc giao dịch gửi theo hợp đồng của client/broker.
- **Broker đã nhận và có thể lưu thông điệp:** thông điệp bước vào cơ chế persistence, routing và dispatch của broker.
- **Consumer xử lý thành công:** logic nghiệp vụ chạy thành công **và** consumer xác nhận kết quả với broker.

Ba mốc này không đồng nghĩa với nhau. Lời gọi gửi thành công **không chứng minh** rằng tác vụ nghiệp vụ phía nhận đã hoàn tất.

### Tình huống xuyên suốt

Giả sử dịch vụ Đơn hàng gửi thông điệp sau vào queue **orders.in**:

~~~json
{
  "eventId": "a2bc9e7e-c338-43c2-a515-64db0af03eb5",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "orderId": "ORD-2401",
  "customerId": "CUS-18",
  "occurredAt": "2026-11-17T07:00:00Z"
}
~~~

Dịch vụ Kho tiêu thụ thông điệp và giữ chỗ hàng. Khóa **eventId** là định danh nghiệp vụ ổn định dùng để chống xử lý trùng; nó khác với header **JMSMessageID** do JMS provider cấp. Dữ liệu mẫu chỉ để học, không hàm ý broker tự hiểu cấu trúc JSON hay tự xác nhận đơn hàng.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Order Service / Producer
    participant B as ActiveMQ broker
    participant Q as Queue orders.in
    participant C as Inventory / Consumer
    participant D as Inventory DB

    P->>B: send(OrderPlaced, PERSISTENT)
    B->>B: Kiểm tra quyền, routing, lưu theo cấu hình
    B->>Q: Đặt thông điệp vào hàng đợi
    B-->>P: Hoàn tất send/commit
    B->>C: Dispatch thông điệp
    C->>D: Xử lý + ghi dấu eventId trong transaction DB
    D-->>C: COMMIT thành công
    C->>B: JMS acknowledgment / session commit
    B->>Q: Đánh dấu thông điệp đã được tiêu thụ
~~~

Sơ đồ thể hiện **đường đi thành công**. Khi lỗi xảy ra giữa các bước, broker và ứng dụng cần phối hợp redelivery, retry, dead-letter queue (DLQ) và idempotency.

## 2. Bước 1 — Producer tạo thông điệp có thể nhận diện và xử lý

Trước khi gửi, producer phải quyết định **gửi đi đâu**, **nội dung là gì**, **độ bền cần thiết** và **consumer nhận diện nghiệp vụ ra sao**.

| Thành phần | Vai trò trong hành trình | Lưu ý thiết kế |
| --- | --- | --- |
| Destination | Queue hoặc topic nơi producer gửi | Tên logic phải khớp cấu hình routing của broker |
| Body | Payload: TextMessage, BytesMessage, v.v. | Ưu tiên định dạng rõ schema và version |
| eventId | Định danh sự kiện do ứng dụng phát sinh | Giữ nguyên khi ứng dụng retry hoặc gửi lại cùng sự kiện |
| JMSMessageID | ID được JMS provider cấp khi gửi | Hữu ích để truy vết broker; không thay thế eventId xuyên hệ thống |
| JMSCorrelationID | Liên hệ thông điệp với request/workflow | Đặc biệt hữu ích với request–reply |
| Properties | Metadata để lọc/route, như eventType | Không đưa dữ liệu mật vào metadata nếu không cần |
| Delivery mode | PERSISTENT hoặc NON_PERSISTENT | Chỉ định chính sách độ bền mong muốn |
| TTL / expiration | Thời hạn thông điệp còn có ý nghĩa | Hết hạn khác với lỗi xử lý và có thể đi expiry queue |
| Priority | Gợi ý ưu tiên dispatch | Không xem đây là cam kết thứ tự tuyệt đối |

**Thiết kế hợp đồng sự kiện:** consumer cần biết cách kiểm tra **eventType**, **schemaVersion**, các trường bắt buộc và cách từ chối phiên bản không tương thích. Broker chỉ vận chuyển; broker không bảo đảm ý nghĩa nghiệp vụ của JSON.

Ví dụ, **OrderPlaced** là một sự kiện đã xảy ra; còn **ReserveInventory** là lệnh yêu cầu làm việc. Nếu dùng tên sự kiện, consumer nên có khả năng phục hồi khi gặp sự kiện lặp. Nếu dùng lệnh, cần định nghĩa rõ ai được phép thực thi, khi nào timeout và cách trả kết quả.

### Thời điểm phát sự kiện so với database

Nếu dịch vụ Đơn hàng lưu order vào database rồi mới gửi JMS, có hai lỗi đối xứng:

1. Database đã commit nhưng ứng dụng chết trước khi gửi: order tồn tại, event chưa được phát.
2. Event đã gửi nhưng transaction database thất bại: consumer có thể xử lý một order không tồn tại.

**Transactional outbox** giải quyết khoảng hở phổ biến này: ghi bản ghi order và outbox trong **cùng transaction database**; một tiến trình khác đọc outbox và gửi JMS, sau đó ghi nhận đã phát. Tiến trình có thể gửi lặp nếu chết giữa lúc broker nhận và lúc đánh dấu outbox; do đó **eventId ổn định** và consumer **idempotent** vẫn bắt buộc. Local JMS transaction tự nó không làm transaction của database thành transaction nguyên tử với broker.

## 3. Bước 2 — Producer gửi và broker tiếp nhận

Trình tự thường thấy là:

1. Client JMS tạo kết nối đến broker và xác thực nếu bật bảo mật.
2. Client tạo destination và message, chọn delivery mode/TTL/priority.
3. Client gọi **send**; nếu dùng session transacted, gọi thêm **commit** để hoàn tất transaction JMS.
4. Broker kiểm tra quyền gửi, khả năng nhận, routing và chính sách tài nguyên.
5. Với message cần lưu bền, broker sử dụng cơ chế persistence theo cấu hình; khi broker hoàn tất send/commit theo hợp đồng, producer nhận kết quả.

**PERSISTENT** yêu cầu JMS provider nỗ lực duy trì message qua sự cố broker theo bảo đảm của provider và cấu hình thực tế. Nó **không** đồng nghĩa mọi bản sao dữ liệu đã được đồng bộ sang máy khác, cũng không biến xử lý end-to-end thành exactly-once. Muốn có khả năng phục hồi khi cả node hỏng, cần xem thêm topology HA, storage, replication hoặc shared store và kiểm thử failover.

**NON_PERSISTENT** có thể giảm chi phí lưu trữ nhưng tăng rủi ro mất message khi sự cố. Chọn mode dựa vào tác động nghiệp vụ: đặt hàng, thanh toán và biến động tồn kho thường cần độ bền cao; thông báo trạng thái tạm thời có thể chấp nhận đánh đổi.

### Khi send thất bại hoặc không rõ kết quả

Nếu producer timeout sau khi broker đã nhận, client có thể không biết message đã được chấp nhận hay chưa. Gửi lại một lần nữa có thể tạo **hai bản giao cùng nội dung**. Vì vậy:

- Retry ở producer nên giữ cùng **eventId**, kèm timeout/backoff có giới hạn.
- Consumer phải kiểm tra trùng ở ranh giới thực hiện side effect.
- Ghi log **eventId**, **JMSMessageID**, destination, kết quả send/commit và thời gian để đối soát.
- Không dựa vào việc lời gọi gửi trả về thành công để báo rằng kho đã giữ hàng xong.

### Transaction JMS có phạm vi nào?

Một JMS session **transacted** gom các send và receive trên session đó vào transaction JMS. **commit** xác nhận những thao tác đó; **rollback** hoàn tác phần chưa commit và khiến message đã nhận có thể được phát lại. Nó **không tự động bao trùm** JDBC transaction, HTTP call, email hoặc thanh toán bên ngoài. Kết hợp nhiều hệ thống đòi hỏi thiết kế riêng như outbox, inbox/idempotency hoặc một cơ chế transaction phân tán được hỗ trợ và vận hành đúng.

## 4. Bước 3 — Broker quyết định đường đi: queue, topic và routing

### Queue: phân công một công việc cho một consumer

Với **point-to-point queue**, mỗi message trong queue thường được phân cho **một** consumer trong nhóm đang nhận từ queue đó. Nếu có ba instance Inventory cùng đọc **orders.in**, một event không phải được xử lý bởi cả ba instance; broker phân phối để chia tải.

~~~mermaid
flowchart LR
    P[Order Producer] --> Q[(orders.in)]
    Q --> C1[Inventory instance A]
    Q --> C2[Inventory instance B]
    Q --> C3[Inventory instance C]
~~~

Đây là hình thức **competing consumers**. Thông điệp chưa được xác nhận vẫn có thể cần redelivery khi consumer ngắt kết nối hoặc rollback. Số lượng consumer ảnh hưởng thông lượng, nhưng cũng làm tăng mức song song và độ phức tạp của thứ tự xử lý.

### Topic: phát sự kiện đến nhiều nhóm quan tâm

Với **publish/subscribe topic**, message có thể được phân phối đến nhiều subscription, ví dụ Inventory, Notification và Analytics. Mỗi subscription có tiến độ nhận và xác nhận riêng; một subscriber xử lý xong không chứng minh hai subscriber còn lại đã xong.

~~~mermaid
flowchart LR
    P[Order Producer] --> T((orders.events))
    T --> I[Inventory subscription]
    T --> N[Notification subscription]
    T --> A[Analytics subscription]
~~~

Với subscriber **non-durable**, message xuất hiện khi subscriber offline thường không được giữ lại riêng cho nó. Với **durable subscription**, broker có thể giữ message dành cho subscription ngay cả khi client tạm thời ngắt kết nối, miễn subscription đã được tạo và cấu hình lưu trữ còn phù hợp. Durable subscription không phải lịch sử vô hạn: retention, TTL, quota và lifecycle subscription vẫn quan trọng.

### ActiveMQ Classic và Artemis: cùng ý tưởng, mô hình bên trong khác nhau

| Góc nhìn | ActiveMQ Classic | ActiveMQ Artemis |
| --- | --- | --- |
| Giao diện ứng dụng | Hỗ trợ JMS queue/topic | Hỗ trợ JMS queue/topic cùng các giao thức khác tùy cấu hình |
| Tổ chức destination | Queue và topic là các destination quen thuộc | **Address** định tuyến đến **queue** được bind theo routing type |
| Point-to-point | JMS queue | Thường được ánh xạ tới routing **ANYCAST** |
| Publish/subscribe | JMS topic và subscription | Thường được ánh xạ tới routing **MULTICAST**, mỗi subscription có queue nhận |
| Cấu hình retry/DLQ | Kết hợp chính sách redelivery của client/broker và dead-letter strategy | Thường dùng **address-settings** như redelivery-delay, max-delivery-attempts, dead-letter-address |
| Chi tiết vận hành | Phụ thuộc phiên bản và cấu hình Classic | Phụ thuộc phiên bản, giao thức và cấu hình Artemis |

Ở Artemis, **address** là nơi thông điệp được route; **queue** là nơi thông điệp chờ consumer. ANYCAST hướng một lần phân phối đến queue phù hợp; MULTICAST chuyển bản phân phối đến các queue subscription phù hợp. Một address có thể được cấu hình nhiều routing type, vì thế khi tạo destination hoặc dùng giao thức ngoài JMS, cần khai báo rõ mong muốn để tránh route ngoài ý định.

Không nên sao chép nguyên cấu hình Classic sang Artemis. Hai sản phẩm có API ứng dụng tương tự ở tầng JMS nhưng tên thuộc tính, mô hình routing, cách quản lý subscription và hành vi của từng phiên bản có khác biệt.

### Thứ tự nhận thông điệp có được giữ nguyên?

Broker có thể duy trì thứ tự trong những điều kiện nhất định, nhưng **không nên thiết kế nghiệp vụ dựa vào FIFO tuyệt đối** khi có nhiều producer/consumer, priority, prefetch, retry, redelivery hoặc failover. Hai message liên tiếp của một order có thể hoàn tất nghiệp vụ ngược thứ tự khi xử lý song song. Nếu thứ tự quan trọng theo **orderId**, cần chiến lược tuần tự hóa theo khóa, grouping/partition, kiểm tra version trong database hoặc từ chối cập nhật trạng thái lùi.

## 5. Bước 4 — Broker dispatch, consumer nhận và bắt đầu xử lý

Sau khi route, message ở trạng thái **sẵn sàng phân phối** hoặc đang chờ do chưa có consumer, broker bị giới hạn tài nguyên hay consumer chưa có khả năng nhận thêm. Tùy cấu hình, broker có thể gửi trước một số message đến buffer của consumer (**prefetch/consumer window**). Điều đó tạo ra khác biệt giữa:

- **Đã được broker dispatch:** broker đã chuyển thông điệp tới client hoặc đặt nó trong vùng đệm phía client.
- **Ứng dụng đã xử lý xong:** nghiệp vụ đã kiểm tra và commit side effect.
- **Broker đã nhận acknowledgment:** broker có cơ sở kết thúc vòng đời giao thông điệp đó đối với queue/subscription.

Prefetch giúp tăng thông lượng nhưng làm giảm công bằng khi một consumer chậm ôm nhiều message; nó cũng làm việc quan sát số message “in-flight” quan trọng. **Queue depth = 0** không nhất thiết chứng minh hệ thống đã xử lý xong mọi công việc nếu message còn đang in-flight.

Consumer nên triển khai một chuỗi rõ ràng:

1. Nhận message và đọc header/properties.
2. Xác thực kiểu message, schemaVersion, eventId và dữ liệu bắt buộc.
3. Kiểm tra event đã xử lý hay chưa bằng cơ chế **idempotency** có lưu bền.
4. Thực hiện thay đổi nghiệp vụ trong transaction database.
5. Commit transaction database.
6. Chỉ sau khi nghiệp vụ đã bền vững mới **acknowledge** hoặc **commit JMS session**.

Nếu dùng listener bất đồng bộ, callback phải tôn trọng cùng thứ tự logic. Không nên kích hoạt xử lý nền rồi trả về thành công ngay khi acknowledgment ở chế độ tự động, bởi broker có thể xem message đã hoàn tất dù tác vụ nền còn chưa chạy xong.

## 6. Bước 5 — Acknowledgment và transaction quyết định “xong” nghĩa là gì

JMS cung cấp các chế độ xác nhận thường gặp:

| Chế độ | Lúc nào message được xác nhận? | Tình huống cần lưu ý |
| --- | --- | --- |
| **AUTO_ACKNOWLEDGE** | Provider tự xác nhận theo quy tắc của synchronous receive hoặc khi listener hoàn tất thành công | Đừng trả callback quá sớm khi side effect chạy ở thread khác |
| **CLIENT_ACKNOWLEDGE** | Ứng dụng gọi **acknowledge()** | Theo JMS, gọi trên một message có thể xác nhận **mọi message đã tiêu thụ trong cùng session**, không chỉ riêng message đó |
| **DUPS_OK_ACKNOWLEDGE** | Provider có thể xác nhận trễ theo lô | Cho phép tăng khả năng nhận trùng; không phù hợp khi kỳ vọng ranh giới xác nhận chặt |
| **SESSION_TRANSACTED** | **commit()** xác nhận các receive/send trong transaction JMS; **rollback()** hủy thao tác chưa commit | Phải chủ động commit/rollback; không áp dụng ack thủ công như ở non-transacted session |

Ở đường đi thành công, broker ghi nhận message của queue/subscription đã được xác nhận rồi có thể giải phóng dữ liệu theo cơ chế storage/housekeeping. **“Xử lý xong”** vì thế gồm hai nửa: **side effect đã commit** và **broker đã nhận ack/commit**.

### Điểm rơi lỗi quan trọng nhất

~~~mermaid
flowchart TD
    R[Consumer nhận message] --> D{Ghi DB thành công?}
    D -- Không --> RB[Rollback JMS]
    RB --> RE[Redelivery sau delay]
    D -- Có --> A{Commit JMS thành công?}
    A -- Có --> DONE[Broker đánh dấu hoàn tất]
    A -- Không rõ --> DUP[Có thể nhận lại message]
    DUP --> I[Tra eventId để xử lý idempotent]
    I --> A
~~~

Giả sử consumer **đã commit DB**, nhưng mất kết nối ngay trước khi commit JMS. Broker chưa chắc biết side effect đã hoàn tất và có thể gửi lại message. Nếu consumer đặt lại chỗ hàng thêm lần nữa, tồn kho sai. Vì vậy **at-least-once delivery** cần đi cùng **idempotent processing**. “Exactly once” ở kết quả nghiệp vụ phải được thiết kế ở application/database boundary; không được suy ra chỉ từ JMS acknowledgment.

## 7. Bước 6 — Khi lỗi: redelivery, backoff, DLQ và expiry

Một message có thể thất bại vì lỗi tạm thời (DB bận, mất mạng), lỗi dữ liệu vĩnh viễn (schema sai, orderId vô hiệu) hoặc lỗi consumer (bug). Không nên xử lý cả ba như nhau.

| Điểm lỗi | Broker/consumer có thể làm gì? | Việc ứng dụng cần làm |
| --- | --- | --- |
| Producer timeout sau send | Message có thể đã vào broker hoặc chưa | Retry có kiểm soát với cùng eventId |
| Consumer chết trước khi xử lý | Message chưa ack được phát lại theo chính sách | Khởi động lại, xử lý idempotent |
| DB rollback hoặc dịch vụ phụ thuộc tạm ngừng | Consumer rollback JMS, broker lên lịch redelivery | Exponential backoff hoặc delay phù hợp; giới hạn số lần |
| DB commit xong nhưng JMS commit thất bại | Message có thể xuất hiện lại | Detect eventId đã xử lý, xác nhận mà không lặp side effect |
| Message sai schema lặp lại | Rollback liên tục, có thể chặn queue | Gửi DLQ/quarantine hoặc để broker chuyển sau ngưỡng retry |
| Không có consumer | Message có thể nằm chờ đến khi consumer sẵn sàng | Quan sát backlog, age, quota và TTL |
| Message hết TTL | Broker xử lý expiration; có thể chuyển tới expiry destination | Quy định rõ nghiệp vụ với event quá hạn |

**Redelivery** là broker/client giao lại message chưa được xác nhận, thường sau rollback, connection failure hoặc session recovery. Cần phân biệt **delivery count** với số lần business logic đã chạy thành công. Header **JMSRedelivered** và property **JMSXDeliveryCount** (khi provider hỗ trợ/cung cấp) giúp chẩn đoán nhưng không thay thế eventId trong kho idempotency.

**Backoff** tránh vòng lặp lỗi nóng liên tục. Chẳng hạn delay 1 giây, 5 giây, 30 giây rồi 2 phút; số lần thực tế phụ thuộc SLA và chính sách broker. Nếu một message liên tục lỗi, broker có thể chuyển nó sang **dead-letter queue (DLQ)** khi đạt ngưỡng; cấu hình và tên đích khác nhau giữa Classic và Artemis.

**DLQ không phải nơi xóa bỏ dữ liệu lỗi.** Cần giám sát, phân loại nguyên nhân, giữ đủ metadata để truy vết, xác định có nên sửa dữ liệu/consumer rồi replay, và có quy trình ngăn replay vô hạn. Khi replay, giữ eventId của sự kiện gốc để cơ chế deduplication tiếp tục hiệu lực.

**Expiry khác DLQ:** thông điệp hết hạn vì thời gian sử dụng đã qua có thể đi **expiry address/queue** tùy cấu hình. Một message hết TTL chưa chắc đã được consumer đọc hoặc từng xảy ra exception.

### Luồng trạng thái logic của một message

| Trạng thái quan sát | Ý nghĩa | Bước kế tiếp |
| --- | --- | --- |
| CREATED | Producer đã tạo object message | SEND |
| ACCEPTED / ENQUEUED | Broker tiếp nhận và route vào queue/subscription | AVAILABLE |
| AVAILABLE | Chờ consumer có khả năng nhận | DISPATCHED |
| DISPATCHED / IN-FLIGHT | Đã chuyển cho consumer, chưa nhận ack cuối cùng | ACKED hoặc REDELIVERED |
| ACKED | JMS commit/ack hoàn tất | Hoàn tất logic trên queue/subscription đó |
| REDELIVERED | Được giao lại sau lỗi hoặc rollback | Xử lý lại theo idempotency |
| DEAD-LETTERED | Chuyển tới DLQ theo policy | Điều tra, sửa và replay nếu cần |
| EXPIRED | Vượt thời hạn hiệu lực | Xử lý expiry theo policy |

Đây là **mô hình tư duy** để học và vận hành, không phải tên trạng thái chuẩn bắt buộc mà cả Classic và Artemis đều xuất ra.

## 8. Thực hành Java JMS với ActiveMQ Artemis

Ví dụ sau dùng **Jakarta Messaging API** và Artemis JMS client tương thích. Các lớp JMS lõi là portable về khái niệm; việc tạo connection factory là chi tiết của nhà cung cấp.

**Điều kiện trước khi chạy:**

- Có Artemis broker đang lắng nghe tại **tcp://localhost:61616**, có user/password hợp lệ và destination queue **orders.in**. Nếu broker không cho tự tạo address/queue, quản trị viên phải khai báo trước queue với routing type **ANYCAST**.
- Dự án Java có dependency **jakarta.jms-api** và **artemis-jakarta-client** với các phiên bản tương thích nhau và tương thích broker. Chọn phiên bản từ BOM/tài liệu của release Artemis đang dùng; không trộn package **jakarta.jms** và **javax.jms** trong cùng đoạn code.
- Đặt environment variables **BROKER_USER** và **BROKER_PASSWORD**; tùy chọn **BROKER_URL** để thay địa chỉ local. Môi trường thật cần TLS và secret manager.

### 8.1. Producer gửi một OrderPlaced trong JMS transaction

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Objects;
import java.util.UUID;

public class OrderProducer {
    public static void main(String[] args) {
        String brokerUrl = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://localhost:61616");
        String user = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String password = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"), "Missing BROKER_PASSWORD");

        String eventId = UUID.randomUUID().toString();
        String payload = "{"
                + "\"eventId\":\"" + eventId + "\","
                + "\"eventType\":\"OrderPlaced\","
                + "\"schemaVersion\":1,"
                + "\"orderId\":\"ORD-2401\""
                + "}";

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(brokerUrl);

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue("orders.in");
            TextMessage message = context.createTextMessage(payload);
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("eventType", "OrderPlaced");
            message.setIntProperty("schemaVersion", 1);
            message.setJMSCorrelationID("order:ORD-2401");

            JMSProducer producer = context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setTimeToLive(0); // 0 = không hết hạn theo TTL JMS

            producer.send(queue, message);
            context.commit(); // send được commit trong JMS session

            System.out.println("Sent eventId=" + eventId
                    + ", JMSMessageID=" + message.getJMSMessageID());
        }
    }
}
~~~

**Chú ý:** producer tạo eventId mới ở mỗi lần chạy chương trình demo. Trong sản phẩm thật, nếu retry **cùng một sự kiện**, phải lấy lại eventId đã được lưu, không sinh UUID mới mỗi lần thử. Transaction này bảo vệ send trong phạm vi JMS, không thay thế transactional outbox nếu order được lưu trong database riêng.

### 8.2. Consumer xử lý, commit hoặc rollback

~~~java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Objects;

public class OrderConsumer {
    public static void main(String[] args) throws Exception {
        String brokerUrl = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://localhost:61616");
        String user = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String password = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"), "Missing BROKER_PASSWORD");

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(brokerUrl);

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue("orders.in");
            JMSConsumer consumer = context.createConsumer(queue);

            while (!Thread.currentThread().isInterrupted()) {
                Message message = consumer.receive(1000);
                if (message == null) {
                    continue;
                }

                try {
                    if (!(message instanceof TextMessage)) {
                        throw new IllegalArgumentException("Expected TextMessage");
                    }
                    String eventId = message.getStringProperty("eventId");
                    if (eventId == null || eventId.isBlank()) {
                        throw new IllegalArgumentException("Missing eventId");
                    }

                    TextMessage text = (TextMessage) message;
                    processForDemo(eventId, text.getText());

                    context.commit(); // chỉ xác nhận sau khi xử lý thành công
                    System.out.println("Committed eventId=" + eventId);
                } catch (Exception processingError) {
                    context.rollback(); // message có thể được redeliver
                    System.err.println("Rolled back: "
                            + processingError.getMessage());
                }
            }
        }
    }

    private static void processForDemo(String eventId, String json) {
        if (!json.contains("\"orderId\"")) {
            throw new IllegalArgumentException("Missing orderId in payload");
        }
        System.out.println("Processing eventId=" + eventId + ": " + json);
        // Thực tế: transaction DB + idempotency, xem mục 9.
    }
}
~~~

Đây là **demo đường truyền và commit/rollback**. Hàm **processForDemo** mới in ra console, chưa ghi database, chưa chống trùng; không dùng nguyên trạng cho nghiệp vụ giữ hàng hoặc thanh toán. Để kiểm tra redelivery, có thể cho hàm này ném exception tạm thời, nhưng cần bật delay/giới hạn retry ở broker để tránh vòng lặp lỗi nóng.

Nếu sử dụng **ActiveMQ Classic**, vẫn giữ logic JMS nhưng dùng **connection factory/client artifact đúng phiên bản Classic**. Classic đời cũ thường dùng **javax.jms**; các dòng mới và Artemis có những client artifact khác nhau. Kiểm tra package API và phiên bản broker trước khi copy code, không suy diễn rằng một dependency chạy được cho mọi dòng ActiveMQ.

### 8.3. Nếu không dùng JMS transaction: CLIENT_ACKNOWLEDGE

Ở chế độ non-transacted, ứng dụng có thể chủ động xác nhận:

~~~java
try (JMSContext context = factory.createContext(
        user, password, JMSContext.CLIENT_ACKNOWLEDGE)) {
    Queue queue = context.createQueue("orders.in");
    Message message = context.createConsumer(queue).receive(5000);

    if (message != null) {
        // Validate + xử lý nghiệp vụ thành công trước
        handleSuccessfully(message);
        message.acknowledge();
    }
}
~~~

Đoạn code này dùng các biến **factory**, **user**, **password** và hàm xử lý **handleSuccessfully** do ứng dụng cung cấp. Cần nhớ: **message.acknowledge()** trong CLIENT_ACKNOWLEDGE có thể xác nhận tất cả thông điệp đã tiêu thụ trong cùng session. Nếu cần ranh giới mỗi message rõ ràng, có thể dùng một session cho luồng xử lý có kiểm soát hoặc JMS transaction. Với listener tự động ack, không dùng xử lý bất đồng bộ fire-and-forget rồi trả callback sớm.

## 9. Làm cho side effect thực sự idempotent

Giả sử Inventory đã trừ số lượng trong DB nhưng JMS commit mất kết nối. Khi message được giao lại, consumer cần nhận ra **eventId đã hoàn tất** và bỏ qua side effect, sau đó vẫn commit JMS để broker kết thúc message.

Một cách thông dụng là lưu eventId theo từng consumer nghiệp vụ trong **cùng database transaction** với thay đổi tồn kho:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Pseudocode sử dụng PostgreSQL:

~~~text
BEGIN DATABASE TRANSACTION

  inserted = INSERT INTO processed_messages(consumer_name, event_id)
             VALUES ('inventory-reserver', :eventId)
             ON CONFLICT DO NOTHING

  IF inserted == 1:
      kiểm tra order và lượng tồn hợp lệ
      cập nhật reserve inventory / tồn kho
  ELSE:
      đây là event đã xử lý -> bỏ qua side effect

COMMIT DATABASE TRANSACTION

COMMIT JMS SESSION
~~~

Cả bước ghi **processed_messages** và bước cập nhật tồn kho phải nằm trong **cùng transaction database**. Nếu database rollback, cả hai cùng rollback; message chưa được JMS ack thì có thể retry. Nếu database commit nhưng JMS commit thất bại, lần nhận lại sẽ gặp bản ghi trùng và không trừ kho lần nữa. Định danh nên có scope **consumer_name** vì một sự kiện có thể được nhiều loại consumer xử lý độc lập.

Lưu ý với nghiệp vụ gọi dịch vụ bên ngoài như charge payment, gửi email hoặc gọi HTTP API: một transaction DB cục bộ **không làm cho tác dụng bên ngoài tự động idempotent**. Hãy dùng **idempotency key** tại dịch vụ đích, outbox cho lời gọi tiếp theo, hoặc workflow có khả năng reconcile/compensate.

**Không dùng mỗi bộ nhớ RAM để chống trùng.** Consumer restart, autoscaling hoặc chuyển node sẽ mất thông tin; nhiều replica cũng không chia sẻ được trạng thái chính xác.

## 10. Vận hành: biết một thông điệp đang kẹt ở đâu

Để xác định message đã đi đến chặng nào, cần quan sát theo cùng **eventId** xuyên suốt producer, broker và consumer:

| Tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| Producer send/commit failures và latency | Broker có nhận message ổn định không? |
| Queue depth / message count | Còn bao nhiêu message đang chờ xử lý? |
| Oldest-message age | Công việc lâu nhất đã chờ bao lâu? |
| Delivering/in-flight count | Message đang nằm ở consumer mà chưa được ack bao nhiêu? |
| Consumer count / processing rate | Có consumer khỏe và đủ công suất không? |
| Redelivery count, rollback rate | Consumer có liên tục thất bại cùng payload không? |
| DLQ/expiry count và age | Có message bị lỗi vĩnh viễn hoặc hết hiệu lực không? |
| Memory/paging, disk journal, connection health | Broker có bị nghẽn tài nguyên, rủi ro đầy đĩa hoặc mất kết nối không? |
| End-to-end processing latency | Từ occurredAt đến khi xử lý nghiệp vụ hoàn tất mất bao lâu? |

Một vài nguyên tắc vận hành then chốt:

- **Bảo mật:** TLS cho kết nối phù hợp, xác thực broker, phân quyền send/consume/manage theo destination, không hardcode mật khẩu, quay vòng secret và kiểm soát quyền quản trị/JMX/console.
- **Giới hạn tải:** điều chỉnh prefetch/consumer window, concurrency, producer flow control, address/queue limits và paging theo đo đạc thực tế. Consumer chậm không được làm đầy disk vô hạn.
- **Độ bền và HA:** chọn persistence phù hợp, giám sát journal/disk, hiểu failover topology, kiểm thử restart/failover có message đang in-flight; lưu ý backup/restore phải nhất quán với dữ liệu broker và subscription.
- **DLQ có chủ sở hữu:** phân quyền xem payload, đặt cảnh báo, có quy trình điều tra, xác định thời hạn giữ và replay có kiểm soát.
- **Quan sát có correlation:** log dùng **eventId**, **JMSMessageID**, **orderId** (nếu chính sách dữ liệu cho phép), tên queue/subscription, delivery count và kết quả DB/JMS commit; tránh log credential hoặc payload chứa dữ liệu cá nhân nhạy cảm.
- **Tối ưu theo SLO:** thông lượng cao không có nghĩa độ trễ thấp; theo dõi tuổi backlog, tỉ lệ thành công và thời gian xử lý thực sự từ đầu đến cuối.

### Quy trình điều tra một message “mất tích”

1. Tìm **eventId** ở outbox hoặc log producer: sự kiện đã được tạo, send và commit chưa?
2. Kiểm tra destination/routing: queue hay topic, ANYCAST/MULTICAST, subscription có tồn tại tại thời điểm publish không?
3. Xem queue depth, delivering/in-flight, consumer count, expiry và DLQ; kiểm tra còn hạn TTL hay không.
4. Tìm log consumer theo eventId: đã validate, DB commit, JMS ack/commit tới đâu?
5. Nếu đã xử lý DB nhưng message lại xuất hiện, kiểm tra bảng **processed_messages** trước khi replay.
6. Nếu cần replay, sửa nguyên nhân gốc, chọn subset message rõ ràng, giữ sự kiện gốc và theo dõi kết quả sau replay.

## 11. Bài thực hành kiểm chứng từng điểm đứt gãy

Dùng môi trường thử nghiệm độc lập với broker Artemis, queue **orders.in**, một producer và một consumer ở mục 8. Bật ghi log eventId và quan sát queue depth, in-flight, DLQ.

| Thí nghiệm | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Luồng bình thường | Chạy consumer, gửi một message hợp lệ | Consumer xử lý, JMS commit; message không còn chờ trên queue |
| Consumer chưa online | Dừng consumer rồi gửi vào queue có persistence phù hợp | Message chờ; khi consumer chạy lại sẽ được giao |
| Lỗi trước xử lý | Cố ý throw trước DB commit và rollback JMS | Message được redeliver theo policy |
| Lỗi sau DB commit | Trong phiên bản có DB/idempotency, mô phỏng mất kết nối trước JMS commit | Message có thể được giao lại, nhưng không lặp side effect |
| Poison message | Gửi payload sai schema, cấu hình retry limit + DLQ | Sau số lần cho phép, message được chuyển DLQ để điều tra |
| TTL ngắn | Gửi message TTL ngắn khi không có consumer | Message có thể hết hạn và được xử lý theo expiry policy |
| Nhiều consumer | Chạy hai consumer cùng đọc một queue | Mỗi message được phân cho một consumer tại một thời điểm; phân phối không nhất thiết cân bằng tuyệt đối |
| Hai subscription | Publish tới topic có hai durable subscriptions đã đăng ký | Mỗi subscription nhận và xác nhận độc lập |

Khi thử **đứt kết nối sau DB commit**, đừng dùng demo chỉ in console ở mục 8 để kết luận có exactly-once: phải thêm transaction DB + bảng dedup như mục 9 rồi xác nhận số lần thay đổi tồn kho.

## 12. Ghi nhớ đường đi của một thông điệp

Một thông điệp nghiệp vụ đi qua các ranh giới độ tin cậy:

**Tạo sự kiện → Gửi JMS → Broker tiếp nhận/lưu → Route vào queue/subscription → Dispatch → Consumer xử lý và commit nghiệp vụ → JMS ack/commit → Hoàn tất.**

Mỗi ranh giới có thể thất bại. Producer phải có định danh sự kiện ổn định và chiến lược retry. Broker cần persistence/routing và giới hạn tài nguyên đúng mục đích. Consumer phải kiểm tra payload, commit side effect bền vững và xử lý trùng. Redelivery và DLQ cho phép phục hồi có kiểm soát khi việc xử lý không đi theo đường thẳng.

Với **ActiveMQ Classic** lẫn **Artemis**, JMS cung cấp một ngôn ngữ chung để gửi, nhận và xác nhận message; nhưng routing, subscription, cấu hình redelivery/DLQ, storage và vận hành cần được kiểm tra trên **đúng sản phẩm, đúng phiên bản** đang triển khai.
