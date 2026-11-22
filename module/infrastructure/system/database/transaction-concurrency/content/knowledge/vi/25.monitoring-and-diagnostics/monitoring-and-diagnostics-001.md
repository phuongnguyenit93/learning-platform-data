# Thu thập phiên, giao dịch đang mở và tuổi của giao dịch

Khi điều tra hệ thống cơ sở dữ liệu chậm, chờ khóa hoặc có nguy cơ hết tài nguyên, cần biết những session nào đang kết nối, transaction nào còn mở và mỗi transaction đã tồn tại bao lâu. Một session có thể đang chạy SQL, đang chờ khóa, đang nhàn rỗi hoặc ở trạng thái `idle in transaction`. Trạng thái cuối thường khó nhận ra nếu chỉ nhìn danh sách truy vấn đang chạy: session không thực thi câu SQL nào nhưng transaction vẫn mở và có thể tiếp tục giữ khóa hoặc snapshot.

Điểm quan trọng là phải đo riêng **tuổi session**, **tuổi câu lệnh** và **tuổi transaction**. Ba khoảng thời gian này trả lời ba câu hỏi khác nhau. Một kết nối có thể tồn tại nhiều giờ nhưng mỗi transaction chỉ kéo dài vài mili giây; ngược lại, một transaction có thể mở từ lâu dù câu SQL cuối cùng đã chạy xong và session đang ngủ.

## 1. Phân biệt session, request và transaction

Các hệ quản trị dùng thuật ngữ khác nhau, nhưng khi chẩn đoán cần phân biệt những đối tượng sau:

- **Session/connection:** một kết nối logic từ ứng dụng hoặc công cụ quản trị đến database. Session có thể tồn tại lâu và thực hiện nhiều transaction liên tiếp.
- **Request/statement:** câu SQL hoặc batch đang được thực thi trên session. Một session thường chỉ có một request đồng thời theo cách sử dụng connection thông thường.
- **Transaction:** đơn vị thay đổi dữ liệu được commit hoặc rollback cùng nhau. Transaction có thể gồm nhiều câu SQL và có thể vẫn mở sau khi câu SQL cuối đã kết thúc.
- **Lock/wait:** tài nguyên session đang giữ hoặc đang chờ. Một session có thể không chạy SQL nhưng vẫn giữ khóa từ transaction trước đó.

Ví dụ một session trong connection pool có thể hoạt động như sau:

```text
Session được tạo
    |
    +-- Transaction 1: BEGIN -> SELECT -> UPDATE -> COMMIT
    |
    +-- Idle trong pool, không có transaction mở
    |
    +-- Transaction 2: BEGIN -> UPDATE -> chờ ứng dụng -> COMMIT
    |                                      ^
    |                                      |
    |                           Session idle in transaction
    |
    +-- Transaction 3: BEGIN -> SELECT -> ROLLBACK
```

Trong ví dụ này, tuổi session có thể lớn hơn nhiều so với tuổi transaction. Transaction thứ hai có thể đang giữ khóa dù session không có câu SQL hoạt động.

## 2. Ba loại tuổi cần thu thập

| Chỉ số | Bắt đầu tính từ | Dùng để trả lời |
|---|---|---|
| Session age | Thời điểm kết nối/session được tạo | Kết nối nào tồn tại lâu bất thường? Có connection leak hoặc pool giữ quá nhiều session không? |
| Query/statement age | Thời điểm câu lệnh hiện tại bắt đầu | Câu SQL nào đang chạy hoặc chờ quá lâu? |
| Transaction age | Thời điểm transaction hiện tại bắt đầu | Transaction nào mở lâu, giữ khóa hoặc giữ snapshot lâu? |

Không dùng thời gian session để kết luận transaction bị mở lâu. Một connection pool có thể giữ session hàng giờ là bình thường. Cũng không dùng thời gian câu lệnh cuối để thay thế tuổi transaction: một transaction có thể chạy một câu `UPDATE`, sau đó ứng dụng xử lý dữ liệu trong bộ nhớ 10 phút rồi mới commit.

Một số hệ quản trị cung cấp cả thời điểm bắt đầu và khoảng thời gian đã trôi qua; một số cung cấp bộ đếm giây theo trạng thái. Hãy xác định rõ cột thời gian có nghĩa là “từ lúc đăng nhập”, “từ lúc câu lệnh bắt đầu”, “từ lúc session đổi trạng thái” hay “từ lúc transaction bắt đầu”.

