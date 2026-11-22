# Chờ listener sẵn sàng trước khi gửi dữ liệu trong Spring Boot Messaging

## 1. Bài toán: producer gửi thành công nhưng test không thấy message

Một integration test dùng Kafka, RabbitMQ, JMS hoặc message broker khác thường làm theo các bước: khởi động Spring Boot context, gửi message, rồi chờ listener xử lý. Những bước này **không đồng bộ** với nhau. Spring context đã load xong không có nghĩa consumer đã subscribe thành công; broker đã khởi động không có nghĩa topic/queue đã sẵn sàng; container đã chuyển sang trạng thái running cũng chưa nhất thiết có assignment hoặc consumer thực sự gắn với broker.

Ví dụ kiểm thử có thể không ổn định:

```java
// Phản ví dụ: không kiểm tra consumer đã được gán partition.
kafkaTemplate.send("orders.events", "order-123").get();
assertEquals("order-123", inbox.poll(1, TimeUnit.SECONDS));
```

Đoạn trên chỉ là **snippet**, không phải một lớp Java độc lập. Việc `send(...).get()` hoàn thành chỉ xác nhận Kafka producer nhận được kết quả gửi/ack tương ứng, **không chứng minh** Spring `@KafkaListener` đã sẵn sàng hoặc xử lý message.

Nếu consumer mới bắt đầu với `auto.offset.reset=latest`, một message được ghi **trước lúc consumer có assignment và xác định offset ban đầu** có thể bị bỏ qua trong test. Nếu consumer đã có committed offsets, hành vi lại phụ thuộc offsets đó. Dùng `Thread.sleep(3000)` sau khi startup có thể che race trên laptop nhưng vẫn flake trong CI chậm.

Bài thuộc nhóm **Messaging**, đề mục **“Chờ listener sẵn sàng trước khi gửi dữ liệu”**. Trọng tâm là **readiness gate trước khi publish**, không chỉ thêm timeout sau khi publish.

### Sau khi học, bạn sẽ biết

1. Phân biệt broker readiness, Spring context readiness, listener container startup, Kafka partition assignment và kết quả xử lý nghiệp vụ.
2. Dùng `KafkaListenerEndpointRegistry` tìm container theo `@KafkaListener(id=...)`.
3. Dùng `ContainerTestUtils.waitForAssignment(container, expectedPartitions)` từ `spring-kafka-test` trước khi gửi message.
4. Viết project Java 17+ / Spring Boot **3.3.5** / Spring Kafka 3.2.x với `@EmbeddedKafka`, producer và listener thật.
5. Gửi message bằng `KafkaTemplate` có xác nhận producer, rồi chờ bằng `BlockingQueue.poll(timeout)` có giới hạn thời gian.
6. Kiểm tra payload, key, partition, offset và thứ tự trong **một Kafka partition**.
7. Không phụ thuộc `Thread.sleep`, kết quả `KafkaTemplate.send`, `isRunning()` hoặc `ApplicationReadyEvent` làm tín hiệu duy nhất.
8. Xử lý topic có nhiều partitions, concurrency, rebalances, multi-consumer groups, missing topics, disabled auto-startup và context caching.
9. Nhận diện nguyên tắc tương tự cho RabbitMQ/JMS nhưng không dùng API Kafka trên các brokers khác.
10. Phân biệt listener nhận record với side effect đã commit hoặc xử lý business thành công.

**Phiên bản minh họa:** Java 17+, Spring Boot 3.3.5, Spring Kafka 3.2.x theo Spring Boot dependency management. Các chi tiết API có thể khác trong Boot 4 hoặc Spring Kafka 4; không giả định bản minh họa là phiên bản mới nhất.

## 2. Năm tầng “sẵn sàng” không giống nhau

```text
JUnit/Spring TestContext
  |
  | (1) ApplicationContext đã refresh
  v
Kafka listener container được tạo
  |
  | (2) Container isRunning() = true
  v
Kafka consumer thread đang khởi động / poll
  |
  | (3) Broker, topic và group coordinator có thể truy cập
  v
Consumer được gán topic-partition(s)
  |
  | (4) ContainerTestUtils.waitForAssignment(...) thành công
  v
Test producer gửi message tới Kafka
  |
  | (5) Kafka ACK producer, rồi listener thực sự nhận/xử lý
  v
Assert hành vi nghiệp vụ hoặc message nhận được
```

| Mốc | Câu hỏi trả lời được | Điều **chưa** bảo đảm |
| --- | --- | --- |
| `@SpringBootTest` context được tạo | Spring beans/config được tạo | Consumer có assignment |
| Kafka broker running | Kafka có tiến trình/endpoint | Topic đã tồn tại, group đã join |
| `container.isRunning()` | Listener container đang trong lifecycle running | Kafka consumer đã được gán partition |
| Consumer started event | Consumer thread chuẩn bị poll | Đã có assignment cụ thể |
| `waitForAssignment(container, 1)` | Container có đủ số partition được gán mà test chờ | Message đã được xử lý hoặc commit nghiệp vụ |
| `KafkaTemplate.send(...).get(...)` | Producer đã nhận kết quả gửi theo Kafka ack policy | Listener đã xử lý record |
| Listener nhận record | Consumer code đã nhận payload | DB commit, external API side effect, downstream message thành công |
| Assert business state | Hành vi ứng dụng mong đợi đã xuất hiện | Mọi future processing/retry đều xong |

Trong ví dụ một topic có **một partition** và listener group có **một consumer**, điều kiện sẵn sàng thực tế là container đã được gán đúng **một topic-partition**. Với nhiều partition hoặc nhiều consumer trong cùng group, số partition cần đợi phải dựa trên topology, không hardcode bừa là 1.

## 3. Vì sao Thread.sleep không phải readiness gate?

```java
Thread.sleep(2000);
kafkaTemplate.send(TOPIC, "order-1");
```

Đây là **phản ví dụ**. Hai giây có thể đủ trên máy developer nhưng không đủ trong CI khi Kafka đang khởi tạo leader, broker metadata chậm hoặc consumer group rebalance. Nếu tăng lên 30 giây, test chậm khi hệ thống vốn đã sẵn sàng sau 200 ms mà vẫn không chứng minh được điều kiện cần.

**Readiness gate** có logic đúng hơn:

- Chờ một **điều kiện có nghĩa nghiệp vụ/hạ tầng**: consumer được assign partition, queue có active consumer, subscription active.
- Có **giới hạn thời gian** và thông báo lỗi khi điều kiện không đạt.
- Nếu điều kiện đã đạt thì tiếp tục ngay.
- Kiểm chứng riêng kết quả xử lý message bằng timeout phù hợp.

Trong Spring Kafka, `ContainerTestUtils.waitForAssignment` thực hiện phần chờ assignment với timeout/exception nội bộ. Sau khi gửi, `BlockingQueue.poll(Duration)` hoặc Awaitility giúp test chờ kết quả có giới hạn. Đừng trộn hai thao tác: readiness **trước publish**, outcome **sau publish**.

