# Chọn điểm bắt đầu theo thời gian hoặc mốc nghiệp vụ

Khi cần phát lại dữ liệu Kafka, câu hỏi đầu tiên thường là: consumer nên bắt đầu đọc từ đâu? Có thể chọn theo một thời điểm, chẳng hạn đọc các sự kiện từ 09:00 sáng, hoặc theo một mốc nghiệp vụ, chẳng hạn bắt đầu từ đơn hàng `ORD-2048`, event ID cụ thể hay sequence number 500. Hai cách chọn này dùng những thông tin khác nhau và không thể thay thế cho nhau.

Kafka lưu record theo offset trong từng partition. Có thể dùng timestamp index để tìm offset gần với một thời điểm, hoặc dùng offset đã biết để `seek()` trực tiếp. Nhưng Kafka không tự tìm kiếm nội dung JSON hay header theo `orderId`/`eventId`; muốn chọn theo mốc nghiệp vụ, ứng dụng cần có chỉ mục hoặc đọc tới khi gặp mốc đó. Bài viết trình bày cách chọn điểm bắt đầu an toàn bằng CLI, Kafka Java Consumer và Spring Kafka.

## 1. Offset là vị trí, timestamp là mốc thời gian

Mỗi record được ghi vào một partition và có offset riêng trong partition đó. Offset là vị trí trong log, không phải thời gian và cũng không phải số thứ tự toàn topic.

Ví dụ:

| Partition | Offset | Timestamp | Event |
|---:|---:|---|---|
| 0 | 120 | 09:00:02 | `OrderPlaced` |
| 0 | 121 | 09:00:05 | `PaymentAuthorized` |
| 0 | 122 | 09:00:11 | `OrderShipped` |
| 1 | 80 | 09:00:01 | `OrderPlaced` |
| 1 | 81 | 09:00:09 | `OrderCancelled` |

Muốn đọc từ 09:00:07, consumer phải tìm offset tương ứng riêng cho partition 0 và partition 1. Không có một offset duy nhất đại diện cho thời điểm đó trên toàn topic.

Trong Kafka, `offsetsForTimes()` tìm offset đầu tiên có timestamp lớn hơn hoặc bằng timestamp yêu cầu cho từng partition. Kết quả có thể khác nhau giữa các partition. Nếu không có record phù hợp trong partition, API trả về `null` cho partition đó.

## 2. Timestamp nào được Kafka dùng để tìm offset?

Kafka record có timestamp. Cách timestamp được lưu phụ thuộc cấu hình `message.timestamp.type` của topic/broker:

| Timestamp type | Ý nghĩa |
|---|---|
| `CreateTime` | Dùng timestamp do producer cung cấp; nếu producer không truyền, Kafka client thường gắn thời điểm gửi record |
| `LogAppendTime` | Broker ghi đè timestamp bằng thời điểm record được append vào log |

`offsetsForTimes()` tìm theo timestamp của Kafka record. Nó không đọc trường `occurredAt` trong JSON value, cũng không đọc `eventTime` trong header. Nếu payload chứa thời điểm nghiệp vụ nhưng producer không gắn thời điểm đó vào Kafka record timestamp, tìm kiếm theo timestamp sẽ không dựa trên trường nghiệp vụ đó.

Ví dụ một event có thể chứa:

```json
{
  "eventId": "evt-9001",
  "orderId": "ORD-2048",
  "occurredAt": "2026-11-20T09:00:00Z",
  "eventType": "OrderPlaced"
}
```

Nếu producer gửi record lúc 09:15 nhưng `occurredAt` là 09:00 và không truyền timestamp riêng, `CreateTime` có thể là 09:15. `offsetsForTimes(09:00)` khi đó không nhất thiết tìm đúng record theo thời điểm nghiệp vụ 09:00.

