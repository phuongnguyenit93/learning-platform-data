# `commitSync`, `commitAsync` và xử lý lỗi commit

Kafka Consumer đọc record theo offset và lưu tiến độ của consumer group bằng thao tác **commit offset**. Commit cho coordinator biết group sẽ tiếp tục đọc từ vị trí nào khi consumer khởi động lại hoặc partition được giao cho member khác. Kafka Java Consumer cung cấp hai cách commit thủ công phổ biến: **`commitSync()`** và **`commitAsync()`**.

`commitSync()` chờ kết quả commit trước khi trả về, phù hợp khi ứng dụng cần biết commit đã hoàn tất trước khi tiếp tục. `commitAsync()` gửi yêu cầu commit rồi trả về ngay, giúp giảm thời gian chờ trong vòng poll, nhưng ứng dụng cần xử lý lỗi trong callback và chú ý thứ tự giữa các lần commit. Chọn sai thời điểm commit có thể gây xử lý trùng hoặc bỏ sót dữ liệu.

## 1. Offset commit thực sự lưu điều gì?

Consumer đọc record trong từng partition. Offset của record là vị trí của record trong partition đó. Khi commit, consumer group lưu **offset kế tiếp cần đọc**, không phải offset của record cuối cùng đã xử lý.

Ví dụ, consumer đã xử lý thành công record có offset 10. Giá trị cần commit là 11:

```text
Partition 0:
  record offset:  8   9   10  11  12
  đã xử lý:       ✓   ✓   ✓
  commit:                     11
  đọc tiếp từ:                11
```

Kafka lưu tiến độ group qua group coordinator, thường được lưu bền vững trong topic nội bộ `__consumer_offsets`. Offset được quản lý riêng cho từng cặp topic-partition. Một group có thể đã commit offset 11 ở partition 0 nhưng offset 25 ở partition 1.

Trong Java:

```java
TopicPartition partition = new TopicPartition("orders.events", 0);
OffsetAndMetadata nextOffset = new OffsetAndMetadata(11L);

consumer.commitSync(Map.of(partition, nextOffset));
```

Giá trị 11 có nghĩa consumer sẽ tiếp tục đọc từ offset 11 nếu record đó còn tồn tại và chính sách reset offset không can thiệp. Không commit 10 nếu đã xử lý xong offset 10, vì lần khởi động sau có thể đọc lại record 10.

## 2. Tắt auto commit khi muốn tự kiểm soát

Kafka Java Consumer có cơ chế auto commit. Khi `enable.auto.commit=true`, consumer tự commit tiến độ theo chu kỳ `auto.commit.interval.ms`. Cơ chế này thuận tiện cho ứng dụng đơn giản, nhưng không tự biết logic nghiệp vụ đã xử lý xong record hay chưa.

Ví dụ rủi ro: consumer poll một batch gồm offset 10–19, auto commit tiến độ 20, nhưng ứng dụng mới xử lý đến offset 14 rồi gặp lỗi. Nếu process dừng, lần chạy sau có thể bắt đầu từ 20 và bỏ qua các record 15–19.

Với xử lý cần kiểm soát thời điểm commit, cấu hình:

```java
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
```

Khi đó ứng dụng chịu trách nhiệm commit sau khi đã xử lý an toàn các record. Cần lưu ý consumer có thể poll một batch lớn hơn khả năng xử lý trong thời gian cho phép; phải cân nhắc `max.poll.records`, `max.poll.interval.ms` và thời gian xử lý mỗi batch để tránh bị loại khỏi group.

## 3. `commitSync()`: commit đồng bộ

`commitSync()` gửi offset tới group coordinator và chặn thread gọi cho đến khi commit hoàn tất hoặc lỗi không thể phục hồi được báo về. Với lỗi tạm thời có thể retry, client có thể thử lại trong giới hạn timeout của API.

Hai cách gọi thường dùng:

```java
// Commit các offset hiện tại mà consumer quản lý từ lần poll gần nhất.
consumer.commitSync();

// Commit chính xác offset kế tiếp cho từng partition.
consumer.commitSync(offsets);
```

Overload nhận `Map<TopicPartition, OffsetAndMetadata>` cho phép chỉ rõ partition và offset cần commit. Cách này hữu ích khi ứng dụng muốn commit đúng các record đã xử lý thành công, nhất là khi xử lý nhiều partition hoặc có logic batch riêng.

### Ưu điểm

