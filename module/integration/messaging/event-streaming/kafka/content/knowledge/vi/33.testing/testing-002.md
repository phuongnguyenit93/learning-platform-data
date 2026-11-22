# MockProducer, MockConsumer và giới hạn mô phỏng

Kafka cung cấp `MockProducer` và `MockConsumer` trong Java client để kiểm thử logic ứng dụng mà không cần chạy broker. Chúng hữu ích khi muốn xác nhận producer tạo đúng record, xử lý callback đúng, consumer điều phối poll/offset đúng hoặc ứng dụng phản ứng ra sao khi một lần gửi thất bại.

Mock không phải Kafka broker thu nhỏ. `MockProducer` và `MockConsumer` không thực hiện network protocol, replication, partition leader election hay group coordination thật. Vì vậy, hãy dùng chúng cho unit test ở ranh giới ứng dụng; dùng broker thật trong integration test khi cần xác nhận behavior của Kafka.

## 1. Khi nào nên dùng MockProducer và MockConsumer?

| Công cụ | Mô phỏng | Phù hợp để kiểm tra |
|---|---|---|
| `MockProducer` | Producer API và kết quả gửi được điều khiển trong test | Topic/key/value/header, callback, lỗi gửi, luồng transaction ở mức gọi API |
| `MockConsumer` | Consumer API, record được nạp trực tiếp vào test | Poll loop, handler, seek, commit, pause/resume, logic khi partition được assign/revoke |
| Embedded Kafka / Testcontainers | Kafka broker thực tế trong test | Protocol, serialization, group coordination, transaction và integration |
| Multi-broker test cluster | Nhiều broker có replication | ISR, leader failover, replication và durability behavior |

Dùng mock khi câu hỏi là “ứng dụng của tôi gọi Kafka API và xử lý kết quả thế nào?”. Dùng broker thật khi câu hỏi là “Kafka có thực hiện protocol, coordination hoặc replication đúng như cấu hình không?”.

## 2. Thêm dependency kiểm thử

`MockProducer` và `MockConsumer` nằm trong artifact `kafka-clients`, cùng package với producer/consumer API. Nếu project đã phụ thuộc Kafka client để chạy ứng dụng, test thường có thể dùng trực tiếp cùng version đó.

Ví dụ Gradle:

~~~kotlin
dependencies {
    implementation("org.apache.kafka:kafka-clients:<kafka-version>")
    testImplementation("org.junit.jupiter:junit-jupiter:<junit-version>")
}
~~~

Ví dụ Maven:

~~~xml
<dependency>
  <groupId>org.apache.kafka</groupId>
  <artifactId>kafka-clients</artifactId>
  <version>VERSION_PLACEHOLDER</version>
</dependency>
~~~

Các placeholder version cần được thay bằng version mà ứng dụng đang dùng. Tránh để test compile với một Kafka client version khác runtime vì API và behavior của mock có thể thay đổi giữa release.

Các class chính:

~~~java
import org.apache.kafka.clients.producer.MockProducer;
import org.apache.kafka.clients.consumer.MockConsumer;
import org.apache.kafka.clients.consumer.OffsetResetStrategy;
~~~

## 3. MockProducer hoạt động như thế nào?

`MockProducer<K, V>` triển khai Kafka `Producer<K, V>` nhưng giữ trạng thái trong bộ nhớ. Test có thể:

- Gửi `ProducerRecord` và kiểm tra record đã gửi qua `history()`.
- Chọn chế độ tự hoàn tất hoặc chờ test gọi hoàn tất.
- Gọi `completeNext()` để hoàn tất lần gửi đang chờ.
- Gọi `errorNext(exception)` để lần gửi tiếp theo được hoàn tất với lỗi.
- Kiểm tra callback nhận `RecordMetadata` hay exception.
- Kiểm tra một số trạng thái flush, close và transaction được mock hỗ trợ.

Constructor thường dùng:

~~~java
MockProducer<String, String> producer =
    new MockProducer<>(
        true,
        new StringSerializer(),
        new StringSerializer()
    );
~~~

