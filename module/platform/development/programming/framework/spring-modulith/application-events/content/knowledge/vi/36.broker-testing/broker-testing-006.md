# Kiểm thử retry route

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi event được chuyển qua Kafka hoặc broker khác, lỗi xử lý có thể khiến message đi qua nhiều tuyến: topic chính, một hoặc nhiều retry topic rồi đến dead-letter topic (DLT). **Kiểm thử retry route** xác minh message được chuyển đúng tuyến theo loại lỗi, số lần thử, backoff và chính sách phục hồi.

Một test retry route cần chứng minh cả đường đi của message và kết quả nghiệp vụ. Việc listener ném exception hoặc bộ đếm retry tăng chưa đủ; cần xác nhận message xuất hiện ở topic dự kiến, metadata được giữ đúng, consumer cuối cùng xử lý hoặc chuyển DLT theo policy, và side effect không bị lặp.

## 1. Retry route là gì?

Retry route là đường đi của một message sau khi consumer xử lý thất bại. Tùy cơ chế retry, broker có thể giữ message ở topic ban đầu để thử lại hoặc chuyển message sang các topic retry có thời gian chờ khác nhau.

Một tuyến non-blocking retry điển hình:

~~~mermaid
flowchart LR
    A[orders] --> B{Listener xử lý}
    B -->|Thành công| C[Commit offset]
    B -->|Lỗi tạm thời| D[orders-retry-1s]
    D --> E[orders-retry-5s]
    E --> F[orders-retry-30s]
    F --> G{Thử lại thành công?}
    G -->|Có| C
    G -->|Không| H[orders-dlt]
    B -->|Lỗi không retry| H
~~~

Các tên topic trong sơ đồ chỉ minh họa. Tên thực tế phụ thuộc naming strategy và cấu hình của ứng dụng.

Route cần thể hiện được:

- Event bắt đầu từ topic nào và được consumer group nào nhận.
- Exception nào được xem là retryable.
- Retry được chuyển sang topic hoặc tuyến nào.
- Số lần thử và khoảng chờ ở mỗi bước.
- Khi nào message được đưa vào DLT.
- Metadata nào được giữ để điều tra và replay.

## 2. Phân biệt blocking retry và retry topic

Spring Kafka hỗ trợ nhiều cách retry. Hai kiểu phổ biến có hành vi route khác nhau:

| Cơ chế | Cách xử lý | Hành vi route |
| --- | --- | --- |
| Blocking retry với DefaultErrorHandler | Consumer thử lại cùng record trong luồng xử lý, thường có backoff. | Record tiếp tục được xử lý tại partition/topic ban đầu; sau khi hết retry có thể được recover hoặc gửi DLT. |
| Non-blocking retry với RetryableTopic | Record lỗi được publish sang retry topic phù hợp với khoảng chờ; listener nhận lại từ retry topic. | Message đi qua các retry topic rồi DLT nếu không thành công. |

Blocking retry có thể giữ partition không tiến lên trong lúc chờ, ảnh hưởng các record phía sau cùng partition. Retry topic cho phép consumer tiếp tục xử lý record khác trên topic chính, nhưng thứ tự xử lý tổng thể có thể thay đổi vì record đang retry được xử lý muộn hơn.

Không nên dùng một test chung để khẳng định cả hai cơ chế. Test blocking retry cần kiểm tra số lần invocation, backoff và hành vi recover của error handler. Test retry topic cần kiểm tra topic đích, chuyển tuyến giữa các retry stage và DLT.

## 3. Thiết kế route theo loại exception

Route phải phản ánh ý nghĩa của lỗi. Ví dụ:

| Loại lỗi | Retry? | Tuyến mong đợi |
| --- | --- | --- |
| Timeout dependency tạm thời | Có, nếu thao tác an toàn khi lặp | Retry topic với backoff tăng dần |
| HTTP 429/rate limit | Có, theo Retry-After hoặc policy | Retry topic có khoảng chờ phù hợp |
| Database connection tạm lỗi | Có giới hạn | Retry topic hoặc blocking retry |
| Payload sai schema | Không | DLT/quarantine ngay hoặc sau bước kiểm tra phù hợp |
| Vi phạm quy tắc nghiệp vụ | Thường không | Event kết quả nghiệp vụ hoặc DLT tùy hợp đồng |
| Lỗi lập trình không xác định | Không nên retry mù quáng | DLT và cảnh báo |
| Hết retry budget | Không tiếp tục tự động | DLT hoặc trạng thái cần can thiệp |

