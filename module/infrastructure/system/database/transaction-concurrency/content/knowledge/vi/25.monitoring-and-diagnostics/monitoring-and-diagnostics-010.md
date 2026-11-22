# Thu thập kế hoạch thực thi và tham số liên quan đến tranh chấp

Khi một câu SQL chậm hoặc nhiều transaction chặn nhau, chỉ lưu câu lệnh là chưa đủ để giải thích nguyên nhân. Cùng một câu SQL có thể chọn index khác, quét số hàng khác nhau hoặc giữ khóa trong thời gian rất khác nhau tùy giá trị tham số, phân bố dữ liệu, thống kê optimizer, isolation level và trạng thái transaction.

Muốn điều tra tranh chấp đồng thời, cần nối được bốn loại bằng chứng:

1. **Kế hoạch thực thi:** optimizer dự định dùng index, join, scan và thứ tự truy cập nào; khi có thể, thu thập thêm số hàng và thời gian thực tế.
2. **Tham số thực tế:** giá trị và kiểu dữ liệu đã bind, phạm vi thời gian, tenant, danh sách ID hoặc các giá trị có độ chọn lọc khác nhau.
3. **Trạng thái transaction và wait:** connection nào chạy câu lệnh, transaction nào đang mở, câu lệnh có chờ khóa hay không và phiên nào đang chặn.
4. **Bối cảnh môi trường:** phiên bản database, schema/index, isolation level, autocommit, cấu hình session, thống kê và thời điểm thu thập.

Execution plan giải thích đường truy cập dự kiến; tham số giải thích vì sao đường truy cập đó được chọn; wait/lock telemetry cho biết tranh chấp thực sự xảy ra ở đâu. Không một nguồn đơn lẻ nào trả lời đầy đủ cả ba câu hỏi.

Bài này tập trung vào MySQL InnoDB và PostgreSQL, đồng thời trình bày quy trình chung để thu thập bằng chứng an toàn. Các lệnh và cột hệ thống có thể khác theo phiên bản; hãy xác nhận trên môi trường đang vận hành.

## 1. Vì sao cần lưu cả plan lẫn tham số?

Một câu truy vấn có thể được viết dưới dạng prepared statement:

```sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at, id
LIMIT ?;
```

Các lần gọi khác nhau chỉ thay bind values nhưng có thể có chi phí rất khác:

- `tenant_id = 10` có thể đại diện cho tenant rất lớn; `tenant_id = 900` chỉ có vài chục hàng.
- `status = 'PENDING'` có thể khớp 70% bảng; `status = 'CANCELLED'` chỉ khớp 0,1%.
- Khoảng ngày 1 giờ có thể quét ít hàng; khoảng 3 năm có thể quét hàng triệu hàng.
- `LIMIT 10` có thể dừng sớm nếu index cung cấp đúng thứ tự; nếu phải sort hoặc lọc nhiều ứng viên, engine vẫn phải đọc nhiều hơn.

Nếu chỉ lưu SQL với dấu `?`, không thể biết lần chạy gặp tranh chấp có tham số nào. Nếu chỉ lưu tham số mà không lưu plan, không biết optimizer đã dùng access path nào. Nếu có plan và tham số nhưng không có transaction/wait data, vẫn chưa biết thời gian chậm đến từ scan, I/O hay lock wait.

### Ví dụ về tham số có độ chọn lọc khác nhau

```sql
SELECT id
FROM orders
WHERE status = 'PENDING'
  AND tenant_id = 10;
```

Với tenant 10 có 2 triệu đơn hàng, truy vấn có thể đọc nhiều index entry. Với tenant 900 chỉ có 20 đơn hàng, cùng câu lệnh có thể hoàn tất rất nhanh. Nếu cả hai chạy `FOR UPDATE`, khác biệt số hàng và thời gian scan có thể làm lock footprint và thời gian giữ khóa khác nhau.

Một plan lấy từ dữ liệu test nhỏ không đủ đại diện cho production. Cần lưu kích thước và phân bố dữ liệu liên quan, không chỉ lưu DDL.

## 2. Phân biệt ước lượng, thực thi thực tế và thời gian chờ

Khi đọc plan, tách ba loại số liệu:

| Loại bằng chứng | Nó cho biết | Không tự chứng minh |
|---|---|---|
| Estimated plan | Optimizer dự kiến scan/index/join và ước lượng cardinality/cost | Số hàng thực tế, thời gian chạy thực tế hoặc lock wait |
| Actual execution statistics | Số hàng thực tế, số vòng lặp, thời gian, buffer/I/O được quan sát khi thực thi | Toàn bộ nguyên nhân của mọi wait hoặc hành vi dưới lịch đồng thời khác |
| Lock/wait telemetry | Transaction đang chờ gì, ai chặn, object/index/mode liên quan | Vì sao optimizer chọn plan đó hoặc query có đọc quá nhiều hàng hay không |

Một truy vấn có thể có plan tốt nhưng chờ khóa 20 giây. Một truy vấn có thể không chờ khóa nhưng đọc hàng triệu bản ghi do plan kém. Cũng có trường hợp scan rộng kéo dài thời gian giữ khóa, khiến các transaction khác chờ lâu hơn. Cần ghép ba loại bằng chứng theo cùng connection/transaction và thời điểm.

## 3. Thu thập thông tin trước khi lấy plan

Trước khi chạy `EXPLAIN`, ghi lại:

- Database engine và phiên bản đầy đủ.
- Database/schema và tên bảng liên quan.
- SQL template chính xác, gồm hint hoặc locking clause nếu có.
- Giá trị và kiểu dữ liệu của bind parameters.
- Connection ID/PID và transaction ID nếu có.
- Isolation level, autocommit, read-only và timeout của session.
- Thời điểm query bắt đầu, thời điểm hoàn tất hoặc thời điểm quan sát nó đang chờ.
- Số hàng ước lượng/kích thước bảng, index và phân bố dữ liệu quan trọng.
- Tải nền, số worker/connection và trạng thái replication nếu có ảnh hưởng.

