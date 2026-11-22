# Outbox pattern

**Transactional Outbox Pattern** là một cách giải quyết bài toán nhất quán dữ liệu khi một ứng dụng cần **vừa ghi database, vừa phát event sang Kafka**. Ý tưởng cốt lõi là không cố commit database transaction và Kafka publish bằng hai thao tác độc lập. Thay vào đó, ứng dụng ghi **thay đổi nghiệp vụ** và một **outbox event** vào **cùng database transaction**. Một thành phần publisher riêng đọc các outbox event đã commit và gửi chúng tới Kafka.

Trong Spring Kafka Reliability Operations, đây là pattern quan trọng vì transaction của Kafka và transaction của database thường **không cùng một giao dịch nguyên tử**. Kafka transaction giúp nhóm các thao tác Kafka, nhưng không tự rollback một lần ghi PostgreSQL hoặc MySQL đã commit. Outbox di chuyển ranh giới nhất quán ban đầu về một database duy nhất, nơi việc ghi business state và ý định phát event có thể được commit nguyên tử.

Outbox không bảo đảm publisher gửi một event **chính xác một lần**: khi Kafka đã nhận event nhưng publisher chết trước khi đánh dấu hàng outbox đã gửi, event có thể được publish lại. Vì vậy, mô hình thực tế thường là **atomic database write + eventual at-least-once Kafka publication + idempotent consumer**.

## 1. Bài toán dual write

Giả sử Order Service cần:

1. Lưu đơn hàng vào database.
2. Phát event OrderCreated sang Kafka để Inventory Service, Billing Service và Analytics Service xử lý.

Cách viết trực tiếp:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(
        Order.from(command)
    );

    kafkaTemplate.send(
        "orders.created",
        order.getId().toString(),
        toJson(order)
    );
}
~~~

Nhìn qua, annotation @Transactional có vẻ đã bao phủ cả hai thao tác. Nhưng nếu transaction manager của method là **JpaTransactionManager**, nó chủ yếu quản lý database transaction; KafkaTemplate.send() không tự trở thành một phần của cùng database transaction nguyên tử.

Có ít nhất hai cửa sổ lỗi:

**Database commit thành công nhưng Kafka publish thất bại:**

~~~text
INSERT orders ------------------> DB commit thành công
                                         |
                                  Kafka send lỗi
                                         |
                                         v
                               Đơn hàng tồn tại trong DB
                               nhưng downstream không nhận event
~~~

**Kafka publish thành công nhưng database rollback:**

~~~text
Kafka broker xác nhận OrderCreated
                  |
             DB commit lỗi
                  |
                  v
       Downstream nhìn thấy đơn hàng
       chưa tồn tại trong nguồn sự thật
~~~

Đảo thứ tự hai thao tác không giải quyết vấn đề, chỉ đổi cửa sổ lỗi. Dù dùng Kafka producer idempotence hoặc retry producer, ứng dụng vẫn có thể rơi vào trạng thái một hệ thống commit nhưng hệ thống kia chưa commit.

Đó là bài toán **dual write**.

## 2. Outbox thay đổi thiết kế thế nào?

Thay vì vừa ghi database vừa gửi Kafka trong request transaction, Order Service ghi hai bảng **trong cùng một database**:

~~~text
HTTP request: Create order
           |
           v
    BEGIN DB TRANSACTION
           |
           +-- INSERT orders
           |
           +-- INSERT outbox_events
           |
           v
       COMMIT DB
           |
           v
       Response success

        Sau đó:

Outbox publisher / CDC
           |
           v
    Đọc outbox đã commit
           |
           v
      Publish Kafka
           |
           v
    Consumer downstream
~~~

Nếu database commit:

- Order row tồn tại.
- Outbox row tồn tại với ý định publish OrderCreated.

Nếu database rollback:

- Order row không tồn tại do transaction thất bại.
- Outbox row cũng không tồn tại.

Hai bảng cùng nằm trong một transactional database và cùng transaction manager. Việc gửi Kafka diễn ra **sau**, không cần HTTP request giữ connection/transaction chờ Kafka broker.

Đổi lại, event được phát **bất đồng bộ**, nên thường có độ trễ giữa DB commit và Kafka publication. Đó là **eventual consistency** mà downstream cần chấp nhận.

## 3. Ba thuộc tính cần phân biệt

| Thuộc tính | Outbox giải quyết thế nào? | Điều kiện |
|---|---|---|
| Atomicity giữa business state và event intent | Ghi cùng database transaction | Cùng datasource và cùng DB transaction thật sự |
| Durability của event intent | Outbox row tồn tại sau commit | Database WAL/backup/retention đáng tin cậy |
| Publication tới Kafka | Publisher hoặc CDC chuyển outbox row | Có retry, monitoring và vận hành |
| Exactly-once publication | **Không bảo đảm chỉ nhờ outbox** | Cần thêm cơ chế dedup/transaction phù hợp theo phạm vi |
| Exactly-once business effect downstream | Không tự bảo đảm | Idempotent consumer/inbox |
| Thứ tự event theo aggregate | Có thể đạt nếu thiết kế | Key, sequence và thứ tự publisher |
| Latency cực thấp | Không bảo đảm | Poll interval, CDC latency, backlog |
| Consistency xuyên database và HTTP khác | Không tự bảo đảm | Saga, idempotency hoặc orchestration bổ sung |

Đặc biệt, **đã ghi outbox row** không đồng nghĩa **event đã xuất hiện trong Kafka**. Cần trạng thái và metric riêng cho từng giai đoạn.

## 4. Thiết kế bảng outbox

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(150) NOT NULL,
    schema_version INTEGER NOT NULL,
    topic_name VARCHAR(200) NOT NULL,
    event_key VARCHAR(200) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ,
    claimed_until TIMESTAMPTZ,
    claimed_by VARCHAR(100),
    claim_version BIGINT NOT NULL DEFAULT 0,
    last_error TEXT
);

CREATE INDEX idx_outbox_ready
    ON outbox_events (status, next_attempt_at, created_at);

