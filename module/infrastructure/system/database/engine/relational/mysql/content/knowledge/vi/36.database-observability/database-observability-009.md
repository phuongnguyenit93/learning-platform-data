# Phân tích locks, metadata locks và phiên chặn

Khi một câu SQL bị treo, nguyên nhân có thể là transaction khác đang giữ khóa trên hàng dữ liệu, một thao tác DDL đang chờ metadata lock, hoặc nhiều phiên đang tạo thành chuỗi chặn nhau. Muốn xử lý đúng, cần xác định **phiên đang chờ**, **phiên đang giữ khóa**, đối tượng bị khóa và transaction nào cần kết thúc.

Trong MySQL, InnoDB row lock và metadata lock (MDL) là hai cơ chế khác nhau. Row lock bảo vệ dữ liệu trong quá trình đọc có khóa hoặc ghi; MDL bảo vệ metadata của đối tượng như bảng và schema khi câu lệnh sử dụng hoặc thay đổi cấu trúc đối tượng. Cả hai đều có thể khiến truy vấn phải chờ, nhưng cần quan sát bằng công cụ và cách xử lý khác nhau.

## 1. Phân biệt các loại khóa và tình huống chờ

| Cơ chế | Bảo vệ điều gì? | Ví dụ thường gặp | Nơi quan sát |
|---|---|---|---|
| InnoDB record/gap/next-key locks | Các bản ghi và khoảng khóa trong index | `UPDATE`, `DELETE`, `SELECT ... FOR UPDATE` | `performance_schema.data_locks`, `data_lock_waits`, `sys.innodb_lock_waits` |
| InnoDB intention/table locks | Báo hiệu ý định khóa ở mức hàng và tương tác với khóa bảng | Transaction lấy row lock, `LOCK TABLES` | `performance_schema.data_locks`, `SHOW ENGINE INNODB STATUS` |
| Metadata locks (MDL) | Metadata của schema, bảng, view, routine và đối tượng liên quan | Transaction đọc bảng còn mở, `ALTER TABLE`, `DROP TABLE` | `performance_schema.metadata_locks`, `sys.schema_table_lock_waits` |
| Deadlock | Chu trình chờ khóa giữa các transaction | A giữ hàng 1 chờ hàng 2, B giữ hàng 2 chờ hàng 1 | `SHOW ENGINE INNODB STATUS`, error log nếu bật ghi deadlock |

Một phiên `Sleep` vẫn có thể giữ transaction và khóa. Trạng thái `Sleep` chỉ cho biết connection hiện không chạy câu lệnh; nó không chứng minh transaction đã commit hoặc rollback.

## 2. Hiểu InnoDB row lock

InnoDB khóa các mục index để bảo vệ thao tác đọc có khóa và ghi. Tùy điều kiện truy vấn, isolation level và access path, khóa có thể bao gồm:

- **Record lock:** khóa một mục index cụ thể.
- **Gap lock:** khóa khoảng trống giữa các mục index để ngăn transaction khác chèn vào khoảng đó trong những trường hợp cần thiết.
- **Next-key lock:** kết hợp record lock với gap lock liền trước mục index.
- **Insert intention lock:** tín hiệu một transaction chuẩn bị chèn vào một khoảng; các insert ở vị trí khác nhau trong cùng khoảng có thể không xung đột với nhau.
- **Intention lock:** khóa ở mức bảng như `IS` hoặc `IX`, cho biết transaction có ý định lấy khóa chia sẻ hoặc độc quyền ở cấp hàng.

Ví dụ hai transaction cùng cập nhật một hàng:

```sql
-- Session A
START TRANSACTION;
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 9001;
-- Chưa COMMIT
```

```sql
-- Session B
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 9001;
-- Có thể phải chờ khóa A đang giữ
```

Nếu Session A commit hoặc rollback, Session B mới có thể tiếp tục. Trong InnoDB, khóa thường được giữ đến khi transaction kết thúc, không chỉ đến khi câu `UPDATE` trả kết quả.

