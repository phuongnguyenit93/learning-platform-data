# Seek về offset cụ thể

Trong Kafka, consumer thường tiếp tục đọc từ committed offset đã lưu cho consumer group. Tuy nhiên, có những tình huống cần chuyển vị trí đọc tới một offset khác: replay một đoạn dữ liệu để điều tra lỗi, chạy lại sự kiện sau khi sửa logic, bỏ qua phần log không còn cần xử lý hoặc bắt đầu từ một mốc thời gian. Kafka cung cấp API `seek()` để thay đổi vị trí đọc của consumer trên một partition.

Điểm quan trọng là `seek()` thay đổi position trong bộ nhớ của consumer đang chạy. Nó không tự thay đổi committed offset đã lưu cho group. Nếu consumer restart hoặc rebalance, position có thể được khôi phục từ committed offset cũ. Muốn thay đổi điểm tiếp tục bền vững, cần commit vị trí mới hoặc reset offset của consumer group bằng công cụ quản trị khi group đã dừng.

## 1. Seek là gì?

`seek()` đặt position của một consumer về một offset được chỉ định trong một `TopicPartition`. Lần `poll()` tiếp theo sẽ tiếp tục đọc từ vị trí đó theo dữ liệu hiện có của partition.

Ví dụ topic `orders` có partition 0 và consumer đang ở position 500. Nếu gọi `seek()` về offset 200, consumer sẽ đọc lại dữ liệu bắt đầu từ vị trí 200:

```text
Partition orders-0:

... 197  198  199  200  201  202  ...  499  500  501 ...
                    ^                       ^
                    |                       |
              seek về 200             position cũ

Sau seek: poll() tiếp tục từ offset 200
```

Offset là vị trí trong một partition, vì vậy cần chỉ rõ cả topic và partition. Offset 200 ở `orders-0` không liên quan tới offset 200 ở `orders-1`.

Seek hữu ích trong các trường hợp:

- Replay một partition từ offset xác định để kiểm tra hoặc tái xử lý sự kiện.
- Tiếp tục từ checkpoint do ứng dụng lưu riêng.
- Bỏ qua một vùng dữ liệu đã được xác minh không cần xử lý.
- Đọc lại dữ liệu sau khi sửa lỗi xử lý.
- Di chuyển tới offset gần thời điểm cần điều tra.

Seek cần được sử dụng có chủ đích vì đọc lại record có thể lặp lại side effect nghiệp vụ. Consumer nên idempotent hoặc có cơ chế kiểm soát replay.

## 2. Điều kiện trước khi gọi seek()

Consumer chỉ có thể seek tới partition mà nó đang sở hữu (đã được assign). Nếu dùng `subscribe()`, assignment được Kafka group coordinator quyết định sau quá trình poll và rebalance. Vì vậy, không gọi `seek()` ngay sau `subscribe()` khi partition chưa được gán.

Ví dụ thứ tự đúng:

```java
consumer.subscribe(List.of("orders"));

// Poll để tham gia group và nhận partition assignment.
consumer.poll(Duration.ofMillis(1000));

TopicPartition partition = new TopicPartition("orders", 0);
if (consumer.assignment().contains(partition)) {
    consumer.seek(partition, 200L);
}
```

Nếu ứng dụng dùng `assign()` để tự gán partition, có thể seek sau khi gọi `assign()`:

```java
TopicPartition partition = new TopicPartition("orders", 0);
consumer.assign(List.of(partition));
consumer.seek(partition, 200L);
```

`assign()` không tham gia cơ chế tự động phân phối partition của consumer group như `subscribe()`. Khi dùng `assign()`, ứng dụng phải tự quản lý việc phân công partition và tránh nhiều consumer cùng xử lý một partition ngoài ý muốn.

`KafkaConsumer` không thread-safe. `seek()`, `poll()`, `commitSync()` và phần lớn API consumer phải được gọi trên thread sở hữu consumer. Không lấy consumer từ thread listener rồi gọi seek trực tiếp từ một thread nghiệp vụ khác.

## 3. Seek tới offset tuyệt đối bằng KafkaConsumer

Ví dụ sau đặt consumer về offset 200 của partition `orders-0`:

```java
TopicPartition partition = new TopicPartition("orders", 0);

consumer.subscribe(List.of("orders"));
consumer.poll(Duration.ofMillis(1000));

if (!consumer.assignment().contains(partition)) {
    throw new IllegalStateException("Partition chưa được assign: " + partition);
}

consumer.seek(partition, 200L);

ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(1000));
```

