# Kiểm thử @KafkaListener

`@KafkaListener` chạy trên listener container và tiêu thụ record bất đồng bộ. Vì vậy, kiểm thử listener không chỉ là gọi một phương thức Java rồi xác minh kết quả. Một bài kiểm thử tích hợp cần xác nhận Spring tạo đúng container, consumer kết nối đúng broker/topic, deserialize payload đúng kiểu, listener được gọi, xử lý nghiệp vụ hoàn tất và offset được quản lý theo cấu hình.

Nên chia kiểm thử thành nhiều lớp. Unit test kiểm tra logic listener nhanh mà không cần Kafka. Integration test dùng `@EmbeddedKafka` để kiểm tra listener container và Kafka client trong cùng Spring context. Testcontainers phù hợp khi cần broker gần môi trường production hoặc cần kiểm thử nhiều dependency cùng lúc. Với mọi bài kiểm thử bất đồng bộ, hãy đợi một điều kiện có ý nghĩa như `CountDownLatch`, `BlockingQueue` hoặc Awaitility; không dùng `Thread.sleep()` để đoán listener đã chạy xong.

## 1. Kiểm thử những gì ở một @KafkaListener?

Một listener có nhiều lớp hành vi có thể lỗi độc lập:

| Lớp cần kiểm tra | Câu hỏi cần trả lời | Cách kiểm thử phù hợp |
|---|---|---|
| Logic nghiệp vụ | Với event này, service có cập nhật đúng dữ liệu không? | Unit test gọi trực tiếp method/service |
| Spring wiring | Listener có được phát hiện và đăng ký đúng không? | Spring context test |
| Consumer configuration | Topic, group ID, deserializer và ack mode có đúng không? | Integration test với broker |
| Serialization | Producer/consumer có cùng contract payload không? | Gửi record thật và xác minh object nhận được |
| Header/metadata | Key, partition, offset, timestamp và header có đúng không? | Kiểm tra `ConsumerRecord` hoặc tham số listener |
| Error handling | Retry, recoverer và DLT có chạy theo chính sách không? | Integration test với lỗi có kiểm soát |
| Offset/acknowledgment | Record có được commit sau khi xử lý theo đúng AckMode không? | Kiểm tra committed offset hoặc hành vi redelivery |
| Batch/concurrency | Batch có đúng phần tử, consumer assignment và xử lý song song không? | Broker nhiều partition và listener batch |
| Lifecycle | Container có start/stop và shutdown đúng không? | Kiểm tra registry/container state |

Không cần dùng broker thật cho mọi test. Hãy chọn tầng kiểm thử theo hành vi cần chứng minh: logic thuần Java thì gọi trực tiếp; hành vi phụ thuộc Kafka client, broker, partition hoặc offset thì cần broker thử nghiệm.

## 2. Unit test: gọi trực tiếp method listener

Unit test giúp xác minh listener chuyển payload và metadata sang service đúng cách. Test này không khởi động Spring container và không chứng minh consumer có thể đọc Kafka.

Listener:

```java
@Component
public class OrderCreatedListener {

    private final OrderService orderService;

    public OrderCreatedListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "orderCreatedListener",
            topics = "${app.kafka.orders-topic}",
            groupId = "${spring.kafka.consumer.group-id}")
    public void onMessage(ConsumerRecord<String, OrderCreated> record) {
        orderService.handle(
                record.value(),
                record.key(),
                record.partition(),
                record.offset());
    }
}
```

Kiểu payload minh họa:

```java
public record OrderCreated(String eventId, String orderId, long amount) {
}
```

Unit test:

```java
@ExtendWith(MockitoExtension.class)
class OrderCreatedListenerTest {

    @Mock
    private OrderService orderService;

    @InjectMocks
    private OrderCreatedListener listener;

    @Test
    void forwardsPayloadAndKafkaMetadata() {
        OrderCreated event = new OrderCreated("evt-42", "O-42", 120_000);
        ConsumerRecord<String, OrderCreated> record =
                new ConsumerRecord<>("orders", 1, 27L, "O-42", event);

        listener.onMessage(record);

        verify(orderService).handle(event, "O-42", 1, 27L);
    }
}
```

