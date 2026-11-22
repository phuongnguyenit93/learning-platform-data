# KafkaTransactionManager và giao dịch đọc, xử lý, ghi

## Mục tiêu bài học

Một consumer Kafka có thể đọc event, xử lý nghiệp vụ rồi ghi kết quả sang topic khác. Nếu output đã được ghi nhưng input offset chưa commit, consumer có thể đọc lại input và tạo output trùng. Nếu input offset đã commit nhưng output chưa được ghi, kết quả có thể bị mất. Spring for Apache Kafka hỗ trợ phối hợp hai thao tác này bằng Kafka transaction và `KafkaTransactionManager`.

Sau bài học, bạn có thể:

- Giải thích vai trò của `KafkaTransactionManager` và transactional `ProducerFactory`.
- Cấu hình transaction ID prefix trong Spring Boot và Spring Java configuration.
- Dùng `@Transactional` và `KafkaTemplate` để gửi nhiều record trong một Kafka transaction.
- Dùng `executeInTransaction()` khi cần điều khiển transaction bằng code.
- Cấu hình listener container để transaction bao trùm việc đọc, xử lý, ghi output và commit input offset.
- Hiểu hành vi commit, rollback, retry và redelivery khi listener lỗi.
- Phân biệt Kafka transaction với transaction database và giới hạn của việc đồng bộ nhiều resource.
- Cấu hình downstream consumer với `read_committed`.
- Kiểm thử failure window và thiết kế idempotency cho side effect ngoài Kafka.

## 1. Vì sao cần transaction trong ứng dụng Spring Kafka?

Một pipeline consume-transform-produce thường thực hiện các bước:

```text
Input topic
    |
    v
Consumer đọc record
    |
    v
Xử lý / transform
    |
    v
Producer ghi output topic
    |
    v
Commit input offset
```

Nếu ghi output và commit input offset là hai thao tác độc lập, process có thể crash giữa chúng.

| Thứ tự và thời điểm lỗi | Hệ quả |
|---|---|
| Output được ghi, process crash trước khi commit input offset | Input được đọc lại, có thể tạo output trùng |
| Input offset được commit, process crash trước khi ghi output | Input không được đọc lại, output có thể bị mất |
| Output và input offset cùng một Kafka transaction | Cả hai được commit hoặc transaction bị abort |

Kafka transaction cho phép ghi output record và cập nhật input offset như một đơn vị nguyên tử trong Kafka. Spring Kafka cung cấp `KafkaTransactionManager` và listener container transaction để tích hợp cơ chế đó vào mô hình Spring.

Phạm vi bảo đảm này là Kafka-to-Kafka. Nếu listener còn cập nhật database, gửi email hoặc gọi HTTP service, các side effect đó không tự động nằm trong Kafka transaction.

## 2. `KafkaTransactionManager` là gì?

`KafkaTransactionManager<K, V>` là implementation của Spring `PlatformTransactionManager`, quản lý transaction dựa trên một Kafka `ProducerFactory` có bật transaction.

Khi Spring bắt đầu transaction:

1. Transaction manager lấy transactional producer từ factory.
2. Producer bắt đầu transaction Kafka.
3. `KafkaTemplate` trong cùng transaction sử dụng producer đã được bind vào transaction context.
4. Khi transaction Spring commit, Kafka producer commit transaction.
5. Khi transaction Spring rollback, Kafka producer abort transaction.

`KafkaTransactionManager` quản lý transaction cho Kafka producer. Nó không thay thế Kafka broker, không quản lý consumer group độc lập và không tự biến database thành một resource trong cùng transaction.

### 2.1. ProducerFactory phải được cấu hình transactional

`KafkaTransactionManager` cần một `ProducerFactory` tạo transactional producer. Với `DefaultKafkaProducerFactory`, cần cấu hình transaction ID prefix.

```java
DefaultKafkaProducerFactory<String, String> producerFactory =
    new DefaultKafkaProducerFactory<>(producerProperties);

producerFactory.setTransactionIdPrefix("order-service-instance-1-");
```

