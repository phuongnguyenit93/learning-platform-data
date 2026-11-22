# Ước lượng số partition từ lưu lượng và mức song song

## Vì sao phải tính số partition trước khi tạo topic?

Partition là đơn vị lưu trữ log, replication và phân công xử lý trong Kafka. Số partition ảnh hưởng trực tiếp đến khả năng ghi/đọc song song, số consumer có thể hoạt động đồng thời trong một consumer group, dung lượng metadata và chi phí vận hành của cụm.

Nếu tạo quá ít partition, một số partition có thể phải gánh lưu lượng lớn, consumer group không thể mở rộng đủ số worker và throughput bị giới hạn. Nếu tạo quá nhiều partition, broker phải quản lý thêm log segment, file, replica, metadata và công việc phục hồi; rebalance và khởi động consumer cũng có thể tốn thời gian hơn. Số partition vì vậy cần dựa trên lưu lượng thực tế, mục tiêu xử lý và năng lực đã đo của cụm.

Trong module KAFKA, người học cần hiểu topic, partition, offset, producer, consumer group, replication và KRaft để triển khai event streaming bằng Java/Spring Kafka, xử lý retry, ordering và giao dịch, tích hợp Kafka Connect/Streams, rồi giám sát, tối ưu và phục hồi cụm. Ước lượng partition là một quyết định nền tảng kết nối các khái niệm đó với năng lực vận hành.

Không có một con số partition đúng cho mọi topic. Cách đáng tin cậy là đo năng lực của một partition trong cấu hình gần production, tính nhu cầu ghi và đọc, kiểm tra mức song song, sau đó đối chiếu dung lượng lưu trữ và giới hạn broker.

## 1. Những dữ liệu cần thu thập

Trước khi tính toán, hãy mô tả workload thay vì chỉ hỏi “topic cần bao nhiêu partition?”. Tối thiểu cần có các thông tin sau:

| Dữ liệu | Cần xác định | Vì sao quan trọng |
|---|---|---|
| Tốc độ ghi | Record/giây và byte/giây ở mức trung bình, đỉnh và burst | Producer có thể bị giới hạn bởi số record hoặc tổng byte |
| Kích thước record | Kích thước trung bình, p95/p99 và độ biến động | Record lớn ảnh hưởng batch, network, disk và thời gian xử lý |
| Mẫu tải | Đỉnh kéo dài bao lâu, có tăng theo giờ/ngày/mùa hay không | Đỉnh ngắn và tải cao liên tục cần cách dự phòng khác nhau |
| Năng lực partition | Throughput ghi/đọc đo được ở độ trễ mục tiêu | Đây là cơ sở để tính số partition thay vì dùng con số ước đoán |
| Consumer | Throughput xử lý của một consumer khi được gán một partition | Xác định số partition cần cho mức song song và SLA |
| Thời gian lưu | Retention theo thời gian/dung lượng và tốc độ dữ liệu trung bình | Xác định dung lượng log và replica |
| Key và phân bố | Số lượng key, tần suất từng key, độ lệch tải | Nhiều partition không giải quyết được một key quá nóng |
| Độ bền dữ liệu | Replication factor, `acks`, `min.insync.replicas` | Replication ảnh hưởng network, disk và năng lực ghi |
| Cụm broker | Số broker, CPU, RAM, disk, network và mức sử dụng hiện tại | Partition/replica phải vừa với tài nguyên và mục tiêu phục hồi |

Hãy dùng cả record/giây và MB/giây. Một topic có thể có rất nhiều record nhỏ nhưng ít byte, hoặc ít record rất lớn. Chỉ đo một trong hai có thể dẫn tới ước lượng sai.

## 2. Đo năng lực của một partition

### 2.1 Không dùng một con số throughput chung cho mọi hệ thống

