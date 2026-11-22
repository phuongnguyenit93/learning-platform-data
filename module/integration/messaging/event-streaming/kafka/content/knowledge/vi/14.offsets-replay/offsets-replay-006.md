# Phát lại bằng group mới và cách bảo vệ consumer đang hoạt động

Kafka lưu tiến độ đọc theo consumer group, topic và partition. Vì vậy, một ứng dụng có thể đọc cùng một topic bằng nhiều group độc lập: consumer production tiếp tục xử lý theo offset của nó, trong khi một consumer replay dùng group ID khác để đọc lại dữ liệu từ đầu hoặc từ một mốc đã chọn.

Cách này phù hợp khi cần dựng lại read model, tái tạo dữ liệu phân tích, kiểm tra logic xử lý mới hoặc chạy backfill. Điểm quan trọng là tạo một group riêng cho lần replay và kiểm soát tác động của nó lên downstream. Không dùng chung group ID với consumer đang chạy nếu mục tiêu là đọc lại độc lập.

## 1. Offset được lưu riêng theo consumer group

Kafka không lưu một offset duy nhất cho topic. Tiến độ đọc được lưu theo tổ hợp:

`(group.id, topic, partition)`

Ví dụ topic `orders` có ba partition và hai consumer group:

| Group | orders-0 | orders-1 | orders-2 |
|---|---:|---:|---:|
| `orders-service` | 1200 | 980 | 1500 |
| `orders-replay-run-01` | 0 | 0 | 0 |

Hai group đọc cùng các partition nhưng có offset độc lập. Consumer replay có thể bắt đầu từ dữ liệu cũ trong khi consumer production tiếp tục từ checkpoint của nó.

~~~mermaid
flowchart TB
    T["Topic: orders<br/>Partition 0, 1, 2"]
    T --> P["Consumer group: orders-service"]
    T --> R["Consumer group: orders-replay-run-01"]
    P --> PO["Offsets production<br/>1200 / 980 / 1500"]
    R --> RO["Offsets replay<br/>earliest retained offsets"]
    PO --> DB["Production database"]
    RO --> RE["Replay target / staging"]
~~~

Offset của group được lưu trong topic nội bộ `__consumer_offsets`. Việc một group commit offset không ghi đè offset của group khác.

Điều này cho phép chạy replay độc lập, nhưng cũng có nghĩa cả hai group có thể cùng thực hiện side effect lên một hệ thống bên ngoài. Tính độc lập về offset không tự động tạo ra tính độc lập về database, API hoặc dữ liệu nghiệp vụ.

## 2. Vì sao nên dùng group ID mới để replay?

Giả sử consumer production đang dùng:

~~~properties
group.id=orders-service
~~~

Nếu tạo consumer replay cũng dùng `orders-service`, Kafka xem nó là một thành viên khác của cùng group. Các consumer sẽ chia nhau partition theo assignment. Replay consumer có thể nhận một phần partition, làm consumer production mất assignment hoặc gây rebalance. Nó không tạo ra một luồng đọc độc lập.

Thay vào đó, dùng group riêng:

~~~properties
group.id=orders-replay-run-01
auto.offset.reset=earliest
enable.auto.commit=false
~~~

Khi group mới chưa có committed offset, `auto.offset.reset=earliest` yêu cầu consumer bắt đầu từ offset sớm nhất còn được giữ của mỗi partition. Consumer production tiếp tục dùng offset của `orders-service`.

| Lựa chọn | Hành vi | Phù hợp khi |
|---|---|---|
| Cùng group ID production | Chia partition và offset với consumer production | Scale thêm consumer xử lý cùng workload |
| Group ID mới | Có checkpoint riêng, đọc độc lập | Replay, backfill, dựng lại read model |
| Reset offset của group cũ | Thay đổi checkpoint của group đó | Chủ động tua lại một group đã dừng và được phép thay đổi |

Nếu mục tiêu là phát lại mà không làm gián đoạn consumer đang hoạt động, group ID mới là lựa chọn rõ ràng nhất.

