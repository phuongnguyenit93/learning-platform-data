# Ước lượng lưu lượng vào từ tốc độ và kích thước sự kiện

## Mục tiêu

Để hoạch định năng lực Kafka, trước hết cần trả lời hai câu hỏi: hệ thống tạo bao nhiêu sự kiện trong một giây và mỗi sự kiện chiếm bao nhiêu byte sau khi serialize? Tích của hai đại lượng này cho ta lưu lượng dữ liệu đầu vào ở mức ứng dụng. Từ đó có thể ước lượng tải theo giờ, ngày, thời điểm cao điểm và lượng dữ liệu cần lưu.

Phép tính chỉ có ý nghĩa khi định nghĩa kích thước event rõ ràng. Kích thước object trong bộ nhớ, số ký tự JSON, số byte sau serialization và số byte Kafka truyền trên network là những đại lượng khác nhau. Bài học này đi từ event nghiệp vụ tới serialized bytes, record batch, compression và lưu lượng broker quan sát được.

Sau bài học, bạn có thể:

- Xác định event rate từ volume nghiệp vụ và cửa sổ thời gian.
- Đo kích thước key, value và headers sau serialization.
- Tính ingress theo từng loại event và tổng workload.
- Chuyển đổi byte/s sang MB/s, MiB/s, GB/ngày và TiB/ngày.
- Ước lượng tải trung bình, peak và burst theo các cửa sổ thời gian.
- Phân biệt payload bytes, Kafka record bytes, compressed batch bytes và replication traffic.
- Dùng producer/broker metrics để kiểm chứng phép tính.
- Lập bảng giả định và khoảng dự phòng để phục vụ capacity planning.

## 1. Công thức lưu lượng đầu vào

Nếu một workload tạo:

- R: số event mỗi giây, đơn vị events/s.
- S: kích thước trung bình của một event, đơn vị bytes/event.

Thì lưu lượng payload đầu vào xấp xỉ:

\[
Ingress_{payload} = R \times S
\]

Đơn vị:

\[
\frac{events}{s} \times \frac{bytes}{event}
= \frac{bytes}{s}
\]

Ví dụ, hệ thống tạo 10.000 event/s, mỗi event có kích thước trung bình 1.024 byte:

\[
10.000 \times 1.024 = 10.240.000\ bytes/s
\]

Tương đương:

- 10,24 MB/s theo đơn vị thập phân.
- Khoảng 9,77 MiB/s theo đơn vị nhị phân.

Đây là payload rate trước khi tính overhead của record/batch/protocol và trước compression. Nó chưa phải network bandwidth chính xác mà broker sẽ quan sát.

### 1.1. Phân biệt event rate và byte rate

Hai hệ thống có cùng event rate vẫn có thể tạo tải rất khác:

| Workload | Event rate | Event size trung bình | Payload ingress |
|---|---:|---:|---:|
| Telemetry nhỏ | 50.000 events/s | 200 B | 10 MB/s |
| Order events | 10.000 events/s | 2 KiB | 20,48 MB/s |
| Document events | 1.000 events/s | 100 KiB | 102,4 MB/s |

Workload có ít event hơn vẫn có thể tạo byte rate cao hơn nhiều nếu payload lớn. Vì vậy, không sizing Kafka chỉ bằng records/s.

### 1.2. Đơn vị phải thống nhất

| Đơn vị | Số byte |
|---|---:|
| 1 KB | 1.000 B |
| 1 MB | 1.000.000 B |
| 1 GB | 1.000.000.000 B |
| 1 KiB | 1.024 B |
| 1 MiB | 1.048.576 B |
| 1 GiB | 1.073.741.824 B |
| 1 TiB | 1.099.511.627.776 B |

Khi viết tài liệu capacity, ghi rõ dùng MB/GB thập phân hay MiB/GiB nhị phân. Không trộn 1.000 với 1.024 trong cùng phép tính.

## 2. Xác định event rate từ dữ liệu nghiệp vụ

Không phải hệ thống nào cũng có metric events/s sẵn. Có thể suy ra rate từ volume nghiệp vụ.

Nếu:

- N: số thực thể nghiệp vụ trong một khoảng thời gian.
- E: số event trung bình phát sinh cho mỗi thực thể.
- T: độ dài khoảng thời gian tính bằng giây.

Thì event rate trung bình:

\[
R_{avg} = \frac{N \times E}{T}
\]

Ví dụ hệ thống xử lý 500.000 đơn hàng/ngày, mỗi đơn tạo trung bình 4 event:

\[
R_{avg} =
\frac{500.000 \times 4}{86.400}
\approx 23,15\ events/s
\]

Đây chỉ là trung bình 24 giờ. Nếu phần lớn đơn hàng được tạo trong 10 giờ hoạt động, rate trung bình trong giờ hoạt động sẽ cao hơn:

\[
\frac{2.000.000}{10 \times 3.600}
\approx 55,56\ events/s
\]

Trong thực tế, traffic còn tăng vào giờ mở bán, chiến dịch marketing, cuối ngày hoặc khi batch job chạy. Dùng daily average để thiết kế peak capacity sẽ đánh giá thiếu tải.

### 2.1. Tách event theo loại

Một thực thể có thể phát sinh nhiều loại event với kích thước khác nhau. Hãy lập inventory theo event type:

| Event type | Rate | Kích thước trung bình |
|---|---:|---:|
| OrderCreated | 1.000 events/s | 2.048 B |
| PaymentAuthorized | 500 events/s | 819 B |
| InventoryAdjusted | 5.000 events/s | 512 B |

Tính riêng từng loại:

\[
R_{Order} = 1.000 \times 2.048 = 2.048.000\ B/s
\]

\[
R_{Payment} = 500 \times 819 = 409.500\ B/s
\]

\[
R_{Inventory} = 5.000 \times 512 = 2.560.000\ B/s
\]

Tổng payload ingress:

\[
R_{total} = 2.048.000 + 409.500 + 2.560.000
= 5.017.500\ B/s
\]

Tương đương khoảng 5,02 MB/s hoặc 4,79 MiB/s.

Không lấy trung bình cộng đơn giản của ba event size rồi nhân với tổng rate. Event size trung bình phải được weighted theo rate:

\[
S_{weighted} =
\frac{\sum_i R_i S_i}{\sum_i R_i}
\]

Trong ví dụ trên, tổng event rate là 6.500 events/s và weighted event size xấp xỉ 772 B/event.

### 2.2. Tính rate từ cửa sổ đo

Đối với hệ thống đang chạy, đo số event thực tế trong các cửa sổ:

- 1 giây để nhìn spike ngắn.
- 10 giây hoặc 1 phút để nhìn burst.
- 5 phút hoặc 15 phút để nhìn tải peak có tính ổn định.
- 1 giờ và 24 giờ để hiểu chu kỳ ngày.

Rate trong cửa sổ:

\[
R_{window} = \frac{EventCount_{window}}{WindowDurationSeconds}
\]

Nếu cửa sổ 60 giây có 720.000 event:

\[
720.000 / 60 = 12.000\ events/s
\]

Khi lập kế hoạch, lưu lại cả average, p95/p99 của rate theo cửa sổ và maximum quan sát được. Một spike 1 giây và một peak kéo dài 15 phút cần chiến lược capacity khác nhau.

## 3. Xác định kích thước thực của event

### 3.1. Object size không phải serialized size

Một Java object có thể chiếm nhiều RAM hơn hoặc ít hơn nhiều so với dữ liệu được gửi đi. Object chứa header JVM, reference, padding, collection và cấu trúc nội bộ; các phần đó không nhất thiết xuất hiện trong Kafka record.

Ngược lại, serializer có thể thêm metadata:

- JSON field names, dấu ngoặc, dấu phẩy và chuỗi escape.
- Avro schema ID hoặc envelope theo serializer.
- Protobuf field tags và wire type.
- Schema Registry framing hoặc custom envelope.
- Encoding UTF-8 cho chuỗi.

Ví dụ một object có 8 field không có nghĩa event chỉ chiếm 8 lần kích thước value. Một chuỗi tiếng Việt cũng có thể chiếm nhiều byte UTF-8 hơn số ký tự hiển thị.

Vì vậy, đo sau serializer thực tế. Không dùng số ký tự của JSON hoặc kích thước object trong heap làm byte size.

