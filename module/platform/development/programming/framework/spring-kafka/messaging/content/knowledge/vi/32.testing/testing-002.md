# spring-kafka-test và starter kiểm thử

Kiểm thử ứng dụng Spring Kafka cần xác nhận nhiều hơn việc một method được gọi. Một luồng messaging thực tế có producer gửi record, broker lưu record vào topic/partition, consumer nhận record, deserialize payload, gọi listener và commit offset. Bộ công cụ kiểm thử phù hợp giúp kiểm tra từng lớp của luồng này với chi phí và độ tin cậy khác nhau.

`spring-kafka-test` cung cấp embedded Kafka broker, tiện ích tạo producer/consumer test, helper đọc record, matcher và mock factory. Với Spring Boot, starter kiểm thử Kafka gom các dependency cần thiết để chạy các bài integration test. Kết hợp chúng với JUnit Jupiter, AssertJ và Mockito để kiểm tra cả logic nghiệp vụ lẫn hành vi giao tiếp với Kafka.

Bài học tập trung vào cách chọn dependency, khởi tạo embedded broker, dùng `KafkaTestUtils`, kiểm thử `KafkaTemplate` và `@KafkaListener`, phân biệt mock với broker thật và tổ chức test ổn định trong CI.

## 1. Các lớp kiểm thử trong ứng dụng Spring Kafka

Không phải test nào cũng cần khởi động Kafka broker. Hãy chọn phạm vi theo điều cần xác minh.

| Loại test | Thành phần được kiểm tra | Công cụ phù hợp |
|---|---|---|
| Unit test | Quy tắc nghiệp vụ, mapping, validation | JUnit Jupiter, Mockito, AssertJ |
| Producer unit test | Cách service gọi `KafkaTemplate` và chọn topic/key/header | Mockito hoặc `MockProducer` |
| Listener unit test | Logic xử lý event sau khi listener nhận payload | Gọi trực tiếp method, mock dependency |
| Kafka integration test | Serialize, publish, consume, partition, header, offset | `spring-kafka-test` và embedded broker |
| Spring context integration test | Auto-configuration, listener container, dependency injection | `@SpringBootTest` và `@EmbeddedKafka` |
| Contract/system test | Tương thích schema, ACL, TLS, cấu hình cluster và nhiều service | Kafka container/cluster test và môi trường tích hợp |

Ví dụ, nếu cần xác minh `OrderService` tính tổng tiền đúng, không cần broker. Nếu cần xác minh `KafkaTemplate` gửi đúng key và topic, có thể mock template. Nếu cần xác minh listener thực sự deserialize JSON và nhận header từ broker, nên dùng embedded Kafka hoặc broker chạy trong container.

Một test tốt có một mục tiêu rõ ràng: kiểm tra logic nghiệp vụ hay kiểm tra hành vi tích hợp Kafka. Tránh đưa broker vào mọi unit test vì thời gian khởi động và trạng thái dùng chung khiến test chậm, khó cô lập.

## 2. Chọn dependency kiểm thử

`spring-kafka-test` là artifact chứa các tiện ích test chuyên biệt của Spring Kafka. Nó không thay thế JUnit hay Spring Test.

### Spring Boot 4.x

Với Spring Boot 4, dùng starter Kafka test:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Starter này đưa các tiện ích kiểm thử Kafka vào test classpath và quản lý phiên bản theo dependency management của Spring Boot.

### Spring Boot 3.x và các phiên bản Boot cũ hơn

Dùng `spring-kafka-test` cùng starter test của Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dự án không dùng Spring Boot, khai báo JUnit Jupiter/Spring Test theo nhu cầu và thêm `spring-kafka-test` cùng phiên bản tương thích với `spring-kafka`.

Không tự chọn một phiên bản `spring-kafka-test` khác phiên bản Spring Kafka runtime. Hãy để Spring Boot dependency management quản lý hoặc khai báo BOM/phiên bản thống nhất.

### Gradle

Spring Boot 4.x:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-kafka-test")
}
```

Spring Boot 3.x:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
```

Sau khi khai báo dependency, IDE có thể import các API:

- `org.springframework.kafka.test.context.EmbeddedKafka`
- `org.springframework.kafka.test.EmbeddedKafkaBroker`
- `org.springframework.kafka.test.utils.KafkaTestUtils`
- `org.springframework.kafka.test.utils.ContainerTestUtils`
- `org.springframework.kafka.test.hamcrest.KafkaMatchers`
- `org.springframework.kafka.test.assertj.KafkaConditions`

Tên package và API cụ thể có thể thay đổi theo major version. Kiểm tra Javadoc của phiên bản thực tế trong dependency tree nếu IDE không resolve được import.

## 3. JUnit Jupiter và cấu trúc test

Spring Kafka hiện hỗ trợ JUnit Jupiter. Một test class cơ bản dùng `@Test`:

```java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderMapperTest {

    @Test
    void mapsOrderToEvent() {
        Order order = new Order("order-42", 125_000);

        OrderCreated event = OrderCreated.from(order);

        assertThat(event.orderId()).isEqualTo("order-42");
        assertThat(event.totalAmount()).isEqualTo(125_000);
    }
}
```

Unit test không cần `@SpringBootTest` nếu chỉ kiểm tra Java logic. Nếu cần inject Spring bean hoặc kiểm tra cấu hình, dùng Spring Test context.

Spring Kafka hiện không còn hỗ trợ JUnit 4; các ví dụ trong bài dùng JUnit Jupiter. Khi nâng cấp dự án cũ, hãy chuyển runner/rule sang extension và annotation tương ứng của JUnit 5.

Một số annotation thường gặp:

| Annotation | Mục đích |
|---|---|
| `@Test` | Đánh dấu test method |
| `@ExtendWith(MockitoExtension.class)` | Khởi tạo Mockito trong JUnit Jupiter |
| `@SpringBootTest` | Khởi động Spring Boot application context |
| `@EmbeddedKafka` | Tạo embedded Kafka broker cho test |
| `@DirtiesContext` | Đánh dấu context cần đóng/làm mới sau test |
| `@TestConfiguration` | Bổ sung bean chỉ dành cho test |
| `@DynamicPropertySource` | Đăng ký property động từ test fixture |

Không dùng `@SpringBootTest` theo thói quen cho tất cả test. Mỗi lần tạo context có thể tốn thời gian và mở listener container ngoài phạm vi test đang kiểm tra.

Với producer service, có thể dùng Mockito để xác minh lời gọi `KafkaTemplate` mà không cần broker:

```java
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.kafka.core.KafkaTemplate;

@ExtendWith(MockitoExtension.class)
class OrderPublisherTest {

    @Mock
    KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @InjectMocks
    OrderPublisher publisher;

    @Test
    void publishesOrderWithBusinessKey() {
        OrderCreated event = new OrderCreated("order-42");

        publisher.publish(event);

        verify(kafkaTemplate).send("orders", "order-42", event);
    }
}
```

Test này xác minh service chọn đúng topic và key. Nó không xác minh broker nhận record hay serializer hoạt động; các hành vi đó thuộc integration test.

## 4. Embedded Kafka là gì?

Embedded Kafka là broker Kafka chạy trong tiến trình test, do `spring-kafka-test` quản lý. Test có thể gửi và đọc record như khi kết nối broker thật.

Các lợi ích:

- Không cần một Kafka server riêng đang chạy trên máy developer.
- Có thể tạo topic và số partition theo test.
- Có thể kiểm tra serialize/deserialize qua Kafka protocol.
- Có thể kiểm tra `KafkaTemplate`, listener container, key, partition và header.
- Có thể chạy trong CI khi môi trường cho phép tiến trình broker cục bộ.

Từ Spring Kafka 3.1 có implementation KRaft `EmbeddedKafkaKraftBroker`. Spring Kafka 3.0/3.1 còn có implementation ZooKeeper legacy; với Kafka 4.0, ZooKeeper đã bị loại bỏ và chỉ còn KRaft.

Trong phần lớn test, dùng annotation `@EmbeddedKafka` để framework tạo broker và đăng ký bean `EmbeddedKafkaBroker`.

