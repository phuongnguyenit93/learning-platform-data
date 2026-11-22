# Dashboard theo mục tiêu dịch vụ, tài nguyên và truy vấn quan trọng

Trong chương **Vận hành hiệu năng** của module **DATABASE_PERFORMANCE**, dashboard hiệu năng là nơi kết nối mục tiêu dịch vụ với hoạt động thực tế của ứng dụng, database và hạ tầng. Một dashboard có ích phải giúp người vận hành trả lời được ba câu hỏi: dịch vụ có đang đáp ứng SLO không, tài nguyên nào đang giới hạn khả năng xử lý và truy vấn quan trọng nào đang tiêu thụ hoặc làm suy giảm năng lực hệ thống.

Dashboard không chỉ là tập hợp biểu đồ CPU, RAM và dung lượng đĩa. CPU thấp không chứng minh database khỏe nếu request đang chờ lock hoặc connection pool; IOPS cao không cho biết đó là table scan, random lookup hay backup; query chậm nhất chưa chắc là query gây tổng tải lớn nếu nó chỉ chạy một lần. Vì vậy, dashboard cần tổ chức theo mục tiêu dịch vụ, liên kết metric ứng dụng với wait event, query fingerprint, execution plan, cache, log, I/O và xu hướng dữ liệu.

Thiết kế dashboard tốt bắt đầu từ SLI/SLO và câu hỏi vận hành, sau đó mới chọn metric, nguồn dữ liệu, độ phân giải, cảnh báo và drill-down. Mỗi biểu đồ cần có đơn vị, phạm vi, cửa sổ thời gian, cách tổng hợp và hành động tiếp theo rõ ràng. Dashboard phải đủ nhanh để phát hiện sự cố, đủ chi tiết để điều tra và đủ ổn định để so sánh trước/sau deployment.

## 1. Dashboard cần phục vụ quyết định nào?

Một dashboard nên giúp các vai trò khác nhau thực hiện công việc cụ thể:

- **Đội ứng dụng:** xác định endpoint nào chậm, request có bao nhiêu lần gọi database, thời gian chờ connection và query nào chiếm nhiều thời gian.
- **DBA/database engineer:** xác định query fingerprint, execution plan, reads, writes, wait events, lock, log flush và replication lag.
- **Đội hạ tầng:** xác định CPU, memory, storage, network hoặc quota nào gần bão hòa.
- **SRE/operations:** đánh giá SLO, error budget, xu hướng, cảnh báo và tác động của incident.
- **Quản lý capacity:** dự báo tăng trưởng, headroom và thời điểm cần mở rộng.

Không nên nhồi tất cả dữ liệu vào một màn hình duy nhất. Có thể thiết kế một dashboard tổng quan với các chỉ số dẫn đường và các dashboard chuyên sâu cho dịch vụ, database, truy vấn, storage và capacity. Các dashboard cần dùng chung tên workload, environment, database, service và deployment version để drill-down không bị đứt mạch.

### 1.1. Ba lớp câu hỏi chính

| Lớp | Câu hỏi | Bằng chứng cần có |
|---|---|---|
| Mục tiêu dịch vụ | Người dùng có đang nhận dịch vụ đúng cam kết? | Availability, request rate, p95/p99, error/timeout, SLO burn rate |
| Tài nguyên | Hệ thống đang chờ hoặc bão hòa ở đâu? | CPU, memory, I/O, queue, connection, lock, log, network |
| Truy vấn quan trọng | SQL nào tạo ra chi phí hoặc regression? | Fingerprint, calls, total/mean latency, reads, writes, rows, plan, waits |

Ba lớp phải được xem cùng thời điểm. Nếu p99 API tăng nhưng database query latency ổn định, có thể bottleneck nằm ở application worker, connection pool hoặc network. Nếu API và database query cùng chậm, cần drill-down tới plan và wait event. Nếu query nhanh nhưng tổng calls tăng gấp mười, tổng chi phí vẫn có thể tăng mạnh.

## 2. Bắt đầu từ SLI, SLO và workload class

SLI (*Service Level Indicator*) là chỉ số đo chất lượng dịch vụ. SLO (*Service Level Objective*) là mục tiêu định lượng cho SLI trong một cửa sổ thời gian. Dashboard nên hiển thị SLO ở vị trí nổi bật để người xem hiểu số liệu tài nguyên có ý nghĩa gì đối với người dùng.

### 2.1. Chọn SLI theo trải nghiệm người dùng

Các SLI phổ biến:

- **Availability:** tỷ lệ request hợp lệ được xử lý thành công.
- **Latency:** thời gian từ lúc request đến hệ thống tới khi có kết quả.
- **Throughput:** số request hoặc transaction hoàn tất mỗi giây.
- **Correctness:** tỷ lệ kết quả hợp lệ theo quy tắc nghiệp vụ, nếu có thể đo tự động.
- **Freshness:** độ mới của dữ liệu, đặc biệt với replica, CDC và hệ thống tổng hợp.

Ví dụ SLO minh họa:

| Workload | SLI | Mục tiêu mẫu |
|---|---|---:|
| API tra cứu đơn hàng | p95 latency | dưới 150 ms |
| API ghi thanh toán | p99 latency | dưới 300 ms |
| Request đọc hợp lệ | Availability | 99,9% trong 30 ngày |
| Dashboard doanh thu | Data freshness | lag dưới 30 giây |
| API đọc từ replica | Replication lag | p95 dưới 2 giây |

Các ngưỡng trên chỉ là ví dụ. Mục tiêu thực tế phải được thống nhất theo yêu cầu sản phẩm, hợp đồng dịch vụ và đặc điểm traffic. Không dùng một SLO chung cho endpoint tương tác và báo cáo dài nếu chúng có yêu cầu khác nhau.

### 2.2. Tách workload class

Phân nhóm request/query theo hành vi và yêu cầu dịch vụ:

- OLTP read: point lookup, range lookup, danh sách có phân trang.
- OLTP write: insert/update/delete và transaction commit.
- Read-after-write hoặc truy vấn cần dữ liệu mới nhất.
- Reporting/analytics: scan, join, aggregate và query dài.
- Batch/ETL: ingest, export, cleanup và xử lý theo lô.
- Background maintenance: checkpoint, vacuum/purge, backup và index maintenance.

Dashboard tổng quan có thể hiển thị SLO của từng nhóm. Dashboard chuyên sâu cần cho phép lọc theo workload class để báo cáo dài không che mất tình trạng API giao dịch.

### 2.3. Định nghĩa chính xác mẫu số và phạm vi

Tỷ lệ thành công phải xác định request nào được tính, loại trừ lỗi client hay không và cách tính retry. Latency cần xác định đo từ thời điểm nào tới thời điểm nào. Throughput cần phân biệt request đến, request được chấp nhận và request hoàn tất.

Ví dụ, nếu API trả HTTP 200 nhưng bên trong đã timeout một query phụ và trả dữ liệu thiếu, chỉ đếm HTTP status có thể đánh giá availability quá lạc quan. Nếu retry được tính thành request riêng, throughput có thể tăng dù số thao tác nghiệp vụ hoàn tất không tăng. Ghi định nghĩa metric ngay trong mô tả panel hoặc tài liệu dashboard.

## 3. Cấu trúc dashboard tổng quan

Một trang tổng quan nên dẫn người xem từ tác động tới nguyên nhân. Có thể bố trí theo thứ tự:

1. SLO và tình trạng dịch vụ.
2. Request rate, throughput hoàn tất và error/timeout.
3. Latency p50/p95/p99 theo workload class.
4. Application queue và database connection pool.
5. Database waits, active sessions và transaction.
6. CPU, memory, I/O, log và network.
7. Top query fingerprint theo latency và tổng chi phí.
8. Deployment marker, migration và tác vụ nền.
9. Replication lag, dung lượng và capacity headroom.

Mỗi panel tổng quan cần liên kết tới một màn hình chi tiết. Ví dụ, click vào p99 của API có thể mở trace; từ trace mở query fingerprint; từ fingerprint mở execution plan và wait metrics. Nếu hệ thống monitoring hỗ trợ template variable, các dashboard nên dùng chung bộ lọc `environment`, `service`, `database`, `instance`, `workload` và `time range`.

### 3.1. Bảng trạng thái ở đầu dashboard

Một bảng trạng thái ngắn có thể hiển thị:

| Thành phần | Trạng thái cần thể hiện | Liên kết chi tiết |
|---|---|---|
| API giao dịch | SLO, p95/p99, error rate | Dashboard service và traces |
| Primary database | Query throughput, active sessions, waits | Dashboard database |
| Read replicas | Health, lag, apply rate | Dashboard replication |
| Storage | Latency, queue, free space | Dashboard I/O và capacity |
| Critical queries | Top regression, plan change | Dashboard query |
| Background jobs | Backup, vacuum, checkpoint, ETL | Dashboard operations |

Không dùng màu xanh/đỏ làm thông tin duy nhất. Hiển thị giá trị, ngưỡng, thời gian duy trì và trạng thái dữ liệu cập nhật gần nhất để người xem hiểu lý do panel đổi trạng thái.

## 4. Dashboard theo mục tiêu dịch vụ

### 4.1. Request rate và throughput hoàn tất

Nên hiển thị riêng:

- Offered/request arrival rate.
- Accepted rate.
- Completed success rate.
- Failed/rejected/timeout rate.
- Retry rate.
- Queue depth hoặc tuổi request/message cũ nhất.

Sự khác biệt giữa arrival và completion cho thấy backlog có đang tích lũy hay không. Nếu arrival ổn định ở 500 request/giây nhưng completion giảm còn 350, queue có thể tăng dù server vẫn nhận request.

### 4.2. Latency percentile

Hiển thị p50, p95 và p99 theo endpoint/workload class. Average latency có thể dùng làm tín hiệu phụ nhưng không thay thế percentile vì một nhóm nhỏ request rất chậm có thể gây trải nghiệm xấu.

Khi dùng histogram phân tán trên nhiều instance, cần merge bucket/count rồi tính percentile trên phân phối chung. Không lấy trung bình p99 của từng instance để tạo p99 toàn hệ thống. Histogram phải có bucket đủ chi tiết quanh ngưỡng SLO và vùng tail.

### 4.3. Error rate và SLO burn rate

Error rate nên được tách theo loại:

- Lỗi ứng dụng.
- Database timeout hoặc connection failure.
- Lock timeout/deadlock.
- Reject do admission control hoặc pool full.
- Lỗi downstream như replica hoặc network.
- Lỗi client theo chính sách SLI.

Burn rate cho biết tốc độ tiêu thụ error budget so với mức cho phép. Cảnh báo burn rate cao trong cửa sổ ngắn giúp phát hiện incident nhanh; cửa sổ dài giúp phát hiện suy giảm kéo dài. Cách tính cụ thể phụ thuộc định nghĩa SLO và hệ thống alerting.

### 4.4. Data freshness

Với workload đọc từ replica, dashboard cần hiển thị replication lag và thời điểm dữ liệu gần nhất. Với CDC hoặc materialized view, hiển thị tuổi bản ghi/offset đã xử lý. Một API có latency tốt nhưng trả dữ liệu quá cũ vẫn không đạt yêu cầu nghiệp vụ.

## 5. Dashboard tài nguyên CPU

CPU utilization cần xem cùng throughput, latency và run queue. Một mức CPU cao nhưng latency ổn định có thể là sử dụng hiệu quả; CPU thấp nhưng query chờ lock hoặc I/O không phải bằng chứng còn nhiều capacity hữu ích.

