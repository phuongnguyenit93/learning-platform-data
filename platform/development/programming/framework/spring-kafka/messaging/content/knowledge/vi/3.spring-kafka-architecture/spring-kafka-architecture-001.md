# Các thành phần chính của Spring for Apache Kafka

## 1. Spring for Apache Kafka là gì?

Spring for Apache Kafka (thường gọi ngắn là Spring Kafka) là thư viện tích hợp Kafka vào ứng dụng Spring. Thư viện cung cấp các abstraction để gửi record, nhận record, quản lý listener, chuyển đổi message, xử lý lỗi và giao dịch. Ứng dụng vẫn sử dụng Kafka client bên dưới; Spring Kafka tổ chức các thành phần đó thành những bean có thể cấu hình, tiêm phụ thuộc và kiểm thử theo cách quen thuộc của Spring.

Trong module `SPRING_KAFKA_MESSAGING`, hai điểm vào thường gặp nhất là `KafkaTemplate` để publish sự kiện và `@KafkaListener` để consume sự kiện. Để hiểu cách chúng hoạt động, cần nắm các factory, listener container, serializer/deserializer và các thành phần quản trị đi kèm.

Spring Boot có thể tự cấu hình nhiều bean dựa trên dependency và `spring.kafka.*`. Khi cần tùy biến, ứng dụng khai báo bean riêng và kết nối chúng với nhau thông qua dependency injection.

## 2. Bức tranh kiến trúc tổng thể

Các thành phần được chia thành hai luồng chính: luồng gửi ở phía producer và luồng nhận ở phía consumer.

```text
Ứng dụng Spring
│
├── Luồng gửi
│   Service nghiệp vụ
│       │
│       ▼
│   KafkaTemplate
│       │
│       ▼
│   ProducerFactory ── tạo/quản lý KafkaProducer
│       │
│       ▼
│   Serializer ── byte[] ──▶ Kafka broker / topic / partition
│
└── Luồng nhận
    Kafka broker / topic / partition
        │
        ▼
    ConsumerFactory ── tạo KafkaConsumer kèm Deserializer
        │
        ▼
    Listener container ── quản lý consumer và gọi poll()
        │
        ▼
    KafkaConsumer trả record đã deserialize key/value
        │
        ▼
    @KafkaListener ── phương thức xử lý nghiệp vụ

Thành phần hỗ trợ: KafkaAdmin, NewTopic, MessageConverter,
CommonErrorHandler, KafkaTransactionManager và observability.
```

Spring Kafka không thay thế broker. Broker vẫn chịu trách nhiệm lưu record, partition, replication và consumer group. Các bean Spring điều phối việc tạo Kafka client, chuyển dữ liệu giữa mô hình ứng dụng và Kafka, cũng như quản lý vòng đời xử lý.

## 3. Cấu hình nền tảng và Spring Boot auto-configuration

Khi thêm dependency Spring Kafka hoặc starter tương ứng của Spring Boot, ứng dụng có thể cấu hình các thuộc tính kết nối trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      group-id: order-notification
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders.events
    listener:
      ack-mode: record
```

`bootstrap-servers` cung cấp địa chỉ broker để client lấy metadata và kết nối đến các broker phù hợp. Cấu hình producer và consumer được Spring Boot chuyển thành cấu hình cho Kafka client. `auto-offset-reset` chỉ có tác dụng khi group chưa có committed offset hợp lệ (hoặc offset hiện tại không còn hợp lệ); nó không tự tua lại một group đã có offset.

Auto-configuration giúp tạo các bean mặc định như `ProducerFactory`, `KafkaTemplate`, `ConsumerFactory`, listener container factory và `KafkaAdmin` khi các điều kiện phù hợp. Nếu khai báo bean tùy chỉnh, cần hiểu bean mặc định nào vẫn được tạo và bean nào bị điều kiện auto-configuration thay thế. Tránh khai báo nhiều bean cùng loại mà không chỉ rõ bean nào được sử dụng.

## 4. Các thành phần phía producer

### ProducerFactory

`ProducerFactory<K, V>` là abstraction tạo Kafka producer. Cài đặt thường dùng là `DefaultKafkaProducerFactory`, nhận cấu hình như broker, serializer, acknowledgement, retry và idempotence rồi tạo các đối tượng `KafkaProducer`.

Ứng dụng thường không tự tạo hoặc đóng `KafkaProducer` trong từng phương thức nghiệp vụ. `ProducerFactory` quản lý việc tạo và tái sử dụng producer theo cơ chế của nó, giúp các service dùng chung cấu hình và vòng đời do Spring quản lý.

### KafkaTemplate

`KafkaTemplate<K, V>` là API gửi message ở mức ứng dụng. Nó nhận topic, key, value và có thể nhận thêm partition, timestamp hoặc headers thông qua các overload hay `ProducerRecord`.

```java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total) {}

