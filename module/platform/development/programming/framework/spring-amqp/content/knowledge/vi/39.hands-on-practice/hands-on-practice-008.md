# Đồng bộ cơ sở dữ liệu và RabbitMQ bằng transactional outbox

Trong một hệ thống đặt hàng dùng **Spring AMQP**, yêu cầu thường xuất hiện như sau:

> Khi tạo đơn hàng thành công trong PostgreSQL, hệ thống phải phát sự kiện `OrderCreated` qua RabbitMQ để service Billing tạo hóa đơn. Nếu database hoặc RabbitMQ gặp sự cố, **không được quên ý định gửi sự kiện**; nếu broker/consumer giao lại, **không được tạo hóa đơn hai lần**.

Một triển khai ngây thơ gọi `orderRepository.save(...)` rồi `rabbitTemplate.convertAndSend(...)` trong cùng method, thậm chí đặt `@Transactional`, vẫn có hai hệ thống commit **độc lập**. Database commit có thể thành công trong khi publish thất bại; publish có thể thành công nhưng kết quả confirm bị mất, khiến ứng dụng retry và tạo duplicate. **Transactional outbox** giải quyết khoảng hở đầu tiên bằng cách ghi thay đổi nghiệp vụ **và bản ghi ý định gửi sự kiện vào cùng một DB transaction**; một relay độc lập gửi những bản ghi outbox tới RabbitMQ. Consumer phía đích phải xử lý **idempotent**, vì toàn bộ chuỗi là **at-least-once**, không phải exactly-once.

Bài thuộc chương **Thực hành tổng hợp** của module **SPRING_AMQP**. Ta sẽ xây một luồng hoàn chỉnh với **PostgreSQL + Spring Boot + Spring JDBC + Spring AMQP + RabbitMQ**, kết hợp exchange, queue, binding, `RabbitTemplate`, correlated publisher confirms, mandatory returns, `@RabbitListener`, ACK/retry/DLQ và metrics. Có đầy đủ schema SQL, các lớp Java cốt lõi, trình tự chạy thử, ma trận fault injection và checklist vận hành.

**Môi trường minh họa:** Java 17+, Spring Boot 3.x, Spring AMQP 3.x, PostgreSQL 15+ và RabbitMQ triển khai AMQP 0-9-1. Những đoạn mã thể hiện một giải pháp lab thực hành **polling outbox tuần tự** để dễ chứng minh tính đúng. Khi mở rộng production, cần phân tách rõ số relay workers, thời hạn lease, throughput, bảo mật, migrations và các quy tắc nghiệp vụ. **Không coi các snippet là kết quả đã được build/test tại đây.**

## 1. Bài toán dual-write: vì sao @Transactional chưa đủ?

### 1.1. Cách làm dễ sai

```java
@Service
public class UnsafeOrderService {

    private final JdbcTemplate jdbc;
    private final RabbitTemplate rabbit;

    public UnsafeOrderService(
            JdbcTemplate jdbc, RabbitTemplate rabbit) {
        this.jdbc = jdbc;
        this.rabbit = rabbit;
    }

    @Transactional
    public void create(UUID orderId) {
        jdbc.update(
                "INSERT INTO orders(id, state) VALUES (?, 'CREATED')",
                orderId);

        rabbit.convertAndSend(
                "orders.events", "orders.created",
                orderId.toString());
    }
}
```

`@Transactional` ở đây thường gắn với **DataSourceTransactionManager/JdbcTransactionManager** của PostgreSQL. Nó **không tự ghép** database transaction với RabbitMQ publish thành một transaction phân tán.

Có hai thứ tự phổ biến và cả hai đều có lỗ hổng:

| Trình tự | Điểm crash | Hậu quả |
|---|---|---|
| Commit DB → publish RabbitMQ | Crash **sau DB commit, trước publish** | Đơn hàng có trong DB nhưng không có sự kiện |
| Publish RabbitMQ → commit DB | Crash **sau publish, trước DB commit** | Consumer thấy sự kiện cho đơn hàng không tồn tại hoặc đã rollback |
| Publish rồi chờ confirm bên trong DB transaction | Broker confirm ACK nhưng DB commit sau đó fail | Sự kiện đã có trên broker nhưng trạng thái DB không được commit |
| DB commit rồi publish với publisher confirms | Broker lỗi sau DB commit | Không còn cơ chế atomic tự phục hồi nếu ý định gửi không lưu bền |
| Publish được broker nhận nhưng confirm bị mất | Producer retry | Có thể gửi **hai bản** của cùng một sự kiện |

Publisher confirms rất quan trọng, nhưng chúng **xác nhận broker**, không tạo atomic commit với PostgreSQL. `channelTransacted` của Spring Rabbit cũng không tạo phép màu gộp hai tài nguyên; giao dịch AMQP và giao dịch database là hai ranh giới khác nhau nếu không có một giải pháp phối hợp giao dịch thực sự.

### 1.2. Transactional outbox thay đổi thứ tự như thế nào?

```text
                  Orders API / OrderService
                              |
                              v
                     PostgreSQL transaction
                   +-------------------------+
                   | INSERT orders           |
                   | INSERT outbox_events    |
                   | COMMIT hoặc ROLLBACK    |
                   +-------------------------+
                              |
                              v
                   Outbox relay / poller
                              |
                     claim row có lease
                              |
                              v
                   RabbitTemplate.publish
                              |
                  confirms + mandatory returns
                              |
             +----------------+---------------+
             |                                |
       ACK + no return                 UNKNOWN/NACK/return
             |                                |
        outbox SENT                       retry/block
             |
             v
       RabbitMQ exchange
             |
             v
       queue + @RabbitListener
             |
             v
    Inbox/dedup + business DB transaction
             |
             v
       Consumer ACK
```

**Đơn vị nguyên tử mới là transaction của database nguồn:**

\[
\text{Commit}(\text{Order},\ \text{OutboxEvent})
\]

Nếu transaction commit, **cả order và bản ghi outbox** tồn tại. Nếu rollback, **cả hai cùng không được ghi**. Relay có thể chạy lại sau process crash vì ý định gửi đã được lưu bền.

**Đơn vị không nguyên tử:** Việc đánh dấu outbox `SENT` và broker đã nhận message **không có transaction chung**. Vì vậy publish có thể thành công rồi relay crash trước `SENT`; một lần retry sẽ tạo duplicate. Hợp đồng thực tế cần là **at-least-once delivery + idempotent consumer**, không phải “exactly once RabbitMQ”.

## 2. Hợp đồng của bài thực hành

### 2.1. Nghiệp vụ

API Orders nhận một yêu cầu tạo đơn hàng, lưu:

- `orders`: đơn hàng với `order_id`, số tiền nguyên, loại tiền, trạng thái và version.
- `outbox_events`: sự kiện `OrderCreated` cùng **eventId cố định**, schema version, JSON payload và trạng thái gửi.

Một tiến trình relay trong ứng dụng Orders định kỳ lấy sự kiện chưa gửi, publish vào exchange `orders.events` với routing key `orders.created`.

Billing đăng ký queue `billing.orders.created` bằng `@RabbitListener`. Sau khi nhận `OrderCreated`, Billing ghi một hóa đơn và một marker `processed_events` **trong cùng transaction của database Billing**. Nếu message được phát lại, marker ngăn hóa đơn thứ hai.

Trong lab có thể đặt **các bảng của Orders và Billing trên cùng một PostgreSQL instance** để giảm công sức thiết lập. **Production microservices nên có quyền sở hữu dữ liệu độc lập**: Orders không update trực tiếp bảng Billing, Billing không đọc transaction nội bộ Orders; mỗi service sở hữu schema/database và tài khoản truy cập của mình.

### 2.2. Sự kiện JSON ổn định

```json
{
  "eventId": "e83c339f-b7b6-49a7-b1db-2f74974ab29a",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "b0375d03-09cb-43f3-9933-1ef27e06c0cc",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-26T03:00:00Z",
  "amountMinor": 125000,
  "currency": "VND"
}
```

**Hợp đồng của các ID:**

| Định danh | Phạm vi | Qua retry có đổi không? |
|---|---|---|
| `orderId` | Aggregate/đơn hàng | **Không** |
| `eventId` | **Một sự kiện nghiệp vụ** | **Không**; dùng để dedup ở consumer |
| `aggregateVersion` | Thứ tự thay đổi của một order | Không đổi cho cùng event; tăng khi có event mới |
| `attemptId` / `CorrelationData.id` | **Một lần publish** qua RabbitMQ | **Có thể đổi** ở mỗi retry |
| `claimToken` | Lần relay claim một outbox row | **Đổi** khi lease/worker thay đổi |
| Consumer delivery tag | Một delivery trên một channel AMQP | Không dùng làm business ID |

Không tạo event ID mới mỗi lần retry; làm thế sẽ vô hiệu hóa deduplication. Không dùng delivery tag làm khóa nghiệp vụ, vì nó chỉ có hiệu lực trong phạm vi channel và có thể thay đổi ở redelivery.

### 2.3. Các bất biến phải chứng minh

1. **Không có order đã commit mà không có outbox intent.**
2. **Không có outbox intent đã commit cho một order bị rollback.**
3. **Không đánh dấu outbox `SENT` chỉ vì `RabbitTemplate.send` trả về**; cần broker confirm đúng và không có mandatory return.
4. **Timeout/connection loss = UNKNOWN outcome**, không suy “broker chắc chắn chưa nhận”.
5. **Event ID ổn định**, ngay cả khi publish attempt/claim token đổi.
6. **Consumer có thể nhận ≥1 lần**, nhưng **business effect chỉ commit một lần cho mỗi eventId**.
7. **Một worker cũ không được ghi đè kết quả claim mới** sau khi lease hết hạn.
8. Lỗi message không thể xử lý phải có **DLQ/quarantine và cách điều tra/replay**, không tạo requeue loop không giới hạn.

## 3. Chuẩn bị dự án và topology RabbitMQ

### 3.1. Nhóm dependency

Một ứng dụng Spring Boot minh họa cần:

| Dependency | Mục đích |
|---|---|
| `spring-boot-starter-amqp` | `RabbitTemplate`, `@RabbitListener`, connection factory, admin |
| `spring-boot-starter-jdbc` | `JdbcTemplate` và DB transactions |
| `spring-boot-starter-web` | REST endpoint tạo order nếu cần |
| `spring-boot-starter-validation` | Kiểm tra dữ liệu đầu vào |
| `org.postgresql:postgresql` | JDBC driver |
| `spring-boot-starter-actuator` | Health/metrics |
| Flyway/Liquibase, hoặc migration SQL được quản lý | Tạo bảng có version |
| `spring-boot-starter-test` | JUnit, AssertJ, Spring Boot Test |
| `org.testcontainers:postgresql` và `org.testcontainers:rabbitmq` | Integration test với cơ sở dữ liệu và broker thật |
| `org.testcontainers:junit-jupiter` + Awaitility | Vòng đời container và điều kiện bất đồng bộ |

Nếu dùng Spring Boot 4 hoặc Testcontainers 2, artifact/package/Java baseline có thể khác. Dùng **BOM hỗ trợ đồng bộ**; không tự trộn Spring Rabbit và Spring Framework major versions.

### 3.2. Cấu hình Spring Boot

```yaml
spring:
  datasource:
    url: "jdbc:postgresql://localhost:5432/orders_lab"
    username: "orders_app"
    password: "REPLACE_FROM_SECRET_MANAGER"
  rabbitmq:
    host: localhost
    port: 5672
    username: "orders_app"
    password: "REPLACE_FROM_SECRET_MANAGER"
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      type: simple
      simple:
        acknowledge-mode: auto
        prefetch: 10
        concurrency: 2
        default-requeue-rejected: false
```

