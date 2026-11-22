# Test recover về DLT

## Mục tiêu của bài kiểm thử

Trong Spring Kafka, recover về Dead Letter Topic (DLT) là bước xử lý record sau khi listener thất bại và chính sách retry đã kết thúc, hoặc khi exception được phân loại là không thể retry. Bài kiểm thử cần chứng minh rằng record lỗi được chuyển đến đúng DLT, giữ đủ thông tin để điều tra, và consumer xử lý offset theo đúng cấu hình.

Một kiểm thử chỉ xác nhận listener đã ném exception là chưa đủ. Nó chưa chứng minh recoverer đã publish record thành công. Tương tự, chỉ thấy record trong DLT cũng chưa chứng minh retry đúng số lần, header nguồn được giữ lại, hoặc source offset được xử lý đúng.

Với một luồng non-transactional điển hình, hợp đồng cần kiểm tra gồm:

1. Listener nhận record từ source topic.
2. Error handler thực hiện đúng số lần retry và backoff.
3. Sau khi retry hết, recoverer publish record sang DLT.
4. DLT record giữ key, value và metadata cần thiết của record gốc.
5. Lỗi publish DLT được phát hiện và xử lý theo chính sách đã chọn.
6. Offset source chỉ được xác nhận theo semantics của container và acknowledgement mode đang dùng.

## Phân biệt các lớp kiểm thử

Không nên dùng một bài integration test để kiểm tra mọi chi tiết. Chia kiểm thử theo trách nhiệm sẽ giúp lỗi dễ định vị hơn.

| Lớp kiểm thử | Thành phần cần kiểm tra | Điều có thể chứng minh |
|---|---|---|
| Unit test | Exception classifier, BackOff, destination resolver, custom recoverer | Quy tắc retry và ánh xạ topic/partition đúng |
| Embedded Kafka integration test | Listener, DefaultErrorHandler, DeadLetterPublishingRecoverer, producer và broker | Record thực sự được publish sang DLT và có header mong đợi |
| Testcontainers hoặc broker test environment | Cấu hình broker gần production, replication, ACL, quota | Hành vi khi có nhiều broker và các giới hạn hạ tầng |
| End-to-end test | Consumer group, offset, DLT consumer và quy trình replay | Luồng phục hồi của ứng dụng hoạt động cùng các thành phần liên quan |

Embedded Kafka phù hợp để kiểm tra luồng publish cơ bản trong CI. Một broker nhúng không chứng minh được hành vi ISR, replication factor, broker failover hoặc ACL production. Các thuộc tính đó cần kiểm thử trên broker có cấu hình tương ứng.

## Xác định điều kiện thành công

Trước khi viết test, hãy thống nhất các assertion:

- **Retry count:** tổng số lần listener được gọi bằng số lần giao ban đầu cộng số lần retry được cấu hình, nếu lần nào cũng thất bại.
- **DLT destination:** record đến đúng topic và partition theo destination resolver.
- **Payload:** key và value được giữ nguyên, hoặc được chuyển đổi theo contract đã định.
- **Original metadata:** header chứa topic, partition, offset và timestamp nguồn có giá trị phù hợp.
- **Exception metadata:** header chẩn đoán phản ánh exception gây recover, nếu ứng dụng bật các header này.
- **Send failure:** khi DLT publish thất bại, recoverer không được âm thầm coi record đã được lưu thành công nếu chính sách yêu cầu phát hiện lỗi.
- **Offset:** hành vi commit phù hợp với AckMode, transaction và error handler của container.

Không nên hard-code giả định rằng mọi cấu hình đều commit offset theo cùng một thời điểm. Với record listener, batch listener, manual acknowledgement và transaction, semantics khác nhau. Test phải sử dụng đúng loại listener và acknowledgement mode của ứng dụng.

## Chuẩn bị Embedded Kafka

Thêm dependency kiểm thử Spring Kafka tương thích với phiên bản Spring Kafka của ứng dụng:

~~~gradle
testImplementation("org.springframework.kafka:spring-kafka-test")
~~~

Ví dụ sau dùng Embedded Kafka với source topic và DLT đã được tạo trước. Tạo sẵn DLT trong test giúp tránh việc auto topic creation che giấu lỗi cấu hình topic hoặc partition.

~~~java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders", "orders.DLT"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class DltRecoveryIntegrationTest {
    // Test code shown in the following sections.
}
~~~

