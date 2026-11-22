# Commit offset theo từng partition và quy tắc offset kế tiếp

Kafka consumer đọc dữ liệu theo từng partition. Mỗi partition có một dãy offset riêng, vì vậy tiến độ xử lý của consumer group cũng được lưu riêng cho từng cặp topic-partition. Khi commit, ứng dụng phải ghi đúng **offset tiếp theo cần đọc**, sau khi những record đứng trước vị trí đó đã được xử lý thành công.

Hiểu đúng quy tắc này giúp tránh hai lỗi quan trọng: commit quá sớm làm mất record khi consumer restart, hoặc commit quá muộn khiến record đã xử lý bị đọc lại nhiều lần. Bài học này trình bày cách commit theo từng partition, cách dùng **ConsumerRecords.nextOffsets()**, lựa chọn **commitSync()**/**commitAsync()**, xử lý rebalance và cấu hình Spring Kafka.

## 1. Offset và vị trí đọc của consumer

Offset là vị trí của một record trong một partition. Nó không phải số thứ tự toàn cục của topic và cũng không có ý nghĩa so sánh trực tiếp giữa hai partition khác nhau.

Ví dụ topic **orders** có ba partition:

| Partition | Các offset trong partition | Consumer đang đọc |
|---|---|---|
| orders-0 | 0, 1, 2, 3, ... | Vị trí độc lập |
| orders-1 | 0, 1, 2, 3, ... | Vị trí độc lập |
| orders-2 | 0, 1, 2, 3, ... | Vị trí độc lập |

Một consumer group có thể đang đọc **orders-0** đến offset 120, **orders-1** đến offset 87 và **orders-2** đến offset 305. Ba giá trị này không cần bằng nhau vì mỗi partition có tốc độ ghi và xử lý riêng.

Kafka có hai khái niệm vị trí quan trọng:

- **Consumer position:** vị trí tiếp theo mà **poll()** sẽ trả về. Position tự tiến lên khi consumer nhận record từ **poll()**.
- **Committed position:** vị trí đã được lưu bền vững cho consumer group. Khi consumer lỗi hoặc khởi động lại, nó dùng vị trí này để tiếp tục.

Position có thể đã tiến lên trong bộ nhớ trong khi ứng dụng vẫn đang xử lý record. Vì vậy, nhận record từ **poll()** không đồng nghĩa record đã được xử lý thành công hoặc đã được commit.

## 2. Commit offset là commit vị trí tiếp theo cần đọc

Đây là quy tắc quan trọng nhất:

> Offset được commit phải là offset của record tiếp theo mà ứng dụng cần đọc.

Giả sử một partition có các record liên tiếp:

| Record | Offset | Trạng thái xử lý |
|---|---:|---|
| A | 10 | Thành công |
| B | 11 | Thành công |
| C | 12 | Thành công |

Sau khi xử lý cả ba record, consumer commit **13**. Nếu commit 12, lần khởi động tiếp theo sẽ đọc lại record C.

Có thể biểu diễn:

~~~text
Đọc và xử lý:  10 -> 11 -> 12
                                  |
                                  v
Commit:                            13
                                  |
                                  v
Lần đọc tiếp theo bắt đầu ở 13
~~~

Không commit offset cuối cùng đã xử lý. Hãy commit vị trí kế tiếp.

### 2.1. Offset không nhất thiết liên tiếp

Không nên mặc định rằng hai record liên tiếp mà consumer nhận được có offset hơn kém nhau đúng 1. Kafka có thể có khoảng trống offset do:

- Topic dùng log compaction và các record cũ đã bị loại bỏ.
- Consumer dùng **isolation.level=read_committed** nên không nhận các record thuộc transaction đã abort.
- Transaction marker và một số record điều khiển không được trả về như record nghiệp vụ.
- Log bị xóa theo retention hoặc có các khoảng offset không còn record.

Ví dụ consumer nhận record ở offset 20 và 23. Offset 21 và 22 có thể không có record mà ứng dụng nhìn thấy. Sau khi xử lý record 23, vị trí tiếp theo có thể là 24.

Không tự tính offset commit bằng cách lấy offset cuối cộng 1 trong mọi trường hợp. Với Kafka Java client, khi đã xử lý hết dữ liệu mà một lần **poll()** trả về, hãy dùng **ConsumerRecords.nextOffsets()** để lấy vị trí tiếp theo chính xác cho từng partition.

### 2.2. Offset được lưu theo consumer group và partition

Kafka lưu tiến độ tiêu thụ theo cặp:

- **group.id:** định danh consumer group.
- Topic và partition: luồng dữ liệu mà group đang đọc.
- Offset: vị trí tiếp theo cần đọc.
- Leader epoch nếu có: thông tin thế hệ leader liên quan đến vị trí đã đọc.

Các offset commit của group được lưu trong internal topic **__consumer_offsets** và được quản lý thông qua group coordinator. Hai consumer group khác nhau đọc cùng topic sẽ có tiến độ độc lập.

Một partition chỉ được gán cho một consumer trong cùng consumer group tại một thời điểm theo cơ chế group assignment. Nhưng một topic có thể được nhiều group đọc độc lập.

## 3. Vì sao cần commit riêng theo từng partition?

Một lần **poll()** có thể trả record từ nhiều partition. Các partition có tốc độ xử lý khác nhau; một partition có thể xử lý xong trong vài mili giây, partition khác cần gọi database hoặc dịch vụ bên ngoài lâu hơn.

Ví dụ một lần poll trả về:

| Partition | Record nhận được | Tiến độ xử lý |
|---|---|---|
| orders-0 | 10, 11, 12 | Đã xử lý cả ba |
| orders-1 | 40, 41 | Đã xử lý record 40, record 41 thất bại |
| orders-2 | 7, 8, 9 | Đã xử lý cả ba |

Có thể commit:

- **orders-0** ở vị trí tiếp theo sau record 12.
- **orders-2** ở vị trí tiếp theo sau record 9.
- Không commit vượt qua record 41 của **orders-1**.

Nếu commit position của cả ba partition theo tiến độ đã **poll()** trả về, consumer có thể bỏ qua record 41 khi khởi động lại. Vì vậy, cần theo dõi vị trí hoàn tất riêng cho mỗi partition.

### 3.1. Commit map

Kafka Java Consumer nhận một map gồm **TopicPartition** và **OffsetAndMetadata**:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

offsets.put(
    new TopicPartition("orders", 0),
    new OffsetAndMetadata(13)
);

offsets.put(
    new TopicPartition("orders", 2),
    new OffsetAndMetadata(10)
);

consumer.commitSync(offsets);
~~~

Trong ví dụ, group commit tiến độ partition 0 đến vị trí 13 và partition 2 đến vị trí 10. Partition 1 không có trong map nên offset đã commit của partition đó không bị thay đổi bởi lần gọi này.

Trong code thực tế, nên giữ leader epoch trong **OffsetAndMetadata** khi có thể. **ConsumerRecords.nextOffsets()** cung cấp cả next offset và metadata tương ứng để commit.

## 4. Auto commit và manual commit

Kafka Java Consumer hỗ trợ hai cách quản lý offset.

### 4.1. Auto commit

Khi **enable.auto.commit=true**, Kafka client tự commit position theo chu kỳ **auto.commit.interval.ms**.

Mặc định Kafka 4.4:

| Cấu hình | Mặc định | Ý nghĩa |
|---|---:|---|
| **enable.auto.commit** | true | Bật tự động commit |
| **auto.commit.interval.ms** | 5.000 ms | Chu kỳ commit offset |

Auto commit phù hợp với consumer đơn giản, xử lý nhanh và không cần gắn chặt commit với kết quả của từng thao tác nghiệp vụ.

Rủi ro xuất hiện khi ứng dụng nhận một batch từ **poll()** rồi chưa xử lý hết nhưng đã gọi **poll()** tiếp theo hoặc đóng consumer. Position có thể đã đi xa hơn phần công việc hoàn tất; offset được commit có thể vượt qua record chưa xử lý, dẫn đến mất dữ liệu nghiệp vụ.

Nếu dùng auto commit, ứng dụng phải xử lý hết tất cả record trả về từ một lần **poll()** trước lần **poll()** tiếp theo và trước khi đóng consumer. Với xử lý có gọi database, HTTP hoặc nhiều bước có thể thất bại, manual commit thường dễ kiểm soát hơn.

### 4.2. Manual commit

Khi **enable.auto.commit=false**, ứng dụng quyết định thời điểm commit.

Ví dụ cấu hình:

~~~properties
enable.auto.commit=false
group.id=orders-processor
~~~

Quy trình thường dùng:

1. Gọi **poll()** để nhận record.
2. Xử lý record và ghi kết quả nghiệp vụ.
3. Chỉ khi xử lý thành công, cập nhật vị trí hoàn tất của partition.
4. Commit offset tương ứng.
5. Nếu xử lý thất bại, không commit vượt qua record lỗi.

Manual commit giúp kiểm soát delivery semantics:

- **At-least-once:** xử lý xong rồi mới commit. Nếu ứng dụng lỗi sau khi ghi kết quả nhưng trước khi commit, record có thể được đọc lại. Cần xử lý duplicate an toàn.
- **At-most-once:** commit trước khi xử lý. Nếu ứng dụng lỗi sau commit nhưng trước khi hoàn tất nghiệp vụ, record có thể bị mất khỏi luồng xử lý của group.
- **Exactly-once:** cần cơ chế giao dịch phù hợp. Chỉ commit offset của Kafka sau khi ghi database không tự tạo exactly-once cho database.

## 5. Dùng ConsumerRecords.nextOffsets() trong Kafka 4.4

**ConsumerRecords.nextOffsets()** trả về map **TopicPartition -> OffsetAndMetadata** cho các partition có position được tiến lên trong lần **poll()** đó.

Map này có hai lợi ích:

- Offset là vị trí tiếp theo mà consumer sẽ đọc, đã tính đến các khoảng trống offset.
- **OffsetAndMetadata** có thể mang leader epoch để Kafka phát hiện log truncation trong một số tình huống thay đổi leadership.

Nếu ứng dụng đã xử lý thành công toàn bộ record trả về từ một lần poll, có thể commit map này trực tiếp.

~~~java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(500));

for (ConsumerRecord<String, String> record : records) {
    process(record);
}

Map<TopicPartition, OffsetAndMetadata> nextOffsets =
        records.nextOffsets();

if (!nextOffsets.isEmpty()) {
    consumer.commitSync(nextOffsets);
}
~~~

Đây là cách rõ ràng khi toàn bộ batch đã xử lý thành công. Nếu **process(record)** ném lỗi, luồng không đi đến commit; consumer sẽ đọc lại từ vị trí đã commit trước đó khi được khởi động hoặc nhận assignment mới.

Không dùng **records.nextOffsets()** để commit toàn bộ poll nếu ứng dụng chỉ mới xử lý một phần batch. Map này mô tả vị trí đã được consumer đi qua trong lần poll, không tự biết công việc nghiệp vụ nào đã hoàn tất.

### 5.1. Commit sau khi xử lý từng partition

Nếu muốn một partition đã xử lý xong được commit ngay, trong khi partition khác còn đang xử lý, có thể commit từng entry trong map:

~~~java
for (Map.Entry<TopicPartition, OffsetAndMetadata> entry
        : records.nextOffsets().entrySet()) {

    TopicPartition partition = entry.getKey();

    for (ConsumerRecord<String, String> record
            : records.records(partition)) {
        process(record);
    }

    OffsetAndMetadata nextOffset = entry.getValue();

    consumer.commitSync(
        Collections.singletonMap(partition, nextOffset)
    );
}
~~~

Với cách này:

- Chỉ commit partition sau khi toàn bộ record của partition đó trong batch đã xử lý thành công.
- Nếu partition 0 đã commit rồi partition 1 gặp lỗi, partition 0 vẫn giữ tiến độ mới.
- Partition bị lỗi không được commit vượt qua record chưa xử lý.
- Nếu consumer restart, partition chưa commit sẽ được đọc lại từ committed offset cũ.

Đây là cách commit theo từng partition đúng với tiến độ xử lý độc lập của từng partition.

## 6. Commit một lần hay commit từng partition?

| Cách commit | Thời điểm | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Commit một map sau toàn bộ poll | Tất cả record trong batch đã xử lý xong | Ít request commit, logic đơn giản | Một partition chậm làm chậm commit các partition khác |
| Commit từng partition | Partition nào xử lý xong thì commit partition đó | Giảm lượng record phải xử lý lại ở partition đã hoàn tất | Có thể tạo nhiều request commit hơn |
| Commit sau từng record | Sau mỗi record thành công | Cửa sổ xử lý lại nhỏ | Tăng overhead commit, cần xác định next offset chính xác |
| Auto commit | Theo chu kỳ | Đơn giản, ít code | Khó gắn commit với kết quả xử lý nghiệp vụ |

Không có một chiến lược duy nhất cho mọi ứng dụng. Nếu xử lý nhanh và batch đồng đều, commit một map sau mỗi batch thường đủ. Nếu các partition có độ trễ xử lý rất khác nhau, commit từng partition giúp giảm việc phát lại dữ liệu đã hoàn tất.

## 7. commitSync và commitAsync

Hai API chính để commit thủ công là **commitSync()** và **commitAsync()**.

### 7.1. commitSync

**commitSync()** gửi yêu cầu commit và chờ kết quả.

~~~java
consumer.commitSync(records.nextOffsets());
~~~

Đặc điểm:

- Chỉ tiếp tục sau khi commit thành công hoặc có lỗi/timeout.
- Dễ biết thời điểm checkpoint đã được broker xác nhận.
- Có thể làm chậm vòng **poll()** nếu commit latency cao.
- Phù hợp với checkpoint quan trọng, commit trước khi rời partition hoặc khi kết thúc xử lý batch.

Có thể truyền timeout rõ ràng:

~~~java
consumer.commitSync(
    records.nextOffsets(),
    Duration.ofSeconds(10)
);
~~~

Nếu group đã rebalance và consumer không còn quyền sở hữu partition, commit có thể thất bại với **CommitFailedException**. Nếu đang ở giữa rebalance, client có thể cần hoàn tất rebalance bằng **poll()** rồi mới xem xét commit lại với assignment và position mới.

### 7.2. commitAsync

**commitAsync()** gửi yêu cầu commit mà không chờ kết quả:

~~~java
consumer.commitAsync(
    records.nextOffsets(),
    (offsets, exception) -> {
        if (exception != null) {
            System.err.println(
                "Offset commit failed: " + exception.getMessage()
            );
        }
    }
);
~~~

Đặc điểm:

- Không chặn luồng xử lý để đợi broker xác nhận.
- Có thể tăng throughput khi commit thường xuyên.
- Lỗi commit cần được ghi nhận qua callback.
- Ứng dụng không được xem commit là thành công chỉ vì lời gọi async đã trả về.

Các lần gọi **commitAsync** được gửi theo thứ tự gọi. Tuy nhiên, không nên tự retry một offset cũ trong callback sau khi đã gửi các commit mới hơn: commit cũ có thể ghi đè tiến độ mới nếu ứng dụng tự xếp nó vào sau. Hãy thiết kế checkpoint tăng đơn điệu và cân nhắc **commitSync()** ở ranh giới cần xác nhận chắc chắn.

### 7.3. Chọn API nào?

- Dùng **commitSync()** khi cần xác nhận checkpoint trước khi chuyển giao partition hoặc hoàn tất một batch quan trọng.
- Dùng **commitAsync()** trong vòng lặp throughput cao khi có callback giám sát lỗi và chiến lược checkpoint rõ ràng.
- Có thể dùng async trong vòng xử lý thông thường và sync khi shutdown/rebalance, nhưng phải bảo đảm không commit một offset cũ hơn vị trí đã hoàn tất.

## 8. Xử lý lỗi và bảo đảm offset không vượt qua record chưa hoàn tất

Giả sử partition **orders-0** có các record:

| Offset | Kết quả xử lý |
|---:|---|
| 100 | Thành công |
| 101 | Thành công |
| 102 | Thất bại |
| 103 | Thành công |

Không được commit vị trí sau 103 khi record 102 chưa được xử lý. Nếu commit vượt qua 102, consumer restart sẽ tiếp tục sau record đó và không tự đọc lại record lỗi.

Các lựa chọn xử lý:

1. **Retry tại chỗ:** thử lại record lỗi với số lần giới hạn và backoff. Chưa commit qua record đó.
2. **Retry topic:** publish record sang topic retry với metadata về số lần thử và thời điểm thử lại. Cần bảo đảm record gốc không bị commit trước khi việc chuyển giao retry đã được xác nhận.
3. **Dead Letter Topic (DLT/DLQ):** sau khi hết retry, ghi record lỗi cùng thông tin exception vào DLQ rồi mới cho phép tiến độ partition đi qua record đó.
4. **Dừng partition hoặc consumer:** dùng khi lỗi có thể làm sai trạng thái nghiệp vụ hoặc cần can thiệp thủ công.

Nếu publish sang DLQ thành công nhưng commit offset gốc thất bại, record có thể được gửi vào DLQ lần nữa sau khi consumer restart. Nên dùng **eventId** để deduplicate. Nếu cần giao dịch Kafka-to-Kafka, có thể gửi DLQ record và offset gốc trong cùng Kafka transaction.

### 8.1. Commit theo tiền tố liên tục đã hoàn tất

Khi xử lý song song, record có thể hoàn tất không theo thứ tự nhận:

| Record | Offset | Trạng thái worker |
|---|---:|---|
| A | 200 | Hoàn tất |
| B | 201 | Đang xử lý |
| C | 202 | Hoàn tất |

Dù C đã xong, vẫn không thể commit vị trí sau 202 vì B chưa hoàn tất. Consumer chỉ được commit qua **tiền tố liên tục** các record đã xử lý thành công trong thứ tự của partition.

Khi B hoàn tất, cả A, B và C đều đã hoàn tất; lúc đó consumer mới có thể tiến checkpoint đến vị trí kế tiếp sau C.

Với offset có khoảng trống, hãy theo thứ tự record mà consumer nhận được, không giả định phải có đủ mọi số nguyên offset. Nếu record đầu tiên chưa hoàn tất có offset 201, commit position phải dừng ở 201 dù offset 200 đã xong.

Khi commit một phần batch, offset cần ghi là offset của record đầu tiên chưa xử lý xong. Leader epoch trong `OffsetAndMetadata` nên lấy từ record cuối cùng đã xử lý thành công:

~~~java
ConsumerRecord<String, String> lastFinished = ...;
ConsumerRecord<String, String> firstUnprocessed = ...;

OffsetAndMetadata checkpoint = new OffsetAndMetadata(
    firstUnprocessed.offset(),
    lastFinished.leaderEpoch(),
    ""
);

consumer.commitSync(Map.of(partition, checkpoint));
~~~

Nếu chưa có record nào trong partition được xử lý thành công, giữ nguyên committed offset trước đó. Trong code production, cần lưu `lastFinished` theo từng partition và chỉ cập nhật nó khi công việc nghiệp vụ thực sự hoàn tất.

## 9. Rebalance và commit offset đúng thời điểm

Consumer group có thể rebalance khi:

- Một consumer mới gia nhập group.
- Một consumer bị dừng hoặc mất heartbeat.
- Consumer vượt quá **max.poll.interval.ms**.
- Topic được thêm partition hoặc thay đổi subscription.
- Group thực hiện thay đổi assignment.

Khi partition bị thu hồi khỏi consumer, ứng dụng cần xử lý phần công việc đang dang dở và commit tiến độ an toàn trước khi nhường partition.

### 9.1. ConsumerRebalanceListener

Có thể đăng ký listener khi subscribe:

~~~java
consumer.subscribe(
    Collections.singletonList("orders"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {
            // Hoàn tất/flush công việc đã xử lý.
            // Commit checkpoint an toàn của các partition sắp bị thu hồi.
        }

        @Override
        public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
            // Khởi tạo state cho các partition mới được giao.
        }
    }
);
~~~

Trong **onPartitionsRevoked()**:

- Dừng nhận thêm việc cho các partition sắp bị thu hồi.
- Chờ worker hoàn tất phần công việc có thể hoàn tất an toàn.
- Commit offset của tiền tố đã xử lý thành công.
- Xóa state hoặc cache gắn với partition nếu cần.

Trong **onPartitionsAssigned()**:

- Khôi phục state local tương ứng.
- Đọc committed offset nếu cần kiểm tra.
- Bắt đầu xử lý từ vị trí consumer được group coordinator giao.

Nếu partition đã bị mất quyền sở hữu, không cố commit offset cho partition đó. Commit có thể thất bại vì consumer không còn là thành viên có quyền commit partition.

### 9.2. max.poll.interval.ms và max.poll.records

Kafka 4.4 có mặc định:

| Cấu hình | Mặc định | Vai trò |
|---|---:|---|
| **max.poll.interval.ms** | 300.000 ms (5 phút) | Thời gian tối đa giữa hai lần gọi **poll()** khi dùng group management |
| **max.poll.records** | 500 | Số record tối đa trả về trong một lần **poll()** |

Nếu xử lý batch lâu hơn **max.poll.interval.ms**, consumer có thể bị xem là không còn tiến triển và partition được rebalance sang member khác. Khi đó commit có thể thất bại vì assignment đã thay đổi.

Có thể giảm **max.poll.records**, tối ưu xử lý hoặc tăng interval có chủ đích. Với công việc có thời gian xử lý không dự đoán được, nên tách poll thread và worker thread, dùng **pause()**/**resume()** theo partition và chỉ commit tiền tố đã hoàn tất. **KafkaConsumer** không thread-safe; chỉ thread sở hữu consumer mới được gọi các API như **poll**, **commit**, **pause**, **resume** và **seek**.

