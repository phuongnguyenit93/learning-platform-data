# Ảnh hưởng của giao dịch chỉ đọc kéo dài đến lưu giữ phiên bản

Trong các hệ quản trị dùng MVCC (Multi-Version Concurrency Control), một truy vấn chỉ đọc vẫn có thể ảnh hưởng đáng kể đến hoạt động ghi và dọn dẹp dữ liệu. Khi transaction đọc giữ một snapshot cũ trong thời gian dài, database phải bảo toàn những phiên bản dòng mà snapshot đó còn có thể nhìn thấy. Các transaction khác vẫn tiếp tục `UPDATE` hoặc `DELETE`, tạo ra phiên bản mới, nhưng cơ chế cleanup chưa thể thu hồi phiên bản cũ cần cho reader.

Hậu quả phụ thuộc DBMS: PostgreSQL có thể tích lũy dead tuples và làm VACUUM bị giới hạn bởi visibility horizon; InnoDB có thể giữ undo history khiến purge không theo kịp; SQL Server có thể giữ row versions trong version store; Oracle có thể cần undo lâu hơn để dựng consistent read và gặp `ORA-01555` nếu undo bị ghi đè trước khi truy vấn hoàn tất.

Điểm quan trọng là **read-only không có nghĩa là không giữ tài nguyên**. Một transaction không ghi dữ liệu vẫn có thể giữ snapshot, version hoặc metadata lock. Cần phân biệt thời gian chạy của một câu `SELECT` với thời gian tồn tại của transaction chứa nó, vì mỗi DBMS và isolation level có quy tắc snapshot riêng.

## 1. MVCC và lý do phải giữ phiên bản cũ

MVCC cho phép reader nhìn thấy một phiên bản dữ liệu nhất quán trong khi writer tạo phiên bản mới. Thay vì bắt reader và writer luôn chặn nhau, database giữ lại các phiên bản cần thiết để mỗi snapshot nhìn thấy đúng trạng thái theo thời điểm của nó.

Ví dụ một tài khoản bắt đầu với số dư 100:

```text
Reader R lấy snapshot S1 và đọc balance = 100
                         |
Writer W1 cập nhật balance = 90 và COMMIT
                         |
Writer W2 cập nhật balance = 70 và COMMIT
                         |
Reader R vẫn cần nhìn thấy balance = 100
```

Reader R phải tiếp tục thấy giá trị 100 theo snapshot cũ, dù trạng thái hiện tại đã là 70. Nếu database xóa phiên bản 100 ngay sau W1 commit, R không thể dựng lại kết quả đúng. Vì thế, hệ thống giữ phiên bản cũ cho đến khi chắc chắn không còn reader nào cần nó.

Một snapshot thường xác định transaction nào đã commit, transaction nào còn hoạt động và transaction nào bắt đầu sau ranh giới quan sát. Từ thông tin đó, engine quyết định version nào visible. **Snapshot càng cũ, phạm vi version cần giữ càng có thể lớn**, đặc biệt khi workload ghi liên tục trên cùng các bảng.

### 1.1. Reader không nhất thiết khóa dòng

Một ưu điểm của MVCC là truy vấn consistent read thông thường thường không cần khóa độc quyền các dòng mà nó đọc. Writer có thể tiếp tục cập nhật, còn reader đọc phiên bản phù hợp với snapshot. Điều này giảm blocking trực tiếp nhưng chuyển một phần chi phí sang lưu trữ và cleanup version.

Không nên suy luận rằng reader không giữ lock nào. Ví dụ, PostgreSQL vẫn lấy table-level `ACCESS SHARE` lock cho câu `SELECT`, thường giữ đến hết transaction; lock này tương thích với phần lớn thao tác đọc/ghi thông thường nhưng xung đột với một số DDL cần `ACCESS EXCLUSIVE`. InnoDB cũng quản lý metadata lock cho table được truy cập. SQL Server có schema stability lock trong lúc truy vấn. Mức lock cụ thể phụ thuộc câu lệnh, isolation và DBMS.

### 1.2. Câu lệnh dài và transaction dài là hai trường hợp khác nhau

- **Long-running statement:** một câu `SELECT` chạy lâu giữ snapshot cần cho toàn bộ thời gian thực thi câu lệnh.
- **Long-running transaction:** transaction có thể giữ snapshot qua nhiều statement, tùy isolation level và engine.
- **Idle transaction:** không chạy câu lệnh nhưng transaction vẫn mở. Nó có thể giữ snapshot ổn định hoặc metadata/lock, tùy DBMS và isolation.

Một câu SELECT chạy 20 phút có thể giữ version trong 20 phút dù nó là câu lệnh duy nhất. Một transaction `REPEATABLE READ` mở 20 phút có thể giữ snapshot qua nhiều câu lệnh, kể cả những khoảng thời gian ứng dụng không chạy SQL. Cần đo cả query age lẫn transaction age.

## 2. Thời gian giữ snapshot theo isolation level

Tên isolation level giống nhau không bảo đảm mọi DBMS giữ snapshot giống nhau.

