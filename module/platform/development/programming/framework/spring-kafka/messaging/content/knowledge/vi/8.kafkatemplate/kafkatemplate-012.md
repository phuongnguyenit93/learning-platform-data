# Kiểm thử KafkaTemplate

**KafkaTemplate** là thành phần Spring Kafka mà producer dùng để gửi record tới Kafka. Một kiểm thử có giá trị cần xác minh nhiều hơn việc phương thức send được gọi: record có được serialize đúng, broker có nhận được, metadata có hợp lệ và consumer có thể đọc lại payload hay không. Với các nhánh lỗi, kiểm thử cần chứng minh ứng dụng quan sát được exception và không âm thầm coi lần gửi thất bại là thành công.

Trong module **SPRING_KAFKA_MESSAGING**, KafkaTemplate là một phần của luồng gửi nhận sự kiện cùng với @KafkaListener, topic, partition, offset và consumer group. Bài học này tập trung vào cách kiểm thử producer ở nhiều cấp độ, từ unit test cho logic phát hành sự kiện đến integration test với broker thật, đồng thời kiểm tra callback, serialization, lỗi kết nối và khả năng cô lập test.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Phân biệt unit test, slice/configuration test và integration test cho producer.
- Dùng Mockito để kiểm tra cách service gọi KafkaTemplate và chuyển tiếp kết quả.
- Dùng EmbeddedKafka để xác minh record thực sự được ghi và có thể đọc lại.
- Kiểm tra topic, key, value, partition, offset và header.
- Kiểm tra serialization/deserialization với payload sự kiện.
- Kiểm thử CompletableFuture, callback thành công và callback thất bại.
- Tạo test cho timeout, lỗi broker và lỗi serialize theo cách ổn định.
- Dùng Testcontainers khi cần broker gần với môi trường triển khai.
- Cô lập topic, consumer group và dữ liệu để tránh test phụ thuộc thứ tự chạy.
- Xác định rõ giới hạn của một lần gửi được broker xác nhận.

## 1. Cần kiểm thử điều gì ở KafkaTemplate?

Một producer thường có nhiều trách nhiệm: nhận dữ liệu nghiệp vụ, tạo event, chọn topic và key, gửi record, rồi xử lý kết quả gửi. Không phải mọi trách nhiệm đều cần broker để kiểm thử.

Hãy chia mục tiêu kiểm thử theo ranh giới:

| Mục tiêu | Cấp kiểm thử phù hợp | Điều cần xác minh |
|---|---|---|
| Tạo event từ dữ liệu nghiệp vụ | Unit test | Event có đúng eventId, timestamp và nội dung. |
| Chọn topic và key | Unit test | Service gọi KafkaTemplate với đúng topic, key và value. |
| Xử lý future | Unit test | Kết quả hoặc exception được chuyển tiếp đúng. |
| Cấu hình serializer | Integration test | Object được chuyển thành byte và giải mã đúng. |
| Ghi record vào Kafka | Integration test | Broker xác nhận record và trả metadata. |
| Đọc lại record | Integration test | Topic, key, value và header đúng như mong đợi. |
| Phân phối partition | Integration test với topic nhiều partition | Key được định tuyến theo cấu hình partitioner. |
| Khả năng chịu lỗi | Integration/failure test | Ứng dụng phản ứng đúng khi broker hoặc kết nối lỗi. |

Một unit test chỉ chứng minh logic của service với dependency được giả lập. Nó không chứng minh broker đang chạy, serializer tương thích hoặc metadata discovery hoạt động. Ngược lại, integration test không cần lặp lại mọi nhánh logic thuần túy đã được kiểm tra ở unit test.

## 2. Unit test service sử dụng KafkaTemplate

Unit test phù hợp để xác minh service gọi KafkaTemplate đúng tham số và trả lại future cho caller. Dùng Mockito để giả lập KafkaTemplate, nhờ đó test không cần khởi động broker.

Ví dụ service:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
        );
    }
}
~~~