### Vì sao index ảnh hưởng phạm vi khóa?

InnoDB khóa các index record mà quá trình thực thi truy cập. Truy vấn có index phù hợp và điều kiện chọn lọc có thể khóa ít mục hơn. Truy vấn quét phạm vi rộng hoặc thiếu index có thể chạm và khóa nhiều mục hơn dự kiến, làm tăng tranh chấp.

Ví dụ, nếu `product_id` là primary key, điều kiện bằng trên `product_id` định vị một record cụ thể. Nếu điều kiện dùng cột không có index, engine có thể phải quét nhiều hàng; phạm vi khóa thực tế phụ thuộc access path và isolation level. Dùng `EXPLAIN` cùng dữ liệu lock để hiểu truy vấn đã đi qua index nào.

Không suy luận rằng mọi `SELECT` đều lấy row lock. Consistent read thông thường của InnoDB dùng MVCC và không khóa các hàng được đọc theo cách `SELECT ... FOR UPDATE` thực hiện. Locking read như `FOR UPDATE` hoặc `FOR SHARE`, cùng các câu lệnh ghi, mới có hành vi khóa tương ứng.

## 3. Metadata lock (MDL) là gì?

MySQL dùng metadata lock để bảo vệ cấu trúc và metadata của đối tượng khi session đang sử dụng đối tượng đó. MDL ngăn một thao tác thay đổi cấu trúc xảy ra đồng thời theo cách làm câu truy vấn khác nhìn thấy metadata không nhất quán.

Các câu lệnh truy cập bảng như `SELECT`, `INSERT`, `UPDATE` và `DELETE` đều lấy loại MDL phù hợp. DDL như `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE` thường cần MDL độc quyền hoặc một mức khóa tương ứng trong quá trình thay đổi metadata.

Điểm quan trọng: transaction có thể giữ MDL đến khi transaction kết thúc. Vì vậy, một session đã chạy `SELECT` trong transaction mở lâu có thể khiến `ALTER TABLE` phải chờ, dù câu `SELECT` đã chạy xong và session hiện đang `Sleep`.

### Mô phỏng DDL bị chặn bởi transaction đọc

```sql
-- Session A
START TRANSACTION;
SELECT * FROM orders WHERE order_id = 7001;
-- Giữ transaction mở, chưa COMMIT/ROLLBACK
```

```sql
-- Session B
ALTER TABLE orders ADD COLUMN source VARCHAR(30);
-- Chờ metadata lock từ Session A
```

Session A có thể không giữ row lock nào sau consistent read thông thường, nhưng vẫn giữ MDL trên bảng `orders`. Session B cần metadata lock xung đột để thay đổi bảng nên phải chờ.

Khi có yêu cầu MDL độc quyền đang chờ, những truy vấn mới trên cùng đối tượng cũng có thể bị xếp hàng phía sau tùy chính sách ưu tiên khóa. Một transaction đọc lâu có thể tạo hiệu ứng dây chuyền: DDL chờ transaction cũ, rồi các truy vấn mới tiếp tục chờ DDL.

### Các trạng thái MDL thường thấy

Trong `performance_schema.metadata_locks`, trường `LOCK_STATUS` thường cho biết:

- `GRANTED`: lock đã được cấp.
- `PENDING`: lock đang chờ được cấp.

`LOCK_TYPE` thể hiện loại yêu cầu như `SHARED_READ`, `SHARED_WRITE`, `SHARED_UPGRADABLE` hoặc `EXCLUSIVE`. `LOCK_DURATION` cho biết phạm vi thời gian giữ lock, thường là `STATEMENT`, `TRANSACTION` hoặc `EXPLICIT`.

## 4. Xem nhanh các transaction InnoDB đang mở

