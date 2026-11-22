# Mục tiêu của kiểm thử messaging

Ứng dụng Spring Kafka giao tiếp qua các luồng bất đồng bộ. Producer có thể gửi thành công nhưng consumer xử lý sau đó; listener có thể retry, commit offset, chuyển record sang dead-letter topic hoặc tham gia transaction. Vì vậy, mục tiêu kiểm thử messaging không chỉ là xác nhận một hàm Java được gọi, mà là chứng minh **record được tạo đúng, truyền qua Kafka đúng hợp đồng, được consumer xử lý theo delivery semantics mong muốn và hệ thống phục hồi đúng khi có lỗi**.

Một bộ kiểm thử tốt giúp trả lời các câu hỏi: producer có serialize đúng không, listener có nhận đúng payload và metadata không, offset có tiến đúng thời điểm không, retry có giới hạn không, record lỗi có vào DLT không, transaction có commit/rollback nguyên tử không và ứng dụng có chịu được duplicate hoặc restart không.

## 1. Vì sao messaging cần kiểm thử riêng?

Một lời gọi hàm đồng bộ thường có kết quả ngay trong cùng call stack. Kafka hoạt động khác: producer gửi record qua mạng, broker lưu record, consumer poll theo partition, listener xử lý trên thread riêng và offset được commit theo cấu hình container.

```text
Producer application
      |
      | serialize + send
      v
Kafka broker / topic / partition
      |
      | consumer poll
      v
Spring Kafka listener container
      |
      | deserialize + convert
      v
@KafkaListener
      |
      | business processing
      v
Database / downstream service
      |
      v
Acknowledgment / offset commit
```

Lỗi có thể xảy ra ở từng ranh giới: serialize, network, broker, deserialize, listener, database, acknowledgement hoặc commit. Unit test cho business service không chứng minh được các ranh giới này hoạt động cùng nhau.

Kiểm thử messaging cần bao phủ ít nhất bốn loại hành vi:

- **Correctness:** payload, key, headers, topic và partition đúng hợp đồng.
- **Delivery:** record được xử lý theo at-most-once, at-least-once hoặc transactional semantics đã chọn.
- **Failure handling:** retry, recovery, DLT và redelivery hoạt động đúng.
- **Operational behavior:** concurrency, ordering, rebalance, pause, timeout và shutdown không tạo trạng thái sai.

## 2. Mục tiêu kiểm thử theo từng thành phần

| Thành phần | Điều cần chứng minh |
| --- | --- |
| Producer/application service | Tạo đúng event, key, topic và headers; xử lý send failure đúng |
| Serializer | Object được chuyển thành wire bytes đúng contract |
| Deserializer/converter | Bytes được chuyển thành payload/headers đúng kiểu |
| Kafka broker/topic | Partitioning, retention, compaction và cấu hình cần thiết phù hợp |
| Consumer/listener container | Poll, assignment, concurrency và listener invocation đúng |
| Listener/business service | Xử lý đúng dữ liệu, idempotent khi redelivery |
| Offset/acknowledgment | Chỉ tiến offset theo thời điểm xử lý đã định |
| Error handler/retry | Retry đúng số lần, đúng backoff và đúng loại exception |
| DLT/recovery | Record lỗi được chuyển đi và có đủ metadata để điều tra |
| Transaction | Output và input offset cùng commit hoặc cùng abort |
| Schema/contract | Producer và consumer tương thích qua các phiên bản dữ liệu |

Không phải mọi bài test đều cần kiểm tra tất cả các mục. Hãy chọn tầng kiểm thử phù hợp với câu hỏi cần trả lời.

## 3. Phân tầng kiểm thử

Một chiến lược thực tế thường có ba tầng chính:

| Tầng | Công cụ thường dùng | Phạm vi |
| --- | --- | --- |
| Unit test | JUnit, Mockito, AssertJ | Business logic, mapping, validation, exception classification |
| Integration test | `spring-kafka-test`, Embedded Kafka, Testcontainers | Producer/consumer, serializer, listener container, offset, retry, DLT, transaction |
| Contract/system test | Schema Registry compatibility check, broker gần production, môi trường staging | Wire contract, ACL/TLS, nhiều service, replay và vận hành end-to-end |

