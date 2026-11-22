# Vai trò của Spring for Apache Kafka và Spring Boot auto-configuration

## Mục tiêu bài học

Apache Kafka cung cấp Java client để producer gửi record và consumer đọc record. Khi xây dựng ứng dụng Spring, nhóm phát triển thường cần thêm dependency injection, cấu hình tập trung, quản lý vòng đời consumer, listener annotation, xử lý lỗi và tích hợp với hệ sinh thái Spring. Spring for Apache Kafka cung cấp các thành phần đó; Spring Boot auto-configuration kết nối chúng với cấu hình ứng dụng để giảm lượng cấu hình thủ công.

Sau bài học, bạn có thể:

- Phân biệt vai trò của Apache Kafka Java client, Spring for Apache Kafka và Spring Boot.
- Giải thích `KafkaTemplate`, `ProducerFactory`, `ConsumerFactory` và listener container.
- Hiểu Spring Boot tạo các bean Kafka mặc định dựa trên classpath và cấu hình như thế nào.
- Cấu hình broker, producer, consumer và listener qua `application.yml`.
- Sử dụng `@KafkaListener` và inject `KafkaTemplate` trong service.
- Biết khi nào Boot auto-configuration tạo bean mặc định và khi nào bean tùy chỉnh thay thế cấu hình đó.
- Chọn cách tùy biến phù hợp mà không tạo nhiều cấu hình producer/consumer trùng lặp.
- Kiểm tra cấu hình thực tế, xử lý lỗi khởi động và tổ chức cấu hình theo môi trường.

## 1. Ba lớp công nghệ trong ứng dụng Spring Kafka

### 1.1. Apache Kafka Java client

Kafka client là thư viện Java chính thức để giao tiếp với Kafka cluster. Hai API cốt lõi là:

- `KafkaProducer<K, V>` gửi record đến topic.
- `KafkaConsumer<K, V>` subscribe topic, poll record và quản lý offset.

Client cung cấp các khả năng như serialization, partitioning, batching, retry, consumer group, commit offset và transaction. Nếu dùng trực tiếp, ứng dụng phải tự tạo, cấu hình và quản lý vòng đời producer/consumer.

### 1.2. Spring for Apache Kafka

Spring for Apache Kafka là framework tích hợp Kafka với mô hình lập trình Spring. Nó xây dựng abstraction và thành phần quản lý quanh Java client, ví dụ:

- `KafkaTemplate` cung cấp API gửi message theo phong cách Spring.
- `ProducerFactory` tạo và quản lý producer.
- `ConsumerFactory` tạo consumer cho listener container.
- Listener container chạy vòng lặp poll và gọi method được đánh dấu `@KafkaListener`.
- `KafkaAdmin` hỗ trợ quản trị tài nguyên Kafka như khai báo topic.
- Error handler, retry, recovery, transaction và message conversion tích hợp với Spring.

Spring Kafka không thay thế Kafka broker hay Kafka protocol. Cuối cùng, các thao tác vẫn được thực hiện bởi Kafka Java client.

### 1.3. Spring Boot auto-configuration

Spring Boot tự cấu hình các bean phổ biến dựa trên dependency có mặt trong classpath, cấu hình ngoài ứng dụng và các bean do ứng dụng tự khai báo. Với Spring Kafka, Boot có thể tạo producer factory, consumer factory, `KafkaTemplate`, listener container factory và các thành phần quản trị cần thiết.

Mục tiêu là giúp ứng dụng bắt đầu với một cấu hình nhỏ, sau đó chỉ tùy biến phần thực sự cần. Boot không tự tạo Kafka cluster; `bootstrap-servers` vẫn phải trỏ đến broker đang chạy.

```text
application.yml / environment variables
                 |
                 v
       Spring Boot configuration
                 |
                 v
          KafkaProperties
                 |
                 v
        Boot auto-configuration
                 |
       +---------+----------+
       |         |          |
       v         v          v
 Producer     Consumer   Listener
 Factory      Factory    Container Factory
       |         |          |
       v         v          v
 KafkaTemplate  KafkaConsumer  @KafkaListener
       |         |          |
       +---------+----------+
                 |
                 v
             Kafka cluster
```

