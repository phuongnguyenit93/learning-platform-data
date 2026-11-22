# KafkaTransactionManager cùng @Transactional

Trong hệ thống Spring Kafka, một nghiệp vụ thường phải cập nhật **database** rồi phát **Kafka event**. Ví dụ dịch vụ đơn hàng lưu trạng thái `OrderCreated` vào PostgreSQL và publish một record sang topic `orders.events`. Nếu database commit nhưng Kafka publish thất bại, hệ thống có đơn hàng mà không có event. Nếu Kafka commit trước nhưng database rollback, consumer downstream lại nhìn thấy event tham chiếu một đơn hàng chưa tồn tại. Đây là một trong những bài toán cốt lõi của reliability khi phối hợp Kafka và database.

`KafkaTransactionManager` giúp Spring quản lý Kafka producer transaction theo abstraction `PlatformTransactionManager`; `@Transactional` dùng để khai báo transaction boundary trên phương thức Java được Spring quản lý. Tuy nhiên, việc sử dụng hai thành phần này **không biến Kafka và database thành một distributed atomic transaction**. Kafka và database vẫn là hai tài nguyên có commit riêng, và luôn tồn tại những cửa sổ lỗi cần được thiết kế bù trừ, đối soát hoặc tránh bằng transactional outbox.

Bài học giải thích cách cấu hình KafkaTransactionManager, lựa chọn transaction manager cho `@Transactional`, đồng bộ Kafka transaction với database transaction, phân biệt DB-first và Kafka-first, cách transactional listener container hoạt động, những cạm bẫy AOP/rollback, và cách bảo đảm độ tin cậy khi production gặp sự cố.

## 1. Ba khái niệm transaction cần phân biệt

| Cơ chế | Quản lý resource nào? | Bảo đảm | Không tự bảo đảm |
|---|---|---|---|
| Database transaction | JDBC/JPA và các thay đổi DB | DB commit/rollback nguyên tử trong DB | Kafka publish thành công |
| Kafka producer transaction | Kafka sends và, khi thiết kế đúng, consumed offsets | Các ghi Kafka cùng commit/abort | DB update, HTTP/email nằm trong cùng transaction |
| DB/Kafka synchronization | Trình tự commit giữa hai local transactions | Điều phối lifecycle theo thứ tự | Atomic distributed commit |

Ví dụ:

~~~text
                     Spring service
                            |
             +--------------+--------------+
             |                             |
             v                             v
    Database transaction             Kafka transaction
             |                             |
             v                             v
      DB COMMIT/ROLLBACK             Kafka COMMIT/ABORT

          Không có một COMMIT chung cho cả hai.
~~~

Điều quan trọng:

- `@Transactional("kafkaTransactionManager")` quản lý Kafka transaction, không tự rollback database.
- `@Transactional("transactionManager")` nếu bean đó là DB manager thì quản lý DB, không mặc nhiên biến mọi Kafka send thành cùng transaction nguyên tử.
- Một service có thể dùng cả hai, nhưng **thứ tự hai commit** quyết định failure window chứ không xóa failure window.

## 2. KafkaTransactionManager là gì?

`KafkaTransactionManager<K,V>` là transaction manager cho Kafka producer. Nó sử dụng một `ProducerFactory` đã bật transactional support để lấy producer, bắt đầu Kafka transaction và commit/abort khi transaction scope kết thúc.

Trong một flow thông thường:

1. Transaction interceptor hoặc listener container yêu cầu mở transaction.
2. KafkaTransactionManager lấy transactional producer từ producer factory.
3. Spring đồng bộ producer với transaction context của thread.
4. `KafkaTemplate` dùng producer thuộc transaction hiện hành nếu cấu hình phù hợp.
5. Transaction thành công thì commit; lỗi theo rollback rule thì abort.
6. Producer được đóng hoặc trả về cache tùy vòng đời của factory.

KafkaTransactionManager **không quản lý JDBC Connection**, JPA EntityManager hay state của một HTTP API. Nó là một local transaction manager cho Kafka.

### 2.1. Những gì Kafka transaction bao gồm

Kafka producer transaction có thể gộp nhiều record gửi đến các topic/partition Kafka. Với Kafka transactional listener container, consumed offsets cũng có thể được gửi vào cùng transaction với output records.

Ngược lại, chỉ dùng `@Transactional("kafkaTransactionManager")` cho phương thức gửi Kafka thông thường **không tự động gắn offset của một consumer Kafka bất kỳ** vào transaction. Phần commit offsets trong read-process-write phải được listener container hoặc Kafka consumer integration thực hiện đúng cách.

### 2.2. Điều kiện kỹ thuật

- Kafka cluster hỗ trợ transactions.
- ProducerFactory được cấu hình với transactional ID prefix.
- KafkaTemplate tham gia transaction qua producer factory phù hợp.
- Transactional IDs không va chạm giữa các instance đồng thời.
- Code không tự tạo KafkaProducer bên ngoài Spring factory trong đường xử lý cần transaction.

Nếu producer không transactional, cấu hình annotation trên service không tự biến nó thành transactional producer.

## 3. Cấu hình Spring Boot

Ví dụ cấu hình một producer có khả năng mở Kafka transaction:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-instance-a-
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

`spring.kafka.producer.transaction-id-prefix` giúp Spring Boot auto-configure một transactional producer factory và, khi các điều kiện thích hợp được thỏa mãn, Kafka transaction manager. Tên prefix trong ví dụ chỉ phù hợp một instance minh họa; production phải thiết kế **unique prefix per active instance**.