Unit test chạy nhanh và cô lập, nhưng không mô phỏng đầy đủ Kafka protocol. Integration test kiểm tra kết nối giữa Spring Kafka và broker. Contract/system test xác minh các service độc lập thực sự hiểu cùng dữ liệu và cấu hình production.

Không cần khởi động broker cho mọi test. Business rule nên được kiểm tra bằng unit test; các hành vi phụ thuộc Kafka cần integration test có broker thật hoặc broker test tương thích.

## 4. Kiểm thử business logic độc lập Kafka

Tách logic nghiệp vụ khỏi listener giúp test dễ và nhanh. Listener chỉ nhận payload, gọi service và để exception/acknowledgment theo chính sách container.

Ví dụ service:

```java
public class OrderProjectionService {

    private final OrderRepository repository;

    public OrderProjectionService(OrderRepository repository) {
        this.repository = repository;
    }

    public void process(OrderCreatedEvent event) {
        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        repository.save(new OrderProjection(
                event.orderId(), event.total(), event.currency()));
    }
}
```

Unit test tập trung vào quy tắc nghiệp vụ:

```java
@ExtendWith(MockitoExtension.class)
class OrderProjectionServiceTest {

    @Mock
    OrderRepository repository;

    @Test
    void savesProjectionFromEvent() {
        var service = new OrderProjectionService(repository);
        var event = new OrderCreatedEvent(
                "evt-1", "ord-42", 125000L, "VND");

        service.process(event);

        verify(repository).save(argThat(projection ->
                projection.orderId().equals("ord-42")
                        && projection.total() == 125000L
                        && projection.currency().equals("VND")));
    }

    @Test
    void rejectsMissingOrderId() {
        var service = new OrderProjectionService(repository);
        var event = new OrderCreatedEvent("evt-2", " ", 100L, "VND");

        assertThrows(IllegalArgumentException.class,
                () -> service.process(event));

        verifyNoInteractions(repository);
    }
}
```

Các test này không cần Kafka broker. Chúng chứng minh mapping và business rule, còn việc listener có deserialize đúng và gọi service hay không sẽ được kiểm tra ở integration test.

## 5. Kiểm thử producer

Producer test cần xác minh ứng dụng gửi đúng:

- Topic đích.
- Key và chiến lược partitioning.
- Payload sau serialization.
- Headers nghiệp vụ/kỹ thuật.
- Callback hoặc future khi gửi thành công/thất bại.
- Hành vi khi broker không khả dụng hoặc serializer ném lỗi.

Với `KafkaTemplate`, send trả về `CompletableFuture<SendResult<K,V>>` ở các phiên bản Spring Kafka hiện đại. Có thể chờ kết quả trong test với timeout:

```java
@Test
void publishesOrderEvent() throws Exception {
    var event = new OrderCreatedEvent("evt-1", "ord-42", 125000L, "VND");

    var result = kafkaTemplate
            .send("orders.created", "ord-42", event)
            .get(10, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic())
            .isEqualTo("orders.created");
    assertThat(result.getRecordMetadata().partition())
            .isGreaterThanOrEqualTo(0);
}
```

Ví dụ này giả định producer factory đã cấu hình serializer phù hợp với `OrderCreatedEvent`. Nó chứng minh broker xác nhận record và trả metadata; để xác minh payload thực tế, cần consume record bằng consumer có deserializer tương ứng.

Không kiểm tra chỉ bằng việc `KafkaTemplate.send()` không ném exception ngay lập tức. Gửi là bất đồng bộ; lỗi có thể xuất hiện sau đó trong future hoặc callback.

## 6. Kiểm thử serializer và deserializer

Serialization là một phần của wire contract. Unit test serializer/deserializer có thể xác minh:

- DTO được chuyển thành bytes đúng format.
- Consumer tạo lại đúng giá trị và kiểu dữ liệu.
- Null, field optional, default, enum và timestamp được xử lý đúng.
- Payload cũ vẫn đọc được theo compatibility policy.
- Payload sai schema hoặc bytes hỏng tạo lỗi có thể dự đoán.

Với JSON, kiểm tra tên field, kiểu số, format thời gian và chính sách unknown properties. Với Avro/Protobuf, kiểm tra generated class, schema ID, default, field number và schema resolution. Nếu dùng Schema Registry, cần thêm test đăng ký/compatibility ở CI hoặc môi trường registry test.

