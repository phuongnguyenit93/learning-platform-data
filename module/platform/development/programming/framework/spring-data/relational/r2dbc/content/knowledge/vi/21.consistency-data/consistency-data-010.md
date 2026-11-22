# Outbox và bù trừ khi cần phối hợp cơ sở dữ liệu với hệ thống khác

Một nghiệp vụ trong ứng dụng Spring Data R2DBC thường phải thay đổi dữ liệu trong database rồi thông báo cho hệ thống khác. Ví dụ, khi tạo đơn hàng, ứng dụng cần lưu order vào PostgreSQL và gửi sự kiện `OrderCreated` tới message broker để inventory, billing hoặc notification service tiếp tục xử lý.

Nếu ứng dụng ghi database và publish message bằng hai thao tác độc lập, luôn có một khoảng thời gian mà một thao tác thành công còn thao tác kia thất bại. Database có thể commit nhưng broker không nhận được message; hoặc message được gửi đi nhưng transaction database rollback. Đây là bài toán *dual write*.

Transactional Outbox giải quyết phần phối hợp giữa một database transaction và việc phát sự kiện: ứng dụng ghi dữ liệu nghiệp vụ cùng một bản ghi outbox trong cùng transaction R2DBC. Một relay riêng đọc outbox đã commit rồi publish message. Nhờ vậy, nếu transaction commit thì thông tin cần phát đã được lưu bền vững trong database; nếu transaction rollback thì cả dữ liệu nghiệp vụ và outbox đều không tồn tại.

Khi một quy trình đi qua nhiều database hoặc dịch vụ độc lập, local transaction của một service không thể rollback toàn bộ hệ thống. Khi đó cần một quy trình dài hạn như Saga, dùng các bước cục bộ và hành động bù trừ (*compensation*) để đưa nghiệp vụ về trạng thái chấp nhận được khi một bước thất bại.

Outbox và Saga giải quyết hai vấn đề liên quan nhưng khác nhau: Outbox bảo đảm sự kiện được chuyển tiếp đáng tin cậy từ một local database; Saga điều phối nhiều bước nghiệp vụ qua các resource độc lập và xử lý thất bại bằng hành động bù hoặc forward recovery.

## 1. Bài toán dual write

Giả sử một API tạo đơn hàng cần:

1. Insert order vào database.
2. Publish `OrderCreated` lên broker.

Code tưởng như đơn giản:

```java
return orderRepository.save(order)
        .flatMap(saved -> eventPublisher.publish(
                new OrderCreated(saved.id(), saved.orderCode()))
                .thenReturn(saved));
```

Hai thao tác này không tự động trở thành một transaction nguyên tử. Database transaction chỉ quản lý resource database; broker có thể là một hệ thống khác với protocol và transaction boundary riêng.

### 1.1. Database commit nhưng publish thất bại

```text
Application                 Database                Message broker
    |                           |                          |
    |---- INSERT order -------> |                          |
    |---- COMMIT ------------> |                          |
    |                           |                          |
    |---- publish event ---------------------------------> X
    |                           |                    network/error
```

Order đã tồn tại nhưng không có event. Inventory hoặc billing không biết đơn hàng mới được tạo. Nếu API trả lỗi và client retry, ứng dụng có thể tạo thêm đơn hàng trùng nếu không có idempotency key.

### 1.2. Publish thành công nhưng database rollback

```text
Application                 Database                Message broker
    |                           |                          |
    |---- publish event ---------------------------------> |
    |                           |                    accepted
    |---- INSERT order -------> |
    |---- COMMIT ------------> X
    |                      constraint/error                |
```

Consumer nhận `OrderCreated` nhưng không tìm thấy order trong database. Đây là một sự kiện mô tả trạng thái chưa từng được commit.

### 1.3. Vì sao không chỉ dùng @Transactional?

`@Transactional` với `R2dbcTransactionManager` quản lý transaction trên `ConnectionFactory` được cấu hình. Nó không tự bao trùm một message broker hoặc HTTP service khác.

Ngay cả khi code publish nằm bên trong method có `@Transactional`, việc gửi message không tự rollback khi database transaction thất bại. Ngược lại, database rollback cũng không thu hồi message broker đã chấp nhận.

Có những hệ thống hỗ trợ distributed transaction hoặc transaction protocol xuyên nhiều resource, nhưng không nên giả định một R2DBC transaction thông thường cung cấp atomic commit cho database và broker. Với kiến trúc service hiện đại, Outbox và Saga thường dễ vận hành hơn việc cố ghép nhiều resource vào một transaction phân tán.

## 2. Transactional Outbox hoạt động như thế nào?

Outbox là một bảng trong cùng database với dữ liệu nghiệp vụ. Trong một transaction, ứng dụng ghi:

- Bản ghi nghiệp vụ, ví dụ `orders`.
- Bản ghi sự kiện cần phát, ví dụ `outbox_events`.

Sau khi transaction commit, một relay đọc các bản ghi outbox chưa gửi và publish chúng tới broker. Khi broker xác nhận publish thành công, relay đánh dấu bản ghi đã gửi.

```text
HTTP request
    |
    v
Reactive service
    |
    |---- R2DBC transaction ---------------------------+
    |                                                  |
    |   INSERT orders                                  |
    |   INSERT outbox_events                           |
    |                                                  |
    +---------------- COMMIT --------------------------+
                                                       |
                                                       v
                                                Outbox relay
                                                       |
                                                       v
                                                Message broker
                                                       |
                                                       v
                                                Consumer services
```

Nếu transaction rollback, cả order và outbox event đều rollback. Nếu commit thành công nhưng ứng dụng chết trước khi publish, outbox row vẫn còn và relay có thể gửi sau khi khởi động lại.

### 2.1. Outbox bảo đảm điều gì?

Với điều kiện dữ liệu nghiệp vụ và outbox row được ghi trong cùng local transaction:

- Không có order commit mà thiếu outbox record tương ứng do lỗi giữa hai câu INSERT.
- Không có outbox event commit khi bản ghi nghiệp vụ cùng transaction đã rollback.
- Relay có thể tiếp tục sau restart vì trạng thái pending được lưu bền vững.
- Có thể retry publish mà không cần client thực hiện lại nghiệp vụ tạo order.

Outbox không tự bảo đảm message chỉ được giao đúng một lần. Một relay có thể publish thành công rồi chết trước khi đánh dấu `PUBLISHED`; sau khi lease hết hạn, event có thể được publish lại. Vì vậy, consumer cần idempotency.

### 2.2. Điều kiện quan trọng: cùng database transaction

Order repository và outbox repository phải dùng cùng database resource và cùng reactive transaction manager. Nếu order được ghi qua `ordersConnectionFactory` còn outbox được ghi qua `auditConnectionFactory`, một `R2dbcTransactionManager` không tự tạo atomicity giữa hai connection factory.

Khi outbox nằm trong một database khác, nó không còn giải quyết được dual write theo cách này. Hãy đặt outbox cùng database sở hữu dữ liệu nghiệp vụ hoặc thiết kế Saga/forwarding phù hợp.

## 3. Thiết kế bảng outbox

Một outbox row cần đủ thông tin để relay biết sự kiện nào cần phát, sự kiện thuộc aggregate nào và trạng thái giao nhận hiện tại.