`information_schema.innodb_trx` cung cấp thông tin transaction InnoDB hiện tại. Có thể bắt đầu bằng truy vấn:

```sql
SELECT trx_id,
       trx_state,
       trx_started,
       TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
       trx_mysql_thread_id AS connection_id,
       trx_query,
       trx_tables_locked,
       trx_rows_locked,
       trx_rows_modified,
       trx_isolation_level
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Các trường hữu ích:

- `trx_started`: thời điểm transaction bắt đầu; transaction cũ thường cần được kiểm tra kỹ.
- `trx_state`: trạng thái như `RUNNING` hoặc `LOCK WAIT`.
- `trx_mysql_thread_id`: connection ID dùng với `SHOW PROCESSLIST` hoặc `KILL`.
- `trx_query`: câu SQL hiện tại nếu transaction đang chạy câu lệnh; có thể `NULL` nếu connection đang idle.
- `trx_rows_locked` và `trx_rows_modified`: số hàng đang khóa và số hàng đã thay đổi theo thống kê của transaction.

Để ghép với user, host và trạng thái connection:

```sql
SELECT t.PROCESSLIST_ID AS connection_id,
       t.PROCESSLIST_USER AS user_name,
       t.PROCESSLIST_HOST AS client_host,
       t.PROCESSLIST_DB AS current_db,
       t.PROCESSLIST_COMMAND AS command_name,
       t.PROCESSLIST_TIME AS command_seconds,
       t.PROCESSLIST_STATE AS process_state,
       trx.trx_id,
       trx.trx_state,
       trx.trx_started,
       trx.trx_query
FROM information_schema.innodb_trx AS trx
LEFT JOIN performance_schema.threads AS t
       ON t.PROCESSLIST_ID = trx.trx_mysql_thread_id
ORDER BY trx.trx_started;
```

Nếu `PROCESSLIST_COMMAND` là `Sleep` nhưng transaction vẫn xuất hiện trong `innodb_trx`, connection đang idle trong khi transaction còn mở. Đây là một dấu hiệu quan trọng khi điều tra blocker.

## 5. Phân tích InnoDB lock wait bằng sys schema

Trên MySQL 8.0, cách thuận tiện là xem view `sys.innodb_lock_waits`. View này kết hợp thông tin lock wait, transaction và connection để cho biết ai đang chờ ai:

```sql
SELECT wait_started,
       wait_age,
       waiting_pid,
       waiting_query,
       locked_table,
       locked_index,
       waiting_trx_rows_locked,
       blocking_pid,
       blocking_query,
       blocking_trx_age,
       blocking_trx_rows_locked,
       sql_kill_blocking_query,
       sql_kill_blocking_connection
FROM sys.innodb_lock_waits
ORDER BY wait_age_secs DESC;
```

Ý nghĩa:

- `waiting_pid`: connection ID đang chờ.
- `waiting_query`: câu lệnh đang chờ khóa.
- `locked_table` và `locked_index`: bảng và index liên quan đến lock wait.
- `blocking_pid`: connection ID đang giữ khóa chặn.
- `blocking_query`: câu lệnh hiện tại của blocker nếu có; có thể `NULL` nếu blocker đang idle.
- `blocking_trx_age`: tuổi transaction chặn.
- `sql_kill_blocking_query` và `sql_kill_blocking_connection`: câu lệnh gợi ý để kết thúc query hoặc connection chặn; chỉ là gợi ý, không nên chạy tự động.

Một blocker có thể chặn nhiều waiter. Hãy nhóm theo `blocking_pid` để xác định connection gây ảnh hưởng rộng:

```sql
SELECT blocking_pid,
       COUNT(*) AS waiting_sessions,
       MAX(wait_age_secs) AS longest_wait_seconds,
       MAX(blocking_trx_age) AS blocking_trx_age