## 2. Dependency và cấu hình khởi đầu

### 2.1. Thêm Spring Kafka vào dự án

Với dự án Spring Boot dùng Maven, thêm dependency `spring-kafka`. Nếu dự án đã dùng Spring Boot parent hoặc dependency management/BOM, thường để Boot quản lý version tương thích:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
```

Không nên tự chọn một version Spring Kafka bất kỳ mà không kiểm tra ma trận tương thích với Spring Boot, Spring Framework và Kafka client. Spring Boot dependency management đã chọn một bộ version được kiểm thử cùng nhau; chỉ override khi có lý do và đã kiểm tra tương thích.

Với ứng dụng Java không dùng Boot, vẫn có thể dùng Spring Kafka nhưng phải tự khai báo cấu hình và bean cần thiết. Nội dung bài tập trung vào Spring Boot.

### 2.2. Khai báo broker trong `application.yml`

Ví dụ cấu hình tối thiểu cho producer và consumer dùng String:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
```

Ý nghĩa:

- `bootstrap-servers`: địa chỉ broker dùng để khởi đầu kết nối và lấy metadata.
- `consumer.group-id`: consumer group mặc định cho listener nếu listener không chỉ định group riêng.
- `consumer.auto-offset-reset`: chính sách khi group không có offset hợp lệ.
- `consumer.enable-auto-commit`: bật/tắt auto commit offset của Kafka client.
- `key-serializer` và `value-serializer`: chuyển object phía producer thành bytes.
- `key-deserializer` và `value-deserializer`: chuyển bytes phía consumer thành object.

`localhost:9092` chỉ phù hợp khi ứng dụng chạy trên máy có thể truy cập broker qua địa chỉ đó. Nếu ứng dụng chạy trong container hoặc Kubernetes, địa chỉ có thể phải dùng service DNS và listener phù hợp với network của ứng dụng.

### 2.3. Cấu hình không có nghĩa broker đã sẵn sàng

Boot có thể tạo bean Kafka dù broker chưa truy cập được tại thời điểm context khởi tạo. Kết nối thực tế thường diễn ra khi producer gửi hoặc consumer bắt đầu hoạt động. Khi ứng dụng khởi động nhưng không tiêu thụ được, hãy kiểm tra DNS, port, listener, authentication, TLS và quyền ACL, không chỉ kiểm tra YAML có parse thành công.

## 3. Spring Boot tạo những bean nào?

Các bean mặc định có thể thay đổi theo version và cấu hình ứng dụng, nhưng các thành phần cốt lõi thường gồm:

| Bean/Thành phần | Vai trò |
|---|---|
| `KafkaProperties` | Giữ cấu hình đã bind từ namespace `spring.kafka` |
| `ProducerFactory<K, V>` | Tạo Kafka producer với serializer và producer properties |
| `ConsumerFactory<K, V>` | Tạo Kafka consumer với deserializer và consumer properties |
| `KafkaTemplate<K, V>` | API gửi record/message từ ứng dụng |
| `ConcurrentKafkaListenerContainerFactory<K, V>` | Cấu hình listener container cho `@KafkaListener` |
| `KafkaAdmin` | Thực hiện các thao tác quản trị Kafka được khai báo qua Spring |

### 3.1. `KafkaProperties`

`KafkaProperties` là lớp cấu hình được Spring Boot bind từ `spring.kafka`. Auto-configuration dùng các giá trị này để xây dựng cấu hình cho producer, consumer, admin và listener.

Ứng dụng thường không cần tự tạo `KafkaProperties`. Có thể inject nó nếu cần đọc một số cấu hình trong code, nhưng tránh lấy cấu hình từ nhiều nguồn không nhất quán.

### 3.2. `ProducerFactory`

`ProducerFactory` chịu trách nhiệm tạo Kafka producer với cấu hình đã định nghĩa. `KafkaTemplate` sử dụng factory này để gửi record.

