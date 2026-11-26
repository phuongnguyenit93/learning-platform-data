# Kiểm thử topic

Kafka topic là nơi lưu trữ các record mà producer gửi và consumer đọc. Một topic có tên, số partition, replication factor và các cấu hình lưu trữ riêng. Kiểm thử topic cần xác minh cả cấu trúc broker lẫn hành vi thực tế của producer và consumer: topic có tồn tại, record được ghi đúng, key được định tuyến đúng, payload được deserialize đúng và consumer xử lý theo semantics đã thiết kế.

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application event có thể được externalize tới Kafka thông qua integration tương ứng. Kiểm thử cần đi qua đúng đường mapping từ event hoặc logical target tới topic vật lý. Chỉ kiểm tra annotation hoặc mock lời gọi producer chưa chứng minh record đã được broker nhận và consumer đọc được.

## 1. Xác định điều cần kiểm thử

Một topic có nhiều khía cạnh. Trước khi viết test, xác định contract và các thuộc tính cần xác minh:

| Phạm vi | Nội dung cần kiểm tra |
|---|---|
| Topic lifecycle | Topic được tạo, tồn tại và có thể được mô tả |
| Topic configuration | Partition, replication, retention, cleanup policy và các config quan trọng |
| Producer | Record được gửi đúng topic, key, value và headers |
| Consumer | Consumer group nhận record và deserialize đúng |
| Partitioning | Key được ánh xạ tới partition theo mong đợi |
| Ordering | Record cùng key giữ thứ tự trong cùng partition |
| Delivery | Acknowledgment, retry, redelivery và offset hoạt động đúng |
| Schema | Payload tương thích với contract và consumer |
| Failure handling | Broker unavailable, serialization failure, timeout và dead-letter |
| Externalization | Spring Modulith target được ánh xạ tới topic đúng và publication lifecycle được theo dõi |

Không phải test nào cũng cần kiểm tra mọi cấu hình. Chọn các thuộc tính ảnh hưởng trực tiếp đến contract hoặc SLA. Ví dụ, test partitioning quan trọng khi thứ tự theo aggregate là yêu cầu; test retention quan trọng khi consumer cần replay trong một khoảng thời gian xác định.

## 2. Dùng broker riêng cho mỗi test suite

Kiểm thử tích hợp nên dùng broker cô lập, thường thông qua Testcontainers. Broker riêng giúp test không phụ thuộc vào topic, offset hoặc consumer group của môi trường phát triển và production.

Một cấu hình Spring Boot test minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class StockReservedTopicIT {

    @Container
    static final KafkaContainer KAFKA =
        new KafkaContainer(
            DockerImageName.parse("apache/kafka-native:3.8.0")
        );

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.kafka.bootstrap-servers",
            KAFKA::getBootstrapServers
        );
    }

    @Test
    void applicationContextStartsWithTestBroker() {
        // Spring context sử dụng broker Testcontainers.
    }
}
~~~

Ví dụ minh họa với Testcontainers Kafka và Spring Boot. Package, image và constructor của KafkaContainer có thể khác theo phiên bản Testcontainers; hãy dùng API đúng với dependency đã chọn và ghim image version rõ ràng. Testcontainers cần Docker hoặc runtime container tương thích.

Dùng một container tĩnh cho test class hoặc suite để tránh khởi động broker cho từng test method. Nếu test chạy song song, mỗi test nên có topic và consumer group riêng hoặc dùng namespace duy nhất để tránh đọc nhầm record của nhau.

Không trỏ integration test vào Kafka production hoặc một cluster dùng chung có dữ liệu quan trọng. Test tạo/xóa topic, thay config hoặc reset offset có thể ảnh hưởng consumer khác.

## 3. Tạo topic và xác minh topic tồn tại

Có thể tạo topic bằng NewTopic bean qua KafkaAdmin hoặc tạo trực tiếp bằng AdminClient trong test. Nếu ứng dụng quản lý topic bằng bean, test nên xác minh chính cấu hình đó được broker áp dụng.

Ví dụ khai báo topic:

~~~java
@Bean
NewTopic stockReservedTopic() {
    return TopicBuilder.name("inventory.stock-reserved.v1")
        .partitions(3)
        .replicas(1)
        .build();
}
~~~

Ví dụ dùng Spring Kafka. KafkaAdmin có thể tạo topic từ NewTopic bean khi ứng dụng khởi động, tùy cấu hình admin và hành vi của phiên bản đang dùng. Không giả định topic đã được tạo chỉ vì bean tồn tại; hãy truy vấn broker để xác minh.

Có thể dùng AdminClient để mô tả topic:

~~~java
try (Admin admin = Admin.create(
        Map.of(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers
        ))) {

    admin.createTopics(List.of(
        new NewTopic("inventory.stock-reserved.v1", 3, (short) 1)
    )).all().get(10, TimeUnit.SECONDS);

    Map<String, TopicDescription> topics =
        admin.describeTopics(
            List.of("inventory.stock-reserved.v1")
        ).allTopicNames().get(10, TimeUnit.SECONDS);

    TopicDescription description =
        topics.get("inventory.stock-reserved.v1");

    assertThat(description.partitions()).hasSize(3);
}
~~~

Đây là ví dụ Kafka Admin API. Nếu topic đã tồn tại, createTopics có thể trả về lỗi TopicExistsException; test có thể xử lý trường hợp này hoặc tạo topic với tên duy nhất cho từng test. Không nuốt mọi exception vì lỗi quyền, cấu hình hoặc broker cũng cần làm test thất bại.

## 4. Kiểm tra partition và replication factor

Số partition ảnh hưởng đến khả năng song song của consumer group và cách record được phân phối. Test nên xác minh số partition thực tế thay vì chỉ kiểm tra property trong application config.

Các điểm cần kiểm tra:

- Topic có đúng số partition theo contract.
- Partition ID hợp lệ nằm trong khoảng từ 0 tới partition count trừ 1.
- Record có cùng key được định tuyến theo partitioner đã cấu hình.
- Consumer group có thể xử lý song song tối đa theo số partition được gán.
- Việc tăng partition có thể thay đổi mapping key sang partition và phải được xem là thay đổi vận hành.

Replication factor xác định số replica của mỗi partition. Một broker test đơn lẻ thường chỉ hỗ trợ replication factor 1. Không thể dùng broker đơn để chứng minh hành vi failover hoặc replication factor lớn hơn 1. Muốn kiểm tra ISR, leader election hoặc broker failure, cần cluster test có nhiều broker và cấu hình replica phù hợp.

Nếu môi trường test chỉ có một broker, hãy kiểm tra replication factor tương thích với broker đó và tách các kiểm thử HA thành một suite riêng.

## 5. Kiểm tra topic configuration

Topic có thể có các config ảnh hưởng trực tiếp đến khả năng phục hồi:

| Config | Ý nghĩa | Cách kiểm tra |
|---|---|---|
| retention.ms | Thời gian giữ record | Describe topic config |
| retention.bytes | Giới hạn dung lượng giữ lại | Describe topic config |
| cleanup.policy | delete, compact hoặc kết hợp | Xác minh giá trị config |
| min.insync.replicas | Số replica tối thiểu trong ISR cho mức acknowledgment phù hợp | Kiểm tra cùng replication factor |
| segment.bytes | Kích thước segment log | Xác minh nếu ứng dụng phụ thuộc |
| max.message.bytes | Kích thước record tối đa được topic chấp nhận | Kiểm tra giới hạn payload |

Ví dụ đọc topic config bằng AdminClient:

~~~java
ConfigResource resource = new ConfigResource(
    ConfigResource.Type.TOPIC,
    topicName
);

Config config = admin.describeConfigs(
    List.of(resource)
).all().get(10, TimeUnit.SECONDS).get(resource);

ConfigEntry retention = config.get("retention.ms");
assertThat(Long.parseLong(retention.value()))
    .isEqualTo(expectedRetentionMs);
~~~

