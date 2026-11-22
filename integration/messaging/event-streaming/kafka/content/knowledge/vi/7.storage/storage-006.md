# Retention theo thời gian, dung lượng và cơ chế xóa segment

## Mục tiêu bài học

Kafka lưu record trong log của từng partition. Khi topic dùng chính sách `delete`, broker giữ các log segment trong khoảng thời gian hoặc giới hạn dung lượng được cấu hình rồi xóa những segment cũ đủ điều kiện. Cơ chế này quyết định consumer có thể đọc lại dữ liệu trong bao lâu, dung lượng đĩa cần dự trù và cách cluster phản ứng khi tốc độ ghi tăng.

Sau bài học, bạn có thể:

- Phân biệt retention theo thời gian với retention theo dung lượng.
- Giải thích vì sao Kafka xóa log segment thay vì xóa từng record ngay khi hết hạn.
- Hiểu vai trò của `retention.ms`, `retention.bytes`, `segment.ms`, `segment.bytes` và chu kỳ kiểm tra retention.
- Ước lượng dung lượng lưu trữ từ tốc độ ghi, thời gian giữ dữ liệu, số partition và replication factor.
- Kiểm tra và thay đổi retention ở cấp topic bằng Kafka CLI.
- Nhận diện rủi ro khi consumer lag vượt quá thời gian lưu dữ liệu.
- Phân biệt retention của topic với thời gian lưu tombstone và consumer group offset.

## 1. Retention là gì?

Retention là chính sách xác định Kafka giữ dữ liệu trong log bao lâu hoặc đến khi log đạt kích thước nào. Với `cleanup.policy=delete`, Kafka xóa các segment cũ khi chúng đủ điều kiện theo chính sách retention. Producer không cần gửi lệnh xóa sau khi consumer đọc xong; consumer cũng không xóa record chỉ bằng việc commit offset.

Ví dụ topic `orders` được cấu hình giữ dữ liệu trong 7 ngày. Một consumer đọc record hôm nay không làm record đó bị xóa ngay. Consumer khác có thể đọc lại cùng record trong khoảng thời gian dữ liệu còn nằm trong log và offset vẫn hợp lệ.

Retention có ảnh hưởng trực tiếp đến:

- **Khả năng replay:** consumer có thể quay lại đọc dữ liệu cũ đến đâu.
- **Khả năng phục hồi:** ứng dụng có thể tái dựng trạng thái sau lỗi hoặc triển khai lại consumer.
- **Dung lượng đĩa:** thời gian giữ dài hơn thường cần nhiều dung lượng hơn.
- **Consumer lag:** consumer chậm có nguy cơ mất quyền truy cập vào record cũ nếu dữ liệu bị xóa trước khi consumer đọc đến.
- **Chi phí vận hành:** dữ liệu lưu trên mọi replica đều tiêu thụ dung lượng vật lý.

Retention là chính sách lưu trữ của topic, không phải cơ chế xác nhận rằng mọi consumer đã xử lý xong dữ liệu.

## 2. Retention theo thời gian

### 2.1. `retention.ms`

`retention.ms` là topic configuration quy định thời gian tối đa giữ log theo chính sách xóa, tính bằng mili giây. Broker cũng có cấu hình mặc định `log.retention.ms`; topic có thể override giá trị này.

Ví dụ:

```properties
retention.ms=604800000
```

Giá trị trên tương ứng 7 ngày:

\[
7 \times 24 \times 60 \times 60 \times 1000
= 604\,800\,000\text{ ms}
\]

Một số cách cấu hình khác thường gặp:

| Giá trị | Ý nghĩa |
|---|---|
| `retention.ms=86400000` | Giữ theo thời gian khoảng 1 ngày |
| `retention.ms=604800000` | Giữ theo thời gian khoảng 7 ngày |
| `retention.ms=2592000000` | Giữ theo thời gian khoảng 30 ngày |
| `retention.ms=-1` | Không áp dụng giới hạn thời gian theo retention |

