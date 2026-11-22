# Theo dõi giao dịch không hoạt động nhưng vẫn đang mở

Một session database có thể không chạy câu SQL nào nhưng vẫn giữ một transaction chưa kết thúc. Trạng thái này thường xuất hiện khi ứng dụng đã chạy `BEGIN`, đọc hoặc cập nhật dữ liệu rồi chờ một bước khác trước khi `COMMIT` hoặc `ROLLBACK`. Trong PostgreSQL, trạng thái đó thường được hiển thị là `idle in transaction`; sau khi một câu lệnh lỗi mà ứng dụng chưa rollback, nó có thể hiện thành `idle in transaction (aborted)`.

Đây là trạng thái cần theo dõi vì transaction vẫn mở dù backend đang rảnh. Nó có thể giữ row lock, giữ thay đổi chưa commit, làm transaction khác phải chờ, giữ snapshot hoặc transaction horizon trong một số trường hợp, và chiếm connection trong pool. Một session `idle` không có transaction mở thường chỉ là connection đang chờ được tái sử dụng; không nên nhầm nó với một transaction đang giữ tài nguyên.

Muốn chẩn đoán đúng, cần trả lời ba câu hỏi: session nào đang giữ transaction, transaction đó đã mở bao lâu và nó đang giữ tài nguyên hoặc cản trở công việc nào? Sau đó mới quyết định yêu cầu ứng dụng kết thúc transaction, chấm dứt session hay điều chỉnh timeout.

## 1. Phân biệt session idle và transaction idle

**Session/connection** là kết nối của client tới database. **Transaction** là đơn vị thao tác dữ liệu bắt đầu và kết thúc bằng ranh giới transaction. Một session có thể đang hoạt động, đang chờ, hoặc không có câu lệnh chạy; điều đó không tự cho biết transaction đã kết thúc hay chưa.

Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa | Rủi ro chính |
|---|---|---|
| `active` | Backend đang thực thi câu lệnh | Có thể chạy lâu, giữ lock hoặc chờ tài nguyên |
| `idle` | Không có câu lệnh đang chạy và không có transaction mở cần xử lý | Thường là connection nhàn rỗi trong pool |
| `idle in transaction` | Không có câu lệnh đang chạy nhưng transaction vẫn mở | Có thể giữ lock, snapshot, thay đổi chưa commit và connection |
| `idle in transaction (aborted)` | Transaction đã gặp lỗi và đang ở trạng thái aborted, nhưng client chưa rollback/kết thúc | Transaction vẫn tồn tại; các câu lệnh tiếp theo thường bị từ chối cho đến rollback |
| `fastpath function call` | Backend đang thực hiện fast-path function call | Cần xem câu lệnh và workload cụ thể |

Tên trạng thái cụ thể tùy DBMS. PostgreSQL hiển thị rõ `idle in transaction`. MySQL có thể cho process ở `Sleep` trong `SHOW PROCESSLIST` nhưng vẫn có transaction InnoDB đang mở. SQL Server có session `sleeping` với `open_transaction_count > 0`. Oracle có session `INACTIVE` nhưng vẫn gắn với một transaction trong `V$TRANSACTION`.

Vì vậy, chỉ nhìn cột `Command`, `status` hoặc `PROCESSLIST` là chưa đủ. Phải kết hợp trạng thái session với metadata transaction của engine.

## 2. Một transaction trở thành idle in transaction như thế nào?

Một ví dụ phổ biến:

```sql
BEGIN;

SELECT balance
FROM account
WHERE account_id = 10;

-- Ứng dụng tạm dừng để gọi HTTP, chờ người dùng hoặc xử lý dữ liệu.

UPDATE account
SET balance = balance - 100
WHERE account_id = 10;

COMMIT;
```

Nếu ứng dụng dừng sau `SELECT` hoặc `UPDATE` nhưng trước `COMMIT`, session vẫn ở trong transaction. Khi không có câu lệnh nào đang chạy, PostgreSQL có thể hiển thị `idle in transaction`.

Những nguyên nhân thường gặp:

- Mã ứng dụng mở transaction thủ công nhưng có nhánh logic quên `COMMIT` hoặc `ROLLBACK`.
- Exception xảy ra, code bắt lỗi nhưng không rollback transaction.
- Ứng dụng gọi API bên ngoài hoặc chờ message trong khi transaction vẫn mở.
- ORM hoặc transaction framework bắt đầu transaction ở tầng cao hơn phạm vi cần thiết.
- Một request bị hủy hoặc client mất kết nối logic nhưng connection trong pool vẫn còn được giữ.
- Server-side cursor hoặc quy trình stream dữ liệu giữ transaction trong thời gian dài.
- Connection được trả về pool khi transaction chưa được đóng do quản lý transaction sai.
- Một tác vụ batch xử lý từng phần nhưng giữ một transaction xuyên suốt toàn bộ công việc.

