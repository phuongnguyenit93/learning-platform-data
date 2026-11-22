# Đợi record bằng Awaitility hoặc polling

Kafka xử lý message bất đồng bộ. Khi test gọi `KafkaTemplate.send()`, producer gửi record tới broker; sau đó consumer có thể cần thêm thời gian để poll, deserialize, chạy listener, cập nhật database và commit offset. Vì vậy, việc gửi thành công không có nghĩa toàn bộ luồng xử lý đã hoàn tất ngay tại thời điểm test tiếp tục.

Trong integration test, không nên dùng `Thread.sleep()` cố định để đoán lúc record sẽ đến. Một khoảng ngủ ngắn có thể làm test thất bại trên CI chậm; một khoảng ngủ dài làm suite chậm mà vẫn không chứng minh được điều kiện mong muốn. Thay vào đó, hãy **đợi một điều kiện có ý nghĩa với timeout hữu hạn**. Awaitility phù hợp khi cần chờ trạng thái cuối cùng hoặc side effect; polling trực tiếp phù hợp khi test cần đọc Kafka record bằng một KafkaConsumer do test quản lý.

Bài học thuộc chương **Kiểm thử** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách đợi record và kết quả xử lý bất đồng bộ bằng Awaitility hoặc polling, đồng thời tránh race condition, timeout vô hạn và test không ổn định.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích vì sao Kafka integration test cần chờ kết quả bất đồng bộ.
- Phân biệt producer send acknowledgement với consumer listener completion.
- Dùng Awaitility để đợi listener, database state, offset hoặc DLT record.
- Dùng collection/thread-safe holder để truyền kết quả từ listener thread sang test thread.
- Dùng BlockingQueue hoặc CountDownLatch với timeout hữu hạn.
- Poll KafkaConsumer theo deadline thay vì ngủ cố định.
- Chờ consumer assignment trước khi phát record khi cần kiểm soát thứ tự test.
- Phân biệt polling dữ liệu với polling một điều kiện.
- Chọn timeout và poll interval hợp lý.
- Kiểm thử retry, DLT, committed offset và side effect mà không tạo flaky test.
- Cô lập topic, group ID và trạng thái giữa các test.

## 1. Vì sao phải đợi trong Kafka test?

Một luồng producer-consumer thường có nhiều bước độc lập:

~~~mermaid
sequenceDiagram
    participant T as Test
    participant P as KafkaTemplate
    participant K as Kafka broker
    participant C as Consumer
    participant S as Listener service
    T->>P: send(record)
    P->>K: Produce request
    K-->>P: Broker acknowledgement
    P-->>T: Send future completes
    K-->>C: Record available
    C->>S: Invoke listener
    S-->>C: Processing completes
    Note over T,S: Test may need to wait for this result
~~~

Future của producer hoàn tất khi broker xác nhận kết quả gửi theo cấu hình producer. Nó không chờ consumer nhận record, listener hoàn thành hay database cập nhật.

Vì vậy, test cần xác định rõ mình đang đợi điều gì:

- Broker đã nhận record.
- Listener đã được gọi.
- Listener đã hoàn thành xử lý.
- Database đã có trạng thái mong đợi.
- Consumer group đã commit offset.
- Record lỗi đã xuất hiện trong DLT.

Mỗi điều kiện là một mốc khác nhau. Hãy đợi đúng mốc mà test đang xác minh.

## 2. Không dùng Thread.sleep để đồng bộ test

Một test dễ gặp vấn đề:

~~~java
@Test
void shouldConsumeOrder() throws Exception {
    kafkaTemplate.send("orders.created", event);

    Thread.sleep(2_000);

    assertThat(orderRepository.findById(event.orderId()))
            .isPresent();
}
~~~

Test này giả định hai giây luôn đủ để consumer xử lý record. Trên máy local có thể pass, nhưng trên CI hoặc khi broker đang rebalance có thể cần lâu hơn. Tăng thời gian ngủ lên mười giây chỉ làm test chậm hơn mà không bảo đảm điều kiện đã xảy ra.

Thay bằng việc đợi trạng thái:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(orderRepository.findById(event.orderId()))
                        .isPresent()
        );
~~~

Awaitility kiểm tra lại assertion cho tới khi thành công hoặc hết timeout. Test kết thúc ngay khi điều kiện đạt, thay vì luôn phải chờ hết một khoảng ngủ cố định.

