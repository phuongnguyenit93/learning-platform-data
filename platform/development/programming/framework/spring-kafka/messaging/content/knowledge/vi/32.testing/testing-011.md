# Kiểm thử error handler

Error handler quyết định điều gì xảy ra khi listener không xử lý được một Kafka record: thử lại, chờ backoff, bỏ qua một loại exception, chuyển record sang Dead Letter Topic (DLT) hoặc để lỗi tiếp tục được xử lý theo policy. Một cấu hình sai có thể làm record bị retry vô hạn, bị đưa vào DLT quá sớm, hoặc offset được xác nhận trong khi nghiệp vụ chưa hoàn tất. Vì vậy, kiểm thử error handler phải xác nhận cả hành vi listener, số lần thử, record được recover, metadata DLT và tiến triển offset của consumer group.

Trong Spring Kafka, `DefaultErrorHandler` là common error handler phổ biến cho listener container không dùng Kafka transaction. Với transactional listener, đường xử lý sau rollback thường do `AfterRollbackProcessor`, điển hình là `DefaultAfterRollbackProcessor`, đảm nhiệm. Hai cơ chế có vị trí và semantics khác nhau; test phải dùng đúng loại container mà ứng dụng vận hành.

Bài học thuộc chương **Kiểm thử** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Error handler nằm ở đâu trong luồng xử lý?

Với record listener không transactional, container gọi listener. Nếu listener ném exception, container chuyển lỗi tới common error handler. Handler có thể retry record, seek consumer, gọi recoverer hoặc để lỗi tiếp tục được xử lý theo policy.

~~~mermaid
flowchart TD
    A[Kafka poll] --> B[Listener container]
    B --> C[@KafkaListener]
    C --> D{Xử lý thành công?}
    D -->|Có| E[Commit offset theo AckMode]
    D -->|Không| F[CommonErrorHandler]
    F --> G{Còn retry?}
    G -->|Có| H[Backoff và giao lại record]
    H --> C
    G -->|Không| I[Recoverer]
    I --> J[DLT hoặc recovery action]
    J --> K[Offset xử lý theo recovery policy]
~~~

Các điểm cần test:

- Listener được gọi bao nhiêu lần cho cùng record.
- Backoff và exception classification có đúng không.
- Recoverer chỉ chạy khi hết retry hoặc lỗi được phân loại không retry.
- DLT có record đúng payload, key, partition và headers cần thiết.
- Offset nguồn chỉ tiến theo policy đã cấu hình.
- Một record lỗi không làm các record độc lập bị mất.

## 2. Phân biệt các loại kiểm thử

Không cần khởi động Kafka cho mọi test. Chọn mức test theo hành vi cần xác nhận:

| Mức test | Thành phần | Mục tiêu |
| --- | --- | --- |
| Unit test | Exception classifier, retry policy, resolver, recoverer wrapper | Kiểm tra rule thuần và nhánh phân loại. |
| Component test | Listener, service và handler trong Spring context | Kiểm tra wiring, dependency injection và listener behavior. |
| Integration test | Spring Kafka container với Embedded Kafka hoặc Testcontainers | Kiểm tra poll, retry, DLT, serialization và offset thực tế. |
| System test | Kafka cluster và các service liên quan | Kiểm tra ACL, broker failure, rebalance và vận hành gần production. |

Mock `KafkaConsumer` thường không chứng minh được semantics seek, poll, group offset hoặc transaction của broker. Dùng unit test để kiểm tra logic nhanh; dùng broker thật cho các hành vi phụ thuộc Kafka protocol.

## 3. Dependencies cho test

Với Maven, thêm Spring Kafka test ở scope test và dùng phiên bản do Spring Boot dependency management hoặc Spring Kafka BOM quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dùng Testcontainers, thêm module Kafka và JUnit integration phù hợp phiên bản dự án:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>kafka</artifactId>
    <scope>test</scope>
</dependency>
~~~

