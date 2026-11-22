# Giới hạn CPU, số lõi và khả năng song song thực tế

Một máy chủ cơ sở dữ liệu có thể được cấp nhiều CPU hoặc nhiều lõi nhưng truy vấn vẫn chạy chậm, hoặc chỉ một vài truy vấn tăng tốc khi bật parallelism. Nguyên nhân là số lõi được nhìn thấy bởi hệ điều hành, số CPU thực sự được cấp, giới hạn container/VM, ngân sách worker của DBMS và khả năng chia nhỏ công việc của từng câu SQL không phải cùng một đại lượng.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần phân biệt **năng lực CPU khả dụng**, **mức đồng thời của workload** và **độ song song thực tế của từng truy vấn**. Tăng degree of parallelism (DOP) có thể rút ngắn một truy vấn CPU-bound, nhưng cũng có thể làm nhiều truy vấn cạnh tranh CPU, bộ nhớ và I/O hơn. Một truy vấn có DOP cao không nhất thiết nhanh hơn nếu dữ liệu lệch, có bước tuần tự, cần trao đổi dữ liệu giữa worker hoặc đang chờ I/O.

Bài học này giải thích physical core, logical processor, vCPU và CPU quota; cách DBMS lập lịch worker và thực thi song song; cách đo DOP thực tế; dấu hiệu phân biệt CPU bottleneck với I/O hoặc lock wait; cùng quy trình chọn giới hạn parallelism theo workload và xác minh bằng benchmark.

## 1. Phân biệt số CPU được nhìn thấy và năng lực CPU thực tế

Khi kiểm tra một máy chủ, công cụ hệ điều hành có thể hiển thị số processor logic. Con số này không đồng nghĩa với số lõi vật lý độc lập hoặc công suất CPU mà tiến trình database luôn được sử dụng.

### 1.1. Physical core và logical processor

- **Physical core** là lõi xử lý vật lý trong CPU, có tài nguyên thực thi riêng.
- **Logical processor** là một luồng phần cứng mà hệ điều hành lập lịch. Công nghệ SMT/Hyper-Threading cho phép một lõi vật lý chạy nhiều luồng phần cứng.
- Hai logical processor trên cùng một physical core chia sẻ một phần tài nguyên lõi. Vì vậy, 16 logical processor không nhất thiết tương đương 16 physical core.

SMT có thể tăng throughput khi một luồng chờ tài nguyên hoặc khi workload tận dụng tốt các đơn vị thực thi còn trống. Nhưng lợi ích không cố định; một workload CPU-bound có thể nhận được mức tăng thấp hơn nhiều so với tỷ lệ logical processor.

### 1.2. vCPU trên máy ảo

Máy ảo thường hiển thị vCPU. vCPU là đơn vị CPU ảo được hypervisor lập lịch lên CPU vật lý. Số vCPU được cấu hình không bảo đảm VM luôn nhận được toàn bộ thời gian CPU tương ứng nếu host quá tải, có quota hoặc giới hạn của nền tảng cloud.

Các yếu tố cần kiểm tra:

- Số vCPU được cấu hình cho VM.
- Số physical core và mức oversubscription trên host nếu có thể quan sát.
- CPU ready/steal time hoặc metric tương đương của hypervisor.
- CPU credit hoặc burst balance ở các loại instance dùng mô hình burstable.
- Giới hạn CPU của nền tảng và chính sách chia sẻ tài nguyên.

Nếu guest OS báo CPU sử dụng thấp nhưng VM vẫn chậm, có thể hypervisor chưa cấp thời gian chạy đủ nhanh. Cần xem metric của nền tảng ảo hóa thay vì chỉ nhìn CPU utilization bên trong VM.

### 1.3. CPU quota và container

Container có thể nhìn thấy nhiều processor nhưng bị giới hạn thời gian CPU bằng quota hoặc cgroup. Ví dụ, một container có thể nhìn thấy 16 CPU logic nhưng quota chỉ tương đương 4 CPU liên tục. Khi tiến trình dùng hết quota trong chu kỳ, nó bị throttle cho đến chu kỳ kế tiếp.

Trên Linux, các thông tin thường cần xem gồm:

- cgroup v2: cpu.max, cpu.stat và cpuset.cpus.effective.
- cgroup v1: cpu.cfs_quota_us, cpu.cfs_period_us, cpu.stat và cpuset.
- CPU affinity của tiến trình.
- Giới hạn CPU do orchestrator như Kubernetes đặt qua requests/limits.

CPU quota biểu thị lượng thời gian CPU được phép tiêu thụ trong một chu kỳ; cpuset giới hạn CPU nào được phép chạy. Hai cấu hình này khác nhau. Một container được phép chạy trên 16 CPU nhưng quota bằng 4 CPU có thể bị throttle dù nhiều CPU đang rảnh trên host.