Test này nhanh và ổn định. Nó có thể phát hiện listener truyền nhầm key, partition, offset hoặc payload. Tuy nhiên, nó không kiểm tra `@KafkaListener` có được Spring đăng ký, broker có topic hay JSON deserializer có hoạt động. Những phần đó cần integration test.

Nếu listener chỉ nhận POJO thay vì `ConsumerRecord`, unit test có thể gọi method bằng object trực tiếp. Khi listener có `Acknowledgment`, header hoặc batch payload, truyền mock/fixture tương ứng và xác minh hành vi của method.

## 3. Thêm dependency kiểm thử

Với Maven, Spring Boot test thường đã cung cấp JUnit Jupiter, Mockito và AssertJ. Thêm Spring Kafka test utilities trong test scope:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <scope>test</scope>
</dependency>
```

Với Gradle:

```groovy
testImplementation 'org.springframework.kafka:spring-kafka-test'
testImplementation 'org.awaitility:awaitility'
```

Hãy để Spring Boot dependency management hoặc Spring Kafka BOM chọn version tương thích với `spring-kafka` trong ứng dụng. Không tự thêm một version `spring-kafka-test` khác với runtime library.

Ở các dòng Spring Boot mới có thể dùng starter test riêng cho Kafka nếu phiên bản đang chạy cung cấp `spring-boot-starter-kafka-test`. Với dự án Boot 3.x, dependency `spring-kafka-test` trực tiếp vẫn là lựa chọn phổ biến. Kiểm tra dependency management của dự án trước khi thêm starter mới.

## 4. Integration test với @EmbeddedKafka

`@EmbeddedKafka` tạo broker Kafka phục vụ test trong cùng tiến trình kiểm thử. Đây là cách thuận tiện để kiểm tra `@KafkaListener`, `KafkaTemplate`, serialization, topic, partition và offset mà không cần một Kafka server cài riêng.

Ví dụ test Spring Boot:

```java
@SpringBootTest(properties = {
        "app.kafka.orders-topic=orders.listener.it",
        "spring.kafka.consumer.group-id=orders-listener-it",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.springframework.kafka.support.serializer.JsonSerializer",
        "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer",
        "spring.kafka.consumer.properties.spring.json.trusted.packages=com.example.orders",
        "spring.kafka.consumer.properties.spring.json.value.default.type=com.example.orders.OrderCreated"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "orders.listener.it",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderCreatedListenerIT {

    @Autowired
    private KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @MockitoBean
    private OrderService orderService;

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @BeforeEach
    void waitForAssignment() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderCreatedListener");
        assertThat(container).isNotNull();
        ContainerTestUtils.waitForAssignment(container, 1);
    }

    @Test
    void consumesEventAndCallsService() throws Exception {
        OrderCreated event = new OrderCreated("evt-42", "O-42", 120_000);

        kafkaTemplate.send("orders.listener.it", "O-42", event)
                .get(10, TimeUnit.SECONDS);

        await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
                verify(orderService).handle(
                        eq(event), eq("O-42"), eq(0), anyLong()));
    }
}
```

Trong ví dụ, `@SpringBootTest` khởi tạo application context thật, `@EmbeddedKafka` cung cấp broker và topic, còn `@MockitoBean` thay `OrderService` bằng mock để quan sát listener gọi service. `@MockitoBean` thuộc Spring Framework 6.2 trở lên; với dự án cũ hơn, có thể dùng `@MockBean` của Spring Boot test nếu phiên bản còn hỗ trợ.

`bootstrapServersProperty` ánh xạ địa chỉ broker embedded vào `spring.kafka.bootstrap-servers`. Từ Spring Kafka 3.0.10, property này mặc định đã được ánh xạ cho Spring Boot, nhưng khai báo tường minh giúp test dễ hiểu và tương thích với các phiên bản trước đó có thuộc tính này.

`KafkaTemplate.send(...).get(...)` chỉ xác nhận producer đã nhận kết quả gửi từ broker. Nó không chứng minh listener đã xử lý xong. `Awaitility` chờ lời gọi service xảy ra trong thời hạn, thay vì giả định listener hoàn tất ngay sau khi `send()` trả về.

## 5. Đợi listener được assign partition trước khi gửi

Một test có thể gửi message ngay sau khi Spring context khởi động, trong khi listener container vẫn đang tham gia group và chờ partition assignment. Nếu consumer dùng `auto.offset.reset=latest`, message được gửi trước khi consumer bắt đầu đọc có thể không được nhận như test mong đợi.

Có thể lấy container từ `KafkaListenerEndpointRegistry` và chờ assignment:

```java
@Autowired
private KafkaListenerEndpointRegistry registry;

