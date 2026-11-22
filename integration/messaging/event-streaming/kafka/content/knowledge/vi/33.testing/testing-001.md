# Phân chia unit test, integration test và kiểm thử đầu cuối

## Mục tiêu

Một ứng dụng Kafka có thể có business logic đúng nhưng vẫn lỗi khi serialize event, gửi sai topic, phân phối key không đúng partition, commit offset sai hoặc không gọi được database ở consumer. Vì vậy, kiểm thử Kafka cần nhiều lớp với phạm vi khác nhau.

- **Unit test** kiểm tra logic nhỏ trong bộ nhớ, không cần broker.
- **Integration test** kiểm tra các thành phần thực sự giao tiếp với Kafka broker và các adapter liên quan.
- **End-to-end test (E2E)** kiểm tra một luồng nghiệp vụ hoàn chỉnh qua producer, broker, consumer và các dependency mà người dùng cuối phụ thuộc.

Không có một loại test nào chứng minh được tất cả. Unit test nhanh nhưng không xác nhận protocol Kafka; integration test xác nhận tương tác broker nhưng không chứng minh toàn bộ hệ thống vận hành đúng; E2E xác nhận luồng thực tế nhưng chậm và khó chẩn đoán hơn. Một chiến lược tốt phân bổ test theo rủi ro và đặt mỗi assertion ở lớp có thể chứng minh nó đáng tin cậy nhất.

Sau bài học, bạn có thể:

- Phân biệt mục tiêu, phạm vi và giới hạn của unit, integration và E2E test.
- Tách business logic khỏi Kafka adapter để unit test dễ và ổn định.
- Dùng JUnit 5, Mockito và AssertJ cho unit test Java.
- Dùng Spring Kafka Embedded KRaft broker để kiểm tra producer/consumer integration.
- Dùng Testcontainers để kiểm thử với Kafka container gần môi trường triển khai.
- Kiểm tra serialization, partition key, headers, ordering, consumer group, retry và dead-letter topic.
- Dùng TopologyTestDriver để kiểm thử Kafka Streams topology mà không cần broker.
- Thiết kế E2E test cho luồng API → Kafka → consumer → database.
- Giảm flaky test bằng topic/group cô lập, polling có timeout và cleanup rõ ràng.
- Tổ chức test suite theo tốc độ phản hồi trong CI.

## 1. Vì sao cần chia nhiều lớp kiểm thử?

Giả sử API nhận yêu cầu tạo đơn hàng, producer publish OrderCreated vào Kafka, consumer nhận event rồi cập nhật inventory và lưu trạng thái đơn hàng.

Một unit test có thể chứng minh OrderValidator từ chối đơn hàng có tổng tiền âm. Nó không chứng minh producer dùng đúng topic hoặc broker nhận được record.

Một integration test có thể chứng minh KafkaTemplate gửi đúng key/value và consumer đọc được record từ broker. Nó không chứng minh toàn bộ endpoint REST, database và listener hoạt động cùng nhau.

Một E2E test có thể gửi HTTP request và chờ trạng thái đơn hàng xuất hiện trong read model. Nó kiểm tra luồng nghiệp vụ hoàn chỉnh, nhưng khi lỗi xảy ra cần nhiều log/trace hơn để xác định nguyên nhân.

### 1.1. Phạm vi của từng loại test

| Loại test | Phạm vi | Có Kafka broker? | Câu hỏi chính |
|---|---|---:|---|
| Unit | Một class/function hoặc một business rule | Không | Logic này có cho kết quả đúng với input đã cho không? |
| Component | Một component cùng dependency giả lập | Thường không | Component gọi đúng port/adapter và xử lý kết quả/lỗi đúng không? |
| Integration | Kafka client, serializer, listener, broker và config thực | Có | Các thành phần có giao tiếp đúng qua Kafka protocol không? |
| E2E | API, producer, broker, consumer, database và dependency liên quan | Có | Một hành trình nghiệp vụ có hoàn thành đúng không? |
| Contract | Event schema, key, headers và quy tắc tương thích | Tùy cách triển khai | Producer và consumer có cùng hiểu event contract không? |
| Performance/resilience | Throughput, latency, recovery, broker failure | Có, thường là cluster riêng | Hệ thống chịu được tải và lỗi mục tiêu không? |

Contract test và performance/resilience test bổ sung cho ba lớp chính. Chúng không phải tên khác của unit/integration/E2E: contract test tập trung vào thỏa thuận dữ liệu; performance/resilience test tập trung vào năng lực và hành vi khi có tải hoặc lỗi.

### 1.2. Test pyramid

~~~mermaid
flowchart TB
    E2E["E2E: ít test, chậm, bao phủ luồng nghiệp vụ"]
    INT["Integration: số lượng vừa, có Kafka thật"]
    UNIT["Unit: nhiều test, nhanh, cô lập"]
    UNIT --> INT --> E2E
~~~

Thông thường:

- Có nhiều unit test cho business rules, mapping và validation.
- Có đủ integration test cho producer, consumer, serializer, retry, offset và broker config.
- Có ít E2E test cho các hành trình quan trọng như tạo đơn, thanh toán và cập nhật tồn kho.
- Chạy performance, chaos và failover test theo lịch hoặc trước release lớn.

