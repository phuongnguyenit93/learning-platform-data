# `enable.auto.commit` và những tình huống có thể mất hoặc lặp xử lý

## Mục tiêu

Kafka consumer có hai vị trí cần phân biệt: vị trí đọc hiện tại trong bộ nhớ và offset đã commit vào Kafka. Vị trí đọc tiến lên khi `poll()` trả record; committed offset là điểm consumer sẽ tiếp tục đọc sau restart hoặc rebalance. `enable.auto.commit` cho Kafka client tự lưu vị trí theo chu kỳ, nhưng broker không biết ứng dụng đã hoàn tất xử lý nghiệp vụ hay chưa.

Nếu commit tiến quá xa so với công việc đã hoàn thành, ứng dụng có thể bỏ mất record khi restart. Nếu xử lý xong nhưng chưa commit, ứng dụng có thể xử lý lại record sau sự cố. Bài học này giúp bạn hiểu chính xác hai cửa sổ lỗi đó và chọn cách commit phù hợp.

Sau bài học, bạn có thể:

- Phân biệt consumer position, committed offset và offset tiếp theo cần đọc.
- Giải thích `enable.auto.commit` và `auto.commit.interval.ms`.
- Nhận diện tình huống mất xử lý và xử lý lặp do crash, poll tiếp theo hoặc rebalance.
- Dùng `commitSync()`, `commitAsync()` và commit offset theo partition đúng thời điểm.
- Chọn at-most-once, at-least-once hoặc cơ chế exactly-once phù hợp với nơi lưu kết quả.
- Thiết kế poll loop, rebalance handling và Spring Kafka acknowledgement an toàn.

## 1. Consumer position và committed offset

Kafka consumer duy trì hai khái niệm vị trí:

| Khái niệm | Ý nghĩa | Khi process restart |
|---|---|---|
| Consumer position | Offset của record tiếp theo mà consumer sẽ trả cho ứng dụng; tự tiến lên khi `poll()` trả record | Không được khôi phục chỉ từ bộ nhớ cũ |
| Committed offset | Offset tiếp theo đã được lưu bền vững cho consumer group trong Kafka | Consumer dùng làm điểm bắt đầu khi khởi động hoặc nhận partition sau rebalance |

Ví dụ, consumer đã đọc record offset `40`. Position của nó có thể là `41`, nghĩa là lần đọc tiếp theo bắt đầu từ offset 41. Nếu committed offset vẫn là `40`, consumer mới sẽ đọc lại record ở offset 40. Nếu committed offset là `41`, consumer mới tiếp tục từ record kế tiếp.

Kafka lưu offset tiếp theo cần đọc, không lưu “offset cuối cùng đã xử lý”. Vì vậy, nếu ứng dụng xử lý record offset `40` thành công, offset cần commit là `41`.

Offset không nhất thiết liên tục. Topic compacted, transaction aborted hoặc các thao tác log có thể tạo khoảng trống. Khi dùng API commit tường minh, ưu tiên `ConsumerRecords.nextOffsets()` hoặc tính đúng vị trí tiếp theo theo partition; không giả định mọi offset đều có record.

## 2. `enable.auto.commit` hoạt động thế nào?

`enable.auto.commit=true` cho phép Kafka consumer tự commit offset định kỳ. Trong Kafka 4.1:

- `enable.auto.commit` mặc định là `true`.
- `auto.commit.interval.ms` mặc định là `5000` ms (5 giây).

Consumer tự quản lý committed position theo chu kỳ. Ứng dụng không phải gọi `commitSync()` hoặc `commitAsync()` để lưu offset trong trường hợp này.

Ví dụ cấu hình mặc định được viết rõ:

```properties
enable.auto.commit=true
auto.commit.interval.ms=5000
```

Điều quan trọng: Kafka chỉ biết record đã được trả về cho ứng dụng và position của consumer đã tiến lên. Kafka không biết ứng dụng đã ghi database, gọi REST API, gửi email hoặc hoàn tất một side effect bên ngoài hay chưa.

Tài liệu Kafka nêu rằng auto commit có thể cung cấp at-least-once nếu ứng dụng xử lý hết dữ liệu được trả về trong mỗi lần `poll()` trước khi gọi `poll()` tiếp theo hoặc đóng consumer. Nếu ứng dụng chuyển record sang xử lý bất đồng bộ rồi tiếp tục poll/close trong khi công việc cũ chưa xong, committed offset có thể đi trước kết quả xử lý và dẫn tới mất record.

