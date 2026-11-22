# Queues for Kafka và nhu cầu chia việc theo từng bản ghi

Kafka truyền thống dùng consumer group để chia partition cho các consumer. Cách này rất phù hợp với xử lý luồng cần giữ thứ tự trong từng partition, nhưng số consumer có thể làm việc song song trong một group bị giới hạn bởi số partition đang được phân phối. Với workload dạng hàng đợi, nơi mỗi record là một công việc độc lập và nhiều worker có thể cùng lấy việc từ một partition, mô hình đó đôi khi buộc hệ thống phải tăng partition chỉ để tăng số worker.

Kafka Share Groups (KIP-932, còn gọi là Queues for Kafka) bổ sung một kiểu group khác để giải quyết nhu cầu này. Nhiều share consumer trong cùng group có thể cùng đọc record từ một partition; broker cấp từng record cho một consumer bằng acquisition lock có thời hạn. Consumer xử lý xong thì acknowledge record; nếu lỗi tạm thời thì release để worker khác thử lại; nếu dữ liệu không thể xử lý thì reject. Kafka theo dõi delivery count để giới hạn số lần giao và tránh poison message lặp vô hạn.

Share Groups production-ready từ Apache Kafka 4.2. Kafka 4.1 chỉ cung cấp preview và Kafka 4.0 là early access. Bài thực hành sử dụng Java KafkaShareConsumer với kafka-clients 4.2.2. Share Group phù hợp với công việc độc lập theo từng record; consumer group truyền thống vẫn phù hợp hơn khi cần thứ tự theo partition.

## 1. Vì sao cần Share Groups?

Giả sử topic image.jobs có 3 partition và hệ thống có 12 worker xử lý ảnh. Với consumer group truyền thống, tại một thời điểm mỗi partition chỉ được gán cho một member trong group. Dù có 12 worker, tối đa 3 worker có partition để đọc; các worker còn lại không nhận được công việc từ group đó.

Với share group, nhiều member có thể được gán cùng một share-partition. Broker cấp các record khác nhau trong partition cho các member khác nhau. Nhờ vậy 12 worker có thể cùng xử lý công việc từ 3 partition mà không cần tạo 12 partition chỉ để đạt số worker đó.

| Nhu cầu | Consumer group | Share group |
|---|---|---|
| Một partition được nhiều consumer trong cùng group cùng đọc | Không; partition được gán độc quyền cho một member tại một thời điểm | Có; nhiều member có thể chia sẻ một partition |
| Số consumer lớn hơn số partition | Member dư có thể không được gán partition | Có thể có nhiều member hơn partition |
| Tiến độ | Committed offset theo partition | Trạng thái giao nhận/ack theo record |
| Xác nhận xử lý | Commit offset | Acknowledge record với ACCEPT, RELEASE, REJECT hoặc RENEW |
| Ordering | Thứ tự record trong partition được bảo toàn khi xử lý tuần tự theo partition | Không bảo đảm thứ tự hoàn tất giữa các batch và các lần giao lại |
| Mục đích | Đọc stream, xử lý theo partition | Chia hàng đợi công việc cho nhiều worker |

Share Group không broadcast một record cho tất cả member. Mỗi record được cấp cho một consumer tại một thời điểm trong cùng share group. Nếu cần nhiều ứng dụng độc lập cùng nhận toàn bộ dữ liệu, hãy tạo nhiều group khác nhau; mỗi group sẽ tiêu thụ topic độc lập.

## 2. Mô hình chia sẻ record

Một share group có một group ID và một tập consumer tham gia. Các consumer đăng ký topic bằng KafkaShareConsumer.subscribe(). Group coordinator quản lý membership và phân phối share-partition; share-partition leader cấp record và xử lý acknowledgement; share coordinator lưu trạng thái share-partition bền vững.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Topic: image.jobs] --> B[Partition 0]
    A --> C[Partition 1]
    A --> D[Partition 2]
    B --> E[Share Group: image-workers]
    C --> E
    D --> E
    E --> F[Worker 1]
    E --> G[Worker 2]
    E --> H[Worker 3]
    E --> I[Worker 4]
    F --> J[ACK / RELEASE / REJECT]
    G --> J
    H --> J
    I --> J
    J --> K[Share-partition state]
~~~

Mỗi consumer trong cùng group có thể được gán cùng partition với consumer khác. Assignment cho biết member có thể lấy record từ partition đó; assignment không có nghĩa member sở hữu độc quyền partition.

Ví dụ:

| Partition | Worker nhận record |
|---|---|
| image.jobs-0 | Worker A, Worker B, Worker C |
| image.jobs-1 | Worker A, Worker D |
| image.jobs-2 | Worker B, Worker C, Worker D |

Broker cấp từng record cho một worker đang có khả năng xử lý. Hai worker không đồng thời giữ acquisition lock hợp lệ cho cùng một record trong cùng share group.

## 3. Share Group khác Consumer Group ở đâu?

