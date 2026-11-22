# Đo độ trễ, thông lượng, CPU/I/O và tính đúng sau thay đổi

Tối ưu SQL chỉ có ý nghĩa khi chứng minh được truy vấn hoặc workload tốt lên mà kết quả nghiệp vụ vẫn chính xác. Một câu lệnh chạy nhanh hơn trong một lần thử chưa đủ để kết luận thành công: cache có thể đang nóng hơn, dữ liệu thử quá nhỏ, số kết nối khác nhau hoặc workload không đại diện cho production.

Một lần đánh giá tuning cần trả lời bốn nhóm câu hỏi:

1. **Độ trễ:** một request/query mất bao lâu, đặc biệt ở p95 và p99?
2. **Thông lượng:** hệ thống hoàn thành được bao nhiêu request, statement hoặc transaction mỗi giây ở mức concurrency đã xác định?
3. **Tài nguyên:** CPU, bộ nhớ, I/O, buffer pool, lock wait và temporary work thay đổi ra sao?
4. **Tính đúng:** kết quả, side effect, transaction semantics và các invariant nghiệp vụ có giữ nguyên sau thay đổi không?

Bài học này xây dựng quy trình đo trước/sau, lấy số liệu từ Performance Schema và status variables, đo tải ở phía client, so sánh một thay đổi tại một thời điểm và kiểm chứng kết quả. Mục tiêu là biến nhận định “truy vấn có vẻ nhanh hơn” thành kết luận có thể lặp lại và giải thích được.

## 1. Phân biệt bốn nhóm chỉ số

| Nhóm | Chỉ số cần theo dõi | Câu hỏi cần trả lời |
|---|---|---|
| Độ trễ (latency) | p50, p95, p99, max, timeout, error rate | Người dùng phải chờ bao lâu và đuôi phân phối có xấu đi không? |
| Thông lượng (throughput) | completed requests/s, QPS, TPS, rows/s | Hệ thống hoàn thành được bao nhiêu công việc trong một khoảng thời gian? |
| Tài nguyên | CPU, RAM, disk IOPS/latency, bytes read/write, buffer pool, lock waits | Tốc độ đạt được tiêu tốn bao nhiêu tài nguyên và bottleneck nằm ở đâu? |
| Tính đúng (correctness) | row set, giá trị, duplicate, thứ tự, invariant, side effect, transaction outcome | Thay đổi có giữ nguyên hành vi nghiệp vụ không? |

Không dùng một chỉ số thay cho tất cả. Ví dụ, throughput tăng nhưng p99 tăng mạnh có thể làm trải nghiệm người dùng xấu đi. CPU giảm nhưng disk I/O tăng có thể chỉ chuyển bottleneck từ CPU sang storage. Truy vấn nhanh hơn nhưng trả thiếu hàng là một tuning thất bại.

## 2. Độ trễ: đo phân phối, không chỉ đo trung bình

Latency là thời gian từ lúc một request bắt đầu cho tới khi nhận được kết quả theo ranh giới đo đã chọn. Cần thống nhất đang đo:

- Thời gian round-trip từ ứng dụng tới MySQL và nhận kết quả.
- Thời gian statement được MySQL ghi nhận.
- Thời gian toàn bộ transaction, gồm nhiều statement và commit.
- Thời gian API/request có thêm xử lý ứng dụng, serialization hoặc network.

Các con số này không giống nhau. Performance Schema ghi thời gian statement ở phía server; benchmark client thường đo round-trip. Nếu người dùng phàn nàn API chậm, chỉ xem server statement time có thể bỏ sót connection pool wait, network, xử lý ứng dụng hoặc thời gian chờ trước khi SQL được gửi.

### Các percentile thường dùng

| Chỉ số | Cách hiểu |
|---|---|
| p50 | 50% request hoàn thành trong thời gian này hoặc nhanh hơn; biểu diễn mức điển hình. |
| p95 | 95% request hoàn thành trong thời gian này hoặc nhanh hơn; thể hiện phần đuôi chậm đáng kể. |
| p99 | 99% request hoàn thành trong thời gian này hoặc nhanh hơn; nhạy với tail latency. |
| max | Request chậm nhất trong cửa sổ đo; dễ bị ảnh hưởng bởi outlier. |
| mean/average | Tổng thời gian chia số request; có thể che giấu một nhóm request rất chậm. |

Ví dụ:

```text
                         Baseline       Candidate
p50 latency                 8 ms            7 ms
p95 latency                35 ms           42 ms
p99 latency               110 ms          190 ms
Average latency             12 ms           11 ms
```

Candidate có average tốt hơn nhưng p95/p99 xấu hơn. Có thể một số request nhanh hơn trong khi request nặng bị chậm do tranh chấp CPU, I/O, lock hoặc sort. Không nên công bố cải thiện chỉ dựa trên average.

### Percentile cần được đo ở phía client

Các summary view của MySQL thường cung cấp count, average, min/max hoặc tổng thời gian, nhưng không phải lúc nào cũng lưu histogram đủ để tính p95/p99 cho từng query digest. Dùng benchmark/load-test harness ở phía client có histogram latency (ví dụ HDR Histogram hoặc công cụ benchmark có percentile) để thu thập p50/p95/p99.

Khi đo, ghi cả timeout và lỗi. Không loại request timeout khỏi phân phối rồi kết luận latency tốt hơn; timeout phải được tính vào error/SLO và phân tích riêng.

