# Định cỡ tài nguyên dựa trên phép đo và điểm bão hòa

Trong chương **Lưu trữ và tài nguyên** của module **DATABASE_PERFORMANCE**, định cỡ tài nguyên (*capacity sizing*) là quá trình xác định CPU, bộ nhớ, lưu trữ, I/O, kết nối và năng lực xử lý đồng thời cần thiết để database đáp ứng workload với độ trễ và độ tin cậy đã cam kết. Việc định cỡ phải dựa trên tải thực tế, execution plan, thống kê truy cập dữ liệu và kết quả thử tải. Chỉ nhìn số core, dung lượng RAM hoặc IOPS ghi trên cấu hình máy không đủ để biết hệ thống có phục vụ được workload hay không.

Một hệ thống thường hoạt động tốt ở mức tải thấp nhưng tăng độ trễ nhanh khi một tài nguyên tiến gần giới hạn. Điểm mà throughput không còn tăng tương ứng với tải đưa vào, trong khi queue và latency tăng mạnh, được gọi là vùng hoặc điểm bão hòa (*saturation point*). Định cỡ hợp lý là tìm được vùng tải bền vững trước điểm này, giữ đủ headroom cho biến động và tăng trưởng, đồng thời biết tài nguyên nào sẽ trở thành nút thắt tiếp theo khi mở rộng.

## 1. Định cỡ theo workload và SLO

Trước khi chọn cấu hình máy chủ hoặc dịch vụ cloud, hãy mô tả workload cần phục vụ. Hai database có cùng dung lượng dữ liệu có thể cần cấu hình rất khác nếu một bên chủ yếu tra cứu theo khóa, còn bên kia chạy báo cáo quét hàng triệu dòng.

### 1.1. Các đặc trưng workload cần thu thập

- **Throughput:** số transaction, query hoặc request mỗi giây; phân biệt trung bình, giờ cao điểm và burst.
- **Latency:** p50, p95, p99 và timeout của các nhóm truy vấn quan trọng.
- **Read/write mix:** tỷ lệ đọc, insert, update, delete và commit.
- **Query mix:** point lookup, range scan, join, sort, aggregate, báo cáo và batch.
- **Concurrency:** số request đồng thời, connection đang hoạt động, worker và transaction mở.
- **Data volume:** số dòng, kích thước bảng/index, tốc độ tăng trưởng và working set.
- **Data distribution:** skew theo tenant, giá trị phổ biến/hiếm, kích thước giao dịch và phân bố khóa.
- **Temporal pattern:** tải theo giờ, ngày, mùa vụ, chiến dịch, cuối kỳ và thời điểm batch.
- **Operational constraints:** backup, replication, failover, maintenance, retention và thời gian phục hồi.

Không chỉ lấy số liệu trung bình. Ví dụ, tải trung bình 300 transaction/giây có thể che khuất các đợt 1.500 transaction/giây trong 10 phút. Nếu chỉ định cỡ theo trung bình, hệ thống có thể quá tải đúng lúc nghiệp vụ cần phục vụ nhiều nhất.

### 1.2. Xác định SLO trước khi thử tải

SLO (*Service Level Objective*) mô tả mức dịch vụ cần đạt. Ví dụ:

| Chỉ tiêu | Mục tiêu minh họa |
|---|---:|
| API đọc thông tin theo khóa | p95 dưới 100 ms |
| Giao dịch ghi đơn hàng | p95 dưới 250 ms |
| Báo cáo tổng hợp | p95 dưới 5 giây |
| Tỷ lệ timeout/lỗi do quá tải | Dưới 0,1% |
| Tải cao điểm cần phục vụ | 1.000 transaction/giây |
| Thời gian chịu burst | 10 phút ở mức tải đỉnh |

Các con số trên chỉ là ví dụ. Mục tiêu thực tế phải được thống nhất với chủ sản phẩm và đội vận hành. SLO cần quy định rõ cách đo, cửa sổ thời gian, nhóm truy vấn, percentile và điều kiện thử. Một throughput cao nhưng p99 vượt ngưỡng hoặc tỷ lệ lỗi tăng không phải năng lực phục vụ đạt yêu cầu.

### 1.3. Phân biệt năng lực trung bình và năng lực bền vững

Một cấu hình có thể xử lý 1.200 request/giây trong một bài test ngắn nhưng chỉ giữ được 700 request/giây trong 30 phút vì cache ghi đầy, checkpoint, garbage collection, log flush hoặc thermal throttling. Năng lực bền vững (*sustainable capacity*) là mức tải hệ thống có thể duy trì trong khoảng thời gian đại diện mà vẫn đạt SLO và không tích lũy backlog.

Định cỡ production nên dựa trên năng lực bền vững. Burst capacity có thể được tính riêng nếu nền tảng có cơ chế burst credit, autoscaling hoặc queue hấp thụ tải, nhưng phải biết thời gian duy trì và thời gian phục hồi sau burst.

## 2. Điểm bão hòa và đường cong tải

Khi tăng tải đầu vào, throughput của database thường tăng theo cho tới khi một tài nguyên hoặc thành phần điều phối trở thành giới hạn. Gần điểm bão hòa, queue bắt đầu tích lũy và latency tăng nhanh.

### 2.1. Hình dạng đường cong điển hình