Ví dụ unit test xác minh lời gọi và future được trả về:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderEventPublisherTest {

    @Mock
    KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    private OrderEventPublisher publisher;

    @BeforeEach
    void setUp() {
        publisher = new OrderEventPublisher(kafkaTemplate);
    }

    @Test
    void shouldSendEventWithOrderIdAsKey() {
        OrderCreatedEvent event = new OrderCreatedEvent(
                "evt-1001",
                "order-1001",
                Instant.parse("2026-01-10T10:15:30Z"),
                new BigDecimal("125.50")
        );

        CompletableFuture<SendResult<String, OrderCreatedEvent>> expected =
                new CompletableFuture<>();

        when(kafkaTemplate.send(
                "orders.created",
                "order-1001",
                event
        )).thenReturn(expected);

        CompletableFuture<SendResult<String, OrderCreatedEvent>> actual =
                publisher.publish(event);

        assertThat(actual).isSameAs(expected);
        verify(kafkaTemplate).send(
                "orders.created",
                "order-1001",
                event
        );
        verifyNoMoreInteractions(kafkaTemplate);
    }
}
~~~

Test này xác minh ba điều: topic là orders.created, key là orderId và publisher trả lại future từ KafkaTemplate. Nó không xác minh record đã được broker ghi.

Nếu service có thêm logic tạo event, hãy kiểm tra event trước khi gửi. Ví dụ, khi nhận một Order, publisher tạo OrderCreatedEvent với eventId duy nhất, timestamp và tổng tiền; unit test có thể kiểm tra các field này mà không cần Kafka.

Không nên mock quá sâu các lớp nội bộ của Kafka producer. Hãy giữ unit test tập trung vào hợp đồng của service với KafkaTemplate.

## 3. Kiểm tra future thất bại bằng unit test

KafkaTemplate.send trả về future. Khi producer không thể hoàn tất gửi, future có thể hoàn tất exceptionally. Có thể tạo một future thất bại để kiểm tra service có giữ nguyên trạng thái lỗi và không biến nó thành thành công giả hay không.

Ví dụ:

~~~java
@Test
void shouldPropagateSendFailure() {
    OrderCreatedEvent event = new OrderCreatedEvent(
            "evt-1002",
            "order-1002",
            Instant.parse("2026-01-10T10:15:30Z"),
            new BigDecimal("80.00")
    );

    CompletableFuture<SendResult<String, OrderCreatedEvent>> failed =
            new CompletableFuture<>();

    failed.completeExceptionally(
            new KafkaException("Broker is unavailable")
    );

    when(kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
    )).thenReturn(failed);

    CompletableFuture<SendResult<String, OrderCreatedEvent>> actual =
            publisher.publish(event);

    assertThat(actual).isCompletedExceptionally();
}
~~~

Nếu publisher gắn whenComplete để ghi log hoặc cập nhật metric, future trả về vẫn nên phản ánh thất bại nếu callback chỉ quan sát kết quả. Test có thể hoàn tất future bằng exception rồi xác minh callback hoặc collaborator xử lý lỗi được gọi.

Khi kiểm tra exception cụ thể, cần lưu ý CompletableFuture.join thường bọc lỗi trong CompletionException, còn get thường bọc trong ExecutionException. Hãy kiểm tra nguyên nhân gốc thay vì phụ thuộc vào lớp wrapper.

Unit test lỗi hữu ích cho các trường hợp khó tái tạo ổn định bằng broker thật, ví dụ callback nhận exception, retry policy được gọi đúng số lần hoặc publisher chuyển lỗi sang một thành phần xử lý riêng.

## 4. Integration test với EmbeddedKafka

**EmbeddedKafka** cung cấp broker nhúng cho kiểm thử Spring Kafka. Nó phù hợp với integration test nhanh, giúp kiểm tra KafkaTemplate gửi record thật và consumer đọc được record đó trong cùng test context.

