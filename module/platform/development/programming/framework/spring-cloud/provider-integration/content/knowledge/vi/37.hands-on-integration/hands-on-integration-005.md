# Phối hợp cơ sở dữ liệu với hàng đợi bằng outbox và xử lý lũy đẳng

## 1. Bài toán và mục tiêu

Một nghiệp vụ trong Spring Boot thường phải cập nhật dữ liệu và phát một message để dịch vụ khác tiếp tục xử lý. Ví dụ:

- Tạo đơn hàng trong database rồi gửi sự kiện OrderCreated.
- Ghi nhận tài liệu đã upload rồi gửi DocumentReady tới worker OCR.
- Cập nhật trạng thái thanh toán rồi phát PaymentCaptured.
- Thay đổi thông tin khách hàng rồi thông báo tới hệ thống tìm kiếm hoặc analytics.

Nếu ứng dụng ghi database và publish message bằng hai thao tác độc lập, có thể xảy ra lỗi dual write: database đã commit nhưng message không được gửi, hoặc message đã được gửi nhưng transaction database rollback. Hai hệ thống khi đó không còn đồng bộ.

Bài thực hành này xây dựng cơ chế phối hợp đáng tin cậy bằng **Transactional Outbox** ở phía producer và **Inbox/Idempotent Consumer** ở phía consumer. Outbox lưu sự kiện trong cùng transaction với dữ liệu nghiệp vụ; relay gửi sự kiện tới broker sau khi transaction commit. Consumer lưu dấu sự kiện đã xử lý và cập nhật dữ liệu nghiệp vụ trong cùng transaction.

Triển khai cùng một hợp đồng nghiệp vụ trên ba hệ sinh thái:

- **AWS:** Spring Boot + relational database + Amazon SQS, dùng AWS SDK for Java 2.x hoặc Spring Cloud AWS.
- **Google Cloud:** Spring Boot + relational database + Pub/Sub, dùng Spring Framework on Google Cloud.
- **Azure:** Spring Boot + relational database + Azure Service Bus, dùng Spring Cloud Azure.

Các thành phần database, broker và worker không nằm trong cùng một distributed transaction. Vì vậy, outbox không làm cho toàn hệ thống có exactly-once processing tuyệt đối. Mô hình được thiết kế để message có thể được gửi lại, còn consumer tạo hiệu ứng nghiệp vụ idempotent.

Sau khi hoàn thành, bạn có thể:

- Giải thích các failure window của dual write.
- Thiết kế outbox table và ghi event cùng transaction với dữ liệu nghiệp vụ.
- Viết polling relay sử dụng lease và FOR UPDATE SKIP LOCKED.
- Phân biệt polling relay với CDC/Debezium.
- Publish message tới SQS, Pub/Sub và Service Bus bằng event ID ổn định.
- Xây consumer inbox với unique constraint.
- Đặt transaction boundary để ACK chỉ sau khi database commit.
- Xử lý duplicate delivery, retry, DLQ và replay.
- Giữ thứ tự theo aggregate khi nghiệp vụ yêu cầu.
- Kết hợp idempotency của broker với idempotency ở tầng nghiệp vụ.
- Kiểm thử các tình huống crash trước/sau publish và trước/sau commit.

> **Phạm vi:** Ví dụ SQL dùng PostgreSQL và Spring Boot với JDBC/JPA ở mức minh họa. Hãy chọn phiên bản Spring Cloud AWS, Spring Framework on Google Cloud và Spring Cloud Azure tương thích với Spring Boot của dự án; không trộn BOM giữa các provider. Các đoạn code tập trung vào ranh giới transaction và API chính, một số repository/model là abstraction cần hoàn thiện theo ứng dụng.

## 2. Dual write và các cửa sổ lỗi

### 2.1. Cách viết dễ gặp lỗi

Một service thường bắt đầu bằng cách lưu dữ liệu rồi gửi message:

~~~java
@Transactional
public Order createOrder(CreateOrderRequest request) {
    Order order = orderRepository.save(Order.from(request));

    sqsClient.sendMessage(builder -> builder
            .queueUrl(queueUrl)
            .messageBody(toJson(new OrderCreated(order.getId()))));

    return order;
}
~~~

Đoạn code này có hai vấn đề:

1. Database và broker không dùng chung transaction manager.
2. @Transactional chỉ quản lý transaction của database; nó không rollback message đã được broker chấp nhận.

Nếu publish xảy ra trước khi database commit, consumer có thể nhận event trong lúc record chưa tồn tại. Nếu publish sau commit, process có thể chết trước khi gửi message.

### 2.2. Hai failure window

~~~mermaid
sequenceDiagram
    participant API as Spring Boot
    participant DB as Database
    participant MQ as Message broker
    participant C as Consumer

    API->>DB: INSERT order
    DB-->>API: Commit
    Note over API: Process crash trước publish
    API-xMQ: Không gửi OrderCreated
    Note over DB,MQ: Order tồn tại, event bị mất

    API->>DB: INSERT order
    API->>MQ: Publish OrderCreated
    MQ-->>API: Accepted
    MQ->>C: Deliver event
    C->>DB: Đọc order
    Note over API,DB: Database transaction rollback
    Note over DB,MQ: Event đã gửi, dữ liệu nghiệp vụ không tồn tại
~~~

| Thứ tự | Lỗi | Kết quả |
| --- | --- | --- |
| Commit DB → crash → publish | Process chết sau commit | Dữ liệu tồn tại nhưng không có event |
| Publish → rollback DB | Transaction thất bại sau khi broker nhận message | Consumer nhận event không có dữ liệu tương ứng |
| Publish thành công → timeout response | Broker đã nhận nhưng producer không biết kết quả | Producer có thể gửi lại, tạo duplicate |
| Consumer commit → crash trước ACK | DB đã cập nhật nhưng message chưa được ACK | Broker giao lại, consumer có thể chạy lần nữa |

### 2.3. Vì sao không dùng distributed transaction?

Có thể nghĩ đến XA/2PC để phối hợp database và broker. Tuy nhiên, không phải mọi broker và database đều hỗ trợ cùng một transaction coordinator; distributed transaction tăng độ phức tạp, latency, coupling và failure modes.

Transactional outbox dùng transaction cục bộ của database để lưu đồng thời:

- Thay đổi dữ liệu nghiệp vụ.
- Bản ghi mô tả message cần phát.

Một relay riêng đọc outbox và gửi message. Nếu relay chết, event vẫn còn trong database để gửi lại. Nếu broker đã nhận message nhưng relay chưa kịp đánh dấu đã gửi, relay gửi lại cùng event ID; consumer xử lý duplicate an toàn.

## 3. Kiến trúc Transactional Outbox và Inbox

### 3.1. Luồng tổng thể

~~~mermaid
flowchart LR
    CMD["HTTP command"] --> SVC["Spring Boot service"]
    SVC --> TX["One DB transaction"]
    TX --> BIZ["Business tables"]
    TX --> OUT["Outbox table"]
    OUT --> RELAY["Polling relay / CDC"]
    RELAY --> BROKER["SQS / Pub/Sub / Service Bus"]
    BROKER --> CONSUMER["Spring Boot consumer"]
    CONSUMER --> ITX["One consumer DB transaction"]
    ITX --> INBOX["Inbox / processed_messages"]
    ITX --> EFFECT["Business state changes"]
~~~

### 3.2. Vai trò từng thành phần

