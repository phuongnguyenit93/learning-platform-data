# Ước lượng thời gian xử lý backlog và mục tiêu phục hồi

## Lập năng lực tiêu thụ để bắt kịp dữ liệu sau sự cố

Trong Kafka, backlog của một consumer group là lượng dữ liệu đã được ghi vào topic nhưng group chưa xử lý và commit đến vị trí tương ứng. Backlog có thể tăng khi consumer dừng, giảm số instance, downstream chậm, broker/network bị giới hạn hoặc tốc độ producer vượt năng lực xử lý.

Hoạch định năng lực không chỉ trả lời “cần bao nhiêu consumer”. Cần xác định:

- Backlog hiện tại lớn đến đâu và nằm ở partition nào.
- Producer vẫn tiếp tục tạo dữ liệu với tốc độ bao nhiêu.
- Consumer xử lý bền vững được bao nhiêu record/byte mỗi giây.
- Có bao nhiêu partition có thể xử lý song song.
- Downstream, broker, network, disk và CPU có đủ năng lực hay không.
- Tổ chức muốn khôi phục dịch vụ trong bao lâu và muốn xóa backlog trong bao lâu.

Điểm mấu chốt là tốc độ xử lý ròng. Khi producer vẫn tiếp tục ghi, backlog chỉ giảm nếu năng lực tiêu thụ lớn hơn tốc độ dữ liệu mới đến.

## 1. Backlog trong Kafka là gì?

### 1.1 Backlog theo consumer group và partition

Mỗi consumer group có committed offset riêng cho từng partition. Broker cũng duy trì log end offset (LEO) của partition. Chênh lệch giữa log end và committed offset được dùng để ước lượng consumer lag.

Ví dụ:

```text
Topic: orders
Partition: 0
CURRENT-OFFSET: 120000
LOG-END-OFFSET: 150000
LAG: 30000
```

Group còn cách log end khoảng 30.000 offset trên partition này. Tổng lag của group có thể được tính bằng cách cộng lag các partition, nhưng cần nhớ lag là khoảng cách offset, không phải lúc nào cũng bằng chính xác số business record còn phải xử lý.

Offset có thể có khoảng trống do compaction, transaction control records hoặc các cơ chế log khác. Consumer đọc với `read_committed` cũng có thể bỏ qua aborted transaction records. Vì vậy, lag theo offset là chỉ báo tiến độ hữu ích, nhưng không phải bộ đếm công việc chính xác trong mọi topic.

### 1.2 Backlog không chỉ là committed lag

Khi tính năng lực ứng dụng, cần quan sát thêm:

- Record đã poll nhưng chưa hoàn tất xử lý.
- Record đã xử lý side effect nhưng chưa commit offset.
- Công việc đã chuyển vào worker pool hoặc hàng đợi nội bộ.
- Retry đang chờ, record bị lỗi hoặc đang nằm trong retry topic.

Committed lag có thể vẫn cao dù worker đã xử lý một phần record nhưng chưa commit. Ngược lại, nếu ứng dụng commit quá sớm rồi mới xử lý, committed lag có thể thấp trong khi công việc vẫn còn trong queue nội bộ.

Do đó, định nghĩa backlog phục vụ capacity planning cần nhất quán. Thông thường hãy dùng consumer group lag theo partition để đo phần còn phải đọc, đồng thời đo riêng in-flight work và application queue depth.

### 1.3 Đo lag

Dùng công cụ consumer group để xem offset và lag:

```bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 \
  --describe --group order-projection
```

Kết quả có các cột như CURRENT-OFFSET, LOG-END-OFFSET, LAG, CONSUMER-ID, HOST và CLIENT-ID tùy phiên bản/cách chạy. Có thể dùng --members --verbose để xem assignment khi cần điều tra phân bố partition.

Không chỉ ghi lại tổng lag. Hãy lưu lag theo partition, vì một partition nóng có thể quyết định thời gian bắt kịp của toàn group.

## 2. Công thức tính thời gian drain backlog