Một test class có thể khai báo topic và ánh xạ địa chỉ broker nhúng vào cấu hình Spring Boot:

~~~java
@SpringBootTest(properties = {
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.acks=all"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "orders.created",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaTemplateIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;

}
~~~

Các thuộc tính serializer trong ví dụ dùng String để tập trung vào hành vi gửi. Nếu ứng dụng gửi DTO, hãy dùng đúng JsonSerializer/JsonDeserializer hoặc serializer thực tế của dự án. Phiên bản Spring Kafka cần tương thích với cách khai báo @EmbeddedKafka và bootstrapServersProperty.

Ví dụ kiểm tra record gửi đi (đặt phương thức này trong class ở trên, thay cho phần thân placeholder):

~~~java
@Test
void shouldPublishRecordAndReadItBack() throws Exception {
    String topic = "orders.created";
    String groupId = "orders-template-test";

    Map<String, Object> consumerProps =
            KafkaTestUtils.consumerProps(
                    groupId,
                    "false",
                    embeddedKafka
            );

    consumerProps.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest"
    );

    try (Consumer<String, String> consumer =
                 new DefaultKafkaConsumerFactory<>(
                         consumerProps,
                         new StringDeserializer(),
                         new StringDeserializer()
                 ).createConsumer()) {

        embeddedKafka.consumeFromAnEmbeddedTopic(consumer, topic);

        SendResult<String, String> result =
                kafkaTemplate.send(
                        topic,
                        "order-1001",
                        "{\"orderId\":\"order-1001\",\"status\":\"CREATED\"}"
                ).get(10, TimeUnit.SECONDS);

        RecordMetadata metadata = result.getRecordMetadata();

        assertThat(metadata.topic()).isEqualTo(topic);
        assertThat(metadata.partition()).isEqualTo(0);
        assertThat(metadata.offset()).isGreaterThanOrEqualTo(0);

        ConsumerRecord<String, String> record =
                KafkaTestUtils.getSingleRecord(
                        consumer,
                        topic,
                        Duration.ofSeconds(10)
                );

        assertThat(record.key()).isEqualTo("order-1001");
        assertThat(record.value())
                .contains("\"status\":\"CREATED\"");

        assertThat(record.partition()).isEqualTo(metadata.partition());
        assertThat(record.offset()).isEqualTo(metadata.offset());
    }
}
~~~

Đoạn test tạo consumer trước khi gửi record, sau đó gửi bằng KafkaTemplate, chờ future hoàn tất với timeout và đọc lại một record từ topic. Việc so sánh partition và offset giúp xác nhận record đọc được chính là record mà producer vừa gửi.

Các lớp KafkaTestUtils, EmbeddedKafkaBroker, DefaultKafkaConsumerFactory và ConsumerRecord cần import từ Spring Kafka hoặc Apache Kafka tương ứng. API tiện ích có thể khác giữa các phiên bản; hãy dùng phiên bản Spring Kafka mà dự án đang quản lý.

Dùng get trong integration test là hợp lý vì test cần chờ kết quả để assertion. Trong code production, không nên chặn thread chỉ để chờ send hoàn tất nếu có thể dùng future hoặc callback.

## 5. Kiểm tra topic, key, partition và offset

Một kiểm thử producer nên xác minh những thuộc tính ảnh hưởng tới hành vi consumer.

- **Topic:** record được gửi tới đúng luồng sự kiện.
- **Key:** record mang key nghiệp vụ mong muốn, ví dụ orderId.
- **Partition:** record được định tuyến theo partitioner và cấu hình topic.
- **Offset:** broker cấp vị trí record trong partition.
- **Timestamp:** timestamp được thiết lập và trả về theo cấu hình timestamp của producer/broker.
- **Headers:** metadata bổ sung như correlation-id hoặc event-type được giữ nguyên.

Ví dụ gửi record kèm header:

~~~java
ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.created",
                null,
                System.currentTimeMillis(),
                "order-1001",
                "{\"orderId\":\"order-1001\"}"
        );