Consumer group theo dõi một offset đã commit cho mỗi topic-partition. Consumer xử lý record theo thứ tự trong partition và commit offset tiếp theo cần đọc. Một record lỗi có thể giữ partition ở vị trí đó cho đến khi retry hoặc recovery hoàn tất.

Share group theo dõi trạng thái của từng record trong share-partition. Khi record được fetch, broker đánh dấu record là acquired cho một consumer và đặt thời hạn lock. Consumer acknowledge kết quả xử lý. Những record khác trong cùng partition vẫn có thể được cấp cho member khác trong lúc record đang acquired.

| Đặc điểm | Consumer group | Share group |
|---|---|---|
| Đơn vị phân phối | Partition | Record, được lấy theo batch để tối ưu |
| Đơn vị tiến độ | Offset commit | Record state và share-partition start offset |
| Cơ chế giao lại | Offset chưa commit được đọc lại sau restart/rebalance | Lock hết hạn hoặc RELEASE làm record sẵn sàng giao lại |
| Poison record | Thường cần error handler/retry/DLT ở ứng dụng | Có delivery count limit; REJECT hoặc hết giới hạn sẽ archive |
| Phân phối | Một member sở hữu partition tại một thời điểm | Nhiều member có thể cùng chia sẻ partition |
| Ordering | Phù hợp với xử lý tuần tự theo partition | Không có strict ordering giữa các batch/lần giao |

Share Group không xóa record khỏi Kafka topic sau khi xử lý. Kafka vẫn giữ dữ liệu theo retention và compaction policy của topic; trạng thái acknowledged/archived chỉ điều khiển việc share group có tiếp tục giao record đó hay không.

## 4. Trạng thái của record trong share-partition

Kafka quản lý bốn trạng thái cơ bản:

| Trạng thái | Ý nghĩa |
|---|---|
| Available | Record có thể được cấp cho consumer |
| Acquired | Record đang được giao cho một consumer và có acquisition lock |
| Acknowledged | Consumer đã xác nhận xử lý thành công |
| Archived | Record không còn đủ điều kiện được giao cho share consumer |

Luồng trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Available
    Available --> Acquired: poll nhận record
    Acquired --> Acknowledged: ACCEPT
    Acquired --> Available: RELEASE hoặc lock timeout
    Acquired --> Archived: REJECT hoặc delivery limit reached
    Acknowledged --> Archived: share start offset tiến qua record
~~~

Mỗi lần record được acquired, delivery count tăng lên. Lần đầu thường là 1. Nếu consumer RELEASE record hoặc lock hết hạn trước khi đạt delivery count limit, record trở lại Available và có thể được giao cho worker khác. Khi chạm giới hạn giao, record không còn được giao lại và chuyển sang Archived.

Delivery count được lưu trong share-partition state, nhưng không phải bộ đếm kiểm toán chính xác tuyệt đối. Việc cập nhật state không có exactly-once semantics; nên dùng nó để ngăn poison message lặp vô hạn, không dùng làm bằng chứng duy nhất về số lần thực thi nghiệp vụ.

## 5. Acquisition lock và xử lý khi worker lỗi

Khi consumer gọi poll(Duration), broker trả về các record đang Available và đặt acquisition lock cho consumer nhận chúng. Trong thời gian lock còn hiệu lực, consumer khác trong cùng share group không được nhận các record đó.

Nếu worker xử lý thành công và gửi ACCEPT, record được xác nhận. Nếu worker chết, mất kết nối hoặc không acknowledge trước khi lock hết hạn, record có thể được giao lại. Nếu lỗi được phát hiện sớm, consumer có thể chủ động RELEASE để record sớm trở lại hàng đợi.

Kafka 4.2 có các giá trị broker mặc định đáng chú ý:

| Broker property | Mặc định Kafka 4.2 | Ý nghĩa |
|---|---:|---|
| group.share.record.lock.duration.ms | 30.000 ms | Thời hạn acquisition lock |
| group.share.min.record.lock.duration.ms | 15.000 ms | Thời hạn tối thiểu broker cho phép |
| group.share.max.record.lock.duration.ms | 60.000 ms | Thời hạn tối đa broker cho phép |
| group.share.delivery.count.limit | 5 | Số lần giao tối đa trước khi archive |
| group.share.partition.max.record.locks | 2.000 | Số record lock tối đa trên mỗi share-partition |
| group.share.max.size | 200 | Số member tối đa trong một share group |

Giá trị có thể thay đổi theo phiên bản và cấu hình cluster. Quản trị viên có thể đặt dynamic group config share.record.lock.duration.ms cho group trong phạm vi broker cho phép. Không đặt lock quá ngắn nếu thời gian xử lý có dao động; lock quá dài làm record lỗi phải chờ lâu hơn trước khi được giao lại.

Với xử lý có thời gian dài hơn lock duration, có thể dùng acknowledgement RENEW để gia hạn lock trong khi công việc vẫn chạy. RENEW chỉ dùng với explicit acknowledgement; consumer vẫn phải gọi poll định kỳ và theo dõi kết quả gia hạn.