Không thay tham số thật bằng một giá trị “đại diện” rồi coi plan thu được là plan của lần sự cố. Nếu phải ẩn danh, giữ đặc điểm chọn lọc của giá trị, ví dụ bucket cardinality hoặc hash ổn định, và ghi rõ phép biến đổi.

## 4. Ghi nhận tham số đã bind

Một prepared statement có hai phần: SQL template và các giá trị bind. Hãy lưu cả hai trong trace của ứng dụng hoặc instrumentation phù hợp.

Ví dụ log có cấu trúc:

```json
{
  "query_name": "find_pending_orders",
  "sql_template": "SELECT id FROM orders WHERE tenant_id = ? AND status = ? AND created_at >= ? AND created_at < ? ORDER BY created_at, id LIMIT ?",
  "parameters": [
    {"position": 1, "type": "BIGINT", "value": 10},
    {"position": 2, "type": "VARCHAR", "value": "PENDING"},
    {"position": 3, "type": "TIMESTAMP", "value": "2026-11-01T00:00:00Z"},
    {"position": 4, "type": "TIMESTAMP", "value": "2026-11-08T00:00:00Z"},
    {"position": 5, "type": "INTEGER", "value": 100}
  ],
  "connection_id": 812,
  "trace_id": "trace-example"
}
```

Đây là ví dụ minh họa, không phải dữ liệu của một lần chạy thực tế. Trong production, không nhất thiết ghi raw value của mọi tham số. Với dữ liệu nhạy cảm, lưu kiểu, nullness, độ dài, bucket/range, hash ổn định hoặc giá trị đã che. Mục tiêu là đủ thông tin để hiểu độ chọn lọc và tái tạo plan mà không làm lộ bí mật.

### Vì sao phải lưu kiểu dữ liệu?

Kiểu bind có thể ảnh hưởng đến so sánh và index usage. Ví dụ cột là `BIGINT` nhưng ứng dụng bind chuỗi, hoặc cột thời gian được truyền dưới dạng text không chuẩn, database có thể thực hiện conversion. Conversion trên cột được index có thể làm điều kiện kém sargable hoặc thay đổi ước lượng.

Ghi cả:

- Kiểu SQL/JDBC của từng tham số.
- Giá trị hoặc biểu diễn đã ẩn danh.
- Có phải `NULL` không.
- Với list/array: số phần tử và kiểu phần tử.
- Với range: biên dưới, biên trên và độ rộng khoảng.
- Với text: độ dài, collation/encoding liên quan nếu có.

### Không ghi secret vào log

Không ghi password, access token, số thẻ, dữ liệu cá nhân hoặc payload bí mật chỉ để tái tạo plan. Dùng dữ liệu synthetic trong môi trường test. Nếu phải điều tra production, áp dụng masking, quyền truy cập giới hạn và retention ngắn cho log có bind values.

## 5. MySQL InnoDB: thu thập estimated plan

Với MySQL, `EXPLAIN` cho biết kế hoạch optimizer dự kiến. Ví dụ:

```sql
EXPLAIN FORMAT=JSON
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PENDING'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at < '2026-11-08 00:00:00'
ORDER BY created_at, id
LIMIT 100;
```

Các trường đáng chú ý:

- `key`: index optimizer chọn.
- `possible_keys`: index có thể được cân nhắc.
- `access_type`/`type`: cách truy cập như `const`, `eq_ref`, `ref`, `range`, `index` hoặc `ALL`.
- `rows`: số hàng optimizer ước lượng phải đọc ở bước đó.
- `filtered`: tỷ lệ hàng ước lượng còn lại sau điều kiện lọc.
- `used_key_parts`: các cột/prefix của composite index được dùng.
- `attached_condition` và `index_condition`: điều kiện được áp dụng trong từng giai đoạn.
- Thông tin `ordering_operation`/`using_filesort`: có cần sort bổ sung hay không.

Ví dụ một index `(tenant_id, status, created_at, id)` có thể hỗ trợ hai equality predicate đầu rồi range theo `created_at`. Nhưng plan thực tế còn phụ thuộc phân bố dữ liệu, thống kê và phiên bản optimizer.

### Lưu cả DDL và index

```sql
SHOW CREATE TABLE orders;
SHOW INDEX FROM orders;
```

Không thể giải thích plan nếu thiếu index definitions. Lưu engine, primary key, unique/secondary index, foreign key và trigger có liên quan. Nếu thống kê optimizer được cập nhật trước hoặc sau run, ghi lại thời điểm và thao tác cập nhật thống kê.

## 6. MySQL: lấy actual execution statistics an toàn

MySQL 8.0.18 trở lên có `EXPLAIN ANALYZE` cho các câu `SELECT` được hỗ trợ. Nó thực thi câu truy vấn và báo actual time, actual rows, loops cùng thời gian của các iterator:

```sql
EXPLAIN ANALYZE
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PENDING'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at < '2026-11-08 00:00:00'
ORDER BY created_at, id
LIMIT 100;
```

Vì `EXPLAIN ANALYZE` thực sự chạy câu lệnh, không dùng tùy tiện trên production. Đặc biệt tránh chạy với câu có locking clause như `FOR UPDATE` hoặc truy vấn có tác dụng phụ trong lúc điều tra nếu chưa đánh giá tác động. Chạy trên bản sao dữ liệu hoặc môi trường kiểm thử với transaction và timeout được kiểm soát.

Đọc actual rows cùng estimated rows:

- Nếu estimated rows rất nhỏ nhưng actual rows lớn, thống kê hoặc giả định phân bố có thể sai.
- Nếu một iterator có `loops` lớn, tổng công việc có thể lớn hơn nhìn từ một vòng lặp.
- Nếu thời gian tăng ở một iterator, đó là nơi cần xem scan, join, sort hoặc I/O.
- Nếu actual plan nhanh nhưng thời gian ứng dụng rất dài, hãy kiểm tra lock wait, network, connection pool và thời gian đọc kết quả.

`EXPLAIN ANALYZE` không thay thế wait telemetry. Một lần chạy đo actual plan có thể không gặp cùng lock contention như lần sự cố.

## 7. MySQL: xem plan của connection đang chạy

Nếu một query vẫn đang chạy và MySQL hỗ trợ cú pháp tương ứng, có thể yêu cầu plan của connection:

```sql
EXPLAIN FORMAT=JSON FOR CONNECTION 812;
```

Thay `812` bằng connection ID lấy từ `SHOW FULL PROCESSLIST` hoặc instrumentation. Lệnh này hữu ích khi muốn xem statement đang thực thi mà không tự chạy lại SQL với tham số khác. Quyền `PROCESS` hoặc quyền phù hợp có thể cần thiết; cú pháp/khả năng phụ thuộc phiên bản.

Nếu query đã kết thúc hoặc connection đã chuyển sang statement khác, plan của statement cũ có thể không còn lấy được. Vì vậy, hãy lưu connection ID, SQL và thời điểm ngay khi phát hiện sự cố.

## 8. MySQL Performance Schema: lịch sử câu lệnh

`performance_schema` có thể lưu event statement hiện tại và lịch sử gần đây. Bảng hữu ích gồm:

- `events_statements_current`: statement đang chạy trên thread.
- `events_statements_history`: các statement gần đây của từng thread.
- `events_statements_history_long`: lịch sử gần đây trên toàn hệ thống, nếu consumer được bật.
- `events_statements_summary_by_digest`: số liệu tổng hợp theo query digest.

Ví dụ đọc lịch sử:

```sql
SELECT
    THREAD_ID,
    EVENT_ID,
    END_EVENT_ID,
    EVENT_NAME,
    CURRENT_SCHEMA,
    SQL_TEXT,
    DIGEST,
    DIGEST_TEXT,
    TIMER_WAIT,
    LOCK_TIME,
    ROWS_EXAMINED,
    ROWS_SENT,
    ROWS_AFFECTED,
    MYSQL_ERRNO,
    RETURNED_SQLSTATE
FROM performance_schema.events_statements_history_long
WHERE SQL_TEXT IS NOT NULL
ORDER BY TIMER_START DESC
LIMIT 100;
```

Các timer trong Performance Schema thường dùng đơn vị picosecond; cần chuyển đổi đúng khi tạo dashboard. `LOCK_TIME` là số liệu lock time của statement theo instrumentation, không nên dùng một mình để kết luận chính xác thời gian chờ row lock InnoDB. Với row lock wait, đối chiếu `data_lock_waits` và trạng thái transaction.

Lịch sử là buffer có giới hạn; event cũ có thể bị ghi đè. Consumer cũng có thể đang tắt hoặc kích thước history không đủ. Nếu cần bằng chứng cho sự cố, thu thập sớm và kiểm tra trạng thái consumer trước khi kết luận “không có statement history”.

### Xem query digest có thời gian và số hàng lớn

```sql
SELECT
    SCHEMA_NAME,
    DIGEST,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_TIMER_WAIT,
    AVG_TIMER_WAIT,
    SUM_LOCK_TIME,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_ROWS_AFFECTED,
    FIRST_SEEN,
    LAST_SEEN
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Digest gộp nhiều lần chạy có literal khác nhau thành một mẫu chuẩn hóa. Đây là cách tìm query family tốn thời gian hoặc đọc nhiều hàng. Nhưng số liệu tổng hợp không cho biết một lần chạy cụ thể dùng bind values nào hoặc transaction nào bị chặn.

## 9. MySQL: nối statement với transaction và lock wait

Khi thấy một statement chậm, hãy xác định connection ID và thread ID. Sau đó đối chiếu:

```sql
SELECT
    trx_id,
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS transaction_age_seconds,
    trx_wait_started,
    trx_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Lấy process/thread data:

```sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_STATE,
    PROCESSLIST_TIME,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND';
```

Rồi lấy row lock wait:

```sql
SELECT
    waits.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    waits.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    waiting_thread.PROCESSLIST_ID AS waiting_connection,
    blocking_thread.PROCESSLIST_ID AS blocking_connection,
    requested.OBJECT_SCHEMA,
    requested.OBJECT_NAME,
    requested.INDEX_NAME AS waiting_index,
    requested.LOCK_MODE AS waiting_mode,
    requested.LOCK_DATA AS waiting_key,
    blocking.INDEX_NAME AS blocking_index,
    blocking.LOCK_MODE AS blocking_mode,
    blocking.LOCK_DATA AS blocking_key
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS requested
  ON requested.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking
  ON blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS waiting_thread
  ON waiting_thread.THREAD_ID = waits.REQUESTING_THREAD_ID
LEFT JOIN performance_schema.threads AS blocking_thread
  ON blocking_thread.THREAD_ID = waits.BLOCKING_THREAD_ID;
```

Những view này trả lời các câu hỏi khác nhau:

- `events_statements_*`: câu SQL nào chạy, đọc bao nhiêu hàng, mất bao lâu theo instrumentation?
- `innodb_trx`: transaction nào đang mở, bắt đầu khi nào, có đang chờ hay không?
- `data_locks`/`data_lock_waits`: index/record nào đang bị khóa và quan hệ waiting/blocking là gì?
- `threads`: thread ID tương ứng với connection ID nào?

Nếu cần chờ metadata lock, xem `performance_schema.metadata_locks`; `data_lock_waits` không đại diện cho mọi loại wait. Nếu connection đã `Sleep`, `PROCESSLIST_INFO` có thể rỗng nhưng transaction vẫn mở.