Ví dụ schema PostgreSQL:

```sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    aggregate_sequence BIGINT NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    event_version INTEGER NOT NULL DEFAULT 1,
    payload TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_by UUID,
    locked_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    last_error TEXT,
    CONSTRAINT uq_outbox_aggregate_sequence
        UNIQUE (aggregate_type, aggregate_id, aggregate_sequence),
    CONSTRAINT ck_outbox_status
        CHECK (status IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'DEAD'))
);

CREATE INDEX idx_outbox_pending
    ON outbox_events(next_attempt_at, created_at, id)
    WHERE status = 'PENDING';

CREATE INDEX idx_outbox_expired_lease
    ON outbox_events(locked_until, created_at, id)
    WHERE status = 'PROCESSING';
```

Đây là ví dụ PostgreSQL; kiểu UUID, `TIMESTAMPTZ`, partial index và cú pháp claim ở các phần sau cần được điều chỉnh nếu dùng hệ quản trị khác.

### 3.1. Ý nghĩa các cột

| Cột | Ý nghĩa |
|---|---|
| `id` | ID duy nhất của event; dùng làm idempotency key ở consumer |
| `aggregate_type` | Loại aggregate, ví dụ `Order` |
| `aggregate_id` | ID order/customer/payment mà event mô tả |
| `aggregate_sequence` | Thứ tự event trong một aggregate nếu nghiệp vụ cần ordering |
| `event_type` | Tên sự kiện, ví dụ `OrderCreated` |
| `event_version` | Phiên bản schema của payload |
| `payload` | Snapshot dữ liệu event đã serialize |
| `occurred_at` | Thời điểm sự kiện nghiệp vụ xảy ra |
| `created_at` | Thời điểm outbox row được ghi |
| `status` | `PENDING`, `PROCESSING`, `PUBLISHED` hoặc `DEAD` |
| `attempts` | Số lần relay đã claim/thử xử lý |
| `next_attempt_at` | Thời điểm sớm nhất được retry |
| `locked_by` | Worker đang giữ lease |
| `locked_until` | Hạn lease; quá hạn có thể được worker khác claim |
| `published_at` | Thời điểm relay ghi nhận publish thành công |
| `last_error` | Thông tin lỗi đã được lọc/giới hạn độ dài |

Không phải ứng dụng nào cũng cần tất cả cột. Với workload đơn giản, có thể bắt đầu từ ID, type, payload, timestamps và trạng thái. Nếu có nhiều worker, cần cơ chế claim/lease để tránh cùng xử lý một row đồng thời.

### 3.2. Lưu payload hay chỉ lưu aggregate ID?

Có hai cách phổ biến:

- **Event snapshot:** lưu đầy đủ payload cần consumer sử dụng tại thời điểm sự kiện xảy ra.
- **Pointer event:** chỉ lưu aggregate ID/version, consumer đọc lại dữ liệu hiện tại từ service nguồn.

Snapshot giúp consumer hiểu trạng thái đã xảy ra, kể cả khi order thay đổi sau đó. Pointer event nhỏ hơn nhưng consumer có thể đọc trạng thái mới hơn thay vì trạng thái tại thời điểm event được tạo.

Với event như `OrderCreated`, payload thường nên chứa các dữ liệu cần thiết để consumer xử lý mà không phải gọi ngược service nguồn ngay lập tức. Không serialize toàn bộ entity persistence nếu nó chứa trường nội bộ, secret hoặc dữ liệu không thuộc public event contract.

### 3.3. Version hóa event schema

Thêm `event_version` hoặc version trong envelope để consumer biết cách diễn giải payload. Khi thêm trường mới, ưu tiên thay đổi tương thích: consumer cũ bỏ qua field không biết; producer mới vẫn gửi các field bắt buộc mà consumer cũ cần trong giai đoạn rolling deployment.

Không đổi ý nghĩa của một field hiện hữu mà vẫn giữ nguyên version nếu consumer có thể diễn giải khác nhau. Với thay đổi phá vỡ, phát event type/version mới hoặc dùng upcaster/adapter có kiểm soát.

## 4. Ghi dữ liệu nghiệp vụ và outbox trong cùng R2DBC transaction

Đây là phần bảo đảm atomicity quan trọng nhất. Repository nghiệp vụ và outbox repository phải dùng cùng `ConnectionFactory` và transaction manager.

Ví dụ entity outbox:

```java
@Table("outbox_events")
public record OutboxEventEntity(
        @Id UUID id,
        @Column("aggregate_type") String aggregateType,
        @Column("aggregate_id") String aggregateId,
        @Column("aggregate_sequence") Long aggregateSequence,
        @Column("event_type") String eventType,
        @Column("event_version") Integer eventVersion,
        String payload,
        @Column("occurred_at") Instant occurredAt,
        @Column("created_at") Instant createdAt,
        String status,
        Integer attempts
) {
}
```

Ví dụ service:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final R2dbcEntityTemplate ordersEntityTemplate;
    private final ObjectMapper objectMapper;

    public OrderApplicationService(
            OrderRepository orderRepository,
            R2dbcEntityTemplate ordersEntityTemplate,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.ordersEntityTemplate = ordersEntityTemplate;
        this.objectMapper = objectMapper;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Mono<OrderEntity> placeOrder(CreateOrderCommand command) {
        OrderEntity draft = OrderEntity.from(command);

        return orderRepository.save(draft)
                .flatMap(saved -> {
                    UUID eventId = UUID.randomUUID();
                    Instant occurredAt = Instant.now();

                    return serializeEvent(saved, eventId, occurredAt)
                        .flatMap(payload -> {
                            OutboxEventEntity event = new OutboxEventEntity(
                                    eventId,
                                    "Order",
                                    saved.id().toString(),
                                    saved.version(),
                                    "OrderCreated",
                                    1,
                                    payload,
                                    occurredAt,
                                    occurredAt,
                                    "PENDING",
                                    0);

                            return ordersEntityTemplate.insert(event)
                                    .thenReturn(saved);
                        });
                });
    }

    private Mono<String> serializeEvent(
            OrderEntity order, UUID eventId, Instant occurredAt) {
        return Mono.fromCallable(() -> objectMapper.writeValueAsString(
                new OrderCreatedEvent(
                        eventId,
                        order.id(),
                        order.orderCode(),
                        order.version(),
                        occurredAt)))
                .onErrorMap(JsonProcessingException.class,
                        EventSerializationException::new);
    }
}
```

Đây là code minh họa cấu trúc; constructor, version field và exception class cần khớp domain thực tế. Ví dụ giả định một event được phát cho mỗi aggregate version; nếu một version có nhiều event, hãy dùng sequence riêng cho từng event. `eventId` được tạo một lần rồi dùng cùng ID trong payload và outbox row. Nên inject `Clock` thay cho `Instant.now()` để timestamp có thể kiểm thử. Serialization có thể thực hiện đồng bộ trên payload nhỏ; với payload lớn hoặc serializer blocking, cần cân nhắc tài nguyên và cách thực thi.

### 4.1. Vì sao `flatMap` và `thenReturn` quan trọng?

Publisher lưu outbox phải được kết hợp vào publisher mà method trả về. Nếu gọi `outboxRepository.save(event).subscribe()` bên trong service, thao tác đó tạo subscription độc lập và có thể chạy ngoài transaction gốc.

Trong ví dụ trên, `eventId` được tạo ở ứng dụng trước khi insert. Với entity không có `@Version`, Spring Data có thể dùng ID khác null để nhận diện entity đã tồn tại khi gọi `save`. Dùng `R2dbcEntityTemplate.insert(event)` thể hiện rõ đây luôn là một insert mới. Một lựa chọn khác là triển khai `Persistable`/newness detection phù hợp nếu muốn giữ repository abstraction.

Chuỗi đúng là:

```java
return orderRepository.save(draft)
        .flatMap(saved -> outboxRepository.save(toOutbox(saved))
                .thenReturn(saved));