Đây là hướng phân bổ, không phải tỷ lệ cứng. Nếu hệ thống có logic đơn giản nhưng phụ thuộc Kafka phức tạp, số integration test có thể nhiều hơn bình thường.

## 2. Unit test — kiểm tra logic độc lập

### 2.1. Unit test nên kiểm tra điều gì?

Trong ứng dụng Kafka, các phần phù hợp với unit test gồm:

- Validate command/event trước khi publish.
- Tạo event từ domain object.
- Tính partition key hoặc routing key bằng hàm thuần.
- Mapping domain object sang event DTO.
- Chọn topic theo loại event.
- Xử lý business rule khi consumer nhận event.
- Tính retry delay hoặc phân loại exception retryable/non-retryable.
- Xây dựng idempotency key và kiểm tra duplicate ở business layer.
- Chuyển đổi schema version hoặc dữ liệu mặc định.

Các logic này nên được viết thành class/function không phụ thuộc Kafka broker. Nếu mọi rule đều nằm trong một method KafkaListener, việc kiểm thử sẽ buộc phải dựng Spring context và broker ngay cả khi chỉ cần xác nhận một phép tính.

### 2.2. Ví dụ unit test cho business rule

Giả sử ứng dụng chỉ publish đơn hàng hợp lệ:

~~~java
import java.math.BigDecimal;

public record CreateOrderCommand(
        String customerId,
        BigDecimal totalAmount) {
}

public class OrderValidator {

    public void validate(CreateOrderCommand command) {
        if (command == null) {
            throw new IllegalArgumentException("command is required");
        }
        if (command.customerId() == null || command.customerId().isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        if (command.totalAmount() == null
                || command.totalAmount().signum() <= 0) {
            throw new IllegalArgumentException("totalAmount must be positive");
        }
    }
}
~~~

Unit test dùng JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderValidatorTest {

    private final OrderValidator validator = new OrderValidator();

    @Test
    void acceptsValidOrder() {
        var command = new CreateOrderCommand(
                "customer-42",
                new BigDecimal("125.50"));

        assertDoesNotThrow(() -> validator.validate(command));
    }

    @Test
    void rejectsBlankCustomerId() {
        var command = new CreateOrderCommand(
                " ",
                new BigDecimal("125.50"));

        assertThrows(
                IllegalArgumentException.class,
                () -> validator.validate(command));
    }

    @Test
    void rejectsZeroAmount() {
        var command = new CreateOrderCommand(
                "customer-42",
                BigDecimal.ZERO);

        assertThrows(
                IllegalArgumentException.class,
                () -> validator.validate(command));
    }
}
~~~

Các test trên chạy trong JVM, không mở socket và không cần Kafka. Khi một test fail, nguyên nhân thường nằm trực tiếp trong business rule vừa kiểm tra.

### 2.3. Unit test cho consumer handler

Tách phần xử lý nghiệp vụ ra khỏi listener:

~~~java
public class OrderCreatedHandler {

    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    public OrderCreatedHandler(
            InventoryService inventoryService,
            OrderRepository orderRepository) {
        this.inventoryService = inventoryService;
        this.orderRepository = orderRepository;
    }

    public void handle(OrderCreated event) {
        inventoryService.reserve(event.orderId(), event.items());
        orderRepository.markAccepted(event.orderId());
    }
}
~~~

Unit test có thể mock hai port để xác nhận hành vi:

~~~java
import java.util.List;

import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderCreatedHandlerTest {

    @Mock
    InventoryService inventoryService;

    @Mock
    OrderRepository orderRepository;

    @InjectMocks
    OrderCreatedHandler handler;

    @Test
    void reservesInventoryAndMarksOrderAccepted() {
        var event = new OrderCreated(
                "order-42",
                List.of(new OrderItem("sku-1", 2)));

        handler.handle(event);

        verify(inventoryService).reserve(event.orderId(), event.items());
        verify(orderRepository).markAccepted(event.orderId());
    }
}
~~~

Test này chứng minh handler gọi đúng business ports. Nó không chứng minh database commit thành công, listener nhận được record hoặc offset chỉ được commit sau khi transaction hoàn tất. Những hành vi đó cần integration/E2E test.

### 2.4. Mock KafkaTemplate có ích đến đâu?

Có thể mock KafkaTemplate để unit test lớp điều phối publish:

- Event được tạo với đúng business data.
- Đúng topic và key được chọn.
- Header correlation/event ID được gắn.
- Kết quả lỗi từ port publish được chuyển thành trạng thái phù hợp.

Nhưng verify một lời gọi send với đúng tham số chỉ chứng minh code gọi method đó. Nó không chứng minh serializer hoạt động, broker chấp nhận record, partitioner chọn đúng partition hoặc consumer đọc được dữ liệu.

Giữ mock ở ranh giới của unit test. Khi mục tiêu là xác nhận Kafka integration, dùng broker thật trong test.

### 2.5. Unit test serializer và mapper

Serializer/mapper có thể test độc lập mà không cần broker:

- Null field được xử lý đúng.
- Timestamp và timezone được chuyển đổi đúng.
- Decimal không bị mất precision.
- Event version có giá trị mong đợi.
- Header names và encoding đúng.
- Unknown field hoặc schema evolution được xử lý theo contract.

Ví dụ với JSON serializer, serialize object rồi kiểm tra JSON output hoặc deserialize ngược lại. Test này kiểm tra serializer code, nhưng schema compatibility với Registry thật vẫn cần contract/integration test riêng.

### 2.6. Unit test Kafka Streams

Với Kafka Streams, dùng TopologyTestDriver để đưa record vào topology và đọc output/state store mà không cần Kafka broker. Đây là test rất phù hợp cho filter, map, join, aggregate, window và processor logic.
Thêm dependency org.apache.kafka:kafka-streams-test-utils với version trùng với kafka-streams của ứng dụng.

~~~java
import java.util.Properties;

import static org.assertj.core.api.Assertions.assertThat;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.TopologyTestDriver;
import org.junit.jupiter.api.Test;

class OrdersTopologyTest {

