# Capacity planning theo peak traffic

Capacity planning cho Spring Kafka là quá trình xác định producer, broker, consumer, mạng, đĩa và các dịch vụ phụ trợ cần bao nhiêu năng lực để xử lý lưu lượng dự kiến trong khi vẫn đáp ứng latency, độ bền dữ liệu và khả năng phục hồi. Khi lập kế hoạch theo peak traffic, cần dùng tải đỉnh có ý nghĩa vận hành thay vì chỉ lấy lưu lượng trung bình. Một hệ thống xử lý tốt 5.000 records/s trong phần lớn thời gian vẫn có thể mất ổn định khi một chiến dịch tạo ra 30.000 records/s trong 15 phút.

Peak traffic còn có nhiều hình dạng. Một đợt tăng tải có thể kéo dài vài giây, vài phút hoặc vài giờ; có thể tăng đều theo mùa, xuất hiện đột ngột do một sự kiện, hoặc tập trung vào một vài partition vì key phân bố lệch. Mỗi dạng tạo áp lực khác nhau lên batching, buffer, consumer lag, broker disk và replication. Vì vậy, capacity planning phải mô hình hóa cả tốc độ, thời lượng, kích thước bản ghi, phân bố key và tình huống lỗi.

## 1. Xác định mục tiêu và phạm vi tải

Trước khi tính số partition hoặc số broker, hãy xác định hệ thống cần phục vụ điều gì. Các mục tiêu cần được diễn đạt bằng con số và phạm vi đo cụ thể:

- **Peak throughput:** số records/s và bytes/s cần xử lý ở các khoảng đo như 1 giây, 1 phút và 5 phút.
- **Duration:** thời gian hệ thống phải duy trì peak, ví dụ 30 giây, 15 phút hoặc 4 giờ.
- **Latency objective:** p95/p99 end-to-end latency tối đa trong thời gian peak.
- **Error objective:** tỷ lệ gửi thất bại, timeout hoặc xử lý lỗi được chấp nhận.
- **Durability:** yêu cầu về replication, `acks`, `min.insync.replicas` và khả năng chịu lỗi broker.
- **Recovery objective:** thời gian tối đa để consumer bắt kịp backlog sau peak hoặc sau sự cố.
- **Growth horizon:** mức tăng trưởng dự kiến trong khoảng thời gian thiết kế, chẳng hạn 6 hoặc 12 tháng.

Phải thống nhất ranh giới của throughput. Producer gửi thành công, broker ghi nhận, consumer fetch và nghiệp vụ hoàn tất là các mốc khác nhau. Nếu yêu cầu là mọi đơn hàng phải được ghi vào hệ thống đích trong vòng hai giây, capacity cần đáp ứng toàn bộ luồng đến lúc nghiệp vụ hoàn tất. Chỉ đo tốc độ producer gửi vào Kafka sẽ không chứng minh được yêu cầu đó.

Một bảng workload ban đầu có thể gồm:

| Thuộc tính | Ví dụ | Tác động đến thiết kế |
|---|---|---|
| Tốc độ bình thường | 8.000 records/s | Xác định tải nền và tốc độ tăng backlog ngoài peak |
| Peak ngắn hạn | 30.000 records/s trong 15 phút | Xác định năng lực xử lý khi tải cao |
| Peak kéo dài | 18.000 records/s trong 3 giờ | Ảnh hưởng lớn đến consumer capacity và tài nguyên liên tục |
| Kích thước record | Trung bình 1,5 KB, p99 8 KB | Ảnh hưởng bytes/s, batch, network và storage |
| Key distribution | 20% bản ghi thuộc một key nóng | Có thể tạo hot partition dù tổng số partition lớn |
| Retention | 3 ngày | Xác định dung lượng log cần giữ |
| Replication factor | 3 | Tăng dung lượng lưu trữ và replication traffic |
| SLO | p99 end-to-end dưới 1 giây | Giới hạn thời gian chờ và mức sử dụng tài nguyên phù hợp |

Các con số trong bảng chỉ là ví dụ. Dữ liệu production hoặc benchmark đại diện phải thay thế chúng trước khi chốt cấu hình.

## 2. Đo peak traffic theo đúng hình dạng

### 2.1. Thu thập dữ liệu theo nhiều cửa sổ thời gian

Một giá trị trung bình 5 phút có thể che khuất một burst 2 giây. Ngược lại, lấy một mẫu cực đại đơn lẻ có thể dẫn đến thiết kế quá mức nếu mẫu đó là lỗi đo hoặc một đợt bất thường không cần hệ thống xử lý ngay. Hãy lưu chuỗi thời gian với nhiều độ phân giải và xác định cửa sổ phù hợp với SLO:

- Cửa sổ 1 giây hoặc vài giây để nhìn burst rất ngắn và khả năng hấp thụ của producer buffer.
- Cửa sổ 1 phút để nhìn peak ngắn và sự thay đổi consumer lag.
- Cửa sổ 5 hoặc 15 phút để nhìn tải peak kéo dài.
- Cửa sổ theo giờ/ngày để nhận biết mùa vụ, lịch chiến dịch và xu hướng tăng trưởng.

Không nên chỉ lấy trung bình theo ngày để tính throughput. Cũng không nên lấy một giá trị max duy nhất làm đại diện cho mọi mục tiêu. Hãy lưu peak theo từng cửa sổ, percentile của các cửa sổ và thời lượng mà tải vượt các ngưỡng quan trọng.

