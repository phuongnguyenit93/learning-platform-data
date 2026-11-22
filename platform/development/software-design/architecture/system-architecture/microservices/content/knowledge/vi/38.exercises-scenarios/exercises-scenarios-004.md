# Ngăn gửi trùng thông báo bằng Outbox và consumer lặp an toàn

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Bài tập và tình huống. README hướng dẫn thiết kế luồng thông báo đáng tin cậy khi một nghiệp vụ được commit trong database và cần phát event sang broker để gửi email, SMS, push hoặc webhook. Trọng tâm là Transactional Outbox, relay theo polling hoặc CDC, delivery at-least-once, consumer idempotency/Inbox, xử lý timeout từ provider, ordering, retry, DLQ, replay, quan sát và kiểm thử lỗi.

## 1. Bài toán: một hành động nghiệp vụ có thể tạo nhiều thông báo

Giả sử khách hàng đặt đơn hàng. Order Service ghi đơn vào PostgreSQL rồi phát `OrderPlaced` lên Kafka để Notification Service gửi email xác nhận.

Một cách triển khai ngây thơ:

1. Mở transaction database.
2. Insert Order.
3. Gọi Kafka producer.
4. Commit database.

Cách này có hai failure window:

- Kafka nhận event nhưng database commit thất bại. Consumer gửi email cho một đơn hàng không tồn tại.
- Database commit thành công nhưng process chết trước khi gửi Kafka. Đơn hàng tồn tại nhưng không có event và khách hàng không nhận email.

Nếu đổi thứ tự, commit database trước rồi publish event, cửa sổ lỗi vẫn còn: process có thể chết sau commit và trước publish. Nếu publish trước rồi commit, consumer có thể thấy event trước khi dữ liệu nghiệp vụ bền vững.

Đây là vấn đề **dual write**: hai hệ thống độc lập (database và message broker) cần được cập nhật như một thao tác logic, nhưng không có một transaction nguyên tử chung bảo đảm cả hai cùng thành công hoặc cùng thất bại.

Một vấn đề khác xuất hiện khi relay hoặc consumer retry:

- Relay gửi event thành công nhưng mất response hoặc chết trước khi đánh dấu event đã publish.
- Broker đã lưu message nhưng publisher không nhận được acknowledgement.
- Consumer xử lý nghiệp vụ xong nhưng chết trước khi commit offset/ack.
- Provider email nhận yêu cầu nhưng response timeout, khiến client không biết email đã được nhận hay chưa.
- Broker redeliver cùng message sau rebalance, network failure hoặc retry.

Vì vậy, hệ thống phân tán thường phải chấp nhận **một message có thể được giao nhiều lần**. Mục tiêu thiết kế là mỗi business effect chỉ xảy ra một lần theo định nghĩa nghiệp vụ, dù message được nhận nhiều lần.

## 2. Hai cơ chế phối hợp: Outbox ở producer, Inbox ở consumer

Transactional Outbox giải quyết việc ghi trạng thái nghiệp vụ và ý định phát event trong cùng database transaction. Consumer Inbox hoặc idempotency store giải quyết việc một event được giao nhiều lần.

~~~text
Client
  |
  v
Order Service
  |
  | one DB transaction
  +--> INSERT orders
  +--> INSERT outbox_events
  |
  v
Outbox Relay / CDC
  |
  | at-least-once publish
  v
Message Broker
  |
  v
Notification Consumer
  |
  | one DB transaction
  +--> INSERT inbox_events (unique event_id)
  +--> INSERT notification_jobs
  |
  v
Notification Dispatcher
  |
  v
Email / SMS / Push Provider
~~~

Hai phần có vai trò khác nhau:

- **Outbox:** không để event bị mất giữa lúc commit dữ liệu nghiệp vụ và lúc publish.
- **Inbox/idempotent consumer:** không áp dụng cùng một business effect nhiều lần khi broker giao trùng.
- **Provider idempotency:** giảm rủi ro gửi lặp khi một request tới nhà cung cấp đã được chấp nhận nhưng response bị mất.
- **Reconciliation:** phát hiện trạng thái không rõ giữa hệ thống nội bộ và provider.

Outbox không tự làm consumer idempotent. Inbox cũng không thể bảo đảm email chỉ được gửi đúng một lần nếu nhà cung cấp không có cơ chế idempotency hoặc tra cứu trạng thái.

## 3. Transactional Outbox hoạt động thế nào?

Trong cùng một transaction database, service ghi:
1. Thay đổi nghiệp vụ (ví dụ Order).
2. Một bản ghi Outbox mô tả event cần phát.

Nếu transaction rollback, cả Order và Outbox đều rollback. Nếu commit, cả hai cùng tồn tại bền vững. Một relay độc lập đọc Outbox và publish event lên broker.

Ví dụ:

~~~text
BEGIN;

INSERT INTO orders (...);

INSERT INTO outbox_events (
  event_id, aggregate_type, aggregate_id,
  event_type, payload, occurred_at
);

COMMIT;
~~~

Điểm quan trọng là service không cần một distributed transaction giữa PostgreSQL và Kafka. Database transaction chỉ bảo đảm **business state và publication intent** cùng commit. Việc chuyển intent thành message diễn ra bất đồng bộ và có thể retry.

Nếu broker tạm ngừng, Outbox giữ event để relay gửi lại khi broker phục hồi. Nếu service chết ngay sau commit, relay khác vẫn có thể tiếp tục từ bản ghi bền vững.

## 4. Mô hình dữ liệu Outbox

Một bảng tổng quát có thể gồm:

~~~sql
CREATE TABLE outbox_events (
    event_id          UUID PRIMARY KEY,
    aggregate_type    VARCHAR(120) NOT NULL,
    aggregate_id      VARCHAR(160) NOT NULL,
    aggregate_version BIGINT,
    event_type        VARCHAR(200) NOT NULL,
    schema_version    INTEGER NOT NULL,
    payload           JSONB NOT NULL,
    headers           JSONB,
    occurred_at       TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at      TIMESTAMPTZ,
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMPTZ,
    last_error_code   VARCHAR(100)
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_events (created_at, event_id)
    WHERE published_at IS NULL;
~~~

Các cột có ý nghĩa:

| Cột | Mục đích |
| --- | --- |
| `event_id` | ID ổn định duy nhất của event, dùng cho dedup |
| `aggregate_type` | Loại aggregate tạo event |
| `aggregate_id` | ID aggregate, ví dụ order ID |
| `aggregate_version` | Version/sequence để kiểm soát thứ tự nếu cần |
| `event_type` | Tên sự kiện đã xảy ra |
| `schema_version` | Phiên bản contract |
| `payload` | Nội dung event đã serialize |
| `headers` | Metadata được allowlist, ví dụ correlation ID |
| `occurred_at` | Thời điểm nghiệp vụ xảy ra |
| `created_at` | Thời điểm ghi Outbox |
| `published_at` | Thời điểm relay đánh dấu đã publish |
| `attempts` | Số lần thử publish |
| `next_attempt_at` | Thời điểm được phép thử lại |
| `last_error_code` | Mã lỗi cuối, không lưu secret hoặc payload nhạy cảm |

Schema thực tế có thể khác. Một số hệ thống tách bảng trạng thái relay, lưu payload dưới dạng text/bytea, dùng partitioning hoặc CDC. Chọn cấu trúc phù hợp database và throughput.

`event_id` phải được tạo một lần khi transaction tạo event và giữ nguyên qua mọi lần retry. Không tạo ID mới mỗi lần relay gửi lại; nếu làm vậy, consumer sẽ tưởng mỗi lần giao là một event mới.

Không nên lưu object JPA tùy ý hoặc toàn bộ entity graph vào payload. Hãy tạo event contract rõ ràng, chứa thông tin cần thiết cho consumer và có schema version.

## 5. Tạo Outbox cùng transaction nghiệp vụ trong Java/Spring

Ví dụ entity đơn giản:

~~~java
@Entity
@Table(name = "outbox_events")
public class OutboxEventEntity {
    @Id
    private UUID eventId;

    private String aggregateType;
    private String aggregateId;
    private Long aggregateVersion;
    private String eventType;
    private Integer schemaVersion;

    @Column(columnDefinition = "jsonb")
    private String payload;

    private Instant occurredAt;
    private Instant createdAt;
    private Instant publishedAt;
    private Integer attempts;

    protected OutboxEventEntity() {}

    public OutboxEventEntity(
        UUID eventId,
        String aggregateType,
        String aggregateId,
        Long aggregateVersion,
        String eventType,
        Integer schemaVersion,
        String payload,
        Instant occurredAt
    ) {
        this.eventId = eventId;
        this.aggregateType = aggregateType;
        this.aggregateId = aggregateId;
        this.aggregateVersion = aggregateVersion;
        this.eventType = eventType;
        this.schemaVersion = schemaVersion;
        this.payload = payload;
        this.occurredAt = occurredAt;
        this.createdAt = Instant.now();
        this.attempts = 0;
    }
}
~~~

Application service:

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final ObjectMapper objectMapper;

    public OrderApplicationService(
        OrderRepository orders,
        OutboxRepository outbox,
        ObjectMapper objectMapper
    ) {
        this.orders = orders;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public OrderId placeOrder(PlaceOrder command) {
        Order order = Order.place(command);
        orders.save(order);

        OrderPlaced event = OrderPlaced.from(order);
        String payload = serialize(event);

        outbox.save(new OutboxEventEntity(
            event.eventId(),
            "Order",
            order.id().toString(),
            order.version(),
            "OrderPlaced",
            1,
            payload,
            event.occurredAt()
        ));

        return order.id();
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize outbox event", ex);
        }
    }
}
~~~