@BeforeEach
void waitForListenerAssignment() {
    MessageListenerContainer container =
            registry.getListenerContainer("orderCreatedListener");
    assertThat(container).isNotNull();
    ContainerTestUtils.waitForAssignment(container, 1);
}
```

`1` là số partition mà listener dự kiến được assign trong test này. Nếu topic có nhiều partition hoặc container concurrency lớn hơn một, hãy tính số partition assignment thực tế cho container thay vì luôn dùng 1.

Chờ assignment giúp loại bỏ race giữa test producer và consumer startup. Ngoài ra, cấu hình `auto-offset-reset=earliest` có thể giúp group test mới đọc record đã tồn tại trước lần poll đầu tiên. Hãy chọn chính sách offset theo mục tiêu test; không dùng `earliest` để che giấu việc listener chưa được start hoặc chưa có assignment.

## 6. Test listener với CountDownLatch hoặc BlockingQueue

Không phải test nào cũng cần Mockito. Có thể tạo một test sink để nhận record từ listener và đợi bằng `BlockingQueue`:

```java
@Component
public class CapturingListener {

    private final BlockingQueue<ConsumerRecord<String, String>> received;

    public CapturingListener(
            BlockingQueue<ConsumerRecord<String, String>> received) {
        this.received = received;
    }

    @KafkaListener(topics = "listener.capture.it", groupId = "capture-it")
    public void listen(ConsumerRecord<String, String> record) {
        received.offer(record);
    }
}
```

Trong test configuration, cung cấp queue:

```java
@TestConfiguration
class ListenerTestConfiguration {

    @Bean
    BlockingQueue<ConsumerRecord<String, String>> receivedRecords() {
        return new LinkedBlockingQueue<>();
    }
}
```

Test gửi record và lấy kết quả:

```java
template.send("listener.capture.it", "key-1", "hello")
        .get(10, TimeUnit.SECONDS);

ConsumerRecord<String, String> received =
        receivedRecords.poll(10, TimeUnit.SECONDS);

assertThat(received).isNotNull();
assertThat(received.key()).isEqualTo("key-1");
assertThat(received.value()).isEqualTo("hello");
```

Queue làm cho kết quả bất đồng bộ dễ quan sát. Nếu test nhiều record, hãy dùng queue mới cho từng test hoặc dọn queue trước mỗi lần chạy để record cũ không làm test pass nhầm. Test sink chỉ phù hợp làm fixture; không nên đưa queue kiểm thử vào production service chỉ để phục vụ test.

## 7. KafkaTestUtils để tạo consumer và đọc record

`spring-kafka-test` cung cấp `KafkaTestUtils` để tạo consumer/producer properties và lấy record từ broker embedded.

Ví dụ đọc record độc lập:

```java
Map<String, Object> props = KafkaTestUtils.consumerProps(
        "orders-verifier", "false", embeddedKafka);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

ConsumerFactory<String, String> consumerFactory =
        new DefaultKafkaConsumerFactory<>(props);