Prefix được dùng để tạo transactional ID cho producer. Với nhiều instance ứng dụng, mỗi instance đang hoạt động cần một prefix duy nhất để tránh producer fencing ngoài ý muốn.

Khi factory được cấu hình transactional, Spring Kafka quản lý việc lấy, sử dụng và trả producer theo transaction lifecycle. Không tự tạo một `KafkaProducer` mới bên trong mỗi listener method.

### 2.2. Transaction ID prefix khác group ID

| Cấu hình | Mục đích |
|---|---|
| `group.id` | Định danh consumer group và tiến độ đọc theo topic-partition |
| `transactionIdPrefix` | Sinh transactional ID cho producer và hỗ trợ fencing/recovery |

Một ứng dụng consume-transform-produce thường có cả hai. Group ID được dùng để quản lý consumer và input offset; transaction ID prefix định danh producer thực hiện transaction.

### 2.3. Transactional producer và idempotence

Transactional producer cần producer idempotence để hỗ trợ tính nhất quán transaction. Kafka client bật các cấu hình liên quan phù hợp khi transaction được cấu hình; không nên tùy tiện tắt idempotence hoặc override các producer property xung đột.

Producer idempotence và transaction có phạm vi khác nhau:

- Idempotence ngăn duplicate do retry của cùng producer sequence trong phạm vi Kafka hỗ trợ.
- Transaction kết hợp nhiều output record và input offset thành một đơn vị commit/abort.
- Cả hai không tự deduplicate side effect ở database hoặc HTTP service.

## 3. Cấu hình transaction trong Spring Boot

### 3.1. Khai báo `transaction-id-prefix`

Với Spring Boot, có thể cấu hình transactional producer qua `spring.kafka.producer.transaction-id-prefix`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${INSTANCE_ID:local}-order-service-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      group-id: order-transformer
      enable-auto-commit: false
      isolation-level: read_committed
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

`INSTANCE_ID` cần có giá trị duy nhất giữa các instance đang chạy đồng thời, ví dụ pod name hoặc một instance identifier được nền tảng cấp. Giá trị `local` chỉ phù hợp cho một instance local tại một thời điểm.

Khi transaction ID prefix được cấu hình, Spring Boot có thể tạo transactional `ProducerFactory` và các bean transaction liên quan theo phiên bản Boot đang dùng. Hãy kiểm tra bean thực tế trong ApplicationContext. Nếu ứng dụng cần một bean manager có tên hoặc cấu hình cụ thể, có thể khai báo tường minh như phần tiếp theo.

### 3.2. Khai báo `KafkaTransactionManager`

```java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

Bean manager dùng cùng `ProducerFactory` với `KafkaTemplate`. Khi có nhiều transaction manager trong ứng dụng, đặt tên rõ ràng và chỉ định manager trong `@Transactional` để Spring không chọn nhầm.

Không tạo `KafkaTransactionManager` trên một factory không có transaction ID prefix. Nếu factory không transactional, manager không thể mở Kafka transaction hợp lệ.

Spring Boot thường đã bật annotation-driven transaction management khi có transaction infrastructure phù hợp. Với ứng dụng Spring Framework không dùng Boot, bật `@EnableTransactionManagement` để `@Transactional` được xử lý qua proxy.

### 3.3. Cấu hình bằng Java khi không dùng Boot

Với ứng dụng Spring không dùng Boot, cần tự cấu hình producer properties, factory, template và transaction manager:

```java
@Configuration
public class KafkaConfiguration {

    @Bean
    ProducerFactory<String, String> producerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);

        DefaultKafkaProducerFactory<String, String> factory =
            new DefaultKafkaProducerFactory<>(props);
        factory.setTransactionIdPrefix("order-service-local-");
        return factory;
    }

    @Bean
    KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