## 3. Vì sao transaction mở lâu đáng quan tâm?

Transaction mở lâu có thể gây ra nhiều ảnh hưởng ngay cả khi session đang `idle`:

1. **Giữ khóa:** khóa đã lấy có thể được giữ đến commit hoặc rollback, làm transaction khác phải chờ.
2. **Giữ snapshot cũ:** các phiên bản dữ liệu cũ có thể cần được giữ lại để transaction còn đọc được.
3. **Cản trở dọn dẹp phiên bản:** với MVCC, transaction cũ có thể giữ mốc đọc khiến vacuum hoặc purge chưa loại bỏ được phiên bản không còn cần thiết.
4. **Tăng undo/version storage:** thay đổi và phiên bản cũ có thể tích tụ, làm tăng I/O và áp lực bộ nhớ/đĩa.
5. **Tăng rủi ro deadlock:** transaction giữ tài nguyên lâu hơn làm cửa sổ xung đột lớn hơn.
6. **Khó phục hồi:** rollback một transaction thay đổi nhiều dữ liệu có thể tốn thời gian.
7. **Làm connection pool cạn:** nếu ứng dụng giữ connection trong lúc chờ người dùng hoặc dịch vụ bên ngoài, request mới có thể không lấy được connection.

Một session `idle in transaction` thường là dấu hiệu đáng điều tra vì ứng dụng đã gửi xong câu lệnh nhưng chưa kết thúc transaction. Tuy nhiên, không phải mọi transaction lâu đều là lỗi: báo cáo dài, batch lớn hoặc tác vụ bảo trì có thể cần thời gian. Cần đối chiếu tuổi transaction với loại công việc, trạng thái chờ, số khóa, lượng dữ liệu thay đổi và SLA.

## 4. Thông tin nên thu thập cho mỗi session

Một ảnh chụp chẩn đoán hữu ích nên có các trường sau nếu DBMS cung cấp:

| Nhóm | Trường gợi ý | Ý nghĩa |
|---|---|---|
| Nhận diện | Session ID, user, database, host/client address, application name | Xác định kết nối thuộc service hoặc người vận hành nào. |
| Trạng thái | Active, idle, sleeping, idle in transaction, suspended | Biết session đang làm gì. |
| Tuổi | Session start, query start, transaction start, state change | Tách ba loại thời gian. |
| SQL | Current query, previous query, query ID, SQL handle | Tìm câu lệnh liên quan; chú ý dữ liệu nhạy cảm trong SQL text. |
| Chờ khóa | Wait type/event, resource, blocker session | Xác định session đang chờ ai và vì tài nguyên nào. |
| Transaction | Transaction ID, isolation level, read-only/read-write, open transaction count | Hiểu phạm vi và trạng thái transaction. |
| Quy mô | Rows locked/modified, undo/version usage, log bytes nếu có | Ước lượng tác động và chi phí rollback. |

Nên lưu cả thời điểm thu thập và múi giờ. Khi đối chiếu log ứng dụng với database, đồng hồ máy ứng dụng và database cần được đồng bộ hoặc có quy tắc quy đổi rõ ràng.

## 5. PostgreSQL: thu thập session và transaction đang mở

PostgreSQL cung cấp view `pg_stat_activity` để xem session, trạng thái và truy vấn. Một truy vấn tổng hợp thường dùng:

```sql
SELECT pid,
       usename,
       datname,
       application_name,
       client_addr,
       state,
       clock_timestamp() - backend_start AS session_age,
       clock_timestamp() - query_start AS query_age,
       clock_timestamp() - xact_start AS transaction_age,
       clock_timestamp() - state_change AS state_age,
       wait_event_type,
       wait_event,
       pg_blocking_pids(pid) AS blocking_pids,
       backend_xid,
       backend_xmin,
       left(query, 1000) AS query_sample
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
```

Ý nghĩa các cột thời gian:

- `backend_start`: thời điểm backend/session được tạo; dùng để tính tuổi session.
- `query_start`: thời điểm câu lệnh hiện tại bắt đầu nếu session đang `active`; khi session không active, giá trị này phản ánh thời điểm câu lệnh gần nhất bắt đầu, nên không được coi là tuổi câu lệnh đang chạy.
- `xact_start`: thời điểm transaction hiện tại bắt đầu; `NULL` nếu không có transaction đang mở.
- `state_change`: thời điểm session chuyển sang trạng thái hiện tại; hữu ích để biết session đã `idle` hoặc `idle in transaction` bao lâu.

### 5.1. Tìm session idle in transaction

```sql
SELECT pid,
       usename,
       application_name,
       client_addr,
       clock_timestamp() - xact_start AS transaction_age,
       clock_timestamp() - state_change AS idle_in_state_for,
       wait_event_type,
       wait_event,
       pg_blocking_pids(pid) AS blocking_pids,
       left(query, 1000) AS last_query
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
```

`idle in transaction` có nghĩa session không chạy câu lệnh tại thời điểm lấy mẫu nhưng transaction vẫn mở. `idle in transaction (aborted)` cho biết transaction đã ở trạng thái lỗi sau một câu SQL thất bại và vẫn chưa được rollback.

### 5.2. Xem blocker và lock

```sql
SELECT blocked.pid AS blocked_pid,
       blocked.application_name AS blocked_app,
       blocked.wait_event_type,
       blocked.wait_event,
       blocker.pid AS blocker_pid,
       blocker.application_name AS blocker_app,
       blocker.state AS blocker_state,
       clock_timestamp() - blocker.xact_start AS blocker_xact_age,
       left(blocker.query, 500) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker ON blocker.pid = p.blocker_pid
ORDER BY blocker.xact_start NULLS LAST;
```

Một blocker có thể đang `idle in transaction`: nó không chạy SQL nhưng vẫn giữ khóa mà session khác cần. Đây là lý do cần thu thập transaction age và state cùng lúc.

### 5.3. Transaction age và vacuum horizon

Với PostgreSQL, transaction cũ có thể giữ `backend_xmin` và làm vacuum không thể loại bỏ các tuple version cũ mà snapshot đó còn cần. Khi điều tra table bloat hoặc autovacuum không tiến triển, ngoài `xact_start` hãy quan sát `backend_xmin`, tuổi XID và thông tin vacuum.

```sql
SELECT pid,
       usename,
       application_name,
       state,
       xact_start,
       age(backend_xmin) AS backend_xmin_age,
       clock_timestamp() - xact_start AS transaction_age,
       left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;
```

`backend_xmin` là mốc transaction ID mà backend có thể cần giữ lại; tuổi lớn có thể góp phần giữ vacuum horizon. Không nên coi một giá trị lớn đơn lẻ là bằng chứng duy nhất của wraparound risk. Cần đối chiếu `age(datfrozenxid)` của database, `age(relfrozenxid)` của bảng và cảnh báo autovacuum.

### 5.4. Quyền xem dữ liệu

Người dùng thông thường có thể chỉ thấy đầy đủ chi tiết của session thuộc chính mình; để xem thông tin của các session khác cần quyền phù hợp, ví dụ `pg_read_all_stats` hoặc quyền quản trị. Query text có thể chứa literal nhạy cảm; hãy giới hạn quyền và tránh lưu log SQL thô nếu không cần.

## 6. MySQL InnoDB: xem transaction đang hoạt động

MySQL InnoDB cung cấp `INFORMATION_SCHEMA.INNODB_TRX` để xem transaction InnoDB đang mở:

```sql
SELECT trx_id,
       trx_state,
       trx_started,
       TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS transaction_age_seconds,
       trx_wait_started,
       trx_mysql_thread_id AS connection_id,
       trx_query,
       trx_tables_locked,
       trx_lock_structs,
       trx_rows_locked,
       trx_rows_modified,
       trx_isolation_level
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Các cột hữu ích:

- `trx_started`: thời điểm transaction bắt đầu.
- `trx_state`: trạng thái transaction, chẳng hạn `RUNNING` hoặc `LOCK WAIT`.
- `trx_wait_started`: thời điểm bắt đầu chờ khóa nếu có.
- `trx_mysql_thread_id`: connection ID tương ứng trong process list.
- `trx_rows_locked` và `trx_rows_modified`: ước lượng quy mô khóa và thay đổi do transaction giữ.

Kết hợp với process list để biết session và ứng dụng:

```sql
SELECT p.ID,
       p.USER,
       p.HOST,
       p.DB,
       p.COMMAND,
       p.TIME,
       p.STATE,
       p.INFO,
       t.trx_state,
       t.trx_started,
       TIMESTAMPDIFF(SECOND, t.trx_started, NOW()) AS transaction_age_seconds