record.headers().add(
        "correlation-id",
        "corr-1001".getBytes(StandardCharsets.UTF_8)
);

SendResult<String, String> result =
        kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);

assertThat(result.getProducerRecord().headers()
        .lastHeader("correlation-id")).isNotNull();
~~~

Để xác minh header ở phía broker, nên đọc lại ConsumerRecord và kiểm tra header trên record nhận được. Việc kiểm tra ProducerRecord trước khi gửi chỉ xác nhận đối tượng đầu vào của producer có header, chưa chứng minh record được ghi và đọc lại đúng.

Khi kiểm tra partition, đừng giả định key cụ thể luôn rơi vào partition số cố định nếu chưa khóa rõ số partition, partitioner và cấu hình. Thay vào đó, kiểm tra record có key đúng và metadata partition phù hợp với hành vi mong đợi trong test setup.

## 6. Kiểm thử serialization và hợp đồng sự kiện

Kafka lưu byte; serializer của producer chuyển object thành byte và deserializer của consumer chuyển byte trở lại object. Vì vậy, test với StringSerializer chưa đủ để xác minh cấu hình JSON hoặc Avro/Protobuf của ứng dụng.

Với JSON, nên có ít nhất hai loại kiểm tra:

1. **Serialization test:** object được chuyển thành payload đúng, có các field và kiểu dữ liệu cần thiết.
2. **Round-trip integration test:** gửi object bằng KafkaTemplate, rồi đọc record bằng consumer có deserializer thực tế để xác minh object nhận được.

Ví dụ DTO:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        Instant occurredAt,
        BigDecimal total
) {}
~~~

Khi kiểm thử JSON, hãy chú ý:

- Field bắt buộc có mặt và không bị đổi tên ngoài ý muốn.
- Instant và BigDecimal được serialize theo định dạng nhất quán.
- Field mới có thể được consumer cũ xử lý theo quy ước tương thích.
- Type headers được xử lý đúng nếu ứng dụng sử dụng metadata kiểu của Spring Kafka.
- Trusted packages được cấu hình giới hạn phù hợp với model được phép deserialize.
- Payload sai định dạng hoặc thiếu dữ liệu bắt buộc tạo lỗi có thể quan sát và xử lý.

Không chỉ assert rằng payload chứa một chuỗi con. Nếu hợp đồng sự kiện quan trọng, hãy deserialize về DTO và so sánh từng field. Điều này phát hiện được lỗi kiểu dữ liệu, giá trị null và thay đổi schema mà kiểm tra chuỗi đơn giản có thể bỏ sót.

Với Avro hoặc Protobuf, test cần dùng schema và serializer/deserializer thực tế, đồng thời kiểm tra tương thích giữa phiên bản producer và consumer đang hỗ trợ.

## 7. Kiểm thử callback và kết quả bất đồng bộ

Trong Spring Kafka 3.x, KafkaTemplate.send trả về CompletableFuture. Test có thể chờ future hoàn tất để kiểm tra SendResult hoặc đăng ký callback để xác minh nhánh success/failure.

Ví dụ quan sát callback:

~~~java
CompletableFuture<SendResult<String, String>> sendFuture =
        kafkaTemplate.send("orders.created", "order-1002", "payload");

CompletableFuture<RecordMetadata> callbackResult =
        new CompletableFuture<>();

sendFuture.whenComplete((result, exception) -> {
    if (exception != null) {
        callbackResult.completeExceptionally(exception);
    } else {
        callbackResult.complete(result.getRecordMetadata());
    }
});

RecordMetadata metadata =
        callbackResult.get(10, TimeUnit.SECONDS);

assertThat(metadata.topic()).isEqualTo("orders.created");
~~~

Dùng một future phụ giúp test đợi đúng kết quả callback. Không cần Thread.sleep để phỏng đoán lúc callback chạy.

Các tình huống cần kiểm tra:

- Callback success nhận được SendResult và metadata hợp lệ.
- Callback failure nhận exception khi future thất bại.
- Callback không biến một future thất bại thành thành công giả.
- Callback không chặn luồng producer bằng truy vấn database hoặc HTTP đồng bộ.
- whenCompleteAsync sử dụng executor có giới hạn và test được trường hợp executor từ chối tác vụ nếu đó là hành vi ứng dụng cần quản lý.

Nếu callback chỉ ghi log hoặc metric, unit test với mock thường đủ. Nếu callback có tác động tới trạng thái nghiệp vụ, hãy kiểm tra trạng thái đó qua collaborator hoặc kết quả được công bố rõ ràng.

## 8. Kiểm thử lỗi và giới hạn retry

Không phải mọi lỗi producer đều dễ tạo ra bằng integration test. Dừng broker giữa test, ngắt mạng hoặc thay đổi ACL có thể hữu ích nhưng dễ gây phụ thuộc môi trường và làm test không ổn định.

Hãy chọn cách kiểm thử theo mục tiêu:

| Tình huống | Cách kiểm thử phù hợp |
|---|---|
| Future hoàn tất exceptionally | Unit test bằng CompletableFuture thất bại. |
| Lỗi serialization | Dùng serializer thật với object không hợp lệ hoặc cấu hình không tương thích. |
| Broker không sẵn sàng | Failure test với container/broker được dừng có kiểm soát. |
| Timeout hoặc lỗi network | Testcontainers và cơ chế fault injection phù hợp với môi trường. |
| Thiếu quyền ghi | Kafka test cluster bật ACL và credential có quyền giới hạn. |
| Retry quá số lần | Unit test policy hoặc integration test có timeout xác định. |

Khi test retry, hãy xác minh số lần thử, khoảng nghỉ hoặc trạng thái cuối cùng theo chính sách. Tránh retry vô hạn vì test sẽ treo hoặc tiêu tốn tài nguyên.

Cũng cần phân biệt retry nội bộ của Kafka producer với retry do ứng dụng thực hiện sau khi future thất bại. Idempotent producer giúp xử lý retry nội bộ theo bảo đảm Kafka cung cấp; nó không tự khử trùng một lần gọi send mới từ ứng dụng sau khi trạng thái lần gửi trước không chắc chắn.

Nếu ứng dụng retry lại một event nghiệp vụ, hãy giữ eventId ổn định và thiết kế consumer idempotent. Test nên xác minh việc gửi lặp không tạo hai tác động nghiệp vụ, ngay cả khi topic có thể chứa nhiều record cùng eventId trong tình huống không chắc chắn.

## 9. EmbeddedKafka và Testcontainers: chọn công cụ nào?

Cả EmbeddedKafka và Testcontainers đều có thể hỗ trợ integration test, nhưng phù hợp với những nhu cầu khác nhau.

| Tiêu chí | EmbeddedKafka | Testcontainers |
|---|---|---|
| Mục tiêu | Kiểm thử tích hợp nhanh trong test JVM | Kiểm thử với broker chạy trong container |
| Khởi động | Thường nhanh, thuận tiện cho test Spring Kafka | Phụ thuộc Docker và thời gian khởi động container |
| Cấu hình broker | Phù hợp các kịch bản test tập trung | Có thể cấu hình gần với image/phiên bản triển khai |
| Nhiều broker | Hỗ trợ theo cách tổ chức test và phiên bản | Có thể dựng cluster nếu test cần |
| Mạng triển khai | Không đại diện đầy đủ cho network production | Có thể kiểm tra port mapping và địa chỉ container |
| Khi nên dùng | Logic producer/consumer, metadata, serialization và callback | Tương thích broker, bảo mật, nhiều broker và hành vi gần production |

EmbeddedKafka thích hợp để xác minh KafkaTemplate và listener trong một test context gọn nhẹ. Testcontainers phù hợp khi khác biệt giữa broker trong test và broker production có thể ảnh hưởng kết quả, hoặc cần kiểm tra cấu hình broker cụ thể.

