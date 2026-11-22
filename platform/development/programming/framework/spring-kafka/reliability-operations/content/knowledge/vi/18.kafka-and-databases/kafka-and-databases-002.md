# DB-first commit order

Trong một ứng dụng Spring Kafka, nghiệp vụ thường cần **ghi database và phát sự kiện Kafka** trong cùng một thao tác: tạo đơn hàng trong PostgreSQL rồi phát `OrderCreated`, cập nhật tồn kho rồi phát `InventoryReserved`, hoặc tiêu thụ một Kafka record, ghi kết quả vào database rồi xác nhận offset. Vấn đề là transaction của database và transaction của Kafka thuộc **hai hệ thống độc lập**.

**DB-first commit order** là chiến lược trong đó **database transaction commit trước, Kafka transaction commit sau**. Spring Kafka có thể phối hợp các transaction theo thứ tự này bằng transaction synchronization; một luồng Kafka listener transactional cũng có thể đạt thứ tự tương tự khi database transaction bên trong hoàn tất trước transaction Kafka của container.

Thứ tự DB-first giúp hiểu rõ lúc nào dữ liệu trong database trở nên bền vững. Tuy nhiên, **DB-first không phải distributed atomic transaction**. Nếu database đã commit nhưng Kafka commit thất bại, database không thể tự rollback. Đây là khoảng trống độ tin cậy quan trọng cần thiết kế recovery, idempotency và thường là **transactional outbox**.

## 1. Vì sao phải quan tâm đến commit order?

Ví dụ service xử lý yêu cầu tạo đơn hàng:

~~~text
HTTP POST /orders
       |
       v
OrderService.createOrder()
       |
       +---- INSERT INTO orders ...
       |
       +---- KafkaTemplate.send("orders.created", ...)
       |
       v
Trả kết quả cho client
~~~

Trong code, thao tác `INSERT` có thể chạy trước `send()`. Nhưng **thứ tự gọi phương thức không đồng nghĩa với thứ tự transaction commit**:

- `jdbcTemplate.update(...)` thực hiện SQL trong database transaction, chưa nhất thiết đã commit.
- `kafkaTemplate.send(...)` gửi record bằng Kafka producer; với transactional producer, record chưa trở thành committed output cho consumer `read_committed`.
- Transaction manager và transaction synchronization quyết định **khi nào** database commit và Kafka commit.

Nếu database commit rồi Kafka commit, hệ thống là **DB-first**. Nếu Kafka commit trước database, hệ thống là **Kafka-first**. Cả hai thứ tự đều tồn tại failure window giữa hai lần commit.

### 1.1. Đích đến lý tưởng và thực tế

Mong muốn nghiệp vụ thường là:

~~~text
DB có order O-1001  <=>  Kafka có event OrderCreated(O-1001)
~~~

Với hai transaction độc lập, điều kiện hai chiều này **không được bảo đảm nguyên tử** chỉ bởi `@Transactional` hoặc `KafkaTransactionManager`. Ngay cả khi cả hai được đồng bộ trong một luồng Java, vẫn có thể xảy ra lỗi sau khi hệ thống thứ nhất đã commit và trước khi hệ thống thứ hai commit.

## 2. DB-first thực sự diễn ra như thế nào?

Giả sử method được quản lý bởi `DataSourceTransactionManager`, còn `KafkaTemplate` dùng một transactional `ProducerFactory` và đồng bộ Kafka transaction vào database transaction đang hoạt động.

~~~text
                        Thread xử lý request
                                 |
             begin DB transaction (primary transaction)
                                 |
                        INSERT / UPDATE DB
                                 |
                        KafkaTemplate.send()
                                 |
              Kafka transactional send (chưa commit)
                                 |
                        Method kết thúc bình thường
                                 |
                    [1] COMMIT DATABASE
                                 |
                    [2] COMMIT KAFKA TRANSACTION
                                 |
                      Hoàn tất lời gọi service
~~~

Hai lần commit là hai thao tác độc lập với resource khác nhau:

1. **Database commit:** các thay đổi SQL được ghi bền vững theo mức durability của database.
2. **Kafka transaction commit:** các record Kafka thuộc transaction được xác nhận committed; những offset được đưa vào transaction (nếu có) cũng commit cùng output Kafka.
3. Nếu bước 2 lỗi, **bước 1 không tự bị đảo ngược**.

