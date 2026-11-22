# Quản lý dead-letter topic

Dead-letter topic (DLT) là nơi lưu các record đã thất bại sau chính sách retry hoặc được phân loại là không thể retry. Trong Spring Kafka, DLT thường được publish bởi `DeadLetterPublishingRecoverer` khi dùng `DefaultErrorHandler`, hoặc được tạo trong luồng non-blocking retry với `@RetryableTopic`. DLT giúp cô lập record lỗi để luồng chính tiếp tục chạy, đồng thời giữ dữ liệu và metadata cho việc điều tra, khắc phục và replay.

Quản lý DLT là một công việc vận hành lâu dài. Topic phải có tên và partition topology rõ ràng, replication và retention phù hợp, quyền truy cập tối thiểu, cảnh báo khi backlog tăng và quy trình replay có kiểm soát. Nếu chỉ tạo một topic có hậu tố DLT mà không có người chịu trách nhiệm, record lỗi có thể nằm đó đến khi hết retention hoặc đầy disk.

## 1. Xác định vai trò của DLT trong kiến trúc

DLT là Kafka topic thông thường được dùng theo quy ước. Kafka broker không tự hiểu record nào là dead-letter; ứng dụng và Spring Kafka quyết định khi nào chuyển record sang topic này.

Luồng điển hình với blocking retry:

```text
orders.events
      |
      v
@KafkaListener
      |
      +---- xử lý thành công --------------------> commit theo AckMode
      |
      +---- exception
               |
               v
       DefaultErrorHandler
               |
        +------+------+
        |             |
      retry       hết retry / lỗi fatal
        |             |
        +-------------+
               |
               v
   DeadLetterPublishingRecoverer
               |
               v
       orders.events.DLT
               |
       +-------+--------+
       |                |
   điều tra          replay có kiểm soát
```

Với non-blocking retry, record có thể đi qua một hoặc nhiều retry topic trước khi tới DLT. Retry topic giữ record để thử lại theo lịch; DLT giữ record đã hết attempts hoặc không được retry. Hãy xác định rõ topic nào là retry và topic nào là DLT để người vận hành không replay nhầm.

## 2. Chuẩn hóa tên DLT và retry topic

Chọn quy ước tên nhất quán để dễ tìm kiếm, cấp ACL, đặt retention và tạo dashboard. Ví dụ:

| Topic nguồn | Retry topic ví dụ | DLT ví dụ |
|---|---|---|
| `orders.events` | `orders.events-retry-1000` | `orders.events.DLT` |
| `payments.events` | `payments.events-retry-1000` | `payments.events.DLT` |
| `inventory.events` | `inventory.events-retry-1000` | `inventory.events.DLT` |

Spring Kafka có quy ước suffix khác nhau tùy cơ chế:

- `DeadLetterPublishingRecoverer` mặc định định tuyến tới topic nguồn cộng hậu tố `.DLT`.
- `@RetryableTopic` có suffix DLT mặc định riêng, thường là `-dlt`; có thể cấu hình `dltTopicSuffix`.

Không giả định hai cơ chế tự tạo cùng một tên. Hãy ghi rõ tên topic thực tế trong cấu hình triển khai, ACL, dashboard và runbook. Nếu đổi suffix, phải cập nhật đồng bộ producer/recoverer, topic provisioning, consumer DLT và cảnh báo.

Nên giữ tên topic DLT gắn với topic nguồn. Cách đặt tên này giúp xác định nguồn dữ liệu và chính sách vận hành ngay từ tên topic, nhất là khi một cluster chứa nhiều domain.

## 3. Thiết kế partition cho DLT

Với `DeadLetterPublishingRecoverer` mặc định, record thường được gửi tới partition có cùng số với partition nguồn. Vì vậy, DLT cần có ít nhất số partition bằng topic nguồn nếu dùng partition mapping mặc định.

Ví dụ:

```text
orders.events
  partition 0 --------------> orders.events.DLT partition 0
  partition 1 --------------> orders.events.DLT partition 1
  partition 2 --------------> orders.events.DLT partition 2
  ...
  partition 11 -------------> orders.events.DLT partition 11
```