```

Transaction manager quan sát completion/error của publisher được trả về. Nếu lưu outbox phát lỗi, error signal thoát khỏi pipeline và transaction có thể rollback cả order lẫn outbox.

### 4.2. Không publish broker bên trong transaction ghi order

Không nên giữ database connection/transaction mở trong khi chờ mạng broker:

```java
// Không dùng cách này làm transactional outbox.
return orderRepository.save(order)
        .flatMap(saved -> broker.publish(toEvent(saved))
                .thenReturn(saved));
```

Publish broker không tham gia transaction R2DBC. Nếu broker chậm, connection bị giữ lâu; nếu publish thành công rồi commit database thất bại, consumer vẫn nhận event. Hãy chỉ ghi outbox row trong transaction; relay publish sau khi transaction đã commit.

### 4.3. Xác nhận cùng transaction manager và ConnectionFactory

Ví dụ:

```java
@EnableR2dbcRepositories(
        basePackages = "com.example.orders.repository",
        entityOperationsRef = "ordersEntityTemplate",
        transactionManagerRef = "ordersTransactionManager")
class OrdersR2dbcConfiguration {
}
```

`OrderRepository` và `OutboxEventRepository` phải thuộc cùng nhóm repository, hoặc ít nhất cùng dùng template/resource phù hợp. `ordersEntityTemplate` và `ordersTransactionManager` phải inject cùng bean `ordersConnectionFactory`.

Nếu outbox repository vô tình được scan vào một nhóm database khác, code vẫn có thể compile nhưng atomicity đã mất. Kiểm thử rollback là cách xác nhận quan trọng.

### 4.4. Kiểm tra rollback khi outbox insert lỗi

Tạo integration test làm outbox insert vi phạm constraint hoặc dùng một test double phát lỗi trước khi commit. Sau khi method phát lỗi, đọc order bằng transaction độc lập và xác nhận order không tồn tại.

Test phải dùng database thật và transaction manager đúng cấu hình. Mock repository không chứng minh hai lệnh ghi cùng transaction.

## 5. Thiết kế relay đọc và publish outbox

Relay có nhiệm vụ:

1. Tìm event đến hạn xử lý.
2. Claim event để worker khác không xử lý cùng lúc.
3. Commit trạng thái claim/lease.
4. Publish event tới broker.
5. Khi broker xác nhận, đánh dấu event đã publish.
6. Nếu lỗi, lên lịch retry hoặc chuyển sang trạng thái dead.

Không nên giữ transaction database mở trong suốt thời gian gọi broker. Một cách triển khai là claim batch trong transaction ngắn, commit lease, sau đó publish bên ngoài transaction.

### 5.1. Trạng thái xử lý

| Trạng thái | Ý nghĩa |
|---|---|
| `PENDING` | Chờ publish hoặc đến thời điểm retry |
| `PROCESSING` | Một worker đã claim và đang giữ lease |
| `PUBLISHED` | Broker đã xác nhận và relay đã ghi nhận |
| `DEAD` | Vượt quá số lần thử hoặc lỗi cần xử lý thủ công |

Lease cho phép worker khác lấy lại event nếu worker cũ chết. `locked_until` là hạn sử dụng claim; `locked_by` giúp chỉ worker đang sở hữu claim mới được cập nhật trạng thái.

### 5.2. Claim batch với PostgreSQL

Một cách atomic là dùng `FOR UPDATE SKIP LOCKED` để nhiều worker claim các row khác nhau:

```sql
UPDATE outbox_events AS e
SET status = 'PROCESSING',
    locked_by = :workerId,
    locked_until = CURRENT_TIMESTAMP
        + (:leaseSeconds * INTERVAL '1 second'),
    attempts = e.attempts + 1
FROM (
    SELECT id
    FROM outbox_events
    WHERE (
        status = 'PENDING'
        AND next_attempt_at <= CURRENT_TIMESTAMP
    ) OR (
        status = 'PROCESSING'
        AND locked_until < CURRENT_TIMESTAMP
    )
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
) AS claimed
WHERE e.id = claimed.id
RETURNING e.id, e.aggregate_type, e.aggregate_id,
          e.aggregate_sequence, e.event_type, e.event_version,
          e.payload, e.attempts, e.locked_by;
```

Đây là SQL PostgreSQL cụ thể. `SKIP LOCKED` cho phép worker bỏ qua row đã bị worker khác khóa. `UPDATE ... RETURNING` vừa claim vừa trả dữ liệu để publish. Với database khác, cần dùng cơ chế claim/lease tương đương.

### 5.3. Claim trong transaction ngắn

Ví dụ sử dụng `DatabaseClient`:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<List<ClaimedOutboxEvent>> claimBatch(
        UUID workerId, int batchSize, int leaseSeconds) {

    return databaseClient.sql(CLAIM_SQL)
            .bind("workerId", workerId)
            .bind("batchSize", batchSize)
            .bind("leaseSeconds", leaseSeconds)
            .map((row, metadata) -> new ClaimedOutboxEvent(
                    row.get("id", UUID.class),
                    row.get("event_type", String.class),
                    row.get("aggregate_id", String.class),
                    row.get("payload", String.class),
                    row.get("attempts", Integer.class)))
            .all()
            .collectList();
}
```

Method reactive hoàn tất sau khi lấy batch. Transaction manager commit lease trước khi publisher ngoài method tiếp tục publish. Nếu dùng `DatabaseClient` và `@Transactional`, bảo đảm client dùng cùng `ConnectionFactory` với manager.

Một câu UPDATE là atomic ở database; transaction ngắn vẫn hữu ích để kiểm soát resource và nhất quán khi claim có nhiều statement bổ sung.

### 5.4. Publish sau khi claim đã commit

```java
public Mono<Void> dispatchOnce() {
    return claimService.claimBatch(workerId, 100, 60)
            .flatMapMany(Flux::fromIterable)
            .concatMap(this::publishOne)
            .then();
}

private Mono<Void> publishOne(ClaimedOutboxEvent event) {
    return brokerPublisher.publish(event)
            .then(outboxStore.markPublished(event.id(), workerId))
            .onErrorResume(error -> outboxStore.scheduleRetry(
                    event.id(), workerId, error));
}
```

Ví dụ dùng `concatMap` để xử lý tuần tự trong một worker. Có thể tăng concurrency hữu hạn nếu broker và database chịu được, nhưng cần tính đến ordering theo aggregate và lease duration. `markPublished` nên chỉ cập nhật row nếu `locked_by` vẫn là worker hiện tại; nếu không, worker đã mất lease.

