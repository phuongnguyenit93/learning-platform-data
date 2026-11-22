# Thứ tự commit Kafka và database

## 1. Vì sao thứ tự commit quan trọng?

Một nghiệp vụ thường vừa thay đổi dữ liệu trong database vừa gửi sự kiện lên Kafka. Ví dụ, khi khách hàng đặt hàng, ứng dụng cần lưu đơn hàng vào database và phát `OrderCreated` để các dịch vụ thanh toán, kho hàng hoặc thông báo tiếp tục xử lý.

Hai hệ thống có hai cơ chế commit độc lập:

- Database commit transaction của JDBC/JPA.
- Kafka commit producer transaction để công bố record; với consumer transaction, Kafka còn có thể commit offset cùng các record được gửi ra.

Nếu hai commit không nằm trong một distributed transaction thực sự, luôn có một khoảng thời gian mà một hệ thống đã commit còn hệ thống kia chưa commit. Thứ tự commit quyết định trạng thái có thể xuất hiện khi ứng dụng hoặc một hệ thống gặp lỗi giữa hai bước.

Với Spring Kafka, transaction synchronization cho phép phối hợp thứ tự commit giữa transaction manager của database và Kafka. Cơ chế này hữu ích, nhưng bản thân nó không biến hai resource manager thành một transaction nguyên tử toàn cục. Muốn hiểu đúng hành vi, cần xem thứ tự commit và các failure window.

## 2. Hai thứ tự commit cơ bản

Khi một service vừa cập nhật database vừa gửi record bằng `KafkaTemplate`, có hai lựa chọn chính:

1. **Database commit trước, Kafka commit sau (DB-first).** Database là transaction chính; Kafka transaction được đồng bộ và commit sau khi database commit thành công.
2. **Kafka commit trước, database commit sau (Kafka-first).** Database transaction bên ngoài; một transaction Kafka lồng bên trong được commit trước khi phương thức ngoài kết thúc.

```text
DB-first
  Begin DB transaction
       |
       +-- update database
       +-- send Kafka record (Kafka transaction được đồng bộ)
       |
  Commit database
       |
  Commit Kafka transaction
       |
  Return

Kafka-first
  Begin DB transaction
       |
       +-- update database
       +-- Begin Kafka transaction (nested method)
       |       |
       |       +-- send Kafka record
       |       +-- Commit Kafka transaction
       |
  Commit database
       |
  Return
```

Không có lựa chọn nào tự loại bỏ mọi trạng thái lệch giữa database và Kafka. DB-first ưu tiên tránh công bố sự kiện khi database chưa commit; Kafka-first ưu tiên chỉ commit database sau khi Kafka đã nhận sự kiện. Lựa chọn phụ thuộc vào hậu quả nghiệp vụ mà hệ thống muốn ưu tiên.

## 3. DB-first: database commit trước Kafka

Đây là thứ tự mặc định khi dùng transaction manager của database làm transaction chính và để `KafkaTemplate` tham gia transaction synchronization.

Ví dụ service:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderApplicationService(
            OrderRepository orderRepository,
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.orderRepository = orderRepository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("transactionManager")
    public void createOrder(Order order) {
        orderRepository.save(order);

        OrderCreated event = new OrderCreated(
                order.getId(), order.getCustomerId(), order.getTotal());

        kafkaTemplate.send("orders", order.getId(), event);
    }
}
```

Trong ví dụ, `transactionManager` là transaction manager của database (ví dụ `JpaTransactionManager` hoặc `DataSourceTransactionManager`). Kafka producer factory phải hỗ trợ transaction và `KafkaTemplate` phải dùng cùng `ProducerFactory` được cấu hình transactional.

Với Spring Boot, có thể bật Kafka producer transaction bằng:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: order-service-${INSTANCE_ID:local}-
```

Khi có `transaction-id-prefix`, Spring Boot cấu hình producer factory có khả năng transaction và `KafkaTransactionManager` tương ứng. Mỗi application instance cần prefix duy nhất để tránh các producer fencing lẫn nhau. Nếu tự cấu hình producer factory, hãy đặt transaction ID prefix duy nhất và dùng đúng factory cho `KafkaTemplate`.

Trong transaction DB-first, khi phương thức kết thúc bình thường, Spring commit database trước. Kafka transaction được đồng bộ và commit sau đó. Nếu database rollback, Kafka transaction đồng bộ cũng được rollback.