| Vùng tải | Throughput | Latency và queue | Diễn giải |
|---|---|---|---|
| Tải thấp | Tăng gần theo tải đưa vào | Latency tương đối ổn định, queue ngắn | Còn nhiều headroom |
| Tải trung bình | Tăng gần theo tải đưa vào | Latency tăng nhẹ | Tài nguyên được sử dụng hiệu quả |
| Gần điểm bão hòa | Throughput tăng chậm dần | p95/p99 và queue tăng rõ | Một hoặc nhiều tài nguyên gần giới hạn |
| Sau bão hòa | Throughput gần như đứng yên hoặc giảm | Latency tăng mạnh, timeout/retry xuất hiện | Hệ thống không hấp thụ thêm tải |

Điểm bão hòa không nhất thiết là CPU 100%. Database có thể bão hòa ở log flush, IOPS, memory bandwidth, lock manager, connection pool, network hoặc một hot index page trong khi CPU tổng thể vẫn thấp.

### 2.2. Nhận diện “đầu gối” của đường cong

Điểm chuyển từ vùng latency ổn định sang vùng latency tăng nhanh thường được gọi là *knee*. Đây là vùng cần đặc biệt chú ý khi định cỡ. Không nên chọn mức tải ngay sát knee vì biến động nhỏ của workload, dữ liệu hoặc tác vụ nền có thể đẩy hệ thống sang vùng bão hòa.

Ví dụ một phép thử tăng dần tải:

| Tải đưa vào (txn/s) | Throughput hoàn tất (txn/s) | p95 (ms) | Queue chờ trung bình |
|---:|---:|---:|---:|
| 200 | 199 | 45 | 2 |
| 400 | 398 | 52 | 4 |
| 600 | 596 | 68 | 8 |
| 800 | 780 | 115 | 28 |
| 1.000 | 820 | 310 | 95 |
| 1.200 | 825 | 780 | 210 |

Trong ví dụ, throughput gần như không tăng sau 800–1.000 txn/s, nhưng p95 và queue tăng mạnh. Nếu SLO yêu cầu p95 dưới 150 ms, cấu hình này chỉ đạt mục tiêu ở vùng thấp hơn knee. Không nên lấy 825 txn/s làm capacity chỉ vì đó là throughput cao nhất quan sát được.

### 2.3. Dùng định luật Little để hiểu queue

Định luật Little mô tả quan hệ giữa số request đang ở trong hệ thống, throughput và thời gian lưu lại:

\[
L = \lambda W
\]

Trong đó:

- \(L\) là số request trung bình đang ở trong hệ thống hoặc queue được xét.
- \(\lambda\) là throughput hoàn tất trung bình trên đơn vị thời gian.
- \(W\) là thời gian trung bình request ở trong hệ thống đó.

Ví dụ, nếu hệ thống hoàn tất 500 transaction/giây và mỗi transaction mất trung bình 0,1 giây trong một tầng xử lý, số transaction trung bình trong tầng đó xấp xỉ 50. Khi thời gian chờ tăng, số request đang tồn tại cũng tăng nếu throughput không đổi.

Little's Law không tự xác định capacity tối đa. Nó giúp giải thích vì sao queue tăng khi latency tăng và hỗ trợ kiểm tra tính nhất quán của số liệu đo.

## 3. Đo tài nguyên CPU

CPU là tài nguyên quan trọng nhưng không nên chỉ nhìn phần trăm utilization tổng. Một database có thể bị giới hạn bởi một core, một latch, một query plan hoặc một worker pool dù tổng CPU còn thấp.

### 3.1. Chỉ số cần theo dõi

- CPU utilization tổng và theo core.
- Run queue hoặc số thread runnable đang chờ CPU.
- CPU time theo query, transaction và database process.
- Context switch, interrupt và system CPU.
- Số worker hoạt động, worker chờ và parallel query.
- Tỷ lệ thời gian CPU so với elapsed time của truy vấn.
- Các wait event liên quan CPU scheduler, spin, latch hoặc worker exhaustion.

CPU cao cùng run queue dài và latency tăng thường cho thấy thiếu năng lực xử lý hoặc query làm quá nhiều công việc. CPU thấp nhưng query chậm có thể là dấu hiệu chờ I/O, lock, log flush, network hoặc pool.

### 3.2. Tìm query tiêu thụ CPU

Phân tích top query theo tổng CPU, CPU trung bình, số lần chạy và CPU trên mỗi lần gọi. Một query chạy 100.000 lần, mỗi lần tốn 5 ms CPU có thể quan trọng hơn một báo cáo chạy một lần tốn 2 giây.

Kiểm tra execution plan để tìm:

- Scan quá nhiều dòng hoặc đọc cột không cần thiết.
- Join order hoặc join algorithm không phù hợp.
- Sort/hash lớn và aggregate tốn CPU.
- Hàm hoặc biểu thức tính lặp trên nhiều dòng.
- Cardinality estimate sai làm chọn plan kém.
- Parallelism tạo overhead hoặc tranh chấp worker.

Trước khi tăng vCPU, hãy xác định CPU đang được dùng cho công việc có ích hay công việc dư thừa. Tối ưu query có thể tăng capacity hiệu quả hơn nâng cấp máy.

### 3.3. Core count và giới hạn mở rộng

