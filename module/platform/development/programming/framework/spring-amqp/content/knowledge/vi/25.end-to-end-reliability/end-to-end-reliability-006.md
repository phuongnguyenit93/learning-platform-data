# Transactional outbox để đồng bộ thay đổi dữ liệu và ý định gửi

Trong ứng dụng tích hợp RabbitMQ bằng **Spring AMQP**, một thao tác nghiệp vụ thường phải làm hai việc: **ghi thay đổi vào cơ sở dữ liệu** và **gửi một message thông báo thay đổi** qua `RabbitTemplate`. Ví dụ, khi tạo đơn hàng, service lưu đơn hàng vào PostgreSQL rồi publish sự kiện `OrderPlaced` đến exchange RabbitMQ để dịch vụ thanh toán hoặc hóa đơn xử lý.

Hai thao tác sử dụng **hai tài nguyên độc lập**: database và RabbitMQ. Nếu chỉ đặt chúng cạnh nhau trong phương thức Java, sự cố giữa hai bước có thể làm dữ liệu và message không khớp. **Transactional outbox** giải quyết vấn đề bằng cách lưu cả **dữ liệu nghiệp vụ** lẫn **ý định gửi sự kiện** vào **cùng một transaction database**. Một tiến trình riêng, gọi là **message relay**, đọc các ý định đã commit rồi publish chúng đến broker.

Bài thuộc chương **Độ tin cậy đầu cuối** của module **SPRING_AMQP**. Ta kết hợp kiến thức về `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, publisher confirms/returns, ACK/NACK, retry, dead-letter và quan sát hệ thống để xây chuỗi xử lý bất đồng bộ có thể phục hồi sau lỗi.

## 1. Vấn đề dual write: vì sao ghi DB rồi gửi RabbitMQ không đủ?

Giả sử nghiệp vụ tạo đơn hàng gồm hai lệnh:

```java
orderRepository.save(order);                    // Ghi database
rabbitTemplate.convertAndSend(
        "orders.events", "orders.placed", event); // Gửi RabbitMQ
```

Ở thời điểm hệ thống bình thường, cả hai cùng thành công. Nhưng một ứng dụng đáng tin cậy phải giải quyết những trường hợp sau:

| Thứ tự | Sự cố | Hậu quả |
|---|---|---|
| Ghi DB rồi gửi broker | DB commit, ứng dụng chết trước khi publish | Đơn hàng tồn tại nhưng không có sự kiện gửi đi |
| Gửi broker rồi ghi DB | Broker nhận message, DB rollback | Consumer nhận một đơn hàng chưa từng được commit |
| Gửi broker trong `@Transactional` của DB | Broker nhận message nhưng DB transaction bị rollback sau đó | Broker không tự hủy message đã nhận |
| DB commit rồi publish qua callback `AFTER_COMMIT` | Process crash ở đoạn callback hoặc RabbitMQ tạm mất kết nối | Callback có thể không bao giờ gửi được message |
| Publish thành công nhưng chưa nhận confirm | Kết nối bị cắt trước khi confirm tới ứng dụng | Ứng dụng không biết broker đã nhận hay chưa |

Gọi `@Transactional` trên service **không tự tạo giao dịch nguyên tử giữa JDBC và RabbitMQ**. Kể cả dùng `channelTransacted=true` và cơ chế đồng bộ AMQP transaction với DB của Spring, vẫn có khoảng hở khi một tài nguyên commit thành công còn tài nguyên kia lỗi; đó không phải cam kết distributed XA/2PC.

Cũng không nên chỉ dựa vào `@TransactionalEventListener(phase = AFTER_COMMIT)` để đảm bảo gửi: callback có thể chạy sau commit, nhưng sự kiện chưa được ghi vào một kho bền vững để tiến trình khác tiếp tục khi process bị dừng.

**Yêu cầu thực tế:** Nếu giao dịch tạo đơn hàng **đã commit**, hệ thống phải giữ được ý định phát sự kiện để tiếp tục gửi về sau, kể cả khi RabbitMQ hoặc ứng dụng tạm thời lỗi. Nếu giao dịch **rollback**, ý định gửi tương ứng cũng phải rollback.

## 2. Cách hoạt động của transactional outbox

### 2.1. Hai giai đoạn với một ranh giới nguyên tử

```text
               REQUEST: tạo đơn hàng
                        |
                        v
                OrderService.place(...)
                        |
               BEGIN DB TRANSACTION
                        |
              +---------+-----------+
              |                     |
              v                     v
       INSERT/UPDATE orders    INSERT outbox_events
              |                     |
              +----------+----------+
                         |
                    COMMIT DB
                         |
         +---------------+------------------+
         |                                  |
         v                                  v
  Đơn hàng được lưu                Ý định gửi được lưu bền
                                            |
                              [message relay / polling / CDC]
                                            |
                                   RabbitTemplate.publish
                                            |
                                     RabbitMQ exchange
                                            |
                                         binding
                                            |
                                        queue đích
                                            |
                                     @RabbitListener
