# Messaging — Dọn broker state, offset và tài nguyên sau từng nhóm test

## 1. Vì sao “test đã kết thúc” không đồng nghĩa broker đã sạch?

Trong kiểm thử messaging, một test gửi sự kiện `OrderCreated` qua Kafka rồi assert consumer đã nhận đúng payload. JUnit báo xanh. Test kế tiếp cũng dùng topic `orders` và group `order-processor` nhưng nhận thêm một record cũ, hoặc không nhận được record mới vì group đã commit offset từ lần chạy trước. Một số test còn giữ consumer thread, AMQP queue chưa ack, dead-letter messages, Kafka Streams state store, listener container hoặc connection pool sau khi assertions đã hoàn thành.

Không có gì mâu thuẫn: **broker là hệ thống có trạng thái**, không phải một Java mock chỉ sống trong một method.

Một nhóm test messaging cần phân biệt ít nhất bốn loại state:

1. **Message state:** Kafka records trên partitions; RabbitMQ messages trong queues/DLQ; JMS messages và durable subscriptions.
2. **Consumer progress:** Kafka group committed offsets; RabbitMQ acknowledgments/in-flight messages; JMS acknowledgments/session transactions.
3. **Broker metadata:** Kafka topics/partitions/group metadata, ACL/config, RabbitMQ exchanges/queues/bindings/vhosts, JMS destinations/subscriptions.
4. **Client/process resources:** producers, consumers, Spring listener containers, channels/connections, `AdminClient`, executors, Testcontainers containers và Spring `ApplicationContext` cache.

**Chỉ xóa messages không có nghĩa đã reset consumer progress.** Đặc biệt với Kafka, **xóa topic không mặc nhiên xóa mọi consumer-group offsets ngay lập tức**, và cấu hình `auto.offset.reset=earliest` không tự đưa một group đã commit về offset 0. Nếu còn committed offset hợp lệ, consumer thường bắt đầu tại offset đã commit.

Bài này giải thích cách **dọn broker state, offset và tài nguyên sau từng nhóm test**, với ví dụ runnable **Java 17 + Spring Boot 3.3 + Spring Kafka + Kafka Testcontainers + JUnit Jupiter**, rồi mở rộng sang RabbitMQ và JMS. Mục tiêu là có tests độc lập, có thể chạy lặp lại, không phá dữ liệu của shared broker, và không nhầm cleanup với xác minh business behavior.

## 2. Những điều cần nắm sau bài

Sau khi hoàn thành, bạn có thể:

1. Chỉ ra sự khác nhau giữa Kafka message log, current consumer position và committed group offset.
2. Giải thích chính xác tác động của `group.id`, `auto.offset.reset`, `enable.auto.commit`, `commitSync` và `seekToBeginning`.
3. Phân biệt **tạo consumer group mới**, **reset offsets**, **xóa consumer group** và **xóa topic** — chúng không đồng nghĩa.
4. Thiết kế isolation cho từng `@Test`, test class, test suite hoặc CI run.
5. Tổ chức `@BeforeEach`/`@AfterEach`/`@AfterAll` và `@Testcontainers` lifecycle theo đúng scope.
6. Viết Kafka integration tests dùng topic/group ngẫu nhiên, Kafka producer thật, consumer thật, manual offset commit và deadlines hữu hạn.
7. Đóng consumers trước khi xóa group/topic và tránh `GroupNotEmpty`/consumer-rebalance race.
8. Biết khi nào **không cần cố xóa từng group offset** vì broker test container được hủy hoàn toàn sau test class.
9. Xử lý cleanup khi assertions fail; không được nuốt lỗi teardown quan trọng.
10. Tránh cleanup có tính phá hủy trên shared staging/production broker.
11. Hiểu RabbitMQ `ack`/`nack`, unacked messages, queue purge/delete, DLQ và vhost isolation.
12. Hiểu JMS durable subscriptions, unacknowledged deliveries, sessions và destination lifecycle.
13. Chẩn đoán test chạy riêng xanh nhưng chạy cả suite đỏ do state cũ, context cache, listener rebalances và parallelism.
14. Báo rõ test đã execute, broker nào đã dùng, state nào đã được reset và giới hạn kết luận.

## 3. Một ma trận “phải dọn gì?” theo loại broker

| Hệ thống | Dữ liệu chính | Tiến độ tiêu thụ | Metadata/resources dễ sót |
| --- | --- | --- | --- |
| Kafka | Records theo topic-partition, retention/compaction | Group committed offsets trong Kafka broker; consumer position trong client | Topics, consumer group metadata, stream state stores, transactions, producers, listeners, admin clients |
| RabbitMQ | Ready messages trên queues, DLQ/delayed queues | Acknowledgments, unacked deliveries, consumer/channel state | Exchanges, bindings, queues, vhosts, connections/channels, retry/DLQ |
| JMS/ActiveMQ Artemis | Queue/topic messages, DLQ | Acknowledgments, transacted sessions, durable subscription cursor | Durable subscriptions, destinations, sessions, connections, client IDs |
| Pulsar | Topic ledger/backlog | Subscription cursor/ack state | Subscriptions, namespaces, tenants, topics, producers/consumers |
| Redis Streams | Stream entries | Consumer group pending-entry list, last-delivered ID | Streams, groups, consumers, keys, TTL |

Bài runnable dùng Kafka vì **offset** là khái niệm trung tâm. Nhưng tư duy rộng hơn là: **message data, consumer progress và client lifecycle là những nguồn state khác nhau**.

### 3.1. Test cleanup không thay thế một test oracle tốt

Test có thể dọn sạch mọi thứ nhưng vẫn không kiểm tra đúng nghiệp vụ. Ví dụ `assertNotNull(kafkaTemplate)` và xóa topic cuối method không chứng minh record được gửi, key/value serialization đúng, consumer đọc hay commit offset đúng.

Một integration test đáng tin nên có:

- Input/fixture cụ thể.
- Action gửi/nhận trên broker thật hoặc engine test được xác định.
- Assertion về payload/key/headers hoặc committed offset theo hợp đồng.
- Deadline/timeouts hữu hạn.
- Cleanup state/resources tương ứng với scope đã cấp.

## 4. Ba khái niệm Kafka phải tách biệt

### 4.1. Log offset thuộc topic-partition

Kafka lưu records theo từng partition. Mỗi record có `offset` tăng dần trong **partition đó**. Offset không phải ID toàn cục của mọi topic.

Ví dụ:

```text
topic: orders-it-001, partition 0

offset 0 -> key order-1, value CREATED
offset 1 -> key order-2, value CREATED
offset 2 -> key order-3, value CANCELLED
```

Nếu chỉ tạo một partition, mỗi record được append theo thứ tự trong partition. Với nhiều partitions, không có một thứ tự tổng tuyệt đối giữa partitions.

**Offset chỉ có nghĩa cùng với topic và partition.** Đừng assert “offset cuối cùng là 3” nếu tests khác có thể append vào cùng partition.

### 4.2. Consumer position thuộc consumer instance

Khi một `KafkaConsumer` đang poll records, nó có một **vị trí đọc hiện tại** cho từng partition được gán. `position(tp)` biểu diễn offset của record tiếp theo mà consumer sẽ đọc ở partition đó.

Position có thể tiến sau `poll()` **trước khi commit**. Nếu consumer chết ngay sau khi xử lý message mà chưa commit, một consumer mới cùng group có thể đọc lại record từ committed offset cũ.

### 4.3. Group committed offset sống ở broker

Kafka lưu offset mà consumer group đã commit. Nó thường là **offset kế tiếp cần đọc**, không phải offset cuối cùng đã xử lý.

Ví dụ:

```text
Consumer đọc record offset 0, xử lý thành công.
commitSync() commits offset 1.

Consumer cùng group khởi động lại:
-> vị trí đọc tiếp thường bắt đầu từ offset 1.
Consumer group mới, auto.offset.reset=earliest:
-> bắt đầu từ earliest available record, thường offset 0
   trong một test topic mới.
```

Nhầm position, committed offset và message log là nguyên nhân phổ biến khiến tests “mất” hoặc “lặp” messages.

## 5. `auto.offset.reset=earliest` không phải nút dọn broker

Cấu hình Kafka:

```properties
spring.kafka.consumer.auto-offset-reset=earliest
```

được dùng khi consumer group **không có committed offset** cho partition hoặc committed offset không còn hợp lệ vì data đã bị xóa/retention. Nếu group đã commit một offset hợp lệ, `earliest` không làm consumer quay về đầu log.

| Trạng thái | `auto.offset.reset=earliest` làm gì? |
| --- | --- |
| Group mới, chưa có offset | Đọc từ earliest available offset |
| Group đã commit offset 12 còn hợp lệ | Bắt đầu từ committed offset 12 |
| Group offset trỏ ra khỏi retention range | Có thể reset theo policy |
| Code gọi `seekToBeginning` sau assignment | Local consumer position thay đổi; không tự xóa group commit |
| Group cũ được xóa hoàn toàn, group id dùng lại | Group không còn stored progress; lần sau áp dụng reset policy |
| Topic xóa nhưng group metadata còn trong broker một thời gian | Không được mặc định mọi offsets/group records biến mất đồng bộ |

