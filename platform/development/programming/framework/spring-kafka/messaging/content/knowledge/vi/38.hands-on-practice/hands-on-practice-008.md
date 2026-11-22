# Thêm kiểm thử với broker nhúng

Khi phát triển ứng dụng Spring Kafka, cần kiểm tra producer, consumer và listener container với một Kafka broker thực. `spring-kafka-test` cung cấp `@EmbeddedKafka` để khởi chạy broker nhúng ngay trong tiến trình kiểm thử. Nhờ đó, integration test có thể gửi record qua `KafkaTemplate`, để `@KafkaListener` nhận record, rồi xác minh payload, key, header, partition và kết quả xử lý.

Broker nhúng giúp kiểm thử luồng Kafka mà không cần cài một cluster riêng hoặc phụ thuộc Docker. Nó không phải mock của `KafkaTemplate`: producer và consumer vẫn sử dụng Kafka client và giao thức Kafka để giao tiếp với broker. Tuy nhiên, cấu hình embedded broker thường nhỏ hơn production; các hành vi phụ thuộc nhiều broker, replication, TLS/SASL hoặc topology production cần được kiểm thử bổ sung bằng môi trường phù hợp.

## 1. Vì sao cần broker nhúng?

Unit test có thể kiểm tra business service bằng Mockito, nhưng không chứng minh serializer, deserializer, topic, partition, consumer group và listener container hoạt động đúng khi ghép lại.

Embedded Kafka phù hợp để kiểm tra:

- Producer gửi record qua `KafkaTemplate` và nhận acknowledgement.
- Consumer nhận record từ topic bằng Kafka client.
- `@KafkaListener` được đăng ký và gọi đúng.
- Key, value, header, timestamp và partition metadata được truyền đúng.
- Consumer group và offset hoạt động theo cấu hình.
- Retry, error handler và dead-letter topic trong một broker test.
- Transaction và `read_committed` khi broker test được cấu hình hỗ trợ.

Luồng kiểm thử cơ bản:

```text
JUnit test
    |
    | KafkaTemplate.send(...)
    v
Embedded Kafka broker
    |
    | topic / partition
    v
Spring Kafka listener container
    |
    v
@KafkaListener
    |
    v
Test probe (BlockingQueue)
    |
    v
JUnit assertions
```

Test gửi record tới broker thật, sau đó chờ listener xử lý bất đồng bộ. Vì vậy, không nên dùng `Thread.sleep()` cố định để đoán thời điểm listener hoàn tất.

## 2. Thêm dependency spring-kafka-test

Với Maven, thêm dependency ở scope `test`:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dự án dùng Spring Boot dependency management, để BOM quản lý phiên bản tương thích với Spring Kafka đang dùng. Tránh tự chọn một phiên bản `spring-kafka-test` khác phiên bản `spring-kafka` của ứng dụng.

Với Gradle:

```kotlin
testImplementation("org.springframework.kafka:spring-kafka-test")
```

Nếu dự án không dùng dependency management của Spring Boot, cần khai báo phiên bản đồng bộ với Spring Kafka runtime. `spring-kafka-test` cung cấp `@EmbeddedKafka`, `EmbeddedKafkaBroker`, `KafkaTestUtils` và `ContainerTestUtils` để hỗ trợ test.

## 3. Khởi tạo broker bằng @EmbeddedKafka

