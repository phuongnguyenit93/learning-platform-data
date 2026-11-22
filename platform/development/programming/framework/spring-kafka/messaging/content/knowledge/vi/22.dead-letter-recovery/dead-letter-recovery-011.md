# Chính sách lưu trữ dead-letter topic

Dead-letter topic (DLT) lưu những Kafka record đã thất bại sau retry hoặc được phân loại là không thể retry. DLT thường là nơi đội vận hành tìm nguyên nhân, sửa dữ liệu hoặc cấu hình rồi phát lại record. Nếu retention quá ngắn, record có thể bị xóa trước khi được phát hiện và xử lý; nếu retention quá dài mà không giới hạn dung lượng, DLT có thể chiếm hết disk của broker.

Chính sách lưu trữ cần cân bằng ba mục tiêu: **đủ thời gian khôi phục**, **giới hạn dung lượng**, và **giữ được dữ liệu cần điều tra/audit**. Kafka thực hiện retention bằng cấu hình topic như `retention.ms`, `retention.bytes` và `cleanup.policy`. Những cấu hình này phải được thiết kế cùng quy trình DLT, năng lực consumer, replication factor và khả năng replay của ứng dụng.

## 1. DLT cần được lưu trong bao lâu?

Không có một thời hạn đúng cho mọi hệ thống. Thời gian lưu DLT phải dài hơn tổng thời gian cần để phát hiện sự cố, điều tra, khắc phục nguyên nhân và replay record.

Có thể lập kế hoạch theo công thức:

\[
T_{retention} \geq T_{detect} + T_{investigate} + T_{fix} + T_{replay} + T_{buffer}
\]

Trong đó:

- `T_detect`: thời gian từ lúc record vào DLT đến khi cảnh báo được phát hiện và có người tiếp nhận.
- `T_investigate`: thời gian phân tích exception, payload, dependency và ảnh hưởng nghiệp vụ.
- `T_fix`: thời gian triển khai bản sửa hoặc khắc phục dữ liệu/cấu hình.
- `T_replay`: thời gian cần để phát lại toàn bộ record tồn đọng với throughput an toàn.
- `T_buffer`: khoảng dự phòng cho ngày nghỉ, ngoài giờ, sự cố kéo dài hoặc quá trình phê duyệt.

Ví dụ, nếu hệ thống cần tối đa 2 ngày để phát hiện, 2 ngày điều tra, 3 ngày sửa và 2 ngày replay, thì retention 7 ngày là quá sát. Cần thêm buffer để sự cố cuối tuần hoặc một đợt DLT tăng đột biến không làm mất dữ liệu.

| Mục tiêu DLT | Chính sách cần cân nhắc |
|---|---|
| Vận hành và replay trong vài ngày | Retention hữu hạn, lớn hơn thời gian khôi phục mục tiêu. |
| Điều tra sự cố kéo dài hoặc audit nội bộ | Retention dài hơn, quyền truy cập chặt chẽ và có thể export sang kho lưu trữ. |
| Lưu trữ phục vụ tuân thủ nhiều tháng/năm | Không nên chỉ dựa vào Kafka topic; cân nhắc archive sang object storage hoặc hệ thống lưu trữ chuyên dụng. |
| DLT có thể tăng đột biến | Kết hợp retention theo thời gian và giới hạn bytes để bảo vệ broker. |

DLT không phải kho lưu trữ vô thời hạn. Nếu yêu cầu audit dài hơn khả năng lưu trữ Kafka, hãy tạo quy trình archive có xác nhận, kiểm tra tính toàn vẹn và chính sách truy xuất độc lập.

## 2. Các cấu hình retention quan trọng

Kafka quản lý việc dọn log bằng cấu hình `cleanup.policy`. Khi dùng chính sách `delete`, hai cấu hình chính là `retention.ms` và `retention.bytes`.