| Thành phần | Trách nhiệm |
| --- | --- |
| Business service | Thực hiện command và quyết định event nghiệp vụ cần phát |
| Business database | Lưu trạng thái nghiệp vụ |
| Outbox table | Lưu event trong cùng transaction với trạng thái nghiệp vụ |
| Relay | Đọc outbox, publish tới broker, ghi nhận trạng thái gửi |
| Broker | Lưu và phân phối message theo delivery semantics của provider |
| Consumer inbox | Nhận diện event đã xử lý theo consumer và event ID |
| Consumer transaction | Ghi inbox marker và cập nhật business state cùng transaction |
| Retry/DLQ | Giữ và phân loại lỗi để retry hoặc điều tra |

### 3.3. Các bảo đảm và giới hạn

| Mô hình | Bảo đảm chính | Giới hạn |
| --- | --- | --- |
| Transactional outbox | Business update và event record cùng commit hoặc cùng rollback | Relay có thể publish lặp |
| Polling relay | Event chưa publish vẫn nằm trong database | Có polling latency và query load |
| CDC relay | Đọc thay đổi đã commit từ transaction log | Cần connector/CDC infrastructure |
| Consumer inbox | Duplicate event không lặp lại DB side effect trong cùng transaction | Không tự bảo vệ side effect ở hệ thống ngoài |
| Broker deduplication | Giảm duplicate publish/delivery theo khả năng provider | Có giới hạn về thời gian, scope và semantics |
| End-to-end exactly once | Không được suy ra chỉ từ outbox hoặc broker | Cần idempotency cho từng side effect và ranh giới hệ thống |

Cách diễn đạt chính xác là: **producer phát event theo at-least-once; consumer có thể đạt hiệu ứng nghiệp vụ idempotent trong database của nó**. Nếu consumer gọi payment gateway, email hoặc API ngoài, phải dùng idempotency key, outbox tiếp theo hoặc saga phù hợp.

## 4. Thiết kế outbox table

### 4.1. Schema

Một outbox record nên có ID ổn định, aggregate key, loại event, payload và trạng thái relay:

~~~sql
CREATE TABLE outbox_events (
    event_id           UUID PRIMARY KEY,
    aggregate_type     VARCHAR(100) NOT NULL,
    aggregate_id       VARCHAR(200) NOT NULL,
    aggregate_version  BIGINT,
    event_type         VARCHAR(200) NOT NULL,
    schema_version     INTEGER NOT NULL DEFAULT 1,
    correlation_id     VARCHAR(200),
    payload            JSONB NOT NULL,
    occurred_at        TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    published_at       TIMESTAMPTZ,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner        VARCHAR(128),
    lease_until        TIMESTAMPTZ,
    last_error         VARCHAR(2000),
    status             VARCHAR(24) NOT NULL DEFAULT 'PENDING'
);
~~~

Ý nghĩa các field:

- event_id: UUID duy nhất, giữ nguyên qua mọi lần retry và replay.
- aggregate_type: loại aggregate, ví dụ Order, Document.
- aggregate_id: khóa aggregate để giữ thứ tự theo entity nếu cần.
- aggregate_version: phiên bản nghiệp vụ tăng dần của aggregate.
- event_type: tên event như OrderCreated, DocumentReady.
- schema_version: phiên bản payload để consumer có thể nâng cấp tương thích.
- payload: dữ liệu event cần thiết cho consumer.
- published_at: chỉ ghi sau khi broker xác nhận publish.
- attempt_count, next_attempt_at: retry policy của relay.
- lease_owner, lease_until: tránh nhiều relay claim cùng một record.
- last_error: thông tin lỗi đã được làm sạch, không chứa secret.
- status: PENDING, IN_FLIGHT, PUBLISHED hoặc DEAD.

Có thể tách trạng thái thành published_at và lease mà không cần cột status; chọn một quy ước nhất quán và dùng unique/partial index phù hợp.

### 4.2. Index cho relay

Với PostgreSQL:

~~~sql
CREATE INDEX idx_outbox_pending
    ON outbox_events (next_attempt_at, created_at)
    WHERE published_at IS NULL
      AND status IN ('PENDING', 'IN_FLIGHT');

CREATE INDEX idx_outbox_aggregate_order
    ON outbox_events (aggregate_type, aggregate_id, aggregate_version);
~~~

Outbox là bảng hàng đợi trong database. Nếu không có index, relay phải quét nhiều row đã publish. Nếu lưu lâu dài, dung lượng và vacuum/maintenance có thể tăng đáng kể.

### 4.3. Event payload là contract

Không serialize nguyên entity JPA rồi gửi đi. Entity có thể chứa lazy relationship, field nội bộ, secret hoặc cấu trúc thay đổi theo schema database.

Tạo event DTO rõ ràng:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderCreatedPayload(
        UUID orderId,
        String customerId,
        long totalAmountMinor,
        String currency,
        Instant createdAt) {
}

public record EventEnvelope<T>(
        UUID eventId,
        String aggregateType,
        String aggregateId,
        Long aggregateVersion,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String correlationId,
        T payload) {
}
~~~

Payload nên chứa đủ dữ liệu để consumer xử lý mà không cần đọc tùy tiện database của producer. Nếu payload chỉ chứa ID, consumer phải gọi API producer; khi đó cần tính tới producer downtime, quyền truy cập và version hiện tại có thể đã khác event.

Không đưa access token, password, signed URL hoặc dữ liệu cá nhân không cần thiết vào event. Event thường được lưu ở database, broker, log và DLQ trong một thời gian dài hơn request ban đầu.

## 5. Ghi business data và outbox trong cùng transaction

### 5.1. Service method

Điều kiện cốt lõi là business repository và outbox repository dùng cùng database và cùng transaction manager:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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
    public Order create(CreateOrderRequest request) {
        Order order = orders.save(Order.from(request));

        UUID eventId = UUID.randomUUID();
        OrderCreatedPayload payload = new OrderCreatedPayload(
                order.getId(),
                order.getCustomerId(),
                order.getTotalAmountMinor(),
                order.getCurrency(),
                Instant.now());
        String correlationId = request.correlationId() != null
                ? request.correlationId()
                : eventId.toString();

        outbox.insert(
                eventId,
                "Order",
                order.getId().toString(),
                order.getVersion(),
                "OrderCreated",
                1,
                correlationId,
                writeJson(payload),
                Instant.now());

        return order;
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize event", ex);
        }
    }
}
~~~

Nếu serialization lỗi, exception làm transaction rollback. Nếu insert outbox lỗi, thay đổi order cũng rollback. Nếu transaction commit, cả hai cùng tồn tại.

### 5.2. Repository insert

Ví dụ dùng NamedParameterJdbcTemplate và PostgreSQL JSONB:

~~~java
import java.sql.Timestamp;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OutboxRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(
            UUID eventId,
            String aggregateType,
            String aggregateId,
            Long aggregateVersion,
            String eventType,
            int schemaVersion,
            String correlationId,
            String payloadJson,
            java.time.Instant occurredAt) {

        String sql = """
            INSERT INTO outbox_events (
                event_id, aggregate_type, aggregate_id,
                aggregate_version, event_type, schema_version, correlation_id,
                payload, occurred_at, created_at, status
            )
            VALUES (
                :eventId, :aggregateType, :aggregateId,
                :aggregateVersion, :eventType, :schemaVersion, :correlationId,
                CAST(:payload AS jsonb), :occurredAt, now(), 'PENDING'
            )
            """;

        jdbc.update(sql, Map.of(
                "eventId", eventId,
                "aggregateType", aggregateType,
                "aggregateId", aggregateId,
                "aggregateVersion", aggregateVersion,
                "eventType", eventType,
                "schemaVersion", schemaVersion,
                "correlationId", correlationId,
                "payload", payloadJson,
                "occurredAt", Timestamp.from(occurredAt)));
    }
}
~~~

