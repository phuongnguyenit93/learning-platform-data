# Đo thông lượng cùng độ trễ khi tăng số yêu cầu đồng thời

Khi nhiều yêu cầu truy cập cơ sở dữ liệu cùng lúc, hệ thống có thể xử lý được nhiều giao dịch hơn nhờ tận dụng CPU, I/O và khả năng song song. Nhưng khi tài nguyên hoặc điểm chia sẻ bị bão hòa, việc tăng số yêu cầu đồng thời có thể làm hàng đợi dài hơn, thời gian chờ khóa tăng, độ trễ p95/p99 xấu đi và thông lượng không còn tăng tương ứng. Vì vậy, đánh giá hiệu năng cần đo đồng thời **thông lượng**, **độ trễ**, **mức đồng thời**, **tỷ lệ lỗi** và **tài nguyên** trong một workload có thể lặp lại.

Bài học thuộc chương **Giao dịch và tranh chấp** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Do đó, phép đo đồng thời trong bài không chỉ nhằm tìm số giao dịch tối đa mà còn giúp nhận ra thời điểm tranh chấp và hàng đợi bắt đầu làm giảm trải nghiệm, từ đó kiểm chứng thay đổi một cách có căn cứ.

## 1. Ba đại lượng cần phân biệt

### 1.1. Thông lượng (throughput)

Thông lượng là lượng công việc hoàn thành trong một đơn vị thời gian. Với cơ sở dữ liệu, có thể đo bằng:

- Transactions per second (TPS): số giao dịch hoàn tất mỗi giây.
- Queries per second (QPS): số câu truy vấn hoàn tất mỗi giây.
- Requests per second: số yêu cầu ứng dụng hoàn tất mỗi giây.
- Rows processed per second hoặc bytes/sec: hữu ích với workload xử lý khối lượng dữ liệu lớn.

Phải định nghĩa chính xác một đơn vị công việc. Một request có thể chứa nhiều câu SQL; một transaction có thể thực hiện nhiều thao tác đọc/ghi. Không nên so sánh TPS của hai bài thử nếu mỗi transaction có số câu lệnh hoặc mức công việc khác nhau.

Thông lượng cần tính trên công việc **hoàn tất thành công**, đồng thời báo cáo riêng lỗi, timeout và rollback. Nếu bộ tạo tải gửi 10.000 yêu cầu mỗi giây nhưng chỉ có 6.000 yêu cầu hoàn tất, không thể báo cáo hệ thống đạt 10.000 requests/sec.

### 1.2. Độ trễ (latency)

Độ trễ là thời gian từ lúc một yêu cầu bắt đầu cho đến khi kết quả hoàn tất theo ranh giới đo đã chọn. Cần xác định đo tại đâu:

- **Client latency:** thời gian bộ tạo tải hoặc ứng dụng quan sát, gồm thời gian chờ kết nối, mạng, xử lý DB và nhận kết quả.
- **Database execution time:** thời gian DB thực thi câu lệnh hoặc transaction theo cách hệ quản trị ghi nhận.
- **Queue/wait time:** thời gian chờ lấy connection, chờ khóa, chờ I/O, chờ worker hoặc chờ tài nguyên khác.

Độ trễ nên được báo cáo bằng phân vị, không chỉ bằng trung bình:

| Chỉ số | Ý nghĩa |
|---|---|
| p50 | Một nửa yêu cầu hoàn tất trong thời gian bằng hoặc thấp hơn giá trị này |
| p90 | 90% yêu cầu hoàn tất trong thời gian bằng hoặc thấp hơn giá trị này |
| p95 | Phản ánh phần đuôi chậm của 5% yêu cầu lâu nhất |
| p99 | Phản ánh phần đuôi rất chậm; nhạy với hàng đợi, tranh chấp và ngoại lệ |
| max | Độ trễ lớn nhất quan sát được; dễ bị ảnh hưởng bởi ngoại lệ đơn lẻ |

Hai hệ thống có cùng độ trễ trung bình có thể có p99 rất khác nhau. Với dịch vụ tương tác, phần đuôi thường quan trọng vì nó ảnh hưởng trực tiếp đến người dùng và timeout ở tầng gọi.

### 1.3. Mức đồng thời (concurrency)

Concurrency là số yêu cầu, phiên hoặc giao dịch đang hoạt động cùng một thời điểm theo định nghĩa của phép đo. Nó khác với tốc độ gửi yêu cầu (arrival rate/offered load).

Ví dụ:

- 100 client liên tục gửi yêu cầu có thể tạo ra mức đồng thời thay đổi tùy thời gian xử lý.
- 100 yêu cầu/giây không có nghĩa là luôn có 100 yêu cầu đang chạy.
- 100 connection trong pool không có nghĩa 100 transaction đang thực hiện công việc hữu ích.

Khi độ trễ tăng, cùng một tốc độ gửi yêu cầu có thể làm số yêu cầu đang chờ tăng lên. Vì vậy, phải ghi nhận cả số client, số request đang in-flight, số connection đang hoạt động và số transaction thực sự chạy trên DB nếu có thể.

## 2. Mối quan hệ giữa concurrency, latency và throughput

Trong điều kiện tải ổn định, định luật Little mô tả quan hệ:

```text
L = λ × W
```

Trong đó:

- `L` là số yêu cầu trung bình đang ở trong hệ thống (số yêu cầu in-flight).
- `λ` là tốc độ hoàn tất trung bình trong trạng thái ổn định (throughput).
- `W` là thời gian trung bình một yêu cầu ở trong hệ thống (latency).

Ví dụ, nếu hệ thống hoàn tất trung bình 200 request/giây và mỗi request mất trung bình 0,25 giây, số request trung bình đang ở trong hệ thống xấp xỉ 50. Đây là quan hệ trung bình trong một hệ thống ổn định, không phải công thức dự báo p95 hoặc giới hạn concurrency tối đa.

