# Consumer lag, checkpoint và tiếp tục đọc stream

## 1. Vì sao phải theo dõi tiến độ consumer?

Trong kiến trúc hướng sự kiện, producer ghi thông điệp vào queue hoặc stream; consumer đọc và xử lý chúng. Với serverless, một Java function có thể được kích hoạt theo từng batch sự kiện. Nền tảng có thể tăng số instance khi lưu lượng tăng, nhưng việc function được gọi thành công không tự chứng minh rằng mọi thông điệp đã được xử lý và lưu kết quả an toàn.

Hai câu hỏi vận hành quan trọng là: consumer đang chậm hơn producer bao nhiêu, và nếu consumer dừng đột ngột thì lần đọc tiếp theo bắt đầu từ đâu? **Consumer lag** mô tả khoảng cách giữa dữ liệu đã có và tiến độ consumer đã hoàn tất. **Checkpoint** lưu vị trí tiến độ để consumer có thể tiếp tục sau restart, rebalance hoặc lỗi. Hai khái niệm liên quan chặt chẽ: checkpoint không chính xác có thể làm lag hiển thị sai, bỏ sót dữ liệu hoặc phát lại dữ liệu đã xử lý.

Trong một hệ thống serverless, lag tăng có thể làm kết quả nghiệp vụ đến muộn, ví dụ thanh toán đã được chấp thuận nhưng đơn hàng vẫn ở `PENDING`. Nếu không giám sát tuổi thông điệp và checkpoint, hệ thống có thể báo function chạy bình thường trong khi backlog vẫn tăng liên tục.

## 2. Queue và stream lưu tiến độ khác nhau

Queue và stream đều truyền thông điệp bất đồng bộ nhưng cách biểu diễn tiến độ thường khác nhau:

| Đặc điểm | Queue | Stream có thứ tự/offset |
|---|---|---|
| Mô hình đọc | Consumer nhận một thông điệp rồi xác nhận (ack) hoặc để thông điệp được giao lại | Consumer đọc theo vị trí trong log hoặc shard |
| Tiến độ | Thường thể hiện qua trạng thái ack/delete của từng message | Thường thể hiện bằng offset, sequence number hoặc checkpoint theo partition/shard |
| Sau khi xử lý | Message đã ack có thể bị xóa khỏi queue | Record vẫn nằm trong stream đến khi hết retention; consumer group có thể đọc lại |
| Nhiều consumer | Thường cạnh tranh nhận message hoặc dùng subscription riêng | Có thể dùng consumer group riêng để mỗi nhóm đọc độc lập |
| Replay | Thường cần giữ bản sao, DLQ hoặc cơ chế redrive | Có thể seek về offset/sequence cũ nếu dữ liệu còn trong retention |

Không phải queue nào cũng có semantics giống nhau và không phải stream nào cũng dùng số offset liên tục. Ví dụ Kafka dùng offset theo từng partition; Kinesis dùng sequence number theo shard; một số dịch vụ managed stream lưu checkpoint qua event source mapping. Khi triển khai, cần hiểu đúng semantics của nền tảng thay vì giả định mọi `ack`, `commit` và `checkpoint` đều tương đương.

## 3. Consumer lag là gì?

Với một stream có offset, lag thường được biểu diễn bằng khoảng cách giữa vị trí mới nhất có thể đọc và vị trí consumer đã commit. Trong Kafka, một cách tính phổ biến cho từng partition là:

\[
\text{lag records} = \text{log end offset} - \text{committed offset}
\]

Offset được commit thường biểu thị **offset kế tiếp cần đọc**, không phải offset cuối cùng đã xử lý. Ví dụ, nếu consumer đã xử lý record offset `41` thành công và commit `42`, lần khởi động tiếp theo bắt đầu từ offset `42`.

Giả sử partition có log end offset là `500000` và committed offset là `487500`, lag xấp xỉ `12500` record. Với tốc độ xử lý 500 record/giây và tốc độ producer tạm thời không đáng kể, backlog tương đương khoảng 25 giây xử lý. Đây chỉ là ước lượng; tốc độ đến, kích thước record và thời gian xử lý có thể thay đổi.

### Các cách đo lag

| Chỉ số | Câu hỏi được trả lời | Lưu ý |
|---|---|---|
| Offset/record lag | Consumer còn cách đầu stream bao nhiêu record? | Hữu ích để so sánh trong cùng partition; offset có thể có khoảng trống |
| Time lag / age of oldest record | Record chưa xử lý lâu nhất đã chờ bao lâu? | Gần với trải nghiệm nghiệp vụ hơn, nhưng phụ thuộc timestamp và đồng hồ |
| Byte lag | Còn bao nhiêu dữ liệu chưa đọc? | Hữu ích khi record có kích thước rất khác nhau |
| Processing latency | Một record mất bao lâu từ lúc phát đến lúc xử lý xong? | Đo end-to-end delay, cần timestamp đáng tin cậy |
| Backlog growth rate | Lag đang tăng hay giảm với tốc độ nào? | Giúp phát hiện consumer không theo kịp producer |

