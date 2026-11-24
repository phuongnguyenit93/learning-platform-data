# Phối hợp cơ sở dữ liệu và sự kiện bằng transactional outbox

Một service Spring Cloud Stream thường phải thực hiện hai việc khi xử lý một lệnh nghiệp vụ: cập nhật cơ sở dữ liệu và phát một event cho hệ thống khác. Ví dụ, Order Service tạo đơn hàng rồi phát `OrderCreated` để Inventory Service giữ hàng và Billing Service chuẩn bị thanh toán.

Nếu service ghi database rồi gửi event trực tiếp, hai thao tác thuộc hai hệ thống độc lập. Database có thể commit nhưng broker không nhận event; hoặc broker nhận event trong khi database rollback. Đây là lỗi **dual write**. Transactional outbox giải quyết vấn đề bằng cách ghi thay đổi nghiệp vụ và một bản ghi outbox trong **cùng transaction của database**. Một relay riêng đọc outbox và gửi event tới Kafka, RabbitMQ hoặc Pulsar qua binder.

Bài thực hành xây dựng luồng end-to-end cho module **SPRING_CLOUD_STREAM**: dùng Supplier/Function/Consumer, binding và binder; giữ event nhất quán với trạng thái database; xử lý retry, duplicate, thứ tự theo aggregate, schema version, quan sát và kiểm thử lỗi. Trọng tâm là cách tích hợp Spring Cloud Stream với database transaction, không giả định một transaction cục bộ có thể bao trùm database và broker.

## 1. Dual write tạo ra hai cửa sổ mất nhất quán

Giả sử service chạy:

~~~java
@Transactional
public Order createOrder(CreateOrder command) {
    Order order = orderRepository.save(Order.from(command));
    streamBridge.send("orders-out-0", new OrderCreated(order.getId()));
    return order;
}
~~~

Đoạn code nhìn có vẻ hợp lý, nhưng transaction database và publish tới broker không tự động là một giao dịch nguyên tử.

| Thứ tự sự cố | Kết quả |
| --- | --- |
| Database commit, sau đó broker unavailable | Đơn hàng tồn tại nhưng không có event |
| Broker nhận event, sau đó database rollback | Consumer xử lý một đơn hàng không tồn tại |
| Broker nhận event nhưng response bị mất | Producer không biết chắc đã gửi; retry có thể tạo duplicate |
| Process chết sau database commit nhưng trước send | Event không bao giờ được phát nếu không có cơ chế khôi phục |
| Process chết sau send nhưng trước khi ghi nhận kết quả | Khi khởi động lại có thể gửi event lần nữa |

Không nên khắc phục bằng cách chỉ đảo thứ tự hai lệnh. Gửi trước rồi commit database vẫn có cửa sổ database rollback sau khi event đã đến broker.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Order Service
    participant D as Database
    participant B as Message Broker
    C->>A: Create order
    A->>D: INSERT order
    D-->>A: Commit DB
    A->>B: Publish OrderCreated
    B--xA: Broker timeout
    Note over D,B: Order đã tồn tại nhưng event có thể chưa được phát
~~~

Transactional outbox thay hai thao tác độc lập bằng một transaction database duy nhất cho phần dữ liệu do service sở hữu.

## 2. Ý tưởng transactional outbox

Trong cùng một transaction database, service:

1. Lưu thay đổi nghiệp vụ, ví dụ tạo Order.
2. Tạo một outbox row mô tả event cần phát.
3. Commit cả hai cùng lúc.

Một relay độc lập đọc các outbox row đã commit, chuyển thành Spring Message và gửi qua output binding bằng `StreamBridge`. Sau khi xác nhận việc gửi theo semantics của binder, relay đánh dấu row đã phát.

~~~mermaid
flowchart TD
    A[HTTP command / use case] --> S[Order Service]
    S --> T[DB transaction]
    T --> O[(orders table)]
    T --> X[(outbox_event table)]
    O --> C{Commit}
    X --> C
    C --> R[Outbox relay]
    R --> M[StreamBridge]
    M --> B[(Kafka / RabbitMQ / Pulsar)]
    B --> K[Downstream Consumer]
    K --> I[(Inbox / dedup table)]
    I --> P[Business side effect]
~~~

Nếu transaction rollback, cả Order và outbox row đều rollback. Nếu transaction commit, event vẫn nằm trong database để relay gửi sau, kể cả broker đang tạm thời không khả dụng.

**Outbox không tạo một distributed transaction giữa database và broker.** Nó bảo đảm việc lưu trạng thái nghiệp vụ và ý định phát event là atomic trong database, sau đó dùng retry để chuyển event sang broker. Relay có thể gửi duplicate, vì vậy consumer cần idempotency.

## 3. Ranh giới transaction và thành phần chịu trách nhiệm

| Thành phần | Transaction hoặc lifecycle | Trách nhiệm |
| --- | --- | --- |
| Command service | Local database transaction | Ghi business row và outbox row cùng nhau |
| Outbox table | Cùng database với business data | Lưu event bất biến cần phát |
| Relay/CDC connector | Đọc các outbox row đã commit | Chuyển event sang broker |
| Spring Cloud Stream binder | Kết nối output binding với broker | Serialization, routing, send và broker-specific options |
| Consumer | Local database transaction | Deduplicate event và cập nhật projection/business data |
| Retention job | Transaction/maintenance riêng | Dọn event đã hoàn tất theo chính sách |

Command service không nên gọi broker trong khi đang giữ transaction database. Một transaction database dài sẽ giữ lock lâu và không làm cho broker publish trở nên atomic.

Relay cũng không nên giữ row lock database trong lúc chờ mạng broker. Nó cần claim một batch bằng transaction ngắn, commit claim, publish bên ngoài transaction đó, rồi cập nhật trạng thái trong transaction mới.

## 4. Hợp đồng event cần ổn định

Trước khi viết outbox table, định nghĩa event contract. Một event nên có metadata đủ để consumer hiểu nguồn, thứ tự và version:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| eventId | Định danh duy nhất của event, giữ nguyên qua mọi lần retry | UUID |
| aggregateType | Loại aggregate phát event | Order |
| aggregateId | Định danh aggregate | order-1024 |
| aggregateSequence | Số thứ tự tăng theo aggregate | 17 |
| eventType | Tên event theo hợp đồng | OrderCreated |
| schemaVersion | Phiên bản payload | 1 |
| occurredAt | Thời điểm nghiệp vụ xảy ra | ISO-8601 UTC |
| payload | Snapshot dữ liệu event | orderId, customerId, total |
| correlationId | Liên kết với request/workflow | UUID |
| trace context | Ngữ cảnh distributed tracing nếu có | traceparent |

Ví dụ payload:

~~~json
{
  "orderId": "order-1024",
  "customerId": "customer-42",
  "total": 129.50,
  "currency": "USD",
  "aggregateSequence": 17
}
~~~

Event nên mô tả **sự kiện đã xảy ra** (`OrderCreated`, `OrderCancelled`) thay vì yêu cầu consumer tự truy vấn trạng thái hiện tại để đoán điều gì đã xảy ra. Nếu relay gửi trễ và order đã thay đổi, payload snapshot vẫn phản ánh dữ liệu tại thời điểm event được tạo.