Một exception trong PostgreSQL có thể làm transaction chuyển sang trạng thái aborted. Nếu ứng dụng bắt exception rồi giữ connection mà không chạy `ROLLBACK`, session có thể nằm ở `idle in transaction (aborted)`. Những câu lệnh tiếp theo trong transaction thường trả lỗi kiểu “current transaction is aborted” cho đến khi rollback.

## 3. Vì sao transaction idle nguy hiểm?

### 3.1. Giữ khóa sau khi câu lệnh kết thúc

Các khóa lấy trong transaction thường được giữ đến khi transaction kết thúc. Ví dụ, session đã chạy `UPDATE` rồi dừng trước commit vẫn giữ row lock. Session khác muốn cập nhật cùng dòng có thể phải chờ, dù session giữ khóa không chạy SQL nào.

```text
Session A                         Session B
------------------------------    ------------------------------
BEGIN                             BEGIN
UPDATE account ...                UPDATE account ...
  lấy row lock                      chờ row lock của A
không chạy câu lệnh nào             vẫn blocked
idle in transaction                lock wait
```

Một transaction idle có thể là blocker của nhiều session. Các session phía sau có thể tạo thành blocking chain: B chờ A, C chờ B, D chờ C. Việc tìm session đang chờ đầu tiên không nhất thiết chỉ ra session gốc giữ khóa lâu; cần truy ngược blocking chain.

### 3.2. Giữ thay đổi chưa commit

Nếu transaction đã `INSERT`, `UPDATE` hoặc `DELETE` nhưng chưa commit, các thay đổi đó chưa trở thành trạng thái đã commit cho transaction khác. Một giao dịch khác có thể đọc phiên bản cũ, chờ trên khóa hoặc gặp xung đột tùy câu lệnh và isolation level.

Transaction mở lâu cũng làm tăng thời gian mà ứng dụng có thể rollback một lượng công việc lớn. Nếu session bị chấm dứt, DBMS phải hoàn tác các thay đổi chưa commit; rollback có thể mất thời gian và tạo thêm I/O.

### 3.3. Có thể cản trở VACUUM và giữ phiên bản dữ liệu cũ

Trong PostgreSQL, snapshot cũ có thể ngăn VACUUM thu hồi các tuple version mà snapshot đó còn có thể nhìn thấy. Một transaction `REPEATABLE READ` hoặc `SERIALIZABLE` giữ snapshot lâu có thể làm visibility horizon lùi lại, khiến dead tuple tích lũy.

Tuy nhiên, không phải mọi session `idle in transaction` đều giữ một snapshot cũ theo cùng cách. Ở `READ COMMITTED`, snapshot thông thường gắn với từng statement; sau khi statement kết thúc, transaction idle không nhất thiết giữ snapshot đó. Transaction đã ghi, cursor, exported snapshot và các trạng thái khác vẫn cần được xem xét. Hãy kiểm tra `backend_xmin` cùng isolation level thay vì kết luận chỉ từ nhãn state.

### 3.4. Chiếm connection pool

Một connection đang nằm trong transaction chưa kết thúc không thể được pool tái sử dụng an toàn cho request khác. Nếu nhiều request cùng để transaction idle, pool có thể cạn connection dù database CPU thấp và không có nhiều query active.

Triệu chứng thường gặp:

- Request mới chờ lâu để lấy connection.
- Pool báo pending acquire hoặc timeout.
- Database có nhiều session `idle in transaction` hoặc sleeping với open transaction.
- Throughput giảm dù CPU database không cao.
- Một số transaction giữ khóa khiến request khác bị chậm dây chuyền.

### 3.5. Làm tăng rủi ro deadlock và timeout

Một session idle đang giữ khóa có thể khiến transaction khác chờ lâu. Nếu các transaction khác giữ khóa bổ sung rồi chờ ngược lại, deadlock có thể hình thành. Session idle không tự tạo chu trình deadlock chỉ vì nó đang idle, nhưng nó có thể là một mắt xích giữ tài nguyên trong chuỗi chờ.

## 4. Theo dõi trong PostgreSQL bằng pg_stat_activity

`pg_stat_activity` là view đầu tiên nên kiểm tra. Nó cung cấp state, thời điểm bắt đầu transaction, thời điểm bắt đầu câu lệnh, backend xmin, wait event, ứng dụng và câu lệnh gần nhất.

