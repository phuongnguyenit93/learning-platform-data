# ProducerFactory, ConsumerFactory và cấu hình theo môi trường

Spring Kafka cung cấp các factory để tạo và quản lý Kafka producer, consumer. `ProducerFactory` cấp producer cho `KafkaTemplate`; `ConsumerFactory` cấp consumer cho listener container. Hai factory này là điểm tập trung để cấu hình serializer, deserializer, kết nối broker, bảo mật và các tùy chọn của Kafka client.

Trong ứng dụng chạy ở nhiều môi trường, cùng một luồng nghiệp vụ có thể cần bootstrap server, security protocol, consumer group, số listener và timeout khác nhau. Cấu hình nên được tổ chức thành phần dùng chung và phần thay đổi theo môi trường. Nhờ đó, mã nghiệp vụ không phải biết ứng dụng đang chạy ở local, staging hay production.

## 1. Vai trò của ProducerFactory và ConsumerFactory

`ProducerFactory<K, V>` là abstraction tạo producer có key kiểu `K` và value kiểu `V`. Implementation phổ biến là `DefaultKafkaProducerFactory`. `KafkaTemplate<K, V>` dùng factory này để gửi record, quản lý callback và cung cấp các thao tác gửi thuận tiện cho ứng dụng Spring.

`ConsumerFactory<K, V>` là abstraction tạo consumer. Implementation phổ biến là `DefaultKafkaConsumerFactory`. Trong Spring Kafka, listener container lấy consumer từ factory, chạy vòng lặp `poll()`, gọi listener, quản lý offset và phối hợp rebalance. Ứng dụng dùng `@KafkaListener` thường không tự tạo hoặc tự gọi `poll()`.

| Thành phần | Trách nhiệm | Thành phần thường sử dụng nó |
|---|---|---|
| `ProducerFactory` | Tạo và quản lý vòng đời producer, áp dụng cấu hình producer | `KafkaTemplate`, transactional producer |
| `KafkaTemplate` | Gửi record, chọn topic/key/partition và nhận kết quả gửi | Service phát event |
| `ConsumerFactory` | Tạo consumer với group, deserializer và cấu hình client | Listener container |
| `ConcurrentKafkaListenerContainerFactory` | Tạo listener container, cấu hình concurrency, ack mode và error handler | `@KafkaListener` |
| `@KafkaListener` | Khai báo phương thức nhận record | Application service/component |

Hai factory không phải nơi lưu message. Producer vẫn gửi record đến broker và consumer vẫn đọc record từ topic theo consumer group, offset và partition assignment của Kafka.

## 2. Vòng đời producer và consumer do factory quản lý

### ProducerFactory

`DefaultKafkaProducerFactory` tạo producer từ một map cấu hình. Trong cấu hình thông thường, factory quản lý producer dùng chung và tái sử dụng để tránh tạo kết nối mới cho mỗi lần gửi. Khi bật transaction, factory quản lý các transactional producer theo `transactional.id` và cơ chế cache tương ứng.

Ứng dụng thường khai báo một factory dùng chung trong Spring context. Không tạo `KafkaProducer` mới cho từng event vì mỗi producer có tài nguyên mạng, buffer, luồng I/O và chi phí khởi tạo riêng. Nếu có nhu cầu đặc biệt như producer riêng theo thread, cần cấu hình rõ và quản lý việc đóng producer theo đúng vòng đời.

`KafkaTemplate` thường được tạo từ `ProducerFactory` và được inject vào service:

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

Kết quả gửi là bất đồng bộ. Ứng dụng cần theo dõi future/callback khi nghiệp vụ cần xác nhận broker đã nhận record. Không được coi việc gọi `send()` là bằng chứng record đã được ghi thành công.

### ConsumerFactory

`DefaultKafkaConsumerFactory` cung cấp consumer mới cho listener container. Mỗi consumer thuộc một consumer group và được Kafka phân partition. Với listener container chạy concurrency lớn hơn 1, Spring Kafka tạo nhiều consumer instance để xử lý song song; số consumer hữu ích không vượt quá số partition được assign cho group.

Không chia sẻ cùng một `KafkaConsumer` giữa nhiều thread. KafkaConsumer không thread-safe. Hãy để listener container quản lý poll thread, assignment, rebalance và shutdown. Nếu ứng dụng dùng consumer API trực tiếp ngoài Spring listener, chính ứng dụng phải tuân thủ quy tắc thread confinement và đóng consumer đúng cách.

## 3. Cấu hình chung bằng Spring Boot