**Không sửa test “không thấy message” bằng cách đổi `latest` sang `earliest` rồi tuyên bố đã reset offset.** Hãy hỏi group ID là gì, đã commit offset nào, topic bắt đầu từ offset nào và consumer đã join group/được assign chưa.

## 6. Khi nào group offset được commit?

### 6.1. Auto commit

`enable.auto.commit=true` khiến Kafka consumer định kỳ tự commit positions theo cấu hình. Việc test chỉ `poll` rồi chờ vài giây có thể tạo tiến độ group khó kiểm soát và flakiness.

Với các test minh họa offset semantics, dùng:

```java
props.put(
        ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
        false);
```

Sau khi kiểm tra xử lý thành công, gọi `commitSync()` tường minh.

### 6.2. Manual commit

```java
try (KafkaConsumer<String, String> consumer =
             createConsumer(groupId)) {
    consumer.subscribe(List.of(topic));
    List<ConsumerRecord<String, String>> records =
            readAtLeast(consumer, 1);
    assertEquals("CREATED", records.get(0).value());
    consumer.commitSync();
}
```

Đoạn này là **pattern nằm trong class runnable ở phần 12**, cần những helper được khai báo ở đó. Trong một test xử lý một message, commit sau assertion là một điểm dễ hiểu. Với consumer processing thực tế, phải commit **chỉ khi xử lý đã hoàn tất theo delivery guarantee**; không commit trước khi cập nhật database rồi gọi đó là exactly-once.

### 6.3. Kafka delivery semantics

- **At-most-once:** có thể mất message nếu commit trước xử lý rồi crash.
- **At-least-once:** có thể đọc lại message sau crash; cần idempotent handler.
- **Exactly-once trong Kafka:** có các transaction/idempotent producer/consumer mechanics và điều kiện cụ thể, không tự áp dụng cho side effect ở một database ngoài Kafka.

Không dùng cleanup offset để che một handler không idempotent. Test message duplicate/redelivery cần assert nghiệp vụ có chống xử lý lặp đúng hay không.

## 7. Thiết kế phạm vi cô lập: test, class, suite, CI run

| Phạm vi | Chiến lược | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| Mỗi `@Test` | Topic/group unique, consumer riêng | Tránh va chạm state | Nhiều topics nếu không cleanup |
| Test class | Một static KafkaContainer, topics unique theo method | Startup broker một lần, dễ group cleanup | Class-scoped broker; context cache phải khớp lifecycle |
| Nhóm integration suite | Một KafkaContainer chung cho nhiều classes | Giảm startup | Cần isolation names, lifecycle/app context thống nhất |
| Một CI job | Broker container dùng riêng job, namespace unique | Chạy nhiều suites | Không tự share với job khác |
| Shared staging broker | Namespace/topic/group có prefix/permissions | Ít chi phí môi trường | Không xóa/alter tài nguyên của người khác; nguy cơ state/race |
| Production | Không dùng làm test cleanup target | Không có | Không delete topics/groups/queues để “dọn test” |

Một quy tắc hữu ích:

**Càng share broker rộng, càng phải tạo tài nguyên có owner/scope rõ.** Nếu broker thuộc riêng một JUnit class và Testcontainers hủy broker cuối class, **toàn bộ topic log và consumer-group offsets** trong broker đó cũng biến mất khi container/test data volume được dọn. Không nhất thiết gọi API xóa từng consumer group.

Nếu broker tồn tại lâu hơn class, cần quản lý topic/group lifecycle riêng và kiểm soát who owns which resources.

## 8. Kế hoạch cleanup một nhóm Kafka test

Một teardown có chủ đích đi theo thứ tự:

```text
Test setup
   |
   +-- Start isolated Kafka broker (per class)
   +-- Generate unique topic and group IDs
   +-- Create topic explicitly, wait for AdminClient result
   +-- Create producer/consumers
   |
Test action
   |
   +-- Send record and await send future
   +-- Subscribe, poll until deadline and assert records
   +-- Commit offset only when test requires it
   |
Per-test teardown
   |
   +-- Stop/close all test-created consumers and listeners
   +-- Wait for in-flight sends/processing to finish (bounded)
   +-- Delete owned test topic if broker remains alive
   +-- Close AdminClient, producer and other handles
   |
After test CLASS
   |
   +-- Testcontainers extension stops class-owned broker
   +-- Broker logs / group offsets / ephemeral storage go away
```

**Thứ tự quan trọng:** đừng delete topic/group khi một consumer còn đang poll hoặc `@KafkaListener` vẫn rebalance; bạn có thể tạo random failures, log noise hoặc group-not-empty errors. Đừng stop broker trước khi hoàn tất các assertions/cleanup cần broker.

### 8.1. Cleanup thất bại là một tín hiệu thật

Một `@AfterEach` gọi `deleteTopics` có thể fail do permission, broker unavailable hoặc timeout. Không nên viết `catch(Exception ignored) {}` khiến suite xanh và rò state. Với broker riêng sắp bị hủy, có thể lựa chọn chỉ ghi log cleanup phụ rồi để container teardown xử lý; phải **mô tả đúng** chứ không báo “topic đã xóa thành công” khi không có xác nhận.

Trong ví dụ runnable, `@AfterEach` để cleanup failures hiện ra, đồng thời đóng `AdminClient` trong `finally`.

## 9. Kafka `deleteTopics`, `deleteRecords` và `deleteConsumerGroups` khác nhau

### 9.1. Xóa topic

```java
admin.deleteTopics(List.of(topic))
        .all()
        .get(15, TimeUnit.SECONDS);
```

Yêu cầu broker xóa topic thuộc test. Metadata/data deletion có thể có độ trễ; completion của API không luôn tương đương mọi broker view đã hội tụ ngay lập tức. Nếu ngay sau đó tạo **cùng tên topic**, nên dùng bounded polling để xác nhận topic đã biến mất; cách đơn giản hơn là không tái sử dụng tên topic.

**Trong shared broker, chỉ xóa topic do chính test tạo.** Không bao giờ gọi `deleteTopics(List.of("orders"))` trên một topic shared vì test muốn “sạch dữ liệu”.

### 9.2. Xóa records

Admin API `deleteRecords` có thể truncation log ở một số offsets mà không đồng nghĩa đổi tất cả group committed offsets. Nó còn phụ thuộc partitions/retention và không nhất thiết phục hồi một “topic trống từ offset 0”.

Do đó **không dùng `deleteRecords` như `repository.deleteAll()` của database**. Với tests, tạo topic unique và bỏ topic/broker thường dễ hơn và an toàn hơn.

### 9.3. Xóa consumer groups

Kafka Admin API hỗ trợ `deleteConsumerGroups` cho các groups **không có active members**:

```java
admin.deleteConsumerGroups(List.of(groupId))
        .all()
        .get(15, TimeUnit.SECONDS);
```

Đây là **mảnh mở rộng**; trong class runnable không gọi nó vì broker private sẽ bị xóa toàn bộ sau class. Trong shared broker, chỉ làm sau khi toàn bộ consumers/listeners của group đã dừng, và chỉ với group ID do test sở hữu. Nếu group vẫn active, broker có thể từ chối, ví dụ group-not-empty.

**Xóa group không xóa records trong topic.** Một group khác vẫn đọc những records ấy theo offsets của riêng họ.

### 9.4. Reset group offset

Kafka tooling/admin cho phép reset offsets tới earliest/latest/specific offset, nhưng group cần inactive theo yêu cầu tương ứng. Đây là **thay đổi tiến độ tiêu thụ**, không xóa message log.

Cẩn thận: reset group có thể khiến side effects được chạy lại hoặc bỏ qua message. Không thực hiện reset group ngoài phạm vi test, đặc biệt ở shared/staging/production.

### 9.5. Dùng `seekToBeginning`

`consumer.seekToBeginning(partitions)` thay đổi **position của consumer hiện tại** sau khi đã được assign partitions. Nó không tự xóa committed offsets của group và không làm mọi consumer cùng group đồng bộ về đầu.

Nếu test muốn đọc lại trong chính instance, `seek` có thể phù hợp. Nếu muốn test restart semantics, hãy close instance, tạo consumer mới cùng group và quan sát **committed offset** thực — không dùng seek để làm giả hành vi restart.

## 10. Container riêng có thể là chiến lược cleanup tốt nhất

Với Testcontainers:

```java
@Testcontainers
class KafkaGroupTest {
    @Container
    static KafkaContainer kafka =
            new KafkaContainer(
                    DockerImageName.parse(
                            "confluentinc/cp-kafka:7.6.1"));
}
```