### 3.2. Các thành phần kích thước ứng dụng

Ở mức ứng dụng, có thể tách:

\[
S_{app} = S_{key} + S_{value} + S_{headers}
\]

Trong đó:

- S_key: số byte key sau key serializer; có thể bằng 0 nếu key null.
- S_value: số byte value sau value serializer; có thể bằng 0 nếu value null.
- S_headers: tổng byte của header names và header values sau encoding.

Ví dụ:

| Thành phần | Kích thước |
|---|---:|
| Key UTF-8 | 24 B |
| Value JSON UTF-8 | 1.200 B |
| Header event-type | 18 B |
| Header trace-id | 32 B |
| Header source | 8 B |
| Tổng ứng dụng xấp xỉ | 1.282 B |

Đây là tổng byte dữ liệu key/value/header, chưa gồm record field encoding, record batch header, request protocol và TCP/TLS/IP/Ethernet overhead.

### 3.3. Kafka record và record batch

Kafka lưu và truyền record theo record batch. Một batch có header riêng; từng record bên trong có các trường như:

- Record length và attributes.
- Timestamp delta và offset delta.
- Key length và key bytes.
- Value length và value bytes.
- Header count và các header key/value.

Mỗi header cũng có length field và tên header. Các trường độ dài dùng varint nên overhead thay đổi theo giá trị thực tế. Batch có base offset, batch length, leader epoch, magic, CRC, attributes và metadata khác.

Do đó:

\[
S_{record} \neq S_{key} + S_{value} + S_{headers}
\]

Và:

\[
S_{batch} \approx S_{batchHeader}
+ \sum_{j=1}^{n} S_{record,j}
\]

Batch có một header chung được chia sẻ cho nhiều record. Batch càng đầy thì batch overhead trên mỗi record thường càng nhỏ. Record size lớn, headers nhiều hoặc batch chỉ chứa một record có thể làm overhead tỷ lệ cao hơn.

Không cộng một số byte overhead cố định cho mọi record để dự báo chính xác. Hãy dùng công thức payload để ước lượng sơ bộ và metrics/benchmark để hiệu chỉnh phần record/batch/protocol overhead.

## 4. Tính ingress từ nhiều loại event

Với nhiều event type, công thức tổng quát:

\[
Ingress_{payload} = \sum_{i=1}^{n} R_i \times S_i
\]

Trong đó R_i là rate và S_i là serialized application size trung bình của loại event thứ i.

Ví dụ:

| Topic/event type | Rate trung bình | Serialized size | Payload ingress |
|---|---:|---:|---:|
| orders.created | 8.000/s | 1,5 KiB | 12,29 MB/s |
| payments.authorized | 2.000/s | 2 KiB | 4,10 MB/s |
| inventory.changed | 10.000/s | 700 B | 7,00 MB/s |
| **Tổng** | **20.000/s** | — | **23,39 MB/s** |

Tổng event rate là tổng các rate, còn tổng byte rate là tổng từng tích rate × size. Có thể tính weighted size để báo cáo:

\[
S_{weighted} =
\frac{Ingress_{payload}}{R_{total}}
\]

Nhưng khi sizing topic, vẫn nên giữ số liệu riêng theo topic vì retention, compression, partition, key distribution và consumer groups có thể khác nhau.

### 4.1. Nhiều producer

Nếu nhiều ứng dụng cùng ghi vào cluster:

\[
Ingress_{cluster} = \sum_{p=1}^{m} Ingress_{producer,p}
\]

Lập bảng theo service:

| Producer | Event rate | Size trung bình | Payload ingress |
|---|---:|---:|---:|
| order-service | 8.000/s | 1,5 KiB | 12,29 MB/s |
| payment-service | 2.000/s | 2 KiB | 4,10 MB/s |
| inventory-service | 10.000/s | 700 B | 7,00 MB/s |
| **Tổng** | **20.000/s** | — | **23,39 MB/s** |

Tránh đếm trùng khi cùng một event được forward qua nhiều service hoặc được ghi lại vào nhiều topic. Xác định rõ đang tính ingress gốc từ ứng dụng hay tổng số lần Kafka nhận record trên tất cả topic.

