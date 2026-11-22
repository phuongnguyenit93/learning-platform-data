# Test transaction rollback trong Spring Kafka

## 1. Mục tiêu: chứng minh điều gì khi transaction thất bại?

Trong một hệ thống xử lý event, thông báo “transaction rollback thành công” chỉ đáng tin khi chúng ta chứng minh được **hậu quả quan sát được**. Một lời gọi Java ném exception hoặc một log ghi “rollback” chưa đủ để kết luận dữ liệu thực sự an toàn.

Giả sử ứng dụng nhận sự kiện từ topic `orders.in`, xử lý rồi phát kết quả sang `orders.out`:

```text
orders.in
    |
    v
@KafkaListener
    |
    +-- kiểm tra/biến đổi event
    |
    +-- KafkaTemplate.send(orders.out)
    |
    +-- xử lý thành công hoặc ném exception
```

Với **Kafka transaction** đúng cấu hình, nếu listener ném lỗi sau khi gửi output nhưng trước khi kết thúc lần xử lý, hệ thống mong muốn:

1. Transaction Kafka đang xử lý được **abort**.
2. Bản ghi đã gửi vào `orders.out` trong transaction thất bại **không hiển thị** với consumer có `isolation.level=read_committed`.
3. Offset của bản ghi đầu vào **không được commit như một lần xử lý thành công** trong transaction đó.
4. Container có thể seek và xử lý lại bản ghi theo chính sách after-rollback/recovery.
5. Khi lần xử lý lại thành công, output được commit và offset đầu vào được commit cùng Kafka transaction thành công.

Điều này giúp kiểm thử mô hình **consume → process → produce** trong phạm vi Kafka. Nó **không tự bảo đảm exactly-once** cho database, HTTP API, email hay những side effect ngoài Kafka.

Trong ngữ cảnh **Spring Kafka Reliability Operations → Kiểm thử tin cậy**, bài học đi qua khái niệm, cấu hình, ví dụ JUnit với embedded broker, các failure point, cách xác minh offset/output và các sai lầm dễ làm test báo xanh giả.

## 2. Rollback nào đang được kiểm thử?

Từ “transaction” trong ứng dụng Spring có thể chỉ nhiều cơ chế khác nhau. Trước khi viết test, phải nêu rõ **transaction manager** và tài nguyên được bảo vệ.

| Transaction | Tài nguyên được quản lý | Rollback có thể làm gì? | Không tự làm gì? |
| --- | --- | --- | --- |
| Kafka producer transaction | Các record gửi bởi producer transactional | Abort các record chưa commit, khiến chúng vô hình với `read_committed` | Không undo HTTP/DB side effect |
| Kafka consumer-initiated transaction | Output Kafka + offset của group được gửi vào transaction | Commit hoặc abort output và offset một cách nguyên tử trong Kafka | Không bảo đảm xử lý nghiệp vụ chỉ chạy một lần |
| JDBC transaction | Các thay đổi DB tham gia cùng transaction | Rollback insert/update/delete chưa commit | Không abort producer Kafka độc lập |
| External service operation | Tùy contract API | Có thể có hành động bù hoặc idempotency | Không tự tham gia Kafka transaction |
| Spring `@Transactional` | Transaction manager được chọn | Theo chính sách của manager/propagation | Không có nghĩa mọi hệ thống cùng một ACID transaction |

Ba tình huống test tiêu biểu:

- **Producer-only:** kiểm chứng một `KafkaTemplate` transactional gửi hai record rồi lỗi; cả hai phải bị abort.
- **Consumer + producer:** listener đọc một event, gửi output rồi lỗi; output bị abort, offset chưa commit và record được xử lý lại.
- **Kafka + database:** listener vừa ghi DB vừa gửi Kafka; kiểm tra failure ở từng ranh giới, vì hai tài nguyên không tự có commit nguyên tử toàn cục.

Bài dùng tình huống thứ hai làm kịch bản chính; producer-only là bước nền dễ cô lập để hiểu nguyên tắc.

## 3. Vì sao cần isolation.level=read_committed?

Kafka có thể lưu trên log những record được gửi trong transaction nhưng sau đó **abort**. Consumer với `isolation.level=read_uncommitted` có thể quan sát cả record thuộc transaction bị abort. Trong khi đó consumer có `read_committed` chỉ trả về record đã commit hoặc record không nằm trong transaction.

```text
Kafka log của orders.out

Offset 10: BEGIN transaction T1
Offset 11: output A của T1
Offset 12: ABORT T1
Offset 13: BEGIN transaction T2
Offset 14: output B của T2
Offset 15: COMMIT T2

read_uncommitted: có thể thấy A và B
read_committed:   chỉ thấy B
```

Đoạn trên là sơ đồ khái niệm, không phải định dạng log vật lý hay cách control record được hiển thị bằng mọi công cụ. Điểm quan trọng: **test rollback phải dùng consumer `read_committed` để xác minh output nghiệp vụ không bị công bố**.

Nếu test dùng `read_uncommitted` rồi assert “không được có bất kỳ record nào trong Kafka log”, nó có thể thất bại dù transaction abort hoạt động đúng. Ngược lại, nếu chỉ kiểm tra callback Java ném exception mà không đọc output với isolation phù hợp, test chưa chứng minh được hiệu ứng giao dịch.

### Producer có cần transaction thật?

Có. Kafka producer phải có `transactional.id` hợp lệ, được Spring Kafka cấu hình qua transaction-capable `ProducerFactory` hoặc thuộc tính Boot `spring.kafka.producer.transaction-id-prefix`. Chỉ đặt `enable.idempotence=true` không biến nhiều send và offset commit thành một transaction consume-process-produce.

Idempotent producer giúp giảm duplicate do producer retry trong một số điều kiện; Kafka transactions cung cấp cơ chế **commit/abort** các write và offset được đưa vào giao dịch.

## 4. Transactional listener hoạt động như thế nào?

