# Giám sát sau triển khai và phát hiện hiệu năng giảm theo thời gian

Trong chương **Vận hành hiệu năng** của module **DATABASE_PERFORMANCE**, tối ưu hiệu năng chỉ được xem là bền vững khi hệ thống tiếp tục đáp ứng mục tiêu sau khi triển khai và trong suốt quá trình dữ liệu, lưu lượng, truy vấn và hạ tầng thay đổi. Một câu SQL có thể nhanh trong ngày đầu nhưng chậm dần khi bảng tăng kích thước, phân bố dữ liệu thay đổi, statistics trở nên cũ, cache không còn chứa working set hoặc một kế hoạch thực thi mới được chọn. Tác vụ nền, phiên bản ứng dụng, thay đổi cấu hình và tăng concurrency cũng có thể làm xuất hiện nút thắt mới.

Giám sát sau triển khai (*post-deployment performance monitoring*) là việc thu thập, liên kết và phân tích số liệu ở tầng ứng dụng, database, hệ điều hành và storage để nhận ra suy giảm trước khi người dùng chịu ảnh hưởng nghiêm trọng. Trọng tâm không chỉ là xem CPU hoặc dung lượng đĩa, mà còn phải theo dõi latency theo percentile, throughput, lỗi, wait events, query fingerprint, execution plan, logical/physical reads, lock contention, log flush, memory pressure và xu hướng tăng trưởng.

Một quy trình vận hành hiệu quả cần có baseline đáng tin cậy, SLI/SLO rõ ràng, dashboard theo workload, cảnh báo có ngữ cảnh, dấu mốc triển khai và quy trình xác minh trước/sau thay đổi. Khi phát hiện bất thường, đội vận hành phải xác định được truy vấn hoặc tài nguyên nào thay đổi, mức độ ảnh hưởng tới SLO và hành động an toàn để giảm tác động.

## 1. Vì sao phải giám sát sau triển khai?

Benchmark trước khi phát hành chỉ mô tả hệ thống trong điều kiện thử nghiệm tại một thời điểm. Production tiếp tục thay đổi:

- Số lượng bản ghi, kích thước index và working set tăng.
- Phân bố dữ liệu thay đổi, một số tenant hoặc khóa trở nên nóng.
- Tỷ lệ đọc/ghi, query mix và concurrency biến động theo thời gian.
- Statistics không còn phản ánh phân bố mới.
- Optimizer chọn plan khác sau khi statistics, schema hoặc phiên bản thay đổi.
- Cache bị cạnh tranh bởi workload mới hoặc tác vụ nền.
- Transaction dài, lock contention, dead tuple, undo/version store hoặc temp spill tích tụ.
- Backup, checkpoint, vacuum, purge, index maintenance và batch job chạy trùng giờ cao điểm.
- Hạ tầng thay đổi: instance resize, storage tier, firmware, network route, quota hoặc cloud limit.
- Phiên bản driver, ORM, database hoặc ứng dụng thay đổi số câu SQL và cách truy cập dữ liệu.

Một thay đổi có thể không gây lỗi ngay khi phát hành nhưng làm chi phí mỗi request tăng dần. Ví dụ, API vẫn trả kết quả đúng nhưng số logical reads trên mỗi request tăng từ 800 lên 8.000; CPU chưa chạm 100% nhưng capacity giảm đáng kể. Nếu chỉ cảnh báo khi CPU vượt 95%, hệ thống có thể phát hiện quá muộn.

Giám sát cần phát hiện cả hai dạng:

1. **Suy giảm tức thời:** latency tăng ngay sau deployment, plan regression, storage failure hoặc cấu hình sai.
2. **Suy giảm tích lũy:** dữ liệu tăng, bloat, backlog cleanup, cache churn, statistics drift hoặc capacity headroom giảm dần.

## 2. Xác định mục tiêu đo trước khi tạo dashboard

Không thể giám sát hiệu năng có ý nghĩa nếu chưa xác định hệ thống cần phục vụ ai, workload nào quan trọng và ngưỡng nào được coi là suy giảm.

### 2.1. SLI và SLO

SLI (*Service Level Indicator*) là chỉ số phản ánh chất lượng dịch vụ, ví dụ latency, availability, tỷ lệ lỗi hoặc throughput. SLO (*Service Level Objective*) là mục tiêu định lượng cho SLI trong một cửa sổ thời gian.

Ví dụ minh họa:

| SLI | SLO mẫu | Phạm vi đo |
|---|---:|---|
| API đọc đơn hàng | p95 dưới 150 ms | Endpoint và loại request cụ thể |
| Giao dịch ghi thanh toán | p99 dưới 300 ms | Từ lúc nhận request đến khi commit/response |
| Tỷ lệ request thành công | 99,9% | Cửa sổ 30 ngày, loại trừ lỗi client theo định nghĩa |
| Query báo cáo | p95 dưới 5 giây | Nhóm truy vấn báo cáo được xác định |
| Replication lag | p95 dưới 2 giây | Replica phục vụ API đọc |
| Tỷ lệ timeout database | Dưới 0,1% | Request có truy cập database |

Các giá trị trên chỉ là ví dụ. SLO thực tế phải phù hợp với hợp đồng nghiệp vụ và cách đo. Không gộp endpoint có đặc tính khác nhau vào một percentile duy nhất; một API báo cáo dài có thể làm p95 tổng thể tăng dù API giao dịch vẫn khỏe, hoặc ngược lại bị che bởi số lượng lớn request nhanh.