Một lỗi nghiệp vụ hợp lệ như hàng không đủ không nhất thiết là lỗi consume. Handler nên phát event kết quả như InventoryUnavailable nếu đó là một nhánh nghiệp vụ bình thường. DLT dành cho message không thể xử lý theo hợp đồng hoặc lỗi kỹ thuật đã hết chính sách phục hồi.

Khi phân loại exception, cần xét cả cause chain và hợp đồng của dependency. Một SocketTimeoutException có thể xảy ra trước khi request được gửi hoặc sau khi hệ thống đích đã thực hiện side effect. Trường hợp thứ hai cần đối soát trước khi gửi lại.

## 4. Cấu hình retry topic bằng Spring Kafka

Với non-blocking retry, Spring Kafka cung cấp annotation RetryableTopic để tạo tuyến retry và DLT. Ví dụ:

~~~java
@Component
class OrderConsumer {

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
            delay = 1_000,
            multiplier = 2.0,
            maxDelay = 10_000
        ),
        include = {TransientInventoryException.class},
        exclude = {InvalidOrderEventException.class},
        dltTopicSuffix = ".dlt"
    )
    @KafkaListener(
        topics = "orders",
        groupId = "inventory-service"
    )
    void consume(OrderConfirmed event) {
        inventoryService.reserve(event);
    }

    @DltHandler
    void onDlt(OrderConfirmed event) {
        dltService.recordForInvestigation(event);
    }
}
~~~

Ví dụ minh họa cấu hình retry topic; các thuộc tính annotation và cách khai báo DLT cần đối chiếu với phiên bản Spring Kafka của ứng dụng. Với cấu hình attempts, hãy xác minh cách phiên bản đang dùng tính tổng số lần giao, bao gồm hay không bao gồm lần xử lý đầu tiên, trước khi viết assertion.

Trong test, không chỉ kiểm tra annotation có mặt. Cần chứng minh một exception thuộc include đi vào retry route, exception thuộc exclude không bị thử lại theo policy và record hết số lần thử đi đến DLT.

## 5. Blocking retry với DefaultErrorHandler

Với blocking retry, DefaultErrorHandler có thể kết hợp BackOff và DeadLetterPublishingRecoverer. Ví dụ khái quát:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    BackOff backOff = new FixedBackOff(1_000L, 2L);
    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.addRetryableExceptions(
        TransientInventoryException.class
    );
    handler.addNotRetryableExceptions(
        InvalidOrderEventException.class
    );

    return handler;
}
~~~

Trong ví dụ, retryable exception được thử lại theo BackOff; lỗi không retryable được chuyển thẳng đến recoverer. Số lần retry và cách tính tổng invocation phải được xác nhận theo API/version đang dùng. Không dùng test của retry topic để kiểm tra cấu hình này vì record không đi qua các retry topic.

## 6. Kiểm thử topology của retry route

Trước khi gửi message, xác định topology mong đợi:

- Topic chính.
- Các retry topic và thứ tự của chúng.
- DLT.
- Partition count và replication phù hợp.
- Consumer group xử lý từng tuyến.
- Listener hoặc recoverer chịu trách nhiệm ở từng topic.

Topic name có thể được tạo theo suffixing strategy hoặc cấu hình custom. Test nên lấy tên từ cấu hình hoặc khai báo topology cố định cho môi trường test, tránh phụ thuộc vào một tên suffix tự suy đoán.

Với retry topic, partition count cần tương thích với yêu cầu định tuyến key và tải. Nếu topic retry có số partition khác topic chính, record có thể không còn giữ được partition mapping như mong muốn. Hãy kiểm thử key và partition thực tế nếu nghiệp vụ phụ thuộc vào thứ tự theo key.

## 7. Chọn broker cho test

Có hai lựa chọn thường dùng:

| Môi trường | Phù hợp với |
| --- | --- |
| Embedded Kafka từ spring-kafka-test | Test route, header, retry stage, DLT và consumer group trong suite nhanh. |
| Kafka qua Testcontainers | Test gần production hơn về broker image, listener configuration, security, replication và broker behavior. |