Ví dụ khái niệm:

~~~text
Container nhìn thấy: 16 logical CPU
CPU quota:            400000 microseconds
CPU period:           100000 microseconds
Năng lực quota gần đúng: 4 CPU
~~~

Giá trị quota ở trên tương đương trung bình tối đa bốn CPU trong mỗi chu kỳ nếu được dùng liên tục. Đây là ví dụ minh họa; cần đọc cấu hình thực tế của container.

### 1.4. CPU affinity và NUMA

CPU affinity giới hạn tiến trình hoặc worker chạy trên một tập CPU cụ thể. NUMA chia máy chủ thành các node có vùng bộ nhớ gắn với CPU. Truy cập bộ nhớ local thường có độ trễ và băng thông tốt hơn truy cập remote node.

Nếu worker database bị pin vào một nhóm CPU nhưng cấp phát bộ nhớ ở NUMA node khác, truy cập remote memory có thể làm giảm hiệu năng. Một cấu hình affinity quá hẹp cũng có thể khiến DBMS không sử dụng được toàn bộ CPU được cấp.

Không thay đổi affinity hoặc NUMA policy theo cảm tính. Hãy kiểm tra topology, CPU locality, memory locality và hướng dẫn của DBMS trước khi điều chỉnh.

## 2. Số lõi không đồng nghĩa với số worker database

DBMS dùng các tiến trình hoặc thread để phục vụ connection, background task, I/O, replication, checkpoint và truy vấn. Số worker đang tồn tại có thể lớn hơn số lõi, nhưng không phải tất cả đều chạy CPU cùng lúc.

Một hệ thống cần phân biệt:

- **Connection/session:** phiên làm việc của client.
- **Worker thread/process:** đơn vị thực thi công việc của DBMS.
- **Parallel worker:** worker tham gia một truy vấn song song.
- **Background worker:** tiến trình nền như vacuum, replication, checkpoint, log writer hoặc task nội bộ.
- **Operating system thread:** luồng được hệ điều hành lập lịch trên CPU.

Một connection không nhất thiết tương ứng một CPU riêng. Nhiều connection có thể luân phiên sử dụng CPU; một truy vấn có thể dùng nhiều worker; background task cũng cạnh tranh tài nguyên với truy vấn ứng dụng.

Vì vậy, không thể đặt số connection bằng số lõi rồi kết luận hệ thống đã được cấu hình tối ưu. Cần xem tổng concurrency, thời gian CPU của mỗi truy vấn, số worker song song và tài nguyên nền.

## 3. Parallel query và Degree of Parallelism (DOP)

Parallel query chia một số phần công việc thành nhiều nhánh để worker xử lý đồng thời. DOP thường biểu thị số worker hoặc số luồng xử lý song song được dùng cho một phần của kế hoạch, nhưng cách định nghĩa và cách đếm có thể khác nhau giữa DBMS.

Ví dụ, một truy vấn quét bảng lớn rồi tổng hợp:

~~~sql
SELECT region_id, COUNT(*), SUM(amount)
FROM sales
WHERE sale_time >= TIMESTAMP '2026-01-01 00:00:00'
GROUP BY region_id;
~~~

Nếu hệ quản trị có thể chia scan thành các vùng độc lập, nhiều worker đọc các phần dữ liệu khác nhau, tính aggregate cục bộ rồi kết hợp kết quả. Khi dữ liệu lớn và CPU là nút thắt, thời gian tường (elapsed time) có thể giảm.

### 3.1. DOP được yêu cầu, được lập kế hoạch và thực tế

Ba con số này có thể khác nhau:

- **Requested DOP:** mức song song được cấu hình hoặc chỉ định.
- **Planned DOP/workers planned:** số worker optimizer dự kiến sử dụng khi tạo kế hoạch.
- **Actual DOP/workers launched:** số worker thực sự được cấp và tham gia lúc chạy.

DBMS có thể lập kế hoạch với 8 worker nhưng chỉ khởi chạy 4 vì giới hạn worker, tải đồng thời hoặc tài nguyên đang thiếu. Một số hệ thống tính cả leader/coordinator vào DOP; hệ thống khác hiển thị số worker phụ riêng. Hãy dùng định nghĩa của đúng DBMS và công cụ đang đọc.

### 3.2. Parallelism không áp dụng cho mọi operator

Một kế hoạch có thể chỉ song song ở một số bước:

- Scan hoặc đọc partition có thể chia việc.
- Filter có thể chạy trên mỗi worker.
- Hash build/probe có thể có biến thể song song.
- Aggregate có thể tính cục bộ rồi kết hợp.
- Sort có thể chạy song song theo phạm vi rồi merge.
- Một số bước điều phối, ghi kết quả hoặc xử lý cuối cùng vẫn cần một leader/coordinator.

Nếu phần tốn thời gian nằm ở bước tuần tự, tăng DOP cho scan không giúp nhiều. Các operator exchange/gather cũng có chi phí phân phối và gom dữ liệu.

### 3.3. Chi phí điều phối

Parallel query cần chia công việc, cấp worker, trao đổi dữ liệu và đồng bộ kết quả. Chi phí này có thể gồm:

- Khởi tạo worker và truyền trạng thái thực thi.
- Chia partition/block/range cho worker.
- Queue, exchange, gather hoặc tuple transfer.
- Đồng bộ barrier và kết hợp aggregate.
- Cạnh tranh cache, memory bandwidth và CPU.

Với truy vấn nhỏ, overhead song song có thể lớn hơn phần công việc tiết kiệm được. Vì vậy, DBMS thường dùng ngưỡng chi phí hoặc kích thước dữ liệu để quyết định có song song hóa hay không.

## 4. Giới hạn parallelism trong các hệ quản trị

Mỗi DBMS có cơ chế riêng. Không nên chuyển nguyên xi một tham số từ hệ này sang hệ khác.

### 4.1. PostgreSQL

PostgreSQL hỗ trợ parallel query cho các kế hoạch và operator đủ điều kiện. Một số tham số quan trọng:

- max_parallel_workers_per_gather: giới hạn worker cho mỗi Gather/Gather Merge.
- max_parallel_workers: giới hạn tổng parallel worker của instance.
- max_worker_processes: giới hạn worker process tổng thể, bao gồm nhiều loại background worker.
- min_parallel_table_scan_size và min_parallel_index_scan_size: ngưỡng kích thước để xem xét parallel scan.
- parallel_setup_cost và parallel_tuple_cost: thành phần chi phí mô hình hóa overhead song song.

Ví dụ xem cấu hình:

~~~sql
SHOW max_parallel_workers_per_gather;
SHOW max_parallel_workers;
SHOW max_worker_processes;
SHOW parallel_setup_cost;
SHOW parallel_tuple_cost;
~~~

Kế hoạch EXPLAIN có thể hiển thị Gather hoặc Gather Merge, Workers Planned và Workers Launched. Với EXPLAIN ANALYZE, xem số hàng và thời gian theo worker nếu đầu ra cung cấp.

Một số hàm, operator hoặc truy vấn có thể không parallel-safe. Transaction state, cursor, temporary table, volatile function và các đặc điểm khác có thể giới hạn parallel plan. Cần xem tài liệu phiên bản PostgreSQL và thuộc tính parallel safety của function.

### 4.2. SQL Server

SQL Server dùng parallel execution plan khi optimizer đánh giá chi phí đủ lớn và có worker/resource phù hợp. Các thiết lập thường cần xem:

- max degree of parallelism (MAXDOP): giới hạn DOP.
- cost threshold for parallelism: ngưỡng chi phí optimizer dùng khi xem xét parallel plan.
- Resource Governor: có thể áp dụng giới hạn tài nguyên cho workload group nếu phiên bản/edition hỗ trợ.
- Query hint hoặc database-scoped configuration: điều chỉnh ở phạm vi truy vấn/database trong các tình huống phù hợp.

Ví dụ xem cấu hình:

~~~sql
EXEC sp_configure 'max degree of parallelism';
EXEC sp_configure 'cost threshold for parallelism';
~~~

Actual Execution Plan có thể hiển thị Parallelism operator, số thread, runtime counters và phân phối hàng. DOP của một request có thể bị giới hạn bởi MAXDOP, affinity, scheduler, memory grant hoặc worker availability.

Các wait type như CXPACKET và CXCONSUMER cần được đọc trong ngữ cảnh. Chúng không tự động chứng minh parallelism xấu; cần xem worker imbalance, CPU time, elapsed time, số hàng trao đổi và waits khác.

### 4.3. Oracle Database

Oracle hỗ trợ Parallel Execution với degree of parallelism (DOP) và các parallel execution server. Cấu hình có thể liên quan:

- PARALLEL_DEGREE_POLICY.
- PARALLEL_MAX_SERVERS.
- PARALLEL_MIN_SERVERS.
- PARALLEL_DEGREE_LIMIT.
- Resource Manager và consumer group.
- Thuộc tính PARALLEL trên object hoặc statement.

