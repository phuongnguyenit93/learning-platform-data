# Kiểm thử gửi, nhận thông điệp và xử lý thông điệp trùng với Spring Boot

## 1. Tình huống thực tế và yêu cầu của bài

Một dịch vụ nhận sự kiện `OrderCreated` từ Apache Kafka. Mỗi sự kiện yêu cầu cộng một số điểm thưởng cho đơn hàng. Producer gửi sự kiện lên broker; một `@KafkaListener` nhận sự kiện, cập nhật bảng `order_points` và ghi lịch sử trong bảng `processed_message`.

Nếu producer hoặc consumer gặp lỗi mạng rồi gửi lại cùng một sự kiện, Kafka có thể chuyển đến **hai bản ghi có cùng business message ID**. Hai bản ghi có thể có Kafka offsets khác nhau, nhưng cùng đại diện một yêu cầu nghiệp vụ. Nếu listener cứ cộng điểm mỗi lần nhận, khách hàng bị cộng hai lần. Vì vậy bài cần kiểm **cả hành trình gửi → broker → listener → database**, và kiểm thêm **idempotency**: xử lý lại cùng thông điệp không tạo thêm business effect.

Đây là bài thực hành tích hợp (*nhóm cha: Thực hành tích hợp*) của module **Spring Boot – testing**. Mục tiêu không chỉ là mock `KafkaTemplate.send()` để kiểm một phương thức được gọi: ta cần có broker thử nghiệm thật và listener thật nhận record bất đồng bộ.

**Sau bài, bạn có thể:**

1. Phân biệt gửi thành công lên broker, nhận bởi listener, commit giao dịch DB và commit consumer offset.
2. Viết integration tests dùng **Spring Boot 3.3.5, Java 17, Spring Kafka 3.2.x, JUnit Jupiter, `@EmbeddedKafka`**, không cần Docker.
3. Gửi JSON event bằng `KafkaTemplate`, kiểm `SendResult`/`RecordMetadata`, rồi chờ listener bằng **Awaitility** thay vì `Thread.sleep`.
4. Chọn **business `messageId`** rõ ràng, không lấy `Kafka offset` làm khóa idempotency.
5. Hiểu Kafka producer key theo `orderId` và quan hệ ordering theo partition.
6. Đặt ràng buộc `PRIMARY KEY(message_id)` trên bảng inbox để chống xử lý trùng **kể cả nhiều consumer instances**.
7. Đặt thao tác **INSERT inbox + UPDATE business state trong cùng JDBC transaction**, không check-then-act bằng `SELECT` rồi `INSERT` ở hai bước không đồng bộ.
8. Phân biệt `DuplicateKeyException` (được nhận diện là trùng) với các lỗi dữ liệu, network, code, SQL khác **phải được retry/điều tra**, không nuốt mọi exception.
9. Không coi cùng `messageId` nhưng **payload khác** là một lần gửi lại hợp lệ; nhận diện collision và đưa vào xử lý ngoại lệ.
10. Viết một project runnable với **12 JUnit Jupiter `@Test`**, kiểm gửi, nhận, lặp hai/ba lần, hai event IDs trên một đơn, hai đơn độc lập, offsets, transaction rollback, collision và validation.
11. Nắm **at-least-once vs exactly-once**: unique DB constraint giúp business effect trong DB xảy ra tối đa một lần theo message ID, nhưng không tự biến mọi email/HTTP/Kafka/DB side effects thành một giao dịch nguyên tử.
12. Lập kế hoạch mở rộng cho retry/backoff, dead-letter topic, poison messages, schema evolution, Testcontainers, observability và CI.
13. Hiểu vì sao `@Transactional` của test thread không rollback một listener chạy trên Kafka consumer thread.
14. Biết cách giảm flaky tests: topic/group riêng, dữ liệu riêng theo UUID, await theo kết quả DB, shutdown broker đúng lifecycle.

**Stack cố định:** Java 17, **Spring Boot 3.3.5**, Spring Kafka được Spring Boot BOM 3.3.x quản lý, JUnit Jupiter, H2 in-memory và `spring-kafka-test`. Các API thuộc Spring Kafka 3.2: `KafkaTemplate.send` trả `CompletableFuture`, `@EmbeddedKafka(... bootstrapServersProperty=..., kraft=true)`, `@KafkaListener`, JSON serializer/deserializer, `AckMode.RECORD`. Các đoạn có nhãn “minh họa” không phải file độc lập; toàn bộ file trong cây project ở mục 7–11 tạo thành chương trình đầy đủ.

## 2. Các mức bảo đảm: gửi, nhận, xử lý, commit

Để tránh kiểm sai thứ cần kiểm, phân biệt bốn mốc:

| Mốc | Quan sát trong bài | Có chứng minh business effect chưa? |
|---|---|---|
| **Producer gửi** | `KafkaTemplate.send(...)` trả một `CompletableFuture` | **Chưa**: asynchronous send có thể fail |
| **Broker xác nhận ghi record** | `future.get(timeout)` trả `SendResult` chứa topic/partition/offset | **Chưa**: consumer có thể chưa đọc |
| **Listener xử lý DB** | `@KafkaListener` gọi service; JDBC transaction commit thành công | **Có** đối với thay đổi DB đã commit |
| **Consumer offset được commit** | Container `AckMode.RECORD` commit sau listener return bình thường | Không đồng nghĩa DB và offset cùng nằm một atomic transaction |

**Một lịch sử có thể xảy ra:**

~~~text
Producer                Kafka broker             Listener                 H2 / SQL
   |                          |                      |                       |
   | send OrderCreated(id=A)  |                      |                       |
   |------------------------->|                      |                       |
   |    SendResult(topic,     |                      |                       |
   |      partition, offset)  |                      |                       |
   |<-------------------------|                      |                       |
   |                          |   deliver record A   |                       |
   |                          |--------------------->| INSERT processed A    |
   |                          |                      | UPDATE order points   |
   |                          |                      |---------------------->|
   |                          |                      |      COMMIT OK        |
   |                          |                      |<----------------------|
   |                          |                      | listener returns      |
   |                          |<---------------------| container commits offset
~~~

**Rủi ro cốt lõi:** Nếu DB đã commit nhưng process crash **trước khi offset commit**, sau restart/rebalance record A có thể được giao lại. Đó là lý do idempotency phải đặt ở consumer/business persistence, **không chỉ ở producer**.

Một test assert `future.get()` thành công **chưa kiểm nhận**. Một test assert listener method được Mockito gọi **chưa kiểm broker serialization/DB side effect**. Bài kiểm nhiều mốc với real embedded broker và SQL.

### 2.1. At-most-once, at-least-once và exactly-once

- **At-most-once**: message có thể bị mất nhưng không được xử lý lặp dưới giả định delivery pattern.
- **At-least-once**: message có thể được chuyển đến lại, nên consumer **phải chịu duplicates**.
- **Exactly-once processing** có phạm vi rất cụ thể trong Kafka transactional producer/stream processing; không tự cam kết giao dịch chung cho external PostgreSQL, HTTP API, email hoặc hệ thống thanh toán.
- **Idempotent business effect**: nhiều lần gọi cùng nghiệp vụ key vẫn cho kết quả hiệu dụng như một lần, ví dụ một `processed_message.message_id` chỉ dẫn tới một lần cộng điểm.

Trong bài, ta chứng minh tính **idempotent của cập nhật DB** theo message ID nhờ `PRIMARY KEY` và transaction. Không tuyên bố đã đạt distributed exactly-once end-to-end. Hai bản ghi Kafka vẫn tồn tại với hai offsets, nhưng chỉ có **một receipt** và **một lần cộng điểm**.

### 2.2. Tại sao `messageId` không phải Kafka offset?

Kafka offset định danh vị trí của một record **trong một topic partition**. Producer gửi lại cùng sự kiện bằng một `send()` mới có thể tạo offset mới. Nếu dedup theo offset, bạn coi bản ghi lặp như event mới.

**Business `messageId`** là UUID/ULID hoặc định danh sự kiện từ nguồn phát. Quy ước:

- Giữ nguyên `messageId` khi **retry cùng một sự kiện**.
- Tạo **messageId mới** cho một nghiệp vụ/sự kiện mới, ngay cả khi nó liên quan **cùng `orderId`**.
- Không đổi payload của một ID đã phát. Cùng `messageId` nhưng `orderId/points` khác là **collision/contract violation**.
- Chọn namespace cho idempotency key đủ rộng: có thể dùng `(consumer_name, message_id)` hoặc `(event_type, message_id)` trong production nếu cùng một ID được nhiều nhóm consumer xử lý độc lập.
- Không dùng `orderId` làm khóa dedup nếu một đơn hàng hợp lệ có thể có nhiều **event khác nhau**.

## 3. Phân biệt bốn ID/khóa dễ nhầm

