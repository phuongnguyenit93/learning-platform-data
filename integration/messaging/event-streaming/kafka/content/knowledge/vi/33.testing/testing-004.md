# Testcontainers và Embedded Kafka cho ứng dụng Java, Spring

Ứng dụng Java/Spring Kafka cần được kiểm thử với broker thật ở những điểm unit test không thể chứng minh: producer ghi đúng topic/key/header, consumer deserialize và commit offset đúng, retry/DLT hoạt động, listener xử lý record theo cấu hình thực tế. Hai lựa chọn phổ biến là **Embedded Kafka** do Spring Kafka cung cấp và **Testcontainers Kafka** chạy broker trong Docker.

Embedded Kafka khởi động broker trong tiến trình kiểm thử, phù hợp với test nhanh cho listener, producer và cấu hình Spring. Testcontainers khởi động Kafka trong container, giúp kiểm tra ứng dụng qua network và với Kafka distribution/config gần production hơn. Cả hai đều bổ sung cho unit test, contract test và end-to-end test.

## 1. Chọn đúng tầng kiểm thử

| Tầng | Mục tiêu | Có cần broker? |
|---|---|---|
| Unit test | Business logic, mapping, validation, key selection, retry classification | Không |
| Serialization test | Encode/decode, schema evolution, header mapping | Có thể không; cần Registry thật nếu kiểm tra integration |
| Spring integration test | Wiring bean, listener container, KafkaTemplate, error handler, transaction | Có |
| Contract test | Schema Registry, compatibility, connector/topic contract | Thường có service phụ trợ |
| End-to-end test | Source → Kafka → processor → sink/downstream | Có nhiều thành phần |
| Performance/chaos test | Throughput, latency, rebalance, broker failure, recovery | Cụm gần production |

Không khởi động broker cho mọi unit test. Tách logic thuần Java để chạy nhanh, dành Embedded Kafka hoặc Testcontainers cho hành vi phụ thuộc Kafka protocol và Spring listener lifecycle.

### Chọn Embedded Kafka khi

- Cần kiểm tra nhanh `@KafkaListener`, `KafkaTemplate`, serialization và consumer configuration.
- Test tập trung vào ứng dụng với một broker local.
- CI không có Docker hoặc cần suite chạy nhẹ.
- Muốn dùng trực tiếp `spring-kafka-test` và JUnit.

### Chọn Testcontainers khi

- Cần kiểm tra broker qua network và port mapping như ứng dụng production.
- Cần pin Kafka image/version hoặc broker properties cụ thể.
- Cần kết hợp Kafka với Schema Registry, database, Kafka Connect hoặc service khác.
- Cần kiểm tra listener, producer và AdminClient với Kafka distribution thực tế.
- CI có Docker hoặc môi trường container tương đương.

Hai cách có thể cùng tồn tại: Embedded Kafka cho suite nhanh, Testcontainers cho integration suite quan trọng hơn.

## 2. Dependency cho Maven và Gradle

Với Spring Boot, để dependency management của Spring Boot quản lý version `spring-kafka` và `spring-kafka-test` tương thích. Không tự chọn version Spring Kafka lệch khỏi dependency set của ứng dụng.

Ví dụ Maven:

~~~xml
<dependencies>
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
~~~

Quản lý Testcontainers bằng BOM để các module dùng cùng version:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>${testcontainers.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`testcontainers.version` là property do dự án chọn và pin theo release tương thích. Tên package của `KafkaContainer` thay đổi giữa một số major version Testcontainers; ví dụ dưới đây dùng API module Kafka mới với package `org.testcontainers.kafka.KafkaContainer`. Nếu dự án đang ở major version cũ, kiểm tra import và artifact name trong tài liệu đúng version.

Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.kafka:spring-kafka-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:kafka")
}
~~~

Nếu dùng Gradle, import Testcontainers BOM bằng dependency platform theo cách quản lý version của dự án. `spring-boot-starter-test` cung cấp JUnit Jupiter và thư viện assertion/mock thường dùng.