Đặt `-1` không có nghĩa dữ liệu được bảo vệ vĩnh viễn trước mọi thao tác. Topic vẫn có thể bị xóa, partition có thể được thay đổi theo thao tác quản trị, storage có thể hỏng hoặc một chính sách khác có thể làm dữ liệu bị loại bỏ.

### 2.2. Thời gian retention không phải thời điểm xóa chính xác từng record

Kafka không chạy một bộ đếm riêng cho từng record rồi xóa đúng mili giây khi hết hạn. Record nằm trong các log segment. Retention manager kiểm tra các segment đã đóng và xóa segment khi segment đủ điều kiện.

Vì vậy, thời điểm record biến mất có thể muộn hơn mốc retention cấu hình do:

- Broker chỉ kiểm tra log theo chu kỳ.
- Segment cần được đóng (roll) trước khi đủ điều kiện xóa.
- Kafka xóa theo segment, không cắt từng record trong segment đang hoạt động.
- Thời điểm và timestamp dùng để đánh giá tuổi segment phụ thuộc timestamp policy của log.

Với `CreateTime`, timestamp của record do producer cung cấp; đồng hồ producer lệch hoặc timestamp được gán sai có thể ảnh hưởng cách đánh giá tuổi segment. Với `LogAppendTime`, broker gán timestamp khi append record. Khi cần SLA retention chính xác, hãy xem xét timestamp policy, segment roll và thời gian kiểm tra cleanup cùng nhau.

### 2.3. Chu kỳ kiểm tra retention

Broker dùng cấu hình `log.retention.check.interval.ms` để xác định chu kỳ kiểm tra log có segment đủ điều kiện xóa hay không. Giá trị thường gặp ở nhiều bản phân phối là vài phút, nhưng phải kiểm tra cấu hình thực tế của cluster.

Chu kỳ kiểm tra càng ngắn thì broker có thể phát hiện segment hết hạn sớm hơn, nhưng không biến retention thành thao tác xóa tức thời. Segment đang hoạt động vẫn cần được roll trước khi xóa. Không nên giảm chu kỳ quá thấp chỉ để cố đạt thời điểm xóa chính xác nếu chưa đánh giá chi phí I/O và tải metadata.

## 3. Retention theo dung lượng

### 3.1. `retention.bytes`

`retention.bytes` giới hạn dung lượng log của **mỗi partition** khi dùng chính sách `delete`. Khi partition vượt giới hạn, Kafka có thể xóa các segment cũ để đưa log về dưới ngưỡng.

Ví dụ:

```properties
retention.bytes=10737418240
```

Giá trị này tương đương khoảng 10 GiB cho mỗi partition. Nếu topic có 12 partition và các partition đều đạt gần giới hạn, dung lượng một bản sao của topic có thể xấp xỉ 120 GiB, chưa tính index, overhead và độ lệch phân bố.

Các giá trị thường gặp:

| Giá trị | Ý nghĩa |
|---|---|
| `retention.bytes=1073741824` | Khoảng 1 GiB cho mỗi partition |
| `retention.bytes=10737418240` | Khoảng 10 GiB cho mỗi partition |
| `retention.bytes=-1` | Không áp dụng giới hạn dung lượng theo retention |

Không nhầm `retention.bytes` với tổng dung lượng của toàn topic hoặc tổng dung lượng của cả cluster. Nó được áp dụng cho log của từng partition; tổng dung lượng topic phụ thuộc số partition và lượng dữ liệu thực tế trong từng partition.

### 3.2. Kích thước log và segment

Partition log được chia thành nhiều segment. Mỗi segment thường gồm file dữ liệu và các index hỗ trợ tìm offset/timestamp. Cấu hình `segment.bytes` đặt kích thước mục tiêu của segment; `segment.ms` giới hạn thời gian trước khi segment đang hoạt động được roll.

Ví dụ:

```properties
segment.bytes=1073741824
segment.ms=604800000
```

