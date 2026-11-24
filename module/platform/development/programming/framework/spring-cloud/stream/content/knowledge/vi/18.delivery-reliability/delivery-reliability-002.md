# Thiết kế xử lý lặp an toàn (idempotency) bằng event ID

Trong hệ thống message, một sự kiện có thể được giao nhiều lần. Consumer có thể đã cập nhật database nhưng bị dừng trước khi xác nhận message; broker sẽ giao lại khi consumer kết nối trở lại. Producer cũng có thể gửi lại vì không nhận được xác nhận publish dù broker đã nhận message. Đây là những tình huống bình thường của mô hình giao nhận at-least-once.

Nếu mỗi lần nhận đều tạo một tác động mới, một đơn hàng có thể bị trừ tồn kho hai lần, một khoản thanh toán có thể được ghi nhận hai lần hoặc một email có thể được gửi lặp. **Idempotency** giúp một sự kiện có thể được xử lý lặp mà tác động nghiệp vụ cuối cùng vẫn tương đương với một lần xử lý. Một cách phổ biến là gắn `eventId` ổn định cho mỗi sự kiện và lưu dấu những ID đã được consumer xử lý.

Bài thuộc chương **Độ tin cậy** của module `SPRING_CLOUD_STREAM`. Module sử dụng mô hình hàm `Supplier`/`Function`/`Consumer`, binding và binder cho Kafka, RabbitMQ hoặc Pulsar. Nội dung tập trung vào thiết kế event ID, lưu dấu xử lý trùng, ranh giới transaction, xử lý đồng thời, tích hợp API bên ngoài, replay và kiểm thử.

## 1. Vì sao message có thể được xử lý nhiều lần?

Một message broker không thể tự biết toàn bộ tác động nghiệp vụ đã hoàn tất trong database hoặc dịch vụ ngoài. Ví dụ:

1. Consumer nhận `OrderPlaced`.
2. Consumer ghi giảm tồn kho vào database.
3. Database commit thành công.
4. Tiến trình bị dừng trước khi broker nhận được acknowledgement hoặc offset commit.
5. Message được giao lại sau khi consumer khởi động.
6. Consumer ghi giảm tồn kho lần nữa nếu không có cơ chế chống trùng.

```text
Broker                Consumer                  Database
  |                       |                         |
  |---- OrderPlaced ----->|                         |
  |                       |---- decrement stock --->|
  |                       |                         | commit
  |                       |<------ success ----------|
  |                       X process stops            |
  |                                                  |
  |---- redeliver ------->|                         |
  |                       |---- decrement again ---->|  <-- duplicate effect
```

Việc broker giao lại không nhất thiết là lỗi của broker. Consumer có thể đã hoàn tất một phần công việc nhưng chưa hoàn tất toàn bộ giao thức xác nhận. Tương tự, producer có thể retry publish sau timeout và tạo ra hai bản ghi cùng một sự kiện nếu không dùng event ID ổn định.

Do đó, consumer nên giả định message có thể đến ít nhất một lần và đôi khi nhiều lần. Cơ chế idempotency đặt tại ranh giới tác động nghiệp vụ để lần giao lại không tạo thêm hiệu ứng.

## 2. Idempotency là gì?

Một thao tác idempotent có tính chất: thực hiện một lần hay nhiều lần với cùng một định danh và cùng nội dung nghiệp vụ thì trạng thái kết quả không thay đổi sau lần thực hiện đầu tiên.

Ví dụ, đặt trạng thái đơn hàng thành `CONFIRMED` thường có thể idempotent nếu thao tác chỉ cập nhật về cùng một trạng thái. Ngược lại, lệnh `balance = balance - amount` không idempotent: chạy hai lần sẽ trừ tiền hai lần.