Đây là ví dụ cấu hình tối thiểu. Production cần bổ sung security, retry, timeout, serializer phù hợp và một transaction ID prefix duy nhất theo instance.

## 4. Gửi nhiều record trong `@Transactional`

### 4.1. Transaction cho một service method

Khi method được đánh dấu `@Transactional` với `KafkaTransactionManager`, các lệnh gửi qua `KafkaTemplate` dùng cùng Kafka transaction đang hoạt động trên thread đó.

```java
@Service
public class OrderEventService {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventService(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishOrderEvents(String orderId,
                                   String orderCreated,
                                   String auditEvent) {
        kafkaTemplate.send("orders", orderId, orderCreated);
        kafkaTemplate.send("order-audit", orderId, auditEvent);
    }
}
```

Khi method kết thúc bình thường, Spring commit Kafka transaction. Nếu method ném exception phù hợp với rollback rule, Spring rollback transaction và các record đã gửi trong transaction không được công bố như output đã commit.

### 4.2. Exception phải được truyền đến transaction boundary

Nếu code bắt exception rồi chỉ ghi log và trả về bình thường, Spring có thể commit transaction vì method đã kết thúc thành công theo góc nhìn transaction interceptor.

Ví dụ cần tránh:

```java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publish(String key, String value) {
    try {
        kafkaTemplate.send("orders", key, value);
        validateBusinessRule();
    } catch (RuntimeException ex) {
        log.error("Publish failed", ex);
        // Nuốt exception: transaction có thể commit nếu không đánh dấu rollback.
    }
}
```

Nếu cần bắt lỗi để bổ sung log, hãy ném lại exception hoặc đánh dấu transaction rollback-only theo API Spring phù hợp. Đồng thời chú ý quy tắc mặc định: Spring thường rollback với unchecked exception và `Error`; checked exception cần rollback rule tường minh nếu đó là yêu cầu.

### 4.3. Gửi bất đồng bộ không có nghĩa transaction đã commit

`KafkaTemplate.send()` trả về kết quả bất đồng bộ. Việc method trả về future không có nghĩa broker đã commit transaction. Transaction manager hoàn tất transaction khi method kết thúc; lỗi gửi có thể được quan sát ở future hoặc xuất hiện khi flush/commit.

Trong ứng dụng thực tế:

- Không bỏ qua exception phát sinh từ quá trình gửi hoặc commit.
- Không tạo fire-and-forget task chạy sau khi transaction method đã kết thúc nếu task đó phải tham gia transaction hiện tại.
- Giữ việc gửi record trong cùng transaction boundary và thread context.
- Nếu cần chờ kết quả từng send để kiểm tra, xử lý future có kiểm soát nhưng tránh chờ không giới hạn.

### 4.4. Phạm vi của `@Transactional`

Spring transaction thường được áp dụng qua proxy. Gọi một method transactional từ method khác trong cùng object (self-invocation) có thể bỏ qua proxy và không mở transaction mới như mong đợi. Đặt transaction boundary ở service bean được gọi qua Spring proxy hoặc dùng cách quản lý transaction tường minh.

Nếu một listener container đã mở Kafka transaction và listener gọi một service method có `@Transactional` dùng cùng `KafkaTransactionManager` với propagation mặc định `REQUIRED`, method service tham gia transaction hiện tại. Nếu service chỉ định một transaction manager khác, đó là resource transaction khác và không tự động trở thành một phần của Kafka transaction.

Nếu có nhiều `PlatformTransactionManager`, luôn chỉ định đúng manager:

```java
@Transactional(transactionManager = "kafkaTransactionManager")
```

Không mặc định rằng `@Transactional` sẽ chọn Kafka manager chỉ vì method đang gọi `KafkaTemplate`.

## 5. Dùng `KafkaTemplate.executeInTransaction()`

Nếu không muốn đặt transaction boundary bằng annotation, có thể dùng callback:

```java
public void publishOrder(String orderId,
                         String createdEvent,
                         String auditEvent) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders", orderId, createdEvent);
        operations.send("order-audit", orderId, auditEvent);
        return null;
    });
}
```

