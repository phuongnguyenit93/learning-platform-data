# Công cụ theo hệ quản trị: pg_stat_statements, Performance Schema và Query Store

Trong chương **Quan sát hệ thống** của module **DATABASE_PERFORMANCE**, nội dung tập trung vào cách dùng số liệu tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu để cải thiện hiệu năng cơ sở dữ liệu. Một hệ thống có thể phục vụ hàng nghìn câu lệnh khác nhau trong cùng một khoảng thời gian. Khi độ trễ tăng hoặc thông lượng giảm, việc xem một truy vấn đang chạy thường chưa đủ để tìm ra nguyên nhân. Cần có công cụ thu thập lịch sử và thống kê theo nhóm câu lệnh, đo thời gian CPU và thời gian chờ, theo dõi kế hoạch thực thi, rồi đối chiếu với tải của máy chủ.

Ba công cụ phổ biến là `pg_stat_statements` của PostgreSQL, Performance Schema của MySQL và Query Store của SQL Server. Chúng đều giúp trả lời những câu hỏi như câu lệnh nào được gọi nhiều, câu lệnh nào tiêu thụ nhiều thời gian, có bao nhiêu dòng được đọc và kế hoạch thực thi thay đổi ra sao. Tuy nhiên, phạm vi dữ liệu, cách tổng hợp và khả năng lưu lịch sử của từng công cụ khác nhau. Người vận hành cần hiểu đúng các giới hạn đó trước khi dùng số liệu để ra quyết định tối ưu.

## 1. Vai trò của công cụ quan sát hiệu năng

Một công cụ quan sát hiệu năng tốt cần giúp nhóm vận hành nối được ba lớp thông tin:

1. **Câu lệnh và workload:** câu SQL nào được thực thi, tần suất gọi, tham số hoặc mẫu câu lệnh, số dòng đọc và số dòng trả về.
2. **Chi phí thực thi:** thời gian thực thi, CPU, I/O, dữ liệu tạm, số lần đọc, số lần ghi và các loại wait event.
3. **Kế hoạch và bối cảnh:** kế hoạch thực thi được chọn, sự thay đổi kế hoạch theo thời gian, khoảng tải, phiên bản, cấu hình và trạng thái tài nguyên máy chủ.

Các công cụ nêu trong bài chủ yếu cung cấp thống kê ở cấp câu lệnh hoặc kế hoạch. Chúng không tự giải thích toàn bộ nguyên nhân. Ví dụ, một truy vấn có tổng thời gian cao có thể do được gọi rất nhiều lần, mỗi lần chạy chậm, hoặc cả hai. Một truy vấn có thời gian trung bình thấp vẫn có thể có một số lần chạy rất chậm. Vì vậy, hãy đọc `calls` hoặc số lần thực thi cùng với tổng thời gian, thời gian trung bình, phân vị từ nguồn đo phù hợp và các chỉ số tài nguyên.

| Nhu cầu | PostgreSQL | MySQL | SQL Server |
|---|---|---|---|
| Tổng hợp theo mẫu câu lệnh | `pg_stat_statements` | `events_statements_summary_by_digest` trong Performance Schema | Query Store runtime statistics |
| Quan sát sự kiện đang diễn ra | `pg_stat_activity` và các view thống kê liên quan | `events_statements_current`, `events_waits_current` | DMV và các công cụ giám sát phiên; Query Store lưu thống kê theo khoảng |
| Phân tích kế hoạch | `EXPLAIN` và `EXPLAIN ANALYZE` | `EXPLAIN`, `EXPLAIN ANALYZE` ở phiên bản hỗ trợ | Kế hoạch được lưu trong Query Store và execution plan cache |
| Lịch sử kế hoạch và hiệu năng | Cần kết hợp snapshot hoặc hệ thống giám sát ngoài | Cần kết hợp snapshot hoặc hệ thống giám sát ngoài | Query Store lưu lịch sử truy vấn, kế hoạch và thống kê runtime |

