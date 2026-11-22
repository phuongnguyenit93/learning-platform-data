# auto.offset.reset khi chưa có offset hoặc offset không còn hợp lệ

## Mục tiêu bài học

Kafka consumer dùng committed offset của consumer group để tiếp tục đọc sau khi restart. Nhưng một group mới có thể chưa có offset, offset cũ có thể đã hết hạn hoặc log có thể bị retention xóa qua vị trí consumer cần đọc. Trong các tình huống đó, consumer cần một chính sách xác định vị trí bắt đầu. Cấu hình `auto.offset.reset` quyết định consumer sẽ đọc từ dữ liệu sớm nhất còn lại, bắt đầu ở cuối log hay dừng để ứng dụng xử lý rõ ràng.

Sau bài học, bạn có thể:

- Giải thích khi nào Kafka áp dụng `auto.offset.reset`.
- Phân biệt group chưa có committed offset với committed offset nằm ngoài phạm vi log hiện tại.
- Chọn `earliest`, `latest`, `none` hoặc `by_duration` khi phiên bản client hỗ trợ.
- Hiểu vì sao `earliest` không có nghĩa luôn đọc từ offset 0 và vì sao `latest` có thể bỏ qua dữ liệu cũ.
- Phân biệt auto offset reset với commit offset, topic retention và thao tác replay thủ công.
- Cấu hình Java consumer và kiểm tra hành vi khi group mới, topic mới hoặc dữ liệu đã bị xóa.
- Reset offset bằng Kafka CLI một cách có kiểm soát.

## 1. Vì sao consumer cần chính sách reset offset?

Kafka consumer group lưu tiến độ đọc theo từng topic-partition. Khi consumer khởi động, nó thường lấy committed offset của group rồi tiếp tục đọc từ vị trí đó. Tuy nhiên, đôi khi không có vị trí hợp lệ để tiếp tục:

- Group mới chưa từng commit offset cho partition.
- Group cũ không còn committed offset vì metadata offset đã hết thời gian lưu.
- Topic có partition mới mà group chưa có offset cho partition đó.
- Retention đã xóa các segment chứa offset mà group đã commit.
- Log bị truncate hoặc thay đổi sau sự cố, khiến offset đã lưu không còn nằm trong phạm vi hợp lệ.

Khi consumer không có committed offset hợp lệ, `auto.offset.reset` chỉ định cách tìm vị trí bắt đầu thay thế.

Ví dụ một partition có trạng thái:

```text
Partition orders-0

Log start offset                         Log end offset
       500                                      900
        |----------------------------------------|
        500 ... 899: các offset còn trong log

Group A committed offset = 650  -> hợp lệ, tiếp tục từ 650
Group B committed offset = none -> dùng auto.offset.reset
Group C committed offset = 420  -> out of range, dùng auto.offset.reset
```

Committed offset thường biểu thị offset kế tiếp cần đọc. Vì vậy group A commit 650 sẽ tiếp tục đọc từ 650; nó không có nghĩa record offset 650 đã được xử lý rồi.

## 2. Khi nào `auto.offset.reset` được áp dụng?

### 2.1. Group chưa có committed offset

Trường hợp phổ biến nhất là một `group.id` mới. Group chưa có tiến độ đọc được lưu cho partition nên consumer phải chọn vị trí ban đầu.

Ví dụ:

```properties
group.id=order-projection-v2
auto.offset.reset=earliest
```

Nếu group `order-projection-v2` chưa từng commit offset, consumer bắt đầu ở offset sớm nhất còn có thể đọc của từng partition. Việc đổi `group.id` tạo một tiến độ tiêu thụ độc lập; committed offset của group cũ không tự động được sao chép sang group mới.

### 2.2. Committed offset không còn nằm trong log

Giả sử group đã commit offset 420, nhưng topic retention đã xóa segment cũ và log start offset hiện là 500. Consumer không thể đọc offset 420 vì dữ liệu tương ứng không còn trong log.