Không nên chỉ nhìn tổng lag của cả stream. Một partition có thể bị nghẽn trong khi các partition khác gần như không có lag. Hãy theo dõi theo consumer group và từng partition/shard, đồng thời quan sát partition có lag lớn nhất và tuổi record cũ nhất.

### Offset lag và time lag không giống nhau

Một partition có thể có 10.000 record chờ nhưng chỉ tương đương vài giây nếu producer đang phát nhanh; một partition khác chỉ có 100 record nhưng record đầu tiên đã chờ 30 phút vì consumer bị dừng. Offset lag giúp đo khối lượng tương đối; age lag giúp đánh giá mức độ trễ nghiệp vụ.

Với Kafka, offset là vị trí trong log chứ không nhất thiết là số record liên tục nhìn thấy được. Compaction, transaction và các khoảng offset bị bỏ qua có thể khiến phép trừ offset không bằng chính xác số record mà ứng dụng sẽ nhận. Với `read_committed`, consumer cũng chỉ đọc các record đã commit theo semantics transaction của Kafka. Vì vậy, hãy coi offset lag là chỉ số tiến độ của log và kết hợp với metric record/age do nền tảng hoặc ứng dụng cung cấp.

Tùy cách broker công bố metric, mốc cuối có thể là log end offset, high watermark hoặc last stable offset. Với consumer dùng `read_committed`, last stable offset có thể phù hợp hơn để ước lượng phần dữ liệu hiện đã đọc được, vì nó không vượt qua transaction đang mở. Khi so sánh dashboard và công cụ quản trị, cần kiểm tra chúng đang dùng cùng loại mốc offset.

## 4. Tính khả năng bắt kịp backlog

Consumer chỉ giảm được backlog nếu tốc độ xử lý lớn hơn tốc độ record mới đến. Gọi:

- \(B\): số record đang tồn đọng.
- \(\lambda\): tốc độ record mới đến mỗi giây.
- \(\mu\): tổng tốc độ xử lý thành công mỗi giây.

Khi \(\mu > \lambda\), thời gian bắt kịp gần đúng là:

\[
T_{catchup} \approx \frac{B}{\mu - \lambda}
\]

Ví dụ có 120.000 record tồn đọng, consumer xử lý được 1.500 record/giây và producer tiếp tục phát 1.000 record/giây. Tốc độ giảm backlog là 500 record/giây, do đó cần khoảng 240 giây để bắt kịp nếu tải và hiệu năng ổn định.

Nếu \(\mu \leq \lambda\), backlog sẽ không giảm. Tăng số lần invocation hoặc tăng concurrency không chắc giúp được nếu nút thắt là database, API bên ngoài, giới hạn partition hoặc một partition key bị nóng. Khi tính throughput, hãy dùng số liệu xử lý **thành công**, không chỉ số record đã poll hoặc nhận vào function.

## 5. Checkpoint, offset và commit

Checkpoint là vị trí mà consumer có thể dùng để tiếp tục đọc sau khi dừng. Tùy nền tảng, checkpoint có thể là:

- Offset đã commit của một consumer group trong từng Kafka partition.
- Sequence number đã xử lý của một Kinesis shard.
- Vị trí đọc được event source mapping lưu cho function.
- Cursor hoặc token tiến độ do hệ thống stream quản lý.

Checkpoint cần đại diện cho tiến độ **đã hoàn tất bền vững**. Việc poll hoặc nhận record không đồng nghĩa record đã được xử lý. Việc gọi một API thành công cũng chưa đủ nếu kết quả chưa được lưu ở nơi có thể khôi phục.

### Commit sau khi xử lý

Giả sử consumer đọc record offset `41`:

1. Consumer đọc record.
2. Áp dụng thay đổi nghiệp vụ và commit giao dịch database.
3. Sau khi database xác nhận thành công, consumer commit offset `42`.
4. Nếu consumer dừng trước bước 3, record `41` có thể được giao lại và cần được xử lý idempotent.

Commit sau khi hiệu ứng nghiệp vụ đã bền vững ưu tiên tránh mất dữ liệu. Đổi lại, nếu tiến trình chết sau khi ghi dữ liệu nhưng trước khi commit offset, record có thể được xử lý lại. Đây là hành vi at-least-once thường gặp.

### Vì sao không commit trước khi xử lý?

