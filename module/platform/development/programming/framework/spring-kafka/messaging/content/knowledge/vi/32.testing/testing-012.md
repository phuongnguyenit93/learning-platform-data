# Kiểm thử retry và dead letter

## 1. Mục tiêu của kiểm thử

Trong Spring Kafka, listener có thể thất bại vì dependency tạm thời không sẵn sàng, dữ liệu không hợp lệ hoặc lỗi lập trình. Retry cho phép thử xử lý lại record theo chính sách đã cấu hình. Khi record không thể xử lý sau số lần thử cho phép, ứng dụng có thể chuyển record sang dead-letter topic (DLT) để điều tra và phục hồi.

Kiểm thử cần chứng minh toàn bộ hành vi:

- Record được giao lại đúng số lần theo chính sách.
- Lỗi tạm thời được xử lý thành công khi dependency phục hồi.
- Lỗi kéo dài hoặc không thể retry được chuyển sang DLT.
- DLT giữ payload, key và metadata nguồn cần thiết.
- Lỗi khi publish DLT không bị coi nhầm là recovery thành công.
- Offset được xác nhận theo đúng chính sách sau khi xử lý hoặc recovery.
- Record được giao lại không làm side effect nghiệp vụ bị nhân đôi.

Ví dụ với topic `orders`: listener cập nhật projection trong database. Nếu database timeout hai lần rồi hoạt động lại, record cần được xử lý thành công ở lần thử tiếp theo. Nếu record có payload không hợp lệ, hệ thống nên chuyển nó sang `orders.DLT` sau chính sách retry phù hợp để luồng chính tiếp tục.

## 2. Phân biệt blocking retry và non-blocking retry

Spring Kafka có hai cách retry thường gặp. Cách kiểm thử phụ thuộc vào cơ chế ứng dụng đang dùng.

| Tiêu chí | Blocking retry | Non-blocking retry |
|---|---|---|
| Cơ chế phổ biến | `DefaultErrorHandler` và `BackOff` | `@RetryableTopic` |
| Nơi retry | Listener container giao lại record trên partition nguồn | Record được publish sang retry topic có delay |
| Partition nguồn | Thường bị chặn tại record lỗi trong lúc retry | Có thể tiếp tục xử lý record kế tiếp |
| Thứ tự | Giữ thứ tự partition tốt hơn trong luồng retry tại chỗ | Có thể thay đổi thứ tự khi record đi qua retry topic |
| Kiểm thử trọng tâm | Số lần listener được gọi, backoff, DLT và offset | Định tuyến retry topic, delay, số attempt, DLT và thứ tự |
| Phù hợp | Retry ngắn, muốn giữ luồng partition | Retry lâu, không muốn giữ partition nguồn bị chặn |

Không gộp hai cơ chế thành một bài test chung. Với blocking retry, cần xác minh số lần gọi listener và hành vi recoverer. Với non-blocking retry, cần xác minh record đi qua retry topic theo cấu hình và cuối cùng đến DLT.

~~~mermaid
flowchart TD
    A["Record từ topic orders"] --> B["Listener xử lý"]
    B --> C{"Thành công?"}
    C -->|Có| D["Commit offset theo AckMode"]
    C -->|Không: blocking| E["DefaultErrorHandler"]
    E --> F{"Còn retry?"}
    F -->|Có| G["BackOff rồi giao lại record"]
    G --> B
    F -->|Không| H["DeadLetterPublishingRecoverer"]
    H --> I["orders.DLT"]
    C -->|Không: non-blocking| J["Retry topic"]
    J --> K["Listener thử lại sau delay"]
    K --> L{"Thành công?"}
    L -->|Có| D
    L -->|Không, hết attempt| I
~~~

## 3. Các mức kiểm thử cần có