| Thành phần | Ví dụ | Mục đích |
|---|---|---|
| Business `messageId` | `event-7c...` | Chống xử lý trùng theo nghiệp vụ |
| Business `orderId` | `order-1a...` | Thực thể được cập nhật và Kafka record key trong ví dụ |
| Kafka key | `order-1a...` | Cùng key thường được partitioner gửi vào cùng partition để giữ thứ tự theo key |
| Kafka topic/partition/offset | `orders.created.v1/0/42` | Vị trí broker record, không phải semantic idempotency ID |

Trong test broker chỉ có **một partition** để dễ quan sát. Production có thể nhiều partitions; khi key ổn định, các records cùng order thường được gửi vào cùng partition, nhưng **không đồng nghĩa Kafka bảo đảm thứ tự trên nhiều topics/partitions hoặc xuyên consumer groups**. Tính chống trùng **không được phụ thuộc duy nhất vào partition ordering**.

### 3.1. Producer idempotence khác consumer idempotence

Kafka producer có `enable.idempotence=true` để xử lý retry của **producer gửi batch** theo producer ID/sequence, giúp tránh một lớp duplicate do retries ở giao thức producer. Nhưng nếu application chủ động gọi `send(event)` **hai lần**, đó là hai sends có hai sequence numbers; Kafka **vẫn lưu hai records**. Producer idempotence không biết rằng `messageId` trong JSON của hai records giống nhau.

Consumer inbox `PRIMARY KEY(message_id)` giải quyết lớp **business duplicate** sau khi record tới listener. Hai cơ chế bổ sung nhau, không thay thế nhau.

## 4. Nguyên tắc thiết kế một consumer idempotent

**Sai: SELECT trước, rồi INSERT/UPDATE sau, không khóa:**

~~~java
// Phản mẫu minh họa; không thuộc project runnable.
// Hai consumer instances có thể cùng thấy exists=false.
if (!repository.existsByMessageId(event.messageId())) {
    repository.updateBusinessState(event);
    repository.saveReceipt(event.messageId());
}
~~~

Race:

~~~text
Consumer A: SELECT processed(A) -> chưa có
Consumer B: SELECT processed(A) -> chưa có
Consumer A: UPDATE + INSERT
Consumer B: UPDATE + INSERT   (effect có thể bị áp hai lần)
~~~

**Đúng hơn:** database **đảm bảo unique key** và đặt **ghi nhận đã xử lý cùng business update trong một transaction**. Thứ tự insert-first:

~~~text
BEGIN TRANSACTION
  INSERT INTO processed_message(message_id,...)
  UPDATE order_points SET total_points=total_points+?
COMMIT

Nếu INSERT gặp duplicate PK:
  transaction lỗi/rollback
  không UPDATE order_points
  đọc receipt đã commit để xem payload trùng thực sự
  cùng payload -> no-op, cho listener return bình thường
  payload khác -> báo lỗi/đưa vào tuyến xử lý lỗi
~~~

`@Transactional` chỉ đủ nếu phương thức được gọi qua **Spring proxy**, giao dịch bao trùm các SQL statements thật, và DB hỗ trợ transaction. Project dùng `OrderInboxService` là Spring `@Service` riêng; listener gọi nó qua DI để transaction interceptor chạy. **Không bắt `DuplicateKeyException` ngay bên trong phương thức transactional rồi tiếp tục cập nhật**: ở PostgreSQL, một lỗi SQL có thể khiến transaction ở trạng thái abort; catch **ngoài proxy** sau rollback rõ ràng hơn.

**Giới hạn của mẫu:** Nếu service gửi email hoặc HTTP thanh toán **giữa** INSERT receipt và COMMIT, hai thao tác đó không rollback cùng DB. Khi cần side effect ngoài DB, sử dụng **transactional outbox**, dispatch/idempotency key ở downstream và thiết kế retry riêng.

## 5. Chiến lược kiểm thử phù hợp

**Một suite tốt nên có các tầng:**

1. **Contract/unit tests**: Java record validation, mapping ID, business method logic; không cần broker.
2. **Repository/transaction tests**: duplicate key, rollback, order không tồn tại; dùng SQL thật/H2 hoặc DB thật.
3. **Messaging integration tests**: `KafkaTemplate.send`, JSON serialization/deserialization, listener thật, DB thật, duplicates và asynchronous completion.
4. **Infrastructure tests với container thật**: PostgreSQL/Kafka production-like, broker restart, consumer rebalance, DLT, retry, network failures, security (SASL/TLS).
5. **End-to-end tests**: nhiều services, outbox/inbox, downstream side effects/compensation.

Bài tập trung mức **3** và phần transaction của mức **2**. Broker nhúng (`spring-kafka-test`) không yêu cầu Docker nhưng không thay thế mọi kiểm thử tương thích với managed Kafka cluster; H2 cũng không đại diện hoàn toàn cho PostgreSQL transaction/error semantics.

### 5.1. Vì sao không kiểm bằng `Thread.sleep(500)`?

`@KafkaListener` xử lý trên consumer thread, thời điểm được broker schedule phụ thuộc startup, partition assignment, CPU/GC. Sleep cố định có thể vừa chậm vừa flaky. Dùng:

~~~java
await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> assertEquals(1, jdbcCount()));
~~~

**Snippet minh họa**: phải dùng `org.awaitility.Awaitility.await`, Java Duration và `jdbcCount()` là hàm test tự định nghĩa. Awaitility lặp assertion đến khi thành công hoặc hết timeout hữu hạn. Trong project mẫu, ta đợi **audit của listener sau khi DB commit**, rồi kiểm SQL state. Đừng chỉ đợi Mockito invocation được ghi lại nếu bạn cần chứng minh business update đã commit.

### 5.2. Kiểm duplicates không cần cố tình crash broker

Gửi **hai hoặc ba Kafka records với cùng `messageId`** là cách **deterministic** kiểm tính idempotent khi consumer nhận bản ghi trùng. Nó **không tự chứng minh** hành vi Kafka redelivery sau consumer crash, rebalance hoặc offset commit failure; những kịch bản đó cần fault-injection/chaos integration tests riêng. Phải mô tả phạm vi chứng minh chính xác.

## 6. Thiết kế runnable project

**Project:** Gradle, Spring Boot3.3.5, Java17, Spring Kafka, Spring JDBC, H2, Spring Kafka Test và JUnit Jupiter/Awaitility.

**Flow thực:**

~~~text
JUnit test:
  create order_points(orderId,0)
  publisher.publish(new OrderCreatedEvent(messageId,orderId,points))
        |
        v
  KafkaTemplate<String,OrderCreatedEvent>
        |
        v
  @EmbeddedKafka broker: orders.created.v1
        |
        v
  @KafkaListener OrderMessageListener
        |
        v
  OrderInboxService.processOnce(event)  <-- @Transactional
        |
        +-- INSERT processed_message UNIQUE(message_id)
        +-- UPDATE order_points += points
        +-- COMMIT
        |
        +-- on duplicate PK -> rollback, compare stored receipt
        |        +-- same payload -> audit duplicate, return normally
        |        +-- different payload -> throw, error handling required
        |
        v
  DeliveryAudit (test observation only)
        |
        v
  Awaitility waits; JUnit checks persisted state
~~~

**Phân biệt test instrumentation:** `DeliveryAudit` dưới đây là một Spring bean in-memory đếm số lần listener hoàn tất với mỗi message ID. Nó giúp tests đợi hai/ba deliveries. Trong production nên thay bằng bounded Micrometer counters/traces hoặc test-only instrumentation, không giữ **mọi messageId mãi mãi** trong `ConcurrentHashMap` gây memory leak. **Database inbox là nguồn sự thật**, audit chỉ hỗ trợ quan sát asynchronous completion.

### 6.1. Cây thư mục đầy đủ

~~~text
settings.gradle
build.gradle
src/main/java/demo/messaging/MessagingApplication.java
src/main/java/demo/messaging/OrderTopics.java
src/main/java/demo/messaging/OrderCreatedEvent.java
src/main/java/demo/messaging/OrderEventPublisher.java
src/main/java/demo/messaging/OrderInboxService.java
src/main/java/demo/messaging/OrderMessageListener.java
src/main/java/demo/messaging/DeliveryAudit.java
src/test/resources/application.properties
src/test/resources/schema.sql
src/test/resources/junit-platform.properties
src/test/java/demo/messaging/MessagingIntegrationTest.java
~~~

Không có một `@Configuration` nào ở test source bị `@SpringBootApplication` vô tình component scan; toàn bộ sample Java dưới main có trách nhiệm rõ. DB schema chỉ ở `src/test/resources/schema.sql`, không tự chạy SQL demo trên production profile.

## 7. Gradle và cấu hình broker/DB test

**settings.gradle**

~~~groovy
rootProject.name = 'messaging-idempotency-integration-tests'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.kafka:spring-kafka'

    // H2 dùng để chạy integration test không cần external DB.
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Một JVM: tránh nhiều embedded brokers cùng dùng
    // shared system properties/ports trong ví dụ.
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Tại sao có `runtimeOnly h2` chứ không `testImplementation h2`?** H2 được dùng bởi Spring Boot application context **khi chạy tests**, và dependency ở Gradle runtime classpath sẽ có trong test runtime classpath. Đối với project ứng dụng thật dùng PostgreSQL, tách H2 vào `testRuntimeOnly 'com.h2database:h2'` cũng là một lựa chọn nếu runtime production có driver riêng. Bài demo chỉ khởi tạo app qua SpringBootTest và không chạy prod.