## 6. Acknowledge type: ACCEPT, RELEASE, REJECT và RENEW

Share Consumer API có bốn kiểu acknowledge:

| Type | Ý nghĩa | Khi dùng |
|---|---|---|
| ACCEPT | Record đã xử lý thành công | Side effect nghiệp vụ đã hoàn tất |
| RELEASE | Xử lý chưa thành công, record có thể được giao lại | Timeout, dependency tạm thời unavailable |
| REJECT | Record không thể xử lý và không được giao lại | Payload sai vĩnh viễn hoặc lỗi nghiệp vụ không thể phục hồi |
| RENEW | Công việc vẫn đang xử lý; gia hạn acquisition lock | Job dài hơn lock duration |

REJECT không tự động gửi record sang Dead Letter Topic. Nếu muốn lưu record lỗi để điều tra, ứng dụng phải publish record sang DLT/quarantine topic trước khi REJECT. Nếu publish DLT thành công nhưng acknowledgement thất bại, record có thể được giao lại và DLT có thể nhận duplicate; dùng eventId ổn định để DLT consumer idempotent.

Khi RELEASE hoặc lock timeout làm record được giao lại, delivery count tăng. Khi delivery count chạm giới hạn, record bị archive. Nếu cần giữ payload poison message, hãy chủ động route sang DLT trước khi record đạt giới hạn hoặc khi ứng dụng phát hiện lỗi vĩnh viễn.

## 7. Ordering và hệ quả của chia việc theo record

Share Group ưu tiên phân phối công việc linh hoạt hơn thứ tự xử lý. Trong cùng một poll batch, record của một partition được trả theo offset tăng dần; nhưng giữa các batch không có bảo đảm thứ tự hoàn tất. Redelivery càng làm thứ tự dễ thay đổi.

Ví dụ một partition có record offset 100 đến 109:

1. Worker A nhận 100–109 rồi bị crash.
2. Worker B nhận 110–119 và xử lý thành công.
3. Lock của A hết hạn; 100–109 trở lại Available.
4. Worker C nhận lại 100–109 với delivery count tăng.
5. Hệ thống đã hoàn tất 110–119 trước khi hoàn tất 100–109.

Do đó, Share Group không phù hợp nếu nghiệp vụ yêu cầu mọi event của một order/account phải được áp dụng theo đúng thứ tự. Nếu thứ tự là yêu cầu bắt buộc, dùng consumer group với key/partition phù hợp hoặc thiết kế tuần tự hóa theo aggregate ở tầng nghiệp vụ.

Nếu thứ tự không quan trọng nhưng không muốn áp dụng event cũ lên trạng thái mới, hãy đưa sequence/version vào payload và kiểm tra trước khi cập nhật database. Dùng idempotency key để tránh áp dụng side effect hai lần.

## 8. Khi nào nên dùng Share Group?

Share Group phù hợp khi mỗi record là một công việc tương đối độc lập:

- Xử lý thumbnail, resize ảnh, OCR hoặc phân tích file.
- Gửi email, SMS, push notification.
- Gọi webhook hoặc đồng bộ dữ liệu tới API ngoài.
- Chạy tác vụ enrichment, kiểm tra hoặc phân loại từng event.
- Work queue có số worker thay đổi theo tải và không cần ordering theo partition.

Không nên chọn Share Group chỉ vì muốn tăng số consumer. Cần cân nhắc:

| Điều kiện nghiệp vụ | Lựa chọn |
|---|---|
| Cần xử lý mọi event theo thứ tự trong partition | Consumer group |
| Mỗi record độc lập, nhiều worker cùng lấy việc | Share group |
| Cần broadcast toàn bộ event đến nhiều ứng dụng | Nhiều group độc lập |
| Cần xử lý event theo key/aggregate và giữ sequence | Consumer group với partition key phù hợp |
| Có poison record và cần per-record retry/reject | Share group hoặc consumer group kết hợp error handling, tùy yêu cầu ordering |

Share Group vẫn cần topic partition để lưu trữ và phân phối dữ liệu. Việc nhiều member chia sẻ partition không loại bỏ nhu cầu chọn partition count hợp lý cho throughput, broker load, keying và replication.

## 9. Phiên bản Kafka và dependency Java

Share Groups được triển khai theo lộ trình:

| Kafka version | Trạng thái |
|---|---|
| 4.0 | Early access, chỉ dùng làm quen/thử nghiệm |
| 4.1 | Preview, chưa khuyến nghị production |
| 4.2 trở lên | KIP-932 production-ready |

Thêm Kafka client 4.2.2 vào Maven:

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-clients</artifactId>
    <version>4.2.2</version>
</dependency>
~~~

Ví dụ dùng Java record ở phần lab, nên dùng JDK 17 trở lên. Client và broker cần có phiên bản hỗ trợ Share Consumer API; nếu client gọi API mà broker chưa hỗ trợ, có thể nhận UnsupportedVersionException. Kiểm tra compatibility matrix và release notes trước khi nâng cấp.