### 2.1 Các đại lượng

Ký hiệu:

| Ký hiệu | Ý nghĩa | Đơn vị ví dụ |
|---|---|---|
| \(B\) | Backlog tại thời điểm bắt đầu phục hồi | record |
| \(\lambda\) | Tốc độ record mới được producer ghi vào | record/giây |
| \(\mu\) | Năng lực xử lý bền vững của consumer group | record/giây |
| \(T\) | Thời gian cần để backlog trở về 0 hoặc mức mục tiêu | giây |

Các tốc độ \(\lambda\) và \(\mu\) phải dùng cùng đơn vị và cùng phạm vi. Nếu backlog tính bằng record thì tốc độ cũng phải là record/giây. Nếu record có kích thước hoặc chi phí xử lý khác nhau đáng kể, hãy tính thêm theo byte/giây hoặc work unit/giây.

### 2.2 Khi producer vẫn tiếp tục ghi

Trong thời gian consumer xử lý backlog, producer vẫn tạo thêm record. Tốc độ backlog thay đổi là:

\[
\frac{dB}{dt} = \lambda - \mu
\]

Nếu \(\mu > \lambda\), backlog giảm với tốc độ ròng \(\mu-\lambda\). Với tốc độ gần như ổn định, thời gian drain xấp xỉ:

\[
T = \frac{B}{\mu-\lambda}
\]

Nếu \(\mu = \lambda\), consumer chỉ xử lý vừa đủ dữ liệu mới; backlog không giảm. Nếu \(\mu < \lambda\), backlog tiếp tục tăng.

Đây là công thức quan trọng nhất khi lập kế hoạch catch-up trong lúc hệ thống vẫn hoạt động.

### 2.3 Khi producer đã dừng hoặc không có dữ liệu mới

Nếu không có record mới đến, \(\lambda=0\), do đó:

\[
T = \frac{B}{\mu}
\]

Đây là trường hợp đơn giản hơn nhưng ít phù hợp với hệ thống production liên tục phát event.

### 2.4 Tính năng lực cần có theo mục tiêu thời gian

Nếu muốn xóa backlog \(B\) trong thời gian \(T\), trong khi producer tiếp tục ghi với tốc độ \(\lambda\), năng lực tối thiểu cần đạt là:

\[
\mu_{required} = \lambda + \frac{B}{T}
\]

Trong thực tế không nên thiết kế đúng sát giá trị tối thiểu. Hãy cộng headroom cho burst, retry, partition skew, GC, broker throttling và biến động downstream:

\[
\mu_{plan} = \mu_{required} \times (1+h)
\]

Trong đó \(h\) là tỷ lệ headroom do đội vận hành chọn dựa trên mức biến động và SLO. Ví dụ có thể bắt đầu đánh giá với 20–30%, nhưng cần xác nhận bằng benchmark và không coi đây là con số bắt buộc cho mọi hệ thống.

## 3. Ví dụ tính backlog và recovery target

Giả sử một consumer group xử lý topic orders có:

- Backlog ban đầu \(B=120.000.000\) record.
- Producer vẫn ghi trung bình \(\lambda=15.000\) record/giây.
- Mục tiêu xóa backlog trong \(T=60\) phút, tức 3.600 giây.

Năng lực xử lý tối thiểu:

\[
\mu_{required}=15.000+\frac{120.000.000}{3.600}
=48.333,3\ \text{record/giây}
\]

Nếu cộng 25% headroom:

\[
\mu_{plan}=48.333,3 \times 1,25
\approx 60.417\ \text{record/giây}
\]

Benchmark với payload và downstream gần production cho thấy một worker tương đương xử lý bền vững 7.000 record/giây trong cấu hình group dự kiến. Số worker cần thiết theo phép chia sơ bộ:

\[
N=\left\lceil\frac{60.417}{7.000}\right\rceil=9
\]

Với 12 partition và consumer group truyền thống, 9 consumer có thể hoạt động đồng thời; ba partition còn lại được phân bổ thêm cho một số member. Tổng năng lực danh nghĩa khoảng 63.000 record/giây. Nếu mức này được benchmark trong layout assignment thực tế và không có partition nóng, thời gian drain ước lượng:

\[
T=\frac{120.000.000}{63.000-15.000}
=2.500\ \text{giây}
\approx 41,7\ \text{phút}
\]

Kết quả đáp ứng mục tiêu 60 phút trong giả định đã nêu. Nếu 7.000 record/giây chỉ là throughput đo trên một partition riêng lẻ, không được nhân thẳng với số worker; cần benchmark lại trong group có assignment và tải downstream thực tế.

### 3.1 Bảng thay đổi năng lực

Với cùng backlog 120 triệu record và producer rate 15.000 record/giây:

| Năng lực consumer \(\mu\) | Tốc độ drain ròng | Thời gian drain |
|---:|---:|---:|
| 15.000 record/s | 0 | Không drain |
| 25.000 record/s | 10.000 record/s | 200 phút |
| 40.000 record/s | 25.000 record/s | 80 phút |
| 48.333 record/s | 33.333 record/s | Khoảng 60 phút |
| 63.000 record/s | 48.000 record/s | Khoảng 41,7 phút |

Bảng cho thấy thêm consumer chỉ có ích khi năng lực tổng tăng thực sự. Nếu downstream đã đạt giới hạn, số consumer tăng lên có thể chỉ làm queue, timeout và retry tăng.

## 4. Tính theo từng partition, không chỉ nhìn tổng

### 4.1 Partition chậm nhất quyết định thời gian hoàn tất

Với consumer group truyền thống, mỗi partition được giao cho tối đa một consumer member tại một thời điểm. Tổng capacity có thể lớn nhưng một partition nóng vẫn làm group chưa bắt kịp hoàn toàn.

Với partition \(i\):

- \(B_i\): backlog của partition.
- \(\lambda_i\): tốc độ record mới vào partition.
- \(\mu_i\): năng lực xử lý partition đó.

Thời gian drain partition:

\[
T_i=\frac{B_i}{\mu_i-\lambda_i}
\quad \text{khi } \mu_i>\lambda_i
\]

Thời gian để toàn bộ partition đạt mục tiêu gần bằng partition drain chậm nhất:

\[
T_{group}\approx\max_i(T_i)
\]

Nếu tồn tại partition có \(\mu_i \le \lambda_i\), partition đó không bao giờ bắt kịp khi tốc độ đầu vào giữ nguyên, dù tổng throughput group nhìn chung cao.

### 4.2 Ví dụ partition skew

| Partition | Backlog | Arrival \(\lambda_i\) | Capacity \(\mu_i\) | Drain time |
|---|---:|---:|---:|---:|
| P0 | 30 triệu | 4.000/s | 6.000/s | 250 phút |
| P1 | 20 triệu | 3.000/s | 7.000/s | 83,3 phút |
| P2 | 10 triệu | 2.000/s | 6.000/s | 41,7 phút |

P0 quyết định thời gian hoàn tất, dù tổng lag của P1 và P2 cũng đáng kể. Nếu P0 có key nóng hoặc xử lý downstream chậm, thêm consumer instance không thể chia một partition thành nhiều member trong cùng consumer group.

### 4.3 Hot key và partition skew

Các nguyên nhân phổ biến:

- Một key chiếm phần lớn traffic và luôn được hash vào cùng partition.
- Một số event type có payload lớn hoặc xử lý tốn CPU hơn.
- Một partition có leader trên broker chậm hoặc disk/network bị giới hạn.
- Consumer xử lý tuần tự theo partition nhưng downstream có latency không đồng đều.

Giải pháp có thể gồm điều chỉnh key strategy, tách workload, tăng partition trong kế hoạch có kiểm soát hoặc xử lý một số loại event bằng pipeline riêng. Đổi partition count có thể thay đổi mapping key cho record mới; cần đánh giá ordering và state trước khi thay đổi.

### 4.4 Share Groups là trường hợp khác