## 3. Embedded Kafka với Spring Kafka

Spring Kafka cung cấp test support trong artifact `spring-kafka-test`. Annotation `@EmbeddedKafka` khởi tạo broker embedded để test producer/consumer và Spring listener container mà không cần Docker.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest
@EmbeddedKafka(
    partitions = 3,
    topics = "orders.events",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class EmbeddedKafkaContextSmokeTest {

    @Test
    void applicationContextStartsWithEmbeddedBroker() {
        // Spring context và listener container đã được khởi tạo.
    }
}
~~~

`bootstrapServersProperty` đưa địa chỉ broker embedded vào property mà Spring Boot dùng để cấu hình producer/consumer. Cách này tránh hard-code port trong `application.yml`.

### Kiểm tra listener thực tế

Giả sử ứng dụng có listener:

~~~java
@Component
class OrderCreatedListener {

    private final OrderService orderService;

    OrderCreatedListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        topics = "${app.kafka.orders-topic}",
        groupId = "${spring.kafka.consumer.group-id}"
    )
    void onMessage(OrderCreated event) {
        orderService.handle(event);
    }
}
~~~

Có thể thay `OrderService` bằng test double trong test context, gửi event bằng `KafkaTemplate` rồi đợi assertion được gọi. Ví dụ:

~~~java
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(properties = {
    "app.kafka.orders-topic=orders.events",
    "spring.kafka.consumer.group-id=orders-listener-test",
    "spring.kafka.consumer.auto-offset-reset=earliest"
})
@EmbeddedKafka(
    partitions = 3,
    topics = "orders.events",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class OrderListenerEmbeddedKafkaTest {

    @Autowired
    KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @MockBean
    OrderService orderService;

    @Test
    void sendsEventToListener() throws Exception {
        OrderCreated event = new OrderCreated("order-1001");

        kafkaTemplate.send("orders.events", event.orderId(), event)
            .get(10, TimeUnit.SECONDS);

        verify(orderService, timeout(10_000)).handle(event);
    }
}
~~~

`@MockBean` minh họa Spring Boot test context; ở các version Spring Boot mới, API mock-bean có thể đã chuyển sang package/module mới. Có thể thay bằng `@MockitoBean` nếu version dự án yêu cầu. Hai snippet là hai test class riêng. Test phải xác nhận kết quả xử lý, không chỉ xác nhận lệnh `send()` hoàn tất.

`@DirtiesContext` đóng context sau test class để tránh broker/listener state bị dùng lại ngoài ý muốn. Không gắn annotation này máy móc vào mọi test vì nó làm tăng thời gian suite.

### Lưu ý với Embedded Kafka

- Chọn số partition đủ cho tình huống cần kiểm tra; một partition không chứng minh được parallelism nhiều partition.
- Dùng group ID riêng cho từng test suite để tránh committed offset còn sót.
- Cấu hình `auto-offset-reset` rõ ràng khi test consumer group mới.
- Tránh port cố định; để Spring test support công bố bootstrap servers.
- Không dùng `Thread.sleep()` để chờ listener; dùng Awaitility, latch hoặc Mockito timeout.
- Đóng consumer, producer và context đúng lifecycle.
- Kiểm tra `@DirtiesContext` khi suite chạy song song hoặc chia sẻ ApplicationContext.

Embedded Kafka có thể dùng KRaft hoặc ZooKeeper tùy version Spring Kafka và cấu hình. Những version mới chuyển sang broker embedded KRaft; nếu test phụ thuộc behavior cụ thể của KRaft, hãy kiểm tra version và cấu hình broker embedded đang dùng.

## 4. Testcontainers Kafka với JUnit 5

Testcontainers chạy Kafka trong Docker container và cung cấp bootstrap server đã map ra host. Ứng dụng test kết nối qua địa chỉ đó như kết nối broker bên ngoài.

Ưu điểm:

- Dùng image Kafka cụ thể, có thể pin version và cấu hình.
- Kiểm tra network, listener và client connection thực tế hơn embedded broker.
- Kết hợp được Kafka, Schema Registry, database, Connect worker hoặc service giả lập.
- Môi trường được tạo và dọn theo lifecycle của test.

Đổi lại, test cần Docker daemon, thời gian startup lớn hơn và tài nguyên CI nhiều hơn.

Ví dụ dùng module Kafka của Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class OrderKafkaContainerTest {

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse("apache/kafka-native:3.8.0")
        );

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers
        );
    }

    @Test
    void contextConnectsToKafkaContainer() {
        // Spring context dùng bootstrap server của container.
    }
}
~~~

