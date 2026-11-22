# Embedded Kafka và Kafka trong Testcontainers

## 1. Mục tiêu: kiểm thử Kafka đến đâu là đủ?

Trong Spring Boot, một nghiệp vụ thường dùng `KafkaTemplate` để gửi sự kiện và `@KafkaListener` để tiêu thụ sự kiện bất đồng bộ. Test đơn giản bằng Mockito có thể xác nhận method `send` được gọi, nhưng không thực hiện Kafka protocol, không tạo record trong topic và không chạy consumer. Vì vậy, một test chỉ verify mock **không phát hiện** sai bootstrap server, topic, serializer, consumer group, partition assignment hoặc listener không đăng ký thành công.

Có hai cách chạy một broker Kafka thật trong test:

- **Embedded Kafka:** module `spring-kafka-test` chạy broker cùng môi trường kiểm thử, được cấu hình bằng `@EmbeddedKafka`. Không cần Docker trong trường hợp thông thường.
- **Kafka Testcontainers:** module Testcontainers chạy Kafka trong Docker-compatible container, dùng image/version broker được chỉ định. Spring Boot có thể lấy bootstrap servers từ `@ServiceConnection`.

Hai giải pháp không thay thế nhau hoàn toàn. Embedded Kafka phù hợp Kafka integration test tương đối nhẹ. Kafka Testcontainers thích hợp kiểm tra sự tương thích của client với Kafka chạy trong image/container và ghép nhiều services trong cùng môi trường. Cả hai đều thường là **single-broker test**, không tự chứng minh availability, replication, security hay hiệu năng production cluster.

### Bạn sẽ học được

1. Phân biệt unit test, Kafka broker integration test và infrastructure/cluster test.
2. Hiểu producer acknowledgment khác với listener/business processing.
3. Dùng `@EmbeddedKafka(kraft=true)` trong Spring Kafka 3.3.
4. Dùng `ConfluentKafkaContainer` với Testcontainers 1.21.x và `@ServiceConnection` của Spring Boot 3.5.
5. Tạo topic với `NewTopic`/KafkaAdmin, kết nối KafkaTemplate và KafkaListener bằng cấu hình test.
6. Chờ listener được assign partition, tránh `Thread.sleep` gây flaky test.
7. Kiểm tra record key/value, Unicode, correlation header, topic, partition và offset.
8. Kiểm tra thứ tự messages **trong cùng partition**, không suy ra global order.
9. Thiết kế test đúng với consumer groups, offsets, retry, DLT và Kafka transactions.
10. Chạy ví dụ Java 17+ gồm **7 JUnit Jupiter tests** sử dụng cùng production code ở hai broker khác nhau.

**Phạm vi phiên bản:** ví dụ nhắm **Java 17+, Spring Boot 3.5.x, Spring Kafka 3.3.x và Testcontainers 1.21.x**. Trong nhánh này, Boot quản lý `spring-kafka` và Testcontainers qua BOM. Với Spring Boot 4, Spring Kafka 4 hoặc Testcontainers 2, cần xem lại import/package, dependency coordinates và khả năng tương thích broker.

## 2. Bản đồ các tầng kiểm thử

```text
Order business service
        │
        ▼
OrderEventPublisher (KafkaTemplate)
        │
        ▼
Kafka producer + serializer
        │
        ▼
  Kafka broker (topic, partition, offset)
        │
        ▼
Kafka consumer + deserializer
        │
        ▼
OrderEventReceiver (@KafkaListener)
        │
        ▼
Business processing / database / downstream
```

| Tầng | Công cụ | Giữ thật những gì? | Không kiểm chứng |
|---|---|---|---|
| Unit | Mockito/fake event port | Business rules, quyết định publish | Broker, serializer, listener, offsets |
| Embedded Kafka | `spring-kafka-test` | Kafka client + broker + listener | Container image, production network |
| Kafka container | Testcontainers Kafka | Client + broker trong Docker image | Multi-node replication, TLS/ACL nếu chưa cấu hình |
| Cluster fault test | Multi-broker/test environment | Leader changes, replication, failover | Tất cả production conditions |
| Staging/smoke | Kafka infrastructure được phép | Auth, network, deployment topology | Test luôn nhanh/độc lập |

**Quy tắc chọn:** mock ở ranh giới cao nhất không làm mất behavior cần kiểm chứng. Muốn test format message Kafka và callback listener, cần broker thật. Muốn test business branching, không cần khởi động Kafka. Muốn test controller/HTTP đầu vào, phải test thêm MVC/HTTP layer; broker test không tự kiểm tra inbound API.

## 3. Embedded Kafka là gì?

`org.springframework.kafka:spring-kafka-test` cung cấp `EmbeddedKafkaBroker`, `@EmbeddedKafka`, `KafkaTestUtils` và `ContainerTestUtils`. Khi có Spring TestContext như `@SpringBootTest`, annotation có thể tạo broker bean trong context. Producer/consumer dùng Kafka client APIs thật, chỉ thay Kafka bootstrap destination thành broker được khởi động cho test.

### 3.1. KRaft và ZooKeeper theo Spring Kafka 3.3

Spring Kafka 3.3 có hai implementation cho embedded broker:

- `EmbeddedKafkaZKBroker`: legacy dùng ZooKeeper.
- `EmbeddedKafkaKraftBroker`: dùng KRaft, được chọn bằng `kraft=true`.

Ví dụ ưu tiên KRaft:

```java
@EmbeddedKafka(
        kraft = true,
        partitions = 2,
        topics = "orders.events.embedded",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

Đây là snippet annotation, test đầy đủ nằm ở phần 9. Với Kafka mới, KRaft thay thế ZooKeeper; các phiên bản Spring Kafka mới có thể xóa cấu hình ZooKeeper. Đừng ghép ví dụ code Spring Kafka 3.3 vào Spring Kafka 4 mà không đọc API mới.

### 3.2. Bootstrap property

Spring Boot lấy địa chỉ Kafka ở `spring.kafka.bootstrap-servers`. Embedded Kafka tạo broker trên cổng thử nghiệm và có thể xuất địa chỉ vào property này thông qua `bootstrapServersProperty`. Trong Spring Kafka **3.0.10+**, giá trị mặc định của mapping cũng là `spring.kafka.bootstrap-servers`; khai báo explicit giúp tránh nhầm với tài liệu cũ chỉ dùng `spring.embedded.kafka.brokers`.

Chỉ thay bootstrap property **không tự sửa** những custom ProducerFactory/ConsumerFactory tự xây bằng code mà không đọc Spring Environment. Ví dụ trong bài sử dụng Boot auto-configuration để tất cả clients dùng broker của test.

### 3.3. Ưu điểm và giới hạn

Embedded Kafka không đòi Docker và thường thích hợp với CI không có container runtime. Nó xác minh path producer/consumer, Kafka topics và listener wiring. Tuy nhiên, broker được gói trong môi trường test, không đại diện Kafka container image, external Docker networking, ACL/TLS hoặc cluster nhiều brokers.

Spring Kafka hỗ trợ broker toàn JUnit plan, nhưng cảnh báo **không kết hợp global embedded broker với per-class `@EmbeddedKafka`** một cách thiếu kiểm soát: chúng dùng system properties chung và có thể làm clients kết nối sai broker. Dùng test topic riêng và quản lý broker lifecycle rõ ràng.

## 4. Kafka trong Testcontainers là gì?

Testcontainers chạy Kafka broker bằng một Docker image, tự quản lý container startup, mapped host ports và cleanup. Với Testcontainers **1.21.x**, những classes phù hợp gồm:

- `org.testcontainers.kafka.ConfluentKafkaContainer`, dùng image `confluentinc/cp-kafka` từ 7.4.0 trở lên.
- `org.testcontainers.kafka.KafkaContainer`, dùng Apache Kafka images phù hợp với module.
- Class cũ `org.testcontainers.containers.KafkaContainer` đã deprecated, không nên dùng cho code mới.

Ví dụ dùng Confluent:

```java
@Container
@ServiceConnection
static final ConfluentKafkaContainer KAFKA =
        new ConfluentKafkaContainer(
                "confluentinc/cp-kafka:7.8.0");
```

Đây là snippet trong class có `@Testcontainers` và `@SpringBootTest`. Image/version cần được cho phép ở CI và Docker runtime phải hoạt động.

### 4.1. @ServiceConnection trong Boot 3.5

Dependency `org.springframework.boot:spring-boot-testcontainers` cung cấp `@ServiceConnection`. Khi Spring Boot nhận thấy typed container Kafka, Boot tạo `KafkaConnectionDetails` cho auto-configured Kafka clients. **Connection details ưu tiên hơn thông số kết nối trong `application.properties`**.

Cơ chế này tốt hơn hardcode `localhost:9092` vì Testcontainers expose Kafka ở mapped port ngẫu nhiên. Với client nằm trong container khác, không được dùng địa chỉ host loopback bừa bãi; Kafka advertised listeners có thể cần được cấu hình cho Docker network.

### 4.2. @DynamicPropertySource là đường thay thế

Khi không dùng `spring-boot-testcontainers` hoặc cần cấu hình thủ công:

```java
@DynamicPropertySource
static void kafkaProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.kafka.bootstrap-servers",
            KAFKA::getBootstrapServers);
}
```

Đây là **mã minh họa thay thế**, cần imports và lifecycle container phù hợp. Test chính của bài dùng `@ServiceConnection`, không chồng đồng thời hai cách wiring một địa chỉ để tránh hiểu sai precedence.

### 4.3. Docker dependencies và giới hạn

Testcontainers cần Docker daemon hoặc môi trường compatible, quyền pull image, CPU/RAM/disk và loopback/container networking phù hợp. Single-node Confluent image **không đại diện** Kafka multi-node cluster. Image PLAINTEXT ở sample cũng không kiểm chứng TLS/SASL/ACL của production.

Trong Spring Boot 3.5 BOM, Testcontainers module dùng artifact `org.testcontainers:kafka` thuộc nhánh **1.21.x**. Tài liệu Testcontainers 2.x có thể dùng artifact `org.testcontainers:testcontainers-kafka`. Trộn artifact của hai major lines mà không kiểm soát version thường gây build errors.

## 5. So sánh Embedded Kafka và Testcontainers

| Tiêu chí | Embedded Kafka | Testcontainers Kafka |
|---|---|---|
| Docker bắt buộc | Không | Có |
| Broker thực | Có | Có |
| Kafka producer/consumer thật | Có | Có |
| Setup JUnit | `@EmbeddedKafka` | `@Testcontainers/@Container` |
| Bootstrap | `bootstrapServersProperty` | `@ServiceConnection` |
| Version broker | Theo thư viện test/Kafka dependencies | Theo Docker image tag |
| Gần image deployment | Thấp hơn | Cao hơn |
| CI startup/resources | Thường nhẹ hơn | Thường nặng hơn |
| Topic, group, offset | Kiểm tra được | Kiểm tra được |
| Kafka serializers/headers | Kiểm tra được | Kiểm tra được |
| Listener assignment/rebalances | Có | Có |
| Host↔container networking | Không | Có |
| Multi-node failover mặc định | Không | Không |
| TLS/SASL/ACL mặc định | Không | Không |
| Scale/load performance production | Không chứng minh | Không chứng minh |

**Hướng chọn:** unit tests cho business logic; Embedded Kafka cho integration nhanh; Testcontainers cho compatibility broker image và môi trường nhiều dịch vụ; multi-node/fault suite cho distributed behavior.

## 6. Kafka semantics cần hiểu trước khi assert

### 6.1. Producer ACK không phải consumer success

Spring Kafka 3.x `KafkaTemplate.send(...)` trả `CompletableFuture<SendResult<K,V>>`. Khi future hoàn tất, producer đã nhận kết quả theo `acks` và broker metadata. Điều này chưa có nghĩa listener đã xử lý xong, Kafka consumer offset đã commit hay database đã ghi.

Một end-to-end test tối thiểu phải:

1. Gửi record qua KafkaTemplate thật.
2. Chờ future với timeout và kiểm tra metadata.
3. Chờ listener nhận record qua một dấu hiệu có thể quan sát được.
4. Assert key, value, topic/partition/offset hoặc business side effect.

Nếu listener còn ghi DB hoặc gọi HTTP, cần kiểm chứng **hậu quả nghiệp vụ**; queue test trong ví dụ chỉ quan sát callback, không khẳng định DB integration.

### 6.2. Partition ordering

Trong Kafka, records có offset tăng trong **một partition**. Kafka không bảo đảm global ordering giữa các partitions. Nếu cần ordering cho một aggregate như order, dùng key nhất quán và producer partitioning policy phù hợp.

Test của bài gửi hai records với **cùng key**; sau khi future của record thứ nhất hoàn tất mới gửi record thứ hai, sau đó assert:

- Cùng partition.
- Offset của bản ghi thứ hai lớn hơn bản ghi thứ nhất.
- Listener thấy event values đúng thứ tự.

Không mở rộng kết luận này sang hai keys khác nhau hoặc multi-partition global ordering.

### 6.3. Consumer group và offset reset

Một consumer group lưu committed offsets. `spring.kafka.consumer.auto-offset-reset=earliest` chỉ được dùng khi **không có valid committed offset** cho group/partition; nó không tự tua lại một group đã commit.

Cần:

- Group ID riêng theo test class hoặc mỗi run nếu dùng shared broker.
- Topic riêng khi nhiều tests chạy song song.
- Không dùng cùng group cho “probe consumer” và listener của ứng dụng nếu muốn cả hai nhận đủ records.
- Đợi assignment trước khi gửi; đừng chỉ `Thread.sleep`.
- Đừng để một consumer cũ đọc records từ test trước mà test mới tưởng là event của nó.

Spring Kafka test utilities có `KafkaTestUtils.consumerProps(...)` và các phương thức lấy records, nhưng consumer độc lập vẫn phải có group/offset policy rõ ràng.

## 7. Ví dụ runnable: một ứng dụng, hai Kafka brokers thử nghiệm

Ví dụ dùng **Java 17+, Spring Boot 3.5.x, Spring Kafka 3.3.x và Testcontainers 1.21.x**. Một ứng dụng production có publisher/receiver/config thật. Hai test classes dùng cùng source code đó:

- `EmbeddedKafkaIntegrationTest`: 3 JUnit tests, broker trong môi trường test, **không Docker**.
- `KafkaTestcontainersIntegrationTest`: 4 JUnit tests, Confluent Kafka trong Docker, `@ServiceConnection`.
- **Tổng 7 JUnit tests.**

Mỗi test dùng topic riêng; producer và consumer dùng String serializer/deserializer. Có hai partitions và một listener consumer được assign cả hai partitions.

### 7.1. Gradle dependencies

Trích đoạn của `build.gradle` đã có Spring Boot 3.5 plugin/BOM, repositories, Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'

    // Artifact names in Boot 3.5 / Testcontainers 1.21.x:
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

### 7.2. Maven dependencies

Trích đoạn trong `pom.xml` với Spring Boot 3.5 parent/BOM và JUnit Platform runner:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>
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
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>kafka</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là dependency snippets, không phải build files nguyên vẹn. Không đặt phiên bản Kafka/Spring Kafka/Testcontainers tùy ý khi Boot BOM đã quản lý chúng. Với Testcontainers 2.x phải thay artifact và xác minh imports tương ứng.

### 7.3. Cây file

```text
src/
├── main/
│   ├── java/com/example/kafkalab/
│   │   ├── KafkaLabApplication.java
│   │   ├── KafkaTopicConfiguration.java
│   │   ├── OrderEventPublisher.java
│   │   └── OrderEventReceiver.java
│   └── resources/
│       └── application.properties
└── test/java/com/example/kafkalab/
    ├── EmbeddedKafkaIntegrationTest.java
    └── KafkaTestcontainersIntegrationTest.java
