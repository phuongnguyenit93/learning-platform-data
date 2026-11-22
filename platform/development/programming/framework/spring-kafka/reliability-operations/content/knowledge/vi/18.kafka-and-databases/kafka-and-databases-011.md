# Idempotency key cho DB write

Trong hệ thống Spring Kafka, một Kafka record có thể được consumer xử lý lại sau khi database đã ghi thành công. Ví dụ: listener cập nhật số dư và commit database, nhưng process bị dừng trước khi commit Kafka offset. Sau khi restart hoặc rebalance, Kafka giao lại cùng record. Nếu listener thực hiện phép cộng/trừ tiền một lần nữa, dữ liệu nghiệp vụ sẽ bị sai.

**Idempotency key** là định danh ổn định cho **một thao tác nghiệp vụ**, giúp ứng dụng nhận ra thao tác đó đã được áp dụng và không ghi database lần thứ hai. Với Kafka consumer ghi database, cách thiết kế vững chắc thường là kết hợp:

1. Một `eventId` hoặc business operation ID ổn định qua retry/replay.
2. Một **unique constraint** trong database để chống race condition giữa các consumer.
3. Một bảng inbox/processed events hoặc business constraint có tính idempotent.
4. Một **database transaction chung** bao trùm marker đã xử lý và thay đổi nghiệp vụ.
5. Chỉ trả thành công cho Spring Kafka listener sau khi database transaction hoàn tất.

Idempotency không ngăn broker giao lại record. Nó đảm bảo nhiều lần thực hiện của cùng logical operation không tạo nhiều lần side effect ngoài ý muốn.

## 1. Vì sao Kafka có thể giao lại record?

Với Kafka consumer thông thường, database transaction và consumer offset commit là hai bước riêng:

~~~mermaid
sequenceDiagram
    participant K as Kafka
    participant L as Spring Kafka listener
    participant DB as Database
    K-->>L: Event OrderPaid, eventId=E1
    L->>DB: BEGIN, ghi đơn hàng, COMMIT
    DB-->>L: Thành công
    Note over L: Process crash trước khi commit Kafka offset
    K-->>L: Giao lại event E1
    L->>DB: Nếu không dedup, có thể ghi lần thứ hai
~~~

Các nguyên nhân phổ biến gồm:

- Process chết sau DB commit, trước offset commit.
- Consumer group rebalance khi offset xử lý chưa được commit.
- Network timeout khiến tiến độ commit không chắc chắn.
- Listener retry sau khi ném exception.
- Non-blocking retry topic chuyển record sang luồng khác.
- Dead Letter Topic (DLT) replay sau khi sửa lỗi.
- Producer upstream gửi lại cùng business operation.

Đây là hệ quả tự nhiên của **at-least-once delivery**. Không nên cố loại bỏ hoàn toàn khả năng redelivery; nên thiết kế database update có thể lặp lại an toàn.

## 2. Chọn đúng idempotency key

Một event có thể có nhiều ID với ý nghĩa khác nhau:

~~~json
{
  "eventId": "7c53afbb-9e6c-4e84-8df7-dbd3419d39be",
  "eventType": "OrderPaid",
  "orderId": "ord-913",
  "paymentId": "pay-550",
  "amount": 290000,
  "currency": "VND",
  "occurredAt": "2026-11-15T08:12:00Z"
}
~~~

Ở đây:

- `orderId` định danh aggregate: một đơn hàng có thể có nhiều event hợp lệ.
- `paymentId` định danh một payment, có thể phù hợp cho operation cụ thể.
- `eventId` định danh một event được producer phát hành; nên giữ nguyên khi retry và replay.
- Kafka `topic + partition + offset` định danh một record vật lý trên broker, không phải toàn bộ vòng đời business operation.

Bảng so sánh:

| Key | Khi nào phù hợp? | Hạn chế |
|---|---|---|
| `eventId` | Dedupe một event qua retry, DLT và republish | Producer phải tạo ID ổn định, duy nhất theo contract |
| `paymentId + operationType` | Chỉ áp dụng một thao tác thanh toán | Cần mô tả rõ mỗi loại operation |
| `orderId` | Một thao tác duy nhất cho một order | Chặn nhầm các event hợp lệ khác cùng order |
| `topic + partition + offset` | Nhận biết một Kafka record nguồn | Republish hoặc replay có offset mới |
| Kafka record key | Routing theo aggregate | Không nhất thiết unique cho operation |
| Random UUID tạo trong consumer | Không phù hợp | Mỗi lần retry tạo key mới |
| Hash toàn bộ payload | Phương án phụ để phát hiện dữ liệu mâu thuẫn | Hai event khác nhau có thể có payload giống nhau |

Ví dụ cùng order có ba event hoàn toàn hợp lệ:

~~~text
evt-101: OrderCreated  / orderId=ord-913
evt-102: OrderPaid     / orderId=ord-913
evt-103: OrderShipped  / orderId=ord-913
~~~

Nếu dedupe chỉ theo `orderId`, event thứ hai và thứ ba sẽ bị loại sai. Idempotency key cần đại diện cho **một operation**, không chỉ thực thể bị tác động.

## 3. Scope của key: một event có thể phục vụ nhiều handler

Một business event `OrderPaid` có thể được nhiều consumer group xử lý:

~~~text
orders.paid
  |
  +-- payment-projection   -> cập nhật database thanh toán
  +-- loyalty-projection   -> tính điểm thưởng
  +-- analytics-projection -> ghi dữ liệu thống kê
~~~

Nếu cả ba handler dùng cùng bảng processed events với primary key duy nhất là `eventId`, handler thứ hai và thứ ba có thể nhìn thấy marker của handler đầu và bỏ qua phần việc của mình.

Vì thế, schema thường dùng khóa ghép:

~~~text
(handler_id, event_id)
~~~

Nếu event ID chỉ unique theo tenant, có thể cần:

~~~text
(tenant_id, handler_id, event_id)
~~~

`handler_id` là ID ổn định của **loại công việc nghiệp vụ**, không phải ID pod hoặc consumer instance ngẫu nhiên. Nếu mỗi lần redeploy thay đổi `handler_id`, các marker cũ không còn giúp dedupe. Nếu cố tình đổi semantics của handler, cần chiến lược version/migration riêng.

## 4. Hai phương pháp làm database write idempotent

### Phương pháp A: Câu SQL có điều kiện nghiệp vụ

Một số mutation vốn gần như idempotent:

~~~sql
UPDATE orders
   SET status = 'PAID'
 WHERE order_id = :order_id
   AND status = 'PENDING_PAYMENT';
~~~

Nếu đơn hàng đã ở trạng thái `PAID`, update này không tiếp tục làm thay đổi giá trị. Nhưng **0 rows updated không đồng nghĩa chắc chắn đã xử lý event**: đơn hàng có thể chưa tồn tại, đã bị hủy hoặc có state không hợp lệ. Cần business validation.

Với phép cộng/trừ, retry thường nguy hiểm:

~~~sql
-- Nếu chạy hai lần sẽ cộng hai lần.
UPDATE wallets
   SET balance = balance + :amount
 WHERE wallet_id = :wallet_id;

-- Nếu thiếu unique business constraint có thể tạo hai khoản phí.
INSERT INTO payment_fees(payment_id, amount)
VALUES (:payment_id, :fee_amount);
~~~

### Phương pháp B: Inbox table/processed events

Dùng một bảng lưu dấu event đã được xử lý. Mỗi lần nhận record:

1. Bắt đầu database transaction.
2. Thử chèn idempotency key có unique constraint.
3. Nếu key đã tồn tại, bỏ qua mutation vì operation đã được commit trước đó.
4. Nếu key mới, cập nhật dữ liệu nghiệp vụ.
5. Commit **marker và mutation cùng một transaction**.

~~~mermaid
flowchart TD
    A["Nhận Kafka event"] --> B["BEGIN DB transaction"]
    B --> C{"INSERT key có unique constraint"}
    C -->|Đã tồn tại| D["Không lặp side effect"]
    C -->|Mới| E["Ghi dữ liệu nghiệp vụ"]
    E --> F{"Write thành công?"}
    F -->|Có| G["COMMIT marker + business state"]
    F -->|Không| H["ROLLBACK tất cả"]
    D --> I["Listener trả success"]
    G --> I
    H --> J["Listener ném exception để Kafka retry"]
