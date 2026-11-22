# Embedded Kafka và Testcontainers — kiểm thử tin cậy trong Spring Kafka

## 1. Vì sao hệ thống Kafka cần integration test với broker thật?

Một ứng dụng Spring Kafka có thể vượt qua toàn bộ unit test nhưng vẫn thất bại khi chạy thực tế:

- Producer serialize đúng object trong unit test nhưng broker từ chối message vì topic không tồn tại hoặc ACL sai.
- Consumer xử lý business logic đúng nhưng `@KafkaListener` không nhận được record do sai `group.id`, topic hoặc deserializer.
- Retry được cấu hình nhưng poison message khiến partition bị xử lý lặp vô hạn.
- Record gửi tới dead-letter topic (DLT) sai partition hoặc thiếu headers cần truy vết.
- Consumer xử lý xong dữ liệu nhưng offset chưa commit; sau crash record bị phát lại.
- Test trên máy cá nhân qua được nhưng trên CI thất bại ngẫu nhiên vì listener chưa được assign partition.
- Một phiên bản Kafka broker, Kafka client hoặc Spring Kafka mới làm thay đổi hành vi mà mock không thể mô phỏng.

**Embedded Kafka** và **Testcontainers** giúp kiểm thử luồng gửi/nhận thật thay vì chỉ mock `KafkaTemplate` hay gọi trực tiếp method listener.

Hai công cụ giải quyết những mục tiêu khác nhau:

- **Embedded Kafka** khởi động Kafka broker phục vụ test ngay trong môi trường JVM test; cấu hình nhanh, tích hợp tốt với `spring-kafka-test`.
- **Testcontainers** khởi động Kafka broker trong Docker container; cách ly process/hệ điều hành rõ hơn, có thể ghép với PostgreSQL, Redis, schema registry hoặc network proxy để kiểm thử tương tác nhiều thành phần.

Trong module **Spring Kafka Reliability Operations**, lựa chọn môi trường test phải xuất phát từ một câu hỏi: **rủi ro tin cậy nào cần chứng minh?** Test nhận một record khác với test bảo đảm retry không mất dữ liệu, và cả hai khác với kiểm thử broker failover thật.

Bài viết sử dụng **Java 17+, Spring Boot 3.x, Spring Kafka 3.x, JUnit 5, Testcontainers 1.x** làm baseline. Các phiên bản Kafka/Spring Kafka/Testcontainers liên tục thay đổi; hãy căn phiên bản dependency theo BOM dự án. Với Spring Boot 4/Spring Kafka 4/Testcontainers 2 cần đối chiếu package và API trước khi dùng nguyên ví dụ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Lựa chọn Embedded Kafka hay Testcontainers theo mục tiêu, giới hạn và chi phí test.
2. Cấu hình `spring-kafka-test`, `@EmbeddedKafka`, `@SpringBootTest` và bootstrap servers.
3. Gửi record bằng `KafkaTemplate`, nhận bằng Kafka consumer thật và assert kết quả.
4. Kiểm tra `@KafkaListener` bất đồng bộ mà không phụ thuộc `Thread.sleep`.
5. Dựng Kafka container độc lập với `@Testcontainers` và `@DynamicPropertySource`.
6. Viết test về retry, DLT, offset, replay, ordering và idempotent processing.
7. Nhận diện chỗ cần fault injection hoặc Kafka cluster nhiều broker.
8. Tổ chức test cô lập, lặp lại được, phù hợp CI và vận hành production.

---

## 2. Phân tầng kiểm thử trước khi chọn công cụ

Không nên khởi động Kafka cho mọi test. Một test suite đáng tin chia theo điều cần xác minh.

| Tầng test | Thành phần | Kiểm tra được | Không kiểm tra đầy đủ |
| --- | --- | --- | --- |
| Unit test | Mockito/fake, domain service | Validation, mapping, quyết định business | Serialization thật, broker, group/offset |
| Slice/integration nhẹ | Spring context + Embedded Kafka | Producer/consumer wiring, topic, partition, serialize, listener | Docker network, OS process isolation, cluster failover |
| Container integration | Spring + Kafka Testcontainers | Kafka broker trong process riêng, network endpoints, kết hợp DB/container | Production broker topology, security và multi-zone nếu không cấu hình thêm |
| Multi-container reliability | Kafka + DB + proxy/chaos + worker | Network partition, recovery, idempotency across services | Mọi đặc tính của production cluster |
| Preproduction / staging | Broker cluster gần production | ACL/TLS, replication, ISR, rebalancing, throughput | Không thể chứng minh tuyệt đối mọi sự cố tương lai |

Quy tắc hiệu quả: dùng **unit test cho logic thuần**, **Embedded Kafka cho vòng phản hồi nhanh**, **Testcontainers cho tích hợp đáng tin với công nghệ thật**, và **cluster test** cho tình huống phân tán/khả dụng cao.

### 2.1. Test “có nhận record” là bước đầu, chưa đủ

Một test:

```text
producer.send() -> broker -> consumer.poll() -> assert value
```

chứng minh có thể truyền một record ở điều kiện bình thường. Nó **không tự chứng minh**:

- Consumer có xử lý đúng khi listener ném exception?
- Offset commit trước hay sau DB commit?
- Sau crash record có thể bị xử lý lại không?
- Có DLT khi retry exhausted?
- Producer có giữ ordering giữa partitions?
- Broker một node có chịu được một node chết không?
- Cấu hình TLS/SASL có tương thích production không?

Chúng ta sẽ xây các scenario này riêng, tránh gộp một test “happy path” thành bằng chứng exactly-once.

---

## 3. Embedded Kafka và Testcontainers: so sánh thực tế

| Tiêu chí | Embedded Kafka | Kafka Testcontainers |
| --- | --- | --- |
| Nơi chạy broker | Trong hệ thống test/JVM, dùng EmbeddedKafkaBroker | Docker container riêng |
| Khởi động | Thường nhanh khi test nhỏ | Có chi phí pull image/start container |
| Yêu cầu Docker | Không | Có |
| Phù hợp developer laptop/CI | Có, không phụ thuộc Docker | Cần Docker runtime/daemon và image |
| Cấu hình test | `@EmbeddedKafka`, `spring-kafka-test` | `@Container` + dynamic bootstrap |
| Hành vi Kafka thật | Có Kafka broker thực cho test | Có Kafka broker thực trong container |
| Process isolation | Thấp hơn container | Rõ hơn |
| Test Kafka + PostgreSQL | Có thể ghép DB khác nhưng không phải trọng tâm | Thuận tiện cùng Docker network |
| Đứt mạng giữa services | Khó mô phỏng chân thực | Có thể thêm Toxiproxy/network controls |
| Test multi-broker replication | Không mặc định; cần topology riêng | Không mặc định; một container thường là một broker |
| Speed/cost trên CI | Phù hợp test thường xuyên | Thường dành cho integration suite chọn lọc |
| TLS/SASL production | Cần cấu hình đặc thù | Có thể dựng topology gần production hơn |
| Độ cô lập topic/group | Vẫn phải chủ động thiết kế | Vẫn phải chủ động thiết kế |

**Điểm chung:** cả hai đều có thể chạy Kafka broker thật cho test, nhưng thường chỉ chạy **một broker**. Một broker đủ để kiểm tra message flow, không chứng minh khả năng chịu lỗi của cluster có replication factor 3 và `min.insync.replicas=2`.

### 3.1. Khi nào ưu tiên Embedded Kafka?

- Test `KafkaTemplate` serialize và publish.
- Test `@KafkaListener` nhận và deserialize.
- Test listener retry/DLT mức integration.
- Test partition routing và key trong một broker.
- Dự án CI hạn chế Docker.
- Cần nhiều test nhanh, độc lập, ở tầng ứng dụng.

### 3.2. Khi nào ưu tiên Testcontainers?

- Kiểm tra ứng dụng Spring Boot với cấu hình Kafka giống quá trình deploy.
- Kết hợp Kafka, PostgreSQL, Redis, service A và service B.
- Test idempotency/transaction khi DB và Kafka chạy đồng thời.
- Cần can thiệp network bằng proxy, pause container hoặc định tuyến trong Docker.
- Kiểm tra client compatibility với image Kafka cụ thể.
- Muốn khởi tạo hạ tầng integration nhất quán giữa máy cá nhân và CI.