    @Test
    void forwardsOnlyValidOrders() {
        Properties props = new Properties();
        props.put(
                StreamsConfig.APPLICATION_ID_CONFIG,
                "orders-topology-test");
        props.put(
                StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
                "dummy:1234");
        props.put(
                StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
                Serdes.String().getClass());
        props.put(
                StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
                Serdes.String().getClass());

        StreamsBuilder builder = new StreamsBuilder();
        builder.<String, String>stream("orders.in")
                .filter((key, value) -> value.startsWith("VALID"))
                .to("orders.valid");

        try (TopologyTestDriver driver =
                     new TopologyTestDriver(builder.build(), props)) {

            var input = driver.createInputTopic(
                    "orders.in",
                    Serdes.String().serializer(),
                    Serdes.String().serializer());
            var output = driver.createOutputTopic(
                    "orders.valid",
                    Serdes.String().deserializer(),
                    Serdes.String().deserializer());

            input.pipeInput("order-1", "VALID:100");

            assertThat(output.readValue()).isEqualTo("VALID:100");
            assertThat(output.isEmpty()).isTrue();
        }
    }
}
~~~

TopologyTestDriver xử lý input đồng bộ và mô phỏng một partition cho mỗi input topic. Nó không thay thế integration test cho broker, consumer group coordination, partition assignment, changelog replication hoặc state restoration trong cluster thật. [Apache Kafka 4.4 — Testing a Streams Application](https://kafka.apache.org/44/streams/developer-guide/testing/).

## 3. Integration test — kiểm tra tương tác với Kafka thật

### 3.1. Khi nào cần integration test?

Integration test phù hợp khi cần xác nhận:

- Producer kết nối broker và publish thành công.
- Serializer/deserializer tương thích với payload thật.
- Key được ghi đúng và record tới đúng partition.
- Headers, timestamp và metadata được giữ đúng.
- Consumer subscribe, poll và deserialize record.
- Consumer group commit offset đúng chính sách.
- Ordering được giữ trong cùng partition.
- Retry, backoff và dead-letter topic hoạt động.
- Transactional producer và read_committed consumer có hành vi mong muốn.
- Topic config, ACL hoặc quota được áp dụng đúng trong môi trường test.

Điểm phân biệt quan trọng: integration test phải sử dụng Kafka broker thực. Mock KafkaTemplate, mock Consumer hoặc một in-memory fake không kiểm tra Kafka protocol và broker behavior.

### 3.2. Hai lựa chọn phổ biến

| Công cụ | Cách chạy | Phù hợp |
|---|---|---|
| Spring Kafka Embedded KRaft broker | Broker được khởi động trong JVM/test lifecycle | Integration test nhanh cho Spring Kafka producer/consumer |
| Testcontainers Kafka | Kafka chạy trong Docker container tạm thời | Test gần phiên bản/image và cấu hình triển khai hơn |

Embedded broker tiện cho test suite Spring. Từ Kafka 4.0, Spring Kafka chỉ còn EmbeddedKafkaKraftBroker; không còn lựa chọn embedded ZooKeeper broker. Testcontainers khởi động Kafka container và cấp bootstrap server động cho test.

Embedded broker và một Kafka container đơn node vẫn không chứng minh replication factor, broker failover hoặc controller quorum behavior. Muốn kiểm tra các tình huống đó, cần dựng cluster nhiều broker/controller phù hợp.

### 3.3. Dependency cho test

Nếu dùng Spring Boot, thêm test starter theo version mà Spring Boot quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dùng Spring Kafka mà không dùng Boot starter, dùng spring-kafka-test với version tương thích spring-kafka.

Đối với Testcontainers 2.x, có thể khai báo:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-kafka</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>
~~~

Nên dùng Testcontainers BOM để quản lý chung version các module. Chọn Kafka image tương thích với Kafka client và version production; không tự động dùng image mới nhất vì test có thể chạy trên broker khác version triển khai.

### 3.4. Integration test với @EmbeddedKafka

Ví dụ sau kiểm tra KafkaTemplate gửi record và Kafka consumer đọc được record từ embedded broker.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

@SpringBootTest(properties = {
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
        partitions = 3,
        topics = "orders.integration",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderProducerIntegrationTest {

    private static final String TOPIC = "orders.integration";

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Test
    void publishesRecordThatCanBeReadFromBroker() throws Exception {
        String groupId = "integration-" + UUID.randomUUID();
        Map<String, Object> props = KafkaTestUtils.consumerProps(
                groupId,
                "false",
                embeddedKafka);

        props.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");
        props.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);

        try (Consumer<String, String> consumer =
                     new KafkaConsumer<>(props)) {

            consumer.subscribe(List.of(TOPIC));

            long assignmentDeadline =
                    System.nanoTime() + Duration.ofSeconds(10).toNanos();
            while (consumer.assignment().isEmpty()
                    && System.nanoTime() < assignmentDeadline) {
                consumer.poll(Duration.ofMillis(100));
            }
            assertThat(consumer.assignment()).isNotEmpty();

            String payload = "{\"orderId\":\"order-42\"}";
            kafkaTemplate.send(TOPIC, "order-42", payload)
                    .get(10, TimeUnit.SECONDS);

            ConsumerRecord<String, String> received = null;
            long recordDeadline =
                    System.nanoTime() + Duration.ofSeconds(10).toNanos();

            while (received == null && System.nanoTime() < recordDeadline) {
                var records = consumer.poll(Duration.ofMillis(200));
                for (ConsumerRecord<String, String> record : records) {
                    if ("order-42".equals(record.key())) {
                        received = record;
                        break;
                    }
                }
            }

            assertThat(received).isNotNull();
            assertThat(received.value()).isEqualTo(payload);
            assertThat(received.partition()).isBetween(0, 2);
        }
    }
}
~~~

Các điểm quan trọng trong test:

- Embedded broker được Spring Kafka khởi động ở chế độ KRaft.
- Consumer group có ID duy nhất để không đọc nhầm offset từ test khác.
- auto.offset.reset=earliest bảo đảm consumer mới đọc được record đã tồn tại trước khi poll.
- Consumer poll trước khi producer gửi để hoàn tất partition assignment.
- Test chờ bằng deadline và poll ngắn, không dùng Thread.sleep() cố định.
- Producer chờ send future hoàn tất để biết broker đã trả kết quả.
- Consumer được đóng bằng try-with-resources.

Đây là test cho producer-to-broker-to-consumer. Nếu ứng dụng có KafkaListener, hãy thêm test khác để xác nhận listener thật gọi handler/repository đúng và offset chỉ tiến sau khi xử lý theo ack/error policy đã cấu hình.

### 3.5. Topic riêng và trạng thái cô lập

Một test suite có thể bị flaky nếu nhiều test dùng chung topic/group và cùng đọc/commit offset. Nên:

- Dùng topic riêng cho từng test class hoặc từng test case nếu cần state độc lập.
- Dùng group ID duy nhất.
- Không phụ thuộc thứ tự test chạy.
- Tạo topic với partition count rõ ràng.
- Không dùng auto-create topic làm điều kiện ngầm trong test quan trọng.
- Xác nhận test đã consume đúng record theo event ID/key thay vì chỉ kiểm tra có record bất kỳ.
- Xóa hoặc cô lập state phụ thuộc sau test.

Spring Kafka khuyến nghị dùng topic khác nhau cho các test khi có thể để tránh cross-talk. KafkaTestUtils.consumerProps() đặt auto.offset.reset=earliest để test thường nhận được record đã gửi trước lúc consumer bắt đầu; nếu đổi sang latest, cần hiểu rõ thời điểm subscription/assignment. [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html).

### 3.6. Integration test với Testcontainers

Testcontainers phù hợp khi muốn kiểm tra với Kafka image thực tế, client version gần production, listener/network config hoặc kết hợp Kafka với database container.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;

@Testcontainers
@SpringBootTest
class OrderKafkaContainerIntegrationTest {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer("apache/kafka:4.0.0");

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.kafka.bootstrap-servers",
                kafka::getBootstrapServers);
    }

    @Test
    void applicationContextConnectsToRealKafkaContainer() {
        // Exercise the application producer/consumer beans here.
    }
}
~~~

Ví dụ pin image apache/kafka:4.0.0 để minh họa; dự án thực tế nên thay bằng tag Kafka đã được kiểm thử và tương thích với client version. Không hard-code localhost:9092: Testcontainers có thể dùng mapped port động và getBootstrapServers() trả địa chỉ kết nối chính xác.

KafkaContainer mới nằm trong package org.testcontainers.kafka và hỗ trợ image apache/kafka hoặc apache/kafka-native. Class cũ org.testcontainers.containers.KafkaContainer đã deprecated trong Testcontainers hiện tại. Testcontainers cần Docker-compatible runtime ở máy developer/CI. [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/).

### 3.7. Kiểm thử serialization và event contract

Một integration test quan trọng là xác nhận record sau khi đi qua producer serializer và consumer deserializer vẫn giữ đúng contract:

- Key/value có đúng schema.
- Field bắt buộc không bị mất.
- Header như event-type, event-version, correlation-id tồn tại.
- Timestamp và event ID được giữ đúng.
- Consumer xử lý schema version cũ theo compatibility policy.
- Payload lỗi bị từ chối hoặc đưa vào DLT đúng cách.

Nếu dùng Schema Registry, cần kiểm tra schema registration/compatibility bằng môi trường registry dành cho test hoặc contract test riêng. Chỉ deserialize một JSON sample không chứng minh schema đã tương thích với tất cả consumer đang chạy.

### 3.8. Kiểm thử partition và ordering

Ordering của Kafka được bảo đảm trong phạm vi một partition. Vì vậy, integration test nên:

1. Gửi nhiều record có cùng key.
2. Đọc record từ broker.
3. Xác nhận chúng được ghi vào cùng partition.
4. Xác nhận thứ tự offset/sequence theo thứ tự publish đã cam kết.

Ví dụ assertion có thể kiểm tra key order-42 luôn về cùng partition và sequence 1, 2, 3 được đọc theo thứ tự. Không viết test yêu cầu ordering toàn cục giữa nhiều partition.

Nếu producer dùng retry, idempotence và max.in.flight.requests.per.connection, test cần dùng cấu hình production tương đương. Nếu key thay đổi, partitioner thay đổi hoặc tăng partition count, mapping key-to-partition có thể thay đổi; đó là thay đổi contract cần đánh giá.

### 3.9. Kiểm thử retry và dead-letter topic

Một integration test cho error handling nên mô phỏng:

- Lỗi tạm thời ở downstream, ví dụ timeout database.
- Lỗi không thể retry, ví dụ payload/schema không hợp lệ.
- Số lần retry và backoff.
- Sau khi hết retry, record được publish tới DLT.
- DLT giữ event ID, key, headers và thông tin exception cần thiết.
- Consumer không xử lý lặp vô hạn một poison record.
- Offset chỉ được commit theo đúng semantics đã chọn.

Không chỉ assert rằng listener method được gọi. Cần đọc DLT từ broker và xác nhận record thực tế đã được chuyển tới đúng topic. Đồng thời kiểm tra retry topic/DLT topic có partition, retention và ACL đúng.

### 3.10. Kiểm thử transaction và offset commit

Với Kafka transactions, integration test nên kiểm tra:

- Producer transaction commit thì record xuất hiện với isolation.level=read_committed.
- Producer transaction abort thì record không xuất hiện với read_committed consumer.
- Consumer xử lý và commit offset trong cùng Kafka transaction nếu dùng consume-transform-produce transactional flow.
- Restart/retry không tạo side effect ngoài mong đợi.

Một consumer mặc định read_uncommitted có thể nhìn thấy record thuộc transaction chưa commit hoặc đã abort trong log. Vì vậy, test phải đặt isolation level phù hợp với guarantee mà ứng dụng cần chứng minh.

### 3.11. Giới hạn của embedded broker và single container

Embedded broker thường là một broker đơn node, phù hợp để kiểm tra client protocol và luồng producer/consumer cơ bản. Một Kafka container đơn node cũng không kiểm tra được đầy đủ:

- Replication factor lớn hơn 1 và ISR.
- Leader election khi broker mất.
- Controller quorum/KRaft failover.
- Replica reassignment và recovery.
- Network partition giữa các broker.
- Broker rolling upgrade.

Những tình huống đó cần integration/system test với cluster nhiều broker/controller, cấu hình gần production và kịch bản fault injection có kiểm soát.

## 4. End-to-end test — kiểm tra hành trình nghiệp vụ

### 4.1. E2E test trả lời câu hỏi gì?

E2E test xác nhận một hành trình từ điểm vào bên ngoài tới kết quả nghiệp vụ cuối cùng. Ví dụ:

1. Client gửi HTTP request tạo đơn hàng.
2. API validate và ghi OrderCreated vào Kafka.
3. Consumer đọc event.
4. Consumer cập nhật inventory và order projection.
5. API/read model trả về trạng thái đơn hàng đã được xử lý.

Test không cần kiểm tra từng method nội bộ. Nó kiểm tra kết quả người dùng và các invariant nghiệp vụ phải đúng sau khi toàn bộ luồng hoàn tất.

### 4.2. Sơ đồ E2E

~~~mermaid
flowchart LR
    U[HTTP client / test] --> A[Order API]
    A --> P[Kafka producer]
    P --> K[(Kafka broker)]
    K --> C[Order consumer]
    C --> D[(Database / read model)]
    D --> V[Verify business result]
~~~

E2E test cần chạy các service thật trong test profile, kết nối tới Kafka và database test. Có thể dùng Testcontainers để dựng Kafka, PostgreSQL và các dependency khác theo đúng luồng cần kiểm tra.

### 4.3. Ví dụ E2E test với Spring Boot và Testcontainers

Ví dụ dưới đây giả định ứng dụng có REST endpoint tạo đơn và consumer cập nhật repository/read model sau khi nhận event:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.math.BigDecimal;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;

@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CreateOrderE2ETest {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer("apache/kafka:4.0.0");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.kafka.bootstrap-servers",
                kafka::getBootstrapServers);
    }

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderReadRepository orderReadRepository;

    @Test
    void createsOrderAndEventuallyUpdatesReadModel() {
        var request = new CreateOrderRequest(
                "customer-42",
                new BigDecimal("125.50"));

        var response = http.postForEntity(
                "/api/orders",
                request,
                CreateOrderResponse.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        assertThat(response.getBody()).isNotNull();

        String orderId = response.getBody().orderId();

        await()
                .atMost(Duration.ofSeconds(15))
                .untilAsserted(() ->
                        assertThat(orderReadRepository.findById(orderId))
                                .isPresent());
    }
}
~~~