Nếu consumer commit offset `42` trước khi ghi thay đổi nghiệp vụ của record `41`, rồi bị dừng giữa hai bước, lần chạy sau bắt đầu ở `42`. Record `41` đã bị đánh dấu hoàn tất dù nghiệp vụ chưa được lưu. Đây là tình huống mất xử lý (message loss) ở góc nhìn ứng dụng.

### Checkpoint quá thường xuyên hoặc quá thưa

- Commit sau từng record giảm lượng công việc có thể phải phát lại khi lỗi, nhưng tăng số thao tác commit và overhead.
- Commit theo batch giảm overhead, nhưng nếu function dừng giữa batch, nhiều record đã xử lý có thể được giao lại.
- Commit theo timer cần phối hợp với tiến độ thực tế; không commit vị trí mới nhất đã poll nếu còn record đang xử lý.

Chọn ranh giới commit dựa trên latency, throughput, kích thước batch và khả năng idempotent. Trong môi trường FaaS, event source mapping thường quản lý checkpoint theo batch hoặc theo record lỗi; function phải tuân theo giao thức phản hồi của nền tảng.

## 6. Checkpoint phải là tiến độ liên tục khi xử lý song song

Một lỗi tinh vi xảy ra khi consumer xử lý record song song. Giả sử một partition có các record `100`, `101`, `102`:

- Record `100` đang xử lý chậm.
- Record `101` và `102` đã hoàn tất.
- Consumer commit vị trí sau `102` (offset `103`).
- Instance bị dừng trước khi `100` hoàn tất.

Khi tiếp tục từ `103`, record `100` có thể bị bỏ qua dù chưa xử lý. Vì vậy, checkpoint phải chỉ ra **vị trí kế tiếp sau record liên tục cuối cùng đã hoàn tất**, không phải record có offset cao nhất vừa hoàn tất.

<text weight="semibold">Ví dụ tiến độ theo partition</text>

```text
Offset:        100       101       102       103
Trạng thái:   RUNNING   DONE      DONE      NOT READ
Checkpoint:   100       100       100       100
                         ^
           Chưa thể vượt qua 100 vì record này chưa xong

Sau khi 100 hoàn tất:
Offset:        100       101       102       103
Trạng thái:   DONE      DONE      DONE      NOT READ
Checkpoint:                         103
```

Trong ví dụ, checkpoint là offset kế tiếp cần đọc. Sau khi cả `100`, `101` và `102` hoàn tất, consumer mới commit `103`. Nếu record thất bại, consumer phải retry hoặc chuyển nó sang quy trình cách ly theo chính sách trước khi tiến qua vị trí đó.

“Liên tục” ở đây có nghĩa là mọi record đủ điều kiện đọc trước vị trí checkpoint đã được xử lý an toàn theo thứ tự của partition. Không phải mọi giá trị offset số học đều nhất thiết có record; compaction hoặc transaction có thể tạo khoảng trống. Consumer cần dùng position/offset semantics của broker thay vì tự giả định rằng mỗi offset kế tiếp luôn tồn tại.

Để xử lý song song an toàn, có thể dùng một trong các cách:

- Xử lý tuần tự trong từng partition, song song giữa các partition.
- Theo dõi trạng thái hoàn tất của từng offset và chỉ commit offset liên tục cao nhất.
- Tạm dừng partition khi batch có record lỗi, hoàn tất hoặc retry record đó trước khi tiếp tục.
- Dùng API partial batch failure của nền tảng để chỉ checkpoint đến vị trí an toàn theo đúng semantics mà nền tảng quy định.

Không giả định rằng thứ tự hoàn tất thread hoặc future chính là thứ tự record. Nếu nghiệp vụ yêu cầu thứ tự theo aggregate, phải giữ thứ tự đó ở consumer hoặc dùng partition key phù hợp.

## 7. Java Kafka consumer: tắt auto commit và commit sau xử lý

Ví dụ sau minh họa consumer xử lý tuần tự các record được trả về từ `poll`. Khi mọi record trong batch đã được xử lý và lưu bền vững, consumer mới commit vị trí hiện tại. Nếu handler ném exception, `commitSync()` không được gọi; khi consumer khởi động lại, các record chưa commit có thể được đọc lại.

```java
import java.time.Duration;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

public final class OrderEventsConsumer {
    public static void main(String[] args) {
        Properties properties = new Properties();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "broker:9092");
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, "order-projection-v1");
        properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(properties)) {
            consumer.subscribe(java.util.List.of("order-events"));

            while (true) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(500));

                for (ConsumerRecord<String, String> record : records) {
                    // Hàm này phải lưu hiệu ứng nghiệp vụ bền vững và idempotent.
                    applyEventIdempotently(record.key(), record.value());
                }

                // Commit offset kế tiếp sau khi toàn bộ batch đã thành công.
                consumer.commitSync();
            }
        }
    }

    private static void applyEventIdempotently(String key, String value) {
        // Thay bằng transaction DB + inbox/unique event ID trong ứng dụng thực tế.
    }
}
```

