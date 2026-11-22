# Cấu trúc log segment, offset index và time index

Kafka lưu dữ liệu của mỗi partition dưới dạng một log được chia thành nhiều segment trên đĩa. Khi producer gửi record, broker nối dữ liệu vào segment đang hoạt động. Các segment đã đóng có thể được giữ lại theo retention hoặc được log cleaner xử lý nếu topic bật compaction.

Để tìm một record theo offset hoặc timestamp, Kafka không phải đọc tuần tự toàn bộ log từ đầu. Mỗi segment có các index hỗ trợ định vị nhanh: offset index ánh xạ offset logic sang vị trí byte trong file log, còn time index hỗ trợ tìm offset tương ứng với mốc thời gian. Sau khi tìm được vị trí gần đúng, broker đọc và kiểm tra các record batch trong log để xác định kết quả chính xác.

Hiểu cấu trúc này giúp giải thích vì sao Kafka có thể ghi tuần tự với throughput cao, vì sao index là sparse, vì sao retention xóa theo segment và vì sao offset của consumer khác với vị trí byte trên đĩa.

## 1. Từ topic và partition đến log trên đĩa

Topic là tên luồng dữ liệu mà producer ghi vào. Mỗi topic được chia thành một hoặc nhiều partition. Mỗi partition là một log độc lập, có thứ tự offset riêng và được một broker giữ bản sao leader hoặc follower.

Trên broker, dữ liệu partition được lưu trong các thư mục thuộc cấu hình **log.dirs**. Một thư mục partition thường có tên theo dạng:

~~~text
<topic>-<partition>
~~~

Ví dụ, partition 0 của topic orders có thể được lưu tại:

~~~text
/data/kafka/orders-0/
~~~

Một partition log không nhất thiết là một file lớn duy nhất. Nó được chia thành nhiều log segment. Mỗi segment chứa một dải record liên tiếp theo thứ tự append và có các file index đi kèm.

~~~text
log.dirs/
└── orders-0/
    ├── 00000000000000000000.log
    ├── 00000000000000000000.index
    ├── 00000000000000000000.timeindex
    ├── 00000000000000000000.txnindex
    ├── 00000000000000125000.log
    ├── 00000000000000125000.index
    ├── 00000000000000125000.timeindex
    └── 00000000000000125000.txnindex
~~~

Các con số trong tên file là base offset của segment, được định dạng với độ dài cố định. Ví dụ, segment bắt đầu ở offset 125000 có tên bắt đầu bằng 00000000000000125000.

Một partition thường có nhiều segment đã đóng và một segment đang hoạt động. Segment mới nhất nhận các record được append tiếp theo. Khi segment được roll, nó trở thành segment đã đóng và một segment mới bắt đầu.

## 2. Vòng đời của một log segment

### 2.1. Active segment và closed segment

**Active segment** là segment hiện nhận record mới. Broker ghi record batch nối tiếp vào cuối file .log của segment này. Các index tương ứng được cập nhật khi cần.

Khi segment đạt điều kiện roll, broker đóng segment hiện tại và tạo segment mới. Các điều kiện thường liên quan đến:

- Kích thước segment đạt **segment.bytes**.
- Tuổi segment đạt **segment.ms**.
- Một số điều kiện nội bộ khác khiến segment cần được roll.

Các cấu hình topic thường dùng để kiểm soát vòng đời segment:

| Cấu hình | Ý nghĩa |
|---|---|
| segment.bytes | Kích thước tối đa mục tiêu của một segment trước khi roll |
| segment.ms | Thời gian tối đa trước khi segment được roll theo tuổi |
| segment.jitter.ms | Khoảng biến thiên thời gian roll để tránh nhiều partition roll đồng thời |
| retention.ms | Thời gian giữ dữ liệu theo chính sách delete |
| retention.bytes | Giới hạn dung lượng log theo partition trước khi xóa segment cũ |
| cleanup.policy | Chính sách dọn dữ liệu: delete, compact hoặc kết hợp |