Việc dùng factory giúp ứng dụng không phải tự `new KafkaProducer` cho mỗi lần gửi. Factory quản lý cách tạo producer và các tùy chọn liên quan đến cache/close tùy implementation và version.

### 3.3. `ConsumerFactory`

`ConsumerFactory` tạo consumer cho listener container. Ứng dụng thường không trực tiếp gọi `poll()` khi dùng `@KafkaListener`; container sở hữu consumer, poll record và gọi method listener.

### 3.4. `KafkaTemplate`

`KafkaTemplate<K, V>` là abstraction gửi message. Nó hỗ trợ gửi key/value, `ProducerRecord`, message có header, callback hoặc kết quả bất đồng bộ theo API version.

Ví dụ inject vào service:

```java
@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String payload) {
        kafkaTemplate.send("orders", orderId, payload);
    }
}
```

`KafkaTemplate.send()` trả về kết quả bất đồng bộ. Trong ứng dụng thật, cần quan sát kết quả gửi và xử lý lỗi phù hợp; không giả định gọi method thành công đồng nghĩa broker đã ghi record.

### 3.5. Listener container factory

`ConcurrentKafkaListenerContainerFactory` dùng để cấu hình các listener container được tạo cho `@KafkaListener`, ví dụ consumer factory, concurrency, error handler, ack mode và transaction manager.

Khi dùng Boot auto-configuration, ứng dụng thường có factory mặc định tên `kafkaListenerContainerFactory`. Annotation có thể chỉ định factory khác bằng thuộc tính `containerFactory` nếu ứng dụng có nhiều nhóm listener cần cấu hình riêng.

## 4. Dùng `KafkaTemplate` để publish event

### 4.1. Publisher đơn giản

```java
@Service
public class OrderPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String eventJson) {
        kafkaTemplate.send("orders", orderId, eventJson)
            .whenComplete((result, error) -> {
                if (error != null) {
                    // Ghi log/metric và chuyển lỗi theo chính sách ứng dụng.
                    log.error("Cannot publish order event {}", orderId, error);
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.info("Published topic={} partition={} offset={}",
                    metadata.topic(), metadata.partition(), metadata.offset());
            });
    }
}
```

Đoạn code minh họa kiểu API trả về `CompletableFuture` ở các version Spring Kafka hiện đại. Một số version cũ dùng kiểu future khác; kiểm tra signature của dependency trong dự án trước khi copy code.

### 4.2. Gửi `Message<?>` có header

Spring Kafka hỗ trợ gửi Spring `Message<?>` để gắn header:

```java
Message<String> message = MessageBuilder
    .withPayload("{\"orderId\":\"ORD-101\"}")
    .setHeader(KafkaHeaders.TOPIC, "orders")
    .setHeader(KafkaHeaders.KEY, "ORD-101")
    .setHeader("event-type", "OrderCreated")
    .build();

kafkaTemplate.send(message);
```

Tên header và API cụ thể có thể thay đổi theo version Spring Kafka. Header nghiệp vụ như `event-type` cần được consumer hiểu theo contract; Kafka không tự diễn giải nó.

### 4.3. Chọn topic mặc định

Có thể cấu hình topic mặc định cho `KafkaTemplate` bằng thuộc tính Boot tương ứng hoặc truyền topic tường minh khi gọi `send()`. Với service có nhiều loại event, truyền topic rõ ràng thường dễ review hơn và tránh publish nhầm do default không phù hợp.

## 5. Dùng `@KafkaListener` để nhận event

### 5.1. Listener đơn giản

```java
@Component
public class OrderListener {

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void onOrderEvent(String payload) {
        log.info("Received order event: {}", payload);
        processOrderEvent(payload);
    }
}
```

Spring Kafka phát hiện annotation và tạo listener container. Container tạo consumer từ `ConsumerFactory`, subscribe topic, gọi `poll()` và chuyển record cho method listener.

