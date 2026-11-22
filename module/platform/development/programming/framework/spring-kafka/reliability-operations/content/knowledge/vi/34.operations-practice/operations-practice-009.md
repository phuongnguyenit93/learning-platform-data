# Mô phỏng producer fencing trong Spring Kafka — thực hành vận hành và khôi phục

## 1. Bối cảnh: hai producer tưởng mình cùng sở hữu một giao dịch

Một hệ thống Spring Kafka xuất bản sự kiện sau khi xử lý đơn hàng. Ứng dụng chạy hai replicas:

```text
             Kafka cluster
                  |
         Transaction coordinator
                  |
        transactional.id = orders-tx-0
                /       \
               /         \
              v           v
          Replica A    Replica B
          Producer A   Producer B
          (old epoch)  (new epoch)
```

Replica A đang xử lý một transaction nhưng bị treo hoặc mất kết nối. Replica B khởi động và lấy **cùng `transactional.id`**. Kafka coordinator cấp một thế hệ producer mới và **fence** thế hệ cũ. Khi A cố tiếp tục transaction, broker từ chối hoạt động của A để ngăn hai producers khác nhau cùng ghi một luồng transactional state.

Điều này chính là **producer fencing**. Nó vừa là cơ chế bảo vệ tính đúng đắn của Kafka transactions, vừa là tín hiệu vận hành cần hiểu:

- **Fencing đúng mong đợi:** một process mới thay thế producer cũ, producer cũ phải dừng.
- **Fencing không mong muốn:** hai replicas đang hoạt động cùng dùng transactional ID, khiến chúng liên tục giành quyền sở hữu và lỗi.
- **Fencing do lỗi triển khai:** transaction prefix bị copy nguyên xi qua mọi pod, cache transactional producer tái sử dụng sai, hoặc code không đóng producer đã bị fence.
- **Fencing trong sự cố chập chờn:** một worker bị pause lâu, process mới nhận ownership; khi worker cũ tỉnh lại, nó không được phép commit transaction đã mất quyền.

Bài thực hành này thuộc **Spring Kafka Reliability Operations → Thực hành vận hành → Mô phỏng producer fencing**. Mục đích không chỉ là khiến test ném `ProducerFencedException`, mà còn biết **vì sao nó xảy ra, Kafka bảo vệ điều gì, dữ liệu nào được nhìn thấy và khi nào phải dừng/restart ứng dụng**.

Chúng ta sẽ dùng **Java 17+, Spring Boot 3.x, Spring Kafka 3.x, Apache Kafka client 3.x, JUnit 5 và Embedded Kafka**. Có thêm phương án **Testcontainers** để gần môi trường deploy hơn. Nếu dự án đã dùng Spring Boot 4/Spring Kafka 4, giữ nguyên mô hình fencing nhưng điều chỉnh test dependencies, Kafka client APIs và embedded broker theo version tương ứng.

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt `transactional.id`, `producerId`, `producer epoch` và `client.id`.
2. Dựng một Kafka broker phục vụ integration test của transactional producer.
3. Tạo **hai KafkaProducer với cùng transactional ID** để tái hiện producer fencing.
4. Assert producer cũ không thể commit, producer mới commit được và `read_committed` chỉ đọc record hợp lệ.
5. Phân biệt fencing với transaction timeout, rebalance/static-membership fencing và lỗi quyền truy cập.
6. Hiểu tác động của `spring.kafka.producer.transaction-id-prefix` trong các replicas Spring Boot.
7. Thiết kế cách phục hồi không retry mù trên producer đã bị fence.
8. Viết regression tests, metrics, alerting và runbook cho production.

---

## 2. Nền tảng: Kafka producer có hai lớp identity

### 2.1. `client.id` không phải transactional identity

Một producer có thể khai báo:

```properties
client.id=orders-producer-node-A
```

`client.id` giúp broker logs, metrics và monitoring gắn tên client. Nó **không** quyết định một producer có quyền tiếp tục một Kafka transaction hay không.

Hai producers có `client.id` giống nhau không tự động bị fence; tuy nhiên chúng sẽ khó phân biệt trong log/metrics.

### 2.2. `transactional.id` đại diện cho chủ sở hữu logic của transactional producer

Kafka transactional producer đặt:

```properties
transactional.id=orders-publisher-slot-0
```

ID này cho phép Kafka coordinator liên hệ các phiên producer qua lần khởi động lại và **fence producer thế hệ cũ**. Kafka bảo đảm tại một thời điểm một transactional identity không được có hai producer epochs cùng có quyền thao tác như chủ sở hữu hiện hành.

**Không dùng chung transactional ID cho hai producers có chủ quyền độc lập và cần hoạt động đồng thời.**

### 2.3. `producerId` và `producer epoch`

Kafka broker/coordinator quản lý producer ID và epoch. Có thể hình dung:

```text
Trạng thái đầu:
  transactional.id = orders-publisher-slot-0
  producerId       = P
  producerEpoch    = 7
  Producer A được phép ghi transactional records

Producer B initTransactions() với cùng transactional.id:
  transactional.id = orders-publisher-slot-0
  producerId       = P (minh họa)
  producerEpoch    = 8
  Producer B trở thành chủ sở hữu mới

Producer A:
  producerEpoch    = 7
  cố commit/send -> bị từ chối vì epoch cũ
```

Dãy số và việc ID có được tái sử dụng là minh họa. **Không dựa vào producerId tăng/không tăng để xác định fencing**; Kafka có logic quản lý epoch/producer identity phù hợp với phiên bản, và hành vi API báo lỗi mới là tín hiệu cần test.

### 2.4. So sánh bốn khái niệm

| Khái niệm | Nơi được dùng | Có quyết định fencing transactional producer? |
| --- | --- | --- |
| `client.id` | Logs/metrics/client diagnostics | Không |
| `transactional.id` | Kafka transaction coordinator | Có |
| `producerId` | Broker/client protocol state | Tham gia |
| `producer epoch` | Fencing producer thế hệ cũ | Có |
| `group.id` | Consumer group offset/assignment | Không phải transactional producer identity |
| `group.instance.id` | Static membership của consumer | Có thể tạo loại **consumer fencing** khác |

Đừng nhầm `ProducerFencedException` với `FencedInstanceIdException` của consumer static group membership. Chúng đều chứa chữ *fenced* nhưng thuộc cơ chế khác nhau.

---

## 3. Vì sao Kafka phải fencing?

Giả sử producer A đang thực hiện transaction:

```text
A: beginTransaction()
A: send(order-100, "CREATED")
A: send(order-101, "CREATED")

[Ứng dụng A mất liên lạc]
[Orchestrator khởi động B để tiếp tục công việc]

B: initTransactions() cùng transactional.id
B: beginTransaction()
B: send(order-102, "CREATED")
B: commitTransaction()

[A tỉnh lại]
A: commitTransaction()   <-- không được chấp nhận
```

Nếu cả A và B có thể commit theo cùng identity mà không có epoch fencing, một worker lỗi thời có thể công bố dữ liệu sau khi quyền xử lý đã chuyển sang worker khác. Điều đó làm hỏng quy tắc ownership và recovery của Kafka transactions.

Kafka dùng transaction coordinator để quản lý generations và ngăn zombie producer tiếp tục. Cơ chế này **không ngăn mọi business duplicate trong mọi kiến trúc**; ví dụ hai transactional IDs **khác nhau** vẫn có thể gửi cùng một business event hai lần nếu ứng dụng logic bị trùng.

### 3.1. “Zombie” producer nghĩa là gì?

Zombie producer là một producer **vẫn còn thực thi ở đâu đó** nhưng **không còn là chủ sở hữu hợp lệ** của transactional identity. Nó có thể xuất hiện khi:

- Process bị stop-the-world pause/GC quá lâu.
- Worker bị ngắt mạng rồi kết nối lại.
- Container bị orchestrator thay thế nhưng bản cũ chưa dừng hoàn toàn.
- Hai replicas được cấu hình sai cùng transactional ID.
- Một scheduled task được chuyển sang node mới trong khi node cũ chưa release resources.

