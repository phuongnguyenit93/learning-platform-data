# Đối soát dữ liệu và phục hồi sau lỗi một phần

Trong hệ thống Spring Cloud Stream, một nghiệp vụ thường đi qua nhiều thành phần: ứng dụng cập nhật database, producer gửi event tới Kafka/RabbitMQ/Pulsar, consumer cập nhật dữ liệu ở dịch vụ khác rồi có thể gọi thêm một API bên ngoài. Các thành phần này không cùng nằm trong một transaction nguyên tử. Vì vậy, một bước có thể thành công trong khi bước tiếp theo thất bại.

Ví dụ, database đã lưu đơn hàng nhưng ứng dụng dừng trước khi publish `OrderCreated`; hoặc consumer đã cập nhật projection nhưng tiến trình dừng trước khi xác nhận message với broker. Những tình huống này tạo ra trạng thái **thành công một phần**: dữ liệu giữa các thành phần không còn đồng bộ, message có thể bị thiếu hoặc được giao lại.

Đối soát dữ liệu giúp phát hiện chênh lệch giữa trạng thái kỳ vọng và trạng thái thực tế. Phục hồi giúp đưa hệ thống về trạng thái nhất quán bằng cách phát lại, xử lý bù, cập nhật trạng thái hoặc chuyển trường hợp bất thường cho người vận hành. Muốn làm được điều đó an toàn, mỗi sự kiện cần định danh ổn định, consumer cần idempotent và hệ thống phải lưu được dấu vết tiến trình.

## 1. Vì sao xảy ra lỗi một phần?

Một chuỗi xử lý phân tán có nhiều ranh giới lỗi: tiến trình có thể dừng, mạng có thể mất kết nối, broker có thể từ chối publish, database có thể timeout hoặc dịch vụ bên ngoài có thể trả kết quả nhưng phản hồi bị mất trên đường về.

| Tình huống | Trạng thái có thể còn lại | Rủi ro |
|---|---|---|
| Database commit thành công, publish event thất bại | Bản ghi nghiệp vụ đã tồn tại nhưng broker chưa có event | Dịch vụ downstream không biết thay đổi đã xảy ra. |
| Broker nhận event, producer dừng trước khi ghi nhận đã publish | Event đã có trên broker nhưng outbox vẫn ở trạng thái chưa gửi | Relay có thể gửi lại event, tạo bản sao. |
| Consumer cập nhật database, ACK/commit offset thất bại | Tác dụng nghiệp vụ đã commit nhưng broker có thể giao lại message | Consumer xử lý trùng. |
| Consumer ACK/commit offset trước khi database commit | Broker xem message đã hoàn tất nhưng thay đổi database bị rollback | Mất tác dụng nghiệp vụ dù message không còn được giao lại. |
| Gọi API thanh toán thành công nhưng ứng dụng timeout trước khi lưu kết quả | Nhà cung cấp đã thực hiện giao dịch, ứng dụng chưa biết kết quả | Gọi lại có thể tạo giao dịch trùng nếu thiếu idempotency. |
| Gửi event tới hai destination, chỉ một lần gửi thành công | Hai hệ thống downstream nhìn thấy trạng thái khác nhau | Luồng dữ liệu bị lệch giữa các hệ thống. |

Lỗi một phần không nhất thiết là lỗi của broker. Phần lớn phát sinh vì database, broker và dịch vụ ngoài có các ranh giới commit khác nhau. Tăng retry có thể giúp vượt lỗi tạm thời, nhưng không tự giải quyết được tính nguyên tử giữa các hệ thống.

## 2. Xác định nguồn dữ liệu chuẩn và trạng thái kỳ vọng

Trước khi đối soát, cần xác định hệ thống nào là nguồn dữ liệu chuẩn (source of truth) cho từng loại thông tin. Ví dụ, Order Service có thể là nguồn chuẩn về trạng thái đơn hàng; Payment Service hoặc nhà cung cấp thanh toán là nguồn chuẩn về kết quả giao dịch; projection của báo cáo chỉ là bản sao phục vụ truy vấn.

Không nên so sánh hai bản sao dữ liệu mà không biết bản nào có quyền quyết định. Nếu projection chậm hơn nguồn chuẩn vài giây, đó có thể là độ trễ bình thường chứ chưa phải mất dữ liệu.