### 2.2. Chọn đơn vị đo phù hợp

Theo dõi đồng thời:

- **Per request:** latency, số query, rows returned, error và retry.
- **Per transaction:** thời gian transaction, số statement, lock wait, log bytes và commit latency.
- **Per query fingerprint:** calls, total/mean/max latency, reads, writes, rows và plan identity.
- **Per database:** throughput, active sessions, wait events, cache, checkpoint và replication.
- **Per file/volume:** IOPS, throughput, request size, queue và latency.
- **Per tenant hoặc workload class:** phân bố tải, query cost và mức độ công bằng tài nguyên.

Số liệu tổng hợp toàn database có thể che một tenant hoặc một query rất nóng. Ngược lại, chia metric thành quá nhiều nhãn có thể làm cardinality tăng mạnh và khiến hệ thống monitoring tốn tài nguyên. Chọn các chiều phân tích có giá trị vận hành rõ ràng.

### 2.3. Xác định cửa sổ thời gian

Latency có thể được tổng hợp theo 1 phút, 5 phút, 1 giờ hoặc 1 ngày. Cửa sổ ngắn giúp phát hiện spike; cửa sổ dài cho thấy xu hướng. Nên dùng nhiều độ phân giải:

- Cửa sổ ngắn cho alert và điều tra incident.
- Cửa sổ theo giờ/ngày để so sánh chu kỳ traffic.
- Cửa sổ theo tuần/tháng để dự báo tăng trưởng và capacity.

Khi so sánh, phải đối chiếu cùng khung giờ, ngày trong tuần, mùa vụ và mức tải. So sáng thứ Hai với đêm Chủ nhật mà không chuẩn hóa traffic có thể dẫn tới kết luận sai.

## 3. Xây dựng baseline hiệu năng

Baseline là tập số liệu tham chiếu của hệ thống khi hoạt động bình thường với workload được mô tả rõ. Nó giúp phân biệt biến động bình thường với suy giảm thực sự.

### 3.1. Baseline cần bao gồm những gì?

- Query/transaction throughput theo nhóm workload.
- p50, p95, p99 latency và số lượng sample.
- Tỷ lệ lỗi, timeout, retry và deadlock.
- CPU utilization theo core, run queue và top query CPU.
- Memory, buffer/cache hit, page eviction và memory spill.
- Logical reads, physical reads, writes và temp I/O.
- IOPS, MB/s, request size, queue depth và I/O latency.
- Log generation, flush latency, checkpoint và archive backlog.
- Active sessions, connection pool wait, lock wait và transaction age.
- Replication lag, send/apply queue và downstream backlog.
- Data/index/log/temp size và tốc độ tăng trưởng.
- Execution plan/fingerprint của các truy vấn quan trọng.

### 3.2. Baseline theo workload, không chỉ theo máy chủ

Một máy chủ có CPU 50% có thể đang đáp ứng tốt workload hiện tại, nhưng con số đó không nói được mỗi request tiêu tốn bao nhiêu CPU. Hãy chuẩn hóa thêm:

\[
CPU\ per\ transaction = \frac{CPU\ time}{Completed\ transactions}
\]

\[
Reads\ per\ request = \frac{Logical\ reads}{Completed\ requests}
\]

\[
Log\ bytes\ per\ write = \frac{Log\ bytes\ generated}{Committed\ write\ transactions}
\]

Nếu throughput giữ nguyên nhưng CPU/transaction tăng gấp đôi, hiệu quả xử lý đã giảm dù CPU utilization chưa vượt ngưỡng. Các tỷ lệ này cần dùng cùng định nghĩa và cửa sổ đo; tránh chia cho số request bằng 0 hoặc trộn request thất bại với thành công mà không nêu rõ.

### 3.3. Baseline cần có trạng thái cache và dữ liệu

Ghi lại kích thước database, index, working set, buffer pool, trạng thái cache, số lượng tenant, cardinality và phân bố dữ liệu. Một benchmark với cache nóng và bảng nhỏ không thể so trực tiếp với production sau khi dữ liệu tăng gấp mười.

Khi thiết lập baseline sau deployment, nên quan sát cả giai đoạn warm-up và steady-state. Lưu plan hash hoặc query plan đại diện cùng thống kê tại thời điểm đó để có thể so sánh khi optimizer chọn plan mới.

### 3.4. Baseline không phải một ngưỡng bất biến

Baseline cần được cập nhật có kiểm soát khi workload, SLO hoặc cấu hình thay đổi hợp lệ. Không tự động nâng baseline mỗi khi hệ thống chậm dần; làm vậy có thể biến suy giảm thành trạng thái bình thường mới. Giữ lịch sử baseline, lý do cập nhật và số liệu chứng minh thay đổi đáp ứng mục tiêu.

## 4. Bộ chỉ số giám sát theo tầng

### 4.1. Tầng ứng dụng

Theo dõi:

- Request rate và throughput hoàn tất.
- p50/p95/p99 latency theo endpoint và loại nghiệp vụ.
- Error rate, timeout, retry và circuit breaker.
- Thời gian chờ application worker và connection pool.
- Số SQL statement trên mỗi request.
- Thời gian JDBC execute, transaction duration và commit latency.
- Kích thước payload, rows/bytes trả về và serialization time.

Nếu API chậm nhưng database query span vẫn nhanh, bottleneck có thể nằm ở thread pool, connection acquisition, network hoặc xử lý ứng dụng. Không quy mọi latency của API cho database.

### 4.2. Tầng database