- Biết commit đã hoàn tất trước khi tiếp tục sau lời gọi.
- Dễ viết logic tuần tự: poll, xử lý, commit.
- Phù hợp cho batch có yêu cầu không tiến offset trước khi toàn bộ batch xử lý xong.
- Khi cần chốt tiến độ cuối cùng, một lần `commitSync()` có thể đợi các commit async trước đó hoàn tất rồi mới commit đồng bộ.

### Đánh đổi

- Thread consumer phải chờ coordinator và network response.
- Commit thường xuyên có thể làm giảm throughput và tăng thời gian vòng poll.
- Nếu rebalance xảy ra, commit có thể thất bại vì consumer không còn quyền commit cho partition đã mất.

`commitSync()` không làm cho xử lý nghiệp vụ và commit offset trở thành một transaction nguyên tử. Nếu ứng dụng đã ghi database thành công nhưng commit offset thất bại, record có thể được đọc và xử lý lại.

## 4. `commitAsync()`: commit bất đồng bộ

`commitAsync()` gửi yêu cầu commit rồi trả về ngay, không chờ broker phản hồi. Có thể truyền callback để nhận kết quả:

```java
consumer.commitAsync((offsets, exception) -> {
    if (exception == null) {
        log.info("Committed offsets: {}", offsets);
    } else {
        log.error("Offset commit failed: {}", offsets, exception);
    }
});
```

Có thể truyền map offset cụ thể:

```java
consumer.commitAsync(offsets, (committed, exception) -> {
    if (exception != null) {
        log.error("Could not commit offsets: {}", committed, exception);
    }
});
```

### Ưu điểm

- Không chặn vòng poll để chờ phản hồi commit.
- Phù hợp cho commit định kỳ trong luồng tiêu thụ có throughput cao.
- Callback cho phép ghi nhận kết quả hoặc phát cảnh báo khi commit thất bại.

### Đánh đổi

- Ứng dụng không biết kết quả ngay tại thời điểm gọi.
- Lỗi commit phải được xử lý trong callback.
- Nếu tự retry một commit cũ sau khi commit mới hơn đã thành công, offset có thể bị lùi về vị trí cũ.

Kafka đảm bảo callback của các lần `commitAsync()` được gọi theo thứ tự các lần commit tương ứng. Tuy vậy, commit async không tự retry lỗi theo cách đơn giản như sync: retry một offset cũ sau một commit mới hơn có thể ghi đè tiến độ mới. Vì vậy, cách thường dùng là ghi log/cảnh báo khi async commit thất bại và để lần commit mới nhất tiếp theo cập nhật tiến độ.

## 5. So sánh `commitSync()` và `commitAsync()`

| Tiêu chí | `commitSync()` | `commitAsync()` |
|---|---|---|
| Chờ kết quả | Có, block đến khi hoàn tất hoặc lỗi được báo | Không, trả về ngay sau khi gửi yêu cầu |
| Nhận lỗi | Qua exception | Qua callback |
| Retry lỗi tạm thời | Client có thể retry trong thời hạn API | Không tự retry theo cách có thể làm đảo thứ tự commit |
| Throughput | Có thể giảm nếu commit thường xuyên | Thường ít chặn vòng poll hơn |
| Phù hợp | Commit sau batch, chốt offset trước khi dừng hoặc khi cần biết kết quả | Commit định kỳ trong vòng tiêu thụ liên tục |
| Rủi ro cần lưu ý | Block lâu, lỗi khi rebalance hoặc timeout | Không được retry commit cũ sau commit mới hơn |

Một mẫu phổ biến là dùng `commitAsync()` sau mỗi batch để không chặn vòng poll, sau đó dùng `commitSync()` khi dừng consumer hoặc trước khi rời group nếu vẫn còn quyền sở hữu partition. `commitSync()` được gọi sau các commit async sẽ chờ các commit async trước đó hoàn tất theo thứ tự API.

## 6. Commit đúng offset sau khi xử lý batch

Với manual commit, chỉ commit những record đã xử lý thành công. Ví dụ dưới đây xử lý đồng bộ từng record và lưu offset kế tiếp cho mỗi partition:

```java
Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

for (ConsumerRecord<String, String> record : records) {
    process(record); // Chỉ trả về khi xử lý nghiệp vụ thành công

    TopicPartition tp = new TopicPartition(
            record.topic(), record.partition());
    offsets.put(tp, new OffsetAndMetadata(record.offset() + 1));
}

if (!offsets.isEmpty()) {
    consumer.commitSync(offsets);
}
```