Image tag là version minh họa. Chọn tag cụ thể được Testcontainers version đang dùng hỗ trợ, pin digest nếu chính sách CI yêu cầu và ưu tiên đồng bộ với production. Không dùng tag trôi nổi như `latest` vì test có thể thay đổi behavior mà không có commit code nào thay đổi.

`@Container static` khởi động một container dùng chung trong phạm vi test class. Field không static thường tạo container theo từng test method, phù hợp khi cần isolation mạnh nhưng tốn thời gian hơn.

### Cấp bootstrap server cho Spring Boot

`@DynamicPropertySource` đăng ký property động trước khi Spring context tạo bean. Nhờ đó `KafkaTemplate`, `ConsumerFactory`, `KafkaAdmin` và listener container đều dùng đúng broker đang chạy.

Không ghi `localhost:9092` vào test `application.yml`. Port được Docker map động; địa chỉ do `getBootstrapServers()` trả về mới là endpoint đúng từ JVM test.

### Tạo topic tường minh

Trong test có thể tạo topic bằng `KafkaAdmin` và `NewTopic`:

~~~java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.TopicBuilder;

@TestConfiguration
class KafkaTestTopics {

    @Bean
    NewTopic ordersEventsTopic() {
        return TopicBuilder.name("orders.events")
            .partitions(3)
            .replicas(1)
            .build();
    }
}
~~~

Đưa `KafkaTestTopics` vào test context bằng `@Import(KafkaTestTopics.class)` hoặc đặt nó thành nested `@TestConfiguration` trong test class. Ví dụ container chỉ có một broker nên replication factor phải là 1. Không đặt RF=3 trên broker đơn rồi kỳ vọng test kiểm tra replication giống production. Nếu cần kiểm thử ISR, leader election hoặc broker failure, dựng cụm nhiều broker riêng cho suite đó.

## 5. Kiểm thử producer và consumer qua broker thật

Một test producer/consumer cần chứng minh record đã được broker lưu và consumer đọc được key, value, header, partition hoặc timestamp cần thiết.

Ví dụ dùng `KafkaTemplate` và `KafkaConsumer` trực tiếp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;

class OrderProducerConsumerTest extends OrderKafkaContainerTest {

    private static final String TOPIC = "orders.events";

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Test
    void publishesRecordThatCanBeConsumed() throws Exception {
        String groupId = "test-" + UUID.randomUUID();
        Properties properties = new Properties();
        properties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            kafka.getBootstrapServers()
        );
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        properties.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        properties.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");

        try (Consumer<String, String> consumer =
                 new KafkaConsumer<>(properties)) {
            consumer.subscribe(List.of(TOPIC));
            long assignmentDeadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(10);
            while (consumer.assignment().isEmpty()
                    && System.nanoTime() < assignmentDeadline) {
                consumer.poll(Duration.ofMillis(100));
            }
            assertThat(consumer.assignment()).isNotEmpty();

            kafkaTemplate.send(TOPIC, "order-1001", "{\"status\":\"NEW\"}")
                .get(10, TimeUnit.SECONDS);

            ConsumerRecord<String, String> received = null;
            long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(10);

            while (received == null && System.nanoTime() < deadline) {
                var records = consumer.poll(Duration.ofMillis(200));
                for (ConsumerRecord<String, String> record : records) {
                    if ("order-1001".equals(record.key())) {
                        received = record;
                        break;
                    }
                }
            }

            assertThat(received).isNotNull();
            assertThat(received.value()).contains("\"NEW\"");
        }
    }
}
~~~