### 2.2. Phân loại các dạng peak

**Sustained peak** là tải cao duy trì đủ lâu để broker, consumer và hệ thống phụ trợ phải xử lý liên tục. Đây thường là yếu tố quyết định CPU, network, disk throughput và số consumer cần thiết.

**Short burst** là tải tăng mạnh trong thời gian ngắn. Producer buffer, batching, queue và khả năng drain backlog có thể hấp thụ một phần burst, miễn là hệ thống có đủ bộ nhớ và thời gian phục hồi. Buffer chỉ trì hoãn việc xử lý; nó không thay thế năng lực dài hạn.

**Ramp-up peak** là tải tăng dần, chẳng hạn lưu lượng tăng trong giờ mở bán. Hệ thống cần có khả năng scale trước khi đạt đỉnh. Nếu autoscaling phản ứng sau khi lag đã tăng cao, consumer có thể không kịp mở rộng trước khi SLO bị vi phạm.

**Replay hoặc reprocessing peak** xuất hiện khi ứng dụng đọc lại dữ liệu sau sự cố, chạy backfill hoặc phát lại sự kiện. Lưu lượng đọc và ghi có thể chồng lên tải người dùng bình thường. Capacity planning cần tính cả trường hợp này nếu replay là một hoạt động vận hành được hỗ trợ.

**Retry amplification** xảy ra khi dịch vụ downstream chậm hoặc lỗi, khiến consumer retry, producer gửi lại hoặc nhiều thành phần cùng tạo thêm request. Tải phát sinh có thể lớn hơn lưu lượng nghiệp vụ ban đầu. Cần mô hình hóa retry policy, backoff, giới hạn số lần retry và dead-letter topic.

**Skewed peak** xảy ra khi tổng lưu lượng tăng đồng thời một vài key hoặc partition nhận phần lớn dữ liệu. Tổng throughput của cluster có thể còn dư nhưng một consumer xử lý partition nóng đã bão hòa.

### 2.3. Dùng dữ liệu production và benchmark

Khi thu thập dữ liệu, nên đo records/s và bytes/s ở producer, broker, consumer và nghiệp vụ; kích thước record trung bình cùng p95/p99; số lượng bản ghi theo từng partition; consumer lag; thời gian xử lý listener; tỷ lệ retry; và tài nguyên CPU, memory, network, disk.

Nếu production chưa từng có peak dự kiến, hãy tạo tải bằng benchmark. Payload, key distribution, compression, TLS, replication, số producer và logic xử lý phải gần với production. Một bài test chỉ gửi record nhỏ vào broker đơn lẻ thường đánh giá thấp năng lực cần thiết cho hệ thống có replication và consumer ghi cơ sở dữ liệu.

## 3. Tính tốc độ tải thiết kế

### 3.1. Từ peak quan sát đến peak thiết kế

Gọi `R_peak` là tốc độ cao nhất đại diện được quan sát trong cửa sổ thời gian đã chọn. Nếu dự báo lưu lượng tăng `g` trong giai đoạn thiết kế, tốc độ tải thiết kế là:

\[
R_{design} = R_{peak} \times (1 + g)
\]

Ví dụ, peak quan sát là 30.000 records/s và dự báo tăng trưởng 20% trong 12 tháng:

\[
R_{design} = 30.000 \times 1,2 = 36.000\ records/s
\]

Đây là tải dự báo cần phục vụ. Tiếp theo phải thêm headroom hoặc chọn giới hạn sử dụng tài nguyên an toàn. Không nên vừa nhân headroom vào tải thiết kế, vừa chia cho một ngưỡng utilization mà không hiểu hai phần đang đại diện cho cùng một khoản dự phòng; làm vậy có thể dự phòng hai lần ngoài ý muốn.

Có hai cách diễn đạt phổ biến:

- **Headroom factor:** `C_required = R_design × H`, trong đó `H` có thể là 1,2 hoặc 1,3 theo mức dự phòng đã chọn.
- **Target utilization:** `C_required = R_design / U_target`, trong đó `U_target` là mức sử dụng mục tiêu, ví dụ 0,7.

Hai cách này đều nhằm giữ tài nguyên còn dư địa. Hãy chọn cách phù hợp với mô hình vận hành và dùng nhất quán trong toàn bộ phép tính. Giá trị dự phòng cần dựa trên biến động tải, khả năng scale, yêu cầu N-1 và kết quả benchmark; không có một tỷ lệ đúng cho mọi cluster.

### 3.2. Quy đổi records/s thành bytes/s

Thông lượng byte ở mức logic có thể ước lượng bằng:

\[
B_{logical} = R_{design} \times S_{avg}
\]

Trong đó `S_avg` là kích thước record trung bình tính bằng byte. Dùng thêm kích thước p95/p99 và kích thước record lớn nhất hợp lệ để kiểm tra các giới hạn batch, request và fetch. Nếu payload có kích thước biến động lớn, chỉ dùng trung bình có thể đánh giá thiếu rủi ro ở các batch lớn.

Ví dụ với 30.000 records/s và kích thước trung bình 1.500 byte:

\[
30.000 \times 1.500 = 45.000.000\ bytes/s \approx 45\ MB/s
\]