### 2.1. Poll loop an toàn với auto commit

Auto commit có thể phù hợp với consumer đơn giản, xử lý đồng bộ, không chuyển record sang queue/thread khác và luôn xử lý hết batch trước poll tiếp theo:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-audit");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, true);
props.put(ConsumerConfig.AUTO_COMMIT_INTERVAL_MS_CONFIG, 5_000);
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("commerce.orders.events.v1"));

    while (running) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(500));

        // Xử lý đồng bộ toàn bộ batch trước lần poll tiếp theo.
        for (ConsumerRecord<String, String> record : records) {
            processSynchronously(record);
        }
    }
}
```

Ví dụ này chỉ phù hợp khi `processSynchronously()` hoàn tất side effect trước khi vòng lặp gọi `poll()` lần tiếp theo. Nếu hàm chỉ enqueue công việc sang executor rồi trả về ngay, điều kiện an toàn không còn đúng.

## 3. Mất xử lý: committed offset đi trước công việc

Mất xử lý xảy ra khi offset được commit trước khi ứng dụng hoàn tất side effect. Consumer restart từ offset mới và không nhận lại record chưa xử lý xong.

Ví dụ batch có các record offset `100`, `101`, `102`:

```text
poll() trả về 100, 101, 102
        |
        v
Consumer position tiến đến 103
        |
        v
Ứng dụng enqueue batch và gọi poll() tiếp theo
        |
        v
Auto commit lưu offset 103
        |
        v
Ứng dụng mới xử lý xong 100
        |
        X  Process crash trước khi xử lý 101 và 102
        |
        v
Consumer mới bắt đầu từ 103
        |
        v
101 và 102 không được xử lý lại
```

Các tình huống thường gặp:

- Consumer poll một batch rồi đẩy từng record vào executor, nhưng tiếp tục poll batch tiếp theo.
- Consumer chỉ xử lý một phần batch rồi gặp lỗi và thoát.
- Shutdown hook đóng consumer trong khi các tác vụ xử lý nền vẫn còn chạy.
- Ứng dụng đánh dấu record hoàn tất trước khi database transaction thực sự commit.
- Consumer xử lý nhiều partition song song nhưng commit position cao nhất trong khi một record trước đó của cùng partition chưa hoàn tất.

Đây là rủi ro chính khi bật auto commit trong pipeline xử lý bất đồng bộ. Tăng `auto.commit.interval.ms` có thể thay đổi tần suất commit, nhưng không giải quyết được việc commit vượt qua công việc chưa hoàn tất.

## 4. Xử lý lặp: side effect hoàn tất nhưng offset chưa commit

Trường hợp ngược lại là ứng dụng đã xử lý record thành công nhưng process crash trước khi offset được commit. Consumer mới sẽ đọc lại từ committed offset cũ và có thể thực hiện side effect lần thứ hai.

Ví dụ:

```text
poll() trả về record offset 200
        |
        v
Ứng dụng ghi đơn hàng vào database thành công
        |
        X  Process crash trước khi commit offset 201
        |
        v
Consumer mới đọc lại offset 200
        |
        v
Side effect ghi đơn hàng có thể bị thực hiện lần hai
```

Đây là hành vi thường gặp của at-least-once. Nó không có nghĩa Kafka gửi sai record; consumer chủ động đọc lại vì lần xử lý trước chưa được xác nhận bằng committed offset.

Giải pháp phổ biến là làm cho side effect idempotent:

- Gắn `eventId` duy nhất cho mỗi event.
- Database có unique constraint trên `eventId` hoặc bảng inbox/deduplication.
- Cập nhật trạng thái bằng câu lệnh idempotent hoặc kiểm tra version trước khi ghi.
- Với API ngoài, truyền idempotency key nếu dịch vụ đích hỗ trợ.

Không thể loại bỏ cửa sổ “side effect đã thành công nhưng commit chưa thành công” chỉ bằng cách tăng commit interval hoặc retry commit.

## 5. Ba delivery semantics thường gặp

| Cách làm | Thời điểm commit | Nếu crash giữa commit và xử lý | Nếu crash sau xử lý nhưng trước commit |
|---|---|---|---|
| At-most-once | Trước xử lý | Có thể mất record | Không áp dụng vì đã commit trước |
| At-least-once | Sau xử lý thành công | Record chưa xử lý vẫn được đọc lại | Record đã xử lý có thể bị xử lý lặp |
| Exactly-once | Kết quả và tiến độ được lưu nguyên tử trong cùng transaction phù hợp | Không để kết quả và offset lệch nhau trong phạm vi transaction | Không để kết quả và offset lệch nhau trong phạm vi transaction |

### 5.1. At-most-once: commit trước xử lý

At-most-once ưu tiên không xử lý trùng. Consumer commit offset trước khi thực hiện side effect:

```java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(500));