Nếu muốn tra cứu theo event time, có thể truyền `occurredAt` dưới dạng epoch milliseconds làm timestamp của `ProducerRecord`, đồng thời dùng `CreateTime`. Nếu dùng `LogAppendTime`, broker sẽ thay timestamp bằng thời điểm append; lúc đó timestamp index phản ánh thời gian Kafka nhận record, không phải thời gian nghiệp vụ ban đầu.

## 3. Chọn điểm bắt đầu theo thời gian bằng Kafka CLI

`kafka-consumer-groups` hỗ trợ reset offset theo một thời điểm với tùy chọn `--to-datetime`. Ví dụ muốn đưa group `order-replay` về vị trí tương ứng với 09:00 ngày 20/11/2026:

```bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group order-replay \
  --topic orders.events \
  --reset-offsets \
  --to-datetime 2026-11-20T09:00:00.000 \
  --dry-run
```

Đọc kết quả `dry-run` để kiểm tra offset dự kiến của từng partition. Nếu đúng, dừng tất cả consumer thuộc group đó rồi thực thi:

```bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group order-replay \
  --topic orders.events \
  --reset-offsets \
  --to-datetime 2026-11-20T09:00:00.000 \
  --execute
```

Sau đó xác minh tiến độ mới:

```bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group order-replay
```

Lệnh reset thay đổi offset đã commit của group. Nó không tự đọc hay phát lại record; consumer cần khởi động lại và tiếp tục từ offset mới. Group phải không có consumer đang hoạt động khi thực hiện reset. Hãy dùng `--dry-run` trước `--execute`, đặc biệt khi thao tác trên group đang phục vụ production.

Định dạng ngày giờ được CLI hỗ trợ phụ thuộc phiên bản Kafka. Hãy dùng định dạng được `kafka-consumer-groups.sh --help` của bản đang triển khai công bố, đồng thời xác nhận timezone mà môi trường chạy CLI đang sử dụng. Nếu timezone không rõ ràng, dùng Java API với epoch milliseconds được chuyển đổi rõ ràng từ UTC để tránh reset lệch giờ.

## 4. `offsetsForTimes()` trong Kafka Java Consumer

Kafka Java Consumer cung cấp API:

```java
Map<TopicPartition, OffsetAndTimestamp> offsetsForTimes(
        Map<TopicPartition, Long> timestampsToSearch)
```

Ứng dụng truyền timestamp tính bằng milliseconds cho từng partition. Kết quả chứa `OffsetAndTimestamp` nếu tìm được record phù hợp; nếu không có record có timestamp lớn hơn hoặc bằng mốc tìm kiếm, giá trị cho partition đó là `null`.

Ví dụ dùng manual assignment để minh họa rõ việc tìm offset cho từng partition:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndTimestamp;
import org.apache.kafka.common.TopicPartition;

List<TopicPartition> partitions = List.of(
        new TopicPartition("orders.events", 0),
        new TopicPartition("orders.events", 1),
        new TopicPartition("orders.events", 2));

long startTimeMs = Instant.parse("2026-11-20T09:00:00Z").toEpochMilli();

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    // Ví dụ này tự gán partition; không dùng group subscription/rebalance.
    consumer.assign(partitions);

    Map<TopicPartition, Long> timestamps = new HashMap<>();
    for (TopicPartition partition : partitions) {
        timestamps.put(partition, startTimeMs);
    }

    Map<TopicPartition, OffsetAndTimestamp> offsets =
            consumer.offsetsForTimes(timestamps);

    for (TopicPartition partition : partitions) {
        OffsetAndTimestamp match = offsets.get(partition);
        if (match != null) {
            consumer.seek(partition, match.offset());
            System.out.printf("%s -> offset %d at %d%n",
                    partition, match.offset(), match.timestamp());
        } else {
            // Không có record nào từ timestamp yêu cầu trở đi: chọn cuối log.
            consumer.seekToEnd(List.of(partition));
            System.out.printf("%s -> no matching timestamp; seek to end%n",
                    partition);
        }
    }

    // Sau khi seek, bắt đầu poll và xử lý record.
    ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(500));
    process(records);
}
```

Đây là ví dụ khung; `props` cần có bootstrap server, deserializer và các cấu hình consumer phù hợp, còn `process` do ứng dụng triển khai. Với partition không tìm thấy timestamp, ví dụ chọn `seekToEnd()` để không đọc dữ liệu trước mốc yêu cầu. Ứng dụng khác có thể chọn bỏ qua partition, báo lỗi hoặc dùng một fallback đã thống nhất. Không mặc định chuyển về `earliest`, vì điều đó có thể phát lại toàn bộ lịch sử ngoài ý muốn.

### Lưu ý về assignment và subscription

Ví dụ trên dùng `assign()` để chủ động gán partition. Khi dùng `subscribe()` và consumer group tự cân bằng, cần chờ partition được giao trước khi gọi `seek()`:

```java
consumer.subscribe(List.of("orders.events"));

