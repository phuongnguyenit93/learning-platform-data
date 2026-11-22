# Không phụ thuộc vào ChainedKafkaTransactionManager

Trong một service Spring Kafka, yêu cầu “lưu database và phát Kafka event trong cùng một nghiệp vụ” rất phổ biến. Ví dụ, API tạo đơn hàng ghi một dòng vào bảng `orders` rồi publish `OrderCreated` để các service khác xử lý. Vấn đề là **PostgreSQL và Kafka có hai cơ chế commit độc lập**. Nếu process crash đúng lúc giữa hai thao tác, một bên có thể đã ghi dữ liệu trong khi bên còn lại chưa hoàn tất.

`ChainedKafkaTransactionManager` từng được sử dụng để phối hợp nhiều local transaction manager theo chuỗi. Tuy nhiên, nó **không cung cấp XA/two-phase commit** cho Kafka và database. Lớp này đã bị **deprecated từ Spring Kafka 2.7**. Vì vậy, ứng dụng mới nên tránh phụ thuộc vào nó, và ứng dụng cũ cần chủ động chọn giải pháp thay thế đúng yêu cầu: **Spring transaction synchronization** nếu chấp nhận commit theo thứ tự và có khả năng bù lỗi, hoặc **transactional outbox/inbox** nếu cần độ tin cậy cao trước crash và mất kết nối.

Đây là vấn đề kiến trúc, không chỉ là việc thay import Java. Mục tiêu của bài học là hiểu rõ ranh giới giao dịch, các điểm lỗi có thể xảy ra, cách dùng Spring Kafka không cần chained manager, và mô hình vận hành phù hợp với từng mức độ quan trọng của dữ liệu.

## 1. Vì sao ghi database và Kafka là bài toán dual-write?

Luồng nghiệp vụ tưởng như đơn giản:

```text
POST /orders
     |
     v
OrderService.create()
     |
     +----> PostgreSQL: INSERT INTO orders (...)
     |
     +----> Kafka: publish OrderCreated
     |
     v
HTTP 201 Created
```

Database transaction quản lý tính nguyên tử của các lệnh SQL trong phạm vi database. Kafka transaction quản lý việc commit các record do producer transactional gửi và, khi phù hợp, offset của Kafka consumer. Hai resource có log, coordinator, network và thời điểm commit riêng.

| Resource | Transaction bảo vệ gì? | Thành phần Spring điển hình |
|---|---|---|
| PostgreSQL | Thay đổi các bảng trong cùng database transaction. | `DataSourceTransactionManager` / `JdbcTransactionManager`. |
| Kafka | Output record và có thể cả Kafka consumer offset trong cùng Kafka transaction. | `KafkaTransactionManager`. |

### Khoảng lỗi khi commit database trước

```text
Database COMMIT thành công
          |
          X process crash / Kafka commit lỗi
          |
Kafka event chưa được xác nhận commit
```

Đơn hàng đã nằm trong database, nhưng downstream có thể không bao giờ nhận event nếu không có một dấu vết bền vững để phát lại.

### Khoảng lỗi khi commit Kafka trước

```text
Kafka COMMIT thành công
          |
          X process crash / Database commit lỗi
          |
Database chưa xác nhận đơn hàng
```

Consumer downstream có thể đọc event về một đơn hàng chưa tồn tại trong database. **Đổi thứ tự commit chỉ đổi loại rủi ro**, không làm hai resource trở thành một transaction nguyên tử.

## 2. ChainedKafkaTransactionManager đã làm gì?

`ChainedKafkaTransactionManager` giúp chuỗi nhiều Spring `PlatformTransactionManager` theo cơ chế phối hợp local transaction. Tư duy của nó là bắt đầu các resource transaction rồi commit/rollback theo thứ tự được định nghĩa.

Ví dụ minh họa cấu hình legacy:

```java
// Legacy: minh họa code cũ, không khuyến nghị đưa vào dự án mới.
ChainedKafkaTransactionManager<String, String> manager =
        new ChainedKafkaTransactionManager<>(
                dataSourceTransactionManager,
                kafkaTransactionManager);
```

Đây không phải triển khai một transaction coordinator bảo đảm “hoặc cả hai commit, hoặc cả hai rollback” dưới mọi điều kiện lỗi. Nếu transaction của resource thứ nhất đã commit thành công mà commit resource thứ hai thất bại, manager **không thể hoàn tác commit thứ nhất**.