Awaitility chờ trạng thái bất đồng bộ với timeout hữu hạn. Không giả định consumer hoàn tất đúng 500 ms sau HTTP response. E2E test nên kiểm tra thêm trạng thái cuối, ví dụ order status, inventory reservation và event ID, tùy invariant quan trọng của hệ thống.

Để test này thực sự là E2E, OrderReadRepository phải kết nối tới database test có hành vi phù hợp với môi trường mục tiêu. Nếu dùng H2 trong memory thay cho PostgreSQL production, test chỉ xác nhận luồng với một database thay thế; các khác biệt SQL, transaction isolation và locking vẫn cần database integration test riêng.

### 4.4. Phân biệt E2E với integration test

Một test dùng SpringBootTest không tự động là E2E. Phạm vi quyết định phân loại:

- Nếu test chỉ kiểm tra KafkaTemplate gửi và consumer nhận record qua broker, đó là integration test.
- Nếu test gọi endpoint, qua producer, broker, listener, database và kiểm tra kết quả nghiệp vụ cuối, đó là E2E test.
- Nếu test chỉ boot toàn bộ Spring context nhưng mock KafkaTemplate và repository, nó chủ yếu là component/context test.

Không dùng tên E2E chỉ vì test có annotation SpringBootTest.

### 4.5. Chọn ít E2E test nhưng có giá trị cao