Nếu dùng Maven, khai báo artifact spring-kafka-test ở scope test. Giữ phiên bản dependency đồng bộ với Spring Kafka trong ứng dụng; không nâng riêng test library lên một phiên bản khác.

Trong test configuration, gắn CommonErrorHandler vào listener container factory. Ví dụ non-transactional:

~~~java
@Bean
DefaultErrorHandler dltErrorHandler(KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(template);

    // Đưa lỗi gửi DLT trở lại error handler.
    recoverer.setFailIfSendResultIsError(true);

    // Một lần giao ban đầu và tối đa một lần retry.
    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(0L, 1L)
    );
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
kafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory,
        DefaultErrorHandler dltErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(dltErrorHandler);
    return factory;
}
~~~

Trong ví dụ, tham số thứ hai của FixedBackOff là số lần retry sau lần giao ban đầu. Vì vậy, giá trị 1 có nghĩa listener có thể được gọi tối đa hai lần nếu cả hai lần đều thất bại. Kiểm tra lại semantics và API của phiên bản Spring Kafka đang sử dụng trước khi áp dụng.

Nếu ứng dụng đã có listener container factory riêng, cấu hình error handler trên factory đó. Không tạo thêm một factory test có tên khác rồi vô tình để listener dùng factory production mặc định.

## Tạo listener có hành vi xác định

Test listener nên có kết quả xác định theo nội dung record. Tránh phụ thuộc vào dịch vụ bên ngoài hoặc thời gian thực vì những yếu tố đó làm test khó lặp lại.

~~~java
@Component
class TestOrderListener {

    private final AtomicInteger attempts = new AtomicInteger();

    @KafkaListener(
        id = "orders-test-listener",
        topics = "orders",
        groupId = "orders-dlt-test"
    )
    void listen(ConsumerRecord<String, String> record) {
        attempts.incrementAndGet();

        if ("poison".equals(record.value())) {
            throw new IllegalArgumentException("invalid order");
        }
    }

    int attempts() {
        return attempts.get();
    }
}
~~~

Với listener này, record có value là poison luôn thất bại. Nếu BackOff cho phép một lần retry, test mong đợi hai lần gọi trước khi recover. Một record hợp lệ sẽ được xử lý thành công ngay lần đầu.

Trong test thực tế, nên reset bộ đếm giữa các test hoặc tạo context/bean riêng cho từng test. Nếu test chạy song song, dùng topic và group riêng để tránh record hoặc counter của test này ảnh hưởng test khác.

## Kiểm tra record được chuyển sang DLT

Bài test cơ bản gửi một poison record vào source topic, sau đó đọc DLT bằng consumer độc lập. Consumer assertion phải dùng group riêng, không dùng group của listener đang được kiểm thử.

~~~java
@Test
void publishesPoisonRecordToDlt() {
    Consumer<String, String> dltConsumer = createDltConsumer();

    embeddedKafka.consumeFromAnEmbeddedTopic(
        dltConsumer,
        "orders.DLT"
    );

    // Đợi listener container được assign partition trước khi gửi.
    ContainerTestUtils.waitForAssignment(
        listenerContainer,
        1
    );

    kafkaTemplate.send("orders", "order-42", "poison").join();

    ConsumerRecord<String, String> dltRecord =
        KafkaTestUtils.getSingleRecord(
            dltConsumer,
            "orders.DLT",
            Duration.ofSeconds(10)
        );

    assertThat(dltRecord.key()).isEqualTo("order-42");
    assertThat(dltRecord.value()).isEqualTo("poison");
    assertThat(listener.attempts()).isEqualTo(2);

    dltConsumer.close();
}
~~~

Đây là cấu trúc minh họa; các field và helper như listenerContainer, embeddedKafka, kafkaTemplate và listener được inject từ test context. Tạo consumer với deserializer phù hợp và group ID riêng. Với Spring Kafka test utility, có thể tạo consumer properties từ EmbeddedKafkaBroker rồi đặt auto.offset.reset thành earliest trước khi tạo consumer.

Nếu listener container được quản lý bằng KafkaListenerEndpointRegistry, lấy container theo listener ID để truyền vào waitForAssignment. Số partition cần chờ phải khớp số partition được assign cho container trong cấu hình test.

Không dùng Thread.sleep để đoán rằng listener đã xử lý xong. Đọc DLT với timeout hữu hạn hoặc dùng Awaitility để đợi một điều kiện có thể quan sát được.

## Kiểm tra DLT headers