Đây là ví dụ về lifecycle consumer thủ công; trong dự án thực tế có thể tách fixture và cấu hình topic vào base test class hoặc `@TestConfiguration`. Nếu dùng Spring context, bảo đảm test class thực sự kế thừa/cấu hình container như ví dụ và không tạo container thứ hai ngoài ý muốn.

Khi test listener của ứng dụng, ưu tiên gửi qua `KafkaTemplate` rồi xác minh side effect ở service/repository hoặc test probe. Điều này bao phủ cả listener container và converter của Spring.

### Kiểm tra key và partition

- Hai record cùng key được route đến cùng partition trong cùng topic configuration.
- Consumer nhìn thấy thứ tự record theo partition.
- Key serializer không làm thay đổi giá trị key ngoài dự kiến.
- Null key hoặc key rỗng được xử lý theo policy đã định.

Không khẳng định thứ tự toàn cục giữa nhiều partition. Kafka chỉ đảm bảo ordering trong một partition.

## 6. Kiểm thử Spring Kafka listener và container

Listener có nhiều cấu hình ảnh hưởng behavior:

- `group.id`, `client.id` và concurrency.
- Manual/record/batch acknowledgment mode.
- `ackAfterHandle`, `ackOnError` và commit behavior.
- Deserializer, message converter và type headers.
- Error handler, retry, backoff và DLT recoverer.
- Pause/resume, poll timeout và max poll interval.
- Transaction manager và isolation level.

Integration test nên khởi động Spring context thật để xác minh các bean được wiring như production.

### Kiểm tra listener không commit khi xử lý thất bại

Thiết kế test để service ném exception ở lần đầu và xử lý thành công ở lần sau. Sau đó xác minh retry xảy ra đúng số lần, offset chỉ được commit theo semantics mong muốn và record không bị mất.

Không chỉ verify số lần gọi method. Nếu yêu cầu at-least-once, hãy kiểm tra side effect và record sau retry; nếu yêu cầu idempotency, gửi cùng event nhiều lần và xác nhận kết quả nghiệp vụ chỉ được áp dụng một lần.

### Kiểm tra batch listener

Với batch listener, kiểm thử record lỗi nằm ở giữa batch:

- Error handler có retry đúng record hay retry cả batch?
- Offset commit của record trước/sau record lỗi như thế nào?
- `BatchListenerFailedException` hoặc cơ chế tương đương có được dùng đúng?
- Record lỗi có vào DLT cùng metadata cần thiết?

Behavior phụ thuộc Spring Kafka version, acknowledgment mode và error handler. Test phải khớp cấu hình thực tế.

## 7. Kiểm thử retry, backoff và Dead Letter Topic

Một retry test nên kiểm tra cả luồng thành công và thất bại cuối cùng:

1. Gửi một record hợp lệ.
2. Gửi một record làm handler lỗi tạm thời.
3. Xác nhận số lần retry và khoảng backoff trong giới hạn cho phép.
4. Xác nhận record cuối cùng được xử lý hoặc chuyển DLT đúng policy.
5. Xác nhận header chứa thông tin exception/retry cần thiết.
6. Xác nhận record DLT giữ key, value và correlation ID.

Không dùng sleep cố định dài để chờ retry. Dùng Awaitility hoặc polling có deadline:

~~~java
await()
    .atMost(Duration.ofSeconds(15))
    .untilAsserted(() ->
        assertThat(deadLetterProbe.received())
            .extracting(ConsumerRecord::key)
            .contains("order-poison")
    );
~~~

`await()` ở ví dụ là API của Awaitility; thêm dependency test tương ứng nếu dự án chưa có. Đặt timeout đủ lớn cho CI nhưng không biến test thành chờ vô hạn.

Kiểm tra DLT:

- Topic name đúng với naming policy.
- Record được ghi đúng partition/key.
- Header retry count, original topic/partition/offset và exception metadata có mặt khi cấu hình yêu cầu.
- ACL của application cho phép publish DLT.
- Consumer DLT có thể deserialize payload lỗi hoặc lưu raw bytes để điều tra.
- Không có vòng lặp DLT-to-main vô hạn.

