# sys schema và các view phục vụ chẩn đoán

Trong MySQL, sys schema là lớp công cụ giúp đọc dữ liệu vận hành từ Performance Schema và một phần metadata của INFORMATION_SCHEMA bằng các view, function và stored procedure có tên dễ hiểu. Thay vì tự ghép nhiều bảng sự kiện, người vận hành có thể bắt đầu từ các view như statement_analysis, processlist, schema_table_statistics, schema_index_statistics, waits_global_by_latency hoặc innodb_lock_waits để tìm vùng cần điều tra.

sys schema không phải một monitoring agent độc lập và cũng không phải kho lưu lịch sử dài hạn. Phần lớn số liệu của nó được tổng hợp từ Performance Schema, vì vậy chất lượng chẩn đoán phụ thuộc vào việc Performance Schema được bật, instrument và consumer có được cấu hình phù hợp hay không. Các bộ đếm cũng có thể được reset hoặc mất khi server khởi động lại.

Bài học thuộc phạm vi DATABASE_MYSQL: hiểu kiến trúc sys schema, chọn đúng view theo câu hỏi vận hành, đọc số liệu truy vấn và I/O, tìm lock wait, đánh giá index/buffer pool, hiểu quyền truy cập và giới hạn của số liệu, rồi xây dựng quy trình chẩn đoán có thể lặp lại.

## 1. sys schema giải quyết vấn đề gì?

Performance Schema cung cấp dữ liệu sự kiện chi tiết về statement, stage, wait, mutex, file I/O, table I/O, transaction và thread. Dữ liệu này mạnh nhưng thường cần JOIN, lọc và định dạng.

sys schema đặt một lớp view và routine lên trên các nguồn dữ liệu đó. Mục tiêu là trả lời nhanh những câu hỏi như:

- Câu SQL nào tiêu tốn tổng thời gian nhiều nhất?
- Câu SQL nào có latency trung bình hoặc p95 cao?
- Schema hoặc bảng nào có nhiều lượt đọc/ghi?
- Index nào có dấu hiệu ít được sử dụng?
- Session nào đang chạy lâu hoặc chờ khóa?
- Transaction nào đang chặn transaction khác?
- Loại wait nào chiếm nhiều thời gian?
- File hoặc tablespace nào có I/O cao?
- Buffer pool đang giữ page của schema/bảng nào?
- Host hoặc user nào tạo ra nhiều tải?

Ví dụ, thay vì tự tổng hợp Performance Schema digest tables, có thể bắt đầu bằng:

~~~
SELECT
    query,
    exec_count,
    total_latency,
    avg_latency,
    rows_examined,
    rows_sent
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 10;
~~~

View này giúp xác định nhóm statement đáng điều tra. Nó không tự chứng minh câu SQL là nguyên nhân duy nhất gây chậm; cần xem execution plan, dữ liệu đầu vào, concurrency và thời điểm quan sát.

## 2. sys schema nằm ở đâu trong kiến trúc quan sát?

Có thể hình dung luồng dữ liệu:

~~~text
Ứng dụng / client
       |
       v
MySQL server
       |
       +-----------------------------+
       |                             |
       v                             v
Performance Schema             INFORMATION_SCHEMA
(events, waits, counters,       (metadata schema,
threads, statements, I/O)        tables, columns, indexes)
       |                             |
       +--------------+--------------+
                      |
                      v
                  sys schema
        (views, functions, procedures)
                      |
                      v
         DBA / developer / monitoring
~~~

sys schema chủ yếu cung cấp cách đọc dễ dùng hơn. Nó không thay thế Performance Schema; khi cần điều tra sâu, vẫn có thể truy vấn bảng nguồn trong performance_schema.

### 2.1. sys schema không tự tạo telemetry

Nếu statement instrumentation hoặc consumer tương ứng bị tắt, view tổng hợp statement có thể thiếu dữ liệu. Nếu file I/O instruments không được bật, các view I/O không thể cung cấp số liệu đầy đủ.

Vì vậy, khi view trả về rỗng hoặc số liệu bằng 0, không vội kết luận server không có hoạt động. Hãy kiểm tra:
- Performance Schema có bật không.
- Instrument cần thiết có được bật không.
- Consumer cần thiết có được bật không.
- Kích thước buffer/summary table có đủ không.
- Server vừa restart hoặc reset counters không.
- Account hiện tại có đủ quyền đọc dữ liệu không.

### 2.2. sys schema có phải dữ liệu lịch sử không?

Không. Phần lớn số liệu Performance Schema là số liệu runtime trong bộ nhớ, thường được tích lũy từ khi server khởi động hoặc từ lần reset tương ứng. Khi restart, nhiều summary bị khởi tạo lại. Khi reset summary, khoảng thời gian quan sát cũng thay đổi.

Nếu cần lịch sử theo ngày/tuần/tháng, hãy thu thập định kỳ từ monitoring platform hoặc lưu snapshot vào hệ thống telemetry riêng. Không coi sys schema là kho lịch sử bền vững.

## 3. Kiểm tra sys schema và phiên bản

Kiểm tra phiên bản server:

~~~
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution;
~~~

Kiểm tra schema:

~~~
SHOW DATABASES LIKE 'sys';
~~~

Liệt kê view:

~~~
SHOW FULL TABLES FROM sys
WHERE Table_type = 'VIEW'
ORDER BY Tables_in_sys;
~~~

Liệt kê routine:

~~~
SHOW PROCEDURE STATUS
WHERE Db = 'sys';

SHOW FUNCTION STATUS
WHERE Db = 'sys';
~~~

Xem định nghĩa một view:

~~~
SHOW CREATE VIEW sys.statement_analysis;
~~~

Xem định nghĩa procedure:

~~~
SHOW CREATE PROCEDURE sys.diagnostics;
~~~

sys schema được tích hợp trong các bản MySQL hiện đại, nhưng tập view, cột và routine có thể thay đổi theo phiên bản. Không dựa vào tên view từ một bài viết cũ để giả định mọi server có cùng schema. Trước khi viết dashboard hoặc script, hãy xác minh object và column trên đúng phiên bản triển khai.