| DBMS / chế độ đọc | Snapshot thường được giữ đến khi nào? | Rủi ro với version cleanup |
|---|---|---|
| PostgreSQL `READ COMMITTED` | Mỗi statement có snapshot riêng | Câu SELECT chạy lâu giữ snapshot đến khi statement kết thúc; transaction idle giữa các statement thường không giữ cùng snapshot ổn định |
| PostgreSQL `REPEATABLE READ` / `SERIALIZABLE` | Snapshot ổn định cho transaction | Transaction kéo dài có thể giữ xmin cũ qua nhiều statement |
| MySQL InnoDB `READ COMMITTED` | Consistent read thường lấy read view mới cho mỗi statement | Statement dài giữ read view trong lúc chạy |
| MySQL InnoDB `REPEATABLE READ` | Read view của consistent read thường được giữ đến hết transaction | Transaction đọc một lần rồi idle vẫn có thể giữ undo history cần cho read view |
| SQL Server RCSI | Row-version snapshot theo statement | Một statement dài làm version cần thiết chưa được cleanup |
| SQL Server `SNAPSHOT` | Snapshot theo transaction | Transaction chỉ đọc kéo dài có thể giữ version store lâu |
| Oracle read consistency thông thường | Consistent read theo statement/SCN của query | Query dài cần undo đủ lâu để dựng block version tại SCN ban đầu |
| Oracle `SET TRANSACTION READ ONLY` | Transaction-level read consistency | Các statement trong transaction cần cùng góc nhìn; undo cũ có thể phải được giữ lâu hơn |

Đây là mô hình khái quát. Cần kiểm tra tài liệu phiên bản DBMS, loại truy vấn, cursor và các tùy chọn snapshot đặc biệt trước khi suy ra thời gian giữ version chính xác.

## 3. PostgreSQL: snapshot cũ giữ dead tuples

PostgreSQL lưu các tuple version trong heap. Khi một dòng được cập nhật hoặc xóa, tuple cũ không nhất thiết bị xóa vật lý ngay. VACUUM chỉ có thể thu hồi tuple khi visibility horizon cho biết không còn snapshot nào cần nó.

### 3.1. READ COMMITTED: snapshot theo statement

Ở `READ COMMITTED`, mỗi câu lệnh thông thường lấy snapshot mới. Một transaction có thể mở lâu nhưng nếu câu `SELECT` đã kết thúc và không có cơ chế nào khác giữ snapshot, câu lệnh tiếp theo sẽ dùng snapshot mới hơn.

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance FROM account WHERE account_id = 7;
-- Statement kết thúc; snapshot của statement này không được giữ
-- làm snapshot cố định cho các câu tiếp theo.

-- Ứng dụng có thể idle trong transaction ở đây.

SELECT balance FROM account WHERE account_id = 7;
-- Statement mới lấy snapshot mới.

COMMIT;
```

Điều này không có nghĩa mọi transaction idle ở `READ COMMITTED` đều vô hại. Transaction có thể giữ table lock đến khi kết thúc; cursor, exported snapshot, thao tác ghi hoặc trạng thái backend khác có thể ảnh hưởng cleanup. Hãy xem `backend_xmin` thay vì chỉ dựa vào `xact_start`.

### 3.2. REPEATABLE READ: snapshot ổn định đến hết transaction

Ở `REPEATABLE READ`, PostgreSQL giữ snapshot ổn định cho transaction. Nếu reader đã lấy snapshot rồi tiếp tục idle, các writer khác vẫn có thể cập nhật dữ liệu, nhưng VACUUM phải bảo toàn các tuple mà reader cũ có thể nhìn thấy.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT balance
FROM account
WHERE account_id = 7;

-- Giữ transaction mở; các statement sau vẫn dùng snapshot cũ.
-- Kết thúc bằng COMMIT hoặc ROLLBACK.
```

`READ ONLY` chỉ giới hạn loại thao tác được phép trong transaction; nó không làm snapshot hết hiệu lực sớm hơn. Một báo cáo chỉ đọc vẫn có thể giữ xmin cũ và ngăn VACUUM thu hồi tuple.

### 3.3. VACUUM và table bloat

Giả sử một báo cáo `REPEATABLE READ` bắt đầu lúc bảng có version V1. Sau đó các worker tạo V2, V3, V4. Reader vẫn cần V1; VACUUM không thể thu hồi các version cần cho snapshot đó. Khi workload ghi tiếp tục, dead tuple tăng, page chứa nhiều dữ liệu chết và relation có thể phình to.

Hậu quả:

- Heap/index lớn hơn so với lượng dữ liệu sống.
- Sequential scan phải đi qua nhiều page hơn.
- Cache chứa ít dữ liệu hữu ích hơn.
- VACUUM phải xử lý backlog lớn sau khi snapshot cũ kết thúc.
- Autovacuum có thể chạy liên tục nhưng không thu hồi được các tuple bị horizon giữ lại.
- Áp lực freeze tăng nếu VACUUM không thể tiến qua transaction ID cũ.