Tham số `autoComplete=true` làm lần gửi được mock hoàn tất tự động. Với `false`, test chủ động điều khiển thời điểm hoàn tất bằng `completeNext()` hoặc lỗi bằng `errorNext()` kết hợp với việc hoàn tất lần gửi đang chờ.

Khi test producer service, nên phụ thuộc vào interface `Producer<K,V>` thay vì khởi tạo `KafkaProducer` trực tiếp bên trong business logic. Nhờ vậy, production dùng KafkaProducer còn unit test truyền MockProducer.

## 4. Unit test gửi record thành công

Ví dụ service xuất bản event:

~~~java
public final class OrderPublisher {
    private final Producer<String, String> producer;

    public OrderPublisher(Producer<String, String> producer) {
        this.producer = producer;
    }

    public void publish(String orderId, String payload) {
        ProducerRecord<String, String> record =
            new ProducerRecord<>("orders", orderId, payload);
        producer.send(record);
    }
}
~~~

Test kiểm tra topic, key và value:

~~~java
class OrderPublisherTest {
    @Test
    void publishesOrderEvent() {
        MockProducer<String, String> producer =
            new MockProducer<>(
                true,
                new StringSerializer(),
                new StringSerializer()
            );
        OrderPublisher publisher = new OrderPublisher(producer);

        publisher.publish("order-42", "{\"status\":\"CREATED\"}");

        assertEquals(1, producer.history().size());
        ProducerRecord<String, String> sent = producer.history().get(0);
        assertEquals("orders", sent.topic());
        assertEquals("order-42", sent.key());
        assertEquals("{\"status\":\"CREATED\"}", sent.value());
    }
}
~~~

Ví dụ trên kiểm tra ứng dụng tạo đúng record và gọi producer. Nó chưa chứng minh broker đã nhận record, replica đã xác nhận hoặc consumer khác đọc được event.

`history()` là lịch sử record của mock, không phải log Kafka. Nếu ứng dụng gửi nhiều record, có thể kiểm tra thứ tự gọi và header. Ví dụ đọc header:

~~~java
MockProducer<String, String> producer =
    new MockProducer<>(true, new StringSerializer(), new StringSerializer());
ProducerRecord<String, String> record =
    new ProducerRecord<>("orders", "order-42", "created");
record.headers().add(
    "correlation-id",
    "order-42".getBytes(StandardCharsets.UTF_8)
);
producer.send(record);
ProducerRecord<String, String> sent = producer.history().get(0);
Header header = sent.headers().lastHeader("correlation-id");
assertNotNull(header);
assertEquals(
    "order-42",
    new String(header.value(), StandardCharsets.UTF_8)
);
~~~

## 5. Kiểm tra callback và lỗi gửi bất đồng bộ

Producer API trả về `Future<RecordMetadata>` và có thể nhận callback. Với mock không tự hoàn tất, test có thể kiểm soát lúc callback được gọi.

~~~java
class ProducerCallbackTest {
    @Test
    void completesSendAndInvokesCallback() {
        MockProducer<String, String> producer =
            new MockProducer<>(
                false,
                new StringSerializer(),
                new StringSerializer()
            );
        AtomicReference<Exception> callbackError = new AtomicReference<>();
        AtomicReference<RecordMetadata> metadata = new AtomicReference<>();

        producer.send(
            new ProducerRecord<>("orders", 0, "order-42", "created"),
            (result, error) -> {
                metadata.set(result);
                callbackError.set(error);
            }
        );

        assertNull(metadata.get());
        assertNull(callbackError.get());
        assertTrue(producer.completeNext());
        assertNull(callbackError.get());
        assertNotNull(metadata.get());
    }
}
~~~

Test lỗi:

~~~java
class ProducerFailureTest {
    @Test
    void callbackReceivesSendFailure() {
        MockProducer<String, String> producer =
            new MockProducer<>(
                false,
                new StringSerializer(),
                new StringSerializer()
            );
        AtomicReference<Exception> callbackError = new AtomicReference<>();

        producer.errorNext(new TimeoutException("simulated timeout"));
        producer.send(
            new ProducerRecord<>("orders", 0, "order-42", "created"),
            (metadata, error) -> callbackError.set(error)
        );

        assertTrue(producer.completeNext());
        assertInstanceOf(TimeoutException.class, callbackError.get());
    }
}
~~~