## 10. MySQL: tham số prepared statement có thể không xuất hiện trong SQL_TEXT

Với prepared statement, SQL text có thể giữ placeholder `?`. Performance Schema digest thường chuẩn hóa literal để gộp query family. Không giả định rằng `SQL_TEXT` hoặc `DIGEST_TEXT` luôn chứa giá trị thực tế mà ứng dụng đã bind.

Để điều tra parameter-sensitive plan:

1. Thu SQL template từ Performance Schema hoặc application trace.
2. Lấy bind values và kiểu từ instrumentation của ứng dụng/driver nếu có.
3. Ghi thời điểm, connection ID và transaction ID.
4. Tái tạo plan với các giá trị đại diện trong môi trường an toàn.
5. So sánh giá trị có độ chọn lọc cao/thấp, range hẹp/rộng và NULL/non-NULL.

General query log có thể ghi nhiều câu lệnh hơn nhưng tạo overhead và có nguy cơ ghi dữ liệu nhạy cảm. Không bật rộng trên production chỉ để tìm bind values mà chưa đánh giá dung lượng, bảo mật và tác động hiệu năng. Ưu tiên tracing có cấu trúc với masking.

## 11. PostgreSQL: thu thập estimated plan

PostgreSQL `EXPLAIN` mặc định lập kế hoạch nhưng không chạy câu lệnh:

```sql
EXPLAIN (FORMAT JSON)
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PENDING'
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND created_at < TIMESTAMPTZ '2026-11-08 00:00:00+00'
ORDER BY created_at, id
LIMIT 100;
```

Các trường quan trọng:

- `Node Type`: kiểu node như `Index Scan`, `Bitmap Heap Scan`, `Seq Scan`, `Nested Loop`, `Hash Join` hoặc `Sort`.
- `Relation Name` và `Index Name`: bảng và index liên quan.
- `Plan Rows`/`Plan Width`: ước lượng số hàng và kích thước hàng.
- `Startup Cost`/`Total Cost`: cost tương đối mà optimizer dùng để so sánh plan, không phải thời gian mili giây.
- `Index Cond`, `Filter`, `Recheck Cond`: điều kiện được dùng trong index hoặc lọc sau đó.
- `Sort Key`: các cột cần sắp xếp.
- `Join Type`/`Join Filter`: cách kết hợp các quan hệ.

Plan JSON thuận tiện để lưu artifact và diff giữa các lần chạy. Cần giữ cả SQL, bind values, phiên bản PostgreSQL và các setting ảnh hưởng planner.

## 12. PostgreSQL: actual plan bằng EXPLAIN ANALYZE

Để đo thực thi thực tế:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, VERBOSE, FORMAT JSON)
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PENDING'
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND created_at < TIMESTAMPTZ '2026-11-08 00:00:00+00'
ORDER BY created_at, id
LIMIT 100;
```

`ANALYZE` thực sự thực thi câu lệnh. `BUFFERS` cho biết hoạt động buffer hit/read/dirtied/written; `SETTINGS` hiển thị một số planner settings khác default; `VERBOSE` bổ sung thông tin node/column. Phiên bản PostgreSQL quyết định tùy chọn nào được hỗ trợ.

Đối chiếu `Plan Rows` với `Actual Rows` và `Actual Loops`:

- Ước lượng thấp hơn thực tế nhiều có thể khiến optimizer chọn join hoặc index không phù hợp.
- `Actual Rows × Loops` giúp hiểu tổng số hàng qua một node lặp nhiều lần.
- `Buffers` giúp phân biệt công việc cache và đọc storage ở mức phù hợp.
- `Sort Method` và temporary blocks có thể cho thấy sort spill.
- `Rows Removed by Filter` cao cho thấy nhiều hàng được đọc rồi loại bỏ.

### Cảnh báo về câu lệnh có tác dụng phụ

`EXPLAIN ANALYZE` thực thi câu lệnh. Với `UPDATE`, `DELETE`, `INSERT` hoặc câu lệnh gọi function có tác dụng phụ, dữ liệu/thao tác thực sự có thể xảy ra. Nếu cần đo DML trong môi trường test, dùng transaction rõ ràng và rollback sau khi thu thập, nhưng nhớ rằng rollback không nhất thiết đảo ngược sequence advancement hoặc tác dụng phụ bên ngoài do trigger/function gọi ra.

Với locking read như `SELECT ... FOR UPDATE`, việc chạy `EXPLAIN ANALYZE` có thể lấy khóa và ảnh hưởng các session khác. Không chạy trực tiếp trên production chỉ để lấy plan. Dùng `EXPLAIN` không thực thi trước, hoặc tái tạo trên môi trường an toàn.

## 13. PostgreSQL: prepared statement và plan phụ thuộc tham số

PostgreSQL có thể chọn custom plan dựa trên giá trị tham số hoặc generic plan dùng chung cho nhiều lần thực thi prepared statement. Điều này quan trọng khi độ chọn lọc của tham số biến thiên lớn.

Ví dụ:

```sql
PREPARE find_orders(bigint, text, timestamptz, timestamptz) AS
SELECT id
FROM orders
WHERE tenant_id = $1
  AND status = $2
  AND created_at >= $3
  AND created_at < $4
ORDER BY created_at, id
LIMIT 100;