Giá trị mặc định của broker có thể được topic ghi đè bằng cấu hình riêng. Cần kiểm tra cấu hình hiệu lực của topic thay vì giả định mọi topic đều dùng cùng giá trị.

### 2.2. Roll segment không phải xóa dữ liệu

Roll chỉ chuyển segment hiện tại sang trạng thái đã đóng và bắt đầu segment tiếp theo. Record cũ vẫn còn trên đĩa.

Ví dụ:

~~~text
Trước khi roll:
  00000000000000000000.log  <- active

Sau khi roll:
  00000000000000000000.log  <- closed
  00000000000000125000.log  <- active
~~~

Segment đã đóng có thể được retention xóa hoặc log cleaner compact tùy cleanup policy. Vì vậy, việc xuất hiện file segment mới không có nghĩa record trong segment cũ đã bị xóa.

### 2.3. Một segment gồm nhiều file

Các file thường gặp có cùng base offset:

| File | Vai trò |
|---|---|
| .log | Chứa record batch và dữ liệu thực tế của segment |
| .index | Offset index, hỗ trợ ánh xạ offset sang vị trí byte trong .log |
| .timeindex | Time index, hỗ trợ tìm offset theo timestamp |
| .txnindex | Lưu thông tin transaction bị abort liên quan đến segment để hỗ trợ xử lý read_committed |

Không phải mọi segment ở mọi thời điểm đều có đủ tất cả file phụ trợ theo cùng một trạng thái. Một số file được tạo, mở rộng hoặc phục hồi trong quá trình broker vận hành. Cấu trúc chi tiết có thể thay đổi theo phiên bản Kafka.

## 3. File log .log chứa gì?

File .log chứa các record batch được append theo thứ tự. Trong các phiên bản Kafka hiện đại, record thường được nhóm thành batch để giảm overhead mạng, I/O và CPU. Một batch có thể chứa nhiều record và các metadata như:

- Base offset và offset delta của các record trong batch.
- Timestamp và timestamp type.
- Producer ID, epoch và sequence khi batch được ghi bởi idempotent hoặc transactional producer.
- Compression codec nếu batch được nén.
- Control flag hoặc thông tin transaction khi phù hợp.
- Key, value và headers của từng record.

Kafka ghi dữ liệu theo hướng append vào cuối log. Mô hình này hỗ trợ ghi tuần tự hiệu quả và tận dụng page cache của hệ điều hành.

Offset là vị trí logic của record trong partition, không phải byte offset của file. Một record có offset 125010 không có nghĩa record nằm ở byte 125010 trong file .log. Vị trí byte được tra thông qua offset index.

### Offset không nhất thiết liên tục trong dữ liệu consumer nhìn thấy

Offset tăng theo log của partition, nhưng consumer không nên giả định rằng mọi số offset đều tương ứng với một record ứng dụng mà nó nhận được.

Có thể xuất hiện khoảng trống offset do:

- Log compaction loại bỏ các record cũ nhưng giữ lại offset của record còn tồn tại.
- Transaction bị abort; consumer dùng read_committed không nhận các record thuộc transaction đã abort.
- Các control batch hoặc cơ chế nội bộ của Kafka chiếm offset trong log.
- Retention làm thay đổi log start offset và loại bỏ segment cũ.

Do đó, offset là tọa độ logic trong partition. Nó không phải số thứ tự liên tục của những message mà một consumer cụ thể đã xử lý.

## 4. Offset index: ánh xạ offset sang vị trí byte

Offset index nằm trong file .index. Nó giúp broker tìm nhanh vị trí gần đúng của một offset trong file .log.

Một entry của offset index về cơ bản chứa:

- Relative offset: offset tương đối so với base offset của segment.
- Physical position: vị trí byte trong file .log nơi batch/record tương ứng bắt đầu.

Ví dụ minh họa:

~~~text
Segment base offset = 125000

offset index:
  relativeOffset  -> physicalPosition
  0               -> 0
  128             -> 8192
  256             -> 16384
  384             -> 24576
