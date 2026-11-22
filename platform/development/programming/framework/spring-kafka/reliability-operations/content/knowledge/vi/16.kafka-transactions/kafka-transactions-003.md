# ProducerFactory transaction capable

Trong Spring Kafka, một producer chỉ có thể tham gia **Kafka transaction** khi factory tạo ra producer được cấu hình để hỗ trợ transaction. Vì vậy, trước khi dùng KafkaTemplate trong một giao dịch, điều cần xác định không chỉ là “KafkaTemplate có gửi được message hay không” mà là **ProducerFactory có transaction capable hay không**, transaction identity được quản lý ra sao và transaction được mở, commit hoặc abort ở đâu.

Chủ đề này nằm trong chương **Transaction Kafka** của module **Spring Kafka Reliability Operations**. Khi cấu hình đúng, nhiều bản ghi Kafka có thể được commit hoặc abort như một đơn vị, và trong mô hình consume-transform-produce, offset của record đầu vào có thể được commit cùng transaction ghi đầu ra. Khi cấu hình sai, service vẫn có thể gửi event bình thường nhưng không có transaction, hoặc thất bại trong runtime vì KafkaTemplate yêu cầu một transaction đang hoạt động.

Bài viết tập trung vào **DefaultKafkaProducerFactory**, **transactionIdPrefix**, **transactionCapable()**, cách kết nối với **KafkaTemplate** và **KafkaTransactionManager**, cũng như các giới hạn về tính nguyên tử, producer fencing, cache, lifecycle và hoạt động production.

## 1. ProducerFactory có trách nhiệm gì?

Trong Spring Kafka, **ProducerFactory<K, V>** là abstraction tạo Kafka producer. Ứng dụng thường sử dụng **DefaultKafkaProducerFactory<K, V>**, sau đó inject factory vào KafkaTemplate.

~~~mermaid
flowchart LR
    A["Business service"] --> T["KafkaTemplate"]
    T --> F["ProducerFactory"]
    F --> P["KafkaProducer"]
    P --> B["Kafka brokers"]
~~~

ProducerFactory chịu trách nhiệm tạo và quản lý producer theo cấu hình:

- Bootstrap servers và security.
- Key/value serializers.
- Acknowledgment, retry và delivery timeout của producer.
- Transactional ID và lifecycle transactional producer khi bật transaction.
- Producer caching/reuse, đóng producer và dọn resource.

KafkaTemplate là API cấp ứng dụng để gửi record. Nó **không tự biến một producer thông thường thành transactional producer**. Khả năng transaction đến từ cấu hình factory và việc có transaction context thích hợp khi gửi.

### 1.1 Hai trạng thái cần phân biệt

Một ProducerFactory có thể:

1. **Không transaction capable**: tạo producer gửi record non-transactional. KafkaTemplate vẫn có thể gửi bình thường.
2. **Transaction capable**: tạo được transactional producers và quản lý transactional.id; KafkaTemplate có thể gửi trong Kafka transaction.

Spring Kafka có contract **ProducerFactory.transactionCapable()** để cho biết factory có hỗ trợ transaction theo cấu hình hiện tại hay không.

Ví dụ kiểm tra lúc khởi động:

~~~java
@Component
public class KafkaTransactionConfigurationCheck {

    public KafkaTransactionConfigurationCheck(
            ProducerFactory<String, String> producerFactory) {

        if (!producerFactory.transactionCapable()) {
            throw new IllegalStateException(
                "ProducerFactory must support Kafka transactions"
            );
        }
    }
}
~~~

Đây là guard phù hợp khi nghiệp vụ yêu cầu transaction và không muốn vô tình chạy ở chế độ non-transactional. Nếu service có nhiều ProducerFactory, cần kiểm tra **đúng factory** mà transactional KafkaTemplate hoặc listener container sử dụng.

### 1.2 Transaction capable không có nghĩa đang có active transaction

Một factory có transaction capability chưa có nghĩa mỗi thread hoặc mỗi lần gửi đều đang nằm trong transaction. Có ba lớp khác nhau:

| Lớp | Câu hỏi |
|---|---|
| ProducerFactory capability | Có tạo và quản lý transactional producer được không? |
| Transaction boundary | Có transaction đang mở cho lần gửi này không? |
| Kafka transaction outcome | Transaction đã commit, abort hay chưa xác định? |

Để có nhóm record atomic, ứng dụng cần cả capability và transaction boundary. Ngoài ra, phải biết kết quả commit thay vì chỉ dựa vào việc KafkaTemplate.send() trả về một future.

## 2. Producer transactional khác producer idempotent ra sao?

Một producer bật **enable.idempotence=true** giúp broker nhận diện và loại bỏ một số lần gửi trùng phát sinh do producer retry trong cùng producer session. Điều đó hữu ích cho độ tin cậy, nhưng **không đồng nghĩa nhiều record nằm trong cùng một transaction**.

Một producer transactional cung cấp thêm cơ chế để commit hoặc abort một nhóm record và có thể phối hợp commit consumer offsets trong Kafka transaction.

| Đặc tính | Producer idempotent | Producer transactional |
|---|---|---|
| Giảm duplicate do producer retry | Có | Có; idempotence là một phần yêu cầu |
| Commit/abort một nhóm record | Không | Có |
| Ghi nhiều partition/topic trong một transaction | Không | Có |
| Gửi consumer offsets vào cùng Kafka transaction | Không | Có |
| Cần transactional.id | Không | Có |
| Downstream read_committed phân biệt aborted record | Không có abort transaction | Có |
| Tự làm HTTP/DB side effect atomic với Kafka | Không | Không |

Ví dụ một service cần ghi hai event đầu ra:

~~~text
OrderAccepted
    -> orders.audit
    -> orders.notification
~~~

Nếu gửi non-transactional, record đầu tiên có thể được broker nhận thành công rồi lần gửi thứ hai thất bại. Hai topic có trạng thái công bố không nhất quán.

Nếu cả hai lần gửi nằm trong **cùng Kafka transaction**:

- Commit thành công: consumer read_committed có thể nhìn thấy cả hai record khi transaction hoàn tất.
- Abort: consumer read_committed không nhận các record thuộc transaction đã abort.
- Transaction chưa hoàn tất: consumer read_committed có thể phải chờ tại Last Stable Offset của partition liên quan.

