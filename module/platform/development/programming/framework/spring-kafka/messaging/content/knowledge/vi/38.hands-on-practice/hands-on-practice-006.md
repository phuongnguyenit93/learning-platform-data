# Thêm retry và dead-letter

Trong bài thực hành này, ta hoàn thiện luồng `orders`: producer gửi event vào topic nguồn, consumer xử lý bằng `@KafkaListener`, Spring Kafka tự retry khi gặp lỗi tạm thời và chuyển record sang dead-letter topic (DLT) khi hết lượt hoặc lỗi không nên retry. Ta sẽ kiểm tra cả trường hợp xử lý thành công sau retry và trường hợp record phải được cách ly.

Bài lab dùng blocking retry với `DefaultErrorHandler`. Khi một record đang retry, các record phía sau trong cùng partition phải chờ. Nếu nghiệp vụ cần tiếp tục xử lý record mới trong lúc record lỗi chờ lâu, hãy đánh giá non-blocking retry bằng `@RetryableTopic` và chấp nhận các hệ quả về ordering.

## 1. Mục tiêu và luồng xử lý

Sau khi hoàn thành, ứng dụng có thể:

- Gửi `OrderCreated` vào topic `orders` bằng `KafkaTemplate`.
- Retry tối đa hai lần sau lần xử lý đầu tiên, mỗi lần cách nhau một giây.
- Chuyển `InvalidOrderException` thẳng sang DLT mà không retry.
- Chuyển lỗi tạm thời vẫn còn sau các lần retry sang `orders.DLT`.
- Xác minh record DLT giữ key, payload và metadata nguồn để điều tra.

```mermaid
flowchart TD
    A[Producer: KafkaTemplate] --> B[Topic orders]
    B --> C[@KafkaListener]
    C --> D{Xử lý thành công?}
    D -->|Có| E[Hoàn tất và commit offset theo AckMode]
    D -->|Không| F{Lỗi không retry?}
    F -->|Có| H[DeadLetterPublishingRecoverer]
    F -->|Không| G{Còn retry?}
    G -->|Có| I[BackOff 1 giây rồi giao lại]
    I --> C
    G -->|Hết lượt| H
    H --> J[Topic orders.DLT]
    J --> K[DLT consumer / quy trình điều tra]
```

## 2. Thêm dependency

Nếu dự án chưa có Spring Kafka, thêm thư viện `spring-kafka`. Dependency kiểm thử `spring-kafka-test` dùng cho Embedded Kafka ở phần cuối. Khi dùng Spring Boot, để dependency management của Boot quản lý version tương thích:

```kotlin
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
```

Spring Boot dependency management/BOM có thể quản lý version tương thích cho hai dependency này. Không trộn tùy ý các version Kafka client và Spring Kafka.

## 3. Chuẩn bị topic nguồn và DLT

Ví dụ dùng topic nguồn `orders` có ba partition. DLT cũng cần ít nhất ba partition vì cấu hình bên dưới giữ nguyên số partition của record nguồn khi định tuyến sang DLT.

```java
@Bean
NewTopic ordersTopic() {
    return TopicBuilder.name("orders")
        .partitions(3)
        .replicas(1)
        .build();
}

@Bean
NewTopic ordersDltTopic() {
    return TopicBuilder.name("orders.DLT")
        .partitions(3)
        .replicas(1)
        .build();
}
```

Replication factor bằng `1` phù hợp cho broker local hoặc Embedded Kafka một node. Trong môi trường thật, hãy provision topic bằng công cụ quản trị và đặt replication factor, `min.insync.replicas`, retention cùng ACL theo tiêu chuẩn của cluster. Principal runtime của consumer không nhất thiết cần quyền tạo topic.

Nếu không khai báo resolver riêng, `DeadLetterPublishingRecoverer` mặc định cũng định tuyến sang topic có hậu tố `.DLT` và partition tương ứng. Ví dụ tường minh ở phần cấu hình giúp nhìn rõ quy tắc mà ứng dụng đang dùng.

## 4. Cấu hình producer và consumer

Với event JSON, producer dùng `JsonSerializer`, consumer dùng `JsonDeserializer`. Ví dụ cấu hình Spring Boot:

```properties
spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.springframework.kafka.support.serializer.JsonSerializer
spring.kafka.producer.acks=all

spring.kafka.consumer.group-id=orders-service
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties.spring.json.trusted.packages=com.example.orders
```