Không ép một version riêng cho `spring-kafka-test` khác với `spring-kafka`. Spring Kafka testing API thay đổi theo phiên bản; hãy dùng dependency cùng dòng version với thư viện runtime. Ví dụ trong bài minh họa record listener và API phổ biến của Spring Kafka 3.x; với dự án 2.x, kiểm tra tên API tương ứng trong Javadoc của đúng version.

## 4. Cấu hình DefaultErrorHandler cần kiểm thử

Một cấu hình thường gặp dùng `DeadLetterPublishingRecoverer` và `FixedBackOff`:

~~~java
@Bean
public DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltTemplate);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(100L, 2L)
        );

    handler.addNotRetryableExceptions(
        InvalidOrderEventException.class
    );

    return handler;
}
~~~

Với `FixedBackOff(100L, 2L)`, lần giao đầu tiên cộng hai lần retry tạo tối đa ba lần listener invocation trước khi recovery, nếu không có policy khác thay đổi hành vi. `addNotRetryableExceptions` đưa exception được chỉ định vào nhóm không retry theo classifier của handler.

Có thể ghi nhận retry bằng `RetryListener`:

~~~java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        retryMetrics.record(record.topic(), deliveryAttempt);
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        recoveryMetrics.increment(record.topic());
    }
});
~~~

Chỉ thêm listener theo dõi nếu ứng dụng cần metric hoặc audit. Test không nên phụ thuộc vào log message; ưu tiên assertion trên số lần invocation, recovery result và record DLT.

## 5. Test exception classification

Phân loại exception quyết định lỗi nào được retry. Ví dụ lỗi hạ tầng tạm thời có thể retry, còn payload vi phạm contract thường nên recover nhanh.

Một listener test có thể ném hai loại exception khác nhau:

~~~java
@Component
public class OrderListener {

    private final AtomicInteger transientAttempts = new AtomicInteger();

    @KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-test-group"
    )
    public void listen(String payload) {
        if (payload.equals("temporary")) {
            if (transientAttempts.getAndIncrement() < 2) {
                throw new TransientOrderException("Temporary failure");
            }
        }

        if (payload.equals("invalid")) {
            throw new InvalidOrderEventException("Invalid payload");
        }

        process(payload);
    }
}
~~~

Test cần xác nhận:

- `temporary` được gọi lại theo retry policy và cuối cùng thành công.
- `invalid` không bị retry nếu đã cấu hình non-retryable.
- Exception không nằm trong classifier vẫn có behavior đúng với default classification của version đang dùng.
- Exception wrapper có cause chain được phân loại theo rule đã cấu hình.

Không chỉ assert rằng `addNotRetryableExceptions` được gọi trong cấu hình. Hãy gửi record thực tế và xác nhận số lần listener invocation để kiểm tra wiring từ container tới handler.

## 6. Unit test retry policy và destination resolver

Những rule thuần như ánh xạ topic/partition có thể test không cần broker:

~~~java
@Test
void shouldRouteFailedRecordToMatchingDltPartition() {
    ConsumerRecord<String, String> record =
        new ConsumerRecord<>(
            "orders",
            2,
            105L,
            "order-42",
            "invalid"
        );

    TopicPartition destination =
        new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        );

    assertThat(destination.topic()).isEqualTo("orders.DLT");
    assertThat(destination.partition()).isEqualTo(2);
}
~~~

Test này chỉ kiểm tra rule route. Nó không chứng minh topic DLT tồn tại, serializer publish được record hoặc offset nguồn được commit.

Với resolver tùy chỉnh, test thêm các trường hợp:

- Topic nguồn khác nhau.
- Partition nguồn ở biên topology.
- Partition được remap theo modulo.
- Exception type làm thay đổi destination.
- Destination không hợp lệ phải thất bại rõ ràng.
- Key/value raw bytes được bảo toàn nếu xử lý deserialization failure.

Đối với `BackOff`, có thể kiểm tra số lần `nextBackOff()` và trạng thái STOP bằng unit test riêng. Integration test vẫn cần xác nhận handler thực sự áp dụng policy đó.

## 7. Integration test với Embedded Kafka