## 10. Xử lý song song mà không commit vượt tiến độ

Một mô hình thường gặp là consumer thread đọc record rồi gửi sang worker pool. Mô hình này có thể tăng throughput, nhưng cần quản lý offset theo từng partition.

Luồng đề xuất:

~~~mermaid
flowchart TD
    A["Consumer thread: poll()"] --> B["Phân nhóm record theo TopicPartition"]
    B --> C["Đưa vào queue theo partition"]
    C --> D["Worker xử lý record"]
    D --> E{"Xử lý thành công?"}
    E -->|Có| F["Đánh dấu record hoàn tất"]
    E -->|Không| G["Retry / DLQ / giữ checkpoint"]
    F --> H["Tìm tiền tố liên tục đã hoàn tất"]
    H --> I["Cập nhật next offset của partition"]
    I --> J["Consumer thread commit offset"]
    G --> K["Không commit vượt record lỗi"]
~~~

Các nguyên tắc:

- Giữ thứ tự xử lý trong cùng partition nếu nghiệp vụ cần ordering.
- Mỗi partition có queue hoặc trạng thái completion riêng.
- Theo dõi record đã nhận, đang xử lý và đã hoàn tất.
- Chỉ commit vị trí sau record cuối cùng trong tiền tố liên tục đã hoàn tất.
- Khi queue đầy, pause partition tương ứng để tránh tăng bộ nhớ.
- Tiếp tục gọi **poll()** theo nhịp để giữ consumer trong group.
- Worker không gọi trực tiếp **KafkaConsumer.commitSync()** hoặc **poll()**.