## 3. auto.offset.reset=earliest không phải lệnh reset offset

`auto.offset.reset` chỉ được áp dụng khi group không có committed offset hợp lệ cho partition, hoặc offset đã lưu không còn nằm trong phạm vi log hiện tại.

Các giá trị thường dùng:

| Giá trị | Hành vi khi không có offset hợp lệ |
|---|---|
| `earliest` | Bắt đầu từ offset sớm nhất hiện còn trong log |
| `latest` | Bắt đầu từ cuối log tại thời điểm xác định vị trí đọc |
| `none` | Ném lỗi nếu không tìm thấy offset hợp lệ |

Điểm cần nhớ:

- Group mới chưa có offset: `earliest` bắt đầu từ dữ liệu cũ nhất còn lưu.
- Group đã có offset hợp lệ: consumer tiếp tục từ offset đó; `earliest` không tua group về đầu.
- Group có offset cũ đã bị retention xóa: offset có thể out of range; chính sách reset được áp dụng.
- `earliest` không có nghĩa luôn bắt đầu từ offset 0. Nếu dữ liệu cũ đã bị xóa, consumer chỉ có thể đọc từ log start offset hiện tại.

Vì vậy, mỗi lần replay độc lập nên có một group ID riêng. Nếu muốn một replay job có thể restart và tiếp tục từ checkpoint, hãy giữ nguyên group ID của job đó qua các lần khởi động lại. Nếu tạo ID mới mỗi lần restart, consumer sẽ lại không có offset và có thể đọc lại toàn bộ dữ liệu.

## 4. Quy trình replay bằng group mới

Một quy trình an toàn có thể triển khai như sau:

1. Xác định topic, partition và khoảng dữ liệu cần phát lại.
2. Tạo group ID riêng cho lần replay, ví dụ `orders-replay-2026-11-20-run-01`.
3. Cấu hình `auto.offset.reset=earliest` nếu muốn đọc từ dữ liệu sớm nhất còn giữ.
4. Tắt auto commit và chỉ commit sau khi batch đã xử lý thành công.
5. Gửi kết quả replay vào database/index/topic đích được kiểm soát.
6. Theo dõi consumer lag, tốc độ đọc, broker load và tải downstream.
7. Xác minh kết quả bằng event ID, số record, partition/offset và quy tắc nghiệp vụ.
8. Dừng replay khi đạt mục tiêu; giữ lại group ID nếu cần tiếp tục job sau này.

### 4.1. Xác định phạm vi dữ liệu

Trước khi chạy replay, cần trả lời:

- Replay toàn bộ dữ liệu còn được giữ hay chỉ một khoảng thời gian?
- Có cần đọc các event mới phát sinh trong lúc replay không?
- Consumer có cần giữ thứ tự theo key không?
- Replay có được phép cập nhật lại dữ liệu production không?
- Có cần một môi trường staging hoặc một bảng đích riêng không?

Nếu chỉ cần tái tạo dữ liệu đến một mốc cố định, hãy xác định end offset cho từng partition tại thời điểm bắt đầu. Consumer cần dừng khi đã xử lý đến ranh giới đó. Nếu chỉ dùng `earliest` mà không có cutoff, consumer sẽ tiếp tục đọc các event mới được ghi trong lúc replay và có thể đuổi theo luồng live.

### 4.2. Replay toàn bộ dữ liệu còn giữ

Với group mới và `auto.offset.reset=earliest`, consumer đọc từ log start offset của mỗi partition. Sau khi xử lý và commit, group lưu tiến độ riêng. Nếu process khởi động lại với cùng group ID, nó tiếp tục từ committed offset.

~~~mermaid
sequenceDiagram
    participant App as Replay consumer
    participant Coord as Group coordinator
    participant Broker as Partition leaders
    participant Target as Replay target

    App->>Coord: Join group orders-replay-run-01
    App->>Coord: OffsetFetch
    Coord-->>App: Chưa có committed offset
    App->>Broker: Fetch từ earliest retained offset
    Broker-->>App: Record batches
    App->>Target: Xử lý event
    App->>Coord: OffsetCommit sau khi xử lý thành công
    Coord-->>App: Commit result