FROM information_schema.processlist AS p
LEFT JOIN information_schema.innodb_trx AS t
       ON t.trx_mysql_thread_id = p.ID
WHERE p.ID <> CONNECTION_ID()
ORDER BY t.trx_started;
```

`processlist.TIME` là thời gian session ở trạng thái hiện tại, không phải tuổi transaction. Dùng `trx_started` để đo transaction age. Một connection có thể đang `Sleep` trong process list nhưng vẫn xuất hiện trong `INNODB_TRX`, nghĩa là ứng dụng đã để transaction mở khi không gửi câu SQL.

### 6.1. Tìm lock wait và blocker

Trong MySQL 8, `performance_schema.data_locks` và `performance_schema.data_lock_waits` cung cấp thông tin khóa và quan hệ chờ. Có thể nối chúng với `performance_schema.threads` hoặc `INNODB_TRX` để tìm thread chờ và thread chặn. Cấu trúc cột phụ thuộc phiên bản; hãy dùng tài liệu của bản MySQL đang chạy.

Để xem nhanh thông tin InnoDB gần nhất:

```sql
SHOW ENGINE INNODB STATUS;
```

Phần `TRANSACTIONS` giúp xem transaction đang mở, lock wait và một số chi tiết về khóa. Phần `History list length` hỗ trợ đánh giá lượng undo history đang chờ purge. Một transaction hoặc read view lâu đời có thể ngăn purge dọn các phiên bản cũ và làm history list tăng.

### 6.2. Phân biệt session ngủ và transaction đóng

`Sleep` chỉ mô tả trạng thái connection không chạy câu lệnh. Nó không chứng minh connection không có transaction mở. Luôn đối chiếu process list với `INNODB_TRX`. Khi một connection ngủ nhưng có transaction trong `INNODB_TRX`, cần điều tra ứng dụng đã quên commit/rollback hay đang cố ý giữ transaction qua một bước xử lý.

## 7. SQL Server: session, request và transaction

SQL Server lưu thông tin session và request ở các Dynamic Management Views (DMV). Một truy vấn chẩn đoán có thể nối session, request và transaction:

```sql
SELECT s.session_id,
       s.login_name,
       s.host_name,
       s.program_name,
       s.status AS session_status,
       s.open_transaction_count,
       tran.transaction_id,
       tran.name AS transaction_name,
       tran.transaction_begin_time,
       DATEDIFF(SECOND, tran.transaction_begin_time, SYSDATETIME())
           AS transaction_age_seconds,
       r.status AS request_status,
       r.command,
       r.start_time AS request_start_time,
       CASE WHEN r.start_time IS NOT NULL
            THEN DATEDIFF(SECOND, r.start_time, SYSDATETIME())
       END AS request_age_seconds,
       r.wait_type,
       r.wait_time,
       r.blocking_session_id,
       DB_NAME(dt.database_id) AS database_name,
       txt.text AS request_sql
FROM sys.dm_exec_sessions AS s
LEFT JOIN sys.dm_tran_session_transactions AS st
       ON st.session_id = s.session_id
LEFT JOIN sys.dm_tran_active_transactions AS tran
       ON tran.transaction_id = st.transaction_id
LEFT JOIN sys.dm_tran_database_transactions AS dt
       ON dt.transaction_id = tran.transaction_id
LEFT JOIN sys.dm_exec_requests AS r
       ON r.session_id = s.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) AS txt