Không nên so sánh trực tiếp các cột cùng tên giữa các hệ quản trị nếu chưa kiểm tra đơn vị và định nghĩa. Một công cụ có thể đo microsecond, công cụ khác lưu timer theo picosecond; có công cụ lưu tổng thời gian, có công cụ lưu trung bình theo khoảng thống kê.

## 2. PostgreSQL: pg_stat_statements

`pg_stat_statements` là extension thống kê hoạt động thực thi câu lệnh SQL. Extension nhóm các câu lệnh có cấu trúc tương tự thành một mục thống kê, nhờ đó có thể tìm ra mẫu truy vấn tiêu thụ nhiều thời gian dù giá trị tham số thay đổi giữa các lần gọi.

### 2.1. Điều kiện sử dụng

Để thu thập thống kê, thư viện phải được nạp khi PostgreSQL khởi động. Trong `postgresql.conf`, cấu hình thường có dạng:

```conf
shared_preload_libraries = 'pg_stat_statements'
pg_stat_statements.max = 10000
pg_stat_statements.track = all
```

Nếu máy chủ đã có các thư viện khác trong `shared_preload_libraries`, hãy giữ nguyên danh sách và thêm `pg_stat_statements` vào đó. Thay đổi `shared_preload_libraries` cần khởi động lại PostgreSQL. Sau khi máy chủ khởi động với thư viện này, tạo extension trong database cần truy vấn view:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Việc tạo extension yêu cầu quyền phù hợp. Thống kê được thu thập ở cấp instance; view có thể hiển thị các mục thuộc những database khác nhau thông qua `dbid`, nhưng extension cần có trong database mà người dùng kết nối để truy vấn view. Hãy kiểm tra đúng phiên bản PostgreSQL và chính sách quyền trước khi triển khai.

Một số cấu hình đáng quan tâm:

- `pg_stat_statements.track` xác định loại câu lệnh được theo dõi, thường là `top`, `all` hoặc `none`. Theo dõi mọi câu lệnh lồng nhau có thể tăng chi phí quan sát.
- `pg_stat_statements.max` giới hạn số mục thống kê được giữ. Khi có quá nhiều mẫu khác nhau, một số mục có thể bị loại bỏ; kiểm tra cột `dealloc` để nhận biết tình trạng này.
- `pg_stat_statements.track_planning` bật thu thập số liệu lập kế hoạch trên các phiên bản hỗ trợ. Việc theo dõi planning có thể tạo thêm overhead, vì vậy chỉ bật khi cần phân tích.
- `pg_stat_statements.track_utility` quyết định có theo dõi các lệnh tiện ích hay không.
- `track_io_timing` của PostgreSQL có thể bổ sung thời gian I/O cho các bộ đếm liên quan. Cần cân nhắc chi phí đo thời gian trên môi trường có tải cao.

### 2.2. Tìm các mẫu truy vấn tiêu thụ nhiều thời gian

Ví dụ sau xếp hạng các mẫu câu lệnh theo tổng thời gian thực thi:

```sql
SELECT queryid,
       calls,
       ROUND(total_exec_time::numeric, 2) AS total_exec_ms,
       ROUND(mean_exec_time::numeric, 2) AS mean_exec_ms,
       rows,
       shared_blks_hit,
       shared_blks_read,
       temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Các cột chính:

- `queryid` nhận diện mẫu câu lệnh trong phạm vi thống kê của PostgreSQL. Không nên xem giá trị này là định danh bất biến qua mọi phiên bản hoặc mọi thay đổi môi trường.
- `calls` là số lần thực thi được ghi nhận.
- `total_exec_time` là tổng thời gian thực thi tích lũy; `mean_exec_time` là trung bình mỗi lần thực thi. Các trường thời gian được biểu diễn bằng millisecond trong các phiên bản hiện đại.
- `rows` là tổng số dòng được trả về hoặc bị tác động theo cách thống kê của câu lệnh.
- `shared_blks_hit` và `shared_blks_read` cho biết số block được tìm thấy trong shared buffers và số block được đọc vào shared buffers. `shared_blks_read` không nhất thiết là số lần đọc vật lý từ thiết bị, vì dữ liệu có thể được phục vụ từ cache của hệ điều hành.
- `temp_blks_written` giúp phát hiện câu lệnh tạo nhiều dữ liệu tạm, thường liên quan tới sort, hash hoặc thao tác trung gian lớn.

Trường thời gian có tên `total_exec_time` trên các phiên bản mới; phiên bản cũ có thể dùng tên trường khác. Hãy kiểm tra schema thực tế trước khi sao chép truy vấn giám sát giữa các phiên bản.

Để tìm mẫu truy vấn có thời gian trung bình cao, có thể lọc những mẫu đã chạy đủ số lần để kết quả ít bị chi phối bởi một lần thực thi bất thường:

```sql
SELECT queryid,
       calls,
       ROUND(mean_exec_time::numeric, 2) AS mean_exec_ms,
       ROUND(max_exec_time::numeric, 2) AS max_exec_ms,
       rows