### Failure window của DB-first

Giả sử database commit thành công nhưng Kafka commit thất bại:

```text
Database: COMMITTED
Kafka:    COMMIT FAILED
```

Kết quả là đơn hàng đã tồn tại trong database nhưng `OrderCreated` chưa được công bố. Các dịch vụ downstream không biết đơn hàng mới đã được tạo. Đây là trạng thái **database có dữ liệu nhưng thiếu sự kiện**.

Từ Spring Kafka 2.5.17, 2.6.12, 2.7.9 và 2.8.0, lỗi commit của synchronized transaction sau khi transaction chính đã commit được ném về caller. Ở các phiên bản cũ hơn, lỗi này từng chỉ được log ở mức debug. Dù exception được ném, database đã commit nên không thể trông chờ rollback DB tự động; ứng dụng cần cơ chế bù hoặc đối soát.

DB-first phù hợp khi ưu tiên không phát sự kiện cho một thay đổi database chưa được xác nhận. Nhưng vẫn cần giải quyết trường hợp DB đã commit còn Kafka chưa commit.

## 4. Kafka-first: Kafka commit trước database

Nếu muốn Kafka commit trước, Spring Kafka hướng dẫn dùng hai phương thức `@Transactional` lồng nhau: phương thức ngoài sử dụng database transaction manager, phương thức trong sử dụng `KafkaTransactionManager`.

Khai báo Kafka transaction manager dùng cùng producer factory với template:

```java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

Phương thức ngoài giữ DB transaction:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OrderEventPublisher eventPublisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            OrderEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional("transactionManager")
    public void createOrder(Order order) {
        orderRepository.save(order);
        eventPublisher.publish(new OrderCreated(
                order.getId(), order.getCustomerId(), order.getTotal()));
    }
}
```