Ở **Spring Boot 3.3 / Testcontainers 1.x**, class `org.testcontainers.containers.KafkaContainer` và module `org.testcontainers:kafka` là lựa chọn phù hợp. Tài liệu Testcontainers bản mới có thể dùng các classes khác như `org.testcontainers.kafka.ConfluentKafkaContainer`/`org.testcontainers.kafka.KafkaContainer` và module artifact thay đổi — không trộn API phiên bản mới vào ví dụ cũ mà không sửa dependency/imports.

- `@Container static`: broker tồn tại cho các methods trong class.
- JUnit Testcontainers extension quản lý start/stop theo class.
- Group/topic state tích lũy **trong class** nếu bạn dùng lại IDs.
- Khi broker class bị dừng/hủy, state ephemeral của broker test biến mất.
- Spring TestContext cache có thể sống lâu hơn JUnit class → phải tránh reuse Kafka client beans trỏ tới broker đã dừng.

Ví dụ này dùng topic/group unique từng method và một class duy nhất, nên lifecycle đơn giản.

**Giới hạn:** Một KafkaContainer đơn node không chứng minh production replication/failover, multi-broker partition leadership hay ACL/TLS của cluster được quản lý.

## 11. Dự án runnable: Spring Boot 3.3 + Java 17 + Kafka Testcontainers

Dự án gồm:

- Spring Boot application class tối giản để Boot tạo Spring Kafka beans.
- Kafka broker thật trong Testcontainers với `@ServiceConnection`.
- Spring `KafkaTemplate<String,String>` để gửi records.
- Kafka `AdminClient` để tạo/xóa topic dành riêng test.
- Kafka `KafkaConsumer<String,String>` tự quản lý để quan sát offsets chính xác.
- Bốn JUnit methods kiểm tra consume, consumer-group independence, commit/resume và uncommitted redelivery.
- `@BeforeEach` cấp topic unique, `@AfterEach` delete topic và close admin, `try-with-resources` close consumer.
- Broker container bị stop sau cả class — reset luôn group offsets còn lại.

Tất cả tests cần container runtime có Docker hoặc tương thích; **không skip âm thầm** nếu Kafka không chạy được.

### 11.1. Cây thư mục

```text
kafka-test-cleanup/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/messaging/
    │   └── MessagingLabApplication.java
    └── test/java/example/messaging/
        └── KafkaGroupCleanupTest.java
```

### 11.2. `settings.gradle`

```groovy
rootProject.name = 'kafka-test-cleanup'
```

### 11.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3 dependency management kiểm soát phiên bản Spring Kafka/Testcontainers client libraries phù hợp. `org.testcontainers:kafka` ở đây tương ứng Testcontainers **1.x** do Boot 3.3 quản lý; trong Testcontainers 2.x tên package/artifact và modules đã khác, cần migration có kiểm tra.

Không dùng `spring-boot-starter-kafka` theo mặc định của Boot 3.3 nếu artifact ấy không thuộc starter set của version đang dùng; dependency chính xác ở đây là **`org.springframework.kafka:spring-kafka`**.

`spring-boot-testcontainers` cung cấp `@ServiceConnection` integration. `org.testcontainers:junit-jupiter` quản lý lifecycle test container. Kafka image `confluentinc/cp-kafka:7.6.1` là ví dụ có chủ đích cho Testcontainers 1.x; production/release pipeline cần duy trì phiên bản/digest theo security policy.

### 11.4. `MessagingLabApplication.java`

**`src/main/java/example/messaging/MessagingLabApplication.java`:**

```java
package example.messaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessagingLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingLabApplication.class, args);
    }
}
```

Ứng dụng không có `@KafkaListener` chạy nền. Đây là lựa chọn có chủ đích để test offset semantics bằng manual consumers mà không có listener container khác bất ngờ join group hoặc ăn mất message.

Trong project thật, nếu có `@KafkaListener`/`ConcurrentMessageListenerContainer`, teardown còn phải dừng các listener containers và quản lý assigned partitions/rebalances.

## 12. `KafkaGroupCleanupTest.java` — bốn integration tests

**`src/test/java/example/messaging/KafkaGroupCleanupTest.java`:**

```java
package example.messaging;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.kafka.core.KafkaTemplate;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(properties = {
        "spring.kafka.producer.key-serializer=" +
        "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=" +
        "org.apache.kafka.common.serialization.StringSerializer"
})
class KafkaGroupCleanupTest {

    @Container
    @ServiceConnection
    static KafkaContainer kafka =
            new KafkaContainer(
                    DockerImageName.parse(
                            "confluentinc/cp-kafka:7.6.1"));

    @Autowired
    KafkaTemplate<String, String> template;

    private AdminClient admin;
    private String topic;
    private boolean created;

    private static String unique(String prefix) {
        return prefix + "-" +
                UUID.randomUUID().toString()
                        .replace("-", "");
    }

    @BeforeEach
    void createIsolatedTopic() throws Exception {
        topic = unique("orders-it");
        created = false;
        admin = AdminClient.create(Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                kafka.getBootstrapServers()));

        admin.createTopics(List.of(
                new NewTopic(topic, 1, (short) 1)))
                .all()
                .get(15, TimeUnit.SECONDS);

        created = true;
    }

    @AfterEach
    void cleanupOwnedTopic() throws Exception {
        if (admin == null) {
            return;
        }

        try {
            if (created) {
                admin.deleteTopics(List.of(topic))
                        .all()
                        .get(15, TimeUnit.SECONDS);
            }
        }
        finally {
            admin.close(Duration.ofSeconds(5));
        }

        // No global group delete: Kafka broker is private
        // to this class and will be removed by Testcontainers.
    }

    private KafkaConsumer<String, String> consumer(
            String groupId) {
        Map<String, Object> props = new HashMap<>();

        props.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                kafka.getBootstrapServers());
        props.put(
                ConsumerConfig.GROUP_ID_CONFIG,
                groupId);
        props.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        props.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        props.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");
        props.put(
                ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
                false);
        props.put(
                ConsumerConfig.ALLOW_AUTO_CREATE_TOPICS_CONFIG,
                false);

        return new KafkaConsumer<>(props);
    }

    private void send(String key, String value)
            throws Exception {
        template.send(topic, key, value)
                .get(15, TimeUnit.SECONDS);
    }

    private List<ConsumerRecord<String, String>> readAtLeast(
            KafkaConsumer<String, String> consumer,
            int expected) {
        List<ConsumerRecord<String, String>> found =
                new ArrayList<>();

        long deadline = System.nanoTime()
                + Duration.ofSeconds(15).toNanos();

        while (found.size() < expected
                && System.nanoTime() < deadline) {
            ConsumerRecords<String, String> batch =
                    consumer.poll(Duration.ofMillis(250));

            batch.forEach(found::add);
        }

        assertTrue(
                found.size() >= expected,
                "Expected at least " + expected +
                        " records but received " + found.size());

        return found;
    }

    @Test
    void consumesTwoRecordsFromFreshGroup() throws Exception {
        send("order-1", "CREATED");
        send("order-2", "PAID");

        try (KafkaConsumer<String, String> c =
                     consumer(unique("group-a"))) {
            c.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> values =
                    readAtLeast(c, 2);

            assertEquals(2, values.size());
            assertEquals("order-1", values.get(0).key());
            assertEquals("CREATED", values.get(0).value());
            assertEquals("order-2", values.get(1).key());
            assertEquals("PAID", values.get(1).value());

            c.commitSync();
        }
    }

    @Test
    void differentGroupCanReadSameRecord()
            throws Exception {
        send("order-3", "CREATED");

        String groupA = unique("group-a");
        String groupB = unique("group-b");

        try (KafkaConsumer<String, String> first =
                     consumer(groupA)) {
            first.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(first, 1);
            assertEquals("CREATED", batch.get(0).value());

            first.commitSync();
        }

        try (KafkaConsumer<String, String> second =
                     consumer(groupB)) {
            second.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(second, 1);

            assertEquals("CREATED", batch.get(0).value());
            second.commitSync();
        }
    }

    @Test
    void sameGroupResumesAfterCommittedOffset()
            throws Exception {
        String groupId = unique("resume-group");

        send("order-4", "CREATED");

        try (KafkaConsumer<String, String> first =
                     consumer(groupId)) {
            first.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(first, 1);

            assertEquals("CREATED", batch.get(0).value());

            first.commitSync();
        }

        send("order-4", "PAID");

        try (KafkaConsumer<String, String> restarted =
                     consumer(groupId)) {
            restarted.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(restarted, 1);

            // The committed offset skips the prior CREATED record.
            assertEquals(1, batch.size());
            assertEquals("PAID", batch.get(0).value());

            restarted.commitSync();
        }
    }

    @Test
    void uncommittedRecordIsRedeliveredAfterRestart()
            throws Exception {
        String groupId = unique("uncommitted-group");

        send("order-5", "CREATED");

        try (KafkaConsumer<String, String> first =
                     consumer(groupId)) {
            first.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(first, 1);

            assertEquals("CREATED", batch.get(0).value());

            // Deliberately do not commit.
        }

        try (KafkaConsumer<String, String> restarted =
                     consumer(groupId)) {
            restarted.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> batch =
                    readAtLeast(restarted, 1);

            // No committed progress: earliest applies.
            assertEquals("CREATED", batch.get(0).value());

            restarted.commitSync();
        }
    }
}
```