Đây là tốc độ dữ liệu logic trước khi xét compression và overhead giao thức. Producer compression có thể làm số byte truyền và lưu trên log thấp hơn, nhưng tỷ lệ nén phụ thuộc dữ liệu và cách gom batch. Hãy benchmark bằng payload thật để lấy compression ratio thay vì giả định mọi topic đều giảm một tỷ lệ cố định.

### 3.3. Tính cả tải phát sinh

Lưu lượng nghiệp vụ ban đầu chưa chắc là toàn bộ tải Kafka phải xử lý. Hãy cộng hoặc mô hình hóa riêng các nguồn sau:

- Retry và gửi lại sau timeout.
- Sự kiện được fan-out sang nhiều topic hoặc nhiều consumer group.
- Dead-letter topic và luồng phục hồi.
- Backfill, replay, reprocessing và migration.
- Consumer fetch lặp lại khi xử lý thất bại hoặc offset được reset.
- Replication giữa broker.

Không cộng mọi thành phần vào cùng một con số nếu chúng đo các luồng khác nhau. Ví dụ, replication làm tăng network và disk traffic của broker, nhưng không có nghĩa producer nhận thêm số record logic. Hãy giữ riêng bảng tải producer, broker, consumer và dịch vụ downstream để tránh đếm trùng.

## 4. Tính năng lực consumer và số partition

Consumer group là nơi nhiều ứng dụng thường gặp giới hạn khi peak traffic xuất hiện. Một group chỉ có thể xử lý song song tối đa theo số partition được gán cho group đó. Tăng số pod hoặc `concurrency` vượt quá số partition không tạo thêm consumer hữu ích cho topic đó.

### 4.1. Đo năng lực xử lý của một consumer

Hãy benchmark một consumer instance trong điều kiện gần production, bao gồm deserialize, validation, gọi dịch vụ, ghi database và commit offset. Ghi nhận tốc độ records/s mà instance duy trì được trong khi vẫn đáp ứng p95/p99 latency và không làm hệ thống downstream bão hòa.

Gọi `r_consumer` là năng lực bền vững của một consumer trong điều kiện đó. Số consumer hoạt động cần thiết có thể ước lượng:

\[
N_{consumer} = \left\lceil \frac{R_{required}}{r_{consumer}} \right\rceil
\]

`R_required` phải bao gồm mức headroom đã chọn. Nếu cần chịu được một consumer instance ngừng hoạt động, phải bảo đảm số consumer còn lại vẫn đủ năng lực:

\[
(N_{consumer} - 1) \times r_{consumer} \ge R_{required}
\]

Ví dụ, nếu tải cần phục vụ là 39.000 records/s và mỗi consumer duy trì 4.000 records/s, cần ít nhất 10 consumer còn hoạt động. Để chịu được một consumer mất khả năng phục vụ, nên bố trí ít nhất 11 consumer instance có thể hoạt động trước sự cố.

Đây là phép tính ban đầu. Throughput thực tế không phải lúc nào cũng tăng tuyến tính theo số consumer vì broker, partition, database connection pool hoặc dịch vụ downstream có thể trở thành giới hạn chung. Phải benchmark ở quy mô dự kiến và kiểm tra trường hợp một instance bị mất.

### 4.2. Chọn số partition

Số partition cần đủ để hỗ trợ số consumer hoạt động song song mong muốn. Một cách ước lượng ban đầu là:

\[
P \ge N_{consumer,peak}
\]

Trong đó `P` là số partition của topic và `N_consumer,peak` là số consumer muốn có thể hoạt động đồng thời trong group. Có thể chọn thêm một mức dự phòng cho tăng trưởng hoặc thay đổi topology, nhưng không nên tăng partition tùy tiện.

Số partition cuối cùng còn phụ thuộc vào:

- **Ordering:** Kafka giữ thứ tự trong một partition. Các bản ghi cùng key thường được đưa vào cùng partition với partitioner mặc định.
- **Key skew:** một key quá nóng có thể làm partition chứa key đó quá tải dù còn nhiều consumer nhàn rỗi.
- **Broker capacity:** nhiều partition tăng metadata, file segment, chi phí leader/replica và công việc quản lý.
- **Consumer assignment:** số partition được gán cho mỗi consumer và cách phân bố tải phải được kiểm tra bằng benchmark.
- **Thay đổi partition count:** tăng partition có thể thay đổi cách key được ánh xạ vào partition cho các record mới, ảnh hưởng giả định về ordering hoặc xử lý theo key.

Nếu ứng dụng cần thứ tự toàn cục cho toàn bộ topic, không thể đơn giản tăng partition để có thêm consumer song song mà vẫn giữ cùng ngữ nghĩa thứ tự. Cần làm rõ yêu cầu ordering trước khi quyết định partition count.

### 4.3. Tính năng lực xử lý backlog

Trong peak, nếu tốc độ sản xuất lớn hơn tốc độ consumer hoàn tất, backlog tăng. Với tốc độ tương đối ổn định:

\[
Backlog = (R_{in} - R_{out}) \times T
\]

`R_in` là tốc độ bản ghi đi vào, `R_out` là tốc độ xử lý hoàn tất và `T` là thời lượng chênh lệch tính bằng giây. Công thức chỉ áp dụng khi `R_in > R_out` trong khoảng đo.