### 4.2. Fan-out và duplicate publish

Một business event có thể được publish vào nhiều topic hoặc nhiều cluster. Nếu producer gửi một event tới ba topic, broker nhận ba lần record bytes. Nếu một pipeline đọc rồi publish lại event, đó là ingress mới tại topic đích.

Hãy phân biệt:

- Unique business events/s.
- Kafka records produced/s.
- Total bytes produced/s trên tất cả topic.

Capacity của broker phụ thuộc Kafka records/bytes thực tế, không chỉ số business event duy nhất.

## 5. Từ average tới peak và burst

### 5.1. Peak multiplier

Nếu chưa có profile đo đủ dài, có thể mô hình hóa peak bằng hệ số:

\[
R_{peak} = R_{avg} \times PeakFactor
\]

Ví dụ:

- Average: 12.000 events/s.
- Peak factor giả định: 2,5.
- Peak: 30.000 events/s.

Với event size trung bình 1,5 KiB:

\[
Ingress_{peak} = 30.000 \times 1.536
= 46.080.000\ B/s
\]

Tương đương khoảng 46,08 MB/s hoặc 43,95 MiB/s payload trước compression.

Peak factor chỉ là giả định khi thiếu dữ liệu. Khi có metrics, dùng peak rate theo cửa sổ 1 giây, 10 giây, 1 phút và 15 phút để mô tả tải chính xác hơn.

### 5.2. Burst volume

Nếu burst rate ổn định trong D giây:

\[
BurstBytes = R_{burst} \times S_{avg} \times D
\]

Ví dụ 30.000 events/s, size 1,5 KiB và burst kéo dài 120 giây:

\[
30.000 \times 1.536 \times 120
= 5.529.600.000\ bytes
\]

Tương đương khoảng 5,53 GB payload trong hai phút.

Đây là lượng dữ liệu producer gửi trong burst. Consumer có thể xử lý đồng thời; nếu consumer không theo kịp, phần chênh lệch sẽ trở thành backlog.

### 5.3. Phân biệt peak rate và burst volume

Peak rate trả lời “mỗi giây có bao nhiêu byte đi vào?”. Burst volume trả lời “trong toàn bộ đợt tăng tải có bao nhiêu byte?”. Cả hai đều cần thiết:

- Network và broker request capacity quan tâm byte/s.
- Storage/retention quan tâm byte tích lũy.
- Consumer capacity quan tâm tốc độ xử lý và backlog.
- Recovery planning quan tâm burst duration và tốc độ drain backlog.

### 5.4. Không ghép percentile một cách tùy tiện

Không mặc định lấy p99 event rate nhân p99 event size để kết luận đó là p99 byte rate. Hai phân phối có thể tương quan hoặc độc lập, và byte rate trong cửa sổ là tổng kích thước của nhiều event.

Ưu tiên đo trực tiếp byte rate theo từng cửa sổ. Nếu phải dự báo từ dữ liệu riêng lẻ, hãy xây workload envelope bằng các kịch bản có căn cứ: peak rate quan sát được, size distribution theo event type và mức tương quan giữa rate với size.

## 6. Compression và lưu lượng thực truyền

Producer thường gom record vào batch và nén batch trước khi gửi. Tỷ lệ nén phụ thuộc:

- Codec như gzip, snappy, lz4 hoặc zstd.
- Kích thước batch và số record trong batch.
- Nội dung payload: JSON lặp field thường nén tốt hơn dữ liệu đã nén/mã hóa.
- Phân phối key, headers và kích thước record.
- Tốc độ event trên từng partition và linger.

Định nghĩa tỷ lệ compression thực nghiệm:

\[
C = \frac{CompressedBatchBytes}{UncompressedBatchBytes}
\]

Nếu C = 0,45, batch sau nén còn khoảng 45% kích thước trước nén. Lưu lượng batch ước lượng:

\[
Ingress_{compressed} \approx Ingress_{uncompressed} \times C
\]

Ví dụ payload rate là 17,58 MiB/s và compression ratio quan sát được là 0,45:

\[
17,58 \times 0,45 \approx 7,91\ MiB/s
\]