// Commit position trước khi chạy business logic.
consumer.commitSync(records.nextOffsets());

for (ConsumerRecord<String, String> record : records) {
    process(record);
}
```

Nếu process crash sau commit nhưng trước khi xử lý một record, record đó sẽ bị bỏ qua khi consumer khởi động lại. Chỉ chọn cách này khi bỏ sót dữ liệu có thể chấp nhận được, ví dụ một số luồng telemetry không quan trọng.

### 5.2. At-least-once: xử lý xong mới commit

Đây là lựa chọn phổ biến cho xử lý nghiệp vụ. Tắt auto commit, xử lý toàn bộ record của batch rồi mới commit:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-processor");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("commerce.orders.events.v1"));

    while (running) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(500));

        try {
            for (ConsumerRecord<String, String> record : records) {
                processIdempotently(record);
            }

            // Commit offset tiếp theo sau khi toàn bộ batch đã xử lý thành công.
            consumer.commitSync(records.nextOffsets());
        } catch (Exception processingError) {
            // Không commit batch lỗi; khi restart, record chưa được xác nhận sẽ được đọc lại.
            throw processingError;
        }
    }
}
```

`records.nextOffsets()` trả về offset tiếp theo theo từng partition và có thể mang leader epoch metadata. Cách này phù hợp hơn việc tự lấy offset lớn nhất rồi cộng 1, nhất là khi log có offset không liên tục.

Nếu `processIdempotently()` đã ghi database thành công nhưng `commitSync()` lỗi hoặc process crash ngay sau đó, batch có thể được đọc lại. Vì vậy, side effect nên có dedup/idempotency.

### 5.3. Exactly-once

Exactly-once phụ thuộc nơi lưu kết quả:

- **Kafka consume → Kafka produce:** dùng Kafka transaction, producer transactional ID và `sendOffsetsToTransaction()` để ghi output record và consumer offsets trong cùng transaction. Consumer downstream dùng `isolation.level=read_committed` để chỉ đọc transaction đã commit.
- **Kafka consume → database:** ghi business result và offset trong cùng transaction của database nếu có thể. Khi đó dữ liệu và tiến độ được commit/rollback nguyên tử trong một hệ quản trị.
- **Kafka consume → API hoặc hệ thống ngoài:** thường cần idempotency key, inbox/outbox hoặc cơ chế dedup ở hệ thống đích. Commit Kafka offset riêng lẻ không thể tạo transaction nguyên tử với một API HTTP bất kỳ.

`enable.auto.commit=false` là điều kiện cần cho nhiều mô hình kiểm soát offset, nhưng tự nó không tạo exactly-once.

## 6. `commitSync()` và `commitAsync()`

Khi tắt auto commit, consumer có thể lưu offset thủ công qua hai API chính:

| API | Đặc điểm | Dùng khi |
|---|---|---|
| `commitSync()` | Chờ broker xác nhận commit hoặc ném lỗi/timeout; dễ xác định commit đã hoàn tất trước bước tiếp theo | Cần ranh giới xác nhận rõ, ví dụ sau mỗi batch hoặc khi revoke partition |
| `commitAsync()` | Gửi commit bất đồng bộ; kết quả lỗi được chuyển qua callback nếu có | Muốn giảm thời gian block ở đường xử lý bình thường và chấp nhận theo dõi lỗi qua callback |

### 6.1. `commitSync()`