Đây là code minh họa; Map.of không nhận giá trị null. Nếu aggregateVersion có thể null, dùng MapSqlParameterSource hoặc một giá trị version bắt buộc.

Trong ví dụ service, CreateOrderRequest được giả định có correlationId tùy chọn lấy từ request header hoặc tracing context. Nếu không có, eventId được dùng làm correlation ID dự phòng.

### 5.3. Các lỗi thiết kế cần tránh

- Gọi broker bên trong transaction database rồi hy vọng rollback được cả hai.
- Dùng @TransactionalEventListener(AFTER_COMMIT) làm cơ chế duy nhất để publish. Process có thể chết sau commit nhưng trước khi listener chạy.
- Ghi outbox bằng một datasource hoặc transaction manager khác với business update.
- Tạo event trước khi biết transaction đã thành công và gửi trực tiếp.
- Serialize toàn bộ JPA entity.
- Xóa outbox row ngay sau khi publish mà không có retention/audit/recovery policy.

@TransactionalEventListener(AFTER_COMMIT) vẫn hữu ích để đánh thức relay sớm nhằm giảm latency, nhưng polling/CDC vẫn phải là cơ chế đảm bảo event không bị mất.

## 6. Polling relay: claim, publish và mark

### 6.1. Quy trình relay

Một relay đơn giản có thể polling liên tục:

1. Mở transaction ngắn và claim một batch event chưa publish.
2. Ghi lease_owner, lease_until, tăng attempt count.
3. Commit transaction claim.
4. Publish message ra broker bên ngoài transaction database.
5. Chờ broker xác nhận nhận message.
6. Ghi published_at, status = PUBLISHED và xóa lease.
7. Nếu publish thất bại, ghi lỗi, tính next_attempt_at và giải phóng lease.

Không giữ transaction database mở trong lúc chờ network tới broker.

~~~mermaid
sequenceDiagram
    participant R as Outbox relay
    participant DB as Database
    participant MQ as Broker

    R->>DB: Claim pending rows + lease
    DB-->>R: Batch event records
    R->>MQ: Publish eventId + payload
    MQ-->>R: Broker accepted
    R->>DB: Mark PUBLISHED
    DB-->>R: Commit
~~~

### 6.2. Claim batch với SKIP LOCKED

Ví dụ SQL PostgreSQL:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_events
    WHERE published_at IS NULL
      AND status IN ('PENDING', 'IN_FLIGHT')
      AND next_attempt_at <= now()
      AND (lease_until IS NULL OR lease_until < now())
    ORDER BY created_at, event_id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_events o
SET status = 'IN_FLIGHT',
    lease_owner = :worker_id,
    lease_until = now() + interval '60 seconds',
    attempt_count = attempt_count + 1
FROM candidates c
WHERE o.event_id = c.event_id
RETURNING o.*;
~~~

FOR UPDATE SKIP LOCKED cho phép nhiều relay cùng lấy batch mà không claim cùng row. Lease giúp phục hồi row khi relay process chết.

Chọn lease dài hơn thời gian publish dự kiến cho batch. Nếu batch có thể kéo dài, chia nhỏ batch hoặc gia hạn lease. Khi đánh dấu published, luôn kiểm tra lease_owner để worker cũ không ghi đè trạng thái của worker đã claim lại row.

### 6.3. Publish ngoài transaction và cập nhật trạng thái

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class OutboxRelay {

    private final TransactionTemplate transactionTemplate;
    private final OutboxRepository outbox;
    private final EventPublisher publisher;
    private final String workerId = java.util.UUID.randomUUID().toString();

    public OutboxRelay(
            TransactionTemplate transactionTemplate,
            OutboxRepository outbox,
            EventPublisher publisher) {
        this.transactionTemplate = transactionTemplate;
        this.outbox = outbox;
        this.publisher = publisher;
    }

    public void runBatch() {
        List<OutboxRecord> batch = transactionTemplate.execute(
                status -> outbox.claim(workerId, 50, Duration.ofSeconds(60)));

        if (batch == null || batch.isEmpty()) {
            return;
        }

        for (OutboxRecord event : batch) {
            try {
                publisher.publish(event).toCompletableFuture().join();

                transactionTemplate.executeWithoutResult(status ->
                        outbox.markPublished(event.eventId(), workerId, Instant.now()));
            }
            catch (Exception ex) {
                transactionTemplate.executeWithoutResult(status ->
                        outbox.scheduleRetry(
                                event.eventId(),
                                workerId,
                                retryTime(event.attemptCount()),
                                safeError(ex)));
            }
        }
    }

    private Instant retryTime(int attempt) {
        long seconds = Math.min(300, 1L << Math.min(attempt, 8));
        return Instant.now().plusSeconds(seconds);
    }

    private String safeError(Exception ex) {
        return ex.getClass().getSimpleName();
    }
}
~~~

Các kiểu OutboxRecord, EventPublisher và phương thức repository là abstraction minh họa. Trong production:

- Dùng bounded executor/concurrency; không tạo thread không giới hạn.
- Tính exponential backoff có jitter.
- Không lưu exception message có thể chứa credential hoặc payload nhạy cảm.
- Cập nhật row với điều kiện event_id và lease_owner khớp.
- Xử lý null hoặc publish future thất bại đúng cách.
- Có shutdown hook để ngừng claim mới và chờ batch đang chạy trong giới hạn.

### 6.4. Cửa sổ duplicate của relay

Giả sử broker đã nhận message nhưng relay chết trước khi ghi published_at:

~~~mermaid
sequenceDiagram
    participant R as Relay
    participant MQ as Broker
    participant DB as Outbox DB

    R->>MQ: Publish event E
    MQ-->>R: Accepted
    Note over R: Process crash
    Note over DB: E vẫn chưa PUBLISHED
    R->>MQ: Retry publish event E
    MQ-->>R: Accepted
    Note over MQ: Có thể tồn tại hai delivery
~~~

Đây là hành vi mong đợi. Relay phải publish lại vì không thể biết chắc broker đã nhận message khi không có xác nhận bền vững được lưu vào database. Giữ nguyên event_id để consumer nhận diện duplicate.

Không đánh dấu PUBLISHED trước khi broker xác nhận. Làm vậy có thể mất event nếu publish thất bại sau khi database đã đánh dấu hoàn tất.

### 6.5. Retry và trạng thái DEAD

Sau số lần thử tối đa, chuyển event sang DEAD, giữ payload và lỗi đã làm sạch, phát alert. Không xóa row lỗi một cách im lặng.

Quy trình replay:

1. Điều tra broker, network, credential và payload.
2. Sửa nguyên nhân.
3. Kiểm tra consumer có thể xử lý event.
4. Đưa row về PENDING, reset next_attempt_at và giữ nguyên event_id.
5. Ghi audit người replay và thời điểm.
6. Theo dõi kết quả publish và consumer.

Nếu event không còn hợp lệ theo nghiệp vụ, đánh dấu CANCELLED với lý do và audit.

## 7. CDC relay với Debezium

### 7.1. Khi nào dùng CDC?

Thay vì polling outbox table, CDC (Change Data Capture) đọc transaction log của database:

- PostgreSQL: logical decoding/WAL.
- MySQL: binlog.
- Một số database khác: transaction log hoặc change stream tương ứng.

Debezium connector theo dõi outbox table và phát event tới Kafka. Outbox Event Router SMT biến row insert thành event message với metadata và payload phù hợp.