FROM pg_stat_statements
WHERE calls >= 20
ORDER BY mean_exec_time DESC
LIMIT 20;
```

`max_exec_time` có trên các phiên bản hỗ trợ tương ứng. Nếu phiên bản hoặc cấu hình không cung cấp trường này, hãy bỏ cột đó hoặc dùng công cụ đo từng lần thực thi. `pg_stat_statements` cung cấp các số tổng hợp và cực trị, nhưng không trực tiếp tạo biểu đồ p95/p99 cho từng mẫu câu lệnh.

### 2.3. Đọc kết quả và liên hệ với execution plan

Không nên chỉ nhìn vào `total_exec_time`. Hãy đặt các câu hỏi:

- Mẫu truy vấn có `calls` rất cao hay mỗi lần gọi thực sự chậm?
- Số dòng đọc và số block đọc có lớn so với số dòng trả về không?
- `temp_blks_written` có tăng mạnh, gợi ý sort hoặc hash phải dùng vùng tạm không?
- Có sự khác biệt lớn giữa các mẫu tham số hoặc các nhóm người dùng không?
- Kế hoạch thực thi thực tế có ước lượng sai số dòng, lặp quá nhiều hoặc quét dữ liệu không cần thiết không?

Sau khi chọn được mẫu truy vấn đáng điều tra, lấy câu SQL đại diện và phân tích kế hoạch bằng `EXPLAIN`. Khi cần số liệu runtime, có thể dùng `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường phù hợp. Lệnh `EXPLAIN ANALYZE` thực thi câu lệnh; phải kiểm soát tác động nếu câu lệnh có thao tác ghi dữ liệu.

Thống kê có thể được đặt lại bằng hàm quản trị `pg_stat_statements_reset()`. Không nên reset tùy tiện trên production vì sẽ xóa đường cơ sở đang được dashboard hoặc nhóm khác sử dụng. Nếu cần đo một khoảng riêng, hãy lưu snapshot trước và sau rồi tính chênh lệch, đồng thời ghi lại thời điểm reset và thời gian quan sát.

## 3. MySQL: Performance Schema

Performance Schema là cơ chế thu thập số liệu nội bộ của MySQL về statement, wait, stage, transaction, mutex và nhiều hoạt động khác. Dữ liệu được lưu trong các bảng ảo thuộc schema `performance_schema`; phần lớn là thống kê trong bộ nhớ và có thể mất khi máy chủ khởi động lại. Schema `sys` cung cấp các view dễ đọc hơn dựa trên Performance Schema.

### 3.1. Kiểm tra cấu hình thu thập

Trước khi phân tích, kiểm tra Performance Schema có được bật hay không:

```sql
SHOW VARIABLES LIKE 'performance_schema';
```

Kiểm tra các consumer và instrument liên quan:

```sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
WHERE NAME LIKE '%statements%'
   OR NAME LIKE '%waits%';

SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/%'
   OR NAME LIKE 'wait/%'
LIMIT 30;
```

