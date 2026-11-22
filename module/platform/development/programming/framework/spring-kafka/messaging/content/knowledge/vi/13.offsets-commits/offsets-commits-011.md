# Reset offset của consumer group

Kafka lưu tiến độ đọc của mỗi consumer group theo từng topic-partition. Reset offset là thao tác thay đổi vị trí đã commit của group để consumer đọc lại dữ liệu cũ hoặc bỏ qua một đoạn dữ liệu. Đây là thao tác vận hành có ảnh hưởng trực tiếp tới những record mà ứng dụng sẽ xử lý tiếp theo.

Với Spring Kafka, listener container đọc tiếp từ offset đã commit của group. Vì vậy, muốn tua lại hoặc đưa group tới vị trí khác, cần thay đổi committed offset của group theo cách có kiểm soát. Công cụ Kafka CLI là lựa chọn phổ biến; Kafka `AdminClient` cũng cung cấp API để thay đổi offset bằng code.

## 1. Offset của consumer group biểu diễn điều gì?

Offset được quản lý riêng cho từng cặp topic và partition. Consumer group có thể có tiến độ khác nhau trên cùng một topic vì mỗi group lưu offset độc lập.

Ví dụ:

```text
Topic orders
  Partition 0: record offsets 0, 1, 2, 3, 4, ...
  Partition 1: record offsets 0, 1, 2, 3, 4, ...

Group order-projection
  orders-0 -> committed offset 105
  orders-1 -> committed offset 82

Group order-audit
  orders-0 -> committed offset 70
  orders-1 -> committed offset 82
```

Hai group có thể đọc cùng topic nhưng tiến độ độc lập. Reset offset cho `order-projection` không làm thay đổi offset của `order-audit`.

**Committed offset thường là vị trí tiếp theo cần đọc**, không phải offset cuối cùng đã xử lý. Nếu consumer xử lý record offset `104` thành công rồi commit `105`, lần đọc tiếp theo bắt đầu tại `105`.

Kafka lưu group offsets trong internal topic `__consumer_offsets`. Reset offset thay đổi metadata tiến độ của group; nó không xóa record khỏi topic nghiệp vụ.

## 2. Khi nào cần reset offset?

Một số tình huống thường gặp:

- **Replay dữ liệu:** cần chạy lại consumer từ đầu hoặc từ một mốc lịch sử để dựng lại read model.
- **Sửa lỗi xử lý:** consumer đã xử lý sai một khoảng dữ liệu và cần chạy lại sau khi triển khai bản sửa.
- **Bỏ qua dữ liệu không còn cần thiết:** muốn đưa group tới cuối log để chỉ nhận record mới phát sinh.
- **Kiểm thử hoặc diễn tập:** cần đưa group về một vị trí xác định để tái tạo kịch bản.
- **Khôi phục sau sự cố:** cần đặt lại tiến độ đọc sau khi đối chiếu dữ liệu và quyết định điểm tiếp tục.

Trước khi reset, phải xác định mục tiêu là đọc lại hay bỏ qua. Reset về offset nhỏ hơn thường làm phát sinh replay; reset về offset lớn hơn có thể khiến group bỏ qua record chưa xử lý.

## 3. Phân biệt reset offset với auto.offset.reset

Hai cơ chế này liên quan tới vị trí bắt đầu đọc nhưng không giống nhau:

| Cơ chế | Khi nào có hiệu lực | Tác động |
|---|---|---|
| Reset committed offset | Người vận hành hoặc Admin API chủ động thay đổi offset đã lưu của group | Ghi vị trí mới cho từng topic-partition của group |
| `auto.offset.reset` | Group không có committed offset hợp lệ, hoặc offset đã lưu không còn trong phạm vi log có thể đọc | Chọn vị trí bắt đầu thay thế như `earliest`, `latest` hoặc báo lỗi với `none` |

Ví dụ, đổi cấu hình Spring Kafka từ `latest` sang `earliest` không tự tua lại một group đã có committed offset hợp lệ. Consumer vẫn tiếp tục từ offset đã commit.

Ngược lại, reset offset bằng Kafka CLI sẽ thay đổi vị trí group đã lưu. Sau khi consumer khởi động lại và tham gia group, nó đọc từ vị trí mới, miễn là offset đó còn hợp lệ theo trạng thái log.