Nếu topic nguồn có 12 partition, hãy tạo DLT ít nhất 12 partition khi recoverer giữ nguyên partition. Nếu dùng destination resolver tùy chỉnh để ánh xạ partition khác, phải kiểm tra partition đích tồn tại và metadata nguồn vẫn được giữ để replay.

Số partition cũng quyết định mức song song tối đa của consumer group đọc DLT. Nếu muốn nhiều worker xử lý DLT đồng thời, cần đủ partition và bảo đảm cách phân vùng dữ liệu không làm mất thứ tự cần thiết.

Không tăng partition DLT một cách tùy tiện sau khi vận hành. Partition count ảnh hưởng tới consumer assignment và cách key được ánh xạ; khi replay về topic nguồn, hãy quyết định rõ có giữ partition gốc hay dùng key partitioner hiện tại.

## 4. Tạo DLT trước khi bật consumer production

Trong production, nên provision DLT trước bằng IaC, Kafka operator hoặc quy trình quản trị cluster. Không phụ thuộc vào auto topic creation của broker để tạo DLT đúng partition, replication và retention.

Ví dụ tạo DLT cho topic nguồn có 12 partition trên cluster ba broker:

```bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create \
  --topic orders.events.DLT \
  --partitions 12 \
  --replication-factor 3
```

Nếu cluster bật authorization, lệnh cần principal quản trị có quyền tạo topic. Ứng dụng chạy listener không nên được cấp quyền tạo mọi topic chỉ để DLT tự xuất hiện.

Nếu dùng `@RetryableTopic`, cần provision cả retry topic lẫn DLT theo đúng naming strategy và số partition. Có thể để Spring Kafka tạo topic trong môi trường local, nhưng production nên khai báo rõ replication factor và topic configs; kiểm tra các thuộc tính autoCreateTopics, numPartitions và replicationFactor của phiên bản Spring Kafka đang dùng.

## 5. Cấu hình độ bền cho DLT

DLT thường chứa dữ liệu cần điều tra hoặc khôi phục nên cần độ bền phù hợp với mức độ quan trọng của event. Một cấu hình phổ biến trong cluster production có ba replica và yêu cầu ít nhất hai replica trong ISR:

| Topic config | Ví dụ | Ý nghĩa |
|---|---:|---|
| `replication.factor` | `3` | Số bản sao của mỗi partition |
| `min.insync.replicas` | `2` | Số replica in-sync tối thiểu để chấp nhận ghi khi producer dùng `acks=all` |
| `cleanup.policy` | `delete` | Giữ record cho tới khi hết retention |
| `compression.type` | `producer` | Giữ codec do producer DLT gửi |

Có thể đặt topic configs sau khi tạo:

```bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.events.DLT \
  --alter \
  --add-config min.insync.replicas=2,cleanup.policy=delete,compression.type=producer
```

`min.insync.replicas` chỉ phát huy tác dụng bảo vệ mức xác nhận khi producer dùng `acks=all`. Hãy kiểm tra producer dùng bởi recoverer có cấu hình acknowledgement phù hợp. Nếu ISR thấp hơn ngưỡng, publish DLT có thể thất bại; đây là lỗi cần được phát hiện và xử lý, không phải lý do để âm thầm bỏ record.

Replication factor phải phù hợp số broker thực tế. Ví dụ RF=3 không thể được đáp ứng trên cluster chỉ có một broker. Không sao chép cấu hình local RF=1 sang production nếu DLT cần chịu lỗi broker.

## 6. Cấu hình retention và cleanup policy

DLT cần được giữ đủ lâu để đội vận hành phát hiện, phân tích, sửa lỗi và replay. Thời gian retention nên dựa trên thời gian phản ứng sự cố, lịch trực, thời gian sửa lỗi, cửa sổ replay và yêu cầu lưu trữ của tổ chức.

Ví dụ giữ DLT trong bảy ngày:

```bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.events.DLT \
  --alter \
  --add-config retention.ms=604800000,cleanup.policy=delete
```

Các thuộc tính quan trọng:

| Config | Ý nghĩa vận hành |
|---|---|
| `retention.ms` | Thời gian lưu record trước khi đủ điều kiện xóa |
| `retention.bytes` | Giới hạn dung lượng log theo từng partition |
| `cleanup.policy=delete` | Xóa segment cũ theo retention |
| `segment.bytes` | Kích thước mục tiêu của log segment |
| `segment.ms` | Thời gian tối đa trước khi segment được roll theo cấu hình |

Retention của Kafka không phải TTL chính xác cho từng record. Việc xóa diễn ra theo log segment và chu kỳ cleanup; record có thể tồn tại lâu hơn thời điểm retention vừa hết. Hãy dành buffer cho độ trễ cleanup khi tính thời gian lưu.

Với DLT, `cleanup.policy=delete` thường phù hợp vì cần giữ từng lần thất bại. Không bật `compact` chỉ để tiết kiệm dung lượng: nếu nhiều record có cùng key, compaction có thể loại bỏ các record cũ và làm mất lịch sử lỗi cần điều tra. Chỉ dùng compaction nếu DLT được thiết kế có chủ đích như một changelog giữ trạng thái mới nhất, không phải kho lưu từng failed event.

Nếu đặt `retention.bytes`, lưu ý giới hạn được áp dụng theo partition. Khi một partition chạm ngưỡng, dữ liệu cũ của partition đó có thể bị xóa trước các partition khác. Không dùng `retention.bytes` quá thấp làm mất record lỗi trước khi đội vận hành kịp xử lý.

## 7. Ước lượng dung lượng DLT

Dung lượng cần thiết phụ thuộc số record lỗi, kích thước trung bình sau serialization/compression, số ngày lưu và replication factor.

Ước lượng sơ bộ:

```text
logical bytes = failed records per day
             x average stored bytes per record
             x retention days

physical bytes ≈ logical bytes x replication factor
```

Ví dụ có 20.000 record lỗi mỗi ngày, kích thước lưu trung bình 4 KiB và retention 7 ngày:

```text
logical bytes = 20,000 x 4 KiB x 7
              ≈ 547 MiB

with replication factor 3:
physical bytes ≈ 1.6 GiB
```

Đây là ước lượng ban đầu, chưa tính index, segment overhead, header, compression ratio thực tế, replica placement và tốc độ lỗi tăng đột biến. Nên dự phòng nhiều hơn theo peak incident thay vì chỉ theo trung bình ngày.

Theo dõi dung lượng theo topic và partition, đồng thời đặt quota/cảnh báo disk ở broker. Một lỗi schema hoặc dependency diện rộng có thể làm tỷ lệ DLT tăng từ vài record lên hàng triệu record trong thời gian ngắn.

## 8. Cấp ACL riêng cho publisher và consumer DLT

Tách quyền của ứng dụng phát DLT, công cụ điều tra và công cụ replay:

| Principal | Quyền cần thiết thường gặp | Phạm vi |
|---|---|---|
| Listener application | `WRITE`, `DESCRIBE` | Topic DLT |
| DLT inspector | `READ`, `DESCRIBE` | Topic DLT và consumer group inspector |
| Replay service | `READ` trên DLT, `WRITE` trên topic đích, quyền group tương ứng | Topic nguồn/DLT và group replay |
| Provisioning principal | `CREATE`, `ALTER`, `ALTER_CONFIGS`, `DESCRIBE_CONFIGS` theo thao tác cần thực hiện | Chỉ các topic được quản lý |

Ví dụ cấp quyền publish DLT cho ứng dụng:

```bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --add \
  --allow-principal User:orders-service \
  --operation WRITE \
  --operation DESCRIBE \
  --topic orders.events.DLT
```

Ví dụ cấp quyền đọc DLT và sử dụng group cho inspector:

```bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --add \
  --allow-principal User:dlt-inspector \
  --operation READ \
  --operation DESCRIBE \
  --topic orders.events.DLT

kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --add \
  --allow-principal User:dlt-inspector \
  --operation READ \
  --group orders-dlt-inspector
```

Các lệnh trên minh họa Kafka ACL authorizer; principal, operation và quyền bổ sung phụ thuộc security setup. Nếu cluster dùng SASL/TLS, thêm `--command-config client.properties` chứa cấu hình xác thực phù hợp. Không lưu password hoặc API secret trực tiếp trong script hoặc source control.