### 12.1. Vì sao runnable suite chỉ có một class?

Testcontainers JUnit extension dừng static `@Container` sau khi class hoàn thành, nhưng Spring TestContext có thể cache context giữa các classes. Một context khác tái sử dụng Kafka producer/listener beans với bootstrap address của broker đã stop có thể fail.

Một class tránh vấn đề reuse đó trong lab. Với suite nhiều classes, dùng Spring-managed container lifecycle hoặc singleton container pattern tương thích context cache; **không** chỉ copy cùng static container vào nhiều classes rồi giả định Spring context và JUnit container có cùng vòng đời.

### 12.2. Vì sao tạo topic mới từng test?

`@BeforeEach` tạo tên topic ngẫu nhiên với prefix `orders-it-`. Các tests không tranh chấp log data dù chạy không theo thứ tự khai báo. Topic có **một partition** để assertions về ordering của hai records minh bạch.

Không dùng một shared topic `orders` rồi gọi `deleteRecords`/`resetOffsets` trước mọi test — cách đó có thể đụng groups khác, tạo races và không reset đủ mọi state.

### 12.3. Vì sao dùng group ID mới từng scenario?

- `differentGroupCanReadSameRecord` chứng minh offsets thuộc group; group B vẫn thấy record mà A đã commit.
- `sameGroupResumesAfterCommittedOffset` cố ý dùng lại **cùng group ID trong một test** để chứng minh restart/resume.
- `uncommittedRecordIsRedeliveredAfterRestart` dùng lại group ID nhưng lần đầu **không commit**, nên lần thứ hai đọc từ earliest.
- Các tests độc lập vì topic/group names khác giữa methods.

Không sử dụng timestamp/UUID khác nhau làm business result assertion; unique name chỉ phục vụ isolation.

### 12.4. Vì sao dùng manual KafkaConsumer thay @KafkaListener?

Trong bài học về offsets, manual consumer cho phép tách rõ:

- `subscribe` và group assignment.
- `poll` trả về batch.
- `commitSync` khi nào được gọi.
- `close` kết thúc group membership.
- Consumer group ID cụ thể.

`@KafkaListener` cùng Spring Kafka listener container có thể auto-commit/ack theo `AckMode` và consumer factory configuration. Nó phù hợp test ứng dụng thật, nhưng sẽ thêm một tầng lifecycle/offset management vào thí nghiệm offset cơ bản.

### 12.5. Vì sao consumer phải nằm trong try-with-resources?

`KafkaConsumer` sở hữu I/O/network resources và group membership. `close()` sẽ giải phóng resources và thực hiện group leave khi thích hợp. Nếu test throw assertion giữa chừng mà không close consumer, broker vẫn có thể thấy active member cho đến session timeout; teardown group sẽ lỗi và tests khác bị rebalances.

`try-with-resources` đảm bảo close ngay cả khi test body fail. `AdminClient` được close trong `finally` của `@AfterEach`.

### 12.6. Vì sao không xóa group từng method?

Broker chỉ thuộc một class và được Testcontainers remove cuối class. Như vậy group metadata/committed offsets còn lại không lọt sang nhóm test khác. Ta xóa topic per method để tập thói quen quản lý resource và tránh tăng số topics trong một class dài.

Nếu test dùng **shared broker** lâu dài, cần thêm group cleanup sau khi tất cả consumers ngừng hoạt động; đó là bài toán riêng có rủi ro shared state, phần 15 mô tả.

### 12.7. Một caveat về cleanup bất đồng bộ

`AdminClient.deleteTopics(...).all().get(...)` xác nhận thao tác admin hoàn thành theo API, **không phải bằng chứng mọi node/metadata cache đã thấy topic biến mất ngay tức thì**. Bài mẫu không tái sử dụng topic name, nên không phụ thuộc “xóa xong rồi tạo lại cùng tên” trong milliseconds.

### 12.8. `@ServiceConnection` thực sự hỗ trợ Kafka?

Trong Spring Boot 3.3, `spring-boot-testcontainers` cung cấp `KafkaConnectionDetails` cho Kafka Testcontainers type được hỗ trợ. Khi `@ServiceConnection` gắn trên static typed `KafkaContainer`, Boot có thể cấu hình Spring Kafka connection đến broker test mà không hardcode `localhost:9092`.

Manual consumer và AdminClient trong lab lấy `kafka.getBootstrapServers()` trực tiếp để nhìn rõ connection và tránh nhầm `KafkaProperties.getBootstrapServers()` chưa được cập nhật giá trị bởi connection details. Spring KafkaTemplate được Boot cấu hình bằng service connection.

**Không** tự thay `@ServiceConnection` bằng `@DynamicPropertySource` đồng thời trên cùng container nếu chưa hiểu configuration precedence.

## 13. Chạy Gradle và kết quả dự kiến

Máy cần JDK 17, Gradle Wrapper phù hợp (ví dụ Gradle 8.7), khả năng tải dependencies, Docker/compatible container runtime và image Confluent Kafka.

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.messaging.KafkaGroupCleanupTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.messaging.KafkaGroupCleanupTest
```

**Kết quả dự kiến:** **4 JUnit test methods pass** khi KafkaContainer startup thành công, KafkaTemplate/Consumer/AdminClient kết nối đúng và broker có khả năng tạo/delete topic. Nếu Docker không sẵn, test có thể fail ở container bootstrap; đó là lỗi môi trường, không phải test “pass vì skip”.

Đây là **kết quả kỳ vọng từ code**, không phải tuyên bố đã thực thi Gradle/Docker trong môi trường biên soạn. Thời gian startup, mapped broker port và container ID là dynamic.

### 13.1. Log Kafka không phải expected stdout cố định

Log có thể chứa broker startup, client cluster metadata, group assignment/rebalance và topic deletion. Đừng assert log text byte-for-byte: Kafka/driver versions thay đổi. Assertions nên dựa vào records, keys, group behavior và cleanup API results.

### 13.2. Có cần Spring Boot chạy HTTP server?

Không. `@SpringBootTest` dùng default web environment MOCK, nhưng project không có starter-web; nó vẫn tạo application context thích hợp để inject KafkaTemplate. Chúng ta đang kiểm tra messaging boundary, không có HTTP endpoint.

### 13.3. Cách báo status test

Nên báo rõ:

```text
Kafka integration suite:
- Test class executed: KafkaGroupCleanupTest
- Methods expected: 4
- Actual passed/failed/skipped: xem JUnit/Gradle report
- Broker: KafkaContainer (class scope)
- Topic scope: one unique topic per test method
- Consumer group scope: unique per scenario
- Cleanup: topic delete request per method, broker teardown per class
```

Đoạn trên là **mẫu báo cáo**, không phải log đã được đo. Không ghi `PASSED 4/4` trừ khi thực sự chạy tests và kiểm tra report.

## 14. Khi application dùng @KafkaListener thì cleanup khác thế nào?

Một Spring Boot application messaging thường dùng:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-service")
public void onMessage(String payload) {
    // business processing
}
```

Đây là **mảnh code minh họa**, không thuộc runnable lab. Khi nạp Spring context, listener container có thể tự start, join group, poll và commit offsets theo cấu hình. Nếu bạn dùng cùng topic/group với manual KafkaConsumer trong test, records có thể được consumer khác nhận → tests trở nên nondeterministic.

### 14.1. Stop listener containers trước cleanup

Trong một test có Spring Kafka listeners, có thể lấy registry:

```java
@Autowired
KafkaListenerEndpointRegistry listenerRegistry;
```

Và trong teardown của một context/dedicated test group:

```java
for (MessageListenerContainer container
        : listenerRegistry.getListenerContainers()) {
    container.stop();
}
```

**Đây là snippet minh họa**, cần imports `org.springframework.kafka.config.KafkaListenerEndpointRegistry` và `org.springframework.kafka.listener.MessageListenerContainer`. `stop()` có thể cần bounded waiting/callback tùy semantics và listener container version; không mặc định return từ mọi call chứng minh tất cả processing work đã kết thúc.

Quan trọng: registry có thể chứa **listeners không do test sở hữu** trong một shared application context. Không stop global listener beans rồi để những tests khác reuse context mà không khởi động lại.

### 14.2. Nếu listener có in-flight messages

Một listener đang xử lý message mất vài giây; teardown bắt đầu xóa topic trước khi callback hoàn tất. Kết quả có thể là late database writes, commit errors, duplicate redelivery hoặc test sau đọc side effects.

Giải pháp:

- Await business assertion với deadline.
- Dừng listener và await shutdown phù hợp.
- Commit/ack theo handler contract.
- Đảm bảo không còn in-flight callback vào state test khác.
- Sau đó mới xóa owned resources.
- Dùng dedicated context/broker khi chia sẻ lifecycle quá khó.

### 14.3. ConsumerFactory, KafkaTemplate và KafkaAdmin

Spring-managed clients khác với consumers do test tự tạo:

- `KafkaTemplate` sử dụng producer factory; producer có thể được cache/reused.
- `DefaultKafkaConsumerFactory` tạo consumers theo listener/test; cần close từng consumer.
- `KafkaAdmin` có thể tạo `NewTopic` beans khi context start.
- `KafkaListenerEndpointRegistry` quản lý listener containers.
- `AdminClient` tự tạo bằng Java cần close.
- Executors, schedulers, retry topics và DLQ consumers có thể tồn tại ngoài test method.

Đừng tạo một `KafkaConsumer` thủ công rồi chỉ dọn nó, trong khi `@KafkaListener` vẫn đang chạy trong cùng context.

## 15. Khi broker dùng chung: dọn consumer groups an toàn

Dùng shared Kafka broker cho nhiều test classes/runs khiến cleanup phức tạp. Một quy trình có quyền/owner rõ:

1. Tạo topic `it-<runId>-orders` và group `it-<runId>-consumer`, ghi owner/run ID.
2. Producer gửi records, chờ futures.
3. Consumer/listener xử lý records và commit/ack theo yêu cầu.
4. Stop/close **tất cả active consumers** thuộc test group.
5. Chờ broker group vào trạng thái inactive/empty với bounded deadline nếu cần.
6. Dùng AdminClient delete consumer groups **chỉ những IDs do run tạo**.
7. Delete topics mà run sở hữu; chờ deletion convergence nếu muốn dùng lại tên (tốt hơn là không reuse).
8. Close AdminClient và các resource handles.
9. Báo chính xác errors, không nuốt `GroupNotEmptyException`.
10. Dọn orphaned test resources còn lại bằng một job có allowlist/prefix/TTL, tuyệt đối không xóa tài nguyên production.

### 15.1. Snippet xóa một group đã đóng

```java
try (AdminClient admin = AdminClient.create(
        Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers))) {
    admin.deleteConsumerGroups(List.of(ownedGroupId))
            .all()
            .get(15, TimeUnit.SECONDS);
}
```

Đây là **snippet độc lập về API**, biến `bootstrapServers` và `ownedGroupId` phải được cấp từ test scope. Nếu group không tồn tại hoặc còn active, thao tác có thể ném exception. Không ép mọi tests phải xóa group khi container private đã được hủy.

### 15.2. Không gọi xóa group khi còn member hoạt động

Kafka có quy tắc chỉ delete group khi không có active members. Nếu `@KafkaListener` đang sống, `deleteConsumerGroups` thường thất bại. Cách sửa là stop/close đúng listener/consumer, không tăng retries vô hạn hoặc can thiệp offset vào group người khác.

### 15.3. Cẩn thận với consumer group ID tái sử dụng

Những identifiers như `test-group` hoặc `inventory-consumer` lặp qua classes/CI builds có thể giữ old commits trong broker. Hậu quả:

- Test run B bắt đầu từ offset của run A, bỏ qua fixture mới.
- Test run B nhìn thấy old retained records với group mới nhưng shared topic.
- Group metadata stale gây khó debug.
- Parallel jobs rebalances nhau nếu group IDs trùng.

Dùng IDs chứa scope: test suite/run/class/method với sanitized UUID hoặc unique suffix. Với topics Kafka có giới hạn naming/length, tránh tên quá dài và ký tự không hợp lệ.

## 16. Kiểm tra offset hiện tại thay vì đoán

Kafka AdminClient có thể quan sát group offsets:

```java
Map<TopicPartition, OffsetAndMetadata> offsets =
        admin.listConsumerGroupOffsets(groupId)
                .partitionsToOffsetAndMetadata()
                .get(15, TimeUnit.SECONDS);
```

Đây là **snippet minh họa**, cần imports `TopicPartition`, `OffsetAndMetadata` và variables `admin`/`groupId` trong scope. Với các Kafka client versions mới, một số Admin APIs có thể bị deprecate hoặc thay bằng overload khác; dùng API đúng version do Spring Boot BOM quản lý.

Điều cần xác minh:

- Group ID đúng.
- Topic/partition IDs đúng.
- Committed offsets đúng và nằm trong log range.
- End offsets (log end) nếu muốn tính lag.
- Group có active members không.

Kafka `kafka-consumer-groups.sh` cũng có:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group it-example-group
```

**Đây chỉ là lệnh minh họa** khi broker thực sự đang nghe trên localhost:9092. Với Testcontainers mapped port ngẫu nhiên, dùng `kafka.getBootstrapServers()` hoặc biến môi trường tương ứng, không hardcode localhost:9092.

### 16.1. Offset reset CLI chỉ dùng trên group inactive

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <bootstrap-servers> \
  --group <owned-test-group> \
  --topic <owned-test-topic> \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

Chuỗi angle-bracket là placeholders cần thay bằng giá trị thực, không lệnh runnable ngay. Muốn áp dụng sẽ dùng `--execute` **sau** dry-run và sau khi xác minh broker/group/topic thuộc test. Không reset một shared group đang xử lý production events.

**Không dùng offset reset làm “cleanup mặc định”**: reset có thể tạo duplicate side effects khi test consumer chạy lại handler.

## 17. Topic deletion: vì sao không thể coi như xóa một SQL row?

Trong Kafka, topic có metadata, partitions, logs, leader/replicas, retention, ACL, quotas và clients subscribe. Việc xóa một topic:

- Có thể bất đồng bộ ở broker/controller level.
- Có thể làm consumer nhận metadata errors/rebalances.
- Không tương đương “xóa records và đặt mọi committed offset về 0”.
- Có thể làm các producers/listeners đang chạy bị errors.
- Có thể đụng resource khác nếu topic được share.
- Không tự xóa local state stores của Kafka Streams hoặc database side effects.

Dùng topic unique **và không tái sử dụng tên** thường đơn giản hơn thử đồng bộ delete/recreate trên cùng tên khi CI chạy song song.

Nếu môi trường broker không cho delete topics, vẫn có lựa chọn:

- Broker container riêng cho test class và hủy toàn bộ sau class.
- Topic prefix riêng và cleanup job có quyền.
- Retention ngắn cho test topics nhưng không coi retention là immediate cleanup.
- Định kỳ xóa resource bằng admin job có allowlist/run TTL.

Không thực hiện thay đổi broker-wide `delete.topic.enable` hoặc cluster ACL tùy tiện chỉ để một test xanh.

## 18. Dead-letter topics, retry topics và Spring Kafka retries

Trong Spring Kafka, các lỗi xử lý có thể dẫn đến:

- Retry cùng record.
- Retry topics có hậu tố hoặc tên cấu hình.
- Dead-letter topic (DLT).
- Backoff timers/scheduled retries.
- Consumer groups riêng cho retry/DLT.
- Failed records với headers/chuyên biệt serializer.

Nếu một test chỉ xóa **main topic** mà để retry/DLT topics cùng messages tồn tại, test sau có thể nhìn thấy lỗi cũ hoặc background listener tiếp tục xử lý.

Một nhóm integration test cần liệt kê **tất cả topics được tạo bởi workflow**, ví dụ:

```text
it-run42.orders
it-run42.orders-retry-0
it-run42.orders-retry-1
it-run42.orders-dlt
```

Đây là **tên minh họa**, không khẳng định Spring Kafka luôn tạo đúng suffix này; cấu hình `@RetryableTopic`, retry policy và naming strategy quyết định tên thực.

Dọn theo thứ tự:

1. Xác nhận retry/DLT assertions đã xong.
2. Stop listeners/consumer groups.
3. Hủy scheduled tasks/callbacks đang chờ.
4. Delete tất cả owned topics/queues hoặc hủy broker.
5. Close producers/admin clients.
6. Không xóa shared DLT topic của hệ thống.

### 18.1. Không để cleanup che bug retry

Nếu handler lỗi rồi message đến DLT, test nên assert **DLT record** trước khi xóa. Xóa ngay sau gửi không phải kiểm thử correct retry behavior, và có thể giấu một consumer chưa kịp xử lý.

### 18.2. Exactly-once và Kafka transactions

Spring Kafka transaction producer có `transactional.id` và state liên quan đến broker. Một nhóm test dùng cùng transactional ID giữa parallel runs có thể gây producer fencing. Dùng transaction ID prefix unique cho test run hoặc broker riêng; close/stop producer factories trước khi hủy broker.

Xóa topic/group offsets **không tự dọn** mọi transactional producer metadata theo nghĩa có thể reset transaction protocol. Broker private disposal thường là lựa chọn sạch hơn cho tests transactional phức tạp.

## 19. RabbitMQ: purge queue không đồng nghĩa dọn toàn bộ messaging state

RabbitMQ dùng mô hình khác Kafka:

```text
Publisher
   |