Nếu không cần xử lý song song trong một partition, một worker tuần tự cho mỗi partition thường đơn giản hơn và giúp commit offset dễ kiểm soát.

## 11. Spring Kafka: AckMode và Acknowledgment

Spring Kafka dùng Kafka Consumer bên dưới nhưng cung cấp listener container để quản lý poll, commit và rebalance.

Khi **enable.auto.commit=false**, container hỗ trợ các **AckMode**:

| AckMode | Khi nào commit |
|---|---|
| **RECORD** | Sau khi listener xử lý xong từng record |
| **BATCH** | Sau khi tất cả record trong poll batch được xử lý |
| **TIME** | Khi hết thời gian cấu hình và batch đã xử lý xong |
| **COUNT** | Khi đủ số record cấu hình và batch đã xử lý xong |
| **COUNT_TIME** | Khi đạt điều kiện thời gian hoặc số lượng |
| **MANUAL** | Listener gọi **acknowledge()**; container áp dụng semantics tương tự BATCH |
| **MANUAL_IMMEDIATE** | Commit ngay khi listener gọi **acknowledge()** trên consumer thread |

Spring Kafka mặc định dùng **AckMode.BATCH**. Từ Spring Kafka 2.3, framework mặc định tắt **enable.auto.commit** nếu ứng dụng không cấu hình rõ, để container tự quản lý commit.