Một test serialize rồi deserialize cùng một phiên bản chỉ chứng minh hai phía khớp nhau. Nó chưa chứng minh consumer mới đọc được payload từ producer cũ. Hãy giữ fixture bytes/payload đại diện cho các schema version còn được hỗ trợ và chạy compatibility tests với chúng.

## 7. Kiểm thử listener bằng Embedded Kafka

`spring-kafka-test` cung cấp `@EmbeddedKafka` để chạy broker Kafka trong cùng tiến trình test. Đây là lựa chọn tiện cho integration test Spring Kafka mà không cần cài broker riêng.

Dependency test thường có dạng:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Ví dụ test listener trong Spring context:

```java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest
@EmbeddedKafka(
        partitions = 1,
        topics = "orders.created",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderListenerIntegrationTest {

    @Autowired
    KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    @Autowired
    OrderProjectionRepository repository;

    @Test
    void consumesOrderCreatedEvent() throws Exception {
        var event = new OrderCreatedEvent(
                "evt-test-1", "ord-test-42", 125000L, "VND");

        kafkaTemplate.send("orders.created", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() ->
                assertThat(repository.findByOrderId("ord-test-42"))
                        .isPresent());
    }
}
```

Ví dụ cần có Awaitility và model/repository tương ứng trong test project. `@EmbeddedKafka` đặt bootstrap server vào property được chỉ định để Spring Boot producer/consumer kết nối tới broker test. Hãy dùng group ID riêng cho từng test context và dọn dữ liệu repository giữa các test để tránh phụ thuộc thứ tự chạy.

## 8. Chờ kết quả bất đồng bộ đúng cách

Kafka listener chạy trên consumer thread riêng. Khi test gửi record, việc `send().get()` chỉ xác nhận producer nhận acknowledgement; nó không có nghĩa listener đã xử lý xong.

Để chờ listener, dùng cơ chế đồng bộ có timeout:

```java
await().atMost(10, TimeUnit.SECONDS).untilAsserted(() ->
        assertThat(testProbe.receivedEvents())
                .extracting(OrderCreatedEvent::orderId)
                .contains("ord-42"));
```

Hoặc dùng `CountDownLatch`/`BlockingQueue` trong test probe. Tránh `Thread.sleep(500)` rồi assert ngay vì thời gian poll, broker scheduling, CI load và rebalance có thể thay đổi.

Timeout cần đủ để phát hiện lỗi nhưng không quá dài khiến suite chậm. Khi timeout xảy ra, log thêm topic, group ID, listener assignment và consumer lag để việc chẩn đoán rõ hơn.

## 9. Kiểm thử key, partition, ordering và consumer group

Các test partitioning nên gửi nhiều record với key khác nhau rồi xác minh metadata partition. Nếu nghiệp vụ yêu cầu event cùng aggregate đi cùng partition, gửi nhiều event có cùng key và xác minh chúng được ghi vào cùng partition.

Ordering chỉ được bảo đảm trong một partition. Test nên xác minh thứ tự offset trong partition thay vì giả định có thứ tự tổng thể giữa nhiều partition.

Consumer group cần test các hành vi:

- Hai consumer cùng group chia partition và không cùng xử lý một partition tại một thời điểm.
- Hai group ID khác nhau nhận độc lập cùng một record.
- Tăng concurrency không tạo thêm mức song song hữu ích vượt số partition được gán.
- Restart consumer hoặc thêm instance gây rebalance nhưng record không bị bỏ sót theo delivery semantics.

Để test ổn định, tạo topic với partition count xác định và chờ container assignment trước khi gửi record. Không phụ thuộc partition mặc định do broker auto-create.

## 10. Kiểm thử offset và acknowledgment

Offset là một phần của correctness. Với `AckMode.RECORD`, `BATCH`, `MANUAL` hoặc `MANUAL_IMMEDIATE`, thời điểm commit khác nhau. Test cần chứng minh offset chỉ tiến sau điểm xử lý mà ứng dụng đã quy định.

Các kịch bản quan trọng:

- Listener thành công và offset được commit.
- Listener ném exception trước khi acknowledge; record được retry/redeliver.
- Manual ack chỉ được gọi sau khi side effect hoàn tất.
- Ứng dụng dừng giữa business commit và Kafka offset commit; record có thể được giao lại.
- `asyncAcks` có acknowledgement đến không theo thứ tự và container chờ offset gap.
- Batch listener xử lý một phần rồi thất bại; kiểm tra phần nào được retry/recover.

Không nên chỉ assert số lần listener được gọi. Hãy kiểm tra trạng thái cuối của database/output topic và offset consumer group khi test yêu cầu semantics commit cụ thể.

## 11. Kiểm thử retry và error handler

Retry test nên xác minh số lần gọi, khoảng backoff theo mức phù hợp, exception classification và kết quả cuối.

Ví dụ dùng service giả lập thất bại hai lần rồi thành công:

```java
@Test
void retriesTransientFailureAndEventuallyProcesses() {
    doThrow(new TransientDataAccessException("temporary") {})
            .doThrow(new TransientDataAccessException("temporary") {})
            .doNothing()
            .when(orderService).process(any());

    // Gửi event tới broker test và chờ side effect thành công.

    await().atMost(10, TimeUnit.SECONDS).untilAsserted(() ->
            verify(orderService, times(3)).process(any()));
}
```

Đây là phần minh họa hành vi cho method `void`; cần cấu hình `DefaultErrorHandler` với số lần retry/backoff nhỏ cho test và đăng ký mock service vào Spring test context (dùng `@MockitoBean` hoặc cơ chế mock bean tương ứng với phiên bản Spring Boot/Spring Framework). Không dùng backoff production dài trong test.

Kiểm tra thêm:

- Retryable exception được thử lại.
- Non-retryable exception đi thẳng tới recovery theo classification.
- Hết retry thì recoverer được gọi.
- Lỗi trong recoverer không làm offset được commit như thể recovery thành công.
- `ackAfterHandle`, `commitRecovered` và AckMode tương tác đúng cấu hình.
- Lỗi deserialize xảy ra trước listener được xử lý qua `ErrorHandlingDeserializer`.

## 12. Kiểm thử Dead Letter Topic

DLT integration test nên gửi một record chắc chắn thất bại, chờ record xuất hiện trên DLT và xác minh payload cùng metadata:

- Payload hoặc raw bytes được giữ đúng theo cấu hình recoverer.
- Header gốc như topic, partition, offset được ghi lại.
- Exception class/message và delivery attempt có mặt theo chính sách.
- DLT partition đủ để nhận partition gốc nếu resolver giữ partition index.
- Offset input chỉ tiến sau khi recovery publish thành công theo cấu hình.
- DLT consumer có thể đọc và điều tra record.

Không chỉ xác minh listener không còn nhận record. Điều đó có thể xảy ra vì container dừng, record bị bỏ qua hoặc offset commit sai. Hãy consume DLT và kiểm tra nội dung thực tế.

## 13. Kiểm thử non-blocking retry topics

Với `@RetryableTopic`, test cần bao phủ topology main/retry/DLT:

1. Gửi record tới main topic.
2. Cho listener thất bại lần đầu và xác nhận record được publish sang retry topic.
3. Xác minh main listener có thể tiếp tục xử lý record phía sau trong khi record lỗi đang chờ.
4. Chờ retry listener nhận record theo backoff và xác nhận thành công hoặc đi tiếp retry stage.
5. Cho một record thất bại hết attempts và xác minh nó vào DLT.
6. Xác minh key, headers và partition mapping theo cấu hình.

Không assert thời gian retry chính xác tuyệt đối. Backoff là thời gian chờ tối thiểu theo cơ chế; poll interval, scheduling và consumer lag có thể làm record được xử lý muộn hơn.

Non-blocking retry không hỗ trợ batch listener và không kết hợp với container transaction. Test cần phản ánh đúng kiến trúc đã chọn thay vì ghép các chế độ không tương thích.

## 14. Kiểm thử Kafka transaction và Exactly-once

Transaction test phải dùng broker hỗ trợ transaction và consumer `read_committed` để xác minh visibility. Có hai đường cơ bản:

**Commit:** listener đọc input, gửi output bằng `KafkaTemplate` cùng `ProducerFactory`, hoàn tất thành công; output và offset input cùng commit.

**Abort:** listener gửi output rồi ném exception; transaction rollback; consumer `read_committed` không nhìn thấy output đã abort và input record được retry theo `AfterRollbackProcessor`.