## 3. Thông lượng: xác định đúng đơn vị công việc

Throughput là lượng công việc hoàn thành trong một đơn vị thời gian. Trong MySQL và ứng dụng, cần phân biệt:

- **Request/s:** số request ứng dụng hoàn tất mỗi giây.
- **QPS:** số câu lệnh SQL được thực thi mỗi giây.
- **TPS:** số transaction hoàn tất mỗi giây.
- **Rows/s:** số hàng được đọc hoặc ghi mỗi giây; hữu ích cho batch job nhưng không đại diện đầy đủ cho công việc nghiệp vụ.

Một request có thể thực hiện 1, 5 hoặc 20 câu SQL. Vì vậy, QPS tăng chưa chắc request throughput tăng. Một transaction có thể chứa nhiều statement; đếm statement không tương đương đếm transaction commit.

Khi báo cáo, ghi rõ đơn vị và phạm vi:

```text
Completed API requests:  820 requests/s
SQL statements:        4,100 statements/s
Committed business tx:   760 transactions/s
Concurrency:              64 clients
Measurement window:       5 minutes after warm-up
```

Đây là số liệu minh họa. Một phép đo thật cần ghi số liệu của workload đang thử và số lỗi/timeout đi kèm.

### Offered load và completed throughput

Offered load là tốc độ client gửi công việc vào hệ thống; completed throughput là tốc độ hệ thống hoàn thành công việc. Khi hệ thống bão hòa, client vẫn có thể gửi 1.000 request/s nhưng server chỉ hoàn tất 700 request/s; phần còn lại tạo queue, timeout hoặc backlog.

Luôn ghi cả offered rate, completed rate, concurrency và error rate. Nếu chỉ ghi số request được gửi, bạn có thể nhầm tải được tạo ra với công việc thực sự hoàn thành.

### Concurrency và saturation

Đo ở nhiều mức concurrency để tìm điểm hệ thống bắt đầu bão hòa, ví dụ 1, 8, 16, 32 và 64 client. Không chỉ đo ở một mức tải. Ở concurrency thấp, một query có thể rất nhanh; ở concurrency cao, lock contention, buffer pool pressure, CPU scheduling hoặc I/O queue có thể làm p99 tăng mạnh.

Khi tăng concurrency, quan sát:

- Completed throughput còn tăng hay đã đi ngang/giảm.
- p95/p99 tăng nhanh ở mức nào.
- `Threads_running`, CPU và I/O queue có tăng không.
- Lock wait, deadlock, timeout và connection pool queue có tăng không.
- Error rate và số request bị loại bỏ có thay đổi không.

## 4. CPU và I/O: xác định tài nguyên đang giới hạn workload

### CPU

CPU có thể tăng do scan nhiều hàng, biểu thức trên nhiều row, join fan-out, sort, aggregate, parse/execute quá nhiều statement hoặc concurrency cao. Đo CPU của tiến trình MySQL và CPU toàn host trong cùng cửa sổ benchmark.

Performance Schema statement timer là thời gian chờ/elapsed của statement, không phải CPU time thuần. Để xác định CPU, kết hợp số liệu process/host như Windows Performance Monitor hoặc Task Manager; trên Linux có thể dùng `pidstat`, `top` hoặc công cụ giám sát tương đương.

Các dấu hiệu cần xem:

- CPU process `mysqld` gần bão hòa trong lúc throughput không tăng.
- Số hàng examined hoặc số vòng lặp JOIN lớn.
- p95/p99 tăng cùng CPU utilization.
- Sort/aggregate hoặc biểu thức tính toán xuất hiện ở các query digest tốn thời gian.

### Disk I/O

I/O có thể tăng khi working set không nằm trong buffer pool, truy vấn đọc nhiều page ngẫu nhiên, sort/materialization spill ra disk, checkpoint/flush ghi dữ liệu hoặc storage có latency cao.

Đo cả:

- IOPS và throughput đọc/ghi của thiết bị.
- Average và tail disk latency.
- Queue depth hoặc thời gian chờ thiết bị.
- Bytes read/written.
- MySQL file I/O wait và InnoDB physical reads.

Performance Schema file wait phản ánh thời gian MySQL chờ các event I/O được instrument; nó không thay thế số liệu latency từ thiết bị/OS. Kết hợp cả hai để biết MySQL có đang chờ file và thiết bị có thực sự bão hòa không.

### Buffer pool

InnoDB buffer pool cache data page và index page. Khi page cần đọc đã ở trong buffer pool, engine tránh được physical read tương ứng. Nếu working set lớn hơn bộ nhớ hoặc truy cập phân tán, physical read có thể tăng.

Hai status counter thường dùng:

- `Innodb_buffer_pool_read_requests`: logical read request.
- `Innodb_buffer_pool_reads`: số lần InnoDB phải đọc page từ storage vào buffer pool.

Có thể tính tỷ lệ hit gần đúng trên một khoảng đo:

\[
\text{Approx. hit ratio} = 1 - \frac{\Delta\text{Innodb\_buffer\_pool\_reads}}{\Delta\text{Innodb\_buffer\_pool\_read\_requests}}
\]

Đây chỉ là chỉ số tổng quan. Nó bị ảnh hưởng bởi read-ahead, workload và khoảng lấy mẫu; không dùng một tỷ lệ cao để khẳng định mọi query đều nhanh hoặc không có I/O bottleneck.