`executeInTransaction()` bắt đầu và kết thúc một Kafka transaction quanh callback. Callback hoàn tất bình thường thì transaction được commit; callback ném exception thì transaction được abort và exception được truyền ra ngoài.

`executeInTransaction()` tạo transaction cục bộ cho callback; không dùng nó bên trong listener với kỳ vọng transaction đó tự bao gồm input offset của listener container. Trong listener đã có container-managed transaction, hãy gửi bằng `KafkaTemplate` thông thường để tham gia transaction đang hoạt động.

Chọn giữa hai cách:

| Cách | Phù hợp khi |
|---|---|
| `@Transactional` + `KafkaTransactionManager` | Muốn transaction boundary theo service method và tích hợp với Spring transaction abstraction |
| `KafkaTemplate.executeInTransaction()` | Muốn một transaction Kafka cục bộ, ngắn và được bao quanh trực tiếp bằng callback |

`executeInTransaction()` không tự đưa input consumer offset vào transaction. Với consume-transform-produce, nên dùng transaction của listener container hoặc API quản lý offset transaction phù hợp. Cũng không giả định callback này tự tham gia transaction database hoặc biến hai resource thành một transaction phân tán.

## 6. Transaction cho listener container

### 6.1. Container bắt đầu transaction trước khi gọi listener

Đối với consume-process-produce, cách tích hợp tự nhiên là cấu hình `KafkaTransactionManager` trên listener container factory.

Container thực hiện:

1. Poll record từ Kafka.
2. Bắt đầu Kafka transaction cho lần xử lý listener.
3. Gọi method `@KafkaListener`.
4. Các lệnh gửi bằng `KafkaTemplate` tham gia transaction đang hoạt động.
5. Nếu listener hoàn tất thành công, container gửi input offset vào transaction và commit.
6. Nếu listener ném exception, container rollback transaction; input offset không được commit trong transaction đó.

Với record listener, transaction thường bao quanh lần gọi listener cho record; với batch listener, transaction bao quanh lần gọi xử lý batch. Chi tiết phụ thuộc listener type và cấu hình container.

### 6.2. Cấu hình listener container factory

Ví dụ với API Spring Kafka hiện đại:

```java
@Configuration
public class TransactionalListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    KafkaTransactionManager<String, String> kafkaTransactionManager) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);
        return factory;
    }
}
```

`setKafkaAwareTransactionManager()` dùng với các phiên bản Spring Kafka hiện đại. Ở các phiên bản cũ, API cấu hình transaction manager trên `ContainerProperties` có thể mang tên `setTransactionManager()`; kiểm tra Javadoc đúng version của dự án vì API cũ đã được thay thế/deprecate trong các bản mới.

Nếu ứng dụng dùng Spring Boot, có thể tùy biến factory mặc định bằng `ConcurrentKafkaListenerContainerFactoryConfigurer` để giữ các thiết lập Boot rồi gắn transaction manager. Tránh vô tình bỏ mất deserializer, error handler hoặc cấu hình consumer khi thay factory mặc định.

### 6.3. Listener đọc, xử lý và ghi output

```java
@Component
public class OrderTransformer {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderTransformer(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(topics = "orders", groupId = "order-transformer")
    public void transform(String orderEvent) {
        String output = enrich(orderEvent);
        kafkaTemplate.send("order-enriched", extractOrderId(orderEvent), output);
    }
}
```

Khi listener container đã được cấu hình với `KafkaTransactionManager`, lệnh `send()` tham gia transaction do container bắt đầu. Khi method trả về bình thường, container đưa offset của input record vào cùng transaction rồi commit.

Nếu `enrich()` hoặc listener ném exception trước commit, transaction rollback. Output record gửi trong transaction không trở thành output đã commit; input offset cũng không được commit bởi transaction đó.

### 6.4. Consumer downstream phải dùng `read_committed`