Giới hạn một consumer member cho mỗi partition áp dụng cho consumer group truyền thống. Kafka Share Groups phân phối record qua acquisition/acknowledgement và cho phép nhiều share consumer cùng làm việc trên một partition. Tuy nhiên, throughput của share group vẫn phải được đo thực tế theo lock, acknowledgement, broker và downstream; không dùng công thức số partition để suy ra số worker tối đa cho share group.

Công thức backlog drain vẫn áp dụng cho share group nếu \(\mu\) là năng lực xử lý bền vững đã đo của toàn share group và backlog được xác định nhất quán theo loại group đó.

## 5. Backlog theo byte và thời gian retention

### 5.1 Record count không phản ánh đầy đủ tải

100 triệu record kích thước 200 byte khác rất nhiều so với 100 triệu record kích thước 20 KiB. Ngoài record count, cần đo:

- Byte backlog còn phải đọc.
- Tốc độ byte mới được producer ghi.
- Tốc độ byte consumer có thể fetch và xử lý.
- Kích thước sau deserialize và chi phí downstream.

Ước lượng sơ bộ:

\[
B_{bytes}\approx B_{records}\times S_{avg,stored}
\]

Trong đó \(S_{avg,stored}\) là kích thước trung bình thực tế trong log sau batching/compression và overhead phù hợp với cách đo. Không dùng kích thước object Java sau deserialize để thay thế byte lưu trên broker.

Nếu record size biến động mạnh, hãy đo byte rate và record rate riêng. Một consumer có thể đạt mục tiêu record/giây nhưng vẫn bị giới hạn bởi network hoặc disk khi payload lớn.

### 5.2 Retention phải giữ đủ backlog trong thời gian phục hồi

Kafka retention không tự động giữ record chỉ vì một consumer group chưa đọc đến. Nếu segment hết hạn theo retention policy, consumer có thể mất khả năng replay phần backlog cũ dù committed offset vẫn còn phía trước log start offset.

Vì vậy, thời gian retention cần bao phủ:

\[
T_{retention} >
T_{outage}+T_{restore}+T_{catchup}+T_{safety}
\]

Đây là điều kiện hoạch định đơn giản; cần kiểm tra cả retention theo thời gian, retention theo dung lượng, compaction và chính sách lưu trữ tiered storage nếu có.

### 5.3 Dung lượng disk của cluster

Ước lượng dung lượng log vật lý trên toàn cluster trước khi phân bổ cho từng broker:

\[
Storage \approx IngestBytesPerDay \times RetentionDays \times RF
\]

Đây là ước lượng tổng dung lượng các replica, không phải dung lượng của từng broker. Sau đó phân bổ theo broker/rack và cộng headroom cho:

- Segment/index overhead.
- Chênh lệch phân bố partition.
- Reassignment hoặc replica rebuild.
- Burst ingest.
- Disk reserve để tránh broker đầy.

Sử dụng byte thực tế sau compression từ broker metrics hoặc log storage, không dùng payload size thô nếu compression làm thay đổi đáng kể dung lượng. Backlog của consumer không tạo thêm một bản log riêng; dữ liệu đã nằm trong Kafka log và phải được retention giữ lại cho đến khi group đọc xong.

## 6. Kiểm tra capacity của consumer và hệ thống phụ thuộc

### 6.1 Throughput consumer phải là throughput đầu-cuối

Khi benchmark, đo số record đã xử lý thành công và commit đúng, không chỉ số record fetch hoặc poll.

Throughput thực tế bị giới hạn bởi thành phần chậm nhất:

```text
Effective capacity = min(
  consumer processing capacity,
  downstream capacity,
  broker read capacity,
  network capacity,
  partition concurrency capacity
)
```

Đây là mô hình khái niệm. Trong hệ thống thực tế, các thành phần có thể pipeline và overlap; vẫn cần đo end-to-end thay vì cộng các throughput độc lập.

### 6.2 Những yếu tố làm throughput benchmark cao hơn production

