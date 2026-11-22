# Test after-rollback redelivery trong Spring Kafka

Một consumer Spring Kafka đang xử lý đơn hàng thì gặp lỗi giữa chừng. Nếu listener nằm trong **Kafka transaction**, framework có thể rollback transaction hiện tại, đưa vị trí consumer trở lại record chưa xử lý thành công và giao lại chính record đó trong lần poll sau. Cơ chế này gọi là **after-rollback redelivery**. Nó quan trọng vì một hệ thống chỉ “thử lại khi exception” chưa chắc đã giữ đúng trạng thái offset và dữ liệu output, đặc biệt khi listener vừa đọc một topic vừa gửi sang topic khác.

Bài học thuộc **Spring Kafka Reliability Operations → Kiểm thử tin cậy**. Chúng ta sẽ dựng một integration test bằng **Spring Boot 3.x, Spring Kafka 3.x, Java 17, JUnit 5 và Embedded Kafka** để chứng minh các điều kiện: listener thất bại lần đầu, transaction đầu bị rollback, cùng `topic-partition-offset` được giao lại, lần xử lý sau thành công và topic đầu ra chỉ có **một kết quả đã commit**. Cuối bài mở rộng sang retry exhaustion, `DefaultAfterRollbackProcessor`, dead-letter topic (DLT), idempotency, restart và các lỗi test dễ gây kết quả sai.

## 1. Redelivery sau rollback thực sự là gì?

Giả sử một record nguồn:

```text
Topic: orders.in
Partition: 0
Offset: 42
Key: order-101
Value: {"amount":120}
```

Listener thực hiện:

1. Đọc record ở offset 42.
2. Tạo kết quả `validated:order-101` và gửi sang `orders.out`.
3. Gặp exception trước khi transaction commit.
4. Spring Kafka rollback Kafka transaction.
5. Thành phần xử lý sau rollback điều chỉnh vị trí consumer để record lỗi được đưa vào lần poll kế tiếp.
6. Listener nhận lại record offset 42 và xử lý thành công.

```text
orders.in: partition 0
    offset 41 [đã xử lý]
    offset 42 [order-101] <----------------------------+
                  |                                   |
              poll #1                                 |
                  |                                   |
                  v                                   |
           Kafka listener                             |
                  |                                   |
                  +--> send orders.out (chưa commit)  |
                  +--> throw exception                |
                  |                                   |
             ROLLBACK Kafka TX                        |
                  |                                   |
                  +--> after-rollback seek/reposition +
                                                      |
              poll #2: offset 42 <--------------------+
                  |
                  v
           Kafka listener
                  |
                  +--> send orders.out
                  +--> return normally
                  |
              COMMIT Kafka TX
                  |
                  v
       orders.out: 1 committed result
```

Thông thường, `DefaultAfterRollbackProcessor` được dùng với transactional listener container để thực hiện việc định vị lại các record sau rollback. Tuy nhiên, **redelivery là một hành vi cần được kiểm tra qua `ConsumerRecord` thực tế**, không nên kết luận chỉ từ số lần method Java được gọi.

### 1.1. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Điều cần test |
| --- | --- | --- |
| **Retry** | Thử xử lý lại sau lỗi; có thể xảy ra ở nhiều tầng | Bao nhiêu attempt, khoảng cách, giới hạn |
| **Redelivery** | Broker/container giao lại record cho listener | Cùng `topic`, `partition`, `offset`, key |
| **Rollback** | Giao dịch hiện tại không được commit | Output của attempt thất bại không hiện với `read_committed` |
| **Offset commit** | Lưu tiến độ tiêu thụ của consumer group | Offset sau xử lý thành công mới được commit theo contract |
| **Recovery** | Sau các attempt thất bại, chọn bỏ qua, DLT hoặc dừng | Có mất record im lặng không, offset được xử lý thế nào |
| **Replay** | Chủ động xử lý lại record lịch sử / DLT | Không đồng nhất với redelivery tự động trong transaction |

Retry có thể được thực hiện **ngay trong một method** mà không hề poll lại Kafka. Trong bài này, chúng ta kiểm tra **redelivery ở mức container**: cùng record đi vào `@KafkaListener` lần thứ hai sau rollback, không phải tự gọi lại phương thức listener trong unit test.

## 2. Điều kiện để có transactional after-rollback behavior

Có ba tầng cần phối hợp:

```text
Kafka Consumer
      |
      v
Spring Kafka listener container
      |
      +--> KafkaTransactionManager / KafkaAwareTransactionManager
      |            |
      |            +--> Kafka TX begin / commit / rollback
      |
      +--> listener xử lý record
      |
      +--> AfterRollbackProcessor khi transaction rollback
      |
      v
Kafka producer: gửi output trong transaction tương ứng
```

Các điều kiện thực hành:

- Producer factory được cấu hình **transactional ID prefix** duy nhất phù hợp phạm vi instance.
- Listener container dùng `KafkaTransactionManager` (hoặc transaction manager phù hợp với Kafka) để quản lý transaction cho quá trình nhận/xử lý.
- Auto-commit của consumer không được tự ý bật để offset bị commit ngoài quy trình transaction.
- Listener phải **ném exception ra ngoài** khi muốn transaction rollback. Bắt lỗi rồi chỉ `log.warn(...)` và return bình thường thường khiến container coi việc xử lý là thành công.
- Dữ liệu output trong Kafka transaction phải được quan sát bằng consumer có `isolation.level=read_committed` để không nhìn thấy record đã bị abort.
- Test phải có giới hạn thời gian và trạng thái chờ rõ, tránh dựa vào `Thread.sleep(...)` như điều kiện đồng bộ chính.

