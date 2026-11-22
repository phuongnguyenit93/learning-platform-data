# Tạo topic, group ID và dữ liệu riêng cho từng ca kiểm thử

Một test Kafka có thể chạy đúng khi đứng một mình nhưng thất bại khi chạy song song với test khác. Nguyên nhân thường không nằm ở logic xử lý mà ở trạng thái dùng chung: hai test cùng ghi vào một topic, dùng chung `group.id` nên đọc/commit offset của nhau, hoặc đọc phải record còn sót từ lần chạy trước.

Muốn kiểm thử độc lập và lặp lại được, mỗi ca test cần có ranh giới dữ liệu rõ ràng. Thông thường nên tạo **topic riêng theo test run hoặc test case**, dùng **consumer group ID riêng**, và gắn **run ID/event ID** vào từng record. `client.id` và `transactional.id` cũng cần được quản lý riêng khi test đo metric hoặc transaction.

## 1. Ba lớp cô lập trong Kafka test

Ba loại định danh giải quyết ba vấn đề khác nhau:

| Thành phần | Cô lập điều gì? | Nếu dùng chung giữa các test |
|---|---|---|
| Topic name | Log record, partition, retention và cấu hình topic | Test có thể đọc dữ liệu của nhau, xung đột partition/config hoặc xóa dữ liệu của test khác |
| `group.id` | Consumer group membership và committed offsets | Test có thể chia partition, nhận record không như mong đợi hoặc bắt đầu từ offset cũ |
| `runId` / `eventId` trong dữ liệu | Nhận diện record thuộc test nào và phát hiện duplicate/missing | Auditor không phân biệt được dữ liệu cũ, dữ liệu của test khác và redelivery |

Ngoài ra:

- `client.id` nhận diện client trong log/metric và quota; nó không tạo consumer group mới.
- `transactional.id` nhận diện producer transaction identity; nó không thay thế topic hoặc `group.id`.
- `key` quyết định partition routing theo partitioner; dùng key riêng hay key cố định phải theo mục tiêu của test.

Vì vậy, đổi `client.id` không làm offset được cô lập. Đổi `group.id` không làm record trong topic được cô lập. Để test thật sự độc lập, phải chọn đúng lớp định danh cho từng loại state.

## 2. Chọn phạm vi topic: theo suite, run hay test case

Có ba chiến lược phổ biến:

| Chiến lược | Cách dùng | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Topic dùng chung cho cả suite | Một topic cố định cho nhiều test, mỗi test lọc record bằng run/event ID | Ít topic, setup nhanh | Phải lọc dữ liệu chính xác; cleanup và chạy song song phức tạp |
| Topic riêng cho mỗi test run | Một topic cho mỗi lần chạy suite, các test case phân biệt bằng `testCaseId` | Cô lập giữa các run, giảm số topic | Các test trong cùng run vẫn phải phân vùng dữ liệu |
| Topic riêng cho mỗi test case | Mỗi test tạo topic mới | Cô lập mạnh, cleanup đơn giản theo owner | Tạo/xóa topic nhiều, tăng metadata churn và thời gian setup |

Với integration test chạy song song, topic riêng theo test case thường dễ suy luận nhất. Với suite lớn hoặc broker dùng chung, có thể dùng topic riêng theo run và phân biệt record bằng `testCaseId`, miễn là test không đọc nhầm dữ liệu của case khác.

Trong unit test dùng broker ephemeral, tạo topic cho mỗi test case thường phù hợp vì toàn bộ broker sẽ bị hủy sau test. Trong môi trường Kafka dùng chung, cần cân bằng số topic, thời gian retention, quota và giới hạn metadata.

## 3. Quy ước tên topic dành cho test

Topic test nên có prefix riêng để phân biệt với business topic và dễ tìm khi cleanup. Một quy ước có thể dùng:

```text
it.<service>.<suite>.<run-id>.<case-id>
```

Ví dụ:

```text
it.orders.producer.20261120a.send-success
it.orders.consumer.20261120a.offset-reset
it.orders.retry.20261120a.retry-after-timeout
```

Nếu test chạy song song trên nhiều worker, thêm UUID hoặc worker ID để tránh collision:

```text
it.orders.consumer.run-a17f.worker-03.case-9c21
```

Quy tắc đặt tên:

- Dùng prefix cố định như `it.` hoặc `test.` để cleanup có thể giới hạn đúng phạm vi.
- Tên phải duy nhất giữa process, CI job và lần chạy đồng thời.
- Chuẩn hóa ký tự đầu vào; không đưa trực tiếp tên class/method tùy ý vào topic name.
- Giữ tên ngắn để không vượt giới hạn độ dài topic name của Kafka.
- Không dùng tên business topic thật trong test nếu test có thể xóa hoặc thay đổi config của topic đó.
- Không đưa thông tin nhạy cảm, token hoặc dữ liệu người dùng vào topic name.

### Tạo tên duy nhất trong Java

```java
import java.util.UUID;

public final class TestNames {
    private TestNames() {}

    public static String newRunId() {
        return UUID.randomUUID().toString().replace("-", "");
    }

    public static String topic(String runId, String suite, String testCase) {
        String safeSuite = sanitize(suite);
        String safeCase = sanitize(testCase);
        return "it.orders." + safeSuite + "." + safeCase + "." + runId;
    }

    public static String groupId(String runId, String testCase) {
        return "it.orders." + sanitize(testCase) + ".group." + runId;
    }

    private static String sanitize(String value) {
        String safe = value.toLowerCase().replaceAll("[^a-z0-9._-]", "-");
        return safe.isBlank() ? "test" : safe;
    }
}
```

Trong hệ thống lớn, nên tạo một `runId` ở đầu test run rồi truyền vào tất cả helper. Cách này giúp log, topic, group và event cùng truy được về một run. Mỗi test case vẫn có `caseId` riêng; chỉ thêm UUID cho những tài nguyên có thể được tạo song song hoặc retry.

## 4. Tạo topic tường minh bằng AdminClient

Không nên phụ thuộc vào broker tự tạo topic khi consumer/producer truy cập tên chưa tồn tại. Auto topic creation có thể tạo topic với partition count hoặc replication factor mặc định không phù hợp với test, làm test phụ thuộc cấu hình broker.

Dùng `AdminClient` để tạo topic với cấu hình đã xác định:

```java
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.NewTopic;

import java.util.Map;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

public final class TestTopicAdmin {
    private final AdminClient admin;

    public TestTopicAdmin(String bootstrapServers) {
        Properties properties = new Properties();
        properties.put("bootstrap.servers", bootstrapServers);
        this.admin = AdminClient.create(properties);
    }

    public void create(String topic, int partitions, short replicationFactor)
            throws Exception {
        NewTopic definition = new NewTopic(topic, partitions, replicationFactor)
                .configs(Map.of(
                        "cleanup.policy", "delete",
                        "retention.ms", "3600000"));

        admin.createTopics(java.util.List.of(definition))
                .all()
                .get(30, TimeUnit.SECONDS);
    }

    public void close() {
        admin.close();
    }
}
```

Ví dụ này cố ý để `TopicExistsException` làm test thất bại. Nếu topic đã tồn tại, có thể test đang tái sử dụng tài nguyên của run cũ hoặc tên chưa đủ duy nhất. Không nên bắt mọi exception rồi bỏ qua vì sẽ che giấu collision và lỗi quyền tạo topic.

### Chọn partition count và replication factor

| Môi trường | Partition | Replication factor | Mục tiêu |
|---|---:|---:|---|
| Broker đơn trong test local/CI | 1–3 | 1 | Kiểm thử logic, serialization, consumer và offset |
| Cluster test nhiều broker | Theo test case | 2 hoặc 3 nếu đủ broker | Kiểm thử replication, ISR và failover |
| Test ordering theo key | Ít nhất 1; có thể nhiều partition | Theo cluster | Xác minh key routing và thứ tự trong partition |
| Test consumer concurrency | Đủ partition để cấp cho số consumer cần thử | Theo cluster | Xác minh assignment và parallelism |

Replication factor không được lớn hơn số broker khả dụng để đặt replica. Broker đơn không thể tạo topic RF=3. Với test durability cần `acks=all` và `min.insync.replicas`, phải chạy trên cluster có đủ broker; không giả lập kết quả production bằng cách hạ RF trong test một broker.