Khi tải tăng, throughput ban đầu thường tăng vì tài nguyên chưa được sử dụng hết. Sau một điểm, một tài nguyên trở thành nút thắt. Hàng đợi bắt đầu tăng nhanh; latency tăng mạnh trong khi throughput tăng ít hoặc đứng yên. Nếu tiếp tục tăng tải, hệ thống có thể timeout, từ chối kết nối, retry dồn dập hoặc giảm cả throughput.

Mô hình khái quát:

```text
Throughput
   ^                    _________ vùng bão hòa
   |                ___/
   |             __/
   |          __/
   |       __/
   |______/
   +--------------------------------> Offered load / concurrency
             điểm bão hòa

Latency
   ^                              /
   |                            _/
   |                         __/
   |                     ___/
   |____________________/
   +--------------------------------> Offered load / concurrency
             điểm bão hòa
```

Đường cong thực tế phụ thuộc workload, phần cứng, cache, connection pool, isolation level, cấu trúc truy vấn và mức tranh chấp. Mục tiêu của bài thử là đo được vùng tăng trưởng, vùng bão hòa và giới hạn vận hành, không giả định hệ thống luôn có đường cong giống hình minh họa.

## 3. Xác định workload trước khi tăng tải

Một bài thử tải chỉ có ý nghĩa nếu công việc được tạo ra gần với hoạt động cần phục vụ. Trước khi chạy, mô tả workload:

- Tỷ lệ đọc/ghi và loại transaction.
- Số câu SQL trong mỗi transaction và thứ tự thực hiện.
- Phân bố tham số: giá trị phổ biến, hiếm, nóng và lạnh.
- Kích thước kết quả, số hàng đọc/ghi và kích thước payload.
- Tỷ lệ commit, rollback, lỗi nghiệp vụ và retry.
- Mức đồng thời dự kiến trong giờ bình thường, giờ cao điểm và đợt tăng đột biến.
- Phân bố tenant, tài khoản hoặc khóa dữ liệu để thể hiện mức độ tập trung truy cập.
- Tần suất transaction dài, batch job và truy vấn báo cáo chạy cùng OLTP.

Không dùng một truy vấn đọc đơn giản để đại diện cho hệ thống có nhiều transaction ghi. Một workload chỉ đọc có thể không bộc lộ tranh chấp khóa, chi phí cập nhật index, log flush hoặc xung đột trên một hàng nóng.

### 3.1. Tạo workload hỗn hợp

Giả sử một ứng dụng bán hàng có các thao tác:

| Loại transaction | Tỷ lệ giả định | Công việc |
|---|---:|---|
| Xem thông tin sản phẩm | 50% | Đọc theo `product_id`, lấy giá và tồn kho |
| Tra cứu đơn hàng | 25% | Đọc theo `customer_id` và thời gian |
| Tạo đơn hàng | 15% | Ghi order, order items và cập nhật tồn kho |
| Cập nhật trạng thái | 8% | Cập nhật một đơn hàng hoặc một nhóm trạng thái |
| Báo cáo ngắn | 2% | Tổng hợp dữ liệu trong một khoảng thời gian |

Các tỷ lệ chỉ là ví dụ. Khi có dữ liệu telemetry, hãy dùng tỷ lệ quan sát thực tế hoặc tạo một profile có lý do rõ ràng. Một bài thử có tỷ lệ đọc/ghi khác xa production có thể cho kết quả throughput và contention không đại diện.

### 3.2. Phân bố dữ liệu và hot keys

Nếu mọi client truy cập các khóa khác nhau, tranh chấp có thể thấp. Nếu tất cả cùng cập nhật một tài khoản, một sản phẩm hoặc một hàng tổng hợp, hàng đó có thể trở thành hot row. Cần thử cả:

- Phân bố đều trên nhiều khóa.
- Phân bố lệch, một số khóa được truy cập thường xuyên.
- Một hot key có chủ đích để kiểm tra giới hạn tranh chấp.
- Dữ liệu mới trong cache và dữ liệu lớn hơn cache.

Đừng chỉ dùng dữ liệu ngẫu nhiên đồng đều nếu production có phân bố lệch. Ngược lại, nếu muốn cô lập một điểm tranh chấp, phải ghi rõ đây là bài thử stress có chủ đích, không phải đại diện cho tỷ lệ tải bình thường.

## 4. Hai mô hình tạo tải: closed-loop và open-loop

### 4.1. Closed-loop (số client cố định)

Trong mô hình closed-loop, mỗi client gửi một yêu cầu, chờ yêu cầu hoàn tất rồi mới gửi yêu cầu tiếp theo. Số client hoạt động được giữ tương đối cố định.

Ví dụ: 50 virtual users liên tục thực hiện transaction; mỗi user chỉ bắt đầu transaction mới sau khi transaction trước kết thúc.

Ưu điểm:

- Dễ kiểm soát số client và mức đồng thời.
- Phù hợp mô phỏng một nhóm người dùng luôn có thao tác tiếp theo.
- Khi DB chậm, tốc độ gửi tự giảm theo thời gian phản hồi.

Giới hạn: nếu hệ thống chậm, chính bộ tạo tải cũng giảm tốc độ phát sinh công việc. Điều này có thể che giấu hiện tượng quá tải vì offered load không còn giữ nguyên trong lúc latency tăng. Một hệ thống có thể trông ổn định hơn trong closed-loop so với dịch vụ thực tế nhận request theo tốc độ bên ngoài.

### 4.2. Open-loop (tốc độ đến được định trước)

Trong mô hình open-loop, bộ tạo tải phát sinh yêu cầu theo một tốc độ đến đã định, độc lập với việc yêu cầu trước đã hoàn tất hay chưa. Ví dụ phát 500 request/giây trong một khoảng thời gian.