`auto-offset-reset=earliest` chỉ có tác dụng khi group chưa có committed offset hợp lệ. Trong production, hãy quyết định rõ chính sách offset và trusted package; không mở trusted packages rộng hơn nhu cầu. Ví dụ giả định class event nằm trong package `com.example.orders`.

## 5. Tạo event và phân loại exception

Dùng một event có ID đơn hàng và dữ liệu đủ để xử lý. Ví dụ Java record:

```java
public record OrderCreated(
    String orderId,
    BigDecimal amount,
    String currency
) {}
```

Tách lỗi dữ liệu cố định khỏi lỗi phụ thuộc tạm thời:

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

public class TransientOrderException extends RuntimeException {
    public TransientOrderException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

`InvalidOrderException` biểu thị event không thể xử lý nếu dữ liệu không đổi, chẳng hạn amount âm hoặc currency không được hỗ trợ. `TransientOrderException` biểu thị sự cố có thể tự phục hồi, chẳng hạn dịch vụ định giá tạm timeout. Hãy phân loại theo nguyên nhân nghiệp vụ, không dựa đơn thuần vào việc exception là checked hay runtime.

## 6. Viết listener và để exception truyền ra ngoài

Listener chỉ điều phối nghiệp vụ. Khi service ném exception, đừng bắt rồi chỉ ghi log và trả về bình thường; container có thể xem record đã xử lý thành công và commit offset theo AckMode.

```java
@Component
public class OrderListener {
    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory")
    public void consume(OrderCreated event) {
        orderService.process(event);
    }
}
```

Trong `OrderService`, kiểm tra dữ liệu và gọi dependency. Ví dụ, nếu event không hợp lệ thì ném `InvalidOrderException`; nếu dependency tạm thời không sẵn sàng thì ném `TransientOrderException` và giữ nguyên nguyên nhân gốc. Listener không cần tự viết vòng lặp retry.

```java
public void process(OrderCreated event) {
    if (event.amount().signum() <= 0) {
        throw new InvalidOrderException("Order amount must be positive");
    }
    try {
        pricingClient.verify(event.orderId(), event.amount(), event.currency());
        orderRepository.save(event);
    } catch (PricingTimeoutException ex) {
        throw new TransientOrderException("Pricing service timed out", ex);
    }
}
```

`PricingTimeoutException`, `pricingClient` và `orderRepository` đại diện cho thành phần của ứng dụng. Trong code thật, chỉ chuyển các lỗi phụ thuộc có thể phục hồi thành `TransientOrderException`; lỗi dữ liệu hoặc quy tắc nghiệp vụ phải giữ loại exception không retry tương ứng.

## 7. Cấu hình DefaultErrorHandler và DLT recoverer

`DefaultErrorHandler` nhận một `BackOff` và một recoverer. `FixedBackOff(1_000L, 2L)` nghĩa là chờ một giây giữa các lần retry và cho phép hai lần retry sau lần xử lý ban đầu. Tổng số lần listener có thể được gọi là ba.

```java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {
        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()));

        // Không xem việc gửi DLT là thành công nếu broker báo lỗi.
        recoverer.setFailIfSendResultIsError(true);

        DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer, new FixedBackOff(1_000L, 2L));

        handler.addNotRetryableExceptions(InvalidOrderException.class);
        handler.addRetryableExceptions(TransientOrderException.class);
        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler ordersErrorHandler) {
        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(ordersErrorHandler);
        return factory;
    }
}
```

Đảm bảo `KafkaTemplate` dùng bởi recoverer có serializer phù hợp với key/value của record được gửi sang DLT. Với event JSON, template cần gửi được kiểu payload mà consumer thực tế nhận. Nếu xử lý lỗi deserialize, payload có thể là byte array gốc; khi đó cần cấu hình template hỗ trợ cả kiểu byte array và kiểu domain hoặc một chiến lược serialization phù hợp.

Resolver trong ví dụ tạo tên DLT bằng cách thêm `.DLT` vào topic nguồn và giữ nguyên partition. Vì vậy, `orders.DLT` phải có đủ partition tương ứng. Nếu topic nguồn có partition 2 nhưng DLT chỉ có một partition, publish có thể thất bại; không giả định Kafka tự ánh xạ partition về một partition hợp lệ.

## 8. Gắn producer và gửi event

Producer gửi event với key là `orderId`. Cùng một đơn hàng vì vậy được định tuyến ổn định vào cùng partition của topic `orders` theo partitioner mặc định:

```java
@Service
public class OrderPublisher {
    private final KafkaTemplate<Object, Object> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<Object, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<Object, Object>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "orders", event.orderId(), event);
    }
}
```

Trong Spring Kafka 3.x trở lên, `send()` trả về `CompletableFuture`; có thể chờ future trong test để xác nhận producer đã nhận acknowledgement. Spring Kafka 2.x dùng `ListenableFuture` và callback tương ứng. Trong luồng production, xử lý future bất đồng bộ và ghi nhận send failure; không chặn thread nghiệp vụ chỉ để đợi kết quả gửi nếu không cần.

## 9. Đọc và điều tra record trong DLT

Một consumer riêng có thể theo dõi DLT. Dùng group ID riêng để consumer kiểm tra DLT không ảnh hưởng group xử lý topic nguồn:

```java
@KafkaListener(topics = "orders.DLT", groupId = "orders-dlt-audit")
public void inspectDeadLetter(ConsumerRecord<String, OrderCreated> record) {
    log.warn(
        "Dead letter received: topic={}, partition={}, offset={}, key={}",
        record.topic(), record.partition(), record.offset(), record.key());

    // Có thể đọc headers để lấy topic/partition/offset nguồn và exception.
    record.headers().forEach(header ->
        log.debug("DLT metadata header: {}", header.key()));
}
```

`DeadLetterPublishingRecoverer` bổ sung header để truy vết topic, partition, offset nguồn và thông tin exception. Khi lưu log hoặc audit, tránh ghi toàn bộ payload nhạy cảm hay thông tin bí mật. DLT là nơi cách ly và điều tra; nó không tự sửa dữ liệu hoặc tự phát lại record.

Khi cần replay, hãy sửa nguyên nhân trước, xác minh event còn hợp lệ với trạng thái nghiệp vụ hiện tại rồi phát lại theo quy trình có kiểm soát. Giữ event ID ổn định và thiết kế consumer idempotent vì replay có thể tạo lần giao lại.

## 10. Hiểu chính xác retry và offset

Với cấu hình `FixedBackOff(1_000L, 2L)`, luồng xử lý có các trường hợp:

| Loại lỗi | Số lần listener tối đa | Kết quả |
| --- | ---: | --- |
| Xử lý thành công ngay | 1 | Không vào DLT |
| `TransientOrderException`, thành công ở lần thứ ba | 3 | Tiếp tục xử lý bình thường |
| `TransientOrderException`, thất bại cả ba lần | 3 | Recoverer gửi sang `orders.DLT` |
| `InvalidOrderException` | 1 | Bỏ qua retry và gửi thẳng sang DLT |

Đây là blocking retry: record lỗi giữ vị trí đầu luồng của partition trong thời gian retry. Các record phía sau trong cùng partition chờ cho đến khi record lỗi được xử lý thành công hoặc recovery hoàn tất. Các partition khác vẫn có thể được consumer khác xử lý.

Khi recovery publish DLT thành công, error handler có thể tiếp tục theo chính sách acknowledgement/commit của container. Nếu publish DLT thất bại và `setFailIfSendResultIsError(true)` báo lỗi, recovery chưa được xem là thành công; record có thể được xử lý lại. Vì vậy cần theo dõi cả lỗi gửi DLT, không chỉ lỗi listener.

## 11. Kiểm thử bằng Embedded Kafka

Thêm `spring-kafka-test` ở test scope và tạo broker với cả topic nguồn lẫn DLT. Dùng ba partition cho cả hai topic để khớp resolver:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 3,
    topics = {"orders", "orders.DLT"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrdersRetryIntegrationTest {
    @Autowired
    KafkaTemplate<Object, Object> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Test
    void invalidOrderIsPublishedToDlt() throws Exception {
        Map<String, Object> props = KafkaTestUtils.consumerProps(
            "dlt-check-" + UUID.randomUUID(), "false", embeddedKafka);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        try (Consumer<String, byte[]> dltConsumer =
                new DefaultKafkaConsumerFactory<>(
                    props, new StringDeserializer(),
                    new ByteArrayDeserializer()).createConsumer()) {
            embeddedKafka.consumeFromAnEmbeddedTopic(
                dltConsumer, "orders.DLT");

            OrderCreated invalid = new OrderCreated(
                "order-invalid", new BigDecimal("-10.00"), "VND");
            kafkaTemplate.send("orders", invalid.orderId(), invalid)
                .get(10, TimeUnit.SECONDS);

            ConsumerRecord<String, byte[]> deadLetter =
                KafkaTestUtils.getSingleRecord(dltConsumer, "orders.DLT");
            assertThat(deadLetter.key()).isEqualTo("order-invalid");
            assertThat(deadLetter.value()).isNotEmpty();
            assertThat(deadLetter.headers().toArray()).isNotEmpty();
        }
    }
}
```

Consumer kiểm thử dùng `ByteArrayDeserializer` để đọc payload DLT thô mà không phụ thuộc type header của JSON. Trong project, thêm các import và assertion library tương ứng. `getSingleRecord` chờ record trong giới hạn mặc định của helper; nếu suite có nhiều record DLT, dùng topic riêng cho test hoặc poll và lọc theo key.

Bổ sung các ca kiểm thử sau:

- Event hợp lệ được xử lý một lần và không xuất hiện ở DLT.
- Dependency giả lập lỗi hai lần rồi thành công ở lần thứ ba; listener được gọi ba lần nhưng không có DLT record.
- Dependency thất bại liên tục; record xuất hiện trong DLT sau lần xử lý thứ ba.
- `InvalidOrderException` được chuyển DLT ngay sau lần đầu, không chờ backoff.
- DLT broker/topic không sẵn sàng; xác minh recovery thất bại và offset nguồn không bị xác nhận như thể đã recover.
- Record DLT có đúng key, payload và header metadata nguồn.

## 12. Vận hành và xử lý sự cố

Theo dõi số lần retry, listener failure, số record vào DLT, lỗi publish DLT, consumer lag và tuổi của record cũ nhất trong DLT. Khi DLT tăng đột biến, phân loại theo exception type và topic nguồn để tìm nguyên nhân: dependency mất kết nối, payload sai hoặc lỗi code.

Một số tình huống thường gặp:

| Triệu chứng | Kiểm tra |
| --- | --- |
| Record retry liên tục | Exception có được phân loại đúng không; backoff và số lần retry có phù hợp không. |
| Không thấy record trong DLT | Recoverer có được gắn vào đúng factory không; DLT topic có tồn tại và đúng partition count không. |
| Gửi DLT lỗi | Serializer của template, ACL `WRITE`, broker connectivity và topic đích. |
| Record sau bị chậm | Blocking retry đang giữ partition; xem xét giảm backoff hoặc non-blocking retry nếu ordering cho phép. |
| Replay tạo side effect trùng | Dùng event ID ổn định và idempotency ở tầng nghiệp vụ. |

DLT cần retention đủ dài cho điều tra nhưng cũng cần quy trình xử lý và dọn dữ liệu. Không replay hàng loạt trước khi sửa nguyên nhân gốc, vì các record có thể quay lại DLT và tạo vòng lặp.

## 13. Checklist hoàn thành bài thực hành

- [ ] Tạo topic `orders` và `orders.DLT` với partition count tương thích.
- [ ] Cấu hình JSON serializer/deserializer cho event.
- [ ] Tạo listener và để exception truyền ra error handler.
- [ ] Gắn `DefaultErrorHandler` vào đúng listener container factory.
- [ ] Cấu hình hai lần retry với backoff một giây.
- [ ] Phân loại `InvalidOrderException` là không retry.
- [ ] Cấu hình `DeadLetterPublishingRecoverer` và xác nhận kết quả gửi.
- [ ] Kiểm tra DLT metadata và quy trình replay có kiểm soát.
- [ ] Chạy integration test cho success, retry success, retry exhausted và non-retryable failure.
- [ ] Theo dõi retry, DLT, lag và lỗi recovery trong môi trường chạy.

Bài thực hành hoàn tất khi một event hợp lệ đi qua topic nguồn và được xử lý thành công, lỗi tạm thời được retry đúng giới hạn, lỗi dữ liệu cố định được chuyển DLT ngay, và lỗi kéo dài được chuyển DLT sau khi hết lượt. Khi kết hợp retry có giới hạn, recoverer xác nhận publish, offset commit đúng thời điểm và idempotency, luồng Spring Kafka có thể phục hồi lỗi mà vẫn giữ được khả năng truy vết.