CREATE INDEX idx_outbox_aggregate
    ON outbox_events (aggregate_type, aggregate_id, aggregate_version);
~~~

Đây là schema ví dụ cho **polling publisher**. Với **CDC/Debezium** thuần túy, outbox table thường có thể đơn giản hơn: hàng là một sự kiện bất biến được đọc từ transaction log, không nhất thiết có trường status/lease/attempts.

### 4.1. Ý nghĩa của từng trường

- **id:** định danh sự kiện ổn định xuyên các lần publish/retry; nên dùng UUID hoặc ID duy nhất.
- **aggregate_type:** loại đối tượng nghiệp vụ, ví dụ Order.
- **aggregate_id:** ID của đối tượng; thường làm Kafka partition key.
- **aggregate_version:** số version/sequence hỗ trợ kiểm soát thứ tự trên từng aggregate.
- **event_type:** OrderCreated, OrderCancelled hoặc PaymentAuthorized.
- **schema_version:** hỗ trợ evolution của contract.
- **topic_name:** đích publish, nên được giới hạn theo allowlist/configuration thay vì tin input từ client.
- **event_key:** partition key ổn định.
- **payload:** snapshot event do service quyết định tại thời điểm ghi DB.
- **status:** trạng thái luân chuyển đối với polling publisher.
- **attempts/next_attempt_at:** retry với backoff.
- **claimed_until/claimed_by/claim_version:** cơ chế lease/fencing giúp nhiều publisher workers không đồng thời claim một row.
- **last_error:** thông tin đã làm sạch để vận hành, không nên chứa secret.

Không phải hệ thống nào cũng cần tất cả các cột. Schema nên thể hiện phương thức chuyển dữ liệu thực tế và yêu cầu giữ ordering, retry, cleanup.

## 5. Ghi business state và outbox trong một Spring transaction

Ví dụ Spring Boot dùng Spring Data JPA:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OutboxEventRepository outboxRepository;
    private final ObjectMapper objectMapper;

    public OrderApplicationService(
            OrderRepository orderRepository,
            OutboxEventRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public UUID createOrder(CreateOrderCommand command) {
        UUID orderId = UUID.randomUUID();
        Order order = Order.create(orderId, command);
        orderRepository.save(order);

        OrderCreated event = new OrderCreated(
            orderId,
            order.getCustomerId(),
            order.getTotalAmount(),
            order.getVersion()
        );

        OutboxEvent outbox = OutboxEvent.newEvent(
            UUID.randomUUID(),
            "Order",
            orderId.toString(),
            order.getVersion(),
            "OrderCreated",
            1,
            "orders.events",
            orderId.toString(),
            serialize(event)
        );

        outboxRepository.save(outbox);
        return orderId;
    }

    private String serialize(OrderCreated event) {
        try {
            return objectMapper.writeValueAsString(event);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Cannot create outbox event payload", ex
            );
        }
    }
}
~~~

Ví dụ sử dụng các domain classes/repositories minh họa. Điều kiện cốt lõi:

1. Method @Transactional thực sự đi qua Spring proxy và có active **database transaction**.
2. OrderRepository và OutboxEventRepository sử dụng **cùng datasource/transaction manager**.
3. Nếu serialize payload thất bại, method ném exception để rollback toàn bộ transaction.
4. Không gọi KafkaTemplate.send() như một bước bắt buộc phải thành công trước khi database commit.
5. Nếu DB transaction commit thất bại, cả order lẫn outbox event đều không được coi là tồn tại.

Với nhiều database hoặc một repository sử dụng connection ngoài transaction, hai lần save không còn nguyên tử. Cùng annotation @Transactional không tạo atomicity xuyên nhiều datasource độc lập.

### 5.1. Event nên phản ánh trạng thái đã commit

Event payload nên được xây dựng từ dữ liệu trong cùng transaction. Không để publisher đọc lại một order sau nhiều phút rồi tự tạo OrderCreated từ trạng thái **hiện tại**, vì order có thể đã đổi status hoặc version.

Ví dụ OrderCreated cần ghi **trạng thái tại thời điểm tạo đơn hàng**, không phải trạng thái sau khi đã Cancelled. Cách đơn giản là lưu payload bất biến vào outbox row ngay trong transaction.

## 6. Vì sao không chỉ dùng @TransactionalEventListener(AFTER_COMMIT)?

Một kỹ thuật phổ biến:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    kafkaTemplate.send("orders.events", event.orderId(), event);
}
~~~

Listener chỉ chạy sau khi database transaction commit thành công, giúp tránh phát event **trước** DB commit. Nhưng nó **không phải một durable outbox** nếu event chỉ tồn tại trong memory.

Nếu process crash ngay sau DB commit nhưng trước khi callback chạy, hoặc callback cố publish Kafka rồi fail mà không có nơi lưu intent, event có thể mất.

**Outbox row** mới là bản ghi bền vững để publisher khác tiếp tục sau restart. Có thể dùng AFTER_COMMIT để đánh thức publisher sớm hơn (optimization), nhưng không thay thế polling/CDC dựa trên database outbox bền vững.

## 7. Hai cách chuyển outbox sang Kafka

Có hai chiến lược chính:

### 7.1. Polling publisher

Một job do ứng dụng hoặc service riêng vận hành:

1. Tìm các outbox rows chưa publish hoặc cần retry.
2. Claim một batch theo lease nếu chạy nhiều workers.
3. Gửi event sang Kafka.
4. Chờ broker xác nhận producer send.
5. Đánh dấu outbox row đã publish.
6. Nếu gửi thất bại, tăng attempts và hẹn retry.

Ưu điểm: không cần CDC/log streaming infrastructure; dễ bắt đầu khi đã có application database. Hạn chế: polling tạo DB load, cần thiết kế claim/retry/cleanup/ordering, latency phụ thuộc lịch poll.

### 7.2. Change Data Capture (CDC)

Một CDC connector như **Debezium** đọc thay đổi đã commit từ transaction log của database (ví dụ PostgreSQL WAL), chuyển outbox inserts thành record Kafka. Debezium Outbox Event Router có thể route event theo aggregate/event metadata.