Một bản ghi đối soát nên có đủ thông tin để xác định:

- **Định danh sự kiện:** `eventId` duy nhất, ổn định qua retry và replay.
- **Định danh nghiệp vụ:** `aggregateId` như `orderId`, `paymentId` hoặc `accountId`.
- **Phiên bản nghiệp vụ:** `aggregateVersion` hoặc sequence để nhận biết thứ tự thay đổi.
- **Loại sự kiện:** `eventType` và phiên bản schema.
- **Thời điểm:** `occurredAt`, `createdAt`, `publishedAt`, `processedAt` nếu có.
- **Tương quan:** `correlationId`, `causationId` để nối các bước trong một quy trình.
- **Trạng thái giao nhận:** pending, published, processed, failed hoặc trạng thái tương ứng của ứng dụng.

Ví dụ payload event:

```json
{
  "eventId": "evt-01J9M7Q3",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateId": "order-9001",
  "aggregateVersion": 1,
  "correlationId": "corr-checkout-77",
  "occurredAt": "2026-11-24T08:15:30Z",
  "data": {
    "customerId": "customer-42",
    "totalAmount": 125000
  }
}
```

`eventId` không đổi khi cùng một sự kiện được retry hoặc phát lại. Nếu tạo ID mới cho mỗi lần thử, consumer không thể nhận biết bản sao của cùng một sự kiện. `aggregateVersion` giúp phát hiện sự kiện bị thiếu hoặc đến sai thứ tự trong phạm vi một aggregate.

## 3. Ma trận lỗi một phần và cách phục hồi

Nên lập ma trận cho các ranh giới quan trọng trước khi triển khai:

| Ranh giới | Dấu hiệu cần tìm | Hướng phục hồi thường dùng |
|---|---|---|
| Database → broker | Có bản ghi nghiệp vụ nhưng thiếu event/outbox chưa publish | Transactional outbox và relay gửi lại. |
| Broker → consumer | Message tồn tại nhưng consumer chưa xử lý | Retry, redelivery, replay từ broker hoặc DLQ. |
| Consumer → database | Event đã nhận nhưng projection chưa cập nhật | Inbox/idempotency và phát lại event. |
| Consumer → API ngoài | Không rõ API đã thực hiện tác vụ hay chưa | Tra cứu trạng thái bằng idempotency key, sau đó retry hoặc bù trừ. |
| Producer → nhiều destination | Một destination nhận event, destination khác chưa nhận | Delivery ledger/outbox riêng cho từng đích và đối soát trạng thái từng đích. |
| Nhiều event cùng aggregate | Phiên bản sau có nhưng phiên bản trước thiếu | Phát hiện gap theo version, tải lại hoặc replay phần thiếu. |

Không có một cơ chế đơn lẻ xử lý tất cả trường hợp. Outbox giải quyết ranh giới database-producer; inbox giải quyết xử lý trùng ở consumer; DLQ giữ message không xử lý được; reconciliation phát hiện chênh lệch còn lại; saga/compensation xử lý các tác dụng nghiệp vụ không thể rollback bằng transaction cục bộ.

## 4. Transactional Outbox: không để mất event sau khi commit database

Một lỗi phổ biến xảy ra khi ứng dụng thực hiện hai thao tác độc lập:

```java
orderRepository.save(order);
streamBridge.send("orders-out-0", event);
```

Nếu database commit nhưng publish thất bại, order đã được lưu nhưng event bị thiếu. Nếu publish thành công rồi database rollback, downstream có thể nhận một event cho thay đổi không tồn tại. Hai thao tác này không tự động trở thành một transaction nguyên tử chỉ vì chúng nằm trong cùng một method Java.

Transactional Outbox giải quyết vấn đề bằng cách lưu thay đổi nghiệp vụ và bản ghi event vào **cùng một transaction database**:

1. Cập nhật order.
2. Thêm event vào bảng outbox.
3. Commit cả hai cùng lúc.
4. Một relay riêng đọc outbox và publish event tới broker.
5. Sau khi nhận được xác nhận gửi theo cơ chế binder/broker, relay đánh dấu bản ghi đã publish.

Ví dụ cấu trúc bảng ở mức khái niệm:

