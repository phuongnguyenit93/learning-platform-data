# Broker thật và broker giả

## Mục tiêu

Khi application event của Spring Modulith được externalize sang Kafka hoặc RabbitMQ, ứng dụng không chỉ cần kiểm tra listener nội bộ. Nó còn cần xác minh cách message được serialize, định tuyến, giao nhận, xác nhận và retry qua broker. Một bài test dùng mock có thể chạy rất nhanh nhưng không chứng minh broker thực tế hiểu cấu hình của ứng dụng. Ngược lại, dùng broker thật cho mọi unit test làm suite chậm và khó chẩn đoán.

**Broker thật và broker giả** là hai lựa chọn kiểm thử ở các mức khác nhau. Broker giả (mock/fake hoặc adapter thay thế) giúp kiểm tra logic ứng dụng nhanh và cô lập. Broker thật, thường chạy trong container dùng Testcontainers, giúp kiểm tra integration với giao thức, cấu hình và hành vi của sản phẩm broker.

Sau bài học, bạn có thể:

- Phân biệt mock, fake, embedded broker và broker thật chạy trong container.
- Chọn loại broker phù hợp với mục tiêu unit, integration, contract và end-to-end test.
- Kiểm thử Spring Modulith externalization với Kafka/RabbitMQ.
- Xác minh routing, serialization, acknowledgement, retry, ordering và dead-letter.
- Quản lý lifecycle container, test data và tính ổn định của test suite.
- Xây dựng chiến lược test cân bằng tốc độ, độ tin cậy và chi phí vận hành.

## 1. Vì sao cần nhiều loại test broker?

Một event có thể đi qua nhiều lớp trước khi consumer xử lý:

1. Module nghiệp vụ phát application event.
2. Spring Modulith ghi nhận publication tới listener/externalization được quản lý.
3. Integration adapter chuyển event thành message, chọn topic/queue, key và headers.
4. Serializer biến payload thành bytes.
5. Producer gửi message tới broker.
6. Broker lưu và định tuyến message.
7. Consumer nhận message, deserialize và gọi application API.
8. Consumer xác nhận message hoặc commit offset theo semantics của broker.

Mock một `KafkaTemplate` hoặc `RabbitTemplate` chỉ có thể xác minh ứng dụng đã gọi method với tham số mong đợi. Nó không chứng minh topic tồn tại, binding đúng, serializer tương thích, broker chấp nhận credentials hay acknowledgement hoạt động như dự kiến.

Mặt khác, nếu mục tiêu chỉ là kiểm tra một policy chọn routing key, khởi động broker thật là quá tốn kém. Test cần dùng đúng mức hạ tầng cho câu hỏi cần trả lời.

## 2. Phân biệt mock, fake, embedded và broker thật

Các thuật ngữ thường bị dùng lẫn nhau, nhưng mức độ mô phỏng khác nhau:

| Loại | Cách hoạt động | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| Mock | Thay dependency bằng đối tượng giả lập lời gọi và kết quả. | Nhanh; xác minh tương tác và nhánh lỗi. | Không thực thi giao thức hoặc semantics của broker. |
| Fake broker/adapter | Cài đặt đơn giản trong bộ nhớ, ví dụ queue nội bộ hoặc `InMemoryEventTransport`. | Có thể kiểm tra luồng gửi/nhận và logic consumer mà không cần hạ tầng. | Chỉ mô phỏng những semantics được lập trình; dễ khác broker thật. |
| Embedded broker | Broker hoặc thành phần broker chạy trong tiến trình test. | Có thể kiểm tra một phần giao thức và integration mà không cần container riêng. | Phiên bản/cấu hình có thể khác production; không phải broker thật trong mọi trường hợp. |
| Broker thật qua Testcontainers | Chạy image Kafka/RabbitMQ thực tế trong container. | Kiểm tra protocol, routing, serialization, ack, consumer group và cấu hình gần production. | Chậm hơn, cần Docker/container runtime và quản lý lifecycle. |
| Broker dùng chung ngoài môi trường test | Kết nối tới cluster test đã triển khai. | Kiểm tra hạ tầng triển khai và cấu hình thực tế. | Dễ phụ thuộc mạng, dữ liệu dùng chung, quyền truy cập và trạng thái môi trường. |