Ưu điểm: giảm truy vấn polling định kỳ lên bảng outbox, thường có độ trễ thấp, lấy log commit order từ nguồn database. Hạn chế: phải vận hành connector, Kafka Connect, database replication slot/log retention, snapshot và schema evolution; vẫn cần xử lý duplicate khi connector restart.

| Tiêu chí | Polling publisher | CDC/Debezium |
|---|---|---|
Nguồn nhận event | Query bảng outbox | Database transaction log |
| Triển khai bước đầu | Thường đơn giản hơn | Thêm connector và CDC infrastructure |
| DB load | Query/claim/update trực tiếp | Đọc WAL/binlog; có chi phí replication/log |
| Độ trễ | Phụ thuộc poll interval/backlog | Thường gần thời điểm commit, vẫn có lag |
| Retry | Ứng dụng quản lý | Connector/Kafka Connect quản lý theo contract |
| State published | Có thể lưu SENT | Không nhất thiết cần flag trên row |
| Thứ tự | Phụ thuộc claim và worker scheduling | Phụ thuộc commit-log order và mapping sang Kafka |
| Duplicate | Có | Có thể có khi recover/restart |
| Vận hành đặc thù | Lease, retry rows, cleanup | Replication slot, connector offsets, snapshot, WAL retention |

Hai cách đều không xóa bỏ nhu cầu về stable event ID và idempotent consumer.

## 8. Polling publisher: vì sao cần claim và lease?

Giả sử ứng dụng có ba replicas chạy scheduler cùng quét:

~~~sql
SELECT *
FROM outbox_events
WHERE status = 'NEW'
ORDER BY created_at
LIMIT 100;
~~~

Nếu không lock/claim, cả ba replicas có thể đọc cùng 100 rows và đồng thời publish, tạo duplicate không cần thiết.

Một cách là dùng PostgreSQL **FOR UPDATE SKIP LOCKED** trong một transaction ngắn để claim rows, rồi commit claim trước khi gửi Kafka.

Ví dụ ý tưởng:

~~~sql
WITH picked AS (
    SELECT id
    FROM outbox_events
    WHERE
        (status = 'NEW'
         OR (status = 'IN_PROGRESS' AND claimed_until < now()))
        AND (next_attempt_at IS NULL
             OR next_attempt_at <= now())
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 50
)
UPDATE outbox_events AS o
SET
    status = 'IN_PROGRESS',
    claimed_by = :worker_id,
    claimed_until = now() + INTERVAL '2 minutes',
    claim_version = claim_version + 1
FROM picked
WHERE o.id = picked.id
RETURNING o.*;
~~~

Tác dụng:

- Chỉ một transaction claim được một row đang bị lock.
- Row IN_PROGRESS có lease hết hạn có thể được claim lại sau crash.
- claim_version hỗ trợ tránh worker cũ cập nhật row sau khi lease đã được chuyển cho worker khác.

**Không giữ database transaction và row lock mở trong lúc chờ Kafka send.** Nếu gửi Kafka mất vài giây, việc giữ DB locks có thể làm giảm throughput hoặc gây lock contention. Claim trong transaction ngắn, commit claim, gửi Kafka ngoài DB transaction, rồi update trạng thái trong transaction khác.

### 8.1. Lease không tự giải quyết duplicate

Giả sử worker A claim row, gửi Kafka thành công, nhưng dừng trước khi đánh dấu SENT. Sau khi lease hết hạn, worker B claim lại row và gửi thêm lần nữa.

Lease ngăn nhiều worker xử lý **đồng thời trong điều kiện bình thường**, nhưng không thể phân biệt chắc chắn trường hợp Kafka đã ghi hay chưa khi worker crash.

Đây là lý do cần event ID và idempotent consumer.

## 9. Publisher: chỉ đánh dấu SENT sau Kafka acknowledgement

Ví dụ logic ở tầng ứng dụng:

~~~java
@Component
public class OutboxPublisher {