Ví dụ:

~~~text
instance A: orders-8f32-
instance B: orders-9b14-
instance C: orders-72a1-
~~~

Spring Kafka có thể thêm suffix cho từng transactional producer trong pool/cache. Nếu hai pod đang chạy cùng transactional ID, broker có thể fence producer cũ. Fencing bảo vệ giao dịch khỏi hai producer cùng nhận một identity; không nên bỏ qua lỗi này.

### 3.1. Custom configuration và auto-configuration

Nếu ứng dụng tự định nghĩa `ProducerFactory`, `KafkaTemplate`, `KafkaTransactionManager` hoặc listener factory, đừng mặc định Spring Boot đã áp dụng mọi property vào bean tùy chỉnh.

Cần xác nhận:

- ProducerFactory có transactional ID prefix thực tế.
- KafkaTemplate dùng đúng ProducerFactory.
- KafkaTransactionManager dùng cùng ProducerFactory phù hợp.
- Listener container có transaction manager nếu cần Kafka read-process-write EOS.
- Cả pod cũ và pod mới trong rolling deployment không tạo transactional IDs va chạm.

Kiểm tra giá trị cấu hình cuối cùng và bean wiring, không chỉ nhìn `application.yml`.

## 4. Định nghĩa KafkaTransactionManager thủ công

Nếu cần chỉ rõ bean manager:

~~~java
@Configuration
public class KafkaTxConfiguration {

    @Bean
    KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
~~~

Ví dụ trên giả định `ProducerFactory` đã được cấu hình transactional. Nếu tự tạo factory, một cách bật transaction prefix là:

~~~java
Map<String, Object> props = new HashMap<>();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class);
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class);
props.put(ProducerConfig.ACKS_CONFIG, "all");

var producerFactory =
        new DefaultKafkaProducerFactory<String, OrderEvent>(props);
producerFactory.setTransactionIdPrefix("orders-instance-a-");
~~~

Đây là đoạn minh họa API producer factory; trong ứng dụng thật cần khai báo bean, cấu hình serializer và cấp identity theo deployment. Không hardcode prefix chung cho nhiều pod.

## 5. @Transactional chọn transaction manager nào?

Trong dự án có cả database và Kafka, có thể tồn tại:

- `JpaTransactionManager` hoặc `DataSourceTransactionManager` cho DB.
- `KafkaTransactionManager` cho Kafka.

Khi chỉ viết `@Transactional` mà không có qualifier, Spring sẽ chọn default transaction manager theo configuration/bean naming/primary rules. Nếu có nhiều managers, có thể bị chọn nhầm hoặc gặp lỗi không xác định manager.

Nên khai báo rõ:

~~~java
@Transactional("kafkaTransactionManager")
public void publishEvents(...) { ... }

@Transactional("transactionManager")
public void updateDatabase(...) { ... }
~~~

`transactionManager` trong ví dụ phải là **tên bean của database manager thực tế**. Nếu ứng dụng dùng tên `jpaTransactionManager`, phải truyền đúng tên đó.

### 5.1. Mỗi @Transactional chỉ định một primary manager

Annotation không có tham số kiểu “hãy commit đồng thời cả Kafka và database”. Cho dù gọi nhiều method được annotation khác nhau, mỗi transaction manager vẫn điều khiển một resource. Muốn phối hợp phải hiểu rõ cách Spring transaction synchronization hoặc nested boundaries hoạt động.

## 6. Dùng KafkaTransactionManager cho nhiều Kafka sends

Một service chỉ cần ghi nhiều Kafka records cùng thành công/cùng abort có thể sử dụng Kafka transaction trực tiếp:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(String orderId,
                        OrderCreated created,
                        OrderAudit audit) throws Exception {

        kafkaTemplate.send(
                "orders.events", orderId, created)
                .get(10, TimeUnit.SECONDS);

        kafkaTemplate.send(
                "orders.audit", orderId, audit)
                .get(10, TimeUnit.SECONDS);
    }
}
~~~

Trong ví dụ, hai sends thuộc cùng Kafka transaction khi KafkaTemplate và manager được cấu hình đúng. Nếu method hoàn tất, transaction manager commit Kafka; nếu method ném exception theo rollback rules, transaction abort. Đây là atomicity của **Kafka outputs**, không bao gồm database.

`get(...)` giúp lỗi gửi record xuất hiện trong lời gọi service và có timeout rõ ràng. Không nhất thiết mọi send phải block trong ứng dụng thực tế, nhưng phải để exception/commit failure được quan sát và không nuốt lỗi.

### 6.1. read_committed tại consumer downstream

Consumer muốn chỉ nhìn thấy output từ Kafka transactions đã commit phải dùng:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

`read_uncommitted` có thể đọc record của transaction bị abort. Vì vậy, bật Kafka transaction ở producer nhưng downstream vẫn đọc uncommitted không cung cấp kỳ vọng “chỉ thấy output đã commit” cho toàn bộ pipeline.

Không phải mọi topic đều nhất thiết chỉ có transactional records; `read_committed` không chứng minh tất cả producers đều tuân thủ EOS.

## 7. KafkaTemplate.executeInTransaction khác gì?

Một lựa chọn khác cho Kafka-only là:

~~~java
String result = kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.events", orderId, created);
    operations.send("orders.audit", orderId, audit);
    return "submitted";
});
~~~