Ưu điểm:

- Phù hợp kiểm tra hệ thống trước một offered load cụ thể.
- Có thể quan sát hàng đợi tăng khi tốc độ đến vượt khả năng xử lý.
- Hữu ích cho workload có tốc độ request từ người dùng hoặc hệ thống ngoài tương đối độc lập với latency DB.

Giới hạn: nếu tốc độ đến vượt xa khả năng xử lý, số yêu cầu in-flight và bộ nhớ hàng đợi có thể tăng không giới hạn. Bộ tạo tải cần có giới hạn, cơ chế backpressure và cách dừng an toàn. Không được để công cụ load test tự trở thành nút thắt CPU, mạng hoặc bộ nhớ.

### 4.3. Chọn mô hình phù hợp

| Đặc điểm | Closed-loop | Open-loop |
|---|---|---|
| Điều khiển chính | Số client/worker cố định | Tốc độ đến yêu cầu |
| Khi hệ thống chậm | Client chờ, tốc độ gửi tự giảm | Offered load tiếp tục theo lịch |
| Dễ quan sát | Năng lực xử lý theo mức client | Khả năng đáp ứng một tốc độ tải cụ thể |
| Rủi ro diễn giải | Có thể che giấu hàng đợi do tải tự giảm | Có thể tạo backlog lớn nếu không giới hạn |
| Phù hợp | Mô phỏng người dùng tuần tự hoặc benchmark concurrency | Dịch vụ nhận request theo tốc độ bên ngoài, kiểm tra saturation |

Không có mô hình nào luôn đúng. Với hệ thống thực tế, có thể cần cả hai: closed-loop để khảo sát khả năng xử lý theo số worker và open-loop để kiểm tra SLO ở offered load mục tiêu.

## 5. Thiết kế các mức concurrency

Không nên chỉ chạy một mức tải cao nhất. Hãy tăng dần theo các nấc để nhận ra điểm bắt đầu bão hòa.

Ví dụ một ma trận thử nghiệm:

| Lượt | Virtual users / workers | Thời gian đo sau warm-up | Mục tiêu |
|---|---:|---:|---|
| A | 1 | 5 phút | Baseline một client |
| B | 4 | 5 phút | Tải thấp |
| C | 8 | 5 phút | Tải vừa |
| D | 16 | 5 phút | Tăng đồng thời |
| E | 32 | 5 phút | Gần tải cao |
| F | 64 | 5 phút | Quan sát vùng bão hòa |
| G | 96 | 5 phút | Chỉ chạy nếu hệ thống và môi trường cho phép |

Các con số chỉ là ví dụ; mức tăng nên phù hợp giới hạn connection, CPU, bộ nhớ, I/O và chính sách môi trường. Có thể tăng theo cấp số nhân ở giai đoạn khảo sát rồi bổ sung các nấc nhỏ quanh điểm bão hòa.

Ở mỗi mức, giữ nguyên workload, dữ liệu, thời gian đo và cách warm-up. Ghi số request hoàn tất, offered load, latency percentiles, error rate, active connections, lock waits và tài nguyên. Không thay đổi cùng lúc số client, tỷ lệ đọc/ghi và cấu hình DB nếu muốn xác định tác động của concurrency.

### 5.1. Ramp-up và bước tăng tải

Ramp-up là khoảng thời gian tăng dần số client hoặc tốc độ đến để tránh tạo một cú spike nhân tạo. Có thể tăng từng nhóm nhỏ trong 1-3 phút rồi giữ mức ổn định trước khi đo. Với thử nghiệm stress, có thể thêm bước tăng nhanh để xem phản ứng khi tải đột biến, nhưng cần tách khỏi phép đo steady-state.

### 5.2. Warm-up và steady state

Kết quả đầu tiên có thể bị ảnh hưởng bởi:

- Cache dữ liệu và cache kế hoạch chưa nóng.
- Connection pool vừa mở kết nối.
- JIT/compile hoặc chuẩn bị statement.
- Autovacuum, checkpoint, log rotation hoặc tác vụ nền.
- Bộ tạo tải chưa đạt tốc độ phát sinh ổn định.

Chạy warm-up riêng rồi mới bắt đầu cửa sổ đo. Không loại bỏ các đợt chậm bất thường nếu chúng là một phần của trải nghiệm production; hãy phân biệt thời gian khởi động với trạng thái ổn định và báo cáo riêng.

## 6. Đo latency đúng cách và tránh coordinated omission

Một bộ tạo tải closed-loop có thể không ghi nhận các yêu cầu lẽ ra được gửi trong lúc hệ thống đang quá chậm. Khi một request mất 2 giây, client chờ 2 giây trước khi gửi request kế tiếp; công cụ không ghi lại độ trễ của những request bị trì hoãn vì chưa được phát sinh. Hiện tượng này thường được gọi là **coordinated omission** và có thể làm histogram latency trông tốt hơn thực tế của một hệ thống nhận tải độc lập.

Để giảm rủi ro:

- Chọn open-loop hoặc công cụ hỗ trợ lịch phát sinh cố định khi cần kiểm tra offered load.
- Ghi cả scheduled time, actual start time và completion time nếu công cụ hỗ trợ.
- Theo dõi số yêu cầu bị trễ lịch, backlog, dropped requests và timeout.
- Không chỉ dựa vào latency của những request đã hoàn tất; báo cáo số request chưa hoàn tất hoặc bị loại bỏ.
- Xác nhận bộ tạo tải có đủ CPU, mạng và worker để duy trì tốc độ phát sinh.

Open-loop cũng cần giới hạn backlog. Nếu công cụ cố tiếp tục gửi trong khi DB không thể xử lý, phép đo có thể biến thành bài thử khả năng chịu backlog của load generator. Ghi rõ chính sách queue, drop và timeout để người đọc hiểu số liệu.