Một số config có thể được kế thừa từ broker default và không xuất hiện như override riêng của topic. Khi kiểm tra, phân biệt cấu hình effective với cấu hình được đặt trực tiếp trên topic. Nếu contract yêu cầu giá trị hiệu lực, cần đọc cả default broker hoặc API/configuration phù hợp.

Không test việc record bị xóa đúng ngay sau một khoảng retention ngắn bằng sleep cố định. Kafka xóa segment theo chu kỳ và điều kiện log retention; kiểm tra config thường ổn định hơn. Nếu cần kiểm thử hành vi cleanup, dùng test riêng với thời gian, segment và log cleaner được kiểm soát.

## 6. Kiểm thử producer gửi record

Producer test cần xác minh broker thực sự nhận record. Với Spring Kafka, KafkaTemplate.send() trả về kết quả bất đồng bộ; chờ future hoàn tất giúp test kiểm tra metadata từ broker.

~~~java
@Test
void publishesRecordToExpectedTopic() throws Exception {
    StockReserved event = sampleStockReserved();

    SendResult<String, StockReserved> result =
        kafkaTemplate.send(
            "inventory.stock-reserved.v1",
            event.reservationId().toString(),
            event
        ).get(10, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic())
        .isEqualTo("inventory.stock-reserved.v1");
    assertThat(result.getRecordMetadata().partition())
        .isBetween(0, 2);
    assertThat(result.getRecordMetadata().offset())
        .isGreaterThanOrEqualTo(0);
}
~~~

Ví dụ dùng Spring Kafka 3.x, nơi send trả về CompletableFuture. Kiểu trả về và overload có thể khác ở phiên bản cũ. Test cần cấu hình key/value serializer giống ứng dụng thực tế.

Kết quả send thành công xác nhận broker đã acknowledge record theo cấu hình producer. Nó không chứng minh consumer đã xử lý nghiệp vụ. Hai điều kiện này phải được kiểm tra riêng.

Với producer bất đồng bộ, test phải chờ future hoặc callback hoàn tất. Không chỉ verify rằng KafkaTemplate.send() đã được gọi, vì lỗi serialization, timeout hoặc broker rejection có thể xảy ra sau lời gọi đó.

## 7. Kiểm tra key và partition routing

Kafka thường dùng key để định tuyến record tới partition. Nếu event cùng aggregate cần giữ thứ tự, test phải xác minh cùng key được gửi tới cùng partition theo partitioner đang dùng.

Ví dụ:

~~~java
@Test
void recordsWithSameAggregateKeyUseSamePartition() throws Exception {
    String key = "reservation-100";

    RecordMetadata first = kafkaTemplate.send(
        topic, key, eventAtVersion(1)
    ).get(10, TimeUnit.SECONDS).getRecordMetadata();

    RecordMetadata second = kafkaTemplate.send(
        topic, key, eventAtVersion(2)
    ).get(10, TimeUnit.SECONDS).getRecordMetadata();

    assertThat(second.partition()).isEqualTo(first.partition());
    assertThat(second.offset()).isGreaterThan(first.offset());
}
~~~

Ví dụ giả định cả hai record được gửi trong cùng topic và cùng producer configuration. Không khẳng định offset của các partition khác nhau có thể so sánh để suy ra thứ tự toàn cục. Kafka bảo đảm thứ tự trong một partition.

Nếu dùng custom partitioner, test cần xác minh quy tắc thực tế của partitioner đó. Khi tăng số partition, cùng key có thể được ánh xạ sang partition khác so với trước; không dùng test cố định một partition ID nếu contract chỉ yêu cầu cùng key giữ cùng partition trong cùng cấu hình.

## 8. Kiểm thử consumer nhận record

Consumer integration test cần xác minh record được nhận và chuyển đổi đúng kiểu. Với KafkaListener, có thể đưa record vào một queue kiểm thử hoặc kiểm tra side effect bền vững của consumer.

Ví dụ listener đưa event nhận được vào queue:

~~~java
@Component
class TestStockReservedListener {

    private final BlockingQueue<StockReserved> received =
        new LinkedBlockingQueue<>();

    @KafkaListener(
        topics = "${test.stock-topic}",
        groupId = "${test.consumer-group}"
    )
    void on(StockReserved event) {
        received.add(event);
    }