~~~

Nếu broker cần đọc offset 125270, nó không cần tìm entry đúng 125270. Nó tìm entry gần nhất có relative offset không lớn hơn 270, sau đó bắt đầu đọc từ physical position tương ứng và quét tiếp các record batch cho đến khi tìm được offset cần thiết.

### 4.1. Vì sao offset index là sparse?

Kafka không ghi một entry index cho từng record. Index là sparse (thưa), nghĩa là chỉ ghi entry theo một khoảng dữ liệu nhất định.

Broker dùng cấu hình **log.index.interval.bytes** để kiểm soát khoảng byte append giữa các lần thêm entry vào offset index. Vì vậy:

- Index nhỏ hơn nhiều so với file log.
- Việc tra cứu cần hai giai đoạn: tìm entry gần nhất trong index rồi scan phần log còn lại.
- Tăng mật độ index có thể giảm lượng dữ liệu phải scan nhưng làm index chiếm nhiều dung lượng hơn.
- Giảm mật độ index tiết kiệm dung lượng nhưng có thể làm tăng lượng dữ liệu phải đọc khi tìm offset.

Đây là đánh đổi giữa không gian lưu trữ và chi phí tìm kiếm. Index không cần chứa mọi offset để việc định vị vẫn hiệu quả.

### 4.2. Quy trình tìm record theo offset

~~~mermaid
flowchart TD
    A["Consumer yêu cầu offset N"] --> B["Broker xác định segment chứa N"]
    B --> C["Tra offset index của segment"]
    C --> D["Tìm entry có relative offset gần nhất nhưng <= N"]
    D --> E["Lấy physical byte position"]
    E --> F["Đọc .log từ vị trí đó"]
    F --> G["Scan record batch và kiểm tra offset"]
    G --> H["Trả dữ liệu phù hợp cho consumer"]
~~~

Quy trình thực tế còn xét log start offset, log end offset, transaction visibility, replica state và các điều kiện fetch khác. Sơ đồ mô tả phần định vị cơ bản.

### 4.3. Base offset và relative offset

Mỗi segment có base offset riêng. Offset index lưu relative offset để giảm kích thước giá trị phải lưu.

Ví dụ:

- Segment bắt đầu tại offset 125000.
- Record cần tìm có offset 125270.
- Relative offset tương ứng là 270.

Khi tìm kiếm, broker kết hợp base offset của segment với relative offset trong index để xác định offset logic, sau đó dùng physical position để đọc file log.

## 5. Time index: tìm offset theo timestamp

Offset index trả lời câu hỏi: “Offset N nằm ở đâu trong file log?”

Time index trả lời một câu hỏi khác: “Từ mốc thời gian T, nên bắt đầu đọc ở offset nào?”

Time index nằm trong file .timeindex. Entry của nó lưu thông tin timestamp và offset tương ứng. Tương tự offset index, time index là sparse và giúp broker định vị một vùng log phù hợp trước khi scan record thực tế.

Ví dụ minh họa:

~~~text
time index:
  timestamp (ms)     -> offset
  1730000000000      -> 125000
  1730000060000      -> 125180
  1730000120000      -> 125360
  1730000180000      -> 125540
~~~

Khi client yêu cầu tìm offset theo timestamp, broker sử dụng metadata của segment và time index để tìm vị trí ứng viên, sau đó kiểm tra record trong log để trả offset phù hợp theo semantics của API.

### 5.1. Timestamp của record đến từ đâu?

Kafka hỗ trợ hai cách diễn giải timestamp phổ biến:

- **CreateTime:** timestamp do producer cung cấp khi tạo record.
- **LogAppendTime:** broker gán timestamp khi append record vào log.

Cấu hình **message.timestamp.type** quyết định loại timestamp được sử dụng ở phía broker/topic theo cấu hình phiên bản và môi trường.

