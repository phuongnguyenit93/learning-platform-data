# Gửi và nhận record trong JUnit

Kiểm thử producer và consumer Kafka cần xác minh cả hai đầu của luồng: producer gửi đúng record lên topic, và consumer nhận đúng key, value, headers cùng metadata cần thiết. Với Spring Kafka, có thể dùng `spring-kafka-test` để chạy Kafka broker nhúng trong JUnit, kết hợp `KafkaTemplate`, `@KafkaListener` và các tiện ích `KafkaTestUtils`.

Một bài test tốt cần phân biệt thời điểm broker xác nhận publish với thời điểm listener hoàn tất xử lý. `KafkaTemplate.send()` trả về kết quả bất đồng bộ; chờ future thành công chứng minh broker đã xác nhận record theo cấu hình producer, nhưng chưa chứng minh consumer đã xử lý xong. Muốn kiểm tra consumer, hãy chờ một tín hiệu từ listener như `BlockingQueue`, `CountDownLatch` hoặc Awaitility.

## 1. Chọn loại kiểm thử phù hợp

Không phải mọi kiểm thử Kafka đều cần khởi động broker. Hãy chọn mức kiểm thử theo hành vi cần xác minh:

| Loại kiểm thử | Thành phần | Mục tiêu |
| --- | --- | --- |
| Unit test | Mockito, fake hoặc stub | Kiểm tra service gọi `KafkaTemplate` với topic, key và payload mong đợi |
| Integration test với Embedded Kafka | `@EmbeddedKafka`, `KafkaTemplate`, `@KafkaListener` | Xác minh serialize/deserialize, publish, consume và listener container hoạt động cùng nhau |
| Integration test với Testcontainers | Kafka container gần với broker triển khai | Kiểm tra phiên bản broker, transaction, security, ACL hoặc cấu hình vận hành thực tế |

`spring-kafka-test` cung cấp broker nhúng và tiện ích kiểm thử. Với các tình huống cần xác minh tương thích Kafka broker cụ thể, SASL/SSL, KRaft hoặc hành vi transaction ở môi trường gần production, Testcontainers thường phù hợp hơn vì cho phép chạy image broker có phiên bản xác định.

## 2. Thêm dependency kiểm thử

Với Maven, thêm `spring-kafka-test` ở scope `test`:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dự án dùng Spring Boot dependency management, để BOM quản lý version của Spring Kafka và `spring-kafka-test` tương thích với nhau. Tránh khai báo một version test library khác với version Spring Kafka đang chạy trong ứng dụng.

JUnit 5 thường đã có trong starter test của Spring Boot. Nếu dự án không dùng Spring Boot, cần có JUnit Jupiter và Spring Test tương ứng để dùng `@SpringJUnitConfig`.

## 3. Khởi tạo Embedded Kafka trong JUnit 5

`@EmbeddedKafka` tạo broker Kafka cho test và có thể tạo sẵn topic. Kết hợp `@SpringJUnitConfig` để nạp cấu hình Spring chứa producer factory, consumer factory và listener container factory.

Ví dụ dưới đây dùng topic `orders-it` với một partition. Key và value đều là chuỗi để tập trung vào luồng gửi/nhận record; khi kiểm thử DTO, có thể thay serializer/deserializer bằng JSON hoặc Avro tương ứng.

```java
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.kafka.annotation.EnableKafka;

@Configuration
@EnableKafka
class KafkaTestConfiguration {

    @Bean
    ConsumerFactory<String, String> consumerFactory(
            EmbeddedKafkaBroker broker) {
        Map<String, Object> props = KafkaTestUtils.consumerProps(
                "orders-listener-group", "false", broker);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        return new DefaultKafkaConsumerFactory<>(
                props, new StringDeserializer(), new StringDeserializer());
    }

    @Bean
    ProducerFactory<String, String> producerFactory(
            EmbeddedKafkaBroker broker) {
        Map<String, Object> props = KafkaTestUtils.producerProps(broker);
        return new DefaultKafkaProducerFactory<>(
                props, new StringSerializer(), new StringSerializer());
    }

    @Bean
    KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory) {
        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        return factory;
    }

    @Bean
    OrderTestListener orderTestListener() {
        return new OrderTestListener();
    }
}
```