### 6.1. Histogram và phân vị

Nên lưu histogram latency hoặc dữ liệu đủ để tính phân vị, thay vì chỉ ghi trung bình. Histogram cho phép quan sát phần đuôi và so sánh các lượt chạy. Khi gộp nhiều worker hoặc nhiều instance, không lấy trung bình các p95 riêng lẻ để suy ra p95 toàn hệ thống; hãy gộp histogram tương thích hoặc dữ liệu mẫu theo cách đúng.

### 6.2. Timeout và request chưa hoàn tất

Một request timeout không có nghĩa DB chưa thực hiện transaction. Client có thể đã gửi lệnh, DB có thể đang chạy hoặc đã commit nhưng phản hồi bị mất. Khi retry, ứng dụng có thể tạo giao dịch lặp nếu thao tác không idempotent. Trong bài thử tải, cần phân biệt:

- Timeout trước khi gửi lệnh.
- Timeout khi chờ lấy connection.
- Timeout trong khi DB đang thực thi.
- Client timeout sau khi DB đã commit nhưng trước khi nhận phản hồi.

Ghi nhận timeout, lỗi kết nối, deadlock, serialization failure và rollback riêng. Không gộp mọi lỗi thành một chỉ số error chung nếu cần chẩn đoán nguyên nhân.

## 7. Đo thông lượng thành công và offered load

Mỗi lượt thử nên ghi tối thiểu:

- Offered load: số yêu cầu được lên lịch/phát sinh mỗi giây.
- Completed throughput: số yêu cầu hoàn tất thành công mỗi giây.
- Failed throughput: số yêu cầu lỗi, timeout hoặc bị từ chối mỗi giây.
- In-flight/backlog: số yêu cầu đang chạy hoặc chờ xử lý.
- Latency distribution: p50, p90, p95, p99 và max nếu có.

Ví dụ:

| Offered load | Completed/s | Error/s | p95 | Backlog cuối lượt |
|---:|---:|---:|---:|---:|
| 100 req/s | 100 | 0 | 40 ms | 0 |
| 200 req/s | 198 | 2 | 55 ms | 5 |
| 300 req/s | 270 | 30 | 180 ms | 120 |
| 400 req/s | 275 | 125 | 900 ms | 1.800 |

Đây là số liệu giả định để minh họa. Ở mức 400 req/s, offered load tăng nhưng throughput hoàn tất gần như không tăng; p95, lỗi và backlog đều tăng. Đây là dấu hiệu hệ thống đã vượt vùng tải ổn định. Không nên công bố 400 req/s là năng lực phục vụ thành công.

## 8. Theo dõi tài nguyên và dấu hiệu tranh chấp

Thông lượng và độ trễ cho biết hệ thống đang hành xử thế nào; các chỉ số tài nguyên giúp tìm lý do.

### 8.1. CPU

Theo dõi CPU tổng, CPU theo tiến trình DB, CPU theo query nếu có, run queue và thời gian chờ CPU. CPU cao có thể đến từ:

- Nhiều truy vấn thực hiện quá nhiều phép tính hoặc đọc hàng.
- Sort/hash/aggregate tốn CPU.
- Plan compile/recompile quá thường xuyên.
- Retry hoặc vòng lặp ở ứng dụng làm tăng request không hữu ích.
- Quá nhiều worker song song gây cạnh tranh scheduling.

CPU thấp không đồng nghĩa DB còn nhiều năng lực. Hệ thống có thể bị giới hạn bởi lock, I/O, connection pool, log flush hoặc một điểm tuần tự hóa.

### 8.2. I/O và bộ nhớ

Theo dõi logical reads, physical reads, IOPS, throughput, latency lưu trữ, queue depth, buffer/cache hit và temp I/O. Nếu tăng concurrency làm p95 tăng cùng read latency hoặc temp spill, nút thắt có thể nằm ở storage hoặc bộ nhớ.

Theo dõi memory grant, sort/hash spill, buffer pool, page cache, swap và áp lực bộ nhớ. Tăng concurrency làm nhiều truy vấn cần bộ nhớ cùng lúc; một query chạy riêng có thể không spill nhưng nhiều query đồng thời có thể tranh chấp grant và ghi tạm.

### 8.3. Connection pool và worker

Ghi nhận số connection mở, active, idle, số request chờ pool, thời gian lấy connection và giới hạn worker của DB. Tăng connection không phải lúc nào cũng tăng throughput. Quá nhiều phiên có thể làm tăng context switching, memory per session, lock contention và cạnh tranh CPU/I/O.

Hãy phân biệt:

- Client/virtual users.
- Connection pool size.
- Connection đang giữ transaction.
- Session đang chạy câu lệnh.
- Worker thực thi song song bên trong DB.

Các con số này có quan hệ nhưng không bằng nhau. Đặc biệt, transaction mở lâu nhưng không chạy câu SQL vẫn có thể giữ lock hoặc snapshot và gây tác động lên hệ thống.

### 8.4. Lock waits và blocking

Theo dõi thời gian chờ khóa, số session bị block, blocking chain, deadlock, lock escalation hoặc wait events tương ứng. Nếu throughput đứng yên trong khi lock wait tăng nhanh, hệ thống có thể bị giới hạn bởi một số hàng/bảng nóng hoặc transaction giữ khóa quá lâu.

Hãy xác định:

- Tài nguyên bị khóa: row/key, page, table, metadata hay đối tượng khác.
- Session giữ khóa và câu SQL đang chạy.
- Transaction giữ khóa bao lâu.
- Số session chờ và thời gian chờ.
- Có vòng chờ deadlock hay chỉ một chuỗi blocking.
- Isolation level và access pattern có làm tăng phạm vi khóa hoặc thời gian giữ snapshot không.