| Mức | Công cụ | Mục tiêu |
|---|---|---|
| Unit test | JUnit, Mockito, AssertJ | Kiểm tra phân loại exception, số lần gọi service, logic idempotency |
| Test cấu hình | Spring test context | Xác minh error handler, backoff và recoverer gắn đúng container factory |
| Integration test | Embedded Kafka hoặc Testcontainers | Kiểm tra record thực sự được retry và publish DLT qua broker |
| Staging smoke test | Kafka cluster gần production | Xác minh ACL, serializer, retention, topic provisioning và cấu hình thực tế |

Unit test không chứng minh Kafka broker đã ghi DLT hoặc offset được commit. Integration test với broker thật là cần thiết cho các hành vi này.

## 4. Chuẩn bị dependency kiểm thử

Với Gradle, thêm dependency test của Spring Kafka cùng phiên bản tương thích với Spring Kafka đang dùng:

~~~gradle
dependencies {
    testImplementation "org.springframework.kafka:spring-kafka-test"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
}
~~~

`spring-kafka-test` cung cấp Embedded Kafka, `KafkaTestUtils` và tiện ích chờ container assignment. Không ép phiên bản `spring-kafka-test` khác phiên bản `spring-kafka` đang được Spring Boot quản lý nếu không có chủ đích.

Embedded Kafka phù hợp để kiểm thử producer, consumer, retry và DLT trong một tiến trình test. Nếu cần kiểm thử cấu hình gần production hơn, chẳng hạn broker nhiều node, ACL, TLS hoặc SASL, hãy dùng Testcontainers với broker được cấu hình các cơ chế tương ứng hoặc staging cluster.

## 5. Tạo Embedded Kafka và topic kiểm thử

Ví dụ dùng JUnit 5 và Spring Boot:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(properties = {
    "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.auto-offset-reset=earliest",
    "spring.kafka.consumer.enable-auto-commit=false"
})
@EmbeddedKafka(
    partitions = 1,
    topics = {
        "orders.transient",
        "orders.transient.DLT",
        "orders.permanent",
        "orders.permanent.DLT"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class RetryAndDltIntegrationTest {

    @Autowired
    KafkaTemplate<Object, Object> kafkaTemplate;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    RetryProbeListener probeListener;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    // Các test method được minh họa ở những mục tiếp theo.
}
~~~

Mỗi topic nguồn và DLT được tạo trước với một partition để ví dụ giữ nguyên partition khi chuyển record. Trong dự án có nhiều test song song, nên dùng tên topic riêng cho từng test class hoặc cấu hình broker riêng để tránh dùng chung dữ liệu.

Một số phiên bản Spring Kafka cũ dùng property `spring.embedded.kafka.brokers` và cách ánh xạ bootstrap server khác. Dùng thuộc tính `bootstrapServersProperty` nếu phiên bản đang dùng hỗ trợ; nếu không, ánh xạ property theo tài liệu đúng phiên bản.

`@DirtiesContext` giúp đóng context sau test class, tránh listener container và consumer group của test rò sang test khác. Nó không thay thế việc dùng topic/group ID riêng và dọn dữ liệu test đúng cách.

## 6. Cấu hình DefaultErrorHandler và DLT recoverer

Với record listener, `DefaultErrorHandler` quản lý retry. Khi hết retry, `DeadLetterPublishingRecoverer` publish record sang DLT.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class RetryTestConfiguration {

    @Bean
    DefaultErrorHandler retryErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

        // Publish DLT thất bại phải được xem là lỗi recovery.
        recoverer.setFailIfSendResultIsError(true);

        var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(200L, 2L)
        );

        handler.addNotRetryableExceptions(
            InvalidOrderPayloadException.class
        );

        return handler;
    }
}
~~~

`FixedBackOff(200L, 2L)` có nghĩa chờ 200 ms giữa các lần retry, tối đa hai lần retry bổ sung sau lần xử lý ban đầu. Nếu listener luôn thất bại với exception retryable, tổng số lần gọi là ba: một lần đầu và hai lần retry.

`InvalidOrderPayloadException` được đánh dấu non-retryable trong ví dụ. Record gặp exception này sẽ đi đến recovery mà không chờ hai lần retry. Chỉ phân loại một exception là non-retryable khi retry không thể làm dữ liệu tự hợp lệ.