**src/test/resources/junit-platform.properties**

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

Tắt parallel JUnit để không lẫn broker lifecycle, SQL fixture setup và test observations trong bài. Không phải khuyến nghị áp dụng lên mọi test suite; các tests có resource isolation có thể chạy song song. Khi tăng Gradle `maxParallelForks` hoặc chạy modules song song, **mỗi JVM có Spring TestContext cache khác** và resource locks không đi xuyên JVM.

### 7.1. Cấu hình test-only

**src/test/resources/application.properties**

~~~properties
spring.main.banner-mode=off

# SQL/H2 only in tests. Schema nằm trong src/test/resources/schema.sql.
spring.datasource.url=jdbc:h2:mem:message_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

# Producer JSON. Tắt Java type headers để contract bớt lệ thuộc class name.
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.springframework.kafka.support.serializer.JsonSerializer
spring.kafka.producer.acks=all
spring.kafka.producer.properties.enable.idempotence=true
spring.kafka.producer.properties.spring.json.add.type.headers=false

# Consumer JSON. Chỉ chấp nhận package demo.messaging trong bài.
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties.spring.json.use.type.headers=false
spring.kafka.consumer.properties.spring.json.value.default.type=demo.messaging.OrderCreatedEvent
spring.kafka.consumer.properties.spring.json.trusted.packages=demo.messaging
spring.kafka.consumer.group-id=order-inbox-demo-group
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.enable-auto-commit=false

# Offset commit được container thực hiện sau listener return bình thường.
spring.kafka.listener.ack-mode=record
spring.kafka.listener.missing-topics-fatal=true
~~~

**Lưu ý properties `spring.kafka.bootstrap-servers`:** file **không hard-code `localhost:9092`**. `@EmbeddedKafka(bootstrapServersProperty="spring.kafka.bootstrap-servers")` trên integration test sẽ map broker localhost port được chọn động vào property của Boot, dựa trên API của `spring-kafka-test`. Không nhầm Kafka broker address với H2 datasource URL.

**Tại sao `spring.json.use.type.headers=false` và `value.default.type`?** Khi producer gửi, JSON serializer được yêu cầu không gắn Java type metadata. Consumer không dựa vào type header mà dùng type `demo.messaging.OrderCreatedEvent`. Điều này giúp demo có format JSON rõ, nhưng production nên có **schema contract/version** (Avro/Protobuf/JSON Schema) và registry/mapping phù hợp hơn là mặc định mọi event đều có một class.

**`AckMode.RECORD`**: khi consumer auto-commit=false và không bật Kafka transactions, container commit offset sau listener xử lý thành công từng record. Một lỗi ném từ listener đi tới error handler và **không được coi là xử lý thành công ngay**. Bài chưa cấu hình DLT; đối với poison messages production phải thêm retry/recoverer.