Khi một Spring Kafka listener container được cấu hình với `KafkaTransactionManager`, container có thể bắt đầu Kafka transaction trước khi gọi listener. Listener gửi record bằng `KafkaTemplate` dùng **cùng transaction-capable producer factory**; sau khi xử lý thành công, container gửi offset vào transaction rồi commit.

```text
KafkaListenerContainer
        |
        v
begin Kafka transaction T
        |
        v
poll record from orders.in
        |
        v
listener(record)
        |
        +-- template.send("orders.out", result)
        |
        +-- success?
              |
              +-- YES: send consumer offsets to T
              |        commit T
              |
              +-- NO:  abort T
                       invoke after-rollback recovery
                       seek/retry/redelivery as configured
```

Một số chi tiết:

- Kafka consumer **không tự trở thành transactional producer**. Kafka transaction được tạo bởi producer và dùng cơ chế gửi offset của consumer group vào transaction.
- `enable.auto.commit=false` là yêu cầu quan trọng; không để consumer tự commit offset độc lập khi container đang quản lý transaction.
- `isolation.level=read_committed` nên được đặt cho cả consumer ứng dụng và consumer xác minh output nếu cần chỉ xử lý dữ liệu committed.
- Container phải biết `KafkaTransactionManager` thực sự, không chỉ có `@Transactional` ở một method bất kỳ.
- Lỗi phải **được propagate ra khỏi listener** để container nhận biết transaction thất bại. Bắt exception rồi return bình thường có thể khiến container commit output/offset như thể thành công.

**Phạm vi bảo đảm:** Kafka có thể bảo đảm output records và input offsets trong cùng Kafka transaction. Việc thực thi Java method, đọc DB hoặc gọi API từ listener có thể xảy ra nhiều lần khi rollback rồi redelivery. Logic xử lý và side effect cần chịu được việc gọi lại.

## 5. Setup dự án test với Spring Boot 3 và Spring Kafka 3

Các ví dụ sau dùng **Java 17+, Spring Boot 3.x, Spring Kafka 3.x**, JUnit 5 và `spring-kafka-test`. Đây là phiên bản và API minh họa; Spring Kafka 4 hoặc các phiên bản Boot khác có thể đổi method/package, nên cần dùng bộ dependency nhất quán của dự án.

### 5.1. Maven dependencies

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
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
</dependencies>
```

Giữ `spring-kafka` và `spring-kafka-test` tương thích qua dependency management của Spring Boot, không trộn ngẫu nhiên các bản Kafka client và broker.

### 5.2. application.yml cho ví dụ consumer-initiated transaction

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      transaction-id-prefix: orders-tx-
      acks: all
    consumer:
      group-id: orders-processor
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      isolation-level: read_committed
      auto-offset-reset: earliest

app:
  kafka:
    input-topic: orders.in
    output-topic: orders.out
```

Đặt `spring.kafka.producer.transaction-id-prefix` khiến Spring Boot, trong cấu hình auto-configuration phù hợp, tạo `KafkaTransactionManager` và kết nối nó với listener container factory được Boot quản lý. Đừng chỉ nhìn YAML mà kết luận transaction đã hoạt động: cần kiểm tra bean `KafkaTransactionManager`, producer factory và listener factory sử dụng đúng cấu hình.

Prefix transactional ID phải **không xung đột giữa những instance đang chạy đồng thời**. Ví dụ `orders-tx-` ở trên chỉ phù hợp làm giá trị minh họa một instance. Trong Kubernetes hoặc khi scale nhiều pod, dùng prefix theo instance được quản lý để không bị producer fencing ngoài chủ đích.

**Chú ý:** nhiều codebase tạo `ConcurrentKafkaListenerContainerFactory` hoặc `ProducerFactory` bằng tay. Khi đó, auto-configuration có thể không còn liên kết transaction manager với factory bạn sử dụng; phải gắn transaction manager theo API của phiên bản Spring Kafka dự án.

### 5.3. Vì sao không đặt auto offset commit?

Nếu consumer tự commit offset, một exception sau khi đã commit offset sẽ khiến bản ghi bị đánh dấu đã xử lý trong khi output Kafka bị abort. Điều kiện cần cho consume-process-produce transaction là **offset thuộc transaction do container điều phối**, không phải tiến độ consumer tự ghi độc lập.

## 6. Listener cố ý thất bại sau khi gửi output

Mục tiêu là tạo một test có thể kiểm soát lỗi: **lần xử lý đầu gửi output rồi ném exception; lần thứ hai gửi output và thành công**.

### 6.1. Listener minh họa

```java
package com.example.kafka;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.CountDownLatch;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class FailOnceOrderListener {

    private final KafkaTemplate<String, String> template;
    private final AtomicInteger attempts = new AtomicInteger();
    private final CountDownLatch successfulAttempt = new CountDownLatch(1);

    public FailOnceOrderListener(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    @KafkaListener(
            id = "orders-rollback-listener",
            topics = "orders.in")
    public void handle(String payload) throws Exception {
        int attempt = attempts.incrementAndGet();

        // Gửi trong transaction đã được listener container mở.
        template.send("orders.out", "order-1", payload.toUpperCase())
                .get(10, TimeUnit.SECONDS);

        if (attempt == 1) {
            throw new IllegalStateException(
                    "Simulated failure after output send");
        }

        // Latch để test biết lần xử lý lại đã tiến tới cuối listener;
        // commit transaction xảy ra SAU KHI method return.
        successfulAttempt.countDown();
    }

    public int attempts() {
        return attempts.get();
    }

    public boolean awaitSuccessfulAttempt(long timeout, TimeUnit unit)
            throws InterruptedException {
        return successfulAttempt.await(timeout, unit);
    }
}
```

**Lưu ý phạm vi của fixture:** listener đếm `attempts` bằng biến toàn cục. Nó phù hợp với integration test chỉ gửi **một event**, một partition và chạy riêng, không phải cách thực hiện xử lý lỗi theo từng event trong production. Trong test nhiều record hoặc chạy song song, dùng trạng thái theo key hoặc fault injection có kiểm soát.