## 4. KafkaListenerEndpointRegistry và ID của listener

Spring Kafka đăng ký các listener containers tạo bởi `@KafkaListener` vào một `KafkaListenerEndpointRegistry`. Những containers tạo bởi annotation **không nhất thiết là ordinary beans** có thể autowire trực tiếp theo tên; registry là điểm quản lý đúng.

```java
@Autowired
KafkaListenerEndpointRegistry registry;

MessageListenerContainer container =
        registry.getListenerContainer("orders-ready-listener");
```

Trong listener:

```java
@KafkaListener(
    id = "orders-ready-listener",
    topics = "learning.ready.orders.v1",
    groupId = "orders-ready-group")
public void receive(String payload) {
    // Xử lý message thật.
}
```

Hai đoạn trên là snippet và sẽ được hiện thực đầy đủ trong project bên dưới. `id` là định danh container để registry tìm được; `groupId` định danh Kafka consumer group. **Không đánh đồng listener ID với group ID**: chúng có thể trùng khi dùng default behavior của framework, nhưng bài minh họa đặt riêng để tránh nhầm.

### Không chỉ assert isRunning()

```java
assertTrue(container.isRunning());
```

Assertion này hữu ích nhưng yếu: container có thể vừa khởi chạy thread consumer và đang chờ metadata/group assignment. Kafka listener có thể chưa có partition dù `isRunning()` true.

Kiểm tra đáng tin hơn cho đúng topology:

```java
assertTrue(container.isRunning());
ContainerTestUtils.waitForAssignment(container, 1);
```

`ContainerTestUtils` thuộc `org.springframework.kafka.test.utils.ContainerTestUtils`. Nó chờ container có đủ **số partitions đã được gán**; method ném exception khi không thể hoàn thành theo thiết kế của version, thay vì ngủ một khoảng tùy ý rồi hy vọng.

**Giới hạn:** assignment cho biết consumer group đã được bố trí với Kafka partitions, không bảo đảm handler không có bug, database reachable hoặc side effects sẽ commit. Vì vậy vẫn cần test xử lý message sau khi publish.

## 5. Khi nào Kafka message có thể bị “mất” trong test?

Kafka là append-only log, nên trong nhiều trường hợp message vẫn ở broker. “Mất” ở đây thường có nghĩa **test listener không đọc được** do offset/group, hoặc message đến một consumer khác.

Ví dụ chuỗi race:

```text
T0: Spring context bắt đầu tạo listener container
T1: Producer gửi "order-123"
T2: Broker đã ghi message (producer future SUCCESS)
T3: Consumer group hoàn tất assignment
T4: Consumer với auto.offset.reset=latest chọn cuối log
T5: Test chờ message và timeout
```

Đây là một scenario khả dĩ, không khẳng định Kafka luôn bỏ qua message khi gửi sớm: nếu consumer đã có committed offset hoặc reset policy là earliest, record có thể vẫn được đọc. Chính tính phụ thuộc vào offset/timing khiến test không đáng tin.

### earliest có thay waitForAssignment được không?

Không. `spring.kafka.consumer.auto-offset-reset=earliest` có ích khi group mới **không có committed offsets**, nhưng:

- Nó không buộc listener đã hoàn tất startup.
- Nó không làm một consumer đã commit offset quay lại đầu log.
- Nó không ngăn consumer khác cùng group lấy partition.
- Nó có thể khiến tests đọc lại messages cũ nếu broker/group tái sử dụng.
- Nó không thay cho việc assert handler đã xử lý đúng.

Trong project mẫu, ta kết hợp `earliest` để test dễ đoán trong embedded broker mới **và** một readiness gate tường minh để test không dựa vào offset reset nhằm che startup race.

## 6. Project Java 17+ / Spring Boot 3.3.5

Dự án chính dùng **embedded Kafka broker** từ `spring-kafka-test`, không cần Docker hay Kafka server được cài sẵn trên máy. Nó dùng một topic, một partition, một listener và một producer.

```text
kafka-listener-ready/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/messaging/
│   ├── MessagingApplication.java
│   ├── KafkaTopics.java
│   └── OrderEventListener.java
├── src/test/java/com/example/messaging/
│   └── OrderListenerReadyTest.java
└── src/test/resources/
    └── application-test.yml
```

### 6.1. settings.gradle

```groovy
rootProject.name = 'kafka-listener-ready'
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

**Giải thích dependencies:**

- `spring-boot-starter`: Spring Boot application core, không cần web server.
- `spring-kafka`: `KafkaTemplate`, `@KafkaListener`, Kafka listener containers.
- `spring-boot-starter-test`: JUnit Jupiter, Spring Boot test context, assertion support.
- `spring-kafka-test`: `@EmbeddedKafka`, `EmbeddedKafkaBroker`, `ContainerTestUtils`, test utilities.
- `junit-platform-launcher`: hỗ trợ môi trường Gradle chạy JUnit Platform.

Các phiên bản Spring Kafka/Kafka clients được Spring Boot BOM quản lý. Không tùy ý ghép Spring Kafka 4.x vào Boot 3.3.5 hoặc dùng import Kafka test khác version vì có thể sinh lỗi API/binary compatibility.

Bản demo **không** có `org.testcontainers:kafka` hoặc Docker; phần Testcontainers ở mục 16 chỉ là một phương án mở rộng.

### 6.3. MessagingApplication.java

`src/main/java/com/example/messaging/MessagingApplication.java`:

```java
package com.example.messaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafka;

@SpringBootApplication
@EnableKafka
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
```

`@EnableKafka` khai báo rõ mục đích bật Kafka listener annotation support. Spring Boot cũng có auto-configuration Kafka và mặc định cung cấp `kafkaListenerContainerFactory` khi điều kiện phù hợp; trong project này không cần tự viết factory để thử một listener String đơn giản.

Ứng dụng production cần `spring.kafka.bootstrap-servers` thật từ configuration. **Trong test**, `@EmbeddedKafka` tự đưa endpoint broker thử nghiệm vào property đó, không hardcode `localhost:9092`.

### 6.4. KafkaTopics.java

`src/main/java/com/example/messaging/KafkaTopics.java`:

```java
package com.example.messaging;

public final class KafkaTopics {

    public static final String ORDERS =
            "learning.ready.orders.v1";