`auto.offset.reset` không phải công cụ quản trị để tua lại một group đang hoạt động. Hãy dùng reset-offsets hoặc Admin API khi cần thay đổi committed offset có chủ đích.

## 4. Điều kiện quan trọng: consumer group phải inactive

Trước khi reset bằng Kafka CLI hoặc `AdminClient`, hãy dừng toàn bộ consumer đang tham gia group cần thay đổi. Kafka yêu cầu group ở trạng thái không có member hoạt động cho thao tác reset offset. Nếu còn instance đang chạy, lệnh reset có thể bị từ chối; trong trường hợp khác, consumer còn hoạt động có thể tiếp tục commit offset và ghi đè vị trí vừa reset.

Quy trình an toàn thường là:

1. Xác định chính xác `group.id` và các topic-partition bị ảnh hưởng.
2. Dừng listener container hoặc triển khai toàn bộ instance của dịch vụ đang dùng group đó.
3. Xác minh group không còn consumer member hoạt động.
4. Chạy reset ở chế độ xem trước và kiểm tra kết quả cho từng partition.
5. Thực thi reset sau khi xác nhận vị trí đích.
6. Khởi động lại consumer và theo dõi lag, record được replay hoặc bị bỏ qua.

Với ứng dụng Spring Kafka, có thể dừng container qua `KafkaListenerEndpointRegistry` nếu mọi consumer của group nằm trong instance đó. Nếu group được dùng bởi nhiều pod, service hoặc ứng dụng, phải dừng tất cả thành viên trên toàn cụm. Dừng một listener trong một instance không đủ nếu còn consumer khác cùng group.

## 5. Kiểm tra trạng thái group trước khi reset

Dùng Kafka CLI để xem consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

Kết quả thường hiển thị topic, partition, current offset, log end offset, lag và consumer ID/host/client ID khi có thành viên hoạt động.

Kiểm tra danh sách group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
```

`--list` chỉ xác nhận group tồn tại, không chứng minh group đã inactive. Dùng kết quả `--describe` để kiểm tra consumer ID/member; các phiên bản CLI hỗ trợ `--state` có thể hiển thị trạng thái group rõ hơn.

Hãy xác nhận:

- Tên group đúng với dịch vụ cần điều chỉnh.
- Topic và partition trong kết quả đúng phạm vi dự kiến.
- Current offset và log end offset đã được ghi nhận để so sánh.
- Group không còn consumer member hoạt động trước khi thực thi reset.
- Không có quy trình triển khai hoặc autoscaling tự động khởi động lại consumer trong lúc thao tác.

## 6. Xem trước reset bằng --dry-run

Ví dụ đưa group `order-projection` về offset sớm nhất còn được lưu của topic `orders`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

`--dry-run` tính và hiển thị offset đích mà không ghi thay đổi vào group. Hãy đọc kết quả cho từng partition trước khi thực thi.

Khi đã xác nhận, chạy lại với `--execute`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
```

Nên luôn dùng `--dry-run` trước. Đừng chạy `--execute` chỉ vì lệnh không báo lỗi cú pháp; phải kiểm tra đúng group, topic, partition và số lượng record sẽ được đọc lại hoặc bỏ qua.

Các ví dụ dùng `localhost:9092` để minh họa. Trong môi trường thật, thay bằng bootstrap server và thêm cấu hình bảo mật phù hợp với cụm Kafka.

## 7. Các chiến lược reset offset thường dùng

Kafka CLI cung cấp nhiều cách chọn vị trí đích. Tên tùy chọn có thể khác theo phiên bản Kafka; hãy kiểm tra `kafka-consumer-groups.sh --help` của đúng bản cài đặt trước khi vận hành.

| Tùy chọn | Ý nghĩa | Tình huống |
|---|---|---|
| `--to-earliest` | Offset sớm nhất còn được lưu trong partition | Replay phần dữ liệu còn retention |
| `--to-latest` | Log end offset tại thời điểm reset | Bỏ qua dữ liệu hiện có, chỉ đọc dữ liệu mới |
| `--to-offset N` | Đặt vị trí đọc tới offset `N` | Bắt đầu từ một mốc đã xác định |
| `--shift-by N` | Dịch chuyển tương đối so với committed offset hiện tại | Lùi hoặc tiến một số offset |
| `--to-datetime` | Chọn offset dựa trên timestamp | Replay từ một mốc thời gian |
| `--by-duration` | Chọn offset theo khoảng thời gian lùi từ hiện tại | Replay dữ liệu của vài giờ hoặc vài ngày gần nhất |