Ví dụ dùng partition `0` tường minh để không phụ thuộc vào broker metadata hoặc partitioner. Hành vi chi tiết của `errorNext`, `completeNext` và callback cần được kiểm tra theo version `kafka-clients` mà project đang dùng.

### Kiểm tra retry ở tầng ứng dụng

Nếu service có retry policy riêng, có thể dùng mock để tạo lần gửi lỗi rồi kiểm tra ứng dụng có lên lịch retry, ghi metric hoặc chuyển sang error path đúng không. Tuy nhiên, `MockProducer` không tái hiện retry nội bộ, backoff, request timeout, network reconnect hoặc idempotent sequence của `KafkaProducer` thật.

Không viết unit test để khẳng định broker sẽ trả đúng một loại lỗi trong một tình huống mạng cụ thể. Hãy kiểm tra nhánh xử lý lỗi bằng mock; kiểm tra retry/protocol thật bằng integration test.

## 6. Kiểm tra flush, close và transaction ở mức API

MockProducer có các trạng thái hỗ trợ test việc ứng dụng gọi `flush()` và `close()`. Có thể kiểm tra producer lifecycle khi service shutdown:

~~~java
@Test
void closesProducerOnShutdown() {
    MockProducer<String, String> producer =
        new MockProducer<>(true, new StringSerializer(), new StringSerializer());

    producer.close();

    assertTrue(producer.closed());
}
~~~

Với transaction, mock có thể hỗ trợ các lời gọi như `initTransactions`, `beginTransaction`, `sendOffsetsToTransaction`, `commitTransaction` và `abortTransaction`, tùy version client. Test có thể xác nhận code đi đúng nhánh commit/abort và không quên đóng transaction.

~~~java
@Test
void executesTransactionalApiFlow() {
    MockProducer<String, String> producer =
        new MockProducer<>(true, new StringSerializer(), new StringSerializer());

    producer.initTransactions();
    producer.beginTransaction();
    producer.send(new ProducerRecord<>("orders", 0, "order-42", "created"));
    producer.commitTransaction();

    assertEquals(1, producer.history().size());
}
~~~

Đây là kiểm tra luồng gọi API trong mock. Nó không chứng minh transaction coordinator, producer ID/epoch, fencing, transaction timeout, commit marker, read_committed isolation hoặc atomicity giữa output topic và consumer offsets trên broker thật.

## 7. MockConsumer hoạt động như thế nào?

`MockConsumer<K, V>` triển khai `Consumer<K, V>` với record và trạng thái do test điều khiển. Test có thể:

- Gán partition bằng `assign()` hoặc mô phỏng assignment bằng `subscribe()` và `rebalance()`.
- Nạp record bằng `addRecord()`.
- Thiết lập beginning/end offset bằng `updateBeginningOffsets()` và `updateEndOffsets()`.
- Gọi `poll()` để lấy record.
- Kiểm tra `position()`, `seek()`, committed offsets.
- Gọi `pause()`/`resume()` và kiểm tra partition đang pause.
- Đăng ký poll task bằng `schedulePollTask()` để điều khiển hành động trong lần poll tiếp theo.

Khởi tạo:

~~~java
MockConsumer<String, String> consumer =
    new MockConsumer<>(OffsetResetStrategy.EARLIEST);
~~~

`MockConsumer` không kết nối broker. Test đưa trực tiếp `ConsumerRecord` đã có key/value vào mock; vì vậy nó không thực hiện fetch protocol hoặc deserialize bytes như consumer thật.

## 8. Unit test poll và xử lý record

Ví dụ một handler nhận record và cập nhật trạng thái đơn hàng:

~~~java
interface OrderService {
    void applyEvent(String orderId, String event);
}

public final class OrderRecordHandler {
    private final OrderService orderService;