VACUUM thường làm không gian có thể tái sử dụng bên trong relation; nó không nhất thiết thu nhỏ file trên filesystem. Không nên chạy `VACUUM FULL` như phản xạ đầu tiên, vì nó rewrite bảng và cần khóa mạnh.

### 3.4. Quan sát snapshot và VACUUM

Tìm backend giữ xmin:

```sql
SELECT pid,
       usename,
       application_name,
       state,
       xact_start,
       query_start,
       clock_timestamp() - xact_start AS transaction_age,
       backend_xmin,
       age(backend_xmin) AS xmin_age,
       left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;
```

Xem bảng có nhiều dead tuple:

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

Theo dõi VACUUM đang chạy:

```sql
SELECT pid,
       relid::regclass AS relation,
       phase,
       heap_blks_total,
       heap_blks_scanned,
       heap_blks_vacuumed
FROM pg_stat_progress_vacuum;
```

`n_dead_tup` là ước lượng thống kê. Một `backend_xmin` cũ là manh mối quan trọng nhưng không phải nguồn duy nhất giữ horizon; replication slot, prepared transaction và standby feedback cũng cần được kiểm tra.

### 3.5. Snapshot trên standby và hot_standby_feedback

Truy vấn dài trên hot standby có thể xung đột với WAL replay khi primary cần cleanup tuple. Nếu `hot_standby_feedback` bật, standby gửi thông tin xmin về primary để giảm query cancellation; đổi lại, primary có thể phải giữ dead tuple lâu hơn.

Đây là một trade-off giữa độ ổn định truy vấn báo cáo trên standby và bloat trên primary. Chuyển truy vấn sang replica không tự động loại bỏ chi phí giữ version. Cần theo dõi query age trên standby, feedback xmin, dead tuple trên primary và replication lag.

Replication slot cũng có thể giữ `xmin` hoặc `catalog_xmin`; `restart_lsn` giữ WAL. Đây là các cơ chế retention liên quan nhưng không giống nhau: giữ tuple version và giữ WAL cần được chẩn đoán riêng.

## 4. MySQL InnoDB: read view giữ undo history

InnoDB dùng undo log để dựng lại phiên bản cũ cho consistent read. Khi một transaction cập nhật dòng, thông tin cũ được lưu trong undo record. Reader có read view cũ có thể cần các undo record đó để nhìn thấy trạng thái đúng theo snapshot.

Purge thread của InnoDB chỉ có thể loại bỏ undo history khi không còn read view nào cần nó. Nếu một transaction `REPEATABLE READ` giữ snapshot lâu, purge không thể tiến qua các version cần cho snapshot đó. History list length có thể tăng, undo tablespace phình lên và cleanup phải làm nhiều việc hơn sau khi transaction kết thúc.

### 4.1. READ COMMITTED và REPEATABLE READ

Ở InnoDB `READ COMMITTED`, mỗi consistent read thường tạo read view mới. Ở `REPEATABLE READ`, các consistent read trong transaction thường dùng cùng read view sau khi nó được tạo. Do đó, một transaction chỉ đọc có thể giữ undo history dù hiện tại không có câu SQL nào đang chạy.

Ví dụ:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION READ ONLY;

SELECT balance
FROM account
WHERE account_id = 7;

-- Giữ transaction mở sau khi SELECT kết thúc.
-- Các UPDATE từ session khác tiếp tục tạo undo history.

COMMIT;
```

Nếu cần lấy read view ngay khi bắt đầu transaction cho một consistent snapshot, InnoDB hỗ trợ `START TRANSACTION WITH CONSISTENT SNAPSHOT` trong các điều kiện isolation phù hợp. Cần kiểm tra hành vi và cú pháp theo phiên bản MySQL đang chạy.

### 4.2. History list length và purge lag

`SHOW ENGINE INNODB STATUS` có phần TRANSACTIONS và thông tin `History list length`. Giá trị tăng liên tục có thể cho thấy purge không theo kịp hoặc một read view cũ đang giữ undo history. Không nên dùng một ngưỡng cố định cho mọi workload; hãy xem xu hướng, tốc độ tăng, lượng DML và dung lượng undo.

```sql
SHOW ENGINE INNODB STATUS\G
```

Tìm transaction mở lâu:

```sql
SELECT trx_id,
       trx_state,
       trx_started,
       TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
       trx_mysql_thread_id,
       trx_isolation_level,
       trx_is_read_only,
       trx_rows_locked,
       trx_rows_modified,
       trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Transaction read-only có thể có `trx_rows_locked` bằng 0 nhưng vẫn giữ read view và ảnh hưởng purge. Vì vậy, chỉ tìm transaction có nhiều row lock sẽ bỏ sót loại reader này.

### 4.3. Hậu quả và cách xử lý

- History list length tăng và purge lag kéo dài.
- Undo tablespace tăng kích thước hoặc không được truncate/reuse nhanh như kỳ vọng.
- DML chịu thêm chi phí quản lý version và purge backlog.
- Storage I/O tăng khi undo history lớn.
- Transaction lâu làm việc thu hồi undo chậm ngay cả khi nó không khóa row.