### Mock không phải broker giả đầy đủ

Ví dụ mock producer:

```java
@Test
void publishesOrderEventToExpectedTopic() {
    OrderEventPublisher publisher = new OrderEventPublisher(kafkaTemplate);

    publisher.publish(orderPlaced);

    verify(kafkaTemplate).send(
            eq("orders.events"),
            eq(orderPlaced.orderId().toString()),
            any(OrderPlacedIntegrationEvent.class));
}
```

Test này xác minh ứng dụng gọi `send` với topic và key dự kiến. Nó không xác minh broker đã nhận message hoặc consumer có thể đọc payload.

Fake broker có thể lưu message vào một queue trong bộ nhớ và cho consumer lấy ra. Fake hữu ích khi muốn kiểm tra orchestration, nhưng cần ghi rõ semantics được mô phỏng: FIFO, redelivery, visibility timeout, ack, partition hay DLQ. Nếu fake không mô phỏng một hành vi, test không thể chứng minh hành vi đó.

### Embedded broker

Với Kafka, Spring Kafka cung cấp hỗ trợ `EmbeddedKafkaBroker` cho một số kiểu integration test. Đây là broker được nhúng cho test, thuận tiện khi không muốn dùng container. Tuy nhiên, cấu hình và phiên bản embedded broker có thể khác cluster production; không nên xem kết quả embedded test là bằng chứng đầy đủ cho network, TLS, authentication, broker distribution hoặc deployment topology.

RabbitMQ không có lựa chọn embedded tương đương phổ biến trong Spring AMQP. Thường dùng mock/fake cho unit test và RabbitMQ container cho integration test cần broker thật.

## 3. Chọn chiến lược theo test level

Một test suite hiệu quả thường có nhiều tầng:

| Tầng test | Broker phù hợp | Điều cần chứng minh |
| --- | --- | --- |
| Unit test | Mock hoặc fake | Mapping, routing decision, policy retry, xử lý lỗi và logic ứng dụng. |
| Module test | Mock/fake ở ranh giới ngoài | Hành vi module và application event nội bộ trong Spring Modulith. |
| Adapter integration test | Embedded broker hoặc Testcontainers | Spring configuration, serializer/deserializer, topic/queue, binding và consumer. |
| Contract test | Schema/contract fixture; có thể kết hợp broker thật | Producer và consumer hiểu cùng event contract và version. |
| End-to-end test | Broker thật trong môi trường test hoặc container | Luồng externalization và consumer hoàn chỉnh, bao gồm ack/retry theo cấu hình. |
| Deployment/smoke test | Cluster test đã triển khai | TLS, authentication, ACL, network policy, topology và cấu hình vận hành. |

Không cần chạy mọi kịch bản lỗi trên broker thật. Hãy dùng test nhanh để bao phủ nhiều nhánh policy và dành broker thật cho các hành vi phụ thuộc vào implementation của broker.

### Quy tắc lựa chọn

- Nếu cần xác minh “ứng dụng có chọn đúng topic/key không?”, mock/fake thường đủ.
- Nếu cần xác minh “Spring Kafka/Rabbit listener có deserialize và bind đúng không?”, dùng embedded broker hoặc Testcontainers.
- Nếu cần xác minh “ack, redelivery, consumer group, partition hoặc DLQ hoạt động thế nào?”, ưu tiên broker thật.
- Nếu cần xác minh “TLS, SASL, certificate và ACL production-like có hoạt động không?”, cần môi trường broker được cấu hình tương ứng; broker container mặc định có thể chưa đủ.
- Nếu cần kiểm tra kiến trúc và nghiệp vụ nội bộ Spring Modulith, dùng module test và chỉ thay thế adapter ở ranh giới bên ngoài.