## 4. Nhóm view quan trọng theo câu hỏi vận hành

| Câu hỏi | View thường dùng |
|---|---|
| Statement nào tiêu tốn latency nhiều? | statement_analysis |
| Statement nào có lỗi hoặc warning? | statements_with_errors_or_warnings |
| Statement nào quét toàn bảng? | statements_with_full_table_scans |
| Statement nào tạo temporary table? | statements_with_temp_tables |
| Statement nào có runtime ở percentile cao? | statements_with_runtimes_in_95th_percentile |
| Session nào đang hoạt động? | processlist, session |
| Host nào tạo nhiều tải? | host_summary, host_summary_by_statement_latency |
| User nào tạo nhiều tải? | user_summary, user_summary_by_statement_latency |
| Bảng nào có nhiều I/O logic? | schema_table_statistics |
| Index nào có hoạt động đọc/ghi? | schema_index_statistics |
| Index nào không ghi nhận lượt sử dụng? | schema_unused_indexes |
| Index nào có vẻ dư thừa? | schema_redundant_indexes |
| InnoDB transaction nào đang chờ khóa? | innodb_lock_waits |
| Metadata/table lock nào đang chờ? | schema_table_lock_waits |
| Wait event nào có latency cao? | waits_global_by_latency |
| File nào có I/O lớn? | io_global_by_file_by_bytes, io_global_by_file_by_latency |
| Buffer pool giữ page của bảng nào? | innodb_buffer_stats_by_table |

Đây là điểm bắt đầu, không phải danh sách đầy đủ. Mỗi view có cách tổng hợp và điều kiện dữ liệu riêng. Hãy dùng SHOW CREATE VIEW để xem nguồn dữ liệu và cột thực tế.

## 5. processlist và session: ai đang chạy hoặc chờ?

sys.processlist cung cấp góc nhìn chi tiết hơn về thread/session so với danh sách process đơn giản. sys.session tập trung vào các foreground session.

Ví dụ:

~~~
SELECT
    conn_id,
    user,
    db,
    command,
    state,
    time,
    current_statement,
    statement_latency,
    lock_latency,
    rows_examined,
    rows_sent,
    tmp_tables,
    tmp_disk_tables,
    full_scan
FROM sys.processlist
ORDER BY statement_latency DESC;
~~~

Các trường có thể giúp trả lời:
- Session đang chạy statement nào?
- Statement đã chạy bao lâu?
- Có chờ lock không?
- Đã đọc bao nhiêu hàng?
- Có tạo temporary table trên disk không?
- Có dấu hiệu full scan không?

Tên cột cụ thể có thể thay đổi theo bản sys schema. Nếu câu truy vấn mẫu báo unknown column, dùng DESCRIBE sys.processlist và SHOW CREATE VIEW để điều chỉnh theo phiên bản.

### 5.1. Phân biệt connection ID và thread ID

MySQL connection ID thường là processlist ID mà client nhìn thấy. Performance Schema có THREAD_ID nội bộ để liên kết sự kiện của thread.

Một session có thể được ánh xạ qua performance_schema.threads:

~~~
SELECT
    PROCESSLIST_ID,
    THREAD_ID,
    NAME,
    TYPE,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE
FROM performance_schema.threads
WHERE PROCESSLIST_ID IS NOT NULL;
~~~

Khi nối dữ liệu từ sys với Performance Schema, phải dùng đúng loại ID. Không dùng CONNECTION_ID() để so sánh trực tiếp với THREAD_ID nếu chưa ánh xạ.

### 5.2. Sleeping session không nhất thiết là lỗi

Một connection ở trạng thái Sleep có thể thuộc connection pool và đang chờ request tiếp theo. Điều cần quan sát là:
- Số lượng sleeping connection.
- Thời gian idle.
- Có transaction mở trong session idle không.
- Pool có giữ connection vượt nhu cầu không.
- Connection có giữ metadata/row lock không.

Session Sleep nhưng vẫn có transaction mở là vấn đề đáng chú ý hơn một connection idle không có transaction.

## 6. statement_analysis: tìm SQL tốn thời gian nhất

View sys.statement_analysis tổng hợp statement theo digest, giúp gom nhiều câu SQL có literal khác nhau về cùng một dạng normalized statement.

Ví dụ:

~~~
SELECT
    db,
    query,
    exec_count,
    err_count,
    warn_count,
    total_latency,
    avg_latency,
    max_latency,
    rows_sent,
    rows_examined,
    tmp_tables,
    tmp_disk_tables,
    rows_sorted,
    full_scan,
    first_seen,
    last_seen
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 20;
~~~

Các chỉ số quan trọng:

| Chỉ số | Cách hiểu |
|---|---|
| exec_count | Số lần thực thi được tổng hợp |
| total_latency | Tổng thời gian thực thi tích lũy |
| avg_latency | Latency trung bình |
| max_latency | Latency lớn nhất được ghi nhận |
| rows_examined | Số hàng đã đọc/xem xét |
| rows_sent | Số hàng trả về client |
| tmp_tables | Số temporary table |
| tmp_disk_tables | Temporary table dùng disk |
| rows_sorted | Số hàng được sắp xếp |
| full_scan | Thông tin về full scan theo cách view tổng hợp |

Một statement có total_latency lớn có thể chỉ vì được gọi rất nhiều lần. Một statement có avg_latency cao có thể chậm dù số lần chạy ít. Hãy xem cả tổng latency, số lần thực thi, latency trung bình, max và lượng hàng đọc.

### 6.1. Rows examined so với rows sent

Nếu rows_examined rất lớn nhưng rows_sent nhỏ, truy vấn có thể đọc nhiều dữ liệu để trả ít kết quả. Đây là tín hiệu cần xem:
- Predicate có dùng index không.
- Index có phù hợp thứ tự cột không.
- Điều kiện có bọc cột trong function không.
- Cardinality và thống kê có đúng không.
- Có thể giảm dữ liệu đầu vào hoặc dùng covering index không.

