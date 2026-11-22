# KafkaTransactionManager

## 1. KafkaTransactionManager là gì?

`KafkaTransactionManager<K, V>` là transaction manager của Spring Kafka dùng để quản lý **Kafka producer transaction** thông qua Spring transaction infrastructure. Khi ứng dụng mở transaction với manager này, các lần gửi qua `KafkaTemplate` dùng đúng transactional `ProducerFactory` có thể tham gia một Kafka transaction chung.

Một Kafka transaction cho phép nhóm nhiều bản ghi gửi đến các Kafka topic/partition và commit hoặc abort chúng như một đơn vị. Trong luồng consume–process–produce, transactional listener container còn có thể gửi offset của record đã tiêu thụ vào cùng Kafka transaction với output record.

~~~text
Business service
       |
       v
KafkaTransactionManager mở transaction
       |
       +--- KafkaTemplate.send(topic A, event A)
       |
       +--- KafkaTemplate.send(topic B, event B)
       |
       v
Commit hoặc abort Kafka transaction
~~~

Điểm cần phân biệt:

- **Send thành công** chưa có nghĩa transaction đã commit.
- **Transaction commit thành công** xác nhận các bản ghi transactional đã được Kafka commit, nhưng không chứng minh consumer downstream đã xử lý.
- **Kafka transaction** không tự bao gồm database transaction, HTTP request hoặc email.
- Consumer dùng `read_committed` sẽ không thấy record thuộc transaction đã abort; consumer `read_uncommitted` có thể đọc các record đó.

KafkaTransactionManager tích hợp Spring với Kafka transaction protocol. Nó không thay thế transaction coordinator của Kafka broker và không tạo ra một transaction phân tán XA giữa Kafka và hệ thống bên ngoài.

## 2. Những thành phần tham gia

| Thành phần | Trách nhiệm |
|---|---|
| `KafkaTransactionManager<K, V>` | Bắt đầu, commit, rollback transaction qua Spring |
| `ProducerFactory<K, V>` | Cung cấp Kafka producer cho KafkaTemplate |
| `DefaultKafkaProducerFactory` | Tạo và quản lý transactional producers, cache và lifecycle |
| `KafkaTemplate<K, V>` | Gửi record bằng producer phù hợp với transaction hiện hành |
| `KafkaProducer` | Thực hiện begin/send/commit/abort ở Kafka client |
| Broker transaction coordinator | Quản lý trạng thái giao dịch theo transactional ID |
| Spring listener container | Quản lý consume–process–produce và gửi offset vào Kafka transaction |
| Consumer `read_committed` | Chỉ đọc record transactional đã commit |

Các thành phần này có ranh giới trách nhiệm khác nhau. `KafkaTemplate` là API gửi message; `KafkaTransactionManager` xác định transaction boundary; producer và broker thực sự thực hiện giao thức transaction.

## 3. Điều kiện đầu tiên: transactional ProducerFactory

### 3.1. Transaction ID prefix

Một Kafka producer thông thường không tự tham gia Kafka transaction. `DefaultKafkaProducerFactory` cần được cấu hình với **transaction ID prefix** để tạo transactional producers có `transactional.id` riêng.

Trong Spring Boot, cách khai báo phổ biến:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-tx-instance-a-
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        transaction.timeout.ms: 60000
~~~

`orders-tx-instance-a-` chỉ là giá trị minh họa. Trong deployment nhiều instance, prefix phải khác nhau giữa các instance chạy đồng thời. Nếu hai producer dùng cùng transactional ID, một producer có thể bị broker fencing.

Spring Boot thường auto-configure KafkaTransactionManager khi có transactional producer factory được cấu hình bằng `spring.kafka.producer.transaction-id-prefix` và không có bean tùy chỉnh xung đột. Cần xác nhận các bean thực tế khi ứng dụng có nhiều producer factory hoặc template.

### 3.2. transaction.id không phải event ID

`transactional.id` nhận diện một transactional producer logic. Kafka dùng ID cùng producer epoch để chống producer cũ tiếp tục gửi sau khi quyền sở hữu ID đã chuyển sang producer khác.

Nó không phải ID của event nghiệp vụ. Nếu một service phát cùng một `OrderCreated` trong hai giao dịch khác nhau, Kafka không tự coi đó là duplicate business event. Event ID ổn định và consumer idempotency vẫn cần khi có retry nghiệp vụ hoặc side effect bên ngoài Kafka.

