# Kiểm thử hồi quy hiệu năng sau đổi SQL, chỉ mục, cấu hình hoặc phiên bản

## Mục tiêu bài học

Một thay đổi được xem là đúng khi kết quả nghiệp vụ vẫn chính xác, nhưng điều đó chưa đủ để kết luận thay đổi an toàn cho production. Một câu SQL mới có thể giảm thời gian của một truy vấn nhưng làm tăng chi phí ghi; một index mới có thể tăng tốc lookup nhưng làm INSERT/UPDATE chậm hơn; một tham số cấu hình có thể cải thiện workload thử nghiệm nhưng làm hệ thống thiếu bộ nhớ khi concurrency tăng; một phiên bản database mới có thể chọn execution plan khác.

Trong chương **Kiểm thử hiệu năng** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn kiểm thử hồi quy hiệu năng sau khi thay đổi SQL, chỉ mục, cấu hình hoặc phiên bản. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, mỗi thay đổi cần được đánh giá trong workload đại diện, có baseline đáng tin cậy, đo cả lợi ích lẫn chi phí phát sinh và có tiêu chí chấp nhận trước khi triển khai.

Sau bài học, bạn có thể:

- Giải thích mục đích và phạm vi của kiểm thử hồi quy hiệu năng.
- Xây dựng baseline có thể tái lập trước thay đổi.
- Chuẩn bị dữ liệu, cấu hình và workload đủ đại diện.
- So sánh execution plan, latency, throughput và mức tiêu thụ tài nguyên.
- Phát hiện tác động phụ khi thêm/bỏ index, sửa SQL, đổi tham số hoặc nâng cấp database.
- Thiết kế ngưỡng regression theo SLA và độ biến động đo lường.
- Tự động hóa benchmark trong CI/staging và kiểm tra canary sau triển khai.
- Đưa ra quyết định chấp nhận, điều tra thêm hoặc rollback dựa trên bằng chứng.

## 1. Kiểm thử hồi quy hiệu năng là gì?

**Kiểm thử hồi quy hiệu năng** (performance regression testing) là quá trình đo và so sánh hành vi hiệu năng của hệ thống trước và sau một thay đổi để xác định liệu thay đổi đó có làm chậm truy vấn, giảm thông lượng, tăng sử dụng tài nguyên hoặc làm xấu khả năng chịu tải hay không.

Phạm vi kiểm thử không chỉ là câu SQL vừa sửa. Một thay đổi trong database có thể tác động tới nhiều workload:

- Thêm index giúp truy vấn đọc nhanh hơn nhưng làm tăng WAL và thời gian ghi.
- Đổi predicate có thể giúp một giá trị tham số nhưng làm plan kém với giá trị khác.
- Tăng `work_mem` có thể giảm sort spill cho một query nhưng làm tổng bộ nhớ tăng khi nhiều query chạy đồng thời.
- Nâng cấp phiên bản có thể thay đổi planner, thống kê, executor hoặc hành vi I/O.
- Thay đổi fillfactor có thể tăng HOT update nhưng làm heap lớn hơn.
- Bật một tính năng mới có thể giảm latency trung bình nhưng làm p99 xấu hơn khi tải cao.

Kiểm thử hồi quy phải xem cả **đường đọc**, **đường ghi** và **toàn hệ thống**. Kết quả tốt ở một truy vấn riêng lẻ chưa chắc là kết quả tốt cho workload hỗn hợp.

### 1.1. Các câu hỏi kiểm thử cần trả lời

1. Kết quả và số dòng trả về có còn đúng không?
2. Latency p50, p95 và p99 thay đổi như thế nào?
3. Throughput ở cùng concurrency tăng hay giảm?
4. CPU, memory, I/O, WAL, temp và connection usage thay đổi ra sao?
5. Execution plan có thay đổi? Thay đổi đó có hợp lý với dữ liệu và tham số không?
6. Một nhóm truy vấn được cải thiện có làm nhóm khác chậm đi không?
7. Hệ thống có còn đáp ứng SLA trong tải đỉnh và sau một thời gian chạy liên tục không?
8. Có thể phát hiện regression trước khi phát hành và rollback trong thời gian cho phép không?

### 1.2. Phân biệt correctness test và performance test

Correctness test xác nhận dữ liệu và kết quả nghiệp vụ đúng. Performance test xác nhận hệ thống đạt mục tiêu thời gian, thông lượng và tài nguyên. Hai loại cần chạy cùng nhau vì một tối ưu có thể vô tình đổi semantics hoặc bỏ qua dữ liệu.

Ví dụ, thêm điều kiện `LIMIT` có thể làm truy vấn nhanh hơn nhưng trả thiếu dữ liệu. Một phép join thay đổi có thể giảm số dòng trung gian nhưng loại bỏ bản ghi không có quan hệ. Một index partial có thể không phục vụ các giá trị nằm ngoài predicate. Không được coi việc truy vấn nhanh hơn là thành công nếu kết quả không còn tương đương.

## 2. Xây dựng baseline trước thay đổi

Baseline là tập dữ liệu tham chiếu được đo trong điều kiện có thể lặp lại. Baseline yếu sẽ dẫn tới kết luận sai: hệ thống có thể trông nhanh hơn chỉ vì cache đã nóng, dữ liệu nhỏ hơn hoặc số client ít hơn.