| Cấu hình | Ý nghĩa | Đơn vị/phạm vi |
|---|---|---|
| `cleanup.policy` | Chọn cách dọn log: xóa segment cũ, compact theo key hoặc kết hợp cả hai. | Topic |
| `retention.ms` | Thời gian tối đa giữ log trước khi các segment cũ đủ điều kiện bị xóa theo chính sách delete. | Milliseconds, topic |
| `retention.bytes` | Giới hạn dung lượng log cho mỗi partition; khi vượt giới hạn, segment cũ có thể bị xóa để giải phóng chỗ. | Bytes, mỗi partition |
| `segment.bytes` | Kích thước tối đa của một log segment trước khi roll segment mới. | Bytes, mỗi partition |
| `segment.ms` | Thời gian tối đa trước khi Kafka roll segment mới ngay cả khi segment chưa đầy. | Milliseconds, mỗi partition |
| `delete.retention.ms` | Thời gian giữ tombstone marker trong topic compacted. | Milliseconds, chỉ liên quan compaction |

Với `cleanup.policy=delete`, Kafka có thể xóa segment cũ khi **đạt giới hạn thời gian hoặc giới hạn dung lượng**, tùy điều kiện nào khiến segment đủ điều kiện trước. Hai giới hạn này bổ sung cho nhau; không nên xem `retention.bytes` là dung lượng dự phòng chỉ kích hoạt sau khi hết `retention.ms`.

Trong cấu hình Kafka phổ biến, `retention.ms` mặc định là 604.800.000 ms (7 ngày), còn `retention.bytes` mặc định là `-1` (không giới hạn theo dung lượng). Giá trị thực tế có thể được broker thay đổi hoặc topic override, vì vậy cần kiểm tra cấu hình hiệu lực của cluster thay vì dựa vào mặc định.

## 3. Chọn cleanup.policy cho DLT

Với DLT lưu các event lỗi để điều tra và replay, lựa chọn thông thường là:

```properties
cleanup.policy=delete
```

Chính sách `delete` giữ lịch sử record trong khoảng retention rồi xóa các segment cũ. Điều này phù hợp với DLT vì mỗi lần thất bại có thể cần được xem xét riêng, kể cả khi nhiều record có cùng business key.

Kafka còn hỗ trợ `compact` và `compact,delete`:

| Chính sách | Hành vi | Có phù hợp làm DLT lịch sử không? |
|---|---|---|
| `delete` | Xóa segment cũ theo retention thời gian/dung lượng. | Thường phù hợp nhất để giữ từng lần lỗi trong một cửa sổ thời gian. |
| `compact` | Giữ giá trị mới nhất theo key; các record cũ cùng key có thể bị loại khỏi log sau khi compaction chạy. | Chỉ phù hợp nếu DLT được thiết kế như trạng thái lỗi mới nhất theo key, không cần giữ mọi lần thất bại. |
| `compact,delete` | Vừa compact các segment còn giữ, vừa xóa segment cũ theo retention. | Không phù hợp nếu cần lưu toàn bộ lịch sử DLT. |

Ví dụ, ba event lỗi của cùng `orderId=O100` có thể cần được điều tra độc lập. Nếu dùng `cleanup.policy=compact`, các record cùng key có thể bị compact thành record mới nhất, làm mất lịch sử hai lần lỗi trước. Nếu mục tiêu là lưu từng dead-letter event, hãy dùng key duy nhất theo event hoặc ưu tiên `delete`.

`delete.retention.ms` không phải thời hạn lưu DLT thông thường. Cấu hình này quản lý thời gian giữ tombstone marker trong topic compacted; không dùng nó thay cho `retention.ms` của DLT có `cleanup.policy=delete`.

## 4. Cấu hình retention.ms và retention.bytes

Ví dụ dưới đây đặt DLT giữ tối đa 14 ngày và giới hạn 10 GiB cho mỗi partition:

```properties
cleanup.policy=delete
retention.ms=1209600000
retention.bytes=10737418240
```