Nếu cần kiểm tra thứ tự toàn bộ record trong một topic, dùng một partition. Nếu muốn kiểm tra per-key ordering trên nhiều partition, tạo key ổn định và xác minh các record cùng key nằm trong cùng partition. Kafka chỉ bảo đảm thứ tự trong từng partition.

## 5. Xác minh topic sau khi tạo

`createTopics().all().get()` xác nhận request tạo topic đã hoàn tất theo phản hồi Admin API, nhưng test vẫn nên xác minh cấu trúc mong muốn nếu topic được tạo bởi fixture dùng chung.

```java
var descriptions = admin.describeTopics(java.util.List.of(topic))
        .allTopicNames()
        .get(30, TimeUnit.SECONDS);

var description = descriptions.get(topic);
if (description == null || description.partitions().size() != expectedPartitions) {
    throw new AssertionError("Unexpected topic partition layout: " + topic);
}
```

Với test kiểm tra topic config, dùng `describeConfigs()` và đối chiếu các config quan trọng như `cleanup.policy`, `retention.ms`, `min.insync.replicas` và `max.message.bytes`. Đừng giả định cấu hình mặc định giữa các môi trường giống nhau.

Topic creation và metadata propagation là thao tác bất đồng bộ. Tránh `Thread.sleep()` cố định dài để chờ topic; dùng Admin API hoặc poll có deadline và báo lỗi rõ khi hết thời gian.

## 6. Dùng group ID riêng cho từng consumer test

Kafka lưu committed offset theo consumer group và topic-partition. Nếu hai test dùng cùng `group.id`, chúng có thể trở thành member của cùng group, chia partition và cùng cập nhật committed offset.

Ví dụ tình huống lỗi:

```text
Test A: group.id = order-test
Test B: group.id = order-test

Topic: orders-test, partitions = 2

Consumer A và B có thể cùng tham gia group order-test,
được assign partition khác nhau và không còn đọc cùng tập record.
```

Đối với test cần đọc toàn bộ record độc lập, mỗi test phải dùng group ID khác nhau:

```text
it.orders.consumer.case-a.group.7d...
it.orders.consumer.case-b.group.2f...
```

### Cấu hình consumer test

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ConsumerConfig.GROUP_ID_CONFIG, uniqueGroupId);
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
```

`auto.offset.reset=earliest` chỉ áp dụng khi group chưa có committed offset hợp lệ cho partition. Nếu tái sử dụng `group.id`, consumer có thể tiếp tục từ committed offset cũ; đổi `auto.offset.reset` không xóa offset đã commit. Vì vậy, group ID duy nhất là cách đơn giản để mỗi test bắt đầu từ trạng thái offset mới.

Với test transaction, thêm:

```java
props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
```

Chỉ dùng `read_committed` khi test đang xác minh transaction visibility. Với test mặc định, lựa chọn isolation phải khớp semantics cần kiểm tra; đừng vô tình che record aborted hoặc làm test khác với consumer production.

## 7. Phân biệt group ID, client ID và transactional ID

| ID | Ví dụ | Phạm vi tác động | Có cần duy nhất theo test? |
|---|---|---|---|
| `group.id` | `it.orders.group.<run>` | Membership và committed offsets của consumer group | Có, khi test cần offset độc lập |
| `client.id` | `it-orders-consumer-<run>` | Log, metric, quota và nhận diện client | Nên có để truy vết |
| `transactional.id` | `it-orders-producer-<run>` | Producer transaction identity và fencing | Có, khi nhiều producer transaction chạy song song |
| Topic name | `it.orders.<run>.<case>` | Record log, partition và topic config | Có, nếu cần log độc lập |
| Event ID | `run-123:case-a:0001` | Nhận diện một event trong dữ liệu | Có, để audit và dedupe |

Không dùng một `transactional.id` cố định cho nhiều producer test chạy đồng thời: producer khởi tạo cùng transactional ID có thể fence producer trước. Nếu test cố ý kiểm tra fencing, hãy dùng chung ID có chủ đích và tách khỏi các test khác.

## 8. Gắn run ID và event ID vào từng record

Ngay cả khi topic riêng, record vẫn nên mang metadata để debug và audit:

```json
{
  "runId": "run-7d12c9",
  "testCaseId": "consumer-replay",
  "eventId": "run-7d12c9:consumer-replay:000042",
  "key": "order-1001",
  "sequence": 42,
  "createdAtEpochMs": 1795178165000,
  "payload": {
    "status": "PAID"
  }
}
```

Nên có:

- `runId`: liên kết log, topic, group và report của một lần chạy.
- `testCaseId`: phân biệt test case khi một topic được dùng chung trong suite.
- `eventId`: duy nhất để tìm duplicate, missing và redelivery.
- `key`: entity dùng cho partition routing.
- `sequence`: kiểm tra thứ tự trong phạm vi key nếu nghiệp vụ yêu cầu.
- `createdAt`: đo event age hoặc end-to-end latency khi đồng hồ đã đồng bộ.

Không tạo key ngẫu nhiên nếu test đang kiểm tra per-key ordering. Hãy dùng một key cố định cho toàn bộ sequence của entity đó; nếu test partition distribution, tạo tập key có phân bố đã định trước.

Có thể đưa `runId` và `testCaseId` vào Kafka headers thay vì payload nếu không muốn thay schema nghiệp vụ. Tuy nhiên, auditor và consumer test phải đọc cùng một convention; không để mỗi test tự đặt tên header khác nhau.

## 9. Producer test gửi dữ liệu có thể đối chiếu

Producer fixture nên gửi record và đợi acknowledgement trước khi consumer bắt đầu kiểm tra. Nhờ đó, test không nhầm producer chưa gửi xong với consumer bị mất record.

```java
Properties producerProps = new Properties();
producerProps.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
producerProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
producerProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
producerProps.put(ProducerConfig.CLIENT_ID_CONFIG, uniqueClientId);