### 3.3. Producer cache

`DefaultKafkaProducerFactory` có thể tái sử dụng transactional producers trong cache. Số producer cần thiết phụ thuộc transaction concurrency của ứng dụng. Nếu có nhiều listener thread hoặc nhiều transaction producer-only chạy song song, cần quan sát tài nguyên producer và cách factory cung cấp producer tương ứng.

Không tự tạo một KafkaProducer mới cho mỗi record và không tự đóng producer do factory quản lý trong service. Để Spring/Kafka quản lý vòng đời giúp giữ transaction và resource binding nhất quán.

## 4. Luồng begin, send, commit và abort

~~~mermaid
sequenceDiagram
    participant S as Business service
    participant M as KafkaTransactionManager
    participant T as KafkaTemplate
    participant P as Transactional producer
    participant B as Kafka broker

    S->>M: Bắt đầu transaction
    M->>P: beginTransaction()
    S->>T: send(topicA, recordA)
    T->>P: send recordA
    P->>B: Produce request
    S->>T: send(topicB, recordB)
    T->>P: send recordB
    P->>B: Produce request
    alt Thành công
        S->>M: Commit
        M->>P: commitTransaction()
        P->>B: Commit transaction
    else Rollback
        S->>M: Rollback
        M->>P: abortTransaction()
        P->>B: Abort transaction
    end
~~~

Trình tự tổng quát:

1. Spring transaction infrastructure chọn KafkaTransactionManager.
2. Manager lấy transactional producer từ ProducerFactory và mở Kafka transaction.
3. Producer được bind vào transaction context hiện hành theo cơ chế resource synchronization của Spring.
4. KafkaTemplate lấy producer phù hợp để gửi các record trong transaction.
5. Transaction manager commit nếu transaction kết thúc thành công.
6. Nếu có lỗi yêu cầu rollback, manager abort transaction.
7. Producer được cleanup/trả về cache theo policy của factory.

Lệnh `send()` trả về future. Future có thể hoàn tất thành công trước khi Kafka transaction commit. Nếu transaction sau đó abort, kết quả Produce request vẫn không chứng minh record được consumer `read_committed` nhìn thấy.

## 5. Khai báo KafkaTransactionManager trong Java

Nếu ứng dụng đã có transactional ProducerFactory, có thể tạo bean:

~~~java
@Configuration
@EnableTransactionManagement
public class KafkaTxConfiguration {

    @Bean
    public KafkaTransactionManager<String, OrderEvent>
            kafkaTransactionManager(
                ProducerFactory<String, OrderEvent> producerFactory
            ) {

        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    public KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory
    ) {
        return new KafkaTemplate<>(producerFactory);
    }
}
~~~

Bean `producerFactory` trong ví dụ phải có transaction ID prefix. Nếu không, chỉ việc tạo manager không khiến producer trở thành transactional.

Khi có nhiều factory, nên dùng qualifier cho manager và template để tránh manager trỏ đến factory A trong khi KafkaTemplate dùng factory B. Kết nối cùng bootstrap servers không đồng nghĩa hai factory chia sẻ transaction.

### 5.1. Chọn manager tường minh

Một ứng dụng có thể có đồng thời `JpaTransactionManager`, `DataSourceTransactionManager` và `KafkaTransactionManager`. Trong trường hợp đó, `@Transactional` không chỉ rõ manager có thể chọn manager mặc định không như mong muốn.

Nên chỉ định rõ:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishEvents() {
    // ...
}
~~~

Tên bean chính xác phụ thuộc cách ứng dụng đăng ký transaction managers. Đảm bảo code được gọi qua Spring-managed proxy để annotation có hiệu lực.

## 6. Producer-only transaction bằng @Transactional

Một service gửi nhiều event Kafka trong một transaction:

~~~java
@Service
@RequiredArgsConstructor
public class OrderPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishOrder(OrderCreatedEvent created) {
        kafkaTemplate.send(
            "order-events",
            created.orderId(),
            created
        );

        kafkaTemplate.send(
            "order-audit",
            created.orderId(),
            new OrderAuditEvent(created.orderId(), "CREATED")
        );
    }
}
~~~

Khi phương thức được gọi thông qua Spring proxy, manager bắt đầu transaction trước khi vào method và commit sau khi method hoàn tất. Hai bản ghi được gửi trong cùng transaction theo cấu hình của KafkaTemplate/ProducerFactory.