Nếu DLT publish nằm trong Kafka transaction, principal còn cần quyền trên transactional ID tương ứng. Cấp quyền đúng resource thay vì wildcard toàn cluster.

## 9. Đảm bảo publish DLT được xác nhận

Recoverer gửi DLT bằng producer. Việc gọi send không đồng nghĩa broker đã xác nhận record được lưu thành công. Nếu topic không tồn tại, partition không hợp lệ, ACL từ chối hoặc broker thiếu ISR, send có thể thất bại.

Với `DeadLetterPublishingRecoverer`, có thể yêu cầu lỗi send result được báo lại:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

recoverer.setFailIfSendResultIsError(true);
```

Kết hợp recoverer với `DefaultErrorHandler` theo cấu hình listener container. Khi publish DLT thất bại, recovery phải được xem là thất bại để error handler/container áp dụng chính sách tiếp theo. Không xác nhận record nguồn như thể đã recover thành công khi chưa có xác nhận publish DLT.

Nếu dùng transactional listener, cần xác định DLT send có tham gia transaction hay không và transaction manager/recoverer có được cấu hình đúng. Kafka transaction chỉ bao phủ tài nguyên Kafka được tham gia vào transaction đó.

## 10. Kiểm tra topic DLT và cấu hình thực tế

Sau khi provisioning, xác minh topic tồn tại và có đủ partition:

```bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders.events.DLT
```

Đọc topic configs:

```bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.events.DLT \
  --describe
```

Kiểm tra consumer group đang đọc DLT:

```bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-dlt-inspector
```

Các điểm cần xác nhận:

- Topic tồn tại trên đúng cluster/namespace.
- Số partition đáp ứng partition mapping của recoverer.
- Leader và replica được phân bố, ISR đủ theo chính sách.
- `cleanup.policy`, `retention.ms`, `retention.bytes` và `min.insync.replicas` đúng.
- Principal publisher có quyền ghi và inspector có quyền đọc.
- Consumer group DLT có lag và tiến độ phù hợp.
- Dashboard và alert đang theo dõi đúng tên topic thực tế.

## 11. Đọc và điều tra record trong DLT

DLT có thể chứa payload đã deserialize hoặc raw bytes tùy lỗi xảy ra ở bước nào và cấu hình serializer. Không giả định mọi record đều là JSON string hoặc Java object cùng một kiểu.

Với record do Spring Kafka recoverer tạo, kiểm tra metadata nguồn như:

| Metadata | Mục đích |
|---|---|
| Original topic | Xác định topic phát sinh lỗi |
| Original partition | Xác định partition nguồn |
| Original offset | Truy ngược record nguồn |
| Original timestamp | Thời điểm record nguồn được tạo theo timestamp type |
| Exception class/message | Phân loại lỗi và tìm nguyên nhân |
| Original consumer group | Xác định consumer group xử lý record |

Spring Kafka cung cấp các hằng số header như `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET` và `KafkaHeaders.DLT_EXCEPTION_FQCN`. Hãy dùng hằng số của phiên bản Spring Kafka đang chạy để đọc header thay vì tự đoán tên.

Ví dụ listener điều tra:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.stereotype.Component;

@Component
class OrdersDltInspector {

    private static final Logger log =
            LoggerFactory.getLogger(OrdersDltInspector.class);

    @KafkaListener(
            id = "orders-dlt-inspector",
            topics = "orders.events.DLT",
            groupId = "orders-dlt-inspector"
    )
    public void inspect(ConsumerRecord<String, Object> record) {
        var originalTopic = record.headers()
                .lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC);
        var originalOffset = record.headers()
                .lastHeader(KafkaHeaders.DLT_ORIGINAL_OFFSET);

        log.error(
                "DLT record: topic={}, partition={}, offset={}, key={}, originalTopicHeader={}, originalOffsetHeader={}",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                originalTopic != null,
                originalOffset != null
        );
    }
}
```