~~~mermaid
flowchart LR
    APP["Spring Boot transaction"] --> DB["Database + outbox"]
    DB --> LOG["WAL / binlog"]
    LOG --> CDC["Debezium connector"]
    CDC --> SMT["Outbox Event Router SMT"]
    SMT --> KAFKA["Kafka topic"]
    KAFKA --> BRIDGE["Sink / bridge / downstream"]
    BRIDGE --> CLOUDMQ["SQS / Pub/Sub / Service Bus"]
~~~

Debezium Outbox Event Router mặc định sử dụng các field:

| Field | Vai trò |
| --- | --- |
| id | Unique event ID; thường được đưa vào header |
| aggregatetype | Định tuyến topic theo loại aggregate |
| aggregateid | Event key; có thể làm message key để giữ thứ tự trong Kafka partition |
| type | Loại event nghiệp vụ |
| payload | Nội dung event |

Outbox nên được xem là insert-only. Không cập nhật payload của một event đã phát. Có thể dùng custom column để mang schema version, timestamp hoặc correlation ID.

Schema minh họa ở phần trước đặt tên cột theo kiểu snake_case (event_id, aggregate_type, aggregate_id, event_type). Nếu dùng cấu hình mặc định của Debezium, hãy đổi tên cột theo schema mặc định hoặc cấu hình các SMT option như table.field.event.id, route.by.field và table.field.event.key để map tên cột thực tế. Không giả định SMT tự nhận diện mọi alias.

### 7.2. CDC không tự động gửi đến mọi managed queue

Debezium Outbox Event Router thường phát ra Kafka topic. Nếu đích cuối là SQS, Pub/Sub hoặc Service Bus, cần connector sink, bridge hoặc publisher service phù hợp. Không giả định bật SMT là database có thể publish trực tiếp tới bất kỳ cloud queue nào.

### 7.3. Polling hay CDC?

| Tiêu chí | Polling relay | CDC/Debezium |
| --- | --- | --- |
| Triển khai ban đầu | Đơn giản, nằm trong ứng dụng | Cần connector và hạ tầng CDC |
| Độ trễ | Theo chu kỳ polling | Gần thời gian thực sau commit |
| Database load | Query/index và update lease | Đọc transaction log, cần retention/replication config |
| Scale | Nhiều relay dùng lease/SKIP LOCKED | Scale connector/partition và downstream |
| Vận hành | Theo dõi backlog và lease | Theo dõi connector lag, slot/binlog retention |
| Phù hợp | Workload vừa, muốn ít thành phần | Throughput lớn, nhiều consumer hoặc đã có Kafka/CDC |

Polling là điểm khởi đầu tốt cho lab. CDC phù hợp khi tổ chức đã vận hành Kafka Connect/Debezium hoặc cần giảm polling load. Cả hai vẫn phải xử lý duplicate và consumer idempotency.

## 8. Chuẩn hóa event và publisher cho ba provider

### 8.1. Hợp đồng publisher

Tạo abstraction nhỏ:

~~~java
import java.util.concurrent.CompletionStage;

public interface EventPublisher {
    CompletionStage<Void> publish(OutboxRecord event);
}
~~~

publish chỉ hoàn thành khi client nhận xác nhận thành công từ broker API. Nếu kết quả không rõ vì timeout, relay coi là chưa chắc chắn và retry cùng event_id.

### 8.2. AWS SQS publisher

Dùng AWS SDK for Java 2.x:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;
import software.amazon.awssdk.services.sqs.model.MessageAttributeValue;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

public class SqsEventPublisher implements EventPublisher {

    private final SqsAsyncClient sqs;
    private final ObjectMapper mapper;
    private final String queueUrl;

    public SqsEventPublisher(
            SqsAsyncClient sqs,
            ObjectMapper mapper,
            String queueUrl) {
        this.sqs = sqs;
        this.mapper = mapper;
        this.queueUrl = queueUrl;
    }

