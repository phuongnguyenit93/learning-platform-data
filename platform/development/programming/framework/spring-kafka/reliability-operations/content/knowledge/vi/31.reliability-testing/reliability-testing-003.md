# Test consumer retry trong Spring Kafka

## 1. Mục tiêu kiểm thử

Consumer retry là cơ chế thử xử lý lại một Kafka record khi listener gặp lỗi tạm thời. Trong Spring Kafka, retry có thể được thực hiện ngay trong listener container bằng `DefaultErrorHandler` (blocking retry), hoặc bằng cách chuyển record qua các retry topic theo lịch với `@RetryableTopic` (non-blocking retry). Kiểm thử cần chứng minh chính sách retry đang chạy đúng với cấu hình và bảo vệ được dữ liệu khi xử lý thất bại.

Một bộ kiểm thử consumer retry nên trả lời được các câu hỏi sau:

- Listener có được gọi lại khi gặp exception được phép retry không?
- Số lần thử thực tế có khớp cấu hình không, và lần thử ban đầu có được tính vào tổng số lần thử hay không?
- Consumer có dừng retry khi xử lý thành công không?
- Exception nào được retry, exception nào được chuyển thẳng đến recoverer hoặc DLT?
- Sau khi hết số lần thử, record có được chuyển đúng DLT và giữ metadata nguồn cần thiết không?
- Record tiếp theo có tiếp tục được xử lý sau khi record trước được recover không?
- Offset, partition, ordering và khả năng xử lý lặp có đáp ứng yêu cầu nghiệp vụ không?
- Với non-blocking retry, record có đi qua đúng retry topic, delay và DLT không?

Kiểm thử phải quan sát được hành vi của consumer và Kafka. Chỉ kiểm tra một method được gọi trong unit test chưa chứng minh listener container, error handler, producer gửi DLT và consumer group phối hợp đúng khi chạy thực tế.

## 2. Phân biệt hai cơ chế retry

### Blocking retry với `DefaultErrorHandler`

`DefaultErrorHandler` xử lý lỗi trong luồng listener container. Khi listener ném exception có thể retry, container thực hiện các lần thử lại theo `BackOff`. Khi hết số lần thử, error handler gọi recoverer, thường là `DeadLetterPublishingRecoverer` để gửi record sang DLT.

Ví dụ cấu hình:

```java
@Configuration
public class KafkaRetryConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(KafkaTemplate<String, String> template) {
        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(template,
                        (record, exception) -> new TopicPartition(
                                record.topic() + ".DLT",
                                record.partition()));

        // 100 ms giữa các lần retry; tối đa 2 lần retry sau lần gọi đầu.
        return new DefaultErrorHandler(recoverer, new FixedBackOff(100L, 2L));
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String> kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            DefaultErrorHandler ordersErrorHandler) {

        ConcurrentKafkaListenerContainerFactory<String, String> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(ordersErrorHandler);
        return factory;
    }
}
```

Với `new FixedBackOff(100L, 2L)`, listener có tối đa **3 lần được gọi cho cùng record**: một lần ban đầu và hai lần retry. Tham số thứ hai là số lần retry thêm, không phải tổng số lần gọi. Đây là điểm cần xác nhận rõ trong test để tránh cấu hình hoặc alert đếm sai.

### Non-blocking retry với `@RetryableTopic`

`@RetryableTopic` chuyển record sang các retry topic thay vì giữ consumer thread chờ retry. Sau số lần thử đã cấu hình, record được chuyển đến DLT. Các retry topic có thể được tạo tự động hoặc được provision trước theo cấu hình triển khai.

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 100, multiplier = 2.0),
        dltTopicSuffix = "-dlt")
@KafkaListener(topics = "orders.nonblocking", groupId = "orders-retry-it")
public void consume(OrderEvent event) {
    orderService.process(event);
}