Vì vậy, không nên đưa ra các kết luận sau:

- “Có một `@Transactional` thì cả Kafka và SQL được commit nguyên tử.”
- “Kafka transaction lỗi chắc chắn làm PostgreSQL rollback, kể cả khi DB đã commit.”
- “Chained manager cung cấp exactly-once cho cả database lẫn Kafka.”
- “Nếu gọi `commit()` tuần tự trong một wrapper thì đã giải quyết bài toán distributed transaction.”

Deprecation từ Spring Kafka 2.7 là tín hiệu để ứng dụng chuyển sang các cơ chế có hợp đồng rõ ràng. Việc mã nguồn không còn lớp `ChainedKafkaTransactionManager` chưa đủ để gọi migration thành công; còn phải có kịch bản xử lý **partial commit**.

## 3. Ba lựa chọn thay thế cần phân biệt

| Lựa chọn | Mục đích | Giới hạn |
|---|---|---|
| Database transaction + Kafka synchronization | Ghi DB và phát Kafka trong cùng một method nghiệp vụ với thứ tự commit rõ ràng. | Commit hai resource vẫn không nguyên tử; có thể xảy ra DB commit rồi Kafka lỗi. |
| Hai `@Transactional` lồng nhau với hai transaction manager | Chủ động thay đổi thứ tự commit, ví dụ Kafka trước DB. | Vẫn có khoảng lỗi; event có thể tồn tại trước database state. |
| Transactional outbox + inbox/idempotency | Lưu DB state và ý định phát event trong **một DB transaction**, rồi publish lại đến khi thành công. | Thường là at-least-once; cần deduplication, worker/CDC và giám sát. |

Khi chỉ đọc input Kafka và tạo output Kafka, một Kafka transaction có thể chứa **output và consumer offset** để đạt bảo đảm Kafka-to-Kafka exactly-once. Nhưng khi thêm database làm resource thứ hai, Kafka transaction không tự kéo SQL vào cùng một commit nguyên tử.

## 4. Phương án DB-first bằng Spring transaction synchronization

Spring Kafka hỗ trợ đồng bộ Kafka transaction với một Spring transaction đã mở. Một service có `@Transactional` dùng **database transaction manager**, sau đó gọi `KafkaTemplate.send(...)` với **transactional producer factory**. Kafka transaction được đồng bộ để commit sau transaction chính của database.

```text
@Transactional(DB)
        |
        v
Begin DB transaction
        |
        v
INSERT/UPDATE business data
        |
        v
KafkaTemplate.send(event)
        |
        v
DB COMMIT
        |
        v
Kafka COMMIT
```

Ưu điểm: code khá gọn và tránh dùng chained manager. Nhược điểm: nếu Kafka commit thất bại **sau** khi DB commit, database đã thay đổi nhưng event chưa được xác nhận. Spring có thể báo lỗi cho caller, nhưng không thể tự rollback một DB transaction đã được commit.

### Cấu hình Spring Boot

```yaml
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/orderdb
    username: order_app
    password: DB_SECRET_FROM_ENVIRONMENT
  kafka:
    bootstrap-servers: kafka:9092
    producer:
      transaction-id-prefix: UNIQUE_PREFIX_PER_INSTANCE
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
```

`DB_SECRET_FROM_ENVIRONMENT` và `UNIQUE_PREFIX_PER_INSTANCE` là placeholder minh họa, cần được cấu hình bằng secret và biến môi trường phù hợp. **Transaction ID prefix phải khác nhau giữa những pod đang chạy đồng thời**, nếu không producer có thể bị fencing vì cùng `transactional.id`.

Khi ứng dụng có nhiều transaction manager, nên phân biệt bằng tên bean:

```java
@Configuration
@EnableTransactionManagement
public class TransactionConfig {

    @Bean("dataSourceTransactionManager")
    PlatformTransactionManager dataSourceTransactionManager(
            DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean("kafkaTransactionManager")
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

Các import chính:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
```

Đây là ví dụ cấu hình minh họa. Nếu Spring Boot đã auto-configure các bean transaction manager thích hợp, không cần tạo thêm bean trùng chức năng. Trong dự án thật, hãy xác nhận tên bean, kiểu `ProducerFactory` và `KafkaTemplate` phù hợp; không để `@Transactional` chọn nhầm Kafka manager khi mục tiêu là DB transaction.