## 5. Khởi tạo embedded broker bằng @EmbeddedKafka

Ví dụ với Spring Boot:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Test
    void embeddedBrokerStarts() {
        assertThat(embeddedKafka.getBrokersAsString())
            .isNotBlank();
    }
}
```

`@EmbeddedKafka` tạo topic `orders` với một partition. `bootstrapServersProperty` cho broker ghi địa chỉ vào `spring.kafka.bootstrap-servers` để Spring Boot Kafka auto-configuration sử dụng.

Từ Spring Kafka 3.0.10, property này mặc định đã là `spring.kafka.bootstrap-servers` cho ứng dụng Spring Boot. Khai báo rõ trong ví dụ giúp người đọc thấy mối liên hệ giữa embedded broker và client properties.

Với test dùng Spring Test context, `EmbeddedKafkaBroker` có thể được inject như một bean. Nếu không dùng Spring context, JUnit Jupiter hỗ trợ parameter resolver:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

@EmbeddedKafka(topics = "orders")
class StandaloneEmbeddedKafkaTest {

    @Test
    void exposesBrokerAddress(EmbeddedKafkaBroker broker) {
        assertThat(broker.getBrokersAsString()).isNotBlank();
    }
}
```

Cách standalone hữu ích khi test chỉ cần broker và không cần khởi động Spring Boot context.

## 6. Cấu hình broker, topic và partition cho test