~~~

Replay toàn bộ có thể kéo dài tùy retention, số partition, tốc độ downstream và cấu hình consumer. Không nên tăng tốc độ đọc đến mức làm ảnh hưởng consumer production hoặc hệ thống database dùng chung.

## 5. Ví dụ Java: consumer replay độc lập

Ví dụ dưới đây dùng group ID riêng, đọc từ dữ liệu sớm nhất còn giữ và commit thủ công sau khi xử lý batch.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

public class OrdersReplayConsumer {

    public static void main(String[] args) {
        Properties props = new Properties();

        props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-replay-2026-11-20-run-01"
        );
        props.put(
            ConsumerConfig.CLIENT_ID_CONFIG,
            "orders-replay-worker-0"
        );
        props.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        props.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        props.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest"
        );
        props.put(
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
            false
        );

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(props)) {

            consumer.subscribe(List.of("orders"));

            while (true) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofMillis(500));

                if (records.isEmpty()) {
                    continue;
                }

                for (var record : records) {
                    replayOrderEvent(
                        record.key(),
                        record.value(),
                        record.topic(),
                        record.partition(),
                        record.offset()
                    );
                }

                // Commit chỉ sau khi toàn bộ batch đã xử lý thành công.
                consumer.commitSync();
            }
        }
    }

    private static void replayOrderEvent(
            String key,
            String value,
            String topic,
            int partition,
            long offset) {
        // Ghi vào replay target hoặc thực hiện xử lý idempotent.
    }
}
~~~

Ví dụ này chạy liên tục và sẽ tiếp tục đọc các event mới khi đã bắt kịp log. Nếu cần replay có giới hạn, hãy bổ sung cutoff theo end offset hoặc timestamp và thoát vòng lặp khi đã xử lý xong phạm vi.

Nếu một record trong batch lỗi, ví dụ không nên commit toàn batch. Các record đã xử lý thành công có thể được đọc lại khi batch được phát lại; vì vậy thao tác ghi đích cần idempotent.

## 6. Replay đến một mốc cố định thay vì theo kịp luồng live

Một lần replay có thể cần tái tạo trạng thái tại một thời điểm xác định, không muốn đọc các event mới phát sinh sau khi bắt đầu. Khi đó, cần tạo snapshot ranh giới theo từng partition.

Cách làm ở mức thiết kế:

1. Sau khi consumer nhận assignment, gọi `endOffsets(partitions)` để ghi nhận end offset của từng partition.
2. Xử lý các record có offset nhỏ hơn end offset đã ghi nhận.
3. Không xử lý record có offset bằng hoặc lớn hơn ranh giới của partition đó.
4. Theo dõi `position(partition)` cho từng partition.
5. Khi tất cả partition đã đạt ranh giới, commit offset cuối cùng đã xử lý và kết thúc job.

End offset là ranh giới exclusive: nếu end offset là 500, record có offset nhỏ hơn 500 thuộc phạm vi snapshot. Record offset 500 trở đi được ghi sau ranh giới và không thuộc lần replay đó.

Khi dùng `read_committed`, cần hiểu end offset và last stable offset theo isolation level; transaction đang mở có thể làm dữ liệu chưa hiển thị cho consumer. Nên ghi lại ranh giới và isolation level cùng metadata của replay run để có thể tái hiện kết quả.

Nếu muốn replay theo thời gian, dùng `offsetsForTimes()` để tìm offset đầu tiên có timestamp lớn hơn hoặc bằng mốc yêu cầu cho từng partition. API có thể trả `null` nếu partition không có record phù hợp; khi đó phải quyết định rõ dùng end offset hay log start offset theo mục tiêu nghiệp vụ.

## 7. Replay theo timestamp hoặc offset cụ thể

Ngoài việc đọc từ đầu, consumer có thể seek đến một vị trí đã chọn. Các API Java thường dùng:

- `beginningOffsets(partitions)`: lấy offset đầu tiên còn được giữ.
- `endOffsets(partitions)`: lấy end offset của partition.
- `offsetsForTimes(timestampMap)`: tìm offset theo timestamp.
- `seek(partition, offset)`: đặt vị trí đọc cho partition đã được assign.

Các API `seek` cần được gọi sau khi consumer đã có assignment cho partition. Nếu dùng `subscribe()`, hãy đợi assignment hoàn tất trong poll loop hoặc dùng callback phù hợp trước khi seek.

Ví dụ khái niệm tìm offset theo timestamp:

~~~java
Map<TopicPartition, Long> timestamps = new HashMap<>();

for (TopicPartition partition : consumer.assignment()) {
    timestamps.put(partition, replayStartEpochMillis);
}

Map<TopicPartition, OffsetAndTimestamp> positions =
    consumer.offsetsForTimes(timestamps);

for (var entry : positions.entrySet()) {
    OffsetAndTimestamp result = entry.getValue();

    if (result != null) {
        consumer.seek(entry.getKey(), result.offset());
    } else {
        // Không có record từ timestamp yêu cầu:
        // quyết định dùng end offset hoặc policy khác.
    }
}
~~~

Đoạn code giả định consumer đã có assignment và các import `Map`, `HashMap`, `TopicPartition`, `OffsetAndTimestamp` đã được khai báo. Nếu cần một lần replay độc lập, hãy dùng group ID mới hoặc một group replay riêng có checkpoint được quản lý.

Không nhầm timestamp trong record với thời điểm nghiệp vụ tuyệt đối. Kafka timestamp có thể là CreateTime do producer đặt hoặc LogAppendTime do broker gán, tùy cấu hình topic/broker. Nếu nghiệp vụ cần lọc theo `occurredAt` trong payload, có thể phải đọc thêm và lọc trong ứng dụng.

## 8. Bảo vệ consumer production đang hoạt động

Tạo group mới giữ offset production độc lập, nhưng replay vẫn dùng tài nguyên chung. Để tránh gây ảnh hưởng:

### 8.1. Không dùng chung group ID

Group replay phải có tên khác production. Ví dụ:

~~~properties
# Consumer đang phục vụ production
group.id=orders-service

# Consumer replay
group.id=orders-replay-run-01
~~~

Không reset offset của `orders-service` khi consumer production còn hoạt động. Việc reset offset một group đang chạy có thể xung đột với các consumer đang commit, gây assignment/offset khó dự đoán hoặc làm ứng dụng đọc lại/bỏ qua dữ liệu.

### 8.2. Tách đích ghi của replay

Nếu replay gọi lại cùng logic cập nhật production database, nó có thể ghi đè trạng thái mới bằng event cũ hoặc kích hoạt side effect lần nữa.

Các lựa chọn an toàn:

- Ghi vào schema/database staging riêng.
- Dựng read model mới rồi chuyển traffic sau khi xác minh.
- Dùng event ID và upsert/idempotency key.
- Tách các lệnh gửi email, thanh toán, thông báo hoặc side effect bên ngoài khỏi replay.
- Nếu bắt buộc ghi production, dùng quy tắc version/sequence để ngăn event cũ ghi đè trạng thái mới.

Replay dữ liệu lịch sử và phát lại side effect là hai hoạt động khác nhau. Không nên mặc định chạy lại handler production sẽ an toàn.

### 8.3. Giới hạn tốc độ replay

Replay consumer có thể đọc nhanh hơn consumer production vì nó không phải phục vụ request trực tiếp. Tuy nhiên, tốc độ cao có thể làm tăng:

- Broker network throughput và disk I/O.
- Fetch request và CPU của broker.
- Consumer lag của các workload khác nếu tài nguyên dùng chung bị bão hòa.
- Connection pool, CPU, lock và I/O của database.
- Tải của downstream API hoặc hệ thống search.

Dùng `max.poll.records`, `fetch.max.bytes`, `max.partition.fetch.bytes`, số consumer và giới hạn tốc độ ở tầng ứng dụng để kiểm soát. Có thể pause partition hoặc giảm concurrency nếu downstream bắt đầu quá tải.