Phương thức trong mở và commit Kafka transaction:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(OrderEvent event) {
        kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

Hai service được tách riêng để lời gọi `eventPublisher.publish()` đi qua Spring proxy và transaction interceptor. Nếu gọi một phương thức `@Transactional` khác trong cùng object bằng `this.publish()`, proxy mặc định không chặn lời gọi nội bộ; transaction Kafka có thể không được mở như mong đợi.

Khi phương thức `publish()` kết thúc, Kafka transaction commit. Sau khi lời gọi này trả về, phương thức ngoài mới kết thúc và DB transaction commit. Đây là thứ tự Kafka-first.

### Failure window của Kafka-first

Nếu Kafka commit thành công nhưng database commit thất bại:

```text
Kafka:    COMMITTED
Database: COMMIT FAILED / ROLLED BACK
```

Sự kiện `OrderCreated` đã xuất hiện với consumer, nhưng đơn hàng không tồn tại hoặc không được lưu trong database. Consumer có thể thực hiện side effect dựa trên một sự kiện mà nguồn dữ liệu chính không xác nhận.

Kafka-first có thể phù hợp nếu việc công bố sự kiện là điều kiện tiên quyết trước khi chốt DB, nhưng thường rất nguy hiểm nếu downstream coi sự kiện là sự thật cuối cùng. Cần thiết kế consumer chịu được sự kiện đến trước trạng thái DB hoặc có cơ chế bù.

## 5. So sánh các failure window

| Tình huống | DB-first | Kafka-first |
|---|---|---|
| DB commit thất bại | Kafka transaction được rollback; không công bố event | Kafka có thể đã commit trước; event có thể tồn tại dù DB rollback |
| Kafka commit thất bại | DB đã commit; thiếu event | Kafka chưa commit; DB transaction ngoài có thể rollback nếu lỗi truyền ngược về trước khi commit DB |
| Process dừng giữa hai commit | DB có thể đã commit nhưng Kafka chưa commit | Kafka có thể đã commit nhưng DB chưa commit |
| Downstream đọc event | Chỉ sau khi Kafka commit; DB đã commit trước | Có thể đọc event trước khi DB commit |
| Hành động bù | Phát lại event dựa trên dữ liệu DB | Hủy/compensate event hoặc sửa downstream state |

Bảng này giả định lỗi được truyền qua transaction boundary và các transaction manager hoạt động đúng cấu hình. Mất kết nối, timeout hoặc kết quả commit không xác định có thể khiến caller không biết chắc broker/database đã commit hay chưa. Cần đối soát bằng định danh nghiệp vụ thay vì suy luận chỉ từ exception phía client.

## 6. Transaction synchronization không phải distributed atomic commit

Spring transaction synchronization phối hợp callback commit/rollback của các transaction manager, nhưng không cung cấp một transaction coordinator có khả năng commit hoặc rollback nguyên tử cả database và Kafka như một global transaction XA.

Điều này có nghĩa:

- Hai resource vẫn có transaction riêng và commit riêng.
- Spring chọn thứ tự commit và thông báo lỗi khi một bước thất bại.
- Nếu resource thứ nhất đã commit, resource thứ hai thất bại thì không thể rollback ngược resource thứ nhất bằng một lệnh rollback thông thường.
- Exception trả về cho caller không đồng nghĩa mọi resource đều đã rollback.
- Cần idempotency, đối soát, compensation hoặc outbox/inbox để xử lý khoảng lệch.

Vì vậy, cách gọi thường gặp là **Best Efforts 1PC**: hệ thống cố gắng phối hợp hai local transaction theo thứ tự đã chọn, nhưng không đạt atomic commit toàn cục. Không mô tả cơ chế này là “DB và Kafka commit nguyên tử tuyệt đối”.

## 7. Cấu hình transaction manager và ProducerFactory

Để Kafka transaction tham gia được Spring transaction:

1. `DefaultKafkaProducerFactory` phải được cấu hình `transactionIdPrefix`.
2. `KafkaTemplate` phải dùng producer factory có khả năng transaction.
3. `KafkaTransactionManager` phải dùng chính producer factory đó.
4. Nếu đồng bộ với DB transaction manager, không tạo nhiều producer factory khác nhau cho template và transaction manager.
5. Với nhiều instance, mỗi instance phải có `transactionIdPrefix` riêng biệt.

Ví dụ cấu hình producer cơ bản:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-${INSTANCE_ID:local}-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

Nếu dùng Spring Boot auto-configuration, kiểm tra bean `KafkaTemplate`, producer factory và transaction manager được auto-configure. Nếu tự khai báo bean, phải đảm bảo chúng dùng chung producer factory. Không khai báo một `KafkaTransactionManager` với factory khác template đang gửi record.

Khi producer factory transactional, các lần gửi bằng template cần nằm trong transaction do `@Transactional`, `TransactionTemplate`, listener container hoặc `executeInTransaction()` mở. Gọi template ngoài transaction có thể ném `IllegalStateException`, trừ khi cấu hình `allowNonTransactional` cho phép gửi non-transactional.

## 8. Thứ tự commit khi consumer nhận record rồi cập nhật database

Một luồng phổ biến khác là consumer đọc event, cập nhật database và commit offset Kafka. Khi muốn commit kết quả DB và offset cùng một quy trình, có thể để listener container mở Kafka transaction, sau đó listener method mở DB transaction.

Với Kafka transaction do container khởi tạo:

1. Container bắt đầu Kafka transaction.
2. Listener nhận record và gọi service có `@Transactional` với DB transaction manager.
3. DB transaction commit khi phương thức listener kết thúc thành công.
4. Container commit Kafka transaction; offset được gửi trong transaction này.

Ví dụ listener:

```java
@Component
public class PaymentListener {

    private final PaymentApplicationService paymentService;

    public PaymentListener(PaymentApplicationService paymentService) {
        this.paymentService = paymentService;
    }

    @KafkaListener(topics = "orders", groupId = "payment-service")
    public void onOrder(OrderCreated event) {
        paymentService.createPayment(event);
    }
}
```

Service cập nhật DB:

```java
@Service
public class PaymentApplicationService {

    private final PaymentRepository paymentRepository;

    public PaymentApplicationService(PaymentRepository paymentRepository) {
        this.paymentRepository = paymentRepository;
    }

    @Transactional("transactionManager")
    public void createPayment(OrderCreated event) {
        paymentRepository.save(Payment.pendingFor(event.orderId()));
    }
}
```

Container cần được cấu hình dùng `KafkaTransactionManager`; với Spring Boot và `spring.kafka.producer.transaction-id-prefix`, Boot có thể auto-configure transaction manager và wiring vào listener container. Nếu tự cấu hình factory, đặt Kafka-aware transaction manager vào `ContainerProperties` theo API của phiên bản Spring Kafka đang dùng.

Trong mô hình này, DB commit trước Kafka transaction/offset commit. Nếu DB commit thất bại, exception làm Kafka transaction rollback và offset không được commit, record có thể được giao lại. Nếu DB commit thành công nhưng Kafka transaction commit thất bại, record có thể được giao lại dù DB đã có payment. Vì vậy `createPayment()` phải idempotent, chẳng hạn có unique constraint trên `orderId` hoặc event ID.

Không dùng non-blocking retry topic cùng container transaction. Spring Kafka không hỗ trợ kết hợp non-blocking retry với container transaction theo cách này; khi listener ném exception, container transaction có thể commit và record được chuyển sang retry topic. Chọn retry strategy phù hợp với transaction model.

## 9. Vì sao không nên phụ thuộc vào ChainedKafkaTransactionManager?

`ChainedKafkaTransactionManager` đã deprecated từ Spring Kafka 2.7. Nó dựa trên `ChainedTransactionManager` để gọi nhiều transaction manager theo thứ tự, nhưng không biến chúng thành một global transaction nguyên tử.

Khi một transaction manager đã commit và transaction manager kế tiếp thất bại, hệ thống vẫn có partial commit. Vì vậy, không nên dùng `ChainedKafkaTransactionManager` như lời giải đảm bảo DB và Kafka luôn cùng commit hoặc cùng rollback.

Với ứng dụng mới:

- Producer-only flow: dùng transaction synchronization với transaction manager chính và chọn thứ tự DB-first hoặc nested Kafka-first có chủ đích.
- Consumer-initiated flow: để container dùng `KafkaTransactionManager`, listener method dùng transaction manager của database.
- Nếu cần độ tin cậy cao giữa DB và Kafka: ưu tiên transactional outbox/inbox cùng idempotency.

Nếu đang duy trì ứng dụng cũ dùng `ChainedKafkaTransactionManager`, cần kiểm tra thứ tự manager, failure window và cách xử lý partial commit trước khi nâng cấp. Không thay thế máy móc mà bỏ qua semantics offset và retry của listener container.

## 10. Transactional outbox: giải pháp phổ biến cho DB và Kafka

Nếu yêu cầu nghiệp vụ là “database đã lưu thay đổi thì sự kiện chắc chắn sẽ được phát”, transactional outbox thường là thiết kế phù hợp hơn việc chọn DB-first hay Kafka-first.

Trong một database transaction duy nhất, ứng dụng:

1. Cập nhật bảng nghiệp vụ, ví dụ `orders`.
2. Thêm một dòng vào bảng `outbox_events` chứa event ID, aggregate ID, event type, payload và thời điểm tạo.
3. Commit database transaction.

Một relay process hoặc CDC connector đọc outbox và publish event sang Kafka. Khi gửi thành công, relay đánh dấu bản ghi đã phát hoặc dựa trên offset/CDC log để tiếp tục.

```text
Application command
       |
       v
Begin DB transaction
       |
       +---- UPDATE orders
       |
       +---- INSERT outbox_events
       |
       v
Commit DB transaction
       |
       v
Outbox relay / CDC connector
       |
       v
Publish to Kafka
       |
       v
Consumer services
```

Nếu DB transaction rollback, cả thay đổi nghiệp vụ và outbox row đều không tồn tại. Nếu DB commit thành công nhưng relay tạm dừng, outbox row vẫn còn để relay phát sau khi phục hồi. Điều này loại bỏ failure window “DB đã commit nhưng chưa có thông tin cần phát” trong transaction của ứng dụng.

Outbox relay vẫn có thể publish trùng nếu gửi Kafka thành công nhưng process dừng trước khi đánh dấu outbox row đã gửi. Do đó, outbox thường cung cấp **at-least-once publication**; consumer cần idempotent theo `eventId`. Nếu cần ordering theo aggregate, relay phải phân vùng/đọc outbox theo aggregate key và duy trì thứ tự phát phù hợp.

### Ví dụ bảng outbox

```sql
CREATE TABLE outbox_events (
    event_id       VARCHAR(100) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(150) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);
```

Ghi nghiệp vụ và outbox trong cùng transaction:

```java
@Transactional("transactionManager")
public void createOrder(Order order) {
    orderRepository.save(order);

    OrderCreated event = OrderCreated.from(order);
    String payload;
    try {
        payload = objectMapper.writeValueAsString(event);
    } catch (JsonProcessingException exception) {
        throw new IllegalStateException("Cannot serialize outbox event", exception);
    }

    outboxRepository.save(OutboxEvent.pending(
            event.eventId(),
            "Order",
            order.getId(),
            "OrderCreated",
            payload));
}
```

Relay có thể được triển khai bằng worker polling có khóa/claim row hoặc CDC như Debezium Outbox Event Router. Cần quản lý retry, lease/claim, cleanup, retention và khả năng phát lại. Không để hai relay cùng publish một dòng mà không có cơ chế claim hoặc deduplication.

## 11. Inbox và idempotency ở consumer

Outbox giảm rủi ro mất sự kiện ở phía producer, nhưng relay có thể gửi trùng. Consumer nên bảo đảm xử lý idempotent bằng `eventId`.

Một mẫu phổ biến là bảng inbox:

```sql
CREATE TABLE processed_events (
    event_id     VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Trong cùng DB transaction với side effect nghiệp vụ:

```java
@Transactional("transactionManager")
public void handle(OrderCreated event) {
    boolean firstDelivery = processedEventRepository
            .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    paymentRepository.createPendingPayment(event.orderId());
}
```

`insertIfAbsent` cần được triển khai bằng unique constraint và câu lệnh atomic phù hợp database (ví dụ `INSERT ... ON CONFLICT DO NOTHING` ở PostgreSQL). Không dùng mô hình “SELECT rồi INSERT” không khóa vì hai consumer song song có thể cùng thấy event chưa tồn tại.

Nếu DB transaction commit nhưng Kafka offset chưa commit, record sẽ được giao lại. Inbox phát hiện event đã xử lý và không lặp side effect. Sau đó listener hoàn tất để container commit offset.

Inbox không bảo vệ được side effect ngoài database nếu side effect đó không cùng transaction hoặc không có idempotency key riêng. Ví dụ gọi cổng thanh toán, gửi email hoặc gọi HTTP cần dùng idempotency key do downstream hỗ trợ hoặc thêm outbox cho lệnh gọi.

## 12. Exactly-once có giải quyết commit DB và Kafka không?

Kafka exactly-once semantics (EOS) có thể bảo đảm luồng consume-transform-produce trong Kafka khi output records và consumed offsets được commit trong cùng Kafka transaction. Consumer dùng `isolation.level=read_committed` để chỉ đọc record đã commit.

EOS của Kafka không tự mở rộng sang database transaction. Khi listener vừa ghi DB vừa commit Kafka offset, DB và Kafka vẫn là hai resource độc lập. Nếu DB commit thành công rồi Kafka commit thất bại, record có thể được giao lại và DB side effect có thể lặp.

Vì vậy:

- Kafka transaction bảo vệ tính nguyên tử giữa các record được gửi vào Kafka và offset Kafka tham gia transaction.
- Database transaction bảo vệ các thay đổi trong database.
- Transaction synchronization chọn thứ tự và phối hợp callback commit.
- Outbox/inbox/idempotency giải quyết phần lệch giữa hai resource trong thực tế.

Không gọi một workflow DB + Kafka là exactly-once chỉ vì nó dùng `@Transactional` và `KafkaTransactionManager`. Hãy mô tả chính xác ranh giới đảm bảo và cách xử lý duplicate.

## 13. Chọn thứ tự commit theo yêu cầu nghiệp vụ

| Yêu cầu ưu tiên | Hướng phù hợp | Điều phải xử lý |
|---|---|---|
| Không phát event nếu DB chưa commit | DB-first hoặc transactional outbox | DB commit xong nhưng Kafka chưa commit; outbox thường bền vững hơn |
| Kafka phải nhận event trước khi DB chốt | Kafka-first | Event có thể được consumer thấy dù DB rollback |
| Consumer cập nhật DB rồi commit offset | Container Kafka transaction + DB transaction trong listener | DB commit trước Kafka offset; cần inbox/idempotency khi redelivery |
| Không chấp nhận mất event sau DB commit | Transactional outbox | Relay retry và consumer deduplication |
| Cần phối hợp nhiều service qua nhiều bước | Saga/compensation kết hợp outbox | Thiết kế trạng thái, timeout và hành động bù |

Trong phần lớn hệ thống nghiệp vụ, transactional outbox cùng consumer idempotency dễ vận hành và phục hồi hơn việc cố gắng chọn một thứ tự commit để che hết failure window.

## 14. Saga và compensation khi hai hệ thống lệch trạng thái

Khi không thể commit database và Kafka nguyên tử, một cách xử lý là chấp nhận các bước nghiệp vụ riêng và định nghĩa hành động bù.

Ví dụ quy trình đặt hàng:

1. Order service lưu đơn hàng trạng thái `PENDING` và outbox event `OrderCreated`.
2. Payment service nhận event, tạo payment intent idempotent.
3. Nếu thanh toán thành công, Payment service phát `PaymentAuthorized`.
4. Nếu thanh toán thất bại, Payment service phát `PaymentRejected`.
5. Order service chuyển đơn hàng sang `CONFIRMED` hoặc `CANCELLED` theo event.

Mỗi bước cập nhật database và outbox trong một local transaction. Saga không rollback transaction đã commit ở service khác; nó phát hành hành động bù, ví dụ hủy reservation hoặc hoàn tiền. Cần dùng event ID, correlation ID, timeout và trạng thái saga để xử lý duplicate/out-of-order.

## 15. Kiểm thử thứ tự commit và failure window

Không chỉ kiểm thử trường hợp thành công. Cần chủ động tạo lỗi giữa hai commit để xác minh hệ thống có thể phục hồi:

1. **DB-first thành công:** xác nhận row DB tồn tại và event xuất hiện trong Kafka sau commit.
2. **DB rollback:** gây exception trước khi DB commit; xác nhận Kafka transaction đồng bộ không công bố event.
3. **Kafka commit lỗi sau DB commit:** mô phỏng broker unavailable hoặc lỗi commit; xác nhận DB vẫn đã commit và ứng dụng ghi nhận trạng thái cần đối soát.
4. **Kafka-first thành công:** xác nhận Kafka commit hoàn tất trước khi DB commit.
5. **DB commit lỗi sau Kafka commit:** mô phỏng constraint violation hoặc DB outage; xác nhận event có thể đã tồn tại và kiểm tra hành động bù.
6. **Listener DB commit lỗi:** xác nhận Kafka container transaction rollback và offset không được commit.
7. **Listener Kafka commit lỗi sau DB commit:** xác nhận record có thể redeliver và inbox/idempotency ngăn side effect lặp.
8. **Outbox relay dừng sau publish:** xác nhận cùng event có thể được publish lại và consumer deduplicate theo event ID.
9. **Nhiều instance:** xác nhận transaction ID prefix không trùng và không phát sinh producer fencing ngoài dự kiến.
10. **Restart/rebalance:** xác nhận offset, transaction recovery và side effect sau redelivery đúng chính sách.

Trong integration test, dùng Kafka broker thật hoặc Testcontainers Kafka cùng database test. Kiểm tra cả trạng thái DB và record Kafka, không chỉ kiểm tra method ném exception. Với lỗi commit không xác định, cần kiểm tra trạng thái cuối bằng event ID hoặc business key.

## 16. Quan sát và vận hành

Nên ghi nhận:

- Kết quả commit DB và Kafka, bao gồm exception từ synchronized transaction.
- Kafka transaction abort/commit, producer fencing và transaction timeout.
- Số outbox row pending, tuổi của row lâu nhất và tốc độ relay publish.
- Số lần publish trùng hoặc inbox duplicate được bỏ qua.
- Consumer lag, redelivery và số lần listener rollback.
- Số saga đang chờ, timeout và compensation thất bại.

Log nên chứa `eventId`, `aggregateId`, correlation ID, transaction flow, topic, partition và offset nếu có. Không ghi payload nhạy cảm hoặc thông tin xác thực vào log. Metric tag chỉ nên dùng giá trị cardinality thấp như topic, listener và outcome; không dùng event ID hoặc offset làm tag.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| DB commit xong nhưng không thấy event | DB-first và Kafka commit sau đó thất bại | Đối soát bằng event ID; dùng outbox để giữ yêu cầu phát event bền vững |
| Consumer thấy event nhưng không tìm thấy row DB | Kafka-first và DB commit sau đó thất bại | Thiết kế compensation hoặc chọn DB-first/outbox |
| `KafkaTemplate` báo không có transaction | ProducerFactory chưa có `transactionIdPrefix` hoặc send ngoài transaction | Bật transactional producer và mở transaction phù hợp |
| KafkaTemplate và KafkaTransactionManager không cùng transaction | Dùng hai ProducerFactory khác nhau | Dùng chung một producer factory |
| Kafka producer fencing | `transactional.id`/prefix bị trùng giữa instance hoặc producer cũ còn hoạt động | Cấp prefix duy nhất cho mỗi instance và kiểm tra lifecycle producer |
| `@Transactional` lồng không tạo transaction Kafka | Gọi nội bộ trong cùng bean, không qua proxy | Tách publisher sang bean khác hoặc dùng `TransactionTemplate` |
| Record được giao lại làm DB ghi trùng | DB commit nhưng offset Kafka chưa commit | Dùng inbox, unique constraint và idempotent handler |
| Nghĩ ChainedKafkaTransactionManager bảo đảm atomicity | Chained manager chỉ điều phối thứ tự local commit | Hiểu partial commit; dùng outbox/inbox hoặc compensation |
| Dùng non-blocking retry với container transaction | Hai cơ chế không tương thích theo cách kết hợp này | Chọn blocking retry/AfterRollbackProcessor hoặc thiết kế retry topic không container transaction |

## 18. Quy trình thiết kế

1. Xác định workflow là producer gửi event sau khi ghi DB hay consumer cập nhật DB sau khi nhận event.
2. Liệt kê các trạng thái không mong muốn nếu process dừng giữa từng bước commit.
3. Nếu dùng transaction synchronization, chọn DB-first hoặc Kafka-first dựa trên hậu quả nghiệp vụ và ghi rõ failure window.
4. Xác nhận Kafka producer factory có transaction và được dùng chung bởi template/transaction manager.
5. Với consumer transaction, cấu hình container dùng KafkaTransactionManager và listener dùng DB transaction manager.
6. Dùng inbox/idempotency để xử lý redelivery và duplicate side effect.
7. Nếu cần bảo đảm DB commit luôn có event tương ứng, triển khai transactional outbox.
8. Nếu quy trình gồm nhiều service, xác định saga state và compensation.
9. Kiểm thử lỗi ở mọi điểm giữa DB commit và Kafka commit, bao gồm restart và rebalance.
10. Theo dõi outbox backlog, commit failure, duplicate và compensation để vận hành.

## 19. Tổng kết

- DB-first commit database trước rồi Kafka; lỗi Kafka sau DB commit có thể để lại dữ liệu DB nhưng thiếu event.
- Kafka-first commit Kafka trước rồi database; lỗi DB sau Kafka commit có thể để lại event không có dữ liệu nguồn tương ứng.
- Spring Kafka transaction synchronization phối hợp thứ tự commit local transaction, không tạo distributed atomic commit.
- Với consumer-initiated transaction, listener container mở Kafka transaction, listener method có thể mở DB transaction; DB commit trước Kafka transaction/offset commit nên cần idempotency khi redelivery.
- `ChainedKafkaTransactionManager` deprecated từ Spring Kafka 2.7 và không giải quyết partial commit.
- Transactional outbox ghi thay đổi nghiệp vụ và event vào cùng DB transaction, sau đó relay/CDC publish sang Kafka.
- Outbox có thể publish trùng; consumer inbox/idempotency xử lý duplicate bằng event ID và unique constraint.
- Kafka EOS bảo vệ Kafka records và offsets trong Kafka transaction; không tự mở rộng exactly-once sang database hoặc HTTP.
- Chọn thứ tự commit theo failure window, và dùng outbox/inbox/compensation khi yêu cầu nghiệp vụ cần độ tin cậy cao.

Thứ tự commit là một quyết định về trạng thái nào có thể xuất hiện khi hệ thống lỗi. Khi hiểu rõ DB-first, Kafka-first và ranh giới transaction, nhóm phát triển có thể chọn thiết kế phù hợp, kiểm thử failure window và xây dựng cơ chế phục hồi thay vì giả định hai hệ thống luôn commit cùng nhau.

## Tài liệu tham khảo

- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka Reference — Tips, Tricks and Examples](https://docs.spring.io/spring-kafka/reference/tips.html)
- [Spring Kafka API — KafkaTransactionManager](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/transaction/KafkaTransactionManager.html)
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Debezium Documentation — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