`executeInTransaction` mở một local Kafka transaction cho callback. Nó hữu ích khi muốn thể hiện scope transaction ngay trong code mà không dùng transaction proxy.

Nhưng cần hiểu:

- Callback là Kafka transaction riêng của template, không tự biến DB transaction thành atomic cùng Kafka.
- Không tự đưa consumed offsets của listener vào Kafka transaction.
- Không đồng nghĩa với transaction đồng bộ cùng Spring DB transaction hiện hành.
- KafkaTemplate và producer factory phải hỗ trợ transactions.
- Commit hoặc send failure vẫn phải được xử lý, không được nuốt lỗi.

Không dùng `executeInTransaction` trong một DB method chỉ vì nghĩ nó tự tạo “two-phase commit”.

## 8. Database-first với @Transactional của database

Trong một số cấu hình Spring Kafka, transactional KafkaTemplate có thể đồng bộ Kafka transaction với Spring transaction đang chạy. Khi **database transaction là primary**, ứng dụng có thể cập nhật database rồi gọi KafkaTemplate trong cùng service method:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderApplicationService(
            OrderRepository orderRepository,
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.orderRepository = orderRepository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("transactionManager")
    public void createOrder(CreateOrderCommand command) throws Exception {

        Order order = orderRepository.save(Order.from(command));
        OrderCreated event = new OrderCreated(order.getId());

        kafkaTemplate.send(
                "orders.events", order.getId(), event)
                .get(10, TimeUnit.SECONDS);
    }
}
~~~

Ví dụ giả định `transactionManager` là DB manager và KafkaTemplate đã được cấu hình để đồng bộ Kafka transaction với Spring transaction hiện hành. Nếu KafkaTemplate không transactional, send sẽ không tham gia Kafka transaction tương ứng.

### 8.1. Commit order ở database-first

~~~text
BEGIN DB transaction
        |
        v
INSERT/UPDATE orders
        |
        v
KafkaTemplate.send() trong Kafka transaction đồng bộ
        |
        v
Method returns
        |
        v
COMMIT DATABASE
        |
        v
COMMIT KAFKA TRANSACTION
~~~

Thông thường database transaction commit trước, Kafka transaction commit sau. Nếu cả hai thành công, DB row và Kafka event đều tồn tại.

### 8.2. Failure window: DB commit được nhưng Kafka commit lỗi

~~~text
DB COMMIT thành công
        |
        X crash / broker unavailable / Kafka commit lỗi
        |
Kafka output chưa được xác nhận thành công
~~~

Spring không thể rollback một DB transaction đã commit chỉ vì Kafka transaction commit ở bước sau thất bại.

Trong các dòng Spring Kafka có hành vi propagate commit failure của synchronized transaction, exception có thể được ném lên caller; nhưng dữ liệu DB đã commit vẫn giữ nguyên. Ứng dụng cần **compensation hoặc reconciliation**, hoặc tốt hơn là transactional outbox nếu không được phép mất event.

Một HTTP client retry toàn bộ `createOrder` cũng có thể tạo đơn hàng thứ hai nếu không có request id/idempotency key và uniqueness constraint.

## 9. Kafka-first với hai service beans

Một số workflow yêu cầu Kafka commit trước DB. Có thể tổ chức DB method bên ngoài gọi một Kafka method được annotation với KafkaTransactionManager ở **bean khác**:

~~~java
@Service
public class KafkaFirstPublisher {

    private final KafkaTemplate<String, OrderCreated> template;

    public KafkaFirstPublisher(
            KafkaTemplate<String, OrderCreated> template) {
        this.template = template;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(OrderCreated event) throws Exception {
        template.send(
                "orders.events", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);
    }
}

@Service
public class OrderService {
    private final OrderRepository repository;
    private final KafkaFirstPublisher publisher;