### 5.1. Panel CPU nên có

- CPU utilization tổng và theo core.
- User/system/steal/iowait nếu hệ điều hành cung cấp.
- Run queue hoặc runnable threads.
- CPU throttling của container/VM.
- Context switches và interrupt nếu có liên quan.
- CPU time theo query fingerprint hoặc workload class.
- CPU per transaction/request.

### 5.2. Chuẩn hóa CPU theo công việc

\[
CPU\ per\ transaction = \frac{CPU\ time}{Completed\ transactions}
\]

Nếu CPU utilization tăng vì transaction rate tăng tương ứng, hệ thống có thể vẫn hiệu quả. Nếu CPU/transaction tăng trong khi query mix không đổi, có thể có plan regression, số lần gọi tăng, dữ liệu cần xử lý lớn hơn hoặc contention làm phát sinh công việc dư thừa.

### 5.3. Tránh diễn giải CPU sai

- CPU tổng thấp không loại trừ một core hoặc một worker bị bão hòa.
- CPU cao không tự động chứng minh thiếu vCPU; query có thể thực hiện scan/join dư thừa.
- I/O wait cao cần xem storage và workload; không nên cộng cơ học vào CPU user/system.
- Container CPU limit có thể gây throttling dù host còn CPU rảnh.
- Parallel query có thể tăng CPU nhưng giảm elapsed time; phải đo throughput và tác động workload khác.

## 6. Dashboard memory và cache

Memory panel cần phân biệt RAM vật lý, memory database dùng, cache hit, memory grant/workspace và memory pressure.

### 6.1. Chỉ số nên theo dõi

- Available/used memory của host và container.
- Swap-in/swap-out, major page faults và OOM events.
- Database buffer pool/cache size và hit/miss.
- Page eviction, cache churn và working set.
- Memory grant requested/granted/used.
- Sort/hash spill và temp bytes.
- Memory theo session/worker nếu engine hỗ trợ.

### 6.2. Cache hit ratio không phải mục tiêu duy nhất

Cache hit ratio cao không đảm bảo query nhanh nếu một truy vấn đọc quá nhiều page logic. Cache hit ratio tổng thể có thể che một query nóng bị miss hoặc một tenant working set không nằm trong memory.

Nên hiển thị thêm physical reads/request, logical reads/request, page read latency và cache eviction. Khi cache hit giảm, kiểm tra data growth, workload mới, memory pressure, scan lớn và cấu hình buffer pool.

### 6.3. Theo dõi spill

Temp spill tăng có thể là dấu hiệu memory grant không đủ, estimate sai hoặc concurrency cao. Panel cần liên kết tới query fingerprint và execution plan có sort/hash spill. Không chỉ tăng memory theo tổng số spill; cần xem query tạo intermediate result lớn hay optimizer ước lượng sai.

## 7. Dashboard storage và I/O

I/O panel phải tách data, log, temp và backup nếu có thể. Một volume có thể dùng chung nhiều loại file; khi đó cần hiển thị topology hoặc ghi chú backend dùng chung.

### 7.1. Chỉ số cốt lõi

- Read IOPS và write IOPS.
- Read throughput và write throughput.
- Average request size.
- Queue depth/average queue length.
- Read/write latency, ưu tiên p95/p99 nếu backend hỗ trợ.
- Device utilization hoặc busy time.
- Free space, growth rate và provisioned limit.
- Burst credits hoặc throttling nếu là cloud storage.

### 7.2. Phân biệt scan và random access

| Mẫu | Dấu hiệu thường gặp | Drill-down |
|---|---|---|
| Scan lớn | Read throughput cao, request có thể lớn, nhiều page | Query plan, scan rows, backup/report job |
| Random lookup | IOPS cao, request nhỏ, cache miss và latency từng request | Index lookup, nested-loop loops, working set |
| Ghi nền | Write throughput/queue tăng theo chu kỳ | Checkpoint, vacuum/purge, rebuild, batch, backup |
| Log flush | Commit latency và log wait tăng | Log volume, fsync/flush, group commit, durability path |
| Temp spill | Temp reads/writes tăng khi query chạy | Sort/hash, memory grant, cardinality estimate |

IOPS cao không nhất thiết là storage đã bão hòa; throughput cao không nhất thiết là query chính đang tạo tải. Đối chiếu database counters, process, file/volume và storage backend trong cùng khoảng thời gian.

### 7.3. Dashboard theo file hoặc volume

Nếu database đặt data, log và temp trên các volume khác nhau, hãy hiển thị từng volume. Nếu volume là logical disk trên SAN, RAID hoặc cloud pool, thêm metric backend để không nhầm tách mount point với tách tài nguyên vật lý.

## 8. Dashboard transaction log, checkpoint và commit

Workload ghi có thể bị giới hạn bởi transaction log dù data volume còn rảnh.

### 8.1. Metric cần có

- Log bytes generated per second.
- Log flushes/second và flush latency.
- p95/p99 commit latency.
- Số transaction mỗi lần flush/group commit nếu engine cung cấp.
- Checkpoint duration, dirty pages và write rate.
- Archive/log shipping backlog.
- Log file size, free space và autogrowth.
- Replication send/apply lag.

### 8.2. Diễn giải

Nếu commit p99 tăng cùng log flush latency, kiểm tra log device, flush semantics và group commit. Nếu write I/O tăng theo chu kỳ checkpoint nhưng commit vẫn ổn định, tác động có thể chủ yếu nằm ở data write. Nếu log generation vượt archive/replication throughput, backlog có thể tích tụ và đe dọa dung lượng.

Không tắt durability hoặc flush để làm dashboard xanh. Hãy giữ yêu cầu phục hồi và tối ưu transaction size, batch, log storage, group commit hoặc lịch ghi nền.

## 9. Dashboard connection pool, sessions và concurrency