`InvalidOrderPayloadException` là exception nghiệp vụ do ứng dụng định nghĩa, ví dụ kế thừa `RuntimeException`. Trong cấu hình thật, đặt class này ở package domain phù hợp và import vào cấu hình retry.

DLT template cần serializer phù hợp với record lỗi. Ví dụ test này dùng String key/value nên template có thể dùng StringSerializer. Khi kiểm thử lỗi deserialize, value gốc có thể là byte array; hãy cấu hình DLT producer hỗ trợ cả byte[] và kiểu object bình thường, ví dụ serializer phân loại theo kiểu. Không giả định `KafkaTemplate<Object,Object>` tự serialize được mọi kiểu.

## 7. Gắn error handler vào listener container factory

Chỉ khai báo bean `DefaultErrorHandler` chưa đủ nếu container factory đang dùng không nhận bean đó. Gắn handler vào factory mà listener tham chiếu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
        retryContainerFactory(
                ConsumerFactory<String, String> consumerFactory,
                DefaultErrorHandler retryErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(retryErrorHandler);
    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

Listener trong test phải tham chiếu đúng factory:

~~~java
@KafkaListener(
    id = "permanentListener",
    topics = "orders.permanent",
    groupId = "retry-permanent-test",
    containerFactory = "retryContainerFactory"
)
public void handle(String payload) {
    // Gọi service hoặc mô phỏng lỗi.
}
~~~

Nếu test listener dùng factory mặc định trong khi error handler được gắn ở `retryContainerFactory`, test sẽ không xác minh được cấu hình mong muốn. Nên đặt `id` rõ ràng để lấy container từ `KafkaListenerEndpointRegistry` và chờ assignment trước khi gửi record.

## 8. Tạo listener mô phỏng lỗi tạm thời và lỗi kéo dài

Để test retry có thể lặp lại, dùng bộ đếm theo message ID thay vì một biến đếm toàn cục không kiểm soát:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class RetryProbeListener {

    private final Map<String, AtomicInteger> attempts =
        new ConcurrentHashMap<>();

    private final CountDownLatch transientSucceeded =
        new CountDownLatch(1);

    @KafkaListener(
        id = "transientListener",
        topics = "orders.transient",
        groupId = "retry-transient-test",
        containerFactory = "retryContainerFactory"
    )
    public void handleTransient(String messageId) {
        int attempt = attempts
            .computeIfAbsent(messageId, key -> new AtomicInteger())
            .incrementAndGet();

        if (attempt < 3) {
            throw new IllegalStateException("Dependency is temporarily unavailable");
        }

        transientSucceeded.countDown();
    }

    @KafkaListener(
        id = "permanentListener",
        topics = "orders.permanent",
        groupId = "retry-permanent-test",
        containerFactory = "retryContainerFactory"
    )
    public void handlePermanent(String messageId) {
        attempts
            .computeIfAbsent(messageId, key -> new AtomicInteger())
            .incrementAndGet();

        throw new IllegalStateException("Permanent processing failure");
    }

    public int attemptsFor(String messageId) {
        var counter = attempts.get(messageId);
        return counter == null ? 0 : counter.get();
    }

    public boolean awaitTransientSuccess(long timeout, TimeUnit unit)
            throws InterruptedException {
        return transientSucceeded.await(timeout, unit);
    }
}
~~~

Listener transient thất bại ở hai lần đầu và thành công ở lần thứ ba. Listener permanent luôn thất bại để error handler chuyển record sang DLT sau khi hết retry.

Trong test thật, nên tách probe listener theo class hoặc dùng message ID duy nhất cho mỗi test. Không dùng lại cùng message ID nếu bộ đếm vẫn còn trong Spring context.

## 9. Kiểm thử retry thành công sau lỗi tạm thời

Kiểm thử cần chờ listener container được assign partition trước khi gửi record. Điều này tránh race condition khi producer gửi trước lúc consumer bắt đầu poll.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.kafka.core.KafkaTemplate;

// Đặt phương thức này trong RetryAndDltIntegrationTest ở mục 5.
@Test
void retriesTransientFailureThenSucceeds() throws Exception {
    var container = registry.getListenerContainer("transientListener");
    ContainerTestUtils.waitForAssignment(container, 1);

    kafkaTemplate.send(
        "orders.transient",
        "transient-001",
        "transient-001"
    ).get(10, TimeUnit.SECONDS);

    assertThat(
        probeListener.awaitTransientSuccess(10, TimeUnit.SECONDS)
    ).isTrue();

    assertThat(probeListener.attemptsFor("transient-001"))
        .isEqualTo(3);
}
~~~

Kết quả mong đợi:

- Producer gửi request record thành công.
- Listener được gọi ba lần.
- Hai lần đầu ném exception.
- Lần thứ ba thành công.
- Record không được chuyển sang DLT.
- Offset được xác nhận theo AckMode sau khi xử lý thành công.

Test này xác minh retry hoạt động khi lỗi có thể phục hồi. Không dùng `Thread.sleep()` để chờ số lần retry; dùng latch, Awaitility hoặc polling có timeout.

## 10. Kiểm thử record được chuyển sang DLT sau khi hết retry

Với listener luôn ném exception retryable, cần xác minh cả số lần gọi và record trong DLT.

Tạo consumer test để đọc DLT:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

private Consumer<String, String> createDltConsumer(
        EmbeddedKafkaBroker broker,
        String groupId,
        String dltTopic) {

    Map<String, Object> properties =
        KafkaTestUtils.consumerProps(groupId, "false", broker);

    properties.put(
        ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
        "earliest"
    );

    var factory = new DefaultKafkaConsumerFactory<String, String>(
        properties,
        new StringDeserializer(),
        new StringDeserializer()
    );

    Consumer<String, String> consumer = factory.createConsumer();
    consumer.subscribe(List.of(dltTopic));
    consumer.poll(Duration.ofMillis(100));

    return consumer;
}
~~~

Consumer test dùng group ID riêng và `auto.offset.reset=earliest` để đọc record DLT đã có. Trong test, gọi `createDltConsumer()` trước khi gửi record nguồn để tránh bỏ lỡ dữ liệu.

Phương thức test tiếp theo cũng được đặt trong `RetryAndDltIntegrationTest` ở mục 5. Test class cần inject `EmbeddedKafkaBroker embeddedKafka` cùng `registry`, `kafkaTemplate` và `probeListener`.

~~~java
@Test
void publishesRecordToDltAfterRetriesAreExhausted() throws Exception {
    var container = registry.getListenerContainer("permanentListener");
    ContainerTestUtils.waitForAssignment(container, 1);

    try (var dltConsumer = createDltConsumer(
            embeddedKafka,
            "permanent-dlt-test",
            "orders.permanent.DLT")) {

        kafkaTemplate.send(
            "orders.permanent",
            "permanent-001",
            "permanent-001"
        ).get(10, TimeUnit.SECONDS);

        ConsumerRecords<String, String> records =
            KafkaTestUtils.getRecords(
                dltConsumer,
                Duration.ofSeconds(10)
            );

        assertThat(probeListener.attemptsFor("permanent-001"))
            .isEqualTo(3);

        assertThat(records.count()).isEqualTo(1);

        var deadLetter = records.iterator().next();
        assertThat(deadLetter.key()).isEqualTo("permanent-001");
        assertThat(deadLetter.value()).isEqualTo("permanent-001");
    }
}
~~~

Ví dụ dùng một partition nguồn và DLT để giữ nguyên partition. Nếu resolver giữ `record.partition()`, DLT cần có đủ partition tương ứng với mọi partition nguồn.

Trong test thực tế, có thể dùng Awaitility để chờ bộ đếm hoặc DLT record thay vì dựa vào thời gian poll cố định. Đảm bảo DLT consumer đã subscribe và assignment hoàn tất trước khi gửi record nếu test cần xác định chính xác thời điểm nhận.

## 11. Kiểm tra DLT headers và metadata nguồn

DLT cần giữ đủ thông tin để nhóm vận hành xác định record gốc. Spring Kafka thêm các header dead-letter như:

| Header | Thông tin |
|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Topic nguồn |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Partition nguồn |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Offset nguồn |
| `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` | Consumer group xử lý |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Tên đầy đủ của exception |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Message exception |

Có thể mở rộng test DLT để kiểm tra header topic gốc:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.kafka.support.KafkaHeaders;

var originalTopicHeader =
    deadLetter.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC);