Execution plan có thể hiển thị PX SEND, PX RECEIVE, table scan hoặc các operator song song. V$PX_SESSION, V$SQL_PLAN_MONITOR và SQL Monitor có thể giúp xem DOP thực tế, worker và phân phối dữ liệu tùy quyền truy cập, phiên bản và license.

Oracle có thể tự chọn DOP theo policy, object size và resource availability. DOP được yêu cầu không bảo đảm số parallel server thực tế luôn bằng mức đó.

### 4.4. MySQL

MySQL/InnoDB thường khai thác CPU chủ yếu qua nhiều connection và thread đồng thời. Không nên giả định mọi câu SELECT lớn đều có intra-query parallelism với DOP tương tự SQL Server, PostgreSQL hoặc Oracle. Khả năng song song hóa phụ thuộc phiên bản, engine, loại thao tác và tính năng cụ thể; một số công việc như replication apply, DDL hoặc thao tác nội bộ có cơ chế worker riêng.

Khi tối ưu MySQL, cần xem thread concurrency, connection count, thread pool nếu dùng, InnoDB background threads, replication workers, CPU quota và contention. Nếu một truy vấn đơn lẻ không thể chia thành nhiều worker, có thể tối ưu SQL, index, partitioning hoặc chạy nhiều công việc độc lập có kiểm soát.

## 5. CPU bottleneck khác gì I/O bottleneck?

CPU utilization cao chưa chắc là vấn đề nếu throughput và latency vẫn trong SLO. Ngược lại, CPU utilization thấp không chứng minh hệ thống còn dư năng lực nếu tiến trình bị quota throttle hoặc đang chờ I/O, lock, network hay worker.

### 5.1. Dấu hiệu CPU-bound

- CPU utilization của host hoặc container cao kéo dài.
- Run queue/runnable thread tăng, nhiều thread sẵn sàng chạy nhưng chờ CPU.
- CPU time của truy vấn cao so với elapsed time trong truy vấn đơn luồng; với truy vấn song song tổng CPU time có thể lớn hơn elapsed time.
- Các operator scan, expression, hash, sort hoặc aggregate tiêu thụ CPU đáng kể.
- Tăng CPU capacity hoặc giảm công việc tính toán làm throughput/latency cải thiện.

### 5.2. Dấu hiệu I/O-bound

- CPU không bão hòa nhưng truy vấn có nhiều physical read hoặc storage latency cao.
- Session chờ đọc page, log flush hoặc I/O completion.
- Throughput bị giới hạn bởi disk bandwidth, IOPS hoặc queue depth.
- Tăng DOP không cải thiện vì worker cùng chờ dữ liệu.

### 5.3. Dấu hiệu lock/contention-bound

- Nhiều session chờ lock/latch hoặc tranh chấp tài nguyên nội bộ.
- CPU có thể thấp trong lúc elapsed time cao.
- Tăng DOP làm nhiều worker cùng đụng một vùng nóng và tăng contention.
- Chỉ một số key, page hoặc partition tạo wait tập trung.

### 5.4. Dấu hiệu CPU quota hoặc VM scheduling

- Container có CPU throttled periods/throttled time tăng.
- VM có CPU ready/steal time cao.
- Tiến trình không dùng được CPU dù host còn tài nguyên.
- CPU quota/affinity nhỏ hơn số CPU hệ điều hành hiển thị.

Phải đo cả host, container/VM và DBMS. Chỉ nhìn một dashboard CPU tổng thể có thể che giấu giới hạn ở tầng container hoặc scheduler.

## 6. DOP cao có thể làm truy vấn chậm hơn

Tăng số worker chỉ giúp khi công việc có thể chia đều và phần tiết kiệm lớn hơn chi phí điều phối.

Các nguyên nhân làm DOP cao kém hiệu quả:

- **Amdahl's law:** một phần truy vấn không thể song song hóa sẽ giới hạn tốc độ tăng.
- **Skew:** một worker nhận nhiều hàng hoặc kết quả hơn các worker khác.
- **Exchange overhead:** dữ liệu phải phân phối/gom qua operator trung gian.
- **Memory pressure:** mỗi worker có thể cần buffer hoặc memory grant riêng.
- **CPU oversubscription:** tổng worker runnable vượt năng lực CPU khả dụng.
- **Cache contention:** nhiều worker tranh chấp cache line, memory bandwidth hoặc buffer.
- **I/O saturation:** nhiều worker đọc cùng lúc làm storage queue tăng.
- **Coordinator bottleneck:** leader phải nhận, kết hợp hoặc serialize kết quả.

### 6.1. Amdahl's law

Nếu tỷ lệ công việc có thể song song là p và dùng N worker, speedup lý tưởng bị giới hạn:

\[
Speedup(N)=\frac{1}{(1-p)+\frac{p}{N}}
\]

