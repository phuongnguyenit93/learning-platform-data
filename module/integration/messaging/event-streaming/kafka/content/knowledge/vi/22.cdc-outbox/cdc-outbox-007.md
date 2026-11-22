# Transactional Outbox và tính nguyên tử trong cơ sở dữ liệu

## Mục tiêu bài học

Một service thường phải cập nhật dữ liệu nghiệp vụ trong database và đồng thời phát event lên Kafka. Nếu service ghi database trước rồi gửi Kafka, process có thể dừng giữa hai thao tác và làm mất event. Nếu gửi Kafka trước rồi database rollback, consumer có thể nhận một event mô tả thay đổi chưa từng được commit. Đây là dual-write problem.

Transactional Outbox giải quyết vấn đề bằng cách ghi thay đổi nghiệp vụ và một bản ghi outbox trong cùng transaction của database. Một relay riêng đọc outbox và publish event lên Kafka. Khi dùng CDC, Debezium đọc transaction log của database để chuyển các thay đổi outbox thành Kafka records.

Bài học trình bày tính nguyên tử ở ranh giới database, hai cách relay là polling và CDC, cấu trúc bảng outbox, tích hợp Spring/JPA, Debezium Outbox Event Router, delivery semantics, idempotency, ordering, cleanup, recovery và kiểm thử lỗi.

Sau bài học, người học có thể:

- Giải thích dual-write problem giữa database và Kafka.
- Mô tả vì sao business row và outbox row phải nằm trong cùng DB transaction.
- Thiết kế bảng outbox có event ID, aggregate key, event type, payload và sequence.
- So sánh polling publisher với CDC relay.
- Tích hợp transactional outbox trong Spring Boot/JPA.
- Cấu hình Debezium Outbox Event Router ở mức cơ bản.
- Hiểu at-least-once delivery và xử lý duplicate ở consumer.
- Thiết kế ordering theo aggregate và kiểm tra event sequence.
- Quản lý retry, poison event, outbox retention và connector recovery.
- Kiểm thử các tình huống crash ở từng ranh giới commit.

## 1. Dual-write problem

Giả sử API tạo đơn hàng cần:

1. Ghi đơn hàng vào database.
2. Phát OrderCreated event lên Kafka để inventory, billing và notification xử lý.

Hai hệ thống có transaction độc lập: database transaction và Kafka produce operation. Nếu không dùng một giải pháp phối hợp, không có transaction nguyên tử bao trùm cả hai hệ thống.

### 1.1. Ghi database trước, Kafka sau

~~~mermaid
sequenceDiagram
    participant S as Order service
    participant DB as Database
    participant K as Kafka
    S->>DB: INSERT order
    DB-->>S: COMMIT thành công
    Note over S: Process crash
    S-xK: Không publish OrderCreated
~~~

Database đã có đơn hàng nhưng Kafka không có event. Các service downstream không biết đơn hàng mới được tạo. Nếu không có cơ chế đối soát, trạng thái giữa các hệ thống bị lệch.

### 1.2. Gửi Kafka trước, database sau

~~~mermaid
sequenceDiagram
    participant S as Order service
    participant K as Kafka
    participant DB as Database
    S->>K: Publish OrderCreated
    K-->>S: ACK
    S->>DB: INSERT order
    DB--xS: Rollback / lỗi
~~~

Kafka đã có event nhưng database không có đơn hàng tương ứng. Consumer có thể thực hiện nghiệp vụ dựa trên một thay đổi chưa được commit.

### 1.3. Vì sao không dùng @Transactional đơn giản?

Spring @Transactional thường điều khiển transaction của một transaction manager cụ thể, ví dụ database transaction manager. Việc gọi KafkaTemplate.send() bên trong method đó không tự động khiến Kafka và database trở thành một distributed atomic transaction.

Kafka transaction có thể atomically commit các Kafka records và consumer offsets trong Kafka. Nó không tự bao gồm transaction của PostgreSQL, MySQL hoặc database khác.

Transactional Outbox không cố gắng tạo một transaction phân tán giữa database và Kafka. Nó đưa ý định phát event vào cùng transaction database với thay đổi nghiệp vụ, rồi relay event sau khi transaction đã commit.

## 2. Nguyên lý Transactional Outbox

Trong một DB transaction, service thực hiện hai thao tác:

- Ghi hoặc cập nhật dữ liệu nghiệp vụ.
- Ghi một row mô tả event cần phát vào bảng outbox.

Nếu transaction commit, cả hai row cùng tồn tại. Nếu transaction rollback, cả hai cùng không tồn tại. Relay chỉ đọc các outbox row đã commit và publish chúng lên Kafka.

~~~mermaid
flowchart TB
    A[Application command] --> B[Begin DB transaction]
    B --> C[Update business tables]
    B --> D[Insert outbox event]
    C --> E{DB commit?}
    D --> E
    E -->|Rollback| F[Không có business change và outbox event]
    E -->|Commit| G[Business data và outbox event cùng tồn tại]
    G --> H[Outbox relay]
    H --> I[Kafka topic]
    I --> J[Consumers]