Biện pháp thường dùng là giữ transaction ngắn, tránh giữ consistent read qua thời gian chờ bên ngoài, chia báo cáo thành batch nếu có thể chấp nhận snapshot khác nhau, và theo dõi `innodb_trx` cùng InnoDB status. `innodb_lock_wait_timeout` điều khiển thời gian chờ lock, không giải quyết read view cũ đang giữ undo. Tăng timeout hoặc tăng purge thread không thể làm mất nhu cầu dữ liệu của snapshot còn hiệu lực.

## 5. SQL Server: row version store trong tempdb hoặc Persistent Version Store

SQL Server có thể dùng row versioning để phục vụ reader mà không cần giữ shared row lock lâu như locking read thông thường. Hai chế độ thường gặp:

- **READ_COMMITTED_SNAPSHOT (RCSI):** mỗi statement đọc một snapshot nhất quán tại thời điểm statement bắt đầu.
- **SNAPSHOT isolation:** transaction đọc theo snapshot được thiết lập cho transaction.

Các row version cần thiết được giữ trong version store. Một reader kéo dài có thể khiến cleanup không xóa được các version mà reader còn cần. Với cấu hình truyền thống, version store nằm trong `tempdb`; khi Accelerated Database Recovery (ADR) được bật, các version phục vụ ADR được lưu trong Persistent Version Store (PVS) ở user database. Cần phân biệt version store của row versioning và PVS theo cấu hình/version SQL Server.

### 5.1. RCSI và SNAPSHOT khác nhau về thời gian snapshot

Ở RCSI, một statement SELECT chạy lâu giữ các version cần thiết trong thời gian statement đó. Khi statement kết thúc, statement snapshot không còn cần thiết; transaction tiếp theo có thể đọc snapshot mới dù cùng transaction ở `READ COMMITTED`.

Ở `SNAPSHOT`, transaction có thể chạy nhiều statement và tiếp tục nhìn thấy snapshot ban đầu. Nếu transaction chỉ đọc mở lâu, version store phải giữ các version mà snapshot đó cần cho đến khi transaction kết thúc.

```sql
-- Cấu hình database (thực hiện bởi DBA theo kế hoạch riêng):
ALTER DATABASE appdb SET ALLOW_SNAPSHOT_ISOLATION ON;
ALTER DATABASE appdb SET READ_COMMITTED_SNAPSHOT ON;
```

Hai tùy chọn trên có mục đích khác nhau. Thay đổi cấu hình cần xem xét transaction đang hoạt động, connection và hành vi ứng dụng; không chạy tùy tiện trong lúc production workload đang phụ thuộc isolation hiện tại.

### 5.2. Quan sát snapshot transaction

```sql
SELECT session_id,
       transaction_id,
       transaction_sequence_num,
       first_snapshot_sequence_num,
       elapsed_time_seconds,
       is_snapshot
FROM sys.dm_tran_active_snapshot_database_transactions
ORDER BY elapsed_time_seconds DESC;
```

View này giúp xác định transaction snapshot đang hoạt động và thời gian tồn tại. Quyền truy cập DMV phụ thuộc phiên bản và quyền server/database.

Theo dõi dung lượng version store trong tempdb:

```sql
SELECT DB_NAME(database_id) AS database_name,
       reserved_page_count,
       reserved_space_kb
FROM sys.dm_tran_version_store_space_usage
ORDER BY reserved_space_kb DESC;
```

Theo dõi tổng dung lượng file tempdb:

```sql
USE tempdb;

SELECT SUM(version_store_reserved_page_count) * 8 AS version_store_kb,
       SUM(unallocated_extent_page_count) * 8 AS unallocated_kb,
       SUM(user_object_reserved_page_count) * 8 AS user_object_kb,
       SUM(internal_object_reserved_page_count) * 8 AS internal_object_kb
FROM sys.dm_db_file_space_usage;
```

Nếu ADR bật, theo dõi Persistent Version Store bằng DMV phù hợp với phiên bản, chẳng hạn `sys.dm_tran_persistent_version_store_stats`. Đừng kết luận PVS tăng chỉ từ dung lượng tempdb hoặc ngược lại.

### 5.3. Hậu quả

- Version store tăng dung lượng và có thể gây áp lực lên tempdb/PVS.
- Cleanup phải giữ version cũ cho snapshot lâu đời.
- tempdb có thể thiếu dung lượng hoặc chịu I/O cao.
- Transaction snapshot kéo dài làm giảm tốc độ thu hồi version.
- Khi có nhiều workload row-versioning, một reader lâu có thể ảnh hưởng đến toàn bộ database dùng chung version store.

Biện pháp gồm giới hạn thời gian truy vấn, theo dõi snapshot transaction lâu, tối ưu báo cáo, tránh giữ transaction qua thao tác bên ngoài và cấp dung lượng/tempdb phù hợp. Client command timeout không phải lúc nào cũng đảm bảo transaction đã được rollback; ứng dụng phải xử lý cancel và trạng thái transaction đúng cách.

## 6. Oracle: undo retention và consistent read