try (Consumer<String, String> consumer = consumerFactory.createConsumer()) {
    embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders.listener.it");

    kafkaTemplate.send("orders.listener.it", "O-42", "payload")
            .get(10, TimeUnit.SECONDS);

    ConsumerRecord<String, String> record =
            KafkaTestUtils.getSingleRecord(consumer, "orders.listener.it");

    assertThat(record.key()).isEqualTo("O-42");
    assertThat(record.value()).isEqualTo("payload");
}
```

`consumerProps(...)` từ Spring Kafka 2.5 đặt `auto.offset.reset=earliest` theo mặc định để consumer test đọc được record đã gửi trước khi nó bắt đầu. Nếu muốn hành vi `latest`, hãy ghi đè property sau khi gọi helper.

`consumeFromAnEmbeddedTopic(...)` mặc định seek partition được assign về đầu topic. Có overload cho phép chọn `seekToEnd`; dùng đúng lựa chọn để tránh đọc record cũ còn lại từ test trước. `getSingleRecord(...)` phù hợp khi mong đợi chính xác một record; `getRecords(...)` phù hợp khi cần kiểm tra nhiều record trong một lần poll.

Để tránh cross-talk, nên dùng topic riêng cho từng test hoặc từng test class. Nếu tái sử dụng topic, phải quản lý offset, group ID và vị trí seek rõ ràng.

## 8. Kiểm tra payload và metadata của ConsumerRecord

Nếu listener nhận `ConsumerRecord<K,V>`, có thể xác minh toàn bộ thông tin mà Kafka giao cho listener:

```java
assertThat(record.topic()).isEqualTo("orders.listener.it");
assertThat(record.key()).isEqualTo("O-42");
assertThat(record.partition()).isEqualTo(0);
assertThat(record.offset()).isGreaterThanOrEqualTo(0L);
assertThat(record.value().orderId()).isEqualTo("O-42");
assertThat(record.timestamp()).isPositive();
```

Nếu producer gửi header nghiệp vụ:

```java
ProducerRecord<String, OrderCreated> outgoing =
        new ProducerRecord<>("orders.listener.it", "O-42", event);
outgoing.headers().add(
        "trace-id", "trace-123".getBytes(StandardCharsets.UTF_8));
kafkaTemplate.send(outgoing).get(10, TimeUnit.SECONDS);
```

Listener có thể đọc header bằng `record.headers().lastHeader("trace-id")`. Test nên xác minh header tồn tại, byte value đúng và xử lý trường hợp header vắng mặt. Không giả định mọi header đều là UTF-8 string; các header số như partition/offset của Spring Kafka có encoding riêng.

## 9. Kiểm tra deserialization và JSON conversion

Một test chỉ gửi string và nhận string không kiểm tra được JSON deserializer. Nếu production dùng `JsonSerializer`/`JsonDeserializer`, hãy gửi object thật và xác minh listener nhận đúng kiểu, field và giá trị.

Consumer JSON thường cần cấu hình trusted packages hoặc type mapping phù hợp:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders
        spring.json.value.default.type: com.example.orders.OrderCreated
```

Test nên có payload hợp lệ, field optional bị thiếu, field null, sai type và JSON malformed. Nếu dùng `ErrorHandlingDeserializer`, hãy kiểm tra listener/error handler nhận được exception header hoặc record đi vào DLT theo thiết kế. Lỗi deserialize xảy ra trước khi listener được gọi; không kiểm tra nó bằng cách chờ mock service trong listener được gọi.

Với Confluent Schema Registry, cần test thêm schema ID lookup, compatibility và registry availability. Embedded Kafka không tự cung cấp Schema Registry; dùng registry test container hoặc một môi trường Registry thử nghiệm riêng.

## 10. Kiểm thử retry và DLT

Để kiểm thử retry, tạo lỗi có thể tái hiện và backoff ngắn. Không dùng lỗi mạng ngẫu nhiên hoặc chờ hàng chục giây nếu có thể mô phỏng lỗi bằng service mock.

Ví dụ service thất bại một lần rồi thành công:

```java
AtomicInteger attempts = new AtomicInteger();

doAnswer(invocation -> {
    if (attempts.incrementAndGet() == 1) {
        throw new TransientOrderException("temporary failure");
    }
    return null;
}).when(orderService).handle(any(), anyString(), anyInt(), anyLong());
```

Gửi một record và dùng Awaitility đợi service được gọi lần thứ hai. Xác minh số lần gọi đúng với retry policy đã cấu hình. Nếu dùng `DefaultErrorHandler`, nhớ rằng số lần retry là số lần thử thêm sau lần xử lý đầu tiên; tổng số invocation bao gồm lần đầu và retry.

Để kiểm tra DLT:

1. Khai báo topic nguồn và topic DLT trong `@EmbeddedKafka`.
2. Cấu hình `DeadLetterPublishingRecoverer` cùng `DefaultErrorHandler` với retry count nhỏ.
3. Gửi record làm listener thất bại liên tục hoặc ném exception non-retryable.
4. Dùng consumer group riêng để đọc DLT.
5. Xác minh key/value, original topic/partition/offset và exception headers.
6. Xác minh offset nguồn chỉ được xem là recovered sau khi publish DLT thành công theo cấu hình.