```

### 7.4. Application bootstrap

**File `src/main/java/com/example/kafkalab/KafkaLabApplication.java`:**

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

`@EnableKafka` kích hoạt annotation-driven `@KafkaListener`. Spring Boot auto-configuration cung cấp `KafkaTemplate`, KafkaAdmin và listener infrastructure khi có đúng dependencies và configurations.

### 7.5. Tạo topic qua KafkaAdmin/NewTopic

**File `src/main/java/com/example/kafkalab/KafkaTopicConfiguration.java`:**

```java
package com.example.kafkalab;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration(proxyBeanMethods = false)
public class KafkaTopicConfiguration {

    @Bean
    NewTopic orderEventsTopic(
            @Value("${app.kafka.topic}") String topic) {

        return TopicBuilder.name(topic)
                .partitions(2)
                .replicas(1)
                .build();
    }
}
```

Topic 2 partitions cho phép kiểm tra partition-aware behavior. Replication factor 1 là lựa chọn **chỉ cho single-broker demo**. Nếu cấu hình replicas=3 nhưng broker chỉ có một node, topic creation thất bại; production cluster cần replicas/min.insync.replicas phù hợp.

KafkaAdmin từ Spring Boot có thể tạo `NewTopic` khi context khởi động. Ở Embedded Kafka test, topic còn được khai báo trong `@EmbeddedKafka(topics=...)`; hai khai báo phải nhất quán. Ở Testcontainers class, KafkaAdmin tạo topic trên broker container.

### 7.6. Publisher dùng KafkaTemplate thật

**File `src/main/java/com/example/kafkalab/OrderEventPublisher.java`:**

```java
package com.example.kafkalab;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafka;
    private final String topic;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafka,
            @Value("${app.kafka.topic}") String topic) {
        this.kafka = kafka;
        this.topic = topic;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String key, String value) {
        validate(key, value);
        return kafka.send(topic, key, value);
    }

    public CompletableFuture<SendResult<String, String>>
            publishWithCorrelationId(
                    String key,
                    String value,
                    String correlationId) {

        validate(key, value);
        if (correlationId == null || correlationId.isBlank()) {
            throw new IllegalArgumentException(
                    "correlationId must not be blank");
        }

        ProducerRecord<String, String> record =
                new ProducerRecord<>(topic, key, value);
        record.headers().add(
                "x-correlation-id",
                correlationId.getBytes(StandardCharsets.UTF_8));
        return kafka.send(record);
    }

    private static void validate(String key, String value) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("key is blank");
        }
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is blank");
        }
    }
}
```

Service production không block trên future; **tests** có thể `get(timeout)` để biết broker ACK và metadata. Không mặc định `KafkaTemplate.send` thành công chỉ vì method trả future; future có thể hoàn thành exceptionally do serializer, metadata, broker hoặc network error.

### 7.7. Consumer với KafkaListener và test-observation queue

**File `src/main/java/com/example/kafkalab/OrderEventReceiver.java`:**

```java
package com.example.kafkalab;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventReceiver {

    public record Received(
            String key,
            String value,
            int partition,
            long offset,
            String correlationId) {}

    private final BlockingQueue<Received> queue =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            id = "orders-listener",
            topics = "${app.kafka.topic}",
            groupId = "${app.kafka.group}")
    public void onRecord(ConsumerRecord<String, String> record) {

        Header header = record.headers()
                .lastHeader("x-correlation-id");

        String correlationId = header == null
                ? null
                : new String(header.value(),
                        StandardCharsets.UTF_8);

        queue.offer(new Received(
                record.key(),
                record.value(),
                record.partition(),
                record.offset(),
                correlationId));
    }

    public Received await(Duration timeout)
            throws InterruptedException {
        return queue.poll(timeout.toMillis(),
                TimeUnit.MILLISECONDS);
    }

    public void clear() {
        queue.clear();
    }
}
```

`BlockingQueue` chỉ là công cụ quan sát callback cho ví dụ. Nó không phải durable event store, không commit consumer offset và không tạo exactly-once business semantics. Trong ứng dụng thật, listener thường gọi service/DB; muốn kiểm chứng business processing phải assert DB hoặc một output observable khác.

### 7.8. Kafka client configuration

**File `src/main/resources/application.properties`:**

```properties
# Default for manual local run; tests replace this endpoint.
spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer

app.kafka.topic=orders.events.local
app.kafka.group=orders.local
spring.kafka.consumer.auto-offset-reset=latest
```

Khi chạy `main()` theo cấu hình này, cần Kafka broker thật tại localhost:9092. Trong **Embedded Kafka tests**, annotation remap bootstrap sang broker embedded. Trong **Testcontainers tests**, `@ServiceConnection` ưu tiên container bootstrap. Không kết nối Kafka production trong CI.

## 8. Cơ chế test chống race và sai offset

Trước khi xem mã hai test classes, cần hiểu ba điểm.

**Thứ nhất**, Spring test context started chưa có nghĩa consumer đã join group hoặc được assign partition. Với một listener concurrency=1 và topic 2 partitions, dùng:

```java
MessageListenerContainer container =
        listenerRegistry.getListenerContainer("orders-listener");

ContainerTestUtils.waitForAssignment(container, 2);
```

Đây là snippet trong test context; đảm bảo partition assignment đã hoàn tất trước khi gửi message. Nếu thay concurrency, số partitions hoặc listener implementation, điều kiện chờ phải được điều chỉnh.

**Thứ hai**, gửi Kafka bất đồng bộ. Cần:

```java
SendResult<String, String> ack =
        publisher.publish("order-1", "CREATED")
                .get(10, TimeUnit.SECONDS);
```

Đây là producer acknowledgment, không phải callback processing. Để quan sát listener:

```java
OrderEventReceiver.Received event =
        receiver.await(Duration.ofSeconds(10));

assertThat(event).isNotNull();
```

Không sử dụng `Thread.sleep(300)` như một “bảo đảm”.

**Thứ ba**, topic/group IDs phải có isolation. Mỗi test class dùng topic riêng, group riêng và keys riêng. Nếu một broker được chia sẻ giữa nhiều JUnit workers, cần namespacing theo run ID, không chỉ hardcode những tên trong demo.

## 9. Test với Embedded Kafka (3 JUnit methods)

**File `src/test/java/com/example/kafkalab/EmbeddedKafkaIntegrationTest.java`:**

```java
package com.example.kafkalab;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = KafkaLabApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "app.kafka.topic=orders.events.embedded",
        "app.kafka.group=orders.embedded.group",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.listener.concurrency=1",
        "spring.kafka.admin.fail-fast=true"
    }
)
@EmbeddedKafka(
    kraft = true,
    partitions = 2,
    topics = "orders.events.embedded",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
class EmbeddedKafkaIntegrationTest {

    @Autowired OrderEventPublisher publisher;
    @Autowired OrderEventReceiver receiver;
    @Autowired KafkaListenerEndpointRegistry registry;

    @BeforeEach
    void waitForAssignment() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");
        assertThat(container).isNotNull();
        ContainerTestUtils.waitForAssignment(container, 2);
        receiver.clear();
    }

    @Test
    void recordTravelsThroughEmbeddedBroker()
            throws Exception {
        SendResult<String, String> result =
                publisher.publish("E-01", "CREATED")
                        .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received received =
                receiver.await(Duration.ofSeconds(10));

        assertThat(received).isNotNull();
        assertThat(received.key()).isEqualTo("E-01");
        assertThat(received.value()).isEqualTo("CREATED");
        assertThat(result.getRecordMetadata().topic())
                .isEqualTo("orders.events.embedded");
        assertThat(received.partition()).isEqualTo(
                result.getRecordMetadata().partition());
        assertThat(received.offset()).isEqualTo(
                result.getRecordMetadata().offset());
    }

    @Test
    void unicodePayloadAndCorrelationHeaderSurvive()
            throws Exception {
        publisher.publishWithCorrelationId(
                "E-02", "Đơn hàng được tạo",
                "trace-embedded-02")
                .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received received =
                receiver.await(Duration.ofSeconds(10));

        assertThat(received).isNotNull();
        assertThat(received.value()).isEqualTo(
                "Đơn hàng được tạo");
        assertThat(received.correlationId()).isEqualTo(
                "trace-embedded-02");
    }

    @Test
    void sameKeyIsOrderedWithinOnePartition()
            throws Exception {
        publisher.publish("E-03", "CREATED")
                .get(10, TimeUnit.SECONDS);
        publisher.publish("E-03", "PAID")
                .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received first =
                receiver.await(Duration.ofSeconds(10));
        OrderEventReceiver.Received second =
                receiver.await(Duration.ofSeconds(10));

        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.value()).isEqualTo("CREATED");
        assertThat(second.value()).isEqualTo("PAID");
        assertThat(first.partition()).isEqualTo(
                second.partition());
        assertThat(first.offset()).isLessThan(
                second.offset());
    }
}
```

**Ba tests này sử dụng broker embedded thật**. Cùng producer/consumer production được chạy; không có Docker. `@DirtiesContext(AFTER_CLASS)` giảm rủi ro context cache giữ embedded broker bean sau khi lifecycle kết thúc, nhất là khi test suite có nhiều class.

Test đầu so sánh metadata producer với record listener nhận. Test thứ hai kiểm tra UTF-8 và custom header. Test thứ ba kiểm tra ordering chỉ trong một partition. Không test nào khẳng định DB transaction, offset commit hoặc retry/DLT đã được kiểm thử.

## 10. Test với Kafka Testcontainers (4 JUnit methods)

**Điều kiện:** Docker daemon hoặc compatible runtime đang chạy, có quyền pull `confluentinc/cp-kafka:7.8.0`. Nếu thiếu Docker, bộ test này không chạy được và CI cần báo rõ, không coi là coverage đã pass.

**File `src/test/java/com/example/kafkalab/KafkaTestcontainersIntegrationTest.java`:**

```java
package com.example.kafkalab;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.ConfluentKafkaContainer;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.kafka.KafkaConnectionDetails;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
    classes = KafkaLabApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "app.kafka.topic=orders.events.container",
        "app.kafka.group=orders.container.group",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.listener.concurrency=1",
        "spring.kafka.admin.fail-fast=true"
    }
)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
class KafkaTestcontainersIntegrationTest {