Thêm core chỉ giúp khi workload có đủ song song và không bị giới hạn ở một điểm tuần tự như lock, log flush, hot row hoặc single-thread query. Một số thao tác database có thể mở rộng tốt theo core; một số khác có hiệu quả giảm dần do contention, memory bandwidth hoặc scheduler.

Benchmark cấu hình core tăng dần để tìm hiệu quả biên. Nếu tăng từ 8 lên 16 vCPU chỉ làm throughput tăng 10% nhưng chi phí gần gấp đôi, cần xem bottleneck khác trước khi tiếp tục scale-up.

## 4. Định cỡ bộ nhớ

Bộ nhớ giúp giữ working set, index page, plan cache, sort/hash workspace và các cấu trúc nội bộ. Thiếu memory làm tăng cache miss, đọc storage và spill; cấp quá nhiều memory cho database có thể khiến hệ điều hành, agent, backup hoặc container thiếu RAM.

### 4.1. Working set

Working set là tập dữ liệu và index được truy cập thường xuyên trong một khoảng thời gian. Dung lượng database tổng thể có thể lớn hơn RAM nhiều lần mà vẫn hoạt động tốt nếu working set đủ nhỏ và access pattern có locality. Ngược lại, một bảng nhỏ hơn RAM vẫn có thể gây cache miss nếu workload truy cập ngẫu nhiên trên tập dữ liệu rộng và cạnh tranh giữa nhiều tenant.

Để ước lượng memory cần thiết, hãy đo:

- Kích thước working set của data và index.
- Buffer pool/cache hit và physical read.
- Tần suất page eviction và cache churn.
- Memory grant cho sort/hash và tỷ lệ spill.
- Memory của connection, worker, plan cache và background task.
- Bộ nhớ của hệ điều hành, filesystem cache, backup agent và sidecar.

Không đặt mục tiêu buffer cache hit ratio 100% bằng mọi giá. Một hệ thống có hit ratio cao vẫn có thể đọc quá nhiều page hoặc tiêu tốn CPU; hit ratio tổng hợp cũng có thể che một query nóng đang miss liên tục.

### 4.2. Memory pressure và paging

Khi hệ điều hành thiếu RAM, paging/swap có thể tạo I/O chậm và khó dự đoán. Database có thể bị giảm memory grant, evict cache hoặc gặp allocation failure. Theo dõi available memory, swap-in/swap-out, major page fault, memory pressure signal và OOM event.

Nếu database chạy trong container hoặc VM, cần xem cả giới hạn cgroup/VM và memory của host. Container có thể bị OOM kill dù máy vật lý vẫn còn RAM nếu giới hạn container thấp.

### 4.3. Sort, hash và spill

Truy vấn lớn có thể cần memory cho sort, hash join, hash aggregate và window function. Nếu memory grant hoặc workspace không đủ, engine có thể spill dữ liệu trung gian ra temp storage. Spill làm tăng I/O và latency, đôi khi biến một query CPU-bound thành I/O-bound.

Kiểm tra plan và metric spill, memory grant requested/granted/used, temp file I/O và số dòng thực tế. Tăng memory có thể giúp, nhưng nếu nguyên nhân là cardinality estimate sai hoặc truy vấn tạo tập trung gian quá lớn, cần sửa thống kê/SQL trước.

### 4.4. Tránh overcommit bộ nhớ

Một số cấu hình memory được cấp theo từng connection hoặc operation. Nếu nhân giá trị tối đa cho số connection tối đa, nhu cầu lý thuyết có thể vượt RAM rất xa. Không phải mọi operation đều sử dụng tối đa cùng lúc, nhưng thiết kế cần tính kịch bản concurrency cao.

Hãy phân biệt memory global/cache với memory per-session/per-query. Giới hạn connection pool, worker và parallel query có thể quan trọng không kém việc tăng RAM.

## 5. Định cỡ storage và I/O

Dung lượng đĩa, IOPS, throughput và latency là các giới hạn khác nhau. Một volume có đủ terabyte nhưng không đủ IOPS vẫn làm database chậm. Một volume có IOPS cao nhưng throughput thấp có thể không đáp ứng scan lớn.

### 5.1. Tách các loại I/O

Phân loại I/O theo thành phần:

- Data file: random read/write, scan và page flush.
- Transaction log/WAL/redo: ghi tuần tự, flush theo commit và checkpoint.
- Temp/sort/hash spill: I/O tạm phát sinh khi workspace không đủ.
- Backup/restore: đọc/ghi tuần tự khối lượng lớn.
- Replication/CDC: đọc log, truyền và ghi dữ liệu ở downstream.
- Maintenance: vacuum, purge, index rebuild, compaction và statistics collection.

Một volume dùng chung cho tất cả có thể khiến scan hoặc backup làm tăng latency log flush. Tách volume chỉ có ý nghĩa nếu chúng thực sự được cấp tài nguyên độc lập ở backend; hai mount point trên cùng một pool không bảo đảm tách I/O.

### 5.2. IOPS và throughput

IOPS đo số request mỗi giây; throughput đo lượng dữ liệu mỗi giây. Mối liên hệ gần đúng:

\[
Throughput = IOPS \times Average\ I/O\ Size
\]

Ví dụ, 20.000 IOPS với request trung bình 16 KiB tương ứng khoảng 312,5 MiB/s theo phép nhân. Nếu workload dùng 4 KiB, cùng IOPS chỉ tương ứng khoảng 78,1 MiB/s.