Có thể tạo nhiều topic và partition:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 3,
    topics = {
        "orders",
        "payments",
        "orders-dlt"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaFlowIntegrationTest {
    // Các test dùng broker và topic đã tạo.
}
```

Nếu cần broker property riêng, dùng `brokerProperties` hoặc `brokerPropertiesLocation`:

```java
@EmbeddedKafka(
    topics = "orders",
    brokerProperties = {
        "auto.create.topics.enable=false",
        "num.partitions=3"
    }
)
```

Các property phải là cấu hình broker Kafka hợp lệ. Không đặt nhầm client property như `group.id` vào `brokerProperties`.

Nếu muốn tạo topic có cấu hình riêng trong test, có thể dùng `EmbeddedKafkaBroker.addTopics(...)` với `NewTopic`:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

@Autowired
EmbeddedKafkaBroker broker;

@Test
void createsTopicWithSeveralPartitions() {
    broker.addTopics(
        new NewTopic("audit-events", 4, (short) 1)
    );
}
```

Với embedded broker một node, replication factor phải phù hợp với số broker đang chạy. Đừng yêu cầu replication factor lớn hơn số broker có sẵn.

Dùng topic riêng cho từng test hoặc từng test class nếu có thể. Điều này tránh record của test trước làm test sau đọc nhầm dữ liệu.

## 7. Dùng KafkaTestUtils để tạo consumer properties

`KafkaTestUtils` giúp tạo cấu hình consumer/producer phù hợp với embedded broker.

Trong Spring Kafka 4.0 trở lên, dùng overload mới:

```java
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

Map<String, Object> consumerProps =
    KafkaTestUtils.consumerProps(
        embeddedKafka,
        "orders-test-group",
        false
    );
```

Overload này nhận broker, group ID và boolean `autoCommit`. Nó cấu hình `bootstrap.servers`, deserializer mặc định và `auto.offset.reset=earliest`.

Với Spring Kafka 3.x, overload thường gặp là:

```java
Map<String, Object> consumerProps =
    KafkaTestUtils.consumerProps(
        "orders-test-group",
        "false",
        embeddedKafka
    );
```

Trong Spring Kafka 4.0, overload cũ nhận chuỗi boolean đã deprecated để loại bỏ. Khi nâng cấp major version, hãy chuyển sang overload dùng boolean và broker đứng đầu danh sách tham số.

Nếu cần kiểu key/value khác mặc định, ghi đè serializer/deserializer:

```java
consumerProps.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
consumerProps.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
```

`auto.offset.reset=earliest` hữu ích khi test gửi record trước khi consumer được tạo hoặc trước khi consumer subscribe. Nếu muốn test chỉ nhận record mới sau khi bắt đầu consume, hãy cấu hình `latest` và kiểm soát thời điểm subscribe/send rõ ràng.

## 8. Tạo producer và gửi record trong test

Tạo producer properties bằng `KafkaTestUtils.producerProps`:

```java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

Map<String, Object> producerProps =
    KafkaTestUtils.producerProps(embeddedKafka);

producerProps.put(
    ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class
);
producerProps.put(
    ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class
);
```

Tuy nhiên, nếu ứng dụng đã có `KafkaTemplate` được Spring Boot cấu hình, test có thể inject template và gửi record qua đó:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@Autowired
KafkaTemplate<String, String> kafkaTemplate;

@Test
void sendsRecord() throws Exception {
    kafkaTemplate.send(
        "orders",
        "order-42",
        "ORDER_CREATED"
    ).get(10, TimeUnit.SECONDS);
}
```

`KafkaTemplate.send` trả về `CompletableFuture<SendResult<K,V>>` ở các phiên bản Spring Kafka hiện đại. Dùng `get(timeout, unit)` trong test để chờ broker xác nhận và làm lỗi gửi được phát hiện ngay trong test.

Không nên chỉ gọi `send` rồi kết thúc test. Nếu test kết thúc trước khi future hoàn tất, lỗi serializer hoặc broker có thể xuất hiện muộn và không được test bắt đúng cách.

Khi cần xác minh metadata gửi, kiểm tra `SendResult`:

```java
SendResult<String, String> result =
    kafkaTemplate.send("orders", "order-42", "ORDER_CREATED")
        .get(10, TimeUnit.SECONDS);

assertThat(result.getRecordMetadata().topic()).isEqualTo("orders");
assertThat(result.getRecordMetadata().partition()).isGreaterThanOrEqualTo(0);
assertThat(result.getRecordMetadata().offset()).isGreaterThanOrEqualTo(0);
```

Nếu test cần partition cụ thể, dùng overload gửi có partition:

```java
kafkaTemplate.send(
    "orders",
    1,
    "order-42",
    "ORDER_CREATED"
).get(10, TimeUnit.SECONDS);
```

Topic phải có partition index tương ứng. Ví dụ `partition=1` yêu cầu topic có ít nhất hai partition.

## 9. Đọc record bằng KafkaTestUtils

Tạo consumer từ properties và subscribe vào topic:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

Map<String, Object> props =
    KafkaTestUtils.consumerProps(
        embeddedKafka,
        "orders-read-test",
        false
    );

props.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
props.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);

Consumer<String, String> consumer =
    new KafkaConsumer<>(props);

try {
    embeddedKafka.consumeFromAnEmbeddedTopic(
        consumer,
        "orders"
    );

    kafkaTemplate.send(
        "orders",
        "order-42",
        "ORDER_CREATED"
    ).get(10, TimeUnit.SECONDS);

    ConsumerRecord<String, String> record =
        KafkaTestUtils.getSingleRecord(
            consumer,
            "orders",
            Duration.ofSeconds(10)
        );

    assertThat(record.key()).isEqualTo("order-42");
    assertThat(record.value()).isEqualTo("ORDER_CREATED");
}
finally {
    consumer.close();
}
```

`consumeFromAnEmbeddedTopic` gán consumer vào topic do embedded broker tạo và mặc định seek về đầu partition. Vì vậy, dùng topic riêng cho test hoặc gọi overload có tham số `seekToEnd` khi cần bắt đầu từ record mới.

`getSingleRecord` đợi một record trong thời gian timeout. Nó sẽ báo lỗi nếu không nhận được record hoặc nhận nhiều hơn một record trong topic đó trong lần poll được kiểm tra.

Nếu test có thể nhận nhiều record, dùng `KafkaTestUtils.getRecords(consumer, timeout)` rồi kiểm tra `ConsumerRecords`:

```java
ConsumerRecords<String, String> records =
    KafkaTestUtils.getRecords(
        consumer,
        Duration.ofSeconds(10)
    );

assertThat(records.count()).isEqualTo(2);
assertThat(records.records("orders"))
    .extracting(ConsumerRecord::value)
    .containsExactlyInAnyOrder("ORDER_CREATED", "ORDER_CANCELLED");
```

Luôn đặt timeout hữu hạn. Test chờ vô hạn sẽ khiến CI bị treo khi broker hoặc listener gặp lỗi.

## 10. Kiểm thử listener bằng Spring Boot và Embedded Kafka

Để kiểm tra luồng end-to-end trong một application context, khởi động listener thật và gửi record vào broker.

Ví dụ listener:

```java
import java.util.concurrent.BlockingQueue;
import org.springframework.kafka.annotation.KafkaListener;

public class TestOrderListener {

    private final BlockingQueue<String> received;

    public TestOrderListener(BlockingQueue<String> received) {
        this.received = received;
    }

    @KafkaListener(
        id = "orders-test-listener",
        topics = "orders",
        groupId = "orders-integration-test"
    )
    public void onMessage(String payload) {
        this.received.add(payload);
    }
}
```

Test configuration và test class:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;

@SpringBootTest(properties = "spring.kafka.consumer.auto-offset-reset=earliest")
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderListenerIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    BlockingQueue<String> received;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Test
    void listenerReceivesPublishedMessage() throws Exception {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-test-listener");
        ContainerTestUtils.waitForAssignment(container, 1);

        kafkaTemplate.send(
            "orders",
            "order-42",
            "ORDER_CREATED"
        ).get(10, TimeUnit.SECONDS);

        String payload = received.poll(10, TimeUnit.SECONDS);

        assertThat(payload).isEqualTo("ORDER_CREATED");
    }

    @TestConfiguration
    static class TestBeans {

        @Bean
        BlockingQueue<String> receivedQueue() {
            return new LinkedBlockingQueue<>();
        }

        @Bean
        TestOrderListener testOrderListener(
                BlockingQueue<String> received) {
            return new TestOrderListener(received);
        }
    }
}
```

Queue giúp test đồng bộ với listener mà không cần `Thread.sleep`. Test gửi record, chờ tối đa 10 giây và kiểm tra payload listener nhận được.

Trong dự án thực tế, listener có thể là bean production được inject dependency thật hoặc mock downstream service. Hãy dùng một consumer group riêng cho test để không xung đột với listener khác trong cùng broker.

Nếu test class dùng `@SpringJUnitConfig`/Spring Test context cùng embedded broker, tài liệu Spring Kafka khuyến nghị cân nhắc `@DirtiesContext` để tránh race khi JVM shutdown và broker bị đóng trước khi context còn đang dùng nó. Với Spring Boot, áp dụng theo vòng đời context và cách suite tái sử dụng broker; không thêm annotation một cách máy móc vì nó khiến context khởi động lại sau mỗi test class.

## 11. Chờ listener assignment trước khi gửi record

Một lỗi phổ biến là gửi record ngay khi test bắt đầu, trong khi listener container chưa subscribe hoặc chưa được assign partition.

Khi test cần xác minh assignment, inject container qua registry và dùng `ContainerTestUtils.waitForAssignment`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.ContainerTestUtils;

@Autowired
KafkaListenerEndpointRegistry registry;

@Autowired
EmbeddedKafkaBroker embeddedKafka;

@Test
void waitsUntilListenerIsAssigned() {
    MessageListenerContainer container =
        registry.getListenerContainer("orders-test-listener");

    ContainerTestUtils.waitForAssignment(
        container,
        embeddedKafka.getPartitionsPerTopic()
    );

    assertThat(container.isRunning()).isTrue();
}
```