assertThat(originalTopicHeader).isNotNull();
assertThat(new String(
    originalTopicHeader.value(),
    StandardCharsets.UTF_8
)).isEqualTo("orders.permanent");
~~~

Header thực tế phụ thuộc phiên bản Spring Kafka và cấu hình recoverer. Dùng các hằng số `KafkaHeaders` của phiên bản đang dùng thay vì tự viết tên header nếu có thể. Không phụ thuộc vào stack trace đầy đủ trong mọi môi trường vì có thể tắt hoặc giới hạn header này để giảm kích thước record và tránh lộ thông tin.

Nên kiểm tra thêm partition và offset nguồn. Không so sánh offset DLT với offset nguồn như thể chúng thuộc cùng một log; chúng là hai topic độc lập.

## 12. Kiểm thử exception không retry

Một lỗi dữ liệu không thể tự hết sau thời gian chờ thường nên được phân loại non-retryable. Ví dụ `InvalidOrderPayloadException` đã được đăng ký qua `addNotRetryableExceptions()`.

Test cần xác minh:

1. Listener được gọi đúng một lần.
2. Không có các lần retry bổ sung.
3. Record được publish đến DLT.
4. Payload và metadata nguồn được giữ.
5. Offset được xử lý theo chính sách recovery.

Đừng dùng `IllegalArgumentException` hoặc `NullPointerException` làm non-retryable một cách máy móc. Một exception có thể đại diện cho lỗi dữ liệu trong module này nhưng lại là lỗi lập trình ở module khác. Tạo exception nghiệp vụ riêng giúp phân loại rõ hơn.