Tại sao `template.send(...).get(...)` được gọi trước exception? Ta muốn broker đã nhận send thuộc transaction T1, rồi ứng dụng cố ý ném lỗi. Điều này làm test có giá trị hơn trường hợp exception xảy ra **trước khi gửi bất kỳ record nào**.

Lời gọi `get(...)` đợi kết quả send, nhưng **không commit transaction**. Nếu listener ném exception, container vẫn có thể abort T1. Việc event T1 được Kafka ghi tạm không có nghĩa consumer `read_committed` sẽ thấy nó.

### 6.2. Không dùng executeInTransaction bên trong listener transaction

Nếu container đã mở transaction, gọi:

```java
template.executeInTransaction(ops -> {
    ops.send("orders.out", payload);
    return null;
});
```

không phải cách an toàn để “tham gia đúng transaction đang có”. `executeInTransaction(...)` có semantics tạo transaction cục bộ của template, có thể là một transaction độc lập/nested so với transaction đang tồn tại; output có thể được commit **trước khi** listener ngoài ném lỗi. Để gửi output cùng transaction do listener container quản lý, dùng `template.send(...)` trực tiếp với cùng producer factory/transaction context.

Đây là một bẫy quan trọng khi kiểm thử: nếu test chỉ kiểm tra listener ném exception mà không kiểm tra output `read_committed`, việc tạo transaction độc lập có thể lọt qua.

## 7. Integration test bằng Embedded Kafka

Để xác minh rollback thật, cần một Kafka broker test chứ không chỉ mock `KafkaTemplate`. `@EmbeddedKafka` từ `spring-kafka-test` cung cấp broker chạy trong quá trình test.

### 7.1. Lớp ứng dụng tối thiểu

```java
package com.example.kafka;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KafkaReliabilityApplication {
}
```

Đặt listener ở package con cùng ứng dụng. Trong test có thể dùng `@SpringBootTest(classes = KafkaReliabilityApplication.class)` để khởi tạo Spring Kafka và bean listener.

### 7.2. Test rollback và redelivery

```java
package com.example.kafka;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@SpringBootTest(
        classes = KafkaReliabilityApplication.class,
        properties = {
            "spring.kafka.producer.transaction-id-prefix=rollback-it-",
            "spring.kafka.consumer.enable-auto-commit=false",
            "spring.kafka.consumer.isolation-level=read_committed",
            "spring.kafka.consumer.auto-offset-reset=earliest",
            "spring.kafka.listener.ack-mode=record"
        })
@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.in", "orders.out"},
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class KafkaTransactionRollbackIT {

    @Autowired
    private KafkaTemplate<String, String> template;

    @Autowired
    private EmbeddedKafkaBroker broker;

    @Autowired
    private FailOnceOrderListener listener;

    @Test
    void abortedOutputIsInvisibleAndInputIsRedelivered()
            throws Exception {

        // Producer trong ứng dụng có transaction-id-prefix.
        // Publish input trong một transaction đã commit.
        template.executeInTransaction(ops -> {
            ops.send("orders.in", "order-1", "created");
            return null;
        });

        // Đây là tín hiệu lần attempt thứ hai đã tới cuối method.
        assertTrue(listener.awaitSuccessfulAttempt(
                20, TimeUnit.SECONDS));
        assertTrue(listener.attempts() >= 2);

        Map<String, Object> consumerProps =
                KafkaTestUtils.consumerProps(
                        "verify-" + UUID.randomUUID(),
                        "false",
                        broker);

        consumerProps.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        consumerProps.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        consumerProps.put(
                ConsumerConfig.ISOLATION_LEVEL_CONFIG,
                "read_committed");
        consumerProps.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");

        try (var consumer =
                     new KafkaConsumer<String, String>(consumerProps)) {
            broker.consumeFromAnEmbeddedTopic(
                    consumer, "orders.out");

            var visible = KafkaTestUtils.getRecords(
                    consumer, Duration.ofSeconds(10));

            assertEquals(1, visible.count());
            assertEquals(
                    "CREATED",
                    visible.iterator().next().value());

            var more = KafkaTestUtils.getRecords(
                    consumer, Duration.ofMillis(500));
            assertEquals(0, more.count());
        }
    }
}
```

Trong ví dụ này:

1. Input event được publish bằng transaction độc lập do **test producer** mở và commit; listener sau đó tiêu thụ event.
2. Listener lần đầu gửi `CREATED` tới output nhưng cố ý throw.
3. Container abort transaction đầu và áp dụng cơ chế after rollback. Với một lỗi transient thành công lần hai, record được xử lý lại.
4. Lần sau listener gửi `CREATED` và return bình thường; container commit transaction thành công.
5. Consumer kiểm tra dùng `read_committed`, chỉ nhìn thấy **một** output, không nhìn thấy bản gửi của transaction bị abort.

Test này dùng cấu hình và broker thật ở mức integration, **không chỉ dùng Mockito**. Tuy nhiên nó vẫn giả định:

- Boot đã liên kết `KafkaTransactionManager` với listener container factory đang dùng.
- Broker/test environment hỗ trợ transactional producer.
- Không có event khác cùng topics hoặc listener instance khác cùng group làm thay đổi dữ liệu.
- Cơ chế after rollback cho phép record được xử lý lại; không có policy recovery khác chủ động skip quá sớm.

**Cần quan sát transaction thật:** nếu một listener factory tự định nghĩa bị bỏ sót transaction manager, test có thể ném lỗi “No transaction in process” khi template transactional gửi ngoài transaction, hoặc có behavior khác. Kiểm tra cấu hình factory nếu tích hợp không hoạt động như dự kiến.

### 7.3. Tại sao dùng latch thay vì Thread.sleep?

`Thread.sleep(5000)` không chứng minh rằng listener đã redeliver; nó chỉ đợi theo thời gian. Latch cho phép test chờ một sự kiện có ý nghĩa. Timeout của latch là giới hạn để test không treo mãi khi hệ thống lỗi.