### 11.1. Ví dụ MANUAL_IMMEDIATE

Cấu hình container:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
kafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);

    return factory;
}
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-projection",
    containerFactory = "kafkaListenerContainerFactory"
)
public void consume(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    processAndPersist(record);
    acknowledgment.acknowledge();
}
~~~

Trong ví dụ, listener chỉ acknowledge sau khi **processAndPersist()** hoàn tất. Nếu xử lý ném exception, acknowledgment không được gọi và error handler/container sẽ quyết định retry hoặc recovery theo cấu hình.

Không gọi đồng thời **consumer.commitSync()** thủ công từ bên trong listener container. Container đã quản lý consumer và offset; hãy chọn một cơ chế commit nhất quán.

### 11.2. MANUAL và MANUAL_IMMEDIATE khác nhau

**MANUAL** ghi nhận acknowledgment từ listener nhưng commit theo semantics batch sau đó. **MANUAL_IMMEDIATE** cố gắng commit ngay khi **acknowledge()** được gọi trên consumer thread.

Nếu gọi acknowledge từ thread khác, hành vi immediate không còn giống khi gọi trên listener thread. Với xử lý bất đồng bộ, cần hiểu cơ chế out-of-order commits và giới hạn của container trước khi triển khai; không acknowledge record sau khi xử lý xong nếu record đứng trước trong cùng partition vẫn chưa hoàn tất.