`@EmbeddedKafka` khởi động broker nhúng cho test, giúp kiểm tra listener container, producer, consumer và DLT mà không cần cluster bên ngoài.

Ví dụ khai báo:

~~~java
@SpringBootTest
@EmbeddedKafka(
    partitions = 3,
    topics = {"orders", "orders.DLT"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderErrorHandlerIntegrationTest {
    // Test dùng KafkaTemplate và listener container thật.
}
~~~

Cấu hình ứng dụng test nên tắt auto commit và dùng group ID riêng cho test. DLT cần số partition tương ứng nếu recoverer mặc định giữ partition nguồn. Nếu test chạy song song, mỗi test class hoặc test case cần topic/group tách biệt hoặc cleanup rõ ràng để tránh đọc nhầm record của lần chạy trước.

Embedded Kafka phù hợp cho integration test nhanh. Nó không thay thế hoàn toàn test với broker/container version tương ứng production, đặc biệt với ACL, TLS, broker rolling, replication và failure mode của cluster nhiều node.

## 8. Tạo consumer test để đọc DLT

Đăng ký consumer DLT trước khi gửi record lỗi. Dùng group ID riêng, `auto.offset.reset=earliest` và deserializer tương thích với kiểu dữ liệu đã publish.

Ví dụ helper:

~~~java
private Consumer<String, String> createDltConsumer(
        EmbeddedKafkaBroker embeddedKafka) {

    Map<String, Object> props =
        KafkaTestUtils.consumerProps(
            "dlt-test-" + UUID.randomUUID(),
            "false",
            embeddedKafka
        );

    props.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    Consumer<String, String> consumer =
        new KafkaConsumer<>(props);

    embeddedKafka.consumeFromAnEmbeddedTopic(
        consumer,
        "orders.DLT"
    );

    return consumer;
}
~~~

Tên và overload của `KafkaTestUtils.consumerProps` thay đổi giữa các dòng Spring Kafka. Nếu compiler không nhận overload trên, dùng signature được cung cấp bởi version dependency của dự án; mục tiêu là tạo consumer có bootstrap server từ Embedded Kafka, group ID riêng và auto commit tắt.

Đóng consumer trong `finally` hoặc try-with-resources. Không để consumer test chạy nền sau khi test kết thúc vì nó có thể giữ thread và làm rò rỉ tài nguyên.

## 9. Test record được chuyển sang DLT

Với một payload luôn làm listener ném `InvalidOrderEventException` và exception đã được cấu hình non-retryable, test có thể gửi record rồi đọc DLT:

~~~java
@Test
void invalidRecordShouldBePublishedToDlt() {
    try (Consumer<String, String> dltConsumer =
             createDltConsumer(embeddedKafka)) {

        kafkaTemplate.send("orders", "order-42", "invalid");

        ConsumerRecord<String, String> dltRecord =
            KafkaTestUtils.getSingleRecord(
                dltConsumer,
                "orders.DLT",
                Duration.ofSeconds(10)
            );

        assertThat(dltRecord.key()).isEqualTo("order-42");
        assertThat(dltRecord.value()).isEqualTo("invalid");
    }
}
~~~

Test cần xác nhận đúng topic đích, key/value, partition theo resolver và metadata header. Nếu DLT consumer nhận record sau một khoảng chờ, dùng timeout đủ dài theo môi trường CI nhưng không dùng sleep cố định.

Nếu listener có thể xử lý record thành công sau retry, record đó không nên xuất hiện ở DLT. Test riêng hai nhánh success-after-retry và exhausted-retry để tránh một assertion duy nhất che mất lỗi policy.

## 10. Kiểm tra số lần retry

Đếm invocation của listener là cách trực tiếp để kiểm tra retry policy. Dùng `AtomicInteger` hoặc test probe thread-safe vì listener chạy trên consumer thread.

Ví dụ với hai retry sau lần đầu:

~~~java
@Test
void transientFailureShouldBeRetriedBeforeSuccess() {
    kafkaTemplate.send("orders", "order-7", "temporary");

    await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
            assertThat(listener.transientAttempts()).isEqualTo(3)
        );

    assertThat(listener.processedOrderIds())
        .contains("order-7");
}
~~~

Số lần chính xác phụ thuộc `BackOff`, classifier, recoverer và cách listener được viết. Với `FixedBackOff(interval, maxAttempts)`, tham số attempts là số lần retry sau lần đầu, không phải tổng số invocation.

Không assert timing chính xác theo mili giây trong integration test. Scheduler, broker startup và CI load có thể làm thời gian thực tế dao động. Test policy bằng số lần invocation và dùng timeout rộng để chờ kết quả cuối cùng.
## 11. Kiểm tra DLT metadata

DLT không chỉ cần chứa payload; record phải có metadata đủ để truy ngược nguồn. Với `DeadLetterPublishingRecoverer` mặc định, Spring Kafka thêm các header mô tả original topic, partition, offset, timestamp và exception.

Ví dụ kiểm tra header:

~~~java
assertThat(dltRecord.headers()
        .lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC))
    .isNotNull();

