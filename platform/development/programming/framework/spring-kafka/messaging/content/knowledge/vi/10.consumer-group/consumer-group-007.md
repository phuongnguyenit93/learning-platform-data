# Group lag và ý nghĩa vận hành

Consumer group lag là khoảng cách giữa tiến độ đọc đã ghi nhận của một consumer group và vị trí dữ liệu hiện có trong các partition mà group đang đọc. Lag giúp đội vận hành biết consumer có theo kịp tốc độ producer hay không, backlog đang nằm ở partition nào và liệu năng lực xử lý có đủ đáp ứng tải hay không.

Lag tăng không tự động có nghĩa dữ liệu bị mất. Nó thường cho biết record đang chờ được đọc hoặc xử lý. Ngược lại, lag bằng không tại một thời điểm cũng không chứng minh toàn bộ luồng messaging đang khỏe mạnh: consumer có thể đang dừng, group chưa có assignment hoặc topic không phát sinh dữ liệu. Vì vậy, cần đọc lag cùng trạng thái consumer group, tốc độ phát sinh dữ liệu, thời gian xử lý, lỗi listener và tuổi của record.

Bài học thuộc chương **Consumer group** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Consumer group lag là gì?

Kafka lưu record trong các partition của topic. Consumer group đọc các partition đó và lưu tiến độ đã commit riêng cho từng topic-partition. Lag biểu thị khoảng cách giữa vị trí dữ liệu mới nhất và vị trí mà group đã commit.

Ví dụ, một partition có vị trí cuối log là 1.000 và group đã commit offset 900. Khoảng cách offset là 100. Điều này cho biết group còn cách cuối log 100 offset theo phép tính thông thường.

~~~text
Topic: order-events, Partition: 0

Offset:      900                         999
               |--------------------------|
Committed:    900
Log end:                                 1000 (next offset)
Lag:                                      100
~~~

Trong ví dụ, committed offset 900 là vị trí tiếp theo group sẽ đọc khi khôi phục từ offset đã commit. Log end offset 1.000 là vị trí tiếp theo mà broker có thể append record. Hiệu của hai giá trị là 100.

Lag thường được theo dõi theo từng partition, sau đó tổng hợp theo consumer group, topic hoặc toàn hệ thống. Một group đọc nhiều topic sẽ có lag riêng trên từng topic-partition.

## 2. Offset nào được dùng để tính lag?

Để hiểu lag, cần phân biệt ba khái niệm: log end offset, consumer position và committed offset.

### 2.1. Log end offset

Log end offset (LEO) là offset tiếp theo mà broker sẽ dùng khi append record vào partition. Nếu record cuối cùng có offset 99 thì log end offset thường là 100.

LEO mô tả vị trí cuối của log trên replica được truy vấn. Trong thực tế, công cụ giám sát có thể dùng high watermark hoặc một mốc đọc được khác tùy loại lag và API. Do đó, khi so sánh số liệu từ nhiều công cụ, cần biết chính xác metric đó lấy mốc cuối nào.

### 2.2. Consumer position

Consumer position là vị trí tiếp theo mà Kafka consumer sẽ đọc trong phiên hoạt động hiện tại. Khi consumer poll và nhận record, position có thể tiến lên ngay cả khi ứng dụng chưa commit offset.

Position thuộc trạng thái runtime của consumer. Nếu tiến trình dừng trước khi commit, position trong bộ nhớ mất đi và consumer có thể khởi động lại từ committed offset cũ.

### 2.3. Committed offset

Committed offset là vị trí tiếp theo mà consumer group đã lưu vào Kafka để có thể tiếp tục đọc sau khi consumer restart hoặc partition được giao cho consumer khác.

Committed offset là mốc bền vững của tiến độ group. Nó không chứng minh tác vụ nghiệp vụ bên ngoài Kafka đã hoàn tất nếu ứng dụng commit sai thời điểm hoặc tác dụng phụ chưa được đồng bộ.

### 2.4. Công thức lag cơ bản

Với một topic-partition, phép tính thường gặp là:

\[
\text{Committed Lag} = \text{Log End Offset} - \text{Committed Offset}
\]

Ví dụ:

| Giá trị | Offset |
| --- | ---: |
| Log end offset | 1.500 |
| Committed offset | 1.420 |
| Committed lag | 80 |

Nếu group đã đọc và commit qua offset 1.499, committed offset sẽ là 1.500 và lag theo phép tính này bằng 0.

Một số công cụ hiển thị lag dựa trên consumer position thay vì committed offset. Khi đó, lag có thể thấp hơn committed lag nếu consumer đã poll dữ liệu nhưng chưa commit. Hãy đọc định nghĩa metric thay vì mặc định mọi chỉ số mang tên lag đều dùng cùng một mốc.

### 2.5. Lag không luôn bằng chính xác số event có thể đọc

Offset là vị trí trong log, không phải bộ đếm liên tục của những payload mà ứng dụng chắc chắn sẽ nhận. Offset có thể có khoảng trống do log compaction, transaction control records hoặc các record không được hiển thị với isolation level đang dùng.

Vì vậy, hiệu offset thường được gọi là record lag nhưng nên hiểu là khoảng cách vị trí trong log. Nó có thể gần với số record đang chờ trong log thông thường, nhưng không phải lúc nào cũng bằng chính xác số event ứng dụng sẽ nhận được.

## 3. Lag được tính riêng theo partition

Consumer group lưu offset riêng cho từng partition. Do đó, không thể chỉ dùng một offset duy nhất để mô tả toàn bộ group.

Ví dụ group `billing-service` đọc topic `payment-events` có ba partition:

| Partition | Log end offset | Committed offset | Lag |
| --- | ---: | ---: | ---: |
| 0 | 12.000 | 11.990 | 10 |
| 1 | 8.500 | 8.100 | 400 |
| 2 | 9.200 | 9.190 | 10 |
| **Tổng** |  |  | **420** |

Tổng lag là 420 offset. Tuy nhiên, partition 1 chiếm phần lớn backlog. Nếu chỉ nhìn tổng, đội vận hành có thể bỏ qua tình trạng phân phối tải không đồng đều.

Các góc nhìn quan trọng:

- **Lag theo partition:** tìm partition đang tích lũy backlog.
- **Tổng lag theo group:** ước lượng tổng khoảng cách offset của group trên các partition.
- **Lag lớn nhất:** phát hiện partition chậm nhất.
- **Tốc độ thay đổi lag:** biết backlog đang tăng, giảm hay ổn định.
- **Lag theo topic:** xác định topic nào đang ảnh hưởng tới group.

Nếu một partition lag cao trong khi các partition khác gần bằng không, cần điều tra key skew, dữ liệu nóng, consumer assignment hoặc một tác vụ xử lý đặc biệt chậm ở partition đó.

## 4. Minh họa lag tăng và giảm theo thời gian

Lag là một đại lượng thay đổi theo thời gian. Producer liên tục append record; consumer liên tục đọc và commit. Khi tốc độ dữ liệu vào lớn hơn tốc độ xử lý, backlog tăng. Khi consumer xử lý nhanh hơn tốc độ dữ liệu vào, backlog giảm.

~~~mermaid
flowchart TD
    A[Producer append record] --> B[Partition log tăng]
    B --> C{Consumer xử lý kịp?}
    C -->|Không| D[Lag tăng]
    C -->|Có| E[Consumer position tiến]
    E --> F[Commit offset]
    F --> G[Lag giảm hoặc giữ ổn định]
    D --> H[Điều tra throughput, lỗi, rebalance]
~~~

Giả sử:

- Producer tạo 800 record mỗi giây.
- Consumer group xử lý và commit tương đương 650 record mỗi giây.
- Backlog tăng khoảng 150 record mỗi giây trong điều kiện đơn giản.

Nếu tình trạng kéo dài 10 phút, lag có thể tăng thêm khoảng 90.000 record. Con số thực tế còn phụ thuộc partition, batch, retry, transaction và cách metric đếm offset.

Khi consumer tăng năng lực lên 1.000 record mỗi giây trong lúc producer vẫn tạo 800 record mỗi giây, backlog có thể giảm ròng khoảng 200 record mỗi giây. Nếu lag đang là 90.000, thời gian lý thuyết để xử lý hết backlog xấp xỉ 450 giây, giả sử tốc độ ổn định và không có thêm gián đoạn.

