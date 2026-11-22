# Latency, rows examined, rows sent và tần suất thực thi

Một truy vấn SQL không thể được đánh giá chỉ bằng thời gian chạy của một lần thực thi. Một câu lệnh mất 2 ms nhưng chạy 200.000 lần mỗi giờ có thể tiêu tốn nhiều tài nguyên hơn một báo cáo mất 2 giây nhưng chỉ chạy một lần mỗi ngày. Tương tự, truy vấn trả về một hàng chưa chắc nhẹ: nó có thể đã đọc và lọc hàng triệu hàng trước khi tạo kết quả.

Để quan sát đúng workload, cần kết hợp ít nhất bốn góc nhìn: **latency** cho biết người dùng phải chờ bao lâu; **rows examined** cho biết server đã xem xét bao nhiêu hàng; **rows sent** cho biết bao nhiêu hàng được trả về client; **execution frequency** cho biết câu lệnh xuất hiện thường xuyên đến mức nào. Kết hợp các số liệu này theo query digest và theo request giúp xác định truy vấn nào cần tối ưu trước.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt latency trung bình, lớn nhất, tổng thời gian và percentile ở cấp ứng dụng.
- Đọc `ROWS_EXAMINED`, `ROWS_SENT` và hiểu giới hạn của từng chỉ số.
- Dùng query digest để tổng hợp số lần thực thi và chi phí của một mẫu SQL.
- Truy vấn Performance Schema và `sys.statement_analysis` để tìm workload tốn thời gian.
- Kết hợp slow query log, execution plan và trace ứng dụng để tìm nguyên nhân.
- Xếp ưu tiên tối ưu dựa trên tác động tổng thể, không chỉ dựa vào truy vấn chậm nhất.
- Theo dõi thay đổi trước/sau tối ưu mà vẫn giữ ngữ nghĩa và chất lượng dịch vụ.

Các ví dụ giả định MySQL 8.0 trở lên, Performance Schema được bật và ứng dụng dùng prepared statement. Một số cột, view và công cụ có thể khác theo phiên bản hoặc cấu hình; hãy kiểm tra trực tiếp trên instance đang vận hành.

## 1. Bốn câu hỏi khi quan sát một truy vấn

Khi một endpoint hoặc báo cáo chậm, hãy tách vấn đề thành bốn câu hỏi:

| Chỉ số | Câu hỏi | Điều nó giúp nhận biết |
|---|---|---|
| Latency | Mỗi lần chạy mất bao lâu? Tổng thời gian tiêu tốn là bao nhiêu? | Trải nghiệm chờ, tail latency và chi phí tích lũy |
| Rows examined | Server đã xem xét bao nhiêu hàng? | Phạm vi đọc và lượng công việc lọc |
| Rows sent | Server trả về bao nhiêu hàng? | Kích thước kết quả theo số hàng và khả năng trả thừa dữ liệu |
| Execution frequency | Mẫu SQL chạy bao nhiêu lần trong một khoảng thời gian? | Truy vấn lặp, hot path và N+1 |

Không chỉ số nào tự nó kết luận truy vấn tốt hay xấu. Một truy vấn tổng hợp có thể examined nhiều hàng nhưng chỉ sent một hàng; một truy vấn đọc theo primary key có thể examined một hàng và sent một hàng; một truy vấn trả 10.000 hàng có thể có latency thấp ở server nhưng chậm ở client do truyền dữ liệu và dựng object.

## 2. Latency: thời gian của một lần chạy và chi phí tích lũy

**Latency** là khoảng thời gian từ lúc câu lệnh bắt đầu đến khi hoàn thành theo góc nhìn của công cụ đo. Cần phân biệt số liệu ở MySQL với thời gian end-to-end mà ứng dụng ghi nhận.

### Các thống kê latency thường dùng

- **Average latency:** thời gian trung bình mỗi lần thực thi. Hữu ích để so sánh xu hướng, nhưng có thể che giấu các lần chạy rất chậm.
- **Maximum latency:** lần chạy chậm nhất trong khoảng thống kê. Có ích để phát hiện outlier, nhưng rất nhạy với một sự cố đơn lẻ.
- **Total latency:** tổng thời gian của mọi lần thực thi trong khoảng đo. Giúp tìm mẫu SQL tiêu tốn nhiều thời gian tích lũy.
- **p50, p95, p99:** percentile mô tả phân phối. p95 là mức mà 95% lần chạy có latency không vượt quá giá trị đó; p99 tập trung vào phần đuôi chậm hơn.