Consumer read_uncommitted có thể quan sát record transactional trước khi commit hoặc record sau đó bị abort. Bởi vậy, contract đọc ở downstream cũng rất quan trọng.

## 3. Điều kiện để DefaultKafkaProducerFactory transaction capable

Trong Spring Kafka, cách thông dụng là cấu hình **transaction ID prefix** trên DefaultKafkaProducerFactory.

~~~java
DefaultKafkaProducerFactory<String, String> factory =
    new DefaultKafkaProducerFactory<>(producerProperties);

factory.setTransactionIdPrefix("orders-service-instance-a-");
~~~

Khi có prefix, factory có thể tạo các producer transactional với **transactional.id** được quản lý theo prefix và suffix phù hợp. Việc thêm suffix cho phép nhiều producer được tạo hoặc cache cùng một ứng dụng mà không phải tất cả tranh chấp cùng một transactional ID.

Một prefix chỉ là ví dụ. Trong hệ thống nhiều replica, prefix phải duy nhất giữa **các application instance đang hoạt động đồng thời**.

### 3.1 Không nên đặt một transactional.id tĩnh cho mọi instance

Cấu hình nguy hiểm về mặt ownership:

~~~properties
transactional.id=orders-service
~~~

Nếu nhiều producer instance cùng dùng transactional.id này, Kafka sẽ dùng cơ chế producer epoch/fencing để ngăn các producer cũ tiếp tục ghi transaction. Điều đó có thể khiến các pod liên tục fencing nhau thay vì hoạt động ổn định.

Trong Spring Kafka, hãy ưu tiên để DefaultKafkaProducerFactory quản lý transactional.id từ một **transactionIdPrefix** có quy tắc uniqueness rõ ràng cho từng instance. Không đặt một ID tĩnh toàn deployment rồi coi đó là cấu hình scale-out.

### 3.2 transactionIdPrefix là danh tính theo instance

Một convention minh họa:

~~~text
orders-service-prod-<instance-id>-
~~~

Ví dụ ba instance cùng chạy:

~~~text
orders-service-prod-instance-01-
orders-service-prod-instance-02-
orders-service-prod-instance-03-
~~~

Mỗi instance có thể tạo thêm nhiều transactional producer trong phạm vi prefix riêng.

Mục tiêu:

- **Cùng deployment, nhiều pod chạy đồng thời:** prefix không trùng nhau.
- **Restart một logical instance:** có thể dùng lại danh tính ổn định nếu lifecycle có ownership rõ; producer cũ sẽ bị fenced khi instance mới sở hữu transactional ID tương ứng.
- **Rolling deployment:** cần chú ý giai đoạn pod cũ và mới chạy đồng thời; không dùng prefix trùng nếu không muốn chủ động fencing.
- **Scale concurrency:** factory có thể cần nhiều transactional producers cùng lúc; suffix/cache giúp phân biệt từng producer thuộc cùng instance.

Không dùng giá trị thay đổi theo từng lần gửi message để đặt prefix. Transaction ID không phải request ID hay event ID. Nó là định danh dài hạn của transactional producer do Kafka dùng để quản lý epoch và fencing.

### 3.3 transactionCapable() là điều kiện kiểm tra, không phải lệnh mở transaction

Khi factory.transactionCapable() trả về true, điều đó chỉ chứng minh khả năng tạo transactional producer theo cấu hình factory. Lời gọi đó **không**:

- Mở Kafka transaction.
- Gửi event.
- Commit consumer offset.
- Commit dữ liệu trong database.
- Bảo đảm mọi KafkaTemplate trong application đều dùng factory này.

Khi có nhiều factory, việc kiểm tra factory A không nói gì về một KafkaTemplate thực sự sử dụng factory B.

## 4. Bật transaction qua Spring Boot

Spring Boot hỗ trợ cấu hình transaction ID prefix cho producer bằng property chuyên biệt:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092

    producer:
      transaction-id-prefix: orders-service-instance-a-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer

      properties:
        acks: all
        enable.idempotence: true
        transaction.timeout.ms: 60000
~~~

Trong dự án thực tế, **transaction-id-prefix** cần được cung cấp riêng cho từng instance đang chạy, thông qua một nguồn cấu hình ổn định/duy nhất do deployment quản lý. Giá trị instance-a trong ví dụ chỉ dùng cho một instance.

Các điểm quan trọng:

- **spring.kafka.producer.transaction-id-prefix** là property của Spring Boot để factory được tạo theo hướng transactional.
- **transaction.timeout.ms** là timeout của transaction trên producer, có thể bị broker giới hạn bởi cấu hình transaction.max.timeout.ms.
- **acks=all** là lựa chọn quan trọng cho producer durability; transaction không thay thế cấu hình replication/ISR của topic.
- **enable.idempotence=true** minh họa chủ đích. Kafka producer transactional cần idempotence; client/framework cũng áp dụng hoặc yêu cầu cấu hình tương thích.

Đặt transaction-id-prefix **không tự khiến một lời gọi @KafkaListener trở thành consume-transform-produce transaction** nếu listener container chưa được cấu hình transaction tương ứng.

### 4.1 Spring Boot có thể tạo KafkaTransactionManager

Trong nhiều phiên bản Spring Boot, khi cấu hình producer transaction-id-prefix và sử dụng auto-configuration, Boot có thể tự cấu hình một **KafkaTransactionManager** tương ứng.

Tuy nhiên, với ứng dụng tự định nghĩa ProducerFactory, KafkaTemplate hoặc listener container factory, không nên giả định mọi bean tự động ghép đúng với nhau. Cần xác định:

- ProducerFactory mà KafkaTransactionManager sử dụng.
- ProducerFactory mà KafkaTemplate sử dụng.
- Listener container factory có dùng Kafka transaction management hay không.
- Có nhiều PlatformTransactionManager khác nhau trong application hay không.

Nếu tự cấu hình toàn bộ, có thể khai báo KafkaTransactionManager như ví dụ ở phần sau.

### 4.2 Property bị override ngoài ý muốn

Spring Boot tổng hợp properties từ nhiều nguồn, gồm profile, môi trường, Helm/ConfigMap, command-line và Java configuration. Nếu production và staging cùng kết nối một Kafka cluster, phải tránh trùng transactional ID prefix giữa các instance sống đồng thời.

Ví dụ một lỗi khó tìm:

~~~text
application.yml: transaction-id-prefix = orders-service-prod-a-
Kubernetes env: override prefix      = orders-service-prod-a-
Pod A và pod B cùng dùng prefix đó
=> Producer fencing có thể xảy ra
~~~

Chỉ đọc application.yml không đủ. Cần kiểm tra effective configuration trong runtime và quan sát transactional.id thực tế khi có sự cố fencing.

## 5. Tạo ProducerFactory bằng Java

Khi ứng dụng cần custom producer factory, có thể tạo DefaultKafkaProducerFactory, cấu hình serializers và gọi setTransactionIdPrefix().

~~~java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    ProducerFactory<String, String> orderProducerFactory() {

        Map<String, Object> props = new HashMap<>();

        props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "kafka-1:9092,kafka-2:9092,kafka-3:9092"
        );
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(
            ProducerConfig.ACKS_CONFIG,
            "all"
        );
        props.put(
            ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
            true
        );

        DefaultKafkaProducerFactory<String, String> factory =
            new DefaultKafkaProducerFactory<>(props);

        // Chỉ minh họa một application instance.
        // Production phải cấp prefix duy nhất cho từng instance.
        factory.setTransactionIdPrefix(
            "orders-service-instance-a-"
        );

        return factory;
    }

    @Bean
    KafkaTemplate<String, String> orderKafkaTemplate(
            ProducerFactory<String, String> orderProducerFactory) {

        return new KafkaTemplate<>(orderProducerFactory);
    }

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> orderProducerFactory) {

        return new KafkaTransactionManager<>(orderProducerFactory);
    }
}
~~~

Factory, KafkaTemplate và KafkaTransactionManager cùng nhận **đúng ProducerFactory instance**. Điều này giảm nguy cơ template gửi qua một producer thường trong khi transaction manager đang điều phối một transactional producer khác.

Trong ứng dụng thực tế, cấu hình bootstrap servers, credentials, serializers, prefix và timeout nên được lấy từ properties của deployment. Ví dụ trên cố tình dùng cấu hình cố định để làm rõ dependency graph, không phải mẫu triển khai production nhiều replica.

### 5.1 Kiểm tra factory có transaction capable

Có thể thêm kiểm tra tại khởi động:

~~~java
@Bean
ApplicationRunner validateTransactionalFactory(
        ProducerFactory<String, String> orderProducerFactory) {

    return args -> {
        if (!orderProducerFactory.transactionCapable()) {
            throw new IllegalStateException(
                "orderProducerFactory is not transaction capable"
            );
        }
    };
}
~~~

Một lỗi cấu hình bị phát hiện lúc startup thường dễ xử lý hơn so với việc service chạy nhiều giờ rồi mới tới branch nghiệp vụ cần transaction.

### 5.2 Nhiều ProducerFactory trong cùng ứng dụng

Một service có thể gửi cả telemetry non-transactional và business events transactional.

~~~text
Business KafkaTemplate
  -> transactional ProducerFactory
  -> KafkaTransactionManager

Telemetry KafkaTemplate
  -> non-transactional ProducerFactory
  -> gửi độc lập
~~~

Không dùng annotation @Transactional rồi giả định nó quản lý mọi KafkaTemplate. Transaction manager chỉ điều phối producer của factory tương ứng. Các template khác có thể có behavior riêng.

Nếu cần gửi message ngoài transaction bằng KafkaTemplate gắn transactional factory, Spring Kafka có cơ chế cấu hình như **allowNonTransactional** trong các phiên bản hỗ trợ. Đây phải là lựa chọn có chủ đích, vì nó cho phép một số send không tham gia transaction. Không bật chỉ để “hết lỗi” mà không kiểm tra yêu cầu atomicity.

## 6. Kafka transaction lifecycle

Một Kafka transactional producer thực hiện vòng đời logic:

~~~mermaid
flowchart TD
    A["ProducerFactory tạo/lấy producer"] --> B["initTransactions nếu cần"]
    B --> C["beginTransaction"]
    C --> D["send record A"]
    D --> E["send record B"]
    E --> F{"Xử lý thành công?"}
    F -->|Có| G["commitTransaction"]
    F -->|Không| H["abortTransaction"]
    G --> I["Records visible cho read_committed"]
    H --> J["Records bị lọc khỏi read_committed"]
~~~

Kafka transaction có thể bao gồm record ở nhiều topic và partition. Khi commit hoàn tất, transactional records trở nên hợp lệ cho consumer đọc read_committed. Khi abort, records của transaction đó không được trả về cho read_committed consumer.

**transactionCapable=true chưa thay thế begin/commit/abort.** Những thao tác này thường do KafkaTemplate hoặc KafkaTransactionManager cùng Spring transaction infrastructure điều phối, tránh ứng dụng phải quản lý producer thủ công.

### 6.1 Một transaction phải có điểm kết thúc

Một transaction mở quá lâu có thể:

- Giữ Last Stable Offset (LSO) ở các partition có record tham gia.
- Làm read_committed consumer không đọc qua vị trí transaction đang mở.
- Tăng end-to-end latency.
- Gặp transaction timeout và bị abort.
- Giữ resource producer lâu hơn dự kiến.

Không bọc một workflow kéo dài nhiều phút hoặc chờ thao tác HTTP không giới hạn trong Kafka transaction nếu có thể tổ chức lại thành các bước ngắn hơn.

### 6.2 Kafka transaction không giống một HTTP request transaction

Một lệnh Kafka send được đưa vào transaction khi đúng transactional producer được sử dụng. Nhưng việc gọi REST API hoặc ghi database trong cùng Java method không tự được Kafka broker quản lý.

~~~text
begin Kafka transaction
  -> send Kafka record
  -> call external HTTP API
  -> commit Kafka transaction
~~~

Nếu HTTP API thành công rồi Kafka commit thất bại, side effect HTTP vẫn có thể đã xảy ra. Kafka không thể tự rollback response của một hệ thống ngoài Kafka.

Vì vậy, transaction của producer chủ yếu giải quyết atomicity trong **Kafka**, không phải distributed transaction bao trùm mọi dependency của service.

## 7. Sử dụng KafkaTemplate.executeInTransaction

Khi cần gửi nhiều record trong một Kafka transaction tại một đoạn code cụ thể, có thể dùng KafkaTemplate.executeInTransaction().

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishTwoEvents(String orderId) {
        kafkaTemplate.executeInTransaction(operations -> {

            operations.send(
                "orders.audit",
                orderId,
                "ORDER_ACCEPTED"
            );

            operations.send(
                "orders.notifications",
                orderId,
                "NOTIFY_CUSTOMER"
            );

            return null;
        });
    }
}
~~~