@DltHandler
public void handleDlt(OrderEvent event) {
    // Ghi nhận hoặc chuyển đến quy trình xử lý lỗi cuối cùng.
}
```

Trong cấu hình này, `attempts = "4"` biểu thị tổng số lần thử, bao gồm lần xử lý ban đầu. Xác nhận cách tính này trong phiên bản Spring Kafka đang sử dụng. Tên retry topic, DLT và số partition phụ thuộc suffix, topic naming strategy và cấu hình thực tế.

| Đặc điểm | Blocking retry | Non-blocking retry |
|---|---|---|
| Cách retry | Gọi lại listener trong luồng container | Publish record sang retry topic |
| Cấu hình phổ biến | `DefaultErrorHandler`, `BackOff`, recoverer | `@RetryableTopic`, `@Backoff`, DLT handler |
| Đếm số lần thử | `FixedBackOff` quy định số lần retry thêm sau lần đầu | `attempts` quy định tổng số lần thử |
| Tác động đến consumer | Record lỗi có thể giữ luồng xử lý trong thời gian backoff | Consumer ban đầu có thể tiếp tục xử lý record khác |
| Ordering | Retry blocking có thể giữ partition bị ảnh hưởng trong quá trình xử lý lỗi | Thứ tự giữa các record có thể thay đổi do các topic và delay khác nhau |
| Điều cần kiểm tra | Số invocation, backoff, recovery và offset | Định tuyến qua retry topic, thời gian chờ, tổng attempts và DLT |

Không dùng cùng một kỳ vọng về số lần thử hoặc thứ tự cho cả hai cơ chế. Trước khi viết test, xác định listener đang dùng cơ chế nào và phiên bản Spring Kafka cụ thể.

## 3. Chọn cấp độ kiểm thử

### Unit test cho logic phân loại lỗi

Unit test phù hợp để kiểm tra logic thuần của ứng dụng, ví dụ:

- Phân loại exception tạm thời và exception không thể phục hồi.
- Quyết định có retry một loại lỗi hay không.
- Tính toán delay trong một `BackOff` tùy chỉnh.
- Xây dựng idempotency key hoặc quyết định nghiệp vụ khi nhận lại cùng event.

Unit test không cần khởi động Kafka broker. Có thể mock service hoặc dependency và xác nhận logic phân loại. Không nên dùng mock để thay thế toàn bộ `DefaultErrorHandler` hoặc `@RetryableTopic` rồi kết luận retry integration đã đúng.

### Integration test với Embedded Kafka

Embedded Kafka phù hợp để kiểm tra luồng Spring Kafka trong một test context:

- Producer gửi record vào topic kiểm thử.
- Listener container nhận record và gọi listener.
- Error handler thực hiện retry theo cấu hình.
- Recoverer gửi record sang DLT.
- Test consumer đọc DLT và xác nhận key, value, partition cùng header cần thiết.

Embedded broker giúp test tự chủ, nhanh và không phụ thuộc Kafka dùng chung. Nó vẫn là broker Kafka thực trong tiến trình kiểm thử, nhưng không thay thế kiểm thử hạ tầng production như ACL, TLS, quota hoặc cấu hình broker riêng.

### Integration test với Testcontainers

Chọn Testcontainers khi cần kiểm tra với phiên bản Kafka hoặc cấu hình broker gần môi trường triển khai, hoặc cần xác minh hành vi liên quan đến broker image, listener endpoint và cấu hình container. Testcontainers cần Docker runtime và thường chậm hơn Embedded Kafka.

### Kiểm thử trên môi trường triển khai

Một số hành vi chỉ có thể xác nhận đầy đủ trên môi trường gần production: ACL, SASL/TLS, schema registry, broker quota, network policy, số partition thực tế và khả năng chịu tải. Chạy test có kiểm soát với topic và consumer group riêng, không dùng topic hoặc group đang phục vụ nghiệp vụ.

## 4. Chuẩn bị test dependencies

Với dự án Spring Boot dùng Gradle, thêm Spring Kafka test support vào cấu hình test. Dùng dependency management/BOM của Spring Boot để chọn phiên bản tương thích với Spring Kafka trong ứng dụng.

```groovy
dependencies {
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
}
```

`spring-kafka-test` cung cấp `@EmbeddedKafka`, `EmbeddedKafkaBroker`, `KafkaTestUtils` và các tiện ích kiểm thử Kafka. Awaitility giúp chờ một điều kiện bất đồng bộ đạt được mà không phải đặt một khoảng `Thread.sleep` cố định.

Một số API test utility thay đổi theo phiên bản Spring Kafka. Khi nâng phiên bản, kiểm tra API của dependency thực tế, đặc biệt cách khai báo bootstrap server cho Embedded Kafka, cách poll consumer và cách lấy record đơn.

## 5. Tạo listener có thể điều khiển trong integration test

Test cần một cách tạo lỗi xác định. Tránh phụ thuộc vào database hoặc API thật chỉ để làm listener thất bại. Có thể dùng một probe thread-safe trong test context để quy định record sẽ thất bại bao nhiêu lần trước khi thành công.

Ví dụ listener:

```java
@Component
public class RetryProbe {