Theo dõi:

- Transaction/query throughput và active sessions.
- Top query theo total time, mean/p95 nếu có, CPU, reads, writes và calls.
- Wait events theo thời gian và session/query.
- Logical/physical reads, buffer hit và cache churn.
- Lock wait, blocking chain, deadlock và transaction lâu.
- Temp file/spill, sort/hash và memory grant.
- Log flush, WAL/redo generation, checkpoint và archive.
- Statistics freshness, plan changes và query regression.
- Replication lag, apply rate và retained log.

### 4.3. Tầng hệ điều hành và storage

Theo dõi CPU theo core, run queue, context switch, memory available, swap, page fault, disk IOPS, throughput, request size, queue, latency và network retransmission. Với cloud storage, cần thêm quota, burst credit, instance limit và metric backend.

Đo đúng device/volume. Một volume logic có thể chia sẻ physical device hoặc storage pool với volume khác. Nếu chỉ nhìn mount point mà không biết topology, có thể bỏ sót cạnh tranh ở backend.

### 4.4. Tầng dữ liệu và tăng trưởng

Theo dõi:

- Data, index, log, temp, undo/version store và backup size.
- Tăng trưởng theo ngày/tuần/tháng.
- Số dòng, số page, phân bố khóa và skew.
- Dead tuple, bloat, history list, version store hoặc fragmentation theo engine.
- Số index, kích thước index và mức sử dụng.
- Partition mới, partition nóng và tỷ lệ dữ liệu hết hạn.

Dung lượng tăng không chỉ là vấn đề storage. Khi bảng/index lớn hơn, scan và cache miss có thể tăng; statistics có thể stale; backup window kéo dài; index rebuild cần nhiều temp space hơn.

## 5. Giám sát query fingerprint và execution plan

Một query fingerprint gom các câu SQL cùng cấu trúc nhưng khác giá trị tham số. Theo dõi fingerprint giúp phát hiện mẫu truy vấn có chi phí tăng dần mà không phải lưu từng câu SQL riêng lẻ.

### 5.1. Các chỉ số quan trọng theo fingerprint

- Số lần gọi (`calls`/`execution_count`).
- Tổng thời gian thực thi.
- Thời gian trung bình và phân vị nếu công cụ hỗ trợ.
- CPU time, logical reads, physical reads và writes.
- Rows returned/affected.
- Temp reads/writes hoặc spill.
- Số lần plan thay đổi và plan identity/hash.
- Tỷ lệ lỗi, timeout và retry.

Đừng chỉ xếp hạng theo thời gian trung bình. Một query mất 2 ms nhưng chạy 200.000 lần có thể tiêu tốn tổng tài nguyên lớn hơn query mất 2 giây chạy một lần. Xem cả tổng chi phí và chi phí trên mỗi lần gọi.

### 5.2. Phát hiện plan regression

Plan regression xảy ra khi cùng một query fingerprint bắt đầu dùng execution plan có chi phí hoặc latency xấu hơn. Nguyên nhân có thể là:

- Statistics thay đổi hoặc stale.
- Data distribution/skew thay đổi.
- Bind parameter khác nhau làm optimizer chọn plan không phù hợp.
- Index được thêm, xóa hoặc thay đổi.
- Schema, database version, compatibility level hoặc optimizer setting thay đổi.
- Parameter sniffing/parameter sensitivity.
- Cardinality estimate sai.

Hãy lưu plan identity cùng thời điểm và so actual rows, loops, buffers, join order, scan/lookup, sort/hash và parallelism. Plan hash thay đổi không tự động có nghĩa plan mới xấu; cần so hiệu năng thực tế và workload tham số đại diện.

### 5.3. Theo dõi estimated rows và actual rows

Chênh lệch lớn giữa estimated rows và actual rows có thể khiến optimizer chọn join, memory grant hoặc access path không phù hợp. Theo dõi các query quan trọng có sai lệch cardinality lớn, nhất là khi sai lệch lặp lại ở node đầu chuỗi join.

Ví dụ:

| Chỉ số | Baseline | Sau một tháng |
|---|---:|---:|
| Estimated rows | 500 | 500 |
| Actual rows | 520 | 85.000 |
| Logical reads | 3.200 | 94.000 |
| p95 latency | 80 ms | 1.400 ms |

Ví dụ cho thấy estimate không còn đại diện dữ liệu thực tế. Hướng điều tra gồm statistics, histogram, skew, predicate, parameter sensitivity và plan. Không chỉ tăng memory hoặc thêm index theo cảm tính.

### 5.4. Phân biệt query chậm với query thường xuyên

Một query có p99 cao nhưng chỉ chạy vài lần mỗi ngày khác với query 10 ms chạy hàng chục nghìn lần mỗi phút. Dashboard nên có ít nhất hai góc nhìn:

- **Top latency:** truy vấn chậm theo p95/p99 hoặc maximum có kiểm soát.
- **Top total cost:** truy vấn theo tổng CPU, reads, elapsed time, writes hoặc calls.

Điều này tránh bỏ sót query nhỏ nhưng gây tổng tải lớn.

## 6. Thu thập số liệu theo hệ quản trị

Các ví dụ sau minh họa nguồn dữ liệu phổ biến. Tên view, cột, quyền truy cập và semantics thay đổi theo phiên bản; cần xác minh theo engine đang chạy. Counter thường tích lũy, nên lấy delta theo cửa sổ thay vì chỉ đọc tổng từ lúc khởi động.

### 6.1. PostgreSQL