Ví dụ, nếu 80% công việc có thể song song (p = 0,8), 20% còn lại là tuần tự:

| Worker | Speedup lý tưởng |
|---:|---:|
| 1 | 1,00x |
| 2 | 1,67x |
| 4 | 2,50x |
| 8 | 3,33x |
| 16 | 4,00x |

Đây là giới hạn lý tưởng, chưa tính overhead, skew, memory và I/O. Trong thực tế, lợi ích thường thấp hơn.

## 7. Tổng worker và nguy cơ oversubscription

Giả sử máy chủ có năng lực CPU tương đương 16 core. Có 12 truy vấn đồng thời, mỗi truy vấn có DOP 8. Nếu mỗi truy vấn sử dụng đủ 8 worker, riêng workload đó có thể cần khoảng 96 worker xử lý song song, chưa kể leader, connection worker và background task.

Không phải tất cả worker luôn chạy cùng lúc, và cách đếm worker khác nhau theo DBMS. Nhưng ví dụ cho thấy DOP per-query phải được xem cùng concurrency.

Một mô hình ngân sách đơn giản:

\[
CPU\ demand \approx \sum_{i=1}^{C} DOP_i + B
\]

Trong đó C là số truy vấn song song đang hoạt động và B là nhu cầu CPU của workload tuần tự/background. Đây chỉ là mô hình sàng lọc, không phải công thức lập lịch chính xác.

Khi tổng nhu cầu runnable cao hơn CPU capacity:

- Run queue tăng.
- Context switch tăng.
- Cache locality có thể giảm.
- Worker chờ CPU lâu hơn.
- Elapsed time tăng dù DOP của từng truy vấn cao.
- Truy vấn nhỏ và workload OLTP có thể bị ảnh hưởng bởi truy vấn phân tích lớn.

Một cách quản trị phổ biến là giới hạn DOP cho truy vấn nặng, phân nhóm workload và dành ngân sách CPU cho các thao tác tương tác/transactional.

## 8. Dùng parallelism theo loại workload

Không nên áp dụng cùng DOP cho mọi truy vấn.

| Loại workload | Đặc điểm | Hướng cân nhắc |
|---|---|---|
| OLTP point lookup | Truy vấn ngắn, ít hàng, độ trễ thấp | Thường ưu tiên plan tuần tự, giảm overhead worker |
| OLTP join vừa | Nhiều truy vấn đồng thời, thời gian ngắn | Giới hạn DOP để giữ CPU cho concurrency |
| Báo cáo lớn | Scan, join, aggregate nhiều dữ liệu | Có thể hưởng lợi từ parallel query nếu CPU còn dư và I/O đủ nhanh |
| ETL/bulk transform | Công việc theo lô, có thể chia độc lập | Dùng worker có giới hạn, điều tiết theo I/O/log/replica |
| Maintenance | Index build, vacuum, backup, statistics | Đặt lịch và giới hạn để không cạnh tranh với workload chính |
| Mixed workload | OLTP và analytics cùng instance | Dùng resource group/workload group hoặc lịch chạy riêng nếu DBMS hỗ trợ |

Nếu hệ thống vừa phục vụ giao dịch vừa chạy báo cáo, có thể tách workload sang replica/warehouse hoặc dùng resource governance. Parallelism không nên lấy toàn bộ CPU của primary trong giờ cao điểm chỉ vì truy vấn báo cáo chạy nhanh hơn.

## 9. Cách đo parallelism thực tế

Để biết DOP có hiệu quả, cần thu thập cả kế hoạch và số liệu runtime.

### 9.1. Chỉ số ở mức truy vấn

- Requested/planned/actual DOP.
- Số worker được cấp và số worker thực sự chạy.
- CPU time và elapsed time.
- Số hàng mỗi worker xử lý.
- Thời gian chờ ở exchange/gather/synchronization.
- Memory grant hoặc memory usage theo operator.
- Logical/physical reads và I/O latency.
- Spill của sort/hash.
- Rows per worker và mức chênh lệch giữa worker nhanh nhất/chậm nhất.

### 9.2. Chỉ số ở mức máy chủ

- CPU utilization theo core/logical processor.
- Run queue hoặc runnable tasks.
- Context switches.
- CPU throttling và quota usage.
- VM CPU ready/steal.
- Memory bandwidth/NUMA locality nếu có metric.
- Background task CPU.
- Số session active, worker active và queue chờ worker.

### 9.3. Worker imbalance

Nếu một worker xử lý 10 triệu hàng trong khi các worker khác chỉ xử lý 1 triệu, thời gian hoàn tất có thể bị chi phối bởi worker nặng nhất. Hãy kiểm tra partitioning, distribution key, filter selectivity và skew dữ liệu.