### Service dùng DB transaction làm transaction chính

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderService(
            OrderRepository orderRepository,
            KafkaTemplate<String, String> kafkaTemplate) {
        this.orderRepository = orderRepository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public Order createOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(Order.from(command));

        String eventJson = toJson(order);
        kafkaTemplate.send("orders.created", order.getId(), eventJson);

        return order;
    }
}
```

Các kiểu `Order`, `OrderRepository`, `CreateOrderCommand` và `toJson(...)` do ứng dụng tự định nghĩa. Khi có Kafka transaction synchronization hoạt động đúng, `KafkaTemplate` gửi output trong Kafka transaction được đồng bộ với DB transaction.

**`KafkaTemplate.send()` trả future không có nghĩa Kafka transaction đã commit.** Chờ send future có thể giúp nhận ra lỗi publish trước khi DB commit, nhưng không loại bỏ hoàn toàn rủi ro Kafka commit thất bại sau DB commit. Đừng công bố mô hình này là atomic DB–Kafka.

## 5. Crash matrix cho DB-first synchronization

| Thời điểm lỗi | Database | Kafka | Việc cần làm |
|---|---|---|---|
| Trước DB commit | Có thể rollback thay đổi. | Transaction có thể abort. | Caller retry với request ID ổn định. |
| Sau DB commit, trước Kafka commit | Đã commit. | Chưa xác nhận commit. | Reconciliation / outbox / phát lại có kiểm soát. |
| Kafka commit lỗi sau DB commit | Đã commit. | Có thể chưa commit hoặc kết quả chưa rõ ở client. | Không retry mù; kiểm tra event ID và trạng thái producer. |
| Cả hai commit thành công | Đã commit. | Đã commit. | Hoàn tất luồng bình thường. |

Nếu exception được ném sau khi DB đã commit, việc retry toàn bộ method có thể tạo thêm một đơn hàng. Vì vậy cần **request idempotency key**, unique constraint hoặc một cơ chế đối soát theo business ID. Không suy ra từ HTTP 500 rằng database chắc chắn rollback.

## 6. Muốn Kafka commit trước database thì làm gì?

Có thể dùng hai method `@Transactional` với **manager khác nhau** và lồng nhau có chủ đích. Method ngoài mở DB transaction; một bean khác mở Kafka transaction ở method bên trong. Kafka transaction kết thúc trước khi method ngoài commit DB.

```text
BEGIN database transaction (outer)
             |
             v
       INSERT order
             |
             v
 BEGIN Kafka transaction (inner)
             |
             v
        Kafka send
             |
             v
    COMMIT Kafka transaction
             |
             v
    COMMIT database transaction
```

Ví dụ tách riêng bean publisher:

```java
@Service
public class OrderKafkaPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderKafkaPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publish(String orderId, String payload) {
        kafkaTemplate.send("orders.created", orderId, payload);
    }
}
```

```java
@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final OrderKafkaPublisher publisher;

    public OrderCommandService(
            OrderRepository orders,
            OrderKafkaPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public Order create(CreateOrderCommand command) {
        Order order = orders.save(Order.from(command));
        publisher.publish(order.getId(), toJson(order));
        return order;
    }
}
```

Việc tách sang **bean khác** quan trọng trong Spring proxy-based transaction management: tự gọi method `@Transactional` qua `this.method()` trong cùng bean thường **không đi qua proxy**, nên không áp dụng transaction annotation của method được gọi.

**Kafka-first không mạnh hơn DB-first về atomicity.** Nếu Kafka đã commit nhưng database commit thất bại, consumer có thể nhận event về một đối tượng chưa tồn tại trong DB. Nếu downstream yêu cầu đọc DB ngay sau khi nhận event, điều này có thể tạo lỗi nghiệp vụ. Chỉ chọn thứ tự này khi hệ thống có cách xử lý eventual consistency hoặc hành động bù phù hợp.

## 7. Không nhầm synchronization với distributed transaction

Hai cách trên có thể giúp ứng dụng lựa chọn thứ tự commit nhưng đều có **partial commit window**:

| Thuộc tính | DB-first | Kafka-first |
|---|---|---|
| Commit thứ nhất | Database | Kafka |
| Commit thứ hai | Kafka | Database |
| Khi commit thứ hai lỗi | DB đã lưu nhưng event có thể thiếu. | Event đã có nhưng DB row có thể thiếu. |
| Có thể rollback commit thứ nhất? | Không, nếu commit DB đã hoàn tất. | Không, nếu Kafka commit đã hoàn tất. |
| Bảo đảm atomic DB + Kafka | Không. | Không. |

Việc cả hai manager nằm trong cùng JVM hoặc cùng lời gọi service không thay đổi tính chất trên. Khi yêu cầu là “DB đã commit thì cuối cùng phải có event ngay cả khi process chết tức thì”, hãy dùng một **ý định publish được lưu bền vững trong DB transaction**.

## 8. Transactional outbox là giải pháp có ranh giới rõ ràng

Transactional outbox đưa thay đổi nghiệp vụ và ý định publish event vào **cùng một database transaction**. Kafka publish được thực hiện bởi một worker hoặc CDC connector độc lập sau DB commit.

```text
POST /orders
      |
      v