Throughput của partition phụ thuộc kích thước record, số record mỗi batch, compression, số producer, số consumer, cấu hình broker, loại disk, network, replication factor, `acks` và mức cạnh tranh tài nguyên với các topic khác.

Vì vậy, hãy benchmark với workload gần thực tế. Một phép đo có ý nghĩa cần giữ các điều kiện quan trọng giống production:

- Kích thước record và phân bố kích thước tương tự dữ liệu thật.
- Key và cách phân bố key phản ánh mức độ lệch tải dự kiến.
- Producer dùng serializer, compression, batching và acknowledgement dự kiến.
- Topic có replication factor và cấu hình ISR tương tự môi trường chạy thật.
- Consumer thực hiện logic xử lý đại diện, bao gồm truy cập database hoặc dịch vụ ngoài nếu chúng nằm trên đường xử lý chính.
- Đo trong thời gian đủ dài để quan sát disk, network, page cache, GC và độ trễ khi tải ổn định.

Ghi lại throughput tối đa vẫn đáp ứng p95/p99 latency, tỷ lệ lỗi và consumer lag mục tiêu. Không nên lấy điểm throughput cao nhất trong một thử nghiệm ngắn làm năng lực vận hành an toàn.

Không chỉ benchmark một partition đơn lẻ rồi nhân kết quả lên toàn cụm. Hãy thử topic có nhiều partition được phân phối trên số broker dự kiến, vì broker, disk và network là tài nguyên dùng chung. Từ thử nghiệm đó, xác định throughput bền vững trung bình trên mỗi partition ở mức tải mà toàn cụm vẫn đáp ứng latency và khả năng phục hồi.

### 2.2 Năng lực ghi của một partition

Gọi:

- \(R_{in}\): tốc độ ghi đỉnh dự kiến của topic, tính bằng MB/s.
- \(W_p\): tốc độ ghi bền vững đo được trên một partition, tính bằng MB/s, với cấu hình replication và độ trễ mục tiêu.
- \(U_w\): tỷ lệ sử dụng mục tiêu của năng lực đo được, ví dụ 0,7 để giữ khoảng dự phòng.

Ước lượng partition theo throughput ghi:

\[
P_{write} = \left\lceil \frac{R_{in}}{W_p \times U_w} \right\rceil
\]

Nếu workload bị giới hạn theo số record thay vì byte, hãy thực hiện phép tính tương tự bằng record/giây:

\[
P_{write,records} = \left\lceil \frac{RecordsPerSecond}{RecordsPerSecondPerPartition \times U_w} \right\rceil
\]

Tính cả hai giới hạn và lấy kết quả lớn hơn. Ví dụ, record nhỏ có thể chạm giới hạn record/giây hoặc CPU trước khi đạt giới hạn byte/giây.

### 2.3 Năng lực đọc và xử lý của một partition

Gọi \(R_{consume}\) là throughput cần xử lý và \(C_p\) là throughput xử lý bền vững của một consumer được gán một partition. Số partition cần cho năng lực đọc được ước lượng:

\[
P_{read} = \left\lceil \frac{R_{consume}}{C_p \times U_c} \right\rceil
\]

Trong đó \(U_c\) là mức sử dụng mục tiêu của consumer. Nếu consumer xử lý một record tốn CPU hoặc gọi database, \(C_p\) cần được đo với logic đó; throughput fetch từ Kafka riêng lẻ sẽ không đại diện cho năng lực xử lý nghiệp vụ.

Với nhiều consumer group, hãy tính nhu cầu của từng group. Mỗi group có tiến độ và phân công partition riêng, nên group phân tích có thể cần số consumer khác group xử lý đơn hàng. Topic cần đáp ứng group có yêu cầu partition lớn nhất, trong khi tổng tài nguyên đọc phải tính cho tất cả group cùng hoạt động.

## 3. Tính partition theo mức song song của consumer