EXPLAIN (FORMAT JSON)
EXECUTE find_orders(
    10,
    'PENDING',
    TIMESTAMPTZ '2026-11-01 00:00:00+00',
    TIMESTAMPTZ '2026-11-08 00:00:00+00'
);
```

`EXPLAIN EXECUTE` cho biết plan của prepared statement trong session hiện tại với các tham số đưa vào. PostgreSQL có thể chuyển từ custom plan sang generic plan tùy chi phí và lịch sử thực thi. Vì vậy, plan khi chạy trực tiếp literal có thể khác plan của prepared statement trong ứng dụng.

`plan_cache_mode` có thể dùng trong môi trường thử nghiệm để khảo sát `auto`, `force_custom_plan` và `force_generic_plan`. Không đổi setting production chỉ để làm một lần đo mà chưa hiểu tác động lên workload.

## 14. PostgreSQL: pg_stat_statements cho query family

Extension `pg_stat_statements` tổng hợp thống kê theo query identity và chuẩn hóa literal/parameter. Nó hữu ích để tìm query family có tổng thời gian, thời gian trung bình, số lần gọi hoặc số hàng bất thường.

Ví dụ:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    min_exec_time,
    max_exec_time,
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

Các cột có thể khác theo phiên bản extension. `pg_stat_statements` lưu query đã chuẩn hóa; nó thường không lưu đầy đủ bind values của từng lần thực thi. Vì vậy, dùng nó để tìm mẫu query cần điều tra, rồi ghép với application trace hoặc log có parameter metadata.

Extension cần được cài đặt và cấu hình qua `shared_preload_libraries` trong nhiều triển khai, sau đó tạo extension trong database. Việc bật có chi phí và giới hạn bộ nhớ; cần theo dõi và cấu hình theo hướng dẫn của phiên bản đang dùng.

## 15. PostgreSQL: nối query với transaction và lock wait

`pg_stat_activity` cho biết backend đang chạy gì và đang chờ loại event nào:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    query_start,
    state_change,
    wait_event_type,
    wait_event,
    backend_xmin,
    query_id,
    left(query, 300) AS query_text
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

`query_id` có sẵn khi query identifier được bật và phiên bản hỗ trợ; nếu không có, có thể bỏ cột này. `query` có thể bị cắt theo `track_activity_query_size`. `state = 'idle in transaction'` nghĩa là backend không chạy query hiện tại nhưng transaction còn mở.

Tìm blocker trực tiếp:

```sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.query_start AS waiting_query_start,
    waiting.xact_start AS waiting_xact_start,
    waiting.wait_event_type,
    waiting.wait_event,
    left(waiting.query, 200) AS waiting_query,
    blocker.pid AS blocking_pid,
    blocker.state AS blocking_state,
    blocker.xact_start AS blocking_xact_start,
    left(blocker.query, 200) AS blocking_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS p(blocking_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocking_pid;
```

`pg_blocking_pids()` xác định backend chặn trực tiếp. Nếu blocker cũng đang chờ một backend khác, tiếp tục truy vết để tìm gốc chuỗi. Với deadlock, cần giữ server log chứa deadlock report; một snapshot `pg_stat_activity` có thể được lấy sau khi deadlock detector đã rollback nạn nhân nên không còn thấy chu trình.

### Xem lock object và mode

```sql
SELECT
    l.pid,
    l.locktype,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple,
    l.transactionid,
    l.mode,
    l.granted,
    a.state,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 200) AS query_text
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
  ON a.pid = l.pid