Đây là ước lượng compressed record-batch bytes trước khi cộng request/protocol/network overhead. Không coi 7,91 MiB/s là băng thông NIC chính xác.

Trong Kafka producer metrics, compression-rate-avg được định nghĩa là tỷ lệ compressed batch size trên uncompressed size. Giá trị càng thấp thường có nghĩa batch nén càng nhỏ. Hãy lấy ratio từ workload thật thay vì giả định mọi topic có cùng tỷ lệ.

### 6.1. Compression phụ thuộc batching

Nếu mỗi partition chỉ nhận vài record trong một khoảng thời gian, batch có thể nhỏ và compression kém hiệu quả. Cùng một payload, producer có traffic dày thường tạo batch tốt hơn producer có traffic thưa.

Vì vậy, không lấy compression ratio từ một bài test duy nhất rồi áp cho toàn bộ cluster. Đo theo topic và workload, đặc biệt khi:

- Một topic có event size nhỏ và traffic thưa.
- Một topic có payload lớn nhưng ít record.
- Một topic có JSON lặp lại nhiều field.
- Một topic có payload đã nén như ảnh, video hoặc archive.

### 6.2. Compression không giảm mọi loại traffic

Compression giảm kích thước record batch được gửi, nhưng không loại bỏ:

- TLS record overhead.
- TCP/IP/Ethernet headers.
- Kafka request/response framing.
- Metadata và control traffic.
- Consumer fetch response overhead.
- Replication và reassignment traffic.

Broker cũng có thể phải giải nén, chuyển đổi message format hoặc nén lại tùy cấu hình và phiên bản. Đo cả CPU và byte rate để đánh giá tổng chi phí.

## 7. Từ ingress payload tới broker và cluster traffic

Không nên dùng một con số “Kafka traffic” cho mọi mục đích. Phân biệt các luồng:

| Đại lượng | Ý nghĩa |
|---|---|
| Application payload ingress | Tổng serialized key/value/headers được ứng dụng tạo ra |
| Producer batch bytes | Record batch sau khi Kafka đóng batch và áp dụng compression |
| Broker client ingress | Byte rate broker nhận từ producer client |
| Replication traffic | Byte broker trao đổi với broker khác để sao chép partition |
| Consumer egress | Byte broker gửi cho các consumer groups |
| Network interface traffic | Byte thực đi qua NIC, gồm các lớp protocol và các loại traffic khác |

### 7.1. Replication không phải producer ingress

Với replication factor 3, leader và hai follower cùng lưu bản sao dữ liệu. Producer chỉ gửi record tới leader; follower fetch dữ liệu từ leader. Do đó:

- Producer client ingress không tự động nhân ba.
- Storage logic của topic phải tính cả ba replica.
- Inter-broker network có thêm traffic sao chép.
- Broker egress tới consumer groups là một luồng riêng.

Đừng nhân producer ingress với replication factor rồi gọi kết quả là BytesInPerSec từ client. Hãy ước lượng riêng storage và inter-broker network theo replica placement.

### 7.2. Consumer groups tạo thêm egress

Nếu ba consumer groups độc lập cùng đọc một topic, mỗi group có thể đọc toàn bộ stream. Egress dữ liệu tới consumer vì thế có thể xấp xỉ ba lần lượng dữ liệu đọc bởi một group, chưa tính fetch batching, retry, replay và phân bố leader.

Nếu một consumer group có nhiều member, chúng chia partition của group; không phải mỗi member đọc toàn bộ topic. Phải phân biệt số group với số consumer instance.

### 7.3. Ước lượng storage từ ingress

Với ingress lưu trữ trung bình B byte/s, retention T giây và replication factor RF:

\[
Storage_{logical} \approx B \times T \times RF
\]

Ví dụ 10 MiB/s, retention 7 ngày và RF=3:

\[
10 \times 604.800 \times 3
= 18.144.000\ MiB
\]

Tương đương khoảng 17,3 TiB cho toàn bộ replica, trước index, segment, filesystem overhead, retention overlap, compaction và headroom.

Trong công thức storage, dùng byte rate gần với dữ liệu thực sự được giữ trên log sau compression/recompression. Không dùng payload rate chưa nén nếu topic lưu batch đã nén và chưa có bước recompression làm thay đổi kích thước.