Công thức ước lượng đơn giản:

\[
\text{Drain Time} \approx
\frac{\text{Current Backlog}}
{\text{Consumer Throughput} - \text{Producer Throughput}}
\]

Công thức chỉ có ý nghĩa khi throughput consumer lớn hơn throughput producer và các tốc độ được đo trên cùng phạm vi dữ liệu. Nếu consumer không nhanh hơn producer, backlog không thể tự giảm.

## 5. Phân biệt record lag và time lag

Record lag cho biết khoảng cách offset. Time lag cố gắng biểu diễn dữ liệu đang chờ đã cũ bao lâu. Hai chỉ số trả lời hai câu hỏi khác nhau.

| Chỉ số | Câu hỏi trả lời | Hạn chế |
| --- | --- | --- |
| Record/offset lag | Group đang cách cuối log bao nhiêu offset? | Không phản ánh trực tiếp thời gian chờ hoặc độ quan trọng của event. |
| Time lag | Event chưa xử lý đã cũ bao lâu? | Cách tính phụ thuộc metric, timestamp và công cụ. |
| Processing latency | Mất bao lâu để listener xử lý một record hoặc batch? | Không cho biết backlog đã tích lũy bao nhiêu. |
| End-to-end latency | Từ lúc event phát sinh đến khi nghiệp vụ hoàn tất mất bao lâu? | Cần correlation/timestamp xuyên suốt các dịch vụ. |

Một topic nhận hàng nghìn event mỗi giây có thể có lag 10.000 nhưng chỉ tương đương vài giây dữ liệu. Một topic ít event mỗi phút có lag 20 nhưng event cũ nhất có thể đã chờ hàng giờ.

Time lag không có một công thức chuẩn duy nhất trong mọi công cụ. Một số hệ thống lấy timestamp của record mới nhất đã xử lý hoặc record cũ nhất chưa xử lý; hệ thống khác đo chênh lệch giữa thời điểm hiện tại và timestamp event. Cần xem định nghĩa metric, clock skew và semantics timestamp trước khi đặt cảnh báo.

Với nghiệp vụ có SLA theo thời gian, time lag hoặc end-to-end latency thường có ý nghĩa trực tiếp hơn một ngưỡng record lag cố định.

## 6. Lag cao có ý nghĩa vận hành gì?

Lag cao cho biết consumer group đang tụt lại so với vị trí dữ liệu hiện có. Tác động cụ thể phụ thuộc loại dữ liệu và SLA của service.

Ví dụ:

- **Thanh toán:** trạng thái giao dịch hoặc đối soát có thể cập nhật chậm.
- **Đơn hàng:** projection và thông báo cho khách hàng có thể trễ.
- **Kho hàng:** số lượng tồn kho có thể không phản ánh event mới nhất.
- **Telemetry:** dashboard và cảnh báo có thể dựa trên dữ liệu cũ.
- **Audit:** bản ghi kiểm toán có thể xuất hiện muộn trong hệ thống lưu trữ.

Lag cao kéo dài có thể gây ra:

- Event được xử lý sau thời điểm nghiệp vụ mong muốn.
- Backlog chiếm dung lượng log trong thời gian dài.
- Consumer phải xử lý lượng dữ liệu lớn sau khi khôi phục.
- Tăng nguy cơ vượt retention nếu consumer tụt lại quá lâu.
- Tăng độ trễ giữa các dịch vụ phụ thuộc event.
- Khó đạt SLA hoặc thời gian hoàn tất workflow.

Lag không đồng nghĩa dữ liệu đã mất. Nếu record vẫn còn trong retention và consumer có thể đọc, group có thể tiếp tục xử lý. Nhưng nếu retention xóa dữ liệu trước khi group đọc tới, consumer có thể không còn khả năng đọc lại toàn bộ backlog ban đầu.

## 7. Các nguyên nhân thường làm lag tăng

### 7.1. Producer tạo dữ liệu nhanh hơn consumer xử lý