WHERE s.is_user_process = 1
ORDER BY tran.transaction_begin_time;
```

Một transaction có thể xuất hiện nhiều dòng nếu nó liên quan đến nhiều database. Khi tổng hợp báo cáo, hãy nhóm theo `transaction_id` hoặc chọn đúng database để tránh đếm trùng.

Các DMV có vai trò khác nhau:

- `sys.dm_exec_sessions`: session, login, host, chương trình và số transaction mở được session báo cáo.
- `sys.dm_exec_requests`: request hiện đang thực thi, thời điểm bắt đầu, trạng thái, wait type và blocker.
- `sys.dm_tran_session_transactions`: ánh xạ session với transaction.
- `sys.dm_tran_active_transactions`: thời điểm bắt đầu và trạng thái transaction.
- `sys.dm_tran_database_transactions`: thông tin transaction theo database và lượng log liên quan.
- `sys.dm_tran_locks`: tài nguyên và chế độ khóa đang được giữ/yêu cầu.

### 7.1. Tìm session ngủ nhưng còn transaction mở

```sql
SELECT s.session_id,
       s.login_name,
       s.host_name,
       s.program_name,
       s.status,
       s.open_transaction_count,
       tran.transaction_begin_time,
       DATEDIFF(SECOND, tran.transaction_begin_time, SYSDATETIME())
           AS transaction_age_seconds
FROM sys.dm_exec_sessions AS s
JOIN sys.dm_tran_session_transactions AS st
  ON st.session_id = s.session_id
JOIN sys.dm_tran_active_transactions AS tran
  ON tran.transaction_id = st.transaction_id
LEFT JOIN sys.dm_exec_requests AS r
  ON r.session_id = s.session_id
WHERE s.is_user_process = 1
  AND r.session_id IS NULL
ORDER BY tran.transaction_begin_time;
```

`r.session_id IS NULL` cho biết session hiện không có request đang chạy; nó vẫn có thể giữ transaction mở. Đây là cách phát hiện một số trường hợp sleeping session với open transaction.

### 7.2. Xem blocker và wait

`blocking_session_id`, `wait_type`, `wait_time` trong `sys.dm_exec_requests` giúp tìm request đang chờ. Với chuỗi blocker phức tạp, kết hợp `sys.dm_os_waiting_tasks`, `sys.dm_tran_locks` và thông tin transaction để dựng quan hệ chờ.

Quyền cần thiết phụ thuộc phiên bản SQL Server. Các bản mới có thể yêu cầu `VIEW SERVER PERFORMANCE STATE`; các bản trước thường dùng `VIEW SERVER STATE`. Không cấp quyền rộng chỉ để một dashboard xem thông tin session nếu có thể giới hạn qua view/procedure được kiểm soát.

## 8. Oracle Database: V$SESSION và V$TRANSACTION

Oracle có thể theo dõi session trong `V$SESSION` và transaction đang mở trong `V$TRANSACTION`. Ghép qua địa chỉ transaction (`TADDR` và `ADDR`) để tính tuổi transaction:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status AS session_status,
       s.machine,
       s.program,
       s.module,
       s.sql_id,
       s.prev_sql_id,
       s.sql_exec_start,
       CASE WHEN s.sql_exec_start IS NOT NULL
            THEN ROUND((SYSDATE - s.sql_exec_start) * 86400)
       END AS current_sql_age_seconds,
       s.last_call_et,
       s.event,
       s.wait_class,
       s.blocking_session,
       s.logon_time,
       t.start_date AS transaction_start,
       CASE WHEN t.start_date IS NOT NULL
            THEN ROUND((SYSDATE - t.start_date) * 86400)
       END AS transaction_age_seconds,
       t.used_ublk,
       t.used_urec
FROM v$session s
LEFT JOIN v$transaction t
       ON t.addr = s.taddr
WHERE s.type = 'USER'
ORDER BY t.start_date NULLS LAST;
```

Các trường thời gian cần phân biệt:

- `LOGON_TIME`: thời điểm session đăng nhập, dùng để tính tuổi session.
- `SQL_EXEC_START`: thời điểm câu SQL hiện tại bắt đầu khi session đang thực thi SQL.
- `V$TRANSACTION.START_DATE`: thời điểm transaction bắt đầu.
- `LAST_CALL_ET`: số giây kể từ khi session chuyển sang trạng thái `ACTIVE` hoặc `INACTIVE` tương ứng; không thay thế trực tiếp transaction age.

`V$TRANSACTION` chỉ có dòng cho transaction đang hoạt động. Session `INACTIVE` vẫn có thể có `TADDR` và một transaction mở; vì vậy cần nối hai view thay vì chỉ lọc `V$SESSION.STATUS = 'ACTIVE'`.

### 8.1. Xem blocker