### 7.2. Test SQL schema

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE order_points (
    order_id VARCHAR(100) PRIMARY KEY,
    total_points INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE processed_message (
    message_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    points INTEGER NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
~~~

Chủ động tách **bảng business state** và **bảng inbox**. Unique `message_id` là cơ chế chống trùng mức database, không phụ thuộc Java `ConcurrentHashMap`. Business update và insert receipt sẽ trong **cùng một transaction**. Với một message id đã tồn tại, lần sau không được UPDATE order points.

**H2 caveat:** H2 thuận tiện để chạy local nhưng không giống PostgreSQL hoàn toàn về lock, isolation, SQLState và transactional behavior. Trước khi production hóa, chạy thêm integration tests với **PostgreSQL Testcontainers** và migration thực. Đừng dùng một inbox in-memory nếu nghiệp vụ phải chống trùng sau process restart.

## 8. Source Java main: application, event và publisher

### 8.1. Application chính

**src/main/java/demo/messaging/MessagingApplication.java**

~~~java
package demo.messaging;

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
~~~

`@EnableKafka` làm rõ việc kích hoạt `@KafkaListener` annotated endpoints. Spring Boot tự cung cấp `KafkaTemplate`, listener container factory và các beans cơ sở khi dependencies/properties đầy đủ. Không có embedded HTTP server vì project không thêm `spring-boot-starter-web`; tests dùng `WebEnvironment.NONE`.

### 8.2. Một hằng tên topic dùng chung

**src/main/java/demo/messaging/OrderTopics.java**

~~~java
package demo.messaging;

public final class OrderTopics {

    public static final String CREATED = "orders.created.v1";

    private OrderTopics() {
    }
}
~~~

Producer, consumer và `@EmbeddedKafka` dùng **cùng constant**; tránh typo `orders.create.v1` vs `orders.created.v1`. Version suffix `v1` là contract namespace minh họa; để phát hành schema mới cần chính sách compatibility/versioning riêng.

### 8.3. Event contract Java record

**src/main/java/demo/messaging/OrderCreatedEvent.java**

~~~java
package demo.messaging;

public record OrderCreatedEvent(
        String messageId,
        String orderId,
        int points) {

    public OrderCreatedEvent {
        if (messageId == null || messageId.isBlank()) {
            throw new IllegalArgumentException(
                    "messageId must not be blank");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        if (points <= 0) {
            throw new IllegalArgumentException(
                    "points must be positive");
        }
    }
}
~~~

Java 17 records tương thích Jackson trong Spring Kafka 3.2/Boot 3.3. `messageId` **không đổi** khi retry semantic event; `orderId` là aggregate id dùng làm Kafka record key; `points` là business amount. Constructor validation bảo vệ những event được tạo qua Java code và event JSON được deserialize; lỗi deserialization trước listener cần error handler riêng trong production.

**Không coi `record` là schema registry.** Đổi tên `points`, xóa trường hoặc thay kiểu có thể phá consumer khác dù Java code của producer compile. Gắn contract/schema test khi nhiều services tham gia.

### 8.4. Producer thực

**src/main/java/demo/messaging/OrderEventPublisher.java**

~~~java
package demo.messaging;

import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafka;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafka) {
        this.kafka = kafka;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>>
            publish(OrderCreatedEvent event) {

        // orderId là Kafka key: giữ records của một order
        // trong cùng một partition khi cấu hình partition ổn định.
        return kafka.send(
                OrderTopics.CREATED, event.orderId(), event);
    }
}
~~~

`KafkaTemplate.send` trả `CompletableFuture<SendResult<...>>`; producer code production không nhất thiết `.get()` block. **Test** được phép chờ với finite timeout để khẳng định broker đã nhận. `SendResult` có `RecordMetadata.topic()`, `partition()`, `offset()`.

**Không dùng thành công của send để thay kiểm business effect.** Future hoàn thành chỉ chứng minh producer acknowledgment theo `acks` đã cấu hình, chưa nói rằng listener đã xử lý xong database transaction.

## 9. Inbox service và listener: atomic DB effect và duplicate detection

### 9.1. Service giao dịch

**src/main/java/demo/messaging/OrderInboxService.java**

~~~java
package demo.messaging;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderInboxService {

    private final JdbcTemplate jdbc;

    public OrderInboxService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void processOnce(OrderCreatedEvent event) {
        // DB unique constraint là điểm phân xử giữa
        // các consumer instances (không phải Java if-check).
        jdbc.update(
                "INSERT INTO processed_message "
                        + "(message_id, order_id, points) "
                        + "VALUES (?, ?, ?)",
                event.messageId(),
                event.orderId(),
                event.points());

        // Business mutation nằm trong CÙNG JDBC transaction.
        int updated = jdbc.update(
                "UPDATE order_points "
                        + "SET total_points = total_points + ? "
                        + "WHERE order_id = ?",
                event.points(), event.orderId());

        if (updated != 1) {
            throw new IllegalArgumentException(
                    "Unknown orderId: " + event.orderId());
        }
    }

    public boolean matchesStoredReceipt(OrderCreatedEvent event) {
        // Gọi SAU khi transaction duplicate đã rollback.
        List<OrderCreatedEvent> stored = jdbc.query(
                "SELECT message_id, order_id, points "
                        + "FROM processed_message WHERE message_id = ?",
                (rs, rowNum) -> new OrderCreatedEvent(
                        rs.getString("message_id"),
                        rs.getString("order_id"),
                        rs.getInt("points")),
                event.messageId());

        return stored.size() == 1 && stored.get(0).equals(event);
    }
}
~~~

**Semantics cần nắm:**

- `INSERT` vào `processed_message` xảy ra trước business UPDATE.
- `PRIMARY KEY(message_id)` khiến duplicate cùng ID **fail ngay khi INSERT**, nên không tới UPDATE.
- Phương thức `@Transactional` nằm trên Spring-managed service và được listener gọi qua một bean khác, nên transactional proxy bao trùm cả hai lệnh.
- Nếu `orderId` không có, UPDATE trả 0; `IllegalArgumentException` làm transaction rollback, bao gồm **xóa insert receipt chưa commit**. Event ấy không bị “đánh dấu đã xử lý” sai.
- `matchesStoredReceipt` so nội dung đã lưu để không im lặng bỏ qua **cùng ID nhưng payload khác**. Nó là một SQL read độc lập sau failed transaction. Với PostgreSQL, không được bỏ qua vấn đề transaction aborted rồi query ngay bên trong cùng transaction lỗi.
- Nếu schema có nhiều consumer logical roles, khóa chính nên có thêm `consumer_name`/scope. Ví dụ minh họa chỉ có **một** consumer subscriber và một loại event.

**Cảnh báo:** Đây là transactional inbox **trong một DB**. Nếu phát event khác, gọi API bên ngoài hoặc gửi email trong `processOnce`, thêm outbox/idempotency key cho downstream; DB rollback không undo email đã gửi.

### 9.2. Instrumentation cho integration tests

**src/main/java/demo/messaging/DeliveryAudit.java**

~~~java
package demo.messaging;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class DeliveryAudit {

    private final ConcurrentMap<String, AtomicInteger> seen =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, AtomicInteger> duplicates =
            new ConcurrentHashMap<>();

    private static void increment(
            ConcurrentMap<String, AtomicInteger> map, String id) {

        map.computeIfAbsent(id, key -> new AtomicInteger())
                .incrementAndGet();
    }

    public void applied(String messageId) {
        increment(seen, messageId);
    }

    public void duplicate(String messageId) {
        increment(seen, messageId);
        increment(duplicates, messageId);
    }

    public int observed(String messageId) {
        AtomicInteger counter = seen.get(messageId);
        return counter == null ? 0 : counter.get();
    }

    public int duplicateCount(String messageId) {
        AtomicInteger counter = duplicates.get(messageId);
        return counter == null ? 0 : counter.get();
    }
}
~~~

Không có `Thread.sleep`, `synchronized` trên test instance hay static global counters. Bởi event IDs được tạo mới bằng UUID trong mỗi test, các observations không bị lẫn. Đây là **demo/test audit**; production không nên giữ một map tăng không giới hạn theo mọi ID. Đổi sang Micrometer counters/structured logs/trace ID hoặc đặt bean dưới test configuration nếu app thực có nhiều consumers.

### 9.3. Kafka listener thực

**src/main/java/demo/messaging/OrderMessageListener.java**

~~~java
package demo.messaging;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageListener {

    private final OrderInboxService inbox;
    private final DeliveryAudit audit;

    public OrderMessageListener(
            OrderInboxService inbox,
            DeliveryAudit audit) {

        this.inbox = inbox;
        this.audit = audit;
    }

    @KafkaListener(topics = OrderTopics.CREATED)
    public void on(OrderCreatedEvent event) {
        try {
            inbox.processOnce(event);
            // processOnce trả về sau khi transaction commit.
            audit.applied(event.messageId());
        } catch (DuplicateKeyException duplicate) {
            // Exception đã đi ra ngoài transactional proxy,
            // transactional interceptor đã rollback.
            if (!inbox.matchesStoredReceipt(event)) {
                throw new IllegalStateException(
                        "messageId reused with different payload",
                        duplicate);
            }

            // Trùng hợp lệ: no-op, cho listener return bình thường.
            audit.duplicate(event.messageId());
        }
    }
}
~~~

**Tại sao chỉ catch `DuplicateKeyException`?** Duplicate key của inbox là trường hợp **dự kiến** khi redelivery cùng message. Nếu DB unavailable, `IllegalArgumentException` do order không tồn tại, lỗi deserialize, bug code, hoặc receipt có nội dung xung đột, listener **không được nuốt lỗi và commit offset như thành công**. Những lỗi ấy cần retry/backoff/DLT/alert được cấu hình rõ ràng; project demo không cố gửi poison message qua Kafka vì không khai báo DLT pipeline.

**Tại sao `audit.applied` nằm sau `processOnce`?** `@Transactional` method trả về sau transaction interceptor xử lý commit (trong cấu hình JDBC synchronous thông thường). Nhờ vậy test đợi `audit.observed` rồi kiểm DB có cơ sở rõ hơn. Nhưng `audit.applied` vẫn **trước Kafka offset commit** của container, nên observed count không chứng minh offset đã được broker commit. Đây là sự phân biệt tầng bảo đảm.

**Khi một message ID bị trùng với payload khác**, `matchesStoredReceipt` trả false, listener throw, không coi collision là retry hợp lệ. Khi đó cần DLT/alert/operator handling để tránh một poison record chặn partition mãi.

## 10. Một integration test class với 12 JUnit Jupiter methods

**src/test/java/demo/messaging/MessagingIntegrationTest.java**

~~~java
package demo.messaging;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@EmbeddedKafka(
        topics = OrderTopics.CREATED,
        partitions = 1,
        kraft = true,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MessagingIntegrationTest {

    @Autowired
    OrderEventPublisher publisher;

    @Autowired
    OrderInboxService inbox;

    @Autowired
    DeliveryAudit audit;

    @Autowired
    JdbcTemplate jdbc;

    private String newOrder() {
        String orderId = "order-" + UUID.randomUUID();

        jdbc.update(
                "INSERT INTO order_points "
                        + "(order_id, total_points) VALUES (?, 0)",
                orderId);

        return orderId;
    }

    private OrderCreatedEvent event(String orderId, int points) {
        return new OrderCreatedEvent(
                "evt-" + UUID.randomUUID(), orderId, points);
    }

    private SendResult<String, OrderCreatedEvent> send(
            OrderCreatedEvent event) throws Exception {

        // Wait for broker acknowledgment, NOT consumer completion.
        return publisher.publish(event)
                .get(20, TimeUnit.SECONDS);
    }

    private void awaitObserved(String messageId, int atLeast) {
        await().atMost(Duration.ofSeconds(30))
                .untilAsserted(() ->
                        assertTrue(
                                audit.observed(messageId) >= atLeast));
    }

    private int points(String orderId) {
        return jdbc.queryForObject(
                "SELECT total_points FROM order_points "
                        + "WHERE order_id = ?",
                Integer.class,
                orderId);
    }

    private int receiptCount(String messageId) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_message "
                        + "WHERE message_id = ?",
                Integer.class, messageId);
    }

    @Test
    void sendReturnsTopicPartitionAndOffset() throws Exception {
        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 7);

        RecordMetadata meta = send(e).getRecordMetadata();

        assertEquals(OrderTopics.CREATED, meta.topic());
        assertEquals(0, meta.partition());
        assertTrue(meta.offset() >= 0);

        awaitObserved(e.messageId(), 1);
        assertEquals(7, points(orderId));
    }

    @Test
    void consumerWritesReceiptAndUpdatesOrder() throws Exception {
        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 9);

        send(e);
        awaitObserved(e.messageId(), 1);

        assertEquals(1, receiptCount(e.messageId()));
        assertEquals(9, points(orderId));
        assertEquals(0, audit.duplicateCount(e.messageId()));
    }

    @Test
    void sameMessageTwiceAppliesBusinessEffectOnlyOnce()
            throws Exception {

        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 11);

        send(e);
        send(e);
        awaitObserved(e.messageId(), 2);

        assertEquals(1, receiptCount(e.messageId()));
        assertEquals(11, points(orderId));
        assertTrue(audit.duplicateCount(e.messageId()) >= 1);
    }

    @Test
    void sameMessageThreeTimesStillAppliesOnlyOnce()
            throws Exception {

        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 13);

        send(e);
        send(e);
        send(e);
        awaitObserved(e.messageId(), 3);

        assertEquals(1, receiptCount(e.messageId()));
        assertEquals(13, points(orderId));
        assertTrue(audit.duplicateCount(e.messageId()) >= 2);
    }

    @Test
    void differentMessageIdsOnSameOrderBothCount()
            throws Exception {

        String orderId = newOrder();
        OrderCreatedEvent first = event(orderId, 4);
        OrderCreatedEvent second = event(orderId, 6);

        send(first);
        send(second);
        awaitObserved(first.messageId(), 1);
        awaitObserved(second.messageId(), 1);

        assertEquals(4 + 6, points(orderId));
        assertEquals(1, receiptCount(first.messageId()));
        assertEquals(1, receiptCount(second.messageId()));
    }

    @Test
    void eventsForDifferentOrdersDoNotInterfere()
            throws Exception {

        String orderA = newOrder();
        String orderB = newOrder();
        OrderCreatedEvent eventA = event(orderA, 3);
        OrderCreatedEvent eventB = event(orderB, 17);

        send(eventA);
        send(eventB);
        awaitObserved(eventA.messageId(), 1);
        awaitObserved(eventB.messageId(), 1);

        assertEquals(3, points(orderA));
        assertEquals(17, points(orderB));
    }

    @Test
    void sameMessageIdAtTwoOffsetsIsStillOneBusinessEvent()
            throws Exception {

        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 5);

        RecordMetadata first = send(e).getRecordMetadata();
        RecordMetadata second = send(e).getRecordMetadata();

        assertEquals(first.partition(), second.partition());
        assertTrue(second.offset() > first.offset());

        awaitObserved(e.messageId(), 2);

        assertEquals(1, receiptCount(e.messageId()));
        assertEquals(5, points(orderId));
    }

    @Test
    void missingOrderRollsBackReceiptAndBusinessUpdate() {
        String unknown = "missing-" + UUID.randomUUID();
        OrderCreatedEvent e = event(unknown, 10);

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> inbox.processOnce(e));

        assertTrue(error.getMessage().contains("Unknown orderId"));
        assertEquals(0, receiptCount(e.messageId()));

        // Không gửi poison record vào Kafka trong test này.
        // Kiểm transaction rollback trực tiếp qua Spring proxy.
    }

    @Test
    void directDuplicateIsRejectedByUniqueConstraint() {
        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 8);

        inbox.processOnce(e);

        assertThrows(
                DuplicateKeyException.class,
                () -> inbox.processOnce(e));

        assertEquals(1, receiptCount(e.messageId()));
        assertEquals(8, points(orderId));
        assertTrue(inbox.matchesStoredReceipt(e));
    }

    @Test
    void sameIdWithDifferentPayloadIsRecognizedAsCollision() {
        String orderId = newOrder();
        OrderCreatedEvent original = event(orderId, 6);
        OrderCreatedEvent conflicting = new OrderCreatedEvent(
                original.messageId(), orderId, 999);

        inbox.processOnce(original);

        assertTrue(inbox.matchesStoredReceipt(original));
        assertFalse(inbox.matchesStoredReceipt(conflicting));
        assertEquals(6, points(orderId));

        // Không gửi conflicting qua Kafka:
        // cần DLT/recovery policy trước khi test poison flow.
    }

    @Test
    void invalidEventConstructionIsRejected() {
        String orderId = newOrder();

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderCreatedEvent(null, orderId, 2));

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderCreatedEvent(" ", orderId, 2));

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderCreatedEvent("evt-valid", "", 2));

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderCreatedEvent("evt-valid", orderId, 0));
    }

    @Test
    void storedReceiptPreservesOriginalPayload() throws Exception {
        String orderId = newOrder();
        OrderCreatedEvent e = event(orderId, 23);

        send(e);
        awaitObserved(e.messageId(), 1);

        Map<String, Object> stored = jdbc.queryForMap(
                "SELECT message_id, order_id, points "
                        + "FROM processed_message WHERE message_id = ?",
                e.messageId());

        assertEquals(e.messageId(), stored.get("MESSAGE_ID"));
        assertEquals(orderId, stored.get("ORDER_ID"));
        assertEquals(23, ((Number) stored.get("POINTS")).intValue());
        assertEquals(23, points(orderId));
    }
}
~~~