Không phải “Testcontainers luôn tốt hơn”. Nếu mục tiêu chỉ là test mapper của một message, cả hai công cụ đều có thể là quá mức cần thiết.

---

## 4. Dự án Spring Boot mẫu

Bài thực hành xây ứng dụng nhỏ:

```text
Producer API / service
       |
       v
  KafkaTemplate<String, String>
       |
       v
  Topic: orders.created
       |
       v
  @KafkaListener
       |
       v
  Order handler / database projection

Các test:
  - EmbeddedKafka: send -> Kafka record
  - EmbeddedKafka: send -> @KafkaListener -> assertion
  - Testcontainers: send -> isolated Kafka broker -> record
  - Reliability: poison message -> retry -> DLT
  - Reliability: duplicate replay -> idempotent handler
```

### 4.1. Thư mục

```text
kafka-reliability-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/kafkalab/
    │   │   ├── KafkaLabApplication.java
    │   │   └── OrderPublisher.java
    │   └── resources/application.yml
    └── test/
        ├── java/com/example/kafkalab/
        │   ├── EmbeddedKafkaIntegrationTest.java
        │   ├── ListenerIntegrationTest.java
        │   ├── KafkaContainerIntegrationTest.java
        │   └── OrderIdempotencyTest.java
        └── resources/application-test.yml
```

### 4.2. Gradle dependency

Ví dụ dùng Spring Boot 3.3.x/Spring Kafka 3.x, Testcontainers 1.x tương thích với Spring Boot BOM.

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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'

    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'

    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

BOM Spring Boot quản lý version các dependency thông dụng; khi dùng Spring Boot bản khác hãy kiểm tra tương thích với Kafka client, Testcontainers và image broker. Một số Testcontainers release mới chuyển module/package; các ví dụ ở đây cố ý chọn API của Testcontainers 1.x để minh họa.

`settings.gradle`:

```groovy
rootProject.name = 'kafka-reliability-lab'
```

### 4.3. Ứng dụng và producer

`KafkaLabApplication.java`:

```java
package com.example.kafkalab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafka;

@SpringBootApplication
@EnableKafka
public class KafkaLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(KafkaLabApplication.class, args);
    }
}
```

`OrderPublisher.java`:

```java
package com.example.kafkalab;

import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> template;

    public OrderPublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String topic,
            String orderId,
            String payload) {

        return template.send(topic, orderId, payload);
    }
}
```

`KafkaTemplate.send(...)` của Spring Kafka 3.x trả `CompletableFuture`. Đối với production, producer thường không nên chờ đồng bộ trên từng message; việc dùng `future.get(...)` trong integration test chỉ giúp xác nhận record đã được broker chấp nhận theo cấu hình producer và đặt timeout để test không treo vô hạn.

### 4.4. Cấu hình serializer/deserializer

`src/test/resources/application-test.yml`:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      auto-offset-reset: earliest
      enable-auto-commit: false
    listener:
      ack-mode: record