Nhiều request chậm bắt nguồn từ việc chờ connection hoặc worker, không phải thời gian database thực thi SQL.

### 9.1. Chỉ số ứng dụng

- Pool size, active, idle và pending/waiting connections.
- Connection acquisition latency p95/p99.
- Connection timeout và pool exhaustion.
- Connection lifetime, idle timeout và số lần tạo mới.
- Số transaction đang hoạt động và thời lượng transaction.

### 9.2. Chỉ số database

- Active/idle sessions.
- Sessions đang chạy, chờ lock hoặc chờ I/O.
- Worker/thread utilization và queue.
- Transaction age và idle-in-transaction.
- Deadlock, lock wait và blocking chain.

### 9.3. Không tăng pool chỉ vì có request đang chờ

Pool chờ có thể do pool quá nhỏ, nhưng cũng có thể do query chậm giữ connection lâu hoặc database đã bão hòa. Tăng pool trong trường hợp thứ hai làm concurrency tăng, tạo thêm lock, memory và I/O pressure. Dashboard phải đặt pool wait cạnh query latency, active sessions, DB waits và CPU/I/O.

## 10. Dashboard wait events và contention

Wait event cho biết session đang chờ loại tài nguyên hoặc sự kiện nào. Đây là lớp thông tin quan trọng để phân biệt CPU-bound, I/O-bound, lock-bound và log-bound.

### 10.1. Nhóm wait nên phân loại

- **Lock/blocking:** chờ transaction khác nhả khóa.
- **I/O:** chờ page/file read/write.
- **Log/commit:** chờ flush transaction log.
- **Memory/workspace:** chờ memory grant hoặc tài nguyên xử lý.
- **Latch/internal synchronization:** tranh chấp cấu trúc nội bộ.
- **Network/client:** chờ client hoặc trao đổi qua mạng.
- **Worker/scheduler:** chờ worker hoặc CPU scheduling.

Tên wait khác nhau theo engine. Không cộng thời gian wait của các session một cách máy móc rồi so với wall-clock; nhiều session có thể chờ song song. Dashboard nên hiển thị rate, tổng thời gian, số session, query và xu hướng trong cùng cửa sổ.

### 10.2. Lock dashboard

Hiển thị:

- Số session blocked và blocking.
- Blocking chain dài nhất.
- Tuổi transaction blocker.
- Lock wait time và deadlock count.
- Query fingerprint của blocker và waiter.
- Table/index/key hoặc resource liên quan nếu engine cung cấp.

Khi alert lock wait, cần drill-down tới transaction giữ khóa lâu. Không tự động kill session dựa trên một ngưỡng duy nhất; cần xem rollback cost, nghiệp vụ và khả năng gây lỗi dây chuyền.

## 11. Dashboard truy vấn quan trọng

Query dashboard nên trả lời hai câu hỏi riêng: truy vấn nào chậm nhất theo mỗi lần gọi và truy vấn nào tiêu tốn tổng tài nguyên nhiều nhất.

### 11.1. Các chỉ số theo query fingerprint

- Query ID/fingerprint và tên workload.
- Calls/executions.
- Total elapsed time và mean latency.
- p95/p99 nếu hệ thống thu thập được ở cấp query.
- CPU time/worker time.
- Logical reads/buffer gets.
- Physical reads/disk reads.
- Logical/physical writes.
- Rows examined, returned hoặc affected.
- Temp reads/writes và spill.
- Lock/wait time nếu có thể liên kết.
- Plan hash/plan identity và thời điểm plan thay đổi.
- Last seen, deployment version hoặc application name.

### 11.2. Hai bảng xếp hạng cần có

**Top latency per execution:** tìm query có một lần chạy rất chậm, ví dụ báo cáo hoặc truy vấn có plan xấu.

**Top total resource cost:** tìm query có tổng CPU, elapsed, reads hoặc writes lớn. Query 3 ms chạy 500.000 lần có thể quan trọng hơn query 3 giây chạy một lần.

Không xếp hạng tất cả loại tài nguyên bằng một điểm tổng hợp không giải thích được. Có thể có các tab riêng cho CPU, logical reads, physical reads, writes, total elapsed và calls.

### 11.3. Chuẩn hóa SQL và bảo vệ dữ liệu

Dùng fingerprint hoặc normalized SQL để nhóm câu lệnh khác bind value. Không đưa raw SQL với literal, user id, email, token hoặc giá trị nhạy cảm vào metric label. Nếu cần xem SQL text để điều tra, dùng công cụ có phân quyền, masking và retention phù hợp.

### 11.4. Phát hiện N+1 và query count tăng

Dashboard theo request có thể hiển thị số SQL statement, JDBC spans và query fingerprint count. Nếu một endpoint tăng từ 4 query/request lên 40 query/request sau deployment, đó là dấu hiệu ORM hoặc mapper có thể phát sinh N+1. Cần drill-down tới trace và nhóm SQL lặp, sau đó kiểm tra fetch plan.

### 11.5. Query regression và plan change

Hiển thị plan identity cùng latency/reads/CPU theo thời gian. Khi plan thay đổi, đánh dấu thời điểm và so actual rows với estimated rows, join order, scan/lookup, loops, memory grant và spill. Plan hash thay đổi không tự động là regression; cần xác nhận chi phí thực tế.

## 12. Nguồn dữ liệu theo hệ quản trị

Dashboard có thể lấy metric từ exporter/agent, database system views, APM, log và cloud monitoring. Tên view và cột phụ thuộc phiên bản, quyền và cấu hình. Các counter tích lũy cần được lấy snapshot và tính delta.

### 12.1. PostgreSQL

Nguồn thường dùng:

- `pg_stat_statements`: calls, execution time, rows, shared blocks, temp blocks theo query identity.
- `pg_stat_activity`: session, state, query age và wait event.
- `pg_locks`: thông tin lock và quan hệ với session.
- `pg_stat_database`: transaction, block activity, temp bytes và deadlocks.
- `pg_stat_user_tables`: tuple counts, dead tuples, vacuum/analyze history.
- `pg_stat_io` từ PostgreSQL 16: I/O theo backend type/object/context.
- `pg_stat_replication` và các hàm WAL trên primary/standby: trạng thái gửi, flush và replay.
- `pg_stat_checkpointer` trên các phiên bản mới hoặc view checkpoint tương ứng phiên bản.

Ví dụ panel top query theo tổng thời gian:

```sql
SELECT queryid,
       calls,
       total_exec_time,
       mean_exec_time,
       rows,
       shared_blks_hit,
       shared_blks_read,
       temp_blks_read,
       temp_blks_written,
       query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Ví dụ panel session đang chạy/chờ:

```sql
SELECT pid,
       application_name,
       state,
       wait_event_type,
       wait_event,
       now() - query_start AS query_age,
       left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
```

Các truy vấn này là nguồn snapshot; không polling quá dày nếu chưa đo overhead. `pg_stat_statements` cần cài/bật và có thể reset; `pg_stat_io` chỉ có trên phiên bản hỗ trợ; một số timing phụ thuộc cấu hình. Dashboard phải ghi rõ version compatibility và trạng thái metric collection.

### 12.2. MySQL/InnoDB

Nguồn thường dùng:

- Performance Schema statement digest summary.
- `events_statements_current` và history tables nếu được cấu hình.
- `table_io_waits_summary_by_table`.
- `file_summary_by_instance`.
- `SHOW GLOBAL STATUS` và InnoDB metrics.
- `SHOW ENGINE INNODB STATUS` cho transaction, lock, buffer pool, purge và checkpoint clues.
- Replication status và GTID state.

Ví dụ top statement digest:

```sql
SELECT SCHEMA_NAME,
       DIGEST,
       COUNT_STAR,
       SUM_TIMER_WAIT,
       AVG_TIMER_WAIT,
       SUM_ROWS_EXAMINED,
       SUM_ROWS_SENT,
       SUM_CREATED_TMP_DISK_TABLES,
       DIGEST_TEXT
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Timer Performance Schema thường được biểu diễn theo picosecond. Bảng summary có thể reset và instrumentation có thể được tắt để giảm overhead; cần theo dõi tính đầy đủ của dữ liệu. Không lưu toàn bộ bind value nhạy cảm vào dashboard.

### 12.3. SQL Server

Nguồn thường dùng:

- Query Store: query, plan và runtime statistics theo interval.
- `sys.dm_exec_query_stats`: counter theo plan cache.
- `sys.dm_exec_requests`: request đang chạy, wait và elapsed time.
- `sys.dm_os_wait_stats`: wait statistics tích lũy.
- `sys.dm_io_virtual_file_stats`: file I/O count, bytes và stall time.
- `sys.dm_db_index_usage_stats`: số lần seek/scan/update theo index từ lúc counter được khởi tạo.
- Performance Monitor counters và Extended Events cho điều tra chuyên sâu.

Ví dụ query top logical reads từ plan cache:

```sql
SELECT TOP (20)
       qs.execution_count,
       qs.total_logical_reads,
       qs.total_physical_reads,
       qs.total_worker_time,
       qs.total_elapsed_time,
       st.text
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
ORDER BY qs.total_logical_reads DESC;
```

DMV plan cache counter có thể mất khi plan bị evict hoặc instance restart. Query Store thường phù hợp hơn để so lịch sử, nhưng cần cấu hình capture, retention và dung lượng. DMV/permission phụ thuộc phiên bản SQL Server và quyền được cấp.

### 12.4. Oracle

Nguồn thường dùng:

- `V$SQL`: executions, elapsed, CPU, buffer gets, disk reads và plan hash.
- `V$SESSION`: session, wait, SQL_ID, blocking session và module/action.
- `V$SYSTEM_EVENT`/`V$SESSION_EVENT`: wait event.
- `V$IOSTAT_FILE` và các view file I/O tương ứng phiên bản.
- `V$SQL_PLAN` hoặc plan display để xem execution plan.
- AWR/ASH khi môi trường có quyền và license phù hợp.

Ví dụ top SQL theo disk reads:

```sql
SELECT sql_id,
       plan_hash_value,
       executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       rows_processed,
       sql_text
FROM v$sql
ORDER BY disk_reads DESC
FETCH FIRST 20 ROWS ONLY;
```

Các view dynamic có counter theo cursor và có thể thay đổi khi cursor aging hoặc instance restart. AWR/ASH và một số tính năng chẩn đoán có điều kiện license/edition; chỉ sử dụng theo quyền của tổ chức. Dashboard cần ghi rõ nguồn và phạm vi dữ liệu.

## 13. Thiết kế metric và nhãn để tránh cardinality cao

Một dashboard có thể gây tải lớn cho monitoring backend nếu mỗi request tạo một metric series riêng.

### 13.1. Không dùng giá trị không giới hạn làm label

Tránh dùng các trường có số lượng giá trị gần như vô hạn:

- Raw SQL text hoặc bind parameter.
- User ID, order ID, email, session ID.
- URL chứa ID động hoặc query string tùy ý.
- Exception message đầy đủ.
- Timestamp chính xác.

Các label phù hợp hơn thường là environment, service, endpoint template, database, query fingerprint, workload class, status class và region. Query fingerprint cũng cần quản lý giới hạn số lượng nếu ứng dụng sinh SQL động không kiểm soát.

### 13.2. Metric và log/trace có vai trò khác nhau

- **Metric:** xu hướng, alert, aggregate và capacity.
- **Log:** sự kiện chi tiết, lỗi, thông báo và ngữ cảnh.
- **Trace:** đường đi của một request qua nhiều service/database call.
- **Query history/plan repository:** chi tiết fingerprint, plan và runtime.