Ở đây, cả hai send tham gia cùng transaction do template quản lý. Nếu callback ném exception hoặc transaction không thể commit, transaction được xử lý theo abort/failure semantics của KafkaTemplate.

Lưu ý:

- executeInTransaction() cần transactional ProducerFactory.
- Đoạn code trong callback cần có thời gian thực thi hữu hạn.
- KafkaTemplate.send() trả về kết quả bất đồng bộ; nếu cần xác nhận chi tiết mỗi send, hãy xử lý futures/callbacks phù hợp mà không che lỗi.
- Transaction commit phụ thuộc broker response. Không log “đã công bố thành công” chỉ vì hàm send() được gọi mà chưa có kết quả transaction.
- Nếu executeInTransaction() được gọi khi ngoài nó đã có một transaction khác, không nên giả định callback tự động gia nhập transaction bên ngoài; Spring Kafka có semantics riêng về transaction do template tạo. Cần xác định transaction boundary muốn dùng.

### 7.1 Khi nào nên dùng executeInTransaction?

Phù hợp khi:

- Một method cần công bố nhiều Kafka records như một đơn vị.
- Không cần tạo Spring-managed transaction cho toàn service method.
- Muốn transaction boundary nhìn thấy ngay trong code.
- Không cần phối hợp consumer offsets từ listener container.

Nếu cần kết hợp nhiều method cùng transaction và dùng declarative transaction, KafkaTransactionManager có thể phù hợp hơn.

## 8. Sử dụng KafkaTransactionManager và @Transactional

KafkaTransactionManager tích hợp Kafka transactions vào mô hình transaction của Spring.

Ví dụ:

~~~java
@Service
public class PaymentEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public PaymentEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishPaymentResult(
            String paymentId,
            String result) {

        kafkaTemplate.send(
            "payments.status",
            paymentId,
            result
        );

        kafkaTemplate.send(
            "payments.audit",
            paymentId,
            "AUDIT:" + result
        );
    }
}
~~~

Khi method được gọi qua Spring transaction proxy và transaction manager được chọn đúng:

1. KafkaTransactionManager bắt đầu Kafka transaction.
2. KafkaTemplate dùng producer gắn với transaction context đó.
3. Các send trong method cùng transaction.
4. Method hoàn tất bình thường: transaction manager commit.
5. Method ném exception thuộc rollback policy: transaction manager rollback/abort.

### 8.1 Đừng chọn nhầm TransactionManager

Nếu ứng dụng có DataSourceTransactionManager, JpaTransactionManager và KafkaTransactionManager, annotation @Transactional không chỉ định manager có thể sử dụng manager mặc định không như mong muốn.

Ví dụ:

~~~java
@Transactional
public void publish() {
    kafkaTemplate.send("orders", "k", "v");
}
~~~

Đoạn này **không tự chứng minh có Kafka transaction**. Cần biết manager nào đang được chọn, KafkaTemplate có đồng bộ transaction phù hợp hay không và factory có transaction capable không.

Cách rõ ràng hơn là chỉ định tên:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
~~~

Nếu mục tiêu là transaction database đồng thời phát Kafka message, cần xem xét outbox hoặc cách phối hợp transaction có failure window được tài liệu hóa, không giả định hai transaction manager sẽ tạo một atomic distributed commit.

### 8.2 Self-invocation không đi qua transaction proxy

Một phương thức được đánh dấu @Transactional nhưng bị gọi từ phương thức khác **trong cùng bean** có thể không đi qua Spring proxy. Khi đó transaction annotation có thể không được áp dụng như dự kiến.

~~~java
@Service
public class ExampleService {