BEGIN DATABASE TRANSACTION
      |
      +--> INSERT orders(...)
      |
      +--> INSERT outbox_events(...)
      |
      v
COMMIT DATABASE TRANSACTION
      |
      v
Outbox worker / CDC
      |
      v
Kafka orders.created
```

Nếu DB transaction rollback, cả row đơn hàng và outbox row đều rollback. Nếu DB transaction commit nhưng process crash trước Kafka publish, outbox row còn lại để worker phát sau. Điểm khác biệt cốt lõi là **ý định phát sự kiện không bị mất khỏi database** sau khi nghiệp vụ commit.

### Ví dụ PostgreSQL schema

```sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_pending
    ON outbox_events (created_at)
    WHERE status = 'PENDING';
```

Ví dụ dùng bảng outbox cho mô hình polling. Với CDC, có thể chọn schema và cơ chế đánh dấu khác tùy connector; không cần luôn có cột `status` như ví dụ.

### Service tạo đơn hàng và outbox event

```java
@Service
public class OutboxOrderService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OutboxOrderService(
            OrderRepository orders, OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public Order create(CreateOrderCommand command) {
        Order order = orders.save(Order.from(command));

        outbox.save(OutboxEvent.pending(
                UUID.randomUUID(),
                "Order",
                order.getId(),
                "OrderCreated",
                toJson(order)));

        return order;
    }
}
```

Các kiểu `OutboxEvent` và repository là thành phần nghiệp vụ cần định nghĩa. Kafka không xuất hiện trực tiếp trong transaction này; **hai thay đổi cần atomic đều ở cùng database**.

## 9. Outbox publisher và giới hạn at-least-once

Worker lấy các row `PENDING`, gửi Kafka và đánh dấu `PUBLISHED` sau khi nhận kết quả gửi phù hợp:

```text
Outbox row PENDING
       |
       v
Publish Kafka event
       |
       v
Confirm send/publish outcome
       |
       v
Mark outbox row PUBLISHED
```

Nếu worker crash **sau Kafka publish thành công nhưng trước khi đánh dấu PUBLISHED**, lần chạy sau có thể gửi lại event. Đây là lý do transactional outbox thường bảo đảm **at-least-once delivery**, không tự bảo đảm mỗi consumer chỉ xử lý sự kiện một lần.

Các nguyên tắc vận hành:

- Dùng **event ID ổn định**, giữ nguyên giữa mọi lần publish retry.
- Consumer downstream phải có **idempotency** theo event ID.
- Nếu nhiều worker cùng chạy, dùng claim/lease an toàn, chẳng hạn `SELECT ... FOR UPDATE SKIP LOCKED` trong transaction phù hợp, để hạn chế tranh chấp.
- Retry có backoff và giám sát số lần thử; không retry vô hạn trong một HTTP request.
- Theo dõi số row pending và tuổi row lâu nhất chưa publish.
- Có quy trình xử lý event lỗi serialization, schema hoặc quyền ghi Kafka.
- Có retention/cleanup các outbox row đã hoàn tất theo chính sách audit và replay.

**Không đánh dấu PUBLISHED trước khi publish được xác nhận** để tránh duplicate: crash sau đánh dấu nhưng trước publish có thể gây mất event vĩnh viễn.

## 10. CDC và Debezium cho outbox

Thay vì viết worker polling, có thể dùng Change Data Capture (CDC), ví dụ Debezium connector, để phát hiện outbox row đã commit trong transaction log của database.

```text
Spring service
     |
     v
PostgreSQL COMMIT (orders + outbox_events)
     |
     v