```sql
SELECT pid,
       usename,
       application_name,
       client_addr,
       state,
       xact_start,
       clock_timestamp() - xact_start AS transaction_age,
       state_change,
       clock_timestamp() - state_change AS state_age,
       backend_xid,
       backend_xmin,
       age(backend_xmin) AS xmin_age,
       wait_event_type,
       wait_event,
       left(query, 300) AS last_query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state IN ('idle in transaction', 'idle in transaction (aborted)')
ORDER BY xact_start NULLS LAST;
```

Các cột quan trọng:

- `pid`: process ID của backend; dùng để liên hệ với lock và các hàm quản trị.
- `usename`, `application_name`, `client_addr`: nhận diện người dùng, ứng dụng và client nguồn.
- `state`: phân biệt `idle in transaction` với `idle` hoặc `active`.
- `xact_start`: thời điểm transaction hiện tại bắt đầu; `NULL` nếu không có transaction đang mở.
- `state_change`: thời điểm backend chuyển sang state hiện tại; hữu ích để biết nó đã idle bao lâu.
- `backend_xid`: transaction ID của backend nếu đã được cấp.
- `backend_xmin`: xmin mà backend đang giữ nếu có; có thể giúp xác định snapshot horizon.
- `wait_event_type`, `wait_event`: sự kiện backend đang chờ. Một session idle thường chờ client gửi lệnh tiếp theo; điều này không có nghĩa nó đang chờ lock.
- `query`: với session idle, thường là câu lệnh gần nhất đã chạy, không phải câu lệnh đang thực thi.

`xact_start` đo tuổi transaction; `state_change` đo thời gian ở state hiện tại. Hai giá trị trả lời hai câu hỏi khác nhau. Một transaction có thể đã mở 30 phút nhưng chỉ mới chuyển sang idle 5 giây; hoặc đã nằm idle gần như toàn bộ thời gian transaction.

### 4.1. Liệt kê transaction mở lâu nhất

```sql
SELECT pid,
       usename,
       application_name,
       state,
       clock_timestamp() - xact_start AS transaction_age,
       clock_timestamp() - state_change AS state_age,
       backend_xmin,
       left(query, 200) AS last_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
  AND pid <> pg_backend_pid()
ORDER BY xact_start
LIMIT 30;
```

Truy vấn này bao gồm cả transaction đang chạy câu lệnh và transaction đang idle. Nó hữu ích để tìm transaction cũ nhất, nhưng cần lọc tiếp theo state và wait event để hiểu nguyên nhân.

### 4.2. Đếm session theo state

```sql
SELECT state,
       COUNT(*) AS session_count,
       MAX(clock_timestamp() - xact_start) AS oldest_transaction
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state
ORDER BY session_count DESC;
```

Theo dõi xu hướng theo thời gian có giá trị hơn một ảnh chụp đơn lẻ. Một vài session idle ngắn có thể là bình thường; số lượng tăng liên tục hoặc transaction age vượt ngưỡng nghiệp vụ mới đáng báo động.

## 5. Tìm blocker do transaction idle trong PostgreSQL

Một session idle chỉ là blocker khi nó đang giữ khóa hoặc tài nguyên mà session khác cần. Dùng `pg_blocking_pids()` để tìm quan hệ chờ trực tiếp:

```sql
SELECT waiting.pid AS waiting_pid,
       waiting.application_name AS waiting_app,
       waiting.state AS waiting_state,
       waiting.wait_event_type,
       waiting.wait_event,
       blocker.pid AS blocker_pid,
       blocker.usename AS blocker_user,
       blocker.application_name AS blocker_app,
       blocker.state AS blocker_state,
       blocker.xact_start AS blocker_xact_start,
       clock_timestamp() - blocker.xact_start AS blocker_xact_age,
       left(blocker.query, 250) AS blocker_last_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS blocked_by(pid)
JOIN pg_stat_activity AS blocker ON blocker.pid = blocked_by.pid
WHERE waiting.wait_event_type = 'Lock'
ORDER BY blocker.xact_start NULLS FIRST;
```

Nếu `blocker_state` là `idle in transaction`, backend giữ khóa nhưng không thực thi câu lệnh tại thời điểm quan sát. Hãy xác định ứng dụng/owner và transaction age trước khi quyết định xử lý.

Để xem khóa của các backend liên quan:

```sql
SELECT a.pid,
       a.application_name,
       a.state,
       l.locktype,
       l.mode,
       l.granted,
       l.relation::regclass AS relation,
       l.page,
       l.tuple,
       a.xact_start,
       left(a.query, 200) AS last_query
FROM pg_locks AS l
JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE a.datname = current_database()
ORDER BY a.xact_start NULLS LAST, a.pid;
```