Không nhồi toàn bộ SQL hoặc trace vào metric. Dashboard dùng metric để phát hiện, sau đó dẫn tới log/trace/query details khi điều tra.

### 13.3. Sampling và retention

Trace toàn bộ request có thể tốn storage/network. Có thể sampling request bình thường và tăng sampling cho lỗi hoặc latency cao nếu nền tảng hỗ trợ. Slow query log cần threshold phù hợp; threshold quá thấp tạo nhiều log, quá cao bỏ sót query nhanh nhưng lặp lại nhiều lần.

Giữ dữ liệu độ phân giải cao trong khoảng thời gian đủ cho incident investigation, rồi downsample/aggregate cho xu hướng dài hạn. Chính sách retention phải cân bằng chi phí, yêu cầu kiểm toán và nhu cầu phân tích.

### 13.4. Bảo vệ thông tin nhạy cảm

SQL text và bind values có thể chứa dữ liệu cá nhân, token hoặc thông tin thanh toán. Mask/redact trước khi lưu; giới hạn quyền truy cập; áp dụng retention và audit. Dashboard phổ thông nên hiển thị fingerprint, query sample đã chuẩn hóa hoặc tên nghiệp vụ thay cho giá trị tham số.

## 14. Thiết kế panel và cách trình bày

Một panel phải có tiêu đề mô tả đại lượng, đơn vị, phạm vi và cách tổng hợp.

### 14.1. Tiêu đề rõ ràng

Ví dụ tốt:

- `API checkout — p99 latency (ms), 5m window`.
- `Primary DB — completed transactions/s`.
- `orders query fingerprint — logical reads/call`.
- `Data volume — read IOPS and p95 latency`.
- `Replica A — replay lag (seconds)`.

Tránh tiêu đề mơ hồ như `Performance`, `Database status` hoặc `I/O` mà không nêu loại dữ liệu.

### 14.2. Chọn biểu đồ theo câu hỏi

| Loại biểu đồ | Phù hợp với | Lưu ý |
|---|---|---|
| Time series | Latency, throughput, CPU, I/O, lag | Dùng cùng time range và đơn vị |
| Stat/single value | Giá trị hiện tại và trạng thái SLO | Hiển thị last updated và threshold |
| Table | Top query, session, file, index | Có sort, filter và drill-down |
| Heatmap/histogram | Phân bố latency hoặc bucket | Cần bucket và sample count đủ tốt |
| Bar chart | So sánh workload/endpoint/resource | Không dùng quá nhiều series khó đọc |
| State timeline | Deployment, backup, checkpoint, failover | Dùng marker để liên hệ sự kiện |
| Scatter plot | Latency so với request rate hoặc rows | Hữu ích tìm vùng saturation/skew |

### 14.3. Hiển thị threshold và SLO

Vẽ đường SLO/threshold trên time series. Màu sắc chỉ hỗ trợ nhận biết, không thay thế con số. Hiển thị thời gian vượt ngưỡng và số request/sample trong cửa sổ để tránh diễn giải percentile từ sample quá nhỏ.

### 14.4. Đơn vị và quy đổi

Không trộn ms với seconds, bytes với MiB hoặc IOPS với MB/s trong cùng panel mà không ghi rõ. Chọn quy ước nhất quán và đặt tooltip giải thích. Ví dụ throughput nên ghi MB/s hoặc MiB/s chính xác; latency ghi ms; log rate ghi bytes/s hoặc MiB/s.

## 15. Biến lọc và drill-down

Các bộ lọc phổ biến:

- Environment: dev, staging, production.
- Service/application.
- Database/cluster/instance.
- Workload class hoặc endpoint template.
- Query fingerprint/SQL ID.
- Tenant class/region nếu cần và cardinality được kiểm soát.
- Deployment version.
- Time range.

Bộ lọc cần có giá trị mặc định hợp lý. Nếu không chọn instance, dashboard tổng quan nên hiển thị toàn cluster theo cách tổng hợp đúng; dashboard chi tiết cần cho phép chọn một node. Không để một biến lọc rỗng khiến query monitoring trả hàng triệu series.

### 15.1. Drill-down từ SLO tới query

Luồng điều tra mẫu:

```text
SLO panel: API p99 vượt ngưỡng
          |
          v
Endpoint panel: request nào chậm?
          |
          v
Trace: thời gian nằm ở pool, DB hay application?
          |
          v
Query fingerprint: SQL nào lặp/chậm/tốn reads?
          |
          v
Execution plan: scan, lookup, loops, spill, estimate?
          |
          v
Resource/wait: CPU, lock, I/O, log hay network?
          |
          v
Runbook: hành động an toàn và cách xác minh
```

Mỗi bước cần giữ nguyên time range, environment và workload context để tránh drill-down sang dữ liệu không liên quan.

## 16. Cảnh báo gắn với dashboard

Dashboard hiển thị tình trạng; alert thông báo khi cần hành động. Không phải mọi panel đều cần alert.

### 16.1. Alert theo SLO

Ưu tiên:

- p95/p99 vượt SLO trong thời gian đủ dài.
- Error/timeout rate tăng.
- Throughput hoàn tất giảm trong khi offered load ổn định.
- SLO burn rate cao.
- Queue age hoặc connection wait vượt ngưỡng.

### 16.2. Alert theo dấu hiệu tài nguyên

- Storage p95/p99 latency và queue tăng đồng thời.
- Log free space thấp hoặc log flush latency tăng.
- Memory pressure, swap hoặc OOM.
- CPU throttling hoặc run queue kéo dài.
- Replication lag tăng liên tục.
- Temp spill hoặc physical reads/request tăng đột biến.
- Dự báo volume chạm ngưỡng trước khi có thể provision thêm.

### 16.3. Kết hợp điều kiện

Một alert CPU 85% trong một phút có thể gây nhiễu nếu latency và throughput vẫn tốt. Có thể kết hợp:

```text
ALERT khi:
  api_p99 > SLO trong 5 phút
  AND request_rate >= baseline_low_bound
  AND (db_wait_time tăng OR connection_pool_wait tăng)
```

Hoặc cảnh báo storage:

```text
ALERT khi:
  storage_p99_latency > threshold trong 5 phút
  AND io_queue tăng
  AND workload_latency xấu đi
```

Đây là logic minh họa; cú pháp thực tế tùy Prometheus, Grafana Alerting, Datadog, CloudWatch hoặc hệ thống monitoring. Mỗi alert cần có owner, runbook, severity, thời gian duy trì và hướng xử lý.

### 16.4. Hysteresis và chống alert fatigue

Thiết lập ngưỡng recovery khác ngưỡng firing hoặc dùng thời gian duy trì để tránh alert bật/tắt liên tục. Gộp các alert cùng một incident; tránh gửi nhiều cảnh báo CPU, I/O và latency độc lập nếu chúng cùng do một query hoặc một storage outage.

## 17. Deployment marker và đối chiếu thay đổi

Dashboard cần đánh dấu:

- Application release/commit.
- Database migration/schema version.
- Index create/drop/rebuild.
- Statistics update hoặc plan change.
- Thay đổi pool size, timeout, isolation và ORM fetch settings.
- Resize instance, volume, storage tier hoặc network.
- Backup, maintenance, checkpoint và failover.

Khi latency tăng sau một deployment, marker giúp khoanh vùng nhưng không chứng minh quan hệ nhân quả. So sánh canary/control nếu có, giữ workload tương đương và kiểm tra query count, plan, CPU/transaction, reads/request, lock và log.

## 18. Ví dụ dashboard cho API tra cứu đơn hàng

Một dịch vụ có ba nhóm chính: API đọc đơn hàng, API cập nhật trạng thái và báo cáo doanh thu. Dashboard tổng quan có thể đặt các panel:

| Khu vực | Panel | Câu hỏi |
|---|---|---|
| SLO | p95/p99 API read/write và error rate | Người dùng có bị ảnh hưởng? |
| Traffic | Arrival, completion, retry và queue | Tải đến có vượt năng lực? |
| Application | JDBC spans/request, pool wait | Request chờ connection hay query? |
| Database | Active sessions, wait events, lock | DB đang chờ tài nguyên nào? |
| CPU/memory | CPU/core, run queue, cache, spill | Có CPU/memory pressure? |
| Storage | Data/log/temp IOPS, latency, queue | I/O nào đang bão hòa? |
| Critical query | Top SQL by total cost và p99 | Query nào gây tải hoặc chậm? |
| Operations | Backup, checkpoint, vacuum, deployment marker | Có tác vụ/sự kiện trùng thời điểm? |
| Capacity | Data/index growth, free space, headroom | Khi nào cần mở rộng? |

Giả sử p99 API đọc tăng từ 100 ms lên 600 ms. Dashboard cho thấy:

- Request rate không đổi.
- JDBC spans/request tăng từ 4 lên 35.
- Database CPU tăng nhẹ.
- Query fingerprint `SELECT ... WHERE customer_id = ?` tăng calls gấp tám.
- Storage latency không đổi.

Những dấu hiệu này hướng tới số query tăng, có thể do N+1 trong ORM, thay vì storage bottleneck. Drill-down trace để tìm mapper/getter kích hoạt lazy loading, sau đó kiểm tra fetch join, EntityGraph, batch fetching hoặc DTO projection. Sau sửa, so calls/request, p95/p99 và total DB time.

Ví dụ khác: p99 tăng, query count không đổi, `shared_blks_read` và read IOPS tăng mạnh, actual rows lệch xa estimate. Khi đó nên điều tra statistics, data skew và plan regression. Dashboard cần giúp phân biệt hai tình huống này thay vì chỉ báo “database chậm”.

## 19. Ví dụ Prometheus và Grafana ở mức khái niệm

Các ví dụ dưới đây minh họa cách biểu diễn metric đã được exporter đưa vào Prometheus. Tên metric thực tế phụ thuộc exporter và phiên bản; không copy query nếu chưa xác nhận schema metric đang có.

### 19.1. Request rate

```promql
sum by (service, endpoint) (
  rate(http_requests_total[5m])
)
```

Metric counter cần dùng `rate()` hoặc `increase()` theo cửa sổ phù hợp. Label endpoint nên là route template, không phải URL chứa ID động.

### 19.2. Error ratio

```promql
sum(rate(http_requests_total{status=~"5.."}[5m]))
/
clamp_min(sum(rate(http_requests_total[5m])), 1)
```

Query minh họa cho tỷ lệ HTTP 5xx; cần điều chỉnh theo định nghĩa success/failure của SLI và loại trừ hoặc bao gồm status phù hợp.

### 19.3. Histogram percentile

```promql
histogram_quantile(
  0.99,
  sum by (le, service, endpoint) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
```

Percentile từ histogram cần bucket phù hợp và đủ sample. Không tính trung bình p99 giữa các instance.

### 19.4. CPU utilization

```promql
100 * (1 - avg by (instance) (
  rate(node_cpu_seconds_total{mode="idle"}[5m])
))
```

Đây là ví dụ với node exporter. Cần xem thêm per-core, iowait, steal và container throttling để tránh hiểu sai CPU tổng.

### 19.5. Storage I/O rate

```promql
sum by (instance, device) (
  rate(node_disk_read_bytes_total[5m])
)
```

Metric này biểu diễn byte đọc mỗi giây theo device. Cần ghép với read/write operations, time spent, queue và database file metrics để phân biệt scan, random access và workload nền.

## 20. Nguyên tắc vận hành dashboard

### 20.1. Độ mới của dữ liệu