ORDER BY l.granted, l.pid;
```

Không phải mọi PostgreSQL lock đều là row lock trực tiếp; nhiều row-level lock được thể hiện qua transaction ID và có thể cần diễn giải cùng `pg_blocking_pids()`. Không kết luận từ một dòng `pg_locks` đơn lẻ.

## 16. PostgreSQL: log query, plan và parameter

Các nguồn log có thể bổ sung cho `pg_stat_activity`:

- `log_min_duration_statement`: ghi statement vượt ngưỡng thời gian.
- `log_lock_waits`: ghi thông tin khi lock wait vượt `deadlock_timeout`.
- `deadlock_timeout`: khoảng chờ trước khi kiểm tra deadlock; cũng ảnh hưởng thời điểm log lock wait.
- `auto_explain`: có thể ghi execution plan của statement vượt ngưỡng cấu hình.
- `log_line_prefix`: thêm PID, user, database, application name, session ID hoặc transaction ID phù hợp.

Ví dụ định hướng cấu hình, cần kiểm tra quyền và phiên bản trước khi áp dụng:

```sql
SHOW log_min_duration_statement;
SHOW log_lock_waits;
SHOW deadlock_timeout;
SHOW log_line_prefix;
```

`auto_explain` có thể ghi plan của câu SQL chậm mà không cần chạy lại câu lệnh sau sự cố. Cần cân nhắc `auto_explain.log_analyze`, `log_buffers`, `log_timing` và ngưỡng duration vì thu thập actual timing có overhead.

PostgreSQL có các setting kiểm soát lượng bind parameter ghi trong log ở những phiên bản hỗ trợ, ví dụ `log_parameter_max_length` và `log_parameter_max_length_on_error`. Ghi parameter có thể làm lộ thông tin nhạy cảm và tăng dung lượng log. Chỉ bật theo chính sách bảo mật, giới hạn độ dài và quyền truy cập; không mặc định log toàn bộ giá trị.

## 17. Query digest và query instance là hai cấp độ khác nhau

Digest gom các câu SQL có cùng cấu trúc thành một query family. Nó giúp xếp hạng workload nhưng có thể che đi khác biệt giữa các tham số.

Ví dụ hai lần chạy:

```sql
SELECT * FROM orders WHERE tenant_id = 10 AND status = 'PENDING';
SELECT * FROM orders WHERE tenant_id = 900 AND status = 'PENDING';
```

Có thể thuộc cùng digest nhưng tenant 10 có hàng triệu bản ghi còn tenant 900 có rất ít. Số liệu tổng hợp có thể cho thấy query family chậm, nhưng để giải thích một spike cụ thể phải tìm query instance, tham số, thời điểm và connection.

Khi phân tích, luôn phân biệt:

- **Query family:** mẫu SQL chuẩn hóa và số liệu tổng hợp.
- **Query instance:** một lần thực thi cụ thể với bind values, connection, thời gian và kết quả riêng.
- **Transaction:** đơn vị có thể chứa nhiều query instance và giữ khóa/snapshot qua các câu lệnh.

Một transaction dài có thể chứa nhiều câu SQL ngắn. Nếu chỉ xem slow query log, có thể bỏ sót khoảng thời gian ứng dụng idle nhưng transaction vẫn giữ khóa.

## 18. Tham số và data skew ảnh hưởng plan ra sao?

Optimizer dựa trên thống kê để ước lượng số hàng phù hợp với predicate. Nếu dữ liệu phân bố lệch, cùng một predicate có thể có selectivity rất khác tùy giá trị.

Các dấu hiệu nên thu thập:

- Giá trị có tần suất rất cao hoặc rất thấp.
- Tenant/partition lớn nhất và nhỏ nhất.
- Range thời gian ngắn so với dài.
- List parameter có số phần tử thay đổi.
- Giá trị NULL hoặc sentinel.
- Prefix text phổ biến hoặc hiếm.
- Join key có skew hoặc nhiều giá trị lặp.

Khi actual rows khác xa estimated rows, có thể cần cập nhật hoặc cải thiện thống kê, tạo histogram/extended statistics nếu hệ quản trị hỗ trợ, hoặc điều chỉnh index/query. Không thêm index chỉ dựa trên một lần chạy; so sánh nhiều tham số đại diện.

### MySQL

MySQL có histogram statistics cho một số cột và `ANALYZE TABLE` để cập nhật thống kê. Cần lưu thời điểm `ANALYZE TABLE`, vì plan có thể thay đổi sau cập nhật. Histogram không thay thế mọi loại thống kê đa cột; correlation giữa `tenant_id` và `status` có thể khiến ước lượng vẫn lệch.

### PostgreSQL

PostgreSQL dùng statistics target, histogram, most-common-values và extended statistics cho một số tương quan cột. `ANALYZE` cập nhật thống kê. Prepared statement có thể dùng generic/custom plan; tham số có skew lớn làm khác biệt này đáng quan tâm.

## 19. Vì sao plan và wait phải được chụp gần cùng thời điểm?

Plan được lấy trước khi query chạy có thể không còn đại diện nếu:

- Statistics được cập nhật giữa hai lần.
- Index được tạo/xóa hoặc schema thay đổi.
- Bind values khác.
- Prepared statement dùng generic plan thay cho custom plan.
- Optimizer settings hoặc session variables khác.
- Dữ liệu thay đổi lớn hoặc phân bố khác.
- Query thực tế chạy qua connection khác với session dùng để `EXPLAIN`.

Wait telemetry cũng là snapshot tại một thời điểm. Nếu lấy `data_lock_waits` sau khi blocker commit, quan hệ chờ đã biến mất. Nếu lấy `pg_stat_activity` sau khi statement kết thúc, query text có thể đã đổi. Vì vậy, công cụ giám sát nên thu thập theo chu kỳ phù hợp hoặc có event-driven tracing, đồng thời lưu timestamp và connection identity.

## 20. Tạo correlation ID xuyên suốt ứng dụng và database

Một request nghiệp vụ có thể mở nhiều connection hoặc thực hiện nhiều câu SQL. Cần correlation ID để nối application trace với database telemetry.

Trong ứng dụng, ghi:

- `trace_id`/`request_id` ổn định.
- Operation name và endpoint/job name.
- Connection ID/PID sau khi lấy connection.
- Transaction begin/commit/rollback timestamp.
- Query name, SQL template, parameter metadata và query duration.
- SQLSTATE/vendor code và retry attempt.

MySQL có thể dùng session attribute, query comment hoặc connection metadata tùy công cụ; PostgreSQL có `application_name` trong connection/session để nhận diện dịch vụ và worker. Không dựa vào comment làm correlation duy nhất vì proxy/driver có thể bỏ comment hoặc log không giữ nguyên.

Ví dụ PostgreSQL:

```sql
SET application_name = 'orders-api trace=trace-example';
```

Trong production, dùng giá trị ngắn, có định dạng và không chứa dữ liệu cá nhân. Với connection pool, cần reset `application_name` khi trả connection để request sau không thừa hưởng trace cũ.

## 21. Bằng chứng cần lưu cho một sự cố tranh chấp

Một gói evidence tối thiểu nên chứa:

| Nhóm | Artifact |
|---|---|
| Query | SQL template nguyên văn, query digest/query ID, statement timestamp |
| Parameters | Bind type/value đã mask, nullness, range/list size, tenant hoặc cardinality bucket |
| Plan | Estimated plan, actual plan nếu an toàn, schema/index và statistics timestamp |
| Session | Connection ID/PID, user, application, database, isolation level, autocommit và timeout |
| Transaction | Transaction ID, start time, state, rows locked/modified nếu có |
| Wait | Waiting transaction, blocking transaction, lock object/index/mode, wait duration |
| Outcome | Row count, SQLSTATE/vendor error, commit/rollback, dữ liệu cuối |
| Environment | Database version, driver, application build, host, time zone và tải nền |

Không phải mọi sự cố đều có actual plan hoặc parameter raw. Ghi rõ artifact nào không thu thập được và lý do, ví dụ query đã kết thúc trước khi lấy plan hoặc quyền quan sát bị giới hạn. Không thay “không có dữ liệu” bằng “không có vấn đề”.

## 22. Quy trình điều tra từ query chậm đến nguyên nhân tranh chấp

1. Xác định request/trace ID và câu SQL cụ thể.
2. Tìm connection ID/PID, transaction ID và timestamp của lần chạy.
3. Thu SQL template cùng bind values/kiểu dữ liệu đã mask.
4. Xác nhận isolation level, autocommit và các session settings.
5. Lấy estimated plan; nếu cần actual plan, thực hiện trong môi trường an toàn.
6. So sánh estimated rows với actual rows, index được chọn, rows examined và sort/join.
7. Kiểm tra transaction age và trạng thái idle/active.
8. Thu wait event, lock rows và blocker relationship tại thời điểm query đang chờ.
9. So sánh tham số của run chậm với run bình thường thuộc cùng query digest.
10. Kiểm tra data skew, statistics, index và plan cache.
11. Tái tạo với tham số tương ứng trên dữ liệu an toàn và giữ lại execution plan.
12. Sau khi thay query/index/config, đo lại plan, wait time và tính đúng đắn dưới tải cạnh tranh.

Sơ đồ tổng quát:

```text
Query chậm hoặc transaction bị chặn
                 |
                 v
        Tìm query instance/trace
                 |
                 v
     Lưu SQL template + bind values
                 |
                 v
       Lấy plan và index được chọn
                 |
                 v
      Đối chiếu estimated/actual rows
                 |
                 v
       Có lock wait tại thời điểm đó?
           /                 \
         Có                   Không
         |                      |
         v                      v
  Tìm blocker, object,       Phân tích scan, join,
  lock mode và transaction  sort, I/O, CPU, network
         |                      |
         +----------+-----------+
                    |
                    v
       So sánh tham số và data skew
                    |
                    v
      Tái lập an toàn và đo lại