Oracle cung cấp read consistency bằng cách dựng lại block version tại một SCN (System Change Number) phù hợp. Khi một transaction thay đổi block, thông tin cũ được ghi vào undo. Một truy vấn bắt đầu tại SCN nhất định có thể cần undo để đọc dữ liệu như nó tồn tại tại thời điểm đó.

Một câu SELECT chạy lâu có thể cần các undo record cũ trong toàn bộ thời gian truy vấn. Nếu undo bị ghi đè trước khi query hoàn tất, Oracle có thể không dựng được phiên bản nhất quán và trả lỗi:

```text
ORA-01555: snapshot too old
```

### 6.1. Statement-level và transaction-level read consistency

Các câu SELECT thông thường có statement-level read consistency. Nếu ứng dụng dùng `SET TRANSACTION READ ONLY`, transaction có read consistency ở mức transaction: nhiều statement trong cùng transaction nhìn cùng một trạng thái logic. Điều này hữu ích cho báo cáo nhiều truy vấn cần cùng góc nhìn, nhưng có thể yêu cầu undo cũ tồn tại lâu hơn.

```sql
SET TRANSACTION READ ONLY;

SELECT SUM(amount) FROM invoice;
SELECT COUNT(*) FROM invoice WHERE status = 'OPEN';

COMMIT;
```

Nếu transaction kéo dài trong lúc các writer liên tục thay đổi bảng, Oracle phải giữ đủ undo để các câu đọc còn có thể dựng trạng thái theo snapshot. `READ ONLY` không làm giảm yêu cầu undo.

### 6.2. Theo dõi undo và query dài

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       maxqueryid,
       tuned_undoretention,
       ssolderrcnt,
       unxpstealcnt,
       nospaceerrcnt
FROM v$undostat
ORDER BY begin_time DESC;
```

Các cột hữu ích:

- `MAXQUERYLEN`: thời lượng query dài nhất trong khoảng thống kê.
- `TUNED_UNDORETENTION`: thời gian retention được Oracle điều chỉnh theo workload và undo capacity.
- `SSOLDERRCNT`: số lỗi snapshot too old được ghi nhận trong khoảng.
- `UNXPSTEALCNT`: số lần undo extent chưa hết hạn bị lấy lại do thiếu không gian trong các điều kiện liên quan.
- `NOSPACEERRCNT`: số lỗi không đủ không gian undo.

Để xem transaction đang dùng undo:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.module,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$session s
JOIN v$transaction t ON t.addr = s.taddr
WHERE s.type = 'USER'
ORDER BY t.start_time;
```

Một reader chỉ đọc có thể không xuất hiện trong `V$TRANSACTION` như một transaction đang tạo undo. Cần kết hợp thông tin SQL đang chạy, thời điểm bắt đầu query, SCN/snapshot và thống kê `V$UNDOSTAT`; đừng chỉ dựa vào `V$TRANSACTION` để tìm mọi reader giữ undo.

### 6.3. UNDO_RETENTION không phải cam kết tuyệt đối trong mọi cấu hình

`UNDO_RETENTION` là mục tiêu retention, nhưng khả năng giữ undo còn phụ thuộc dung lượng undo tablespace, workload và cấu hình như retention guarantee. Nếu không đủ không gian và không có guarantee phù hợp, Oracle có thể tái sử dụng undo cần thiết và query dài gặp `ORA-01555`.

Tăng `UNDO_RETENTION` mà không đảm bảo đủ dung lượng không tự giải quyết vấn đề. Cần ước lượng undo generation rate, thời gian query dài nhất, kích thước undo tablespace và theo dõi `V$UNDOSTAT`.

## 7. So sánh tác động giữa các DBMS

| DBMS | Cơ chế giữ version | Dấu hiệu thường gặp | Hậu quả chính |
|---|---|---|---|
| PostgreSQL | Heap tuple versions và visibility horizon | `backend_xmin` cũ, dead tuples tăng, autovacuum không thu hồi được | Table/index bloat, VACUUM backlog, áp lực freeze |
| MySQL InnoDB | Undo records và read view | History list length tăng, transaction read view lâu | Purge lag, undo growth, tăng chi phí cleanup |
| SQL Server RCSI/SNAPSHOT | Row version store trong tempdb; PVS khi ADR áp dụng | Snapshot transaction lâu, version store/PVS tăng | tempdb/PVS growth, I/O và cleanup pressure |
| Oracle | Undo records để dựng consistent read theo SCN | Query dài, tuned retention không đủ, `SSOLDERRCNT` tăng | `ORA-01555`, áp lực undo tablespace |

Các hệ thống khác nhau về cách lưu version nhưng có cùng nguyên tắc: **version cũ không thể bị thu hồi khi còn một reader hợp lệ cần nó**. Một reader không cần khóa ghi vẫn có thể làm tăng chi phí lưu trữ và cleanup của writer.

## 8. Tác động hiệu năng của read-only transaction kéo dài

### 8.1. Tăng dung lượng lưu phiên bản