    public OrderService(
            OrderRepository repository, KafkaFirstPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional("transactionManager")
    public void create(CreateOrderCommand command) throws Exception {
        Order order = repository.save(Order.from(command));
        publisher.publish(new OrderCreated(order.getId()));
    }
}
~~~

Phương thức Kafka trên bean riêng được Spring proxy gọi, có thể tạo Kafka transaction riêng; nó commit trước khi method DB bên ngoài hoàn tất.

~~~text
BEGIN DB transaction
       |
       v
INSERT order (chưa commit)
       |
       v
BEGIN Kafka transaction
       |
       v
Kafka send
       |
       v
COMMIT KAFKA
       |
       v
COMMIT DB
~~~

Đây là Kafka-first theo cách phối hợp local transactions. Không phải XA.

### 9.1. Failure window: Kafka commit trước, DB rollback sau

Nếu Kafka commit thành công nhưng DB commit thất bại, downstream có thể thấy `OrderCreated` dù database chưa có đơn hàng. Trường hợp này nguy hiểm nếu downstream đọc DB ngay lập tức theo event.

Cần một trong các cách:

- Có compensation event rõ nghĩa.
- Downstream kiểm tra trạng thái hoặc version nghiệp vụ và retry an toàn.
- Thiết kế lại để DB là source of truth và sử dụng transactional outbox.
- Đối soát các event committed với database records.

Việc đảo thứ tự commit chỉ thay đổi phía nào chịu rủi ro; không xóa khoảng hở.

## 10. Vì sao không thể có một @Transactional cho cả hai tài nguyên?

Một service như sau không đủ để bảo đảm DB + Kafka atomic commit:

~~~java
@Transactional
public void process(OrderCommand command) {
    repository.save(...);
    kafkaTemplate.send(...);
}
~~~

Annotation không nói rõ manager nào được dùng. Nếu manager là DB manager, Kafka có thể synchronize như database-first trong điều kiện phù hợp, nhưng hai commits vẫn tách biệt. Nếu manager là Kafka manager, database không được tự động đưa vào Kafka transaction.

Một số dự án từng dùng các chained transaction managers để phối hợp resource, trong đó có API Spring Kafka cũ đã deprecated. Chained local transactions vẫn không tương đương distributed atomic transaction: resource commit trước có thể thành công trong khi resource commit sau thất bại.

Nên bắt đầu bằng câu hỏi nghiệp vụ: “Resource nào là nguồn sự thật, nếu một commit thất bại thì ai khôi phục và làm sao biết record đã phát hay chưa?”.

## 11. Transactional listener container thay đổi điều gì?

Khi listener container được cấu hình Kafka transaction manager, container bắt đầu Kafka transaction trước khi gọi `@KafkaListener`. Khi listener thành công, container gửi consumed offsets vào cùng Kafka transaction với output và commit.

~~~text
KafkaConsumer.poll()
         |
         v
Container BEGIN Kafka transaction
         |
         v
@KafkaListener reads OrderCreated
         |
         v
KafkaTemplate sends OrderProcessed
         |
         v
Container sends input offset to transaction
         |
         v
COMMIT Kafka output + input offsets
~~~

Đây là cơ sở **Kafka-to-Kafka exactly-once semantics** cho read-process-write. Output và consumed offsets được commit/abort cùng nhau trong Kafka transaction. Nhưng không đảm bảo Java listener chỉ chạy một lần: crash/rollback có thể khiến record được giao lại.

### 11.1. Gắn Kafka transaction manager vào factory

Ví dụ cho Spring Kafka có API `setKafkaAwareTransactionManager`:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
transactionalOrdersFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        KafkaAwareTransactionManager<?, ?> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);
    return factory;
}
~~~

API cụ thể có thể thay đổi theo Spring Kafka version. Trên dự án cũ có thể gặp tên setter khác. Quan trọng nhất là **listener thực sự sử dụng factory có Kafka transaction manager**, và output KafkaTemplate dùng producer factory tương thích.

### 11.2. read_committed cho downstream

Consumer downstream phải dùng `read_committed` để không nhìn thấy record của Kafka transactions bị abort:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

Không đổi sang `read_uncommitted` chỉ để thấy output sớm hơn khi đang có transaction chờ commit. Làm vậy có thể đưa aborted output vào xử lý.

## 12. Listener vừa cập nhật database vừa ghi Kafka

Xét một listener có Kafka transaction từ container, bên trong gọi database service có `@Transactional("transactionManager")`:

~~~java
@Component
public class OrderListener {
    private final OrderDbService dbService;
    private final KafkaTemplate<String, OrderProcessed> kafkaTemplate;

    public OrderListener(
            OrderDbService dbService,
            KafkaTemplate<String, OrderProcessed> kafkaTemplate) {
        this.dbService = dbService;
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.input",
            groupId = "orders-group",
            containerFactory = "transactionalOrdersFactory")
    public void onMessage(OrderCreated event) throws Exception {
        dbService.applyIdempotently(event);
        kafkaTemplate.send(
                "orders.processed",
                event.orderId(),
                new OrderProcessed(event.orderId()))
                .get(10, TimeUnit.SECONDS);
    }
}

@Service
public class OrderDbService {
    private final OrderRepository repository;

    public OrderDbService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional("transactionManager")
    public void applyIdempotently(OrderCreated event) {
        repository.applyIfNotProcessed(event.eventId());
    }
}
~~~

`applyIfNotProcessed` là method nghiệp vụ minh họa; production phải bảo vệ bằng database constraints và transaction đúng.

Timeline:

~~~text
Container BEGIN Kafka transaction
       |
       v
Listener gọi DB service
       |
       v
BEGIN DB transaction
       |
       v
DB update
       |
       v
COMMIT DB
       |
       v
KafkaTemplate.send()
       |
       v
Container COMMIT Kafka output + consumed offset
~~~

Nếu DB commit rồi Kafka transaction abort do crash, input được giao lại, nhưng DB side effect của lần trước đã có. **Idempotent DB update** là bắt buộc để tránh ghi lặp dù Kafka output và offset được xử lý transactional.

### 12.1. Không tự ack/commit consumer offset ngoài transaction

Transactional listener container điều phối việc gắn offsets vào Kafka transaction. Không gọi KafkaConsumer.commitSync() thủ công hoặc dùng một producer bất kỳ để “đẩy offset qua” nhằm khắc phục lỗi, vì có thể phá vỡ atomicity với Kafka outputs.

### 12.2. Exception và after-rollback

Khi transactional listener ném exception, Kafka transaction có thể abort. Các thành phần xử lý sau rollback, chẳng hạn `DefaultAfterRollbackProcessor`, quyết định seek/retry hoặc recover record theo policy. Không áp dụng máy móc hướng dẫn cho `DefaultErrorHandler` của non-transactional container mà không kiểm tra transaction-specific flow.

## 13. Transaction synchronization không đồng nghĩa EOS end-to-end