    @Container
    @ServiceConnection
    static final ConfluentKafkaContainer KAFKA =
            new ConfluentKafkaContainer(
                    "confluentinc/cp-kafka:7.8.0");

    @Autowired KafkaConnectionDetails details;
    @Autowired OrderEventPublisher publisher;
    @Autowired OrderEventReceiver receiver;
    @Autowired KafkaListenerEndpointRegistry registry;

    @BeforeEach
    void waitForAssignment() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");
        assertThat(container).isNotNull();
        ContainerTestUtils.waitForAssignment(container, 2);
        receiver.clear();
    }

    @Test
    void springBootUsesContainerBootstrapServers() {
        assertThat(KAFKA.isRunning()).isTrue();
        assertThat(details.getBootstrapServers())
                .contains(KAFKA.getBootstrapServers());
    }

    @Test
    void sendAndReceiveThroughContainerBroker()
            throws Exception {
        SendResult<String, String> result =
                publisher.publish("C-01", "CREATED")
                        .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received received =
                receiver.await(Duration.ofSeconds(10));

        assertThat(received).isNotNull();
        assertThat(received.key()).isEqualTo("C-01");
        assertThat(received.value()).isEqualTo("CREATED");
        assertThat(result.getRecordMetadata().topic())
                .isEqualTo("orders.events.container");
        assertThat(received.partition()).isEqualTo(
                result.getRecordMetadata().partition());
    }

    @Test
    void correlationHeaderSurvivesContainerTransport()
            throws Exception {
        publisher.publishWithCorrelationId(
                "C-02", "CONFIRMED",
                "trace-container-02")
                .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received received =
                receiver.await(Duration.ofSeconds(10));

        assertThat(received).isNotNull();
        assertThat(received.value()).isEqualTo("CONFIRMED");
        assertThat(received.correlationId()).isEqualTo(
                "trace-container-02");
    }

    @Test
    void sameKeyKeepsPartitionAndOffsetOrder()
            throws Exception {
        publisher.publish("C-03", "CREATED")
                .get(10, TimeUnit.SECONDS);
        publisher.publish("C-03", "PACKED")
                .get(10, TimeUnit.SECONDS);

        OrderEventReceiver.Received first =
                receiver.await(Duration.ofSeconds(10));
        OrderEventReceiver.Received second =
                receiver.await(Duration.ofSeconds(10));

        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.value()).isEqualTo("CREATED");
        assertThat(second.value()).isEqualTo("PACKED");
        assertThat(first.partition()).isEqualTo(
                second.partition());
        assertThat(first.offset()).isLessThan(
                second.offset());
    }
}
```

Lớp Testcontainers giữ **nguyên production KafkaLabApplication, KafkaTopicConfiguration, OrderEventPublisher và OrderEventReceiver**. Chỉ khác bootstrap broker, topic/group settings và Docker image. Không cần `@EmbeddedKafka` ở lớp này.

**Test 1** xác nhận container đang chạy và Boot connection details trỏ đúng broker. **Test 2–4** thực thi producer/consumer qua container broker, kiểm tra key/value, headers và ordering. Không sử dụng localhost:9092 hardcoded làm đích cuối, bởi service connection ưu tiên container bootstrap.

### 10.1. Vì sao không gọi @DynamicPropertySource cùng @ServiceConnection?

Cả hai có thể cung cấp bootstrap configuration. Trong ví dụ, dùng **một** cơ chế: Boot-managed `@ServiceConnection`. Nếu project không sử dụng spring-boot-testcontainers, có thể bỏ @ServiceConnection và thêm `@DynamicPropertySource` trỏ `KAFKA::getBootstrapServers`. Cần đảm bảo không có một property/custom bean khác ưu tiên sai địa chỉ.

### 10.2. Vì sao không tạo container mới trong từng test method?

Static `@Container` cho phép Testcontainers JUnit quản lý một container dùng chung trong test class, giảm startup/image cost. Mỗi test method vẫn cần keys riêng và receiver state sạch. Khi các tests song song và chia sẻ Kafka broker, dùng topic/group namespaces rõ ràng hoặc test isolation nâng cao.

### 10.3. Vì sao @DirtiesContext ở lớp container test?

Spring TestContext cache có thể giữ bean đã cấu hình bootstrap của container sau khi JUnit extension đã stop container. Với một class demo, `@DirtiesContext(AFTER_CLASS)` giúp context được đóng cùng lifecycle. Ở suite lớn, chọn container/context sharing strategy nhất quán; không sử dụng một broker đã stop cho cached contexts khác.

## 11. Chạy ví dụ bằng Gradle/Maven

Linux/macOS:

```bash
# Embedded (không cần Docker)
./gradlew test --tests "com.example.kafkalab.EmbeddedKafkaIntegrationTest"

# Testcontainers (cần Docker)
./gradlew test --tests "com.example.kafkalab.KafkaTestcontainersIntegrationTest"

# Nếu dự án dùng Maven:
./mvnw -Dtest=EmbeddedKafkaIntegrationTest test
./mvnw -Dtest=KafkaTestcontainersIntegrationTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.kafkalab.EmbeddedKafkaIntegrationTest"
.\gradlew.bat test --tests "com.example.kafkalab.KafkaTestcontainersIntegrationTest"