Exchange --binding--> Queue
                      | ready messages
                      | unacked deliveries
                      v
                   Consumer
                      |
                    ack / nack
                      |
                      +--> accepted, removed
                      +--> requeue (if requested)
                      +--> dead-letter flow (if configured)
```

Với RabbitMQ, hãy phân biệt:

- **Ready messages:** đang nằm trong queue chờ consumer.
- **Unacked deliveries:** broker đã giao cho consumer nhưng chưa nhận ack/nack; chúng có thể được requeue khi channel/connection đóng.
- **DLQ:** queue khác nhận messages bị dead-letter.
- **Exchange/binding/queue metadata:** không mất chỉ vì purge message.
- **Consumers/channels/connections:** process resources phải stop/close.

### 19.1. `purgeQueue` không xóa exchange và bindings

Spring AMQP có `AmqpAdmin.purgeQueue(queueName, false)` hoặc API tương ứng để xóa ready messages trên queue do test sở hữu. Nhưng:

- Purge không xóa queue/exchange/bindings.
- In-flight unacked deliveries có thể tái xuất hiện sau consumer disconnect/nack tùy lifecycle.
- DLQ vẫn giữ messages riêng.
- Delayed/scheduled messages có thể đang nằm ở extension/queue khác.
- Nếu test khác dùng chung queue, purge phá state của họ.

Với một dedicated test broker/vhost, purge có thể phù hợp cho testcase cụ thể. Với shared queue, **không** purge như cách reset toàn cục.

### 19.2. Snippet dọn queue test thuộc quyền sở hữu

```java
// Chỉ chạy khi toàn bộ consumers test đã stop,
// và queue là resource của chính test.
amqpAdmin.deleteQueue(ownedQueueName);
```

Đây là **mảnh code**, biến `amqpAdmin` kiểu `AmqpAdmin` và `ownedQueueName` phải được cấp bởi test configuration. Queue deletion là thao tác phá hủy: nó xóa ready messages và queue bindings liên quan; không được gọi trên production/shared queue.

### 19.3. Vhost và tên tài nguyên

Trong RabbitMQ tests lớn, vhost riêng cho CI run là một cách cô lập mạnh: policies, exchanges, queues và consumer connections có namespace độc lập. Tạo/xóa vhost có thể yêu cầu quyền quản trị cao, nên chọn theo team policy. Nếu dùng Testcontainers RabbitMQContainer private cho class/suite, hủy container là cách reset broker state sạch hơn.

### 19.4. DLQ và retries

Test negative handling phải assert:

1. Message được gửi vào main exchange/queue.
2. Consumer nhận và ném error đúng điều kiện.
3. Retry/requeue logic diễn ra theo policy.
4. Message cuối cùng vào DLQ (nếu hợp đồng yêu cầu).
5. Header x-death/retry count được xử lý đúng nếu có.
6. Cleanup main queue + DLQ + consumers sau assertions.

Không xóa DLQ trước khi test kịp assert; không coi queue length 0 tức là message đã được xử lý thành công — nó có thể đang unacked hoặc đã chuyển sang DLQ.

## 20. JMS/ActiveMQ Artemis: durable subscriptions là một loại state khác

JMS có queues và topics; với durable subscription, broker có thể giữ subscription/message backlog **sau khi consumer disconnect**. Vì vậy stop listener chưa chắc xóa subscription.

Những tài nguyên cần xem:

- JMS Connection và Session.
- MessageConsumer/MessageProducer.
- Queue/topic destination.
- Durable subscription name và client ID.
- Acknowledgment mode / transacted sessions.
- Dead-letter address/queue.
- Redelivery delay và scheduled messages.
- Broker test container/embedded broker process.

Nếu test tạo durable subscription, cleanup có thể cần **unsubscribe** sau khi subscriber không còn active, theo JMS provider API/quy định. Ví dụ JMS Session có `unsubscribe(subscriptionName)` dành cho named durable subscriptions trong ngữ cảnh phù hợp. Không áp dụng `consumer.close()` là bằng chứng broker đã xóa durable state.

### 20.1. Khi JMS transaction rollback

Với transacted session, message receive/ack có thể rollback và message được redeliver. Một test “queue trống” sau method có thể không đúng nếu transaction rollback hoặc session đóng trước commit. Cần assert commit/rollback/redelivery theo contract và cleanup sau khi quyết định transaction outcome.

### 20.2. ActiveMQ Artemis test container

Testcontainers hỗ trợ ArtemisContainer ở những phiên bản tương ứng; Spring Boot có `ArtemisConnectionDetails` cho typed container khi dùng service connections. Chọn đúng version module và broker image. Một Artemis container đơn không đại diện toàn bộ clustered HA topology.

## 21. Spring TestContext cache và broker lifecycle là hai đồng hồ khác nhau

Spring Boot integration tests dùng Spring TestContext caching để tránh nạp lại application context nhiều lần. Trong khi đó, JUnit Testcontainers extension có thể stop static `@Container` khi **một class** kết thúc.

Tình huống lỗi:

```text
Test Class A:
    @SpringBootTest -> ApplicationContext cached
    @Container static Kafka broker A started
    KafkaTemplate points to bootstrap broker A
    methods PASS
    JUnit extension stops broker A

Test Class B:
    Spring reuses cached ApplicationContext
    KafkaTemplate still points to stopped broker A
    KafkaContainer broker B may have another port
    methods FAIL / timeout
```

Các giải pháp:

- Sắp xếp lifecycle broker tương thích context, ví dụ Spring-managed container bean ở test configuration phù hợp.
- Hoặc singleton container pattern có lifecycle dài bằng JVM test process/context.
- Hoặc mỗi class có context isolation rõ, chấp nhận chi phí bootstrap.
- Không dùng `@DirtiesContext` bừa bãi như “dọn Kafka messages”; nó chỉ loại Spring context cache, không tự xóa remote broker state.
- Không đặt static broker bị JUnit stop cuối class rồi mong cached context reuse an toàn ở class khác.

**Dọn messaging state** và **dọn Spring context state** là hai thao tác khác nhau, có thể cần phối hợp nhưng không thay thế nhau.

## 22. Parallel tests: ba nguồn race dễ gặp

### Race A — Hai tests cùng topic và group

Hai consumers thuộc cùng group sẽ chia partitions, không phải ai cũng nhận toàn bộ messages. Test A có thể “ăn” message của test B; Test B timeout dù producer gửi thành công.

**Sửa:** unique group/topic theo test khi cần independent consumption.

### Race B — Hai tests cùng topic nhưng khác group

Mỗi group có thể đọc mọi message trong topic, kể cả fixture của test còn lại. Kết quả có thêm records không mong đợi.

**Sửa:** unique topic hoặc filter/key namespace mạnh; group riêng thôi chưa luôn đủ.

### Race C — Cleanup của test A xóa resource test B

Test A `@AfterEach` gọi delete topic shared `orders-test` trong khi B vẫn poll. B nhận metadata errors/timeout. Đây là một **bug isolation** ở test infrastructure, không phải lỗi Kafka.

**Sửa:** mỗi test có ownership scope. Khi chạy parallel, tài nguyên unique và teardown chỉ đụng owned names.

### 22.1. Testcontainers JUnit parallel considerations

Testcontainers JUnit Jupiter extension trong các versions thường được tài liệu hóa chủ yếu cho sequential execution. Nếu muốn parallel, phải đánh giá module lifecycle, state isolation và resource pressure; không mặc định extension bảo đảm mọi shared container race được tránh.

Với bài lab, giữ một class tuần tự. Nếu repo bật JUnit parallel globally, đánh dấu class test mang shared static container/state bằng cơ chế JUnit phù hợp như `@Execution(ExecutionMode.SAME_THREAD)` với imports cần thiết, hoặc tổ chức dedicated Gradle task.

## 23. Polling có deadline thay vì sleep cố định

Message delivery bất đồng bộ. Sau producer `send()`, consumer có thể cần thời gian join group và được assign partition trước khi nhận record.

Không làm:

```java
template.send(topic, "key", "value");
Thread.sleep(1000);
assertEquals(1, received.size());
```

Đây là **anti-pattern**:

- Không chờ send future nên chưa biết broker đã ack publish.
- Ngủ 1 giây có thể thừa hoặc thiếu.
- Shared `received` có thể bị race nếu listener thread cập nhật.
- Không biết offset/assignment/group state.

Trong lab:

```java
template.send(topic, key, value)
        .get(15, TimeUnit.SECONDS);