Khi client phát hiện offset đã lưu không còn hợp lệ, `auto.offset.reset` quyết định vị trí thay thế:

- `earliest`: chuyển đến log start offset hiện tại.
- `latest`: chuyển đến log end offset hiện tại.
- `none`: không tự chọn; báo lỗi để ứng dụng hoặc operator quyết định.

Việc reset không khôi phục được record đã bị retention xóa. Nếu cần dữ liệu cũ hơn log start offset, phải lấy từ bản lưu trữ khác, backup hoặc nguồn dữ liệu gốc.

### 2.3. Partition mới trong topic hiện có

Giả sử topic `orders` ban đầu có bốn partition và consumer group đã commit offset cho cả bốn. Sau đó topic được tăng lên sáu partition. Group có thể nhận thêm partition 4 và 5 nhưng chưa có committed offset cho hai partition mới.

`auto.offset.reset` được áp dụng cho những partition chưa có offset hợp lệ. Các partition cũ vẫn tiếp tục từ committed offset của chúng. Không phải toàn bộ group đều bị đưa về đầu hoặc cuối log chỉ vì topic có partition mới.

### 2.4. Offset của group hết hạn khác dữ liệu topic hết hạn

Kafka quản lý record trong topic và committed offset của consumer group bằng hai cơ chế retention khác nhau:

- **Topic retention:** xóa log segment theo thời gian/dung lượng hoặc cleanup policy. Nó làm record cũ không còn đọc được.
- **Consumer offset retention:** lưu committed offset và metadata group theo chính sách broker. Group không hoạt động đủ lâu có thể mất committed offset dù record trong topic vẫn còn.

Nếu committed offset của group hết hạn nhưng record vẫn còn, lần chạy tiếp theo có thể dùng `auto.offset.reset` để chọn vị trí mới. Nếu record đã bị xóa nhưng committed offset vẫn còn, offset đó có thể trở thành out of range và cũng kích hoạt chính sách reset.

Không nhầm thời gian giữ record của topic với thời gian giữ offset của group.

## 3. Các giá trị của `auto.offset.reset`

### 3.1. `earliest`

`earliest` yêu cầu consumer bắt đầu từ offset sớm nhất còn có thể đọc trong partition.

Ví dụ:

```java
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
```

Phù hợp khi:

- Group mới cần xử lý lại toàn bộ dữ liệu hiện còn trong topic.
- Consumer cần dựng projection hoặc cache từ event còn được lưu.
- Môi trường lab muốn quan sát các record đã được produce trước khi consumer khởi động.

Điểm cần nhớ:

- `earliest` không đảm bảo bắt đầu từ offset 0. Log start offset có thể đã lớn hơn 0 do retention, compaction hoặc thao tác quản trị.
- `earliest` không lấy lại record đã bị xóa.
- Với compacted topic, các phiên bản cũ của cùng key có thể đã bị compaction loại bỏ; đọc từ earliest chỉ trả dữ liệu còn tồn tại trong log.
- Nếu group đã có committed offset hợp lệ, consumer tiếp tục từ offset đó; `earliest` không tự rewind group mỗi lần restart.

### 3.2. `latest`

`latest` yêu cầu consumer bắt đầu từ cuối log hiện tại khi không có offset hợp lệ. Consumer bỏ qua những record đang có trước vị trí bắt đầu và đọc record mới được append sau đó.

Ví dụ:

```java
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
```

Phù hợp khi:

- Một consumer mới chỉ cần event phát sinh từ thời điểm nó bắt đầu hoạt động.
- Dữ liệu cũ không cần được xử lý bởi group mới.
- Ứng dụng có nguồn dữ liệu khác để dựng trạng thái hiện tại và Kafka chỉ dùng cho cập nhật mới.

Rủi ro lớn nhất là bỏ qua lịch sử. Nếu một group mới dùng `latest`, các event đã tồn tại trong topic trước khi consumer lấy vị trí ban đầu có thể không được group xử lý.

Ví dụ:

```text
Trước khi group mới bắt đầu:
  P0: offset 0 ... 99 đã có trong log

auto.offset.reset=latest
  -> vị trí bắt đầu được đặt ở cuối log, ví dụ 100

Sau đó producer ghi offset 100, 101, 102
  -> group đọc các record mới từ vị trí bắt đầu
```

Trong môi trường nhiều producer/consumer, thời điểm consumer lấy end offset và thời điểm producer ghi record mới có thể xen kẽ. Vì vậy, hãy kiểm tra hành vi thực tế nếu yêu cầu nghiệp vụ cần một ranh giới thời gian chính xác.

### 3.3. `none`

`none` yêu cầu consumer không tự chọn vị trí khi không có committed offset hợp lệ. Consumer báo lỗi để ứng dụng hoặc người vận hành đưa ra quyết định rõ ràng.

```java
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "none");
```

Phù hợp khi:

- Không được phép âm thầm bỏ qua lịch sử hoặc tự replay dữ liệu.
- Việc thiếu offset là một điều kiện cần operator điều tra.
- Hệ thống muốn kiểm soát rõ vị trí bắt đầu trước khi xử lý nghiệp vụ.

Ứng dụng cần bắt và xử lý lỗi phù hợp. Tùy trường hợp, client có thể báo lỗi không có offset hoặc offset nằm ngoài phạm vi log, chẳng hạn `NoOffsetForPartitionException` hoặc `OffsetOutOfRangeException`. Không nên chỉ log rồi tiếp tục vòng lặp như thể consumer đã có vị trí đọc hợp lệ.

### 3.4. `by_duration` trên các phiên bản hỗ trợ

Một số phiên bản Kafka client hỗ trợ giá trị `by_duration:<duration>` để đặt vị trí bắt đầu tương đối theo thời gian, ví dụ:

```java
props.put(
    ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
    "by_duration:PT1H"
);
```

Ví dụ biểu thị mong muốn bắt đầu từ dữ liệu trong khoảng một giờ gần đây, dựa trên timestamp index của partition. Cú pháp duration dùng định dạng ISO-8601. Tính năng và hành vi chi tiết phụ thuộc phiên bản Kafka client/broker; hãy xác nhận hỗ trợ trong tài liệu phiên bản đang triển khai.

`by_duration` vẫn là chính sách fallback khi không có offset hợp lệ. Nó không tự thay thế committed offset còn hợp lệ và cũng không thể đọc record đã bị retention xóa.

### 3.5. So sánh nhanh

| Giá trị | Vị trí bắt đầu khi không có offset hợp lệ | Rủi ro chính |
|---|---|---|
| `earliest` | Offset sớm nhất còn trong log | Có thể replay nhiều dữ liệu; lịch sử đã xóa không thể khôi phục |
| `latest` | Cuối log tại thời điểm reset | Có thể bỏ qua các record cũ đang còn trong topic |
| `none` | Không tự chọn; ném lỗi | Ứng dụng phải xử lý lỗi và quyết định thủ công |
| `by_duration:...` | Vị trí theo timestamp trong khoảng thời gian chỉ định, nếu phiên bản hỗ trợ | Kết quả phụ thuộc timestamp, dữ liệu còn giữ và hỗ trợ phiên bản |

Trong nhiều Kafka Java client, giá trị mặc định là `latest`; không nên phụ thuộc ngầm vào mặc định. Hãy khai báo tường minh để hành vi group mới được review và kiểm thử.

## 4. `auto.offset.reset` không phải lệnh replay mỗi lần khởi động

Một nhầm lẫn thường gặp là đặt `auto.offset.reset=earliest` rồi mong consumer luôn đọc lại từ đầu sau mỗi lần restart. Điều đó không đúng.

Ví dụ group `order-projection` đã commit offset 250:

```text
Lần chạy 1:
  committed offset = 250
  consumer đọc từ 250
  xử lý đến 299
  commit offset = 300

Lần chạy 2:
  committed offset = 300 vẫn hợp lệ
  consumer tiếp tục từ 300
  auto.offset.reset=earliest không được dùng
```