@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

Trong ví dụ, `orderId` là key để các sự kiện cùng đơn hàng thường được định tuyến về cùng partition theo partitioner đang sử dụng. `OrderCreated` là value được serializer chuyển thành byte trước khi gửi. `send` trả về `CompletableFuture` trong các phiên bản Spring Kafka hiện đại; ứng dụng nên quan sát kết quả hoàn tất để biết record được broker xác nhận hay gửi thất bại.

`KafkaTemplate` cũng hỗ trợ gửi `Message<?>` của Spring Messaging, gửi theo `ProducerRecord`, truy cập metadata kết quả gửi và thực hiện thao tác trong transaction. Nó là API tiện dụng, còn việc tạo producer và cấu hình kết nối vẫn do `ProducerFactory` đảm nhiệm.

### ProducerRecord và SendResult

`ProducerRecord<K, V>` biểu diễn một record sắp gửi, có thể chứa topic, partition tùy chọn, timestamp, key, value và headers. Nếu không chỉ định partition, partitioner sẽ chọn partition dựa trên key hoặc chính sách phân vùng đang cấu hình.

`SendResult<K, V>` chứa record đã gửi cùng `RecordMetadata` do broker trả về, trong đó có topic, partition và offset. Metadata này hữu ích cho log, tracing hoặc chẩn đoán. Không nên dùng offset như một ID nghiệp vụ toàn cục vì offset chỉ có ý nghĩa trong một partition.

## 5. Các thành phần phía consumer

### ConsumerFactory

`ConsumerFactory<K, V>` tạo Kafka consumer với cấu hình group ID, deserializer, commit, poll và các thuộc tính liên quan. Cài đặt phổ biến là `DefaultKafkaConsumerFactory`.

Kafka consumer không thread-safe. Spring Kafka vì vậy để listener container quản lý consumer và thực hiện poll trên thread phù hợp, thay vì cho nhiều thread nghiệp vụ gọi chung một đối tượng consumer.

### @KafkaListener

`@KafkaListener` đánh dấu một phương thức làm điểm nhận record. Annotation có thể khai báo topic, topic pattern, group ID, container factory, concurrency ở mức endpoint, batch listener và các tùy chọn khác.

```java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            id = "order-created-listener",
            topics = "orders",
            groupId = "order-notification")
    public void onOrderCreated(OrderCreated event) {
        // Gọi service nghiệp vụ để xử lý sự kiện.
        System.out.println("Received order: " + event.orderId());
    }
}
```

`KafkaListenerAnnotationBeanPostProcessor` phát hiện annotation khi khởi động, tạo endpoint và đăng ký listener container tương ứng thông qua `KafkaListenerEndpointRegistry`. Khi có record, container chuyển dữ liệu cho phương thức listener sau khi Kafka client deserialize và Spring chuyển đổi payload cần thiết.

Phương thức listener có thể nhận thêm metadata như key, topic, partition, offset hoặc headers thông qua `@Header`, `@Headers` và các hằng số trong `KafkaHeaders`. Đây là cách lấy thông tin vận chuyển mà không phải tự thao tác trực tiếp với Kafka consumer.

### Listener container

Listener container là thành phần thực thi vòng lặp poll, gọi listener, xử lý lỗi và quản lý offset. Hai loại thường gặp:

- `KafkaMessageListenerContainer`: quản lý một Kafka consumer và một luồng xử lý chính cho consumer đó.
- `ConcurrentMessageListenerContainer`: tạo và quản lý nhiều `KafkaMessageListenerContainer` con để tăng concurrency.

Ví dụ, một listener container factory có thể cấu hình concurrency:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        return factory;
    }
}
```

Để listener sử dụng factory này, chỉ rõ tên tại annotation:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-notification",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void onOrderCreated(OrderCreated event) {
    // Xử lý event.
}
```

Concurrency là số consumer mà container có thể tạo cho endpoint. Trong cùng consumer group, mỗi partition tại một thời điểm chỉ được gán cho tối đa một consumer. Vì vậy, tăng concurrency vượt số partition được gán không làm tăng số consumer đang đọc hữu ích; một số consumer có thể không được gán partition. Nếu cần xử lý song song, phải cân nhắc cả số partition, số instance ứng dụng và thời gian xử lý mỗi record.

### KafkaListenerEndpointRegistry

`KafkaListenerEndpointRegistry` quản lý các listener container được tạo từ `@KafkaListener`. Có thể dùng registry để lấy container theo `id`, kiểm tra trạng thái, dừng hoặc khởi động listener theo nhu cầu vận hành. Các container này thường được quản lý thông qua registry thay vì khai báo như bean container độc lập trong context.

Không nên tùy tiện stop/start listener từ nhiều nơi trong ứng dụng. Nếu cần điều khiển động, hãy gom thao tác vào một thành phần quản trị rõ ràng và xử lý trường hợp container chưa được đăng ký hoặc đang trong quá trình khởi động.

## 6. Serialization, deserialization và message conversion

Kafka lưu byte. Producer phải biến key/value thành byte bằng serializer; consumer dùng deserializer để chuyển byte thành kiểu dữ liệu mà ứng dụng có thể sử dụng.

Spring Kafka cung cấp serializer/deserializer cho các kiểu phổ biến và hỗ trợ JSON thông qua `JsonSerializer` và `JsonDeserializer`. Hai phía cần thống nhất schema, kiểu dữ liệu và cách nhận diện type. Cấu hình trusted packages của JSON deserializer nên giới hạn ở package cần thiết, tránh tin cậy toàn bộ package trong môi trường không kiểm soát.

Cần phân biệt hai lớp chuyển đổi:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Serializer / Deserializer | Chuyển key/value giữa object và byte để trao đổi với Kafka | `StringSerializer`, `JsonSerializer`, `JsonDeserializer` |
| MessageConverter | Chuyển đổi giữa Spring `Message<?>` / `ConsumerRecord` và payload, headers của ứng dụng | `MessagingMessageConverter`, `StringJsonMessageConverter` |

Deserializer hoạt động ở lớp Kafka client. Message converter hoạt động ở lớp Spring Messaging và listener adapter. Converter có thể ánh xạ Kafka headers thành Spring message headers, giúp phương thức listener nhận payload và metadata theo kiểu tham số thuận tiện.

Nếu producer và consumer dùng JSON, cần có quy tắc tương thích schema khi thêm, đổi tên hoặc xóa field. Thay đổi cấu trúc event không tương thích có thể khiến consumer cũ lỗi khi đọc dữ liệu mới, hoặc ngược lại. Với hệ thống nhiều dịch vụ, nên quản lý phiên bản schema và quy định chính sách tương thích trước khi triển khai.

## 7. KafkaAdmin và khai báo topic

`KafkaAdmin` dùng Kafka Admin API để thực hiện thao tác quản trị cụm từ ứng dụng Spring. Một ứng dụng có thể khai báo bean `NewTopic`; khi khởi động, KafkaAdmin có thể tạo topic chưa tồn tại với cấu hình được yêu cầu.

```java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, "2")
                .build();
    }
}
```

