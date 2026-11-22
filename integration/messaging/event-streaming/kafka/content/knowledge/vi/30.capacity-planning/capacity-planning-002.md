# Tính dung lượng theo retention, replication và hệ số nén

Hoạch định dung lượng Kafka bắt đầu từ lượng dữ liệu thực sự được ghi vào log và khoảng thời gian phải giữ dữ liệu. Sau đó mới tính ảnh hưởng của compression, số bản sao replication, phân bố partition, index/segment và phần dung lượng cần dự phòng.

Một phép tính chỉ lấy kích thước payload nhân với số ngày retention thường thiếu nhiều yếu tố. Payload được serialize thành record, producer có thể nén theo batch, broker lưu nhiều replica, retention được thực thi theo segment và dung lượng giữa các broker không phải lúc nào cũng cân bằng. Bài học này xây dựng mô hình tính từ từng topic, sau đó tổng hợp thành dung lượng cluster và dung lượng disk cho mỗi broker.

## 1. Mục tiêu hoạch định dung lượng

Sau bài học, người học có thể:

- Ước lượng tốc độ dữ liệu đầu vào từ số record/giây và kích thước record đã serialize.
- Đo và áp dụng hệ số nén dựa trên workload thực tế.
- Tính dung lượng theo retention.ms, retention.bytes, số partition và replication factor.
- Phân biệt dung lượng một bản log logic với tổng dung lượng replica trên cluster.
- Ước lượng dung lượng disk cho mỗi broker, có headroom và khả năng chịu lỗi broker.
- Đánh giá ảnh hưởng của segment, log compaction, tiered storage, network và throughput.
- Kiểm chứng dự báo bằng metric JMX, log directory và kết quả chạy thử.

Phép tính storage không thay thế capacity test. Sau khi dự báo dung lượng, cần thử tải với kích thước record, codec, batch, partition, retention và replication gần với production.

## 2. Các đại lượng cần thu thập

Trước khi tính, hãy lập inventory theo topic. Mỗi topic có thể có traffic, retention, compression và replication khác nhau.

| Đại lượng | Ký hiệu | Đơn vị | Ý nghĩa |
|---|---|---|---|
| Tốc độ record | lambda | record/s | Số record được tạo trong một giây |
| Kích thước record đã serialize | S | byte/record | Key, value, headers và phần framing liên quan |
| Dữ liệu đầu vào chưa nén | R | byte/s | lambda nhân S |
| Hệ số nén | C | không đơn vị | Compressed bytes / uncompressed bytes |
| Tốc độ dữ liệu sau nén | D | byte/s | R nhân C |
| Retention theo thời gian | T | giây | Thời gian giữ log |
| Số partition | P | partition | Số partition của topic |
| Retention theo dung lượng | B | byte/partition | Giới hạn kích thước log mỗi partition |
| Replication factor | RF | replica | Số bản sao của mỗi partition |
| Số broker | N | broker | Số broker lưu replica |
| Hệ số overhead | H | không đơn vị | Index, segment, metadata và phần phát sinh đã đo |
| Hệ số tăng trưởng | G | không đơn vị | Tăng trưởng traffic và độ trễ cleanup dự kiến |
| Hệ số phân bố | K | không đơn vị | Dự phòng cho partition/broker skew |
| Mức sử dụng disk mục tiêu | U | tỷ lệ | Tỷ lệ disk tối đa dự kiến dùng cho dữ liệu |

**Quy ước hệ số nén trong bài:** C = compressed_bytes / uncompressed_bytes. Ví dụ C = 0,40 nghĩa là dữ liệu sau nén còn 40% kích thước ban đầu, tương đương giảm 60%. Cách định nghĩa này tránh nhầm lẫn với cách gọi tỷ lệ nén 2,5:1.

### 2.1. Đo kích thước record đúng cách

Không lấy riêng số ký tự JSON hoặc kích thước business object làm kích thước record. Cần tính dữ liệu sau serializer, gồm:

- Serialized key.
- Serialized value.
- Record headers.
- Schema/envelope metadata nếu có.
- Record/batch framing và overhead liên quan.

Nếu record có kích thước không đồng đều, lấy trung bình có trọng số theo traffic và đồng thời kiểm tra p95/p99. Một vài record rất lớn có thể làm thay đổi batch size, memory và network dù không làm thay đổi nhiều kích thước trung bình.

### 2.2. Dùng traffic trung bình và traffic đỉnh đúng mục đích

- Dùng lưu lượng trung bình trong cửa sổ retention để tính dung lượng log giữ trong nhiều ngày.
- Dùng peak hoặc p95/p99 throughput để kiểm tra năng lực network, disk I/O, CPU và khả năng xử lý burst.
- Dùng tốc độ tăng trưởng dự báo để ước lượng nhu cầu ở thời điểm tương lai.

Không nhân peak một vài giây với toàn bộ số ngày retention nếu peak không kéo dài. Cách đó có thể làm dự báo storage lớn hơn thực tế rất nhiều. Ngược lại, chỉ dùng trung bình tháng có thể bỏ qua ngày cao điểm hoặc mùa vụ.

## 3. Tính tốc độ dữ liệu đầu vào

Với một topic:

~~~text
R = lambda * S
~~~

Trong đó:

- lambda: record được tạo mỗi giây.
- S: kích thước record đã serialize, tính bằng byte.
- R: tốc độ byte chưa nén.

Ví dụ có 8.000 record/giây, mỗi record trung bình 2.000 byte:

~~~text
R = 8.000 * 2.000
  = 16.000.000 byte/s
  = 16 MB/s
~~~