Với CreateTime, timestamp có thể phản ánh thời điểm nghiệp vụ xảy ra nhưng phụ thuộc đồng hồ và dữ liệu do producer gửi. Với LogAppendTime, timestamp phản ánh thời điểm broker ghi record, thuận tiện hơn khi cần quan sát thời gian tiếp nhận tại Kafka.

Time index hỗ trợ tìm kiếm theo timestamp; nó không biến partition thành một cơ sở dữ liệu có thể truy vấn tùy ý theo thời gian, cũng không tạo ra một thứ tự toàn cục giữa các partition.

### 5.2. Ví dụ tìm offset bằng KafkaConsumer

Java Kafka Consumer cung cấp **offsetsForTimes** để tra offset đầu tiên phù hợp với timestamp yêu cầu trên từng partition:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.OffsetAndTimestamp;
import org.apache.kafka.common.TopicPartition;

public class TimestampSeekExample {
    public static void seekToTime(
            Consumer<String, String> consumer) {
        TopicPartition partition =
            new TopicPartition("orders", 0);

        long timestamp = Instant
            .parse("2026-01-15T10:00:00Z")
            .toEpochMilli();

        consumer.assign(List.of(partition));

        Map<TopicPartition, OffsetAndTimestamp> result =
            consumer.offsetsForTimes(
                Map.of(partition, timestamp)
            );

        OffsetAndTimestamp match = result.get(partition);
        if (match != null) {
            consumer.seek(partition, match.offset());
        }
    }
}
~~~

Nếu không tìm thấy offset có timestamp phù hợp, giá trị trả về cho partition có thể là null. Ứng dụng cần xử lý trường hợp này, ví dụ giữ vị trí hiện tại, seek đến end hoặc báo không có dữ liệu theo chính sách nghiệp vụ.

**offsetsForTimes** là API tiện dụng cho việc tra cứu; broker thực hiện phần tìm kiếm dựa trên timestamp và log/index. API không yêu cầu ứng dụng tự đọc file .timeindex.

## 6. Broker tìm record như thế nào?

Khi consumer fetch từ một partition tại offset N, broker cần xác định segment chứa N.

Một cách nhìn khái quát:

1. Broker kiểm tra log start offset và log end offset để biết phạm vi dữ liệu hiện có.
2. Broker xác định segment có base offset phù hợp với N.
3. Broker dùng offset index của segment để tìm physical position gần nhất.
4. Broker đọc file .log từ vị trí đó.
5. Broker scan record batch, bỏ qua phần trước N và áp dụng điều kiện visibility nếu có.
6. Broker trả các record phù hợp trong giới hạn fetch request.

Với truy vấn theo timestamp, broker sử dụng time index để tìm offset ứng viên, rồi tiếp tục đọc log để xác minh.

Hai index hỗ trợ hai loại tìm kiếm khác nhau:

| Thành phần | Đầu vào | Kết quả hỗ trợ | File |
|---|---|---|---|
| Offset index | Offset logic | Vị trí byte gần đúng trong segment | .index |
| Time index | Timestamp | Offset ứng viên tương ứng | .timeindex |
| Log segment | Vị trí byte/offset | Record batch thực tế | .log |
| Transaction index | Thông tin transaction abort | Hỗ trợ bỏ qua vùng dữ liệu thuộc transaction abort khi đọc read_committed | .txnindex |

Index chỉ giúp tìm nhanh. Dữ liệu record thực tế vẫn nằm trong file .log.

## 7. Segment rolling, retention và compaction

Segment là đơn vị quan trọng trong vòng đời dữ liệu. Kafka thường thao tác dọn dữ liệu theo segment thay vì cắt bỏ tùy ý từng record ở giữa file log.

### 7.1. Retention theo thời gian hoặc dung lượng

Nếu topic dùng **cleanup.policy=delete**, Kafka có thể xóa segment cũ khi vượt **retention.ms** hoặc **retention.bytes**.

Ví dụ:

~~~text
orders-0/
  segment 0: offset 0 - 124999       <- cũ, đủ điều kiện xóa
  segment 1: offset 125000 - 249999  <- còn giữ
  segment 2: offset 250000 - ...     <- active