## 4. Tách broker adapter khỏi module nghiệp vụ

Module nghiệp vụ không nên phụ thuộc trực tiếp vào `KafkaTemplate`, `RabbitTemplate`, `ConsumerRecord` hoặc API riêng của broker. Hãy đặt transport ở adapter/integration layer và chuyển event thành application command hoặc integration contract.

Ví dụ cổng publish do ứng dụng định nghĩa:

```java
public interface EventTransport {
    void send(OutboundEvent event);
}

public record OutboundEvent(
        String destination,
        String key,
        String eventType,
        Object payload) {}
```

Production adapter có thể dùng Kafka:

```java
@Component
class KafkaEventTransport implements EventTransport {

    private final KafkaTemplate<String, Object> kafka;

    KafkaEventTransport(KafkaTemplate<String, Object> kafka) {
        this.kafka = kafka;
    }

    @Override
    public void send(OutboundEvent event) {
        kafka.send(event.destination(), event.key(), event.payload());
    }
}
```

Test có thể dùng fake:

```java
final class InMemoryEventTransport implements EventTransport {

    private final Queue<OutboundEvent> messages = new ConcurrentLinkedQueue<>();

    @Override
    public void send(OutboundEvent event) {
        messages.add(event);
    }

    List<OutboundEvent> messages() {
        return List.copyOf(messages);
    }
}
```

Fake này chỉ lưu message trong bộ nhớ; nó không mô phỏng persistence, partition, redelivery hoặc acknowledgement. Đó là chủ ý: dùng cho unit/module test, không dùng để thay thế integration test broker.

Với Spring Modulith, event nội bộ vẫn nên được phát bằng `ApplicationEventPublisher`. Cấu hình externalization/adapter chịu trách nhiệm đưa event cần tích hợp ra broker. Module không nên biết test đang dùng Kafka thật hay fake transport.

## 5. Kiểm thử với Kafka thật bằng Testcontainers

Testcontainers khởi chạy Kafka trong container trước test và dừng sau khi suite hoàn tất. Test sử dụng bootstrap server động do container cung cấp, nhờ đó có thể kiểm tra producer/consumer Spring với broker thật.

### Khai báo test dependency

Với Maven, dự án thường cần Testcontainers core và module Kafka phù hợp với version đang dùng, cùng test support của Spring Kafka nếu cần. Ví dụ các artifact phổ biến:

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>kafka</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
```

Version nên được quản lý nhất quán qua BOM/dependency management của dự án. Tên package/class và image Kafka tương thích phụ thuộc phiên bản Testcontainers; hãy chọn API hiện hành của version đã khóa trong build.

### Khởi chạy container

Ví dụ minh họa với API `KafkaContainer` của Testcontainers:

```java
@Testcontainers
@SpringBootTest
class KafkaEventIntegrationTests {