Dùng đơn vị nhất quán. Trong bài này, MB, GB, TB là đơn vị thập phân: 1 MB = 1.000.000 byte; 1 TB = 1.000.000.000.000 byte. Nếu công cụ vận hành hiển thị MiB/GiB/TiB, hãy đổi đơn vị trước khi so sánh với disk.

Với nhiều topic, tính riêng từng topic rồi cộng tốc độ:

~~~text
R_cluster = R_topic_1 + R_topic_2 + ... + R_topic_n
~~~

Không cộng các consumer group vào tốc độ ghi storage. Consumer group làm tăng lượng dữ liệu broker phải phục vụ qua network, nhưng không tự tạo thêm một bản log được lưu trong Kafka.

## 4. Đo hệ số nén

### 4.1. Công thức

~~~text
C = compressed_bytes / uncompressed_bytes

D = R * C
~~~

Ví dụ:

~~~text
R = 16 MB/s
C = 0,40

D = 16 * 0,40
  = 6,4 MB/s
~~~

Kafka lưu record batches. Producer nén batch thay vì nén từng record độc lập, vì vậy hiệu quả nén phụ thuộc vào kích thước batch, linger.ms, dữ liệu lặp lại và entropy của payload.

### 4.2. Các codec

| Codec | Đặc điểm thực tế cần đánh giá |
|---|---|
| none | Không nén; CPU thấp hơn nhưng network và disk cần nhiều dung lượng |
| gzip | Có thể nén tốt nhưng thường tốn CPU hơn |
| snappy | Tốc độ nén/giải nén nhanh, tỷ lệ nén phụ thuộc dữ liệu |
| lz4 | Thường phù hợp workload cần throughput cao và độ trễ thấp |
| zstd | Có thể đạt tỷ lệ nén tốt; CPU phụ thuộc compression level |

Không có một hệ số nén đúng cho mọi topic. JSON có trường lặp lại thường nén khác với ảnh, file nhị phân, payload đã mã hóa hoặc dữ liệu ngẫu nhiên.

Hãy lấy mẫu từ production/staging, dùng cùng serializer, key/value, headers, batch size, codec, compression level và cấu hình producer dự kiến. Ghi lại:

- Byte trước nén.
- Byte sau nén.
- Compression ratio.
- CPU producer và broker.
- Produce latency.
- Network throughput.
- Kích thước log thực tế sau khi ghi.

Có thể dùng metric compression-rate-avg của producer để theo dõi xu hướng, nhưng khi lập capacity model nên đối chiếu với kích thước batch và log thực tế. Không mặc định giá trị của một metric client luôn bằng chính xác tỷ lệ byte trên disk của topic.

### 4.3. Cấu hình producer và broker

Ví dụ producer:

~~~properties
compression.type=zstd
linger.ms=20
batch.size=65536
~~~

batch.size tính bằng byte. linger.ms tạo thêm thời gian để gom record vào batch; điều này có thể cải thiện nén nhưng cũng ảnh hưởng latency. Cần benchmark thay đổi từng tham số với workload thật.

Ở topic, compression.type=producer giữ codec do producer sử dụng. Nếu cấu hình topic thành codec khác, broker có thể phải giải nén và nén lại batch theo codec được yêu cầu. Hãy tính cả CPU và network của việc recompression nếu sử dụng.

Ví dụ topic giữ codec producer:

~~~properties
compression.type=producer
~~~

Producer và topic có cấu hình nén khác nhau không đồng nghĩa với việc broker luôn lưu đúng số byte mà producer đã gửi. Hãy xác nhận cấu hình broker/topic và đo kích thước log sau khi ghi.

## 5. Tính dung lượng một bản log theo retention

### 5.1. Retention theo thời gian

Nếu topic dùng cleanup.policy=delete và giữ dữ liệu trong T giây:

~~~text
L_time = D * T
~~~

Với ví dụ ở trên, retention 7 ngày:

~~~text
T = 7 * 24 * 60 * 60
  = 604.800 giây

L_time = 6,4 MB/s * 604.800 s
       = 3.870.720 MB
       = 3.870,72 GB
       = 3,87072 TB
~~~

Đây là dung lượng gần đúng của một bản log logic trước khi nhân replication factor và cộng overhead.

### 5.2. Retention theo dung lượng

retention.bytes là giới hạn theo từng partition. Nếu topic có P partition và giới hạn B byte cho mỗi partition:

~~~text
L_size = P * B
~~~

Ví dụ topic có 48 partition, mỗi partition đặt retention.bytes=100 GB:

~~~text
L_size = 48 * 100 GB
       = 4.800 GB
       = 4,8 TB
~~~

Đây là tổng giới hạn theo kích thước cho một bản log logic của topic, giả định traffic phân bố tương đối đều và cleanup đạt được mục tiêu.

Nếu chỉ đặt retention.bytes trên topic, không được hiểu nhầm đó là giới hạn toàn topic. Hãy nhân với số partition để ước lượng giới hạn topic.

### 5.3. Khi cấu hình cả retention.ms và retention.bytes

Với cleanup.policy=delete, Kafka xóa các segment cũ khi đạt giới hạn thời gian hoặc kích thước. Có thể ước lượng dung lượng được giữ bằng giới hạn đến trước:

~~~text
L_logical ~= min(D * T, P * B)
~~~

Công thức này giả định traffic phân bố gần đều giữa các partition. Với partition j có tốc độ dữ liệu sau nén D_j và giới hạn B_j, công thức chi tiết hơn là:

~~~text
L_logical ~= sum(j = 1..P, min(D_j * T, B_j))
~~~

Khi D_j = D/P và B_j = B cho mọi partition, công thức chi tiết rút gọn về min(D*T, P*B).

Nếu một trong hai giới hạn là -1, xem giới hạn đó là không áp dụng.