~~~

Điểm quan trọng là **không commit marker trước business write**. Nếu marker đã tồn tại nhưng business write chưa hoàn tất, lần giao lại sẽ bị bỏ qua nhầm và record thực tế bị mất xử lý.

## 5. Schema PostgreSQL có unique constraint

Ví dụ một bảng dùng cho nhiều Kafka handlers:

~~~sql
CREATE TABLE processed_kafka_event (
    handler_id       VARCHAR(120) NOT NULL,
    event_id         UUID NOT NULL,
    source_topic     VARCHAR(255),
    source_partition INTEGER,
    source_offset    BIGINT,
    processed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (handler_id, event_id)
);
~~~

Composite primary key bảo vệ trước các consumer đồng thời. Thông tin source topic, partition và offset giúp điều tra, nhưng không phải key chính của **business deduplication**.

Truy vấn atomic insert:

~~~sql
INSERT INTO processed_kafka_event (
    handler_id,
    event_id,
    source_topic,
    source_partition,
    source_offset
)
VALUES (
    :handler_id,
    :event_id,
    :topic,
    :partition,
    :offset
)
ON CONFLICT (handler_id, event_id) DO NOTHING;
~~~

PostgreSQL trả về số row affected: 1 nếu chèn mới; 0 nếu key đã tồn tại. Khi có hai transaction cùng tranh một key, unique index của database là nơi quyết định chỉ một marker được commit. Transaction còn lại có thể phải chờ kết quả commit/rollback của transaction thứ nhất.

Cú pháp `ON CONFLICT` là của PostgreSQL; các hệ quản trị khác như MySQL hoặc SQL Server có cú pháp và semantics khác. Không copy nguyên ví dụ mà không điều chỉnh database dialect.

## 6. Ví dụ Spring Kafka và Spring JDBC

Giả sử listener nhận `OrderPaid` và cập nhật bảng `order_projection`. Event ID là `UUID`.

### DTO

~~~java
public record OrderPaid(
        UUID eventId,
        String orderId,
        String paymentId,
        long amount) {
}
~~~

### Repository claim idempotency key

~~~java
@Repository
public class ProcessedEventRepository {

    private final JdbcTemplate jdbcTemplate;

    public ProcessedEventRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public boolean insertIfAbsent(
            String handlerId,
            UUID eventId,
            String topic,
            int partition,
            long offset) {

        int inserted = jdbcTemplate.update("""
            INSERT INTO processed_kafka_event (
                handler_id, event_id,
                source_topic, source_partition, source_offset
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (handler_id, event_id) DO NOTHING
            """,
            handlerId, eventId, topic, partition, offset
        );

        return inserted == 1;
    }
}
~~~

Repository không tự commit. Nó phải tham gia transaction do service mở.

### Service chứa database transaction

~~~java
@Service
public class OrderPaidProjection {

    private static final String HANDLER_ID = "order-paid-projection";

    private final ProcessedEventRepository processedEventRepository;
    private final JdbcTemplate jdbcTemplate;

    public OrderPaidProjection(
            ProcessedEventRepository processedEventRepository,
            JdbcTemplate jdbcTemplate) {
        this.processedEventRepository = processedEventRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void apply(
            OrderPaid event,
            String topic,
            int partition,
            long offset) {

        boolean isNew = processedEventRepository.insertIfAbsent(
            HANDLER_ID, event.eventId(), topic, partition, offset
        );

        if (!isNew) {
            return; // Event đã được commit trước đó.
        }

        int updated = jdbcTemplate.update("""
            UPDATE order_projection
               SET status = 'PAID',
                   payment_id = ?,
                   paid_amount = ?
             WHERE order_id = ?
               AND status = 'PENDING_PAYMENT'
            """,
            event.paymentId(),
            event.amount(),
            event.orderId()
        );

        if (updated != 1) {
            throw new InvalidOrderTransitionException(
                "Cannot apply OrderPaid to " + event.orderId()
            );
        }

        // Commit marker và order projection trong cùng DB transaction.
    }
}
~~~

`InvalidOrderTransitionException` là custom exception do ứng dụng định nghĩa. Nếu update sai trạng thái và ném exception, Spring database transaction rollback cả marker lẫn business write, cho phép error handler xử lý đúng theo policy.

### Kafka listener chỉ gọi service

~~~java
@Component
public class OrderPaidListener {