    public OrderRecordHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    public void handle(ConsumerRecord<String, String> record) {
        orderService.applyEvent(record.key(), record.value());
    }
}
~~~

Test dùng MockConsumer để cấp record:

~~~java
class OrderRecordHandlerTest {
    @Test
    void processesPolledRecord() {
        MockConsumer<String, String> consumer =
            new MockConsumer<>(OffsetResetStrategy.EARLIEST);
        TopicPartition partition = new TopicPartition("orders", 0);
        consumer.assign(List.of(partition));
        consumer.updateBeginningOffsets(Map.of(partition, 0L));
        consumer.addRecord(
            new ConsumerRecord<>("orders", 0, 0L, "order-42", "CREATED")
        );

        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(1));

        assertEquals(1, records.count());
        ConsumerRecord<String, String> record = records.iterator().next();
        assertEquals("order-42", record.key());
        assertEquals("CREATED", record.value());
        AtomicReference<String> handledEvent = new AtomicReference<>();
        OrderRecordHandler handler = new OrderRecordHandler(
            (orderId, event) -> handledEvent.set(orderId + ":" + event)
        );
        handler.handle(record);
        assertEquals("order-42:CREATED", handledEvent.get());
    }
}
~~~

Test này kiểm tra logic đọc record và có thể được mở rộng để gọi handler/service. Nếu cần xác nhận ứng dụng commit sau khi handler thành công, hãy kiểm tra commit offset trong poller/service adapter thay vì chỉ assert số record được trả về.

### Nạp nhiều record và nhiều partition

`addRecord()` nhận `ConsumerRecord` có topic/partition cụ thể. Partition cần được assign cho mock trước khi nạp record. Có thể nạp nhiều record để kiểm tra thứ tự xử lý trong một partition:

~~~java
consumer.addRecord(new ConsumerRecord<>("orders", 0, 0L, "order-1", "CREATED"));
consumer.addRecord(new ConsumerRecord<>("orders", 0, 1L, "order-2", "CREATED"));
consumer.addRecord(new ConsumerRecord<>("orders", 0, 2L, "order-1", "PAID"));

ConsumerRecords<String, String> batch = consumer.poll(Duration.ofMillis(1));
assertEquals(3, batch.count());
~~~

Thứ tự record được test đưa vào không chứng minh Kafka broker sẽ lưu thứ tự tương tự khi nhiều producer gửi đồng thời. Đây chỉ là dữ liệu đầu vào của unit test.

## 9. Kiểm tra commit offset và seek

Consumer nên commit offset tiếp theo sau record đã xử lý thành công. Ví dụ record offset `10` hoàn tất thì offset được commit thường là `11`.

~~~java
@Test
void commitsNextOffsetAfterProcessing() {
    MockConsumer<String, String> consumer =
        new MockConsumer<>(OffsetResetStrategy.EARLIEST);
    TopicPartition partition = new TopicPartition("orders", 0);
    consumer.assign(List.of(partition));
    consumer.updateBeginningOffsets(Map.of(partition, 10L));
    consumer.addRecord(
        new ConsumerRecord<>("orders", 0, 10L, "order-42", "CREATED")
    );

    ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(1));
    assertEquals(1, records.count());

    consumer.commitSync(
        Map.of(partition, new OffsetAndMetadata(11L))
    );

    Map<TopicPartition, OffsetAndMetadata> committed =
        consumer.committed(Set.of(partition), Duration.ofSeconds(1));
    assertEquals(11L, committed.get(partition).offset());
}
~~~

Mock lưu committed offset trong bộ nhớ để test. Nó không ghi vào `__consumer_offsets`, không gọi group coordinator và không kiểm tra commit có được replicate hay không.

Để kiểm tra logic replay, có thể dùng `seek()` đưa position về offset đã chọn rồi xác nhận consumer position:

~~~java
consumer.seek(partition, 10L);
assertEquals(10L, consumer.position(partition));
~~~

Mock giúp kiểm tra code chọn offset. Nó không kiểm tra broker retention, offset out of range sau khi segment bị xóa hoặc reset behavior của group coordinator thực tế.