`auto.offset.reset` chỉ được dùng khi group không có committed offset hoặc offset đó không còn hợp lệ. Nếu muốn replay từ đầu trong khi committed offset hiện tại vẫn hợp lệ, cần chủ động reset offset, dùng group ID mới hoặc gọi API seek theo thiết kế ứng dụng.

### 4.1. Đổi group ID để có tiến độ độc lập

Đổi từ `order-projection` sang `order-projection-rebuild` tạo group mới. Group mới không kế thừa committed offset cũ và sẽ áp dụng `auto.offset.reset`.

Cách này hữu ích để chạy song song một pipeline rebuild, nhưng cần tính đến tải đọc tăng, side effect có thể lặp và retention của topic. Không đổi group ID mỗi lần deploy nếu mục tiêu là tiếp tục tiến độ cũ.

### 4.2. Dùng `seek()` khi cần điều khiển vị trí trong code

Ứng dụng có thể điều khiển vị trí đọc bằng `seek()` sau khi partition được assign:

```java
TopicPartition partition = new TopicPartition("orders", 0);
consumer.assign(List.of(partition));
consumer.seek(partition, 100L);
```

Ví dụ này minh họa manual assignment và seek đến offset 100. Nếu offset không còn hợp lệ, consumer vẫn cần xử lý lỗi phù hợp. Khi dùng group-managed `subscribe()`, thao tác seek phải diễn ra sau khi partition được assign, thường trong callback assignment hoặc sau khi `poll()` hoàn tất assignment.

`seek()` là chỉ dẫn vị trí trực tiếp cho consumer hiện tại; nó không giống việc thay đổi `auto.offset.reset` và cũng không tự commit vị trí mới cho group. Muốn vị trí được lưu cho lần chạy sau, ứng dụng cần commit offset theo chính sách.

## 5. Ví dụ Java: cấu hình `earliest`

Ví dụ dưới đây tạo consumer mới, dùng group ID riêng và đọc dữ liệu còn tồn tại từ đầu log mỗi partition khi group chưa có offset:

```java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-projection-rebuild");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders"));

    while (running) {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, String> record : records) {
            processOrderEvent(record.key(), record.value());
        }

        // Commit sau khi các record trong batch đã xử lý thành công.
        consumer.commitSync();
    }
}
```

`running` và `processOrderEvent` là phần logic của ứng dụng. Nếu một record lỗi và batch chưa được xử lý hoàn tất, không nên commit vượt qua record đó. Với xử lý song song, cần theo dõi offset hoàn tất liên tục theo từng partition thay vì commit toàn batch một cách mù quáng.

Vì `group.id` trong ví dụ là group mới, `earliest` sẽ được dùng nếu chưa có committed offset. Nếu chạy lại cùng group sau khi đã commit, consumer tiếp tục từ offset đã lưu thay vì tự đọc lại từ đầu.

## 6. Ví dụ chọn `latest` hoặc `none`

### 6.1. Chỉ nhận sự kiện mới

```java
props.put(ConsumerConfig.GROUP_ID_CONFIG, "live-notification-v1");
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
```

Group mới sẽ bắt đầu ở cuối log khi lấy vị trí ban đầu. Cấu hình này phù hợp nếu notification service chỉ cần event phát sinh sau khi group bắt đầu. Nếu notification cần gửi lại các thông báo chưa xử lý từ trước, `latest` có thể làm mất cơ hội xử lý các event cũ còn trong topic.

### 6.2. Buộc operator quyết định khi thiếu offset

```java
props.put(ConsumerConfig.GROUP_ID_CONFIG, "financial-ledger-reader");
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "none");
```

Với luồng dữ liệu tài chính, ứng dụng có thể muốn dừng khi không có vị trí đọc hợp lệ để operator xác minh dữ liệu và quyết định replay. Khi chọn `none`, cần có quy trình vận hành để:

1. Xác định topic-partition gặp lỗi.
2. Kiểm tra log start/end offset và committed offset hiện tại.
3. Xác định dữ liệu đã bị retention xóa hay group offset đã hết hạn.
4. Chọn offset bắt đầu có căn cứ.
5. Reset offset hoặc khôi phục dữ liệu theo quy trình được phê duyệt.

## 7. Log start offset, log end offset và out-of-range

Để hiểu reset, cần phân biệt ba giá trị:

- **Log start offset:** offset sớm nhất còn có thể đọc trong partition.
- **Log end offset:** vị trí kế tiếp sau record cuối cùng đã append vào log.
- **Committed offset:** vị trí kế tiếp mà consumer group đã lưu để tiếp tục đọc.

Ví dụ:

```text
Log start offset = 500
Committed offset = 420
Log end offset   = 900

             420        500                         900
              |          |                           |
              v          v                           v
          offset cũ   dữ liệu còn đọc được       cuối log
          đã bị xóa   500..899
```

Committed offset 420 thấp hơn log start 500 nên không còn hợp lệ. Consumer cần áp dụng `auto.offset.reset` hoặc báo lỗi nếu dùng `none`.

Một offset lớn hơn log end cũng có thể không hợp lệ, ví dụ sau khi log bị truncate hoặc trạng thái thay đổi. Không nên tự suy luận rằng mọi lỗi offset out of range đều do retention; hãy kiểm tra log start/end, broker log và lịch sử sự cố.

### 7.1. Offset gap không đồng nghĩa dữ liệu bị mất

Offset không nhất thiết liên tục theo những record mà ứng dụng quan sát. Transaction control record, aborted transaction, compaction hoặc các cơ chế log có thể tạo khoảng trống. Consumer có thể đọc record tiếp theo ở offset lớn hơn mà không có nghĩa record nghiệp vụ ở giữa đã bị retention xóa.

Khi điều tra, so sánh committed offset với log start/end và xem record thực tế có thể đọc. Không chỉ dựa vào việc hai offset không liền nhau để kết luận mất dữ liệu.

### 7.2. Compaction ảnh hưởng đến ý nghĩa của `earliest`

Với topic `cleanup.policy=compact`, Kafka có thể loại bỏ phiên bản cũ của cùng key trong quá trình compaction. `earliest` chỉ đưa consumer đến offset sớm nhất còn trong log; nó không tái tạo toàn bộ lịch sử thay đổi ban đầu.

Nếu cần event history đầy đủ, dùng topic có retention phù hợp hoặc lưu lịch sử ở hệ thống lưu trữ khác. Compacted topic thường phù hợp hơn để tái dựng trạng thái mới nhất theo key.

## 8. Reset offset thủ công bằng Kafka CLI

`auto.offset.reset` là fallback tự động. Khi cần chủ động replay một group đang có committed offset hợp lệ, operator có thể reset offset bằng Kafka CLI.

### 8.1. Xem trạng thái group trước khi reset

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

Ghi nhận topic, partition, current offset, log end offset và lag. Xác định rõ group nào cần replay; không reset nhầm group đang phục vụ production.

### 8.2. Lập kế hoạch reset về earliest

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection-rebuild \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

`--dry-run` hiển thị offset dự kiến mà không thực hiện thay đổi. Đọc kỹ kết quả cho từng partition và xác nhận phạm vi group/topic.

### 8.3. Thực thi sau khi xác nhận