| Thao tác | Tính chất | Lý do |
|---|---|---|
| Đặt trạng thái đơn hàng thành `CONFIRMED` | Có thể idempotent | Lặp lại cùng giá trị không làm thay đổi kết quả sau lần đầu |
| Tăng bộ đếm thêm 1 | Không idempotent | Mỗi lần gọi làm bộ đếm tăng thêm |
| Trừ tồn kho theo số lượng | Không idempotent nếu không kiểm tra event | Giao lại message có thể trừ thêm lần nữa |
| Ghi một bản ghi với khóa duy nhất là `eventId` | Có thể idempotent | Unique constraint ngăn tạo bản ghi trùng |
| Gửi email qua API không có idempotency key | Không bảo đảm idempotent | Timeout có thể khiến ứng dụng gửi lại email đã được nhà cung cấp chấp nhận |

Idempotency không có nghĩa mọi lần gọi đều trả về cùng response ở tầng kỹ thuật. Một lần đầu có thể trả `APPLIED`, lần sau trả `DUPLICATE`; điều cần giữ là tác động nghiệp vụ chỉ được áp dụng một lần.

## 3. Event ID phải ổn định qua mọi lần gửi lại

`eventId` là định danh duy nhất của một sự kiện cụ thể. Producer nên tạo ID khi sự kiện được hình thành và giữ nguyên ID đó qua các lần retry publish. Consumer sử dụng ID này để nhận biết các bản giao lại của cùng một sự kiện.

Ví dụ payload:

```json
{
  "eventId": "018f4a1e-7b2d-7c40-9f42-8a53e8a2d011",
  "eventType": "OrderPlaced",
  "occurredAt": "2026-11-24T09:15:00Z",
  "orderId": "ORD-2026-0042",
  "customerId": "CUS-018",
  "items": [
    { "sku": "COFFEE-01", "quantity": 2 }
  ]
}
```

Khi producer retry gửi sự kiện này, nó phải gửi lại cùng `eventId`, không tạo ID mới ở mỗi lần gọi `send`. Nếu mỗi lần retry lại sinh UUID mới, consumer sẽ coi các bản gửi lại là sự kiện khác và cơ chế deduplication không còn tác dụng.

Một event ID tốt có các đặc điểm:

- Duy nhất trong phạm vi producer hoặc nguồn sự kiện được xác định.
- Bất biến trong toàn bộ vòng đời của sự kiện.
- Được tạo trước khi publish lần đầu và lưu bền vững nếu producer cần retry sau restart.
- Không phụ thuộc vào thời điểm consumer nhận message.
- Có thể được truyền trong payload hoặc header theo hợp đồng đã thống nhất.

Nếu nhiều producer có thể tạo cùng một giá trị ID, hãy kết hợp `source` hoặc `producerId` vào khóa deduplication. Ví dụ khóa là `(source, eventId)` thay vì chỉ `eventId`.

## 4. Phân biệt event ID với business key và correlation ID

Ba loại định danh thường xuất hiện cùng nhau nhưng có mục đích khác nhau:

| Định danh | Đại diện cho | Ví dụ | Dùng để |
|---|---|---|---|
| `eventId` | Một lần phát sinh sự kiện | `evt-8f2...` | Deduplication và truy vết một message logic |
| `orderId` | Một thực thể nghiệp vụ | `ORD-42` | Nhận diện đơn hàng, áp dụng quy tắc theo aggregate |
| `correlationId` | Một luồng tương tác hoặc quy trình | `corr-91a...` | Liên kết log và message qua nhiều dịch vụ |

Một đơn hàng có thể phát nhiều event: `OrderPlaced`, `OrderConfirmed`, `OrderShipped`. Mỗi event cần `eventId` riêng nhưng có thể dùng chung `orderId` và `correlationId` tùy quy trình.

Không nên dùng `orderId` làm event ID nếu cùng một đơn hàng có thể phát nhiều sự kiện cùng loại hoặc nhiều lần cập nhật. Khi đó, deduplication theo `orderId` có thể loại nhầm sự kiện hợp lệ.