    private final AtomicInteger attempts = new AtomicInteger();
    private final AtomicInteger failuresBeforeSuccess = new AtomicInteger();

    public void failForNextRecord(int failures) {
        attempts.set(0);
        failuresBeforeSuccess.set(failures);
    }

    public int attempts() {
        return attempts.get();
    }

    @KafkaListener(
            id = "orders-retry-listener",
            topics = "${app.kafka.orders-topic}",
            groupId = "orders-retry-it")
    public void listen(ConsumerRecord<String, String> record) {
        int currentAttempt = attempts.incrementAndGet();
        if (currentAttempt <= failuresBeforeSuccess.get()) {
            throw new IllegalStateException("simulated transient failure");
        }
    }
}
```

Probe này cố ý đơn giản để minh họa retry của một record trong một test. Nếu test có nhiều record đồng thời, cần đếm theo key hoặc correlation ID thay vì dùng một counter chung. Không để test chạy song song trên cùng listener state nếu các test có thể ghi đè số lần lỗi của nhau.

Trong ứng dụng thực tế, listener thường gọi service nghiệp vụ. Có thể thay dependency bằng test double để kiểm soát số lần thất bại, trong khi vẫn giữ listener container và error handler thật.

## 6. Kiểm thử blocking retry bằng Embedded Kafka

### Cấu hình test broker

Khai báo source topic và DLT topic trong test. Ví dụ dưới đây dùng một partition để kiểm tra định tuyến partition gốc một cách đơn giản:

```java
@SpringBootTest(properties = {
        "app.kafka.orders-topic=orders",
        "spring.kafka.consumer.auto-offset-reset=earliest"
})
@EmbeddedKafka(
        partitions = 1,
        topics = {"orders", "orders.DLT"},
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class BlockingRetryIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    RetryProbe retryProbe;

    // Các test được trình bày ở phần tiếp theo.
}
```

Đảm bảo producer và consumer test dùng `StringSerializer`/`StringDeserializer`, và listener factory trong test thực sự được gắn `DefaultErrorHandler`. Với nhiều phiên bản Spring Kafka, `@EmbeddedKafka` có thuộc tính bootstrap server khác nhau; dùng thuộc tính được hỗ trợ bởi phiên bản đang cài đặt.

### Test retry thành công trước khi hết số lần thử

Giả sử listener thất bại hai lần rồi thành công ở lần thứ ba, với `FixedBackOff(100L, 2L)`. Test cần xác nhận listener được gọi ba lần và record không bị chuyển sang DLT.

```java
@Test
void retriesUntilListenerSucceeds() throws Exception {
    retryProbe.failForNextRecord(2);

    kafkaTemplate.send("orders", "order-42", "payload")
            .get(10, TimeUnit.SECONDS);

    await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
            assertThat(retryProbe.attempts()).isEqualTo(3));
}
```

Việc producer send hoàn tất chỉ xác nhận producer nhận kết quả gửi theo cấu hình; nó không có nghĩa listener đã xử lý record. Vì vậy, test tiếp tục chờ counter listener đạt giá trị mong đợi. Trong test đầy đủ, nên bổ sung một tín hiệu xử lý thành công theo key hoặc ghi nhận kết quả từ service để chứng minh lần cuối đã hoàn tất.

### Test chuyển DLT sau khi hết retry

Khi listener luôn thất bại, `DefaultErrorHandler` phải gọi recoverer sau lần thử ban đầu và hai lần retry. Test cần đọc record từ DLT, đồng thời kiểm tra số lần gọi listener.

```java
@Test
void publishesRecordToDltAfterRetriesAreExhausted() throws Exception {
    retryProbe.failForNextRecord(Integer.MAX_VALUE);

    Map<String, Object> consumerProps = KafkaTestUtils.consumerProps(
            "dlt-assert-" + UUID.randomUUID(), "false", embeddedKafka);
    consumerProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    try (Consumer<String, String> dltConsumer =
                 new DefaultKafkaConsumerFactory<String, String>(
                         consumerProps,
                         new StringDeserializer(),
                         new StringDeserializer()).createConsumer()) {

        embeddedKafka.consumeFromAnEmbeddedTopic(dltConsumer, "orders.DLT");

        kafkaTemplate.send("orders", "order-99", "bad-payload")
                .get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> dltRecord = await()
                .atMost(Duration.ofSeconds(15))
                .until(() -> {
                    ConsumerRecords<String, String> records =
                            dltConsumer.poll(Duration.ofMillis(250));
                    return records.isEmpty() ? null : records.iterator().next();
                }, Objects::nonNull);

        assertThat(retryProbe.attempts()).isEqualTo(3);
        assertThat(dltRecord.key()).isEqualTo("order-99");
        assertThat(dltRecord.value()).isEqualTo("bad-payload");
        assertThat(dltRecord.topic()).isEqualTo("orders.DLT");
    }
}
```

Các import tương ứng thường gồm `Consumer`, `ConsumerRecord`, `ConsumerRecords`, `ConsumerConfig`, `DefaultKafkaConsumerFactory`, `StringDeserializer`, `KafkaTestUtils`, `Duration`, `UUID`, `Objects` và Awaitility. Điều chỉnh generic type và API của `createConsumer()` theo phiên bản Spring Kafka của dự án.

Test consumer phải subscribe/assign DLT trước khi gửi record để tránh bỏ lỡ message trong các cấu hình test không đọc từ đầu. `consumeFromAnEmbeddedTopic` thường gán partition và seek theo chính sách của utility; xác minh hành vi của phiên bản đang dùng nếu test cần đọc từ một offset cụ thể.

Trong test thực tế, nên kiểm tra thêm DLT header nếu ứng dụng dựa vào metadata nguồn:

```java
assertThat(dltRecord.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC))
        .isNotNull();