```

**Giai đoạn A — transaction nghiệp vụ:** Một transaction trên **cùng database** ghi thay đổi nghiệp vụ và một hoặc nhiều dòng outbox. Khi transaction commit, cả hai cùng hiện diện. Khi rollback, cả hai cùng không xuất hiện.

**Giai đoạn B — chuyển message:** Relay chỉ đọc những outbox row đã commit, publish bằng `RabbitTemplate` và sử dụng publisher confirm/return để đánh giá lần gửi. Nếu không chắc chắn đã gửi, relay giữ/retry **cùng event ID**.

Điểm khác biệt so với “DB + RabbitMQ transaction chung” là **không có nhu cầu commit đồng thời hai tài nguyên**. Ranh giới nguyên tử duy nhất là transaction database, còn publish vận hành theo cơ chế **at least once** khi relay, broker và consumer được cấu hình phù hợp.

### 2.2. Outbox lưu ý định gửi, không lưu trạng thái “đã xử lý xong”

Một dòng outbox mô tả **điều đã xảy ra trong domain** và **đích cần publish**, ví dụ:

```json
{
  "eventId": "edcc4b0f-6c43-4301-9357-6b795751ea29",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "aggregateId": "4831a64d-74b8-4eeb-b7c1-11f883535fcf",
  "aggregateVersion": 1,
  "occurredAt": "2026-01-12T08:30:00Z",
  "data": {
    "orderId": "4831a64d-74b8-4eeb-b7c1-11f883535fcf",
    "amountCents": 250000
  }
}
```

Các trường có vai trò khác nhau:

- `eventId`: định danh **không đổi** của sự kiện, dùng để deduplicate ở consumer và tương quan với publisher confirm.
- `aggregateId` và `aggregateVersion`: định danh và phiên bản dữ liệu nghiệp vụ, hỗ trợ kiểm tra thứ tự khi có nhiều sự kiện cùng một aggregate.
- `eventType` và `schemaVersion`: hợp đồng cho bên nhận; cần versioning khi payload tiến hóa.
- `exchangeName` và `routingKey` (trong outbox row): quyết định RabbitMQ exchange/routing key dùng khi relay publish.
- `status`, `attempts`, `availableAt`: trạng thái vận hành của **relay**, không phải trạng thái xử lý thành công của `@RabbitListener` phía downstream.

**Không đổi event ID mỗi lần retry.** Nếu tạo event ID mới sau một lần publish không chắc chắn, phía nhận sẽ không thể nhận diện hai message là cùng một sự kiện.

### 2.3. Những bảo đảm và giới hạn

| Thuộc tính | Outbox cung cấp gì? | Điều kiện/giới hạn |
|---|---|---|
| Atomicity giữa thay đổi DB và ý định gửi | **Có** | Cả hai ghi trong **cùng một local DB transaction** |
| Có thể tiếp tục publish sau process crash | **Có thể** | Outbox row còn bền, relay được chạy lại và có cảnh báo khi tắc |
| Broker chỉ nhận một bản duy nhất | **Không** | Lỗi giữa publish và đánh dấu `SENT` có thể tạo duplicate |
| Consumer xử lý nghiệp vụ chính xác một lần | **Không tự động** | Phải có idempotency/deduplication tại consumer |
| Strict ordering toàn hệ thống | **Không tự động** | Polling song song, retry và multiple consumers có thể làm đảo thứ tự |
| Publish thành công nghĩa là consumer đã xử lý | **Không** | Publisher confirm chỉ liên quan đến tiếp nhận phía broker |
| Không mất sự kiện mãi mãi | **Chỉ khi được vận hành đúng** | Cần retry, durability, quan sát, cảnh báo và xử lý lỗi vĩnh viễn |

Đây là kiến trúc **eventual consistency**: dữ liệu nguồn đã commit, còn downstream có thể nhìn thấy sự kiện muộn hơn. Hệ thống cần chấp nhận độ trễ này trong hợp đồng nghiệp vụ.

## 3. Thiết kế database: bảng domain và bảng outbox

Ví dụ dùng **PostgreSQL**; các lệnh SQL bên dưới phụ thuộc PostgreSQL (kiểu `jsonb`, `timestamptz`, `FOR UPDATE SKIP LOCKED`, `RETURNING`). Với MySQL hoặc DB khác cần chuyển đổi cú pháp và kiểm tra semantics khóa.

### 3.1. DDL minh họa

```sql
CREATE TABLE orders (
    id           uuid PRIMARY KEY,
    amount_cents bigint NOT NULL CHECK (amount_cents > 0),
    state        varchar(30) NOT NULL,
    version      bigint NOT NULL DEFAULT 1,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
    id                uuid PRIMARY KEY,
    aggregate_type    varchar(100) NOT NULL,
    aggregate_id      uuid NOT NULL,
    aggregate_version bigint NOT NULL,
    event_type        varchar(150) NOT NULL,
    schema_version    integer NOT NULL,
    exchange_name     varchar(255) NOT NULL,
    routing_key       varchar(255) NOT NULL,
    payload           jsonb NOT NULL,

    status            varchar(20) NOT NULL DEFAULT 'NEW',
    attempts          integer NOT NULL DEFAULT 0,
    available_at      timestamptz NOT NULL DEFAULT now(),
    locked_by         varchar(120),
    leased_until      timestamptz,
    published_at      timestamptz,
    last_error        text,
    created_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT outbox_status_check CHECK (
      status IN ('NEW', 'IN_FLIGHT', 'RETRY', 'SENT', 'FAILED')
    )
);

CREATE INDEX idx_outbox_pending
    ON outbox_events (available_at, created_at, id)
    WHERE status IN ('NEW', 'RETRY');

CREATE INDEX idx_outbox_expired_lease
    ON outbox_events (leased_until, id)
    WHERE status = 'IN_FLIGHT';
```

**Tại sao dùng bảng outbox bền vững?** Sau DB commit, việc ứng dụng đột ngột dừng không xóa được ý định gửi. Relay khác có thể tiếp tục từ bảng này. Ngược lại, một event chỉ được lưu vào hàng đợi trong bộ nhớ hoặc `@Async` task sẽ có nguy cơ mất khi process crash.

**Vì sao phải lưu payload ở thời điểm giao dịch?** Sự kiện mô tả trạng thái liên quan đến transaction đã commit. Nếu relay chỉ lưu order ID rồi đọc lại database sau nhiều phút, thông tin đơn hàng có thể đã thay đổi; payload phát đi không còn đại diện cho sự kiện ban đầu. Tối thiểu phải lưu version và cơ chế tái tạo snapshot nhất quán.

### 3.2. Vòng đời của outbox row

```text
                   tạo trong DB transaction
                              |
                              v
                            NEW
                              |
                relay claim + tạo lease
                              |
                              v
                          IN_FLIGHT
                         /         \
            confirm + routing OK   lỗi/timeout/không chắc chắn
                    |                     |
                    v                     v
                   SENT                 RETRY
                                          |
                               hết backoff/availableAt
                                          |
                                          +--> IN_FLIGHT
                                          |
                                 vượt ngưỡng retry
                                          v
                                        FAILED