Kafka fencing ép zombie producer thất bại thay vì commit như không có chuyện gì.

### 3.2. Fencing là lỗi nghiêm trọng đối với producer instance cũ

Sau `ProducerFencedException`, producer cũ phải được xem là **không còn dùng được**. Không nên bắt exception rồi gọi lại `send` hoặc `commitTransaction` vô hạn trên cùng `KafkaProducer`.

Cách xử lý đúng thường là đóng producer bị fence, dừng công việc đã mất ownership, ghi lại diagnostic context, để coordinator/orchestrator hoặc service owner có thẩm quyền quyết định tạo producer mới và phục hồi an toàn.

---

## 4. Mục tiêu thực hành và kết quả kỳ vọng

Ta sẽ xây một integration test có hai producers:

```text
Kafka Embedded Broker
  topic: fencing.same-id.it, 1 partition

Producer A:
  transactional.id = fencing-it-slot-1
  initTransactions()
  beginTransaction()
  send(A_UNCOMMITTED) -> broker append trong transaction A

Producer B:
  transactional.id = fencing-it-slot-1  [TRÙNG A]
  initTransactions() -> Kafka thay epoch / fence A
  beginTransaction()
  send(B_COMMITTED)
  commitTransaction() -> OK

Producer A:
  commitTransaction() -> ProducerFencedException

Consumer:
  isolation.level = read_committed
  seek earliest
  đọc B_COMMITTED
  KHÔNG đọc A_UNCOMMITTED đã bị abort

Kết quả:
  A không được commit
  B trở thành producer hiện hành
  Consumer không thấy transaction bị bỏ dở của A
```

Ngoài kịch bản chính, chúng ta cần một **negative control**:

- Producer A và B có transactional IDs **khác nhau**.
- Cả hai có thể commit.
- Consumer `read_committed` thấy cả hai records.

Như vậy test không chỉ chứng minh Kafka có lỗi; nó còn chứng minh **điều kiện gây lỗi chính là tranh chấp cùng transactional ID**.

---

## 5. Hai nguyên tắc khi dựng broker thử nghiệm

### 5.1. Một broker là đủ để mô phỏng fencing

Producer fencing do transaction coordinator và producer epoch quyết định. Test có thể dùng một Kafka broker với internal transaction state topic phù hợp.

Đối với **single broker**, phải giảm replication/ISR của internal transaction state topic:

```properties
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
offsets.topic.replication.factor=1
```

Nếu quên, `initTransactions()` có thể timeout vì broker mặc định yêu cầu replication factor không đáp ứng được trong test một node. Đó là **lỗi setup test**, không phải bằng chứng producer fencing.

### 5.2. Single-broker không chứng minh production resilience

Test này kiểm tra **fencing logic và transaction visibility**, không kiểm tra leader failover, ISR durability hoặc khả năng transaction coordinator sống sót khi nhiều brokers thay nhau mất kết nối. Những nội dung đó cần cluster nhiều brokers hay preproduction environment.

---

## 6. Cấu hình dự án Spring Boot + Kafka test

### 6.1. Cấu trúc

```text
kafka-fencing-lab/
├── settings.gradle
├── build.gradle
└── src/
    └── test/
        └── java/com/example/fencing/
            ├── ProducerFencingIT.java
            ├── DistinctIdIT.java
            └── SpringTransactionalPublisherIT.java
```

Để tái hiện bằng raw Kafka clients, không cần một ứng dụng business hoàn chỉnh. Tuy nhiên project Spring Boot hữu ích nếu muốn mở rộng sang `KafkaTemplate`/`KafkaTransactionManager`.

### 6.2. `build.gradle` cho Spring Boot 3.x

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
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'

    // Tùy chọn nếu chạy thêm Kafka qua Docker.
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`settings.gradle`:

```groovy
rootProject.name = 'kafka-fencing-lab'
```

**Vì sao không khai báo version riêng cho `kafka-clients`?** Spring Boot BOM quản lý phiên bản client tương thích với Spring Kafka. Nếu project đã sử dụng dependency khác làm override, xem dependency tree và release matrix trước khi chạy test.

### 6.3. Chọn dependency theo Boot release

Ví dụ trên hướng tới **Boot 3.x / Spring Kafka 3.x**. Với **Boot 4.x / Spring Kafka 4.x**, dự án có thể dùng các starter Kafka/test được modularize:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-kafka'
testImplementation 'org.springframework.boot:spring-boot-starter-kafka-test'
```

Khi đó dùng đúng Embedded Kafka KRaft implementation tương ứng, không giữ ZooKeeper-specific test APIs từ phiên bản cũ. Bài này sẽ giữ code mẫu cho Boot 3.x để người học theo một baseline nhất quán.

---

## 7. Bài thực hành chính: JUnit tạo hai producer cùng `transactional.id`

Dưới đây là test Java theo hướng **chạy được trong một Spring test context**. Ta dùng `@EmbeddedKafka` để cung cấp broker, nhưng chủ động tạo hai `KafkaProducer` của Apache Kafka để kiểm soát **chính xác** giá trị `transactional.id`, thay vì phụ thuộc vào suffix/cache của Spring `DefaultKafkaProducerFactory`.

### 7.1. Test đầy đủ

Tạo `src/test/java/com/example/fencing/ProducerFencingIT.java`:

```java
package com.example.fencing;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.errors.ProducerFencedException;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(ProducerFencingIT.TestConfig.class)
@EmbeddedKafka(
    partitions = 1,
    topics = {"fencing.same-id.it", "fencing.distinct-id.it"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers",
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1",
        "offsets.topic.replication.factor=1",
        "auto.create.topics.enable=false"
    }
)
class ProducerFencingIT {

    private static final String SAME_ID_TOPIC =
        "fencing.same-id.it";

    private static final String DIFFERENT_ID_TOPIC =
        "fencing.distinct-id.it";

    @Configuration
    static class TestConfig {
        // Embedded broker do spring-kafka-test đăng ký.
    }

    @Autowired
    EmbeddedKafkaBroker broker;