Các giá trị mật khẩu chỉ là placeholder; hãy nạp secrets qua môi trường triển khai. `default-requeue-rejected=false` trong lab yêu cầu DLX/DLQ được provision; nếu không, lỗi xử lý có thể khiến broker discard message.

- `publisher-confirm-type: correlated` cho phép từng publish attempt có `CorrelationData.getFuture()`.
- `publisher-returns: true` cho phép nhận message không có route.
- `template.mandatory: true` yêu cầu broker gửi `basic.return` khi exchange tồn tại nhưng không có queue route phù hợp.
- `AcknowledgeMode.AUTO` làm container ACK khi listener hoàn thành bình thường; **không phải** broker auto-ack.

`spring.datasource` là DB nguồn của ứng dụng lab. Trong deployment Billing độc lập, service đó phải có **datasource riêng** với bảng `processed_events` và `billing_invoices`; cấu hình ở trên không hàm ý hai microservices dùng một transaction xuyên DB.

### 3.3. Exchange, queue, binding và dead-letter

```java
@Configuration
@EnableRabbit
@EnableScheduling
public class MessagingConfig {

    @Bean
    Declarables ordersTopology() {
        DirectExchange events =
                new DirectExchange("orders.events", true, false);
        DirectExchange dlx =
                new DirectExchange("orders.dlx", true, false);

        Queue billing = QueueBuilder.durable("billing.orders.created")
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("billing.invalid")
                .build();

        Queue invalid = QueueBuilder.durable("billing.orders.invalid")
                .build();

        Binding normalBinding = BindingBuilder.bind(billing)
                .to(events).with("orders.created");
        Binding deadBinding = BindingBuilder.bind(invalid)
                .to(dlx).with("billing.invalid");

        return new Declarables(
                events, dlx, billing, invalid,
                normalBinding, deadBinding);
    }
}
```

Imports tiêu biểu: `org.springframework.amqp.core.*`, `org.springframework.amqp.rabbit.annotation.EnableRabbit`, `org.springframework.scheduling.annotation.EnableScheduling` và `org.springframework.context.annotation.*`.

`RabbitAdmin` thường có thể khai báo các beans topology với Spring Boot; production cũng có thể provision qua Terraform/Kubernetes/CLI. **Không tự động redeclare một queue đang tồn tại với type/arguments khác**: RabbitMQ có thể đóng channel với `PRECONDITION_FAILED`; cần migration riêng.

Sơ đồ:

```text
RabbitTemplate
   |
   | exchange=orders.events, routingKey=orders.created
   v
[direct exchange orders.events]
   | binding("orders.created")
   v
[queue billing.orders.created] ---- @RabbitListener ---> Billing DB
   |
   | NACK/REJECT requeue=false
   v
[dead-letter exchange orders.dlx]
   | binding("billing.invalid")
   v
[queue billing.orders.invalid] ---- operator inspection/replay
```

**Chú ý:** Đây là classic durable queues cho bài lab. Nếu production dùng quorum queue, phải chọn queue type, replication, delivery limit, dead-letter strategy và sizing tương ứng. Dead-letter routing thành công hay không cũng cần kiểm thử; **DLX mặc định không đồng nghĩa bảo đảm at-least-once tới DLQ**.

## 4. Thiết kế bảng PostgreSQL để giao dịch được nguyên tử

Các SQL dưới đây có thể đưa vào một migration có quản lý (ví dụ `V1__orders_outbox.sql`). Không yêu cầu worker này tạo file migration vật lý; nội dung ở đây là ví dụ bài học.

### 4.1. Bảng orders và outbox_events

```sql
CREATE TABLE orders (
    id             uuid PRIMARY KEY,
    state          varchar(32) NOT NULL,
    amount_minor   bigint NOT NULL CHECK (amount_minor > 0),
    currency       varchar(3) NOT NULL,
    version        bigint NOT NULL CHECK (version > 0),
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
    id                 uuid PRIMARY KEY,
    aggregate_id       uuid NOT NULL REFERENCES orders(id),
    aggregate_version  bigint NOT NULL,
    event_type         varchar(80) NOT NULL,
    schema_version     integer NOT NULL,
    payload            jsonb NOT NULL,

    state              varchar(16) NOT NULL DEFAULT 'PENDING'
                       CHECK (state IN
                              ('PENDING', 'IN_FLIGHT', 'RETRY',
                               'SENT', 'BLOCKED')),
    attempts           integer NOT NULL DEFAULT 0,
    next_attempt_at    timestamptz NOT NULL DEFAULT now(),

    claim_token        uuid,
    lease_until        timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    published_at       timestamptz,
    last_error         text,

    UNIQUE (aggregate_id, aggregate_version, event_type)
);

CREATE INDEX outbox_due_idx
    ON outbox_events (next_attempt_at, created_at, id)
    WHERE state IN ('PENDING', 'RETRY');

CREATE INDEX outbox_expired_lease_idx
    ON outbox_events (lease_until, id)
    WHERE state = 'IN_FLIGHT';
```

**Ý nghĩa các cột:**

- `id` chính là **eventId**; giữ nguyên khi relay retry.
- `payload` là JSON đã tạo tại thời điểm business transaction, để relay không phải query trạng thái order hiện tại rồi tạo một nội dung sự kiện khác lúc retry.
- `state=PENDING`: đã commit cùng order nhưng chưa được relay nhận.
- `state=IN_FLIGHT`: một relay đã claim, có `claim_token` và `lease_until`.
- `state=RETRY`: lần gửi trước không được phân loại thành publish thành công; chờ `next_attempt_at`.
- `state=SENT`: broker ACK và không có mandatory return theo chính sách gửi hiện tại.
- `state=BLOCKED`: đã vượt retry budget hoặc có lỗi cần con người sửa; **không** được tự xóa record.
- `attempts` đếm **lần claim/publish thử**, khác số lần xử lý bởi consumer.
- `claim_token` là fencing token dạng UUID để worker cũ không thể cập nhật row đã bị worker mới reclaim.

**Không dùng `state=SENT` làm bằng chứng người nhận đã hoàn tất hóa đơn.** Muốn biết Billing đã xử lý, cần sự kiện/ack ở cấp nghiệp vụ, query projection hoặc một workflow tracking độc lập.

### 4.2. Bảng inbox/dedup của Billing

```sql
CREATE TABLE processed_events (
    consumer_name   varchar(80) NOT NULL,
    event_id        uuid NOT NULL,
    processed_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE billing_invoices (
    order_id       uuid PRIMARY KEY,
    amount_minor   bigint NOT NULL,
    currency       varchar(3) NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
```

Trong lab, cả hai bảng trên có thể nằm trong cùng PostgreSQL để chạy thử. Trong production, đặt chúng trong database thuộc sở hữu Billing. Unique key `(consumer_name,event_id)` cho phép các loại consumer khác nhau xử lý cùng event mà không chặn lẫn nhau.

Một event ID bị gửi lại 3 lần nhưng được xử lý bởi cùng consumer chỉ phải tạo **một business effect**. Khi người vận hành replay, marker khiến sự kiện đã xử lý được bỏ qua; nếu muốn **rebuild projection hoàn toàn mới**, dùng consumer name/namespace khác hoặc reset có kế hoạch thay vì xóa marker production tùy tiện.

## 5. Ghi order và outbox trong CÙNG một transaction

### 5.1. DTO định dạng sự kiện

```java
public record OrderCreatedEvent(
        UUID eventId,
        String eventType,
        int schemaVersion,
        UUID orderId,
        long aggregateVersion,
        Instant occurredAt,
        long amountMinor,
        String currency) {
}
```

Imports: `java.util.UUID` và `java.time.Instant`. Trong một Spring Boot app có Jackson Java Time Module tương thích, `ObjectMapper` được auto-configure thường có thể serialize/deserialize `Instant`. Nếu build tối giản không có module, thêm cấu hình Jackson phù hợp và test JSON round-trip.

**Vì sao event cần `aggregateVersion`?** Dedup theo `eventId` chống lặp cùng event, nhưng không tự chặn **hai event khác nhau đến sai thứ tự**. Các consumer xử lý projection theo trạng thái phải so version/sequence của aggregate khi nghiệp vụ yêu cầu ordering.

### 5.2. OrderCommandService

```java
@Service
public class OrderCommandService {

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public OrderCommandService(
            JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Transactional
    public OrderCreatedEvent createOrder(
            UUID orderId, long amountMinor, String currency) {

        if (orderId == null || amountMinor <= 0
                || currency == null || currency.length() != 3) {
            throw new IllegalArgumentException("Dữ liệu order không hợp lệ");
        }

        OrderCreatedEvent event = new OrderCreatedEvent(
                UUID.randomUUID(),
                "OrderCreated",
                1,
                orderId,
                1,
                Instant.now(),
                amountMinor,
                currency);

        // Serialize trước khi INSERT để không có checked exception
        // thoát khỏi transaction sau khi đã sửa dữ liệu.
        final String payload;
        try {
            payload = mapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Không serialize được event", ex);
        }

        jdbc.update("""
            INSERT INTO orders (
                id, state, amount_minor, currency, version
            ) VALUES (?, 'CREATED', ?, ?, 1)
            """, orderId, amountMinor, currency);

        jdbc.update("""
            INSERT INTO outbox_events (
                id, aggregate_id, aggregate_version,
                event_type, schema_version, payload
            ) VALUES (?, ?, ?, ?, ?, ?::jsonb)
            """,
            event.eventId(),
            event.orderId(),
            event.aggregateVersion(),
            event.eventType(),
            event.schemaVersion(),
            payload);

        return event;
    }
}
```

Imports chính: `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `org.springframework.jdbc.core.JdbcTemplate`, `com.fasterxml.jackson.databind.ObjectMapper`, `com.fasterxml.jackson.core.JsonProcessingException` và các kiểu Java liên quan.

**Điểm then chốt:** Phương thức `createOrder` là **public method của Spring-managed bean** được gọi qua Spring proxy và có transaction manager dành cho đúng `DataSource`. Cả hai `jdbc.update(...)` phải dùng **cùng DataSource** tham gia transaction. Nếu hai statements ở hai DB connections không được cùng transaction điều phối, hoặc method được gọi qua self-invocation bỏ qua Spring proxy, tính nguyên tử có thể không còn.

Nếu `INSERT outbox_events` lỗi, exception runtime của JDBC khiến toàn bộ DB transaction rollback, bao gồm `INSERT orders`. Nếu `INSERT orders` lỗi, outbox cũng không được ghi. Đó là cốt lõi của transactional outbox.

### 5.3. Một API minh họa

```java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderCommandService commands;

    public OrderController(OrderCommandService commands) {
        this.commands = commands;
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> create(
            @RequestBody CreateOrderRequest request) {

        OrderCreatedEvent event = commands.createOrder(
                request.orderId(),
                request.amountMinor(),
                request.currency());

        return ResponseEntity.status(HttpStatus.CREATED).body(
                Map.of(
                    "orderId", event.orderId(),
                    "eventId", event.eventId(),
                    "eventDelivery", "PENDING_ASYNC"));
    }
}