## 8. Kiểm thử transaction và processing guarantee

Với producer transaction, cần xác minh consumer đọc ở `read_committed` chỉ thấy record thuộc transaction đã commit.

Các tình huống nên có:

- Transaction commit: output records xuất hiện.
- Transaction abort: output records không xuất hiện với `read_committed`.
- Producer fencing: producer cũ không thể tiếp tục ghi sau khi bị producer mới thay thế cùng transactional identity.
- Consume-transform-produce: output và input offsets được commit trong cùng transaction khi dùng Kafka Streams EOS hoặc transactional consume-process-produce pattern phù hợp.

Không suy ra exactly-once end-to-end chỉ vì producer transaction test pass. Side effect ở database hoặc HTTP API cần idempotency, outbox/inbox hoặc transaction coordination riêng.

Test transaction nên dùng broker version/config tương thích production, topic phù hợp và consumer `isolation.level=read_committed`. Broker đơn vẫn có thể kiểm tra nhiều transaction semantics, nhưng không kiểm chứng fault tolerance của replication factor nhiều broker.

## 9. Kiểm thử schema và serialization

**Unit/compatibility test** nên xác minh:

- Avro/JSON/Protobuf object serialize và deserialize đúng.
- Field default, nullable, enum và logical type đúng.
- Schema evolution tương thích theo policy.
- Subject naming strategy đúng.
- Message key và value dùng đúng serializer.

**Integration test với Schema Registry** nên xác minh:

- Serializer đăng ký hoặc tìm schema đúng subject.
- Consumer resolve schema ID được.
- Schema references được xử lý.
- Compatibility mode từ chối schema không tương thích.
- Record đã ghi từ version cũ vẫn decode được.

Testcontainers Kafka không tự động cung cấp Schema Registry. Nếu ứng dụng dùng Confluent Schema Registry hoặc registry khác, khởi chạy thêm container/service tương thích hoặc dùng registry test chuyên dụng. Pin image version và cấu hình auth/TLS nếu cần kiểm tra contract bảo mật.

Không mock Schema Registry trong test duy nhất rồi kết luận wire format hoạt động. Record có schema ID trong payload cần registry tương ứng để consumer decode.

## 10. Kiểm thử consumer group, rebalance và concurrency

Các test nên bao gồm:

- Một consumer đọc nhiều partition.
- Nhiều consumer trong cùng group chia partition.
- Consumer mới tham gia làm rebalance.
- Consumer rời group hoặc mất heartbeat.
- Listener concurrency lớn hơn số partition.
- Partition bị revoke/assign và listener hoàn tất công việc đang xử lý theo policy.
- Commit offset và xử lý record trong thời gian rebalance.

Dùng nhiều consumer instance với group ID chung để kiểm tra assignment. Dùng `ConsumerRebalanceListener` hoặc event listener của Spring để quan sát partition assignment/revocation nếu cần.

Không khẳng định concurrency lớn hơn partition count làm tăng throughput tuyến tính. Một consumer group không thể có nhiều consumer đang sở hữu partition hơn số partition; consumer dư sẽ idle.

Với test rebalance, dùng Awaitility để đợi assignment ổn định và kiểm tra partition ownership. Tránh assert chính xác thời gian rebalance vài mili giây vì CI có thể chịu tải khác nhau.

## 11. Kiểm thử AdminClient và topic configuration

Các bài test provisioning nên xác nhận:

- Topic được tạo với partition count dự kiến.
- Replication factor phù hợp môi trường.
- `cleanup.policy`, `retention.ms`, `retention.bytes`, `min.insync.replicas` và `max.message.bytes` được áp dụng.
- Topic đã tồn tại được xử lý idempotently.
- ACL/authorization lỗi được báo rõ.

Ví dụ kiểm tra metadata bằng AdminClient:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;