| Thiết kế | Kết quả được bảo vệ |
|---|---|
| Kafka-only `@Transactional("kafkaTransactionManager")` | Các Kafka sends trong transaction commit/abort cùng nhau |
| Kafka transactional listener + KafkaTemplate | Kafka output và consumed offsets commit/abort nguyên tử trong Kafka |
| DB `@Transactional` + Kafka synchronized producer | Hai local commits theo thứ tự, vẫn có partial commit window |
| Kafka-first nested local transactions | Kafka commit trước DB, vẫn có partial commit window |
| DB transaction + outbox row | Business DB state và ý định publish nằm trong cùng DB transaction |
| Kafka consumer + DB inbox | Database xử lý idempotent khi Kafka redeliver |

Không dùng từ “exactly-once” mà không nói **đúng phạm vi**. Kafka EOS không rollback HTTP call, email, database update hoặc file write.

## 14. Transactional outbox khi database là nguồn sự thật

Nếu yêu cầu là “đã lưu đơn hàng thì cuối cùng phải có Kafka event”, trực tiếp synchronize Kafka với DB vẫn có nguy cơ DB commit nhưng Kafka commit không thành công. **Transactional outbox** là một hướng đáng cân nhắc.

~~~text
Create order request
        |
        v
BEGIN DB transaction
        |
        +-- INSERT order
        |
        +-- INSERT outbox_event
        |
        v
COMMIT DB (atomic)
        |
        v
Outbox publisher / CDC
        |
        v
Kafka topic
~~~

Ví dụ:

~~~sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

Schema minh họa phù hợp PostgreSQL; production cần chính sách retention, partitioning, indexing, payload schema và cleanup.

Trong một DB transaction, service lưu entity và row outbox cùng nhau. Một publisher/CDC độc lập sẽ phát event sang Kafka và retry khi cần. Nếu publisher crash sau khi Kafka send thành công nhưng trước khi đánh dấu row đã publish, event có thể được phát lại. Vì vậy outbox vẫn cần **event id ổn định và idempotent consumer**, nhưng tránh cửa sổ “DB đã commit mà không còn ý định publish nào”.

### 14.1. Vì sao không chỉ retry phương thức DB-first?

Khi DB đã commit và Kafka commit thất bại, retry toàn bộ method có thể tạo thêm entity hoặc side effect. Outbox tách hẳn việc “tạo order” khỏi “publish order event” và cung cấp trạng thái có thể đối soát; không buộc gọi lại toàn bộ nghiệp vụ.

## 15. Inbox và idempotency cho consumer cập nhật database

Kafka có thể giao lại một record vì:

- Consumer crash trước offset commit.
- Kafka transaction abort.
- Rebalance.
- DLT/replay.
- Recovery publisher phát lại bản record.

Nếu listener cập nhật database, cần chống side effect trùng:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong **cùng DB transaction**:

1. Ghi event id vào bảng processed events với unique constraint.
2. Nếu event id đã tồn tại, nhận diện dữ liệu đã xử lý trước đó.
3. Nếu mới, thực hiện business DB update.
4. Commit database transaction.
5. Để listener hoàn tất và container commit offset theo cấu hình.

Marker processed và business update phải cùng commit để tránh marker nói “xong” nhưng business state chưa đổi.

Không dùng Kafka transactional ID làm idempotency key nghiệp vụ: transactional ID xác định producer, không xác định một event.

## 16. AOP proxy: @Transactional không tự hoạt động trong mọi lời gọi

Trong cấu hình proxy thông thường, Spring `@Transactional` chỉ có hiệu lực khi lời gọi đi qua Spring proxy.

### 16.1. Self-invocation

~~~java
@Service
public class WrongOrderService {

    @Transactional("transactionManager")
    public void create() {
        publish();
    }

    @Transactional("kafkaTransactionManager")
    public void publish() {
        // Một lời gọi trực tiếp trong cùng object có thể bypass proxy.
    }
}
~~~

Việc method `publish` có annotation không chứng minh Kafka transaction được mở. Giải pháp dễ hiểu là tách thành service bean khác và gọi qua Spring dependency injection, như ví dụ Kafka-first.

### 16.2. Các trường hợp khác

- Object được tạo bằng `new` thay vì Spring-managed bean.
- Method không được proxy intercept trong cấu hình hiện tại.
- Annotation chọn nhầm transaction manager.
- Exception bị catch và nuốt.
- Công việc chuyển sang thread pool sau khi method kết thúc.
- Transaction chỉ bao quanh việc schedule task chứ không bao quanh thực thi task.

Hãy viết integration tests quan sát output committed/aborted thật, không chỉ assert rằng annotated method đã được gọi.

## 17. Rollback rules và checked exceptions

Theo quy tắc Spring `@Transactional` thông dụng, `RuntimeException` và `Error` kích hoạt rollback mặc định; checked exceptions không tự động rollback nếu không cấu hình.

Ví dụ:

~~~java
@Transactional(
        transactionManager = "kafkaTransactionManager",
        rollbackFor = Exception.class)
public void publishOrder(OrderCreated event) throws Exception {
    kafkaTemplate.send("orders.events", event.orderId(), event)
            .get(10, TimeUnit.SECONDS);
}
~~~

`Future.get()` có thể ném checked exceptions như `ExecutionException` hoặc `InterruptedException`. Nếu kỳ vọng các exception đó làm rollback, phải thiết lập rules phù hợp hoặc chuyển thành domain exception có semantics rõ. Khi xử lý interruption, cần giữ interrupt flag nếu tầng code bắt exception đó.

Không đặt `rollbackFor=Exception.class` chỉ để “an toàn” nếu có checked exceptions được định nghĩa là business success hoặc không nên rollback; chính sách phải thống nhất với nghiệp vụ.