Spring Boot có thể tự cấu hình `ProducerFactory`, `ConsumerFactory`, `KafkaTemplate`, `KafkaAdmin` và listener infrastructure từ namespace `spring.kafka`. Khi không cần tùy biến đặc biệt, nên bắt đầu bằng cấu hình này thay vì tự tạo tất cả bean.

Ví dụ `application.yml` chứa các giá trị dùng chung:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000

    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP:orders-service}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[isolation.level]": read_committed

    listener:
      ack-mode: record
      concurrency: ${KAFKA_LISTENER_CONCURRENCY:3}
```

Ý nghĩa các cấu hình chính:

- `bootstrap-servers` là địa chỉ khởi đầu để producer/consumer tìm broker và metadata của cluster.
- Serializer/deserializer phải tương thích với kiểu dữ liệu mà ứng dụng gửi và nhận.
- `acks: all` yêu cầu broker xác nhận theo chính sách replica đang áp dụng; kết hợp idempotence giúp producer xử lý retry ở tầng giao thức an toàn hơn.
- `enable-auto-commit: false` để Spring Kafka container quản lý thời điểm commit offset theo ack mode.
- `auto-offset-reset: earliest` chỉ được áp dụng khi group chưa có offset hợp lệ; nó không tự tua lại offset đã commit của một group đang hoạt động.
- `isolation.level: read_committed` phù hợp với consumer cần chỉ đọc record transactional đã commit.
- `ack-mode: record` yêu cầu container commit offset sau khi listener xử lý thành công từng record, theo cơ chế ack/commit của container.
- `concurrency` là số consumer container chạy đồng thời cho listener factory; cần cân đối với số partition và tài nguyên downstream.

Các key Kafka client có dấu chấm trong map `properties` được đặt trong ngoặc vuông để Spring Boot giữ nguyên tên key, ví dụ `[enable.idempotence]` và `[isolation.level]`.

Nếu ứng dụng dùng JSON thay vì chuỗi, có thể thay `StringSerializer`/`StringDeserializer` bằng `JsonSerializer`/`JsonDeserializer`, rồi cấu hình default type và trusted packages cho consumer. Chỉ tin cậy package của các event type cần nhận; tránh mở wildcard rộng trong hệ thống nhận dữ liệu từ nhiều nguồn.

## 4. Tách cấu hình theo môi trường bằng profiles

Nên đặt các thuộc tính ổn định ở `application.yml`, còn giá trị khác nhau ở `application-dev.yml`, `application-test.yml`, `application-staging.yml` hoặc `application-prod.yml`. Spring Boot nạp file theo profile đang active và cho phép biến môi trường ghi đè cấu hình.

Ví dụ `application-dev.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    properties:
      "[security.protocol]": PLAINTEXT
```

Ví dụ `application-prod.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": ${KAFKA_SASL_JAAS_CONFIG}
```

Kích hoạt profile bằng biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=prod
KAFKA_BOOTSTRAP_SERVERS=broker-1.example.net:9093,broker-2.example.net:9093
KAFKA_SASL_JAAS_CONFIG='org.apache.kafka.common.security.scram.ScramLoginModule required username="app" password="...";'
```

Các giá trị trên chỉ minh họa cách truyền cấu hình. Credential thực tế nên lấy từ secret manager hoặc cơ chế quản lý secret của nền tảng triển khai; không commit password hoặc JAAS config có secret vào Git. Production cũng cần cấu hình truststore/certificate theo chính sách TLS của cluster nếu JVM truststore mặc định không đủ.

Có thể dùng biến môi trường ánh xạ trực tiếp sang thuộc tính Spring Boot, chẳng hạn `SPRING_KAFKA_BOOTSTRAP_SERVERS`, `SPRING_KAFKA_CONSUMER_GROUP_ID` và `SPRING_KAFKA_PRODUCER_ACKS`. Nếu dùng placeholder tùy chỉnh như `KAFKA_BOOTSTRAP_SERVERS`, hãy thống nhất tên biến trong manifest, Helm chart hoặc deployment pipeline.

### Những giá trị nên khác nhau giữa môi trường

| Thuộc tính | Local/dev | Staging | Production |
|---|---|---|---|
| Bootstrap servers | Broker local hoặc container | Cluster staging | Cluster production |
| Security protocol | Có thể `PLAINTEXT` trong môi trường cô lập | TLS/SASL theo cấu hình staging | TLS/SASL và secret được quản lý |
| Consumer group | Group riêng của developer/test | Group staging | Group ổn định của service production |
| Topic | Topic dev/test | Topic staging | Topic production |
| Concurrency | Thấp để debug | Gần cấu hình production | Theo partition, tải và năng lực downstream |
| Logging | Chi tiết hơn | Có kiểm soát | Có cấu trúc, tránh lộ payload/credential |