### Reset về earliest

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

`earliest` là offset sớm nhất còn được lưu, không nhất thiết là `0`. Nếu retention đã xóa dữ liệu cũ, reset không thể khôi phục các record đó.

### Reset về latest

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-latest \
  --dry-run
```

Group sẽ bắt đầu từ log end offset được xác định khi reset. Những record đang có trong log trước mốc này sẽ bị bỏ qua bởi group đó. Các group khác không bị ảnh hưởng.

### Reset tới offset cụ thể

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-offset 500 \
  --dry-run
```

Offset `500` là vị trí tiếp theo mà consumer sẽ đọc. Trước khi thực thi, kiểm tra offset đích nằm trong phạm vi hợp lệ của partition và phù hợp với mốc nghiệp vụ cần replay. Không giả định mọi số offset đều tương ứng với một record hiện còn tồn tại; log có thể có khoảng trống do compaction hoặc retention.

### Dịch chuyển tương đối bằng shift-by

Lùi 100 offset so với vị trí hiện tại:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --shift-by -100 \
  --dry-run
```

Giá trị âm lùi về trước để replay; giá trị dương tiến về sau và có thể bỏ qua dữ liệu. Kiểm tra kết quả từng partition vì mỗi partition có current offset khác nhau. Không dùng shift lớn mà chưa đối chiếu earliest và end offset.

### Reset theo timestamp

Ví dụ chọn vị trí gần thời điểm bắt đầu ngày 1 tháng 11 năm 2026:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-datetime 2026-11-01T00:00:00.000 \
  --dry-run
```

Kafka tìm offset dựa trên timestamp của record trong từng partition. Kết quả phụ thuộc loại timestamp mà topic/broker sử dụng và dữ liệu còn lưu. Timestamp không phải lúc nào cũng là thời điểm nghiệp vụ tạo event; nếu cần replay theo thời điểm nghiệp vụ, phải xác minh ý nghĩa timestamp của record trước.

### Reset theo khoảng thời gian gần đây

Trên các phiên bản Kafka hỗ trợ `--by-duration`, ví dụ replay khoảng một ngày gần nhất:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --by-duration P1D \
  --dry-run
```

`P1D` là duration theo định dạng ISO-8601. Hãy kiểm tra phiên bản CLI hỗ trợ tùy chọn này và đọc offset kết quả trước khi thực thi.

## 8. Chỉ reset topic cần thiết

Có thể chỉ định một topic bằng `--topic orders` như các ví dụ trên. Nếu group subscribe nhiều topic, việc giới hạn phạm vi giúp tránh reset nhầm tiến độ của luồng khác.

Kafka CLI cũng hỗ trợ reset tất cả topic mà group có offset bằng tùy chọn `--all-topics` trên các phiên bản tương ứng:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --all-topics \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

`--all-topics` có phạm vi rộng và có thể ảnh hưởng nhiều luồng nghiệp vụ. Chỉ dùng khi đã liệt kê, kiểm tra toàn bộ topic-partition thuộc group và có phê duyệt vận hành phù hợp. Với thao tác thông thường, chọn rõ từng topic.

Nếu chỉ cần reset một vài partition, dùng cú pháp chọn partition được hỗ trợ bởi phiên bản Kafka CLI đang cài đặt hoặc dùng `AdminClient` với map `TopicPartition` tường minh. Không giả định cú pháp CLI giống nhau giữa mọi phiên bản; hãy kiểm tra phần trợ giúp của công cụ trước khi chạy.

## 9. Hiểu kết quả offset sau khi reset

Giả sử partition `orders-0` có:

```text
Current committed offset: 900
Log start offset:          100
Log end offset:           1200
```

Một số lựa chọn sẽ có ý nghĩa:

| Reset tới | Vị trí tiếp theo | Tác động |
|---|---:|---|
| Earliest | 100 | Replay record còn lưu từ offset sớm nhất |
| Latest | 1200 | Bỏ qua record hiện có và chờ record mới |
| Offset cụ thể | 500 | Tiếp tục từ vị trí 500 |
| Shift by -100 | 800 | Đọc lại khoảng từ vị trí 800 tới trước vị trí cũ |

Các con số trên chỉ minh họa. Log start offset và log end offset thay đổi theo retention, ghi mới và thao tác quản trị. Với compacted topic, offset có thể không liên tục vì record cũ đã bị loại bỏ.

Offset đích là vị trí đọc, không phải số record chắc chắn sẽ được xử lý. Muốn ước lượng replay volume, so sánh offset đích với log end offset và kiểm tra dữ liệu thực tế của từng partition.

## 10. Reset offset bằng Kafka AdminClient

Nếu cần tự động hóa một quy trình vận hành, Kafka `AdminClient` cung cấp `alterConsumerGroupOffsets(...)`. API này nhận group ID và map từ `TopicPartition` tới `OffsetAndMetadata`.

Ví dụ đặt group `order-projection` tại offset `500` của partition `0`:

```java
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