Sau `seek()`, `position(partition)` phản ánh vị trí đọc mới. Tuy nhiên, offset 200 có thể không còn là record đọc được nếu log start offset đã tăng do retention, hoặc có thể nằm trong vùng offset có khoảng trống do compaction/transaction. Kafka tìm dữ liệu có thể đọc tại hoặc sau vị trí được yêu cầu theo log hiện tại; không nên giả định mọi số offset đều tương ứng với một record đang tồn tại.

Nếu seek tới offset thấp hơn log start offset hoặc vượt quá log end offset, consumer có thể gặp `OffsetOutOfRangeException` ở lần fetch tiếp theo. Cách xử lý phụ thuộc cấu hình `auto.offset.reset` hoặc logic xử lý lỗi của ứng dụng. Hãy kiểm tra mốc offset trước khi seek thay vì giả định consumer sẽ chờ cho tới khi log tăng tới offset mục tiêu.

## 4. Seek về đầu hoặc cuối partition

KafkaConsumer cung cấp hai API tiện ích:

```java
Set<TopicPartition> partitions = consumer.assignment();

// Đưa position về log start offset của các partition được gán.
consumer.seekToBeginning(partitions);

// Đưa position tới log end offset hiện tại của các partition được gán.
consumer.seekToEnd(partitions);
```

`seekToBeginning()` đưa position về đầu log hiện còn được giữ, không nhất thiết là offset 0. Dữ liệu đã bị retention hoặc compaction loại bỏ sẽ không thể được đọc lại.

`seekToEnd()` đưa position tới cuối log tại thời điểm gọi. Consumer sẽ chờ record mới được ghi sau vị trí đó. Đây là cách bắt đầu theo dõi dữ liệu mới của các partition đang được gán mà không đọc lại phần lịch sử hiện có.

Nếu muốn áp dụng cho một partition cụ thể, truyền tập chỉ gồm partition đó. Hai phương thức này cũng chỉ thay đổi position cục bộ, không tự cập nhật committed offset của group.

## 5. Kiểm tra offset hợp lệ trước khi seek

Trước khi seek, nên kiểm tra log start và log end offset để biết phạm vi dữ liệu hiện có:

```java
TopicPartition partition = new TopicPartition("orders", 0);

Map<TopicPartition, Long> beginning =
        consumer.beginningOffsets(Set.of(partition));
Map<TopicPartition, Long> end =
        consumer.endOffsets(Set.of(partition));

long startOffset = beginning.get(partition);
long endOffset = end.get(partition);
long targetOffset = 200L;

if (targetOffset < startOffset || targetOffset > endOffset) {
    throw new IllegalArgumentException(
            "Offset ngoài phạm vi log: start=" + startOffset
                    + ", end=" + endOffset
                    + ", target=" + targetOffset);
}

consumer.seek(partition, targetOffset);
```

Đây là kiểm tra phạm vi cơ bản. `endOffsets()` trả về vị trí cuối log mà client nhìn thấy theo isolation level và trạng thái cluster; khi dùng `read_committed`, mốc có thể khác so với `read_uncommitted`. Dữ liệu có thể thay đổi giữa thời điểm kiểm tra và seek, do producer tiếp tục ghi hoặc retention chạy nền. Vì vậy, vẫn cần xử lý `OffsetOutOfRangeException` trong vòng đời consumer.

Offset target bằng log end offset là vị trí tiếp theo, không phải offset của một record cuối cùng. Seek tới end nghĩa là chờ dữ liệu mới. Offset target bằng log start offset là vị trí sớm nhất còn có thể đọc tại thời điểm truy vấn.

## 6. Seek tương đối và replay theo timestamp

Trong một số tình huống, ứng dụng không biết trước offset chính xác mà chỉ muốn lùi hoặc tiến tương đối so với position hiện tại. Kafka client có thể dùng `position()` để lấy vị trí tiếp theo rồi tính offset mục tiêu:

```java
long currentPosition = consumer.position(partition);
long targetOffset = Math.max(startOffset, currentPosition - 100L);

consumer.seek(partition, targetOffset);
```

Ví dụ lùi 100 offset, có chặn tại log start offset. Đây là phép tính theo vị trí offset, không đảm bảo replay đúng 100 record nghiệp vụ vì có thể tồn tại khoảng trống offset. Nếu yêu cầu là replay 100 record thực tế, cần đọc và đếm record thay vì trừ số offset.