```sql
CREATE TABLE outbox_event (
    event_id            VARCHAR(80) PRIMARY KEY,
    aggregate_id        VARCHAR(100) NOT NULL,
    aggregate_version   BIGINT NOT NULL,
    event_type          VARCHAR(150) NOT NULL,
    payload             TEXT NOT NULL,
    status              VARCHAR(20) NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    published_at        TIMESTAMP NULL,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMP NULL,
    lease_until         TIMESTAMP NULL
);
```

Kiểu cột và cú pháp SQL cần điều chỉnh theo database. `event_id` là khóa duy nhất; có thể thêm unique constraint trên `(aggregate_id, aggregate_version, event_type)` nếu quy tắc nghiệp vụ bảo đảm một phiên bản chỉ phát một event loại đó.

Ví dụ service ghi order và outbox trong một transaction:

```java
@Transactional
public void createOrder(CreateOrder command) {
    Order order = Order.create(command);
    orderRepository.save(order);

    OrderCreated event = OrderCreated.from(order);
    outboxRepository.insert(OutboxEvent.pending(
        event.eventId(),
        order.id(),
        order.version(),
        "OrderCreated",
        serialize(event)
    ));
}
```

Nếu transaction rollback, cả order và outbox row đều không tồn tại. Nếu commit thành công, relay có thể tiếp tục gửi event kể cả khi tiến trình web đã dừng.

### 4.1. Relay cần chịu được việc publish lặp

Relay thường đọc các row pending theo lô, claim bằng lease hoặc cơ chế khóa phù hợp, publish rồi cập nhật trạng thái. Có một cửa sổ lỗi không thể loại bỏ chỉ bằng thứ tự thao tác:

- Broker đã nhận event.
- Relay dừng trước khi cập nhật `status = 'PUBLISHED'` trong database.
- Sau khi khởi động lại, relay thấy row vẫn pending và gửi lại event.

Vì vậy, outbox thường cung cấp **at-least-once publication**: event không bị mất trong tình huống được thiết kế đúng, nhưng có thể được gửi nhiều lần. Consumer phải idempotent theo `eventId`. Không đánh dấu published trước khi gửi vì nếu relay dừng giữa hai thao tác, event có thể bị mất vĩnh viễn.

`StreamBridge.send(...)` trả về `true` chỉ phản ánh thao tác gửi được chấp nhận ở mức API/channel theo implementation; không nên mặc định nó chứng minh dữ liệu đã được broker lưu bền vững. Relay cần dùng cơ chế xác nhận mà binder/client hỗ trợ và chỉ chuyển trạng thái khi có kết quả phù hợp. Chi tiết publisher confirm, transaction và timeout khác nhau giữa Kafka, RabbitMQ và Pulsar.

### 4.2. Giữ thứ tự event khi relay chạy song song

Nếu nhiều relay cùng đọc outbox, hai event của cùng `aggregateId` có thể được publish sai thứ tự. Có thể partition công việc theo aggregate, claim theo khóa, hoặc chỉ cho phép phát phiên bản kế tiếp khi phiên bản trước đã được xác nhận. Dùng `aggregateVersion` để consumer phát hiện gap và bỏ qua hoặc cách ly event đến sai thứ tự.

Không cần giữ thứ tự toàn cục cho mọi event nếu nghiệp vụ chỉ yêu cầu thứ tự theo một aggregate. Giới hạn phạm vi thứ tự giúp tăng throughput.

## 5. Inbox và idempotency: xử lý message giao lại mà không nhân đôi tác dụng

Broker có thể giao lại message khi consumer xử lý xong nhưng ACK/offset commit bị mất, khi consumer restart hoặc khi mạng bị gián đoạn. Đây là hành vi bình thường trong mô hình at-least-once. Consumer cần chịu được cùng `eventId` xuất hiện nhiều lần.

Inbox pattern lưu dấu message đã xử lý. Một bảng inbox có thể gồm:

```sql
CREATE TABLE inbox_message (
    consumer_name   VARCHAR(120) NOT NULL,
    event_id        VARCHAR(80) NOT NULL,
    processed_at    TIMESTAMP NOT NULL,
    result_ref      VARCHAR(150) NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Khóa chính `(consumer_name, event_id)` ngăn cùng một consumer áp dụng cùng event nhiều lần. Tên consumer phải ổn định qua các lần triển khai; nếu đổi tên tùy tiện, bản ghi inbox cũ không còn được dùng để chống trùng.

Thuật toán xử lý:

1. Bắt đầu transaction database.
2. Thử insert `(consumer_name, event_id)` vào inbox.
3. Nếu khóa đã tồn tại, coi đây là bản giao lại và không áp dụng lại tác dụng nghiệp vụ.
4. Nếu insert thành công, cập nhật projection hoặc trạng thái nghiệp vụ trong cùng transaction.
5. Commit transaction.
6. Để binder/broker xác nhận message theo cơ chế đã cấu hình sau khi xử lý hoàn tất.

Ví dụ pseudocode:

```java
@Transactional
public void handle(OrderCreated event) {
    boolean firstDelivery = inboxRepository.tryInsert(
        "order-projection",
        event.eventId()
    );

    if (!firstDelivery) {
        return; // Event đã được áp dụng trước đó.
    }

    projectionRepository.apply(event);
}
```

`tryInsert` cần dựa trên unique constraint và xử lý xung đột theo database đang dùng. Không triển khai theo kiểu “SELECT trước rồi INSERT” mà không có ràng buộc duy nhất, vì hai consumer đồng thời có thể cùng thấy chưa có row rồi cùng áp dụng event.

Inbox row và thay đổi nghiệp vụ phải nằm trong cùng transaction. Nếu ghi inbox trước rồi xử lý nghiệp vụ ở transaction khác, ứng dụng có thể đánh dấu event đã xử lý dù tác dụng chưa commit. Nếu cập nhật projection trước rồi ghi inbox sau, crash giữa hai bước có thể làm tác dụng bị áp dụng hai lần.

## 6. Đối soát giữa outbox, broker và inbox

Outbox cho biết producer đã ghi nhận event cần phát; inbox cho biết một consumer đã áp dụng event. Broker giữ message trong topic/queue theo retention, subscription, offset và ACK policy. Đối soát có thể so sánh các dấu vết này để tìm khoảng trống.

Một báo cáo đối soát có thể phân loại:

| Trạng thái producer | Trạng thái consumer | Diễn giải | Hành động |
|---|---|---|---|
| Outbox pending quá hạn | Chưa có inbox | Relay chưa phát hoặc publish liên tục thất bại | Kiểm tra relay, kết nối broker và retry có giới hạn. |
| Outbox published | Chưa có inbox sau thời gian chờ | Consumer chưa nhận, đang lag hoặc message bị cách ly | Kiểm tra lag, group/subscription, DLQ và retention. |
| Outbox published | Inbox có event ID | Consumer đã áp dụng | Đối chiếu trạng thái nghiệp vụ và kết thúc. |
| Outbox pending | Inbox đã có event ID | Có thể đã publish nhưng relay chưa cập nhật trạng thái | Xác minh broker; cập nhật trạng thái relay an toàn, không xóa dấu vết. |
| Nhiều lần giao cùng event | Chỉ một inbox row | Duplicate đã được loại bằng idempotency | Ghi metric duplicate, không áp dụng lại. |
| Có event version N+1 nhưng thiếu N | Gap theo aggregate | Event bị thiếu hoặc đến sai thứ tự | Tìm event N trong outbox, broker retention hoặc DLQ; replay có kiểm soát. |

Không nên đối soát chỉ bằng tổng số message. Hai hệ thống có thể có cùng số lượng nhưng chứa các event khác nhau; ngược lại, số lượng có thể tạm lệch do độ trễ xử lý bình thường. Nên đối chiếu theo `eventId`, aggregate/version, trạng thái và một khoảng thời gian chờ (grace period).

### 6.1. Quy trình đối soát định kỳ

Một job đối soát có thể chạy theo lịch hoặc theo sự kiện cảnh báo:

1. Chọn khoảng thời gian đã đủ lâu để tránh đánh dấu nhầm message đang trên đường xử lý.
2. Lấy danh sách event kỳ vọng từ outbox hoặc nguồn chuẩn.
3. So sánh với delivery ledger/inbox của consumer cần kiểm tra.
4. Phân loại event thiếu, event trùng, event quá hạn và event sai phiên bản.
5. Tra cứu broker offset/lag, queue depth, subscription backlog và DLQ để xác định vị trí lỗi.
6. Tạo recovery task có khóa duy nhất theo event và consumer.
7. Replay hoặc bù trừ sau khi xác minh nguyên nhân.
8. Lưu kết quả đối soát, người/hệ thống thực hiện và kết quả phục hồi.

Đối soát cần có giới hạn thời gian, phân trang và checkpoint riêng để không tải toàn bộ dữ liệu lịch sử vào bộ nhớ. Nếu dữ liệu lớn, có thể chia theo ngày, tenant, aggregate range hoặc partition.

## 7. Replay event có kiểm soát

Replay là phát lại một event đã tồn tại để consumer xử lý lại sau khi lỗi được sửa hoặc hệ thống đã khôi phục. Replay hữu ích khi consumer bị dừng, projection bị mất dữ liệu hoặc một message đã được chuyển vào DLQ.

Nguyên tắc khi replay:

- Giữ nguyên `eventId` gốc để inbox nhận ra bản sao.
- Giữ `aggregateId`, `aggregateVersion`, `occurredAt` và schema version gốc.
- Bổ sung metadata replay riêng như `replayId`, `replayedAt`, `replayReason`, `replayedBy`.
- Xác định consumer/group đích và khoảng event trước khi phát lại.
- Giới hạn tốc độ replay để không làm quá tải broker hoặc downstream.
- Tránh gửi replay trở lại cùng đường đang tạo lỗi mà không có biện pháp ngăn lặp.
- Lưu lại kết quả, số lần replay và người phê duyệt nếu nghiệp vụ yêu cầu.

Ví dụ metadata:

```json
{
  "eventId": "evt-01J9M7Q3",
  "replayId": "replay-20261124-001",
  "replayedAt": "2026-11-24T10:00:00Z",
  "replayReason": "projection-rebuild",
  "replayedBy": "reconciliation-job"
}
```

Không tạo `eventId` mới chỉ để replay. Nếu consumer đã xử lý event trước đó, inbox sẽ bỏ qua. Nếu mục tiêu là cố ý áp dụng lại dữ liệu vào một projection mới, hãy dùng consumer identity mới hoặc namespace inbox riêng cho lần rebuild, sau khi xác định rõ dữ liệu đích cần được tạo lại.

Replay toàn bộ topic có thể gây tác dụng phụ nếu consumer gửi email, trừ tiền hoặc gọi API bên ngoài. Nên tách consumer rebuild chỉ ghi projection khỏi consumer tạo tác dụng bên ngoài; hoặc áp dụng idempotency key ở dịch vụ đích.

## 8. Phục hồi từ DLQ và parking-lot destination

DLQ lưu message đã vượt quá chính sách retry hoặc bị broker/consumer đưa vào luồng lỗi. DLQ không tự sửa dữ liệu và không tự bảo đảm message sẽ được xử lý lại. Cần một quy trình vận hành:

1. Thu thập message, exception, event ID, binding, group/subscription và thời điểm lỗi.
2. Phân loại lỗi tạm thời, dữ liệu không hợp lệ, schema không tương thích, lỗi cấu hình hoặc lỗi nghiệp vụ.
3. Sửa nguyên nhân trước khi replay; nếu payload sai, cần quyết định sửa payload hay phát event điều chỉnh.
4. Chọn message hoặc khoảng message được phép replay.
5. Phát lại với tốc độ giới hạn và giữ nguyên event ID gốc.
6. Xác minh inbox/đích nghiệp vụ đã cập nhật và không phát sinh tác dụng trùng.
7. Lưu kết quả và đóng recovery task.

Parking-lot destination có thể được dùng cho message không thể tự phục hồi hoặc cần người xử lý. Không nên để DLQ trở thành nơi lưu vô thời hạn mà không có cảnh báo, retention và chủ sở hữu.

## 9. Phục hồi khi gọi dịch vụ bên ngoài

Một transaction database không thể rollback một thao tác đã thực hiện ở nhà cung cấp thanh toán, email hoặc hệ thống vận chuyển. Ví dụ, nhà cung cấp đã chấp thuận thanh toán nhưng ứng dụng mất kết nối trước khi ghi nhận kết quả.

Không nên lập tức gọi thanh toán lần nữa với một request mới. Thay vào đó:

1. Gửi request với idempotency key ổn định, ví dụ `paymentId` hoặc `commandId`.
2. Nếu timeout, tra cứu trạng thái giao dịch bằng idempotency key hoặc API truy vấn của nhà cung cấp.
3. Nếu nhà cung cấp xác nhận đã thành công, cập nhật trạng thái nội bộ tương ứng.
4. Nếu xác nhận chưa thực hiện, có thể retry cùng idempotency key.
5. Nếu trạng thái không xác định, giữ ở trạng thái cần đối soát thay vì tự suy đoán thành công/thất bại.
6. Nếu một bước sau không thể hoàn tất, thực hiện hành động bù trừ theo quy tắc nghiệp vụ, ví dụ hoàn tiền hoặc hủy giữ hàng.

Saga là cách tổ chức một quy trình nhiều bước bằng các transaction cục bộ và hành động bù trừ. Compensation không phải rollback vật lý: hoàn tiền là một giao dịch mới có ý nghĩa nghiệp vụ, không xóa sự kiện thanh toán đã xảy ra.

## 10. Trạng thái phục hồi và lease để tránh nhiều worker xử lý trùng

Nếu nhiều instance chạy job reconciliation hoặc replay, cần lưu trạng thái task để chúng không cùng phục hồi một event theo cách không kiểm soát.

Một recovery task có thể có các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `DETECTED` | Đã phát hiện chênh lệch. |
| `READY` | Đã xác minh và đủ điều kiện phục hồi. |
| `IN_PROGRESS` | Một worker đang giữ lease và xử lý. |
| `REPLAYED` | Event đã được gửi lại theo cơ chế phục hồi. |
| `VERIFIED` | Đã xác minh trạng thái đích đúng. |
| `RETRY_WAIT` | Phục hồi thất bại tạm thời và chờ lần thử tiếp theo. |
| `MANUAL_REVIEW` | Cần người có thẩm quyền xem xét. |
| `COMPENSATION_REQUIRED` | Cần thực hiện hành động bù trừ nghiệp vụ. |
| `CLOSED` | Đã hoàn tất và lưu dấu vết. |

Worker có thể claim task bằng lease có thời hạn. Nếu worker dừng đột ngột, lease hết hạn để worker khác tiếp quản. Cần dùng cập nhật có điều kiện/optimistic locking hoặc khóa database phù hợp để tránh hai worker cùng sở hữu một task. Lease không thay thế idempotency; worker cũ có thể vẫn chạy sau khi lease hết hạn, nên mọi tác dụng bên ngoài vẫn phải chịu được lặp.

## 11. Những lưu ý theo broker

### Kafka

Kafka lưu log theo partition và consumer group commit offset để ghi nhận vị trí đã đọc. Offset không phải bằng chứng nghiệp vụ đã commit trong database. Nếu consumer commit offset trước khi transaction database hoàn tất, crash có thể làm mất tác dụng nghiệp vụ. Nếu commit sau khi database commit nhưng crash trước khi offset được ghi, message có thể được giao lại; inbox/idempotency xử lý bản sao.

Kafka transaction có thể phối hợp đọc và ghi giữa các topic Kafka trong một transaction Kafka, tùy cấu hình và binder. Nó không tự bao gồm transaction của database hoặc API bên ngoài. Với database-to-Kafka, outbox vẫn là lựa chọn phổ biến để phối hợp trạng thái cục bộ và event.

Khi đối soát, xem consumer lag, committed offset, log end offset, partition assignment, rebalance và DLQ topic. Không dùng offset đơn lẻ để kết luận projection đã cập nhật đúng.

### RabbitMQ

RabbitMQ sử dụng ACK/NACK và queue. Message chưa ACK có thể được giao lại khi consumer/channel/connection đóng. Queue depth, unacked count, redelivery flag và DLX/DLQ là các dấu hiệu hữu ích khi điều tra. Cần xác định message có được ACK sau khi database commit hay không và tránh cấu hình requeue vô hạn cho lỗi không thể phục hồi.

Publisher confirm và consumer ACK là hai hướng xác nhận khác nhau. Confirm giúp producer biết broker đã nhận publish theo cơ chế xác nhận của RabbitMQ; consumer ACK cho broker biết message đã được xử lý. Không nhầm hai tín hiệu này thành một xác nhận end-to-end.

### Pulsar

Pulsar dùng subscription và acknowledgement. Message chưa ACK có thể được redeliver theo subscription type và chính sách client/broker. Theo dõi backlog, redelivery, unacked message và dead-letter topic. Với Key_Shared hoặc Shared, thứ tự và phân phối phụ thuộc subscription type; đối soát theo event ID/aggregate version thay vì giả định một thứ tự toàn cục.

Các binder có thuộc tính riêng về ACK, retry, DLQ và transaction. Hãy xác minh theo đúng phiên bản binder/client đang chạy; không chuyển nguyên cấu hình Kafka sang RabbitMQ hoặc Pulsar.

## 12. Vì sao không thể chỉ dựa vào exactly-once?

Các broker có thể cung cấp bảo đảm giao nhận hoặc transaction ở một phạm vi nhất định. Tuy nhiên, một luồng nghiệp vụ thường gồm nhiều tài nguyên độc lập: broker, database, cache và API bên ngoài. “Exactly once” trong một ranh giới không tự mở rộng thành đúng một lần cho toàn bộ chuỗi.

Ví dụ, Kafka transaction có thể bảo đảm các record Kafka được commit cùng nhau trong transaction Kafka, nhưng không tự rollback một lần ghi PostgreSQL. RabbitMQ publisher confirm không chứng minh consumer đã commit database. Pulsar acknowledgement không tự bảo đảm API ngoài chỉ được gọi một lần.

Thiết kế thực tế thường kết hợp:

- At-least-once delivery ở ranh giới broker.
- Outbox để không mất event sau transaction database.
- Inbox/idempotency để loại tác dụng trùng ở consumer.
- Version/sequence để phát hiện thiếu hoặc sai thứ tự event.
- Reconciliation để tìm chênh lệch còn lại.
- Compensation cho các bước nghiệp vụ không thể rollback.

## 13. Kiểm thử lỗi một phần và phục hồi

Kiểm thử happy path không đủ để chứng minh độ tin cậy. Cần chủ động tạo lỗi giữa các bước:

| Điểm tiêm lỗi | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Trước database commit | Dừng service sau khi chuẩn bị order/outbox | Cả hai cùng rollback; không có event mồ côi. |
| Sau database commit, trước relay publish | Dừng relay | Outbox còn pending và được gửi sau khi relay phục hồi. |
| Sau broker publish, trước mark published | Dừng relay | Có thể publish trùng; consumer inbox chỉ áp dụng một lần. |
| Sau DB commit ở consumer, trước ACK | Ngắt consumer | Broker có thể giao lại; inbox ngăn tác dụng lặp. |
| Trước DB commit ở consumer | Ném exception | Transaction rollback; message được retry/redeliver theo cấu hình. |
| API ngoài trả thành công nhưng response timeout | Mô phỏng mất phản hồi | Tra cứu bằng idempotency key; không tạo tác dụng ngoài trùng. |
| Một destination publish thành công, destination khác lỗi | Tạo lỗi riêng từng đích | Delivery ledger giữ trạng thái từng đích và chỉ retry đích chưa thành công. |
| Replay cùng event nhiều lần | Gửi lại event ID cũ | Inbox/idempotency giữ kết quả nghiệp vụ không đổi. |
| Worker reconciliation dừng khi đang giữ task | Dừng tiến trình | Lease hết hạn và worker khác tiếp quản an toàn. |

Có thể dùng Spring Cloud Stream Test Binder để kiểm thử function/binding và logic message trong JVM. Đối với ACK, offset, publisher confirm, redelivery, DLQ và transaction thực tế, cần integration test với Kafka/RabbitMQ/Pulsar tương ứng. Nên bổ sung kiểm thử khôi phục sau restart, mất mạng và broker tạm ngừng hoạt động.

## 14. Quan sát và cảnh báo đối soát

Một quy trình đối soát cần có metric để phát hiện chênh lệch trước khi người dùng báo lỗi:

- Số outbox row pending và tuổi của row pending lâu nhất.
- Số lần publish thất bại, retry count và thời gian từ tạo event tới publish.
- Consumer lag/backlog theo destination và group/subscription.
- Số event phát hiện thiếu, trùng, sai version hoặc quá hạn.
- Số inbox duplicate bị bỏ qua.
- Số message trong DLQ/parking lot và tuổi message cũ nhất.
- Số recovery task theo trạng thái, số lần replay và tỷ lệ phục hồi thành công.
- Số compensation đang chờ và thời gian chưa hoàn tất.

Metric tag nên có cardinality thấp như `destination`, `consumer`, `eventType` hoặc `result`. Dùng `eventId`, `aggregateId` và `correlationId` trong log có cấu trúc hoặc trace, không đưa hàng triệu ID riêng lẻ vào metric label.

Mỗi recovery task nên lưu lý do phát hiện, dữ liệu trước/sau, hành động đã thực hiện, thời gian và danh tính worker. Điều này giúp audit và tránh một job tự động sửa dữ liệu mà không thể giải thích sau đó.

## 15. Quy trình đối soát và phục hồi end-to-end

Một quy trình vận hành có thể tổ chức theo các bước:

1. **Xác định nguồn chuẩn:** chọn hệ thống có thẩm quyền cho trạng thái nghiệp vụ cần kiểm tra.
2. **Tạo dấu vết:** đảm bảo event có ID ổn định, aggregate version, correlation ID và trạng thái outbox/inbox.
3. **Phát hiện chênh lệch:** so sánh event kỳ vọng với delivery ledger/inbox sau một grace period.
4. **Khoanh vùng:** kiểm tra relay, broker, consumer lag, ACK/offset, DLQ và log theo event ID.
5. **Phân loại:** lỗi tạm thời, message sai dữ liệu/schema, mất event, duplicate, sai thứ tự hoặc tác dụng bên ngoài chưa rõ kết quả.
6. **Chọn hành động:** retry, replay, rebuild projection, sửa dữ liệu có kiểm soát hoặc compensation.
7. **Giới hạn tác động:** dùng idempotency, lease, rate limit và phạm vi replay cụ thể.
8. **Xác minh sau phục hồi:** kiểm tra trạng thái ở nguồn chuẩn và hệ thống đích, không chỉ kiểm tra message đã được publish.
9. **Đóng recovery task:** lưu kết quả, metric và audit trail.
10. **Ngăn tái diễn:** bổ sung test lỗi, cảnh báo hoặc thay đổi thiết kế ở ranh giới đã thất bại.

## 16. Checklist thiết kế độ tin cậy

Trước khi đưa một luồng Spring Cloud Stream vào production, hãy xác minh:

1. Database update và outbox event có cùng transaction không?
2. Relay có thể gửi lại sau crash mà không làm mất event không?
3. Event ID có ổn định qua retry/replay không?
4. Consumer có inbox hoặc idempotency key bảo vệ tác dụng nghiệp vụ không?
5. Inbox row và thay đổi nghiệp vụ có cùng transaction không?
6. ACK/offset có được xác nhận sau khi tác dụng nghiệp vụ đã bền vững không?
7. Có aggregate version/sequence để phát hiện gap và sai thứ tự không?
8. Đối soát có xác định source of truth và grace period không?
9. DLQ có chủ sở hữu, retention, cảnh báo và quy trình redrive không?
10. Replay có giới hạn tốc độ, giữ event ID và tránh tác dụng phụ trùng không?
11. API bên ngoài có idempotency key hoặc cơ chế truy vấn trạng thái không?
12. Các bước không thể rollback có hành động compensation rõ ràng không?
13. Có kiểm thử crash ở từng ranh giới commit/publish/ACK không?
14. Có metric, log, trace và audit trail để phát hiện và giải thích chênh lệch không?

Đối soát không thay thế thiết kế giao nhận đúng ngay từ đầu; nó là lớp phát hiện và phục hồi cho những sai lệch vẫn có thể xảy ra trong hệ thống phân tán. Kết hợp outbox, inbox, idempotency, versioning, replay có kiểm soát và compensation giúp ứng dụng Spring Cloud Stream duy trì tính nhất quán nghiệp vụ ngay cả khi chỉ một phần của chuỗi xử lý thành công.