public class ConsumerGroupOffsetReset {

    public void resetOrdersPartition() throws Exception {
        Properties properties = new Properties();
        properties.put(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");

        try (AdminClient admin = AdminClient.create(properties)) {
            Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
                    new TopicPartition("orders", 0),
                    new OffsetAndMetadata(500L)
            );

            admin.alterConsumerGroupOffsets("order-projection", offsets)
                    .all()
                    .get(10, TimeUnit.SECONDS);
        }
    }
}
```

`OffsetAndMetadata(500L)` đặt vị trí tiếp theo cần đọc là `500`. Map chỉ chứa `orders-0`, nên ví dụ chỉ thay đổi offset của partition đó; các partition khác không được cập nhật bởi lời gọi này.

Group phải inactive khi thay đổi offset. API không cung cấp một chế độ dry-run tương đương CLI; nếu tự động hóa, hãy đọc offset hiện tại, tính offset đích, ghi log kế hoạch và yêu cầu bước xác nhận trước khi gọi `alterConsumerGroupOffsets`.

Ví dụ trên chỉ cấu hình bootstrap server để minh họa. Trong môi trường thật, `AdminClient` cần cấu hình security, credential và quyền quản trị phù hợp. Không đưa secret trực tiếp vào source code.

## 11. Đọc committed offset trước khi thay đổi bằng AdminClient

Trước khi ghi offset mới, có thể lấy committed offsets hiện tại để lập kế hoạch:

```java
Map<TopicPartition, OffsetAndMetadata> currentOffsets = admin
        .listConsumerGroupOffsets("order-projection")
        .partitionsToOffsetAndMetadata()
        .get(10, TimeUnit.SECONDS);

currentOffsets.forEach((partition, metadata) -> {
    System.out.printf(
            "%s-%d currentOffset=%d%n",
            partition.topic(),
            partition.partition(),
            metadata.offset());
});
```

Có thể kết hợp `AdminClient` với `listOffsets(...)` để kiểm tra log start/end offset trước khi lập kế hoạch reset. Không nên chọn offset chỉ dựa vào current committed offset; phải xác minh nó nằm trong phạm vi log có thể đọc và đúng với mục tiêu nghiệp vụ.

Một quy trình tự động nên tách thành hai pha:

1. **Plan:** đọc group offsets, log bounds, tính vị trí mới và xuất báo cáo cho từng partition.
2. **Apply:** sau khi được xác nhận, gọi `alterConsumerGroupOffsets` và đọc lại để xác minh.

Không chạy pha apply trong lúc consumer vẫn hoạt động. Cũng nên có audit log ghi người yêu cầu, group, topic-partition, offset cũ, offset mới, lý do và thời điểm thực hiện.

## 12. Reset offset khác với seek runtime trong Spring Kafka

Reset group offset thay đổi vị trí đã commit trên Kafka. `seek` thay đổi vị trí đọc hiện tại của một consumer đang chạy. Hai thao tác có mục đích gần nhau nhưng phạm vi và thời gian tồn tại khác nhau.

Spring Kafka hỗ trợ `ConsumerSeekAware` để listener điều khiển seek trong vòng đời consumer, ví dụ seek tới offset cụ thể hoặc về đầu partition khi partition được gán. Cơ chế này phù hợp với thao tác runtime có chủ đích trên consumer thread.

Ví dụ ý tưởng seek khi partition được assign:

```java
import java.util.Map;