~~~

Tính nguyên tử được bảo đảm trong database: business data và event intent cùng commit hoặc cùng rollback. Việc gửi lên Kafka là một bước bất đồng bộ sau đó; vì vậy relay cần retry và consumer cần xử lý duplicate.

### 2.1. Bảng outbox mẫu

Một bảng outbox tổng quát có thể gồm:

~~~sql
CREATE TABLE outbox_event (
    id              UUID PRIMARY KEY,
    aggregatetype   VARCHAR(255) NOT NULL,
    aggregateid     VARCHAR(255) NOT NULL,
    type            VARCHAR(255) NOT NULL,
    payload         JSONB NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    sequence_no     BIGINT,
    published_at    TIMESTAMPTZ,
    claimed_by      VARCHAR(255),
    claim_token     UUID,
    lease_until     TIMESTAMPTZ,
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT
);

CREATE INDEX idx_outbox_pending
    ON outbox_event (occurred_at, id)
    WHERE published_at IS NULL;

CREATE INDEX idx_outbox_aggregate_sequence
    ON outbox_event (aggregateid, sequence_no);
~~~

Các field có ý nghĩa:

| Field | Vai trò |
|---|---|
| id | Event ID duy nhất, ổn định qua retry |
| aggregatetype | Loại aggregate, ví dụ Order hoặc Payment |
| aggregateid | ID aggregate, dùng làm Kafka key |
| type | Event type, ví dụ OrderCreated |
| payload | Nội dung event theo data contract |
| occurred_at | Thời điểm event phát sinh theo nghiệp vụ |
| sequence_no | Thứ tự event trong một aggregate nếu cần kiểm soát ordering |
| published_at | Thời điểm relay xác nhận Kafka publish thành công |
| claimed_by / claim_token | Worker và token giữ lease khi dùng polling relay |
| lease_until | Thời hạn claim để worker khác có thể tiếp quản |
| attempts / last_error | Theo dõi retry và lỗi relay |

Đây là schema minh họa cho polling relay. Nếu dùng Debezium CDC, không nhất thiết cần published_at, claimed_by hoặc lease columns; bảng outbox thường giữ các field event mà Event Router cần. Tránh thêm các cột vận hành polling vào CDC table nếu connector không cần chúng, vì mỗi update cũng có thể tạo CDC event.

### 2.2. Event payload và metadata

Payload nên là event đã được định nghĩa theo data contract, không nhất thiết là toàn bộ database row. Event nên chứa dữ liệu consumer cần để phản ứng với thay đổi nghiệp vụ.

Ví dụ:

~~~json
{
  "eventId": "8a8f2b48-49ab-4ed6-9c64-4e0c8a3b5f21",
  "eventType": "OrderCreated",
  "orderId": "order-42",
  "sequence": 1,
  "occurredAt": "2026-11-20T10:15:30Z",
  "customerId": "customer-7",
  "total": {
    "amount": "125000.00",
    "currency": "VND"
  }
}
~~~

Event ID cần giữ nguyên khi relay retry. Aggregate ID phù hợp làm Kafka key nếu cần giữ thứ tự trong một aggregate. Timestamp phục vụ quan sát nhưng không nên dùng làm sequence duy nhất vì clock có thể lệch và nhiều event có thể cùng timestamp.

## 3. Ghi business data và outbox row trong cùng transaction

Điều kiện quan trọng nhất là hai thao tác phải tham gia cùng transaction database và cùng transaction manager. Nếu business row được ghi ở database A còn outbox row ghi ở database B, mẫu này không còn bảo đảm atomicity.

### 3.1. Ví dụ Spring Boot và JPA

Entity outbox tối giản:

~~~java
import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "outbox_event")
public class OutboxEvent {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String aggregatetype;

    @Column(nullable = false)
    private String aggregateid;

    @Column(nullable = false)
    private String type;

    @Column(nullable = false, columnDefinition = "jsonb")
    @JdbcTypeCode(SqlTypes.JSON)
    private JsonNode payload;

    @Column(nullable = false)
    private Instant occurredAt;

    protected OutboxEvent() {
    }

    public OutboxEvent(
            UUID id,
            String aggregatetype,
            String aggregateid,
            String type,
            JsonNode payload,
            Instant occurredAt) {
        this.id = id;
        this.aggregatetype = aggregatetype;
        this.aggregateid = aggregateid;
        this.type = type;
        this.payload = payload;
        this.occurredAt = occurredAt;
    }
}
~~~

Service nghiệp vụ:

~~~java
import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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
    public Order createOrder(CreateOrderCommand command) {
        Order order = Order.create(command);
        orderRepository.save(order);

        UUID eventId = UUID.randomUUID();
        OrderCreated event = OrderCreated.from(order, eventId);

        JsonNode payload = objectMapper.valueToTree(event);
        outboxRepository.save(new OutboxEvent(
            eventId,
            "Order",
            order.getId().toString(),
            "OrderCreated",
            payload,
            Instant.now()
        ));

        return order;
    }
}
~~~