Khi muốn bắt đầu từ một thời điểm, dùng `offsetsForTimes()` để tìm offset đầu tiên có timestamp lớn hơn hoặc bằng timestamp mục tiêu:

```java
long targetTimestamp = Instant.parse("2026-01-15T10:00:00Z")
        .toEpochMilli();

Map<TopicPartition, Long> timestamps =
        Map.of(partition, targetTimestamp);
Map<TopicPartition, OffsetAndTimestamp> matches =
        consumer.offsetsForTimes(timestamps);

OffsetAndTimestamp match = matches.get(partition);
if (match != null) {
    consumer.seek(partition, match.offset());
} else {
    log.warn("Không tìm thấy record tại hoặc sau timestamp mục tiêu");
}
```

Timestamp có thể là `CreateTime` do producer gửi hoặc `LogAppendTime` do broker gán. Cần xác định timestamp phản ánh thời điểm phát sinh nghiệp vụ hay thời điểm Kafka ghi record. Nếu không có record phù hợp, kết quả của `offsetsForTimes()` có thể là `null`.

## 7. Seek chỉ thay đổi position, không reset committed offset

Đây là khác biệt quan trọng nhất khi sử dụng seek.

Giả sử group `orders-worker` đã commit offset 500. Consumer đang chạy và gọi `seek()` về offset 200:

```text
Committed offset của group: 500
Consumer position trước seek: 500

consumer.seek(partition, 200L)

Consumer position sau seek: 200
Committed offset của group: 500 (không đổi)
```

Nếu consumer tiếp tục chạy, nó đọc từ position 200. Nhưng nếu consumer restart hoặc partition bị revoke rồi assign lại, container/client có thể khôi phục position từ committed offset 500. Do đó, seek trong bộ nhớ không phải là thao tác reset tiến độ bền vững của group.

Nếu dùng KafkaConsumer thuần và muốn lưu vị trí mới cho group, có thể commit offset mục tiêu sau khi seek:

```java
long targetOffset = 200L;
consumer.seek(partition, targetOffset);

consumer.commitSync(Map.of(
        partition,
        new OffsetAndMetadata(targetOffset)));
```

Đoạn code trên lưu vị trí tiếp theo cần đọc là 200. Khi restart, group có thể tiếp tục từ vị trí đã commit này, miễn là offset vẫn hợp lệ và partition được gán cho consumer.

Khi replay, không nên commit offset mục tiêu một cách tùy tiện nếu nghiệp vụ cần giữ checkpoint cũ. Hãy xác định replay có chạy trên group riêng hay có chủ đích thay đổi tiến độ của group production. Thường nên dùng một group ID riêng cho tác vụ replay để không làm thay đổi tiến độ consumer đang phục vụ traffic chính.

## 8. Reset committed offset bằng Kafka CLI

Để thay đổi committed offset đã lưu của consumer group, Kafka cung cấp lệnh `kafka-consumer-groups.sh --reset-offsets`. Khác với `seek()`, đây là thao tác quản trị lên offset của group và có thể ảnh hưởng tới lần chạy tiếp theo của consumer.

Trước tiên, dừng toàn bộ consumer đang tham gia group cần reset. Kafka yêu cầu group ở trạng thái inactive/không có member đang hoạt động cho thao tác reset offset. Sau đó chạy `--dry-run` để xem kế hoạch:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-worker \
  --topic orders \
  --reset-offsets \
  --to-offset 200 \
  --dry-run
```

Nếu kết quả đúng với partition và offset dự kiến, thực hiện bằng `--execute`:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-worker \
  --topic orders \
  --reset-offsets \
  --to-offset 200 \
  --execute
```

Ví dụ trên áp dụng offset mục tiêu cho các partition thuộc topic được chọn theo phạm vi mà công cụ hiển thị. Với topic nhiều partition có log start/end khác nhau, hãy kiểm tra kết quả dry-run và bảo đảm offset hợp lệ cho từng partition trước khi execute. Cú pháp lọc partition cụ thể có thể khác theo phiên bản Kafka; kiểm tra `--help` của script đang cài trước khi chạy lệnh trong production.