Tuy vậy, latch được giảm **trước khi Kafka transaction commit** vì method listener chưa return. Do đó, phần assert output vẫn phải dựa vào **consumer read_committed có poll timeout** để xác minh commit; không suy diễn từ latch rằng transaction đã commit.

### 7.4. Tách test class hoặc bảo đảm isolation

Fixture dùng `AtomicInteger` và `CountDownLatch` có state. Nếu nhiều test chia sẻ cùng Spring context, broker, topic và listener bean, lần thử “đầu tiên” có thể đã xảy ra ở bài test trước. Với một suite lớn:

- Tách test vào một class/context riêng.
- Tạo topic và consumer group test có tên duy nhất khi kiến trúc cho phép.
- Reset state test theo cách an toàn hoặc dựng listener fixture theo test.
- Tránh test chạy song song mà dùng cùng topic và group.
- Dùng `@DirtiesContext` có chủ đích khi cần giải phóng toàn bộ listener/broker giữa các kịch bản.

Nếu Maven dùng hậu tố class `*IT`, cấu hình Maven Failsafe hoặc đổi tên thành `*Test` để test được runner thực thi. Không giả định `mvn test` mặc định luôn chạy mọi file `*IT.java`.

## 8. Unit/integration test producer-only rollback

Trước khi kiểm thử consumer-initiated transaction, có thể tạo một test nhỏ để thấy `KafkaTemplate.executeInTransaction` làm việc khi không có listener.

### 8.1. Rollback khi callback ném exception

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

@Test
void producerTransactionAbortsOnException() {
    assertThrows(IllegalStateException.class, () ->
            template.executeInTransaction(ops -> {
                ops.send("tx.output", "A", "first");
                ops.send("tx.output", "B", "second");
                throw new IllegalStateException("force abort");
            }));
}
```

Đoạn trên là test method nằm trong lớp test đã có transactional `KafkaTemplate` và broker topic `tx.output`. Nếu dùng chung cấu hình ví dụ trước, hãy thêm topic vào `@EmbeddedKafka` hoặc chọn một topic đã được provision.

**Assertion về exception chưa đủ.** Sau khi callback ném lỗi, mở một consumer `read_committed` mới, seek đến đầu topic test (hoặc từ offset trước test), poll trong một khoảng bounded và assert **không có record A/B nào được nhìn thấy**.

### 8.2. Transaction commit bình thường

```java
@Test
void committedProducerTransactionIsVisible() {
    template.executeInTransaction(ops -> {
        ops.send("tx.output", "C", "committed");
        return null;
    });
    // Dùng read_committed consumer để assert có record C.
}
```

Hai test đối lập cho thấy sự khác nhau giữa **abort** và **commit**. Hãy tách topic hoặc offset boundary để test commit không vô tình đọc dữ liệu từ kịch bản khác.

### 8.3. Vì sao producer-only test không chứng minh offset rollback?

`executeInTransaction` ở trên không đọc bản ghi bằng `@KafkaListener` và không gửi consumer offset vào transaction. Vì vậy nó chỉ chứng minh **record đầu ra được commit/abort**, không thể suy ra behavior redelivery của consumer group. Muốn kiểm chứng offset, phải dùng test **listener-container transaction** hoặc gọi chính xác các API gửi offset vào transaction với group metadata đúng.

## 9. Xác minh offset rollback theo đúng nghĩa

Điểm dễ gây kết luận sai: **consumer đã poll record** không đồng nghĩa offset đã được commit. Kafka consumer giữ vị trí đọc (position) trong memory, còn group committed offset nằm ở broker.

```text
Consumer position: có thể đã vượt record N sau poll
Group committed offset: offset dùng khi consumer mới join/restart
```

Khi Kafka transaction abort, offset đã được gửi vào transaction đó **không được coi là committed**. Container có thể seek hoặc khiến record được đọc lại, tùy phiên bản và recovery policy.

### 9.1. Cách kiểm chứng ở mức integration

Một test mạnh nên:

1. Sử dụng một consumer group test riêng.
2. Gửi một input event đã commit.
3. Cho listener xử lý lần đầu và throw.
4. Kiểm tra record được nhận lại (ví dụ `attempts >= 2` và cùng input key).
5. Kiểm tra output bị abort ở attempt lỗi không hiển thị bằng `read_committed`.
6. Cho attempt sau thành công và đọc **group committed offset** bằng `AdminClient.listConsumerGroupOffsets(...)` hoặc consumer mới trong cùng group ở thời điểm đã ổn định.
7. Xác minh offset sau thành công đã tiến qua bản ghi đó; nếu dùng consumer mới trong cùng group, kiểm soát rebalance và tắt/stop listener cũ trước khi quan sát để tránh race.

Việc listener nhận cùng message lần hai là bằng chứng **redelivery**, nhưng chỉ riêng nó chưa chứng minh mọi chi tiết commit offset ở broker: rebalances, seek có chủ đích và recovery policy cũng có thể tạo hành vi phát lại. Muốn khẳng định committed offset, đối chiếu metadata của group.

### 9.2. Đừng nhầm offset hiển thị trên consumer

Các API như `consumer.position(partition)` thể hiện vị trí đọc của chính consumer đó. Khi cần xác minh transaction đã commit offset của **consumer group**, phải quan sát group committed offset, không chỉ position sau poll.

Offset có thể được tiến lên **offset kế tiếp** sau bản ghi đã xử lý. Ví dụ record ở offset 5 được commit xử lý thì committed offset thường là 6. Đây là semantics thông thường của Kafka consumer offset, không phải broker “bỏ qua” bản ghi.

### 9.3. Test trước/sau rollback ở ranh giới xác định

Nếu muốn quan sát chính xác committed offset **ngay sau transaction bị abort**, không nên dùng fixture fail-once rồi lập tức retry thành công vì cửa sổ giữa hai lần rất ngắn. Có thể dùng fault injection giữ consumer ở trạng thái failure có kiểm soát, tạm dừng listener container hoặc cấu hình backoff hợp lý, rồi dùng AdminClient đo trước khi cho phép xử lý tiếp.

Không đặt một `Thread.sleep` tùy ý và coi nó là ranh giới giao dịch; dùng latch/future và điều phối thời điểm test với cơ chế container/broker cho phép.

## 10. Test các điểm lỗi khác nhau trong vòng đời transaction

Một bài test rollback đáng tin không chỉ kiểm tra một chỗ throw.

| Điểm lỗi | Ví dụ | Kết quả cần kiểm chứng |
| --- | --- | --- |
| Trước khi gửi output | Validation ném lỗi ngay | Không có output; offset chưa commit thành công |
| Sau khi gửi output, trước listener return | Lỗi mô phỏng trong ví dụ | Output transactional bị abort; record có thể redeliver |
| Trong send/ack từ broker | Broker tạm thời mất kết nối | Transaction không được báo thành công giả; quan sát failure |
| Khi commit Kafka transaction | Fencing, timeout hoặc broker lỗi | Outcome có thể cần đối soát; không tự retry side effect bừa bãi |
| Sau DB commit nhưng trước Kafka commit | Kafka commit thất bại | DB có thể đã commit; xử lý lặp có nguy cơ duplicate DB |
| Trong bước recover/DLT | DLT publish thất bại | Không được đánh dấu record đã xử lý nếu recovery chưa thành công |
| Consumer rebalance khi xử lý lâu | `max.poll.interval.ms` bị vượt | Cần kiểm chứng quyền sở hữu partition và transaction lifecycle |
| Process crash | JVM kill trước commit | Không giả định callback cleanup được gọi; xác minh outcome từ broker |

Với test các lỗi **broker/commit thực sự**, embedded Kafka có thể hữu ích cho kịch bản cơ bản nhưng không luôn đại diện đầy đủ cho một cluster production. Những trường hợp mất kết nối, restart broker, fencing và network partition nên cân nhắc thêm **Testcontainers Kafka**, fault injection có kiểm soát hoặc môi trường integration chuyên dụng.

## 11. Retry/redelivery sau rollback: tránh vòng lặp vô hạn

Một record gây lỗi có thể được đọc lại nhiều lần. Nếu lỗi là tạm thời, redelivery có thể giải quyết. Nếu lỗi là poison pill (payload không thể xử lý), lặp vô hạn sẽ làm partition không tiến lên.

Spring Kafka có cơ chế **AfterRollbackProcessor**, thường dùng `DefaultAfterRollbackProcessor` trong container transactional, để xác định cách seek/retry/recover sau rollback. Thiết kế cần:

- Xác định loại exception retryable hay non-retryable.
- Giới hạn số lần thử lại và có backoff.
- Sau khi cạn retry, quyết định fail/stop, alert hoặc publish DLT theo policy.
- Không âm thầm commit offset nếu việc recover chưa tạo ra trạng thái bền vững có thể điều tra.
- Xác minh record ở sau poison pill có thể tiếp tục được xử lý sau khi policy hoàn tất.

**Phân biệt ba khái niệm:**

| Cơ chế | Ý nghĩa | Rủi ro nếu hiểu sai |
| --- | --- | --- |
| Kafka transaction rollback | Abort output và offset của attempt thất bại | Không tự chữa dữ liệu hoặc dependency |
| Listener retry/redelivery | Gọi xử lý record lại | Có thể nhân đôi side effect ngoài Kafka |
| DLT/recovery | Đưa record không xử lý được vào đường điều tra | Nếu DLT publish fail mà offset đã commit, có thể mất dấu vết |

### 11.1. Config recovery trong transactional container

Trong Spring Kafka 3.x, ví dụ khái niệm:

```java
import org.springframework.kafka.listener.DefaultAfterRollbackProcessor;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
var afterRollback = new DefaultAfterRollbackProcessor<>(
        recoverer,
        new FixedBackOff(1000L, 2L));