Ví dụ giả định `orders` và `outbox` dùng cùng datasource và cùng transaction manager. Cần bảo đảm hai repository tham gia **cùng một database transaction**. Nếu Outbox được ghi vào database khác, atomicity không còn được bảo đảm.

Không publish Kafka trực tiếp trong method này rồi nghĩ rằng `@Transactional` sẽ bao trùm cả broker. Spring transaction của JPA không tự tạo một transaction nguyên tử với Kafka. Một transaction synchronization hoặc `afterCommit` có thể giúp trigger relay sớm, nhưng không thay thế Outbox bền vững: process vẫn có thể chết sau commit và trước callback.

## 6. Event contract nên biểu diễn sự kiện đã xảy ra

Ví dụ event:

~~~json
{
  "eventId": "7df4d6ef-21c8-4d9b-b8b2-2adf09f44a11",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-12T03:15:00Z",
  "aggregate": {
    "type": "Order",
    "id": "ord-123",
    "version": 4
  },
  "data": {
    "customerReference": "cus-456",
    "notificationLocale": "vi-VN",
    "orderNumber": "A-2026-00123"
  }
}
~~~

Đây là payload minh họa. Event cần:
- ID duy nhất, ổn định qua retry.
- Event type và schema version.
- Thời điểm xảy ra theo business semantics.
- Aggregate identity/version nếu ordering cần thiết.
- Payload tối thiểu đủ cho consumer.
- Correlation/causation metadata nếu có mục đích.
- Data classification và retention.
- Producer owner và contract compatibility.

Một `OrderPlaced` event nên thể hiện đơn đã được tạo thành công. Không dùng event như `SendEmailNow` nếu đó chỉ là một lệnh kỹ thuật, trừ khi command semantics được thiết kế rõ. Consumer có thể quyết định kênh và template theo policy của Notification domain.

Không đưa access token, password, payment card data hoặc toàn bộ customer profile vào event. Event có thể được lưu ở broker lâu, replay nhiều lần và được nhiều consumer đọc.

## 7. Polling relay: đọc Outbox rồi publish

Một relay polling định kỳ tìm các event chưa publish, gửi lên broker và cập nhật trạng thái. Pseudocode:

~~~text
loop:
  rows = claim unpublished rows
  for each row:
    publish message with stable event_id
    wait for broker acknowledgement
    mark row published
  wait briefly
~~~

Trình tự phải là:
1. Claim event.
2. Publish.
3. Chờ broker xác nhận theo semantics đã cấu hình.
4. Đánh dấu Outbox đã publish.

Nếu đánh dấu trước khi publish, process có thể chết và event bị mất. Nếu publish xong rồi chết trước khi đánh dấu, event có thể được gửi lại. Đây là lý do consumer phải idempotent.

### 7.1. Claim an toàn khi có nhiều relay

Nhiều relay có thể cùng chạy để tăng throughput. Nếu không khóa hoặc claim row, hai relay có thể đọc cùng event và publish đồng thời.

Với PostgreSQL, một pattern thường dùng là transaction ngắn với `FOR UPDATE SKIP LOCKED`:

~~~sql
BEGIN;

SELECT event_id
FROM outbox_events
WHERE published_at IS NULL
  AND (next_attempt_at IS NULL OR next_attempt_at <= now())
ORDER BY created_at, event_id
FOR UPDATE SKIP LOCKED
LIMIT 100;

-- Claim/update lease hoặc giữ lock trong transaction publish
-- theo thiết kế relay.

COMMIT;
~~~

Đoạn trên chỉ minh họa phần lấy hàng. Không giữ transaction và row locks mở lâu trong khi chờ broker nếu throughput hoặc lock contention là vấn đề. Có thể dùng claim lease (`claimed_by`, `lease_until`) rồi publish ngoài transaction, với cơ chế lease expiry và xử lý worker chết.

Một lease cần:
- Worker ID.
- Thời điểm hết hạn.
- Số lần claim.
- Cách reclaim sau khi worker crash.
- Cách tránh worker cũ cập nhật trạng thái sau khi lease đã được worker khác nhận.
- Không đánh dấu published khi broker chưa xác nhận.

`SKIP LOCKED` là tính năng cụ thể của một số database, không phải SQL portable. Với MySQL hoặc hệ khác, chọn locking/claim strategy tương ứng.

### 7.2. Không giả định batch publish là nguyên tử

Nếu một batch có 100 event, broker có thể nhận 97 và 3 event lỗi. Relay cần theo dõi acknowledgement theo từng event hoặc theo semantics batch API; không đánh dấu cả batch published chỉ vì request tổng thể trả về.

## 8. Polling relay: retry và backoff

Khi broker unavailable hoặc lỗi tạm thời:
- Giữ Outbox event chưa publish.
- Tăng `attempts`.
- Đặt `next_attempt_at` theo exponential backoff.
- Thêm jitter để nhiều relay không retry đồng thời.
- Ghi `last_error_code` đã chuẩn hóa.
- Đưa alert khi tuổi event chưa publish vượt ngưỡng nghiệp vụ.

Ví dụ backoff:

\[
delay_n = \min(delay_{max}, delay_{base} \times 2^n) + jitter
\]

Các tham số cần giới hạn. Không retry liên tục mỗi vài mili giây khi broker đang outage; điều đó tạo load và log storm. Không retry vô hạn mà không có cảnh báo hoặc cơ chế xử lý poison event.

Phân biệt:
- Lỗi tạm thời: timeout, throttling, leader election, network interruption.
- Lỗi cấu hình/quyền: topic không tồn tại, ACL sai, credential hết hạn.
- Lỗi dữ liệu: payload serialize sai, schema không hợp lệ.
- Lỗi logic: event không phù hợp contract.

Lỗi tạm thời có thể retry. Lỗi cấu hình cần alert và sửa. Payload lỗi không nên bị retry nóng vô hạn; cần quarantine/parking state và quy trình điều tra, nhưng không được âm thầm bỏ event.

## 9. Cửa sổ duplicate của Outbox relay

Một tình huống quan trọng:

1. Relay gửi event `E1`.
2. Broker ghi event thành công.
3. Broker gửi acknowledgement nhưng network bị đứt trước khi relay nhận.
4. Relay timeout, không biết broker đã nhận hay chưa.
5. Relay thử lại `E1`.
6. Broker có thể chứa hai bản giao cùng event ID.

Một tình huống khác: relay nhận acknowledgement, nhưng process chết trước khi cập nhật `published_at`. Khi khởi động lại, event được gửi lại.

Không thể loại bỏ hoàn toàn cửa sổ này chỉ bằng thứ tự cập nhật database và broker nếu không có transaction chung được hỗ trợ end-to-end. Thiết kế phổ biến là **at-least-once publication + idempotent consumption**.

Broker producer idempotence có thể giảm duplicate do retry trong một producer session/semantics cụ thể, nhưng không thay thế event identity và consumer dedup qua process restart, relay reprocessing hoặc nhiều publisher.

## 10. CDC relay: dùng Change Data Capture

Thay vì polling bảng Outbox, có thể dùng CDC đọc transaction log của database (ví dụ PostgreSQL WAL hoặc MySQL binlog) rồi chuyển event sang broker.

~~~text
Business transaction
  |
  +--> orders table
  +--> outbox_events table
           |
           v
      DB transaction log
           |
           v
       CDC connector
           |
           v
       Kafka topic
~~~