Không kết luận “DB chậm vì lock” chỉ từ một wait event đơn lẻ. Ghép thời điểm lock wait với latency, throughput và query đang giữ khóa.

## 9. Thiết kế phép đo tranh chấp giao dịch

Để kiểm tra một điểm nóng, tạo các profile có chủ đích:

### 9.1. Baseline không tranh chấp đáng kể

Cho mỗi worker cập nhật các khóa khác nhau hoặc đọc các vùng dữ liệu tách biệt. Phép đo này giúp xác định mức năng lực khi không có hot row lớn. Ghi throughput, latency, CPU, I/O và số lock wait.

### 9.2. Tranh chấp trên một khóa nóng

Cho nhiều worker cập nhật cùng một hàng hoặc cùng một khóa logic. Ví dụ nhiều transaction cùng trừ tồn kho của một sản phẩm có lượng bán rất cao. Theo dõi thời gian chờ khóa, blocking, deadlock, throughput và p99.

Không dùng một hot key duy nhất để suy ra mọi workload. Đây là stress case nhằm xác định giới hạn và kiểm tra cơ chế đồng bộ.

### 9.3. Tranh chấp theo phạm vi

Thử nhiều worker cập nhật các hàng khác nhau nhưng nằm cùng một page, cùng index range hoặc cùng partition. Một số hệ quản trị có latch, page-level contention hoặc metadata contention dù các khóa logic khác nhau. So sánh với trường hợp các hàng phân tán để nhận biết điểm nóng ở cấu trúc lưu trữ.

### 9.4. Transaction ngắn và dài

Giữ cùng số thao tác nhưng thay đổi thời gian transaction hoặc thêm một khoảng chờ có kiểm soát trong transaction ở môi trường thử nghiệm. Quan sát thời gian giữ khóa, số session bị block và độ trễ của transaction khác.

Không đưa sleep tùy tiện vào transaction production. Bài thử cần giới hạn phạm vi và có mục tiêu rõ ràng. Kết quả giúp thấy vì sao giữ transaction lâu, gọi API bên ngoài trong transaction hoặc chờ người dùng giữa các thao tác có thể khuếch đại contention.

## 10. Isolation level, retry và tính đúng đắn

Concurrency test phải giữ nguyên hoặc ghi rõ isolation level, vì nó ảnh hưởng cách transaction nhìn dữ liệu và cơ chế khóa/phiên bản.

- Isolation thấp hơn có thể giảm một số loại chờ nhưng cho phép anomaly mà nghiệp vụ có thể không chấp nhận.
- Isolation cao hơn có thể phát sinh nhiều blocking hoặc serialization failures tùy hệ quản trị và workload.
- MVCC giảm một số xung đột đọc/ghi nhưng không loại bỏ mọi tranh chấp ghi, lock hoặc vacuum/version cleanup.
- Retry có thể giúp xử lý deadlock hoặc serialization failure, nhưng retry dồn dập có thể khuếch đại tải khi hệ thống đang bão hòa.

Không giảm isolation level chỉ để làm benchmark đẹp hơn. Mọi thay đổi cần giữ nguyên các bất biến nghiệp vụ và được kiểm tra bằng test tính đúng đắn đồng thời.

### 10.1. Retry có backoff và giới hạn

Nếu ứng dụng retry ngay lập tức sau deadlock hoặc lỗi tạm thời, nhiều client có thể cùng retry tại một thời điểm và tạo thêm tải. Cơ chế thường cần:

- Chỉ retry những lỗi được xác định là có thể retry.
- Giới hạn số lần thử.
- Dùng exponential backoff và jitter phù hợp.
- Đảm bảo thao tác idempotent hoặc có idempotency key.
- Theo dõi số retry và tổng thời gian đến khi thành công.

Trong load test, ghi cả lần thử ban đầu và retry. Nếu chỉ tính transaction thành công cuối cùng mà bỏ qua số lần thử, hệ thống có thể trông có throughput tốt nhưng đang tiêu tốn nhiều tài nguyên cho retry.

## 11. Xác định điểm bão hòa và năng lực vận hành

Điểm bão hòa là vùng mà tăng offered load hoặc concurrency không còn đem lại throughput tăng tương ứng, trong khi latency, backlog hoặc lỗi tăng rõ rệt. Không nhất thiết có một điểm duy nhất: workload đọc, ghi, báo cáo và hot-key có thể bão hòa ở mức khác nhau.

Một quy trình xác định:

1. Bắt đầu ở tải thấp và xác nhận số liệu đo đáng tin cậy.
2. Tăng concurrency hoặc offered load theo từng nấc.
3. Giữ mỗi nấc đủ lâu để đạt trạng thái ổn định.
4. Ghi throughput thành công, p50/p95/p99, error rate và backlog.
5. Ghi CPU, I/O, memory, connection, lock waits và log flush.
6. Tìm vùng throughput bắt đầu đi ngang trong khi latency hoặc lỗi tăng nhanh.
7. Lặp lại quanh vùng đó với bước tải nhỏ hơn.
8. Xác định mức tải vận hành có headroom, không lấy điểm cực đại làm tải mục tiêu.

### 11.1. Throughput tối đa không phải capacity an toàn

Nếu hệ thống đạt 1.000 transaction/giây ở p99 5 giây và error rate 8%, đó không phải năng lực phục vụ phù hợp cho dịch vụ có SLO p99 dưới 300 ms và lỗi dưới 0,1%. Năng lực an toàn phải thỏa các giới hạn dịch vụ và có khoảng dự phòng cho biến động, batch job, failover và tăng trưởng.

Có thể định nghĩa capacity theo điều kiện đồng thời:

- p95/p99 không vượt SLO.
- Error/timeout/deadlock rate nằm trong ngưỡng.
- Backlog không tăng liên tục.
- Tài nguyên còn headroom cần thiết.
- Throughput thành công ổn định trong khoảng đo.