Các cột `BLOCKING_SESSION`, `BLOCKING_INSTANCE` và thông tin event trong `V$SESSION` giúp xác định session đang chặn. Các view `V$LOCK`, `DBA_BLOCKERS` và `DBA_WAITERS` cũng hữu ích tùy quyền và phiên bản. Với Oracle RAC, dùng các view `GV$` và bao gồm `INST_ID` để phân biệt session ở các instance khác nhau.

Quyền đọc các view động thường cần quyền phù hợp như `SELECT_CATALOG_ROLE` hoặc quyền truy cập view được cấp riêng. Chỉ cấp quyền tối thiểu cần thiết cho công cụ giám sát.

## 9. Một session idle không có nghĩa transaction đã kết thúc

Đây là một trong những lỗi diễn giải phổ biến nhất. Trạng thái `idle`, `Sleep`, `sleeping` hoặc `INACTIVE` nói rằng session không thực hiện request tại thời điểm quan sát. Nó không nhất thiết nói rằng transaction đã commit hoặc rollback.

Ví dụ:

```sql
BEGIN;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 99;

-- Ứng dụng tạm dừng để gọi dịch vụ khác.
-- Không có câu SQL đang chạy, nhưng transaction chưa commit.
```

Nếu ứng dụng giữ connection và chờ phản hồi dịch vụ trong 30 giây, session có thể xuất hiện là idle/sleeping nhưng transaction vẫn giữ khóa trên hàng tồn kho. Các request khác cần cùng hàng sẽ phải chờ.

Trong vận hành, nên có dashboard hoặc truy vấn riêng cho:

- Session đang active và query age vượt ngưỡng.
- Session đang chờ lock và blocker tương ứng.
- Session idle trong khi transaction vẫn mở.
- Transaction age vượt ngưỡng theo loại ứng dụng.
- Transaction lâu nhất trong mỗi database hoặc service.
- Connection pool có nhiều session đang ngủ nhưng vẫn có transaction mở.

## 10. Tuổi transaction không phải lúc nào cũng là thời gian giữ khóa

Transaction age cho biết thời gian từ khi transaction bắt đầu. Nó không trực tiếp đo thời gian một khóa cụ thể đã được giữ.

Ví dụ, transaction có thể bắt đầu bằng một `SELECT` không khóa, chờ 5 phút trong ứng dụng, sau đó mới cập nhật một hàng. Tuổi transaction là 5 phút nhưng khóa ghi chỉ được giữ từ lúc `UPDATE`. Ngược lại, một transaction có thể lấy khóa ngay ở câu lệnh đầu rồi chờ 10 phút trước commit; khi đó tuổi transaction và thời gian giữ khóa đều dài.

Muốn hiểu tác động thực tế, hãy kết hợp:

- Transaction age.
- Session state và state age.
- Lock inventory và lock wait graph.
- Thời điểm câu lệnh cập nhật/locking read bắt đầu.
- Số hàng bị khóa hoặc thay đổi nếu DBMS cung cấp.
- Log ứng dụng để biết transaction đang chờ bước nào.

Không kết luận rằng transaction lâu nhất luôn là blocker nguy hiểm nhất. Một transaction lâu nhưng chỉ đọc snapshot có thể không chặn writer theo cơ chế MVCC thông thường, dù vẫn có thể giữ vacuum horizon. Một transaction ngắn hơn nhưng đang giữ khóa trên hàng nóng có thể gây ảnh hưởng lớn hơn.

## 11. Tìm transaction lâu nhất và đặt ngưỡng cảnh báo

Một dashboard có thể hiển thị danh sách transaction đang mở, sắp xếp theo tuổi giảm dần. Ngưỡng cảnh báo nên khác nhau theo workload:

| Loại workload | Cách đặt ngưỡng |
|---|---|
| API OLTP | Transaction thường ngắn; tuổi vài giây có thể đã cần điều tra nếu có lock wait. |
| Batch update | Cho phép lâu hơn, nhưng theo dõi batch duration, rows modified, log và blocker. |
| Báo cáo dài | Theo dõi snapshot age, tác động vacuum/undo và tài nguyên đọc. |
| Migration/DDL | Theo dõi lock mode, blocker và cửa sổ bảo trì; không chỉ dựa trên transaction age. |
| Tác vụ tương tác với người dùng | Transaction không nên mở trong lúc người dùng nhập liệu hoặc chờ thao tác. |