try (KafkaProducer<String, String> producer = new KafkaProducer<>(producerProps)) {
    for (int sequence = 1; sequence <= 3; sequence++) {
        String eventId = runId + ":" + testCaseId + ":" + sequence;
        String value = "{\"runId\":\"" + runId + "\","
                + "\"testCaseId\":\"" + testCaseId + "\","
                + "\"eventId\":\"" + eventId + "\","
                + "\"sequence\":" + sequence + "}";

        producer.send(new ProducerRecord<>(topic, "order-1001", value)).get();
    }
    producer.flush();
}
```

Trong code production, nên dùng JSON serializer/object mapper thay vì nối chuỗi JSON. Ví dụ trên chỉ minh họa cách gắn ID và chờ send result. Nếu test muốn kiểm tra async throughput, hãy gửi bất đồng bộ có giới hạn in-flight và đợi tất cả callback/future hoàn tất trước khi audit.

## 10. Consumer test đọc đúng dữ liệu của mình

Với topic và group ID riêng, consumer có thể đọc từ đầu bằng `auto.offset.reset=earliest`. Đặt deadline thay vì vòng lặp vô hạn:

```java
Map<String, Integer> receivedCounts = new HashMap<>();
Set<String> expectedEventIds = Set.of("run-1:case-a:1", "run-1:case-a:2", "run-1:case-a:3");
int expectedCount = expectedEventIds.size();
long deadline = System.nanoTime() + Duration.ofSeconds(10).toNanos();

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(consumerProps)) {
    consumer.subscribe(List.of(topic));

    while (receivedCounts.values().stream().mapToInt(Integer::intValue).sum() < expectedCount
            && System.nanoTime() < deadline) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(200));

        for (ConsumerRecord<String, String> record : records) {
            receivedCounts.merge(extractEventId(record.value()), 1, Integer::sum);
        }
    }
}

int receivedTotal = receivedCounts.values().stream()
        .mapToInt(Integer::intValue)
        .sum();
boolean hasDuplicate = receivedCounts.values().stream().anyMatch(count -> count > 1);

