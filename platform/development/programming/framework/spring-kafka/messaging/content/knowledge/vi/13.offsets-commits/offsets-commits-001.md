# Ý nghĩa của offset trong partition

Trong Kafka, mỗi record được ghi vào một partition sẽ có một vị trí gọi là **offset**. Offset cho biết vị trí của record trong log của partition đó, giúp consumer biết đang đọc tới đâu và có thể tiếp tục từ vị trí đã lưu sau khi restart. Offset cũng là thông tin quan trọng để truy vết record, kiểm tra consumer lag, replay dữ liệu và xác định tiến độ xử lý.

Offset chỉ có ý nghĩa trong phạm vi một partition. Nó không phải mã định danh toàn cục của record, không phải số thứ tự chung của cả topic và cũng không nhất thiết phản ánh số lượng record đã được xử lý. Để xác định một record trong Kafka, cần kết hợp tên topic, partition và offset.

## 1. Offset là vị trí trong log của một partition

Topic được chia thành một hoặc nhiều partition. Mỗi partition là một log độc lập, trong đó record được nối thêm ở cuối log. Broker gán offset cho record khi ghi vào partition. Offset tăng theo tiến trình ghi của partition đó.

Ví dụ topic `orders` có hai partition:

```text
orders-0:  offset 0 -> offset 1 -> offset 2 -> offset 3 -> ...
orders-1:  offset 0 -> offset 1 -> offset 2 -> offset 3 -> ...
```

Offset `2` trong `orders-0` và offset `2` trong `orders-1` là hai record khác nhau. Không thể xác định một record chỉ bằng offset mà bỏ qua partition.

Một record có thể được nhận diện bằng bộ ba:

```text
topic     = orders
partition = 0
offset    = 42
```

Đây là vị trí của một record trong log partition `orders-0`. Khi ghi log, nên lưu cả ba trường này cùng event ID hoặc business key nếu cần truy vết xuyên hệ thống.

## 2. Offset không phải số thứ tự toàn cục

Kafka chỉ bảo đảm thứ tự record bên trong cùng một partition. Hai partition có thể ghi và được consumer đọc độc lập. Vì vậy, offset 100 ở partition 0 không nhất thiết xảy ra trước offset 50 ở partition 1.

| Phạm vi | Bảo đảm về thứ tự |
|---|---|
| Một partition | Record có thứ tự theo offset tăng dần |
| Nhiều partition trong cùng topic | Không có thứ tự toàn cục giữa các partition |
| Nhiều topic | Không có thứ tự toàn cục được Kafka bảo đảm |

Nếu nghiệp vụ cần các sự kiện của cùng một đơn hàng được đọc theo thứ tự, producer thường gửi `orderId` làm key để các record cùng key được đưa vào cùng partition. Khi đó offset trong partition giúp consumer đọc các sự kiện của đơn hàng theo thứ tự đã ghi.

Không nên dùng offset để so sánh thời điểm nghiệp vụ giữa các partition. Nếu cần thời điểm, hãy dùng timestamp của record hoặc trường thời gian nghiệp vụ trong payload. Timestamp cũng có semantics riêng và không thay thế offset.

## 3. Offset được gán như thế nào?

Producer gửi record tới một topic. Partitioner chọn partition đích; broker leader của partition ghi record vào log và gán offset. Producer nhận metadata phản hồi, thường bao gồm topic, partition và offset của record đã được ghi.

Luồng cơ bản:

```text
Producer gửi record
        |
        v
Chọn partition
        |
        v
Broker leader append record vào log
        |
        v
Gán offset trong partition
        |
        v
Producer nhận metadata (partition, offset)
        |
        v
Consumer poll và nhận record cùng offset
```

Ví dụ gửi bằng Spring Kafka:

```java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders", event.orderId(), event);

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error("Không gửi được order event", error);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.info("topic={}, partition={}, offset={}",
            metadata.topic(), metadata.partition(), metadata.offset());
});
```

`RecordMetadata.offset()` là offset của record được broker ghi nhận. Nếu producer retry hoặc dùng idempotence, client xử lý một số tình huống gửi lại trong phạm vi bảo đảm của producer; điều đó không biến offset thành event ID nghiệp vụ. Nếu ứng dụng phát cùng một sự kiện bằng một lần gọi send mới, record mới vẫn có thể có offset khác.

