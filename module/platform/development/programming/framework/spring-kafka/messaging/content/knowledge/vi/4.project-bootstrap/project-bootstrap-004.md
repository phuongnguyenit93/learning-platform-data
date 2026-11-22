# Khai báo dependency cho kiểm thử Kafka

Kiểm thử ứng dụng Spring Kafka cần hai nhóm công cụ: công cụ kiểm thử ứng dụng Spring và công cụ hỗ trợ dựng Kafka broker trong môi trường test. Dependency phù hợp giúp kiểm tra producer, consumer, serialization và luồng sự kiện một cách lặp lại được, không phụ thuộc vào Kafka đang chạy trên máy cá nhân hay môi trường dùng chung.

Trong module `SPRING_KAFKA_MESSAGING`, ứng dụng gửi sự kiện bằng `KafkaTemplate` và nhận sự kiện bằng `@KafkaListener`. Vì vậy, bộ dependency kiểm thử nên hỗ trợ cả kiểm thử Spring context lẫn kiểm thử tương tác thật với broker.

## 1. Hai dependency nền tảng

### spring-boot-starter-test

`spring-boot-starter-test` cung cấp nền tảng kiểm thử quen thuộc của Spring Boot, thường bao gồm:

- JUnit Jupiter để viết và chạy test.
- Spring Test để khởi tạo application context và kiểm thử bean.
- AssertJ để viết assertion dễ đọc.
- Mockito để mock dependency khi kiểm thử đơn vị.

Dependency này phù hợp cho kiểm thử service, business logic, cấu hình Spring và các thành phần không cần Kafka broker thật.

### spring-kafka-test

`spring-kafka-test` bổ sung các tiện ích dành riêng cho Spring Kafka:

- `@EmbeddedKafka` và `EmbeddedKafkaBroker` để chạy Kafka broker nhúng trong tiến trình kiểm thử.
- `KafkaTestUtils` để tạo consumer/producer properties và hỗ trợ đọc record.
- `ContainerTestUtils` để chờ listener container được gán partition.
- Các thành phần hỗ trợ kiểm tra luồng gửi, nhận và xử lý record.

Dependency này có scope kiểm thử. Nó không phải dependency để ứng dụng production khởi chạy Kafka broker.

## 2. Khai báo với Maven

Nếu dự án sử dụng Spring Boot parent hoặc import Spring Boot dependency management, có thể khai báo hai dependency mà không cần ghi version riêng:

```xml
<dependencies>
    <!-- Các dependency chạy ứng dụng, ví dụ spring-kafka,
         được khai báo ở phần dependency chính của dự án. -->

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
</dependencies>
```

Spring Boot dependency management quản lý các version tương thích trong hệ sinh thái Spring Boot. `spring-kafka-test` nên đi cùng version Spring Kafka mà ứng dụng đang sử dụng. Nếu dự án không dùng BOM hoặc parent của Spring Boot, cần khai báo version rõ ràng và tự bảo đảm các module Spring Kafka tương thích với nhau.

Sau khi thêm dependency, chạy:

```bash
./mvnw test
```

Trên Windows có thể dùng:

```powershell
.\mvnw.cmd test
```

## 3. Khai báo với Gradle

Với Gradle Groovy DSL:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

Với Gradle Kotlin DSL:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
```

Nếu dự án đã áp dụng Spring Boot Gradle plugin hoặc Spring dependency management, version thường được quản lý tập trung. Nếu không, hãy import BOM phù hợp hoặc chỉ định version đồng bộ cho các dependency Spring Boot và Spring Kafka.

Chạy test bằng:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

## 4. Chọn cách cung cấp Kafka broker cho test

Có ba cấp độ kiểm thử thường dùng. Chọn cấp độ dựa trên hành vi cần xác minh.

| Cách kiểm thử | Broker | Phù hợp để kiểm tra |
|---|---|---|
| Unit test | Không cần broker | Business logic, xử lý lỗi và lời gọi đến `KafkaTemplate` |
| Embedded Kafka | Broker nhúng trong tiến trình test | Producer, consumer, listener, serialization và luồng record |
| Testcontainers | Kafka chạy trong container | Tích hợp gần môi trường triển khai, cấu hình mạng và tương thích broker |

### Unit test không cần Kafka

Nếu mục tiêu chỉ là kiểm tra service quyết định gửi sự kiện nào, có thể mock `KafkaTemplate`. Test chạy nhanh và không cần thêm broker.

Ví dụ minh họa:

```java
@ExtendWith(MockitoExtension.class)
class OrderEventServiceTest {