Không truyền tham số, `commitSync()` commit offsets được trả về từ lần `poll()` gần nhất cho các partition tương ứng. Có thể truyền map tường minh:

```java
consumer.commitSync(records.nextOffsets());
```

Lệnh sẽ block cho đến khi commit thành công, gặp lỗi không thể phục hồi hoặc timeout. Nếu commit thất bại, không nên giả định offset đã được lưu. Với at-least-once, giữ nguyên kết quả nghiệp vụ đã xử lý và chấp nhận khả năng record được đọc lại; đảm bảo handler idempotent.

### 6.2. `commitAsync()`

Ví dụ commit bất đồng bộ sau khi xử lý xong batch:

```java
consumer.commitAsync(records.nextOffsets(), (offsets, exception) -> {
    if (exception != null) {
        logger.warn("Offset commit failed: {}", offsets, exception);
        // Ghi metric/log; không retry mù một offset cũ sau các commit mới hơn.
        return;
    }

    logger.debug("Offsets committed: {}", offsets);
});
```

Các lần `commitAsync()` được gửi theo thứ tự gọi và callback cũng được gọi theo thứ tự tương ứng. Một lệnh `commitSync()` tiếp theo sẽ chờ các commit async trước đó hoàn tất trước khi trả về; bảo đảm callback đã được gọi trước khi `commitSync()` hoàn tất được Kafka nêu rõ khi consumer dùng consumer group protocol. Tuy nhiên, nếu ứng dụng tự retry một offset cũ sau khi một offset mới hơn đã commit, nó có thể ghi lùi tiến độ. Vì vậy, không nên retry mù trong callback; hãy xử lý lỗi dựa trên trạng thái hiện tại và dùng `commitSync()` ở ranh giới cần xác nhận cuối cùng.

### 6.3. Commit theo từng partition

Một `poll()` có thể trả record của nhiều partition. Nếu xử lý theo partition, ứng dụng có thể commit offset hoàn tất riêng cho từng partition:

```java
for (TopicPartition partition : records.partitions()) {
    List<ConsumerRecord<String, String>> partitionRecords =
            records.records(partition);

    for (ConsumerRecord<String, String> record : partitionRecords) {
        processIdempotently(record);
    }

    OffsetAndMetadata nextOffset = records.nextOffsets().get(partition);
    consumer.commitSync(Map.of(partition, nextOffset));
}
```

Đoạn code này chỉ đúng khi xử lý record trong mỗi partition theo thứ tự và hoàn tất toàn bộ record của partition trước commit. Nếu xử lý song song trong cùng partition, chỉ commit đến offset liên tục cao nhất đã hoàn tất; không commit vượt qua một record còn đang xử lý.

## 7. Rebalance và commit offset

Consumer group rebalance khi consumer tham gia/rời nhóm, mất heartbeat, không gọi `poll()` đúng hạn hoặc partition subscription thay đổi. Khi partition bị thu hồi, consumer nên commit tiến độ đã xử lý xong trước khi nhường partition.

`ConsumerRebalanceListener` cung cấp callback:

- `onPartitionsRevoked()`: partition sắp được thu hồi; commit offset an toàn của phần việc đã hoàn tất và giải phóng state liên quan.
- `onPartitionsAssigned()`: partition mới được giao; khởi tạo state hoặc khôi phục offset cần thiết.
- `onPartitionsLost()` (ở client hỗ trợ): partition đã bị mất quyền sở hữu; không giả định còn có thể commit thành công.

Ví dụ minh họa với xử lý đồng bộ và commit offset của các partition bị revoke:

```java
Map<TopicPartition, OffsetAndMetadata> completedOffsets = new HashMap<>();

consumer.subscribe(List.of("commerce.orders.events.v1"),
        new ConsumerRebalanceListener() {
            @Override
            public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
                Map<TopicPartition, OffsetAndMetadata> offsetsToCommit =
                        new HashMap<>();

                for (TopicPartition partition : partitions) {
                    OffsetAndMetadata offset = completedOffsets.get(partition);
                    if (offset != null) {
                        offsetsToCommit.put(partition, offset);
                    }
                }

                if (!offsetsToCommit.isEmpty()) {
                    consumer.commitSync(offsetsToCommit);
                }
            }

            @Override
            public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
                // Khôi phục state theo partition nếu ứng dụng có state cục bộ.
            }

            @Override
            public void onPartitionsLost(Collection<TopicPartition> partitions) {
                // Quyền sở hữu đã mất: dừng công việc còn dang dở và không commit mù.
            }
        });
```