    private final OutboxStore outboxStore;
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OutboxPublisher(
            OutboxStore outboxStore,
            KafkaTemplate<String, String> kafkaTemplate) {
        this.outboxStore = outboxStore;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Scheduled(fixedDelayString = "${outbox.poll.delay.ms:500}")
    public void publishPending() {
        List<ClaimedOutboxEvent> batch =
            outboxStore.claimReadyRows(50);

        for (ClaimedOutboxEvent event : batch) {
            try {
                ProducerRecord<String, String> record =
                    new ProducerRecord<>(
                        event.topicName(),
                        event.eventKey(),
                        event.payload()
                    );

                record.headers().add(
                    "event-id",
                    event.id().toString().getBytes(StandardCharsets.UTF_8)
                );

                kafkaTemplate.send(record)
                    .get(30, TimeUnit.SECONDS);

                outboxStore.markSent(
                    event.id(),
                    event.claimVersion()
                );
            }
            catch (Exception ex) {
                outboxStore.scheduleRetry(
                    event.id(),
                    event.claimVersion(),
                    ex
                );
            }
        }
    }
}
~~~

Các interface **OutboxStore** và **ClaimedOutboxEvent** là abstraction minh họa; ứng dụng cần triển khai SQL claim, retry/lease và xử lý concurrency. Code dùng synchronous future wait để trình bày ranh giới xác nhận; production có thể dùng async callbacks với concurrency bounded nếu quản lý state/claim phù hợp.

Để lỗi không làm mất event:

- **markSent** chỉ chạy sau Kafka producer future báo thành công.
- Nếu producer send fail, row vẫn phải có đường retry.
- Nếu producer send timeout, kết quả có thể **chưa rõ**: không tự xóa outbox row, chấp nhận khả năng publish duplicate.
- Bảo vệ markSent/scheduleRetry bằng claim_version để worker cũ không ghi đè kết quả của worker mới.
- Không để failed row bị treo vĩnh viễn nếu worker chết; lease phải có đường reclaim.
- Không ghi raw payload nhạy cảm vào last_error hoặc log.

### 9.1. Fencing cập nhật row đã claim

Ví dụ logic update:

~~~sql
UPDATE outbox_events
SET
    status = 'SENT',
    published_at = now(),
    claimed_by = NULL,
    claimed_until = NULL
WHERE id = :event_id
  AND claim_version = :claim_version
  AND status = 'IN_PROGRESS';
~~~

Nếu affected rows bằng 0, worker có thể đã mất lease hoặc row đã chuyển trạng thái. Cần log/metric và không cố update bằng điều kiện yếu hơn để “cho thành công”.

Tương tự khi scheduleRetry, update phải kiểm tra claim_version. Nếu một send thật sự thành công nhưng claim đã mất do timeout dài, worker khác vẫn có thể publish lại; version check bảo vệ **database state**, không bảo đảm một lần publish duy nhất.

## 10. Các cửa sổ lỗi quan trọng

| Thời điểm lỗi | Trạng thái database | Trạng thái Kafka | Kỳ vọng |
|---|---|---|---|
| Lỗi trước DB commit | Order và outbox cùng rollback | Không có event tương ứng từ outbox | Retry request an toàn theo request ID |
| DB commit xong, publisher chưa chạy | Order và outbox đã commit | Chưa có event | Publisher sẽ gửi sau |
| Publisher claim rồi crash | Outbox IN_PROGRESS | Chưa rõ, có thể chưa gửi | Lease hết hạn, worker khác claim lại |
| Kafka send fail rõ ràng | Outbox chưa SENT | Event chưa được xác nhận | Retry có backoff |
| Kafka đã ghi, response mất | Outbox chưa SENT | Event có thể đã tồn tại | Retry có thể tạo duplicate |
| Kafka ack thành công, markSent fail | Outbox chưa SENT | Event đã tồn tại | Retry có thể tạo duplicate |
| MarkSent thành công | Outbox SENT | Đã có broker acknowledgement theo cấu hình | Có thể cleanup theo policy |
| Consumer xử lý xong DB, commit Kafka offset fail | Outbox event đã đến Kafka | Downstream có thể replay | Idempotent consumer |

Sự khác biệt giữa **không mất ý định phát event** và **không phát event trùng** là trọng tâm thiết kế. Outbox giải quyết vế đầu tại DB commit boundary. Vế thứ hai cần được xử lý ở tầng consumer/semantics bổ sung.

## 11. Vì sao polling publisher thường là at-least-once?

Giả sử:

~~~text
Publisher đọc row E-42
      |
      v
Kafka send(E-42) thành công
      |
      v
Process crash trước UPDATE status='SENT'
      |
      v
Publisher restart
      |
      v
Thấy E-42 chưa SENT
      |
      v
Kafka send(E-42) lần nữa
~~~

Không có một commit atomically chung giữa DB update status='SENT' và Kafka producer send trong thiết kế outbox polling thông thường. Do đó, hành vi an toàn là chấp nhận **at-least-once delivery** và chống duplicate bằng event ID ổn định.

Không nên đánh dấu SENT **trước** khi Kafka xác nhận để cố tránh duplicate. Cách này đổi duplicate thành **event loss** nếu Kafka publish thất bại sau khi trạng thái DB đã chuyển.

Trong reliability engineering, **duplicate có thể kiểm soát bằng idempotency** thường tốt hơn **silent loss** không thể tự phục hồi.

## 12. Consumer idempotency bằng inbox pattern

Outbox ở producer nên có một **inbox/dedup** tại consumer quan trọng. Consumer lưu event ID đã xử lý trong cùng database transaction với business side effect.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_events (
    event_id UUID NOT NULL,
    consumer_name VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, consumer_name)
);
~~~

Định danh gồm event_id và consumer_name để hai service khác nhau có thể xử lý cùng event mà không cản nhau.

Spring service minh họa:

~~~java
@Service
public class InventoryEventProcessor {

    private final JdbcTemplate jdbc;
    private final InventoryRepository inventoryRepository;