## 5. Xây dựng baseline có thể lặp lại

Baseline là số liệu trước thay đổi, được thu thập trong điều kiện đủ rõ để lần đo sau có thể so sánh. Một baseline hữu ích cần ghi:

1. Phiên bản MySQL, storage engine và cấu hình liên quan.
2. Schema, index, row count và phân bố dữ liệu.
3. SQL chính xác, parameter values và query digest.
4. Isolation level, autocommit và transaction boundary.
5. Dataset snapshot hoặc quy trình nạp dữ liệu giống nhau.
6. Cache state: warm-up, buffer pool state và cách xử lý lần chạy đầu.
7. Concurrency, connection pool size, offered load và thời gian chạy.
8. p50/p95/p99, completed throughput, errors và timeouts.
9. CPU, memory, disk I/O, lock wait và temporary/sort counters.
10. Execution plan và actual rows/loops nếu có thể đo an toàn.

Không so sánh một lần chạy cold-cache với một lần chạy warm-cache rồi quy toàn bộ chênh lệch cho index mới. Cần chọn một phương pháp nhất quán: hoặc warm-up cả hai trước khi đo, hoặc chủ động đo riêng cold-start và steady-state.

### Warm-up và cache state

Warm-up giúp loại bỏ một phần chi phí khởi tạo/cache lạnh trước khi đo steady-state. Nhưng warm-up không được làm thay đổi dữ liệu hoặc khiến một candidate được chạy nhiều lần hơn baseline.

Một quy trình mẫu:

```text
1. Restore cùng một dataset snapshot.
2. Khởi động/chuẩn bị cùng phiên bản và cấu hình server.
3. Chạy warm-up theo cùng workload trong 60-120 giây.
4. Bắt đầu cửa sổ đo cố định, ví dụ 5 phút.
5. Thu latency histogram, completed throughput và tài nguyên.
6. Lặp lại ít nhất vài vòng với cùng điều kiện.
7. Đổi thứ tự baseline/candidate giữa các vòng nếu có thể.
```

Thời gian chỉ là ví dụ; workload thực tế có thể cần warm-up và measurement window dài hơn để ổn định cache và đại diện chu kỳ tải.

### Giữ workload giống nhau

Baseline và candidate phải dùng cùng:

- Tập parameter values, hoặc cùng phân bố parameter.
- Tỷ lệ đọc/ghi và mix các query digest.
- Số client và connection pool.
- Thời gian warm-up/measurement.
- Dữ liệu và thống kê tương đương.
- Giới hạn tài nguyên và điều kiện host.

Nếu một candidate được thử với ít client hơn hoặc ít query nặng hơn, kết quả không còn là phép so sánh công bằng.

## 6. Ví dụ tuning: chuyển điều kiện DATE() thành range predicate

Tạo bảng thử nghiệm với timestamp dạng `DATETIME`:

```sql
CREATE TABLE tuning_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

INSERT INTO tuning_orders (
    order_id, tenant_id, status, created_at, total_amount
)
VALUES
    (1, 42, 'PAID', '2026-01-15 08:10:00', 100.00),
    (2, 42, 'PAID', '2026-01-15 16:30:00', 250.00),
    (3, 42, 'NEW',  '2026-01-15 18:45:00',  80.00),
    (4, 42, 'PAID', '2026-01-16 00:05:00', 300.00),
    (5, 99, 'PAID', '2026-01-15 12:00:00', 500.00);
```

Baseline query:

```sql
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND DATE(created_at) = '2026-01-15'
ORDER BY created_at DESC, order_id DESC;
```

Áp dụng hàm `DATE()` lên cột có thể khiến index thông thường trên `created_at` không được dùng làm range access như mong muốn. Candidate query giữ cùng điều kiện nghiệp vụ bằng khoảng nửa mở:

```sql
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00'
ORDER BY created_at DESC, order_id DESC;
```

Tạo index ứng viên:

```sql
CREATE INDEX idx_tuning_orders_tenant_status_created
ON tuning_orders (tenant_id, status, created_at);
```

Với InnoDB, secondary index mang primary key làm phần định vị; `order_id` là primary key nên không cần lặp lại trong định nghĩa index. Sau khi tạo index, kiểm tra kế hoạch:

```sql
EXPLAIN FORMAT=TREE
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00'
ORDER BY created_at DESC, order_id DESC;

EXPLAIN ANALYZE
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00'
ORDER BY created_at DESC, order_id DESC;
```

Fixture chỉ có năm hàng nên optimizer có thể vẫn chọn table scan. Dùng dataset đủ lớn để đánh giá access path và thời gian thực tế; không lấy plan của bảng nhỏ làm bằng chứng rằng index không hữu ích.

### Kiểm tra tương đương của kết quả

Trên `DATETIME`, khoảng nửa mở từ đầu ngày tới trước đầu ngày tiếp theo tương đương với `DATE(created_at) = ngày` trong ví dụ này. Để so sánh row set và giá trị, có thể lưu hai kết quả trong temporary table trên cùng session:

```sql
CREATE TEMPORARY TABLE result_before AS
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND DATE(created_at) = '2026-01-15';

CREATE TEMPORARY TABLE result_after AS
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00';
```

Đối chiếu số hàng:

```sql
SELECT 'before' AS result_set, COUNT(*) AS row_count
FROM result_before
UNION ALL
SELECT 'after', COUNT(*)
FROM result_after;
```

Tìm hàng thiếu, thừa hoặc có giá trị khác:

```sql
SELECT b.order_id, 'missing_or_changed' AS difference
FROM result_before AS b
LEFT JOIN result_after AS a
  ON a.order_id = b.order_id
WHERE a.order_id IS NULL
   OR NOT (b.status <=> a.status)
   OR NOT (b.created_at <=> a.created_at)
   OR NOT (b.total_amount <=> a.total_amount)

UNION ALL

SELECT a.order_id, 'extra' AS difference
FROM result_after AS a
LEFT JOIN result_before AS b
  ON b.order_id = a.order_id
WHERE b.order_id IS NULL;
```

Kết quả mong đợi là không có dòng khác biệt. Hai temporary table trên so sánh membership và giá trị, không bảo đảm thứ tự kết quả vì bảng không có thứ tự vật lý SQL. Nếu truy vấn nghiệp vụ yêu cầu thứ tự, chạy cả hai SELECT với cùng `ORDER BY` và so sánh sequence ở phía client.

**Lưu ý kiểu thời gian:** ví dụ dùng `DATETIME`. Nếu cột là `TIMESTAMP`, MySQL chuyển đổi theo session time zone khi đọc/ghi; phải xác định timezone của ngày nghiệp vụ và dùng cùng timezone cho hai biểu thức. Không thay thế máy móc `DATE(timestamp_col)` bằng mốc UTC nếu truy vấn cũ đang áp dụng ngày theo timezone khác.

## 7. Đo latency và throughput ở phía ứng dụng

Một benchmark client nên ghi ít nhất:

```text
test_name
query_or_request_id
concurrency
offered_requests_per_second
completed_requests_per_second
success_count
error_count
timeout_count
p50_ms
p95_ms
p99_ms
max_ms
measurement_duration_seconds
```

Nếu workload có nhiều loại truy vấn, thu histogram riêng cho từng loại hoặc query class. Một digest nhanh chạy hàng triệu lần có thể che khuất một digest chậm chạy ít lần nếu chỉ nhìn latency tổng thể.

### Tránh coordinated omission

Load generator cần tiếp tục ghi nhận độ trễ của các request lẽ ra phải được gửi trong lúc server đang bận. Nếu client chỉ gửi request mới sau khi request trước hoàn tất, nó có thể giảm offered load khi server chậm và đánh giá thấp tail latency. Chọn công cụ có cách phát tải và histogram phù hợp với mục tiêu đo; ghi rõ mô hình closed-loop hay open-loop.

### Đo transaction end-to-end

Với transaction gồm nhiều statement, đo thời gian từ trước statement đầu tiên đến sau `COMMIT`/`ROLLBACK`, không chỉ đo câu SELECT nhanh nhất. Transaction có thể chờ lock, flush log hoặc network round-trip giữa các statement. Ghi số transaction thành công và transaction bị rollback cùng latency distribution.

## 8. Dùng Performance Schema để tìm query digest tốn thời gian

`performance_schema.events_statements_summary_by_digest` tổng hợp statement theo normalized digest. View này hữu ích để tìm query có tổng thời gian cao, nhiều hàng examined hoặc tạo temporary/sort work.

```sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(AVG_TIMER_WAIT / 1000000000, 2) AS avg_ms,
    ROUND(MAX_TIMER_WAIT / 1000000000, 2) AS max_ms,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_CREATED_TMP_TABLES,
    SUM_CREATED_TMP_DISK_TABLES,
    SUM_SORT_ROWS,
    SUM_NO_INDEX_USED
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Các giá trị timer của Performance Schema được biểu diễn theo picosecond. Chia `AVG_TIMER_WAIT` cho 1.000.000.000 để đổi sang millisecond. `SUM_TIMER_WAIT` xếp hạng theo tổng thời gian tiêu thụ; query chạy nhiều lần có thể đứng đầu dù mỗi lần không quá chậm.

Đọc các cột cùng nhau:

- `COUNT_STAR`: số lần statement được ghi nhận.
- `AVG_TIMER_WAIT` và `MAX_TIMER_WAIT`: average và maximum server-side statement time.
- `SUM_ROWS_EXAMINED`: tổng số hàng đã xem xét.
- `SUM_ROWS_SENT`: tổng số hàng gửi về client.
- `SUM_CREATED_TMP_TABLES` và `SUM_CREATED_TMP_DISK_TABLES`: số internal temporary table được ghi nhận.
- `SUM_SORT_ROWS`: số hàng đã sort.
- `SUM_NO_INDEX_USED`: số lần statement được thực hiện mà không dùng index.

Summary theo digest không cung cấp p95/p99 trực tiếp. Nó cũng có thể gộp nhiều parameter values vào cùng digest, nên cần kết hợp với application tracing hoặc slow log để xác định parameter gây chậm.

### Xem table I/O wait

```sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    COUNT_READ,
    ROUND(SUM_TIMER_READ / 1000000000000, 3) AS read_wait_seconds,
    COUNT_WRITE,
    ROUND(SUM_TIMER_WRITE / 1000000000000, 3) AS write_wait_seconds
