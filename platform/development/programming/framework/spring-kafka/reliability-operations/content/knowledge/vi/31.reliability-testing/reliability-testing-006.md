# Test transaction commit trong Spring Kafka

## 1. Bài toán: gửi thành công chưa chắc đã commit

Trong hệ thống dùng **Spring Kafka**, một service có thể nhận message từ topic đầu vào, xử lý nghiệp vụ rồi gửi message mới đến topic đầu ra. Nếu tiến trình gặp lỗi giữa chừng, hệ thống phải biết message nào thật sự được công bố, message nào bị hủy và consumer group offset có được cập nhật đúng không.

Chỉ kiểm tra rằng **KafkaTemplate.send(...) không ném exception** là chưa đủ. Nếu producer đang ở trong một Kafka transaction, một record đã được broker nhận vẫn có thể bị **abort** trước khi transaction kết thúc. Consumer cấu hình **read_committed** sẽ không trả về record thuộc transaction bị abort.

Ví dụ:

~~~text
Order processor
     |
     v
beginTransaction()
     |
     +-- send(order-created, O101) ----> Kafka log
     |
     +-- send(order-audited, O101) ----> Kafka log
     |
     +-- commitTransaction()
             |
             +-- Thành công: cả hai record visible với read_committed
             |
             +-- abort: cả hai record bị ẩn với read_committed
             |
             +-- Mất ACK / process crash: cần xác minh trạng thái thực tế
~~~

Trong chương **Spring Kafka Reliability Operations → Kiểm thử tin cậy**, bài **Test transaction commit** tập trung xây kiểm thử chứng minh điều này bằng một Kafka broker thật trong môi trường test, không chỉ dựa vào mock method.

Mục tiêu:

1. Khai báo **transactional producer** bằng \`transactional.id\` hoặc \`transactionIdPrefix\`.
2. Xác minh transaction commit làm các record xuất hiện với consumer \`read_committed\`.
3. Xác minh transaction abort làm các record không xuất hiện với \`read_committed\`.
4. Hiểu khác biệt giữa **producer send acknowledgment** và **transaction commit acknowledgment**.
5. Kiểm tra luồng **consume → process → produce** có output và consumer offsets thuộc cùng Kafka transaction.
6. Thiết kế fault injection cho failure trước commit, sau commit và lúc commit outcome không rõ.
7. Nhận diện giới hạn của Kafka transactions khi workflow còn ghi database, HTTP API hoặc file.
8. Ghi nhận bằng chứng test, metrics và runbook để vận hành giao dịch tin cậy.

Các đoạn code minh họa hệ sinh thái **Spring Kafka 3.x, Kafka clients 3.x, Java 17 và JUnit 5**. Khi nâng cấp framework, cần đối chiếu API configuration của phiên bản đang chạy; các khái niệm transaction và isolation ở đây vẫn là trọng tâm.

## 2. Kafka transaction bảo đảm điều gì?

Một Kafka producer có thể gửi nhiều record vào **một transaction**, trên một hoặc nhiều partition/topic, rồi **commit** hoặc **abort** như một đơn vị giao dịch ở cấp Kafka.

Ví dụ:

~~~text
Transaction TX-100
   |
   +-- topic orders: key=O101 value=CREATED
   |
   +-- topic audit:  key=O101 value=CREATED_BY_JOB
   |
   +-- COMMIT
        |
        v
Consumers with isolation.level=read_committed:
  See both records when transaction is committed.
~~~

Nếu cùng giao dịch bị abort, consumer \`read_committed\` không trả về cả hai record đó. Broker vẫn có thể giữ các dữ liệu và transaction markers trong log vật lý theo cơ chế Kafka, nhưng chúng **không được coi là visible business records** đối với consumer read_committed.

### Những điều Kafka transaction không tự bảo đảm

- Không tự làm một câu \`INSERT\` trong PostgreSQL và một \`send\` tới Kafka thành **một distributed atomic transaction**.
- Không rollback email, HTTP request, payment, file output hoặc cache write.
- Không đảm bảo business handler của hệ thống downstream không chạy trùng nếu consumer hoặc external side effect không được thiết kế idempotent.
- Không bảo đảm producer application nhận được ACK trong mọi tình huống mạng; có thể tồn tại **commit outcome chưa rõ đối với client**.
- Không thay thế việc kiểm tra record keys, payload, partitioning, schema và nghiệp vụ.

**Exactly-once semantics (EOS)** trong Kafka cần được hiểu trong phạm vi các thao tác Kafka được cấu hình đúng: transactional writes và, với luồng consume-transform-produce, việc ghi output **cùng** việc commit offsets của consumer group vào transaction. Khi dữ liệu đi ra khỏi ranh giới Kafka này, phải có thiết kế tin cậy bổ sung.

## 3. Các khái niệm cần phân biệt

| Khái niệm | Mô tả | Vai trò trong test |
|---|---|---|
| \`transactional.id\` | Định danh transaction producer, dùng với coordinator để quản lý epoch/fencing | Xác định ownership và khả năng producer fencing |
| \`transactionIdPrefix\` | Prefix Spring Kafka dùng để cấp transactional.id cho các producer trong factory/cache | Cấu hình transactional producer |
| \`enable.idempotence\` | Giúp ngăn duplicate do producer retry ở phạm vi producer session và partition | Liên quan delivery guarantees, nhưng không thay thế transaction |
| \`initTransactions()\` | Đăng ký/khởi tạo producer có khả năng transaction với broker | Cần trước giao dịch khi dùng KafkaProducer trực tiếp |
| \`beginTransaction()\` | Bắt đầu transaction | Giới hạn tập record đang gửi |
| \`commitTransaction()\` | Yêu cầu commit transaction | Điểm test visibility |
| \`abortTransaction()\` | Hủy transaction | Điểm test rollback trên Kafka |
| \`isolation.level=read_committed\` | Consumer chỉ trả các record từ transaction đã commit cùng các record không giao dịch | Để xác nhận visibility được bảo đảm |
| \`isolation.level=read_uncommitted\` | Consumer có thể đọc cả record từ transaction chưa commit hoặc đã abort | Phục vụ so sánh, không dùng để đánh giá EOS |
| LSO / Last Stable Offset | Ranh giới đọc của consumer read_committed khi còn transaction mở | Giải thích vì sao dữ liệu đến sau một transaction mở có thể bị giữ lại |
| Producer fencing | Producer epoch mới có thể làm producer cũ dùng cùng transactional.id không còn được phép commit | Tránh hai owner cùng ghi dưới cùng identity |
| Consumer group offset | Vị trí đã được ghi nhận cho nhóm consumer | Với consume-process-produce, phải gắn vào transaction khi cần EOS |

**Một record có offset trong Kafka log không đồng nghĩa transaction của nó đã commit.** Consumer read_committed dựa vào transaction markers/isolation để xác định record nào được trả cho ứng dụng.

### Send ACK khác commit ACK

~~~text
KafkaTemplate.send(...).get(...) / .join()
               |
               v
Broker đã ACK record append theo acks config
               |
               X Chưa phải bằng chứng transaction COMMITTED
               |
               v
KafkaTemplate.executeInTransaction(...) callback kết thúc
               |
               v
Kafka producer commit transaction
               |
               v
read_committed consumer mới nhìn thấy records
~~~

Nếu có exception trong callback của \`executeInTransaction\`, Spring Kafka sẽ cố abort transaction. Kiểm thử cần xác nhận **outcome quan sát từ broker**, chứ không chỉ xác nhận method đã ném exception.

## 4. Điều kiện để test transaction đúng

Một integration test đáng tin cậy cần:

1. **Broker thật** ở mức giao thức Kafka, dùng EmbeddedKafka hoặc Testcontainers.
2. Transactional producer được cấu hình thật, không chỉ mock KafkaTemplate.
3. Consumer dùng **read_committed**, có \`enable.auto.commit=false\` và group ID riêng cho mỗi test.
4. Topic và test key không trộn lẫn dữ liệu từ các test khác.
5. Chờ đồng bộ theo kết quả record/offset có timeout, không dùng \`Thread.sleep\` để đoán commit.
6. Phân biệt rõ \`send\`, \`commit\`, \`abort\` và lúc consumer poll.
7. Có test cả **commit success**, **abort**, và **commit failure/uncertain outcome**.
8. Không giả định Kafka broker test mặc định nhiều replica giống production.

Với broker đơn trong test, Kafka transaction coordinator cần internal topic \`__transaction_state\`. Trên một cluster một broker, có thể cần:

~~~properties
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
transaction.state.log.num.partitions=1
offsets.topic.replication.factor=1
~~~

Những giá trị này phù hợp cho **integration test một broker**, **không phải** cấu hình reliability khuyến nghị cho production. Cluster thật cần replication, min ISR và availability được thiết kế theo SLA.

## 5. Lựa chọn EmbeddedKafka hay Testcontainers

| Đặc điểm | EmbeddedKafka | Testcontainers với Kafka |
|---|---|---|
| Khởi động | Broker chạy cùng bộ test theo hạ tầng Spring Kafka Test | Kafka chạy trong container |
| Phù hợp | Test integration nhanh cho producer/consumer/transaction | Test gần môi trường triển khai và network hơn |
| Phụ thuộc Docker | Thường không | Có |
| Kiểm tra commit/abort | Có | Có |
| Mô phỏng crash/network partition | Hạn chế hơn | Có thể kết hợp proxy/chaos tools |
| Chênh lệch production | Cần xem broker version và cấu hình | Có thể pin Kafka image/version tương ứng |
| Test nhiều broker | Có thể cấu hình, nhưng phức tạp hơn | Dùng topology phù hợp với test |

**EmbeddedKafka** đủ để chứng minh logic transaction commit/abort của producer. **Testcontainers** đặc biệt hữu ích khi cần kiểm tra sự cố broker, network, coordinator và cấu hình gần production.

Trong bài này ta viết test chạy broker qua \`@EmbeddedKafka\` trước, sau đó trình bày kịch bản mở rộng với container và fault injection.

## 6. Dependencies của dự án test

Ví dụ Gradle cho Spring Boot đã có plugin và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

Với Maven, dependency tương ứng gồm \`spring-kafka-test\` ở scope test. Cần bảo đảm **spring-kafka, spring-kafka-test, kafka-clients** cùng bộ version được framework quản lý; tránh trộn những version không tương thích.

Một số project Spring Boot dùng \`spring-boot-starter-kafka\` tùy thế hệ release; nếu starter đó có sẵn trong BOM tương ứng thì có thể dùng. Điểm bắt buộc cho ví dụ test ở đây là \`spring-kafka\` và \`spring-kafka-test\`.

## 7. Cấu hình transactional producer

Trong Spring Kafka, \`DefaultKafkaProducerFactory\` có thể tạo transactional producers khi được cấp **transactionIdPrefix**.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

public class KafkaTxProducerSetup {

    public static ProducerFactory<String, String> producerFactory(
            String bootstrapServers) {

        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.ACKS_CONFIG, "all");

        DefaultKafkaProducerFactory<String, String> factory =
                new DefaultKafkaProducerFactory<>(props);

        factory.setTransactionIdPrefix(
                "order-service-test-" + UUID.randomUUID() + "-");
        return factory;
    }

    public static KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> factory) {
        return new KafkaTemplate<>(factory);
    }
}
~~~

Trong ví dụ, prefix được sinh **một lần khi tạo factory** để cô lập một instance test khỏi instance khác. **Không sinh transactional ID mới mỗi lần gửi record** trong ứng dụng cần reuse/fencing có kiểm soát: lifecycle của transactional producer và prefix phải được quản lý ở phạm vi application instance.

Ở production, prefix nên **duy nhất giữa các instance đang chạy đồng thời** để tránh fencing ngoài ý muốn; đồng thời phải có chính sách quản lý identity khi instance cũ bị thay thế. Nếu để hai process hoạt động dùng cùng một transactional.id, producer cũ có thể bị fencing.

Với Spring Boot auto-configuration, một cách khai báo phổ biến là:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    producer:
      acks: all
      transaction-id-prefix: orders-service-instance-a-
~~~

Đây là **config minh họa**; trong Kubernetes/đa instance, không hardcode cùng prefix cho tất cả pod. Cơ chế đảm bảo duy nhất cần đi cùng deployment identity và chính sách Spring Kafka phiên bản đang dùng.

Việc kích hoạt transactional producer không tự bảo đảm listener container cũng quản lý **offsets trong cùng Kafka transaction**. Trường hợp đó cần cấu hình riêng ở phần consume-process-produce.

## 8. Test commit/abort với EmbeddedKafka

Đây là phần thực hành cốt lõi. Bộ test chạy một broker Embedded Kafka, cấu hình transactional producer thật, thực hiện commit/abort rồi poll bằng consumer có isolation level rõ ràng.

### 8.1. Test configuration

~~~java
package com.example.kafka.tx;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

@Configuration
public class TxTestConfiguration {

    @Bean
    public ProducerFactory<String, String> txProducerFactory(
            EmbeddedKafkaBroker broker) {

        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                broker.getBrokersAsString());
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.ACKS_CONFIG, "all");

        DefaultKafkaProducerFactory<String, String> factory =
                new DefaultKafkaProducerFactory<>(props);
        factory.setTransactionIdPrefix(
                "tx-it-" + UUID.randomUUID() + "-");

        return factory;
    }

    @Bean
    public KafkaTemplate<String, String> txKafkaTemplate(
            ProducerFactory<String, String> txProducerFactory) {
        return new KafkaTemplate<>(txProducerFactory);
    }
}
~~~

Ở đây Spring Kafka test tự cấp **EmbeddedKafkaBroker** qua context khi dùng \`@EmbeddedKafka\`. Prefix duy nhất trên factory giúp các lần chạy test khác nhau hạn chế fencing do reuse identity.

### 8.2. Test class: commit nhìn thấy, abort không nhìn thấy

~~~java
package com.example.kafka.tx;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = TxTestConfiguration.class)
@EmbeddedKafka(
    partitions = 1,
    topics = {"tx.practice.records"},
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1",
        "transaction.state.log.num.partitions=1",
        "offsets.topic.replication.factor=1"
    }
)
class KafkaTransactionCommitIT {

    private static final String TOPIC = "tx.practice.records";

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker broker;

    @Test
    void committedRecordIsVisibleToReadCommittedConsumer() {
        String key = "commit-" + UUID.randomUUID();

        kafkaTemplate.executeInTransaction(operations -> {
            operations.send(TOPIC, key, "ORDER_CREATED").join();
            return null;
        });

        assertTrue(containsKey(key, "read_committed",
                Duration.ofSeconds(10)));
    }

    @Test
    void abortedRecordIsHiddenFromReadCommittedConsumer() {
        String key = "abort-" + UUID.randomUUID();

        assertThrows(IllegalStateException.class,
                () -> kafkaTemplate.executeInTransaction(operations -> {
                    operations.send(TOPIC, key, "ORDER_CREATED").join();
                    throw new IllegalStateException("FAIL_BEFORE_COMMIT");
                }));

        assertFalse(containsKey(key, "read_committed",
                Duration.ofSeconds(3)));
    }

    @Test
    void readUncommittedCanObserveAbortedRecord() {
        String key = "aborted-debug-" + UUID.randomUUID();

        assertThrows(IllegalStateException.class,
                () -> kafkaTemplate.executeInTransaction(operations -> {
                    operations.send(TOPIC, key, "ORDER_CREATED").join();
                    throw new IllegalStateException("FORCE_ABORT");
                }));

        assertTrue(containsKey(key, "read_uncommitted",
                Duration.ofSeconds(10)));
        assertFalse(containsKey(key, "read_committed",
                Duration.ofSeconds(3)));
    }

    private boolean containsKey(
            String expectedKey, String isolation, Duration timeout) {

        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                broker.getBrokersAsString());
        props.put(ConsumerConfig.GROUP_ID_CONFIG,
                "tx-it-consumer-" + UUID.randomUUID());
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, isolation);

        try (KafkaConsumer<String, String> consumer =
                new KafkaConsumer<>(props)) {

            consumer.subscribe(List.of(TOPIC));
            long deadline = System.nanoTime() + timeout.toNanos();

            while (System.nanoTime() < deadline) {
                var records = consumer.poll(Duration.ofMillis(250));
                for (var record : records) {
                    if (expectedKey.equals(record.key())) {
                        return true;
                    }
                }
            }
            return false;
        }
    }
}
~~~

**Giải thích cách test hoạt động:**

- \`executeInTransaction\` mở transaction, chạy callback, commit khi callback trả về bình thường hoặc cố abort khi callback ném exception.
- \`operations.send(...).join()\` chờ Kafka ACK việc gửi record trong transaction. Đây **chưa phải commit**.
- Mỗi test dùng một **message key ngẫu nhiên**; test không phụ thuộc vào record của test khác.
- Mỗi consumer dùng group ID mới và \`auto.offset.reset=earliest\` để đọc log từ đầu rồi lọc theo test key.
- \`read_committed\` chỉ thấy record thuộc transaction đã commit (hoặc record không transactional).
- \`read_uncommitted\` có thể thấy cả record thuộc transaction đã abort, nên **không dùng nó để chứng minh exactly-once visibility**.
- Poll dùng **deadline hữu hạn**, không \`Thread.sleep\` đoán trạng thái broker.

### Lưu ý về kiểm thử âm tính

Một assertion **“không thấy key trong 3 giây”** chỉ có ý nghĩa khi đã chứng minh producer gửi record thành công trước khi abort và test consumer đã đọc đúng topic/partition. Ở đây \`send(...).join()\` được đặt trước exception, giúp phân biệt “không thấy vì transaction abort” với “không thấy vì record chưa bao giờ được gửi”.

Với môi trường CI tải cao, nên tăng timeout có kiểm soát và có test dương đi kèm. Có thể kiểm tra record bằng read_uncommitted trong cùng kịch bản để chứng minh log chứa record đã abort.

### Test có phải lúc nào cũng thấy các record từ giao dịch khác?

Không. Một consumer \`read_committed\` có thể tạm bị giới hạn bởi **Last Stable Offset** nếu trên partition còn transaction mở ở offset thấp hơn. Bộ test trên chờ transaction kết thúc trước khi poll, vì vậy giảm rủi ro này. Với các test đồng thời dùng chung topic, giao dịch đang mở của test khác có thể làm kiểm thử flaky; tốt nhất cô lập topic/broker hoặc không chạy song song tùy cấu hình test.

## 9. Test nhiều record trong cùng một transaction

Một transaction có thể gửi nhiều record rồi commit. Test cần xác minh **cả tập**, không chỉ một record:

~~~java
String transactionKey = "order-" + UUID.randomUUID();

kafkaTemplate.executeInTransaction(operations -> {
    operations.send("tx.orders", transactionKey,
            "ORDER_CREATED").join();
    operations.send("tx.audit", transactionKey,
            "AUDIT_CREATED").join();
    return null;
});
~~~

Trong test này, cần tạo sẵn hai topic **tx.orders** và **tx.audit**. Sau callback commit, consumer read_committed trên mỗi topic phải thấy record tương ứng cùng key. Với kịch bản abort, không topic nào được trả record của giao dịch đó cho consumer read_committed.

Một giao dịch Kafka có thể bao trùm nhiều topic/partition, nhưng **thứ tự toàn cục giữa các partition không được bảo đảm**. Test chỉ nên assert số lượng và tập key/value theo từng partition hoặc business correlation, không suy ra consumer ở hai partition sẽ nhận theo cùng một thứ tự tuyệt đối.

### Không chỉ assert số record

Một test có thể có hai record nhưng một record sai key, value hoặc topic. Nên kiểm tra:

| Kiểm tra | Lý do |
|---|---|
| Topic đúng | Không publish nhầm destination |
| Key đúng | Giữ partitioning và business correlation |
| Value/schema đúng | Transaction atomic không bảo đảm payload đúng |
| Số record đúng | Không mất hoặc ghi trùng trong contract |
| read_committed visibility | Chứng minh record đã commit |
| Không visible khi abort | Chứng minh isolation |
| Không có partial output giữa nhiều topic | Chứng minh transaction boundary khi broker hỗ trợ |

## 10. Consumer read_committed và read_uncommitted

Hãy tưởng tượng topic có những record:

~~~text
offset 0: non-transactional A
offset 1: TX-1 record B
offset 2: TX-1 record C
offset 3: TX-1 ABORT marker
offset 4: TX-2 record D
offset 5: TX-2 COMMIT marker
~~~

Đây là sơ đồ khái niệm; marker và vị trí thực trong log phụ thuộc Kafka internals.

| Consumer isolation | Business records có thể được trả về |
|---|---|
| \`read_uncommitted\` | A, B, C, D |
| \`read_committed\` | A, D |

Consumer \`read_committed\` **không nhất thiết nhận offset liên tiếp** vì transactional data bị abort và control records vẫn chiếm vị trí trong Kafka log. Vì vậy, đừng viết test kỳ vọng offset của hai business record thành công luôn tăng đúng một.

Khi còn một transaction **đang mở**, read_committed consumer có thể chưa thấy record ở phía sau Last Stable Offset dù chúng có vẻ đã có trong log. Trong test, phải tính đến hành vi này để tránh diễn giải nhầm thành lỗi commit.

## 11. KafkaTemplate.executeInTransaction và KafkaTransactionManager

Spring Kafka hỗ trợ nhiều cách quản lý transaction:

**Local transaction**: \`KafkaTemplate.executeInTransaction(callback)\` mở và kết thúc transaction quanh callback trên transactional ProducerFactory. Phù hợp để test commit/abort ở phần trên.

**Spring-managed transaction**: \`KafkaTransactionManager\` có thể được dùng với \`@Transactional\` và các cấu hình KafkaTemplate/container phù hợp. Khi đó Spring quản lý transaction theo scope của method hoặc listener.

Ví dụ bean transaction manager:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Bean
public KafkaTransactionManager<String, String> kafkaTransactionManager(
        ProducerFactory<String, String> txProducerFactory) {

    return new KafkaTransactionManager<>(txProducerFactory);
}
~~~

Khi dùng \`@Transactional\`, cần chọn đúng transaction manager trong ứng dụng có cả database và Kafka. Nếu context có nhiều PlatformTransactionManager, một annotation không chỉ định có thể chọn manager không như mong muốn.

Không nên **lồng \`executeInTransaction\` tùy tiện** bên trong scope đang có Kafka transaction và giả định chúng là một transaction duy nhất. Local transaction có lifecycle riêng theo semantics KafkaTemplate; hãy quyết định rõ component nào sở hữu transaction boundary và test riêng điều đó.

## 12. Consume-process-produce: output và offset phải commit cùng nhau

Một trường hợp reliability quan trọng hơn producer đơn lẻ:

~~~text
orders.input
      |
      v
@KafkaListener
      |
      v
Process order
      |
      v
KafkaTemplate.send(orders.enriched)
      |
      v
Kafka transaction COMMIT:
  - output record được commit
  - offset của orders.input được commit vào cùng transaction
~~~

Nếu listener thành công và transaction commit, input record được đánh dấu đã xử lý đối với consumer group và output xuất hiện cho read_committed downstream.

Nếu listener ném exception trước commit, Kafka transaction được abort theo cơ chế container, các output record chưa commit không visible với read_committed, và consumer group offset **không được commit như một phần của transaction thất bại**. Container/error handler có thể seek/retry theo chính sách, khiến input được xử lý lại.

Điều quan trọng là cần **Kafka-aware transaction manager tại listener container**; chỉ cấu hình KafkaTemplate.transactionIdPrefix chưa tự bảo đảm listener offsets có cùng transaction.

### Cấu hình listener container (minh họa Spring Kafka 3.2+)

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config
        .ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
transactionalKafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory,
        KafkaTransactionManager<String, String> txManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(txManager);
    return factory;
}
~~~

Ở một số phiên bản Spring Kafka cũ hơn, API container transaction manager có tên **setTransactionManager**. Đây là chỗ cần xác nhận theo phiên bản dự án. ConsumerFactory nên dùng:

~~~properties
enable.auto.commit=false
isolation.level=read_committed
~~~

Trong Spring Kafka listener container, commit offsets và quản lý retry/seek có semantics riêng; không tự gọi \`consumer.commitSync()\` bên trong listener được quản lý transactional với giả định nó sẽ gộp vào Kafka transaction.

### Listener minh họa

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.stereotype.Component;

@Component
public class OrderTransformListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderTransformListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders.input",
        groupId = "orders-transformer",
        containerFactory =
            "transactionalKafkaListenerContainerFactory"
    )
    public void onOrder(
            String value,
            @Header(KafkaHeaders.RECEIVED_KEY) String key) {

        if ("FAIL_BEFORE_COMMIT".equals(value)) {
            throw new IllegalStateException("TRANSFORM_FAILED");
        }

        kafkaTemplate.send("orders.enriched", key,
                "ENRICHED:" + value);
    }
}
~~~

Code minh họa giả định KafkaTemplate và listener container cùng sử dụng transactional ProducerFactory/transaction context thích hợp. **Không sử dụng cách này để khẳng định đã có exactly-once ở một database bên ngoài**. Nếu cần xử lý poison message, hãy cấu hình failure/recovery policy có giới hạn để tránh listener thử lại vô hạn.

## 13. Kiểm thử commit offset với listener thật

Để chứng minh transaction của consume-process-produce, không chỉ kiểm tra output; cần kiểm tra **input consumer group offset** có thay đổi hay không.

Ví dụ một record ở topic \`orders.input\`, partition 0, offset 10:

~~~text
Input offset = 10

Case SUCCESS
  Listener xử lý -> send output
  Kafka TX COMMIT
  Output visible với read_committed
  Group committed offset = 11

Case FAILURE BEFORE COMMIT
  Listener send output rồi ném exception
  Kafka TX ABORT
  Output không visible với read_committed
  Group committed offset không tiến thành 11 do TX lỗi
  Input có thể được redeliver/retry
~~~

Trong Kafka, **committed offset là vị trí kế tiếp cần đọc**, nên sau xử lý thành công offset 10, group offset thường trở thành 11. Test phải tính chính xác partition, assignment, record đầu vào và groupId.

### Quy trình integration test

1. Tạo input/output topics trong EmbeddedKafka hoặc Testcontainers.
2. Tạo listener container transactional dùng consumer group **tx-orders-test-...** riêng.
3. Gửi một input record rồi chờ listener xử lý bằng \`CountDownLatch\` hoặc cơ chế điều kiện có timeout.
4. Với **success path**, đọc output bằng read_committed và xác minh key/value.
5. Dùng **AdminClient** hoặc consumer metadata API kiểm tra committed offset của group tại partition tương ứng.
6. Với **failure path**, buộc listener ném exception **sau khi send nhưng trước khi trả về thành công**.
7. Chặn hoặc giới hạn redelivery trong test để quan sát trạng thái abort; xác minh output chưa visible và group offset chưa tiến do transaction lỗi.
8. Cho xử lý lần tiếp theo thành công, xác minh **một output committed cuối cùng**, offset được commit và không có duplicate visible.

Một test failure path phải kiểm soát chính sách **AfterRollbackProcessor**, error handler và thời điểm redelivery. Nếu không, listener có thể retry thành công quá nhanh, khiến lúc test đọc offset thì đã thấy commit mới; khi đó assertion “offset chưa tiến” không còn nói về lần thử thất bại ban đầu.

### Dùng AdminClient xem committed offsets

Ví dụ ý tưởng:

~~~java
import java.util.Set;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.TopicPartition;

// adminClient được tạo với bootstrap.servers phù hợp.
var offsets = adminClient.listConsumerGroupOffsets(
        "orders-transformer-test-group")
        .partitionsToOffsetAndMetadata()
        .get();

var metadata = offsets.get(
        new TopicPartition("orders.input", 0));

// metadata.offset() là next offset đã commit khi metadata != null.
~~~

Đoạn này chỉ minh họa cách đọc offset; cần tạo/đóng AdminClient và đồng bộ nhóm consumer trong test. Không nên lấy offset đầu tiên bằng một số hardcode nếu broker/topic có thể đã chứa record từ test khác.

## 14. Test rollback sau khi đã send output

Một lỗi quan trọng cần thử: listener **đã gọi KafkaTemplate.send(...)** nhưng sau đó exception xuất hiện.

~~~text
Input O101
  |
  v
Listener -> send output O101
  |
  v
Exception trước khi listener hoàn tất
  |
  v
Kafka TX ABORT
  |
  +-- Output O101: không visible với read_committed
  |
  +-- Input offset: không commit như TX thành công
~~~

Nếu chỉ mock \`KafkaTemplate.send\` rồi verify method gọi một lần, test **không chứng minh rollback visibility**. Phải dùng Kafka broker thật và read_committed consumer.

Để test có thể lặp lại, một biến điều khiển **fail once** có thể ném exception ở lần xử lý đầu, sau đó cho phép lần thứ hai thành công:

~~~java
private final AtomicBoolean failOnce = new AtomicBoolean(true);

// Trong listener demo/test:
kafkaTemplate.send("orders.enriched", key,
        "ENRICHED:" + value);
if (failOnce.compareAndSet(true, false)) {
    throw new IllegalStateException("FAIL_AFTER_SEND");
}
~~~

Nếu triển khai listener thực sự như vậy, cần xác định concurrency và phân vùng state test để không dùng \`failOnce\` chung cho record không liên quan. Khi broker read_committed cuối cùng thấy **một output**, test vẫn nên bổ sung quan sát **aborted transaction marker/metrics hoặc điều khiển hai pha** để biết output lần đầu không trở thành committed, thay vì chỉ kết luận từ tổng count.

## 15. Chọn đúng transaction boundary trong Spring

Có hai khái niệm dễ nhầm:

1. **Transaction của Kafka producer:** commit/abort record được ghi vào Kafka và có thể bao gồm consumer offsets.
2. **Transaction của database:** commit/rollback SQL/JPA.

Ví dụ:

~~~text
Business method
   |
   +-- INSERT order into PostgreSQL
   |
   +-- KafkaTemplate.send(order-created)
   |
   v
method returns
~~~

Một annotation \`@Transactional\` **không tự làm PostgreSQL và Kafka trở thành một transaction XA duy nhất**. Spring có thể đồng bộ thứ tự commit qua transaction managers, nhưng vẫn có crash window khiến một resource đã commit còn resource kia chưa.

### Kịch bản DB-first

~~~text
DB transaction commits
        |
        v
Application crashes
        |
        X
Kafka transaction chưa commit
~~~

Kết quả: database có bản ghi nhưng Kafka consumer chưa thấy event.

### Kịch bản Kafka-first

~~~text
Kafka transaction commits
        |
        v
DB transaction fails
        |
        X
Kafka event đã visible
~~~

Kết quả: Kafka có event dù DB chưa xác nhận thay đổi tương ứng.

**Test commit Kafka chỉ chứng minh atomicity của Kafka transaction**, không chứng minh tính nguyên tử giữa Kafka và SQL database.

### Transactional outbox

Đối với quy trình DB + event quan trọng, một lựa chọn được dùng rộng rãi là:

~~~text
Business DB transaction:
   INSERT order
   INSERT outbox_event(order_id, event_type, payload)
   COMMIT
        |
        v
Outbox publisher / CDC
        |
        v
Kafka publish
        |
        v
Consumer idempotency by eventId
~~~

Outbox giúp biến việc ghi dữ liệu nghiệp vụ và ghi yêu cầu phát event thành **một transaction DB**. Publisher vẫn có thể gửi lặp sau khi broker nhận message nhưng ACK bị mất, nên consumer cần dedup/idempotency. Đây không phải bảo đảm Kafka + DB exactly-once end-to-end tự động.

## 16. Test commit khi có database

Với service vừa ghi DB vừa phát Kafka, cần thêm các tình huống ngoài Kafka-only test:

| Kịch bản | DB | Kafka | Điều cần assert |
|---|---|---|---|
| Happy path | Commit | Commit | Row và event nhất quán |
| DB fails before commit | Rollback | Chưa publish/abort theo orchestration | Không có event business được công bố sai |
| DB commit, Kafka fail | Commit | Không commit | Gap được audit/reconcile/outbox |
| Kafka commit, DB fail | Rollback | Commit | Có cảnh báo/compensation theo thiết kế |
| Process crash giữa hai commits | Có thể một bên đã commit | Bên kia chưa rõ | Recovery không làm mất event hay duplicate không kiểm soát |
| Outbox publisher retry | Order + outbox committed | Publish có thể lặp | Event ID dedup và outbox state đúng |

Một test đúng phải chỉ rõ **kiến trúc đang lựa chọn** (DB-first, Kafka-first, outbox). Không assert rằng cả hai đều rollback khi chưa có cơ chế distributed transaction phù hợp.

### Ví dụ outbox schema

~~~sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(64) PRIMARY KEY,
    aggregate_id   VARCHAR(64) NOT NULL,
    event_type     VARCHAR(64) NOT NULL,
    payload        TEXT NOT NULL,
    publish_status VARCHAR(20) NOT NULL
);
~~~

Test có thể xác minh khi DB transaction rollback, cả business row và outbox row đều vắng mặt; khi commit, cả hai cùng tồn tại. Sau đó test publisher riêng để chứng minh event đến Kafka và tiêu thụ idempotent khi gửi lại.

## 17. Transaction timeout và producer fencing

Kafka transaction có các giới hạn vận hành:

- **transaction.timeout.ms**: thời gian broker cho phép transaction mở trước khi timeout/abort theo cơ chế Kafka.
- **max.block.ms** và request/delivery timeouts: giới hạn các thao tác của producer, có thể tác động tới latency và failure.
- **transactional.id**: identity để coordinator quản lý producer epoch và fencing.
- **transactional.id.expiration.ms**: chính sách của broker liên quan expiration của transactional IDs; cần hiểu trước khi dựa vào fencing cho hệ thống lâu không hoạt động.

Không giữ transaction mở khi gọi một HTTP API có thể treo hàng chục phút mà không có timeout. Transaction dài có thể gây ảnh hưởng visibility của read_committed consumer do LSO, lock tài nguyên producer và làm recovery khó hơn.

### Producer fencing

Nếu hai producer khác nhau khởi tạo transaction với **cùng transactional.id**, producer mới có thể làm producer cũ bị fencing. Producer cũ không còn quyền commit như một owner hợp lệ.

~~~text
Producer A: transactional.id = orders-instance-1
    |
    v
Producer B starts with same transactional.id
    |
    v
Coordinator advances producer epoch
    |
    v
Producer A: fenced, không được tiếp tục transaction hợp lệ
~~~

Đây là cơ chế bảo vệ ownership chứ không phải sự cố ngẫu nhiên cần retry vô hạn. **ProducerFencedException** thường yêu cầu đóng producer cũ và xử lý lifecycle/identity, không tiếp tục dùng cùng instance như một transient network error.

### Test fencing

Một integration test riêng có thể:

1. Tạo hai KafkaProducer với cùng một \`transactional.id\`.
2. Producer A \`initTransactions\` và bắt đầu giao dịch.
3. Producer B \`initTransactions\` với cùng identity.
4. Cho A thực hiện thao tác giao dịch/commit và quan sát lỗi fencing phù hợp.
5. Xác minh không có transaction A đã bị fencing nào trở thành output hợp lệ ngoài kỳ vọng.
6. Đóng producers trong finally.

Do thời điểm broker cập nhật epoch và network response ảnh hưởng exception cụ thể, không hardcode chỉ một stack trace message duy nhất làm tiêu chí. Cần dựa trên class/lifecycle và visibility outcome.

## 18. Mô phỏng lỗi ở thời điểm commit

Có ba mốc khác nhau:

~~~text
1. BEFORE COMMIT:
   Callback đã send nhưng chưa gọi commit

2. DURING COMMIT:
   Commit request đã gửi, ACK có thể mất

3. AFTER COMMIT:
   Broker đã commit, ứng dụng gặp lỗi ở bước tiếp theo
~~~

### Lỗi trước commit

Test abort bằng cách ném exception trong callback \`executeInTransaction\` như phần 8. Đây là trường hợp dễ điều khiển, có thể khẳng định transaction được cố abort theo Spring Kafka semantics và đọc lại để xác minh.

### Lỗi sau commit

Ví dụ:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("tx.practice.records", key,
            "COMMITTED").join();
    return null;
});

// Transaction đã commit trước khi chạy dòng tiếp theo.
throw new IllegalStateException("FAIL_AFTER_COMMIT");
~~~

Exception ở cuối **không rollback Kafka transaction đã hoàn tất**. Test cần xác minh record vẫn visible với read_committed.

### Lỗi trong lúc commit: outcome không rõ

Một giả lập broker crash hoặc network cut đúng lúc client chờ ACK của \`commitTransaction()\` có thể tạo **ambiguous outcome** từ góc nhìn client. Không kết luận “producer nhận exception nên broker chắc đã abort”.

Để mô phỏng gần thực tế, dùng:

- Kafka qua Testcontainers và một proxy mạng có khả năng điều khiển đường kết nối.
- Cách chặn/kích hoạt failure ở request commit được test harness hỗ trợ.
- Log broker/coordinator và consumer read_committed ở bước kiểm tra sau khi cluster ổn định.
- Correlation key duy nhất để xác minh transaction thực tế có visible hay không.
- Logic phục hồi có thể chấp nhận cả trường hợp **commit đã thành công** và trường hợp **commit chưa thành công**.

Không coi một mock \`KafkaTemplate.send\` ném exception là mô phỏng commit failure thật. **Send failure** và **commit failure** xảy ra ở các ranh giới khác nhau.

## 19. Testcontainers cho các tình huống broker lỗi

Testcontainers hữu ích khi cần pin một phiên bản Kafka và tạo môi trường độc lập. Ví dụ Gradle:

~~~groovy
dependencies {
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

Ví dụ cấu trúc test dùng Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class KafkaTxContainerIT {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer(
                    DockerImageName.parse("apache/kafka:3.8.0"));

    @Test
    void committedRecordIsVisible() {
        String bootstrapServers = kafka.getBootstrapServers();
        // Tạo transactional ProducerFactory từ bootstrapServers.
        // Tạo topic, send qua executeInTransaction, verify read_committed.
    }
}
~~~

Tag **apache/kafka:3.8.0** chỉ là ví dụ cho test có image version cố định; chọn version tương thích với client và runtime thực của dự án. Class/package Testcontainers thay đổi theo phiên bản; kiểm tra dependency và API khi áp dụng.

**Testcontainers không tự mô phỏng commit ACK loss.** Nếu test chỉ start KafkaContainer rồi gọi commit, đó vẫn chủ yếu là happy-path integration test. Muốn kiểm tra ambiguity cần kịch bản fault injection cụ thể, chẳng hạn network proxy hoặc broker interruption có kiểm soát.

## 20. Không dùng sleep để kết luận commit đã xảy ra

Phản mẫu:

~~~java
kafkaTemplate.send(topic, key, value);
Thread.sleep(500);
assertTrue(consumed);
~~~

Sai vì:

- \`send\` có thể chưa được broker ACK.
- Record có thể thuộc transaction chưa commit.
- 500 ms tùy tải máy và broker.
- Consumer chưa chắc được assign partition.
- Test không kiểm soát isolation level.

Thay bằng:

1. Chờ \`send(...).join()\` khi cần xác nhận broker ACK record trong transaction.
2. Kết thúc transaction qua \`executeInTransaction\` hoặc transaction manager.
3. Poll bằng \`read_committed\` consumer với **timeout hữu hạn**.
4. Lọc bằng test key hoặc topic riêng.
5. Với listener, dùng latch, Awaitility hoặc điều kiện offset/output thay vì sleep cứng.

**Send ACK không thay thế commit verification.** Test cần có bước thứ ba.

## 21. Ma trận kiểm thử tin cậy

| ID | Kịch bản | Expected result |
|---|---|---|
| TX-01 | Một record và commit thành công | read_committed thấy record |
| TX-02 | Hai record cùng transaction, commit | read_committed thấy đủ hai record |
| TX-03 | Send rồi exception trước commit | Transaction abort; read_committed không thấy record |
| TX-04 | Record abort với read_uncommitted | Có thể nhìn thấy record đã abort |
| TX-05 | Transaction trên hai topics | Commit/abort cả tập đúng |
| TX-06 | Listener xử lý thành công | Output visible + input group offset được commit |
| TX-07 | Listener send rồi throw | Output abort; input offset không commit bởi attempt lỗi |
| TX-08 | Listener fail once rồi thành công | Redelivery và một kết quả committed cuối |
| TX-09 | Producer fencing | Producer cũ không commit hợp lệ sau khi bị fenced |
| TX-10 | Transaction timeout | Transaction dài bị xử lý theo broker policy |
| TX-11 | Exception sau commit | Record vẫn visible, không bị rollback |
| TX-12 | Network drop lúc commit | Outcome phải được kiểm tra, không suy đoán từ client exception |
| TX-13 | DB commit rồi Kafka fail | Test phát hiện consistency gap/outbox recovery |
| TX-14 | Kafka commit rồi DB fail | Test không giả định DB rollback đã hủy Kafka event |
| TX-15 | Producer restart cùng identity theo policy | Fencing/recovery diễn ra có kiểm soát |
| TX-16 | Consumer đang dùng read_uncommitted | Test chứng minh isolation khác với read_committed |
| TX-17 | Multi-partition cùng transaction | Không giả định thứ tự tuyệt đối giữa partitions |
| TX-18 | Broker/consumer restart | Output và offsets vẫn đúng sau recovery |

Mỗi case nên có:

- Topic và partition cụ thể.
- Transaction key/correlation ID duy nhất.
- Producer identity và transaction policy.
- Isolation level của consumer dùng để assert.
- Group ID, input offset và expected committed offset khi liên quan.
- Điểm fault injection chính xác.
- Timeout hữu hạn và cleanup resources.
- Kết quả bền vững đã quan sát, không chỉ log của application.

## 22. Test transaction commit và retry/DLT

Spring Kafka có các cơ chế retry, error handler, DefaultAfterRollbackProcessor và Dead Letter Topic (DLT). Khi listener container chạy transactional, một số lỗi được xử lý bằng **rollback + seek/redelivery**, khác với xử lý lỗi trong container không transaction.

Nếu một record gây lỗi vĩnh viễn:

~~~text
Input record
    |
    v
Listener throws
    |
    v
Kafka TX ABORT
    |
    v
AfterRollbackProcessor / recovery policy
    |
    +-- Retry có giới hạn
    |
    +-- Recovery / DLT theo cấu hình
~~~

Để tránh vòng lặp vô hạn, test phải xác định số lần retry và điều kiện đưa record sang DLT. Nếu dùng DLT, hãy kiểm tra:

- Record có đúng key/value/headers được phép.
- Output chính không visible nếu transaction xử lý thất bại.
- Khi recovery quyết định bỏ qua record, consumer group offset được xử lý đúng theo cơ chế recovery đã cấu hình.
- Việc publish DLT có transaction riêng hay không, và transaction nào sở hữu commit.
- Không log payload nhạy cảm trong exception/DLT headers.

**Không giả định kết hợp mọi cơ chế non-blocking retry topic với container transactions đều được hỗ trợ như nhau.** Cần xác nhận giới hạn của phiên bản Spring Kafka và thiết kế error handling theo transaction model được tài liệu của phiên bản đó hỗ trợ.

## 23. Quan sát trạng thái transaction trong vận hành

Một log tốt cần phân biệt **send**, **commit attempt**, **committed** và **aborted**:

~~~text
event=kafka.transaction.begin
transactionRef=tx_02f1
jobExecutionId=835
topic=orders.events

event=kafka.producer.send.acked
transactionRef=tx_02f1
recordCount=2

event=kafka.transaction.committed
transactionRef=tx_02f1
recordCount=2

event=kafka.transaction.aborted
transactionRef=tx_02f2
reasonCode=BUSINESS_PROCESSING_FAILED
~~~

Các giá trị trên minh họa một schema audit ứng dụng, không phải log Kafka mặc định. Trong ứng dụng nhiều thread, cần context propagation đúng để không gắn transactionRef sai.

Nếu commit thất bại hoặc outcome không xác định, dùng trạng thái ví dụ **COMMIT_UNCONFIRMED**, không tự log **ABORTED** khi chưa có bằng chứng broker đã abort.

Các metric có thể theo dõi:

| Nhóm | Chỉ số |
|---|---|
| Producer | Transaction commit/abort rate, transaction duration, errors |
| Kafka client | Request latency, timeout/error, producer metrics |
| Consumer | Lag, read_committed visibility, committed offsets |
| Listener | Process failures, retries, redelivery, DLT count |
| Broker | Transaction coordinator health, under-replicated partitions, ISR |
| Business | Input/output reconciliation, duplicate keys, missing events |
| Operations | Time to recover, last successful publish/checkpoint |

Metric cụ thể có thể xuất qua Kafka client JMX, Micrometer/Spring Kafka instrumentation và hệ giám sát broker. Tên meter tùy version; đừng giả định mọi metric có cùng tên trên tất cả deployment.

**Không dùng transactional.id, orderId hoặc jobExecutionId động làm label Prometheus không kiểm soát**, vì sẽ tạo high cardinality; để các ID động trong log/traces/audit có retention và phân quyền phù hợp.

## 24. Runbook khi transaction commit gặp lỗi

Khi service báo commit failure hoặc consumer read_committed chưa thấy output như kỳ vọng:

1. **Xác định phạm vi:** topic, partition, key, transactional.id, producer instance, consumer group, time window.
2. **Phân biệt lỗi:** send failure, listener exception trước commit, producer fenced, transaction timeout hay commit ACK không rõ.
3. **Kiểm tra broker:** availability, transaction coordinator, ISR, replication, logs phù hợp và producer metrics.
4. **Đọc bằng read_committed consumer** với offset/partition rõ để xác định record đã được công bố chưa.
5. **Đối chiếu read_uncommitted khi cần điều tra**, nhưng không coi thấy record ở chế độ này là commit thành công.
6. **Với consume-process-produce**, kiểm tra input group committed offset và output transaction cùng nhau.
7. **Đánh giá side effects ngoài Kafka**: DB row, outbox, API receipt hoặc file đã phát hành.
8. **Xác định replay policy:** không resend mù nếu outcome không rõ và downstream không idempotent.
9. **Khôi phục có kiểm soát** bằng reprocessing, idempotency key, outbox hoặc compensation tùy kiến trúc.
10. **Đối soát kết quả cuối**, chỉ đánh dấu business event READY khi các điều kiện cần thiết đạt.

Nếu producer bị fencing, cần đóng producer cũ và điều tra identity/lifecycle. Nếu một transaction mở quá lâu, cần xem timeout và chỗ có blocking operation. Nếu output bị thiếu nhưng input offsets đã commit, cần kiểm tra liệu offset có được commit **ngoài** transaction hoặc listener container có dùng transaction manager đúng không.

### Không sửa consumer group offsets tùy tiện

Việc reset/alter offsets không tự khôi phục output đã mất và có thể làm record được xử lý lại trên diện rộng. Trước khi can thiệp, phải bảo đảm các consumer trong group được dừng/điều phối đúng, ghi nhận offset cũ và kiểm tra idempotency downstream.

## 25. Những sai lầm thường gặp

**Test chỉ verify KafkaTemplate.send được gọi.** Mock chỉ chứng minh lệnh gọi; không chứng minh broker transaction commit và read_committed visibility.

**Nhầm send ACK với commit ACK.** Broker nhận record chưa có nghĩa transaction đã commit.

**Dùng consumer read_uncommitted để assert exactly-once.** Nó có thể nhìn thấy record bị abort, cho kết quả sai.

**Không cấu hình transaction.state.log trên broker test một node.** Transactional producer có thể khởi tạo lỗi vì internal topic yêu cầu replication phù hợp.

**Dùng chung transactional.id prefix giữa các instance active.** Producer có thể tự fencing nhau.

**Dùng cùng topic/group không cách ly cho mọi test.** Dữ liệu cũ và offset cũ gây false positives hoặc false negatives.

**Thread.sleep rồi assert.** Test flaky và không xác nhận commit boundary.

**Chỉ đếm record ở một topic trong giao dịch đa topic.** Có thể bỏ qua việc producer ghi nhầm topic hoặc payload.

**Giả định offset của business records liên tiếp.** Aborted records và transaction markers vẫn chiếm vị trí log.

**Chỉ bật transaction cho producer mà không bật ở listener container.** Consume-process-produce có thể không commit input offsets vào cùng transaction.

**Tự commit consumer offset ngoài transaction.** Có thể làm mất dữ liệu khi output chưa commit.

**Kết luận DB và Kafka đã atomic vì cùng @Transactional.** Hai resource có ranh giới commit độc lập nếu không có giao thức đồng bộ phù hợp.

**Retry commit failure không rõ outcome như một send failure thông thường.** Có thể tạo duplicate nếu transaction đã commit.

**Cho rằng lỗi sau commit làm record biến mất.** Exception ứng dụng sau commit không rollback Kafka transaction đã hoàn tất.

**Không xử lý producer fencing.** Dùng tiếp producer đã bị fenced không phải recovery an toàn.

**Không giới hạn retry poison message.** Listener có thể redeliver vô hạn, tăng lag và ngăn tiến độ group.

**Bật logging raw payload/headers để debug.** Dễ rò rỉ PII, token hoặc dữ liệu nghiệp vụ vào log tập trung.

## 26. Quy trình triển khai test transaction commit

Để đưa transaction commit tests vào pipeline Spring Kafka:

1. **Chốt phạm vi bảo đảm:** Kafka producer-only hay consume-process-produce có offsets; DB/API nằm ngoài transaction nào.
2. **Tạo test broker:** EmbeddedKafka cho kiểm thử chức năng, Testcontainers cho tình huống gần production và fault injection.
3. **Cấu hình transactional producer:** prefix được quản lý, serializers và ACK phù hợp.
4. **Tạo consumer read_committed có group ID riêng:** poll với deadline và test key duy nhất.
5. **Kiểm tra happy-path commit:** verify topic/key/value và record visibility.
6. **Kiểm tra abort:** send đã ACK rồi ném exception trước commit; read_committed không thấy record.
7. **So sánh read_uncommitted:** quan sát record bị abort để xác nhận ranh giới isolation.
8. **Nếu có listener:** kiểm tra output và input offset cùng commit, rollback và redelivery có kiểm soát.
9. **Thử fencing/timeout và commit ambiguity:** không mặc định exception đồng nghĩa transaction đã rollback.
10. **Kiểm tra side effects ngoài Kafka:** DB/outbox, API, idempotency và reconciliation.
11. **Gắn log/metric/alert:** commit, abort, timeout, fencing, lag, retry và kết quả nghiệp vụ.
12. **Tích hợp CI:** timeout hữu hạn, broker/resource cleanup, tránh test chạy song song cùng transactional identity hoặc topic không được cô lập.

Một bộ test tin cậy phải chứng minh **kết quả được consumer nhìn thấy tại ranh giới transaction**, chứ không chỉ chứng minh một method được gọi. Với Spring Kafka, cặp kiểm tra **commit visible / abort invisible qua read_committed**, bổ sung kiểm tra **consumer offset trong cùng Kafka transaction** cho luồng consume-process-produce, là nền tảng quan trọng của reliability testing. Khi workflow còn đi qua database, API hoặc file, hãy giữ ranh giới bảo đảm rõ ràng và thêm idempotency, outbox, audit và reconciliation thay vì khẳng định một Kafka transaction có thể tự giải quyết mọi vấn đề nhất quán dữ liệu.