`pg_locks` có thể chứa nhiều loại lock; không phải mọi lock đều là row lock hay lock gây blocking. Cần đọc `locktype`, `mode`, `granted` và đối chiếu với waiting PID. PostgreSQL thường dùng tuple-level locking có metadata khác với hình dung một dòng tương ứng một entry `pg_locks`; không nên chỉ đếm lock row để suy ra số dòng đang bị khóa.

## 6. Theo dõi ảnh hưởng tới VACUUM và MVCC

Nếu nghi ngờ transaction idle đang giữ snapshot cũ, xem backend xmin:

```sql
SELECT pid,
       usename,
       application_name,
       state,
       xact_start,
       backend_xmin,
       age(backend_xmin) AS xmin_age,
       left(query, 200) AS last_query
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;
```

Đồng thời xem dead tuple và lần autovacuum gần nhất:

```sql
SELECT schemaname,
       relname,
       n_live_tup,
       n_dead_tup,
       last_autovacuum,
       autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

`n_dead_tup` là ước lượng thống kê, không phải số đếm chính xác tức thời. Một transaction idle có `backend_xmin` cũ là manh mối; cần xem thêm replication slot, prepared transaction và standby feedback vì các nguồn đó cũng có thể giữ horizon.

Kiểm tra replication slot:

```sql
SELECT slot_name,
       slot_type,
       active,
       xmin,
       catalog_xmin,
       restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Nếu `backend_xmin` không có giá trị hoặc session idle không giữ snapshot ổn định, điều đó không chứng minh session vô hại: nó vẫn có thể giữ row/table lock hoặc uncommitted write. Cần kết hợp thông tin lock và trạng thái transaction.

## 7. Theo dõi MySQL và InnoDB

Trong MySQL, `SHOW PROCESSLIST` có thể hiển thị một connection đang `Sleep`. Trạng thái `Sleep` chỉ cho biết connection hiện không chạy statement. Để biết nó có transaction InnoDB đang mở hay không, kiểm tra `information_schema.innodb_trx`.

```sql
SELECT trx_id,
       trx_state,
       trx_started,
       TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
       trx_mysql_thread_id,
       trx_isolation_level,
       trx_rows_locked,
       trx_rows_modified,
       trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Ghép với processlist để nhận diện session đang ngủ:

```sql
SELECT p.ID,
       p.USER,
       p.HOST,
       p.DB,
       p.COMMAND,
       p.TIME AS command_time_seconds,
       p.STATE,
       t.trx_id,
       t.trx_state,
       t.trx_started,
       TIMESTAMPDIFF(SECOND, t.trx_started, NOW()) AS trx_age_seconds,
       t.trx_rows_locked,
       t.trx_rows_modified,
       t.trx_query
FROM information_schema.PROCESSLIST AS p
JOIN information_schema.innodb_trx AS t
  ON t.trx_mysql_thread_id = p.ID
ORDER BY t.trx_started;
```

Nếu `COMMAND = 'Sleep'` nhưng có dòng tương ứng trong `innodb_trx`, connection đang không chạy statement nhưng vẫn có transaction InnoDB. `trx_query` có thể là `NULL` khi không có câu lệnh hiện tại; `trx_started` mới là thời điểm transaction bắt đầu.

### 7.1. Xem transaction đang chờ khóa

```sql
SELECT *
FROM sys.innodb_lock_waits;
```

View này giúp xem quan hệ giữa transaction chờ và transaction giữ khóa trên các phiên bản MySQL có schema `sys` tương ứng. Nếu không có quyền hoặc view không có sẵn, dùng `performance_schema.data_locks`, `performance_schema.data_lock_waits` và `information_schema.innodb_trx` theo phiên bản đang chạy.

### 7.2. Phân biệt wait timeout và transaction idle

`innodb_lock_wait_timeout` giới hạn thời gian một transaction chờ khóa InnoDB; nó không phải timeout chuyên biệt cho một transaction đang idle và giữ khóa. `wait_timeout` điều khiển thời gian connection không hoạt động trước khi server đóng connection theo cấu hình; việc dựa vào nó để quản lý transaction có thể khiến connection pool bị ngắt bất ngờ.

Nếu server đóng connection có transaction chưa commit, InnoDB sẽ rollback transaction đó khi connection được dọn dẹp. Tuy nhiên, không nên coi timeout connection là cơ chế quản lý transaction chính. Ứng dụng vẫn phải commit/rollback rõ ràng và theo dõi transaction mở lâu.

## 8. Theo dõi SQL Server

SQL Server có thể có session ở trạng thái `sleeping` nhưng vẫn có transaction chưa kết thúc. `sys.dm_exec_sessions.open_transaction_count` và các DMV transaction giúp nhận diện trường hợp này.

```sql
SELECT s.session_id,
       s.login_name,
       s.host_name,
       s.program_name,
       s.status AS session_status,
       s.open_transaction_count,
       at.transaction_id,
       at.transaction_begin_time,
       DATEDIFF(SECOND, at.transaction_begin_time, SYSDATETIME())
           AS transaction_age_seconds,
       at.transaction_state,
       r.status AS request_status,
       r.wait_type,
       r.blocking_session_id,
       txt.text AS current_sql