Với Testcontainers, địa chỉ bootstrap phải được lấy động từ container, không hardcode localhost. Ví dụ cấu hình Spring test:

~~~java
@DynamicPropertySource
static void kafkaProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.kafka.bootstrap-servers",
            kafkaContainer::getBootstrapServers
    );
}
~~~

kafkaContainer cần được khai báo và khởi động bằng module Testcontainers Kafka phù hợp với phiên bản dependency của dự án. Tên package và loại container có thể khác giữa các phiên bản; hãy dùng đúng API đã chọn trong build.

Không cần dùng Testcontainers cho mọi unit test. Khởi động container chỉ ở những test thực sự cần broker sẽ giúp suite nhanh và ổn định hơn.

## 10. Cô lập dữ liệu và tránh test phụ thuộc thứ tự

Kafka là hệ thống lưu log. Record của test trước có thể còn trong topic và bị test sau đọc lại nếu dùng chung topic, group-id hoặc offset.

Để test độc lập:

- Dùng topic riêng cho test hoặc tên topic duy nhất theo test run.
- Dùng consumer group riêng để tránh dùng lại offset của test khác.
- Cấu hình auto.offset.reset có chủ đích khi group chưa có offset.
- Tạo consumer trước khi gửi nếu test cần đọc record mới ngay sau đó.
- Đọc đúng số record cần thiết, dùng timeout rõ ràng.
- Đóng consumer và producer do test tự tạo trong finally hoặc try-with-resources.
- Tránh xóa topic dùng chung nếu test khác có thể đang sử dụng.
- Không phụ thuộc vào thứ tự chạy test hoặc trạng thái broker còn sót từ lần chạy trước.

Một lỗi phổ biến là dùng consumer group cố định cho nhiều test. Khi group đã commit offset từ lần trước, test sau có thể không đọc lại record cũ dù auto.offset.reset được đặt earliest. auto.offset.reset chỉ áp dụng khi group không có offset hợp lệ; nó không ghi đè offset đã commit.

Nếu test chạy song song, nên cấp topic và group-id duy nhất cho từng test hoặc từng test worker. Dọn dẹp tài nguyên cần được thiết kế để không xóa topic mà test khác đang sử dụng.

## 11. Kiểm tra transaction và mức xác nhận

Nếu producer sử dụng acks=all, test có thể xác minh future hoàn tất và metadata được trả về sau khi broker xác nhận theo cấu hình ISR. Tuy nhiên, test không nên suy ra callback success có nghĩa consumer đã xử lý record hoặc database đã commit.

Với Kafka transaction, cần kiểm tra hai lớp:

- Send future của từng record.
- Kết quả commit hoặc abort của transaction.

Một send có thể nhận kết quả broker trong lúc transaction còn đang mở. Consumer cấu hình isolation.level=read_committed chỉ đọc record thuộc transaction đã commit. Vì vậy, test transaction nên có cả nhánh commit và abort, rồi dùng consumer read_committed để xác minh record nào được nhìn thấy.

Transaction của Kafka không bao phủ database hoặc API bên ngoài. Nếu producer phát event dựa trên thay đổi database, hãy kiểm thử outbox/inbox hoặc idempotency ở ranh giới dữ liệu tương ứng.

## 12. Quy trình xây dựng một bộ test producer

Có thể triển khai theo trình tự sau:

1. Viết unit test cho service tạo event, chọn topic/key và gọi KafkaTemplate.
2. Kiểm tra future được trả về và exception được giữ đúng.
3. Dựng EmbeddedKafka để kiểm tra record thực sự được ghi.
4. Đọc lại record để xác minh key, value, header, partition và offset.
5. Thêm round-trip test cho serializer/deserializer thực tế.
6. Kiểm tra callback success và failure.
7. Thêm test retry có giới hạn và kiểm tra idempotency nếu ứng dụng retry ở cấp nghiệp vụ.
8. Dùng Testcontainers cho những kịch bản cần broker hoặc network gần production.
9. Cô lập topic và group-id để test có thể chạy độc lập và song song.
10. Đưa các test cần broker vào pipeline CI với timeout và dọn dẹp tài nguyên rõ ràng.