    private KafkaTopics() {
    }
}
```

Constant tránh lệch tên topic giữa listener, test annotation và producer. Topic ở ví dụ được tạo với **một partition**, nên điều kiện `waitForAssignment(container, 1)` là phù hợp. Trong hệ thống thật, số partitions có thể được quản lý bởi Kafka Admin/migrations thay vì hardcode trong code.

## 7. Listener thực và hàng đợi quan sát cho bài học

`src/main/java/com/example/messaging/OrderEventListener.java`:

```java
package com.example.messaging;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final BlockingQueue<ConsumerRecord<String, String>>
            observed = new LinkedBlockingQueue<>();

    @KafkaListener(
            id = "orders-ready-listener",
            topics = KafkaTopics.ORDERS,
            groupId = "orders-ready-group",
            concurrency = "1")
    public void receive(ConsumerRecord<String, String> record) {
        observed.offer(record);
    }

    public ConsumerRecord<String, String> awaitRecord(
            Duration timeout) throws InterruptedException {
        return observed.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public void clearObserved() {
        observed.clear();
    }
}
```

**Vì sao dùng `BlockingQueue`?** `@KafkaListener` được gọi bất đồng bộ trên consumer thread, còn JUnit test chạy trên test thread. `LinkedBlockingQueue` cung cấp truyền dữ liệu thread-safe và `poll(timeout)` để test chờ một khoảng **có giới hạn**, không cần busy loop hoặc `Thread.sleep`.

**Lưu ý kiến trúc:** Queue `observed` trong listener chỉ là **instrumentation của bài học** để thấy record Kafka thật; nó không có persistent business value và không phải mẫu cho production event store. Trong ứng dụng thực, listener thường gọi một service/repository, rồi integration test assert database/state hoặc mock collaborator **phía sau listener** (không mock chính listener).

### Vì sao nhận ConsumerRecord thay vì chỉ String?

`ConsumerRecord<String,String>` cho phép kiểm tra:

- `record.topic()`: message đi từ đúng topic.
- `record.key()`: producer key được truyền đúng.
- `record.value()`: payload String được deserialize đúng.
- `record.partition()`: partition được phân phối.
- `record.offset()`: log offset tương ứng.

Với một partition, hai records được producer gửi tuần tự vào cùng topic/partition sẽ được Kafka phân phối cho consumer theo thứ tự log. Nếu topic có nhiều partitions, **không** khẳng định global ordering giữa chúng.

### Vì sao không dùng CountDownLatch đơn giản cho mọi test?

`CountDownLatch` có thể phù hợp khi chỉ cần đếm N callbacks, nhưng latch một lần đạt zero **không reset**. Nếu bean listener được cache qua nhiều test methods, một latch cũ có thể khiến test sau PASS ngay dù chưa có message mới. Có thể tạo latch mới per test với thread-safe coordination, nhưng `BlockingQueue` trong ví dụ giúp kiểm tra chính **payload**/metadata và lấy từng record dễ hơn.

`clearObserved()` chỉ dùng để đặt lại instrumentation giữa tests. Trong production, không nên để một test method xóa internal state của service đang phục vụ người dùng.

## 8. Cấu hình Kafka producer/consumer riêng cho test

`src/test/resources/application-test.yml`:

```yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
```

`@ActiveProfiles("test")` sẽ tải file này. Nó dùng serializers/deserializers `String` ở cả hai phía để KafkaTemplate và `ConsumerRecord<String,String>` thống nhất. Không cần `JsonDeserializer`, trusted packages hoặc custom message converter cho ví dụ String.

**Không đưa `spring.kafka.bootstrap-servers=localhost:9092` vào file test.** Broker embedded có thể chọn một host port động; annotation `@EmbeddedKafka(bootstrapServersProperty="spring.kafka.bootstrap-servers")` sẽ cung cấp địa chỉ chính xác.

`earliest` ở đây giúp test broker mới dễ hiểu hơn nhưng **không thay readiness wait**. Nếu broker đã có dữ liệu cũ và group chưa có offset, earliest có thể đọc lại quá nhiều records. Project dùng embedded broker mới và một topic riêng cho lớp test; không dựa vào dữ liệu Kafka dùng chung.

## 9. @EmbeddedKafka khởi tạo broker thử nghiệm

Trước khi viết full test, cần hiểu annotation:

```java
@EmbeddedKafka(
        partitions = 1,
        topics = KafkaTopics.ORDERS,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers",
        kraft = true)