### 11.2. Headroom và tải đỉnh

Không vận hành liên tục sát điểm bão hòa. Cần dự phòng cho burst, sự cố một node, backup, replication lag, tác vụ bảo trì và thay đổi phân bố truy vấn. Headroom nên được xác định bằng thử nghiệm và yêu cầu availability, không lấy một tỷ lệ cố định áp dụng cho mọi hệ thống.

## 12. Quy trình benchmark có thể lặp lại

Một bài đo có thể tổ chức theo các giai đoạn sau:

### Giai đoạn A: Chuẩn bị

- Xác định câu hỏi cần trả lời: throughput tối đa, latency tại tải mục tiêu hay điểm contention?
- Ghi phiên bản DB, cấu hình, phần cứng, storage, schema, index và isolation level.
- Chuẩn bị dữ liệu có kích thước và phân bố đại diện.
- Xác định workload, tỷ lệ transaction và bộ tham số.
- Kiểm tra load generator, network và connection pool không phải nút thắt.
- Xác định giới hạn an toàn, thời gian dừng và người theo dõi.

### Giai đoạn B: Baseline

- Chạy workload ở concurrency thấp.
- Warm-up và xác nhận cache/connection ổn định.
- Đo latency distribution, completed throughput, lỗi và tài nguyên.
- Lưu execution plan cho các truy vấn chính nếu có thể lấy an toàn.
- Ghi số liệu nền của DB và load generator.

### Giai đoạn C: Tăng tải

- Tăng từng nấc concurrency hoặc offered load.
- Giữ nguyên tỷ lệ workload, tham số và thời lượng đo.
- Chờ mỗi nấc ổn định, sau đó ghi cùng bộ chỉ số.
- Dừng nếu vượt ngưỡng lỗi, backlog hoặc tài nguyên đã định.
- Ghi lại mọi thay đổi môi trường hoặc tác vụ nền.

### Giai đoạn D: Lặp lại và xác nhận

- Lặp lại các mức quan trọng để đánh giá độ biến động.
- Nếu kết quả bất thường, chạy lại sau khi xác định nguyên nhân, không xóa bỏ dữ liệu bất lợi.
- So sánh cùng phiên bản, dữ liệu, tham số và cách khởi tạo cache.
- Phân biệt warm cache và cold cache nếu cả hai có ý nghĩa.

### Giai đoạn E: Phân tích và báo cáo

- Vẽ throughput và latency theo offered load/concurrency.
- Đánh dấu vùng bắt đầu bão hòa.
- Ghép thời điểm p99 tăng với CPU, I/O, lock wait, memory và connection queue.
- Phân loại bottleneck theo bằng chứng.
- Nêu giới hạn, số lượt chạy, số mẫu, sai khác và độ tin cậy của kết luận.

## 13. Mẫu bảng ghi kết quả

Một bảng ghi chép nên chứa đủ thông tin để người khác hiểu phép đo:

| Mức tải | Offered/s | Success/s | Error % | p50 | p95 | p99 | CPU | Lock wait | I/O latency |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 workers |  |  |  |  |  |  |  |  |  |
| 8 workers |  |  |  |  |  |  |  |  |  |
| 16 workers |  |  |  |  |  |  |  |  |  |
| 32 workers |  |  |  |  |  |  |  |  |  |
| 64 workers |  |  |  |  |  |  |  |  |  |

Ngoài bảng tổng hợp, lưu histogram latency, log lỗi, số request in-flight, số connection active/waiting, số transaction commit/rollback và snapshot metrics theo thời gian. Nếu có nhiều loại transaction, ghi riêng từng loại; latency trung bình toàn workload có thể che giấu một loại giao dịch chậm.

### 13.1. Mẫu báo cáo benchmark

```text
Tên phép thử:
Mục tiêu:
Thời gian và môi trường:
DB engine/version:
CPU/RAM/storage/network:
Schema/index/statistics:
Isolation level:
Dataset size/distribution:
Workload mix:
Parameter distribution:
Load model: closed-loop / open-loop
Ramp-up:
Warm-up:
Measurement window:
Concurrency / offered load:
Completed throughput:
Latency p50/p95/p99:
Errors/timeouts/retries:
Backlog / in-flight:
CPU / memory / I/O:
Connections / worker utilization:
Lock waits / deadlocks:
Execution plans / query metrics:
Saturation point:
Safe operating range:
Limitations and deviations:
Conclusion / next experiment:
```

## 14. Đọc kết quả và tìm nguyên nhân

### 14.1. Throughput tăng, latency gần như ổn định

Hệ thống có thể vẫn còn năng lực và đang tận dụng thêm tài nguyên. Tiếp tục tăng tải có kiểm soát để xác định vùng bắt đầu bão hòa. Không dừng chỉ vì throughput đạt một con số mong muốn nếu chưa kiểm tra p99 và lỗi.

### 14.2. Throughput đi ngang, latency tăng mạnh

Đây là dấu hiệu điển hình của bão hòa hoặc hàng đợi. Hãy xem tài nguyên nào đã chạm giới hạn và yêu cầu đang chờ ở đâu. Nếu CPU cao và run queue tăng, có thể là CPU bottleneck. Nếu lock waits tăng, tìm hot row và blocking chain. Nếu I/O latency và queue depth tăng, xem storage. Nếu thời gian chờ pool tăng nhưng DB còn rảnh, có thể connection pool hoặc tầng ứng dụng là nút thắt.

### 14.3. Throughput giảm khi concurrency tiếp tục tăng

Có thể xảy ra khi context switching, lock contention, memory pressure, retry storm, connection overload hoặc I/O queue làm hệ thống kém hiệu quả hơn. Kiểm tra error rate, deadlock, timeout, số retry và các wait events theo cùng cửa sổ thời gian.