Để chỉ đọc output của transaction đã commit, consumer downstream cần:

```yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
```

Consumer `read_uncommitted` có thể nhìn thấy record thuộc transaction chưa commit hoặc đã abort. Khi pipeline dựa vào transaction để bảo đảm output và input offset nhất quán, downstream nên dùng `read_committed` để quan sát đúng kết quả đã commit.

`read_committed` có thể chờ khi có transaction đang mở trên partition vì Last Stable Offset chưa tiến qua transaction đó. Transaction nên ngắn và được kết thúc kịp thời.

## 7. Rollback, retry và redelivery

### 7.1. Listener ném exception

Khi listener container quản lý Kafka transaction và listener ném exception:

- Kafka transaction hiện tại bị rollback/abort.
- Output record thuộc transaction không được consumer `read_committed` xem là output đã commit.
- Input offset trong transaction không được commit.
- Container thực hiện recovery/retry theo cấu hình; record có thể được giao lại.

Việc rollback không xóa log record đã ghi vật lý ngay lập tức. Kafka dùng transaction marker và isolation level để xác định record nào được coi là committed.

### 7.2. Retry sau rollback

Spring Kafka hỗ trợ cơ chế xử lý sau rollback như `DefaultAfterRollbackProcessor`. Có thể cấu hình retry/backoff và sau số lần thử đưa record sang Dead Letter Topic bằng recoverer.

Ví dụ về chính sách ở mức khái niệm:

```text
Listener xử lý record
       |
       +-- Thành công --> commit output + input offset
       |
       +-- Exception --> rollback transaction
                            |
                            v
                     Retry theo backoff
                            |
                  +---------+---------+
                  |                   |
               Còn retry           Hết retry
                  |                   |
                  v                   v
              Redeliver          Recover / DLT
```

Nếu DLT recoverer cũng gửi bằng Kafka, có thể cấu hình recovery trong transaction theo khả năng của phiên bản Spring Kafka và error handler. Cần xác minh `commitRecovered`, transaction manager và recoverer phối hợp đúng; không giả định mọi DLT flow mặc định đều nguyên tử.

### 7.3. Retry không thay thế idempotency

Record có thể được xử lý lại do rollback, rebalance hoặc restart. Nếu listener cập nhật database trước khi Kafka transaction commit, database update có thể đã hoàn tất dù Kafka transaction rollback.

Để chịu được redelivery:

- Gắn event ID ổn định vào mỗi event.
- Dùng inbox/deduplication table với unique constraint.
- Thực hiện deduplication và business update trong cùng database transaction.
- Chỉ thực hiện side effect sau khi đã xác định event chưa được xử lý.
- Với HTTP/payment API, truyền idempotency key nếu hệ thống đích hỗ trợ.

## 8. Kafka transaction và database transaction

### 8.1. `KafkaTransactionManager` chỉ quản lý Kafka

Giả sử listener vừa cập nhật database vừa ghi output topic:

```text
Input Kafka
    |
    v
Listener
    |--------------------|
    v                    v
Update database      Send output Kafka
    |                    |
    v                    v
DB commit            Kafka commit + input offset
```

Database transaction và Kafka transaction là hai resource transaction riêng. `KafkaTransactionManager` không thể rollback một database transaction đã commit; `DataSourceTransactionManager` cũng không thể tự rollback một Kafka transaction đã commit.

### 8.2. Transaction synchronization không phải distributed atomic commit

Spring có cơ chế đồng bộ transaction giữa các transaction manager trong một số cách phối hợp. Cơ chế này có thể điều phối thứ tự commit/rollback giữa các resource, nhưng không tạo ra một XA transaction nguyên tử giữa Kafka và database.

Nếu resource thứ nhất commit thành công nhưng resource thứ hai thất bại, hệ thống vẫn có cửa sổ không nhất quán. Không mô tả cấu hình nhiều transaction manager là exactly-once end-to-end nếu chưa có giao thức phân tán thực sự và khả năng recovery tương ứng.