Đặt `@EmbeddedKafka` trên test class để khởi chạy broker trong vòng đời test context:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest
@EmbeddedKafka(
        partitions = 1,
        topics = "orders.created",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderMessagingIntegrationTest {
}
```

Các thuộc tính đáng chú ý:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `partitions` | Số partition tạo cho mỗi topic được khai báo |
| `topics` | Danh sách topic cần tạo trước khi test |
| `bootstrapServersProperty` | Property Spring nhận địa chỉ bootstrap của embedded broker |
| `brokerProperties` | Các broker property bổ sung cho môi trường test |
| `kraft` | Chọn chế độ KRaft ở các phiên bản Spring Kafka hỗ trợ thuộc tính này |

Ví dụ dùng `bootstrapServersProperty = "spring.kafka.bootstrap-servers"` giúp Spring Boot `ProducerFactory` và `ConsumerFactory` kết nối tới embedded broker. Nếu dùng property riêng, cần bảo đảm cả producer và consumer đều đọc đúng property đó.

## 4. Cấu hình Spring Boot cho test

Trong integration test, ứng dụng nên dùng bootstrap server của embedded broker và một consumer group dành riêng cho test:

```java
@SpringBootTest(properties = {
        "spring.kafka.consumer.group-id=orders-embedded-test",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.enable-auto-commit=false"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "orders.created",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderMessagingIntegrationTest {
}
```

`auto-offset-reset=earliest` giúp consumer group test mới đọc từ đầu partition nếu chưa có committed offset. `enable-auto-commit=false` phù hợp với Spring Kafka listener container vì container quản lý offset theo `AckMode`.

Nếu listener khai báo `groupId` trực tiếp trong `@KafkaListener`, giá trị đó có thể ghi đè group ID mặc định. Hãy bảo đảm test dùng group riêng, tránh đọc committed offset từ test run trước.

## 5. Tạo listener probe để quan sát record

Một cách đơn giản để kiểm tra listener là đưa record nhận được vào `BlockingQueue`. Test có thể lấy record từ queue với timeout thay vì chờ bằng `sleep`.

```java
import java.util.concurrent.BlockingQueue;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

public class TestOrderListener {

    private final BlockingQueue<ConsumerRecord<String, String>> received;

    public TestOrderListener(
            BlockingQueue<ConsumerRecord<String, String>> received) {
        this.received = received;
    }

    @KafkaListener(
            id = "embedded-orders-listener",
            topics = "orders.created",
            groupId = "orders-embedded-test")
    public void listen(ConsumerRecord<String, String> record) {
        received.add(record);
    }
}
```

Trong ứng dụng thật, listener thường gọi application service hoặc repository. Probe ở trên chỉ dành cho test để giữ lại record và cho phép assertion trên key, value, header, topic, partition và offset.

## 6. Đăng ký probe trong Spring test context

Có thể khai báo một nested `@TestConfiguration` để tạo queue và listener bean chỉ dành cho test:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
static class ListenerTestConfiguration {

    @Bean
    BlockingQueue<ConsumerRecord<String, String>> receivedRecords() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    TestOrderListener testOrderListener(
            BlockingQueue<ConsumerRecord<String, String>> receivedRecords) {
        return new TestOrderListener(receivedRecords);
    }
}
```

Import cấu hình này vào test class:

```java
@Import(ListenerTestConfiguration.class)
```

Spring Kafka phát hiện `@KafkaListener` trên bean listener và đăng ký endpoint vào listener container registry. Test có thể lấy container theo ID để chờ partition assignment trước khi gửi record.

Nếu ứng dụng đã có listener thật, có thể kiểm tra side effect của application service/repository thay vì tạo probe riêng. Tránh để cả listener production và probe cùng consume một topic trong cùng group nếu mục tiêu test là xác minh một consumer cụ thể; chúng sẽ chia partition và có thể nhận record khác nhau.

## 7. Chờ listener được gán partition

Container khởi động bất đồng bộ. Ngay sau khi Spring context được tạo, consumer có thể chưa hoàn tất group join và partition assignment. Dùng `ContainerTestUtils.waitForAssignment(...)` để chờ trạng thái này:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.utils.ContainerTestUtils;

@Autowired
KafkaListenerEndpointRegistry registry;

@BeforeEach
void waitForListenerAssignment() {
    var container = registry.getListenerContainer("embedded-orders-listener");
    assertThat(container).isNotNull();
    ContainerTestUtils.waitForAssignment(container, 1);
}
```

Tham số `1` là tổng số partition mà listener dự kiến được gán trong ví dụ topic một partition. Nếu listener subscribe nhiều topic hoặc topic có nhiều partition, hãy tính tổng số partition mong đợi theo assignment của test.

Việc chờ assignment giúp giảm race condition: test không gửi record trước khi consumer sẵn sàng. Nó không thay thế timeout khi chờ listener xử lý record.

## 8. Gửi record bằng KafkaTemplate và xác minh kết quả

Test có thể inject `KafkaTemplate` giống ứng dụng production:

```java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.SendResult;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;

@Autowired
KafkaTemplate<String, String> kafkaTemplate;

@Autowired
BlockingQueue<ConsumerRecord<String, String>> receivedRecords;

@Test
void sendsRecordAndListenerReceivesIt() throws Exception {
    SendResult<String, String> result = kafkaTemplate
            .send("orders.created", "order-42", "created")
            .get(10, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic())
            .isEqualTo("orders.created");

    ConsumerRecord<String, String> received =
            receivedRecords.poll(10, TimeUnit.SECONDS);

    assertThat(received).isNotNull();
    assertThat(received.key()).isEqualTo("order-42");
    assertThat(received.value()).isEqualTo("created");
    assertThat(received.topic()).isEqualTo("orders.created");
}
```

`send(...).get(...)` chờ producer nhận kết quả gửi từ broker. Nó không chờ listener xử lý xong; vì vậy test tiếp tục lấy record từ queue với timeout riêng.

Nếu `send()` thất bại, `get()` sẽ ném exception (thường được bọc trong `ExecutionException`). Test nên để lỗi này làm test fail hoặc assert nguyên nhân cụ thể trong test failure scenario.

## 9. Kiểm tra Kafka headers

Embedded broker lưu headers cùng record, nên test có thể xác minh correlation ID hoặc metadata khác:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

@Test
void preservesCorrelationIdHeader() throws Exception {
    ProducerRecord<String, String> record = new ProducerRecord<>(
            "orders.created", "order-43", "created");

    record.headers().add(new RecordHeader(
            "correlation-id",
            "corr-test-43".getBytes(StandardCharsets.UTF_8)));

    kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);

    ConsumerRecord<String, String> received =
            receivedRecords.poll(10, TimeUnit.SECONDS);

    assertThat(received).isNotNull();
    var header = received.headers().lastHeader("correlation-id");
    assertThat(header).isNotNull();
    assertThat(new String(header.value(), StandardCharsets.UTF_8))
            .isEqualTo("corr-test-43");
}
```

Header value của Kafka là byte array. Test nên kiểm tra encoding giống cách producer/consumer thực tế sử dụng, không so sánh trực tiếp với `String`.

## 10. Kiểm tra partition và metadata

Với topic một partition, record thường được ghi vào partition `0`. Có thể kiểm tra metadata broker trả về:

```java
assertThat(result.getRecordMetadata().partition()).isEqualTo(0);
assertThat(result.getRecordMetadata().offset()).isGreaterThanOrEqualTo(0);
```

Nếu topic có nhiều partition, không hardcode partition khi producer dùng default partitioner và key. Thay vào đó, kiểm tra partition nằm trong miền hợp lệ hoặc kiểm tra các record có cùng key đi vào cùng partition khi test ordering theo key.

Muốn kiểm tra partition assignment của listener, dùng `ContainerTestUtils.waitForAssignment()` và kiểm tra record metadata được listener nhận. Số partition của topic, concurrency và số consumer trong group cùng quyết định mức song song.

## 11. Dùng KafkaTestUtils để tạo consumer test độc lập

Đôi khi cần kiểm tra record trong topic mà không thông qua `@KafkaListener`. `KafkaTestUtils` giúp tạo consumer properties cho embedded broker:

```java
import java.time.Duration;
import java.util.Map;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@Autowired
EmbeddedKafkaBroker embeddedKafkaBroker;

@Test
void readsRecordWithTestConsumer() {
    Map<String, Object> props = KafkaTestUtils.consumerProps(
            "orders-read-test", "false", embeddedKafkaBroker);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);

    try (Consumer<String, String> consumer = new KafkaConsumer<>(props)) {
        embeddedKafkaBroker.consumeFromAnEmbeddedTopic(
                consumer, "orders.created");

        kafkaTemplate.send("orders.created", "order-44", "paid");

        var records = KafkaTestUtils.getRecords(
                consumer, Duration.ofSeconds(10));

        assertThat(records.count()).isGreaterThan(0);
        assertThat(records.iterator().next().value()).isEqualTo("paid");
    }
}
```

Consumer test dùng group ID riêng và được đóng bằng try-with-resources. `consumeFromAnEmbeddedTopic()` thiết lập subscription/assignment cho topic embedded; `KafkaTestUtils.getRecords()` poll record với timeout. Nếu test cần xác minh một record cụ thể trong topic có dữ liệu cũ, hãy dùng topic riêng hoặc lọc theo key/value thay vì giả định record đầu tiên luôn là record vừa gửi.

## 12. Kiểm thử deserialization và message conversion

Nếu producer gửi JSON hoặc object, cấu hình embedded broker test phải dùng cùng serializer/deserializer hoặc converter như ứng dụng.

Các điểm nên kiểm tra:

- JSON field được serialize đúng tên và kiểu.
- Consumer deserialize thành đúng DTO/record.
- Header mapping không làm mất custom header.
- Null, optional field và timestamp có semantics nhất quán.
- Payload sai định dạng đi qua `ErrorHandlingDeserializer`/error handler theo chính sách.
- Type header hoặc trusted packages được cấu hình đúng nếu dùng JSON type mapping.

Một test producer và consumer cùng dùng `StringSerializer` chỉ chứng minh đường truyền string. Nếu production dùng Avro, Protobuf hoặc JSON serializer, cần integration test với serializer thực tế và fixture schema phù hợp.

## 13. Kiểm thử listener gọi application service

Nếu muốn kiểm tra listener thật của ứng dụng, có thể thay thế hoặc spy application service trong Spring test context rồi xác minh nó nhận event sau khi record đi qua broker.

Với Spring Boot phiên bản hỗ trợ `@MockitoBean`, có thể mock service:

```java
@MockitoBean
OrderProjectionService orderProjectionService;

@Test
void listenerDelegatesToApplicationService() throws Exception {
    kafkaTemplate.send("orders.created", "order-45", "created")
            .get(10, TimeUnit.SECONDS);

    await().atMost(10, TimeUnit.SECONDS).untilAsserted(() ->
            verify(orderProjectionService).process("order-45", "created"));
}
```

Đây là ví dụ với method service giả định `process(String key, String value)`. Nếu phiên bản Spring Boot cũ hơn chưa có `@MockitoBean`, dùng annotation mock bean được hỗ trợ bởi phiên bản đó. Dù mock service giúp xác minh listener invocation, vẫn cần các test khác kiểm tra business logic thật.

## 14. Kiểm thử nhiều partition và concurrency

Để kiểm tra listener concurrency, tạo topic có nhiều partition:

```java
@EmbeddedKafka(
        partitions = 3,
        topics = "orders.concurrent",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
```

Listener có thể cấu hình:

```java
@KafkaListener(
        id = "concurrent-orders-listener",
        topics = "orders.concurrent",
        groupId = "orders-concurrent-test",
        concurrency = "3")
public void listen(String payload) {
    // Xử lý record.
}
```

Với ba partition và concurrency ba, container có thể chạy tối đa ba consumer trong group, mỗi consumer được gán partition theo assignment. Không khẳng định mỗi thread sẽ luôn nhận đúng một partition theo thứ tự cố định; assignment phụ thuộc group coordinator và partition assignor.

Test nên xác minh tất cả record được xử lý, không giả định thứ tự tổng thể giữa nhiều partition. Ordering chỉ được bảo đảm trong cùng một partition.

## 15. Kiểm thử offset và consumer group

Embedded broker cho phép kiểm tra consumer group và committed offset bằng `AdminClient` hoặc consumer group test riêng.

Các tình huống hữu ích:

- Listener xử lý thành công và offset tiến theo AckMode.
- Listener ném exception và record được retry/redelivery.
- Manual acknowledgment chỉ commit sau khi gọi `acknowledge()`.
- Consumer restart và tiếp tục từ committed offset.
- Hai group ID khác nhau cùng đọc một topic độc lập.
- Hai consumer trong cùng group chia partition.

Không dùng cùng group ID giữa các test không liên quan. Offset đã commit từ lần chạy trước có thể khiến test mới không đọc lại record. Dùng group ID riêng, topic riêng hoặc reset dữ liệu theo chiến lược rõ ràng.

## 16. Kiểm thử retry và Dead Letter Topic

Có thể khai báo main topic và DLT ngay trên annotation:

```java
@RetryableTopic(
        attempts = "3",
        backoff = @Backoff(delay = 100),
        dltTopicSuffix = ".dlt")
@KafkaListener(topics = "orders.retry", groupId = "orders-retry-test")
public void listen(String payload) {
    orderService.process(payload);
}
```

Với Embedded Kafka, cần tạo trước các retry topic và DLT cần thiết hoặc cấu hình topic creation phù hợp với cách test. Gửi record làm listener thất bại, sau đó consume DLT và xác minh payload/header metadata.

Test cần chờ bất đồng bộ với timeout đủ cho retry delay và poll cycle. Không assert thời điểm retry chính xác tuyệt đối vì scheduling và broker polling có thể khiến xử lý muộn hơn thời gian backoff tối thiểu.

Non-blocking retry qua `@RetryableTopic` không kết hợp với container transaction và không hỗ trợ batch listener. Nếu ứng dụng dùng transactional listener, hãy kiểm thử retry/rollback qua `AfterRollbackProcessor` thay vì dùng cấu hình retry topic không tương thích.

## 17. Kiểm thử transaction với embedded broker

Nếu cần kiểm tra Kafka transaction, broker nhúng phải được cấu hình transaction state topic phù hợp. Với broker một node trong test:

```java
@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.input", "orders.output"},
        brokerProperties = {
                "transaction.state.log.replication.factor=1",
                "transaction.state.log.min.isr=1"
        },
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
```

Transactional producer cần `transactionIdPrefix` duy nhất. Consumer dùng `isolation.level=read_committed` để chỉ nhìn thấy output đã commit. Test nên bao gồm cả commit và abort, đồng thời kiểm tra offset input nếu dùng transactional listener.

Replication factor bằng 1 chỉ dành cho embedded broker một node; không phản ánh độ bền production. Nếu kiểm tra broker config, TLS/SASL hoặc nhiều broker, hãy cân nhắc Testcontainers hoặc cluster test phù hợp.

## 18. Cô lập test và tránh flaky

Các test Kafka có thể ảnh hưởng nhau qua topic, group ID, offset và dữ liệu còn lại. Áp dụng các nguyên tắc:

- Dùng topic riêng hoặc đảm bảo mỗi test có dữ liệu/key định danh riêng.
- Dùng consumer group ID riêng theo test class/run.
- Khai báo số partition xác định trong `@EmbeddedKafka`.
- Chờ listener assignment bằng `ContainerTestUtils.waitForAssignment()`.
- Dùng `BlockingQueue`, `CountDownLatch` hoặc Awaitility để chờ listener.
- Đặt timeout hữu hạn cho producer future và consumer poll.
- Không dựa vào `Thread.sleep()` cố định.
- Dọn queue/repository trước mỗi test.
- Đóng consumer tự tạo bằng try-with-resources.
- Không chạy song song các test chia sẻ cùng topic/group nếu chưa cô lập.

Nếu test chỉ fail trên CI, kiểm tra consumer assignment, rebalance log, timeout, topic/group reuse và tải CPU thay vì chỉ tăng timeout một cách tùy tiện.

## 19. Embedded Kafka và Testcontainers khác nhau thế nào?

| Tiêu chí | Embedded Kafka | Testcontainers Kafka |
| --- | --- | --- |
| Cách chạy | Broker nhúng trong tiến trình test | Broker chạy trong container |
| Docker | Không bắt buộc | Cần Docker runtime |
| Tốc độ | Thường nhanh cho integration test | Thường chậm hơn do khởi tạo container |
| Phiên bản broker | Theo dependency Spring Kafka test | Có thể chọn image/version cụ thể |
| Cấu hình production-like | Phù hợp các hành vi Kafka cơ bản | Linh hoạt hơn cho broker config, security và topology |
| Phù hợp | Producer/listener, headers, offset, retry cơ bản | Compatibility, TLS/SASL, broker image và cấu hình gần production |

Embedded Kafka không thay thế mọi kiểm thử hạ tầng. Ví dụ, một broker nhúng không thể chứng minh replication, leader failover hoặc hành vi khi mất một broker trong cluster nhiều node.

## 20. Troubleshooting khi test với Embedded Kafka

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Spring context kết nối sai broker | `bootstrapServersProperty` không trùng property Spring đang dùng | Đồng bộ property producer/consumer với embedded broker |
| Listener không nhận record | Container chưa assign partition hoặc topic/group sai | Chờ assignment, kiểm tra listener ID/topic/group |
| Producer future timeout | Broker chưa sẵn sàng hoặc test dùng sai bootstrap | Chờ broker khởi tạo, kiểm tra send exception và metadata |
| Test đọc record cũ | Topic/group được dùng lại | Dùng topic/group riêng hoặc lọc theo event ID |
| Test flaky do sleep | Listener chạy bất đồng bộ | Dùng queue/latch/Awaitility với timeout |
| `NoSuchBeanDefinition` cho KafkaTemplate | Context không auto-configure producer hoặc test config thiếu bean | Kiểm tra dependency và Spring Boot Kafka auto-configuration |
| Transaction test không chạy | Broker thiếu transaction state settings | Cấu hình replication factor/min ISR phù hợp |
| Nhiều listener cùng nhận/không nhận record mong đợi | Các listener chia cùng consumer group | Dùng group ID đúng mục tiêu test |
| Port/property xung đột giữa test context | Nhiều embedded broker hoặc system property dùng chung | Dùng bootstrap property riêng, cô lập context và lifecycle |

## 21. Checklist hoàn thành integration test

- [ ] Có dependency `spring-kafka-test` cùng phiên bản tương thích.
- [ ] `@EmbeddedKafka` khai báo topic và partition rõ ràng.
- [ ] Spring producer/consumer dùng bootstrap property của embedded broker.
- [ ] Consumer group ID riêng cho test.
- [ ] Listener container được chờ assignment trước khi gửi record.
- [ ] Producer future được chờ với timeout.
- [ ] Listener được đồng bộ bằng queue/latch/Awaitility.
- [ ] Assertion kiểm tra key, value, topic, partition và headers khi cần.
- [ ] Serializer/deserializer giống cấu hình ứng dụng cần xác minh.
- [ ] Retry/DLT/transaction có test riêng theo semantics thực tế.
- [ ] Test không phụ thuộc thứ tự chạy hoặc offset từ lần trước.
- [ ] Consumer và tài nguyên test được đóng/cleanup.
- [ ] Các yêu cầu production như replication, security và failover có test hạ tầng riêng.

## 22. Kết luận

`@EmbeddedKafka` và `spring-kafka-test` giúp thêm integration test có broker thực cho ứng dụng Spring Kafka mà không cần dựng cluster riêng. Hãy khai báo topic/partition trong annotation, trỏ Spring Boot tới bootstrap server của broker nhúng, chờ listener assignment rồi gửi record bằng `KafkaTemplate`. Dùng future để xác nhận producer send và `BlockingQueue`, latch hoặc Awaitility để chờ listener xử lý.

Kiểm tra cả payload và metadata như key, partition, offset, headers; dùng consumer group riêng để tránh ảnh hưởng giữa các test. Embedded Kafka phù hợp cho phần lớn kiểm thử producer/consumer/listener, retry và transaction cơ bản. Với yêu cầu nhiều broker, replication, security hoặc cấu hình production cụ thể, bổ sung test bằng Testcontainers hay môi trường tích hợp tương ứng. Nhờ đó, test suite kiểm tra được cả business behavior lẫn ranh giới messaging mà không trở nên phụ thuộc vào timing ngẫu nhiên.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Testing](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring for Apache Kafka — Embedded Kafka Broker](https://docs.spring.io/spring-kafka/reference/testing.html#embedded-kafka)
- [Spring for Apache Kafka — KafkaTestUtils API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [Spring for Apache Kafka — ContainerTestUtils API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/test/utils/ContainerTestUtils.html)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