```

`bootstrap-servers` **không được hardcode** ở file test này; Embedded Kafka hoặc Testcontainers sẽ cung cấp endpoint đúng theo môi trường.

Ý nghĩa:

- `acks=all`: broker chờ xác nhận theo điều kiện ISR; trong cluster một broker đây không phải bằng chứng replication.
- `auto-offset-reset=earliest`: dùng khi group chưa có committed offset; giúp test consumer mới không bỏ record gửi trước khi subscribe.
- `enable-auto-commit=false`: cho Spring listener container quản lý offset thay vì client auto commit.
- `ack-mode=record`: listener container thường commit offset sau khi record listener xử lý thành công theo semantics cấu hình. Với retry/error handler/transactions, hành vi commit cần được kiểm tra bằng scenario cụ thể.

Cấu hình test được kích hoạt bằng `@ActiveProfiles("test")`.

---

## 5. Embedded Kafka: broker được tạo trong test

### 5.1. `@EmbeddedKafka` hoạt động thế nào?

`spring-kafka-test` cung cấp:

- `@EmbeddedKafka` để yêu cầu test khởi tạo Kafka broker.
- `EmbeddedKafkaBroker` để truy cập bootstrap servers, topic và các tiện ích test.
- `KafkaTestUtils` để tạo cấu hình consumer/producer và đọc record test.
- `ContainerTestUtils` hỗ trợ chờ partition assignment của listener container.

Khi dùng Spring context, Spring Kafka đăng ký broker phù hợp cho test. Hãy tránh đồng thời bật các kiểu khởi tạo embedded broker khác nhau trong cùng suite nếu không có chủ đích.

### 5.2. Test publish → consume bằng Kafka client thật

`EmbeddedKafkaIntegrationTest.java`:

```java
package com.example.kafkalab;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = KafkaLabApplication.class)
@ActiveProfiles("test")
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.embedded.it"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class EmbeddedKafkaIntegrationTest {

    private static final String TOPIC = "orders.embedded.it";

    @Autowired
    OrderPublisher publisher;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Test
    void producerPublishesRecordToEmbeddedBroker()
            throws Exception {

        String groupId =
            "probe-" + UUID.randomUUID();

        Map<String, Object> consumerProps =
            KafkaTestUtils.consumerProps(
                groupId, "false", embeddedKafka);

        try (Consumer<String, String> consumer =
                new DefaultKafkaConsumerFactory<>(
                    consumerProps,
                    new StringDeserializer(),
                    new StringDeserializer()
                ).createConsumer()) {

            // Assign topic/partition và seek về đầu.
            // Nên subscribe/assign trước lúc publish.
            embeddedKafka.consumeFromAnEmbeddedTopic(
                consumer, TOPIC);

            var result = publisher.publish(
                TOPIC, "order-42", "CREATED")
                .get(10, TimeUnit.SECONDS);

            assertEquals(TOPIC,
                result.getRecordMetadata().topic());

            var received = KafkaTestUtils.getSingleRecord(
                consumer, TOPIC, Duration.ofSeconds(10));

            assertEquals("order-42", received.key());
            assertEquals("CREATED", received.value());
            assertEquals(TOPIC, received.topic());
            assertEquals(0, received.partition());
        }
    }
}
```

### 5.3. Vì sao dùng một consumer riêng?

Test tạo `group.id` ngẫu nhiên để không đọc committed offsets của test trước. Consumer test được đóng bằng `try-with-resources` để giải phóng network connections.

`embeddedKafka.consumeFromAnEmbeddedTopic(...)` gán partition và seek theo tiện ích của Spring Kafka test, tránh phụ thuộc vào việc consumer có kịp join group trước khi publish hay không. Khi topic có nhiều partitions, phải xem assignment và offset của từng partition; không giả định mọi key được phân vào partition 0.

### 5.4. `bootstrapServersProperty` quan trọng

Annotation:

```java
@EmbeddedKafka(
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

chuyển bootstrap address của embedded broker vào property mà Spring Boot Kafka auto-configuration đọc. Nếu không gắn đúng property, `KafkaTemplate` có thể cố kết nối `localhost:9092` và gây test thất bại hoặc vô tình dùng Kafka broker trên máy developer.

Với một số phiên bản `spring-kafka-test`, default mapping sang `spring.kafka.bootstrap-servers` có thể đã có; cấu hình tường minh giúp bài thực hành dễ đọc và giảm lệ thuộc vào default theo version.

### 5.5. Test phải chứng minh đủ hai phía

`future.get(...)` thành công chỉ chứng minh gửi được message theo ack semantics. `KafkaTestUtils.getSingleRecord(...)` chứng minh consumer test nhận được record đó. Nếu muốn kiểm tra application listener và business side effect, cần test ở bước tiếp theo; không thể lấy kết quả raw consumer làm bằng chứng `@KafkaListener` của ứng dụng chạy đúng.

---

## 6. Kiểm thử `@KafkaListener` bất đồng bộ

### 6.1. Vì sao listener test dễ flaky?

`@KafkaListener` chạy trên thread của container, không cùng thread JUnit. Khi test vừa gửi message và lập tức assert:

```java
publisher.publish(TOPIC, key, value);
assertEquals(1, processed.size()); // Flaky
```

listener có thể chưa được assign partition hoặc chưa kịp poll, kể cả khi message đã nằm trong broker.

Đừng sửa bằng `Thread.sleep(5000)`:

- Trên máy nhanh, test mất thời gian vô ích.
- Trên CI chậm, 5 giây vẫn có thể thiếu.
- Test không chờ đúng điều kiện cần xảy ra.
- Khi lỗi, khó phân biệt Kafka lỗi với race trong test.

### 6.2. Tạo probe listener chỉ dành cho test

`ListenerIntegrationTest.java`:

```java
package com.example.kafkalab;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = KafkaLabApplication.class)
@ActiveProfiles("test")
@Import(ListenerIntegrationTest.ProbeConfig.class)
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.listener.it"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class ListenerIntegrationTest {

    @Autowired
    OrderPublisher publisher;

    @Autowired
    ProbeListener probe;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Test
    void listenerReceivesPublishedOrder() throws Exception {
        MessageListenerContainer container =
            registry.getListenerContainer(
                "orders-it-listener");

        assertNotNull(container);

        // Chờ listener được assign một partition thật.
        ContainerTestUtils.waitForAssignment(
            container, 1);

        publisher.publish(
            "orders.listener.it", "order-51", "APPROVED")
            .get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> record =
            probe.received.poll(
                10, TimeUnit.SECONDS);

        assertNotNull(record);
        assertEquals("order-51", record.key());
        assertEquals("APPROVED", record.value());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ProbeConfig {

        @Bean
        ProbeListener probeListener() {
            return new ProbeListener();
        }
    }

    static class ProbeListener {

        private final BlockingQueue<ConsumerRecord<String, String>>
            received = new LinkedBlockingQueue<>();

        @KafkaListener(
            id = "orders-it-listener",
            topics = "orders.listener.it",
            groupId = "orders-listener-it"
        )
        public void onRecord(ConsumerRecord<String, String> record) {
            received.add(record);
        }
    }
}
```

Test dùng `ContainerTestUtils.waitForAssignment(...)` làm barrier cho việc listener sẵn sàng, sau đó chờ bằng `BlockingQueue.poll(timeout)`. Test kết thúc sớm khi điều kiện đạt, và có giới hạn thời gian khi sự kiện không xảy ra.

Trong dự án thật, nên inject **handler business** và assert trạng thái lưu vào repository/database (đầu ra được quan sát từ ngoài) thay vì chỉ quan sát queue test. Queue chỉ minh họa cơ chế test asynchronous.

### 6.3. Nếu listener có nhiều partitions?

Giả sử `@EmbeddedKafka(partitions=3)`, listener concurrency=2. Khi dùng `waitForAssignment`, con số cần truyền phải phù hợp tổng assignment kỳ vọng của container, không tự đặt là 1. Nếu có group rebalancing, assignment có thể thay đổi; test nên chờ trạng thái ổn định trước khi gửi.

### 6.4. Dùng Awaitility cho kết quả bất đồng bộ

Nếu handler ghi vào repository:

```java
await()
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        assertTrue(repository.existsByEventId("evt-2001"));
    });
```

Import tương ứng:

```java
import static org.awaitility.Awaitility.await;
```

Cách này giúp kiểm tra **hệ quả nghiệp vụ đã persist**. Không dùng `await().until(() -> true)` hoặc chờ đơn thuần theo thời gian rồi giả định Kafka đã hoàn tất.

---

## 7. Định nghĩa topic rõ ràng và cô lập dữ liệu test

### 7.1. Không phụ thuộc auto-create topic ngoài ý muốn

Một single-broker test có thể hoạt động dù không khai báo topic, do Kafka tự tạo topic khi producer gửi. Điều này dễ che lỗi production, nơi `auto.create.topics.enable=false` hoặc producer không có quyền tạo topic.

Với Embedded Kafka:

```java
@EmbeddedKafka(
    partitions = 3,
    topics = {"orders.input.it", "orders.input.it.DLT"},
    brokerProperties = {
        "auto.create.topics.enable=false"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

Với Testcontainers và Spring Boot, có thể khai báo `NewTopic` để `KafkaAdmin` tạo topic lúc ứng dụng khởi động:

```java
@Bean
NewTopic ordersTopic() {
    return TopicBuilder.name("orders.container.it")
        .partitions(1)
        .replicas(1)
        .build();
}
```

Imports:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.kafka.config.TopicBuilder;
```

Ở production, topic creation thường được quản lý bởi Terraform/Ansible/platform team; test `KafkaAdmin` chỉ minh họa cách tạo resource deterministically.

### 7.2. Nhớ cả topic và consumer group

Để các test không làm nhiễu nhau:

- Dùng tên topic test riêng theo class/scenario.
- Dùng consumer group ID riêng hoặc tạo broker mới.
- Nếu có DLT, tạo DLT topic rõ ràng.
- Không dùng chung `group.id` với listener production hoặc test khác.
- Reset/đóng consumer, listener và database giữa test khi cần.
- Khi test chia sẻ Spring context, cân nhắc `@DirtiesContext` có mục đích; tránh dùng đại trà gây chậm suite.

### 7.3. Cấu hình offset reset không thay thế isolation

`auto.offset.reset=earliest` chỉ có tác dụng **khi group chưa có committed offset hợp lệ**. Nếu một group đã commit offset cuối, consumer mới với cùng group thường tiếp tục từ offset đã commit, không tự quay về đầu.

Vì vậy một test đọc tất cả record từ đầu phải dùng group mới, gán/seek offsets tường minh, hoặc broker/topic được làm mới theo fixture.

---

## 8. Kafka Testcontainers: broker trong Docker

### 8.1. Mô hình lifecycle

Testcontainers quản lý container theo vòng đời test:

```text
JUnit starts
    |
    v
Testcontainers checks Docker
    |
    v
Starts Kafka image
    |
    v
Waits for broker readiness
    |
    v
Exposes mapped bootstrap address
    |
    v
Spring Boot KafkaTemplate / listener
    |
    v
Runs assertions
    |
    v
Container cleanup
```

Kafka chạy trong một process/container riêng, nhưng test vẫn cần cấu hình producer/consumer đúng. Việc container đã “started” không chứng minh topic được tạo hoặc consumer đã được assign.

### 8.2. Test container cùng `@DynamicPropertySource`

Ví dụ cho Testcontainers **1.x** dùng `org.testcontainers.containers.KafkaContainer`. API này có thể được đánh dấu deprecated trong các release mới; khi nâng lên Testcontainers mới hơn, xem module/container class tương ứng như `org.testcontainers.kafka.ConfluentKafkaContainer` và yêu cầu version/image.

`KafkaContainerIntegrationTest.java`:

```java
package com.example.kafkalab;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.kafka.config.TopicBuilder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers(disabledWithoutDocker = true)
@SpringBootTest(classes = KafkaLabApplication.class)
@ActiveProfiles("test")
@Import(KafkaContainerIntegrationTest.TopicConfig.class)
class KafkaContainerIntegrationTest {

    private static final String TOPIC =
        "orders.container.it";

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse(
                "confluentinc/cp-kafka:7.6.1"));

    @DynamicPropertySource
    static void kafkaProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers);
    }

    @Autowired
    OrderPublisher publisher;

    @Test
    void publishesAndConsumesUsingDockerKafka()
            throws Exception {

        Map<String, Object> props = new HashMap<>();
        props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            kafka.getBootstrapServers());
        props.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "tc-probe-" + UUID.randomUUID());
        props.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest");
        props.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
        props.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
        props.put(
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
            false);

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(props)) {

            consumer.subscribe(java.util.List.of(TOPIC));

            publisher.publish(
                TOPIC, "order-600", "CREATED")
                .get(10, TimeUnit.SECONDS);

            var received = KafkaTestUtils.getSingleRecord(
                consumer, TOPIC, Duration.ofSeconds(15));

            assertEquals("order-600", received.key());
            assertEquals("CREATED", received.value());
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TopicConfig {

        @Bean
        NewTopic ordersContainerTopic() {
            return TopicBuilder.name(TOPIC)
                .partitions(1)
                .replicas(1)
                .build();
        }
    }
}
```

`@Container` static giúp container được tạo một lần cho test class thay vì start/stop cho từng test method. `@DynamicPropertySource` truyền bootstrap servers thực tế đã map port cho Spring Boot.

Trong ví dụ, Testcontainers tạo một Kafka broker thật trong Docker. `KafkaTestUtils.getSingleRecord` vẫn tiện để assert consumer đã nhận record; Testcontainers không bắt buộc phải dùng helper của Spring Kafka, nhưng thư viện test đã có nên có thể sử dụng.

**Lưu ý:** `disabledWithoutDocker = true` giúp môi trường không có Docker skip test thay vì fail; với CI nơi integration suite **bắt buộc phải chạy**, có thể bỏ cờ này để pipeline báo thiếu Docker là lỗi cấu hình. Đừng để test quan trọng bị silently skipped khi triển khai.

### 8.3. `@ServiceConnection` của Spring Boot 3.1+

Khi thêm dependency:

```groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
```

Spring Boot có thể tự tạo connection details từ một số container được hỗ trợ:

```java
@Container
@ServiceConnection
static KafkaContainer kafka =
    new KafkaContainer(DockerImageName.parse(
        "confluentinc/cp-kafka:7.6.1"));
```

Import:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
```

Với cấu hình phù hợp, không cần tự viết `@DynamicPropertySource` cho bootstrap servers.

**Chọn một cơ chế rõ ràng** (`@ServiceConnection` hoặc `@DynamicPropertySource`) để tránh khó xác định property nào đang thắng. Support cho các container types phụ thuộc phiên bản Boot/Testcontainers; nên đối chiếu release đang dùng, đặc biệt khi chuyển sang Testcontainers 2.x.

### 8.4. Không hardcode cổng 9092

Kafka container thường expose một endpoint được Docker map ra cổng ngẫu nhiên. Chỉ lấy qua:

```java
kafka.getBootstrapServers()
```

Không viết `spring.kafka.bootstrap-servers=localhost:9092` để ép kết nối; điều đó có thể kết nối nhầm Kafka trên host hoặc thất bại ở runner CI.

---

## 9. Đưa Kafka và database vào cùng integration test

Một rủi ro reliability quan trọng là **consumer xử lý record rồi cập nhật database**. Unit test chỉ mock repository không chứng minh transaction/constraint đúng.

Có thể dùng Testcontainers để dựng:

```text
                 Docker runtime
           +----------------------+
           | KafkaContainer       |
           | topic: orders.events  |
           +----------+-----------+
                      |
                      v
            Spring Boot @KafkaListener
                      |
                      v
           +----------------------+
           | PostgreSQLContainer  |
           | processed_event table|
           +----------------------+
```

### 9.1. Khai báo thêm PostgreSQL Testcontainers

Dependency:

```groovy
testImplementation 'org.testcontainers:postgresql'
testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
testRuntimeOnly 'org.postgresql:postgresql'
```

Trong ứng dụng JDBC thật, `spring-boot-starter-jdbc` thường là `implementation`, không phải `testImplementation`. Đặt dependency theo kiến trúc ứng dụng.

Ví dụ các containers:

```java
@Container
static final KafkaContainer kafka =
    new KafkaContainer(DockerImageName.parse(
        "confluentinc/cp-kafka:7.6.1"));

@Container
static final PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>(
        DockerImageName.parse("postgres:16-alpine"))
        .withDatabaseName("reliability")
        .withUsername("test")
        .withPassword("test");

@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.kafka.bootstrap-servers",
        kafka::getBootstrapServers);
    registry.add("spring.datasource.url",
        postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
        postgres::getUsername);
    registry.add("spring.datasource.password",
        postgres::getPassword);
}
```

Khi dùng database thật, tạo schema bằng Flyway/Liquibase hoặc SQL initialization có chủ đích và kiểm tra readiness của từng container. Đây là **hạ tầng test**, không phải toàn bộ chương trình listener/DAO.

### 9.2. Scenario idempotency quan trọng

Bảng đích:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    payload VARCHAR(1000) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Nếu consumer đọc lại cùng event (do crash trước commit offset, rebalance hoặc replay), bảng phải không có hai logical records cho cùng `event_id`.

Ví dụ PostgreSQL:

```sql
INSERT INTO processed_event (
    event_id, order_id, payload
) VALUES (?, ?, ?)
ON CONFLICT (event_id) DO NOTHING;
```

Nếu có thêm một tác vụ nghiệp vụ đi cùng event, transaction DB phải được thiết kế để xử lý nó đúng một lần theo event ID. `ON CONFLICT DO NOTHING` chỉ có ý nghĩa khi duplicate theo key là thao tác an toàn theo hợp đồng.

Test có thể gửi cùng event ID hai lần và chờ:

```java
await()
    .atMost(Duration.ofSeconds(15))
    .untilAsserted(() ->
        assertEquals(1L,
            jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM processed_event WHERE event_id = ?",
                Long.class, "evt-500")));