FROM sys.dm_exec_sessions AS s
LEFT JOIN sys.dm_tran_session_transactions AS st
  ON st.session_id = s.session_id
LEFT JOIN sys.dm_tran_active_transactions AS at
  ON at.transaction_id = st.transaction_id
LEFT JOIN sys.dm_exec_requests AS r
  ON r.session_id = s.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) AS txt
WHERE s.is_user_process = 1
  AND s.open_transaction_count > 0
ORDER BY at.transaction_begin_time;
```

Một session `sleeping` với `open_transaction_count > 0` là dấu hiệu đáng chú ý: request hiện tại đã kết thúc hoặc session đang chờ client, nhưng transaction chưa được đóng. `current_sql` có thể là `NULL` vì không có request đang chạy; cần xem thêm input buffer, application name, host và log ứng dụng để tìm câu lệnh đã mở transaction.

### 8.1. DBCC OPENTRAN

Trong database cần điều tra:

```sql
DBCC OPENTRAN;
```

Lệnh này cung cấp thông tin về transaction đang hoạt động cũ nhất trong database. Nó hữu ích để phát hiện transaction giữ log truncation hoặc transaction lâu, nhưng không thay thế việc liệt kê tất cả session và blocking chain.

### 8.2. Tìm blocker

```sql
SELECT r.session_id AS waiting_session_id,
       r.blocking_session_id,
       r.wait_type,
       r.wait_time,
       s.status AS blocker_session_status,
       s.open_transaction_count,
       s.login_name,
       s.host_name,
       s.program_name
FROM sys.dm_exec_requests AS r
JOIN sys.dm_exec_sessions AS s
  ON s.session_id = r.blocking_session_id
WHERE r.blocking_session_id <> 0
ORDER BY r.wait_time DESC;
```

Nếu blocker session ở `sleeping` và có transaction mở, hãy kiểm tra ứng dụng nào sở hữu connection và vì sao transaction chưa kết thúc. Quyền đọc các DMV phụ thuộc quyền server/database của tài khoản giám sát.

## 9. Theo dõi Oracle

Trong Oracle, `V$SESSION.STATUS = 'INACTIVE'` chỉ ra session hiện không thực thi lời gọi database. Session vẫn có thể gắn với transaction đang mở. Có thể join `V$SESSION.TADDR` với `V$TRANSACTION.ADDR`:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.machine,
       s.program,
       s.module,
       s.last_call_et,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$session s
JOIN v$transaction t
  ON t.addr = s.taddr
WHERE s.type = 'USER'
  AND s.status = 'INACTIVE'
ORDER BY t.start_time;
```

`LAST_CALL_ET` với session inactive là số giây kể từ khi lời gọi cuối kết thúc. `START_TIME` là thời điểm bắt đầu transaction; `USED_UBLK` và `USED_UREC` cho biết mức sử dụng undo theo block/record. Session inactive có transaction không nhất thiết là lỗi: một ứng dụng có thể đang ở giữa một quy trình hợp lệ. Cần kết hợp transaction age, lock, module, machine và tác động thực tế.

Các view `V$` yêu cầu quyền phù hợp. Trong môi trường RAC, cần xem xét các view `GV$` để tổng hợp nhiều instance.

## 10. Một bài thực hành: tạo blocker idle in transaction trong PostgreSQL

Bài lab dùng bảng thử nghiệm riêng. Không chạy trên bảng nghiệp vụ thật.

### Chuẩn bị

```sql
DROP TABLE IF EXISTS idle_tx_demo;

CREATE TABLE idle_tx_demo (
    id INTEGER PRIMARY KEY,
    value INTEGER NOT NULL
);

INSERT INTO idle_tx_demo VALUES (1, 100);
```

Mở ba session PostgreSQL: A, B và Monitor.

### Session A: mở transaction và giữ row lock

```sql
BEGIN;

UPDATE idle_tx_demo
SET value = value + 1
WHERE id = 1;

-- Dừng ở đây, không COMMIT hoặc ROLLBACK.
```

Session A đã thay đổi dòng nhưng chưa commit. Sau khi câu lệnh `UPDATE` kết thúc, A có thể chuyển sang `idle in transaction` và vẫn giữ row lock.