while (consumer.assignment().isEmpty()) {
    consumer.poll(Duration.ofMillis(100));
}

// Tại đây lấy assignment, gọi offsetsForTimes() rồi seek()
// trên consumer thread trước khi xử lý records trả về ở các poll tiếp theo.
```

Trong ứng dụng thực tế, cần tránh xử lý batch trả về trong lần poll dùng để hoàn tất assignment trước khi áp dụng điểm bắt đầu mới. Có thể bỏ qua batch khởi tạo, thực hiện `seek()` ngay trên consumer thread, sau đó mới xử lý dữ liệu từ vị trí đã chọn.

Không gọi `seek()`, `poll()` hoặc `offsetsForTimes()` trên worker thread khác. `KafkaConsumer` không thread-safe và việc điều khiển vị trí đọc phải được thực hiện trên thread sở hữu consumer.

## 5. Xử lý kết quả `null` và giới hạn dữ liệu còn lưu

`offsetsForTimes()` có thể trả về `null` cho một partition nếu không tìm được record có timestamp thỏa điều kiện. Một số nguyên nhân thường gặp:

- Mốc thời gian nằm sau timestamp của record mới nhất trong partition.
- Partition rỗng.
- Dữ liệu phù hợp đã bị xóa do retention.
- Timestamp của record không phản ánh thời gian nghiệp vụ mà ứng dụng đang tìm.

Nên kiểm tra `beginningOffsets()` và `endOffsets()` để hiểu phạm vi offset còn đọc được:

```java
Map<TopicPartition, Long> beginnings = consumer.beginningOffsets(partitions);
Map<TopicPartition, Long> ends = consumer.endOffsets(partitions);