### 17.1. Bắt lỗi rồi trả thành công

~~~java
@Transactional("kafkaTransactionManager")
public void wrong(OrderCreated event) {
    try {
        kafkaTemplate.send("orders.events", event);
    }
    catch (Exception ex) {
        log.warn("Send failed", ex);
        // Sai nếu muốn transaction rollback.
    }
}
~~~

Nếu transaction interceptor thấy method trả về bình thường, nó có thể commit. Hãy truyền exception lên hoặc đánh dấu rollback theo API Spring khi chính sách yêu cầu; đừng chỉ log lỗi mà cho rằng transaction đã abort.

## 18. @Async, CompletableFuture và transaction boundary

Transaction context thường gắn với thread. Ví dụ nguy hiểm:

~~~java
@Transactional("kafkaTransactionManager")
public void publishAsync(OrderCreated event) {
    executor.submit(() -> kafkaTemplate.send("orders.events", event));
    // Method kết thúc trước khi task chạy xong.
}
~~~

Worker ở thread khác không mặc nhiên tham gia Kafka transaction của caller. Transaction có thể commit khi method return, trong khi worker chưa gửi output hoặc gửi sau khi producer transaction đã kết thúc.

Nếu cần async:

- Định nghĩa một transaction riêng tại worker hoặc workflow.
- Có cơ chế bảo đảm task đã bền vững trước khi caller trả thành công.
- Không commit Kafka input offset trước khi output/recovery đã được lưu đúng cách.
- Dùng outbox nếu cần tách xử lý khỏi request thread mà không mất event.

Không suy ra rằng dùng `CompletableFuture` bên trong transactional method tự động giữ transaction mở đến khi future hoàn tất.

## 19. Transaction timeout, producer cache và fencing

Kafka producer transaction có timeout và phụ thuộc broker transaction coordinator. Transaction kéo dài vì HTTP request, database lock, xử lý batch quá lớn hoặc broker lag có thể bị abort.

Các yếu tố cần quản lý:

- Transaction timeout phù hợp với thời gian listener xử lý.
- Producer send timeout và retry/backoff của client.
- Transactional ID uniqueness.
- Producer cache lifecycle.
- Consumer group rebalance và graceful shutdown.
- Topic min.insync.replicas/acks nếu yêu cầu durability cao.

### 19.1. ProducerFencedException

Hai producer dùng cùng transactional ID có thể khiến broker fence producer cũ:

~~~text
Pod A: transactional.id=orders-tx-1
Pod B: transactional.id=orders-tx-1
             |
             v
      Old producer fenced
             |
             v
     Transaction commit fails
~~~

Không cố tiếp tục commit bằng producer đã bị fenced; cần khắc phục collision và khôi phục producer/container theo lifecycle được Spring Kafka hỗ trợ.

### 19.2. maxAge của producer factory

Với producer cache ít được sử dụng, một số phiên bản Spring Kafka hỗ trợ `DefaultKafkaProducerFactory.maxAge` để làm mới transactional producer trước khi trạng thái transactional ID quá cũ so với cấu hình broker. Chọn giá trị theo broker expiration, workload và phiên bản Spring Kafka; không copy mù quáng từ hệ thống khác.

## 20. Xử lý lỗi ở transactional listener và DLT

Khi transactional listener ném exception, Kafka transaction abort. Spring Kafka có các cơ chế after-rollback như `DefaultAfterRollbackProcessor` để quyết định seek, retry, recover hoặc chuyển DLT.

Nếu record không thể xử lý và cần đưa vào DLT, cần bảo đảm **DLT publish và xác nhận offset nguồn** theo recovery policy an toàn. Một số cấu hình dùng transactional KafkaTemplate và commit recovered offset trong Kafka transaction tương ứng. Các API như `commitRecovered` có điều kiện về transaction manager và phiên bản; hãy kiểm tra tài liệu của dependency đang chạy.

Nguyên tắc:

1. Không commit input offset trước khi output hoặc DLT recovery được lưu bền vững.
2. Không bỏ qua failure khi producer gửi DLT.
3. DLT producer cần serializer phù hợp cả raw bytes khi lỗi deserialize.
4. Recovery/DLT consumer phải idempotent khi record được giao lại.
5. Test DLT broker unavailable/ACL denied để quan sát commit behavior.

### 20.1. Non-blocking retry topics không phải sự thay thế đơn giản

Spring Kafka có giới hạn tương thích giữa `@RetryableTopic` non-blocking retry và transactional listener containers; trong nhiều phiên bản, chúng không được hỗ trợ kết hợp trực tiếp. Không thêm retry topic rồi mặc nhiên giữ được Kafka read-process-write EOS qua toàn bộ topology.

Khi cần delayed retries dài, hãy thiết kế recovery path và idempotency riêng, hoặc chọn mô hình có transaction boundaries rõ ràng theo phiên bản hỗ trợ.

## 21. Những cửa sổ lỗi cần nhớ

| Thời điểm lỗi | DB | Kafka | Rủi ro |
|---|---|---|---|
| Trước cả hai commit | Rolled back | Aborted | Có thể retry nếu idempotent |
| DB-first: DB commit xong, Kafka commit lỗi | Committed | Aborted/unknown | DB có state nhưng event có thể thiếu |
| Kafka-first: Kafka commit xong, DB commit lỗi | Aborted/unknown | Committed | Downstream thấy event khi DB state chưa tồn tại |
| Transactional listener: DB commit xong, Kafka abort | Committed | Output/offset không commit | Input redelivery; DB side effect có thể lặp |
| Kafka-only transaction abort | Không áp dụng | Aborted | `read_committed` không thấy output abort |
| DLT send fail nhưng nguồn commit sai | Phụ thuộc | Recovery chưa lưu | Nguy cơ mất record |