Ngoài ra, test producer fencing với transactional ID, transaction timeout, consumer restart và nhiều instance có prefix riêng nếu đó là rủi ro production cần kiểm soát.

Không dùng `read_uncommitted` để xác minh EOS visibility vì consumer đó có thể nhìn thấy record thuộc transaction chưa commit hoặc đã abort.

## 15. Kiểm thử schema evolution và contract

Hãy lưu fixture đại diện cho schema version cũ và kiểm tra consumer hiện tại có đọc được chúng không. Khi schema thay đổi:

- Validate payload mới theo schema.
- Chạy compatibility check với subject/policy của Registry.
- Kiểm tra producer serialize đúng schema ID và wire format.
- Kiểm tra consumer deserialize dữ liệu cũ và mới.
- Kiểm tra field optional, null, default, enum mới và timestamp.
- Replay fixture hoặc dữ liệu lịch sử đại diện.

Một producer và consumer cùng dùng một DTO mới có thể pass integration test nhưng vẫn phá vỡ các service cũ. Contract testing phải bao gồm các phiên bản độc lập còn được hỗ trợ.

## 16. Embedded Kafka hay Testcontainers?

| Tiêu chí | Embedded Kafka | Testcontainers Kafka |
| --- | --- | --- |
| Cách chạy | Broker test trong tiến trình test | Broker chạy trong container |
| Tốc độ khởi động | Thường nhanh cho test Spring Kafka | Thường chậm hơn do khởi tạo container |
| Môi trường | Tiện cho listener, producer, offset và retry test | Gần môi trường broker triển khai hơn khi chọn đúng image/config |
| Cấu hình broker | Có thể cấu hình nhưng thường tập trung test nhanh | Có thể kiểm thử image/version và broker config cụ thể |
| Phụ thuộc môi trường | Không cần Docker cho embedded broker | Cần Docker runtime khả dụng |
| Use case | Integration test thường xuyên trong suite | Test tương thích broker, transaction/security/config gần production |

Chọn công cụ theo mục tiêu. Embedded Kafka phù hợp cho phần lớn integration test Spring Kafka. Testcontainers hữu ích khi cần kiểm tra phiên bản Kafka broker cụ thể, listener SSL/SASL, transaction settings hoặc cấu hình gần production.

Không dùng mock `KafkaTemplate` để chứng minh Kafka protocol, partition assignment, offset commit hoặc transaction. Mock chỉ phù hợp để kiểm tra service gọi đúng API với tham số mong muốn.

## 17. Cô lập test và tránh flaky tests

Messaging test dễ flaky nếu nhiều test dùng chung topic, group ID, offset hoặc dữ liệu. Các nguyên tắc:

- Dùng topic và group ID riêng theo test class/run khi cần cô lập.
- Khởi tạo topic với partition count xác định.
- Chờ listener container được assign partition trước khi gửi record.
- Dọn database/test state giữa các test.
- Không dựa vào thứ tự test hoặc offset còn lại từ lần chạy trước.
- Dùng Awaitility, latch hoặc queue với timeout thay vì sleep cố định.
- Đóng producer/consumer/container và giải phóng broker sau test.
- Giữ backoff và timeout nhỏ nhưng đủ để test đúng state transition.
- Không chạy song song các test chia sẻ cùng topic/group nếu không được thiết kế để cô lập.

Nếu test fail ngẫu nhiên, thu thập log group rebalance, partition assignment, consumer lag, offset và trạng thái listener container thay vì chỉ tăng timeout tùy tiện.

## 18. Kiểm thử bảo mật và cấu hình production

Nếu ứng dụng production dùng TLS, mTLS, SASL hoặc ACL, cần có kiểm thử riêng cho cấu hình bảo mật:

- Client xác minh đúng CA và hostname broker.
- Client certificate hợp lệ được chấp nhận khi dùng mTLS.
- Certificate không hợp lệ hoặc hết hạn bị từ chối.
- Producer chỉ ghi được topic được cấp quyền.
- Consumer chỉ đọc topic và group được cấp quyền.
- Transactional ID có quyền phù hợp khi dùng Kafka transaction.
- Secret không xuất hiện trong log hoặc test report.