## 8. Đo kích thước sau serialization trong Java

Để có số liệu đáng tin cậy, đo byte array mà serializer thực tế tạo ra. Ví dụ helper sau tính phần byte của key, value và headers:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.serialization.Serializer;

public final class EventSizeEstimator {

    private EventSizeEstimator() {
    }

    public static <K, V> long estimateApplicationBytes(
            String topic,
            K key,
            V value,
            Headers headers,
            Serializer<K> keySerializer,
            Serializer<V> valueSerializer) {

        byte[] keyBytes = keySerializer.serialize(topic, key);
        byte[] valueBytes = valueSerializer.serialize(topic, value);

        long total = lengthOf(keyBytes) + lengthOf(valueBytes);

        for (Header header : headers) {
            total += header.key().getBytes(StandardCharsets.UTF_8).length;
            total += lengthOf(header.value());
        }

        return total;
    }

    private static int lengthOf(byte[] bytes) {
        return bytes == null ? 0 : bytes.length;
    }
}
~~~

Helper này chỉ tính byte của serialized key, value và nội dung headers. Nó không tính varint/record fields, record batch header, request protocol, compression hoặc TCP/TLS/IP overhead. Khi sử dụng trong ứng dụng thật:

- Dùng đúng serializer và cấu hình giống producer đang chạy.
- Tránh serialize lần thứ hai chỉ để đo nếu chi phí CPU đáng kể.
- Có thể đo ở serialization boundary rồi truyền byte arrays vào producer.
- Ghi histogram kích thước thay vì chỉ ghi average.
- Không log payload chỉ để kiểm tra kích thước.

Nếu key hoặc value null, serializer có thể trả null; helper xem phần đó là 0 byte payload. Kafka vẫn mã hóa trường length/record metadata tương ứng.

### 8.1. Đo JSON đúng cách

Nếu producer dùng JSON serializer, hãy đo byte output của serializer. Không dùng phép đo String.length() vì length() đếm UTF-16 code units của Java String, không phải byte UTF-8.

Với JSON UTF-8:

~~~java
byte[] jsonBytes = json.getBytes(StandardCharsets.UTF_8);
int serializedSize = jsonBytes.length;
~~~

Tuy nhiên, cách này chỉ đúng nếu byte array đó thực sự là payload gửi tới Kafka. Nếu serializer thêm schema ID, envelope hoặc metadata, hãy đo output của serializer thực tế.

## 9. Kiểm chứng bằng Kafka metrics

Phép tính từ event rate và serialized size là mô hình ban đầu. Sau khi triển khai, đối chiếu với producer và broker metrics.

### 9.1. Producer metrics

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| record-send-rate | Số record producer gửi mỗi giây |
| record-size-avg | Kích thước record trung bình |
| record-size-max | Kích thước record lớn nhất |
| byte-rate theo topic | Byte producer gửi mỗi giây cho topic |
| batch-size-avg | Kích thước batch trung bình |
| records-per-request-avg | Số record trung bình trong một request |
| compression-rate-avg | Tỷ lệ kích thước batch sau nén trên trước nén |
| record-retry-rate | Số record retry mỗi giây |
| record-error-rate | Số record gửi lỗi mỗi giây |

byte-rate theo topic đo tốc độ byte producer gửi trong các record batches; trong implementation producer, giá trị được ghi từ kích thước batch ước lượng sau khi batch được nén. Vì vậy, so sánh metric này với compressed batch estimate, không so trực tiếp với payload rate chưa nén. record-size-avg giúp kiểm tra giả định kích thước record; compression-rate-avg cho biết tỷ lệ batch sau nén trên trước nén.

### 9.2. Broker metrics

Theo dõi các broker topic metrics:

| Metric | Ý nghĩa |
|---|---|
| MessagesInPerSec | Số message/record broker nhận |
| BytesInPerSec | Byte broker nhận từ client |
| ReplicationBytesInPerSec | Byte broker nhận từ các broker khác |
| BytesOutPerSec | Byte broker gửi tới client |
| ReplicationBytesOutPerSec | Byte broker gửi tới broker khác |