Không nên kết luận imbalance chỉ từ số hàng nếu độ rộng hàng hoặc công việc trên mỗi hàng khác nhau. Cần đối chiếu elapsed/CPU time, bytes, I/O và số kết quả.

## 10. Ví dụ đọc kế hoạch song song

Một kế hoạch khái quát:

~~~text
Gather
  Workers Planned: 8
  Workers Launched: 4
  -> Parallel Seq Scan on sales
       Filter: sale_time >= ...
       actual rows per worker: varied
~~~

Ví dụ này cho thấy optimizer dự kiến 8 worker nhưng runtime chỉ khởi chạy 4. Cần tìm nguyên nhân ở giới hạn worker, số worker đang dùng, quota, tài nguyên hoặc chính sách DBMS. Không thể kết luận DOP thực tế bằng 8 chỉ vì Workers Planned là 8.

Nếu các worker xử lý số hàng rất khác nhau, hãy kiểm tra phân phối dữ liệu và predicate. Nếu tất cả worker đều có số hàng tương đương nhưng CPU cao, có thể workload CPU-bound. Nếu worker chờ I/O, tăng worker có thể chỉ làm tăng queue.

Với SQL Server, Actual Execution Plan cần được đọc cùng runtime counters và thread distribution. Với Oracle, SQL Monitor hoặc PX views có thể giúp xem worker. Với MySQL, nếu truy vấn không có intra-query parallel plan, hãy đo concurrency giữa connection và background thread thay vì tìm DOP không tồn tại.

## 11. Thiết lập giới hạn CPU ở tầng hệ điều hành và nền tảng

Trước khi điều chỉnh DBMS, hãy xác nhận năng lực CPU thực tế:

1. Đọc số CPU logic và physical core trên host.
2. Xác định VM có bao nhiêu vCPU và có dấu hiệu CPU ready/steal hay không.
3. Kiểm tra container CPU quota, cpuset và throttling.
4. Kiểm tra CPU affinity của tiến trình database.
5. Xác định CPU được cấp có thay đổi theo thời gian hoặc burst credit không.
6. Đối chiếu với cấu hình worker/DOP của DBMS.

Ví dụ trên Linux:

~~~bash
# CPU topology
lscpu

# cgroup v2: quota/period và trạng thái throttling
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
~~~

Các đường dẫn có thể khác nếu hệ thống dùng cgroup v1 hoặc mount cgroup khác. Trong container, cần đọc cgroup namespace mà tiến trình thực sự chịu giới hạn.

Không nên đặt max worker bằng số CPU logic nhìn thấy nếu CPU quota thấp hơn nhiều. DBMS có thể tạo nhiều worker hơn năng lực CPU được cấp, làm tăng context switching và latency.

## 12. Đặt giới hạn parallelism trong DBMS

Một cấu hình tốt cần có giới hạn theo cả instance và truy vấn.

### 12.1. Giới hạn per-query

Giới hạn DOP per-query ngăn một truy vấn chiếm quá nhiều CPU. Điều chỉnh theo:

- Kích thước và loại truy vấn.
- Số truy vấn song song có thể chạy cùng lúc.
- Mục tiêu p95/p99 của workload khác.
- Số CPU khả dụng sau khi trừ background tasks.
- Khả năng chia đều dữ liệu.

### 12.2. Giới hạn toàn instance

Giới hạn tổng parallel workers ngăn tổng số worker vượt quá ngân sách. Cần dành năng lực cho:

- Connection và query worker thông thường.
- WAL/redo/log writer.
- Checkpoint và background I/O.
- Replication sender/receiver/apply.
- Vacuum, purge, statistics và maintenance.
- Monitoring, backup và hệ điều hành.

### 12.3. Resource group hoặc workload group

Nếu DBMS hỗ trợ, có thể phân loại workload theo nhóm:

- OLTP interactive: ưu tiên độ trễ, DOP thấp.
- Reporting: DOP cao hơn nhưng giới hạn concurrency.
- ETL: chạy theo lịch, giới hạn CPU và I/O.
- Maintenance: dùng ngân sách riêng trong cửa sổ bảo trì.

Resource governance giúp tránh việc một truy vấn lớn chiếm toàn bộ tài nguyên. Tuy nhiên, giới hạn quá thấp có thể kéo dài thời gian job và tăng thời gian giữ snapshot/transaction. Cần đo cả hai phía.

## 13. CPU capacity và memory/I/O có liên hệ với nhau

Parallel worker thường cần thêm memory, buffer hoặc cấu trúc trung gian. Khi DOP tăng:

- Nhiều worker có thể cùng tạo hash table hoặc sort run.
- Memory grant tổng có thể tăng.
- Cache và buffer pool chịu áp lực lớn hơn.
- I/O đồng thời tăng, làm storage queue dài hơn.
- Exchange buffer và queue cần thêm bộ nhớ.

Một truy vấn CPU-bound có thể tăng tốc khi tăng DOP, nhưng nếu sau đó sort/hash spill ra đĩa hoặc storage bão hòa, hiệu năng có thể giảm. Khi điều tra, không tách CPU khỏi memory, I/O và network.

Ví dụ, Hash Join song song có thể tạo hash partition cho worker. Nếu dữ liệu lệch hoặc memory grant thấp, một số worker spill nhiều hơn. Tăng DOP có thể làm tổng memory requirement lớn hơn và khiến spill trầm trọng.

## 14. Quy trình benchmark DOP

### Bước 1: Chọn truy vấn đại diện

Chọn truy vấn có CPU time đáng kể hoặc có thể hưởng lợi từ parallel scan/join/aggregate. Không chọn một truy vấn nhỏ chỉ vì muốn thử DOP.

### Bước 2: Ghi đường cơ sở

Thu thập:

- Execution plan và estimated/actual rows.
- CPU time, elapsed time.
- Logical/physical reads và I/O latency.
- DOP/worker count.
- Memory usage, grant và spill.
- CPU host/container, run queue và throttling.
- p95/p99 của workload nền.

### Bước 3: Thử các mức DOP có kiểm soát

Ví dụ với máy có năng lực CPU tương đương 16 core, có thể thử mức 1, 2, 4 và 8 cho một truy vấn phân tích. Đây chỉ là dải thử nghiệm minh họa; giới hạn thực tế phải dựa trên quota, workload và chính sách DBMS.

Giữ nguyên dữ liệu, tham số, cache condition và concurrency khi so sánh. Nếu thay đổi nhiều yếu tố cùng lúc, khó xác định nguyên nhân cải thiện.

### Bước 4: Đo dưới tải đồng thời

Sau khi đo truy vấn đơn, chạy nhiều request đại diện cùng lúc. Một DOP tối ưu cho một truy vấn riêng lẻ có thể làm tổng throughput giảm khi nhiều truy vấn cùng chạy.

### Bước 5: Tìm điểm bão hòa

Nếu DOP tăng nhưng elapsed time gần như không giảm, trong khi CPU, queue, memory hoặc I/O tăng, đã đến vùng lợi ích giảm dần. Chọn mức DOP thấp hơn có throughput tổng thể tốt hơn.

### Bước 6: Kiểm tra worker imbalance

So sánh số hàng, CPU time, elapsed time và bytes theo worker. Nếu một worker chậm hơn nhiều, điều tra skew hoặc phân phối partition trước khi tăng DOP.

### Bước 7: Đánh giá workload khác

Kiểm tra truy vấn OLTP, commit latency, replication, maintenance và p95/p99. Cấu hình chỉ tốt khi tổng workload đáp ứng SLO.

## 15. Ví dụ: DOP cao làm giảm throughput tổng thể

Giả sử một máy chủ có CPU quota tương đương 8 core. Có hai loại truy vấn:

- Truy vấn A: báo cáo scan lớn, có thể hưởng lợi từ DOP.
- Truy vấn B: OLTP ngắn, cần latency thấp và có nhiều session đồng thời.

Nếu đặt DOP 8 cho A và chạy đồng thời nhiều bản báo cáo, các worker của A có thể chiếm phần lớn CPU quota. Truy vấn B phải chờ scheduler dù bản thân nó chỉ cần ít CPU.

Một chiến lược có thể thử:

- Giới hạn DOP của báo cáo ở mức thấp hơn.
- Giới hạn số báo cáo chạy đồng thời.
- Dành CPU cho workload OLTP.
- Chạy báo cáo ngoài giờ cao điểm hoặc trên replica/warehouse.
- Theo dõi CPU throttling, run queue và p95 của B.

Nếu DOP thấp hơn làm thời gian một báo cáo tăng nhẹ nhưng throughput OLTP và độ trễ tổng thể cải thiện, đó có thể là lựa chọn tốt hơn cho hệ thống.

## 16. Các dấu hiệu chẩn đoán và hướng xử lý