Trong poll loop, sau khi xử lý thành công toàn bộ record của batch, cập nhật `completedOffsets` bằng `records.nextOffsets()` cho các partition tương ứng. Không cập nhật map trước khi side effect hoàn tất. Đây là skeleton minh họa; ứng dụng thực tế cần đồng bộ map với logic xử lý và chỉ giữ offset liên tục đã hoàn tất.

Nếu commit trong `onPartitionsRevoked()` thất bại, partition mới có thể đọc lại một phần record đã xử lý. Đây là duplicate theo at-least-once; idempotency giúp tránh lặp side effect.

## 8. `max.poll.interval.ms` và xử lý lâu

Consumer cần tiếp tục gọi `poll()` để duy trì tiến độ và tham gia group coordination. Trong Kafka 4.1, một số mặc định quan trọng:

| Cấu hình | Mặc định | Ý nghĩa |
|---|---:|---|
| `max.poll.interval.ms` | 300.000 ms (5 phút) | Khoảng tối đa giữa hai lần gọi `poll()` trước khi consumer bị xem là không tiến triển và group có thể rebalance |
| `max.poll.records` | 500 | Số record tối đa trả về trong một lần `poll()` |
| `enable.auto.commit` | `true` | Bật commit offset tự động |
| `auto.commit.interval.ms` | 5.000 ms | Chu kỳ auto commit khi auto commit bật |

Nếu xử lý một batch lâu hơn `max.poll.interval.ms`, consumer có thể bị loại khỏi group và partition được giao cho thành viên khác. `commitSync()` sau đó có thể thất bại vì consumer không còn sở hữu partition.

Các cách xử lý:

- Giảm `max.poll.records` để giới hạn số record cần xử lý trong một poll.
- Tăng `max.poll.interval.ms` nếu thời gian xử lý dài nhưng có giới hạn dự đoán được.
- Nếu xử lý bất đồng bộ, tắt auto commit, theo dõi offset hoàn tất, pause partition khi đã có đủ công việc đang chạy và chỉ commit offset liên tục đã xử lý xong.
- Giữ mọi lời gọi API `KafkaConsumer` trên một thread sở hữu consumer; `KafkaConsumer` không thread-safe.

Không giải quyết poll timeout bằng cách tăng `max.poll.interval.ms` vô hạn. Điều đó có thể làm group chậm phát hiện consumer không còn hoạt động.

## 9. Xử lý bất đồng bộ mà không commit vượt tiến độ

Nếu consumer gửi record sang worker pool, cần theo dõi tiến độ theo từng partition. Giả sử partition 0 nhận offset 10, 11, 12; worker xử lý xong 10 và 12 nhưng 11 còn chạy. Offset an toàn để commit vẫn chỉ là 11 (offset tiếp theo sau record 10), không phải 13.

```text
Partition 0:  offset 10      offset 11      offset 12
              completed     processing    completed

Commit an toàn: 11
Không được commit: 13
```

Thiết kế thường cần:

1. Consumer thread poll record và chuyển công việc sang worker pool.
2. Theo dõi số lượng task đang chạy theo partition.
3. Chỉ đánh dấu offset hoàn tất sau khi side effect đã commit thành công.
4. Duy trì watermark là offset tiếp theo sau record liên tục cao nhất đã hoàn tất.
5. Dùng `consumer.pause(partitions)` khi worker pool đầy hoặc partition có quá nhiều record đang xử lý.
6. Tiếp tục gọi `poll()` định kỳ để giữ group membership; dùng `resume()` khi worker pool có chỗ.
7. Commit watermark từ consumer thread; không gọi trực tiếp `KafkaConsumer.commit*()` đồng thời từ worker threads.
8. Khi rebalance, dừng nhận việc mới cho partition bị revoke, chờ/huỷ công việc theo policy và commit phần liên tục đã hoàn tất.

Nếu không thể bảo đảm thứ tự hoàn tất trong một partition, cân nhắc xử lý tuần tự theo partition hoặc dùng hàng đợi riêng cho từng partition. Không commit offset của một record hoàn tất ở phía sau khi record trước đó vẫn đang chạy.