Khi định cỡ, phải lấy block size và read/write mix từ workload thực. Không so spec random read 4 KiB của thiết bị với workload database đang ghi tuần tự 64 KiB rồi kết luận thiết bị đủ năng lực.

### 5.3. Latency và queue depth

Theo dõi p50/p95/p99 I/O latency, queue length, await và mức sử dụng thiết bị. Latency tăng cùng queue tích lũy thường báo hiệu tầng storage hoặc một tầng phía trước đang bị bão hòa.

Nếu IOPS thấp nhưng latency cao, nguyên nhân có thể là request bị serialize, queue ở host/controller, network storage hoặc thiết bị có latency bất thường. Nếu IOPS đạt giới hạn provisioned và queue tăng, cần tăng năng lực hoặc giảm số I/O.

### 5.4. Dung lượng và tăng trưởng

Dung lượng cần tính cả:

- Data và index hiện tại.
- Tăng trưởng dữ liệu theo ngày/tháng.
- Transaction log, WAL/redo và archive log.
- Temp space, undo/version store và staging.
- Backup local, snapshot hoặc vùng phục hồi nếu nằm cùng pool.
- Khoảng trống cho index rebuild, vacuum/compaction và migration.
- Headroom cho tăng trưởng bất thường và thời gian mở rộng.

Không chỉ dự báo kích thước bảng. Index, log, temp và bản sao có thể chiếm dung lượng đáng kể. Theo dõi tốc độ tăng trưởng theo từng loại file và dự báo thời điểm đạt ngưỡng cảnh báo.

## 6. Định cỡ log và năng lực commit

Với workload OLTP, transaction log có thể trở thành nút thắt trước data volume. Mỗi commit cần bảo đảm log record đã được flush theo durability policy. Nếu log storage có latency cao, commit latency tăng dù data page đọc nhanh.

Các chỉ số cần đo:

- Log bytes/second và log generation rate.
- Log flushes/second, flush latency và p95/p99.
- Số transaction mỗi lần flush/group commit.
- Log file growth, checkpoint và archive backlog.
- Replication/standby lag và thời gian apply log.
- Dung lượng log cần cho transaction lớn và thời gian backup/truncate.

Không giảm durability để đạt throughput cao hơn nếu yêu cầu nghiệp vụ cần bảo đảm commit. Thay vào đó, tối ưu transaction size, batch, group commit, log storage và số thao tác ghi thừa. Khi sizing, hãy kiểm tra sustained log throughput dưới tải cao điểm, không chỉ tốc độ ghi data file.

## 7. Kết nối, worker và concurrency

Tăng số connection không đồng nghĩa tăng throughput. Mỗi connection có thể tiêu thụ memory, backend process/thread và tài nguyên scheduler. Quá nhiều connection hoạt động đồng thời có thể làm tăng context switch, lock contention, memory pressure và queue.

### 7.1. Connection pool

Ứng dụng thường dùng connection pool để tái sử dụng kết nối. Cần định cỡ:

- Số connection tối đa mỗi instance ứng dụng.
- Tổng connection trên tất cả instance.
- Số connection hoạt động thực tế và số đang chờ pool.
- Thời gian giữ connection và thời gian chờ acquire.
- Tỷ lệ transaction dài hoặc session idle.

Nếu có 20 instance ứng dụng, mỗi instance cho phép 100 connection, database có thể nhận tới 2.000 connection dù workload chỉ cần vài trăm transaction đồng thời. Tính tổng toàn hệ thống, bao gồm job, migration, monitoring và admin tool.

### 7.2. Concurrency và queue

Giới hạn concurrency có thể cải thiện throughput tổng bằng cách tránh đẩy database vào vùng bão hòa. Khi resource đã bận, thêm request chỉ làm queue dài và p99 tăng. Một pool nhỏ hơn nhưng được điều chỉnh theo capacity có thể tạo latency ổn định hơn.

Đặt giới hạn ở các tầng phù hợp:

- API/request admission.
- Application connection pool.
- Worker queue và batch scheduler.
- Database max connections và worker settings.
- Parallel query degree.

Các giới hạn cần phối hợp. Nếu pool ứng dụng quá lớn so với database, queue chuyển vào database và khó kiểm soát hơn. Nếu quá nhỏ, ứng dụng tạo queue dài dù database còn headroom. Hãy đo thời gian chờ ở cả pool và database.

### 7.3. Lock contention và hot key

Một hot row, counter hoặc index page có thể bão hòa trước CPU, RAM hay storage. Dấu hiệu gồm lock wait, latch wait, deadlock và throughput không tăng khi thêm worker. Định cỡ thêm core không giải quyết được điểm serialize này.

Phân tích top lock/wait, transaction giữ khóa lâu, thứ tự cập nhật và độ phân tán khóa. Có thể giảm contention bằng batch, sharding counter, partition dữ liệu, rút ngắn transaction hoặc thay đổi mô hình cập nhật.

## 8. Network và replication capacity

Network có thể giới hạn ứng dụng và database khi lưu lượng lớn, payload rộng hoặc database ở xa. Theo dõi throughput, packet loss, retransmission, round-trip time, connection setup và số request mỗi transaction.