Writer tiếp tục tạo version mới trong khi reader giữ version cũ. Dung lượng tăng theo tốc độ ghi, số dòng bị thay đổi, thời gian giữ snapshot và khả năng cleanup của engine. Một truy vấn kéo dài trên bảng ít thay đổi có thể ít tác động; một snapshot cũ trên bảng cập nhật hàng nghìn dòng mỗi giây có thể rất tốn kém.

### 8.2. Tăng I/O và CPU cho cleanup

Khi snapshot kết thúc, engine có thể phải xử lý backlog lớn: PostgreSQL VACUUM quét heap/index, InnoDB purge undo history, SQL Server version store cleanup, Oracle quản lý undo extent. Quá trình dọn dẹp cạnh tranh CPU và I/O với workload ứng dụng.

### 8.3. Tăng latency của writer gián tiếp

Reader MVCC thường không chặn writer theo từng dòng, nhưng version retention làm tăng kích thước dữ liệu và chi phí quản lý. Writer có thể chậm hơn do I/O, cache miss, cleanup backlog hoặc storage pressure. Không nên chỉ đo lock wait để đánh giá ảnh hưởng của long reader.

### 8.4. Ảnh hưởng đến DDL và metadata

Một số engine giữ metadata/schema lock đến khi transaction kết thúc. Ví dụ PostgreSQL `SELECT` giữ `ACCESS SHARE` table lock đến hết transaction; nó tương thích với DML thông thường nhưng có thể chặn DDL cần `ACCESS EXCLUSIVE`. InnoDB metadata lock cũng có thể khiến DDL chờ một transaction đã truy cập bảng. Vì thế, transaction read-only lâu có thể chặn thay đổi schema dù không khóa dòng để ghi.

### 8.5. Rủi ro vận hành thứ cấp

- Dung lượng disk/tempdb/undo tablespace tăng ngoài dự kiến.
- Backup, restore, replica và maintenance chịu thêm tải.
- Autovacuum/purge/version cleanup không theo kịp.
- Cảnh báo dung lượng đến muộn nếu chỉ theo dõi kích thước database mà không theo dõi version backlog.
- Báo cáo dài trên replica có thể tác động ngược về primary qua feedback hoặc replication conflict.

## 9. Cách nhận diện long reader thực sự có giữ version

Không nên chỉ tìm transaction có thời gian mở dài nhất. Hãy phân biệt ba yếu tố:

1. **Snapshot age:** snapshot hoặc read view cũ nhất mà engine còn phải tôn trọng.
2. **Write churn:** tốc độ tạo version mới trên các bảng liên quan trong thời gian snapshot còn hiệu lực.
3. **Cleanup backlog:** lượng version/dead tuple/undo đang chờ được thu hồi.

Một transaction dài trên bảng gần như chỉ đọc có thể ít tạo bloat. Một transaction ngắn nhưng lặp lại liên tục hoặc một reader dài trên bảng ghi rất nhiều có thể tạo áp lực lớn hơn. Cần liên kết snapshot age với write rate và version-store metrics.

### 9.1. PostgreSQL

Xem `pg_stat_activity.backend_xmin`, `xact_start`, `query_start`, isolation level (nếu được thu thập ở tầng ứng dụng), `pg_stat_user_tables.n_dead_tup`, `pg_stat_progress_vacuum` và replication slot xmin. `pg_stat_activity` không cung cấp một cột isolation level cho mọi session; có thể ghi isolation vào `application_name`/log hoặc lấy từ ứng dụng khi cần.

### 9.2. MySQL

Ghép `information_schema.innodb_trx` với processlist; theo dõi `trx_started`, `trx_isolation_level`, `trx_is_read_only`, `trx_query` và History list length trong InnoDB status. Một transaction read-only có thể không có row lock nhưng vẫn giữ read view.

### 9.3. SQL Server

Theo dõi `sys.dm_tran_active_snapshot_database_transactions`, dung lượng `sys.dm_tran_version_store_space_usage`, `sys.dm_db_file_space_usage` và PVS DMV nếu ADR bật. Xác định transaction snapshot cũ nhất thay vì chỉ nhìn request đang active.

### 9.4. Oracle

Theo dõi query age/SQL ID, `V$UNDOSTAT` (`MAXQUERYLEN`, `TUNED_UNDORETENTION`, `SSOLDERRCNT`) và undo tablespace usage. Một truy vấn consistent read có thể giữ SCN cần undo mà không xuất hiện như một transaction đang tạo undo trong `V$TRANSACTION`.

## 10. Bài thực hành PostgreSQL: reader chỉ đọc giữ snapshot cũ

Thí nghiệm sau dùng hai session PostgreSQL độc lập và một bảng riêng. Mục tiêu là quan sát reader `REPEATABLE READ READ ONLY` tiếp tục thấy giá trị cũ trong khi writer cập nhật và VACUUM phải giữ tuple cần cho snapshot.

### 10.1. Chuẩn bị dữ liệu

Chạy ngoài transaction trong session quản trị:

```sql
DROP TABLE IF EXISTS mvcc_reader_demo;

CREATE TABLE mvcc_reader_demo (
    id INTEGER PRIMARY KEY,
    value INTEGER NOT NULL
);

INSERT INTO mvcc_reader_demo VALUES (1, 100);
ANALYZE mvcc_reader_demo;
```