for (TopicPartition partition : partitions) {
    System.out.printf("%s beginning=%d end=%d%n",
            partition, beginnings.get(partition), ends.get(partition));
}
```

`beginningOffsets` là offset sớm nhất còn có thể đọc theo trạng thái log hiện tại; `endOffsets` là vị trí cuối log theo nghĩa offset kế tiếp cần ghi/đọc. Các giá trị có thể thay đổi khi producer ghi thêm dữ liệu hoặc retention/compaction chạy. Offset không được đánh lại liên tục sau compaction, vì vậy có thể có khoảng trống giữa các offset còn tồn tại.

Nếu mốc thời gian cũ hơn dữ liệu còn lưu, consumer chỉ có thể bắt đầu từ phần log còn tồn tại. Kafka không thể phục hồi record đã bị retention xóa nếu không có bản lưu trữ khác.

## 6. Chọn điểm bắt đầu theo mốc nghiệp vụ

Mốc nghiệp vụ có thể là:

- `eventId`: định danh duy nhất của một sự kiện.
- `orderId` hoặc `accountId`: định danh entity cần bắt đầu xử lý.
- `sequenceNumber` hoặc `aggregateVersion`: số thứ tự nghiệp vụ của một entity.
- `causationId`: ID của event/command đã gây ra thay đổi hiện tại.
- Một checkpoint đã được ứng dụng lưu từ lần xử lý trước.

Kafka không có API tìm kiếm tùy ý trong payload hoặc headers. Broker định vị record bằng partition và offset; nó không thực hiện truy vấn như `WHERE orderId = ...` trên JSON value. Vì vậy, muốn bắt đầu từ một marker, cần biến marker thành một vị trí Kafka có thể `seek()` tới.

Có ba cách phổ biến:

1. **Đã biết partition và offset:** dùng trực tiếp `consumer.seek(partition, offset)`.
2. **Có chỉ mục ngoài:** duy trì mapping `eventId -> topic, partition, offset` hoặc `businessKey -> checkpoint`, rồi tra cứu offset trước khi replay.
3. **Chỉ biết business key/sequence:** bắt đầu từ checkpoint hoặc offset gần nhất rồi đọc và kiểm tra record cho tới khi gặp marker mong muốn.

Ví dụ khi đã biết marker tương ứng partition 1, offset 8450:

```java
TopicPartition partition = new TopicPartition("orders.events", 1);
consumer.assign(List.of(partition));
consumer.seek(partition, 8450L);
```

Nếu marker là `eventId=evt-9001` nhưng chưa biết offset, ứng dụng cần tra index hoặc scan record. Không thể gọi `seek("evt-9001")` vì Kafka không hỗ trợ tìm trực tiếp theo value/header.

## 7. Duy trì chỉ mục event ID hoặc business checkpoint

Với workload cần replay thường xuyên theo event ID, có thể lưu chỉ mục trong database:

| event_id | topic | partition_id | offset | created_at |
|---|---|---:|---:|---|
| `evt-9001` | `orders.events` | 1 | 8450 | `2026-11-20T09:00:00Z` |
| `evt-9002` | `orders.events` | 0 | 1932 | `2026-11-20T09:01:12Z` |

Khi producer nhận metadata từ kết quả gửi thành công, ứng dụng có thể lưu topic, partition và offset cùng event ID vào index. Việc ghi event vào Kafka và ghi index vào database không tự động nguyên tử; nếu index là bắt buộc, cần thiết kế outbox, retry/reconciliation hoặc một pipeline index độc lập để tránh thiếu mapping.

Index phải tuân theo vòng đời dữ liệu Kafka. Offset không thay đổi số sau compaction, nhưng record tại offset đó có thể không còn tồn tại; retention có thể xóa cả segment chứa record. Trước khi replay, xác minh offset vẫn nằm trong phạm vi dữ liệu còn đọc được và xử lý trường hợp record đã bị compact/xóa.

Một lựa chọn khác là phát hành checkpoint định kỳ theo business key hoặc sequence number vào topic compacted riêng. Consumer có thể đọc checkpoint để biết vị trí gần nhất đã xử lý an toàn. Checkpoint phải được cập nhật nhất quán với side effect và offset commit; nếu checkpoint tiến trước dữ liệu nghiệp vụ, replay có thể bỏ sót công việc.

## 8. Tìm theo sequence number hoặc entity version

Nếu mỗi entity có sequence tăng dần, consumer có thể dùng sequence để xác định điểm bắt đầu chính xác hơn timestamp. Ví dụ các sự kiện của `account-42` có version 100, 101, 102. Khi cần phát lại từ version 102:

1. Dùng `accountId` làm Kafka key để các sự kiện cùng account đi vào cùng partition.
2. Lưu checkpoint mapping `accountId + version` tới partition/offset gần nhất.
3. Tra checkpoint version 102.
4. `seek()` tới offset tương ứng rồi xác thực `accountId` và version trong payload.
5. Nếu index chỉ trỏ tới offset gần trước version 102, scan tới khi gặp version đó.

Không giả định sequence number của các entity khác nhau có thể so sánh toàn cục. Version 102 của account A không nhất thiết xảy ra trước hoặc sau version 102 của account B. Kafka ordering vẫn nằm trong partition; sequence nghiệp vụ cần có phạm vi rõ ràng.

Nếu dữ liệu có thể đến trễ, timestamp nghiệp vụ không tăng đơn điệu theo offset. Một event được tạo lúc 09:00 có thể đến Kafka sau event 09:05. Khi đó, timestamp search chỉ giúp tìm điểm bắt đầu gần mốc; để tái dựng chính xác theo event time, consumer cần đọc và lọc theo trường nghiệp vụ, hoặc dùng index/changelog được xây dựng theo event time.

## 9. Tìm theo thời gian không đồng nghĩa lọc chính xác một khoảng thời gian

`offsetsForTimes()` chọn offset bắt đầu theo timestamp của Kafka record. Nó không tự giới hạn consumer chỉ đọc đến một timestamp kết thúc.

Muốn replay khoảng `[startTime, endTime)`, cần:

1. Tìm offset bắt đầu theo `startTime` cho từng partition.
2. Ghi nhận `endOffsets` tại thời điểm bắt đầu replay để tạo một snapshot giới hạn dữ liệu cần đọc, nếu mục tiêu là chỉ xử lý dữ liệu đã tồn tại lúc bắt đầu.
3. Đọc record và kiểm tra timestamp hoặc trường event time theo yêu cầu nghiệp vụ.
4. Dừng khi đạt end offset snapshot của partition, không chỉ dừng ở record đầu tiên có timestamp lớn hơn `endTime` nếu timestamp có thể đến không theo thứ tự offset.

Nếu timestamp là `CreateTime` do producer gửi và có thể out-of-order, một record có timestamp sau `endTime` có thể đứng trước một record đến trễ có timestamp trong khoảng cần replay. Dừng ngay ở record đầu tiên vượt `endTime` sẽ bỏ qua event đến trễ. Cần đọc tới end offset snapshot và lọc từng record, hoặc dựa trên giả định timestamp monotonic đã được bảo đảm bởi hệ thống.

Nếu timestamp type là `LogAppendTime`, timestamp thường phản ánh thứ tự broker append trong partition tốt hơn, nhưng nó vẫn không đại diện cho thời điểm nghiệp vụ ban đầu. Chọn timestamp theo đúng câu hỏi cần trả lời.

## 10. `seek()`, `auto.offset.reset` và reset group offsets khác nhau thế nào?

Ba cơ chế này thường bị nhầm lẫn:

| Cơ chế | Tác động | Khi nào dùng |
|---|---|---|
| `consumer.seek(tp, offset)` | Thay đổi vị trí đọc trong consumer hiện tại | Replay có kiểm soát trong một lần chạy |
| `auto.offset.reset` | Chọn vị trí khi group chưa có committed offset hợp lệ hoặc offset đã commit không còn trong log | Quy định hành vi mặc định khi bắt đầu/offset out of range |
| `kafka-consumer-groups --reset-offsets` | Thay đổi committed offset của một consumer group | Đặt lại tiến độ group để lần chạy sau tiếp tục từ điểm mới |

`auto.offset.reset=earliest` không tự kéo một group đã có committed offset về đầu topic. Nếu group có offset hợp lệ, consumer tiếp tục từ offset đó. Muốn replay group hiện tại, dùng `seek()` hoặc reset committed offsets có chủ đích.

`seek()` không tự commit vị trí mới. Nếu ứng dụng seek tới offset cũ rồi dừng trước khi commit tiến độ mới, lần chạy sau có thể trở lại committed offset trước đó. Nếu cần lưu vị trí replay cho lần khởi động sau, phải commit offset phù hợp sau khi xử lý thành công hoặc dùng CLI reset group offsets.

## 11. Reset theo offset hoặc mốc thời gian bằng CLI

Ngoài `--to-datetime`, Kafka CLI còn hỗ trợ các cách chọn vị trí:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--to-earliest` | Đặt về offset sớm nhất còn được lưu |
| `--to-latest` | Đặt về cuối log hiện tại |
| `--to-offset N` | Đặt tới offset N cho partition được chọn |
| `--to-datetime ...` | Tìm offset theo timestamp |
| `--shift-by N` | Dịch committed offset hiện tại thêm/bớt N vị trí |
| `--by-duration ...` | Chọn vị trí theo khoảng thời gian lùi từ hiện tại, nếu phiên bản CLI hỗ trợ |