Không dùng `Thread.sleep` làm cách đồng bộ giữa producer, consumer và test. Nếu cần mô phỏng thời gian xử lý hoặc timeout của nghiệp vụ, hãy điều khiển bằng clock, latch hoặc test double phù hợp.

## 3. Thêm Awaitility vào test

Awaitility là thư viện giúp chờ một điều kiện cuối cùng đạt được với timeout và poll interval có thể cấu hình.

Nếu dự án chưa có Awaitility, thêm dependency ở test scope. Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <scope>test</scope>
</dependency>
~~~

Với Gradle:

~~~groovy
testImplementation("org.awaitility:awaitility")
~~~

Nếu dùng Spring Boot dependency management, có thể để version được quản lý bởi dependency management phù hợp của dự án; nếu không, khai báo version đã được chuẩn hóa trong build.

Import thường dùng:

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
~~~

Awaitility không tạo Kafka broker và không thay thế EmbeddedKafka hoặc Testcontainers. Nó chỉ điều phối việc chờ điều kiện trong test.

## 4. Cấu hình timeout và poll interval

Một lệnh Awaitility cơ bản:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .until(() -> orderRepository.existsById(orderId));
~~~

Ý nghĩa:

- `atMost`: giới hạn tổng thời gian chờ.
- `pollInterval`: khoảng cách giữa các lần kiểm tra.
- `until`: điều kiện phải trả về true.

Nếu cần assertion giàu thông tin, dùng `untilAsserted`:

~~~java
await()
        .alias("order should be persisted by Kafka listener")
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
                assertThat(orderRepository.findById(orderId))
                        .isPresent()
        );
~~~

Chọn timeout đủ cho thời gian khởi động consumer, group join, poll, xử lý và cập nhật state. Poll interval không cần quá nhỏ; kiểm tra mỗi vài mili giây thường chỉ tạo tải không cần thiết lên database hoặc broker.

Không dùng timeout vô hạn. Khi hết timeout, test cần fail để chỉ ra điều kiện nào chưa xảy ra.

## 5. Đợi listener nhận record bằng dữ liệu thread-safe

Listener chạy trên consumer thread, còn test chạy trên test thread. Không nên chia sẻ một `ArrayList` thông thường giữa hai thread mà không có đồng bộ.

Có thể dùng `BlockingQueue`:

~~~java
@Component
public class TestOrderListener {

    private final BlockingQueue<OrderCreatedEvent> received =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            topics = "${test.kafka.topic}",
            groupId = "test-orders-listener"
    )
    public void listen(OrderCreatedEvent event) {
        received.add(event);
    }

    public BlockingQueue<OrderCreatedEvent> received() {
        return received;
    }
}
~~~

Test gửi record và đợi bằng `poll(timeout)`:

~~~java
@Test
void shouldReceiveOrderEvent() throws Exception {
    OrderCreatedEvent event = sampleEvent();

    kafkaTemplate.send(topic, event.orderId(), event)
            .get(10, TimeUnit.SECONDS);

    OrderCreatedEvent actual =
            testOrderListener.received().poll(10, TimeUnit.SECONDS);

    assertThat(actual).isEqualTo(event);
}
~~~

`BlockingQueue.poll` chờ tối đa thời gian đã định và trả về null nếu không có record. Cách này ngắn gọn khi test chỉ cần lấy một kết quả.

Hãy dọn queue trước mỗi test nếu listener bean được dùng lại trong cùng application context:

~~~java
@BeforeEach
void clearReceivedEvents() {
    testOrderListener.received().clear();
}
~~~

Nếu test chạy song song, mỗi test nên có listener state riêng hoặc dùng correlation/event ID để phân biệt kết quả.

## 6. Dùng Awaitility với AtomicReference hoặc collection thread-safe

Nếu muốn chờ bằng Awaitility, có thể lưu kết quả vào `AtomicReference`:

~~~java
@Component
public class AwaitableOrderListener {

    private final AtomicReference<OrderCreatedEvent> received =
            new AtomicReference<>();

    @KafkaListener(
            topics = "${test.kafka.topic}",
            groupId = "test-awaitable-orders"
    )
    public void listen(OrderCreatedEvent event) {
        received.set(event);
    }

    public OrderCreatedEvent received() {
        return received.get();
    }

    public void reset() {
        received.set(null);
    }
}
~~~