## 12. Offset và transaction

Kafka có thể kết hợp việc publish output records và commit input offsets trong cùng một Kafka transaction. Đây là cách xây dựng luồng consume-transform-produce có semantics exactly-once trong phạm vi Kafka.

Luồng khái quát:

1. Consumer đọc input records.
2. Ứng dụng xử lý và tạo output records.
3. Producer bắt đầu transaction.
4. Output records được gửi vào Kafka.
5. Input offsets được gửi vào transaction bằng cơ chế **sendOffsetsToTransaction** hoặc listener container transaction.
6. Transaction commit thành công thì output và offset cùng được công nhận.
7. Nếu transaction abort, consumer có thể đọc lại input.

Consumer downstream cần cấu hình **isolation.level=read_committed** để chỉ nhận output transaction đã commit.

Nếu kết quả xử lý nằm trong database bên ngoài Kafka, Kafka transaction không tự bao trùm transaction database. Có thể lưu kết quả và offset trong cùng transaction database, hoặc dùng inbox/outbox và deduplication để kiểm soát việc phát lại.

## 13. auto.offset.reset không phải offset commit

**auto.offset.reset** chỉ được dùng khi group chưa có committed offset hợp lệ hoặc offset đã commit không còn tồn tại trong log, ví dụ dữ liệu đã bị retention xóa.