    @Mock
    private KafkaTemplate<String, String> kafkaTemplate;

    @InjectMocks
    private OrderEventService orderEventService;

    @Test
    void publishesOrderCreatedEvent() {
        orderEventService.publishCreated("order-42");

        verify(kafkaTemplate).send(
            "orders",
            "order-42",
            "ORDER_CREATED"
        );
    }
}
```

Unit test này xác minh service gọi đúng topic, key và payload. Nó không chứng minh broker nhận được record hoặc consumer giải mã được record. Những hành vi đó cần integration test.

### Embedded Kafka với spring-kafka-test

Embedded Kafka phù hợp cho phần lớn integration test cần broker thật nhưng muốn chạy gọn trong test suite, không phụ thuộc Docker.

Khai báo `@EmbeddedKafka` sẽ khởi tạo broker nhúng và tạo topic phục vụ test. Thuộc tính `bootstrapServersProperty` đưa địa chỉ broker vào cấu hình Spring Boot để `KafkaTemplate` và các listener container dùng cùng broker.

Ví dụ kiểm tra một record được gửi vào topic:

```java
@SpringBootTest(properties = {
    "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderPublisherIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Test
    void publishesRecordToOrdersTopic() throws Exception {
        Map<String, Object> consumerProperties = new HashMap<>();
        consumerProperties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            embeddedKafka.getBrokersAsString()
        );
        consumerProperties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-test-group"
        );
        consumerProperties.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest"
        );
        consumerProperties.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class
        );
        consumerProperties.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class
        );

        try (Consumer<String, String> consumer =
                 new KafkaConsumer<>(consumerProperties)) {

            embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");

            kafkaTemplate.send(
                "orders",
                "order-42",
                "ORDER_CREATED"
            ).get(10, TimeUnit.SECONDS);

            ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofSeconds(10));

            assertThat(records.records("orders")).isNotEmpty();

            ConsumerRecord<String, String> record =
                records.records("orders").iterator().next();

            assertThat(record.key()).isEqualTo("order-42");
            assertThat(record.value()).isEqualTo("ORDER_CREATED");
        }
    }
}
```

Các import quan trọng trong ví dụ:

```java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

import static org.assertj.core.api.Assertions.assertThat;
```

Trong test thực tế, các class ứng dụng và cấu hình serializer/deserializer phải khớp với kiểu dữ liệu của topic. Ví dụ trên dùng `StringSerializer` và `StringDeserializer` để tập trung vào cơ chế gửi/nhận cơ bản. Nếu ứng dụng gửi DTO JSON, hãy cấu hình `JsonSerializer` và `JsonDeserializer` tương ứng rồi kiểm tra cả quá trình chuyển đổi object.

### Kiểm thử @KafkaListener

Khi cần xác minh listener nhận và xử lý record, có thể dùng `@EmbeddedKafka` cùng một cơ chế đồng bộ trong test, chẳng hạn `BlockingQueue`, `CountDownLatch` hoặc Awaitility. Không nên dùng `Thread.sleep()` cố định vì thời gian xử lý thay đổi theo máy chạy test.

Nếu cần bảo đảm listener đã nhận partition trước khi gửi record, `ContainerTestUtils.waitForAssignment(...)` trong `spring-kafka-test` có thể chờ listener container được gán đủ partition. Cách này tránh race condition giữa thời điểm test gửi record và thời điểm listener sẵn sàng.

## 5. Dùng Testcontainers khi cần môi trường gần production

Embedded Kafka kiểm tra được nhiều hành vi của producer và consumer, nhưng không đại diện đầy đủ cho topology triển khai thực tế. Khi cần kiểm tra broker chạy trong container, cấu hình listener, kết nối qua Docker network hoặc hành vi theo phiên bản Kafka cụ thể, có thể dùng Testcontainers.

Với Testcontainers 1.x, các dependency thường dùng là:

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>kafka</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Nên import Testcontainers BOM để quản lý version đồng bộ. Tên artifact và package Java có thể thay đổi giữa các major version của Testcontainers; hãy dùng module Kafka và JUnit Jupiter tương ứng với major version đã chọn, không trộn dependency của các major version khác nhau.

Luồng cấu hình điển hình với JUnit 5:

1. Khai báo Kafka container bằng `@Container`.
2. Dùng `@Testcontainers` để tích hợp vòng đời container với JUnit.
3. Đăng ký `getBootstrapServers()` vào property `spring.kafka.bootstrap-servers` bằng `@DynamicPropertySource`.
4. Chạy integration test với `@SpringBootTest` như khi dùng broker khác.

Ví dụ dưới đây dùng API Testcontainers 1.x và image Confluent Kafka tương thích với API đó:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class KafkaContainerIntegrationTest {

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse("confluentinc/cp-kafka:7.6.1")
        );

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers
        );
    }

    // Các integration test của ứng dụng đặt tại đây.
}
```