Embedded Kafka giúp test không cần broker bên ngoài và phù hợp để xác minh logic route. Testcontainers phù hợp khi cần kiểm tra cấu hình broker thật hơn, chẳng hạn SASL/TLS, ACL hoặc hành vi liên quan phiên bản Kafka.

Không nên thay broker bằng mock hoàn toàn khi mục tiêu test là xác minh record thực sự được publish sang retry topic hoặc DLT. Mock có thể kiểm tra listener gọi recoverer, nhưng không xác minh serialization, topic tồn tại, partition, header hoặc broker acknowledgement.

## 8. Cấu trúc integration test với Embedded Kafka

Một test có thể khởi chạy broker nhúng và Spring context:

~~~java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders"}
)
@DirtiesContext
class OrderRetryRouteTest {

    @Autowired
    KafkaTemplate<String, OrderConfirmed> kafkaTemplate;

    @Test
    void routesTransientFailureThroughRetryTopic() {
        // Gửi event có key riêng cho test.
        // Chờ consumer retry nhận event và xử lý thành công.
        // Xác minh số lần thử và side effect chỉ xảy ra một lần.
    }
}
~~~

Đây là skeleton minh họa. Cần cấu hình bootstrap servers, serializer/deserializer, group ID và retry topic topology theo phiên bản Spring Kafka. Nếu retry topics được tự tạo, chờ topology sẵn sàng trước khi gửi event; nếu khai báo topic tường minh, bảo đảm tất cả topic cần thiết có đủ partition.

Trong một số phiên bản, EmbeddedKafka cung cấp broker address qua property riêng; Spring Boot cần được cấu hình dùng đúng address đó. Không giả định broker nhúng tự động dùng đúng bootstrap servers của application nếu chưa cấu hình.

## 9. Gửi message và chờ route một cách xác định

Test nên gửi record với key và eventId riêng, đợi broker xác nhận send rồi mới bắt đầu assertion:

~~~java
SendResult<String, OrderConfirmed> result =
    kafkaTemplate.send(
        "orders",
        "order-test-42",
        new OrderConfirmed(
            "event-test-42",
            "order-test-42"
        )
    ).get(5, TimeUnit.SECONDS);

assertThat(result.getRecordMetadata().topic())
    .isEqualTo("orders");
~~~

Đoạn code minh họa cần thay record constructor theo event contract thực tế. Việc send hoàn tất chỉ xác nhận producer nhận được kết quả gửi theo cấu hình broker; nó chưa chứng minh listener đã xử lý xong hoặc message đã đi qua retry route.

Để chờ kết quả, dùng Awaitility hoặc cơ chế đồng bộ trong test:

~~~java
await()
    .atMost(Duration.ofSeconds(15))
    .untilAsserted(() ->
        assertThat(orderProjection.findByOrderId("order-test-42"))
            .hasValueSatisfying(order ->
                assertThat(order.status()).isEqualTo("RESERVED")
            )
    );
~~~

Không dùng Thread.sleep cố định để giả định retry đã chạy xong. Thời gian scheduling, rebalance và tốc độ broker có thể thay đổi giữa local và CI.

## 10. Kiểm thử route khi lỗi tạm thời rồi thành công

Kịch bản quan trọng nhất là listener thất bại một vài lần vì lỗi tạm thời rồi xử lý thành công:

1. Gửi event vào topic chính.
2. Test fixture làm lần xử lý đầu tiên ném TransientInventoryException.
3. Xác minh record được chuyển đến retry topic theo backoff.
4. Lần xử lý sau thành công.
5. Xác minh projection hoặc side effect cuối cùng tồn tại.
6. Xác minh event không bị đưa vào DLT.

Có thể dùng một test collaborator thread-safe để điều khiển số lần lỗi:

~~~java
class RetryFailurePlan {

    private final AtomicInteger remainingFailures =
        new AtomicInteger(2);

    void failFirstAttempts() {
        if (remainingFailures.getAndUpdate(value ->
                Math.max(0, value - 1)) > 0) {
            throw new TransientInventoryException();
        }
    }
}
~~~

Trong integration test, collaborator phải được inject vào listener thật. Không mock Kafka consumer hoặc retry infrastructure. Chỉ thay dependency nghiệp vụ gây lỗi để test điều khiển được kết quả.