```

- `NEW`: dữ liệu domain và ý định gửi đã commit.
- `IN_FLIGHT`: một relay instance đang sở hữu một **lease hữu hạn** để publish.
- `SENT`: broker đã confirm và không có returned message theo policy kiểm tra routing; **không** đồng nghĩa consumer đã xử lý xong.
- `RETRY`: cần thử lại sau backoff.
- `FAILED`: vượt ngưỡng/chờ can thiệp; giữ bản ghi và cảnh báo, không âm thầm xóa.

Nếu relay chết trong `IN_FLIGHT`, một instance khác phải có khả năng **reclaim lease đã hết hạn**. Lease chỉ hạn chế việc nhiều worker cùng publish trong điều kiện bình thường; nó không thể loại bỏ hoàn toàn duplicate khi pause dài hoặc mất kết nối.

## 4. Ghi thay đổi domain và outbox trong cùng transaction Spring

### 4.1. Code service dùng transaction của PostgreSQL

Ví dụ dưới đây dùng `JdbcTemplate` cho cả bảng `orders` và `outbox_events`, cùng `DataSource`, cùng transaction manager. Java 17+ cho phép dùng `record` và text block. Phần payload dùng JSON để không phụ thuộc Java serialization ở consumer.

```java
public record OrderPlaced(
        UUID eventId,
        String eventType,
        int schemaVersion,
        UUID orderId,
        long amountCents,
        Instant occurredAt) {
}
```

```java
@Service
public class OrderService {

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public OrderService(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Transactional(transactionManager = "transactionManager")
    public UUID placeOrder(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }

        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();
        OrderPlaced event = new OrderPlaced(
                eventId,
                "OrderPlaced",
                1,
                orderId,
                amountCents,
                Instant.now());

        String json = serialize(event);

        jdbc.update(
                "INSERT INTO orders (id, amount_cents, state) "
                        + "VALUES (?, ?, 'PLACED')",
                orderId,
                amountCents);

        jdbc.update("""
                INSERT INTO outbox_events (
                    id, aggregate_type, aggregate_id,
                    aggregate_version, event_type, schema_version,
                    exchange_name, routing_key, payload
                )
                VALUES (?, 'Order', ?, 1, 'OrderPlaced', 1,
                        'orders.events', 'orders.placed',
                        CAST(? AS jsonb))
                """,
                eventId,
                orderId,
                json);

        return orderId;
    }

    private String serialize(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Không tạo được payload", ex);
        }
    }
}
```

Các import chính: `java.util.UUID`, `java.time.Instant`, `com.fasterxml.jackson.databind.ObjectMapper`, `com.fasterxml.jackson.core.JsonProcessingException`, `org.springframework.jdbc.core.JdbcTemplate`, `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`.

**Yêu cầu không thể bỏ:** Lệnh `INSERT orders` và `INSERT outbox_events` phải dùng **cùng DataSource và cùng transaction DB**. Nếu outbox repository dùng datasource/transaction khác, hoặc thực thi trong một thread mới qua `@Async`, bạn đã phá vỡ điều kiện atomicity của mô hình.

`@Transactional` qua Spring proxy: hãy gọi `placeOrder` từ một Spring bean khác, không gọi qua `this.placeOrder()` trong chính class khi kỳ vọng transaction advice. Với Spring Boot có nhiều transaction manager, chỉ rõ manager thật sự điều khiển DB nguồn.

### 4.2. Kết quả khi thành công và lỗi

| Điểm dừng | Bảng `orders` | Bảng `outbox_events` | Broker |
|---|---|---|---|
| Code ném exception trước commit | Rollback | Rollback | Chưa publish |
| Commit DB thành công | Có đơn hàng | Có `NEW` | Có thể chưa có message |
| DB commit xong, RabbitMQ tạm down | Có đơn hàng | `NEW`/`RETRY` được giữ lại | Chưa nhận; relay thử lại |
| Broker nhận nhưng relay chết trước `SENT` | Có đơn hàng | Có thể vẫn `IN_FLIGHT` | Đã có message; lần sau có thể gửi trùng |
| Gửi xong, row được đánh dấu `SENT` | Có đơn hàng | `SENT` | Broker đã xác nhận publish/routing theo policy |

Bước gửi **không nằm trong method `placeOrder`**. Điều này giữ transaction database ngắn và loại bỏ phụ thuộc trực tiếp của thao tác ghi đơn hàng vào tình trạng broker ở đúng thời điểm commit. Tuy nhiên, doanh nghiệp phải thiết kế SLA về thời gian trễ gửi và cách xử lý outbox tồn đọng.

## 5. Định tuyến RabbitMQ cho sự kiện trong outbox

Relay gửi tới exchange `orders.events` với routing key `orders.placed`. Service nhận có queue `billing.order-placed` và binding tương ứng:

```java
@Configuration
public class OrderEventTopology {