### 8.3. Inbox pattern cho Kafka-to-database

Nếu consumer cập nhật database, dùng inbox pattern:

1. Bắt đầu database transaction.
2. Insert event ID vào bảng inbox có unique constraint.
3. Nếu event ID mới, thực hiện business update.
4. Commit database transaction.
5. Sau đó để Kafka listener container commit input offset.
6. Nếu process crash giữa bước 4 và 5, record được giao lại nhưng inbox nhận diện duplicate và không áp dụng business update lần nữa.

Kết quả là Kafka có thể giao nhiều lần, nhưng database chỉ áp dụng hiệu quả nghiệp vụ một lần theo event ID.

### 8.4. Outbox pattern cho database-to-Kafka

Khi một request cập nhật database và cần phát event, ghi business state và outbox row trong cùng database transaction. Một publisher hoặc CDC connector đọc outbox rồi gửi event đến Kafka. Nếu publisher crash sau khi Kafka nhận event nhưng trước khi đánh dấu outbox đã gửi, event có thể được gửi lại; consumer downstream vẫn cần idempotency.

Outbox bảo đảm event không bị tách khỏi transaction ghi database. Nó không yêu cầu Kafka transaction manager quản lý database.

## 9. Chọn transaction boundary phù hợp

| Nhu cầu | Cách triển khai thường phù hợp |
|---|---|
| Service publish nhiều record Kafka như một đơn vị | `@Transactional` với `KafkaTransactionManager` |
| Một đoạn code cần transaction Kafka cục bộ | `KafkaTemplate.executeInTransaction()` |
| Listener đọc input, ghi output topic và commit input offset cùng nhau | Kafka transaction trên listener container |
| Listener chỉ cập nhật database | Database transaction + inbox/idempotency; Kafka offset do container quản lý sau khi listener thành công |
| Listener vừa cập nhật database vừa ghi Kafka | Inbox/outbox hoặc quy trình phối hợp có recovery; không giả định atomicity xuyên resource |
| Stream processing Kafka-to-Kafka phức tạp | Kafka Streams với processing guarantee phù hợp hoặc listener transaction theo thiết kế |

Không mở transaction quá rộng. Một transaction nên bao quanh nhóm thao tác Kafka cần commit/abort cùng nhau, không giữ transaction trong lúc chờ người dùng, gọi API bên ngoài lâu hoặc thực hiện tác vụ không liên quan.

## 10. Cấu hình và vận hành transaction trong Spring Kafka

### 10.1. Transaction ID prefix duy nhất

Mỗi application instance có thể chạy nhiều listener thread và producer. Spring Kafka dùng transaction ID prefix để sinh ID transactional cho các producer được quản lý. Prefix phải được phân biệt giữa các instance đang hoạt động đồng thời.

Ví dụ triển khai:

```text
order-transformer-pod-a-
order-transformer-pod-b-
order-transformer-pod-c-
```

Không dùng cùng một prefix cố định cho mọi pod nếu việc đó khiến các producer tạo cùng transactional ID. Producer fencing sẽ xảy ra khi producer mới tiếp quản cùng ID; fencing ngoài dự kiến có thể làm listener lỗi liên tục.

### 10.2. Transaction timeout

`transaction.timeout.ms` giới hạn thời gian một Kafka transaction được phép mở; broker áp dụng `transaction.max.timeout.ms` làm giới hạn tối đa. Chọn timeout đủ cho xử lý bình thường nhưng không quá dài vì transaction bỏ dở có thể giữ Last Stable Offset và làm consumer `read_committed` chờ.

Đo thời gian xử lý record/batch, gửi output và commit trong điều kiện tải đỉnh trước khi chọn timeout.

### 10.3. Consumer auto commit