### 2.1. Chỉ số cần lưu

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Latency | p50, p95, p99, max và timeout rate | Thời gian phản hồi và phần đuôi phân phối |
| Throughput | Requests/s, transactions/s, rows/s, MB/s | Lượng công việc hoàn thành |
| SQL | Calls, total time, mean time, rows, query fingerprint | Truy vấn nào tiêu thụ tài nguyên |
| Plan | Scan, join, sort, aggregate, estimated/actual rows | Cách database thực thi |
| Buffer/I/O | Shared hit/read, temp read/write, read/write latency | Khối lượng truy cập bộ nhớ và storage |
| CPU | CPU utilization, CPU time, run queue | Mức tiêu thụ xử lý |
| Memory | RSS, cache, work memory, peak memory, swap | Áp lực bộ nhớ và nguy cơ spill |
| Concurrency | Active sessions, pool pending, lock wait, deadlock | Khả năng xử lý đồng thời |
| Write path | WAL bytes, commit latency, checkpoint, write throughput | Chi phí ghi và durability |
| Vận hành | Database size, index size, replication lag, cost | Tác động dài hạn và chi phí |

Không cần thu thập mọi metric cho mọi bài test. Hãy chọn metric liên quan tới giả thuyết thay đổi và một nhóm metric bảo vệ để phát hiện tác động phụ.

### 2.2. Baseline theo query fingerprint

Query fingerprint gom các câu lệnh có cấu trúc giống nhau dù giá trị literal khác nhau. Thay vì theo dõi từng câu có ID hoặc timestamp khác nhau, ta có thể xếp hạng theo fingerprint để biết nhóm SQL nào chiếm phần lớn tổng thời gian.

Trong PostgreSQL, extension `pg_stat_statements` cung cấp thống kê tổng hợp theo truy vấn chuẩn hóa. Ví dụ với các phiên bản có các cột thời gian thực thi hiện hành:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    left(query, 300) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Tên cột có thể khác giữa các phiên bản PostgreSQL và phiên bản extension; hãy kiểm tra schema thực tế trước khi dùng dashboard. Các bộ đếm thường là số liệu tích lũy từ lần reset hoặc thời điểm khởi động, vì vậy nên lấy hai snapshot theo khoảng thời gian và tính delta.

Không chỉ xếp hạng theo `mean_exec_time`. Một truy vấn 10 ms chạy hàng trăm nghìn lần có thể tiêu tốn nhiều tài nguyên hơn truy vấn 2 giây chạy rất ít. Xem đồng thời `calls`, `total_exec_time`, latency phân vị từ tracing và mức độ quan trọng của endpoint.

### 2.3. Ghi lại môi trường baseline

Mỗi lần đo nên lưu:

- Database engine, phiên bản, extension và driver.
- CPU, RAM, storage type, IOPS/throughput limit và filesystem.
- Các tham số database liên quan tới truy vấn và concurrency.
- Schema, index, partition và kích thước dữ liệu.
- Statistics freshness và thời điểm `ANALYZE` gần nhất.
- Connection pool, số client, worker và concurrency.
- Phiên bản ứng dụng, SQL text/fingerprint và dữ liệu đầu vào.
- Cache state, thời gian warm-up và thời điểm chạy.

Khi so sánh hai phiên bản, hãy giữ các yếu tố này giống nhau hoặc ghi rõ khác biệt. Không thể quy kết một thay đổi SQL làm truy vấn nhanh hơn nếu lần chạy sau có nhiều RAM hơn hoặc dataset nhỏ hơn.

## 3. Chuẩn bị dữ liệu và workload đại diện

Một bộ dữ liệu thử nghiệm nhỏ, sạch và có phân bố đều thường không phản ánh hành vi production. Planner và storage có thể chọn cách xử lý rất khác khi dữ liệu lớn, lệch phân bố hoặc có nhiều giá trị trùng.

### 3.1. Đặc điểm dữ liệu cần giữ

- Số dòng và kích thước bảng gần với quy mô cần dự báo.
- Cardinality, skew và tỷ lệ NULL của các cột lọc/join.
- Tỷ lệ dữ liệu mới, dữ liệu cũ và dữ liệu thường xuyên cập nhật.
- Phân bố kích thước row, JSON/TOAST hoặc payload lớn.
- Số lượng và kích thước index.
- Số partition và phân bố dòng giữa partition.
- Mức độ bloat và trạng thái vacuum phù hợp với production.
- Quan hệ khóa ngoại, unique constraint và trigger có ảnh hưởng tới write path.

Nếu không thể dùng dữ liệu production, tạo dữ liệu tổng hợp có phân bố tương tự. Chỉ tạo số dòng giống nhau là chưa đủ; cần tái hiện skew và tương quan giữa các cột nếu chúng ảnh hưởng tới selectivity hoặc join cardinality.

### 3.2. Bảo vệ dữ liệu nhạy cảm

Khi tạo bản sao dữ liệu để benchmark, cần tuân theo chính sách bảo mật và quyền truy cập của tổ chức. Có thể masking, tokenization hoặc sinh dữ liệu tổng hợp. Việc masking phải giữ đặc điểm phân bố cần cho benchmark nhưng không làm lộ thông tin cá nhân hoặc bí mật nghiệp vụ.

### 3.3. Workload mix

Workload nên mô phỏng tỷ lệ các loại thao tác thực tế:

| Nhóm | Ví dụ | Tác động cần quan sát |
|---|---|---|
| Point lookup | Tìm đơn hàng theo ID | Index lookup, cache hit, latency |
| Range scan | Đọc sự kiện theo khoảng thời gian | Số trang đọc, partition pruning, I/O |
| Join/report | Join nhiều bảng và aggregate | Join order, hash/sort memory, temp spill |
| Insert | Nạp sự kiện hoặc đơn hàng | WAL, index maintenance, commit latency |
| Update | Đổi trạng thái, cập nhật số dư | Row lock, HOT update, WAL và bloat |
| Delete/retention | Xóa dữ liệu cũ | Dead tuples, vacuum, WAL, lock duration |
| Concurrent mixed | Đọc và ghi đồng thời | p95/p99, lock, CPU/I/O contention |

Nếu chỉ benchmark SELECT trong khi production có nhiều UPDATE, việc thêm index có thể trông rất tốt nhưng làm tổng workload chậm hơn. Hãy giữ tỷ lệ đọc/ghi và mức đồng thời gần với tình huống mục tiêu.

### 3.4. Tham số truy vấn phải đa dạng

Một prepared statement có thể nhận nhiều giá trị tham số với selectivity rất khác nhau. Ví dụ `tenant_id = ?` có thể trả 10 dòng với tenant nhỏ nhưng hàng triệu dòng với tenant lớn. Một plan tốt cho tenant nhỏ có thể kém cho tenant lớn.

Tập test cần bao gồm:

- Giá trị phổ biến và hiếm.
- Khoảng thời gian ngắn và dài.
- Tenant hoặc nhóm dữ liệu lớn nhất.
- Giá trị NULL hoặc biên nếu hợp lệ.
- Trang đầu và trang sâu nếu có pagination.
- Trường hợp trả ít dòng và trường hợp trả nhiều dòng.

Không chỉ benchmark một tham số thuận lợi rồi suy rộng cho mọi request.

## 4. Thiết kế các loại kiểm thử

Không một bài test đơn lẻ nào bao phủ mọi loại regression. Chọn cấp độ kiểm thử theo chi phí và phạm vi thay đổi.

### 4.1. Microbenchmark cho một truy vấn

Microbenchmark tập trung vào một query hoặc một thao tác cụ thể, thường chạy nhiều lần với cùng dataset và parameter set. Nó hữu ích để so sánh SQL rewrite, index hoặc plan.

Giới hạn: microbenchmark không thể hiện đầy đủ contention, connection pool, background jobs và I/O cạnh tranh của toàn hệ thống. Dùng nó để sàng lọc thay đổi, sau đó kiểm tra workload hỗn hợp.

### 4.2. Load test

Load test chạy hệ thống ở mức tải dự kiến hoặc tải đỉnh để kiểm tra SLA và throughput. Tăng tải theo các mức đã định nghĩa, giữ mỗi mức đủ lâu để hệ thống ổn định và đo latency phân vị.

### 4.3. Stress test

Stress test vượt mức tải dự kiến để tìm điểm bão hòa và hành vi khi quá tải. Mục tiêu là xác định throughput tối đa, điểm p99 tăng mạnh, queue bắt đầu tích lũy và cách hệ thống phục hồi khi giảm tải.

### 4.4. Soak test

Soak test chạy workload ổn định trong thời gian dài để phát hiện vấn đề tích lũy như memory leak, connection leak, bloat, WAL retention, cache churn, autovacuum backlog hoặc queue tăng dần.

### 4.5. Spike test

Spike test tạo tải tăng đột ngột để xem connection pool, cache, autoscaling, queue và database phản ứng ra sao. Nó hữu ích với hệ thống có giờ cao điểm, chiến dịch hoặc batch khởi chạy đồng thời.

### 4.6. Mixed workload và concurrency test

Mixed workload chạy nhiều loại truy vấn cùng lúc, gồm cả đọc và ghi. Đây thường là bước quan trọng trước khi chấp nhận thay đổi index hoặc cấu hình vì chi phí của một thao tác có thể ảnh hưởng tới thao tác khác.

## 5. So sánh execution plan trước và sau

Execution plan giải thích database định đọc dữ liệu bằng cách nào. Kiểm thử hồi quy cần lưu plan trước và sau thay đổi để nhận diện thay đổi access path, ước lượng cardinality và chi phí tài nguyên.