Hiển thị thời điểm metric gần nhất và cảnh báo collector/exporter mất dữ liệu. Một panel không có sample mới không được hiển thị như thể giá trị bằng 0. Phân biệt zero traffic với telemetry bị gián đoạn.

### 20.2. Độ phân giải và chi phí

Scrape interval quá ngắn có thể tạo tải lên database và monitoring backend. Query thống kê nặng hoặc lấy execution plan liên tục có thể ảnh hưởng production. Chọn tần suất theo mục đích: metric nhẹ có thể thu thập thường xuyên; query plan, table size hoặc index usage có thể snapshot ít thường xuyên hơn.

### 20.3. Retention và downsampling

Giữ dữ liệu độ phân giải cao đủ cho điều tra incident, sau đó lưu aggregate dài hạn cho trend. Đừng chỉ giữ average nếu cần phân tích tail latency; giữ histogram hoặc percentile summary theo cách có thể tổng hợp đúng.

### 20.4. Quyền truy cập

Dashboard tổng quan có thể mở rộng cho nhiều vai trò, nhưng raw SQL, bind values, session details và thông tin nhạy cảm cần phân quyền. Dùng service account read-only cho exporter; tránh cấp quyền DDL/DML chỉ để thu thập metric.

### 20.5. Kiểm tra dashboard như một sản phẩm

- Panel phải có owner và mô tả.
- Query dashboard phải được kiểm tra khi đổi exporter/database version.
- Alert phải được test bằng tình huống giả lập phù hợp.
- Dashboard cần có runbook liên kết.
- Metric không còn sử dụng cần được loại bỏ có kiểm soát.
- Thay đổi SLO hoặc workload class phải cập nhật panel và alert liên quan.

## 21. Những sai lầm thường gặp

- **Chỉ xây dashboard tài nguyên:** không liên kết CPU/I/O với SLO và request.
- **Chỉ hiển thị average:** bỏ qua p95/p99 và tail latency.
- **Gộp mọi endpoint:** workload khác nhau che lẫn nhau.
- **Chỉ xếp hạng query theo mean latency:** bỏ qua query nhanh nhưng gọi rất nhiều lần.
- **Chỉ xếp hạng query theo total time:** bỏ qua query hiếm nhưng p99 cực cao.
- **Coi plan hash đổi là lỗi:** phải so actual runtime, rows và resource cost.
- **Đọc counter tích lũy như tốc độ:** cần delta theo cửa sổ và biết thời điểm reset.
- **Dùng raw SQL hoặc ID làm metric label:** tạo cardinality cao và rủi ro lộ dữ liệu.
- **Lấy trung bình các p99 của instance:** không tạo ra percentile toàn hệ thống đúng.
- **Không phân biệt arrival và completion:** bỏ sót backlog và overload.
- **Không hiển thị telemetry freshness:** dữ liệu mất có thể bị hiểu là không có tải.
- **Polling query thống kê quá dày:** dashboard tự tạo overhead trên database.
- **Alert trên CPU đơn lẻ:** tạo false positive hoặc bỏ qua lock/I/O/log bottleneck.
- **Không gắn deployment marker:** khó xác định thay đổi bắt đầu khi nào.
- **Không có drill-down/runbook:** dashboard chỉ cho biết có vấn đề nhưng không hỗ trợ xử lý.
- **Tự động nâng baseline khi hệ thống chậm dần:** biến suy giảm thành trạng thái bình thường.

## 22. Checklist xây dựng dashboard hiệu năng

- [ ] Đã xác định người dùng dashboard và quyết định họ cần thực hiện.
- [ ] Đã định nghĩa SLI/SLO, phạm vi request, mẫu số và cửa sổ đo.
- [ ] Đã phân nhóm workload read, write, reporting, batch và maintenance.
- [ ] Đã có request rate, completion throughput, error, retry và queue.
- [ ] Đã có p50/p95/p99 theo endpoint/workload class và sample count.
- [ ] Đã liên kết application latency với connection pool và database time.
- [ ] Đã có CPU per core, run queue, memory pressure và cache/spill.
- [ ] Đã có data/log/temp IOPS, throughput, request size, queue và latency.
- [ ] Đã có log flush, checkpoint, lock wait, deadlock và replication lag.
- [ ] Đã có query fingerprint theo calls, total cost, latency, reads, writes và rows.
- [ ] Đã lưu plan identity và phát hiện plan change/regression.
- [ ] Đã có dashboard riêng cho truy vấn dài, query tổng chi phí cao và workload quan trọng.
- [ ] Đã gắn deployment, migration, maintenance và failover marker.
- [ ] Đã có bộ lọc thống nhất và drill-down từ SLO tới trace, query, plan và resource.
- [ ] Đã giới hạn metric cardinality, sampling, polling overhead và retention.
- [ ] Đã bảo vệ SQL/bind values và phân quyền dashboard/exporter.
- [ ] Đã có alert theo SLO và nhiều tín hiệu, kèm owner/runbook.
- [ ] Đã kiểm tra dashboard khi exporter/database version thay đổi.
- [ ] Đã có panel capacity, data growth, storage free space và headroom.
- [ ] Đã xác nhận dữ liệu monitoring còn mới và phân biệt mất telemetry với giá trị zero.

Dashboard theo mục tiêu dịch vụ, tài nguyên và truy vấn quan trọng giúp chuyển từ quan sát rời rạc sang điều tra có liên kết. SLO cho biết mức ảnh hưởng tới người dùng; metric tài nguyên và wait event cho biết hệ thống đang chờ ở đâu; query fingerprint và execution plan chỉ ra công việc tạo ra chi phí. Khi các lớp này dùng chung workload context, time range và deployment marker, đội vận hành có thể phát hiện suy giảm, khoanh vùng nguyên nhân, đánh giá headroom và xác minh hiệu quả của thay đổi mà không phải dựa vào một chỉ số đơn lẻ.