Một số lựa chọn reset phổ biến:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--to-offset N` | Đặt committed offset về vị trí N |
| `--to-earliest` | Đặt về log start offset hiện còn được giữ |
| `--to-latest` | Đặt về log end offset hiện tại |
| `--shift-by N` | Dịch committed offset tương đối theo số offset |
| `--to-datetime ...` | Tìm vị trí theo thời điểm |
| `--by-duration ...` | Dịch về trước theo khoảng thời gian |
| `--dry-run` | Hiển thị kế hoạch mà chưa ghi thay đổi |
| `--execute` | Thực hiện thay đổi offset |

Reset offset có thể làm consumer đọc lại dữ liệu hoặc bỏ qua một phần dữ liệu. Luôn lưu lại trạng thái ban đầu, kiểm tra group ID/topic/partition và đọc kỹ kết quả dry-run trước khi execute. Sau reset, khởi động lại consumer và xác minh committed offset cùng hành vi đọc thực tế.

## 9. Seek trong Spring Kafka với ConsumerSeekAware

Khi dùng `@KafkaListener`, Spring Kafka quản lý KafkaConsumer bên trong listener container. Không nên tự tạo một consumer khác hoặc gọi API consumer trực tiếp từ thread nghiệp vụ chỉ để seek. Spring Kafka cung cấp `ConsumerSeekAware` và `ConsumerSeekCallback` để yêu cầu container thay đổi position trên consumer thread phù hợp.

Ví dụ seek tới offset được cấu hình khi partition được assign:

```java
@Component
public class OrderReplayListener implements ConsumerSeekAware {