assertThat(dltRecord.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_OFFSET))
        .isNotNull();
```

Header cụ thể phụ thuộc phiên bản Spring Kafka, recoverer và cấu hình header. Hãy xác nhận tên header và giá trị trong message thật. Nếu dùng destination resolver tùy chỉnh, kiểm tra topic và partition đích đúng với quy tắc định tuyến của ứng dụng.

### Điều gì cần tránh trong ví dụ

Không dùng một `Thread.sleep(5000)` rồi giả định retry đã hoàn tất. Thời gian xử lý phụ thuộc broker, scheduler và tải của test process. Chờ điều kiện quan sát được như counter, record ở DLT hoặc kết quả nghiệp vụ giúp test ổn định hơn. Cũng không nên assert một khoảng thời gian chính xác cho từng lần retry; scheduler và hệ điều hành có thể tạo sai số.

## 7. Kiểm thử phân loại exception

Không phải exception nào cũng nên retry. Ví dụ lỗi timeout tạm thời có thể retry, trong khi lỗi validation do payload sai định dạng thường không thay đổi nếu gửi lại cùng record.

Với `DefaultErrorHandler`, có thể cấu hình exception không retry bằng `addNotRetryableExceptions(...)` hoặc phân loại qua `setClassifications(...)`, tùy nhu cầu và phiên bản. Test nên kiểm tra riêng từng nhánh:

| Kịch bản | Hành vi mong đợi |
|---|---|
| Exception tạm thời, lần sau thành công | Listener được gọi lại đúng số lần cần thiết; record được xử lý thành công |
| Exception tạm thời, luôn thất bại | Thử đủ số lần; sau đó gọi recoverer hoặc DLT |
| Exception không retry | Không thực hiện các lần retry cấu hình; chuyển đến recovery theo chính sách |
| Exception được bọc trong exception khác | Phân loại đúng theo cause chain hoặc classifier đã cấu hình |
| Recoverer xử lý thành công | Record được phục hồi theo chính sách; consumer tiếp tục xử lý record kế tiếp |

Ví dụ khai báo exception không retry:

```java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(100L, 2L));