Nếu xử lý thất bại ở giữa batch và exception thoát khỏi vòng lặp, lệnh commit ở cuối không chạy. Các record đã xử lý trước lỗi có thể được đọc lại sau khi consumer khởi động lại hoặc rebalance; do đó `process()` nên idempotent hoặc có cơ chế deduplication.

### Vì sao cần commit offset kế tiếp đã xử lý?

Giả sử partition 0 có offset 20, 21 và 22. Ứng dụng xử lý thành công 20 và 21 nhưng lỗi ở 22. Giá trị commit an toàn là 22, tức vị trí kế tiếp sau record cuối cùng đã xử lý liên tục. Không commit 23 vì điều đó sẽ bỏ qua record 22.

Nếu xử lý record song song, không được commit offset cao nhất chỉ vì record đó hoàn tất trước. Chỉ commit offset sau **dãy record liên tục đã xử lý thành công** của mỗi partition. Ví dụ offset 22 hoàn tất trước nhưng offset 21 chưa xong thì chưa thể commit 23 một cách an toàn.

## 7. Xử lý lỗi commit thường gặp

Commit có thể thất bại vì group membership thay đổi, timeout, lỗi xác thực hoặc consumer không còn quyền sở hữu partition.

| Exception / hiện tượng | Ý nghĩa thường gặp | Cách xử lý |
|---|---|---|
| `CommitFailedException` | Consumer không còn member hợp lệ hoặc partition đã bị chuyển cho member khác khi commit | Không cố commit offset của partition đã mất; để consumer hoàn tất rebalance và xử lý lại từ offset đã commit trước đó |
| `RebalanceInProgressException` | Group đang trong quá trình rebalance nên commit chưa thể hoàn tất | Tiếp tục `poll()` để hoàn tất rebalance; sau đó chỉ commit partition còn được gán và offset vẫn hợp lệ |
| `TimeoutException` | Không nhận được kết quả commit trong thời hạn | Kiểm tra coordinator/network; kết quả có thể chưa rõ với ứng dụng, không gửi lại offset cũ nếu đã có commit mới hơn |
| `FencedInstanceIdException` | Static member bị fencing bởi instance khác dùng cùng `group.instance.id` | Bảo đảm instance ID duy nhất và xử lý vòng đời member cũ trước khi khởi động member mới |
| `GroupAuthorizationException` | Principal không có quyền thao tác với consumer group | Kiểm tra ACL/quyền `READ` hoặc quyền group phù hợp trên cluster |
| Callback nhận exception trong `commitAsync()` | Yêu cầu commit async không thành công | Ghi log, metric và để commit mới nhất tiếp theo cập nhật tiến độ; tránh retry một offset cũ sau commit mới |

Tên exception và thời điểm phát sinh có thể khác theo phiên bản Kafka client, trạng thái group và loại API commit. Hãy xử lý theo loại lỗi thay vì bắt mọi exception rồi retry vô hạn.

### `CommitFailedException` sau rebalance

Một tình huống phổ biến:

1. Consumer A poll record của partition 0.
2. A xử lý batch quá lâu hoặc không poll trong khoảng thời gian cho phép.
3. Group rebalance và partition 0 được giao cho consumer B.
4. A gọi `commitSync()` với offset của partition 0.
5. Coordinator từ chối commit vì A không còn sở hữu partition.

Consumer A không nên tiếp tục commit offset của partition 0. Nếu các record A xử lý chưa được commit, consumer B có thể đọc lại chúng. Đây là lý do xử lý nghiệp vụ cần idempotent.

## 8. Commit khi rebalance và khi consumer dừng

Consumer có thể nhận callback `onPartitionsRevoked` khi partition sắp được thu hồi. Nếu ứng dụng quản lý offset thủ công, đây là thời điểm phù hợp để commit các offset đã xử lý an toàn cho những partition sắp rời khỏi consumer.

Ví dụ khung listener:

```java
consumer.subscribe(List.of("orders.events"), new ConsumerRebalanceListener() {
    @Override
    public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
        Map<TopicPartition, OffsetAndMetadata> safeOffsets =
                offsetsProcessedFor(partitions);
        if (!safeOffsets.isEmpty()) {
            consumer.commitSync(safeOffsets);
        }
    }

    @Override
    public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
        // Khởi tạo state hoặc chuẩn bị xử lý các partition mới được giao.
    }
});
```

`offsetsProcessedFor(...)` là hàm ứng dụng tự triển khai để trả về offset kế tiếp sau các record đã xử lý liên tục của đúng các partition được thu hồi. Không dùng vị trí poll hiện tại nếu ứng dụng chưa xử lý hết record.