Trong ví dụ, segment có kích thước mục tiêu khoảng 1 GiB và được roll theo giới hạn thời gian khoảng 7 ngày. Đây là ví dụ cấu hình, không phải khuyến nghị mặc định cho mọi workload.

Segment có thể được roll khi đạt ngưỡng kích thước hoặc điều kiện thời gian. Segment đang hoạt động (active segment) nhận record mới; segment đã roll trở thành segment cũ và có thể được xét cho retention/cleanup.

### 3.3. Vì sao retention.bytes có thể vượt ngưỡng một thời gian?

Kafka xóa theo segment. Giả sử partition có giới hạn 10 GiB, segment kích thước mục tiêu 1 GiB và log đang có 10.4 GiB. Segment hiện tại có thể vẫn đang hoạt động; Kafka không xóa từng phần của segment để lập tức đưa log về đúng 10 GiB. Khi segment được roll và cleanup chạy, broker có thể xóa một hoặc nhiều segment cũ, khiến dung lượng giảm theo bước.

Do đó, `retention.bytes` là giới hạn được thực thi theo segment và chu kỳ cleanup, không phải hard cap chính xác cho từng byte trong mọi thời điểm. Cần dự trù headroom để log tăng giữa các lần roll và cleanup.

## 4. Khi cấu hình cả retention.ms và retention.bytes

Nếu topic bật `cleanup.policy=delete` và cả hai cấu hình đều có giới hạn, Kafka có thể xóa segment cũ khi điều kiện thời gian **hoặc** điều kiện dung lượng yêu cầu xóa. Nói cách khác, dữ liệu có thể bị loại bỏ theo điều kiện đến trước.

Ví dụ:

```properties
cleanup.policy=delete
retention.ms=604800000
retention.bytes=10737418240
```

Topic đặt mục tiêu giữ tối đa khoảng 7 ngày và giới hạn khoảng 10 GiB cho mỗi partition. Nếu partition tăng nhanh và chạm giới hạn dung lượng trước 7 ngày, các segment cũ có thể bị xóa sớm hơn. Nếu lưu lượng thấp, retention theo thời gian có thể xóa dữ liệu dù partition chưa đầy 10 GiB.

| Tình huống | Điều kiện có thể kích hoạt xóa |
|---|---|
| Lưu lượng thấp, log còn nhỏ nhưng segment đã quá tuổi | `retention.ms` |
| Lưu lượng cao, partition vượt ngưỡng dung lượng trước khi đủ tuổi | `retention.bytes` |
| Cả hai điều kiện đều đã đạt | Segment cũ đủ điều kiện sẽ được xóa theo cleanup |
| Một trong hai đặt `-1` | Điều kiện đó không giới hạn retention; điều kiện còn lại vẫn có thể áp dụng |

Nếu nghiệp vụ yêu cầu consumer có tối thiểu 7 ngày để replay, không nên chỉ đặt `retention.ms=7 days` rồi để `retention.bytes` quá thấp. Giới hạn dung lượng có thể làm mất dữ liệu trước khi hết 7 ngày. Hãy kiểm tra cả hai điều kiện và tốc độ tăng trưởng cực đại.

## 5. Cơ chế xóa segment diễn ra như thế nào?

Một chu trình đơn giản:

```text
Producer append record
         |
         v
Active segment nhận dữ liệu
         |
         v
Đạt segment.bytes hoặc segment.ms?
         |
         v
Roll sang segment mới
         |
         v
Retention manager kiểm tra segment cũ
         |
         v
Đạt retention time hoặc size?
       /       \
     Chưa       Có
      |          |
      v          v
 Giữ lại    Đánh dấu/xóa segment
                 |
                 v
          Giải phóng dung lượng
```

Các bước trên mô tả khái niệm. Kafka còn có các quy tắc về segment cuối, log start offset, transaction và compaction. Vì thế, không nên suy luận rằng mỗi record sẽ được xóa ngay sau khi timestamp của nó vượt ngưỡng.

### 5.1. Segment roll