## 10. Kiểm tra pause/resume và backpressure

Ứng dụng có thể pause partition khi downstream quá tải rồi resume khi xử lý kịp. MockConsumer cho phép kiểm tra nhánh điều khiển:

~~~java
@Test
void pausesAndResumesPartition() {
    MockConsumer<String, String> consumer =
        new MockConsumer<>(OffsetResetStrategy.EARLIEST);
    TopicPartition partition = new TopicPartition("orders", 0);
    consumer.assign(List.of(partition));

    consumer.pause(Set.of(partition));
    assertTrue(consumer.paused().contains(partition));

    consumer.resume(Set.of(partition));
    assertFalse(consumer.paused().contains(partition));
}
~~~

Unit test xác nhận ứng dụng gọi pause/resume đúng điều kiện. Nó không mô phỏng đầy đủ fetch buffer, network traffic, heartbeat, `max.poll.interval.ms` hoặc tác động của pause tới group membership.

## 11. Mô phỏng assignment và rebalance callback

Với consumer subscribe theo topic, test có thể gắn `ConsumerRebalanceListener` rồi yêu cầu MockConsumer mô phỏng assignment:

~~~java
@Test
void invokesAssignmentCallback() {
    MockConsumer<String, String> consumer =
        new MockConsumer<>(OffsetResetStrategy.EARLIEST);
    TopicPartition partition = new TopicPartition("orders", 0);
    AtomicReference<Collection<TopicPartition>> assigned =
        new AtomicReference<>();

    consumer.subscribe(
        List.of("orders"),
        new ConsumerRebalanceListener() {
            @Override
            public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {
            }

            @Override
            public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
                assigned.set(partitions);
            }
        }
    );

    consumer.rebalance(List.of(partition));

    assertNotNull(assigned.get());
    assertTrue(assigned.get().contains(partition));
}
~~~

Có thể dùng `schedulePollTask()` để xếp một hành động sẽ chạy trong lần poll kế tiếp, ví dụ mô phỏng assignment thay đổi trong khi poll loop tiếp tục hoạt động. Tuy nhiên, `rebalance()` của mock chỉ gọi logic mô phỏng; nó không chạy JoinGroup/SyncGroup protocol, cooperative revoke, heartbeat timeout hay coordinator failover thật.

## 12. Kiểm tra lỗi xử lý và không commit khi thất bại

Một invariant quan trọng là không commit offset vượt qua record chưa được xử lý thành công. Có thể kiểm tra logic của poller bằng cách tiêm handler giả ném exception:

~~~java
@FunctionalInterface
interface ConsumerRecordHandler {
    void handle(ConsumerRecord<String, String> record);
}

public final class OrderPoller {
    private final Consumer<String, String> consumer;
    private final ConsumerRecordHandler handler;

    public OrderPoller(
        Consumer<String, String> consumer,
        ConsumerRecordHandler handler
    ) {
        this.consumer = consumer;
        this.handler = handler;
    }

    public void pollOnce() {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(100));
        Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

        for (ConsumerRecord<String, String> record : records) {
            handler.handle(record);
            TopicPartition tp =
                new TopicPartition(record.topic(), record.partition());
            offsets.put(tp, new OffsetAndMetadata(record.offset() + 1));
        }

        if (!offsets.isEmpty()) {
            consumer.commitSync(offsets);
        }
    }
}
~~~

Ví dụ đơn giản trên xử lý tuần tự. Nếu nhiều record cùng partition được xử lý bất đồng bộ, không được commit offset cao nhất khi vẫn còn record thấp hơn chưa hoàn tất. Cần quản lý contiguous completed offset hoặc một cơ chế checkpoint tương đương.

Test có thể nạp record, cấu hình handler ném exception và xác nhận committed offset chưa tiến lên. Điều này kiểm tra logic poller; nó không xác minh commit/rebalance race của broker.

## 13. Tách adapter để unit test dễ hơn

Không nên để business logic phụ thuộc trực tiếp vào toàn bộ Kafka Consumer API. Một lớp adapter mỏng có thể chuyển record thành command/domain event:

~~~java
public interface EventPublisher {
    void publish(String topic, String key, String payload);
}

public interface EventHandler {
    void handle(String key, String payload);
}
~~~

Production adapter dùng KafkaProducer/KafkaConsumer. Unit test business service có thể dùng fake hoặc mock interface đơn giản; chỉ những test tập trung vào cách adapter tương tác với Kafka API mới cần MockProducer/MockConsumer.

Điều này giúp test không bị khóa vào chi tiết `poll()`, `ConsumerRecord` hoặc `ProducerRecord` nếu business logic không cần biết chúng.

## 14. Những điều MockProducer không mô phỏng

| Hành vi Kafka thật | Vì sao mock không đủ |
|---|---|
| Broker network và protocol | Không có socket, request/response hoặc network failure |
| Partition metadata và leader | Không có controller/metadata refresh thật |
| Partitioner theo cluster | Nếu không cung cấp metadata/cluster thích hợp, mock không chứng minh partition mapping trên cluster |
| Replication và ISR | Không có follower, high watermark hoặc leader election |
| `acks=all` và `min.insync.replicas` | Không có broker để kiểm tra durability policy |
| Idempotent producer protocol | Không có producer ID/epoch và broker sequence validation thật |
| Retry/backoff của KafkaProducer | `errorNext()` chỉ tiêm lỗi cho test, không chạy network retry engine |
| Transaction coordinator | Không có coordinator, transaction marker hoặc fencing thật |
| ACL/TLS/SASL | Không có authentication/authorization handshake |
| Broker quota/throttling | Không có quota manager và throttle time thật |

Có thể dùng MockProducer để kiểm tra ứng dụng xử lý callback exception, nhưng cần broker thật để xác minh producer retry, idempotence, transaction và durability.

## 15. Những điều MockConsumer không mô phỏng

| Hành vi Kafka thật | Vì sao mock không đủ |
|---|---|
| Fetch protocol và broker response | Record được test nạp trực tiếp |
| Group coordinator | Không có JoinGroup/SyncGroup/Heartbeat protocol |
| Partition assignment algorithm | Test tự gọi assign/rebalance hoặc điều khiển assignment |
| Rebalance timing | Không mô phỏng timeout, network delay hoặc member failure |
| `__consumer_offsets` | Commit được lưu trong mock memory |
| Retention và offset out of range | Không có log segment bị xóa theo retention |
| Read committed/isolation | Không có transaction marker và LSO của broker |
| Consumer lag thực tế | Không có log end offset của cluster |
| Deserializer/network errors | ConsumerRecord đã có object key/value |
| Cooperative rebalance và fencing | Không chạy group protocol thật |

MockConsumer phù hợp để kiểm tra poll loop, handler và quyết định offset. Dùng broker thật để xác nhận consumer group, rebalance, commit timing, isolation level và behavior khi broker/consumer member gặp sự cố.

## 16. Các lỗi thường gặp khi viết test mock

- **Assert mock history rồi kết luận record đã được Kafka lưu:** history chỉ là trạng thái trong mock.
- **Dùng autoComplete cho mọi test:** không kiểm tra được callback đang chờ và thứ tự hoàn tất.
- **Không điều khiển lỗi gửi:** bỏ qua nhánh callback failure và retry logic của ứng dụng.
- **Dùng MockConsumer để chứng minh rebalance thật:** `rebalance()` không chạy group coordinator.
- **Nạp record trước khi assign partition:** mock có thể từ chối record vì partition chưa được gán.
- **Commit offset cao nhất khi xử lý song song:** có thể bỏ qua record chưa hoàn tất ở giữa.
- **Dùng mock để kiểm tra serializer:** MockConsumer nhận object đã deserialize; hãy test serializer riêng hoặc dùng broker integration.
- **Giả định mock thread-safe như client thật:** chỉ thao tác từ test thread theo API mock; không dùng mock để chứng minh concurrency/network behavior.
- **Không pin Kafka client version:** test có thể compile hoặc chạy khác production.
- **Mock mọi thứ:** test chỉ xác nhận implementation giả lập, không còn bằng chứng integration với Kafka.