### 5.1. Lấy plan trong PostgreSQL

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
ORDER BY created_at DESC
LIMIT 50;
```

Trên phiên bản hỗ trợ, có thể thêm `WAL` để xem thống kê WAL của câu lệnh ghi trong một số trường hợp. Các tùy chọn và trường đầu ra phụ thuộc phiên bản.

Với mỗi plan, ghi nhận:

- Node type và thứ tự join.
- Estimated rows và actual rows.
- Loops của từng node.
- Buffers hit/read/dirtied/written.
- Sort method, memory và disk spill.
- Hash batches và memory usage.
- Planning time và execution time.
- Settings liên quan nếu được hiển thị.

### 5.2. Estimated rows so với actual rows

Nếu planner ước lượng 100 dòng nhưng thực tế có 1 triệu dòng, nó có thể chọn nested loop hoặc join order không phù hợp. Sai lệch có thể đến từ statistics cũ, skew, tương quan giữa các cột hoặc parameter-sensitive plan.

Sau thay đổi, không chỉ nhìn node `Index Scan` xuất hiện. Hãy xem tổng buffers, actual rows, số loops và latency. Một index scan có thể vẫn chậm nếu nó phải truy cập heap hàng triệu lần hoặc trả phần lớn bảng.

### 5.3. Plan text không phải mục tiêu tối ưu duy nhất

Plan có thể thay đổi mà hiệu năng không xấu đi; planner cost không phải thời gian thực tế và có thể khác giữa môi trường. Ngược lại, plan text giống nhau nhưng storage latency hoặc concurrency thay đổi khiến query chậm hơn.

Hãy so sánh execution plan cùng với metric thực thi. Không đặt điều kiện CI cứng rằng plan phải giống hệt từng dòng, trừ khi có lý do đặc biệt và kiểm soát phiên bản rất chặt.

### 5.4. EXPLAIN ANALYZE có chi phí

`EXPLAIN ANALYZE` thực thi câu lệnh và đo thời gian bên trong server. Nó có thể làm thay đổi cache state, gây tải và với câu lệnh ghi sẽ thực hiện tác dụng phụ. Nếu cần phân tích DML, dùng clone/staging hoặc transaction có thể rollback và xác nhận mọi tác dụng phụ đều nằm trong transaction. Không chạy truy vấn nguy hiểm trên production chỉ để thu plan.

Thời gian trong `EXPLAIN ANALYZE` cũng không bao gồm toàn bộ thời gian truyền kết quả qua mạng tới ứng dụng. Đối với truy vấn trả nhiều dòng, cần đo end-to-end từ client.

## 6. Kiểm thử hồi quy sau thay đổi SQL

SQL rewrite có thể thay đổi thứ tự join, cardinality, filter pushdown, số round trip hoặc cách sử dụng index.

### 6.1. Kiểm tra tính tương đương

Trước khi so hiệu năng, xác nhận hai câu SQL trả cùng tập kết quả theo semantics nghiệp vụ:

- Cùng điều kiện lọc và ranh giới thời gian.
- Cùng cách xử lý NULL.
- Cùng quy tắc duplicate và join cardinality.
- Cùng thứ tự nếu ứng dụng phụ thuộc thứ tự; cần `ORDER BY` rõ ràng.
- Cùng timezone và precision.
- Cùng hành vi khi dữ liệu liên quan không tồn tại.

Với truy vấn tổng hợp, có thể đối chiếu count, sum, min/max và checksum theo nhóm. Với tập kết quả lớn, dùng so sánh theo khóa ổn định hoặc hash phân vùng để tìm khác biệt.

### 6.2. Test nhiều bộ tham số

Chạy cùng câu SQL với bộ tham số đại diện: selectivity cao/thấp, tenant nhỏ/lớn, khoảng thời gian ngắn/dài và trường hợp dữ liệu rỗng. Nếu ứng dụng dùng prepared statement, kiểm tra hành vi plan cache của driver và database.

### 6.3. Đo end-to-end

Đo thời gian từ ứng dụng gửi query tới lúc đọc hết kết quả. Bao gồm:

- Pool acquisition và network round trip.
- Parse/prepare nếu có.
- Server execution.
- Transfer result set.
- Decode và mapping ở driver/ORM.
- Số lượng dòng/cột trả về.

Một SQL nhanh hơn trong server nhưng trả nhiều cột hơn có thể làm request chậm hơn do network và mapping.

## 7. Kiểm thử hồi quy sau thay đổi index

Index tác động cả đọc và ghi. Một index mới có thể giảm số trang đọc cho truy vấn mục tiêu nhưng làm tăng dung lượng, WAL, cache pressure và chi phí INSERT/UPDATE/DELETE.

### 7.1. Đo lợi ích đọc

- Query latency và throughput của các truy vấn dùng index.
- Actual rows, buffers read và heap fetches.
- Sort được loại bỏ hay không.
- Tỷ lệ cache hit và kích thước index.
- Kết quả với tham số có selectivity khác nhau.

### 7.2. Đo chi phí ghi

- INSERT/UPDATE/DELETE throughput.
- WAL bytes và commit latency.
- Index size và tốc độ tăng dung lượng.
- HOT update ratio nếu liên quan.
- Vacuum/index maintenance và replication lag.
- Buffer cache pressure do index lớn.

### 7.3. Kiểm tra index có thực sự được dùng

Trong PostgreSQL, thống kê index theo bảng có thể giúp xem số lần scan và buffer:

```sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;
```

Đây là thống kê tích lũy và cần đọc cùng `stats_reset`, thời gian quan sát và workload. `idx_scan` thấp không tự động chứng minh index vô dụng: index có thể phục vụ constraint, query hiếm nhưng quan trọng hoặc vừa mới được tạo.

### 7.4. Index mới có thể làm truy vấn khác chậm hơn

Index chiếm cache và storage; nhiều index làm write amplification tăng. Planner cũng có thêm lựa chọn, có thể chọn plan khác khi statistics hoặc parameter thay đổi. Kiểm tra top query trước và sau, không chỉ query được tạo index để phục vụ.

Khi thử tạo index, có thể dùng môi trường clone hoặc canary. Với PostgreSQL, `CREATE INDEX CONCURRENTLY` giảm mức chặn DML so với cách tạo index thông thường nhưng có nhiều phase, tốn I/O và cần thêm dung lượng; nó không thể chạy bên trong transaction block. Việc dùng concurrently không thay thế benchmark.

## 8. Kiểm thử hồi quy sau thay đổi cấu hình

Tham số cấu hình có thể thay đổi hành vi trên toàn instance hoặc database. Một giá trị tốt cho một query không nhất thiết tốt khi nhiều query chạy đồng thời.

### 8.1. Phân loại cấu hình

| Nhóm | Ví dụ PostgreSQL | Tác động cần kiểm tra |
|---|---|---|
| Memory | `shared_buffers`, `work_mem`, `maintenance_work_mem` | Cache, sort/hash, tổng memory khi concurrency tăng |
| Planner | `random_page_cost`, `effective_cache_size`, statistics target | Lựa chọn scan/join và estimated cost |
| Parallelism | `max_parallel_workers`, `max_parallel_workers_per_gather` | CPU concurrency, memory và I/O |
| WAL/checkpoint | `max_wal_size`, `checkpoint_timeout`, `checkpoint_completion_target` | WAL retention, checkpoint I/O, recovery time |
| Connection | `max_connections`, pool size phía ứng dụng | Backend memory, context switching, queueing |
| Vacuum | autovacuum thresholds, workers, cost settings | Dead tuples, I/O và khả năng freeze |

Tên tham số và hành vi có thể thay đổi theo phiên bản. Trước khi test, lưu giá trị hiện tại, context áp dụng (reload/restart), nguồn cấu hình và các tham số phụ thuộc.

### 8.2. Thay đổi từng nhóm có giả thuyết

Nếu thay nhiều tham số cùng lúc, rất khó xác định thay đổi nào tạo lợi ích hoặc regression. Hãy ghi giả thuyết cụ thể, ví dụ:

- “Tăng `work_mem` sẽ giảm temp spill của báo cáo X; kiểm tra memory peak khi chạy 20 báo cáo đồng thời.”
- “Tăng `max_wal_size` sẽ giảm checkpoint do WAL pressure; kiểm tra dung lượng WAL và crash recovery.”
- “Giảm `random_page_cost` có thể thay đổi lựa chọn index scan; kiểm tra nhiều query fingerprint và storage thực tế.”

Thay đổi một biến hoặc một nhóm có quan hệ rõ, đo, ghi kết quả rồi mới chuyển bước. Nếu cần thử nhiều tham số tương tác, dùng ma trận thử nghiệm có kiểm soát và giữ lại baseline.

### 8.3. Kiểm tra memory theo concurrency

Một số tham số memory áp dụng theo operation hoặc backend, không phải một ngân sách duy nhất cho toàn server. Ví dụ `work_mem` có thể được dùng bởi nhiều sort/hash node trong một query và nhiều session cùng lúc. Tăng giá trị này có thể giảm spill cho một truy vấn nhưng tạo memory pressure khi concurrency cao.

Không chỉ benchmark một session. Chạy workload đồng thời, đo RSS, peak memory, swap, temp files và số query bị ảnh hưởng.

### 8.4. Kiểm tra cấu hình I/O và checkpoint

Khi thay đổi checkpoint hoặc tham số ghi, đo:

- Checkpoint frequency và duration.
- Buffers written, write/sync time.
- WAL bytes, FPI và WAL flush latency.
- Storage read/write latency và queue depth.
- Commit p95/p99 và throughput ghi.
- WAL directory size, archive backlog và replication lag.
- Thời gian crash recovery trong thử nghiệm phù hợp.

Không đánh giá cấu hình checkpoint chỉ bằng latency của một truy vấn hoặc số lần checkpoint.

## 9. Kiểm thử hồi quy sau nâng cấp phiên bản database

Nâng cấp phiên bản có thể thay đổi planner, executor, statistics, index format, extension, driver compatibility, WAL behavior và cấu hình mặc định. Một truy vấn có thể chọn plan khác dù SQL và schema không đổi.

### 9.1. Chuẩn bị môi trường so sánh

- Tạo bản sao dữ liệu có kích thước và phân bố tương đương.
- Dùng cùng schema, index và extension tương thích.
- Ghi lại tham số cấu hình và thay đổi mặc định giữa hai phiên bản.
- Chạy `ANALYZE` theo quy trình nhất quán sau restore/upgrade khi cần.
- Giữ cùng workload, parameter set và concurrency.
- Tách riêng chi phí upgrade, warm-up và thời gian chạy ổn định.

Không so sánh một database cũ đã warm cache với một database mới vừa khởi động rồi kết luận phiên bản mới chậm hơn. Cần chạy warm-up có kiểm soát và test cold-cache riêng nếu cold start là yêu cầu vận hành.

### 9.2. So sánh plan và thống kê

Lưu plan của top query trước nâng cấp. Sau nâng cấp, tìm các thay đổi đáng kể:

- Join order hoặc join algorithm đổi.
- Index scan chuyển sang sequential scan hoặc ngược lại.
- Estimated rows thay đổi mạnh.
- Sort/hash bắt đầu spill.
- Parallel plan xuất hiện hoặc biến mất.
- Partition pruning khác trước.
- Planning time tăng hoặc query plan nhạy hơn với tham số.

Không yêu cầu mọi plan phải giống hệt. Mục tiêu là tìm thay đổi có tác động thực tế và hiểu nguyên nhân.

### 9.3. Kiểm tra extension và driver

Xác nhận extension, collation, locale, driver và ORM tương thích với phiên bản mới. Thay đổi collation hoặc kiểu dữ liệu có thể ảnh hưởng thứ tự so sánh và index. Một extension chưa hỗ trợ có thể làm thiếu tính năng hoặc yêu cầu rebuild object.

### 9.4. Kiểm tra cả phục hồi và vận hành

Ngoài benchmark query, kiểm tra backup/restore, replication, failover, monitoring, vacuum, index maintenance, log format và quy trình migration. Một phiên bản có query nhanh hơn nhưng làm backup lâu hơn hoặc replication không ổn định vẫn có thể không đáp ứng yêu cầu production.

## 10. Phương pháp đo lường có độ tin cậy

Hiệu năng có biến động tự nhiên do cache, scheduler, I/O, checkpoint, autovacuum, background job và các client khác. Một lần chạy nhanh hơn không chứng minh có cải thiện.

### 10.1. Warm-up và cold run

Warm-up giúp nạp code, plan và dữ liệu thường dùng vào cache. Cold run đo hành vi khi cache chưa nóng hoặc sau restart. Hai loại trả lời câu hỏi khác nhau:

- Warm workload phản ánh hệ thống ổn định khi dữ liệu thường dùng đã nằm trong cache.
- Cold workload phản ánh restart, failover, cache miss hoặc dữ liệu ít truy cập.

Ghi rõ trạng thái cache và chạy các lượt so sánh tương đương. Không xóa cache production để tạo cold test.

### 10.2. Lặp lại và dùng phân vị

Chạy nhiều vòng độc lập sau warm-up. Báo cáo median và p95/p99, không chỉ mean. Với thời gian query rất ngắn, đo nhiều lần trong một batch để giảm ảnh hưởng của timer và scheduling.

Nếu kết quả có dao động lớn, tăng số lần chạy hoặc điều tra nguồn nhiễu trước khi đặt ngưỡng regression. Không loại bỏ outlier chỉ vì chúng làm kết quả xấu; chỉ loại khi có nguyên nhân đo lường rõ và được ghi lại.

### 10.3. A/B hoặc paired run

Khi có thể, chạy baseline và candidate xen kẽ trên cùng môi trường để giảm ảnh hưởng của drift theo thời gian. Ví dụ:

```text
Run 1: baseline
Run 2: candidate
Run 3: candidate
Run 4: baseline
Run 5: baseline
Run 6: candidate
```

Thứ tự có thể được ngẫu nhiên hóa. Với mỗi cặp, giữ cùng input, concurrency và thời gian warm-up. Cách này giảm nguy cơ candidate luôn được chạy vào giờ ít tải hơn.

### 10.4. Ý nghĩa thống kê và độ lớn tác động

Đừng chỉ hỏi khác biệt có xuất hiện hay không; hãy hỏi khác biệt có đủ lớn để ảnh hưởng SLA hoặc chi phí không. Nếu p95 dao động tự nhiên ±8%, một thay đổi 2% có thể chưa đủ bằng chứng. Nếu p99 tăng 40% và vượt SLA, cần điều tra dù mean chỉ tăng 3%.

Có thể đặt ngưỡng theo cả phần trăm và giá trị tuyệt đối:

```text
Regression nếu:
  candidate_p95 > baseline_p95 * 1.10
  VÀ candidate_p95 vượt SLA