FROM performance_schema.table_io_waits_summary_by_table
WHERE OBJECT_SCHEMA = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Các timer trong Performance Schema là số tích lũy và phụ thuộc instrumentation. Đây là thời gian wait được ghi nhận ở lớp table handler, không phải latency vật lý thuần của thiết bị. Dùng để tìm bảng có hoạt động I/O nổi bật, sau đó đối chiếu file/device metrics.

### Xem file I/O wait

```sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS wait_seconds
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE EVENT_NAME LIKE 'wait/io/file/%'
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Truy vấn này giúp tìm loại file event có tổng wait cao, chẳng hạn data file hoặc redo log file nếu instrumentation tương ứng được bật. Counter mang tính tích lũy từ khi khởi động/reset phù hợp; dùng delta trong cửa sổ đo thay vì chỉ nhìn giá trị tuyệt đối.

## 9. Đo InnoDB buffer pool và status counters

Lấy snapshot các counter trước và sau một cửa sổ workload:

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_running',
    'Threads_connected',
    'Questions',
    'Queries',
    'Slow_queries',
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_data_read',
    'Innodb_data_written',
    'Created_tmp_tables',
    'Created_tmp_disk_tables'
);
```

Ghi snapshot trước khi benchmark, chạy workload trong thời gian cố định rồi lấy snapshot thứ hai. Delta giữa hai lần đo giúp ước lượng số logical/physical reads, bytes đọc/ghi, temporary tables và mức concurrency trong cửa sổ đó.

Không reset global status counter trên production chỉ để tiện đo nếu chưa hiểu ảnh hưởng tới các hệ thống giám sát khác. Chụp giá trị trước/sau và tính delta thường an toàn hơn.

### Diễn giải một số counter

| Counter | Cách sử dụng |
|---|---|
| `Threads_running` | Số thread đang thực thi, không chỉ kết nối đang mở. Quan sát cùng CPU và throughput. |
| `Threads_connected` | Số connection đang mở; so với connection pool và giới hạn server. |
| `Questions`/`Queries` | Counter statement theo định nghĩa của MySQL; không coi là business TPS. |
| `Innodb_buffer_pool_read_requests` | Logical page read requests. |
| `Innodb_buffer_pool_reads` | Physical page reads vào buffer pool. |
| `Innodb_data_read`/`Innodb_data_written` | Bytes InnoDB đã đọc/ghi theo counter tương ứng. |
| `Created_tmp_disk_tables` | Internal temporary tables được ghi nhận là on-disk; không đại diện cho mọi file tạm của filesort hoặc mọi memory-mapped temporary storage. |

Counter có thể chịu ảnh hưởng của toàn bộ workload trên instance, không riêng truy vấn đang thử. Dùng instance thử nghiệm hoặc cô lập workload khi cần gắn thay đổi với một query cụ thể.

## 10. Đo CPU, disk và memory ở cấp host

SQL status variables không thay thế giám sát hệ điều hành. Trong cùng khoảng benchmark, ghi:

| Tài nguyên | Số liệu nên thu thập | Diễn giải |
|---|---|---|
| CPU | mysqld process CPU, host CPU, run queue | CPU gần 100% kéo dài trong khi throughput đi ngang có thể báo hiệu CPU saturation. |
| Memory | mysqld RSS/working set, available memory, swap/page faults | RAM thiếu hoặc swap có thể làm latency tăng đột biến. |
| Disk | read/write IOPS, MB/s, average/p95 latency, queue depth | I/O wait cao cùng device latency cao gợi ý storage bottleneck. |
| Network | bytes/s, retransmit, connection latency | Có thể giới hạn kết quả lớn hoặc nhiều round-trip. |
| MySQL | Threads_running, buffer pool reads, file wait, lock wait | Giúp nối hoạt động SQL với tài nguyên host. |

Trên Windows, có thể dùng Performance Monitor để theo dõi process `mysqld`, CPU, working set và disk counters. Trên Linux, dùng công cụ như `iostat`, `pidstat`, `vmstat` hoặc hệ thống observability sẵn có. Chọn đúng volume chứa data, redo log và temporary files; chúng có thể nằm trên các thiết bị khác nhau.

## 11. Kiểm soát biến số khi so sánh trước/sau

Một benchmark chỉ có giá trị nếu baseline và candidate được thử trong điều kiện đủ tương đồng. Các yếu tố dễ làm sai phép so sánh:

- Dataset khác số hàng hoặc phân bố dữ liệu.
- Buffer pool một bên nóng, bên còn lại lạnh.
- Một phép đo chạy trong giờ tải thấp, phép kia trong giờ cao.
- Background job, backup, purge hoặc replication hoạt động khác nhau.
- Connection pool size hoặc concurrency khác nhau.
- Parameter values không đại diện cùng phân bố.
- Một bên đã chạy warm-up nhiều hơn.
- Host hoặc storage có workload của process khác.
- Một candidate làm thay đổi plan của query khác do index/cache contention.

Khi có thể, chạy baseline và candidate trên cùng loại instance và cùng dataset snapshot. Lặp lại nhiều vòng, đổi thứ tự chạy để giảm ảnh hưởng thời gian, và báo cả median của các lần benchmark cùng phân phối từng request.

### Chỉ thay một yếu tố mỗi lần

Nếu đồng thời đổi SQL, index, isolation level, connection pool và buffer size, bạn sẽ không biết yếu tố nào tạo ra kết quả. Thay từng yếu tố hoặc thiết kế thí nghiệm có kiểm soát; ghi lại DDL/config/query version cho mỗi candidate.