    @Bean
    Declarables orderEventsDeclarables() {
        DirectExchange orders =
                new DirectExchange("orders.events", true, false);
        Queue billing = QueueBuilder
                .durable("billing.order-placed")
                .build();

        return new Declarables(
                orders,
                billing,
                BindingBuilder.bind(billing)
                        .to(orders)
                        .with("orders.placed"));
    }
}
```

Các class thuộc `org.springframework.amqp.core` và `org.springframework.context.annotation`. Trong hệ thống thật, topology có thể được quản lý bằng RabbitMQ policies, IaC hoặc các dịch vụ sở hữu queue; cần thống nhất quyền khai báo, tên exchange, loại exchange và binding.

**Ba lớp cần phân biệt:**

1. **Exchange tồn tại**: publish đến tên exchange sai có thể làm channel bị broker đóng.
2. **Có binding đến queue phù hợp**: exchange nhận message nhưng không có queue đích vẫn có thể xảy ra.
3. **Queue/message bền vững**: durable queue và persistent message là điều kiện quan trọng để giảm mất message khi broker restart; còn phụ thuộc loại queue và cấu hình cluster.

Không nên xem `convertAndSend` trả về bình thường là bằng chứng đã đến queue đích.

## 6. Message relay: claim, publish, xác nhận và hoàn tất

Có hai kiểu relay phổ biến:

- **Polling publisher:** service định kỳ query bảng outbox, claim các row mới, publish RabbitMQ. Dễ triển khai với Spring `@Scheduled` nhưng cần kiểm soát cạnh tranh và tải truy vấn.
- **Transaction-log tailing / CDC:** công cụ như Debezium đọc log thay đổi DB và phát event ra hệ thống trung gian. Phù hợp hệ thống lớn nhưng phải vận hành connector, offsets và downstream pipeline. CDC vẫn có thể phát trùng khi restart.

Phần tiếp theo minh họa **polling publisher** vì trực quan và có thể xây trực tiếp với Spring AMQP.

### 6.1. Claim nhiều row mà không giữ DB transaction lúc chờ broker

Nếu có hai relay instances, chúng không nên cùng lấy toàn bộ row `NEW` rồi đồng thời publish. PostgreSQL hỗ trợ `FOR UPDATE SKIP LOCKED` để **claim theo batch** trong một câu lệnh ngắn:

```sql
WITH candidates AS (
    SELECT id
    FROM outbox_events
    WHERE
        (status IN ('NEW', 'RETRY') AND available_at <= now())
        OR (status = 'IN_FLIGHT' AND leased_until < now())
    ORDER BY created_at, id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_events o
SET status = 'IN_FLIGHT',
    locked_by = :worker_id,
    leased_until = now() + interval '60 seconds',
    attempts = o.attempts + 1
FROM candidates c
WHERE o.id = c.id
RETURNING o.*;
```

Đây là **PostgreSQL SQL có named parameters** (ví dụ dùng `NamedParameterJdbcTemplate`), không phải SQL chạy trực tiếp nếu chưa thay `:batch_size` và `:worker_id`. Câu lệnh được commit **trước khi publish tới RabbitMQ**. Relay chỉ giữ các row trả về kèm `attempts` mới, `locked_by` và hạn lease.

Tại sao không bắt đầu DB transaction, khóa hàng loạt row rồi giữ transaction đến khi nhận publisher confirm? Vì một RabbitMQ outage có thể kéo dài thời gian chờ, khiến DB giữ connection/row locks, ảnh hưởng các transaction nghiệp vụ. Cơ chế lease tách việc claim DB khỏi tác vụ network chậm.

**Lease hết hạn** cho phép khôi phục row khi worker mất liên lạc. Thời gian lease nên lớn hơn thời gian xử lý một batch theo chiến lược worker, hoặc cần cơ chế gia hạn lease. Nếu một worker chậm hơn lease, hai worker có thể publish cùng event; duplicate vẫn phải được xử lý tại consumer.

### 6.2. Cấu hình publisher confirms và returns trong Spring Boot

```yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
```

- **Publisher confirm:** broker gửi ACK/NACK cho publish; dùng `CorrelationData` để đối chiếu với outbox event ID.
- **Publisher return với `mandatory=true`:** broker trả message **không định tuyến được đến queue nào**. Publisher ACK vẫn có thể xảy ra với message không có route, vì ACK của confirm không đồng nghĩa routing đã thành công.
- Nếu exchange không tồn tại, broker có thể đóng channel; cần xử lý lỗi này và alert topology thay vì retry dồn dập không giới hạn.
- `publisher-confirm-type: correlated` và `publisher-returns: true` cần được cấu hình trên connection factory thực sự dùng bởi `RabbitTemplate`. Không tự ghép AMQP transactions với confirm mode trên cùng channel.

Để message có độ bền phù hợp, publish persistent message tới durable queue (và cấu hình loại queue phù hợp). Publisher confirm không thay thế chính sách durability và không thông báo rằng một consumer đã hoàn thành nghiệp vụ.

### 6.3. Publisher dùng cùng eventId cho mỗi lần thử

Ví dụ sau dùng **Spring AMQP 3.x/4.x** với `CorrelationData.getFuture()` và `getReturn()`. Payload outbox là chuỗi JSON đã lưu ở DB:

```java
public record OutboxEvent(
        UUID id,
        String eventType,
        int schemaVersion,
        String exchangeName,
        String routingKey,
        String payloadJson,
        int attempts) {
}
```

```java
@Service
public class OutboxRabbitPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OutboxRabbitPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishAndAwait(OutboxEvent event) throws Exception {
        String eventId = event.id().toString();
        CorrelationData correlation = new CorrelationData(eventId);

        rabbitTemplate.convertAndSend(
                event.exchangeName(),
                event.routingKey(),
                event.payloadJson(),
                message -> {
                    MessageProperties p = message.getMessageProperties();
                    p.setMessageId(eventId);
                    p.setContentType(MessageProperties.CONTENT_TYPE_JSON);
                    p.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    p.setHeader("eventType", event.eventType());
                    p.setHeader("schemaVersion", event.schemaVersion());
                    return message;
                },
                correlation);

        CorrelationData.Confirm confirm =
                correlation.getFuture().get(10, TimeUnit.SECONDS);

        if (!confirm.isAck()) {
            throw new IllegalStateException(
                    "Broker NACK: " + confirm.getReason());
        }

        if (correlation.getReturn() != null) {
            throw new IllegalStateException(
                    "Unroutable: " + correlation.getReturn().getReplyText());
        }
    }
}
```

Các import chính: `java.util.UUID`, `java.util.concurrent.TimeUnit`, `org.springframework.amqp.core.MessageProperties`, `org.springframework.amqp.core.MessageDeliveryMode`, `org.springframework.amqp.rabbit.connection.CorrelationData`, `org.springframework.amqp.rabbit.core.RabbitTemplate`, `org.springframework.stereotype.Service`.

Trong điều kiện publisher confirms + returns hoạt động đúng, Spring AMQP gắn returned message vào `CorrelationData` **trước khi** confirm future hoàn thành với ACK. Với một số phiên bản API cũ hơn, tên accessor cho returned message khác; đối chiếu với version của ứng dụng trước khi sao chép. Hãy giữ callback returns ngắn và không block vì thứ tự return/confirm có giới hạn thời gian trong Spring AMQP.

`publishAndAwait` chỉ kết thúc thành công khi **nhận confirm ACK và không có return**. Nó không bao hàm việc consumer đã xử lý thành công. Nếu timeout, NACK, exception hoặc không có route, **không đánh dấu `SENT`**.

**Timeout không chứng minh broker chưa nhận message.** Lần retry phải dùng lại `eventId`. Điều này cố ý chấp nhận khả năng publish trùng để tránh đánh mất ý định gửi.

### 6.4. Đánh dấu SENT hoặc RETRY bằng điều kiện sở hữu lease

Sau khi nhận confirm, relay ghi lại trạng thái vào **một DB transaction ngắn khác**:

```sql
UPDATE outbox_events
SET status = 'SENT',
    published_at = now(),
    locked_by = NULL,
    leased_until = NULL,
    last_error = NULL