Khi đã xác nhận kế hoạch và group không còn consumer active theo yêu cầu của công cụ, chạy:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection-rebuild \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
```

Sau đó mô tả group lại để xác minh committed offset mới. Khởi động consumer và theo dõi lag, throughput, lỗi xử lý trùng cùng tác động lên downstream.

### 8.4. Một số lựa chọn reset khác

| Tùy chọn | Mục đích |
|---|---|
| `--to-earliest` | Đặt về offset sớm nhất còn trong log |
| `--to-latest` | Đặt về cuối log hiện tại |
| `--to-offset <n>` | Đặt về offset cụ thể theo yêu cầu |
| `--shift-by <n>` | Dịch committed offset một số vị trí tương đối |
| `--to-datetime <timestamp>` | Chọn vị trí theo timestamp nếu topic có timestamp index phù hợp |

Reset offset là thao tác thay đổi tiến độ đọc của group. Replay có thể làm side effect chạy lại; skip có thể bỏ qua dữ liệu chưa xử lý. Dùng dry-run, dừng consumer group và có kế hoạch idempotency trước khi execute.

## 9. `auto.offset.reset` và các cấu hình liên quan

| Cấu hình/cơ chế | Vai trò | Có thay thế `auto.offset.reset` không? |
|---|---|---|
| `group.id` | Định danh tiến độ đọc của group | Không; group mới có thể chưa có offset |
| `enable.auto.commit` | Bật/tắt commit offset tự động | Không; quyết định cách lưu tiến độ sau khi đọc |
| `auto.commit.interval.ms` | Chu kỳ commit khi auto commit bật | Không; không chọn vị trí bắt đầu |
| `auto.offset.reset` | Chọn fallback khi offset không có/không hợp lệ | Đây là chính sách reset tự động |
| `seek()` | Đặt vị trí đọc cho consumer hiện tại | Có thể ghi đè vị trí đọc sau assignment nhưng không tự commit |
| CLI `--reset-offsets` | Operator thay đổi committed offset của group | Là thao tác quản trị chủ động |
| Topic retention | Xác định dữ liệu còn tồn tại bao lâu | Không; retention có thể khiến offset cũ thành invalid |

Điểm quan trọng: `auto.offset.reset` không commit offset thay cho ứng dụng. Sau khi consumer bắt đầu đọc, tiến độ chỉ được lưu theo chính sách auto commit hoặc manual commit.

## 10. Các lỗi và tình huống thường gặp

| Tình huống | Điều có thể xảy ra | Hướng xử lý |
|---|---|---|
| Group mới dùng `earliest` | Đọc dữ liệu còn lại từ đầu log mỗi partition | Kiểm tra retention và tải replay lên downstream |
| Group mới dùng `latest` | Bỏ qua các record đã có trước vị trí bắt đầu | Chỉ dùng khi nghiệp vụ chấp nhận chỉ nhận event mới |
| Group restart với committed offset hợp lệ | Tiếp tục từ offset đã commit | Không kỳ vọng `earliest` tự rewind |
| Committed offset thấp hơn log start | Offset out of range do dữ liệu cũ không còn | Chọn reset policy hoặc phục hồi từ nguồn lưu trữ khác |
| Offset group hết hạn nhưng topic còn dữ liệu | Group không có committed offset và dùng fallback | Xem lại group retention và chính sách reset |
| Topic tăng partition | Partition mới chưa có offset cho group | `auto.offset.reset` chỉ áp dụng cho partition mới |
| Dùng `none` nhưng không có quy trình vận hành | Consumer dừng với lỗi offset | Xây dựng runbook kiểm tra và reset có kiểm soát |
| Reset CLI khi consumer vẫn chạy | Consumer có thể commit lại offset hoặc hành vi cạnh tranh | Dừng group, dry-run, execute rồi xác minh |
| Replay dữ liệu vào hệ thống có side effect | Email, thanh toán hoặc cập nhật có thể lặp | Dùng event ID, idempotency key và kiểm soát replay |
| Dùng `earliest` trên compacted topic để mong lịch sử đầy đủ | Phiên bản cũ có thể đã bị compaction xóa | Chọn nguồn event history phù hợp |

## 11. Quy trình chọn chính sách reset

Trước khi chọn giá trị, hãy trả lời:

1. Đây là group mới hay group đang hoạt động có committed offset?
2. Group có cần xử lý dữ liệu cũ còn trong topic không?
3. Nếu offset đã hết hạn hoặc out of range, có được phép bỏ qua dữ liệu không?
4. Topic dùng `delete`, `compact` hay cả hai?
5. Retention của topic có đủ cho thời gian gián đoạn và replay không?
6. Nếu chọn `earliest`, downstream có chịu được lượng dữ liệu phát lại không?
7. Nếu chọn `latest`, nghiệp vụ có chấp nhận bỏ qua event đang còn trong log không?
8. Nếu chọn `none`, ai chịu trách nhiệm điều tra và quyết định offset?
9. Có cần reset theo timestamp hoặc offset cụ thể thay vì fallback tự động không?
10. Consumer có idempotent để chịu được replay không?

Gợi ý lựa chọn:

- Chọn `earliest` cho group cần đọc lại dữ liệu còn lưu hoặc rebuild trạng thái.
- Chọn `latest` cho group chỉ cần sự kiện mới và đã có nguồn trạng thái ban đầu khác.
- Chọn `none` khi thiếu offset cần dừng để operator xác minh.
- Chọn `by_duration` nếu client hỗ trợ và yêu cầu bắt đầu theo một khoảng thời gian tương đối.

Đây là lựa chọn theo nghiệp vụ, không phải quy tắc áp dụng chung cho mọi topic.

## 12. Checklist vận hành

- Khai báo `auto.offset.reset` tường minh trong cấu hình consumer.
- Giữ `group.id` ổn định nếu cần tiếp tục tiến độ cũ qua restart/deploy.
- Dùng group ID mới có chủ đích khi muốn một tiến độ tiêu thụ độc lập.
- Phân biệt committed offset với log start và log end offset.
- Xác nhận `earliest` nghĩa là offset sớm nhất còn tồn tại, không nhất thiết là 0.
- Xác nhận `latest` có thể bỏ qua dữ liệu cũ còn trong topic.
- Không coi `auto.offset.reset` là lệnh replay cho mỗi lần khởi động.
- Thiết kế retention đủ cho consumer lag và yêu cầu replay.
- Theo dõi offset out of range, group offset expiry và consumer lag.
- Với `none`, có runbook xử lý lỗi và chọn offset.
- Với reset CLI, dừng group, chạy `--dry-run`, xác nhận rồi mới `--execute`.
- Bảo đảm downstream idempotent trước khi replay dữ liệu cũ.

## 13. Câu hỏi tự kiểm tra

1. Kafka áp dụng `auto.offset.reset` trong những tình huống nào?
2. Vì sao group mới chưa có committed offset cần chính sách chọn vị trí bắt đầu?
3. `earliest` có luôn đưa consumer về offset 0 không? Vì sao?
4. `latest` có thể làm mất cơ hội xử lý những record nào đối với group mới?
5. Vì sao `auto.offset.reset=earliest` không làm group đọc lại từ đầu sau mỗi lần restart?
6. Committed offset 420 thấp hơn log start 500 sẽ tạo ra tình huống gì?
7. Topic retention và consumer offset retention khác nhau như thế nào?
8. Khi topic tăng partition, vì sao reset policy chỉ áp dụng cho partition chưa có offset hợp lệ?
9. `none` phù hợp với loại yêu cầu vận hành nào?
10. `by_duration` có ý nghĩa gì và cần lưu ý điều gì về phiên bản?
11. Khác biệt giữa `auto.offset.reset`, `seek()` và CLI `--reset-offsets` là gì?
12. Vì sao cần `--dry-run` và dừng consumer group trước khi reset offset?

## Kết luận

`auto.offset.reset` là chính sách fallback khi consumer group chưa có committed offset hoặc offset đã lưu không còn hợp lệ. `earliest` đọc từ dữ liệu sớm nhất còn trong log, `latest` bắt đầu ở cuối log, `none` yêu cầu ứng dụng xử lý lỗi rõ ràng và `by_duration` có thể chọn vị trí theo thời gian trên các phiên bản hỗ trợ. Cấu hình này không rewind một group đang có offset hợp lệ, không khôi phục dữ liệu đã bị retention xóa và không thay thế thao tác commit/reset chủ động. Hiểu đúng các ranh giới đó giúp consumer replay có kiểm soát và tránh vô tình bỏ qua hoặc xử lý lại dữ liệu.