    private Properties producerProps(
            String transactionalId, String clientId) {

        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            broker.getBrokersAsString());
        props.put(ProducerConfig.CLIENT_ID_CONFIG, clientId);
        props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
            transactionalId);
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.RETRIES_CONFIG, 5);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
        props.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG,
            30_000);
        return props;
    }

    private Properties consumerProps() {
        Properties props = new Properties();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            broker.getBrokersAsString());
        props.put(ConsumerConfig.GROUP_ID_CONFIG,
            "fencing-observer-" + java.util.UUID.randomUUID());
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
            false);
        props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG,
            "read_committed");
        return props;
    }

    private List<String> committedValues(
            String topic, String expectedValue) {

        List<String> values = new ArrayList<>();
        TopicPartition partition =
            new TopicPartition(topic, 0);

        try (KafkaConsumer<String, String> consumer =
                new KafkaConsumer<>(consumerProps())) {

            consumer.assign(List.of(partition));
            consumer.seekToBeginning(List.of(partition));

            long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(15);

            boolean found = false;

            while (System.nanoTime() < deadline && !found) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofMillis(250));

                for (ConsumerRecord<String, String> record
                        : records) {
                    values.add(record.value());
                    if (expectedValue.equals(record.value())) {
                        found = true;
                    }
                }
            }
        }
        return values;
    }

    @Test
    void newerProducerFencesOlderProducerWithSameId()
            throws Exception {

        String transactionalId = "fencing-demo-slot-1";

        try (KafkaProducer<String, String> a =
                 new KafkaProducer<>(
                     producerProps(transactionalId, "producer-A"));
             KafkaProducer<String, String> b =
                 new KafkaProducer<>(
                     producerProps(transactionalId, "producer-B"))) {

            // 1. A lấy ownership và bắt đầu transaction.
            a.initTransactions();
            a.beginTransaction();

            a.send(new ProducerRecord<>(
                SAME_ID_TOPIC, "A", "A_UNCOMMITTED"))
                .get(10, TimeUnit.SECONDS);

            // 2. B khởi tạo với cùng transactional.id.
            //    Coordinator chuyển sang producer epoch mới.
            b.initTransactions();
            b.beginTransaction();

            b.send(new ProducerRecord<>(
                SAME_ID_TOPIC, "B", "B_COMMITTED"))
                .get(10, TimeUnit.SECONDS);

            b.commitTransaction();

            // 3. A không được commit transaction cũ.
            assertThrows(
                ProducerFencedException.class,
                a::commitTransaction);

            // Sau fencing không tiếp tục sử dụng A.
        }

        // 4. read_committed không thấy A_UNCOMMITTED.
        List<String> committed =
            committedValues(SAME_ID_TOPIC, "B_COMMITTED");

        assertTrue(committed.contains("B_COMMITTED"));
        assertFalse(committed.contains("A_UNCOMMITTED"));
        assertEquals(List.of("B_COMMITTED"), committed);
    }

    @Test
    void distinctTransactionalIdsCanBothCommit()
            throws Exception {

        try (KafkaProducer<String, String> a =
                 new KafkaProducer<>(
                     producerProps(
                         "fencing-distinct-A", "producer-A2"));
             KafkaProducer<String, String> b =
                 new KafkaProducer<>(
                     producerProps(
                         "fencing-distinct-B", "producer-B2"))) {

            a.initTransactions();
            b.initTransactions();

            a.beginTransaction();
            a.send(new ProducerRecord<>(
                DIFFERENT_ID_TOPIC, "A2", "A2_COMMITTED"))
                .get(10, TimeUnit.SECONDS);
            a.commitTransaction();

            b.beginTransaction();
            b.send(new ProducerRecord<>(
                DIFFERENT_ID_TOPIC, "B2", "B2_COMMITTED"))
                .get(10, TimeUnit.SECONDS);
            b.commitTransaction();
        }

        List<String> committed =
            committedValues(
                DIFFERENT_ID_TOPIC, "B2_COMMITTED");

        assertTrue(committed.contains("A2_COMMITTED"));
        assertTrue(committed.contains("B2_COMMITTED"));
        assertEquals(2, committed.size());
    }
}
```

### 7.2. Test chứng minh điều gì?

- `a.initTransactions()` làm A trở thành producer hợp lệ cho transactional ID đã chọn.
- `a.beginTransaction()` và `a.send(...).get(...)` đưa một record vào transaction **chưa commit** của A.
- `b.initTransactions()` **cùng ID** yêu cầu coordinator khởi tạo thế hệ mới; transaction đang dở của A được kết thúc/abort trong quá trình recovery/fencing.
- `b.commitTransaction()` thành công cho transaction mới.
- `a.commitTransaction()` phải thất bại vì producer A không còn quyền commit.
- Consumer `read_committed` chỉ trả dữ liệu từ transactions đã commit, không đưa record thuộc transaction bị abort lên tầng ứng dụng.
- Negative control sử dụng **hai ID khác nhau** và cho thấy cả hai producers đều có thể commit.

**Lưu ý version và timing:** ví dụ chọn một thứ tự gọi tường minh, chờ future send thành công và để B `initTransactions` trước khi A commit. Trong những biến thể khác, lỗi fencing có thể lộ ra ở `send`, `flush`, `commitTransaction` hoặc callbacks và có thể được bọc bởi Kafka exception. Test phải kiểm tra loại lỗi ở điểm thao tác phù hợp với Kafka client version mục tiêu, không phụ thuộc vào một chuỗi log cố định.

### 7.3. Vì sao gửi record A trước khi B xuất hiện?

Nếu A chưa bắt đầu transaction hoặc chưa gửi record, vẫn có thể bị fence khi B dùng cùng ID; nhưng ta sẽ không quan sát được đầy đủ điều kiện dữ liệu **uncommitted/aborted**. Gửi record A thành công vào transaction trước khi B init giúp kiểm tra hai mặt: *fencing* và *transactional visibility*.

### 7.4. Vì sao không gọi `abortTransaction()` trên A sau khi bị fence?

Fencing là lỗi fatal với producer cũ; sau đó A không còn là chủ sở hữu hợp lệ. Cố `abortTransaction()` hoặc `commitTransaction()` thêm lần nữa không phải recovery an toàn và có thể lại ném exception. Producer cũ cần được đóng; producer hợp lệ mới/coordinator chịu trách nhiệm theo transaction protocol.

### 7.5. Kết quả mong đợi khi chạy test

```text
[Producer A] initTransactions OK
[Producer A] begin + send A_UNCOMMITTED OK
[Producer B] initTransactions using same transactional.id OK
[Producer B] begin + send B_COMMITTED OK
[Producer B] commitTransaction OK
[Producer A] commitTransaction -> ProducerFencedException
[Consumer read_committed] -> B_COMMITTED only

Second test:
[Producer A2, tx.id A] commit OK
[Producer B2, tx.id B] commit OK
[Consumer read_committed] -> A2_COMMITTED, B2_COMMITTED
```

Log thực tế khác theo Kafka version. Đừng assert exact log string; assert exception category và **kết quả consumer**.

---

## 8. Kiểm tra bằng `read_uncommitted`: quan sát record của transaction bị abort

Trong Kafka, một record đã được append vào log trong transaction A có thể được consumer với `isolation.level=read_uncommitted` trả ra dù transaction cuối cùng bị abort. Consumer `read_committed` sẽ không trả record đó.

Để mở rộng bài test, tạo một consumer khác:

```java
Properties props = consumerProps();
props.put(
    ConsumerConfig.ISOLATION_LEVEL_CONFIG,
    "read_uncommitted");

try (KafkaConsumer<String, String> c =
        new KafkaConsumer<>(props)) {

    TopicPartition tp =
        new TopicPartition("fencing.same-id.it", 0);

    c.assign(List.of(tp));
    c.seekToBeginning(List.of(tp));

    // Poll cho tới khi thấy các records của scenario.
    // Quan sát A_UNCOMMITTED và B_COMMITTED
    // tùy Kafka log/retention và test isolation.
}
```

### 8.1. Ý nghĩa kết quả

| Record | Transaction status | Consumer `read_uncommitted` | Consumer `read_committed` |
| --- | --- | --- | --- |
| `A_UNCOMMITTED` | A bị fence, transaction bị abort | Có thể nhìn thấy record đã append | **Không** |
| `B_COMMITTED` | B commit thành công | Có | Có |
| Control markers | Kafka transaction protocol | Không biểu diễn như business records thường | Không biểu diễn như business records thường |

Không dùng `read_uncommitted` cho consumer nghiệp vụ muốn chỉ thấy committed transactional records. Đây là điểm đặc biệt quan trọng khi test “không lộ half transaction”.

### 8.2. Tại sao test chỉ kiểm tra value chưa đủ?

Nếu nhiều test dùng chung một topic có dữ liệu cũ, việc tìm thấy `B_COMMITTED` chưa chứng minh record thuộc lần chạy hiện tại. Bài test dùng topic riêng; khi phát triển suite lớn hơn nên dùng topic/transactional IDs có namespace test được kiểm soát, consumer group mới hoặc broker mới. Với môi trường chia sẻ, thêm correlation/test-run ID trong key/value và kiểm tra chính xác.

---

## 9. Đưa tình huống này vào Testcontainers

### 9.1. Khi nào chọn Testcontainers?

Embedded Kafka đủ để tái hiện fencing. Testcontainers phù hợp khi muốn:

- Chạy broker trong process/container riêng thay vì embedded test JVM.
- Chọn Kafka image/broker version cụ thể.
- Kết hợp Kafka, database, mock API, network proxy.
- Mô phỏng restart/pause và kết nối lại.
- Ghi logs/metrics từ Kafka container để phân tích tình huống production.

Testcontainers không mặc định tạo cluster HA: một Kafka container vẫn là **một broker**.

### 9.2. Kafka container với internal transaction state topic

Ví dụ Testcontainers 1.x:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class KafkaContainerFencingIT {

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse(
                "confluentinc/cp-kafka:7.6.1"))
            .withEnv(
                "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", "1")
            .withEnv(
                "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", "1")
            .withEnv(
                "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", "1");

    @Test
    void reproduceFencing() throws Exception {
        String bootstrap = kafka.getBootstrapServers();

        // Tạo topic bằng AdminClient trước khi gửi.
        // Dùng bootstrap trong producerProps(...).
        // Thực hiện lại kịch bản Producer A / Producer B
        // cùng transactional.id như mục 7.
    }
}
```