Đây là nguyên nhân phổ biến. Producer throughput tăng do traffic, batch import, chiến dịch hoặc một dịch vụ upstream phát nhiều event hơn bình thường.

Cách nhận biết:

- Record send rate tăng.
- Consumer processing rate không tăng tương ứng.
- Lag tăng trên nhiều partition.
- Listener không nhất thiết có lỗi; chỉ đơn giản xử lý không kịp.

Hướng xử lý là xác định tải đầu vào, kiểm tra năng lực consumer và quyết định scale hoặc điều tiết producer nếu hệ thống hỗ trợ backpressure.

### 7.2. Consumer xử lý chậm

Listener có thể thực hiện truy vấn database, gọi HTTP, tính toán nặng hoặc ghi nhiều hệ thống bên ngoài. Nếu thời gian xử lý mỗi record tăng, consumer throughput giảm và lag tăng.

Cần đo:

- Thời gian xử lý listener.
- Thời gian chờ database/HTTP.
- Số lần retry.
- Kích thước batch và số record mỗi poll.
- CPU, heap, GC và thread utilization.

Tăng consumer count không giải quyết được dependency phía sau đang quá tải. Có thể cần tối ưu truy vấn, batch write, connection pool, cache hoặc giảm tác vụ đồng bộ trong listener.

### 7.3. Consumer bị dừng hoặc không được gán partition

Consumer có thể không chạy do crash, deployment, lỗi cấu hình hoặc không kết nối được broker. Consumer group có thể ở trạng thái không có member hoạt động hoặc thiếu consumer nhận assignment.

Một group không có consumer vẫn có thể có committed offset cũ và lag tiếp tục tăng khi producer ghi dữ liệu. Cần phân biệt group không hoạt động với group đang hoạt động nhưng xử lý chậm.

Kiểm tra group state, member, assignment và log khởi động của listener container trước khi tăng concurrency.

### 7.4. Rebalance xảy ra thường xuyên

Rebalance xảy ra khi member tham gia/rời group, subscription thay đổi hoặc consumer không đáp ứng yêu cầu poll/heartbeat. Trong giai đoạn rebalance, partition có thể tạm thời không được xử lý.

Nguyên nhân có thể gồm:

- Container restart liên tục.
- Consumer vượt `max.poll.interval.ms` vì xử lý quá lâu.
- Mạng không ổn định hoặc broker không nhận heartbeat.
- Scale deployment lên/xuống liên tục.
- Thay đổi topic subscription hoặc partition.

Nếu rebalance xảy ra liên tục, tăng số consumer có thể làm tình hình tệ hơn. Cần tìm nguyên nhân khiến group membership không ổn định.

### 7.5. Retry hoặc poison record làm chậm partition

Một record lỗi có thể bị retry nhiều lần hoặc chờ backoff. Nếu cách xử lý lỗi chặn partition, các record sau trên cùng partition phải đợi. Lag partition đó tăng trong khi các partition khác có thể vẫn bình thường.

Cần kiểm tra:

- Exception listener và số lần retry.
- Error handler đang seek, retry hay chuyển record sang DLT.
- Thời gian backoff và số lần thử.
- Tỷ lệ record bị lỗi theo topic/partition.
- DLT có tăng bất thường hay không.

Không nên retry vô hạn với lỗi dữ liệu không thể tự hết. Cần phân biệt lỗi tạm thời của dependency với payload không hợp lệ và có chính sách DLT phù hợp.

### 7.6. Phân phối key không đều

Nếu nhiều record có cùng key hoặc một số key nóng, một partition có thể nhận nhiều dữ liệu hơn các partition còn lại. Consumer group không thể cân bằng một partition đơn lẻ cho nhiều consumer trong cùng group.

Dấu hiệu là một partition lag cao trong khi các partition khác gần bằng không. Cần xem phân phối key, throughput theo partition và thời gian xử lý của record trong partition nóng.

Thay đổi key hoặc tăng partition có thể giúp phân phối lại trong tương lai, nhưng có thể ảnh hưởng thứ tự theo key và không tự di chuyển record cũ. Đây là thay đổi thiết kế cần đánh giá trước.

### 7.7. Broker hoặc network gặp vấn đề