Ví dụ, hai query digest có số liệu như sau:

| Mẫu truy vấn | Số lần chạy | Average | Total latency gần đúng |
|---|---:|---:|---:|
| A: tra cứu trạng thái đơn hàng | 120.000 | 2 ms | 240 giây |
| B: báo cáo tổng hợp | 20 | 1.200 ms | 24 giây |

Truy vấn B chậm hơn nhiều ở mỗi lần chạy, nhưng mẫu A tiêu tốn tổng thời gian database lớn hơn trong khoảng đo. Nếu giảm latency A từ 2 ms xuống 1 ms, lượng thời gian tích lũy tiết kiệm có thể đáng kể.

Tổng latency cộng dồn không phải thời gian wall-clock của toàn hệ thống: nhiều câu lệnh có thể chạy đồng thời. Dùng nó để so sánh đóng góp tương đối của các digest trong cùng một khoảng đo, không dùng để suy ra thời gian request hoặc thời gian server bận theo cách trực tiếp.

### Average không thay thế percentile

Giả sử 99 request hoàn thành trong 5 ms và một request mất 2 giây. Average có thể vẫn trông chấp nhận được trong một tập đủ lớn, nhưng người dùng gặp lần chạy chậm vẫn thấy timeout hoặc giao diện bị treo.

Các bảng tổng hợp digest của Performance Schema cung cấp số lần chạy, tổng, trung bình và lớn nhất; không nên giả định chúng lưu đủ mẫu thô để tính p95/p99 chính xác. Để theo dõi percentile, hãy dùng histogram hoặc trace/metrics ở tầng ứng dụng, APM hay hệ thống giám sát có lưu phân phối latency. Có thể kết hợp slow query log và statement history để điều tra các lần chạy cụ thể.

### Server latency và application latency

Thời gian ứng dụng đo có thể bao gồm:

- Chờ lấy connection từ connection pool.
- Thời gian gửi request qua mạng đến MySQL.
- Thời gian MySQL thực thi và chờ khóa/I/O.
- Thời gian truyền kết quả về client.
- Driver giải mã dữ liệu, ORM dựng object và logic ứng dụng xử lý.

Performance Schema đo thời gian statement ở phía server; nó không bao gồm toàn bộ thời gian chờ pool hoặc xử lý sau khi dữ liệu đã về ứng dụng. Nếu latency ứng dụng cao nhưng statement latency thấp, hãy kiểm tra pool wait, network, số byte trả về và thời gian mapping.

Timer của statement phản ánh thời gian elapsed ở server, bao gồm thời gian chờ xảy ra trong phạm vi instrument của statement; nó không phải số CPU time thuần. Khi cần tách CPU, lock wait và I/O wait, hãy kết hợp thêm wait events, file I/O và metrics của hệ điều hành.

## 3. Rows examined và rows sent

### Rows examined

`ROWS_EXAMINED` cho biết số hàng được server ghi nhận là đã xem xét trong quá trình thực thi statement. Đây là chỉ số hữu ích để nhận biết truy vấn phải lọc một phạm vi lớn trước khi tìm ra kết quả.

Ví dụ:

```sql
SELECT order_id, status
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-11-01';
```

Nếu điều kiện không có index phù hợp, MySQL có thể phải xem xét rất nhiều hàng rồi mới giữ lại các đơn của khách hàng 42. `ROWS_EXAMINED` tăng cao là dấu hiệu cần xem lại access path, index và độ chọn lọc.

Rows examined không đồng nghĩa với số page vật lý đọc từ đĩa. Một hàng có thể được tìm thấy trong buffer pool; một index range scan cũng có thể đi qua nhiều index entry. Để hiểu I/O, cần kết hợp thêm buffer pool, file I/O và thiết bị lưu trữ.

### Rows sent

`ROWS_SENT` là số hàng server gửi về client. Nó giúp phát hiện truy vấn trả quá nhiều hàng, đặc biệt khi endpoint chỉ cần một trang nhỏ hoặc một vài trường.

Ví dụ, một truy vấn trả 100.000 hàng có thể tạo chi phí truyền mạng, giải mã và cấp phát object lớn ngay cả khi MySQL đọc dữ liệu hiệu quả. Hãy xem số cột, kích thước mỗi hàng, pagination và việc ứng dụng có thực sự tiêu thụ toàn bộ kết quả không.