Nếu `pg_stat_statements` đã được cài và bật, có thể theo dõi query có tổng thời gian cao:

```sql
SELECT queryid,
       calls,
       total_exec_time,
       mean_exec_time,
       rows,
       shared_blks_hit,
       shared_blks_read,
       shared_blks_dirtied,
       shared_blks_written,
       temp_blks_read,
       temp_blks_written,
       query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

`pg_stat_statements` thống kê theo query identity và các counter tích lũy. `shared_blks_read` là block được nạp vào shared buffers từ tầng dưới; không nhất thiết tương đương một lần đọc NAND vật lý vì OS/storage cache có thể phục vụ. Lấy snapshot định kỳ và tính delta để tìm tốc độ calls, reads và thời gian trong từng cửa sổ.

Theo dõi session đang chạy và wait event:

```sql
SELECT pid,
       usename,
       application_name,
       state,
       wait_event_type,
       wait_event,
       now() - query_start AS query_age,
       left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
```

Theo dõi dead tuple và vacuum:

```sql
SELECT relname,
       n_live_tup,
       n_dead_tup,
       last_autovacuum,
       autovacuum_count,
       last_autoanalyze,
       autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

Đối với I/O theo backend/object/context, PostgreSQL 16 trở lên có `pg_stat_io`. Một số trường thời gian yêu cầu cấu hình I/O timing phù hợp; đối chiếu với metric OS. `pg_stat_database`, `pg_stat_checkpointer` hoặc view thống kê tương ứng theo phiên bản có thể cung cấp checkpoint, temp bytes và block activity.

### 6.2. MySQL/InnoDB

Performance Schema có bảng summary theo digest:

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

Timer trong Performance Schema thường biểu diễn theo picosecond. Bảng summary có thể reset hoặc mất dữ liệu khi restart/configuration thay đổi; cần snapshot định kỳ và kiểm tra instrumentation đang bật.

Để xem file I/O:

```sql
SELECT FILE_NAME,
       EVENT_NAME,
       COUNT_READ,
       SUM_NUMBER_OF_BYTES_READ,
       SUM_TIMER_READ,
       COUNT_WRITE,
       SUM_NUMBER_OF_BYTES_WRITE,
       SUM_TIMER_WRITE
FROM performance_schema.file_summary_by_instance
ORDER BY SUM_TIMER_READ + SUM_TIMER_WRITE DESC
LIMIT 20;
```

Đối chiếu với `SHOW ENGINE INNODB STATUS`, buffer pool metrics, history list length, transaction lâu và replication status. `EXPLAIN ANALYZE` có thể cung cấp actual rows/loops trên phiên bản hỗ trợ, nhưng nó thực thi statement; chỉ dùng với truy vấn an toàn trong môi trường phù hợp.

### 6.3. SQL Server

Query Store lưu lịch sử query, plan và runtime statistics khi được bật. Đây là nguồn quan trọng để so sánh plan và runtime trước/sau deployment. Cần cấu hình capture mode, retention và storage phù hợp.

DMV `sys.dm_exec_query_stats` cung cấp counter theo plan cache:

```sql
SELECT TOP (20)
       qs.execution_count,
       qs.total_worker_time,
       qs.total_elapsed_time,
       qs.total_logical_reads,
       qs.total_physical_reads,
       qs.total_logical_writes,
       st.text
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
ORDER BY qs.total_worker_time DESC;
```

Các DMV counter có thể reset khi plan bị evict hoặc instance restart. Query Store có thể giữ lịch sử lâu hơn nhưng vẫn cần cấu hình retention và theo dõi dung lượng. Đọc cùng wait statistics, actual plan, memory grant, spill và file I/O.

### 6.4. Oracle