Broker có thể chậm do disk I/O, CPU, replication, request queue hoặc network. Consumer fetch chậm khiến processing rate giảm dù listener không làm nhiều việc.

Theo dõi broker request latency, bytes in/out, under-replicated partitions, network error và consumer fetch metrics. Nếu nhiều group cùng lag trên các topic do một cluster phục vụ, cần điều tra hạ tầng chung.

## 8. Đọc lag bằng Kafka CLI

Kafka cung cấp công cụ `kafka-consumer-groups.sh` để xem trạng thái consumer group và offset.

Liệt kê group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

Xem chi tiết một group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-service
~~~

Kết quả thường có các cột tương tự:

| Cột | Ý nghĩa |
| --- | --- |
| GROUP | Tên consumer group. |
| TOPIC | Topic mà group đang đọc. |
| PARTITION | Partition cụ thể. |
| CURRENT-OFFSET | Offset đã commit của group. |
| LOG-END-OFFSET | Mốc cuối log mà công cụ báo cáo. |
| LAG | Khoảng cách offset giữa log end và current offset. |
| CONSUMER-ID | Định danh consumer member nếu có. |
| HOST | Host của consumer member. |
| CLIENT-ID | Client ID của consumer. |

Tên hoặc cách hiển thị cột có thể khác giữa các phiên bản Kafka CLI. Nếu CURRENT-OFFSET chưa có, công cụ có thể hiển thị dấu gạch ngang và lag là unknown thay vì một số hợp lệ.

Ví dụ kết quả minh họa:

~~~text
GROUP            TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
billing-service  payment-events 0          1200            1210            10
billing-service  payment-events 1          900             1500            600
billing-service  payment-events 2          750             755             5
~~~

Trong ví dụ, partition 1 có lag 600, lớn hơn đáng kể hai partition còn lại. Nên bắt đầu điều tra partition đó: consumer nào được gán, key nào tập trung, record có lỗi/retry hay tác vụ downstream nào chậm.

Có thể xem thêm trạng thái group tùy phiên bản Kafka:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-service \
  --state
~~~

Hoặc xem assignment/member:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-service \
  --members \
  --verbose
~~~

Các option cụ thể phụ thuộc phiên bản Kafka. Hãy dùng help của script đi kèm cluster/client tương ứng.

## 9. Lag, consumer position và commit cadence

Một consumer có thể đã poll record nhưng chưa commit. Vì thế, committed lag và lag theo position có thể khác nhau.

Ví dụ:

- Log end offset là 1.000.
- Consumer position đã tiến tới 980.
- Committed offset mới nhất là 950.

Khi đó:

- Khoảng cách theo position: 20.
- Committed lag: 50.

Consumer đã đọc qua một phần backlog nhưng chưa ghi nhận tiến độ bền vững tới group coordinator. Nếu consumer dừng, nó có thể đọc lại từ committed offset 950.

Điều này không nhất thiết là lỗi. Nếu container dùng batch acknowledgement, offset có thể được commit sau khi batch poll được xử lý. Tuy nhiên, commit cadence quá thưa làm committed lag cao hơn lượng công việc thực tế đang chờ.

Cần đọc lag cùng các chỉ số consumer position, records consumed, commit rate và listener processing. Không nên chỉ tăng tần suất commit để làm đẹp dashboard; commit quá thường xuyên cũng tạo thêm request và chi phí coordinator.

## 10. Lag với transaction và isolation level

Với consumer đọc dữ liệu transactional, isolation level ảnh hưởng record nào được nhìn thấy.

- `read_uncommitted` cho phép consumer đọc cả record thuộc transaction chưa commit.
- `read_committed` chỉ trả về record của transaction đã commit và dừng ở last stable offset (LSO), tức mốc an toàn cho dữ liệu committed.

Nếu một transaction còn mở lâu, LSO có thể thấp hơn log end offset. Consumer dùng read_committed có thể không đọc tiếp được qua vùng transaction chưa hoàn tất, dù log end offset vẫn tăng.

Do đó, lag đo bằng log end offset có thể bao gồm khoảng cách mà consumer read_committed chưa thể đọc vì transaction chưa hoàn tất. Đây không nhất thiết là consumer xử lý chậm; cần kiểm tra transaction producer, thời gian transaction mở và LSO/high watermark theo công cụ.

