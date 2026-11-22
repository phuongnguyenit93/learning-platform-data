# Duplicate delivery

Trong **Spring Kafka Reliability Operations**, **Duplicate delivery** là tình huống một Kafka record được consumer nhận và xử lý nhiều hơn một lần. Đây là hành vi có thể xảy ra bình thường trong hệ thống phân tán, đặc biệt khi consumer dùng **at-least-once delivery**, khi process crash giữa business processing và offset commit, khi consumer group rebalance, khi retry hoặc khi operator replay records.

Một record được giao lại không nhất thiết có nghĩa Kafka đã lưu hai bản sao. Thường đó là **cùng một record được đọc lại vì broker chưa thấy offset đã xử lý được commit**, hoặc vì application chủ động retry/recover. Nếu business handler thực hiện side effect không idempotent, việc đọc lại có thể tạo hai lần trừ tiền, hai đơn hàng, hai lần cập nhật tồn kho hoặc hai lần gửi thông báo.

Mục tiêu vận hành không phải giả định duplicate sẽ không bao giờ xảy ra. Mục tiêu là thiết kế consumer **chịu được việc một event được giao lại**, bảo vệ side effects bằng idempotency, hiểu rõ offset/ack/transaction boundary và có thể chứng minh kết quả sau recovery.

> **Kafka delivery và business side effect là hai việc khác nhau.** Hãy giả định một record có thể được giao lại; chỉ coi một business operation là hoàn tất khi side effect và dấu nhận diện xử lý đã được lưu bền vững theo cùng một ranh giới nhất quán.

## 1. Duplicate delivery là gì?

Giả sử topic orders.events có record:

~~~text
topic       = orders.events
partition   = 2
offset      = 1042
event_id    = evt-7f91
event_type  = OrderPaid
~~~

Consumer nhận record, cập nhật database, sau đó process bị kill trước khi Kafka offset 1043 được commit. Khi consumer khởi động lại hoặc partition được giao cho member khác, Kafka vẫn thấy committed offset trước đó và có thể giao lại record offset 1042.

~~~text
Lần 1:
  poll offset 1042
  database update thành công
  process crash trước offset commit

Lần 2:
  consumer khởi động / partition reassigned
  poll lại offset 1042
  database update chạy lần nữa
~~~

Kafka có thể chỉ có **một record vật lý** tại partition/offset đó. Duplicate xuất hiện ở **delivery/processing layer** vì cùng record được giao lại.

Cần phân biệt:

- **Duplicate production**: producer gửi cùng một business event thành nhiều Kafka records.
- **Duplicate delivery**: cùng một Kafka record được consumer nhận lại.
- **Duplicate processing**: handler thực hiện business logic nhiều lần cho cùng event.
- **Duplicate side effect**: hệ thống bên ngoài ghi nhận hành động nghiệp vụ nhiều lần.
- **Duplicate output**: consumer phát nhiều output records do redelivery hoặc retry.

Các hiện tượng liên quan nhưng cách xử lý khác nhau. Idempotent producer có thể giảm duplicate do producer retries; consumer idempotency bảo vệ side effects khi delivery lặp lại.

## 2. Vì sao Kafka có thể giao lại một record?

Kafka lưu **committed offset** theo consumer group. Offset đó biểu thị vị trí tiếp theo consumer group sẽ đọc, không phải một cờ xác nhận riêng cho từng business side effect.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant DB as Database
    participant K as Kafka
    C->>K: poll record offset 1042
    K-->>C: record 1042
    C->>DB: update business state
    DB-->>C: commit success
    Note over C: Process crashes here
    C->>K: Restart and poll from committed offset
    K-->>C: record 1042 again
    C->>DB: same business update again
~~~

Các nguyên nhân thường gặp:

1. Process crash sau khi business transaction commit nhưng trước khi offset commit.
2. Pod bị terminate trong lúc listener đang xử lý.
3. Consumer group rebalance khiến partition chuyển sang member khác.
4. Network failure làm client không biết commit request đã thành công hay chưa.
5. Listener ném exception và error handler retry record.
6. Database transaction rollback hoặc commit outcome không rõ.
7. Kafka transaction abort khiến input offsets chưa được commit.
8. Operator reset offset hoặc replay từ offset cũ.
9. Retry topic/DLT recovery tạo một delivery path khác.
10. Producer gửi cùng business event nhiều lần với các Kafka offsets khác nhau.

Một ứng dụng đúng phải chấp nhận một số trường hợp này thay vì dựa vào timing thuận lợi.

## 3. Delivery guarantee không giống business exactly-once

| Guarantee | Điều được bảo vệ | Điều không tự được bảo vệ |
|---|---|---|
| At-most-once | Record không được xử lý lặp theo cách commit trước processing | Có thể mất record nếu crash sau commit trước side effect |
| At-least-once | Record được retry/redeliver theo policy | Handler/side effect có thể chạy nhiều lần |
| Kafka producer idempotence | Giảm duplicate records do producer retry trong protocol/session | Consumer side effect hoặc duplicate business event từ nhiều sends |
| Kafka transactions/EOS | Atomicity của Kafka output records và consumed offsets trong transaction scope | Database/HTTP/email side effects bên ngoài Kafka |
| Business idempotency | Cùng business event được áp dụng tối đa một lần theo key/policy | Không tự bảo đảm broker delivery hoặc mọi external systems |

**At-least-once** là lựa chọn phổ biến cho xử lý nghiệp vụ vì ưu tiên không mất dữ liệu. Đổi lại, consumer phải chịu được redelivery.