Replication cũng tiêu thụ network, CPU và I/O. Primary có thể tạo log nhanh hơn standby apply, làm replication lag tăng. Khi định cỡ, cần thử cả thời gian cao điểm và sự kiện failover/resync, không chỉ đo throughput của primary.

Các điểm cần kiểm tra:

- Băng thông và latency giữa application, primary, replica và backup target.
- Số round trip trong query pattern.
- Kích thước result set và payload.
- Log shipping/CDC throughput và apply rate.
- Replication lag, queue và thời gian catch-up sau burst.
- Năng lực standby khi chuyển vai trò thành primary.

Một replica đọc không nhất thiết có cùng cấu hình với primary nếu workload khác, nhưng phải đủ năng lực khi nhận thêm traffic hoặc khi failover theo yêu cầu RTO/RPO.

## 9. Quy trình thử tải để tìm điểm bão hòa

Thử tải phải đại diện cho dữ liệu, truy vấn và chu kỳ vận hành. Một bài test chỉ chạy `SELECT 1` hoặc insert vào bảng rỗng không thể dùng để định cỡ database production.

### 9.1. Chuẩn bị môi trường và dữ liệu

1. Dùng môi trường riêng có cấu hình CPU, memory, storage, network và database gần production.
2. Nạp dữ liệu có kích thước và phân bố tương đương, bao gồm skew, index, partition và lịch sử cần thiết.
3. Chuẩn bị query mix thực tế: đọc, ghi, join, scan, report, batch và maintenance.
4. Thiết lập SLO, timeout, concurrency, thời lượng và điều kiện dừng.
5. Ghi baseline tài nguyên khi idle và ở tải bình thường.
6. Bảo đảm workload generator không trở thành bottleneck của phép thử.

### 9.2. Tăng tải theo từng bậc

Tăng số client hoặc arrival rate theo từng bậc, giữ mỗi bậc đủ lâu để quan sát ổn định. Ví dụ:

| Giai đoạn | Tải mục tiêu | Mục đích |
|---|---:|---|
| Warm-up | 10–20% dự báo peak | Làm nóng cache và xác nhận hệ thống ổn định |
| Step 1 | 30% peak | Đo vùng tải thấp |
| Step 2 | 50% peak | Xem mức tăng latency và resource |
| Step 3 | 70% peak | Xác định resource bắt đầu tăng nhanh |
| Step 4 | 85% peak | Kiểm tra gần vùng vận hành mục tiêu |
| Step 5 | 100% peak | Xác minh SLO ở tải đỉnh |
| Step 6 | Tăng từng bước vượt peak | Tìm knee và giới hạn bão hòa trong môi trường thử |
| Soak | Tải mục tiêu trong thời gian dài | Kiểm tra sustained behavior, cleanup và backlog |

Không nhất thiết dùng đúng các tỷ lệ trên. Mỗi bậc nên đủ dài để queue, cache, checkpoint, purge và background process thể hiện tác động. Dừng phép thử nếu lỗi, latency hoặc tài nguyên vượt ngưỡng an toàn đã đặt.

### 9.3. Open-loop và closed-loop load

Closed-loop generator gửi request mới khi request trước hoàn tất. Khi hệ thống chậm, generator tự giảm tốc, nên có thể che khuất khả năng quá tải thực tế. Open-loop generator phát request theo arrival rate định trước; khi hệ thống chậm, queue tăng và thể hiện rõ overload, nhưng cần giới hạn queue và tránh làm generator tự bão hòa.

Với API có traffic đến độc lập, open-loop thường phản ánh tốt hơn áp lực đầu vào. Closed-loop hữu ích để đo latency theo số client đồng thời. Nên hiểu mô hình load generator và dùng phương pháp phù hợp với traffic production.

### 9.4. Steady-state và soak test

Sau warm-up, cần có khoảng đo steady-state đủ dài. Soak test kéo dài giúp phát hiện memory leak, cache churn, log growth, version cleanup backlog, storage GC và resource exhaustion. Một benchmark ngắn có thể không bộc lộ các vấn đề chỉ xuất hiện sau vài giờ.

## 10. Xác định resource bottleneck

Khi throughput không tăng hoặc latency tăng mạnh, hãy tìm tài nguyên có tín hiệu bão hòa và liên kết nó với query/wait tương ứng.

| Triệu chứng | Chỉ số hỗ trợ | Hướng điều tra |
|---|---|---|
| CPU cao, run queue dài | CPU/core, runnable threads, top query CPU | Query plan, scan, join, aggregate, parallelism |
| CPU thấp nhưng query chậm | I/O wait, lock wait, log wait, network | Xác định tầng đang chờ và queue ở tầng đó |
| Physical read tăng, cache miss cao | Buffer hit, page read latency, IOPS | Working set, index, memory, storage latency |
| p99 I/O tăng và queue dài | Device latency, queue depth, IOPS/throughput limit | Storage backend, burst credit, request size, contention |
| Commit chậm | Log flush latency, WAL/redo throughput | Log volume, group commit, transaction size, durability path |
| Temp I/O tăng | Sort/hash spill, memory grant/work_mem | Cardinality, query shape, memory pressure |
| Lock wait/deadlock tăng | Lock graph, wait events, hot key | Transaction scope, index, update order, concurrency |
| Connection pool wait tăng | Active/idle/waiting connections | Pool sizing, query duration, admission control |
| Replication lag tăng | Log generation/apply rate, network | Standby capacity, network, long-running query/transaction |
| Throughput đứng yên dù CPU còn thấp | Hot page, single worker, lock/latch, serial operator | Điểm serialize, skew và giới hạn song song |