Ví dụ reset riêng partition 1 về offset 8450 (cú pháp chọn partition cần được xác nhận theo phiên bản CLI):

```bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group order-replay \
  --topic orders.events:1 \
  --reset-offsets --to-offset 8450 --dry-run
```

Khi kết quả đã được kiểm tra, chạy lại với `--execute`. Offset được đặt theo từng partition; không dùng một offset duy nhất cho toàn topic nếu partition có tiến độ khác nhau.

Luôn kiểm tra `--help` của đúng phiên bản Kafka trước khi dùng cú pháp `topic:partition`, `--by-duration` hoặc định dạng datetime. Các tùy chọn có thể khác giữa các phiên bản.

## 12. Spring Kafka: seek theo timestamp hoặc checkpoint

Spring Kafka cung cấp `ConsumerSeekAware` để listener có thể yêu cầu seek khi partition được gán. Ví dụ khung:

```java
@KafkaListener(topics = "orders.events", groupId = "order-replay")
public class OrderReplayListener implements ConsumerSeekAware {

    private final long startTimeMs =
            Instant.parse("2026-11-20T09:00:00Z").toEpochMilli();

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        assignments.keySet().forEach(partition ->
                callback.seekToTimestamp(partition.topic(),
                        partition.partition(), startTimeMs));
    }

    @KafkaHandler
    public void listen(ConsumerRecord<String, String> record) {
        process(record);
    }
}
```