Không đưa mật khẩu, access token, thông tin thanh toán nhạy cảm hoặc toàn bộ entity graph vào payload. Chỉ công bố trường mà consumer được phép nhận.

## 5. Thiết kế bảng outbox

Một schema thực hành trên PostgreSQL:

~~~sql
CREATE TABLE outbox_event (
    id                  UUID PRIMARY KEY,
    aggregate_type      VARCHAR(120) NOT NULL,
    aggregate_id        VARCHAR(200) NOT NULL,
    aggregate_sequence  BIGINT NOT NULL,
    event_type          VARCHAR(200) NOT NULL,
    schema_version      INTEGER NOT NULL,
    payload             JSONB NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts            INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    lock_token          UUID,
    locked_until        TIMESTAMPTZ,
    published_at        TIMESTAMPTZ,
    last_error          VARCHAR(2000),
    CONSTRAINT ck_outbox_status
        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'RETRY', 'SENT', 'FAILED')),
    CONSTRAINT uq_outbox_aggregate_sequence
        UNIQUE (aggregate_type, aggregate_id, aggregate_sequence)
);

CREATE INDEX ix_outbox_ready
    ON outbox_event (next_attempt_at, occurred_at, id)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX ix_outbox_aggregate_order
    ON outbox_event (aggregate_type, aggregate_id, aggregate_sequence)
    WHERE status <> 'SENT';

CREATE INDEX ix_outbox_expired_lease
    ON outbox_event (locked_until, occurred_at)
    WHERE status = 'IN_FLIGHT';
~~~

Ý nghĩa một số cột:

- `id` là event ID và là khóa chống duplicate ở consumer.
- `aggregate_sequence` giúp phát hiện event đến sai thứ tự. Nếu một lần thay đổi aggregate sinh nhiều event, sequence phải duy nhất theo aggregate; có thể dùng cặp aggregate version + event index.
- `payload` lưu JSON snapshot bất biến. Có thể dùng JSON Schema, Avro hoặc Protobuf thay cho JSON tùy hợp đồng.
- `status` mô tả lifecycle của relay, không phải trạng thái nghiệp vụ của Order.
- `attempts`, `next_attempt_at` hỗ trợ retry có backoff.
- `lock_token`, `locked_until` dùng để claim row giữa nhiều relay instance.
- `published_at` chỉ được đặt sau khi có xác nhận gửi theo semantics binder đã cấu hình.
- `last_error` lưu thông tin chẩn đoán đã được giới hạn và loại bỏ dữ liệu nhạy cảm.

Unique constraint trên aggregate sequence giả định một sequence cho một event. Nếu một business version có thể phát nhiều event, hãy thêm `event_index` và tạo unique key trên (aggregate_type, aggregate_id, aggregate_version, event_index).

Bảng này là schema cho **polling relay**. Nếu dùng Debezium CDC theo cấu trúc Outbox Event Router mặc định, schema và lifecycle row sẽ khác; phần CDC bên dưới trình bày riêng.

## 6. Ghi business data và outbox trong cùng transaction

Ví dụ command service dùng Spring Boot, Spring Data/JDBC và cùng một datasource:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final ObjectMapper objectMapper;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox,
            ObjectMapper objectMapper) {
        this.orders = orders;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public UUID createOrder(CreateOrder command) {
        Order order = orders.save(Order.create(
                command.customerId(),
                command.total(),
                command.currency()));

        // Domain aggregate cấp sequence tăng đơn điệu trong cùng transaction.
        long aggregateSequence = order.nextEventSequence();
        UUID eventId = UUID.randomUUID();
        OrderCreated event = new OrderCreated(
                eventId,
                order.getId(),
                command.customerId(),
                command.total(),
                command.currency(),
                aggregateSequence,
                Instant.now());

        try {
            String json = objectMapper.writeValueAsString(event);
            outbox.insert(
                    eventId,
                    "Order",
                    order.getId().toString(),
                    aggregateSequence,
                    "OrderCreated",
                    1,
                    json);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize OrderCreated", ex);
        }

        return order.getId();
    }
}
~~~

Hai thao tác `orders.save(...)` và `outbox.insert(...)` phải tham gia **cùng local database transaction**. Khi method commit, cả hai tồn tại; khi runtime exception xảy ra trước commit, cả hai rollback.

Ví dụ event DTO:

~~~java
public record OrderCreated(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        BigDecimal total,
        String currency,
        long aggregateSequence,
        Instant occurredAt) {
}
~~~

Repository outbox có thể dùng JDBC để ghi JSONB:

~~~java
@Repository
public class OutboxRepository {

    private final JdbcTemplate jdbc;

    public OutboxRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(
            UUID eventId,
            String aggregateType,
            String aggregateId,
            long sequence,
            String eventType,
            int schemaVersion,
            String payloadJson) {

        jdbc.update("""
            INSERT INTO outbox_event (
                id, aggregate_type, aggregate_id, aggregate_sequence,
                event_type, schema_version, payload, occurred_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CAST(? AS jsonb), now())
            """,
            eventId, aggregateType, aggregateId, sequence,
            eventType, schemaVersion, payloadJson);
    }
}
~~~

Nếu dùng JPA và JdbcTemplate cùng lúc, hãy xác minh chúng dùng cùng DataSource và transaction manager. Nếu chúng trỏ tới hai database khác nhau hoặc hai transaction manager độc lập, hai insert không còn atomic.

### Quy tắc rollback của @Transactional

Theo mặc định, Spring rollback với `RuntimeException` và `Error`, nhưng checked exception không tự động làm transaction rollback. Ví dụ trên chuyển lỗi serialize thành `IllegalStateException`. Nếu phương thức để checked exception thoát ra, hãy khai báo `rollbackFor` phù hợp.

Đừng nuốt exception từ `outbox.insert` rồi trả thành công. Khi ghi outbox thất bại, business transaction phải thất bại theo cùng một chính sách.

## 7. Không gửi broker trực tiếp trong command transaction

Đoạn sau không phải transactional outbox:

~~~java
@Transactional
public UUID createOrder(CreateOrder command) {
    Order order = orders.save(Order.create(command));
    streamBridge.send("orders-out-0", new OrderCreated(...));
    return order.getId();
}
~~~

Dù lời gọi send nằm trong method có `@Transactional`, transaction manager database không tự bao gồm producer Kafka/RabbitMQ/Pulsar. Event có thể được broker nhận trước khi database commit. Nếu DB rollback, consumer đã nhận một sự kiện không hợp lệ.