**Quan trọng:** đây là ví dụ phần **hạ tầng container**, không phải toàn bộ test độc lập; tạo topic và các KafkaProducer/Consumer như mục 7. Với Testcontainers versions mới, module/package Kafka container thay đổi, có thể dùng `org.testcontainers.kafka.ConfluentKafkaContainer` theo tài liệu bản đang cài.

Nếu environment variables không được image/container startup script áp dụng như kỳ vọng, kiểm tra Kafka broker effective configs và container logs. Transaction coordinator cần khởi tạo được trước khi mô phỏng fencing.

### 9.3. Tạo topic bằng AdminClient

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;

try (AdminClient admin = AdminClient.create(
        Map.of(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            kafka.getBootstrapServers()))) {

    admin.createTopics(List.of(
        new NewTopic(
            "fencing.container.it",
            1,
            (short) 1)))
        .all()
        .get(15, TimeUnit.SECONDS);
}
```

Nếu dùng topic tên cố định nhưng container có state giữ lại, xử lý `TopicExistsException` có chủ đích. Không bật auto-create để “test đơn giản hơn” rồi vô tình che topic ACL/configuration bugs.

### 9.4. Tạo thêm một Kafka broker có giúp tái hiện fencing tốt hơn?

Không cần. Producer fencing là một cơ chế **transaction coordinator/epoch**; test với một broker đủ cho semantics này. Cluster nhiều brokers chỉ cần khi bạn muốn test coordinator failover, ISR và availability. Việc dựng ba brokers nhưng vẫn dùng transaction ID sai không làm lỗi này tự biến mất.

---

## 10. Spring Kafka `transaction-id-prefix` trong ứng dụng thật

### 10.1. Cấu hình Spring Boot

Spring Boot/Spring Kafka thường tạo transactional producer factory khi khai báo:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
```

`localhost:9092` chỉ là ví dụ local; với Kubernetes/CI cần lấy bootstrap servers từ environment/platform.

Khi có transaction ID prefix, Spring Kafka quản lý transactional producers qua `DefaultKafkaProducerFactory`. Spring Boot có thể auto-configure transaction manager và template phù hợp nếu các bean conditions đáp ứng. **Không đồng nhất prefix với một single transactional ID cố định**: factory quản lý các IDs/suffixes cho producers trong cache và theo số giao dịch đồng thời.

### 10.2. Producer factory tạo transactional IDs như thế nào?

Có thể hình dung:

```text
Spring Boot property:
  transaction-id-prefix = orders-node-A-

DefaultKafkaProducerFactory:
  transactional.id = orders-node-A-0
  transactional.id = orders-node-A-1
  transactional.id = orders-node-A-2
  ...

Một replica khác:
  transaction-id-prefix = orders-node-B-
  transactional.id = orders-node-B-0
  transactional.id = orders-node-B-1
  ...
```

Hậu tố và cơ chế tái sử dụng thực tế thay đổi theo Spring Kafka version và transaction suffix strategy. **Không viết unit test production dựa vào một chuỗi suffix cứng**. Quy tắc là các transactional IDs được factory quản lý phải không tranh chấp giữa hai live producer owners.

### 10.3. Sai lầm: hai replicas cùng prefix và cùng suffix space

```text
Replica A:
  transaction-id-prefix = orders-tx-
  producer.id = orders-tx-0

Replica B:
  transaction-id-prefix = orders-tx-
  producer.id = orders-tx-0

Replica A <---- FENCED ----> Replica B
```

Nếu cả hai replicas tạo cùng transactional ID, chúng có thể liên tục fence nhau, nhất là sau scale-out hoặc rolling deployment. Đây là lỗi cấu hình phổ biến.

### 10.4. Chiến lược đặt prefix

Một phương án có thể dùng **logical owner identity**:

```text
Service: orders-publisher
Namespace: production
Logical owner: shard-03

transaction-id-prefix = orders-prod-shard-03-
```

Các lưu ý:

1. Prefix **duy nhất giữa các owners đang hoạt động đồng thời**.
2. Nếu một owner được thay thế mà process cũ còn sống, việc dùng lại cùng identity **có thể là chủ đích** để fence zombie.
3. Nếu mọi lần restart sinh UUID mới dù vẫn là cùng logical owner, Kafka sẽ không dùng shared transactional ID để fence producer cũ; còn cần fencing/lease ở tầng assignment nếu có yêu cầu.
4. Nếu mỗi replica sinh prefix cố định giống hệt nhau, đó là lỗi tranh chấp.
5. Nếu dùng `HOSTNAME` hoặc Kubernetes pod name, hiểu rằng Deployment pod names thường thay đổi qua rollout; dùng StatefulSet ordinal hoặc assignment ID ổn định khi cần owner identity liên tục.

Không có công thức tên prefix duy nhất cho mọi hệ thống. Cần xác định **ai sở hữu transaction scope**, số replica, shard/partition ownership và cách worker được thay thế.

### 10.5. Không dùng một ID mới cho mỗi transaction chỉ để né fencing

```text
transactional.id = random UUID every send
```

Cách này có thể giảm collision giữa producers nhưng làm mất một lợi ích cốt lõi của transactional ID ổn định: một phiên producer mới có thể fence phiên cũ của cùng logical owner. Nó cũng có thể làm Kafka coordinator giữ nhiều transactional IDs không cần thiết. Không dùng random per-message ID như một “fix” phổ quát cho fencing.

---

## 11. Spring Kafka transaction với `KafkaTemplate`

### 11.1. Dùng Spring-managed transactional producer

Sau khi cấu hình `transaction-id-prefix`, một service có thể xuất bản atomically trong phạm vi Kafka transaction:

```java
package example.kafka;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class TransactionalOrderPublisher {

    private final KafkaTemplate<String, String> template;

    public TransactionalOrderPublisher(
            KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public void publishOrder(
            String orderId, String json) {

        template.executeInTransaction(operations -> {
            operations.send(
                "orders.events", orderId, json);
            return null;
        });
    }
}
```

Đây là một cách để Spring Kafka lấy transactional producer từ factory và xử lý begin/commit/abort theo callback. Nó khác ví dụ raw `KafkaProducer` ở mục 7, nơi ta chủ động tạo hai producers và cùng đặt một transactional ID để tái hiện lỗi.

### 11.2. `@Transactional` với Kafka

Spring Kafka có `KafkaTransactionManager` để quản lý Kafka transactions. Trong ứng dụng phối hợp database/JPA, cần rõ transaction manager nào được chọn:

```java
@Transactional("kafkaTransactionManager")
public void publishInKafkaTransaction(...) {
    kafkaTemplate.send(...);
}
```

Đây là ví dụ cấu trúc; cần bean name thực tế và factory cấu hình đúng. Không gán một `@Transactional` không chỉ định rồi mặc định rằng Kafka và JDBC cùng nằm trong một ACID transaction.

### 11.3. Fencing đi qua Spring như thế nào?

Nếu một `KafkaProducer` bên trong factory bị fence:

- Thao tác send/commit có thể fail với `ProducerFencedException` hoặc cause liên quan Kafka producer epoch.
- Spring transaction synchronization có thể wrap exception theo lớp tích hợp.
- Factory không nên tiếp tục tái sử dụng một producer đã fatal.
- Application nên phân loại đây là **ownership/fatal transactional producer issue**, không phải lỗi serialization một record có thể skip.

Để viết **test fencing có điều kiện hoàn toàn deterministically**, dùng raw `KafkaProducer` như mục 7. Test Spring-managed factory cần xác nhận exact transactional IDs hoặc thiết lập suffix strategy kiểm soát, rồi khởi tạo contexts/instances phù hợp; không dựa vào assumption “cứ hai KafkaTemplate là sẽ fence”.

---