WHERE id = :event_id
  AND status = 'IN_FLIGHT'
  AND locked_by = :worker_id
  AND attempts = :attempt;
```

Nếu kết quả update bằng **0 row**, worker đã mất quyền sở hữu hoặc row đã được claim lại; không được ghi đè trạng thái của worker mới. `attempts` đóng vai trò như một token phiên bản của lần claim.

Trong trường hợp publish lỗi, thay vì xóa row, relay chuyển sang `RETRY`:

```sql
UPDATE outbox_events
SET status = 'RETRY',
    available_at = :next_attempt_at,
    locked_by = NULL,
    leased_until = NULL,
    last_error = :sanitized_error
WHERE id = :event_id
  AND status = 'IN_FLIGHT'
  AND locked_by = :worker_id
  AND attempts = :attempt;
```

`next_attempt_at` được tính bằng backoff có giới hạn và jitter, ví dụ 1 giây, 2 giây, 4 giây, tối đa 5 phút; giới hạn số lần thử và báo động `FAILED` nếu lỗi kéo dài. Không ghi payload nhạy cảm hoặc toàn bộ stack trace vào `last_error`.

### 6.5. Khung relay cho Spring Scheduling

```java
@Component
public class OutboxRelay {

    private final OutboxClaimRepository claims;
    private final OutboxStateRepository states;
    private final OutboxRabbitPublisher publisher;
    private final String workerId = UUID.randomUUID().toString();

    public OutboxRelay(
            OutboxClaimRepository claims,
            OutboxStateRepository states,
            OutboxRabbitPublisher publisher) {
        this.claims = claims;
        this.states = states;
        this.publisher = publisher;
    }

    @Scheduled(fixedDelay = 1000)
    public void publishPending() {
        // claimBatch thực thi SQL ở mục 6.1 rồi commit ngắn.
        for (OutboxEvent event : claims.claimBatch(workerId, 20)) {
            try {
                publisher.publishAndAwait(event);
                states.markSent(
                        event.id(), workerId, event.attempts());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                states.scheduleRetry(
                        event.id(), workerId, event.attempts(), ex);
                return;
            } catch (Exception ex) {
                states.scheduleRetry(
                        event.id(), workerId, event.attempts(), ex);
            }
        }
    }
}
```

Đây là **khung phối hợp**: `OutboxClaimRepository` và `OutboxStateRepository` là các lớp ứng dụng cần triển khai bằng `NamedParameterJdbcTemplate`, dùng SQL ở mục 6.1 và 6.4, cùng chính sách backoff/`FAILED` đã chọn. Cần bật `@EnableScheduling` ở cấu hình Spring. Để code vận hành đầy đủ, bổ sung xử lý lỗi khi **cập nhật trạng thái DB thất bại**, theo dõi kết quả affected rows và báo động khi relay không xử lý được batch.

**Quy tắc triển khai:** Không giữ transaction DB xuyên suốt `publishAndAwait`. `claimBatch` commit trước khi publish; `markSent`/`scheduleRetry` thực hiện cập nhật DB riêng. Khi lập lịch song song, phải giới hạn mức độ đồng thời, xử lý expired leases và tránh backlog tăng vô hạn.

## 7. Tại sao outbox vẫn có duplicate?

Xét một lần relay gửi `E-101`:

```text
Relay                         RabbitMQ                      PostgreSQL
  |                              |                              |
  | --- publish E-101 ---------> |                              |
  | <--- publisher ACK --------- |                              |
  |                              |                              |
  X  process crash               |                              |
                                 |                outbox E-101 vẫn IN_FLIGHT
                                 |                              |
                   ... lease hết hạn ...                        |
  |                              |                              |
  | --- publish E-101 ---------> |  <--- relay thử lại -------- |
  | <--- publisher ACK --------- |                              |
  |                              |                              |
  | ---------------------------- mark SENT -------------------> |