    @Container
    static final KafkaContainer kafka = new KafkaContainer(
            DockerImageName.parse("confluentinc/cp-kafka:7.6.1"));

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.kafka.bootstrap-servers", kafka::getBootstrapServers);
    }

    @Autowired
    KafkaTemplate<String, Object> kafkaTemplate;

    @Test
    void sendsMessageToRealKafkaBroker() {
        kafkaTemplate.send("orders.events", "order-100", eventPayload);
        // Consumer/test probe xác nhận record đã được broker nhận và đọc được.
    }
}
```

Đây là skeleton; class/package constructor của Kafka container thay đổi theo dòng phiên bản Testcontainers. Dùng image được thư viện hỗ trợ và phiên bản phù hợp với Kafka client. Test cần tạo topic hoặc cấu hình auto-topic creation theo cách rõ ràng; không dựa vào cấu hình mặc định ngẫu nhiên của máy developer.

`@DynamicPropertySource` đăng ký bootstrap server sau khi container khởi động. Nếu dùng Spring context cache, cần bảo đảm container có lifecycle ổn định trong suốt thời gian context dùng property đó. Không dừng container trước khi các listener/executor của Spring context hoàn tất.

### Kiểm tra producer và consumer

Một integration test có giá trị nên gửi message qua producer thật và đọc message qua consumer thật, thay vì chỉ verify method `send`:

```java
@Test
void publishesAndConsumesOrderEvent() {
    kafkaTemplate.send("orders.events", "order-100", eventPayload);

    ConsumerRecord<String, OrderPlacedIntegrationEvent> record =
            testConsumer.receive(Duration.ofSeconds(10));

    assertThat(record.key()).isEqualTo("order-100");
    assertThat(record.value().orderId()).isEqualTo(orderId);
}
```

`testConsumer` ở đây là consumer test được cấu hình với deserializer phù hợp. Cần subscribe trước khi gửi message, dùng consumer group/topic riêng cho test và commit/close consumer đúng cách. Không dùng cùng group ID cố định cho nhiều test chạy song song vì record có thể được chia cho test khác.

### Embedded Kafka hay Testcontainers?

`EmbeddedKafkaBroker` có thể phù hợp với test Spring Kafka cần chạy nhanh và kiểm tra binding cơ bản. Testcontainers phù hợp hơn khi cần dùng broker image cụ thể, cấu hình gần production, kiểm tra protocol/network hoặc chia sẻ cách dựng hạ tầng giữa nhiều loại broker. Hai cách bổ sung nhau; chọn theo hành vi cần chứng minh.

## 6. Kiểm thử với RabbitMQ thật bằng Testcontainers

RabbitMQ container cho phép kiểm tra exchange, queue, binding, routing key, acknowledgement và redelivery với broker thật.

### Khởi chạy RabbitMQ container

Ví dụ với `RabbitMQContainer`:

```java
@Testcontainers
@SpringBootTest
class RabbitEventIntegrationTests {

    @Container
    static final RabbitMQContainer rabbit = new RabbitMQContainer(
            DockerImageName.parse("rabbitmq:3.13-management"));

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }
}
```

Artifact Testcontainers RabbitMQ và API của `RabbitMQContainer` cần khớp version đã chọn. Nếu production dùng plugin, exchange type, quorum queue, TLS hoặc policy riêng, hãy cấu hình container/test broker tương ứng; image mặc định không tự phản ánh toàn bộ production topology.

### Kiểm tra routing và acknowledgement

Test nên khai báo exchange, queue và binding rõ ràng. Sau đó publish message qua `RabbitTemplate` và xác nhận message tới đúng queue. Để kiểm tra ack/requeue, có thể cấu hình listener test cố ý thất bại lần đầu rồi thành công ở lần giao tiếp theo; xác minh số lần xử lý và trạng thái cuối.

Không chỉ kiểm tra queue depth ngay sau publish vì message có thể chưa được route hoặc consumer đã lấy message. Dùng consumer probe/latch và kiểm tra kết quả xử lý cuối cùng.

## 7. Kiểm tra Spring Modulith externalization

`@ApplicationModuleTest` phù hợp để kiểm tra module nội bộ và event listener trong Spring Modulith. Broker integration test cần kiểm tra phần externalization qua transport.

Luồng kiểm thử end-to-end có thể là:

1. Gọi application service trong module nguồn.
2. Transaction commit và event được publish.
3. Spring Modulith ghi nhận publication theo cấu hình Event Publication Registry.
4. Externalization adapter serialize event và gửi tới Kafka/RabbitMQ.
5. Test consumer nhận message từ broker thật.
6. Xác minh event type, payload, key, headers và correlation metadata.
7. Nếu có consumer ứng dụng, xác minh consumer xử lý message và side effect được commit.

Ví dụ kiểm thử có thể kích hoạt use case thay vì gọi `KafkaTemplate` trực tiếp:

```java
@SpringBootTest
class OrderExternalizationTests {