Consumer quyết định loại sự kiện nào được lưu vào các bảng current, history hoặc summary; instrument quyết định loại hoạt động nào được đo và có bấm giờ hay không. Không phải mọi consumer và instrument đều luôn được bật trong mọi bản cài đặt. Hãy chỉ bật những nhóm cần thiết và theo dõi overhead, dung lượng bộ nhớ cũng như tác động lên máy chủ.

Ví dụ, nếu cần lưu lịch sử statement dài hơn cho mục đích điều tra ngắn hạn, có thể bật consumer tương ứng sau khi đánh giá tác động và quyền quản trị:

```sql
UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME IN ('events_statements_current',
               'events_statements_history',
               'events_statements_history_long');
```

Đây là cấu hình runtime của Performance Schema; việc bật consumer không đồng nghĩa lịch sử sẽ được lưu bền vững qua lần restart. Kích thước history có giới hạn, vì vậy sự kiện cũ có thể bị ghi đè khi tải tăng.

### 3.2. Tổng hợp theo digest

`events_statements_summary_by_digest` nhóm câu lệnh theo digest, tức mẫu SQL đã chuẩn hóa để gom những câu lệnh có cấu trúc tương tự. Đây là điểm bắt đầu hữu ích để tìm các mẫu câu lệnh tiêu thụ nhiều thời gian:

```sql
SELECT DIGEST,
       DIGEST_TEXT,
       COUNT_STAR AS executions,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
       ROUND(AVG_TIMER_WAIT / 1000000000000, 3) AS avg_seconds,
       SUM_ROWS_EXAMINED,
       SUM_ROWS_SENT,
       SUM_CREATED_TMP_DISK_TABLES,
       SUM_SORT_ROWS,
       SUM_NO_INDEX_USED
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Các timer trong Performance Schema được biểu diễn theo picosecond; chia cho một nghìn tỷ để chuyển sang giây. Các cột đáng chú ý gồm:

- `COUNT_STAR`: số lần sự kiện được ghi nhận.
- `SUM_TIMER_WAIT` và `AVG_TIMER_WAIT`: tổng và trung bình thời gian chờ/thực thi được đo cho nhóm statement.
- `SUM_ROWS_EXAMINED`: tổng số dòng được kiểm tra trong quá trình thực thi.
- `SUM_ROWS_SENT`: tổng số dòng trả về client.
- `SUM_CREATED_TMP_DISK_TABLES`: số bảng tạm trên đĩa được tạo.
- `SUM_SORT_ROWS`: số dòng tham gia thao tác sort.
- `SUM_NO_INDEX_USED`: số lần thực thi không dùng chỉ mục theo tiêu chí thống kê của MySQL.

Một digest có nhiều dòng examined nhưng ít dòng sent có thể đang đọc và lọc lượng dữ liệu lớn. Số bảng tạm trên đĩa hoặc số dòng sort cao có thể gợi ý thao tác trung gian tốn kém. Tuy nhiên, các bộ đếm này cần được xem cùng loại statement, kích thước dữ liệu, kế hoạch thực thi và tần suất gọi. Không dùng riêng `SUM_NO_INDEX_USED` để kết luận một truy vấn chắc chắn cần thêm chỉ mục; một số truy vấn quét toàn bảng vẫn là lựa chọn đúng khi cần đọc phần lớn bảng.

Digest có thể bị giới hạn bởi cấu hình độ dài văn bản chuẩn hóa; nhiều mẫu khác nhau cũng có thể không được giữ đầy đủ nếu giới hạn tài nguyên thống kê đạt tới. Khi `DIGEST` là `NULL`, thường cần kiểm tra các mục không được phân loại vào digest và trạng thái thu thập tương ứng.

### 3.3. Xem lịch sử và wait event

Các bảng `events_statements_current`, `events_statements_history` và `events_statements_history_long` cung cấp thông tin ở các phạm vi thời gian khác nhau. Bảng current thể hiện sự kiện đang diễn ra; history giữ một số sự kiện gần nhất theo thread; history_long giữ lịch sử toàn cục trong giới hạn bộ nhớ cấu hình. Ví dụ:

```sql
SELECT THREAD_ID,
       EVENT_ID,
       SQL_TEXT,
       TIMER_WAIT / 1000000000000 AS elapsed_seconds,
       ROWS_EXAMINED,
       ROWS_SENT,
       MYSQL_ERRNO