try (Admin admin = Admin.create(Map.of(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
        kafka.getBootstrapServers()))) {
    var description = admin.describeTopics(
        List.of("orders.events")
    ).allTopicNames().get(10, TimeUnit.SECONDS);

    assertThat(description.get("orders.events").partitions())
        .hasSize(3);
}
~~~

API `describeTopics` có thể trả về `KafkaFuture`/map method khác đôi chút theo Kafka client version. Dùng API tương ứng dependency của dự án và chờ future với timeout hữu hạn.

## 12. Kiểm thử bảo mật

Broker embedded phù hợp với test logic và listener, nhưng không đại diện đầy đủ cho production TLS/SASL/ACL. Với security integration:

- Khởi động broker/container với listener và SASL mechanism tương ứng.
- Dùng test certificate hoặc credential không có quyền truy cập dữ liệu thật.
- Kiểm tra handshake thành công và thất bại.
- Kiểm tra principal chỉ có quyền cần thiết.
- Kiểm tra producer không ghi được topic ngoài scope.
- Kiểm tra consumer không đọc được group/topic bị cấm.
- Kiểm tra secret không bị in trong log hoặc exception message.

Không đưa private key production, password thật hoặc token lâu dài vào test fixture. Tạo credential tạm trong CI và xóa sau test.

Một test bảo mật tốt có cả assertion positive và negative: client hợp lệ thực hiện được thao tác cần thiết, client thiếu ACL bị từ chối.

## 13. Testcontainers cho nhiều service

Khi pipeline dùng Kafka cùng database và Schema Registry, Testcontainers có thể tạo môi trường tích hợp gần production:

~~~mermaid
flowchart LR
    TEST["JUnit test"] --> APP["Spring Boot app"]
    APP --> KAFKA["Kafka container"]
    APP --> SCHEMA["Schema Registry container"]
    CONNECT["Connect worker container"] --> KAFKA
    CONNECT --> DB["Database container"]
    APP --> DB
~~~

Tổ chức container bằng `@Container` hoặc container composition theo lifecycle của test. Dùng network chung nếu service cần gọi nhau bằng alias nội bộ; không tự ghép hostname/port trước khi container khởi động.

Một integration test nhiều container cần kiểm tra:

- Kafka đã sẵn sàng trước khi app/Connect bắt đầu.
- Schema Registry kết nối đúng Kafka hoặc storage backend theo cấu hình.
- Database có schema/table/slot/log retention cần thiết.
- Connect plugin được cài và connector task chuyển sang RUNNING.
- Producer/consumer có thể serialize/deserialize và đọc/ghi.
- Dữ liệu test được dọn hoặc dùng namespace riêng để tránh test phụ thuộc thứ tự.

Không khởi động toàn bộ stack cho mọi test. Chia suite theo nhóm để thời gian CI và tài nguyên vẫn kiểm soát được.

## 14. So sánh Embedded Kafka và Testcontainers

| Tiêu chí | Embedded Kafka | Testcontainers Kafka |
|---|---|---|
| Khởi động | Trong JVM test | Docker container |
| Tốc độ | Thường nhanh hơn | Chậm hơn do pull/start container |
| Docker | Không cần | Cần Docker/runtime tương đương |
| Network/port mapping | Mô hình local embedded | Gần cách client kết nối broker ngoài |
| Broker version | Theo dependency Spring Kafka | Chọn image Kafka cụ thể |
| Nhiều service | Hạn chế, phải tự dựng | Kết hợp container thuận tiện |
| TLS/SASL/ACL | Có thể cấu hình nhưng không phải mục tiêu mặc định | Phù hợp hơn cho integration test bảo mật |
| Nhiều broker/failure test | Có thể nhưng phức tạp | Có thể dựng cluster, tốn tài nguyên |
| Dọn môi trường | Theo lifecycle context | Container được dọn theo lifecycle |
| Phù hợp | Listener, producer, consumer và Spring wiring | Protocol, broker config, network và service integration |

Không có lựa chọn nào tự động chứng minh production readiness. Testcontainers một broker vẫn không kiểm chứng replica failover, ISR hoặc rack awareness của cụm nhiều broker.