| Triệu chứng | Khả năng | Hướng kiểm tra |
|---|---|---|
| CPU gần 100%, run queue cao | CPU capacity thiếu hoặc workload quá nặng | Xem top query, CPU time, DOP, quota và concurrency |
| CPU thấp nhưng truy vấn chậm | I/O, lock, network, worker wait hoặc quota/VM scheduling | Xem wait events, I/O latency, throttling và CPU ready |
| Workers planned nhiều nhưng launched ít | Worker limit hoặc tài nguyên runtime thiếu | Xem max worker, active workers, queue và cấu hình DBMS |
| DOP tăng nhưng latency không giảm | Phần tuần tự, skew, exchange overhead hoặc I/O bottleneck | Đọc plan theo operator và số liệu per-worker |
| DOP cao làm OLTP chậm | Oversubscription hoặc resource contention | Giới hạn DOP/concurrency, workload group |
| Một worker chạy lâu hơn nhiều | Data skew hoặc partition imbalance | Xem rows/bytes/CPU theo worker và phân phối key |
| Container CPU cao bất thường dù host còn rảnh | CPU quota throttling | Đọc cgroup cpu.stat và CPU limit |
| VM CPU thấp nhưng request chậm | Hypervisor scheduling/steal hoặc burst credit | Xem metric VM/host và loại instance |
| Nhiều context switch, throughput thấp | Quá nhiều runnable thread hoặc worker | Giảm DOP/concurrency, kiểm tra thread pool |

## 17. Những sai lầm thường gặp

- **Đồng nhất logical processor với physical core.** SMT không tạo thêm một lõi vật lý đầy đủ.
- **Đồng nhất vCPU với công suất được bảo đảm.** Hypervisor và cloud quota có thể giới hạn thời gian CPU.
- **Chỉ nhìn số CPU trong container.** Cần xem quota, cpuset và throttling.
- **Đặt DOP bằng số lõi cho mọi truy vấn.** Workload và concurrency khác nhau.
- **Cho rằng planned workers là actual workers.** Runtime có thể cấp ít worker hơn.
- **Tăng DOP để chữa mọi truy vấn chậm.** Nếu bottleneck là I/O hoặc lock, parallelism có thể làm tình hình xấu hơn.
- **Đọc CXPACKET/CXCONSUMER như lỗi độc lập.** Wait cần được phân tích cùng plan và worker imbalance.
- **Bỏ qua background tasks.** Replication, checkpoint, vacuum, backup và maintenance cũng dùng CPU.
- **Tối ưu truy vấn đơn lẻ mà bỏ qua workload.** Một query nhanh hơn có thể làm p99 của hệ thống xấu đi.
- **Coi số worker nhiều là throughput cao.** Oversubscription có thể tăng context switch và giảm hiệu quả.
- **Không kiểm tra NUMA/affinity.** Worker và memory locality có thể làm hiệu năng thay đổi.

## 18. Checklist đánh giá CPU và parallelism

- [ ] Đã xác định physical core, logical processor, vCPU và CPU quota.
- [ ] Đã kiểm tra CPU affinity, cpuset, NUMA và VM scheduling nếu có.
- [ ] Đã đo CPU throttling, run queue và context switch.
- [ ] Đã phân biệt CPU-bound với I/O-bound, lock-bound và worker-bound.
- [ ] Đã thu thập requested, planned và actual DOP/workers.
- [ ] Đã đọc execution plan để xác định operator nào thực sự chạy song song.
- [ ] Đã so sánh số hàng, CPU time và elapsed time theo worker.
- [ ] Đã kiểm tra skew, exchange/gather overhead và phần tuần tự.
- [ ] Đã tính cả concurrency của truy vấn và background worker.
- [ ] Đã kiểm tra giới hạn parallelism ở cấp query và instance.
- [ ] Đã phân nhóm OLTP, reporting, ETL và maintenance nếu DBMS hỗ trợ.
- [ ] Đã benchmark nhiều mức DOP với cùng dữ liệu và tham số.
- [ ] Đã benchmark dưới tải đồng thời và theo dõi p95/p99 của workload nền.
- [ ] Đã theo dõi memory grant, spill, I/O và cache khi tăng DOP.
- [ ] Đã chọn cấu hình theo throughput tổng thể và SLO thay vì tốc độ của một truy vấn.

Số lõi CPU chỉ mô tả một phần năng lực xử lý. Physical core, SMT, vCPU, quota, affinity và scheduler quyết định DBMS thực sự được chạy trên bao nhiêu CPU; DOP và worker budget quyết định một truy vấn có thể sử dụng phần năng lực đó như thế nào. Parallelism hữu ích khi công việc đủ lớn, chia đều và CPU là nút thắt. Khi workload bị giới hạn bởi I/O, lock, skew hoặc concurrency, tăng worker có thể làm tổng thể chậm hơn. Hãy đo actual workers, CPU time, elapsed time, worker imbalance, throttling và độ trễ workload dưới tải đại diện trước khi đặt giới hạn CPU và parallelism.