Ví dụ bảng ghi nhận:

| Run | Candidate | Concurrency | p95 | p99 | Completed TPS | CPU | Disk read MB/s | Errors |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A1 | Baseline | 32 | 42 ms | 110 ms | 720 | 68% | 85 | 0.02% |
| B1 | Index mới | 32 | 25 ms | 61 ms | 910 | 59% | 44 | 0.01% |

Đây là dữ liệu minh họa, không phải kết quả đo thực tế. Một báo cáo thật nên có nhiều lần lặp và ghi measurement window, warm-up, workload mix, dataset và cấu hình.

## 12. Kiểm chứng tính đúng sau khi tối ưu SELECT

Một rewrite có thể thay đổi semantics dù nhìn có vẻ tương đương. Kiểm tra:

- Số hàng và tập khóa trả về.
- Giá trị từng cột, bao gồm NULL và kiểu dữ liệu.
- Duplicate và semantics `DISTINCT`/`UNION`.
- Thứ tự nếu truy vấn có `ORDER BY`.
- Boundary của range, thời gian, timezone và precision.
- Collation, case sensitivity và so sánh chuỗi.
- Aggregate, rounding, overflow và kiểu numeric.
- Phân quyền/visibility nếu truy vấn có filter theo tenant hoặc user.

Không chỉ so sánh `COUNT(*)` hoặc `SUM(amount)`. Hai tập kết quả khác nhau có thể có cùng count và sum. Hãy so sánh key set và từng giá trị quan trọng; dùng test case ở boundary như đầu/cuối ngày, NULL, duplicate, giá trị âm/0, dữ liệu lớn và nhiều tenant.

### Kiểm tra query result bằng tập đối chiếu

Phần ví dụ ở mục 6 tạo `result_before` và `result_after`. Dùng anti-join để tìm missing/extra và null-safe equality (`<=>`) để so giá trị. Nếu kết quả chứa duplicate mà không có unique key, cần so sánh multiplicity bằng grouping/count thay vì chỉ anti-join theo khóa không duy nhất.

Với truy vấn có thứ tự, cần so sánh sequence ở phía client. Một bảng SQL không có thứ tự được bảo đảm; chỉ `ORDER BY` của SELECT cuối mới xác định thứ tự trả về.

## 13. Kiểm chứng tính đúng sau thay đổi DML

Khi tuning INSERT/UPDATE/DELETE hoặc batch job, phải kiểm tra cả trạng thái dữ liệu và side effect:

- Số hàng bị tác động có đúng không (`ROW_COUNT()` trong cùng session ngay sau statement, hoặc affected rows từ driver)?
- Có hàng nào bị bỏ sót hoặc cập nhật trùng không?
- Unique, foreign key, check constraint và các invariant còn giữ không?
- Trigger, audit row, outbox event hoặc counter nghiệp vụ có thay đổi như trước không?
- Retry có thể thực hiện cùng thao tác hai lần không?
- Transaction commit/rollback có bao trọn đúng tập statement không?

Ví dụ trong môi trường thử nghiệm:

```sql
START TRANSACTION;

UPDATE tuning_orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at < '2026-01-01 00:00:00';

SELECT ROW_COUNT() AS affected_rows;

-- Kiểm tra các invariant trước khi quyết định kết thúc transaction.
SELECT COUNT(*) AS remaining_old_paid_rows
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at < '2026-01-01 00:00:00';

ROLLBACK;
```

Ví dụ rollback để minh họa; DDL không nằm trong transaction này. Trong ứng dụng thật, `ROW_COUNT()` phải được đọc ngay sau DML trong cùng connection vì statement tiếp theo có thể thay đổi giá trị trạng thái đó.

## 14. Kiểm chứng transaction và concurrency

Một query chạy đơn lẻ có thể đúng nhưng khi chạy đồng thời lại gây lost update, double spend, duplicate insert hoặc đọc trạng thái không nhất quán. Sau tuning, kiểm tra:

- Cùng isolation level và transaction boundaries như trước.
- Locking read (`FOR UPDATE`, `FOR SHARE`) còn được dùng đúng nơi cần bảo vệ quyết định ghi.
- Các thao tác cập nhật theo điều kiện vẫn atomic.
- Deadlock/lock timeout có tăng không.
- Retry toàn transaction có giữ tính idempotent không.
- Không xuất hiện phantom hoặc race condition ngoài quy tắc nghiệp vụ cho phép.
- Thứ tự khóa giữa nhiều transaction có thay đổi không.

### Ví dụ invariant số dư

Giả sử hai giao dịch chuyển tiền phải bảo đảm tổng số dư không đổi nếu chuyển khoản thành công và mọi thao tác nằm trong cùng transaction. Test đồng thời cần kiểm tra:

1. Không tài khoản nào bị ghi âm nếu nghiệp vụ cấm số dư âm.
2. Tổng số dư trước/sau bằng nhau khi chỉ chuyển nội bộ.
3. Mỗi transfer ID chỉ được áp dụng một lần.
4. Nếu một bước lỗi, cả hai cập nhật rollback.
5. Hai session cùng rút tiền không thể cùng sử dụng một số dư cũ để vượt quá số tiền hiện có.

Có thể dùng `SELECT ... FOR UPDATE` hoặc conditional UPDATE phù hợp để bảo vệ invariant. Tuning phải giữ nguyên cơ chế bảo vệ concurrency, không loại bỏ lock chỉ để giảm latency đơn lẻ.