Trong ứng dụng Spring Boot đã dùng Kafka auto-configuration, thông thường không cần tự tạo `KafkaConsumer` hoặc viết vòng lặp poll. Nếu tự tạo consumer song song với listener container, cần xác định rõ quyền sở hữu partition và group để tránh hai cơ chế đọc dữ liệu không mong muốn.

Với ứng dụng Spring Framework không dùng Boot, cần bật cơ chế xử lý annotation bằng `@EnableKafka` và tự cấu hình listener container factory. Trong ứng dụng Spring Boot dùng Kafka auto-configuration mặc định, hạ tầng annotation-driven thường đã được cấu hình; chỉ thêm `@EnableKafka` khi ứng dụng chủ động thay đổi hoặc loại bỏ phần auto-configuration tương ứng và hiểu rõ bean nào cần được tạo.

### 5.2. Nhận key, metadata và payload

Có thể nhận thêm key, partition, offset hoặc toàn bộ record:

```java
@KafkaListener(topics = "orders", groupId = "order-audit")
public void onOrderEvent(
        @Payload String payload,
        @Header(KafkaHeaders.RECEIVED_KEY) String key,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    log.info("topic=orders key={} partition={} offset={}",
        key, partition, offset);
    audit(payload);
}
```

Tên header constant và kiểu dữ liệu cụ thể phụ thuộc version Spring Kafka. Nếu cần tất cả metadata hoặc thao tác theo record, có thể nhận `ConsumerRecord<K, V>` trực tiếp.

### 5.3. Chọn group ID

`groupId` trên `@KafkaListener` có thể chỉ định group cho listener. Nếu bỏ qua, listener có thể dùng `spring.kafka.consumer.group-id` đã cấu hình. Cần hiểu rõ:

- Các instance của cùng một pipeline dùng cùng group ID để chia partition.
- Các ứng dụng cần nhận toàn bộ event độc lập dùng group ID khác nhau.
- Không tạo group ID ngẫu nhiên cho mỗi instance nếu mục tiêu là scale out cùng một pipeline.

### 5.4. Concurrency

Có thể cấu hình concurrency để một listener container chạy nhiều consumer thread:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-projection",
    concurrency = "3"
)
public void onOrderEvent(String payload) {
    processOrderEvent(payload);
}
```

Concurrency tạo nhiều consumer member trong cùng group theo cấu hình container. Số partition giới hạn mức song song hữu ích; nếu topic có hai partition mà concurrency là năm, một số consumer có thể không nhận partition.

Concurrency có thể cấu hình tại annotation hoặc listener container factory. Nên chọn một nơi làm nguồn cấu hình chính để tránh khác biệt giữa code và môi trường.

## 6. Spring Boot auto-configuration hoạt động ra sao?

### 6.1. Dựa trên classpath và điều kiện

Spring Boot auto-configuration là tập cấu hình có điều kiện. Khi dependency Spring Kafka có mặt, Boot có thể đăng ký các bean cần thiết nếu ứng dụng chưa cung cấp bean thay thế phù hợp.

Ví dụ khái quát:

```text
spring-kafka có trong classpath?
       |
       +-- Không --> Không cấu hình Kafka integration
       |
       +-- Có
            |
            v
KafkaProperties được bind
            |
            v
Ứng dụng đã khai báo ProducerFactory/ConsumerFactory/KafkaTemplate?
            |
            +-- Chưa --> Boot tạo bean mặc định phù hợp
            |
            +-- Rồi --> Auto-configuration lùi lại theo điều kiện bean
            |
            v