Khi điều tra lag trên topic transactional, cần biết isolation level của consumer và định nghĩa lag mà công cụ đang hiển thị.

## 11. Lag với log compaction và retention

### 11.1. Log compaction

Trên topic compacted, Kafka có thể loại bỏ các phiên bản cũ của cùng key trong quá trình compaction. Offset trong log có thể có khoảng trống so với record ứng dụng nhìn thấy.

Vì vậy, chênh lệch offset trên compacted topic không nhất thiết bằng số payload đang chờ consumer nhận. Lag vẫn hữu ích để theo dõi vị trí đọc, nhưng cần hiểu semantics của log compaction.

### 11.2. Retention và nguy cơ không còn dữ liệu để đọc

Kafka giữ record theo retention policy. Nếu consumer group tụt lại lâu hơn thời gian dữ liệu được giữ, committed offset có thể nằm trước log start offset của partition.

Khi consumer tiếp tục, Kafka có thể báo offset out of range. Hành vi sau đó phụ thuộc `auto.offset.reset` và chính sách phục hồi của ứng dụng.

Ví dụ:

- Group đã commit offset 100.
- Retention xóa các segment cũ khiến log start offset tăng lên 500.
- Consumer quay lại với offset 100, nhưng dữ liệu từ offset đó không còn.
- Consumer cần xử lý tình huống offset out of range; nếu reset về earliest thì bắt đầu từ dữ liệu còn lại, còn latest có thể bỏ qua phần backlog còn giữ.

Đây là lý do cần đặt cảnh báo cho lag/time lag và đảm bảo khả năng xử lý backlog trước khi dữ liệu hết retention. Lag cao kéo dài có thể chuyển từ vấn đề độ trễ thành rủi ro không thể replay toàn bộ dữ liệu.

## 12. Tăng consumer để giảm lag

Scale consumer là một cách tăng throughput, nhưng chỉ hiệu quả khi còn partition có thể phân phối và bottleneck nằm ở consumer capacity.

Ví dụ topic có sáu partition:

~~~text
6 partitions

Concurrency 2:
  Consumer A -> P0, P1, P2
  Consumer B -> P3, P4, P5

Concurrency 6:
  Consumer A -> P0
  Consumer B -> P1
  Consumer C -> P2
  Consumer D -> P3
  Consumer E -> P4
  Consumer F -> P5
~~~

Sơ đồ chỉ là một cách assignment minh họa; assignor có thể phân phối khác. Trong cùng group, số consumer hữu ích bị giới hạn bởi số partition được assign. Tăng concurrency từ sáu lên mười không tạo thêm luồng đọc song song cho topic sáu partition.

Trước khi scale, cần kiểm tra:

- Lag tăng trên tất cả partition hay chỉ một vài partition?
- Consumer có đủ CPU, memory và thread không?
- Database hoặc HTTP dependency có còn capacity không?
- Thời gian listener có bị chi phối bởi I/O không?
- Có rebalance hoặc poll timeout không?
- Số partition có đủ cho concurrency mục tiêu không?

Nếu consumer đã bão hòa database, tăng consumer có thể làm database quá tải và khiến lag tăng nhanh hơn. Cần scale toàn bộ đường xử lý, không chỉ số consumer.

### 12.1. Tăng partition có phải giải pháp không?

Tăng partition có thể mở rộng mức song song cho group trong tương lai. Tuy nhiên, nó không tự chia backlog cũ thành các partition mới; record hiện có vẫn nằm ở partition cũ.

Ngoài ra, thay đổi số partition có thể làm thay đổi ánh xạ key sang partition với partitioner mặc định. Nếu thứ tự theo key quan trọng, phải đánh giá tác động trước khi tăng partition.

Tăng partition cũng làm tăng metadata, replication traffic và tài nguyên broker. Đây là quyết định topology, không phải thao tác chữa cháy mặc định mỗi khi lag tăng.

## 13. Theo dõi lag bằng metric trong hệ thống Spring Kafka