Share Consumer API có interface riêng là ShareConsumer và implementation KafkaShareConsumer. Không thay KafkaConsumer bằng KafkaShareConsumer rồi giữ nguyên toàn bộ logic offset commit cũ; mô hình tiến độ và acknowledgement khác nhau.

## 10. Cấu hình broker và internal state topic

Share Group dùng internal topic __share_group_state để lưu trạng thái share-partition. Kafka tự tạo topic này khi cluster bắt đầu sử dụng Share Groups.

Kafka 4.2 có mặc định:

~~~properties
share.coordinator.state.topic.replication.factor=3
share.coordinator.state.topic.min.isr=2
share.coordinator.state.topic.num.partitions=50
~~~

Với cluster ít hơn ba broker, phải đặt replication factor và min ISR phù hợp trước khi bắt đầu sử dụng Share Groups, ví dụ cho lab một broker:

~~~properties
share.coordinator.state.topic.replication.factor=1
share.coordinator.state.topic.min.isr=1
~~~

Đây là cấu hình riêng cho lab một broker. Production nên giữ replication factor và min ISR phù hợp durability; không giảm cấu hình chỉ để tránh lỗi tạo internal topic. Số partition của __share_group_state không nên thay đổi sau khi triển khai.

Một số broker settings khác có thể điều chỉnh theo workload:

~~~properties
group.share.record.lock.duration.ms=30000
group.share.delivery.count.limit=5
group.share.partition.max.record.locks=2000
group.share.max.size=200
~~~

Các giá trị trên là mặc định Kafka 4.2, không phải cấu hình tối ưu cho mọi hệ thống. Thay đổi lock duration, delivery limit hoặc số record lock cần dựa trên processing latency, concurrency và tải coordinator.

## 11. Cấu hình Java KafkaShareConsumer

Share consumer cần bootstrap server, group.id, deserializer và acknowledgement mode. Ví dụ dùng explicit acknowledgement để ứng dụng quyết định kết quả từng record:

~~~java
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaShareConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

import java.util.Properties;

Properties properties = new Properties();
properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
properties.put(ConsumerConfig.GROUP_ID_CONFIG, "image-workers");
properties.put(ConsumerConfig.CLIENT_ID_CONFIG, "image-worker-01");
properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
properties.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, "10");
properties.put("share.acknowledgement.mode", "explicit");
properties.put("share.acquire.mode", "record_limit");

KafkaShareConsumer<String, String> consumer =
        new KafkaShareConsumer<>(properties);
~~~

share.acknowledgement.mode có hai lựa chọn:

- implicit: lần poll kế tiếp tự acknowledge các record đã trả về ở poll trước; commitSync/commitAsync cũng commit acknowledgement đang chờ.
- explicit: ứng dụng phải acknowledge từng record trước lần poll kế tiếp; nếu poll khi còn record chưa acknowledge, client ném IllegalStateException.

Với ứng dụng có phân loại lỗi theo từng record, explicit thường dễ kiểm soát hơn. Không dùng enable.auto.commit hoặc auto.commit.interval.ms như consumer group truyền thống; Share Groups không hỗ trợ auto-commit offset.

share.acquire.mode có hai lựa chọn:

- batch_optimized (mặc định): tối ưu theo batch boundaries; số record trả về có thể vượt max.poll.records và client có thể prefetch.
- record_limit: mỗi poll trả không quá max.poll.records và không prefetch; phù hợp hơn khi thời gian xử lý dài hoặc cần kiểm soát số record đang acquired.

## 12. Ví dụ xử lý record với explicit acknowledgement

Ví dụ sau mô phỏng worker xử lý image job. Lỗi tạm thời sẽ RELEASE để thử lại; lỗi dữ liệu vĩnh viễn sẽ ghi DLT rồi REJECT; xử lý thành công sẽ ACCEPT.

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaShareConsumer;
import org.apache.kafka.clients.consumer.AcknowledgeType;
import org.apache.kafka.common.errors.WakeupException;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ImageShareWorker {
    private final AtomicBoolean closed = new AtomicBoolean(false);
    private final KafkaShareConsumer<String, String> consumer;

    public ImageShareWorker(Properties properties) {
        this.consumer = new KafkaShareConsumer<>(properties);
    }

    public void run() {
        try {
            consumer.subscribe(List.of("image.jobs"));

            while (!closed.get()) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofSeconds(1));

                for (ConsumerRecord<String, String> record : records) {
                    try {
                        processImageJob(record.value());
                        consumer.acknowledge(record, AcknowledgeType.ACCEPT);
                    } catch (TemporaryDependencyException exception) {
                        logRetry(record, exception);
                        consumer.acknowledge(record, AcknowledgeType.RELEASE);
                    } catch (InvalidJobException exception) {
                        try {
                            publishToDlt(record, exception);
                            consumer.acknowledge(record, AcknowledgeType.REJECT);
                        } catch (Exception dltFailure) {
                            logDltFailure(record, dltFailure);
                            consumer.acknowledge(record, AcknowledgeType.RELEASE);
                        }
                    }
                }

                var commitErrors = consumer.commitSync();
                commitErrors.forEach((partition, error) -> {
                    if (error.isPresent()) {
                        System.err.printf(
                                "ack commit failed for %s: %s%n",
                                partition, error.get().getMessage());
                    }
                });
            }
        } catch (WakeupException exception) {
            if (!closed.get()) {
                throw exception;
            }
        } finally {
            consumer.close(Duration.ofSeconds(10));
        }
    }

    public void shutdown() {
        closed.set(true);
        consumer.wakeup();
    }

    private void processImageJob(String payload) {
        // Validate and process one image job.
    }

    private void publishToDlt(
            ConsumerRecord<String, String> record,
            Exception exception) {
        // Publish original key/value plus source metadata and error details.
        // Wait for producer send result before returning.
    }

    private void logRetry(
            ConsumerRecord<String, String> record,
            Exception exception) {
        // Record event ID, topic, partition, offset and delivery count.
    }

    private void logDltFailure(
            ConsumerRecord<String, String> record,
            Exception exception) {
        // Alert; the record is released for another attempt.
    }

    private static final class TemporaryDependencyException extends RuntimeException {
    }

    private static final class InvalidJobException extends RuntimeException {
    }
}
~~~