### 5.5. Scheduler và subscription ở ranh giới ứng dụng

`dispatchOnce()` trả về publisher và chỉ chạy khi được subscribe. Có thể dùng scheduler hoặc lifecycle component để tạo một subscription được quản lý ở cấp ứng dụng. Giữ `Disposable` để dừng relay khi shutdown, xử lý lỗi từng vòng polling và tránh tạo nhiều subscription trùng lặp.

Không gọi `subscribe()` bên trong business service để tách một thao tác khỏi transaction. Relay là một tiến trình nền độc lập nên cần một subscription gốc do lifecycle của nó sở hữu.

## 6. Xử lý lỗi, retry và dead-letter state

Publish có thể thất bại vì broker tạm thời không truy cập được, timeout, authentication, quota hoặc payload không hợp lệ. Relay cần phân biệt lỗi có thể retry và lỗi cần can thiệp.

### 6.1. Retry với exponential backoff

Một lịch retry thường dùng:

```text
delay = min(maxDelay, baseDelay * 2^(attempt - 1)) + jitter
```

Ví dụ:

| Attempt | Delay cơ sở minh họa |
|---:|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |

Jitter giúp nhiều worker không retry đồng loạt sau một sự cố broker. Giá trị thực tế cần dựa trên SLA, timeout và năng lực broker.

### 6.2. Cập nhật trạng thái retry

Ví dụ SQL PostgreSQL:

```sql
UPDATE outbox_events
SET status = CASE
        WHEN attempts >= :maxAttempts THEN 'DEAD'
        ELSE 'PENDING'
    END,
    next_attempt_at = CURRENT_TIMESTAMP
        + (:delaySeconds * INTERVAL '1 second'),
    locked_by = NULL,
    locked_until = NULL,
    last_error = :safeError
WHERE id = :eventId
  AND status = 'PROCESSING'
  AND locked_by = :workerId;
```

Điều kiện `locked_by` tránh worker cũ cập nhật row sau khi lease đã được worker khác claim. `safeError` nên được rút gọn và loại bỏ credential/PII; không lưu stack trace khổng lồ vào bảng outbox.

### 6.3. Mark published chỉ sau broker acknowledgement

Chỉ chuyển `PUBLISHED` sau khi broker client báo publish thành công theo semantics của nó. Nếu đánh dấu trước khi gửi, process có thể chết sau update và event bị mất.

Tuy nhiên, nếu broker đã nhận event nhưng ứng dụng chết trước khi đánh dấu, relay sẽ gửi lại sau khi lease hết hạn. Đây là duplicate có chủ đích trong mô hình at-least-once.

### 6.4. Dead-letter và vận hành thủ công

Event chuyển `DEAD` sau số lần thử tối đa hoặc khi lỗi được phân loại là không thể retry. Cần có công cụ vận hành để:

- Xem event type, aggregate ID, event ID và lỗi đã redact.
- Xem số lần thử và thời điểm thử gần nhất.
- Xác minh consumer/broker đã nhận event hay chưa nếu có thể.
- Retry lại sau khi sửa nguyên nhân.
- Đánh dấu bỏ qua chỉ khi nghiệp vụ cho phép và có audit record.

Không xóa event dead ngay lập tức. Nó là bằng chứng cho một nghiệp vụ chưa được chuyển tiếp và có thể cần điều tra.

### 6.5. Lease duration và heartbeat

Lease phải dài hơn thời gian xử lý dự kiến của một event/batch hoặc được gia hạn khi worker còn làm việc. Nếu lease quá ngắn, worker khác có thể claim event trong khi worker cũ vẫn đang publish. Điều đó tăng duplicate.

Với publish chậm, có thể gia hạn lease định kỳ bằng update có điều kiện theo `locked_by`. Nếu worker chết, lease vẫn hết hạn và event được thu hồi. Consumer idempotency vẫn là lớp bảo vệ cuối cùng.

## 7. Delivery semantics: at-least-once và idempotency

Outbox relay thông thường cung cấp *at-least-once delivery*: event có thể được giao một hoặc nhiều lần, nhưng relay tiếp tục thử cho tới khi thành công hoặc chuyển trạng thái cần xử lý.

Không nên quảng cáo exactly-once end-to-end chỉ vì broker có transaction hoặc outbox có unique ID. Từ database tới relay, broker, consumer và database đích là nhiều boundary. Một crash ở đúng thời điểm có thể khiến event được giao lại.

### 7.1. Dùng event ID ổn định

Mỗi event cần ID duy nhất được tạo lúc ghi outbox. Khi retry, relay gửi lại cùng event ID, không tạo ID mới. Consumer dùng ID đó để nhận biết duplicate.

Envelope có thể gồm:

```json
{
  "eventId": "8e4f9e10-7b0f-4a2d-9c6a-9a4b6d8d5f10",
  "eventType": "OrderCreated",
  "eventVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "order-1042",
  "aggregateSequence": 1,
  "occurredAt": "2026-11-15T08:30:00Z",
  "payload": {
    "orderCode": "ORD-001042",
    "totalAmount": "250000.00"
  }
}
```

Đây là payload minh họa. Chọn kiểu ID, timestamp và decimal encoding theo contract thực tế. Với tiền tệ, decimal string thường tránh lỗi biểu diễn binary floating point ở JSON consumer.

### 7.2. Bảng inbox/processed message ở consumer

Consumer có thể lưu event đã xử lý trong cùng database với thay đổi nghiệp vụ:

```sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(120) NOT NULL,
    message_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, message_id)
);
```

Khi nhận event, consumer thực hiện trong một transaction:

1. Insert `(consumer_name, message_id)`.
2. Nếu key đã tồn tại, coi event là duplicate và bỏ qua xử lý nghiệp vụ.
3. Nếu insert mới thành công, cập nhật dữ liệu nghiệp vụ.
4. Ghi outbox event tiếp theo nếu cần phát event khác.
5. Commit transaction.
6. Chỉ acknowledge message sau khi transaction hoàn tất thành công theo cơ chế của broker integration.

### 7.3. Insert idempotency key an toàn

Với PostgreSQL:

```sql
INSERT INTO processed_messages (consumer_name, message_id)
VALUES (:consumerName, :messageId)
ON CONFLICT DO NOTHING;
```

Kiểm tra `rowsUpdated`: nếu bằng 1, message mới; nếu bằng 0, message đã được xử lý. Cách này tránh cố insert duplicate rồi bắt constraint exception trong transaction PostgreSQL, vì một constraint violation có thể làm transaction hiện tại ở trạng thái lỗi cho tới rollback.

### 7.4. Consumer xử lý và inbox trong cùng transaction

```java
@Transactional(transactionManager = "inventoryTransactionManager")
public Mono<Void> handle(OrderCreatedEvent event) {
    return inboxStore.recordIfNew("inventory", event.eventId())
            .flatMap(isNew -> {
                if (!isNew) {
                    return Mono.empty();
                }

                return inventoryService.reserveFor(event)
                        .then();
            });
}
```