OrderRepository, OutboxEventRepository, Order, CreateOrderCommand và OrderCreated là các kiểu ứng dụng minh họa. Điểm cốt lõi là cả hai repository dùng cùng DataSource và transaction manager. Nếu serialize event thất bại, exception phải làm transaction rollback để không commit business row mà thiếu outbox event.

Với Hibernate 6 và PostgreSQL JSONB, ví dụ dùng JsonNode cùng JdbcTypeCode(SqlTypes.JSON) để lưu một JSON object, không phải chuỗi JSON bị encode thành JSON string. Mapping cụ thể còn phụ thuộc Hibernate version và database dialect; có thể dùng converter hoặc JSON type mapping tương ứng nếu dự án dùng phiên bản khác.

### 3.2. Những điều cần kiểm tra với @Transactional

- Method phải chạy qua Spring transaction proxy; self-invocation có thể bỏ qua proxy.
- Hai repository phải tham gia cùng transaction manager.
- Không gọi KafkaTemplate để publish trực tiếp như bước bắt buộc của transaction database.
- Exception làm serialize hoặc insert outbox thất bại phải được rollback theo rollback rules.
- Nếu dùng nhiều database, cần xác định rõ transaction boundary và giải pháp khác phù hợp.
- Không trả response thành công trước khi database transaction commit.

Nếu client có thể retry lệnh tạo đơn sau timeout HTTP, cần idempotency key ở command/API boundary. Event ID được tạo trong mỗi lần xử lý chỉ ổn định cho relay retry của lần xử lý đó; nó không tự ngăn hai lần command giống nhau tạo hai order và hai outbox event.

Spring mặc định rollback với RuntimeException và Error; checked exception cần cấu hình rollbackFor nếu muốn rollback. Trong ví dụ, ObjectMapper.valueToTree chuyển lỗi chuyển đổi thành runtime exception; nếu dùng API ném checked exception, hãy khai báo rollback rule rõ ràng.

### 3.3. Transaction boundary trong service

Một transaction cần bao trọn business update và outbox insert. Không nên gọi một service độc lập commit outbox trước khi business update commit, hoặc dùng REQUIRES_NEW cho outbox nếu yêu cầu atomicity giữa hai thao tác.

Nếu nghiệp vụ cần ghi nhiều bảng, hãy ghi toàn bộ thay đổi và event tương ứng trong cùng transaction. Có thể có nhiều outbox event cho một command, nhưng tất cả phải commit hoặc rollback cùng business change.

## 4. Hai cách relay outbox

Outbox row đã được commit cần được chuyển thành Kafka record. Hai hướng triển khai phổ biến:

| Cách relay | Cách hoạt động | Phù hợp |
|---|---|---|
| Polling publisher | Service định kỳ truy vấn outbox table và publish event | Hệ thống đơn giản, muốn tự kiểm soát retry/lease |
| CDC relay | Connector đọc transaction log database và phát change event lên Kafka | Muốn tách relay khỏi ứng dụng và tận dụng log-based CDC |

Không nên chạy cả polling publisher và Debezium cùng publish một bảng outbox vào cùng luồng nếu không có chủ đích, vì consumer sẽ nhận duplicate event.

## 5. Polling publisher

Polling publisher định kỳ lấy các row chưa publish, gửi lên Kafka và đánh dấu đã publish sau khi nhận xác nhận từ broker.

~~~mermaid
sequenceDiagram
    participant R as Outbox relay
    participant DB as Database
    participant K as Kafka
    R->>DB: Claim batch pending rows
    DB-->>R: Rows + claim token
    loop Mỗi event
        R->>K: Send record (key=aggregateid)
        K-->>R: Produce ACK
        R->>DB: Mark published_at
        DB-->>R: Update committed
    end
~~~

### 5.1. Claim row an toàn với nhiều worker

Nếu nhiều relay worker cùng truy vấn pending rows, chúng không được publish cùng row một cách không kiểm soát. PostgreSQL hỗ trợ FOR UPDATE SKIP LOCKED để các worker claim các row khác nhau trong transaction ngắn.

Một cách triển khai là tạo lease:

~~~sql
WITH picked AS (
    SELECT id
    FROM outbox_event
    WHERE published_at IS NULL
      AND (lease_until IS NULL OR lease_until < now())
    ORDER BY occurred_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE outbox_event AS e
SET claimed_by = :worker_id,
    claim_token = :claim_token,
    lease_until = now() + interval '30 seconds',
    attempts = attempts + 1
FROM picked
WHERE e.id = picked.id
RETURNING e.*;
~~~

Transaction claim kết thúc nhanh, giải phóng row lock. Worker gửi event ra Kafka bên ngoài transaction claim. Sau khi nhận produce ACK, worker cập nhật published_at với điều kiện claim_token vẫn khớp:

~~~sql
UPDATE outbox_event
SET published_at = now(),
    claimed_by = NULL,
    claim_token = NULL,
    lease_until = NULL,
    last_error = NULL
WHERE id = :event_id
  AND claim_token = :claim_token
  AND published_at IS NULL;
~~~

Claim token ngăn worker cũ ghi trạng thái sau khi lease đã hết hạn và row được worker khác claim. Nó không ngăn Kafka nhận duplicate nếu worker cũ đã publish trước khi mất lease; consumer vẫn cần idempotency.

### 5.2. Vì sao không đánh dấu published trước khi gửi?

Nếu cập nhật published_at trước rồi mới gửi Kafka, process có thể crash sau DB commit nhưng trước khi Kafka nhận record. Outbox row đã bị coi là hoàn tất và event bị mất.

Thứ tự an toàn hơn là:

1. Claim row.
2. Gửi Kafka.
3. Chờ broker ACK.
4. Đánh dấu published.

Thứ tự này có thể tạo duplicate nếu process crash sau bước 3 nhưng trước bước 4. Đây là trade-off chủ đích để ưu tiên không mất event.

Producer relay nên cấu hình durability phù hợp, thường gồm acks=all và enable.idempotence=true cùng retry/timeout được cân nhắc theo Kafka client version. Idempotence giúp xử lý duplicate do retry protocol trong producer session; nó không loại bỏ duplicate do relay restart sau khi Kafka đã ACK nhưng database chưa ghi published_at.

### 5.3. At-least-once delivery

Polling relay thường cung cấp at-least-once delivery:

- Nếu gửi thất bại trước khi broker nhận record, worker retry.
- Nếu broker đã nhận record nhưng ACK bị mất, worker có thể gửi lại.
- Nếu ACK đã nhận nhưng DB chưa đánh dấu published, worker khác có thể gửi lại sau lease timeout.

Do đó, một event có thể xuất hiện nhiều lần trong Kafka. Event ID ổn định là khóa idempotency để consumer phát hiện bản trùng.

### 5.4. Retry và poison event

Khi Kafka không sẵn sàng, relay cần retry với backoff và jitter. Khi payload lỗi hoặc topic/ACL cấu hình sai, retry vô hạn có thể khiến một row chặn các row khác.

Nên lưu:

- attempts.
- last_error đã rút gọn và loại bỏ secret.
- thời điểm retry tiếp theo.
- claim/lease state.
- trạng thái cần can thiệp thủ công nếu vượt ngưỡng.

Không xóa event chỉ vì vượt số lần retry. Chuyển sang trạng thái quarantine/failed có audit và alert; chỉ bỏ qua khi nghiệp vụ chấp thuận và có cách phục hồi dữ liệu.

### 5.5. Polling không bảo đảm ordering toàn aggregate

ORDER BY occurred_at không đủ bảo đảm thứ tự commit của database. Nhiều worker dùng SKIP LOCKED có thể claim event sau của cùng aggregate trước event trước. Network latency và retry cũng có thể làm đảo thứ tự publish.

Nếu ordering quan trọng:

- Ghi sequence_no tăng đơn điệu trong cùng transaction của aggregate.
- Claim/serialize publish theo aggregate hoặc dùng một worker cho mỗi shard.
- Không cho event sequence N+1 vượt N khi N chưa được publish thành công.
- Dùng aggregateid làm Kafka key để các event cùng aggregate vào cùng partition.
- Consumer kiểm tra sequence và phát hiện gap/duplicate.

Timestamp phục vụ quan sát, còn sequence_no biểu diễn thứ tự nghiệp vụ rõ hơn.

## 6. CDC relay với Debezium

CDC (Change Data Capture) đọc thay đổi đã commit từ transaction log của database thay vì liên tục query bảng outbox. Debezium connector theo dõi log như PostgreSQL WAL hoặc MySQL binlog và phát change event lên Kafka.

Với Transactional Outbox, Debezium Outbox Event Router SMT biến row thay đổi trong outbox thành Kafka record có key, topic, headers và payload theo cấu hình.

~~~mermaid
flowchart LR
    A[Spring service] --> B[DB transaction]
    B --> C[Business tables]
    B --> D[Outbox table]
    D --> E[DB transaction log<br/>WAL / binlog]
    E --> F[Debezium connector]
    F --> G[Outbox Event Router SMT]
    G --> H[Kafka topic]
    H --> I[Consumers]
~~~

CDC không cần ứng dụng tự đánh dấu published_at cho từng row theo cách polling làm. Connector quản lý vị trí đọc log bằng offset và database replication slot/binlog position.

### 6.1. Ví dụ cấu hình Debezium PostgreSQL

Đây là cấu hình minh họa cho Kafka Connect REST API và Debezium PostgreSQL connector:

~~~json
{
  "name": "orders-outbox-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "tasks.max": "1",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "<externalized-secret>",
    "database.dbname": "orders",
    "topic.prefix": "orders-cdc",
    "plugin.name": "pgoutput",
    "slot.name": "orders_outbox_slot",
    "publication.name": "orders_outbox_publication",
    "table.include.list": "public.outbox_event",
    "tombstones.on.delete": "false",
    "transforms": "outbox",
    "transforms.outbox.type": "io.debezium.transforms.outbox.EventRouter",
    "transforms.outbox.table.field.event.id": "id",
    "transforms.outbox.table.field.event.key": "aggregateid",
    "transforms.outbox.table.field.event.type": "type",
    "transforms.outbox.table.field.event.payload": "payload",
    "transforms.outbox.route.by.field": "aggregatetype"
  }
}
~~~