## 15. Đánh giá chi phí ghi và tác động ngoài query mục tiêu

Thêm index thường giảm read cost nhưng tăng write amplification. Một candidate có thể làm query A nhanh hơn nhưng khiến INSERT/UPDATE/DELETE chậm hơn, tăng dung lượng, buffer pool pressure và replication lag.

Đo workload mix thay vì chỉ benchmark query được tối ưu:

- Tỷ lệ SELECT/INSERT/UPDATE/DELETE.
- Throughput của write path.
- Redo generation, data bytes written và disk latency.
- Lock wait/deadlock.
- Buffer pool hit/read behavior.
- Replica lag nếu hệ thống có replication.
- Dung lượng index trước/sau.

Một index chỉ có lợi nếu mức tiết kiệm đọc lớn hơn chi phí duy trì trong workload thực tế. Nếu thêm index mới khiến query mục tiêu giảm 30% latency nhưng write throughput giảm 40%, cần đánh giá lại mục tiêu hệ thống.

## 16. Ngưỡng chấp nhận và quyết định rollout

Trước khi chạy benchmark, định nghĩa tiêu chí thành công. Ví dụ:

| Tiêu chí | Ngưỡng minh họa |
|---|---|
| Correctness | 100% test case và invariant phải pass. |
| p95 latency | Không vượt baseline; mục tiêu giảm ít nhất 15%. |
| p99 latency | Không tăng quá 5% ở concurrency mục tiêu. |
| Throughput | Tăng ít nhất 10% hoặc giữ nguyên khi giảm tài nguyên. |
| Error/timeout rate | Không tăng; không chấp nhận regression ngoài SLO. |
| CPU | Không vượt giới hạn vận hành đã đặt. |
| Disk I/O | Không tạo queue/latency vượt ngưỡng storage. |
| Write path | Không giảm throughput dưới mức yêu cầu nghiệp vụ. |

Đây chỉ là ví dụ. Chọn ngưỡng dựa trên SLO, capacity và business priority thực tế. Nếu correctness fail, candidate bị loại dù latency tốt đến đâu.

### Rollout có kiểm soát

1. Lưu baseline SQL, plan, DDL, cấu hình và benchmark result.
2. Triển khai candidate trên staging hoặc canary có dữ liệu/workload tương đương.
3. Chạy correctness suite và concurrency test.
4. Đo latency, throughput, CPU/I/O và error rate.
5. Triển khai theo tỷ lệ nhỏ nếu hệ thống hỗ trợ canary.
6. Theo dõi query digest, p95/p99, resource và business metrics.
7. Rollback SQL/index/config nếu có regression vượt ngưỡng.
8. Giữ lại bằng chứng trước/sau để người khác có thể lặp lại phép đo.

Với DDL tạo index trên bảng lớn, đánh giá thêm thời gian build, metadata lock, disk space, replica lag và cách rollback/drop index. Một truy vấn nhanh hơn trong benchmark chưa đủ nếu migration làm hệ thống gián đoạn.

## 17. Những sai lầm thường gặp khi đo tuning

| Sai lầm | Vì sao gây sai kết luận | Cách khắc phục |
|---|---|---|
| Chỉ đo một lần | Cache, scheduler và background work tạo biến động | Warm-up và lặp nhiều vòng. |
| Chỉ báo average latency | Che khuất p95/p99 và timeout | Thu histogram ở phía client. |
| Gọi QPS là TPS | Một transaction có thể gồm nhiều statement | Ghi rõ request/s, statement/s và transaction/s. |
| Đếm offered load thay completed throughput | Bỏ qua backlog, timeout và lỗi | Ghi cả offered, completed và error rate. |
| Chạy candidate trên cache nóng, baseline trên cache lạnh | So sánh không công bằng | Chuẩn hóa cache state hoặc báo riêng cold/warm runs. |
| Dùng fixture quá nhỏ | Optimizer chọn table scan, không phản ánh workload | Dùng dữ liệu đủ lớn và phân bố đại diện. |
| Chỉ xem EXPLAIN | Plan estimate không cho biết latency thật | Kết hợp EXPLAIN ANALYZE, client metrics và host metrics. |
| Coi statement timer là CPU time | Timer bao gồm thời gian elapsed/wait | Đo CPU ở host/process và đối chiếu Performance Schema waits. |
| Coi `Created_tmp_disk_tables` là mọi file tạm | Không đếm mọi filesort spill/memory-mapped temporary storage | Đọc counter cùng Sort counters, plan và OS I/O. |
| So count/sum để kết luận hai kết quả bằng nhau | Khác row set có thể có cùng count/sum | So key set và giá trị từng hàng, duplicate và order. |
| Chỉ test một client | Không phát hiện lock contention và saturation | Đo nhiều mức concurrency và transaction mix. |
| Bỏ qua write path khi thêm index | Read nhanh hơn nhưng write chậm hơn | Benchmark workload mix và write amplification. |
| Thay nhiều yếu tố cùng lúc | Không xác định được nguyên nhân cải thiện/regression | Thay một yếu tố mỗi lần hoặc thiết kế experiment có kiểm soát. |
| Bỏ qua lỗi/timeout trong báo cáo | Throughput/latency có vẻ tốt giả tạo | Báo success, errors, timeouts và dropped requests. |