Sau peak, thời gian drain backlog được ước lượng bằng:

\[
T_{drain} = \frac{Backlog}{R_{recovery} - R_{normal}}
\]

`R_recovery` là tốc độ consumer có thể duy trì sau peak và `R_normal` là tốc độ đầu vào bình thường. Nếu `R_recovery` không lớn hơn `R_normal`, backlog không thể giảm trong trạng thái đó.

Ví dụ, peak kéo dài 15 phút với tốc độ đầu vào 30.000 records/s trong khi consumer chỉ xử lý 24.000 records/s:

\[
Backlog = (30.000 - 24.000) \times 900 = 5.400.000\ records
\]

Sau peak, producer trở về 8.000 records/s và consumer có thể xử lý 32.000 records/s. Năng lực giảm backlog ròng là 24.000 records/s, do đó thời gian bắt kịp xấp xỉ 225 giây, tức 3 phút 45 giây. Nếu downstream chỉ cho phép consumer chạy 10.000 records/s trong giai đoạn phục hồi, backlog sẽ giảm rất chậm hoặc không giảm; cần tính capacity của toàn bộ chuỗi xử lý.

Consumer lag theo offset là chỉ báo backlog hữu ích, nhưng không tự động biểu diễn thời gian chờ của từng sự kiện. Hãy theo dõi cả số record lag, tốc độ lag tăng/giảm và tuổi của bản ghi cũ nhất nếu hệ thống có phép đo này.

## 5. Tính dung lượng lưu trữ cho peak và retention

Kafka lưu log theo partition và duy trì các bản sao theo replication factor. Dung lượng cần thiết phụ thuộc vào tốc độ dữ liệu trong toàn bộ retention window, kích thước record sau compression, replication factor, overhead và mức sử dụng đĩa mục tiêu.

Ước lượng tổng dung lượng cluster:

\[
S_{cluster} = R_{avg} \times S_{avg} \times T_{retention} \times C \times RF \times (1 + O)
\]

Trong đó:

- `R_avg` là tốc độ record trung bình trong khoảng retention, không phải peak ngắn hạn.
- `S_avg` là kích thước record trung bình trước compression.
- `T_retention` là thời gian giữ dữ liệu tính bằng giây.
- `C` là tỷ lệ kích thước sau compression so với trước compression; ví dụ 0,5 nghĩa là còn khoảng một nửa.
- `RF` là replication factor.
- `O` là tỷ lệ dự phòng cho index, segment, metadata và biến động thực tế.

Nếu cluster chỉ được phép sử dụng tối đa `U_target` dung lượng đĩa, dung lượng vật lý cần cấp phát là:

\[
S_{provisioned} = \frac{S_{cluster}}{U_{target}}
\]

Ví dụ, topic có tốc độ trung bình 8.000 records/s, record trung bình 1.500 byte, compression ratio đo được là 0,5, retention 3 ngày, replication factor 3 và dự phòng overhead 20%:

\[
8.000 \times 1.500 = 12.000.000\ bytes/s = 12\ MB/s
\]

Dữ liệu logic trong một ngày xấp xỉ 1.036,8 GB trước compression. Sau compression còn khoảng 518,4 GB/ngày. Trong 3 ngày là khoảng 1,555 TB cho một bản sao; nhân replication factor 3 và overhead 20% cho tổng dung lượng cluster khoảng 5,60 TB. Nếu đặt mức sử dụng đĩa mục tiêu 70%, tổng dung lượng vật lý cần cấp phát xấp xỉ 8,0 TB.

Ví dụ này dùng tốc độ trung bình trong retention window. Không nhân peak 30.000 records/s với toàn bộ 3 ngày nếu peak chỉ kéo dài 15 phút; làm như vậy sẽ phóng đại dung lượng. Ngược lại, nếu peak kéo dài nhiều giờ mỗi ngày, cần đưa phần thời gian đó vào tốc độ trung bình có trọng số. Với topic compacted, tombstone, retention theo byte hoặc dữ liệu có kích thước biến động, cần kiểm tra dung lượng thực tế trên broker thay vì chỉ dựa vào công thức đơn giản.

Khi phân bổ dung lượng, kiểm tra từng broker và từng volume. Tổng dung lượng toàn cluster có thể đủ nhưng một broker đầy đĩa do leader/replica phân bố không đều. Cần tính thêm dung lượng trống cho segment roll, recovery, reassignment và hoạt động bảo trì.

## 6. Tính network và năng lực broker

Broker xử lý producer request, ghi log, phục vụ consumer fetch và đồng bộ replica. Capacity planning cần đánh giá riêng network ingress, network egress, disk throughput, IOPS, CPU, memory/page cache và replication traffic.

### 6.1. Network ingress và egress

Network ingress từ producer phụ thuộc bytes/s sau serialization và compression. Egress phục vụ consumer phụ thuộc số consumer group đọc topic, tốc độ fetch và việc consumer có đọc toàn bộ dữ liệu hay chỉ một phần. Một topic được năm consumer group độc lập đọc toàn bộ có thể tạo lượng egress lớn hơn nhiều so với một group.

Replication factor lớn hơn 1 làm phát sinh inter-broker traffic để follower nhận dữ liệu từ leader. Với replication factor 3, mỗi record logic có một leader replica và hai follower replica. Có thể dùng số bản sao bổ sung để ước lượng sơ bộ replication traffic, nhưng network thực tế phụ thuộc cách phân bố broker, batch fetch, compression, leader placement và topology mạng.