## 5. Lưu dấu event ID bằng Inbox pattern

Một cách triển khai phổ biến là tạo bảng inbox để lưu những sự kiện đã được consumer áp dụng. Khóa duy nhất kết hợp tên consumer logic với event ID, vì hai consumer độc lập có thể cần xử lý cùng một sự kiện.

Ví dụ schema PostgreSQL:

```sql
CREATE TABLE processed_message (
    consumer_name  VARCHAR(120) NOT NULL,
    source_name    VARCHAR(120) NOT NULL,
    event_id       VARCHAR(160) NOT NULL,
    payload_hash   VARCHAR(128),
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, source_name, event_id)
);
```

`consumer_name` là tên ổn định của một vai trò xử lý, chẳng hạn `inventory-projection`. `source_name` xác định nguồn tạo event. `event_id` nhận diện sự kiện. Khóa chính ngăn cùng một consumer áp dụng cùng một event hai lần.

Nếu hai consumer độc lập cùng đọc `orders.events`, chúng phải có namespace inbox khác nhau. Ví dụ `inventory-projection` và `analytics-projection` đều được phép xử lý cùng `eventId`, vì đó là hai tác động nghiệp vụ khác nhau.

Không nên dùng tên pod hoặc hostname làm `consumer_name`; các giá trị này thay đổi khi triển khai và sẽ làm mỗi replica có một vùng deduplication riêng. Tên consumer phải đại diện cho nhóm logic dùng chung database hoặc kho deduplication.

## 6. Ghi inbox và cập nhật nghiệp vụ trong cùng transaction

Điều quan trọng nhất là thao tác ghi dấu `eventId` và thay đổi nghiệp vụ phải nằm trong cùng một transaction database. Nếu ghi inbox thành công nhưng cập nhật nghiệp vụ thất bại và hai thao tác không cùng transaction, lần giao lại có thể bị đánh dấu trùng dù tác động nghiệp vụ chưa hoàn tất.

Với PostgreSQL, có thể dùng `INSERT ... ON CONFLICT DO NOTHING` để xác định event đã được xử lý:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record OrderPlaced(String eventId, String source, String orderId,
                   String sku, int quantity) {}

enum ApplyResult {
    APPLIED,
    DUPLICATE
}

@Service
class InventoryEventHandler {

    private final JdbcTemplate jdbc;

    InventoryEventHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ApplyResult handle(OrderPlaced event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_message
                (consumer_name, source_name, event_id)
            VALUES (?, ?, ?)
            ON CONFLICT (consumer_name, source_name, event_id) DO NOTHING
            """,
            "inventory-projection",
            event.source(),
            event.eventId()
        );

        if (inserted == 0) {
            return ApplyResult.DUPLICATE;
        }

        jdbc.update("""
            UPDATE inventory
               SET available = available - ?
             WHERE sku = ?
            """,
            event.quantity(),
            event.sku()
        );

        return ApplyResult.APPLIED;
    }
}
```

Trong ví dụ:

1. Database thử chèn khóa `(consumer_name, source_name, event_id)`.
2. Nếu khóa đã tồn tại, `inserted` bằng `0`; handler trả `DUPLICATE` và không trừ tồn kho.
3. Nếu chèn thành công, handler cập nhật tồn kho rồi trả `APPLIED`.
4. Nếu cập nhật tồn kho thất bại, exception làm transaction rollback; bản ghi inbox vừa chèn cũng bị rollback.
5. Khi message được giao lại, thao tác có thể thử lại từ đầu.

Đảm bảo này chỉ đúng khi inbox và dữ liệu nghiệp vụ nằm trong cùng transaction manager/database transaction. Nếu cập nhật tồn kho nằm ở một database khác hoặc gọi một API bên ngoài, transaction local không thể tự rollback tác động đã xảy ra ở hệ thống kia.

Trong ví dụ production, cần kiểm tra số dòng được cập nhật ở bảng `inventory`, xử lý SKU không tồn tại và kiểm tra số lượng hợp lệ. Đoạn code tập trung minh họa ranh giới transaction của inbox; các quy tắc nghiệp vụ cần được bổ sung.

## 7. Vì sao unique constraint quan trọng khi xử lý đồng thời?

Một cách triển khai đơn giản có thể làm như sau:

```java
if (!repository.existsByEventId(event.eventId())) {
    repository.save(new ProcessedMessage(event.eventId()));
    applyBusinessChange(event);
}
```

Đoạn code có race condition. Hai thread có thể cùng kiểm tra `exists` và đều nhận `false` trước khi một thread ghi dữ liệu. Sau đó cả hai cùng thực hiện tác động nghiệp vụ.

Unique constraint ở database là lớp bảo vệ cuối cùng vì việc kiểm tra và chèn khóa được database đồng bộ hóa. Có thể bắt lỗi duplicate key, hoặc dùng cú pháp như `ON CONFLICT DO NOTHING` để xử lý rõ ràng. Không dựa riêng vào kiểm tra trước trong Java.

Khi dùng JPA, cần bảo đảm unique constraint thực sự tồn tại trong database và transaction được quản lý đúng. Một exception unique violation có thể đánh dấu transaction rollback-only; không phải lúc nào cũng an toàn để bắt exception rồi tiếp tục dùng transaction đó. Cách insert-ignore phụ thuộc database và API repository.

## 8. Event ID trùng nhưng payload khác nhau là bất thường

Nếu hai message có cùng `eventId` nhưng nội dung khác nhau, không nên tự động coi message sau là duplicate hợp lệ. Điều này có thể cho thấy producer tái sử dụng ID, lỗi serialize, dữ liệu bị sửa hoặc một sự cố bảo mật.

Có thể lưu thêm `payload_hash` hoặc schema version để phát hiện trường hợp này:

```text
Khóa inbox: (consumer_name, source_name, event_id)
Payload hash lần đầu:  7b2f...
Payload hash lần sau:  91ac...

Cùng event ID nhưng hash khác
          |
          v
  Ghi nhận IDENTITY_CONFLICT
          |
          v
  Cách ly và điều tra
```

Hash nên được tính từ biểu diễn payload đã chuẩn hóa hoặc từ bytes bất biến của message theo hợp đồng. JSON có thể khác thứ tự thuộc tính nhưng vẫn cùng dữ liệu logic; nếu hash raw bytes, hai JSON tương đương về ngữ nghĩa có thể cho hash khác nhau. Cần chọn cách canonicalization phù hợp.

Không ghi đè payload hash ban đầu bằng hash mới. Lưu dấu xung đột để điều tra và không áp dụng tác động nghiệp vụ lần hai.

## 9. Event ID trong payload hay message header?

Có thể truyền event ID trong payload hoặc header. Mỗi cách có ưu và nhược điểm:

| Vị trí | Ưu điểm | Lưu ý |
|---|---|---|
| Payload JSON | ID đi cùng hợp đồng sự kiện và dễ lưu trữ/phát lại | DTO phải có trường event ID; consumer cần deserialize payload |
| Message header | Tách metadata khỏi dữ liệu nghiệp vụ; có thể dùng `Message<T>` | Header mapping khác nhau giữa binder; cần bảo đảm ID được giữ qua broker |
| Cả hai | Có thể đối chiếu hợp đồng và metadata | Phải quy định giá trị nào là nguồn chuẩn; nếu lệch nhau cần từ chối |

Ví dụ tạo message có event ID trong header:

```java
import java.util.UUID;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderPayload(String orderId, String status) {}

OrderPayload payload = new OrderPayload("ORD-42", "PLACED");
String eventId = UUID.randomUUID().toString(); // tạo một lần cho sự kiện này

Message<OrderPayload> message = MessageBuilder
    .withPayload(payload)
    .setHeader("eventId", eventId)
    .setHeader("eventType", "OrderPlaced")
    .build();
```

Producer phải tạo message một lần và giữ nguyên header khi retry publish. Lưu `eventId` cùng outbox record hoặc trạng thái phát bền vững để lần retry sau restart vẫn dùng lại ID đó. Không đặt việc sinh UUID bên trong một đoạn code được gọi lại mỗi lần retry. Nếu consumer cần dedup sau khi message đi qua nhiều broker hoặc connector, hãy kiểm tra header có được map và bảo toàn hay không; payload ID thường dễ mang qua các hệ thống hơn.

## 10. Consumer Spring Cloud Stream sử dụng event ID

Một consumer có thể nhận DTO bằng functional model:

```java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryConsumerConfiguration {

    @Bean
    Consumer<OrderPlaced> inventoryProjection(
            InventoryEventHandler handler) {
        return event -> handler.handle(event);
    }
}
```

Cấu hình binding:

```yaml
spring:
  cloud:
    function:
      definition: inventoryProjection
    stream:
      bindings:
        inventoryProjection-in-0:
          destination: orders.placed
          group: inventory-projection
          content-type: application/json
```

Binding group giúp các replica của cùng consumer logic chia tải. Inbox table dùng cùng `consumer_name` cho tất cả replica trong nhóm để chúng phối hợp chống trùng. Nếu mỗi replica dùng tên khác nhau, cùng một event có thể được áp dụng một lần trên mỗi replica.

Nếu có consumer analytics độc lập, consumer đó cần namespace inbox riêng như `analytics-projection`. Việc một consumer đã xử lý event không được ngăn consumer khác xử lý cùng event cho mục đích nghiệp vụ khác.

## 11. Acknowledgement phải xảy ra sau khi transaction nghiệp vụ hoàn tất

Một nguyên tắc quan trọng: không xác nhận message đã xử lý trước khi transaction lưu tác động nghiệp vụ và dấu inbox commit thành công.

```text
Nhận message
    |
    v
Mở DB transaction
    |
    v
Insert event ID vào inbox
    |
    +---- đã tồn tại ----> không áp dụng lại
    |
    v
Áp dụng thay đổi nghiệp vụ
    |
    v
Commit transaction
    |
    v
Hoàn tất handler
    |
    v
Binder/broker xác nhận theo cấu hình
```

Nếu tiến trình dừng sau commit nhưng trước acknowledgement, broker có thể giao lại message. Inbox nhận ra event đã được áp dụng và handler không lặp tác động. Sau đó consumer hoàn tất lần giao lại để binder xác nhận.

Nếu acknowledgement xảy ra trước khi transaction commit và tiến trình dừng giữa hai bước, message có thể bị xem là đã xử lý trong khi thay đổi database chưa được lưu. Cách cấu hình acknowledgement và commit offset phụ thuộc binder; cần xác minh thứ tự thực tế trong phiên bản sử dụng.

## 12. Idempotency với tác động bên ngoài database

Inbox transaction chỉ bảo vệ được các thay đổi nằm trong cùng transaction database. Nếu handler gọi payment API, gửi email hoặc gọi một dịch vụ khác, có một khoảng lỗi khó tránh:

1. Dịch vụ ngoài đã thực hiện tác động.
2. Consumer bị timeout trước khi nhận response hoặc trước khi ghi inbox.
3. Message được giao lại.
4. Consumer gọi dịch vụ ngoài lần nữa.

Có ba cách tiếp cận thường dùng:

- **Idempotency key ở API đích:** gửi `eventId` hoặc một key nghiệp vụ ổn định; dịch vụ nhận lưu key và trả lại kết quả cũ khi request lặp.
- **Command/outbox:** ghi yêu cầu cần gửi vào database cùng transaction nghiệp vụ; worker phát yêu cầu và đánh dấu trạng thái, đồng thời sử dụng idempotency key ở đích.
- **Saga/compensation:** nếu không thể làm thao tác idempotent, thiết kế bước bù trừ và trạng thái quy trình để xử lý trường hợp tác động một phần.

Không đánh dấu event hoàn tất trong inbox trước khi tác động bên ngoài đã có trạng thái xác định, trừ khi trạng thái đó chính là “đã lên lịch thực hiện” và công việc ngoài được lưu bền vững trong outbox/job table. Nếu ghi inbox trước, gọi API ngoài sau rồi crash, lần giao lại có thể bị bỏ qua trong khi API chưa từng được gọi.

## 13. Kết hợp Inbox và Outbox

Inbox bảo vệ consumer khỏi xử lý trùng. Outbox bảo vệ producer khỏi khoảng lỗi giữa commit database và publish message.

Ví dụ service tạo đơn hàng:

```text
Một DB transaction
  +-- INSERT order
  +-- INSERT outbox(event_id, payload, status='NEW')
              |
              v
       Outbox relay đọc bản ghi
              |
              v
       Publish message đến broker
              |
              v
       Đánh dấu bản ghi đã gửi
```

Nếu relay publish thành công nhưng crash trước khi đánh dấu `SENT`, relay có thể publish lại cùng outbox record. Vì vậy, outbox không tự bảo đảm chỉ gửi một lần; nó bảo đảm sự kiện được lưu cùng transaction và có thể được phát lại. Consumer vẫn cần event ID và inbox để chống tác động trùng.

Khi thiết kế hệ thống, producer tạo event ID một lần và lưu trong outbox. Relay không tạo ID mới khi retry. Consumer dùng cùng ID để deduplicate. Hai pattern bổ sung cho nhau ở hai đầu của luồng message.

## 14. Phạm vi và thời gian lưu dấu deduplication

Inbox table không thể tăng vô hạn mà không có chính sách lưu trữ. Tuy nhiên, xóa dấu event ID quá sớm sẽ cho phép một message cũ được xử lý lại.

Thời gian giữ dữ liệu cần lớn hơn hoặc bằng khoảng thời gian hệ thống có thể replay message, bao gồm:

- Retention của topic hoặc queue.
- Thời gian lưu DLQ và retry destination.
- Khoảng thời gian vận hành có thể phát lại sau sự cố.
- Thời gian backup/restore và phục hồi disaster recovery.
- Yêu cầu audit hoặc đối soát nghiệp vụ.

Nếu Kafka topic cho phép đọc lại dữ liệu trong 30 ngày nhưng inbox chỉ giữ 7 ngày, replay từ ngày thứ 20 có thể áp dụng lại tác động nghiệp vụ. Cần đồng bộ retention của broker và inbox.

Với hệ thống có lượng event lớn, có thể partition inbox theo thời gian, archive các bản ghi cũ hoặc lưu dấu trong kho có TTL. Việc dọn dữ liệu phải dựa trên replay horizon đã thống nhất. Không xóa chỉ vì bản ghi đã cũ theo một ngưỡng tùy ý.

## 15. Replay có chủ đích và phiên bản consumer

Đôi khi cần chạy lại toàn bộ lịch sử để xây dựng lại projection hoặc sửa lỗi logic. Nếu dùng cùng namespace inbox, tất cả event cũ có thể bị nhận diện là đã xử lý và bị bỏ qua.

Có thể dùng một `consumer_name` hoặc projection version mới cho lần rebuild, ví dụ:

| Mục đích | Namespace inbox |
|---|---|
| Projection tồn kho hiện tại | `inventory-projection-v1` |
| Rebuild projection bằng logic mới | `inventory-projection-v2` |
| Analytics độc lập | `analytics-projection-v1` |

Chỉ thay namespace khi thực sự muốn áp dụng lại lịch sử vào một trạng thái mới. Không tạo namespace mới cho mỗi lần restart vì sẽ vô hiệu hóa deduplication. Replay các tác động bên ngoài như thanh toán hoặc gửi email cần chính sách riêng; không nên dùng cơ chế rebuild projection để thực hiện lại giao dịch thực.

## 16. Khác biệt broker không loại bỏ nhu cầu idempotency

Kafka, RabbitMQ và Pulsar có cơ chế xác nhận và giao lại khác nhau, nhưng consumer vẫn cần an toàn với duplicate:

| Broker | Tình huống có thể dẫn đến xử lý lại | Điểm cần kiểm soát |
|---|---|---|
| Kafka | Consumer xử lý xong nhưng offset chưa commit; rebalance hoặc restart làm record được đọc lại | Commit offset gắn với kết quả xử lý; dùng event ID và inbox; hiểu phạm vi transaction Kafka |
| RabbitMQ | Consumer channel/connection đóng trước khi ack; message chưa ack được requeue | Ack sau khi transaction hoàn tất; kiểm tra redelivery; dùng inbox để bảo vệ tác động |
| Pulsar | Consumer không ack hoặc ack timeout; subscription giao lại message | Ack sau xử lý; hiểu subscription và redelivery policy; dùng event ID ổn định |

Kafka có các cơ chế transaction và exactly-once semantics cho một số luồng Kafka-to-Kafka, nhưng chúng không tự bao trùm một database ngoài hoặc API thanh toán. RabbitMQ publisher confirms và consumer acknowledgements cũng không tạo transaction chung với database nghiệp vụ. Pulsar transactions có phạm vi và hỗ trợ riêng; không tự bảo đảm một API ngoài được gọi đúng một lần.

Vì vậy, idempotency ở tầng nghiệp vụ vẫn quan trọng ngay cả khi broker cung cấp tính năng giao nhận mạnh.

## 17. Kiểm thử idempotency

Một bộ test tốt cần kiểm tra không chỉ việc cùng event ID được gửi hai lần, mà cả tình huống cạnh tranh và crash ở ranh giới transaction:

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Cùng event gửi hai lần tuần tự | Gọi handler hai lần với cùng ID | Tác động nghiệp vụ chỉ xảy ra một lần |
| Hai event khác ID | Gửi hai sự kiện hợp lệ khác nhau | Cả hai đều được áp dụng |
| Hai consumer logic khác nhau | Cùng event vào hai consumer name | Mỗi consumer áp dụng một lần độc lập |
| Hai thread cùng event ID | Gọi đồng thời từ hai thread | Unique constraint cho phép chỉ một transaction áp dụng tác động |
| Business update thất bại | Ném lỗi sau khi insert inbox | Transaction rollback cả inbox và business update |
| Crash sau DB commit trước ack | Mô phỏng redelivery sau commit | Lần giao lại nhận diện duplicate, không lặp tác động |
| Cùng ID nhưng payload khác | Gửi cùng khóa với hash khác | Ghi nhận identity conflict và cách ly |
| Event cũ sau cleanup | Replay event ngoài retention của inbox | Kiểm tra chính sách có ngăn tác động lặp theo yêu cầu không |
| Outbox relay publish lặp | Publish cùng outbox event hai lần | Consumer inbox ngăn áp dụng lặp |
| API ngoài timeout sau khi thành công | Retry cùng idempotency key | API đích trả kết quả tương ứng, không tạo tác động mới |

Test concurrency nên chạy trên database tương thích với môi trường production vì unique constraint, isolation level và cú pháp insert-ignore có semantics riêng. Mock repository không kiểm tra được race condition ở database.

## 18. Quan sát và vận hành

Nên theo dõi:

- Số message được áp dụng mới (`APPLIED`).
- Số message bị bỏ qua vì duplicate (`DUPLICATE`).
- Số trường hợp cùng event ID nhưng payload hash khác nhau.
- Số lỗi insert inbox hoặc transaction rollback.
- Số lần redelivery theo binder/broker.
- Tuổi và số lượng bản ghi inbox, tốc độ tăng dung lượng.
- Số outbox record đang chờ, publish thất bại hoặc publish lại.
- Tỷ lệ idempotency key conflict ở các API ngoài.

Log nên có `eventId`, `source`, `consumerName`, `correlationId` và kết quả `APPLIED`/`DUPLICATE`. Không dùng event ID làm nhãn metric có cardinality cao; hãy dùng counter tổng hợp theo binding, consumer logic và loại kết quả.

Khi tỷ lệ duplicate tăng đột ngột, kiểm tra consumer restart, rebalance, timeout, broker redelivery, producer retry và thời gian xử lý. Duplicate không nhất thiết là lỗi nếu cơ chế idempotency hoạt động, nhưng mức tăng bất thường có thể chỉ ra sự cố giao nhận hoặc cấu hình acknowledgement.

## 19. Quy trình thiết kế idempotency bằng event ID

Khi xây dựng một consumer Spring Cloud Stream:

1. Quy định event ID trong hợp đồng message và xác định nguồn tạo ID.
2. Tạo ID một lần khi sự kiện hình thành; giữ nguyên ID qua mọi lần retry publish.
3. Xác định namespace deduplication gồm consumer logic, nguồn và event ID.
4. Tạo inbox table với unique constraint ở database.
5. Chèn dấu inbox và áp dụng thay đổi nghiệp vụ trong cùng transaction.
6. Xác nhận message sau khi transaction commit theo cơ chế binder.
7. Dùng idempotency key ở API ngoài hoặc outbox/saga cho tác động không nằm trong database transaction.
8. Quy định cách xử lý cùng ID nhưng payload khác.
9. Giữ dấu deduplication đủ lâu so với retention và replay horizon.
10. Tách namespace khi rebuild projection có chủ đích; không đổi namespace mỗi lần restart.
11. Kiểm thử duplicate tuần tự, đồng thời, crash window và redelivery thật.
12. Theo dõi duplicate rate, inbox storage, outbox backlog và lỗi transaction.

## 20. Tự kiểm tra

- [ ] Giải thích được vì sao consumer có thể nhận cùng một message nhiều lần.
- [ ] Phân biệt event ID, business key và correlation ID.
- [ ] Bảo đảm producer giữ nguyên event ID qua các lần retry publish.
- [ ] Thiết kế inbox key theo consumer logic, source và event ID.
- [ ] Giải thích được vì sao insert inbox và business update cần cùng transaction.
- [ ] Hiểu vai trò của unique constraint khi hai thread xử lý cùng event.
- [ ] Nhận diện trường hợp cùng event ID nhưng payload khác nhau.
- [ ] Phân biệt inbox với outbox và biết cách kết hợp hai pattern.
- [ ] Xác định thời gian lưu deduplication theo replay horizon.
- [ ] Giải thích vì sao broker exactly-once không tự bao trùm database hoặc API ngoài.
- [ ] Thiết kế được kiểm thử duplicate, concurrency, crash và redelivery.

## Kết luận

Idempotency giúp consumer xử lý an toàn khi broker hoặc producer giao lại cùng một sự kiện. Producer phải tạo `eventId` một lần và giữ nguyên nó qua mọi lần publish; consumer lưu dấu ID bằng inbox có unique constraint và áp dụng dấu inbox cùng thay đổi nghiệp vụ trong một transaction. Với tác động bên ngoài database, cần idempotency key ở API đích hoặc một quy trình bền vững như outbox/saga. Phạm vi lưu dấu phải đủ dài cho retention và replay, còn mỗi consumer logic cần namespace riêng. Các cơ chế Kafka, RabbitMQ và Pulsar giảm rủi ro giao nhận nhưng không thay thế idempotency ở tầng nghiệp vụ.