Không dùng một ngưỡng cố định như 60 giây cho mọi transaction. Một transaction 3 giây đang chặn hàng trăm request có thể nghiêm trọng hơn transaction báo cáo 20 phút chạy chỉ đọc trên snapshot được kiểm soát.

Một chính sách cảnh báo có thể kết hợp điều kiện:

- Transaction age vượt ngưỡng của loại workload.
- Session đang idle in transaction.
- Có session khác đang chờ nó.
- Số hàng khóa hoặc log/undo usage vượt ngưỡng.
- Transaction giữ `xmin` hoặc read view quá cũ.

## 12. Thu thập định kỳ và lưu lịch sử

Các view session thường phản ánh trạng thái hiện tại, không phải lịch sử đầy đủ. Deadlock hoặc lock wait có thể biến mất trước khi dashboard truy vấn kịp. Để điều tra xu hướng, cần lấy mẫu định kỳ và lưu các trường cần thiết.

Một thiết kế thu thập cơ bản:

1. Chạy collector theo chu kỳ phù hợp, chẳng hạn mỗi 10–30 giây cho dashboard vận hành; điều chỉnh theo tải và độ nhạy cần thiết.
2. Ghi thời điểm sample, DBMS, instance, session ID, user, application, state, transaction start, query start và wait.
3. Chỉ lưu SQL text khi cần và đã có chính sách che dữ liệu nhạy cảm.
4. Ghi nhận session ID có thể được tái sử dụng; kết hợp session start/logon time hoặc transaction ID để định danh một vòng đời.
5. Lưu lịch sử đủ lâu để so sánh trước/sau khi deploy hoặc khi xuất hiện lock contention.
6. Giới hạn dung lượng và retention của bảng telemetry để chính công cụ giám sát không tạo tải quá lớn.

Tần suất lấy mẫu quá dày có thể tạo overhead và vẫn bỏ lỡ một sự kiện rất ngắn. Đối với deadlock, hãy bật cơ chế log/event chuyên dụng của DBMS thay vì chỉ dựa vào polling.

## 13. Gắn session với service và request ứng dụng

Session ID chỉ hữu ích khi có thể biết nó thuộc ứng dụng nào. Hãy thiết lập metadata nhận diện nếu DBMS và driver hỗ trợ:

- Application name hoặc program name.
- Host/container/pod hoặc worker ID.
- Database user hoặc role riêng theo service.
- Module/action hoặc client identifier.
- Request/trace ID được truyền qua session context khi phù hợp.

Ví dụ PostgreSQL có `application_name`; SQL Server có `program_name` và session context; Oracle có `MODULE`, `ACTION`, `CLIENT_IDENTIFIER`; MySQL có thể nhận diện qua user, host, process list và Performance Schema. Dùng connection initialization hoặc API driver phù hợp để đặt các giá trị này.

Không nhúng token, mật khẩu hoặc thông tin cá nhân vào `application_name`, module hoặc query comment. Metadata nên đủ để truy ngược service và loại công việc nhưng không làm lộ bí mật.

## 14. Xử lý transaction mở lâu

Khi phát hiện transaction lâu, hãy điều tra trước khi kết thúc session:

1. Xác định session thuộc service, worker hay người dùng nào.
2. Xem session đang active, idle, sleeping hay idle in transaction.
3. Đo transaction age và xác định câu SQL gần nhất.
4. Kiểm tra session có đang chặn transaction khác hay giữ snapshot cũ không.
5. Đối chiếu log ứng dụng để biết transaction đang chờ I/O, dịch vụ ngoài, thread pool hay logic người dùng.
6. Xác định có thể để transaction hoàn tất tự nhiên, yêu cầu ứng dụng rollback, hoặc cần kết thúc session.
7. Theo dõi quá trình rollback và xác nhận khóa được giải phóng.

Không kết thúc session chỉ vì tuổi lớn. Rollback transaction lớn có thể mất thời gian và tạo thêm I/O. Nếu session thuộc migration, batch hoặc tác vụ bảo trì, hủy giữa chừng có thể làm công việc phải chạy lại hoặc cần phục hồi.

### 14.1. Hủy câu lệnh và kết thúc session khác nhau