assertThat(dltRecord.headers()
        .lastHeader(KafkaHeaders.DLT_ORIGINAL_PARTITION))
    .isNotNull();

assertThat(dltRecord.headers()
        .lastHeader(KafkaHeaders.DLT_ORIGINAL_OFFSET))
    .isNotNull();
~~~

Header value là byte array; nếu cần so sánh, chuyển đổi theo kiểu dữ liệu được Spring Kafka ghi vào header hoặc dùng helper trong test. Đừng so sánh trực tiếp object header với String hay Long.

Test thêm:

- Original topic đúng topic nguồn.
- Original partition và offset khớp record nguồn.
- Exception class/message được thêm theo cấu hình header.
- Header không bị mất khi có custom destination resolver.
- DLT partition đúng với policy giữ nguyên hoặc remap.
- Key và payload giữ nguyên nếu serializer hỗ trợ kiểu dữ liệu đó.

Nếu ứng dụng chủ động thay đổi header qua `setHeadersFunction` hoặc `setExceptionHeadersCreator`, test cần xác nhận cả metadata chuẩn và header tùy chỉnh.

## 12. Kiểm tra offset sau recovery

Một integration test chỉ đọc thấy record trong DLT chưa đủ chứng minh consumer group đã tiến qua record nguồn. Nếu offset không được xác nhận theo recovery policy, record nguồn có thể được giao lại sau restart và xuất hiện thêm lần nữa trong DLT.

Có thể đọc committed offset bằng AdminClient:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets =
    adminClient.listConsumerGroupOffsets("orders-test-group")
        .partitionsToOffsetAndMetadata()
        .get(10, TimeUnit.SECONDS);

OffsetAndMetadata committed =
    offsets.get(new TopicPartition("orders", sourcePartition));

assertThat(committed).isNotNull();
assertThat(committed.offset()).isGreaterThan(sourceOffset);
~~~

Để test có kết quả xác định, gửi record vào partition cụ thể và lưu metadata trả về từ `KafkaTemplate.send(...).get(...)`. Sau khi DLT publish hoàn tất, chờ committed offset vượt qua source offset đó.

Committed offset biểu thị vị trí tiếp theo cần đọc, vì vậy sau khi record ở offset `n` được xác nhận, committed offset thường lớn hơn `n` (thường là `n + 1` nếu không có gap trong cùng partition).

Offset assertion phải tính đến AckMode, manual acknowledgment, container transaction và `commitRecovered`. Không hard-code kỳ vọng cho một cấu hình khác với cấu hình đang test.

## 13. Kiểm tra recoverer publish thất bại

Recovery chỉ hoàn tất khi thao tác publish DLT đáp ứng policy của ứng dụng. Nếu producer gửi DLT thất bại nhưng handler vẫn coi record là recovered, offset nguồn có thể tiến và record bị mất khỏi luồng xử lý.

Có thể cấu hình recoverer kiểm tra send result:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(dltTemplate);