At-most-once có thể tránh lặp bằng cách commit offset trước khi xử lý, nhưng crash sau commit sẽ làm record bị bỏ qua. Không chọn at-most-once chỉ để dashboard không hiện duplicate nếu nghiệp vụ không chấp nhận mất records.

## 4. Offset là vị trí tiếp theo cần đọc

Kafka offsets là số thứ tự theo partition. Khi consumer đã xử lý offset 1042 và muốn tiếp tục từ 1043, committed offset thường là **1043**.

~~~text
Last processed record: 1042
Committed position:    1043
Next record to read:   1043
~~~

Committed offset thường biểu thị vị trí tiếp theo, không phải record ở chính offset đó đã xử lý. Offsets có phạm vi **partition**, không phải global order của toàn topic. Consumer có thể commit tiến độ partition 0 trong khi partition 1 vẫn đang xử lý record cũ.

Khi batch chứa nhiều records, không được commit offset vượt qua record chưa xử lý thành công trong cùng partition.

## 5. Cửa sổ crash tạo duplicate

Có hai ranh giới thường không thể commit nguyên tử nếu dùng database và Kafka thông thường:

~~~text
A. Business side effect trước, Kafka offset sau:
   DB commit -> crash -> offset chưa commit -> redelivery
   => duplicate side effect nếu không idempotent

B. Kafka offset trước, business side effect sau:
   offset commit -> crash -> DB chưa commit -> record không được giao lại
   => mất business operation
~~~

At-least-once thường chọn A vì duplicate có thể được xử lý bằng idempotency; mất dữ liệu thường khó khôi phục hơn.

Đừng đảo thứ tự sang B chỉ để tránh duplicate. Hãy tạo business idempotency và transaction boundary phù hợp.

## 6. Spring Kafka AckMode ảnh hưởng thời điểm commit

Spring Kafka container quản lý acknowledgment và offset commits theo **AckMode**. Khi Kafka auto commit được tắt và container quản lý commits, các chế độ phổ biến gồm:

| AckMode | Hành vi tổng quát |
|---|---|
| RECORD | Commit sau khi listener xử lý thành công từng record |
| BATCH | Commit sau khi tất cả records từ poll batch được xử lý thành công |
| TIME | Commit khi khoảng thời gian cấu hình đã trôi qua sau các records đã xử lý |
| COUNT | Commit khi đủ số records đã xử lý |
| COUNT_TIME | Kết hợp ngưỡng count và time |
| MANUAL | Listener gọi acknowledge; container commit theo batch semantics phù hợp |
| MANUAL_IMMEDIATE | Commit ngay khi acknowledge được gọi trên consumer thread; cách gọi từ thread khác có thể làm thay đổi thời điểm thực tế |

Default container AckMode thường là BATCH khi container quản lý commits và auto commit được tắt; hãy xác minh phiên bản và cấu hình ứng dụng.

AckMode không biến business side effect và Kafka offset thành một transaction chung với database. Nếu DB commit xong rồi process crash trước Kafka commit, duplicate vẫn có thể xảy ra.

## 7. RECORD và BATCH tạo cửa sổ khác nhau

Với RECORD:

~~~text
poll [100, 101, 102]
listener(100) -> success -> commit position 101
listener(101) -> success -> commit position 102
listener(102) -> crash
restart -> đọc lại từ committed position
~~~

Với BATCH:

~~~text
poll [100, 101, 102]
listener(100) -> success
listener(101) -> success
listener(102) -> success
batch completes -> commit position 103
~~~

Nếu process crash trước batch commit, một số hoặc toàn bộ records trong batch có thể được giao lại dù business side effects của chúng đã hoàn tất.

BATCH có thể tăng phạm vi redelivery khi batch chưa được commit, đổi lại giảm commit overhead. Lựa chọn AckMode là trade-off giữa throughput, commit cost và kích thước cửa sổ duplicate.

## 8. MANUAL acknowledgment không có nghĩa exactly-once

Ví dụ:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.apply(record.value());

    acknowledgment.acknowledge();
}
~~~

Thứ tự này thể hiện at-least-once: side effect thành công trước, sau đó mới acknowledge. Nếu process chết giữa hai bước, record có thể được giao lại.

Không acknowledge trước khi side effect bền vững hoàn tất nếu không muốn chấp nhận mất nghiệp vụ:

~~~java
// Nguy hiểm nếu side effect có thể thất bại sau acknowledge.
acknowledgment.acknowledge();
orderService.apply(record.value());
~~~

Với MANUAL/MANUAL_IMMEDIATE, cần hiểu consumer thread, AckMode, async acknowledgments và version-specific semantics. Không gọi acknowledge tùy tiện từ worker thread nếu chưa cấu hình và hiểu rõ cơ chế hỗ trợ.

## 9. Consumer group rebalance có thể tạo redelivery

Khi consumer rời group, partition có thể được giao cho consumer khác. Nếu record đã được xử lý nhưng offset chưa commit, member mới có thể đọc lại.

Một số nguyên nhân rebalance:

- Deployment/rolling restart.
- Pod bị kill hoặc node failure.
- Consumer heartbeat/session timeout.
- Vượt max.poll.interval.ms.
- Scaling consumer instances.
- Network interruption.
- Subscription hoặc assignment strategy thay đổi.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant K as Group Coordinator
    participant B as Consumer B
    A->>K: owns partition 2
    A->>K: processes offset 1042
    Note over A: DB committed, Kafka offset not committed
    A--xK: leaves group / heartbeat timeout
    K->>B: assigns partition 2
    B->>K: joins and fetches from committed offset
    K-->>B: offset 1042 redelivered
~~~