Trong ứng dụng Spring Kafka, có thể kết hợp Kafka client metrics, listener metrics và metric hạ tầng để hiểu nguyên nhân lag.

Các nhóm chỉ số nên quan sát:

| Nhóm | Chỉ số gợi ý | Ý nghĩa |
| --- | --- | --- |
| Consumer fetch | Fetch rate, fetch latency, bytes consumed | Consumer lấy dữ liệu từ broker có hiệu quả không. |
| Consumer records | Records consumed rate, records lag/max lag nếu client export | Consumer đang đọc bao nhiêu và khoảng cách fetch tới cuối log. |
| Listener | Processing count, processing duration, error count | Listener xử lý nhanh hay chậm, có lỗi không. |
| Commit | Commit rate, commit latency, commit failures | Tiến độ đọc có được ghi nhận ổn định không. |
| Group | Member count, assignment, rebalance count | Group có ổn định và phân phối partition hợp lý không. |
| Producer | Record send rate, request latency | Tốc độ dữ liệu đi vào có tăng bất thường không. |
| Broker | Request queue, disk, network, ISR | Hạ tầng Kafka có đang là bottleneck không. |

Spring Kafka có thể tích hợp Micrometer để ghi nhận listener observation/timer tùy cấu hình và phiên bản. Kafka client cũng cung cấp consumer metrics; tên metric, mức chi tiết và cách export phụ thuộc phiên bản Kafka client và hệ thống monitoring.

Không nên khẳng định một metric đơn lẻ luôn đại diện cho committed lag của toàn group. Một số consumer metrics phản ánh fetch lag hoặc lag theo consumer runtime; committed group lag thường được thu thập từ Kafka Admin API, exporter hoặc công cụ quản trị group.

Nên gắn metric với các nhãn phù hợp như consumer group, topic và partition, nhưng cần kiểm soát cardinality. Nếu hệ thống có hàng nghìn partition hoặc topic động, xuất mọi nhãn vào mọi hệ thống metric có thể làm tăng đáng kể chi phí monitoring.

## 14. Thiết kế cảnh báo lag

Một cảnh báo tốt nên phát hiện xu hướng và tác động, không chỉ dựa vào một con số cố định.

Có thể kết hợp:

- Lag tuyệt đối theo group/topic.
- Lag lớn nhất trên một partition.
- Tốc độ tăng lag trong một khoảng thời gian.
- Time lag hoặc tuổi record chưa xử lý.
- Consumer group không có member hoặc thiếu assignment.
- Listener error rate và processing latency.
- Khoảng thời gian lag vượt ngưỡng liên tục.

Ví dụ quy tắc cảnh báo minh họa:

| Mức | Điều kiện tham khảo | Hành động |
| --- | --- | --- |
| Warning | Lag tăng liên tục trong vài phút nhưng time lag vẫn trong SLA | Kiểm tra throughput, partition distribution và consumer utilization. |
| Critical | Time lag vượt SLA hoặc lag tiếp tục tăng dù consumer đang hoạt động | Điều tra ngay listener, downstream dependency và broker. |
| Critical | Group không có consumer trong khi topic vẫn nhận dữ liệu | Khôi phục listener/container hoặc deployment. |
| Critical | Committed offset cũ hơn log start offset | Đánh giá dữ liệu đã hết retention và kế hoạch phục hồi. |

Ngưỡng cụ thể phải dựa trên throughput bình thường, SLA và retention. Một topic telemetry có thể chấp nhận lag vài chục nghìn record nếu chỉ tương đương vài giây; một topic giao dịch có thể cần cảnh báo khi record chậm vài giây.

Tránh alert theo một sample đơn lẻ. Hãy dùng cửa sổ thời gian, điều kiện kéo dài và ngưỡng theo service để giảm cảnh báo giả.

## 15. Quy trình điều tra khi lag tăng

Khi nhận cảnh báo lag, nên đi theo thứ tự từ phạm vi rộng đến partition cụ thể.