Ưu tiên các luồng:

- Tạo event quan trọng và xác nhận consumer xử lý.
- Event thanh toán hoặc inventory có side effect không được thực hiện hai lần.
- Event lỗi được chuyển tới DLT và có thể replay.
- Consumer restart giữa chừng nhưng business state vẫn đúng.
- API báo trạng thái accepted trước khi event được xử lý, sau đó read model eventually consistent.

Không cần lặp lại mọi business validation ở E2E nếu unit test đã bao phủ đầy đủ. E2E nên kiểm tra hành trình và invariant xuyên qua boundary.

## 5. Chọn test cho từng hành vi Kafka

| Hành vi cần xác nhận | Unit test | Integration test | E2E test |
|---|---|---|---|
| Validate event fields | Chính | Không bắt buộc | Chỉ một vài luồng đại diện |
| Event mapping/headers | Chính | Xác nhận serializer output | Kiểm tra nếu ảnh hưởng business |
| Producer gửi đúng topic/key | Mock để kiểm tra routing logic | Chính, đọc record từ broker | Có thể xác nhận qua flow |
| Serialization/deserialization | Test serializer độc lập | Chính với broker/client thật | Bao phủ gián tiếp |
| Partition selection | Test partitioner logic nếu custom | Chính, kiểm tra metadata/partition | Ít khi cần |
| Ordering cùng key | Test logic sequence | Chính | Chỉ khi invariant nghiệp vụ quan trọng |
| Consumer handler | Chính, mock ports | Listener integration | Bao phủ toàn luồng |
| Offset commit/ack mode | Không đủ | Chính | Một vài recovery flow |
| Retry và DLT | Test exception classification | Chính, kiểm tra DLT record | Test luồng xử lý lỗi quan trọng |
| Kafka transaction | Test transaction decision logic | Chính, read_committed | Có thể test business atomicity |
| Kafka Streams topology | TopologyTestDriver | Broker integration cho runtime | Test output tới dependency cuối |
| Broker replication/failover | Không | Multi-broker system test | DR exercise riêng |
| API → Kafka → DB | Không | Có thể chia component tests | Chính |