Ưu điểm:
- Giảm polling queries và row-lock contention.
- Có thể giữ thứ tự commit trong phạm vi connector/partition phù hợp.
- Tận dụng log stream của database.
- Phù hợp throughput cao hoặc nhiều bảng Outbox.

Nghĩa vụ bổ sung:
- Connector lifecycle và offset management.
- Replication slot/binlog retention.
- Schema history và schema evolution.
- Snapshot initial load.
- Connector lag và restart.
- WAL/binlog disk growth khi connector dừng.
- Duplicate sau restart hoặc offset replay.
- Routing/partitioning và transform.
- Monitoring và backup cấu hình.

CDC cũng không làm delivery exactly-once đến mọi consumer. Connector có thể phát lại sau khi restart hoặc khi offset chưa được commit; consumer vẫn cần idempotency.

### 10.1. Polling hay CDC?

| Tiêu chí | Polling relay | CDC relay |
| --- | --- | --- |
| Độ phức tạp ban đầu | Thường thấp hơn | Cao hơn |
| Tải database | Query/claim/update theo batch | Đọc transaction log |
| Ordering | Phải thiết kế query/partition/aggregate | Có thể tận dụng log order, nhưng còn partition semantics |
| Throughput | Phù hợp thấp đến vừa, có thể scale | Phù hợp workload lớn nếu connector được vận hành tốt |
| Vận hành | Worker, retry, lease, cleanup | Connector, offsets, replication slots, schema history |
| Latency | Theo polling interval và batch | Gần realtime theo log stream |
| Recovery | Reclaim rows và retry | Replay từ offset/checkpoint, quản lý log retention |

Chọn theo throughput, latency, database capability và năng lực vận hành. Đừng chọn CDC chỉ vì nó có vẻ hiện đại nếu nhóm chưa có năng lực quản lý connector và transaction log retention.

## 11. Consumer idempotency: cùng event, cùng business effect

Consumer có thể nhận cùng event nhiều lần. Một consumer idempotent bảo đảm xử lý lại cùng event không tạo thêm business effect ngoài ý muốn.

Ví dụ Notification Service nhận `OrderPlaced`. Nếu cùng event được giao ba lần, nó chỉ nên tạo một notification job theo policy, thay vì ba job gửi email.

Một cách phổ biến là **Inbox table** với unique key theo consumer và event ID:

~~~sql
CREATE TABLE inbox_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      UUID NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ,
    status        VARCHAR(30) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer thực hiện trong một database transaction:
1. Insert Inbox record.
2. Nếu unique conflict, event đã được xử lý hoặc đang được ghi nhận; bỏ qua duplicate theo policy.
3. Nếu insert mới, ghi business effect hoặc notification job.
4. Commit cả Inbox và business effect cùng nhau.
5. Chỉ sau khi transaction thành công mới ack/commit message offset.

Nếu transaction rollback, Inbox record và business effect cùng rollback, broker có thể giao lại event. Nếu transaction commit nhưng ack bị mất, broker giao lại; unique key giúp consumer nhận ra duplicate.

## 12. Consumer Inbox trong Java/Spring

Ví dụ service xử lý event:

~~~java
@Service
public class OrderPlacedConsumer {
    private final InboxRepository inbox;
    private final NotificationJobRepository jobs;

    public OrderPlacedConsumer(
        InboxRepository inbox,
        NotificationJobRepository jobs
    ) {
        this.inbox = inbox;
        this.jobs = jobs;
    }

    @Transactional
    public void handle(OrderPlaced event) {
        int inserted = inbox.insertIfAbsent(
            "notification-order-placed",
            event.eventId()
        );

        if (inserted == 0) {
            return;
        }

        jobs.save(NotificationJob.pending(
            event.eventId(),
            event.orderId(),
            "ORDER_CONFIRMATION"
        ));
    }
}
~~~

`insertIfAbsent` cần được triển khai bằng thao tác database nguyên tử, không phải `SELECT` rồi `INSERT` ở hai câu lệnh không khóa. Với PostgreSQL:

~~~sql
INSERT INTO inbox_events (
    consumer_name, event_id, status
)
VALUES (:consumer, :eventId, 'RECEIVED')
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Kiểm tra số row được insert. Nếu bằng 0, unique conflict cho biết event đã có. Nếu bằng 1, transaction hiện tại sở hữu lần xử lý đầu tiên.

Một entity Inbox có thể dùng `status=RECEIVED/PROCESSED/FAILED`, nhưng state machine cần rõ. Nếu insert Inbox và đánh dấu PROCESSED trước khi business effect hoàn tất ở một transaction khác, event có thể bị bỏ qua vĩnh viễn sau crash. Ưu tiên ghi dedup record và effect cùng transaction khi chúng cùng database.

## 13. Vì sao `SELECT` rồi `INSERT` không đủ?

Một cách ngây thơ:

~~~java
if (!inbox.existsByEventId(event.eventId())) {
    inbox.save(new InboxEvent(event.eventId()));
    createNotification();
}
~~~

Hai consumer thread có thể chạy đồng thời:

~~~text
Consumer A: SELECT -> not found
Consumer B: SELECT -> not found
Consumer A: INSERT
Consumer B: INSERT
Consumer A: create job
Consumer B: create job
~~~

Cả hai cùng thấy chưa có record. Chỉ unique constraint ở database mới là hàng rào cuối cùng chống race condition.

Có thể xử lý duplicate key exception, nhưng trong một số ORM/transaction manager, exception có thể đánh dấu transaction rollback-only. Dùng `INSERT ... ON CONFLICT DO NOTHING` hoặc API tương đương giúp điều khiển kết quả rõ hơn.

**Không chỉ kiểm tra ở memory, cache hoặc ConcurrentHashMap.** Những cơ chế đó không hoạt động xuyên process, restart, nhiều replica hoặc region.

## 14. Transaction boundary của consumer

Cần xác định chính xác thứ gì nằm trong một transaction:

~~~text
Broker delivers event
        |
        v
BEGIN DB transaction
  INSERT inbox (unique consumer + event ID)
  INSERT notification_job
  UPDATE notification state
COMMIT
        |
        v
ACK / commit broker offset
~~~

Nếu consumer commit broker offset trước database commit, process có thể chết và message không được giao lại dù business effect chưa lưu.

Nếu database commit trước broker ack, process có thể chết ở giữa; message được giao lại nhưng Inbox dedup giúp bỏ qua effect lần hai.

Đây là lựa chọn phổ biến: **DB effect commit trước, broker ack sau**, chấp nhận redelivery và xử lý bằng idempotency.

Transaction manager của Spring Kafka và JPA có thể được cấu hình theo nhiều cách, nhưng không mặc định mọi transaction đều nguyên tử qua broker và database. Hãy xác định transaction boundary thật, ack mode, offset commit timing và failure behavior theo version/config đang dùng.

## 15. Notification job và dispatcher tách khỏi event consumer

Không nên giữ Kafka consumer thread mở trong khi chờ provider email/SMS lâu hoặc retry nhiều lần. Một thiết kế bền vững:

1. Consumer ghi Inbox + Notification Job trong một transaction.
2. Dispatcher claim job đang PENDING.
3. Dispatcher gọi provider.
4. Lưu kết quả hoặc trạng thái không xác định.
5. Retry có kiểm soát nếu lỗi tạm thời.
6. Cập nhật delivery receipt khi có callback.

Ví dụ bảng:

~~~sql
CREATE TABLE notification_jobs (
    job_id            UUID PRIMARY KEY,
    source_event_id   UUID NOT NULL,
    channel           VARCHAR(30) NOT NULL,
    recipient_ref     VARCHAR(160) NOT NULL,
    template_key      VARCHAR(120) NOT NULL,
    payload           JSONB NOT NULL,
    status            VARCHAR(30) NOT NULL,
    provider_key      VARCHAR(200) NOT NULL,
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMPTZ,
    provider_message_id VARCHAR(200),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at           TIMESTAMPTZ,
    last_error_code   VARCHAR(100),
    UNIQUE (source_event_id, channel, template_key, recipient_ref)
);
~~~

Unique key business phải được chọn theo định nghĩa thông báo. Có thể một Order cần một email xác nhận và một push; đó là hai job hợp lệ vì channel khác nhau. Nếu cùng event cần gửi một email cho nhiều recipient, recipient reference là một phần của uniqueness scope.

Không phải mọi hệ thống cần bảng job riêng. Nếu consumer có thể thực hiện một effect ngắn và idempotent trong cùng transaction, Inbox + effect có thể đủ. Với provider call bên ngoài, tách job thường giúp kiểm soát retry và trạng thái không rõ tốt hơn.