Kafka không tham gia một transaction XA/2PC chung với database trong mô hình Spring Kafka transaction synchronization này. Transaction synchronization là cơ chế **sắp xếp lifecycle** giữa các resource, không phải một atomic commit protocol liên hệ hai coordinator.

## 3. Thiết lập producer có Kafka transaction

Để `KafkaTemplate` thực sự tham gia Kafka transaction, producer factory phải được cấu hình transactional ID. Với Spring Boot, ví dụ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: "orders-instance-a-tx-"
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

`transaction-id-prefix` làm cho producer factory quản lý transactional producers. Spring Kafka tạo các transactional ID đầy đủ từ prefix và suffix; phải bảo đảm **không có hai instance active-active tạo trùng transactional ID**.

Trong production, `orders-instance-a-tx-` chỉ là tên minh họa. Prefix cần được tạo theo định danh instance/worker ổn định trong phạm vi hoạt động đồng thời và theo chiến lược fencing phù hợp. Khi dùng container orchestrator, cần xem xét rollout overlap và khả năng tái sử dụng transactional ID.

`acks=all` giúp broker xác nhận việc ghi theo chính sách replication, nhưng **không làm database và Kafka commit nguyên tử**. Record được broker nhận trong một Kafka transaction chưa có nghĩa transaction đã commit.

### 3.1. Transaction manager nào là primary?

Nếu ứng dụng có cả `DataSourceTransactionManager` và `KafkaTransactionManager`, một `@Transactional` không nêu tên manager có thể khó đọc hoặc phụ thuộc vào lựa chọn bean của Spring. Với DB-first, hãy làm rõ database transaction manager là **primary transaction** tại điểm bắt đầu nghiệp vụ.

Ví dụ khai báo tên transaction manager minh bạch:

~~~java
@Configuration
public class DatabaseTransactionConfiguration {

    @Bean("dataSourceTransactionManager")
    public DataSourceTransactionManager dataSourceTransactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Trong ứng dụng dùng JPA, transaction manager của database có thể là `JpaTransactionManager` thay vì `DataSourceTransactionManager`. Điều quan trọng là annotation phải chỉ tới đúng transaction manager đang quản lý các thao tác ghi dữ liệu.

Spring Boot có thể tự tạo transaction manager khi đủ điều kiện; không cần tạo thêm bean nếu ứng dụng đã có manager thích hợp. Các snippet trong bài chỉ minh họa những thành phần cần được thiết lập, không phải cấu hình auto-configuration duy nhất.

## 4. Ví dụ @Transactional DB-first với KafkaTemplate

Một service nhận command, lưu order và phát event:

~~~java
@Service
public class OrderCommandService {