Một Kafka commit failure có thể cho kết quả chưa rõ ở tầng caller; không nên gửi lại event với ID mới một cách mù quáng. Dùng event id ổn định, outbox trạng thái publish hoặc reconciliation để xác định thực tế.

## 22. Kiểm thử tích hợp: không chỉ mock KafkaTemplate

Để chứng minh transaction behavior, cần Kafka broker thật hoặc test broker có hỗ trợ transactions, cùng DB test phù hợp. Chỉ mock KafkaTemplate không chứng minh atomic commit/abort.

### 22.1. Kafka-only commit

1. Service `@Transactional("kafkaTransactionManager")` gửi hai records.
2. Gọi thành công.
3. Dùng consumer `read_committed` xác nhận cả hai records hiển thị.
4. Đối chiếu records và transaction outcome.

### 22.2. Kafka-only rollback

1. Trong method transactional, send record rồi ném exception.
2. Xác nhận transaction abort.
3. Dùng `read_committed` consumer xác nhận record abort không hiển thị.

### 22.3. DB-first partial commit

1. DB transaction cập nhật row và gửi Kafka synchronized.
2. Mô phỏng Kafka commit failure sau DB commit.
3. Xác nhận DB row vẫn tồn tại.
4. Xác nhận application phát hiện tình huống và có reconciliation/outbox.
5. Kiểm tra HTTP caller retry không tạo duplicate entity.

### 22.4. Kafka-first partial commit

1. Method Kafka transaction commit.
2. Mô phỏng DB rollback tại bước commit ngoài.
3. Xác nhận downstream `read_committed` thấy event.
4. Kiểm tra compensation hoặc state validation.

### 22.5. Transactional listener + DB idempotency

1. Consumer nhận input và DB service update.
2. Mô phỏng crash sau DB commit nhưng trước Kafka transaction commit.
3. Input được redeliver.
4. DB inbox phát hiện event id đã xử lý.
5. Kafka output + input offset commit theo thiết kế.

### 22.6. AOP, exception, async

1. So sánh gọi annotated method qua proxy và self-invocation.
2. Test checked exception rollback rules.
3. Test producer fencing.
4. Test worker thread không tự nhận transaction context.
5. Test DLT publish failure để xác nhận input không bị mất.

Nên assert state DB, output nhìn thấy bằng `read_committed` và consumer group offsets thực tế; không chỉ assert một dòng log “transaction started”.

## 23. Observability cho hệ thống Kafka và database

Metrics và logs nên phản ánh cả hai resources:

| Chỉ số | Mục tiêu |
|---|---|
| Kafka txn begin/commit/abort | Tỷ lệ transaction thành công/thất bại |
| Kafka commit latency | Broker hoặc network chậm |
| Producer fencing errors | Transactional ID collision/lifecycle |
| Kafka send failure count | Lỗi gửi record |
| DB commit/rollback rate | Tình trạng DB transactions |
| DB committed, Kafka failed cases | Phát hiện inconsistency |
| Outbox backlog và oldest age | Event chưa publish |
| Consumer lag và record age | Độ trễ xử lý |
| Inbox duplicates | Redelivery/replay |
| DLT publish/recovery failure | Tình trạng đường phục hồi |

Không phải tất cả metrics có sẵn với cùng tên ở Spring Kafka. Một số cần Micrometer, Kafka client metrics, database monitoring và application instrumentation.

### 23.1. Structured logging

Log nên có service, instance ID, request/event ID, topic, partition, offset, stage của transaction, loại manager và exception class. Không log secret, PII hoặc toàn bộ payload nhạy cảm. Tránh dùng event ID hoặc offset làm metric tag do cardinality cao; dùng trace/log để tìm một sự kiện cụ thể.

### 23.2. Alerts

- Kafka transaction abort tăng kéo dài.
- `ProducerFencedException` xuất hiện sau scale-out.
- DB commit thành công nhưng Kafka commit thất bại.
- Outbox backlog vượt SLA.
- Kafka consumer lag tăng do transaction/DB processing chậm.
- DLT/recovery publish failures.

Ngưỡng alert nên gắn với SLO nghiệp vụ thay vì đặt chung cho mọi topic.

## 24. Runbook: DB có dữ liệu nhưng Kafka thiếu event

1. Xác định entity ID, event ID và thời điểm DB commit.
2. Kiểm tra service dùng DB-first synchronization hay outbox.
3. Kiểm tra Kafka transaction commit error và broker status.
4. Xác nhận KafkaTemplate thực sự transactional.
5. Nếu outbox tồn tại, kiểm tra row outbox và trạng thái publisher.
6. Nếu direct synchronization, chạy reconciliation/compensation phù hợp.
7. Không tạo event ID mới khi chưa biết event cũ đã commit hay chưa.
8. Kiểm tra downstream trạng thái sau recovery.

## 25. Runbook: Kafka có event nhưng DB không có row