public record CreateOrderRequest(
        UUID orderId, long amountMinor, String currency) {
}
```

Imports phù hợp từ `org.springframework.web.bind.annotation.*`, `org.springframework.http.*`, `java.util.Map` và `java.util.UUID`.

Phản hồi `201 CREATED` ở đây chỉ nói **order đã được ghi trong DB nguồn** và outbox đã được tạo theo transaction. Nó **không** hứa Billing đã tạo hóa đơn ở thời điểm HTTP response được gửi. Contract của API nên ghi rõ trạng thái bất đồng bộ và nơi truy vấn tiến độ xử lý.

Nếu client retry cùng `orderId` sau HTTP timeout, unique key của `orders.id` ngăn tạo hai orders nhưng ví dụ này sẽ trả lỗi duplicate. Production nên xây API idempotency key: kiểm tra request cũ cùng payload thì trả lại kết quả ban đầu; nếu nội dung khác cùng key, trả conflict. **API idempotency** là vấn đề riêng nhưng bổ sung quan trọng cho **message idempotency**.

### 5.4. Bằng chứng về tính nguyên tử

Để kiểm tra đúng transaction:

1. Cho outbox insert ném lỗi có kiểm soát sau orders insert.
2. Gọi `createOrder` qua Spring bean thực.
3. Xác nhận transaction bị rollback; **không có cả row orders lẫn outbox**.
4. Gọi lại bình thường; xác nhận có **đúng một order và một outbox row** cho event.
5. Không cần RabbitMQ hoạt động để bước tạo order/outbox thành công; broker availability ảnh hưởng **relay**, không ảnh hưởng atomicy DB.
6. Nếu database down, toàn bộ API tạo order thất bại; outbox **không thay thế** khả năng commit của DB.

## 6. Thiết kế relay có lease: vì sao không chỉ SELECT PENDING?

### 6.1. Nguy cơ nhiều relay gửi cùng một row

Nếu ba application replicas cùng thực hiện:

```sql
SELECT *
FROM outbox_events
WHERE state = 'PENDING'
LIMIT 100;
```

rồi cả ba publish, cùng một event có thể bị gửi **ba lần** ngay cả khi không có sự cố. At-least-once consumer phải chịu duplicate, nhưng publish trùng không cần thiết làm tăng chi phí và có thể gây áp lực downstream.

Một relay cần **claim atomically**:

- `SELECT ... FOR UPDATE SKIP LOCKED` để nhiều workers lấy các rows khác nhau.
- Chuyển state sang `IN_FLIGHT` và gắn `claim_token` cùng `lease_until` **trước khi publish**.
- Commit transaction claim sớm; **không giữ DB row lock trong lúc chờ broker confirm**.
- Khi nhận ACK/return/NACK, chỉ update row nếu `claim_token` vẫn đúng.
- Sau crash, lease hết hạn để worker khác có thể reclaim.

### 6.2. SQL claim với PostgreSQL SKIP LOCKED

```sql
WITH picked AS (
    SELECT id
    FROM outbox_events
    WHERE (
            state IN ('PENDING', 'RETRY')
            AND next_attempt_at <= now()
          )
       OR (
            state = 'IN_FLIGHT'
            AND lease_until < now()
          )
    ORDER BY created_at, id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_events AS o
SET state = 'IN_FLIGHT',
    claim_token = :new_claim_token,
    lease_until = now() + interval '60 seconds',
    attempts = o.attempts + 1
FROM picked
WHERE o.id = picked.id
RETURNING o.id,
          o.payload::text AS payload,
          o.attempts,
          o.claim_token;
```

`:new_claim_token` là placeholder minh họa SQL, không phải cú pháp của plain `JdbcTemplate`; code Java bên dưới dùng `?`. Khi nhiều relay transactions cùng chạy, một worker chọn row đang bị worker khác lock sẽ **skip** thay vì chờ lâu. `SKIP LOCKED` là công cụ cho **job queue**, không phải một cách đọc snapshot hoàn hảo cho nghiệp vụ phân tích.

**Lease không phải transaction xuyên RabbitMQ.** Một worker bị treo có thể tỉnh lại sau khi lease đã hết và worker mới reclaim cùng row. Vì thế `claim_token` đóng vai trò **fencing** để kết quả cũ không cập nhật đè kết quả của worker mới. Nhưng nó **không ngăn được duplicate publish tới RabbitMQ** khi cả hai attempts đã gửi: dedup ở consumer vẫn bắt buộc.

### 6.3. Code repository: claim một event mỗi tick

```java
public record ClaimedOutbox(
        UUID eventId,
        String payload,
        int attempts,
        UUID claimToken) {
}

@Repository
public class OutboxRepository {

    private final JdbcTemplate jdbc;

    public OutboxRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public List<ClaimedOutbox> claimOne(UUID token) {
        return jdbc.query("""
            WITH picked AS (
                SELECT id
                FROM outbox_events
                WHERE (
                    state IN ('PENDING', 'RETRY')
                    AND next_attempt_at <= now()
                ) OR (
                    state = 'IN_FLIGHT'
                    AND lease_until < now()
                )
                ORDER BY created_at, id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE outbox_events AS o
            SET state = 'IN_FLIGHT',
                claim_token = ?,
                lease_until = now() + interval '60 seconds',
                attempts = o.attempts + 1
            FROM picked
            WHERE o.id = picked.id
            RETURNING
                o.id,
                o.payload::text AS payload,
                o.attempts,
                o.claim_token
            """,
            (rs, rowNum) -> new ClaimedOutbox(
                    rs.getObject("id", UUID.class),
                    rs.getString("payload"),
                    rs.getInt("attempts"),
                    rs.getObject("claim_token", UUID.class)),
            token);
    }

    @Transactional
    public boolean markSent(ClaimedOutbox event) {
        int count = jdbc.update("""
            UPDATE outbox_events
            SET state = 'SENT',
                published_at = now(),
                claim_token = NULL,
                lease_until = NULL,
                last_error = NULL
            WHERE id = ? AND claim_token = ?
                  AND state = 'IN_FLIGHT'
            """, event.eventId(), event.claimToken());
        return count == 1;
    }

    @Transactional
    public boolean markBlocked(
            ClaimedOutbox event, String reason) {
        int count = jdbc.update("""
            UPDATE outbox_events
            SET state = 'BLOCKED',
                claim_token = NULL,
                lease_until = NULL,
                last_error = ?
            WHERE id = ? AND claim_token = ?
                  AND state = 'IN_FLIGHT'
            """, reason, event.eventId(), event.claimToken());
        return count == 1;
    }

    @Transactional
    public boolean scheduleRetry(
            ClaimedOutbox event, String reason) {

        boolean exhausted = event.attempts() >= 8;
        int seconds = Math.min(
                300, 1 << Math.min(event.attempts(), 8));

        int count = jdbc.update("""
            UPDATE outbox_events
            SET state = ?,
                next_attempt_at = now() +
                    (? * interval '1 second'),
                claim_token = NULL,
                lease_until = NULL,
                last_error = ?
            WHERE id = ? AND claim_token = ?
                  AND state = 'IN_FLIGHT'
            """,
            exhausted ? "BLOCKED" : "RETRY",
            seconds,
            reason,
            event.eventId(),
            event.claimToken());

        return count == 1;
    }
}
```

Imports chính: `java.util.List`, `java.util.UUID`, `org.springframework.jdbc.core.JdbcTemplate`, `org.springframework.stereotype.Repository` và `org.springframework.transaction.annotation.Transactional`.

Các cập nhật dựa trên `WHERE id=? AND claim_token=? AND state='IN_FLIGHT'`. Nếu count = 0, kết quả publish đến từ một attempt đã mất ownership hoặc row đã được chuyển trạng thái; relay phải **log/cảnh báo để đối soát**, không update vô điều kiện theo `eventId`.

**Giới hạn của lab:**

- Mỗi tick claim **một row**, xử lý tuần tự để thời gian chờ confirm không vượt lease 60 giây trong điều kiện bình thường. Production có thể claim batch và gửi nhiều publish bất đồng bộ nhưng phải giữ **số in-flight có giới hạn** và tính lại lease duration.
- `lease_until` dùng **DB clock** (`now()`), tránh so sánh đồng hồ của những replicas khác nhau.
- Retry tối đa tám lần là chính sách **minh họa**. Sau đó row `BLOCKED` và được giữ lại để điều tra, không bị xóa.
- `scheduleRetry` áp dụng backoff nhị phân tối đa 300 giây; production cần thêm jitter, phân loại transient/permanent và rate limits.
- Với strict per-aggregate ordering, chỉ claim “row bất kỳ” là **chưa đủ**: một event version 2 có thể đến trước version 1 khi retry; cần điều kiện claim theo aggregate hoặc consumer version checks.
- Để chạy đúng `@Transactional`, repository phải là Spring bean gọi từ **một bean khác**, không self-invocation vào một method transaction.

## 7. Publisher confirms: chỉ đánh dấu SENT sau khi broker chấp nhận

### 7.1. RabbitTemplate và CorrelationData

Relay publish vào exchange `orders.events`, routing key `orders.created` bằng `RabbitTemplate.send`, message JSON UTF-8, `messageId=eventId` và `CorrelationData.id=attemptId`.

```java
public enum PublishOutcome {
    CONFIRMED,
    UNROUTABLE,
    NACK
}

public record PublishResult(
        PublishOutcome outcome,
        String reason) {
}

@Component
public class OutboxRabbitPublisher {

    private final RabbitTemplate rabbit;

    public OutboxRabbitPublisher(RabbitTemplate rabbit) {
        this.rabbit = rabbit;
    }

    public PublishResult sendAndConfirm(ClaimedOutbox event)
            throws Exception {

        CorrelationData correlation = new CorrelationData(
                UUID.randomUUID().toString()); // Attempt ID mới.

        MessageProperties properties = new MessageProperties();
        properties.setMessageId(event.eventId().toString());
        properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setHeader(
                "eventId", event.eventId().toString());

        Message message = new Message(
                event.payload().getBytes(StandardCharsets.UTF_8),
                properties);

        rabbit.send(
                "orders.events",
                "orders.created",
                message,
                correlation);

        // Chờ broker confirm (không phải consumer ACK).
        CorrelationData.Confirm confirm =
                correlation.getFuture().get(8, TimeUnit.SECONDS);

        if (!confirm.isAck()) {
            return new PublishResult(
                    PublishOutcome.NACK, confirm.getReason());
        }

        var returned = correlation.getReturn();
        if (returned != null) {
            return new PublishResult(
                    PublishOutcome.UNROUTABLE,
                    returned.getReplyCode() + ": " +
                    returned.getReplyText());
        }

        return new PublishResult(
                PublishOutcome.CONFIRMED, null);
    }
}
```

Imports gồm `org.springframework.amqp.rabbit.core.RabbitTemplate`, `org.springframework.amqp.rabbit.connection.CorrelationData`, `org.springframework.amqp.core.Message`/`MessageProperties`/`MessageDeliveryMode`, `java.util.UUID`, `java.nio.charset.StandardCharsets` và `java.util.concurrent.TimeUnit`.

**Ba điều kiện đúng:**

1. `publisher-confirm-type=correlated` được bật trên connection factory dùng bởi `RabbitTemplate`.
2. `publisher-returns=true` và `mandatory=true` cùng có hiệu lực nếu muốn nhận thông báo unroutable.
3. `correlation.getReturn()` chỉ được đọc sau khi confirm future hoàn tất; với correlated confirms + returns đúng cấu hình, Spring Rabbit bảo đảm return được gắn trước confirm completion.

**ACK chưa phải đảm bảo consumer đã xử lý.** Với exchange tồn tại nhưng không có binding, broker có thể trả `312 NO_ROUTE` **và sau đó ACK**. Nếu chỉ kiểm tra `confirm.isAck()` mà không kiểm tra `getReturn()`, relay có thể đánh dấu `SENT` cho event không nằm ở queue mong muốn.

Nếu exchange không tồn tại, broker thường đóng channel với `404 NOT_FOUND`; đây **không phải** mandatory return. Spring client có thể ném exception hoặc hoàn tất confirm âm; cần giữ event intent và phân loại nguyên nhân.

### 7.2. Các trạng thái của một publish attempt

| Kết quả quan sát | Thao tác đối với outbox | Lý do |
|---|---|---|
| Confirm ACK, `getReturn() == null` | `SENT` | Đã được broker chấp nhận theo routing policy của lab |
| Confirm ACK, `getReturn() != null` | `BLOCKED`/quarantine cho sai topology | Broker đã xử lý publish nhưng **không tìm thấy route** |
| Confirm NACK | `RETRY` với backoff hoặc `BLOCKED` theo nguyên nhân | Broker/client báo không xác nhận thành công |
| `TimeoutException` khi chờ confirm | `RETRY` nhưng outcome **UNKNOWN** | Broker có thể đã nhận nhưng confirm chưa tới |
| Connection/channel failure | `RETRY` hoặc `BLOCKED` tùy loại lỗi | Có thể đã publish hoặc không |
| Lỗi database khi ghi `SENT` | Giữ record còn chưa chắc đã được đánh dấu | Broker đã có thể nhận; retry tạo duplicate, consumer phải idempotent |

**Lưu ý về alternate exchange:** ACK + no-return chứng minh broker không trả message unroutable **theo cấu hình exchange**, không chứng minh nó đã vào đúng queue nếu exchange có alternate exchange được định tuyến tới nơi khác. Lab dùng direct exchange và binding tường minh không có alternate exchange; production phải kiểm thử topology thật.

## 8. Relay service: poll, publish, cập nhật trạng thái

### 8.1. Cách làm tuần tự dễ kiểm tra

```java
@Component
public class OutboxRelay {

    private static final Logger log =
            LoggerFactory.getLogger(OutboxRelay.class);

    private final OutboxRepository repository;
    private final OutboxRabbitPublisher publisher;

    public OutboxRelay(
            OutboxRepository repository,
            OutboxRabbitPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Scheduled(fixedDelay = 500)
    public void dispatchOne() {
        UUID token = UUID.randomUUID();

        // Transaction claim đã COMMIT khi method trả về.
        List<ClaimedOutbox> batch = repository.claimOne(token);

        for (ClaimedOutbox event : batch) {
            try {
                PublishResult result = publisher.sendAndConfirm(event);

                boolean updated = switch (result.outcome()) {
                    case CONFIRMED -> repository.markSent(event);
                    case UNROUTABLE -> repository.markBlocked(
                            event, "UNROUTABLE: " + result.reason());
                    case NACK -> repository.scheduleRetry(
                            event, "NACK: " + result.reason());
                };

                if (!updated) {
                    log.warn(
                            "Stale claim result ignored, eventId={} token={}",
                            event.eventId(), event.claimToken());
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                repository.scheduleRetry(
                        event, "Interrupted while waiting for confirm");
                return;
            } catch (Exception failure) {
                // Có thể là timeout, network/channel failure hoặc lỗi DB
                // cập nhật SENT. Không suy broker chắc chắn chưa nhận.
                boolean updated = repository.scheduleRetry(
                        event,
                        "UNKNOWN: " + failure.getClass().getSimpleName());
                if (!updated) {
                    log.warn(
                            "Cannot reschedule stale/changed eventId={}",
                            event.eventId());
                }
            }
        }
    }
}
```

Imports chính: `java.util.List`/`UUID`, `org.springframework.stereotype.Component`, `org.springframework.scheduling.annotation.Scheduled` và `org.slf4j.Logger`/`LoggerFactory`.

**Vì sao công việc publish nằm ngoài DB transaction claim?** Nếu giữ row lock khi chờ confirm 8 giây, các DB transactions khác có thể bị trì hoãn, tăng deadlock/connection pool pressure và làm throughput tệ. Claim commit trước publish; sau publish có một transaction mới cập nhật kết quả theo token.

**Đánh đổi của code mẫu:**

- Đây là **polling tuần tự**, tối đa một event mỗi tick. Nó tối ưu tính dễ hiểu, **không** phải throughput tối đa.
- Lỗi `UNROUTABLE` được chuyển `BLOCKED` để người vận hành sửa topology; không retry vô hạn một routing key chắc chắn sai.
- `NACK`/`UNKNOWN` retry có backoff, và sau retry budget row thành `BLOCKED`; mọi lần thử giữ **eventId**.
- `InterruptedException` được khôi phục interrupt flag. Với production, cần phối hợp graceful shutdown và logic repository update khi thread đang interrupted.
- Nếu `sendAndConfirm` bị kẹt lâu hơn lease 60 giây (ví dụ socket blocked), một worker khác có thể reclaim và gửi trùng. **Lease không tự ngăn publish trùng**; cần timeout/watchdog/circuit breaker và fencing token để ngăn stale database update.
- Khi relay có nhiều replicas, claim lock và token cho phép scale nhưng **mỗi replica vẫn cần giới hạn số in-flight**; đừng claim hàng nghìn rows rồi chờ confirms làm lease hết hạn.
- Một lần call `repository.markSent` không thành công sau publish phải được theo dõi: kết quả broker có thể tốt nhưng row vẫn chưa `SENT`, sau đó retry và gây duplicate có chủ đích của mô hình at-least-once.

### 8.2. Trình tự trạng thái

```text
INSERT trong DB transaction
        |
        v
     PENDING
        |
        | claimOne()
        v
    IN_FLIGHT --[ACK + no return]----------------> SENT
        |
        +---------[NACK/UNKNOWN]----------------> RETRY
        |                                            |
        |                        next_attempt_at đến |
        |                                            v
        +<------------- claimOne() <------------------+
        |
        +---------[NO_ROUTE/quá attempts]-----------> BLOCKED
        |
        +---------[worker crash]----> lease expired -> reclaim
```

**Không bao giờ đồng nhất `IN_FLIGHT` với message đã ở queue RabbitMQ.** Nó chỉ nghĩa một worker đang giữ quyền thử gửi. Message có thể chưa được gọi `send`, đang trên socket, đã broker nhận hoặc confirm bị mất.

## 9. Consumer idempotent: nửa còn lại của độ tin cậy

### 9.1. Vì sao mỗi event có thể được nhận nhiều lần?

Với nguồn outbox:

```text
Relay                            RabbitMQ              Billing
  |                                 |                     |
  |--- event E -------------------->|                     |
  |<-- broker confirm ACK ----------|                     |
  X CRASH trước khi mark SENT       |                     |
                                    |--- deliver E ------>|
                                    |                     | DB commit
                                    |<----- consumer ACK --|
  |                                 |                     |
  | recovery, E vẫn chưa SENT       |                     |
  |--- retry event E -------------->|                     |
  |<-- broker confirm ACK ----------|                     |
                                    |--- deliver E ------>|
                                                          |
                                                  dedup marker E
                                                  skip side effect
```

Một lần publish đã thành công rồi relay crash trước khi update outbox sẽ dẫn đến retry cùng event. Consumer còn có thể bị redeliver do **DB commit thành công nhưng broker ACK consumer bị mất**. Cả hai là tình huống **bình thường trong mô hình at-least-once**.

### 9.2. Billing service với unique event marker

```java
@Service
public class BillingService {

    private final JdbcTemplate jdbc;

    public BillingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(OrderCreatedEvent event) {
        int first = jdbc.update("""
            INSERT INTO processed_events (consumer_name, event_id)
            VALUES ('billing-invoice', ?)
            ON CONFLICT DO NOTHING
            """, event.eventId());

        if (first == 0) {
            return; // Đã xử lý event này trong transaction trước.
        }

        jdbc.update("""
            INSERT INTO billing_invoices (
                order_id, amount_minor, currency
            ) VALUES (?, ?, ?)
            """,
            event.orderId(),
            event.amountMinor(),
            event.currency());
    }
}
```

Điều kiện **cực kỳ quan trọng**:

- `processed_events` và `billing_invoices` phải thuộc **cùng transaction DB của Billing**.
- Nếu insert marker thành công nhưng insert invoice lỗi, **cả hai phải rollback**; message có thể retry an toàn.
- Nếu marker đã có, method return bình thường để container ACK duplicate. Không tạo side effect mới.
- Nếu có **hai events khác nhau** cho cùng order nhưng business chỉ cho phép một invoice, unique key của `billing_invoices.order_id` bảo vệ invariant khác với dedup `eventId`. Cần quyết định sự kiện mới nên update hay bị reject.
- Nếu xử lý external HTTP API ngoài DB, marker trong DB **không tự đảm bảo** external side effect exactly-once. Dùng idempotency key cùng event ID với downstream, hoặc outbox/workflow khác cho cuộc gọi đó.

### 9.3. @RabbitListener và chính sách lỗi

```java
@Component
public class BillingOrderListener {

    private final BillingService billing;
    private final ObjectMapper mapper;

    public BillingOrderListener(
            BillingService billing, ObjectMapper mapper) {
        this.billing = billing;
        this.mapper = mapper;
    }

    @RabbitListener(queues = "billing.orders.created")
    public void onOrder(Message message) throws Exception {

        final OrderCreatedEvent event;
        try {
            event = mapper.readValue(
                    message.getBody(), OrderCreatedEvent.class);
        } catch (JsonProcessingException invalidJson) {
            throw new AmqpRejectAndDontRequeueException(
                    "Malformed OrderCreated JSON", invalidJson);
        }

        if (event.eventId() == null
                || event.orderId() == null
                || !"OrderCreated".equals(event.eventType())
                || event.schemaVersion() != 1
                || event.amountMinor() <= 0) {
            throw new AmqpRejectAndDontRequeueException(
                    "Unsupported or invalid event contract");
        }

        // Proxy transaction commit trước khi listener return.
        billing.applyOnce(event);
    }
}
```

Các imports: `org.springframework.amqp.core.Message`, `org.springframework.amqp.rabbit.annotation.RabbitListener`, `org.springframework.amqp.AmqpRejectAndDontRequeueException`, `com.fasterxml.jackson.databind.ObjectMapper`, `com.fasterxml.jackson.core.JsonProcessingException` và `org.springframework.stereotype.Component`.

Spring listener container với `AcknowledgeMode.AUTO` ACK delivery sau khi method trả về bình thường; exception được xử lý theo error policy. `AmqpRejectAndDontRequeueException` yêu cầu reject không requeue, broker dead-letter theo cấu hình queue. **Không có DLX phù hợp thì message có thể bị drop.**

Một lỗi database transient nên được retry có **giới hạn và backoff**; cấu hình `default-requeue-rejected=false` trong lab sẽ từ chối không requeue cả lỗi DB nếu không có retry advice/recoverer phù hợp. Vì vậy production phải **bổ sung policy phân loại lỗi transient vs permanent**, ví dụ retry trong listener với backoff hữu hạn rồi DLQ để vận hành replay, hoặc dùng retry queues có TTL/DLX. Đừng phát sinh vòng nóng `nack(requeue=true)` không giới hạn.

### 9.4. Không gắn ACK của RabbitMQ vào database transaction

```text
Billing DB transaction        RabbitMQ consumer delivery
        |                                |
  insert marker + invoice               |
        |                                |
     COMMIT OK                           |
        |                                |
        +------ listener return -------> |
                                         |
                                    broker basic.ack
```

Nếu connection mất giữa `COMMIT OK` và `basic.ack`, broker có thể redeliver. Dedup marker giữ business effect một lần. Đây là **cách giải thích chính xác hơn** việc nói “đặt `@Transactional` trên listener là đủ đảm bảo không lặp”.

### 9.5. Schema evolution và ordering

- Thêm `schemaVersion` để consumer nhận biết payload version; khi có breaking change cần migration hoặc dual-read version.
- `eventId` giữ ổn định qua retry.
- `aggregateVersion` tăng theo mỗi sự kiện mới của cùng order. Nếu consumer xử lý version 3 trước version 2, dedup theo ID **không phát hiện được** thiếu version 2; cần version checkpoint/optimistic concurrency nếu nghiệp vụ phụ thuộc thứ tự.
- RabbitMQ queue có thể có nhiều consumers, prefetch, requeue và concurrency; **không tự suy strict ordering đầu cuối**.
- Khi schema mới không đọc được, fail sang DLQ/quarantine có kiểm soát thay vì bỏ qua silent và ACK.

## 10. Dựng lab bằng Docker Compose và chạy theo từng bước

### 10.1. PostgreSQL và RabbitMQ

Trong môi trường học tập cô lập, có thể dùng cấu hình Compose sau (lưu thành `compose.yaml` trong **dự án thực hành riêng** khi làm lab):

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: orders_lab
      POSTGRES_USER: orders_app
      POSTGRES_PASSWORD: lab-only-password
    ports:
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U orders_app -d orders_lab"]
      interval: 5s
      timeout: 3s
      retries: 20
    volumes:
      - postgres_data:/var/lib/postgresql/data

  rabbitmq:
    image: rabbitmq:4.1-management
    environment:
      RABBITMQ_DEFAULT_USER: orders_app
      RABBITMQ_DEFAULT_PASS: lab-only-password
    ports:
      - "127.0.0.1:5672:5672"
      - "127.0.0.1:15672:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 20
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq

volumes:
  postgres_data:
  rabbitmq_data:
```

**Chỉ dùng mật khẩu dễ đọc ở lab.** Production cần secrets, TLS, network policies, persistent-volume/backup và version pinning. Hình thức bind `127.0.0.1` giúp tránh mở dịch vụ ra mạng ngoài máy học. Nếu môi trường dùng WSL/remote Docker hoặc CI, host mapping và port có thể khác.

Trong `application.yml` của lab, dùng credential của Compose hoặc inject qua environment:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_lab
    username: orders_app
    password: lab-only-password
  rabbitmq:
    host: localhost
    port: 5672
    username: orders_app
    password: lab-only-password
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
        prefetch: 10
```

Chạy theo trình tự minh họa:

```bash
docker compose up -d
docker compose ps

# Áp SQL migration ở mục 4 bằng công cụ migration dự án
# hoặc psql vào database trong lab trước khi start app.

# Chạy ứng dụng Spring Boot từ dự án thực hành đã cài dependencies.
./mvnw spring-boot:run
```

Với Gradle thì dùng nhiệm vụ run tương đương. Bài viết **không** thực thi các lệnh này; học viên thực hiện trong dự án lab đã chuẩn bị.

### 10.2. Tạo đơn hàng

Gửi yêu cầu:

```bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "b0375d03-09cb-43f3-9933-1ef27e06c0cc",
    "amountMinor": 125000,
    "currency": "VND"
  }'
```

Phản hồi minh họa:

```json
{
  "orderId": "b0375d03-09cb-43f3-9933-1ef27e06c0cc",
  "eventId": "e83c339f-b7b6-49a7-b1db-2f74974ab29a",
  "eventDelivery": "PENDING_ASYNC"
}
```

`eventId` là UUID sinh ra trong lần chạy thực tế, **không nhất thiết giống** giá trị JSON mẫu. Ngay sau khi API trả response, row outbox có thể đang `PENDING`, `IN_FLIGHT` hoặc đã `SENT` tùy tốc độ relay. Không viết test chỉ assert một state thoáng qua nếu scheduler đang chạy.

### 10.3. Xem các bảng

```sql
SELECT id, state, amount_minor, currency, version
FROM orders
ORDER BY created_at DESC
LIMIT 10;

SELECT id, aggregate_id, event_type, state,
       attempts, next_attempt_at, lease_until,
       published_at, last_error
FROM outbox_events
ORDER BY created_at DESC
LIMIT 10;

SELECT consumer_name, event_id, processed_at
FROM processed_events
ORDER BY processed_at DESC
LIMIT 10;

SELECT order_id, amount_minor, currency
FROM billing_invoices
ORDER BY created_at DESC
LIMIT 10;
```

Kỳ vọng khi broker, exchange, binding và consumer khỏe:

1. `orders` có đúng một order.
2. `outbox_events` có một event ID và cuối cùng thành `SENT`.
3. Billing nhận message và ghi một marker trong `processed_events`.
4. `billing_invoices` có một invoice tương ứng.
5. RabbitMQ queue work không tích lũy backlog dài hạn; DLQ không tăng.

**Thứ tự quan sát có thể khác:** Outbox có thể đạt `SENT` trước khi Billing tạo invoice, vì publisher confirm diễn ra trước business commit phía consumer. Đó không phải race bug; đó là **hợp đồng bất đồng bộ**.

### 10.4. Xem RabbitMQ Management

Trên RabbitMQ Management ở địa chỉ localhost port 15672 của lab, xem:

- Exchange `orders.events` và binding key `orders.created`.
- Queue `billing.orders.created`: ready, unacked, consumer count.
- Dead-letter exchange `orders.dlx` và queue `billing.orders.invalid`.
- Deliver/ACK rates khi gửi nhiều order.
- Connection/channel state khi dừng/restart ứng dụng.

**Không dùng queue depth bằng 0 làm bằng chứng duy nhất**: queue có thể rỗng vì người nhận đã ACK, nhưng cũng có thể bị purge, expire, reject hoặc routing sai. Đối chiếu kết quả với **database Billing**.

## 11. Fault injection: chứng minh các khoảng lỗi thay vì chỉ happy path

Một transactional outbox đạt yêu cầu khi **vẫn đúng dưới sự cố**, không chỉ khi server và mạng ổn định.

### 11.1. Ma trận sự cố theo thời điểm

| Vị trí sự cố | Trạng thái DB nguồn | Message ở RabbitMQ | Kỳ vọng recovery |
|---|---|---|---|
| Trước DB transaction commit | Order và outbox đều rollback | Chưa có publish do relay chỉ đọc committed rows | API fail, không có ghost event |
| Sau DB commit, trước relay claim | Order + outbox `PENDING` | Chưa publish | Relay khởi động lại, tiếp tục |
| Sau claim commit, trước publish | Outbox `IN_FLIGHT` có lease | Chưa publish | Lease hết hạn, worker khác reclaim |
| Sau broker lưu message, trước publisher confirm đến app | Outbox còn `IN_FLIGHT`/`RETRY` | Có thể đã có message | Retry cùng event ID, có thể duplicate |
| Sau confirm ACK, trước `markSent` DB commit | Outbox chưa `SENT` | Message đã được broker nhận | Retry có thể gửi lại; Billing dedup |
| Sau `SENT`, trước consumer delivery | Outbox `SENT` | Message ready/chờ delivery | Consumer chạy lại sẽ xử lý |
| Sau consumer DB commit, trước consumer ACK | Billing đã có invoice + marker | Broker chưa chắc nhận ACK | Redelivery được dedup |
| Payload sai schema | Outbox có thể `SENT` | Consumer reject/DLQ | Điều tra, sửa schema và replay có kiểm soát |
| Broker down kéo dài | Outbox PENDING/RETRY/IN_FLIGHT/BLOCKED | Publish không tiến triển | Backoff, capacity, alert, không mất intent |
| DLQ/unroutable | Outbox có thể BLOCKED hoặc event vào DLQ | Tùy vị trí lỗi | Sửa topology/consumer, audit và replay |

**Bảo đảm cốt lõi:** Outbox giải quyết “đã commit business state nhưng quên sự kiện” bằng DB atomicity; dedup giải quyết “cùng sự kiện tới nhiều lần”. **Không có thao tác đơn lẻ** nào bảo đảm cả hai trên hai hệ thống độc lập.

### 11.2. Thí nghiệm A — Broker down trước khi tạo order

1. Dừng RabbitMQ **trong lab**, giữ PostgreSQL hoạt động.
2. Gọi API tạo order.
3. Xác nhận `orders` và `outbox_events` được commit (API thành công theo contract nguồn).
4. Relay không thể nhận publisher confirm tốt; record vẫn ở PENDING/RETRY/IN_FLIGHT rồi được reclaim theo lease/backoff.
5. Khởi động RabbitMQ lại, kiểm tra outbox cuối cùng `SENT` và Billing tạo invoice.
6. Đối chiếu `eventId` ở DB nguồn và marker ở Billing.

Nếu API tạo order cũng không hoạt động vì code bắt buộc kết nối RabbitMQ trước khi ghi DB, kiến trúc **chưa tách độc lập transaction nguồn với relay** đúng cách.

### 11.3. Thí nghiệm B — Outbox insert lỗi, order rollback

1. Trong test DB cô lập, dùng fault injection có kiểm soát để statement insert outbox ném lỗi sau insert orders.
2. Gọi `createOrder` qua bean có `@Transactional`.
3. Xác nhận **không tồn tại order** và **không tồn tại outbox event** cho request đó.
4. Không có message `OrderCreated` mới xuất hiện do relay chỉ poll committed rows.
5. Gỡ fault, thử lại và kiểm tra một transaction bình thường.

Ví dụ một test-only PostgreSQL trigger có thể chủ động ném exception khi insert outbox, nhưng **không** cài trigger lỗi này vào schema production. Mục tiêu là chứng minh tính nguyên tử **hai câu INSERT** thực sự dùng cùng transaction manager.

### 11.4. Thí nghiệm C — Relay crash sau claim

1. Có một outbox row `PENDING`.
2. Cho relay `claimOne` thành `IN_FLIGHT`.
3. Dừng relay trước khi `sendAndConfirm`.
4. Đợi lease hết hạn trên DB test clock.
5. Khởi động lại relay; nó reclaim với `claim_token` **khác**.
6. Message được publish sau recovery và event ID **không đổi**.

**Không dùng Spring Retry local memory làm bản ghi ý định gửi:** process crash sẽ xóa mọi in-memory work. Bản row outbox chính là nơi bền vững cần tồn tại xuyên restart.

### 11.5. Thí nghiệm D — Broker nhận event, relay crash trước SENT

1. Publish event, chờ broker xác nhận hoặc sử dụng fault injection tại điểm sau confirm.
2. Dừng process relay **trước khi gọi `markSent`**.
3. Outbox row còn `IN_FLIGHT`, lease hết hạn.
4. Relay khác reclaim và publish cùng payload/event ID một lần nữa.
5. Billing có thể nhận **hai delivery** nhưng `billing_invoices` chỉ có **một invoice** nhờ `processed_events`.

Nếu test chỉ thấy invoice count = 1 nhưng chưa chứng minh delivery trùng đã xảy ra, ghi thêm **application dedup counter** hoặc listener invocation count trong test để phân biệt “không có duplicate” với “duplicate đã bị chặn đúng”.

### 11.6. Thí nghiệm E — Mất consumer ACK sau DB commit

1. Cho Billing commit marker và invoice.
2. Cắt connection/channel consumer trước khi broker nhận ACK, trong môi trường fault test có kiểm soát.
3. RabbitMQ có thể redeliver message.
4. Billing thấy marker đã có, skip business effect và return bình thường.
5. Broker nhận ACK của lần delivery mới; không có invoice thứ hai.

Không đặt transaction commit của Billing **sau** consumer ACK. Nếu ACK sớm rồi DB rollback, broker có thể đã bỏ message và hóa đơn không bao giờ được tạo.

### 11.7. Thí nghiệm F — Exchange thiếu hoặc routing sai

Để thử mandatory return, giữ exchange `orders.events` tồn tại nhưng dùng routing key **không có binding** trong một **test publisher/config**. Khi `mandatory=true`:

- Broker có thể gửi return `312 NO_ROUTE` rồi confirm ACK.
- Relay phân loại `UNROUTABLE` và giữ bản ghi `BLOCKED`, không đánh dấu `SENT`.
- Sau khi sửa binding/config, operator cho phép retry/replay có kiểm soát.
- Kiểm tra Billing nhận event với cùng event ID.

Khi publish tới exchange **không tồn tại**, RabbitMQ thường đóng channel với `404 NOT_FOUND`; đây **không phải** NO_ROUTE return. Không gộp hai lỗi topology thành một nhãn “RabbitMQ down”.

### 11.8. Thí nghiệm G — Nhiều relay replicas

1. Chạy hai relay processes kết nối **cùng PostgreSQL** nguồn.
2. Seed 50 outbox rows ở trạng thái PENDING.
3. Ghi `claim_token`/workerId cho mỗi attempt ở log kiểm thử.
4. Xác minh `FOR UPDATE SKIP LOCKED` tránh **cùng một row bị hai transactions claim đồng thời**.
5. Cố ý để một lease hết hạn khi worker cũ đang chậm.
6. Worker mới reclaim; worker cũ nhận confirm muộn và gọi `markSent` với token cũ.
7. Xác nhận update của worker cũ trả **0 rows**, không ghi đè trạng thái attempt mới.
8. Dù fencing hoạt động, **duplicate publish vẫn có thể xảy ra**; Billing dedup là tuyến bảo vệ cuối.

### 11.9. Thí nghiệm H — Payload poison

1. Trong lab, tạo event payload không đúng schema version hoặc JSON không parse được.
2. Relay vẫn có thể publish và broker confirm thành công; outbox có thể `SENT`.
3. Listener phân loại permanent error và reject không requeue.
4. Message vào `billing.orders.invalid` nếu DLX/binding đúng.
5. Quan sát DLQ count, reason/`x-death` và sự kiện gốc.
6. Sửa dữ liệu/schema bằng một quá trình **replay được phê duyệt**, không tự nuốt lỗi và gọi ACK.

**Đừng xóa event khỏi DLQ ngay khi nhận lỗi.** DLQ là nơi giữ bằng chứng sự kiện chưa xử lý để điều tra, cần chính sách retention và access control.

## 12. Testcontainers và kiểm thử tích hợp

Mock `RabbitTemplate` giúp unit test logic “nếu confirm ACK thì mark SENT”, nhưng **không thể xác nhận** bản ghi PostgreSQL rollback thật, broker mandatory return hay consumer ACK/redelivery. Dùng **PostgreSQL + RabbitMQ thật** trong Testcontainers cho các bất biến quan trọng.

### 12.1. Khung integration test

Ví dụ với Testcontainers **1.x**, Spring Boot Test và JUnit Jupiter:

```java
@Testcontainers
@SpringBootTest
class OutboxEndToEndIT {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>(
                    DockerImageName.parse("postgres:16-alpine"));

    @Container
    static final RabbitMQContainer RABBIT =
            new RabbitMQContainer(
                    DockerImageName.parse("rabbitmq:4.1-management"));

    @DynamicPropertySource
    static void containers(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add(
                "spring.datasource.username", POSTGRES::getUsername);
        registry.add(
                "spring.datasource.password", POSTGRES::getPassword);

        registry.add(
                "spring.rabbitmq.host", RABBIT::getHost);
        registry.add(
                "spring.rabbitmq.port", RABBIT::getAmqpPort);
        registry.add(
                "spring.rabbitmq.username", RABBIT::getAdminUsername);
        registry.add(
                "spring.rabbitmq.password", RABBIT::getAdminPassword);
    }

    @Autowired OrderCommandService orders;
    @Autowired JdbcTemplate jdbc;

    @Test
    void orderAndEventEventuallyCreateOneInvoice() {
        UUID orderId = UUID.randomUUID();
        OrderCreatedEvent event =
                orders.createOrder(orderId, 125000, "VND");

        await().atMost(Duration.ofSeconds(20))
                .untilAsserted(() -> {
                    String state = jdbc.queryForObject("""
                        SELECT state
                        FROM outbox_events
                        WHERE id = ?
                        """, String.class, event.eventId());

                    Integer count = jdbc.queryForObject("""
                        SELECT count(*)
                        FROM billing_invoices
                        WHERE order_id = ?
                        """, Integer.class, orderId);

                    assertThat(state).isEqualTo("SENT");
                    assertThat(count).isEqualTo(1);
                });
    }
}
```

Imports cần bổ sung: `org.junit.jupiter.api.Test`, `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.test.context.DynamicPropertySource`/`DynamicPropertyRegistry`, `org.testcontainers.containers.PostgreSQLContainer`/`RabbitMQContainer`, `org.testcontainers.junit.jupiter.Container`/`Testcontainers`, `org.testcontainers.utility.DockerImageName`, `org.springframework.jdbc.core.JdbcTemplate`, `java.time.Duration`, `java.util.UUID`, Awaitility `await` và AssertJ `assertThat`.

**Điều kiện cần bổ sung khi chạy thật:**

- Spring test context phải chứa các beans Orders, Outbox relay, Billing và `MessagingConfig` được khai báo trong bài.
- Migration SQL ở mục 4 phải được chạy tự động (Flyway/Liquibase) **trước khi test**.
- Broker phải khai báo exchange–binding–queue đúng lúc app start.
- Scheduler `@EnableScheduling` phải hoạt động cho test end-to-end; test độc lập cho repository có thể dùng config khác để không bị relay tranh rows.
- Testcontainers 2.x có thay đổi module/package; chọn phiên bản tương thích theo BOM.
- Nếu test chạy song song, dùng **DB/schema và queue namespaces cô lập**, tránh một test xóa bảng/queue của test khác.
- `RabbitMQContainer` và `PostgreSQLContainer` cần container runtime khả dụng trong CI.

**Không dùng `Thread.sleep(5000)` thay `Awaitility`.** Kết quả từ broker/relay/consumer là bất đồng bộ; test cần chờ điều kiện thực với timeout hữu hạn. `count=1` cũng phải được kết hợp test redelivery thật để kiểm chứng idempotency trong failure scenarios.

### 12.2. Unit tests cho state transitions

Ngoài integration test, tách lớp publisher/transport hoặc dùng mock có kiểm soát để kiểm tra bảng:

| Input giả lập | Trạng thái outbox mong đợi |
|---|---|
| Confirm ACK, không returned message | `SENT` |
| Confirm ACK, có `NO_ROUTE` | `BLOCKED` |
| Negative confirm | `RETRY`, tăng attempts; sau budget `BLOCKED` |
| Confirm timeout | `RETRY` với lý do UNKNOWN; eventId không đổi |
| DB update `markSent` lỗi | Row chưa xác nhận `SENT`; có reconciliation/retry |
| Worker cũ dùng claim token đã hết hạn | Update 0 row, không đè token mới |
| Worker được claim nhưng crash | Lease hết hạn, job được reclaim |
| Consumer xử lý cùng eventId hai lần | Một invoice, một marker |
| JSON payload malformed | Listener error/DLQ, không ghi invoice |
| Không có broker khi source commit | Order + outbox vẫn được commit |

Đối với logic retry/lease, dùng **test clock/database time** hoặc điều chỉnh lease có chủ đích, thay vì bắt test chờ 60 giây cho mỗi kịch bản.

### 12.3. Cần test nguồn transaction manager

Unit test với mock `JdbcTemplate` không thể chứng minh hai câu SQL cùng rollback. Bài test DB thật phải cố ý làm lần ghi outbox thất bại sau ghi orders và xác minh:

```sql
SELECT count(*)
FROM orders
WHERE id = 'b0375d03-09cb-43f3-9933-1ef27e06c0cc';

SELECT count(*)
FROM outbox_events
WHERE aggregate_id = 'b0375d03-09cb-43f3-9933-1ef27e06c0cc';
```

Kết quả cả hai phải bằng 0 sau rollback. Chú ý nếu test method tự có `@Transactional` và framework rollback test ở cuối thì có thể **che một lỗi transaction boundary của service**; hãy chủ động kiểm soát test transaction và verify từ một transaction/connection độc lập sau service call.

## 13. Hiệu năng: mở rộng relay mà không phá bất biến

Polling một row mỗi 500 ms giúp lab dễ hiểu nhưng **không thích hợp workload hàng nghìn message/giây**. Khi mở rộng:

1. Claim batch size hữu hạn dựa trên **số worker slots sẵn có**.
2. Gửi nhiều attempts bằng `CorrelationData.getFuture().whenComplete(...)` thay vì chờ từng confirm.
3. Giới hạn outstanding publishes bằng `Semaphore`/bounded executor; không tích lũy futures và payload trong RAM vô hạn.
4. Xử lý confirm/return nhanh, chuyển cập nhật DB sang worker pool được giới hạn nếu callback thread nhạy cảm với latency.
5. Đặt lease duration lớn hơn thời gian publish/confirm/DB update dự kiến, nhưng luôn có watchdog/circuit breaker cho attempts bị kẹt.
6. Không claim batch 1.000 rows rồi giữ chúng `IN_FLIGHT` trong khi publisher chỉ có 20 slots.
7. Nếu broker dừng nhận confirms, giảm tốc/dừng claim, để outbox pending tạo **backpressure nhìn thấy được**, không crash JVM.
8. Dùng indexes, retention/archiving và pagination hợp lý khi bảng outbox lớn.

### 13.1. Số in-flight và độ trễ confirm

Trong hệ tương đối ổn định:

\[
L \approx \lambda \times W
\]

Với throughput mục tiêu `1.000 publish/giây` và mean publisher confirm RTT `0,1 giây`, số outstanding trung bình khoảng `100`. Để chịu burst, có thể thử window 128/256 rồi benchmark, **không có con số mặc định đúng cho mọi cluster/queue type**.

**Giới hạn của mô hình:** Công thức dùng **mean**, không dùng p95 để tính đúng \(L\) trung bình. Confirm timeout hoặc network outage phá giả định steady-state; không giải quyết bằng cách mở window vô hạn. Quorum queue, replication, disk durability và mạng cũng ảnh hưởng confirm RTT.

### 13.2. Một publisher attempt luôn có hai ID

```text
Business eventId = E-501  (giữ nguyên)

Attempt 1:
  CorrelationData.id = A-1
  broker ACK nhưng relay crash

Attempt 2:
  CorrelationData.id = A-2
  broker ACK và outbox mark SENT

Billing thấy eventId E-501 hai lần -> xử lý nghiệp vụ một lần
```

**Đừng dùng CorrelationData attempt ID làm dedup key**: nó đổi mỗi lần retry. Ngược lại, không dùng một `CorrelationData` object duy nhất cho nhiều publishes đang chờ; sẽ khó ghép kết quả confirm đúng attempt.

### 13.3. Outbox polling với ordering per aggregate

`FOR UPDATE SKIP LOCKED` ưu tiên throughput/concurrency; nó **không bảo đảm publish theo thứ tự version** nếu một event bị retry còn event sau đã sẵn sàng. Khi nghiệp vụ cần thứ tự:

- Thiết kế claim chỉ lấy event version tiếp theo của từng `aggregate_id`.
- Hoặc phân vùng công việc theo aggregate hash để cùng order đi qua một đường phát tuần tự.
- Hoặc consumer dùng `aggregateVersion` và giữ/checkpoint version, reject hoặc defer event đến quá sớm.
- Không phụ thuộc chỉ vào RabbitMQ queue FIFO khi có nhiều consumers, retries, DLQ hoặc redeliveries.

**Đừng khóa toàn bộ bảng outbox** để đạt ordering nếu throughput lớn. Cần chọn ranh giới cần thứ tự: **toàn queue**, **theo order**, hay chỉ **state transitions cùng aggregate**.

### 13.4. Polling outbox so với CDC

| Cách relay | Ưu điểm | Đánh đổi |
|---|---|---|
| **Polling SQL + SKIP LOCKED** | Triển khai rõ với Spring JDBC, kiểm soát retries, dễ lab/debug | Tạo query tải DB, cần lease/backoff/cleanup, latency phụ thuộc lịch poll |
| **CDC từ WAL (ví dụ Debezium outbox pattern)** | Giảm polling, bắt committed changes từ database log | Cần vận hành CDC connector, schema/outbox event router, recovery/offset, delivery semantics, quyền replication |
| **Publish trực tiếp trong DB transaction** | Code ngắn | **Không atomic giữa DB và RabbitMQ**; không thay transactional outbox |
| **AMQP transaction/confirm riêng** | Biết broker outcome | Không đóng được dual-write gap của DB nguồn |

CDC **không tự tạo exactly-once nghiệp vụ** và không loại bỏ consumer idempotency. Tùy pipeline, vẫn có replay/duplicate khi connector khôi phục hoặc offset chưa được commit. Trong bài lab, polling đơn giản là lựa chọn phù hợp để thấy rõ mọi bước.

## 14. Retry, dead-letter và vòng đời của event bị lỗi

### 14.1. Hai loại retry không được trộn

**Publisher relay retry** xảy ra **trước khi có xác nhận publish tốt**:

```text
PENDING -> IN_FLIGHT -> RETRY -> IN_FLIGHT -> SENT
                             \
                              -> BLOCKED
```

**Consumer retry** xảy ra khi message **đã ở queue RabbitMQ** nhưng Billing xử lý lỗi:

```text
RabbitMQ work queue -> Billing listener -> transient failure
                         |
                         +-- bounded retry/backoff
                         |
                         +-- exhausted -> DLQ
```

Hai retry loops có **định danh và metrics khác nhau**. Một event có thể đã `SENT` ở outbox nhưng vẫn nằm trong DLQ của Billing. Không quay lại trạng thái `RETRY` của outbox chỉ vì Billing báo lỗi: đó là workflow downstream phải được xử lý riêng, tránh tự động publish trùng không cần thiết.

### 14.2. Phân loại lỗi

| Lỗi | Thường xử lý như thế nào? | Điều cần tránh |
|---|---|---|
| RabbitMQ tạm mất kết nối | Relay backoff/UNKNOWN retry, event ID giữ nguyên | Retry nóng, xóa outbox |
| Broker confirm timeout | UNKNOWN; đợi recovery và retry idempotent | Khẳng định broker chưa nhận |
| Exchange không tồn tại | Sửa topology; BLOCKED hoặc retry có giới hạn sau deploy fix | Retry vô hạn lỗi 404 |
| Exchange có nhưng route sai | Mandatory return, BLOCKED/quarantine | Đánh dấu SENT chỉ vì ACK |
| Malformed JSON tại consumer | Permanent failure, reject không requeue vào DLQ | Infinite requeue loop |
| DB Billing tạm lỗi | Retry hữu hạn có backoff | ACK sớm rồi mất event |
| Dữ liệu vi phạm quy tắc nghiệp vụ | Reject/quarantine và audit | Nuốt exception rồi ACK nếu chưa xử lý |
| Dup eventId | Xử lý no-op, ACK delivery | Tạo invoice trùng |
| DLQ target unavailable | Theo policy broker; phát cảnh báo và khắc phục | Giả định dead-letter luôn lossless |

### 14.3. Replay có trách nhiệm

Khi sửa schema/bug consumer, replay DLQ cần:

1. Xác minh root cause đã được giải quyết.
2. Chọn **một tập event IDs có thể kiểm kê**, không replay toàn bộ production DLQ tùy tiện.
3. **Giữ nguyên eventId và thông tin nghiệp vụ gốc**; chỉ thay payload qua migration có version/audit rõ.
4. Publish lại với routing hợp lệ, mandatory returns/confirms và quan sát kết quả.
5. Consumer dedup, hoặc dùng một consumer namespace mới nếu xây lại projection.
6. Theo dõi số processed, duplicate skips, DLQ mới và dữ liệu chênh lệch.
7. Chỉ xóa/archive DLQ records khi có bằng chứng nghiệp vụ đã hoàn tất và retention policy cho phép.

**Không xóa marker `processed_events` production** chỉ để làm message được xử lý lần nữa nếu side effect cũ vẫn còn. Làm vậy có thể tạo invoice thứ hai hoặc gọi external provider thêm một lần.

### 14.4. Recovery của outbox BLOCKED

`BLOCKED` biểu thị một publish intent cần điều tra, không phải event bị loại bỏ. Khi operator sửa exchange/binding hoặc credentials:

```sql
-- Chỉ chạy cho đúng event ID đã kiểm tra và sửa root cause.
UPDATE outbox_events
SET state = 'RETRY',
    next_attempt_at = now(),
    claim_token = NULL,
    lease_until = NULL,
    last_error = NULL
WHERE id = 'e83c339f-b7b6-49a7-b1db-2f74974ab29a'
  AND state = 'BLOCKED';
```

Trong production thao tác phải có authorization, audit log, change request và theo dõi eventId. Nếu row đã được `SENT` hoặc đang `IN_FLIGHT`, không ép state về RETRY bằng SQL trên mà không có kiểm soát, vì worker khác có thể đang xử lý.

## 15. Observability: nhìn được cả “DB đã ghi” và “broker đã nhận”

### 15.1. Metrics nên có

| Chỉ số | Ý nghĩa vận hành |
|---|---|
| `app.outbox.pending.count` | Số record PENDING/RETRY đang chờ publish |
| `app.outbox.inflight.count` | Số record đang được relay claim và chưa hoàn tất |
| `app.outbox.expired_lease.count` | Row IN_FLIGHT quá lease; dấu hiệu relay crash/stuck |
| `app.outbox.blocked.count` | Event cần operator xử lý |
| `app.outbox.oldest_pending.age` | Tuổi intent chưa được publish, đo **từ DB created_at** |
| `app.outbox.publish.confirm.duration` | Thời gian từ publish attempt đến confirm |
| `app.outbox.publish.outcome.total` | Counts ACK/NACK/UNROUTABLE/UNKNOWN phân biệt |
| `app.outbox.publish.retry.total` | Số attempts lại và nguyên nhân |
| `app.billing.event.duplicates.total` | Số lần consumer skip vì eventId đã xử lý |
| `app.billing.business.commits.total` | Số nghiệp vụ tạo invoice thành công |
| RabbitMQ ready/unacked, consumer count, ACK rate | Broker và listener có tiến triển không |
| `billing.orders.invalid` depth | Số poison/permanent errors cần điều tra |
| End-to-end age | Từ Order DB commit/occurredAt đến Billing DB commit |

**Không gắn `eventId`, `orderId`, `attemptId` hoặc payload vào metric labels**: cardinality quá cao. Dùng logs/traces có IDs, kiểm soát dữ liệu nhạy cảm và trace sampling.

### 15.2. SQL cảnh báo outbox backlog

```sql
SELECT state, count(*) AS events
FROM outbox_events
GROUP BY state
ORDER BY state;

SELECT extract(epoch FROM (now() - min(created_at)))
       AS oldest_unsent_age_seconds
FROM outbox_events
WHERE state IN ('PENDING', 'RETRY', 'IN_FLIGHT', 'BLOCKED');

SELECT count(*) AS expired_leases
FROM outbox_events
WHERE state = 'IN_FLIGHT'
  AND lease_until < now();

SELECT id, attempts, last_error, created_at
FROM outbox_events
WHERE state = 'BLOCKED'
ORDER BY created_at
LIMIT 50;
```

Một cảnh báo tốt phải nêu rõ business impact:

- **Critical:** Oldest unsent event vượt SLO, dù RabbitMQ queue depth bằng 0 (nghẽn trước broker).
- **Warning:** NACK/confirm timeout/unknown outcomes tăng cùng outbox retries.
- **Critical:** Outbox BLOCKED có event nghiệp vụ quan trọng không được xử lý.
- **Warning:** `expired_lease` tăng nhiều, có thể relay crash, timeout quá ngắn hoặc DB transaction kẹt.
- **Critical:** Consumer Billing không có ACK rate trong khi queue ready tăng hoặc business age quá hạn.
- **Warning:** DLQ/duplicate skips tăng bất thường sau network outage/rolling deploy.

### 15.3. Định nghĩa đúng latency

```text
Orders transaction COMMIT
     |
     +------ outbox waiting / polling lag -------+
                                                 |
                                           publish attempt
                                                 |
     +------ RabbitMQ confirm latency -----------+
                                                 |
                                           broker ready/consumer
                                                 |
     +------ listener + Billing DB commit -------+
                                                 |
                                           business complete
```

**Publisher confirm latency** không bằng **queue waiting** và không bằng **business end-to-end latency**. Nếu outbox relay down, RabbitMQ không có backlog nhưng đơn hàng vẫn chờ hóa đơn. Vì vậy phải đo **outbox pending age** cùng RabbitMQ ready/unacked và Billing commit latency.

### 15.4. Structured logging và tracing

Ví dụ log mục tiêu:

```text
service=orders-relay
eventId=e83c339f-b7b6-49a7-b1db-2f74974ab29a
attemptId=ffa1056e-c9e2-4b9c-ae98-6771f11f61f7
claimToken=521ce635-f5a5-4d12-924d-83491d1f0a41
exchange=orders.events
routingKey=orders.created
outcome=UNKNOWN
reason=PUBLISH_CONFIRM_TIMEOUT
retryAfterSeconds=32
```

Đây là **gợi ý log do ứng dụng tự tạo**, không phải một log mặc định của Spring Rabbit. Đừng log toàn bộ payload/PII. Distributed tracing qua AMQP headers có thể nối Orders API → relay → Billing nhưng cần bảo toàn trace context khi event nằm nhiều phút trong outbox, và phân biệt parent/linked spans theo tracing policy.

## 16. Dữ liệu, phân quyền và retention

Transactional outbox được thiết kế để không quên ý định gửi, nhưng bản thân outbox là **một kho dữ liệu** phải được quản lý.

### 16.1. Quyền tối thiểu

- Orders app chỉ cần quyền SQL phù hợp trên `orders` và `outbox_events` thuộc DB của nó.
- Billing app chỉ cần quyền trên `processed_events` và `billing_invoices` của Billing.
- RabbitMQ Orders publisher cần quyền **write exchange phù hợp**; Billing consumer cần quyền **read queue phù hợp**; quyền configure topology có thể thuộc IaC/admin riêng.
- API replay DLQ, chỉnh `BLOCKED` và thay routing cần quyền operator riêng, audit và approval.
- TLS/secret manager và rotation phải áp dụng cho PostgreSQL lẫn RabbitMQ; không để credential thật trong Git.

### 16.2. Không lưu payload nhạy cảm vô hạn

Outbox `payload` thường chứa dữ liệu nghiệp vụ. Với dữ liệu thanh toán, định danh cá nhân hoặc nội dung nhạy cảm:

- Giảm payload xuống mức đủ cho consumer, ưu tiên ID/ref và dữ liệu được phép chia sẻ.
- Mã hóa/giới hạn quyền truy cập dữ liệu ở trạng thái nghỉ theo chính sách tổ chức.
- Xác định retention riêng cho `SENT`, `BLOCKED`, DLQ và `processed_events`.
- Không xóa `PENDING`/`RETRY` chỉ vì bản ghi đã “quá cũ”; đó là những intent chưa hoàn tất.
- Xóa/archive `SENT` theo batch nhỏ và kế hoạch audit; giữ marker dedup đủ lâu để chịu replay/late duplicates trong phạm vi nghiệp vụ.
- Kiểm tra tăng trưởng bảng và hiệu quả indexes khi backlog lớn; autovacuum, disk space và backup.

### 16.3. Giới hạn của event ID dedup retention

Nếu consumer xóa `processed_events` quá sớm và sau đó replay cùng event ID từ archive/DLQ, nó có thể xử lý lại. Vì vậy **thời gian lưu marker phải tương thích với khoảng thời gian có thể tái xuất hiện event** hoặc business effect phải tự có unique/idempotency constraint lâu dài.

Một workflow phát hóa đơn hoặc trừ tiền đặc biệt cần idempotency key ở **external payment provider** nếu có side effect vượt ngoài DB transaction, không chỉ unique marker local.

## 17. Checklist triển khai production

- [ ] Mọi thay đổi orders và outbox event được ghi trong **cùng database transaction**, cùng DataSource/transaction manager.
- [ ] Mỗi sự kiện có `eventId` bất biến, `schemaVersion`, `aggregateVersion` và payload đủ/đúng định dạng.
- [ ] API nguồn có idempotency strategy khi HTTP client retry.
- [ ] Outbox claim là atomic và có `FOR UPDATE SKIP LOCKED` hoặc cơ chế tương đương cho nhiều workers.
- [ ] Worker có `claim_token`, lease và **fenced updates**; stale attempt không đè state mới.
- [ ] Claim transaction **commit trước publish**, không giữ row lock khi chờ broker.
- [ ] Relay không claim nhiều work hơn số publish slots có thể xử lý an toàn.
- [ ] RabbitTemplate dùng correlated confirms, mandatory returns, durable topology và persistent message theo policy.
- [ ] ACK + no return mới cho phép mark `SENT` theo hợp đồng routing đã kiểm thử.
- [ ] NO_ROUTE, NACK, channel error và timeout được phân loại riêng; UNKNOWN không coi là chắc chắn chưa gửi.
- [ ] Retry có backoff, jitter/giới hạn và trạng thái `BLOCKED` được giám sát.
- [ ] Có cơ chế broker reconnect, circuit breaker, watchdog/lease monitoring và phục hồi sau crash.
- [ ] Consumer `@RabbitListener` dùng DB idempotency marker **cùng transaction** với business effect.
- [ ] ACK consumer sau business commit; không có early ACK, không giả định exactly-once.
- [ ] Lỗi transient/permanent được phân loại, có retry hữu hạn và DLQ/quarantine hợp lệ.
- [ ] `processed_events` retention phù hợp với cửa sổ replay/duplicate có thể xảy ra.
- [ ] Có giải pháp per-aggregate ordering nếu nghiệp vụ yêu cầu.
- [ ] Integration tests chứng minh rollback, crash before/after publish, lost confirm, redelivery và concurrent claims.
- [ ] Dashboard có outbox oldest age, blocked count, confirm latency/outcomes, queue ready/unacked, Billing commit và DLQ.
- [ ] Có runbook replay/sửa BLOCKED an toàn, backup và audit lịch sử incident.

## 18. Những ngộ nhận cần tránh

| Ngộ nhận | Sự thật |
|---|---|
| “`@Transactional` quanh `save` + `convertAndSend` đã atomic DB/RabbitMQ.” | Transaction DB không tự bao gồm broker. |
| “Publisher confirm chứng minh Billing đã tạo invoice.” | Chỉ là tín hiệu broker đối với publisher. |
| “Outbox bảo đảm mỗi event được publish đúng một lần.” | Relay có thể retry sau ACK/DB update gap, tạo duplicate. |
| “Dùng event ID mới khi retry để tránh trùng request.” | Làm consumer mất khả năng dedup cùng event nghiệp vụ. |
| “Đánh dấu `SENT` khi `RabbitTemplate.send` không ném exception.” | Send có thể trả về trước confirm; cần phân loại confirm và return. |
| “Confirm timeout chứng minh broker chưa nhận.” | UNKNOWN, broker có thể đã lưu event. |
| “Claim row rồi giữ DB transaction suốt lúc chờ broker là an toàn nhất.” | Giữ lock lâu, tăng DB contention và rủi ro pool exhaustion. |
| “`SKIP LOCKED` bảo đảm event không bao giờ gửi trùng.” | Chỉ tránh claim đồng thời; lease expiry/crash vẫn có thể tạo duplicate. |
| “Lease hết hạn nghĩa worker cũ chắc chắn đã ngừng.” | Worker có thể treo rồi tỉnh lại; dùng fencing token. |
| “Outbox `SENT` có nghĩa workflow hoàn tất.” | Consumer có thể chưa xử lý hoặc đang ở DLQ. |
| “DB Billing có unique eventId thì mọi external API tự idempotent.” | External side effects cần idempotency riêng. |
| “Thêm retry vô hạn sẽ tự giải quyết mọi lỗi.” | Có thể là poison/schema/config vĩnh viễn, gây retry storm. |
| “Mọi message trong RabbitMQ đều đến đúng queue nếu publisher ACK.” | Mandatory return và alternate exchange cần xem xét. |
| “Queue ready = 0 chứng minh tất cả invoice đã commit.” | Có thể đã deliver, DLQ, expire hoặc drop. |
| “CDC tự động cho exactly-once end-to-end.” | Recovery/offset có thể tạo duplicate; consumer vẫn phải idempotent. |
| “Khi hết lỗi chỉ cần xóa `processed_events` rồi replay.” | Có thể tạo side effect trùng trên dữ liệu đã commit. |

## 19. Câu hỏi tự kiểm tra

1. Vì sao một `@Transactional` bình thường không bảo đảm order insert và RabbitMQ publish atomic?
2. Hai records nào phải commit trong cùng DB transaction để triển khai transactional outbox?
3. `eventId` khác `CorrelationData.id` và `claimToken` thế nào?
4. Khi broker đã nhận event nhưng relay chưa mark `SENT` thì điều gì có thể xảy ra sau crash?
5. `FOR UPDATE SKIP LOCKED` giải quyết vấn đề gì trong nhiều relay replicas?
6. Vì sao không giữ transaction claim mở suốt thời gian chờ broker confirm?
7. Tại sao phải có lease, và lease không thể thay thế idempotency ở điểm nào?
8. Khi worker cũ update một row đã bị worker mới reclaim, điều kiện SQL nào ngăn ghi đè?
9. Confirm ACK nhưng có mandatory return có được đánh dấu `SENT` không?
10. Broker confirm timeout nên được ghi thành NACK, SUCCESS hay UNKNOWN?
11. Vì sao phải giữ business `eventId` ổn định trong mọi lần gửi lại?
12. Khi Billing đã commit invoice nhưng ACK message bị mất, consumer nên làm gì lúc redelivery?
13. Hai statements nào phải cùng transaction trong Billing để marker không ngăn nghiệp vụ chưa hoàn tất?
14. `orders` và `processed_events` có bắt buộc dùng chung database khi triển khai microservices không?
15. Một event có aggregateVersion 3 đến trước version 2: dedup bằng eventId có phát hiện được không?
16. `BLOCKED` và DLQ khác nhau ở tầng nào của workflow?
17. Outbox polling vs CDC có khác nhau thế nào về vận hành và giao nhận?
18. Những metric nào phát hiện tắc trước broker, kể cả khi RabbitMQ queue depth thấp?
19. Vì sao `processed_events` retention ảnh hưởng tới replay sau nhiều tháng?
20. Muốn chứng minh outbox đúng dưới sự cố, cần ít nhất những fault injection nào?

**Đáp án gợi ý:** (1) DB và broker là hai tài nguyên commit riêng. (2) Order state và outbox intent. (3) Event business, attempt correlation, claim ownership. (4) Retry và duplicate publish. (5) Claim phân tán không chặn nhau. (6) Tránh giữ DB locks trong lúc network chậm. (7) Phục hồi row sau crash nhưng không ngăn duplicate publish. (8) `WHERE id=? AND claim_token=? AND state='IN_FLIGHT'`. (9) Không; message unroutable. (10) UNKNOWN. (11) Để consumer dedup. (12) Skip effect, return thành công để ACK. (13) Insert marker và insert invoice. (14) Không; mỗi service sở hữu DB của mình, dùng chung chỉ cho lab. (15) Không; cần version checkpoint/ordering policy. (16) BLOCKED ở producer relay, DLQ ở consumer/broker. (17) Poll queries/leases so với WAL connector/offsets. (18) Oldest outbox pending age, blocked, retry, confirm timeout. (19) Marker bị xóa sớm có thể khiến replay xử lý lần hai. (20) DB rollback, broker down, crash sau confirm, lost confirm, consumer ACK loss, concurrent reclaim.

## 20. Tổng kết

**Transactional outbox** là cách đáng tin cậy để đồng bộ **ý định gửi sự kiện** với thay đổi dữ liệu trong PostgreSQL mà không cần giả định RabbitMQ có thể commit nguyên tử cùng database. Business service ghi `orders` và `outbox_events` **trong cùng transaction**; relay lấy bản ghi đã commit, publish qua `RabbitTemplate`, chờ correlated confirms/mandatory returns rồi mới đánh dấu `SENT`. Những kết quả không chắc chắn phải được retry có kiểm soát với **event ID giữ nguyên**.

Ở downstream, `@RabbitListener` không được xem publisher ACK như bằng chứng nghiệp vụ thành công. Billing phải ghi marker `processed_events` cùng business effect trong **một DB transaction**, để một message được delivery nhiều lần vẫn chỉ tạo hóa đơn một lần. Lease, `SKIP LOCKED` và claim tokens giúp nhiều relays phối hợp, nhưng không loại bỏ mọi trường hợp duplicate; **consumer idempotency là lớp bảo vệ bắt buộc**.

Một bài thực hành được coi là đạt khi không chỉ demo happy path, mà còn chứng minh các khoảng lỗi: **rollback DB, broker down, crash trước/sau publish, confirm timeout, consumer ACK loss, DLQ và concurrent reclaim**. Việc quan sát phải đi từ outbox pending age đến RabbitMQ ready/unacked rồi đến business commit, để phát hiện lỗi ở đúng tầng.

### Tài liệu tham khảo

- [Spring AMQP — RabbitTemplate và Publisher Confirms/Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `CorrelationData`, publish ACK/NACK, returned message và các API gửi.
- [Spring AMQP — Annotation-driven Rabbit Listener](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): `@RabbitListener`, conversion, ACK và listener containers.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): DB transaction boundaries, proxy-based `@Transactional`.
- [PostgreSQL — SELECT locking clause](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE SKIP LOCKED` và tác động lock.
- [PostgreSQL — UPDATE / RETURNING](https://www.postgresql.org/docs/current/sql-update.html): atomic claim và fenced state updates.
- [RabbitMQ — Publisher Confirms and Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): phân biệt hai loại ACK và unknown outcome.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): reject/requeue, dead-letter routing và policies.
- [RabbitMQ — Reliability](https://www.rabbitmq.com/docs/reliability): confirms, retransmission, durability và failure handling.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): integration test database thật.
- [Testcontainers — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): integration test RabbitMQ thật.
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): CDC alternative cho relay polling, event routing và duplicates.