`recordIfNew` phải thực hiện insert idempotency key qua cùng database/ConnectionFactory với thao tác inventory. Nếu consumer ghi inbox ở một database rồi inventory ở database khác, atomicity lại bị mất.

### 7.5. Acknowledge sau commit

Nếu message bị acknowledge trước khi transaction consumer commit, process có thể chết sau ack nhưng trước commit; broker không gửi lại và thay đổi nghiệp vụ bị mất. Nếu commit xong nhưng ack thất bại, broker gửi lại; inbox dedup xử lý duplicate an toàn.

Chi tiết ack phụ thuộc broker và framework integration. Hãy xác nhận reactive listener chỉ ack khi publisher hoàn tất thành công và transaction đã commit.

## 8. Ordering và event sequence

Không phải mọi event đều cần thứ tự toàn cục. Nhưng một aggregate có thể yêu cầu event được xử lý theo thứ tự, ví dụ:

```text
OrderCreated (sequence 1)
OrderPaid    (sequence 2)
OrderShipped (sequence 3)
```

Nếu `OrderShipped` đến trước `OrderPaid`, consumer có thể chuyển state sai.

### 8.1. Tạo sequence theo aggregate

Có thể dùng version của aggregate hoặc một sequence riêng tăng trong cùng transaction. Unique constraint `(aggregate_type, aggregate_id, aggregate_sequence)` ngăn tạo hai event cùng sequence.

Không dùng timestamp đơn thuần làm thứ tự tuyệt đối: hai event có thể cùng timestamp hoặc clock khác nhau giữa instance.

### 8.2. Partition key ở broker

Nếu broker hỗ trợ partitioning theo key, dùng `aggregate_id` làm partition key để các event cùng aggregate được đưa vào cùng partition. Điều này giúp bảo toàn thứ tự trong phạm vi partition theo semantics broker.

Partition key không tự bảo đảm relay publish đúng sequence nếu nhiều worker claim và publish song song. Cần giới hạn một event đang xử lý cho mỗi aggregate hoặc thiết kế consumer phát hiện sequence gap.

### 8.3. Xử lý sequence gap ở consumer

Consumer có thể lưu last processed sequence theo aggregate. Khi nhận sequence lớn hơn sequence kế tiếp, tạm giữ/retry event hoặc yêu cầu replay event bị thiếu. Khi nhận sequence cũ đã xử lý, bỏ qua theo idempotency.

Chiến lược này tăng độ phức tạp; chỉ áp dụng nếu ordering là invariant nghiệp vụ. Với nhiều event độc lập, không cần tuần tự hóa toàn bộ relay.

## 9. Outbox cleanup và retention

Outbox table tăng liên tục. Cần xác định thời gian giữ event đã publish và chính sách lưu event dead.

### 9.1. Không xóa ngay sau publish

Giữ published event trong một khoảng thời gian để:

- Điều tra event đã phát.
- Đối chiếu với broker/consumer.
- Retry hoặc replay theo quy trình vận hành.
- Phân tích duplicate và delivery latency.

Sau retention period, có thể archive hoặc xóa theo batch. Không chạy một lệnh delete khổng lồ trong giờ cao điểm nếu bảng lớn.

### 9.2. Cleanup theo batch

Ví dụ PostgreSQL:

```sql
DELETE FROM outbox_events
WHERE id IN (
    SELECT id
    FROM outbox_events
    WHERE status = 'PUBLISHED'
      AND published_at < CURRENT_TIMESTAMP - INTERVAL '14 days'
    ORDER BY published_at
    LIMIT 1000
);
```

Chạy lặp lại theo batch cho đến khi hết dữ liệu đủ tuổi. Thời gian retention 14 ngày chỉ là ví dụ; chọn theo yêu cầu audit, replay và dung lượng.

### 9.3. Archive dead events

Dead events cần retention dài hơn hoặc được archive riêng cho tới khi có quyết định vận hành. Nếu xóa dead event mà không có audit record, tổ chức có thể mất khả năng chứng minh vì sao downstream chưa xử lý một nghiệp vụ.

### 9.4. Partitioning khi volume lớn

Với outbox volume cao, cân nhắc partition theo thời gian hoặc chiến lược archive phù hợp database. Thiết kế partition key phải tương thích unique constraint và cách relay claim event. Không thêm partitioning trước khi đo volume và chi phí thực tế.

## 10. Observability cho outbox relay

Outbox có thể âm thầm tích backlog nếu relay dừng hoặc broker không sẵn sàng. Theo dõi ít nhất:

- Số row `PENDING`, `PROCESSING`, `PUBLISHED`, `DEAD`.
- Tuổi của event pending lâu nhất.
- Thời gian từ `occurred_at` tới `published_at`.
- Số attempt trung bình và phân bố retry.
- Số lease hết hạn và event được reclaim.
- Publish success/failure rate.
- Batch size, poll duration và relay throughput.
- Consumer lag và duplicate rate nếu broker cung cấp.

### 10.1. Cảnh báo backlog

Một số alert hữu ích:

- Pending count tăng liên tục.
- Event pending lâu hơn SLA.
- Dead event xuất hiện hoặc tăng nhanh.
- Lease hết hạn liên tục.
- Relay không publish được trong khoảng thời gian quy định.
- Publish latency tăng cao.

Chỉ theo dõi số lượng pending có thể không đủ; một event quan trọng có thể bị kẹt dù tổng backlog nhỏ. Theo dõi oldest pending age.

### 10.2. Correlation và tracing

Đưa `eventId`, `aggregateId`, `correlationId`, trace context và saga ID vào envelope/log theo chính sách. Không đưa access token hoặc secret vào payload. Khi relay publish, tạo span producer và truyền trace context qua header theo chuẩn instrumentation của broker.

## 11. Khi nào cần Saga và compensation?

Outbox giải quyết việc chuyển event từ một local database tới broker một cách đáng tin cậy. Nó không làm cho nhiều database cùng commit/rollback nguyên tử.

Ví dụ tạo đơn hàng có thể gồm:

1. Order service tạo order.
2. Inventory service giữ hàng.
3. Payment service authorize hoặc capture tiền.
4. Shipping service tạo lệnh giao hàng.

Mỗi service sở hữu database riêng. Nếu bước payment thất bại sau khi inventory đã giữ hàng, không thể rollback transaction database của inventory bằng transaction manager của order service. Cần một hành động nghiệp vụ bù trừ: giải phóng hàng đã giữ.

Saga là một chuỗi local transaction, trong đó mỗi bước có thể phát sự kiện/command tiếp theo. Khi một bước thất bại, Saga kích hoạt compensation cho các bước đã hoàn thành theo quy tắc nghiệp vụ.

### 11.1. Saga không phải distributed rollback

Compensation không xóa lịch sử như thể thao tác chưa từng xảy ra. Nó tạo một hành động nghiệp vụ mới để giảm hoặc đảo tác động của hành động trước.

Ví dụ:

| Hành động đã hoàn tất | Hành động bù trừ có thể dùng |
|---|---|
| Reserve inventory | Release reservation |
| Authorize payment | Void authorization |
| Capture payment | Refund payment |
| Create shipment label | Cancel label nếu carrier cho phép |
| Send email | Không thể thu hồi; có thể gửi thông báo đính chính |
| Ship package | Có thể cần quy trình return; không thể “rollback” việc đã giao |