Rows sent không đo số byte. Hai truy vấn cùng gửi 1.000 hàng nhưng một truy vấn chỉ có hai cột số, truy vấn kia có nhiều cột `TEXT`/JSON lớn, có thể tạo payload và thời gian truyền rất khác nhau. Cần đo thêm response bytes hoặc network throughput khi nghi ngờ nút thắt nằm ở truyền dữ liệu.

### Tỷ lệ examined/sent

Có thể dùng tỷ lệ sau như một tín hiệu chẩn đoán:

\[
\text{examined per sent} = \frac{\text{rows examined}}{\text{rows sent}}
\]

Nếu truy vấn examined 500.000 hàng nhưng chỉ sent 20 hàng, hãy kiểm tra vì sao phạm vi đọc lớn hơn kết quả nhiều. Tuy nhiên, không có ngưỡng chung áp dụng cho mọi query:

- Truy vấn `COUNT(*)`, `SUM()` hoặc `GROUP BY` có thể sent rất ít hàng nhưng cần đọc nhiều hàng hợp lệ.
- `UPDATE`/`DELETE` thường sent 0 hàng, nên tỷ lệ không xác định; hãy xem rows examined cùng rows affected.
- Truy vấn tìm kiếm có thể cần quét nhiều candidate để bảo đảm kết quả chính xác.
- Một full scan trên bảng nhỏ có thể rẻ hơn index lookup và không nhất thiết cần sửa.

Đừng tối ưu chỉ để làm tỷ lệ thấp. Hãy xác nhận truy vấn có đang làm công việc không cần thiết so với yêu cầu nghiệp vụ hay không.

## 4. Execution frequency và query digest

Ứng dụng có thể gửi cùng một mẫu SQL với các giá trị tham số khác nhau:

```sql
SELECT order_id, status
FROM orders
WHERE customer_id = 42;

SELECT order_id, status
FROM orders
WHERE customer_id = 91;
```

Performance Schema chuẩn hóa literal thành digest để gom các lần chạy cùng cấu trúc thành một nhóm. Hai câu trên thường được tổng hợp thành cùng một query digest. `COUNT_STAR` cho biết số lần statement trong nhóm đã được thực thi kể từ khi thống kê được khởi tạo hoặc reset.

Việc gom nhóm làm mất khác biệt giữa các giá trị tham số. Nếu `customer_id = 42` có hàng triệu đơn còn `customer_id = 91` chỉ có vài đơn, hai lần chạy có thể có latency và rows examined rất khác nhau nhưng vẫn nằm trong cùng digest. Khi thấy `MAX_TIMER_WAIT` cao hoặc phân phối không ổn định, cần liên kết với log/trace ứng dụng để tìm tham số và tenant gây lệch.

Frequency rất quan trọng vì:

- Một truy vấn 1 ms chạy 100.000 lần có thể tiêu tốn nhiều CPU và round trip.
- N+1 tạo ra số lần thực thi lớn của một digest với tham số khóa thay đổi.
- Polling quá thường xuyên có thể làm tăng tải dù mỗi lần truy vấn nhẹ.
- Một query digest có thể chạy trên nhiều endpoint hoặc tenant; cần trace ứng dụng để xác định nguồn.

### Tổng thời gian và số lần chạy

Với mỗi digest, xem đồng thời:

- `COUNT_STAR`: tần suất thực thi.
- `SUM_TIMER_WAIT`: tổng thời gian tích lũy.
- `AVG_TIMER_WAIT`: thời gian trung bình.
- `MAX_TIMER_WAIT`: lần chạy lớn nhất.
- `SUM_ROWS_EXAMINED` và `SUM_ROWS_SENT`: tổng số hàng được xem xét và trả về.
- `SUM_ROWS_AFFECTED`: tổng số hàng bị thay đổi bởi các statement ghi; hữu ích với UPDATE/DELETE vì `ROWS_SENT` thường bằng 0.

Một digest có count cao nhưng average thấp vẫn có thể là ứng viên tối ưu tốt vì tần suất lặp lớn. Một digest count thấp nhưng max rất cao có thể cần điều tra dữ liệu lệch, khóa chờ hoặc kế hoạch thực thi thay đổi theo tham số.