```

Đây chỉ là ví dụ. Một hệ thống có thể cần ngưỡng chặt hơn cho giao dịch quan trọng hoặc ngưỡng rộng hơn cho workload batch. Đặt ngưỡng trước khi chạy để tránh điều chỉnh tiêu chí theo kết quả mong muốn.

## 11. Phân tích regression theo từng thay đổi

### 11.1. Khi sửa SQL

Kiểm tra semantics, parameter sensitivity, execution plan, rows, buffers, temp spill, network bytes và client-side processing. Nếu query nhanh hơn nhưng trả nhiều dòng hoặc cột hơn, request có thể vẫn chậm.

### 11.2. Khi thêm hoặc bỏ index

Kiểm tra query được hưởng lợi, top query khác, write throughput, WAL, index size, cache pressure và vacuum. Bỏ index có thể tiết kiệm ghi nhưng làm một query ít gọi trở nên rất chậm; đánh giá theo tầm quan trọng nghiệp vụ và tổng thời gian, không chỉ số lần scan.

### 11.3. Khi thay cấu hình

Kiểm tra cả một session lẫn concurrency thực tế. Tham số memory, parallelism và connection thường có tương tác. Ghi rõ tham số cần reload/restart, giá trị thực tế sau khi áp dụng và cách rollback.

### 11.4. Khi nâng cấp phiên bản

Kiểm tra top query, plan changes, extension, collation, driver, statistics, replication, backup/restore và thao tác vận hành. Tách riêng thời gian warm-up và migration để không gán nhầm chi phí khởi tạo cho hiệu năng ổn định.

## 12. Tự động hóa kiểm thử hồi quy

Không phải mọi benchmark cần chạy trên mỗi commit. Có thể tổ chức theo nhiều lớp để cân bằng tốc độ CI và độ tin cậy.

### 12.1. Lớp nhanh trong pull request

- Chạy correctness tests cho truy vấn thay đổi.
- Chạy microbenchmark ngắn trên dataset cố định.
- So sánh query plan hoặc một số metric quan trọng.
- Cảnh báo nếu query count, result rows hoặc buffers tăng bất thường.

Lớp này sàng lọc regression rõ ràng nhưng không thay thế load test.

### 12.2. Lớp benchmark định kỳ

- Chạy workload mix trên staging có cấu hình gần production.
- Tạo concurrency theo profile thực tế.
- Lưu latency distribution, throughput và resource metrics.
- So sánh với baseline đã version hóa.
- Lưu plan và query fingerprint để điều tra.

### 12.3. Lớp trước phát hành lớn

Với thay đổi index diện rộng, cấu hình instance hoặc database upgrade, chạy load/stress/soak test, kiểm tra backup/restore và failover. Dùng dataset đủ lớn và workload đại diện, có cửa sổ thử nghiệm riêng.

### 12.4. Lưu kết quả benchmark

Mỗi kết quả nên kèm:

- Commit hoặc release identifier.
- Database version và cấu hình.
- Dataset version/size.
- Workload script và seed.
- Machine/storage profile.
- Warm-up và test duration.
- Concurrency và request mix.
- Baseline reference.
- Metric thô và summary.
- Kết luận, ngưỡng và người phê duyệt theo quy trình tổ chức.

Không lưu mỗi ảnh chụp dashboard mà thiếu raw data hoặc cấu hình; như vậy khó tái lập và so sánh sau này.

## 13. Canary và giám sát sau triển khai

Benchmark staging không thể tái hiện hoàn toàn production. Một số regression chỉ xuất hiện khi có dữ liệu thật, traffic skew, cache state hoặc workload đồng thời.

### 13.1. Triển khai canary

Canary áp dụng thay đổi cho một phần nhỏ traffic hoặc một nhóm instance trước. So sánh nhóm candidate với control trong cùng thời điểm nếu có thể.

Theo dõi:

- p95/p99 và error rate theo endpoint.
- Query fingerprint và database time.
- CPU, I/O, memory và connection pool.
- Lock wait, deadlock, WAL và replication lag.
- Cache hit rate hoặc temp spill nếu liên quan.
- Kết quả nghiệp vụ và dữ liệu đối soát.

### 13.2. Ngưỡng dừng và rollback

Định nghĩa trước điều kiện dừng, ví dụ:

- p99 vượt SLA liên tục trong một khoảng xác định.
- Error/timeout rate tăng vượt ngân sách lỗi.
- Throughput giảm ở cùng mức request rate.
- CPU, memory, I/O hoặc connection pool bão hòa.
- Lock wait, deadlock, WAL backlog hoặc replica lag tăng bất thường.
- Sai khác dữ liệu hoặc lỗi nghiệp vụ xuất hiện.

Rollback cần khả thi và được thử trước. Với index, rollback có thể là drop index nhưng cần xem tác động query; với config, khôi phục giá trị cũ; với SQL, chuyển lại code path cũ; với major upgrade, rollback có thể không đơn giản do format dữ liệu và migration. Không giả định mọi database upgrade đều có thể hạ phiên bản bằng cách đổi binary.

## 14. Ví dụ thực tế: thêm index để tăng tốc API tìm đơn hàng

Giả sử API tìm đơn hàng theo `customer_id` và khoảng thời gian có p95 450 ms. Nhóm kỹ thuật đề xuất index ghép:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
```