Tham số partition count phải phù hợp với assignment mà test mong đợi. Với concurrency nhiều consumer, không giả định mỗi child đều nhận partition; tổng số partition và consumer group quyết định phân phối.

Chờ assignment trước khi publish giúp giảm flaky test do timing, đặc biệt khi test kiểm tra partition cụ thể, rebalance, offset hoặc pause/resume.

## 12. Kiểm tra key, partition, header và timestamp

Một integration test nên kiểm tra metadata nếu logic ứng dụng phụ thuộc vào chúng.

Ví dụ:

```java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.core.KafkaTemplate;

ProducerRecord<String, String> record =
    new ProducerRecord<>(
        "orders",
        0,
        "order-42",
        "ORDER_CREATED"
    );

record.headers().add(
    "correlation-id",
    "corr-123".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);
```

Sau khi đọc record:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import org.apache.kafka.common.header.Header;

assertThat(received.key()).isEqualTo("order-42");
assertThat(received.partition()).isZero();

// Header correlation:

Header correlationHeader =
    received.headers().lastHeader("correlation-id");

assertThat(correlationHeader).isNotNull();
assertThat(new String(
    correlationHeader.value(),
    StandardCharsets.UTF_8
)).isEqualTo("corr-123");
```

Kiểm tra `partition` khi ứng dụng yêu cầu routing theo key hoặc partition. Nếu chỉ kiểm tra payload, lỗi chọn partition có thể bị bỏ sót.

## 13. Kiểm thử serialization và deserialization

`spring-kafka-test` kết hợp embedded broker giúp kiểm tra serializer/deserializer thực tế. Điều này đặc biệt quan trọng với JSON, Avro, Protobuf hoặc custom serializer.

Ví dụ test JSON:

1. Tạo `KafkaTemplate<String, OrderCreated>` dùng serializer của ứng dụng.
2. Gửi event vào topic.
3. Tạo consumer dùng deserializer tương ứng.
4. Đọc record và kiểm tra field, schema version và type.
5. Gửi payload không hợp lệ nếu muốn xác minh error path.

Không chỉ kiểm tra rằng JSON có thể parse. Hãy kiểm tra contract quan trọng: tên field, nullability, enum, timestamp, schema ID/header và compatibility với consumer.

Với `ErrorHandlingDeserializer`, có thể gửi bytes không hợp lệ và xác minh lỗi deserialize được đưa vào header để error handler xử lý. Listener có thể không được gọi trong trường hợp này; hãy quan sát error path hoặc DLT consumer.

## 14. Kiểm thử retry, error handler và DLT

Embedded Kafka có thể kiểm tra luồng lỗi:

- Listener ném exception ở lần xử lý đầu.
- Error handler thực hiện retry theo backoff.
- Listener thành công ở lần sau hoặc record được recover.
- Record thất bại cuối cùng được gửi tới DLT.
- DLT record có metadata gốc và exception header cần thiết.

Không dùng `Thread.sleep` để giả định retry đã xảy ra. Dùng `CountDownLatch`, `BlockingQueue`, Awaitility hoặc event/callback để chờ kết quả với timeout hữu hạn.

Test nên kiểm tra cả số lần gọi listener, kết quả recovery và nội dung DLT. Với retry có backoff, đặt thời gian chờ phù hợp với chính sách cấu hình nhưng tránh timeout quá rộng làm test suite chậm.

## 15. MockProducer và MockConsumer khi không cần broker

Kafka client cung cấp `MockProducer` và `MockConsumer`. Từ Spring Kafka 3.0.7, `MockProducerFactory` và `MockConsumerFactory` giúp dùng chúng trực tiếp với `KafkaTemplate` và listener container.

Dùng mock khi muốn kiểm tra logic gọi producer/consumer mà không cần broker:

- `MockProducer` cho phép kiểm tra record đã gửi.
- `MockConsumer` cho phép thêm record giả, điều khiển assignment và offset.
- `MockProducerFactory` tích hợp với `KafkaTemplate`.
- `MockConsumerFactory` tích hợp với listener container.

Ví dụ `MockProducerFactory`:

```java
import org.apache.kafka.clients.producer.MockProducer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.mock.MockProducerFactory;