Ví dụ:

- Tốc độ nén: 6,4 MB/s.
- Retention time: 7 ngày.
- Số partition: 48.
- retention.bytes: 100 GB/partition.

Ta có:

~~~text
L_time = 3,87072 TB
L_size = 4,8 TB

L_logical ~= min(3,87072; 4,8)
          = 3,87072 TB
~~~

Trong ví dụ này, retention theo thời gian đạt trước giới hạn dung lượng.

Nếu retention.bytes=50 GB:

~~~text
L_size = 48 * 50 GB = 2,4 TB

L_logical ~= min(3,87072; 2,4)
          = 2,4 TB
~~~

Khi đó giới hạn kích thước làm dữ liệu cũ bị xóa trước 7 ngày. Nếu yêu cầu nghiệp vụ bắt buộc phải replay đủ 7 ngày, không đặt giới hạn size thấp hơn lượng dữ liệu thực tế phát sinh trong 7 ngày.

### 5.4. Phân bố record giữa partition

Công thức D * T / P giả định traffic chia đều. Thực tế có thể lệch do:

- Key có độ phổ biến khác nhau.
- Một số key tạo nhiều event hơn.
- Producer không có key hoặc dùng partitioner không phù hợp.
- Một partition nhận workload lớn hơn do cách phân vùng dữ liệu.

Nếu một partition nhận gấp đôi traffic trung bình, nó có thể chạm retention.bytes sớm hơn. Hãy kiểm tra bytes in và log size theo từng partition. Hệ số skew trong phần sizing broker sẽ dự phòng cho độ lệch này.

Retention cũng cần bao phủ thời gian consumer có thể ngừng hoạt động, thời gian phát hiện/khắc phục sự cố và khoảng replay/backfill. Nếu retention ngắn hơn outage cộng thời gian phục hồi, consumer có thể mất khả năng đọc lại toàn bộ dữ liệu cần thiết.

## 6. Phân biệt log logic và dung lượng replica

Replication factor là số bản sao của mỗi partition, bao gồm leader và follower. Nếu một topic có dung lượng log logic L_logical và replication factor RF:

~~~text
L_physical_cluster = L_logical * RF
~~~

Ví dụ:

~~~text
L_logical = 3,87072 TB
RF = 3

L_physical_cluster = 3,87072 * 3
                   = 11,61216 TB
~~~

Như vậy:

- Một bản log logic: khoảng 3,87 TB.
- Tổng các bản sao trên cluster: khoảng 11,61 TB.

Replication factor 3 không có nghĩa topic có 3 lần dữ liệu logic khi consumer đọc. Nó có nghĩa Kafka lưu ba replica để tăng khả năng chịu lỗi và tính sẵn sàng.

min.insync.replicas và producer acks ảnh hưởng điều kiện xác nhận ghi và khả năng tiếp tục ghi khi replica lỗi; chúng không tạo thêm một bản copy vật lý ngoài replication factor. Dùng RF để tính số bản sao, sau đó kiểm tra min ISR riêng cho durability/availability.

### 6.1. Phân bổ replica trên broker

Giả sử cluster có 6 broker và topic có 48 partition, replication factor 3:

~~~text
Tổng replica partition = 48 * 3 = 144

Replica trung bình mỗi broker = 144 / 6 = 24
~~~

Nếu phân bố cân bằng:

~~~text
Dung lượng trung bình mỗi broker
= 11,61216 TB / 6
= 1,93536 TB
~~~

Đây mới là dung lượng log cơ sở. Chưa cộng index, segment, metadata, tăng trưởng và headroom.

### 6.2. Rack awareness

Nếu cần chịu lỗi rack, cấu hình broker rack và phân bố replica trên các rack độc lập. RF=3 trên ba broker cùng một rack không bảo vệ được dữ liệu trước sự cố mất toàn bộ rack.

Capacity model cần xác nhận:

- Số broker trong mỗi rack.
- Số replica của từng partition trên từng rack.
- Disk capacity còn lại sau khi một broker hoặc rack mất.
- Khả năng đặt lại replica khi cluster ở trạng thái degraded.

Không chỉ chia tổng dung lượng cho số broker rồi kết luận mọi broker đều đủ disk. Replica placement và tải leader có thể không đồng đều.

## 7. Từ dung lượng log đến dung lượng disk cần cấp

Dung lượng log tính bằng retention là phần dữ liệu cơ sở. Disk thực tế cần thêm không gian cho index, segment, metadata, tăng trưởng và phần disk không nên sử dụng hết.

### 7.1. Các hệ số dự phòng

| Hệ số | Ví dụ | Dùng cho |
|---|---:|---|
| Overhead H | 1,10 | Index, segment, metadata và phần phát sinh quan sát được |
| Growth G | 1,25 | Traffic tăng 25% trong kỳ hoạch định và cleanup có độ trễ |
| Skew K | 1,15 | Partition/leader/replica phân bố không đều |
| Target utilization U | 0,70 | Chỉ sử dụng tối đa 70% disk đã cấp cho dữ liệu dự kiến |

Các giá trị trên chỉ là giả định cho ví dụ. Hãy thay bằng số đo từ cluster thật. Topic có nhiều partition nhỏ và segment nhỏ có thể có tỷ lệ index/segment overhead cao hơn topic có ít partition lớn. Nếu D đã là traffic forecast tại năm/kỳ hoạch định thì đặt G=1 để tránh tính tăng trưởng hai lần.

### 7.2. Công thức dung lượng disk mỗi broker

Với N broker đồng nhất:

~~~text
Base_per_broker = L_physical_cluster / N

Required_disk_per_broker
  = Base_per_broker * H * G * K / U
~~~

Trong ví dụ:

~~~text
Base_per_broker = 11,61216 / 6
                = 1,93536 TB

Required_disk_per_broker
  = 1,93536 * 1,10 * 1,25 * 1,15 / 0,70
  ~= 4,37 TB
~~~

Với các giả định này, mỗi broker cần khoảng 4,37 TB disk vật lý để giữ mức sử dụng mục tiêu không quá 70% trong điều kiện bình thường.

Nếu chọn ổ 5 TB cho mỗi broker, dung lượng sử dụng ở mức 70% là 3,5 TB, cao hơn phần dữ liệu đã nhân overhead, growth và skew là khoảng 3,06 TB. Ổ 5 TB đáp ứng sizing bình thường theo ví dụ.

### 7.3. Dự phòng khi mất một broker

Nếu yêu cầu cluster vẫn đủ chỗ để tạo lại replica sau khi mất một broker, tính dung lượng trên số broker còn lại:

~~~text
Base_after_one_broker_loss
  = L_physical_cluster / (N - 1)

Required_disk_survivor
  = Base_after_one_broker_loss * H * G * K / U
~~~

Với 6 broker:

~~~text
Base_after_one_broker_loss
  = 11,61216 / 5
  = 2,322432 TB

Required_disk_survivor
  = 2,322432 * 1,10 * 1,25 * 1,15 / 0,70
  ~= 5,25 TB
~~~

Nếu cần tái tạo đủ replica sau khi một broker mất, mỗi broker còn lại cần khoảng 5,25 TB disk vật lý theo các giả định đã chọn. Đây là yêu cầu cao hơn sizing bình thường.

Có thể chọn disk 6 TB cho mỗi broker trong ví dụ này để có headroom cho tình huống một broker mất. Tuy nhiên, phải kiểm tra rack placement, giới hạn throughput và việc replica có thể phân bố trên các broker còn lại hay không.

Điều kiện N-1 chỉ khả thi nếu còn đủ broker/rack độc lập để đặt các replica của mỗi partition; số broker còn lại phải ít nhất bằng RF và rack placement phải cho phép phân bố replica hợp lệ.

Không phải hệ thống nào cũng cần tái tạo toàn bộ replica ngay trong thời gian broker down. Hãy ghi rõ mục tiêu phục hồi: chỉ tiếp tục phục vụ khi mất broker, hay phải tái tạo replication factor đầy đủ trước khi hết cửa sổ bảo trì.

### 7.4. Broker có disk khác nhau

Nếu broker có dung lượng disk hoặc replica placement khác nhau, không dùng phép chia trung bình. Hãy tính từng broker:

~~~text
Required_disk_broker_i
  = (replica_bytes_broker_i
     * H_i
     * G_i
     * K_i) / U_i
~~~

Sau đó kiểm tra broker có giá trị cao nhất và các kịch bản mất broker/rack. Một cluster có tổng disk lớn vẫn có thể đầy một broker nếu leader/replica placement lệch.

## 8. Worked example: topic orders

Giả sử một hệ thống thương mại điện tử có topic orders với các thông số:

| Tham số | Giá trị |
|---|---:|
| Record rate trung bình | 8.000 record/s |
| Kích thước record đã serialize | 2.000 byte |
| Hệ số nén | 0,40 |
| Retention | 7 ngày |
| Số partition | 48 |
| Replication factor | 3 |
| Số broker | 6 |
| Overhead factor | 1,10 |
| Growth factor | 1,25 |
| Skew factor | 1,15 |
| Target disk utilization | 70% |

### 8.1. Tốc độ dữ liệu

~~~text
R = 8.000 * 2.000
  = 16 MB/s

D = 16 * 0,40
  = 6,4 MB/s
~~~

### 8.2. Dung lượng một bản log trong 7 ngày

~~~text
T = 604.800 giây

L_logical = 6,4 * 604.800
          = 3.870.720 MB
          = 3,87072 TB
~~~

### 8.3. Dung lượng trung bình mỗi partition

~~~text
L_partition = 3,87072 TB / 48
            = 0,08064 TB
            = 80,64 GB
~~~

Mỗi partition có khoảng 80,64 GB cho một replica theo giả định traffic chia đều.

### 8.4. Dung lượng toàn cluster sau replication

~~~text
L_physical_cluster = 3,87072 * 3
                   = 11,61216 TB
~~~

### 8.5. Dung lượng trung bình mỗi broker

~~~text
Base_per_broker = 11,61216 / 6
                = 1,93536 TB
~~~

### 8.6. Dung lượng disk cần cấp

~~~text
Required_disk_per_broker
  = 1,93536 * 1,10 * 1,25 * 1,15 / 0,70
  ~= 4,37 TB
~~~

Nếu phải chịu được một broker mất và vẫn có thể tái tạo replica:

~~~text
Required_disk_after_one_loss
  = 11,61216 / 5 * 1,10 * 1,25 * 1,15 / 0,70
  ~= 5,25 TB mỗi broker còn lại
~~~

Kết quả này chỉ tính topic orders. Nếu cluster còn topic payment, audit, retry, DLQ, Kafka Connect internal topics và Kafka Streams changelog/repartition topics, phải tính chúng riêng rồi cộng vào tổng cluster.

## 9. Mô hình nhiều topic

Trong production, mỗi topic cần một dòng tính riêng.

| Topic | Rate trước nén | Hệ số nén | Retention | Partitions | RF |
|---|---:|---:|---:|---:|---:|
| orders | 16 MB/s | 0,40 | 7 ngày | 48 | 3 |
| payments | 4 MB/s | 0,50 | 14 ngày | 24 | 3 |
| audit-events | 2 MB/s | 0,60 | 30 ngày | 24 | 2 |
| orders-dlq | 0,1 MB/s | 0,50 | 14 ngày | 12 | 2 |