Không chỉ assert log có dòng lỗi. DLT test phải chứng minh record thực sự được publish tới đúng topic và có đủ metadata để điều tra.

## 11. Kiểm tra batch listener

Nếu listener nhận batch, bật batch mode trên container factory và gửi nhiều record vào topic có số partition phù hợp. Test cần xác minh:

- Listener được gọi với collection đúng số phần tử.
- Thứ tự record trong từng partition được giữ.
- Metadata list có index khớp với payload.
- Batch có thể chứa record từ nhiều partition.
- `BatchListenerFailedException` chỉ đúng index khi một record thất bại.
- Error handler retry/recover đúng phần record còn lại.

Không giả định một lần `send()` sẽ tạo một batch listener invocation. Kafka consumer poll gom record theo tải, partition assignment và `max.poll.records`; số record trong một lần gọi có thể khác nhau. Để kiểm thử chắc chắn, gửi trước một nhóm record, chờ consumer nhận đủ số lượng bằng latch/queue và cấu hình batch listener với timeout phù hợp.

## 12. Kiểm tra acknowledgment và offset commit

Nếu listener dùng `AckMode.RECORD`, container commit tiến độ theo record sau khi listener xử lý thành công. Với `AckMode.BATCH`, commit thường diễn ra sau khi toàn batch được xử lý thành công. `MANUAL` và `MANUAL_IMMEDIATE` yêu cầu listener gọi `acknowledge()` theo đúng thời điểm.

Test manual acknowledgment nên chứng minh record chưa được xác nhận trước khi listener gọi ack và được commit sau khi ack. Có thể kiểm tra committed offset bằng `AdminClient` hoặc một consumer group verifier, nhưng cần chờ commit hoàn tất và phân biệt offset đã xử lý với offset kế tiếp cần đọc. Kafka commit offset thường lưu vị trí kế tiếp, nên nếu xử lý record offset 7 thành công thì committed offset thường là 8.

Với listener xử lý bất đồng bộ, không return trước khi công việc thực tế hoàn tất nếu container sẽ commit offset khi method return. Nếu task được đưa vào executor và listener kết thúc ngay, test có thể phát hiện offset đã tiến lên trong khi side effect chưa hoàn tất. Khi cần async processing, phải thiết kế acknowledgment/checkpoint phù hợp.

## 13. Kiểm tra concurrency và partition assignment

Để kiểm tra concurrency, tạo topic có nhiều partition và cấu hình listener container có concurrency lớn hơn một. Lấy container từ registry, đợi assignment hoàn tất và gửi record với key để phân bố dữ liệu qua partition.

Các điều cần xác minh:

- Số child consumer không vượt số partition hữu ích trong group.
- Mỗi partition chỉ được assign cho tối đa một consumer trong cùng group tại một thời điểm.
- Record cùng key đi vào partition mong muốn theo partitioner.
- Listener có thể xử lý song song giữa partition nhưng không phá thứ tự trong cùng partition nếu nghiệp vụ yêu cầu.
- Rebalance không làm mất record; duplicate delivery được xử lý idempotent.

Không dùng một topic một partition để kết luận concurrency 3 hoạt động đúng. Chỉ một consumer có thể nhận partition đó; các consumer còn lại không có partition để xử lý.

## 14. Kiểm thử listener với Testcontainers

`@EmbeddedKafka` rất tiện cho test nhanh, nhưng embedded broker vẫn có thể khác cấu hình Kafka production. Testcontainers khởi chạy Kafka trong Docker và phù hợp khi cần kiểm tra broker image/version, KRaft, network hoặc nhiều dependency cùng nhau.

Với Testcontainers 2.x, Kafka module cung cấp `org.testcontainers.kafka.KafkaContainer` cho image Apache Kafka. Ví dụ:

Thêm dependency test (và quản lý version bằng Testcontainers BOM của dự án):

```groovy
testImplementation 'org.testcontainers:testcontainers-kafka'
testImplementation 'org.testcontainers:junit-jupiter'
```