### 14.4. p99 tăng nhưng p50 gần như không đổi

Điều này cho thấy phần lớn request vẫn nhanh, nhưng một nhóm nhỏ gặp hàng đợi hoặc đường xử lý chậm. Tìm phân bố theo query type, parameter, tenant, partition, lock resource và thời điểm. Một số truy vấn báo cáo hoặc transaction dài có thể gây tail latency cho các yêu cầu ngắn khác.

### 14.5. CPU thấp nhưng throughput không tăng

Kiểm tra lock, log flush, storage latency, connection pool, giới hạn worker, network và các tài nguyên tuần tự hóa. CPU thấp có thể là hệ quả của nhiều session đang chờ, không phải dấu hiệu còn nhiều capacity hữu ích.

## 15. Phân biệt bottleneck của DB và load generator

Bộ tạo tải có thể hết CPU, bộ nhớ, socket hoặc băng thông mạng trước DB. Khi đó throughput không tăng dù DB còn năng lực.

Theo dõi trên máy phát tải:

- CPU và run queue.
- Bộ nhớ, garbage collection và số worker.
- Socket, network throughput, retransmission và connection errors.
- Tốc độ tạo request thực tế so với lịch dự kiến.
- Thời gian xử lý phía client và overhead serialization.
- Số connection và queue nội bộ của công cụ.

Nếu có thể, phân tán load generator qua nhiều máy hoặc tăng tài nguyên theo cách kiểm soát. Không tăng số generator mà không ghi nhận vì điều đó làm thay đổi topology và có thể thay đổi network path.

## 16. An toàn và tính đúng đắn khi load test

Load test có thể tạo ghi dữ liệu, khóa, log, backup và chi phí lưu trữ. Trước khi chạy:

- Ưu tiên môi trường thử nghiệm có dữ liệu và cấu hình đại diện.
- Không chạy stress test không giới hạn trên production.
- Xác định trước giới hạn concurrency, offered load, error rate và backlog để dừng.
- Dùng dữ liệu giả lập hoặc đã ẩn danh theo chính sách.
- Xác định cách dọn dữ liệu test và tránh ảnh hưởng dữ liệu nghiệp vụ.
- Kiểm tra transaction có rollback đúng và thao tác có idempotent không.
- Theo dõi replication lag, log growth, storage capacity và tác vụ nền.
- Chuẩn bị người vận hành và quy trình dừng nếu DB hoặc dịch vụ vượt ngưỡng.

Với transaction ghi, kiểm tra tính đúng đắn sau tải: không mất cập nhật, không trừ tồn kho quá mức, không tạo giao dịch trùng và các constraint vẫn được giữ. Throughput cao nhưng dữ liệu sai là kết quả thất bại.

## 17. Ví dụ thực hành: tìm vùng bão hòa của API đặt hàng

Giả sử API đặt hàng thực hiện trong một transaction:

1. Đọc tồn kho của sản phẩm.
2. Kiểm tra số lượng có thể bán.
3. Tạo đơn hàng và dòng đơn hàng.
4. Giảm tồn kho.
5. Commit.

Một bài thử cần dùng nhiều sản phẩm và khách hàng, nhưng cũng có nhóm sản phẩm nóng. Tăng mức client theo các nấc, dùng cùng phân bố tham số và ghi nhận success throughput, p95/p99, deadlock, lock wait, CPU, log flush, I/O và connection pool.

Giả sử số liệu minh họa:

| Workers | Success TPS | p95 | Deadlock/min | Lock wait trung bình |
|---:|---:|---:|---:|---:|
| 4 | 180 | 45 ms | 0 | 1 ms |
| 8 | 330 | 52 ms | 0 | 2 ms |
| 16 | 520 | 85 ms | 1 | 8 ms |
| 32 | 550 | 260 ms | 8 | 65 ms |
| 64 | 548 | 780 ms | 22 | 210 ms |

Trong ví dụ này, throughput gần như đi ngang từ 32 workers, trong khi p95 và lock wait tăng mạnh. Đây là dấu hiệu contention có thể đang giới hạn hệ thống. Cần kiểm tra blocking chain, khóa trên hàng tồn kho, thời gian transaction và phân bố hot product. Có thể thử một thay đổi riêng như giảm thời gian giữ transaction hoặc phân phối truy cập, sau đó chạy lại cùng workload để xác nhận.

Không nên chỉ tăng connection pool hoặc worker lên 128 vì số client lớn hơn có thể làm hàng đợi và tranh chấp nặng hơn. Hãy xác định tài nguyên bị giới hạn và thử nghiệm từng giả thuyết.

## 18. Các sai lầm thường gặp

- **Chỉ báo cáo TPS:** không cho biết độ trễ và tỷ lệ lỗi mà người dùng phải chịu.
- **Chỉ báo cáo latency trung bình:** che giấu p95/p99 và các nhóm request chậm.
- **Nhầm offered load với completed throughput:** số yêu cầu được gửi không phải số yêu cầu hoàn tất.
- **Nhầm concurrency với requests/sec:** hai đại lượng có quan hệ nhưng không đồng nhất.
- **Chỉ dùng closed-loop:** có thể làm tốc độ phát sinh tự giảm khi DB chậm và đánh giá thấp hàng đợi.
- **Không kiểm soát coordinated omission:** histogram latency có thể trông tốt hơn trải nghiệm của tải đến độc lập.
- **Không warm-up hoặc không tách warm-up:** kết quả bị chi phối bởi cache và khởi tạo.
- **Thay nhiều yếu tố cùng lúc:** không xác định được nguyên nhân cải thiện hoặc suy giảm.
- **Bỏ qua load generator:** công cụ tạo tải có thể là nút thắt.
- **Tăng connection vô hạn:** tăng context switching, bộ nhớ, contention và queue.
- **Không kiểm tra lỗi/retry:** retry storm có thể làm tải tăng mà không tạo thêm công việc hữu ích.
- **Dùng dữ liệu quá sạch hoặc phân bố đều:** bỏ qua hot key và skew trong production.
- **Không xác minh dữ liệu sau bài thử:** throughput cao không đảm bảo transaction đúng.
- **Lấy peak throughput làm capacity an toàn:** bỏ qua SLO, headroom và biến động.