    private final Map<TopicPartition, Long> replayOffsets = Map.of(
            new TopicPartition("orders", 0), 200L);

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        assignments.keySet().forEach(partition -> {
            Long target = replayOffsets.get(partition);
            if (target != null) {
                callback.seek(
                        partition.topic(),
                        partition.partition(),
                        target);
            }
        });
    }
}
```

`onPartitionsAssigned()` được gọi khi container nhận partition assignment. Callback cho phép yêu cầu seek đúng consumer thread. Ví dụ giả định `replayOffsets` đã được cung cấp từ cấu hình hoặc checkpoint của ứng dụng; cần kiểm tra offset nằm trong phạm vi log trước khi dùng.

Khi listener chạy concurrency, Spring Kafka có callback gắn với từng consumer thread. Nếu lưu callback để dùng về sau, phải lưu riêng theo thread/consumer và xóa hoặc cập nhật khi partition bị revoke; không dùng một biến callback dùng chung cho mọi consumer. `ConsumerSeekAware` còn có các callback như `registerSeekCallback`, `onPartitionsRevoked` và `onIdleContainer` để quản lý vòng đời seek theo nhu cầu. API cụ thể cần đối chiếu phiên bản Spring Kafka đang dùng.

Ví dụ listener nhận record:

```java
@KafkaListener(
        id = "ordersReplayListener",
        topics = "orders",
        groupId = "orders-replay-worker")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    log.info("Replay record partition={}, offset={}",
            record.partition(), record.offset());
    orderService.reprocess(record.value());
}
```

Nên dùng group ID riêng như `orders-replay-worker` cho luồng replay nếu không muốn thay đổi committed offset của group đang xử lý chính. Nếu cố ý replay bằng group production, phải phối hợp seek với commit/acknowledgment để xác định điểm tiếp tục sau khi replay kết thúc.

## 10. Seek và rebalance

Khi consumer group rebalance, partition có thể bị revoke rồi assign lại. Position được đặt bằng seek trước đó có thể bị thay thế khi container khôi phục từ committed offset hoặc khi callback assignment thực hiện logic khác. Nếu cần seek sau mỗi lần assignment, hãy đặt logic trong `ConsumerSeekAware.onPartitionsAssigned()` hoặc cơ chế rebalance callback tương ứng.

Ví dụ một consumer seek tới offset 200, sau đó partition bị revoke. Khi partition được assign lại, container có thể khởi tạo position theo committed offset của group. Nếu ứng dụng muốn tiếp tục từ checkpoint riêng, cần áp dụng checkpoint đó trong callback assignment mỗi lần thích hợp.

Không seek vượt qua các record chưa xử lý xong trong cùng partition nếu offset commit có thể đi qua chúng. Khi xử lý song song, phải theo dõi offset liên tục đã hoàn tất để tránh commit vượt qua record đang chạy.

## 11. Các lỗi thường gặp khi seek

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `IllegalStateException` khi seek | Partition chưa được assign cho consumer | Poll để nhận assignment hoặc gọi `assign()` trước khi seek |
| `OffsetOutOfRangeException` | Offset nhỏ hơn log start hoặc vượt phạm vi hợp lệ | Kiểm tra `beginningOffsets()`/`endOffsets()` và retention; chọn offset hợp lệ hoặc reset policy rõ ràng |
| Seek xong nhưng restart lại đọc vị trí cũ | Chỉ thay đổi position, committed offset không đổi | Commit vị trí mới hoặc reset group offset bằng CLI |
| Consumer không nhận record sau seek | Seek tới cuối log, offset vượt dữ liệu hiện có hoặc `read_committed` bị giới hạn bởi transaction đang mở | Kiểm tra LEO/LSO, isolation level và producer activity |
| Replay gây side effect trùng | Record được xử lý lại từ offset cũ | Dùng group replay riêng, idempotency key hoặc cơ chế deduplication |
| Seek không có tác dụng sau rebalance | Assignment mới khôi phục position theo committed offset hoặc callback khác ghi đè | Đặt seek trong `onPartitionsAssigned()` và kiểm tra thứ tự callback |
| CLI reset báo group đang hoạt động | Consumer vẫn đang tham gia group | Dừng toàn bộ consumer của group rồi chạy lại dry-run |

## 12. Quy trình replay an toàn

Một quy trình replay có kiểm soát có thể thực hiện như sau:

1. Xác định topic, partition và khoảng offset cần đọc lại.
2. Kiểm tra log start/end offset, retention và isolation level để xác nhận dữ liệu còn khả dụng.
3. Quyết định dùng consumer group riêng cho replay hay thay đổi committed offset của group hiện tại.
4. Đánh giá side effect và bảo đảm handler idempotent hoặc có cơ chế chống xử lý trùng.
5. Nếu dùng `seek()`, bảo đảm partition đã assign và thực hiện trên consumer thread.
6. Nếu cần reset group offset, dừng consumer, chạy `--dry-run`, kiểm tra kết quả rồi mới `--execute`.
7. Khởi động consumer, xác minh partition/offset thực tế và theo dõi lag, lỗi xử lý, số record replay.
8. Sau khi hoàn tất, xác nhận group tiếp tục từ checkpoint mong muốn và không bỏ sót dữ liệu mới.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| `seek()` thay đổi committed offset | `seek()` chỉ thay đổi position cục bộ; cần commit hoặc reset group offset để lưu bền vững |
| Có thể seek ngay sau `subscribe()` | Cần chờ partition assignment, thường bằng cách poll trước |
| `seekToBeginning()` luôn về offset 0 | Nó về log start offset hiện còn được giữ |
| `seekToEnd()` đọc record cuối cùng | Nó đặt position ở cuối log hiện tại để chờ record mới |
| Trừ 100 offset nghĩa là replay 100 record | Offset có thể có khoảng trống; số offset không luôn bằng số record |
| Reset offset CLI dùng được khi consumer đang chạy | Group phải inactive; cần dừng consumer trước khi reset |
| Seek tới một offset bất kỳ luôn trả đúng record có offset đó | Offset có thể không còn tồn tại hoặc bị bỏ trống; consumer đọc theo log hiện tại từ vị trí yêu cầu |
| Replay bằng group production không ảnh hưởng tiến độ chính | Replay có thể thay đổi position/committed offset và gây đọc trùng hoặc bỏ qua dữ liệu |

## Checklist

- Đã xác định đúng topic, partition và offset mục tiêu.
- Consumer đã được assign partition trước khi gọi `seek()`.
- Kiểm tra log start/end offset và khả năng offset đã bị retention loại bỏ.
- Hiểu `seek()` chỉ thay đổi position, không tự cập nhật committed offset.
- Chọn rõ commit vị trí mới, dùng group replay riêng hay reset group offset.
- Nếu dùng Kafka CLI, group đã inactive và đã kiểm tra `--dry-run` trước `--execute`.
- Với Spring Kafka, dùng `ConsumerSeekAware`/`ConsumerSeekCallback` thay vì truy cập consumer từ thread khác.
- Có idempotency hoặc deduplication để kiểm soát side effect khi replay.
- Theo dõi offset thực tế, lag và kết quả xử lý sau khi seek.

`seek()` là công cụ điều khiển position mạnh mẽ cho từng partition. Khi phân biệt rõ position với committed offset, chờ assignment trước khi seek và kiểm tra phạm vi log, ứng dụng có thể replay hoặc chuyển điểm đọc có kiểm soát. Với Spring Kafka, `ConsumerSeekAware` giúp tích hợp thao tác seek vào lifecycle của listener container; với thay đổi tiến độ bền vững của group, hãy dùng commit hoặc quy trình reset offset có kiểm soát.