Tên cấu hình và property có thể khác theo Debezium version. Cấu hình thực tế còn cần database/schema/table permissions, publication, replication slot, plugin, Kafka Connect converters và Schema Registry nếu dùng schema-aware payload.

Ví dụ không chứa secret thật. Kafka Connect config có thể lưu credential trong config store hoặc externalized secrets; không commit password vào source control.

### 6.2. Outbox Event Router mapping

Với bảng có các field id, aggregatetype, aggregateid, type và payload:

| Field outbox | Vai trò trong event |
|---|---|
| id | Event ID |
| aggregatetype | Giá trị dùng để route topic |
| aggregateid | Kafka record key |
| type | Event type, thường được đưa vào header |
| payload | Kafka record value |

Trong cấu hình minh họa, topic được route theo aggregatetype và key là aggregateid. Nếu cần route theo quy tắc khác, cấu hình route.by.field và route.topic.replacement theo tài liệu Debezium version đang dùng.

### 6.3. Payload dạng JSON

Outbox Event Router có thể xử lý payload theo converter và cấu hình connector. Với PostgreSQL JSONB, cần xác minh payload được converter chuyển thành Kafka value đúng dạng JSON mong muốn. Một số cấu hình cần bật tùy chọn mở rộng JSON payload của SMT; không giả định JDBC/JSONB converter luôn cho ra byte payload giống ứng dụng mong đợi.

Kiểm tra bằng integration test trên đúng phiên bản Debezium và Kafka Connect, không chỉ dựa vào cấu hình mẫu.

## 7. Polling publisher và CDC: chọn cách nào?

| Tiêu chí | Polling publisher | CDC với Debezium |
|---|---|---|
| Thành phần vận hành | Service relay do đội ứng dụng quản lý | Kafka Connect và Debezium connector |
| Đọc dữ liệu | Query bảng outbox | Đọc WAL/binlog |
| Độ trễ | Theo polling interval và batch | Gần thời gian thực theo transaction log |
| Đánh dấu published | Thường có trạng thái/lease trong DB | Dựa vào connector offset; không cần update row để đánh dấu |
| Retry | Logic ứng dụng | Connector retry/recovery theo connector |
| Ordering | Cần điều phối worker/aggregate | Theo thứ tự log/partition và routing; vẫn cần key/sequence |
| Cleanup | Xóa row đã publish sau retention | Có thể cleanup theo policy riêng sau khi CDC đã đọc; phải cẩn thận với snapshot/recovery |
| Độ phức tạp | Dễ bắt đầu nhưng cần code claim/retry tốt | Cần quản lý Connect, connector, slot/binlog và schema |

Polling phù hợp khi hệ thống nhỏ, muốn kiểm soát logic bằng code ứng dụng hoặc chưa có nền tảng CDC. Debezium phù hợp khi tổ chức đã vận hành Kafka Connect và muốn dùng transaction log để capture event với độ trễ thấp.

Không có lựa chọn nào tự tạo exactly-once end-to-end giữa database và Kafka. Cả hai đều cần xử lý duplicate và consumer idempotency.

## 8. Ordering và partition key

Kafka chỉ bảo đảm thứ tự record trong một partition. Với outbox, nên chọn aggregate ID làm key để các event cùng aggregate đi vào cùng partition.

Ví dụ:

~~~text
key=order-42, OrderCreated, sequence=1
key=order-42, OrderPaid, sequence=2
key=order-42, OrderShipped, sequence=3
~~~

Nếu cả ba record cùng partition và relay gửi theo sequence, consumer có thể quan sát thứ tự này.

### 8.1. Vì sao timestamp không đủ?

Hai event có thể cùng timestamp hoặc timestamp từ nhiều application node có clock skew. Event được tạo trước chưa chắc có timestamp nhỏ hơn. Dùng sequence_no được cập nhật trong transaction aggregate để biểu diễn thứ tự nghiệp vụ.

### 8.2. CDC ordering

Debezium đọc transaction log theo thứ tự commit mà database cung cấp trong phạm vi connector/partition. Tuy nhiên, khi route nhiều aggregate vào nhiều Kafka topic/partition, consumer chỉ có ordering trong từng partition. Nếu consumer cần thứ tự theo aggregate, phải dùng aggregate key ổn định và sequence để xác minh.

### 8.3. Polling ordering

Nhiều worker polling cùng lúc có thể làm event sau của aggregate được gửi trước event trước. Có thể:

- Serialize claim theo aggregate.
- Dùng partition/shard worker dựa trên hash aggregate ID.
- Chỉ claim event có sequence bằng next expected sequence.
- Dùng lock hoặc advisory lock theo aggregate khi claim.
- Tách queue theo shard để một aggregate luôn đi qua cùng relay worker.

Không dùng một global lock nếu throughput cao; lock theo aggregate hoặc shard giúp cân bằng ordering và concurrency.

## 9. Consumer idempotency và Inbox pattern

Vì relay có thể publish duplicate, consumer cần xử lý event theo cách idempotent. Một cách phổ biến là lưu event ID đã xử lý trong cùng database transaction với side effect nghiệp vụ.

Inbox table:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(255) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer xử lý:

1. Bắt đầu DB transaction.
2. Thử insert event ID vào processed_event.
3. Nếu unique conflict, event đã xử lý; bỏ qua side effect.
4. Nếu insert thành công, áp dụng business update.
5. Commit transaction.
6. Listener chỉ acknowledge/commit offset sau khi DB transaction thành công theo cấu hình container.

Với Spring, một cách dễ kiểm soát là listener gọi một service method được proxy bởi database transaction manager; service commit DB transaction trước khi trả về, sau đó listener mới hoàn tất và container mới commit offset theo AckMode. Kiểm tra cấu hình transaction/acknowledgment thực tế để không commit Kafka offset trước khi DB commit.

Ví dụ logic:

~~~java
@Transactional
public void handle(OrderCreated event) {
    boolean firstDelivery =
        inboxRepository.insertIfAbsent("billing", event.eventId());

    if (!firstDelivery) {
        return;
    }

    billingService.createInvoice(event);
}
~~~

insertIfAbsent cần được triển khai bằng INSERT ... ON CONFLICT DO NOTHING hoặc cơ chế tương đương và trả kết quả có tính nguyên tử. Không thực hiện SELECT trước rồi INSERT sau vì hai consumer đồng thời có thể cùng vượt qua bước SELECT.

Inbox row và business update phải nằm trong cùng transaction database. Nếu side effect là gọi HTTP sang hệ thống khác, inbox không tự làm HTTP call nguyên tử; cần outbox tiếp theo, idempotency key hoặc saga.

## 10. Exactly-once và ranh giới bảo đảm

Các khái niệm cần phân biệt:

| Cơ chế | Bảo đảm |
|---|---|
| DB transaction + outbox insert | Business change và event intent cùng commit/rollback trong database |
| Polling/CDC relay | Chuyển event đã commit sang Kafka; thường có at-least-once và có thể duplicate |
| Kafka idempotent producer | Chống duplicate do retry producer protocol trong phạm vi producer session/identity |
| Kafka transaction | Atomically commit các Kafka records và offsets trong Kafka |
| Consumer inbox/idempotency | Ngăn side effect nghiệp vụ bị áp dụng lặp cho cùng event ID trong DB transaction |

Không gọi toàn bộ pipeline là exactly-once nếu chưa định nghĩa rõ ranh giới. Mục tiêu thực tế thường là không mất event intent, chấp nhận duplicate ở transport và bảo đảm side effect consumer idempotent.

## 11. Cleanup và retention của outbox

Outbox table tăng liên tục nếu không dọn row cũ. Tuy nhiên, xóa quá sớm có thể làm mất khả năng audit, replay hoặc recovery.

### 11.1. Polling relay cleanup

Có thể xóa các row đã published sau một khoảng retention:

~~~sql
DELETE FROM outbox_event
WHERE published_at < now() - interval '7 days';
~~~

Chạy cleanup theo batch để tránh transaction quá lớn và lock lâu. Chỉ xóa row đã được publish xác nhận và đã qua thời gian cần giữ để điều tra/replay. Giữ lại failed/quarantined rows cho đến khi có quyết định vận hành.

### 11.2. CDC cleanup

Với Debezium, xóa row outbox cũng tạo một change event trong transaction log. Outbox Event Router thường được cấu hình để xử lý insert event; cần kiểm tra delete/tombstone behavior theo phiên bản và SMT config.

Không xóa outbox row chỉ dựa trên thời gian kể từ insert nếu connector có thể bị lag hoặc phải snapshot/recover. Cần biết connector đã tiến qua log position chứa insert và đã commit offset tương ứng.

### 11.3. Partitioning outbox table

Với volume lớn, có thể partition outbox table theo thời gian hoặc chiến lược khác để cleanup nhanh hơn. Cần kiểm tra ràng buộc unique/primary key của database khi dùng partitioned table và cách connector capture các partition. Không áp dụng partitioning trước khi đo volume và hiểu tác động đến CDC.

## 12. Recovery và failure scenarios