### Session B: thử cập nhật cùng dòng

```sql
BEGIN;

UPDATE idle_tx_demo
SET value = value + 10
WHERE id = 1;
```

Lệnh của B sẽ chờ khóa do A đang giữ.

### Session Monitor: tìm blocker

```sql
SELECT waiting.pid AS waiting_pid,
       waiting.state AS waiting_state,
       blocker.pid AS blocker_pid,
       blocker.state AS blocker_state,
       blocker.xact_start AS blocker_xact_start,
       clock_timestamp() - blocker.xact_start AS blocker_age,
       blocker.application_name,
       blocker.query AS blocker_last_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS b(pid)
JOIN pg_stat_activity AS blocker ON blocker.pid = b.pid;
```

Kết quả cho thấy B đang chờ A; A là blocker dù state của A là idle trong transaction.

### Kết thúc thí nghiệm

Quay lại A:

```sql
ROLLBACK;
```

Lệnh của B tiếp tục sau khi khóa được giải phóng. Nếu B đã thực hiện thành công, kết thúc B:

```sql
COMMIT;
```

Kiểm tra dữ liệu:

```sql
SELECT * FROM idle_tx_demo WHERE id = 1;
```

Vì A rollback và B commit, giá trị cuối là 110. Lab minh họa một transaction idle có thể chặn transaction khác dù backend giữ khóa không chạy câu SQL nào.

## 11. Quy trình chẩn đoán khi phát hiện transaction idle lâu

Khi dashboard hoặc alert báo transaction không hoạt động nhưng vẫn mở, hãy điều tra theo trình tự:

1. Xác định DBMS, database, session ID và trạng thái transaction thực tế.
2. Ghi nhận transaction start time, thời gian ở state idle, user, host, application/module và câu lệnh gần nhất.
3. Xác định transaction có đang giữ lock, block session khác hoặc nằm trong blocking chain không.
4. Với PostgreSQL, kiểm tra `backend_xmin`, isolation level, prepared transaction, replication slot và ảnh hưởng VACUUM nếu có dấu hiệu MVCC bloat.
5. Với MySQL, ghép processlist `Sleep` với `innodb_trx`; xem số row lock/modified và lock wait.
6. Với SQL Server, kiểm tra `open_transaction_count`, active transaction DMV, `DBCC OPENTRAN` và blocking session.
7. Với Oracle, kiểm tra `V$SESSION`, `V$TRANSACTION`, module, machine và undo usage.
8. Liên hệ owner ứng dụng để xác định request/job nào mở transaction và nhánh code nào chưa kết thúc nó.
9. Nếu có thể, yêu cầu ứng dụng rollback/commit đúng nghiệp vụ hoặc đóng connection theo quy trình.
10. Chỉ terminate session khi đã đánh giá tác động, có thẩm quyền và chấp nhận việc rollback transaction chưa commit.
11. Theo dõi blocking chain, pool usage, rollback time và trạng thái dữ liệu sau xử lý.

Không nên terminate session chỉ dựa trên tuổi transaction. Một transaction dài có thể là batch hoặc quy trình hợp lệ; ngược lại, transaction mới mở vài giây nhưng đang giữ khóa quan trọng có thể gây sự cố nghiêm trọng. Mức độ ưu tiên phải dựa trên tác động thực tế, không chỉ một ngưỡng thời gian.

## 12. Kết thúc session và rollback có chủ đích

Ưu tiên xử lý từ ứng dụng vì ứng dụng hiểu request đang thực hiện và có thể hoàn tất theo nghiệp vụ. Nếu transaction bị bỏ quên, nhóm vận hành có thể yêu cầu ứng dụng rollback hoặc đóng connection đúng cách.

Trong PostgreSQL, quản trị viên có thể dùng:

```sql
-- Yêu cầu hủy câu lệnh đang chạy; không phải cách đáng tin cậy
-- để kết thúc một transaction đã idle.
SELECT pg_cancel_backend(:pid);

-- Kết thúc backend session; transaction chưa commit sẽ rollback.
SELECT pg_terminate_backend(:pid);
```

`pg_cancel_backend()` chủ yếu hủy câu lệnh hiện tại. Nếu backend đang idle và không có câu lệnh, lệnh cancel không thay thế việc kết thúc transaction. `pg_terminate_backend()` kết thúc session; DBMS rollback transaction chưa commit và quá trình rollback có thể mất thời gian.

Trong MySQL:

```sql
KILL QUERY <processlist_id>;
KILL CONNECTION <processlist_id>;
```