```java
@Testcontainers
@SpringBootTest
class OrderCreatedListenerContainerIT {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.kafka.bootstrap-servers", kafka::getBootstrapServers);
    }

    // Các test gửi record và xác minh listener như ví dụ EmbeddedKafka.
}
```

Chọn image Kafka tương thích với phiên bản broker production. Testcontainers cần Docker-compatible runtime và tự quản lý vòng đời container qua JUnit extension. Với Testcontainers 2.x, dùng package `org.testcontainers.kafka.KafkaContainer`; class cũ `org.testcontainers.containers.KafkaContainer` đã deprecated. Nếu dùng Confluent Kafka image, chọn `ConfluentKafkaContainer` tương ứng.

Testcontainers phù hợp với integration/system test chạy ít hơn nhưng có độ sát production cao hơn. Không nhất thiết thay toàn bộ `@EmbeddedKafka` bằng Docker; giữ embedded test nhanh và thêm một số test container cho các hành vi phụ thuộc môi trường thật.

## 15. MockConsumerFactory và MockProducerFactory

Kafka client cung cấp `MockConsumer` và `MockProducer`. Từ Spring Kafka 3.0.7, framework có `MockConsumerFactory` và `MockProducerFactory` để tích hợp các mock này với listener container và `KafkaTemplate`.

Chúng hữu ích khi cần kiểm tra container hoặc template mà không cần broker chạy. Tuy nhiên, mock không kiểm tra protocol broker, partition assignment thực, serialization wire format, group coordinator hoặc transaction thật.

Khi test concurrency, factory cần tạo consumer mới cho mỗi lần gọi. Không dùng cùng một `MockConsumer` instance cho nhiều child container. Với `MockProducer` transactional, cần gọi `initTransactions()` trước khi dùng transaction.

## 16. Tránh flaky test và race condition

Các nguyên nhân phổ biến khiến Kafka listener test lúc pass lúc fail:

- Gửi message trước khi listener container được start/assign.
- Dùng topic chung và đọc nhầm record từ test trước.
- Dùng group ID chung khiến offset cũ làm test bỏ qua record.
- Không đặt `auto.offset.reset` phù hợp khi group chưa có offset.
- Dùng `Thread.sleep()` với thời gian quá ngắn hoặc quá dài.
- Chờ producer send nhưng không chờ listener xử lý.
- Test song song trên cùng topic/group và tranh offset.
- Không đóng consumer do test tự tạo.
- Dùng embedded broker bị shutdown trước Spring context còn đang dùng nó.

Biện pháp:

1. Dùng topic và group ID riêng cho test hoặc test class.
2. Đợi listener assignment trước khi gửi khi test phụ thuộc startup timing.
3. Dùng `CompletableFuture.get`, `CountDownLatch`, `BlockingQueue` hoặc Awaitility với timeout hữu hạn.
4. Dọn queue/mock state giữa các test.
5. Đóng consumer/producer do test tự tạo bằng try-with-resources hoặc lifecycle hook.
6. Không chạy song song test chia sẻ cùng topic/group nếu chưa cô lập dữ liệu.
7. Quản lý embedded broker và Spring context lifecycle; cân nhắc `@DirtiesContext` theo khuyến nghị của Spring Kafka.
8. Không kết hợp global embedded broker và broker khai báo theo từng test class trong cùng suite nếu chưa kiểm soát system property dùng chung.

## 17. Test nhiều class với một embedded broker

Khởi động broker mới cho mỗi test class có thể làm suite chậm. Spring Kafka hỗ trợ chia sẻ `EmbeddedKafkaBroker` qua Spring test context cache hoặc dùng global embedded broker cho toàn JUnit test plan.

Nếu dùng một broker chung:

- Mỗi test nên dùng topic riêng hoặc có chiến lược seek/cleanup rõ ràng.
- Không chia sẻ group ID giữa test độc lập.
- Không giả định topic rỗng sau khi test trước kết thúc.
- Quản lý shutdown broker đúng thời điểm so với Spring context.
- Không kết hợp global embedded broker và `@EmbeddedKafka` theo class một cách tùy tiện vì chúng có thể dùng chung system properties.