Không có một ngưỡng rows_examined/rows_sent phù hợp cho mọi truy vấn. Truy vấn báo cáo tổng hợp có thể cần đọc nhiều hàng; truy vấn lookup theo primary key thì thường không.

### 6.2. Tổng latency không phải CPU time

Latency trong Performance Schema có thể bao gồm thời gian chờ và thực thi theo instrument. Nó không đồng nghĩa CPU time thuần. Một query có latency cao có thể do:
- Chờ lock.
- Chờ I/O.
- Chờ metadata lock.
- Chờ tài nguyên khác.
- Thực thi CPU nhiều.
- Trả dữ liệu lớn qua mạng.

Cần kết hợp statement view với wait views, lock views và OS metrics.

## 7. Tìm statement có lỗi, full scan và temporary table

### 7.1. Lỗi và warning

~~~
SELECT *
FROM sys.statements_with_errors_or_warnings
ORDER BY last_seen DESC
LIMIT 20;
~~~

Dùng view này để tìm nhóm statement có lỗi hoặc warning được Performance Schema ghi nhận. Sau đó xem query digest, thời điểm và error count. Không phải mọi lỗi ứng dụng đều được biểu diễn đầy đủ nếu instrumentation hoặc retention không đủ.

### 7.2. Full table scan

~~~
SELECT *
FROM sys.statements_with_full_table_scans
ORDER BY rows_examined DESC
LIMIT 20;
~~~

Full scan không luôn luôn xấu. Nếu bảng nhỏ hoặc truy vấn đọc phần lớn bảng, table scan có thể rẻ hơn index lookup. Cần so sánh:
- Kích thước bảng.
- Số hàng ước lượng và thực tế.
- Selectivity của predicate.
- Chi phí random I/O.
- Kế hoạch EXPLAIN.
- Tần suất chạy.

### 7.3. Temporary table

~~~
SELECT *
FROM sys.statements_with_temp_tables
ORDER BY disk_tmp_tables DESC
LIMIT 20;
~~~

Temporary table trong memory có thể bình thường. Temporary table spill ra disk có thể làm tăng latency, nhất là khi dữ liệu trung gian lớn hoặc query chạy thường xuyên.

Xem query có GROUP BY, DISTINCT, ORDER BY, UNION hoặc thao tác trung gian nào. Không tăng mọi buffer limit ngay lập tức; trước tiên xác định query shape và dữ liệu trung gian.

### 7.4. Runtime ở percentile cao

~~~
SELECT *
FROM sys.statements_with_runtimes_in_95th_percentile
ORDER BY avg_latency DESC
LIMIT 20;
~~~

Percentile view giúp phát hiện nhóm statement có latency tail cao. Latency trung bình tốt không bảo đảm p95/p99 tốt; một số request có thể chậm do lock, cache miss, dữ liệu lớn hoặc contention.

## 8. Digest và normalized query

Performance Schema chuẩn hóa statement thành digest để tổng hợp những câu SQL có cấu trúc giống nhau nhưng literal khác nhau.

Ví dụ:

~~~
SELECT * FROM orders WHERE customer_id = 101;
SELECT * FROM orders WHERE customer_id = 202;
~~~

Có thể được gom vào cùng một digest pattern, tùy statement normalization.

Digest hữu ích để:
- Nhận diện query pattern phổ biến.
- Ước lượng tổng chi phí theo loại statement.
- Tìm query shape có nhiều lần thực thi.
- Theo dõi thay đổi workload qua thời gian.
- Tránh phải lưu mọi literal nhạy cảm vào dashboard.

Digest không giữ mọi chi tiết của từng lần chạy. Nếu chỉ một giá trị tham số gây skew dữ liệu, tổng hợp digest có thể che khuất trường hợp đặc biệt. Khi điều tra parameter-sensitive query, cần lấy mẫu có kiểm soát ở tầng ứng dụng hoặc slow log.

### 8.1. Digest capacity và mất dấu statement

Performance Schema có giới hạn số digest được giữ đồng thời. Nếu workload có rất nhiều query shape, một số digest có thể không được lưu hoặc bị tổng hợp vào trạng thái khác theo cấu hình.

Kiểm tra biến liên quan:

~~~
SHOW VARIABLES LIKE 'performance_schema_max_digest_length';
SHOW VARIABLES LIKE 'performance_schema_digests_size';
~~~

Không tăng capacity mà chưa ước lượng bộ nhớ và workload. Thay đổi sizing có thể cần restart tùy biến cấu hình.

## 9. Tổng hợp tải theo schema và bảng

sys.schema_table_statistics tổng hợp hoạt động đọc/ghi theo bảng:

~~~
SELECT
    table_schema,
    table_name,
    rows_fetched,
    fetch_latency,
    rows_inserted,
    insert_latency,
    rows_updated,
    update_latency,
    rows_deleted,
    delete_latency,
    total_latency
FROM sys.schema_table_statistics
ORDER BY total_latency DESC
LIMIT 30;
~~~

Có thể dùng để tìm:
- Bảng được đọc nhiều.
- Bảng có latency đọc cao.
- Bảng có ghi nhiều.
- Bảng có tổng latency lớn.
- Bảng có tỷ lệ hoạt động bất thường.

Số liệu phụ thuộc instrument table I/O và thời gian tích lũy. Một bảng lớn hoặc được truy cập nhiều có thể đứng đầu dù mọi truy vấn đều tối ưu. Hãy chuẩn hóa theo workload và số request khi so sánh.

### 9.1. schema_table_statistics_with_buffer

View này bổ sung góc nhìn buffer pool cho hoạt động bảng. Có thể dùng để xem page trong buffer pool, tỷ lệ hit/allocated hoặc thông tin liên quan theo định nghĩa của phiên bản.

~~~
SELECT *
FROM sys.schema_table_statistics_with_buffer
ORDER BY total_latency DESC
LIMIT 20;
~~~