Không dùng chung consumer group giữa dev, staging và production. Các môi trường dùng chung group có thể tranh partition và cùng commit offset, khiến việc kiểm thử ảnh hưởng đến luồng dữ liệu thật.

## 5. Tùy biến ProducerFactory và ConsumerFactory

Khi Spring Boot auto-configuration đáp ứng đủ nhu cầu, không cần khai báo lại factory. Nếu cần serializer riêng, custom partitioner, interceptor, transaction hoặc cấu hình client khác biệt, có thể tự khai báo factory.

Ví dụ tối giản tạo producer factory:

```java
@Configuration
public class KafkaFactoryConfig {

    @Bean
    ProducerFactory<String, String> producerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers) {

        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        return new DefaultKafkaProducerFactory<>(props);
    }
}
```

Ví dụ consumer factory:

```java
@Configuration
public class KafkaConsumerFactoryConfig {

    @Bean
    ConsumerFactory<String, String> consumerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers,
            @Value("${spring.kafka.consumer.group-id}") String groupId) {

        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");

        return new DefaultKafkaConsumerFactory<>(props);
    }
}
```

Đây là ví dụ tối giản để thấy factory nhận một map cấu hình. Khi tự khai báo factory, ứng dụng phải đưa vào map tất cả thuộc tính cần thiết, bao gồm security, SSL/SASL, timeout, serializer/deserializer và các thuộc tính riêng của môi trường. Không nên nghĩ rằng mọi thuộc tính `spring.kafka.*` sẽ tự động được hợp nhất vào một factory tùy biến do ứng dụng tự tạo. Với ứng dụng dùng nhiều cấu hình, hãy xây dựng map từ một cấu hình có kiểu rõ ràng hoặc dùng cơ chế binding của Spring Boot để tránh bỏ sót thuộc tính.

Nếu chỉ cần thay đổi một vài hành vi, cân nhắc giữ auto-configuration và tùy biến đúng bean cần thiết. Việc khai báo `ProducerFactory` hoặc `ConsumerFactory` tùy chỉnh có thể khiến một phần auto-configuration mặc định lùi lại; cần kiểm tra bean nào đang được Spring tạo và bean nào được inject vào `KafkaTemplate`/listener container.

## 6. Cấu hình listener container theo từng luồng

`ConsumerFactory` chỉ tạo consumer. `ConcurrentKafkaListenerContainerFactory` điều khiển cách listener container sử dụng consumer đó, bao gồm concurrency, ack mode, batch mode, error handler và interceptors.

Ví dụ tạo một factory listener riêng:

```java
@Configuration
public class OrdersListenerConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String> ordersListenerFactory(
            ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);
        return factory;
    }
}
```

Listener có thể chọn factory theo tên:

```java
@KafkaListener(
        topics = "orders",
        containerFactory = "ordersListenerFactory"
)
public void onOrder(String payload) {
    orderService.handle(payload);
}
```

Khi cần luồng khác có batch listener, concurrency khác hoặc error handler riêng, có thể khai báo thêm container factory. Không nhất thiết phải tạo một `ConsumerFactory` riêng cho mọi listener nếu các listener dùng chung cấu hình client; chỉ tách khi group, deserializer, isolation hoặc các thuộc tính consumer thực sự khác nhau.

Concurrency không đồng nghĩa với số thread xử lý tùy ý. Mỗi consumer trong group nhận một tập partition; nếu concurrency lớn hơn số partition được assign, một số consumer có thể rảnh. Tăng concurrency cũng làm tăng số kết nối và áp lực lên database/API downstream.

## 7. Transactional producer và factory