Với global embedded broker, cấu hình `spring.kafka.global.embedded.enabled=true` trên JUnit Platform và cung cấp số broker, port, topic, partition theo nhu cầu. Tính năng này phù hợp với suite lớn nhưng cần quy ước cô lập topic/group nhất quán.

## 18. Kiểm tra bảo mật và cấu hình listener

Nếu production dùng SASL/SSL, test local embedded broker thường chạy plaintext. Vì vậy, nó không chứng minh credential, TLS truststore, ACL hoặc authorization hoạt động đúng.

Nên chia kiểm thử:

- Embedded Kafka: logic listener, payload, header, retry, DLT, offset và partition.
- Testcontainers hoặc broker test chuyên dụng: listener với Kafka image/version và security configuration gần production.
- Environment smoke test: xác minh SASL/SSL, ACL READ/DESCRIBE, group authorization và secret injection.

Không đưa secret production vào test. Dùng credential test có quyền tối thiểu và kiểm tra rằng listener bị từ chối khi thiếu quyền cần thiết.

## 19. Ma trận kiểm thử @KafkaListener

| Nhóm | Ca kiểm thử | Kỳ vọng |
|---|---|---|
| Startup | Listener ID hợp lệ, topic tồn tại | Container start và được assign partition |
| Delivery | Gửi một record hợp lệ | Listener xử lý đúng payload |
| Serialization | JSON hợp lệ và sai type | Deserialize đúng hoặc lỗi được chuyển tới error handler |
| Metadata | Key, partition, offset, timestamp, header | Listener nhận metadata đúng |
| Group | Hai consumer cùng group | Partition được chia theo assignment, không broadcast record cho từng member |
| Retry | Lỗi tạm thời rồi thành công | Listener được gọi lại theo retry policy |
| DLT | Lỗi hết retry hoặc non-retryable | Record xuất hiện ở DLT cùng metadata nguồn |
| Batch | Nhiều record trong một poll | Payload/header list đúng index |
| Partial batch failure | Một record lỗi tại index xác định | Retry/recover đúng phần còn lại |
| Ack | Manual acknowledgment | Offset commit sau thời điểm acknowledge |
| Concurrency | Nhiều partition, nhiều child consumer | Assignment và xử lý song song đúng thiết kế |
| Rebalance | Consumer rời/join group | Record không mất; duplicate được xử lý idempotent |
| Shutdown | Đóng context | Container dừng và consumer được đóng |
| Failure isolation | Broker hoặc downstream tạm thời unavailable | Test timeout hữu hạn, lỗi được quan sát rõ |

Không cần mọi dự án triển khai toàn bộ ma trận ở mọi module. Hãy chọn các ca tương ứng với tính năng listener thực sự sử dụng và giữ một số integration test đại diện cho đường đi quan trọng.

## 20. Troubleshooting test thất bại

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Test timeout chờ listener | Container chưa start/assignment hoặc sai topic/group | Kiểm tra registry ID, topic, group và `waitForAssignment` |
| Producer send thành công nhưng service mock chưa được gọi | Send ack không đồng nghĩa listener đã xử lý; deserialize có thể lỗi | Chờ bằng Awaitility và xem consumer logs/error handler |
| Consumer test không nhận record | Offset reset là `latest`, group đã có offset hoặc seek sai | Dùng group mới, cấu hình `earliest`, kiểm tra seek position |
| Nhận record từ test trước | Topic/group được dùng chung | Dùng topic riêng hoặc seek/cleanup rõ ràng |
| Listener nhận `byte[]`/`String` thay POJO | Deserializer hoặc message converter sai | Kiểm tra consumer factory và JSON type mapping |
| DLT không có record | Recoverer chưa gắn vào factory, số retry chưa hết hoặc DLT partition sai | Kiểm tra error handler, recoverer, topic và send result |
| Duplicate invocation | Redelivery, test song song hoặc side effect trước commit | Kiểm tra offset/ack và làm handler idempotent |
| Embedded broker shutdown race | Broker và Spring context có lifecycle không đồng bộ | Quản lý context cleanup và `@DirtiesContext` phù hợp |
| Testcontainers không start | Docker runtime/image/network không khả dụng | Kiểm tra Docker, image tag và container logs |
| Concurrency test chỉ có một consumer hoạt động | Topic có quá ít partition | Tạo đủ partition và đợi assignment |