## 16. Provider timeout: đã nhận yêu cầu hay chưa?

Một tình huống khó:

1. Dispatcher gửi email request với idempotency key `N-123`.
2. Provider nhận và tạo message.
3. Response bị mất trên mạng.
4. Dispatcher timeout và không biết provider đã nhận hay chưa.
5. Nếu gửi lại mà provider không hỗ trợ idempotency, khách hàng có thể nhận email hai lần.

Inbox chỉ ngăn consumer tạo job hai lần. Nó không tự bảo đảm provider không xử lý một HTTP request lặp.

Ưu tiên theo thứ tự:
- Dùng provider API có idempotency key ổn định.
- Retry cùng key cho cùng một logical notification.
- Nếu provider hỗ trợ query status theo client reference, tra cứu trước khi gửi lại.
- Lưu provider message ID và kết quả theo job.
- Nếu không có idempotency/status lookup, xác định chính sách trade-off giữa duplicate và lost notification.
- Với webhook callback, dedup callback bằng provider event ID.

Không tạo idempotency key mới cho mỗi lần retry. Key cần đại diện cho **một notification intent** và giữ nguyên suốt vòng đời retry.

Nếu provider không có cơ chế chống lặp, không thể khẳng định exactly-once delivery. Hãy công bố semantics thực tế và có reconciliation/support workflow cho trạng thái UNKNOWN.

## 17. Phân biệt event ID, notification ID và provider message ID

| Identifier | Định danh | Ví dụ |
| --- | --- | --- |
| `event_id` | Một sự kiện nghiệp vụ được tạo bởi producer | `OrderPlaced` |
| `notification_id` / `job_id` | Một ý định gửi thông báo cụ thể | Email xác nhận đơn |
| `provider_idempotency_key` | Một thao tác gửi logic tới provider | Key ổn định qua retry |
| `provider_message_id` | Message ID do provider trả về | ID tra cứu trạng thái |
| `provider_event_id` | Callback/delivery event do provider phát | Delivered/Bounced |
| `correlation_id` | Workflow liên quan | Checkout flow |

Một event có thể tạo nhiều notification jobs: email, push và SMS. Vì vậy không dùng event ID làm uniqueness key duy nhất nếu mỗi channel/recipient là một effect riêng. Ngược lại, không dùng provider message ID làm dedup key cho event đầu vào vì ID này chỉ xuất hiện sau khi provider đã nhận.

## 18. Idempotency key nên dựa trên semantics nghiệp vụ

Một số lựa chọn:
- Event ID nếu một event chỉ tạo một effect cho consumer.
- `(consumer_name, event_id)` nếu mỗi consumer xử lý độc lập.
- `(event_id, channel, recipient, template)` nếu một event tạo nhiều notification intents.
- Business command ID nếu client retry cùng một command.
- Provider idempotency key nếu gọi API bên ngoài.

Không dùng:
- Timestamp hiện tại.
- Random UUID tạo mới trong mỗi lần retry.
- Trace ID (sampling/replay có thể thay đổi).
- Payload hash nếu hai event khác nhau hợp lệ có cùng payload.
- Order ID đơn lẻ nếu một order hợp lệ có nhiều notification cùng loại ở các thời điểm khác nhau.

Idempotency scope phải trả lời: **hai request nào được coi là cùng một hành động logic?** Đây là quyết định nghiệp vụ, không chỉ là quyết định database.

## 19. Ordering: chống duplicate chưa giải quyết sai thứ tự

Giả sử một Order phát:
1. `OrderPlaced` version 1.
2. `OrderPaid` version 2.
3. `OrderCancelled` version 3.

Nếu relay hoặc broker giao `OrderCancelled` trước `OrderPaid`, consumer có thể gửi thông báo sai thứ tự hoặc hiển thị trạng thái cũ.

Các biện pháp:
- Ghi `aggregate_version`/sequence trong Outbox.
- Dùng aggregate ID làm partition key nếu cần ordering theo aggregate.
- Đảm bảo relay không publish event sau trước event trước cùng aggregate.
- Consumer lưu version đã xử lý và phát hiện gap/out-of-order.
- Có policy buffer/retry/defer event khi thiếu version.
- Thiết kế notification theo state hiện tại nếu semantics cho phép, nhưng không tự suy diễn event cũ thành trạng thái mới.

Ordering toàn hệ thống thường tốn kém và không cần thiết. Nhiều domain chỉ cần thứ tự trong một aggregate. Kafka bảo đảm ordering trong một partition, không tự bảo đảm thứ tự trên nhiều partition hoặc giữa các topic.

Nếu nhiều relay claim event cùng aggregate song song, thứ tự query `created_at` không đủ. Cần partition relay theo aggregate, lock aggregate stream, sequence gate hoặc một cơ chế tương đương.

## 20. Retry consumer và poison messages

Retry cần phân loại:
- **Transient:** broker/database timeout, network reset, provider throttling.
- **Permanent:** schema không hợp lệ, thiếu field bắt buộc, unsupported event version.
- **Business rejection:** event hợp lệ nhưng không thỏa policy; có thể ghi trạng thái từ chối thay vì retry.
- **Unknown:** chưa xác định, cần giới hạn retry và đưa vào điều tra.

Một policy có thể:
1. Retry ngắn trong process với giới hạn nhỏ.
2. Retry topic có delay/backoff.
3. Dead-letter queue sau số lần thử hoặc tuổi tối đa.
4. Ghi error code và event ID để điều tra.
5. Có replay tool với quyền/audit.
6. Giữ nguyên event ID khi replay cùng logical event.

Không retry vô hạn một poison message ở đầu partition nếu nó chặn mọi message sau. Nhưng chuyển DLQ cũng có thể làm mất thứ tự nghiệp vụ; cần quyết định theo aggregate và event semantics.

DLQ không phải thùng rác. Nó cần owner, retention, alert, dashboard, runbook và quy trình sửa/replay. Không xóa message chỉ để giảm lag.

## 21. Inbox retention và dedup horizon

Nếu xóa Inbox record quá sớm, broker có thể replay event cũ sau đó và consumer sẽ xử lý lại.

Retention cần ít nhất bao phủ:
- Broker topic retention và khả năng replay.
- Retry topic/DLQ retention.
- Thời gian outage tối đa được hỗ trợ.
- Thời gian backup/restore có thể đưa consumer về trạng thái cũ.
- Provider callback/reconciliation window.
- Business/legal audit requirements.

Không nhất thiết giữ mọi Inbox row vĩnh viễn. Có thể archive, partition hoặc compact theo policy, nhưng dedup horizon phải nhất quán với khả năng replay.

Với consumer có volume cao, cần tính storage growth:
- Events/day.
- Kích thước row/index.
- Số consumer group logic.
- Retention days.
- Backup và replication overhead.

Có thể giữ compact tombstone/dedup ledger hoặc trạng thái theo aggregate nếu semantics cho phép. Không xóa record chỉ dựa trên `processed_at` mà không xem event có thể được replay từ đâu.

## 22. Inbox state machine và xử lý crash

Một state machine đơn giản:

~~~text
ABSENT
  |
  | atomic insert
  v
RECEIVED
  |
  | business effect committed
  v
PROCESSED
  |
  +--> duplicate delivery: ignore
~~~

Nếu xử lý trong một transaction, `RECEIVED` và `PROCESSED` có thể không cần commit ở hai bước riêng. Có thể insert và update cùng transaction hoặc chỉ lưu record đã processed.

Nếu cần xử lý dài:
- Transaction đầu claim event và tạo durable job.
- Dispatcher xử lý job theo lease.
- Job có trạng thái PENDING/IN_PROGRESS/SUCCEEDED/RETRY/UNKNOWN.
- Lease có expiry để reclaim khi worker chết.
- Mỗi side effect cần idempotency key.
- Trạng thái không rõ cần reconciliation thay vì đánh dấu success giả.

Không để một Inbox row `RECEIVED` tồn tại mãi mà không có owner/recovery rule. Cần alert cho stuck processing và cơ chế xác định có thể retry an toàn hay không.

## 23. Khi consumer cần cập nhật database và phát event tiếp

Một consumer có thể nhận `OrderPlaced`, tạo notification job, đồng thời phát `NotificationScheduled`. Đây lại là dual write nếu update Inbox/job và publish event trực tiếp.

Giải pháp:
- Cùng transaction ghi Inbox + business state + Outbox mới.
- Relay phát event mới.
- Consumer downstream tiếp tục idempotent.