## 17. Chọn đúng cấp độ kiểm thử

| Cấp kiểm thử | Công cụ | Câu hỏi chính |
|---|---|---|
| Domain unit test | Fake service/interface | Business rule có đúng không? |
| Kafka adapter unit test | MockProducer/MockConsumer | Ứng dụng gọi API và xử lý callback/offset đúng không? |
| Serialization test | Serializer/Deserializer trực tiếp | Payload, header và schema có encode/decode đúng không? |
| Broker integration test | Embedded Kafka hoặc Testcontainers | Client, broker, protocol, group và transaction có tương tác đúng không? |
| Cluster/system test | Nhiều broker, controller và dependency thật | Replication, failover, ACL, quota và recovery có đạt yêu cầu không? |

Spring Kafka cung cấp `spring-kafka-test` và `@EmbeddedKafka` để chạy broker trong integration test. Testcontainers có thể khởi chạy Kafka container gần với deployment hơn và hữu ích khi cần kiểm tra image/config thực tế. Để test replication factor, ISR hoặc broker failure, cần topology nhiều broker; một broker đơn lẻ không chứng minh được behavior đó.

Kafka Streams có `TopologyTestDriver` cho kiểm thử topology và state logic ở mức test. Nó phục vụ mục đích khác với MockProducer/MockConsumer và cũng không thay thế integration test với broker.

## 18. Ví dụ chiến lược test cho Order Service

Một service xử lý đơn hàng có thể chia test như sau:

| Hành vi | Cấp test phù hợp |
|---|---|
| Chuyển trạng thái CREATED sang PAID | Domain unit test |
| Publisher tạo record đúng topic/key/header | MockProducer |
| Publisher phản ứng đúng khi callback lỗi | MockProducer |
| Consumer handler gọi đúng domain service | MockConsumer hoặc EventHandler adapter |
| Không commit khi handler thất bại | MockConsumer + poller unit test |
| JSON/Avro serializer tương thích schema | Serializer test và schema integration |
| Consumer group rebalance khi scale member | Broker integration test |
| Producer transaction và read_committed | Broker integration test |
| RF=3, ISR shrink và leader failover | Multi-broker cluster test |
| ACL/TLS/SASL | Security integration test |

Một test suite cân bằng không cần biến mọi test thành integration test. Giữ phần lớn business logic test nhanh, thêm một số integration test tập trung vào Kafka behavior thực sự cần xác minh.

## 19. Production-oriented checklist

- [ ] Service nhận `Producer`/`Consumer` qua constructor hoặc adapter để có thể inject mock.
- [ ] Unit test xác nhận topic, key, value, header và callback.
- [ ] Có test send success và send failure.
- [ ] Có test ứng dụng gọi flush/close/transaction theo lifecycle cần thiết.
- [ ] MockConsumer được assign partition trước khi nạp record.
- [ ] Có test poll, handler, seek, commit, pause/resume và assignment callback nếu ứng dụng dùng chúng.
- [ ] Không commit offset khi handler thất bại hoặc record trước đó chưa hoàn tất.
- [ ] Kafka client version của test trùng version runtime đã chọn.
- [ ] Serializer/deserializer được test riêng với payload thực tế.
- [ ] Integration test dùng broker thật cho protocol, group coordination, transaction và security.
- [ ] Multi-broker test được dùng khi cần xác minh replication, ISR hoặc failover.
- [ ] Không dùng mock history/committed map làm bằng chứng broker đã lưu dữ liệu.
- [ ] Test mock không được xem là bằng chứng hiệu năng hoặc concurrency của Kafka thật.

`MockProducer` và `MockConsumer` giúp kiểm tra nhanh cách ứng dụng sử dụng Kafka API và xử lý các nhánh thành công/thất bại có thể điều khiển. Chúng không thay thế broker, controller, replication hay group coordinator. Chọn mock cho unit test, broker thật cho integration test và multi-broker cluster cho durability/failover sẽ tạo bằng chứng phù hợp ở từng lớp.