Giải thích:

- `1209600000` ms = 14 ngày.
- `10737418240` bytes = 10 GiB cho mỗi partition.
- Nếu topic có 6 partition, giới hạn bytes logic xấp xỉ 60 GiB cho toàn topic trước khi tính replication và overhead.
- Segment cũ có thể bị xóa khi hết retention time hoặc khi partition vượt giới hạn bytes.

Đặt `retention.ms=-1` sẽ tắt giới hạn thời gian; đặt `retention.bytes=-1` sẽ tắt giới hạn dung lượng. Nếu cả hai đều `-1` và cleanup policy chỉ là delete, DLT không có giới hạn retention hữu hạn theo hai cấu hình này. Cách này có nguy cơ làm đầy disk nếu không có quy trình archive hoặc giới hạn khác.

## 5. Tạo DLT với Spring Kafka TopicBuilder

Khi Spring Kafka quản lý việc tạo topic qua `KafkaAdmin`, có thể khai báo `NewTopic` bean với các topic-level config:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class DeadLetterTopicConfiguration {

    @Bean
    NewTopic ordersDltTopic() {
        return TopicBuilder.name("orders.events-dlt")
                .partitions(6)
                .replicas(3)
                .config("cleanup.policy", "delete")
                .config("retention.ms", "1209600000")
                .config("retention.bytes", "10737418240")
                .build();
    }
}
```

Trong ví dụ:

- DLT có 6 partition để tương thích với topic nguồn 6 partition nếu recoverer gửi record vào partition tương ứng.
- Replication factor 3 yêu cầu cluster có đủ broker phù hợp.
- `cleanup.policy=delete` giữ từng record lỗi trong retention window.
- `retention.ms` và `retention.bytes` tạo hai giới hạn cho mỗi partition.

`NewTopic` mô tả cấu hình khi KafkaAdmin tạo topic. Nếu DLT đã tồn tại, hãy kiểm tra cấu hình thực tế và dùng Kafka Admin API hoặc CLI để thay đổi topic config khi cần; không giả định việc khai báo bean sẽ tự động sửa mọi cấu hình của topic hiện hữu.

Replication factor không làm thay đổi giá trị `retention.bytes` được tính cho mỗi partition, nhưng có ảnh hưởng đến tổng dung lượng vật lý mà cluster cần lưu. Nếu dùng producer `acks=all`, có thể cấu hình `min.insync.replicas` phù hợp để đặt mức xác nhận tối thiểu khi ghi DLT.

## 6. Thay đổi cấu hình DLT đã tồn tại bằng Kafka CLI

Có thể thay đổi topic config bằng `kafka-configs.sh`:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events-dlt \
  --alter \
  --add-config cleanup.policy=delete,retention.ms=1209600000,retention.bytes=10737418240
```

Kiểm tra cấu hình:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events-dlt \
  --describe