Mở session A (reader) và session B (writer/monitor). Có thể đặt `application_name` khác nhau để nhận diện.

### 10.2. Session A: lấy snapshot và đọc

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT value
FROM mvcc_reader_demo
WHERE id = 1;
```

Kết quả là 100. Giữ transaction A mở, không commit.

### 10.3. Session B: cập nhật nhiều lần

```sql
UPDATE mvcc_reader_demo SET value = 110 WHERE id = 1;
UPDATE mvcc_reader_demo SET value = 120 WHERE id = 1;
UPDATE mvcc_reader_demo SET value = 130 WHERE id = 1;
```

Các câu lệnh autocommit hoặc có thể đặt trong từng transaction riêng. Sau đó kiểm tra giá trị hiện tại trong một session mới: giá trị mới nhất là 130.

### 10.4. Session A đọc lại

Trong session A:

```sql
SELECT value
FROM mvcc_reader_demo
WHERE id = 1;
```

A vẫn thấy 100 vì transaction `REPEATABLE READ` giữ snapshot ban đầu. Session mới sẽ thấy 130.

### 10.5. Quan sát xmin và thử VACUUM

Trong session B:

```sql
SELECT pid,
       application_name,
       state,
       xact_start,
       backend_xmin,
       age(backend_xmin) AS xmin_age
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;
```

Có thể quan sát backend của A giữ `backend_xmin` cũ. Chạy VACUUM bên ngoài transaction:

```sql
VACUUM (VERBOSE) mvcc_reader_demo;
```

VACUUM có thể chạy nhưng không được thu hồi tuple mà snapshot A còn cần. Thông báo chi tiết phụ thuộc phiên bản và tình trạng page/index; không nên yêu cầu một dòng log cụ thể làm điều kiện duy nhất của bài lab.

### 10.6. Kết thúc reader và vacuum lại

Trong session A:

```sql
COMMIT;
```

Sau đó trong session B:

```sql
VACUUM (VERBOSE) mvcc_reader_demo;
```

Khi không còn snapshot cũ cần các version đó, VACUUM có thể thu hồi chúng để tái sử dụng. `pg_stat_user_tables.n_dead_tup` là ước lượng và có thể cập nhật trễ; mục tiêu của lab là quan sát quan hệ snapshot–version retention, không phải chứng minh kích thước file giảm ngay.

## 11. Giảm tác động mà vẫn giữ tính nhất quán báo cáo

Không phải lúc nào cũng có thể rút ngắn một báo cáo lớn thành một câu SELECT ngắn. Cần chọn chiến lược theo yêu cầu nhất quán dữ liệu.

### 11.1. Chia báo cáo thành batch

Đọc theo keyset pagination, xử lý từng chunk và kết thúc transaction sau mỗi chunk. Cách này giảm thời gian giữ snapshot, nhưng các chunk có thể nhìn thấy trạng thái dữ liệu khác nhau. Nếu báo cáo bắt buộc là một snapshot thống nhất, phải cân nhắc giải pháp khác thay vì âm thầm đổi semantics.

Ví dụ keyset pagination:

```sql
SELECT order_id, total_amount
FROM orders
WHERE order_id > :last_seen_id
ORDER BY order_id
LIMIT 1000;
```

Mỗi batch có thể chạy trong transaction riêng. Cần xác định cách xử lý dòng được chèn/cập nhật trong lúc export và bảo đảm khóa phân trang ổn định.

### 11.2. Dùng bản sao hoặc snapshot dữ liệu dành cho báo cáo

Có thể tạo staging table, materialized view, snapshot export hoặc bản sao dữ liệu theo lịch. Báo cáo đọc từ bản đã chốt thay vì giữ snapshot lâu trên bảng giao dịch nóng. Cần công bố độ trễ dữ liệu và cách đồng bộ bản sao.

Đọc trên replica có thể giảm tải query trên primary, nhưng không đảm bảo loại bỏ version retention: PostgreSQL standby feedback có thể giữ tuple trên primary; SQL Server replica/secondary có cơ chế version và redo riêng; Oracle standby cũng có read consistency và undo considerations. Cần đo ở cả nguồn lẫn replica.

### 11.3. Đóng cursor và transaction ngay khi đọc xong

Không để cursor server-side hoặc transaction read-only mở trong lúc ứng dụng serialize kết quả, nén file, upload object hoặc chờ người dùng. Nếu dữ liệu đã được fetch hết, đóng cursor và kết thúc transaction trước các bước hậu kỳ.

### 11.4. Dùng isolation level đúng yêu cầu

Nếu báo cáo chỉ cần snapshot theo từng statement, không dùng transaction-level snapshot kéo dài. Nếu nhiều câu lệnh phải nhìn cùng một trạng thái, transaction-level snapshot có thể là yêu cầu thật; khi đó cần kiểm soát thời lượng, dung lượng version và tần suất chạy.

Không hạ isolation level chỉ để giảm version retention nếu nó làm báo cáo cộng các phần dữ liệu từ những thời điểm khác nhau trong khi người dùng kỳ vọng một kết quả nhất quán.

### 11.5. Đặt timeout phù hợp

Timeout có thể giới hạn query hoặc transaction bị bỏ quên, nhưng phải phù hợp với workload:

- PostgreSQL `statement_timeout` giới hạn thời gian câu lệnh; `idle_in_transaction_session_timeout` xử lý session idle trong transaction, không hủy một SELECT vẫn đang active.
- MySQL có giới hạn execution time cho một số SELECT và timeout connection/lock riêng; `innodb_lock_wait_timeout` không giới hạn read view age.
- SQL Server dùng command timeout/cancel và chính sách ứng dụng; cần bảo đảm transaction được kết thúc sau khi cancel.
- Oracle có thể dùng Resource Manager hoặc chính sách profile phù hợp; `IDLE_TIME` xử lý session không hoạt động, không phải query đang chạy lâu.

Timeout quá thấp có thể hủy báo cáo hợp lệ. Hãy đo thời gian query, xác định SLA và có cách resume/retry trước khi áp dụng.

## 12. Những nhầm lẫn thường gặp

**Read-only transaction không thể ảnh hưởng writer.** Không đúng. Nó có thể giữ snapshot và khiến engine phải giữ version cũ; nó cũng có thể giữ metadata/table lock.

**Không có row lock nghĩa là không có version retention.** Không đúng. MVCC reader có thể không khóa dòng nhưng vẫn cần phiên bản cũ.

**Mọi transaction mở lâu đều giữ snapshot cũ như nhau.** Không đúng. PostgreSQL `READ COMMITTED` và `REPEATABLE READ` khác nhau; InnoDB `READ COMMITTED` và `REPEATABLE READ` cũng khác nhau; SQL Server RCSI là statement snapshot còn SNAPSHOT là transaction snapshot.

**Chạy VACUUM hoặc purge mạnh hơn sẽ xóa được version đang cần.** Không đúng. Cleanup phải tôn trọng reader còn hiệu lực; tăng worker không thể bỏ qua snapshot hợp lệ.

**Chuyển báo cáo sang replica luôn giải quyết vấn đề.** Không đúng. Replica có thể có cơ chế feedback, undo/version retention hoặc conflict riêng.

**Timeout lock giải quyết transaction chỉ đọc kéo dài.** Không đúng. Một consistent read có thể không chờ lock nào. Cần timeout query/transaction hoặc thiết kế snapshot phù hợp.

**Tăng undo retention luôn ngăn được ORA-01555.** Không đúng. Cần đủ undo capacity và theo dõi workload; tham số retention không tạo ra dung lượng vật lý.

## 13. Checklist vận hành

Khi version store, undo history hoặc dead tuple tăng, hãy kiểm tra:

1. Có long-running SELECT nào đang giữ statement snapshot không?
2. Có transaction-level snapshot như PostgreSQL `REPEATABLE READ`, InnoDB `REPEATABLE READ`, SQL Server `SNAPSHOT` hoặc Oracle read-only transaction đang mở không?
3. Transaction đã idle bao lâu và query đã chạy bao lâu?
4. Reader có cursor hoặc exported snapshot đang mở không?
5. Write churn trên bảng liên quan cao đến mức nào trong thời gian reader tồn tại?
6. PostgreSQL `backend_xmin`, dead tuple, autovacuum và replication slot có dấu hiệu giữ horizon không?
7. InnoDB History list length và purge lag có tăng liên tục không?
8. SQL Server version store/PVS có tăng và transaction snapshot nào cũ nhất?
9. Oracle `V$UNDOSTAT` có `SSOLDERRCNT`, `UNXPSTEALCNT` hoặc `NOSPACEERRCNT` tăng không?
10. Reader có cần snapshot thống nhất xuyên nhiều statement hay có thể chia batch?
11. Có thể chuyển sang snapshot/staging/materialized report không?
12. Transaction, cursor và connection có được đóng ngay sau khi đọc xong không?
13. Timeout có phù hợp và có quy trình resume/tra cứu kết quả không?

## 14. Kết luận

Giao dịch chỉ đọc kéo dài vẫn có thể tạo chi phí đồng thời đáng kể vì MVCC phải bảo toàn phiên bản dữ liệu mà snapshot còn cần. PostgreSQL giữ heap tuple cũ cho đến khi visibility horizon tiến lên; InnoDB giữ undo history cho read view; SQL Server giữ row version trong tempdb hoặc PVS theo cấu hình; Oracle cần undo để dựng consistent read theo SCN.

Tác động có thể xuất hiện dưới dạng table bloat, vacuum/purge backlog, version store hoặc undo growth, tăng I/O và lỗi snapshot. Hãy đo tuổi query và transaction, xác định isolation/snapshot lifetime, liên kết với tốc độ ghi và cleanup backlog, rồi chọn cách giảm thời gian giữ snapshot hoặc cung cấp dữ liệu báo cáo riêng. Một transaction read-only vẫn là một phần của hệ thống đồng thời và cần được quản lý vòng đời như transaction ghi.