    @Autowired
    OrderApplicationService orders;

    @Autowired
    TestKafkaConsumer probe;

    @Test
    void externalizesOrderPlacedAfterCommit() {
        orders.place(validCommand);

        ConsumerRecord<String, OrderPlacedIntegrationEvent> record =
                probe.awaitRecord(Duration.ofSeconds(10));

        assertThat(record.value().orderId()).isNotNull();
    }
}
```

`TestKafkaConsumer` là helper của test, không phải API Spring Modulith. Test cần chờ transaction commit và publication/externalization hoàn tất; nếu listener hoặc publisher bất đồng bộ, dùng timeout và probe có đồng bộ hóa. Không dùng `Thread.sleep()`.

### Event Publication Registry không phải broker

Event Publication Registry theo dõi publication tới listener và trạng thái hoàn tất trong Spring Modulith. Broker đảm nhận vận chuyển/lưu message theo semantics của Kafka hoặc RabbitMQ. Hai thành phần có trách nhiệm khác nhau:

| Thành phần | Điều cần kiểm tra |
| --- | --- |
| Event Publication Registry | Publication được ghi nhận, hoàn tất hoặc còn incomplete đúng theo listener/externalization. |
| Broker | Message được publish, route, lưu, giao lại và acknowledge đúng. |
| Consumer | Deserialize, idempotency và side effect nghiệp vụ đúng. |

Một test broker thành công không tự chứng minh registry phục hồi đúng sau crash. Một test registry thành công cũng không chứng minh broker đã nhận message. Với yêu cầu độ tin cậy cao, cần test crash window và duplicate ở từng ranh giới.

## 8. Các hành vi nên kiểm tra trên broker thật

Không phải mọi hành vi đều cần broker thật, nhưng các semantics phụ thuộc broker nên có integration test:

| Hành vi | Vì sao cần broker thật? | Điều cần xác minh |
| --- | --- | --- |
| Topic/queue và routing | Cấu hình broker quyết định message đi đâu. | Message đến đúng destination và không lọt queue khác. |
| Serialization/deserialization | Serializer/deserializer phải tương thích wire format. | Consumer đọc được payload và metadata. |
| Kafka key/partition | Partitioner và topic metadata quyết định phân phối. | Key cùng aggregate được route theo chiến lược đã chọn. |
| Consumer group/rebalance | Đây là semantics của Kafka group coordinator. | Partition assignment, restart và xử lý lại không mất message. |
| RabbitMQ ack/requeue | Broker quản lý delivery state và redelivery. | Nack/requeue, manual ack và redelivery đúng policy. |
| Retry/DLQ | Binding, retry topic/queue và dead-letter policy do broker thực thi. | Message chuyển đúng route, có metadata cần thiết. |
| Persistence/durability | Queue/topic, replication và broker config ảnh hưởng durability. | Message tồn tại theo cấu hình khi consumer tạm dừng hoặc broker restart. |
| TLS/authentication/ACL | Cấu hình kết nối và quyền phụ thuộc broker. | Kết nối hợp lệ thành công; identity/quyền sai bị từ chối. |
| Ordering | Partition/queue và concurrency ảnh hưởng thứ tự. | Thứ tự trong phạm vi được cam kết và cách consumer xử lý song song. |

Testcontainer mặc định có thể chạy một broker đơn lẻ, không phản ánh cluster nhiều node, replication, failover hoặc network partition production. Những hành vi đó cần môi trường test topology phù hợp hoặc test chuyên biệt.

## 9. Kiểm thử lỗi và khả năng phục hồi

Broker integration test nên có cả nhánh thành công và lỗi:

- Broker không sẵn sàng lúc ứng dụng khởi động.
- Broker dừng hoặc mất kết nối sau khi ứng dụng đã chạy.
- Producer timeout hoặc nhận lỗi publish.
- Consumer chết sau khi nhận message nhưng trước acknowledgement.
- Consumer xử lý xong database transaction nhưng ack thất bại, dẫn tới redelivery.
- Message sai schema hoặc không deserialize được.
- Queue/topic hoặc binding không tồn tại.
- Retry hết ngân sách và message chuyển sang DLQ/quarantine.
- Consumer restart/rebalance trong khi còn message đang xử lý.

Mục tiêu không phải kiểm tra mọi lỗi bằng một test dài. Chia thành test nhỏ, cô lập nguyên nhân và đặt timeout rõ ràng. Dùng test broker thật cho hành vi transport; dùng fake hoặc unit test cho các nhánh policy dễ tạo lỗi xác định.

### Idempotency và duplicate

Kafka/RabbitMQ và ứng dụng có thể giao message theo at-least-once tùy cấu hình. Nếu consumer commit side effect rồi chết trước ack/offset commit, message có thể được giao lại. Test cần chứng minh cùng `messageId` không tạo side effect lần hai.

Một pattern phổ biến là ghi inbox/idempotency record cùng transaction với thay đổi nghiệp vụ. Với side effect tới hệ thống ngoài, dùng idempotency key được hệ thống đích hỗ trợ hoặc outbox/saga. Không khẳng định exactly-once end-to-end chỉ vì broker có transaction hoặc producer idempotence.

### Retry và dead-letter

Kiểm tra retry bằng lỗi có thể phục hồi, ví dụ listener fail một lần rồi thành công. Kiểm tra DLQ bằng lỗi không thể retry hoặc hết retry budget. Xác minh payload gốc, message ID, error metadata và correlation ID vẫn truy xuất được.

Không để test retry phụ thuộc thời gian chờ dài. Có thể cấu hình backoff nhỏ riêng cho test, nhưng vẫn giữ cơ chế retry/ack thật cần kiểm tra. Tránh dùng production retry delay trong test suite.

## 10. Test data, isolation và lifecycle container

Test broker có thể chạy song song và chia sẻ container. Nếu topic, queue hoặc consumer group dùng tên cố định, test có thể đọc nhầm message của nhau.

Các nguyên tắc:

- Dùng topic/queue hoặc routing key riêng cho từng test class/test run khi cần.
- Dùng consumer group ID riêng để tránh record bị chia cho test khác.
- Subscribe consumer trước khi publish để tránh bỏ lỡ record trong một số cấu hình.
- Drain/cleanup queue và đóng consumer/channel sau test.
- Không dùng static mutable probe chia sẻ giữa test chạy song song.
- Tạo event ID và business key riêng cho từng test.
- Chờ listener/consumer hoàn tất trước khi đóng context/container.
- Giữ container sống lâu bằng static container hoặc shared lifecycle phù hợp với Spring context cache.

### Container reuse

Có thể tái sử dụng container giữa nhiều test để giảm thời gian khởi động, nhưng phải kiểm soát dữ liệu và topology. Reuse không được làm test phụ thuộc vào message còn sót từ lần chạy trước. Nếu bật reuse trong môi trường developer, CI vẫn cần đảm bảo mỗi test run tạo namespace/topic/queue riêng hoặc cleanup đầy đủ.

### Docker và môi trường CI

Testcontainers cần container runtime tương thích và quyền truy cập daemon. CI cần cấu hình Docker socket/remote daemon và giới hạn tài nguyên phù hợp. Nếu môi trường CI không có Docker, có thể chạy unit/module tests bằng fake và tách broker integration suite sang job có container runtime. Không được coi việc bỏ qua toàn bộ broker test là tương đương với test đã chạy thành công.

## 11. Bảo mật và cấu hình gần production

Broker container mặc định thường dùng cấu hình đơn giản để test nhanh. Nếu production yêu cầu TLS, mTLS, SASL, ACL hoặc credentials riêng, cần có test profile/container config kiểm tra các lớp này.

- Dùng secret test giả lập, không đưa credential production vào test.
- Kiểm tra client xác minh certificate/hostname khi dùng TLS.
- Kiểm tra identity không có quyền publish/consume bị từ chối.
- Cấu hình topic/queue permission theo service account.
- Không log payload nhạy cảm hoặc credentials trong test failure.
- Giữ image version rõ ràng để kết quả ổn định và có thể tái lập.

Không dùng image `latest` cho suite cần tái lập. Pin version broker và ghi rõ khác biệt với production. Cập nhật image có chủ đích để phát hiện thay đổi behavior thay vì để test thay đổi ngẫu nhiên theo thời gian.

## 12. Những lỗi kiểm thử thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng mock rồi kết luận broker integration đúng | Không kiểm tra protocol, routing hay ack. | Bổ sung integration test với broker thật cho semantics phụ thuộc broker. |
| Dùng broker thật cho mọi unit test | Suite chậm và khó xác định lỗi logic. | Dùng mock/fake cho policy và logic thuần. |
| Fake mô phỏng FIFO nhưng production có concurrency | Test không phát hiện ordering issue. | Test thứ tự trên broker/consumer thật theo yêu cầu. |
| Topic/queue dùng chung giữa test | Test đọc message của test khác. | Namespace riêng và cleanup rõ ràng. |
| Consumer subscribe sau khi publish | Test có thể bỏ lỡ record tùy cấu hình. | Subscribe và xác nhận assignment trước khi gửi. |
| Chỉ verify `send()` | Không biết broker có nhận và consumer có đọc được. | Publish rồi consume qua broker thật. |
| Không test redelivery | Side effect có thể bị lặp khi ack thất bại. | Failure injection và inbox/idempotency. |
| Dùng image `latest` | Test thay đổi theo lần chạy. | Pin image version. |
| Container dừng trước Spring context | Listener còn chạy nhưng broker đã đóng. | Quản lý lifecycle container/context đúng thứ tự. |
| Testcontainer đơn node được xem như cluster production | Bỏ sót replication/failover/topology. | Dùng topology test chuyên biệt cho các yêu cầu đó. |

## 13. Quy trình áp dụng

Khi xây dựng test cho broker integration của Spring Modulith:

1. Xác định câu hỏi test và chọn mock, fake, embedded broker hay broker thật.
2. Giữ unit/module test tập trung vào nghiệp vụ, mapping và policy.
3. Tạo adapter riêng cho Kafka/RabbitMQ để module không phụ thuộc API transport.
4. Dùng Testcontainers hoặc embedded broker cho integration test cần xác minh broker behavior.
5. Cấu hình topic/queue, binding, serializer, consumer group và bootstrap endpoint rõ ràng.
6. Kích hoạt use case/module event khi kiểm tra Spring Modulith externalization, thay vì chỉ gọi producer adapter.
7. Kiểm tra publish/consume, routing, key, headers, ack, retry, ordering và DLQ theo semantics cần bảo đảm.
8. Kiểm tra duplicate, crash window và idempotency ở consumer.
9. Cô lập topic/queue/group ID, quản lý container lifecycle và cleanup test data.
10. Tách suite cần Docker khỏi unit/module test nhanh và theo dõi rõ suite nào đã chạy.

Broker giả giúp kiểm tra logic nhanh và có kiểm soát; broker thật giúp phát hiện khác biệt ở protocol, routing, acknowledgement và cấu hình hạ tầng. Kết hợp đúng hai loại test giúp ứng dụng Spring Modulith giữ được tốc độ phản hồi của unit/module test và vẫn có bằng chứng đáng tin cậy cho luồng application event đi qua Kafka hoặc RabbitMQ.