### Bước 1 — Baseline

Ghi nhận:

- p50/p95/p99 của API.
- Query calls và tổng thời gian fingerprint.
- Plan, actual rows và buffers.
- INSERT/UPDATE throughput của bảng orders.
- WAL bytes, commit latency và index size hiện tại.
- CPU/I/O và concurrency.

### Bước 2 — Tạo dữ liệu thử đại diện

Giữ tỷ lệ đơn hàng theo khách hàng, gồm khách hàng nhỏ và khách hàng lớn. Dùng thời gian dữ liệu đủ dài để query range có thể chọn ít hoặc nhiều dòng. Giữ số lượng index và tỷ lệ ghi gần với production.

### Bước 3 — So sánh candidate

Tạo index trên clone hoặc môi trường thử nghiệm, chạy cùng query và parameter set. Xem index có được dùng, buffers giảm bao nhiêu, sort có được loại bỏ và p95/p99 thay đổi thế nào.

### Bước 4 — Đo chi phí ghi

Chạy cùng workload INSERT/UPDATE. So sánh throughput, WAL, commit latency, index size và cache pressure. Nếu API đọc nhanh hơn 35% nhưng throughput ghi giảm 20% trong khi hệ thống chủ yếu ghi, cần đánh giá lại lợi ích tổng thể.