FROM sys.innodb_lock_waits
GROUP BY blocking_pid
ORDER BY waiting_sessions DESC, longest_wait_seconds DESC;
```

View `sys.innodb_lock_waits` phụ thuộc vào Performance Schema và các bảng hệ thống bên dưới. Nếu view không có dữ liệu, không vội kết luận không có lock; xác minh phiên bản, quyền truy cập và instrumentation trước.

## 6. Xem chi tiết lock bằng Performance Schema

Trong MySQL 8.0, `performance_schema.data_locks` liệt kê lock InnoDB đang tồn tại và `performance_schema.data_lock_waits` mô tả quan hệ giữa lock đang yêu cầu với lock đang chặn.

Kiểm tra các lock trên một bảng:

```sql
SELECT ENGINE,
       ENGINE_TRANSACTION_ID,
       THREAD_ID,
       OBJECT_SCHEMA,
       OBJECT_NAME,
       INDEX_NAME,
       LOCK_TYPE,
       LOCK_MODE,
       LOCK_STATUS,
       LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'orders'
ORDER BY ENGINE_TRANSACTION_ID, INDEX_NAME;
```

`LOCK_MODE` có thể thể hiện các chế độ như `S`, `X`, `IS`, `IX`, `GAP`, `REC_NOT_GAP` hoặc tổ hợp của chúng tùy loại lock. `LOCK_DATA` có thể chứa giá trị khóa của record; không phải lúc nào trường này cũng có giá trị.

Truy vấn sau ghép lock đang chờ với lock chặn và thread tương ứng:

```sql
SELECT w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
       wt.PROCESSLIST_ID AS waiting_connection_id,
       r.OBJECT_SCHEMA,
       r.OBJECT_NAME,
       r.INDEX_NAME,
       r.LOCK_MODE AS requested_lock_mode,
       r.LOCK_DATA AS requested_lock_data,
       w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
       bt.PROCESSLIST_ID AS blocking_connection_id,
       b.LOCK_MODE AS blocking_lock_mode,
       b.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS wt
  ON wt.THREAD_ID = w.REQUESTING_THREAD_ID
LEFT JOIN performance_schema.threads AS bt
  ON bt.THREAD_ID = w.BLOCKING_THREAD_ID;
```

`data_lock_waits` là bảng quan hệ giữa các lock, không phải danh sách mọi lock đang tồn tại. Dùng `data_locks` khi cần xem lock đã cấp hoặc đang chờ; dùng `data_lock_waits` khi cần biết cặp waiter/blocker.

## 7. Phân tích metadata lock wait

MDL được quan sát trong `performance_schema.metadata_locks`. Truy vấn sau liệt kê các yêu cầu đang chờ cùng những lock đã được cấp trên cùng đối tượng:

```sql
SELECT ml.OBJECT_TYPE,
       ml.OBJECT_SCHEMA,
       ml.OBJECT_NAME,
       ml.LOCK_TYPE,
       ml.LOCK_DURATION,
       ml.LOCK_STATUS,
       th.PROCESSLIST_ID AS connection_id,
       th.PROCESSLIST_USER AS user_name,
       th.PROCESSLIST_HOST AS client_host,
       th.PROCESSLIST_COMMAND AS command_name,
       th.PROCESSLIST_TIME AS command_seconds,
       esc.SQL_TEXT AS current_sql
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
       ON th.THREAD_ID = ml.OWNER_THREAD_ID
LEFT JOIN performance_schema.events_statements_current AS esc
       ON esc.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.LOCK_STATUS IN ('PENDING', 'GRANTED')
  AND ml.OBJECT_SCHEMA = DATABASE()