Trong một consumer group, một partition tại một thời điểm chỉ được gán cho một consumer. Một consumer có thể nhận nhiều partition, nhưng một partition không được chia cho nhiều consumer trong cùng group để xử lý song song đồng thời.

Do đó:

- Nếu muốn 12 consumer instance đều có ít nhất một partition đang hoạt động, topic cần tối thiểu 12 partition.
- Nếu topic có 8 partition nhưng group chạy 12 consumer, tối đa 8 consumer có thể nhận partition; các consumer còn lại sẽ rảnh đối với topic đó.
- Nếu topic có 24 partition và group chạy 6 consumer, mỗi consumer có thể nhận trung bình khoảng 4 partition, tùy chiến lược assignor và trạng thái cụm.

Số consumer không phải lúc nào cũng cần bằng số partition. Một consumer có thể xử lý nhiều partition nếu năng lực CPU, bộ nhớ và thời gian xử lý cho phép. Hãy chọn số consumer theo throughput thực đo và mục tiêu triển khai, sau đó đảm bảo số partition đủ để đạt mức song song mong muốn.

Gọi \(C_{target}\) là số consumer cần hoạt động đồng thời trong group. Khi mỗi consumer cần tối thiểu một partition:

\[
P_{parallel} \geq C_{target}
\]

Nếu một consumer instance có thể xử lý an toàn tối đa \(q\) partition, số instance cần thiết có thể ước lượng bằng:

\[
ConsumersNeeded = \left\lceil \frac{P}{q} \right\rceil
\]

Giá trị \(q\) không phải hằng số của Kafka. Nó phụ thuộc logic xử lý, độ trễ I/O, concurrency trong ứng dụng và cách Spring Kafka quản lý listener container.

### 3.1 Số partition giới hạn mức song song, không bảo đảm throughput

Tăng partition chỉ tạo thêm đơn vị có thể được phân công. Nó không tự làm database xử lý nhanh hơn, không loại bỏ hot key và không bảo đảm producer có thể tăng tốc. Nếu bottleneck nằm ở database, downstream API, CPU hoặc network, thêm partition có thể chỉ làm tăng số luồng cạnh tranh cùng tài nguyên.

Hãy benchmark end-to-end và kiểm tra consumer lag theo partition. Nếu một group đã có đủ consumer nhưng lag vẫn tăng, cần tìm nguyên nhân xử lý chậm hoặc phân bố key không đều trước khi quyết định tăng partition.

## 4. Kết hợp các nhu cầu để chọn số partition ban đầu

Ba giới hạn chính thường gặp là throughput ghi, throughput đọc và mức song song. Có thể xác định số partition cơ sở như sau:

\[
P_{base} = \max(P_{write}, P_{read}, P_{parallel})
\]

Nếu có nhiều consumer group, \(P_{read}\) là nhu cầu lớn nhất trong các group, nhưng cần kiểm tra tổng tải đọc đồng thời lên broker. Sau khi tính \(P_{base}\), hãy xem xét tốc độ tăng trưởng và khoảng dự phòng.

Có hai cách đưa dự phòng vào phép tính:

1. Dùng mức sử dụng mục tiêu \(U_w\), \(U_c\) thấp hơn 1 trong các công thức throughput.
2. Hoặc tính theo tải đỉnh hiện tại rồi nhân thêm hệ số tăng trưởng/dự phòng.

Không nên cộng dự phòng nhiều lần mà không có lý do. Hãy ghi rõ hệ số nào đã nằm trong throughput benchmark và hệ số nào dành cho tăng trưởng trong tương lai.

Số partition cuối cùng cần là số nguyên. Không có yêu cầu chung rằng số partition phải là lũy thừa của 2. Có thể chọn số thuận tiện cho kế hoạch consumer và phân bố replica, miễn là kết quả benchmark và vận hành đáp ứng yêu cầu.

## 5. Ví dụ tính toán cho topic orders

Giả sử hệ thống thương mại điện tử cần tạo topic `orders` với yêu cầu sau:

| Thông số | Giá trị giả định |
|---|---:|
| Lưu lượng ghi đỉnh | 80 MB/s |
| Throughput ghi đo được trên một partition | 8 MB/s |
| Mức sử dụng mục tiêu cho ghi | 70% |
| Throughput xử lý của một consumer/partition | 6 MB/s |
| Throughput đọc cần đạt | 60 MB/s |
| Số consumer mong muốn hoạt động đồng thời | 12 |
| Tăng trưởng dự kiến trong kỳ kế hoạch | 20% |

**Bước 1: Tính theo throughput ghi.**

\[
P_{write} = \left\lceil \frac{80}{8 \times 0.7} \right\rceil
= \lceil 14.29 \rceil = 15
\]

**Bước 2: Tính theo throughput đọc.** Giả sử benchmark cho thấy một consumer xử lý bền vững 6 MB/s với logic nghiệp vụ thực tế và mức sử dụng mục tiêu đã được phản ánh trong con số này:

\[
P_{read} = \left\lceil \frac{60}{6} \right\rceil = 10
\]

**Bước 3: Tính theo mức song song.** Muốn 12 consumer có thể nhận partition:

\[
P_{parallel} = 12
\]

**Bước 4: Chọn số partition cơ sở.**

\[
P_{base} = \max(15, 10, 12) = 15
\]

Mức sử dụng 70% ở bước ghi đã chừa năng lực cho biến động quanh tải đỉnh hiện tại. Hệ số 20% tiếp theo dành cho tăng trưởng dự báo trong kỳ kế hoạch.

**Bước 5: Dự phòng tăng trưởng 20%.**

\[
P_{planned} = \lceil 15 \times 1.2 \rceil = 18
\]

Với giả định này, 18 partition là điểm bắt đầu để benchmark lại trên cụm thật. Có thể chọn 18 hoặc một số gần đó theo kế hoạch consumer và replica. Đây chưa phải kết luận cuối cùng: cần kiểm tra lưu lượng key có lệch hay không, tài nguyên broker có đủ hay không và consumer có thực sự đạt throughput đo được khi chạy đồng thời.

Nếu throughput 8 MB/s/partition được đo ở cấu hình replication factor 1 nhưng production dùng replication factor 3, không được dùng nguyên số đó để kết luận. Hãy đo lại với replication, `acks`, ISR và số broker dự kiến vì leader/follower replication tiêu thụ network và disk trên cụm.

## 6. Kiểm tra dung lượng lưu trữ và replication

Số partition không trực tiếp quyết định tổng dung lượng dữ liệu, nhưng mỗi partition có log segment và replica riêng. Retention và replication có thể khiến cụm hết disk dù throughput vẫn đáp ứng.

Ước lượng dung lượng log cần cấp phát:

\[
Storage \approx R_{avg} \times RetentionSeconds \times CompressionRatio
\times ReplicationFactor
\]

Trong đó:

- \(R_{avg}\) là tốc độ dữ liệu trung bình trước nén, tính theo byte/giây.
- `RetentionSeconds` là thời gian lưu theo giây.
- `CompressionRatio` là tỷ lệ dung lượng sau nén so với trước nén, ví dụ 0,5 nghĩa là dữ liệu sau nén còn khoảng một nửa.
- `ReplicationFactor` là số bản sao của mỗi partition.

Dung lượng đĩa cần cấp phát phải lớn hơn kết quả trên để có chỗ cho segment đang ghi, index, log compaction, phục hồi replica, biến động lưu lượng và ngưỡng disk utilization. Nếu muốn giữ mức sử dụng đĩa tối đa \(U_d\), có thể ước lượng:

\[
ProvisionedDisk \geq \frac{Storage}{U_d}
\]

### 6.1 Ví dụ dung lượng retention

Giả sử lưu lượng trung bình là 30 MB/s, retention 7 ngày, compression ratio 0,5 và replication factor 3:

\[
RawBytes = 30 \times 604800 = 18,144,000\ MB
\]

Sau nén, một bản sao cần khoảng 9,072,000 MB, tương đương khoảng 9,07 TB theo đơn vị thập phân. Với replication factor 3, tổng dữ liệu replica khoảng 27,22 TB. Nếu mục tiêu disk utilization tối đa là 70%:

\[
ProvisionedDisk \geq \frac{27.22}{0.7} \approx 38.9\ TB
\]

Đây là ước lượng sơ bộ cho toàn cụm. Khi lập kế hoạch thực tế, cần cộng thêm overhead, dung lượng cho rebalance/replica recovery, phân bố dữ liệu không đều và dung lượng dự phòng khi broker bảo trì hoặc gặp sự cố. Dùng tốc độ trung bình cho retention; dùng tốc độ đỉnh cho throughput và khả năng chịu burst.

### 6.2 Replication làm tăng tài nguyên cụm

Với replication factor 3, mỗi partition có một leader và hai follower replica. Producer ghi vào leader; follower fetch dữ liệu để theo kịp leader. Replication tăng khả năng chịu lỗi nhưng cũng làm tăng lượng dữ liệu ghi trên disk và traffic nội bộ giữa broker.

Khi benchmark, hãy dùng cấu hình gần production, ví dụ replication factor 3 và `acks=all` nếu đó là yêu cầu độ bền. `min.insync.replicas` cần được đặt phù hợp với replication factor và mục tiêu chấp nhận lỗi. Số partition cần tính dựa trên throughput thực tế của cấu hình đó, không chỉ throughput ghi đơn giản vào một broker.

## 7. Đối chiếu với số broker và chi phí vận hành

Giả sử topic có \(P\) partition và replication factor \(RF\). Tổng số replica partition của topic xấp xỉ:

\[
ReplicaCount = P \times RF
\]

Nếu cụm có \(B\) broker và replica được phân phối tương đối đều, số replica partition trung bình trên mỗi broker xấp xỉ:

\[
ReplicasPerBroker \approx \frac{P \times RF}{B}
\]

Đây chỉ là phép chia trung bình. Kafka còn phải phân phối leader, follower, rack và zone theo cấu hình; không nên dùng con số trung bình để bỏ qua chênh lệch tải thực tế.

Ví dụ topic có 18 partition, replication factor 3 và cụm 6 broker:

- Tổng replica partition: \(18 \times 3 = 54\).
- Trung bình khoảng 9 replica partition trên mỗi broker.
- Leader của 18 partition được phân phối giữa các broker; một broker có thể giữ nhiều leader và follower của nhiều topic khác.

Một topic có vẻ nhỏ vẫn có thể góp phần tạo ra tổng số partition lớn nếu hệ thống có hàng trăm topic. Hãy tính tổng partition và replica của toàn cụm, không chỉ xem từng topic riêng lẻ.

Mỗi partition làm phát sinh metadata, log segment, index, file handle, hoạt động phục hồi và công việc theo dõi. Nhiều partition nhỏ có thể tạo chi phí đáng kể khi broker khởi động lại, di chuyển replica hoặc controller xử lý thay đổi metadata. Năng lực quản lý partition trên mỗi broker phụ thuộc phiên bản Kafka, tài nguyên, kích thước segment, workload và cách vận hành; không có một giới hạn cố định áp dụng cho mọi cụm.

Khi đánh giá, hãy kiểm tra:

- CPU và thời gian GC của broker/controller.
- Disk throughput, latency, dung lượng trống và tốc độ phục hồi replica.
- Network ingress/egress và traffic replication.
- Số partition/replica và số leader trên từng broker.
- Số file mở, số log segment và thời gian khởi động/recovery.
- Thời gian rebalance và ảnh hưởng đến consumer lag.

## 8. Phân bố key có thể làm sai lệch phép tính