Một số hành động không thể bù trừ hoàn toàn. Khi đó cần forward recovery, manual intervention hoặc trạng thái nghiệp vụ thể hiện rõ việc xử lý chưa hoàn tất.

### 11.2. Khi nào chỉ cần Outbox?

Dùng Outbox khi một service cập nhật database của chính nó và cần phát event tới broker. Ví dụ:

- Tạo customer rồi phát `CustomerRegistered`.
- Cập nhật order rồi phát `OrderStatusChanged`.
- Ghi inventory adjustment rồi thông báo warehouse system.

Nếu không có chuỗi nhiều bước cần điều phối hoặc compensation, không cần thêm Saga chỉ để publish một event.

### 11.3. Khi nào cần Saga?

Cân nhắc Saga khi:

- Một nghiệp vụ kéo dài qua nhiều service/database.
- Mỗi bước có thể commit độc lập.
- Không có distributed transaction phù hợp.
- Thất bại ở bước sau cần hành động bù cho bước trước.
- Cần timeout, retry, theo dõi tiến độ và trạng thái nghiệp vụ trung gian.

## 12. Orchestration và choreography

Hai kiểu triển khai Saga thường gặp:

### 12.1. Orchestration

Một Saga orchestrator/process manager lưu trạng thái và quyết định bước tiếp theo.

```text
              Saga Orchestrator
                     |
          +----------+----------+
          |          |          |
          v          v          v
      Inventory   Payment    Shipping
      Service     Service    Service
```

Orchestrator gửi command, nhận kết quả, cập nhật saga state và quyết định tiếp tục hoặc compensation.

Ưu điểm:

- Luồng nghiệp vụ nhìn thấy ở một nơi.
- Timeout, retry và compensation dễ điều phối.
- Có thể quan sát trạng thái saga tập trung.

Nhược điểm:

- Orchestrator có thêm trách nhiệm và cần được vận hành bền vững.
- Nếu thiết kế quá tập trung, thay đổi workflow có thể làm orchestrator phức tạp.

### 12.2. Choreography

Các service phản ứng với event của nhau mà không có một orchestrator trung tâm:

```text
OrderCreated
    |
    v
InventoryReserved
    |
    v
PaymentAuthorized
    |
    v
ShipmentCreated
```

Mỗi service cập nhật database cục bộ và phát event tiếp theo qua outbox.

Ưu điểm:

- Service ít phụ thuộc trực tiếp vào nhau.
- Không cần một coordinator điều khiển mọi bước.

Nhược điểm:

- Luồng tổng thể phân tán qua nhiều consumer.
- Khó quan sát trạng thái khi có nhiều nhánh.
- Compensation và timeout có thể khó hiểu nếu event choreography không được tài liệu hóa.

### 12.3. Chọn cách nào?

Workflow ngắn, ít nhánh có thể phù hợp choreography. Workflow có nhiều bước, timeout, compensation hoặc yêu cầu hiển thị trạng thái tiến trình thường dễ quản lý hơn với orchestration. Có thể kết hợp cả hai, nhưng cần một nguồn sự thật rõ cho saga state.

## 13. Thiết kế Saga state và compensation

Một saga cần ID ổn định, trạng thái hiện tại, dữ liệu cần tiếp tục sau restart và lịch sử bước.

Ví dụ bảng:

```sql
CREATE TABLE saga_instances (
    saga_id UUID PRIMARY KEY,
    saga_type VARCHAR(100) NOT NULL,
    business_key VARCHAR(120) NOT NULL,
    status VARCHAR(30) NOT NULL,
    current_step VARCHAR(100) NOT NULL,
    state_payload TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

CREATE TABLE saga_step_history (
    id UUID PRIMARY KEY,
    saga_id UUID NOT NULL REFERENCES saga_instances(saga_id),
    step_name VARCHAR(100) NOT NULL,
    action_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    command_id UUID,
    result_payload TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Tên trạng thái có thể gồm `STARTED`, `RUNNING`, `COMPENSATING`, `COMPLETED`, `FAILED`, `MANUAL_REVIEW`. Quy ước phải rõ và transition được kiểm soát.

### 13.1. Ví dụ state machine

```text
STARTED
   |
   v
RESERVING_INVENTORY
   |
   +---- failure --------------------+
   |                                 |
   v                                 v
AUTHORIZING_PAYMENT             FAILED
   |
   +---- failure --------------------+
   |                                 |
   v                                 v
CREATING_SHIPMENT             COMPENSATING_INVENTORY
   |                                 |
   v                                 v
COMPLETED                       COMPENSATED
```

Đây chỉ là luồng rút gọn. Thực tế có thể cần trạng thái compensation payment, retry, timeout và manual review.

### 13.2. Compensation theo thứ tự ngược

Nếu các bước đã hoàn tất theo thứ tự A → B → C và bước D thất bại, thường bù theo C → B → A. Tuy nhiên, thứ tự cụ thể phụ thuộc dependency nghiệp vụ. Một compensation có thể thất bại và phải retry độc lập.

### 13.3. Compensation phải idempotent

Nếu command `ReleaseReservation` được gửi hai lần, inventory không được giải phóng hai lần theo cách làm sai số lượng. Dùng command ID/saga ID làm idempotency key, kiểm tra trạng thái reservation và ghi inbox cùng transaction với thay đổi tồn kho.

### 13.4. Timeout không đồng nghĩa bước trước thất bại

Một service có thể đã commit nhưng response/event bị trễ hoặc mất. Khi orchestrator timeout, không được mặc định thao tác chưa xảy ra. Cần truy vấn trạng thái theo command ID/idempotency key hoặc gửi command bù trừ có khả năng nhận biết trạng thái hiện tại.

## 14. Outbox và Inbox trong từng service của Saga

Mỗi service tham gia Saga nên dùng local transaction để:

- Ghi thay đổi nghiệp vụ.
- Ghi inbox record để deduplicate command/event nhận được.
- Ghi outbox event/response cần phát tiếp.

```text
Incoming event/command
          |
          v
       Consumer
          |
          |---- local R2DBC transaction ----------------+
          |                                             |
          |  INSERT inbox message (dedupe)              |
          |  UPDATE local business state                |
          |  INSERT next outbox event                   |
          |                                             |
          +---------------- COMMIT ---------------------+
                                                        |
                                                        v
                                                 Local outbox relay
                                                        |
                                                        v
                                                    Broker