Với mỗi topic:

1. Tính tốc độ sau nén D_i = R_i * C_i.
2. Tính dung lượng log logic theo retention time và size cap.
3. Nhân với replication factor của topic.
4. Cộng các topic để có dung lượng replica toàn cluster.
5. Cộng internal topics và overhead cần thiết.
6. Phân bổ replica lên broker theo rack/partition assignment thực tế.

Công thức tổng quát cho topic dùng delete retention:

~~~text
L_i = min(D_i * T_i, P_i * B_i)

L_cluster = sum(L_i * RF_i)
~~~

Nếu retention.bytes=-1, bỏ giới hạn size khỏi phép min. Nếu retention.ms=-1, bỏ giới hạn time. Nếu topic dùng compaction, không áp dụng công thức time-retention như topic delete; xem phần log compaction.

### 9.1. Bảng tính spreadsheet

Có thể tạo các cột:

| Cột | Nội dung | Công thức |
|---|---|---|
| A | Topic | Nhập |
| B | Records/s | Nhập |
| C | Serialized bytes/record | Nhập |
| D | Raw MB/s | B*C/1000000 |
| E | Compression factor | Nhập |
| F | Compressed MB/s | D*E |
| G | Retention seconds | Nhập |
| H | Partition count | Nhập |
| I | Retention bytes/partition | Nhập hoặc -1 |
| J | Logical TB | MIN(F*G, H*I/1000000)/1000000 nếu cả hai giới hạn được bật; I là byte/partition |
| K | Replication factor | Nhập |
| L | Cluster physical TB | J*K |

Trong công thức spreadsheet, F*G có đơn vị MB còn I có đơn vị byte/partition; vì vậy H*I phải đổi sang MB trước khi lấy MIN. Khi retention.ms hoặc retention.bytes là không giới hạn, cần xử lý riêng thay vì đưa -1 trực tiếp vào phép MIN.

### 9.2. Internal topics cần tính

Một cluster chạy ứng dụng thực tế thường có thêm:

- __consumer_offsets.
- Kafka Streams changelog topics.
- Kafka Streams repartition topics.
- Kafka Connect config, offset và status topics.
- Retry topics và dead-letter topics.
- Topic phục vụ audit hoặc replay.

Streams changelog và repartition topic có thể có traffic lớn tùy topology. Không tính chúng bằng cách lấy một tỷ lệ tùy ý của topic input; hãy đo hoặc ước lượng theo từng processor/store và retention policy.

## 10. Retention, segment và cleanup thực tế

### 10.1. retention.ms

Giới hạn thời gian giữ log cho policy delete. Ví dụ 7 ngày:

~~~properties
cleanup.policy=delete
retention.ms=604800000
retention.bytes=-1
~~~

Giá trị 604800000 là 7 ngày tính bằng millisecond.

retention.ms không phải cam kết rằng một record sẽ bị xóa chính xác ngay tại thời điểm hết hạn. Kafka xóa theo segment, nên thời gian và dung lượng thực tế có thể vượt ngưỡng lý thuyết một khoảng.

### 10.2. retention.bytes

Giới hạn kích thước log trên mỗi partition:

~~~properties
retention.bytes=107374182400
~~~

Giá trị trên tương đương 100 GiB mỗi partition. Với topic 48 partition, tổng giới hạn lý thuyết là 4.800 GiB cho một bản log logic nếu traffic và phân bố phù hợp.

### 10.3. Segment size và segment time

Kafka quản lý log bằng segment. Các cấu hình thường gặp:

~~~properties
segment.bytes=1073741824
segment.ms=604800000
~~~

segment.bytes giới hạn kích thước segment; segment.ms buộc log roll theo thời gian. Retention và cleanup thực hiện theo file/segment, vì vậy:

- Segment lớn giảm số file nhưng làm retention kém chính xác hơn.
- Segment nhỏ làm cleanup linh hoạt hơn nhưng tăng số file và index.
- Partition nhiều với segment nhỏ làm tăng overhead file/index.
- Active segment chưa được xóa như một segment đã đóng.

Không giảm segment.bytes chỉ để cố làm dung lượng giảm. Hãy cân nhắc số file, index, filesystem và khả năng vận hành.

### 10.4. cleanup.policy=compact

Log compaction giữ lại giá trị mới nhất theo key thay vì xóa dữ liệu đơn thuần theo tuổi. Vì thế, dung lượng topic compacted phụ thuộc vào:

- Số lượng key còn tồn tại.
- Kích thước value mới nhất của mỗi key.
- Tốc độ cập nhật key.
- Tỷ lệ segment đã đủ điều kiện compact.
- Cleaner throughput và compaction lag.
- Tombstone và delete.retention.ms.

Một topic compacted có thể có traffic ghi lớn nhưng dung lượng ổn định nếu số key duy nhất ít. Ngược lại, nếu số key liên tục tăng, dung lượng state cũng tăng.

Không dùng ingress bytes/s nhân retention days làm dự báo duy nhất cho topic compacted. Hãy ước lượng working set theo số key và kích thước giá trị hiện tại, cộng phần log chưa compact và tombstone.

### 10.5. compact,delete

Topic có thể dùng cả hai policy:

~~~properties
cleanup.policy=compact,delete
~~~

Compaction giữ trạng thái mới nhất theo key; delete loại bỏ segment theo retention time/size. Cần hiểu cả hai hành vi khi xác định thời gian replay và dung lượng cần giữ.

### 10.6. Tiered storage

Nếu bật remote/tiered storage, cần tách:

- Dung lượng local log trên broker.
- Dung lượng remote object storage.
- Local retention (local.retention.ms, local.retention.bytes).
- Topic retention tổng thể (retention.ms, retention.bytes).
- Chi phí remote read, write, request và network.

Local disk có thể nhỏ hơn tổng retention nếu dữ liệu cũ được chuyển lên remote storage. Nhưng remote storage vẫn cần dung lượng, lifecycle policy, chi phí truy cập và kiểm tra phục hồi. Không lấy local disk capacity làm tổng dung lượng dữ liệu mà hệ thống đang lưu.

Với Kafka 4.4, tiered storage cần một RemoteStorageManager implementation được cấu hình; Kafka không cung cấp sẵn implementation production cho object store. Tài liệu 4.4 cũng nêu tiered storage chưa hỗ trợ compacted topics, vì vậy hãy kiểm tra giới hạn phiên bản trước khi chọn policy cho topic.

## 11. Ảnh hưởng của replication đến network và disk throughput

Replication không chỉ tăng dung lượng disk. Mỗi record mới được ghi ở leader cần được truyền đến follower replica.

Với tốc độ dữ liệu sau nén D và replication factor RF, ước lượng tổng replication traffic theo cluster:

~~~text
Replication traffic ~= D * (RF - 1)
~~~

Đây là ước lượng lưu lượng copy cho một luồng dữ liệu cân bằng, không phải công thức thay thế cho đo ReplicationBytesInPerSec/ReplicationBytesOutPerSec trên từng broker.

Ví dụ:

~~~text
D = 6,4 MB/s
RF = 3

Replication traffic ~= 6,4 * (3 - 1)
                    = 12,8 MB/s
~~~

Ngoài traffic replication còn có:

- Producer client gửi dữ liệu vào leader.
- Consumer group fetch dữ liệu.
- Nhiều consumer group có thể đọc cùng topic.
- Replica reassignment và recovery traffic.
- Inter-broker control/metadata traffic.
- TLS overhead và request/response overhead.

### 11.1. Ước lượng network egress

Nếu có G consumer group đều đọc toàn bộ topic và mỗi group đọc gần bằng tốc độ ghi:

~~~text
Client fetch traffic ~= D * G
Replication egress ~= D * (RF - 1)

Approximate broker egress
  ~= Client fetch traffic + Replication egress
~~~

Đây chỉ là ước lượng tổng cluster. Từng broker có thể chịu tải khác nhau do leader placement, consumer fetch locality và replica assignment.

Không nhân D với RF rồi gọi toàn bộ là network egress. RF-1 là số follower copies bổ sung cho mỗi record; client fetch traffic là một thành phần riêng.

### 11.2. Disk write throughput

Tổng byte được ghi trên tất cả replica xấp xỉ:

~~~text
Cluster disk write throughput ~= D * RF
~~~

Phân bố thực tế phụ thuộc leader/follower placement, replication, log append, index update, flush và filesystem. Khi benchmark cần theo dõi disk write latency, IOPS và throughput trên từng broker.

### 11.3. Tái tạo replica và reassignment

Khi broker mất hoặc partition được reassignment, lượng network/disk I/O có thể tăng mạnh trong thời gian phục hồi. Capacity planning nên có headroom cho:

- Replica catch-up.
- Partition reassignment.
- Broker rolling restart.
- Consumer replay.
- Backfill và batch ingestion.

Không chạy reassignment lớn cùng lúc với peak traffic nếu cluster không đủ disk/network headroom.

## 12. Ảnh hưởng của số partition

Partition count ảnh hưởng cả throughput và storage.

Tăng partition có thể giúp:

- Tăng parallelism của producer/consumer.
- Phân tán leader và replica trên nhiều broker.
- Tăng khả năng xử lý đồng thời.

Nhưng tăng partition cũng làm tăng:

- Số log directory và segment.
- Index và file handle.
- Metadata và chi phí controller.
- Công việc leader election và reassignment.
- Thời gian khởi động, phục hồi và rebalance.
- Số task/state store trong Kafka Streams.

Nếu topic có tổng dung lượng log logic L và P partition, dung lượng trung bình mỗi partition là:

~~~text
L_partition = L / P
~~~

Đây là trung bình. Một key nóng có thể làm partition lớn hơn nhiều.

Chọn partition count dựa trên throughput mục tiêu, số consumer cần chạy song song, key distribution và giới hạn vận hành. Không tăng partition chỉ vì muốn tăng retention hoặc giảm disk utilization.

## 13. Kiểm chứng bằng metric Kafka

Capacity model cần được so sánh với dữ liệu thực tế.

### 13.1. Broker metrics

Theo dõi:

| Metric/MBean | Dùng để |
|---|---|
| BytesInPerSec | Byte broker nhận từ client |
| BytesOutPerSec | Byte broker gửi đến client |
| ReplicationBytesInPerSec | Byte broker nhận từ replica khác |
| ReplicationBytesOutPerSec | Byte broker gửi đến replica khác |
| kafka.log:type=Log,name=Size | Kích thước log partition trên disk |
| RetentionSizeInPercent | Mức sử dụng so với retention.bytes |
| NumLogSegments | Số segment của partition |
| LogStartOffset | Offset đầu tiên còn trong log |
| UnderReplicatedPartitions | Partition chưa đủ ISR |
| OfflinePartitionsCount | Partition offline |

Metric RetentionSizeInPercent có thể vượt 100% nếu cleanup bị trễ. Với topic dùng tiered storage, metric local này có thể không phản ánh tổng dung lượng remote.

### 13.2. Producer metrics

Theo dõi:

- record-send-rate.
- record-size-avg.
- compression-rate-avg.
- request-latency-avg/max.
- record-error-rate.
- record-retry-rate.
- buffer-available-bytes.