Listener factory và các thành phần còn thiếu được cấu hình
```

Đây là mô hình khái niệm; điều kiện chính xác và tên bean có thể thay đổi theo version Spring Boot. Khi cần biết bean nào được tạo, dùng condition evaluation report hoặc xem ApplicationContext thay vì đoán theo một bài hướng dẫn của version khác.

### 6.2. Bean do ứng dụng khai báo có thể làm Boot back off

Nếu ứng dụng khai báo bean tùy chỉnh cho một thành phần, auto-configuration có thể không tạo bean mặc định tương ứng nữa. Cơ chế này thường được gọi là back-off.

Ví dụ, khi cần một producer factory có serializer hoặc property riêng, ứng dụng có thể khai báo `ProducerFactory` tùy chỉnh. Nhưng nếu bean đó thay thế factory mặc định, các cấu hình Boot mà ứng dụng mong đợi có thể không còn được áp dụng tự động.

Vì vậy:

- Chỉ override bean cần tùy biến.
- Giữ các cấu hình chung trong `spring.kafka` nếu chúng vẫn phù hợp.
- Khi tạo factory thủ công, chủ động giữ lại các thuộc tính cần thiết như bootstrap servers, serializer, security, retry và timeout.
- Kiểm tra bean thực tế sau khi context khởi tạo.

### 6.3. Tránh khai báo trùng bean

Một lỗi thường gặp là vừa dùng Boot auto-configuration, vừa khai báo một `KafkaTemplate` hoặc listener factory khác nhưng không biết bean nào được inject. Có thể dẫn đến:

- `NoSuchBeanDefinitionException` nếu bean cần thiết không được tạo.
- `NoUniqueBeanDefinitionException` nếu có nhiều bean cùng type mà injection không phân biệt.
- Listener dùng nhầm factory hoặc consumer group.
- Producer dùng serializer khác với payload thực tế.

Khi có nhiều factory/template, đặt tên bean rõ ràng và chỉ định bằng `@Qualifier` hoặc `containerFactory`.

## 7. Tùy biến `ConcurrentKafkaListenerContainerFactory`

### 7.1. Khi nào cần factory riêng?

Factory riêng hữu ích khi listener có yêu cầu khác nhau, ví dụ:

- Một nhóm listener xử lý String, nhóm khác xử lý JSON object.
- Concurrency khác nhau theo workload.
- Ack mode hoặc error handler khác nhau.
- Một listener dùng transaction trong khi listener khác không dùng.
- Một nhóm cần retry/DLT riêng.

Nếu mọi listener dùng cùng cấu hình, factory mặc định thường đủ và ít code hơn.

### 7.2. Ví dụ khai báo factory tùy chỉnh

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            auditKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(2);
        return factory;
    }
}
```

Listener sử dụng factory này:

```java
@KafkaListener(
    topics = "audit-events",
    groupId = "audit-service",
    containerFactory = "auditKafkaListenerContainerFactory"
)
public void onAuditEvent(String payload) {
    processAudit(payload);
}
```

Ví dụ dùng `ConsumerFactory` được Boot cung cấp, chỉ tạo listener factory riêng. Nếu muốn deserializer khác, hãy tạo `ConsumerFactory` riêng với cấu hình tương ứng và inject vào factory này. Tránh đổi deserializer dùng chung nếu listener khác vẫn cần kiểu cũ.

### 7.3. Ack mode và offset commit

Listener container có các chế độ acknowledgment/commit. Cấu hình cụ thể cần khớp semantics xử lý:

- Record listener thường xử lý từng record, container quyết định commit theo ack mode.
- Batch listener nhận một batch và cần xác định khi nào toàn batch đã xử lý thành công.
- Manual acknowledgment cho phép listener xác nhận sau khi hoàn tất side effect, nhưng phải tuân thủ quy tắc commit và thứ tự xử lý.
- Khi dùng Kafka transaction, cần cấu hình transaction manager/factory phù hợp thay vì tự commit offset độc lập.

Không chọn manual ack chỉ vì muốn “chắc chắn”. Nếu ack trước side effect, vẫn có nguy cơ mất xử lý; nếu ack sau side effect, vẫn có thể duplicate khi crash trước commit. Cần kết hợp idempotency nếu side effect nằm ngoài Kafka.

## 8. Cấu hình theo môi trường

### 8.1. Profile cho local và production

Có thể tách cấu hình bằng Spring profile:

`application-local.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service-local
      auto-offset-reset: earliest
```

`application-prod.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.internal:9092,kafka-2.internal:9092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
      enable-auto-commit: false
```

Kích hoạt profile bằng `spring.profiles.active` hoặc biến môi trường phù hợp. Tránh commit credentials hoặc truststore password vào source control.