Vì cấu trúc cột có thể khác theo phiên bản, hãy DESCRIBE trước khi đưa vào dashboard. Buffer pool hit ratio tổng thể cao không bảo đảm mọi truy vấn đều nhanh; một hot table có thể bị miss trong khi các bảng khác giữ nhiều page không cần thiết.

## 10. schema_index_statistics: index được sử dụng ra sao?

~~~
SELECT
    table_schema,
    table_name,
    index_name,
    rows_selected,
    select_latency,
    rows_inserted,
    insert_latency,
    rows_updated,
    update_latency,
    rows_deleted,
    delete_latency
FROM sys.schema_index_statistics
ORDER BY rows_selected DESC
LIMIT 30;
~~~

View giúp quan sát hoạt động index theo số liệu Performance Schema. Cần phân biệt:
- Index được dùng cho đọc.
- Index bị duy trì bởi INSERT/UPDATE/DELETE.
- Index có chi phí ghi nhưng ít lượt đọc.
- Index hỗ trợ constraint hoặc truy vấn hiếm nhưng quan trọng.

### 10.1. schema_unused_indexes không phải lệnh DROP

~~~
SELECT *
FROM sys.schema_unused_indexes
ORDER BY object_schema, object_name, index_name;
~~~

View liệt kê index không ghi nhận lượt sử dụng trong khoảng dữ liệu hiện có. Không được tự động DROP các index trong danh sách.

Trước khi bỏ index, cần:
1. Quan sát đủ chu kỳ workload, bao gồm báo cáo định kỳ và tác vụ cuối tháng/quý.
2. Kiểm tra index có phục vụ PRIMARY KEY, UNIQUE, FOREIGN KEY hoặc constraint không.
3. Kiểm tra query plan hiếm nhưng quan trọng.
4. Kiểm tra workload batch, ETL, backup/maintenance.
5. Đánh giá tác động tới locking và access path.
6. Thử trên staging và đo.
7. Có kế hoạch rollback DDL.

Counters có thể mới được reset sau restart; index dùng mỗi tháng một lần có thể bị đánh dấu unused nếu quan sát quá ngắn.

### 10.2. schema_redundant_indexes

~~~
SELECT *
FROM sys.schema_redundant_indexes
ORDER BY table_schema, table_name;
~~~

View tìm các index có dấu hiệu trùng lặp hoặc bao hàm tiền tố của index khác. Nhưng hai index có cùng leftmost prefix không luôn dư thừa về mặt vận hành:
- Một index có thể UNIQUE, index kia không.
- Collation, sort direction hoặc prefix length có thể khác.
- Index có thể hỗ trợ constraint khác.
- Một index hẹp hơn có thể giảm I/O cho workload cụ thể.
- Visibility và optimizer behavior có thể khác.

Dùng view làm danh sách điều tra, không phải quyết định xóa tự động.

## 11. Quan sát InnoDB buffer pool

sys.innodb_buffer_stats_by_table tổng hợp page trong buffer pool theo schema/table:

~~~
SELECT
    object_schema,
    object_name,
    allocated,
    data,
    pages
FROM sys.innodb_buffer_stats_by_table
ORDER BY allocated DESC
LIMIT 20;
~~~

Các cột cụ thể cần xác minh bằng DESCRIBE vì có thể thay đổi theo phiên bản sys schema. View có thể giúp tìm bảng chiếm nhiều buffer pool memory.

Cần hiểu:
- Buffer pool chứa page dữ liệu và index đang được cache.
- Page hiện diện không đồng nghĩa truy vấn đang dùng hiệu quả.
- Một bảng lớn chiếm buffer pool có thể là do workload đọc nhiều.
- Buffer pool snapshot phản ánh trạng thái tại thời điểm truy vấn, không phải lịch sử.
- View này có thể tốn tài nguyên khi tổng hợp trên buffer pool lớn; không chạy liên tục ở tần suất quá cao.

### 11.1. Không tối ưu chỉ theo tỷ lệ hit

Hit ratio cao là tín hiệu tốt nhưng không phải mục tiêu duy nhất. Nếu query đọc quá nhiều page nhưng tất cả đều nằm trong memory, latency vẫn có thể cao do CPU, latch, row lock hoặc lượng dữ liệu xử lý.

Kết hợp:
- Buffer pool read requests và reads.
- Statement rows_examined.
- Table/index statistics.
- Waits.
- OS memory và I/O.
- Latency ứng dụng.

## 12. InnoDB lock waits

sys.innodb_lock_waits giúp tìm transaction đang chờ row lock và transaction đang chặn.

~~~
SELECT
    waiting_pid,
    waiting_query,
    waiting_trx_started,
    waiting_trx_age,
    waiting_trx_rows_locked,
    blocking_pid,
    blocking_query,
    blocking_trx_started,
    blocking_trx_age,
    blocking_trx_rows_locked
FROM sys.innodb_lock_waits
ORDER BY waiting_trx_age DESC;
~~~

Câu hỏi cần trả lời:
- Session nào đang chờ?
- Session nào đang chặn?
- Transaction bắt đầu lúc nào?
- Transaction đã mở bao lâu?
- Có bao nhiêu row bị lock?
- Query hiện tại của blocker là gì?
- Có transaction idle nhưng chưa commit không?

### 12.1. Blocking query có thể là NULL

Một transaction có thể giữ lock sau khi câu SQL cuối cùng đã kết thúc và session trở về Sleep. Khi đó blocking_query có thể không còn là statement đang chạy. Hãy xem blocking transaction, session và lịch sử statement gần nhất thay vì kết luận không có blocker.

### 12.2. Cột sql_kill_* chỉ là câu lệnh gợi ý

Một số view sys cung cấp cột chứa câu SQL như KILL QUERY hoặc KILL CONNECTION để hỗ trợ thao tác. Đó là chuỗi lệnh được tạo ra để tham khảo; SELECT view không tự thực thi lệnh đó.

Trước khi KILL:
- Xác nhận đúng connection ID.
- Xác định chủ sở hữu ứng dụng.
- Kiểm tra transaction có thể rollback lớn không.
- Đánh giá ảnh hưởng tới request và dữ liệu.
- Theo runbook và quyền vận hành.