# Hoặc Maven Wrapper:
.\mvnw.cmd "-Dtest=EmbeddedKafkaIntegrationTest" test
.\mvnw.cmd "-Dtest=KafkaTestcontainersIntegrationTest" test
```

Dùng đúng build tool của project; không bắt buộc dùng cả hai. Với Docker Testcontainers, cần cho phép image pull, socket/daemon, port mapping và CPU/RAM phù hợp. Một run bị skip vì thiếu Docker **không được gọi là đã test broker container**.

### 11.1. Kỳ vọng của test report

| Class | Số phương thức @Test | Broker | Có Docker? |
|---|---:|---|---|
| `EmbeddedKafkaIntegrationTest` | 3 | Embedded KRaft broker | Không |
| `KafkaTestcontainersIntegrationTest` | 4 | Confluent cp-kafka container | Có |
| **Tổng** | **7** | Hai test environments độc lập | Tùy class |

**Mục tiêu dự kiến:** 7 JUnit tests pass trong môi trường phù hợp. Đây là mã mẫu được kiểm tra theo tài liệu/API, **không phải kết quả đã biên dịch hoặc chạy trong phiên soạn bài**. Không có stdout cố định từ ứng dụng; broker, JUnit, Maven/Gradle có thể in logs với thời điểm/thứ tự thay đổi.

## 12. Những nguyên nhân thường khiến Kafka tests flaky

### 12.1. Gửi trước khi consumer được assign

Một context khởi động xong chưa có nghĩa listener đã được Kafka assign partition. Nếu gửi quá sớm và group bắt đầu với `latest`, consumer có thể bỏ lỡ message. Dùng `ContainerTestUtils.waitForAssignment(...)` trước khi publish hoặc một synchronization mechanism tương đương.

### 12.2. Reuse cùng topic/group giữa tests

Topic có retained records và group có committed offsets. Chạy riêng một test so với chạy cả suite có thể cho kết quả khác. Với shared broker:

- Tạo topic/group riêng theo class/run.
- Không dùng group production.
- Chọn `earliest`/`latest` có chủ đích.
- Khi cần replay, tạo group mới hoặc seek; chỉ đổi earliest chưa đủ khi có committed offsets.
- Không dùng cùng group cho probe consumer và application listener ngoài ý muốn.

Trong sample, mỗi class dùng topic/group riêng và mỗi test method dùng keys riêng; việc clear queue trong BeforeEach tránh giữ observation của test trước.

### 12.3. Chờ bằng sleep cố định

`Thread.sleep(200)` có thể đủ trên máy cá nhân nhưng fail trên CI. Các mốc cần chờ riêng:

1. KafkaAdmin tạo topic và broker sẵn sàng.
2. Consumer join/partition assignment.
3. Producer nhận ACK.
4. Listener callback chạy.
5. Business side effect hoàn tất (nếu có).

Sử dụng bounded wait/probe tương ứng, đừng chờ cùng một sleep duy nhất.

### 12.4. Ordering giả

Hai keys có thể được route vào hai partitions. Không assert global order của mọi records. Với bài toán ordering per order/account, thiết kế stable partition key. Producer retries/idempotence/concurrency và version cũng liên quan nếu cần test ordering dưới failure.

### 12.5. Consumer lag và offset commit

Listener nhận record thành công không chứng minh offset đã commit theo ack mode. Nếu cần test restart/resume/offset correctness, bạn phải dừng/restart consumer container, xác định group/offset và quan sát replay. Sample chỉ test callback received, không test Kafka offset transaction.

## 13. Error handling, retry và Dead Letter Topic

Một happy-path test như ví dụ **chưa kiểm tra**:

- JSON/Avro deserialization failure.
- Business exception làm listener throw.
- Producer broker timeout.
- Kafka consumer retry/backoff.
- `DefaultErrorHandler`, `DeadLetterPublishingRecoverer` hoặc `@RetryableTopic`.
- DLT topic destination/partition/header.
- Poison-pill khiến partition ngừng tiến.
- Consumer offset commit sau recovery.

### 13.1. DLT test cần broker path thật

Nếu cần DLT integration:

1. Tạo source topic và DLT topic với partitions phù hợp.
2. Cấu hình error handler/recoverer và retry policy test.
3. Gửi poison-pill thật khiến listener throw.
4. Chờ đủ attempt/handler path.
5. Dùng consumer group riêng đọc DLT.
6. Assert key, value/raw bytes, error headers, partition và destination topic.
7. Đảm bảo timeout và retry count bounded.

Một mock `DeadLetterPublishingRecoverer.accept(...)` chỉ chứng minh method được gọi, **không chứng minh** DLT record đã được broker lưu.

### 13.2. Ví dụ policy mang tính minh họa

```java
@Bean
DefaultErrorHandler errorHandler(
        KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);
    return new DefaultErrorHandler(
            recoverer, new FixedBackOff(0L, 2L));
}
```

Đây là **snippet**, không phải file runnable thuộc ví dụ 7 tests. Cần imports, serializer/deserializer và DLT provisioning đúng. Với `FixedBackOff(0L,2L)`, cần xác nhận semantics retry attempts của handler version đang dùng. Không dùng configuration production mặc định mà không xem xét retryable exceptions, poison-pill behavior và throughput.

### 13.3. Khi nào chọn Embedded hay Container cho DLT?

Nếu chỉ kiểm tra policy/error handler và DLT publish/consume, Embedded Kafka có thể đủ. Nếu test phụ thuộc broker/image version, security, network hoặc broker-specific config, dùng Testcontainers. Với Schema Registry/Avro/Protobuf, cân nhắc container schema registry riêng hoặc test contract/schema phù hợp.

## 14. Transactions và exactly-once: không suy quá từ send/receive

### 14.1. Kafka producer transactions

Kafka hỗ trợ transactions và idempotent producer. Producer có thể ACK một record trước khi transaction commit. Nếu transaction abort, consumer dùng `isolation.level=read_committed` không thấy aborted record. Do vậy:

- Send future hoàn tất không bằng Kafka transaction commit.
- Listener receive không tự chứng minh DB commit.
- Consumer acknowledgment/offset commit không đồng nghĩa business operation exactly-once trong external systems.

Một test Kafka transaction nên tạo transactional producer, commit/abort rõ, dùng consumer read_committed và assert committed/aborted records.

### 14.2. DB và Kafka là hai resource boundaries

Một service dùng `@Transactional` với JPA ghi DB rồi `KafkaTemplate.send` không tự có distributed XA transaction cho cả hai resources. Process có thể crash sau DB commit nhưng trước Kafka publish, hoặc event Kafka commit nhưng HTTP call thất bại.

Các cách tăng an toàn:

- Transactional outbox/inbox.
- Idempotent event consumers theo event ID.
- Unique constraints/deduplication.
- Recovery/retry và dead-letter policy.
- Test controlled failure points giữa các commits.
- Đo processing effects ngoài Kafka, không chỉ queue callback.

Embedded Kafka/Testcontainers hỗ trợ kiểm tra Kafka path thật nhưng **không thay** một kiến trúc consistency giữa database và Kafka.

## 15. Security, compatibility, Docker network và HA

### 15.1. Single broker không phải cluster HA

Embedded KRaft broker và Confluent container trong bài đều một broker với replicas=1. Chúng không kiểm tra:

- Replication factor 3, min.insync.replicas, ISR shrink.
- Leader election, controller quorum failover.
- Broker crash/restart giữa produce/consume.
- Rack awareness và partition reassignment.
- Rolling upgrades.
- Network partitions và backpressure dưới tải.
- Multi-node throughput và durability targets.

Nếu production SLA phụ thuộc những tính chất đó, thiết kế separate multi-node Kafka cluster/fault suite.

### 15.2. Advertised listeners

Kafka clients dùng bootstrap address để lấy metadata chứa broker endpoints. Trong Docker:

- Host JVM dùng `KAFKA.getBootstrapServers()`.
- Container khác không thể mặc định truy cập `localhost:<mapped-port>` của host, vì localhost trong container chỉ tới chính container đó.
- Nếu app chạy trong một container khác, có thể cần đăng ký additional listener phù hợp Docker network.
- Sai advertised listeners làm bootstrap ban đầu connect nhưng send/poll sau đó timeout.

Đừng hardcode `localhost:9092` cho Kafka Testcontainers. Với Spring Boot auto-config, `@ServiceConnection` tránh phần lớn lỗi host-side mapped port.

### 15.3. TLS/SASL/ACL

Demo dùng local broker thường PLAINTEXT. Nó không kiểm tra certificate chain, mTLS, SASL/PLAIN/SCRAM, OAuthBearer, ACL topics/groups/transactional IDs, DNS/proxy production hoặc secret rotation. Nếu đây là rủi ro quan trọng, dùng broker test có security config tương ứng hoặc staging infrastructure được phép.

Không đưa production credentials, PII hoặc SASL secrets vào source/test logs. Kafka record value/headers có thể chứa dữ liệu nhạy cảm; log broker/test runner cần redaction.

### 15.4. Version matrix

Một Kafka protocol client có thể tương tác với nhiều broker versions, nhưng không có nghĩa mọi tổ hợp đều hỗ trợ các features giống nhau. Pin và ghi rõ:

- Spring Boot version.
- Spring Kafka/kafka-clients version do BOM quản lý.
- Testcontainers major/module version.
- Kafka image và broker version.
- Serializer/schema versions.
- Security/protocol config.

Chỉ nâng Kafka image tag khi có compatibility tests; không cho rằng embedded test với broker phụ thuộc classpath đã thay thế Testcontainers image test.

## 16. Debug các lỗi phổ biến

| Triệu chứng | Lý do thường gặp | Giải pháp |
|---|---|---|
| Test kết nối localhost:9092 | Bootstrap test override không được dùng | @EmbeddedKafka bootstrapServersProperty hoặc @ServiceConnection |
| @EmbeddedKafka nhưng client vẫn chờ broker ngoài | Custom ProducerFactory bỏ qua Spring properties | Dùng Boot auto-config hoặc truyền broker test address vào custom factory |
| Consumer không nhận record | Chưa assign, sai topic/group, offset latest | Chờ assignment, dùng group mới/earliest |
| Consumer nhận event cũ | Topic/group shared và retained messages | Isolate topic/group, clear probe queue |
| Test send future treo | KafkaAdmin/topic/metadata/broker network lỗi | Future bounded timeout, kiểm tra logs/topic |
| KafkaListener không chạy | Sai @EnableKafka/bean scan/topic/deserializer | Kiểm tra listener registry, group và logs |
| No class ConfluentKafkaContainer | Sai artifact/version Testcontainers | Boot 3.5 dùng org.testcontainers:kafka và đúng package |
| Docker environment unavailable | Daemon không hoạt động/quyền CI không đủ | Dùng Docker job, Testcontainers Cloud hoặc tách suite |
| Image pull failed | Registry/proxy/quota policy | Pin/mirror image, chuẩn bị CI registry access |
| Container chạy nhưng Kafka timeout | Advertised listener sai | getBootstrapServers/ServiceConnection, correct networking |
| Topic không tạo được | KafkaAdmin chưa tạo/replicas>brokers | NewTopic partitions=2, replicas=1 |
| KafkaTemplate gửi String nhưng serializer sai | Key/value serializer mismatch | StringSerializer và StringDeserializer đúng |
| Key/value khác kỳ vọng | Charset/headers/serialization khác | Verify record metadata + listener payload |
| Test ordering cross-partition fail | Kafka chỉ order per partition | Same key/partition; assert offsets |
| DLT không có record | Error handler/partition/topic thiếu | Configure/recoverer + consume DLT bằng group riêng |
| Group đã commit không replay | earliest không áp dụng khi offset có sẵn | Group mới hoặc explicit seek |
| Testcontainers test bị skip | CI không có Docker hoặc test selection chỉ chạy Embedded | Kiểm tra JUnit skipped count và Docker job |
| Embedded shutdown race | Context cache và broker bean lifecycle | @DirtiesContext hoặc lifecycle strategy |
| Retry gây duplicate business actions | At-least-once delivery | Idempotent consumer + domain deduplication |
| Test pass nhưng production TLS fail | Test PLAINTEXT | Security integration suite riêng |
| Spring Boot 4 import fails | Package/starter/test module khác major | Dùng đúng version-specific docs |

### 16.1. Trình tự chẩn đoán hiệu quả

1. Xác định test dùng Embedded Kafka hay Testcontainers; không trộn bootstrap vô ý.
2. Xem dependency tree đúng Spring Boot 3.5/Spring Kafka 3.3/Testcontainers 1.21.
3. Xem broker startup/logs và topic provisioning.
4. Kiểm tra bootstrap source: embedded system property hay container connection details.
5. Kiểm tra topic, group ID và listener container ID.
6. Chờ consumer assignment; xác nhận partitions count.
7. Kiểm tra producer serializer, consumer deserializer và record metadata.
8. Chờ KafkaTemplate future rồi listener callback với bounded timeout.
9. Nếu container: Docker runtime, mapped ports, advertised listeners, image.
10. Nếu test yêu cầu retry/DLT/transaction/HA: đánh giá nó có cấu hình và asserts riêng chưa.

## 17. Câu hỏi thực hành có đáp án

### Câu A. Vì sao Mockito không chứng minh Kafka integration?

Một unit test verify `kafkaTemplate.send(topic, key, event)` được gọi một lần. Developer đổi serializer sang loại sai. Test vẫn xanh. Vì sao?

**Đáp án:** mock chỉ xác nhận Java method invocation. Embedded Kafka/Testcontainers cho serializer, broker và listener chạy thật, phát hiện lỗi wiring/type. Unit test vẫn hữu ích cho business logic, nhưng không đủ cho protocol integration.

### Câu B. @EmbeddedKafka còn kết nối localhost:9092

**Đáp án:** kiểm tra `bootstrapServersProperty="spring.kafka.bootstrap-servers"` hoặc mapping property từ broker; xem custom factories đã bỏ qua Boot properties hay chưa. Không sửa bằng cách đưa địa chỉ production vào test.

### Câu C. Testcontainers có Kafka bootstrap port cố định không?

**Không.** Use `@ServiceConnection`/`KafkaConnectionDetails` hoặc `KAFKA.getBootstrapServers()`. Docker mapped ports động, không được mặc định là localhost:9092.

### Câu D. Khi nào producer ACK không đủ?

Producer future thành công, consumer không nhận. **Đáp án:** ACK phản ánh gửi broker, không phải consumer assignment/processing. Kiểm tra topic, group, offsets, listener registration và deserializer; chờ callback riêng.

### Câu E. Thứ tự records ở hai partitions

Hai records có keys khác nhau, B được nhận trước A. Có phải Kafka sai?

**Không.** Kafka chỉ bảo đảm order per partition. Nếu domain cần thứ tự per entity, dùng stable key và assert same partition/offset.

### Câu F. earliest không replay

Đổi `auto-offset-reset=earliest` nhưng group vẫn không đọc record cũ. **Đáp án:** group có committed offset hợp lệ; phải tạo group mới hoặc explicit seek.

### Câu G. Muốn kiểm tra Dead Letter Topic

Mock error handler pass, nhưng DLT không nhận event. **Đáp án:** unit mock không kiểm tra broker publish. Tạo poison-pill thật, cấu hình recoverer/source/DLT, consumer group riêng đọc DLT.

### Câu H. Kafka Testcontainers có giống production HA không?

**Không.** Một container single-node không test multi-broker replication, ISR, leader failover hoặc TLS/SASL nếu chưa cấu hình. Cần cluster tests phù hợp.

### Câu I. Kafka record đã ACK nhưng transaction abort

Với consumer read_committed, record có được nhìn thấy không? **Thông thường không** vì aborted transaction không được hiển thị cho read_committed consumer.

### Câu J. Kafka và JPA cùng @Transactional

Có đảm bảo atomic commit DB và Kafka không? **Không mặc định.** Chúng là resource transactions khác nhau. Xem outbox, idempotency và recovery.

### Câu K. CI không có Docker

Embedded Kafka tests pass nhưng TC tests không chạy. Có được báo mọi integration tests PASS không? **Không.** Chỉ báo coverage thực chạy, cấu hình job có Docker hoặc rõ skipped count.

## 18. Checklist hoàn tất Kafka integration tests

- [ ] Có chọn đúng tầng unit, Embedded Kafka, Testcontainers hay real cluster.
- [ ] Không mock KafkaTemplate trong test được gọi là broker integration.
- [ ] Có Kafka producer/consumer real config và serializer/deserializer đúng.
- [ ] Version Spring Boot/Spring Kafka/Testcontainers/BOM được pin.
- [ ] Embedded Kafka dùng đúng KRaft/bootstraps của nhánh version.
- [ ] Kafka container dùng đúng class, artifact và Docker image.
- [ ] Boot KafkaConnectionDetails trỏ tới container, không production broker.
- [ ] Topic thực sự được tạo với partition/replica phù hợp.
- [ ] Listener được assign trước khi test publish.
- [ ] Không dùng Thread.sleep làm điều kiện pass.
- [ ] Test chờ KafkaTemplate future và listener callback riêng.
- [ ] Có assert record key/value, metadata và headers.
- [ ] Không assert ordering toàn cục giữa partitions.
- [ ] Group ID/topic được cô lập, xử lý offset reset đúng.
- [ ] Không dùng probe consumer chung group với application ngoài ý muốn.
- [ ] DLT/retry/transaction chỉ được nhận là đã test khi có cấu hình/scenarios thật.
- [ ] Không nhầm broker ACK với consumer DB state/offset commit.
- [ ] Không nhầm Kafka transaction với distributed DB+Kafka XA.
- [ ] Docker/Testcontainers availability được kiểm tra và báo skip/fail rõ.
- [ ] Image/Kafka protocol version có compatibility test.
- [ ] Advertised listeners/network host/container phù hợp.
- [ ] TLS/SASL/ACL được test riêng nếu thuộc mục tiêu.
- [ ] Single-node không được gọi là multi-node availability test.
- [ ] Embedded broker lifecycle/context cache được quản lý.
- [ ] Tests chạy độc lập, không phụ thuộc thứ tự và không rò messages.
- [ ] Logs được redact, không chứa production credentials/PII.
- [ ] JUnit report có số tests thực chạy/pass/fail/skipped.
- [ ] Kết quả test không khẳng định những features chưa được cấu hình.

## 19. Kết luận

**Embedded Kafka** và **Kafka trong Testcontainers** đều cho phép kiểm thử Kafka broker integration thật, nhưng khác nhau về môi trường và mức độ giống deployment. Embedded không cần Docker, hợp lý cho nhiều integration tests chạy thường xuyên; Testcontainers dùng Kafka image/version xác định, phù hợp khi cần containerized broker compatibility và kết hợp với các dịch vụ khác.

Một bài test tốt không chỉ khởi động broker. Nó phải xác nhận **producer gửi được**, **listener đã sẵn sàng**, **consumer thực sự nhận được**, **message/metadata đúng** và **test state được cô lập**. Với retry, DLT, transactions, security hoặc high availability, cần bổ sung những suites riêng có cấu hình thực để tránh false confidence.

Ví dụ trong bài dùng cùng source production với cả hai test environments và **7 JUnit methods** (3 embedded, 4 container). Kết quả được mô tả như kỳ vọng theo API/version; chúng cần được biên dịch và chạy trong môi trường phù hợp trước khi coi là thực chứng cho ứng dụng cụ thể.

## Tài liệu tham khảo chính thức

- [Spring Kafka 3.3 — Testing Applications](https://docs.spring.io/spring-kafka/reference/3.3/testing.html): EmbeddedKafkaBroker, KRaft, @EmbeddedKafka, KafkaTestUtils, listener/offset notes và test lifecycle.
- [Spring Kafka 3.3 — EmbeddedKafka annotation API](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/test/context/EmbeddedKafka.html): broker options, topics, partitions, bootstrap property.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): @ServiceConnection, KafkaConnectionDetails, connection precedence.
- [Spring Boot 3.5 — Managed dependency coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Spring Kafka 3.3.x, Testcontainers 1.21.x modules.
- [Spring Boot 3.5 — Kafka messaging](https://docs.spring.io/spring-boot/3.5/reference/messaging/kafka.html): KafkaTemplate, KafkaAdmin, NewTopic, Kafka listeners.
- [Testcontainers Java — Kafka Module](https://java.testcontainers.org/modules/kafka/): ConfluentKafkaContainer, KafkaContainer, image versions, bootstrap servers và additional listeners.
- [Spring Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): KafkaTemplate async results.
- [Spring Kafka — Error Handling](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): DefaultErrorHandler, DLT/recoverer.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): Kafka transactions và consumer offset coordination.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): topics, partitions, consumer groups, offsets, producer transactions, durability.