## 6. Những lỗi thường làm test Kafka thiếu tin cậy

### 6.1. Dùng Thread.sleep() để chờ consumer

Thread.sleep(1000) chỉ trì hoãn test một giây, không chứng minh consumer đã nhận record. Máy CI chậm có thể cần lâu hơn; máy nhanh lại lãng phí thời gian.

Dùng polling có deadline:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(orderReadRepository.findById(orderId))
                        .isPresent());
~~~

Với native Kafka consumer, gọi poll(Duration) trong vòng lặp có deadline. Luôn có timeout để test fail rõ ràng thay vì treo vô hạn.

### 6.2. Dùng topic/group dùng chung

Nếu nhiều test ghi cùng topic và dùng cùng group ID, kết quả phụ thuộc test chạy trước/sau, committed offset cũ và record còn sót. Dùng topic/group cô lập hoặc reset state có kiểm soát.

### 6.3. Không hiểu auto.offset.reset

latest chỉ áp dụng khi group chưa có committed offset hợp lệ. Nếu test gửi record trước khi consumer group subscribe/assign partition, consumer mới có thể bỏ qua record đó. Với test cần đọc record đã gửi, dùng earliest và tạo group mới; hoặc subscribe/assign trước khi gửi record.

### 6.4. Kiểm tra quá ít

Assert rằng send() không ném exception chưa đủ. Hãy kiểm tra:

- Record thực sự có trên broker.
- Topic và partition đúng.
- Key/value/headers đúng.
- Consumer nhận được record.
- Business side effect hoàn tất.
- Offset/ack policy đúng khi handler lỗi.

### 6.5. Dùng mock để kiểm chứng protocol

Mock không thể xác nhận broker xử lý request, authentication, ACL, serializer framing, partition assignment hoặc transaction marker. Dùng broker thật cho các hành vi đó.

### 6.6. Chạy integration test song song trên shared state