KILL CONNECTION có thể làm transaction rollback và gây tác động rộng hơn việc dừng query hiện tại.

## 13. Metadata lock và table lock waits

Row lock và metadata lock là hai nhóm khác nhau. DDL như ALTER TABLE có thể chờ metadata lock trong khi session khác đang dùng bảng.

sys.schema_table_lock_waits giúp quan sát một số table/metadata lock wait:

~~~
SELECT
    object_schema,
    object_name,
    waiting_pid,
    waiting_query,
    waiting_query_secs,
    blocking_pid,
    blocking_query,
    blocking_lock_type,
    sql_kill_blocking_connection
FROM sys.schema_table_lock_waits
ORDER BY waiting_query_secs DESC;
~~~

Tên cột có thể khác theo phiên bản. Xác minh bằng DESCRIBE sys.schema_table_lock_waits trước khi dùng.

Khi DDL bị chờ:
- Tìm session đang giữ metadata lock.
- Kiểm tra transaction dài hoặc session idle-in-transaction.
- Xác định DDL có đang chờ queue và làm các request sau bị xếp hàng không.
- Chọn thời điểm DDL phù hợp.
- Không kill blocker trước khi hiểu tác động.

Không nhầm view này với innodb_lock_waits. Một transaction có thể không chờ row lock nhưng vẫn chặn DDL do metadata lock.

## 14. Wait events: server đang chờ điều gì?

sys.waits_global_by_latency tổng hợp wait event theo thời gian chờ:

~~~
SELECT
    events,
    total,
    total_latency,
    avg_latency,
    max_latency
FROM sys.waits_global_by_latency
ORDER BY total_latency DESC
LIMIT 30;
~~~

Tên cột có thể được định dạng khác theo phiên bản. View cho biết nhóm wait nào có tổng latency lớn.

Một số nhóm thường gặp:
- File I/O.
- Table I/O.
- Lock.
- Mutex.
- Condition.
- Socket/network.
- Synchronization nội bộ.

### 14.1. Tổng latency và số lần wait

Một wait event có total_latency lớn có thể do:
- Số lần xảy ra rất nhiều.
- Mỗi lần chờ kéo dài.
- Một số lần chờ cực lâu.

So sánh total, avg và max. Một wait hiếm có max rất cao có thể gây tail latency; một wait thường xuyên với avg thấp có thể tích lũy tổng thời gian lớn.

### 14.2. Wait theo user và host

Các view như waits_by_user_by_latency và waits_by_host_by_latency có thể giúp phân biệt workload theo nguồn. Nếu một account hoặc host tạo ra nhiều wait, điều tra pool, query pattern, network và concurrency của nhóm đó.

Không kết luận host gây lỗi chỉ từ tổng latency; host có thể đơn giản là nguồn tạo nhiều request nhất.

## 15. File I/O và table I/O

sys.io_global_by_file_by_bytes:

~~~
SELECT *
FROM sys.io_global_by_file_by_bytes
ORDER BY total_allocated DESC
LIMIT 20;
~~~

sys.io_global_by_file_by_latency:

~~~
SELECT *
FROM sys.io_global_by_file_by_latency
ORDER BY total_latency DESC
LIMIT 20;
~~~

Các view này giúp xác định file có lượng I/O hoặc latency lớn. Tên cột cụ thể nên kiểm tra trên server thực tế.

Có thể dùng để tìm:
- Tablespace có nhiều read/write.
- Redo/undo hoặc log file có hoạt động cao.
- File I/O latency tăng.
- Tệp tạm hoặc file liên quan workload đặc biệt.

Không quy mọi I/O latency về storage device ngay lập tức. Cần đối chiếu OS metrics, filesystem, queue depth, buffer pool và workload.

## 16. Tải theo user và host

sys.user_summary và sys.host_summary cung cấp góc nhìn theo nguồn workload:

~~~
SELECT *
FROM sys.user_summary
ORDER BY statement_latency DESC
LIMIT 20;
~~~

~~~
SELECT *
FROM sys.host_summary
ORDER BY statement_latency DESC
LIMIT 20;
~~~

Có thể xem sâu hơn theo statement type hoặc file I/O bằng các view cùng nhóm.

Các câu hỏi:
- Account nào tạo nhiều statement nhất?
- Account nào có latency cao?
- Host nào tạo nhiều rows examined?
- Một batch client có tạo quá nhiều temporary table không?
- Có account bất thường hoặc workload ngoài giờ không?

Số liệu theo user/host là tổng hợp trong Performance Schema. Account/host có thể được normalize hoặc gom theo cách định nghĩa view. Không dùng nó thay thế audit bảo mật; cần log/audit riêng nếu phải truy vết hành động của một người dùng cuối.

## 17. sys schema và các bảng cấu hình

sys.sys_config là bảng cấu hình một số routine/view của sys schema. Có thể xem:

~~~
SELECT *
FROM sys.sys_config
ORDER BY variable;
~~~

Các giá trị cấu hình có thể điều khiển giới hạn hoặc hành vi của một số helper. Không sửa bảng này theo phỏng đoán; xem comment và định nghĩa object liên quan trước.

Một số biến cấu hình sys thường được dùng trong routines như:
- diagnostics.allow_i_s_tables
- diagnostics.include_raw
- statement_performance_analyzer.limit
- statement_performance_analyzer.view
- statement_performance_analyzer.limit

Danh sách thực tế phụ thuộc phiên bản. Kiểm tra dữ liệu sys_config và SHOW CREATE PROCEDURE/FUNCTION. Không giả định mọi biến đều tồn tại ở mọi release.

## 18. Function và procedure hữu ích

Ngoài view, sys schema có helper function để định dạng hoặc tra cứu thông tin.