Trong explicit mode, acknowledge() cập nhật trạng thái cục bộ của consumer; commitSync() mới gửi acknowledgement state tới Kafka. Giá trị trả về của commitSync là map kết quả theo topic-partition. Nếu một partition có lỗi commit, record liên quan có thể được giao lại; ứng dụng phải log/alert lỗi và giữ xử lý nghiệp vụ idempotent.

Đây là khung xử lý minh họa; ứng dụng cần cung cấp implementation cho xử lý ảnh, DLT producer và logging. Mỗi record nhận được trong explicit mode phải có một acknowledgement type trước poll tiếp theo. Nếu gửi DLT thất bại, RELEASE để thử lại thay vì REJECT làm mất cơ hội giao lại.

Trong thực tế, publish DLT và REJECT không phải một transaction nguyên tử giữa producer và share acknowledgement. Nếu DLT publish thành công nhưng acknowledgement commit thất bại, record có thể được giao lại và DLT có thể có bản sao. DLT consumer nên deduplicate bằng eventId hoặc một khóa nguồn gồm topic, partition và offset.

## 13. Implicit acknowledgement và rủi ro khi xử lý lỗi

Implicit mode giảm số lời gọi API:

~~~java
while (true) {
    ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofSeconds(1));
    for (ConsumerRecord<String, String> record : records) {
        process(record);
    }
    // Lần poll tiếp theo implicit-ack batch trước.
}
~~~

Trong implicit mode, lần poll tiếp theo đánh dấu các record của poll trước là đã xử lý thành công và gửi acknowledgement bất đồng bộ. Vì vậy, nếu process(record) bắt exception nhưng ứng dụng vẫn tiếp tục poll, record lỗi có thể bị implicit acknowledge như record thành công.

Chỉ dùng implicit mode khi ứng dụng có thể xử lý cả batch thành công hoặc có cơ chế failure handling rõ ràng trước lần poll kế tiếp. Nếu cần ACCEPT/RELEASE/REJECT riêng từng record, hãy dùng explicit mode.

## 14. Lock timeout và RENEW cho công việc dài

Acquisition lock mặc định là 30 giây trong Kafka 4.2. Nếu công việc có thể kéo dài hơn, có hai cách:

1. Quản trị viên điều chỉnh dynamic group config share.record.lock.duration.ms trong giới hạn broker cho phép nếu thời gian xử lý tương đối ổn định.
2. Dùng explicit acknowledgement và gửi RENEW định kỳ trong lúc công việc vẫn đang chạy.

RENEW gia hạn lock để record không bị cấp cho worker khác trong lúc worker hiện tại vẫn xử lý. Consumer phải tiếp tục gọi poll theo chu kỳ và acknowledge RENEW cho record đang chạy. Khi xử lý xong, gửi ACCEPT; khi thất bại tạm thời, gửi RELEASE; khi không thể xử lý, gửi REJECT.

Không giữ lock lâu hơn cần thiết. Nếu worker bị treo và liên tục renew mà không tiến triển, nó có thể làm chậm delivery progress. Kết hợp timeout nghiệp vụ, heartbeat/poll interval và quan sát thời gian xử lý thực tế.

KafkaShareConsumer không thread-safe. Mỗi instance nên do một thread sở hữu; không gọi poll, acknowledge, commit hoặc close đồng thời từ nhiều thread. wakeup() là ngoại lệ có thể gọi từ thread khác để ngắt poll khi shutdown. Consumer phải gọi poll đều đặn để duy trì liveness; nếu vượt max.poll.interval.ms, client có thể chủ động rời share group. Khi xử lý lâu, thiết kế poll/renew rõ ràng thay vì chặn thread consumer vô thời hạn.