### 10.1. Bottleneck có thể di chuyển

Sau khi tăng RAM, cache miss giảm và storage không còn là giới hạn; CPU có thể trở thành bottleneck mới. Sau khi thêm index, query đọc ít page hơn nhưng write throughput giảm vì index maintenance. Sau khi tăng worker, lock contention có thể tăng.

Vì vậy, mỗi thay đổi phải được đo lại trên toàn workload. Không giả định sửa một bottleneck sẽ tăng capacity theo đúng tỷ lệ tài nguyên được thêm.

### 10.2. Phân biệt saturation và lỗi thiết kế query

Một query scan toàn bảng có thể làm storage bận, nhưng nguyên nhân gốc là predicate không tận dụng index hoặc báo cáo cần đọc quá nhiều dữ liệu. Một query join sai cardinality có thể tiêu thụ CPU/memory không cần thiết. Nếu chỉ tăng IOPS hoặc vCPU, chi phí có thể tăng mà hiệu quả không tương xứng.

Trước khi nâng cấu hình, xem query có đọc đúng lượng dữ liệu cần thiết không, thống kê có mới không và plan có hợp lý không. Tối ưu phần công việc dư thừa thường giúp capacity tăng trên mọi cấu hình.

## 11. Tính headroom và capacity mục tiêu

Không nên định cỡ hệ thống ở đúng mức throughput tối đa đo được. Cần giữ headroom để hấp thụ burst, biến động dữ liệu, tác vụ nền, failover và tăng trưởng.

### 11.1. Từ tải mục tiêu tới capacity an toàn

Giả sử thử tải cho thấy cấu hình đáp ứng SLO bền vững tới 800 transaction/giây; từ 850 trở lên p95 tăng nhanh. Nếu dự báo peak production là 500 transaction/giây, tỷ lệ sử dụng tại peak so với capacity bền vững là:

\[
Utilization = \frac{500}{800} = 62.5\%
\]

Headroom tương ứng là 37,5% của capacity bền vững. Đây là cách diễn đạt theo capacity; nếu tính headroom theo nhu cầu thì phần dư so với 500 txn/s là 300 txn/s, tức 60% của tải dự báo. Cần ghi rõ mẫu số khi báo cáo phần trăm headroom để tránh nhầm lẫn.

### 11.2. Công thức sizing đơn giản

Nếu tải dự báo tăng trưởng theo năm:

\[
Demand_{future} = Demand_{current} \times (1 + g)^n
\]

Trong đó \(g\) là tỷ lệ tăng trưởng mỗi kỳ và \(n\) là số kỳ. Ví dụ tải hiện tại 400 txn/s, tăng 20% mỗi năm, sau hai năm:

\[
400 \times 1.2^2 = 576\ txn/s
\]

Nếu cấu hình có sustainable capacity 800 txn/s, utilization dự báo là 72%. Cần kiểm tra thêm peak burst, tăng trưởng dữ liệu và workload mới; tăng trưởng transaction không nhất thiết tỷ lệ tuyến tính với CPU, memory hay I/O.

### 11.3. Headroom không phải một con số cố định

Headroom phụ thuộc:

- Mức biến động tải và tốc độ tăng trưởng.
- Thời gian cần để mở rộng tài nguyên hoặc provision volume.
- Tác động của failover và maintenance.
- Khả năng burst của cloud volume/instance.
- SLO và chi phí khi vượt ngưỡng.
- Mức độ dễ dự đoán của workload.

Hệ thống có autoscaling nhanh và queue tốt có thể dùng headroom khác với hệ thống cần mua phần cứng trước nhiều tháng. Đặt ngưỡng dựa trên thời gian phản ứng và rủi ro, không dùng một tỷ lệ phổ quát.

## 12. Định cỡ theo từng tài nguyên

### 12.1. CPU

Ước lượng CPU demand bằng tổng CPU time của các workload trong một khoảng, nhưng cần benchmark vì concurrency, cache và parallelism làm hiệu quả thay đổi. Theo dõi CPU utilization, run queue và CPU time/query tại tải mục tiêu. Chọn cấu hình có thể đáp ứng SLO trước knee, kể cả khi chạy backup, vacuum, statistics collection hoặc batch theo lịch.

### 12.2. Memory

Ước lượng memory dựa trên working set, buffer/cache, session/worker, memory grant, temp workspace và phần dành cho OS. Kiểm tra concurrency vì nhiều sort/hash có thể đồng thời xin memory. Không cấp toàn bộ RAM cho database nếu hệ điều hành và công cụ vận hành cần vùng riêng.

### 12.3. Storage capacity

Ước lượng dung lượng theo tốc độ tăng trưởng của data, index, log, temp, undo/version store, backup và vùng bảo trì. Tính cả khoảng trống cần cho rebuild hoặc migration. Đặt cảnh báo trước khi volume chạm ngưỡng mà việc mở rộng mất nhiều thời gian.

### 12.4. IOPS và throughput