`KILL QUERY` hủy câu lệnh hiện tại nhưng giữ connection; `KILL CONNECTION` đóng connection và transaction chưa commit sẽ được rollback. Trong SQL Server, `KILL <session_id>` chấm dứt session và rollback transaction; dùng `KILL <session_id> WITH STATUSONLY` để xem tiến độ rollback khi phù hợp. Oracle có thể dùng `ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE` theo quyền và quy trình DBA.

Các thao tác terminate có thể gây rollback lớn, tạo tải I/O và làm request client thất bại. Nếu transaction đã thực hiện một phần công việc nhưng chưa commit, dữ liệu chưa commit sẽ không được giữ; ứng dụng có thể phải retry. Ghi lại session ID, owner, lý do, thời điểm và kết quả rollback để phục vụ điều tra.

## 13. Cấu hình timeout và cảnh báo

Timeout là hàng rào bảo vệ bổ sung. Nó không thay thế transaction boundary đúng trong code.

### 13.1. PostgreSQL

`idle_in_transaction_session_timeout` kết thúc session đã idle trong transaction lâu hơn ngưỡng cấu hình. Có thể đặt ở cấp role:

```sql
ALTER ROLE app_user
SET idle_in_transaction_session_timeout = '2min';
```

Hoặc cấu hình ở cấp database/role phù hợp với chính sách. Khi timeout, session bị kết thúc và transaction chưa commit bị rollback. Chọn giá trị dựa trên thời gian xử lý hợp lệ; đặt quá thấp có thể làm hỏng thao tác hợp pháp.

Phân biệt các timeout:

| Tham số | Tác dụng |
|---|---|
| `idle_in_transaction_session_timeout` | Kết thúc session idle trong transaction quá lâu |
| `idle_session_timeout` | Kết thúc session idle không nằm trong transaction; cần thận trọng với connection pool |
| `statement_timeout` | Hủy câu lệnh chạy quá thời gian |
| `lock_timeout` | Hủy câu lệnh khi phải chờ lock quá thời gian |

`statement_timeout` và `lock_timeout` không tự giải quyết session đã idle sau một câu lệnh thành công. Muốn xử lý trường hợp đó, cần timeout dành riêng cho idle-in-transaction.

### 13.2. MySQL/InnoDB

Theo dõi `innodb_trx` và processlist định kỳ. `innodb_lock_wait_timeout` kiểm soát thời gian chờ lock, không phải thời gian transaction được phép idle. `wait_timeout` điều khiển thời gian connection không hoạt động; connection bị đóng có thể khiến transaction rollback và làm pool phải tạo connection mới. Cần cân nhắc ảnh hưởng tới pool và ứng dụng trước khi điều chỉnh.

### 13.3. SQL Server

SQL Server không có một tham số server đơn giản tương đương `idle_in_transaction_session_timeout` cho mọi session. Nên theo dõi DMV, transaction age, blocking và transaction log; đặt timeout ở application/driver phù hợp và đảm bảo code luôn rollback trong nhánh lỗi. `SET LOCK_TIMEOUT` chỉ giới hạn thời gian chờ khóa, không tự kết thúc một session đang sleeping và giữ transaction.

### 13.4. Oracle

Oracle Profile có thể dùng `IDLE_TIME` để giới hạn thời gian session không hoạt động khi resource limit được bật. Khi session bị kết thúc, transaction chưa commit sẽ được rollback. DBA cần kiểm tra chính sách profile, cách áp dụng và tác động tới session pool trước khi dùng.

### 13.5. Thiết kế alert

Không đặt một ngưỡng chung cho mọi workload. Có thể theo dõi:

- Số session idle-in-transaction/sleeping-open-transaction.
- Tuổi transaction lâu nhất và phân vị transaction age.
- Tuổi state idle.
- Số blocker và số session bị block bởi mỗi blocker.
- Tổng thời gian lock wait và blocking duration.
- Connection pool active/idle/pending acquire.
- Dead tuple, vacuum lag và oldest xmin ở PostgreSQL.
- Transaction log/undo usage phù hợp với DBMS.
- Số transaction bị terminate, timeout và rollback.

Alert nên phân biệt một session idle lâu nhưng không ảnh hưởng ai với một session đang chặn hàng trăm request. Có thể cảnh báo sớm theo transaction age và nâng mức cảnh báo khi session trở thành blocker hoặc làm pool/maintenance suy giảm.

## 14. Phòng ngừa từ ứng dụng

### 14.1. Giữ transaction chỉ bao quanh phần cần nguyên tử

Mẫu xử lý nên có ranh giới rõ:

```text
validate request ngoài transaction

BEGIN
  đọc/khóa dữ liệu cần thiết
  kiểm tra bất biến
  ghi các thay đổi liên quan
COMMIT

gọi dịch vụ ngoài hoặc xử lý phần hậu kỳ sau commit
```