    public void outer() {
        inner(); // Self-invocation; chú ý Spring proxy semantics.
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void inner() {
        // Gửi Kafka records...
    }
}
~~~

Với Spring proxy-based transaction management mặc định, cách gọi này không tạo Kafka transaction chỉ nhờ annotation ở inner(). Cần thiết kế boundary qua bean/proxy đúng hoặc dùng executeInTransaction() khi phù hợp.

### 8.3 Không nuốt exception nếu muốn rollback

Nếu transactional method bắt exception, chỉ log rồi return bình thường, transaction manager có thể xem method thành công và commit các Kafka records đã gửi.

~~~java
try {
    kafkaTemplate.send("orders", key, value);
} catch (Exception ex) {
    log.error("send failed", ex);
    // Không tự động rollback nếu method vẫn return bình thường.
}
~~~

Nếu lỗi cần abort transaction, hãy để exception lan ra hoặc đánh dấu rollback-only theo Spring transaction API phù hợp. Đồng thời, cần xét lỗi send bất đồng bộ xảy ra sau khi send() đã trả về.

## 9. ProducerFactory transaction capable trong consume-transform-produce

Một use case quan trọng là service:

1. Đọc record từ topic input.
2. Biến đổi dữ liệu.
3. Ghi record sang topic output.
4. Commit offset input.

Nếu bước 3 thành công nhưng bước 4 thất bại, input có thể được đọc lại và output trùng. Nếu bước 4 commit trước nhưng bước 3 thất bại, input có thể bị bỏ qua mà không có output.

Kafka transaction cho phép đưa **output records và input consumer offsets** vào cùng Kafka transaction, tạo nền tảng exactly-once processing trong phạm vi Kafka.

~~~mermaid
flowchart LR
    I["Input topic"] --> C["Spring Kafka listener container"]
    C --> L["Business transform"]
    L --> T["Transactional KafkaTemplate"]
    T --> O["Output topic"]
    C --> K["Kafka transaction: output + consumed offsets"]
    K --> G["Commit hoặc abort atomic trong Kafka"]
~~~

Để đạt behavior mong muốn, cần:

- Transaction-capable ProducerFactory.
- KafkaTransactionManager hoặc container transaction configuration phù hợp với Spring Kafka version.
- KafkaTemplate dùng đúng transactional factory.
- Listener container được cấu hình transaction thật sự.
- Consumer group offset được đưa vào transaction theo cơ chế container.
- Downstream consumer cần chỉ thấy committed output thì dùng isolation.level=read_committed.
- Broker/client/transaction settings hỗ trợ semantics yêu cầu.

### 9.1 Listener không cần tự commit offset thủ công khi container đã quản lý transaction

Ví dụ logic listener:

~~~java
@KafkaListener(
    topics = "orders.in",
    groupId = "orders-transformer",
    containerFactory = "transactionalListenerFactory"
)
public void transform(OrderCreated event) {

    String output = transformService.convert(event);

    kafkaTemplate.send(
        "orders.out",
        event.orderId(),
        output
    );
}
~~~

Code trên chỉ cho thấy logic nghiệp vụ. **Điều kiện quyết định** là transactionalListenerFactory phải được cấu hình đúng để mở Kafka transaction cho listener và để container quản lý offsets trong transaction. Chỉ vì listener gọi KafkaTemplate transactional không đảm bảo EOS nếu container factory chưa gắn đúng transaction management.

Ở một số Spring Kafka/Spring Boot version, framework có thể tự liên kết KafkaTransactionManager với container factory phù hợp. Với factory custom, cần kiểm tra API cấu hình transaction trên ContainerProperties và bean wiring của version đang dùng.

### 9.2 Khi listener ném exception

Nếu listener đang chạy trong Kafka transaction và ném exception:

- Container thực hiện rollback/abort Kafka transaction theo policy.
- Output records đã gửi trong transaction không được downstream read_committed nhìn thấy.
- Offset input được đưa vào transaction đó không được commit.
- Input có thể được nhận lại để retry sau rollback.
- Recovery policy cho transactional listener thường liên quan cơ chế AfterRollbackProcessor, không nên mặc định dùng DefaultErrorHandler giống non-transactional listener.

Side effect ngoài Kafka vẫn không tự rollback theo Kafka transaction.

### 9.3 Exactly-once có phạm vi rõ ràng

Kafka EOS bảo vệ chuỗi **consume Kafka → produce Kafka → commit consumer offset trong Kafka transaction** khi cấu hình đúng.

Nó không tự bảo đảm:

- Database insert chỉ diễn ra một lần.
- HTTP API chỉ được gọi một lần.
- Email chỉ được gửi một lần.
- Consumer khác đọc read_uncommitted không thấy aborted records.
- Business event không bị lặp từ producer upstream.

Để bảo vệ side effect bên ngoài Kafka, cần idempotency key, inbox/outbox, unique constraint hoặc quy trình bù trừ tùy use case.

## 10. Kafka producer transaction ID và fencing

Kafka dùng **transactional.id** để nhận diện producer logic, theo dõi epoch và chặn producer cũ khi producer mới chiếm cùng identity. Cơ chế này gọi là **producer fencing**.

Một ví dụ:

~~~text
Instance A mở transaction với transactional.id = orders-prod-slot-1-0
A bị treo hoặc mất kết nối

Instance B được khởi động với cùng transactional.id
B khởi tạo transaction và có epoch mới

A cố tiếp tục gửi/commit
=> A bị fenced; không được tiếp tục giao dịch cũ
~~~

Fencing ngăn producer zombie tiếp tục ghi như thể nó vẫn sở hữu identity hợp lệ.

### 10.1 Lỗi do trùng prefix

Nếu hai pod đang hoạt động sử dụng cùng transactionIdPrefix, factory của chúng có thể sinh cùng transactional.id suffix. Kafka sẽ fencing các producer tranh chấp, gây lỗi khi gửi/commit.

Triệu chứng:

- ProducerFencedException hoặc lỗi transaction liên quan.
- Transaction commit thất bại.
- Retry/restart liên tục sau rolling deployment.
- Một instance khởi động thì instance khác bắt đầu lỗi.
- Consumer read_committed chờ transaction hoàn tất hoặc timeout.

Giải pháp ưu tiên là sửa chiến lược cấp identity cho instance và lifecycle rollout, không phải bắt ProducerFencedException rồi retry mãi trên producer đã mất quyền.

### 10.2 Cách thiết kế prefix

Có ba yêu cầu:

1. **Uniqueness giữa các instance cùng hoạt động.**
2. **Ổn định ở mức logical instance khi mong muốn fencing producer cũ sau restart.**
3. **Không buộc mọi event tạo một transactional ID mới.**

Trong Kubernetes, có thể chọn danh tính theo slot của StatefulSet hoặc một instance identity được deployment quản lý. Với Deployment tạo pod không có identity bền vững, cần đảm bảo prefix duy nhất cho mỗi pod đang chạy và hiểu rằng identity thay đổi qua restart có thể làm transactional IDs cũ chờ expire/cleanup thay vì được tái sử dụng ngay.

Không tự dùng group.id làm transactional.id prefix cho mọi replica; group.id của consumer thường cố ý giống nhau giữa các replica, trong khi transactional prefix cần uniqueness.

### 10.3 Producer fencing là lỗi cần xử lý ở lifecycle

Khi producer bị fenced, nó không thể tiếp tục transaction như cũ. Nên:

- Ghi log transactional identity, producer instance và exception.
- Dừng sử dụng producer cũ theo framework policy.
- Kiểm tra có pod duplicate prefix hoặc rollback pod cũ chưa dừng.
- Để factory/container khởi tạo producer hợp lệ theo lifecycle.
- Không retry vô hạn cùng producer bị fenced.
- Kiểm tra trạng thái input offset, output visibility và khả năng replay.

## 11. Producer cache, concurrency và transactional.id suffix

DefaultKafkaProducerFactory có cơ chế quản lý producer cache để tái sử dụng transactional producer. Một transaction không nhất thiết phải khởi tạo một KafkaProducer mới từ đầu rồi đóng ngay sau khi commit.

Khi KafkaTemplate hoặc transaction manager hoàn tất transaction, factory có thể đưa producer về cache thay vì đóng connection vật lý ngay. Điều này giúp giảm chi phí khởi tạo transaction và network connections.

### 11.1 Tại sao cache quan trọng?

Khởi tạo transactional producer có thể cần tương tác với transaction coordinator, trong đó có quá trình initTransactions(). Nếu mỗi transaction đều phải init producer mới, latency và broker load có thể tăng.

Reuse producer hợp lý giúp:

- Giảm overhead create/close.
- Ổn định connection và metadata.
- Giảm chi phí initTransactions.
- Hỗ trợ throughput cao hơn ở nhiều transaction ngắn.

Tuy nhiên, cache cần được quản lý cùng concurrency, transaction lifetime và broker expiration.

### 11.2 Số producer có thể nhiều hơn một

Nếu một application có bốn listener threads cùng xử lý Kafka transactions, có thể cần nhiều transactional producers đồng thời. Factory dùng transactional.id prefix/suffix để các producer đó không tranh chấp nhau.

Một vài dòng log:

~~~text
orders-service-instance-a-0
orders-service-instance-a-1
orders-service-instance-a-2
orders-service-instance-a-3
~~~

Đây chỉ là ví dụ format ID, không phải cam kết suffix chính xác của mọi framework version.

Cần lưu ý số transactional producers được tạo/cache có thể phụ thuộc cấu hình và transaction usage thực tế, không phải lúc nào cũng đúng bằng concurrency. Các phiên bản Spring Kafka có cách cấp suffix và cache khác nhau.

### 11.3 ProducerPerThread không phải group assignment

Một số cấu hình ProducerFactory có lựa chọn producer theo thread. Không nên nhầm thread-bound producer với consumer group partition assignment:

- Kafka consumer threads có thể tăng theo listener concurrency.
- Kafka transactional producer có identity riêng.
- Một transaction manager quản lý producer qua transaction context.
- Một KafkaTemplate có thể được gọi từ nhiều thread, nhưng transaction participation không tự động lan sang thread khác.

Nếu ứng dụng dùng asynchronous executor hoặc thread handoff, cần kiểm tra transaction context có được giữ trong thread thực hiện send hay không. Không nên giả định @Transactional trên thread A sẽ tự áp dụng cho send thực hiện bởi thread B.

## 12. Producer expiration và maxAge

Kafka broker có cấu hình như **transactional.id.expiration.ms** để quản lý transactional IDs không còn hoạt động. Nếu một transactional producer nằm trong cache quá lâu mà không được sử dụng, ID của nó có thể hết hạn ở broker.

Một trường hợp có thể gặp:

1. Factory tạo transactional producer và hoàn tất transaction.
2. Producer được đưa vào cache.
3. Không có traffic trong thời gian dài.
4. Broker hết hạn transactional ID do không còn hoạt động.
5. Khi factory tái sử dụng producer cũ, có thể gặp lỗi liên quan epoch/producer fencing.

Trong các phiên bản Spring Kafka hỗ trợ, DefaultKafkaProducerFactory cung cấp cấu hình **maxAge** để loại producer khỏi cache trước khi broker hết hạn transactional ID.

Nguyên tắc:

- Chọn maxAge nhỏ hơn transactional.id.expiration.ms của broker với khoảng dự phòng.
- Theo dõi số lượng producer trong cache và tuổi producer.
- Không đặt maxAge quá nhỏ khiến initTransactions thường xuyên mà không cần thiết.
- Kiểm tra behavior theo Spring Kafka version và traffic pattern.

Nếu service hoạt động theo đợt, có khoảng idle dài rồi traffic tăng đột ngột, bài toán producer cache expiration càng đáng chú ý.

## 13. Transaction timeout và các giới hạn

Transactional producer phải kết thúc transaction trong khoảng thời gian được broker cho phép.

Một vài cấu hình thường gặp:

| Cấu hình | Vai trò |
|---|---|
| transaction.timeout.ms | Thời gian tối đa producer yêu cầu cho transaction |
| transaction.max.timeout.ms | Giới hạn timeout transaction phía broker |
| delivery.timeout.ms | Giới hạn thời gian gửi message của producer, không đồng nghĩa transaction timeout |
| request.timeout.ms | Timeout request mạng, không phải toàn bộ transaction |
| acks | Mức ACK producer cần; durability còn phụ thuộc replication/ISR |
| enable.idempotence | Bật cơ chế chống duplicate do producer retry |
| retries | Retry các producer request trong giới hạn delivery timeout |
| transactional.id | Identity của một transactional producer |
| transactionIdPrefix (Spring) | Prefix để factory cấp các transactional IDs |

Không được coi transaction.timeout.ms là backoff cho consumer. Đây là timeout transaction do Kafka coordinator quản lý.

### 13.1 Transaction mở quá lâu

Nếu listener mở Kafka transaction rồi chờ HTTP API 2 phút, trong khi transaction.timeout.ms chỉ 60 giây, transaction có thể bị coordinator abort. Khi method cố commit, ứng dụng nhận exception.

Tăng timeout không phải giải pháp mặc định. Có thể cần:

- Tách công việc ngoài Kafka transaction.
- Giảm thời gian xử lý mỗi input record/batch.
- Áp dụng timeout rõ cho downstream.
- Giảm tải và tăng capacity nếu cần.
- Chọn transaction timeout phù hợp với thời gian xử lý p99 mà broker cho phép.

Transaction kéo dài còn làm downstream read_committed phải chờ tại LSO ở những partition có record thuộc transaction đang mở.

### 13.2 Producer send đã ACK nhưng transaction chưa commit

Một producer có thể nhận kết quả ACK cho send record nhưng transaction sau đó bị abort. Điều này không mâu thuẫn:

- Send ACK nghĩa là broker đã nhận/ghi record theo producer ACK policy.
- Transaction commit quyết định nhóm records đó có được xem là committed không.
- read_committed consumer chỉ thấy committed transactional records.

Vì thế, không phát thông báo nghiệp vụ “đã công bố sự kiện” chỉ vì một send callback thành công khi transaction còn mở.

## 14. Transaction commit, abort và tình trạng kết quả không rõ

Không phải mọi lỗi producer đều giống nhau. Nếu một send thất bại, framework có thể cần abort transaction. Nếu commit thất bại do network interruption, ứng dụng đôi khi khó xác định chắc chắn broker đã hoàn tất commit hay chưa nếu chỉ dựa vào exception ở phía client.

Đừng tự khẳng định:

~~~text
commitTransaction() ném timeout
=> chắc chắn transaction đã abort
~~~

Kết quả có thể cần được xác minh theo Kafka client/transaction coordinator semantics và dấu vết nghiệp vụ. Khi retry toàn bộ business operation, phải xét khả năng output đã được commit ở lần trước nhưng response bị mất.

Các nguyên tắc:

- Không retry vô hạn trên producer fatal/fenced.
- Để transaction manager và KafkaProducer xử lý abort theo contract API.
- Thiết kế event id và side effect downstream để chịu duplicate ở ranh giới không chắc chắn.
- Theo dõi commit/abort rate và transaction coordinator errors.
- Dùng read_committed consumer để quan sát output phù hợp, thay vì diễn giải từ riêng send ACK.

## 15. Giao dịch Kafka và database: giới hạn atomicity

Một nghiệp vụ thường cần vừa ghi database vừa phát event. KafkaTransactionManager không tự tạo transaction phân tán atomic với database.

Ví dụ:

~~~text
Begin DB transaction
    update orders table
Commit DB transaction

Begin Kafka transaction
    send OrderUpdated
Commit Kafka transaction
~~~

Nếu DB commit thành công nhưng Kafka commit thất bại, database đã thay đổi nhưng event có thể không được công bố. Đảo thứ tự cũng có failure window ngược lại.

Spring hỗ trợ một số cơ chế đồng bộ transaction giữa Kafka và database, nhưng nếu không có một distributed atomic commit chung thì vẫn cần hiểu rõ thứ tự commit và cách xử lý lỗi ở giữa. Một transaction manager được inject vào method không đồng nghĩa hai hệ thống đã có exactly-once xuyên biên giới.

### 15.1 Transactional outbox

Một giải pháp thường dùng:

1. Trong cùng một DB transaction, ghi business table và outbox row.
2. Commit DB transaction.
3. Một publisher hoặc CDC process đọc outbox.
4. Publisher gửi event sang Kafka với retry.
5. Đánh dấu/duy trì tiến độ xuất bản theo thiết kế và idempotency.

Outbox không nhất thiết loại bỏ mọi duplicate Kafka event. Consumer vẫn cần xử lý idempotent. Nhưng nó tránh một số khoảng lỗi “DB đã commit mà không có ý định phát event được lưu bền vững”.

### 15.2 Chọn phạm vi transaction

Nếu toàn bộ yêu cầu là ghi hai Kafka topics atomic với nhau, ProducerFactory transaction capable có thể là cơ chế đúng.

Nếu cần điều phối SQL database, Kafka, HTTP API và email như một business workflow dài, cần thiết kế orchestration, outbox/inbox hoặc saga phù hợp thay vì giữ Kafka transaction mở cho toàn bộ workflow.

## 16. Giám sát ProducerFactory transaction capable trong production

Một hệ thống có producer transactional cần giám sát cả **configuration** lẫn **transaction outcome**.

| Nhóm | Tín hiệu cần quan sát |
|---|---|
| Factory | transactionCapable, transactionIdPrefix, số factory/template |
| Producer | Producer creation, cache reuse, producer close, age |
| Transaction | Begin/commit/abort rate, commit latency, timeout |
| Failure | Fenced producer, coordinator errors, authentication/ACL |
| Send | Record send success/failure, request latency, retry rate |
| Broker | Transaction coordinator health, ISR, replica lag |
| Consumer | read_committed lag, LSO/HW, records received |
| Business | Event id, duplicate detection, downstream consistency |

### 16.1 Startup log hữu ích

Có thể log một số giá trị đã được làm sạch:

~~~text
service=orders-transformer
environment=prod
producerFactory=orderProducerFactory
transactionCapable=true
transactionIdPrefix=orders-prod-instance-17-
transactionManager=kafkaTransactionManager
~~~

Cần tránh log credential hoặc sensitive Kafka configuration. Không in ra nguyên cấu hình security.

Trong hệ thống dùng nhiều factory, log riêng từng factory và các template/container sử dụng nó. Việc application có **một** factory capable không chứng minh listener mong muốn dùng factory đó.

### 16.2 Những lỗi cần cảnh báo

- ProducerFencedException hoặc epoch errors tăng đột biến.
- Kafka transaction bị abort nhiều hơn bình thường.
- Transaction commit latency tăng.
- Transaction timeout xuất hiện.
- Producer cache liên tục bị miss hoặc tạo producer quá nhiều.
- Read_committed consumer lag tăng trong khi HW tiến triển nhưng LSO đứng yên.
- Producer send success nhưng nghiệp vụ không thấy output committed.
- Duplicate side effect sau restart/retry.

Không chỉ theo dõi tỷ lệ send thành công; record có thể được gửi nhưng transaction sau đó abort.

## 17. Các tình huống sai cấu hình

| Tình huống | Triệu chứng | Hướng xử lý |
|---|---|---|
| Factory không có transactionIdPrefix | transactionCapable=false; transactional send lỗi | Cấu hình prefix và kiểm tra factory |
| Hai pod dùng cùng prefix | Fencing lặp lại khi start/commit | Cấp prefix duy nhất cho instance sống đồng thời |
| KafkaTemplate dùng nhầm factory | Không tham gia transaction như mong muốn | Kiểm tra dependency injection, bean qualifiers |
| @Transactional chọn DB manager | Kafka transaction không như dự kiến | Chỉ định đúng transactionManager |
| Self-invocation gọi @Transactional | Không có transaction qua proxy | Thiết kế lại boundary hoặc dùng executeInTransaction |
| Kafka send ngoài transaction trên transactional template | Có thể ném lỗi nếu không được phép non-transactional | Gọi trong transaction hoặc cấu hình rõ yêu cầu gửi ngoài tx |
| Listener container chưa transaction-enabled | Output/offset không atomic | Cấu hình container transaction và kiểm chứng |
| Prefix chung cho group id | Pod trong cùng group có thể trùng transactional IDs | Tách logical consumer group ID với transactional prefix riêng instance |
| Producer cache idle lâu | Fencing/epoch error lúc reuse | Cân nhắc maxAge dưới broker expiration |
| Transaction chờ downstream lâu | Timeout, abort, read_committed stall | Giảm transaction lifetime |
| DLT/retry side effect ngoài Kafka | Duplicate sau replay | Idempotency và recovery policy |
| read_uncommitted downstream | Có thể thấy records aborted | Đặt isolation.level=read_committed nơi cần semantics committed |

## 18. Quy trình điều tra khi transaction không hoạt động

Khi ứng dụng báo “đã bật transaction nhưng vẫn gửi thiếu một phần event” hoặc KafkaTemplate ném lỗi:

1. Xác định **ProducerFactory instance** mà KafkaTemplate thật sự sử dụng.
2. Kiểm tra **transactionCapable()** tại runtime.
3. Kiểm tra **transactionIdPrefix** và transactional.id sinh ra, bảo đảm không trùng giữa các pod.
4. Xác định transaction boundary: executeInTransaction, @Transactional với KafkaTransactionManager, hay container transaction.
5. Nếu dùng @Transactional, xác nhận method được gọi qua Spring proxy và manager đúng.
6. Nếu dùng @KafkaListener, kiểm tra container factory, transaction manager và offset-in-transaction configuration.
7. Kiểm tra KafkaProducer exceptions, đặc biệt fencing, timeout, coordinator hoặc serialization.
8. So sánh producer send ACK với transaction commit outcome, không coi hai thứ là một.
9. Kiểm tra downstream isolation.level và LSO nếu record “chưa xuất hiện”.
10. Kiểm tra broker transaction max timeout, topic replication/ISR và ACL.
11. Nếu có database/HTTP side effect, xác định việc nào đã commit và việc nào có thể lặp.
12. Sau khi sửa, thử commit/abort, restart và failure injection trong staging trước khi mở rộng rollout.

Không tự reset consumer group offset chỉ vì output chưa hiện ra. Nguyên nhân có thể là transaction chưa commit, abort hoặc downstream read_committed đang chờ LSO.

## 19. Integration test cho transaction-capable ProducerFactory

Unit test mock KafkaTemplate không thể chứng minh Kafka broker hỗ trợ transactional commit, abort và consumer isolation. Nên dùng Kafka broker tích hợp, ví dụ Testcontainers hoặc môi trường staging.

### 19.1 Kiểm tra capability

- Khởi tạo application context với cấu hình transactional prefix.
- Lấy ProducerFactory thật từ context.
- Xác nhận transactionCapable() trả true.
- Xác nhận KafkaTemplate và KafkaTransactionManager dùng đúng factory.
- Kiểm tra prefix do deployment inject.

### 19.2 Commit thành công

- Bắt đầu transaction qua executeInTransaction hoặc KafkaTransactionManager.
- Gửi hai records đến topic/partition thử nghiệm.
- Commit transaction.
- Dùng read_committed consumer để đọc.
- Xác nhận cả hai records xuất hiện.
- Ghi nhận transaction latency và offset của output.

### 19.3 Abort

- Bắt đầu transaction.
- Gửi hai records.
- Ném exception trước commit.
- Xác nhận transaction abort/rollback.
- Dùng read_committed consumer xác nhận hai records không xuất hiện.
- Nếu dùng read_uncommitted consumer để thử, hiểu rằng nó có thể nhìn thấy records của transaction đã abort.

### 19.4 Fencing

- Khởi tạo producer transactional với transactional.id xác định trong test environment.
- Khởi tạo producer thứ hai sử dụng cùng identity.
- Xác nhận producer cũ bị fencing theo Kafka semantics.
- Kiểm tra service không retry vô hạn producer cũ.
- Đảm bảo test không dùng transactional IDs của production.

### 19.5 Consume-transform-produce

- Tạo input topic và output topic.
- Cấu hình listener container với Kafka transaction.
- Gửi input record.
- Listener ghi output và cho container commit input offset cùng transaction.
- Xác nhận read_committed downstream đọc output sau commit.
- Lặp lại với listener ném exception; xác nhận output bị rollback và input chưa được commit theo transactional flow.
- Xác nhận recovery/retry có thể hoàn tất sau đó mà không tạo side effect ngoài Kafka trùng.

### 19.6 Crash và producer reuse

- Tạo giao dịch rồi dừng instance trước commit trong test environment.
- Khởi động instance hợp lệ với prefix đúng.
- Kiểm tra producer fencing/abort cleanup theo lifecycle.
- Cho factory idle lâu theo thời gian test được rút ngắn nếu có thể.
- Xác nhận producer reuse/expiration policy không tạo lỗi bất thường.
- Kiểm tra các records committed được tiêu thụ bình thường sau recovery.

## 20. Checklist trước khi triển khai

**Cấu hình factory**

- [ ] ProducerFactory dự kiến trả transactionCapable()=true.
- [ ] DefaultKafkaProducerFactory được cấu hình transactionIdPrefix.
- [ ] Prefix duy nhất giữa các application instance đang chạy.
- [ ] KafkaTemplate và KafkaTransactionManager dùng đúng factory.
- [ ] Serializers, acks, security và transaction timeout phù hợp.
- [ ] Producer cache và maxAge được xem xét theo traffic/expiration.

**Transaction boundary**

- [ ] Các gửi cần atomic nằm trong cùng transaction thực sự.
- [ ] Có commit/abort rõ, không nuốt exception cần rollback.
- [ ] @Transactional dùng đúng manager và proxy boundary.
- [ ] Không gửi ra khỏi transaction một cách vô tình.
- [ ] Transaction không giữ mở quá lâu vì external I/O.

**Consume-transform-produce**

- [ ] Listener container thực sự dùng Kafka transaction management.
- [ ] Output records và input offset cùng transaction khi yêu cầu EOS.
- [ ] Downstream dùng read_committed khi cần visibility của committed transactions.
- [ ] Retry/rollback/AfterRollbackProcessor được hiểu đúng theo version.
- [ ] Side effect ngoài Kafka có idempotency hoặc outbox/inbox.

**Vận hành**

- [ ] Có metric transaction begin/commit/abort và fencing.
- [ ] Theo dõi producer cache, age, transaction timeout và coordinator health.
- [ ] Có runbook cho trùng prefix, zombie producer và commit failure.
- [ ] Đã thử commit, abort, restart và consumer read_committed trong staging.
- [ ] Không tuyên bố atomicity xuyên database/HTTP khi chưa có cơ chế riêng.

**ProducerFactory transaction capable** là điều kiện nền tảng để Spring Kafka tạo producer có thể tham gia Kafka transaction. Với DefaultKafkaProducerFactory, cấu hình transaction ID prefix cho phép factory quản lý transactional producers và KafkaTemplate/KafkaTransactionManager có thể điều phối begin, commit hoặc abort. Tuy nhiên, capability chỉ là bước đầu: transactional ID phải được cấp đúng cho từng instance, transaction boundary phải thật sự hoạt động, listener offset phải được phối hợp khi cần EOS và downstream phải đọc read_committed nếu muốn loại bỏ aborted records. Độ tin cậy production đến từ sự nhất quán giữa factory, template, transaction manager, broker và quy trình phục hồi — không chỉ từ một property được bật.