Khi test fail, đọc log của listener container, consumer group và embedded broker trước khi tăng timeout. Timeout dài hơn không sửa được sai group ID, topic, deserializer hoặc offset reset.

## 21. Quy trình viết một integration test ổn định

1. Chọn một hành vi cần chứng minh, ví dụ listener chuyển `OrderCreated` vào service.
2. Tạo topic và group ID riêng cho test.
3. Khởi tạo `@EmbeddedKafka` hoặc Kafka Testcontainer.
4. Cấu hình Spring Boot bootstrap server, serializer/deserializer và listener properties.
5. Đợi container được assign partition nếu test phụ thuộc startup timing.
6. Gửi record bằng `KafkaTemplate` và chờ send future hoàn tất.
7. Chờ listener side effect bằng Awaitility, latch hoặc queue.
8. Assert payload, key, header, partition, offset và side effect cần thiết.
9. Nếu test lỗi, xác minh retry/DLT/offset theo policy thay vì chỉ kiểm tra log.
10. Đóng resource tự tạo và bảo đảm broker/context được cleanup.

## 22. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Gọi trực tiếp method là đã test `@KafkaListener` | Chỉ test logic method; không test container, broker, deserializer hoặc group |
| `KafkaTemplate.send()` hoàn tất nghĩa là listener xử lý xong | Future send xác nhận kết quả producer/broker; listener chạy bất đồng bộ |
| `Thread.sleep(1000)` là cách đợi listener | Dùng latch, queue, Awaitility hoặc consumer poll với timeout |
| Embedded Kafka giống hệt production | Embedded broker tốt cho integration test nhưng có thể khác image, security và topology production |
| `auto-offset-reset=earliest` luôn đọc lại mọi record | Chỉ áp dụng khi group không có committed offset hợp lệ; group cũ tiếp tục từ offset đã commit |
| Một partition đủ để test concurrency cao | Consumer hữu ích bị giới hạn bởi số partition được gán |
| MockConsumer kiểm tra được Kafka protocol | Mock không thay broker thật cho assignment, network, transaction và serialization wire format |
| Test pass chứng minh không có duplicate trong production | Cần test redelivery/idempotency và kiểm soát side effect |
| Test DLT chỉ cần xác minh exception được log | Cần đọc record từ DLT và kiểm tra metadata, key/value, routing |

## Checklist trước khi merge test @KafkaListener

- Có unit test cho logic listener/service quan trọng.
- Có integration test dùng broker cho hành vi phụ thuộc container/Kafka.
- Topic và group ID được cô lập giữa test.
- Listener assignment được chờ khi cần.
- Producer send future và listener completion được chờ riêng biệt.
- Không dùng `Thread.sleep()` để đồng bộ test.
- Serialization/deserialization và header được kiểm tra bằng record thực.
- Retry, DLT, batch và acknowledgment được test nếu ứng dụng sử dụng.
- Consumer/producer tự tạo được đóng đúng lifecycle.
- Embedded broker và Spring context không bị shutdown race.
- Testcontainers dùng image/version tương thích khi cần production parity.
- Timeout hữu hạn và log đủ thông tin để chẩn đoán lỗi.
- Test chứng minh idempotency hoặc redelivery behavior nếu listener tạo side effect.

Kiểm thử `@KafkaListener` cần kết hợp unit test cho logic và integration test cho container/broker behavior. `@EmbeddedKafka` cùng `KafkaTestUtils` giúp kiểm tra luồng Kafka nhanh trong test suite; Testcontainers giúp tăng độ sát với broker và dependency production. Khi cô lập topic/group, đợi assignment, chờ listener bằng tín hiệu bất đồng bộ và xác minh retry/offset/DLT theo contract, bài kiểm thử sẽ ổn định và phản ánh đúng cách listener vận hành.

## Tài liệu tham khảo

- [Spring for Apache Kafka – Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Boot – Apache Kafka Support and Testing with Embedded Kafka](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Testcontainers for Java – Kafka Module](https://java.testcontainers.org/modules/kafka/)
- [Testcontainers for Java – General Docker Environment Requirements](https://java.testcontainers.org/supported_docker_environment/)