Spring Kafka có một số exception được mặc định xem là fatal/non-retryable, đặc biệt lỗi deserialize hoặc message conversion. Khi tùy chỉnh phân loại, hãy kiểm tra cấu hình mặc định của phiên bản Spring Kafka và chỉ ghi đè khi có lý do rõ ràng.

## 13. Kiểm thử khi publish DLT thất bại

Một lỗi quan trọng là recoverer không thể publish DLT do topic không tồn tại, thiếu partition, ACL thiếu, broker lỗi hoặc serializer không tương thích.

Nếu dùng `recoverer.setFailIfSendResultIsError(true)`, lỗi gửi DLT được báo lại thay vì bị xem là recovery thành công. Cần kiểm thử tình huống này trong môi trường cô lập:

- Cấu hình destination resolver trỏ đến một topic không tồn tại khi broker không tự tạo topic.
- Hoặc dùng principal test thiếu quyền `WRITE` trên DLT.
- Gửi record gây lỗi để kích hoạt recovery.
- Xác minh error handler nhận biết lỗi publish DLT.
- Xác minh record nguồn chưa bị đánh dấu recovered theo cách làm mất dữ liệu.
- Theo dõi record được giao lại hoặc giữ lại theo AckMode và cấu hình container.

Hành vi offset chính xác khi recoverer ném exception phụ thuộc AckMode, container transaction và phiên bản Spring Kafka. Vì vậy, test cần đọc committed offset hoặc quan sát record được giao lại trong cấu hình cụ thể của ứng dụng. Không chỉ assert log có exception.

Sau khi cấp quyền hoặc sửa topic, cần có test chứng minh record có thể được recovery thành công và không bị mất. Không dùng một DLT destination lỗi trong test dùng chung vì nó có thể làm listener container liên tục retry và ảnh hưởng test khác.

## 14. Kiểm thử deserialization failure và DLT payload