Nếu method ném exception thuộc rollback rule, Spring yêu cầu abort. Với `@Transactional`, rollback mặc định thường áp dụng cho unchecked exception và `Error`; checked exception cần cấu hình rollback nếu muốn:

~~~java
@Transactional(
    transactionManager = "kafkaTransactionManager",
    rollbackFor = Exception.class
)
public void publishOrThrow() throws Exception {
    kafkaTemplate.send("order-events", "order-42", event);

    if (businessRuleFailed()) {
        throw new Exception("Abort Kafka transaction");
    }
}
~~~

Nếu listener/service bắt exception rồi trả về bình thường, Spring có thể coi transaction thành công và commit. Phải để exception đi qua transaction boundary hoặc chủ động đánh dấu rollback-only.

### 6.1. Commit thất bại sau khi method body chạy xong

Transaction interceptor chỉ commit sau khi method body kết thúc. Do đó, code bên trong method không nên log “Kafka transaction committed” ngay sau lần `send()` cuối.

Commit vẫn có thể thất bại vì broker, transaction timeout, producer fencing hoặc lỗi I/O. Caller cần nhận kết quả cuối cùng từ lời gọi đi qua transaction interceptor, không chỉ từ future send của từng record.

### 6.2. Thread-bound transaction context

Resource binding của Spring thường gắn với thread. Nếu code bên trong transactional method tự chuyển việc send sang `CompletableFuture.runAsync(...)` hoặc executor thread khác, transaction context không tự động đi theo.

Sai về giả định:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishAsync(OrderEvent event) {
    CompletableFuture.runAsync(
        () -> kafkaTemplate.send("order-events", event.orderId(), event)
    );
}
~~~

Phương thức có thể kết thúc và commit trước khi task nền thực hiện send; task chạy trên thread khác có thể không tham gia transaction. Hãy thực hiện các lệnh KafkaTemplate.send trong transaction scope, còn bản thân Kafka producer đã hỗ trợ gửi bất đồng bộ ở tầng I/O.

### 6.3. Self-invocation

Với proxy-based Spring transactions, method A gọi method B trên chính object đó có thể bỏ qua transaction interceptor của B.

~~~java
public void handleOrder(OrderEvent event) {
    publishTransactional(event);  // gọi nội bộ, không qua proxy
}

@Transactional(transactionManager = "kafkaTransactionManager")
public void publishTransactional(OrderEvent event) {
    kafkaTemplate.send("order-events", event.orderId(), event);
}
~~~

Có thể tách transactional operation sang bean khác hoặc dùng `TransactionTemplate` để tránh phụ thuộc self-invocation.

## 7. TransactionTemplate và KafkaTemplate.executeInTransaction

### 7.1. Spring TransactionTemplate

`TransactionTemplate` cung cấp transaction boundary bằng code:

~~~java
@Service
public class KafkaOrderService {

    private final KafkaTemplate<String, OrderEvent> template;
    private final TransactionTemplate transactionTemplate;

    public KafkaOrderService(
        KafkaTemplate<String, OrderEvent> template,
        KafkaTransactionManager<String, OrderEvent> manager
    ) {
        this.template = template;
        this.transactionTemplate = new TransactionTemplate(manager);
    }

    public void sendBoth(OrderEvent first, OrderEvent second) {
        transactionTemplate.executeWithoutResult(status -> {
            template.send("order-events", first.orderId(), first);
            template.send("order-events", second.orderId(), second);
        });
    }
}
~~~

`TransactionTemplate` xử lý begin, commit và rollback quanh callback. Nó hữu ích khi cần boundary tường minh hoặc khi transaction không thuận tiện đặt trên một service method.

### 7.2. KafkaTemplate.executeInTransaction

`KafkaTemplate` cũng có API local transaction:

~~~java
public void sendBoth(OrderEvent first, OrderEvent second) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("order-events", first.orderId(), first);
        operations.send("order-events", second.orderId(), second);
        return null;
    });
}
~~~

Đây là cách mở một Kafka transaction cục bộ quanh callback bằng transactional template. Cần lưu ý semantics của `executeInTransaction` có scope riêng và không nên tự giả định nó tham gia cùng một transaction bên ngoài do KafkaTransactionManager quản lý. Chọn boundary phù hợp, tránh lồng các cơ chế giao dịch khi không cần.