Các lựa chọn thường gặp trong Kafka 4.4:

- **earliest:** bắt đầu từ offset sớm nhất còn tồn tại.
- **latest:** bắt đầu từ cuối log hiện tại.
- **by_duration:<duration>:** bắt đầu từ vị trí tương ứng với một khoảng thời gian trước hiện tại.
- **none:** ném lỗi nếu không tìm thấy committed offset hợp lệ.

Nếu group đã có committed offset hợp lệ, consumer tiếp tục từ offset đó; **auto.offset.reset** không đưa consumer về đầu topic sau mỗi lần restart.

Khi tăng số partition và dùng **latest**, cần chú ý khoảng thời gian trước khi consumer phát hiện partition mới. Record được ghi vào partition mới trong khoảng đó có thể bị bỏ qua nếu vị trí khởi tạo được reset về log end. Hãy chọn chính sách reset phù hợp với yêu cầu không mất dữ liệu.

## 14. Kiểm tra committed offset và consumer lag

Dùng lệnh sau để xem tiến độ của group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-projection \
  --describe
~~~

Các cột thường quan sát:

| Cột | Ý nghĩa |
|---|---|
| **TOPIC** | Topic consumer group đang đọc |
| **PARTITION** | Partition cụ thể |
| **CURRENT-OFFSET** | Offset đã commit, tức vị trí tiếp theo cần đọc |
| **LOG-END-OFFSET** | Vị trí cuối hiện tại của log |
| **LAG** | Chênh lệch giữa log end và committed position |