`KafkaTestUtils.consumerProps()` và `producerProps()` lấy bootstrap server cùng một số cấu hình phù hợp từ broker nhúng. `auto.offset.reset=earliest` giúp consumer test đọc được record từ đầu nếu chưa có committed offset cho group. Trong bài test gửi record sau khi listener đã khởi động, điều này cũng giúp tránh phụ thuộc vào offset cũ của group được tái sử dụng.

## 4. Kiểm thử producer gửi record và @KafkaListener nhận record

Tạo một listener chỉ dùng trong test. Listener đưa record đã nhận vào `BlockingQueue` để test thread có thể chờ kết quả mà không cần `Thread.sleep()`:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

class OrderTestListener {

    private final BlockingQueue<ConsumerRecord<String, String>> received =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            id = "orders-test-listener",
            topics = "orders-it",
            groupId = "orders-listener-group")
    public void onOrder(ConsumerRecord<String, String> record) {
        received.add(record);
    }

    public BlockingQueue<ConsumerRecord<String, String>> received() {
        return received;
    }
}
```

Bean listener đã được đăng ký trong `KafkaTestConfiguration`. Sau đó viết test JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.kafka.support.SendResult;

@SpringJUnitConfig(classes = KafkaTestConfiguration.class)
@EmbeddedKafka(partitions = 1, topics = "orders-it")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderKafkaIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private OrderTestListener listener;

    @Test
    void sendsRecordAndListenerReceivesIt() throws Exception {
        SendResult<String, String> sendResult = kafkaTemplate
                .send("orders-it", "order-42", "ORDER_CREATED")
                .get(10, TimeUnit.SECONDS);

        assertNotNull(sendResult.getRecordMetadata());

        ConsumerRecord<String, String> received = listener.received()
                .poll(10, TimeUnit.SECONDS);

        assertNotNull(received, "Listener không nhận được record trong thời hạn chờ");
        assertEquals("orders-it", received.topic());
        assertEquals("order-42", received.key());
        assertEquals("ORDER_CREATED", received.value());
        assertEquals(0, received.partition());
        assertEquals(0L, received.offset());
    }
}
```

Trong cấu hình thực tế, `KafkaTestConfiguration` cần khai báo thêm bean `OrderTestListener` như đoạn trước. Có thể gộp bean này vào cùng class cấu hình. Test context được đóng sau class nhờ `@DirtiesContext`; listener container và producer factory do Spring quản lý lifecycle.

`send(...).get(...)` chờ broker xác nhận publish. `received().poll(...)` chờ listener thực sự nhận record. Không thay hai bước này bằng một `Thread.sleep(1000)`: thời gian xử lý phụ thuộc máy chạy test và tải broker, nên sleep có thể vừa làm test chậm vừa tạo lỗi chập chờn.

Offset bằng 0 trong ví dụ chỉ đúng khi topic vừa được tạo, chưa có record trước đó và chỉ có record test này. Nếu test chạy lại trên topic dùng chung, hãy kiểm tra topic/partition/key/value hoặc metadata theo điều kiện phù hợp thay vì cố định offset bằng 0.

## 5. Kiểm tra record trực tiếp bằng KafkaTestUtils

Nếu mục tiêu là kiểm tra producer đã ghi đúng record vào Kafka, có thể tạo một consumer test riêng và đọc topic bằng `KafkaTestUtils`. Cách này hữu ích khi không cần khởi động Spring listener container.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@Test
void producerWritesRecordToTopic() throws Exception {
    Map<String, Object> props = KafkaTestUtils.consumerProps(
            "orders-verification-group", "false", embeddedKafka);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    try (Consumer<String, String> consumer =
            new DefaultKafkaConsumerFactory<String, String>(
                    props,
                    new StringDeserializer(),
                    new StringDeserializer()).createConsumer()) {

        embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders-it");

        kafkaTemplate.send("orders-it", "order-99", "ORDER_CREATED")
                .get(10, TimeUnit.SECONDS);

        ConsumerRecords<String, String> records = KafkaTestUtils.getRecords(
                consumer, Duration.ofSeconds(10));

        assertEquals(1, records.count());
        ConsumerRecord<String, String> record = records.iterator().next();
        assertEquals("order-99", record.key());
        assertEquals("ORDER_CREATED", record.value());
    }
}
```

Trong class test này cần inject `EmbeddedKafkaBroker` và `KafkaTemplate`:

```java
@Autowired
private EmbeddedKafkaBroker embeddedKafka;

