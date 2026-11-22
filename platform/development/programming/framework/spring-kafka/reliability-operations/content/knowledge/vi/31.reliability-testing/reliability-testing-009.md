# Test exactly once flow trong Spring Kafka Reliability Operations

Trong một ứng dụng dùng Spring Kafka, consumer nhận sự kiện thanh toán, tính toán kết quả và xuất sự kiện sang topic khác. Khi process bị lỗi **sau khi gửi output nhưng trước khi hoàn tất xử lý**, chuyện gì xảy ra? Consumer có đọc lại input không? Output có xuất hiện hai lần không? Offset của consumer group có bị commit dù output bị rollback không?

Đó là những câu hỏi phải trả lời bằng **integration test của exactly-once flow**. Một unit test chỉ kiểm tra `KafkaTemplate.send(...)` được gọi một lần không đủ chứng minh tính đúng đắn, vì lỗi thường nằm tại ranh giới **Kafka transaction, producer output, consumer offset và broker commit**.

Bài học thuộc **Spring Kafka Reliability Operations → Kiểm thử tin cậy**, tập trung vào luồng **Kafka input → xử lý → Kafka output** được quản lý bằng transaction của Spring Kafka. Ta sẽ xây dựng cấu hình, test có broker, cố ý gây lỗi giữa chừng, kiểm tra output mà consumer `read_committed` thực sự nhìn thấy, kiểm tra offset đã commit, rồi mở rộng sang tình huống retry, restart, fencing và ghi dữ liệu ngoài Kafka.

Ví dụ Java lấy **Spring Boot 3.x, Spring Kafka 3.x, Apache Kafka 3.x và Java 17** làm mốc. Khi dùng Spring Kafka 4.x hoặc Spring Boot 4.x, cần đối chiếu chữ ký API, phiên bản Kafka client và cấu hình tương thích; nguyên tắc giao dịch Kafka vẫn là nền tảng.

## 1. “Exactly once” thực sự bảo đảm điều gì?

Nói “consumer xử lý đúng một lần” dễ gây hiểu nhầm. Trong Spring Kafka, **exactly-once semantics (EOS)** của giao dịch Kafka nhằm bảo đảm kết quả **read → process → write** được ghi nhận nhất quán: **các record xuất ra Kafka và consumer offsets được commit trong cùng một Kafka transaction**.

Điều đó **không** có nghĩa phương thức listener hoặc code nghiệp vụ chỉ chạy đúng một lần. Khi transaction rollback, Kafka có thể giao lại cùng input để listener chạy lần nữa.

| Khía cạnh | Điều có thể xảy ra khi dùng Kafka EOS | Có được bảo đảm “chỉ một lần” không? |
| --- | --- | --- |
| Listener được gọi | Có thể được gọi nhiều lần với cùng input sau rollback | **Không** — phần đọc/xử lý có tính chất at-least-once |
| Gửi output trong transaction đã abort | Record có thể tồn tại vật lý trong log nhưng bị consumer `read_committed` che khỏi kết quả quan sát | **Không được coi là output đã commit** |
| Kafka output của transaction thành công | Record thành công được hiển thị cho consumer `read_committed` | **Có**, trong phạm vi kết quả Kafka transaction của luồng thiết kế đúng |
| Offset input của consumer group | Được đưa vào transaction cùng output; rollback không commit offset đó | **Có**, cùng ranh giới commit của Kafka transaction |
| Ghi database riêng, gọi REST, gửi email | Có thể đã tạo side effect dù Kafka transaction rollback | **Không**, Kafka EOS không tự bao phủ hệ thống ngoài Kafka |
| Hai input khác nhau nhưng trùng business ID | Hai bản ghi vẫn có thể được xử lý như hai input hợp lệ | **Không** tự deduplicate theo khóa nghiệp vụ |

Ví dụ mong muốn:

```text
input topic: orders.in
    offset 42: {"orderId":"O-42","status":"PAID"}
          |
          v
  @KafkaListener xử lý
          |
          +--> KafkaTemplate.send("orders.out", ...)
          |
          +--> ghi nhận offset input 43 trong cùng transaction
          |
          v
   COMMIT Kafka transaction
          |
          v
read_committed consumer nhìn thấy 1 output
group offset sau commit = 43
```

Khi lỗi xảy ra trước commit:

```text
Lần thử 1:
  đọc offset 42
  gửi output vào Kafka transaction T1
  listener ném exception
  ABORT T1 --> output không hiện với read_committed
                offset 43 không được commit

Lần thử 2:
  đọc lại offset 42
  gửi output vào Kafka transaction T2
  listener thành công
  COMMIT T2 --> output được nhìn thấy
                offset 43 được commit
```

**Tiêu chí kiểm thử quan trọng:** listener đã thực thi lại, nhưng người tiêu thụ `read_committed` chỉ quan sát **một kết quả Kafka đã commit**, và consumer group đã tiến đến offset thích hợp. Không thể kết luận EOS chỉ từ `attemptCount == 1`; trên thực tế test rollback có thể kỳ vọng `attemptCount >= 2`.

## 2. So sánh at-most-once, at-least-once và Kafka exactly-once

| Chiến lược | Cách thực hiện điển hình | Rủi ro sau crash | Test cần xác nhận |
| --- | --- | --- | --- |
| **At-most-once** | Commit offset trước khi xử lý/output thành công | Có thể mất kết quả nếu process chết sau commit offset | Có thể mất item; không kỳ vọng replay |
| **At-least-once** | Xử lý/gửi output rồi commit offset riêng | Có thể có output trùng nếu crash trước offset commit | Có replay, writer/consumer sau cần dedup |
| **Kafka exactly-once read–process–write** | Kafka output và consumed offsets chung một transaction | Listener có thể replay nhưng aborted output không hiển thị với `read_committed` | Kết quả đã commit duy nhất, offset nhất quán và không rò aborted record |

Kafka EOS không ngăn một producer hoặc client khác **chủ động gửi cùng payload hai lần** trong hai transaction đã commit. Nó cũng không quyết định “một đơn hàng phải chỉ được thanh toán một lần” theo business key. Đó là ràng buộc nghiệp vụ, cần unique key/idempotency/dedup riêng.

Vì thế hãy đặt tên rõ cho hai lớp kiểm thử:

- **Transactional EOS test:** output Kafka và input offset có commit/rollback cùng nhau hay không?
- **Business idempotency test:** nếu hai input khác nhau mang cùng `orderId`, kết quả nghiệp vụ có bị nhân đôi không?

Bài này ưu tiên test đầu tiên, sau đó nêu cách bổ sung test thứ hai.