| Điểm crash | Trạng thái có thể xảy ra | Cách phục hồi |
|---|---|---|
| Trước DB commit | Business và outbox cùng rollback | Client có thể retry command theo idempotency nghiệp vụ |
| Sau DB commit, trước relay đọc | Outbox row còn pending | Relay đọc lại khi hoạt động |
| Polling: sau claim, trước Kafka send | Lease còn hoặc hết hạn | Worker khác claim khi lease hết |
| Polling: Kafka ACK rồi crash trước published_at | Event đã có ở Kafka, DB còn pending | Relay gửi lại; consumer deduplicate event ID |
| CDC: connector dừng sau khi đọc log nhưng trước khi offset được lưu | Có thể phát lại change sau restart | Connector resume từ offset đã commit; consumer idempotent |
| Consumer DB commit rồi crash trước offset commit | Kafka gửi lại event | Inbox unique key ngăn side effect lặp |
| Consumer offset commit trước DB commit | Có thể mất side effect | Cấu hình acknowledgment/transaction boundary để DB commit trước offset |
| Database mất kết nối | Không tạo được business/outbox transaction | Trả lỗi và retry command theo policy |
| Kafka mất kết nối | Outbox giữ event intent | Relay/connector retry khi Kafka phục hồi |

### 12.1. PostgreSQL replication slot và WAL retention

Debezium PostgreSQL thường dùng logical replication slot để đọc WAL. Nếu connector dừng lâu, slot có thể giữ WAL chưa được tiêu thụ và làm dung lượng disk tăng mạnh.

Theo dõi:

- Connector/task state.
- Replication slot active state.
- Restart LSN và confirmed flush LSN.
- WAL retained bytes.
- Database disk free space.
- CDC lag và Kafka Connect offset progress.

Không xóa replication slot tùy tiện để giải phóng disk. Xóa slot có thể khiến connector không còn vị trí resume và phải tạo lại slot/snapshot, có nguy cơ replay hoặc mất khả năng capture phần WAL đã bị recycle.

### 12.2. Snapshot và bootstrap

Khi connector mới tạo hoặc cần khôi phục, Debezium có thể thực hiện snapshot theo cấu hình connector. Với outbox table, snapshot có thể khiến các row đang tồn tại được xử lý như dữ liệu snapshot tùy connector và SMT/version/config. Điều này có thể replay event cũ.

Thiết kế bootstrap cần quyết định:

- Có cần phát lại các outbox row đang tồn tại khi snapshot không?
- Outbox table có được cleanup trước snapshot không?
- Consumer có idempotency theo event ID không?
- Connector offsets và replication slot được quản lý thế nào?
- Có cần snapshot mode hoặc signaling phù hợp với database/version?

Kiểm thử snapshot/restart trên staging với dữ liệu đại diện trước khi dùng trong production. Không mặc định rằng restart connector luôn chỉ tiếp tục từ đúng một record mà không thể replay.

## 13. Monitoring và vận hành

### 13.1. Polling relay metrics

Theo dõi:

- Số outbox rows pending.
- Tuổi của row pending lâu nhất.
- Publish rate và publish latency.
- Retry count và failure rate.
- Số row đang claim và lease hết hạn.
- Số row quarantine/failed.
- DB query latency và lock contention.

Một alert hữu ích là tuổi của event pending lâu nhất vượt SLA, thay vì chỉ theo dõi số lượng pending.

### 13.2. Debezium/Kafka Connect metrics

Theo dõi:

- Connector và task state.
- Source record poll/write rate.
- Source record lag và queue capacity.
- Connector offset commit progress.
- Replication slot lag/WAL retained size.
- Kafka producer error và retry.
- SMT transformation error.

Tên metric phụ thuộc Kafka Connect/Debezium version và metrics reporter. Kiểm tra JMX/Prometheus exporter thực tế trước khi tạo dashboard.

### 13.3. Consumer metrics

Theo dõi consumer lag, processing latency, duplicate event rate, inbox conflict count, sequence gap và DLT rate. Nếu duplicate tăng, điều tra relay restart, timeout, connector offset recovery hoặc lease expiry.

## 14. Kiểm thử Transactional Outbox

Không chỉ kiểm tra rằng repository.save() được gọi. Cần kiểm tra transaction thật và các failure window.

### 14.1. Kiểm tra atomicity trong database

Test hai trường hợp:

- Tạo order thành công: order row và outbox row cùng tồn tại.
- Serialize/insert outbox thất bại: transaction rollback và order row không tồn tại.

Có thể dùng Testcontainers PostgreSQL để test với cùng database engine production. H2 có thể khác PostgreSQL về JSONB, locking, SKIP LOCKED và transaction behavior.

### 14.2. Kiểm tra polling relay

1. Tạo outbox row pending.
2. Chạy relay và xác minh Kafka nhận event.
3. Xác minh published_at được cập nhật sau ACK.
4. Mô phỏng send failure và xác minh row vẫn pending.
5. Mô phỏng crash sau Kafka ACK trước DB update.
6. Chạy lại relay và xác minh duplicate có cùng event ID.
7. Xác minh consumer inbox chỉ áp dụng side effect một lần.