PostgreSQL WAL
     |
     v
CDC connector / Outbox Event Router
     |
     v
Kafka topic
```

Ưu điểm: không cần giữ HTTP request chờ Kafka, và connector có thể phát event dựa trên thay đổi DB đã commit. Đổi lại phải vận hành connector, replication slot, WAL retention, mapping schema, lag và cơ chế retry. CDC vẫn có thể phát record lặp trong một số kịch bản restart; idempotent consumer vẫn là yêu cầu quan trọng.

## 11. Inbox / idempotent consumer

Kafka consumer có thể nhận cùng event nhiều lần khi:

- Outbox worker publish thành công rồi crash trước khi cập nhật trạng thái.
- Consumer xử lý thành công nhưng crash trước khi commit offset.
- Người vận hành replay DLT hoặc reset offset.
- Client không biết chắc kết quả commit do mất kết nối.

Ví dụ bảng lưu dấu vết xử lý:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong cùng DB transaction, consumer ghi dấu vết event ID và thay đổi nghiệp vụ:

```java
@Transactional(transactionManager = "dataSourceTransactionManager")
public void onOrderCreated(OrderCreated event) {
    boolean inserted = processedEvents.tryInsert(
            "shipping-service", event.eventId());
    if (!inserted) {
        return;
    }

    shipmentRepository.createShipment(event);
}
```

`tryInsert` phải dựa trên unique constraint và thao tác xử lý conflict nguyên tử, không chỉ kiểm tra `exists()` rồi insert không có ràng buộc. Nếu database đã commit nhưng Kafka offset chưa commit, lần giao lại có thể được nhận diện là đã xử lý, tránh tạo shipment lần hai.

## 12. Kafka EOS cho output và offset không mở rộng sang database

Trong luồng Kafka → xử lý → Kafka, Spring Kafka có thể đưa **output record và offset input** vào cùng một Kafka transaction:

```text
Kafka input
     |
     v
Transactional @KafkaListener
     |
     +--> KafkaTemplate.send(output)
     |
     +--> sendOffsetsToTransaction(...)
     |
     v