Các dynamic performance view như `V$SQL` giúp theo dõi query theo SQL_ID:

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
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
```

`V$SQL` chứa thống kê theo cursor và có thể thay đổi khi cursor aging hoặc instance restart. So sánh executions, elapsed, CPU, buffer gets và disk reads; dùng plan hash như một dấu hiệu thay đổi chứ không phải thước đo chất lượng độc lập.

Các view AWR/ASH và một số báo cáo lịch sử có thể yêu cầu quyền và license Oracle Diagnostics/Tuning Pack tùy phiên bản/edition. Chỉ sử dụng khi tổ chức có quyền phù hợp; nếu không, dùng các view và công cụ được cấp phép.

## 7. Phát hiện suy giảm theo thời gian

Suy giảm dài hạn thường khó phát hiện bằng một ngưỡng tức thời. Cần theo dõi xu hướng và chuẩn hóa theo workload.

### 7.1. So sánh cùng khung thời gian

So sánh p95 thứ Hai tuần này với p95 thứ Hai tuần trước trong cùng giờ, cùng endpoint và mức request rate gần nhau. Đối với traffic theo mùa vụ, dùng baseline theo ngày trong tuần hoặc giai đoạn nghiệp vụ tương ứng.

Không so sánh một ngày có traffic thấp với ngày có traffic gấp ba rồi kết luận latency tăng là do database. Dùng thêm latency per query, CPU/transaction, reads/request và wait distribution để tách tác động do tải.

### 7.2. Theo dõi tốc độ tăng trưởng

Đo tốc độ tăng của data, index, log, temp và backup:

\[
GrowthRate = \frac{Size_{t2} - Size_{t1}}{t2 - t1}
\]

Ví dụ, index tăng 30 GB trong 30 ngày tương đương khoảng 1 GB/ngày. Nếu dung lượng còn trống 90 GB và tốc độ không đổi, thời gian tới ngưỡng đầy xấp xỉ 90 ngày; thực tế cần tính tăng trưởng biến động, khoảng trống bảo trì và thời gian provision.

### 7.3. Theo dõi chi phí trên một đơn vị công việc

Các tỷ lệ chuẩn hóa giúp phát hiện hiệu quả suy giảm ngay cả khi traffic tăng:

- CPU milliseconds trên mỗi transaction.
- Logical reads trên mỗi request.
- Physical reads trên mỗi query fingerprint.
- Log bytes trên mỗi write transaction.
- Temp bytes trên mỗi báo cáo.
- Connection wait time trên mỗi request.
- Retry/deadlock trên mỗi nghìn transaction.

Nếu request rate tăng 20% nhưng CPU tăng 70%, cần tìm công việc mới phát sinh hoặc plan regression. Nếu CPU tăng gần tỷ lệ request và latency vẫn ổn định, đó có thể là tăng tải bình thường; vẫn phải đánh giá headroom.

### 7.4. Phát hiện thay đổi phân bố dữ liệu

Theo dõi cardinality, distinct count, skew, top values và phân bố theo partition/tenant. Một cột trước đây có giá trị tương đối đồng đều có thể trở nên lệch mạnh; index hoặc histogram cũ không còn phản ánh selectivity. Query plan có thể thay đổi dù SQL và schema không đổi.

Khi query chậm dần, hãy kiểm tra dữ liệu thực tế và statistics cùng với execution plan. Chỉ nhìn plan text mà không xem actual rows và phân bố tham số có thể bỏ qua nguyên nhân.

## 8. Giám sát contention và transaction dài

Một hệ thống có thể có CPU và I/O còn headroom nhưng vẫn chậm do transaction chờ khóa hoặc một tài nguyên bị serialize.

### 8.1. Các tín hiệu cần theo dõi

- Lock wait duration và số session bị block.
- Deadlock rate và transaction retry.
- Transaction age, idle-in-transaction và snapshot age.
- Hot row/key, hot index page hoặc latch wait.
- Connection pool active/waiting và thời gian acquire.
- Long-running query và transaction giữ lock.

### 8.2. Phân biệt lock wait với I/O wait

Nếu session chờ lock, tăng IOPS không giải quyết được nguyên nhân. Tìm blocking chain, transaction giữ khóa lâu, thứ tự cập nhật và truy vấn gây tranh chấp. Nếu session chờ I/O, kiểm tra volume, queue và page access. Một session có thể lần lượt chờ nhiều loại tài nguyên, nên cần trace theo thời gian.

### 8.3. Theo dõi transaction lâu

Transaction dài có thể giữ lock, snapshot, undo hoặc phiên bản MVCC, khiến vacuum/purge/version cleanup không tiến triển. Theo dõi tuổi transaction và xác định session nào giữ snapshot lâu. Không tự động kill transaction chỉ vì vượt một ngưỡng nếu chưa hiểu tác động rollback và nghiệp vụ.

## 9. Cảnh báo hiệu năng có ngữ cảnh

Cảnh báo nên phản ánh tác động và khả năng hành động. Một metric cao đơn lẻ không luôn là incident.

### 9.1. Cảnh báo theo SLO

Ưu tiên cảnh báo khi:

- p95/p99 của endpoint quan trọng vượt SLO liên tục.
- Error/timeout rate tăng.
- Throughput hoàn tất giảm trong khi offered load không giảm.
- SLO burn rate cho thấy error budget bị tiêu thụ nhanh.
- Queue hoặc connection pool wait tăng cùng latency.

### 9.2. Cảnh báo theo dấu hiệu sớm

Các tín hiệu sớm có thể gồm:

- I/O queue và p99 latency tăng trước khi throughput giảm.
- Log flush latency tăng và log free space giảm.
- Replication lag tăng liên tục.
- Buffer cache churn hoặc physical reads/request tăng.
- Temp spill tăng đột ngột.
- Transaction age hoặc blocking chain vượt mức thông thường.
- Index/data growth làm headroom storage giảm.
- Query fingerprint có plan change và cost tăng.

### 9.3. Kết hợp nhiều điều kiện

Tránh cảnh báo chỉ vì CPU vượt 80% trong một phút nếu latency và throughput vẫn tốt. Có thể dùng điều kiện kết hợp:

```text
ALERT khi:
  p95_api > SLO trong 5 phút
  AND request_rate không giảm đáng kể
  AND (db_wait tăng OR connection_pool_wait tăng)
```

Hoặc cảnh báo capacity:

```text
ALERT khi:
  storage_free < ngưỡng vận hành
  OR dự báo chạm ngưỡng trong thời gian provision