## 15. Tổ chức test suite trong CI

Một pipeline CI có thể chia thành:

1. Unit test chạy ở mọi commit.
2. Embedded Kafka test chạy cùng bộ integration nhanh.
3. Testcontainers Kafka chạy trên runner có Docker.
4. Schema/Connect/DB contract suite chạy khi thay đổi dependency tương ứng.
5. Performance, multi-broker và chaos test chạy theo lịch hoặc trước release lớn.

### Cấu hình Maven Surefire/Failsafe

Theo quy ước Maven, unit test thường chạy qua Surefire; integration test có thể dùng Failsafe với tên class `*IT`. Ví dụ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>${maven-failsafe-plugin.version}</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Version plugin cần được pin theo Maven/build policy của dự án. Chạy integration suite bằng:

~~~bash
mvn verify
~~~

Nếu CI chia stage, bảo đảm `verify` chạy sau `integration-test` để Failsafe tổng hợp kết quả và fail build khi integration test lỗi.

### CI cần chuẩn bị gì?

- Docker daemon khả dụng cho Testcontainers.
- Quyền pull image từ registry.
- Cache image/dependency hợp lý để giảm thời gian.
- Giới hạn CPU/RAM và thời gian startup.
- Port được map động, không hard-code cổng dùng chung.
- Test report và log container được lưu khi fail.
- Credential test tạm thời, không dùng secret production.
- Parallel execution không chia sẻ topic/group ID gây xung đột.

Khi chạy test song song, đặt topic và group ID unique theo test run hoặc test class. Không cho hai test cùng reset consumer group hoặc xóa topic mà test khác đang dùng.

## 16. Tránh test flaky

| Nguyên nhân | Cách xử lý |
|---|---|
| Gửi record trước khi consumer subscribe/assign | Khởi tạo consumer, poll đến khi assignment sẵn sàng rồi mới gửi |
| Consumer group dùng offset cũ | Dùng group ID riêng và reset policy rõ ràng |
| Chờ bằng `Thread.sleep()` | Dùng Awaitility, latch hoặc polling có deadline |
| Topic auto-create không ổn định | Tạo topic tường minh bằng AdminClient/KafkaAdmin |
| Test chia sẻ topic | Dùng topic namespace unique hoặc dọn dữ liệu có kiểm soát |
| Container chưa ready | Dùng wait strategy và startup timeout phù hợp |
| Port cố định bị chiếm | Dùng bootstrap server/port mapping động |
| Test phụ thuộc thứ tự | Mỗi test tự chuẩn bị dữ liệu và state |
| Assertion chỉ kiểm tra `send()` | Kiểm tra record thực sự được consume hoặc side effect hoàn tất |
| Timeout quá ngắn trên CI | Chọn deadline theo môi trường, log trạng thái khi timeout |

Không tăng timeout vô hạn để che lỗi. Khi test timeout, ghi nhận topic, partition, group, offset, container log và listener error để chẩn đoán.

## 17. Test data và cleanup

Kafka không có thao tác xóa một record cụ thể khỏi topic. Vì vậy test data nên có namespace riêng:

- Topic theo test class hoặc UUID.
- Key có prefix test run.
- Consumer group ID riêng.
- Database schema/table riêng hoặc transaction rollback nếu phù hợp.
- Dọn topic/container sau suite thay vì cố xóa record từng test.

Nếu dùng topic cố định để giảm startup, test phải kiểm soát offset và correlation ID. Tránh assert “record đầu tiên” khi topic có thể chứa record từ lần chạy trước.

Với listener ghi database, chỉ kiểm tra database sau khi xác nhận transaction commit. Dùng Awaitility để đợi trạng thái cuối thay vì giả định listener xử lý đồng bộ ngay khi `KafkaTemplate.send()` trả về.

## 18. Kiểm thử failure và recovery

Một suite gần production nên có các scenario:

- Broker container restart trong lúc consumer đang đọc.
- Producer retry khi broker tạm unavailable.
- Consumer bị dừng giữa xử lý và khởi động lại.
- Rebalance khi instance mới tham gia/rời group.
- DLT unavailable hoặc publish DLT bị từ chối.
- Schema Registry tạm unavailable.
- Connect task restart và resume source offset.
- Kafka Streams restore state từ changelog.
- Topic hết retention hoặc consumer lag vượt retention.

Những bài test này có thể cần nhiều broker, network fault injection hoặc môi trường staging. Không cố nhồi tất cả vào một unit/integration suite chạy mỗi commit.

Khi kiểm tra broker failure, đo:

- Thời gian phát hiện và phục hồi.
- Produce/consume error rate.
- Consumer lag và thời gian catch-up.
- Partition leader/ISR sau phục hồi.
- Duplicate/missing theo business invariant.
- RPO/RTO thực tế so với mục tiêu.

## 19. Checklist chọn công cụ và review test

### Trước khi viết test

- [ ] Xác định behavior cần chứng minh và tầng test phù hợp.
- [ ] Chọn Embedded Kafka hoặc Testcontainers theo dependency.
- [ ] Pin Spring Kafka, Kafka client, Testcontainers và broker image.
- [ ] Xác định topic, partition, group ID và retention của test.
- [ ] Quyết định test cần một broker hay nhiều broker.
- [ ] Tạo test data có correlation ID và cleanup strategy.

### Khi viết test

- [ ] Cấu hình bootstrap server động.
- [ ] Tạo topic tường minh khi cần.
- [ ] Không dùng `Thread.sleep()` làm cơ chế đồng bộ chính.
- [ ] Chờ kết quả bằng timeout hữu hạn.
- [ ] Kiểm tra key, value, header, partition và side effect cần thiết.
- [ ] Xác minh retry, DLT, offset và transaction semantics.
- [ ] Đóng consumer/producer và container đúng lifecycle.

### Trước khi merge

- [ ] Unit và integration suite chạy ổn định nhiều lần.
- [ ] Testcontainers chạy được trên CI runner.
- [ ] Test không phụ thuộc thứ tự hoặc dữ liệu tồn dư.
- [ ] Log và report có đủ thông tin chẩn đoán.
- [ ] Security test không chứa secret production.
- [ ] Các giới hạn của broker đơn được ghi rõ.

## 20. Bài tập tự kiểm tra

1. Embedded Kafka khác Testcontainers Kafka ở lifecycle và network như thế nào?
2. Khi nào unit test không cần khởi động broker?
3. Vì sao phải dùng `@DynamicPropertySource` cho bootstrap server của container?
4. Vì sao broker đơn không kiểm tra được replication factor 3?
5. Làm thế nào test `@KafkaListener` của Spring?
6. Cần kiểm tra gì ngoài việc `KafkaTemplate.send()` hoàn tất?
7. Làm thế nào test retry, DLT và offset commit?
8. Vì sao schema registry cần được test riêng với broker?
9. Làm thế nào tránh consumer đọc nhầm record của test run trước?
10. Khi nào cần multi-broker hoặc failure test gần production?

## Kết luận

Embedded Kafka và Testcontainers là hai công cụ bổ sung cho nhau khi kiểm thử ứng dụng Java/Spring Kafka. Embedded Kafka phù hợp với test nhanh cho Spring wiring, listener, producer và consumer. Testcontainers phù hợp khi cần broker trong container, network thực tế hơn, pin image version và phối hợp nhiều service.

Hãy chọn công cụ theo behavior cần chứng minh. Unit test giữ logic thuần Java chạy nhanh; integration test xác minh broker, listener, serialization, retry, DLT, transaction và offset; contract/E2E test xác minh Schema Registry, Connect, Streams và downstream. Một suite đáng tin cần bootstrap server động, topic/group riêng, chờ bất đồng bộ có timeout, test data cô lập và chạy ổn định trong CI. Với replication, security, performance và broker failure, dùng môi trường nhiều broker gần production thay vì suy luận từ một broker embedded hoặc container đơn.