if (receivedTotal != expectedCount
        || !receivedCounts.keySet().equals(expectedEventIds)
        || hasDuplicate) {
    throw new AssertionError("Expected " + expectedCount + " unique events, received "
            + receivedTotal + " records and " + receivedCounts.size() + " unique IDs");
}
```

Đây là ví dụ rút gọn; `expectedEventIds` phải được tạo từ fixture của chính test, còn `extractEventId()` cần parse payload theo schema test. So sánh tập ID giúp phát hiện cả missing lẫn unexpected ID; bộ đếm giúp phát hiện duplicate. Khi cần xác minh offset commit, phải đọc lại committed offset qua Admin API hoặc restart consumer cùng group trong một test riêng có chủ đích.

Consumer group mới cần thời gian join và nhận partition assignment. `poll()` đầu tiên có thể chỉ thực hiện join/rebalance mà chưa trả record; vòng lặp có deadline xử lý điều đó. Không dùng `Thread.sleep()` cố định để đoán khi nào assignment hoàn tất.

## 11. Dữ liệu riêng cho từng loại test

| Loại test | Topic | Group ID | Data/key strategy |
|---|---|---|---|
| Producer send/serialization | Topic riêng cho test | Không cần nếu không consume | Event ID riêng, key theo test |
| Consumer deserialize | Topic riêng | Group riêng | Payload theo schema/edge case |
| Offset reset/replay | Topic riêng | Group mới mỗi scenario | Gửi trước, sau đó tạo consumer group và kiểm tra `earliest`/`latest` |
| Consumer group rebalance | Topic riêng, đủ partition | Một group dùng chung có chủ đích giữa các member trong cùng scenario | Các member thuộc một test scenario; không chia sẻ với test khác |
| Per-key ordering | Topic riêng | Group riêng | Cùng key, sequence tăng dần |
| Transaction visibility | Topic riêng | Group riêng với `read_committed` | Có transaction commit và abort trong cùng test |
| Retry/DLT | Topic chính, retry và DLT riêng | Group riêng | Event ID xuyên suốt để kiểm tra retry/duplicate |
| Replication/failover | Topic trên cluster test nhiều broker | Group riêng nếu consume | Record ID và offset trước/sau failure |

Một ngoại lệ quan trọng: test rebalance cần nhiều consumer member cùng tham gia **một group** để kiểm tra partition assignment. Trong scenario đó, các member phải dùng cùng `group.id` theo chủ đích; sự cô lập đạt được bằng cách cấp group/topic riêng cho toàn bộ scenario, không phải mỗi member một group.

## 12. Cô lập dữ liệu khi chạy test song song

Khi JUnit/Gradle/Maven chạy test song song hoặc CI tạo nhiều job, tên tài nguyên phải chứa một định danh duy nhất ở cấp run/job/worker/test.

Ví dụ:

```text
it.orders.run-7d12.worker-1.producer-send
it.orders.run-7d12.worker-1.consumer-read
it.orders.run-9a31.worker-2.consumer-read
```

Nguyên tắc:

- Tạo `runId` một lần cho mỗi JVM hoặc CI job.
- Tạo `caseId` cho mỗi test method/scenario.
- Nếu test chạy song song trong cùng JVM, thêm UUID hoặc worker index vào tài nguyên được tạo.
- Không chia sẻ `KafkaConsumer` hoặc `KafkaProducer` giữa test nếu lifecycle không được đồng bộ.
- Mỗi test sở hữu tài nguyên nào thì chỉ cleanup tài nguyên đó.
- Nếu dùng topic theo suite, tất cả record phải có `testCaseId` và consumer phải filter đúng; không chỉ dựa vào timestamp.

## 13. Cleanup topic và consumer group an toàn

Topic và consumer group là tài nguyên trên broker, không tự biến mất khi test process kết thúc. Cần cleanup rõ ràng hoặc dùng broker ephemeral.

### Cleanup theo ownership

Một test chỉ được xóa topic do chính test tạo và có tên nằm trong namespace test riêng. Không xóa theo pattern rộng như `orders.*` hoặc `.*test.*` trên cluster dùng chung.

Ví dụ:

```java
admin.deleteTopics(List.of(ownedTopic))
        .all()
        .get(30, TimeUnit.SECONDS);