## 5. Query digest trong Performance Schema

MySQL lưu thống kê theo digest trong `performance_schema.events_statements_summary_by_digest`. Bảng này tổng hợp số liệu statement từ khi server khởi động hoặc từ lần reset thống kê tương ứng.

Ví dụ tìm 20 digest có tổng latency lớn nhất trong schema hiện tại:

```sql
SELECT SCHEMA_NAME,
       DIGEST_TEXT,
       COUNT_STAR AS exec_count,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_latency_s,
       ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_latency_s,
       ROUND(MAX_TIMER_WAIT / 1000000000000, 6) AS max_latency_s,
       SUM_ROWS_EXAMINED AS rows_examined,
       SUM_ROWS_SENT AS rows_sent,
       SUM_ROWS_AFFECTED AS rows_affected,
       ROUND(SUM_ROWS_EXAMINED / NULLIF(COUNT_STAR, 0), 1)
           AS avg_rows_examined
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Các timer của Performance Schema được biểu diễn bằng picosecond. Chia `SUM_TIMER_WAIT` cho (10^{12}) để đổi sang giây; chia `AVG_TIMER_WAIT` hoặc `MAX_TIMER_WAIT` tương tự. Không đọc trực tiếp các giá trị timer như millisecond.

Tìm digest có tần suất cao nhất:

```sql
SELECT DIGEST_TEXT,
       COUNT_STAR AS exec_count,
       ROUND(AVG_TIMER_WAIT / 1000000000, 3) AS avg_latency_ms,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_latency_s,
       SUM_ROWS_EXAMINED,
       SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY COUNT_STAR DESC
LIMIT 20;
```

Tìm digest examined nhiều hàng nhưng sent ít hàng:

```sql
SELECT DIGEST_TEXT,
       COUNT_STAR,
       SUM_ROWS_EXAMINED,
       SUM_ROWS_SENT,
       ROUND(SUM_ROWS_EXAMINED / NULLIF(SUM_ROWS_SENT, 0), 1)
           AS examined_per_sent
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
  AND SUM_ROWS_SENT > 0
ORDER BY examined_per_sent DESC
LIMIT 20;
```

Truy vấn thứ ba chỉ tạo shortlist để điều tra. Cần loại các truy vấn aggregate hợp lệ, xác minh bảng nhỏ/full scan có chủ đích và xem `EXPLAIN` trước khi thêm index.

### Những cột hữu ích khác

Tùy phiên bản, bảng digest còn cung cấp các thống kê như:

- `SUM_CREATED_TMP_TABLES`, `SUM_CREATED_TMP_DISK_TABLES`: số internal temporary table được ghi nhận.
- `SUM_SORT_ROWS`, `SUM_SORT_MERGE_PASSES`: hoạt động sort.
- `SUM_NO_INDEX_USED`, `SUM_NO_GOOD_INDEX_USED`: số lần không dùng index hoặc không tìm được index phù hợp theo bộ đếm.
- `SUM_ERRORS`, `SUM_WARNINGS`: lỗi và cảnh báo của statement.
- `FIRST_SEEN`, `LAST_SEEN`: thời điểm digest lần đầu và gần nhất được ghi nhận.

Các bộ đếm là tổng tích lũy. Hãy so sánh delta giữa hai thời điểm để tính tốc độ phát sinh, đặc biệt khi instance có uptime dài.

## 6. Dùng sys.statement_analysis để đọc workload nhanh

MySQL cài kèm schema `sys` trên nhiều bản phân phối. View `sys.statement_analysis` trình bày các digest theo cách dễ đọc hơn, gồm số lần thực thi, tổng/average/max latency, rows sent, rows examined, temporary tables và thông tin scan.

```sql
SELECT query,
       exec_count,
       total_latency,
       avg_latency,
       max_latency,
       rows_sent,
       rows_examined,
       rows_examined_avg,
       tmp_tables,
       tmp_disk_tables,
       full_scan
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 20;
```

Có thể sắp xếp theo `exec_count` để tìm mẫu truy vấn chạy thường xuyên hoặc theo `rows_examined` để tìm mẫu đọc nhiều dữ liệu. `sys.statement_analysis` là view tiện ích dựa trên Performance Schema; nếu view không tồn tại hoặc không trả kết quả, kiểm tra schema `sys`, quyền truy cập và các instrument/consumer tương ứng.

## 7. Xem các lần thực thi gần đây

Digest summary cho biết tổng hợp, nhưng đôi khi cần xem một lần chạy cụ thể để phát hiện tham số gây chậm hoặc thời điểm bị lock wait. Nếu statement history được bật và còn dữ liệu trong ring buffer, có thể đọc:

```sql
SELECT THREAD_ID,
       EVENT_ID,
       ROUND(TIMER_WAIT / 1000000000000, 6) AS latency_s,
       ROWS_EXAMINED,
       ROWS_SENT,
       MYSQL_ERRNO,
       SQL_TEXT