    private final JdbcTemplate jdbcTemplate;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderCommandService(
            JdbcTemplate jdbcTemplate,
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.jdbcTemplate = jdbcTemplate;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public void createOrder(CreateOrder command) {
        jdbcTemplate.update(
                "INSERT INTO orders (id, status) VALUES (?, ?)",
                command.orderId(),
                "NEW");

        OrderCreated event = new OrderCreated(command.orderId(), "NEW");
        kafkaTemplate.send("orders.created", command.orderId(), event);
    }
}
~~~

Giả sử `CreateOrder` và `OrderCreated` là Java records/DTO nghiệp vụ, database schema đã có bảng `orders`, Kafka producer đã bật transaction, và `KafkaTemplate` được cung cấp bởi transactional producer factory.

Khi service đi qua proxy Spring và database transaction được mở:

1. `createOrder()` bắt đầu database transaction.
2. SQL ghi order nhưng chưa commit.
3. `KafkaTemplate` sử dụng transactional producer được đồng bộ với transaction hiện tại.
4. Khi method trả về bình thường, Spring **commit DB trước**.
5. Sau đó Spring thực hiện **commit Kafka transaction** đã đồng bộ.
6. Nếu Kafka commit thành công, database state và Kafka event đều được xác nhận.

### 4.1. Điều kiện để ví dụ vận hành đúng

- Gọi method thông qua **Spring proxy**; self-invocation trong cùng class thường bỏ qua interceptor `@Transactional`.
- Database operations phải dùng cùng transactional resource do DB manager quản lý.
- Kafka producer factory phải có `transactionIdPrefix` và KafkaTemplate phù hợp.
- Không dùng `KafkaTemplate.executeInTransaction(...)` tùy tiện bên trong method rồi kỳ vọng inner transaction tự có cùng thứ tự DB-first; API này quản lý transaction theo cách riêng.
- Nếu Spring context có nhiều transaction manager, xác định rõ manager trong annotation.
- Serializer và partition key phải phù hợp với event thực tế; một lỗi serialization trước commit có thể làm method thất bại.
- Để kiểm chứng transaction visibility, dùng consumer có `isolation.level=read_committed`.

Nếu cần chờ kết quả Kafka send, có thể kiểm tra future theo API của phiên bản Spring Kafka đang dùng, nhưng phải hiểu **Kafka send acknowledged không đồng nghĩa Kafka transaction committed**.

## 5. Vì sao send() thành công vẫn chưa bảo đảm kết quả?

`KafkaTemplate.send()` thường trả về một future tương ứng với kết quả gửi. Kafka producer có thể nhận broker acknowledgment rằng record đã được ghi vào log trong transaction.

~~~text
KafkaTemplate.send()
        |
        v
Broker ghi record có transaction metadata
        |
        v
Producer nhận send acknowledgment
        |
        v
Kafka transaction vẫn đang mở
        |
        +---- commit thành công -> read_committed consumer nhìn thấy
        |
        +---- abort / timeout -> read_committed consumer bỏ qua
~~~

Do đó:

- Future của `send()` có thể thành công **trước** Kafka transaction commit.
- `acks=all` không thay thế `commitTransaction()`.
- Nếu commit xảy ra sau DB commit và commit Kafka lỗi, database vẫn có thể chứa order trong khi event chưa được commit.
- Nếu mạng đứt đúng thời điểm commit, ứng dụng có thể **không biết chắc** broker đã commit thành công hay chưa.

Không nên dùng `send().get()` hoặc `send().join()` làm bằng chứng rằng database và Kafka đã commit atomically.

## 6. Failure windows của DB-first

Điểm dễ sai nhất nằm ở các mốc thời gian khác nhau:

| Thời điểm lỗi | Database | Kafka event | Điều cần xử lý |
|---|---|---|---|
| Trước khi DB transaction commit | Có thể rollback | Kafka transaction chưa commit; cần abort/timeout phù hợp | Retry operation theo semantics nghiệp vụ. |
| Sau DB commit, trước Kafka commit | **Đã commit** | Chưa commit, hoặc kết quả cuối chưa rõ | Có khoảng trống DB/Kafka; cần cơ chế reconciliation/recovery. |
| Kafka commit trả lỗi rõ ràng | **Đã commit** | Có thể chưa commit; tùy lỗi có thể chưa rõ kết quả | Không tự giả định DB rollback hay event chắc chắn mất. |
| Cả DB và Kafka commit xong, nhưng response thất lạc | **Đã commit** | **Đã commit** | Client retry có thể tạo duplicate command/event nếu thiếu idempotency. |
| Process bị kill ngay sau DB commit | **Đã commit** | Transaction Kafka có thể chưa commit; broker xử lý timeout/fencing | Khi restart phải có đường phát lại event bị thiếu. |

### 6.1. Lỗi trước khi database commit

Ví dụ SQL vi phạm unique constraint hoặc service ném exception trước khi method hoàn tất. Database transaction có thể rollback. Kafka transaction được đồng bộ cũng cần được kết thúc tương ứng; những record chưa commit không được coi là output hợp lệ đối với consumer `read_committed`.

Trường hợp này thường dễ phục hồi hơn, vì database chưa trở thành nguồn dữ liệu bền vững cho thay đổi mới.

### 6.2. Database commit thành công nhưng Kafka commit lỗi

Đây là **DB-first failure window**:

~~~text
INSERT order O-1001
        |
        v
DB COMMIT thành công
        |
        v
Kafka COMMIT lỗi / timeout
        |
        +---- DB vẫn có O-1001
        |
        +---- orders.created có thể chưa có committed event
~~~

Về phía application, exception có thể được ném ra trong giai đoạn hoàn tất transaction synchronization. Các phiên bản Spring Kafka hiện đại truyền lỗi secondary Kafka commit ra caller để ứng dụng có thể thực hiện **compensating action**. Với phiên bản cũ, một số lỗi sau primary commit từng có cách báo log khác; cần đánh giá behavior của đúng version đang chạy.

**Lỗi secondary commit không thể đảo ngược primary DB commit đã thành công.** Không nên bắt exception rồi thực hiện thao tác “rollback DB” trên cùng transaction đã đóng.

### 6.3. Không biết chắc kết quả Kafka commit

Lỗi network ngay sau khi gửi commit request là tình huống “unknown outcome”: broker có thể đã xử lý commit nhưng response không đến được producer. Nếu ứng dụng lập tức gửi lại một event mới bằng producer mới, **có thể tạo duplicate**.

Thiết kế recovery nên dùng event ID ổn định, có tracking state và khả năng xử lý idempotent; không suy diễn “exception = Kafka chắc chắn chưa có event”.

## 7. Kafka-first có giải quyết vấn đề không?

Nếu đảo thứ tự để Kafka commit trước database, rủi ro chỉ đổi phía:

~~~text
Kafka transaction COMMIT
           |
           v
Database COMMIT
           |
           +---- database commit lỗi
           |
           +---- event đã visible nhưng DB chưa có state tương ứng
~~~

Kafka-first phù hợp với một số yêu cầu workflow, nhưng không giải quyết atomicity cross-system. Trong Spring, có thể điều phối thứ tự bằng nested transactional methods và những transaction manager khác nhau, song cách làm đó cũng có failure window giữa hai lần commit.

| Commit order | Failure window chính |
|---|---|
| **DB-first** | DB state mới đã tồn tại nhưng Kafka event chưa được commit/được xác nhận. |
| **Kafka-first** | Kafka event đã commit nhưng DB state tương ứng chưa commit. |

Vì vậy, lựa chọn DB-first thường xuất phát từ yêu cầu coi **database là source of truth**, chứ không phải một bằng chứng rằng workflow đã có exactly-once end-to-end.

## 8. DB-first trong Kafka consumer xử lý database

Một biến thể khác thường gặp: listener container mở Kafka transaction, nhưng xử lý database nằm trong method có database transaction riêng. Database method kết thúc trước khi listener container commit Kafka transaction.

~~~text
Kafka listener container mở Kafka transaction
              |
              v
Listener gọi dbWriter.apply(event)
              |
              v
Database transaction bắt đầu
              |
              v
INSERT / UPDATE / UPSERT
              |
              v
DATABASE COMMIT khi dbWriter.apply() trả về
              |
              v
Listener có thể gửi Kafka output
              |
              v
Kafka listener transaction COMMIT
(Kafka output + input offset)
~~~

Ví dụ chia hai Spring beans để database `@Transactional` được proxy xử lý:

~~~java
@Service
public class OrderDatabaseWriter {