@Bean
ProducerFactory<String, String> mockProducerFactory() {
    return new MockProducerFactory<>(
        () -> new MockProducer<>(
            true,
            new StringSerializer(),
            new StringSerializer()
        )
    );
}
```

Trong test, inject `MockProducer` hoặc factory để xác minh record gửi đi. Nếu producer chạy nhiều thread, factory cần trả về producer instance riêng phù hợp; không chia sẻ một mock producer không thread-safe cho các thread đồng thời.

Với transactional mock producer, phải gọi `initTransactions()` trước khi thực hiện transaction. Spring Kafka cung cấp constructor của `MockProducerFactory` hỗ trợ transactional producer và transactional ID.

Mock không mô phỏng đầy đủ broker protocol, serialization network, partition leadership, transaction coordinator hay rebalance. Khi cần kiểm tra các hành vi đó, dùng embedded broker hoặc broker container.

## 16. Phân biệt embedded Kafka và Testcontainers

Hai cách đều có thể kiểm tra integration nhưng mục tiêu khác nhau:

| Tiêu chí | Embedded Kafka | Testcontainers Kafka |
|---|---|---|
| Cách chạy | Broker nhúng trong tiến trình test | Kafka chạy trong container |
| Khởi động | Không cần Docker | Cần Docker hoặc container runtime |
| Tốc độ | Thường nhanh cho test component | Thường chậm hơn do khởi động container |
| Cấu hình cluster | Phù hợp test broker đơn giản | Linh hoạt hơn với image/version/config |
| Môi trường gần production | Phù hợp protocol cơ bản | Có thể chọn Kafka image và cấu hình sát môi trường |
| CI | Cần cho phép broker chạy trong JVM | Cần CI hỗ trợ container |
| Phù hợp | Test producer/listener, serialization, retry, DLT | Test compatibility theo version, security, cluster topology và môi trường gần production |

Embedded Kafka là lựa chọn tốt cho nhiều integration test trong module. Testcontainers hữu ích khi cần kiểm tra image Kafka cụ thể, nhiều broker, cấu hình security hoặc tương tác với các container khác.

Không cần chạy cả hai cho mọi test. Chọn công cụ dựa trên điều cần xác minh.

## 17. Quản lý vòng đời và chia sẻ embedded broker

Khởi động broker riêng cho từng test method thường làm suite chậm. Spring Test context cache và `@EmbeddedKafka` cho phép tái sử dụng broker trong phạm vi context.

Một số nguyên tắc:

- Ưu tiên một broker cho một nhóm integration test có cùng context.
- Dùng topic riêng hoặc đảm bảo consumer seek đúng vị trí.
- Dùng consumer group ID riêng để tránh commit offset ảnh hưởng test khác.
- Đóng consumer/producer tự tạo trong `try-with-resources` hoặc `@AfterEach`.
- Đóng container listener khi test tự tạo container thủ công.
- Tránh global embedded broker và per-class `@EmbeddedKafka` cùng một suite vì chúng dùng chung system properties và có thể gây xung đột.

Spring Kafka từ phiên bản 3.0 có `GlobalEmbeddedKafkaTestExecutionListener` cho JUnit Platform, mặc định tắt. Khi bật global broker, cấu hình topic, partition và broker properties qua JUnit Platform/system properties. Không kết hợp global broker với broker riêng từng test class trong cùng suite nếu chưa có thiết kế rõ ràng.

## 18. Tránh flaky test

Các nguyên nhân thường gặp:

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Consumer không nhận record đã gửi | Consumer bắt đầu sau khi record được publish nhưng offset reset là latest | Dùng earliest hoặc subscribe trước khi gửi |
| Test nhận record từ lần chạy trước | Dùng chung topic và group | Topic/group riêng hoặc seek rõ ràng |
| Test lúc pass lúc fail | Không chờ listener assignment | `ContainerTestUtils.waitForAssignment` |
| Test timeout | Không đặt timeout hợp lý hoặc broker chưa sẵn sàng | Chờ điều kiện cụ thể và log broker |
| Nhận nhiều record hơn dự kiến | Topic dùng chung giữa test | Cô lập topic hoặc lọc theo key/event ID |
| Context shutdown lỗi | Broker đóng trước context | Quản lý `@DirtiesContext` và lifecycle |
| Test chạy song song bị đụng topic | Nhiều test dùng cùng topic/group | Đặt tên topic/group unique hoặc giới hạn parallelism |
| Test treo CI | Dùng poll/await vô hạn | Dùng Duration/timeout hữu hạn |

Tránh dùng `Thread.sleep` làm cơ chế đồng bộ. Dùng `CountDownLatch`, queue, Awaitility hoặc polling có timeout để đợi điều kiện thật.

## 19. Tổ chức test trong dự án

Có thể chia test source thành các nhóm:

```text
src
└── test
    ├── java
    │   └── com/example/messaging
    │       ├── unit
    │       │   ├── OrderServiceTest.java
    │       │   └── OrderMapperTest.java
    │       ├── producer
    │       │   └── OrderPublisherTest.java
    │       ├── listener
    │       │   └── OrderListenerTest.java
    │       └── integration
    │           ├── OrderKafkaIntegrationTest.java
    │           ├── RetryAndDltIntegrationTest.java
    │           └── SerializationIntegrationTest.java
    └── resources
        └── application-test.yml