Không nên chỉ cộng tổng bytes/s toàn cluster rồi chia đều cho số broker. Leader partition có thể phân bố không đều; một broker có thể nhận nhiều producer write và đồng thời phục vụ nhiều consumer fetch. Hãy ước lượng theo broker và xác minh bằng metric bytes in/out trên từng node.

### 6.2. Disk và page cache

Kafka ghi log tuần tự và tận dụng page cache của hệ điều hành. Throughput ghi đĩa không phải yếu tố duy nhất; cần xem disk latency, khả năng flush, hoạt động đọc, page cache hit và áp lực bộ nhớ. Consumer fetch thường đọc dữ liệu đã có trong page cache, nhưng workload đọc lại lớn hoặc working set vượt bộ nhớ có thể làm tăng disk read.

Khi kiểm tra broker disk, hãy phân biệt:

- Dung lượng lưu trữ cần cho retention.
- Throughput ghi khi peak xảy ra.
- Throughput đọc khi consumer group fetch dữ liệu.
- IOPS và latency trong tình huống segment roll, recovery hoặc reassignment.
- Dung lượng dự phòng khi một broker hoặc volume không khả dụng.

Đĩa đủ dung lượng vẫn có thể không đáp ứng peak nếu tốc độ ghi/đọc hoặc latency không đạt yêu cầu.

### 6.3. CPU và memory

CPU broker được dùng cho request handling, TLS, compression/decompression, checksum, replication và tác vụ nền. CPU producer/consumer còn chịu ảnh hưởng bởi serialization, deserialization, xử lý nghiệp vụ và garbage collection. Một cấu hình compression giảm network nhưng có thể tăng CPU; cần đo cả hai phía.

Memory cần đủ cho heap ứng dụng, buffer producer, fetch buffer, metadata và page cache của hệ điều hành. Không dành toàn bộ RAM cho JVM heap nếu broker cần page cache. Khi consumer concurrency tăng, số lượng buffer, request và kết nối cũng có thể tăng.

### 6.4. Replication và durability

`replication.factor`, `min.insync.replicas` và producer `acks` ảnh hưởng cả độ bền lẫn năng lực ghi. Với `acks=all`, leader chờ các replica thuộc ISR đáp ứng điều kiện xác nhận. Khi follower chậm hoặc ISR giảm, producer latency có thể tăng; nếu số replica trong ISR thấp hơn `min.insync.replicas`, ghi có thể bị từ chối.

Capacity cần đủ cho replication trong peak và đủ headroom khi một broker mất khả năng phục vụ. Không lập kế hoạch dựa trên throughput đo được khi tắt replication nếu production yêu cầu RF=3. Việc giảm `acks` hoặc `min.insync.replicas` để đạt một con số throughput cao hơn phải được đánh giá cùng rủi ro mất dữ liệu.

## 7. Thiết kế headroom và khả năng chịu lỗi

Peak traffic thường trùng với thời điểm doanh nghiệp ít chấp nhận gián đoạn. Vì vậy, cluster phải có năng lực dự phòng khi một broker, consumer instance, availability zone hoặc dịch vụ phụ trợ gặp sự cố.

### 7.1. N-1 capacity

N-1 planning kiểm tra xem hệ thống còn đáp ứng tải mục tiêu khi mất một thành phần hay không. Với consumer, tính tổng năng lực của số instance còn lại sau khi một instance dừng. Với broker, kiểm tra leader reassignment, replica availability, network và disk trên các broker còn lại.

Ví dụ, nếu 12 consumer instance mỗi instance duy trì 4.000 records/s, tổng năng lực danh nghĩa là 48.000 records/s. Khi một instance dừng, còn 44.000 records/s. Nếu yêu cầu capacity có headroom là 39.000 records/s thì nhóm consumer vẫn đủ năng lực trong mô hình này, miễn là partition assignment và downstream chịu được tải mới.

N-1 không chỉ là phép tính tổng. Khi một broker mất, leader của partition được chuyển sang broker khác; broker còn lại có thể phải phục vụ thêm network egress, ghi dữ liệu và replica fetch. Cần thử nghiệm tình huống broker restart hoặc mất node để xác nhận phân bố tải sau failover.

### 7.2. Headroom theo loại tài nguyên

Không nên dùng một ngưỡng CPU duy nhất để đại diện cho toàn bộ capacity. Broker có thể còn CPU nhưng network đã bão hòa; consumer có thể còn CPU nhưng database connection pool đã hết. Xác định headroom riêng cho:

- CPU và thời gian xử lý request.
- Network ingress, egress và inter-broker traffic.
- Disk capacity, disk throughput và disk latency.
- JVM heap, garbage collection và page cache.
- Consumer concurrency, partition assignment và database connections.
- Quota, số kết nối, giới hạn request và giới hạn dịch vụ cloud.

Ngưỡng cảnh báo và ngưỡng scale phải dựa trên baseline, benchmark và SLO. Một tài nguyên chạy ở 80% có thể ổn định với workload đều, nhưng không còn đủ chỗ cho burst hoặc failover. Tài nguyên chạy ở 50% vẫn có thể gây latency cao nếu một partition hoặc thread cụ thể đã bão hòa.