Không tăng số consumer replay vượt số partition với kỳ vọng một partition được xử lý song song bởi nhiều consumer trong cùng group.

## 9. Retention và compaction giới hạn khả năng replay

Replay chỉ có thể đọc dữ liệu còn tồn tại trong topic. Offset 0 có thể đã bị xóa bởi retention; `earliest` có nghĩa offset sớm nhất còn lại chứ không phải toàn bộ lịch sử từng được ghi.

Hai chính sách cleanup phổ biến:

| cleanup.policy | Dữ liệu có thể replay |
|---|---|
| `delete` | Các segment còn nằm trong retention theo thời gian/dung lượng |
| `compact` | Chủ yếu giữ giá trị mới nhất theo key sau compaction; không bảo đảm toàn bộ lịch sử event |
| `compact,delete` | Kết hợp compaction và retention; lịch sử có thể bị loại bỏ theo cả hai cơ chế |

Với topic compacted, record cũ của cùng key có thể bị loại sau compaction. Tombstone cũng có thể bị xóa sau thời gian giữ tombstone. Vì vậy, compacted topic thường phù hợp tái tạo trạng thái mới nhất theo key, không phải replay toàn bộ event history.

Trước khi chạy backfill dài, hãy kiểm tra:

- `retention.ms` và `retention.bytes`.
- `cleanup.policy`.
- Log start offset của từng partition.
- Số record thực sự còn lại.
- Topic có dùng compaction và tombstone hay không.

Replication factor không thay thế retention hoặc backup. Nếu event đã bị xóa khỏi mọi replica theo retention, tạo group mới cũng không thể khôi phục chúng.

## 10. Commit offset và khả năng chạy lại

Với replay, nên tắt auto commit và commit sau khi xử lý thành công. Điều này làm rõ ranh giới giữa dữ liệu đã xử lý và dữ liệu còn phải làm lại.

| Thời điểm commit | Hệ quả |
|---|---|
| Trước xử lý | Có nguy cơ bỏ qua event nếu process chết sau commit |
| Sau xử lý thành công | Có thể xử lý lặp nếu chết trước commit |
| Sau khi ghi đích có idempotency | Có thể retry an toàn hơn vì ghi lặp không tạo side effect mới |
| Không commit trong suốt job | Restart có thể đọc lại từ checkpoint cũ và làm lại nhiều dữ liệu |

Với database target, một cách phổ biến là ghi event ID vào bảng có unique constraint cùng với cập nhật read model trong một database transaction. Nếu event ID đã tồn tại, xử lý lần nữa có thể được bỏ qua hoặc trả về kết quả đã có.

Nếu output của replay là một topic Kafka khác và cần atomicity giữa consume và produce, có thể xem xét Kafka transaction. Nếu output là database hoặc API, Kafka transaction không tự bao trùm hệ thống bên ngoài.

## 11. Theo dõi replay và xác minh kết quả

Một replay run nên có metadata để truy vết:

- Replay run ID và group ID.
- Topic và danh sách partition.
- Start offset/end offset hoặc timestamp range.
- Isolation level.
- Thời điểm bắt đầu/kết thúc.
- Phiên bản ứng dụng và schema.
- Số record đọc, thành công, lỗi, duplicate và bỏ qua.
- Checkpoint cuối cùng theo từng partition.

Các lệnh kiểm tra group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service
~~~

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-replay-run-01
~~~

Hai lệnh cho phép đối chiếu committed offset và lag của production group với replay group. Khi replay mới bắt đầu, group có thể chưa xuất hiện trong danh sách cho đến khi consumer tham gia hoặc commit offset.

Có thể kiểm tra topic và partition:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
~~~

Sau khi replay, xác minh bằng số event ID duy nhất, tổng record theo partition, phạm vi offset đã xử lý và các quy tắc nghiệp vụ. Chỉ nhìn thấy consumer lag bằng 0 không đủ chứng minh read model đã được dựng đúng.