while (records.size() < expected
        && System.nanoTime() < deadline) {
    ConsumerRecords<String, String> batch =
            consumer.poll(Duration.ofMillis(250));
    batch.forEach(records::add);
}
```

Điểm tốt:

- Chờ producer send future hoàn tất có timeout.
- Consumer poll với deadline.
- Assert số records thật.
- Consumer close trong try-with-resources.
- Không assert delay đúng từng millisecond.

Trong một hệ thống có Kafka listener/background work, có thể dùng Awaitility hoặc CountDownLatch có timeout, nhưng chỉ dùng latch khi đã thiết kế thread-safety và tránh callback sau teardown.

## 24. Message ordering và offset assertions: đừng phóng đại bằng chứng

Trong lab mỗi topic một partition. Vì thế records `CREATED`, `PAID` được gửi tuần tự và có thể kiểm tra thứ tự qua consumer cùng partition.

Nếu topic có nhiều partitions:

- Order chỉ được bảo đảm **trong một partition**.
- Cùng key thường được partitioner đưa tới cùng partition, nhưng behavior phụ thuộc partitioner/config/schema.
- Group members có thể được assign subsets của partitions.
- `poll()` có thể chứa records từ nhiều partitions; thứ tự iteration không là global event ordering contract.
- Offset number không thể so trực tiếp giữa partitions.
- Producer retries/idempotence và max in-flight settings ảnh hưởng ordering khi có failure.

Đừng viết một test giả định tất cả messages trên một multi-partition topic có global order. Nếu cần event ordering theo aggregate key, thiết kế key/partitioning và assert đúng granularity.

### 24.1. Lag không phải offset đã commit

Consumer lag thường được tính từ log end offset trừ committed group offset theo từng partition. Nó là diagnostic, không là proof business processing hoàn tất: handler có thể commit trước side effects, hoặc có retry pipeline chưa done.

Trong cleanup, chỉ nhìn lag bằng 0 chưa đủ để nói không có in-flight callbacks, DLQ messages hoặc database writes đang chờ.

## 25. Kafka Streams: state stores và internal topics cần cleanup riêng

Một `KafkaStreams` application có thể tạo:

- State stores local trên disk.
- Changelog topics.
- Repartition topics.
- Internal consumer groups/transactional producer IDs.
- RocksDB state directories.
- Background stream threads.

Nếu test chỉ delete input topic nhưng Kafka Streams client còn chạy, internal topics/stores có thể sống và làm test sau nhận state cũ.

Với Spring Kafka Streams:

1. Dùng `application.id` unique cho test group.
2. Stop `KafkaStreams` instance và đợi close.
3. Quản lý owned internal topics theo application ID hoặc hủy private broker.
4. Xóa local state dir do test sở hữu khi thích hợp.
5. Không dùng cùng `application.id`/state dir cho parallel runs.
6. Không xóa internal topics của production-like stream application khác.

Một static class KafkaContainer hủy sau test có thể giải quyết broker-side state, **nhưng local filesystem state stores của JVM** vẫn cần xem riêng nếu cấu hình durable test directories.

## 26. Test retry và dead-letter phải chờ điều kiện ổn định

Trong các tests message-driven:

```text
send record
    |
listener consumes
    |
business operation fails
    |
retry scheduled
    |
DLQ/DLT receives record
    |
assert payload/headers/retry count
    |
stop listener / cleanup all resources
```

Nếu teardown bắt đầu ngay sau `KafkaTemplate.send().get()`, test có thể xóa topic khi listener chưa hoàn thành retry. Producer send acknowledgment **không** là consumer processing acknowledgment.

Test nên đợi outcome quan sát được (DB row, emitted event, DLT record, callback flag) với timeout. Chỉ cleanup sau khi behavior được kiểm tra hoặc test fail và cần abort resources an toàn.

### 26.1. Cleanup khi test fail trước assertion

JUnit `@AfterEach` vẫn được gọi nếu test method throw assertion/error trong phần lớn tình huống bình thường. Nhưng nếu JVM bị kill, Docker daemon mất hoặc process crash, callbacks không bảo đảm chạy. Broker private Testcontainers với resource cleanup giúp giảm orphan leaks, nhưng CI còn cần container/volume retention policy và watchdog.

Không xem `@AfterEach` là một distributed transaction có thể rollback tất cả effects khi process chết.

## 27. Bảo mật: không dọn shared resources bằng quyền quá lớn

Một test account có quyền xóa mọi Kafka topic hoặc RabbitMQ vhost có thể gây hậu quả nghiêm trọng nếu trỏ nhầm môi trường.

Nguyên tắc:

- CI integration broker dùng container/namespace riêng.
- Không cấp production credentials hoặc network write access vào test job nếu không cần.
- Mỗi run có unique prefix và ownership metadata.
- Cleanup chỉ theo allowlist của tài nguyên do run tạo.
- Không dùng wildcard delete toàn bộ topics/queues.
- Không reset offsets cho consumer group production.
- Không dùng RabbitMQ `purgeQueue`/`deleteQueue` với tên queue shared.
- Không log SASL passwords, client certificates, authentication headers hoặc PII trong messages.
- Khi test cần OAuth/SASL/TLS, tạo secrets test-only và kiểm tra broker policy riêng.
- Dọn test volumes, logs và DLQ chứa synthetic payloads theo retention.
- Trên shared broker, phân quyền admin riêng để test không thể xóa resource ngoài namespace.

**Nếu không chắc resource có thuộc quyền test hay không, không xóa.** Dùng broker container riêng là giải pháp đơn giản để giảm phạm vi rủi ro.

## 28. Troubleshooting: xanh riêng, đỏ khi chạy cả suite

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Consumer không nhận message mới | Group đã commit offset cao, topic dùng chung, listener khác ăn record | Unique group/topic, kiểm tra committed offsets |
| Group mới đọc cả messages cũ | Topic shared còn retained records | Unique topic hoặc broker riêng |
| `earliest` vẫn không đọc record từ đầu | Group đã có committed offset hợp lệ | Dùng group mới/offset reset có chủ đích |
| Message xuất hiện lại khi restart | Consumer chưa commit offset | Test at-least-once, idempotent processing |
| `GroupNotEmptyException` khi delete group | Consumer/listener còn active | Stop/close, chờ group inactive có timeout |
| `UnknownTopicOrPartitionException` trong teardown | Topic chưa tạo hoặc đã bị xóa | Chỉ xóa owned-created topic, idempotent cleanup |
| Admin delete trả success nhưng create lại cùng tên fail | Topic deletion/metadata propagation chưa hội tụ | Tên topic unique; nếu reuse, bounded wait |
| Lỗi `TimeoutException` Kafka client | Broker/startup/network/group assignment | Kiểm tra bootstrap servers, image, logs |
| KafkaTemplate send xanh, listener assertion fail | Send ack ≠ consume/ack | Await consumer outcome/offset, group isolation |
| Test fail sau khi class trước chạy | Spring context cache trỏ broker đã dừng | Fix container/context lifecycle |
| Producer/consumer threads không thoát | Resources không close | try-with-resources, listener stop, admin.close |
| Delete main topic nhưng DLT vẫn còn | Retry/DLT topics khác | Liệt kê toàn bộ owned topics |
| Rabbit queue rỗng nhưng DLQ có records | Reject/dead-letter | Assert DLQ, cleanup riêng |
| Rabbit purge xong message quay lại | Unacked delivery được requeue | Stop/ack/nack consumer trước purge |
| JMS durable subscription giữ backlog | Close consumer chưa unsubscribe | Unsubscribe theo provider semantics |
| Tests parallel đụng nhau | Shared topic/group/queue/reset | Unique namespace hoặc serialize tests |
| Kafka Streams state cũ | Internal topics/local state store reuse | Unique application.id, cleanup state dir |
| No Docker environment | Testcontainers runtime thiếu | Chạy stage có container runtime |
| Tests skipped nhưng Gradle xanh | Filter/conditional test disabled | Báo executed/skipped rõ |
| Cleanup ở shared broker phá test khác | Ownership scope sai | Không delete shared resources, private broker |

### 28.1. Đọc log theo tầng

- **Container startup:** Kafka image pull, advertised listeners, Testcontainers environment.
- **Producer:** bootstrap address, serialization, send future, authorization.
- **Consumer:** group join, partition assignment, offsets, poll/commit errors.
- **Listener:** application handler, retries, ack mode, exception handler.
- **Admin:** topic/group existence, deletion rights, group membership, timeouts.
- **Spring:** context cache, bean lifecycles, `@ServiceConnection`/`@DynamicPropertySource` precedence.

Sửa đúng tầng thay vì tăng timeout chung cho mọi failure.

## 29. Bài tập thực hành

### Bài 1 — Fresh group vs committed group

Chạy `sameGroupResumesAfterCommittedOffset` và `differentGroupCanReadSameRecord`. Giải thích: cùng group restart theo committed offset; group mới từ earliest thấy record đã tồn tại. Thay `auto.offset.reset` sang latest trong nhánh sandbox và quan sát ảnh hưởng với group chưa commit.

### Bài 2 — Bỏ manual commit

Trong `sameGroupResumesAfterCommittedOffset`, tạm bỏ `first.commitSync()`. Consumer restarted có thể đọc lại `CREATED` trước `PAID`. Khôi phục và giải thích vì sao message delivery at-least-once yêu cầu idempotent handler.

### Bài 3 — Dùng group id cố định

Đổi helper unique group thành `"test-consumer"` rồi chạy suite nhiều lần trong shared broker. Mô tả false positives/flaky do committed offsets và rebalances. Khôi phục unique IDs.

### Bài 4 — Dùng topic chung

Đổi setup thành một topic `orders-test` dùng chung tất cả methods, không xóa giữa tests. Quan sát records cũ làm lệch expectations nếu groups mới đọc từ earliest. Khôi phục per-test topics.

### Bài 5 — Thử delete group khi consumer active

Trong broker sandbox, cho consumer còn subscribe/poll, gọi `deleteConsumerGroups` bằng group ID ấy. Quan sát lỗi group-not-empty, rồi đóng consumer và retry có timeout. Không thử trên shared/staging group.

### Bài 6 — Cleanup sau exception

Tạo một test cố tình `assertEquals("wrong", record.value())`. Xác nhận `try-with-resources` vẫn close consumer và `@AfterEach` vẫn thực hiện owned topic cleanup. Khôi phục assertion để suite xanh.

### Bài 7 — RabbitMQ ready vs unacked

Tạo một RabbitMQContainer riêng, publish message, consume nhưng chưa ack, kiểm tra ready/unacked state; sau khi consumer/channel close, xác minh requeue behavior. So sánh `purgeQueue`, `deleteQueue` và stop consumer.

### Bài 8 — RabbitMQ DLQ cleanup

Tạo test queue có DLX/DLQ, reject một message với requeue=false, assert DLQ record, rồi cleanup **cả main queue và DLQ**. Không xóa DLQ trước assertion.

### Bài 9 — JMS durable subscription

Dùng Artemis test broker, tạo durable subscription với unique client ID, disconnect, publish event, reconnect và assert backlog. Unsubscribe/destroy test resources sau khi inactive. Phân biệt close consumer với unsubscribe.

### Bài 10 — KafkaListener Spring context cache

Tạo một `@KafkaListener` test trong dedicated context; chạy hai classes chia sẻ config nhưng container lifecycle theo class. Quan sát vì sao cached producer/listener có thể giữ bootstrap server đã stop, rồi giải quyết bằng lifecycle đúng.

### Bài 11 — Retry/DLT isolation

Thêm Spring Kafka retry/DLT config và test handler cố tình fail. Assert DLT record rồi cleanup toàn bộ topic group thuộc run. Không dùng wildcard delete.

### Bài 12 — Parallel CI jobs

Giả sử hai CI jobs dùng cùng test Kafka broker. Thiết kế topic prefix chứa run ID và group IDs không trùng; dùng namespace/ACL theo job và cleanup chỉ owned resources. Khi nào nên chuyển sang broker-per-job?

### Bài 13 — Kafka Streams state store

Tạo test Kafka Streams có stateful aggregation, chạy hai lần với same application.id/state.dir. Quan sát sự khác nhau khi local state còn; sửa bằng unique application ID và cleanup state dir/broker.

### Bài 14 — Báo cáo teardown

Thêm test report ghi topic/group names, whether deleteTopics future succeeded, broker container lifecycle và số active consumers tại shutdown. Không log SASL credentials hoặc payload nhạy cảm.

## 30. Checklist trước khi chốt Messaging QA

- [ ] Xác định broker đang dùng: Kafka/RabbitMQ/JMS/khác, test-only hay shared.
- [ ] Biết message state, consumer progress và metadata là các tầng khác nhau.
- [ ] Không coi Kafka topic deletion là reset mọi committed group offsets.
- [ ] Không coi `auto.offset.reset=earliest` là reset một group đã commit hợp lệ.
- [ ] Test Kafka có topic/group IDs unique theo scope cần cô lập.
- [ ] Test consumer có timeouts/bounded polling, không sleep cố định.
- [ ] Test chờ producer send future nếu cần chứng minh message đã gửi.
- [ ] Manual commit chỉ xảy ra sau action/assertion phù hợp.
- [ ] Consumers/producer/admin/listener resources được close/stop.
- [ ] Teardown không xóa group khi vẫn còn active consumer.
- [ ] Chỉ xóa topic/queue/group test sở hữu.
- [ ] Khi dùng class-scoped broker, lifecycle container và Spring context cache phù hợp.
- [ ] Không chia sẻ static container vô tội vạ giữa các classes.
- [ ] Không để parallel tests reset/xóa tài nguyên của nhau.
- [ ] DLT/retry topics, retry listeners và scheduled callbacks đã được tính tới.
- [ ] RabbitMQ cleanup xét cả ready, unacked, DLQ và exchanges/bindings.
- [ ] JMS cleanup xét durable subscriptions, sessions và transactions.
- [ ] Kafka Streams cleanup xét application.id/internal topics/local state stores.
- [ ] Không dùng `@DirtiesContext` thay thế broker cleanup.
- [ ] Không nuốt cleanup failures cần quan sát.
- [ ] Không kết luận test đã pass khi thực tế bị skip/không có broker.
- [ ] Không xóa/purge/reset resources của staging/production.
- [ ] Có chính sách cleanup orphan resources ở CI theo allowlist/TTL.
- [ ] Assertions kiểm tra actual message/offset/outcome, không chỉ bean tồn tại.

## 31. Quy tắc quyết định cuối cùng

```text
Messaging integration test cần cô lập state?
         |
         +--> Broker private trong Testcontainers?
         |       |
         |       +--> Per-test unique topics/groups
         |       +--> Close consumer/listener/admin/producer
         |       +--> Delete owned topics nếu cần
         |       +--> Dispose broker sau test group/class
         |            -> Broker offsets/logs được reset
         |
         +--> Broker shared giữa classes/runs?
                 |
                 +--> Namespace resources theo run ID
                 +--> Stop active consumers/listeners
                 +--> Assert outcome và commit/ack state
                 +--> Delete ONLY owned inactive groups
                 +--> Delete ONLY owned topics/queues/DLQ
                 +--> Await admin operations with deadlines
                 +--> Track orphan cleanup, never wildcard