Nếu cần gọi dịch vụ ngoài, cân nhắc transactional outbox để ghi ý định gửi cùng transaction rồi worker gửi sau commit. Không giữ transaction mở trong lúc chờ HTTP, message hoặc người dùng.

### 14.2. Luôn rollback khi có lỗi

Trong Java JDBC, quản lý transaction và connection bằng `try/finally` hoặc transaction framework. Ví dụ:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateAccount(connection, request);
        insertLedgerEntries(connection, request);
        connection.commit();
    } catch (Exception e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
```

Đoạn mã minh họa việc rollback khi lỗi và đóng connection. Trong code thực tế cần xử lý cả lỗi khi `setAutoCommit(false)`, commit có kết quả không rõ do mất kết nối, exception phân cấp và transaction manager của framework. Nếu commit trả lỗi mạng, không thể tự kết luận transaction đã rollback; hãy tra cứu theo idempotency key hoặc request ID trước khi retry.

### 14.3. Không trả connection về pool khi transaction còn mở

Connection pool có thể reset một số trạng thái khi connection được trả lại, nhưng không nên dựa vào hành vi reset không rõ ràng để cứu code. Transaction phải được commit hoặc rollback trước khi trả connection. Một số pool có thể phát hiện connection leak hoặc rollback transaction còn mở khi recycle; hãy xem đó là hàng rào phát hiện lỗi, không phải thay thế quản lý transaction.

### 14.4. Tránh giữ transaction qua thao tác chậm

- Không chờ người dùng nhập liệu trong transaction.
- Không gọi API đối tác khi đang giữ row lock.
- Không xử lý file lớn hoặc tính toán CPU lâu giữa `BEGIN` và `COMMIT` nếu có thể tách ra.
- Không stream kết quả lâu trong một transaction snapshot nếu không cần tính nhất quán đó.
- Với batch lớn, chia thành chunk có checkpoint và idempotency phù hợp.

### 14.5. Ghi nhận transaction context

Đặt `application_name` trong PostgreSQL hoặc module/client identifier tương ứng của DBMS để DBA liên kết session với service/job. Log nên có request ID, transaction start, connection ID và thời gian commit/rollback. Tránh log dữ liệu nhạy cảm hoặc câu lệnh có literal chứa bí mật.

## 15. Checklist chẩn đoán nhanh

Khi phát hiện giao dịch không hoạt động nhưng vẫn mở, hãy xác định:

1. Session đang ở `idle`, `idle in transaction`, `sleeping` hay `INACTIVE`?
2. Có transaction thực sự mở không: `xact_start`, `innodb_trx`, `open_transaction_count` hoặc `V$TRANSACTION`?
3. Transaction đã mở bao lâu và đã idle bao lâu?
4. User, host, application, module và request/job owner là ai?
5. Câu SQL gần nhất đã đọc hay ghi dữ liệu nào?
6. Session có giữ lock hoặc đang là blocker không?
7. Có blocking chain hoặc pool exhaustion không?
8. Với PostgreSQL, `backend_xmin` có cũ và autovacuum có bị cản trở không?
9. Với MySQL, transaction có nhiều row locked/modified không?
10. Với SQL Server, transaction có giữ log hoặc lock quan trọng không?
11. Với Oracle, transaction đang dùng bao nhiêu undo block/record?
12. Có thể yêu cầu ứng dụng rollback/commit an toàn không?
13. Nếu terminate, rollback có thể kéo dài bao lâu và request nào sẽ bị ảnh hưởng?
14. Cần timeout, leak detection hoặc sửa code nào để ngăn tái diễn?

## 16. Kết luận

Session không chạy câu SQL nào không có nghĩa transaction đã kết thúc. `idle in transaction` ở PostgreSQL, `Sleep` đi kèm dòng trong `innodb_trx` ở MySQL, session `sleeping` có `open_transaction_count` ở SQL Server và session `INACTIVE` gắn với `V$TRANSACTION` ở Oracle đều có thể là giao dịch chưa được đóng.

Transaction idle có thể giữ lock, chặn request khác, giữ thay đổi chưa commit, chiếm connection pool và trong một số trường hợp giữ snapshot khiến MVCC cleanup chậm. Hãy giám sát transaction age cùng state age, nhận diện owner, tìm blocker và xem ảnh hưởng thực tế. Khi xử lý, ưu tiên kết thúc transaction từ ứng dụng; chỉ terminate session khi đã hiểu tác động rollback. Timeout và leak detection giúp phát hiện sớm, nhưng biện pháp bền vững là giữ transaction ngắn, rollback mọi nhánh lỗi và không chờ dịch vụ ngoài trong lúc đang giữ transaction.