Lỗi deserialize có thể xảy ra trong `poll()` trước khi listener được gọi. Để Spring Kafka error handler xử lý được, thường cần `ErrorHandlingDeserializer` bọc deserializer thật.

Một test deserialization nên kiểm tra:

- Gửi byte hoặc JSON không hợp lệ vào topic nguồn.
- Listener không nhận object sai kiểu.
- Error handler nhận được lỗi deserialize.
- Record được chuyển đến DLT theo chính sách non-retryable hoặc retry đã cấu hình.
- DLT giữ raw key/value và metadata exception cần thiết.

Điểm quan trọng là DLT template phải serialize được cả payload bình thường và raw byte array. Nếu template chỉ dùng `StringSerializer`, publish một value kiểu `byte[]` có thể thất bại. Có thể cấu hình `DelegatingByTypeSerializer` để chọn serializer theo kiểu value hoặc dùng template chuyên biệt cho recovery.

Không chỉ test payload JSON sai cú pháp. Cần có test schema/version không tương thích, tombstone value null và key deserialize thất bại nếu hệ thống hỗ trợ các trường hợp đó.

## 15. Kiểm thử non-blocking retry với @RetryableTopic

Với non-blocking retry, record được chuyển qua retry topic rồi được giao lại sau delay. Ví dụ listener:

Khi cần bật retry topic infrastructure tường minh, khai báo cấu hình sau (tùy phiên bản và auto-configuration của ứng dụng):

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.retrytopic.EnableKafkaRetryTopic;

@Configuration
@EnableKafkaRetryTopic
class RetryTopicTestConfiguration {
}
~~~

~~~java
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class NonBlockingRetryListener {

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 200, multiplier = 2.0),
        retryTopicSuffix = ".retry",
        dltTopicSuffix = ".DLT"
    )
    @KafkaListener(
        topics = "orders.async",
        groupId = "orders-async-test"
    )
    public void handle(String message) {
        throw new IllegalStateException("Temporary downstream failure");
    }

    @DltHandler
    public void handleDlt(String message) {
        // Ghi nhận record đã đến DLT.
    }
}
~~~

Cần bật retry topic infrastructure bằng `@EnableKafkaRetryTopic` nếu cấu hình ứng dụng yêu cầu; Spring Boot/Spring Kafka version và cấu hình annotation quyết định cách kích hoạt. `attempts = "4"` là tổng số lần giao dự kiến gồm lần đầu và các lần thử lại, khác với tham số retry count của `FixedBackOff`.

Kiểm thử non-blocking retry nên xác minh:

- Record được chuyển qua retry topic theo naming strategy đã cấu hình.
- Delay giữa các lần giao phù hợp với backoff, trong giới hạn sai số của test.
- Sau khi hết attempt, record đến DLT.
- DLT handler nhận đúng payload.
- Record tiếp theo trên topic nguồn vẫn có thể được xử lý trong lúc record trước đang chờ retry.
- Key, partition và metadata cần thiết được giữ theo cấu hình routing.

Tên retry topic cuối cùng có thể chứa suffix và giá trị delay theo naming strategy. Hãy xác minh naming strategy đang dùng rồi provision topic tương ứng; không hard-code tên retry topic mặc định từ một phiên bản khác.

Non-blocking retry có thể làm thay đổi thứ tự record. Test phải phản ánh yêu cầu nghiệp vụ về ordering, đặc biệt khi nhiều event cùng key hoặc cùng partition.

## 16. Kiểm thử batch listener

Nếu listener xử lý batch, không áp dụng nguyên xi kỳ vọng của record listener. Khi một phần tử trong batch thất bại, cách retry phụ thuộc exception và vị trí record được xác định.

Với `DefaultErrorHandler`, batch listener có thể ném `BatchListenerFailedException` để chỉ ra record trong batch bị lỗi. Nếu không xác định được record lỗi, container có thể retry lại cả batch theo hành vi cấu hình.

Test batch cần xác minh:

- Batch nào được giao lại và số lần giao lại.
- Record đã xử lý thành công trước lỗi có bị xử lý lại không.
- Offset nào được commit.
- DLT chứa đúng record lỗi hay cả batch theo recoverer strategy.
- Side effect của các record được giao lại là idempotent.