```

`@EmbeddedKafka` đến từ `org.springframework.kafka.test.context.EmbeddedKafka`, có trong `spring-kafka-test`. Nó tạo một broker dành cho test, với topic được nêu rõ, đồng thời công bố địa chỉ vào property Boot dùng.

**KRaft:** Spring Kafka 3.2.x hỗ trợ lựa chọn embedded Kafka KRaft bằng `kraft=true`. Nó tránh phụ thuộc ZooKeeper của embedded broker cũ. Không copy option này sang các phiên bản Spring Kafka quá cũ chưa có attribute tương ứng.

**Không phải Docker:** embedded Kafka là broker thử nghiệm do Spring Kafka test infrastructure quản lý trong JVM/test runtime. Nó vẫn có startup và consumer group assignment **bất đồng bộ**; không phải mock `KafkaTemplate`. Vì vậy test vẫn cần chờ assignment.

### Khi nào broker được tạo?

Với `@SpringBootTest` và `@EmbeddedKafka`, broker được đăng ký trong Spring TestContext và bootstrap addresses được công bố cho Spring Boot Kafka auto-configuration. Topic tạo trước khi listener bắt đầu subscribe theo lifecycle phù hợp. Nếu topic chưa tồn tại hoặc không có leader, container có thể chạy nhưng không được assignment; timeout sẽ giúp lộ lỗi thay vì test im lặng.

### Tại sao dùng @DirtiesContext?

Embedded Kafka broker và Spring ApplicationContext có thể có lifecycle/cache tương tác. `@DirtiesContext(classMode=AFTER_CLASS)` giúp context được đóng sau lớp test, hạn chế việc cache consumer client trỏ đến broker đã dừng khi test class khác chạy. Điều này có chi phí context startup, nên dùng có chủ đích; không đặt bừa lên mọi unit test.

## 10. Bộ test runnable: chờ assignment trước khi gửi

Tạo `src/test/java/com/example/messaging/OrderListenerReadyTest.java`:

```java
package com.example.messaging;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@EmbeddedKafka(
        partitions = 1,
        topics = KafkaTopics.ORDERS,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers",
        kraft = true)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderListenerReadyTest {

    @Autowired
    KafkaTemplate<String, String> producer;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    OrderEventListener listener;

    private MessageListenerContainer container;

    @BeforeEach
    void waitUntilListenerOwnsPartition() {
        container = registry.getListenerContainer(
                "orders-ready-listener");

        assertNotNull(
                container, "listener id must be registered");
        assertTrue(
                container.isRunning(),
                "listener container should auto-start");

        // One topic, one partition and one consumer in this test.
        ContainerTestUtils.waitForAssignment(container, 1);

        // Clear only test instrumentation, after readiness.
        listener.clearObserved();
    }

    @Test
    void listenerIsAssignedBeforeAnyPublication() {
        assertTrue(container.isRunning());

        var partitions = container.getAssignedPartitions();
        assertNotNull(partitions);
        assertEquals(1, partitions.size());
        assertEquals(
                new TopicPartition(KafkaTopics.ORDERS, 0),
                partitions.iterator().next());
    }

    @Test
    void messageSentAfterAssignmentIsConsumed()
            throws Exception {
        String marker =
                "order-one-" + UUID.randomUUID();

        SendResult<String, String> result = producer.send(
                KafkaTopics.ORDERS, "order-key-1", marker)
                .get(10, TimeUnit.SECONDS);

        assertEquals(
                KafkaTopics.ORDERS,
                result.getRecordMetadata().topic());

        ConsumerRecord<String, String> received =
                listener.awaitRecord(Duration.ofSeconds(10));

        assertNotNull(
                received, "listener did not receive message");
        assertEquals(KafkaTopics.ORDERS, received.topic());
        assertEquals("order-key-1", received.key());
        assertEquals(marker, received.value());
        assertEquals(0, received.partition());
    }

    @Test
    void twoMessagesOnOnePartitionPreserveOrder()
            throws Exception {
        String marker = UUID.randomUUID().toString();

        producer.send(
                KafkaTopics.ORDERS, "shared-key", marker + "-A")
                .get(10, TimeUnit.SECONDS);

        producer.send(
                KafkaTopics.ORDERS, "shared-key", marker + "-B")
                .get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> first =
                listener.awaitRecord(Duration.ofSeconds(10));
        ConsumerRecord<String, String> second =
                listener.awaitRecord(Duration.ofSeconds(10));

        assertNotNull(first);
        assertNotNull(second);
        assertEquals(marker + "-A", first.value());
        assertEquals(marker + "-B", second.value());
        assertEquals(0, first.partition());
        assertEquals(0, second.partition());
        assertTrue(second.offset() > first.offset());
    }

    @Test
    void utf8PayloadIsDecodedAfterReadiness()
            throws Exception {
        String payload =
                "đơn-hàng-đã-sẵn-sàng-"
                        + UUID.randomUUID();

        producer.send(
                KafkaTopics.ORDERS, "unicode-key", payload)
                .get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> received =
                listener.awaitRecord(Duration.ofSeconds(10));

        assertNotNull(received);
        assertEquals(payload, received.value());
    }
}
```

**Có 4 phương thức `@Test` trong project mẫu**, mỗi phương thức đều chạy `@BeforeEach` để xác nhận readiness trước khi gửi dữ liệu. Không có assertion nào phụ thuộc vào việc test method khác phải chạy trước. Payload dùng UUID giúp phân biệt messages giữa các trường hợp.

### Đọc từng giai đoạn

**Giai đoạn 1 — tìm listener**

`registry.getListenerContainer("orders-ready-listener")` cần trùng chính xác giá trị `id` trên `@KafkaListener`. Nếu bean chưa được scan hoặc listener ID sai, kết quả có thể null; test fail ngay bằng thông báo rõ.

**Giai đoạn 2 — kiểm tra lifecycle**

`container.isRunning()` xác nhận auto-startup đã được kích hoạt. Đây là điều kiện sơ bộ, không phải readiness hoàn chỉnh.

**Giai đoạn 3 — chờ partition assignment**

`ContainerTestUtils.waitForAssignment(container, 1)` đợi consumer group sở hữu topic partition. Nếu container không thể join group hoặc topic không tồn tại, test có thể nhận exception thay vì chờ vô hạn.

**Giai đoạn 4 — chỉ sau đó publish**

`producer.send(...).get(10, TimeUnit.SECONDS)` giới hạn thời gian chờ producer ack. Nó không đồng nghĩa listener đã xử lý, nên test còn phải chờ record trong queue.

**Giai đoạn 5 — kiểm tra listener callback**

`listener.awaitRecord(Duration.ofSeconds(10))` chờ xử lý thật, rồi assert topic, key, value, partition hoặc offset. Nếu không có record, `assertNotNull` fail; test không dùng `Thread.sleep` để đoán tốc độ.

### Vì sao tách hai timeout?

- Producer `get(10, TimeUnit.SECONDS)`: giới hạn gửi/ack broker.
- Consumer `poll(10 s)`: giới hạn nhận event từ listener.

Nếu producer fail, phải điều tra broker/topic/network/serializer; nếu producer ACK nhưng queue trống, phải điều tra group assignment, listener invocation, deserializer hoặc handler failures. Hai timeout giúp chẩn đoán chính xác hơn một `Thread.sleep(20s)`.

## 11. Cách chạy và kết quả mong đợi

Với Gradle Wrapper có trong project:

```bash
./gradlew test --tests 'com.example.messaging.OrderListenerReadyTest'
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu thư mục chưa có Gradle Wrapper nhưng đã cài Gradle tương thích:

```bash
gradle test
```

Lớp test được thiết kế có **4 `@Test` methods**. `spring-kafka-test` cần khởi động embedded Kafka nên chạy có thể lâu hơn test Mockito thuần. Môi trường local/CI cần đủ CPU, bộ nhớ và khả năng tạo file/socket tạm phù hợp.

**Không có execution report được thu thập trong bài này.** “4 methods” là số từ source, **không phải tuyên bố 4 PASS đã chạy**. Sau khi chạy thực tế, xem:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

### Output đáng tin

Không có stdout nghiệp vụ cố định: log Kafka/Spring/Gradle phụ thuộc version và môi trường. Nếu tất cả assertions đúng, Gradle test task kết thúc thành công; nếu không, test report sẽ cho thấy lỗi ở startup, assignment, producer send hoặc listener receive. Không hardcode một dòng log `Assigned partitions: [topic-0]` rồi coi đó là output duy nhất.

## 12. Vì sao không chỉ chờ ApplicationReadyEvent?

`ApplicationReadyEvent` nghĩa là Spring Boot đã hoàn tất startup sequence theo cách của Spring, nhưng Kafka group join/partition rebalance có thể vẫn chạy bất đồng bộ. Một handler:

```java
@EventListener(ApplicationReadyEvent.class)
public void publishWarmup() {
    kafkaTemplate.send("learning.ready.orders.v1", "hello");
}
```

là **snippet phản ví dụ kiến trúc**, thiếu class và injection. Nó không tự chứng minh `@KafkaListener` đã nhận được assignment. Nếu business startup thật bắt buộc publish sau khi listeners ready, hãy dùng một **coordinator** theo readiness cần thiết hoặc chủ động chờ assignment. Nhưng không copy trực tiếp test-only `ContainerTestUtils` vào production chỉ vì nó tiện.

### Production readiness khác test readiness

Trong production, việc startup phụ thuộc broker, topic creation, group membership, rebalance và network. Readiness check có thể:

- Xác nhận broker connectivity và topic metadata.
- Kiểm tra listener container state/partition assignment.
- Phân biệt listener đang paused hoặc stopped.
- Chỉ báo readiness cho orchestration (Kubernetes readiness probe) dựa vào điều kiện phù hợp.
- Xử lý timeout/error khi broker tạm thời không sẵn, chứ không chặn vô hạn bootstrap thread.

`ContainerTestUtils` là tiện ích **test scope** (dependency `spring-kafka-test`). Đối với production, có thể dùng registry và trạng thái/metrics/health checks phù hợp, không phụ thuộc test artifact ở runtime.

## 13. ConsumerStartedEvent không đồng nghĩa đã được assignment

Spring Kafka có application events liên quan listener lifecycle:

- `ConsumerStartingEvent`: consumer thread vừa khởi tạo, trước khi poll.
- `ConsumerStartedEvent`: consumer sắp bắt đầu poll.
- `ConsumerFailedToStartEvent`: không khởi động consumer đúng trong ngưỡng cấu hình.
- `ListenerContainerIdleEvent`: không nhận message trong một khoảng idle được cấu hình.
- `NonResponsiveConsumerEvent`: poll quá lâu/consumer không phản hồi theo cơ chế giám sát.

Những events giúp quan sát startup/debug, nhưng **không tự xác nhận Kafka partition assignment**. Một consumer có thể started trong khi group rebalance đang diễn ra. Nếu cần bằng chứng partition được gán trong runtime, xem consumer rebalance callbacks, container assignment state hoặc metrics phù hợp.

**Không lấy một log “consumer started” rồi ngay lập tức publish** nếu yêu cầu test là bảo đảm listener đã sở hữu partition. Trong một embedded Kafka test, `waitForAssignment` là tín hiệu sát mục tiêu hơn.

## 14. Tại sao producer ACK không chứng minh consumer đã xử lý?

Kafka producer có thể được broker ACK trong khi consumer chưa poll tới record:

```text
Producer -> Broker append record -> ACK producer
                                  |
                                  v
                           Kafka partition log
                                  |
                       ... consumer poll sau ...
                                  |
                                  v
                         @KafkaListener callback
                                  |
                                  v
                         Database / business side effect
```

`KafkaTemplate.send(...).get(...)` hoàn thành chỉ nói về giai đoạn producer/broker với cấu hình acks tương ứng. Nó không đợi listener, transaction của listener, database commit, consumer offset commit hoặc downstream service.

Để kiểm tra end-to-end business:

1. **Trước khi gửi:** chờ listener đủ assignment.
2. **Sau khi gửi:** chờ business side effect có thể quan sát, ví dụ database row, trạng thái đơn hàng hoặc message đầu ra.
3. Dùng một timeout giới hạn, không polling vô hạn.
4. Nếu handler tự retry hoặc dùng async executor, chờ đến điều kiện business thật, không chỉ callback bắt đầu.
5. Với DB transaction, đừng assert một row chưa commit từ test thread khác rồi tưởng handler fail.

Queue `observed` trong project xác nhận callback nhận record, **không xác nhận business transaction commit**. Trong hệ thống thực, hãy thay/instrument thêm bằng repository assertion hoặc state/event mà người dùng cuối cần.

## 15. Nhiều partitions và concurrency

Project mẫu có đúng một partition, nên:

```java
ContainerTestUtils.waitForAssignment(container, 1);
```

phù hợp. Nhưng với topic ba partitions và listener concurrency hai consumers trong **một consumer group**, assignments có thể được chia giữa hai child containers. Parent `ConcurrentMessageListenerContainer` thường tổng hợp partitions của các children.

Ví dụ khái niệm:

```text
Topic: orders.events = partitions [0, 1, 2]
Group: orders-group
Listener parent container concurrency=2

Child consumer A -> partitions [0, 2]
Child consumer B -> partition  [1]

Parent assignment total = 3
```

Nếu mục tiêu là **cả ba partitions thuộc chính listener container này**, số `expectedPartitions` là 3. Nhưng nếu cùng group còn một app/test consumer khác, partitions có thể được gán cho consumer **khác**, và chờ cả ba trong một container sẽ không bao giờ đạt.

### Quy tắc chọn expectedPartitions

- Xác định topic(s) và số partitions thật.
- Xác định listener concurrency.
- Xác định **tất cả consumers đang tham gia cùng group**.
- Nếu test kiểm soát broker, topic và group duy nhất, có thể kỳ vọng listener nhận toàn bộ partitions.
- Nếu một group có nhiều instances, không mặc định một instance sở hữu tất cả partitions.
- Một listener có nhiều topics/pattern subscription có topology khác; không hardcode 1 nếu cần bảo vệ toàn bộ assignments.
- Trong case đặc thù, đợi partition cụ thể qua metadata/assignment state, không suy từ `isRunning()`.

**Kafka chỉ bảo đảm thứ tự trong một partition**, không có global ordering giữa nhiều partitions. Test thứ tự trong project đặt tất cả records vào topic có **một partition**, nên assert offset tăng là hợp lệ. Nếu có ba partitions, cần dùng key/explicit partition phù hợp và assert theo từng partition.

## 16. Alternative: Testcontainers Kafka broker thật trong Docker

`@EmbeddedKafka` phù hợp test nhanh trong JVM, còn Testcontainers hữu ích khi muốn kiểm tra gần với Kafka broker image cụ thể, Docker networking hoặc version compatibility.

Cách tiếp cận:

- Thêm `spring-boot-testcontainers`, `testcontainers:junit-jupiter` và Testcontainers Kafka module phù hợp với BOM.
- Khởi động Kafka container `@Container` có lifecycle rõ ràng.
- Với Spring Boot có `@ServiceConnection` hỗ trợ Kafka container tương ứng, để Boot tạo `KafkaConnectionDetails` và cấu hình bootstrap servers. Nếu không được hỗ trợ, dùng `@DynamicPropertySource` với `kafka.getBootstrapServers()`.
- Đăng ký hoặc tạo topic bằng `KafkaAdmin`/`NewTopic` trước khi chờ assignment.
- **Vẫn** lấy `KafkaListenerEndpointRegistry` và gọi `ContainerTestUtils.waitForAssignment` trước khi gửi data.
- Sau gửi, chờ listener xử lý bằng bounded assertion.
- Không kết nối nhầm localhost Kafka hoặc broker của người khác.

Ví dụ snippet **không phải project runnable độc lập** vì chưa có Testcontainers dependencies/lifecycle:

```java
@DynamicPropertySource
static void kafkaProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers);
}
```

Biến `kafka` ở đây là một Kafka container được tạo và quản lý đúng trong class test của phương án Testcontainers. Điểm đáng nhớ: **broker readiness là điều kiện cần, assignment vẫn là điều kiện riêng**. Một container Kafka `isRunning()` không có nghĩa consumer group đã join.