ORDER BY ml.OBJECT_NAME, ml.LOCK_STATUS, th.PROCESSLIST_ID;
```

Truy vấn này giúp nhìn các lock trên cùng đối tượng, nhưng không tự xác định mọi quan hệ tương thích/xung đột giữa các loại MDL. Để xem cặp session chờ và chặn theo cách dễ đọc hơn, dùng `sys.schema_table_lock_waits`:

```sql
SELECT object_schema,
       object_name,
       waiting_pid,
       waiting_account,
       waiting_lock_type,
       waiting_query,
       waiting_query_secs,
       blocking_pid,
       blocking_account,
       blocking_lock_type,
       bsql.SQL_TEXT AS blocking_current_sql,
       sql_kill_blocking_query,
       sql_kill_blocking_connection
FROM sys.schema_table_lock_waits AS waits
LEFT JOIN performance_schema.threads AS bt
       ON bt.THREAD_ID = waits.blocking_thread_id
LEFT JOIN performance_schema.events_statements_current AS bsql
       ON bsql.THREAD_ID = bt.THREAD_ID
ORDER BY waiting_query_secs DESC;
```

View này tập trung vào metadata lock wait trên đối tượng bảng. Nó cung cấp thread ID, connection ID và thông tin lock của waiter/blocker; câu SQL hiện tại của blocker được lấy thêm từ `events_statements_current`. `blocking_current_sql` có thể `NULL` nếu session chặn không còn chạy câu SQL nhưng transaction vẫn mở. Khi đó cần ghép `blocking_pid` với `innodb_trx` và `threads` để xem transaction bắt đầu lúc nào, user nào sở hữu connection và trạng thái hiện tại.

### Kiểm tra instrumentation MDL

Nếu `metadata_locks` không cung cấp thông tin như mong đợi, kiểm tra instrument:

```sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME = 'wait/lock/metadata/sql/mdl';
```

Nếu instrument đang tắt và bạn có quyền quản trị, có thể bật để thu thập tiếp:

```sql
UPDATE performance_schema.setup_instruments
SET ENABLED = 'YES', TIMED = 'YES'
WHERE NAME = 'wait/lock/metadata/sql/mdl';
```

Chỉ bật khi cần và theo chính sách vận hành. Thay đổi instrumentation có thể ảnh hưởng overhead và phạm vi quan sát; không cập nhật toàn bộ `setup_instruments` một cách tùy tiện. Sau khi điều tra, khôi phục trạng thái trước đó nếu chính sách yêu cầu.

## 8. Ghép blocker với câu lệnh và transaction

Không phải lúc nào câu SQL đang hiển thị cũng là câu đã lấy lock. Một transaction có thể thực hiện nhiều câu lệnh; câu đầu đã lấy MDL hoặc row lock, câu sau đã kết thúc, rồi connection trở về `Sleep` nhưng transaction chưa commit.

Khi `blocking_query` là `NULL`, hãy kiểm tra:

1. `information_schema.innodb_trx` để biết transaction còn mở, tuổi transaction và số hàng đang khóa.
2. `performance_schema.threads` để biết connection ID, user, host, command và trạng thái.
3. `performance_schema.events_statements_current` để biết câu lệnh đang chạy; nếu rỗng, xem `events_statements_history` hoặc `events_statements_history_long` nếu consumer đã bật và dữ liệu còn trong history.
4. Log của ứng dụng để tìm transaction bắt đầu ở request nào và vì sao chưa commit/rollback.

Ví dụ xem statement gần nhất của các thread đang giữ transaction:

```sql
SELECT th.PROCESSLIST_ID AS connection_id,
       th.PROCESSLIST_USER AS user_name,
       th.PROCESSLIST_HOST AS client_host,
       th.PROCESSLIST_COMMAND AS command_name,
       th.PROCESSLIST_TIME AS command_seconds,
       esh.EVENT_ID,
       esh.SQL_TEXT,
       esh.TIMER_WAIT
FROM performance_schema.threads AS th
JOIN information_schema.innodb_trx AS trx
  ON trx.trx_mysql_thread_id = th.PROCESSLIST_ID
LEFT JOIN performance_schema.events_statements_history AS esh
  ON esh.THREAD_ID = th.THREAD_ID