~~~text
Incoming event
   |
   v
BEGIN transaction
  INSERT inbox
  UPDATE notification state
  INSERT outbox (NotificationScheduled)
COMMIT
   |
   v
Relay publishes NotificationScheduled
~~~

Outbox có thể được dùng ở nhiều service. Mỗi service sở hữu Outbox của database mình; không tạo một bảng chung mà mọi service ghi trực tiếp.

## 24. Khi notification cần gọi provider: thêm outbound outbox/job

Nếu dispatcher gọi provider ngay sau khi đọc job, vẫn cần xử lý provider timeout và crash. Một mô hình:

~~~text
Kafka OrderPlaced
    |
    v
Notification consumer
    |
    | transaction
    +--> Inbox(event_id)
    +--> NotificationJob(PENDING)
    |
    v
Dispatcher claims job
    |
    +--> provider API with stable idempotency key
    |
    +--> update job result
    |
    v
Provider callback / reconciliation
~~~

Job cần các trạng thái có nghĩa:
- `PENDING`: chưa bắt đầu.
- `IN_PROGRESS`: worker đang xử lý, có lease.
- `SENT/ACCEPTED`: provider xác nhận đã nhận theo semantics API.
- `DELIVERED`: có delivery receipt nếu provider cung cấp.
- `FAILED_PERMANENT`: lỗi không retry được.
- `RETRY_WAIT`: lỗi tạm thời, chờ backoff.
- `UNKNOWN`: request có thể đã được provider nhận nhưng không có kết quả chắc chắn.

Phân biệt `ACCEPTED` và `DELIVERED`: provider chấp nhận request không đồng nghĩa email đã vào inbox hoặc SMS đã tới thiết bị. Dashboard cần dùng đúng semantics.

## 25. Java/Spring: dispatcher có lease

Pseudocode:

~~~java
@Component
public class NotificationDispatcher {
    private final NotificationJobRepository jobs;
    private final NotificationProvider provider;

    public void dispatchBatch() {
        List<ClaimedNotification> batch = jobs.claimBatch(
            "notification-worker-1",
            50,
            Instant.now()
        );

        for (ClaimedNotification job : batch) {
            dispatchOne(job);
        }
    }

    private void dispatchOne(ClaimedNotification job) {
        try {
            ProviderResult result = provider.send(
                job.payload(),
                job.providerIdempotencyKey()
            );
            jobs.markAccepted(
                job.jobId(),
                job.leaseToken(),
                result.messageId()
            );
        } catch (TransientProviderException ex) {
            jobs.scheduleRetry(
                job.jobId(),
                job.leaseToken(),
                backoff(job.attempts()),
                classify(ex)
            );
        } catch (UnknownProviderOutcomeException ex) {
            jobs.markUnknown(
                job.jobId(),
                job.leaseToken(),
                classify(ex)
            );
        }
    }
}
~~~

Đây là skeleton minh họa, không phải code production hoàn chỉnh. Các thao tác `claimBatch`, `markAccepted`, `scheduleRetry` cần conditional update theo lease token/version để worker hết lease không ghi đè trạng thái của worker mới.

Không giữ một database transaction mở trong khi chờ network provider nếu có thể tránh. Claim job trong transaction ngắn, gọi provider ngoài transaction, rồi cập nhật kết quả bằng transaction mới. Idempotency key ở provider bảo vệ trường hợp worker chết sau provider acceptance nhưng trước khi lưu kết quả.

## 26. Kafka consumer acknowledgment và Spring configuration

Với Spring Kafka, cần hiểu:
- Ack mode (`RECORD`, `BATCH`, manual modes).
- Offset commit timing.
- Listener exception handling.
- Retry topics hoặc error handler.
- Concurrency và partition assignment.
- Rebalance behavior.
- Transaction manager được sử dụng.
- Dead-letter publishing.
- Consumer group ID và offset reset policy.

Một cấu hình khái niệm:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: notification-service
      auto-offset-reset: earliest
    listener:
      ack-mode: record
~~~

Property names và semantics phụ thuộc Spring Kafka/Spring Boot version. Với container-managed offset commit, `enable-auto-commit=false` thường là cấu hình phù hợp để listener container kiểm soát ack. Không copy cấu hình mà chưa kiểm tra phiên bản và error handler.

Listener:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "notification-service"
)
public void onOrderPlaced(OrderPlaced event) {
    consumer.handle(event);
}
~~~

`consumer.handle` nên thực hiện Inbox + Notification Job trong một transaction. Cần kiểm tra transaction propagation giữa listener container và service; `@Transactional` trên method không tự quyết định thời điểm broker offset commit nếu listener container được cấu hình khác.

Một integration test phải chứng minh:
1. DB transaction rollback thì offset chưa được commit theo policy.
2. DB commit rồi process chết trước ack thì redelivery không tạo job thứ hai.
3. Duplicate event ID được bỏ qua.
4. Event ID khác nhau với cùng order có thể tạo effect hợp lệ nếu nghiệp vụ yêu cầu.

## 27. Event identity và schema evolution

Dedup dựa trên event ID chỉ đáng tin khi producer bảo đảm identity ổn định.

Quy tắc:
- Sinh event ID khi business transaction tạo Outbox row.
- Lưu ID vào Outbox và payload/header.
- Mọi lần relay retry dùng cùng ID.
- CDC restart/replay không thay ID.
- DLQ/replay cùng logical event giữ ID gốc.
- Nếu tạo một event mới do nghiệp vụ phát sinh lại, tạo ID mới và có causation/reference tới event trước.
- Không dùng offset đơn lẻ làm event identity toàn cục.
- Không dùng payload hash thay ID nếu hai event hợp lệ có payload giống nhau.

Schema evolution:
- Consumer phải xử lý field optional/unknown theo contract.
- Producer không đổi semantics mà giữ schema version cũ.
- Consumer lưu event ID và schema version để debug.
- Replay cũ phải tương thích hoặc có upcaster/translator.
- Không thay đổi event ID khi upcast payload.

## 28. Ordering và partitioning cho Outbox relay

Nếu business requirement cần order events theo aggregate:
- Ghi `aggregate_version` trong transaction.
- Broker message key là aggregate ID.
- Relay publish theo version tăng dần cho mỗi aggregate.
- Chỉ đánh dấu/advance cursor sau khi publish được xác nhận theo policy.
- Consumer phát hiện version gap và defer hoặc reconcile.

Một query lấy 100 event theo `created_at` có thể lấy event version 5 của Order A trước version 4 nếu hai relay chạy song song hoặc timestamp không phản ánh commit order. Dùng sequence do aggregate/database cấp trong cùng transaction, không chỉ dựa vào wall clock.

Có thể partition Outbox theo hash aggregate ID hoặc chia relay workers theo shard. Phải tránh hai worker cùng publish cùng aggregate song song nếu ordering là yêu cầu cứng.

Nếu không có yêu cầu thứ tự, không thêm cơ chế global serialization đắt đỏ. Hãy ghi rõ event nào có thể xử lý độc lập.

## 29. Exactly-once: cần nói rõ phạm vi

“Exactly once” có thể được dùng cho nhiều nghĩa:
- Producer không ghi duplicate vào broker.
- Broker chỉ deliver một lần.
- Consumer chỉ commit effect một lần.
- Provider chỉ gửi một email một lần.
- Người nhận chỉ nhìn thấy một thông báo một lần.

Đây là các ranh giới khác nhau. Broker transaction hoặc idempotent producer có thể cung cấp guarantees trong phạm vi Kafka transaction/producer semantics, nhưng không tự mở rộng sang database và email provider.

Một mục tiêu thực tế:
- Business state + Outbox intent: atomic trong database transaction.
- Broker publication: at-least-once với stable event ID.
- Consumer DB effect: effectively-once nhờ Inbox unique key và transaction.
- Provider call: at-least-once attempt với provider idempotency key nếu hỗ trợ.
- Final delivery: theo guarantee và receipt của provider, có reconciliation.

Hãy ghi rõ guarantee theo từng boundary. Tránh tuyên bố “email exactly once” nếu provider không cung cấp idempotency hoặc query semantics đủ mạnh.

## 30. Transactional Outbox và saga

Outbox thường là một thành phần của saga hoặc event-driven workflow:
- Order Service ghi Order + `OrderPlaced`.
- Inventory Service reserve stock và ghi Inbox + state + `InventoryReserved`.
- Payment Service authorize và ghi Inbox + state + `PaymentAuthorized`.
- Order Service cập nhật trạng thái dựa trên event tiếp theo.