errorHandler.addNotRetryableExceptions(IllegalArgumentException.class);
```

Test cho `IllegalArgumentException` cần xác nhận listener chỉ được gọi một lần trước khi recovery. Test cho exception khác cần xác nhận số lần gọi theo `BackOff`. Nếu ứng dụng có custom exception classifier, kiểm thử trực tiếp các trường hợp subclass và cause lồng nhau để tránh phân loại sai.

Không dùng exception quá tổng quát như `RuntimeException` làm non-retryable nếu trong ứng dụng có nhiều lỗi tạm thời kế thừa từ loại đó. Ngược lại, không retry lỗi validation vô hạn hoặc quá nhiều lần chỉ vì tất cả lỗi đều được xử lý bởi một catch block.

## 8. Kiểm thử non-blocking retry với `@RetryableTopic`

Non-blocking retry phải được kiểm tra qua các topic trung gian. Test cần chứng minh record được gửi lại theo lịch, đến DLT sau tổng số attempts và không bị xử lý lặp ngoài dự kiến.

### Xác định topic cần kiểm tra

Tên retry topic phụ thuộc cấu hình `@RetryableTopic`, suffix, chiến lược đặt tên topic và phiên bản Spring Kafka. Trước khi test, xác định danh sách topic thực tế được tạo từ cấu hình. Có thể provision topic bằng `@EmbeddedKafka(topics = {...})` hoặc cơ chế tạo topic được phép trong test. Không hardcode tên topic suy đoán từ một ví dụ rồi dùng cho mọi phiên bản.

Với một cấu hình retry có nhiều delay, cần xác định số retry topic được tạo, partition count, replication factor và topic DLT. Khi dùng broker test có auto topic creation, vẫn nên kiểm tra topic thực sự tồn tại và có số partition phù hợp với source topic.

### Kịch bản cần kiểm tra

1. Gửi một record vào source topic.
2. Cho listener thất bại ở các lần đầu và thành công ở một attempt sau.
3. Xác nhận record xuất hiện trên retry topic theo cấu hình và cuối cùng được xử lý thành công.
4. Với trường hợp luôn thất bại, xác nhận tổng số attempts đúng với `attempts` và record cuối cùng đến DLT.
5. Kiểm tra key, payload, correlation ID, original topic/partition/offset và các header cần thiết được giữ qua các lần chuyển topic.
6. Xác nhận DLT handler hoặc DLT consumer nhận đúng record và không tạo side effect nghiệp vụ ngoài dự kiến.

Có thể dùng `@DltHandler` để kiểm tra điểm đến cuối, hoặc một test consumer riêng để đọc DLT. Nếu DLT handler ghi vào database hoặc gọi service khác, kiểm tra side effect bằng test double hoặc dữ liệu kiểm thử có thể đối soát.

### Kiểm tra thời gian backoff

Backoff là thời gian chờ tối thiểu theo chính sách; thời điểm thực tế có thể muộn hơn do scheduling, broker và tải. Test nên xác nhận record không xuất hiện trước một giới hạn hợp lý nếu điều đó quan trọng, rồi chờ record xuất hiện trong timeout đủ rộng. Tránh yêu cầu chính xác rằng lần thử phải xảy ra ở mili giây thứ N.

Với exponential backoff, kiểm tra các mức delay đã cấu hình bằng một test có thời gian đủ rộng và quan sát timestamp/header nếu hệ thống lưu lại. Không để test suite phải chờ nhiều phút chỉ để xác minh một công thức; dùng cấu hình delay ngắn riêng cho test và giữ nguyên logic backoff.

## 9. Kiểm thử offset, partition và ordering

Retry không chỉ là đếm số lần listener được gọi. Nó ảnh hưởng đến thời điểm commit offset và thứ tự xử lý.

### Offset và recovery

Kiểm tra các tình huống:

- Record được xử lý thành công sau retry: offset tiến theo ack mode và container configuration.
- Record được recover sang DLT: recovery được xác nhận theo cấu hình; consumer không lặp vô hạn cùng record.
- Publish DLT thất bại: error handler phản ứng theo cấu hình, và không đánh dấu record đã phục hồi nếu việc gửi chưa được xác nhận theo yêu cầu độ tin cậy.
- Ứng dụng restart trong khi đang retry: hành vi redelivery và xử lý lặp có thể xảy ra; logic nghiệp vụ phải an toàn khi nhận lại record.

Không giả định mọi cấu hình Spring Kafka đều commit offset theo cùng một cách. Ack mode, record/batch listener, transaction, error handler và phiên bản thư viện có thể làm thay đổi chi tiết. Viết test theo hành vi mà ứng dụng cam kết, sau đó xác nhận offset bằng consumer group hoặc một consumer kiểm tra độc lập.

### Partition và key

Nếu recoverer gửi DLT vào cùng partition number với source record, topic đích cần có đủ partition tương ứng. Test nhiều partition để xác nhận destination resolver không tạo partition ngoài phạm vi. Nếu ứng dụng chủ ý phân phối lại theo key, kiểm tra partition mapping mới và tác động đến ordering.

Không dùng một partition duy nhất để kết luận hệ thống nhiều partition hoạt động đúng. Một test đơn giản với một partition có thể kiểm tra số lần retry; một test riêng nên xác minh partition mapping, key và metadata nguồn.

### Ordering

Blocking retry có thể khiến record lỗi giữ luồng xử lý của partition trong lúc chờ retry. Non-blocking retry đưa record sang topic khác, do đó record tiếp theo ở source topic có thể được xử lý trước record đang chờ retry. Nếu nghiệp vụ yêu cầu thứ tự theo key, test phải gửi nhiều record cùng key và xác nhận hành vi phù hợp với thiết kế.

Nếu ordering không được bảo đảm bởi kiến trúc retry, ứng dụng cần version/event sequence, state transition guard hoặc cơ chế khác để từ chối sự kiện đến sai thứ tự. Không suy ra ordering chỉ từ việc record dùng cùng Kafka key.

## 10. Kiểm thử idempotency và side effect

Kafka consumer thường có thể nhận lại một record, ví dụ khi listener đã ghi dữ liệu ra hệ thống ngoài nhưng process dừng trước khi offset được commit. Retry trong cùng process cũng có thể gọi lại listener sau khi một phần logic đã thực hiện xong rồi mới ném exception.

Một test idempotency nên mô phỏng tình huống:

1. Listener nhận event và thực hiện side effect đầu tiên.
2. Một lỗi xảy ra sau side effect nhưng trước khi xử lý hoàn tất.
3. Consumer retry hoặc nhận lại record sau restart.
4. Hệ thống bảo đảm cùng event không tạo side effect trùng, hoặc có cơ chế bù trừ được định nghĩa.

Các kỹ thuật thường dùng gồm idempotency key, unique constraint ở database, inbox/deduplication table, transaction nghiệp vụ phù hợp hoặc kiểm tra event version. Test phải xác nhận kết quả nghiệp vụ cuối cùng, không chỉ xác nhận số lần listener được gọi.

Ví dụ assertion nghiệp vụ có thể là một order chỉ có một lần chuyển trạng thái dù listener được gọi nhiều lần. Nếu mỗi lần thử được phép tạo audit entry, test cần phân biệt log lần thử với giao dịch nghiệp vụ đã commit.

## 11. Kiểm thử DLT và metadata

Khi record hết retry, DLT là bằng chứng cho thấy hệ thống giữ lại message để điều tra hoặc xử lý sau. Test nên xác nhận:

- Record được gửi đến đúng DLT tương ứng source topic/listener.
- Key và payload còn nguyên vẹn, trừ khi ứng dụng có transformation được định nghĩa.
- Original topic, partition, offset, timestamp và consumer group được giữ trong header nếu recoverer hỗ trợ.
- Exception class, exception message và stack trace được lưu theo cấu hình và chính sách bảo mật.
- Record không bị gửi nhầm sang DLT của listener khác.
- DLT consumer hoặc `@DltHandler` nhận được record và xử lý theo hợp đồng.

Không ghi nguyên payload nhạy cảm hoặc stack trace có chứa secret vào log test report được chia sẻ rộng. Nếu header chứa exception message hoặc stack trace, kiểm tra rằng dữ liệu nhạy cảm được loại bỏ theo yêu cầu của hệ thống.

Nếu ứng dụng dùng `DeadLetterPublishingRecoverer` tùy chỉnh, test cả resolver chọn topic/partition và cách xử lý kết quả publish. Một test chỉ xác nhận method recoverer được gọi không chứng minh record thực sự tồn tại trong DLT.

## 12. Kiểm thử lỗi khi publish DLT

Đường ghi DLT cũng có thể thất bại vì topic thiếu, ACL, broker, timeout hoặc producer lỗi. Đây là trường hợp quan trọng vì consumer có thể không được phép coi record là đã phục hồi nếu message chưa được lưu an toàn.

Các tình huống nên có test riêng:

- Recoverer gửi thành công: record xuất hiện trong DLT và luồng consumer tiếp tục theo chính sách.
- Producer gửi DLT thất bại: lỗi được quan sát và xử lý theo cấu hình error handler/container.
- DLT topic thiếu hoặc partition không hợp lệ: test xác nhận lỗi được phát hiện, không âm thầm bỏ record.
- Producer callback/send result báo lỗi: xác nhận cơ chế xác nhận gửi của recoverer phù hợp với yêu cầu của ứng dụng.

Không nên mô phỏng broker failure bằng cách tắt broker dùng chung trong test suite. Có thể dùng producer test double để kiểm tra nhánh lỗi của code tùy chỉnh, hoặc một môi trường broker cô lập để kiểm tra lỗi publish thực tế. Cần phân biệt rõ test unit của nhánh lỗi và integration test của hành vi Kafka.

## 13. Test deserialization và lỗi trước listener

Không phải mọi lỗi đều phát sinh bên trong method `@KafkaListener`. Deserializer có thể lỗi trước khi listener nhận được payload. Vì vậy, counter trong listener không đủ để kiểm tra retry của lỗi deserialize.

Nếu ứng dụng dùng `ErrorHandlingDeserializer`, test nên gửi payload không hợp lệ hoặc schema không tương thích, rồi xác nhận error handler/recoverer nhận được record theo cấu hình. Kiểm tra header chứa exception và thông tin raw data có đúng chính sách hay không. Với JSON, test các trường hợp JSON hỏng, field bắt buộc thiếu, type sai và schema version không hỗ trợ.

Đối với lỗi deserialize, cần xác nhận cụ thể cách framework chuyển exception và raw record đến error handler trong phiên bản đang dùng. Không giả định listener sẽ được gọi một lần cho mỗi lần deserialize thất bại.

## 14. Làm cho test ổn định và dễ chẩn đoán

### Tránh race condition

- Tạo consumer group riêng cho mỗi test hoặc mỗi test class.
- Dùng topic riêng hoặc bảo đảm test không chạy song song trên cùng topic và group.
- Tạo test consumer và subscribe DLT trước khi gửi record.
- Chờ điều kiện cụ thể bằng Awaitility, `CountDownLatch` hoặc polling có timeout.
- Dùng counter/map thread-safe khi listener chạy trên thread khác.
- Reset state trước mỗi test; không chia sẻ counter giữa test đang chạy song song.
- Đặt timeout hữu hạn để test thất bại rõ ràng thay vì treo.

### Tránh phụ thuộc thời gian không cần thiết

Không dùng `Thread.sleep` dài để đoán consumer đã retry xong. Nếu cần xác minh backoff, dùng timestamp ghi nhận attempt hoặc quan sát thời điểm record xuất hiện. Chấp nhận sai số scheduling hợp lý và không assert mili giây tuyệt đối.

### Cô lập dữ liệu

Mỗi test nên dùng key duy nhất và payload có thể nhận diện. Nếu test chạy trên broker dùng chung, thêm run ID vào topic/group hoặc resource name, đồng thời có quy trình dọn tài nguyên an toàn. Không xóa topic hoặc group mà test khác hoặc service khác đang dùng.

### Thu thập bằng chứng khi test lỗi

Khi test timeout, ghi lại:

- Listener container ID và trạng thái running.
- Consumer group, member, partition assignment và lag.
- Số lần listener đã được gọi theo key.
- Topic source, retry và DLT có tồn tại hay không.
- Producer send result và exception cuối cùng.
- Các header của record đã được nhận.

Thông tin này giúp phân biệt test chưa gửi được record, listener chưa được assign partition, retry chưa hết thời gian backoff hay recoverer không gửi được DLT.

## 15. Ma trận kịch bản kiểm thử đề xuất

| Nhóm | Kịch bản | Assertion chính |
|---|---|---|
| Retry cơ bản | Thất bại một lần rồi thành công | Listener được gọi lại; record chỉ hoàn tất sau lần thành công |
| Giới hạn retry | Luôn thất bại | Số lần gọi khớp chính sách; recovery xảy ra sau attempt cuối |
| Phân loại exception | Lỗi không retry | Không có retry không cần thiết; record đi theo nhánh recovery đã định nghĩa |
| Backoff | Fixed hoặc exponential | Thứ tự và khoảng chờ phù hợp cấu hình trong sai số cho phép |
| DLT | Hết retry | Record xuất hiện đúng DLT, giữ key/value và metadata cần thiết |
| DLT publish failure | Broker/topic/producer trả lỗi | Không âm thầm coi record đã phục hồi; lỗi được quan sát |
| Tiếp tục xử lý | Record A lỗi, record B hợp lệ | Record B được xử lý theo semantics của listener và partition |
| Offset | Retry/recovery/restart | Offset và redelivery phù hợp ack mode, transaction và error handler |
| Partition | Nhiều partition | Định tuyến DLT và partition mapping đúng |
| Ordering | Nhiều record cùng key | Hành vi thứ tự đúng hợp đồng nghiệp vụ |
| Idempotency | Side effect xảy ra trước exception | Retry không tạo side effect nghiệp vụ trùng |
| Non-blocking | Qua retry topic | Topic, attempts, delay và DLT đúng cấu hình |
| Deserialize | Payload không hợp lệ | Lỗi trước listener được xử lý theo cấu hình deserializer/error handler |
| Restart | Consumer dừng giữa retry | Redelivery và kết quả nghiệp vụ an toàn, có thể đối soát |

Không phải dự án nào cũng cần mọi kịch bản trong một test suite. Chọn các trường hợp theo cơ chế retry, semantics dữ liệu, yêu cầu ordering, dependency và mức độ quan trọng của luồng nghiệp vụ.

## 16. Chạy test và xử lý lỗi thường gặp

Với Gradle, chạy một test class cụ thể:

```bash
./gradlew test --tests "com.example.kafka.BlockingRetryIntegrationTest"
```

Trên Windows có thể dùng `gradlew.bat` thay cho `./gradlew`. Nếu dự án dùng source set hoặc task integration test riêng, dùng task đã được cấu hình trong build của dự án.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Test producer gửi thành công nhưng counter listener bằng 0 | Listener không start, topic/group sai, chưa được assign partition | Container registry, bootstrap server, topic, group và log consumer |
| Counter cao hơn dự kiến | Test gửi trùng, listener nhận record cũ, nhiều instance dùng chung state hoặc cấu hình retry khác dự kiến | Key duy nhất, group riêng, offset reset, số retry và concurrency |
| DLT không có record | Recoverer chưa được gọi, publish thất bại, topic/partition sai hoặc test consumer subscribe quá muộn | Exception cuối, producer send result, topic metadata và thời điểm subscribe |
| Test lúc pass lúc fail | Race condition, timeout quá ngắn, state dùng chung hoặc phụ thuộc sleep | Awaitility, consumer group riêng, timeout phù hợp và state thread-safe |
| DLT record có partition không hợp lệ | Topic đích ít partition hơn source hoặc resolver chọn partition sai | Destination resolver và partition count của topic |
| Non-blocking retry không đến DLT | Sai attempts, retry topic chưa được tạo, listener retry topic không chạy hoặc exception được phân loại khác | Topic topology, retry configuration, group và exception classifier |
| Record bị xử lý trùng | Side effect không idempotent, offset chưa commit hoặc replay/redelivery | Idempotency key, transaction, ack mode và luồng recovery |

Nếu test lỗi, không tăng timeout hoặc retry count ngay lập tức để làm test xanh. Trước tiên xác định consumer có nhận record không, listener đã được gọi bao nhiêu lần và recoverer có publish thành công không.

## 17. Tiêu chí hoàn tất kiểm thử consumer retry

Một thay đổi về retry chỉ nên được coi là đã kiểm chứng khi các assertion liên quan đến hợp đồng của ứng dụng đều đạt:

- Số lần thử và cách tính attempt đúng với cơ chế blocking hoặc non-blocking đang dùng.
- Exception retryable và non-retryable được phân loại đúng.
- Record thành công sau retry không bị chuyển nhầm sang DLT.
- Record hết số lần thử được recover hoặc chuyển đến đúng DLT.
- Metadata nguồn và thông tin lỗi cần thiết được giữ theo cấu hình.
- Consumer tiếp tục hoạt động và xử lý record tiếp theo theo semantics đã định nghĩa.
- Offset, partition, ordering và idempotency được kiểm tra ở mức phù hợp với nghiệp vụ.
- Test bất đồng bộ có timeout rõ ràng, state an toàn giữa các thread và không phụ thuộc broker dùng chung.
- Các giới hạn do phiên bản Spring Kafka hoặc broker test được ghi nhận để người bảo trì hiểu phạm vi bằng chứng.

## 18. Checklist cho pull request

- [ ] Test xác định rõ đang kiểm tra blocking retry hay non-blocking retry.
- [ ] Số lần thử được tính đúng, gồm cả lần đầu và số lần retry thêm nếu áp dụng.
- [ ] Có trường hợp retry thành công và trường hợp hết retry.
- [ ] Có kiểm tra exception không retry nếu ứng dụng có phân loại exception.
- [ ] Có xác nhận record thật sự xuất hiện trong DLT, không chỉ xác nhận recoverer được gọi.
- [ ] Có kiểm tra key, payload, partition và header quan trọng.
- [ ] Có đánh giá offset, ordering và idempotency theo yêu cầu nghiệp vụ.
- [ ] Test dùng topic/group cô lập, chờ bất đồng bộ có timeout và tránh sleep cố định.
- [ ] Cấu hình test tương thích với phiên bản Spring Kafka/Kafka của dự án.
- [ ] Kết quả test và các giới hạn môi trường được ghi rõ trong pull request.