Ví dụ:

| Topic | Partition | CURRENT-OFFSET | LOG-END-OFFSET | LAG |
|---|---:|---:|---:|---:|
| orders | 0 | 120 | 130 | 10 |
| orders | 1 | 85 | 100 | 15 |
| orders | 2 | 310 | 312 | 2 |

Lag là chỉ số hữu ích nhưng không phản ánh đầy đủ thời gian xử lý. Cần kết hợp tốc độ tiêu thụ, tốc độ ghi, thời gian xử lý record và thời gian commit.

### 14.1. Các chỉ số nên theo dõi

- Consumer lag theo từng partition.
- Số record xử lý thành công và thất bại.
- Thời gian xử lý p50, p95, p99.
- Commit latency và commit error rate.
- Số lần rebalance và thời gian hoàn tất rebalance.
- Số lần retry, số record đưa vào DLQ.
- Khoảng cách giữa consumer position và committed position.
- Số worker đang chạy và số record còn pending theo partition.

Nếu lag tăng liên tục, cần xác định consumer thiếu throughput, xử lý record quá lâu, commit bị chậm, partition phân bố không đều hay broker gặp vấn đề.

## 15. Lỗi thường gặp khi commit offset

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Record bị mất sau khi consumer restart | Commit trước khi xử lý xong hoặc auto commit vượt tiến độ | Tắt auto commit và commit sau xử lý thành công |
| Record bị xử lý lặp lại | Ứng dụng lỗi sau khi xử lý nhưng trước khi commit | Thiết kế handler idempotent và dùng event ID |
| Consumer liên tục đọc lại một batch | Commit thất bại hoặc offset map không được cập nhật | Kiểm tra callback, **commitSync()** exception và group assignment |
| **CommitFailedException** | Consumer đã mất quyền sở hữu partition sau rebalance | Hoàn tất poll/rebalance và chỉ commit partition đang được assign |
| Offset nhảy qua record lỗi | Commit position dựa trên poll position thay vì completed prefix | Theo dõi tiến độ riêng từng partition |
| Consumer lag tăng dù xử lý nhanh | Commit chậm, rebalance liên tục hoặc một partition bị nghẽn | Kiểm tra commit latency, poll interval, assignment và lag theo partition |
| Xử lý song song làm đảo thứ tự | Worker hoàn tất không theo thứ tự nhận record | Dùng queue tuần tự theo partition và contiguous completion |
| Spring listener commit quá sớm | Ack được gọi trước khi nghiệp vụ hoàn tất | Chỉ acknowledge sau khi xử lý và lưu kết quả thành công |