- Dữ liệu thử nhỏ hơn hoặc dễ nén hơn dữ liệu thật.
- Không có TLS, authentication hoặc network hop như production.
- Database/API downstream không có tải cạnh tranh.
- Không bật transaction, retry, deduplication hoặc validation thực tế.
- Benchmark chỉ chạy ngắn nên chưa thấy GC, disk pressure và cache miss.
- Chỉ đo poll/fetch rate mà không đo side effect và commit.
- Không có partition skew hoặc burst traffic trong test.

Hãy dùng payload phân bố gần thực tế, thời gian chạy đủ dài và downstream cùng cấu hình bảo mật với production.

### 6.3 Downstream thường là nút thắt

Ví dụ consumer đọc được 80.000 record/giây nhưng database chỉ ghi bền vững 35.000 record/giây. Năng lực xử lý thực tế không phải 80.000; nếu không có queue hữu hạn và backpressure, ứng dụng chỉ tích lũy công việc trong memory hoặc tạo timeout.

Kiểm tra:

- Database connection pool, transaction latency và write IOPS.
- API rate limit, quota và response p95/p99.
- Thread pool, bounded queue và rejection rate.
- CPU, heap, GC và deserialize cost.
- Retry/DLT rate và thời gian xử lý lỗi.

Không scale consumer vượt quá khả năng downstream có thể nhận một cách bền vững.

## 7. Tính số consumer và kiểm tra partition concurrency

### 7.1 Ước lượng ban đầu

Nếu một consumer instance có throughput bền vững \(r\) record/giây trong điều kiện tải tương tự production, số instance sơ bộ:

\[
N=\left\lceil\frac{\mu_{plan}}{r}\right\rceil
\]

Với consumer group truyền thống, số consumer hoạt động đồng thời trên một topic không thể vượt số partition được assign. Nếu \(N\) lớn hơn partition count, các instance dư không có partition để xử lý topic đó.

### 7.2 Đừng nhầm số instance với số luồng xử lý

Một consumer instance có thể sở hữu nhiều partition và có thể dùng worker pool để xử lý song song, nhưng điều đó yêu cầu quản lý offset completion, ordering, pause/resume và rebalance cẩn thận. Một partition vẫn là đơn vị assignment độc quyền giữa các consumer member trong cùng consumer group.

Nếu cần tăng concurrency:

- Tăng consumer instance đến giới hạn partition hiện tại nếu broker/downstream còn capacity.
- Đánh giá tăng partition khi cần nhiều đơn vị xử lý độc lập hơn.
- Phân tích key distribution để tránh một key nóng chi phối partition.
- Cân nhắc worker pool trong mỗi instance nếu xử lý song song phù hợp với semantics.
- Giữ commit offset theo thứ tự completion an toàn trên từng partition.

### 7.3 Thêm consumer không phải lúc nào cũng tăng throughput

Nếu consumer count tăng nhưng throughput tổng không đổi, có thể bottleneck nằm ở:

- Partition count hoặc partition skew.
- Database/API downstream.
- Broker disk/network hoặc fetch quota.
- CPU/GC hoặc deserialization.
- Lock contention và thread pool.
- Rebalance thường xuyên.

Đo throughput sau mỗi lần scale và dừng tăng instance khi marginal throughput gần bằng 0 hoặc latency/error tăng nhanh.

## 8. Recovery objective: RTO, RPO và catch-up time

### 8.1 Phân biệt các mục tiêu

| Thuật ngữ | Ý nghĩa |
|---|---|
| RTO (Recovery Time Objective) | Thời gian tối đa tổ chức chấp nhận để khôi phục dịch vụ sau sự cố |
| RPO (Recovery Point Objective) | Mức dữ liệu có thể chấp nhận mất, thường biểu diễn bằng thời gian |
| Backlog catch-up target | Thời gian tối đa để consumer xử lý phần dữ liệu tồn đọng và trở lại lag mục tiêu |
| Steady-state headroom | Năng lực dự phòng để hệ thống chịu burst hoặc một phần tài nguyên bị mất |