    StockReserved awaitEvent(Duration timeout)
            throws InterruptedException {
        return received.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Test có thể gửi record rồi chờ:

~~~java
@Test
void consumerReceivesDeserializedEvent() throws Exception {
    StockReserved expected = sampleStockReserved();

    kafkaTemplate.send(topic, expected.reservationId().toString(), expected)
        .get(10, TimeUnit.SECONDS);

    StockReserved actual =
        listener.awaitEvent(Duration.ofSeconds(10));

    assertThat(actual).isEqualTo(expected);
}
~~~

Ví dụ cần cấu hình test listener bean, topic property và JSON deserializer phù hợp. Trong test production-like, nên xác minh side effect của consumer ở database thay vì chỉ kiểm tra queue nhận event.

Dùng consumer group riêng cho từng test hoặc từng suite. Nếu tái sử dụng group ID và offset cũ, consumer có thể bắt đầu ở vị trí không mong muốn hoặc nhận record từ test trước.

## 9. Kiểm tra consumer group và offset

Consumer group xác định cách các instance chia partition và duy trì offset. Một số kịch bản cần kiểm tra:

- Hai instance cùng group chia nhau partition thay vì mỗi instance nhận toàn bộ record.
- Hai group độc lập đều có thể đọc cùng một topic.
- Consumer mới bắt đầu từ offset theo auto.offset.reset khi chưa có committed offset.
- Sau khi xử lý thành công, offset được commit theo acknowledgment policy.
- Khi process dừng trước commit, record có thể được giao lại.
- Rebalance không làm mất dữ liệu đã được ghi bền vững.

Không dùng một group ID cố định cho nhiều test song song. Dùng suffix duy nhất hoặc cấu hình group cho mỗi test để tránh offset và partition assignment can thiệp lẫn nhau.

Nếu kiểm thử redelivery, cố ý tạo cửa sổ giữa xử lý nghiệp vụ và commit offset. Xác minh inbox/idempotency ngăn side effect trùng. Không chỉ kiểm tra listener được gọi hai lần; điều quan trọng là trạng thái nghiệp vụ cuối cùng chỉ phản ánh một lần xử lý.

## 10. Kiểm tra serialization và headers

Topic lưu byte, do đó producer và consumer phải thống nhất serializer/deserializer. Kiểm thử payload cần bao gồm:

- Tên và kiểu trường theo contract.
- Timestamp ISO-8601 hoặc epoch với đơn vị đã xác định.
- Decimal và currency theo biểu diễn chính xác.
- Enum và trường nullable.
- Event type và schema version nếu topic chứa nhiều loại event.
- Event ID, correlation ID và trace context nếu cần.

Ngoài value, kiểm tra Kafka headers:

- Content type hoặc schema identifier.
- Event type/version.
- Correlation ID và causation ID.
- W3C traceparent/tracestate khi tracing được bật.
- Header định tuyến do integration sử dụng.

Không để header mang secret hoặc payload nhạy cảm. Test nên xác minh header được inject/extract đúng nhưng không phụ thuộc vào thứ tự header nếu contract không yêu cầu.

Nếu dùng Schema Registry, kiểm tra schema được đăng ký, compatibility mode và consumer đọc được payload theo phiên bản schema đã công bố. Test chỉ deserialize bằng cùng class Java ở producer và consumer có thể bỏ sót lỗi tương thích với hệ thống khác ngôn ngữ.

## 11. Kiểm tra retention và compaction

Retention và compaction ảnh hưởng tới khả năng replay:

- Với cleanup policy delete, record được giữ theo retention time/size rồi đủ điều kiện xóa.
- Với cleanup policy compact, Kafka giữ giá trị mới nhất theo key theo quá trình compaction.
- Với compact,delete, cả compaction và retention có thể tác động theo cấu hình.

Kiểm tra config bằng AdminClient là cách xác minh contract nhanh và ổn định. Nếu cần kiểm tra hành vi, phải hiểu compaction là tác vụ nền và không diễn ra ngay sau khi gửi record. Test cần cấu hình segment/cleanup phù hợp, chờ điều kiện quan sát được và có timeout hữu hạn.

Tombstone có value null có ý nghĩa đặc biệt với compacted topic. Test cần xác minh consumer hiểu tombstone là xóa trạng thái theo contract, không coi nó như payload JSON rỗng hoặc event bị lỗi deserialize.

Không dùng compacted topic như kho lưu toàn bộ lịch sử event. Nếu cần replay mọi thay đổi, cần topic/log có retention phù hợp hoặc archive/event store riêng.

## 12. Kiểm thử Spring Modulith externalization tới topic

Với Spring Modulith, event có thể dùng @Externalized để khai báo logical target:

~~~java
@Externalized("inventory.stock-reserved.v1")
public record StockReserved(
    UUID eventId,
    UUID reservationId,
    int quantity,
    Instant occurredAt
) {}
~~~

Target trong annotation là định danh externalization logic. Integration đang dùng quyết định target được ánh xạ tới topic vật lý như thế nào. Không mặc định @Externalized tự tạo Kafka topic hoặc tự cấu hình broker.

Một integration test xuyên suốt nên:

1. Phát event trong transaction nghiệp vụ.
2. Commit transaction.
3. Xác minh externalization listener được gọi theo cấu hình.
4. Xác minh target được ánh xạ tới đúng topic.
5. Đọc record từ broker và kiểm tra key, payload, headers.
6. Xác minh publication lifecycle theo acknowledgment semantics của adapter.
7. Mô phỏng lỗi gửi để kiểm tra publication còn khả năng phục hồi.
8. Resubmit publication và xác minh consumer xử lý redelivery idempotent.

Event Publication Registry theo dõi publication tới listener ở phía ứng dụng. Nó không phải Kafka consumer offset và không chứng minh consumer downstream đã hoàn tất nghiệp vụ. Test cần tách rõ broker acknowledgment, publication completion và consumer processing.

## 13. Kiểm thử topic không tồn tại hoặc cấu hình sai

Một số lỗi cần chủ động tạo:

- Producer gửi tới topic không tồn tại khi broker không bật auto topic creation.
- Producer thiếu quyền ghi topic.
- Consumer thiếu quyền đọc topic hoặc join group.
- Topic có partition count thấp hơn cấu hình mong đợi.
- Value serializer không tương thích với consumer deserializer.
- Message vượt max.message.bytes.
- Topic retention hoặc cleanup policy không đáp ứng yêu cầu replay.

Kết quả mong đợi phụ thuộc policy: producer nhận lỗi rõ, listener publication không bị đánh dấu hoàn tất giả, consumer không âm thầm bỏ record và hệ thống phát metric/cảnh báo phù hợp.

Nếu broker tự động tạo topic, test có thể vô tình pass với topic được tạo theo default partition/config sai. Trong test kiểm tra topic provisioning, nên tắt auto topic creation hoặc xác minh config thực tế sau khi topic xuất hiện.

## 14. Kiểm thử retry và dead-letter

Khi consumer xử lý record thất bại, kiểm tra chính sách retry và dead-letter:

- Lỗi tạm thời được retry theo backoff.
- Lỗi vĩnh viễn hoặc hết retry được chuyển sang DLT theo policy.
- Record DLT giữ key, payload, headers cần thiết và metadata nguồn.
- Offset của record gốc chỉ được commit sau khi DLT ghi thành công.
- Replay từ DLT giữ event ID và không tạo side effect trùng.
- Retry topic không phá ordering nếu nghiệp vụ cần thứ tự theo key.

Có thể kiểm tra DLT bằng consumer group riêng và chờ record với event ID mong đợi. Không chỉ kiểm tra method recoverer được gọi; cần xác minh broker thực sự lưu record lỗi.

## 15. Cô lập test và dọn dẹp topic

Test topic thường thất bại ngẫu nhiên khi dùng chung tên topic hoặc group ID. Một số nguyên tắc:

- Dùng topic name có namespace của test suite hoặc test case.
- Dùng consumer group riêng.
- Chỉ tạo topic trong broker test riêng.
- Dọn resource sau test khi cần, nhưng không xóa topic dùng chung trước khi consumer khác hoàn tất.
- Không dựa vào thứ tự chạy test.
- Đặt timeout hữu hạn cho send, receive và AdminClient.
- Chờ điều kiện cụ thể thay vì Thread.sleep() cố định.
- Giữ log broker và record metadata khi test thất bại.

Nếu test chạy song song, có thể tạo topic một lần cho suite và phân chia theo test ID. Tránh tạo quá nhiều topic không cần thiết vì broker cũng có chi phí metadata và partition.

## 16. Đọc kết quả khi topic test thất bại

Khi test thất bại, phân loại theo giai đoạn:

| Dấu hiệu | Nguyên nhân có thể | Nơi kiểm tra |
|---|---|---|
| Topic not found | Topic chưa được provision hoặc sai tên | AdminClient, KafkaAdmin, target mapping |
| Timeout khi send | Broker chưa sẵn sàng, metadata hoặc network lỗi | Bootstrap servers, broker log, producer future |
| SerializationException | Serializer hoặc payload không khớp | Producer config, schema, DTO |
| Consumer không nhận record | Group offset, subscription, deserializer hoặc listener lỗi | Consumer log, group ID, topic/partition |
| Sai partition | Key hoặc partitioner không như dự kiến | Producer key, partition count, custom partitioner |
| Record bị xử lý lặp | Offset commit, retry hoặc consumer restart | Inbox, idempotency, acknowledgment |
| Retention test không ổn định | Cleanup là tác vụ nền | Topic config, segment và log cleaner |
| AuthorizationException | ACL hoặc credential thiếu quyền | Principal và topic/group ACL |

Đọc exception gốc và record metadata trước khi tăng timeout. Một test consumer không nhận được record có thể do offset đang ở cuối log hoặc group đã commit offset từ test trước, không nhất thiết do producer gửi thất bại.

## 17. Kiểm thử trong CI

CI cần chạy broker test với phiên bản tương thích với production. Cần kiểm soát:

- Docker/runtime container có sẵn và đủ tài nguyên.
- Image broker được ghim version.
- Topic và group được tạo cô lập.
- Port và bootstrap endpoint được lấy từ container động, không hard-code.
- Test có timeout phù hợp với CI.
- Container được đóng sau suite.
- Test song song không chia sẻ topic hoặc offset ngoài ý muốn.
- Log broker và report test được lưu khi failure.

Nếu môi trường CI không hỗ trợ Docker, có thể dùng broker test thay thế hoặc một test profile riêng, nhưng cần ghi rõ giới hạn. Mock producer/consumer chỉ phù hợp cho unit test; nó không thay thế integration test với broker thật cho những contract về topic, partition, offset và acknowledgment.

## 18. Checklist kiểm thử topic

Trước khi xem topic đã được kiểm thử đầy đủ, xác nhận:

- Topic được tạo hoặc provision theo cách ứng dụng dự kiến.
- Tên topic và mapping từ logical target đã đúng.
- Partition count và replication factor phù hợp môi trường test.
- Các config retention, cleanup, message size và ISR được xác minh.
- Producer nhận broker acknowledgment và metadata đúng.
- Consumer đọc được record và deserialize đúng contract.
- Key và ordering được kiểm tra trong phạm vi một partition.
- Consumer group và offset được cô lập giữa các test.
- Headers, event ID, correlation ID và trace context được truyền đúng.
- Externalization publication lifecycle được kiểm tra riêng với consumer offset.
- Retry, DLT, replay và idempotency có test cho các failure case quan trọng.
- Test có timeout, cleanup và không phụ thuộc vào thứ tự chạy.
- CI dùng broker image tương thích và lưu đủ log khi thất bại.

Kiểm thử topic phải đi xa hơn việc xác nhận topic tồn tại. Khi xác minh cấu hình broker, record metadata, partition key, serialization, consumer offset và failure handling bằng broker cô lập, nhóm phát triển có bằng chứng rằng application events được chuyển qua Kafka đúng contract và có thể phục hồi khi gặp sự cố.