Segment roll đóng segment hiện tại và mở segment mới. Các yếu tố ảnh hưởng gồm:

- `segment.bytes`: ngưỡng kích thước segment.
- `segment.ms`: thời gian tối đa trước khi roll segment.
- `segment.jitter.ms`: độ lệch ngẫu nhiên có thể được áp dụng để tránh nhiều log roll cùng lúc.
- Các giới hạn index và điều kiện nội bộ của log.

Nếu topic có lưu lượng rất thấp và `segment.ms` dài, một segment có thể tồn tại lâu trước khi đóng. Điều đó có thể làm thời điểm retention xóa dữ liệu trễ hơn mong đợi. Điều chỉnh segment roll có thể giúp cleanup kịp thời hơn nhưng cũng làm tăng số lượng file và metadata.

### 5.2. Xóa file và giải phóng dung lượng

Khi segment đủ điều kiện, Kafka loại segment khỏi log và xóa file theo cơ chế filesystem của broker. Một số cấu hình có thể trì hoãn xóa file vật lý trong một khoảng thời gian để tránh ảnh hưởng đến thao tác đang mở file. Vì vậy, dung lượng hệ điều hành báo cáo có thể không giảm ngay đúng thời điểm segment bị loại khỏi log.

Theo dõi cả log size của Kafka và dung lượng filesystem. Nếu hai số liệu khác nhau trong một khoảng ngắn, cần kiểm tra segment deletion delay, file đang mở, filesystem và tiến trình cleanup trước khi kết luận retention không hoạt động.

## 6. `cleanup.policy`: delete và compact

Retention theo thời gian/dung lượng thường được hiểu cùng với `cleanup.policy`.

### 6.1. `cleanup.policy=delete`

Với `delete`, Kafka xóa segment cũ theo `retention.ms` và/hoặc `retention.bytes`. Đây là mô hình phù hợp với event stream cần giữ lịch sử trong một khoảng thời gian, ví dụ `orders`, `payments` hoặc `application-events`.

Consumer có thể replay các record còn trong retention. Sau khi segment bị xóa, consumer có offset trỏ vào dữ liệu đã mất sẽ không thể đọc lại record đó. Ứng dụng cần xử lý tình huống offset out of range theo chính sách phù hợp, chẳng hạn dừng để điều tra hoặc dùng `auto.offset.reset` nếu nghiệp vụ cho phép chuyển đến vị trí còn tồn tại.

### 6.2. `cleanup.policy=compact`

Với `compact`, Kafka giữ lại giá trị mới nhất theo key theo tiến trình compaction. Topic phù hợp để biểu diễn trạng thái hiện tại của từng thực thể, ví dụ cấu hình thiết bị hoặc hồ sơ tài khoản.

Compaction không đồng nghĩa chỉ còn đúng một record cho mỗi key ngay lập tức. Cleaner chạy nền; các segment đang hoạt động và segment chưa được compact vẫn có thể chứa nhiều phiên bản của cùng key. Consumer đọc từ đầu có thể nhìn thấy nhiều phiên bản trước khi compaction hoàn tất.

### 6.3. `cleanup.policy=compact,delete`

Có thể kết hợp compaction với retention theo thời gian/dung lượng. Trong trường hợp này, compaction giữ trạng thái mới nhất theo key trong phạm vi dữ liệu còn được giữ, còn delete policy có thể loại bỏ các segment đủ điều kiện theo retention. Hãy xác định rõ yêu cầu replay và khả năng tái dựng state trước khi kết hợp hai chính sách.

### 6.4. `delete.retention.ms` không phải `retention.ms`

Trong compacted topic, record có key và value `null` được gọi là **tombstone**, thường biểu thị việc xóa key. `delete.retention.ms` quy định thời gian tombstone được giữ để consumer có cơ hội quan sát thông tin xóa trước khi tombstone bị loại bỏ trong quá trình compaction.

Hai cấu hình có mục đích khác nhau:

| Cấu hình | Ý nghĩa |
|---|---|
| `retention.ms` | Giới hạn thời gian giữ log theo delete retention policy |
| `retention.bytes` | Giới hạn kích thước log theo delete retention policy, tính theo partition |
| `delete.retention.ms` | Thời gian giữ tombstone trong compacted topic |

Không dùng `delete.retention.ms` để thay thế retention lịch sử của event stream. Ngược lại, không giả định `retention.ms` bảo đảm tombstone luôn được giữ đủ lâu để mọi consumer bootstrap.

## 7. Ước lượng dung lượng cần thiết

### 7.1. Công thức ước lượng cơ bản

Nếu biết tốc độ dữ liệu ghi trung bình sau nén, thời gian giữ và replication factor, có thể ước lượng dung lượng log:

\[
S \approx R \times T \times RF
\]

Trong đó:

- `S`: dung lượng vật lý xấp xỉ cho log trên toàn bộ replica.
- `R`: tốc độ dữ liệu lưu trữ mỗi giây của topic (bytes/s), sau nén nếu đã đo ở dạng lưu trên disk.
- `T`: thời gian retention (giây).
- `RF`: replication factor.

Nếu tốc độ ghi đo ở dạng trước nén, cần ước lượng compression ratio để chuyển sang tốc độ lưu trên disk. Ngoài ra phải cộng index, segment overhead, metadata, dữ liệu đang được replication và dung lượng dự phòng cho rebalance/recovery.

### 7.2. Ví dụ tính toán

Giả sử:

- Topic nhận trung bình 4 MB/s dữ liệu đã nén.
- Retention là 3 ngày.
- Replication factor bằng 3.
- Bỏ qua index và overhead để tính sơ bộ.

Thời gian giữ:

\[
T = 3 \times 24 \times 60 \times 60 = 259\,200\text{ giây}
\]

Dung lượng một bản sao:

\[
S_{logical} = 4 \times 259\,200 = 1\,036\,800\text{ MB}
\]

Tương đương khoảng 1,04 TB theo đơn vị thập phân. Với RF=3:

\[
S_{physical} \approx 1.04 \times 3 = 3.12\text{ TB}
\]

Đây là dung lượng cho toàn bộ replica của topic, chưa phải dung lượng mỗi broker. Kafka phân bố partition replica qua broker; dung lượng thực tế từng broker phụ thuộc assignment, tải từng partition và mất cân bằng giữa các broker.

### 7.3. Tính theo partition và giới hạn retention.bytes

Nếu topic có `P` partition và `retention.bytes=B`, dung lượng tối đa xấp xỉ cho một bản sao của topic theo ngưỡng này là:

\[
S_{logical} \approx P \times B
\]

Tổng dung lượng các replica xấp xỉ:

\[
S_{physical} \approx P \times B \times RF
\]

Ví dụ 12 partition, `retention.bytes=10 GiB` và RF=3:

\[
12 \times 10 \times 3 = 360\text{ GiB}
\]

Đây là ước lượng khi mọi partition đều sử dụng gần hết giới hạn. Cần cộng headroom vì segment deletion không diễn ra chính xác theo byte, và vì broker cần chỗ trống để replica catch up hoặc phục hồi sau lỗi.

### 7.4. Chọn retention dựa trên yêu cầu replay

Không nên chọn retention chỉ dựa vào dung lượng hiện có. Hãy bắt đầu từ câu hỏi nghiệp vụ:

- Consumer có thể ngừng hoạt động tối đa bao lâu trước khi cần replay?
- Có cần dựng lại projection hoặc materialized view từ đầu không?
- Có cần điều tra sự cố sau nhiều ngày hoặc nhiều tuần không?
- Có nguồn lưu trữ dài hạn khác như data lake/object storage không?
- Nếu consumer lag tăng đột ngột, thời gian còn lại trước khi record cũ bị xóa là bao lâu?

Sau khi xác định thời gian cần giữ, hãy tính dung lượng dựa trên tốc độ ghi cao điểm, không chỉ trung bình. Nếu tốc độ tăng gấp đôi trong thời gian cao điểm, dung lượng cần thiết cũng tăng tương ứng trong cùng thời gian retention.