Đây là ví dụ consumer chạy liên tục, không phải handler trực tiếp cho mọi FaaS. `KafkaConsumer` không thread-safe; không chia sẻ cùng instance cho nhiều thread. Nếu xử lý song song, phải quản lý offset liên tục cho từng partition và không commit vượt qua record chưa hoàn tất. Trong production cũng cần cấu hình bảo mật broker, deserializer/schema, graceful shutdown, poll interval, max poll records, timeout và error handling.

`auto.offset.reset=earliest` chỉ được áp dụng khi group không có offset hợp lệ hoặc offset không còn tồn tại theo semantics Kafka; nó không khiến consumer đọc lại từ đầu mỗi lần restart. `latest` có thể bỏ qua backlog cũ khi group chưa có offset. `none` khiến consumer báo lỗi nếu không tìm thấy offset để buộc người vận hành chọn chính sách rõ ràng.

Nếu chạy trong FaaS qua event source mapping, nền tảng thường quản lý consumer group, poll và checkpoint. Khi đó function nhận batch sự kiện và trả kết quả theo hợp đồng trigger. Không tự tạo Kafka consumer loop bên trong function nếu nền tảng đã quản lý việc poll; hai lớp poll/commit độc lập có thể gây cạnh tranh hoặc checkpoint sai.

## 8. Resume: tiếp tục từ checkpoint

Resume là khởi động hoặc tiếp tục consumer từ vị trí đã lưu. Quy trình tổng quát:

1. Xác định consumer group hoặc subscription cần tiếp tục.
2. Đọc checkpoint đã commit theo từng partition/shard.
3. Kiểm tra checkpoint còn nằm trong phạm vi dữ liệu được giữ hay không.
4. Gán partition/shard cho consumer theo cơ chế của nền tảng.
5. Đọc từ vị trí kế tiếp checkpoint, áp dụng xử lý idempotent và tiếp tục commit.
6. Theo dõi lag, lỗi và số lần replay trong giai đoạn bắt kịp.

Trong Kafka, consumer group lưu offset theo partition. Khi một consumer restart, nó tham gia group và nhận partition assignment; consumer bắt đầu từ committed offset của partition. Nếu không có offset hợp lệ, `auto.offset.reset` quyết định hành vi như `earliest`, `latest` hoặc `none`. Đặt `earliest` có thể phát lại nhiều dữ liệu cũ; đặt `latest` có thể bỏ qua backlog đã tồn tại trước khi group bắt đầu.

Trong stream chia shard, checkpoint thường gắn với sequence number hoặc vị trí trong shard. Event source mapping có thể tự khôi phục từ checkpoint đã lưu. Khi function lỗi, nền tảng có thể retry batch hoặc shard theo chính sách cấu hình. Cần đọc tài liệu của trigger cụ thể để biết record nào được phát lại và checkpoint được cập nhật khi nào.

### Resume khác replay

- **Resume:** tiếp tục từ checkpoint hiện tại sau gián đoạn thông thường.
- **Replay:** chủ động đọc lại một khoảng dữ liệu cũ để khôi phục, sửa projection hoặc chạy lại logic.
- **Backfill:** đọc lịch sử để tạo dữ liệu mới, thường dùng consumer group hoặc pipeline riêng.

Replay có thể tạo hiệu ứng lặp ở hệ thống đích. Trước khi replay, cần xác định consumer có idempotent, dữ liệu đầu ra có thể ghi đè an toàn hay không, và có cần dùng một consumer group mới để không ảnh hưởng tiến độ production. Không reset offset của consumer group production một cách tùy tiện để “thử lại”; việc đó có thể khiến mọi partition phát lại dữ liệu ngoài dự kiến.

## 9. Retention và checkpoint hết hạn

Checkpoint chỉ hữu ích nếu dữ liệu ở vị trí đó còn được lưu. Stream có retention hữu hạn; Kafka có thể xóa segment theo thời gian hoặc dung lượng, còn dịch vụ stream managed có thể giới hạn số ngày giữ record. Nếu consumer dừng lâu hơn retention, checkpoint có thể trỏ đến dữ liệu đã bị xóa.

Khi offset nằm ngoài phạm vi còn lưu, nền tảng có thể báo `OffsetOutOfRange`, yêu cầu chọn reset policy hoặc bắt đầu từ vị trí khả dụng. Chọn `earliest` khi dữ liệu cũ còn có thể phát lại; nếu dữ liệu đã hết retention, `earliest` chỉ là record cũ nhất còn lại. Chọn `latest` giúp tiếp tục nhận record mới nhưng bỏ qua phần backlog đã mất. Không có lựa chọn tự động nào khôi phục được record đã bị xóa.