## 18. Checklist thực hành trước/sau tuning

### Trước thay đổi

- [ ] Ghi SQL chính xác và parameter distribution.
- [ ] Ghi schema, index, row count và data distribution.
- [ ] Ghi phiên bản MySQL, isolation level, autocommit và cấu hình liên quan.
- [ ] Lấy EXPLAIN/EXPLAIN ANALYZE phù hợp.
- [ ] Đo p50/p95/p99, throughput và error rate ở client.
- [ ] Đo CPU, RAM, disk latency/IOPS, buffer pool và lock waits.
- [ ] Chạy correctness test trên baseline và lưu kết quả chuẩn.

### Sau thay đổi

- [ ] Dùng cùng dataset, workload mix, concurrency và measurement window.
- [ ] Warm-up theo cùng quy tắc.
- [ ] Lặp nhiều vòng và so sánh phân phối latency.
- [ ] So completed throughput, error/timeout và resource usage.
- [ ] So execution plan, actual rows/loops và statement digest.
- [ ] So sánh result set, NULL, duplicate, ordering và business invariants.
- [ ] Test concurrent read/write, rollback, retry và deadlock behavior nếu có liên quan.
- [ ] Đo tác động tới query khác và write path.
- [ ] Chỉ rollout khi correctness pass và performance đạt ngưỡng đã định.

## 19. Bài tập thực hành

### Bài tập A — Tạo baseline

1. Tạo `tuning_orders` và nạp dataset có nhiều tenant, status và ngày.
2. Chạy query dùng `DATE(created_at)`.
3. Thu EXPLAIN, query digest, p50/p95/p99 và completed throughput.
4. Ghi CPU, disk I/O, buffer pool counters và error rate.
5. Lưu baseline cùng parameter distribution và concurrency.

### Bài tập B — Tuning một điều kiện

1. Đổi điều kiện `DATE(created_at)` thành khoảng nửa mở.
2. Tạo composite index phù hợp.
3. Chạy EXPLAIN và EXPLAIN ANALYZE.
4. So sánh rows examined, actual time và access path.
5. Chạy benchmark với cùng concurrency và workload.

### Bài tập C — Kiểm chứng tính đúng

1. Lưu kết quả baseline và candidate trong hai temporary tables.
2. So sánh row count.
3. Dùng anti-join và null-safe equality để tìm missing/extra/changed rows.
4. Kiểm tra boundary đầu ngày/cuối ngày, tenant khác, status khác và NULL nếu schema cho phép.
5. So sánh thứ tự ở client nếu ORDER BY là một phần contract.

### Bài tập D — Đo CPU/I/O và saturation

1. Chạy workload ở concurrency 1, 8, 16 và 32.
2. Ghi completed throughput, p95/p99 và error rate.
3. Ghi mysqld CPU, disk latency, Threads_running và buffer pool read deltas.
4. Xác định điểm throughput đi ngang hoặc latency tăng mạnh.
5. Giải thích bottleneck có dấu hiệu nghiêng về CPU, storage, lock hay connection queue.

### Bài tập E — Đánh giá workload mix

1. Benchmark SELECT sau khi thêm index.
2. Benchmark INSERT/UPDATE với cùng tỷ lệ workload.
3. So sánh read latency, write throughput, bytes written và index size.
4. Kiểm tra query digest khác có bị regression không.
5. Đề xuất giữ, điều chỉnh hoặc bỏ index dựa trên tổng workload.

Bạn hoàn thành bài khi có thể tạo baseline lặp lại, đọc latency percentile và throughput đúng đơn vị, liên hệ CPU/I/O với số liệu MySQL, chứng minh kết quả trước/sau tương đương và đưa ra quyết định rollout dựa trên cả correctness lẫn performance.

## 20. Nguyên tắc cần ghi nhớ

- Tuning thành công phải cải thiện mục tiêu đo được và giữ nguyên tính đúng nghiệp vụ.
- Đo p50/p95/p99 ở client; average không thể thay thế tail latency.
- Phân biệt request/s, QPS, TPS và rows/s; luôn ghi offered load, completed throughput và error rate.
- Đo ở nhiều mức concurrency để tìm saturation và lock contention.
- Performance Schema statement timer là elapsed/wait time, không phải CPU time thuần.
- Kết hợp CPU process/host, disk latency/IOPS, memory, buffer pool và MySQL wait counters.
- Dùng cùng dataset, parameter distribution, workload mix, warm-up, concurrency và measurement window khi so sánh.
- Dùng query digest để tìm statement tiêu thụ tổng thời gian/hàng examined cao; dùng client histogram cho p95/p99.
- Status counters là tích lũy; chụp trước/sau và tính delta thay vì reset tùy tiện trên production.
- So sánh row set, giá trị, NULL, duplicate, ordering, side effect và transaction/concurrency invariants.
- Không kết luận đúng chỉ từ count/sum hoặc một lần benchmark.
- Đánh giá write amplification, storage, replica lag và query khác khi thêm index.
- Đặt performance/correctness gate trước rollout và chuẩn bị phương án rollback.

Khi đo độ trễ, thông lượng, CPU/I/O và tính đúng trong cùng một quy trình có kiểm soát, bạn có thể chứng minh một thay đổi SQL thực sự cải thiện hệ thống. Số liệu trước/sau có thể lặp lại, giải thích được và đủ tin cậy để quyết định triển khai.