```

Sau đó cần kiểm tra **số lần side effect thực tế** nếu consumer còn gọi dịch vụ bên ngoài, không chỉ count row.

### 9.3. At-least-once và ranh giới Kafka/DB

```text
Consumer poll event E
         |
         v
DB transaction commits event E
         |
         X  app crashes before offset commit
         |
         v
Consumer restarts and receives E again
```

Trong chuỗi này, Kafka có thể phát lại event; đó là đặc tính thực tế của at-least-once processing. Transaction producer Kafka hoặc commit offset Kafka **không tự tạo một transaction nguyên tử với một PostgreSQL database bên ngoài**.

Vì vậy, trong hầu hết consumer cập nhật database:

- Dùng business/event key ổn định.
- Đảm bảo DB write idempotent.
- Commit offset theo semantics listener phù hợp, **sau** business handling thành công.
- Nếu cần phát event khác, cân nhắc transactional outbox.
- Test crash windows và duplicate replay, không chỉ test happy path.

---

## 10. Retry và dead-letter topic: test phải quan sát kết quả cuối

### 10.1. Poison message là gì?

Một message có payload sai kiểu, thiếu field bắt buộc hoặc vi phạm invariant khiến listener liên tục ném exception:

```text
Kafka topic
  |
  +-- record A: valid  -> processed
  +-- record B: poison -> exception
  +-- record C: valid  -> bị kẹt nếu B retry vô hạn
```

Mục tiêu là **retry có hạn**, sau đó chuyển B sang DLT (hoặc cơ chế recovery đã định), để C có thể được xử lý mà không mất record B khỏi khả năng điều tra.

### 10.2. Cấu hình `DefaultErrorHandler`

Trong Spring Kafka 3.x, một cấu hình phổ biến là:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaErrorHandlingConfig {

    @Bean
    DefaultErrorHandler commonErrorHandler(
            KafkaTemplate<String, String> template) {

        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                template,
                (record, exception) ->
                    new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()));

        // Hai lần retry sau attempt đầu: tổng tối đa
        // ba lần thử xử lý record với cấu hình này.
        return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(100L, 2L));
    }
}
```

Cần tạo topic `orders.fail.it` và `orders.fail.it.DLT`. Với resolver giữ nguyên partition gốc, DLT phải có **ít nhất số partitions tương ứng** của source. Ví dụ một partition của source và một partition của DLT sẽ đơn giản cho test.

### 10.3. Listener chủ động ném lỗi

```java
@KafkaListener(
    id = "failing-order-listener",
    topics = "orders.fail.it",
    groupId = "orders-fail-it"
)
public void listen(ConsumerRecord<String, String> record) {
    if ("POISON".equals(record.value())) {
        throw new IllegalArgumentException(
            "Unprocessable payload");
    }

    // Business processing bình thường
}
```

Đoạn code là một method trong bean được Spring quản lý, không phải standalone method bên ngoài class.

### 10.4. Test scenario

```text
topic: orders.fail.it
DLT:   orders.fail.it.DLT

Send key=order-bad, value=POISON
    |
    v
Listener throws
    |
    v
DefaultErrorHandler retry với budget đã cấu hình
    |
    v
DeadLetterPublishingRecoverer publishes DLT record
    |
    v
Consumer test đọc DLT:
  key = order-bad
  value = POISON
  header chứa thông tin lỗi/original topic tùy version
```

Với `@EmbeddedKafka`:

```java
@EmbeddedKafka(
    partitions = 1,
    topics = {
        "orders.fail.it",
        "orders.fail.it.DLT"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

Một test có thể tạo consumer riêng cho DLT trước khi gửi poison message:

```java
Map<String, Object> props =
    KafkaTestUtils.consumerProps(
        "dlt-probe-" + UUID.randomUUID(),
        "false", embeddedKafka);

try (Consumer<String, String> dltConsumer =
        new DefaultKafkaConsumerFactory<>(
            props,
            new StringDeserializer(),
            new StringDeserializer()).createConsumer()) {

    embeddedKafka.consumeFromAnEmbeddedTopic(
        dltConsumer, "orders.fail.it.DLT");

    publisher.publish(
        "orders.fail.it",
        "order-bad",
        "POISON"
    ).get(10, TimeUnit.SECONDS);

    var dlt = KafkaTestUtils.getSingleRecord(
        dltConsumer,
        "orders.fail.it.DLT",
        Duration.ofSeconds(20));

    assertEquals("order-bad", dlt.key());
    assertEquals("POISON", dlt.value());
}
```

**Phần cần setup kèm theo:** bean listener, bean `DefaultErrorHandler`, serializer/deserializer String và hai topics đều phải thuộc cùng Spring test context. Test như trên minh họa cấu trúc assertion, không chỉ chạy standalone fragment.

### 10.5. Không nhầm broker ack với listener recovery

`KafkaTemplate.send(...).get(...)` thành công chỉ nói **record đầu vào được broker chấp nhận**. DLT record xuất hiện chứng minh recovery path có hoạt động. Nếu cần đảm bảo message đã được consumer xử lý đúng sau retry hoặc được đưa vào DLT, phải assert một trong các kết quả này, **không dựa vào send future**.

### 10.6. Cần test loại lỗi và số attempts

Một test reliability nên còn đo:

- Listener bị gọi bao nhiêu lần cho poison message.
- Retry có backoff hoặc chính sách không retry với lỗi cố định.
- DLT nhận đúng một logical record theo event ID.
- Header original topic/partition/offset và exception metadata nếu cần audit.
- Record hợp lệ sau poison vẫn được xử lý theo chính sách.
- Nếu DLT không khả dụng, error handler xử lý recovery failure ra sao.
- Trường hợp deserialization lỗi ngay **trước listener**, có dùng `ErrorHandlingDeserializer`/handling path riêng hay không.

Các kết quả trên cần được xác nhận bằng behavior của Spring Kafka version đang triển khai; đừng giả định mọi exception đều đi qua cùng một listener error handler.

---

## 11. Lỗi deserialization không giống lỗi trong listener

### 11.1. Tại sao listener chưa được gọi?

Pipeline thông thường:

```text
Kafka bytes
    |
    v
Deserializer
    |
    +-- failure trước khi tạo object
    |
    v
ConsumerRecord<K,V>
    |
    v
@KafkaListener
    |
    +-- business exception
```

Một `JsonDeserializer` có thể không tạo được object do payload lỗi. Nếu sử dụng trực tiếp deserializer và không có cơ chế bắt lỗi phù hợp, listener method không nhận record; test ném exception ở listener không mô phỏng được giai đoạn này.

### 11.2. `ErrorHandlingDeserializer`

Spring Kafka cung cấp `ErrorHandlingDeserializer` để giữ thông tin lỗi deserialize trong header và cho phép container error handling xử lý theo cách được cấu hình.

Ví dụ property mang tính mô tả:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
```

Khi dùng JSON, cần cấu hình type mapping/trusted packages phù hợp schema của ứng dụng, không bật trusted packages `*` vô điều kiện trong môi trường nhận input không tin cậy.

### 11.3. Ca integration cần có

Test một payload invalid JSON:

1. Producer gửi bytes không parse được.
2. Consumer được cấu hình `ErrorHandlingDeserializer`.
3. Xác minh listener business không coi payload đó là object hợp lệ.
4. Error handler đưa record vào DLT hoặc theo chính sách recovery.
5. Assert DLT lưu payload/headers theo thiết kế, không làm partition kẹt vô hạn.

**Giới hạn:** cách serialize payload DLT khi value deserialize thất bại có thể cần producer hỗ trợ `byte[]` và JSON hoặc configuration phù hợp. Không mặc định `KafkaTemplate<String,String>` luôn ghi được mọi failed record bytes. Trong integration suite thực, thiết kế recoverer/serializer map phù hợp cả payload hợp lệ và payload chưa deserialize.

---

## 12. Kiểm thử offset, replay và delivery semantics

### 12.1. Offset là của consumer group

Một topic có nhiều partitions; mỗi group theo dõi committed offset riêng cho từng partition:

```text
topic orders.events partition 0
  offset 0: E1
  offset 1: E2
  offset 2: E3
  offset 3: E4

group = orders-projection
  committed offset = 2
  => sau restart có thể xử lý từ offset 2
     (next record theo semantics commit offset)
```

Kafka commit offset biểu diễn **vị trí tiếp theo cần đọc** trong từng partition, không trực tiếp là “message ID đã được xử lý duy nhất”.

### 12.2. Test replay do crash window

Một scenario có ý nghĩa:

```text
E1 -> listener receives
   -> business DB commit successful
   -> process killed before offset commit
   -> listener restarts with same group
   -> E1 may be delivered again
```

Test cần xác định:

- Kafka offset chưa commit ở thời điểm crash.
- Consumer group cũ sau restart đọc lại E1.
- Handler dựa vào unique `eventId`, không tạo duplicate business row.
- Nếu có downstream event, không phát hai business effects ngoài contract.

Không chỉ gọi listener method hai lần bằng Mockito rồi kết luận end-to-end at-least-once; phải có Kafka consumer group và trạng thái offset thật ở ít nhất một integration test.

### 12.3. Ack mode và commit timing

Spring Kafka listener container hỗ trợ các ack modes như `RECORD`, `BATCH`, `MANUAL` và `MANUAL_IMMEDIATE`. Cách commit offset khác nhau theo cấu hình, consumer transaction và error handler.

Ví dụ khi dùng manual ack:

```yaml
spring:
  kafka:
    listener:
      ack-mode: manual_immediate
```

Listener có thể nhận `Acknowledgment`:

```java
@KafkaListener(
    topics = "orders.manual.it",
    groupId = "orders-manual-it"
)
public void onMessage(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    businessService.persistIdempotently(record);
    acknowledgment.acknowledge();
}
```

Import:

```java
import org.springframework.kafka.support.Acknowledgment;
```

Chỉ ack **sau** khi business operation thành công theo hợp đồng. Nhưng ack và database commit vẫn là hai hệ thống khác nhau; crash ở ranh giới có thể tạo replay. Kiểm thử phải dựa vào idempotency thay vì giả định exactly-once toàn hệ thống.

### 12.4. Khi nào cần `seek` trong test?

Để kiểm tra replay một record đã nằm ở offset cụ thể, test có thể assign partition và `seek` về offset mong muốn. Khi làm vậy, consumer thủ công không mô phỏng đầy đủ group rebalance/commit, nên cần một test khác chạy consumer group thật.

Phân biệt rõ:

- **Seek test:** kiểm tra handler có idempotent khi record được đọc lại.
- **Group restart test:** kiểm tra lifecycle offset commit, assignment, rebalance.
- **Broker failover test:** kiểm tra recovery khi broker leader đổi hoặc connection mất.

Không dùng một seek test làm bằng chứng cho cả ba.

---

## 13. Kiểm thử ordering, partition và concurrency

### 13.1. Kafka chỉ bảo đảm order trong một partition

Ví dụ:

```text
Topic orders.events, 3 partitions:

partition 0: E1 -> E4 -> E7
partition 1: E2 -> E5
partition 2: E3 -> E6
```

Consumer cùng group có thể xử lý các partitions song song. Kafka không bảo đảm thứ tự tổng quát giữa partitions. Nếu business rule cần các event của cùng order đi theo thứ tự, producer nên sử dụng **cùng key** cho các events của order đó để route ổn định vào một partition.

### 13.2. Test giữ thứ tự cho một key

Một scenario:

1. Tạo topic 3 partitions.
2. Gửi `ORDER_CREATED`, `ORDER_PAID`, `ORDER_SHIPPED` cùng key `order-777`.
3. Chờ consumer nhận đủ.
4. Assert thứ tự của ba records cùng key theo offset trong partition.
5. Kiểm tra chúng nằm cùng một partition.

Không kiểm tra “tổng thứ tự” của các records khác key ở nhiều partitions; đó không phải guarantee chung của Kafka.

### 13.3. Test concurrency và rebalance

Với `@KafkaListener(concurrency = "3")` trên topic ba partitions, số consumer instances tối đa có thể hoạt động đồng thời. Nhưng test phải xét:

- Consumer group assignment.
- Partition count thực tế.
- Thời điểm listeners bắt đầu và join group.
- Listener thread safety.
- Shared DB writes/unique constraints.
- Rebalance khi thêm/bớt consumer.

Tăng concurrency không làm một partition tự chia record cho nhiều consumers **cùng một group** xử lý song song tùy ý; mỗi partition được assign cho một consumer trong group tại một thời điểm theo group protocol.

### 13.4. Retry có thể ảnh hưởng tiến độ partition

Nếu record đầu tiên ở một partition liên tục fail và error handler seek/retry, các records sau cùng partition có thể bị chậm. Test không nên chỉ assert DLT của poison record; nên gửi thêm record hợp lệ sau nó và xác nhận tiến độ được khôi phục theo policy.

---

## 14. Test producer reliability: ack, timeout và duplicate

### 14.1. Những cấu hình cần hiểu

```yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 5
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
```

Đây là cấu hình minh họa, không phải giá trị tối ưu cho mọi workload. Với Kafka client hiện đại, idempotent producer có thể được bật mặc định khi cấu hình cho phép; cấu hình tường minh giúp người học nhận diện mục tiêu.

- `acks=all`: leader chờ số replicas trong ISR theo broker/topic policy.
- `enable.idempotence=true`: giảm duplicate do producer retries trong phạm vi Kafka producer session/sequence semantics.
- `retries`: retry lỗi retriable cho phép.
- `delivery.timeout.ms`: giới hạn thời gian tổng thể producer dành cho delivery, bao gồm retry theo client semantics.
- `max.in.flight.requests.per.connection` liên quan ordering và idempotence.

### 14.2. Single-broker không chứng minh replication

Trong Testcontainers một broker, topic `replicas=1`. `acks=all` ở đây chỉ nhận ack theo ISR duy nhất hiện có; không thể chứng minh dữ liệu tồn tại khi **một broker khác** failover.

Muốn test mất broker leader nhưng hệ thống tiếp tục hoạt động, phải tạo cluster nhiều brokers, replication factor phù hợp, `min.insync.replicas` thực tế và có cơ chế kiểm tra leader/ISR.

### 14.3. Producer idempotence không thay thế consumer idempotence

Producer idempotence giúp tránh một số duplicate do producer retry cùng record. Nhưng application gọi `send` hai lần vì HTTP request được gửi lại vẫn có thể tạo hai business events. Consumer replay sau commit offset failure cũng có thể gây xử lý lặp. Vì vậy business event ID và database uniqueness vẫn quan trọng.

---

## 15. Testcontainers cho failure injection

### 15.1. Những loại fault cần mô phỏng

| Fault | Tại sao cần | Điều cần assert |
| --- | --- | --- |
| Broker chưa sẵn sàng lúc startup | Producer/consumer kết nối muộn | Application không báo success giả, có retry hoặc readiness phù hợp |
| Broker tạm không truy cập được | Network timeout | Producer future báo lỗi/timeout đúng, consumer phục hồi theo budget |
| Broker restart | TCP connections bị cắt | Client tái kết nối, không đánh mất event theo retention/offset |
| DB tạm unavailable | Consumer persist thất bại | Không ack sai; retry/replay idempotent |
| Listener process chết | Offset chưa commit | Record được replay, output không trùng |
| Poison message | Handler liên tục ném exception | Retry exhausted → DLT, sau đó tiếp tục |
| Rebalance | Consumer membership thay đổi | Assignment/offset đúng, không xử lý sai do state chia sẻ |
| DLT producer thất bại | Recovery path không khả dụng | Không silently commit offset/mất record |
| Network latency cao | Request/response chậm | Timeout, backoff và SLA đúng |

### 15.2. Dùng Toxiproxy khi cần cắt network

Một mô hình nhiều container:

```text
Spring application
        |
        v
   Toxiproxy
    /    \
   /      \  latency, bandwidth limit,
  /        \ connection cut
 v
Kafka broker
```

Testcontainers hỗ trợ Toxiproxy container để đưa fault vào đường TCP. Nhưng Kafka có **advertised listeners**: client lấy bootstrap metadata rồi có thể kết nối trực tiếp đến địa chỉ broker được quảng bá, bỏ qua proxy nếu topology cấu hình sai.

Vì vậy, test network partition với Kafka cần thiết kế đúng advertised endpoints và đường đi client/broker. Chỉ proxy bootstrap port không bảo đảm mọi connection sau đó đi qua proxy.

### 15.3. Không dừng rồi khởi động lại container tùy tiện

Nếu `KafkaContainer` bị `stop()` rồi `start()` giữa một test, Docker có thể gán **mapped host port khác**. Spring context đã nhận bootstrap address cũ từ `@DynamicPropertySource` khi khởi tạo; client đang kết nối endpoint cũ có thể không phục hồi.

Khi thử broker restart:

- Dùng fault injection không làm thay đổi advertised endpoint, hoặc
- Khởi động lại Spring context/datasource clients khi endpoint thay đổi, hoặc
- Dựng network topology cố định trong Docker và kiểm tra connectivity theo cách phù hợp.

Đừng coi test container lifecycle sai là lỗi Kafka retry.

### 15.4. Dùng timeout hữu hạn

Trong fault injection, một producer send hoặc consumer poll có thể block đến timeout. Test phải đặt thời hạn rõ:

```java
var future = publisher.publish(
    "orders.container.it", "order-x", "DATA");

assertThrows(
    java.util.concurrent.TimeoutException.class,
    () -> future.get(100, TimeUnit.MILLISECONDS));
```

Đây chỉ là **minh họa dạng assertion**: với Kafka client và máy CI cụ thể, send có thể hoàn tất nhanh hoặc lỗi theo kiểu khác; không nên chọn timeout 100 ms như một sự thật về broker outage. Test ổn định phải điều khiển fault, biết thời điểm endpoint bị cắt và assert loại outcome được thiết kế (thành công, failure hay deadline exceeded) theo SLA của ứng dụng.

---

## 16. Kiểm thử transactions và exactly-once một cách chính xác

### 16.1. Kafka transaction dùng cho Kafka records/offsets

Spring Kafka hỗ trợ transactional producer và listener container để phối hợp Kafka transactions trong những flow phù hợp, ví dụ consume một topic và publish sang topic khác cùng Kafka transaction.

Để thử transactional producer trong **single-broker test**, internal transaction state topic thường cần cấu hình replication factor và ISR phù hợp với một broker:

```java
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.tx.input", "orders.tx.output"},
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1",
        "offsets.topic.replication.factor=1"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

Spring Kafka transaction configuration còn cần transaction ID prefix và listener container transaction manager/transactional producer phù hợp phiên bản. Không bật một vài brokerProperties rồi tự coi job đã có exactly-once processing.

### 16.2. Test consumer `read_committed`

Với Kafka transactional records, consumer đọc bằng:

```yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
```

Test nên phân biệt:

- Transaction commit: record xuất hiện với `read_committed`.
- Transaction abort: record không xuất hiện với `read_committed`.
- Kafka-to-Kafka processing: output records và consumed offsets được commit theo cùng Kafka transaction khi cấu hình EOS đúng.
- Business database khác Kafka: không có atomicity tự động giữa Kafka transaction và PostgreSQL local transaction.

### 16.3. Exactly-once không phải “mọi side effect đúng một lần”

Kafka EOS bảo vệ một phạm vi nhất định của Kafka transaction. Nếu consumer gửi email hoặc tạo payment ở remote API rồi crash, Kafka transaction không tự hoàn tác email/payment. Test reliability phải cụ thể hóa “exactly-once” là:

- Exactly-once **Kafka output records** trong một processing topology hỗ trợ.
- At-least-once delivery với **idempotent DB projection**.
- Exactly-once **business effect** theo idempotency key được hệ thống đích hỗ trợ.

Không dùng một single-broker embedded test để khẳng định mọi side effect trong production đã đúng một lần.

---

## 17. Làm test lặp lại được: chống flaky integration tests

### 17.1. Những nguyên nhân flaky thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Producer send thành công nhưng listener chưa nhận | Consumer chưa được assign | `ContainerTestUtils.waitForAssignment` hoặc condition wait |
| Consumer bỏ qua message gửi trước | `auto.offset.reset=latest`, group mới subscribe muộn | `earliest` cho fixture hoặc assign trước send |
| Test đọc record của test trước | Topic/group dùng chung | Topic fixture riêng, consumer group mới |
| Test nhận hai records không mong đợi | Retry/replay hoặc leftover topic | Assert theo event ID, isolation và cleanup |
| Test treo vô hạn | Poll/get không timeout | Timeout hữu hạn, fail có chẩn đoán |
| CI không có Docker | Container không start | Docker-enabled runner, tách integration suite |
| Testcontainers image pull quá chậm | Image chưa cache/network yếu | Pin image, cache Docker layers khi có thể |
| Context dùng Kafka localhost:9092 | Bootstrap property không override | `bootstrapServersProperty` hoặc `@DynamicPropertySource` |
| DLT test không nhận record | Topic/partition thiếu, serializer sai | Tạo DLT, kiểm tra recoverer/factory |
| JSON deserialize lỗi trước listener | Error handler không xử lý deserialization stage | `ErrorHandlingDeserializer` và DLT serializer phù hợp |
| Tests tác động nhau | Shared Spring context/broker state | Fixtures độc lập; `@DirtiesContext` có chọn lọc |
| Test assertion quá sớm | Kafka async | Poll/latch/Awaitility theo điều kiện |
| Test chạy pass local, fail trên CI load cao | Threshold timing cứng, CPU throttling | Timeout có biên, quan sát assignment/readiness |
| Broker stop/start làm đổi endpoint | Docker mapped port đổi | Stable proxy hoặc khởi tạo context mới |
| Test ordering sai | So sánh toàn topic nhiều partitions | Assert per partition/per key |
| Container test bị skip không ai biết | `disabledWithoutDocker=true` | Bắt buộc Docker ở CI critical suite |

### 17.2. Dùng event ID để tránh assert nhầm

Không assert “listener received one message bất kỳ”. Nên gửi key/event ID riêng:

```java
String eventId = "it-" + UUID.randomUUID();
publisher.publish(TOPIC, eventId, "CREATED");
```

Consumer test tìm đúng key này. Tuy nhiên, một ID ngẫu nhiên **trong một test** để cô lập fixture khác với việc dùng UUID tùy tiện làm business event identity ở production. Business event ID thực phải ổn định qua retries/replays.

### 17.3. Chọn thời điểm tạo topic và listener

Khi dùng `@EmbeddedKafka(topics=...)`, broker tạo topic trước khi test method chạy. Khi dùng Testcontainers + `NewTopic`, KafkaAdmin tạo topic lúc application context start. Test cần bảo đảm **topic đã tồn tại** trước khi gửi nếu auto-create bị tắt.

Listener đã có bean không có nghĩa partition assignment đã hoàn tất. Nếu test cần đồng bộ với listener, chờ readiness qua registry/container trước khi gửi.

### 17.4. Test không được dựa vào thứ tự thực thi của JUnit

Một test setup topic và method khác đọc topic có thể fail khi chạy riêng. Mỗi test nên tự setup prerequisite, hoặc dùng lifecycle `@BeforeAll`/`@BeforeEach` rõ ràng. Khi chạy song song, dùng isolation theo class/topic/group để không có trạng thái dùng chung gây race.

### 17.5. Assert cuối cùng qua output có ý nghĩa

Cho consumer chuyển event thành database projection:

```text
Test gửi event E
  |
  v
Kafka listener xử lý async
  |
  v
Đợi database projection được cập nhật
  |
  v
Assert business key + fields + unique count
```

Điều này đáng tin hơn assert một flag boolean trong listener bị test tự set mà không đi qua logic persist thực tế.

---

## 18. Tổ chức test suite và CI

### 18.1. Nhóm theo mục tiêu

Một cấu trúc hợp lý:

```text
src/test/java/
  Unit:
    OrderMapperTest
    ValidationRuleTest

  Embedded integration:
    EmbeddedKafkaIntegrationTest
    ListenerIntegrationTest
    KafkaDltIntegrationTest

  Container integration:
    KafkaContainerIntegrationTest
    KafkaPostgresIntegrationTest

  Reliability/fault injection:
    KafkaOutageIT
    KafkaConsumerReplayIT
    BrokerFailoverIT