### Bước 5 — Kiểm tra tải hỗn hợp

Chạy API đọc cùng lúc với ingestion và update. Theo dõi pool pending, CPU, I/O, p99 và lock wait. Xác nhận candidate không chỉ thắng trong benchmark đọc riêng.

### Bước 6 — Canary và quyết định

Triển khai index hoặc SQL mới cho phạm vi nhỏ theo kế hoạch, quan sát cùng metric và có rollback. Chỉ mở rộng khi SLA đọc cải thiện, write path vẫn trong ngân sách và chi phí storage chấp nhận được.

## 15. Mẫu báo cáo kiểm thử hồi quy

Một báo cáo ngắn nhưng có thể kiểm chứng nên có cấu trúc:

| Mục | Nội dung cần ghi |
|---|---|
| Thay đổi | SQL/index/config/version và lý do |
| Giả thuyết | Nút thắt dự kiến được giải quyết |
| Môi trường | Engine/version, CPU/RAM/storage, config |
| Dữ liệu | Kích thước, phân bố, index, statistics |
| Workload | Query mix, parameter set, concurrency, duration |
| Baseline | p50/p95/p99, throughput, CPU/I/O, plan |
| Candidate | Cùng các chỉ số như baseline |
| Regression | Chỉ số xấu đi, độ lớn, mức tin cậy và phạm vi |
| Tác động phụ | Write cost, WAL, storage, replication, memory |
| Kết quả correctness | Row count, aggregate, checksum hoặc đối soát |
| Quyết định | Accept, investigate, tune further hoặc rollback |
| Theo dõi | Canary metrics, alert và thời gian quan sát |