DeadLetterPublishingRecoverer bổ sung metadata để người vận hành biết record đến từ đâu và vì sao nó bị recover. Tùy phiên bản Spring Kafka và cấu hình header, các header thường gặp gồm:

| Header | Nội dung cần xác nhận |
|---|---|
| DLT original topic | Tên source topic |
| DLT original partition | Partition nguồn |
| DLT original offset | Offset của record nguồn |
| DLT original timestamp | Timestamp nguồn khi có |
| DLT exception FQCN | Tên đầy đủ của class exception |
| DLT exception message | Thông điệp exception |
| DLT exception stacktrace | Stack trace nếu cấu hình giữ header này |

Có thể đọc header bằng KafkaHeaders constants của Spring Kafka:

~~~java
Header originalTopic =
    dltRecord.headers().lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC);

assertThat(originalTopic).isNotNull();
assertThat(new String(originalTopic.value(), StandardCharsets.UTF_8))
    .isEqualTo("orders");
~~~

Tên constant và loại header có thể khác theo phiên bản. Dùng constant của phiên bản dự án thay vì tự viết chuỗi header trong production code. Một số metadata được serialize thành byte array, do đó test cần giải mã theo định dạng tương ứng.

Không chỉ kiểm tra header tồn tại. Hãy xác nhận giá trị bằng topic, partition và offset thực tế của record đã gửi. Điều này giúp phát hiện lỗi ánh xạ partition hoặc lỗi header khi record được chuyển qua nhiều tầng.

## Kiểm tra số lần retry

Test retry cần phân biệt số lần listener được gọi với số lần retry. Nếu cấu hình cho phép R lần retry, tổng số lần giao tối đa trong trường hợp luôn thất bại là:

~~~text
Tổng số lần listener nhận record = 1 lần giao ban đầu + R lần retry
~~~

Ví dụ với FixedBackOff(0L, 2L), listener có thể nhận record tối đa ba lần trước khi recover. Backoff bằng 0 giúp test nhanh; test cấu hình production cần kiểm tra thêm thời gian chờ hoặc chiến lược backoff tương ứng.

Một test khác nên chứng minh record được retry thành công sẽ không vào DLT:

~~~java
void succeedsOnSecondAttempt(ConsumerRecord<String, String> record) {
    int currentAttempt = attempts.incrementAndGet();

    if (currentAttempt == 1) {
        throw new IllegalStateException("temporary failure");
    }

    // Lần thứ hai xử lý thành công.
}
~~~

Với kịch bản này, assertion cần xác nhận listener được gọi hai lần và không có record tương ứng trong DLT trong khoảng thời gian kiểm tra hữu hạn. Dùng topic riêng cho test để DLT không chứa record từ test trước.

## Kiểm tra exception không retry

Một số exception biểu thị dữ liệu không hợp lệ và không thể sửa bằng cách thử lại. Có thể cấu hình DefaultErrorHandler để chuyển các exception đó sang DLT ngay:

~~~java
DefaultErrorHandler errorHandler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );

errorHandler.addNotRetryableExceptions(
    IllegalArgumentException.class
);
~~~

Bài test cần chứng minh IllegalArgumentException chỉ tạo một lần gọi listener rồi được recover, trong khi exception tạm thời được retry theo BackOff.

Kiểm tra cả exception gốc và exception bọc. Một số listener hoặc framework có thể bọc lỗi nghiệp vụ trong ListenerExecutionFailedException hoặc cause khác. Cấu hình phân loại phải khớp loại exception mà error handler thực sự nhìn thấy.

## Kiểm tra khi publish DLT thất bại

Đây là trường hợp cần có test riêng. Recover thành công và recover thất bại có ý nghĩa vận hành khác nhau.

Nếu producer không gửi được DLT do timeout, ACL, topic không tồn tại, partition không sẵn sàng hoặc broker lỗi, hệ thống phải biểu hiện lỗi theo chính sách đã chọn. Với DeadLetterPublishingRecoverer, cấu hình failIfSendResultIsError cho phép lỗi send được truyền lại thay vì chỉ ghi log và coi quá trình recover đã hoàn tất.

Có thể kiểm thử ở hai mức:

- **Unit test recoverer:** dùng KafkaOperations giả lập trả về send future thất bại, rồi xác nhận recoverer phát sinh lỗi khi bật failIfSendResultIsError. API future khác nhau giữa các thế hệ Spring Kafka; phiên bản mới dùng CompletableFuture, trong khi các phiên bản cũ có thể dùng ListenableFuture.
- **Integration test broker:** cấu hình DLT producer thiếu quyền ghi hoặc gửi đến destination không hợp lệ trong một broker test có bảo mật, rồi xác nhận lỗi publish xuất hiện trong container/error handler và record không bị coi là đã recover thành công.