## 4. Offset không nhất thiết liên tục trong dữ liệu consumer nhận được

Offset thường tăng dần, nhưng consumer không nên giả định các record nó nhìn thấy luôn có offset liên tiếp 0, 1, 2, 3. Có thể có khoảng trống vì:

- Topic dùng log compaction: Kafka có thể loại bỏ các record cũ của cùng key nhưng không đánh lại offset của record còn lại.
- Consumer dùng `isolation.level=read_committed`: record thuộc transaction đã abort không được trả về cho consumer, nên có thể bỏ qua các offset tương ứng.
- Log chứa control record phục vụ transaction hoặc các bản ghi nội bộ mà ứng dụng không nhận như record nghiệp vụ thông thường.
- Retention xóa các segment cũ; consumer không còn đọc được những offset đã bị xóa.

Ví dụ sau compaction, consumer có thể nhìn thấy:

```text
Offset 10: key=A, value=A-v1   (đã bị compact loại khỏi log đọc được)
Offset 11: key=B, value=B-v1
Offset 12: key=A, value=A-v2
Offset 13: key=C, value=C-v1

Consumer có thể nhận: 11, 12, 13
```

Ví dụ trên minh họa rằng offset là vị trí log, không phải chỉ số thứ tự của phần tử trong danh sách consumer nhận được. Không tự tăng offset bằng cách đếm số record đã xử lý rồi giả định offset tiếp theo bằng số đếm đó.

## 5. Các mốc offset quan trọng trong partition

Khi vận hành Kafka, thường cần phân biệt log start offset, log end offset, high watermark và last stable offset. Các mốc này mô tả phạm vi log và dữ liệu có thể đọc theo isolation level.

| Mốc | Ý nghĩa |
|---|---|
| Log start offset | Offset sớm nhất còn có thể đọc trong partition; có thể tăng khi retention hoặc compaction loại bỏ dữ liệu cũ |
| Log end offset (LEO) | Vị trí tiếp theo ở cuối log leader; record mới sẽ được append tại vị trí này |
| High watermark (HW) | Ranh giới dữ liệu đã được replicate đủ theo semantics của Kafka; consumer `read_uncommitted` chỉ đọc dữ liệu dưới ranh giới này |
| Last stable offset (LSO) | Ranh giới đọc an toàn cho consumer `read_committed`; transaction đang mở có thể giữ LSO lại phía sau HW |

Minh họa khái quát:

```text
log start                                      log end
    |                                             |
    v                                             v
    +---- dữ liệu đã ghi và replicate ----+-------+
                          ^               ^
                          |               |
                         HW              LEO

Nếu có transaction chưa kết thúc:
                         LSO
                          ^
                          |
               read_committed dừng ở đây
```

LEO có thể đi trước HW vì record đã được append ở leader nhưng chưa replicate đủ. Với `read_uncommitted`, consumer không đọc vượt high watermark. Với `read_committed`, consumer chỉ nhận record thuộc transaction đã commit và dữ liệu non-transactional trong phạm vi LSO; transaction đang mở có thể làm các record phía sau chưa hiển thị.

Các mốc này là vị trí offset, thường biểu thị ranh giới tiếp theo chứ không phải offset của record cuối cùng. Khi xem metric hoặc output của công cụ quản trị, cần đọc đúng semantics của trường được hiển thị và phiên bản Kafka.

## 6. Log start offset thay đổi khi retention hoặc compaction

Offset không được đánh lại từ 0 sau khi Kafka xóa dữ liệu cũ. Ví dụ partition từng có các offset từ 0 đến 999. Sau retention, những segment đầu bị xóa và log start offset có thể chuyển lên 400. Record mới vẫn tiếp tục được ghi với offset ở cuối log, không quay lại offset 0.

```text
Trước retention:
0  1  2  3  4  5  ...  999

Sau retention:
                    400 401 402 ... 999
                    ^
                    log start offset
```

Nếu consumer group lưu committed offset là 250 nhưng log start offset đã tăng lên 400, consumer không thể đọc lại offset 250 vì dữ liệu đó đã bị loại bỏ. Client có thể gặp `OffsetOutOfRangeException`; chính sách `auto.offset.reset` quyết định cách xử lý khi offset không còn hợp lệ.