WHERE th.TYPE = 'FOREGROUND'
ORDER BY th.PROCESSLIST_ID, esh.EVENT_ID DESC;
```

History chỉ lưu các statement gần đây trong bộ đệm có giới hạn và có thể không được bật. Không có dòng history không có nghĩa connection chưa chạy câu SQL trước đó. Hãy đối chiếu thêm log ứng dụng và transaction age.

## 9. Phân biệt lock wait với deadlock

**Lock wait** là một transaction đang chờ lock mà transaction khác giữ. Nếu blocker kết thúc, waiter có thể tiếp tục. Nếu chờ quá thời gian cấu hình, câu lệnh có thể gặp lỗi lock wait timeout (thường là lỗi `1205`).

**Deadlock** là chu trình phụ thuộc: transaction A chờ tài nguyên do B giữ, trong khi B lại chờ tài nguyên do A giữ (hoặc tạo thành chu trình dài hơn). InnoDB phát hiện deadlock và chọn một transaction làm victim để rollback nhằm phá chu trình; ứng dụng nhận lỗi deadlock (thường là `1213`) và nên retry toàn bộ transaction theo chính sách có giới hạn.

Xem deadlock gần nhất:

```sql
SHOW ENGINE INNODB STATUS;
```

Tìm phần `LATEST DETECTED DEADLOCK` trong kết quả. Nếu cần ghi tất cả deadlock vào error log để điều tra, quản trị viên có thể cân nhắc `innodb_print_all_deadlocks`, nhưng phải đánh giá lượng log và quy trình vận hành trước khi bật.

Lock wait timeout không đồng nghĩa deadlock. Với InnoDB, mặc định khi lock wait timeout xảy ra, statement đang chờ bị rollback; toàn transaction chỉ bị rollback nếu `innodb_rollback_on_timeout` được bật hoặc ứng dụng chủ động rollback. Ứng dụng nên xử lý lỗi nhất quán, thường rollback transaction và retry toàn bộ đơn vị nghiệp vụ nếu có thể.

## 10. Quy trình xử lý phiên chặn an toàn

Khi nhận cảnh báo truy vấn chờ khóa, làm theo thứ tự:

1. **Xác định loại chờ:** row lock, MDL, table lock hay deadlock. Dùng `sys.innodb_lock_waits`, `sys.schema_table_lock_waits` và `SHOW ENGINE INNODB STATUS` phù hợp.
2. **Tìm waiter và blocker:** ghi lại connection ID, transaction ID, bảng, index, lock mode và thời gian chờ.
3. **Tìm root blocker:** nếu blocker lại đang chờ một session khác, lần theo chuỗi đến transaction giữ khóa gốc.
4. **Đánh giá tác động:** số waiter, tuổi transaction, số hàng đã sửa, user/host, câu lệnh và nghiệp vụ liên quan.
5. **Ưu tiên xử lý ở ứng dụng:** nếu chủ sở hữu connection có thể rollback hoặc commit an toàn, yêu cầu ứng dụng kết thúc transaction đúng cách.
6. **Chỉ can thiệp quản trị khi đã hiểu tác động:** xác minh connection ID và chủ sở hữu trước khi dùng `KILL`; thông báo cho nhóm chịu ảnh hưởng theo quy trình vận hành.
7. **Xác minh sau xử lý:** kiểm tra waiter đã chạy tiếp hoặc nhận lỗi, lock wait biến mất và không phát sinh chuỗi chặn mới.

### `KILL QUERY` và `KILL CONNECTION` khác nhau

```sql
KILL QUERY 12345;
KILL CONNECTION 12345;
```

- `KILL QUERY` dừng câu lệnh hiện tại của connection nhưng giữ connection. Nếu connection đang ở trong transaction mở, transaction có thể vẫn còn mở và tiếp tục giữ lock.
- `KILL CONNECTION` ngắt connection. Transaction đang mở của connection sẽ được rollback; việc rollback có thể mất thời gian nếu transaction đã sửa nhiều dữ liệu. Lock được giải phóng khi quá trình rollback hoàn tất.

Không chạy câu `KILL` chỉ dựa vào một connection ID cũ trong dashboard. ID có thể đã kết thúc và được tái sử dụng theo vòng đời server; hãy xác minh lại user, host, thời gian và transaction ngay trước khi can thiệp. Với MDL do transaction idle giữ, `KILL QUERY` thường không giải quyết được nguyên nhân vì không có câu lệnh đang chạy để dừng.

## 11. Giảm nguy cơ lock contention và blocking

- Giữ transaction ngắn; không chờ người dùng hoặc gọi dịch vụ bên ngoài khi transaction còn mở.
- Truy cập các bảng và hàng theo thứ tự nhất quán giữa các transaction để giảm nguy cơ deadlock.
- Tạo index phù hợp cho điều kiện `WHERE` và join để giảm số index record cần quét và khóa.
- Cập nhật theo lô nhỏ khi thao tác trên lượng dữ liệu lớn; commit theo ranh giới nghiệp vụ an toàn.
- Xử lý lỗi deadlock và timeout bằng retry có giới hạn, có backoff và bảo đảm thao tác có tính idempotent khi cần.
- Không để DDL chờ vô thời hạn mà không giám sát. Kiểm tra transaction lâu trước khi chạy `ALTER TABLE`, `DROP TABLE` hoặc `RENAME TABLE`.
- Đặt timeout phù hợp cho ứng dụng và vận hành, nhưng không xem giảm timeout là cách sửa transaction giữ khóa quá lâu.
- Theo dõi tuổi transaction, số waiter, thời gian chờ lớn nhất và bảng/index thường xuyên bị tranh chấp.

## 12. Bảng chọn công cụ quan sát

| Câu hỏi | Công cụ nên dùng | Mục đích |
|---|---|---|
| Transaction InnoDB nào đang mở lâu? | `information_schema.innodb_trx` | Tuổi transaction, trạng thái, connection ID và số hàng khóa |
| Connection nào đang chờ row lock và ai chặn? | `sys.innodb_lock_waits` | Xem waiter/blocker, bảng, index và tuổi chờ |
| Muốn xem chi tiết lock mode và lock data? | `performance_schema.data_locks`, `data_lock_waits` | Phân tích lock được cấp và quan hệ chờ |
| DDL đang chờ metadata lock nào? | `sys.schema_table_lock_waits` | Ghép session chờ với session giữ MDL |
| Muốn xem trạng thái granted/pending MDL? | `performance_schema.metadata_locks` | Xem object, lock type, duration và owner thread |
| Muốn điều tra deadlock gần nhất? | `SHOW ENGINE INNODB STATUS` | Đọc transaction, index record và chu trình deadlock |
| Connection hiện đang làm gì? | `SHOW FULL PROCESSLIST`, `performance_schema.threads` | User, host, command, state và câu lệnh hiện tại |

## 13. Tự kiểm tra

1. InnoDB row lock và metadata lock khác nhau ở đối tượng được bảo vệ như thế nào?
2. Vì sao một connection `Sleep` vẫn có thể chặn transaction hoặc DDL khác?
3. Transaction đọc thông thường có thể giữ MDL dù không giữ row lock không?
4. `sys.innodb_lock_waits` cho biết waiter và blocker qua những cột nào?
5. Khi nào nên dùng `performance_schema.data_locks` và `data_lock_waits`?
6. Vì sao `metadata_locks` liệt kê các lock nhưng không tự mô tả đầy đủ quan hệ tương thích giữa chúng?
7. `KILL QUERY` khác `KILL CONNECTION` thế nào khi blocker đang ở trong transaction mở?
8. Deadlock khác lock wait timeout ở điểm nào và ứng dụng nên xử lý ra sao?