```

`deleteTopics()` trả kết quả theo Admin API; việc xóa vật lý segment có thể diễn ra bất đồng bộ. Broker phải cho phép topic deletion (`delete.topic.enable=true`). Không tái sử dụng ngay tên topic vừa xóa; tạo tên mới cho test tiếp theo để tránh race với metadata/cleanup.

### Xóa consumer group

Chỉ xóa group sau khi tất cả consumer member đã đóng và group không còn active:

```java
admin.deleteConsumerGroups(List.of(ownedGroupId))
        .all()
        .get(30, TimeUnit.SECONDS);
```

Nếu group còn member, broker có thể trả lỗi group not empty hoặc deletion chưa hoàn tất. Đóng consumer trong `finally`/try-with-resources trước khi cleanup group. Nếu test không cần xóa group ngay, unique group ID và retention của `__consumer_offsets` có thể đủ; không nên tạo cleanup race không cần thiết.

### Thứ tự cleanup

1. Dừng producer và chờ callback/future hoàn tất.
2. Đóng consumer để rời group.
3. Chờ test assertion/audit hoàn tất.
4. Xóa consumer group nếu test sở hữu group và cần dọn ngay.
5. Xóa topic nếu test sở hữu topic và broker cho phép deletion.
6. Đóng AdminClient và các tài nguyên khác.

Nếu test thất bại, lưu run ID, topic name, group ID và event ID trong report trước cleanup để vẫn điều tra được. Có thể giữ tài nguyên trong một khoảng thời gian ngắn khi CI failure, nhưng phải có TTL/cleanup job riêng để không làm đầy cluster test.

## 14. Dùng Kafka broker ephemeral với Testcontainers

Với integration test, broker ephemeral giúp test không phụ thuộc topic, group offset hoặc dữ liệu từ cluster developer/CI dùng chung. Mỗi test suite hoặc test class có thể khởi động một Kafka container, tạo topic/group riêng rồi hủy container sau khi hoàn tất.

Ví dụ cấu trúc JUnit/Testcontainers (API import và image tag phụ thuộc phiên bản Testcontainers được dự án khóa):

```java
@Testcontainers
class OrderConsumerIT {

    @Container
    static final KafkaContainer kafka = new KafkaContainer(
            DockerImageName.parse("apache/kafka-native:3.8.0"));