| Cách sử dụng | Boundary | Tình huống phù hợp |
|---|---|---|
| `@Transactional("kafkaTransactionManager")` | Spring transaction interceptor | Service method gửi nhiều Kafka records |
| `TransactionTemplate` | Callback Spring transaction | Điều khiển transaction bằng code |
| `KafkaTemplate.executeInTransaction` | Local Kafka transaction | Producer-only callback độc lập |
| Transactional listener container | Container transaction | Consume–process–produce |

## 8. Consume–process–produce với KafkaTransactionManager

Một use case quan trọng là đọc record từ Kafka, tính kết quả, phát output record sang Kafka và đưa offset nguồn vào **cùng Kafka transaction**.

~~~text
Input topic "payments"
      |
      v
Transactional listener container
      |
      +-- Nhận input record
      +-- Chạy business logic
      +-- KafkaTemplate.send("payment-results", result)
      +-- Send input consumer offset to transaction
      |
      v
Commit Kafka transaction
      |
      +-- Output được commit
      +-- Input offset cũng được commit
~~~

Nếu transaction abort, output record không hiển thị với `read_committed` consumer và input offset không được commit trong transaction đó. Record nguồn có thể được giao lại sau rollback/seek theo thiết lập container.

### 8.1. Vì sao offset phải nằm trong cùng transaction?

Nếu output được commit trước nhưng source offset được commit riêng sau, crash ở giữa hai bước khiến Kafka output đã có mà source offset chưa tiến. Record nguồn có thể được đọc lại và output bị phát lặp.

Khi output và offset cùng tham gia Kafka transaction, hai kết quả này được commit hoặc abort theo transaction protocol. Đây là cơ sở cho exactly-once semantics trong luồng Kafka-to-Kafka.

### 8.2. Transactional listener

Ví dụ listener gửi kết quả sang một Kafka topic khác:

~~~java
@Component
@RequiredArgsConstructor
public class PaymentListener {

    private final KafkaTemplate<String, PaymentResult> template;

    @KafkaListener(
        topics = "payment-requests",
        groupId = "payment-processor",
        containerFactory = "transactionalListenerContainerFactory"
    )
    public void onPayment(PaymentRequested request) {
        PaymentResult result = calculateResult(request);

        template.send(
            "payment-results",
            request.paymentId(),
            result
        );
    }
}
~~~

Listener container phải được cấu hình transactional và dùng producer factory phù hợp. Không tự gọi `commitSync()` trong listener để commit source offset khi container đang chịu trách nhiệm transaction.

### 8.3. Cấu hình container factory

Với Spring Kafka version hỗ trợ Kafka-aware transaction manager trên container properties:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, PaymentRequested>
        transactionalListenerContainerFactory(
            ConsumerFactory<String, PaymentRequested> consumerFactory,
            KafkaTransactionManager<String, PaymentResult> kafkaTxManager
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, PaymentRequested>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTxManager);

    return factory;
}
~~~

Tên API để gắn transaction manager phụ thuộc phiên bản Spring Kafka. Phiên bản cũ có thể cung cấp `setTransactionManager(...)`, phiên bản mới dùng API Kafka-aware. Nên đối chiếu Javadoc của dependency thực tế khi viết cấu hình Java và bảo đảm đúng bean factory được `@KafkaListener` sử dụng.

Nếu dùng auto-configuration của Spring Boot hoặc một container factory tùy chỉnh, hãy xác định Kafka transaction manager có thực sự được gắn vào container; chỉ bật `transaction-id-prefix` ở producer chưa đủ để mọi listener tự có transaction.

## 9. Exactly-once semantics và read_committed

Kafka transaction cung cấp atomicity cho các thao tác Kafka trong transaction. Consumer muốn tránh đọc record từ transaction đã abort cần đặt:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
      enable-auto-commit: false
~~~

`read_committed` chỉ trả về record transactional đã commit và không trả về aborted records. Nó còn có thể chờ khi một transaction vẫn đang mở trước vị trí có thể đọc an toàn (last stable offset). Vì vậy, transaction mở lâu có thể tác động đến consumer lag và độ trễ hiển thị record.

| Consumer isolation | Hành vi với transactional records |
|---|---|
| `read_committed` | Không đọc aborted transactions; chỉ trả committed records |
| `read_uncommitted` | Có thể đọc cả records thuộc aborted hoặc in-flight transactions |