Các công thức throughput thường giả định tải được phân phối tương đối đều. Trong thực tế, producer thường chọn partition theo key. Nếu một key chiếm phần lớn traffic, partition chứa key đó có thể nóng dù tổng số partition lớn.

Ví dụ, topic có 24 partition nhưng 40% record đều mang key `tenant-001`. Những record này tiếp tục đi vào một partition theo quy tắc partitioner. Thêm partition có thể cải thiện phân phối các key khác nhưng không tự chia một key thành nhiều partition mà vẫn giữ thứ tự của key đó.

Trước khi quyết định số partition:

1. Đo số lượng key khác nhau và tần suất theo key.
2. Tính tỷ lệ traffic của các key lớn nhất.
3. Kiểm tra byte/giây và record/giây theo từng partition trong thử nghiệm.
4. Xác định key nóng có thể chia nhỏ hay không về mặt nghiệp vụ.
5. Nếu shard một key, xác nhận ứng dụng có thể chấp nhận mất thứ tự tổng thể giữa các shard.

Nếu yêu cầu ordering bắt buộc cho một thực thể nóng, giới hạn throughput của partition chứa thực thể đó là một giới hạn kiến trúc. Cần tối ưu xử lý, payload, batching, downstream hoặc thay đổi cách phân chia nghiệp vụ thay vì chỉ tăng số partition.

## 9. Quy trình benchmark và hiệu chỉnh

Ước lượng bằng công thức giúp chọn cấu hình ban đầu. Trước khi đưa vào production, hãy kiểm chứng bằng thử nghiệm có kiểm soát:

1. **Tạo topic thử nghiệm** với partition count và replication factor dự kiến.
2. **Sinh dữ liệu thực tế** về kích thước record, key distribution, tốc độ đỉnh và burst.
3. **Đo producer**: records/sec, MB/sec, p95/p99 produce latency, error/retry rate và CPU client.
4. **Đo broker**: CPU, disk latency/throughput, network, request queue, ISR và under-replicated partitions.
5. **Đo consumer**: throughput xử lý, lag theo partition, thời gian xử lý record, rebalance và lỗi downstream.
6. **Tăng tải từng bước** để xác định điểm mà latency hoặc lag bắt đầu tăng nhanh.
7. **Thử lỗi và phục hồi**: dừng một broker, quan sát leader election, replica catch-up, consumer rebalance và thời gian trở lại ổn định.
8. **Điều chỉnh partition count** hoặc cấu hình producer/consumer rồi chạy lại cùng một workload để so sánh.

Không thay đổi đồng thời quá nhiều biến trong một lượt benchmark. Nếu cùng lúc đổi partition count, compression, batch size và consumer concurrency, sẽ khó xác định yếu tố nào tạo ra khác biệt.

### 9.1 Các chỉ số cần quan sát

| Nhóm | Chỉ số | Dấu hiệu cần chú ý |
|---|---|---|
| Producer | Record/byte in rate, produce latency, retry/error | Latency tăng hoặc retry kéo dài khi tải đạt ngưỡng |
| Partition | Bytes/records in theo partition | Một vài partition nhận tải vượt trội |
| Consumer | Lag và tốc độ xử lý theo partition | Lag tăng liên tục dù consumer đã ổn định |
| Broker | CPU, disk latency, network, request queue | Một tài nguyên chạm trần trước các tài nguyên khác |
| Replication | ISR, under-replicated partitions, replica lag | Replica không theo kịp hoặc ISR co lại |
| Điều phối | Rebalance duration, partition assignment | Rebalance kéo dài hoặc gây gián đoạn xử lý |

Với Kafka, tổng consumer lag của topic có thể che giấu một partition bị nghẽn. Luôn xem lag theo partition và đối chiếu với tốc độ ghi/đọc, key distribution và consumer đang được gán partition đó.