Một số function thường gặp:
- format_bytes(): định dạng số byte thành đơn vị dễ đọc.
- format_time(): định dạng thời gian picosecond thành chuỗi dễ đọc.
- format_path(): chuẩn hóa đường dẫn file.
- extract_schema_from_file_name(): trích schema từ tên file tablespace trong các trường hợp được hỗ trợ.
- extract_table_from_file_name(): trích tên bảng.
- ps_thread_id(): ánh xạ processlist ID sang Performance Schema thread ID.
- ps_thread_account(): trả account của thread theo ID.
- ps_thread_trx_info(): cung cấp thông tin transaction của thread theo cấu trúc hỗ trợ.

Ví dụ:

~~~
SELECT
    sys.format_bytes(1048576) AS one_mib,
    sys.format_time(1000000000000) AS one_second;
~~~

Định dạng output phụ thuộc helper và phiên bản. Hãy dùng helper để hiển thị dashboard, nhưng giữ số liệu gốc dạng numeric nếu cần tính toán tiếp.

### 18.1. statement_performance_analyzer

sys.statement_performance_analyzer là procedure hỗ trợ phân tích statement summary. Nó có thể tạo hoặc so sánh snapshot statement statistics theo các chế độ được hỗ trợ.

Vì procedure có tham số và hành vi thay đổi theo phiên bản, trước khi tích hợp vào runbook:
~~~
SHOW CREATE PROCEDURE sys.statement_performance_analyzer;
~~~

Đọc định nghĩa và tài liệu của đúng phiên bản. Không gọi procedure trên production lần đầu mà chưa hiểu nó tạo temporary table, sử dụng biến session hoặc yêu cầu quyền gì.

### 18.2. diagnostics

sys.diagnostics là procedure thu thập nhiều nhóm thông tin chẩn đoán trong một khoảng thời gian. Nó có thể truy vấn nhiều view và sinh output lớn.

Trước khi dùng:
- Xem SHOW CREATE PROCEDURE.
- Kiểm tra tham số và mức thu thập.
- Ước lượng overhead.
- Chạy thử trên staging.
- Chỉ chọn mức chi tiết cần thiết.
- Lưu output vào hệ thống incident theo chính sách dữ liệu.

Không chạy diagnostics liên tục như một polling loop thay cho monitoring platform.

## 19. Quyền truy cập và bảo mật

sys schema không bỏ qua cơ chế privilege của MySQL. Quyền cần thiết phụ thuộc view/routine, SQL SECURITY, nguồn dữ liệu và loại thông tin muốn xem.

Một account chỉ được xem một phần dữ liệu có thể không nhìn thấy mọi thread hoặc mọi statement. Quyền PROCESS có ảnh hưởng tới khả năng xem hoạt động của session khác trong một số giao diện. Quyền đọc Performance Schema, sys view và metadata cũng cần được cấp phù hợp.

Xem định nghĩa view:

~~~
SHOW CREATE VIEW sys.processlist;
~~~

Xem quyền hiện tại:

~~~
SHOW GRANTS FOR CURRENT_USER();
~~~

Nguyên tắc:
- Tạo account/role riêng cho observability.
- Cấp SELECT trên đúng view cần thiết.
- Xem SQL SECURITY của view/procedure trước khi cấp quyền.
- Cấp PROCESS hoặc quyền nhạy cảm chỉ khi use case yêu cầu.
- Không dùng root cho dashboard.
- Không cấp quyền KILL cho account chỉ cần đọc.
- Hạn chế hiển thị query text có literal nhạy cảm.
- Bảo vệ endpoint/dashboard và log chứa SQL.

Một số view có thể hiển thị statement text, user, host, schema hoặc đường dẫn file. Đây có thể là dữ liệu nhạy cảm. Chỉ chia sẻ cho người có nhu cầu vận hành hợp lệ.

## 20. Cách đọc số liệu: counter, latency và khoảng thời gian

Một lỗi phổ biến là xem counter tích lũy như tốc độ tức thời.

Ví dụ rows_examined = 1.000.000 có thể là:
- 1 triệu hàng trong 10 giây.
- 1 triệu hàng trong 30 ngày.
- 1 triệu hàng kể từ lần reset trước.

Ba tình huống có ý nghĩa vận hành khác nhau.

Để tính tốc độ, lấy hai snapshot ở thời điểm t1 và t2:

\[
rate = \frac{counter(t2)-counter(t1)}{t2-t1}
\]

Ví dụ số statement tăng từ 10.000 lên 16.000 trong 60 giây:

\[
rate = \frac{16000-10000}{60}=100
\]

Tức khoảng 100 statement mỗi giây trong khoảng đo.

### 20.1. Cần xử lý counter reset

Nếu server restart hoặc summary table được truncate/reset, counter tại t2 có thể nhỏ hơn t1. Khi đó phép trừ trực tiếp không còn hợp lệ. Ghi nhận server uptime, thời điểm reset và instance identity cùng snapshot.

Không so sánh counter giữa hai server hoặc hai lần restart như cùng một chuỗi liên tục nếu không có chuẩn hóa.

### 20.2. Tổng latency và tỷ lệ latency

Một view hiển thị total_latency tích lũy. Muốn đo latency trong một khoảng thời gian, cần snapshot hai lần và tính delta nếu nguồn counter phù hợp. Avg latency trong view có thể là trung bình tích lũy từ lúc reset, không phải average của 1 phút vừa qua.

Để có latency theo cửa sổ thời gian chính xác, dùng monitoring system thu thập histogram/summary định kỳ ở tầng ứng dụng hoặc database exporter.

## 21. Workflow chẩn đoán một incident database

### Bước 1: Xác định phạm vi và thời gian

Ghi lại:
- Incident bắt đầu lúc nào.
- Instance nào bị ảnh hưởng.
- Query/API nào chậm.
- Tỷ lệ lỗi và latency p95/p99.
- Thay đổi deploy/config gần đây.
- Số connection và transaction đang mở.

### Bước 2: Kiểm tra session và lock

~~~
SELECT *
FROM sys.processlist
ORDER BY statement_latency DESC
LIMIT 20;
~~~

~~~
SELECT *
FROM sys.innodb_lock_waits
ORDER BY waiting_trx_age DESC;
~~~