Kafka EOS không bảo đảm listener chỉ được gọi đúng một lần ở mọi điều kiện. Input record có thể được giao lại khi transaction abort. Điều được bảo đảm trong luồng Kafka-to-Kafka là output và offset của transaction được phối hợp nguyên tử, khi dùng đúng transactional processing và consumer isolation.

### 9.1. Không phải exactly-once đối với database

Nếu listener ghi một database rồi gửi Kafka output, database transaction là resource khác:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) {
    orderRepository.save(...);          // SQL side effect
    kafkaTemplate.send("results", ...); // Kafka transaction
}
~~~

Database có thể commit thành công trong khi Kafka transaction abort. Input được redeliver và database side effect có thể chạy lần nữa. Cần unique constraint, inbox table hoặc idempotent upsert để xử lý điều này.

## 10. KafkaTransactionManager và database transaction manager

Spring có thể có nhiều transaction manager:

- `JpaTransactionManager` cho JPA persistence context và database.
- `DataSourceTransactionManager` cho JDBC.
- `KafkaTransactionManager` cho Kafka producer.

`@Transactional` không chỉ định manager chưa đủ để kết luận các resource được điều phối thế nào. Nếu code cập nhật database và publish Kafka event, phải xác định manager nào là primary và Kafka transaction có được synchronized với transaction khác hay không.

### 10.1. Transaction synchronization

Spring Kafka cho phép đồng bộ hóa Kafka producer transaction với một Spring transaction hiện có, ví dụ database transaction. Với database primary, dòng commit có thể là:

~~~text
Begin database transaction
    |
    +-- Update domain tables
    +-- KafkaTemplate sends in synchronized Kafka transaction
    |
    v
Commit database
    |
    v
Commit Kafka
~~~

Nếu database commit thành công nhưng Kafka commit thất bại, hai hệ thống bị lệch trạng thái. Transaction synchronization không phải two-phase commit/XA. Thứ tự resource commit và cách exception được propagate phụ thuộc cấu hình/phiên bản, do đó không được suy ra atomicity xuyên resource.

### 10.2. Nested transactions

Có thể tổ chức các transaction boundary lồng nhau để đổi thứ tự commit giữa Kafka và database. Nhưng đổi thứ tự chỉ thay đổi cửa sổ sự cố: Kafka có thể commit trước DB rồi DB fail, hoặc DB commit trước Kafka rồi Kafka fail.

Không nên dùng nested transaction như một cách “tự động đồng bộ” nếu chưa phân tích thứ tự, rollback rule, proxy và exception propagation.

### 10.3. Transactional outbox

Với yêu cầu database và event Kafka nhất quán, transactional outbox thường đáng tin cậy hơn transaction synchronization:

1. Trong cùng database transaction, ghi dữ liệu nghiệp vụ và outbox row.
2. Commit database.
3. Publisher đọc outbox row chưa phát.
4. Publisher gửi Kafka record và nhận kết quả.
5. Đánh dấu outbox row đã xử lý hoặc lưu progress.

~~~mermaid
flowchart LR
    S[Business service] --> T[Database transaction]
    T --> D[Domain tables]
    T --> O[Outbox table]
    O --> P[Outbox publisher]
    P --> K[Kafka topic]
~~~

Nếu Kafka send đã thành công nhưng publisher crash trước khi đánh dấu outbox, nó có thể phát lại cùng event. Vì vậy outbox thường có at-least-once semantics và vẫn cần event ID cùng idempotent consumer.

KafkaTransactionManager có thể giúp publisher phát nhiều Kafka output record trong một transaction, nhưng nó không biến việc cập nhật outbox table thành Kafka XA transaction.

## 11. Fencing và định danh producer

### 11.1. Producer fencing

Kafka dùng `transactional.id` và producer epoch để ngăn producer cũ ghi khi một producer mới đã nhận cùng identity. Khi producer bị fencing, nó có thể gặp `ProducerFencedException` hoặc lỗi tương đương.

Đây là lỗi quan trọng cần xử lý đúng lifecycle. Producer đã bị fencing không nên tiếp tục được dùng cho các transaction sau; cần dừng/recreate theo cơ chế của Kafka client/factory và kiểm tra vì sao ID bị trùng.

### 11.2. Prefix duy nhất giữa các instance

Ví dụ ba pod không nên dùng cùng một prefix nếu điều đó dẫn đến trùng transactional IDs:

~~~text
Sai nếu chạy đồng thời với cùng suffix:
  orders-tx-
  orders-tx-
  orders-tx-

Hợp lý hơn khi mỗi instance có prefix riêng:
  orders-tx-pod-a-
  orders-tx-pod-b-
  orders-tx-pod-c-
~~~

Khi rollout Kubernetes, xem cả giai đoạn pod cũ và pod mới cùng chạy. Prefix phải gắn với một identity đủ duy nhất để không va chạm trong thời gian overlap.

### 11.3. Static membership khác transactional identity

Consumer property `group.instance.id` phục vụ static membership của consumer group. Nó không thay thế `transactional.id` của producer.

Hai identity giải quyết hai vấn đề khác nhau:

- `group.instance.id` giúp coordinator nhận diện một static consumer member.
- `transactional.id` giúp Kafka quản lý và fence transactional producer.

Không nên hoán đổi hoặc dùng một property thay cho property còn lại.

## 12. Transaction timeout

Kafka producer transaction có timeout. Nếu giữ transaction mở quá lâu, broker có thể abort transaction và lần commit sau sẽ thất bại.

Các nguyên nhân thường gặp:

- Listener xử lý batch quá lớn.
- Gọi HTTP đồng bộ không có timeout.
- Database query hoặc lock chờ lâu.
- Retry blocking bên trong transactional listener.
- Broker/network chậm.
- Code giữ transaction mở qua xử lý không liên quan.

Các cấu hình cần xem:

| Cấu hình / chỉ số | Ý nghĩa |
|---|---|
| `transaction.timeout.ms` | Thời gian Kafka transaction được phép mở |
| Broker transaction timeout limit | Giới hạn timeout được broker chấp nhận |
| `request.timeout.ms` | Thời gian producer chờ response của request |
| `delivery.timeout.ms` | Thời hạn cho quá trình produce delivery |
| `max.poll.interval.ms` | Giới hạn giữa các lần consumer poll |
| Transaction duration | Thời gian transaction thực tế |
| Commit/abort latency | Độ trễ kết thúc transaction |

Không nên tăng timeout vô hạn để che một listener có thể treo. Đặt timeout riêng cho database/HTTP, giảm batch size hoặc tách tác vụ chậm ra ngoài transaction khi có thể.

## 13. Lỗi thường gặp trong Kafka transaction

| Lỗi | Ý nghĩa thường gặp | Điều tra |
|---|---|---|
| `ProducerFencedException` | Producer mất ownership của transactional ID | Prefix trùng, pod overlap, lifecycle |
| `InvalidProducerEpochException` | Epoch producer không còn hợp lệ | Fencing và transaction state |
| `InvalidTxnStateException` | Thao tác không hợp lệ với transaction hiện tại | Begin/commit/abort và lỗi trước đó |
| `TimeoutException` | Request, delivery hoặc commit không hoàn tất đúng hạn | Broker, network, timeout |
| `AuthorizationException` | Thiếu quyền liên quan topic/transactional ID | Principal và ACL |
| `SerializationException` | Không serialize được record | Serializer và schema |
| Kafka commit failure | Không xác nhận được transaction đã commit | Giữ trạng thái không chắc chắn; điều tra trước retry |
| Application exception | Transaction được rollback theo policy của Spring | Transaction boundary và rollback rule |

Đặc biệt, timeout tại thời điểm commit có thể khiến caller không biết chắc kết quả cuối cùng. Không mặc định “đã timeout” nghĩa là Kafka chưa ghi record. Ghi event ID/correlation ID và làm downstream idempotent để việc retry không tạo side effect trùng.

## 14. Retry và after-rollback processing

Với transactional listener container, lỗi listener phải dẫn đến transaction rollback/abort nếu nghiệp vụ chưa thành công. Sau rollback, Spring Kafka có thể sử dụng `AfterRollbackProcessor` để điều khiển seek, redelivery hoặc recovery.

`DefaultAfterRollbackProcessor` là thành phần thường gặp trong luồng này. Không nên tự gắn `DefaultErrorHandler` rồi nuốt exception mà không hiểu semantics của transactional container.

Ví dụ listener:

~~~java
@KafkaListener(
    topics = "payments",
    containerFactory = "transactionalListenerContainerFactory"
)
public void onPayment(PaymentRequested event) {
    paymentService.processAndPublish(event);
    // Nếu thất bại, ném exception để container rollback transaction.
}
~~~