## 12. Fencing hợp lệ và fencing do cấu hình sai

### 12.1. Trường hợp hợp lệ: failover một logical owner

```text
Shard 03 -> owner A
A đang xử lý transaction T, sau đó mất lease

Shard 03 -> owner B
B nhận assignment hợp lệ
B dùng transactional identity của shard 03
Kafka fences A

A tỉnh lại -> ProducerFencedException
A không được publish nữa
```

Fencing bảo vệ correctness. Tuy nhiên, chuyển ownership của **business shard** phải do orchestrator/coordinator kiểm soát, không chỉ dựa vào Kafka transaction ID. Kafka không biết các side effects ngoài Kafka của A.

### 12.2. Trường hợp sai: tất cả pods cùng tên

```text
orders-service pod-1 -> orders-tx-0
orders-service pod-2 -> orders-tx-0
orders-service pod-3 -> orders-tx-0
```

Nếu mỗi pod đều tin mình có quyền dùng `orders-tx-0`, producer epochs liên tục thay đổi. Kết quả thường là transaction failures, throughput thấp, retry loops và message processing không ổn định.

Sửa bằng cách xác định namespace transactional IDs theo owner/replica/shard và đảm bảo không có two-live-owner collisions.

### 12.3. Một pod bị pause không giống pod chết

Nếu pod A bị pause, orchestrator có thể cho B khởi động. A có thể hồi phục sau khi B đã nhận quyền. Producer fencing khiến A không commit bằng epoch cũ, nhưng **A vẫn có thể gây tác động ngoài Kafka** nếu code đã gọi HTTP/DB trước khi nhận exception.

Vì vậy cần lease/fencing token ở tầng business resource hoặc idempotency/outbox khi thao tác ngoài Kafka.

---

## 13. Fencing và các exception liên quan

### 13.1. `ProducerFencedException`

Kafka API `org.apache.kafka.common.errors.ProducerFencedException` biểu thị producer bị fence do producer khác được khởi tạo với cùng transactional identity hoặc một tình huống producer epoch ownership đã thay đổi.

Đây là lỗi **fatal cho producer instance bị fence**. Không retry send/commit trên chính instance này.

### 13.2. `InvalidProducerEpochException`

Đây là một lỗi protocol liên quan epoch không còn phù hợp. Tùy broker/client path và thời điểm lỗi, người vận hành có thể thấy exception này hoặc nguyên nhân gốc tương tự khi producer epoch không hợp lệ. Phải xem stack trace/cause chain và Kafka logs, không chỉ regex thông báo.

### 13.3. `OutOfOrderSequenceException`

Liên quan idempotent producer sequence state. Không tự kết luận mọi lỗi sequence đều do trùng `transactional.id`. Cần phân tích producer epoch/transaction state, broker response và phần mềm producer/client.

### 13.4. `TransactionAbortedException` và timeout

Một transaction có thể bị abort vì timeout hoặc thao tác application fail. Transaction abort **không nhất thiết là producer fencing**. Với lỗi abortable, client API cho phép abort transaction và tiếp tục trong một số trường hợp; với producer đã bị fenced, không làm vậy.

### 13.5. `TransactionalIdAuthorizationException`

Nếu principal không có quyền với transactional ID, broker có thể từ chối `initTransactions()` hoặc transaction operations. Đây là **security/ACL issue**, không được “chữa” bằng cách đổi ID ngẫu nhiên hoặc cấp wildcard ACL.

### 13.6. `FencedInstanceIdException`

Một consumer dùng `group.instance.id` (static membership) có thể bị fence nếu hai consumers cùng tranh chấp static member identity. Đây là lỗi ở **consumer group coordinator**, khác với producer transaction epoch fencing. Tên exception gần giống nhưng runbook và cấu hình cần sửa khác.

### 13.7. Bảng nhận diện

| Exception / dấu hiệu | Bối cảnh thường gặp | Định hướng |
| --- | --- | --- |
| `ProducerFencedException` | Transactional producer mất ownership | Đóng producer cũ, kiểm tra ID collision/lease |
| `InvalidProducerEpochException` | Producer epoch không hợp lệ | Điều tra epoch state, nested causes |
| `OutOfOrderSequenceException` | Sequence tracking không nhất quán | Xem idempotent producer/retries |
| Transaction timeout | Transaction mở quá lâu | Xem processing duration, broker max timeout |
| Transactional ID authorization | ACL sai | Sửa quyền tối thiểu |
| `FencedInstanceIdException` | Consumer static membership trùng | Sửa `group.instance.id`, không phải tx prefix |
| `TimeoutException` từ `initTransactions` | Broker/coordinator chưa sẵn sàng hoặc internal topic không đủ ISR | Kiểm tra broker setup trước khi kết luận fencing |

---

## 14. Tại sao không nên bắt `ProducerFencedException` rồi retry?

Đây là anti-pattern:

```java
while (true) {
    try {
        producer.commitTransaction();
        break;
    } catch (ProducerFencedException ex) {
        // SAI: producer đã mất quyền, retry không tạo quyền mới.
        Thread.sleep(1000);
    }
}
```

Khi producer bị fence, epoch cũ không tự trở thành hợp lệ lại. Lặp lại thao tác trên cùng instance làm việc phục hồi bị kẹt và che nguyên nhân.

### 14.1. Hướng recovery phù hợp

```text
Catch ProducerFencedException
            |
            v
  Mark producer instance unusable
            |
            v
  Stop affected workflow / partition
            |
            v
  Close producer and stop stale owner
            |
            v
  Collect tx.id / owner / epoch diagnostics
            |
            v
  Reconcile Kafka and business outcomes
            |
            v
  Coordinator assigns owner legitimately
            |
            v
  New producer initializes transaction
            |
            v
  Resume only if idempotency/offset safe
```

**Không** phải mọi producer cần được tái tạo thủ công ngay trong catch block. Với Spring-managed producers và orchestration, thường tốt hơn để container lifecycle/restart policy tiếp quản sau khi xác định failed owner.

### 14.2. Khi nào phải alert?

Nếu fencing xảy ra đúng một lần khi chuyển logical ownership, nó có thể là expected recovery event. Nếu cùng transaction ID liên tục fenced trong vài phút khi nhiều replicas đều đang healthy, đây có thể là **transactional ID collision** và cần cảnh báo.

Đừng cấu hình alert “bất kỳ ProducerFencedException là Sev-1” khi application có cơ chế failover hợp lệ; liên hệ với impact lên business output và tần suất.

---

## 15. So sánh fencing với transaction timeout

Một transaction timeout độc lập cũng có thể gây abort và lỗi producer, nhưng nguyên nhân không giống tranh chấp transactional ID.

| Điều kiện | Producer fencing | Transaction timeout |
| --- | --- | --- |
| Trigger | Producer khác cùng ID/epoch ownership mới | Transaction kéo dài vượt giới hạn |
| Dấu hiệu | Fencing/invalid epoch errors | Timeout/abort-related errors |
| Có cần producer B? | Trong test tranh chấp ID: có | Không |
| Sửa bằng tăng timeout? | Không | Chỉ khi transaction duration hợp lệ |
| Sửa bằng unique ID per active owner? | Có thể | Không đủ |
| Dữ liệu chưa commit | Không hiện với `read_committed` nếu transaction bị abort | Tương tự |
| Recovery | Stop stale owner, reinitialize hợp lệ | Điều tra duration, timeout và idempotent retry |

### 15.1. `transaction.timeout.ms` và broker max timeout

`KafkaProducer` có `transaction.timeout.ms`; broker có `transaction.max.timeout.ms`. Nếu client yêu cầu timeout lớn hơn giới hạn broker, `initTransactions`/transaction setup có thể bị từ chối theo error tương ứng.

Nếu workload chậm, không tăng transaction timeout vô hạn vì:

- Long-running transactions kéo dài last stable offset, ảnh hưởng consumers `read_committed`.
- Giữ nhiều records chưa visible.
- Làm failure recovery chậm.
- Che latency/bottleneck thực sự.