## 15. Delivery count và poison message

Kafka Share Group tăng delivery count mỗi khi record được acquired. Mặc định Kafka 4.2 cho phép tối đa 5 lần giao. Khi record đã chạm delivery count limit và lần giao tiếp tục thất bại hoặc lock hết hạn, record chuyển Archived và không được giao lại.

Record có thể được kiểm tra delivery count qua ConsumerRecord.deliveryCount():

~~~java
short attempts = record.deliveryCount().orElse((short) -1);
System.out.printf(
        "topic=%s partition=%d offset=%d deliveryCount=%d%n",
        record.topic(), record.partition(), record.offset(), attempts);
~~~

Delivery count có thể không chính xác tuyệt đối do trạng thái giao nhận không được cập nhật exactly-once. Dùng nó để nhận diện record có dấu hiệu lặp, không dùng làm audit log.

Điểm quan trọng: tự động archive không đồng nghĩa tự động gửi DLT. Nếu cần lưu poison message, hãy:

1. Kiểm tra lỗi và xác định không thể retry.
2. Publish payload, key, eventId, source topic/partition/offset và exception sang DLT.
3. Chờ producer xác nhận gửi thành công.
4. Acknowledge REJECT để share group không giao lại record đó.
5. Nếu DLT publish lỗi, RELEASE để record có cơ hội được xử lý lại.

Khi delivery count sắp chạm giới hạn, có thể chủ động route DLT trước khi broker tự archive. Tuy nhiên, do delivery count không phải bộ đếm chính xác tuyệt đối, quy trình DLT vẫn phải idempotent.

## 16. Share-partition start offset và lag

Share Group không dùng committed offset giống consumer group truyền thống. Nó quản lý:

- SPSO (Share-Partition Start Offset): offset đầu tiên mà share group còn cần theo dõi trạng thái giao nhận.
- SPEO (Share-Partition End Offset): ranh giới cuối của vùng record mà share group đã đưa vào quản lý.
- State và delivery count của từng record trong vùng đang theo dõi.

Khi record được acknowledge và SPSO tiến qua record đó, record chuyển sang Archived về mặt logic. Record được archived không còn eligible để giao cho share consumer, nhưng bản ghi gốc vẫn nằm trong Kafka log cho đến khi retention/compaction xử lý.

Lệnh describe share group hiển thị START-OFFSET và LAG. START-OFFSET là offset sớm nhất của các record đang được đánh giá giao; một số record sau đó có thể đã hoàn tất xử lý. Vì vậy, share-group lag không nên diễn giải đơn giản như phép trừ LEO trừ committed offset của consumer group.

## 17. Quản trị Share Group bằng CLI

Liệt kê tất cả group type:

~~~bash
kafka-groups.sh --bootstrap-server localhost:9092 --list
~~~

Liệt kê share group:

~~~bash
kafka-share-groups.sh --bootstrap-server localhost:9092 --list
~~~

Xem start offset và lag:

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group image-workers
~~~

Xem member và partition assignment:

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group image-workers \
  --members
~~~

Xem trạng thái group:

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group image-workers \
  --state
~~~

Reset share-group start offset về earliest:

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets \
  --group image-workers \
  --topic image.jobs \
  --to-earliest \
  --dry-run
~~~

Sau khi kiểm tra kết quả dry-run, thực hiện với --execute. Reset share-group offset chỉ thực hiện khi group không có active members; thao tác này loại bỏ in-flight state và delivery count hiện tại. Chỉ reset khi đã hiểu rõ tác động replay hoặc bỏ qua công việc.

Xóa share group:

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --delete \
  --group image-workers
~~~

Chỉ group không có active members mới có thể bị xóa. Lệnh reset/delete là thao tác quản trị có ảnh hưởng đến công việc đang chờ; không chạy trên group production khi chưa có kế hoạch.

## 18. ACL và bảo mật

Share Group dùng resource type GROUP tương tự consumer group:

- DESCRIBE trên GROUP để đọc thông tin share group.
- READ trên GROUP để thực hiện các thao tác tiêu thụ/acknowledge.
- READ/DESCRIBE trên TOPIC tương ứng để đọc record và metadata.
- Principal của ứng dụng cần quyền phù hợp với DLT topic nếu publish record lỗi.

Admin client khi mô tả share group cần DESCRIBE trên các topic mà group sử dụng. Các RPC nội bộ giữa broker/share coordinator được authorize theo cluster action; đây là quyền broker nội bộ, không phải quyền ứng dụng client cần tự cấp.

Với SASL_SSL, cấu hình security.protocol, sasl.mechanism, JAAS và truststore theo cluster. Secret phải được lấy từ secret manager hoặc environment, không ghi vào source code hay log. DLT cần chính sách retention, ACL và kiểm soát payload nhạy cảm như topic chính.

## 19. Giới hạn cấu hình client và broker

Một số cấu hình consumer truyền thống không áp dụng cho share consumer:

| Cấu hình | Với Share Group |
|---|---|
| enable.auto.commit / auto.commit.interval.ms | Không hỗ trợ auto-commit offset |
| group.instance.id | Không hỗ trợ static membership theo cách consumer group truyền thống |
| partition.assignment.strategy | Không dùng client-side partition assignor; assignment do broker điều phối |
| auto.offset.reset | Dùng group config share.auto.offset.reset |
| isolation.level | Dùng group config share.isolation.level |
| share.acknowledgement.mode | Chọn implicit hoặc explicit |
| share.acquire.mode | Chọn batch_optimized hoặc record_limit |
| max.poll.records | Giới hạn poll khi dùng record_limit; batch_optimized có thể trả nhiều hơn |

share.auto.offset.reset mặc định là latest; share.isolation.level mặc định là read_uncommitted. Các cấu hình group như share.auto.offset.reset, share.isolation.level và share.record.lock.duration.ms có phạm vi group. Các member trong cùng group không nên tự chọn chính sách khác nhau vì chúng cùng chia sẻ trạng thái giao nhận.

## 20. Monitoring và vận hành

Theo dõi cả group, record và coordinator:

| Chỉ số cần theo dõi | Vì sao cần |
|---|---|
| Số member đang hoạt động | Xác định worker pool có đủ member |
| Share group state | Phát hiện group không stable hoặc coordinator có vấn đề |
| Start offset và lag | Quan sát backlog theo share-partition |
| Số record acquired | Biết lượng công việc đang được worker giữ lock |
| ACCEPT/RELEASE/REJECT | Phân biệt thành công, retry và poison message |
| Delivery count phân bố | Phát hiện record bị giao lại nhiều lần |
| Lock timeout | Tìm worker chết, xử lý quá lâu hoặc lock duration quá ngắn |
| DLT publish và DLT backlog | Theo dõi công việc bị cách ly |
| Share coordinator state-topic health | Đảm bảo trạng thái giao nhận được lưu bền vững |
| Poll interval và processing latency | Phát hiện worker chậm hoặc không gọi poll đúng hạn |

Nên log eventId, topic, partition, offset, deliveryCount, worker ID, acknowledgement type và processing duration. Dùng eventId để nối trace giữa producer, worker, DLT và hệ thống đích.

## 21. Lab: chia công việc cho nhiều worker trên một partition

Mục tiêu: chứng minh nhiều share consumer trong cùng group có thể cùng xử lý record từ một partition và mỗi record được acknowledge riêng.

### Bước 1: tạo topic lab

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic image.jobs \
  --partitions 1 \
  --replication-factor 1
~~~

Với lab một broker, cấu hình share coordinator state topic replication factor và min ISR bằng 1 trước khi sử dụng share group. Trong production, dùng replication factor phù hợp cluster.

### Bước 2: khởi chạy ba worker

Khởi chạy ba worker với cùng group.id là image-workers, nhưng client.id khác nhau. Mỗi worker subscribe image.jobs. Share group mặc định khởi tạo start offset ở latest; vì vậy cần cho worker tham gia group trước khi gửi record của bài lab, hoặc cấu hình share.auto.offset.reset=earliest theo group trước khi bắt đầu.

### Bước 3: gửi công việc

Gửi ít nhất 20 record JSON, mỗi record có eventId và imageUrl. Dùng một partition để thấy rõ các worker cùng chia sẻ một partition.

~~~json
{"eventId":"img-001","imageUrl":"https://example.test/001.jpg"}
{"eventId":"img-002","imageUrl":"https://example.test/002.jpg"}
{"eventId":"img-003","imageUrl":"https://example.test/003.jpg"}
~~~

Các URL chỉ là dữ liệu minh họa; worker lab có thể thay bằng xử lý giả lập theo eventId. Bảo đảm mỗi instance có một KafkaShareConsumer riêng và không chia sẻ object consumer giữa thread.

### Bước 4: xử lý và acknowledge

Đặt share.acknowledgement.mode=explicit và share.acquire.mode=record_limit. Khi poll nhận record:

- Thành công: ACCEPT.
- Lỗi tạm thời: RELEASE.
- Payload sai vĩnh viễn: publish DLT rồi REJECT.
- Job dài: RENEW theo chu kỳ, sau đó ACCEPT/RELEASE.

Quan sát log để thấy các worker nhận record từ cùng partition nhưng offset có thể xen kẽ giữa các worker.

### Bước 5: thử crash worker

Cho một worker nhận record rồi dừng process trước khi acknowledge. Sau khi acquisition lock hết hạn, xác nhận record có thể được giao lại cho worker còn sống và delivery count tăng.

### Bước 6: thử poison message

Gửi một record sai schema hoặc sai dữ liệu. Thử RELEASE đến khi đạt delivery count limit và quan sát record không còn được giao. Sau đó chạy lại với logic chủ động publish DLT và REJECT để xác nhận ứng dụng kiểm soát được quarantine.

### Bước 7: so sánh consumer group