~~~

Khi segment cũ bị xóa, log start offset có thể tiến lên. Consumer đang giữ committed offset thấp hơn log start offset có thể gặp OffsetOutOfRangeException hoặc cần áp dụng auto.offset.reset tùy cấu hình.

**retention.bytes** được áp dụng theo log partition, không phải một giới hạn tổng cho toàn bộ topic. Tổng dung lượng topic còn phụ thuộc số partition và replication factor.

### 7.2. Log compaction

Nếu topic dùng **cleanup.policy=compact**, Kafka giữ lại trạng thái mới nhất theo key theo quá trình compact nền. Log cleaner xử lý các segment đã đóng và có thể tạo các segment đã compact. Active segment đang nhận ghi không được xem như một segment đã hoàn tất để cleaner compact ngay lập tức.

Ví dụ, cùng một key xuất hiện nhiều lần:

~~~text
offset 10: key=customer-42, value=ACTIVE
offset 25: key=customer-42, value=SUSPENDED
offset 41: key=customer-42, value=ACTIVE
~~~

Sau khi compaction chạy, Kafka có thể giữ record mới nhất của key trong phần log đã được compact. Việc dọn diễn ra nền nên trong một khoảng thời gian, record cũ vẫn có thể tồn tại.

Tombstone (key khác null, value null) đánh dấu xóa trạng thái của key trong compacted topic. Tombstone được giữ trong khoảng thời gian cấu hình trước khi có thể bị loại bỏ ở lượt compaction sau.

### 7.3. Kết hợp compact và delete

Topic có thể cấu hình **cleanup.policy=compact,delete**. Khi đó:

- Compaction loại bỏ các phiên bản cũ theo key.
- Retention có thể xóa các segment cũ theo thời gian hoặc dung lượng.
- Tombstone vẫn tuân theo thời gian lưu giữ tombstone.

Cần hiểu rõ mục tiêu lưu dữ liệu trước khi chọn cleanup policy. Event history cần giữ mọi sự kiện trong một khoảng thời gian có thể dùng delete. Topic lưu trạng thái mới nhất theo key thường dùng compact. Một topic có thể kết hợp hai cơ chế nếu yêu cầu dữ liệu phù hợp.

## 8. Consumer committed offset khác offset index

Đây là điểm dễ nhầm khi tìm hiểu storage.

**Offset index** là file phụ trợ của partition log trên broker. Nó giúp broker ánh xạ offset logic sang vị trí byte trong file segment.

**Committed offset** là tiến độ mà một consumer group đã xác nhận. Kafka lưu tiến độ consumer group trong internal topic **__consumer_offsets**.

Hai loại offset có mục đích khác nhau:

| Tiêu chí | Offset index | Consumer committed offset |
|---|---|---|
| Nằm ở đâu? | File .index trong thư mục partition log | Internal topic __consumer_offsets |
| Thuộc về ai? | Segment của một partition | Consumer group và topic partition |
| Dùng để làm gì? | Tìm vị trí record trên đĩa | Xác định tiến độ đọc đã commit |
| Có phải record data không? | Không, là index file | Là metadata nội bộ do Kafka lưu |
| Ai sử dụng? | Broker khi tra cứu log | Consumer group coordinator và consumer |

Committed offset thường biểu diễn vị trí tiếp theo mà group sẽ đọc sau khi phục hồi. Ứng dụng cần quản lý thời điểm commit phù hợp với việc xử lý nghiệp vụ để tránh mất record hoặc xử lý trùng.

Không nên tìm committed offset trong file .index của topic dữ liệu. Hai cơ chế này có quan hệ với nhau khi consumer tiếp tục đọc, nhưng được lưu và quản lý riêng.

## 9. Index được tạo, mở rộng và phục hồi như thế nào?

Offset index và time index được broker cập nhật trong quá trình append. Vì index là sparse, chúng có kích thước nhỏ hơn đáng kể so với log data.

Một số cấu hình broker có liên quan:

| Cấu hình | Tác động |
|---|---|
| log.dirs | Các thư mục gốc dùng lưu partition log |
| log.index.interval.bytes | Khoảng byte append giữa các entry offset index |
| log.index.size.max.bytes | Giới hạn kích thước offset index |
| log.segment.bytes | Kích thước segment mặc định ở broker |
| log.roll.ms | Thời gian roll segment mặc định ở broker |
| log.retention.ms | Retention mặc định theo thời gian |
| log.retention.bytes | Retention mặc định theo dung lượng |

Tên cấu hình mặc định ở broker có thể có cấu hình topic tương ứng như **segment.bytes**, **segment.ms**, **retention.ms** và **retention.bytes**. Cần phân biệt broker default với topic override khi đọc cấu hình thực tế.

Nếu broker phát hiện index bị thiếu hoặc không nhất quán trong quá trình khởi động/recovery, Kafka có thể quét log để xây dựng lại index. Quá trình này tốn I/O và thời gian tùy kích thước dữ liệu.

Không nên tự ý xóa hoặc sửa .index, .timeindex khi broker đang hoạt động để xử lý lỗi. Hãy đọc log broker và sử dụng quy trình phục hồi phù hợp với phiên bản Kafka, trạng thái replica và bản sao dữ liệu.

## 10. Quan sát và kiểm tra log segment

### 10.1. Kiểm tra thư mục log trên broker

Có thể dùng **log.dirs** trong cấu hình broker để xác định thư mục lưu trữ. Mỗi partition directory chứa các segment và index tương ứng.

Ví dụ cấu trúc:

~~~text
/data/kafka/
  orders-0/
  orders-1/
  payments-0/
  payments-1/
~~~

Không nên suy luận toàn bộ tình trạng cluster chỉ từ một thư mục. Cần đối chiếu replica assignment, leader, ISR và log directory health.

### 10.2. Xem log directory của broker

Công cụ **kafka-log-dirs.sh** giúp xem thông tin log directory và replica được lưu trên broker:

~~~bash
kafka-log-dirs.sh \
  --bootstrap-server broker-1:9092 \
  --describe \
  --broker-list 1
~~~

Kết quả có thể hỗ trợ kiểm tra kích thước replica và thư mục lưu trữ. Tùy phiên bản Kafka, định dạng đầu ra và tham số có thể khác.

### 10.3. Đọc nội dung segment bằng kafka-dump-log

Đối với file segment trên broker, công cụ **kafka-dump-log.sh** có thể giúp phân tích record batch và dữ liệu log:

~~~bash
kafka-dump-log.sh \
  --files /data/kafka/orders-0/00000000000000000000.log \
  --print-data-log
~~~

Đây là thao tác kiểm tra file trên filesystem của broker. Cần dùng đúng đường dẫn, quyền đọc và phiên bản công cụ tương thích với dữ liệu. Không sửa file segment bằng tay.

### 10.4. Những chỉ số nên theo dõi

| Chỉ số hoặc hiện tượng | Ý nghĩa cần xem xét |
|---|---|
| Disk usage tăng nhanh | Tốc độ ghi lớn, retention chưa dọn hoặc segment roll không phù hợp |
| Nhiều segment nhỏ | Segment roll quá thường xuyên hoặc lưu lượng thấp, gây tăng metadata/file overhead |
| Log directory gần đầy | Cần xem retention, dung lượng replica và phân bố partition |
| Fetch latency tăng | Đĩa, page cache, broker load hoặc network có thể là nút thắt |
| Consumer OffsetOutOfRange | Offset group đã thấp hơn log start hoặc cao hơn phạm vi hiện có |
| Log recovery kéo dài | Broker phải scan nhiều log/index hoặc storage có vấn đề |
| Compaction lag tăng | Cleaner không theo kịp tốc độ ghi hoặc tài nguyên cleaner hạn chế |

Một index lớn hơn không nhất thiết làm hệ thống nhanh hơn. Cần theo dõi cả lượng dữ liệu scan, cache hit, disk latency và request latency khi điều chỉnh index interval.