## 16. Lab: commit offset riêng theo từng partition

Mục tiêu: tạo topic có ba partition, xử lý record theo partition và quan sát committed offset thay đổi độc lập.

### Bước 1: Tạo topic

~~~bash
bin/kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic orders \
  --partitions 3 \
  --replication-factor 1
~~~

### Bước 2: Chạy consumer với manual commit

Cấu hình consumer:

~~~java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-lab");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName()
);
props.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName()
);
~~~

Sau mỗi lần **poll()**, nhóm record theo partition. Xử lý xong một partition thì commit **OffsetAndMetadata** lấy từ **records.nextOffsets()** cho partition đó.

### Bước 3: Gửi dữ liệu vào nhiều partition

Dùng producer gửi record với nhiều key khác nhau để dữ liệu được phân bố. Ghi lại partition và offset từ producer callback.

### Bước 4: Quan sát tiến độ

Chạy:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-lab \
  --describe
~~~

Quan sát **CURRENT-OFFSET** thay đổi theo từng partition.

### Bước 5: Thử lỗi xử lý

- Làm cho xử lý partition 1 thất bại ở một record.
- Để partition 0 và partition 2 xử lý xong và commit.
- Dừng consumer rồi khởi động lại.
- Xác nhận partition 0 và 2 tiếp tục sau committed offset mới.
- Xác nhận partition 1 đọc lại từ vị trí trước record lỗi.

### Bước 6: Thử auto commit

Bật **enable.auto.commit=true**, giảm **auto.commit.interval.ms** trong môi trường lab và tạo batch xử lý chậm. Quan sát sự khác biệt khi consumer poll tiếp trước khi xử lý hết batch.

Không dùng cấu hình thử nghiệm để kết luận production nếu chưa kiểm tra thời gian xử lý và hành vi lỗi thực tế.

## 17. Checklist trước khi triển khai

- [ ] Hiểu committed offset là vị trí tiếp theo cần đọc.
- [ ] Không nhầm consumer position với committed position.
- [ ] Theo dõi offset độc lập cho từng **TopicPartition**.
- [ ] Không giả định offset trong partition luôn liên tiếp.
- [ ] Dùng **ConsumerRecords.nextOffsets()** khi đã xử lý hết batch.
- [ ] Commit theo từng partition nếu các partition hoàn tất ở thời điểm khác nhau.
- [ ] Tắt auto commit nếu cần gắn commit với kết quả xử lý nghiệp vụ.
- [ ] Chọn **commitSync** hoặc **commitAsync** theo yêu cầu latency và độ tin cậy.
- [ ] Không commit vượt qua record lỗi hoặc record chưa hoàn tất.
- [ ] Xử lý rebalance và commit checkpoint trước khi nhường partition.
- [ ] Giữ poll interval phù hợp với thời gian xử lý.
- [ ] Với xử lý song song, chỉ commit tiền tố liên tục đã hoàn tất.
- [ ] Trong Spring Kafka, chọn **AckMode** phù hợp và để container quản lý commit.
- [ ] Nếu dùng Kafka transaction, commit offset trong transaction khi cần exactly-once Kafka-to-Kafka.
- [ ] Có metric cho lag, commit latency, retry và rebalance.
- [ ] Đã thử crash trước commit, sau commit và giữa lúc rebalance.

## 18. Tài liệu tham khảo

- [Apache Kafka 4.4 – KafkaConsumer Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
- [Apache Kafka 4.4 – Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka 4.4 – ConsumerRecords Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/ConsumerRecords.html)
- [Apache Kafka 4.4 – OffsetAndMetadata Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/OffsetAndMetadata.html)
- [Spring Kafka – Message Listener Containers and Offset Commits](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)

Commit offset là checkpoint của tiến độ xử lý trong từng partition. Hãy commit đúng vị trí tiếp theo cần đọc, chỉ sau khi phần dữ liệu đứng trước vị trí đó đã được xử lý an toàn. Khi kết hợp commit theo partition, rebalance handling và xử lý idempotent, consumer có thể phục hồi sau lỗi mà không bỏ qua record chưa hoàn tất.