Một job xử lý hàng triệu bản ghi có thể cần chia nhỏ transactions/partitions thay vì mở một Kafka transaction kéo dài hàng giờ.

---

## 16. Producer fencing có liên quan đến idempotence không?

Có nhưng không đồng nhất.

### 16.1. Idempotent producer

Kafka idempotent producer dùng producer ID/sequence numbers để giảm duplicate records do **producer retry** trong những giới hạn của protocol/session.

```yaml
spring:
  kafka:
    producer:
      properties:
        enable.idempotence: true
```

Đây không phải bảo đảm mọi business event chỉ xuất hiện một lần. Nếu service gọi `send` hai lần cho cùng order vì HTTP request lặp, Kafka vẫn có thể lưu hai event hợp lệ.

### 16.2. Transactional producer

Transactional producer bổ sung `transactional.id`, begin/commit/abort, producer epoch fencing và khả năng phối hợp records/offsets trong Kafka transactions.

```text
Idempotent:
  chống một số duplicate do send retries trong producer session

Transactional:
  atomic visibility của records trong transaction
  ownership fencing theo transactional.id
  có thể phối hợp Kafka consumed offsets trong transaction
```

Không có `transactional.id` thì test hai idempotent producers với cùng `client.id` sẽ không tạo ra transactional producer fencing theo cách này.

### 16.3. Business idempotency vẫn cần

Ngay cả khi producer A bị fence hoàn toàn đúng:

- Worker B có thể reprocess input đã từng làm DB commit.
- App có thể phát event mới cho cùng business operation nếu request duplicate.
- Consumer có thể xử lý lại record nếu offset commit chưa hoàn tất.
- External HTTP/payment/email side effect có thể bị lặp.

Do đó cần event/business IDs ổn định, unique constraints, transactional outbox hoặc cơ chế deduplication phù hợp.

---

## 17. Nếu producer A đã gửi message trước khi bị fence thì sao?

Có ba tình huống cần phân biệt.

### 17.1. Message thuộc transaction A chưa commit

```text
A begin
A send X (broker append)
B init cùng transactional.id
A transaction aborted/fenced
B commit Y

read_committed -> Y
read_uncommitted -> có thể nhìn thấy X và Y
```

X không được xem là committed business record.

### 17.2. A đã commit transaction xong trước khi B init

```text
A begin
A send X
A commit -> success

B init cùng transactional.id
B begin, send Y, commit

read_committed -> X và Y
```

Fencing **không xóa** transaction đã commit hợp lệ trước đó. Nó ngăn A commit các transaction **sau khi epoch mất hiệu lực**.

### 17.3. A đã ghi DB ngoài Kafka trước khi bị fence

```text
A begins Kafka transaction
A updates PostgreSQL -> COMMIT
B init same tx.id, fences A
A Kafka commit fails
```

Kafka không rollback PostgreSQL. Khi B xử lý lại input, DB có thể gặp duplicate hoặc tạo side effects mới nếu thiếu idempotency. Đây là lý do không thể coi producer fencing là distributed transaction trên toàn ứng dụng.

---

## 18. Spring Kafka consumer–producer transaction và fencing

Một consumer nhận input và publish output có thể dùng Kafka transaction để phối hợp **output Kafka records** với **consumed offsets** (khi cấu hình container/transaction manager đúng).

```text
Consumer group orders-transform
          |
      input record E
          |
          v
  Kafka transactional producer
          |
  send transformed output
  send offsets to transaction
          |
          v
    commit transaction
```

Khi owner cũ bị fence trước commit:

- Output chưa commit của old producer không được visible cho `read_committed` consumer.
- Offset chưa được commit trong old Kafka transaction có thể dẫn đến replay sau recovery.
- New owner có thể nhận lại input và xử lý lại một cách hợp lệ.
- Side effects bên ngoài Kafka vẫn cần idempotency.

### 18.1. `sendOffsetsToTransaction` (Kafka client API)

Trong raw Kafka Producer API, Kafka-to-Kafka transactions có thể bao gồm offsets:

```java
// Minh họa API: consumerGroupMetadata đến từ consumer
// và offsets map do application xác định đúng.
producer.sendOffsetsToTransaction(
    offsetsToCommit,
    consumer.groupMetadata());
```

Tuy nhiên test của bài **không cần** gọi API này, vì nó chỉ chứng minh producer fencing và transactional visibility. Khi thêm source consumer/offsets, cần test riêng group assignments, transaction fencing và restart/replay semantics.

### 18.2. Không tự động đồng bộ JDBC

`KafkaTransactionManager` không tự tạo atomicity với một `DataSourceTransactionManager` khác. Một pipeline cần exactly-once **business effects** thường dùng thêm transactional outbox/idempotent consumers hoặc reconciliation theo business keys.

---

## 19. Mô phỏng fencing trong Kubernetes và nhiều replicas

### 19.1. Cấu hình sai để tái hiện (chỉ trong test/staging)

Hai replicas đều có:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-
```

Nếu mỗi replica có producer suffix `0`, transactional ID thực trùng nhau. Sau khi traffic đi qua cả hai, một replica có thể bị fence; nếu cả hai tiếp tục khởi tạo producers, có thể tạo **fencing storm**.

Không cố ý triển khai cấu hình này trên production chỉ để quan sát lỗi.

### 19.2. Cấu hình theo logical owner

Ví dụ operator assign partitions/shards:

```text
Deployment logical owner 0:
  transaction-id-prefix = orders-live-owner-0-

Deployment logical owner 1:
  transaction-id-prefix = orders-live-owner-1-

Deployment logical owner 2:
  transaction-id-prefix = orders-live-owner-2-
```

Với StatefulSet, ordinal có thể cung cấp logical owner ID ổn định trong tình huống cụ thể. Với Deployment, pod names mới sau mỗi rollout có thể đổi nên cần hiểu cách ứng dụng giữ ownership liên tục.

### 19.3. Khi worker cũ tỉnh lại

Nếu old worker mất lease, new worker lấy cùng logical owner identity, Kafka fencing có thể giúp old worker không publish sau thời điểm đó. Tuy nhiên old worker phải **tự ngừng xử lý các tác vụ ngoài Kafka** sau khi lease mất. Nên gắn lease/fencing token hoặc DB ownership check ở tầng business resource khi có requirement này.

### 19.4. Những nguồn tạo ID collision

- Copy cùng `transaction-id-prefix` qua ConfigMap tất cả replicas.
- App tự gán fixed `transactional.id` thay vì dùng producer factory.
- Hai environments/staging/prod vô tình trỏ tới cùng Kafka cluster và cùng prefix.
- Cùng một logical owner được assign cho hai workers vì race trong scheduler/lease.
- Rolling restart không đợi old process dừng khi identity assignment không có fencing/recovery plan.
- Tên suffix dựa vào biến môi trường trống/fallback chung, làm mọi pod tạo ID giống nhau.

---

## 20. Quan sát producer fencing ở log, metrics và tracing

### 20.1. Log có cấu trúc

Một log sự kiện hữu ích:

```text
event=kafka_producer_fenced
service=orders-publisher
environment=staging
owner=shard-03
transactionalId=orders-staging-shard-03-0
clientId=orders-publisher-pod-6
pod=orders-publisher-pod-6
operation=commitTransaction
exception=ProducerFencedException
action=close_stale_producer
```

Chỉ đưa vào log các metadata vận hành cần thiết. Không log payload khách hàng, credentials, SASL config hoặc private keys.

### 20.2. Các tín hiệu cần giám sát

| Signal | Giải thích |
| --- | --- |
| Count của producer fencing exceptions | Nhận biết collision hay expected ownership transfer |
| Transaction commit failures | Tác động lên output |
| Transaction abort rate | Phân biệt business abort với fencing |
| Kafka producer send errors/latency | Broker/client health |
| Consumer group lag | Replay/processing bị chậm |
| Rebalance frequency | Có vấn đề ở assignment không |
| Producer instance restarts | Fencing storm có gây restart loop không |
| Business output count / duplicate keys | Xác nhận tính đúng |
| Kafka broker transaction coordinator logs | Epoch/owner changes |
| DLT/backlog nếu pipeline dùng | Message lỗi còn được xử lý/đối soát không |

Không dùng `transactionalId` làm metric tag nếu mỗi producer/session tạo một chuỗi ID mới không giới hạn; dùng logical owner/shard/namespace có cardinality hữu hạn, và ghi ID chi tiết trong logs có kiểm soát.

### 20.3. Phân biệt expected và unexpected fencing

Ví dụ một lần failover:

```text
T=10:00:00 lease của A hết hạn
T=10:00:02 B trở thành owner
T=10:00:03 B init tx.id
T=10:00:04 A bị fenced và dừng