### 7.3. Autoscaling và thời gian phản ứng

Autoscaling consumer theo lag có thể hữu ích khi peak tăng dần, nhưng cần tính thời gian phát hiện, khởi động pod, tạo consumer, join group và rebalance. Nếu peak chỉ kéo dài vài giây, autoscaling có thể phản ứng quá muộn; cần capacity dự phòng sẵn hoặc cơ chế buffer phù hợp.

Consumer scaling cũng bị giới hạn bởi số partition. Khi số consumer đạt số partition được gán, thêm pod không tăng khả năng xử lý topic đó. Nếu phải tăng partition, hãy xem xét ordering, key mapping và tác động vận hành trước khi thực hiện.

Broker autoscaling thường phức tạp hơn vì thêm broker không tự động phân bố lại partition và replica. Cần có quy trình reassignment, kiểm tra disk/network và giám sát replication trong lúc di chuyển dữ liệu.

## 8. Liên hệ capacity planning với cấu hình Spring Kafka

Spring Kafka cung cấp cấu hình producer, consumer và listener container để điều chỉnh batching, fetch, concurrency và hành vi poll. Các giá trị phải được chọn dựa trên benchmark; chúng không thay thế việc cấp đủ partition, broker và năng lực hệ thống phụ trợ.

Ví dụ cấu hình minh họa trong Spring Boot:

```yaml
spring:
  kafka:
    producer:
      acks: all
      batch-size: 65536
      buffer-memory: 67108864
      compression-type: lz4
      properties:
        linger.ms: 5
    consumer:
      enable-auto-commit: false
      max-poll-records: 500
      fetch-min-size: 65536
      fetch-max-wait: 50ms
    listener:
      concurrency: 12
```

Các cấu hình trên có ý nghĩa sau:

- `batch-size` giới hạn kích thước batch producer theo byte. Batch lớn có thể giảm số request nhưng cần đủ dữ liệu để lấp batch.
- `linger.ms` cho producer thêm thời gian gom bản ghi. Giá trị lớn hơn có thể tăng hiệu quả batch và thêm thời gian chờ.
- `buffer-memory` xác định bộ nhớ producer dành cho các bản ghi đang chờ gửi. Buffer giúp hấp thụ burst ngắn; nếu tải dài hạn vượt năng lực broker, buffer vẫn cạn.
- `compression-type` chọn codec nén batch. Hãy đo compression ratio và CPU bằng payload thật.
- `acks: all` yêu cầu xác nhận theo ISR. Cần đặt replication factor và `min.insync.replicas` phù hợp.
- `max-poll-records` giới hạn số record trả về trong một lần `poll`; phải cân bằng batch xử lý và thời gian giữa các lần poll.
- `fetch-min-size` và `fetch-max-wait` ảnh hưởng lượng dữ liệu broker cố gắng gom và thời gian chờ fetch. Giá trị cao hơn có thể tăng hiệu quả truyền nhưng tăng latency khi tải thấp.
- `listener.concurrency` đặt số consumer chạy song song trong listener container. Số consumer hữu ích còn bị giới hạn bởi partition được gán và năng lực downstream.

Ví dụ listener:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-processor",
    concurrency = "12"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