## 10. Tăng hoặc giảm số partition sau khi topic đã chạy

Tăng partition có thể giúp tăng mức song song và dung lượng phân phối, nhưng cần cân nhắc tác động tới key-to-partition mapping. Với partitioner dựa trên hash và số partition, một số key có thể được định tuyến sang partition khác sau khi tăng số lượng. Record cũ vẫn nằm ở partition cũ; record mới có thể đi vào partition mới. Vì vậy, Kafka không bảo đảm một thứ tự xuyên suốt cho cùng key qua thời điểm thay đổi topology.

Kafka không cung cấp thao tác giảm số partition của topic hiện có theo cách thông thường. Nếu tạo quá nhiều partition, hướng xử lý thường là tạo topic mới với số partition phù hợp, chuyển dữ liệu/producer/consumer theo kế hoạch và ngừng topic cũ sau khi đối soát.

Trước khi tăng partition, hãy xem xét:

- Có thực sự thiếu partition hay bottleneck nằm ở downstream, CPU, disk hoặc network?
- Consumer group có thể tận dụng thêm partition hay số consumer đã đủ?
- Key nào bị ảnh hưởng khi partitioner ánh xạ lại?
- Có yêu cầu giữ ordering xuyên suốt quá trình thay đổi không?
- Broker còn đủ tài nguyên cho replica, file, metadata và recovery không?

Đối với topic cần ordering nghiêm ngặt theo key, có thể cần tạo topic mới và chuyển đổi theo mốc dữ liệu thay vì tăng partition trực tiếp.

## 11. Các sai lầm thường gặp khi sizing

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ dựa vào số consumer hiện tại | Có thể thiếu partition khi cần tăng worker hoặc tăng throughput | Tính thêm throughput và tăng trưởng dự kiến |
| Dùng throughput tối đa trong benchmark ngắn | Production chạm ngưỡng latency hoặc lag khi tải kéo dài | Dùng năng lực bền vững tại p95/p99 mục tiêu và có headroom |
| Chỉ đo MB/s, bỏ qua records/s | CPU và overhead mỗi record có thể trở thành bottleneck | Tính cả byte/giây và record/giây |
| Benchmark không có replication | Ước lượng cao hơn năng lực cụm production | Benchmark với RF, `acks` và ISR dự kiến |
| Dùng peak để tính retention storage | Có thể cấp phát quá lớn hoặc hiểu sai nhu cầu lưu | Dùng average ingress cho retention, peak cho throughput |
| Bỏ qua key skew | Một partition nóng dù tổng partition đủ lớn | Đo phân bố key và traffic từng partition |
| Tăng partition như cách xử lý mọi lag | Tăng chi phí mà không giải quyết bottleneck downstream | Xác định nguyên nhân lag trước khi thay đổi topology |
| Quên tính tổng partition của toàn cụm | Broker chịu tải metadata/replica cao hơn dự kiến | Tổng hợp partition và replica trên tất cả topic |

## Kết luận

Ước lượng partition cần kết hợp ba nhu cầu: throughput ghi, throughput đọc và mức song song của consumer. Hãy đo năng lực bền vững của một partition trong cấu hình gần production, tính số partition theo byte/giây và record/giây, rồi lấy mức lớn nhất cùng với nhu cầu consumer. Sau đó kiểm tra retention, replication, phân bố key, số broker và chi phí quản lý partition.

Với hệ thống KAFKA, số partition là quyết định ảnh hưởng lâu dài đến ordering, consumer group, dung lượng và khả năng phục hồi. Bắt đầu bằng một phép tính có giả định rõ ràng, benchmark end-to-end, quan sát lag theo partition và dành khoảng tăng trưởng hợp lý. Khi lưu lượng hoặc kiến trúc thay đổi, hãy đánh giá lại bằng số liệu vận hành và lập kế hoạch chuyển đổi cẩn thận để giữ đúng yêu cầu nghiệp vụ.