    private final JdbcTemplate jdbcTemplate;

    public OrderDatabaseWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(transactionManager = "dataSourceTransactionManager")
    public void apply(OrderEvent event) {
        jdbcTemplate.update(
                "UPDATE orders SET status = ? WHERE id = ?",
                event.status(),
                event.orderId());
    }
}
~~~

Listener dùng Kafka container đã được cấu hình transaction manager:

~~~java
@Component
public class OrderKafkaListener {

    private final OrderDatabaseWriter dbWriter;
    private final KafkaTemplate<String, OrderProcessed> kafkaTemplate;

    public OrderKafkaListener(
            OrderDatabaseWriter dbWriter,
            KafkaTemplate<String, OrderProcessed> kafkaTemplate) {
        this.dbWriter = dbWriter;
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.in",
            containerFactory = "transactionalListenerFactory")
    public void handle(ConsumerRecord<String, OrderEvent> record) {
        dbWriter.apply(record.value()); // DB commit khi method này hoàn tất

        kafkaTemplate.send(
                "orders.processed",
                record.key(),
                new OrderProcessed(record.value().orderId()));
    }
}
~~~

Trong trường hợp này, cần hiểu **hai transaction được lồng theo vòng đời**, không được hợp nhất thành một XA transaction:

- DB commit có thể đã xảy ra khi `dbWriter.apply()` trả về.
- Kafka transaction của container commit sau khi listener hoàn tất, bao gồm output Kafka và input offset nếu được cấu hình đúng.
- Nếu Kafka transaction bị abort hoặc producer bị fence, input offset có thể chưa commit và record sẽ được giao lại.
- Khi redelivery, database operation có thể được thực thi thêm lần nữa nếu không có idempotency.

Lưu ý: Đây là **một cách đạt DB-first**, khác với ví dụ service mở **DB primary transaction** và dùng Kafka resource synchronization. Cần phân biệt hai mô hình khi đọc stack trace, log và thiết kế recovery.

## 9. Consumer redelivery và idempotency với database

Giả sử listener xử lý event `PaymentAuthorized(id=E-100)`:

~~~text
Consumer đọc E-100
      |
      v
DB UPDATE thành công, COMMIT
      |
      v
Kafka offset commit thất bại
      |
      v
Consumer restart / rebalance
      |
      v
E-100 được giao lại
      |
      v
DB UPDATE lặp
~~~

Nếu SQL chỉ làm `SET status = 'AUTHORIZED'`, việc chạy lại có thể không tạo tác dụng phụ thêm. Nhưng nếu xử lý bằng `balance = balance - amount` hoặc ghi thêm payment transaction, lặp lại có thể gây sai dữ liệu nghiêm trọng.

Một giải pháp là **inbox/deduplication table** với unique constraint theo consumer và event ID. Logic cập nhật nghiệp vụ và ghi dấu đã xử lý phải nằm **trong cùng database transaction**:

~~~sql
CREATE TABLE consumed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ví dụ PostgreSQL:

~~~java
@Transactional(transactionManager = "dataSourceTransactionManager")
public void applyOnce(PaymentAuthorized event) {
    int inserted = jdbcTemplate.update(
            """
            INSERT INTO consumed_events (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "payments-consumer",
            event.eventId());

    if (inserted == 0) {
        return; // Event đã áp dụng trong DB
    }

    jdbcTemplate.update(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?",
            event.amount(),
            event.accountId());
}
~~~

Đoạn SQL và Java dùng PostgreSQL và text blocks của Java hiện đại. Nếu update nghiệp vụ ném exception, **toàn bộ DB transaction** rollback, gồm cả marker trong `consumed_events`. Nếu duplicate được giao lại sau DB commit, marker giúp bỏ qua business side effect. Với consumer khác, nên dùng namespace riêng (`consumer_name`) nếu nghiệp vụ yêu cầu mỗi consumer độc lập áp dụng event.

Đây là **idempotent DB processing**, không loại trừ hoàn toàn duplicate Kafka event; nó giúp doanh nghiệp chịu được at-least-once delivery trong khoảng trống DB-first.

## 10. Transactional outbox: cách ưu tiên khi cần publish event đáng tin cậy

Nếu yêu cầu là “mỗi thay đổi database bền vững phải có một event cuối cùng được publish”, dùng transaction synchronization DB-first thuần túy có điểm yếu: **sau DB commit và trước Kafka commit, không nhất thiết có bằng chứng bền vững để phát lại event bị thiếu**.

**Transactional outbox** thu hẹp khoảng trống bằng cách lưu business state và **ý định publish event** trong *cùng một database transaction*.

~~~text
Business request
       |
       v
DB transaction
       |
       +---- INSERT/UPDATE orders
       |
       +---- INSERT outbox_events(event_id, payload, ...)
       |
       v
DB COMMIT (business + outbox nguyên tử)
       |
       v
Outbox publisher / CDC đọc event chưa publish
       |
       v
Kafka publish
       |
       v
Đánh dấu đã publish hoặc checkpoint CDC
~~~

Nếu DB rollback, cả business state và outbox record rollback. Nếu Kafka tạm thời không khả dụng, **outbox record vẫn còn trong DB** để thử gửi lại khi hệ thống phục hồi.

### 10.1. Ví dụ schema outbox

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ NULL
);
~~~

Schema trên minh họa PostgreSQL. Một hệ thống production còn có thể cần state, retry count, partition key, lỗi publish gần nhất, lease/claim fields hoặc retention/archival policy.

Business service ghi hai loại row trong một DB transaction:

~~~java
@Transactional(transactionManager = "dataSourceTransactionManager")
public void createOrder(CreateOrder command) {
    UUID eventId = UUID.randomUUID();

    jdbcTemplate.update(
            "INSERT INTO orders (id, status) VALUES (?, ?)",
            command.orderId(), "NEW");

    jdbcTemplate.update(
            """
            INSERT INTO outbox_events (
                event_id, aggregate_type, aggregate_id, event_type, payload
            ) VALUES (?, ?, ?, ?, ?::jsonb)
            """,
            eventId,
            "Order",
            command.orderId(),
            "OrderCreated",
            serializeOrderCreated(command, eventId));
}
~~~

Không cần gọi Kafka trong chính transaction này. Nếu DB commit thành công, event intent đã được lưu bền vững cùng order.

### 10.2. Publisher và cửa sổ duplicate

Outbox publisher thường:

1. Chọn những event chưa gửi thành công.
2. Publish tới Kafka với **event ID ổn định**.
3. Xác nhận Kafka publish/transaction theo cơ chế đang dùng.
4. Đánh dấu row là published.

Nếu Kafka publish thành công nhưng tiến trình chết **trước khi update `published_at`**, row sẽ được gửi lại. Vì vậy, outbox mặc định thường đem lại **at-least-once publishing**, không phải chính xác một lần trong mọi hệ thống.

Thiết kế phù hợp là **outbox + stable event ID + idempotent consumer**. Nếu có nhiều worker outbox đồng thời, phải dùng claim/locking an toàn, chẳng hạn `FOR UPDATE SKIP LOCKED` cùng timeout/recovery phù hợp, để tránh cạnh tranh và giảm duplicate không cần thiết.

Có thể dùng **Change Data Capture (CDC)**, chẳng hạn Debezium outbox pattern, thay cho polling publisher. Dù chọn CDC hay polling, vẫn cần xem xét duplicate delivery, ordering theo aggregate, schema evolution và monitoring.

## 11. Khi nào DB-first trực tiếp vẫn hợp lý?

Không phải mọi ứng dụng đều cần outbox. Transaction synchronization DB-first có thể đủ khi:

- Kafka event chỉ phục vụ cache invalidation hoặc thông báo có thể tái tạo dễ dàng.
- Hệ thống có reconciliation job định kỳ phát lại những event bị thiếu.
- Business requirement chấp nhận khoảng ngắt ngắn giữa DB state và Kafka event.
- Event có idempotency key và có quy trình recovery rõ ràng.
- Có metric/alert riêng cho việc Kafka commit thất bại sau DB commit.

Nhưng với event quan trọng cho thanh toán, vận chuyển, fulfillment, ledger hay data pipeline không được phép mất business event, **outbox thường an toàn hơn**. Nó chuyển “ý định phát event” thành dữ liệu bền vững nằm ngay trong primary DB commit.

Đừng chọn DB-first đồng bộ chỉ vì muốn ít bảng hơn nếu không có cách phục hồi trường hợp DB đã commit nhưng Kafka không có event.

## 12. Recovery và reconciliation khi có partial commit

Nếu đang vận hành DB-first không có outbox và gặp Kafka commit failure, hướng xử lý không phải đơn giản là rollback DB đã commit. Cần có quy trình cụ thể:

1. **Ghi nhận trạng thái:** correlation ID, order ID, thời điểm DB commit, Kafka transaction ID và exception.
2. **Phân loại kết quả Kafka:** commit thất bại chắc chắn hay **không biết kết quả** do timeout/network?
3. **Tra cứu event ID:** xác định event đã có downstream hay chưa qua tracking đáng tin cậy; không suy ra chỉ từ việc ứng dụng ném exception.
4. **Khôi phục từ source of truth:** dựng lại event từ DB state hoặc một event ledger/outbox bền vững nếu có.
5. **Publish lại với cùng event ID**, kèm deduplication ở consumer.
6. **Đối soát trạng thái:** quan sát tiến độ Kafka consumers và xác nhận downstream đã áp dụng event.

Nếu database chỉ lưu trạng thái hiện tại, dựng lại chính xác event lịch sử có thể không thực hiện được. Ví dụ, trạng thái order đã thay đổi nhiều lần; sau sự cố, đọc trạng thái mới nhất không đủ để tạo lại event “đơn hàng chuyển từ NEW sang PAID lúc nào”. Đây là một lý do mạnh để lưu outbox/event history bền vững ngay khi transaction diễn ra.

### 12.1. Đừng retry HTTP command một cách mù quáng

Nếu client nhận HTTP 500 vì Kafka commit thất bại **sau khi DB commit**, client có thể gửi lại request. Nếu command tạo order không có unique business key hoặc idempotency key, ứng dụng có thể tạo hai order.

Nên thiết kế API write với idempotency key, unique constraints và khả năng trả về kết quả của command đã xử lý. Việc reply lỗi sau DB commit cần được diễn giải là “trạng thái tổng thể chưa chắc chắn”, không có nghĩa DB chưa thay đổi.

## 13. Commit order và rollback của listener container

Trong luồng Kafka listener transactional:

- Kafka transaction của container quản lý output Kafka và offset consumer khi cấu hình đúng.
- DB transaction do service khác quản lý có thể commit **trước** Kafka transaction.
- Nếu business service ném exception, DB transaction rollback, listener exception có thể làm Kafka transaction rollback.
- Nếu DB commit thành công nhưng Kafka transaction bị abort, record đầu vào có thể được giao lại và cần idempotency.
- `AfterRollbackProcessor` hỗ trợ seek/recovery sau Kafka rollback, nhưng **không rollback DB commit đã hoàn tất**.

Với poison record, DLT recovery có thể giúp Kafka offset tiến tiếp. Tuy nhiên, trước khi chuyển record sang DLT, phải kiểm tra DB đã ghi hiệu ứng gì hay chưa. Nếu DB đã commit nhưng Kafka offset chưa commit, replay từ DLT và redelivery từ main topic có thể tạo xử lý lặp.

Kafka exactly-once semantics bảo vệ ranh giới Kafka; database transaction không tự trở thành thành viên của cùng transaction coordinator.

## 14. Tại sao không dùng ChainedKafkaTransactionManager?

Một số mã Spring Kafka cũ sử dụng `ChainedKafkaTransactionManager` hoặc cách chain các transaction manager để đặt thứ tự commit. Cách chain này **không phải distributed two-phase commit** và không thể loại bỏ khoảng trống khi resource đầu đã commit nhưng resource sau lỗi.

`ChainedKafkaTransactionManager` đã bị deprecated trong hệ sinh thái Spring Kafka. Với ứng dụng mới, nên xem xét transaction synchronization được hỗ trợ hoặc kiến trúc outbox, thay vì coi chained manager là giải pháp exactly-once giữa Kafka và database.

Chained commit order có thể làm workflow thuận tiện về lifecycle, nhưng không nên bị hiểu nhầm thành bảo đảm atomicity end-to-end.

## 15. Quan sát DB-first trong production

Hệ thống cần phân biệt ít nhất ba trạng thái:

~~~text
BUSINESS_DB_COMMITTED
KAFKA_EVENT_COMMITTED
DOWNSTREAM_PROCESSED
~~~

Một request có thể đạt trạng thái đầu tiên nhưng chưa đạt trạng thái thứ hai; event Kafka có thể commit nhưng downstream chưa xử lý. Do đó, metric “request successful” không đủ để kết luận pipeline end-to-end khỏe mạnh.

Các tín hiệu nên theo dõi:

| Tín hiệu | Ý nghĩa |
|---|---|
| DB commit success/error | Primary transaction có bền vững hay không. |
| Kafka transaction commit error | Có lỗi ở bước secondary Kafka commit. |
| Unknown Kafka commit outcome | Cần reconciliation, tránh resend không idempotent. |
| Outbox pending count và oldest age | Số event chờ publish và độ trễ dài nhất. |
| Outbox publish/retry/DLT rate | Khả năng chuyển event từ DB sang Kafka. |
| Consumer lag theo topic/partition | Downstream có theo kịp dữ liệu hay không. |
| Duplicate event/business command rate | Idempotency key và deduplication có hoạt động không. |
| Reconciliation discrepancies | DB state và event stream lệch nhau ở đâu. |

Log/trace nên có `orderId`, `eventId`, `transactionName`, Kafka topic/partition khi biết, và trạng thái từng bước. Không log payload nhạy cảm. Cẩn thận với metric label dùng event ID vì cardinality có thể rất lớn; event ID phù hợp hơn trong structured logs hoặc traces.

Đừng chỉ log `KafkaTemplate.send()` success rồi kết luận Kafka transaction commit đã thành công. Cần đo đúng commit boundary.

## 16. Kiểm thử thứ tự commit và các failure windows

Dùng database thật trong Testcontainers và Kafka broker thật để kiểm tra semantics. Unit test chỉ mock `JdbcTemplate` và `KafkaTemplate` không thể chứng minh thứ tự commit của resource.

Các tình huống tích hợp có giá trị:

1. **Happy path:** DB có order; consumer `read_committed` nhận `OrderCreated` sau Kafka commit.
2. **DB rollback:** cố tình làm SQL/validation thất bại trước commit; xác nhận không có Kafka event committed.
3. **Kafka failure sau DB commit:** mô phỏng Kafka commit thất bại ở cửa sổ sau primary DB commit; xác nhận DB vẫn có order và exception được báo theo version.
4. **Process crash tại cửa sổ commit:** dừng process sau DB commit nhưng trước Kafka commit; kiểm tra nhu cầu reconciliation/outbox.
5. **Unknown outcome:** gây mất kết nối tại thời điểm Kafka commit; kiểm tra retry/recovery không tạo business duplicate.
6. **Consumer redelivery:** DB commit thành công nhưng Kafka listener transaction/offset commit thất bại; xác nhận inbox unique key chặn cập nhật lần hai.
7. **Outbox publisher crash:** Kafka đã nhận event nhưng row outbox chưa được đánh dấu published; xác nhận publish lại giữ event ID và downstream idempotent.
8. **Nhiều outbox workers:** tranh chấp cùng row; xác nhận locking/claim tránh double work không cần thiết.
9. **Schema/serializer lỗi:** event không serialize được; xác nhận không đánh mất outbox row hoặc trạng thái lỗi rõ ràng.
10. **Rollout/rollback:** phiên cũ và mới chạy đồng thời; vẫn đọc được outbox/event và hoạt động với schema version mong đợi.

Để xác nhận “DB commit trước Kafka commit”, có thể gắn hook/log quan sát các transaction lifecycle events hoặc tạo failure injection có kiểm soát tại secondary commit. Không dựa chỉ vào thứ tự hai dòng `jdbc.update()` và `kafkaTemplate.send()` trong source.

Test nên dùng timeout hữu hạn, chờ điều kiện cụ thể và không dựa vào `Thread.sleep()` dài. Với Kafka transaction, consumer kiểm tra nên dùng `read_committed` để tránh hiểu nhầm record chưa commit hoặc bị abort.

## 17. Các sai lầm thường gặp

- **Cho rằng `@Transactional` bao phủ cả database và Kafka như XA transaction:** transaction manager chỉ có phạm vi resource và synchronization được cấu hình.
- **Đồng nhất send acknowledgment với Kafka commit:** send được broker ack chưa có nghĩa transaction hoàn tất.
- **Không xét lỗi sau DB commit:** secondary Kafka commit failure không làm database tự rollback.
- **Bắt Kafka commit exception rồi trả về “DB đã rollback”:** phản ánh sai trạng thái durable.
- **Retry command mà thiếu idempotency key:** DB operation có thể chạy lại dù lần đầu đã commit.
- **Nghĩ outbox bảo đảm exactly-once publish tuyệt đối:** publisher có thể gửi lại khi crash sau Kafka ack nhưng trước đánh dấu sent.
- **Chỉ tăng Kafka retry/backoff khi DB/Kafka lệch:** thiếu event bền vững để phục hồi thì retry không tự giải quyết mọi failure window.
- **Dùng Kafka-first và coi đó là chữa DB-first:** thứ tự đảo ngược chỉ tạo failure window ngược lại.
- **Đổi `transaction-id-prefix` tùy tiện trên mọi replica:** có thể dẫn đến producer fencing nếu cùng full transactional ID.
- **Không dùng `read_committed` khi kiểm thử transaction visibility:** đọc output bị abort và kết luận sai.
- **Commit DB trong consumer nhưng không chống redelivery:** offset Kafka chưa commit có thể khiến business state bị áp dụng lặp.
- **Chỉ lưu DB current state mà không lưu event intent:** sau sự cố khó dựng lại chính xác event lịch sử.
- **Tưởng ChainedKafkaTransactionManager làm 2PC:** chaining không tạo atomic cross-resource commit.

## 18. Chọn DB-first cho production

Trước khi triển khai một workflow ghi DB và phát Kafka, cần làm rõ:

- Database hay Kafka là source of truth của nghiệp vụ?
- Secondary Kafka commit có thể thất bại sau DB commit không? **Có**, vậy recovery ở đâu?
- Nếu Kafka commit outcome không rõ, event ID và deduplication có đủ không?
- Nếu process chết ngay sau DB commit, có dữ liệu bền vững nào cho phép publish event còn thiếu?
- Nếu input Kafka được giao lại, DB operation có thể áp dụng lặp không?
- Transaction manager nào thực sự là primary trong `@Transactional`?
- Kafka producer có đang dùng transactional producer factory và listener có đúng transaction context không?
- Lỗi secondary commit được đưa vào logging, alert và reconciliation như thế nào?
- Có cần transactional outbox và inbox để đáp ứng SLA/độ bền dữ liệu?
- Đã có integration test cho partial commit, unknown outcome, restart và duplicate processing chưa?

**DB-first commit order** là một lựa chọn nhất quán về thứ tự: database commit trước, Kafka commit sau. Nó đơn giản hóa việc ưu tiên database làm nguồn sự thật, nhưng không làm hai resource commit nguyên tử. Đối với các sự kiện nghiệp vụ cần bảo đảm không bị thất lạc khi process hoặc Kafka gặp lỗi, hãy coi **transactional outbox, reconciliation và idempotent consumers** là thành phần kiến trúc chính chứ không phải bước vá lỗi tùy chọn.