```

Ví dụ Inventory service nhận `ReserveInventory`:

1. Insert inbox key `(inventory, commandId)`.
2. Nếu đã tồn tại, bỏ qua duplicate.
3. Kiểm tra và reserve hàng trong local database transaction.
4. Ghi `InventoryReserved` hoặc `InventoryReservationRejected` vào outbox.
5. Commit.
6. Ack command sau commit.

Nếu reserve thất bại vì không đủ hàng, đó có thể là kết quả nghiệp vụ hợp lệ chứ không phải lỗi kỹ thuật cần retry vô hạn. Service phát event rejected để orchestrator quyết định hủy hoặc bù trừ các bước trước.

## 15. Ví dụ Saga đặt hàng

Giả sử quy trình gồm:

1. Order service tạo order ở trạng thái `PENDING`.
2. Inventory service reserve hàng.
3. Payment service authorize payment.
4. Shipping service tạo shipment.
5. Order service chuyển order sang `CONFIRMED`.

### 15.1. Khởi tạo Saga trong Order service

Trong một transaction của order database:

- Insert order `PENDING`.
- Insert saga instance `STARTED`.
- Insert outbox command/event `ReserveInventory`.
- Commit.

Relay publish command sau commit. Nếu broker tạm thời không sẵn sàng, outbox giữ command để retry.

### 15.2. Inventory service xử lý

Trong transaction inventory database:

- Deduplicate command bằng inbox.
- Reserve số lượng nếu đủ.
- Ghi outbox `InventoryReserved` hoặc `InventoryRejected`.
- Commit rồi ack message.

### 15.3. Payment service xử lý

Khi nhận `InventoryReserved`, payment service authorize payment. Nếu thành công, ghi `PaymentAuthorized`; nếu thất bại, ghi `PaymentRejected`. Payment request phải có idempotency key để retry không tạo charge/authorization trùng.

### 15.4. Shipping service xử lý

Khi payment đã được authorize, shipping service tạo shipment. Nếu thành công, phát `ShipmentCreated`. Nếu thất bại, Saga có thể bắt đầu compensation.

### 15.5. Compensation khi payment thất bại

Nếu inventory đã reserve nhưng payment bị từ chối:

1. Orchestrator chuyển saga sang `COMPENSATING`.
2. Gửi `ReleaseInventory` với command ID ổn định.
3. Inventory service xử lý idempotently và phát `InventoryReleased`.
4. Orchestrator cập nhật order sang `PAYMENT_FAILED` hoặc trạng thái nghiệp vụ phù hợp.
5. Saga kết thúc `COMPENSATED` hoặc `FAILED` theo quy ước.

Order không nhất thiết bị xóa. Giữ trạng thái và lịch sử để audit, hỗ trợ khách hàng và xử lý đối soát.

### 15.6. Compensation khi shipping thất bại sau khi payment capture

Nếu tiền đã capture, compensation có thể là refund. Refund là một giao dịch mới và có thể thất bại hoặc mất thời gian. Saga cần trạng thái `REFUND_PENDING`/`REFUND_FAILED` và retry/manual review, không thể giả định payment đã biến mất ngay lập tức.

## 16. Retry, timeout và xử lý sự kiện độc hại

Không phải mọi lỗi đều nên retry giống nhau.

| Loại lỗi | Ví dụ | Hành động thường dùng |
|---|---|---|
| Tạm thời | Broker unavailable, network reset | Retry có backoff/jitter |
| Quá tải | Rate limit, service busy | Retry theo `Retry-After` hoặc backoff |
| Nghiệp vụ | Không đủ tồn kho, payment declined | Phát kết quả nghiệp vụ; điều phối compensation nếu cần |
| Dữ liệu/schema | Payload không tương thích, thiếu field bắt buộc | Dead-letter, điều tra hoặc upcast |
| Vĩnh viễn | Credential sai, event type không hỗ trợ | Alert và manual intervention; không retry vô hạn |
| Không rõ kết quả | Timeout sau khi downstream có thể đã commit | Query theo idempotency key hoặc gửi lại command idempotent |

### 16.1. Giới hạn retry

Đặt max attempts, max elapsed time và backoff cap. Nếu retry vô hạn, backlog có thể tăng và event lỗi liên tục chiếm tài nguyên. Nếu retry quá ít, lỗi tạm thời có thể đẩy nhiều event vào dead state không cần thiết.

### 16.2. Poison message

Một payload không thể parse hoặc luôn vi phạm schema có thể làm relay/consumer thất bại lặp lại. Ghi nhận event ID, version, type và lỗi đã redact; chuyển sang dead-letter sau chính sách retry. Có quy trình sửa/transform/replay.

### 16.3. Không retry lỗi nghiệp vụ như lỗi mạng

Ví dụ payment declined là kết quả nghiệp vụ; retry ngay cùng thông tin thẻ không nhất thiết làm giao dịch thành công và có thể tạo hành vi không mong muốn. Phát kết quả thất bại để Saga quyết định bước tiếp theo.

### 16.4. Retry phải giữ idempotency key

Mọi lần retry cùng một logical command phải giữ cùng command ID/idempotency key. Nếu mỗi lần retry tạo key mới, downstream có thể xem đó là giao dịch mới và thực hiện nhiều lần.

## 17. Outbox polling hay Change Data Capture?

Có hai cách phổ biến để relay biết outbox row mới.

### 17.1. Polling relay

Relay định kỳ query các row pending, claim theo batch và publish. Ưu điểm:

- Dễ hiểu và có thể triển khai chỉ bằng R2DBC + broker client.
- Không cần đọc transaction log database.
- Dễ điều chỉnh batch, retry và lease.

Nhược điểm:

- Có polling latency.
- Query liên tục tạo tải database.
- Cần quản lý claim, lease và nhiều worker.
- Bảng outbox cần index/retention phù hợp.

### 17.2. CDC relay

Change Data Capture đọc transaction log/binlog/WAL để phát hiện outbox row đã commit. Một connector có thể chuyển thay đổi sang broker.

Ưu điểm:

- Có thể giảm polling query lên database.
- Gần với luồng event-driven và tận dụng log database.
- Có thể đạt throughput cao với volume lớn.

Nhược điểm:

- Cần vận hành connector và transaction log retention.
- Cấu hình snapshot, offset, schema evolution phức tạp hơn.
- Phụ thuộc database và connector version.
- Cần hiểu ordering, duplicate và recovery semantics của CDC.

### 17.3. Chọn theo quy mô và khả năng vận hành

Polling phù hợp khi volume vừa phải, muốn kiểm soát retry bằng code và chưa có hạ tầng CDC. CDC phù hợp khi đã có platform vận hành connector, throughput cao hoặc cần latency thấp. Cả hai vẫn cần idempotent consumer vì duplicate/replay có thể xảy ra.

## 18. Những giới hạn và lỗi thiết kế thường gặp

### Ghi order và outbox ở hai transaction khác nhau

Nếu order commit trước rồi outbox insert thất bại, dual-write vẫn còn. Hai thao tác phải nằm trong cùng local transaction và cùng `ConnectionFactory`.

### Publish broker ngay trong transaction database

Broker không thuộc transaction R2DBC. Publish thành công rồi database rollback vẫn tạo event sai; đồng thời giữ connection trong lúc chờ mạng.

### Gọi subscribe trong service để lưu outbox

Publisher tách rời có thể chạy ngoài transaction. Kết hợp bằng `flatMap`/`then` và trả publisher cho transaction manager.

### Đánh dấu PUBLISHED trước khi broker xác nhận

Process có thể chết sau update và trước publish, làm mất event. Chỉ mark sau acknowledgement theo semantics broker.

### Cho rằng outbox giao đúng một lần

Relay có thể publish thành công rồi chết trước khi mark. Thiết kế at-least-once và idempotent consumer.

### Consumer xử lý nghiệp vụ rồi mới ghi inbox trong transaction khác

Nếu process chết giữa hai thao tác, duplicate có thể áp dụng nghiệp vụ lần nữa. Inbox và business update cần cùng local transaction.

### Acknowledge message trước khi consumer commit

Message có thể bị mất nếu process chết trước commit. Ack sau khi transaction hoàn tất thành công.

### Lease quá ngắn hoặc không có lease

Worker khác có thể claim khi worker trước vẫn publish. Chọn lease phù hợp, gia hạn khi cần và vẫn chấp nhận duplicate.

### Không có retention/cleanup

Outbox tăng vô hạn làm index và query claim ngày càng nặng. Có retention, archive và cleanup theo batch.

### Dùng timestamp để bảo đảm ordering

Timestamp không bảo đảm sequence trong một aggregate. Dùng aggregate sequence/version và partition key nếu thứ tự là invariant.

### Coi compensation là rollback database

Compensation là hành động nghiệp vụ mới, có thể thất bại và không xóa tác động bên ngoài. Thiết kế retry và manual review.

### Không xử lý timeout với kết quả không rõ

Downstream có thể đã commit nhưng response bị mất. Dùng idempotency key và truy vấn trạng thái thay vì tạo command mới.

## 19. Kiểm thử Outbox và Saga

Outbox/Saga cần integration test vì correctness phụ thuộc transaction, database, broker và thời điểm crash.

### 19.1. Test atomicity của outbox write

Test hai tình huống:

- Order insert và outbox insert thành công: cả hai tồn tại sau commit.
- Order insert thành công nhưng outbox insert lỗi: cả hai không tồn tại sau rollback.

Đọc trạng thái bằng transaction độc lập. Không chỉ assert method phát error.

### 19.2. Test relay retry sau restart

1. Ghi outbox row pending.
2. Claim row.
3. Giả lập broker lỗi.
4. Xác nhận row được trả về pending với `next_attempt_at` tương lai.
5. Tạo relay worker mới hoặc chờ lease hết hạn.
6. Xác nhận event được publish sau khi broker phục hồi.

### 19.3. Test crash window sau publish

Giả lập broker đã nhận event nhưng relay chưa mark published. Khi event được claim lại, consumer phải xử lý duplicate mà không tạo thay đổi nghiệp vụ lần hai.

### 19.4. Test nhiều relay worker

Chạy hai worker claim đồng thời và xác nhận một row không bị claim đồng thời trong điều kiện lease còn hiệu lực. Sau đó kiểm tra lease hết hạn có thể được reclaim.

### 19.5. Test idempotent consumer

Gửi cùng message ID hai lần. Xác nhận business state chỉ thay đổi một lần và inbox chỉ có một row cho `(consumer_name, message_id)`.

### 19.6. Test Saga compensation

Tạo workflow mà inventory reserve thành công nhưng payment thất bại. Xác nhận:

- Saga chuyển sang compensation.
- `ReleaseInventory` được phát.
- Inventory trở về trạng thái đúng.
- Order có trạng thái nghiệp vụ thất bại phù hợp.
- Gửi lại event không giải phóng tồn kho hai lần.

### 19.7. Test compensation thất bại

Giả lập service bù trừ tạm thời không khả dụng. Saga phải giữ trạng thái chưa hoàn tất, retry hoặc chuyển manual review; không đánh dấu `COMPENSATED` khi chưa có bằng chứng.

### 19.8. Test event schema evolution

Consumer cần xử lý payload version hiện tại và các version cũ còn được phát trong hệ thống. Kiểm tra field optional, default, unknown field và upcasting nếu dùng.

## 20. Quy trình triển khai trong ứng dụng Spring Data R2DBC

1. Xác định ranh giới local transaction và các hệ thống ngoài cần nhận event.
2. Nếu cần phối hợp nhiều service/database, mô tả state machine và compensation trước.
3. Tạo outbox table trong cùng database sở hữu dữ liệu nghiệp vụ.
4. Tạo entity/repository hoặc custom store cho outbox.
5. Bảo đảm business repository và outbox repository dùng cùng `ConnectionFactory`/reactive transaction manager.
6. Trong Service, ghi business state và outbox event trong một reactive pipeline transactional.
7. Không publish broker trực tiếp trong transaction nghiệp vụ.
8. Chọn polling relay hoặc CDC; xác định claim, lease, retry và retention.
9. Publish với event ID ổn định, event type/version và aggregate sequence nếu cần.
10. Mark published sau broker acknowledgement; chấp nhận duplicate trong crash window.
11. Ở consumer, ghi inbox/dedup key và cập nhật business state trong cùng local transaction.
12. Ack message sau commit; kiểm tra semantics của broker integration.
13. Với Saga, lưu saga state, step history, timeout và compensation progress.
14. Thiết kế compensation idempotent và có manual recovery cho bước không thể đảo ngược.
15. Theo dõi backlog, oldest event age, retry, dead event, duplicate và saga duration.
16. Kiểm thử atomicity, crash window, multi-worker claim, duplicate consumer và compensation failure.

## 21. Checklist ghi nhớ

- [ ] Đã xác định dual-write risk giữa database và broker/service khác.
- [ ] Business row và outbox row được ghi trong cùng local R2DBC transaction.
- [ ] Hai repository dùng cùng `ConnectionFactory` và transaction manager.
- [ ] Event có ID ổn định, type, version, aggregate identity và payload phù hợp.
- [ ] Payload không chứa secret hoặc dữ liệu ngoài contract.
- [ ] Relay chỉ đọc event đã commit.
- [ ] Claim/lease ngăn nhiều worker xử lý cùng row trong thời gian lease.
- [ ] Publish xảy ra ngoài transaction ghi nghiệp vụ.
- [ ] Event chỉ được mark published sau broker acknowledgement.
- [ ] Retry có backoff, jitter, giới hạn và dead-letter policy.
- [ ] Lease có thời hạn và có thể reclaim sau worker crash.
- [ ] Consumer có inbox/idempotency key và business update cùng transaction.
- [ ] Message được ack sau consumer commit.
- [ ] Ordering theo aggregate được bảo đảm nếu nghiệp vụ yêu cầu.
- [ ] Outbox có retention, cleanup và quy trình replay.
- [ ] Metrics theo dõi pending age, backlog, attempts và dead events.
- [ ] Saga state và compensation được lưu bền vững khi workflow đi qua nhiều service.
- [ ] Compensation là idempotent và có xử lý khi chính compensation thất bại.
- [ ] Timeout xử lý được trường hợp downstream đã commit nhưng response bị mất.
- [ ] Integration test bao phủ rollback, duplicate, restart, nhiều worker và compensation.

Transactional Outbox giúp một service ghi dữ liệu nghiệp vụ và ý định phát sự kiện trong cùng transaction R2DBC, sau đó relay chuyển event tới broker theo mô hình at-least-once. Inbox và idempotent consumer xử lý duplicate; lease, retry, dead-letter và retention giúp relay phục hồi sau lỗi. Khi nghiệp vụ kéo dài qua nhiều database hoặc hệ thống độc lập, Saga bổ sung state machine và hành động bù trừ cho từng local transaction. Hai mẫu này không tạo một distributed rollback thần kỳ, nhưng cung cấp cách phối hợp có thể quan sát, kiểm thử và phục hồi khi một phần hệ thống thất bại.