**Chú ý:** Kafka transaction bảo vệ các thao tác Kafka được tham gia đúng transaction và offset tiêu thụ được gửi vào transaction theo cơ chế container. Nó không tự biến một thao tác ghi PostgreSQL, gọi REST API hay gửi email thành cùng một giao dịch nguyên tử với Kafka.

## 3. Vì sao dùng `DefaultAfterRollbackProcessor` thay vì chỉ `DefaultErrorHandler`?

Spring Kafka có nhiều cơ chế xử lý lỗi. Với **record listener không transactional**, thường gặp `DefaultErrorHandler`: xử lý record exception, backoff, recoverer và seek/resubmit theo cấu hình. Với **transactional listener container**, exception thường cần thoát ra để Kafka transaction rollback; sau đó **`AfterRollbackProcessor`** chịu trách nhiệm xử lý các record còn lại và vị trí consumer.

| Ngữ cảnh | Cơ chế thường dùng | Điều gì không được nhầm? |
| --- | --- | --- |
| Record listener không dùng container transaction | `DefaultErrorHandler` | Không có Kafka TX để rollback output |
| Listener chạy trong Kafka transaction | `DefaultAfterRollbackProcessor` | Exception cần dẫn tới rollback trước khi redelivery |
| Non-blocking retry topic | `@RetryableTopic` / retry topics | Đây là một luồng retry khác, không phải seek sau rollback trong cùng consumer |
| Batch listener | Cách xác định record lỗi phụ thuộc listener và exception | Không mặc định mọi batch thất bại được redeliver đúng một item |

`DefaultAfterRollbackProcessor` có thể sử dụng backoff và recoverer khi một record liên tục thất bại. Một cấu hình recover/skip sau nhiều lần thử **thay đổi kỳ vọng của test**: không thể assert “redelivery mãi mãi” nếu policy cho phép phục hồi rồi bỏ qua record.

Trong phần test chính, ta cố ý cho record **lỗi đúng một lần rồi thành công** để kiểm tra đường rollback → redelivery mà không phụ thuộc vào ngưỡng recovery mặc định.

## 4. Mô hình test và tiêu chí thành công

Thiết kế hai topic, mỗi topic một partition:

```text
orders.rb.input  -->  @KafkaListener  --> orders.rb.output
                             |
                             +-- attempt #1: send rồi throw
                             |
                             +-- attempt #2: send rồi return
```

Giả định một record có key `order-101` và value `120`:

| Điều kiện | Kết quả mong đợi |
| --- | --- |
| Attempt #1 | Listener nhận record và ném lỗi giả lập |
| Transaction #1 | Bị rollback, output attempt #1 không được commit |
| Attempt #2 | Listener nhận lại đúng `topic-partition-offset` |
| Transaction #2 | Commit thành công |
| Quan sát output bằng `read_committed` | Có đúng một message `accepted:120` |
| Offset và key | Hai lần nhận có cùng `topic`, `partition`, `offset` và `key` |
| Thời gian test | Có timeout hữu hạn; không treo nếu redelivery không đến |

**Điều test không nên khẳng định:** “Kafka chắc chắn chỉ gọi listener đúng hai lần trong mọi môi trường production”. Trong tình huống fixture đơn lẻ không bị restart/rebalance và lỗi được mô phỏng một lần, hai lần giao là kỳ vọng của test. Ở môi trường thật, crash/rebalance và các failure mode khác có thể tạo thêm delivery; consumer phải được thiết kế để chịu được việc xử lý lặp.

## 5. Chuẩn bị dự án test

`build.gradle` minh họa với một phiên bản Spring Boot 3.x cụ thể; khi đưa vào dự án thật, dùng BOM/phiên bản đã được dự án quản lý:

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong bài thực hành:

- `spring-kafka` cung cấp `@KafkaListener`, `KafkaTemplate`, transaction manager và `DefaultAfterRollbackProcessor`.
- `spring-kafka-test` cung cấp `@EmbeddedKafka`, `EmbeddedKafkaBroker` và `KafkaTestUtils`.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và các tiện ích kiểm thử Spring Boot.
- Test dùng broker nhúng, **không cần một Kafka cluster thật bên ngoài**, nhưng chưa chứng minh được hành vi network, auth, ACL, multi-broker failover hay broker configuration production.

Một cấu trúc dự án khả thi:

```text
src/
├── main/
│   └── java/com/example/kafka/
│       └── ReliabilityApplication.java
└── test/
    └── java/com/example/kafka/
        └── AfterRollbackRedeliveryTest.java
```

Ở đây ví dụ đặt bean test listener và cấu hình container trong chính class test để người học nhìn toàn bộ thiết lập ở một nơi.

## 6. Bật Kafka transactions cho listener

Trong Spring Boot, một producer transactional thường được kích hoạt bằng `spring.kafka.producer.transaction-id-prefix`. Ngoài việc bật Kafka transaction ở producer, listener container **phải được gắn transaction manager** để xử lý lỗi listener theo đường rollback.

Cấu hình test dùng `@SpringBootTest` và `@EmbeddedKafka`:

```java
@SpringBootTest(
    classes = {
        AfterRollbackRedeliveryTest.App.class,
        AfterRollbackRedeliveryTest.KafkaTestConfig.class
    },
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.isolation-level=read_committed",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.transaction-id-prefix=rb-test-"
            + "${random.uuid}-"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.rb.input", "orders.rb.output"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
```

Đây là **đoạn annotation**, sẽ được dùng trong class test đầy đủ ở phần 9. `bootstrapServersProperty` cho phép Spring Embedded Kafka đăng ký địa chỉ broker vào thuộc tính được Spring Boot Kafka auto-configuration đọc.

Các điểm quan trọng:

1. `enable-auto-commit=false`: không cho consumer tự commit offset theo chu kỳ ngoài việc kiểm soát của container.
2. `isolation.level=read_committed`: consumer chỉ thấy record đã commit trong Kafka transaction, không thấy record từ transaction bị abort.
3. `transaction-id-prefix`: producer factory có khả năng tạo transactional producer; prefix cần quản lý **duy nhất giữa các instance** có thể chạy đồng thời trong môi trường thật.
4. `auto-offset-reset=earliest`: phù hợp fixture test khi group chưa có committed offset; không phải quy tắc recovery cho group đã có offset.

Không nên dùng cùng một `transactional.id` cố định cho nhiều application instance hoạt động song song: chúng có thể fence lẫn nhau. Trong production, prefix có thể kết hợp định danh instance ổn định duy nhất theo lifecycle và các ràng buộc của hệ thống điều phối.

## 7. Cấu hình `KafkaTransactionManager` và after-rollback processor

Trong Spring Kafka 3.x, `ConcurrentKafkaListenerContainerFactory` có thể được cấu hình để sử dụng Kafka transaction manager. Ví dụ class cấu hình test:

```java
@TestConfiguration
static class KafkaTestConfig {

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean("kafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            KafkaTransactionManager<String, String> transactionManager) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(1);

        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(transactionManager);

        // Dùng ARP mặc định để seek/re-deliver sau rollback.
        factory.setAfterRollbackProcessor(
                new DefaultAfterRollbackProcessor<>());

        return factory;
    }

    @Bean
    FlakyOrderListener flakyOrderListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        return new FlakyOrderListener(kafkaTemplate);
    }
}
```

`@TestConfiguration`, `@Bean` là annotation của Spring Boot/Spring; `ProducerFactory`, `ConsumerFactory`, `KafkaTemplate`, `ConcurrentKafkaListenerContainerFactory`, `KafkaTransactionManager` và `DefaultAfterRollbackProcessor` là các class của Spring Kafka. `FlakyOrderListener` sẽ được định nghĩa ở phần 8.

**Vì sao đặt concurrency bằng 1?** Ta cần một test xác định, chỉ một partition và một listener thread. Nếu có nhiều partition, nhiều thread hoặc group member, vẫn phải bảo đảm tính đúng đắn nhưng thứ tự các callback có thể khó dự đoán hơn.

**Vì sao dùng ARP mặc định?** Mục tiêu trước mắt chỉ là kiểm tra một lần lỗi rồi redelivery. Các thiết lập backoff, recoverer/DLT và số lần thử sẽ được kiểm tra bằng test riêng, không trộn lẫn để khỏi nhầm nguyên nhân.

Trong các phiên bản Spring Boot có auto-configuration Kafka transaction manager từ thuộc tính producer transaction prefix, nếu tự khai báo bean như ví dụ thì cần tránh vô tình tạo hai transaction manager dùng cho cùng mục đích. Cấu hình trong ứng dụng thực phải kiểm tra bean nào đang được inject vào listener container.

## 8. Listener fixture: thất bại lần đầu, thành công lần sau

Để test có thể quan sát sự kiện, listener giữ:

- Một `AtomicInteger` để đếm số lần callback nhận record trong fixture.
- Một queue thread-safe ghi `topic`, `partition`, `offset` và key của mỗi delivery.
- Một `CountDownLatch` để test biết đã có lần xử lý thành công.

```java
static class FlakyOrderListener {

    record Delivery(
            String topic, int partition, long offset, String key) {}

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final AtomicInteger attempts = new AtomicInteger();
    private final ConcurrentLinkedQueue<Delivery> deliveries =
            new ConcurrentLinkedQueue<>();
    private final CountDownLatch successfulAttempt =
            new CountDownLatch(1);

    FlakyOrderListener(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders.rb.input",
        groupId = "rollback-demo-group",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void onOrder(ConsumerRecord<String, String> record) {
        deliveries.add(new Delivery(
                record.topic(),
                record.partition(),
                record.offset(),
                record.key()));

        int currentAttempt = attempts.incrementAndGet();

        // Việc send tham gia Kafka transaction của listener container.
        kafkaTemplate.send(
                "orders.rb.output",
                record.key(),
                "accepted:" + record.value());

        if (currentAttempt == 1) {
            throw new IllegalStateException("SIMULATED_FIRST_FAILURE");
        }

        successfulAttempt.countDown();
    }

    boolean awaitSuccessfulAttempt(Duration timeout)
            throws InterruptedException {
        return successfulAttempt.await(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    List<Delivery> recordedDeliveries() {
        return List.copyOf(deliveries);
    }
}
```

Ở attempt đầu, `kafkaTemplate.send(...)` **đã được gọi** nhưng listener ném exception, dẫn tới transaction rollback. Điều này khác việc ném lỗi trước khi send: nếu test chỉ ném lỗi từ đầu, ta mới kiểm tra redelivery mà chưa kiểm tra output của Kafka transaction đầu có bị abort hay không.

`successfulAttempt.countDown()` xảy ra trước khi container hoàn tất commit transaction. Vì vậy test **không được** chỉ chờ latch rồi tuyên bố output đã commit: cần một output consumer `read_committed` để đọc và khẳng định kết quả cuối.

Fixture dùng state trong JVM để cố ý làm lỗi lần đầu; đây **không phải** retry counter dùng trong production. Trong hệ thống thật, record cần idempotency và recovery policy phù hợp để không bị xử lý sai khi process restart.

## 9. Integration test hoàn chỉnh với Embedded Kafka

Đoạn dưới đây gom cấu hình và fixture thành **một file test** để có thể triển khai trực tiếp với các dependency đã nêu.

`AfterRollbackRedeliveryTest.java`:

```java
package com.example.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.listener.DefaultAfterRollbackProcessor;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@SpringBootTest(
    classes = {
        AfterRollbackRedeliveryTest.App.class,
        AfterRollbackRedeliveryTest.KafkaTestConfig.class
    },
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.isolation-level=read_committed",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.transaction-id-prefix=rollback-test-"
            + "${random.uuid}-"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.rb.input", "orders.rb.output"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class AfterRollbackRedeliveryTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class App {}

    @TestConfiguration
    static class KafkaTestConfig {

        @Bean
        KafkaTransactionManager<String, String> kafkaTransactionManager(
                ProducerFactory<String, String> producerFactory) {
            return new KafkaTransactionManager<>(producerFactory);
        }

        @Bean("kafkaListenerContainerFactory")
        ConcurrentKafkaListenerContainerFactory<String, String>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, String> consumerFactory,
                KafkaTransactionManager<String, String> transactionManager) {

            var factory =
                    new ConcurrentKafkaListenerContainerFactory<
                            String, String>();
            factory.setConsumerFactory(consumerFactory);
            factory.setConcurrency(1);
            factory.getContainerProperties()
                    .setKafkaAwareTransactionManager(transactionManager);
            factory.setAfterRollbackProcessor(
                    new DefaultAfterRollbackProcessor<>());
            return factory;
        }

        @Bean
        FlakyOrderListener flakyOrderListener(
                KafkaTemplate<String, String> template) {
            return new FlakyOrderListener(template);
        }
    }

    static class FlakyOrderListener {
        record Delivery(String topic, int partition, long offset, String key) {}

        private final KafkaTemplate<String, String> template;
        private final AtomicInteger attempts = new AtomicInteger();
        private final ConcurrentLinkedQueue<Delivery> deliveries =
                new ConcurrentLinkedQueue<>();
        private final CountDownLatch succeeded = new CountDownLatch(1);

        FlakyOrderListener(KafkaTemplate<String, String> template) {
            this.template = template;
        }

        @KafkaListener(
            topics = "orders.rb.input",
            groupId = "rollback-demo-group",
            containerFactory = "kafkaListenerContainerFactory")
        public void onOrder(ConsumerRecord<String, String> record) {
            deliveries.add(new Delivery(
                    record.topic(), record.partition(),
                    record.offset(), record.key()));

            int attempt = attempts.incrementAndGet();
            template.send(
                    "orders.rb.output",
                    record.key(),
                    "accepted:" + record.value());

            if (attempt == 1) {
                throw new IllegalStateException("SIMULATED_FIRST_FAILURE");
            }
            succeeded.countDown();
        }
    }

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private EmbeddedKafkaBroker broker;

    @Autowired
    private FlakyOrderListener listener;

    @Test
    void rollsBackThenRedeliversSameRecordAndCommitsOnlyOnce()
            throws Exception {

        // KafkaTemplate transactional: gửi input trong transaction riêng.
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send(
                    "orders.rb.input", "order-101", "120").join();
            return null;
        });

        assertThat(listener.succeeded.await(20, TimeUnit.SECONDS))
                .as("Listener should succeed after redelivery")
                .isTrue();

        // Hai callback ứng với cùng bản ghi logic tại cùng offset.
        List<FlakyOrderListener.Delivery> received =
                List.copyOf(listener.deliveries);
        assertThat(received).hasSize(2);
        assertThat(received.get(1))
                .isEqualTo(received.get(0));
        assertThat(received.get(0).key())
                .isEqualTo("order-101");
        assertThat(received.get(0).topic())
                .isEqualTo("orders.rb.input");

        // Observer chỉ nhìn thấy output đã COMMIT.
        Map<String, Object> consumerProps =
                KafkaTestUtils.consumerProps(
                        "rb-observer-" + UUID.randomUUID(),
                        "false", broker);
        consumerProps.put(
                ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
        consumerProps.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        var observerFactory =
                new DefaultKafkaConsumerFactory<String, String>(
                        consumerProps,
                        new StringDeserializer(),
                        new StringDeserializer());

        try (Consumer<String, String> observer =
                     observerFactory.createConsumer()) {

            broker.consumeFromAnEmbeddedTopic(
                    observer, "orders.rb.output");

            ConsumerRecord<String, String> output =
                    KafkaTestUtils.getSingleRecord(
                            observer,
                            "orders.rb.output",
                            Duration.ofSeconds(20));

            assertThat(output.key()).isEqualTo("order-101");
            assertThat(output.value()).isEqualTo("accepted:120");

            ConsumerRecords<String, String> unexpected =
                    KafkaTestUtils.getRecords(
                            observer, Duration.ofMillis(500));
            assertThat(unexpected.count()).isZero();
        }
    }
}
```

**Kết quả mà test chứng minh:** cùng record Kafka được đưa lại cho listener; attempt đầu đã rollback nên **không có output đã commit** từ lần đó; sau lần xử lý thành công, observer `read_committed` nhận đúng một output theo fixture này.

**Điểm cần hiểu khi triển khai:** `getSingleRecord(...)` kiểm tra một record trong phạm vi poll của test và lần poll tiếp theo giúp tìm duplicate sớm. Với hệ thống lớn hơn, nên xác định **test window đủ rõ**, số input cố định, topic/group cô lập và đối soát kết quả cuối thay vì tuyên bố hệ thống tuyệt đối không bao giờ tạo duplicate chỉ từ một test nhỏ.

### 9.1. Vì sao gửi input bằng `executeInTransaction(...)`?

Khi `KafkaTemplate` được cấu hình trên một transactional producer factory, gọi `send(...)` trực tiếp bên ngoài transaction có thể bị từ chối tùy cấu hình và API. Trong test:

```java
kafkaTemplate.executeInTransaction(ops -> {
    ops.send("orders.rb.input", "order-101", "120").join();
    return null;
});
```

Ta tạo **một transaction riêng để gửi fixture vào topic đầu vào**, sau đó listener dùng transaction của container để xử lý record đó. Đây là hai transaction có mục đích khác nhau; không giả định callback của test đang chia sẻ transaction với listener thread.

### 9.2. Vì sao phải kiểm tra offset thay vì chỉ key?

`orderId` hoặc key có thể xuất hiện ở nhiều Kafka record. Hai record cùng key nhưng offset khác nhau **không phải cùng một delivery**. Test cần so sánh đồng thời:

```text
topic
partition
offset
key
```

`topic-partition-offset` nhận diện vị trí record trong log Kafka. Với cùng record được giao lại sau rollback, offset phải giống nhau. Không cần hardcode offset bằng `0`, vì topic test có thể đã chứa dữ liệu trước đó hoặc broker có cơ chế tạo record nội bộ khác theo cấu hình.

### 9.3. Vì sao `read_committed` là bắt buộc cho observer?

Kafka transaction bị abort **không xóa vật lý record đã ghi khỏi log ngay lập tức**. Một consumer `read_uncommitted` có thể nhìn thấy các record của aborted transaction. Vì vậy nếu bạn đọc topic đầu ra bằng consumer mặc định không kiểm soát isolation, test có thể nhìn thấy **hai message** rồi kết luận sai rằng rollback không hoạt động.

Trong test, observer dùng:

```java
consumerProps.put(
        ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
```

Đây là cách quan sát kết quả **được phép đọc theo giao dịch** của Kafka. Test không nên thay `read_committed` bằng sleep dài hơn để “chờ record lỗi biến mất”.

## 10. Kiểm thử offset commit sau redelivery

Kiểm tra cùng offset được giao lại là một phần của bài. Với transactional consumer, còn cần hiểu sự liên hệ giữa **xử lý thành công** và **tiến độ consumer group**:

```text
Attempt #1 (FAILED)
   input offset 42
   output send in transaction
   exception
   TX abort
   input offset NOT successfully committed as processed

Attempt #2 (SUCCESS)
   input offset 42 redelivered
   output send
   listener returns
   TX commit (bao gồm tiến độ offset theo container)
   next record can be consumed
```

Để test chính xác committed offsets, có thể dùng `AdminClient.listConsumerGroupOffsets(groupId)` hoặc công cụ Kafka Admin tương đương **sau khi transaction thứ hai đã commit**. Lưu ý Kafka commit theo **next offset**: sau khi xử lý thành công offset 42, committed offset cho partition đó thường là **43**, không phải 42.

Không nhất thiết thêm AdminClient vào test cơ bản nếu mục tiêu chỉ là redelivery + output đã commit. Test offset nên có **group ID duy nhất**, poll/trạng thái commit có timeout và không có record khác cùng group làm thay đổi tiến độ trong lúc assertion.

Trong môi trường có `isolation.level=read_committed`, những record từ transaction còn mở có thể làm last stable offset chậm tiến. Điều này ảnh hưởng cách quan sát lag và output, nên không dùng chỉ một snapshot lag để suy ra chính xác một rollback đã/đã chưa xảy ra.

## 11. Khi listener luôn lỗi: backoff, recovery và DLT

Test ở phần 9 cố ý thành công trong lần thứ hai. Nhưng cần thêm một test độc lập cho **poison record**: một message có nội dung không hợp lệ sẽ lỗi mãi nếu không được sửa.

Ví dụ:

```text
orders.rb.input offset 43, value="not-a-number"
   |
   +-- attempt 1 FAILED -> rollback
   +-- attempt 2 FAILED -> rollback
   +-- attempt 3 FAILED -> rollback
   |
   +-- recover / publish DLT / stop, tùy chính sách
```

Nếu không có giới hạn, poison record có thể làm partition bị kẹt. `DefaultAfterRollbackProcessor` có thể kết hợp `BackOff` và recoverer để quyết định sau bao nhiêu lần thất bại sẽ xử lý record theo hướng khác.

Ví dụ cấu hình **cho bài test recovery riêng**:

```java
import org.springframework.kafka.listener.DefaultAfterRollbackProcessor;
import org.springframework.util.backoff.FixedBackOff;

var processor =
        new DefaultAfterRollbackProcessor<String, String>(
                (record, error) -> {
                    // Demo: ghi nhận sự kiện recover bằng mã cố định.
                    // Production phải có recoverer bền vững hoặc DLT.
                    recoveryCounter.incrementAndGet();
                },
                new FixedBackOff(100L, 2L));

factory.setAfterRollbackProcessor(processor);
```

`recoveryCounter` là biến test do lớp test định nghĩa; đoạn trên là fragment minh họa, không phải toàn bộ class độc lập. `FixedBackOff(100L, 2L)` đặt khoảng chờ 100 ms và ngân sách retry theo ngữ nghĩa của `BackOff`; nên kiểm tra bằng assertion thực tế thay vì tự đoán từ tổng số callback. Nếu recoverer **chỉ tăng counter rồi bỏ qua**, record có nguy cơ mất khỏi đường xử lý bình thường; đó không phải chiến lược dữ liệu production an toàn.

### 11.1. Dead-letter publishing recoverer

Với dữ liệu không thể xử lý, thường muốn gửi một sự kiện lỗi được phép sang DLT:

```text
orders.rb.input
    |
    +-- failed attempts --> rollback / redelivery
                               |
                               v
                   after-rollback recoverer
                               |
                               v
                       orders.rb.input.DLT
```

Trong Spring Kafka có `DeadLetterPublishingRecoverer` để phát hành record tới một topic đích sau khi lỗi đã được phân loại. Khi dùng nó với transactional after-rollback processing, cần xem xét:

- DLT được ghi trong **transaction nào**, và kết quả recovery có được commit hay không.
- Offset của record được recover/skip có được commit **đúng cách** để không redeliver mãi khi process restart.
- `commitRecovered` và Kafka operations/template truyền cho processor phải phù hợp **ack mode**, transaction manager và phiên bản Spring Kafka đang dùng. Các cấu hình này không chỉ là bật một flag rồi đủ.
- DLT có partition, retention, quyền truy cập, serialization và consumer replay riêng.
- Payload/headers có thể chứa dữ liệu nhạy cảm hoặc exception detail; cần chính sách bảo vệ như mọi topic khác.

**Test recovery cần assert nhiều điều hơn test redelivery:** số lần giao theo policy, một record DLT đã commit, offset sau recovery, không có output nghiệp vụ sai, và đường replay/repair thực tế. Không coi việc “đã log lỗi” là một recovery hoàn chỉnh.

### 11.2. Không đánh đồng `@RetryableTopic` với after-rollback redelivery

`@RetryableTopic` thường tạo luồng retry **non-blocking qua các topic khác**, với delay và routing riêng. After-rollback redelivery xử lý lại record sau rollback trong luồng listener/container transactional tương ứng. Hai cách có ngữ nghĩa offset, ordering, transaction và topology khác nhau.

Với một bài test cụ thể, hãy chọn **một** chiến lược đang dùng trong sản phẩm rồi viết assertion theo đúng chiến lược đó. Không đặt kỳ vọng “cùng topic-partition-offset” cho một record đã được publish sang retry topic khác.

## 12. Batch listener và record listener: khác nhau khi rollback

Test chính dùng **record listener**:

```java
@KafkaListener(topics = "orders.rb.input")
public void onOrder(ConsumerRecord<String, String> record) { ... }
```

Với **batch listener** nhận một `List<ConsumerRecord<K,V>>`, một poll có thể cung cấp nhiều record. Khi transaction rollback, các record còn lại của poll có thể được xử lý lại; việc chọn một record để recover đòi hỏi framework biết record nào gây lỗi hoặc dùng chiến lược xử lý batch phù hợp.

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Record listener, một record lỗi | Cùng offset được redeliver |
| Poll chứa nhiều record, một record lỗi | Các record còn lại được seek/replay theo chính sách |
| Batch listener ném exception chung | Không mặc định xác định chính xác item lỗi |
| Batch listener cung cấp thông tin record lỗi phù hợp | Recovery có thể định vị record theo API hỗ trợ |
| Batch DLT/recovery | Không ghi nhầm cả batch thành một item lỗi nếu chỉ một record hỏng |

Với Spring Kafka, `BatchListenerFailedException` là một cơ chế cho phép truyền thông tin vị trí record lỗi trong batch khi cấu hình và phiên bản hỗ trợ. Nếu test batch behavior, cần dựng **ít nhất ba record**, cho lỗi ở record giữa, rồi xác nhận phạm vi replay và output từng record. Một test chỉ có một record sẽ không phát hiện sự khác nhau về rollback của batch.

## 13. Cẩn thận với side effect bên ngoài Kafka

Giả sử listener làm cả hai việc:

```java
@KafkaListener(topics = "orders.rb.input")
public void process(OrderEvent event) {
    paymentService.charge(event.orderId());
    kafkaTemplate.send("orders.rb.output", event.orderId(), "CHARGED");
    throw new IllegalStateException("SIMULATED_FAILURE");
}
```

Nếu Kafka transaction rollback, Kafka output có thể bị abort. Nhưng **lệnh charge đã gửi cho payment service không tự rollback**. Khi record được redeliver, listener có thể charge lần nữa. Vì thế:

```text
Kafka TX rollback  !=  External side effect rollback
```

Để chịu được redelivery:

1. **Idempotency key ổn định:** ví dụ `orderId` hoặc `source event ID` theo contract; cùng key lặp lại không tạo giao dịch mới.
2. **Transactional outbox/inbox:** nếu ghi database, dùng transaction và ràng buộc unique để ghi nhận event đã xử lý cùng dữ liệu nghiệp vụ; phát hành kết quả theo worker riêng.
3. **Khả năng đối soát:** sau timeout từ API, trạng thái thực tế có thể không xác định; tra cứu theo key trước khi thử lại.
4. **Không dùng attempt number làm idempotency key:** một record redeliver với attempt khác phải được nhận là cùng tác vụ nghiệp vụ.
5. **Test side effect giả:** mock/stub service có counter và kiểm tra ứng dụng không tạo tác dụng phụ trùng; không chỉ kiểm tra output topic.

Kafka hỗ trợ một số đảm bảo exactly-once cho luồng **consume-process-produce trong Kafka khi cấu hình giao dịch đúng**. Điều đó **không** mở rộng tự động thành exactly-once cho database hoặc HTTP bên ngoài Kafka. Vì thế vẫn cần thiết kế idempotency ở ranh giới nghiệp vụ.

## 14. Tránh test flaky: đồng bộ bằng sự kiện, không đoán bằng thời gian

Kafka là hệ thống bất đồng bộ. Nếu test chỉ:

```java
kafkaTemplate.send("orders.rb.input", "key", "value");
Thread.sleep(1000);
assertThat(attempts.get()).isEqualTo(2);
```

thì kết quả phụ thuộc tốc độ khởi động broker, partition assignment, CPU của CI và broker networking. Một máy chạy nhanh có thể pass, một máy tải cao có thể fail.

### 14.1. Chờ đúng điều kiện

Trong ví dụ, dùng:

```java
assertThat(listener.succeeded.await(20, TimeUnit.SECONDS)).isTrue();
```