## 12. Khi nào cần reset offset của group hiện có?

Replay bằng group mới không yêu cầu reset offset. Nhưng đôi khi cần tua lại một consumer group đã dừng và tiếp tục dùng chính group đó. Khi đó có thể dùng công cụ `kafka-consumer-groups.sh --reset-offsets`.

Ví dụ minh họa reset một group đã dừng về earliest:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-recovery \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Sau khi xem kết quả và xác nhận phạm vi, mới thực hiện:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-recovery \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Các lệnh reset offset thường yêu cầu consumer group không có member đang hoạt động. Hãy kiểm tra cú pháp của phiên bản CLI và xác minh group đã dừng trước khi execute. Không chạy reset lên group production đang hoạt động để phục vụ một replay thử nghiệm.

Các lựa chọn reset khác tùy phiên bản gồm `--to-offset`, `--to-datetime`, `--by-duration`, `--shift-by` hoặc `--to-latest`. Luôn dùng `--dry-run` trước và kiểm tra offset mục tiêu theo từng partition.

## 13. Lỗi thường gặp khi replay bằng group mới

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Replay bắt đầu gần cuối topic | `auto.offset.reset=latest` hoặc group đã có offset hợp lệ | Dùng group ID mới và `earliest` |
| Replay không đọc từ offset 0 | Retention đã xóa dữ liệu cũ | Kiểm tra log start offset và retention |
| Consumer production bị rebalance khi replay bắt đầu | Replay dùng nhầm group ID production | Dùng group ID riêng |
| Replay xử lý event mới mãi không kết thúc | Không đặt end offset/timestamp cutoff | Chụp ranh giới theo từng partition |
| Database có dữ liệu trùng | Replay gọi lại side effect, thiếu idempotency | Dùng event ID, unique constraint hoặc target riêng |
| Read model bị lùi trạng thái | Event cũ ghi đè state mới | Dùng version/sequence hoặc dựng read model riêng |
| Replay làm production chậm | Tăng tải broker và downstream | Giới hạn tốc độ, concurrency và batch |
| Không tìm thấy event cần replay | Compaction/retention đã loại record | Kiểm tra cleanup policy và archive/backup |
| Reset offset không thực hiện được | Group còn member hoạt động hoặc sai CLI syntax | Dừng group, dry-run và dùng đúng phiên bản tool |

## 14. Checklist replay an toàn

- [ ] Đã xác định topic, partition và phạm vi dữ liệu cần phát lại.
- [ ] Replay dùng group ID riêng với production.
- [ ] `auto.offset.reset=earliest` được dùng khi group replay chưa có offset hợp lệ.
- [ ] Group ID được giữ ổn định nếu cần resume cùng một replay job.
- [ ] Đã kiểm tra retention, cleanup policy và log start offset.
- [ ] Đã quyết định replay toàn bộ dữ liệu còn giữ hay snapshot đến end offset/timestamp.
- [ ] Auto commit được tắt nếu cần kiểm soát checkpoint sau xử lý.
- [ ] Side effect được tách hoặc bảo vệ bằng event ID/idempotency.
- [ ] Đã đánh giá tác động lên broker và downstream.
- [ ] Có giới hạn tốc độ, concurrency và batch.
- [ ] Đã theo dõi offset/lag của cả production group và replay group.
- [ ] Đã xác minh kết quả bằng event ID, offset và quy tắc nghiệp vụ.
- [ ] Không reset offset của consumer production đang hoạt động.

Phát lại bằng group mới tận dụng việc Kafka lưu offset độc lập cho từng consumer group. Group replay có thể đọc dữ liệu cũ mà không thay đổi checkpoint của production group. Để replay an toàn, cần chọn đúng phạm vi dữ liệu, hiểu giới hạn retention/compaction, giữ group ID ổn định khi cần resume và kiểm soát side effect cùng tải downstream. Group ID mới bảo vệ tiến độ đọc của consumer đang hoạt động; tính an toàn của dữ liệu đích vẫn phụ thuộc vào idempotency và quy trình xác minh của ứng dụng.