@Autowired
private KafkaTemplate<String, String> kafkaTemplate;
```

Consumer test dùng group ID riêng để không chia partition với listener group của ứng dụng. Tạo consumer trước khi gửi record và subscribe vào topic trước khi publish giúp test dễ dự đoán hơn. `try-with-resources` bảo đảm consumer được đóng kể cả khi assertion thất bại.

## 6. Kiểm thử producer service bằng Mockito

Unit test của service không cần broker nếu chỉ muốn xác minh service gọi `KafkaTemplate` với tham số chính xác. Ví dụ:

```java
@ExtendWith(MockitoExtension.class)
class OrderPublisherTest {

    @Mock
    KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @InjectMocks
    OrderPublisher orderPublisher;

    @Test
    void publishesOrderCreatedEvent() {
        OrderCreated event = new OrderCreated("order-42");

        orderPublisher.publish(event);

        verify(kafkaTemplate).send(
                "orders", "order-42", event);
    }
}
```

Đây là unit test cho quyết định của service, không xác minh broker nhận record, serializer hoạt động hay listener consume thành công. Không nên dùng mock để thay thế toàn bộ integration test khi mục tiêu là kiểm thử luồng Kafka thực.

Nếu service xử lý kết quả future, hãy mock `CompletableFuture<SendResult<...>>` tương ứng và kiểm tra nhánh thành công/thất bại. Với các version Spring Kafka hiện đại, `KafkaTemplate.send()` trả về `CompletableFuture`; dự án cũ có thể dùng API future khác, vì vậy hãy theo đúng version dependency đang dùng.

## 7. Kiểm tra metadata của ConsumerRecord

Khi kiểm thử, đừng chỉ assert payload. `ConsumerRecord` còn cung cấp thông tin hữu ích để phát hiện lỗi routing hoặc serialization:

| Thuộc tính | Cách kiểm tra |
| --- | --- |
| `topic()` | Record được gửi đến đúng topic |
| `partition()` | Key/partitioner đưa record đến partition mong đợi |
| `offset()` | Record có vị trí hợp lệ trong partition |
| `key()` | Key đúng để bảo toàn partitioning/order theo key |
| `value()` | Payload sau deserialize đúng giá trị |
| `headers()` | Correlation ID, event type, trace ID hoặc metadata nghiệp vụ được giữ |
| `timestamp()` | Timestamp đúng loại và khoảng thời gian mong đợi |

Ví dụ kiểm tra header:

```java
Header eventType = received.headers().lastHeader("event-type");
assertNotNull(eventType);
assertEquals(
        "OrderCreated",
        new String(eventType.value(), StandardCharsets.UTF_8));