Khi viết unit test, kiểm tra cả hai cấu hình failIfSendResultIsError bật và tắt để xác nhận chính sách lỗi. Với integration test, tránh dùng một lỗi ngẫu nhiên của broker làm assertion duy nhất; thu thập exception cụ thể và trạng thái offset để biết lỗi đã đi qua đúng nhánh.

Đừng mặc định rằng listener sẽ được gọi lại ngay khi DLT send thất bại. Hành vi tiếp theo còn phụ thuộc error handler, BackOff, recoverer, AckMode và transaction. Test phải mô tả chính sách thực tế của ứng dụng.

## Kiểm tra topic và partition mapping

Nếu dùng destination resolver mặc định hoặc resolver tùy chỉnh, xác nhận topic và partition đích bằng dữ liệu thực tế. Ví dụ source topic orders có nhiều partition thì DLT cần đủ partition nếu resolver giữ nguyên số partition nguồn.

Một unit test cho resolver có thể kiểm tra:

- Topic đích được tạo đúng hậu tố hoặc quy tắc định tuyến.
- Partition đích khớp partition nguồn khi đó là yêu cầu.
- Record có partition ngoài phạm vi được xử lý theo fallback đã thiết kế.
- Resolver xử lý đúng khi exception hoặc record có metadata đặc biệt.

Không nên chỉ kiểm tra tên topic. Một resolver trả đúng topic nhưng sai partition có thể tạo hotspot, vi phạm thứ tự hoặc gửi đến partition không tồn tại.

## Kiểm tra offset và acknowledgement

Sau khi recoverer gửi DLT thành công, container cần xử lý offset source theo cấu hình. Đây là phần dễ bị kiểm thử sai vì commit behavior phụ thuộc nhiều yếu tố.

Hãy xác định rõ:

- AckMode là RECORD, BATCH, MANUAL hay MANUAL_IMMEDIATE.
- Listener là record listener hay batch listener.
- Consumer có bật auto commit hay không.
- Error handler có commit recovered record theo cấu hình container hay không.
- Luồng có sử dụng Kafka transaction hay không.
- Offset được commit đồng thời với DLT publish hay theo một bước riêng.

Trong test, đọc committed offset của đúng consumer group sau khi container xử lý xong. So sánh với offset của record test và quy tắc commit đã chọn. Dùng AdminClient hoặc consumer group metadata phù hợp với phiên bản Kafka client.

Không dùng consumer assertion đọc DLT làm bằng chứng duy nhất rằng source offset đã commit. Publish DLT và commit source offset là hai kết quả cần kiểm tra riêng, đặc biệt trong luồng non-transactional.

## Kiểm thử khi ứng dụng dùng transaction

Với Kafka transaction, cách recover sau rollback khác với error handler non-transactional. Thường cần cấu hình DefaultAfterRollbackProcessor và recoverer phù hợp. Khi yêu cầu atomicity, việc publish DLT và commit source offset cần nằm trong transaction được thiết kế cho luồng phục hồi.

Bộ test transactional cần chứng minh ít nhất:

1. Listener thất bại và transaction ban đầu rollback.
2. Retry sau rollback diễn ra đúng số lần.
3. Khi hết retry, recoverer publish DLT theo transaction recovery được cấu hình.
4. DLT record chỉ xuất hiện sau khi transaction commit.
5. Source offset được commit theo transaction recovery policy.
6. Khi transaction abort, DLT record không xuất hiện như một kết quả đã commit.

Một test chỉ dùng Embedded Kafka một broker không đủ để chứng minh mọi kịch bản lỗi transaction của cluster production. Với yêu cầu durability cao, bổ sung test trên cluster nhiều broker có replication phù hợp.

## Ma trận test khuyến nghị