Không phải mọi thay đổi code đều cần chạy toàn bộ cluster test. Unit test nên chạy thường xuyên; integration test chạy trong pipeline phù hợp; test lỗi mạng hoặc nhiều broker có thể nằm ở nhóm kiểm thử chuyên biệt.

## 13. Bài tập tổng hợp: kiểm thử OrderEventPublisher

Hãy xây dựng OrderEventPublisher gửi OrderCreatedEvent tới topic orders.created.

Yêu cầu:

1. Viết unit test xác minh publisher gọi KafkaTemplate với đúng topic, orderId làm key và event làm value.
2. Kiểm tra publisher trả về đúng CompletableFuture.
3. Tạo future thất bại để xác minh lỗi được giữ nguyên và callback failure được kích hoạt.
4. Dùng EmbeddedKafka để gửi record tới broker nhúng.
5. Đọc lại ConsumerRecord và xác minh key, payload, topic, partition và offset.
6. Kiểm thử header correlation-id.
7. Dùng serializer/deserializer thực tế của ứng dụng để kiểm tra JSON round-trip.
8. Kiểm tra callback success và đo thời gian hoàn tất gửi.
9. Tạo failure test có giới hạn để xác minh retry policy.
10. Nếu ứng dụng retry event, gửi lặp cùng eventId và xác minh consumer không lặp tác động nghiệp vụ.
11. Dùng Testcontainers nếu cần xác minh phiên bản broker, security hoặc network.
12. Chạy test song song để kiểm tra việc cô lập topic và consumer group.

Bộ test hoàn thành khi chứng minh được ba lớp: service gọi KafkaTemplate đúng; broker nhận và trả metadata; consumer đọc lại được record đúng hợp đồng. Với nhánh lỗi, test cần chứng minh ứng dụng nhận biết thất bại, giữ thông tin nguyên nhân và xử lý retry có giới hạn.

## 14. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Unit test | Mockito và KafkaTemplate | Xác minh đúng topic, key, value và future. |
| 2. Future/error | CompletableFuture, exception | Kiểm tra được cả success và failure. |
| 3. Broker test | EmbeddedKafka | Gửi và đọc lại được record thật. |
| 4. Metadata | SendResult, RecordMetadata | Xác minh topic, partition và offset. |
| 5. Serialization | JSON hoặc schema serializer | Round-trip payload đúng hợp đồng. |
| 6. Callback | whenComplete và whenCompleteAsync | Callback chạy đúng nhánh và không chặn producer. |
| 7. Reliability | Retry, idempotence, eventId | Test được retry có giới hạn và xử lý lặp an toàn. |
| 8. Container test | Testcontainers | Kiểm tra được broker và cấu hình gần production. |
| 9. Isolation | Topic, group-id, cleanup | Test độc lập, chạy lặp và chạy song song ổn định. |

Bài học hoàn thành khi bạn có bộ unit test xác minh hợp đồng publisher, integration test xác minh record thực sự được ghi và đọc lại, cùng các kiểm tra cho metadata, serialization, callback và lỗi. Hãy giữ rõ ranh giới giữa broker xác nhận record và consumer hoàn tất nghiệp vụ; hai kết quả này cần những kiểm thử khác nhau.

KafkaTemplate giúp việc gửi record trong Spring trở nên thuận tiện, nhưng chỉ kiểm thử ở cấp service là chưa đủ để chứng minh luồng messaging hoạt động. Kết hợp unit test, EmbeddedKafka hoặc Testcontainers, kiểm tra metadata và đọc lại record sẽ giúp phát hiện sớm lỗi cấu hình, serialization, kết nối và xử lý bất đồng bộ.