Ví dụ này chỉ minh họa việc nhận record và xác nhận có metadata header; trong hệ thống thực tế cần decode header theo kiểu dữ liệu do Spring Kafka ghi, lưu bản ghi điều tra vào hệ thống incident/audit và tránh log payload nhạy cảm. Nếu listener chỉ dùng để quan sát, hãy bảo đảm consumer group và offset policy phù hợp để không vô tình tạo thêm side effect.

## 12. Theo dõi DLT bằng metrics và alert

Không nên chỉ cảnh báo khi DLT có record đầu tiên. Một record lỗi có thể là sự cố đơn lẻ; hàng nghìn record tăng nhanh hoặc record cũ không được xử lý mới là dấu hiệu vận hành nghiêm trọng.

Nên theo dõi tối thiểu:

| Chỉ số | Ý nghĩa | Cảnh báo khi |
|---|---|---|
| DLT records in | Số record mới vào DLT | Tăng đột biến hoặc vượt baseline |
| DLT bytes in | Lượng dữ liệu lỗi mới | Disk/network tăng nhanh |
| DLT consumer lag | Inspector/replay consumer còn tồn bao nhiêu record | Lag tăng liên tục hoặc không giảm |
| Oldest DLT age | Tuổi record cũ nhất chưa được điều tra | Vượt SLA phản hồi |
| Publish failure | Recoverer không gửi được DLT | Bất kỳ lỗi kéo dài hoặc tăng đột biến |
| DLT partition skew | Lỗi tập trung vào một partition | Một partition tăng nhanh hơn hẳn |
| Replay success/failure | Kết quả xử lý lại | Replay thất bại lặp lại |

`records-lag-max` của consumer group là một chỉ báo lag, không phải tuổi của record và không thay thế DLT ingest rate. Để đo tuổi record chính xác, nên bổ sung header thời điểm đưa vào DLT như `x-dlt-recorded-at` bằng header function phù hợp của recoverer, hoặc lưu timestamp nhận DLT ở inspector. Timestamp gốc của event có thể đã cũ trước khi record bị chuyển DLT.

Tách alert theo mức độ:

- **Warning:** DLT có record mới nhưng tốc độ thấp và inspector vẫn tiến triển.
- **Critical:** DLT tăng nhanh, inspector lag không giảm, tuổi record vượt SLA hoặc publish DLT thất bại.
- **Capacity:** Dung lượng DLT/broker tiến gần giới hạn disk hoặc retention đang xóa record trước khi xử lý.

Đính kèm topic, partition, consumer group, exception class và link dashboard vào alert để người trực có thể bắt đầu điều tra ngay.

## 13. Thiết kế dashboard vận hành

Một dashboard DLT hữu ích nên có các biểu đồ:

1. Record in theo phút và theo topic nguồn.
2. Bytes in và dung lượng log DLT theo thời gian.
3. Consumer lag của từng group inspector/replay.
4. Tuổi record chưa xử lý lớn nhất.
5. Phân bố exception class và topic nguồn.
6. Publish failure và retry/recoverer failure.
7. Replay count, replay success/failure và số record đang được xử lý thủ công.
8. Partition có backlog cao nhất.

Cho phép lọc theo môi trường, service, topic nguồn, exception class và thời gian. Không đưa payload hoặc dữ liệu cá nhân nhạy cảm lên dashboard; dùng event ID và metadata truy vết.

## 14. Quy trình replay DLT có kiểm soát

Replay là phát lại một record đã lưu trong DLT sau khi nguyên nhân lỗi được khắc phục. Không nên tự động replay toàn bộ DLT ngay khi thấy service đã healthy; nếu schema, dữ liệu hoặc side effect chưa được xử lý, record sẽ tiếp tục thất bại hoặc tạo tác động trùng lặp.

Quy trình an toàn:

1. Tạm dừng replay tự động nếu có; giữ nguyên DLT để điều tra.
2. Xác định nguyên nhân theo exception, schema ID, event ID và metadata nguồn.
3. Sửa code, schema, dependency hoặc dữ liệu nghiệp vụ.
4. Kiểm thử record mẫu trong môi trường staging.
5. Chọn tập record cần replay theo topic/partition/offset, event ID hoặc thời gian.
6. Replay với tốc độ giới hạn và theo dõi downstream capacity.
7. Xác nhận kết quả nghiệp vụ và idempotency.
8. Lưu audit về ai replay, lúc nào, số lượng bao nhiêu và kết quả.
9. Chỉ đóng incident khi DLT backlog và replay failures trở về mức chấp nhận được.