Test:

~~~java
@Test
void shouldEventuallyReceiveExpectedEvent() throws Exception {
    OrderCreatedEvent expected = sampleEvent();

    awaitableOrderListener.reset();

    kafkaTemplate.send(topic, expected.orderId(), expected)
            .get(10, TimeUnit.SECONDS);

    await()
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() ->
                    assertThat(awaitableOrderListener.received())
                            .isEqualTo(expected)
            );
}
~~~

Với nhiều record, có thể dùng `CopyOnWriteArrayList` hoặc collection thread-safe khác:

~~~java
private final List<OrderCreatedEvent> received =
        new CopyOnWriteArrayList<>();
~~~

Và chờ đủ số record:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(received).hasSize(3)
        );
~~~

Điều kiện Awaitility có thể được thực thi nhiều lần. Không đặt thao tác tiêu thụ dữ liệu như `queue.take()`, `consumer.poll()` hoặc xóa collection bên trong điều kiện; lần kiểm tra đầu có thể lấy mất dữ liệu khiến lần sau không còn gì để kiểm tra.

## 7. Khi nào dùng CountDownLatch hoặc BlockingQueue thay Awaitility?

Awaitility phù hợp khi test chờ một trạng thái có thể truy vấn lặp lại. Nếu listener chỉ cần báo “đã nhận một record”, `CountDownLatch` hoặc `BlockingQueue` thường đơn giản hơn.

Ví dụ latch:

~~~java
@Component
public class LatchOrderListener {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<OrderCreatedEvent> received =
            new AtomicReference<>();

    @KafkaListener(
            topics = "${test.kafka.topic}",
            groupId = "test-latch-orders"
    )
    public void listen(OrderCreatedEvent event) {
        received.set(event);
        latch.countDown();
    }

    public boolean await(Duration timeout) throws InterruptedException {
        return latch.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public OrderCreatedEvent received() {
        return received.get();
    }
}
~~~

Test:

~~~java
kafkaTemplate.send(topic, event).get(10, TimeUnit.SECONDS);

assertThat(listener.await(Duration.ofSeconds(10))).isTrue();
assertThat(listener.received()).isEqualTo(event);
~~~

Latch chỉ đếm xuống, không tự reset. Nếu dùng lại listener giữa nhiều test, hãy tạo latch mới cho mỗi test hoặc tạo listener/test context riêng. Không chờ latch vô hạn.

## 8. Phân biệt chờ producer acknowledgement và chờ consumer completion

Với Spring Kafka 3.x, `KafkaTemplate.send()` trả về `CompletableFuture<SendResult<K, V>>`. Có thể chờ broker acknowledgement bằng `get(timeout)`:

~~~java
SendResult<String, OrderCreatedEvent> result =
        kafkaTemplate.send(topic, event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

assertThat(result.getRecordMetadata().topic()).isEqualTo(topic);
~~~

Lệnh này xác minh producer gửi thành công theo cấu hình acknowledgement. Nó không xác minh listener đã xử lý record.

Sau đó, dùng Awaitility, queue hoặc consumer polling để đợi kết quả phía consumer.

Trong các phiên bản Spring Kafka cũ hơn, API send có thể trả về `ListenableFuture`. Hãy dùng API tương ứng với phiên bản dependency; không trộn ví dụ của hai thế hệ API trong cùng codebase.

Không bỏ qua future nếu test cần xác minh producer send. Nếu send thất bại, test nên fail tại bước publish thay vì chờ consumer tới timeout rồi mới báo lỗi khó hiểu.

## 9. Polling trực tiếp bằng KafkaConsumer

Đôi khi test cần đọc record trực tiếp thay vì chờ một `@KafkaListener`. Có thể tạo KafkaConsumer test, subscribe topic và gọi `poll(Duration)`.

Ví dụ khởi tạo consumer:

~~~java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ConsumerConfig.GROUP_ID_CONFIG, "test-reader-" + UUID.randomUUID());
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class);
~~~

Nếu dùng JsonDeserializer, cần cấu hình target type/trusted packages hoặc mapping phù hợp với test contract. Có thể dùng StringDeserializer hoặc ByteArrayDeserializer khi test chỉ cần xác minh wire payload.

Subscribe:

~~~java
consumer.subscribe(List.of(topic));
~~~