```

Nếu topic có 8 partition, concurrency 12 không tạo ra 12 consumer cùng nhận dữ liệu của topic đó; tối đa 8 consumer trong group được gán partition tại cùng thời điểm. Nếu cần 12 consumer hoạt động song song, topic phải có đủ partition và cách phân phối key phải cho phép tải được chia đều.

Khi xử lý peak, không nên tăng `max-poll-records`, concurrency hoặc buffer chỉ dựa trên một chỉ số. Hãy kiểm tra thời gian xử lý một poll, `max.poll.interval.ms`, heartbeat, rebalance, số connection database và giới hạn dịch vụ ngoài. Một consumer có thể fetch nhanh nhưng xử lý quá lâu, khiến group rebalance và throughput thực tế giảm.

## 9. Mở rộng capacity theo từng tầng

### 9.1. Producer

Nếu producer là nút thắt, kiểm tra serialization, batch efficiency, compression, buffer wait, số thread gửi và kết nối mạng. Có thể tăng batching hoặc tối ưu payload khi CPU và latency cho phép. Nếu producer gửi đến nhiều partition, phân bố key hợp lý giúp sử dụng tài nguyên broker đồng đều hơn.

Không mở rộng producer vô hạn để bù cho consumer chậm. Điều đó có thể làm backlog tăng nhanh hơn, chiếm buffer và tăng áp lực broker.

### 9.2. Broker

Khi broker là giới hạn, xác định tài nguyên đang bão hòa trước khi thêm node. Có thể cần tăng network capacity, disk throughput, CPU, phân bố lại leader/replica hoặc mở rộng cluster. Thêm broker mà không reassignment partition có thể không cải thiện ngay tải của các broker hiện tại.

Đánh giá cả tác động của việc di chuyển replica: reassignment tạo thêm network và disk I/O, có thể làm latency tăng trong lúc peak. Lên lịch di chuyển partition ngoài cửa sổ peak nếu có thể và giới hạn tốc độ di chuyển theo khả năng cluster.

### 9.3. Consumer

Khi consumer là nút thắt, tìm xem giới hạn nằm ở xử lý CPU, I/O, partition count hay downstream. Tối ưu truy vấn database, dùng batch API phù hợp, giới hạn concurrency và connection pool, hoặc mở rộng consumer group nếu partition còn đủ.

Nếu tăng consumer làm database bão hòa, throughput toàn hệ thống có thể giảm. Capacity của consumer group phải được tính cùng capacity của database, HTTP service, cache và các hệ thống được gọi trong listener.

### 9.4. Hệ thống phụ trợ

Consumer có thể xử lý nhanh hơn năng lực ghi của database hoặc dịch vụ đích. Khi đó cần xem xét batch write, index, transaction size, connection pool, partitioning ở hệ thống đích và giới hạn rate. Cần bảo đảm các thay đổi vẫn giữ ngữ nghĩa xử lý, idempotency và khả năng retry.

Một cách bảo vệ downstream là giới hạn concurrency hoặc áp dụng backpressure. Điều này có thể làm Kafka lag tăng tạm thời nhưng tránh làm hệ thống đích sụp đổ. Capacity plan cần xác định backlog tối đa được phép, thời gian lưu dữ liệu và thời gian catch-up sau khi downstream phục hồi.

## 10. Quy trình lập capacity plan

Một quy trình thực tế có thể triển khai theo các bước sau:

1. **Xác định SLO và phạm vi.** Ghi rõ peak throughput, p95/p99 latency, tỷ lệ lỗi, durability, recovery time và ranh giới hoàn tất nghiệp vụ.
2. **Thu thập workload.** Đo tốc độ theo nhiều cửa sổ, record size, key distribution, số topic, số consumer group, retention, retry và replay.
3. **Dự báo tăng trưởng.** Áp dụng growth factor cho giai đoạn thiết kế; ghi rõ giả định về mùa vụ và sự kiện kinh doanh.
4. **Tính năng lực consumer.** Benchmark records/s trên mỗi consumer trong điều kiện SLO, tính số consumer và kiểm tra N-1.
5. **Chọn partition count.** Đáp ứng mức song song cần thiết, giữ ordering theo yêu cầu và kiểm tra hot partition.
6. **Tính broker resources.** Ước lượng network, disk capacity, disk throughput, CPU, memory và replication traffic theo từng broker.
7. **Tính storage.** Dùng tốc độ trung bình trong retention window, compression ratio đo được, replication factor, overhead và target disk utilization.
8. **Kiểm tra downstream.** Xác nhận database, API, cache, connection pool và quota chịu được tốc độ consumer dự kiến.
9. **Benchmark tải đại diện.** Chạy baseline, sustained peak, short burst, peak có key skew và replay nếu phù hợp.
10. **Thử nghiệm sự cố.** Dừng một consumer, restart broker hoặc mô phỏng downstream chậm để xác nhận headroom và thời gian phục hồi.
11. **Ghi lại giả định và ngưỡng.** Lưu mô hình tính, cấu hình, metric, giới hạn đã đo và ngưỡng cảnh báo để có thể cập nhật khi workload thay đổi.
12. **Rà soát định kỳ.** Cập nhật capacity plan khi peak mới, record size, retention, partition count, consumer group hoặc yêu cầu SLO thay đổi.

## 11. Kịch bản benchmark cần có

Một bài benchmark cho capacity planning nên bao phủ các trường hợp sau:

| Kịch bản | Mục đích | Quan sát chính |
|---|---|---|
| Normal load | Xác nhận baseline | Throughput, latency, CPU và lag bình thường |
| Sustained peak | Kiểm tra năng lực dài hạn | Tài nguyên broker/consumer, p99 và lag theo thời gian |
| Short burst | Kiểm tra khả năng hấp thụ burst | Buffer wait, queue growth, thời gian drain |
| Ramp-up | Kiểm tra khả năng scale | Thời gian autoscaling, rebalance và độ trễ khi tăng tải |
| Key skew | Kiểm tra partition nóng | Records/s theo partition và mức mất cân bằng consumer |
| Large records | Kiểm tra giới hạn byte/batch | Request size, fetch, network, memory và disk |
| Retry/replay | Kiểm tra tải phụ phát sinh | Retry rate, dead-letter, consumer lag và downstream capacity |
| Consumer failure | Kiểm tra N-1 | Năng lực còn lại, rebalance và catch-up |
| Broker failure | Kiểm tra replication/failover | ISR, leader movement, network và latency khi phục hồi |
| Slow downstream | Kiểm tra backpressure | Queue growth, connection pool, timeout và khả năng drain sau phục hồi |

Không chỉ ghi throughput cực đại. Với mỗi kịch bản, ghi nhận p50/p95/p99 latency, lỗi, consumer lag, CPU, memory/GC, network, disk, request queue và thời gian để trở lại trạng thái bình thường.

## 12. Theo dõi capacity trong vận hành

Capacity plan là mô hình cần được cập nhật bằng số liệu production. Các dashboard nên cho phép nhìn tổng quan và drill-down theo topic, partition, consumer group và broker.

### Producer

- Records sent/s và bytes sent/s.
- Batch size trung bình và records per request.
- Request latency, retry, timeout và lỗi gửi.
- Buffer available, buffer wait và số lần hết buffer.

### Broker

- Bytes in/out theo broker.
- Request rate, request queue time và request processing time.
- CPU, network, disk throughput, disk latency và dung lượng còn trống.
- Leader/replica distribution, ISR shrink/expand và under-replicated partitions.
- Tình trạng quota, connection và request handler.

### Consumer

- Records consumed/s và bytes consumed/s.
- Lag theo group và partition, cùng tốc độ lag tăng/giảm.
- Tuổi bản ghi cũ nhất hoặc end-to-end latency nếu ứng dụng đo được.
- Thời gian xử lý listener, poll duration, commit latency và rebalance count.
- Retry, dead-letter rate và số lượng consumer đang hoạt động.

### Downstream

- Database transaction rate, query latency, connection pool usage và lock wait.
- HTTP request rate, latency, timeout và giới hạn quota.
- Queue hoặc worker backlog của hệ thống đích.

Đặt cảnh báo dựa trên xu hướng và SLO. Ví dụ, consumer lag tăng liên tục trong 10 phút có ý nghĩa khác với một đợt lag tăng ngắn rồi giảm. Disk utilization tăng đều có thể cảnh báo sớm hơn việc đợi broker đầy đĩa. p99 latency tăng cùng request queue hoặc database latency giúp xác định tầng gây nghẽn.

Không nên chỉ cảnh báo khi CPU vượt một ngưỡng. Một partition nóng có thể làm một consumer bão hòa trong khi CPU trung bình của cả cluster vẫn thấp. Tương tự, network hoặc disk có thể là nút thắt trước khi CPU đạt mức cao.

## 13. Những sai lầm thường gặp

- **Dùng average traffic để thiết kế peak:** bỏ qua burst và tải kéo dài trong các sự kiện đặc biệt.
- **Lấy một giá trị max không có cửa sổ đo:** dễ bị ảnh hưởng bởi spike đo lường hoặc sự kiện không đại diện.
- **Dùng peak ngắn cho toàn bộ retention:** phóng đại storage nếu không tính thời lượng và tốc độ trung bình có trọng số.
- **Chỉ tính records/s:** bỏ qua record size, bytes/s, compression, replication và số consumer group.
- **Coi tổng cluster capacity là đủ:** một broker hoặc partition nóng vẫn có thể quá tải do phân bố không đều.
- **Tăng consumer mà không tăng partition:** consumer dư không được gán partition và không tạo thêm throughput.
- **Tăng partition mà không kiểm tra key:** hot key vẫn có thể tập trung vào một partition.
- **Bỏ qua downstream:** consumer tăng tốc có thể làm database hoặc API quá tải.
- **Không tính replay và retry:** lưu lượng phát sinh sau sự cố có thể trùng với peak người dùng.
- **Không thử nghiệm N-1:** throughput bình thường không chứng minh cluster còn đủ năng lực khi mất một node.
- **Scale broker mà không phân bố lại partition:** node mới có thể chưa nhận phần tải cần thiết.
- **Chọn headroom theo cảm tính:** dự phòng quá ít gây vi phạm SLO; dự phòng quá nhiều làm tăng chi phí mà không có căn cứ.
- **Không cập nhật mô hình:** tăng trưởng, thay đổi payload và consumer group có thể làm giả định cũ không còn đúng.

## 14. Checklist capacity planning

Trước khi chốt kế hoạch capacity cho một topic hoặc consumer group, hãy xác nhận:

- [ ] Đã xác định SLO, ranh giới đo throughput và end-to-end latency.
- [ ] Đã thu thập peak theo nhiều cửa sổ và thời lượng peak.
- [ ] Đã phân loại sustained peak, burst, ramp-up, retry, replay và key skew.
- [ ] Đã đo record size trung bình, p95/p99 và compression ratio.
- [ ] Đã áp dụng growth factor cho giai đoạn thiết kế.
- [ ] Đã chọn rõ headroom factor hoặc target utilization và tránh tính dự phòng trùng lặp.
- [ ] Đã benchmark năng lực consumer trong điều kiện xử lý nghiệp vụ thực tế.
- [ ] Đã chọn partition count phù hợp với concurrency, ordering và key distribution.
- [ ] Đã tính backlog và thời gian drain sau peak.
- [ ] Đã tính retention bằng tốc độ trung bình trong retention window, compression, replication và overhead.
- [ ] Đã kiểm tra network, disk, CPU, memory và replication theo từng broker.
- [ ] Đã xác nhận database, API, quota và các dịch vụ downstream chịu được peak.
- [ ] Đã kiểm tra N-1 cho consumer và broker.
- [ ] Đã chạy benchmark sustained peak, burst, key skew, replay và failure scenario.
- [ ] Đã thiết lập dashboard, cảnh báo và lịch rà soát capacity.

Capacity planning theo peak traffic cần kết hợp workload thực tế, dự báo tăng trưởng, năng lực xử lý đã đo và headroom cho sự cố. Với Spring Kafka, số partition và consumer quyết định khả năng song song; broker, replication, network và disk quyết định khả năng tiếp nhận và lưu trữ; các dịch vụ downstream quyết định tốc độ hoàn tất nghiệp vụ. Khi tính riêng từng tầng, kiểm tra N-1 và benchmark với hình dạng peak đại diện, hệ thống có thể xử lý đợt tăng tải mà vẫn duy trì latency, durability và thời gian phục hồi theo mục tiêu vận hành.