Ví dụ cách kết luận:

```text
Candidate cải thiện p95 của truy vấn tìm đơn hàng 28% và giảm shared
buffer reads 41% ở các tenant nhỏ/lớn đã thử. INSERT throughput giảm 4%,
WAL tăng 6%, index chiếm thêm 3,2 GB. Mixed workload vẫn đáp ứng SLA,
không tăng lock wait và replication lag nằm trong giới hạn. Kết quả dữ liệu
đã đối chiếu. Đề xuất canary 10% traffic với ngưỡng rollback đã định nghĩa.
```

Các số trong đoạn trên chỉ là ví dụ minh họa, không phải ngưỡng mặc định.

## 16. Những sai lầm thường gặp

- **Chỉ đo một lần:** cache, scheduler và I/O có thể làm kết quả dao động; cần lặp lại.
- **Chỉ đo mean:** p95/p99 có thể xấu đi dù mean tốt hơn.
- **Chỉ benchmark một query:** index hoặc config có thể làm workload khác chậm đi.
- **Dùng dataset nhỏ:** không thể hiện skew, bloat, I/O và planner behavior của dữ liệu lớn.
- **Không kiểm soát cache state:** so sánh cold run với warm run tạo kết luận sai.
- **Chỉ nhìn plan text:** plan giống nhau vẫn có thể chậm do I/O; plan khác nhau không nhất thiết xấu.
- **Chỉ nhìn planner cost:** cost là ước lượng tương đối, không phải milliseconds.
- **Không test write path sau khi thêm index:** bỏ qua WAL, storage và chi phí duy trì index.
- **Tăng `work_mem` rồi chỉ chạy một session:** bỏ qua tổng memory khi nhiều query đồng thời.
- **Nâng cấp rồi so ngay sau restart:** candidate có thể chưa warm cache hoặc chưa cập nhật statistics theo quy trình.
- **Đặt ngưỡng sau khi xem kết quả:** dễ hợp thức hóa regression; cần định nghĩa tiêu chí trước.
- **Chỉ test staging một lần:** production có traffic skew và background work khác biệt.
- **Không có rollback plan:** phát hiện regression nhưng không thể khôi phục nhanh.
- **Tối ưu tốc độ nhưng không kiểm tra kết quả:** query nhanh hơn nhưng sai dữ liệu là thất bại.

## 17. Checklist kiểm thử hồi quy hiệu năng

- [ ] Đã mô tả thay đổi, giả thuyết và truy vấn/workload bị ảnh hưởng.
- [ ] Đã lưu baseline cùng cấu hình, phiên bản, schema và dữ liệu.
- [ ] Dataset có quy mô, cardinality, skew và tỷ lệ đọc/ghi đại diện.
- [ ] Workload có parameter set phổ biến, hiếm, nhỏ và lớn.
- [ ] Đã đo p50/p95/p99, throughput, timeout và error rate.
- [ ] Đã lưu execution plan và so sánh actual rows, loops, buffers, sort/hash/temp.
- [ ] Đã đo CPU, memory, I/O, WAL, connection, lock wait và replication khi liên quan.
- [ ] SQL mới đã được kiểm tra tính tương đương kết quả.
- [ ] Index mới đã được đánh giá cả lợi ích đọc lẫn chi phí ghi/storage.
- [ ] Config mới đã được test ở concurrency thực tế và có giá trị rollback.
- [ ] Version mới đã được kiểm tra plan, extension, driver, backup/restore và replication.
- [ ] Benchmark được warm-up, lặp lại và so sánh trong điều kiện tương đương.
- [ ] Ngưỡng regression và tiêu chí chấp nhận được đặt trước khi chạy.
- [ ] Mixed workload/load test đã xác nhận không có tác động phụ lớn.
- [ ] Có canary, dashboard, alert và rollback plan.
- [ ] Kết quả, raw metrics, workload script và môi trường được lưu để tái lập.

## Kết luận

Kiểm thử hồi quy hiệu năng biến một thay đổi SQL, index, cấu hình hoặc phiên bản thành một quyết định có bằng chứng. Baseline phải tái lập; dữ liệu và workload phải đại diện; phép đo cần bao gồm latency phân vị, throughput, execution plan và tài nguyên. Đánh giá index phải tính cả write path, đánh giá memory phải tính concurrency, còn nâng cấp phiên bản phải kiểm tra plan, extension và quy trình vận hành.

Hãy lặp lại phép đo, kiểm soát cache và môi trường, đặt ngưỡng trước khi chạy, rồi kiểm tra workload hỗn hợp. Sau khi staging đạt yêu cầu, dùng canary để phát hiện khác biệt production và chỉ mở rộng khi kết quả dữ liệu đúng, SLA được giữ, tài nguyên còn headroom và rollback khả thi. Một thay đổi chỉ nên được chấp nhận khi lợi ích của nó tồn tại trên toàn workload mà không chuyển chi phí sang một đường xử lý khác.