Khi thiết kế recovery cho transactional listener cần làm rõ:

- Record nào sẽ được redeliver sau rollback?
- Retry blocking diễn ra ở đâu và trong thời gian bao lâu?
- Khi hết retry, recoverer/DLT làm gì?
- DLT publish thất bại có thể khiến source offset bị commit sai không?
- Việc commit recovered offset có dùng transaction riêng không?
- Có side effect database nào cần idempotency không?

Không nên giả định non-blocking retry topic tự kết hợp với transactional listener; Spring Kafka có các giới hạn khi phối hợp non-blocking retry với container transaction.

## 15. Kafka transaction không thay thế idempotency

Các trường hợp vẫn có thể tạo duplicate nghiệp vụ dù producer dùng transaction:

- Client gọi lại API phát event sau timeout không rõ outcome.
- Ứng dụng gửi cùng event trong hai transaction độc lập.
- Listener cập nhật database nhưng Kafka transaction abort.
- Consumer `read_uncommitted` đọc bản ghi của aborted transaction.
- DLT publish thành công nhưng trạng thái phục hồi nguồn chưa commit.
- Một consumer group mới replay lịch sử.

Với mỗi business event, nên dùng event ID ổn định; ở bên nhận, áp dụng unique constraint, inbox table hoặc idempotent upsert. Kafka transaction bảo vệ atomicity trong Kafka log, còn idempotency bảo vệ side effect khi event được giao nhiều lần.

## 16. Observability cho KafkaTransactionManager

Một transaction có thể thất bại ở begin, send, commit hoặc abort. Chỉ log KafkaTemplate.send là chưa đủ để biết kết quả cuối cùng.

| Tín hiệu | Mục đích |
|---|---|
| Transaction begin count | Đếm số transaction đã mở |
| Commit success/error | Kết quả commit cuối cùng |
| Abort count | Phân biệt rollback do nghiệp vụ/hạ tầng |
| Commit latency | Phát hiện coordinator/broker chậm |
| Transaction duration | Phát hiện transaction mở quá lâu |
| Producer fencing errors | Phát hiện trùng transactional ID |
| Producer send error/retry rate | Theo dõi Produce request trong transaction |
| Consumer lag | Quan sát tiến độ consumer |
| read_committed visibility delay | Tác động của transaction mở đến downstream |
| Listener processing duration | Thời gian chạy nghiệp vụ |
| Offset/group errors | Điều tra redelivery |

Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka và hệ thống observability. Nên kết hợp producer metrics, listener/container metrics, log transaction và business event ID.

Không dùng event ID làm metric label vì cardinality cao; dùng event ID trong structured log hoặc trace. Tránh ghi payload chứa dữ liệu nhạy cảm.

## 17. Kịch bản kiểm thử transaction

### 17.1. Producer-only commit thành công

1. Tạo transactional producer factory và KafkaTransactionManager.
2. Bắt đầu transaction, gửi hai record tới hai topic.
3. Để transaction commit.
4. Đọc bằng consumer `read_committed`.
5. Xác nhận cả hai bản ghi có thể đọc sau commit.

### 17.2. Producer-only abort

1. Gửi hai record trong transaction.
2. Ném exception thuộc rollback rule.
3. Xác nhận transaction bị abort.
4. Đọc lại bằng consumer `read_committed`.
5. Xác nhận không nhận các record aborted.

### 17.3. Consume–process–produce crash trước commit

1. Gửi một record nguồn có event ID.
2. Listener transactional đọc và gửi output.
3. Dừng process trước khi transaction commit theo kịch bản kiểm thử có kiểm soát.
4. Khởi động lại cùng group ID.
5. Xác nhận record nguồn có thể được giao lại khi source offset chưa commit.
6. Xác nhận aborted output không xuất hiện ở `read_committed` consumer.
7. Cho lần xử lý sau commit và quan sát output/offset.

### 17.4. Producer fencing

1. Trong môi trường thử nghiệm, tạo hai transactional producers cố dùng cùng transactional ID.
2. Quan sát producer cũ bị fencing theo protocol.
3. Xác nhận ứng dụng không tiếp tục dùng producer đã bị fence.
4. Đổi prefix để không còn trùng và kiểm tra lại.

### 17.5. Database side effect