```

**Thông điệp chính:** “Dọn messaging test” không phải một lệnh xóa dữ liệu duy nhất. **Kafka records, consumer offsets, group membership và resource handles có vòng đời riêng; RabbitMQ unacked deliveries, DLQ và JMS durable subscriptions cũng vậy.** Với nhiều integration tests, chiến lược ít lỗi nhất thường là **broker test container riêng cho nhóm test, namespace riêng từng method, đóng consumers đúng thứ tự và hủy broker sau nhóm**. Khi buộc phải dùng shared broker, phải quản lý ownership, offset/group state, admin operations và bảo vệ các tài nguyên ngoài test.

## 32. Tài liệu chính thức

- Apache Kafka — Consumer configuration, `auto.offset.reset` và `enable.auto.commit`: https://kafka.apache.org/documentation/#consumerconfigs
- Apache Kafka — Basic operations, consumer groups/offset reset: https://kafka.apache.org/documentation/#basic_ops_consumer_group
- Apache Kafka — KafkaConsumer Javadoc (poll, commitSync, close, position, seek): https://kafka.apache.org/37/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html
- Apache Kafka — Admin API, deleteTopics/deleteConsumerGroups: https://kafka.apache.org/37/javadoc/org/apache/kafka/clients/admin/Admin.html
- Spring Boot 3.3 — Apache Kafka support: https://docs.spring.io/spring-boot/3.3/reference/messaging/kafka.html
- Spring Boot 3.3 — Testcontainers `@ServiceConnection`: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Kafka — Testing applications, `@EmbeddedKafka` and `KafkaTestUtils`: https://docs.spring.io/spring-kafka/reference/testing.html
- Spring Kafka — Container lifecycle, manual acknowledgments: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring Kafka — Retry topics and dead-letter topics: https://docs.spring.io/spring-kafka/reference/retrytopic.html
- Testcontainers Java — Kafka module, version-dependent API: https://java.testcontainers.org/modules/kafka/
- Testcontainers Java — JUnit Jupiter lifecycle: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers — Lifecycle and Spring context cache caveats: https://testcontainers.com/guides/testcontainers-container-lifecycle/
- RabbitMQ — Consumer acknowledgements and confirms: https://www.rabbitmq.com/docs/confirms
- RabbitMQ — Queues and queue lifecycle: https://www.rabbitmq.com/docs/queues
- RabbitMQ — Dead-letter exchanges: https://www.rabbitmq.com/docs/dlx
- Spring AMQP — RabbitAdmin / AmqpAdmin: https://docs.spring.io/spring-amqp/reference/amqp/admin.html
- Jakarta Messaging — Durable subscriptions and Session semantics: https://jakarta.ee/specifications/messaging/3.1/
- ActiveMQ Artemis — Address/queue/consumer management: https://activemq.apache.org/components/artemis/documentation/latest/
- JUnit Jupiter — Lifecycle annotations and execution: https://docs.junit.org/current/user-guide/