Sau subscribe, consumer chưa chắc đã có assignment ngay. Gọi poll để tham gia group và chờ assignment trước khi phát record nếu test cần tránh race với `auto.offset.reset=latest`.

## 10. Chờ consumer assignment trước khi gửi record

Một lỗi thường gặp là test tạo consumer, subscribe rồi gửi record ngay. Consumer có thể chưa hoàn thành group join; nếu dùng `latest`, nó có thể bắt đầu từ cuối log sau khi record đã được ghi.

Có thể chờ assignment với deadline:

~~~java
consumer.subscribe(List.of(topic));

long assignmentDeadline =
        System.nanoTime() + Duration.ofSeconds(10).toNanos();

while (consumer.assignment().isEmpty()
        && System.nanoTime() < assignmentDeadline) {
    consumer.poll(Duration.ofMillis(100));
}

assertThat(consumer.assignment()).isNotEmpty();
~~~

Đoạn poll này cần chạy trên chính thread sở hữu KafkaConsumer. KafkaConsumer không thread-safe; không gọi `poll()` từ một thread trong khi thread khác đang dùng cùng consumer.

Khi assignment đã sẵn sàng, test có thể gửi record và bắt đầu vòng poll để đọc. Nếu topic có nhiều partition hoặc subscription phức tạp, kiểm tra assignment chứa partition mong đợi thay vì chỉ kiểm tra collection không rỗng.

## 11. Poll theo deadline thay vì poll vô hạn

Một helper polling có timeout rõ ràng:

~~~java
static <K, V> List<ConsumerRecord<K, V>> pollUntilCount(
        Consumer<K, V> consumer,
        int expectedCount,
        Duration timeout) {

    long deadline = System.nanoTime() + timeout.toNanos();
    List<ConsumerRecord<K, V>> collected = new ArrayList<>();

    while (collected.size() < expectedCount
            && System.nanoTime() < deadline) {

        ConsumerRecords<K, V> batch =
                consumer.poll(Duration.ofMillis(100));

        batch.forEach(collected::add);
    }

    if (collected.size() < expectedCount) {
        throw new AssertionError(
                "Expected " + expectedCount
                + " records but received " + collected.size()
        );
    }

    return collected;
}
~~~

Helper dừng khi đã nhận đủ record hoặc hết deadline. Nó không dùng `while(true)` và không chờ vô hạn.

Trong test, hãy bảo đảm consumer đã subscribe và có assignment trước khi gửi record nếu cần kiểm soát offset reset. Sau khi đọc, có thể assert topic, key, value, partition, offset và headers.

Nếu cần đọc chính xác một record, truyền expectedCount bằng một. Nếu cần kiểm tra không có record dư hoặc duplicate, hãy định nghĩa rõ cửa sổ quan sát và điều kiện test; việc nhận đủ N record đầu tiên không tự chứng minh sẽ không có record thứ N+1.

## 12. Polling một điều kiện và polling Kafka record khác nhau

Hai kỹ thuật cùng có tên polling nhưng có trách nhiệm khác nhau:

| Kỹ thuật | Đối tượng được kiểm tra | Thường dùng khi |
|---|---|---|
| Awaitility polling | Một điều kiện có thể truy vấn lặp lại | Database row xuất hiện, listener state thay đổi, offset được commit. |
| KafkaConsumer.poll | Record từ broker | Test cần kiểm tra wire record, headers, partition và offset. |
| BlockingQueue.poll | Kết quả được listener đẩy vào queue | Test cần lấy record listener đã nhận. |
| CountDownLatch.await | Tín hiệu hoàn tất | Test cần biết một callback đã chạy. |

Không đặt KafkaConsumer.poll trong Awaitility condition nếu cùng consumer có thể bị gọi từ nhiều thread. Nếu dùng Awaitility để chờ dữ liệu từ listener, hãy chờ một holder thread-safe như AtomicReference hoặc queue peek.

Nếu test cần đọc record trực tiếp, dùng vòng poll đồng bộ trên test thread với deadline.

## 13. Dùng EmbeddedKafka để kiểm thử listener

Spring Kafka cung cấp `@EmbeddedKafka` để chạy broker embedded trong integration test. Ví dụ:

~~~java
@SpringBootTest
@EmbeddedKafka(
        topics = "orders.created",
        partitions = 1,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderListenerIntegrationTest {
    // Inject KafkaTemplate và listener capture.
}
~~~

Test có thể gửi record bằng KafkaTemplate, sau đó chờ listener cập nhật queue hoặc database.

EmbeddedKafka phù hợp cho test nhanh và kiểm tra tích hợp Spring Kafka. Tuy nhiên, broker embedded không thay thế hoàn toàn môi trường Kafka production, đặc biệt khi cần xác minh SASL/TLS, nhiều broker, replication, rack awareness hoặc behavior phụ thuộc phiên bản cluster.

Hãy dùng Testcontainers hoặc môi trường integration chuyên biệt cho các kịch bản cần broker gần production hơn.

## 14. Dùng Testcontainers khi cần broker thực tế hơn

Testcontainers có thể khởi chạy Kafka container trong test và cung cấp bootstrap servers cho Spring context.

Các bước tổng quát:

1. Khởi động Kafka container trước khi Spring context tạo Kafka clients.
2. Truyền bootstrap servers vào `spring.kafka.bootstrap-servers`.
3. Tạo topic hoặc bật topic provisioning trong test.
4. Gửi record bằng KafkaTemplate.
5. Đợi listener/side effect hoặc đọc record bằng consumer test.
6. Dừng container sau khi test kết thúc.

Testcontainers hữu ích khi kiểm tra phiên bản broker cụ thể, listener config, transactions hoặc security. Cần chọn image và mode phù hợp với phiên bản Kafka client/broker đang dùng.

Không nên khởi động một broker container mới cho từng assertion. Tận dụng lifecycle của test suite hoặc class khi các test có thể chia sẻ broker nhưng vẫn cô lập topic và group ID.

## 15. Đợi database side effect sau khi listener chạy

Một listener có thể nhận record rồi cập nhật database bất đồng bộ. Nếu mục tiêu test là xác minh kết quả nghiệp vụ, nên đợi trạng thái database thay vì chỉ đợi listener invocation.

~~~java
kafkaTemplate.send(topic, event).get(10, TimeUnit.SECONDS);

await()
        .alias("order should be stored")
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            assertThat(orderRepository.findById(event.orderId()))
                    .hasValueSatisfying(order ->
                            assertThat(order.getStatus()).isEqualTo("CREATED")
                    );
        });
~~~

Điều kiện cần truy vấn trạng thái có thể quan sát và không tạo side effect. Nếu repository đọc qua cache, hãy xác định test đang kiểm tra database hay cache.

Nếu listener chạy transaction database riêng, test không nên bọc toàn bộ test method trong transaction rồi kỳ vọng consumer thread nhìn thấy dữ liệu chưa commit. Transaction của test thread và transaction của listener thread là hai transaction khác nhau.

## 16. Đợi committed offset

Một số test cần xác minh listener đã xử lý và consumer group đã commit offset. Có thể truy vấn AdminClient và đợi offset đạt giá trị mong đợi.

Ví dụ điều kiện khái quát:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            OffsetAndMetadata committed =
                    adminClient.listConsumerGroupOffsets(groupId)
                            .partitionsToOffsetAndMetadata()
                            .get(5, TimeUnit.SECONDS)
                            .get(new TopicPartition(topic, partition));

            assertThat(committed).isNotNull();
            assertThat(committed.offset()).isGreaterThan(expectedInputOffset);
        });
~~~

Offset commit là offset tiếp theo cần đọc. Nếu test xử lý record offset 10, committed offset mong đợi thường là 11 hoặc lớn hơn, tùy record trước đó và AckMode.

Không dùng committed offset làm bằng chứng duy nhất cho side effect database. Offset có thể commit theo cấu hình container; test nghiệp vụ nên kiểm tra cả trạng thái nghiệp vụ.

Nếu dùng MANUAL acknowledgment hoặc transaction, xác định chính xác điều kiện commit tương ứng trước khi viết assertion.

## 17. Đợi retry và dead-letter record

Khi test retry, listener có thể được gọi nhiều lần trước khi recovery. Khi test DLT, cần đợi record xuất hiện ở DLT sau khi error handler publish thành công.

Có thể dùng một DLT test listener ghi vào queue:

~~~java
@Component
public class TestDltListener {

    private final BlockingQueue<ConsumerRecord<String, byte[]>> received =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            topics = "orders.created.DLT",
            groupId = "test-dlt-reader"
    )
    public void listen(ConsumerRecord<String, byte[]> record) {
        received.add(record);
    }

    public BlockingQueue<ConsumerRecord<String, byte[]>> received() {
        return received;
    }
}
~~~