FROM performance_schema.events_statements_history_long
WHERE SQL_TEXT IS NOT NULL
ORDER BY TIMER_WAIT DESC
LIMIT 20;
```

Để tìm các loại wait tích lũy, có thể xem bảng tổng hợp theo tên sự kiện:

```sql
SELECT EVENT_NAME,
       COUNT_STAR,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_wait_seconds
FROM performance_schema.events_waits_summary_global_by_event_name
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Wait event cho biết nhóm hoạt động hoặc tài nguyên đang tiêu tốn thời gian chờ. Hãy đọc tên sự kiện cùng cấp độ đo, instance và thread liên quan; số liệu tổng hợp toàn cục không tự chỉ ra câu SQL gây ra chờ. Có thể dùng các bảng theo thread hoặc instance để thu hẹp phạm vi.

Nếu MySQL có schema `sys`, view `sys.statement_analysis` cung cấp bản tổng hợp dễ đọc cho nhiều chỉ số statement. View này hữu ích khi điều tra nhanh, nhưng người vận hành vẫn nên biết nó được xây dựng từ những bảng Performance Schema nào và giới hạn dữ liệu gốc ra sao.

## 4. SQL Server: Query Store

Query Store ghi lại câu lệnh, kế hoạch thực thi và thống kê runtime theo các khoảng thời gian. Đây là lợi thế lớn khi điều tra hồi quy hiệu năng: có thể xác định một câu lệnh từng chạy tốt với kế hoạch cũ nhưng sau đó chuyển sang kế hoạch khác và chậm hơn. Query Store được giới thiệu từ SQL Server 2016; khả năng theo dõi wait statistics trong Query Store có từ SQL Server 2017. Các tính năng và tùy chọn cụ thể phụ thuộc phiên bản.

### 4.1. Bật và kiểm tra trạng thái

Query Store được cấu hình theo từng database. Có thể bật bằng:

```sql
ALTER DATABASE [YourDatabase]
SET QUERY_STORE = ON;
```

Kiểm tra trạng thái, dung lượng và chế độ thu thập:

```sql
SELECT actual_state_desc,
       desired_state_desc,
       readonly_reason,
       current_storage_size_mb,
       max_storage_size_mb,
       query_capture_mode_desc,
       wait_stats_capture_mode_desc
FROM sys.database_query_store_options;
```

Trong cấu hình vận hành, cần xem `actual_state_desc` có phải `READ_WRITE` hay không. Nếu Query Store chuyển sang `READ_ONLY`, kiểm tra `readonly_reason`, giới hạn dung lượng, chính sách cleanup và các điều kiện khiến việc ghi dữ liệu bị dừng. Cột `wait_stats_capture_mode_desc` có trên các phiên bản hỗ trợ thu thập wait statistics trong Query Store; với SQL Server 2016, hãy bỏ cột này khỏi truy vấn kiểm tra. Có thể cấu hình khoảng thống kê, chế độ capture, dung lượng tối đa và chính sách dọn dữ liệu phù hợp với yêu cầu lưu lịch sử.

Ví dụ cấu hình sau chỉ mang tính minh họa; hãy chọn giới hạn dung lượng, khoảng thời gian và chế độ capture theo workload thực tế:

```sql
ALTER DATABASE [YourDatabase]
SET QUERY_STORE
(
    OPERATION_MODE = READ_WRITE,
    QUERY_CAPTURE_MODE = AUTO,
    INTERVAL_LENGTH_MINUTES = 15,
    MAX_STORAGE_SIZE_MB = 1000,
    CLEANUP_POLICY = (STALE_QUERY_THRESHOLD_DAYS = 30)
);
```