```

Kết quả `--describe` cho biết các topic config override. Nếu một thuộc tính không xuất hiện trong phần override, topic có thể đang kế thừa giá trị broker default. Hãy đối chiếu cả broker config khi cần biết giá trị hiệu lực.

Đổi retention xuống ngắn hơn có thể làm các segment cũ đủ điều kiện xóa sớm. Trước khi áp dụng trong production, cần xác nhận backlog DLT đã được xử lý hoặc archive, và việc thay đổi không làm mất cửa sổ replay đang được cam kết với đội vận hành.

## 7. Ước lượng dung lượng DLT

Dung lượng DLT phụ thuộc vào số record lỗi, kích thước record sau compression, retention window và replication factor.

Ước lượng dung lượng logic:

\[
S_{logical} \approx R_{day} \times B_{record} \times D
\]

Trong đó:

- `R_day`: số dead-letter record trung bình mỗi ngày.
- `B_record`: kích thước trung bình một record sau compression, gồm payload và headers.
- `D`: số ngày retention.

Ước lượng tổng dung lượng cluster:

\[
S_{cluster} \approx S_{logical} \times RF + S_{overhead}
\]

`RF` là replication factor. `S_overhead` gồm index, segment, filesystem và phần dự phòng vận hành; cần đo từ cluster thực tế vì compression và phân bố partition ảnh hưởng đáng kể.

Ví dụ:

- 1.000 record lỗi/ngày.
- Kích thước trung bình sau compression là 20 KiB/record.
- Retention 14 ngày.
- Replication factor bằng 3.

Dung lượng logic xấp xỉ:

\[
1000 \times 20\ KiB \times 14 \approx 273.4\ MiB
\]

Tổng bản sao trên cluster xấp xỉ:

\[
273.4\ MiB \times 3 \approx 820.2\ MiB
\]

Đây là ước lượng cơ bản, chưa tính index, segment overhead, header lớn, burst traffic và hệ số dự phòng. DLT có thể tăng đột biến khi một dependency ngừng hoạt động; hãy sizing theo kịch bản sự cố thay vì chỉ dùng trung bình ngày bình thường.

### Chia giới hạn theo partition

`retention.bytes` được áp dụng ở cấp partition. Nếu topic có `P` partition và muốn giới hạn dung lượng logic tổng khoảng `S`, có thể bắt đầu bằng:

\[
retention.bytes \approx \frac{S}{P}
\]

Ví dụ 60 GiB cho 6 partition tương ứng khoảng 10 GiB mỗi partition. Cần thêm headroom nếu key distribution không đều hoặc một partition nhận nhiều record lỗi hơn các partition còn lại. Một partition nóng có thể chạm giới hạn bytes và xóa dữ liệu cũ sớm hơn các partition khác.

## 8. Retention không phải TTL chính xác cho từng record

Kafka dọn dữ liệu theo log segment, không xóa từng record riêng lẻ ngay tại thời điểm hết hạn. Segment cần được roll và đủ điều kiện theo retention/cleanup trước khi broker xóa file. Vì vậy:

- `retention.ms` là giới hạn retention của log theo chính sách delete, không phải lịch hẹn xóa chính xác từng record.
- `segment.bytes` và `segment.ms` ảnh hưởng thời điểm segment được roll và mức độ chi tiết của việc dọn dữ liệu.
- Segment lớn có thể khiến việc xóa ít chính xác theo thời gian hơn vì Kafka dọn theo file segment.
- Segment đang active chưa thể bị xóa như segment đã đóng; vì vậy dung lượng partition có thể tạm thời vượt `retention.bytes` trước khi roll và cleanup hoàn tất.
- Thời điểm xóa thực tế còn phụ thuộc chu kỳ cleanup và hoạt động của broker.

Không nên cam kết với nghiệp vụ rằng record sẽ biến mất chính xác tại giây thứ N. Hãy coi retention là cửa sổ lưu trữ vận hành và thiết kế replay/alert có buffer trước thời điểm hết hạn.

## 9. Số partition và replication factor của DLT

DLT cần đủ partition cho cách recoverer định tuyến record. Với `DeadLetterPublishingRecoverer` mặc định, record thường được gửi vào partition có cùng index với partition nguồn. Do đó, DLT thường cần ít nhất số partition bằng topic nguồn.

Nếu DLT có ít partition hơn topic nguồn, việc publish vào partition không tồn tại có thể thất bại. Có thể tùy biến destination resolver để chọn partition hợp lệ hoặc để partitioner quyết định, nhưng phải giữ được khả năng truy vết và throughput cần thiết.

Replication factor quyết định số bản sao partition được duy trì trên cluster. Nó không phải retention window và cũng không thay thế backup/archive. Nếu một record bị xóa do retention, các replica cũng sẽ phản ánh log đã bị cắt theo cơ chế replication; replication không giúp khôi phục record đã hết hạn.

Khi thiết kế DLT production, cần đánh giá:

- Số broker và replication factor có thể đáp ứng.
- `min.insync.replicas` cùng producer `acks` nếu yêu cầu xác nhận ghi mạnh hơn.
- Dung lượng disk trên từng broker sau khi tính replica placement.
- Partition count và mức phân bố record lỗi theo key.
- Khả năng consumer DLT đọc và replay trước khi retention xóa dữ liệu.

## 10. Quy trình replay trước khi record hết hạn

Retention chỉ có ý nghĩa khi đội vận hành biết cách xử lý record trong cửa sổ lưu trữ. Một quy trình replay an toàn nên có các bước:

1. **Phát hiện:** alert khi DLT có record mới hoặc oldest record age tăng.
2. **Phân loại:** nhóm lỗi theo exception class, error code, source topic và service.
3. **Khắc phục:** sửa dependency, cấu hình hoặc dữ liệu nguồn trước khi replay.
4. **Chọn phạm vi:** replay theo source topic, partition, offset range, event ID hoặc nhóm lỗi đã được phê duyệt.
5. **Giữ dấu vết:** thêm metadata như `replay-id`, `replayed-at`, `replay-operator` và source DLT khi phát lại.
6. **Chống xử lý trùng:** giữ `eventId` và dùng consumer idempotent/inbox để side effect không bị áp dụng hai lần.
7. **Xác minh:** kiểm tra số record đã replay, số record thành công, số record tiếp tục lỗi và offset/sequence nghiệp vụ.

Nếu cần giữ thứ tự theo aggregate, không replay ngẫu nhiên các record của cùng key. Có thể cần sắp theo original partition và original offset hoặc sequence nghiệp vụ, tùy cách DLT được tạo. Offset từ các partition khác nhau không thể so sánh thành một thứ tự toàn cục.

Không nên replay mù toàn bộ DLT về topic nguồn khi nguyên nhân chưa được khắc phục. Điều đó có thể tạo vòng lặp lỗi, tăng DLT nhanh hơn và làm quá tải consumer/database. Hãy giới hạn tốc độ replay để không gây thêm áp lực lên hệ thống đã phục hồi.

## 11. Consumer offset và retention

Committed offset của consumer group không khóa record và không ngăn Kafka xóa segment đã hết hạn. Nếu DLT consumer ngừng hoạt động lâu hơn retention window, record cũ có thể bị xóa dù group vẫn giữ committed offset trỏ đến vị trí đó.

Khi consumer yêu cầu offset đã nằm ngoài phạm vi log còn tồn tại, hành vi phụ thuộc `auto.offset.reset`:

| Giá trị | Hành vi khi offset không còn hợp lệ hoặc chưa có committed offset |
|---|---|
| `earliest` | Bắt đầu từ offset sớm nhất còn tồn tại; record đã bị retention xóa không thể đọc lại. |
| `latest` | Bắt đầu từ cuối log hiện tại; có thể bỏ qua backlog còn lại theo vị trí reset. |
| `none` | Ném lỗi khi không có offset hợp lệ để sử dụng. |

Với DLT consumer dùng để điều tra/replay, hãy đặt `earliest` nếu muốn đọc toàn bộ dữ liệu còn giữ khi group mới bắt đầu; tuy nhiên điều này không khôi phục record đã hết hạn. Theo dõi consumer lag và oldest record age để bảo đảm consumer theo kịp retention window.

## 12. Monitoring và cảnh báo retention

DLT cần dashboard riêng hoặc ít nhất có metric phân biệt với topic nghiệp vụ. Các chỉ số nên theo dõi:

| Metric | Mục đích |
|---|---|
| DLT incoming records/rate | Phát hiện số record lỗi tăng bất thường. |
| DLT bytes per partition | Theo dõi mức sử dụng `retention.bytes` và phát hiện partition nóng. |
| Oldest DLT record age | Xác định backlog gần hết retention window. |
| DLT consumer lag | Biết tốc độ xử lý DLT có theo kịp tốc độ phát sinh không. |
| Broker disk usage | Phát hiện nguy cơ đầy disk do DLT hoặc các topic khác. |
| DLT publish failure | Phát hiện recoverer không thể ghi record vào DLT. |
| Replay success/failure count | Đánh giá hiệu quả khôi phục và lỗi lặp lại. |
| Exception class/error category | Nhận diện lỗi hệ thống, lỗi dữ liệu hoặc lỗi nghiệp vụ phổ biến. |

Nên cảnh báo khi:

- DLT nhận record vượt ngưỡng bình thường.
- Oldest DLT record age đạt một tỷ lệ đáng kể của retention window, ví dụ 70–80%.
- Consumer lag tăng liên tục hoặc không giảm sau khi dependency phục hồi.
- Partition đạt gần `retention.bytes` hoặc broker disk vượt ngưỡng vận hành.
- Recoverer publish thất bại hoặc DLT topic không đủ partition/ISR.

Không chỉ theo dõi tổng số record của topic. Một partition có thể đạt giới hạn bytes trong khi tổng dung lượng topic vẫn thấp, khiến dữ liệu cũ của partition đó bị xóa sớm.

## 13. Bảo mật và lưu trữ dài hạn

DLT thường chứa payload gây lỗi và exception metadata. Nội dung này có thể bao gồm dữ liệu cá nhân, token, SQL, URL nội bộ hoặc thông tin triển khai. Retention càng dài thì phạm vi dữ liệu nhạy cảm tồn tại càng lâu.

Các biện pháp nên áp dụng:

- Giới hạn quyền đọc/ghi DLT bằng ACL hoặc authorization tương ứng.
- Lọc credential và header nhạy cảm trước khi publish DLT.
- Mã hóa dữ liệu khi truyền và khi lưu theo chính sách của cluster.
- Thiết lập retention theo nhu cầu khôi phục và chính sách dữ liệu, tránh giữ vô hạn theo mặc định.
- Nếu cần archive lâu dài, xuất record sang object storage hoặc hệ thống audit có lifecycle/immutability phù hợp.
- Ghi nhận ai replay record, replay khi nào và kết quả ra sao.
- Kiểm tra quy trình xóa dữ liệu theo yêu cầu privacy/compliance.

Archive cần có xác nhận ghi thành công và kiểm tra số lượng/checksum trước khi giảm retention Kafka. Nếu chỉ copy không kiểm chứng rồi để Kafka xóa bản gốc, có thể mất dữ liệu khi pipeline archive bị lỗi.

## 14. Ví dụ chính sách DLT hoàn chỉnh

Một cấu hình minh họa cho service xử lý order:

| Thuộc tính | Giá trị ví dụ | Lý do |
|---|---|---|
| Topic | `orders.events-dlt` | DLT riêng cho luồng order. |
| Partitions | `6` | Tương thích topic nguồn có 6 partition nếu giữ partition index. |
| Replication factor | `3` | Có nhiều bản sao trên cluster. |
| `cleanup.policy` | `delete` | Giữ từng record lỗi trong retention window. |
| `retention.ms` | `1209600000` | 14 ngày để điều tra và replay. |
| `retention.bytes` | `10737418240` | 10 GiB mỗi partition làm giới hạn dung lượng. |
| DLT consumer | `orders-dlt-ops` | Consumer riêng phục vụ điều tra/replay. |
| Alert oldest age | `10 ngày` | Cảnh báo trước khi hết cửa sổ 14 ngày. |

Các giá trị này chỉ là ví dụ. Trước khi áp dụng, cần tính theo tốc độ record lỗi, kích thước record, partition skew, replication factor, khả năng replay và yêu cầu audit của hệ thống.

## 15. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Record biến mất trước khi replay | `retention.ms` quá ngắn so với thời gian phát hiện và khắc phục. | Tăng retention window, alert oldest record age và archive khi cần. |
| DLT chiếm quá nhiều disk | Không đặt giới hạn bytes hoặc failure rate tăng kéo dài. | Đặt `retention.bytes`, xử lý nguyên nhân gốc và theo dõi broker disk. |
| Một partition mất record sớm hơn partition khác | `retention.bytes` áp dụng riêng từng partition và phân bố record không đều. | Theo dõi bytes/partition, điều chỉnh partitioning hoặc giới hạn có headroom. |
| DLT chỉ còn event mới nhất theo key | Topic dùng `cleanup.policy=compact` hoặc `compact,delete`. | Dùng `delete` nếu cần giữ từng dead-letter event. |
| `delete.retention.ms` không thay đổi thời hạn DLT | Nhầm tombstone retention với log retention. | Dùng `retention.ms` và `retention.bytes` cho cleanup delete. |
| Record vẫn tồn tại sau mốc retention | Kafka xóa theo segment, không xóa từng record chính xác từng giây. | Dùng buffer trong kế hoạch replay và hiểu `segment.ms`/`segment.bytes`. |
| Consumer offset out of range | Consumer dừng lâu hơn retention và offset cũ đã bị xóa. | Khởi động từ offset còn tồn tại theo reset policy; dữ liệu đã xóa cần archive/backup. |
| Thay đổi TopicBuilder nhưng topic không đổi config | Topic đã tồn tại và config hiện hành chưa được alter. | Dùng Kafka CLI/Admin API để thay đổi và describe xác nhận. |
| Replication không cứu được record hết hạn | Retention xóa log trên partition và các replica đồng bộ việc xóa. | Dùng archive/backup nếu cần khôi phục sau retention. |

## 16. Ghi nhớ

- Chọn retention window lớn hơn tổng thời gian phát hiện, điều tra, sửa lỗi, replay và buffer.
- `retention.ms` giới hạn thời gian; `retention.bytes` giới hạn dung lượng cho mỗi partition khi dùng cleanup delete.
- Khi một trong hai giới hạn delete đạt điều kiện, segment cũ có thể bị xóa.
- `cleanup.policy=delete` thường phù hợp với DLT cần giữ từng lần thất bại; `compact` có thể loại record cũ cùng key.
- `delete.retention.ms` quản lý tombstone của topic compacted, không thay thế `retention.ms` của DLT thông thường.
- Retention được thực hiện theo segment, không phải TTL chính xác cho từng record.
- `retention.bytes` nhân với partition count để ước lượng giới hạn logic topic; replication factor làm tăng dung lượng vật lý cluster.
- Committed offset không bảo vệ record khỏi retention; consumer lag cần nằm trong cửa sổ lưu trữ.
- Có quy trình replay idempotent, giữ metadata nguồn và giới hạn tốc độ replay.
- Nếu cần lưu lâu hơn cửa sổ Kafka, archive sang hệ thống lưu trữ chuyên dụng và xác minh trước khi giảm retention.

Chính sách DLT tốt phải bắt đầu từ thời gian khôi phục thực tế, sau đó sizing theo lưu lượng lỗi và partition count, rồi mới chọn `retention.ms`, `retention.bytes` và `cleanup.policy`. Kết hợp monitoring oldest record age, consumer lag, disk usage và quy trình replay sẽ giúp record lỗi còn đủ thời gian được xử lý mà không để DLT trở thành nguồn tiêu thụ disk không kiểm soát.

## Tài liệu tham khảo

- [Apache Kafka — Topic Configurations](https://kafka.apache.org/44/configuration/topic-configs/)
- [Apache Kafka — Consumer Configurations](https://kafka.apache.org/documentation/#consumerconfigs)
- [Spring for Apache Kafka — Dead-letter Publishing](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html#publishing-dead-letter-records)
- [Spring for Apache Kafka — KafkaAdmin and Topic Configuration](https://docs.spring.io/spring-kafka/reference/kafka/configuring-topics.html)