### 10.1. Đếm chính xác 12 JUnit tests

| Phương thức `@Test` | Khẳng định chính |
|---|---|
| `sendReturnsTopicPartitionAndOffset` | Broker ACK có metadata; listener và DB hoàn tất về sau |
| `consumerWritesReceiptAndUpdatesOrder` | Nhận một message → một inbox row, một business effect |
| `sameMessageTwiceAppliesBusinessEffectOnlyOnce` | Gửi cùng id 2 lần → 1 effect, 1 duplicate |
| `sameMessageThreeTimesStillAppliesOnlyOnce` | Gửi 3 lần → 1 effect, ít nhất 2 duplicates |
| `differentMessageIdsOnSameOrderBothCount` | Cùng order nhưng hai event IDs → cộng cả hai |
| `eventsForDifferentOrdersDoNotInterfere` | Hai order IDs riêng không ảnh hưởng |
| `sameMessageIdAtTwoOffsetsIsStillOneBusinessEvent` | Kafka offsets khác không phá business dedup |
| `missingOrderRollsBackReceiptAndBusinessUpdate` | UPDATE=0 → rollback cả inbox insert |
| `directDuplicateIsRejectedByUniqueConstraint` | DB PK trực tiếp chống trùng, không double-update |
| `sameIdWithDifferentPayloadIsRecognizedAsCollision` | Cùng id khác payload bị nhận diện bất nhất |
| `invalidEventConstructionIsRejected` | Event contract chặn ID rỗng/points không hợp lệ |
| `storedReceiptPreservesOriginalPayload` | Inbox lưu đúng id/orderId/points sau consume |
| **Tổng** | **12 phương thức JUnit Jupiter** |

**Vì sao assertions không dựa test order?** Mỗi test dùng UUID mới cho `orderId` và `messageId`; không gọi `DELETE FROM ...` trong `@BeforeEach` làm xóa dữ liệu mà listener của test trước còn dùng. `junit-platform.properties` tắt parallelism; các sends đều chờ broker ACK rồi đợi listener audit. Nếu bạn vẫn muốn tách DB cho mỗi test, dùng unique schema/namespace riêng thay vì truncate global table trong khi consumers còn làm việc.

**Vì sao nhiều tests assert `audit.observed(id) >= n` thay vì bằng đúng n?** Kafka là hệ at-least-once; nếu có redelivery bất thường, số lần giao có thể lớn hơn các sends chủ động. Business invariant vẫn là **one receipt/one effect per business ID**. Nếu logic cần assert số retries chính xác, phải cô lập retry policy và đo delivery attempts theo test-specific state; không trộn với mục tiêu idempotency.

### 10.2. Một lưu ý về `@DirtiesContext`

`@DirtiesContext(classMode=AFTER_CLASS)` đóng test context sau khi cả class hoàn tất để giải phóng embedded broker/test resources do context quản lý. Nó **không** gắn lên từng method, tránh khởi tạo Kafka/DB lại cho mọi test. Không cần `@DirtiesContext` chỉ để xóa inbox rows; mỗi test đã sử dụng unique IDs.

Nếu có nhiều test classes cùng @EmbeddedKafka và cùng Spring cached context, cần thiết kế topic/broker ownership và profile keys rõ ràng. Đừng dùng `@DirtiesContext` đại trà hoặc chạy tests này song song rồi khiến class A đóng broker mà class B còn đang dùng.

## 11. Chạy Gradle và diễn giải output

Để chạy project cần JDK17 và Gradle tương thích với Spring Boot3.3.5, quyền tải Maven Central lần đầu. Embedded Kafka cần tài nguyên CPU/RAM, temporary dirs và local loopback ports; **không cần Docker**. Nếu CI dùng sandbox cấm bind localhost ports, embedded broker vẫn có thể không start — đó là giới hạn môi trường.

Nếu project đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu mới tạo các file trong cây nhưng **chưa tạo `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`**, bạn không thể dùng `./gradlew` ngay. Dùng Gradle đã cài để tạo wrapper hoặc chạy:

~~~bash
gradle test
~~~

**Chạy một test riêng:**

~~~bash
./gradlew test --tests demo.messaging.MessagingIntegrationTest.sameMessageTwiceAppliesBusinessEffectOnlyOnce
~~~

**Chạy toàn class:**

~~~bash
./gradlew test --tests demo.messaging.MessagingIntegrationTest
~~~

**Báo cáo Gradle:** `build/reports/tests/test/index.html`; XML `build/test-results/test/TEST-*.xml`. Các logs của embedded Kafka có thể rất dài và thứ tự khác nhau. Kết quả thiết kế mong đợi là **12 JUnit tests PASS**, nhưng đây là **dự kiến dựa trên code/API**; không phải khẳng định đã chạy suite trong môi trường người học.

**Không có stdout chính xác cố định**: Kafka offsets, ephemeral port, consumer thread names và timing thay đổi mỗi run. Do đó bài assert offset không âm/tăng ở hai sends sequential cùng partition, chứ không hard-code offset `0` hoặc port `9092`. `SendResult` không chứng minh listener done, nên luôn theo sau bằng await và SQL assertion.

### 11.1. Nếu broker startup chậm

- Kiểm JDK17 có sẵn, dependency Spring Kafka Test tương thích Boot BOM.
- Đảm bảo `@EmbeddedKafka` đã map `spring.kafka.bootstrap-servers`; không để producer trỏ broker mặc định ở localhost:9092.
- Kiểm class có `kraft=true` khả dụng với Spring Kafka3.2.
- Xem `RecordMetadata` logs/broker startup errors, cổng bị chiếm và temporary disk.
- Tăng **test wait timeout có giới hạn hợp lý** theo CI thực; không thêm `Thread.sleep` bừa.
- Không tự tuyên bố được test suite xanh chỉ vì producer `send().get()` đã trả.

## 12. Test sending và receiving: những lỗi đo lường phổ biến

### 12.1. “Producer ACK” không có nghĩa listener đã chạy

~~~java
SendResult<String, OrderCreatedEvent> result =
        publisher.publish(event).get(20, TimeUnit.SECONDS);

assertEquals(
        OrderTopics.CREATED,
        result.getRecordMetadata().topic());
~~~