Nếu dùng `@ServiceConnection` cho broker, không cần đăng ký bootstrap servers cùng lúc qua DynamicPropertySource trừ khi có lý do rõ; dùng một nguồn connection details chính để tránh hiểu nhầm precedence.

## 17. Alternative: RabbitMQ listener sẵn sàng

Với Spring AMQP/RabbitMQ, khái niệm tương tự nhưng API khác Kafka:

- Broker đã mở cổng AMQP chưa đủ để có queue/binding.
- `@RabbitListener` container có thể đang chạy nhưng chưa attach consumer tới queue do channel/connection/backoff.
- Queue declaration, exchange/binding và consumer startup có thể bất đồng bộ.
- Publisher confirm chỉ xác nhận một tầng publisher/broker, không chứng minh listener đã ack/xử lý message.
- Dùng `RabbitListenerEndpointRegistry` lấy listener container theo ID, kiểm tra lifecycle và **active consumer/readiness signal phù hợp với container type**.
- Với `SimpleMessageListenerContainer`, số active consumers là thông tin hữu ích; với `DirectMessageListenerContainer`, cách quản lý consumers/queues khác, nên không cast mù một type sang type kia.
- Đợi kết quả xử lý bằng Awaitility, latch hoặc queue có timeout; không dùng `Thread.sleep`.
- Nếu test dùng RabbitMQContainer, hãy chờ broker/container health/queue binding và active consumer, rồi mới publish.

Snippet minh họa registry (không phải source runnable độc lập):

```java
RabbitListenerEndpointRegistry registry = ...;
MessageListenerContainer container =
        registry.getListenerContainer("invoice-listener");

// isRunning() chỉ là lifecycle signal;
// phải kiểm tra active consumers/queue bindings riêng.
```

Các types `RabbitListenerEndpointRegistry` và `MessageListenerContainer` ở snippet thuộc Spring AMQP, **không** phải Kafka classes. Chỉ dẫn này là nguyên tắc đối chiếu, không tuyên bố Kafka `ContainerTestUtils.waitForAssignment` dùng được với RabbitMQ.

## 18. Alternative: JMS, Redis Streams và message subscriptions

**JMS:** listener container phải được start, JMS connection/session/subscription được tạo và broker đủ sẵn sàng. `DefaultMessageListenerContainer.isRunning()` là bước đầu; durable subscriptions hoặc destination creation có thể cần xác minh riêng. Gửi message trước khi consumer subscribe có semantics khác nhau giữa queue và topic, nhất là non-durable topics.

**Redis Streams consumer groups:** cần stream tồn tại, group được tạo ở offset phù hợp và consumer active/read path hoạt động. Đừng nhầm XADD thành XREADGROUP đã consume. Chọn offset `0`, `$` hoặc group-delivered pending semantics theo contract.

**Pub/sub thuần:** nếu subscriber chưa subscribe mà publisher phát message, có thể **thực sự mất** message do không có durable log/queue, khác Kafka. Chờ subscription ack/readiness trước publish là điều kiện quan trọng hơn nữa.

**Message broker được mock:** một test chỉ dùng mocked producer không kiểm tra readiness của listener. Chỉ khi thực sự có broker/consumer chạy mới phát hiện được startup races.

## 19. Khi listener bị autoStartup=false

Một số ứng dụng tắt auto-startup vì listener chỉ nên chạy sau migration hoặc manual enable:

```java
@KafkaListener(
    id = "orders-ready-listener",
    topics = KafkaTopics.ORDERS,
    autoStartup = "false")
public void receive(String payload) {
    // ...
}
```

Đây là **snippet biến thể**, không áp dụng vào project runnable chính. Nếu autoStartup=false, `container.isRunning()` sẽ false. Khi test có quyền chủ động start listener:

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-ready-listener");
assertNotNull(container);
container.start();
ContainerTestUtils.waitForAssignment(container, 1);
```

Cần cleanup/stop phù hợp nếu test tự điều khiển lifecycle. **Không gọi `waitForAssignment` trên container cố ý chưa start** rồi chờ nó tự hoạt động. Trong production, khởi động muộn có thể đi cùng ordering/migration/business readiness constraints riêng.

Nếu ứng dụng có nhiều listeners, start/stop toàn bộ registry có tác động rộng; thường quản lý listener theo ID chính xác là tốt hơn.

## 20. Group rebalance làm readiness thay đổi

Assignment không phải trạng thái bất biến. Khi thêm consumer, consumer chết, partition count đổi hoặc broker/network gặp sự cố, Kafka có thể **rebalance**:

```text
Listener assigned partition -> test begins publish
          |
          +-- new consumer joins same group
          |
          v
Rebalance starts: assignment có thể bị revoke
          |
          v