Khi ứng dụng cần Kafka transaction, factory phải được cấu hình để tạo transactional producer. Trong Spring Boot, có thể đặt `spring.kafka.producer.transaction-id-prefix` với prefix riêng cho từng instance ứng dụng:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${KAFKA_TRANSACTION_ID_PREFIX}
```

Prefix phải tạo transactional ID không trùng giữa các producer đang hoạt động đồng thời. Khi triển khai nhiều replica, mỗi replica cần giá trị riêng và ổn định trong vòng đời instance logic. Không dùng cùng một prefix/ID khiến các instance fencing lẫn nhau.

Với transactional listener, cần cấu hình container và transaction manager phù hợp với cách xử lý. Nếu dùng consume-transform-produce, offset input phải được gửi trong cùng Kafka transaction với output theo cơ chế Spring Kafka hỗ trợ. Việc bật transaction producer không tự động khiến mọi thao tác database hoặc HTTP nằm trong transaction đó.

Consumer đọc dữ liệu transactional cần `isolation.level=read_committed` nếu không muốn nhận record thuộc transaction bị abort. Thuộc tính này thường được đặt trong `spring.kafka.consumer.properties` như ví dụ cấu hình chung ở trên.

## 8. Cấu hình bảo mật và tách secret

ProducerFactory và ConsumerFactory dùng cùng bootstrap servers nhưng có thể cần cùng hoặc khác quyền truy cập. Nếu một service chỉ đọc topic, không cấp quyền ghi hoặc quản trị topic cho principal đó. Nếu service vừa consume vừa produce, quyền nên được giới hạn theo topic và operation cần thiết.

Các thuộc tính bảo mật thường được đặt trong `spring.kafka.properties` để dùng chung hoặc trong `spring.kafka.producer.properties`/`spring.kafka.consumer.properties` nếu chỉ áp dụng cho một client:

```properties
spring.kafka.properties[security.protocol]=SASL_SSL
spring.kafka.properties[sasl.mechanism]=SCRAM-SHA-512
spring.kafka.properties[sasl.jaas.config]=${KAFKA_SASL_JAAS_CONFIG}
```

Không đưa credential vào log hoặc exception message trả về client. Dùng TLS để mã hóa kết nối, xác thực bằng SASL hoặc cơ chế được cluster hỗ trợ, và cấp quyền tối thiểu cho từng principal. Nếu producer và consumer có cơ chế xác thực khác nhau, đặt cấu hình ở namespace riêng thay vì dùng thuộc tính chung.

## 9. Kiểm tra cấu hình khi ứng dụng khởi động

Một cấu hình hợp lệ về cú pháp vẫn có thể sai về mặt vận hành. Ví dụ, bootstrap server trỏ nhầm cluster, consumer group dùng chung giữa môi trường, serializer không khớp kiểu listener hoặc concurrency vượt quá khả năng downstream.

Nên kiểm tra ở startup hoặc trong health/diagnostic endpoint:

- Profile đang active và cluster bootstrap server đã chọn (không in secret).
- Producer serializer/deserializer và schema/type mapping phù hợp với event contract.
- Consumer group, `auto.offset.reset`, `enable.auto.commit` và `isolation.level` đúng yêu cầu.
- Security protocol, principal và quyền trên topic cần thiết.
- Số partition, concurrency và năng lực dịch vụ downstream.
- Transaction ID prefix duy nhất nếu dùng transaction.

Không nên để lộ toàn bộ map cấu hình trong log vì map có thể chứa JAAS, password hoặc truststore credential. Có thể log các trường không nhạy cảm như profile, bootstrap host đã được làm sạch, group ID và client ID.

## 10. Checklist thiết kế theo môi trường

- Dùng `ProducerFactory` và `ConsumerFactory` dùng chung trong Spring context; không tạo client cho mỗi record.
- Để Spring Boot auto-configure factory khi không có nhu cầu tùy biến đặc biệt.
- Đặt cấu hình chung trong `application.yml`, khác biệt môi trường trong profile hoặc biến môi trường.
- Dùng consumer group và topic riêng cho dev, staging, production.
- Quản lý credential qua secret manager; không commit password hoặc JAAS config.
- Đảm bảo serializer/deserializer khớp kiểu dữ liệu và schema contract.
- Tắt auto commit nếu Spring Kafka container quản lý offset; chọn ack mode phù hợp.
- Chọn concurrency theo số partition và khả năng downstream.
- Nếu tự khai báo factory, hợp nhất đầy đủ security và client properties từ môi trường.
- Dùng transactional ID prefix riêng cho từng instance nếu bật Kafka transaction.
- Theo dõi lỗi kết nối, serialization, authentication, consumer lag và thời gian xử lý.

`ProducerFactory` và `ConsumerFactory` là ranh giới cấu hình giữa Spring application với Kafka client. Kết hợp factory dùng chung, Spring Boot profiles và biến môi trường giúp một codebase chạy được ở nhiều môi trường mà vẫn giữ cấu hình producer, consumer, listener và bảo mật nhất quán. Khi cần tùy biến factory, hãy quản lý đầy đủ map thuộc tính và vòng đời client để tránh vô tình bỏ qua cấu hình production hoặc tạo quá nhiều kết nối.