Snippet dùng biến `publisher`/`event` từ class test. Lúc future hoàn thành, broker đã nhận record theo producer acknowledgment semantics, nhưng consumer có thể chưa được assign partition. Phải đợi **business state** với Awaitility, không assert `SELECT` ngay lập tức nếu asynchronous.

### 12.2. “Listener được gọi” không có nghĩa DB đã commit

Nếu bạn `@SpyBean` listener rồi `verify(listener).on(...)`, verify có thể quan sát method trước khi JDBC transaction commit hoặc ở mock/proxy khác. Bài dùng audit callback **sau `processOnce` return** và kiểm `processed_message`/`order_points` sau await. Dù vậy, để thực sự kiểm offset đã commit phải thêm một consumer group/consumer admin offset inspection riêng; bài **không** claim kiểm được mốc ấy.

### 12.3. `@Transactional` trên JUnit test không rollback Kafka consumer thread

`@KafkaListener` chạy trên thread của listener container, không phải test caller thread. Test-managed transaction có Spring `ThreadLocal` state ở test thread. Việc đặt:

~~~java
@SpringBootTest
@Transactional
class MessageIntegrationTest {
    @Test
    void test() {
        // Send Kafka record; listener viết DB trên thread khác.
    }
}
~~~

**Snippet minh họa**, không thuộc runnable project. Giao dịch test có thể rollback DML của chính test thread nhưng **không tự rollback insert/update do listener thread commit**. Bởi vậy project không đặt `@Transactional` lên JUnit test class, dùng unique order IDs và `@Transactional` trên **business inbox service**.

### 12.4. Kafka idempotent producer không chống gửi hai lần từ app

Bật `enable.idempotence=true` giảm duplicates ở mức producer protocol retries, **không** gộp hai calls `send(e)` khác nhau. Test `sameMessageIdAtTwoOffsetsIsStillOneBusinessEvent` chứng minh hai records khác offsets nhưng business effect vẫn một lần. Dữ liệu inbox xử lý duplicates theo application message ID.

## 13. Những failure/retry cases phải phân loại đúng

| Tình huống | Consumer nên làm | Tại sao |
|---|---|---|
| Cùng `messageId`, cùng orderId/points, đã commit | No-op, return bình thường, có thể ACK/commit offset | Duplicate hợp lệ |
| `messageId` mới, business order tồn tại | Transactional INSERT receipt + UPDATE points | Event mới hợp lệ |
| `messageId` mới, orderId không tồn tại | Rollback; retry ngắn nếu phụ thuộc thứ tự, nếu vĩnh viễn thì DLT/alert | Không lưu receipt giả |
| Cùng `messageId` nhưng payload khác | Throw/log masked collision; DLT/alert | Không được im lặng coi là retry |
| DB connection timeout | Retry/backoff có kiểm soát | Transient failure; không ACK như thành công |
| DB unique constraint unrelated to inbox | Không nuốt mọi `DataIntegrityViolationException` | Có thể là bug hoặc invalid data |
| JSON deserialization fail trước listener | ErrorHandlingDeserializer/DLT recovery tương ứng | `@KafkaListener` có thể chưa chạy |
| Consumer crash sau DB commit trước offset commit | Redelivery → inbox detect duplicate, no-op | At-least-once recovery |
| Kafka schema incompatible | Contract tests, versioning/DLT | Data poison message |
| External email sent rồi DB transaction rollback | Downstream idempotency/outbox | Không có atomic DB-email transaction |

**Không catch `Exception` rồi return để “tránh retry”**: như vậy một DB failure có thể bị ghi nhận là đã xử lý dù business effect chưa commit. Cũng không bao giờ gửi tất cả exceptions vào vô hạn retries không backoff; một poison record có thể chặn partition và làm consumer lag tăng mãi.

### 13.1. Cấu hình retry/DLT production (định hướng)

Với Spring Kafka, các lựa chọn gồm:
- `DefaultErrorHandler` với `FixedBackOff`/exponential backoff phù hợp.
- `DeadLetterPublishingRecoverer` để gửi record không xử lý được sang dead-letter topic.
- `ErrorHandlingDeserializer` để chặn lỗi deserialize và định tuyến được những invalid bytes.
- `@RetryableTopic` cho non-blocking retries nếu phù hợp version topology/ordering requirements.
- Micrometer metrics để theo dõi failures, retries, duplicate rate, consumer lag và DLT occupancy.

**Chú ý:** Đây là hướng mở rộng, không có một DLT broker/topic pipeline nào được khai báo trong project runnable. Vì vậy test `sameIdWithDifferentPayloadIsRecognizedAsCollision` kiểm phát hiện collision trực tiếp ở service, **không** gửi poison record thật rồi chờ DLT chưa có. Khi tự xây DLT integration test, phải tạo topic `orders.created.v1.DLT` hoặc cấu hình routing và kiểm consumer offsets/errors thực, tránh viết test chắc chắn timeout.

### 13.2. Một minh họa về error handler

~~~java
// Snippet định hướng cho context đã có KafkaTemplate/ConsumerFactory phù hợp.
// Chưa là cấu hình chạy độc lập; cần khai DLT topics và policy.
DefaultErrorHandler handler =
        new DefaultErrorHandler(
                (record, exception) -> {
                    // Route to DLT / metrics / alert, theo policy.
                },
                new FixedBackOff(1000L, 2L));
~~~

Với đoạn minh họa, `FixedBackOff(1000,2)` cho khoảng cách retries 1 giây, hai retry attempts **theo cấu hình BackOff handler**, không cam kết giao được DLT nếu `(record,exception)` lambda chỉ comment. Trong project thật nên dùng `DeadLetterPublishingRecoverer` gắn với KafkaTemplate và broker topics thật; không đánh đồng Java lambda logging với DLT integration.

**Không đưa snippet này vào Gradle project chính** nếu chưa thêm imports `org.springframework.kafka.listener.DefaultErrorHandler`, `org.springframework.util.backoff.FixedBackOff` và cấu hình handler bean. Nó chỉ là minh họa để định hướng mở rộng.

## 14. Những trường hợp xử lý trùng mà test thường bỏ sót

### 14.1. Duplicate xuyên hai consumer instances

Một `ConcurrentHashMap.newKeySet()` trong JVM chỉ nhớ message IDs ở đúng process; restart hoặc scale replicas thì mất. Unique constraint trong DB giúp **các consumer cùng chia sẻ database** cạnh tranh trên cùng `messageId`: chỉ một transaction insert được unique key; transaction thua phải rollback trước khi làm business effect.

H2 embedded broker test ở một JVM **không phải chứng minh đầy đủ** concurrency của PostgreSQL multi-instance. Khi triển khai thật:
- Dùng PostgreSQL unique index `(consumer_name,message_id)`.
- Chạy hai consumers hoặc integration test instances cùng DB.
- Tạo hai deliveries đồng thời và assert một business effect.
- Kiểm rollback của bên thua và error translation.
- Không bỏ unique constraint chỉ vì application có `if(!processed)` check.

### 14.2. Trùng cùng orderId nhưng event ID mới

Trong bài, **hai `messageId` khác nhau** cùng `orderId` được cộng cả hai lần. Đó là behavior đúng nếu mỗi ID là một business event độc lập. Nếu nghiệp vụ thực cho phép chỉ **một** thưởng cho mỗi đơn, phải dùng unique business key như `(order_id,reward_type)` và một contract khác; không thể giải bằng việc lấy orderId làm Kafka key hoặc messageId tùy tiện.

### 14.3. Cùng ID nhưng payload bị đổi

Khi một producer retry, event ID và **payload không được thay**. Nếu cùng ID xuất hiện với khác `points`, listener không được silently no-op: có thể là lỗi upstream tái sử dụng ID cho sự kiện mới, bug serialization hoặc hành vi gian lận. `matchesStoredReceipt` trong ví dụ trả false; listener ném lỗi để tuyến DLT/alert quyết định.

Một hệ production nên log **messageId fingerprint** và an toàn dữ liệu, không in toàn bộ JSON chứa PII/secrets. Có thể lưu schema version/tenant ID/event type/payload checksum trong inbox để detect collision mạnh hơn.

### 14.4. TTL/cleanup của inbox

Nếu tự xóa receipt sau 7 ngày nhưng Kafka có thể redeliver event 30 ngày sau, message cũ sẽ được xử lý như mới. Chọn retention dựa vào:
- Kafka topic retention, offset replay/recovery requirements.
- Khoảng retry/DLT replay tối đa.
- Nghĩa vụ tài chính/kiểm toán.
- Khả năng dữ liệu được tái đồng bộ sau disaster recovery.
- Chế độ xoá PII/consent phù hợp.

Không tự động `DELETE WHERE processed_at < NOW()-7D` mà không có policy. Bài giữ receipts suốt test JVM, không giới thiệu TTL không căn cứ.

### 14.5. Exactly-once Kafka transactions không bao trùm JDBC mặc định

Kafka transactions/Exactly-once semantics trong Kafka có thể phối hợp topic outputs và consumer offsets trong phạm vi Kafka, nhưng JDBC DB là resource khác. Ngay cả khi Kafka transaction thành công, không có XA/global transaction tự nhiên đảm bảo email, PostgreSQL và Kafka atomic tuyệt đối. Chọn inbox/outbox, idempotency keys, compensation phù hợp SLA nghiệp vụ.