Nếu nghi metadata lock, kiểm tra sys.schema_table_lock_waits.

### Bước 3: Tìm statement tốn thời gian

~~~
SELECT
    query,
    exec_count,
    total_latency,
    avg_latency,
    max_latency,
    rows_examined,
    rows_sent,
    tmp_disk_tables,
    full_scan
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 20;
~~~

Xác định query digest có liên quan thời điểm incident hay không. Nếu cần, lấy query mẫu và chạy EXPLAIN trong môi trường an toàn.

### Bước 4: Xem bảng và index

~~~
SELECT *
FROM sys.schema_table_statistics
ORDER BY total_latency DESC
LIMIT 20;
~~~

~~~
SELECT *
FROM sys.schema_index_statistics
ORDER BY rows_selected DESC
LIMIT 20;
~~~

Xác định bảng nóng, index có lượng truy cập cao và dấu hiệu scan.

### Bước 5: Xem waits và I/O

~~~
SELECT *
FROM sys.waits_global_by_latency
ORDER BY total_latency DESC
LIMIT 20;
~~~

~~~
SELECT *
FROM sys.io_global_by_file_by_latency
ORDER BY total_latency DESC
LIMIT 20;
~~~

Đối chiếu OS metrics và storage telemetry.

### Bước 6: Xác minh giả thuyết

Một dấu hiệu trong sys view chỉ là bằng chứng ban đầu. Dùng EXPLAIN, EXPLAIN ANALYZE phù hợp, slow query log, application trace và OS metrics để xác minh.

### Bước 7: Thay đổi có kiểm soát

Chỉ thay index, query, configuration hoặc concurrency sau khi xác định nguyên nhân. Ghi lại baseline, thay đổi, thời điểm và kết quả sau thay đổi.

## 22. Ví dụ thực tế: điều tra truy vấn báo cáo chậm

Giả sử API báo cáo đơn hàng chậm. Bắt đầu bằng statement analysis:

~~~
SELECT
    query,
    exec_count,
    avg_latency,
    max_latency,
    rows_examined,
    rows_sent,
    tmp_disk_tables
FROM sys.statement_analysis
WHERE db = 'sales'
ORDER BY total_latency DESC
LIMIT 10;
~~~

Giả sử một digest có rows_examined cao và rows_sent thấp. Bước tiếp theo:
1. Lấy query mẫu từ slow log hoặc application trace.
2. Chạy EXPLAIN.
3. Kiểm tra index và predicate.
4. Xem bảng tương ứng trong schema_table_statistics.
5. Kiểm tra waits để loại trừ lock/I/O.
6. Thử rewrite hoặc index trên staging.
7. So sánh latency, rows examined và write overhead.
8. Triển khai có rollback plan.

Không tạo index chỉ vì rows_examined lớn. Nếu báo cáo đọc phần lớn bảng, scan có thể là kế hoạch hợp lý. Nếu query bị lock wait, index mới có thể không giải quyết nguyên nhân chính.

## 23. Giới hạn và cạm bẫy khi dùng sys schema

- Số liệu không phải lịch sử dài hạn.
- Counters có thể reset khi restart hoặc truncate summary.
- Thiếu instrumentation dẫn đến view thiếu dữ liệu.
- Digest aggregation có thể gộp nhiều giá trị tham số.
- Digest capacity có giới hạn.
- Một số view có thể tốn tài nguyên khi tổng hợp trên instance lớn.
- Tên cột và object có thể thay đổi giữa phiên bản.
- Privilege có thể khiến account chỉ nhìn thấy một phần dữ liệu.
- Một query có tổng latency cao chưa chắc là query chậm nhất trong cửa sổ incident hiện tại.
- Index unused không đồng nghĩa index có thể xóa an toàn.
- Full scan không luôn luôn là lỗi.
- Buffer pool hit ratio không phản ánh toàn bộ hiệu năng.
- KILL statement có thể gây rollback hoặc ảnh hưởng request.
- Query text có thể chứa thông tin nhạy cảm.
- View chỉ mô tả quan sát; nó không tự khắc phục vấn đề.

## 24. Bài tập thực hành

### Bài 1: Khám phá sys schema

Liệt kê view, procedure và function trong schema sys. Chọn năm view, chạy SHOW CREATE VIEW và ghi lại nguồn Performance Schema/INFORMATION_SCHEMA mà chúng dùng.

### Bài 2: Statement analysis

Tạo workload SELECT/INSERT/UPDATE trong database lab. Truy vấn statement_analysis, xếp hạng theo total_latency và avg_latency. Giải thích vì sao hai thứ tự có thể khác.

### Bài 3: Rows examined

Tạo hai truy vấn cùng trả 10 hàng nhưng một truy vấn quét nhiều hàng hơn. Quan sát rows_examined/rows_sent và dùng EXPLAIN để giải thích.

### Bài 4: Temporary table

Chạy truy vấn GROUP BY/ORDER BY trên tập dữ liệu lớn. Xem statements_with_temp_tables và disk temporary table. Thử rewrite hoặc index trong staging.

### Bài 5: Session và connection pool

Mở một số connection idle và một transaction chưa commit trong lab. Quan sát sys.processlist và sys.session. Phân biệt Sleep bình thường với idle transaction giữ lock.

### Bài 6: Lock wait

Dùng hai session tạo row lock wait. Quan sát sys.innodb_lock_waits, xác định waiting_pid và blocking_pid. Không KILL connection trước khi xác định transaction owner.

### Bài 7: Metadata lock

Trong lab, mở transaction đọc bảng rồi thử DDL từ session khác. Quan sát sys.schema_table_lock_waits và giải thích khác biệt với row lock.

### Bài 8: Index usage

Chạy workload trên bảng có nhiều index. Xem schema_index_statistics và schema_unused_indexes. Lập danh sách index cần điều tra, nhưng không DROP chỉ dựa trên view.

### Bài 9: Wait events

Tạo workload đọc/ghi và quan sát waits_global_by_latency. So sánh total, avg và max latency. Phân biệt tổng thời gian chờ với CPU time.