Mỗi service dùng Outbox để phát event sau commit và Inbox để xử lý duplicate. Saga vẫn cần:
- Idempotent commands.
- Compensation khi một bước thất bại.
- Timeout và deadline.
- Correlation/causation.
- State machine rõ.
- Reconciliation cho outcome không xác định.

Outbox không tự giải quyết business compensation. Nó chỉ giúp không mất publication intent và hỗ trợ delivery bền vững.

## 31. Notification dedup theo nghiệp vụ

Một order có thể tạo nhiều thông báo hợp lệ:
- Email xác nhận đơn.
- Push khi thanh toán thành công.
- SMS khi đơn được giao.
- Email hóa đơn.
- Thông báo hủy/hoàn tiền.

Nếu chỉ dùng `order_id` làm unique key, có thể chặn nhầm các thông báo hợp lệ. Nếu chỉ dùng `event_id`, retry của một event có thể tạo duplicate khi producer tạo event mới do retry command không idempotent.

Xác định uniqueness key theo notification intent:
- Event ID.
- Notification type/template.
- Channel.
- Recipient reference.
- Locale hoặc version nếu cần.
- Business sequence/version nếu cùng loại notification có thể phát nhiều lần hợp lệ.

Ví dụ:

~~~sql
CREATE UNIQUE INDEX uq_notification_intent
ON notification_jobs (
    source_event_id,
    channel,
    template_key,
    recipient_ref
);
~~~

Chỉ thêm cột vào unique key khi nó thật sự phân biệt hai intent hợp lệ. Không dùng email address thô làm key nếu privacy policy yêu cầu tokenized reference; có thể dùng recipient ID ổn định hoặc hash có key theo policy.

## 32. Xử lý event trùng do producer command retry

Outbox bảo đảm event được lưu nếu business transaction commit. Nhưng client có thể gửi cùng command nhiều lần do HTTP timeout:

1. Client gửi PlaceOrder.
2. Server commit Order và Outbox.
3. Response bị mất.
4. Client retry PlaceOrder.
5. Server tạo Order thứ hai và Outbox thứ hai nếu command không idempotent.

Do đó, producer cũng cần idempotency cho command:
- Client gửi `Idempotency-Key` hoặc command ID.
- Server lưu command receipt/response trong transaction.
- Unique constraint theo caller scope + key.
- Cùng key và cùng request semantics trả lại kết quả cũ.
- Cùng key nhưng payload khác phải bị từ chối hoặc xử lý theo policy.
- Order + Outbox chỉ được tạo một lần cho logical command.

Outbox xử lý dual write sau khi nghiệp vụ đã quyết định tạo event; nó không ngăn business command duplicate ở đầu vào.

## 33. Observability: đo tuổi Outbox, duplicate và delivery lag

Các metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| `outbox_pending_count` | Số event chưa publish |
| `outbox_oldest_pending_age_seconds` | Tuổi event chưa publish lâu nhất |
| `outbox_publish_attempts_total` | Số lần relay thử publish |
| `outbox_publish_failures_total` | Lỗi publish theo loại |
| `outbox_publish_latency_seconds` | Thời gian từ claim đến acknowledgement |
| `inbox_duplicates_total` | Số event bị dedup |
| `inbox_processing_failures_total` | Lỗi xử lý consumer |
| `notification_jobs_pending` | Job chưa dispatch |
| `notification_job_age_seconds` | Tuổi job chờ gửi |
| `provider_timeout_total` | Timeout khi gọi provider |
| `provider_unknown_outcome_total` | Kết quả provider chưa rõ |
| `notification_accepted_total` | Provider chấp nhận request |
| `notification_delivered_total` | Delivery receipt nếu có |
| `notification_bounced_total` | Bounce/failure receipt |

Metric labels nên có dimension hữu hạn như service, event type đã kiểm soát, channel, outcome và provider. Không dùng event ID, order ID, recipient ID hoặc message ID làm metric label.

Log/traces có thể chứa event ID/job ID ở mức access-controlled để điều tra. Dashboard cần phân biệt:
- Broker publish thành công.
- Consumer xử lý event thành công.
- Notification job được tạo.
- Provider chấp nhận.
- Provider báo delivered.

Một metric tên `notification_sent_total` mơ hồ nếu không định nghĩa "sent" là request đã gửi, provider accepted hay delivered.

## 34. Alert và runbook

Alert nên tập trung vào hành động cần thực hiện:
- Outbox oldest pending age vượt business threshold.
- Outbox backlog tăng liên tục.
- Relay publish failures tăng.
- CDC connector lag hoặc replication slot WAL growth cao.
- Consumer lag/oldest message age vượt ngưỡng.
- Inbox processing stuck.
- Notification job UNKNOWN tăng.
- Provider throttling hoặc timeout tăng.
- DLQ có message mới.
- Dedup rate tăng bất thường (có thể chỉ ra ack/offset/relay issue).

Runbook cần:
1. Xác định service, topic, event type và thời điểm bắt đầu.
2. Kiểm tra DB availability, Outbox backlog và tuổi event.
3. Kiểm tra broker topic/ACL/partition health.
4. Kiểm tra relay worker/lease hoặc CDC connector/offset.
5. Xác định lỗi tạm thời hay permanent.
6. Kiểm tra consumer lag và Inbox transaction errors.
7. Kiểm tra provider status và UNKNOWN jobs.
8. Không xóa Outbox/Inbox records để làm dashboard xanh.
9. Replay bằng event ID gốc và có audit.
10. Đối soát business effect và provider receipts sau recovery.

## 35. Kiểm thử Outbox: kiểm tra failure windows

Một bộ test có giá trị nên mô phỏng các điểm chết:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Order insert lỗi | Không có Outbox event |
| Outbox insert lỗi | Order transaction rollback |
| Transaction rollback | Không có business state và event |
| Commit thành công, relay chưa chạy | Outbox vẫn tồn tại |
| Broker unavailable | Event vẫn pending, retry sau |
| Broker nhận event, relay chết trước mark | Event có thể publish lại, consumer dedup |
| Relay mark sau ack | Không mất event do mark sớm |
| Hai relay cùng chạy | Không mất event; duplicate được kiểm soát |
| Consumer DB rollback | Inbox/effect rollback cùng nhau |
| Consumer commit, ack bị mất | Redelivery không tạo effect thứ hai |
| Hai consumer thread cùng event | Unique key chỉ cho một lần xử lý |
| Provider accepted, response timeout | Retry cùng idempotency key hoặc chuyển UNKNOWN |
| DLQ replay | Event identity được giữ, duplicate an toàn |

Không chỉ mock mọi dependency. Dùng integration test với database engine thực tế hoặc Testcontainers để kiểm tra unique constraints, transaction isolation, row locks và `ON CONFLICT` semantics.

## 36. Kiểm thử consumer idempotency

Một test có thể:
1. Tạo event `E1`.
2. Gọi consumer lần đầu.
3. Assert có một Inbox row và một Notification Job.
4. Gọi consumer lần hai cùng `E1`.
5. Assert vẫn chỉ có một job.
6. Gọi với event `E2` khác nhưng cùng order.
7. Assert kết quả theo business uniqueness policy.
8. Chạy hai invocation song song với cùng `E1`.
9. Assert unique constraint ngăn duplicate.
10. Buộc rollback sau Inbox insert và trước job insert.
11. Retry event và assert job được tạo đúng một lần.

Điều quan trọng là kiểm tra database state sau commit/rollback, không chỉ kiểm tra method được gọi bao nhiêu lần trong Mockito. Test song song cần dùng barrier/latch để tạo race có chủ đích.

## 37. Kiểm thử provider timeout và callback

Provider adapter cần test:
- Request đầu được provider chấp nhận nhưng client timeout.
- Retry cùng idempotency key trả lại cùng provider result hoặc trạng thái đã có.
- Provider từ chối key reuse với payload khác.
- Provider callback đến hai lần.
- Callback đến trước khi worker lưu provider message ID.
- Callback đến trễ sau khi job đã retry.
- Provider báo delivered rồi webhook replay.
- Provider báo bounce/failed sau trạng thái accepted.
- Query status trả UNKNOWN hoặc không hỗ trợ.

Webhook callback cần signature verification, timestamp/replay protection và Inbox riêng theo provider event ID. Không tin callback chỉ vì URL endpoint được gọi.

## 38. Reconciliation cho trạng thái không xác định

