# Deduplication store

Trong một hệ thống Spring Kafka, **deduplication store** là nơi lưu dấu vết bền vững cho biết một message hoặc business event đã được xử lý theo một phạm vi xác định. Khi cùng một event xuất hiện lại do consumer redelivery, producer retry, retry topic, DLT replay hoặc client gửi lại command, consumer có thể tra cứu store để quyết định có cần thực hiện side effect lần nữa hay không.

Deduplication store thường được triển khai bằng một bảng relational database như **processed_events/inbox**, một kho key-value như Redis, hoặc một storage chuyên dụng. Lựa chọn quan trọng nhất không phải tốc độ lookup đơn thuần mà là **ranh giới atomicity**: việc ghi dấu event đã xử lý phải được phối hợp đúng với business side effect. Nếu lưu dấu thành công rồi side effect thất bại, message replay có thể bị bỏ qua vĩnh viễn. Nếu side effect thành công nhưng dấu dedup chưa được lưu, lần redelivery có thể lặp side effect.

Bài học thuộc chương **Tính đúng và idempotency** trong module **Spring Kafka Reliability Operations**. Nội dung giải thích identity và key scope, inbox/processed-message store, atomic transaction, concurrency và unique constraints, TTL/retention, Redis so với relational database, retry/replay/DLT, partitioning, observability, migration, failure modes và runbooks.

## 1. Deduplication store giải quyết vấn đề gì?

Kafka consumer thường xử lý theo committed offsets. Nếu listener hoàn tất business operation nhưng process chết trước khi offset được commit, record có thể được giao lại. Kafka không tự biết một database transaction hoặc HTTP side effect ngoài Kafka đã hoàn thành.

Ví dụ:

~~~text
Kafka record: eventId=evt-42, offset=100
       |
       v
Consumer nhận record
       |
       v
Database trừ tồn kho thành công
       |
       v
Process crash trước khi Kafka offset commit
       |
       v
Consumer khởi động lại và nhận offset 100
       |
       v
Nếu không dedup: tồn kho có thể bị trừ lần thứ hai
~~~

Deduplication store giúp nhận diện event đã được áp dụng và ngăn lặp business effect:

~~~text
Consumer nhận event evt-42
       |
       v
Kiểm tra processed_events
       |
       +-- Chưa có -> xử lý và ghi dấu atomically
       |
       +-- Đã có -> bỏ qua side effect lặp
~~~

Mục tiêu là **at-least-once delivery với business effect idempotent**. Store không khiến Kafka delivery trở thành exactly-once toàn hệ thống; nó giúp ứng dụng kiểm soát duplicate trong phạm vi business operation được bảo vệ.

## 2. Phân biệt deduplication với các khái niệm liên quan

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Deduplication | Nhận diện cùng event/command đã được xử lý | eventId đã tồn tại trong inbox |
| Idempotency | Lặp cùng operation không tạo thêm effect | Reserve stock hai lần vẫn chỉ reserve một lần |
| Inbox pattern | Persist message identity và processing state ở consumer | processed_events table |
| Outbox pattern | Persist event cần publish cùng business transaction | outbox_events table |
| Kafka idempotent producer | Chống duplicate do producer protocol retries trong phạm vi session/protocol | enable.idempotence |
| Kafka transactions | Atomic commit Kafka outputs và consumed offsets trong Kafka transaction | consume-transform-produce |
| Cache | Lưu dữ liệu để đọc nhanh | Product lookup cache |

Deduplication store thường là một phần của inbox/idempotency design. Cache có thể hỗ trợ lookup nhưng không nên tự động được xem là nguồn sự thật bền vững nếu eviction, failover hoặc restart có thể xóa key trước khi hết thời gian duplicate.

Kafka producer idempotence cũng không thay thế deduplication store ở consumer. Hai cơ chế bảo vệ các failure boundaries khác nhau.

## 3. Chọn identity nào để deduplicate?

Đây là quyết định nền tảng. Một Kafka record có các thuộc tính:

- cluster;
- topic;
- partition;
- offset;
- key;
- headers;
- payload.

Một business event có thể có:

- eventId;
- eventType;
- aggregateId;
- tenantId;
- occurredAt;
- schemaVersion.

Một command có thể có:

- commandId;
- idempotencyKey;
- clientId;
- tenantId.

**Kafka topic-partition-offset** nhận diện một record cụ thể trong một Kafka log. Nó phù hợp để xác định cùng record bị redeliver. Nhưng khi event được publish lại vào topic khác hoặc được replay, offset mới sẽ xuất hiện.

**Business event ID** thường phù hợp hơn để deduplicate cùng event xuyên producer retries, retry topics, DLT và replay. Điều này chỉ đúng khi producer đảm bảo eventId ổn định và duy nhất trong scope đã định nghĩa.

Không dùng payload hash làm identity mặc định. Hai business events độc lập có thể có payload giống hệt nhau, ví dụ hai đơn hàng cùng mặt hàng và số lượng. Ngược lại, cùng event có thể được serialize khác nhau sau schema evolution.

## 4. Xác định scope của deduplication key

Event ID có thể duy nhất toàn hệ thống, duy nhất theo tenant, hoặc chỉ duy nhất trong một producer. Deduplication key phải phản ánh contract thực tế.

Ví dụ:

~~~text
eventId = evt-42
consumer = inventory-service
tenant = tenant-a
~~~

Các lựa chọn key:

~~~text
event_id
(consumer_name, event_id)
(tenant_id, event_id, consumer_name)
(event_source, event_id, processing_contract)
~~~

Một bảng dùng riêng event_id có thể gây collision nếu hai tenants hoặc producers tạo ID trong namespace riêng. Một bảng dùng event_id toàn cục chỉ an toàn khi hệ thống có contract global uniqueness thực sự.

Consumer name/processing contract cũng quan trọng. Cùng một event có thể cần được xử lý một lần bởi inventory-service và một lần bởi billing-service. Nếu chỉ lưu eventId toàn cục trong một store dùng chung, service thứ hai có thể bị chặn nhầm.

Nên định nghĩa key bằng một câu rõ ràng, ví dụ: “Mỗi OrderCreated event được áp dụng tối đa một lần cho mỗi tenant trong inventory-service”.

## 5. Thiết kế schema processed_events

Một relational table tối thiểu:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Nếu eventId chỉ duy nhất trong tenant:

~~~sql
CREATE TABLE processed_events (
    tenant_id VARCHAR(100) NOT NULL,
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, consumer_name, event_id)
);
~~~

Primary key/unique constraint là thành phần quan trọng nhất để giải quyết race giữa nhiều consumer attempts. Kiểm tra rồi insert bằng hai thao tác riêng mà không có unique constraint có thể cho phép hai threads cùng thấy “chưa tồn tại” và cùng chạy side effect.

Có thể bổ sung:

- source topic/partition/offset;
- event type;
- payload/schema version;
- status;
- processed timestamp;
- correlation/trace ID;
- processing version;
- failure metadata đã được làm sạch.

Không cần lưu toàn bộ payload trong dedup table nếu mục tiêu chỉ là nhận diện event đã xử lý. Lưu dữ liệu lớn làm tăng index/storage và có thể tạo thêm rủi ro privacy.