```

Ví dụ chỉ minh họa logic; cú pháp cụ thể phụ thuộc Prometheus, Datadog, CloudWatch hoặc hệ thống monitoring đang dùng. Ngưỡng phải dựa trên baseline và thời gian phản ứng cần thiết.

### 9.4. Tránh alert fatigue

- Dùng warning và critical theo mức độ tác động.
- Gộp alert liên quan cùng incident.
- Có owner, runbook và hành động tiếp theo cho mỗi alert.
- Dùng thời gian duy trì hoặc hysteresis để tránh bật/tắt liên tục.
- Không cảnh báo trên metric không có người xử lý.
- Rà soát alert false positive và metric không còn ý nghĩa.

## 10. Dashboard phục vụ điều tra

Một dashboard tốt nên hỗ trợ đi từ triệu chứng tới nguyên nhân, không chỉ hiển thị nhiều gauge.

### 10.1. Dashboard cấp dịch vụ

- Request rate, throughput hoàn tất.
- p50/p95/p99 theo endpoint/workload class.
- Error, timeout, retry và SLO burn rate.
- Queue age, request in-flight và connection pool wait.
- Deployment marker, version ứng dụng và cấu hình liên quan.

### 10.2. Dashboard database

- Transactions/queries per second.
- Active sessions, waits, lock/blocking và deadlocks.
- Top query fingerprints theo total time, CPU, reads và calls.
- Plan changes và query regressions.
- Buffer cache, physical reads, temp spill và memory pressure.
- Log flush, checkpoint, WAL/redo và replication lag.

### 10.3. Dashboard hạ tầng

- CPU per core, run queue, memory available, swap.
- Disk IOPS, throughput, request size, queue và latency.
- Network throughput, retransmission và round-trip.
- Volume free space, growth rate, provisioned limit và burst credits.
- VM/container resource limits và throttling.

### 10.4. Dashboard capacity và xu hướng

- Data/index/log/temp/backup growth.
- CPU, memory và I/O utilization ở peak.
- Headroom theo tài nguyên.
- Forecast thời điểm chạm quota hoặc dung lượng.
- Throughput bền vững theo workload class.
- Năng lực failover khi một replica/node không khả dụng.

Dashboard nên có link hoặc drill-down từ endpoint sang trace, từ trace sang query fingerprint, rồi tới execution plan và wait/resource metrics. Tránh hiển thị SQL text hoặc bind values nhạy cảm cho mọi người dùng dashboard.

## 11. Liên kết deployment với hiệu năng

Một trong những cách nhanh nhất để phát hiện suy giảm là gắn dấu mốc phiên bản và thay đổi cấu hình vào chuỗi metric.

### 11.1. Ghi deployment marker

Ghi thời điểm và thông tin:

- Application version/commit.
- Database migration/schema version.
- Driver, ORM và database version.
- Thay đổi index/statistics/configuration.
- Thay đổi instance, storage, network hoặc pool size.
- Tỷ lệ traffic canary và thời điểm mở rộng rollout.

Khi latency tăng sau một deployment, marker giúp thu hẹp phạm vi điều tra. Tuy nhiên, tương quan thời gian chưa đủ chứng minh deployment là nguyên nhân; cần so query count, plan, resource và workload.

### 11.2. Canary và so sánh trước/sau

Triển khai một phần traffic trước, giữ nhóm đối chứng nếu kiến trúc cho phép. So sánh cùng endpoint, query mix, payload, tenant distribution và thời gian. Theo dõi:

- p95/p99 và error rate.
- Query count per request.
- DB time, CPU/transaction, reads/request.
- Connection pool wait và transaction duration.
- Lock wait, log bytes và replication lag.

Nếu canary có latency hoặc resource cost tăng đáng kể mà không có lợi ích tương ứng, dừng mở rộng và điều tra. Không đợi CPU hoặc storage chạm 100% mới rollback.

### 11.3. Kiểm tra migration và index change

DDL có thể thay đổi plan, lock metadata, tăng log hoặc làm tăng write cost. Sau migration:

1. Xác nhận index/constraint đã tạo đúng.
2. Kiểm tra statistics và plan của query quan trọng.
3. So logical reads, physical reads, rows và latency.
4. Đo write throughput và index maintenance cost.
5. Kiểm tra lock, replication lag và dung lượng.

Một index mới có thể giảm reads nhưng tăng chi phí INSERT/UPDATE và dung lượng. Đánh giá cả read workload và write workload trước khi giữ thay đổi.

## 12. Quy trình điều tra khi hiệu năng giảm

### 12.1. Xác nhận phạm vi ảnh hưởng

Xác định endpoint, database, tenant, query fingerprint, thời điểm bắt đầu và tỷ lệ người dùng bị ảnh hưởng. So sánh p50/p95/p99, throughput và error rate với baseline tương ứng.

### 12.2. Kiểm tra thay đổi gần nhất

Xem deployment, migration, index, statistics, configuration, traffic mix, batch job, backup và thay đổi hạ tầng. Dùng deployment marker để thu hẹp khoảng thời gian.

### 12.3. Phân loại latency

Tách thời gian ở application, connection pool, network, database execution, lock wait, I/O wait và serialization. Trace giúp xác định request dành phần lớn thời gian ở tầng nào.

### 12.4. Tìm query hoặc tài nguyên gây tác động

Xếp hạng query fingerprint theo total cost và latency; kiểm tra plan, rows, loops, reads, temp spill và waits. Đồng thời xem CPU, memory, storage, log, network và connection pool.

### 12.5. Đưa ra giả thuyết có thể kiểm chứng

Ví dụ:

- Plan đổi từ index seek sang scan sau khi statistics cập nhật.
- Logical reads/request tăng do ORM phát sinh thêm query.
- Physical reads tăng vì working set vượt buffer pool.
- Log flush latency tăng do transaction commit quá thường xuyên.
- Lock wait tăng vì một transaction mới giữ khóa lâu.
- Temp I/O tăng do memory grant hoặc cardinality estimate thay đổi.
- Replica lag tăng vì query báo cáo cạnh tranh apply worker.

Mỗi giả thuyết cần chỉ ra metric dự kiến thay đổi và cách xác minh.

### 12.6. Giảm tác động trước, tối ưu sau

Trong incident, ưu tiên khôi phục SLO bằng hành động có thể đảo ngược: dừng rollout, giảm concurrency, throttle batch, chuyển báo cáo sang replica phù hợp, giới hạn query dài hoặc rollback cấu hình gần nhất. Tránh thay đổi nhiều tham số cùng lúc vì sẽ khó xác định nguyên nhân và tăng rủi ro.

Sau khi dịch vụ ổn định, mới thực hiện sửa query/index/statistics hoặc thay đổi kiến trúc trong môi trường kiểm thử và rollout có kiểm soát.

## 13. Ví dụ: API chậm dần sau nhiều tuần

Một API tìm đơn hàng có p95 ban đầu 90 ms. Sau sáu tuần, p95 tăng lên 420 ms dù request rate chỉ tăng khoảng 15%. CPU database tăng từ 45% lên 65%, physical reads/request tăng gần bốn lần.

Dashboard và query history cho thấy:

| Chỉ số | Baseline | Sau sáu tuần |
|---|---:|---:|
| Request rate | 400/s | 460/s |
| p95 API | 90 ms | 420 ms |
| Logical reads/request | 1.200 | 1.350 |
| Physical reads/request | 20 | 78 |
| Query calls/request | 4 | 4 |
| Estimated rows | 300 | 300 |
| Actual rows | 320 | 24.000 |
| Index size | 18 GB | 27 GB |

Số query không tăng, nhưng actual rows lệch xa estimate và physical reads tăng. Điều này gợi ý data distribution hoặc statistics đã thay đổi, làm plan không còn phù hợp.

Quy trình điều tra:

1. Lấy actual plan của query ở thời điểm chậm và so với plan baseline.
2. Kiểm tra predicate, histogram, statistics age và phân bố khóa theo tenant.
3. Xác định query có giá trị tham số skew khiến một plan không phù hợp cho mọi tenant không.
4. Thử cập nhật statistics hoặc điều chỉnh index/SQL trên môi trường đại diện.
5. Chạy benchmark với tenant nhỏ, tenant lớn và workload hỗn hợp.
6. Canary thay đổi và so p95, reads/request, CPU/transaction, write cost và replication.

Giả sử plan mới giảm physical reads/request về gần baseline và p95 về 110 ms nhưng làm INSERT chậm thêm 4%. Cần đánh giá tỷ lệ đọc/ghi và SLO của cả hai workload trước khi quyết định giữ index hoặc plan change. Không chỉ nhìn API đọc để kết luận tối ưu tổng thể.

## 14. Ví dụ: latency tăng ngay sau deployment

Một phiên bản ứng dụng mới giữ nguyên endpoint nhưng p99 tăng gấp ba. Database CPU và I/O tổng chưa tăng nhiều. Trace cho thấy số JDBC spans trên mỗi request tăng từ 5 lên 42; nhiều span có cùng fingerprint `SELECT ... WHERE id = ?`.

Đây là dấu hiệu ứng dụng phát sinh truy vấn lặp, chẳng hạn N+1 từ lazy association trong mapper hoặc serializer. Hướng xử lý:

1. So query count và fingerprint trước/sau deployment.
2. Tìm code path truy cập association trong vòng lặp.
3. Chọn fetch join, EntityGraph, batch fetching hoặc DTO projection theo nhu cầu.
4. Thêm regression test kiểm tra query count theo số entity.
5. Canary bản sửa và đo lại JDBC spans, DB time, p95/p99 và memory.

CPU tổng thấp không loại trừ vấn đề database. Nhiều round trip ngắn có thể làm latency tăng vì network và connection overhead trước khi CPU bão hòa.

## 15. Capacity trend và dự báo trước khi bão hòa

Giám sát hiệu năng không chỉ để xử lý incident hiện tại. Cần dự báo khi tài nguyên sẽ chạm ngưỡng và chuẩn bị mở rộng trước khi SLO bị vi phạm.

### 15.1. Theo dõi headroom

Với mỗi tài nguyên, ghi:

- Mức sử dụng trung bình và peak.
- Năng lực bền vững đã được benchmark.
- Tải dự báo theo tăng trưởng.
- Thời gian cần để provision/resize/migrate.
- Mức dự phòng khi failover hoặc maintenance.

Không dùng utilization đơn lẻ làm capacity. CPU 70% có thể còn đủ headroom nếu latency ổn định; storage queue tăng và p99 I/O cao ở mức utilization thấp có thể báo hiệu bottleneck sớm hơn.

### 15.2. Dự báo dung lượng

Nếu data tăng trung bình 500 GB/tháng và volume còn trống 3 TB, phép chia đơn giản cho thời gian còn lại là 6 tháng. Capacity plan thực tế phải trừ vùng trống dành cho index rebuild, temp, backup, log, snapshot và thời gian mở rộng; tốc độ tăng cũng có thể không tuyến tính.

### 15.3. Dự báo năng lực xử lý

Theo dõi CPU/transaction, reads/request và log bytes/write transaction. Nếu workload tăng 10% mỗi tháng nhưng chi phí mỗi transaction tăng thêm 5% mỗi tháng, tổng resource demand có thể tăng nhanh hơn lưu lượng. Phân rã hai yếu tố giúp xác định cần tối ưu query hay mở rộng hạ tầng.

## 16. Chất lượng dữ liệu monitoring và chi phí quan sát

Monitoring cũng tiêu thụ tài nguyên và có thể tạo vấn đề nếu thu thập quá chi tiết.

### 16.1. Cardinality của metric

Không gắn raw SQL, user id, order id hoặc giá trị bind vào metric label. Những giá trị có vô số khả năng tạo cardinality cao, làm tăng memory, storage và query cost của monitoring backend. Dùng query fingerprint, normalized endpoint, database name hoặc workload class có số lượng giới hạn.

### 16.2. Sampling trace và slow query log

Trace toàn bộ request có thể tốn storage và network. Dùng sampling có chủ đích, tăng tỷ lệ sample cho lỗi hoặc latency cao nếu hệ thống hỗ trợ. Slow query threshold cần phù hợp với workload; ngưỡng quá thấp tạo quá nhiều log, ngưỡng quá cao bỏ sót query lặp nhanh nhưng tổng cost lớn.

### 16.3. Bảo vệ dữ liệu nhạy cảm

SQL text và bind parameter có thể chứa email, token, thông tin thanh toán hoặc dữ liệu cá nhân. Mask/redact trước khi lưu; giới hạn quyền truy cập; đặt retention; không đưa secrets vào dashboard hoặc alert. Log đủ để tìm fingerprint và plan nhưng không lưu dữ liệu nhạy cảm không cần thiết.

### 16.4. Đồng bộ thời gian

Đồng bộ clock giữa application, database, OS và monitoring collector để liên kết trace với database event. Với đo duration trong một process, ưu tiên monotonic clock. Wall clock có thể bị điều chỉnh bởi NTP hoặc clock drift; không tính duration bằng cách trừ timestamp từ hai máy chưa đồng bộ.

## 17. Những sai lầm thường gặp

- **Chỉ giám sát CPU và RAM:** bỏ qua query cost, wait events, log flush, lock, cache miss và replication.
- **Chỉ dùng average latency:** che p95/p99 và một nhóm request rất chậm.
- **Không lưu baseline:** không thể biết thay đổi có gây regression hay không.
- **So sánh khác workload:** traffic mix hoặc dữ liệu khác làm kết quả mất ý nghĩa.
- **Chỉ xếp hạng query theo mean time:** bỏ qua query nhanh nhưng chạy rất thường xuyên.
- **Coi plan hash thay đổi là regression:** plan mới cần được đánh giá bằng actual runtime và resource cost.
- **Không theo dõi actual rows:** cardinality estimate sai có thể gây plan kém mà không được phát hiện.
- **Đọc counter tích lũy như tốc độ hiện tại:** cần delta và uptime/reset context.
- **Alert trên một metric đơn lẻ:** CPU cao chưa chắc ảnh hưởng SLO; I/O queue cao cần gắn với latency/workload.
- **Không gắn deployment marker:** khó liên hệ regression với phiên bản, migration hoặc cấu hình.
- **Tự động cập nhật baseline theo trạng thái mới:** có thể hợp thức hóa suy giảm kéo dài.
- **Thu thập SQL/bind không kiểm soát:** gây cardinality cao, log volume lớn và rủi ro lộ dữ liệu.
- **Không đo chi phí monitoring:** instrumentation quá nặng có thể tự tạo tải.
- **Tối ưu một query mà bỏ qua workload khác:** giảm read cost có thể tăng write cost, log và replication.
- **Chỉ phản ứng khi đã quá tải:** không dự báo headroom và thời gian provision.

## 18. Checklist giám sát sau triển khai

- [ ] Đã xác định SLI/SLO theo endpoint và workload class.
- [ ] Đã lưu baseline throughput, p50/p95/p99, error rate và query mix.
- [ ] Đã lưu query fingerprint, plan identity và số liệu reads/CPU/rows của query quan trọng.
- [ ] Đã đo logical/physical reads, temp spill, log flush, lock wait và replication lag.
- [ ] Đã theo dõi CPU theo core, memory pressure, I/O queue/latency và network.
- [ ] Đã đo query count, JDBC time và connection pool wait theo request.
- [ ] Đã theo dõi data/index/log/temp growth và headroom.
- [ ] Đã gắn deployment marker cho app, schema, index, database và infrastructure changes.
- [ ] Đã so sánh cùng khung thời gian và workload tương đương.
- [ ] Đã có cảnh báo theo SLO, nhiều tín hiệu và ngưỡng capacity.
- [ ] Đã có dashboard drill-down từ endpoint tới trace, query, plan và resource.
- [ ] Đã kiểm tra cardinality, sampling, retention và bảo vệ dữ liệu nhạy cảm.
- [ ] Đã có runbook xác nhận phạm vi, phân loại bottleneck, giảm tác động và rollback.
- [ ] Đã kiểm thử canary và đo trước/sau deployment.
- [ ] Đã dự báo tăng trưởng và xác định thời điểm cần mở rộng.
- [ ] Đã rà soát baseline có kiểm soát, không tự động chấp nhận suy giảm thành bình thường.

Giám sát sau triển khai giúp phát hiện hiệu năng giảm trước khi nó trở thành sự cố người dùng. Cần liên kết SLO của ứng dụng với query fingerprint, execution plan, wait events, cache, log, storage và xu hướng dữ liệu. Baseline theo workload, deployment marker, cảnh báo có ngữ cảnh và quy trình điều tra nhất quán sẽ cho biết điều gì đã thay đổi, thay đổi ở tầng nào và hành động nào có thể khôi phục hiệu năng. Đo lại sau mỗi điều chỉnh để xác nhận cải thiện trên toàn workload, đồng thời giữ lịch sử để nhận ra suy giảm tích lũy theo thời gian.