```

Tên package chỉ là gợi ý. Quan trọng là phân biệt unit test với integration test để developer có thể chạy nhóm nhanh khi sửa logic và chạy nhóm broker test khi sửa cấu hình Kafka.

Ví dụ profile test:

```yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Cấu hình trong `application-test.yml` phải phù hợp với test case. Không áp dụng một `AckMode` chung nếu có test cần xác minh commit semantics khác nhau.

## 20. Checklist trước khi hoàn thành test suite

- Có `spring-kafka-test` hoặc starter Kafka test phù hợp với Spring Boot version.
- Phiên bản Spring Kafka test tương thích runtime.
- Unit test không khởi động broker khi không cần.
- Embedded Kafka được cấu hình topic và partition rõ ràng.
- Boot test dùng đúng `spring.kafka.bootstrap-servers`.
- Consumer group và topic được cô lập giữa test.
- Consumer subscribe/assignment hoàn tất trước khi publish khi cần.
- `KafkaTestUtils` dùng timeout hữu hạn.
- Test kiểm tra key, partition, header và payload nếu chúng thuộc contract.
- Test serialization/deserialization với serializer thật.
- Retry/DLT được kiểm tra bằng tín hiệu đồng bộ thay vì sleep.
- Mock producer/consumer chỉ dùng cho hành vi không cần broker.
- Consumer, producer và listener container được đóng đúng lifecycle.
- Suite không trộn global embedded broker với per-class broker tùy tiện.
- CI chạy được broker embedded hoặc container theo chiến lược dự án.