1. Xác định Kafka output có thuộc committed transaction không.
2. Kiểm tra có Kafka-first commit order hay không.
3. Xem database rollback, constraint violation hoặc commit timeout.
4. Xác định event có được publish từ producer khác không.
5. Kiểm tra downstream có dùng `read_committed`.
6. Thực hiện compensation hoặc thiết kế DB state validation.
7. Cân nhắc outbox nếu DB là source of truth.

## 26. Runbook: @Transactional không rollback Kafka như mong đợi

1. Kiểm tra tên transaction manager trong annotation.
2. Xác minh method được gọi qua Spring proxy.
3. Xem exception có bị catch và nuốt không.
4. Kiểm tra checked exception và `rollbackFor`.
5. Xác nhận KafkaTemplate dùng transactional ProducerFactory.
6. Xem code có dùng `executeInTransaction` riêng không.
7. Kiểm tra có async worker vượt transaction boundary không.
8. Dùng consumer `read_committed` để xác nhận output abort.

## 27. Runbook: ProducerFencedException sau deploy

1. Kiểm tra transactional ID prefix/suffix của mọi pod.
2. Xác định có rolling update hoặc blue/green overlap không.
3. Kiểm tra việc cấp unique instance ID.
4. Xem producer cache/lifecycle và transaction timeout.
5. Không dùng producer đã fenced để commit tiếp.
6. Khôi phục container/producer đúng lifecycle.
7. Theo dõi abort rate, lag và output sau khi sửa.

## 28. Những sai lầm thường gặp

**Nhầm KafkaTransactionManager với DB transaction manager.** Hai manager quản lý hai resources khác nhau.

**Tin rằng hai @Transactional lồng nhau tạo XA.** Commit thứ nhất có thể thành công trong khi commit thứ hai thất bại.

**Không chọn manager rõ ràng.** Annotation có thể bind tới manager không mong đợi.

**Self-invocation bypass proxy.** Annotation có thể không mở transaction.

**Nuốt Kafka send exception.** Method trả bình thường có thể dẫn đến commit dù output mong muốn không được ghi.

**Dùng executeInTransaction trong DB method rồi coi là atomic.** Local Kafka callback transaction không phải distributed commit.

**DB-first không có outbox hoặc đối soát.** Event có thể bị thiếu sau DB commit.

**Kafka-first không có compensation.** Downstream có thể nhận event dù DB rollback.

**Quên idempotency cho database.** Kafka redelivery có thể cập nhật DB nhiều lần.

**Gửi async sau method return.** Worker không mặc nhiên tham gia transaction.

**Downstream dùng read_uncommitted.** Aborted Kafka records có thể xuất hiện.

**Không kiểm thử lỗi commit thứ hai.** Đây là failure window quan trọng nhất.

## 29. Checklist triển khai

### Kafka configuration

- [ ] ProducerFactory có transactional ID prefix.
- [ ] Transactional IDs duy nhất giữa các instance.
- [ ] KafkaTemplate và KafkaTransactionManager dùng ProducerFactory tương thích.
- [ ] Listener container có Kafka transaction manager nếu cần read-process-write EOS.
- [ ] Downstream dùng `read_committed` khi cần transactional visibility.

### Spring transaction boundaries

- [ ] `@Transactional` chọn đúng bean manager.
- [ ] Đã xác định DB-first, Kafka-first hoặc Kafka-only.
- [ ] Đã ghi rõ thứ tự commit và failure window.
- [ ] Không có self-invocation/async khiến transaction context sai.
- [ ] Rollback rules cho checked exceptions phù hợp nghiệp vụ.

### Reliability và recovery

- [ ] DB-first có outbox/reconciliation nếu event không được phép mất.
- [ ] Kafka-first có compensation khi DB commit fails.
- [ ] Consumer cập nhật DB có inbox/idempotency.
- [ ] DLT/recovery publish không bị nuốt lỗi.
- [ ] Có giới hạn retry/backoff và transaction timeout.

### Validation và observability

- [ ] Test Kafka-only commit và rollback.
- [ ] Test DB-first/Kafka-first partial commits.
- [ ] Test listener redelivery sau DB commit.
- [ ] Test fencing, rebalance, transaction timeout và DLT failure.
- [ ] Metrics/alerts cho Kafka abort, DB rollback, outbox lag, consumer lag.
- [ ] Có runbook đối soát dữ liệu giữa DB và Kafka.

## Kết luận

`KafkaTransactionManager` đưa Kafka producer transactions vào cơ chế transaction của Spring; `@Transactional("kafkaTransactionManager")` tạo ranh giới gửi Kafka có thể commit/abort như một nhóm. Khi listener container cũng dùng Kafka transaction manager và KafkaTemplate phù hợp, Kafka output và consumed offsets có thể được commit nguyên tử trong phạm vi **Kafka read-process-write**. Nhưng Kafka transaction không tự bao gồm database hoặc HTTP side effects.

Khi phối hợp database với Kafka, **DB-first synchronization** và **Kafka-first nested transactions** chỉ quyết định thứ tự commit của hai local transactions. Cả hai có cửa sổ một resource đã commit và resource còn lại thất bại; chúng không phải distributed XA. Nếu DB là nguồn sự thật và Kafka event không được phép mất, transactional outbox là lựa chọn quan trọng. Nếu consumer Kafka cập nhật database, inbox/idempotency giúp an toàn khi redelivery. Cuối cùng, hãy chỉ định manager rõ ràng, hiểu Spring AOP proxy, quản lý transactional IDs và kiểm thử fault injection ngay tại bước commit thứ hai trước khi đưa vào production.