```

Khi header có thể xuất hiện nhiều lần, dùng `lastHeader()` hoặc duyệt toàn bộ headers theo đúng hợp đồng. Không giả định header luôn duy nhất.

## 8. Tránh test chập chờn và rò rỉ tài nguyên

Các test Kafka thường không ổn định khi dùng chung topic, group ID hoặc offset giữa nhiều test. Một số nguyên tắc giúp test lặp lại được:

1. Dùng topic và group ID riêng cho test hoặc class test; không dựa vào dữ liệu còn sót từ lần chạy trước.
2. Tạo consumer và subscribe trước khi gửi record nếu test đọc trực tiếp từ topic.
3. Chờ future gửi và chờ listener bằng timeout hữu hạn; không dùng sleep cố định.
4. Dùng `BlockingQueue`, `CountDownLatch` hoặc Awaitility để đồng bộ giữa test thread và listener thread.
5. Đóng consumer, producer factory và listener container theo lifecycle của Spring/test.
6. Tránh chạy nhiều test đồng thời trên cùng topic/group nếu test có thể tiêu thụ record của nhau.
7. Không assert offset tuyệt đối nếu topic không được làm sạch hoặc có nhiều record.
8. Khi test fail, in topic, partition, offset, key và group ID để dễ chẩn đoán.

Nếu listener chạy bất đồng bộ, hãy chờ kết quả ở một điểm đồng bộ rõ ràng. Một latch được đếm trong listener sau khi xử lý xong thường phù hợp hơn việc chỉ chờ producer future hoàn tất.

## 9. Kiểm thử gửi/nhận DTO và serializer thực tế

Với payload là DTO, integration test nên dùng serializer/deserializer giống cấu hình ứng dụng. Ví dụ producer dùng `JsonSerializer` và consumer dùng `JsonDeserializer` với trusted package/type mapping phù hợp. Nếu chỉ dùng `StringSerializer` trong test, bạn chưa xác minh được cấu hình JSON của ứng dụng.

Các trường hợp nên kiểm tra:

- DTO có field null hoặc field optional.
- Enum, timestamp và kiểu số được serialize/deserialize đúng.
- Header type mapping hoặc event type được giữ theo contract.
- Payload không hợp lệ dẫn đến exception mong đợi và error handler xử lý đúng.
- Schema version cũ/mới có thể đọc theo compatibility policy nếu dùng Schema Registry.

Không nên tắt validation hoặc mở trusted package quá rộng chỉ để test chạy qua. Hãy cấu hình serializer giống môi trường thật và giới hạn trusted type theo mô hình bảo mật của ứng dụng.

## 10. Khi nào cần Testcontainers?

Embedded Kafka thuận tiện, khởi động nhanh và phù hợp với test luồng cơ bản. Tuy nhiên, nếu hành vi phụ thuộc phiên bản broker hoặc cấu hình cluster, hãy dùng Testcontainers để chạy Kafka image phù hợp.

Testcontainers đặc biệt hữu ích khi kiểm thử:

- Kafka transaction và `read_committed`/`read_uncommitted`.
- EOS V2 và producer fencing theo consumer group metadata.
- SASL, TLS, ACL và xác thực client.
- Tương thích broker/client khi nâng cấp Kafka.
- KRaft, listener address và cấu hình broker gần production.

Dù dùng Embedded Kafka hay Testcontainers, vẫn nên giữ test độc lập bằng topic/group riêng và dọn tài nguyên sau khi test hoàn tất.

## 11. Những lỗi thường gặp

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `send()` thành công nhưng listener chưa nhận | Producer future chỉ xác nhận broker, không xác nhận listener xử lý | Chờ tín hiệu từ listener bằng queue/latch |
| Consumer không thấy record | Subscribe sau khi gửi, group offset ở cuối, topic sai hoặc listener chưa start | Tạo consumer trước, cấu hình offset phù hợp và chờ container sẵn sàng |
| Test đọc record cũ | Dùng lại topic/group từ test khác | Tách topic/group hoặc dùng topic mới cho test |
| Test timeout ngẫu nhiên | Dùng `Thread.sleep()` hoặc timeout quá ngắn | Dùng queue/latch/Awaitility và timeout hợp lý |
| Offset khác 0 | Topic đã có record hoặc test chạy lại | Không hardcode offset nếu không kiểm soát trạng thái topic |
| Listener không được gọi | Sai `groupId`, `containerFactory`, deserializer hoặc topic | Kiểm tra listener container, group và cấu hình consumer |
| Test treo khi kết thúc | Consumer/container không được đóng | Dùng try-with-resources và lifecycle Spring |

## 12. Checklist kiểm thử JUnit

- [ ] Dependency `spring-kafka-test` tương thích với Spring Kafka của ứng dụng.
- [ ] Embedded Kafka tạo đúng topic và số partition cần thiết.
- [ ] Producer/consumer test dùng serializer/deserializer đúng với mục tiêu kiểm thử.
- [ ] `KafkaTemplate.send()` được chờ kết quả với timeout hữu hạn.
- [ ] Consumer được xác minh độc lập bằng listener queue/latch hoặc test consumer.
- [ ] Test kiểm tra topic, key, value và metadata cần thiết.
- [ ] Topic/group ID không xung đột giữa các test.
- [ ] Không dùng `Thread.sleep()` để đồng bộ test.
- [ ] Consumer và listener container được đóng đúng lifecycle.
- [ ] Các tính năng transaction, security hoặc broker-specific được kiểm tra trên broker phù hợp khi cần.

Khi kiểm thử gửi và nhận record trong JUnit, hãy xác minh riêng việc broker nhận publish và việc consumer hoàn tất xử lý. Embedded Kafka cùng `KafkaTemplate`, `@KafkaListener` và `KafkaTestUtils` giúp tạo integration test nhanh; Mockito phù hợp với unit test service, còn Testcontainers giúp kiểm tra hành vi phụ thuộc broker thật. Tách rõ các mục tiêu này sẽ giúp test phát hiện đúng lỗi của producer, serialization, consumer và listener container.