Kiểu `ConsumerRecord<String, byte[]>` chỉ phù hợp khi container factory của DLT test listener dùng `StringDeserializer` cho key và `ByteArrayDeserializer` cho value. Kiểu tham số Java của listener không tự cấu hình deserializer; nếu DLT đang dùng serializer khác, hãy chọn kiểu value và factory tương ứng.

Test gửi record gây lỗi, sau đó đợi DLT record:

~~~java
ConsumerRecord<String, byte[]> deadLetter =
        dltListener.received().poll(15, TimeUnit.SECONDS);

assertThat(deadLetter).isNotNull();
assertThat(deadLetter.headers().lastHeader(
        KafkaHeaders.DLT_ORIGINAL_TOPIC
)).isNotNull();
~~~

Timeout cần bao gồm số lần retry và backoff đã cấu hình. Nếu test dùng backoff dài, giảm thời gian trong test profile hoặc tăng timeout có giới hạn; không thay đổi semantics production chỉ để test chạy nhanh.

Nếu muốn kiểm tra retry count, dùng counter thread-safe hoặc spy/mock phù hợp và đợi điều kiện cuối cùng. Đừng dùng sleep để đoán thời điểm lần retry thứ ba đã xảy ra.

## 18. Tránh flaky test do dữ liệu cũ và consumer group dùng lại

Một test có thể nhận record từ lần chạy trước nếu topic/group ID được tái sử dụng và offset reset không đúng kỳ vọng.

Các biện pháp cô lập:

- Dùng topic riêng hoặc topic được tạo mới cho test.
- Dùng group ID duy nhất theo test run khi cần đọc từ đầu.
- Đặt `auto.offset.reset` có chủ đích.
- Tạo consumer và chờ assignment trước khi gửi record nếu dùng latest.
- Xóa queue/capture state trước mỗi test.
- Không chạy hai test cùng ghi một topic/group nếu chúng ảnh hưởng kết quả của nhau.
- Đóng KafkaConsumer, AdminClient và các tài nguyên sau test.
- Không phụ thuộc thứ tự chạy test.

`auto.offset.reset=earliest` chỉ áp dụng khi group chưa có committed offset hợp lệ. Nếu group đã có offset, consumer tiếp tục từ offset đã commit; đổi auto.offset.reset không tự tua lại dữ liệu.

Nếu dùng topic chung, hãy lọc theo event ID riêng và xác minh đúng record của test hiện tại.

## 19. Chọn timeout theo thời gian thực tế

Timeout không nên quá ngắn đến mức CI tải cao làm test thất bại ngẫu nhiên, cũng không nên quá dài khiến lỗi thật mất nhiều phút mới được phát hiện.

Hãy xem xét:

- Thời gian khởi động broker và Spring context.
- Thời gian consumer group join/rebalance.
- Poll timeout và concurrency.
- Retry/backoff nếu có.
- Thời gian xử lý database hoặc downstream.
- Môi trường local, CI và container runtime.
- Timeout của chính producer send và AdminClient request.

Có thể dùng timeout dài hơn cho lần khởi động đầu và ngắn hơn cho điều kiện listener đã sẵn sàng. Không tăng mọi timeout cùng lúc khi test flaky; hãy xác định bước nào đang chậm.

Thông báo timeout nên nêu điều kiện mong đợi, topic, group ID và event ID để việc chẩn đoán dễ hơn. Tránh chỉ báo “condition was not fulfilled” mà không có ngữ cảnh.