Khi dùng listener container transaction, không bật auto commit offset của Kafka consumer. Container phối hợp offset với Kafka transaction. Cấu hình thường dùng:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
```

Không gọi `consumer.commitSync()` thủ công trong listener đang dùng container-managed transaction để commit cùng offset ngoài transaction boundary.

### 10.4. Security và ACL

Producer transactional cần quyền phù hợp để ghi topic và sử dụng transactional ID. Consumer cần quyền đọc topic, tham gia group và các quyền liên quan. Nếu transaction không khởi tạo được, kiểm tra cả ACL trên topic/group lẫn transactional ID; không chỉ kiểm tra quyền produce thông thường.

## 11. Quan sát và troubleshooting

Khi transaction không commit hoặc listener bị lặp, kiểm tra theo thứ tự:

1. ProducerFactory đã có transaction ID prefix chưa?
2. `KafkaTransactionManager` có dùng đúng ProducerFactory với `KafkaTemplate` không?
3. Listener container có được cấu hình Kafka-aware transaction manager không?
4. `@Transactional` có chỉ định đúng manager và đi qua Spring proxy không?
5. Exception có bị catch/nuốt trước transaction boundary không?
6. Có producer instance khác dùng cùng transaction ID prefix/ID và fence producer hiện tại không?
7. Transaction duration có vượt `transaction.timeout.ms` không?
8. Consumer downstream có dùng `read_committed` không?
9. Listener có bị rollback liên tục do poison message hoặc lỗi database không?
10. Nếu có database side effect, đã có inbox/idempotency để xử lý redelivery chưa?

Metric/log hữu ích:

- Transaction commit/abort và thời gian transaction.
- Lỗi producer send, commit, abort và fencing.
- Listener error, retry count và số record vào DLT.
- Consumer lag và thời gian partition không tiến triển.
- Transaction coordinator request latency và lỗi coordinator.
- Event ID, topic, partition, offset, group ID và transaction ID trong log.

Tên metric cụ thể tùy Kafka client, Spring Kafka và hệ thống monitoring. Không log toàn bộ payload nếu có dữ liệu cá nhân hoặc bí mật.

## 12. Kiểm thử các failure scenario

Một bài kiểm thử transaction cần xác minh cả output topic lẫn input offset, không chỉ kiểm tra listener method được gọi.

| Kịch bản | Kết quả mong đợi với Kafka transaction |
|---|---|
| Listener xử lý thành công | Output và input offset cùng commit |
| Listener ném exception sau khi gửi output | Transaction rollback; output không được `read_committed` thấy như committed, input được đọc lại |
| Process crash giữa transaction | Transaction cũ được coordinator resolve; input được xử lý lại nếu offset chưa commit |
| Producer bị fencing | Instance cũ không tiếp tục commit; cần dừng/restart đúng logical instance |
| Downstream dùng `read_committed` | Chỉ nhận output transaction đã commit |
| Downstream dùng `read_uncommitted` | Có thể thấy record chưa commit/đã abort; không phù hợp để xác minh EOS |
| Database commit xong, Kafka rollback | Input redelivery không tạo business update trùng nhờ inbox |

Nên kiểm thử bằng broker thật hoặc môi trường integration tương đương, có khả năng tạo transaction, restart process và kiểm tra offset. Mock `KafkaTemplate` không xác minh được transaction coordinator, transaction marker hay read isolation.

## 13. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Tạo `KafkaTransactionManager` với non-transactional ProducerFactory | Không mở được Kafka transaction | Cấu hình transaction ID prefix trước |
| Dùng cùng transactional ID giữa nhiều instance đang chạy | Producer fence lẫn nhau | Dùng prefix duy nhất theo instance |
| Gọi `KafkaTemplate` nhưng không có transaction boundary | Các send có thể không cùng transaction như mong muốn | Dùng `@Transactional`, container transaction hoặc `executeInTransaction()` |
| `@Transactional` chọn nhầm database manager | Kafka send không tham gia Kafka transaction | Chỉ định `transactionManager = "kafkaTransactionManager"` |
| Bắt exception rồi nuốt | Spring có thể commit transaction | Ném lại hoặc đánh dấu rollback-only |
| Gọi `executeInTransaction()` và nghĩ input offset tự commit cùng | Output và input offset không cùng transaction | Dùng listener container transaction cho consume-transform-produce |
| Bật auto commit trong transactional listener | Offset có thể commit độc lập | Tắt auto commit và để container quản lý offset |
| Gọi `commitSync()` thủ công trong listener transaction | Làm lệch transaction boundary | Để container gửi offset vào transaction |
| Downstream dùng `read_uncommitted` | Có thể đọc output chưa commit/đã abort | Dùng `read_committed` |
| Nghĩ Kafka transaction rollback database | DB side effect vẫn có thể đã commit | Dùng inbox/outbox và idempotency |
| Giữ transaction mở trong lúc gọi API ngoài lâu | Timeout, LSO bị chặn và latency tăng | Rút ngắn transaction, tách side effect ngoài Kafka |
| Retry vô hạn poison message | Partition bị kẹt và lag tăng | Retry hữu hạn, backoff và DLT |

## 14. Checklist triển khai

- ProducerFactory được cấu hình transactional bằng transaction ID prefix.
- Prefix duy nhất giữa các application instance đang hoạt động.
- `KafkaTransactionManager` dùng cùng ProducerFactory với KafkaTemplate.
- Các method `@Transactional` chỉ định đúng transaction manager.
- Listener container được cấu hình Kafka-aware transaction manager khi cần read-process-write.
- Consumer auto commit được tắt khi container quản lý offset trong transaction.
- Output Kafka và input offset nằm trong cùng transaction boundary.
- Downstream consumer dùng `read_committed` khi cần chỉ thấy output đã commit.
- Listener không nuốt exception khiến transaction commit ngoài ý muốn.
- Retry/backoff/DLT có giới hạn và được kiểm thử.
- Transaction timeout phù hợp với thời gian xử lý và broker max timeout.
- Database/HTTP side effect có inbox/outbox hoặc idempotency riêng.
- Có log/metric cho commit, abort, fencing, retry, DLT và lag.
- Đã kiểm thử crash, rollback, producer fencing và redelivery.

## 15. Câu hỏi tự kiểm tra

1. `KafkaTransactionManager` quản lý resource nào?
2. Vì sao ProducerFactory cần transaction ID prefix?
3. `transactionIdPrefix` khác `group.id` như thế nào?
4. Khi dùng `@Transactional`, `KafkaTemplate` tham gia transaction hiện tại bằng cách nào?
5. Vì sao nuốt exception có thể làm transaction commit ngoài ý muốn?
6. `executeInTransaction()` khác transaction do listener container quản lý ở điểm nào?
7. Listener container phối hợp output record và input offset như thế nào?
8. Vì sao consumer downstream nên dùng `read_committed`?
9. Điều gì xảy ra khi listener ném exception sau khi đã gửi output?
10. Retry sau rollback có thể làm side effect database lặp như thế nào?
11. Vì sao KafkaTransactionManager không tạo transaction nguyên tử với database?
12. Inbox và outbox giải quyết các failure window nào?
13. Tại sao không nên bật auto commit khi container đang quản lý offset bằng Kafka transaction?
14. Những metric nào giúp phát hiện transaction kéo dài hoặc producer fencing?

## Kết luận

`KafkaTransactionManager` kết nối transaction Kafka với Spring transaction abstraction. Với producer service, `@Transactional` hoặc `KafkaTemplate.executeInTransaction()` có thể gom nhiều lần gửi thành một Kafka transaction. Với consume-process-produce, listener container cần được cấu hình transaction manager để output record và input offset được commit cùng nhau; lỗi listener làm transaction rollback và record có thể được giao lại. Downstream cần `read_committed` để chỉ thấy output đã commit. Khi xử lý thêm database hoặc HTTP, cần inbox/outbox và idempotency vì Kafka transaction không tự bao trùm các hệ thống ngoài Kafka.