Khi provider outcome UNKNOWN:
- Không tự đánh dấu FAILED nếu provider có thể đã gửi.
- Không tạo notification mới với idempotency key khác.
- Query provider status theo client reference nếu hỗ trợ.
- Đợi callback trong một khoảng thời gian định nghĩa.
- So khớp provider logs/receipt với internal job.
- Escalate hoặc xử lý thủ công khi vượt SLA.
- Ghi audit cho quyết định resend/close.

Reconciliation job có thể:
1. Tìm job UNKNOWN quá thời hạn.
2. Query provider status.
3. Nếu accepted/delivered, cập nhật trạng thái.
4. Nếu provider xác nhận không tồn tại, schedule retry với key phù hợp.
5. Nếu vẫn không rõ, giữ UNKNOWN và tạo work item.

Không gửi lại một thông báo nhạy cảm hoặc có chi phí cao chỉ vì không thấy response. Cần cân nhắc hậu quả duplicate so với missed notification.

## 39. Partitioning và cleanup Outbox

Outbox có thể tăng liên tục. Cần:
- Xóa/archival event đã publish sau retention.
- Giữ event chưa publish và event đang retry.
- Partition theo thời gian nếu volume lớn.
- Index chỉ cho pending rows nếu database hỗ trợ.
- Batch delete để tránh transaction quá lớn.
- VACUUM/maintenance theo database.
- Không xóa khi relay còn lease hoặc CDC cần log/schema metadata.
- Có audit/retention cho event phục vụ compliance.

Với CDC, xóa Outbox row không nhất thiết xóa ngay WAL/binlog đã được connector đọc; replication slot lag có thể giữ transaction log và làm disk tăng. Theo dõi cả table growth và log retention.

Inbox cleanup phải dài ít nhất dedup/replay horizon. Nếu consumer có thể replay topic 30 ngày, không xóa Inbox sau 7 ngày trừ khi có một cơ chế dedup khác bảo đảm.

## 40. Backpressure và throughput

Khi producer phát event nhanh hơn relay/consumer xử lý:
- Outbox backlog tăng.
- Database storage tăng.
- Consumer lag tăng.
- Notification jobs chờ lâu.
- Provider quota bị vượt.

Cần:
- Batch size có giới hạn.
- Worker concurrency theo broker/DB/provider capacity.
- Rate limit theo provider/channel.
- Queue depth và oldest age alert.
- Backpressure ở consumer.
- Retry với jitter.
- Circuit breaker cho provider.
- Admission control khi backlog quá lớn.
- Capacity forecast và load test.

Tăng concurrency không phải lúc nào cũng giải quyết backlog; có thể làm DB lock contention hoặc provider throttling tăng. Đo bottleneck trước khi scale.

## 41. Multi-tenant và fairness

Nếu một tenant phát lượng lớn event, tenant khác không nên bị starvation:
- Partition/queue strategy theo tenant hoặc workload class.
- Per-tenant rate limits có bounded cardinality.
- Quotas cho notification types.
- Fair scheduling ở dispatcher.
- Provider limits và priority policy.
- Monitoring backlog theo tenant tier ở nơi phù hợp.
- Không đưa raw tenant ID làm metric label nếu cardinality lớn.

Tenant isolation phải áp dụng cho cả Outbox, Inbox, notification payload và provider credentials. Không cho consumer dùng một id từ event để truy cập dữ liệu tenant khác mà chưa xác thực ownership.

## 42. Security và privacy

Outbox/Inbox thường chứa dữ liệu được lưu bền vững và có thể replay. Cần:
- Chỉ lưu payload tối thiểu cần cho consumer.
- Mã hóa dữ liệu nhạy cảm khi lưu và truyền.
- Không lưu access token, password hoặc full payment credentials.
- Redact payload trong logs.
- Giới hạn quyền đọc Outbox/Inbox theo service.
- Audit thao tác replay, purge và manual resend.
- Xác thực chữ ký provider webhook.
- Bảo vệ notification recipient và template content.
- Áp dụng retention/deletion policy.
- Không đưa PII vào metric labels hoặc baggage.

Nếu payload cần dữ liệu có thể thay đổi như địa chỉ email hiện tại, quyết định dùng snapshot tại thời điểm event hay lookup profile khi gửi phải là business rule rõ. Snapshot giúp tái hiện intent; lookup mới có thể phản ánh dữ liệu hiện tại nhưng làm notification thay đổi theo thời gian và thêm runtime dependency.

## 43. Outbox event payload: snapshot hay reference?

Hai lựa chọn:

**Snapshot event:** chứa các giá trị nghiệp vụ cần tại thời điểm xảy ra, ví dụ order number, locale và display total. Ưu điểm là replay tái tạo đúng nội dung theo thời điểm; nhược điểm là payload lớn hơn và có thể chứa PII.

**Reference event:** chứa order ID và consumer gọi Order API để lấy dữ liệu. Ưu điểm payload nhỏ; nhược điểm là consumer phụ thuộc availability của producer và dữ liệu hiện tại có thể đã thay đổi.

Có thể kết hợp: snapshot một số field bất biến/được chốt và reference cho dữ liệu không cần lưu. Quyết định phải tính privacy, retention, replay, consistency và provider latency.

Không phát một event chỉ chứa ID rồi giả định API luôn sẵn sàng khi consumer replay sau nhiều ngày. Cũng không snapshot toàn bộ entity graph nếu consumer chỉ cần ba field.

## 44. Khi nào dùng transactional messaging hoặc broker transactions?

Một số broker hỗ trợ producer transactions, idempotent producer hoặc consume-transform-produce transaction trong phạm vi broker. Chúng có thể giải quyết một số failure windows giữa input offset và output record khi tất cả liên quan nằm trong broker semantics.

Nhưng business database thường vẫn là một resource khác. Nếu consumer cập nhật PostgreSQL và commit Kafka offset, vẫn cần phối hợp hoặc idempotency. Broker transaction không tự làm một email provider tham gia transaction.

Có thể dùng:
- Outbox + broker producer.
- CDC + Kafka.
- Broker transaction cho consume-transform-produce thuần broker.
- Inbox/unique constraints cho DB effects.
- Provider idempotency cho external effects.

Chọn theo transaction boundary thật và đọc guarantee cụ thể của broker/client version. Không suy rộng một tính năng exactly-once của broker thành exactly-once toàn hệ thống.

## 45. Ví dụ end-to-end: gửi email xác nhận Order

**Bước 1 – Place order**
- Client gửi command với idempotency key.
- Order Service ghi command receipt, Order và Outbox `OrderPlaced` trong một transaction.
- Response trả về order ID.

**Bước 2 – Publish**
- Relay/CDC phát event với stable `event_id`.
- Nếu publish retry, event ID giữ nguyên.
- Outbox chỉ được coi đã publish theo acknowledgement/CDC checkpoint semantics.

**Bước 3 – Consume**
- Notification Service nhận event.
- Trong một transaction, insert Inbox unique `(consumer, event_id)`.
- Nếu mới, tạo Notification Job với unique intent key.
- Commit DB, sau đó ack offset.

**Bước 4 – Dispatch**
- Worker claim job bằng lease.
- Gọi email provider với idempotency key ổn định của job.
- Lưu provider message ID và trạng thái accepted.
- Nếu timeout không rõ, đánh UNKNOWN và reconcile.

**Bước 5 – Delivery**
- Provider callback được xác thực.
- Inbox callback dedup theo provider event ID.
- Cập nhật DELIVERED/BOUNCED theo semantics provider.
- Dashboard tách accepted và delivered.

~~~text
HTTP command
   |
   v
Order DB transaction
  +-- command receipt
  +-- orders
  +-- outbox_events
   |
   v
Relay / CDC
   |
   v
Kafka: OrderPlaced(event_id=E1)
   |
   v
Notification DB transaction
  +-- inbox(E1)
  +-- notification_job(J1)
   |
   v
Dispatcher -- idempotency_key=J1 --> Email Provider
   |
   +--> accepted / unknown / retry
   |
   v
Provider callback --> callback inbox --> delivery state
~~~

## 46. Các quyết định thiết kế cần ghi trong ADR

Một ADR cho notification pipeline nên trả lời:

- Database nào là nguồn sự thật của Outbox?
- Outbox được relay bằng polling hay CDC?
- Event ID được tạo ở đâu và giữ ổn định thế nào?
- Ordering cần theo aggregate nào?
- Broker acknowledgement nào được coi là publish success?
- Relay retry/backoff/lease ra sao?
- Consumer Inbox uniqueness scope là gì?
- Inbox và business effect có cùng transaction không?
- Offset/ack commit timing thế nào?
- Notification intent uniqueness key gồm những gì?
- Provider có idempotency/status lookup không?
- Outcome UNKNOWN được xử lý thế nào?
- DLQ/replay và retention ra sao?
- Ai sở hữu runbook, dashboards, alert và reconciliation?
- Security/privacy/retention policy nào áp dụng?