1. **Xác định group và topic:** lag thuộc consumer group nào, topic nào và môi trường nào.
2. **Xem lag theo partition:** xác định mọi partition đều tăng hay chỉ một partition.
3. **Kiểm tra group state/member:** group có consumer đang hoạt động không, partition assignment có đủ không.
4. **So sánh producer và consumer throughput:** dữ liệu vào tăng hay consumer rate giảm.
5. **Kiểm tra listener latency/error:** listener có chậm, retry hoặc mắc ở một record lỗi không.
6. **Kiểm tra rebalance/poll:** group có rebalance liên tục hoặc consumer vượt max.poll.interval.ms không.
7. **Kiểm tra dependency:** database, HTTP, connection pool, CPU, memory, GC và network.
8. **Kiểm tra broker:** fetch latency, request queue, disk, replication và network.
9. **Kiểm tra retention:** backlog có nguy cơ vượt thời gian lưu dữ liệu không.
10. **Đánh giá biện pháp:** scale consumer, tối ưu listener, điều chỉnh partition hoặc giảm tốc độ producer theo nguyên nhân đã xác định.

Không nên reset offset để làm lag về zero như một biện pháp mặc định. Reset offset có thể bỏ qua dữ liệu chưa xử lý hoặc khiến dữ liệu được đọc lại; đây là thao tác ảnh hưởng trực tiếp đến tiến độ nghiệp vụ và cần quyết định có chủ đích.

## 16. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| Lag là số message chắc chắn còn chờ trong bộ nhớ consumer. | Lag thường là khoảng cách offset trong log, không phải số message trong RAM. |
| Lag bằng zero nghĩa service khỏe mạnh. | Group có thể không hoạt động hoặc topic không có dữ liệu mới; cần kiểm tra state và throughput. |
| Lag cao đồng nghĩa dữ liệu bị mất. | Thường là backlog; mất khả năng đọc chỉ xảy ra khi dữ liệu không còn trong retention hoặc có thao tác bỏ qua/reset. |
| Mọi metric lag đều giống nhau. | Metric có thể dựa trên committed offset, consumer position, fetch position hoặc mốc log khác nhau. |
| Offset là số lượng event liên tục. | Offset là vị trí log; compaction/transaction có thể tạo khoảng trống giữa record ứng dụng nhìn thấy. |
| Tăng consumer luôn giảm lag. | Mức song song bị giới hạn bởi partition và bottleneck có thể nằm ở downstream hoặc broker. |
| Chỉ cần tăng partition khi lag cao. | Cần xác định bottleneck; tăng partition ảnh hưởng key ordering và topology. |
| Commit offset là bằng chứng nghiệp vụ đã hoàn tất. | Commit chỉ ghi nhận tiến độ group; tính nhất quán với database/API cần thiết kế riêng. |
| Reset offset làm hệ thống khỏe hơn. | Reset có thể bỏ qua hoặc đọc lại dữ liệu; cần đánh giá tác động nghiệp vụ. |
| Retention không liên quan đến lag. | Consumer tụt lại quá lâu có thể không còn đọc được dữ liệu cũ khi retention xóa segment. |

## 17. Checklist vận hành consumer group lag

Khi theo dõi một consumer group, hãy xác nhận:

1. Có metric lag theo từng topic-partition và tổng theo group.
2. Có phân biệt committed lag với consumer/fetch position lag.
3. Có theo dõi producer rate và consumer processing rate.
4. Có metric thời gian xử lý listener, lỗi và retry.
5. Có theo dõi member count, assignment và rebalance.
6. Có cảnh báo theo xu hướng tăng lag và time lag/SLA.
7. Có kiểm tra retention khi backlog kéo dài.
8. Có đánh giá partition skew và key distribution.
9. Có quy trình scale consumer mà không làm downstream quá tải.
10. Có runbook cho reset/replay offset với phê duyệt nghiệp vụ phù hợp.

Consumer group lag là một chỉ báo quan trọng về khả năng theo kịp dữ liệu của hệ thống. Giá trị của nó nằm ở việc kết hợp offset theo partition với throughput, processing latency, group state và retention để xác định nguyên nhân. Khi đọc đúng ngữ nghĩa và xu hướng lag, đội vận hành có thể phát hiện sớm bottleneck, ước lượng thời gian xử lý backlog và chọn biện pháp khôi phục mà không vô tình bỏ qua dữ liệu nghiệp vụ.