Để giảm rủi ro:

- Đặt retention dài hơn thời gian gián đoạn tối đa mà nghiệp vụ chấp nhận.
- Cảnh báo khi age lag tiến gần retention window.
- Lưu bản sao hoặc archive nếu cần replay lịch sử dài hạn.
- Có quy trình tái tạo projection hoặc đối soát từ nguồn dữ liệu chuẩn.
- Ghi nhận rõ khoảng dữ liệu không thể khôi phục và đánh giá ảnh hưởng nghiệp vụ.

Retention dài hơn giúp có thêm thời gian phục hồi nhưng tăng chi phí lưu trữ và có thể ảnh hưởng giới hạn dung lượng. Hãy cân đối giữa RPO, thời gian phục hồi, nhu cầu audit và chi phí.

## 10. Rebalance và quyền sở hữu partition

Trong Kafka consumer group, rebalance xảy ra khi thành viên tham gia/rời group, session timeout hoặc partition được phân bổ lại. Khi rebalance, consumer có thể mất quyền sở hữu partition đang xử lý. Nếu commit không kịp hoặc xử lý dở dang, record có thể được giao lại cho consumer khác.

Một consumer cần:

- Xử lý graceful shutdown và dừng nhận thêm công việc khi sắp mất assignment.
- Hoàn tất hoặc hủy công việc đang chạy theo chính sách rõ ràng.
- Commit offset an toàn trước khi nhả partition nếu còn thời gian và quyền sở hữu.
- Không commit sau khi đã mất quyền sở hữu partition.
- Thiết kế handler idempotent vì rebalance vẫn có thể tạo duplicate.

Trong FaaS, event source mapping có thể quản lý lease/shard ownership thay cho ứng dụng. Tuy nhiên, scale out, timeout function, deploy phiên bản mới hoặc lỗi mapping vẫn có thể làm shard được giao lại. Cần giám sát số lần invoke, retry và checkpoint để nhận biết vòng lặp lỗi.

Số consumer có ích trong một group bị giới hạn bởi số partition/shard có thể xử lý song song. Nếu topic có 8 partition mà tạo 30 consumer cùng group, tối đa khoảng 8 consumer có thể sở hữu partition tại một thời điểm; phần còn lại có thể không nhận dữ liệu. Tăng partition có thể tăng song song nhưng ảnh hưởng thứ tự, key mapping và vận hành; hãy thiết kế partitioning từ đầu theo throughput dự kiến.

## 11. Backpressure và cách xử lý lag tăng

Backpressure là cách giới hạn tốc độ đầu vào hoặc tốc độ xử lý để consumer không làm quá tải dependency. Lag tăng có thể do producer tăng tốc, consumer giảm năng lực, một partition bị nóng hoặc downstream chậm.

Các hướng xử lý:

1. **Tìm nút thắt:** so sánh lag theo partition, thời gian handler, database latency, API rate limit, error rate và concurrency.
2. **Tăng năng lực consumer có kiểm soát:** tăng concurrency hoặc batch throughput nếu dependency chịu được.
3. **Giảm công việc mỗi record:** tối ưu truy vấn, gom ghi database theo batch hoặc loại bỏ thao tác đồng bộ không cần thiết.
4. **Điều tiết đầu vào:** pause partition, giảm poll rate hoặc giới hạn event source mapping concurrency khi downstream quá tải.
5. **Xử lý partition skew:** xem key phân vùng có dồn phần lớn tải vào một partition hay không.
6. **Tách consumer chậm:** một consumer làm nhiều công việc không liên quan có thể được tách thành queue/subscription riêng.

Không tăng concurrency vô hạn. Mỗi instance Java có thể mở thêm connection, gọi API và tạo tải đồng thời. Khi database là bottleneck, scale out có thể làm lỗi tăng nhanh hơn. Cần đặt reserved/max concurrency, connection pool limit, batch size và timeout phù hợp với dependency.

### Batch size và batching window trong FaaS

Batch lớn giảm số invocation và overhead khởi tạo, nhưng làm tăng thời gian chờ để đủ batch, bộ nhớ cần thiết và số record bị phát lại khi một batch thất bại. Batch nhỏ giảm latency và blast radius nhưng có thể tăng invocation cost. Batching window cho phép đợi một khoảng thời gian để gom record; cần cân nhắc SLA độ trễ.

Với stream có thứ tự, một record lỗi có thể chặn tiến độ shard/partition nếu nền tảng retry cả batch hoặc giữ checkpoint ở record lỗi. Cần phân biệt lỗi tạm thời (có thể retry) và poison message (luôn thất bại do dữ liệu hoặc code). Poison message nên được ghi nhận đầy đủ vào DLQ/quarantine với event ID và nguyên nhân, rồi chỉ bỏ qua khi có chính sách nghiệp vụ được phê duyệt. Bỏ qua record mà không lưu dấu có thể tạo lỗ hổng dữ liệu khó phát hiện.