### 14.6. Thiết kế producer outbox để tránh mất event

Project có `OrderEventPublisher.publish` được gọi trực tiếp bởi test. Trong app production nếu business DB commit rồi producer send fail, event có thể mất; nếu producer send trước DB commit, consumer có thể nhận event trước khi order row được tạo.

**Transactional outbox pattern:**
1. Trong cùng business DB transaction, INSERT/UPDATE order và INSERT outbox record.
2. Worker/CDC đọc outbox và publish Kafka.
3. Retry send được phép; giữ nguyên `messageId`.
4. Consumer dùng inbox unique key để bỏ duplicates.
5. Theo dõi outbox backlog, poison event/DLT, cleanup và schema version.

Outbox không xuất hiện trong runnable code vì cần một cơ chế dispatch/CDC riêng; đừng nhầm publisher demo là fully reliable production outbox.

## 15. Dấu hiệu test flaky và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `TimeoutException` khi `future.get` | Broker chưa start, metadata unreachable, network/port | Kiểm `@EmbeddedKafka`, bootstrap servers và logs |
| Send ACK nhưng DB vẫn 0 | Listener chưa subscribe/assign, deserialize fail, service error | Chờ Awaitility; xem Kafka listener logs |
| `No message received` | Consumer group, topic, JSON deserializer, offset reset | Kiểm topic constant và `@EnableKafka` |
| `ClassNotFoundException` khi deserialize | JSON type header từ producer khác package | Cấu hình trusted packages/default type/type mapping |
| `SerializationException`/JSON errors | Payload/record contract không hợp | ErrorHandlingDeserializer + schema contract |
| H2 table not found | `schema.sql` sai classpath hoặc SQL init disabled | Đặt `src/test/resources/schema.sql`, `spring.sql.init.mode=always` |
| Receipt có nhưng points chưa tăng | Ghi receipt và update không cùng tx/exception bị nuốt | Đảm bảo service `@Transactional`, insert-first + rollback |
| Duplicate vẫn cộng điểm hai lần | Khóa theo offset/orderId sai, thiếu UNIQUE index | Dùng business messageId + DB unique |
| Test fail ngẫu nhiên do `Thread.sleep` | Listener asynchronous | Await condition với timeout hữu hạn |
| `DuplicateKeyException` bắn ra khi event trùng | Listener không catch đúng sau rollback hoặc thiếu payload compare | Bắt đúng loại lỗi, no-op nếu cùng payload |
| DB deadlock/transaction aborted | Concurrency hoặc catch bên trong transaction lỗi | Rollback rồi xử lý duplicate ở boundary |
| `@Transactional` test không rollback listener DB | Listener chạy thread khác | Fixture IDs riêng/cleanup ngoài transaction |
| Tests tác động nhau | Truncate shared tables khi listener còn làm việc | Không truncate trước mỗi test, UUID IDs riêng |
| Consumer group đọc events cũ | Broker/topic được tái dùng, offsets/state shared | Group/topic riêng, bootstrap lifecycle rõ |
| `@DirtiesContext` tăng runtime | Khởi động broker/context lại mỗi method | Dirties AFTER_CLASS nếu cần, không AFTER_METHOD đại trà |
| CI nhiều Gradle JVMs chạm một DB | Lock/cache chỉ trong JVM | Test schemas/containers riêng |
| Producer idempotence bật mà vẫn có hai records | Hai lời gọi send chủ động tạo hai sequence | Consumer inbox dedup theo messageId |
| DLT không có record như kỳ vọng | Chưa cấu hình recoverer/topic | Cấu hình DLT thật, test lỗi với retry bound |
| Retry không dừng | Poison event có lỗi không thể phục hồi | Phân loại fatal/non-retryable và DLT |
| `offset` khác nhau nhưng một effect | Đúng hành vi của semantic dedup | Không assert Kafka dedup theo messageId |
| Metrics audit tăng vô hạn | Demo ConcurrentHashMap không có TTL | Đổi sang metrics bounded/observation |
| Sau process restart bị cộng lại | Inbox chỉ in-memory hoặc đã bị dọn sớm | Durable SQL inbox + retention phù hợp |
| Trùng ID nhưng payload khác bị bỏ qua | Không so receipt payload | Hash/contract compare và alert |
| Test chỉ mock KafkaTemplate | Không kiểm serializer/broker/listener thật | Dùng @EmbeddedKafka hoặc Testcontainers |
| Embedded broker không chạy trong sandbox | Local ports/FS bị hạn chế | Dùng container/CI infra được phép |

### 15.1. Debug một ca thực tế

1. Xem producer send future: success hay `ExecutionException`?
2. Kiểm topic/partition/offset có đúng expected không?
3. Kiểm `spring.kafka.bootstrap-servers` trỏ embedded broker chứ không phải localhost:9092.
4. Kiểm `@KafkaListener` đã được đăng ký, partition assigned, consumer group đúng.
5. Nếu listener không chạy, kiểm JSON deserializer (trusted packages/default type).
6. Nếu listener chạy nhưng DB chưa đổi, xem transaction exception chain/constraint.
7. Nếu duplicate, kiểm `messageId` có giữ nguyên trong cả hai sends không.
8. Kiểm receipt uniqueness ở DB, đừng chỉ dựa in-memory Set.
9. Kiểm event mới cùng order có ID khác để không false-dedup.
10. Kiểm trong test có await **sau** send ACK không, không chỉ sleep.
11. Nếu CI parallel, tách broker topics/group IDs/DB schemas theo worker.
12. Không xem `SendResult` là bằng chứng committed consumer offset.
13. Nếu thiếu order, xử lý lỗi theo retry/dead-letter policy; đừng ACK rồi mất event.
14. Nếu payload conflict, kiểm upstream ID generation và contract, không silently ignore.

## 16. Mở rộng: kiểm retry, DLT, rebalance, real brokers

### 16.1. `@EmbeddedKafka` vs Testcontainers

| Yêu cầu | `@EmbeddedKafka` | Kafka Testcontainers |
|---|---|---|
| Không yêu cầu Docker | **Có** | Thường **không** |
| Kiểm `KafkaTemplate`/`@KafkaListener` async | **Có** | **Có** |
| Gần môi trường broker production hơn | Giới hạn | Tốt hơn khi cùng broker/version/config |
| Chạy với SASL/TLS/custom network | Hạn chế | Dễ mô phỏng hơn với cấu hình container |
| Kiểm restart/network failure | Cần fixture phức tạp | Có thể stop/start container và dùng Toxiproxy |
| Test DB thật PostgreSQL | Không liên quan | Dùng thêm PostgreSQL container |
| CI cần local port/resource | Có | Có + Docker daemon |
| Startup time/resources | Thường gọn cho demo | Phụ thuộc container pull/start |

**Ví dụ chuyển sang Testcontainers** không được viết như một dòng import duy nhất: cần thêm `spring-boot-testcontainers`, `org.testcontainers:kafka`, JUnit container lifecycle, `@ServiceConnection` hoặc `@DynamicPropertySource`, Docker readiness và topic provisioning. Không copy `@EmbeddedKafka` và Kafka container cùng chạy song song trên một `spring.kafka.bootstrap-servers` mà không xác định rõ cái nào dùng.

### 16.2. Redelivery sau crash thật sự

Một integration test nâng cao cần:
1. Dùng broker/test DB có lifecycle chủ động.
2. Gửi event A rồi cho listener commit DB effect.
3. Cố ý ngắt consumer **trước khi commit offset** hoặc reset offset/replay có kiểm soát.
4. Start consumer lại cùng group/partition và quan sát record A được giao lại.
5. Assert inbox count 1, order points chỉ một lần tăng.
6. Phân biệt test replay (chủ động seek offset) với crash window đúng nghĩa.
7. Kiểm consumer logs/offset commit và DB commit thực, không chỉ audit count.

Bài hiện tại test **semantic duplicates do gửi nhiều lần**, không claim đã mô phỏng crash/rebalance. Đây là giới hạn được phát biểu chủ động để tránh kết luận sai về reliability.

### 16.3. Schema compatibility

Producer và consumer đều biết `OrderCreatedEvent` record. Trong hệ nhiều teams:
- Viết contract tests với JSON Schema, Avro Schema Registry hoặc Protobuf descriptors.
- Dùng explicit `eventType`, `schemaVersion`, `messageId`, `occurredAt`.
- Thử thêm optional fields và kiểm consumers cũ còn parse được.
- Thử đổi type/rename/remove required fields và xác định breaking changes.
- Không để Java-specific class names là giao thức liên đội dài hạn.
- Quản lý idempotency key theo event type/version/consumer scope, không chỉ JSON hash.
- Test lỗi deserialization bằng raw bytes và DLT policy **trong một test suite riêng có cấu hình error handler**.

### 16.4. Test invalid payload và poison flow