FROM performance_schema.events_statements_history_long
WHERE SQL_TEXT IS NOT NULL
ORDER BY TIMER_WAIT DESC
LIMIT 30;
```

`events_statements_history_long` chỉ giữ một số lượng event giới hạn; dữ liệu cũ bị ghi đè. Nó không phải kho lưu trữ lịch sử lâu dài. Nếu consumer hoặc instrument chưa bật, bảng có thể rỗng hoặc thiếu sự kiện.

Kiểm tra cấu hình thu thập:

```sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
WHERE NAME IN (
    'events_statements_current',
    'events_statements_history',
    'events_statements_history_long'
);

SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/%';
```

Việc bật thêm instrument/consumer có thể tạo overhead và tăng bộ nhớ history. Thay đổi cấu hình quan sát cần có chủ đích, thử trên staging và cân bằng độ chi tiết với chi phí.

## 8. Slow query log: tìm các lần chạy chậm

Slow query log ghi những statement vượt điều kiện cấu hình. Đây là nguồn tốt để tìm truy vấn chậm riêng lẻ và lấy SQL mẫu, nhưng không thay thế digest summary vì các truy vấn nhanh nhưng lặp nhiều có thể không lọt ngưỡng.

Kiểm tra:

```sql
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'min_examined_row_limit';
SHOW VARIABLES LIKE 'log_output';
```

Ví dụ cấu hình thử nghiệm:

```sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 0.2;
SET GLOBAL min_examined_row_limit = 100;
```

Thay đổi GLOBAL thường áp dụng cho connection mới; nếu cần thử ngay trong session hiện tại, kiểm tra và đặt biến SESSION khi biến đó hỗ trợ phạm vi SESSION. Cần quyền quản trị phù hợp. Ghi log quá chi tiết có thể tạo thêm I/O và chiếm dung lượng; đặt ngưỡng, thời gian bật và chính sách rotate/retention rõ ràng.

Không bật `log_queries_not_using_indexes` một cách rộng rãi mà không đánh giá workload: nhiều truy vấn hợp lệ trên bảng nhỏ vẫn có thể không dùng index và log sẽ tăng nhanh. Slow log cũng có thể chứa literal nhạy cảm; hạn chế quyền đọc và bảo vệ file log.

## 9. Đọc EXPLAIN để giải thích rows examined

Sau khi tìm được digest đáng chú ý, lấy một câu SQL đại diện và kiểm tra kế hoạch:

```sql
EXPLAIN FORMAT=TREE
SELECT order_id, status
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-11-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Xem các yếu tố:

- Access method: `const`, `ref`, `range`, `index` hay `ALL`.
- Index được chọn và phần key được sử dụng.
- Số hàng ước lượng và điều kiện lọc còn lại.
- Join order, sort, temporary table và materialization.
- Điều kiện nào được áp dụng sớm và điều kiện nào phải lọc sau khi đọc hàng.

`EXPLAIN ANALYZE` thực thi SELECT và cho số hàng/thời gian thực tế theo từng iterator:

```sql
EXPLAIN ANALYZE
SELECT order_id, status
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-11-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Chỉ chạy khi có thể chấp nhận việc thực thi truy vấn và tải phát sinh. So sánh estimated rows với actual rows để phát hiện thống kê sai hoặc phân phối dữ liệu lệch. `EXPLAIN ANALYZE` không thay thế đo latency end-to-end trong ứng dụng.

## 10. Ví dụ: cùng một endpoint, bốn kiểu vấn đề

Giả sử endpoint hiển thị 50 đơn gần nhất của một khách hàng. Bảng có index:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    KEY ix_orders_customer_created
        (customer_id, created_at, order_id)
) ENGINE = InnoDB;
```

Truy vấn:

```sql
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Các tình huống quan sát:

| Số liệu | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Latency cao, rows examined cao | Đọc quá nhiều dữ liệu hoặc plan kém | Kiểm tra index, selectivity, partition pruning và thống kê |
| Latency thấp, frequency rất cao | Query lặp hoặc N+1 | Batch loading, cache theo request, giảm polling |
| Rows examined cao, rows sent thấp | Lọc nhiều hàng để lấy ít kết quả | Kiểm tra predicate, index ghép và khả năng lọc sớm |
| Rows sent cao, examined gần bằng sent | Có thể trả quá nhiều dữ liệu | Pagination, chọn ít cột, giới hạn payload |
| Server latency thấp, application latency cao | Chờ pool, mạng hoặc mapping | Đo pool wait, network, bytes và thời gian xử lý client |

Index ghép `(customer_id, created_at, order_id)` phù hợp với điều kiện bằng trên `customer_id` và thứ tự theo ngày/mã đơn. Tuy nhiên, phải xác minh bằng `EXPLAIN` và dữ liệu thực tế; index có thể không được chọn nếu bảng rất nhỏ hoặc optimizer đánh giá scan rẻ hơn.

## 11. Xếp ưu tiên tối ưu

Không nên chỉ chọn query có `MAX_TIMER_WAIT` cao nhất. Hãy xếp hạng theo nhiều chiều:

1. **Tổng latency:** digest tiêu tốn tổng thời gian lớn trong khoảng đo.
2. **Tần suất:** digest chạy quá nhiều, đặc biệt trên endpoint nóng hoặc trong vòng lặp.
3. **Average và tail latency:** tìm mẫu có trải nghiệm kém hoặc có outlier lớn.
4. **Rows examined:** tìm lượng đọc/lọc lớn so với công việc cần làm.
5. **Rows sent và payload:** tìm truy vấn trả thừa dữ liệu hoặc quá nhiều cột.
6. **Errors, warnings, temporary tables và full scan:** tìm dấu hiệu phụ trợ cho vấn đề.
7. **Mức độ quan trọng nghiệp vụ:** ưu tiên luồng thanh toán, đăng nhập, đặt hàng hoặc tác vụ có SLO nghiêm ngặt.

Một cách thực dụng là lập bảng shortlist:

| Digest | Exec count | Avg latency | Total latency | Avg examined | Avg sent | Ưu tiên |
|---|---:|---:|---:|---:|---:|---|
| A | Rất cao | Thấp | Rất cao | Trung bình | Thấp | Giảm số lần gọi |
| B | Thấp | Rất cao | Trung bình | Cao | Thấp | Điều tra plan và lock wait |
| C | Cao | Trung bình | Cao | Cao | Cao | Giảm phạm vi đọc và payload |

Sau mỗi thay đổi, đo lại cùng khoảng thời gian và workload tương đương. Không so sánh một giờ cao điểm trước tối ưu với một giờ thấp điểm sau tối ưu rồi kết luận hiệu quả.

## 12. Những sai lầm khi đọc metrics

| Sai lầm | Vì sao sai | Cách đọc đúng |
|---|---|---|
| Chỉ nhìn average latency | Che khuất tail latency | Theo dõi p95/p99 ở ứng dụng/APM |
| Chọn query chậm nhất để tối ưu trước | Có thể chỉ chạy một lần | Xem total latency và frequency |
| Rows examined = disk reads | Nhiều hàng có thể ở buffer pool; counter không đếm page I/O | Đối chiếu file I/O và buffer pool metrics |
| Rows sent = network bytes | Kích thước hàng khác nhau | Đo payload bytes/network throughput |
| Examined/sent càng thấp càng tốt trong mọi trường hợp | Aggregate hợp lệ có thể đọc nhiều hàng và trả một hàng | Xem loại truy vấn và yêu cầu nghiệp vụ |
| Digest summary là lịch sử đầy đủ | Bảng tổng hợp và history có giới hạn/reset | Export định kỳ hoặc dùng monitoring lưu dài hạn |
| Một digest tương ứng một endpoint | Cùng SQL có thể được gọi từ nhiều nơi | Correlate trace ID, service và endpoint ở ứng dụng |
| Full scan luôn là lỗi | Scan bảng nhỏ có thể rẻ hơn index | Đọc plan, kích thước bảng và số hàng thực tế |

## 13. Quy trình quan sát một workload

1. Chọn khoảng đo đại diện, ghi lại thời điểm, lượng request và trạng thái tải.
2. Lấy snapshot digest từ `events_statements_summary_by_digest`; lưu count, latency, rows và timestamp.
3. Sau khoảng đo, lấy snapshot thứ hai và tính delta cho từng digest.
4. Xếp hạng theo total latency, count, average/max latency và rows examined.
5. Đối chiếu p95/p99 và latency end-to-end từ ứng dụng.
6. Chọn digest đại diện, kiểm tra SQL, `EXPLAIN` và khi phù hợp `EXPLAIN ANALYZE`.
7. Xác định nguyên nhân: index, join, N+1, payload, sort, lock wait, I/O hay pool/network.
8. Thay đổi một yếu tố mỗi lần và chạy lại workload tương đương.
9. So sánh cả latency, frequency, rows examined, rows sent, bytes và error rate.
10. Thiết lập dashboard/cảnh báo và lưu baseline để nhận ra regression.

Khi lấy delta từ counter tích lũy, xử lý trường hợp server restart hoặc Performance Schema bị reset giữa hai mẫu. Nếu counter giảm, không lấy phép trừ âm làm tốc độ; hãy bắt đầu một cửa sổ đo mới.

Tần suất trong cửa sổ có thể ước lượng bằng `(COUNT_STAR_mới - COUNT_STAR_cũ) / số_giây_đo`. Tương tự, chia delta của `SUM_TIMER_WAIT` cho (10^{12}) để có tổng giây trong cửa sổ. Luôn lưu timestamp của hai snapshot để phép tính không phụ thuộc khoảng lấy mẫu dự kiến.

## 14. Bài thực hành

Trên MySQL instance thử nghiệm có bảng `orders` ở phần 10:

1. Chạy một truy vấn tra cứu theo `customer_id` và quan sát `COUNT_STAR`, `SUM_TIMER_WAIT`, `SUM_ROWS_EXAMINED`, `SUM_ROWS_SENT` trong digest summary.
2. Tạo workload lặp lại cùng một mẫu SQL với nhiều giá trị `customer_id`. Xác nhận các câu có literal khác nhau được gom vào digest tương ứng.
3. Tạo truy vấn lọc thiếu index trên bảng đủ lớn, so sánh rows examined trước và sau khi thêm index ghép phù hợp.
4. Chạy truy vấn trả toàn bộ hàng rồi giới hạn bằng pagination. So sánh rows sent và payload phía ứng dụng.
5. Chạy một truy vấn tổng hợp `COUNT(*)` hoặc `SUM()` và giải thích vì sao rows sent nhỏ không có nghĩa rows examined cũng nhỏ.
6. Bật slow query log với ngưỡng thử nghiệm, đối chiếu các lần chạy chậm với digest summary.
7. Dùng `sys.statement_analysis` để tìm digest có total latency cao và digest có execution count cao.
8. Dùng `events_statements_history_long` để xem các lần chạy gần đây nếu consumer được bật.
9. Đo p95/p99 ở tầng ứng dụng và so sánh với average/max trong Performance Schema. Giải thích vì sao hai nguồn không thay thế nhau.
10. Viết báo cáo ngắn chọn ba digest cần tối ưu, nêu bằng chứng từ latency, frequency, rows examined và rows sent.

## Ghi nhớ

- Latency đo thời gian; rows examined phản ánh lượng hàng được xem xét; rows sent phản ánh lượng hàng trả về; execution frequency cho biết mức độ lặp.
- Tổng latency giúp tìm chi phí tích lũy, còn p95/p99 giúp nhìn tail latency; digest summary không tự cung cấp percentile đầy đủ.
- Performance Schema `events_statements_summary_by_digest` là điểm bắt đầu tốt để xếp hạng workload theo mẫu SQL.
- Rows examined không phải số lần đọc đĩa; rows sent không phải số byte truyền mạng.
- Một truy vấn nhanh nhưng chạy rất thường xuyên có thể đáng tối ưu hơn truy vấn chậm hiếm gặp.
- Dùng slow query log để tìm lần chạy chậm, `EXPLAIN` để hiểu access path và trace ứng dụng để tìm endpoint gây tải.
- Đo trước/sau trong điều kiện tương đương và kết hợp nhiều chỉ số trước khi kết luận tối ưu thành công.