Replay tạo record mới với offset mới trong topic đích. Hãy giữ original topic/partition/offset và DLT source coordinates trong custom headers hoặc audit store để truy vết. Nếu cần giữ thứ tự theo partition, dùng partition mapping có chủ đích thay vì chỉ gửi theo key và giả định partition sẽ giống trước đây.

## 15. Ví dụ replay bằng Spring Kafka

Một replay service có thể đọc record DLT, gửi lại payload vào topic nguồn và đính kèm metadata audit. Ví dụ sau dành cho Spring Kafka 3.x, giả định DLT deserializer có thể tạo kiểu `Object` và producer serializer hỗ trợ kiểu value đó:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class DltReplayService {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    DltReplayService(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void replay(
            ConsumerRecord<String, Object> dltRecord,
            String targetTopic,
            int targetPartition,
            String replayId
    ) {
        ProducerRecord<String, Object> replayRecord = new ProducerRecord<>(
                targetTopic,
                targetPartition,
                dltRecord.key(),
                dltRecord.value()
        );

        replayRecord.headers().add(
                "x-replay-id",
                replayId.getBytes(StandardCharsets.UTF_8)
        );
        replayRecord.headers().add(
                "x-replay-source-topic",
                dltRecord.topic().getBytes(StandardCharsets.UTF_8)
        );
        replayRecord.headers().add(
                "x-replay-source-partition",
                Integer.toString(dltRecord.partition()).getBytes(StandardCharsets.UTF_8)
        );
        replayRecord.headers().add(
                "x-replay-source-offset",
                Long.toString(dltRecord.offset()).getBytes(StandardCharsets.UTF_8)
        );

        // Chờ broker xác nhận send trước khi caller xác nhận record DLT đã replay.
        kafkaTemplate.send(replayRecord).join();
    }
}
```

Trong ứng dụng thực tế, `targetTopic` và `targetPartition` phải được xác thực từ metadata nguồn hoặc quy tắc replay đã phê duyệt; không nhận tùy ý từ request không tin cậy. Nếu DLT chứa raw `byte[]` do lỗi deserialize, producer replay phải giữ nguyên bytes hoặc deserialize bằng schema đã được sửa trước khi gửi. Nếu dùng Avro/Protobuf/JSON Schema, replay tool cần serializer tương ứng.

Nếu gọi service từ DLT listener, chỉ trả về bình thường sau khi send đã được xác nhận. Nếu send thất bại, để exception được truyền ra để container không commit offset DLT như thể replay thành công. Bảo đảm listener error handler không tự đưa record DLT vào vòng replay vô hạn.

## 16. Idempotency và thứ tự khi replay

Kafka đảm bảo offset mới cho record được publish lại; nó không biết record này đã tạo side effect trước đó hay chưa. Có thể lần xử lý ban đầu đã cập nhật database thành công nhưng offset chưa commit, sau đó record mới được replay. Nếu không có idempotency, hệ thống có thể tạo đơn hàng, thanh toán hoặc email trùng.

Các biện pháp bảo vệ:

- Dùng event ID ổn định và lưu trạng thái xử lý đã hoàn tất.
- Dùng unique constraint hoặc inbox table ở database.
- Dùng upsert/idempotent command cho side effect có thể lặp.
- Giữ key và partition mapping nếu thứ tự theo partition là yêu cầu nghiệp vụ.
- Replay theo batch nhỏ, giới hạn tốc độ và có thể dừng ngay khi lỗi tăng.

Không replay đồng thời nhiều record cùng key nếu nghiệp vụ phụ thuộc thứ tự. Nếu partition count của topic nguồn đã thay đổi, mapping theo partition cũ cần được xem xét lại.

## 17. Dọn dẹp DLT sau khi xử lý

Không xóa topic DLT chỉ vì dashboard tạm thời hiển thị lag bằng 0. Trước khi dọn dẹp, xác nhận:

- Không còn record chưa điều tra hoặc đang chờ replay.
- Các incident liên quan đã có quyết định xử lý.
- Audit/replay log đã được lưu ở nơi phù hợp.
- Retention đáp ứng yêu cầu lưu trữ và compliance.
- Không có consumer group hoặc công cụ replay còn cần đọc dữ liệu cũ.

Thông thường nên để retention tự dọn segment theo policy đã duyệt. Xóa topic thủ công là thao tác có phạm vi lớn, làm mất toàn bộ dữ liệu và offset của topic; chỉ thực hiện qua quy trình quản trị có phê duyệt và xác minh cluster/topic chính xác.

## 18. Runbook khi DLT tăng đột biến

| Bước | Việc cần làm | Kết quả mong đợi |
|---|---|---|
| 1. Xác nhận | Xem DLT records in, bytes in, lag và oldest age | Biết mức độ và thời điểm bắt đầu |
| 2. Khoanh vùng | Nhóm theo topic nguồn, partition và exception class | Xác định service/loại record bị ảnh hưởng |
| 3. Bảo toàn | Kiểm tra retention/disk và tạm dừng replay không an toàn | Không mất dữ liệu trong lúc điều tra |
| 4. Chẩn đoán | Đọc headers, schema ID, event ID và log tương ứng | Tìm nguyên nhân gốc |
| 5. Khắc phục | Sửa schema, code, dependency, ACL hoặc downstream | Record mẫu xử lý được |
| 6. Thử replay | Replay một nhóm nhỏ có giới hạn | Xác minh kết quả và idempotency |
| 7. Mở rộng | Tăng dần batch/rate theo capacity | Backlog giảm ổn định |
| 8. Kết thúc | Ghi audit, theo dõi alert và đóng incident | Không còn record tồn đọng ngoài kế hoạch |

Nếu lỗi do downstream đang quá tải, không replay ngay cả khi DLT consumer có thể đọc. Khôi phục capacity trước, nếu không replay sẽ chỉ đẩy áp lực ngược vào hệ thống.

## 19. Những nhầm lẫn thường gặp

1. **Tạo DLT một partition cho topic nguồn nhiều partition.** Recoverer giữ partition nguồn có thể không gửi được record vào partition đích không tồn tại.
2. **Dùng retention quá ngắn.** Record có thể bị xóa trước khi đội vận hành hoàn tất điều tra.
3. **Bật compaction cho DLT mà không hiểu hậu quả.** Các record lỗi cùng key có thể bị loại bỏ, làm mất lịch sử.
4. **Cho rằng publish DLT luôn thành công.** ACL, topic, ISR và broker failure có thể làm send thất bại.
5. **Chỉ theo dõi consumer lag.** Lag không thể hiện số record mới vào DLT hoặc tuổi record cũ nhất.
6. **Replay toàn bộ ngay sau khi service healthy.** Nguyên nhân dữ liệu/schema hoặc side effect trùng có thể chưa được xử lý.
7. **Replay mà không giữ metadata nguồn.** Khó truy vết record mới về topic/partition/offset ban đầu.
8. **Cấp quyền wildcard cho DLT inspector.** Dễ làm lộ dữ liệu lỗi của nhiều domain; nên giới hạn ACL theo topic/group.
9. **Dùng cùng suffix cho mọi cơ chế mà không kiểm tra.** `DeadLetterPublishingRecoverer` và `@RetryableTopic` có naming convention riêng.
10. **Xóa topic khi lag bằng 0.** Có thể vẫn còn dữ liệu cần audit hoặc replay ngoài consumer group đang theo dõi.

Quản lý DLT hiệu quả cần xem DLT như một phần của vận hành messaging: provision đúng partition và replication, đặt retention đủ dài, cấp ACL theo vai trò, xác nhận publish thành công, theo dõi tốc độ vào/lag/tuổi record và có runbook replay idempotent. Khi các trách nhiệm này được gắn với service owner và dashboard cụ thể, DLT trở thành vùng phục hồi có kiểm soát thay vì nơi tích tụ lỗi không ai xử lý.