    public InventoryEventProcessor(
            JdbcTemplate jdbc,
            InventoryRepository inventoryRepository) {
        this.jdbc = jdbc;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void handle(OrderCreated event) {
        int inserted = jdbc.update(
            """
            INSERT INTO processed_events(event_id, consumer_name)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            event.eventId(),
            "inventory-service"
        );

        if (inserted == 0) {
            return; // Event đã được xử lý thành công trước đây.
        }

        inventoryRepository.reserve(
            event.orderId(),
            event.items()
        );
    }
}
~~~

Điều kiện: **JdbcTemplate và InventoryRepository phải tham gia cùng database transaction**. Nếu reserve thất bại, cả insert processed_events lẫn business update phải rollback. Nếu insert dấu processed được commit trước rồi reserve lỗi, retry sẽ bị nhận nhầm là duplicate và bỏ qua nghiệp vụ.

Với @KafkaListener:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "inventory-service"
)
public void onOrderCreated(OrderCreated event) {
    inventoryEventProcessor.handle(event);
}
~~~

Khi method handle commit DB thành công rồi listener return, container mới tiến tới commit consumed offset theo AckMode. Nếu offset Kafka commit fail, record có thể replay nhưng bảng processed_events chống side effect lặp.

Với API/side effect ngoài database, còn cần idempotency key hoặc outbox/saga tương ứng; chỉ inbox database chưa tự đảm bảo HTTP call không bị lặp.

## 13. Event ID, aggregate ID và Kafka key

Ba giá trị phục vụ mục đích khác nhau:

| Giá trị | Ví dụ | Vai trò |
|---|---|---|
| eventId | UUID E-42 | Dedup qua retry/replay |
| aggregateId | Order O-123 | Nhóm các event thuộc cùng đối tượng |
| Kafka key | O-123 | Chọn partition, thường dùng giữ thứ tự theo aggregate |

Nếu publisher retry E-42, **eventId phải giữ nguyên**. Không tạo UUID mới trong mỗi lần send, vì consumer sẽ coi chúng là event mới và dedup thất bại.

Kafka key thường là aggregateId để các event của cùng order được route vào cùng partition khi topology/partition mapping ổn định. Nhưng chỉ cùng partition **chưa đủ** để đảm bảo thứ tự nếu publisher phát các event cùng aggregate theo thứ tự sai.

Ví dụ OrderCreated version 1 và OrderCancelled version 2:

~~~text
Database commit:
  OrderCreated(v1)
  OrderCancelled(v2)

Publisher worker B gửi v2 trước worker A gửi v1
        |
        v
Kafka partition nhận v2 rồi v1
~~~

Kafka giữ thứ tự **đã append vào partition**, không thể tự sửa việc ứng dụng gửi sai thứ tự.

## 14. Bảo toàn ordering với outbox

Ordering là phần khó trong outbox đa worker. Các lưu ý:

- Dùng **aggregate version** tăng đơn điệu trong database transaction nếu nghiệp vụ cần trình tự.
- Serialize các sự kiện cùng aggregate theo đúng version.
- Tránh để hai publisher độc lập claim và gửi hai event cùng aggregate theo thứ tự ngược.
- Dùng cùng Kafka key cho một aggregate khi partition mapping ổn định.
- Consumer có thể kiểm tra version để phát hiện event đến muộn hoặc bị thiếu.
- Khi Kafka topic tăng partition, mapping key→partition có thể thay đổi; cần kế hoạch migration nếu strict ordering qua lịch sử là bắt buộc.

Không nên coi **outbox id tăng** hoặc **created_at** là bảo đảm tuyệt đối về **thứ tự DB commit** khi nhiều transactions chạy đồng thời. Sequence number trong DB có thể được cấp trước commit; một transaction có ID nhỏ hơn vẫn có thể commit sau transaction ID lớn hơn.

Nếu dùng polling publisher, có thể cần thiết kế claim theo aggregate (mỗi aggregate chỉ một event in-flight), khóa hàng business khi cấp version hoặc một cơ chế sequencing khác. Nếu dùng CDC, log commit ordering giúp phản ánh thứ tự commit của database, nhưng route sang Kafka và parallel consumer vẫn cần key/partition phù hợp.

## 15. Retry cho polling publisher

Một row outbox không publish được không nên bị mất. Có thể áp dụng retry với backoff:

~~~text
attempt = 1 -> chờ 1s
attempt = 2 -> chờ 2s
attempt = 3 -> chờ 4s
attempt = 4 -> chờ 8s
attempt = 5 -> chờ 16s
Sau đó -> max 60s hoặc chuyển trạng thái NEEDS_ATTENTION
~~~

Điểm cần thiết kế:

- Phân loại lỗi transient như timeout/coordinator unavailable và lỗi permanent như ACL/serializer sai.
- Đặt producer delivery timeout và backoff hữu hạn.
- Không retry vòng lặp nóng trên row không bao giờ sửa được.
- Nếu event bị đánh dấu NEEDS_ATTENTION hoặc FAILED, vẫn giữ payload/event ID và có alert; **không xóa row**.
- Nếu strict ordering cần version 1 trước version 2, failure của version 1 có thể buộc publisher giữ các version sau cùng aggregate.
- Chỉ đánh dấu SENT khi có đủ bằng chứng broker đã xác nhận theo producer acks policy.

Outbox row lỗi không phải một Kafka consumer poison pill. Nó thuộc failure domain **DB-to-Kafka publisher**; retry và monitoring nên tách khỏi Kafka listener error handling.

## 16. CDC với Debezium Outbox Event Router

Với PostgreSQL, Debezium connector có thể đọc logical decoding/WAL và phát các insert outbox đã commit. Event Router SMT có thể chuyển row thành event Kafka theo aggregate metadata.

Một schema CDC-friendly thường có các field:

~~~sql
CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregatetype VARCHAR(100) NOT NULL,
    aggregateid VARCHAR(128) NOT NULL,
    type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Đây là schema theo naming thường dùng với Debezium Outbox Event Router. Nếu sử dụng field names khác, phải chỉnh connector configuration tương ứng.

Ví dụ fragment cấu hình Kafka Connect/Debezium:

~~~properties
transforms=outbox
transforms.outbox.type=io.debezium.transforms.outbox.EventRouter
transforms.outbox.table.field.event.id=id
transforms.outbox.table.field.event.key=aggregateid
transforms.outbox.route.by.field=aggregatetype
~~~

Event Router có thể route event theo aggregate type, dùng aggregate ID làm Kafka key và mang event ID để downstream dedup. Cấu hình topic naming, field payload và envelope/header cần xác định theo phiên bản Debezium và event contract thực tế.

Các yêu cầu vận hành CDC:

- Database đã bật logical replication hoặc binlog theo connector.
- Connector có quyền đọc và replication phù hợp.
- Replication slot/log retention được giám sát, tránh WAL tăng vô hạn khi connector dừng.
- Kafka Connect có offset storage bền vững.
- Xử lý snapshot/initial start và schema evolution.
- Giữ event ID ổn định để chịu được duplicate khi connector restart.

CDC không có nghĩa một insert sẽ **chắc chắn chỉ xuất hiện đúng một lần** trong Kafka khi connector crash hoặc recover. Hãy thiết kế consumer idempotent.

## 17. Không dùng cả polling và CDC cho cùng nguồn một cách vô tình

Khi migrate từ polling sang Debezium, nếu cả hai publisher cùng đọc và gửi **cùng outbox rows**, cùng event ID có thể xuất hiện hai lần trở lên do hai luồng độc lập.

Nếu cần chuyển đổi:

1. Xác định nguồn publisher đang active.
2. Chọn thời điểm cutover và checkpoint rõ ràng.
3. Xác nhận connector snapshot behavior.
4. Theo dõi event IDs đã publish ở cả hai luồng.
5. Không xóa các outbox rows chưa có bằng chứng đã được xử lý.
6. Dùng idempotent consumers trong giai đoạn chuyển đổi.

Không coi việc tắt polling scheduler rồi bật CDC là đủ nếu chưa xét các row pending và transaction log offset.

## 18. Outbox và Kafka transaction có bổ sung cho nhau không?

Có. Nhưng cần hiểu phạm vi của từng cơ chế:

**Outbox** bảo đảm thay đổi business state và event intent nằm trong cùng database transaction.

**Kafka transaction** bảo đảm một nhóm thao tác Kafka và, trong mô hình consume–transform–produce, consumed offsets có thể commit/abort cùng nhau.

Kafka producer transactional trong outbox publisher có thể hữu ích nếu một outbox row tạo nhiều Kafka records cần commit nguyên tử. Nhưng transaction Kafka **không** tự bao gồm DB update status SENT. Nếu broker commit Kafka transaction xong mà DB chưa đánh dấu SENT, row vẫn có thể được publish lại sau restart.

~~~text
DB transaction:
  INSERT orders + INSERT outbox
               |
               v
        Outbox publisher
               |
               v
        Kafka transaction commit
               |
               X  Không có atomic bridge tự động
               |
               v
        DB UPDATE outbox SET status='SENT'
~~~

Không nên quảng bá outbox + Kafka transactions là một distributed exactly-once commit giữa database và Kafka. Để tạo exactly-once business effects, vẫn cần event ID và idempotency tại consumers.

## 19. Chuyện gì xảy ra khi một record bị publish trùng?

Ví dụ outbox row:

~~~json
{
  "eventId": "e782a43e-7ca4-4b9c-bc70-2ad583aa0e12",
  "aggregateType": "Order",
  "aggregateId": "O-123",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "payload": {
    "orderId": "O-123",
    "totalAmount": 250000
  }
}
~~~

Publisher gửi event tới Kafka, broker đã ghi nhưng ứng dụng crash trước markSent. Sau restart, publisher gửi lại. Consumer có thể thấy hai records khác Kafka offset, nhưng **cùng eventId**.

~~~text
Kafka orders.events:
    offset 101: eventId E-42
    offset 125: eventId E-42

Inventory consumer:
    E-42 lần đầu -> insert processed_event, reserve stock
    E-42 lần hai -> unique constraint, không reserve stock nữa
~~~

Nếu consumer dùng Kafka offset làm idempotency key, duplicate ở offset 125 sẽ không được nhận diện. Vì vậy, **business event ID** ổn định mới là dedup key quan trọng.

Một event ID cần có scope uniqueness phù hợp. Nếu hệ thống đa tenant, có thể dùng khóa (tenant_id, event_id, consumer_name) tùy contract.

## 20. Idempotency của HTTP command tạo outbox

Không chỉ Kafka publisher có thể retry; HTTP client cũng có thể gửi lại CreateOrder khi response timeout sau DB commit.

Nếu mỗi HTTP request tạo một order và một outbox event mới mà không có idempotency key, client retry có thể tạo **hai đơn hàng hợp lệ riêng biệt**.

Khi API yêu cầu create-once, dùng request ID/idempotency key:

~~~sql
CREATE TABLE command_dedup (
    request_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong cùng database transaction, service kiểm tra/insert request ID bằng unique constraint; nếu request đã được xử lý, trả lại order ID tương ứng thay vì tạo order mới và phát event mới.

Outbox giúp nhất quán giữa order row và event intent, nhưng không tự chống duplicate do **client gửi lại command**.

## 21. Cleanup và retention

Outbox bảng chỉ tăng mà không cleanup sẽ gây:

- Storage và index tăng liên tục.
- Polling query chậm.
- Backup/vacuum/maintenance tốn tài nguyên.
- Thời gian restore database kéo dài.

Với polling publisher, thường chỉ cleanup **SENT rows** đã qua retention an toàn. Không xóa NEW, IN_PROGRESS chưa hồi phục hoặc FAILED/NEEDS_ATTENTION chưa được xử lý.

Ví dụ:

~~~sql
DELETE FROM outbox_events
WHERE status = 'SENT'
  AND published_at < now() - INTERVAL '7 days';
~~~

Retention 7 ngày chỉ là ví dụ. Cần tính đến:

- Thời gian điều tra/replay.
- Kafka retention và consumer lag downstream.
- Backup/snapshot và yêu cầu audit.
- Nguy cơ một outbox row bị đánh dấu SENT sai.
- Các yêu cầu pháp lý hoặc dữ liệu nhạy cảm.

Với CDC, tránh xóa/UPDATE outbox rows theo cách làm Event Router phát sự kiện phụ không mong muốn. Nhiều thiết kế CDC dùng insert-only event table và cleanup theo cơ chế được quản trị; phải kiểm tra connector SMT/filter behavior.

## 22. Polling có thể gây mất thứ tự khi batch lớn

Giả sử worker A claim 50 events cũ, worker B claim 50 events mới. Worker B có broker connection nhanh hơn và publish trước worker A.

Khi đó Kafka log nhận các event mới trước, dù created_at của chúng lớn hơn.

Nếu thứ tự toàn cục không bắt buộc, hệ thống có thể chấp nhận. Nếu cần thứ tự theo aggregate:

- Claim theo aggregate để không có hai event cùng aggregate in-flight.
- Gửi events của một aggregate theo aggregate_version.
- Có optimistic version check ở consumer.
- Đánh giá việc dùng CDC để bám commit-log order.
- Không giả định Kafka bảo toàn thứ tự DB khi publisher phát song song.

Một retry của version cũ cũng cần được xét: nếu version 1 publish fail, version 2 có được phép gửi hay phải chờ? Trả lời dựa trên contract của downstream, không dựa trên mong muốn throughput.

## 23. Outbox và microservice saga

Outbox giải quyết một đoạn của workflow phân tán, nhưng không giải quyết toàn bộ:

~~~text
Order Service:
   DB commit OrderCreated + outbox event
      |
      v
Kafka
      |
      v
Inventory Service:
   DB reserve + outbox InventoryReserved
      |
      v
Kafka
      |
      v
Billing Service:
   Charge payment + outbox PaymentAuthorized
~~~

Mỗi service dùng outbox để bảo đảm event intent gắn với local database commit. Nhưng nếu Inventory thành công còn Billing thất bại, workflow cần **saga/compensation** hoặc state machine quyết định hủy reserve, retry charge, chuyển sang manual review.

Outbox không phải distributed transaction xuyên ba service; nó là building block giúp mỗi service phát event đáng tin cậy từ local transaction.

## 24. Bảo mật và chất lượng event payload

Payload outbox có thể tồn tại đồng thời ở database, Kafka và DLT. Không nên copy mọi cột trong business entity vào event nếu không cần.

Các thực hành hữu ích:

- Chỉ đưa các trường downstream cần.
- Đánh dấu schema version và event type.
- Không chứa password, token, secret hoặc dữ liệu nhạy cảm không cần thiết.
- Áp dụng ACL và encryption cho database/outbox/topic.
- Không log raw payload khi publish thất bại.
- Có chính sách retention/xóa phù hợp.
- Kiểm tra giới hạn kích thước record Kafka ngay khi xây dựng outbox payload.
- Chuẩn hóa timestamps/time zone để consumer hiểu đúng.

Nếu event phải tuân theo Avro/JSON Schema/Protobuf contract, có thể validate payload trước DB commit. Nếu serialize/validate thất bại, rollback cả business write và outbox write thay vì để publisher gặp permanent poison row.

## 25. Observability: theo dõi cả ba chặng

Đừng chỉ nhìn số Kafka records published. Một dashboard outbox nên theo dõi:

| Metric/tín hiệu | Câu hỏi |
|---|---|
| Outbox inserts/sec | Nghiệp vụ tạo event intent với tốc độ nào? |
| Pending outbox rows | Bao nhiêu event chưa publish? |
| Oldest pending age | Event cũ nhất chờ bao lâu? |
| Claimed/in-progress count | Bao nhiêu row đang được publisher xử lý? |
| Expired leases count | Có worker chết hoặc publish kéo dài không? |
| Publish success/sec | Có event thực sự được broker xác nhận không? |
| Publish failure theo exception | Lỗi broker, ACL, serializer hay topic? |
| Retry attempts/backoff | Có retry storm hoặc row bị kẹt không? |
| Outbox → Kafka publish latency | Mất bao lâu từ DB commit đến Kafka ack? |
| CDC connector lag | WAL/binlog và Connect có đang chậm không? |
| Kafka topic consumer lag | Downstream xử lý có kịp không? |
| Consumer dedup hits | Bao nhiêu duplicate được bảo vệ? |
| Business completion latency | Mất bao lâu đến khi nghiệp vụ downstream hoàn tất? |

Đặc biệt, **oldest pending age** thường quan trọng hơn số lượng pending. Một pending row sau outage 2 giây có thể chấp nhận được; một row tồn tại chưa gửi 4 giờ cần alert dù pending count thấp.

Alert cần có owner, threshold theo SLO và runbook. Không đưa eventId vào metric label có cardinality cao; ghi eventId vào log/trace cùng correlation ID.

## 26. Runbook: outbox backlog tăng

Khi outbox pending tăng hoặc tuổi event vượt SLO:

### Bước 1: Khoanh vùng

- Polling hay CDC đang được sử dụng?
- Backlog thuộc một tenant/topic/aggregate hay toàn bộ publisher?
- Outbox inserts/sec và publish success/sec khác nhau thế nào?
- Kafka producer có nhận acknowledgement không?

### Bước 2: Kiểm tra database

- Query ready rows có dùng index không?
- Có lock contention, long-running DB transaction hoặc connection pool exhaustion không?
- Có nhiều IN_PROGRESS leases hết hạn không?
- Table/index size và vacuum/maintenance có vấn đề không?

### Bước 3: Kiểm tra Kafka

- Topic đích có tồn tại không?
- ACL producer cho topic có đúng không?
- Leader, ISR và broker health thế nào?
- Producer có serialization, record-too-large hoặc timeout không?
- Kafka key/event schema có đúng contract không?

### Bước 4: Kiểm tra publisher

- Có process/worker nào đã chết hoặc bị pause?
- Lease expiry có đủ dài cho producer timeout không?
- Worker có retry row lỗi vô hạn và chặn rows khác không?
- Có concurrency quá cao tạo reorder hoặc quá tải broker không?

### Bước 5: Khôi phục có kiểm soát

- Sửa ACL/topic/serializer/DB issue.
- Retry những row vẫn còn intent, giữ nguyên eventId.
- Giới hạn tốc độ xả backlog để không làm downstream quá tải.
- Theo dõi publish success rate và oldest age giảm.

### Bước 6: Kiểm tra hậu quả duplicate và ordering

- Có Kafka send thành công nhưng DB markSent thất bại không?
- Downstream có idempotency và consumer lag ổn định không?
- Aggregate version có bị out-of-order không?
- Có business reconciliation hoặc manual correction cần thiết không?

## 27. Runbook: Kafka đã có event nhưng status vẫn NEW

Triệu chứng: eventId E-42 xuất hiện trong Kafka, nhưng outbox row E-42 chưa SENT. Đây là cửa sổ lỗi đã dự kiến của at-least-once publisher.

Hành động:

1. Xác nhận eventId và aggregateId trên Kafka record.
2. Kiểm tra publisher logs quanh send/ack/markSent.
3. Không xóa outbox row bằng tay khi chưa hiểu trạng thái.
4. Nếu cho publisher retry, giữ nguyên eventId để consumer dedup.
5. Kiểm tra downstream đã thực hiện side effect chưa.
6. Nếu cần reconcile trạng thái, ghi nhận bằng quy trình có audit.

Đừng sửa publisher thành “mark SENT ngay sau send()” để tránh duplicate: cách đó có thể biến một lần gửi thất bại thành event loss.

## 28. Kiểm thử reliability cho outbox

Các ca kiểm thử đáng có:

### 28.1. Database rollback

Ép business validation hoặc DB constraint thất bại. Xác nhận cả business row và outbox row rollback.

### 28.2. Database commit, Kafka chưa sẵn sàng

Tạo order khi Kafka broker bị tạm ngắt trong môi trường test. Xác nhận order và outbox vẫn commit, outbox pending được giữ, publisher publish thành công sau khi Kafka phục hồi.

### 28.3. Publisher crash trước Kafka send

Claim row rồi dừng publisher trước send. Sau khi lease hết hạn, worker khác reclaim và publish.

### 28.4. Publisher crash sau Kafka ack

Cho Kafka send thành công rồi ép process chết trước markSent. Sau restart, event được publish lại với **cùng eventId**; consumer idempotent không thực hiện side effect lần hai.

### 28.5. Hai publisher cạnh tranh

Hai workers đồng thời claim outbox rows. Xác nhận cơ chế lock/claim không để cùng row active bởi hai workers trong thời gian lease hợp lệ. Kiểm tra reclaim sau lease expired.

### 28.6. Ordering theo aggregate

Tạo OrderCreated(v1), OrderPaid(v2), OrderCancelled(v3) gần nhau. Gây retry v1 và xem publisher/consumer có giữ contract ordering/version hay không.

### 28.7. Permanent publish error

Producer thiếu ACL, serializer sai hoặc topic không tồn tại. Xác nhận row không bị xóa/đánh dấu SENT, alert được phát, và có đường sửa cấu hình/retry.

### 28.8. CDC restart

Với Debezium, dừng connector sau khi đã có event rồi khởi động lại. Xác nhận không mất event intent và consumer chịu được duplicate/snapshot behavior.

Không dùng cluster sản xuất để mô phỏng broker outage, khóa replication slot hoặc xóa topic. Dùng test infrastructure/fault injection có kiểm soát.

## 29. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Ghi business DB rồi Kafka trực tiếp | Dual-write gap và inconsistency | Ghi business row + outbox trong một DB transaction |
| Dùng @TransactionalEventListener như durable queue | Crash sau DB commit có thể mất event intent | Lưu outbox row bền vững |
| Đánh dấu SENT trước Kafka ack | Có thể mất event khi send fail | Chỉ mark sau send result thành công |
| Không có event ID ổn định | Consumer không dedup duplicate | Tạo eventId khi ghi outbox, giữ qua retries |
| Nhiều publishers SELECT mà không lock/claim | Publish duplicate không cần thiết | Lease + SKIP LOCKED/claim phù hợp |
| Giữ DB row lock trong lúc Kafka send | Lock contention và transaction dài | Claim transaction ngắn, send ngoài DB tx |
| Không reclaim IN_PROGRESS | Crash khiến event bị kẹt vĩnh viễn | Lease expiry và recovery |
| Update SENT không kiểm tra claim version | Worker cũ ghi đè state của worker mới | Fencing/version check |
| Coi id auto-increment là DB commit order | Sai ordering dưới concurrency | Version theo aggregate/CDC commit order |
| Dùng key ngẫu nhiên cho cùng aggregate | Events phân tán partitions | Key = aggregateId khi cần ordering |
| Tin outbox đảm bảo exactly-once publication | Crash sau ack trước mark tạo duplicate | Idempotent consumer/inbox |
| Outbox row chỉ có aggregate ID, publisher đọc state mới nhất để tạo event | Event payload không phản ánh thời điểm thay đổi | Lưu snapshot payload trong DB transaction |
| Xóa mọi row cũ | Có thể xóa pending/failed event | Cleanup theo trạng thái và retention |
| Không monitor oldest pending age | Event kẹt dài nhưng count nhỏ | Alert theo age/SLO |
| Chạy polling và CDC trùng nguồn khi cutover | Duplicate hàng loạt | Cutover có checkpoint và dedup |
| Cho rằng Kafka transaction bao gồm outbox status UPDATE | Atomicity không tồn tại giữa hai hệ thống | Chấp nhận at-least-once + idempotency |

## 30. Checklist triển khai Outbox pattern

Trước khi đưa vào production, hãy xác nhận:

1. Business row và outbox row có được ghi trong **cùng một database transaction** không?
2. Nếu transaction rollback, cả hai dữ liệu có cùng rollback không?
3. Event payload có được tạo từ trạng thái nghiệp vụ tại thời điểm transaction không?
4. Mỗi event có eventId ổn định, aggregateId, eventType và schemaVersion không?
5. Publisher là polling hay CDC, và có owner rõ ràng cho vận hành không?
6. Nếu polling, claim/lease có an toàn với nhiều replicas và crash không?
7. Kafka send có chờ acknowledgement trước khi mark SENT không?
8. Nếu send result timeout/ambiguous, publisher có giữ event để retry an toàn không?
9. Nếu Kafka đã nhận event nhưng mark SENT fail, consumer có idempotency không?
10. Kafka key có hỗ trợ ordering theo aggregate khi cần không?
11. Có version/sequence hoặc logic xử lý out-of-order nếu domain yêu cầu không?
12. Có retry/backoff phân biệt lỗi transient và permanent không?
13. Outbox table có index phù hợp và cleanup chỉ xóa record an toàn không?
14. Nếu CDC, replication slot/binlog retention và connector offsets có được monitor không?
15. Downstream có inbox/dedup thực hiện trong cùng database transaction với side effect không?
16. Có metric oldest pending age, publish failures, retry rate và end-to-end business latency không?
17. Có runbook cho Kafka outage, DB lock, serializer/ACL và publisher crash không?
18. Có test failure windows ở cả DB commit, Kafka ack và mark SENT không?
19. Có chính sách bảo mật, dữ liệu nhạy cảm và schema evolution cho outbox payload không?
20. Với workflow nhiều services, saga/compensation có được thiết kế riêng không?

**Kết luận:** Outbox pattern giải quyết lỗ hổng dual write bằng cách lưu business change và ý định phát Kafka event trong cùng database transaction. Publisher polling hoặc CDC chuyển event đã commit sang Kafka với khả năng retry, nhưng có thể gửi duplicate khi crash ở ranh giới Kafka acknowledgement và cập nhật trạng thái outbox. Vì vậy, một triển khai bền vững cần outbox event ID ổn định, publisher có lease/ack/retry an toàn hoặc CDC được vận hành đúng, Kafka key và version phục vụ ordering, consumer idempotency/inbox, cùng dashboard phát hiện backlog. Outbox tạo nền tảng nhất quán dữ liệu giữa Kafka và database theo hướng **eventual, at-least-once và có thể phục hồi**, không phải một cam kết distributed exactly-once tự động.