Ghi cả assumptions và giới hạn. Nếu provider không hỗ trợ idempotency, ADR phải nói rõ duplicate risk còn lại.

## 47. Checklist triển khai Outbox

- [ ] Business state và Outbox row được ghi trong cùng DB transaction.
- [ ] Outbox nằm cùng datasource/transaction manager với business data.
- [ ] Event ID ổn định qua retry và replay.
- [ ] Event contract có type/version/owner.
- [ ] Payload tối thiểu, không chứa secret/PII dư thừa.
- [ ] Relay có claim/lease hoặc CDC offset management rõ.
- [ ] Publish acknowledgement được xử lý đúng.
- [ ] Chỉ mark published sau khi xác nhận publish theo policy.
- [ ] Retry có backoff/jitter và phân loại lỗi.
- [ ] Nhiều relay không gây mất event hoặc race không kiểm soát.
- [ ] Ordering theo aggregate được xác định nếu nghiệp vụ cần.
- [ ] Outbox backlog/oldest age có dashboard và alert.
- [ ] Retention/partition/cleanup có policy.
- [ ] CDC replication slot/WAL retention được giám sát nếu dùng CDC.
- [ ] Failure windows được integration test.

## 48. Checklist consumer idempotency và notification

- [ ] Inbox có unique constraint theo consumer và event ID.
- [ ] Insert dedup là thao tác atomic ở database.
- [ ] Inbox record và business effect cùng transaction khi có thể.
- [ ] Broker ack/offset commit diễn ra sau DB commit theo policy.
- [ ] Duplicate event không tạo thêm notification job.
- [ ] Unique intent key phản ánh channel/template/recipient semantics.
- [ ] Notification job có state machine và lease.
- [ ] Provider retry dùng cùng idempotency key.
- [ ] Provider timeout không rõ chuyển UNKNOWN/reconciliation.
- [ ] Webhook callback có signature verification và dedup.
- [ ] Retry/DLQ có owner, retention và replay process.
- [ ] Inbox retention bao phủ replay horizon.
- [ ] Event ordering/version gap được xử lý nếu cần.
- [ ] Business effect và provider delivery được phân biệt.
- [ ] Test concurrent duplicate và crash windows.

## 49. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Commit DB rồi publish trực tiếp | Event có thể mất khi process chết | Transactional Outbox |
| Publish rồi mới commit DB | Consumer thấy event của transaction rollback | Ghi Outbox cùng business state |
| Mark Outbox published trước broker ack | Mất event | Publish, nhận ack rồi mark |
| Tạo event ID mới mỗi lần retry | Dedup không nhận ra duplicate | Stable event ID |
| Consumer SELECT rồi INSERT | Race condition giữa replicas | Unique constraint + atomic insert |
| Ack trước DB commit | Message mất khi DB rollback | DB commit rồi ack |
| DB commit rồi ack bị mất | Redelivery | Inbox idempotency |
| Chỉ dùng in-memory set | Restart/scale làm mất dedup | Durable Inbox |
| Gọi provider trong Kafka listener lâu | Consumer thread/partition bị giữ | Persist job, dispatcher riêng |
| Retry provider với key mới | Có thể gửi trùng | Stable provider idempotency key |
| Timeout coi là thất bại chắc chắn | Gửi lại khi provider đã nhận | UNKNOWN + status lookup/reconcile |
| Dùng order ID làm mọi dedup key | Chặn nhầm notification hợp lệ | Intent key theo business semantics |
| Xóa Inbox quá sớm | Replay tạo effect lại | Retention theo replay horizon |
| DLQ không có owner | Event bị bỏ quên | Alert, runbook, replay governance |
| Reset offset về latest | Bỏ qua notification | Replay có kiểm soát và đối soát |
| Dùng timestamp làm ordering | Clock/parallel relay gây đảo thứ tự | Aggregate sequence/version |
| Tuyên bố exactly-once toàn hệ thống | Guarantee vượt phạm vi thực tế | Ghi rõ semantics từng boundary |
| Log toàn bộ payload | Lộ PII và tăng chi phí | Structured logs, redaction |
| Retry vô hạn | Poison message chặn pipeline | Backoff, DLQ và repair workflow |

## 50. Câu hỏi thường gặp

**Outbox có bảo đảm event chỉ được gửi đúng một lần không?**

Không. Outbox bảo đảm business state và publication intent cùng commit. Relay có thể publish lại nếu không biết broker đã nhận hay chưa. Consumer cần idempotency để duplicate không tạo thêm business effect.

**Tại sao không dùng `@Transactional` rồi gửi Kafka trong cùng method?**

Transaction JPA thường chỉ bao phủ database. Broker publish là một resource khác; nếu không có distributed transaction được cấu hình và hỗ trợ đúng, hai thao tác vẫn có failure window. Outbox lưu ý định phát event trong database transaction.

**Inbox có cần unique constraint không?**

Có. Kiểm tra tồn tại rồi insert có race giữa nhiều consumer threads/replicas. Unique key ở database là cơ chế atomic chống xử lý đồng thời cùng event.

**Có thể đánh dấu Inbox trước rồi xử lý business effect sau không?**

Chỉ khi có state machine, lease và recovery workflow rõ. Nếu Inbox commit nhưng effect chưa xảy ra, redelivery có thể bị bỏ qua vĩnh viễn. Khi có thể, ghi Inbox và effect trong cùng transaction.

**Nếu consumer gửi email trực tiếp thì Inbox có đủ không?**

Không đủ để bảo đảm provider không gửi trùng khi response timeout. Inbox ngăn tạo effect nội bộ hai lần; provider idempotency key hoặc status lookup cần thiết để giảm duplicate bên ngoài.

**Polling relay hay CDC tốt hơn?**

Polling thường đơn giản hơn và đủ cho tải thấp/vừa. CDC có thể hiệu quả với throughput/latency lớn nhưng thêm vận hành connector, offsets và transaction log retention. Chọn theo năng lực và workload.

**Có nên giữ Outbox row mãi mãi?**

Không nhất thiết. Có thể archive/cleanup event đã publish sau retention phù hợp. Event chưa publish hoặc đang retry phải được bảo vệ; Inbox retention phải bao phủ khả năng replay.

**Một event tạo nhiều thông báo thì dedup thế nào?**

Dùng notification intent key gồm các chiều phân biệt effect hợp lệ, ví dụ event ID, channel, template và recipient reference. Không dùng một key quá rộng khiến email và push hợp lệ bị coi là duplicate.

**Kafka exactly-once có thay Inbox không?**

Không trong mọi kiến trúc. Kafka transaction có thể phối hợp offset và output record trong phạm vi broker, nhưng không tự atomically commit PostgreSQL và provider API. Inbox vẫn hữu ích cho database effects và replay.

**Nếu provider không hỗ trợ idempotency thì sao?**

Không thể bảo đảm exactly-once delivery qua timeout. Dùng client reference/status lookup nếu có, callback reconciliation, trạng thái UNKNOWN và chính sách quyết định resend dựa trên rủi ro duplicate/lost notification.

**Có nên retry message vô hạn cho tới khi gửi được không?**

Không. Phân loại lỗi, dùng backoff/jitter, giới hạn attempts/age, DLQ hoặc parking workflow cho lỗi permanent và có owner điều tra. Retry vô hạn có thể tạo poison loop.

**Làm sao biết notification đã gửi thành công?**

Phân biệt dispatcher đã gửi request, provider đã accepted, provider báo delivered và thiết bị/người dùng thực sự nhìn thấy. Chỉ tuyên bố mức mà provider receipt và hệ thống có thể chứng minh.

**Có cần Outbox cho mọi event trong mọi service không?**

Nếu event cần bảo đảm không mất so với transaction nghiệp vụ, Outbox hoặc cơ chế tương đương là lựa chọn phù hợp. Với telemetry/best-effort events, có thể không cần. Quyết định dựa trên business impact và delivery guarantee.

---

**Nguyên lý ghi nhớ:** *Ghi business state và Outbox intent trong cùng transaction; relay phát at-least-once với event ID ổn định; consumer ghi Inbox và business effect nguyên tử để duplicate không lặp tác động; provider call dùng idempotency key và reconciliation cho outcome không rõ. Thiết kế theo failure windows thực tế, vì “exactly once” chỉ có ý nghĩa khi nói rõ ranh giới nào được bảo đảm.*