Assert số lần invocation, topic retry đã nhận record và kết quả nghiệp vụ cuối. Nếu nhiều retry stage được cấu hình, kiểm tra record đi qua đúng stage theo policy thay vì chỉ xác nhận listener được gọi nhiều lần.

## 11. Kiểm thử lỗi không retry

Với lỗi không retryable, message cần đi theo tuyến được cấu hình, thường là DLT hoặc quarantine ngay:

- Gửi một event có payload hợp lệ về mặt serialization nhưng vi phạm event contract hoặc gây InvalidOrderEventException.
- Xác minh listener không đi qua retry stages dành cho lỗi tạm thời.
- Xác minh record xuất hiện ở DLT theo policy.
- Xác minh metadata ghi lại topic gốc, exception và thời điểm lỗi.
- Xác minh handler nghiệp vụ không tạo side effect một phần.

Đừng chỉ kiểm tra DLT có một record. Cần xác minh record đó chính là event vừa gửi bằng eventId/key, không phải record cũ còn lại từ test khác.

Nếu lỗi là kết quả nghiệp vụ bình thường, test nên xác minh event kết quả nghiệp vụ được phát và DLT không nhận record. Đây là cách phân biệt xử lý nghiệp vụ với lỗi kỹ thuật.

## 12. Kiểm thử hết retry budget và DLT

Khi mọi lần thử đều thất bại, record phải đến DLT sau khi retry budget cạn:

~~~mermaid
sequenceDiagram
    participant M as Main topic
    participant C as Listener
    participant R1 as Retry topic 1
    participant R2 as Retry topic 2
    participant D as DLT

    M->>C: Event E
    C-->>R1: Transient failure
    R1->>C: Retry attempt
    C-->>R2: Still failing
    R2->>C: Final retry
    C-->>D: Retry budget exhausted
~~~

Test cần xác minh:

- Số lần xử lý tổng thể theo semantics của cấu hình.
- Không có retry stage ngoài dự kiến.
- DLT nhận đúng một record cho eventId.
- Không còn record cùng eventId trong retry topic đang chờ xử lý.
- DLT handler ghi nhận trạng thái điều tra hoặc phát cảnh báo theo thiết kế.
- Publication/offset của từng tuyến được commit theo semantics của listener container.

Nếu DLT handler cũng thất bại, cần xác định policy cho lỗi DLT: retry, giữ record, dừng consumer hay chuyển sang quy trình vận hành. Không giả định DLT là nơi message tự động an toàn và không thể lỗi.

## 13. Kiểm tra header và metadata trên mỗi route

Khi message đi qua retry topic, broker record thường mang metadata phục vụ retry và điều tra. Tùy Spring Kafka version, các header có thể thể hiện:

- Topic gốc.
- Partition và offset gốc.
- Timestamp của lần gửi ban đầu.
- Exception class và message gần nhất.
- Thông tin delivery attempt hoặc retry destination.
- Key và các header nghiệp vụ của producer.

Test nên kiểm tra metadata qua API/header contract của phiên bản đang dùng. Không hardcode tên header nội bộ nếu thư viện cung cấp constant hoặc abstraction công khai. Nếu cần tương thích nhiều phiên bản, viết adapter test đọc metadata theo API đã được khóa trong dependency.

Các assertion hữu ích:

| Thuộc tính | Điều cần xác minh |
| --- | --- |
| Event ID | Giữ nguyên qua retry và DLT. |
| Key | Không bị mất hoặc thay đổi ngoài ý muốn. |
| Original topic | Có thể truy ra topic ban đầu. |
| Retry attempt | Tăng đúng theo từng lần giao. |
| Exception metadata | Ghi đúng loại lỗi cuối hoặc lỗi đã cấu hình. |
| Correlation ID | Được giữ để nối trace và log. |
| Timestamp | Phân biệt thời điểm phát ban đầu và thời điểm retry. |

Tránh đưa stack trace quá dài hoặc payload nhạy cảm vào header. Header có giới hạn kích thước thực tế và có thể được sao chép qua nhiều topic.

## 14. Kiểm thử key, partition và thứ tự

Kafka chỉ bảo đảm thứ tự trong một partition. Nếu route retry chuyển record sang topic khác, thứ tự giữa record đang retry và record mới trên topic chính có thể thay đổi. Đây là đặc tính quan trọng của non-blocking retry.

Ví dụ:

1. Event OrderUpdated version 4 bị lỗi và được chuyển sang retry topic.
2. Event OrderUpdated version 5 tiếp tục được xử lý trên topic chính.
3. Version 5 có thể hoàn tất trước version 4.

Nếu projection ghi đè theo thứ tự đến, dữ liệu có thể lùi về version 4 khi retry hoàn tất. Consumer cần kiểm tra aggregateVersion hoặc sequence và bỏ qua event cũ.

Test nên gửi nhiều event cùng key, cố tình làm event đầu retry và xác minh:

- Key được giữ đúng qua route.
- Partition mapping phù hợp với topology đã cấu hình.
- Test không giả định thứ tự hoàn tất giữa main topic và retry topic.
- Projection không bị lùi version.
- Các event cùng aggregate được xử lý theo policy nghiệp vụ.

Nếu nghiệp vụ bắt buộc strict ordering, hãy cân nhắc blocking retry hoặc thiết kế serialization theo aggregate key; non-blocking retry topic có thể không đáp ứng thứ tự toàn cục.

## 15. Kiểm thử route tùy chỉnh theo exception hoặc destination

Một hệ thống có thể định tuyến DLT khác nhau tùy loại exception, tenant hoặc nhóm nghiệp vụ. Ví dụ lỗi dữ liệu có thể vào orders-invalid.dlt, lỗi dependency vào orders-transient.dlt.

Khi có custom destination resolver, test nên bao phủ:

- Mỗi exception category được ánh xạ đúng destination.
- Exception lạ có fallback route rõ ràng.
- Không tạo topic name từ payload không tin cậy mà không validate.
- DLT destination tồn tại và có đủ partition.
- ACL của consumer/producer cho phép publish đến đúng topic đích.
- Metadata gốc được giữ qua custom route.

Không nên chỉ unit test resolver. Cần ít nhất một integration test xác minh record thực sự được publish vào destination do resolver chọn.

## 16. Kiểm thử idempotency khi route retry

Retry có nghĩa một event có thể được xử lý nhiều lần. Một lần xử lý có thể đã commit side effect rồi consumer gặp lỗi trước khi offset hoặc publication được xác nhận. Vì vậy, handler phải idempotent.

Các cách thường dùng:

- Giữ eventId ổn định qua main, retry và DLT.
- Lưu eventId đã xử lý trong inbox cùng transaction với side effect.
- Dùng unique constraint theo business key/eventId.
- Dùng idempotency key ổn định khi gọi hệ thống ngoài.
- Kiểm tra aggregate version để không áp dụng event cũ.

Test nên xác minh một event có thể được giao nhiều lần nhưng chỉ tạo một reservation, một payment capture hoặc một bản ghi projection theo semantics nghiệp vụ. Không chỉ đếm số lần listener được gọi; cần kiểm tra số side effect bền vững.

## 17. Kiểm thử DLT và replay

DLT là nơi lưu record không thể tiếp tục retry tự động. Một quy trình vận hành có thể sửa dữ liệu, khắc phục dependency rồi replay record về topic chính hoặc một topic phục hồi riêng.

Test replay cần xác minh:

1. Record DLT giữ eventId, key và metadata gốc.
2. Replay dùng chính sách rõ ràng và có audit.
3. Event được đưa về đúng topic/route.
4. Handler idempotent nên replay không nhân đôi side effect đã commit.
5. Nếu lỗi vẫn còn, record lại đi theo retry route hoặc DLT theo policy.
6. Không replay vô hạn mà không có giới hạn hoặc trạng thái điều tra.

Không tự động replay toàn bộ DLT sau khi deploy. Một phần record có thể là dữ liệu không hợp lệ hoặc lỗi nghiệp vụ không thể sửa bằng code mới.

## 18. Cô lập test broker và dữ liệu

Test retry route dễ bị nhiễm trạng thái từ lần chạy trước nếu dùng topic và group ID cố định. Hãy:

- Dùng topic riêng hoặc prefix duy nhất cho test run.
- Dùng consumer group ID riêng cho test.
- Tạo eventId/key duy nhất.
- Đọc đúng record theo eventId thay vì lấy record đầu tiên trong topic.
- Khởi tạo offset ở vị trí phù hợp, thường là earliest cho topic mới.
- Chờ consumer group và retry topology sẵn sàng trước khi gửi.
- Dừng consumer test và dọn topic/container sau khi listener hoàn tất.