Đây là ví dụ minh họa API seek của Spring Kafka; cấu trúc class listener, method annotation và callback có thể cần điều chỉnh theo phiên bản Spring Kafka. `seekToTimestamp` sử dụng timestamp của Kafka record, không tìm trường `occurredAt` trong payload. Nếu cần seek theo business marker, tra index trước rồi dùng callback `seek(topic, partition, offset)`.

Khi dùng listener container, không gọi trực tiếp `KafkaConsumer.seek()` từ thread nghiệp vụ. Dùng `ConsumerSeekCallback` hoặc cơ chế seek của container để thực hiện trên consumer thread đúng vòng đời assignment. Nếu partition rebalance, callback được dùng lại cho assignment mới; logic seek cần xác định rõ khi nào chỉ áp dụng lúc khởi tạo và khi nào áp dụng mỗi lần được giao lại.

## 13. Quy trình replay an toàn

Trước khi phát lại dữ liệu, cần xác định phạm vi và tác động:

1. Xác định replay theo Kafka record time, event time, event ID, entity version hay checkpoint.
2. Xác định topic, partition và group sẽ bị ảnh hưởng.
3. Kiểm tra retention, compaction và offset bounds để biết dữ liệu còn tồn tại.
4. Ưu tiên tạo group replay riêng nếu không muốn thay đổi tiến độ của consumer production.
5. Chọn offset theo timestamp hoặc tra index business marker.
6. Với CLI reset, dừng group, chạy `--dry-run`, xác minh từng partition rồi mới `--execute`.
7. Bảo đảm consumer replay idempotent hoặc ghi sang output riêng để tránh side effect lặp.
8. Theo dõi lag, tốc độ replay, lỗi và tài nguyên broker/downstream.
9. Sau replay, lưu checkpoint mới và xác minh kết quả nghiệp vụ.