// Gắn afterRollback vào Kafka listener container factory theo
// API của version Spring Kafka đang dùng.
```

Đây là **trích đoạn minh họa policy**, chưa phải một config class hoàn chỉnh. `FixedBackOff(1000L, 2L)` là khoảng nghỉ 1 giây và tối đa hai lần retry theo semantics của Spring retry/backoff API. Số attempts cuối cùng cần được test, không diễn giải mơ hồ “2 nghĩa là 2 lần tổng cộng”.

Để **recover record và commit offset đã recover trong Kafka transaction mới**, Spring Kafka cung cấp các cơ chế như `commitRecovered` cùng `KafkaTemplate` trong `DefaultAfterRollbackProcessor` khi cấu hình phù hợp. Không tự sao chép một vài dòng từ ví dụ sang production mà chưa kiểm tra:

- Recovered record được gửi tới DLT bằng producer transactional hay không?
- Recovery và offset có được commit cùng Kafka transaction cần thiết không?
- Publish DLT có được xác nhận trước khi đánh dấu bản ghi đã recover?
- Sau khi process crash giữa các bước, có thể có duplicate DLT hoặc mất record không?

Chọn recovery theo semantics, không chỉ theo mong muốn “consumer hết lỗi”.

### 11.2. Test DLT riêng với rollback test

Một test poison pill có thể:

1. Gửi record invalid.
2. Cho listener luôn ném exception được phân loại.
3. Đợi số attempt vượt ngưỡng đã cấu hình.
4. Dùng consumer `read_committed` trên topic DLT để kiểm tra record được publish.
5. Xác minh input offset được xử lý theo recovery policy, rồi một record hợp lệ phía sau có thể tiếp tục.
6. Kiểm tra không có bản ghi output nghiệp vụ từ những attempt abort.

Không dùng cùng fixture `FailOnceOrderListener` để suy ra policy poison pill: nó chỉ lỗi một lần rồi thành công, không đi vào nhánh recover sau khi hết retry.

## 12. Kafka + database: rollback không nguyên tử xuyên hai hệ thống

Một flow production thường là:

```text
orders.in -> listener
                |
                +-- UPDATE orders database
                |
                +-- KafkaTemplate.send(orders.out)