## 12. Retry, partial batch failure và checkpoint

Khi function xử lý batch, có ba hành vi phổ biến:

- **Retry toàn batch:** chỉ cần một record lỗi thì cả batch được giao lại. Những record đã thành công có thể chạy lần nữa; consumer phải idempotent.
- **Partial batch response:** function trả danh sách record lỗi hoặc vị trí lỗi đầu tiên theo giao thức nền tảng; mapping chỉ retry phần cần thiết hoặc giữ checkpoint trước vị trí lỗi.
- **Bisect batch:** nền tảng chia batch lỗi thành các phần nhỏ hơn để cô lập record gây lỗi; cách này tăng số invocation nhưng giúp tìm poison record.

Không phải nền tảng nào cũng hỗ trợ cùng cơ chế. Có nền tảng chỉ cho báo cáo sequence number đầu tiên thất bại trong shard; có nền tảng nhận danh sách message ID; có nền tảng quản lý retry ở cấp invocation. Adapter cần trả đúng cấu trúc được trigger yêu cầu. Nếu function trả thành công trong khi một record chưa được lưu, nền tảng có thể checkpoint qua record đó.

Một quy trình an toàn cho batch:

1. Parse và validate từng record.
2. Xử lý record bằng khóa idempotency.
3. Chỉ đánh dấu record thành công sau khi hiệu ứng bền vững.
4. Thu thập lỗi có thể retry và lỗi dữ liệu cần quarantine.
5. Trả partial failure theo semantics của nền tảng.
6. Theo dõi retry count, DLQ và checkpoint để tránh poison message chặn shard vô hạn.

Với stream yêu cầu thứ tự, không được xác nhận record sau một record thất bại nếu việc đó khiến checkpoint nhảy qua record lỗi. Có thể xử lý các record độc lập ở partition khác, nhưng tiến độ trong một partition phải tuân theo quy tắc liên tục.

## 13. Idempotency và ranh giới giữa dữ liệu nghiệp vụ với checkpoint

Thông thường, thay đổi database nghiệp vụ và commit offset/checkpoint nằm ở hai hệ thống khác nhau. Không có một transaction nguyên tử bao trùm cả hai. Vì vậy, hai tình huống có thể xảy ra:

- Database commit thành công, nhưng consumer chết trước khi commit checkpoint: record được giao lại.
- Checkpoint commit thành công trước khi database commit: record có thể bị bỏ qua dù thay đổi nghiệp vụ chưa được lưu.

Hãy chọn thứ tự database trước, checkpoint sau để tránh mất record; sau đó dùng idempotency để xử lý giao lại. Có thể lưu `eventId` trong bảng inbox/processed-events với unique constraint cùng transaction cập nhật dữ liệu nghiệp vụ. Nếu cần phát sự kiện tiếp theo sau khi cập nhật, dùng transactional outbox trong cùng transaction đó.

Với Kafka-to-Kafka, Kafka transactions có thể phối hợp ghi output và commit offset trong cùng transaction theo cấu hình phù hợp. Nhưng transaction đó không tự bao trùm một database hoặc API bên ngoài. Với Kinesis, Pub/Sub hoặc managed event source mapping, hãy dùng cơ chế idempotency của ứng dụng và semantics checkpoint/ack mà dịch vụ cung cấp.

Không hứa hẹn “exactly once” chỉ vì broker có transaction hoặc function có checkpoint. Cần chỉ rõ exactly-once áp dụng ở ranh giới nào: đọc, ghi trong broker, cập nhật database hay hiệu ứng bên ngoài. Với thanh toán, email hoặc gọi API đối tác, idempotency key và đối soát vẫn rất quan trọng.

## 14. Vận hành Java consumer trên serverless

Khi Java function được trigger theo batch stream, cần thiết kế phù hợp với thời hạn invocation:

- Timeout function phải đủ cho batch lớn nhất trong điều kiện downstream chậm hợp lý.
- Batch size và concurrency phải nằm trong khả năng database và API phụ thuộc.
- Không bắt đầu công việc async rồi trả response thành công trước khi công việc hoàn tất hoặc được lưu vào một queue bền vững khác.
- Nếu timeout xảy ra, giả định một phần record có thể đã được xử lý và sẽ được giao lại.
- Không lưu checkpoint trong biến static hoặc file tạm của instance.
- Dùng connection pool có giới hạn và tái sử dụng client an toàn khi runtime cho phép.
- Với batch lớn, cân nhắc memory, payload size và thời gian deserialize.
- Khi deploy code mới, bảo đảm schema cũ vẫn được đọc trong khoảng thời gian record cũ còn trong retention.