## 6. Inbox table có processing state

Một thiết kế đơn giản dùng insert marker chỉ phù hợp khi insert và side effect cùng một transaction. Với workflow dài hoặc cần điều tra trạng thái, có thể lưu state:

~~~sql
CREATE TABLE inbox_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    status VARCHAR(24) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code VARCHAR(80),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ví dụ states:

| State | Ý nghĩa |
|---|---|
| RECEIVED | Event đã được ghi nhận, chưa xử lý |
| PROCESSING | Một worker đang xử lý, nếu workflow dùng claim/lease |
| COMPLETED | Business operation đã hoàn tất |
| FAILED_RETRYABLE | Lỗi có thể retry theo policy |
| FAILED_TERMINAL | Lỗi cần recovery/manual action |
| REPLAY_PENDING | Được lên lịch replay theo workflow |

State machine phải có quy tắc transition và concurrency control rõ ràng. Không đặt trạng thái COMPLETED trước khi business transaction thực sự commit.

Với listener xử lý ngắn trong một database transaction, thường không cần state machine phức tạp: insert inbox marker, thực hiện side effect, commit cùng transaction là đủ.

## 7. Atomicity: ghi dedup marker và side effect cùng transaction

Đây là quy tắc quan trọng nhất của relational inbox.

~~~text
BEGIN DATABASE TRANSACTION
    |
    +-- INSERT processed_events(eventId)
    |
    +-- Apply business side effect
    |
COMMIT
~~~

Nếu insert marker thất bại do unique constraint, event đã được xử lý trong scope đó. Nếu business operation ném exception, transaction rollback cả marker lẫn side effect.

Ví dụ Spring:

~~~java
@Service
public class InventoryEventProcessor {

    private final JdbcTemplate jdbcTemplate;
    private final InventoryRepository inventoryRepository;