Các metric này giúp xác định producer có gửi đúng throughput dự báo, batch có đủ lớn để nén và broker có đáp ứng được không.

### 13.3. Đo kích thước log thực tế

Có thể dùng công cụ Kafka để kiểm tra partition replica và log directory.

Liệt kê topic và replica:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders
~~~

Xem cấu hình topic:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
~~~

Kiểm tra log directory của broker:

~~~bash
bin/kafka-log-dirs.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --broker-list 1,2,3
~~~

Các lệnh cần chạy với bootstrap address, quyền ACL và phiên bản Kafka phù hợp. Khi cluster bật TLS/SASL, truyền client properties tương ứng.

### 13.4. So sánh dự báo và thực tế

Sau một khoảng chạy ổn định, ghi lại:

- Ingress bytes/s theo topic.
- Compression ratio.
- Disk growth mỗi giờ/ngày.
- Kích thước log mỗi partition.
- Tổng replica bytes trên từng broker.
- Mức sử dụng disk.
- Retention cleanup delay.
- Replication bytes và reassignment traffic.

Tính sai số:

~~~text
Sizing error (%) =
  (Measured storage - Predicted storage)
  / Predicted storage * 100
~~~

Nếu sai số lớn, kiểm tra lại serialized record size, codec, batch, retention, partition skew, internal topics và replica placement. Không chỉ tăng disk dựa trên một hệ số chung khi chưa hiểu nguyên nhân sai lệch.

## 14. Cảnh báo capacity

Các cảnh báo nên phản ánh xu hướng đầy disk và khả năng hết dung lượng trước khi retention cleanup hoặc broker recovery gặp vấn đề.

| Alert | Điều kiện tham khảo | Ý nghĩa |
|---|---|---|
| BrokerDiskUsageHigh | Disk usage vượt ngưỡng vận hành | Broker sắp thiếu headroom |
| BrokerDiskGrowthFast | Disk tăng nhanh bất thường | Traffic tăng hoặc retention cleanup không theo kịp |
| TopicRetentionNearLimit | Partition tiến gần retention.bytes | Topic có thể xóa dữ liệu sớm hơn mong muốn |
| PartitionSizeSkew | Partition lớn nhất lệch nhiều so với median | Key/traffic distribution không đều |
| RetentionCleanupDelayed | RetentionSizeInPercent vượt 100% kéo dài | Cleanup không kịp hoặc segment chưa đủ điều kiện |
| ReplicationRecoveryRisk | Disk headroom không đủ cho replica recovery | Broker failure có thể làm cluster không phục hồi đủ RF |
| RemoteStorageGrowth | Remote object bytes tăng nhanh | Chi phí hoặc quota remote storage có thể vượt dự báo |

Ngưỡng 70%, 80% hoặc 90% cần được chọn theo tốc độ tăng disk, thời gian xử lý sự cố, thời gian cấp thêm disk và recovery plan. Một broker tăng 1% disk mỗi ngày có thể có phản ứng khác broker tăng 10% mỗi giờ.

### 14.1. Ước lượng thời gian đến khi đầy

Nếu disk còn FreeBytes và tăng trưởng trung bình GrowthBytesPerSecond:

~~~text
Time_to_full = FreeBytes / GrowthBytesPerSecond
~~~

Ví dụ:

~~~text
FreeBytes = 600 GB
GrowthBytesPerDay = 120 GB

Time_to_full = 600 / 120
             = 5 ngày
~~~

Dùng tốc độ tăng trong cửa sổ gần đây và kiểm tra xu hướng dài hơn. Nếu retention cleanup sắp giải phóng segment, dự báo tuyến tính có thể bi quan; nếu traffic đang tăng, dự báo có thể lạc quan. Alert nên có cả time-to-full và mức sử dụng hiện tại.

## 15. Quy trình hoạch định dung lượng

Một quy trình có thể lặp lại cho mỗi topic:

1. **Phân loại topic:** delete, compact hay compact+delete; xác định dữ liệu có cần replay không.
2. **Đo ingress:** record/s và serialized bytes/record trong ngày thường, peak và mùa vụ.
3. **Đo compression:** benchmark codec, batch và cấu hình producer/broker.
4. **Chọn retention:** xác định thời gian replay, SLA consumer và retention.bytes nếu cần.
5. **Tính log logic:** tính dung lượng cho một bản copy theo retention time/size.
6. **Tính replication:** nhân theo RF và kiểm tra rack placement.
7. **Cộng overhead:** index, segment, metadata, internal topic và phần phát sinh.
8. **Dự phòng tăng trưởng:** dùng forecast traffic, retention cleanup delay và skew.
9. **Chọn disk:** tính theo từng broker và kịch bản mất broker/rack.
10. **Kiểm tra throughput:** network, disk I/O, CPU nén/giải nén và consumer fetch.
11. **Benchmark:** chạy tải với cấu hình tương tự production.
12. **Theo dõi sai số:** so sánh disk growth thực tế với forecast và điều chỉnh hệ số.

## 16. Lab: tính dung lượng topic orders

### Mục tiêu

Tạo một bảng tính sizing cho topic orders, thay đổi retention, compression và replication factor để quan sát ảnh hưởng lên dung lượng cluster.

### Bước 1: Thu thập dữ liệu mẫu

Dùng workload giả lập hoặc dữ liệu đã được ẩn danh. Đo record rate và kích thước serialized record. Ghi lại traffic trung bình, p95 và peak.

### Bước 2: Đo compression

Chạy thử với none, lz4 và zstd. Giữ cùng dữ liệu, serializer, key, headers và batch settings. So sánh compression ratio, CPU và latency.

### Bước 3: Tạo bảng tính