Cũng không nên chỉ dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` để gửi event rồi bỏ qua outbox. Nếu process chết sau database commit nhưng trước listener publish, event có thể mất. Có thể dùng callback after-commit để **đánh thức relay**, nhưng bản ghi outbox phải được ghi trong transaction gốc.

## 8. Luồng relay: claim, publish, mark sent

Relay có ba bước tách biệt:

1. **Claim:** claim một số row pending/retry trong transaction database ngắn; cấp lock token và lease.
2. **Publish:** gửi message qua StreamBridge ngoài transaction database.
3. **Mark sent:** sau khi broker xác nhận thành công, cập nhật status SENT trong transaction database khác.

~~~mermaid
sequenceDiagram
    participant R as Outbox Relay
    participant D as Database
    participant S as StreamBridge
    participant B as Broker
    R->>D: Claim batch + lock token
    D-->>R: Rows đã claim
    Note over R,D: Transaction claim đã commit
    R->>S: send(output binding, event)
    S->>B: Publish
    B-->>S: Broker acknowledgement
    S-->>R: Send success
    R->>D: UPDATE status = SENT
    D-->>R: Commit trạng thái
~~~

**Không giữ transaction/row lock database trong lúc publish network.** Nếu relay chờ broker nhiều giây khi vẫn khóa row, transaction database sẽ dài và các worker khác bị block.

### Vì sao cần lock token và lease?

Nhiều relay instance có thể chạy song song. Claim row phải đảm bảo hai instance không cùng xử lý một row ở trạng thái bình thường. Lease cho phép worker khác nhận lại row nếu process chết.

Lock token giúp worker cũ không thể ghi đè kết quả sau khi lease hết hạn và row đã được worker mới claim.

## 9. Claim batch bằng PostgreSQL SKIP LOCKED

Ví dụ SQL:

~~~sql
WITH candidates AS (
    SELECT e.id
    FROM outbox_event e
    WHERE (
          e.status IN ('PENDING', 'RETRY')
          OR (e.status = 'IN_FLIGHT' AND e.locked_until < now())
      )
      AND e.next_attempt_at <= now()
      AND (e.locked_until IS NULL OR e.locked_until < now())
      AND NOT EXISTS (
          SELECT 1
          FROM outbox_event earlier
          WHERE earlier.aggregate_type = e.aggregate_type
            AND earlier.aggregate_id = e.aggregate_id
            AND earlier.aggregate_sequence < e.aggregate_sequence
            AND earlier.status <> 'SENT'
      )
    ORDER BY e.occurred_at, e.id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_event e
SET status = 'IN_FLIGHT',
    lock_token = :lock_token,
    locked_until = now() + (:lease_seconds * interval '1 second'),
    attempts = attempts + 1
FROM candidates c
WHERE e.id = c.id
RETURNING e.*;
~~~

Giải thích:

- `FOR UPDATE SKIP LOCKED` cho phép nhiều relay cùng claim queue-like table mà không chờ những row worker khác đang khóa.
- `LIMIT` giới hạn batch để transaction claim nhanh.
- `lock_token` là token riêng của lượt claim.
- `locked_until` là thời điểm lease hết hạn.
- Điều kiện claim bao gồm cả row `IN_FLIGHT` đã hết lease; nếu bỏ nhánh này, process chết giữa lúc publish có thể để row mắc kẹt mãi ở IN_FLIGHT.
- `NOT EXISTS` ngăn claim event mới hơn của cùng aggregate nếu event trước chưa SENT.

PostgreSQL mô tả SKIP LOCKED phù hợp với nhiều consumer truy cập một bảng có semantics giống queue, nhưng kết quả đọc là một view không nhất quán và không nên dùng cho truy vấn nghiệp vụ thông thường.

Điều kiện thứ tự trong ví dụ khiến một event FAILED của aggregate chặn event sau nó. Đây là lựa chọn an toàn khi thứ tự nghiệp vụ bắt buộc. Nếu nghiệp vụ cho phép bỏ qua một event đã xử lý thủ công, cần có trạng thái SKIPPED được audit và điều kiện query rõ ràng; không tự động coi FAILED là SENT.

## 10. Claim repository và transaction ngắn

Ví dụ repository sử dụng `NamedParameterJdbcTemplate` vì câu SQL claim dùng named parameters:

~~~java
@Repository
public class OutboxClaimRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OutboxClaimRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public List<ClaimedOutboxEvent> claim(
            int batchSize,
            int leaseSeconds,
            UUID lockToken) {

        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("batch_size", batchSize)
                .addValue("lease_seconds", leaseSeconds)
                .addValue("lock_token", lockToken);

        return jdbc.query(CLAIM_SQL, parameters,
                (rs, rowNum) -> new ClaimedOutboxEvent(
                        rs.getObject("id", UUID.class),
                        rs.getString("aggregate_type"),
                        rs.getString("aggregate_id"),
                        rs.getLong("aggregate_sequence"),
                        rs.getString("event_type"),
                        rs.getInt("schema_version"),
                        rs.getString("payload"),
                        rs.getTimestamp("occurred_at").toInstant(),
                        lockToken));
    }
}
~~~

Đây là khung minh họa. Khi triển khai thật, khai báo `CLAIM_SQL` đúng với SQL ở phần trước, dùng mapper tương ứng kiểu JSONB và kiểm tra tên cột `RETURNING`. Phương thức claim phải được gọi qua Spring bean proxy để transaction commit khi method trả về.

Nếu claim batch lớn nhưng relay publish chậm, lease có thể hết hạn trước khi worker hoàn tất. Chọn batch nhỏ, lease dài hơn thời gian publish dự kiến và có thể gia hạn lease cho event đang xử lý. Không dùng một lease ngắn tùy tiện.

## 11. Cấu hình output binding cho StreamBridge

Relay là một nguồn event không phải function input, vì vậy có thể dùng `StreamBridge` để gửi tới output binding.

Khai báo binding tường minh:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orderEvents-out-0
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
~~~

`output-bindings` tạo binding khi ứng dụng khởi động. Nếu không khai báo trước, StreamBridge có thể tạo binding khi gọi send lần đầu; với relay production, binding tường minh giúp phát hiện lỗi destination/configuration sớm hơn.

Ví dụ tạo message:

~~~java
EventEnvelope envelope = new EventEnvelope(
        row.id(),
        row.aggregateType(),
        row.aggregateId(),
        row.aggregateSequence(),
        row.eventType(),
        row.schemaVersion(),
        row.occurredAt(),
        objectMapper.readTree(row.payload()));

Message<EventEnvelope> message = MessageBuilder
        .withPayload(envelope)
        .setHeader("eventId", row.id().toString())
        .setHeader("aggregateId", row.aggregateId())
        .setHeader("eventType", row.eventType())
        .setHeader("schemaVersion", row.schemaVersion())
        .build();

boolean accepted = streamBridge.send("orderEvents-out-0", message);
if (!accepted) {
    throw new IllegalStateException("Output binding rejected the event");
}
~~~

DTO envelope:

~~~java
public record EventEnvelope(
        UUID eventId,
        String aggregateType,
        String aggregateId,
        long aggregateSequence,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        JsonNode payload) {
}
~~~

StreamBridge dùng cùng cơ chế gửi của Spring Integration. Theo tài liệu Spring Cloud Stream hiện hành, send chạy trên thread gọi theo mặc định; có thể bật async bằng `setAsync(true)`. Với relay, thường ưu tiên đường gửi có kết quả xác nhận rõ ràng để chỉ mark SENT khi đã nhận broker acknowledgment.

## 12. Phân biệt StreamBridge send result và broker acknowledgement

Đây là điểm quan trọng nhất trong relay polling.

- Giá trị boolean của `StreamBridge.send(...)` cho biết thao tác gửi qua binding/channel có được chấp nhận hay không.
- Điều đó không phải lúc nào cũng tương đương với việc broker đã xác nhận lưu message.
- Kafka binder producer có thuộc tính `sync`; mặc định là false. Khi cần relay chờ kết quả gửi, cấu hình synchronous publish và timeout phù hợp.
- Với RabbitMQ/Pulsar, xác minh cơ chế publisher confirm/send completion của binder và phiên bản đang sử dụng.

Ví dụ cấu hình Kafka output:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orderEvents-out-0:
            producer:
              sync: true
              message-key-expression: headers['aggregateId']
              configuration:
                acks: all
~~~

`sync: true` yêu cầu Kafka binder thực hiện synchronous publish; `sendTimeoutExpression` có thể đặt thời gian chờ acknowledgment theo message khi cần. `acks: all` yêu cầu broker xác nhận theo replication policy đã cấu hình. Replication factor, min.insync.replicas và ISR vẫn phải được thiết kế phù hợp.

Không bật `StreamBridge.setAsync(true)` cho đường relay rồi lập tức mark SENT chỉ dựa trên boolean trả về. Nếu send async, phải dùng cơ chế callback/confirmation của binder để cập nhật trạng thái sau khi send hoàn tất; nếu callback thất bại hoặc không đến, giữ row có thể retry.

Nếu dùng nhiều binder, chọn đúng binder cho output binding bằng overload StreamBridge tương ứng hoặc cấu hình binding rõ ràng. Không giả định một binding name sẽ tự chọn đúng cluster khi nhiều binder cùng có mặt.

## 13. Kafka key và thứ tự theo aggregate

Để event của cùng một order vào cùng partition Kafka, dùng aggregate ID làm message key. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orderEvents-out-0:
            producer:
              message-key-expression: headers['aggregateId']
~~~

Khi aggregateId ổn định, các event cùng order thường được định tuyến tới cùng partition theo partitioner. Kafka chỉ bảo đảm thứ tự trong một partition; nó không bảo đảm thứ tự toàn topic giữa nhiều partition.

Relay cũng phải tránh gửi sequence 18 trước sequence 17 của cùng aggregate. Chỉ dùng SKIP LOCKED mà không có điều kiện theo aggregate có thể khiến worker A claim sequence 17 rồi worker B claim sequence 18 và publish nhanh hơn.

Khi thay số partition của topic, key-to-partition mapping có thể thay đổi. Nếu yêu cầu thứ tự chặt chẽ xuyên suốt lịch sử, phải có kế hoạch partition migration và consumer cutover.

## 14. Publish và mark SENT ở hai transaction khác nhau

Sau khi publish được xác nhận, cập nhật row:

~~~sql
UPDATE outbox_event
SET status = 'SENT',
    published_at = now(),
    lock_token = NULL,
    locked_until = NULL,
    last_error = NULL
WHERE id = :event_id
  AND status = 'IN_FLIGHT'
  AND lock_token = :lock_token;
~~~

Kiểm tra số row được update. Nếu bằng 0, lease có thể đã hết hạn và một worker khác đã claim event. Worker cũ không được ghi đè trạng thái mới.

**Không mark SENT trước khi publish.** Nếu database commit SENT rồi process chết trước khi broker nhận event, event bị mất khỏi relay.

Ngược lại, vẫn tồn tại cửa sổ duplicate:

1. Broker nhận event và xác nhận thành công.
2. Relay process chết trước khi commit status SENT.
3. Lease hết hạn.
4. Relay khác publish lại event.

Đây là hành vi **at-least-once**. Không thể xóa cửa sổ này chỉ bằng hai transaction độc lập của database và broker. Consumer phải idempotent.

## 15. Lập lịch retry và xử lý lỗi publish

Khi broker tạm lỗi hoặc send timeout, giữ row để retry. Ví dụ cập nhật trạng thái:

~~~sql
UPDATE outbox_event
SET status = CASE
        WHEN attempts >= :max_attempts THEN 'FAILED'
        ELSE 'RETRY'
    END,
    next_attempt_at = :next_attempt_at,
    lock_token = NULL,
    locked_until = NULL,
    last_error = :sanitized_error
WHERE id = :event_id
  AND status = 'IN_FLIGHT'
  AND lock_token = :lock_token;
~~~

Chính sách retry nên có:

- Exponential backoff.
- Jitter để nhiều relay instance không retry đồng thời.
- Giới hạn số lần thử hoặc thời gian tồn tại tùy SLA.
- Timeout cho broker send.
- Alert khi row FAILED hoặc backlog tăng kéo dài.
- Khả năng operator retry lại sau khi sửa lỗi.

Không retry nóng liên tục khi broker unavailable; điều đó có thể làm cạn connection, CPU và database. Không lưu toàn bộ stack trace hoặc payload nhạy cảm vào `last_error`; lưu exception class, mã lỗi và thông tin chẩn đoán đã sanitize.

Một event không thể serialize vì schema sai thường không tự hết lỗi. Đưa row sang FAILED, alert và yêu cầu sửa schema/mapper hoặc xử lý thủ công. Không xóa event lỗi để làm dashboard sạch.

## 16. Khung relay hoàn chỉnh

Ví dụ sau thể hiện ranh giới transaction. Các phương thức repository claim/mark/retry phải nằm trong bean riêng có `@Transactional`, tránh self-invocation làm transaction annotation không được áp dụng.

~~~java
@Component
public class OutboxRelay {

    private final OutboxClaimRepository claims;
    private final OutboxStateRepository state;
    private final StreamBridge streamBridge;
    private final ObjectMapper objectMapper;

    public OutboxRelay(
            OutboxClaimRepository claims,
            OutboxStateRepository state,
            StreamBridge streamBridge,
            ObjectMapper objectMapper) {
        this.claims = claims;
        this.state = state;
        this.streamBridge = streamBridge;
        this.objectMapper = objectMapper;
    }

    @Scheduled(fixedDelayString = "\${outbox.relay.delay:500}")
    public void publishBatch() {
        UUID token = UUID.randomUUID();
        List<ClaimedOutboxEvent> batch =
                claims.claim(50, 60, token);

        for (ClaimedOutboxEvent row : batch) {
            publishOne(row);
        }
    }

    private void publishOne(ClaimedOutboxEvent row) {
        try {
            EventEnvelope envelope = new EventEnvelope(
                    row.id(),
                    row.aggregateType(),
                    row.aggregateId(),
                    row.aggregateSequence(),
                    row.eventType(),
                    row.schemaVersion(),
                    row.occurredAt(),
                    objectMapper.readTree(row.payload()));

            Message<EventEnvelope> message = MessageBuilder
                    .withPayload(envelope)
                    .setHeader("eventId", row.id().toString())
                    .setHeader("aggregateId", row.aggregateId())
                    .setHeader("eventType", row.eventType())
                    .setHeader("schemaVersion", row.schemaVersion())
                    .build();

            boolean accepted = streamBridge.send(
                    "orderEvents-out-0", message);

            if (!accepted) {
                throw new IllegalStateException(
                        "StreamBridge rejected the output message");
            }

            // Chỉ gọi sau khi binder đã cung cấp send confirmation
            // theo semantics được cấu hình (Kafka sync=true ở ví dụ).
            state.markSent(row.id(), row.lockToken());
        }
        catch (Exception ex) {
            state.scheduleRetry(
                    row.id(),
                    row.lockToken(),
                    sanitize(ex));
        }
    }

    private String sanitize(Exception ex) {
        return ex.getClass().getSimpleName() + ": "
                + safeMessage(ex.getMessage());
    }

    private String safeMessage(String value) {
        if (value == null) {
            return "no details";
        }
        return value.length() <= 500
                ? value
                : value.substring(0, 500);
    }
}
~~~

Đây là khung ứng dụng. Khi dùng thực tế:

- Bảo đảm Kafka producer `sync: true` hoặc xác nhận send tương đương của binder.
- Không gọi `state.markSent` khi chỉ biết channel đã nhận message nhưng broker ack còn pending.
- Cần xử lý `InterruptedException`/shutdown theo lifecycle nếu relay dùng blocking API.
- Nếu publish có kết quả không chắc chắn do timeout, giữ retry và chấp nhận duplicate; đừng tự giả định message chưa đến broker.
- Tạo lease token đúng cho mỗi batch/claim và chỉ update khi token còn khớp.
- Thêm metric và giới hạn concurrency/batch size.
- Với event cùng aggregate, bảo đảm query claim và cách dispatch không cho event sau vượt event trước.

## 17. Vì sao không dùng một transaction bao trùm send?

Một lựa chọn tưởng như đơn giản là:

~~~java
@Transactional
public void createAndPublish(...) {
    saveOrder();
    saveOutbox();
    streamBridge.send(...);
}
~~~

Cách này vẫn không làm database và broker thành một resource manager duy nhất. Nếu database commit và broker send không cùng XA/distributed transaction coordinator, một bên vẫn có thể commit trong khi bên kia rollback hoặc timeout.

Kafka transactional producer có thể commit nhiều Kafka records và consumer offsets trong một transaction Kafka; nó không tự bao trùm một database transaction JDBC/JPA. Transactional outbox tránh phải giữ transaction database mở trong khi chờ broker và làm rõ eventual delivery.

Một số hệ thống có thể đồng bộ transaction giữa Kafka và database bằng transaction synchronization hoặc XA trong điều kiện đặc biệt, nhưng điều đó tăng độ phức tạp và không thay thế outbox khi cần bảo đảm phục hồi qua crash. Hãy chọn kiến trúc dựa trên failure model, không dựa vào việc một method có annotation `@Transactional`.

## 18. Consumer inbox: chống xử lý lặp

Outbox relay có thể gửi duplicate sau crash. Consumer phải ghi nhận event ID đã xử lý trong cùng transaction với side effect của consumer.

Schema inbox:

~~~sql
CREATE TABLE inbox_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer service:

~~~java
@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(EventEnvelope event) {
        int inserted = jdbc.update("""
            INSERT INTO inbox_event (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "order-projection",
            event.eventId());

        if (inserted == 0) {
            // Event đã được commit ở lần xử lý trước.
            return;
        }

        updateProjection(event);
    }

    private void updateProjection(EventEnvelope event) {
        // Cập nhật projection/business data trong cùng DB transaction.
    }
}
~~~

Nếu event duplicate, insert trả 0 và consumer bỏ qua side effect. Nếu `updateProjection` lỗi, transaction rollback cả inbox insert và business update; lần giao lại sau có thể xử lý lại.

Ví dụ function consumer:

~~~java
@Bean
public Consumer<EventEnvelope> projectOrder(
        OrderProjectionService service) {
    return service::apply;
}
~~~

Đảm bảo method transactional nằm trong bean khác được gọi qua Spring proxy. Không gọi một method @Transactional private hoặc self-invocation rồi giả định proxy tự mở transaction.

Inbox chỉ chống duplicate trong **cùng consumer_name và database**. Nếu một consumer thực hiện side effect tới một hệ thống ngoài database, cần idempotency key hoặc outbox riêng cho side effect tiếp theo.

## 19. Offset commit và database transaction của consumer

Với Kafka consumer, một kịch bản phổ biến:

1. Consumer nhận event E1.
2. Consumer transaction database insert inbox và cập nhật projection.
3. Database commit.
4. Process chết trước khi Kafka offset được commit.
5. Kafka giao lại E1.
6. Inbox unique key phát hiện E1 đã được xử lý; consumer không lặp side effect.
7. Kafka offset có thể tiến sau khi lần xử lý mới hoàn tất.

Đây là mô hình **at-least-once delivery + idempotent consumer**. Không tuyên bố end-to-end exactly-once chỉ vì bật Kafka EOS hoặc dùng transactional outbox. Database và broker vẫn có hai transaction boundary khác nhau.

Nếu consumer commit offset trước khi database commit, một crash có thể làm mất side effect. Hãy dùng acknowledgment/transaction mode phù hợp để chỉ acknowledge sau khi service transaction thành công. Cấu hình cụ thể phụ thuộc binder và listener container.

## 20. Thứ tự event theo aggregate

Giả sử một Order phát:

~~~text
OrderCreated(sequence=1)
OrderPaid(sequence=2)
OrderShipped(sequence=3)
~~~

Nếu relay nhiều worker không có chính sách thứ tự, worker A có thể giữ event 1 trong lúc worker B gửi event 2. Consumer nhận sequence 2 trước sequence 1 có thể tạo trạng thái sai.

Các lớp cần phối hợp:

1. Command service cấp aggregate sequence tăng đơn điệu trong cùng transaction cập nhật aggregate.
2. Outbox lưu sequence và event ID.
3. Relay chỉ claim event đầu tiên chưa SENT của mỗi aggregate khi cần strict order.
4. Message key là aggregate ID để cùng aggregate đi cùng partition (Kafka) hoặc routing/ordering key tương đương.
5. Consumer kiểm tra sequence, phát hiện gap hoặc duplicate và có chính sách chờ/reconcile.

Không có thứ tự toàn cục giữa mọi aggregate. Thường chỉ cần thứ tự theo một Order, Account hoặc Customer.

### Nếu event trước bị FAILED?

Nếu sequence 8 bị FAILED nhưng sequence 9 vẫn được phát, consumer có thể thấy trạng thái thiếu một transition. Có hai lựa chọn:

- **Strict order:** giữ sequence 9 ở pending cho tới khi sequence 8 được phục hồi hoặc operator xác nhận skip.
- **Relaxed order:** cho phép sequence 9 đi tiếp, nhưng consumer phải chịu được out-of-order và có logic reconcile.

Không để hành vi này xảy ra ngẫu nhiên chỉ do query claim.

## 21. Retry, backoff và trạng thái FAILED

Một state machine relay đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> IN_FLIGHT: claim
    RETRY --> IN_FLIGHT: đến hạn retry
    IN_FLIGHT --> SENT: broker ack + DB update
    IN_FLIGHT --> RETRY: lỗi tạm thời
    IN_FLIGHT --> FAILED: hết retry / lỗi vĩnh viễn
    FAILED --> PENDING: operator replay sau sửa lỗi
    SENT --> [*]
~~~

| Trạng thái | Ý nghĩa |
| --- | --- |
| PENDING | Event đã commit, đang chờ relay |
| IN_FLIGHT | Một worker đã claim với lease |
| RETRY | Send thất bại, chờ đến next_attempt_at |
| SENT | Binder xác nhận send theo cấu hình và DB ghi nhận |
| FAILED | Cần can thiệp hoặc chính sách quarantine |

Retry delay ví dụ:

~~~text
delay = min(baseDelay * 2^attempt, maxDelay) + randomJitter
~~~

Giới hạn retry phải phù hợp SLA. Broker outage có thể kéo dài; nếu chuyển mọi row thành FAILED sau vài lần thử quá ngắn, backlog sẽ cần thao tác thủ công lớn. Ngược lại, retry vô hạn không có alert khiến một event lỗi schema bị mắc kẹt không ai biết.

Khi replay FAILED, giữ nguyên event ID và payload gốc nếu đó vẫn là event hợp lệ. Nếu cần sửa payload, tạo một correction/new event có event ID mới và audit mối quan hệ với event cũ; đừng âm thầm thay nội dung một event đã phát.

## 22. Dead-letter queue khác outbox FAILED

Cần phân biệt hai vị trí lỗi:

- **Outbox relay không gửi được event tới broker:** event vẫn còn trong database outbox. Nếu broker đang DOWN, DLT trên chính broker đó cũng có thể không gửi được. Giữ row RETRY/FAILED và cảnh báo.
- **Consumer nhận event nhưng không xử lý được:** binder/container có thể đưa record tới Kafka DLT, Rabbit dead-letter exchange hoặc Pulsar dead-letter topic theo cấu hình consumer.

Outbox FAILED là trạng thái điều phối ở database; DLT là destination message broker. Không dùng hai khái niệm thay thế nhau.

Nếu có một quarantine broker độc lập, có thể publish event lỗi sang đó sau khi xác nhận. Nhưng việc gửi quarantine cũng có cửa sổ duplicate/ack tương tự và phải giữ event ID, source status, error reason.

## 23. Cleanup và retention outbox

Bảng outbox tăng liên tục. Cần cleanup nhưng phải giữ row đủ lâu để điều tra và replay:

- Chỉ xóa/archive row SENT sau thời gian retention được thống nhất.
- Không xóa PENDING, IN_FLIGHT, RETRY hoặc FAILED.
- Dùng batch delete theo ID/thời gian để tránh transaction lớn.
- Tạo index phục vụ claim và cleanup.
- Theo dõi disk growth, autovacuum/bloat (PostgreSQL), backup/restore và partition pruning nếu lưu lượng cao.
- Lưu audit tối thiểu nếu quy định nghiệp vụ yêu cầu giữ lịch sử.

Ví dụ cleanup theo batch:

~~~sql
DELETE FROM outbox_event
WHERE id IN (
    SELECT id
    FROM outbox_event
    WHERE status = 'SENT'
      AND published_at < now() - interval '14 days'
    ORDER BY published_at
    LIMIT 1000
);
~~~

Chạy lặp có giới hạn, không xóa toàn bảng trong một transaction. Nếu cần giữ event lâu để replay, archive sang storage phù hợp hoặc giữ bảng theo partition thời gian.

## 24. Phương án CDC: Debezium Outbox Event Router

Polling relay không phải lựa chọn duy nhất. Với Change Data Capture (CDC), database ghi outbox row trong transaction; connector đọc transaction log/WAL/binlog và phát thay đổi đã commit tới Kafka. Debezium cung cấp **Outbox Event Router SMT** để biến outbox change record thành event message.

Cấu trúc mặc định của Debezium Outbox Event Router thường có:

| Cột | Ý nghĩa |
| --- | --- |
| id | Event ID; được đưa vào message header để consumer deduplicate |
| aggregatetype | Giá trị định tuyến topic, ví dụ Order |
| aggregateid | Message key, giúp giữ thứ tự theo aggregate trong Kafka partition |
| type | Event type |
| payload | JSON hoặc representation của event |

~~~mermaid
flowchart LR
    A[Order Service] --> T[DB transaction]
    T --> O[(outbox_event INSERT)]
    O --> W[(WAL / binlog)]
    W --> D[Debezium connector]
    D --> SMT[Outbox Event Router SMT]
    SMT --> K[(Kafka topic)]
    K --> C[Spring Cloud Stream consumer]
~~~

Cấu hình SMT cơ bản trong Kafka Connect:

~~~properties
transforms=outbox
transforms.outbox.type=io.debezium.transforms.outbox.EventRouter
~~~

Theo cấu hình mặc định, `aggregatetype` tham gia tên topic, `aggregateid` làm Kafka key, `id` thành header và `payload` thành message value. Có thể tùy chỉnh routing field, topic replacement, event ID/key/payload field và placement của additional fields.

### Khác biệt schema và lifecycle với polling

Debezium Outbox Event Router mong đợi outbox rows chủ yếu được **INSERT**. Một số cấu hình SMT cảnh báo hoặc báo lỗi nếu gặp UPDATE; DELETE được lọc theo mặc định. Vì vậy, không bê nguyên bảng polling có status/lock updates sang CDC mà không xem kỹ cấu hình SMT.

CDC không cần relay tự cập nhật published_at cho từng row; connector offset/transaction log tracking quản lý tiến độ capture. Tuy nhiên, connector, replication slot, WAL retention, snapshot, schema history, Kafka Connect worker và monitoring đều trở thành thành phần vận hành quan trọng.

Không xóa outbox row quá sớm trước khi connector đã capture; cần retention phù hợp với khả năng connector outage và snapshot/recovery.

## 25. Chọn polling relay hay CDC?

| Tiêu chí | Polling relay | CDC/Debezium |
| --- | --- | --- |
| Thành phần vận hành | Application relay + database | Connector, Kafka Connect, database log capture |
| Độ trễ | Theo chu kỳ poll/batch | Gần thời gian thực theo log capture |
| Database load | Poll/index/update/delete | Đọc transaction log; cần cấu hình WAL/binlog |
| State tracking | Trạng thái/lease trong outbox | Connector offsets và log position |
| Retry logic | Application chủ động | Connector retry/restart và downstream policy |
| Broker đích | Có thể dùng StreamBridge tới Kafka/Rabbit/Pulsar theo binder | Outbox Event Router phổ biến cho Kafka Connect/Kafka |
| Ordering | Relay phải chủ động claim theo aggregate | Key aggregate ID giúp route cùng Kafka partition; vẫn phải kiểm tra connector/order config |
| Độ phức tạp | Dễ bắt đầu, cần quản lý leases và duplicate | Nhiều hạ tầng hơn, phù hợp throughput lớn và CDC platform sẵn có |

Chọn polling nếu workload vừa phải, muốn triển khai đơn giản hoặc cần gửi qua binder không phải Kafka. Chọn CDC khi tổ chức đã vận hành Kafka Connect/Debezium, cần capture throughput cao và chấp nhận quản lý connector/transaction logs.

Hai cách cùng giải quyết dual write ở phía database, nhưng có failure model, retention và operational ownership khác nhau.

## 26. Tích hợp Spring Cloud Stream với RabbitMQ và Pulsar

Transactional outbox không phụ thuộc Kafka. Bảng outbox và transaction ghi business data vẫn giữ nguyên; relay có thể dùng StreamBridge tới binder tương ứng.

Tuy nhiên, semantics xác nhận và ordering khác nhau:

| Binder | Đặc điểm cần kiểm tra |
| --- | --- |
| Kafka | Producer sync/acks, message key, partition, consumer group, read_committed nếu dùng transaction Kafka |
| RabbitMQ | Publisher confirms, exchange/queue durability, routing, delivery mode, mandatory returns, dead-letter exchange |
| Pulsar | Send completion/ack, topic partition, message key, subscription type, schema và redelivery policy |

Không coi `StreamBridge.send() == true` là bằng chứng phổ quát rằng mọi broker đã lưu bền vững. Hãy kiểm tra cơ chế confirm cụ thể của binder đang dùng và chỉ mark SENT khi đã có kết quả đủ mạnh.

Nếu ứng dụng có nhiều binder, chọn binder đúng cho output binding; tránh vô tình gửi event tới cluster mặc định khác. Cùng event ID/aggregate key phải được giữ nguyên qua các binder.

## 27. Schema evolution và event version

Outbox row có thể tồn tại trong database lâu hơn một phiên bản ứng dụng. Relay phiên bản mới có thể đọc event được tạo bởi phiên bản cũ; consumer cũng có thể chạy chậm hơn producer.

Cần có:

- Event type ổn định và schemaVersion rõ.
- Payload snapshot không phụ thuộc lazy-loaded JPA entity khi relay chạy.
- Quy tắc compatibility cho thêm/bỏ/đổi field.
- Mapper/serializer có thể đọc version cũ trong thời gian retention.
- Consumer unknown event type có chính sách skip/quarantine rõ, không deserialize tùy ý.
- Kiểm thử producer mới với consumer cũ và ngược lại.

Không lưu class name Java rồi dùng reflection tùy ý để tạo object khi relay phát event. Dùng event type allowlist và mapping tới schema/DTO đã biết.

## 28. Trace context và correlation

Event được ghi trong transaction rồi gửi sau có thể phát trên thread khác và thời điểm khác. Hãy lưu correlation metadata cần thiết trong outbox:

- eventId;
- aggregateId;
- correlationId;
- causationId nếu có;
- occurredAt;
- trace context đã được phép lưu và propagate.

Không giữ toàn bộ request headers hoặc authentication token trong outbox. Trace context là metadata quan sát, không phải nguồn xác thực.

Khi relay gửi bằng StreamBridge, tạo message headers từ các trường đã lưu và để Micrometer/Spring observability instrumentation quản lý propagation phù hợp. Nếu bật async send, cần cấu hình context propagation theo tài liệu Spring Cloud Stream.

## 29. Bảo mật và quyền truy cập

Outbox chứa dữ liệu nghiệp vụ có thể nhạy cảm. Áp dụng:

- Chỉ command service và relay được quyền đọc/ghi bảng outbox theo vai trò.
- Consumer không truy cập database nguồn chỉ để lấy payload.
- Mã hóa dữ liệu nhạy cảm theo chính sách database/storage.
- Không ghi payload đầy đủ hoặc secrets vào logs/metrics.
- Giới hạn dynamic destinations; không lấy topic name trực tiếp từ user input.
- Cấp broker ACL riêng cho relay producer và consumer.
- Bảo vệ Actuator/metrics và thông tin connection.
- Đặt retention/purge theo yêu cầu pháp lý và nghiệp vụ.
- Audit thao tác replay/FAILED resolution.

Event là một hợp đồng chia sẻ dữ liệu giữa service; chỉ đưa vào những trường downstream cần và được phép xử lý.

## 30. Observability: biết outbox có đang bị nghẽn không

Các metric hữu ích:

| Metric | Mục đích |
| --- | --- |
| outbox_pending_count | Số event đang chờ |
| outbox_oldest_pending_age | Tuổi của event chưa gửi lâu nhất |
| outbox_in_flight_count | Số row đang được relay claim |
| outbox_retry_count | Tổng retry theo thời gian |
| outbox_failed_count | Event cần can thiệp |
| outbox_publish_latency | Thời gian từ claim tới broker confirmation |
| outbox_publish_success_total | Số event đã xác nhận |
| outbox_publish_error_total | Số lần gửi lỗi |
| outbox_lease_expired_total | Số lease hết hạn |
| consumer_duplicate_total | Số event bị inbox loại do đã xử lý |
| consumer_processing_lag | Độ trễ event từ occurredAt tới processedAt |

Log có cấu trúc nên bao gồm eventId, aggregateId, eventType, sequence, destination, attempt, relay instance, send result và error class. Không dùng eventId làm metric tag vì cardinality cao.

Alert nên tập trung vào tuổi pending, FAILED count, retry rate và relay không tiến triển. Một số lượng pending lớn nhưng vừa được tạo có thể bình thường; **oldest pending age** thường hữu ích hơn chỉ nhìn tổng row count.

## 31. Kiểm thử transaction ghi business data và outbox

Test quan trọng đầu tiên là chứng minh hai insert cùng rollback/commit.

Ví dụ kịch bản:

| Kịch bản | Order row | Outbox row |
| --- | --- | --- |
| Command thành công | Có | Có |
| Validation thất bại trước save | Không | Không |
| Order insert thành công nhưng outbox insert lỗi | Rollback | Rollback |
| Transaction bị đánh dấu rollback-only | Không commit | Không commit |
| Process crash sau DB commit | Có | Có; relay có thể phát sau restart |

Dùng integration test với database thật qua Testcontainers nếu dựa vào JSONB, SKIP LOCKED, partial index hoặc SQL đặc thù PostgreSQL. H2 có thể không mô phỏng đúng semantics cần kiểm tra.

Test có thể chủ động ném exception sau outbox insert và xác minh cả hai bảng không có row.

## 32. Kiểm thử relay và cửa sổ duplicate

| Kịch bản | Kỳ vọng |
| --- | --- |
| Broker unavailable trước send | Row RETRY/PENDING, không SENT |
| StreamBridge từ chối message | Không SENT; ghi retry/error |
| Kafka send sync nhận ack | Sau đó row mới SENT |
| Broker ack nhưng process chết trước DB mark | Event có thể được gửi lại; consumer dedupe |
| Lease hết hạn và worker khác claim | Token cũ không thể mark SENT |
| Hai worker claim cùng batch | Không claim cùng row trong trạng thái bình thường |
| Event trước cùng aggregate đang IN_FLIGHT | Event sau không vượt lên nếu strict order |
| Hết retry | FAILED + alert, row vẫn giữ lại |
| Operator replay | Giữ event ID, audit và kiểm tra duplicate |

Không viết test chỉ assert `StreamBridge.send()` trả true rồi coi broker đã lưu. Với Kafka, cấu hình sync và test broker thật để xác minh send completion/ack; với Rabbit/Pulsar, dùng xác nhận tương ứng của binder.

## 33. Kiểm thử inbox và idempotency

Test consumer với cùng event hai lần:

1. Lần đầu: insert inbox thành công, business projection thay đổi.
2. Lần hai: unique constraint chặn insert, consumer bỏ qua.
3. Cả hai lần đều không tạo hai side effects.
4. Nếu lần đầu business update lỗi, transaction rollback inbox insert.
5. Khi giao lại, consumer có thể xử lý thành công.

Ngoài duplicate liên tiếp, test duplicate sau restart, concurrent delivery từ hai thread và replay từ DLT. Unique constraint database là cơ chế đồng bộ cuối cùng; chỉ dùng một `if (cache.contains(eventId))` trong memory là không đủ.

## 34. Bài thực hành end-to-end

### Bước 1: Tạo database schema

- Tạo bảng orders.
- Tạo outbox_event với event ID, aggregate sequence, payload và trạng thái relay.
- Tạo inbox_event ở database của consumer.
- Thêm index cho claim, cleanup và unique constraints.

### Bước 2: Viết command service

- Tạo Order trong một `@Transactional` method.
- Tạo OrderCreated snapshot.
- Insert outbox row bằng cùng datasource/transaction manager.
- Không gọi StreamBridge trong method này.
- Test rollback khi outbox insert thất bại.

### Bước 3: Tạo output binding

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orderEvents-out-0
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
      kafka:
        bindings:
          orderEvents-out-0:
            producer:
              sync: true
              message-key-expression: headers['aggregateId']
              configuration:
                acks: all
~~~

Đây là cấu hình Kafka minh họa. Với RabbitMQ/Pulsar, thay producer confirmation và key/routing configuration theo binder tương ứng.

### Bước 4: Viết relay

- Scheduled poll gọi claim repository.
- Claim batch bằng SKIP LOCKED và lock token.
- Commit transaction claim trước khi send.
- Gửi envelope qua StreamBridge.
- Chỉ mark SENT sau broker confirmation.
- Nếu lỗi, schedule retry có backoff.
- Theo dõi FAILED và lease expiry.

### Bước 5: Viết consumer

~~~java
@Bean
public Consumer<EventEnvelope> consumeOrderCreated(
        OrderProjectionService service) {
    return service::apply;
}
~~~

`OrderProjectionService.apply` mở transaction database, insert inbox_event trước rồi cập nhật projection. Dùng eventId làm unique dedup key.

### Bước 6: Chạy broker và database integration tests

- Tạo order, xác minh order và outbox cùng commit.
- Dừng broker trước relay; xác minh row vẫn pending/retry.
- Bật broker lại; xác minh relay gửi event.
- Kill relay sau broker ack nhưng trước mark SENT; xác minh duplicate được consumer dedupe.
- Gửi event sequence 2 trước sequence 1 ở test giả lập; xác minh consumer phát hiện gap hoặc relay giữ thứ tự.
- Gửi payload schema version không hỗ trợ; xác minh quarantine/FAILED policy.

### Bước 7: Chạy nhiều relay instance

- Start ít nhất hai relay.
- Claim batch đồng thời.
- Xác minh lock token và lease không cho hai worker xử lý cùng row bình thường.
- Giả lập worker chết để lease hết hạn.
- Xác minh worker khác claim lại và worker cũ không thể cập nhật trạng thái bằng token cũ.

## 35. Checklist vận hành production

- Business row và outbox row dùng cùng database transaction.
- Event payload là snapshot bất biến, có eventId, eventType và schemaVersion.
- Không gửi broker trực tiếp trong command transaction.
- Relay claim bằng transaction ngắn, publish bên ngoài DB transaction.
- Có lock token, lease và recovery khi lease hết hạn.
- Chỉ mark SENT sau broker confirmation có ý nghĩa.
- Chấp nhận at-least-once và xây consumer inbox/idempotency.
- Có thứ tự per aggregate nếu nghiệp vụ cần.
- Retry có backoff/jitter, FAILED alert và replay audit.
- DLT consumer và outbox relay failure được phân biệt.
- Cleanup chỉ xóa row SENT sau retention.
- CDC connector giữ WAL/binlog đủ lâu nếu dùng Debezium.
- Kiểm thử rollback, broker outage, crash windows, duplicate, ordering và scale.
- Theo dõi oldest pending age, publish errors, retries, FAILED và consumer duplicate.
- Bảo vệ payload, headers, database credentials và broker ACL.

## 36. Những lỗi triển khai phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Ghi DB rồi send broker trong cùng @Transactional | Hai hệ thống vẫn commit độc lập | Ghi outbox cùng DB transaction |
| Dùng AFTER_COMMIT listener mà không lưu publication bền vững | Crash sau commit có thể làm mất event | Persist outbox row trước commit |
| Giữ row lock trong khi gọi broker | Transaction DB dài, lock contention | Claim/commit rồi publish riêng |
| Mark SENT trước send | Có thể mất event | Chỉ mark sau confirmation |
| Mark SENT khi async send mới được enqueue | Broker có thể chưa ack | Dùng sync/confirmation callback |
| Không dùng event ID | Duplicate không thể dedupe ổn định | Event ID duy nhất, inbox unique constraint |
| Inbox insert ngoài business transaction | Marker có thể commit nhưng side effect rollback | Ghi inbox và side effect cùng transaction |
| Nhiều worker bỏ qua aggregate ordering | Event đến sai thứ tự | Sequence, per-aggregate claim và key |
| Xóa row PENDING/FAILED | Mất khả năng replay | Cleanup chỉ row SENT sau retention |
| Retry nóng không giới hạn | Tạo tải khi broker đang lỗi | Backoff, jitter, alert và circuit policy |
| CDC connector nhận UPDATE của outbox insert-only | SMT có thể cảnh báo/lỗi | Thiết kế CDC table và lifecycle riêng |
| Coi Kafka EOS là DB+broker atomic | Sai giả định nhất quán | Outbox + idempotent consumer |

## 37. Tài liệu tham khảo

- [Spring Cloud Stream — Producing and Consuming Messages / StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — @Transactional rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [PostgreSQL — SELECT locking clause and SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html)
- [AWS Prescriptive Guidance — Transactional Outbox Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)

API, property và publisher confirmation phụ thuộc release train Spring Cloud Stream, Spring Boot và binder cụ thể. Hãy đối chiếu BOM của ứng dụng, broker version và test với broker thật trước khi phát hành. Ví dụ PostgreSQL dùng JSONB, SKIP LOCKED và SQL RETURNING; nếu dùng MySQL hoặc database khác, điều chỉnh kiểu dữ liệu, locking syntax và CDC connector tương ứng.

## Kết luận

Transactional outbox giải quyết dual write bằng cách ghi **business state và event intent trong cùng database transaction**. Relay hoặc CDC sau đó chuyển event đã commit tới broker. Polling relay qua StreamBridge cần claim bằng lease, publish với confirmation, rồi mark SENT; crash sau broker ack nhưng trước DB update có thể tạo duplicate. Consumer inbox và idempotency xử lý duplicate trong cùng transaction với side effect. Nếu cần thứ tự, dùng aggregate sequence, key/routing ổn định và điều phối relay theo aggregate. Đây là mô hình eventual delivery có thể phục hồi và quan sát được, không phải một distributed transaction exactly-once tự động.