## 8. Consumer lag và rủi ro mất dữ liệu trước khi đọc

Consumer group lưu offset đã commit riêng với log record. Kafka không giữ record vô thời hạn chỉ vì consumer group chưa đọc đến. Nếu retention xóa segment chứa offset mà consumer cần, consumer có thể gặp `OffsetOutOfRangeException` hoặc được reset theo `auto.offset.reset` tùy cấu hình và cách xử lý lỗi.

Ví dụ:

```text
Partition 0:
  Log start offset = 500
  Consumer committed offset = 420
  Log end offset = 900

Consumer muốn đọc từ 420 nhưng dữ liệu bắt đầu từ 500.
Các record 420..499 đã không còn trong log.
```

Điều này có thể xảy ra khi consumer dừng lâu hơn retention hoặc khi retention.bytes xóa dữ liệu sớm do tốc độ ghi cao. Vì vậy, retention cần được thiết kế lớn hơn khoảng thời gian consumer có thể bị gián đoạn, có thêm dự phòng cho tốc độ ghi bất thường.

Theo dõi các metric:

- Consumer lag theo partition và consumer group.
- Log start offset và log end offset.
- Thời gian ước lượng để consumer bắt kịp producer.
- Tốc độ ghi dữ liệu và disk usage.
- Số lần offset out of range hoặc reset offset.

Một cảnh báo lag nên tính đến retention còn lại. Lag lớn chưa chắc đã mất dữ liệu nếu tốc độ xử lý vẫn đủ để bắt kịp; nhưng nếu consumer không thể bắt kịp trước khi segment bị xóa, cần can thiệp sớm.

## 9. Kiểm tra và thay đổi retention bằng Kafka CLI

### 9.1. Xem cấu hình topic

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
```

Lệnh cho biết các topic-level override. Nếu một cấu hình không xuất hiện, topic có thể đang kế thừa broker default; hãy kiểm tra cấu hình broker hoặc dùng Admin API phù hợp phiên bản để phân biệt giá trị hiệu lực và nguồn của cấu hình.

### 9.2. Đặt retention theo thời gian

Giữ dữ liệu trong 7 ngày:

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --add-config retention.ms=604800000
```

### 9.3. Đặt retention theo dung lượng

Giới hạn khoảng 10 GiB cho mỗi partition:

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --add-config retention.bytes=10737418240
```

### 9.4. Đặt cả hai điều kiện

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --add-config retention.ms=604800000,retention.bytes=10737418240
```

Sau khi thay đổi, chạy lại lệnh `--describe` để xác minh. Cấu hình có thể được áp dụng động, nhưng thời điểm segment bị xóa còn phụ thuộc segment roll và retention check. Thay đổi retention xuống thấp có thể làm dữ liệu cũ bị xóa sớm hơn; hãy đánh giá tác động replay trước khi áp dụng production.

### 9.5. Xóa override để dùng broker default