    @Override
    public CompletionStage<Void> publish(OutboxRecord event) {
        try {
            String body = mapper.writeValueAsString(event.envelope());

            SendMessageRequest request = SendMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .messageBody(body)
                    .messageAttributes(Map.of(
                            "eventId", MessageAttributeValue.builder()
                                    .dataType("String")
                                    .stringValue(event.eventId().toString())
                                    .build()))
                    .build();

            return sqs.sendMessage(request).thenApply(response -> null);
        }
        catch (Exception ex) {
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

Ví dụ trên dành cho SQS Standard. Với FIFO queue, bổ sung:

- messageGroupId: thường là aggregate_id để giữ thứ tự trong aggregate.
- messageDeduplicationId: dùng event_id ổn định.
- Nếu bật content-based deduplication, SQS tạo ID từ body; hãy cân nhắc khi payload có field thay đổi giữa lần retry.

SQS FIFO loại duplicate send trong cửa sổ deduplication 5 phút. Đây là lớp bảo vệ bổ sung cho producer, không thay consumer inbox và không biến side effect ở database/API ngoài thành exactly-once.

### 8.3. Google Pub/Sub publisher

Spring Framework on Google Cloud cung cấp PubSubTemplate. Ví dụ đơn giản publish JSON envelope:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.Map;

public class PubSubEventPublisher implements EventPublisher {

    private final PubSubTemplate pubSubTemplate;
    private final ObjectMapper mapper;
    private final String topic;

    public PubSubEventPublisher(
            PubSubTemplate pubSubTemplate,
            ObjectMapper mapper,
            String topic) {
        this.pubSubTemplate = pubSubTemplate;
        this.mapper = mapper;
        this.topic = topic;
    }

    @Override
    public CompletionStage<Void> publish(OutboxRecord event) {
        try {
            String payload = mapper.writeValueAsString(event.envelope());

            Map<String, String> headers = Map.of(
                    "eventId", event.eventId().toString(),
                    GcpPubSubHeaders.ORDERING_KEY, event.aggregateId());

            return pubSubTemplate.publish(topic, payload, headers)
                    .thenApply(messageId -> null);
        }
        catch (Exception ex) {
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

Đưa eventId vào payload và header để consumer có thể dedupe. Header ORDERING_KEY dùng aggregate_id; bật message ordering trong publisher và cấu hình regional endpoint khi nhiều publisher cần cùng thứ tự. Ví dụ này dùng API publish trả CompletableFuture của Spring Framework on Google Cloud 5.6.x; ở release cũ trả ListenableFuture thì bridge bằng callback tương ứng.

Pub/Sub hỗ trợ exactly-once delivery cho pull subscriptions trong cùng một region. Điều đó xác nhận việc ACK và tránh một số redelivery của cùng Pub/Sub message ID; nó không ngăn producer publish cùng một event hai lần với hai message ID khác nhau. Inbox theo eventId nghiệp vụ vẫn cần thiết.

### 8.4. Azure Service Bus publisher

Có thể dùng Azure SDK Java hoặc Spring Messaging Azure Service Bus. Ví dụ SDK:

~~~java
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class ServiceBusEventPublisher implements EventPublisher {

    private final ServiceBusSenderClient sender;
    private final ObjectMapper mapper;

    public ServiceBusEventPublisher(
            ServiceBusSenderClient sender,
            ObjectMapper mapper) {
        this.sender = sender;
        this.mapper = mapper;
    }

    @Override
    public CompletionStage<Void> publish(OutboxRecord event) {
        try {
            String body = mapper.writeValueAsString(event.envelope());

            ServiceBusMessage message = new ServiceBusMessage(body)
                    .setMessageId(event.eventId().toString())
                    .setSubject(event.eventType())
                    .setCorrelationId(event.correlationId());

            sender.sendMessage(message);
            return CompletableFuture.completedFuture(null);
        }
        catch (Exception ex) {
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

Đây là ví dụ đồng bộ được bọc trong CompletionStage để minh họa contract; adapter production nên dùng async sender nếu relay cần concurrency cao. Tạo sender bằng ServiceBusClientBuilder và DefaultAzureCredential, không hardcode SAS connection string.

Khi queue/topic bật duplicate detection, MessageId phải ổn định qua retry. Nếu dùng Service Bus Sessions để giữ thứ tự theo aggregate, đặt SessionId bằng aggregate_id và cấu hình entity hỗ trợ sessions.

### 8.5. Spring configuration và workload identity

- AWS: dùng SqsAsyncClient được cấu hình theo region và default credentials provider; runtime role có sqs:SendMessage đúng queue.
- GCP: dùng ADC/service account hoặc Workload Identity; publisher cần roles/pubsub.publisher trên topic.
- Azure: dùng managed identity/workload identity; principal cần Azure Service Bus Data Sender trên queue/topic scope.

Không lưu access key, service account JSON hoặc SAS connection string trong source code. Dùng secret manager/secret store nếu có credential cần cấu hình.

## 9. Giữ thứ tự event theo aggregate

### 9.1. Vì sao ORDER BY created_at chưa đủ?

Hai relay worker có thể claim hai event của cùng một aggregate và publish theo thứ tự khác nhau:

~~~text
Order-42, version 10 -> worker A (publish chậm)
Order-42, version 11 -> worker B (publish nhanh)
Broker nhận version 11 trước version 10
~~~

Nếu consumer áp dụng trạng thái theo thứ tự, dữ liệu có thể bị lùi hoặc sai.

### 9.2. Các cơ chế giữ thứ tự

- Gán aggregate_version tăng dần trong cùng transaction với aggregate update.
- Chỉ claim event tiếp theo của một aggregate khi event trước đã publish.
- Partition hoặc group theo aggregate_id.
- Consumer kiểm tra version và từ chối cập nhật lùi version.
- Nếu thứ tự không quan trọng, cho phép xử lý song song để tăng throughput.

Provider hỗ trợ cơ chế riêng:

| Provider | Cơ chế |
| --- | --- |
| SQS FIFO | MessageGroupId = aggregate_id; message trong group được xử lý theo thứ tự |
| Pub/Sub | Ordering key = aggregate_id; cần enable ordering và cùng region |
| Azure Service Bus | Sessions; SessionId = aggregate_id |

Broker ordering chỉ kiểm soát thứ tự theo semantics của broker. Nếu relay đã publish version 11 trước version 10 thì broker không thể tự sửa lại thứ tự gốc. Relay phải bảo đảm publish sequence hoặc consumer phải kiểm tra aggregate version.

### 9.3. Claim event kế tiếp

Một cách minh họa là không claim event nếu cùng aggregate còn event cũ chưa publish:

~~~sql
SELECT o.event_id
FROM outbox_events o
WHERE o.published_at IS NULL
  AND o.status = 'PENDING'
  AND o.next_attempt_at <= now()
  AND NOT EXISTS (
      SELECT 1
      FROM outbox_events earlier
      WHERE earlier.aggregate_type = o.aggregate_type
        AND earlier.aggregate_id = o.aggregate_id
        AND earlier.aggregate_version < o.aggregate_version
        AND earlier.published_at IS NULL
  )
ORDER BY o.created_at
LIMIT :batch_size
FOR UPDATE SKIP LOCKED;
~~~

Đây là SQL định hướng; khi triển khai cần kết hợp update lease trong cùng transaction claim. Nếu event cũ chuyển DEAD, phải có policy rõ ràng: chặn aggregate, bỏ qua có audit hoặc sửa/replay event cũ. Không để một event chết âm thầm làm hệ thống chờ vô hạn.

## 10. Consumer Inbox và xử lý lũy đẳng

### 10.1. Inbox schema

Consumer cần lưu event đã xử lý theo consumer name và event ID:

~~~sql
CREATE TABLE processed_messages (
    consumer_name  VARCHAR(128) NOT NULL,
    event_id       UUID NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    outcome        VARCHAR(32) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

consumer_name cho phép nhiều consumer độc lập xử lý cùng một event. Ví dụ billing-projection và search-indexer có thể cùng nhận OrderCreated nhưng có inbox riêng.

### 10.2. Insert inbox và cập nhật business state trong một transaction

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderEventConsumer {

    private final JdbcTemplate jdbc;
    private final CustomerProjectionRepository projection;

    public OrderEventConsumer(
            JdbcTemplate jdbc,
            CustomerProjectionRepository projection) {
        this.jdbc = jdbc;
        this.projection = projection;
    }

    @Transactional
    public void handle(EventEnvelope<OrderCreatedPayload> event) {
        int inserted = jdbc.update("""
                INSERT INTO processed_messages (
                    consumer_name, event_id, outcome
                )
                VALUES (?, ?, 'STARTED')
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """,
                "billing-projection",
                event.eventId());

        if (inserted == 0) {
            return;
        }

        projection.applyOrderCreated(event.payload());

        jdbc.update("""
                UPDATE processed_messages
                SET outcome = 'COMPLETED',
                    processed_at = now()
                WHERE consumer_name = ?
                  AND event_id = ?
                """,
                "billing-projection",
                event.eventId());
    }
}
~~~

Cả insert inbox và business update nằm trong cùng transaction:

- Nếu business update lỗi, inbox insert rollback; broker có thể giao lại để retry.
- Nếu transaction commit nhưng process chết trước ACK, broker giao lại; insert inbox bị conflict và consumer bỏ qua side effect.
- Nếu event được gửi hai lần với cùng event ID, consumer chỉ áp dụng business update một lần.

ON CONFLICT DO NOTHING trả số row update bằng 0 khi event đã được ghi nhận. Cách xử lý unique conflict cần phù hợp database đang dùng.

### 10.3. ACK sau commit

Listener gọi một service @Transactional qua Spring proxy. Khi method trả về, transaction đã commit hoặc ném exception. Chỉ sau khi method trả về thành công mới ACK/complete message.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant L as Listener
    participant S as Consumer service
    participant DB as Database

    B->>L: Deliver event E
    L->>S: handle(E)
    S->>DB: INSERT inbox(E)
    S->>DB: Apply business update
    S->>DB: COMMIT
    S-->>L: Success
    L->>B: ACK / Complete
    Note over L,B: Nếu crash trước ACK, E được giao lại
    B->>L: Redeliver E
    L->>S: handle(E)
    S->>DB: INSERT inbox(E) -> conflict
    S-->>L: No-op success
    L->>B: ACK / Complete
~~~

Không ACK trước khi transaction commit. Không nuốt exception từ consumer service rồi trả success cho listener nếu database chưa ghi được.

## 11. Spring Boot consumer cho ba broker

### 11.1. AWS SQS với Spring Cloud AWS

Dependency dùng Spring Cloud AWS BOM và SQS starter tương thích:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AWS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>
</dependencies>
~~~

Listener mặc định ON_SUCCESS xác nhận message sau khi xử lý thành công:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderSqsListener {

    private final EventDeserializer deserializer;
    private final OrderEventConsumer consumer;

    public OrderSqsListener(
            EventDeserializer deserializer,
            OrderEventConsumer consumer) {
        this.deserializer = deserializer;
        this.consumer = consumer;
    }

    @SqsListener("${app.queues.order-events}")
    public void receive(String body) {
        EventEnvelope<OrderCreatedPayload> event =
                deserializer.orderCreated(body);

        consumer.handle(event);
    }
}
~~~

Nếu consumer.handle ném exception, listener thất bại và SQS có thể giao lại sau visibility timeout. Cấu hình redrive policy để chuyển message sang DLQ sau số lần nhận tối đa. Với listener dùng manual acknowledgement, chỉ gọi acknowledge() sau khi service transaction đã commit.

### 11.2. Google Pub/Sub

Dependency dùng Spring Framework on Google Cloud Pub/Sub starter. Adapter Spring Integration có thể đặt AckMode.MANUAL:

~~~java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.AckMode;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
public class OrderPubSubConfiguration {

    @Bean
    MessageChannel orderEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    PubSubInboundChannelAdapter orderEventsAdapter(
            MessageChannel orderEventsChannel,
            PubSubTemplate pubSubTemplate) {

        PubSubInboundChannelAdapter adapter =
                new PubSubInboundChannelAdapter(
                        pubSubTemplate,
                        "order-events-subscription");

        adapter.setOutputChannel(orderEventsChannel);
        adapter.setAckMode(AckMode.MANUAL);
        return adapter;
    }
}
~~~

Handler gọi consumer transaction trước khi ACK:

~~~java
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderPubSubHandler {

    private final EventDeserializer deserializer;
    private final OrderEventConsumer consumer;

    public OrderPubSubHandler(
            EventDeserializer deserializer,
            OrderEventConsumer consumer) {
        this.deserializer = deserializer;
        this.consumer = consumer;
    }

    @ServiceActivator(inputChannel = "orderEventsChannel")
    public void receive(Message<String> message) {
        BasicAcknowledgeablePubsubMessage original =
                message.getHeaders().get(
                        GcpPubSubHeaders.ORIGINAL_MESSAGE,
                        BasicAcknowledgeablePubsubMessage.class);

        EventEnvelope<OrderCreatedPayload> event =
                deserializer.orderCreated(message.getPayload());

        consumer.handle(event);
        original.ack();
    }
}
~~~

Nếu consumer.handle ném exception, không ACK. Có thể cấu hình retry policy và dead-letter topic trên subscription. Exactly-once delivery chỉ áp dụng pull subscription trong cùng region; vẫn giữ inbox vì producer có thể publish duplicate event với message ID khác nhau.

### 11.3. Azure Service Bus

Spring Cloud Azure cung cấp @ServiceBusListener và listener container. Ví dụ:

~~~java
import com.azure.spring.messaging.servicebus.annotation.ServiceBusListener;
import org.springframework.stereotype.Component;

@Component
public class OrderServiceBusListener {

    private final EventDeserializer deserializer;
    private final OrderEventConsumer consumer;

    public OrderServiceBusListener(
            EventDeserializer deserializer,
            OrderEventConsumer consumer) {
        this.deserializer = deserializer;
        this.consumer = consumer;
    }

    @ServiceBusListener(destination = "order-events")
    public void receive(String body) {
        EventEnvelope<OrderCreatedPayload> event =
                deserializer.orderCreated(body);

        consumer.handle(event);
    }
}
~~~

Với Peek-Lock mode, listener container settle message sau khi handler thành công theo cấu hình của version đang dùng. Khi consumer transaction ném exception, message cần được abandon/để lock hết hạn để broker giao lại hoặc chuyển DLQ theo delivery count. Kiểm tra auto-complete/settlement mode của Spring Cloud Azure version; không giả định hành vi giống SQS hoặc Pub/Sub.

### 11.4. Cấu hình identity cho consumer

| Provider | Consumer permission |
| --- | --- |
| AWS SQS | sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes trên queue |
| Google Pub/Sub | roles/pubsub.subscriber trên subscription |
| Azure Service Bus | Azure Service Bus Data Receiver trên queue/subscription |

Dùng IAM role, Workload Identity hoặc managed identity theo runtime. Không cấp quyền quản trị broker cho consumer chỉ để nhận message.

## 12. Idempotency ở ngoài database

### 12.1. Inbox chỉ bảo vệ transaction database

Giả sử consumer thực hiện:

1. Ghi inbox và cập nhật projection trong database.
2. Gọi payment gateway.
3. ACK message.

Nếu process chết sau bước 2 nhưng trước ACK, message được giao lại. Inbox có thể cho biết event đã được xử lý và bỏ qua toàn bộ handler, nhưng payment gateway có thể chưa trả response hoặc side effect đã xảy ra.

Giải pháp:

- Gửi idempotency key bằng event_id hoặc business operation ID tới downstream API.
- Lưu kết quả/operation state của external call.
- Dùng outbox thứ hai để tạo command cho integration worker.
- Với quy trình nhiều dịch vụ, thiết kế saga/compensation.
- Nếu downstream không hỗ trợ idempotency, cần reconciliation và quy trình xử lý trạng thái không chắc chắn.

### 12.2. Idempotency key phải đại diện nghiệp vụ

Không dùng timestamp hiện tại hoặc random UUID mới mỗi lần retry. Key phải được tạo một lần và giữ nguyên qua mọi lần thử.

Ví dụ:

~~~text
event_id = 6e4b2a5e-4f87-4c4d-a37a-31c2d8e0a9b4
payment_operation_key = capture:order-4821:version-3
thumbnail_key = document-91:generation-1730000000000000
~~~

Một event có thể tạo nhiều side effect; mỗi side effect cần key riêng nếu có vòng đời và retry độc lập.

### 12.3. Idempotency ở tầng HTTP command

Nếu client retry POST /orders do timeout, ứng dụng có thể tạo hai order và hai event khác nhau. Dùng idempotency key ở API boundary:

- Client gửi Idempotency-Key.
- Server lưu key, request hash và kết quả trong cùng transaction với order/outbox.
- Request lặp cùng key và cùng payload trả lại kết quả cũ.
- Cùng key nhưng payload khác trả lỗi conflict.
- Unique constraint bảo vệ trường hợp nhiều request đồng thời.

Outbox đảm bảo order và event cùng commit; idempotency key bảo vệ việc tạo order trước khi outbox được relay.

## 13. Broker deduplication không thay consumer inbox

Các provider có tính năng giảm duplicate nhưng giới hạn khác nhau:

| Provider | Cơ chế | Phạm vi/giới hạn |
| --- | --- | --- |
| SQS Standard | At-least-once | Có thể giao message trùng; consumer phải idempotent |
| SQS FIFO | MessageDeduplicationId hoặc content-based dedup | Deduplication interval 5 phút; MessageGroupId giữ thứ tự trong group |
| Pub/Sub | Exactly-once delivery tùy chọn | Pull subscription, trong cùng region; duplicate publish với message ID khác vẫn có thể xuất hiện |
| Service Bus | Duplicate detection theo MessageId | Standard/Premium; cửa sổ cấu hình từ 20 giây đến 7 ngày; chủ yếu chặn duplicate ở phía gửi |

Không kết luận exactly once cho toàn bộ ứng dụng chỉ vì queue có deduplication. Broker không thể biết transaction database hoặc API ngoài đã commit side effect nào.

Inbox vẫn cần thiết để xử lý:

- Producer publish lại cùng event.
- Relay timeout không biết broker đã nhận hay chưa.
- Consumer crash sau commit trước ACK.
- Replay từ DLQ.
- Broker deduplication window đã hết hạn.
- Nhiều queue/subscription nhận cùng event.

## 14. Retry, DLQ và replay

### 14.1. Ba lớp retry riêng biệt

| Lớp | Thành phần | Retry cho việc gì |
| --- | --- | --- |
| Producer transaction | HTTP/client command | Retry tạo nghiệp vụ bằng API idempotency key |
| Outbox relay | Outbox row | Retry publish tới broker |
| Consumer | Broker delivery + inbox/job | Retry xử lý message hoặc side effect |

Không nhân số lần retry một cách không kiểm soát. Ví dụ 5 lần relay retry × 10 lần broker delivery × 5 lần downstream retry có thể tạo rất nhiều lần thực thi.

### 14.2. Phân loại lỗi

| Lỗi | Cách xử lý |
| --- | --- |
| Broker timeout/5xx/throttling | Relay retry exponential backoff + jitter |
| Credential hết hạn/403 | Alert, sửa identity; giới hạn retry và tránh retry liên tục |
| Payload schema không hỗ trợ | Đưa vào quarantine/DLQ, giữ event ID và schema version |
| Consumer database tạm thời lỗi | Không ACK; broker giao lại |
| Business validation thất bại vĩnh viễn | Ghi outcome REJECTED và ACK sau khi lưu kết quả |
| Duplicate event | Inbox conflict; ACK/complete sau khi xác nhận đã xử lý |
| Outbox row vượt retry limit | Đánh dấu DEAD, alert và replay có kiểm soát |

### 14.3. DLQ không phải kho lưu trữ vĩnh viễn

Thiết lập DLQ theo provider:

- SQS: redrive policy và maxReceiveCount.
- Pub/Sub: dead-letter topic và quyền publish/subscribe cho service agent/consumer.
- Service Bus: built-in DLQ, theo dõi DeadLetterReason và DeadLetterErrorDescription.

Quy trình replay:

1. Alert khi DLQ hoặc outbox DEAD tăng.
2. Đọc metadata và error category; không log secret.
3. Xác định lỗi payload, permission, downstream hay bug.
4. Sửa nguyên nhân.
5. Kiểm tra consumer inbox và trạng thái nghiệp vụ.
6. Replay bằng cùng event_id.
7. Theo dõi kết quả và ghi audit.

Nếu cần chạy lại logic nghiệp vụ sau khi đã xử lý thành công, tạo một reprocessing command/event mới với ID mới và lý do rõ ràng. Không xóa inbox marker cũ một cách tùy tiện vì có thể tạo duplicate side effect.

## 15. Outbox retention, cleanup và vận hành

### 15.1. Dọn row đã publish

Không cần giữ outbox row mãi mãi, nhưng không xóa ngay sau publish. Chọn retention theo yêu cầu audit và khả năng replay.

Ví dụ xóa row đã publish lâu hơn 14 ngày:

~~~sql
DELETE FROM outbox_events
WHERE published_at < now() - interval '14 days'
  AND status = 'PUBLISHED';
~~~

Chạy cleanup theo batch để tránh transaction quá lớn. Nếu cần audit, archive row hoặc giữ event metadata ở bảng lịch sử.

Không xóa row PENDING, IN_FLIGHT hoặc DEAD chỉ vì đã quá cũ. Cần quy trình reconcile và quyết định nghiệp vụ.

### 15.2. Metrics

Theo dõi:

- outbox_pending_count: số event chờ publish.
- outbox_oldest_pending_age: tuổi event chưa gửi lâu nhất.
- outbox_publish_attempts: số lần thử publish.
- outbox_publish_latency: thời gian từ commit đến broker accepted.
- outbox_dead_count: số row ở trạng thái DEAD.
- consumer_duplicate_count: số event inbox conflict.
- consumer_processing_latency: thời gian xử lý event.
- consumer_retry_count: số lần broker giao lại.
- consumer_dlq_count: message vào DLQ.
- lease_expired_count: số lease relay/consumer hết hạn.

### 15.3. Alert và runbook

Một số điều kiện cảnh báo:

- Pending outbox tăng liên tục hoặc oldest pending age vượt SLA.
- Relay không có heartbeat hoặc không publish thành công trong thời gian dài.
- Outbox DEAD tăng.
- Consumer backlog hoặc age of oldest message tăng.
- DLQ tăng đột biến.
- Duplicate rate tăng bất thường.
- Database connection pool hoặc broker throttling tăng.

Runbook nên trả lời: ai chịu trách nhiệm, cách xem event ID, cách kiểm tra broker delivery, cách replay an toàn và cách đối chiếu business state với consumer projection.

## 16. Bảo mật và quản trị event

- Dùng workload identity thay cho long-lived cloud keys.
- Tách producer publisher role và consumer receiver role.
- Giới hạn quyền theo queue/topic.
- Validate event_type, schema_version, tenant và aggregate ID.
- Không tin tenant ID hoặc URL do client/event gửi nếu không đối chiếu dữ liệu tin cậy.
- Không đưa PII/secret không cần thiết vào payload.
- Mã hóa dữ liệu nhạy cảm và giới hạn retention của outbox, broker và DLQ.
- Redact payload/error trong logs.
- Có audit cho replay, purge, manual state change và thay đổi retry policy.
- Kiểm tra schema compatibility trước khi deploy consumer/producer khác phiên bản.

Outbox chứa bản sao event nghiệp vụ và có thể được đọc bởi relay/operator; áp dụng database grants tối thiểu. Consumer chỉ cần quyền đọc queue/subscription và quyền cần thiết trên database riêng.

## 17. Kiểm thử các failure window

### 17.1. Producer tests

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Business insert thành công, outbox insert thành công | Cả hai commit |
| Business insert thành công, outbox insert lỗi | Cả hai rollback |
| Serialization payload lỗi | Transaction rollback |
| Client retry cùng idempotency key | Không tạo business record/event trùng |
| Hai request đồng thời cùng key | Unique constraint chỉ cho một request tạo mới |

### 17.2. Relay tests

- Relay chết trước khi publish: lease hết hạn và event được claim lại.
- Broker trả timeout: retry cùng event ID.
- Broker nhận message, relay chết trước mark published: duplicate publish được consumer xử lý an toàn.
- Hai relay chạy đồng thời: SKIP LOCKED và lease tránh claim cùng row.
- Lease hết hạn trong lúc publish: worker cũ không được mark row nếu lease owner đã đổi.
- Publish liên tục thất bại: event chuyển DEAD và tạo alert.
- Hai event cùng aggregate: kiểm tra thứ tự publish theo aggregate_version.

### 17.3. Consumer tests

- Event được nhận lần đầu: inbox và business update commit.
- Duplicate cùng event ID: business update không chạy lần hai.
- Consumer lỗi trước commit: inbox và business update rollback.
- Consumer commit rồi crash trước ACK: broker redeliver nhưng inbox no-op.
- Hai consumer instance nhận cùng event đồng thời: unique constraint bảo vệ.
- Event schema version không hỗ trợ: quarantine/DLQ.
- External API timeout sau khi side effect đã xảy ra: retry với idempotency key.

### 17.4. Integration test với broker thật

Dùng database test riêng và queue/topic/subscription test:

1. Gọi API tạo business record.
2. Xác minh outbox row cùng transaction đã commit.
3. Chạy relay và xác minh message xuất hiện trong broker.
4. Gửi cùng event hai lần.
5. Xác minh consumer chỉ áp dụng DB side effect một lần.
6. Dừng relay sau publish nhưng trước mark published; khởi động lại và xác minh duplicate được xử lý.
7. Dừng consumer sau commit trước ACK; xác minh redelivery không tạo side effect lặp.
8. Làm broker tạm thời unavailable; xác minh outbox giữ event và retry.
9. Làm consumer thất bại nhiều lần; xác minh DLQ.
10. Replay cùng event ID và xác minh inbox bảo vệ nghiệp vụ.
11. Kiểm tra ordering cho cùng aggregate nếu bật FIFO/session/ordering key.
12. Kiểm tra metrics, logs và audit.

LocalStack, Pub/Sub emulator và Azure Service Bus emulator (nếu môi trường hỗ trợ) có thể giúp test client API. IAM/RBAC, deduplication window, retry, settlement và behavior của managed service cần được xác minh thêm trên cloud test account.

## 18. So sánh AWS, Google Cloud và Azure

| Khía cạnh | AWS SQS | Google Pub/Sub | Azure Service Bus |
| --- | --- | --- | --- |
| Spring integration | Spring Cloud AWS / AWS SDK | Spring Framework on Google Cloud | Spring Cloud Azure / Azure SDK |
| Producer permission | sqs:SendMessage | roles/pubsub.publisher | Azure Service Bus Data Sender |
| Consumer permission | Receive/Delete/GetQueueAttributes | roles/pubsub.subscriber | Azure Service Bus Data Receiver |
| Default delivery | Standard: at-least-once | At-least-once | Peek-Lock: at-least-once |
| Producer duplicate reduction | FIFO deduplication ID, 5 phút | Exactly-once không dedupe các lần publish nghiệp vụ khác ID | Duplicate detection theo MessageId trong cửa sổ cấu hình |
| Ordering | FIFO MessageGroupId | Ordering key và regional constraints | Sessions/SessionId |
| Consumer settlement | Delete/ACK | ACK/NACK | Complete/Abandon/DeadLetter |
| DLQ | SQS redrive queue | Dead-letter topic | Built-in DLQ |

Các khác biệt quan trọng:

- SQS FIFO giảm duplicate send trong cửa sổ 5 phút; SQS Standard vẫn có thể giao trùng.
- Pub/Sub exactly-once chỉ áp dụng pull subscription trong cùng region; publish lại cùng payload vẫn có thể tạo message ID mới.
- Service Bus duplicate detection dựa trên MessageId trong thời gian cấu hình và không thay inbox consumer.
- Ordering key/group/session chỉ giữ thứ tự trong phạm vi tương ứng; relay vẫn phải publish event theo aggregate sequence.
- ACK/settlement semantics khác nhau; không xây abstraction che mất lỗi settlement của provider.

## 19. Bài tập thực hành tổng hợp

**Bối cảnh:** Xây một Order Service bằng Spring Boot. Khi người dùng tạo đơn hàng, ứng dụng phải lưu order và phát OrderCreated để Billing Service cập nhật projection. Hệ thống cần hoạt động đúng khi database, relay, broker hoặc consumer tạm thời gặp lỗi.

### Nhiệm vụ A — Business transaction và outbox

1. Tạo bảng orders và outbox_events.
2. Định nghĩa OrderCreated event envelope có eventId, aggregateId, aggregateVersion, eventType và schemaVersion.
3. Viết service @Transactional lưu order và outbox trong cùng transaction.
4. Kiểm thử trường hợp outbox insert lỗi và xác minh order rollback.

### Nhiệm vụ B — Outbox relay

1. Viết polling relay với batch claim và lease.
2. Publish event qua SQS, Pub/Sub hoặc Service Bus.
3. Chỉ mark PUBLISHED sau khi broker xác nhận.
4. Retry lỗi transient với exponential backoff và jitter.
5. Đánh dấu DEAD sau retry limit và tạo alert.
6. Kiểm thử crash sau publish nhưng trước khi cập nhật outbox.

### Nhiệm vụ C — Consumer inbox

1. Tạo bảng processed_messages với primary key (consumer_name, event_id).
2. Insert inbox marker và cập nhật projection trong một transaction.
3. ACK/complete sau khi transaction commit.
4. Gửi cùng event hai lần và xác minh projection chỉ đổi một lần.

### Nhiệm vụ D — Provider semantics

- SQS: thử Standard và FIFO; cấu hình MessageGroupId/MessageDeduplicationId.
- Pub/Sub: cấu hình pull subscription; tìm hiểu exactly-once và ordering key.
- Service Bus: bật duplicate detection; thử MessageId và Session.
- So sánh retry, settlement và DLQ.

### Nhiệm vụ E — Failure injection

- Kill relay trước publish.
- Kill relay sau publish trước mark published.
- Kill consumer sau DB commit trước ACK.
- Làm broker unavailable.
- Gửi event schema version không hỗ trợ.
- Replay event từ DLQ.
- Kiểm thử hai event cùng aggregate đến đồng thời.
- Kiểm thử API idempotency key khi client retry tạo order.

**Tiêu chí đạt:** Business state và outbox luôn cùng commit/rollback; relay không làm mất event khi process restart; duplicate publish được phép nhưng consumer không lặp DB side effect; ACK chỉ sau commit; retry/DLQ có giới hạn và quan sát được; thứ tự theo aggregate được giữ khi nghiệp vụ yêu cầu.

## 20. Ghi nhớ

- Dual write giữa database và broker tạo failure window; @Transactional không tự quản lý transaction của broker.
- Transactional outbox ghi business state và event trong cùng database transaction.
- Relay publish sau commit; chỉ mark published khi broker xác nhận.
- Relay có thể publish lặp nếu crash sau broker accept nhưng trước khi ghi trạng thái; giữ event ID ổn định.
- Polling relay dùng lease và FOR UPDATE SKIP LOCKED; CDC/Debezium đọc transaction log.
- Debezium Outbox Event Router dùng event ID, aggregate type/id, event type và payload; thường phát qua Kafka.
- Consumer inbox dùng unique constraint theo consumer và event ID.
- Inbox insert và business update phải nằm trong cùng transaction.
- ACK/complete sau khi consumer transaction commit.
- Broker deduplication giúp giảm duplicate nhưng không thay idempotent consumer.
- Pub/Sub exactly-once có phạm vi pull subscription cùng region; Service Bus duplicate detection có cửa sổ; SQS FIFO dedup 5 phút.
- Side effect ở hệ thống ngoài cần idempotency key, outbox tiếp theo hoặc saga.
- Giữ thứ tự bằng aggregate version và partition/group/session key; relay phải publish đúng sequence.
- Theo dõi pending outbox, oldest event age, relay attempts, consumer duplicates, backlog và DLQ.
- Replay phải có audit và giữ nguyên event ID nếu muốn inbox nhận diện duplicate.

### Tài liệu tham khảo

- [Transactional Outbox pattern — Debezium Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Spring Framework — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Cloud AWS — SQS integration and acknowledgement modes](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
- [Amazon SQS — Exactly-once processing in FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Amazon SQS — Message deduplication and grouping](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-key-terms.html)
- [Google Cloud Pub/Sub — Exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Google Cloud Pub/Sub — Message ordering](https://docs.cloud.google.com/pubsub/docs/ordering)
- [Spring Framework on Google Cloud — Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/index.html)
- [Spring Framework on Google Cloud — Pub/Sub template and ordering keys](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/pubsub.html)
- [Spring Framework on Google Cloud 5.6.1 — PubSubTemplate API](https://googleapis.dev/java/spring-cloud-gcp/5.6.1/com/google/cloud/spring/pubsub/core/PubSubTemplate.html)
- [Azure Service Bus — Duplicate detection](https://learn.microsoft.com/en-us/azure/service-bus-messaging/duplicate-detection)
- [Azure Service Bus — Prevent message loss and duplicate processing](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-message-loss-and-duplicates)
- [Azure Service Bus Java — ServiceBusSenderClient](https://learn.microsoft.com/en-us/java/api/com.azure.messaging.servicebus.servicebussenderclient?view=azure-java-stable)
- [Azure Service Bus Java — ServiceBusMessage](https://learn.microsoft.com/en-us/java/api/com.azure.messaging.servicebus.servicebusmessage?view=azure-java-stable)
- [Spring Cloud Azure — Spring Messaging for Service Bus](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/spring-messaging-service-bus-support)