### 8.2. Externalized configuration

Spring Boot có thể lấy cấu hình từ YAML, properties, environment variables, command-line arguments và config server. Điều này cho phép dùng cùng artifact ứng dụng ở nhiều môi trường nhưng thay đổi broker, group ID, security và tuning theo môi trường.

Ví dụ biến môi trường:

```text
SPRING_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
SPRING_KAFKA_CONSUMER_GROUP_ID=order-service
```

Quy tắc ánh xạ tên biến môi trường theo relaxed binding của Spring Boot. Kiểm tra cấu hình đã bind nếu tên property có dấu gạch hoặc cấu trúc map phức tạp.

### 8.3. Security

Với cluster yêu cầu SASL/TLS, cấu hình client properties theo cơ chế bảo mật của cluster. Có thể dùng namespace `spring.kafka.properties` hoặc properties riêng cho producer/consumer/admin tùy nhu cầu và version Boot.

Không ghi username, password, private key hoặc truststore secret trực tiếp trong YAML được commit. Dùng secret manager, environment injection hoặc cơ chế quản lý secret của nền tảng triển khai.

## 9. Tạo topic bằng Spring Kafka

Spring Kafka cung cấp `KafkaAdmin` và kiểu `NewTopic` để khai báo topic như một bean:

```java
@Configuration
public class TopicConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
            .partitions(6)
            .replicas(3)
            .build();
    }
}
```

Khi admin integration được cấu hình và có quyền quản trị phù hợp, Spring Kafka có thể yêu cầu broker tạo topic khi ứng dụng khởi động. Cần lưu ý:

- Broker phải có đủ broker phù hợp cho replication factor.
- Ứng dụng cần quyền tạo topic nếu cluster bật ACL.
- Topic đã tồn tại không tự động được giảm partition hoặc thay đổi mọi cấu hình chỉ vì bean `NewTopic` khác.
- Tạo topic khi khởi động cần được quản lý cẩn thận trong production, nhất là khi nhiều service cùng khởi động.
- Việc tạo topic tự động của broker là cơ chế khác với khai báo `NewTopic` qua Spring Kafka.

Với hạ tầng production, topic có thể được quản lý bởi quy trình platform/IaC thay vì để từng ứng dụng tự tạo.

## 10. Spring Kafka và xử lý lỗi

Spring Kafka bổ sung cơ chế xử lý lỗi cho listener, ví dụ error handler, retry, backoff và dead-letter recoverer. Tuy nhiên, auto-configuration không tự biết chính sách nghiệp vụ của từng event.

Khi listener ném exception, cần xác định:

- Đây là lỗi tạm thời như database/network unavailable hay lỗi dữ liệu không thể xử lý?
- Có nên retry tại chỗ với backoff không?
- Retry có làm block partition và tăng lag không?
- Sau số lần thử, record được đưa vào DLT hay dừng container?
- Offset chỉ được commit sau khi record thành công hoặc được recovery theo policy nào?
- Side effect có idempotent khi record được giao lại không?

Ví dụ, một lỗi database tạm thời có thể retry hữu hạn. Một payload sai schema thường không nên retry vô hạn; nên đưa vào DLT kèm metadata nguồn để điều tra. Cấu hình error handler và DLT nên được thiết kế ở bài chuyên sâu, không bật một retry policy chung cho mọi listener.

## 11. Quan sát cấu hình auto-configuration

Khi ứng dụng không tạo bean hoặc listener không chạy như dự kiến, kiểm tra theo thứ tự:

1. Dependency `spring-kafka` có trong runtime classpath không?
2. Spring Boot version và Spring Kafka version có tương thích không?
3. `spring.kafka.bootstrap-servers` đã bind đúng chưa?
4. Producer/consumer serializer và deserializer có đúng với payload không?
5. Có bean tùy chỉnh nào làm auto-configuration back off không?
6. Có nhiều `KafkaTemplate`, `ProducerFactory` hoặc listener factory gây ambiguity không?
7. `@KafkaListener` có được scan trong Spring component scan không?
8. Listener đang dùng đúng topic, group ID và container factory không?
9. Broker có truy cập được, đúng listener và security protocol không?
10. Consumer có assignment, poll và quyền ACL phù hợp không?