1. Cho listener cập nhật database rồi publish Kafka.
2. Tạo lỗi Kafka commit sau khi database commit.
3. Xác nhận hai resource có thể tạm không nhất quán.
4. Kiểm tra idempotency hoặc outbox có thể khôi phục trạng thái mong muốn.
5. Kiểm tra duplicate khi event được phát lại.

Kiểm thử phải xác minh trạng thái thực tế của Kafka output, consumer offset và database. Method return hoặc send future complete không chứng minh Kafka transaction đã commit.

## 18. Các lỗi thiết kế phổ biến

**Tạo KafkaTransactionManager nhưng factory không transactional:** manager không thể mở Kafka transaction đúng khi producer thiếu transaction ID prefix.

**Có nhiều transaction managers nhưng @Transactional không chỉ rõ:** code có thể dùng manager database thay vì Kafka.

**Trùng transactional ID giữa pod:** broker có thể fence một producer; retry vô hạn trên producer đó không giải quyết ownership.

**Coi KafkaTemplate.send thành công là transaction commit:** một transaction vẫn có thể abort sau khi send hoàn tất.

**Consumer read_uncommitted:** có thể đọc record aborted dù producer sử dụng transaction.

**Coi Kafka + database là một XA transaction:** KafkaTransactionManager không tự bảo đảm commit nguyên tử xuyên hai resource.

**Giữ transaction mở qua HTTP call lâu:** dễ dẫn đến timeout và trì hoãn visibility downstream.

**Self-invocation:** annotation @Transactional có thể không chạy qua proxy.

**Gửi trên thread khác:** transaction context không tự truyền theo executor thread.

**Nuốt exception trong listener transactional:** có thể khiến container commit mặc dù nghiệp vụ chưa hoàn tất.

**Dùng nhầm KafkaTemplate/ProducerFactory:** send có thể không nằm trong transaction đang mở.

**Không theo dõi commit/abort outcome:** không biết record đã committed hay chỉ mới được gửi.

**Không có idempotency:** business retry và external side effect vẫn có nguy cơ lặp.

## 19. Chọn KafkaTransactionManager cho production

| Yêu cầu | Thiết kế phù hợp | Lưu ý chính |
|---|---|---|
| Gửi nhiều Kafka records nguyên tử | KafkaTransactionManager + Spring transaction boundary | Transactional factory, commit/abort |
| Callback producer-only ngắn | `KafkaTemplate.executeInTransaction` | Local transaction scope |
| Consume Kafka rồi ghi Kafka kèm offset | Transactional listener container | Offset-in-transaction, read_committed |
| Ghi SQL và publish Kafka nhất quán | Transactional outbox | Không có XA; cần idempotency |
| Không đọc aborted records | Consumer `read_committed` | Last stable offset và latency |
| Chạy nhiều instance | Unique transaction ID prefix | Producer fencing và lifecycle |
| Retry sau transactional listener failure | Rollback + AfterRollbackProcessor | DLT/recovery và offset correctness |

Một quy trình triển khai thực tế:

1. Xác định rõ resource nào cần atomicity: Kafka-only hay Kafka với external system.
2. Dùng transactional producer factory với prefix khác nhau giữa các instance.
3. Chọn KafkaTemplate dùng đúng factory và manager điều khiển transaction.
4. Chọn boundary: `@Transactional`, `TransactionTemplate`, local transaction hoặc transactional listener container.
5. Với consume–process–produce, bảo đảm output và source offsets tham gia Kafka transaction.
6. Cấu hình consumer downstream với `read_committed` khi cần visibility tương ứng.
7. Giới hạn transaction duration và các tác vụ blocking.
8. Chọn recovery/rollback policy phù hợp, không nuốt exception.
9. Bảo vệ external side effect bằng inbox/outbox hoặc idempotency.
10. Theo dõi commit, abort, fencing, transaction latency và lag; kiểm thử crash windows.

`KafkaTransactionManager` kết nối Spring transaction infrastructure với Kafka producer transaction. Nó đặc biệt hữu ích khi cần gửi nhiều record Kafka nguyên tử hoặc phối hợp output records và source offsets trong consume–process–produce. Để bảo đảm độ tin cậy đầu cuối, cần kết hợp transaction boundary rõ ràng, producer identity duy nhất, consumer `read_committed`, recovery hợp lý và idempotency khi dữ liệu đi ra ngoài Kafka.