Đo read/write IOPS, block size, throughput và p95/p99 latency ở workload đại diện. Tính riêng data, log và temp nếu chúng có đường lưu trữ khác nhau. Với cloud, kiểm tra giới hạn volume, instance và burst credit; provisioned IOPS không bảo đảm throughput nếu bị giới hạn ở tầng khác.

### 12.5. Log throughput

Đo log generation rate ở peak, commit flush latency và khả năng archive/replicate. Log volume phải chịu được burst ghi và transaction lớn. Dung lượng log cần đủ cho backup, replication lag, long transaction và quy trình recovery.

### 12.6. Connection và worker

Định cỡ pool theo concurrency cần thiết ở tải mục tiêu, không theo số người dùng đăng ký. Theo dõi thời gian chờ connection, active transaction, worker queue và memory mỗi session. Giới hạn tổng connection trên mọi instance ứng dụng.

### 12.7. Network

Đo bytes/second, round-trip time, retransmission và throughput giữa các tầng. Ước lượng result set, replication, backup và CDC cùng lúc. Nếu database ở xa application, số round trip trong một request có thể quan trọng hơn băng thông tối đa.

## 13. Vertical scaling, horizontal scaling và giới hạn mở rộng

### 13.1. Scale-up

Scale-up tăng CPU, RAM, IOPS hoặc throughput cho một node. Ưu điểm là ứng dụng ít phải thay đổi và có thể xử lý bottleneck tài nguyên nhanh. Giới hạn gồm chi phí, giới hạn instance, thời gian resize, khả năng mở rộng không tuyến tính và điểm lỗi đơn nếu kiến trúc không có HA.

Scale-up phù hợp khi workload còn tập trung ở một database node và bottleneck là tài nguyên có thể mở rộng trên node đó. Trước khi nâng cấp, kiểm tra query, index, connection và lock để tránh trả tiền cho tài nguyên không giải quyết được điểm nghẽn.

### 13.2. Scale-out đọc

Read replica có thể phân tán workload đọc, nhưng cần xét replication lag, read-after-write consistency và năng lực khi failover. Không gửi mọi truy vấn đọc sang replica nếu một số thao tác cần dữ liệu mới nhất hoặc transaction semantics cụ thể.

### 13.3. Sharding và partitioning

Sharding phân chia dữ liệu và workload giữa nhiều node. Nó có thể tăng capacity khi bottleneck là một node, nhưng làm tăng độ phức tạp của transaction phân tán, join, unique key, rebalance và vận hành. Partitioning trong một database thường giúp quản lý và pruning dữ liệu; bản thân partitioning không đồng nghĩa với scale-out.

Chỉ sharding khi có bằng chứng một node không đáp ứng được yêu cầu sau khi đã tối ưu query, index và tài nguyên. Chọn shard key dựa trên phân bố tải; key skew có thể tạo một shard nóng và làm capacity tổng thể thấp hơn mong đợi.

### 13.4. Kiểm tra failover capacity

Nếu primary chuyển sang replica, replica phải đủ CPU, memory, storage và network để nhận workload mới. Nếu thiết kế chỉ đủ tài nguyên khi đọc được chia cho nhiều replica, sự cố mất một replica có thể đẩy các node còn lại vào vùng bão hòa.

Thử failover và tải sau failover trong môi trường phù hợp. Capacity plan cần bao gồm tình huống giảm redundancy, không chỉ trạng thái bình thường.

## 14. Định cỡ trên nền tảng cloud

Cloud database và block storage thường có nhiều lớp quota: vCPU, memory, IOPS, throughput, connection, storage size, log rate, network và giới hạn instance. Tăng một thông số có thể không tăng capacity nếu một lớp khác vẫn giới hạn.

Các yếu tố cần kiểm tra:

- IOPS/throughput được provision theo volume hay theo instance.
- Burst credit có hay không, tốc độ tích lũy/tiêu thụ và hành vi khi hết credit.
- Giới hạn network throughput theo loại instance.
- Giới hạn connection, worker, storage growth và log throughput.
- Thời gian resize, restart hoặc failover khi đổi tier.
- Chi phí snapshot, backup, replica, I/O và dung lượng tăng thêm.
- Metric cloud có đo ở guest, volume hay backend và độ trễ cập nhật metric.

Không suy ra năng lực từ nhãn instance hoặc tên tier. Đọc giới hạn dịch vụ hiện hành và benchmark chính workload của mình. Một volume có IOPS provision cao nhưng instance không đủ throughput có thể không đạt số đã cấu hình.

## 15. Ví dụ xây dựng capacity plan

Giả sử một hệ thống đơn hàng có các đặc trưng đo được:

- Tải trung bình 250 transaction/giây.
- Peak 600 transaction/giây trong 15 phút.
- Tỷ lệ đọc/ghi 70/30.
- Data và index tăng 8% mỗi tháng.
- SLO giao dịch ghi p95 dưới 250 ms, API đọc p95 dưới 100 ms.
- Bài test trên cấu hình hiện tại đạt 700 transaction/giây bền vững trước khi p95 vượt SLO; ở 800 transaction/giây, log flush latency và p99 tăng mạnh.

### 15.1. Đánh giá cấu hình hiện tại