RTO không mặc nhiên đồng nghĩa với thời gian xóa hết backlog. Dịch vụ có thể hoạt động trở lại sau 10 phút nhưng cần thêm 50 phút để xử lý hết dữ liệu tồn. Hãy ghi rõ SLA yêu cầu “service restored” hay “consumer caught up”.

RPO cũng không phải consumer lag. Nếu record đã được Kafka lưu và còn trong retention, consumer chưa xử lý không đồng nghĩa dữ liệu đã mất. RPO liên quan đến mức dữ liệu có thể mất khi phục hồi sau sự cố, phụ thuộc replication, acknowledgement, storage và quy trình backup/DR.

### 8.2 Tổng thời gian phục hồi

Một cách phân rã để lập kế hoạch:

\[
T_{recovery}=T_{detect}+T_{diagnose}+T_{restore}+T_{catchup}
\]

Trong đó:

- \(T_{detect}\): thời gian phát hiện.
- \(T_{diagnose}\): thời gian khoanh vùng và quyết định.
- \(T_{restore}\): thời gian khôi phục consumer/broker/downstream.
- \(T_{catchup}\): thời gian drain backlog đến ngưỡng lag mục tiêu.

Nếu SLA chỉ đo thời gian dịch vụ nhận request trở lại, RTO có thể kết thúc trước catch-up. Nếu SLA yêu cầu dữ liệu được xử lý hoàn toàn, phải đưa catch-up vào mục tiêu phục hồi.

### 8.3 Tạo backlog trong thời gian outage

Nếu consumer ngừng xử lý trong \(\Delta t\) giây và producer tiếp tục ghi ổn định:

\[
B_{outage}\approx \lambda \times \Delta t
\]

Backlog thực tế còn gồm lag đã có trước outage, record đang retry và các biến động traffic. Dùng số đo lag khi khôi phục thay vì chỉ ước lượng từ thời gian outage.

## 9. Xử lý traffic thay đổi theo thời gian

Công thức \(B/(\mu-\lambda)\) giả định tốc độ đến và tốc độ xử lý gần ổn định. Trong production, chúng thay đổi theo giờ cao điểm, batch producer, retry và downstream.

Với các khoảng thời gian nhỏ:

\[
B_{t+1}=\max(0,\ B_t+(\lambda_t-\mu_t)\Delta t)
\]

Tính lặp theo từng cửa sổ 1 phút hoặc 5 phút sẽ cho dự báo sát hơn. Khi capacity thay đổi do autoscaling, dùng \(\mu_t\) tương ứng với số instance thực tế và partition assignment ở mỗi cửa sổ.

Nếu producer có thể giảm tốc hoặc tạm dừng, mô hình cần cập nhật \(\lambda_t\). Backpressure ở producer có thể giúp backlog không tăng thêm, nhưng phải đánh giá tác động đến API, upstream và SLA phát event.

### 9.1 Dự báo theo cửa sổ

Ví dụ một hệ thống có:

| Khoảng thời gian | Arrival rate | Consumer capacity | Thay đổi backlog mỗi giây |
|---|---:|---:|---:|
| Giờ thấp điểm | 8.000/s | 40.000/s | Giảm 32.000 |
| Giờ bình thường | 15.000/s | 40.000/s | Giảm 25.000 |
| Giờ cao điểm | 38.000/s | 40.000/s | Giảm 2.000 |
| Burst | 55.000/s | 40.000/s | Tăng 15.000 |

Nếu chỉ dùng arrival rate trung bình cả ngày, dự báo có thể bỏ qua việc backlog tăng trong burst. Hãy mô phỏng đúng lịch traffic và xác định backlog cực đại, không chỉ backlog cuối ngày.

## 10. Kế hoạch benchmark và xác nhận recovery objective

### 10.1 Kịch bản cần kiểm thử