```

Lưu ý tên `*IT` là convention để phân biệt integration tests; Gradle mặc định không tự tạo nguồn/chế độ chạy riêng chỉ dựa trên tên. Nếu muốn test task độc lập (`integrationTest`), phải cấu hình sourceSets/tasks rõ và CI invoke đúng.

### 18.2. Chiến lược chạy

| Lúc chạy | Test đề xuất | Lý do |
| --- | --- | --- |
| Mỗi lần lưu code/PR nhỏ | Unit + Embedded Kafka chọn lọc | Phản hồi nhanh |
| Pull request vào main | Unit + Embedded + Kafka container | Phát hiện lỗi wiring/dependency |
| Trước release | Kafka + DB + DLT/replay/transaction scenarios | Chứng minh failure paths |
| Theo lịch/nightly | Multi-container chaos, network failures, broker restarts | Chi phí cao và nhiều điều kiện |
| Staging/preproduction | ACL, TLS, multi-broker, retention, ISR, load | Tiệm cận production topology |

Không nên để mọi test phụ thuộc một Kafka broker dùng chung giữa nhiều CI jobs; điều đó tăng rủi ro dữ liệu test chồng lấn và khó debug.

### 18.3. Docker image và version

Pin image thay vì dùng `latest`:

```java
DockerImageName.parse("confluentinc/cp-kafka:7.6.1")
```

Điều này giúp test chạy nhất quán khi upstream phát hành Kafka image mới. Nhưng cũng cần **chủ động nâng phiên bản theo kế hoạch** để phát hiện client/broker compatibility issues; pin vĩnh viễn không phải chiến lược bảo đảm an toàn.

### 18.4. Tối ưu thời gian CI

- Dùng static container cho cả test class khi các methods có isolation tốt.
- Không startup Docker cho unit test.
- Dùng một Kafka container chung cho một integration class nếu phù hợp.
- Giảm số lần tạo Spring context khi không cần.
- Dùng Awaitility và chờ assignment thay cho sleep dài.
- Sử dụng cached Docker images trên runner khi chính sách cho phép.
- Chỉ bật Testcontainers reusable containers trên developer machine khi hiểu rủi ro state leakage; không coi reusability là mặc định an toàn của CI.

### 18.5. Thu thập evidence khi test fail

Một integration failure report hữu ích gồm:

- Topic, partition, offset và key/event ID của record.
- Container logs và Kafka broker errors.
- Consumer group/assignment và committed offsets nếu liên quan.
- Spring Kafka listener exception stack trace.
- Retry attempts, DLT topic/headers.
- DB row state, transaction outcome, idempotency checks.
- Versions Java, Boot, Spring Kafka, Kafka image và Testcontainers.
- Timeout và thời điểm fault injection.

Tránh xuất secrets, full PII payload và credential từ container logs vào CI artifacts công khai.

---

## 19. Một ma trận kiểm thử tin cậy thực dụng

Đừng cố gọi một test “reliability test” rồi mong bao phủ hết. Một ma trận cho hệ thống xử lý order events:

| ID | Scenario | Môi trường | Assertion cốt lõi |
| --- | --- | --- | --- |
| R01 | Producer gửi String record | Embedded | Broker nhận đúng topic/key/value |
| R02 | `@KafkaListener` nhận event | Embedded | Listener business side effect đúng |
| R03 | JSON payload hợp lệ | Embedded/container | Deserialize thành domain object |
| R04 | JSON invalid | Embedded | Error handler/DLT nhận failed bytes/headers đúng |
| R05 | Listener lỗi transient rồi thành công | Embedded | Attempts hữu hạn; output đúng |
| R06 | Poison record exhausted | Embedded | DLT có record, không kẹt partition vô hạn |
| R07 | Listener crash sau DB commit | Kafka + PostgreSQL | Replay không nhân đôi DB business effect |
| R08 | Broker mất kết nối ngắn | Container + proxy | Client hồi phục hoặc fail theo SLA |
| R09 | Broker unavailable lâu | Container + proxy | Timeout/backoff, không nhận success giả |
| R10 | Same key gửi nhiều events | 3-partition broker | Per-key ordering |
| R11 | Consumer rebalance | Container/multi-consumer | Assignment và offset không bỏ record |
| R12 | Kafka transaction abort | Transaction-enabled broker | Consumer `read_committed` không thấy aborted output |
| R13 | DLT không khả dụng | Broker/container fault | Không silently mất record |
| R14 | Deployment compatibility | Image/cluster version matrix | Client/serializer/schema tương thích |
| R15 | Cluster leader failover | Multi-broker Kafka | Recovery và durability theo ISR policy |

Không phải mọi scenario được kiểm tra đủ bằng single-node Embedded Kafka. Cần chọn đúng độ chân thực của môi trường test theo dòng ma trận.

---

## 20. Dự án thực hành: bài tập theo cấp độ

### Bài 1 — Test producer trên Embedded Kafka

Tạo `OrderPublisher` gửi record đến `orders.embedded.it`. Dùng `@EmbeddedKafka` và consumer test riêng.

Yêu cầu:

- Bootstrap address phải lấy từ embedded broker.
- Assert topic/key/value.
- Gửi nhiều records khác key để quan sát partition.
- Không sử dụng `Thread.sleep`.
- Consumer đóng sau test.

### Bài 2 — Test listener với dữ liệu nghiệp vụ

Viết `@KafkaListener` nhận `OrderEvent` và gọi repository lưu trạng thái. Dùng `@EmbeddedKafka` và test `await().untilAsserted(...)` trên repository.

Yêu cầu: dữ liệu persisted đúng, listener assignment sẵn sàng và test không phụ thuộc vào thứ tự test methods.

### Bài 3 — Chuyển test sang Testcontainers

Thay Embedded Kafka bằng `KafkaContainer` và `@DynamicPropertySource`. Khai báo `NewTopic` trong test config.

Yêu cầu:

- Image Kafka cố định.
- Không hardcode `localhost:9092`.
- Test chạy được trên Docker CI runner.
- Khi thiếu Docker, quyết định fail hay skip theo chính sách suite.

### Bài 4 — Retry rồi DLT

Listener ném exception khi payload bằng `POISON`. Cấu hình `DefaultErrorHandler` và `DeadLetterPublishingRecoverer`.

Yêu cầu:

- Attempts hữu hạn.
- DLT nhận đúng key/value.
- Header truy vết phù hợp.
- Record hợp lệ phía sau vẫn được xử lý.
- Không hardcode sleep để chờ DLT.

### Bài 5 — DLT cho deserialize failure

Producer gửi invalid JSON bytes; consumer dùng `ErrorHandlingDeserializer`. Cấu hình recoverer và serializer DLT phù hợp.

Yêu cầu: listener business không nhận object sai, DLT giữ thông tin đủ để phân tích, và consumer không retry vô hạn.

### Bài 6 — Idempotent DB projection

Dùng Kafka + PostgreSQL Testcontainers. Viết listener lưu `eventId` vào bảng có unique constraint; gửi cùng event ID hai lần.

Yêu cầu: chỉ có một business record; test cả replay sau simulated crash trước offset commit.

### Bài 7 — Ordering theo key

Tạo topic ba partitions. Gửi `CREATED`, `PAID`, `SHIPPED` cho cùng order key. Assert thứ tự theo offset và không yêu cầu ordering giữa các keys ở partitions khác.

### Bài 8 — Broker/network outage

Dùng Kafka Testcontainers và một fault-injection proxy được cấu hình đúng advertised listeners. Ngắt mạng trong lúc producer gửi.

Yêu cầu: app báo đúng trạng thái, retry/backoff có giới hạn, và sau phục hồi record/DB output được đối soát theo event ID.

### Bài 9 — Transactional Kafka flow

Tạo processor consume topic A, publish topic B trong Kafka transaction, có record gây exception. Test `read_committed` chỉ thấy committed outputs và offsets theo cấu hình EOS.

Giải thích ranh giới với PostgreSQL/HTTP side effects, không tuyên bố exactly-once cho các hệ thống bên ngoài.

### Bài 10 — Chạy test trên CI

Tách nhóm Embedded Kafka và Testcontainers. Đặt timeouts, logs, versions và cách cache Docker images. Cố ý làm một test fail để kiểm tra artifact/log có đủ dữ liệu debug.

---

## 21. Checklist trước khi tin một integration test Kafka

- [ ] Test khởi động Kafka broker thật, không vô tình kết nối broker ngoài môi trường.
- [ ] Bootstrap servers đến từ `@EmbeddedKafka` hoặc Testcontainers, không hardcode port.
- [ ] Topics và partitions tạo deterministically.
- [ ] Consumer group/offset isolation rõ, không nhiễm records từ test khác.
- [ ] Test đồng bộ với listener readiness hoặc chờ business output bằng timeout.
- [ ] Không phụ thuộc fixed sleep hay JUnit method ordering.
- [ ] Assert không chỉ producer ack mà còn **consumer effect** khi cần.
- [ ] Kiểm tra success, transient failure, permanent failure và DLT.
- [ ] Có test replay/duplicate và business idempotency.
- [ ] Không đồng nhất `acks=all` trên một broker với replication durability.
- [ ] Ranh giới Kafka transaction và DB transaction được mô tả rõ.
- [ ] Nếu test network fault, advertised listeners thực sự đi qua đường fault injection.
- [ ] Container logs và exception context có thể thu thập khi CI fail.
- [ ] Versions Kafka client/broker, Spring Kafka và Testcontainers được kiểm soát.
- [ ] Các bài kiểm thử security, failover nhiều broker và tải nặng được đặt ở tầng phù hợp.

## 22. Tổng kết

**Embedded Kafka** phù hợp để kiểm tra nhanh và thật luồng Spring Kafka `KafkaTemplate → broker → consumer/@KafkaListener`, đặc biệt khi cần một test suite gọn, không phụ thuộc Docker. **Testcontainers** cung cấp broker chạy trong Docker và là nền tảng thuận tiện để thêm database, network proxy và các thành phần phân tán vào integration tests.

Đối với reliability, câu hỏi cuối cùng không phải “test đã nhận được message chưa”, mà là:

- Khi listener lỗi, message được retry rồi xử lý đúng hay chuyển đến DLT?
- Khi crash ở ranh giới commit, dữ liệu nghiệp vụ có bị ghi trùng?
- Khi broker hoặc database mất kết nối, ứng dụng có timeout, retry và phục hồi có giới hạn?
- Khi consumer group rebalance, có giữ đúng ordering theo partition và không mất sự kiện?
- Khi test chạy lại trên CI, kết quả có ổn định và đủ evidence để debug?

Một hệ thống Kafka đáng tin cậy cần **nhiều lớp test**, mỗi lớp chứng minh đúng phạm vi của nó. Embedded Kafka và Testcontainers không thay thế nhau hoàn toàn; chúng bổ sung cho nhau để tìm lỗi trước khi lỗi xuất hiện trên production.

## 23. Tài liệu tham khảo

- [Spring for Apache Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `EmbeddedKafkaBroker`, `KafkaTestUtils` và listener test.
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler` và recoverers.
- [Spring for Apache Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): `@RetryableTopic` và retry/DLT topology.
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): Kafka transactions và exactly-once phạm vi Kafka.
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): Kafka auto-configuration và properties.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và container test setup.
- [Testcontainers for Java — Kafka Module](https://java.testcontainers.org/modules/kafka/): `KafkaContainer`, `ConfluentKafkaContainer` và image compatibility.
- [Testcontainers for Java — Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/): network fault injection.
- [Apache Kafka Documentation — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): group IDs, offset reset và isolation level.
- [Apache Kafka Documentation — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): acks, retries, idempotence và delivery timeout.