## 10. `auto.offset.reset` không phải auto commit

Hai cấu hình có mục đích khác nhau:

| Cấu hình | Chức năng |
|---|---|
| `enable.auto.commit` | Quyết định consumer tự lưu committed offset định kỳ hay ứng dụng tự commit |
| `auto.offset.reset` | Quyết định bắt đầu từ đâu khi group chưa có committed offset hoặc offset hiện tại không còn tồn tại trên broker |

Các lựa chọn phổ biến của `auto.offset.reset`:

- `earliest`: bắt đầu từ offset sớm nhất còn được giữ.
- `latest`: bắt đầu từ cuối log hiện tại.
- `none`: ném lỗi nếu không tìm thấy committed offset hợp lệ.
- `by_duration:...`: chọn vị trí theo khoảng thời gian trong các phiên bản hỗ trợ.

Đổi `auto.offset.reset` không sửa được việc auto commit đã đi trước side effect. Nó chỉ áp dụng khi không có offset phù hợp để khôi phục. Chọn `latest` có thể bỏ qua dữ liệu cũ khi group mới bắt đầu hoặc partition mới được thêm; chọn `earliest` có thể khiến ứng dụng đọc lại lượng dữ liệu lớn.

## 11. Spring Kafka và acknowledgement mode

Khi dùng Spring Kafka listener container, container quản lý poll loop và offset commit theo `AckMode`. Thông thường nên để container quản lý commit và tắt auto commit của Kafka client:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
```

Một số acknowledgement mode thường dùng:

| AckMode | Thời điểm container commit |
|---|---|
| `RECORD` | Sau khi listener xử lý xong từng record |
| `BATCH` | Sau khi listener xử lý xong toàn bộ record của poll batch |
| `MANUAL` | Ứng dụng gọi acknowledge; container thực hiện commit theo ranh giới batch |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge trên consumer thread; nếu gọi từ thread khác, hành vi được phối hợp theo container |

Tên và chi tiết cấu hình phụ thuộc phiên bản Spring Kafka. Không trộn lẫn việc container quản lý acknowledgement với việc tự gọi `consumer.commitSync()` trong listener nếu chưa cấu hình đúng chế độ thủ công. Với xử lý bất đồng bộ, cần dùng cơ chế acknowledgement hỗ trợ async của phiên bản Spring Kafka đang dùng và bảo đảm container không commit trước khi tác vụ hoàn tất.

## 12. Chọn chiến lược theo loại công việc

| Use case | Gợi ý |
|---|---|
| Log/metrics không quan trọng, chấp nhận bỏ một ít record | Có thể dùng auto commit nếu xử lý đồng bộ hết mỗi poll batch |
| Cập nhật database hoặc trạng thái đơn hàng | Tắt auto commit, xử lý xong mới `commitSync`/acknowledge; side effect idempotent |
| Gửi email hoặc gọi API ngoài | Tắt auto commit, dùng idempotency key ở hệ thống đích; xử lý retry có kiểm soát |
| Consume rồi produce sang Kafka | Dùng transaction và `sendOffsetsToTransaction()` nếu cần exactly-once trong Kafka |
| Xử lý song song nhiều record | Tắt auto commit, quản lý watermark liên tục theo partition và commit từ consumer thread |
| Xử lý mỗi record mất nhiều phút | Giới hạn batch, điều chỉnh poll interval hoặc pause/resume và tách worker có quản lý offset |

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Record đã được poll nhưng không thấy xử lý sau restart | Auto commit đã lưu position trước khi worker hoàn tất | Tắt auto commit; commit offset sau side effect hoặc sau khi worker hoàn tất |
| Database có bản ghi trùng | Side effect thành công nhưng offset chưa commit | Dùng event ID, unique constraint hoặc inbox/dedup |
| `CommitFailedException` | Consumer không còn là thành viên hợp lệ hoặc partition đã bị revoke | Kiểm tra poll interval, rebalance và quyền sở hữu partition; chấp nhận replay theo at-least-once |
| Commit offset nhảy qua record đang xử lý | Commit position poll thay vì offset liên tục đã hoàn tất | Theo dõi completion watermark theo partition |
| Consumer liên tục rebalance | Xử lý lâu, poll không đúng hạn hoặc heartbeat/network lỗi | Giảm `max.poll.records`, điều chỉnh `max.poll.interval.ms`, kiểm tra processing và network |
| `auto.offset.reset=latest` làm thiếu dữ liệu ban đầu | Group chưa có offset và consumer bắt đầu ở cuối log | Chọn `earliest` hoặc cấp offset rõ ràng theo yêu cầu nghiệp vụ |
| `commitAsync` báo lỗi nhưng ứng dụng bỏ qua | Không có callback hoặc không ghi nhận lỗi | Gắn callback, metric và commitSync ở ranh giới cần xác nhận |

## 14. Bài thực hành và tự kiểm tra

### Thực hành A — Quan sát mất xử lý với auto commit

1. Tạo topic `consumer-commit-lab` và gửi ít nhất 20 record có ID tăng dần.
2. Tạo consumer group `commit-lab-auto`, bật `enable.auto.commit=true` và đặt `auto.commit.interval.ms=1000`.
3. Poll một batch, đưa record vào executor xử lý chậm, rồi tiếp tục poll batch tiếp theo.
4. Dừng process khi một số record vẫn đang xử lý.
5. Khởi động consumer cùng group và quan sát committed offset.
6. So sánh các record đã poll, đã xử lý thành công và các record không được xử lý lại.

### Thực hành B — Quan sát duplicate với manual commit

1. Tạo consumer group mới và đặt `enable.auto.commit=false`.
2. Poll một batch và xử lý từng record vào database.
3. Dừng process sau khi database ghi thành công nhưng trước `commitSync()`.
4. Khởi động lại consumer và quan sát record được đọc lại.
5. Thêm unique constraint theo `eventId` hoặc bảng inbox để biến lần xử lý lại thành no-op an toàn.

Chỉ thực hiện thử nghiệm dừng process trên cluster lab và database dùng riêng cho bài học.

### Câu hỏi tự kiểm tra

1. Consumer position khác committed offset ở điểm nào?
2. Vì sao commit offset cần lưu offset tiếp theo thay vì offset của record vừa xử lý?
3. `enable.auto.commit` và `auto.commit.interval.ms` có giá trị mặc định nào trong Kafka 4.1?
4. Điều kiện nào giúp auto commit hoạt động theo at-least-once trong poll loop đồng bộ?
5. Vì sao xử lý bất đồng bộ rồi poll tiếp có thể làm mất record?
6. Vì sao manual commit sau side effect vẫn có thể tạo duplicate?
7. Khi nào chọn at-most-once và rủi ro là gì?
8. `commitSync()` và `commitAsync()` khác nhau ra sao?
9. Vì sao không được commit offset 13 nếu offset 11 vẫn đang xử lý?
10. `max.poll.interval.ms` ảnh hưởng thế nào đến rebalance và commit?
11. `auto.offset.reset` khác `enable.auto.commit` ở mục đích nào?
12. Cần làm gì để có exactly-once khi kết quả nằm trong database hoặc một topic Kafka khác?

## Kết luận

`enable.auto.commit` lưu consumer position định kỳ, nhưng không theo dõi việc xử lý nghiệp vụ đã hoàn tất. Nếu ứng dụng poll tiếp hoặc đóng consumer khi công việc của batch trước còn dang dở, offset có thể đi trước và làm mất xử lý. Nếu side effect đã thành công nhưng commit chưa hoàn tất, record có thể được đọc lại. Với nghiệp vụ quan trọng, thường tắt auto commit, commit sau xử lý, thiết kế side effect idempotent và quản lý offset theo từng partition. Exactly-once cần một transaction nguyên tử bao trùm cả kết quả lẫn tiến độ trong phạm vi hệ thống hỗ trợ.

## Tài liệu tham khảo

- [Apache Kafka 4.1 — KafkaConsumer API: offsets, automatic commit and manual commit](https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
- [Apache Kafka 4.1 — Consumer configuration](https://kafka.apache.org/41/configuration/consumer-configs/)
- [Apache Kafka 4.1 — Design: Message delivery semantics](https://kafka.apache.org/41/design/design/#message-delivery-semantics)
- [Spring for Apache Kafka — Message Listener Container and AckMode](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