Có thể bật debug log cho auto-configuration hoặc dùng condition evaluation report của Spring Boot để biết cấu hình nào được áp dụng và điều kiện nào không thỏa. Không nên bật log nhạy cảm trong production lâu dài.

## 12. Ví dụ ứng dụng Spring Boot tối thiểu

Một cấu trúc package đơn giản:

```text
com.example.orders
  OrderApplication.java
  config/
    KafkaTopicConfiguration.java
  messaging/
    OrderPublisher.java
    OrderListener.java
```

Application:

```java
@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

Publisher:

```java
@Service
public class OrderPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String payload) {
        return kafkaTemplate.send("orders", orderId, payload);
    }
}
```

Listener:

```java
@Component
public class OrderListener {
    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void consume(String payload) {
        process(payload);
    }
}
```

Với Spring Kafka version có API `CompletableFuture`, publisher có thể trả future để caller quyết định cách quan sát kết quả. Nếu version dự án dùng kiểu kết quả khác, điều chỉnh signature theo API thực tế.

Ứng dụng tối thiểu này dùng Boot auto-configuration để cung cấp template và listener infrastructure. Chưa bao gồm schema, retry/DLT, transaction hoặc database idempotency; các thành phần đó cần bổ sung theo yêu cầu nghiệp vụ.

## 13. Spring Boot auto-configuration và cấu hình thủ công

| Tiêu chí | Dùng auto-configuration | Tự khai báo bean |
|---|---|---|
| Khởi đầu dự án | Ít code, dùng `spring.kafka` | Nhiều cấu hình hơn |
| Cấu hình chung | YAML/environment | Java config hoặc properties tự xây dựng |
| Nhiều producer/consumer khác nhau | Cần thêm bean/factory riêng khi cấu hình khác biệt | Kiểm soát rõ từng factory |
| Tùy biến listener | Dùng factory mặc định rồi bổ sung khi cần | Toàn quyền cấu hình container factory |
| Nguy cơ | Không hiểu back-off/bean mặc định | Trùng bean, thiếu property hoặc bỏ sót cấu hình bảo mật |
| Phù hợp | Ứng dụng phổ biến, một cấu hình Kafka chính | Nhiều cluster, nhiều format, listener có semantics khác nhau |

Nên bắt đầu bằng auto-configuration. Khi có yêu cầu thực sự khác biệt, mở rộng từng thành phần cụ thể và giữ cấu hình còn lại ở một nguồn rõ ràng.

## 14. Các lỗi và anti-pattern thường gặp

| Lỗi/anti-pattern | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ Spring Boot tự tạo Kafka broker | Auto-configuration chỉ tạo client-side bean | Chạy/provision Kafka cluster riêng và cấu hình bootstrap servers |
| Thêm dependency nhưng không cấu hình broker | Client không biết bootstrap endpoint | Khai báo `spring.kafka.bootstrap-servers` |
| Producer và consumer dùng serializer/deserializer không khớp | Hai phía diễn giải bytes khác nhau | Thống nhất key/value format và cấu hình tương ứng |
| Tự tạo `KafkaConsumer` trong service dùng `@KafkaListener` | Có hai cơ chế sở hữu consumer và assignment | Dùng listener container hoặc quản lý manual consumer riêng có chủ đích |
| Tạo `KafkaTemplate` tùy chỉnh không rõ bean mặc định | Auto-configuration back off hoặc injection ambiguity | Đặt tên/qualifier và kiểm tra condition report |
| Nhiều listener dùng chung factory dù cần ack/error policy khác | Cấu hình dùng chung không đáp ứng semantics | Tạo factory riêng cho nhóm listener cần khác biệt |
| Dùng `group.id` khác nhau trên từng instance | Mỗi instance thành group độc lập, đọc trùng dữ liệu | Dùng group ID ổn định cho cùng pipeline |
| Coi `KafkaTemplate.send()` trả về là broker đã ghi | Gửi là bất đồng bộ | Quan sát future/callback và xử lý failure |
| Bật auto commit nhưng xử lý side effect lâu | Offset có thể commit trước khi business logic hoàn tất | Thiết kế ack/commit theo semantics và idempotency |
| Tạo topic ở mọi ứng dụng mà không có ownership | Khó quản lý partition, replication và config | Quản lý topic bằng platform/IaC hoặc quy trình rõ ràng |
| Commit secret vào `application.yml` | Lộ credentials | Dùng secret manager hoặc environment injection |
| Copy cấu hình từ version Boot khác | Property/API có thể đổi theo version | Đối chiếu documentation của version dự án |

## 15. Checklist triển khai Spring Kafka

Trước khi chạy ứng dụng, xác nhận:

- Dependency `spring-kafka` tương thích với Spring Boot version.
- `bootstrap-servers` trỏ đến broker có thể truy cập từ runtime environment.
- Producer serializer và consumer deserializer khớp format topic.
- `group.id` phản ánh đúng subscription logic và ổn định qua restart.
- `auto-offset-reset` được chọn theo yêu cầu dữ liệu.
- Chính sách auto/manual commit phù hợp với side effect.
- `KafkaTemplate` được inject từ bean đúng.
- `@KafkaListener` được scan và dùng đúng topic/group/container factory.
- Concurrency không vượt mức song song hữu ích của partition.
- Bean tùy chỉnh không vô tình làm mất cấu hình Boot cần thiết.
- Nhiều factory/template được đặt tên và qualifier rõ ràng.
- Security credentials được quản lý ngoài source control.
- Retry, DLT, transaction và idempotency được thiết kế theo nghiệp vụ.
- Có log/metric cho publish failure, listener error, lag và rebalance.
- Topic được quản lý bởi owner/quy trình có trách nhiệm rõ ràng.

## 16. Câu hỏi tự kiểm tra

1. Apache Kafka Java client, Spring for Apache Kafka và Spring Boot khác nhau ở vai trò nào?
2. `KafkaTemplate` dùng `ProducerFactory` để làm gì?
3. `ConsumerFactory` khác listener container factory như thế nào?
4. Spring Boot auto-configuration dựa vào những điều kiện nào để tạo bean Kafka?
5. Vì sao khai báo một bean tùy chỉnh có thể khiến Boot back off?
6. `spring.kafka.bootstrap-servers` có làm broker tự khởi động không?
7. `@KafkaListener` được thực thi bởi thành phần nào?
8. Khi nào cần một `ConcurrentKafkaListenerContainerFactory` riêng?
9. Concurrency của listener có thể vượt số partition hữu ích không?
10. Vì sao cần theo dõi kết quả bất đồng bộ của `KafkaTemplate.send()`?
11. `group.id` mặc định và `groupId` trên annotation liên quan với nhau thế nào?
12. Spring `NewTopic` và broker auto topic creation khác nhau ở đâu?
13. Cần kiểm tra những gì khi listener không nhận record dù ứng dụng đã khởi động?
14. Khi nào nên giữ auto-configuration và khi nào nên tự khai báo factory?

## Kết luận

Spring for Apache Kafka cung cấp các abstraction như `KafkaTemplate`, producer/consumer factory và listener container để tích hợp Kafka vào ứng dụng Spring. Spring Boot auto-configuration bind `spring.kafka` và tạo các bean mặc định khi dependency cùng điều kiện phù hợp, giúp ứng dụng khởi đầu nhanh mà không phải tự dựng toàn bộ infrastructure. Khi cần nhiều cấu hình hoặc semantics khác nhau, có thể khai báo bean riêng; cần hiểu cơ chế back-off và quản lý bean rõ ràng. Nắm được ranh giới giữa Kafka client, Spring Kafka và Boot giúp cấu hình ứng dụng dễ kiểm soát, dễ quan sát và phù hợp với từng môi trường triển khai.