1. Steady state: producer và consumer chạy ở tải bình thường.
2. Peak load: producer chạy ở p95/p99 rate dự kiến.
3. Consumer outage: dừng group trong khoảng thời gian đại diện rồi bật lại.
4. Scale-out: tăng consumer đến giới hạn partition và đo marginal throughput.
5. Downstream slowdown: tăng latency hoặc giới hạn database/API.
6. Broker maintenance: một broker hoặc leader unavailable trong phạm vi thử nghiệm an toàn.
7. Retry/poison record: đo phần capacity mất đi khi có lỗi và retry.
8. Catch-up: xác nhận lag giảm đúng dự báo trong khi producer vẫn tiếp tục ghi.

### 10.2 Chỉ số cần ghi

- Arrival records/sec và bytes/sec theo topic/partition.
- Consumer records/sec và bytes/sec đã xử lý thành công.
- Consumer lag tổng và theo partition.
- Thời gian xử lý record/batch p50, p95, p99.
- Commit latency và số record in-flight.
- Consumer count, assigned partitions và rebalance count.
- Retry/DLT rate và downstream error/latency.
- Broker disk/network/CPU, fetch request latency và replication health.
- Heap, GC pause, thread pool và queue depth.

### 10.3 Tiêu chí đạt

- Consumer capacity lớn hơn arrival rate trong suốt giai đoạn catch-up.
- Lag giảm theo tốc độ ròng đã tính, không chỉ giảm trong một khoảng ngắn.
- Partition nóng không có \(\mu_i \le \lambda_i\).
- Downstream không vượt quota hoặc SLO.
- Không tăng duplicate/lost side effect do commit sai.
- Broker vẫn giữ replication/ISR và request latency trong ngưỡng vận hành.
- Thời gian phục hồi đạt objective đã thống nhất.

## 11. Dashboard và cảnh báo cho backlog

Dashboard capacity nên có:

**Backlog**

- Consumer lag tổng và per partition.
- Log end offset, committed offset và log start offset.
- Lag tăng/giảm theo thời gian.
- Backlog bytes ước lượng nếu có metric phù hợp.

**Rate**

- Producer arrival records/sec và bytes/sec.
- Consumer processed records/sec và bytes/sec.
- Net drain rate: \(\mu-\lambda\).
- Retry/DLT rate.

**Resource**

- Consumer CPU, heap, GC và processing latency.
- Broker disk, network, request queue và replication lag.
- Downstream throughput, connection pool, quota và latency.

Gợi ý alert:

- Net drain rate bằng hoặc thấp hơn 0 trong khi backlog đang tồn tại.
- Backlog tăng liên tục vượt ngưỡng theo SLO.
- Partition lag lớn nhất tăng nhanh hơn lag trung bình.
- Dự báo catch-up time vượt recovery target.
- Retention headroom không đủ để giữ dữ liệu đến khi catch-up.
- Downstream error/latency hoặc queue depth tăng khi scale consumer.

Không cảnh báo chỉ dựa trên tổng lag. Topic ít traffic có thể có lag nhỏ nhưng tồn tại lâu; topic throughput cao có thể có lag lớn nhưng drain rất nhanh. Kết hợp lag với tốc độ đến, tốc độ xử lý và thời gian drain dự báo.

## 12. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Tính \(B/\mu\) trong khi producer vẫn ghi | Dự báo catch-up quá lạc quan | Dùng \(B/(\mu-\lambda)\) |
| Capacity bằng arrival rate | Backlog không giảm | Đảm bảo \(\mu>\lambda\) và có headroom |
| Dùng throughput poll/fetch làm consumer capacity | Bỏ qua processing và commit | Đo record xử lý thành công end-to-end |
| Chỉ nhìn tổng lag | Bỏ sót hot partition | Tính \(T_i\) cho từng partition |
| Tăng consumer vượt partition count | Instance dư không nhận partition | Kiểm tra assignment; cân nhắc partition strategy |
| Scale consumer khi database đã bão hòa | Retry, timeout và queue tăng | Tăng downstream capacity hoặc điều tiết consumer |
| Coi lag offset là số business record chính xác | Ước lượng sai work còn lại | Đối chiếu record rate, bytes và application metrics |
| Nghĩ retention tự giữ record chưa đọc | Backlog có thể bị xóa trước khi xử lý | Đặt retention vượt outage + restore + catch-up |
| Nhầm RTO với catch-up time | SLA phục hồi không rõ | Định nghĩa riêng service RTO và backlog target |
| Bỏ qua retry/DLT và duplicate | Capacity thực tế thấp hơn benchmark | Benchmark với lỗi và thiết kế idempotency |
| Chỉ benchmark trong vài phút | Không thấy GC, burst và disk pressure | Chạy test đủ dài với traffic gần production |