Graceful shutdown và xử lý listener nhanh giúp giảm cửa sổ này, nhưng không loại bỏ crash/network ambiguity. Idempotency vẫn cần thiết.

## 10. Retry và error handler cũng tạo nhiều lần xử lý

Spring Kafka có thể retry record sau listener exception:

~~~text
Delivery 1 -> listener throws
Retry 1    -> listener throws
Retry 2    -> listener succeeds
~~~

Nếu listener thực hiện side effect rồi mới throw, retry có thể lặp side effect. Ví dụ DB update thành công nhưng sau đó HTTP call timeout; handler throw khiến toàn record được giao lại.

Hãy xác định **điểm side effect** và thứ tự thao tác. Đừng giả định listener ném exception nghĩa là không có thay đổi nào đã xảy ra.

Nếu retry chuyển record sang retry topic hoặc DLT, mỗi stage vẫn có thể gặp duplicate do publish/offset commit failure. Consumer ở retry/DLT stage cũng phải có idempotency phù hợp.

## 11. Producer idempotence và consumer idempotency

Hai cơ chế bảo vệ hai ranh giới khác nhau:

| Cơ chế | Bảo vệ |
|---|---|
| enable.idempotence | Producer retries không tạo duplicate append theo semantics Kafka producer |
| Transactional producer | Atomic Kafka writes và offsets trong transaction |
| Consumer inbox/deduplication | Một business event không áp dụng side effect lặp |
| Database unique constraint | Chặn hai transactions cùng ghi một event ID |
| External API idempotency key | Downstream API nhận cùng operation key nhiều lần nhưng áp dụng một lần |

Producer idempotence không loại bỏ duplicate do producer application gửi cùng event hai lần, producer restart và application retry, hai service instances cùng phát event, consumer redelivery hoặc operator replay.

Consumer idempotency vẫn là trách nhiệm riêng.

## 12. Kafka transactions và giới hạn exactly-once

Spring Kafka có thể cấu hình transactional listener container. Trong Kafka-to-Kafka processing, transaction có thể gộp output records và input offsets vào cùng transaction. Consumer downstream dùng isolation.level=read_committed sẽ không nhìn thấy output records từ transaction bị abort.

Điều này giúp đạt **exactly-once semantics trong phạm vi Kafka transaction** khi cấu hình đúng.

Nhưng transaction không tự bao gồm:
- JDBC database update.
- HTTP API call.
- Email/SMS.
- File/object storage.
- Payment gateway.
- Side effect ở hệ thống ngoài Kafka.

Listener có thể được gọi lại sau transaction abort. Nếu listener đã gọi external API trước khi transaction abort, API đó không tự rollback.

**Kafka EOS không đồng nghĩa toàn bộ business workflow exactly-once.** Cần idempotency/outbox/inbox ở các hệ thống bên ngoài transaction boundary.

## 13. Database inbox pattern

Một cách phổ biến là lưu event ID đã xử lý trong database cùng transaction với business update.

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khi nhận record:

1. Bắt đầu DB transaction.
2. Insert event ID vào processed_events.
3. Nếu unique conflict, event đã được áp dụng; kết thúc mà không lặp side effect.
4. Nếu insert mới, thực hiện business update.
5. Commit cả marker và business update trong cùng transaction.
6. Chỉ sau khi listener thành công, container mới commit Kafka offset theo AckMode.

Nếu DB transaction rollback, marker cũng rollback. Khi record được giao lại, consumer có thể thử lại.

## 14. SQL insert-if-absent phải atomic

Không làm kiểu check-then-act:

~~~java
if (!repository.existsByEventId(eventId)) {
    repository.saveProcessedEvent(eventId);
    orderRepository.apply(event);
}
~~~

Hai consumer threads có thể đồng thời kiểm tra exists=false rồi cùng insert/apply. Đây là race condition.

Dùng unique constraint làm trọng tài ở database:

~~~sql
INSERT INTO processed_events (
    consumer_name,
    event_id,
    processed_at
)
VALUES (
    :consumerName,
    :eventId,
    CURRENT_TIMESTAMP
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Cú pháp trên là PostgreSQL. MySQL, SQL Server và các database khác có cú pháp tương ứng khác nhau. Phải kiểm tra số rows affected để biết event ID vừa được claim hay đã tồn tại.

Nếu insert và domain update cùng một DB transaction, unique constraint giúp hai concurrent deliveries không cùng áp dụng business update.

## 15. Ví dụ service idempotent

Một interface repository có thể cung cấp insert-if-absent:

~~~java
public interface ProcessedEventRepository {

    boolean insertIfAbsent(
            String consumerName,
            String eventId
    );
}
~~~

Service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdempotentOrderHandler {

    private final ProcessedEventRepository processedEvents;
    private final OrderRepository orders;

    public IdempotentOrderHandler(
            ProcessedEventRepository processedEvents,
            OrderRepository orders) {
        this.processedEvents = processedEvents;
        this.orders = orders;
    }

    @Transactional
    public ProcessingResult handle(OrderEvent event) {

        boolean firstDelivery = processedEvents.insertIfAbsent(
            "orders-projection",
            event.eventId()
        );

        if (!firstDelivery) {
            return ProcessingResult.duplicate();
        }

        orders.apply(event);

        return ProcessingResult.applied();
    }
}
~~~

ProcessingResult, repositories và OrderEvent là domain types minh họa. Điều quan trọng là **marker và orders.apply nằm trong cùng transaction manager/database transaction**.

Nếu orders.apply ném exception, transaction rollback phải undo cả marker. Nếu marker commit riêng trước domain update, crash có thể khiến lần giao lại bị coi là duplicate dù business update chưa bao giờ xảy ra.

## 16. Idempotency key phải ổn định

Một deduplication key nên đại diện cho **một business operation**, không chỉ một lần Kafka delivery.

Ví dụ:
- event_id do producer tạo một lần và giữ nguyên qua retries.
- payment_operation_id cho một yêu cầu thanh toán.
- order_event_id cho một domain event.
- source_system + source_event_id nếu nhiều nguồn có thể trùng namespace.

Không tạo UUID mới mỗi lần consumer retry; như vậy duplicate không thể nhận ra.

Kafka topic/partition/offset có thể định danh một record vật lý, nhưng khi producer phát cùng business event thành hai records khác offsets, offset khác nhau không giúp phát hiện duplicate nghiệp vụ. Ngược lại, khi replay event sang topic khác, event ID ổn định có thể giữ deduplication xuyên replay nếu đó là chính sách mong muốn.

Chọn scope của key: cùng event có thể cần được xử lý một lần cho mỗi consumer application, nên unique key thường gồm consumer_name và event_id.

## 17. Kiểm tra event ID và payload consistency

Nếu cùng event_id xuất hiện với payload khác nhau, không nên âm thầm coi đó là duplicate hợp lệ.

Một policy tốt:
- Cùng event_id và cùng logical content: duplicate delivery, bỏ qua side effect.
- Cùng event_id nhưng payload khác: event identity conflict, quarantine/alert.
- Event ID thiếu hoặc malformed: validation failure theo policy.
- Event ID tái sử dụng sau thời gian dài: quyết định theo retention/business contract.

Có thể lưu schema version hoặc payload fingerprint từ canonical representation để phát hiện identity collision. Fingerprint không cần chứa raw payload trong logs/traces; bảo vệ nó theo policy vì có thể cho phép correlation.

Không dùng hash không ổn định của JSON serialization nếu field order, whitespace hoặc schema evolution làm cùng nội dung có fingerprint khác nhau.

## 18. Deduplication retention phải bao phủ replay horizon

Nếu processed_events xóa marker sau 7 ngày nhưng Kafka topic có thể replay 30 ngày, một record cũ được replay có thể áp dụng side effect lần nữa.

Retention cần xem:
- Kafka retention của input topic.
- Thời gian tối đa consumer outage.
- Retry topic retention.
- DLT retention và thời gian operator xử lý.
- Backup/restore/replay horizon.
- Cross-region disaster recovery.
- Manual backfill và historical reprocessing.
- Business/legal retention policy.

Một số hệ thống giữ marker vĩnh viễn hoặc giữ theo business entity lifetime. Một số dùng partitioned/TTL tables với retention được chứng minh đủ dài. Không chọn TTL chỉ vì bảng dedupe đang lớn.

Nếu xóa marker, hệ thống chủ động cho phép event có thể được áp dụng lại sau thời điểm đó.

## 19. Ordering và duplicate

Idempotency không tự bảo đảm ordering. Kafka chỉ đảm bảo thứ tự trong một partition theo append order. Nếu event cùng key đi qua nhiều partitions, hoặc retry topics làm thay đổi timing, thứ tự nghiệp vụ có thể thay đổi.

Ví dụ:
~~~text
OrderCreated version 1
OrderPaid    version 2
OrderClosed  version 3
~~~

Nếu version 2 được xử lý hai lần, consumer cần nhận biết duplicate. Nếu version 3 đến trước version 2 do retry/replay, consumer cần xử lý out-of-order theo domain policy.

Các biện pháp:
- Partition theo aggregate key ổn định.
- Dùng aggregate version/sequence number.
- Conditional update chỉ áp dụng version mới hơn.
- Reject/quarantine version gap khi cần.
- Không retry lâu một event rồi giả định mọi event sau nó sẽ chờ đúng thứ tự nếu retry strategy không bảo đảm điều đó.

## 20. Conditional update và optimistic versioning

Một cách idempotent khác là áp dụng state transition theo version:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version = :incomingVersion - 1;
~~~

Nếu update không ảnh hưởng row nào, có thể:
- Event đã được áp dụng (current version >= incoming version).
- Event bị đến sai thứ tự (version thấp hơn expected).
- Order không tồn tại.
- Version gap cần retry hoặc quarantine.

Phải phân biệt các trường hợp thay vì coi mọi rows-updated=0 là duplicate. Có thể đọc state hiện tại và phân loại theo domain rule.

Một unique event ID và optimistic versioning bổ sung cho nhau: event ID chống delivery lặp; version bảo vệ transition ordering.

## 21. External API side effects

Database inbox chỉ bảo vệ những side effects nằm trong cùng DB transaction. Nếu listener gọi payment/shipping/email API, DB transaction không thể rollback thao tác đã được hệ thống kia chấp nhận.

Ví dụ nguy hiểm:

~~~java
@Transactional
public void handle(PaymentRequested event) {
    paymentClient.charge(event.amount(), event.cardReference());
    processedEvents.insert(event.eventId());
}
~~~

Nếu payment API charge thành công nhưng response timeout trước khi client biết kết quả, transaction DB có thể rollback và Kafka giao lại record. Lần gọi sau có thể charge lần nữa.

Giải pháp ưu tiên:
- Dùng idempotency key ổn định được API downstream hỗ trợ.
- Truyền cùng key cho mọi retry của cùng operation.
- Downstream lưu kết quả theo key và trả lại kết quả cũ khi request lặp.
- Phân biệt timeout không rõ outcome với lỗi chắc chắn chưa thực hiện.
- Có reconciliation để kiểm tra operation đã được thực hiện hay chưa.

Không tạo idempotency key mới mỗi lần retry.

## 22. Outbox pattern cho side effects liên dịch vụ

Nếu consumer cần cập nhật database và phát lệnh sang hệ thống khác, **transactional outbox** giúp lưu ý định gửi cùng transaction DB:

~~~text
Kafka input
   |
   v
DB transaction:
  insert inbox event_id
  update domain state
  insert outbox command
   |
   v
commit DB transaction
   |
   v
outbox publisher sends command
   |
   v
downstream idempotency key
~~~

Ví dụ bảng outbox:

~~~sql
CREATE TABLE outbox (
    id VARCHAR(160) PRIMARY KEY,
    aggregate_id VARCHAR(160) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Payload trong outbox là dữ liệu nghiệp vụ, phải được bảo vệ như database business data; không copy nó vào spans/logs. Publisher có thể gửi cùng outbox row nhiều lần nếu crash sau publish trước khi đánh dấu published. Downstream vẫn cần idempotency.

Inbox + domain update + outbox insert nên commit trong cùng DB transaction. Kafka offset được commit sau khi listener transaction thành công theo cấu hình container.

## 23. Kafka-to-Kafka processing với transactions

Nếu consumer đọc topic A, xử lý rồi ghi topic B, Spring Kafka transactional listener có thể giúp gộp output và input offsets vào Kafka transaction.

~~~text
begin Kafka transaction
  consume input record
  produce output record
  send consumed offset to transaction
commit transaction
~~~

Nếu transaction abort, output record không hiển thị cho read_committed consumers và input offset chưa được commit trong transaction; record có thể được giao lại.

Điều này ngăn output từ transaction thất bại xuất hiện như một kết quả đã commit. Nhưng handler vẫn có thể chạy lại. Business code trong transaction không nên tạo external side effects không được bảo vệ.

Nếu producer gửi email trước transaction commit, Kafka abort không thể thu hồi email đó.

## 24. Error handler và DLT có thể giao lặp

Một error handler có thể retry, recover hoặc publish failed record sang DLT. Cũng có crash window ở bước recovery:

~~~text
1. Publish record to DLT
2. DLT publish succeeds
3. Process crashes before input offset commit
4. Original record is delivered again
5. DLT publish may happen again
~~~

Vì vậy DLT consumer cũng nên idempotent, và DLT recovery cần một identity ổn định cho original event. Đừng giả định đã vào DLT thì không thể duplicate.

Spring Kafka error handling có thể dùng DefaultErrorHandler, DeadLetterPublishingRecoverer, AfterRollbackProcessor hoặc @RetryableTopic. Chi tiết seek, ack, transaction và recovery phụ thuộc cấu hình/version; phải hiểu chính xác record nào được retry và khi nào offset được commit.

## 25. Retry topics thay đổi timing, không xóa duplicate

Non-blocking retry dùng các retry topics tách thời gian retry khỏi main consumer. Điều này có thể cho phép records sau tiếp tục xử lý, nhưng:
- Retry record có thể được publish lại nếu offset chưa commit.
- Retry listener có thể bị crash sau side effect.
- DLT publication có thể bị lặp.
- Ordering có thể thay đổi giữa main và retry stages.
- Một business event có thể xuất hiện ở nhiều topics trong cùng workflow.

Giữ event ID ổn định qua main/retry/DLT. Đừng tạo ID mới ở mỗi stage. Dùng retry-stage metadata để quan sát, không dùng topic name làm idempotency key nếu cùng event có thể chuyển qua nhiều retry topics.

## 26. Consumer concurrency và race condition

Một consumer group có thể có nhiều partitions và nhiều listener threads. Cùng một business event có thể xuất hiện ở hai Kafka records khác nhau hoặc được replay trong khi lần xử lý trước vẫn đang chạy ở một hệ thống khác.

Một check-then-act không atomic dễ race:

~~~text
Thread A: event not processed?
Thread B: event not processed?
Thread A: yes -> apply
Thread B: yes -> apply
~~~

Unique constraint trên (consumer_name, event_id) hoặc atomic insert-if-absent giúp chỉ một transaction claim được event.

Nếu processing cần thứ tự theo aggregate, partition key ổn định và database concurrency control phải hỗ trợ cùng invariant. Không dựa vào một in-memory HashSet/ConcurrentHashMap để chống duplicate trong cluster nhiều replicas.

## 27. Idempotency không phải chỉ là cache trong memory

Một set trong memory mất dữ liệu khi process restart, không chia sẻ giữa pods và không phối hợp với DB transaction. Nó chỉ có thể là optimization, không phải source of truth cho correctness.

Các cơ chế bền vững:
- Database inbox table với unique key.
- Business table unique constraint.
- Conditional upsert/version check.
- Downstream API idempotency store.
- Durable outbox/inbox.
- Transactional Kafka offsets/output khi toàn bộ side effects nằm trong Kafka.

Một cache có thể giảm DB lookup nhưng không được là lớp duy nhất ngăn side effect lặp.

## 28. Idempotent upsert cho projection

Với consumer xây dựng read model, upsert theo entity version có thể tự nhiên idempotent:

~~~sql
INSERT INTO order_projection (
    order_id,
    status,
    version
)
VALUES (
    :orderId,
    :status,
    :version
)
ON CONFLICT (order_id)
DO UPDATE SET
    status = EXCLUDED.status,
    version = EXCLUDED.version
WHERE order_projection.version < EXCLUDED.version;
~~~

Đây là PostgreSQL example. Nếu cùng event version được giao lại, update không thay đổi state lần nữa. Event cũ đến sau event mới sẽ không ghi đè state mới hơn.

Nhưng không phải mọi operation đều là set-state. Các lệnh tăng counter, trừ balance hoặc gửi email cần idempotency key riêng; chạy lại câu UPDATE cộng số tiền vẫn tạo duplicate.

## 29. Idempotency cho các thao tác cộng dồn

Ví dụ counter:

~~~sql
UPDATE inventory
SET reserved_quantity = reserved_quantity + :quantity
WHERE sku = :sku;
~~~

Câu lệnh này không idempotent: cùng event chạy hai lần sẽ cộng hai lần.

Cách bảo vệ là claim event ID và update trong cùng transaction:

~~~sql
BEGIN;

INSERT INTO processed_events (
    consumer_name, event_id, processed_at
)
VALUES (
    'inventory-reservation', :eventId, CURRENT_TIMESTAMP
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Chỉ thực hiện update khi insert đã claim event thành công.
UPDATE inventory
SET reserved_quantity = reserved_quantity + :quantity
WHERE sku = :sku;

COMMIT;
~~~

Đây là pseudocode SQL; ứng dụng phải kiểm tra rows affected của INSERT trước khi chạy UPDATE. Nếu event ID đã tồn tại, không chạy phần update. Nếu update thất bại, rollback cả marker.

## 30. Xử lý duplicate cần phân biệt kết quả

Đừng coi duplicate như lỗi hạ tầng cần retry mãi. Một event đã được áp dụng thành công có thể được xử lý như **no-op thành công** để container tiếp tục commit offset.

~~~java
ProcessingResult result = handler.handle(event);

if (result.isDuplicate()) {
    log.info(
        "Duplicate event ignored: eventType={}, consumer={}",
        safeEventType(event),
        "orders-projection"
    );
}
~~~

Log không cần ghi full payload hoặc PII. Có thể tăng metric duplicate count theo consumer/topic/event type đã chuẩn hóa. Nếu duplicate key có payload conflict, đó là identity/data integrity incident, không phải duplicate bình thường.

Đảm bảo duplicate path return thành công chỉ khi đã xác minh marker đại diện cho một lần business transaction thực sự commit.

## 31. Observability cho duplicate delivery

Metrics gợi ý:

| Metric | Ý nghĩa |
|---|---|
| consumer.records.received | Records listener nhận |
| consumer.events.applied | Business events mới được áp dụng |
| consumer.events.duplicate | Delivery bị dedupe |
| consumer.events.identity_conflict | Cùng ID nhưng payload/version xung đột |
| consumer.offset.commit.failure | Commit failures |
| consumer.rebalance.count | Group changes |
| consumer.retry.count | Retry attempts |
| consumer.dlt.count | DLT recovery |
| consumer.processing.duration | Thời gian xử lý |
| consumer.lag | Backlog |
| inbox.unique_conflict.count | Dedupe constraint hits |
| outbox.publish.retry | Outbox dispatch retries |

Đây là tên metric minh họa; một số cần custom instrumentation. Không dùng event ID, customer ID hoặc raw key làm metric labels vì cardinality cao và có thể lộ dữ liệu.

Log structured có thể ghi topic, partition, offset, event type đã allowlist, consumer name, result=duplicate và trace ID opaque nếu policy cho phép. Không log payload.

## 32. Đếm duplicate đúng cách

Một consumer nhận cùng event ID nhiều lần không nhất thiết chứng minh Kafka delivery lỗi. Producer có thể đã publish cùng business event nhiều lần với offsets khác nhau.

Nên phân biệt:
- **Same topic/partition/offset delivered again**: redelivery của cùng Kafka record.
- **Same event_id, different offsets**: producer/application duplicate hoặc replay.
- **Same business key, different event_id**: có thể là hai event hợp lệ hoặc producer identity bug.
- **Same event_id, different payload**: event identity conflict.

Để phân tích, có thể log/metric event ID ở dạng opaque reference đã được phê duyệt, cùng topic/partition/offset. Cần chính sách privacy/cardinality riêng cho event ID.

## 33. Replay và backfill tương tác với deduplication

Operator có thể reset offsets để replay historical records hoặc chạy backfill. Nếu inbox table giữ event IDs lâu dài, replay có thể bị bỏ qua vì các event đã được xử lý trước đó.

Điều này có thể đúng nếu mục tiêu chỉ là khôi phục consumer position; nhưng sai nếu mục tiêu là **rebuild projection từ đầu**.

Xác định mode rõ:
- Normal processing: dedupe theo consumer name và event ID.
- Rebuild projection: dùng projection generation/rebuild namespace mới hoặc tạo target rỗng.
- Replay để sửa bug: cần policy quyết định event nào được phép áp dụng lại.
- Reconciliation: so sánh business state, không chỉ xóa inbox rows tùy tiện.

Không xóa toàn bộ dedupe table chỉ để backfill. Làm vậy có thể khiến external side effects lịch sử chạy lại.

## 34. Retention và partitioning của inbox table

Inbox table có thể lớn. Các chiến lược vận hành:
- Index unique trên consumer_name + event_id.
- Partition theo thời gian nếu database hỗ trợ và query/unique semantics cho phép.
- Archive markers cũ theo retention contract.
- Theo dõi insert latency và unique-conflict rate.
- Xóa theo batch nhỏ để không gây lock/IO spike.
- Duy trì retention dài hơn retry/DLT/replay/DR horizon.
- Không xóa marker khi event còn có thể được giao lại.

Nếu dùng partitioned table, một số database yêu cầu partition key xuất hiện trong unique constraint; thiết kế phải bảo toàn uniqueness toàn bộ phạm vi dedupe. Đừng partition làm mất guarantee unique event ID.

## 35. Async listener và duplicate

Nếu listener submit work vào executor rồi return, container có thể acknowledge record trước khi task hoàn tất tùy AckMode:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    executor.submit(() -> service.apply(event));
    // Listener return có thể dẫn tới offset commit trước task completion.
}
~~~

Nếu offset commit trước khi task hoàn tất, task thất bại có thể không được redeliver. Nếu task chạy rồi consumer crash trước commit, duplicate có thể chạy song song.

Khi dùng async:
- Dùng acknowledgment/lifecycle semantics được Spring Kafka version hỗ trợ.
- Chỉ ack sau durable completion.
- Giữ bounded in-flight tasks.
- Xử lý rebalance/shutdown và tasks đang chạy.
- Bảo vệ DB bằng unique key/transaction.
- Không commit vượt records pending trong partition.
- Kiểm thử crash và task timeout.

Async không tự tăng delivery guarantee.

## 36. Concurrency và partition ordering

Kafka chỉ đảm bảo order trong cùng partition. Nếu event cùng aggregate key không luôn vào cùng partition, hoặc retry topics làm thay đổi timing, duplicate guard không giải quyết được out-of-order updates.

Dùng key ổn định theo aggregate khi cần ordering. Kết hợp:
- Partition key theo aggregate.
- Version number tăng dần.
- Conditional database update.
- Inbox unique event ID.
- Retry policy hiểu rõ việc chuyển records sang retry topics có thể thay đổi thứ tự.

Nếu event version 4 được xử lý trước version 3, consumer cần phát hiện gap hoặc bỏ qua version cũ theo domain policy; không chỉ coi mọi duplicate key là thành công.

## 37. Manual offset reset và operator replay

Offset reset có thể tạo duplicate delivery có chủ đích. Trước khi replay:

1. Xác định group/topic/partitions và offset range.
2. Xác định business side effects đã được áp dụng chưa.
3. Xác minh idempotency store còn giữ event IDs.
4. Xác định replay là recovery, rebuild hay bug correction.
5. Dùng consumer identity/namespace phù hợp nếu cần xử lý lại.
6. Không reset offsets khi consumers còn active nếu quy trình yêu cầu group inactive.
7. Theo dõi lag, retry, DLT và side effects.
8. Lưu audit trail về ai, vì sao và phạm vi replay.

Reset offset không xóa record và không làm event mới. Nó chỉ thay đổi vị trí đọc; replay thường làm record cũ được giao lại.

## 38. Shutdown và deployment để giảm duplicate window

Graceful shutdown giúp listener hoàn tất công việc trong thời gian cho phép, dừng container đúng lifecycle và commit offsets theo policy. Nhưng shutdown timeout ngắn hơn processing duration có thể khiến pod bị kill giữa side effect và commit.

Cần:
- Đặt termination grace period đủ cho listener drain hợp lý.
- Stop container theo lifecycle.
- Tránh bắt đầu batch mới trong shutdown nếu có thể pause/drain.
- Theo dõi in-flight transactions.
- Không commit thủ công nếu processing chưa bền vững.
- Thiết kế idempotency dù graceful shutdown đã được cấu hình.

Graceful shutdown giảm tần suất duplicate; nó không loại bỏ crash, node loss hoặc network partition.

## 39. Integration test duplicate delivery

Một test có giá trị nên tái hiện cửa sổ side effect đã commit nhưng offset chưa commit:

1. Dùng EmbeddedKafka hoặc Testcontainers.
2. Tạo topic và group riêng.
3. Gửi event có event ID ổn định.
4. Consumer xử lý và commit DB transaction.
5. Dừng consumer trước khi Kafka offset commit hoàn tất hoặc dùng test harness kiểm soát acknowledgment.
6. Khởi động lại consumer/reassign partition.
7. Xác nhận record được giao lại.
8. Xác nhận inbox unique key nhận ra duplicate.
9. Xác nhận business side effect chỉ được áp dụng một lần.
10. Xác nhận offset cuối cùng tiến sau duplicate no-op.

Không chỉ mock repository trả duplicate. Cần kiểm tra DB transaction, unique constraint và Kafka redelivery trong integration scenario phù hợp.

## 40. Test DB rollback và concurrency

Các test cần có:

**DB rollback:** insert inbox marker thành công nhưng domain update throw exception; xác nhận marker rollback. Khi redelivery, event có thể được xử lý lại.

**Concurrent duplicate:** hai consumer/test threads cùng xử lý event ID; xác nhận chỉ một transaction claim và áp dụng side effect.

**Payload conflict:** cùng event ID nhưng payload khác; xác nhận error/quarantine, không silently ignore.

**Retention boundary:** event cũ được replay sau thời gian dự kiến; xác nhận dedupe policy có hành vi rõ.

**Ordering:** version cũ đến sau version mới; xác nhận state không bị rollback.

**External API timeout:** API đã áp dụng operation nhưng response bị mất; retry dùng cùng idempotency key và không lặp side effect.

## 41. Test Kafka transactions và retry/DLT

Với transactional listener:
- Gây exception trước transaction commit.
- Xác nhận transaction abort và output không visible cho read_committed consumer.
- Xác nhận input record có thể redeliver.
- Xác nhận business side effect ngoài Kafka được bảo vệ riêng.
- Kiểm tra AfterRollbackProcessor/recovery policy.

Với retry/DLT:
- Gây lỗi listener và retry.
- Gây crash sau DLT publish trước input offset commit nếu harness cho phép.
- Xác nhận DLT có thể nhận duplicate.
- Consumer DLT dùng inbox/idempotency.
- Xác nhận event ID ổn định qua retry metadata.

Test này giúp phân biệt Kafka EOS với business exactly-once.

## 42. Runbook khi duplicate side effect xảy ra

**Xác định**
1. Thu topic, partition, offset, group, event ID và trace correlation an toàn.
2. Phân biệt same offset redelivery với same event ID/different offset.
3. Xác định consumer stage: main, retry, DLT hay replay.
4. Xác định business side effect đã chạy bao nhiêu lần và transaction nào commit.

**Khoanh vùng**
5. Kiểm tra committed offsets và AckMode.
6. Kiểm tra rebalance, crash, timeout, retry và deploy timeline.
7. Kiểm tra inbox marker/unique constraint.
8. Kiểm tra producer retries và event ID generation.
9. Kiểm tra external API idempotency/reconciliation.

**Phục hồi**
10. Tạm dừng hoặc giới hạn consumer nếu duplicate tiếp tục gây thiệt hại.
11. Không reset offset hoặc xóa inbox markers tùy tiện.
12. Reconcile business state bằng hệ thống nguồn được cấp quyền.
13. Sửa idempotency/transaction boundary.
14. Replay có kiểm soát sau khi chứng minh duplicate safe.

**Xác minh**
15. Side effect chỉ áp dụng một lần theo event key.
16. Offset tiến và consumer lag giảm.
17. Retry/DLT backlog ổn định.
18. Không còn duplicate conflict.
19. Ghi incident root cause và preventive actions.

## 43. Anti-patterns thường gặp

- Dùng in-memory Set để dedupe: mất khi restart và không chia sẻ giữa replicas.
- Check-then-act không atomic: hai threads có thể cùng thấy event chưa xử lý.
- Commit offset trước side effect: crash có thể làm mất business operation.
- Ghi inbox marker ngoài transaction với business update: crash có thể đánh dấu event đã xử lý dù side effect chưa commit.
- Tạo event ID mới khi retry: duplicate không còn nhận diện được.
- Dùng Kafka offset làm business idempotency key: cùng event ở offsets khác nhau vẫn bị áp dụng hai lần.
- Cho rằng idempotent producer giải quyết consumer duplicate: hai lớp bảo vệ khác nhau.
- Cho rằng Kafka transaction bao gồm database/HTTP: transaction scope chỉ gồm resources được tham gia.
- Xóa inbox markers quá sớm: historical replay có thể lặp side effect.
- Dùng retry topics nhưng không giữ event identity: dedupe thất bại giữa stages.
- Coi duplicate delivery là bug của broker: at-least-once thường cho phép redelivery.
- Bỏ qua same event ID với payload khác: có thể che producer identity conflict hoặc data corruption.
- Async submit rồi return trước durable completion: offset có thể commit quá sớm.

## 44. Checklist production

**Delivery và offset**
- [ ] AckMode/auto-commit được hiểu và cấu hình rõ.
- [ ] Biết committed offset là vị trí tiếp theo cần đọc.
- [ ] Xác định crash window giữa side effect và offset commit.
- [ ] Rebalance/retry/timeout được coi là nguồn redelivery.
- [ ] Không commit vượt records chưa hoàn tất.

**Idempotency**
- [ ] Mỗi business event có ID ổn định.
- [ ] Inbox/unique constraint dùng atomic insert-if-absent.
- [ ] Inbox marker và DB side effect cùng transaction.
- [ ] Duplicate path là no-op thành công.
- [ ] Same ID/different payload được phát hiện.
- [ ] Retention bao phủ retry/DLT/replay/DR horizon.
- [ ] External APIs nhận idempotency key ổn định.

**Transactions và retry**
- [ ] Phân biệt Kafka EOS với external side effects.
- [ ] Transactional listener/AfterRollbackProcessor được test.
- [ ] Retry/DLT consumer cũng idempotent.
- [ ] Event identity được giữ qua retry stages.
- [ ] Ordering/version policy rõ ràng.

**Vận hành**
- [ ] Metrics duplicate, offset commit, rebalance và lag.
- [ ] Có runbook replay/reset offsets.
- [ ] Graceful shutdown đủ thời gian.
- [ ] Có reconciliation cho external side effects.
- [ ] Không dùng in-memory dedupe làm source of truth.

**Testing**
- [ ] Test redelivery sau DB commit trước offset commit.
- [ ] Test DB rollback.
- [ ] Test concurrent duplicate.
- [ ] Test payload conflict.
- [ ] Test external API timeout/idempotency.
- [ ] Test Kafka transaction abort và retry/DLT.

## 45. Kết luận

**Duplicate delivery** là một phần tự nhiên của hệ thống Kafka at-least-once. Consumer có thể xử lý thành công business side effect rồi crash trước offset commit; rebalance, retry, transaction abort, network ambiguity và operator replay đều có thể làm cùng record được giao lại.

Spring Kafka AckMode, acknowledgment, error handlers và transactions quyết định thời điểm retry/commit, nhưng không tự làm mọi business side effect exactly-once. **Kafka producer idempotence** bảo vệ producer retry; **Kafka transactions** bảo vệ atomicity trong Kafka; **database inbox/unique constraint, conditional upsert và external API idempotency key** bảo vệ business effects ngoài ranh giới đó.

Thiết kế bền vững cần event ID ổn định, atomic deduplication cùng transaction với business update, retention đủ dài, xử lý payload conflict và observability phân biệt redelivery với duplicate business events. Khi vận hành, hãy xác định offset, group, retry stage và side effect outcome trước khi replay. Một consumer đáng tin cậy không phải consumer chưa từng nhận duplicate; đó là consumer có thể nhận lại record mà vẫn giữ **business state đúng và không áp dụng side effect lặp ngoài ý muốn**.