recoverer.setFailIfSendResultIsError(true);
recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(5));
~~~

Tên API và kiểu timeout có thể khác theo Spring Kafka version; dùng đúng signature trong dependency đang chạy.

Test failure path bằng cách làm DLT producer không thể publish, ví dụ dùng topic không tồn tại trong môi trường tắt auto-create hoặc producer có ACL bị từ chối. Xác nhận:

- Recovery được ghi nhận là thất bại.
- Exception của recovery được quan sát theo cấu hình handler.
- Offset nguồn không tiến như thể record đã recover thành công.
- Khi DLT publish được khôi phục, record có thể được xử lý lại theo policy.
- Log/metric phân biệt listener failure với DLT publish failure.

Không chỉ mock `KafkaTemplate.send()` ném exception rồi kết luận đã test broker-side authorization hoặc topic routing. Mock phù hợp cho unit test; integration test cần kiểm tra failure từ broker.

## 14. Test retry listener và metrics

Nếu ứng dụng dùng `RetryListener` để phát metric, có thể inject một test probe thread-safe và xác nhận callback được gọi:

~~~java
public class RetryProbe implements RetryListener {

    private final AtomicInteger failedDeliveries = new AtomicInteger();
    private final AtomicInteger recoveredRecords = new AtomicInteger();

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        failedDeliveries.incrementAndGet();
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        recoveredRecords.incrementAndGet();
    }

    public int failedDeliveries() {
        return failedDeliveries.get();
    }

    public int recoveredRecords() {
        return recoveredRecords.get();
    }
}
~~~

Gắn probe vào handler trong test configuration:

~~~java
handler.setRetryListeners(retryProbe);
~~~

Sau khi gửi record lỗi, chờ probe cập nhật rồi assert số callback theo semantics version đang dùng. `deliveryAttempt` thường bắt đầu từ lần delivery thất bại đầu tiên; hãy xác nhận giá trị qua version runtime thay vì giả định chỉ số luôn bằng số retry.

Metric production nên có tag giới hạn như topic, exception class và listener ID. Tránh dùng event ID hoặc offset làm metric label vì cardinality có thể tăng không giới hạn.

## 15. Kiểm thử deserialization failure

Deserialization failure xảy ra trước khi listener nhận được object Java. Vì vậy, test payload JSON sai phải xác nhận listener không được gọi và error handling vẫn đưa được raw bytes sang DLT nếu đó là policy.

Cấu hình consumer dùng `ErrorHandlingDeserializer` bọc delegate:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Trong test, gửi byte payload không phải JSON hợp lệ tới topic nguồn. Xác nhận:

- Listener invocation count không tăng.
- Container error handling nhận được deserialization exception.
- Recoverer publish được record lỗi sang DLT theo cấu hình.
- Raw value bytes còn nguyên nếu yêu cầu lưu payload gốc.
- Exception metadata/header có thể truy vết nguyên nhân.

Nếu DLT template có thể nhận cả object đã deserialize và raw `byte[]`, cấu hình serializer đa kiểu, ví dụ `DelegatingByTypeSerializer`. DLT consumer trong test phải đọc `byte[]` khi kiểm tra payload deserialize thất bại; không dùng `StringDeserializer` rồi mặc định rằng bytes sẽ tự chuyển đúng.

Test riêng key deserialization failure và value deserialization failure vì hai trường hợp có header và raw bytes ở vị trí khác nhau. Cũng test tombstone/null value hợp lệ để tránh nhầm null thật với deserialize failure.

## 16. Test batch listener và BatchListenerFailedException

Batch listener có semantics error handling khác record listener. Khi một record trong batch lỗi, ứng dụng có thể ném `BatchListenerFailedException` kèm vị trí record lỗi để `DefaultErrorHandler` xác định phần cần seek/retry theo batch policy.

Ví dụ minh họa:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-batch-test",
    containerFactory = "batchListenerFactory"
)
public void listenBatch(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int index = 0; index < records.size(); index++) {
        try {
            process(records.get(index).value());
        }
        catch (Exception exception) {
            throw new BatchListenerFailedException(
                "Batch record failed",
                exception,
                index
            );
        }
    }
}
~~~