Ví dụ tạo topic `orders` có 6 partition, replication factor 3 và yêu cầu tối thiểu 2 replica trong ISR khi producer ghi với `acks=all`. Cụm phải có đủ broker để đáp ứng replication factor. Nếu topic đã tồn tại, hành vi thay đổi cấu hình phụ thuộc thao tác và phiên bản; không nên xem bean `NewTopic` là cách tự động sửa mọi cấu hình topic đang chạy.

Trong môi trường production, có thể quản lý topic bằng quy trình hạ tầng riêng thay vì để mọi lần khởi động ứng dụng tự tạo tài nguyên. Dù dùng cách nào, cần xác minh tên, partition, replication factor, retention và ACL của topic.

## 8. Xử lý lỗi, retry và dead-letter

Listener có thể gặp lỗi nghiệp vụ, lỗi dữ liệu, timeout hoặc lỗi hệ thống phụ thuộc. Spring Kafka cung cấp cơ chế error handler để quyết định retry, bỏ qua, phục hồi hoặc chuyển record lỗi sang dead-letter topic.

`CommonErrorHandler` là abstraction xử lý lỗi của listener container. `DefaultErrorHandler` hỗ trợ retry với backoff và có thể kết hợp `DeadLetterPublishingRecoverer` để publish record không xử lý được sang dead-letter topic.