## 19. Bài tập tự kiểm tra

### Bài tập 1: Phân biệt concurrency và throughput

Một bài thử có 40 virtual users. Mỗi user chờ transaction hoàn tất rồi mới gửi tiếp. Hệ thống đạt 200 transaction/giây với latency trung bình 200 ms.

**Câu hỏi:** 40 virtual users có nghĩa là 40 transaction/giây không? Số transaction trung bình đang ở trong hệ thống xấp xỉ bao nhiêu nếu áp dụng Little trong trạng thái ổn định?

**Gợi ý trả lời:** không. 40 là số user/client trong mô hình thử, không phải tốc độ giao dịch. Theo Little, `L = λ × W = 200 × 0,2 = 40` transaction trung bình đang ở trong hệ thống, nếu throughput và latency cùng đo một phạm vi và hệ thống ổn định.

### Bài tập 2: Nhận biết điểm bão hòa

Khi tăng từ 16 lên 32 workers, throughput tăng 3%, p95 tăng gấp 3 và error rate tăng từ 0,1% lên 4%. Khi tăng lên 64 workers, throughput giảm.

**Câu hỏi:** nên xem mức nào là vùng bắt đầu bão hòa và cần kiểm tra gì?

**Gợi ý trả lời:** vùng 32 workers đã có dấu hiệu bão hòa vì throughput gần đi ngang trong khi latency và lỗi tăng mạnh. Kiểm tra CPU, I/O, lock waits, memory, connection queue, retry và backlog; 64 workers thể hiện quá tải rõ hơn. Capacity an toàn cần thấp hơn điểm này và thỏa SLO.

### Bài tập 3: Closed-loop hay open-loop?

Một API nhận request từ nhiều hệ thống ngoài với tốc độ tương đối độc lập với thời gian phản hồi DB. Nhóm benchmark dùng 100 client closed-loop và thấy p99 khá thấp.

**Câu hỏi:** phép đo có thể bỏ sót điều gì? Nên bổ sung thử nghiệm nào?

**Gợi ý trả lời:** khi DB chậm, closed-loop làm client chờ nên offered load tự giảm; có thể không thể hiện hàng đợi khi request đến liên tục. Bổ sung open-loop với tốc độ đến định trước, giới hạn backlog và ghi scheduled/actual start, timeout, dropped request cùng p99.

### Bài tập 4: p99 tăng, CPU thấp

Ở 32 workers, p99 tăng mạnh nhưng CPU DB chỉ 35%. Lock wait và thời gian chờ connection pool tăng.

**Câu hỏi:** có nên tăng CPU hoặc số connection ngay không?

**Gợi ý trả lời:** chưa. Bằng chứng hướng đến khóa hoặc pool queue. Tìm blocking chain, transaction giữ khóa lâu, hot key, pool size và số session thực sự hoạt động. Tăng connection có thể làm contention nặng hơn; cần thử thay đổi có kiểm soát.

### Bài tập 5: Retry làm sai lệch throughput

Một client retry tối đa 5 lần ngay lập tức khi gặp deadlock. Dashboard chỉ tính transaction cuối cùng thành công.

**Câu hỏi:** báo cáo hiện tại thiếu thông tin nào?

**Gợi ý trả lời:** cần ghi số lần thử, deadlock, retry, thời gian đến khi thành công và tổng công việc DB đã thực hiện. Retry tức thời có thể tạo retry storm; cần giới hạn, backoff, jitter và bảo đảm idempotency.

### Checklist trước khi công bố kết quả load test

- [ ] Đã định nghĩa rõ transaction/request được tính trong throughput.
- [ ] Đã phân biệt offered load, completed throughput và failed throughput.
- [ ] Đã ghi concurrency, in-flight, connection pool và session active.
- [ ] Đã mô tả workload mix, phân bố tham số và hot keys.
- [ ] Đã chọn closed-loop/open-loop phù hợp và ghi rõ giới hạn.
- [ ] Đã tách warm-up khỏi cửa sổ đo steady-state.
- [ ] Đã ghi p50, p95, p99, error, timeout, retry và backlog.
- [ ] Đã kiểm tra coordinated omission và năng lực load generator.
- [ ] Đã theo dõi CPU, memory, I/O, lock waits, deadlocks và connection queue.
- [ ] Đã tăng tải theo nấc và xác định vùng bão hòa.
- [ ] Đã xác định capacity theo SLO và headroom, không chỉ peak TPS.
- [ ] Đã kiểm tra tính đúng đắn dữ liệu sau transaction test.
- [ ] Đã lưu môi trường, dữ liệu, tham số, execution plan và giới hạn phép đo.

Đo thông lượng cùng độ trễ khi tăng số yêu cầu đồng thời giúp xác định năng lực thực tế và thời điểm hệ thống bắt đầu bão hòa. Thông lượng chỉ có ý nghĩa khi đi cùng độ trễ, lỗi và backlog; concurrency chỉ có ý nghĩa khi biết mô hình tạo tải; còn nguyên nhân tranh chấp cần được xác nhận bằng lock waits, execution plan và tài nguyên. Một benchmark tốt phải tái hiện workload có chủ đích, kiểm soát điều kiện đo, kiểm tra tính đúng đắn và báo cáo vùng vận hành an toàn theo SLO.