Nếu dùng Embedded Kafka với context cache, bảo đảm broker lifecycle tương thích với Spring ApplicationContext. Nếu dùng Testcontainers, không để test class dừng container trong khi context khác còn giữ kết nối.

Không xóa hoặc reset topic dùng chung khi test khác đang chạy song song. Nếu cần parallel execution, tách topic/group theo worker hoặc dùng broker/container riêng.

## 19. Embedded Kafka và Testcontainers: chọn cách nào?

| Tiêu chí | Embedded Kafka | Kafka Testcontainers |
| --- | --- | --- |
| Tốc độ suite | Thường nhanh hơn và tích hợp trực tiếp với Spring test. | Chậm hơn do khởi động container. |
| Route retry cơ bản | Phù hợp để kiểm tra retry topics và DLT. | Phù hợp. |
| Cấu hình broker production-like | Có giới hạn theo broker test. | Có thể dùng image/version gần production. |
| SASL/TLS/ACL | Tùy khả năng cấu hình test broker. | Phù hợp hơn khi cần xác minh cấu hình thực. |
| Replication và nhiều broker | Không phải lựa chọn mặc định. | Có thể dựng topology nhiều broker nếu cần. |
| CI | Cần Java và test dependency. | Cần Docker/container runtime. |

Có thể dùng Embedded Kafka cho test route thường xuyên và một số integration test Testcontainers cho security, broker version hoặc replication. Không cần dùng cluster lớn cho mọi test nếu mục tiêu chỉ là kiểm tra exception routing.

## 20. Kiểm thử retry route không flaky

Retry route phụ thuộc scheduler, broker và consumer thread. Test sẽ dễ flaky nếu assertion dựa trên thời gian cứng hoặc dùng chung topic.

Các nguyên tắc:

- Dùng backoff ngắn trong profile test nhưng vẫn giữ thứ tự các stage.
- Dùng Awaitility với timeout tổng thể hữu hạn.
- Đợi record theo eventId và topic cụ thể.
- Không giả định chính xác thời điểm record được giao; kiểm tra nó không đến trước ngưỡng tối thiểu chỉ khi test đó thực sự cần xác minh delay.
- Dùng AtomicInteger hoặc fixture thread-safe cho failure plan.
- Không dùng Thread.sleep để đồng bộ test.
- Đặt timeout đủ rộng cho CI nhưng không kéo dài vô hạn.
- Sau khi đạt assertion, chờ các listener liên quan kết thúc trước cleanup.

Nếu cần xác minh backoff, kiểm tra khoảng thời gian quan sát được trong biên dung sai thay vì đòi timestamp chính xác đến mili giây. Đồng hồ CI và tải broker có thể làm thời điểm giao dao động.

## 21. Kiểm thử retry route với transaction

Nếu consumer dùng Kafka transaction hoặc listener cập nhật database trong transaction, cần kiểm tra cả route và commit semantics:

- Khi xử lý thành công, offset và side effect được commit theo cấu hình.
- Khi handler rollback, record được retry hoặc chuyển route theo error handler.
- Khi publish sang retry topic thất bại, record gốc không bị mất theo semantics đã cấu hình.
- Khi publish DLT thất bại, recovery không âm thầm đánh dấu message đã xử lý.
- Khi listener đã commit side effect nhưng offset commit lỗi, redelivery không tạo side effect trùng.

Không giả định transaction database và Kafka tự động là một transaction phân tán duy nhất. Nếu dùng Kafka transaction, transaction manager và container cần được cấu hình phù hợp; nếu ghi database và publish Kafka, cần outbox hoặc cơ chế phối hợp tương ứng.

## 22. Kiểm thử lỗi của chính retry route

Retry infrastructure cũng có thể thất bại. Nên kiểm tra các tình huống:

| Lỗi | Điều cần xác minh |
| --- | --- |
| Retry topic không tồn tại | Provisioning hoặc auto-creation thất bại được phát hiện rõ. |
| Không có quyền publish retry topic | Error được log/alert; record không bị xem là đã xử lý thành công. |
| Broker tạm mất kết nối | Producer retry hoặc container recovery theo policy. |
| DLT publish thất bại | Record được giữ/recover theo error handler; không mất im lặng. |
| Deserializer lỗi trên retry topic | DLT/quarantine nhận metadata đủ để điều tra. |
| Retry consumer không chạy | Backlog/lag của retry topic được quan sát và cảnh báo. |
| Rebalance giữa lúc retry | Record có thể được giao lại nhưng không lặp side effect. |
| DLT handler thất bại | Có chính sách retry hoặc can thiệp riêng cho DLT. |