Nếu muốn topic quay lại kế thừa broker default, có thể xóa override bằng cú pháp `--delete-config` ở các phiên bản Kafka hỗ trợ:

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --delete-config retention.ms,retention.bytes
```

Xóa override không có nghĩa retention bị tắt. Topic sẽ dùng giá trị mặc định theo broker/configuration hiện hành. Hãy đọc lại cấu hình và xác nhận giá trị hiệu lực.

## 10. Các lỗi cấu hình và nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Consumer đọc xong thì record bị xóa | Kafka retention độc lập với consumer commit offset |
| `retention.ms` xóa từng record đúng thời điểm | Kafka xóa log segment đủ điều kiện theo chu kỳ cleanup |
| `retention.bytes` là tổng dung lượng topic | Giới hạn được áp dụng cho mỗi partition |
| Retention 7 ngày đảm bảo dữ liệu luôn có đủ 7 ngày | `retention.bytes` có thể xóa sớm hơn nếu giới hạn dung lượng đạt trước |
| Segment active có thể bị xóa ngay | Segment đang hoạt động thường phải roll trước khi đủ điều kiện xóa |
| RF=3 nghĩa là chỉ cần dự trù dung lượng một bản sao | Dung lượng vật lý cần tính cả ba replica |
| `delete.retention.ms` giống `retention.ms` | Một cấu hình dành cho tombstone, cấu hình kia điều khiển retention log theo thời gian |
| Consumer group offset retention quyết định thời gian giữ record | Offset metadata và record data có chính sách retention riêng |
| `retention.ms=-1` bảo vệ dữ liệu vĩnh viễn | Nó chỉ bỏ giới hạn thời gian; topic vẫn chịu các thao tác và rủi ro khác |

Một lỗi vận hành phổ biến là đặt `retention.ms` dài nhưng `retention.bytes` quá thấp. Khi lưu lượng tăng, Kafka xóa segment cũ theo giới hạn dung lượng và consumer mất cơ hội replay trước mốc thời gian mong muốn. Hãy kiểm tra đồng thời cả hai config.

## 11. Checklist thiết kế retention

Trước khi triển khai topic, hãy xác nhận:

- `cleanup.policy` có bật `delete` nếu muốn retention theo thời gian/dung lượng.
- `retention.ms` đáp ứng thời gian replay và gián đoạn consumer dự kiến.
- `retention.bytes` đủ lớn theo tốc độ ghi cực đại của từng partition.
- Segment roll (`segment.ms`, `segment.bytes`) phù hợp với tốc độ dữ liệu và yêu cầu cleanup.
- `log.retention.check.interval.ms` được hiểu đúng như chu kỳ kiểm tra, không phải SLA xóa chính xác.
- Dung lượng đã tính replication factor, compression, index và headroom.
- Consumer lag có cảnh báo trước khi log start offset vượt qua offset consumer cần.
- Compacted topic có chính sách tombstone phù hợp với thời gian bootstrap consumer.
- Đội vận hành biết thay đổi retention thấp có thể xóa dữ liệu cũ sớm hơn.
- Có nguồn lưu trữ dài hạn riêng nếu nghiệp vụ cần giữ dữ liệu lâu hơn Kafka retention.

## 12. Câu hỏi tự kiểm tra

1. `retention.ms` và `retention.bytes` điều khiển hai giới hạn nào?
2. Vì sao `retention.bytes` được tính theo từng partition thay vì tổng topic?
3. Nếu cấu hình cả hai giới hạn, điều kiện nào có thể khiến segment bị xóa trước?
4. Vì sao Kafka xóa segment thay vì xóa từng record đúng thời điểm hết hạn?
5. `segment.ms` và `segment.bytes` ảnh hưởng như thế nào đến thời điểm segment được roll?
6. Vì sao active segment có thể làm thời điểm xóa dữ liệu trễ hơn retention đã cấu hình?
7. `cleanup.policy=delete` khác `compact` ở mục tiêu lưu trữ nào?
8. `delete.retention.ms` có vai trò gì với tombstone?
9. Consumer group có thể mất dữ liệu cần đọc như thế nào khi lag vượt quá retention?
10. Khi ước lượng disk capacity, vì sao cần nhân với replication factor và cộng headroom?

## Kết luận

Với `cleanup.policy=delete`, Kafka giữ log theo giới hạn thời gian `retention.ms` và/hoặc dung lượng `retention.bytes` của từng partition. Broker xóa các segment cũ đủ điều kiện sau khi segment được roll và retention cleanup kiểm tra; vì thế thời điểm xóa không chính xác đến từng record. Thiết kế retention cần bắt đầu từ yêu cầu replay, consumer lag và tốc độ ghi, sau đó tính dung lượng với partition, compression, replication factor và headroom. Hiểu rõ các giới hạn này giúp tránh mất dữ liệu trước khi consumer kịp xử lý và giúp cluster sử dụng disk có kế hoạch.