## 20. Những lỗi thường gặp khi chờ record

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng Thread.sleep cố định | Flaky hoặc test chậm | Awaitility, queue/latch hoặc poll deadline. |
| Nghĩ send future xong là listener xong | Assert quá sớm | Đợi listener hoặc side effect riêng. |
| Awaitility condition tiêu thụ queue | Lần poll sau không còn dữ liệu | Dùng peek/AtomicReference trong condition; lấy dữ liệu sau khi đạt. |
| Dùng KafkaConsumer từ nhiều thread | Vi phạm thread-safety | Poll trên một thread duy nhất. |
| Gửi trước khi consumer assignment sẵn sàng với latest | Consumer có thể bỏ lỡ record vừa gửi | Chờ assignment trước khi produce hoặc dùng group/topic cô lập. |
| Poll không có deadline | Test treo vô hạn | Dùng deadline và timeout hữu hạn. |
| Dùng group ID cũ | Đọc tiếp từ committed offset cũ | Tạo group ID riêng hoặc quản lý offset rõ ràng. |
| Chỉ đợi listener invocation | Chưa chứng minh database commit | Đợi trạng thái nghiệp vụ cần xác minh. |
| Timeout ngắn hơn retry/backoff | Test fail dù code đúng | Tính tổng thời gian retry và recovery. |
| Chia sẻ ArrayList giữa listener và test | Race condition hoặc visibility issue | Dùng BlockingQueue, AtomicReference hoặc collection thread-safe. |
| Không đóng consumer | Rò rỉ thread/connection và ảnh hưởng test sau | Dùng try-with-resources hoặc cleanup lifecycle. |

## 21. Bài tập tổng hợp: kiểm thử OrderCreatedListener

Hãy xây dựng integration test cho topic `orders.created` và listener cập nhật trạng thái đơn hàng.

Yêu cầu:

1. Chạy broker bằng EmbeddedKafka hoặc Testcontainers.
2. Tạo listener test ghi event vào BlockingQueue hoặc AtomicReference.
3. Gửi event bằng KafkaTemplate và chờ producer acknowledgement với timeout.
4. Dùng Awaitility đợi listener nhận đúng event ID.
5. Dùng Awaitility đợi database có order ở trạng thái CREATED.
6. Viết một test dùng BlockingQueue.poll(timeout) thay cho Awaitility.
7. Viết một test consumer trực tiếp, subscribe và chờ assignment trước khi gửi record.
8. Tạo helper pollUntilCount với deadline hữu hạn.
9. Xác minh topic, key, value, partition, offset và headers.
10. Kiểm tra committed offset bằng AdminClient.
11. Mô phỏng listener retry rồi thành công và đợi đúng kết quả cuối.
12. Mô phỏng hết retry và đợi record trong DLT.
13. Dùng group ID riêng để tránh đọc offset từ lần test trước.
14. Thử chạy test song song và bảo đảm topic, event ID, capture state không xung đột.
15. Xác minh test không dùng Thread.sleep và không có vòng poll vô hạn.

Bài tập hoàn thành khi test chỉ kết thúc sau khi điều kiện thực tế đã đạt hoặc timeout hữu hạn hết hạn, đồng thời thông báo lỗi đủ thông tin để xác định topic, group, event và bước xử lý bị chậm.

## 22. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Async flow | Producer, broker, consumer, listener | Phân biệt send acknowledgement với listener completion. |
| 2. Awaitility | until và untilAsserted | Đợi được trạng thái cuối với timeout. |
| 3. Thread safety | Queue, latch, atomic holder | Chia sẻ kết quả giữa listener và test an toàn. |
| 4. Producer future | CompletableFuture | Xác minh broker acknowledgement riêng. |
| 5. Consumer polling | poll(Duration) | Đọc record bằng vòng poll có deadline. |
| 6. Assignment | Subscribe và group join | Chờ partition assignment trước khi gửi khi cần. |
| 7. Side effects | Database và committed offset | Đợi đúng trạng thái cần kiểm tra. |
| 8. Error paths | Retry và DLT | Chờ được kết quả recovery. |
| 9. Isolation | Topic, group ID và cleanup | Không nhận dữ liệu cũ hoặc chồng lấn giữa test. |
| 10. Reliability | Timeout và diagnostics | Không dùng sleep hoặc wait vô hạn. |

Bài học hoàn thành khi bạn có thể chọn Awaitility để chờ trạng thái bất đồng bộ, dùng BlockingQueue/CountDownLatch cho tín hiệu listener hoặc poll KafkaConsumer trực tiếp theo deadline. Bạn cũng cần phân biệt broker acknowledgement, listener completion, database commit và consumer offset commit.

Kafka test ổn định khi test đợi điều kiện thực tế thay vì đoán thời gian. Hãy đặt timeout hữu hạn, dùng trạng thái thread-safe, cô lập topic/group ID và chỉ poll KafkaConsumer trên một thread. Khi đó test vừa nhanh khi hệ thống phản hồi tốt, vừa báo lỗi rõ ràng khi luồng messaging không hoàn tất.