```

## 23. So sánh một lần chạy chậm với lần chạy bình thường

Đừng chỉ so sánh thời gian tổng. So sánh cùng query family theo các chiều:

| Chỉ số | Run bình thường | Run chậm | Ý nghĩa có thể |
|---|---|---|---|
| Bind values | Tenant nhỏ, range ngắn | Tenant lớn, range rộng | Data volume khác |
| Index/access type | `range`/`ref` | `ALL` hoặc index khác | Plan/access path thay đổi |
| Estimated rows | Gần actual | Sai lệch lớn | Statistics hoặc skew |
| Actual rows examined | Ít | Rất nhiều | Scan rộng hoặc filter muộn |
| Lock wait | Không có | Chờ blocker lâu | Contention trực tiếp |
| Transaction age | Ngắn | Dài/idle | Khóa có thể bị giữ lâu |
| Rows returned | Tương tự | Tương tự | Output nhỏ không đồng nghĩa scan nhỏ |
| Buffer/I/O | Cache hit cao | Physical reads/temp spill cao | Áp lực I/O hoặc working set |

Nếu thời gian tăng nhưng plan, actual rows và buffers tương tự, trong khi wait duration tăng, nguyên nhân có thể là contention. Nếu wait bằng 0 nhưng rows examined tăng mạnh, cần xem query plan hoặc tham số. Cả hai có thể cùng xảy ra.

## 24. Cẩn trọng với EXPLAIN ANALYZE trong hệ thống đang có tải

`EXPLAIN ANALYZE` không phải lệnh chỉ đọc metadata; nó thực thi câu SQL. Với SELECT thông thường, nó vẫn tiêu thụ CPU/I/O và có thể cạnh tranh tài nguyên. Với locking read, nó có thể lấy khóa. Với DML, nó thay đổi dữ liệu trừ khi được rollback; rollback cũng không đảo ngược mọi tác dụng phụ bên ngoài.

Quy tắc thực hành:

- Dùng `EXPLAIN` trước để lấy estimated plan.
- Không chạy actual analyze trên câu DML production chỉ để đo plan.
- Không chạy `SELECT ... FOR UPDATE` trong production chỉ để xem lock footprint.
- Tái tạo trên staging/clone với schema, statistics và dữ liệu gần tương đương.
- Đặt statement timeout và giới hạn concurrency cho phép đo.
- Nếu phải chạy production, có phê duyệt vận hành và hiểu rõ tác động của query.
- Ghi rõ câu lệnh có được thực thi hay chỉ được lập kế hoạch.

## 25. Log parameter: lợi ích và rủi ro

Parameter logging giúp tái tạo plan nhưng có thể làm lộ:

- Email, số điện thoại, địa chỉ và định danh người dùng.
- Token, secret hoặc mã xác thực.
- Nội dung tìm kiếm hoặc thông tin nghiệp vụ nhạy cảm.
- Dữ liệu thanh toán hoặc thông tin tài chính.

Nên ưu tiên structured tracing trong ứng dụng với allowlist query name và parameter metadata. Có thể lưu bucket thay vì raw value, ví dụ `tenant_size_bucket=large`, `date_range_days=365`, `id_list_size=500`. Với các giá trị cần tái lập chính xác, dùng dữ liệu synthetic hoặc bản đã mask trong môi trường kiểm thử.

Nếu bật database logging tạm thời, đặt duration ngắn, giới hạn phạm vi, bảo vệ quyền đọc log và có ngày kết thúc rõ ràng. Sau điều tra, tắt cấu hình bổ sung và tuân thủ retention policy.

## 26. Các sai lầm thường gặp khi thu thập plan và parameters

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ lưu SQL có placeholder | Không biết giá trị nào gây skew hoặc plan khác | Lưu bind type/value đã mask trong trace |
| Chỉ lưu literal query chạy tay | Có thể không giống prepared statement trong ứng dụng | Lưu SQL template và cách bind thực tế |
| Dùng một plan từ staging nhỏ | Cardinality và statistics khác production | Lưu dữ liệu phân bố và plan theo tham số đại diện |
| Chỉ nhìn query digest | Mất khác biệt giữa các lần chạy cùng mẫu | Correlate digest với query instance/trace |
| Chỉ nhìn EXPLAIN | Không biết wait/blocker thực tế | Thu transaction và lock telemetry đồng thời |
| Coi `LOCK_TIME` là row lock wait chính xác | Có thể phân loại sai nguồn chậm | Đối chiếu data lock wait views và wait events |
| Chạy EXPLAIN ANALYZE trên DML production | Có thể thực sự sửa dữ liệu hoặc tạo tải | Dùng môi trường an toàn, transaction rollback có kiểm soát |
| Lấy plan sau khi query đã kết thúc | Có thể mất statement/parameter instance ban đầu | Thu trace và plan sớm; dùng connection correlation |
| Không lưu session settings | Không tái tạo được isolation/timeout/plan behavior | Lưu settings của chính session chạy query |
| Log toàn bộ bind values | Rò rỉ dữ liệu nhạy cảm, log phình to | Mask, allowlist, bucket và giới hạn retention |

## 27. Mẫu hồ sơ query contention

Có thể lưu một hồ sơ theo cấu trúc sau:

```markdown
# Query contention evidence