Chạy lại cùng topic bằng consumer group truyền thống với ba partition và ba consumer. So sánh assignment độc quyền partition với nhiều share consumer cùng được gán một partition; ghi lại ordering, retry behavior và số worker thực sự có việc.

## 22. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| KafkaShareConsumer nhận UnsupportedVersionException | Broker chưa hỗ trợ API/version tương ứng | Nâng broker lên bản hỗ trợ Share Groups và kiểm tra feature version |
| Không tạo được __share_group_state | Cluster ít broker hơn replication factor yêu cầu | Đặt state topic replication factor/min ISR phù hợp trước lần dùng đầu |
| Poll không trả record | Group đang ở latest, topic chưa có record mới hoặc record đang acquired | Kiểm tra share.auto.offset.reset, active lock và group state |
| Record được giao lại | Worker crash, RELEASE hoặc acquisition lock hết hạn | Kiểm tra processing latency, exception và lock duration |
| Record biến mất khỏi lần giao tiếp theo | REJECT hoặc delivery count limit đã đạt | Kiểm tra deliveryCount và DLT flow |
| Poll tiếp theo ném IllegalStateException | Explicit mode còn record chưa acknowledge | Acknowledge mọi record trong batch trước lần poll kế tiếp |
| Worker xử lý ngoài thứ tự | Share Group không bảo đảm ordering giữa batch | Dùng consumer group nếu cần strict ordering hoặc thêm sequence guard |
| DLT có duplicate | DLT publish thành công nhưng ack commit không thành công | Deduplicate bằng eventId hoặc source topic/partition/offset |
| Group không có member | Worker không chạy, không poll hoặc lỗi kết nối | Kiểm tra client logs, heartbeat, session timeout và network |
| Lag không giống consumer group lag | Share Group dùng per-record state và start offset | Dùng kafka-share-groups.sh --describe và diễn giải đúng START-OFFSET/LAG |

## 23. Tiêu chí hoàn thành

- Giải thích được lý do cần Share Groups bên cạnh consumer group.
- Phân biệt assignment partition độc quyền và chia sẻ partition.
- Mô tả được Available, Acquired, Acknowledged và Archived.
- Cấu hình KafkaShareConsumer và group.id.
- Phân biệt implicit và explicit acknowledgement.
- Sử dụng đúng ACCEPT, RELEASE, REJECT và RENEW.
- Giải thích acquisition lock, delivery count limit và poison message.
- Xử lý DLT có idempotency khi publish và acknowledge không nguyên tử.
- Nhận biết giới hạn ordering và chọn mô hình group phù hợp.
- Quản trị group bằng kafka-share-groups.sh và hiểu start offset/lag.
- Cấu hình internal state topic replication phù hợp cluster.

## 24. Ghi nhớ

| Khái niệm | Vai trò |
|---|---|
| Share Group | Nhóm worker cùng chia sẻ việc tiêu thụ record |
| KafkaShareConsumer | Java client dành cho Share Consumer API |
| Share-partition | Trạng thái chia sẻ việc đọc của một topic-partition trong một share group |
| Acquisition lock | Khóa giao nhận có thời hạn cho record |
| ACCEPT | Xác nhận xử lý thành công |
| RELEASE | Đưa record trở lại khả năng được giao |
| REJECT | Từ chối record, không giao lại |
| RENEW | Gia hạn lock khi công việc vẫn đang chạy |
| Delivery count | Số lần record được acquire, dùng bảo vệ poison message |
| SPSO | Share-partition start offset |
| __share_group_state | Internal topic lưu trạng thái share-partition |
| kafka-share-groups.sh | Công cụ quản trị share group |

Share Groups bổ sung mô hình queue cho Kafka bằng cách chia sẻ partition và acknowledge theo từng record. Mô hình này giúp mở rộng worker độc lập với partition count, đổi lại không giữ thứ tự xử lý như consumer group truyền thống. Hãy chọn đúng workload, đặt lock và delivery limit phù hợp, dùng explicit acknowledgement khi cần phân loại lỗi, và xây dựng DLT/idempotency để xử lý poison message an toàn.

## 25. Tài liệu tham khảo

- Apache Kafka 4.2 – [Share Consumer API](https://kafka.apache.org/42/apis/)
- Apache Kafka 4.2 – [KafkaShareConsumer Javadoc](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/consumer/KafkaShareConsumer.html)
- Apache Kafka 4.2 – [AcknowledgeType Javadoc](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/consumer/AcknowledgeType.html)
- Apache Kafka 4.2 – [Consumer Configs](https://kafka.apache.org/42/configuration/consumer-configs/)
- Apache Kafka 4.2 – [Group Configs](https://kafka.apache.org/42/configuration/group-configs/)
- Apache Kafka 4.2 – [Basic Kafka Operations: Managing Share Groups](https://kafka.apache.org/42/operations/basic-kafka-operations/)
- Apache Kafka – [KIP-932: Queues for Kafka](https://cwiki.apache.org/confluence/display/KAFKA/KIP-932%3A+Queues+for+Kafka)