Testcontainers cần Docker daemon hoạt động trên máy hoặc CI runner. Chọn image và version broker phù hợp với môi trường triển khai; nếu hệ thống dùng TLS, SASL, nhiều listener hoặc nhiều broker, cần mở rộng cấu hình container để mô phỏng các điều kiện đó. Với Testcontainers 2.x, module Kafka và package Java đã thay đổi; hãy chuyển sang API/artifact tương ứng của major version đó thay vì trộn với dependency 1.x trong ví dụ.

## 6. Những kiểm thử nên có cho Spring Kafka

Khi đã khai báo dependency, hãy xây dựng test theo rủi ro của luồng messaging:

- **Producer**: kiểm tra topic, key, payload, header và kết quả gửi.
- **Serialization**: kiểm tra object được chuyển thành bytes và giải mã đúng kiểu dữ liệu.
- **Consumer**: kiểm tra listener nhận record và gọi đúng nghiệp vụ.
- **Consumer group**: kiểm tra listener container được gán partition phù hợp với số consumer và partition.
- **Retry và dead-letter**: xác minh số lần thử, điều kiện chuyển record sang DLT và nội dung record sau khi chuyển.
- **Transaction**: kiểm tra các thao tác Kafka cần commit hoặc rollback cùng nhau.
- **Lỗi broker**: kiểm tra ứng dụng phản ứng đúng khi broker tạm thời không sẵn sàng, nếu đây là yêu cầu của hệ thống.

Không cần đưa mọi trường hợp vào một integration test lớn. Unit test nên bao phủ logic nghiệp vụ; integration test với Embedded Kafka kiểm tra tương tác Kafka thường gặp; Testcontainers dành cho các khác biệt có ý nghĩa giữa môi trường test và môi trường triển khai.

## 7. Lỗi thường gặp khi khai báo dependency

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy `@EmbeddedKafka` | Thiếu `spring-kafka-test` hoặc dependency chưa được đồng bộ | Thêm dependency ở scope test và reload Maven/Gradle |
| Không tìm thấy `@SpringBootTest` hoặc JUnit extension | Thiếu `spring-boot-starter-test` | Thêm starter ở scope test |
| Lỗi `NoSuchMethodError` trong test | Version `spring-kafka-test` lệch với `spring-kafka` | Dùng Spring Boot BOM hoặc đồng bộ version |
| Test không kết nối được broker | Ứng dụng đang dùng bootstrap server khác broker nhúng | Cấu hình `bootstrapServersProperty` hoặc property tương ứng |
| Test listener lúc qua lúc trượt | Gửi record trước khi listener được gán partition | Chờ assignment hoặc dùng cơ chế đồng bộ thay vì sleep |
| Testcontainers không khởi động | Docker không chạy hoặc image không tương thích | Kiểm tra Docker daemon, image và version Testcontainers |

Sau khi sửa dependency, hãy reload project để IDE và build tool nhận classpath mới. Nếu test chạy từ IDE nhưng thất bại trong CI, kiểm tra Docker availability, Java version, dependency cache và cấu hình mạng của runner.

## 8. Nguyên tắc chọn dependency

Với phần lớn dự án Spring Kafka, hai dependency nên có trong test scope là:

- `spring-boot-starter-test` cho JUnit, Spring Test, assertion và mock.
- `spring-kafka-test` cho Embedded Kafka và các tiện ích kiểm thử Kafka.

Chỉ bổ sung Testcontainers khi cần xác minh hành vi phụ thuộc vào broker/container hoặc môi trường gần production. Giữ dependency kiểm thử ở test scope để chúng không trở thành thành phần runtime của ứng dụng.

Khi dependency đã được khai báo đúng và đồng bộ version, nhóm có thể kiểm tra luồng `KafkaTemplate` → broker → `@KafkaListener` một cách tự động, lặp lại được trong local và CI.