Không cần chạy toàn bộ security test trong mỗi unit test. Có thể chạy trong integration/security pipeline với broker test được cấu hình SSL/SASL/ACL tương ứng.

## 19. Kiểm thử hiệu năng và tải

Performance test trả lời câu hỏi throughput và latency khi tải tăng, không thay thế correctness test. Các chỉ số cần thu thập:

- Producer send rate, error rate và request latency.
- Consumer records/sec và lag theo partition.
- Listener processing time ở p50/p95/p99.
- Retry rate, DLT rate và thời gian backoff.
- Rebalance count/duration.
- CPU, heap, garbage collection và thread count.
- Database/HTTP pool utilization và downstream latency.
- Transaction duration/abort rate nếu dùng EOS.

Tải test nên dùng phân phối key thực tế để phát hiện hot partition. Tăng concurrency không nhất thiết tăng throughput nếu partition count, CPU hoặc downstream đã là bottleneck.

## 20. Ma trận kiểm thử tham khảo

| Khu vực | Unit | Integration broker | Contract/system |
| --- | :---: | :---: | :---: |
| Business rule và validation | ✓ |  |  |
| Event mapping | ✓ | ✓ |  |
| Serializer/deserializer | ✓ | ✓ | ✓ |
| Topic/key/partition |  | ✓ | ✓ |
| Listener invocation |  | ✓ | ✓ |
| Offset/acknowledgment |  | ✓ | ✓ |
| Retry/backoff/DLT |  | ✓ | ✓ |
| Non-blocking retry topology |  | ✓ | ✓ |
| Kafka transaction/EOS |  | ✓ | ✓ |
| Schema compatibility | ✓ | ✓ | ✓ |
| TLS/SASL/ACL |  | ✓ | ✓ |
| Throughput/latency |  |  | ✓ |
| Multi-service replay |  |  | ✓ |

Ma trận chỉ là gợi ý. Dự án có thể chuyển một số kiểm thử sang tầng khác tùy chi phí và mức độ tin cậy cần đạt.

## 21. Checklist trước khi phát hành

- [ ] Business logic có unit test độc lập Kafka.
- [ ] Producer test xác minh send result và metadata.
- [ ] Serializer/deserializer có test wire format và fixture cũ.
- [ ] Listener integration test chạy với broker test.
- [ ] Test dùng topic, group ID và partition count xác định.
- [ ] Test chờ bất đồng bộ bằng latch/queue/Awaitility có timeout.
- [ ] Offset và manual acknowledgment được xác minh theo AckMode.
- [ ] Retry, exception classification và DLT được kiểm tra.
- [ ] Non-blocking retry được kiểm tra cả retry topics và DLT.
- [ ] Transaction commit/abort được xác minh bằng consumer `read_committed`.
- [ ] Schema compatibility và cross-version fixtures được kiểm tra.
- [ ] TLS/SASL/ACL được kiểm tra trong pipeline phù hợp.
- [ ] Performance test có tải và key distribution đại diện.
- [ ] Log/metric đủ để chẩn đoán flaky test và production incident.

## 22. Kết luận

Mục tiêu của kiểm thử messaging là chứng minh toàn bộ hành vi trao đổi event, từ wire contract đến xử lý, offset, retry, recovery và vận hành khi lỗi. Unit test bảo vệ business logic; integration test với Embedded Kafka hoặc Testcontainers xác minh Spring Kafka tương tác đúng với broker; contract/system test kiểm tra compatibility giữa các service và môi trường triển khai.

Hãy kiểm thử theo ranh giới bất đồng bộ thực tế: chờ future của producer, chờ listener bằng latch/queue/Awaitility, kiểm tra offset và trạng thái cuối thay vì dựa vào sleep hoặc số lần gọi đơn lẻ. Bao phủ các tình huống redelivery, DLT, transaction rollback, schema evolution và security theo mức rủi ro. Một bộ test messaging đáng tin cậy giúp phát hiện lỗi trước khi event bị mất, xử lý trùng hoặc mắc kẹt trong production.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Testing](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring for Apache Kafka — Embedded Kafka Broker](https://docs.spring.io/spring-kafka/reference/testing.html#embedded-kafka)
- [Spring for Apache Kafka — KafkaTestUtils API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/test/utils/KafkaTestUtils.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