Với các phiên bản client có callback `onPartitionsLost`, partition đã bị mất quyền sở hữu; không nên cố commit ở callback này vì một consumer khác có thể đã tiếp quản. Chỉ commit khi còn hợp lệ và đang ở callback/điểm vòng đời cho phép.

Khi shutdown bình thường, dừng nhận record mới, hoàn tất hoặc dừng an toàn các công việc đang xử lý, commit offset an toàn cuối cùng bằng `commitSync()` nếu partition vẫn còn được gán, rồi gọi `consumer.close()`. Nếu process bị kill đột ngột, không có cơ hội commit cuối; consumer sẽ đọc lại từ offset đã commit trước đó.

## 9. Ví dụ vòng poll với manual commit

Ví dụ sau minh họa luồng tiêu thụ đồng bộ: poll, xử lý record, commit offset kế tiếp theo partition. Phần xử lý nghiệp vụ được giả định là đồng bộ và trả về khi hoàn tất.

```java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;

Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-processor");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders.events"));

    while (running) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(500));

        Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

        for (ConsumerRecord<String, String> record : records) {
            processOrderEvent(record); // Ném lỗi nếu nghiệp vụ chưa hoàn tất

            TopicPartition tp = new TopicPartition(
                    record.topic(), record.partition());
            offsets.put(tp, new OffsetAndMetadata(record.offset() + 1));
        }

        if (!offsets.isEmpty()) {
            consumer.commitSync(offsets);
        }
    }
}
```

Đây là đoạn minh họa phần lõi; `running` và `processOrderEvent` do ứng dụng định nghĩa. Trong service thực tế, cần bổ sung xử lý shutdown, rebalance, exception nghiệp vụ, logging và metric. Không để một tác vụ đồng bộ kéo dài vượt `max.poll.interval.ms`; nếu cần xử lý dài, giảm `max.poll.records`, chia nhỏ công việc hoặc thiết kế worker/partition assignment có kiểm soát.

## 10. Ví dụ commit async theo batch

Trong vòng poll liên tục, ứng dụng có thể commit async sau khi đã xử lý xong batch:

```java
if (!offsets.isEmpty()) {
    consumer.commitAsync(offsets, (committed, exception) -> {
        if (exception != null) {
            log.warn("Async commit failed for {}", committed, exception);
            metrics.increment("kafka.consumer.commit.failure");
        }
    });
}
```

Callback cần nhẹ và không gọi các API `KafkaConsumer` từ thread khác. KafkaConsumer không thread-safe; các thao tác poll, commit, pause/resume và subscribe nên được điều phối trên thread sở hữu consumer.

Khi shutdown bình thường, sau khi đã dừng poll và hoàn tất xử lý các record an toàn, có thể gọi `commitSync(latestSafeOffsets)` rồi đóng consumer. Lệnh sync cuối cùng giúp chốt offset mới nhất và đợi các async commit trước đó hoàn tất. Không lấy một offset cũ trong callback lỗi rồi retry sau khi offset mới hơn đã commit thành công.

## 11. At-least-once, at-most-once và duplicate

Thời điểm commit so với thời điểm xử lý quyết định khả năng mất hoặc lặp record:

| Thứ tự thao tác | Hậu quả khi process dừng giữa hai bước | Semantics thường đạt được |
|---|---|---|
| Xử lý xong rồi commit | Nếu dừng sau xử lý nhưng trước commit, record có thể được đọc lại | At-least-once; có thể duplicate |
| Commit rồi mới xử lý | Nếu dừng sau commit nhưng trước xử lý, record bị bỏ qua khi chạy lại | At-most-once; có thể mất xử lý |
| Xử lý và commit trong cùng transaction Kafka phù hợp | Output Kafka và offset có thể được commit nguyên tử | Exactly-once processing trong phạm vi Kafka transaction |

Với phần lớn ứng dụng tích hợp database/API bên ngoài, pattern phổ biến là xử lý rồi commit, chấp nhận khả năng duplicate và làm thao tác nghiệp vụ idempotent. Ví dụ dùng `eventId` làm unique key trong database, upsert theo version hoặc lưu bảng inbox để phát hiện event đã xử lý.

`commitSync()` và `commitAsync()` chỉ khác nhau ở cách gửi/đợi xác nhận offset. Bản thân hai API này không cung cấp exactly-once cho side effect ở database.

## 12. Khi nào cần Kafka transaction?

Nếu consumer đọc từ Kafka, xử lý rồi ghi kết quả sang topic Kafka khác và muốn output cùng offset đầu vào được commit nguyên tử, có thể dùng Kafka transaction với producer transactional:

1. Consumer đọc record và lấy offset kế tiếp đã xử lý.
2. Producer bắt đầu transaction.
3. Producer gửi output record.
4. Producer gọi `sendOffsetsToTransaction(offsets, consumer.groupMetadata())`.
5. Producer commit transaction.

Nếu transaction commit, output và offset được ghi nhận cùng nhau; nếu abort, cả hai không được xem là đã commit. Consumer downstream cần cấu hình `isolation.level=read_committed` để chỉ đọc dữ liệu transactional đã commit.

Trong mô hình này, không gọi `consumer.commitSync()` hoặc `commitAsync()` cho cùng offset đầu vào như một bước độc lập bên ngoài transaction, vì sẽ phá vỡ tính nguyên tử mong muốn. Kafka transaction cũng không tự bao gồm thao tác ghi vào database ngoài Kafka; cần outbox, inbox hoặc distributed transaction phù hợp cho hệ thống đó.

## 13. Spring Kafka: acknowledgment và commit

Khi dùng Spring Kafka listener container, container thường quản lý poll và commit offset dựa trên `AckMode`. Ứng dụng không nhất thiết gọi trực tiếp `KafkaConsumer.commitSync()` trong listener.

Các mode thường gặp:

| AckMode | Thời điểm commit |
|---|---|
| `RECORD` | Sau khi listener xử lý thành công từng record |
| `BATCH` | Sau khi tất cả record trong poll batch được xử lý thành công |
| `MANUAL` | Listener gọi `Acknowledgment.acknowledge()`; container hoàn tất commit theo semantics của mode |
| `MANUAL_IMMEDIATE` | Commit được yêu cầu ngay khi acknowledge trên consumer thread; hành vi còn phụ thuộc thread gọi và cấu hình container |

Ví dụ manual acknowledgment:

```java
@KafkaListener(topics = "orders.events", groupId = "order-processor")
public void listen(ConsumerRecord<String, String> record,
                   Acknowledgment acknowledgment) {
    processOrderEvent(record);
    acknowledgment.acknowledge();
}
```

Chỉ acknowledge sau khi xử lý thành công. Nếu listener chạy bất đồng bộ hoặc hand off công việc sang thread khác, phải cấu hình ack mode và quản lý thời điểm acknowledge theo vòng đời công việc thực tế; không acknowledge ngay sau khi chỉ đưa task vào executor nếu nghiệp vụ chưa hoàn tất.

## 14. Checklist xử lý commit trong production

- Tắt `enable.auto.commit` nếu ứng dụng cần kiểm soát commit sau xử lý.
- Commit offset kế tiếp sau record cuối cùng đã xử lý liên tục ở mỗi partition.
- Không commit offset vượt qua record đang xử lý dở hoặc thất bại.
- Dùng `commitSync()` khi cần biết kết quả trước khi tiếp tục hoặc chốt offset cuối.
- Dùng `commitAsync()` trong vòng tiêu thụ liên tục khi muốn giảm thời gian chờ; xử lý callback và không retry offset cũ sau commit mới.
- Xử lý `CommitFailedException`, rebalance, timeout và authorization theo nguyên nhân.
- Giữ poll loop hoạt động trong giới hạn `max.poll.interval.ms`.
- Commit an toàn cho partition sắp revoke nếu còn quyền sở hữu; không commit partition đã lost.
- Làm side effect idempotent vì xử lý xong nhưng commit thất bại có thể dẫn tới replay.
- Dùng Kafka transaction khi cần commit nguyên tử output topic và input offsets.
- Với Spring Kafka, chọn `AckMode` và error handler phù hợp thay vì trộn lẫn cơ chế commit thủ công không kiểm soát.

## 15. Ghi nhớ

Offset commit là vị trí kế tiếp consumer group sẽ đọc. `commitSync()` chờ kết quả và phù hợp khi cần xác nhận tiến độ đã lưu; `commitAsync()` trả về ngay và phù hợp cho commit định kỳ, nhưng lỗi callback cần được ghi nhận và không nên retry offset cũ sau commit mới hơn.

Để tránh mất dữ liệu, xử lý record thành công rồi mới commit offset kế tiếp. Cách này có thể tạo duplicate nếu process dừng trước commit, vì vậy consumer cần idempotent. Khi rebalance, chỉ commit partition còn thuộc quyền sở hữu; khi cần output Kafka và input offset nguyên tử, dùng Kafka transaction. Lựa chọn commit đúng giúp consumer phục hồi an toàn và duy trì tiến độ xử lý nhất quán.