    @Test
    void consumesOnlyEventsFromThisCase() throws Exception {
        String runId = UUID.randomUUID().toString();
        String topic = "it.orders." + runId.replace("-", "");
        String groupId = "it.orders.group." + runId;

        // Tạo topic, producer và consumer bằng kafka.getBootstrapServers().
        // Cleanup hoặc để container bị hủy sau test class.
    }
}
```

Container riêng giúp cô lập broker state mạnh hơn, nhưng khởi động container cho từng method có thể chậm. Có thể dùng một container cho test class/suite và vẫn tạo topic/group ID riêng cho từng test case. Nếu test nhiều broker, replication hoặc failover, phải khởi chạy topology test đủ broker thay vì dùng một broker container đơn.

Nếu dùng embedded broker hoặc broker dùng chung, nguyên tắc đặt topic/group/data riêng vẫn áp dụng. Ephemeral broker không thay thế việc kiểm soát test parallelism và resource lifecycle.

## 15. Các lỗi cô lập thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test đọc được record từ lần chạy trước | Topic dùng chung hoặc group có committed offset cũ | Tạo topic/group mới; gắn run ID vào record |
| Hai test nhận mỗi test một phần record | Dùng chung `group.id` và cùng subscribe topic | Dùng group riêng; chỉ chia group khi test rebalance có chủ đích |
| Consumer không đọc record đã gửi | `auto.offset.reset=latest`, group đã có offset hoặc consumer bắt đầu sau dữ liệu | Dùng group mới và cấu hình reset phù hợp; kiểm tra offset thực tế |
| Test chạy riêng pass nhưng chạy song song fail | Topic/group/client/transactional ID bị collision | Thêm run/worker/case ID vào tài nguyên |
| Topic đã tồn tại khi test bắt đầu | Tên không unique hoặc cleanup lần trước chưa hoàn tất | Fail rõ ràng, tạo suffix mới, kiểm tra owner |
| Test bị timeout chờ consumer | Consumer chưa assign, producer chưa ack hoặc topic chưa sẵn sàng | Poll với deadline, chờ send future, kiểm tra partition metadata |
| Test rebalance không tái hiện | Mỗi consumer dùng group ID khác nhau | Tất cả member trong scenario dùng cùng group ID riêng của scenario |
| Xóa nhầm topic khác | Cleanup theo prefix quá rộng hoặc namespace trùng | Chỉ xóa exact topic do test sở hữu |
| Transaction test bị producer fence | Nhiều producer dùng cùng `transactional.id` | Dùng transactional ID duy nhất, trừ test fencing có chủ đích |
| Test bị ảnh hưởng bởi topic config mặc định | Dựa vào auto-create hoặc broker defaults | Tạo topic explicit và verify config |

## 16. Quy trình tạo fixture dùng chung cho test suite

Một fixture có thể cung cấp các bước chuẩn hóa:

1. Tạo `runId` và `testCaseId`.
2. Sinh topic name, group ID và client ID theo convention.
3. Dùng AdminClient tạo topic với partition/RF/config phù hợp broker test.
4. Describe topic và xác nhận partition count/config.
5. Tạo producer/consumer với ID riêng; tắt auto commit nếu test kiểm soát offset.
6. Gửi test data có `runId`, `eventId`, `testCaseId` và sequence.
7. Chờ producer acknowledgement trước khi bắt đầu assertion phụ thuộc dữ liệu.
8. Consumer poll với deadline; xác minh event ID, count, key, partition và sequence.
9. Đọc committed offset nếu scenario cần kiểm tra commit/replay.
10. Đóng client và cleanup đúng tài nguyên do fixture sở hữu.

Fixture không nên tự động xóa mọi topic có prefix test trên cluster. Nó chỉ quản lý danh sách tài nguyên được tạo trong chính run đó. Nếu fixture được chia sẻ giữa test class, ownership và lifecycle phải rõ ràng để một class không xóa topic mà class khác vẫn đang dùng.

## 17. Checklist trước khi chạy Kafka integration test

- [ ] Mỗi test run có `runId` duy nhất.
- [ ] Topic có namespace test và không trùng business topic.
- [ ] Quyết định topic riêng theo run hay theo test case.
- [ ] Topic được tạo tường minh với partition/RF/config phù hợp môi trường.
- [ ] Test xác minh topic metadata sau khi tạo.
- [ ] Consumer group ID riêng cho từng scenario cần offset độc lập.
- [ ] Consumer member dùng chung group ID chỉ khi scenario đang kiểm tra group coordination/rebalance.
- [ ] `auto.offset.reset` được chọn có chủ đích; không nhầm nó với thao tác reset committed offset.
- [ ] `client.id` giúp truy vết; `transactional.id` không collision khi chạy song song.
- [ ] Record có run ID, test case ID và event ID để audit.
- [ ] Key/sequence phản ánh đúng mục tiêu partition/order test.
- [ ] Producer send được acknowledge trước assertion phụ thuộc dữ liệu.
- [ ] Consumer poll có deadline và kiểm tra assignment/record count rõ ràng.
- [ ] Cleanup chỉ xóa topic/group do test sở hữu.
- [ ] Broker ephemeral hoặc shared broker được chọn phù hợp loại test.
- [ ] Khi test fail, report giữ lại topic/group/run ID để điều tra.

## Tài liệu tham khảo

- [Apache Kafka Admin API](https://kafka.apache.org/documentation/#adminapi)
- [Apache Kafka Consumer Configs — `group.id`, `auto.offset.reset`, `enable.auto.commit`](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka Topic Configs](https://kafka.apache.org/documentation/#topicconfigs)
- [Testcontainers for Apache Kafka](https://java.testcontainers.org/modules/kafka/)

Kiểm thử Kafka độc lập cần cô lập cả topic log, consumer group offsets và record data. Topic name riêng ngăn test ghi/đọc lẫn nhau; `group.id` riêng ngăn committed offset và membership bị chia sẻ; `runId`/`eventId` giúp truy vết dữ liệu và phát hiện duplicate. Khi tài nguyên được tạo tường minh, xác minh sau setup và cleanup đúng ownership, test có thể chạy song song và lặp lại mà ít phụ thuộc trạng thái broker còn sót.