Function có thể bị cold start hoặc bị terminate giữa lúc xử lý. Checkpoint do nền tảng quản lý hoặc consumer group lưu phải là nguồn tiến độ chuẩn. Instance mới tiếp tục từ checkpoint và có thể nhận lại một phần batch trước đó. Do đó, handler cần có thể chạy lại an toàn.

Nếu function chỉ xử lý nhanh rồi ghi sang database, hãy đo thời gian theo batch và record. Nếu một record gọi API ngoài có latency biến động, cân nhắc queue trung gian hoặc workflow để tách bước chậm khỏi consumer stream, tránh giữ partition lâu và làm tăng lag cho các record sau.

## 15. Replay và backfill có kiểm soát

Replay hữu ích khi sửa bug trong projection, xây dựng báo cáo mới hoặc phục hồi dữ liệu sau sự cố. Nhưng replay có thể phát lại hàng triệu record và làm tải downstream tăng mạnh.

Quy trình replay nên gồm:

1. Chọn khoảng offset/sequence hoặc thời gian cần đọc lại.
2. Tạo consumer group hoặc subscription riêng nếu cần bảo vệ tiến độ production.
3. Xác định schema version của dữ liệu cũ và kiểm tra consumer còn đọc được.
4. Dùng sink riêng hoặc khóa idempotency để không tạo tác động trùng lên nghiệp vụ đang chạy.
5. Giới hạn tốc độ replay để không làm quá tải database và API.
6. Đo lag, lỗi, record đã xử lý và checkpoint trong suốt quá trình.
7. Đối soát kết quả trước khi đưa dữ liệu replay vào luồng chính.

Nếu replay cùng group production, cần biết rõ thao tác reset offset ảnh hưởng toàn bộ partition và consumer đang hoạt động. Không chạy đồng thời hai nhóm consumer cùng ghi vào một projection nếu không có cơ chế chống ghi đè hoặc phân vùng dữ liệu rõ ràng.

## 16. Quan sát lag và checkpoint

Một dashboard vận hành nên kết hợp metric của broker, consumer runtime và nghiệp vụ:

| Metric | Mục đích | Gợi ý cảnh báo |
|---|---|---|
| Lag theo partition/shard | Phát hiện partition bị nghẽn | Lag tăng liên tục hoặc một partition lệch lớn so với phần còn lại |
| Age of oldest record | Đo độ trễ thực tế | Vượt SLA xử lý của nghiệp vụ |
| Consumer throughput | So sánh năng lực xử lý với tốc độ đến | Throughput thấp hơn arrival rate trong thời gian dài |
| Processing latency p95/p99 | Tìm record hoặc dependency chậm | Vượt ngân sách latency |
| Commit/checkpoint age | Phát hiện consumer xử lý nhưng không lưu tiến độ | Thời gian từ lần checkpoint gần nhất vượt ngưỡng |
| Retry và failure count | Phát hiện lỗi tạm thời hoặc poison message | Retry tăng nhanh hoặc lặp cùng event ID |
| DLQ/quarantine depth | Theo dõi record không thể tự xử lý | Có record mới hoặc tuổi record tăng |
| Rebalance/lease changes | Phát hiện group không ổn định | Rebalance dày hoặc shard liên tục đổi owner |
| Function concurrency và timeout | Đánh giá giới hạn serverless | Concurrency chạm trần, timeout tăng |

Log có cấu trúc nên chứa `eventId`, topic/stream, partition/shard, offset/sequence, consumer group, correlation ID, thời gian xử lý và kết quả. Không ghi payload nhạy cảm. Với một record bị xử lý nhiều lần, có thể đối chiếu event ID và checkpoint để xác định lỗi nằm ở handler, commit hay trigger mapping.

Đặt cảnh báo theo ngữ nghĩa nghiệp vụ. Queue email có thể chấp nhận trễ vài phút; luồng cập nhật số dư hoặc fraud detection có thể cần cảnh báo sau vài giây. Không dùng một ngưỡng lag records chung cho mọi stream có kích thước record và SLA khác nhau.

## 17. Ví dụ tình huống: consumer ngừng 10 phút

Giả sử một stream nhận 800 record/giây. Consumer dừng 10 phút nên tích lũy khoảng:

\[
800 \times 10 \times 60 = 480.000 \text{ record}
\]

Sau khi khởi động, consumer xử lý được 1.200 record/giây trong khi producer tiếp tục gửi 800 record/giây. Tốc độ giảm backlog là 400 record/giây, nên thời gian bắt kịp ước tính:

\[
480.000 / (1.200 - 800) = 1.200 \text{ giây} = 20 \text{ phút}
\]

Trong thời gian này, consumer vẫn đang xử lý record mới nhưng age lag có thể còn cao. Nếu SLA yêu cầu dữ liệu cập nhật trong 2 phút, cần tăng năng lực xử lý hoặc điều tiết producer, đồng thời kiểm tra dependency có chịu được tải cao hơn không. Nếu partition chỉ có 4 shard và mỗi shard đã đạt throughput tối đa, tăng số function instance vượt quá số shard sẽ không làm stream xử lý nhanh hơn.

Nếu checkpoint cuối cùng đã lưu trước khi consumer dừng, khi resume consumer đọc lại từ vị trí đó. Một số record trước khi dừng có thể đã ghi vào database nhưng chưa commit checkpoint, nên xuất hiện duplicate. Inbox/idempotency giúp những record đó không tạo hiệu ứng nghiệp vụ lần thứ hai. Sau khi lag về mức bình thường, tiếp tục theo dõi age lag, retry và DLQ để chắc chắn không còn record bị mắc kẹt.

## 18. Quy trình thiết kế checkpoint và phục hồi

Khi triển khai một consumer mới, hãy xác định các quyết định sau trước khi chạy production:

1. **Định nghĩa đơn vị tiến độ:** offset theo partition, sequence theo shard hay ack từng message.
2. **Chọn nơi lưu checkpoint:** broker/consumer group, managed event source mapping hay checkpoint store riêng.
3. **Xác định thời điểm commit:** sau khi database commit, sau khi output được ghi hoặc theo partial batch contract.
4. **Thiết kế idempotency:** dùng event ID, unique constraint hoặc idempotency key cho tác động ngoài.
5. **Quyết định mức song song:** theo partition/shard, bảo đảm checkpoint không vượt qua record chưa xong.
6. **Định nghĩa retry và poison message:** số lần retry, backoff, DLQ/quarantine và điều kiện bỏ qua có kiểm soát.
7. **Đặt retention và recovery policy:** xác định khoảng gián đoạn tối đa, cách xử lý offset hết hạn và nguồn phục hồi.
8. **Tính catch-up capacity:** đo arrival rate, successful throughput và thời gian bắt kịp backlog.
9. **Kiểm thử lỗi:** dừng function giữa xử lý và commit, gây lỗi database, rebalance, hết retention và replay.
10. **Thiết lập quan sát:** lag theo partition, age, checkpoint age, retry, DLQ, concurrency và trạng thái nghiệp vụ.

## 19. Checklist trước khi đưa consumer vào production

- [ ] Đã hiểu semantics ack/offset/checkpoint của queue hoặc stream đang dùng.
- [ ] Lag được đo theo partition/shard và có cả age lag phù hợp SLA.
- [ ] Tốc độ xử lý thành công lớn hơn tốc độ đến trong điều kiện tải dự kiến.
- [ ] Checkpoint chỉ tiến sau khi hiệu ứng nghiệp vụ đã bền vững.
- [ ] Commit offset theo vị trí kế tiếp cần đọc và không vượt qua record chưa hoàn tất.
- [ ] Consumer idempotent để chịu được duplicate sau crash/rebalance/retry.
- [ ] Xử lý song song vẫn giữ checkpoint liên tục theo partition/shard.
- [ ] Auto commit được tắt hoặc được cấu hình đúng theo semantics cần thiết.
- [ ] Resume policy rõ khi không có checkpoint hoặc checkpoint hết retention.
- [ ] Replay/backfill có group hoặc luồng riêng và giới hạn tải phù hợp.
- [ ] Retry, partial batch failure, DLQ và poison message có quy trình rõ.
- [ ] Concurrency, batch size, timeout và connection pool phù hợp với dependency.
- [ ] Rebalance/graceful shutdown không commit sau khi mất quyền sở hữu partition.
- [ ] Có cảnh báo lag, age, checkpoint age, retry, DLQ và timeout.
- [ ] Đã kiểm thử crash giữa side effect và checkpoint, đồng thời xác minh không mất dữ liệu.

## Kết luận

Consumer lag cho biết consumer đang cách đầu stream bao xa; checkpoint xác định vị trí có thể tiếp tục đọc sau gián đoạn. Thiết kế đúng cần commit sau khi kết quả nghiệp vụ đã bền vững, xử lý duplicate bằng idempotency và chỉ checkpoint qua phần dữ liệu đã hoàn tất liên tục. Trong serverless, cần phối hợp batch, concurrency, timeout, partition/shard và session/lease của nền tảng để scale mà không làm mất tiến độ. Retention, replay, backpressure và giám sát age lag giúp hệ thống phục hồi có kiểm soát khi consumer chậm hoặc dừng hoạt động.