## 21. Ghi nhớ

- `spring-kafka-test` bổ sung công cụ test chuyên biệt cho Spring Kafka.
- Spring Boot 4 có `spring-boot-starter-kafka-test`; các phiên bản Boot trước đó thường dùng `spring-kafka-test` cùng `spring-boot-starter-test`.
- `@EmbeddedKafka` tạo broker thật trong tiến trình test và có thể đăng ký địa chỉ cho `spring.kafka.bootstrap-servers`.
- Kafka 4.0 chỉ dùng embedded KRaft broker.
- `KafkaTestUtils` hỗ trợ tạo producer/consumer properties và đọc record.
- Trong Spring Kafka 4, ưu tiên overload `consumerProps(embeddedKafka, group, autoCommit)`.
- `ContainerTestUtils.waitForAssignment` giúp đồng bộ test với listener assignment.
- `MockProducerFactory` và `MockConsumerFactory` phù hợp test không cần broker; chúng không thay thế integration test.
- Dùng topic/group riêng, timeout hữu hạn và tín hiệu đồng bộ để tránh flaky test.
- Kiểm thử phải xác minh đúng lớp cần kiểm tra: logic nghiệp vụ, Spring context hay giao tiếp Kafka thực tế.

Khi kết hợp JUnit Jupiter, starter kiểm thử và `spring-kafka-test`, đội phát triển có thể kiểm tra luồng messaging từ producer tới listener với chi phí hợp lý. Unit test giữ feedback nhanh cho logic nghiệp vụ; embedded broker xác nhận hành vi Kafka thực tế; còn container test phù hợp với các tình huống cần môi trường gần production.

## Tài liệu tham khảo

- [Spring Kafka – Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Boot – Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Kafka – KafkaTestUtils API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [Spring Kafka – EmbeddedKafkaBroker API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/test/EmbeddedKafkaBroker.html)
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/)