Nếu replay có thể gửi lại email, tạo đơn hàng, trừ tiền hoặc gọi API bên ngoài, cần bật chế độ replay an toàn hoặc chặn side effect không mong muốn. Reset offset chỉ thay đổi điểm đọc; nó không hiểu nghiệp vụ và không tự bảo vệ hệ thống downstream khỏi xử lý trùng.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `offsetsForTimes()` trả `null` | Không có record từ mốc đó trở đi, partition rỗng hoặc timestamp không phù hợp | Kiểm tra beginning/end offsets và quyết định fallback rõ ràng |
| Replay lệch múi giờ | CLI/JVM timezone không như giả định | Dùng UTC và epoch milliseconds; kiểm tra kết quả dry-run |
| Replay không đúng thời điểm nghiệp vụ | Kafka timestamp phản ánh thời gian gửi/append thay vì `occurredAt` | Gắn event time vào record timestamp theo CreateTime hoặc lọc theo payload/index |
| `auto.offset.reset=earliest` nhưng group không đọc từ đầu | Group đã có committed offset hợp lệ | Dùng `seek()` hoặc reset committed offsets |
| Reset CLI báo group đang hoạt động | Vẫn còn consumer member trong group | Dừng toàn bộ instance dùng group đó rồi chạy lại dry-run/execute |
| `seek()` xong restart lại đọc vị trí cũ | Vị trí seek chưa được commit | Commit tiến độ mới sau xử lý hoặc reset group offsets |
| Không tìm được event ID bằng Kafka CLI | Kafka không index payload/header theo event ID | Dùng external index hoặc scan từ checkpoint/offset đã biết |
| Offset trong index không còn record | Retention/compaction đã loại bỏ dữ liệu tại vị trí đó | Kiểm tra offset bounds và duy trì index đồng bộ với retention |
| Dừng replay ở timestamp cuối nhưng bỏ sót event đến trễ | Timestamp không tăng đơn điệu theo offset | Đọc tới end offset snapshot và lọc từng record theo event time |

## 15. Checklist thiết kế replay theo thời gian và nghiệp vụ

- Xác định rõ timestamp cần tìm là CreateTime, LogAppendTime hay trường event time trong payload.
- Chuẩn hóa timezone và đơn vị milliseconds.
- Tìm offset riêng cho từng partition.
- Xử lý `null` từ `offsetsForTimes()` theo chính sách cụ thể.
- Kiểm tra `beginningOffsets`/`endOffsets` và giới hạn retention.
- Dùng key ổn định nếu cần thứ tự theo entity.
- Duy trì mapping event ID/checkpoint tới partition và offset nếu cần replay chính xác theo marker.
- Kiểm tra index có thể trỏ tới record đã bị compaction/retention xóa hay không.
- Không nhầm `seek()` với commit offset của group.
- Dùng group replay riêng nếu cần giữ nguyên tiến độ production.
- Chạy CLI reset bằng `--dry-run` trước `--execute` và dừng group.
- Bảo vệ side effect bằng idempotency, deduplication hoặc output riêng.
- Nếu lọc time window, xử lý khả năng timestamp đến không theo thứ tự offset.

## 16. Ghi nhớ

Chọn điểm bắt đầu theo thời gian dùng timestamp index và `offsetsForTimes()` hoặc `--to-datetime`; kết quả là offset riêng cho từng partition và dựa trên timestamp của Kafka record. Chọn theo mốc nghiệp vụ cần biết partition/offset từ checkpoint hoặc index, hoặc scan record để tìm event ID, business key hay sequence number. Kafka không truy vấn trực tiếp payload/header theo business marker.

`seek()` thay đổi vị trí đọc của consumer hiện tại; `auto.offset.reset` chỉ dùng khi không có committed offset hợp lệ; `--reset-offsets` thay đổi tiến độ đã commit của group. Trước khi replay, kiểm tra timestamp semantics, timezone, retention, compaction, offset bounds và side effect downstream. Một kế hoạch replay tốt phải chọn đúng điểm bắt đầu, giữ nguyên tiến độ group không liên quan và xử lý an toàn các record được đọc lại.