Không nên đặt dung lượng quá nhỏ khiến dữ liệu lịch sử liên tục bị dọn, hoặc lưu mọi câu lệnh với cấu hình quá rộng nếu workload có số lượng truy vấn ad hoc rất lớn. Cần giám sát dung lượng Query Store như một tài nguyên vận hành.

### 4.2. Tìm truy vấn có tổng chi phí cao

Query Store lưu runtime statistics theo plan và khoảng thời gian. Truy vấn sau tính trung bình có trọng số theo số lần thực thi trong bảy ngày gần nhất, xếp hạng theo tổng thời gian thực thi ước tính:

```sql
SELECT TOP (20)
       q.query_id,
       qt.query_sql_text,
       SUM(rs.count_executions) AS executions,
       SUM(rs.avg_duration * rs.count_executions)
           / NULLIF(SUM(rs.count_executions), 0) / 1000.0
           AS weighted_avg_duration_ms,
       SUM(rs.avg_cpu_time * rs.count_executions)
           / NULLIF(SUM(rs.count_executions), 0) / 1000.0
           AS weighted_avg_cpu_ms,
       SUM(rs.avg_logical_io_reads * rs.count_executions)
           / NULLIF(SUM(rs.count_executions), 0)
           AS weighted_avg_logical_reads
FROM sys.query_store_query AS q
JOIN sys.query_store_query_text AS qt
  ON qt.query_text_id = q.query_text_id
JOIN sys.query_store_plan AS p
  ON p.query_id = q.query_id
JOIN sys.query_store_runtime_stats AS rs
  ON rs.plan_id = p.plan_id
JOIN sys.query_store_runtime_stats_interval AS rsi
  ON rsi.runtime_stats_interval_id = rs.runtime_stats_interval_id
WHERE rsi.start_time >= DATEADD(day, -7, SYSUTCDATETIME())
GROUP BY q.query_id, qt.query_sql_text
ORDER BY SUM(rs.avg_duration * rs.count_executions) DESC;
```

Trong Query Store, `avg_duration` và `avg_cpu_time` được lưu theo microsecond; chia cho 1.000 để chuyển sang millisecond. `avg_logical_io_reads` là số logical read trung bình mỗi lần thực thi. Phép tính có trọng số giúp tránh việc lấy trung bình đơn giản giữa các khoảng có số lần gọi rất khác nhau. Truy vấn mẫu tổng hợp các plan của cùng query; khi điều tra hồi quy, nên bổ sung `plan_id` và phân tích riêng từng kế hoạch để nhận ra plan nào tạo ra thay đổi.

Query Store runtime statistics là dữ liệu tổng hợp theo khoảng và theo plan. Không nên diễn giải `weighted_avg_duration_ms` là p95 hoặc p99. Muốn phân tích phân vị, cần nguồn telemetry ghi nhận từng lần thực thi hoặc công cụ đo ở tầng ứng dụng.

### 4.3. Phân tích wait statistics và hồi quy kế hoạch

Nếu Query Store wait statistics được hỗ trợ và bật, có thể xếp hạng nhóm chờ theo truy vấn:

```sql
SELECT TOP (20)
       q.query_id,
       ws.wait_category_desc,
       SUM(ws.total_query_wait_time_ms) AS total_wait_ms,
       MAX(ws.max_query_wait_time_ms) AS max_wait_ms
FROM sys.query_store_wait_stats AS ws
JOIN sys.query_store_plan AS p
  ON p.plan_id = ws.plan_id
JOIN sys.query_store_query AS q
  ON q.query_id = p.query_id
GROUP BY q.query_id, ws.wait_category_desc
ORDER BY total_wait_ms DESC;
```

Wait category giúp khoanh vùng CPU, I/O, khóa, log hoặc các nhóm chờ khác. Đối chiếu thời gian chờ với runtime statistics và khoảng tải tương ứng. Một wait category có tổng thời gian lớn có thể do nhiều lần thực thi cộng dồn; nó không có nghĩa một lần chạy đơn lẻ đã chờ lâu như vậy.