`auto.offset.reset=earliest` có nghĩa bắt đầu từ offset sớm nhất còn được giữ, không phải luôn quay về offset 0. `latest` bắt đầu từ cuối log theo thời điểm reset. Nếu group đã có committed offset hợp lệ, `auto.offset.reset` không được áp dụng chỉ vì consumer restart.

Với topic compacted, compaction giữ lại giá trị mới nhất theo key theo tiến trình nền và có thể tạo ra khoảng trống offset tương tự. Tombstone cũng là record có offset, dùng để biểu thị việc xóa key; nó không phải offset rỗng.

## 7. Consumer position và committed offset khác nhau

Consumer có hai khái niệm quan trọng:

- **Position**: vị trí hiện tại của consumer trong partition, tức offset tiếp theo mà consumer sẽ nhận khi poll.
- **Committed offset**: vị trí đã được lưu cho consumer group để consumer có thể tiếp tục sau restart hoặc rebalance.

Ví dụ consumer vừa nhận record offset 40:

```text
Record vừa nhận:       offset 40
Consumer position:     41 (vị trí tiếp theo dự kiến đọc)
Committed offset:      40 hoặc thấp hơn (nếu chưa commit tiến độ mới)
```

Trong ví dụ, committed offset có thể vẫn là 40 nếu trước đó group đã lưu vị trí bắt đầu từ 40; khi xử lý xong record 40, consumer cần commit offset 41. Position có thể tiến lên khi record được trả về từ `poll()`, ngay cả khi nghiệp vụ chưa hoàn tất. Vì vậy, không được coi position hiện tại là bằng chứng rằng record đã xử lý bền vững.

Nếu consumer xử lý record 40 thành công nhưng chưa commit 41 rồi tiến trình dừng, lần chạy tiếp theo có thể nhận lại record 40. Đây là hành vi at-least-once phổ biến. Nếu commit 41 trước khi xử lý thành công, tiến trình dừng có thể khiến record 40 bị bỏ qua trong lần chạy tiếp theo.

## 8. Vì sao offset commit là vị trí tiếp theo cần đọc?

Kafka lưu committed offset như vị trí tiếp theo consumer group cần đọc, không phải offset của record cuối cùng đã xử lý. Nếu xử lý thành công record offset 42, vị trí cần commit là 43.

```text
Partition orders-0:

offset 40  -> đã xử lý
offset 41  -> đã xử lý
offset 42  -> vừa xử lý thành công
offset 43  -> vị trí tiếp theo cần đọc

Commit: 43
```

Ví dụ commit thủ công bằng Kafka client:

```java
Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();
TopicPartition partition = new TopicPartition("orders", 0);

// Record offset 42 đã xử lý thành công, nên commit vị trí tiếp theo là 43.
offsets.put(partition, new OffsetAndMetadata(43));
consumer.commitSync(offsets);
```

Nếu dùng `commitSync()` không truyền map, Kafka client commit các position hiện tại của consumer. Chỉ thực hiện điều đó sau khi các record tương ứng đã được xử lý thành công. Khi xử lý song song, cần bảo đảm không commit vượt qua offset của record chưa hoàn tất trong cùng partition.

Spring Kafka cũng tuân theo nguyên tắc commit vị trí tiếp theo. Với AckMode do container quản lý, Spring tính offset cần commit sau khi listener hoàn thành theo chế độ đã chọn. Khi dùng `Acknowledgment`, hãy gọi `acknowledge()` sau khi nghiệp vụ hoàn tất hoặc công việc đã được lưu bền vững.

## 9. Đọc metadata offset bằng KafkaConsumer

Kafka client cung cấp API để xem position, committed offset và các mốc của partition. Các API dưới đây nên được gọi trên thread sở hữu `KafkaConsumer`; consumer không thread-safe.

```java
TopicPartition tp = new TopicPartition("orders", 0);

// Sau khi partition đã được assign:
long position = consumer.position(tp);

OffsetAndMetadata committed = consumer.committed(tp);
Long committedOffset = committed == null ? null : committed.offset();

Map<TopicPartition, Long> beginning =
        consumer.beginningOffsets(Set.of(tp));
Map<TopicPartition, Long> end =
        consumer.endOffsets(Set.of(tp));

log.info("position={}, committed={}, beginning={}, end={}",
        position, committedOffset, beginning.get(tp), end.get(tp));
```