    public InventoryEventProcessor(
            JdbcTemplate jdbcTemplate,
            InventoryRepository inventoryRepository) {
        this.jdbcTemplate = jdbcTemplate;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public boolean process(OrderCreated event) {
        int inserted = jdbcTemplate.update(
            """
            INSERT INTO processed_events(consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "inventory-service",
            event.eventId()
        );

        if (inserted == 0) {
            return false; // Duplicate đã được áp dụng trước đó.
        }

        inventoryRepository.reserve(
            event.orderId(),
            event.items()
        );

        return true;
    }
}
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "inventory-worker"
)
public void onOrderCreated(OrderCreated event) {
    inventoryEventProcessor.process(event);
}
~~~

Trong ví dụ PostgreSQL, ON CONFLICT DO NOTHING dựa trên unique constraint. Cú pháp tương đương ở database khác sẽ khác. Cần bảo đảm Spring transaction manager và JDBC/JPA repository cùng tham gia một transaction manager/database transaction.

Khi method trả về false, listener có thể kết thúc thành công; container sau đó commit offset theo AckMode/error-handling policy. Không ném exception chỉ vì duplicate đã được xử lý đúng, nếu contract cho phép duplicate suppression là success.

## 8. Vì sao không insert marker trước rồi commit riêng?

Thiết kế nguy hiểm:

~~~text
Transaction A:
  INSERT processed_events(eventId)
  COMMIT

Business operation:
  reserve stock
  FAIL

Kafka redelivers event
  |
  v
Dedup marker exists
  |
  v
Consumer skips event
  |
  v
Stock was never reserved
~~~

Đây là **false dedup**: store nói event đã xử lý dù business effect chưa hoàn tất.

Thiết kế ngược lại cũng nguy hiểm:

~~~text
Business operation commits
       |
       v
Process crashes before dedup marker insert
       |
       v
Kafka redelivers
       |
       v
Business operation runs again
~~~

Với side effect nằm trong cùng relational database, cách an toàn là marker và business write cùng transaction.

Nếu side effect ở hệ thống ngoài database, một transaction SQL không thể atomic với HTTP call hoặc payment provider. Khi đó cần idempotency key ở hệ thống đích, outbox/saga hoặc workflow có trạng thái và reconciliation.

## 9. Unique constraint giải quyết race condition

Giả sử hai consumer attempts xử lý cùng event gần như đồng thời:

~~~text
Worker A: SELECT eventId -> not found
Worker B: SELECT eventId -> not found

Worker A: reserve stock
Worker B: reserve stock

Worker A: INSERT marker
Worker B: INSERT marker
~~~

Nếu chỉ SELECT rồi INSERT mà không có unique constraint/locking đúng, cả hai có thể thực hiện side effect.

Thiết kế insert-first:

~~~text
Worker A: INSERT eventId -> success, owns processing
Worker B: INSERT eventId -> unique conflict/no-op

Worker A: apply side effect -> commit
Worker B: sees duplicate -> skip
~~~

Unique constraint là trọng tài ở database. Nó xử lý cạnh tranh ngay cả khi hai application instances không biết nhau.

Với PostgreSQL, INSERT ... ON CONFLICT DO NOTHING là một cách phổ biến. Với database khác, dùng cơ chế atomic insert-if-absent/unique key tương đương.

Không dựa vào JVM synchronized hoặc local HashSet để dedup giữa nhiều pods.

## 10. Xử lý duplicate bằng exception hay affected row count?

Có hai cách:

1. Thực hiện INSERT và bắt unique-constraint exception.
2. Dùng insert-if-absent và kiểm tra số dòng được insert.

Cách thứ hai thường dễ diễn đạt hơn:

~~~java
int inserted = jdbcTemplate.update(
    """
    INSERT INTO processed_events(consumer_name, event_id)
    VALUES (?, ?)
    ON CONFLICT DO NOTHING
    """,
    consumerName,
    eventId
);

if (inserted == 0) {
    return DuplicateDecision.ALREADY_PROCESSED;
}

return DuplicateDecision.NEW_EVENT;
~~~

Không bắt mọi DataIntegrityViolationException rồi coi là duplicate. Lỗi có thể do NOT NULL, foreign key, length hoặc constraint khác. Nếu dùng exception path, phải xác định đúng constraint và chỉ xử lý lỗi duplicate tương ứng.

## 11. Database transaction và Kafka offset commit là hai transaction khác nhau

Với relational inbox, timeline phổ biến:

~~~text
Kafka delivers record
       |
       v
DB transaction:
  insert inbox marker
  apply business write
  commit
       |
       v
Listener returns successfully
       |
       v
Spring Kafka commits source offset
~~~

Có một cửa sổ giữa DB commit và Kafka offset commit. Nếu process crash ở đó, Kafka redelivers. Inbox marker đã commit nên lần sau consumer bỏ qua business write lặp.

Đây là lý do inbox pattern hoạt động tốt cho **database side effects** dù không có một distributed transaction giữa Kafka và database.

Không cần cố gắng commit Kafka offset trước database commit để giảm duplicate; điều đó tạo nguy cơ mất message nếu DB transaction thất bại sau khi offset đã tiến.

## 12. Kết hợp với AckMode

Với Spring Kafka:

- AckMode.RECORD có thể commit offset sau khi record listener hoàn tất theo container semantics.
- AckMode.BATCH commit tiến độ poll batch sau khi xử lý batch.
- MANUAL/MANUAL_IMMEDIATE yêu cầu ứng dụng acknowledge theo contract.
- Transactional listener có đường commit offsets cùng Kafka transaction.

Dedup store không thay đổi AckMode. Nó bảo vệ business side effect khi record được giao lại.

Với manual ack:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    inventoryEventProcessor.process(event);
    acknowledgment.acknowledge();
}
~~~

Method process phải hoàn tất database transaction trước khi acknowledge. Nếu async processing được sử dụng, chỉ acknowledge sau khi operation thực sự hoàn tất và lỗi đã được xử lý theo policy.

## 13. Kafka transactions có thay thế inbox không?

Kafka transactions có thể atomically commit:

- Kafka output records được gửi trong transaction.
- Input consumer offsets được gửi vào cùng transaction.
- Transaction commit hoặc abort toàn bộ các thao tác Kafka thuộc transaction đó.

Điều này hữu ích cho consume-transform-produce khi mọi side effects nằm trong Kafka.

Nhưng Kafka transaction không tự bao gồm relational database, Redis, HTTP service hoặc payment provider. Nếu consumer cập nhật DB rồi commit Kafka offset, vẫn có failure window giữa hai systems.

Nếu mọi business state và dedup marker đều ở Kafka compacted topic/state store có transaction semantics phù hợp, có thể thiết kế dedup khác. Nhưng không nên khái quát Kafka EOS thành exactly-once cho toàn bộ application.

## 14. Redis làm deduplication store

Redis hỗ trợ thao tác atomic set-if-absent:

~~~text
SET dedup:inventory:evt-42 1 NX EX 604800
~~~

Ý nghĩa:

- SET key nếu key chưa tồn tại.
- NX bảo đảm thao tác chỉ thành công nếu chưa có key.
- EX đặt TTL 604800 giây, ví dụ bảy ngày.

Nếu trả về OK, request đã claim key. Nếu key tồn tại, event có thể đã được xử lý hoặc đang được một worker khác claim.

Trong Spring Data Redis:

~~~java
Boolean claimed = stringRedisTemplate.opsForValue()
    .setIfAbsent(
        "dedup:inventory:" + event.eventId(),
        "PROCESSING",
        Duration.ofDays(7)
    );
~~~

Đây chỉ là ví dụ atomic claim. Nó chưa giải quyết đầy đủ trạng thái PROCESSING, failure recovery, lease expiry và atomicity với database side effect.

Nếu Redis claim thành công rồi database transaction thất bại, key vẫn có thể tồn tại và redelivery bị bỏ qua. Không dùng một Redis SET NX trước DB write làm bằng chứng business operation đã hoàn tất.

## 15. Redis claim và lease

Nếu cần Redis để điều phối processing, state có thể có:

~~~text
ABSENT
  |
  v
PROCESSING (lease expires at T)
  |
  +-- Business operation success -> COMPLETED
  |
  +-- Failure -> FAILED_RETRYABLE or release claim
~~~

Một lease cần:

- Owner token duy nhất cho worker claim.
- Expiration.
- Atomic compare-and-set khi gia hạn hoặc release.
- Không cho worker cũ release claim của worker mới.
- Quy tắc recovery khi lease hết hạn.
- Idempotent business side effect vì worker cũ có thể vẫn đang chạy sau khi lease hết hạn.

Chỉ dùng DEL key khi worker kết thúc có thể nguy hiểm: worker A hết lease, worker B claim, rồi worker A chạy finally DEL và xóa claim của B. Dùng owner token và Lua script/atomic conditional operation để chỉ release đúng claim của mình.

Ngay cả lease đúng cũng không làm HTTP/DB side effect atomic với Redis. Cần idempotency tại nơi thực hiện side effect.

## 16. Redis persistence và eviction

Redis có thể restart, failover hoặc evict keys tùy persistence, replication và maxmemory policy.

Nếu dedup key bị mất trước khi duplicate có thể xuất hiện, event được xem là mới và side effect có thể lặp.

Đánh giá:

- AOF/RDB persistence policy.
- Replication/failover guarantees.
- Eviction policy.
- Memory pressure.
- TTL distribution.
- Backup/restore behavior.
- Cluster hash slot/partitioning.
- Network timeout và ambiguous write outcome.

Nếu yêu cầu dedup là điều kiện correctness tài chính hoặc tồn kho, không dùng cache volatile làm nguồn sự thật duy nhất trừ khi durability/retention của nó đáp ứng yêu cầu và business operation có thêm protection.

## 17. So sánh relational database và Redis

| Tiêu chí | Relational inbox | Redis key-value |
|---|---|---|
| Atomic với business DB write cùng database | Có, cùng transaction | Không nếu business write ở SQL DB riêng |
| Atomic insert-if-absent | Unique constraint | SET NX |
| Durability | Theo database commit/replication policy | Phụ thuộc persistence/replication config |
| Query/audit history | Mạnh, SQL | Cần thiết kế riêng |
| TTL | Cleanup job/partition retention | TTL native |
| Concurrency | Unique constraint/transactions | Atomic commands/Lua |
| High throughput | Phụ thuộc DB/index/partitioning | Thường nhanh cho key lookups |
| Multi-service shared dedup | Có thể, cần scope rõ | Có thể, cần namespace/ACL |
| Transaction với business side effect SQL | Tốt nếu cùng DB | Không tự atomic |
| Failure khi eviction | Không thường tự xóa trước cleanup | Có thể mất key do eviction |

Một lựa chọn phổ biến cho business effects trong PostgreSQL là inbox table trong cùng database transaction. Redis phù hợp với duplicate suppression ngắn hạn, rate limiting hoặc claim/lease, nếu loss/expiry semantics được chấp nhận.

## 18. TTL: giữ dedup key bao lâu?

Dedup store không thể xóa key tùy ý. TTL/retention phải dài hơn khoảng thời gian hệ thống cho phép cùng event quay lại.

Các nguồn replay:

- Consumer retry/backoff.
- Retry topics có delay dài.
- DLT retention và manual review.
- Operator replay sau incident.
- Producer/outbox retry.
- Backup restore hoặc disaster recovery.
- Client retries.

Nếu TTL là một ngày nhưng operator có thể replay DLT sau ba tuần, event cũ có thể bị áp dụng lại sau khi dedup key hết hạn.

Quy tắc:

~~~text
dedup retention >= maximum allowed replay horizon
                   + operational safety margin
~~~

Nếu không thể giới hạn replay horizon, cần một business-level uniqueness constraint hoặc permanent event ledger phù hợp thay vì chỉ TTL ngắn.

## 19. Retention và chi phí storage

Giả sử hệ thống nhận 2 triệu unique events mỗi ngày, mỗi row/index footprint trung bình 120 bytes:

~~~text
2,000,000 × 120 bytes = 240 MB/day
30 days ≈ 7.2 GB
90 days ≈ 21.6 GB
~~~

Đây là phép tính minh họa chưa bao gồm replication, index overhead, vacuum/free space, page fragmentation và backup.

Thiết kế retention cần cân bằng:

- Duplicate/replay horizon.
- Regulatory/audit retention.
- Database storage và index size.
- Cleanup workload.
- Partition pruning.
- Query latency.
- Recovery objectives.

Không xóa marker chỉ vì bảng lớn mà chưa xác định thời gian replay tối đa. Có thể partition theo processed_at và drop partitions cũ sau khi hết retention, nhưng cần đảm bảo unique constraint/index semantics phù hợp với database.

## 20. Cleanup job và race với event replay

Một cleanup job:

~~~sql
DELETE FROM processed_events
WHERE processed_at < now() - INTERVAL '90 days';
~~~

Query này minh họa cho PostgreSQL; xóa hàng triệu records một lần có thể tạo transaction dài, lock, WAL và vacuum pressure.

Các cách vận hành:

- Xóa theo batches có giới hạn.
- Chạy ngoài peak traffic.
- Theo dõi rows deleted, duration, locks và database bloat.
- Dùng time partitioning khi schema/unique key hỗ trợ.
- Xác định rõ replay policy trước khi xóa.

Một race có thể xảy ra: cleanup xóa key ngay trước khi một DLT replay cũ được publish. Nếu replay horizon dài hơn retention, dedup không còn bảo vệ event đó.

## 21. Partitioning inbox table

Bảng dedup lớn có thể partition theo thời gian:

~~~text
processed_events
  +-- p2026_01
  +-- p2026_02
  +-- p2026_03
~~~

Partitioning giúp cleanup bằng drop partition nhanh hơn delete từng row, nhưng nhiều relational databases yêu cầu partition key phải nằm trong unique/primary key của partitioned table. Điều này có thể làm mất khả năng global uniqueness của eventId nếu thiết kế không phù hợp.

Các lựa chọn:

- Dùng event timestamp/processing date trong unique key khi contract cho phép.
- Giữ một compact global dedup index/table.
- Dùng sharding theo hash eventId.
- Tách hot inbox và archive/audit store.

Đừng thêm partitioning trước khi đo index size, insert rate, vacuum và query plan. Partitioning sai có thể làm unique constraint không còn bảo vệ key toàn cục như mong muốn.

## 22. Chọn database cho dedup store

Nếu business state nằm trong PostgreSQL, inbox table cùng DB thường là lựa chọn tự nhiên vì atomic transaction.

Nếu business state nằm trong MySQL, dùng unique key và transaction trong MySQL.

Nếu business state nằm ở nhiều stores, phải chọn một **source of truth** cho idempotency và thiết kế workflow có thể phục hồi. Không nên ghi marker ở Redis rồi side effect ở SQL và giả định hai writes atomic.

Nếu service chỉ làm một side effect HTTP, xem API đích có hỗ trợ idempotency key và lookup operation outcome hay không. Nếu không, cần một state machine durable để xử lý ambiguous timeout và reconciliation.

## 23. External API và payment idempotency

Một database inbox không tự ngăn external API được gọi hai lần:

~~~text
Consumer nhận PaymentRequested
       |
       v
Insert inbox marker
       |
       v
Call payment provider
       |
       v
Provider charge thành công
       |
       v
Process crash trước khi lưu kết quả
       |
       v
Kafka redelivery
~~~

Nếu lần sau gọi provider với request mới, có thể charge hai lần.

Giải pháp:

- Dùng eventId/commandId làm provider idempotency key nếu API hỗ trợ.
- Persist provider operation ID và state.
- Khi timeout ambiguous, query provider theo idempotency key/operation ID trước khi gọi lại.
- Ghi kết quả và inbox state trong DB transaction sau khi xác nhận.
- Có reconciliation job cho operation ở trạng thái UNKNOWN.

Không đánh dấu COMPLETED trước khi có evidence provider đã thực hiện operation theo contract. Cũng không gọi lại charge chỉ vì client timeout mà không biết lần đầu có thành công không.

## 24. State machine cho side effect ngoài database

Một workflow có thể dùng:

~~~text
RECEIVED
   |
   v
PENDING
   |
   v
CALLING_EXTERNAL
   |
   +-- Confirmed success -> COMPLETED
   |
   +-- Definitive failure -> FAILED_RETRYABLE / FAILED_TERMINAL
   |
   +-- Timeout unknown -> RECONCILIATION_REQUIRED
~~~

Các state phải được lưu bền vững. Worker cần claim/lease để không chạy cùng operation song song; mỗi external request cần idempotency key ổn định; reconciliation phải có quyền query trạng thái provider.

Nếu workflow có thể chạy lâu, không giữ một DB transaction mở trong suốt HTTP call. Dùng state transitions ngắn, durable, và một saga/workflow orchestration phù hợp.

## 25. Dùng eventId và payload fingerprint

Event ID nhận diện business event. Payload fingerprint giúp phát hiện producer tái sử dụng cùng eventId cho payload khác.

Ví dụ:

~~~text
eventId = evt-42
payloadHash = SHA-256(canonical payload)
~~~

Nếu store đã có evt-42:

- Hash giống: có thể là duplicate event.
- Hash khác: producer vi phạm uniqueness contract hoặc event ID bị tái sử dụng.

Không hash raw serialized bytes một cách tùy tiện nếu serializer/schema evolution có thể thay đổi field order hoặc encoding. Dùng canonical representation hoặc một immutable event identity contract.

Nếu hash payload chứa dữ liệu nhạy cảm, lưu digest đã được tính an toàn và không log payload gốc. Hash không thay thế eventId; nó là kiểm tra consistency bổ sung.

## 26. Consumer version và dedup semantics

Một event có thể được xử lý bởi phiên bản code khác sau deployment. Cần quyết định dedup key có bao gồm processing version hay không.

Nếu key chỉ là (consumer,eventId), một event đã được xử lý bởi version 1 sẽ bị skip khi version 2 replay. Điều này thường đúng nếu mục tiêu là không lặp business side effect.

Nếu workflow là rebuild projection, có thể cần một scope mới:

~~~text
(projection_name, projection_generation, event_id)
~~~

Ví dụ projection orders-v2 có thể cần đọc lại lịch sử events độc lập với orders-v1. Không dùng cùng dedup namespace nếu muốn một lần xử lý có chủ đích cho projection mới.

Ngược lại, không thêm deployment version vào key cho một payment side effect chỉ để “cho phép chạy lại” sau deploy. Làm vậy có thể charge lại payment.

## 27. DLT replay và deduplication store

Khi replay từ DLT, business event ID thường nên giữ nguyên để inbox nhận ra event đã được xử lý.

Nhưng có hai trường hợp:

**Replay vì consumer crash sau side effect thành công:** marker đã commit; skip side effect là đúng.

**Replay vì business logic ban đầu thất bại và chưa có marker:** event chưa được đánh dấu completed; consumer cần xử lý lại.

Nếu inbox marker được ghi sai thời điểm hoặc state FAILED_TERMINAL được coi như COMPLETED, replay hợp lệ có thể bị bỏ qua.

Nên phân biệt states:

- COMPLETED: business effect đã commit.
- FAILED: chưa hoàn tất; có thể replay theo policy.
- SUPPRESSED_DUPLICATE: event trùng với một completed event.
- REPLAY_AUTHORIZED: có explicit workflow cho phép xử lý lại.

Một replay có chủ đích để **sửa/rebuild** có thể cần command riêng và processing scope mới. Không xóa marker thủ công để ép event chạy lại nếu không hiểu side effects trước đó.

## 28. Reprocessing và business compensation

Nếu event đã được xử lý sai và cần chạy lại, dedup store không nên bị xóa một cách mù quáng.

Có thể:

- Tạo compensating event để hoàn tác business effect cũ.
- Tạo correction command mới có idempotency key riêng.
- Dùng projection generation mới cho read model rebuild.
- Dùng explicit replay authorization ghi audit.
- Giữ event history để điều tra trước/sau.

Ví dụ, một OrderPaid event đã được ghi sổ sai thì có thể cần PaymentCorrection event thay vì xóa processed marker rồi chạy lại OrderPaid. Cách nào đúng phụ thuộc domain invariants.

## 29. Xử lý đồng thời với nhiều consumer instances

Trong consumer group, một partition chỉ được assign cho một group member tại một thời điểm theo ownership bình thường. Tuy nhiên, cùng business event vẫn có thể tới:

- Hai partitions do producer key không nhất quán.
- Hai topics.
- Hai consumer groups.
- Replay worker và live worker.
- Hai service instances qua một command path khác.

Vì vậy, dedup store phải xử lý concurrency ở storage layer. Một unique constraint hoặc atomic SET NX là cần thiết nếu nhiều workers có thể cùng claim key.

Không dựa vào partition ordering để bảo vệ global event uniqueness. Nếu cùng eventId được gửi với hai keys khác nhau, chúng có thể vào hai partitions và được xử lý song song.

## 30. Locking và claim strategy

Một số workflow cần claim row:

~~~sql
SELECT *
FROM inbox_events
WHERE status = 'RECEIVED'
ORDER BY received_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

Đây là pattern PostgreSQL cho worker queue. Nó hữu ích khi nhiều workers claim các rows khác nhau.

Với một Kafka listener synchronous, thường không cần thêm queue/lease state nếu DB transaction ngắn và unique insert đủ bảo vệ. Thêm locking không cần thiết có thể làm tăng contention.

Nếu dùng claim state:

- Có owner ID.
- Có lease expiry.
- Có atomic state transition.
- Có recovery cho expired leases.
- Có fencing/version để worker cũ không ghi đè state mới.
- Business side effect vẫn idempotent.

Lease không đảm bảo worker cũ dừng ngay khi lease hết hạn; network pause hoặc GC pause có thể khiến nó tiếp tục. Do đó, storage claim cần fencing hoặc downstream idempotency.

## 31. Dedup store trong nhiều regions

Multi-region active-active làm identity và consistency phức tạp hơn:

~~~text
Region A consumer ----+
                     +---- Shared eventId
Region B consumer ----+
~~~

Nếu hai regions có dedup stores độc lập, cả hai có thể cùng thấy event chưa tồn tại và thực hiện side effect.

Các lựa chọn:

- Một authoritative dedup store cho business key.
- Sharding theo eventId/tenant để một region sở hữu key.
- Strongly consistent database/conditional write.
- Domain partitioning để mỗi aggregate chỉ được xử lý ở một home region.
- Downstream idempotency key ở hệ thống thực hiện side effect.

Eventual replication của Redis hoặc database không bảo đảm hai regions không cùng claim một key trong khoảng replication lag.

Chọn trade-off availability/latency/consistency có chủ đích. Không tuyên bố global dedup exactly-once nếu store chỉ eventually consistent.

## 32. Multi-tenant deduplication

Trong SaaS, cùng eventId có thể được tạo bởi hai tenants nếu mỗi tenant dùng namespace riêng.

Schema:

~~~sql
CREATE TABLE processed_events (
    tenant_id VARCHAR(100) NOT NULL,
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, consumer_name, event_id)
);
~~~

Không lấy tenantId trực tiếp từ một payload không tin cậy rồi dùng nó để vượt qua dedup scope. Xác minh tenant identity theo authentication/authorization contract của event source.

Không để một tenant có thể chiếm event ID namespace của tenant khác bằng cách gửi message giả. Nếu event source không đáng tin, cần signature, ACL và validation phù hợp.

## 33. Dedup store và schema evolution

Event schema có thể thay đổi qua thời gian, nhưng event identity nên ổn định.

Ví dụ:

~~~text
OrderCreated v1:
  eventId=evt-42
  payload: orderId, items

OrderCreated v2:
  eventId=evt-42
  payload: orderId, items, currency
~~~

Nếu event v2 là cùng event được serialize lại, dedup phải giữ nguyên identity. Nếu event v2 là một event nghiệp vụ mới, phải có eventId mới dù aggregateId giống nhau.

Đừng dùng schemaVersion trong dedup key trừ khi contract chủ đích xem mỗi schema version là một operation độc lập. Thông thường schema version mô tả format, không tạo ra một business event mới.

## 34. Dedup store và event ordering

Deduplication ngăn cùng event chạy nhiều lần nhưng không đảm bảo event order.

Ví dụ:

~~~text
OrderCreated -> eventId=E1, aggregateId=O1
OrderPaid    -> eventId=E2, aggregateId=O1
~~~

Nếu E2 tới trước E1 do producer/key/partition topology sai, dedup store vẫn coi cả hai là events mới. Business logic cần kiểm tra aggregate version/sequence hoặc partitioning theo aggregate key.

Có thể lưu:

- aggregateId;
- aggregateVersion;
- event sequence;
- eventId.

Unique constraint trên (aggregateId, aggregateVersion) có thể phát hiện hai events cùng version hoặc replay bất thường, nhưng không thay thế eventId dedup.

## 35. Outbox và inbox kết hợp

Một service có thể vừa consume event vừa publish event mới:

~~~text
Input Kafka event
       |
       v
Database transaction
  +-- Insert inbox marker
  +-- Update business state
  +-- Insert outbox event
       |
       v
Commit DB transaction
       |
       v
Outbox publisher sends Kafka event
~~~

Inbox ngăn input event lặp side effect. Outbox bảo đảm output event intent được lưu cùng business state. Outbox publisher vẫn có thể publish duplicate nếu send ACK và mark-sent không atomic; downstream consumer cần dedup bằng eventId.

Hai pattern bổ sung cho nhau:

- **Inbox:** chống lặp khi nhận.
- **Outbox:** không mất event khi phát.

Không có nghĩa cả pipeline trở thành exactly-once; nó tạo các ranh giới durable và có thể phục hồi.

## 36. Dedup khi xử lý batch

Batch listener có thể nhận nhiều records cùng lúc. Mỗi record cần dedup key riêng, không dùng một marker chung cho cả batch trừ khi batch identity là business contract.

Một transaction:

~~~text
BEGIN
  for each record:
    insert inbox marker
    if new:
      apply side effect
    else:
      count duplicate
COMMIT
~~~

Nếu một record lỗi và transaction rollback, các markers và side effects trong cùng transaction cũng rollback. Error handler có thể redeliver batch/record theo batch error semantics.

Với batch lớn:

- Dùng batch insert/upsert nếu DB hỗ trợ.
- Giữ unique constraint.
- Phân biệt records mới và duplicates.
- Cân nhắc transaction duration/lock contention.
- Không acknowledge toàn batch trước khi tất cả side effects đủ điều kiện.

Nếu mỗi record có thể commit độc lập, thiết kế batch error handling và dedup transaction boundary cho phù hợp.

## 37. Logging cho dedup decisions

Khi store xác định duplicate, nên ghi event log có cấu trúc:

~~~json
{
  "event": "dedup_duplicate_suppressed",
  "service": "inventory-service",
  "consumer": "inventory-worker",
  "event_id": "evt-42",
  "tenant_id": "tenant-a",
  "topic": "orders.events",
  "partition": 2,
  "offset": 18421,
  "dedup_scope": "tenant-consumer-event",
  "decision": "skip_business_effect"
}
~~~

Log này giúp phân biệt record mới ở offset 18421 với business event đã được xử lý trước. Không log payload đầy đủ hoặc secret.

Nên log duplicate ở DEBUG/INFO theo sampling/baseline; một duplicate suppressed có thể là hành vi bình thường trong at-least-once processing. Alert khi tỷ lệ tăng đột biến hoặc duplicate suppression xuất hiện ở workflow không kỳ vọng.

## 38. Metrics cho deduplication store

Các metrics gợi ý:

| Metric | Ý nghĩa |
|---|---|
| dedup_lookup_total | Tổng số lần kiểm tra/claim key |
| dedup_new_event_total | Key mới được claim |
| dedup_duplicate_total | Key đã tồn tại |
| dedup_store_error_total | Lookup/insert lỗi |
| dedup_lookup_latency | Độ trễ đọc/claim |
| dedup_db_conflict_total | Unique conflict/duplicate insert |
| dedup_expired_key_total | Keys bị cleanup/expire nếu đo được |
| dedup_inflight_total | Processing claims đang hoạt động |
| dedup_stale_processing_total | Claims PROCESSING quá lease |
| business_effect_applied_total | Business effects thực sự được áp dụng |
| duplicate_suppressed_total | Side effects bị ngăn do duplicate |

Các metric names là custom. Đặt labels có cardinality hữu hạn như consumer, service, topic, outcome và store type. Không đưa eventId, tenant ID tự do hoặc Kafka offset vào Prometheus labels nếu chúng có tập giá trị lớn.

### 38.1. Dedup ratio

Một tỷ lệ đơn giản:

~~~text
duplicate_ratio =
    duplicate_suppressed
    / all_dedup_decisions
~~~

Phải định nghĩa denominator rõ ràng. Tỷ lệ cao có thể là dấu hiệu producer duplicate, replay hoặc retry behavior; không nhất thiết là lỗi nếu hệ thống chủ động replay.

## 39. Prometheus query minh họa

Giả sử app export counters:

~~~promql
sum by (consumer, topic) (
  rate(app_dedup_duplicate_total[5m])
)
~~~

Tỷ lệ duplicate:

~~~promql
sum(rate(app_dedup_duplicate_total[10m]))
/
clamp_min(
  sum(rate(app_dedup_lookup_total[10m])),
  0.000001
)
~~~

Store errors:

~~~promql
sum by (store_type, error_group) (
  rate(app_dedup_store_error_total[5m])
)
~~~

Lookup latency p95 nếu Timer được export dưới dạng histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, consumer) (
    rate(app_dedup_lookup_latency_seconds_bucket[5m])
  )
)
~~~

Tên metric thực tế phụ thuộc Micrometer registry và naming convention. Không dùng các query này trước khi xác nhận exporter đang cung cấp metric tương ứng.

## 40. Alert cho dedup store

### Store unavailable

Nếu dedup store không truy cập được, consumer không thể quyết định chắc chắn event mới hay duplicate.

Chính sách thường an toàn là **fail closed** cho business side effects cần idempotency: không thực hiện side effect khi không thể kiểm tra/claim key. Error handler có thể retry theo backoff hoặc pause theo policy.

Fail open (bỏ qua dedup và xử lý) có thể gây side effects lặp. Chỉ dùng nếu domain chấp nhận duplicate hoặc downstream có idempotency độc lập.

### Duplicate spike

Alert khi duplicate ratio tăng vượt baseline và kết hợp:

- producer send retries/ambiguous acknowledgements;
- consumer rebalances/commit failures;
- outbox publisher retries;
- DLT replay volume;
- idempotency suppression rate.

### Stale processing claims

Với state machine/lease, alert khi PROCESSING rows quá hạn. Xác định worker còn sống, lease renewal có lỗi hay side effect đang treo.

### Storage pressure

Theo dõi table size, index size, Redis memory, evictions, cleanup lag và lookup latency. Dedup store chậm có thể kéo giảm consumer throughput và tăng Kafka lag.

## 41. Dedup store failure: fail open hay fail closed?

Hai chính sách:

| Chính sách | Hành vi khi store unavailable | Rủi ro |
|---|---|---|
| Fail open | Xử lý message như chưa thấy | Duplicate side effects |
| Fail closed | Không chạy side effect, retry/pause | Throughput giảm, lag tăng |

Đối với payment, inventory, account balance hoặc operation không thể lặp an toàn, **fail closed** thường phù hợp hơn nếu không có idempotency ở downstream.

Đối với một analytics counter có thể cộng trùng trong giới hạn chấp nhận, fail open có thể là lựa chọn business. Quyết định phải được domain owner chấp thuận và được ghi trong runbook.

Không catch mọi exception từ dedup store rồi return thành công; làm vậy có thể khiến offset commit và event mất cơ hội được xử lý đúng.

## 42. DB outage và transaction behavior

Nếu inbox DB và business state cùng database:

~~~text
Kafka record
   |
   v
DB unavailable
   |
   v
Inbox insert fails
   |
   v
Transaction rollback / listener exception
   |
   v
Kafka offset không được commit theo error policy
   |
   v
Record được retry sau khi DB phục hồi
~~~

Đây là behavior phù hợp với fail-closed. Nhưng cần:

- Timeout DB rõ ràng.
- Retry/backoff có giới hạn.
- Không giữ consumer thread block vô hạn.
- Monitor lag và DB health.
- Tránh retry storm khi database outage kéo dài.

Nếu DB connection pool hết, dedup store latency và consumer lag có thể tăng trước khi lỗi database được phát hiện rõ.

## 43. Store timeout và kết quả không rõ

Một write dedup có thể timeout ở client trong khi database đã commit:

~~~text
INSERT marker + side effect
       |
       v
DB commit thành công
       |
       v
Response bị mất
       |
       v
Client nhận timeout
       |
       v
Kafka redelivery
~~~

Lần xử lý lại thực hiện INSERT cùng unique key. Nếu row tồn tại, ứng dụng nhận duplicate và không lặp side effect. Đây là lợi ích của unique constraint và transaction.

Không giả định timeout nghĩa transaction rollback. Với kết quả không rõ, đọc lại durable state hoặc để unique constraint quyết định khi retry.

## 44. Redis timeout và ambiguous claim

Với Redis SET NX:

~~~text
Client gửi SET key NX
       |
       v
Redis lưu key
       |
       v
Response bị mất
       |
       v
Client timeout
~~~

Ứng dụng không biết key đã được claim hay chưa. Có thể đọc lại key và kiểm tra owner/state, nhưng một read riêng không giải quyết mọi race nếu workflow thay đổi giữa hai thao tác.

Thiết kế claim cần owner token, state, TTL và atomic scripts phù hợp. Với side effect tài chính, đừng để Redis claim là lớp bảo vệ duy nhất nếu business write ở database riêng.

## 45. Backup, restore và disaster recovery

Dedup store mất dữ liệu sau restore có thể khiến event lịch sử được xử lý lại:

~~~text
Database backup at T1
       |
       v
Process events through T2
       |
       v
Disaster recovery restores DB to T1
       |
       v
Kafka group/offset restored at T2 or T1?
       |
       v
Potential mismatch and duplicate effects
~~~

Phải phối hợp recovery point của:

- business database;
- inbox/dedup store;
- Kafka committed offsets;
- outbox rows;
- external side effect state.

Nếu database restore về thời điểm trước marker nhưng Kafka offsets vẫn ở thời điểm sau, event có thể không được redeliver trong khi business state đã rollback. Nếu Kafka offsets restore lùi hơn DB state, event có thể replay và dedup store phải còn markers tương ứng.

Disaster recovery runbook cần reconciliation, không chỉ restore từng hệ thống độc lập.

## 46. Dedup store migration

Khi đổi schema hoặc store:

- Giữ nguyên key semantics.
- Không tạo khoảng thời gian mà hai stores cùng nhận traffic nhưng không chia sẻ uniqueness.
- Backfill markers theo source of truth.
- Xác minh retention/horizon.
- Chạy dual-read/dual-write chỉ khi semantics và failure handling rõ.
- Có rollback plan không làm mất markers.

Ví dụ chuyển từ Redis sang PostgreSQL:

1. Chọn retention và key scope.
2. Export active Redis keys với trạng thái/expiry.
3. Backfill vào DB bằng unique constraints.
4. So sánh counts và sample keys.
5. Chuyển consumer sang DB transaction.
6. Theo dõi duplicate hits, store errors và lag.
7. Chỉ retire Redis sau khi hết replay horizon cần bảo vệ.

Nếu bỏ Redis ngay sau backfill mà còn các keys chưa được copy hoặc TTL chưa hết, duplicates có thể lọt qua.

## 47. Versioning và backward compatibility

Một event ID contract có thể được dùng bởi nhiều producer versions. Khi thay format ID:

- Duy trì parser tương thích với IDs cũ.
- Tránh đổi namespace khiến event cũ thành “new” trong dedup store.
- Backfill hoặc alias keys nếu cần.
- Ghi rõ event source/version.
- Không đưa schema version vào key nếu không có lý do nghiệp vụ.

Nếu consumer đổi tên consumer_name trong inbox key sau deployment, toàn bộ events cũ có thể bị xem là mới. Hãy xem consumer_name là một phần của processing contract ổn định, không nhất thiết là bean/listener ID thay đổi theo refactor.

## 48. Security và privacy của dedup store

Dedup table có thể chứa event IDs, tenant IDs, source offsets và timestamps. Dù không lưu payload, metadata vẫn có thể nhạy cảm.

Áp dụng:

- Database credentials least privilege.
- Chỉ consumer cần thiết được insert/select vào namespace của mình.
- Mã hóa transport và storage theo policy.
- Retention/cleanup phù hợp privacy.
- Audit access khi cần.
- Không expose endpoint tra cứu eventId công khai.
- Không log toàn bộ keys/tenant IDs nếu policy không cho phép.
- Tránh lưu payload hoặc token trong failure metadata.

Một endpoint “check if event exists” có thể bị dùng để dò hoạt động của tenant khác. Cần authentication, authorization và rate limiting nếu expose qua API.

## 49. Runbook: duplicate side effect xảy ra

**Bước 1 — Xác định business event và effect**

Thu thập eventId/commandId, consumer, tenant, operation ID và thời gian. Xác minh effect có thực sự lặp ở database/provider.

**Bước 2 — Phân loại duplicate**

Cùng Kafka offset redelivery, eventId khác offset, producer republish, DLT replay hay client command duplicate?

**Bước 3 — Kiểm tra dedup store**

Marker có tồn tại không? Key scope có đúng không? Có TTL hết hạn, cleanup race, Redis eviction hoặc restore rollback không?

**Bước 4 — Kiểm tra atomicity**

Marker và business state có cùng transaction không? Có marker được commit trước effect không? External API có idempotency key không?

**Bước 5 — Kiểm tra concurrency**

Có unique constraint không? Hai workers có cùng claim event không? Có local in-memory dedup thay cho shared store không?

**Bước 6 — Giảm tác động**

Theo domain, tạm dừng consumer/operation gây thêm duplicate nếu an toàn. Không reset offsets hoặc xóa marker vội vàng.

**Bước 7 — Reconcile**

Đối soát payment/inventory/order state, thực hiện compensation theo quy trình nghiệp vụ.

**Bước 8 — Sửa và xác minh**

Thêm atomic inbox/unique key hoặc downstream idempotency. Test crash sau side effect trước offset commit và xác nhận side effect chỉ xảy ra một lần.

## 50. Runbook: dedup store unavailable

1. Xác định relational DB/Redis và endpoint bị ảnh hưởng.
2. Xem connection pool, timeout, latency, failover và network.
3. Xác nhận consumer đang fail closed hay fail open.
4. Với side effects không an toàn khi lặp, giữ fail closed.
5. Kiểm tra consumer lag, retry rate và partition assignment.
6. Khôi phục store hoặc failover theo quy trình.
7. Xác nhận unique constraint/Redis availability và consistency.
8. Cho consumer tiếp tục theo rollout/throughput có kiểm soát.
9. Theo dõi duplicate suppression và business effects.

Không bỏ qua dedup để giảm lag khi store outage nếu downstream không có idempotency tương đương.

## 51. Runbook: duplicate event bị skip nhầm

Triệu chứng: consumer log duplicate nhưng business effect chưa từng hoàn tất.

1. Tìm inbox row theo composite key.
2. Xem status và processed_at.
3. Kiểm tra code path có ghi marker trước side effect và commit riêng không.
4. Xem transaction boundaries/transaction manager propagation.
5. Xác minh business state và external provider state.
6. Nếu marker sai, chỉ điều chỉnh theo quy trình reconciliation có audit.
7. Sửa atomicity và test side effect failure sau marker insert.

Không xóa marker chỉ dựa trên log duplicate. Có thể business side effect đã hoàn tất nhưng log success bị mất.

## 52. Runbook: duplicate lọt qua dedup store

Khả năng:

- Key scope không bao gồm tenant/consumer phù hợp.
- Event ID được producer tạo lại mỗi lần retry.
- Unique constraint thiếu hoặc sai.
- Store bị eviction/TTL hết hạn.
- Hai regions dùng stores eventual consistency.
- Consumer sử dụng local cache thay vì shared store.
- Marker và side effect nằm ở hai transactions khác nhau.

Kiểm tra:

1. So sánh key thực tế ở hai processing attempts.
2. Kiểm tra unique constraint/index.
3. Kiểm tra DB/Redis durability và cleanup.
4. Xem concurrency/region/partition.
5. Xác minh eventId contract ở producer.
6. Reproduce race trong integration test.

## 53. Kiểm thử deduplication store

Một bộ test quan trọng:

### 53.1. Event mới

- Inbox insert thành công.
- Business effect chạy một lần.
- Transaction commit.
- Kafka listener return thành công.

### 53.2. Cùng event được giao lại

- Inbox insert bị conflict/no-op.
- Business effect không chạy lại.
- Listener kết thúc theo duplicate policy.

### 53.3. Business operation thất bại

- Inbox marker insert.
- Side effect throw exception.
- DB transaction rollback.
- Marker không tồn tại sau rollback.
- Retry có thể xử lý lại event.

### 53.4. Hai workers cạnh tranh

- Hai threads/instances cùng xử lý eventId.
- Chỉ một unique insert thành công.
- Business effect chỉ xảy ra một lần.

### 53.5. DB commit response timeout

- Transaction có thể đã commit dù client timeout.
- Redelivery thử insert lại.
- Unique constraint ngăn effect lặp.

### 53.6. Redis claim timeout

- Mô phỏng SET NX response ambiguous.
- Xác minh owner/state recovery.
- Không cho worker cũ xóa claim mới.

### 53.7. TTL expiry và DLT replay

- Event replay trước TTL phải bị dedup.
- Replay sau TTL phải tuân theo business retention policy.
- Không để cleanup race làm mất protection sớm.

### 53.8. Database restore

- Restore business DB/inbox và Kafka offsets theo kịch bản DR.
- Xác nhận không mất business effect hoặc tạo duplicate ngoài ý muốn.

## 54. Kiểm thử với Spring Kafka và Testcontainers

Một integration test có thể dùng Kafka Testcontainers và database Testcontainers:

1. Start Kafka broker và PostgreSQL test instance.
2. Tạo topic và consumer group riêng.
3. Gửi eventId cố định.
4. Để listener gọi service transactional inbox.
5. Gửi lại cùng eventId ở một Kafka record mới hoặc ép redelivery cùng offset trong test phù hợp.
6. Assert số business rows/stock changes chỉ tăng một lần.
7. Assert inbox có đúng một composite key.
8. Assert consumer group offset cuối cùng tiến.
9. Kiểm tra duplicate metric/log được phát đúng.

Hai test cases cần tách:

- **Same-record redelivery:** cùng topic-partition-offset được giao lại.
- **Duplicate publication:** hai offsets khác nhau nhưng cùng eventId.

Không gộp chúng thành một test “send same message twice” vì điều đó chỉ kiểm tra duplicate publication, không mô phỏng offset redelivery.

## 55. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Dùng local HashSet làm dedup store | Mất khi restart, không chia sẻ giữa pods | Shared durable store |
| SELECT rồi INSERT không unique constraint | Race cho phép hai side effects | Atomic insert-if-absent/unique key |
| Ghi marker rồi commit trước business effect | Event có thể bị skip dù effect thất bại | Cùng DB transaction |
| Business effect commit rồi mới ghi marker riêng | Redelivery lặp effect | Inbox marker và effect atomic |
| Dùng Redis SET NX làm bằng chứng hoàn tất DB write | Hai systems không atomic | Durable workflow/downstream idempotency |
| TTL ngắn hơn DLT replay horizon | Event cũ được áp dụng lại | Retention theo replay policy |
| Eviction làm mất dedup keys | Duplicate lọt qua | Persistence/no-eviction hoặc durable DB |
| Key chỉ eventId nhưng ID không global unique | Collision giữa tenants/producers | Composite key theo contract |
| Key chứa consumer bean name hay deployment version | Refactor làm events cũ thành mới | Stable processing contract |
| Dùng topic-partition-offset cho business dedup | Replay/republish có offset mới | Business event ID |
| Dùng payload hash làm identity duy nhất | Hai events hợp lệ có payload giống | Stable event/command ID |
| Dùng Kafka EOS để bảo vệ database | DB không nằm trong Kafka transaction | Inbox/outbox/idempotency |
| Fail open khi store lỗi | Side effect có thể lặp | Fail closed theo domain |
| Xóa marker thủ công để replay | Có thể charge/áp dụng lại effect | Audited compensation/replay |
| Không phối hợp DB restore và Kafka offsets | Duplicate hoặc skipped events | DR reconciliation |
| Không đo store latency/errors | DB/Redis degradation gây lag khó tìm | Metrics và alerts |

## 56. Checklist production

Trước khi đưa deduplication store vào production:

1. Đã định nghĩa identity của business event/command chưa?
2. Key có scope đúng theo tenant, consumer và processing contract không?
3. Producer có giữ eventId ổn định qua retry/replay không?
4. Có unique constraint hoặc atomic set-if-absent ở storage layer không?
5. Marker và business side effect có cùng DB transaction không?
6. Nếu side effect là HTTP/payment, downstream có idempotency key không?
7. Có phân biệt RECEIVED/PROCESSING/COMPLETED/FAILED nếu workflow cần state không?
8. Claim/lease có owner token, expiry và fencing/conditional release không?
9. TTL có dài hơn mọi retry/DLT/manual replay horizon không?
10. Cleanup có batch/partition strategy và không race với replay không?
11. Redis persistence, replication và eviction policy có đáp ứng correctness không?
12. Multi-region consistency có ngăn hai regions claim cùng key không?
13. Database backup/restore có phối hợp với Kafka offsets và outbox không?
14. Có metrics lookup latency, duplicate hits, store errors và stale claims không?
15. Có alert cho store unavailable và duplicate spike không?
16. Logs có eventId, current/original Kafka metadata và decision outcome không?
17. Có tránh high-cardinality labels chứa event IDs không?
18. Có integration test same-offset redelivery và different-offset duplicate publication riêng không?
19. Có test crash sau business commit trước offset commit không?
20. Có runbook reconciliation/compensation và replay được audit không?

## 57. Kết luận

**Deduplication store** cung cấp một nguồn trạng thái bền vững để nhận diện event đã được xử lý trong một scope xác định. Với business side effects nằm trong cùng relational database, inbox table có unique constraint và ghi marker cùng side effect trong một transaction là một thiết kế rõ ràng và dễ kiểm chứng. Redis SET NX có thể phù hợp cho claims hoặc duplicate suppression ngắn hạn, nhưng không tự tạo atomicity với database hoặc external API.

Thiết kế phải xác định đúng event identity, consumer/tenant scope, retention và replay horizon; xử lý race bằng unique constraint hoặc atomic operation; và có policy rõ khi store timeout, failover hoặc restore. Kafka retries, rebalances và DLT replay vẫn có thể tạo lại delivery; dedup store giúp lần xử lý lại không tạo side effect ngoài ý muốn khi các boundary được thiết kế đúng.

Một deduplication store tốt không chỉ trả lời “key đã tồn tại chưa?”. Nó phải chứng minh **business operation đã hoàn tất hay chưa**, xử lý được concurrency và failure windows, giữ đủ lịch sử trong thời gian cần thiết, và cho phép đội vận hành điều tra/reconcile mà không vô tình bỏ qua hoặc lặp một nghiệp vụ quan trọng.