## 3. Spring Kafka triển khai read–process–write transaction

Khi listener container được cấu hình với `KafkaAwareTransactionManager` (trong Spring Kafka 3.x thường là `KafkaTransactionManager`), container mở Kafka transaction **trước khi gọi listener**.

Luồng thành công:

```text
KafkaMessageListenerContainer
        |
        v
BEGIN Kafka transaction
        |
        v
Consumer.poll() / record đến listener
        |
        v
@KafkaListener
    KafkaTemplate.send(output)
        |
        v
Listener trả về bình thường
        |
        v
sendOffsetsToTransaction(
    next consumed offset,
    consumer group metadata
)
        |
        v
COMMIT Kafka transaction
        |
        +--> output hiển thị cho read_committed
        |
        +--> consumer group offset được commit
```

Luồng thất bại:

```text
BEGIN Kafka transaction
      |
      v
@KafkaListener
      |
      +--> send output
      +--> throw RuntimeException
      |
      v
ABORT Kafka transaction
      |
      +--> output không hiển thị cho read_committed
      +--> offset không được commit trong transaction đó
      |
      v
AfterRollbackProcessor / seek / replay
      |
      v
Cùng input có thể được đọc lại
```

Trong Spring Kafka 3.x, **`EOSMode.V2` là chế độ EOS được hỗ trợ**, sử dụng cơ chế phối hợp group metadata và producer để broker fencing phù hợp. Hệ thống cần broker Kafka có hỗ trợ giao thức liên quan (Kafka broker **2.5+** cho EOS V2 theo tài liệu của Spring Kafka 3.x); trong triển khai mới nên chọn broker/client version được hỗ trợ bởi bộ phiên bản hiện tại của dự án.

Các điều kiện cốt lõi:

1. Producer có **`transactional.id`**, thường qua `transactionIdPrefix` của producer factory.
2. Listener container chạy bằng **Kafka transaction manager** thực sự, không chỉ có một `KafkaTemplate` transactional nhưng container vẫn commit offsets theo đường khác.
3. `enable.auto.commit=false` cho consumer; để container quản lý offsets.
4. Consumer downstream dùng **`isolation.level=read_committed`** nếu muốn không thấy output của transaction bị abort.
5. Output được gửi **trong transaction của listener**, không thông qua một producer khác nằm ngoài transaction.
6. Exception làm transaction rollback phải **được phép lan ra ngoài listener** theo cơ chế xử lý lỗi đã thiết kế.
7. Mỗi application instance đang chạy đồng thời phải có **transaction ID prefix riêng**, tránh producer fencing ngoài ý muốn.

## 4. Cấu hình Spring Boot cho Kafka transaction

Ví dụ `application.yml` dành cho môi trường có Kafka broker:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    consumer:
      group-id: orders-eos-v1
      enable-auto-commit: false
      auto-offset-reset: earliest
      isolation-level: read_committed
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      transaction-id-prefix: "orders-eos-${HOSTNAME:local}-"

app:
  kafka:
    topics:
      input: orders.in
      output: orders.out
```

Với **Spring Boot 3.x**, khi cấu hình `spring.kafka.producer.transaction-id-prefix` và hạ tầng auto-configuration phù hợp, Boot tạo `KafkaTransactionManager` và kết nối nó với listener container factory do Boot quản lý. Nếu dự án tự tạo `ConcurrentKafkaListenerContainerFactory` hoặc producer factory, cần **xác nhận chính bean mà listener sử dụng thật sự được cấu hình transaction manager**; một property trong YAML không đảm bảo các factory tự viết đã dùng nó.

Ý nghĩa của các thuộc tính:

| Thuộc tính | Lý do |
| --- | --- |
| `transaction-id-prefix` | Bật producer transaction; factory cấp các `transactional.id` cụ thể |
| `enable-auto-commit=false` | Không để Kafka consumer tự commit offset ngoài flow |
| `isolation-level=read_committed` | Input từ producer transactional chỉ thấy record đã commit |
| `auto-offset-reset=earliest` | Khi group mới không có offset, đọc từ đầu để không lỡ test/luồng mới |
| `group-id` | Định danh consumer group; offset commit nằm theo topic/partition/group |
| `key/value serializer` | Producer ghi dữ liệu đúng định dạng |
| `key/value deserializer` | Consumer đọc đúng định dạng |

**Không copy `transaction-id-prefix: orders-eos-local-` nguyên xi cho nhiều pod production.** Spring Kafka yêu cầu prefix khác nhau giữa các instance chạy đồng thời. Có thể inject ID pod/instance phù hợp từ hạ tầng deploy. Chọn prefix có ý nghĩa nhưng không lộ bí mật hoặc dữ liệu nhạy cảm.

### Dùng cấu hình Gradle tối thiểu

Với ứng dụng Spring Boot dùng BOM/plugin quản lý phiên bản:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tùy dự án, dependency Spring Kafka cũng có thể được thêm thông qua starter hoặc platform nội bộ. Quan trọng là **version Spring Boot, Spring Kafka, Kafka client và broker tương thích**. `spring-kafka-test` mang công cụ `@EmbeddedKafka`, `KafkaTestUtils` và các lớp phục vụ test với broker; mock `KafkaTemplate` không thay thế được transaction broker.

## 5. Listener nghiệp vụ cho luồng Kafka → Kafka

Một ứng dụng đơn giản nhận một order event dạng text và ghi kết quả sang topic khác:

```java
package com.example.eos;

import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderForwardingListener {

    private final KafkaTemplate<String, String> template;
    private final String outputTopic;

    public OrderForwardingListener(
            KafkaTemplate<String, String> template,
            @Value("${app.kafka.topics.output}") String outputTopic) {
        this.template = template;
        this.outputTopic = outputTopic;
    }

    @KafkaListener(topics = "${app.kafka.topics.input}")
    public void onOrder(ConsumerRecord<String, String> input)
            throws Exception {

        String output = "processed:" + input.value();

        // Send tham gia transaction của listener container
        // khi container được cấu hình KafkaTransactionManager.
        template.send(outputTopic, input.key(), output)
                .get(10, TimeUnit.SECONDS);
    }
}
```

Đoạn ví dụ gọi `get(...)` nhằm thấy lỗi producer ngay trong một phương thức minh họa; đây **không phải yêu cầu bắt buộc** cho mọi listener. Khi dùng Kafka transaction, framework sẽ chờ các send cần thiết khi kết thúc transaction; trong ứng dụng throughput cao có thể gửi bất đồng bộ và xử lý lỗi bằng transaction đúng cách. Dù chọn phương thức nào, **đừng coi `send()` trả về future là dấu hiệu transaction đã commit**.

Không nên gọi `template.executeInTransaction(...)` bên trong listener container **nếu mục tiêu là gửi output trong chính transaction do container mở**. Phương thức đó có thể tạo **Kafka transaction riêng**, khiến output và offset không còn thuộc ranh giới commit như dự định. `executeInTransaction` phù hợp cho các thao tác producer-initiated bên ngoài listener, chẳng hạn gửi input test.

Đừng gọi `consumer.commitSync()` thủ công trong listener transactional. Offsets cần được gửi vào **transaction của producer** thông qua container; commit consumer riêng phá vỡ khả năng kiểm thử tính nguyên tử output-offset.

## 6. Test chính: lỗi sau khi gửi output nhưng trước commit

Đây là test quan trọng nhất trong bài. Ta muốn kiểm chứng sự cố tại **khoảng thời gian nguy hiểm**:

```text
read input
   |