Tùy DBMS, thao tác cancel query thường chỉ dừng câu SQL hiện tại; transaction có thể vẫn mở. Terminate/kill session thường đóng session và làm transaction chưa commit rollback, nhưng cleanup có thể mất thời gian.

- PostgreSQL có `pg_cancel_backend(pid)` để yêu cầu hủy câu lệnh và `pg_terminate_backend(pid)` để kết thúc backend.
- MySQL có `KILL QUERY connection_id` để hủy câu lệnh hiện tại và `KILL CONNECTION connection_id` để kết thúc connection.
- SQL Server có `KILL session_id`; rollback có thể tiếp tục sau khi lệnh kill được gửi. `KILL session_id WITH STATUSONLY` có thể báo tiến độ rollback.
- Oracle có thể dùng `ALTER SYSTEM KILL SESSION 'sid,serial#'` theo quyền và quy trình vận hành; trong RAC cần xác định instance phù hợp. Một số trường hợp session được đánh dấu để cleanup bất đồng bộ.

Chỉ thực hiện thao tác này theo quy trình vận hành có thẩm quyền. Xác minh session ID và vòng đời kết nối trước khi kill vì ID có thể được tái sử dụng hoặc thuộc một tác vụ quan trọng.

## 15. Các biện pháp ngăn transaction mở lâu

- Giữ transaction chỉ bao quanh các câu lệnh database cần commit/rollback cùng nhau.
- Không chờ người dùng, HTTP, file hoặc message broker trong lúc transaction đang mở.
- Đặt timeout phù hợp cho query, lock wait và transaction.
- Dùng `try/finally` hoặc transaction manager để rollback khi exception.
- Trả connection về pool chỉ sau khi transaction đã kết thúc và session được reset.
- Với batch lớn, chia thành đơn vị commit độc lập khi nghiệp vụ cho phép.
- Với tác dụng phụ ngoài database, cân nhắc transactional outbox.
- Theo dõi `idle in transaction`, sleeping session có open transaction và transaction age theo service.
- Kiểm tra connection leak và đường code bỏ sót commit/rollback.

Một số DBMS có timeout chuyên biệt để giới hạn session idle trong transaction. Ví dụ PostgreSQL có `idle_in_transaction_session_timeout`; MySQL có các timeout session/transaction phù hợp từng tình huống, nhưng `wait_timeout` chủ yếu xử lý connection idle và không thay thế chính sách transaction; SQL Server và Oracle có các cơ chế quản lý session/resource riêng. Cần kiểm tra tác động của timeout trước khi bật rộng vì nó có thể hủy một công việc hợp lệ.

## 16. Checklist khi thu thập session và transaction age

- [ ] Đã phân biệt tuổi session, tuổi query và tuổi transaction.
- [ ] Đã thu thập session ID, user, database, host và application/service name.
- [ ] Đã ghi trạng thái active/idle/sleeping/idle in transaction.
- [ ] Đã lấy transaction start time và query start time từ nguồn phù hợp của DBMS.
- [ ] Đã kiểm tra session idle nhưng vẫn có transaction mở.
- [ ] Đã thu thập wait event/type, blocker và lock resource.
- [ ] Đã xem xét tác động MVCC, vacuum/purge hoặc undo/version storage.
- [ ] Đã xác định quyền cần thiết và giới hạn truy cập SQL text nhạy cảm.
- [ ] Đã lấy mẫu lịch sử với tần suất và retention hợp lý.
- [ ] Đã xác minh session thuộc workload nào trước khi cancel hoặc terminate.
- [ ] Đã theo dõi rollback/cleanup và xác nhận khóa được giải phóng.
- [ ] Đã có timeout và transaction cleanup trong code ứng dụng.

Thu thập session, transaction đang mở và tuổi transaction giúp phân biệt một connection tồn tại lâu bình thường với một transaction thực sự giữ tài nguyên quá lâu. Hãy kết hợp trạng thái session, thời điểm bắt đầu, blocker, lock footprint và tác động MVCC để xác định mức độ ảnh hưởng. Khi xử lý, ưu tiên hiểu transaction đang làm gì và thuộc workload nào; chỉ cancel hoặc terminate sau khi đã đánh giá tác động và có cách xác nhận rollback hoàn tất.