Với malformed JSON, Kafka `JsonDeserializer` có thể throw **trước khi vào listener**. Nếu muốn assert DLT, cấu hình `ErrorHandlingDeserializer` làm delegate và `DefaultErrorHandler`/`DeadLetterPublishingRecoverer` theo API version. Test raw Kafka `ProducerRecord<byte[],byte[]>`, gửi invalid bytes và chờ DLT message. **Không** mong `@KafkaListener(OrderCreatedEvent e)` bắt được byte stream sai type rồi return thành công.

Các tình huống nên có ở hệ production:
- Missing `messageId` hoặc blank `orderId`.
- Unknown `schemaVersion`.
- `points` âm, overflow lớn hoặc business rule trái phép.
- Same ID different payload.
- DB down/transient network error và bounded retry.
- DLT publish failed.
- Retry backlog/consumer lag.
- Out-of-order event, rebalance trong lúc DB commit.
- Một batch chứa valid+poison record.

## 17. Bài tập thực hành

**Bài 1 — Broker ACK vs consumer:** Bỏ `awaitObserved` khỏi test đầu rồi assert DB ngay sau `send().get()`. Tại sao test có thể flaky dù producer đúng?

**Bài 2 — Kafka offsets:** Dùng cùng `messageId` hai lần; kiểm hai `RecordMetadata.offset()` khác nhau. Vì sao consumer phải dedup theo semantic ID?

**Bài 3 — Duplicate ba lần:** Gửi cùng event ba lần, quan sát `audit.duplicateCount` và DB. Nêu invariant chính xác.

**Bài 4 — Hai events hợp lệ cùng order:** Đổi test thành gửi `eventId` mới cho cùng order, tổng điểm phải bằng bao nhiêu? Vì sao dùng `orderId` làm inbox PK là sai trong nghiệp vụ này?

**Bài 5 — Race condition:** Thay insert-first bằng `SELECT exists → UPDATE → INSERT`, chạy song song hai consumer instances và tìm double effect. Vì sao database unique constraint + transaction là guardrail bền hơn?

**Bài 6 — DB rollback:** Gửi event cho order không tồn tại **trực tiếp vào service**, kiểm receipt không tồn tại sau exception. Vì sao ghi receipt trước UPDATE nhưng khác transaction sẽ nguy hiểm?

**Bài 7 — Payload conflict:** Cùng messageId, thay points từ 6 thành 999. Vì sao không nên silently no-op? Thiết kế DLT/alert policy.

**Bài 8 — Producer idempotence:** Giữ `enable.idempotence=true`, gửi cùng event hai lần từ app. Vì sao broker vẫn có hai offsets?

**Bài 9 — `@Transactional` test:** Đánh dấu JUnit method `@Transactional` rồi cho listener ghi DB. Vì sao rollback của test thread không xóa business effect của listener?

**Bài 10 — H2 vs PostgreSQL:** Chạy lại test duplicate insert dưới PostgreSQL Testcontainers. So error translation, unique constraint và rollback semantics.

**Bài 11 — ErrorHandlingDeserializer:** Gửi raw bytes malformed JSON và định tuyến vào DLT có recoverer thật, kiểm không có inbox row.

**Bài 12 — Retry/backoff:** Cố ý cho DB unavailable trong một lần, sau đó hồi phục. Chứng minh bounded retries và một business effect.

**Bài 13 — Consumer crash window:** Thực hiện replay có chủ đích sau khi DB commit nhưng trước offset commit; đo consumer offsets và database.

**Bài 14 — Outbox:** Trong cùng DB transaction lưu Order và outbox; worker publish Kafka. Gửi lại outbox record và kiểm inbox dedup.

**Bài 15 — Ordering:** Gửi hai events cùng orderId, cùng Kafka key, nhưng ID khác. Kiểm thứ tự trong một partition; thử nhiều partitions và giải thích giới hạn ordering.

**Bài 16 — Schema evolution:** Thêm optional field `source` vào event JSON, thử consumer cũ còn parse. Sau đó đổi `points` từ int sang string và đánh giá breaking change.

**Bài 17 — Concurrent instances:** Cho hai consumers dùng cùng DB/schema và group khác nhau (nên cả hai đều nhận same record). Chứng minh unique inbox chỉ một effect dù cả hai thấy message.

**Bài 18 — Retention:** Xóa inbox receipt sau thời gian ngắn rồi replay event. Phân tích double effect và đề xuất retention theo business requirements.

**Bài 19 — Observability:** Thêm counters cho received, applied, duplicate, failed, DLT và consumer lag; không lưu message IDs vĩnh viễn trong memory.

**Bài 20 — CI isolation:** Chạy nhiều Gradle forks với embedded brokers hoặc Testcontainers. Thiết kế topic/group/DB schema namespace riêng, tránh dùng @DirtiesContext toàn suite.

## 18. Checklist review trước khi đưa tests vào CI

- [ ] Producer send kiểm future/metadata; không suy business effect từ ACK.
- [ ] Consumer là `@KafkaListener` thật được bật, không chỉ Mockito mock.
- [ ] `@EmbeddedKafka` map đúng bootstrap servers của Spring Boot.
- [ ] Topics được provision và consumer group được định nghĩa rõ.
- [ ] JSON serializer/deserializer dùng contract đúng type và trusted packages.
- [ ] Business messageId là ID semantic, ổn định qua retries.
- [ ] Kafka key được chọn theo business ordering needs, không nhầm idempotency key.
- [ ] Inbox có `PRIMARY KEY`/unique key ở DB.
- [ ] Receipt insert và business mutation chạy **cùng transaction**.
- [ ] Duplicate caught **sau rollback**, chỉ đúng duplicate key case.
- [ ] Cùng ID nhưng payload khác được phát hiện và xử lý như lỗi.
- [ ] DB unavailable/unknown order không bị catch-all rồi ACK như thành công.
- [ ] Listener success audit nằm sau DB commit, tests chờ asynchronous completion.
- [ ] Tests dùng unique order/message IDs, không truncate shared tables trong lúc listener chạy.
- [ ] `@Transactional` trên test thread không được hiểu là rollback listener thread.
- [ ] Retry/backoff/DLT/poison payload đã có test riêng khi triển khai production.
- [ ] Không nhầm producer idempotence với consumer business idempotence.
- [ ] Không khẳng định exactly-once end-to-end ngoài phạm vi DB inbox.
- [ ] Nếu dùng PostgreSQL/real Kafka, có integration suite tương ứng.
- [ ] Không claim tests đã chạy nếu chỉ mới trình bày source và expected behavior.

## 19. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Apache Kafka Support](https://docs.spring.io/spring-boot/3.3/reference/messaging/kafka.html): KafkaTemplate, KafkaListener, properties và testing embedded broker.
- [Spring Kafka 3.2 — Testing Applications](https://docs.spring.io/spring-kafka/reference/3.2/testing.html): `@EmbeddedKafka`, `bootstrapServersProperty`, JUnit integration và broker lifecycle.
- [Spring Kafka 3.2 — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/3.2/kafka/receiving-messages/message-listener-container.html): AckMode.RECORD/BATCH/MANUAL và offset commit.
- [Spring Kafka 3.2 — Serialization/Deserialization](https://docs.spring.io/spring-kafka/reference/3.2/kafka/serdes.html): JsonSerializer, JsonDeserializer, trusted packages và type metadata.
- [Spring Kafka 3.2 — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/3.2/kafka/annotation-error-handling.html): DefaultErrorHandler, DeadLetterPublishingRecoverer, retries và DLT.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): Kafka transaction scope và giới hạn.
- [Spring Boot 3.3 — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): schema.sql, H2, spring.sql.init.mode.
- [Spring Framework — Transaction Declarative Annotations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): @Transactional và transaction proxy boundaries.
- [Spring Framework — Test-Managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): ThreadLocal test transactions.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html): SpringBootTest, JUnit Jupiter và starter-test.
- [Awaitility — Documentation](https://github.com/awaitility/awaitility/wiki/Usage): bounded asynchronous assertions.
- [Apache Kafka — Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-least-once, producer retries, offsets và transactions.
- [Testcontainers — Apache Kafka module](https://java.testcontainers.org/modules/kafka/): real broker integration suite.
- [Testcontainers — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): real SQL isolation/transaction validation.

**Kết luận:** Một test gửi thông điệp tốt phải kiểm **broker ACK**, **listener receive**, **DB transaction commit** và **business invariant**, không trộn bốn mốc thành một assertion. Khi at-least-once delivery gây trùng, dùng **business `messageId` ổn định**, unique inbox constraint và transaction gộp INSERT receipt + UPDATE state; gửi lại cùng ID hai/ba lần vẫn chỉ có **một business effect**. Đồng thời phải nhận diện cùng ID khác payload, không nuốt lỗi ngoài duplicate, và có kế hoạch retries/DLT/outbox khi ra production. `@EmbeddedKafka` và Awaitility cho phép kiểm hành trình thật một cách tái lập; H2/embedded broker là điểm khởi đầu, không thay thế kiểm chứng trên hạ tầng thực.