Test các lỗi hạ tầng này thường cần broker integration test và một số test điều khiển producer/consumer. Không nên cố tạo mọi lỗi trong từng test route cơ bản; chọn scenario đại diện để suite vẫn ổn định.

## 23. Quan sát retry route trong test và production

Để debug route, ghi nhận các trường:

- eventId và correlationId.
- Topic hiện tại và topic gốc.
- Consumer group và partition/offset.
- Retry attempt và thời điểm giao.
- Exception category và exception type.
- Destination tiếp theo hoặc DLT.
- Kết quả side effect và idempotency decision.

Metrics nên theo dõi số record ở từng retry topic, consumer lag, số record vào DLT, tỷ lệ retry thành công và tuổi của record cũ nhất. Một retry topic có backlog tăng liên tục có thể cho thấy backoff quá dài, consumer thiếu năng lực hoặc dependency chưa phục hồi.

Không ghi toàn bộ payload nhạy cảm hoặc secret vào log. Khi điều tra, dùng eventId để tra metadata và record trong hệ thống có quyền truy cập.

## 24. Những lỗi thường gặp khi kiểm thử retry route

| Lỗi test | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ verify listener invocation | Không chứng minh record đi đúng topic. | Đọc record từ retry topic/DLT bằng consumer test. |
| Dùng sleep cố định | Test flaky khi broker/CI chậm. | Chờ điều kiện với timeout hữu hạn. |
| Dùng topic/group cố định cho nhiều test song song | Đọc nhầm record hoặc tranh chấp offset. | Namespace topic/group theo test run. |
| Không phân biệt blocking và non-blocking retry | Assertion route sai cơ chế. | Viết test riêng cho từng error handler. |
| Chỉ kiểm tra DLT có record | Có thể là record cũ hoặc event khác. | Assert eventId, key và metadata. |
| Không kiểm tra exception classification | Lỗi nghiệp vụ bị retry vô hạn. | Test retryable và non-retryable riêng. |
| Giả định thứ tự toàn cục qua retry topic | Test fail hoặc projection lùi state. | Kiểm tra version/key và ordering contract. |
| Không kiểm tra side effect | Retry có thể tạo duplicate. | Assert inbox/unique constraint và kết quả bền vững. |
| Bỏ qua lỗi publish retry/DLT | Message có thể mất hoặc bị xác nhận sai. | Test recovery của producer/recoverer. |

## 25. Checklist kiểm thử retry route

- Xác định rõ đang kiểm thử blocking retry hay non-blocking retry topic.
- Khai báo topology topic chính, retry topic và DLT rõ ràng.
- Test exception retryable, non-retryable và lỗi hết retry budget.
- Xác minh route bằng record thực từ broker, không chỉ mock invocation.
- Kiểm tra attempts, backoff và semantics tổng số lần giao theo version.
- Kiểm tra eventId, key, original topic, exception metadata và correlation ID.
- Kiểm tra partition mapping và ordering khi nghiệp vụ phụ thuộc key.
- Dùng Embedded Kafka hoặc Testcontainers phù hợp mục tiêu test.
- Dùng topic/group/event ID riêng để cô lập test.
- Chờ route bằng điều kiện có timeout; tránh sleep cố định.
- Xác minh DLT và quy trình replay có idempotency.
- Kiểm tra retry/DLT publish failure và consumer lag.
- Xác minh transaction/offset commit không làm mất record hoặc lặp side effect.
- Theo dõi retry backlog, DLT volume và tuổi record trong production.

Kiểm thử retry route cần chứng minh message đi đúng tuyến theo exception và retry policy, giữ nguyên metadata cần thiết và kết thúc ở trạng thái nghiệp vụ an toàn. Khi test sử dụng broker thật hoặc broker nhúng, chờ theo điều kiện, cô lập topic/group và kiểm tra cả DLT lẫn side effect, hệ thống có thể phát hiện sớm lỗi định tuyến, retry vô hạn, mất message và xử lý trùng trước khi đưa event pipeline vào vận hành.