## Identity
- Incident/run ID:
- Trace/request ID:
- Query name/digest/query ID:
- Database and version:
- Application build:
- Timestamp and time zone:

## Session and transaction
- Connection ID/PID:
- Transaction ID:
- Isolation level:
- Autocommit:
- Transaction start:
- Query start/end:
- Session timeout settings:

## SQL and parameters
- SQL template:
- Bind parameter positions/types:
- Sanitized values or selectivity buckets:
- Prepared statement/generic-custom plan details:

## Schema and plan
- Table DDL/indexes:
- Statistics timestamp:
- Estimated plan artifact:
- Actual plan artifact (if safely collected):
- Estimated vs actual rows:
- Rows examined/sent:
- Buffers/I/O/sort details:

## Contention
- Wait event/type:
- Waiting transaction:
- Blocking transaction:
- Lock object/index/mode:
- Wait duration:
- Blocker state and transaction age:

## Outcome
- Rows affected:
- SQLSTATE/vendor error:
- Commit/rollback result:
- Final data verification:
- Difference from a normal run:

## Limitations and privacy
- Missing evidence:
- Masking applied:
- Collection window/retention:
```

Nếu một trường không áp dụng, ghi `N/A` cùng lý do. Nếu dữ liệu không thu thập được, ghi `not captured` thay vì để người đọc hiểu nhầm là giá trị rỗng có ý nghĩa.

## 28. Checklist thực hiện một lần thu thập

1. Xác định query instance, trace ID và connection ID.
2. Lưu SQL template và bind parameter metadata đã mask.
3. Ghi database version, schema, index và session settings.
4. Lấy estimated plan cho đúng câu lệnh và tham số.
5. Nếu cần actual plan, đánh giá tác động và chạy trong môi trường an toàn.
6. Ghi estimated rows, actual rows, loops, buffers/I/O và rows examined.
7. Thu transaction age, trạng thái active/idle và isolation level.
8. Thu lock/wait relation cùng blocker, object, index và mode.
9. Correlate query event với transaction và application trace.
10. So sánh run chậm với run bình thường có tham số tương ứng.
11. Lưu artifact nguyên văn và timestamp; che dữ liệu nhạy cảm.
12. Ghi rõ những nguồn không có dữ liệu hoặc đã hết thời gian lưu.

## 29. Tự kiểm tra

**Vì sao SQL template có dấu `?` chưa đủ để tái tạo plan?**

Vì giá trị và kiểu bind ảnh hưởng selectivity, implicit conversion và plan. Cần biết tham số của lần chạy cụ thể, ít nhất dưới dạng đã mask hoặc bucket có ý nghĩa.

**Query digest cho biết điều gì và không cho biết điều gì?**

Digest gom các câu cùng cấu trúc để xem thống kê query family. Nó không tự xác định bind values, connection, transaction hay wait của một lần chạy cụ thể.

**`EXPLAIN ANALYZE` khác `EXPLAIN` như thế nào?**

`EXPLAIN` lấy kế hoạch mà không thực thi câu lệnh. `EXPLAIN ANALYZE` thực thi câu lệnh để đo số hàng/thời gian thực tế, vì vậy có thể tiêu thụ tài nguyên, lấy khóa hoặc thay đổi dữ liệu tùy statement.

**Vì sao một plan tốt vẫn có thể chậm do tranh chấp?**

Plan có thể tìm đúng hàng nhanh nhưng transaction vẫn phải chờ khóa do phiên khác giữ. Cần xem wait telemetry và blocker relationship.

**Vì sao phải lưu isolation level và autocommit cùng plan?**

Chúng ảnh hưởng visibility, loại locking read, thời gian sống của transaction và khóa. Cùng câu SQL/index có thể có hành vi đồng thời khác khi session settings khác nhau.

**Nếu `pg_stat_statements` cho thấy query family chậm, có thể biết giá trị bind nào gây chậm không?**

Không từ số liệu digest đơn thuần. Cần nối với application trace hoặc log parameter đã mask để tìm query instance và tham số cụ thể.

**Có thể chạy `EXPLAIN ANALYZE SELECT ... FOR UPDATE` trên production để xem khóa không?**

Không nên chạy tùy tiện. Lệnh thực thi locking read có thể lấy khóa và ảnh hưởng transaction khác. Hãy dùng estimated plan trước và tái tạo trên môi trường an toàn.

**Không thấy dòng trong `data_lock_waits` có chứng minh query không bị chặn không?**

Không. Có thể lấy mẫu sai thời điểm, thiếu quyền, hoặc query đang chờ metadata lock hay loại wait khác. Phải xem nguồn telemetry phù hợp và thời điểm thu thập.

Thu thập plan và tham số chỉ có giá trị khi được nối với transaction và wait của đúng lần chạy. Hãy giữ **SQL template, bind values/kiểu đã mask, plan, schema/statistics, connection identity và lock telemetry** trong cùng một hồ sơ. Cách làm này giúp phân biệt plan kém với tham số lệch phân bố, lock wait với thời gian thực thi, và query chậm với transaction mở lâu; đồng thời tạo bằng chứng đủ rõ để tái lập và đánh giá thay đổi.