Để điều tra plan regression, so sánh `plan_id`, thời gian trung bình, CPU, logical reads và số lần thực thi giữa các khoảng. Query Store có thể hỗ trợ force một kế hoạch đã biết là ổn định, nhưng đây là biện pháp có điều kiện. Trước khi force plan, cần xác nhận kế hoạch cũ vẫn phù hợp với dữ liệu và tham số hiện tại, kiểm tra nguyên nhân optimizer đổi plan, theo dõi sau khi force và chuẩn bị cách bỏ force nếu kết quả xấu đi. Không dùng plan forcing để che một vấn đề thống kê hoặc thiết kế dữ liệu chưa được xử lý.

## 5. Quy trình dùng công cụ để tìm nút thắt

Ba công cụ có cách lưu dữ liệu khác nhau, nhưng quy trình điều tra có thể thống nhất:

1. **Xác định phạm vi:** chọn database, khoảng thời gian, workload, mức tải và mục tiêu cần cải thiện. Ghi lại thời điểm restart hoặc reset thống kê nếu có.
2. **Xếp hạng mẫu truy vấn:** dùng tổng thời gian để tìm nhóm tiêu thụ nhiều tài nguyên; dùng số lần gọi và thời gian trung bình để phân biệt truy vấn phổ biến với truy vấn chậm mỗi lần.
3. **Đánh giá lượng công việc:** xem số dòng examined, rows, logical reads, block reads, dữ liệu tạm, sort và số lần thực thi. So sánh dữ liệu phải xử lý với kết quả cần trả về.
4. **Phân loại chờ:** kiểm tra wait event hoặc wait category, xác định I/O, lock, log, đồng bộ hay tài nguyên khác đang chi phối. Dùng dữ liệu ở cấp session/thread khi cần tìm tác nhân.
5. **Đọc execution plan:** so sánh ước lượng với số liệu thực tế, kiểm tra scan, join, sort, hash, số vòng lặp và sự thay đổi plan theo thời gian.
6. **Đặt giả thuyết:** ví dụ giảm số dòng phải đọc, giảm số lần gọi lặp, rút ngắn thời gian giữ khóa hoặc loại bỏ spill ra đĩa.
7. **Đo lại và so sánh:** dùng cùng khoảng tải hoặc bài kiểm thử tương đương; so sánh độ trễ, throughput, CPU, I/O, wait, logical reads và tỷ lệ lỗi.

Số liệu thống kê tích lũy cần được chuyển thành số liệu theo khoảng bằng cách lấy hiệu giữa hai snapshot. Nếu máy chủ khởi động lại, view bị reset hoặc công cụ dọn dữ liệu trong khoảng đo, phép tính chênh lệch có thể sai. Hãy ghi nhận những sự kiện đó cùng kết quả đo.

## 6. Ví dụ chọn công cụ và diễn giải kết quả

Giả sử nhóm vận hành nhận thấy endpoint tra cứu đơn hàng chậm hơn trong giờ cao điểm. Trên PostgreSQL, `pg_stat_statements` cho thấy một mẫu truy vấn có hàng triệu lần gọi và tổng thời gian cao, nhưng thời gian trung bình chỉ ở mức vừa phải. `shared_blks_read` và `temp_blks_written` tăng nhanh. Điều này gợi ý cần xem xét cả tần suất gọi và lượng dữ liệu trung gian, sau đó dùng `EXPLAIN (ANALYZE, BUFFERS)` để kiểm tra plan.

Trong một hệ thống MySQL có triệu chứng tương tự, `events_statements_summary_by_digest` cho thấy `SUM_ROWS_EXAMINED` cao hơn nhiều so với `SUM_ROWS_SENT`, đồng thời số bảng tạm trên đĩa tăng. Nhóm phát triển kiểm tra điều kiện lọc, thứ tự cột của chỉ mục và thao tác sort. Chỉ mục mới chỉ được chấp nhận sau khi đo lại cả truy vấn đọc lẫn chi phí ghi.