Testcontainers JUnit Jupiter hỗ trợ container static dùng chung trong một test class và container instance khởi động lại cho từng method. Nhưng shared Kafka topic/group vẫn có thể gây xung đột. Nếu chạy parallel, cần namespace riêng cho topic/group và dữ liệu; nếu không thể cô lập an toàn, chạy tuần tự nhóm test dùng chung broker. [Testcontainers — JUnit 5 integration](https://java.testcontainers.org/test_framework_integration/junit_5/).

JUnit Jupiter extension của Testcontainers hiện được kiểm thử với test chạy tuần tự; chạy parallel chưa được hỗ trợ và có thể tạo tác dụng phụ. Nếu bật parallel execution, cần kiểm tra kỹ lifecycle container và state cô lập, hoặc quản lý container bằng lifecycle riêng thay vì dựa vào extension mặc định.

### 6.7. Không đóng resource

Consumer, producer, Admin client, Streams test driver và container cần được đóng theo lifecycle. Resource leak có thể khiến test suite treo, port bị giữ hoặc JVM không thoát.

### 6.8. Dựa vào auto-create topic

Auto-create topic có thể khiến test chạy được với partition count/default config khác production. Với test partitioning, replication hoặc retention, tạo topic rõ ràng bằng Admin API hoặc broker fixture và assert config mong muốn.

## 7. Thiết kế test cho các tình huống lỗi

Kafka là hệ thống phân tán, nên ngoài happy path cần kiểm tra failure semantics.

### 7.1. Producer

- Broker unavailable hoặc connection timeout.
- Serialization exception trước khi gửi.
- Request timeout và retry.
- Idempotence khi retry.
- Buffer đầy và backpressure.
- Authentication/authorization failure.
- Message quá kích thước cho phép.
- Callback/future báo lỗi và ứng dụng phản ứng đúng.

Unit test kiểm tra quyết định của ứng dụng khi send future thất bại. Integration test mới kiểm tra broker, timeout, ACL và serialization thật.

### 7.2. Consumer

- Record hợp lệ được xử lý.
- Payload lỗi được phân loại non-retryable.
- Downstream timeout được retry theo policy.
- Poison record đi vào DLT.
- Consumer restart sau khi xử lý nhưng trước commit.
- Commit sync/async theo cấu hình.
- Rebalance khi member rời group.
- Handler chạy quá max.poll.interval.ms.
- Duplicate event không tạo side effect hai lần.

### 7.3. Ordering và partition

- Các event cùng business key phải về cùng partition.
- Sequence number tăng đúng thứ tự trong partition.
- Không yêu cầu ordering toàn topic nếu có nhiều partition.
- Test hành vi khi tăng partition count nếu ứng dụng phụ thuộc key-to-partition mapping.
- Kiểm tra retry có làm đảo thứ tự hay không theo cấu hình producer và consumer.

### 7.4. Transaction và exactly-once

- Transaction commit/abort được quan sát bằng consumer read_committed.
- Consumer không nhìn thấy record thuộc transaction đã abort.
- Offset input và output transaction được commit theo đúng flow.
- Crash/restart không tạo business side effect sai.
- Test không nhầm Kafka EOS với exactly-once side effect trong database hoặc HTTP service; dependency ngoài Kafka cần transaction/idempotency strategy riêng.

### 7.5. Security

Integration/system test nên xác nhận:

- Producer có quyền WRITE đúng topic.
- Consumer có quyền READ đúng topic và group.
- Principal không có quyền bị từ chối.
- TLS/SASL config hoạt động với test broker phù hợp.
- Secret không bị in ra log khi test fail.

Một embedded broker không cấu hình authentication không thể chứng minh security config production đúng.

## 8. Tổ chức test suite trong CI

Một pipeline thực tế có thể chia:

| Giai đoạn | Test chạy | Mục tiêu |
|---|---|---|
| Mỗi commit/PR | Unit + static checks | Feedback nhanh |
| PR hoặc merge queue | Integration với Embedded KRaft broker | Kiểm tra producer/consumer cơ bản |
| Main branch | Testcontainers integration và contract tests | Xác nhận Kafka image/schema tương thích |
| Nightly | E2E, multi-service và consumer recovery tests | Kiểm tra luồng nghiệp vụ |
| Trước release | Performance, multi-broker failover, security và DR exercise | Xác nhận non-functional requirement |

Không cần mọi E2E hoặc cluster fault test chạy cho mỗi lần sửa một hàm validation. Nhưng thay đổi producer config, serializer, consumer ack/retry, topic partition hoặc schema cần chạy đúng nhóm integration/contract test liên quan.

### 8.1. Báo cáo test hữu ích

Mỗi test suite nên ghi:

- Test name và loại test.
- Kafka broker/image/client version.
- Topic, partition count và group ID.
- Producer/consumer config quan trọng.
- Event ID hoặc correlation ID dùng để trace.
- Thời gian chạy và timeout.
- Connector/container log khi fail.
- Assertion thất bại và record metadata nếu có.

Không ghi payload chứa dữ liệu nhạy cảm vào test log. Có thể log event ID, key đã mask, topic, partition và offset để điều tra.

## 9. Quy trình thiết kế test cho một feature Kafka

Khi thêm feature mới, thực hiện theo thứ tự:

1. Viết business rule và acceptance criteria.
2. Tách business logic khỏi Kafka adapter.
3. Viết unit test cho validation, mapping, handler và error classification.
4. Xác định Kafka contract: topic, key, schema, headers, partition và ordering.
5. Viết integration test với broker thật để xác nhận producer/consumer/serializer/offset behavior.
6. Nếu feature đi qua nhiều service/dependency, viết một E2E test cho happy path và một số failure path quan trọng.
7. Chạy test suite tương ứng trong CI.
8. Ghi lại version/config của broker và client để test có thể tái lập.

Không cố nhồi mọi assertion vào một E2E test. Khi E2E fail, unit/integration tests phải giúp khoanh vùng nhanh thành phần có lỗi.

## 10. Bài thực hành và tự kiểm tra

### Thực hành A — Unit test business logic

1. Tạo OrderValidator và OrderCreatedHandler.
2. Viết test cho input hợp lệ, field thiếu, amount bằng 0 và amount âm.
3. Mock repository/inventory service để kiểm tra handler gọi đúng business port.
4. Viết test cho retryable và non-retryable exception.
5. Chạy unit test mà không khởi động Kafka.

### Thực hành B — Integration test với Embedded KRaft broker

1. Thêm Spring Kafka test dependency.
2. Tạo test class với @EmbeddedKafka.
3. Tạo topic riêng có ba partition.
4. Gửi record bằng KafkaTemplate.
5. Đọc bằng Kafka consumer với group ID mới và auto.offset.reset=earliest.
6. Assert key, value, partition, headers và offset.
7. Tạo test cho hai record cùng key và xác nhận cùng partition, đúng sequence.

### Thực hành C — Integration test retry/DLT

1. Tạo listener gọi một service có thể phát sinh exception.
2. Với event ID cụ thể, cho service lỗi hai lần rồi thành công.
3. Assert số lần retry và side effect cuối cùng.
4. Với payload không hợp lệ, xác nhận không retry vô hạn.
5. Đọc DLT từ broker và kiểm tra key, value, event ID và exception header.
6. Restart consumer và kiểm tra offset/duplicate behavior.

### Thực hành D — E2E test với Testcontainers

1. Khởi động Kafka container bằng Testcontainers.
2. Cấp bootstrap server động qua DynamicPropertySource.
3. Khởi động Spring Boot application bằng SpringBootTest.
4. Gọi endpoint tạo đơn bằng HTTP client.
5. Chờ consumer cập nhật database/read model bằng polling có timeout.
6. Assert trạng thái cuối và event ID.
7. Dừng container sau test và xác nhận suite không phụ thuộc broker cài sẵn trên máy.

### Thực hành E — Phân loại test

Với mỗi assertion dưới đây, chọn lớp test phù hợp nhất và giải thích:

1. Amount âm bị từ chối.
2. Event mapper tạo đúng eventVersion.
3. Kafka broker nhận record vào đúng topic.
4. Consumer deserialize record JSON từ broker.
5. Record cùng key được ghi vào cùng partition.
6. Consumer retry ba lần rồi publish DLT.
7. HTTP request tạo đơn và cuối cùng inventory được reserve.
8. Kafka Streams topology tính đúng tổng theo key.
9. Cluster tiếp tục phục vụ khi một broker bị dừng.
10. Producer và consumer tương thích schema sau khi thêm field mới.

### Câu hỏi tự kiểm tra

1. Unit test khác integration test ở dependency nào?
2. Vì sao mock KafkaTemplate không chứng minh broker nhận được record?
3. Khi nào nên dùng EmbeddedKafka?
4. EmbeddedKafka từ Kafka 4.0 chạy ở mode nào?
5. Khi nào Testcontainers có lợi hơn embedded broker?
6. Vì sao phải dùng group ID riêng cho test?
7. auto.offset.reset=earliest có ý nghĩa gì khi group chưa có committed offset?
8. Vì sao nên poll với timeout thay cho Thread.sleep?
9. Test nào phù hợp để kiểm tra retry và DLT?
10. Vì sao single-broker test không chứng minh replication/failover?
11. E2E test cần kiểm tra kết quả nào ngoài việc HTTP request trả 202?
12. TopologyTestDriver kiểm tra được gì và không kiểm tra được gì?
13. Contract test khác E2E test ở mục tiêu nào?
14. Những test nào nên chạy mỗi PR và test nào phù hợp nightly?
15. Vì sao test Kafka cần kiểm tra duplicate và idempotency?

## Kết luận

Unit test xác nhận business logic nhanh và cô lập; integration test dùng Kafka broker thật để xác nhận serialization, publish/consume, partition, offset, retry và transaction; E2E test xác nhận hành trình nghiệp vụ hoàn chỉnh qua API, Kafka, consumer và dependency cuối. Với Kafka Streams, TopologyTestDriver cho phép kiểm tra topology mà không cần broker. Embedded KRaft broker phù hợp với integration test nhanh; Testcontainers phù hợp khi cần image/version và dependency gần production. Độ tin cậy của test phụ thuộc vào topic/group cô lập, timeout rõ ràng, resource cleanup và assertion đúng phạm vi. Hãy đặt mỗi kiểm tra ở lớp test nhỏ nhất có thể chứng minh hành vi đó, rồi bổ sung E2E và resilience tests cho các rủi ro xuyên hệ thống.

## Tài liệu tham khảo

- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Boot — Apache Kafka Support and Testing with Embedded Kafka](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
- [Testcontainers — JUnit 5 Integration](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Apache Kafka 4.4 — Testing a Streams Application](https://kafka.apache.org/44/streams/developer-guide/testing/)
- [Apache Kafka 4.4 — TopologyTestDriver Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TopologyTestDriver.html)