### 14.3. Kiểm tra CDC relay

1. Khởi chạy PostgreSQL, Kafka và Kafka Connect/Debezium trong test environment.
2. Đăng ký connector và outbox SMT.
3. Commit business row cùng outbox row.
4. Xác minh record xuất hiện trên topic đúng, key đúng và payload đúng.
5. Restart connector trong lúc có event mới.
6. Xác minh resume/snapshot behavior và consumer deduplication.
7. Kiểm tra connector error khi schema hoặc publication không hợp lệ.

CDC integration test cần pin version PostgreSQL, Debezium, Kafka Connect và Kafka để kết quả có thể lặp lại.

## 15. Checklist thiết kế và triển khai

- Business update và outbox insert dùng cùng DB transaction.
- Event ID ổn định, duy nhất và không đổi qua retry.
- Event payload theo data contract đã version.
- Aggregate ID được dùng làm Kafka key khi cần ordering.
- Sequence number được tạo trong transaction nếu nghiệp vụ cần thứ tự chặt.
- Chỉ có một relay strategy chủ động publish cùng outbox table.
- Polling relay claim row an toàn khi chạy nhiều worker.
- Publish ACK xảy ra trước khi đánh dấu published.
- Duplicate được chấp nhận ở transport và consumer có idempotency.
- Inbox insert và business side effect cùng DB transaction.
- Retry có backoff, jitter, alert và quarantine policy.
- Outbox cleanup không chạy trước khi event an toàn để xóa.
- Debezium connector có monitoring cho slot/WAL lag và snapshot.
- Secrets không nằm trong source control.
- Có test cho crash window, duplicate, ordering và recovery.

## 16. Bài tập thực hành

### Bài tập 1: Tạo transactional outbox

1. Tạo bảng orders và outbox_event trong PostgreSQL.
2. Viết OrderApplicationService với @Transactional.
3. Ghi order row và OrderCreated outbox row.
4. Cố ý ném exception sau khi insert outbox.
5. Xác minh cả hai thao tác rollback.

### Bài tập 2: Polling relay với lease

1. Viết query claim batch dùng FOR UPDATE SKIP LOCKED.
2. Tạo claim token và lease timeout.
3. Publish record với key là aggregateid.
4. Chờ Kafka ACK rồi cập nhật published_at.
5. Mô phỏng crash sau ACK và quan sát duplicate.

### Bài tập 3: Debezium Outbox Event Router

1. Khởi chạy PostgreSQL và Kafka Connect.
2. Tạo logical replication publication/slot phù hợp.
3. Cấu hình PostgreSQL connector và EventRouter SMT.
4. Insert outbox event trong transaction.
5. Xác minh topic, key, type header và payload.
6. Restart connector và quan sát offset recovery.

### Bài tập 4: Consumer Inbox

1. Tạo processed_event table với unique key consumer_name/event_id.
2. Viết consumer xử lý OrderCreated.
3. Gửi cùng event ID hai lần.
4. Xác minh business side effect chỉ áp dụng một lần.
5. Mô phỏng DB commit rồi consumer crash trước offset commit.

### Bài tập 5: Ordering theo aggregate

1. Tạo ba event cho cùng order với sequence 1, 2, 3.
2. Publish bằng aggregate ID làm Kafka key.
3. Chạy nhiều relay worker.
4. Mô phỏng retry event sequence 1.
5. Xác minh event 2 không vượt event 1 nếu hệ thống yêu cầu strict ordering.

## 17. Câu hỏi tự kiểm tra

1. Dual-write problem xảy ra khi nào?
2. Vì sao @Transactional của database không tự commit Kafka atomically?
3. Transactional Outbox bảo đảm điều gì trong DB transaction?
4. Vì sao relay thường có at-least-once delivery?
5. Vì sao phải đánh dấu published sau khi nhận Kafka ACK?
6. Claim token và lease giải quyết vấn đề nào trong polling relay?
7. Debezium đọc thay đổi từ WAL/binlog như thế nào?
8. Outbox Event Router dùng aggregate type, aggregate ID, event type và payload ra sao?
9. Vì sao aggregate ID nên là Kafka key khi cần ordering?
10. Vì sao timestamp không đủ để biểu diễn thứ tự nghiệp vụ?
11. Inbox pattern ngăn duplicate side effect như thế nào?
12. Kafka transaction có làm database và Kafka trở thành một distributed transaction không?
13. Vì sao replication slot PostgreSQL có thể làm WAL tăng khi connector dừng?
14. Snapshot/restart Debezium có thể làm replay event cũ trong trường hợp nào?
15. Khi nào nên chọn polling relay và khi nào nên chọn CDC?

Transactional Outbox bảo đảm thay đổi nghiệp vụ và ý định phát event cùng tồn tại trong database transaction. Relay chuyển event sang Kafka với khả năng retry; consumer idempotency và sequence validation hoàn thiện khả năng phục hồi trước duplicate, crash và thay đổi thứ tự trong toàn bộ luồng sự kiện.