```

Nếu Kafka transaction abort nhưng JDBC transaction đã commit, thay đổi DB **không tự rollback**. Ngược lại, nếu DB fail trước khi Kafka transaction commit và exception được propagate, Kafka transaction có thể abort, nhưng cần hiểu rõ transaction order của Spring và thiết kế ứng dụng.

### 12.1. Thử nghiệm failure trước DB commit

Khi JDBC transaction còn active và method ném exception, thay đổi SQL trong transaction đó có thể rollback. Nhưng Kafka container vẫn cần nhận exception để abort Kafka transaction; nếu exception bị catch và xử lý như thành công, Kafka có thể commit không đúng ý muốn.

### 12.2. Thử nghiệm failure sau DB commit

```text
T1: Kafka container bắt đầu transaction
T2: service @Transactional(JDBC) cập nhật DB
T3: JDBC transaction COMMIT
T4: KafkaTemplate đã gửi output
T5: Kafka transaction COMMIT thất bại
T6: Listener record bị redeliver
```

Nếu lần xử lý sau cập nhật DB lần nữa hoặc gửi email lần nữa, side effect có thể lặp. Spring không cung cấp một distributed ACID transaction hai pha mặc định để commit Kafka và JDBC như một đơn vị nguyên tử.

Một số cấu hình synchronized transaction có thể giảm khoảng mất đồng bộ nhưng vẫn có cửa sổ failure giữa hai lần commit. Đối với nghiệp vụ quan trọng, cân nhắc:

- **Idempotent database writes** dựa trên event ID hoặc business key.
- **Transactional outbox**: ghi thay đổi nghiệp vụ cùng outbox row trong một JDBC transaction; một publisher/CDC gửi Kafka sau đó.
- **Inbox/processed-event table**: kiểm tra event ID đã xử lý để chặn side effect lặp.
- Saga/compensation khi bắt buộc tương tác với nhiều dịch vụ.

### 12.3. Test DB idempotency sau Kafka rollback

Ví dụ bảng:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(80) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Kịch bản:

1. Listener nhận `eventId=EV-1` và DB ghi `processed_event` với khóa duy nhất.
2. Kafka transaction fail sau khi DB đã commit.
3. Cùng event được redeliver.
4. Logic lần hai phát hiện `EV-1` đã tồn tại và không nhân đôi side effect DB.
5. Kafka processing vẫn có thể phát output phù hợp và commit offset.

**Không dùng `Kafka offset` làm khóa chống trùng nghiệp vụ** nếu event có thể được publish lại trên partition/offset mới. Dùng một event ID bền vững do producer nghiệp vụ cung cấp.

Đối với outbox, test cũng phải xác minh event không bị mất khi publisher crash, có thể gửi lại và consumer downstream idempotent nếu cần.

## 13. Test commit vs rollback: ma trận kỳ vọng

| Kịch bản | Output `read_committed` | Input offset | Hành vi kế tiếp |
| --- | --- | --- | --- |
| Listener gửi và return bình thường | Output được nhìn thấy sau commit | Commit cùng transaction | Chuyển sang record tiếp theo |
| Listener throw trước send | Không có output | Không commit thành công | Redelivery/recovery |
| Listener send rồi throw | Không thấy output aborted | Không commit thành công | Redelivery/recovery |
| Listener throw nhưng catch rồi return | Có thể bị commit | Có thể được commit | **Sai nếu muốn rollback** |
| Listener gửi bằng transaction độc lập rồi throw | Output độc lập có thể đã commit | Tx container có thể abort offset | **Có nguy cơ duplicate output** |
| Retry thành công sau lần rollback | Chỉ output đã commit của attempt thành công | Commit khi attempt thành công | Tiếp tục |
| Poison pill hết retry, chuyển DLT | DLT phụ thuộc recovery transaction | Theo policy recover/commit | Có thể tiếp tục nếu recover thành công |
| DB commit rồi Kafka transaction fail | Kafka output có thể abort | Kafka offset chưa commit | DB side effect cần idempotency |
| JVM crash trước commit | Không thấy output chưa commit với read_committed | Chưa được commit từ tx đó | Khôi phục qua broker/rebalance |

Ma trận này là **kỳ vọng theo contract khi transaction được cấu hình đúng**. Tùy thời điểm crash và transaction outcome chưa rõ, cần đo trên broker hoặc metadata thay vì dựa vào stacktrace của ứng dụng.

## 14. Test không nên chỉ dựa vào Mockito

Mockito hữu ích để unit test logic:

```java
verify(kafkaTemplate).send("orders.out", "order-1", "CREATED");
```

Nhưng lời gọi được verify không chứng minh:

- Producer đã bắt đầu Kafka transaction.
- Record được gửi thành công tới broker.
- Record đó được abort hay commit.
- Consumer `read_committed` có nhìn thấy nó không.
- Offset đầu vào được commit cùng output hay không.
- Container có redeliver sau rollback hay không.

Do đó chia rõ hai cấp kiểm thử:

| Cấp | Mục tiêu | Công cụ phù hợp |
| --- | --- | --- |
| Unit | Chuyển đổi payload, phân loại lỗi, business rule | JUnit/Mockito |
| Integration Kafka | Producer transaction commit/abort, output visibility | `@EmbeddedKafka` + Kafka consumer thật |
| Integration listener | Rollback output + redelivery + offset semantics | Listener container transactional + broker |
| DB + Kafka | Lỗi ở giữa hai transaction và idempotency | Test DB + broker hoặc Testcontainers |
| Reliability/chaos | Broker restart, network partition, fencing, process crash | Môi trường tích hợp với fault injection có kiểm soát |

Đừng đổi tên một unit test dùng mock thành “test transaction rollback” nếu không có một transaction thật cần kiểm chứng.

## 15. Các nguồn flaky trong test transaction

### 15.1. Topic/group dùng chung giữa test

Nếu nhiều bài test cùng dùng `orders.in`, `orders.out` và group `orders-processor`, event cũ có thể bị tiêu thụ hoặc gây assertion sai.

Giải pháp:

- Cô lập broker/context cho test quan trọng.
- Dùng topic/group test riêng khi phù hợp.
- Sử dụng input key/event ID duy nhất.
- Khi test đọc output, chỉ assert những record thuộc event ID được kiểm thử.
- Không tự xóa metadata production hoặc “reset offset” của một group thật để chạy test.

### 15.2. Test đọc quá sớm

Với Kafka, send callback, listener method return và broker commit không xảy ra cùng một thời điểm. Test phải chờ **một điều kiện có ý nghĩa** và có timeout. Sau đó dùng consumer `read_committed` để kiểm chứng output đã commit.

Đừng để test phụ thuộc một `Thread.sleep(1000)` cố định; trên CI chậm, transaction có thể cần lâu hơn, làm test fail ngẫu nhiên.

### 15.3. Producer transactional ID trùng

Hai producer đang hoạt động với cùng `transactional.id` có thể fence nhau. Trong test chạy song song hoặc khi scale ứng dụng, prefix cần được quản lý để không tạo xung đột ngoài chủ đích.

### 15.4. Broker không đủ khả năng transaction

Trong cluster Kafka production, transaction coordinator phụ thuộc cấu hình replication/ISR phù hợp. Embedded broker cho test được cấu hình để hỗ trợ mục đích test, nhưng khi tự chạy Kafka một node, cần điều chỉnh những thuộc tính nội bộ của transaction state log theo môi trường dev. Lỗi khởi tạo transaction có thể là cấu hình broker, không phải bug của listener.

### 15.5. Deserializer gây lỗi trước listener

Nếu payload không parse được khi deserialize, method `@KafkaListener` có thể **chưa được gọi**. Đó là một nhánh reliability khác: dùng `ErrorHandlingDeserializer` và policy recover/poison-pill phù hợp. Đừng dùng lỗi deserialization để kiểm thử “throw sau khi listener gửi output”, vì failure point đã khác.

### 15.6. Commit offset sai do auto-commit hoặc manual ack

Một test có thể báo “không phát lại record” vì consumer đã commit offset theo cơ chế khác ngoài Kafka transaction. Khi test rollback, xác minh `enable.auto.commit=false`, container transaction manager, ack mode và error handler/recovery policy thực tế.

## 16. Fencing, timeout và tình huống commit không rõ kết quả

Kafka transactions có cơ chế bảo vệ khi producer identity/epoch bị thay thế hoặc khi transaction timeout. Ví dụ:

- `ProducerFencedException` khi một producer cũ bị fencing.
- Transaction timeout khiến broker abort một transaction chưa hoàn tất.
- Rebalance và việc sở hữu partition thay đổi khi xử lý quá lâu.
- Network interruption đúng lúc commit: client có thể không xác định ngay broker đã commit hay chưa.

Trong các tình huống này:

1. Không tự coi mọi exception Kafka là transient để retry vô hạn cùng một producer.
2. Với lỗi fatal/fencing, để container và producer factory xử lý theo contract, có thể cần tạo producer mới hoặc restart container.
3. Theo dõi transaction duration, `max.poll.interval.ms`, session timeout và các cấu hình broker/producer liên quan.
4. Dùng event ID và idempotency để kết quả nghiệp vụ vẫn đúng nếu có redelivery hoặc outcome không rõ.
5. Đối soát output `read_committed` và committed group offset thay vì suy đoán từ log.

### Test fencing có nên dùng embedded broker?

Có thể xây test với hai transactional producers dùng cùng `transactional.id` và chủ động khởi tạo producer mới để fence producer cũ. Nhưng đây là bài test riêng, cần kiểm soát thời điểm tạo producer, giao dịch đang mở và xử lý lỗi của client. Không nên gộp nó vào test fail-once cơ bản, vì dễ gây flakiness và làm mục tiêu rollback bị mờ.

## 17. Logging và metrics cho transaction rollback

Khi điều tra, log nên có những trường sau nếu được phép:

```text
consumerGroup
listenerId
topic
partition
offset
eventId
transactionOutcome: COMMITTED | ABORTED | UNKNOWN
attempt
errorCategory
traceId
deploymentInstance
```

Ví dụ:

```json
{
  "event": "kafka_record_processing_failed",
  "consumerGroup": "orders-processor",
  "topic": "orders.in",
  "partition": 0,
  "offset": 125,
  "eventId": "EV-1042",
  "errorCategory": "DEPENDENCY_TIMEOUT",
  "attempt": 1
}
```

Không log token, credential, raw payload nhạy cảm hoặc toàn bộ header. Cũng không khẳng định transaction đã `ABORTED` chỉ vì listener ném exception: quan sát state transaction/producer và kết quả từ broker nếu cần đánh giá chính xác.

Metric gợi ý:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `kafka_listener_failed_total{listener,errorCategory}` | Số lần xử lý lỗi |
| `kafka_transaction_aborted_total{service}` | Theo dõi transaction abort nếu instrumentation hỗ trợ |
| `kafka_listener_redelivery_total{listener}` | Phát hiện retry/redelivery tăng |
| `kafka_dlt_published_total{topic,errorCategory}` | Theo dõi record được chuyển DLT |
| Consumer lag theo group | Phát hiện partition bị kẹt sau rollback liên tiếp |
| Transaction duration/p95 | Phát hiện transaction kéo dài |
| Time since last committed event | Phát hiện pipeline dừng tiến |

Đây là **tên metric tùy chỉnh minh họa**, không phải cam kết metric mặc định Spring Kafka hoặc Micrometer. Tránh dùng `eventId`, offset hay exception message làm label có cardinality cao; để chúng trong log/trace.

## 18. Quy trình điều tra khi test rollback thất bại

Giả sử test “aborted output is invisible” báo có hai record thay vì một. Đi theo thứ tự:

1. **Kiểm tra verifier:** consumer đọc output có `isolation.level=read_committed` không? Có record từ test khác không?
2. **Kiểm tra listener:** exception có propagate hay bị catch rồi return bình thường?
3. **Kiểm tra producer:** `KafkaTemplate` có dùng transaction-capable producer factory và cùng transaction của container không?
4. **Kiểm tra transaction manager:** listener factory có `KafkaTransactionManager` hay không?
5. **Kiểm tra nested transaction:** có gọi `executeInTransaction(...)` trong listener khiến output commit độc lập không?
6. **Kiểm tra recovery:** after-rollback processor có đang publish thêm output/DLT theo chính sách không?
7. **Kiểm tra test isolation:** broker/topic/group có dữ liệu cũ từ test trước không?
8. **Kiểm tra số lần listener chạy:** lần đầu ném lỗi đúng điểm sau send chưa?
9. **Kiểm tra group offsets:** sau aborted attempt, có cơ chế auto-commit hoặc ack ngoài transaction không?
10. **Kiểm tra side effect ngoài Kafka:** duplicate thực sự xuất hiện trong DB/HTTP hay chỉ là record có trong log nhưng bị abort?

Nếu test không thấy output dù listener chạy thành công, kiểm tra:

- Transaction thứ hai thực sự commit xong chưa.
- Verifier đang assign đúng topic/partition không.
- `auto.offset.reset` có phù hợp khi group chưa có offset không.
- Consumer đã poll đủ thời gian chưa; có được cung cấp bootstrap server của embedded broker không.
- Producer có bị fenced hoặc transaction coordinator lỗi không.
- Output có nằm ở một topic khác do cấu hình properties không.

## 19. Bài tập thực hành

**Bài 1 — Producer rollback.** Tạo `KafkaTemplate` transactional và topic test. Trong `executeInTransaction` gửi hai record rồi ném exception. Dùng consumer `read_committed` chứng minh cả hai không hiển thị; sửa callback để commit và kiểm tra record hiển thị.

**Bài 2 — Listener fail once.** Xây `@KafkaListener` gửi output rồi throw ở lần nhận đầu; lần hai xử lý thành công. Dùng `@EmbeddedKafka`, assert hai lần xử lý và chỉ một output committed.

**Bài 3 — Quan sát committed offset.** Dùng group test riêng, tạm dừng xử lý sau failure đầu và tra committed offset bằng AdminClient. Cho phép retry thành công rồi tra lại; giải thích sự khác nhau giữa consumer position và committed offset.

**Bài 4 — Poison pill và DLT.** Cho listener luôn ném exception với một payload invalid. Cấu hình after-rollback recovery có backoff/giới hạn. Xác minh DLT nhận record theo policy và consumer có thể xử lý record hợp lệ phía sau.

**Bài 5 — Bắt exception sai cách.** Đổi listener thành catch exception rồi return bình thường. Quan sát output/offset và giải thích vì sao container có thể commit thay vì rollback.

**Bài 6 — Nested transaction.** Cố ý dùng `KafkaTemplate.executeInTransaction` trong listener transactional, rồi throw ở listener ngoài. Kiểm tra output của transaction độc lập có thể commit dù offset transaction ngoài abort. Sau đó sửa thành `template.send` trực tiếp.

**Bài 7 — DB side effect.** Cho listener insert vào DB rồi fail ở Kafka transaction. Redeliver cùng event và quan sát duplicate hoặc unique constraint. Thêm `processed_event(event_id)` với khóa duy nhất hoặc transactional outbox, rồi kiểm tra kết quả cuối.

**Bài 8 — Broker failure.** Dùng môi trường integration có điều khiển để restart broker hoặc ngắt kết nối trong lúc transaction đang mở. Phân biệt failure trước send, sau send và gần commit; không dùng sleep để kết luận transaction outcome.

**Bài 9 — Group rebalancing.** Xử lý record lâu hơn ngưỡng poll interval trong môi trường test và quan sát hành vi container. Thiết kế timeout, concurrency và recovery để không gây retry vô hạn.

**Bài 10 — Monitoring.** Gắn log correlation `topic/partition/offset/eventId`, đo listener failure, redelivery và DLT. Tạo alert khi consumer lag tăng kèm failure liên tiếp.

## 20. Tóm tắt kiểm chứng cần có trước khi xem là thành công

| Điều cần chứng minh | Phương pháp |
| --- | --- |
| Producer thật đang dùng Kafka transaction | Kiểm tra producer factory/transaction manager và broker integration |
| Output trong transaction thất bại bị abort | Consumer `read_committed` không thấy record failed attempt |
| Lần xử lý thành công có output | Consumer `read_committed` thấy record đã commit |
| Input không bị coi là xử lý thành công sau rollback | Redelivery cùng record và/hoặc đo committed group offset |
| Không tạo duplicate output sau retry | Kiểm tra chỉ một output nghiệp vụ committed cho event ID |
| Poison pill không gây kẹt vĩnh viễn | Test recovery/DLT và xử lý record kế tiếp |
| DB/API không bị nhân đôi side effect | Test idempotency/outbox riêng |
| Test không flaky vì timing | Latch, polling có timeout, fixture độc lập |
| Có thể điều tra failure | Structured logs, metric và trace/correlation IDs |

**Kết luận:** Test transaction rollback của Spring Kafka không chỉ là `assertThrows(...)`. Một bài test đáng tin phải có **broker thật**, Kafka transaction được gắn với đúng listener container, verifier dùng **`read_committed`**, và các assertion về **output, offset, redelivery và side effect**. Khi lỗi xảy ra sau `send` nhưng trước commit, output của attempt đó phải bị abort và input offset không được commit như thành công; record có thể được xử lý lại theo after-rollback policy. Với database và API ngoài Kafka, phải thêm idempotency/outbox hoặc cơ chế giao dịch phù hợp vì Kafka rollback không tự hoàn tác các hệ thống đó.

### Tài liệu tham khảo

- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