Không viết test batch chỉ assert số lần listener method được gọi; cần kiểm tra từng record và offset vì một lần gọi có thể chứa nhiều record.

## 17. Kiểm thử offset, redelivery và idempotency

Retry và DLT liên quan trực tiếp đến offset. Với record listener, sau khi listener thành công, container commit offset theo AckMode. Khi record được recover thành công và publish DLT, error handler có thể xem record đã được xử lý theo chính sách recovery và cho phép commit offset tương ứng.

Một tình huống cần test là listener đã thực hiện side effect nhưng ứng dụng dừng trước khi offset commit. Kafka có thể giao lại record sau khi consumer khởi động lại hoặc rebalance. Side effect có thể được thực hiện lần nữa.

Vì vậy, test nên bao gồm:

1. Listener ghi nhận side effect theo event ID.
2. Mô phỏng lỗi hoặc dừng consumer trước commit nếu test harness cho phép.
3. Khởi động lại consumer với cùng group ID.
4. Xác minh record có thể được giao lại.
5. Xác minh deduplication hoặc idempotency ngăn side effect bị nhân đôi.

Không dùng group ID mới cho test redelivery nếu mục tiêu là xác minh committed offset cũ. Group ID mới có thể bắt đầu từ `auto.offset.reset`, làm sai kết quả mong đợi.

Với DLT, có thể kiểm tra committed offset bằng `AdminClient.listConsumerGroupOffsets()` sau khi container đã xử lý recovery. Chờ offset ổn định trước khi assert; đừng đọc ngay sau khi DLT consumer nhận record vì publish DLT và commit offset nguồn là hai thao tác cần được quan sát riêng.

## 18. Đồng bộ test không dùng Thread.sleep()

Kafka là hệ thống bất đồng bộ. Một test có thể thất bại ngẫu nhiên nếu giả định listener luôn chạy trong một khoảng thời gian cố định.

Ưu tiên:

- `ContainerTestUtils.waitForAssignment()` để chờ listener có partition assignment.
- `CountDownLatch` khi chờ một hành động listener xác định.
- Awaitility để chờ điều kiện như số lần retry, DLT record hoặc committed offset.
- `KafkaTestUtils.getRecords(consumer, timeout)` để poll record với giới hạn thời gian.
- `CompletableFuture.get(timeout, unit)` để chờ kết quả producer.

Không dùng `Thread.sleep(1000)` rồi giả định listener đã xử lý xong. Nếu cần xác minh backoff, đo khoảng thời gian giữa các lần gọi với tolerance đủ rộng; tránh assert mili giây chính xác vì scheduling và broker latency có thể thay đổi.

## 19. Ma trận kịch bản kiểm thử

| Kịch bản | Kết quả mong đợi |
|---|---|
| Listener thành công ngay | Một lần gọi, không có DLT |
| Lỗi tạm thời rồi thành công | Số lần gọi đúng chính sách, không có DLT |
| Lỗi retryable kéo dài | Initial + retry count, sau đó một DLT record |
| Exception non-retryable | Không retry bổ sung, chuyển DLT |
| DLT topic thiếu partition | Recovery thất bại được quan sát |
| DLT publish bị ACL từ chối | Không coi record là recovered thành công |
| Deserialization failure | Listener không nhận object sai; DLT giữ raw data theo cấu hình |
| Consumer restart trước commit | Có thể redelivery; side effect idempotent |
| Batch listener lỗi giữa batch | Retry/commit đúng record và offset theo chiến lược |
| Non-blocking retry | Record đi qua retry topic và đến DLT sau số attempt |
| Nhiều test chạy đồng thời | Topic, group và message ID không xung đột |