Peak 600 txn/s chiếm khoảng 85,7% sustainable capacity 700 txn/s. Headroom theo capacity chỉ còn khoảng 14,3%, thấp nếu tải có burst hoặc hệ thống cần chạy maintenance cùng thời điểm. Không nên lấy 800 txn/s làm năng lực vì SLO đã bị vi phạm ở vùng đó.

### 15.2. Tìm bottleneck trước khi nâng cấp

Giả sử phép đo cho thấy:

- CPU tổng khoảng 55%, chưa có run queue dài.
- Buffer cache hit ổn định.
- Data I/O latency thấp.
- Log flush p99 tăng nhanh ở 700–800 txn/s.
- Transaction ghi nhỏ nhưng commit rate cao.

Bằng chứng gợi ý đường log flush là bottleneck trước CPU và data storage. Các phương án cần thử gồm log volume có latency thấp hơn, cải thiện group commit, giảm commit thừa nếu nghiệp vụ cho phép và điều chỉnh batch/transaction. Tăng vCPU hoặc RAM có thể không tăng capacity đáng kể.

### 15.3. Tính nhu cầu tương lai

Nếu peak dự báo tăng 20% mỗi năm, sau hai năm:

\[
600 \times 1.2^2 = 864\ txn/s
\]

Cấu hình hiện tại không đáp ứng mức này với SLO. Capacity plan cần benchmark phương án cải thiện log và/hoặc scale-up, rồi xác minh sustainable capacity mới. Nếu cần duy trì headroom 25% theo capacity, sustainable capacity mục tiêu tối thiểu theo cách tính utilization là:

\[
Capacity_{target} \geq \frac{864}{0.75} = 1.152\ txn/s
\]

Đây là phép tính sơ bộ. Năng lực mới phải được chứng minh bằng thử tải và kiểm tra failover, backup, maintenance cùng workload thực tế.

## 16. Những sai lầm thường gặp

- **Định cỡ theo số người dùng hoặc dung lượng database:** không phản ánh query mix, concurrency và working set.
- **Dùng CPU trung bình:** bỏ qua peak, run queue và một core hoặc worker bị bão hòa.
- **Chọn cấu hình theo throughput tối đa:** không xét SLO, p99, queue và năng lực bền vững.
- **Chỉ benchmark ngắn:** không thấy checkpoint, GC, purge, log growth hoặc thermal throttling.
- **Dùng dữ liệu thử quá nhỏ:** cache hit cao giả tạo và plan khác production.
- **Tăng connection để tăng throughput:** có thể làm tăng contention, memory và queue.
- **Coi IOPS là đại diện đầy đủ cho storage:** bỏ qua block size, throughput, latency và read/write mix.
- **Bỏ qua log volume:** commit latency có thể là bottleneck dù data disk còn rảnh.
- **Cấp hết RAM cho database:** hệ điều hành, filesystem, agent hoặc container có thể thiếu memory.
- **Scale-up mà không tối ưu query:** tài nguyên mới tiếp tục bị tiêu thụ bởi công việc dư thừa.
- **Giả định scale-out tuyến tính:** network, coordination, shard skew và replication tạo overhead.
- **Không thử failover:** cấu hình dự phòng có thể không đủ sức gánh toàn tải.
- **Không tính thời gian provision:** tài nguyên cloud hoặc phần cứng có thể không mở rộng ngay khi cần.
- **Không đặt headroom:** một biến động nhỏ có thể đẩy hệ thống vượt knee.

## 17. Checklist định cỡ tài nguyên

- [ ] Đã mô tả query mix, read/write mix, concurrency, data volume và giờ cao điểm.
- [ ] Đã xác định SLO cho throughput, p95/p99, timeout và tỷ lệ lỗi.
- [ ] Đã dùng dữ liệu thử có kích thước, skew và index gần production.
- [ ] Đã thử tải theo từng bậc và xác định vùng knee/saturation.
- [ ] Đã chạy soak test để kiểm tra năng lực bền vững.
- [ ] Đã đo CPU theo core, run queue, top query và worker.
- [ ] Đã đo working set, buffer cache, memory pressure, swap và spill.
- [ ] Đã đo storage capacity, IOPS, throughput, block size, queue và p95/p99 latency.
- [ ] Đã đo log generation, flush latency, checkpoint và replication lag.
- [ ] Đã đo connection pool wait, active transaction, lock wait và hot key.
- [ ] Đã kiểm tra network, quota và giới hạn ở mọi tầng cloud/storage.
- [ ] Đã phân biệt bottleneck query với bottleneck tài nguyên.
- [ ] Đã tính headroom, tăng trưởng dữ liệu, peak burst và thời gian mở rộng.
- [ ] Đã kiểm tra năng lực trong maintenance, backup và failover.
- [ ] Đã benchmark lại sau mỗi thay đổi và cập nhật capacity plan theo số liệu.

Định cỡ tài nguyên hiệu quả là tìm mức tải bền vững mà database vẫn đáp ứng SLO trước khi queue và latency tăng mạnh. CPU, memory, storage, log, connection và network phải được đo cùng workload thực tế vì bottleneck có thể di chuyển sau mỗi lần tối ưu. Khi xác định được điểm bão hòa, giữ headroom theo biến động và thời gian mở rộng, rồi kiểm chứng cả trạng thái bình thường lẫn failover, nhóm vận hành có thể chọn cấu hình phù hợp và tránh đầu tư vào tài nguyên không giải quyết đúng nút thắt.