    private final OrderPaidProjection projection;

    public OrderPaidListener(OrderPaidProjection projection) {
        this.projection = projection;
    }

    @KafkaListener(
        topics = "orders.paid",
        groupId = "order-paid-projection")
    public void onMessage(ConsumerRecord<String, OrderPaid> record) {
        projection.apply(
            record.value(),
            record.topic(),
            record.partition(),
            record.offset()
        );
    }
}
~~~

Sử dụng `@Transactional` trên bean service được listener gọi qua Spring proxy. Tránh self-invocation như gọi `this.apply(...)` bên trong cùng class khiến transaction advice không chạy như mong đợi.

Khi ứng dụng có nhiều transaction manager (Kafka và database), cần chỉ rõ transaction manager của database, ví dụ:

~~~java
@Transactional(transactionManager = "jdbcTransactionManager")
public void apply(...) {
    // DB write và inbox marker ở đây.
}
~~~

Ví dụ này chỉ hợp lệ nếu bean `jdbcTransactionManager` tồn tại. Không được nhầm Kafka transaction manager với database transaction manager; Kafka transaction không tự bảo vệ hai SQL statements ở database.

## 7. Vì sao không thể chỉ SELECT rồi INSERT?

Một cách hay gặp nhưng có race condition:

~~~java
if (!repository.existsByEventId(eventId)) {
    walletRepository.addBalance(walletId, amount);
    repository.insertProcessedEvent(eventId);
}
~~~

Hai thread có thể cùng nhận kết quả chưa tồn tại:

~~~text
Thread A                            Thread B
SELECT exists -> false             SELECT exists -> false
UPDATE balance +100                UPDATE balance +100
INSERT marker                      INSERT marker
~~~

Nếu không có unique constraint, cả hai có thể được commit. Ngay cả khi có unique constraint nhưng business update đã commit ở transaction khác, một bên có thể làm side effect trước khi marker của nó bị từ chối.

Cần dùng database atomic uniqueness và **cùng transaction** cho marker cùng business mutation. Lock in-memory, `synchronized` trong một pod hoặc cache local không bảo vệ được nhiều replica.

## 8. Không tách marker và side effect thành hai transactions

Mô hình đúng:

~~~text
BEGIN DB TRANSACTION
  INSERT inbox marker
  UPDATE wallet/ledger/order
COMMIT BOTH
~~~

Mô hình sai 1:

~~~text
BEGIN
  INSERT inbox marker
COMMIT

BEGIN
  UPDATE business state
  -- lỗi ở đây
ROLLBACK

=> Lần retry thấy marker nhưng business chưa được cập nhật.
~~~

Mô hình sai 2:

~~~text
BEGIN
  UPDATE balance
COMMIT

BEGIN
  INSERT inbox marker
  -- process chết trước commit
ROLLBACK

=> Lần retry không thấy marker và cộng balance lần nữa.
~~~

Nếu một trong hai method được gắn `@Transactional(propagation = REQUIRES_NEW)`, hãy xem kỹ vì propagation này có thể tách commit boundary. Đặc biệt tránh gọi API bên ngoài khi giữ DB transaction dài nếu API đó không hỗ trợ idempotency.

## 9. Crash matrix giữa DB và Kafka offset

Trong mô hình listener thông thường, DB transaction ở service kết thúc trước khi listener trả về; Spring Kafka container commit offset theo ack mode sau đó. Các failure window:

| Điểm thất bại | Database | Kafka offset | Kết quả khi redelivery |
|---|---|---|---|
| Trước khi claim marker | Chưa thay đổi | Chưa commit | Thử lại từ đầu |
| Sau insert marker, trước DB commit | Transaction rollback | Chưa commit | Chèn marker và thực hiện lại |
| Sau business mutation, trước DB commit | Transaction rollback | Chưa commit | Thử lại an toàn |
| Sau DB commit, trước Kafka offset commit | Marker + mutation đã commit | Có thể chưa commit | Inbox phát hiện duplicate |
| Sau cả DB commit và offset commit | Mutation đã có | Tiến độ đã commit | Thường không cần đọc lại |
| DLT replay sau khi DB đã xử lý | Marker vẫn có | Offset mới của topic replay | Không lặp side effect |

Mấu chốt: hệ thống **chấp nhận việc cùng record được giao lại**, vì cơ chế inbox đảm bảo DB mutation chỉ áp dụng một lần khi marker đã commit.

Không submit công việc DB vào `CompletableFuture` rồi trả về ngay từ listener. Container có thể commit offset trước khi DB task kết thúc, tạo failure window mất dữ liệu khó phục hồi.

## 10. Kafka Exactly-Once Semantics không thay thế DB idempotency

Spring Kafka hỗ trợ Kafka transactions để atomic commit output Kafka và input offset trong pipeline consume–process–produce. Nhưng database là resource khác. Nếu listener ghi DB rồi commit Kafka transaction thất bại, DB write đã commit vẫn tồn tại.

~~~text
Kafka container transaction bắt đầu
  -> DB transaction commit thành công
  -> Kafka offset/output commit thất bại
  -> Kafka record được giao lại
  -> Nếu thiếu inbox, DB side effect có thể lặp
~~~

Dù dùng `@Transactional` trên listener, phải biết annotation được áp dụng với **transaction manager nào**. Hai resource managers khác nhau không tự động tạo thành một distributed transaction atomic.

Vì vậy, **Kafka EOS trong phạm vi Kafka** và **idempotent DB write** là hai cơ chế bổ sung, không thay thế nhau.

## 11. Khi vừa ghi database vừa phát Kafka output

Nếu business state được ghi vào DB và listener còn publish một event mới sang Kafka, chỉ dùng inbox có thể chưa đủ.

Ví dụ DB commit thành công nhưng Kafka output chưa commit. Lần redelivery thấy inbox marker rồi return sớm: database đúng, nhưng **output Kafka bị thiếu** nếu ứng dụng không tạo lại output.

Một mô hình phổ biến là **transactional outbox**:

~~~sql
CREATE TABLE outbox_event (
    id           UUID PRIMARY KEY,
    event_type   VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);
~~~

Trong **cùng DB transaction**:

~~~text
BEGIN
  INSERT inbox marker nếu chưa có
  UPDATE business state
  INSERT outbox event
COMMIT

Outbox publisher:
  đọc outbox event chưa publish
  gửi Kafka
  đánh dấu đã publish
~~~

Nếu publisher đã gửi Kafka nhưng chết trước khi đánh dấu `published_at`, event outbox có thể được gửi lại. Downstream cần dedup bằng output event ID ổn định. Outbox ngăn làm mất ý định publish đã commit cùng business data; không có nghĩa mọi Kafka send vật lý chỉ xảy ra đúng một lần.

## 12. Cùng event ID nhưng payload mâu thuẫn

Giả sử hai records:

~~~json
{"eventId":"7c53afbb-9e6c-4e84-8df7-dbd3419d39be","amount":200000}
~~~

~~~json
{"eventId":"7c53afbb-9e6c-4e84-8df7-dbd3419d39be","amount":900000}
~~~

Nếu consumer chỉ check ID, record thứ hai bị coi là duplicate và bỏ qua. Điều đó có thể che lỗi producer hoặc vi phạm contract.

Có thể lưu thêm `event_type`, `schema_version`, `payload_hash` hoặc các field nghiệp vụ cần xác minh vào inbox. Khi gặp cùng key:

1. Nếu dữ liệu tương đương theo contract, đây là duplicate bình thường.
2. Nếu payload có mâu thuẫn nghiệp vụ, ghi nhận collision và đưa vào quarantine/DLT.
3. Không âm thầm overwrite marker hoặc áp dụng cả hai thao tác.

Nếu dùng hash, phải chuẩn hóa payload vì JSON có thể đổi thứ tự field hoặc thêm metadata mà business meaning không đổi. Hash chỉ là bằng chứng bổ trợ, không thay thế event identity được producer đảm bảo.

## 13. Idempotency không giải quyết ordering

Idempotency trả lời: **“Đây có phải thao tác đã xử lý?”**

Ordering trả lời: **“Thao tác mới này có hợp lệ ở trạng thái hiện tại không?”**

Ví dụ:

~~~text
event A, seq=10: OrderCreated
event B, seq=11: OrderPaid
event C, seq=12: OrderCancelled
~~~

Nếu A bị chuyển sang retry topic, B có thể được xử lý trước A. Cả hai có ID khác nhau nên inbox không coi là duplicate, nhưng thứ tự nghiệp vụ vẫn có thể sai.

Một kỹ thuật là dùng optimistic version:

~~~sql
UPDATE order_projection
   SET status = :new_status,
       event_sequence = :new_sequence
 WHERE order_id = :order_id
   AND event_sequence < :new_sequence;
~~~

Điều kiện này ngăn event cũ ghi đè event mới, nhưng nếu nghiệp vụ bắt buộc không được **nhảy qua version**, cần kiểm tra chính xác `expected_previous_sequence` hoặc giữ event chờ dependency.

Hệ thống thường cần đồng thời:

- `eventId` để dedup.
- `aggregateId` để xác định đối tượng bị tác động.
- `eventSequence`/version để kiểm tra thứ tự.
- Business state machine để kiểm tra transition hợp lệ.

## 14. Khi nào dùng topic/partition/offset làm key?

Nếu upstream chưa có event ID bền vững, có thể dùng tọa độ Kafka nguồn:

~~~text
(handler_id, source_topic, source_partition, source_offset)
~~~

Cách này deduplicate **một physical Kafka record**, không nhất thiết cùng logical event:

- Republish event sang offset mới sẽ không bị phát hiện.
- DLT replay hoặc retry topic có topic/offset mới.
- Topic xóa rồi tạo lại có thể tái sử dụng cùng name và offset trong vòng đời khác.
- Cùng business operation ở hai records khác nhau vẫn được xem là hai operation.

Nếu phải dựa vào coordinates, nên lưu **original topic/partition/offset** trong metadata khi forward và xác định chính sách cho việc topic recreation. Với hệ thống thanh toán hoặc DB mutation quan trọng, cần ưu tiên một event/operation ID của nghiệp vụ.

## 15. Retention của idempotency keys

Bảng inbox có thể tăng rất nhanh. Nhưng xóa marker quá sớm khiến một DLT replay sau vài tuần bị coi là thao tác mới.

Retain key nên dựa trên:

- Kafka topic retention.
- Retry topic và DLT retention.
- Thời gian doanh nghiệp cho phép replay.
- Khả năng upstream resend sau outage hoặc migration.
- Yêu cầu audit, tài chính và kiểm soát duplicate.
- Cách chia shard/partition và chi phí index.

Các lựa chọn gồm giữ lâu dài với ledger quan trọng, partition inbox table theo thời gian, chuyển marker cũ sang kho lịch sử hoặc đặt policy replay chỉ trong cửa sổ đã bảo vệ. **Không chọn TTL chỉ bằng tổng thời gian retry vài giây** nếu DLT có thể replay sau nhiều tháng.

Khi thay `handler_id` hoặc schema key, cần kế hoạch migrate marker cũ, tránh tạo một “làn sóng event mới” do các key đã xử lý không còn match.

## 16. Redis/cache không tự bảo đảm DB write một lần

`SET NX` trên Redis có thể claim key atomic trong Redis nhưng không tạo transaction atomic với database:

~~~text
Redis SET NX key -> success
  |
  +-- DB UPDATE thất bại
  |
Redis vẫn chứa key -> retry bị chặn nhầm
~~~

Cache còn có eviction/TTL, restart và replication issues. Một cache có thể hữu ích để tối ưu lookup, nhưng database unique constraint cùng DB transaction nên là nguồn chân lý nếu business write phải được bảo vệ bền vững.

Tránh dùng `ConcurrentHashMap` hoặc Java `synchronized` để deduplicate trong nhiều pod: chúng chỉ bảo vệ một JVM và mất dữ liệu khi restart.

## 17. Phân loại exception với Kafka retry

| Trường hợp | Hướng xử lý |
|---|---|
| Inbox marker đã tồn tại và operation thật sự đã commit | Trả thành công, không ghi lại |
| DB deadlock/connection lỗi tạm thời | Rollback, retry có backoff |
| Payload thiếu field hoặc event ID không hợp lệ | Non-retryable; DLT/quarantine |
| Business transition sai | Rollback marker, phân loại theo nghiệp vụ |
| Cùng event ID khác payload | Cảnh báo collision, quarantine |
| DLT publishing thất bại | Recovery chưa thành công; không âm thầm bỏ record |
| Unique constraint business operation khác xung đột | Phân biệt duplicate với dữ liệu mâu thuẫn |

Với non-transactional Spring Kafka consumer, `DefaultErrorHandler` có thể retry lỗi tạm thời và chuyển lỗi permanent sang DLT. Với Kafka transactional listener, xử lý sau rollback thường dùng `DefaultAfterRollbackProcessor`. Không cơ chế Kafka nào thay database transaction trong việc atomically ghi marker và business mutation.

## 18. Batch listener và concurrency

Khi xử lý batch, một phần record có thể đã được DB commit trước khi record tiếp theo thất bại. Nếu Kafka batch bị xử lý lại, inbox key của các record đã commit phải giúp skip duplicate.

Có hai kiểu transaction boundary:

- **Mỗi record một DB transaction:** xử lý từng event qua service transactional; những record đã commit có marker riêng.
- **Cả batch một DB transaction:** tất cả marker và mutations commit hoặc rollback chung; cần cân nhắc transaction time, lock và batch retry semantics.

Với nhiều consumer instances, unique index database bảo vệ concurrent claim. Nếu hai transactions cùng insert một `(handler_id,event_id)`, một transaction có thể chờ để biết transaction kia commit hay rollback. Đặt DB timeout/retry phù hợp và theo dõi lock contention.

Nếu dùng nhiều database/shard, key phải được route đúng shard hoặc có cơ chế uniqueness toàn cục phù hợp. Một unique index trên từng shard không bảo đảm uniqueness nếu cùng logical event được ghi vào hai shard khác nhau.

## 19. Thiết kế kiểm thử cho idempotency

Một bộ kịch bản nên bao phủ:

1. Cùng event ID nhận hai lần: business state chỉ áp dụng một lần.
2. Hai threads cùng claim key: chỉ một transaction được quyền áp dụng mutation.
3. Lỗi sau marker insert nhưng trước DB commit: marker và side effect cùng rollback.
4. Lỗi sau DB commit nhưng trước Kafka offset commit: redelivery được skip.
5. Replay từ DLT giữ event ID: không tạo business effect mới.
6. Hai handler độc lập cùng event ID: mỗi handler được áp dụng đúng phần việc riêng.
7. Cùng event ID nhưng payload mâu thuẫn: báo collision, không lặng lẽ bỏ.
8. Event đến đảo thứ tự: version/state-machine bảo vệ invariant.
9. DB connection timeout/deadlock: retry không lưu marker nửa vời.
10. Outbox được publish lặp: downstream dedup output event ID.

Các tình huống này là **thiết kế kiểm thử cho người học**; trong bước tạo bài này không chạy kiểm thử hay QA nội dung. Test concurrency nên sử dụng database thật hoặc Testcontainers để kiểm chứng unique index, transaction isolation và SQL dialect.

## 20. Observability và vận hành

| Chỉ số | Ý nghĩa |
|---|---|
| `db_idempotency_new_total` | Số business operations mới được áp dụng |
| `db_idempotency_duplicate_total` | Lượng record được nhận lại |
| `db_idempotency_collision_total` | Cùng key với dữ liệu mâu thuẫn |
| `db_transaction_rollback_total` | Lỗi trước DB commit |
| Inbox unique key conflict/wait | Tranh chấp giữa các consumer |
| Kafka consumer lag và rebalance | Tiến độ offset và redelivery |
| DLT volume/replay count | Rủi ro duplicate lâu ngày |
| Inbox storage/index size | Chi phí retention |
| Outbox publish failure | Luồng DB-to-Kafka cần khôi phục |

Log một event có thể chứa `eventId`, `handlerId`, `topic`, `partition`, `offset`, kết quả `NEW` / `DUPLICATE` / `FAILED`. Không dùng event ID làm metric label vì cardinality cao; dùng nó trong tracing/log có phân quyền phù hợp.

Ví dụ:

~~~text
kafka_db_apply handler=order-paid-projection
  eventId=7c53afbb-9e6c-4e84-8df7-dbd3419d39be
  source=orders.paid-2@418
  outcome=DUPLICATE
  mutation=SKIPPED
~~~

Nếu số duplicate tăng đột biến, hãy kiểm tra crash/rebalance, offset commit failures, retry topic, DLT replay và upstream duplicate thay vì chỉ đổ lỗi cho broker.

## 21. Runbook khi phát hiện DB write bị lặp

1. Xác định business operation bị nhân đôi: event ID, payment ID, order ID, loại mutation.
2. Truy vết các lần nhận record qua topic/partition/offset, consumer group và retry stage.
3. Xác minh producer giữ nguyên ID qua retry/republish.
4. Kiểm tra unique constraint tồn tại trên database production và đúng scope.
5. Kiểm tra marker + business write thực sự chạy cùng một DB transaction.
6. Kiểm tra Spring `@Transactional` được áp dụng qua proxy và dùng đúng DB transaction manager.
7. Tìm `REQUIRES_NEW`, JDBC auto-commit, async task hoặc network call làm tách commit boundary.
8. Kiểm tra handler có dựa vào `SELECT EXISTS` thay atomic insert không.
9. Kiểm tra retention marker và các trường hợp DLT replay muộn.
10. Kiểm tra cùng key với payload mâu thuẫn và event ordering.
11. Nếu còn Kafka output, đánh giá outbox và failure window DB commit/Kafka output fail.
12. Khắc phục dữ liệu đã bị ghi trùng bằng quy trình nghiệp vụ có audit; không tự xóa marker rồi replay hàng loạt.

Với ledger và thanh toán, việc bù trừ side effect phải tuân theo nghiệp vụ; không tùy tiện đảo ngược một DB write nếu các hệ thống khác đã dựa vào kết quả đó.

## 22. Các sai lầm cần tránh

- Dùng `orderId` làm ID cho mọi event của cùng order.
- Tạo UUID mới trong consumer mỗi lần nhận record.
- Dùng Kafka offset làm business operation ID trong mọi trường hợp.
- Chỉ check `exists` trong Java mà không có unique constraint DB.
- Commit marker ở transaction riêng trước mutation.
- Claim key trong Redis rồi update DB như thể hai bước atomic.
- Cho listener return trước khi DB transaction commit.
- Coi `KafkaTransactionManager` là transaction manager của database.
- Bỏ qua cùng key khác payload mà không điều tra.
- Bỏ marker sớm hơn cửa sổ DLT replay.
- Chỉ dùng inbox mà quên outbox khi business state cần phát Kafka output.
- Coi idempotency đã tự bảo vệ ordering giữa các event khác nhau.

## 23. Checklist triển khai

- [ ] Idempotency key đại diện cho operation và ổn định qua retry/replay.
- [ ] Scope key gồm handler/tenant khi cần.
- [ ] Có unique constraint bền vững trong database.
- [ ] Marker và business mutation được commit trong cùng DB transaction.
- [ ] Transaction rollback cả marker nếu business write thất bại.
- [ ] Listener chỉ trả success khi DB commit thật sự hoàn tất.
- [ ] Không có self-invocation hoặc transaction manager bị chọn nhầm.
- [ ] Có kiểm soát same-key/different-payload collision.
- [ ] Có cơ chế version/sequence nếu ordering quan trọng.
- [ ] Retention marker bao phủ retry, DLT và manual replay.
- [ ] Inbox/outbox được thiết kế nếu cần publish Kafka sau DB commit.
- [ ] Có log, metrics và runbook cho duplicate/collision/rollback.

**Kết luận:** Idempotency key cho DB write giúp Spring Kafka consumer tạo **hiệu quả nghiệp vụ không bị nhân đôi** trên nền at-least-once delivery. Hãy dùng ID ổn định của event hoặc business operation, unique constraint trong database và transaction chung giữa marker với side effect. Khi Kafka giao lại record sau crash, retry hoặc DLT replay, listener có thể nhận biết duplicate mà không cập nhật DB lần hai. Với output Kafka và các tác động khác, cần thiết kế thêm outbox, idempotency của hệ thống đích và kiểm soát thứ tự — Kafka offset hay Kafka transaction không tự thay thế các yêu cầu đó.