| Kịch bản | Kết quả mong đợi |
|---|---|
| Listener thành công ngay | Không có DLT record; listener một lần |
| Listener thất bại rồi thành công | Retry đúng số lần; không có DLT record |
| Listener thất bại đến hết retry | Một DLT record; listener nhận đúng số lần |
| Exception không retry | Chuyển DLT ngay; không chạy retry |
| DLT topic không tồn tại hoặc partition sai | Publish lỗi được phát hiện; record không bị coi là recover thành công |
| DLT producer không có ACL | Lỗi authorization được quan sát; source recovery theo chính sách lỗi |
| Payload không serialize được | Lỗi serializer được phát hiện; không mất metadata cần thiết |
| Payload quá lớn | RecordTooLarge được phát hiện và xử lý theo chính sách |
| Destination resolver tùy chỉnh | Topic và partition đúng quy tắc |
| DLT publish thành công nhưng source offset chưa commit | Test phát hiện trạng thái chưa hoàn tất theo semantics đã chọn |
| Transaction recovery commit | DLT record và offset được commit nhất quán |
| Transaction recovery abort | Không có DLT record đã commit từ transaction bị abort |

Không phải mọi dự án đều cần toàn bộ ma trận trong mỗi lần chạy CI. Giữ các test luồng cơ bản chạy thường xuyên; các bài test broker security, replication và fault injection có thể chạy trong pipeline integration chuyên biệt.

## Giảm flaky test

Test Kafka có tính bất đồng bộ. Một test ổn định cần kiểm soát thời điểm assign partition, thời điểm gửi record và thời điểm đọc DLT.

- Đợi listener container được assign partition trước khi gửi record.
- Dùng group ID riêng cho consumer đọc DLT.
- Đặt auto.offset.reset thành earliest khi consumer test cần đọc record từ đầu topic.
- Tạo topic test riêng hoặc bảo đảm topic được làm sạch giữa các test.
- Dùng timeout hữu hạn và Awaitility/KafkaTestUtils để chờ điều kiện.
- Tránh Thread.sleep cố định vì thời gian xử lý thay đổi giữa máy developer và CI.
- Không chạy song song các test dùng chung topic, group ID hoặc AtomicInteger.
- Đóng consumer và AdminClient sau khi test hoàn thành.
- Đặt timeout test đủ dài để thu được lỗi có ý nghĩa nhưng không làm pipeline treo vô hạn.

Nếu test thỉnh thoảng không tìm thấy DLT record, kiểm tra consumer đã subscribe trước khi gửi chưa, offset reset có đúng không, listener container đã assign chưa và DLT consumer có đang dùng group cũ với offset ở cuối topic hay không.

## Báo cáo lỗi kiểm thử

Khi test recover thất bại, log nên đủ dữ liệu để xác định bước hỏng:

- Source topic, partition, offset và key của record.
- Consumer group và listener ID.
- Số lần listener đã được gọi.
- Exception cuối cùng và chuỗi cause.
- DLT topic/partition do resolver chọn.
- Kết quả producer send và exception của send nếu có.
- AckMode hoặc transaction state liên quan.
- Source committed offset và thời điểm quan sát.

Không log payload nhạy cảm hoặc toàn bộ stack trace vào header DLT nếu chính sách dữ liệu không cho phép. Header exception cần đủ để chẩn đoán nhưng phải có giới hạn kích thước và retention phù hợp.

## Quy trình thực hiện trong CI

Một pipeline thực tế có thể tổ chức theo thứ tự:

1. Chạy unit test cho retry policy, exception classification và destination resolver.
2. Khởi động Embedded Kafka và chạy integration test cho success, retry, recover và header.
3. Chạy test publish failure bằng mock send future hoặc broker test có ACL.
4. Chạy test transactional nếu ứng dụng bật Kafka transaction.
5. Chạy Testcontainers hoặc môi trường Kafka nhiều broker theo lịch hoặc trong pipeline integration chuyên biệt.
6. Lưu log test và thông tin broker khi failure để có thể tái hiện sự cố.

Khi nâng Spring Kafka hoặc Kafka client, chạy lại bộ test recover DLT vì hành vi API, kiểu future, header và cấu hình container có thể thay đổi giữa các phiên bản.

## Kết luận vận hành

Một bộ test recover về DLT đáng tin cậy phải xác nhận toàn bộ kết quả của recovery: số lần retry, DLT topic/partition, payload, metadata, lỗi gửi và source offset. Integration test với Embedded Kafka chứng minh được luồng cơ bản; các yêu cầu về ACL, replication, failover và transaction cần môi trường kiểm thử tương ứng.

Khi test được thiết kế theo các hợp đồng này, thay đổi error handler, retry policy, serializer hoặc destination resolver sẽ có bằng chứng rõ ràng rằng record lỗi vẫn được giữ lại và có thể điều tra, phát lại theo quy trình vận hành.