## 11. Ví dụ tổng hợp: định vị một đơn hàng theo offset và thời gian

Giả sử topic orders có partition 0 và chứa nhiều segment. Một consumer cần đọc đơn hàng từ offset 250100.

Broker sẽ:

1. Xác định segment có base offset phù hợp với 250100.
2. Tra file .index để tìm entry có relative offset gần nhất nhưng không vượt quá offset mục tiêu.
3. Lấy physical position trong .log.
4. Scan record batch cho đến offset 250100 và trả dữ liệu theo điều kiện fetch.

Nếu ứng dụng muốn đọc từ 10:00 ngày 15/01/2026, nó có thể gọi **offsetsForTimes** cho partition 0. Broker tra .timeindex để tìm offset ứng viên có timestamp phù hợp, rồi scan log để xác định offset trả về.

Hai truy vấn khác nhau:

- Tìm theo offset là định vị theo thứ tự log của partition.
- Tìm theo timestamp là tìm điểm bắt đầu dựa trên timestamp record.

Nếu dữ liệu được gửi với CreateTime và đồng hồ producer không đồng bộ, timestamp có thể không phản ánh chính xác thứ tự nghiệp vụ. Nếu cần thời gian tiếp nhận tại broker, cân nhắc LogAppendTime và hiểu rõ ảnh hưởng của cấu hình timestamp.

## 12. Những nhầm lẫn thường gặp

- **“Offset là vị trí byte trong file.”** Offset là tọa độ logic của record trong partition; offset index mới ánh xạ nó sang vị trí byte.
- **“Mỗi record có một entry trong offset index.”** Offset index là sparse, chỉ lưu các điểm định vị theo khoảng dữ liệu.
- **“Time index lưu toàn bộ record theo thời gian.”** Time index chỉ lưu các entry timestamp-offset để tìm vị trí ứng viên; record vẫn nằm trong .log.
- **“Roll segment đồng nghĩa xóa segment cũ.”** Roll chỉ đóng segment hiện tại và mở segment mới.
- **“Retention xóa từng record chính xác theo thời điểm.”** Với cleanup policy delete, Kafka thường xóa cả segment khi segment đủ điều kiện.
- **“Compaction xảy ra ngay khi producer gửi record mới.”** Log cleaner làm việc nền, chủ yếu trên các segment đã đóng.
- **“Committed offset của consumer nằm trong .index.”** Committed offset được lưu trong __consumer_offsets; .index thuộc partition log dữ liệu.
- **“Offset không liên tục nghĩa là dữ liệu bị mất.”** Compaction, transaction và control batch có thể tạo khoảng trống offset mà không đồng nghĩa broker làm mất dữ liệu.
- **“Có thể sửa index hoặc segment bằng tay khi broker chạy.”** Thao tác trực tiếp có thể làm hỏng dữ liệu; hãy dùng công cụ và quy trình phục hồi phù hợp.

## 13. Kết luận

Kafka tổ chức dữ liệu partition thành các log segment để ghi tuần tự, quản lý retention và compaction theo từng phần. File .log chứa record batch; .index giúp ánh xạ offset logic sang vị trí byte; .timeindex giúp tìm offset theo timestamp; .txnindex hỗ trợ xử lý transaction bị abort trong các luồng đọc phù hợp.

Offset index và time index là các cấu trúc định vị thưa, không thay thế dữ liệu record. Broker tìm entry phù hợp trong index rồi scan log để xác định kết quả chính xác. Segment rolling tạo ranh giới cho retention và compaction; consumer committed offset lại được lưu riêng trong __consumer_offsets.

Khi vận hành Kafka, hãy theo dõi segment count, dung lượng log directory, retention, compaction lag, index và disk latency. Hiểu rõ mối quan hệ giữa log, segment và index giúp chẩn đoán nhanh vấn đề đọc dữ liệu, offset ngoài phạm vi, storage tăng nhanh và quá trình phục hồi broker.