### Bài 10: Buffer pool

Đọc innodb_buffer_stats_by_table và schema_table_statistics_with_buffer. Xác định bảng chiếm buffer pool lớn nhất. Giải thích vì sao không thể kết luận bảng đó gây chậm chỉ từ dung lượng page.

### Bài 11: Counter delta

Lấy hai snapshot statement_analysis hoặc Performance Schema summary cách nhau 60 giây. Tính delta exec_count và rows_examined mỗi giây. Lặp lại sau restart lab để thấy tác động reset.

### Bài 12: Dashboard role

Tạo role chỉ đọc cho một số view sys cần thiết. Kiểm tra SQL SECURITY và quyền nguồn. Xác nhận account không có quyền KILL hoặc quyền ghi dữ liệu nghiệp vụ.

### Bài 13: Incident report

Giả lập một query chậm do thiếu index và một query chậm do lock wait. Dùng sys views để thu thập bằng chứng, sau đó viết incident report gồm triệu chứng, giả thuyết, bằng chứng, nguyên nhân và hành động.

## 25. Checklist vận hành sys schema

- [ ] Đã xác nhận phiên bản MySQL và object sys có sẵn.
- [ ] Đã xác nhận Performance Schema đang bật.
- [ ] Đã kiểm tra instrument và consumer cần thiết.
- [ ] Đã biết số liệu là counter runtime, không phải lịch sử dài hạn.
- [ ] Đã kiểm tra thời điểm restart/reset trước khi so sánh.
- [ ] Đã dùng statement_analysis để tìm query pattern.
- [ ] Đã xem rows_examined, rows_sent, total/avg/max latency.
- [ ] Đã kiểm tra error, warning, full scan và temporary table.
- [ ] Đã dùng processlist/session để điều tra session.
- [ ] Đã phân biệt connection ID với Performance Schema THREAD_ID.
- [ ] Đã dùng schema_table_statistics và schema_index_statistics theo đúng câu hỏi.
- [ ] Không DROP index chỉ vì schema_unused_indexes liệt kê.
- [ ] Đã kiểm tra innodb_lock_waits và metadata lock waits riêng biệt.
- [ ] Đã xem wait events và file I/O khi cần.
- [ ] Đã hiểu buffer pool view chỉ là snapshot.
- [ ] Đã xác minh tên cột bằng DESCRIBE/SHOW CREATE VIEW.
- [ ] Đã kiểm tra quyền và SQL SECURITY trước khi cấp dashboard access.
- [ ] Đã bảo vệ query text và thông tin account/host.
- [ ] Đã đo delta nếu cần tốc độ theo thời gian.
- [ ] Đã xác minh giả thuyết bằng EXPLAIN, application trace và OS metrics.
- [ ] Đã không coi sys schema là công cụ tự sửa lỗi hoặc kho lịch sử.

## 26. Kết luận

sys schema là lớp quan sát tiện dụng để chẩn đoán MySQL. Nó biến nhiều dữ liệu chi tiết từ Performance Schema và INFORMATION_SCHEMA thành các view dễ đọc theo statement, session, schema, index, wait, I/O, buffer pool và lock. Bắt đầu từ câu hỏi vận hành rồi chọn view phù hợp sẽ hiệu quả hơn việc đọc mọi view một cách máy móc.

Các view không tự tạo dữ liệu telemetry; chúng phụ thuộc instrument, consumer, capacity và privilege của Performance Schema. Số liệu phần lớn là counter runtime, có thể reset hoặc mất khi restart, vì vậy cần lấy snapshot theo thời gian nếu muốn tính rate và dùng monitoring platform cho lịch sử dài hạn.

Hãy dùng sys schema để hình thành giả thuyết, sau đó xác minh bằng execution plan, slow log, application trace, lock diagnostics và OS metrics. Không xóa index chỉ từ danh sách unused, không KILL session chỉ từ một dòng output và không cấp quyền rộng cho dashboard. Một quy trình quan sát tốt phải có khoảng thời gian đo, ngữ cảnh workload, quyền tối thiểu và bằng chứng trước/sau mỗi thay đổi.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – The sys Schema](https://dev.mysql.com/doc/refman/8.4/en/sys-schema.html)
- [MySQL 8.4 Reference Manual – sys Schema Reference](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-reference.html)
- [MySQL 8.4 Reference Manual – Statement Analysis](https://dev.mysql.com/doc/refman/8.4/en/sys-statement-analysis.html)
- [MySQL 8.4 Reference Manual – Processlist](https://dev.mysql.com/doc/refman/8.4/en/sys-processlist.html)
- [MySQL 8.4 Reference Manual – Schema Table Statistics](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-table-statistics.html)
- [MySQL 8.4 Reference Manual – Schema Index Statistics](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-index-statistics.html)
- [MySQL 8.4 Reference Manual – InnoDB Lock Waits](https://dev.mysql.com/doc/refman/8.4/en/sys-innodb-lock-waits.html)
- [MySQL 8.4 Reference Manual – Schema Table Lock Waits](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-table-lock-waits.html)
- [MySQL 8.4 Reference Manual – Waits Global by Latency](https://dev.mysql.com/doc/refman/8.4/en/sys-waits-global-by-latency.html)
- [MySQL 8.4 Reference Manual – I/O Global by File by Latency](https://dev.mysql.com/doc/refman/8.4/en/sys-io-global-by-file-by-latency.html)
- [MySQL 8.4 Reference Manual – InnoDB Buffer Stats by Table](https://dev.mysql.com/doc/refman/8.4/en/sys-innodb-buffer-stats-by-table.html)
- [MySQL 8.4 Reference Manual – sys Schema Functions](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-functions.html)
- [MySQL 8.4 Reference Manual – sys Schema Procedures](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-procedures.html)
- [MySQL 8.4 Reference Manual – Performance Schema](https://dev.mysql.com/doc/refman/8.4/en/performance-schema.html)
- [MySQL 8.4 Reference Manual – Performance Schema Statement Digests](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-statement-digests.html)