và `KafkaTestUtils.getSingleRecord(...)` với `Duration` rõ. Latch chứng minh listener đã đi đến điểm thành công; consumer `read_committed` chứng minh output đã được commit. Chúng bổ sung cho nhau.

Nếu cần kiểm tra listener **đã được assign partition** trước khi gửi:

```java
// Có thể lấy container theo listener id và dùng tiện ích chờ assignment.
// Không cần chỉ sleep một khoảng thời gian cố định.
```

Spring Kafka Test có `ContainerTestUtils.waitForAssignment(...)`. Với một test cần kiểm soát nhiều container và partition, gắn `id` cố định vào `@KafkaListener`, lấy container từ `KafkaListenerEndpointRegistry`, rồi chờ đúng số partition được assign trước khi gửi fixture.

### 14.2. Cô lập các test

| Nguyên nhân gây flaky | Giải pháp |
| --- | --- |
| Dùng lại topic/group qua nhiều test | Topic hoặc group riêng, context cô lập |
| Listener test trước còn chạy | Dừng container/context và không chia sẻ state ngầm |
| Shared `AtomicInteger` chưa reset | Tạo listener mới cho mỗi test hoặc reset có kiểm soát |
| Broker chưa assign partition | Chờ assignment/event thay vì sleep |
| KafkaTemplate transactional gửi fixture không có TX | `executeInTransaction(...)` hoặc producer test riêng |
| Observer dùng `read_uncommitted` | Đặt `isolation.level=read_committed` |
| Assert offset luôn bằng 0 | So offset giữa hai delivery, không hardcode |
| Timeout quá ngắn | Timeout hữu hạn có dự phòng cho CI, có failure message |
| Tests chạy song song trên chung group | Dùng group độc lập hoặc tắt parallel cho kịch bản này |
| Chỉ assert callback count | Assert thêm cùng offset, output committed, trạng thái recovery |

Với suite lớn, có thể dùng `@DirtiesContext` để tránh bean listener và embedded broker của test trước ảnh hưởng test sau. Tuy nhiên tạo/dừng context và broker tốn thời gian; tốt nhất là kết hợp **topic/group riêng** với test lifecycle được quản lý rõ.

### 14.3. Không bật debug log payload bừa bãi

Trong test lỗi, `ConsumerRecord.value()` có thể chứa thông tin nhạy cảm. Khi chạy production, không nên log nguyên record hoặc exception mang payload từ serializer/deserializer. Có thể log `topic`, `partition`, `offset`, attempt, mã lỗi an toàn và correlation ID đã được duyệt; item key nhạy cảm cần token hóa.

## 15. Mở rộng thành ma trận kiểm thử tin cậy

Một bài test “lỗi lần đầu rồi thành công” là điểm khởi đầu, không phải toàn bộ kiểm chứng reliability.

| Kịch bản | Cách tạo fixture | Kỳ vọng |
| --- | --- | --- |
| Lỗi một lần rồi thành công | Throw ở attempt 1 | Cùng offset redeliver; một committed output |
| Lỗi mãi | Throw ở mọi attempt | Backoff, recover/DLT hoặc stop theo policy |
| Lỗi ngay trước output send | Throw trước `kafkaTemplate.send(...)` | Redelivery, không có output attempt đầu |
| Lỗi sau output send | Send rồi throw | Output TX đầu bị abort, chỉ output TX thành công visible |
| Send lỗi trước commit | Producer failure giả lập | Transaction fail/rollback; không coi listener return là success |
| Có hai record trong cùng poll | Record 1 thành công, record 2 lỗi | Phạm vi rollback/replay theo container và transaction |
| Nhiều partition | Record lỗi trên partition A | Kiểm tra position và tiến độ partition B theo cấu hình |
| Restart process giữa xử lý | Dừng worker trước commit | Consumer group nhận lại record chưa commit |
| Rebalance khi processing | Thay đổi group membership | Không mất record; xử lý trùng phải an toàn |
| Poison record sang DLT | Recovery policy với backoff hữu hạn | DLT có record bền vững, offset xử lý đúng |
| External DB/API side effect | Stub service có idempotency key | Không thực hiện tác dụng phụ trùng |
| Observer `read_uncommitted` | Consumer test dùng isolation sai | Thấy khác biệt, hiểu rõ aborted records |

**Quan trọng với restart test:** `AtomicInteger` trong listener được reset khi JVM khởi động lại, nên không thể dùng nó làm bằng chứng về số lần xử lý của một record xuyên nhiều process. Hãy dùng identity/offset từ Kafka, event audit và dữ liệu bên ngoài để xác định kết quả.

## 16. Quan sát rollback và redelivery khi vận hành

Hệ thống production cần nhìn thấy khi nào redelivery tăng bất thường:

```text
event=kafka_listener_attempt_failed
listener=orders-consumer
topic=orders.in
partition=0
offset=42
error_code=TRANSIENT_PARTNER_FAILURE

event=kafka_transaction_rolled_back
listener=orders-consumer
topic=orders.in
partition=0

event=kafka_record_recovered
listener=orders-consumer
topic=orders.in
partition=0
offset=42
recovery=DLT
```

Đây là **schema event gợi ý**, không phải những dòng mặc định mà Spring Kafka phát ra y hệt. Có thể dùng container listener, metrics/Micrometer, interceptor hoặc custom recoverer để xuất sự kiện phù hợp, tránh log payload nhạy cảm.

Những chỉ số cần quan tâm:

- Số lần xử lý lỗi theo listener/topic/error code.
- Số record được recover, chuyển DLT hoặc còn chờ xử lý.
- Độ trễ redelivery, thời gian transaction và tỷ lệ abort.
- Consumer lag theo **partition**, chú ý khác biệt giữa current position, committed offset và last stable offset.
- Tỷ lệ lỗi lặp lại trên cùng offset; một offset lỗi liên tục có thể làm partition chậm lại.
- Số producer fencing/transaction timeout, rebalance và consumer poll timeout.

Không dùng `topic-partition-offset` làm label cho time-series metrics: cardinality có thể rất lớn. Nó phù hợp hơn làm field tìm kiếm trong log hoặc audit được bảo vệ.

## 17. Các lỗi triển khai/test thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Listener gọi một lần rồi không redeliver | Exception bị nuốt, container transaction không bật, recovery đã skip | Để exception propagate; kiểm tra transaction manager/ARP |
| Test thấy hai output | Observer dùng `read_uncommitted` hoặc đã có hai transaction commit | Dùng `read_committed`, topic/group cô lập, xác nhận metadata |
| Test báo success trước khi Kafka commit | Chỉ chờ latch bên trong listener | Poll committed output sau latch |
| Consumer không nhận message test | Chưa assign partition, group/offset sai, topic sai | Chờ assignment, dùng unique group và kiểm tra fixture send |
| `KafkaTemplate.send` báo không có transaction | Transactional template được gọi ngoài TX | Dùng `executeInTransaction` khi gửi fixture |
| Transactional producer bị fenced | Trùng `transactional.id` giữa instance | Thiết kế prefix/instance ID duy nhất |
| Test callback count thay đổi ngẫu nhiên | Consumer rebalance, test song song, shared listener state | Cô lập topic/group/context và test window |
| Poison record kẹt vô hạn | Không có policy backoff/recovery rõ | DLT hoặc fail/stop theo contract, kiểm tra offset |
| Record đã DLT vẫn quay lại sau restart | Recovery/offset commit không phù hợp transaction | Kiểm tra `commitRecovered`/ack mode và transaction boundary |
| DB ghi trùng dù Kafka output chỉ có một | DB không nằm trong Kafka transaction | Idempotency/inbox/outbox và integration test DB |
| Test chỉ gọi trực tiếp method `@KafkaListener` | Bỏ qua broker, transaction và ARP | Dùng Embedded Kafka/Testcontainers integration test |
| Dùng `@RetryableTopic` rồi assert cùng offset | Retry xảy ra ở topic khác | Viết test theo topology thực tế |
| Log exception và toàn bộ `ConsumerRecord` | Có thể tiết lộ dữ liệu nghiệp vụ | Log metadata + mã lỗi đã duyệt |

## 18. Bài thực hành nâng cao

Sau khi chạy được test cơ bản, hãy thực hiện lần lượt:

1. **Đổi failure point:** ném exception trước `kafkaTemplate.send(...)`, chạy test và giải thích vì sao assertion “một output committed” vẫn pass nhưng không còn kiểm tra aborted output từ attempt đầu.
2. **Giữ failure sau send:** xác nhận observer `read_committed` chỉ đọc output từ attempt thành công; nếu đổi observer sang `read_uncommitted`, ghi nhận sự khác biệt mà không coi đó là lỗi framework.
3. **Kiểm tra cùng offset:** lưu `topic`, `partition`, `offset`, `key` qua các attempt; chứng minh cùng record được redeliver thay vì hai record trùng key.
4. **Poison record:** cho listener luôn ném exception; cấu hình backoff hữu hạn và recovery policy rõ, tránh kẹt partition.
5. **DLT:** thay recoverer log-only bằng `DeadLetterPublishingRecoverer`, tạo topic DLT, xác minh một record đã commit và đường xử lý lại có idempotency.
6. **Offset sau recovery:** đọc committed consumer group offset và so với offset nguồn; chú ý Kafka commit vị trí kế tiếp.
7. **Nhiều input record:** gửi ba record, làm record thứ hai lỗi. Quan sát phạm vi rollback và những record được replay khi container polling/chunk boundaries thay đổi.
8. **Restart:** dừng listener/container trước commit, khởi động lại group và kiểm tra record chưa commit được giao lại. Không dùng counter trong JVM làm dữ liệu duy nhất.
9. **External side effect:** thay send output bằng một stub database/API có counter; mô phỏng timeout sau khi side effect thành công và bổ sung idempotency.
10. **CI:** chạy test lặp nhiều lần trong môi trường cô lập. Nếu test flaky, chờ partition assignment và sự kiện commit bằng condition có timeout thay vì tăng `Thread.sleep`.

## 19. Tổng kết

After-rollback redelivery trong Spring Kafka là cơ chế quan trọng của **transactional listener**: khi xử lý lỗi, Kafka transaction bị rollback và listener container có thể đưa record chưa xử lý thành công trở lại để tiêu thụ. Kiểm thử đúng phải xác nhận **hai mặt cùng lúc**:

- **Input:** cùng `topic-partition-offset` được giao lại sau rollback, không chỉ một method Java bị gọi hai lần.
- **Output:** các bản ghi được gửi trong transaction đã abort **không xuất hiện với `read_committed`**, và transaction thành công tạo kết quả được commit.

`EmbeddedKafka`, `@KafkaListener`, `DefaultAfterRollbackProcessor`, `KafkaTransactionManager`, `KafkaTestUtils` và các primitive như `CountDownLatch` giúp tạo một kịch bản xác định. Khi chuyển sang production, cần kiểm tra thêm backoff, poison record/DLT, committed offset, idempotency cho side effect ngoài Kafka và khả năng phục hồi sau crash. **Đừng nhầm một test redelivery pass với bảo đảm exactly-once cho toàn bộ hệ thống**; độ tin cậy phải được kiểm chứng ở từng transaction boundary và ranh giới dữ liệu thực tế.