process
   |
send output (broker đã nhận record trong transaction)
   |
   X  <-- cố ý ném exception tại đây
   |
send offsets + commit  (lần 1 không được đi đến đây)
```

Nếu transaction đúng:

- **Lần thử đầu** đọc input, gửi output rồi ném exception. Kafka transaction **abort**.
- **Lần thử sau** nhận lại input, gửi output và hoàn tất. Transaction **commit**.
- Consumer `read_committed` thấy **đúng một output**.
- Offset của group tiến đến **vị trí tiếp theo** sau input đã xử lý; lần đầu bị rollback không làm group offset tiến.
- Listener có thể chạy **hai lần** (hoặc nhiều hơn nếu lỗi môi trường), và điều này **không mâu thuẫn** với Kafka EOS.

### 6.1. Broker tích hợp với `@EmbeddedKafka`

Test cần broker hỗ trợ transaction. Với broker đơn để chạy test, Kafka yêu cầu giảm replication factor của internal transaction state topic xuống 1 và ISR tối thiểu xuống 1:

```java
@EmbeddedKafka(
    partitions = 1,
    topics = { "eos.it.input", "eos.it.output" },
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1",
        "offsets.topic.replication.factor=1"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

Đây là **cấu hình chỉ dành cho broker một node trong test**. Không sao chép `transaction.state.log.replication.factor=1` vào Kafka cluster production nhiều broker; độ bền giao dịch trong production cần replication, ISR và availability phù hợp.

### 6.2. Integration test đầy đủ

File ví dụ `src/test/java/com/example/eos/EosFlowIT.java`:

```java
package com.example.eos;

import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = EosFlowIT.TestApplication.class,
    properties = {
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.isolation-level=read_committed",
        "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.transaction-id-prefix=eos-it-tx-",
        "spring.kafka.consumer.group-id=eos-it-workers"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = { "eos.it.input", "eos.it.output" },
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1",
        "offsets.topic.replication.factor=1"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class EosFlowIT {

    private static final String INPUT = "eos.it.input";
    private static final String OUTPUT = "eos.it.output";
    private static final String GROUP = "eos-it-workers";

    @Autowired
    KafkaTemplate<String, String> template;

    @Autowired
    EmbeddedKafkaBroker broker;

    @Autowired
    FailingOnceForwarder forwarder;

    @Test
    void abortedOutputIsInvisibleAndOffsetCommitsWithSuccess()
            throws Exception {

        // Gửi INPUT bằng Kafka transaction độc lập trong test.
        // KafkaTemplate đã bật transaction nên không dùng send()
        // ngoài transaction.
        template.executeInTransaction(operations -> {
            try {
                operations.send(INPUT, "order-42", "paid")
                        .get(10, TimeUnit.SECONDS);
            } catch (Exception ex) {
                throw new IllegalStateException(
                        "Cannot prepare test input", ex);
            }
            return null;
        });

        Map<String, Object> observerProps =
                consumerProperties(
                        "eos-output-observer-" + UUID.randomUUID());
        observerProps.put(
                ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");

        try (Consumer<String, String> observer =
                     new DefaultKafkaConsumerFactory<String, String>(
                             observerProps).createConsumer()) {

            // Gán topic và seek về đầu để quan sát cả lịch sử
            // output; record aborted vẫn bị read_committed che.
            broker.consumeFromAnEmbeddedTopic(observer, OUTPUT);

            ConsumerRecord<String, String> output =
                    KafkaTestUtils.getSingleRecord(
                            observer, OUTPUT, Duration.ofSeconds(30));

            assertEquals("order-42", output.key());
            assertEquals("processed:paid", output.value());

            // Chỉ kỳ vọng một output đã commit trong test case này.
            assertEquals(0,
                    observer.poll(Duration.ofSeconds(2)).count());
        }

        // Lần đầu đã throw và rollback; input được nhận lại.
        assertTrue(forwarder.attempts.get() >= 2);

        // Chứng minh consumer group offset được commit sau
        // transaction thành công, không chỉ nhìn output.
        Map<String, Object> groupProps =
                consumerProperties(GROUP);

        TopicPartition inputPartition =
                new TopicPartition(INPUT, 0);

        try (Consumer<String, String> groupInspector =
                     new DefaultKafkaConsumerFactory<String, String>(
                             groupProps).createConsumer()) {

            var offsets = groupInspector.committed(
                    Set.of(inputPartition), Duration.ofSeconds(10));

            assertNotNull(offsets.get(inputPartition));
            assertEquals(1L,
                    offsets.get(inputPartition).offset());
        }
    }

    private Map<String, Object> consumerProperties(String groupId) {
        Map<String, Object> props =
                KafkaTestUtils.consumerProps(groupId, "false", broker);
        props.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        return props;
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class TestApplication {

        @Bean
        FailingOnceForwarder forwarder(
                KafkaTemplate<String, String> template) {
            return new FailingOnceForwarder(template);
        }
    }

    static class FailingOnceForwarder {

        private final KafkaTemplate<String, String> template;
        final AtomicBoolean failFirst = new AtomicBoolean(true);
        final AtomicInteger attempts = new AtomicInteger();

        FailingOnceForwarder(
                KafkaTemplate<String, String> template) {
            this.template = template;
        }

        @KafkaListener(
            topics = INPUT,
            groupId = GROUP
        )
        public void handle(ConsumerRecord<String, String> input)
                throws Exception {

            attempts.incrementAndGet();

            // Chờ broker ack record để failure injection thật sự
            // nằm SAU một send thành công nhưng TRƯỚC commit.
            template.send(
                    OUTPUT,
                    input.key(),
                    "processed:" + input.value())
                    .get(10, TimeUnit.SECONDS);

            if (failFirst.compareAndSet(true, false)) {
                throw new IllegalStateException(
                        "Injected failure before transaction commit");
            }
        }
    }
}
```

**Ý nghĩa của từng mốc trong test:**

1. `@SpringBootTest` khởi tạo Kafka auto-configuration và listener container thật, không mock `KafkaTemplate` hay `JobRepository`.
2. `@EmbeddedKafka` chạy Kafka broker phục vụ test và ánh xạ bootstrap server vào Spring Boot.
3. `transaction-id-prefix` kích hoạt Kafka producer transaction; listener container được cấu hình dùng transaction manager do Boot tạo.
4. `FailingOnceForwarder` gửi output và **chờ broker xác nhận send** trước khi cố ý ném lỗi.
5. Lỗi đi ra khỏi listener làm transaction thứ nhất **rollback**; after-rollback behavior cho phép nhận lại input.
6. Lần thứ hai hoàn tất; output và consumed offset được commit.
7. Observer riêng sử dụng `read_committed`, không thể nhìn thấy output thuộc transaction bị abort.
8. Truy vấn committed offset của **chính consumer group xử lý**; với topic mới và một record ở partition 0 offset 0, expected committed offset là **1**, tức vị trí kế tiếp.

Ở test suite có nhiều test chạy song song, nên tạo **topic, consumer group và transaction ID prefix riêng cho mỗi test context** để không dùng chung state. Ví dụ trên cố ý chỉ có **một test case và một broker riêng**, giúp kết quả đầu vào có offset 0. Nếu project dùng broker dùng chung hoặc có dữ liệu cũ, **không hardcode offset 1**; phải ghi nhớ offset của input do producer tạo và assert `committed == input.offset() + 1` theo partition tương ứng.

### 6.3. Vì sao cần kiểm tra cả offset?

Giả sử test chỉ assert consumer output nhận đúng một record. Lỗi cấu hình có thể khiến output commit thành công nhưng input offset **chưa commit**. Sau khi consumer restart, nó nhận lại input và có thể tạo output thứ hai. Output “đúng một record tại thời điểm T” chưa đủ chứng minh offset và output đã đi qua cùng transaction.

Do đó, một test đáng tin nên quan sát **cả hai phía**:

```text
Given: INPUT offset 0, group eos-it-workers

Failure lần 1:
  listener attempts >= 1
  Kafka transaction ABORT
  không có output committed từ lần 1
  group offset chưa tiến lên 1 vì lần 1

Success lần 2:
  listener attempts >= 2
  Kafka transaction COMMIT
  read_committed output count == 1
  group committed offset == 1
```

Test trên quan sát group offset **sau lần thành công**. Để chứng minh trực tiếp trạng thái sau rollback và trước retry, cần bổ sung điểm đồng bộ có kiểm soát (chẳng hạn latch trong môi trường test hoặc tạm dừng listener sau failure) rồi query offset ở thời điểm trung gian. Không nên dùng `Thread.sleep` tùy tiện và suy đoán timing: điều kiện đồng bộ cần phản ánh đúng mốc transaction đã rollback.

## 7. Trạng thái transaction: `read_committed` và `read_uncommitted`

Một output producer có thể đã được broker append vào partition log nhưng transaction cuối cùng **abort**. Consumer với `read_uncommitted` có thể đọc record đó; consumer với `read_committed` **không nhận** record đã abort.

```text
Output topic vật lý:
  offset 0  -> record của T1  [ABORTED]
  offset 1  -> control marker T1
  offset 2  -> record của T2  [COMMITTED]
  offset 3  -> control marker T2

read_committed consumer:
  chỉ nhìn thấy record của T2

read_uncommitted consumer:
  có thể nhìn thấy record của T1 và T2
```

Các offset trên chỉ **minh họa**; Kafka control batches và cách sinh offset thực tế phụ thuộc broker/transaction. Không được suy luận rằng “hai input/output business events” là “hai offset liên tiếp” khi log có transaction markers hoặc record aborted.

**Test dễ bị false negative:** nếu observer dùng mặc định `read_uncommitted`, nó có thể báo output trùng và khiến nhóm phát triển kết luận EOS lỗi, trong khi hệ thống downstream production dùng `read_committed` sẽ chỉ thấy output đã commit.

**Test dễ bị false positive:** nếu observer chỉ đọc record mới nhất (`auto.offset.reset=latest`) hoặc poll quá sớm, nó có thể không thấy aborted output cũng như committed output; cần setup consumer topic/offset rõ ràng, kiểm tra chính xác record kỳ vọng rồi xác nhận không có record committed dư.

Tạo hai observer có isolation khác nhau là một phép thử giáo dục hữu ích, nhưng assertion chuẩn của Kafka EOS phải dựa trên **`read_committed`**.

## 8. Kịch bản kiểm thử failure injection khác nhau

Test ở mục 6 tập trung vào điểm khó nhất: **output đã được gửi trong transaction nhưng commit chưa xảy ra**. Một bộ integration test đầy đủ nên có ma trận tình huống sau:

| Điểm lỗi | Dự kiến Kafka transaction/offset | Assertion chính |
| --- | --- | --- |
| Trước khi listener bắt đầu xử lý | Chưa có output; offset chưa tiến | Sau phục hồi, input vẫn được xử lý |
| Sau xử lý nghiệp vụ, trước `KafkaTemplate.send` | Abort, không có output mới, offset không commit | Replay input rồi tạo một output committed |
| **Sau broker ack output, trước commit** | **Output T1 aborted, offset không commit** | `read_committed` thấy một output của T2 sau replay |
| Trong lúc commit, kết quả commit không rõ | Phải xác minh Kafka transaction outcome qua consumer/offset, không đoán | Không tạo business output trùng khi recover |
| Sau commit Kafka, trước khi logger/HTTP caller nhận thông báo | Output và offset đã commit | Restart/rebalance không xử lý lại input từ offset cũ |
| Rebalance giữa xử lý | Transaction/offset phải gắn group generation hợp lệ | Không commit stale offsets; không nhân đôi output |
| Producer bị fencing | Transaction không được commit bởi producer cũ | Đảm bảo instance thay thế hoạt động an toàn |
| Consumer process bị kill | Transaction đang dở sẽ abort/timeout theo broker | Group kế tiếp replay input và commit một kết quả |
| Poison pill lỗi liên tục | Nhiều lần rollback, cuối cùng policy quyết định recover/DLT/fail | Không lặng lẽ commit offset mà mất message |
| Hai input khác nhau trùng `businessId` | Kafka có thể commit hai output tương ứng | Business dedup phải được test riêng |
| Writer ghi database rồi Kafka rollback | DB side effect có thể đã commit | Outbox/inbox/idempotency bảo đảm an toàn |

Với mỗi case, nên ghi rõ **transaction nào kỳ vọng commit**, **offset nào phải tiến**, **topic nào cần quan sát**, **số lần listener có thể chạy**, và **kết quả nghiệp vụ**. Đừng tạo một assertion chung “listener gọi đúng một lần” cho mọi failure: nó không phản ánh thiết kế transactional consume.

## 9. Test crash/restart thật thay vì chỉ ném exception

Ném exception từ listener giúp test rollback, nhưng chưa hoàn toàn mô phỏng **JVM bị kill giữa transaction**. Để kiểm tra restart thực tế:

1. Chạy một consumer application như **process/container riêng**, với transactional producer và group `eos-test-group`.
2. Tạo input record có ID/offset xác định.
3. Điều khiển ứng dụng xử lý đến điểm **producer send ack nhưng transaction chưa commit**. Dùng barrier/latch hoặc endpoint test-only để dừng ở mốc chính xác.
4. Kill process/container một cách cưỡng bức tại điểm đó; đừng chỉ gọi graceful shutdown nếu cần mô phỏng crash.
5. Khởi động application instance mới dùng **cùng consumer group**, transaction ID prefix **khác instance đồng thời**, cấu hình broker/repository giữ nguyên.
6. Đợi broker phát hiện/giải quyết transaction cũ và consumer group tiếp nhận partition.
7. Query output bằng `read_committed` và query committed offset của group.
8. Assert **một kết quả committed** và offset đã tiến tới sau input; không chấp nhận output trùng.

**Không nhầm “kill process” với “broker transaction lập tức abort trong cùng một mili giây”.** Kafka transaction có thể ở trạng thái open cho tới khi timeout/fencing/recovery; một `read_committed` consumer có thể bị chặn bởi last stable offset cho tới khi broker xác định kết quả transaction. Test phải có timeout phù hợp và quan sát trạng thái thay vì kết luận “không có record” khi transaction cũ chưa được giải quyết.

Để điều khiển thời điểm crash chính xác, có thể dùng Testcontainers, một ứng dụng test-only với latch hoặc một hook fault injection. **Không để endpoint crash/fault injection tồn tại trong môi trường production**.

## 10. Kiểm tra producer fencing và transactional ID

Kafka producer transactional dùng `transactional.id` để liên kết phiên giao dịch với broker. Nếu một producer mới dùng cùng transactional ID, producer cũ có thể bị **fenced**: nó không còn quyền commit transaction với epoch cũ. Đây là một phần quan trọng của cơ chế tránh zombie producer.

Trong Spring Kafka 3.x, `DefaultKafkaProducerFactory` tạo các transactional producers dựa trên `transactionIdPrefix + suffix`. Từ Spring Kafka 3.2 có cơ chế quản lý suffix và cache; nếu cấu hình giới hạn cache quá thấp so với concurrency, có thể gặp `NoProducerAvailableException`.

Các tình huống cần test:

- Hai **instance chạy đồng thời** cố ý dùng **cùng transaction ID prefix**: quan sát rủi ro fencing, sau đó sửa thành prefix duy nhất.
- Một consumer cũ bị pause lâu rồi bị thay thế/rebalance: không được commit offset cũ bằng metadata consumer group đã hết hiệu lực.
- Transaction timeout hoặc producer idle quá lâu: đảm bảo lỗi được quan sát và luồng có thể phục hồi theo runbook.
- Concurrency của listener tăng từ 1 lên N: bảo đảm producer pool/cache và transaction prefix đáp ứng số giao dịch đồng thời.

**Không dùng một transactional.id cố định cho mọi partition và mọi pod.** Đồng thời, không tùy tiện khởi động nhiều producer có cùng ID rồi cho rằng Kafka sẽ “cân bằng tải”; fencing có thể làm luồng thất bại liên tục.

Bài test EOS cơ bản phải xác nhận tính nguyên tử; test fencing bổ sung nhằm kiểm tra **hành vi khi ownership thay đổi**, một vấn đề xuất hiện rõ trong production cluster.

## 11. Batch listener, record listener và ranh giới commit

Spring Kafka có record listener và batch listener. Khi dùng transaction, container đưa offsets đã xử lý vào transaction trước commit; phạm vi transaction có thể gắn với **một record** hoặc **một batch records**, theo loại listener/container.

Với **record listener** trong ví dụ:
 
```text
Input record R1 -> Kafka transaction T1
Input record R2 -> Kafka transaction T2
...
```

Với **batch listener**, một transaction có thể bao gồm cả batch record mà listener xử lý:

```text
Poll: R1, R2, R3 -> listener xử lý batch
                        |
                   Kafka transaction
                        |
             +----------+-----------+
             |                      |
        all succeed           R2 throws
             |                      |
          COMMIT                  ABORT
             |                      |
       offsets progress       batch có thể replay
```

Nếu batch listener đã send output cho R1 rồi lỗi ở R2 trước commit, kết quả của batch transaction có thể bị abort **cùng nhau**, không chỉ riêng output của R2. Assertion “chỉ R2 được đọc lại” là không phù hợp trừ khi framework có cơ chế xử lý/seek riêng được cấu hình chính xác.

Với batch listener và poison pill, nên test đủ tình huống partial processing; dùng một test record listener không tự chứng minh semantics của batch listener.

### `AckMode` và manual ack

Ở các container không giao dịch, `AckMode.RECORD` và `AckMode.BATCH` quyết định cách commit consumer offsets. Trong container giao dịch, offset được gửi vào Kafka transaction theo semantics tương ứng với record/batch listener. **Không dùng manual consumer commit ngoài transaction** để “đẩy nhanh” offset; thao tác đó có thể phá ranh giới EOS.

## 12. Retry, after rollback và Dead Letter Topic

Một record có thể lỗi vĩnh viễn, chẳng hạn payload không hợp lệ. Nếu mỗi lần nhận đều throw, transaction sẽ rollback và record có thể bị replay nhiều lần. Spring Kafka có các cơ chế after-rollback/recoverer và DLT để tránh một poison pill chặn partition vô hạn.

Cần phân biệt:

| Kết quả | Kafka output topic chính | Input offset | DLT |
| --- | --- | --- | --- |
| Xử lý thành công | Commit output | Commit cùng transaction | Không cần |
| Xử lý lỗi, rollback để retry | Output trong transaction bị abort | Không commit offset của lần lỗi | Chưa chuyển |
| Retry hết, chính sách đưa tới DLT | Không có output nghiệp vụ thành công | Được commit/đánh dấu recovered theo transaction policy | Một record lỗi được ghi vào DLT khi recoverer thành công |
| Recoverer/DLT publish lỗi | Không được âm thầm đánh dấu input hoàn tất | Cần fail/retry theo policy | DLT chưa nhận record |

Spring Kafka có `DefaultAfterRollbackProcessor` và `DeadLetterPublishingRecoverer`. Với listener transactional, phải kiểm tra chính xác cấu hình xử lý sau rollback, thời điểm publish DLT và việc **commit recovered offset**. Một cấu hình cho phép recovery có thể dùng KafkaTemplate transactional và `commitRecovered` trong after-rollback processor tương ứng, nhưng cần dựng đúng theo API/version và test thực tế.

**Không coi DLT là bằng chứng exactly-once một cách tự động.** Test phải kiểm tra:

1. Record sai đã trải qua số lần thử theo retry policy.
2. Output chính **không** có kết quả sai hoặc kết quả abort bị lộ.
3. DLT chứa record lỗi có correlation/topic/partition/offset ban đầu đủ điều tra.
4. Offset input được xử lý theo chính sách recover một cách có chủ đích.
5. Nếu DLT send thất bại, record không bị “mất” chỉ vì handler nuốt exception.

Một bẫy khác: listener bắt `Exception` rồi chỉ log và **return bình thường**. Container có thể coi xử lý đã thành công và commit transaction/offset, dù code chưa tạo output hợp lệ. Khi muốn rollback, exception phải được đưa đến cơ chế error handler/transaction manager theo hợp đồng; không nuốt lỗi rồi mặc nhiên kỳ vọng Kafka sẽ replay.

## 13. Kafka EOS không tự bảo đảm exactly once với database

Một lỗi thiết kế rất phổ biến là dùng transaction Kafka và mặc định suy ra DB cũng thuộc cùng giao dịch.

Ví dụ:

```text
@KafkaListener
     |
     +--> UPDATE orders SET processed=true ...  (DB commit)
     |
     +--> KafkaTemplate.send("orders.out", ...)
     |
     +--> Kafka transaction ABORT
```

Dù output Kafka bị abort và input replay, **database có thể đã commit** thay đổi. Nếu processing lần sau gọi một side effect không idempotent (trừ tiền, tăng counter, gửi email), nghiệp vụ bị lặp.

| Tài nguyên | Kafka transaction mặc định có bao phủ không? |
| --- | --- |
| Output records gửi qua producer tham gia transaction | **Có** |
| Consumer offsets được container đưa vào cùng transaction | **Có** |
| Bảng SQL qua transaction manager riêng | **Không tự động** |
| REST API, email, payment gateway | **Không** |
| File trên object storage | **Không** |
| Một Kafka producer khác không tham gia transaction | **Không** |

Spring Kafka có thể đồng bộ transaction Kafka với transaction manager khác ở mức ứng dụng, nhưng **transaction synchronization không tự biến DB và Kafka thành một distributed ACID transaction nguyên tử**. Một transaction có thể commit trước rồi transaction còn lại fail. Vì vậy, cần test crash window giữa các commit.

### Những chiến lược thường gặp

- **Idempotent consumer:** xử lý input theo `eventId`/`businessId` trong database với unique constraint, đảm bảo replay không tạo cùng side effect hai lần.
- **Inbox/dedup table:** lưu ID message đã xử lý và cập nhật nghiệp vụ **trong cùng DB transaction**.
- **Transactional outbox:** cập nhật domain data và ghi outbox row trong **cùng DB transaction**, rồi một publisher riêng đưa outbox event lên Kafka. Publisher có thể gửi lại nên downstream vẫn cần idempotency.
- **Saga/compensation:** xử lý các bước nghiệp vụ phân tán với khả năng bù trừ rõ ràng.
- **Idempotency key ở hệ thống đích:** khi gọi API thanh toán hoặc gửi yêu cầu ra ngoài, hệ thống đích phải nhận diện cùng yêu cầu và không nhân đôi kết quả.

**Test cho DB + Kafka không được chỉ assert một record output Kafka.** Cần kiểm tra cả số dòng/giá trị nghiệp vụ thực trong database, unique key, trạng thái outbox và kết quả replay.

Ví dụ invariant mong muốn khi có hai lần giao một message:

```text
eventId = payment-event-42

Kafka input delivered twice
Listener invoked twice (hoặc nhiều hơn)
DB payment effects for eventId = đúng một
Published business outcome per eventId = đúng một
```

Invariant này đến từ **thiết kế idempotency**, không tự có vì bật Kafka transaction.

## 14. Test transaction ở đơn vị và test với broker: không thay thế nhau

Một unit test có thể có ích:

```java
@Test
void transformsOrderValue() {
    assertEquals(
            "processed:paid",
            OrderTransformer.transform("paid"));
}
```

Hoặc dùng Mockito xác nhận listener gọi `KafkaTemplate` với đúng key/value. Những test này kiểm tra **logic hoặc tương tác ở Java**, không chạy Kafka broker, do đó không thể chứng minh:

- Producer đã dùng transactional ID.
- Listener container thực sự mở transaction.
- `sendOffsetsToTransaction` được gọi đúng với group metadata.
- Broker commit/abort đúng.
- Consumer `read_committed` không thấy aborted record.
- Producer bị fencing trong điều kiện ownership thay đổi.
- Input được replay sau rollback theo Kafka offset thực.
- Rebalance/transaction timeout không gây mất dữ liệu.

Vì vậy phân lớp:

| Loại test | Mục đích | Không thể chứng minh |
| --- | --- | --- |
| Unit test transformer/service | Đúng logic chuyển đổi, validation, idempotency keys | Kafka transaction broker |
| Integration test `@EmbeddedKafka` | Output, offset, abort/commit với broker tích hợp | Mọi đặc tính của cluster production |
| Testcontainers Kafka | Broker chạy trong container, mô phỏng process/network gần production hơn | Không thay thế hoàn toàn multi-broker chaos |
| Integration test DB + Kafka | Consistency và idempotency qua hai tài nguyên | Chính xác mọi failure mode của cluster phân tán |
| Chaos/failure-injection test | Crash, rebalance, timeout, partition, producer fencing | Không thay thế kiểm thử business correctness |

## 15. Khi nào nên dùng Testcontainers thay `@EmbeddedKafka`?

`@EmbeddedKafka` phù hợp cho vòng lặp phát triển và CI nhanh khi muốn kiểm tra Kafka transaction thật trong một context Spring. Nhưng khi cần kiểm tra **transactional.id fencing qua restart**, network faults, broker version thực tế hoặc multi-container deployment, Testcontainers giúp kiểm soát process và môi trường sát production hơn.

Khung triển khai:

```text
@Testcontainers
  |
  +-- KafkaContainer (broker)
  +-- PostgreSQLContainer (nếu test DB side effects)
  |
  +-- @DynamicPropertySource
        spring.kafka.bootstrap-servers = kafka.getBootstrapServers()
  |
  +-- Spring Boot app/context hoặc app trong container riêng
        |
        +-- @KafkaListener transactional
        +-- KafkaTemplate transactional
  |
  +-- Producer test phát input
  +-- Consumer read_committed đọc output
  +-- Query consumer group committed offset
```

Cần dùng **module/API Testcontainers tương thích phiên bản dự án** (package của Kafka container có khác giữa các dòng Testcontainers). Với test kill JVM, app nên chạy dưới một process/container test riêng; `@SpringBootTest` chạy trong cùng JVM JUnit không thể kill toàn process mà vẫn giữ test runner để assert.

Đối với Kafka container **một broker**, internal transaction topic phải có cấu hình replication/min ISR cho phép giao dịch chạy. Trong cluster production nhiều broker, các giá trị này phải tuân thủ chính sách durability thực tế, không dùng mặc định test đơn node.

### Một lưu ý về độ ổn định của CI

Một test EOS dễ bị flaky nếu:

- Test suite tái sử dụng cùng topic/group từ run trước.
- Producer transactional ID bị chia sẻ với test chạy song song.
- Dùng `Thread.sleep(1000)` rồi assert record không tồn tại dù transaction chưa giải quyết.
- Test consumer bắt đầu ở `latest` sau khi output đã commit.
- Không đợi producer send ack trước khi chèn failure.
- Broker thiếu cấu hình internal transaction topic nên `initTransactions` bị timeout.
- Test context được cache nhưng bean `AtomicBoolean failFirst` không reset giữa test.
- Test chỉ đếm messages nhận được trong một poll thay vì đợi outcome ổn định.

Dùng **một topic/group/prefix riêng cho mỗi scenario**, timeout đủ cho Kafka transaction và cơ chế đồng bộ theo event/condition. Giữ dữ liệu expected theo key/id độc nhất để những record test khác không làm sai kết quả.

## 16. Quan sát và kiểm tra committed offset đúng cách

Đối với consumer group, committed offset của Kafka là **vị trí tiếp theo sẽ tiêu thụ**, không phải offset bản ghi vừa xử lý. Nếu input ở partition 2 offset 42 được xử lý và commit thành công, group offset thông thường sẽ là **43** trên partition 2.

Phải kiểm tra **đúng group ID và TopicPartition**:

```java
TopicPartition tp = new TopicPartition("orders.in", 2);

try (Consumer<String, String> inspector =
         consumerFactory.createConsumer()) {

    var committed = inspector.committed(
            Set.of(tp), Duration.ofSeconds(10));

    assertNotNull(committed.get(tp));
    assertEquals(43L, committed.get(tp).offset());
}
```

Mã là ví dụ trích từ test và giả định `consumerFactory` đã được cấu hình, cũng như input record thực sự có offset 42. Trong test ở mục 6, ta dùng topic mới, partition 0 và record đầu offset 0, nên expected là 1.

Kafka transaction control batches và aborted records có thể làm **vị trí log cuối cùng** khác số message nghiệp vụ quan sát. `read_committed` consumer có thể thấy lag khác dự kiến khi có transaction còn mở. Đừng dùng “log end offset tăng bao nhiêu” để thay thế đếm committed business outputs.

## 17. Các metrics và log cần cho test/reliability

Khi điều tra lỗi EOS, nên log hoặc quan sát:

| Trường hoặc metric | Vì sao cần |
| --- | --- |
| `eventId`/`businessKey` | Liên kết một công việc nghiệp vụ qua replay |
| `topic`, `partition`, `offset` | Định danh Kafka input thực tế |
| `consumerGroupId` | Xác định nơi commit consumed offset |
| `transactional.id` / instance ID được kiểm soát | Điều tra producer fencing và transaction identity |
| `attempt` / delivery attempt | Biết input có được xử lý lại không |
| `transaction begin/commit/abort` | Phân biệt output gửi thành công và output đã commit |
| `output topic/key` | Xác định kết quả Kafka |
| `ProducerFencedException`, timeout, commit error | Phân loại lỗi hạ tầng giao dịch |
| `DLT topic` và original offset | Điều tra poison pill đã recovery |

Không nên log full message payload, secret, thông tin khách hàng hoặc payment data trong trace. Với transaction ID, chỉ log giá trị theo chính sách vận hành, tránh vô tình đưa metadata môi trường nhạy cảm vào hệ thống logs công khai.

Khi thấy listener xử lý lại cùng record, **không tự kết luận EOS bị lỗi**. Hãy kiểm tra output visible với `read_committed`, committed offsets và transaction outcome. Ngược lại, nếu business side effect ngoài Kafka xuất hiện hai lần, đó là vấn đề idempotency/end-to-end consistency dù Kafka EOS có thể vẫn hoạt động đúng.

## 18. Chẩn đoán lỗi test thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng điều tra |
| --- | --- | --- |
| `TimeoutException` khi mở transaction ở Embedded Kafka | Broker một node chưa cấu hình internal transaction topic | Kiểm tra `transaction.state.log.replication.factor=1` và `min.isr=1` cho môi trường test |
| Test thấy hai output sau một rollback | Observer dùng `read_uncommitted`, hoặc output thật sự nằm ngoài transaction | Đọc bằng `read_committed`; kiểm tra transaction manager và producer |
| Không thấy output nào | Consumer bắt đầu từ `latest`, transaction chưa commit, listener chưa chạy | Kiểm tra bootstrap, group, offset start, listener startup |
| Listener được gọi hai lần | Rollback/replay bình thường | Kiểm tra chỉ **một output committed**, không assert chỉ một invocation |
| Output đúng một nhưng sau restart xử lý lại | Offset không được commit cùng transaction | Kiểm tra container transaction, group ID và committed offset |
| Transaction commit nhưng output không như kỳ vọng | `send()` ngoài transaction hoặc lỗi bị nuốt | Xác minh template/producers và exception handling |
| `ProducerFencedException` | Transaction ID trùng giữa instance, producer cũ hoặc epoch mismatch | Prefix riêng cho mỗi instance, kiểm tra redeploy/rebalance |
| `NoProducerAvailableException` | Pool/cache transactional producers thiếu dưới concurrency | Điều chỉnh suffix cache, concurrency, retry/backoff phù hợp |
| Poison pill làm partition đứng mãi | Không có recoverer/after-rollback policy đúng | Test retry exhaustion, DLT và recovered offset |
| DLT có record nhưng offset vẫn không tiến | DLT publishing và offset recovery không phối hợp đúng | Kiểm tra `DefaultAfterRollbackProcessor` và transactional recoverer |
| DB ghi hai lần dù Kafka output một lần | Kafka transaction không bao phủ DB | Inbox/outbox/idempotency và test DB side effect |
| Test pass máy dev, fail CI | Topic/group/prefix dùng chung, timing hoặc version broker khác | Isolate test, đồng bộ mốc transaction, fix compatibility |
| Test dùng mock KafkaTemplate vẫn báo EOS pass | Không có broker hay offset transaction thật | Thêm broker-backed integration test |
| Consumer lag không về 0 dù không có output mới | Transaction markers, open transaction, lag semantics | Quan sát committed offsets/LSO, không suy luận từ lag đơn lẻ |
| `@KafkaListener` bắt exception rồi return | Container có thể commit dù nghiệp vụ thất bại | Cho lỗi lan tới transaction rollback/error policy |
| Test kill JVM rồi không đọc được kết quả ngay | Broker chờ timeout/transaction resolution | Chờ kết quả có điều kiện, đặt timeout hợp lý |
| Nhiều partition nhưng assert offset chung | Offset là giá trị **theo partition** | Lưu key theo TopicPartition và compare đúng input offsets |

## 19. Bộ tiêu chí chấp nhận cho exactly-once flow

Trước khi coi một implementation Kafka EOS là đủ tin cậy, cần chứng minh bằng test ít nhất các yêu cầu:

1. **Cấu hình:** transactional producer và listener container transaction manager thực sự được bật; consumer auto-commit tắt.
2. **Happy path:** input duy nhất tạo output đúng, offset đúng partition/group được commit.
3. **Rollback window:** cố ý lỗi sau broker ack output nhưng trước transaction commit; output aborted không hiển thị với `read_committed`.
4. **Replay:** input được giao lại sau rollback, listener thực sự chạy lần sau.
5. **Committed output:** sau recovery chỉ một output committed cho input của scenario.
6. **Committed offset:** group tiến đến offset sau input đã xử lý; restart cùng group không phát lại từ offset cũ.
7. **Isolation:** test observer dùng `read_committed`, topic/group/transaction ID prefix tách biệt.
8. **Failure policy:** poison pill, retry exhaustion và DLT được xử lý mà không nuốt/mất message.
9. **Concurrency:** transaction ID prefix và producer pool hoạt động khi nhiều listener/pod xử lý song song.
10. **External effects:** nếu có database/API, test side effects/idempotency riêng; không ghi “exactly once end-to-end” chỉ từ Kafka output.
11. **Observability:** có đủ topic/partition/offset/event ID để giải thích một lần replay.
12. **Recovery:** crash, rebalance hoặc broker timeout không dẫn đến duplicate committed Kafka results hoặc mất input ngoài chính sách.

Các tiêu chí này là **khung thiết kế test**, không phải một annotation `@ExactlyOnceTest` có sẵn của Spring Kafka. Cần điều chỉnh với record listener, batch listener, DLT policy và loại output thực tế của dự án.

## 20. Bài tập thực hành mở rộng

**Bài tập 1 — Happy path và offset.** Tắt fault injection, gửi một record, assert đúng một output và group offset tăng đến vị trí sau record. So sánh kết quả `read_committed` với `read_uncommitted` khi chỉ có transaction thành công.

**Bài tập 2 — Abort và replay.** Bật fault injection sau output send ack như test trong bài. Assert listener retry và output không trùng với consumer `read_committed`. Thêm latch để tạm dừng sau rollback, query offset chưa tiến, rồi cho phép retry.

**Bài tập 3 — Nhiều record.** Gửi 10 input keys trên một partition; cố ý fail ở record thứ 5, bảo đảm output và committed offset phản ánh chính xác mọi transaction thành công. Sau đó mở rộng sang hai partitions và kiểm tra offsets theo từng partition.

**Bài tập 4 — Fencing.** Chạy hai app instance với transaction prefix trùng để quan sát lỗi fencing trong môi trường test, sau đó cấu hình prefix duy nhất và xác nhận cả hai làm việc đúng trên các partitions được gán.

**Bài tập 5 — Poison pill/DLT.** Gửi một record luôn lỗi, cấu hình retry/after-rollback recoverer, assert record xuất hiện trong DLT theo policy, original offset đủ để điều tra và downstream không nhận output lỗi.

**Bài tập 6 — Database side effects.** Trong listener tăng một counter ở database rồi cố ý abort Kafka transaction. Quan sát counter có thể tăng khi input replay. Sau đó thêm inbox unique `eventId`, ghi domain state và inbox trong cùng DB transaction, assert cuối cùng chỉ một business effect.

**Bài tập 7 — Kill và restart.** Dùng Testcontainers chạy consumer app riêng, kill đúng giữa output send và commit, restart cùng group. Assert output committed duy nhất và offset không bị mất; ghi lại thời gian broker giải quyết transaction cũ.

**Bài tập 8 — Tách biệt hạ tầng test.** Chạy test suite song song với topic/group/prefix riêng; xác nhận không bị inter-test interference hoặc producer fencing không mong muốn.

## 21. Tài liệu tham khảo chính thức

- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka Reference — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka Reference — Handling Exceptions / After-Rollback Processor](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Reference — Testing Applications, Embedded Kafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Apache Kafka Documentation — Transactions and Semantics](https://kafka.apache.org/documentation/)
- [Spring Kafka Reference — Transactional Outbox and transaction synchronization considerations](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)

**Kết luận:** Một test **exactly once flow** đáng tin cậy không kiểm tra “listener chỉ được gọi một lần”, mà kiểm tra **Kafka output và consumed offsets cùng commit hoặc cùng rollback**. Hãy cố ý gây lỗi **sau khi output đã được broker nhận nhưng trước khi transaction commit**, chứng minh listener có thể nhận lại input, rồi dùng consumer `read_committed` để xác nhận chỉ có **một output đã commit** và query **committed offset** của đúng consumer group. Bổ sung crash, fencing, DLT và idempotency cho các hệ thống ngoài Kafka để kết luận về độ tin cậy đúng phạm vi, không nhầm Kafka EOS với exactly-once business processing trên toàn bộ kiến trúc.