Ví dụ cấu hình retry có giới hạn và gửi record đã thất bại đến DLT:

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }
}
```

Đoạn cấu hình minh họa hai lần retry sau lần xử lý đầu tiên, mỗi lần cách nhau một giây; sau khi hết retry, recoverer gửi record đến topic DLT theo quy tắc định tuyến mặc định hoặc quy tắc được cấu hình thêm. Cần cấu hình serializer cho DLT phù hợp với cả record bình thường và record có payload lỗi; nếu không, chính thao tác publish DLT cũng có thể thất bại.

Retry phù hợp với lỗi tạm thời. Với lỗi dữ liệu không hợp lệ, retry lặp lại thường không giúp ích và có thể làm chậm partition. Nên phân loại exception, đặt backoff và giới hạn retry, theo dõi DLT, đồng thời xây dựng quy trình kiểm tra và phát lại record sau khi khắc phục nguyên nhân.

## 9. Offset, acknowledgement và transaction

Listener container quản lý việc commit offset theo `AckMode`. Các chế độ phổ biến gồm:

- `RECORD`: commit offset sau khi listener xử lý xong từng record.
- `BATCH`: commit offset sau khi xử lý xong một batch record được poll.
- `MANUAL` và `MANUAL_IMMEDIATE`: ứng dụng gọi `Acknowledgment.acknowledge()` để chủ động xác nhận theo quy tắc của chế độ.

Chọn ack mode cần dựa trên mức độ chấp nhận xử lý lặp, thông lượng và cách listener xử lý lỗi. Commit offset trước khi hoàn tất tác dụng phụ nghiệp vụ có thể làm record không được đọc lại dù nghiệp vụ chưa thành công. Commit sau khi xử lý xong có thể dẫn đến giao lại record khi ứng dụng dừng đột ngột trước commit; vì vậy handler vẫn nên idempotent.

Spring Kafka hỗ trợ giao dịch Kafka thông qua `KafkaTransactionManager` và producer factory được cấu hình transaction ID prefix. `KafkaTemplate` có thể gửi record trong transaction, và listener container có thể tham gia luồng xử lý giao dịch theo cấu hình tương ứng. Điều này hữu ích khi cần phối hợp consume-transform-produce trong Kafka với bảo đảm giao dịch phù hợp.

Exactly-once trong Kafka có phạm vi cụ thể: thường bảo đảm kết quả đọc và ghi giữa các topic Kafka trong một luồng được cấu hình transactional và consumer đọc với isolation phù hợp. Nếu listener cập nhật cơ sở dữ liệu quan hệ hoặc gọi API bên ngoài, Kafka transaction không tự tạo một giao dịch ACID chung với hệ thống đó. Khi cần nhất quán giữa database và event, hãy xem xét Transactional Outbox, inbox hoặc cơ chế idempotency.

## 10. Các thành phần bổ trợ và khả năng quan sát

Ngoài các thành phần cốt lõi, Spring Kafka còn có những công cụ giúp xây dựng luồng messaging hoàn chỉnh:

| Thành phần | Mục đích |
|---|---|
| `KafkaOperations` | Interface trừu tượng cho các thao tác gửi Kafka; `KafkaTemplate` là triển khai phổ biến |
| `Message<?>` và `KafkaHeaders` | Mang payload cùng metadata như topic, key, partition, offset và reply topic |
| `ReplyingKafkaTemplate` | Hỗ trợ mẫu request-reply qua Kafka khi ứng dụng thực sự cần chờ phản hồi tương quan |
| `KafkaTransactionManager` | Quản lý transaction sử dụng Kafka producer |
| `KafkaAdmin` | Thực hiện thao tác quản trị topic và tài nguyên Kafka |
| Listener container events | Thông báo các sự kiện vòng đời và trạng thái của listener container |

Trong vận hành, nên theo dõi producer send failure/latency, consumer lag, số record xử lý, retry, DLT, rebalance và trạng thái listener container. Spring Kafka tích hợp với hệ sinh thái metrics/observation của Spring; tên metric và cách export phụ thuộc phiên bản Spring Boot, Micrometer và cấu hình ứng dụng.

Log nên chứa event ID, topic, partition và offset khi phù hợp để hỗ trợ truy vết. Tránh ghi toàn bộ payload nếu có dữ liệu nhạy cảm. Với nhiều dịch vụ, correlation ID hoặc trace context trong message header giúp nối các bước xử lý thành một luồng quan sát được.

## 11. Một luồng xử lý hoàn chỉnh

Giả sử Order Service phát `OrderCreated` và Notification Service nhận sự kiện:

1. Service nghiệp vụ tạo đối tượng `OrderCreated` và gọi `KafkaTemplate`.
2. `KafkaTemplate` chuyển yêu cầu cho `ProducerFactory`; producer serialize key/value thành byte và gửi đến broker.
3. Broker ghi record vào partition; kết quả gửi trả metadata để ứng dụng log hoặc xử lý lỗi.
4. Consumer được tạo bởi `ConsumerFactory` và được listener container quản lý.
5. Container poll record; deserializer và message converter chuẩn bị payload.
6. Listener adapter gọi phương thức `@KafkaListener`.
7. Phương thức gọi service nghiệp vụ, sau đó container xử lý lỗi và commit offset theo ack mode.
8. Nếu xử lý không thành công, error handler quyết định retry hoặc chuyển record sang DLT.

Mỗi thành phần có một trách nhiệm riêng. Việc tách trách nhiệm giúp kiểm thử và thay đổi cấu hình dễ hơn: có thể thay serializer mà không viết lại nghiệp vụ gửi, thay error handler mà không thay listener, hoặc tăng concurrency mà không tự quản lý Kafka consumer thread.

## 12. Tổng kết

- `ProducerFactory` tạo Kafka producer; `KafkaTemplate` là API gửi record từ ứng dụng.
- `ConsumerFactory` tạo Kafka consumer; listener container quản lý poll, gọi listener và offset.
- `@KafkaListener` khai báo điểm nhận record; `KafkaListenerEndpointRegistry` quản lý các container được tạo từ annotation.
- Serializer/deserializer chuyển đổi byte ở lớp Kafka client; MessageConverter chuyển đổi payload và headers ở lớp Spring Messaging.
- `KafkaAdmin` và `NewTopic` hỗ trợ khai báo, quản trị topic.
- `CommonErrorHandler`, `DefaultErrorHandler` và `DeadLetterPublishingRecoverer` hỗ trợ retry và dead-letter.
- `KafkaTransactionManager` hỗ trợ transaction với Kafka; tính nhất quán với database/API ngoài Kafka cần thiết kế bổ sung.

Khi hiểu mối quan hệ giữa các bean này, có thể đọc cấu hình Spring Kafka, lần theo luồng gửi/nhận và lựa chọn đúng thành phần để tùy biến serialization, concurrency, retry, offset hoặc transaction cho ứng dụng messaging tin cậy.