Expected: một fencing event khi handoff.
```

Trong cấu hình lỗi:

```text
T=10:00:00 A init tx.id
T=10:00:01 B init same tx.id -> fences A
T=10:00:02 A recreates producer -> fences B
T=10:00:03 B recreates producer -> fences A
...
```

Đây là collision/fencing storm và cần can thiệp nhanh. Sửa code retry không đủ nếu prefix conflict tiếp diễn.

---

## 21. Runbook xử lý khi `ProducerFencedException` xuất hiện

### Bước 1 — Xác nhận phạm vi

Ghi nhận:

- Service, namespace, deployment version, pod ID.
- `transactional.id` thực và `client.id`.
- Thời điểm lỗi, operation (`initTransactions`/`send`/`commit`).
- Kafka cluster, broker versions, coordinator logs.
- Số replicas đang hoạt động, owner/shard assignment.
- Có rollout, pod restart, lease handoff hoặc network disruption gần đó không.

### Bước 2 — Kiểm tra collision

Nếu hai pods/instances log cùng transactional ID trong cùng khoảng thời gian:

- Xác minh có phải failover hợp lệ của **cùng logical owner**.
- Nếu không, kiểm tra `transaction-id-prefix`, suffix strategy và owner identity.
- Kiểm tra ConfigMap/Helm chart/environment variables và fallback values.
- Dừng vòng lặp restart liên tục nếu gây ảnh hưởng lớn.

### Bước 3 — Không cố commit producer bị fence

Không retry trực tiếp trên producer cũ. Đảm bảo worker mất ownership không tiếp tục ghi Kafka hoặc thực hiện side effects ngoài Kafka không được bảo vệ.

### Bước 4 — Đối soát trạng thái

Cần biết:

- Transaction của A đã commit trước B hay chưa.
- Dữ liệu A gửi thuộc transaction bị abort hay đã committed.
- B đã ghi business event nào.
- Consumer group có replay record nào.
- DB/external side effects nào đã xảy ra trước khi fencing.

Khi cần, đọc topic bằng `read_committed` consumer và đối chiếu event ID/business key. Không dùng `read_uncommitted` để quyết định event đã được công bố hợp lệ.

### Bước 5 — Sửa ownership/identity

Chọn prefix/schema transactional ID phù hợp. Nếu lỗi do hai replicas cùng prefix, bảo đảm unique giữa live owners. Nếu failover hợp lệ, đảm bảo old owner thực sự dừng và new owner có quyền tiếp tục.

### Bước 6 — Khôi phục có kiểm soát

- Đóng stale producer.
- Khởi tạo producer mới **chỉ khi ownership hợp lệ**.
- Giữ idempotent business handling.
- Resume source offsets theo contract.
- Kiểm tra producer transactions/consumer lag/DLT.
- Đối soát business output và duplicate side effects.

### Bước 7 — Phòng ngừa tái phát

Thêm kiểm thử:

1. Hai live replicas không tạo cùng transactional IDs ngoài ownership handoff.
2. Khi new owner init cùng ID, old producer bị fence và dừng.
3. Sau fencing, không retry trên old producer.
4. Business output không trùng sau replay.
5. Alert phân biệt expected failover và collision storm.

---

## 22. Những lỗi thường gặp khi mô phỏng producer fencing

| Lỗi | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| Quên `transaction.state.log.replication.factor=1` trên single broker | `initTransactions` timeout | Chỉnh test broker settings |
| Dùng `enable.idempotence=true` nhưng không có `transactional.id` | Không có producer fencing mong đợi | Tạo transactional producer |
| Dùng hai `client.id` giống nhau và nghĩ sẽ fence | Test không ném exception | Dùng **cùng transactional ID** |
| Hai producers có transactional IDs khác nhau | Cả hai commit | Đúng behavior; dùng làm negative control |
| Để A commit trước khi B init | A không bị fence cho transaction đã commit | Giữ A transaction mở đến khi B init |
| Không đợi `send` future của A | Test race/timing khác nhau | Chờ ack trước khi B init |
| Dùng `read_uncommitted` để assert invisible record | Thấy record của A đã bị abort | Dùng `read_committed` |
| Assert exact Kafka log message | Test fail khi nâng version | Assert exception + committed outputs |
| Dùng Spring Kafka prefix mà không kiểm soát suffix | Không tái hiện đúng ID collision | Raw KafkaProducer để test deterministic |
| Bắt exception rồi retry cùng producer | Fencing loop | Close stale producer |
| Thay ID random mỗi transaction | Không còn fencing logical zombie hiệu quả | Namespace theo owner/shard |
| Dùng Kafka transaction để giả định DB atomic | Duplicate side effects | Outbox/idempotency |
| Chạy test trên topic broker dùng chung | Dữ liệu test lẫn nhau | Topic/tx ID isolation |
| Quên DLT/offset consequences | Business reconciliation thiếu | Test end-to-end recovery |
| Stop/start Docker container khiến port đổi | App giữ bootstrap cũ | Dùng stable endpoint hoặc recreate context |
| Assert một broker chứng minh cluster HA | Bỏ qua ISR/failover | Multi-broker/staging suite |
| Gán cùng prefix cho mọi pod | Fencing storm | Unique concurrent owners |

---

## 23. Mở rộng bài lab: tình huống owner handoff có kiểm soát

Một test advanced có thể mô phỏng orchestrator giao một shard:

```text
Lease table:
  owner_key = orders-shard-03
  holder = pod-A
  lease_version = 41

A:
  obtain lease 41
  begin tx for orders-shard-03

Lease expires:
  B obtains lease 42
  B initializes same Kafka tx identity
  B commits new transaction

A resumes:
  Kafka commit -> fenced
  DB write guarded by lease_version=41 -> rejected