import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.ConsumerSeekAware;
import org.springframework.kafka.listener.ConsumerSeekAware.ConsumerSeekCallback;
import org.springframework.stereotype.Component;

@Component
public class ReplayAwareListener implements ConsumerSeekAware {

    @Override
    public void registerSeekCallback(ConsumerSeekCallback callback) {
        // Lưu callback nếu cần seek từ một phương thức khác.
    }

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        // Chỉ minh họa: seek về đầu các partition vừa được gán.
        // Không bật hành vi này vô điều kiện trong production.
        // callback.seekToBeginning(assignments.keySet());
    }
}
```

Seek thay đổi vị trí đọc trong consumer hiện tại. Nếu group sau đó commit offset cũ hoặc một consumer khác tiếp quản partition, vị trí đọc có thể quay lại committed offset. Muốn thay đổi tiến độ bền vững của group, cần commit vị trí mới hoặc dùng reset-offsets/AdminClient khi group inactive.

Không đặt `seekToBeginning` vô điều kiện trong `onPartitionsAssigned` nếu không muốn replay mỗi lần rebalance. Callback này có thể được gọi nhiều lần trong vòng đời consumer.

## 13. Tác động tới xử lý nghiệp vụ khi replay

Reset offset về trước làm consumer xử lý lại record đã từng được giao. Nếu handler tạo hóa đơn, trừ tồn kho, gửi email hoặc gọi API bên ngoài, replay có thể lặp side effect.

Trước khi replay, hãy kiểm tra:

- Consumer có idempotent theo `eventId` hoặc khóa nghiệp vụ không?
- Database có unique constraint, inbox table hoặc cơ chế deduplication không?
- Các lệnh gọi dịch vụ ngoài có idempotency key không?
- Read model có thể rebuild từ đầu hay cần xóa/truncate dữ liệu trước?
- Retry topic, dead-letter topic hoặc luồng phát lại khác có tạo thêm bản sao không?
- Có thể chạy replay bằng group mới để không làm thay đổi tiến độ production hiện tại không?

Một cách an toàn cho việc dựng lại read model là tạo consumer group mới, đọc từ earliest còn lưu và ghi vào bảng/index mới. Sau khi xác minh kết quả, chuyển ứng dụng đọc sang read model mới. Cách này tránh thay đổi offset của group đang phục vụ traffic, nhưng cần đủ dung lượng và kế hoạch chuyển đổi dữ liệu.

## 14. Tác động khi reset về phía trước

Reset tới latest hoặc offset lớn hơn current có thể bỏ qua record chưa xử lý. Đây là quyết định mất cơ hội xử lý ở group đó; Kafka vẫn giữ record trong log cho tới khi retention/compaction loại bỏ chúng, và group khác vẫn có thể đọc.

Trước khi bỏ qua dữ liệu:

- Xác định chính xác khoảng offset sẽ bị bỏ qua trên từng partition.
- Kiểm tra có sự kiện nghiệp vụ quan trọng đang chờ xử lý hay không.
- Đối chiếu log end offset và consumer lag.
- Xác nhận group có thể bỏ qua đoạn dữ liệu đó hoặc dữ liệu đã được xử lý bằng quy trình khác.
- Ghi lại lý do và người phê duyệt thao tác.

Không dùng `--to-latest` như cách chữa consumer lag mà chưa tìm nguyên nhân. Nếu consumer chậm do lỗi downstream, reset tới latest chỉ che giấu vấn đề bằng cách bỏ qua backlog.

## 15. Retention, compaction và offset ngoài phạm vi

Reset không thể khôi phục dữ liệu đã bị Kafka xóa do retention. Nếu offset đích nhỏ hơn log start offset, consumer không thể đọc các record đã bị loại khỏi log. Hành vi tiếp theo có thể phụ thuộc `auto.offset.reset` nếu offset trở nên out of range.

Với compacted topic, Kafka giữ trạng thái mới nhất theo key và có thể xóa record cũ trong quá trình compaction. Offset không liên tục là điều bình thường; `--to-offset` chọn vị trí trong log chứ không đảm bảo có record mang đúng số offset đó.

Nếu cần replay dài hạn vượt retention của topic, cần nguồn lưu trữ khác như backup, object storage, database nguồn hoặc topic/archive được thiết kế cho mục tiêu đó. Reset offset chỉ thay đổi tiến độ consumer; nó không mở rộng retention.

## 16. Xác minh sau khi reset

Sau khi thực thi, đọc lại group offsets:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

Xác minh:

1. Current offset của từng topic-partition đã ở vị trí đích.
2. Không có consumer member ngoài dự kiến ghi đè offset trong quá trình thao tác.
3. Khi consumer khởi động lại, partition assignment hoàn tất và listener bắt đầu đọc.
4. Lag thay đổi theo mục tiêu replay hoặc skip.
5. Record được xử lý đúng, không tạo side effect trùng ngoài dự kiến.
6. Không phát sinh lỗi `OffsetOutOfRange`, lỗi deserialize hoặc lỗi downstream do dữ liệu lịch sử.

Nếu reset về earliest, lag thường tăng vì group phải đọc lại backlog. Nếu reset về latest, lag có thể về gần 0 tại thời điểm reset. Đây là tín hiệu quan sát, không thay thế việc xác minh nghiệp vụ.

## 17. Các lỗi thường gặp

**Group vẫn active:** dừng toàn bộ consumer cùng group rồi kiểm tra lại trạng thái trước khi reset.

**Reset nhầm group:** xác minh `group.id` trong cấu hình Spring Kafka, CLI và môi trường triển khai.

**Reset nhầm topic hoặc partition:** dùng `--topic` cụ thể và đọc kỹ kết quả dry-run trước khi execute.

**Nghĩ `auto.offset.reset=earliest` sẽ replay:** cấu hình này chỉ dùng khi không có committed offset hợp lệ. Dùng reset offset có chủ đích.

**Reset thành công nhưng consumer đọc từ vị trí khác:** kiểm tra consumer còn hoạt động có commit đè, listener có runtime seek, group có member khác hoặc offset đích không còn hợp lệ.

**Reset tới offset cũ nhưng dữ liệu đã hết retention:** Kafka không thể trả lại record đã bị xóa. Tìm nguồn backup hoặc nguồn dữ liệu chuẩn.

**Replay tạo dữ liệu trùng:** triển khai idempotency/deduplication và kiểm tra side effect ngoài Kafka.

**Dùng `--all-topics` ngoài ý muốn:** giới hạn bằng `--topic` cụ thể và xem dry-run trước khi thực thi.

**CLI không hỗ trợ tùy chọn:** kiểm tra `--help` và phiên bản Kafka CLI; một số tùy chọn reset theo thời gian có thể khác giữa phiên bản.

**AdminClient không đổi được offset:** kiểm tra group đã inactive, quyền ACL quản trị và lỗi trả về từ future của API.

## 18. Checklist vận hành reset offset

- Xác định rõ mục tiêu replay hay bỏ qua backlog.
- Xác minh đúng cluster, group ID, topic và partition.
- Ghi lại current offset, log start offset và log end offset.
- Dừng toàn bộ consumer member của group và ngăn autoscaling khởi động lại trong lúc thao tác.
- Chọn chiến lược reset phù hợp: earliest, latest, offset cụ thể, shift hoặc timestamp.
- Chạy `--dry-run` và kiểm tra kết quả từng partition.
- Chỉ dùng `--execute` sau khi offset đích được xác nhận.
- Nếu dùng AdminClient, có bước plan/approval trước `alterConsumerGroupOffsets`.
- Đảm bảo handler idempotent trước khi replay dữ liệu.
- Xác minh committed offsets và hành vi consumer sau khi khởi động lại.
- Theo dõi lag, lỗi listener và side effect nghiệp vụ sau thao tác.
- Lưu audit log cho thao tác reset.

Reset offset là cách thay đổi tiến độ đọc của một consumer group theo từng partition. Thực hiện an toàn cần dừng group, xem trước offset đích, áp dụng đúng phạm vi và xác minh sau khi khởi động lại. Đặc biệt, hãy đánh giá tác động nghiệp vụ của replay hoặc skip vì Kafka quản lý vị trí đọc, còn tính idempotent và tính đúng đắn của side effect thuộc trách nhiệm của ứng dụng.