`position(tp)` trả về vị trí tiếp theo consumer sẽ đọc. `committed(tp)` trả về offset group đã commit hoặc `null` nếu chưa có. `beginningOffsets()` và `endOffsets()` trả về các ranh giới log mà consumer client nhìn thấy theo isolation level và trạng thái cluster. Các lời gọi lấy offset có thể cần trao đổi metadata với broker; không nên gọi dồn dập trong đường xử lý từng record.

Để chuyển consumer tới một offset cụ thể, có thể dùng `seek()` sau khi partition đã được gán:

```java
consumer.seek(tp, 100L);
```

`seek()` thay đổi position cục bộ của consumer; nó không tự commit offset mới cho group. Nếu consumer restart trước khi commit, committed offset cũ vẫn là điểm tiếp tục. `seekToBeginning()` và `seekToEnd()` cũng thay đổi position, không tự động thay đổi committed offset đã lưu.

## 10. Tìm offset theo timestamp

Kafka lưu timestamp cùng record. Consumer có thể tìm offset đầu tiên có timestamp lớn hơn hoặc bằng thời điểm yêu cầu bằng `offsetsForTimes()`:

```java
Map<TopicPartition, Long> timestamps = Map.of(tp, targetEpochMillis);
Map<TopicPartition, OffsetAndTimestamp> matches =
        consumer.offsetsForTimes(timestamps);

OffsetAndTimestamp match = matches.get(tp);
if (match != null) {
    consumer.seek(tp, match.offset());
}
```

Nếu không tìm thấy record phù hợp trong partition, kết quả có thể là `null`. Timestamp được dùng có thể là `CreateTime` do producer cung cấp hoặc `LogAppendTime` do broker gán, tùy cấu hình topic/broker. Nếu cần replay từ thời điểm nghiệp vụ, phải hiểu timestamp đang biểu diễn thời điểm nào và cân nhắc độ trễ giữa thời điểm phát sinh sự kiện với thời điểm ghi vào Kafka.

Tìm offset theo timestamp hữu ích cho replay theo khoảng thời gian, điều tra sự cố hoặc chạy lại dữ liệu từ một mốc. Sau khi tìm được offset, hãy xác định rõ group nào đang sử dụng và có cần commit position mới hay không. Không dùng `seek()` như thao tác reset offset lâu dài nếu consumer group cần tiếp tục từ vị trí mới sau restart; khi cần thay đổi committed offset, dùng cơ chế quản trị hoặc commit có chủ đích.

## 11. Offset trong Spring Kafka

Với `@KafkaListener`, có thể nhận trực tiếp `ConsumerRecord<K, V>` để đọc metadata của record:

```java
@KafkaListener(topics = "orders", groupId = "orders-worker")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    log.info("topic={}, partition={}, offset={}, timestamp={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.timestamp(),
            record.key());

    orderService.handle(record.value());
}
```

`ConsumerRecord` cho phép truy cập topic, partition, offset, timestamp, key, value và headers. Đây là cách rõ ràng khi cần trace hoặc xử lý theo partition. Nếu listener chỉ nhận payload, Spring Kafka vẫn quản lý metadata và offset ở container nhưng phương thức không có đầy đủ thông tin record.

Với manual acknowledgment:

```java
@KafkaListener(topics = "orders", groupId = "orders-worker")
public void onOrder(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    orderService.handleAndPersist(record.value());
    acknowledgment.acknowledge();
}
```

Container commit vị trí tiếp theo sau record đã được xác nhận, theo AckMode và semantics của Spring Kafka. Không tự lấy `record.offset()` rồi commit đúng số đó; committed offset cần là vị trí tiếp theo. Cũng không acknowledge trước khi side effect nghiệp vụ hoàn tất nếu muốn tránh mất xử lý.

## 12. Offset và consumer lag

Consumer lag thường được tính bằng chênh lệch giữa log end offset và vị trí consumer group đã commit hoặc vị trí đọc đang được theo dõi, tùy hệ thống metric. Ở mức khái niệm:

\[
\text{lag} \approx \text{log end offset} - \text{committed offset}
\]

Ví dụ log end offset là 500 và committed offset là 470 thì lag xấp xỉ 30 offset. Đây là chênh lệch vị trí, không nhất thiết chính xác bằng 30 record nghiệp vụ mà consumer sẽ nhìn thấy, vì compaction, transaction và các khoảng trống offset có thể ảnh hưởng.

Lag lớn có thể cho biết producer ghi nhanh hơn consumer xử lý, consumer bị pause, listener xử lý chậm hoặc group không có đủ consumer/partition assignment. Lag bằng 0 thường cho biết group đang theo kịp log tại thời điểm đo; record mới vẫn có thể xuất hiện ngay sau đó.

Kiểm tra bằng Kafka CLI:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-worker
```

Kết quả thường hiển thị `CURRENT-OFFSET`, `LOG-END-OFFSET` và `LAG` cho từng partition. Hãy đọc theo từng partition để xác định partition nào bị chậm; tổng lag của group có thể che khuất một partition nóng hoặc một consumer bị lỗi.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Offset là ID duy nhất của record trong toàn Kafka | Offset chỉ duy nhất trong một partition; cần topic + partition + offset |
| Offset 100 luôn cũ hơn offset 50 | Chỉ có thể so sánh thứ tự offset trong cùng partition |
| Offset bằng số record đã xử lý | Offset là vị trí log; có thể có khoảng trống do compaction, transaction hoặc retention |
| Commit offset 42 sau khi xử lý record 42 | Thường phải commit 43, tức vị trí tiếp theo cần đọc |
| Position bằng committed offset | Position là vị trí đọc hiện tại; committed offset là tiến độ đã lưu cho group |
| `earliest` luôn bắt đầu từ offset 0 | Bắt đầu từ log start offset hiện còn được giữ |
| `seek()` tự lưu offset cho lần restart sau | `seek()` thay đổi position cục bộ; cần commit nếu muốn lưu tiến độ mới cho group |
| Lag 30 luôn có nghĩa còn đúng 30 record nghiệp vụ | Lag là chênh lệch offset; dữ liệu compaction/transaction có thể làm số record nhìn thấy khác đi |

## 14. Quy trình sử dụng offset trong thực tế

1. Khi producer gửi record, ghi nhận metadata topic, partition và offset nếu cần truy vết.
2. Khi consumer nhận record, log topic/partition/offset cùng event ID để hỗ trợ điều tra.
3. Xử lý nghiệp vụ và lưu kết quả bền vững trước khi xác nhận offset theo chính sách đã chọn.
4. Commit vị trí tiếp theo cần đọc, không commit offset của record vừa xử lý.
5. Khi restart hoặc rebalance, consumer tiếp tục từ committed offset của group.
6. Khi replay, xác định partition và offset/timestamp bắt đầu; đánh giá tác động của việc xử lý lại và tính idempotent.
7. Theo dõi log start, log end, committed offset và lag theo từng partition.
8. Nếu offset đã bị retention xóa, chọn chính sách reset có chủ đích và hiểu dữ liệu nào sẽ bị bỏ qua hoặc đọc lại.

## Checklist

- Xác định record bằng topic, partition và offset.
- Hiểu ordering chỉ được bảo đảm trong một partition.
- Không giả định offset liên tục hoặc bằng số record đã xử lý.
- Phân biệt log start offset, log end offset, high watermark và last stable offset.
- Phân biệt consumer position với committed offset.
- Commit offset tiếp theo sau record đã xử lý thành công.
- Dùng `seek()` đúng partition và hiểu rằng seek không tự commit.
- Xem xét retention, compaction và `read_committed` khi offset có khoảng trống hoặc không còn hợp lệ.
- Theo dõi lag theo từng partition và xử lý record theo cách idempotent khi có thể được giao lại.

Offset là nền tảng để Kafka theo dõi vị trí đọc và giúp ứng dụng phục hồi sau lỗi. Khi hiểu offset theo từng partition, phân biệt position với committed offset và commit đúng vị trí tiếp theo, ứng dụng Spring Kafka có thể quản lý tiến độ tiêu thụ, replay và xử lý sự kiện một cách có kiểm soát.