## 20. Lỗi thường gặp khi viết test

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test lúc pass lúc fail | Gửi record trước khi listener assignment hoàn tất | Chờ `waitForAssignment()` |
| Không thấy DLT record | Recoverer chưa gắn vào container factory hoặc DLT topic sai tên | Kiểm tra factory, resolver và topic đích |
| DLT consumer đọc record cũ | Dùng group ID hoặc topic chung giữa test | Dùng group ID duy nhất và topic cô lập |
| Số lần retry nhiều hơn dự kiến | Nhầm retry count với tổng attempts | Với `FixedBackOff(interval, n)`, n là retry bổ sung sau lần đầu |
| DLT publish thất bại nhưng test vẫn pass | Không kiểm tra send result của recoverer | Bật fail-on-send-error và assert recovery failure |
| DLT value deserialize thất bại | Serializer DLT không hỗ trợ raw byte[] hoặc kiểu record | Dùng serializer tương thích với mọi kiểu value |
| Test không chứng minh commit offset | Chỉ kiểm tra DLT record | Kiểm tra committed offset bằng AdminClient hoặc redelivery |
| Test TLS/SASL pass giả | Embedded broker không bật security | Dùng Testcontainers/staging có TLS/SASL/ACL |
| Test bị ảnh hưởng bởi context cũ | Listener container còn chạy sau test | Dùng `@DirtiesContext` và lifecycle cleanup |

## 21. Tổ chức test trong CI

Trong CI, nhóm test nên được chia theo chi phí:

- Unit test exception classification và idempotency chạy nhanh ở mọi commit.
- Integration test Embedded Kafka chạy cho mỗi pull request.
- Testcontainers broker có TLS/SASL/ACL chạy ở pipeline bảo mật hoặc nightly nếu thời gian khởi động lớn.
- Staging smoke test chạy sau deploy và trước khi nhận traffic.

Mỗi test cần timeout tổng thể. Nếu test broker hoặc consumer bị treo, CI phải dừng với thông báo rõ ràng thay vì chiếm worker vô thời hạn.

Không chia sẻ Kafka topic và consumer group giữa pipeline build khác nhau. Dùng prefix theo build/test run hoặc broker riêng để tránh test này đọc record của test khác.

## 22. Checklist kiểm thử retry và dead letter

- [ ] Dùng `spring-kafka-test` hoặc Testcontainers phù hợp mục tiêu.
- [ ] Tạo trước topic nguồn, retry topic và DLT cần thiết.
- [ ] Gắn đúng `DefaultErrorHandler` vào listener container factory.
- [ ] Xác định rõ retry count và tổng số lần giao.
- [ ] Test lỗi tạm thời rồi thành công.
- [ ] Test lỗi retryable kéo dài và xác minh DLT.
- [ ] Test exception non-retryable.
- [ ] Kiểm tra payload, key, topic, partition, offset và DLT headers.
- [ ] Kiểm tra trường hợp DLT publish thất bại.
- [ ] Kiểm tra raw byte[] khi test deserialization failure.
- [ ] Phân biệt blocking retry với `@RetryableTopic`.
- [ ] Kiểm tra thứ tự và delay nếu dùng non-blocking retry.
- [ ] Kiểm tra batch listener riêng nếu ứng dụng xử lý batch.
- [ ] Xác minh committed offset và redelivery khi cần.
- [ ] Dùng message ID, topic và group ID cô lập cho từng test.
- [ ] Chờ assignment và điều kiện bất đồng bộ bằng latch/Awaitility/poll timeout.
- [ ] Không dùng `Thread.sleep()` làm cơ chế đồng bộ chính.
- [ ] Bảo đảm side effect idempotent khi record được giao lại.

Kiểm thử retry và dead letter phải xác minh cả đường xử lý thành công, đường recovery và trạng thái offset. Với blocking retry, kiểm tra `DefaultErrorHandler`, số lần listener được gọi và `DeadLetterPublishingRecoverer`. Với non-blocking retry, kiểm tra routing qua retry topic, delay, ordering và DLT. Khi dùng broker test có topic/group cô lập, chờ bất đồng bộ bằng timeout rõ ràng và xác minh metadata nguồn, nhóm phát triển có thể tin cậy hơn vào chính sách phục hồi của ứng dụng Spring Kafka.