## 13. Quy trình lập capacity plan

1. Chọn consumer group và topic cần hoạch định; xác định lag theo từng partition.
2. Đo arrival rate theo record/byte trong giờ bình thường, cao điểm và burst.
3. Đo throughput xử lý end-to-end trong môi trường gần production.
4. Tính backlog \(B\), arrival \(\lambda\), capacity \(\mu\) và net drain rate.
5. Xác định catch-up target \(T\), tính \(\mu_{required}=\lambda+B/T\).
6. Cộng headroom và quy đổi thành số worker theo throughput đã benchmark.
7. Kiểm tra partition concurrency, hot key và partition-level drain time.
8. Kiểm tra downstream, broker, network, disk, heap và retention headroom.
9. Kiểm thử outage/scale-out/catch-up và so sánh dự báo với thực tế.
10. Đưa capacity target, RTO, catch-up target và alert vào runbook.

## 14. Checklist production

- Có định nghĩa backlog rõ ràng: committed lag, in-flight work và application queue.
- Có arrival rate và processing rate theo record/byte.
- Công thức drain tính cả producer traffic vẫn tiếp tục đến.
- Năng lực consumer được đo sau khi xử lý và commit thành công.
- Có headroom cho peak, retry, GC, skew và downstream variation.
- Lag và drain time được theo dõi theo partition.
- Consumer count phù hợp partition concurrency và workload semantics.
- Downstream có đủ capacity cho tốc độ catch-up.
- Broker network/disk và replication đủ sức phục vụ consumer tăng tải.
- Retention giữ backlog qua outage, restore và catch-up.
- RTO, RPO và backlog catch-up target được định nghĩa riêng.
- Đã benchmark consumer outage, scale-out, downstream slowdown và retry.
- Có cảnh báo net drain rate không dương và dự báo catch-up vượt mục tiêu.

## Kết luận

Ước lượng thời gian xử lý backlog phải tính cả dữ liệu mới vẫn tiếp tục đi vào Kafka. Với backlog \(B\), arrival rate \(\lambda\) và consumer capacity \(\mu\), thời gian drain gần đúng là \(B/(\mu-\lambda)\), chỉ có ý nghĩa khi \(\mu>\lambda\). Muốn đạt mục tiêu \(T\), năng lực tối thiểu cần có là \(\lambda+B/T\), sau đó cộng headroom phù hợp.

Tổng throughput chưa đủ để chứng minh group sẽ bắt kịp: partition nóng, downstream chậm, retention, broker/network và retry có thể kéo dài thời gian thực tế. Hãy tính theo partition, benchmark end-to-end, phân biệt RTO với catch-up target và xác nhận bằng net drain rate cùng lag trend. Một capacity plan tốt cho biết không chỉ cần bao nhiêu consumer, mà còn chứng minh toàn hệ thống có thể xử lý backlog trong thời gian mục tiêu mà vẫn duy trì durability và SLO.

## Tài liệu tham khảo

- Apache Kafka 4.2 Consumer Configs: https://kafka.apache.org/42/configuration/consumer-configs/
- Apache Kafka 4.2 Monitoring: https://kafka.apache.org/42/operations/monitoring/
- Apache Kafka 4.2 Design — Replication: https://kafka.apache.org/42/design/design/
- Apache Kafka 4.2 Topic Configs: https://kafka.apache.org/42/configuration/topic-configs/
- KafkaConsumer Java API 4.2: https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html