New assignment to this or another consumer
```

`waitForAssignment` bảo vệ startup race trong môi trường test kiểm soát broker/group, nhưng **không** chứng minh không có rebalance sau thời điểm return. Để tests đáng tin:

- Dùng group ID và topics riêng cho suite.
- Không chạy các test khác cùng group và broker nếu không có thiết kế parallel.
- Tránh khởi động/dừng consumer ngẫu nhiên trong cùng test.
- Với topology nhiều consumers, thiết kế expected assignment phù hợp thay vì “đợi đủ tất cả partitions trên một consumer”.
- Nếu muốn test rebalance, điều đó là **một bài integration khác**: quan sát listener state trước/sau revoke/assign và xác minh không duplicate/loss ngoài contract.

Khi production thực có rebalances, message processing phải có idempotency và offset commit strategy đúng; readiness wait không thay thế chúng.

## 21. Chọn ack mode, offsets và isolation đúng

Một số Kafka configuration dễ làm test khác expectation:

| Thiết lập | Ý nghĩa | Ảnh hưởng tới test |
| --- | --- | --- |
| `auto.offset.reset=earliest` | Nếu group chưa có committed offset, bắt đầu từ earliest | Có thể đọc records cũ trên reused broker |
| `auto.offset.reset=latest` | Nếu group chưa có committed offset, bắt đầu ở cuối log | Message gửi trước assignment có thể bị bỏ qua |
| `group.id` | Consumer group identity | Groups khác đọc log độc lập; consumers cùng group chia partitions |
| `enable.auto.commit` | Kafka client tự commit offsets hay không | Khác listener/container commit strategy |
| Spring listener ack mode | Khi nào framework acknowledge/commit | Không đồng nghĩa business DB transaction commit |
| `isolation.level=read_committed` | Bỏ qua chưa commit/aborted transactional records | Test transactional producer cần cấu hình tương ứng |
| Topic partition count | Phân phối records và ordering | ảnh hưởng expected assignment và message order |

Không sửa `auto-offset-reset=earliest` để “làm tất cả tests pass” nếu yêu cầu production dùng latest/committed positions. Đầu tiên hãy xác định race condition, sau đó viết readiness gate và tách data/group IDs. Nếu test đang xác minh **offset reset behavior**, cố ý gửi message trước assignment có thể là setup hợp lệ, nhưng đó không phải test listener-ready thông thường.

### Producer key không quyết định thứ tự toàn cluster

Trong một partition, records có log ordering. Một key ổn định thường giúp partitioner đưa messages cùng key vào cùng partition, nhưng **topic nhiều partitions và thay đổi partition count** có thể ảnh hưởng mapping. Khi test đòi strict order, chọn một partition hoặc gửi rõ vào cùng partition rồi assert offset. Project mẫu chọn một partition để loại giả định mơ hồ.

## 22. Bounded waiting và failure diagnostics

Một wait hữu ích phải có **deadline**. Trong project:

```java
ContainerTestUtils.waitForAssignment(container, 1);
```

test utility thực hiện bounded waiting và ném lỗi khi assignment không đạt. Nếu method fail, đọc root cause/lifecycle; không thay ngay bằng `Thread.sleep(60000)`.

Để chờ business side effect, có thể dùng Awaitility (ngoài project, cần dependency) theo dạng:

```java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertEquals("PROCESSED", repository.findStatus(id)));
```

Đây là **snippet**, chưa có `repository`/`id` và chưa thêm Awaitility dependency trong build.gradle. Nó biểu diễn cách chờ eventual condition thay vì sleep cố định.

### Log nào giúp debug?

Khi timeout, thu thập có chọn lọc:

- Listener ID và `container.isRunning()`.
- Assigned partitions tại thời điểm lỗi.
- Topic name và topic partitions (không nhầm tên).
- Consumer group ID thực tế.
- Bootstrap servers (không log password/secret).
- Kafka startup, group join/rebalance logs.
- Producer send exception/result metadata.
- Consumer deserialization/handler exception.
- Offset reset policy và committed offset khi cần.

Không dán nguyên Kafka logs chứa payload PII, credentials hoặc SASL settings vào artifact public. Test error message nên nói rõ **đang chờ readiness hay chờ xử lý message**.

## 23. Tránh test pollution và phụ thuộc thứ tự

Những nguyên nhân test đơn lẻ PASS nhưng cả suite FAIL:

- Dùng chung broker/topic/group giữa nhiều test classes.
- Dùng `@EmbeddedKafka` và global embedded broker cùng lúc, gây cạnh tranh system properties.
- Context cache giữ consumer trỏ tới broker đã dừng.
- Một test restart listener khiến test sau thấy state khác.
- Queue/latch test không reset hoặc giữ record cũ.
- Producer gửi 2 records nhưng test chỉ poll 1, làm test tiếp nhận “đồ thừa”.
- Parallel tests cùng gửi vào một topic/consumer group và chia nhau messages.
- Bắt đầu test trước khi group assignment ổn định.
- Test kiểm tra global order trên nhiều partitions.

Project mẫu dùng một embedded broker/class, một topic/group, bốn methods tuần tự theo JUnit default, readiness trước publish, queue reset và drain đúng số records. Nếu bật JUnit parallel execution, cần isolate test topic/group/fixture hoặc hạn chế parallel cho class này; **không** mặc nhiên cho rằng queue chung vẫn an toàn.

### Context cache và @DirtiesContext

`@DirtiesContext(classMode=AFTER_CLASS)` làm Spring test context đóng sau class, giảm nguy cơ lifecycle mismatch. Nếu có nhiều Kafka tests chia sẻ brokers hoặc Testcontainers, hãy thiết kế một ownership/lifecycle rõ cho mỗi suite. Đừng dùng listener của broker A qua KafkaTemplate đang trỏ broker B.

## 24. Lỗi thường gặp và cách giải quyết

| Triệu chứng | Nguyên nhân có thể | Giải pháp |
| --- | --- | --- |
| `registry.getListenerContainer(...) == null` | ID sai, bean không được scan hoặc @KafkaListener chưa được đăng ký | Kiểm tra ID, @EnableKafka, component scan |
| `container.isRunning()==false` | autoStartup=false, startup lỗi, context chưa chuẩn | Kiểm tra lifecycle/exception; start nếu test chủ động |
| `waitForAssignment` timeout | Topic thiếu, broker không ready, group không join, consumer gặp lỗi | Kiểm tra Kafka logs, topic metadata, group ID |
| Assigned count thấp hơn expected | Consumer khác cùng group sở hữu partitions | Isolate group hoặc sửa expected theo topology |
| Producer send ACK nhưng test không nhận | Listener chưa assignment, offset reset, deserializer hoặc consumer group khác | Chờ assignment trước gửi, xem errors |
| Test PASS local, FAIL CI | Startup timing/resources thay đổi | Không sleep cố định, bounded waits và đủ CI resources |
| Test thấy message của case trước | Queue/topic/group dùng chung, records chưa drain | Unique marker và cleanup/isolation |
| Test đọc record nhưng DB chưa có | Handler async/transaction chưa commit | Chờ business state, không chỉ callback |
| Test thứ tự fail trên nhiều partitions | Kafka chỉ order per partition | Gửi cùng partition, assert theo partition |
| `@EmbeddedKafka` broker không start | Dependency/version/port/temp files | Kiểm tra spring-kafka-test và logs |
| Consumer không decode được String | Serializer/deserializer không khớp | StringSerde cấu hình ở test YAML |
| KafkaTemplate bean thiếu | Thiếu spring-kafka/auto config | Kiểm tra Gradle, Spring Boot Kafka config |
| Unknown topic partition | Topic chưa được tạo hoặc name lệch | @EmbeddedKafka topics, KafkaAdmin/NewTopic |
| ConsumerStartedEvent có nhưng không nhận | Event chưa bảo đảm assignment | Dùng waitForAssignment |
| Rabbit listener isRunning nhưng không consume | Queue/binding hoặc active consumer chưa ready | Kiểm tra active consumers/connection riêng |
| Chờ vô hạn | Await thiếu deadline | Dùng bounded poll/await timeout |
| Parallel jobs flaky | Shared group/topics | Tách mỗi suite, tránh consumer competition |
| Ứng dụng gọi broker production | Bootstrap server config sai | Dùng embedded property hoặc Testcontainers connection details |

### Lộ trình debug 7 bước

1. Xác định broker thực sự được test dùng: embedded, container hay shared?
2. Xác định topic đã tồn tại, đúng partition count?
3. Xác nhận listener bean được Spring scan và registry tìm được đúng ID?
4. Xác nhận container running và Kafka consumer được assignment?
5. Chỉ sau đó gửi một record có marker duy nhất; chờ producer future với timeout.
6. Chờ listener outcome có timeout; xác nhận key/value/topic/offset hoặc business state.
7. Nếu thất bại chỉ khi chạy suite, xem group collision, reused broker, parallel execution và context cache.

## 25. Checklist QA trước khi merge

- [ ] Đã phân biệt context refresh, broker ready, listener running, partition assigned và handler completed?
- [ ] `@KafkaListener` có ID rõ để tìm qua registry?
- [ ] `getListenerContainer(id)` được kiểm tra khác null?
- [ ] Container được start đúng lifecycle; `autoStartup` đã hiểu?
- [ ] Với Kafka, test **chờ assignment** trước khi publish?
- [ ] Số partitions đợi phù hợp topic/group topology?
- [ ] Không dùng `Thread.sleep` cố định thay readiness gate?
- [ ] Producer send có timeout và kiểm tra kết quả/exception?
- [ ] Test chờ listener/business outcome bằng bounded poll/await?
- [ ] Producer ACK không được xem là listener completed?
- [ ] Kafka serializers/deserializers khớp payload type?
- [ ] Broker bootstrap URI đến từ embedded/Testcontainers, không hardcode localhost?
- [ ] Topic được tạo trước khi listener subscribe?
- [ ] Consumer group/topic có isolate khỏi tests khác?
- [ ] `auto.offset.reset` và committed offsets được xét đúng?
- [ ] Nếu test kiểm tra order, các records thuộc cùng partition?
- [ ] Không assert global ordering trên multi-partition topic?
- [ ] Test hooks/queues/latches không rò state giữa methods?
- [ ] Không có test phụ thuộc thứ tự JUnit methods?
- [ ] CI có đủ tài nguyên cho embedded Kafka/Testcontainers?
- [ ] Spring context cache và broker lifecycle có hợp lý?
- [ ] Rabbit/JMS không được áp dụng mù Kafka waitForAssignment API?
- [ ] Test business side effect được kiểm tra riêng nếu cần?
- [ ] Đã xem báo cáo chạy thực, không suy PASS chỉ từ mã nguồn?
- [ ] Không in payload nhạy cảm hoặc secrets vào test artifacts?

## 26. Bài tập thực hành

1. Chạy `OrderListenerReadyTest` và xem Kafka listener được gán partition trước khi publish thế nào.
2. Tạm bỏ `ContainerTestUtils.waitForAssignment` trong sandbox, bật `auto-offset-reset=latest`, chạy nhiều lần để quan sát tính không ổn định; không mặc nhiên hứa có race ở mọi lần.
3. Đổi listener `id` nhưng giữ test lookup ID cũ, xem assertion báo thiếu container.
4. Đặt `autoStartup="false"`, giải thích vì sao phải gọi `start()` trước khi chờ assignment.
5. Bỏ `@EnableKafka` khi dùng Boot auto-config, xác định thực tế listener có còn được đăng ký không và vì sao; không mặc định mọi app config như nhau.
6. Đổi Kafka topic thành ba partitions, đặt concurrency=2 và chọn expected assignment phù hợp.
7. Tạo một consumer cùng group ở test khác, quan sát consumer competition và rebalance.
8. Gửi hai messages cùng key khi topic có hai partitions và giải thích phạm vi ordering.
9. Gửi dữ liệu Unicode và verify `StringSerializer`/`StringDeserializer` xử lý chính xác.
10. Đổi consumer deserializer thành JSON sai với payload String, xem root cause thay vì nới timeout.
11. Đổi producer timeout thành quá ngắn trên CI mô phỏng và phân biệt producer failure với listener timeout.
12. Thêm service/repository thật vào listener rồi dùng Awaitility chờ DB state sau callback.
13. Dùng `@EmbeddedKafka(kraft=true)` và kiểm tra phiên bản Spring Kafka hỗ trợ attribute đó.
14. Thêm Testcontainers Kafka để đối chiếu broker image với embedded; vẫn chờ assignment riêng.
15. Viết RabbitMQ test kiểm tra active consumer trước publish; không dùng Kafka ContainerTestUtils cho Rabbit.
16. Thử parallel test classes cùng group để thấy vì sao tests cần isolated consumer groups/topics.
17. Dùng `ConsumerStartedEvent` làm tín hiệu duy nhất trong sandbox rồi phân tích vì sao chưa đủ.
18. Chạy một test riêng và cả suite; không để messages dư từ test khác.
19. Kiểm tra JUnit XML/HTML report để xác định số tests PASS/FAIL/SKIPPED thật.
20. Thiết kế readiness strategy cho production khi listener có thể rebalance sau startup.

## 27. Tài liệu tham khảo

- [Spring Boot 3.3 — Kafka Support](https://docs.spring.io/spring-boot/3.3/reference/messaging/kafka.html): auto-configuration, KafkaTemplate, @KafkaListener, testing with embedded broker.
- [Spring Kafka 3.2 — Testing Applications](https://docs.spring.io/spring-kafka/reference/3.2/testing.html): spring-kafka-test, @EmbeddedKafka, KRaft, embedded brokers và utilities.
- [Spring Kafka 3.2 — ContainerTestUtils](https://docs.spring.io/spring-kafka/docs/3.2.x/api/org/springframework/kafka/test/utils/ContainerTestUtils.html): `waitForAssignment(Object, int)` và failure modes.
- [Spring Kafka — @KafkaListener Lifecycle](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/kafkalistener-lifecycle.html): registry, listener IDs và container startup.
- [Spring Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): consumer started/idle/non-responsive events và ý nghĩa.
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): group ID, auto.offset.reset, isolation level.
- [Testcontainers Java — Kafka](https://java.testcontainers.org/modules/kafka/): Kafka container bootstrap addresses.
- [Spring AMQP — Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): Rabbit listeners, consumer lifecycle.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): @BeforeEach, test independence.
- [Spring Framework — TestContext Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): application context reuse.

## 28. Kết luận

**Chờ listener sẵn sàng phải dựa trên điều kiện đúng — không dựa vào thời gian ngủ.** Với Kafka integration tests, ứng dụng Spring đã startup và listener container `isRunning()` chưa bảo đảm consumer đã có partition assignment. Một chiến lược đơn giản, đúng phạm vi khi test kiểm soát broker/topic/group là:

1. Tìm container bằng `KafkaListenerEndpointRegistry.getListenerContainer(listenerId)`.
2. Xác nhận container running và gọi `ContainerTestUtils.waitForAssignment(container, expectedPartitions)`.
3. Chỉ **sau đó** gửi record bằng `KafkaTemplate`.
4. Chờ listener callback hoặc business state bằng timeout hữu hạn.
5. Assert payload/metadata/side effect và giữ fixtures/group/topic cô lập giữa tests.

Broker ACK không đồng nghĩa xử lý hoàn tất, `auto.offset.reset=earliest` không thay thế readiness, và thứ tự Kafka chỉ được bảo đảm trong từng partition. Khi triển khai RabbitMQ, JMS hoặc Redis Streams, áp dụng cùng tư duy về subscription/consumer readiness nhưng chọn **cơ chế riêng của từng broker**. Kiểm thử thực tế nên đọc Gradle/CI report trước khi tuyên bố PASS.