Constructor của `BatchListenerFailedException` có thể khác theo phiên bản Spring Kafka. Test phải dùng đúng signature của dependency dự án.

Các assertion nên có:

- Batch listener được gọi với batch có nhiều record.
- Index lỗi đúng với record gây exception.
- Record trước vị trí lỗi không bị xử lý lại nếu policy cho phép commit phần trước.
- Record lỗi được retry theo backoff.
- Record sau lỗi được seek và giao lại theo semantics batch handler.
- Khi hết retry, chỉ record được recover theo policy đi vào DLT.

Nếu batch listener ném exception chung mà không chỉ rõ failed index, handler có thể phải retry cả batch. Test điều này riêng và bảo đảm nghiệp vụ batch idempotent.

## 17. Test transactional listener: dùng AfterRollbackProcessor

Nếu container có Kafka transaction, test đường rollback qua `AfterRollbackProcessor`, không áp dụng nguyên xi kỳ vọng của `DefaultErrorHandler`.

Cấu hình transactional listener thường có:

- ProducerFactory transactional với transaction ID prefix.
- `KafkaTransactionManager` gắn vào listener container.
- Consumer auto commit tắt.
- Consumer downstream dùng `read_committed`.
- `DefaultAfterRollbackProcessor` để retry/recover sau transaction rollback.

Test cần xác nhận listener exception làm transaction rollback, output record thuộc transaction bị abort không hiển thị với consumer `read_committed`, input offset không commit trong transaction thất bại và record được giao lại theo after-rollback policy.

Nếu retry hết và processor gửi record sang DLT với `commitRecovered=true`, xác nhận DLT record xuất hiện và offset nguồn được commit trong transaction recovery mới. DLT publish failure phải được test riêng.

Không dùng `DefaultErrorHandler` để thay thế test `DefaultAfterRollbackProcessor`. Hai đường xử lý có lifecycle khác nhau.

## 18. Test AckMode và manual acknowledgment

Offset behavior phụ thuộc AckMode và cách listener xác nhận record. Khi test error handler, phải dùng cùng AckMode như production.

| AckMode | Điều cần xác nhận |
| --- | --- |
| RECORD | Offset được xác nhận sau khi từng record listener hoàn tất thành công. |
| BATCH | Offset được xác nhận theo batch poll sau khi batch hoàn tất. |
| MANUAL | Listener gọi acknowledge theo logic ứng dụng. |
| MANUAL_IMMEDIATE | Acknowledge có thể commit ngay khi được gọi trên consumer thread; hành vi cần xét thread và container configuration. |

Với manual acknowledgment, test thêm trường hợp listener ném exception trước và sau khi gọi acknowledge. Không gọi acknowledge rồi tiếp tục làm nghiệp vụ có thể thất bại nếu ứng dụng không chấp nhận record đã được xác nhận.

Nếu dùng asynchronous acknowledgment hoặc worker pool, kiểm tra thứ tự acknowledge, out-of-order completion, rebalance và shutdown theo đúng version. Đừng chỉ kiểm thử handler mà bỏ qua offset contract của listener.

## 19. Kiểm thử listener có concurrency

Khi container concurrency lớn hơn một, nhiều child consumer có thể xử lý record song song. Test cần tránh dùng một counter không thread-safe hoặc giả định record được xử lý theo thứ tự toàn topic.

Nên kiểm tra:

- Retry của một partition không làm sai xử lý partition khác.
- DLT routing giữ đúng source partition theo resolver.
- Consumer group có assignment như mong đợi.
- State dùng chung trong test được bảo vệ bằng `AtomicInteger`, concurrent collection hoặc synchronization.
- Không dùng cùng event key nếu test cần chứng minh xử lý song song độc lập.
- Không assert global ordering giữa các partition.