BytesInPerSec và ReplicationBytesInPerSec là hai luồng khác nhau. Nếu gộp chúng, sẽ khó biết producer traffic tăng hay replication traffic tăng do recovery/reassignment.

### 9.3. So sánh model và thực tế

| So sánh | Câu hỏi |
|---|---|
| Event count vs MessagesInPerSec | Có publish trùng hoặc ghi nhiều topic không? |
| Estimated compressed batch bytes vs producer byte-rate | Đã tính key, headers, serializer envelope và compression chưa? |
| Producer byte-rate vs broker BytesInPerSec | Có chênh lệch do sampling, compression hoặc metric scope không? |
| Compression ratio vs batch-size-avg | Batch có đủ lớn và payload có nén được không? |
| Broker BytesInPerSec vs NIC receive | Có protocol overhead, replication hoặc traffic khác không? |
| ReplicationBytesInPerSec vs replica movement | Có recovery/reassignment đang chạy không? |

Không yêu cầu các metric bằng nhau tuyệt đối: chúng đo ở các lớp khác nhau, có thời gian lấy mẫu khác nhau và có thể áp dụng aggregation khác nhau.

## 10. Ví dụ capacity estimate hoàn chỉnh

Giả sử một hệ thống event streaming có:

- 12.000 events/s ở giờ cao điểm bình thường.
- Serialized application size trung bình 1,5 KiB/event.
- Peak factor dự phòng 2,5.
- Compression ratio đo từ batch benchmark là 0,45.
- Retention cần được tính riêng sau khi biết byte rate lưu trên log.

### Bước 1: Tính payload ingress

\[
12.000 \times 1.536
= 18.432.000\ B/s
\]

Tương đương:

- 18,43 MB/s.
- 17,58 MiB/s.

### Bước 2: Tính peak ingress

\[
R_{peak} = 12.000 \times 2,5 = 30.000\ events/s
\]

\[
30.000 \times 1.536
= 46.080.000\ B/s
\]

Tương đương khoảng 46,08 MB/s hoặc 43,95 MiB/s payload trước compression.

### Bước 3: Ước lượng compressed batch bytes

Ở tải trung bình:

\[
17,58 \times 0,45 \approx 7,91\ MiB/s
\]

Ở peak:

\[
43,95 \times 0,45 \approx 19,78\ MiB/s
\]

Đây là ước lượng batch bytes theo compression ratio quan sát được, chưa gồm request/network overhead. Compression ratio ở peak có thể khác nếu batch size và phân phối payload thay đổi.

### Bước 4: Ước lượng volume trong ngày

Nếu 17,58 MiB/s duy trì liên tục 24 giờ:

\[
17,58 \times 86.400
\approx 1.518.912\ MiB/day
\]

Tương đương xấp xỉ 1,45 TiB/day payload chưa nén. Nếu log giữ batch nén với ratio 0,45, volume compressed lý thuyết sẽ thấp hơn, nhưng phải dùng số đo disk/log thực tế để chốt retention capacity.

### Bước 5: Xác minh bằng metrics

Sau khi triển khai, so sánh:

1. Producer record-send-rate với 12.000 events/s.
2. Producer record-size-avg với 1,5 KiB.
3. Producer topic byte-rate với ước lượng compressed batch khoảng 7,91 MiB/s; 18,43 MB/s là payload rate trước compression.
4. Producer compression-rate-avg với 0,45 và kiểm tra batch size có tương tự benchmark không.
5. Broker BytesInPerSec với compressed batch rate producer gửi tới các broker, tổng hợp theo đúng topic/broker và cùng cửa sổ đo.
6. Broker ReplicationBytesInPerSec riêng với replication traffic.

Nếu sai lệch lớn, kiểm tra event fan-out, duplicate publish, headers, serializer framing, compression, sampling interval và metric aggregation.

## 11. Checklist thu thập đầu vào

Trước khi gửi capacity estimate, thu thập:

- [ ] Event type và topic đích.
- [ ] Số event theo ngày/giờ và rate theo các cửa sổ 1s, 1m, 5m, 15m.
- [ ] Average, p95, p99 và maximum event size sau serialization.
- [ ] Key size và headers size.
- [ ] Serializer và schema/envelope đang sử dụng.
- [ ] Compression codec và compression ratio benchmark.
- [ ] Producer count và số lần publish mỗi business event.
- [ ] Peak factor, burst duration và lịch sự kiện cao điểm.
- [ ] Consumer group count và replay/backfill pattern.
- [ ] Replication factor và traffic giữa broker.
- [ ] Retention và compaction policy.
- [ ] Producer/broker byte metrics để đối chiếu sau triển khai.

## 12. Bài thực hành và tự kiểm tra

### Thực hành A — Tính ingress từ volume nghiệp vụ

1. Chọn một nghiệp vụ như đơn hàng, thanh toán hoặc telemetry.
2. Ước lượng số entity/ngày và số event/entity.
3. Tính event rate trung bình 24 giờ và trong giờ hoạt động.
4. Ghi lại peak rate theo cửa sổ 1 phút.
5. Giải thích vì sao daily average không đủ để sizing network.

### Thực hành B — Đo serialized event size

1. Tạo producer Java với serializer thực tế của ứng dụng.
2. Serialize key, value và headers thành byte arrays.
3. Ghi histogram size theo event type.
4. So sánh JSON character length với UTF-8 byte length.
5. Đo p50/p95/p99 và maximum để tìm payload lớn bất thường.

### Thực hành C — Tính byte rate và compression

1. Lập bảng rate và average size cho ít nhất ba event type.
2. Tính payload ingress bằng tổng R_i × S_i.
3. Chạy producer với codec đang dùng trong production.
4. Thu byte-rate, batch-size-avg và compression-rate-avg.
5. Tính compressed batch byte rate và so sánh với broker BytesInPerSec.
6. Giải thích sai lệch do record/batch/protocol overhead và sampling.

### Thực hành D — Peak và burst estimate

1. Chọn peak factor từ dữ liệu hoặc một giả định có ghi rõ.
2. Tính peak byte/s.
3. Tính tổng burst bytes trong 30 giây, 5 phút và 15 phút.
4. So sánh burst volume với consumer processing capacity.
5. Đề xuất mức headroom và cách kiểm chứng bằng load test.

### Câu hỏi tự kiểm tra

1. Công thức cơ bản tính payload ingress từ event rate và event size là gì?
2. Vì sao records/s không đủ để mô tả tải Kafka?
3. Event rate suy ra từ volume nghiệp vụ như thế nào?
4. Vì sao phải đo kích thước sau serializer?
5. Object size trong JVM khác serialized size ở điểm nào?
6. Key, value và headers đóng góp thế nào vào application bytes?
7. Kafka record batch có những phần overhead nào?
8. Weighted average event size được tính ra sao?
9. Vì sao không nên nhân p99 rate với p99 event size để gọi đó là p99 byte rate?
10. Peak rate và burst volume khác nhau thế nào?
11. Compression ratio được định nghĩa ra sao trong producer metrics?
12. Vì sao compression ratio phụ thuộc batching và nội dung payload?
13. Producer ingress khác replication traffic như thế nào?
14. Nhiều consumer groups ảnh hưởng tới byte egress ra sao?
15. Những metrics nào giúp đối chiếu capacity estimate với broker thực tế?

## Kết luận

Ước lượng ingress bắt đầu từ event rate và kích thước byte sau serialization. Với nhiều loại event, tính tổng từng tích rate × size; dùng rate theo cửa sổ để phân biệt average, peak và burst. Sau đó bổ sung overhead của Kafka record/batch, compression và protocol bằng số đo thực tế. Producer byte-rate và broker BytesInPerSec giúp xác minh client ingress; ReplicationBytesInPerSec phải được theo dõi riêng. Khi các giả định được ghi rõ và kiểm chứng bằng metrics, capacity estimate trở thành đầu vào đáng tin cậy cho hoạch định network, storage, partition và headroom.

## Tài liệu tham khảo

- [Apache Kafka 4.4 — Message Format](https://kafka.apache.org/44/implementation/message-format/)
- [Apache Kafka 4.4 — Monitoring](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka 4.4 — Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka 4.4 — Broker Configs](https://kafka.apache.org/44/configuration/broker-configs/)