Kafka transaction COMMIT / ABORT
```

Khi transaction abort, consumer `read_committed` không thấy output aborted và offset không commit trong transaction đó. Đây là bảo đảm Kafka-to-Kafka exactly-once về output/offset, **không phải atomicity với PostgreSQL**.

Nếu listener vừa update database vừa gửi Kafka output, DB commit vẫn có thể hoàn tất trong khi Kafka transaction abort. Input sau đó được giao lại và có thể làm database cập nhật lần hai. Cần inbox/idempotency, outbox hoặc một cơ chế đồng bộ khác.

Với transactional listener, xử lý lỗi cần tương thích với `AfterRollbackProcessor` và chính sách rollback của container. Không nuốt exception khiến container coi record thất bại là đã thành công để rồi commit output/offset sai.

## 13. Chọn mô hình theo độ tin cậy cần thiết

| Mục tiêu nghiệp vụ | Cách tiếp cận | Điều cần bổ sung |
|---|---|---|
| Chấp nhận rủi ro một bên commit và có thể đối soát | DB-first synchronization. | Monitoring, reconciliation, idempotency. |
| Consumer có thể nhận event trước khi DB state sẵn sàng | Nested Kafka-first transaction. | Eventual consistency, compensation, idempotency. |
| DB đã commit thì ý định publish không được mất sau crash | Transactional outbox. | Worker/CDC, at-least-once, consumer dedupe. |
| Consumer cập nhật DB từ Kafka event | Inbox / idempotent processing. | Unique key, ghi dấu vết và DB side effect cùng transaction. |
| Chỉ đọc Kafka và ghi lại Kafka | Kafka transaction bao gồm output và offset. | `read_committed`, transaction manager, recovery. |
| Workflow nhiều service và resource | Saga / compensation. | State machine, timeout, sự kiện bù và đối soát. |

Nếu event liên quan thanh toán, giao hàng, tồn kho hoặc các nghiệp vụ mà thiếu event gây thiệt hại đáng kể, transactional outbox có retry và giám sát thường phù hợp hơn cách phối hợp hai local commit theo best effort.

## 14. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| DB có đơn hàng nhưng Kafka không có event | DB-first partial commit hoặc producer/transaction commit thất bại. | Xem producer errors, transaction result, event ID, reconciliation/outbox. |
| Kafka có event nhưng DB không có đơn hàng | Kafka-first commit trước DB; DB transaction rollback. | Kiểm tra thứ tự commit, log DB, retry/compensation. |
| Sau retry tạo hai đơn hàng | Request không idempotent, không có unique constraint. | Bổ sung business request key và ghi DB nguyên tử. |
| Kafka event bị lặp | Outbox publisher crash sau publish hoặc consumer replay. | Dùng event ID bền vững và inbox dedupe. |
| `@Transactional` không có hiệu lực ở method nested | Self-invocation bỏ qua Spring proxy, hoặc chọn sai manager. | Gọi qua bean khác, kiểm tra proxy và transaction manager. |
| `ProducerFencedException` sau rollout | Transaction ID prefix trùng giữa các pod. | Kiểm tra prefix/suffix của producer factory theo instance. |
| Outbox pending tăng | Worker/CDC lỗi, broker unavailable hoặc lỗi serializer/ACL. | Kiểm tra backlog age, publisher logs và Kafka send result. |
| Consumer đã ghi DB nhưng offset không tiến | DB và Kafka commit khác nhau; consumer restart/rebalance. | Dùng inbox idempotency và kiểm tra committed offset. |

Khi debug, đừng kết luận từ một log “KafkaTemplate.send() called”. Cần biết record đã được broker nhận chưa, Kafka transaction đã commit chưa, và consumer downstream đọc bằng isolation level nào.

## 15. Runbook: DB commit nhưng thiếu Kafka event

Giả sử service đã lưu `orderId=ord-4782` nhưng downstream không thấy `OrderCreated`.

1. **Xác định transaction model.** Đang dùng synchronization, Kafka-first hay outbox? Không đánh đồng log và hành vi của ba mô hình.
2. **Kiểm tra DB state.** Tìm order theo business ID và idempotency key, ghi lại thời điểm DB commit.
3. **Kiểm tra producer.** Xem lỗi serialize, ACL, timeout, coordinator, abort và fencing. Không coi HTTP 500 là bằng chứng DB rollback.
4. **Tra cứu Kafka theo event ID.** Tìm ở đúng cluster/topic. Với transactional output, consumer kiểm tra nên dùng `read_committed`.
5. **Nếu có outbox**, xem row `PENDING`, claim/lease, attempts, lỗi CDC/worker và backlog age. Khôi phục publisher trước khi tự publish.
6. **Nếu là synchronous dual-write**, xác định partial commit, đối soát và phát event bù với cùng event ID; không tạo lại đơn hàng.
7. **Xác nhận downstream**, đo record đã được xử lý và hiệu ứng nghiệp vụ đã xuất hiện, không chỉ đo producer send count.

Không reset offset hoặc replay hàng loạt khi chưa biết event đã commit ở Kafka hay chưa; có thể tạo duplicate ngoài dự kiến.

## 16. Runbook: Kafka event đã có nhưng database rollback

Đây là nguy cơ khi Kafka-first hoặc khi publisher nằm ngoài DB transaction dự kiến:

1. Kiểm tra `@Transactional` và transaction manager thực tế tại method publisher và method DB.
2. Xác nhận nested Kafka transaction có thực sự đi qua Spring proxy, không phải self-invocation.
3. Kiểm tra constraint violation, deadlock, transaction timeout hoặc rollback-only flag của database.
4. Xác nhận event ở Kafka đã **commit**, thay vì record aborted mà consumer `read_uncommitted` nhìn thấy.
5. Nếu event đã commit nhưng DB state không có, phát hành compensating event hoặc tạo lại state theo business ID với idempotency.
6. Đánh giá lại thứ tự commit và kiến trúc; chuyển sang outbox nếu downstream yêu cầu DB state phải tồn tại trước event.

Một Kafka record đã commit không thể bị “undo” bằng cách rollback PostgreSQL sau đó. Compensation là **một sự kiện nghiệp vụ mới**, không phải xóa lịch sử Kafka.

## 17. Quan sát production

Theo dõi cả Kafka lẫn database, thay vì chỉ nhìn producer throughput:

- Tỷ lệ DB transaction commit/rollback và lỗi deadlock/constraint.
- Kafka producer send error, commit/abort rate, timeout và `ProducerFencedException`.
- Outbox pending count, oldest pending age, attempts và publish failures.
- CDC connector status, lag, replication slot/WAL retention nếu sử dụng.
- Consumer lag, DLT ingress, duplicate event được inbox bỏ qua.
- Reconciliation mismatch giữa DB state và event downstream.

Ví dụ log do ứng dụng tự định nghĩa:

```text
event=order_created
order_id=ord-4782
event_id=6c4de23b-6e99-4e89-9695-2586e8ce8840
db_transaction=COMMITTED
outbox_status=PENDING
kafka_publish_status=NOT_YET_CONFIRMED
```

Không gắn trạng thái `kafka_publish_status=COMMITTED` chỉ vì `send()` trả future. Nếu dùng Kafka transaction, phải xét kết quả transaction commit. Tên metric và log ở trên là gợi ý instrumentation, không phải tên mặc định của Spring Kafka.

## 18. Migration khỏi ChainedKafkaTransactionManager

Khi gặp mã nguồn cũ dùng `ChainedKafkaTransactionManager`, làm theo trình tự:

1. Xác định mọi bean `ChainedKafkaTransactionManager`, listener container, transaction manager và `KafkaTemplate` liên quan.
2. Làm rõ **commit order** hiện tại, loại giao dịch mở trong request và các side effect ngoài Kafka/DB.
3. Lập crash matrix: trước commit, giữa hai commit, sau commit, timeout không rõ kết quả.
4. Chọn mô hình thay thế dựa trên yêu cầu độ tin cậy: synchronized local transactions hoặc outbox/inbox.
5. Với Spring synchronization, dùng `@Transactional(transactionManager="dataSourceTransactionManager")` và KafkaTemplate transactional. Với Kafka-first, tách nested method qua bean khác.
6. Với outbox, tạo schema, event ID, worker/CDC, retry, monitoring, dedupe và reconciliation.
7. Kiểm thử failure injection: Kafka down sau DB commit, DB deadlock sau Kafka publish, pod crash, producer fencing, replay.
8. Rollout có quan sát mismatch, outbox backlog, DLT và side effect trùng.

Không thay lớp chained bằng một wrapper tự viết vẫn gọi hai phương thức `commit()` rồi đặt tên “atomic manager”. Thay đổi đó giữ nguyên dual-write failure window mà không tạo thêm bảo đảm.

## 19. Checklist thiết kế và triển khai

- [ ] Đã xác định hệ thống nào là **source of truth** của nghiệp vụ.
- [ ] Không xem `ChainedKafkaTransactionManager` như XA hoặc distributed atomic commit.
- [ ] Chỉ định rõ manager trong `@Transactional` khi có cả DB và Kafka manager.
- [ ] `KafkaTemplate` dùng transactional producer factory nếu cơ chế yêu cầu Kafka transaction.
- [ ] Transaction ID prefix không trùng giữa các instance đang chạy đồng thời.
- [ ] Có mô tả hành vi khi crash **giữa hai bước commit**.
- [ ] Có request idempotency key, event ID bền vững và unique constraint.
- [ ] Nếu yêu cầu event không mất sau DB commit, sử dụng transactional outbox hoặc cơ chế tương đương có bảo đảm lưu ý định publish.
- [ ] Outbox publisher/CDC có retry, backoff, monitoring và khả năng xử lý duplicate.
- [ ] Consumer có inbox/deduplication cho các thao tác DB không được phép thực hiện hai lần.
- [ ] Có runbook reconciliation, replay/DLT và quyền vận hành tương ứng.
- [ ] Đã thử nghiệm pod crash, broker outage, database rollback và commit result không rõ ràng.

## 20. Kết luận

`ChainedKafkaTransactionManager` không thể khiến Kafka và database commit nguyên tử như một transaction XA. Việc tránh phụ thuộc vào lớp này giúp hệ thống công khai đúng giới hạn của từng resource và chọn phương án phục hồi phù hợp.

Nếu chỉ cần **best-effort transaction synchronization**, Spring Kafka hỗ trợ `KafkaTemplate` tham gia transaction được điều phối bởi database manager, với rủi ro Kafka commit sau DB có thể thất bại. Nếu yêu cầu là **database đã commit thì ý định publish event phải tồn tại bất chấp crash**, transactional outbox cùng inbox/idempotency là mô hình đáng tin cậy hơn. Độ tin cậy đến từ dữ liệu bền vững, retry và reconciliation có thể kiểm chứng — không đến từ việc đặt hai transaction manager dưới một tên lớp duy nhất.