```

Kafka fence bảo vệ Kafka output; **lease version check** bảo vệ tài nguyên ngoài Kafka. Hãy test:

- A không thể publish Kafka transaction cũ.
- A không thể update DB khi lease version đã đổi.
- B xử lý đúng input/offset state.
- Nếu A đã commit một business effect trước handoff, B dedupe được bằng event ID.

Bài mở rộng chứng minh sự khác nhau giữa **Kafka transactional fencing** và **distributed ownership fencing** cho toàn bộ workflow.

---

## 24. Kiểm thử theo lỗi và đối chứng

Một test suite production hữu ích có các trường hợp:

| ID | Scenario | Assertion |
| --- | --- | --- |
| F01 | A/B cùng transactional ID | A `ProducerFencedException` sau B init |
| F02 | A/B khác transactional IDs | Cả hai commit thành công |
| F03 | A chưa commit rồi bị fence | `read_committed` không nhìn thấy A |
| F04 | A commit trước B init | Transaction đã commit của A vẫn được nhìn thấy |
| F05 | A bị fence rồi cố send tiếp | Producer cũ không được tái sử dụng |
| F06 | B bị chậm nhưng vẫn là owner | Không tự tạo producer mới/fence vô lý |
| F07 | Hai Spring replicas cùng prefix | Collision được phát hiện bằng logs/metrics |
| F08 | Unique prefix theo live owner | Không fence nhau dưới concurrent load |
| F09 | Transaction timeout không có B | Phân biệt timeout và fencing |
| F10 | Transactional ID ACL thiếu | Lỗi authorization, không phải fencing |
| F11 | Consumer static ID trùng | `FencedInstanceIdException`, runbook riêng |
| F12 | Kafka tx + PostgreSQL effect | Replay không nhân đôi DB business state |
| F13 | Broker restart | Transaction recover/reinitialize hợp lệ |
| F14 | Rolling version upgrade | Không thay đổi ownership semantics |
| F15 | Producer metrics alert | Expected handoff không bị báo sai severity |

### 24.1. Những test không nên gộp làm một

- **Unit test:** kiểm tra prefix generator, owner assignment, error classifier.
- **Embedded Kafka:** kiểm tra fencing/transaction visibility.
- **Testcontainers Kafka + DB:** kiểm tra idempotency và recovery sau crash window.
- **Cluster test:** kiểm tra coordinator failover/ISR/durability.
- **Preproduction:** kiểm tra auth/ACL, cluster load và rolling deploy.

Một test mô phỏng fencing bằng hai raw producers không chứng minh cả hệ thống tự phục hồi hoàn hảo. Cần thêm các test đúng phạm vi.

---

## 25. Bài tập thực hành

### Bài 1 — Producer fencing cơ bản

Dựng `@EmbeddedKafka` một broker. Tạo A và B cùng `transactional.id`, cho A gửi record chưa commit, sau đó B `initTransactions` và commit một record khác.

Yêu cầu:

- A ném `ProducerFencedException` khi cố commit.
- B commit thành công.
- Consumer `read_committed` chỉ thấy record B.

### Bài 2 — Negative control

Giữ nguyên test nhưng dùng hai `transactional.id` khác nhau.

Yêu cầu: cả A và B commit, consumer thấy đủ hai records; giải thích vì sao `client.id` không quyết định kết quả.

### Bài 3 — Transaction đã hoàn tất

Cho A commit trước khi B init với cùng ID, sau đó B commit record mới.

Yêu cầu: `read_committed` nhìn thấy cả record A và B; chứng minh fencing không xóa các transaction đã commit.

### Bài 4 — `read_uncommitted` so với `read_committed`

Trong test A bị fence lúc transaction chưa commit, tạo hai consumers với hai isolation levels.

Yêu cầu: mô tả vì sao consumer `read_uncommitted` có thể thấy record A đã append trong log nhưng `read_committed` thì không.

### Bài 5 — Prefix collision giữa hai replicas

Tạo hai Spring application contexts cùng `transaction-id-prefix=orders-tx-` và chạy transactions đồng thời. Ghi lại transactional IDs thực tế do factories cấp.

Yêu cầu: xác định lúc nào collisions xảy ra theo suffix strategy, không chỉ giả định hai templates chắc chắn trùng `-0`.

### Bài 6 — Logical owner prefix

Viết generator nhận `environment`, `service`, `shardId` và trả prefix ổn định. Test uniqueness giữa active owners và cùng prefix khi một owner được thay thế.

Yêu cầu: phân biệt ổn định theo logical owner với random UUID theo mỗi transaction.

### Bài 7 — Recovery handler

Viết wrapper cho transactional publisher. Khi producer bị fenced, không retry trên instance cũ; báo loss of ownership, đóng producer và để orchestration restart khi hợp lệ.

Yêu cầu: test không xảy ra retry loop và exception context được log đủ.

### Bài 8 — Kafka + database

Dùng Testcontainers Kafka + PostgreSQL. Producer A đã commit DB business row nhưng Kafka transaction bị fence trước commit; B replay input.

Yêu cầu: unique business key và reconciliation giúp DB không nhân đôi; phân tích Kafka và DB transaction boundaries.

### Bài 9 — Broker failure khác fencing

Không tạo producer B. Dừng Kafka network trong khi A đang commit, xem timeout/retriable exception behavior. So sánh exception và recovery với kịch bản có B cùng transactional ID.

Yêu cầu: không gộp mọi timeout vào `ProducerFencedException`.

### Bài 10 — Runbook vận hành

Một deployment có 5 pods cùng dùng `transaction-id-prefix=orders-prod-` và logs có hàng trăm fencing events mỗi phút.

Viết runbook xác định owners, IDs, khả năng collision, bước giảm tác động, khôi phục và điều kiện tuyên bố data integrity đạt yêu cầu.

### Bài 11 — Mô phỏng failover zombie

Cho A dừng sau khi gửi record nhưng trước commit, B chiếm cùng identity và commit. A tỉnh lại và thử commit. Mở rộng bằng lease version cho DB writer.

Yêu cầu: Kafka và DB đều chặn stale owner.

### Bài 12 — Dashboard

Thiết kế dashboard gồm số fenced producers theo service/owner, transaction failures, consumer lag, aborted transactions, restart rate và duplicate business effects. Đặt cảnh báo phân biệt expected handoff và fencing storm.

---

## 26. Checklist trước khi áp dụng lên production

- [ ] `transactional.id` biểu diễn một logical owner/producer identity rõ ràng.
- [ ] Không có hai producers độc lập cần hoạt động đồng thời dùng cùng transactional ID.
- [ ] Spring Kafka `transaction-id-prefix` được namespace phù hợp cho replicas/shards.
- [ ] Producer cũ sau fencing được đóng, không retry send/commit trên instance đã mất quyền.
- [ ] Producer ID/epoch/fencing được phân biệt với consumer `group.instance.id` fencing.
- [ ] Test dùng đúng Kafka transaction-enabled broker settings.
- [ ] Test có positive case trùng ID và negative case khác IDs.
- [ ] `read_committed` không lộ records thuộc transaction aborted.
- [ ] Transactions đã commit trước fencing được giữ nguyên.
- [ ] Timeout, ACL, out-of-order sequence được phân loại riêng.
- [ ] Business side effects ngoài Kafka có idempotency/lease protection.
- [ ] Consumer offset replay được kiểm tra khi có Kafka-to-Kafka workflow.
- [ ] Monitoring phân biệt expected failover và collision storm.
- [ ] Rollout/rollback biết transaction ownership và trạng thái nghiệp vụ.
- [ ] Test production-like có broker/client versions tương thích.
- [ ] Không dùng test single-broker làm bằng chứng cluster failover/durability.

## 27. Kết luận

**Producer fencing là tính năng bảo vệ Kafka transactions, không chỉ là một exception cần che đi.** Khi hai producers dùng chung `transactional.id`, coordinator chỉ cho thế hệ hiện hành thao tác với transactional state; producer cũ mất quyền và phải dừng.

Thí nghiệm cốt lõi rất rõ:

```text
A init + begin + send (chưa commit)
B init với cùng transactional.id
B begin + send + commit thành công
A commit -> ProducerFencedException

read_committed -> chỉ thấy bản ghi đã commit của B
```

Từ đây, hệ thống Spring Kafka cần thêm quy tắc vận hành: **transactional ID không collision giữa những owners đang hoạt động**, failover phải có ownership rõ ràng, producer bị fence không được tái sử dụng, còn các side effects bên ngoài Kafka phải có idempotency và reconciliation.

Khi mô phỏng được fencing và giải thích được record nào visible/aborted, người vận hành sẽ phân biệt được **fencing đúng mong đợi khi failover** với **fencing storm do cấu hình sai**, từ đó xử lý sự cố mà không vô tình tạo thêm duplicate business effects.

## 28. Tài liệu tham khảo

- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): `transactional.id`, idempotence, acks, timeout.
- [Apache Kafka — Design: Transactions](https://kafka.apache.org/documentation/#transactions): transactional producers, fencing và consumer visibility.
- [KafkaProducer Javadoc](https://kafka.apache.org/37/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html): `initTransactions`, `beginTransaction`, `commitTransaction`, `abortTransaction`.
- [Kafka ProducerFencedException Javadoc](https://kafka.apache.org/37/javadoc/org/apache/kafka/common/errors/ProducerFencedException.html): ý nghĩa lỗi producer fencing.
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): `KafkaTransactionManager`, `DefaultKafkaProducerFactory` và transaction ID prefix.
- [Spring Kafka — Testing](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `EmbeddedKafkaBroker`.
- [Spring Boot — Apache Kafka](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): auto-configuration và Kafka transaction properties.
- [Testcontainers Kafka Module](https://java.testcontainers.org/modules/kafka/): broker thật trong Docker.
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): `isolation.level=read_committed`.