Nhập:

- Record rate.
- Serialized bytes/record.
- Compression factor.
- Retention days.
- Partition count.
- Replication factor.
- Broker count.
- Overhead/growth/skew factors.
- Target disk utilization.

Tính R, D, L_logical, L_physical_cluster và disk cần cấp cho mỗi broker.

### Bước 4: Thử thay đổi retention

So sánh 1 ngày, 7 ngày và 30 ngày. Xác định dung lượng tăng tuyến tính ra sao khi traffic và compression không đổi.

### Bước 5: Thử thay đổi replication

So sánh RF=1, RF=2 và RF=3. Ghi lại tổng cluster disk và replication traffic ước lượng.

### Bước 6: Thử thay đổi compression

Thử C=1,0, C=0,6, C=0,4 và C=0,25. Đây là các giá trị giả định để quan sát công thức; khi sizing thật phải thay bằng số đo.

### Bước 7: Thử retention.bytes

Đặt giới hạn theo partition và so sánh P * retention.bytes với D * T. Xác định giới hạn nào đạt trước.

### Bước 8: Thử mất broker

Tính lại dung lượng trung bình khi số broker còn lại giảm từ 6 xuống 5. Xác định disk headroom có đủ để tạo lại replica hay không.

### Bước 9: Đối chiếu với Kafka

Tạo topic trong cluster lab, gửi record với cấu hình nén đã chọn. Theo dõi log directory size và broker metrics trong thời gian chạy.

### Bước 10: Viết kết luận

Ghi lại:

- Dự báo logical bytes.
- Tổng physical bytes theo RF.
- Disk cần cấp mỗi broker.
- Sai số giữa dự báo và đo thực tế.
- Codec phù hợp với throughput/CPU.
- Retention và partition skew.
- Kịch bản broker failure đã kiểm tra.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ lấy payload size | Thiếu key, headers, serializer và record overhead | Đo serialized record thực tế |
| Dùng compression ratio mặc định | Dự báo disk sai | Benchmark đúng dữ liệu và batch |
| Quên nhân replication factor | Thiếu disk cho follower replica | Tính tổng replica bytes |
| Nhầm retention.bytes là giới hạn toàn topic | Ước lượng thấp khi có nhiều partition | Nhân với partition count |
| Dùng retention time cho topic compacted | Dự báo quá cao hoặc quá thấp | Ước lượng working set theo key và compaction |
| Chia đều dung lượng cho broker | Bỏ qua partition/leader skew | Kiểm tra log size từng broker và dùng skew factor |
| Không dự phòng broker failure | Không đủ chỗ phục hồi replica | Tính kịch bản N-1 hoặc rack loss |
| Chỉ tính storage | Broker vẫn có thể nghẽn network hoặc disk I/O | Tính throughput và replication traffic |
| Bỏ qua segment/index | Disk thực tế lớn hơn log data | Đo overhead và retention cleanup |
| Không tính internal topics | Thiếu capacity cho Streams/Connect | Inventory tất cả topic |
| Dùng peak ngắn cho toàn retention | Dự báo storage quá cao | Dùng average retention-window và peak cho throughput |
| Dùng average duy nhất | Bỏ qua mùa vụ và burst | Dùng forecast, p95/p99 và growth factor |
| Không kiểm tra tiered storage | Nhầm local disk với tổng data footprint | Tính local và remote riêng |
| Không đo lại sau triển khai | Model nhanh chóng lỗi thời | So sánh forecast với disk growth định kỳ |

## 18. Checklist production

- [ ] Inventory đầy đủ topic và internal topics.
- [ ] Ghi nhận record/s và serialized bytes/record.
- [ ] Đo traffic trung bình, peak và mùa vụ.
- [ ] Benchmark compression trên dữ liệu thực tế.
- [ ] Xác định compression.type ở producer và topic.
- [ ] Chọn retention.ms theo nhu cầu replay.
- [ ] Chọn retention.bytes theo partition nếu cần giới hạn size.
- [ ] Xác định cleanup.policy cho từng topic.
- [ ] Tính dung lượng logical theo topic.
- [ ] Nhân replication factor để có physical bytes.
- [ ] Xác nhận rack awareness và replica placement.
- [ ] Cộng index, segment và internal topic overhead.
- [ ] Dự phòng growth, skew và retention cleanup delay.
- [ ] Tính dung lượng mỗi broker và kịch bản N-1.
- [ ] Giữ disk utilization dưới target vận hành.
- [ ] Kiểm tra network replication và client fetch throughput.
- [ ] Kiểm tra disk IOPS, latency và write throughput.
- [ ] Theo dõi log size và retention size percent.
- [ ] Theo dõi disk growth và time-to-full.
- [ ] Tính riêng local/remote capacity nếu dùng tiered storage.
- [ ] Benchmark trước khi đưa workload production vào cluster.
- [ ] So sánh sizing forecast với số đo định kỳ.

## 19. Tài liệu tham khảo

- [Apache Kafka 4.4 – Topic Configs](https://kafka.apache.org/44/configuration/topic-configs/)
- [Apache Kafka 4.4 – Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka 4.4 – Monitoring](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka 4.4 – Log Compaction](https://kafka.apache.org/44/design/design/#compaction)
- [Apache Kafka 4.4 – Tiered Storage](https://kafka.apache.org/44/operations/tiered-storage/)

Capacity planning cho Kafka là bài toán kết hợp dữ liệu, thời gian giữ, compression, replication và cách phân bố replica. Tính riêng từng topic giúp tránh dùng một hệ số chung cho workload khác nhau; kiểm chứng bằng log size, broker metrics và benchmark giúp mô hình phản ánh đúng cluster đang vận hành.