Nếu test chỉ tập trung error handler của một record, đặt concurrency bằng một để giảm nondeterminism. Có test concurrency riêng khi hành vi đa consumer là mục tiêu cần xác minh.

## 20. Dùng Awaitility thay cho sleep

Kafka processing bất đồng bộ. Sau khi gọi `KafkaTemplate.send`, listener chưa chắc đã xử lý xong ngay tại dòng tiếp theo.

Tránh:

~~~java
Thread.sleep(2_000);
assertThat(dltRecords).hasSize(1);
~~~

Dùng điều kiện chờ có timeout:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertThat(dltRecords()).hasSize(1)
    );
~~~

Hoặc dùng `CountDownLatch` nếu test cần chờ một listener callback cụ thể. Timeout phải đủ rộng cho CI nhưng không quá dài khiến test suite chậm khi có lỗi.

Không poll consumer test và assert ngay khi chưa có record. `KafkaTestUtils.getSingleRecord` có thể chờ trong thời gian giới hạn; nếu tự dùng `poll`, lặp đến deadline và tích lũy records thay vì giả định một poll luôn trả kết quả.

## 21. Làm test ổn định và dễ chẩn đoán

Các nguyên nhân thường làm test error handler flaky:

- Consumer test được tạo sau khi record đã publish và dùng offset reset `latest`.
- Tái sử dụng group ID khiến consumer bắt đầu ở committed offset cũ.
- Topic DLT có ít partition hơn nguồn trong khi resolver giữ nguyên partition index.
- Dùng chung topic và listener state giữa các test chạy song song.
- Không đóng consumer hoặc không dừng listener container.
- Dùng sleep cố định thay vì chờ condition.
- Test dựa vào log text thay vì quan sát record/offset.
- Backoff quá dài làm suite chậm hoặc quá ngắn khiến race condition khó tái hiện.
- Producer/consumer serializer trong test không tương thích với DLT payload.

Mỗi test nên có event ID riêng, group ID riêng và topic tách biệt nếu có thể. Khi test fail, log topic, partition, offset, group ID, attempt count và exception class. Không log toàn bộ payload nhạy cảm.

Dùng `@DirtiesContext` khi test thực sự làm thay đổi Spring context hoặc container state không thể khôi phục; không thêm annotation này vào mọi test vì nó làm khởi động lại context và kéo dài suite.

## 22. Checklist kiểm thử error handler

Trước khi xem error handling là đủ test, hãy xác nhận:

1. Listener success không đi vào retry hoặc DLT.
2. Retryable exception được thử lại đúng số lần.
3. Non-retryable exception được recover theo policy.
4. Exception cause chain được phân loại đúng nếu ứng dụng có wrap exception.
5. Backoff và retry limit có test riêng.
6. Recoverer chọn đúng DLT topic và partition.
7. DLT giữ đúng key, payload và source metadata headers.
8. DLT publish failure không làm record nguồn bị coi là recovered.
9. Committed offset tiến đúng theo AckMode/recovery policy.
10. Deserialization failure không gọi listener và raw bytes được bảo toàn nếu yêu cầu.
11. Key failure, value failure và tombstone được phân biệt.
12. Batch listener xác định đúng failed index và redelivery range.
13. Transactional listener được test qua AfterRollbackProcessor.
14. Consumer downstream dùng read_committed khi cần xác nhận transaction visibility.
15. Manual acknowledgment và async handoff có test offset riêng.
16. Concurrency/rebalance không làm mất record hoặc route sai.
17. Test dùng Awaitility/latch với timeout, không dựa vào sleep.
18. Consumer, container và broker test được đóng đúng lifecycle.

Kiểm thử error handler phải xác nhận hành vi từ listener đến broker: số lần retry, backoff, exception classification, DLT publish và offset recovery. Unit test phù hợp cho rule thuần; Embedded Kafka hoặc Testcontainers cần thiết để kiểm tra seek, poll, serialization, headers và committed offset. Với transactional listener, dùng AfterRollbackProcessor và kiểm tra transaction visibility riêng để không nhầm semantics với DefaultErrorHandler.