```

Broker đã nhận **hai lần cùng một sự kiện**. Không có cách dùng local DB transaction + publisher confirm nào để nguyên tử hóa “broker đã nhận” với “DB đã ghi `SENT`” thành một bước duy nhất.

Do đó, mô hình chuẩn phải chấp nhận:

- **At-least-once publication/delivery:** retry những publish chưa chắc chắn, có thể gửi trùng.
- **Stable event ID:** cùng một sự kiện luôn có cùng ID trong mọi lần publish.
- **Idempotent consumer:** nhận sự kiện trùng không tạo tác dụng phụ nghiệp vụ lần thứ hai.
- **Hợp đồng ordering:** khi cần đúng thứ tự, phải xử lý riêng; outbox alone không tự giải quyết.

Nếu ai đó gọi transactional outbox là **exactly once messaging** mà không định nghĩa rõ ranh giới, đó là cách diễn đạt gây hiểu nhầm. Ta có thể đạt **tác dụng phụ đúng một lần trên một database** nhờ unique constraint và transaction tại consumer, nhưng không thể tự động bảo đảm mọi thao tác bên ngoài (email, HTTP, thanh toán) chỉ chạy một lần.

## 8. Idempotent consumer với @RabbitListener

Ví dụ consumer `billing.order-placed` phải lập bản ghi thanh toán/hóa đơn từ `OrderPlaced`. Khi broker redeliver hoặc relay publish lại, consumer chỉ được áp dụng tác dụng phụ vào DB một lần cho mỗi `eventId`.

### 8.1. Bảng ghi nhận sự kiện đã xử lý

```sql
CREATE TABLE processed_events (
    consumer_name varchar(100) NOT NULL,
    event_id      uuid NOT NULL,
    processed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE billing_records (
    order_id      uuid PRIMARY KEY,
    amount_cents  bigint NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
```

Bảng `processed_events` phải nằm trong **cùng transaction database** với thay đổi `billing_records` của consumer. Nếu chỉ ghi cache hoặc ghi dấu đã xử lý sau khi nghiệp vụ commit, consumer vẫn gặp khoảng hở và có thể áp dụng tác dụng phụ hai lần.

### 8.2. Code consumer và service transaction

```java
@Component
public class BillingListener {

    private final ObjectMapper mapper;
    private final BillingService billing;

    public BillingListener(ObjectMapper mapper, BillingService billing) {
        this.mapper = mapper;
        this.billing = billing;
    }

    @RabbitListener(queues = "billing.order-placed")
    public void onMessage(Message message) throws JsonProcessingException {
        OrderPlaced event = mapper.readValue(
                message.getBody(), OrderPlaced.class);
        billing.applyOnce(event);
    }
}

@Service
public class BillingService {

    private final JdbcTemplate jdbc;

    public BillingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(OrderPlaced event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_events (consumer_name, event_id)
            VALUES ('billing', ?)
            ON CONFLICT DO NOTHING
            """, event.eventId());

        if (inserted == 0) {
            return; // Duplicate: đã áp dụng ở lần trước.
        }

        jdbc.update("""
            INSERT INTO billing_records (order_id, amount_cents)
            VALUES (?, ?)
            """, event.orderId(), event.amountCents());
    }
}
```

Các import chính: `org.springframework.amqp.core.Message`, `org.springframework.amqp.rabbit.annotation.RabbitListener`, `com.fasterxml.jackson.databind.ObjectMapper`, `com.fasterxml.jackson.core.JsonProcessingException`, `org.springframework.jdbc.core.JdbcTemplate`, `org.springframework.transaction.annotation.Transactional`, `org.springframework.stereotype.Component`, `org.springframework.stereotype.Service`.

Với `AcknowledgeMode.AUTO`, listener chỉ trở về bình thường **sau khi** lời gọi qua Spring proxy tới `BillingService.applyOnce` đã commit DB. Khi DB ghi lỗi, exception được ném lên listener/container để áp dụng requeue/retry/DLQ phù hợp.

Nếu DB commit xong nhưng consumer ACK bị mất, broker có thể giao lại cùng message. Unique key `(consumer_name, event_id)` khiến lần xử lý sau không tạo thêm `billing_records`. Nếu DB transaction bị rollback, cả bản ghi `processed_events` và `billing_records` đều rollback, nên retry có thể thực hiện lại.

Cách này xử lý duplicate cho **tác dụng phụ trong cùng DB**. Với gọi API thanh toán, gửi email hoặc ghi hệ thống khác, cần thêm idempotency key đến downstream, outbox phía consumer hoặc workflow riêng. Ngoài ra, nếu hai loại event khác nhau dùng cùng order ID, consumer phải quyết định theo `eventType`/version thay vì chỉ dựa trên `orderId`.

### 8.3. Retry và dead-letter ở consumer

Lỗi chuyển đổi payload, lỗi nghiệp vụ không thể sửa và lỗi database tạm thời cần xử lý khác nhau:

| Lỗi | Hướng xử lý gợi ý |
|---|---|
| Database tạm mất kết nối | Retry có backoff/giới hạn; khi cần, delay queue hoặc DLQ |
| Payload schema không tương thích | Reject không requeue, chuyển DLQ và alert; sửa serializer/schema |
| Event ID đã xử lý | Trả thành công, ACK message; không lặp tác dụng phụ |
| Event đến sai thứ tự phiên bản | Theo dõi version, chờ/gom lại hoặc xử lý theo state machine |
| Consumer crash sau DB commit nhưng trước ACK | Cho phép redelivery; unique event ID giúp bỏ qua |

Trong RabbitMQ, DLX phải được cấu hình trên queue nguồn cùng binding phù hợp; chỉ NACK với `requeue=false` mà queue không có DLX không bảo đảm message xuất hiện ở DLQ.

**Outbox `SENT` chỉ biểu thị publish đã được xác nhận ở broker.** Nếu listener phía nhận lỗi và message nằm ở DLQ, hệ thống end-to-end vẫn chưa xử lý xong nghiệp vụ. Vì vậy phải theo dõi cả outbox và consumer/DLQ.

## 9. Ordering, scaling, CDC và những quyết định kiến trúc

### 9.1. Outbox không tự giữ strict ordering

Có thể xảy ra trình tự:

1. Đơn `O-9` có sự kiện `OrderPlaced` version 1 và `OrderPaid` version 2.
2. Relay A claim version 1, bị timeout và retry sau.
3. Relay B claim version 2, publish thành công ngay.
4. Consumer thấy version 2 **trước** version 1.

Ngay cả `ORDER BY created_at` trong một truy vấn polling cũng không đủ để đảm bảo strict order khi nhiều relay, nhiều channel, routing/broker redelivery hoặc nhiều consumers đang chạy đồng thời.

Nếu nghiệp vụ yêu cầu thứ tự theo aggregate, cần ít nhất:

- Gán `aggregateVersion` tăng đơn điệu trong cùng transaction cập nhật aggregate.
- Thiết kế **không cho publish version mới vượt version cũ chưa hoàn tất** đối với cùng aggregate (ví dụ khóa/partition theo aggregate), hoặc consumer buffer và từ chối phiên bản thiếu.
- Kiểm soát thứ tự khi có nhiều queue, nhiều consumers, prefetch/concurrency và retry; message đi qua DLQ rồi replay có thể đến muộn.
- Xác định hợp đồng: “mỗi aggregate” thường thực tế hơn “mọi sự kiện trên toàn hệ thống”.

Nếu toàn hệ thống không cần thứ tự nghiêm ngặt, ưu tiên idempotency và event version để tránh tăng độ phức tạp không cần thiết.

### 9.2. Chọn polling hay CDC

| Tiêu chí | Polling publisher | CDC / transaction log tailing |
|---|---|---|
| Nguồn dữ liệu | Query bảng `outbox_events` | Đọc DB commit log/binlog |
| Triển khai ban đầu | Dễ với Spring `@Scheduled` | Cần connector, pipeline và lưu offsets |
| Latency | Phụ thuộc chu kỳ poll và batch | Có thể thấp hơn khi pipeline hoạt động tốt |
| Áp lực DB | Truy vấn lặp, khóa/claim có thể tốn tài nguyên | Chủ yếu chi phí log/CDC và pipeline |
| Mở rộng nhiều relay | Cần lease/`SKIP LOCKED` | Cần quản lý partition/offset và relay |
| Duplicate | Vẫn có | Vẫn có, nhất là khi restart/replay |
| Khi nào chọn | Ứng dụng vừa và nhỏ, cần kiểm soát đơn giản | Hệ thống có CDC vận hành ổn định, throughput lớn |

CDC không thay thế nhu cầu tạo outbox row **trong cùng transaction** với domain. Nó chỉ thay cách đọc và chuyển tiếp ý định gửi sau commit.

### 9.3. Chọn payload và schema

Có hai kiểu thông điệp:

- **Event notification:** chỉ gửi `eventId`, `aggregateId`, version; consumer truy xuất thông tin nơi khác. Đơn giản nhưng phụ thuộc network/DB state bên ngoài.
- **Event carried state:** chứa snapshot các trường consumer thực sự cần tại thời điểm thay đổi. Ít phụ thuộc truy vấn ngược hơn nhưng cần versioning schema và quản lý dữ liệu nhạy cảm.

Với Spring AMQP, thường dùng JSON có `schemaVersion` rõ ràng, event ID trong payload và header AMQP `messageId`. Tránh phụ thuộc vào Java serialization giữa các service chạy độc lập.

**Không lưu bí mật, thông tin thẻ, token hoặc dữ liệu cá nhân dư thừa vào outbox**. Row sẽ nằm lâu hơn request và có thể được copy qua nhiều hệ thống quan sát/backup. Có chiến lược retention và xóa dữ liệu theo yêu cầu nghiệp vụ.

## 10. Quan sát và vận hành outbox đáng tin cậy

### 10.1. Các chỉ số tối thiểu

| Chỉ số | Ý nghĩa/cảnh báo |
|---|---|
| `outbox_pending_count` | Số row `NEW`/`RETRY` chưa gửi; tăng liên tục có thể do relay chậm hoặc broker lỗi |
| `outbox_oldest_pending_age_seconds` | Độ trễ từ commit DB đến lúc publish; phản ánh SLA gửi event |
| `outbox_in_flight_expired` | Số lease hết hạn; tăng có thể do worker chết/timeout quá ngắn |
| `outbox_publish_attempts` | Số lần thử; tăng đột biến báo lỗi kết nối, xác nhận hoặc routing |
| `outbox_confirm_nack_total` và `outbox_return_total` | Lỗi broker confirm và message không có route |
| `outbox_failed_count` | Row cần can thiệp thủ công; luôn alert nếu khác 0 ở nghiệp vụ quan trọng |
| `consumer_duplicate_total` | Event trùng; tín hiệu cần điều tra nếu tăng bất thường |
| `rabbitmq_queue_ready`, `rabbitmq_unacked`, `dlq_depth` | Message còn đợi, chưa ACK, bị chuyển tới DLQ |
| `event_end_to_end_latency` | Từ `occurredAt` đến lúc consumer commit tác dụng phụ |

Đính `eventId`, `aggregateId`, trace ID vào log và metrics phù hợp, nhưng tránh nhét event ID làm metric label có cardinality cao. Log event ID giúp truy một sự kiện qua **domain commit → outbox row → publish attempt → broker confirm → consumer → DB commit**.

### 10.2. Quy trình khôi phục khi xảy ra sự cố

- **RabbitMQ ngừng hoạt động:** DB vẫn nhận giao dịch nghiệp vụ nếu không quá tải; outbox `NEW`/`RETRY` tăng. Giới hạn backlog và tiếp tục retry với backoff sau khi broker hồi phục.
- **Relay bị restart:** claim lại các row `IN_FLIGHT` có lease hết hạn; giữ nguyên event ID để deduplicate.
- **Sai routing key hoặc thiếu binding:** publisher returns báo `NO_ROUTE` (với `mandatory`), kiểm tra topology trước khi reprocess.
- **Consumer gặp lỗi liên tục:** theo dõi DLQ và sửa nguyên nhân. Replay DLQ cần giữ ID, xác định hiệu ứng nghiệp vụ trước khi gửi lại.
- **Outbox tăng quá nhanh:** xem số lượng worker, kích thước batch, tốc độ DB, RabbitMQ, prefetch và throughput consumer. Dọn `SENT` sau thời gian lưu trữ theo chính sách; không xóa `NEW`/`RETRY`/`FAILED` để “giảm dung lượng”.
- **Cần reprocess row thất bại:** dùng công cụ vận hành đổi `FAILED` về `RETRY` có audit, giữ nguyên event ID và tránh chạy lại các sự kiện đã bị hủy về mặt nghiệp vụ.

Để relay hoạt động ổn định, cần thiết kế **backpressure**: khi broker chậm, không tăng vô hạn số publish outstanding hoặc giữ hàng nghìn DB connections. Có thể publish theo batch và xử lý confirms bất đồng bộ khi cần thông lượng cao hơn; ví dụ `getFuture().get` theo từng event ở đây được chọn để dễ quan sát semantics.

## 11. Bài thực hành end-to-end

Dùng PostgreSQL, RabbitMQ và hai Spring Boot services (Order và Billing) hoặc một ứng dụng demo với DB riêng cho từng bounded context. Hai DB của domain producer và consumer có thể khác nhau; **mỗi service phải đảm bảo transaction cục bộ của riêng nó**.

### Bước 1 — Tạo dữ liệu thành công

Gọi `OrderService.placeOrder(250000)`. Kiểm tra:

1. Bảng `orders` có đơn trạng thái `PLACED`.
2. Bảng `outbox_events` có row `NEW` với `eventId`, `aggregateId`, payload JSON.
3. Relay claim, publish, nhận ACK và không có return, chuyển row thành `SENT`.
4. Queue `billing.order-placed` nhận event; `@RabbitListener` gọi `BillingService.applyOnce`; bảng `billing_records` có đúng một bản ghi cho order.

### Bước 2 — Thử rollback transaction DB

Trong `placeOrder`, cố ý ném `IllegalStateException` **sau khi insert outbox nhưng trước khi method kết thúc**. Cả hàng `orders` và `outbox_events` phải không còn bản ghi của lần thử này, không có gì để relay publish.

### Bước 3 — Broker ngắt kết nối

Dừng RabbitMQ sau khi DB commit thành công, trước khi relay publish. Quan sát row `NEW` hoặc `RETRY` vẫn còn. Khởi động broker trở lại, xác nhận relay tự gửi sau backoff. Đo độ trễ event và số attempts.

### Bước 4 — Publisher ACK nhưng chưa cập nhật SENT

Giả lập lỗi ở `markSent` hoặc dừng relay ngay sau khi nhận confirm. Cho lease hết hạn rồi chạy relay lần nữa. RabbitMQ có thể nhận hai bản cùng `eventId`; consumer chỉ insert `processed_events` một lần và không tạo hai `billing_records`.

### Bước 5 — Unroutable message

Trong môi trường test, dùng một routing key không có binding. Với `mandatory=true` và publisher returns, relay phải phát hiện returned message, giữ row để retry/điều tra; **không** đánh dấu `SENT` chỉ vì publisher confirm ACK.

### Bước 6 — Lỗi consumer

Cho `BillingService.applyOnce` ném exception trước DB commit. Kiểm tra `processed_events` cũng rollback và message có thể retry theo cấu hình. Sau khi sửa lỗi, xử lý lại cùng `eventId` thành công. Nếu áp dụng retry có giới hạn, xác nhận message được chuyển DLQ khi hết số lần thử.

### Bước 7 — Kiểm tra thứ tự

Tạo hai sự kiện cùng `aggregateId` có `aggregateVersion` 1 và 2. Cố ý làm chậm gửi version 1. Quan sát cách ứng dụng hiện tại xử lý đảo thứ tự và xác định có cần chặn version 2 hay dùng buffer/reconciliation ở consumer.

**Tiêu chí đạt:** Khi DB rollback, không có event committed; khi DB đã commit nhưng broker down, ý định gửi còn lại để retry; khi publish bị lặp, hiệu ứng DB của consumer không lặp; khi routing lỗi hoặc consumer lỗi, hệ thống hiển thị được nguyên nhân và có đường khôi phục.

## 12. Những nhầm lẫn cần tránh

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “Có `@Transactional` là DB và RabbitMQ cùng commit.” | `@Transactional` chỉ quản lý các tài nguyên thuộc transaction manager đã chọn; outbox giải quyết nhu cầu atomicity bằng **một DB transaction**. |
| “Gửi ở `AFTER_COMMIT` thì không mất event.” | Callback vẫn có thể không chạy khi process crash; outbox row bền là nguồn để retry. |
| “`RabbitTemplate.convertAndSend` không ném exception nghĩa là vào queue.” | Cần publisher confirms và kiểm tra returns/mandatory nếu phải bảo đảm định tuyến. |
| “Confirm ACK nghĩa là consumer đã xử lý.” | Confirm phản ánh broker; xử lý ở consumer là giai đoạn khác với ACK/NACK riêng. |
| “Outbox bảo đảm exactly-once end-to-end.” | Relay có thể publish duplicate; consumer cần idempotency. |
| “Outbox `SENT` là có thể xóa ngay.” | Cần chính sách retention/audit và hiểu rằng downstream có thể chưa xử lý xong. |
| “`SKIP LOCKED` bảo đảm các sự kiện luôn theo thứ tự.” | Nó tránh tranh chấp row, không tự bảo đảm ordering khi nhiều workers và retry. |
| “Retry phải tạo event ID mới.” | Phải **giữ nguyên event ID** để consumer phát hiện duplicate. |
| “Chỉ cần durable queue.” | Phải xem cả persistent messages, confirm, routing, consumer ACK, DLQ và khả năng phục hồi của broker. |

## 13. Câu hỏi tự kiểm tra

1. Vì sao `save(order)` rồi `convertAndSend(event)` trong một method có thể gây mất sự kiện dù method gắn `@Transactional`?
2. Transactional outbox đưa **những thao tác nào** vào cùng transaction database?
3. Nếu DB commit thành công nhưng broker down một giờ, row outbox phải ở trạng thái nào và relay cần làm gì?
4. Khi broker gửi publisher ACK nhưng relay chết trước khi đánh dấu `SENT`, event có thể được gửi lại không? Làm sao tránh hiệu ứng nghiệp vụ trùng?
5. Tại sao publisher confirm ACK và `mandatory=true` vẫn phải kiểm tra publisher returns?
6. Vì sao unique key trong `processed_events` phải được commit cùng thay đổi ở `billing_records`?
7. Hai relay dùng `FOR UPDATE SKIP LOCKED` có bảo đảm version 1 luôn được consumer nhìn thấy trước version 2 không?
8. Khi outbox row `SENT` nhưng consumer đưa message vào DLQ, có thể xem toàn bộ nghiệp vụ hoàn tất không?

**Đáp án ngắn:** (1) Broker không thuộc DB transaction; (2) thay đổi domain và insert outbox row; (3) giữ `NEW`/`RETRY` để thử lại; (4) có, giữ event ID và idempotent consumer; (5) confirm không chứng minh có route; (6) tránh ghi dấu processed nhưng nghiệp vụ chưa commit hoặc ngược lại; (7) không; (8) không.

## 14. Tổng kết

**Transactional outbox đồng bộ thay đổi dữ liệu với ý định gửi** bằng cách ghi chúng **trong cùng một DB transaction**, rồi tách nhiệm vụ publish RabbitMQ sang relay có retry. Khi DB commit thì event intent tồn tại bền vững; khi DB rollback thì intent cũng biến mất. Với `RabbitTemplate`, publisher confirms và mandatory returns giúp relay quyết định khi nào có thể đánh dấu outbox `SENT`; broker nhận message không đồng nghĩa consumer đã xử lý.

Độ tin cậy **đầu cuối** còn cần idempotent `@RabbitListener`, ACK/NACK có chủ đích, retry/DLQ, quy ước ordering, giới hạn backlog và giám sát thời gian trễ. Kiến trúc này chấp nhận **at-least-once** và hướng đến **hiệu ứng nghiệp vụ đúng một lần trong phạm vi transaction được kiểm soát**, thay vì hứa hẹn exactly-once toàn hệ thống.

### Tài liệu tham khảo

- [Microservices.io — Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox): dual write, outbox và message relay, duplicate/idempotent consumer.
- [Spring AMQP — RabbitTemplate Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `CorrelationData`, `getFuture()`, `getReturn()`, mandatory và return.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ranh giới xác nhận của publisher/consumer, unroutable và confirm ACK.
- [RabbitMQ — Reliability Guide](https://www.rabbitmq.com/docs/reliability): publish retry, data safety và idempotency khi gặp network failure.
- [AWS Prescriptive Guidance — Transactional Outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html): ứng dụng outbox và các lưu ý về duplicate, ordering.