Trên SQL Server, người vận hành thấy thời gian thực thi của cùng một query_id tăng mạnh sau một lần triển khai. Query Store cho thấy plan_id đã đổi trong khoảng thời gian đó và logical reads tăng. Nhóm có thể so sánh hai kế hoạch, xem thống kê và dữ liệu đầu vào, sau đó thử kế hoạch ổn định trong điều kiện kiểm soát. Việc force plan chỉ được duy trì nếu kiểm thử tải và theo dõi production xác nhận lợi ích.

Các ví dụ trên cho thấy mỗi công cụ tạo ra một điểm bắt đầu khác nhau. Quyết định tối ưu chỉ được đưa ra sau khi nối thống kê truy vấn với plan, wait event và điều kiện tải thực tế.

## 7. Những giới hạn và sai lầm cần tránh

- **Xem số liệu tích lũy như kết quả của một lần chạy:** các bộ đếm thường tăng từ khi khởi động, reset hoặc bắt đầu khoảng thống kê. Hãy xác định khoảng đo và tính delta khi cần.
- **Chỉ xếp hạng theo tổng thời gian:** truy vấn được gọi rất nhiều có thể đứng đầu dù mỗi lần chạy nhanh. Hãy xem cả calls, mean, số dòng và độ trễ từng lần nếu có.
- **Dùng trung bình để suy ra p95/p99:** thống kê trung bình không mô tả đuôi phân phối. Cần telemetry ở cấp lần thực thi cho phân vị.
- **Coi mọi lần đọc block là đọc đĩa vật lý:** cache của hệ điều hành và cache của cơ sở dữ liệu ảnh hưởng cách diễn giải số liệu I/O.
- **Bật mọi instrument và consumer:** thu thập quá rộng có thể tăng overhead hoặc dung lượng bộ nhớ; hãy bật đúng phạm vi cần thiết.
- **Giả định dữ liệu luôn tồn tại sau restart:** Performance Schema chủ yếu lưu dữ liệu trong bộ nhớ; thống kê PostgreSQL có thể reset; Query Store có chính sách lưu trữ và cleanup riêng.
- **So sánh số liệu khác đơn vị:** xác minh timer là millisecond, microsecond hay picosecond trước khi tính toán hoặc đưa lên dashboard.
- **Kết luận cần thêm chỉ mục chỉ từ một bộ đếm:** số lần không dùng chỉ mục hoặc số dòng examined là tín hiệu điều tra, không phải bằng chứng duy nhất. Quét toàn bảng đôi khi là kế hoạch hợp lý.
- **Force plan hoặc reset thống kê thiếu kiểm soát:** các thao tác này có thể ảnh hưởng vận hành và làm mất dữ liệu chẩn đoán; cần quy trình thay đổi, đường cơ sở và kế hoạch hoàn tác.

## 8. Checklist triển khai và vận hành

- [ ] Đã xác nhận công cụ được bật và thu thập đúng loại sự kiện cần thiết.
- [ ] Đã ghi nhận phiên bản hệ quản trị, cấu hình, quyền truy cập và thời điểm restart/reset.
- [ ] Đã kiểm tra đơn vị của timer và phạm vi của từng bộ đếm.
- [ ] Đã theo dõi tổng thời gian, số lần gọi, thời gian trung bình và số dòng đọc/trả về.
- [ ] Đã kết hợp thống kê truy vấn với execution plan và wait event.
- [ ] Đã xác định giới hạn lưu trữ, cleanup, history size và overhead của công cụ.
- [ ] Đã bảo vệ quyền truy cập đối với SQL text và dữ liệu có thể chứa thông tin nhạy cảm.
- [ ] Đã lưu đường cơ sở và đo lại sau thay đổi trong điều kiện tương đương.

`pg_stat_statements`, Performance Schema và Query Store cung cấp các góc nhìn bổ sung để hiểu workload. Khi biết cách bật, truy vấn, diễn giải và kiểm soát giới hạn của từng công cụ, nhóm vận hành có thể tìm đúng mẫu SQL cần tối ưu, nhận diện thay đổi kế hoạch và wait, rồi xác nhận hiệu quả bằng số liệu trước và sau điều chỉnh.
