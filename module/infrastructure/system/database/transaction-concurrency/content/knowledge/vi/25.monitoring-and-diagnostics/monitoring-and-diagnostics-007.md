# Theo dõi phiên bản cũ, undo và áp lực thu gom dữ liệu

Các hệ quản trị hỗ trợ MVCC (Multi-Version Concurrency Control) thường giữ nhiều phiên bản của cùng một hàng trong một khoảng thời gian. Khi transaction cập nhật hoặc xóa dữ liệu, phiên bản cũ có thể vẫn cần thiết cho những transaction đang đọc snapshot trước đó. Database chỉ được phép thu gom phiên bản cũ khi không còn reader nào có thể cần nó.

Nếu transaction đọc kéo dài, cursor mở lâu, replica hoặc replication slot giữ một mốc dữ liệu cũ, quá trình thu gom có thể bị chậm. Khi đó, hệ thống có thể tích lũy dead tuple, undo history, version store hoặc WAL. Hệ quả thường gặp là dung lượng tăng, truy vấn chậm, checkpoint/purge/vacuum không theo kịp và đôi khi xuất hiện lỗi như snapshot quá cũ hoặc thiếu không gian.

Để chẩn đoán, cần quan sát đồng thời ba yếu tố: **phiên bản cũ đang bị giữ bởi ai, tốc độ tạo phiên bản mới là bao nhiêu, và bộ phận thu gom đang xử lý được bao nhiêu**. Cách lưu phiên bản và tên chỉ số khác nhau giữa PostgreSQL, MySQL/InnoDB, Oracle và SQL Server, vì vậy không nên dùng một ngưỡng chung cho mọi engine.

## 1. Phiên bản cũ được tạo ra vì sao?

Trong mô hình MVCC, một transaction đọc dữ liệu theo snapshot phù hợp với isolation level. Một transaction khác có thể cập nhật cùng hàng và commit trong lúc reader vẫn đang chạy. Để reader không nhìn thấy trạng thái nửa cũ nửa mới, database cần giữ phiên bản mà snapshot của reader được phép nhìn thấy.

Ví dụ một hàng tài khoản có số dư 100:

```text
Thời điểm 1: R1 bắt đầu đọc và nhìn thấy balance = 100.
Thời điểm 2: W1 cập nhật balance = 80 và COMMIT.
Thời điểm 3: R1 tiếp tục truy vấn trong snapshot cũ.

R1 vẫn có thể cần phiên bản balance = 100.
Reader mới R2 nhìn thấy balance = 80.
```

Database không thể xóa phiên bản 100 ngay khi W1 commit nếu R1 còn có thể cần nó. Phiên bản cũ chỉ trở thành ứng viên thu gom khi không còn snapshot hoặc cơ chế phục hồi nào cần tham chiếu đến nó.

### Vòng đời khái quát

```text
UPDATE / DELETE
       |
       v
Tạo phiên bản mới hoặc lưu before-image
       |
       v
Phiên bản cũ vẫn cần cho snapshot đang hoạt động
       |
       v
Snapshot cũ kết thúc / retention horizon tiến lên
       |
       v
VACUUM / PURGE / VERSION CLEANUP
       |
       v
Không còn cần phiên bản cũ
       |
       v
Không gian có thể được tái sử dụng hoặc thu hồi
```

Thu gom không nhất thiết làm file database nhỏ lại ngay. Nhiều engine chỉ đánh dấu không gian bên trong file để tái sử dụng cho lần ghi sau. Việc trả dung lượng về filesystem có thể cần thao tác rewrite, shrink hoặc cơ chế riêng và thường tốn kém.

## 2. Những nguồn có thể giữ phiên bản cũ

Một phiên bản cũ có thể còn cần thiết vì nhiều lý do:

- **Transaction đọc lâu:** transaction giữ snapshot cũ trong khi dữ liệu liên tục được cập nhật.
- **Transaction đang mở nhưng không hoạt động:** ứng dụng đã đọc dữ liệu rồi để connection ở trạng thái idle trong transaction.
- **Cursor hoặc streaming result:** ứng dụng đọc từng phần trong thời gian dài và giữ transaction/snapshot mở.
- **Snapshot isolation:** một transaction có thể cần nhìn cùng snapshot trong toàn bộ thời gian chạy, dù có nhiều statement.
- **Replication hoặc logical decoding:** subscriber/replication slot có thể giữ một mốc dữ liệu hoặc WAL để bảo đảm có thể tiếp tục đồng bộ.
- **Backup hoặc tác vụ đọc nhất quán:** một số quy trình backup, export hoặc báo cáo cần snapshot ổn định trong thời gian dài.
- **Transaction bị treo do ứng dụng:** thread chờ lock, gọi HTTP hoặc chờ người dùng trong khi transaction vẫn mở.

Không phải mọi transaction lâu đều chắc chắn giữ snapshot cũ. Ví dụ trong PostgreSQL, `xact_start` cũ là tín hiệu cần điều tra, còn `backend_xmin` cho biết backend đang giữ một mốc xmin có ý nghĩa đối với việc thu gom. Cần kết hợp nhiều chỉ số thay vì kết luận chỉ từ tuổi transaction.

## 3. Áp lực thu gom được hình thành như thế nào?

Có thể mô hình hóa đơn giản:

```text
Tốc độ tạo phiên bản cũ > Tốc độ thu gom
                    |
                    v
              Backlog tăng
                    |
                    v
        Dung lượng / I/O / CPU tăng
                    |
                    v
     Query, commit hoặc checkpoint chậm hơn
```

Ba nhóm tín hiệu cần theo dõi:

| Nhóm | Câu hỏi cần trả lời | Ví dụ chỉ số |
| --- | --- | --- |
| Retention horizon | Snapshot hoặc transaction cũ nhất đang giữ mốc nào? | Tuổi transaction, oldest snapshot, `xmin`, read view, snapshot transaction sequence |
| Generation rate | Database đang tạo phiên bản cũ nhanh đến đâu? | Tốc độ UPDATE/DELETE, undo bytes, WAL bytes, version store growth |
| Cleanup throughput | Bộ phận thu gom xử lý được bao nhiêu? | VACUUM progress, purge history, checkpoint progress, version store cleanup |

Một con số backlog lớn chưa đủ để kết luận hệ thống đang gặp sự cố. Quan trọng là xu hướng: backlog có tăng liên tục không, có transaction cũ giữ horizon không, cleanup có tiến triển không và dung lượng còn lại có đủ cho workload dự kiến không.

## 4. Triệu chứng thường gặp

Áp lực giữ phiên bản cũ có thể biểu hiện qua nhiều dạng:

- File database, undo tablespace, `tempdb` hoặc WAL tăng nhanh.
- Dung lượng trống trong filesystem giảm dù ứng dụng không tăng nhiều dữ liệu logic.
- Vacuum hoặc purge chạy liên tục nhưng backlog không giảm.
- Truy vấn đọc lâu hơn do phải xét nhiều phiên bản hoặc version chain.
- Checkpoint không thể hoàn tất hoặc WAL không thể reset.
- Xuất hiện `ORA-01555: snapshot too old` khi Oracle không còn giữ được undo cần cho consistent read.
- MySQL/InnoDB có History list length tăng kéo dài.
- PostgreSQL có nhiều dead tuple, autovacuum chậm hoặc cảnh báo transaction ID wraparound.
- SQL Server có version store tăng trong `tempdb` hoặc Persistent Version Store tăng khi bật Accelerated Database Recovery.
- Transaction ghi bị chậm do I/O, lock wait hoặc tài nguyên cleanup cạnh tranh với workload ứng dụng.

Không phải mọi trường hợp file lớn đều do phiên bản cũ. Index bloat, dữ liệu thật tăng, log retention, replication lag, backup và file đã cấp phát trước đó cũng có thể làm dung lượng tăng. Cần xác định đúng loại dữ liệu đang giữ lại.

## 5. PostgreSQL: dead tuple, VACUUM và xmin horizon

PostgreSQL dùng MVCC với các tuple version trong heap. Một UPDATE thường tạo tuple mới và đánh dấu tuple cũ không còn là phiên bản hiện hành; DELETE đánh dấu tuple bị xóa. Phiên bản cũ không được loại bỏ ngay vì snapshot đang hoạt động có thể vẫn nhìn thấy nó.

PostgreSQL không dùng một undo log tập trung giống InnoDB hoặc Oracle cho đường đi MVCC thông thường. Các phiên bản hàng cũ nằm trong heap; `VACUUM` dọn những tuple không còn cần thiết và quản lý khả năng tái sử dụng không gian.

### Các chỉ số quan trọng

- `n_dead_tup`: ước lượng số dead tuple trong bảng.
- `last_autovacuum`, `autovacuum_count`: thời điểm và số lần autovacuum gần đây.
- `backend_xmin`: mốc xmin backend đang giữ, có thể góp phần ngăn vacuum loại bỏ tuple cũ.
- `age(datfrozenxid)`: tuổi transaction ID so với mốc freeze của database, quan trọng để theo dõi nguy cơ wraparound.
- `pg_stat_progress_vacuum`: tiến độ của VACUUM đang chạy.
- `pg_replication_slots.xmin` và `catalog_xmin`: slot có thể giữ tuple thường hoặc catalog tuple cũ.
- `restart_lsn`: mốc WAL mà replication slot còn cần; có thể làm WAL tiếp tục được giữ lại.

### Tìm transaction lâu và snapshot cũ

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Tập trung vào transaction có `xact_start` rất cũ, trạng thái `idle in transaction` và backend có `backend_xmin` cũ. `xact_start` chỉ cho biết tuổi transaction; nó không tự chứng minh transaction đó đang giữ snapshot cản vacuum. Hãy đối chiếu `backend_xmin`, trạng thái, query và các slot.

Một transaction ở trạng thái `idle in transaction` đặc biệt đáng chú ý: ứng dụng có thể đã đọc một snapshot rồi chờ xử lý bên ngoài database, trong khi transaction vẫn mở.

### Theo dõi dead tuple và lịch sử vacuum

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

`n_dead_tup` là ước lượng thống kê, không phải số đếm chính xác tại thời điểm truy vấn. Hãy xem xu hướng qua nhiều lần lấy mẫu và so sánh với kích thước bảng/index. Một bảng cập nhật liên tục có thể có dead tuple cao trong thời gian ngắn mà vẫn được autovacuum xử lý bình thường.

Theo dõi tiến độ vacuum:

```sql
SELECT
    pid,
    relid::regclass AS table_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
```

Nếu vacuum chạy lâu, hãy kiểm tra phase, bảng lớn, index, I/O và transaction/slot đang giữ horizon. Một vacuum không thể thu gom tuple còn nhìn thấy được bởi snapshot cũ.

### Kiểm tra replication slot

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots;
```

Slot không hoạt động nhưng vẫn giữ `xmin` hoặc `catalog_xmin` có thể ngăn vacuum thu gom một số tuple. `restart_lsn` cũ có thể giữ WAL và làm file WAL tăng. Đây là hai dạng retention liên quan nhưng khác nhau: tuple retention và WAL retention.

Không xóa replication slot chỉ vì nó cũ. Trước tiên xác nhận consumer đã bị bỏ, có thể tạo lại hoặc đồng bộ lại và không còn cần dữ liệu mà slot giữ. Xóa slot sai có thể khiến subscriber hoặc replica không thể tiếp tục từ vị trí cũ.

### Theo dõi nguy cơ transaction ID wraparound

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    datfrozenxid
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
```

VACUUM còn có nhiệm vụ freeze tuple đủ cũ để tránh transaction ID wraparound. Đây là yêu cầu vận hành quan trọng, không chỉ là tối ưu dung lượng. Khi tuổi `datfrozenxid` tiến gần ngưỡng cảnh báo của phiên bản/configuration, phải xử lý vacuum/freeze khẩn trương theo hướng dẫn PostgreSQL; không trì hoãn chỉ để giảm I/O.

### VACUUM có trả dung lượng về filesystem không?

`VACUUM` thường làm không gian trong relation có thể được tái sử dụng bởi các lần INSERT/UPDATE sau. Nó không nhất thiết làm file table nhỏ lại hoặc trả dung lượng về filesystem. `VACUUM FULL` viết lại relation để thu nhỏ file nhưng cần lock mạnh và thêm không gian tạm; không nên dùng như thao tác định kỳ để xử lý mọi dead tuple.

## 6. MySQL/InnoDB: undo log và purge thread

InnoDB dùng undo log để giữ thông tin cần thiết cho rollback và consistent read. Khi một hàng được cập nhật, undo record giúp reader có thể dựng lại phiên bản phù hợp với read view của nó. Khi không còn transaction nào cần các undo record đó, purge thread có thể xử lý lịch sử cũ và loại bỏ các record/index entry đã hết hiệu lực.

### History list length

Một chỉ số thường dùng để quan sát áp lực purge là **History list length** trong `SHOW ENGINE INNODB STATUS`:

```sql
SHOW ENGINE INNODB STATUS\G
```

Trong phần TRANSACTIONS, tìm dòng `History list length`. Chỉ số này phản ánh lượng lịch sử undo cần purge theo đơn vị nội bộ, không phải số byte và không có một ngưỡng tuyệt đối đúng cho mọi hệ thống.

Có thể xem metric tương ứng trong `INNODB_METRICS` nếu metric được bật và phiên bản cung cấp:

```sql
SELECT NAME, COUNT
FROM information_schema.innodb_metrics
WHERE NAME = 'trx_rseg_history_len';
```

Quan trọng hơn giá trị đơn lẻ là xu hướng. Nếu history list length tăng liên tục dù tải ghi đã ổn định, purge có thể không theo kịp hoặc một read view cũ đang giữ undo.

### Tìm transaction giữ read view lâu

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_mysql_thread_id,
    trx_isolation_level,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Tìm transaction có tuổi lớn, kể cả transaction `RUNNING` hoặc `LOCK WAIT`. Một transaction read-only có thể không giữ row lock nhưng vẫn giữ consistent read view và làm chậm purge. `trx_query` có thể NULL khi transaction đang idle; cần liên kết thread ID với process list/performance schema để tìm connection và ứng dụng sở hữu nó.

### Vì sao History list length tăng?

- Transaction `REPEATABLE READ` mở lâu và giữ read view cũ.
- Ứng dụng đọc dữ liệu rồi để transaction idle.
- Một batch update/delete lớn tạo undo nhanh hơn purge có thể xử lý.
- Purge thread thiếu năng lực do I/O, CPU hoặc workload cạnh tranh.
- Một transaction bị quên rollback/commit giữ read view lâu.

Khi purge không thể xử lý lịch sử, undo tablespace có thể tăng. InnoDB không thể thu gom record mà snapshot cũ vẫn cần để dựng phiên bản.

### Xử lý và cấu hình purge

Các biến như `innodb_purge_threads`, `innodb_max_purge_lag` và `innodb_max_purge_lag_delay` ảnh hưởng cách InnoDB xử lý backlog hoặc làm chậm thao tác ghi khi purge lag lớn. Không nên tăng số purge thread một cách mù quáng: nếu bottleneck là I/O, một transaction cũ giữ read view hoặc storage đã bão hòa, tăng thread có thể làm cạnh tranh tài nguyên nặng hơn.

Hãy giải quyết transaction giữ read view trước, sau đó đo throughput purge và cân nhắc cấu hình theo phiên bản MySQL, số core, workload và storage. Undo tablespace truncation cũng phụ thuộc cấu hình và điều kiện engine; không xóa file undo bằng filesystem.

## 7. Oracle: undo retention và consistent read

Oracle dùng undo segments để lưu before-image của thay đổi. Khi một query cần đọc dữ liệu nhất quán tại một thời điểm, Oracle dùng undo để tái tạo phiên bản phù hợp. Undo cũng phục vụ rollback và recovery.

Nếu một query chạy lâu nhưng lượng undo cần thiết đã bị ghi đè hoặc không còn khả dụng, query có thể nhận:

```text
ORA-01555: snapshot too old
```

Nếu undo tablespace không còn đủ không gian để cấp phát extent cần thiết, có thể xuất hiện lỗi như:

```text
ORA-30036: unable to extend segment in undo tablespace
```

Hai lỗi này có liên quan đến áp lực undo nhưng không đồng nghĩa. `ORA-01555` cho biết query không còn dựng được snapshot cần thiết; `ORA-30036` cho biết không thể mở rộng segment trong undo tablespace.

### Theo dõi V$UNDOSTAT

```sql
SELECT
    begin_time,
    end_time,
    undoblks,
    txncount,
    maxquerylen,
    tuned_undoretention,
    ssolderrcnt,
    nospaceerrcnt,
    unxpstealcnt
FROM v$undostat
ORDER BY begin_time DESC;
```

Các cột hữu ích:

- `UNDOBLKS`: số block undo được tạo trong khoảng thống kê.
- `TXNCOUNT`: số transaction trong khoảng đó.
- `MAXQUERYLEN`: độ dài query lâu nhất được ghi nhận.
- `TUNED_UNDORETENTION`: retention được Oracle điều chỉnh theo workload và cấu hình.
- `SSOLDERRCNT`: số lỗi snapshot too old trong khoảng thống kê.
- `NOSPACEERRCNT`: số lỗi không đủ không gian undo.
- `UNXPSTEALCNT`: số lần phải lấy lại undo extent chưa hết retention trong các điều kiện liên quan.

Hãy so sánh các khoảng thời gian có `SSOLDERRCNT` tăng với `MAXQUERYLEN`, tốc độ tạo undo và `TUNED_UNDORETENTION`. Một query có thể chạy lâu hơn thời gian undo thực tế được giữ, đặc biệt khi workload DML tạo undo nhanh.

### Kiểm tra extent undo

```sql
SELECT
    tablespace_name,
    status,
    COUNT(*) AS extent_count,
    SUM(bytes) AS bytes_total
FROM dba_undo_extents
GROUP BY tablespace_name, status
ORDER BY tablespace_name, status;
```

Các trạng thái như ACTIVE, UNEXPIRED và EXPIRED giúp hiểu mức độ extent đang được transaction dùng, đang trong retention hay có thể tái sử dụng. Quyền truy cập view phụ thuộc quyền DBA/catalog của tài khoản.

### UNDO_RETENTION và RETENTION GUARANTEE

`UNDO_RETENTION` là mục tiêu retention, nhưng khả năng giữ undo thực tế phụ thuộc kích thước tablespace, tốc độ tạo undo, cấu hình autoextend và các tính năng/phiên bản đang dùng. Không nên coi giá trị cấu hình là lời hứa rằng mọi query đều được bảo đảm có đủ undo.

`RETENTION GUARANTEE` yêu cầu Oracle giữ undo chưa hết retention, nhưng nếu tablespace hết chỗ, thao tác ghi mới có thể thất bại thay vì ghi đè undo đó. Đây là trade-off giữa bảo vệ consistent read và khả năng tiếp tục ghi. Chỉ bật sau khi đã tính dung lượng và đánh giá tác động đến workload ghi.

## 8. SQL Server: row version store trong tempdb và PVS

SQL Server có thể dùng row versioning để thực hiện Read Committed Snapshot Isolation (RCSI) hoặc Snapshot Isolation. Các phiên bản hàng được giữ để reader nhìn thấy dữ liệu phù hợp với snapshot mà không phải chặn writer theo cách khóa đọc truyền thống.

Ở các cấu hình không dùng Accelerated Database Recovery (ADR), version store thường nằm trong `tempdb`. Khi ADR được bật, Persistent Version Store (PVS) được dùng trong database tương ứng thay cho version store truyền thống trong tempdb đối với các chức năng ADR liên quan. Cần xác định chính xác phiên bản và cấu hình database trước khi chẩn đoán dung lượng.

### RCSI và Snapshot Isolation

- **RCSI:** mỗi statement đọc theo snapshot tại thời điểm statement bắt đầu. Một transaction có nhiều statement có thể thấy snapshot khác nhau giữa các statement.
- **Snapshot Isolation:** transaction đọc theo snapshot được xác lập khi transaction bắt đầu; snapshot có thể phải được giữ đến khi transaction kết thúc.

Vì vậy, một transaction Snapshot Isolation lâu có thể giữ các row version cũ lâu hơn một statement RCSI ngắn. Dù RCSI thường giảm lock blocking, nó không làm chi phí version store biến mất.

### Theo dõi version store trong tempdb

```sql
SELECT
    DB_NAME(database_id) AS database_name,
    reserved_page_count,
    reserved_space_kb
FROM sys.dm_tran_version_store_space_usage
ORDER BY reserved_space_kb DESC;
```

View này giúp xem dung lượng version store trong tempdb theo database. Có thể theo dõi dung lượng file tempdb:

```sql
SELECT
    SUM(version_store_reserved_page_count) * 8 AS version_store_kb,
    SUM(unallocated_extent_page_count) * 8 AS unallocated_kb,
    SUM(user_object_reserved_page_count) * 8 AS user_object_kb,
    SUM(internal_object_reserved_page_count) * 8 AS internal_object_kb
FROM sys.dm_db_file_space_usage;
```

Kết quả của `sys.dm_db_file_space_usage` phản ánh các loại cấp phát trong tempdb; phải chạy trong đúng context database `tempdb` để đọc số liệu file tempdb.

### Tìm snapshot transaction lâu

```sql
SELECT
    transaction_id,
    session_id,
    elapsed_time_seconds,
    is_snapshot,
    first_snapshot_sequence_num,
    max_version_chain_traversed,
    average_version_chain_traversed
FROM sys.dm_tran_active_snapshot_database_transactions
ORDER BY elapsed_time_seconds DESC;
```

Kết hợp với session và transaction DMVs để xác định ứng dụng, query và thời điểm bắt đầu. Một transaction snapshot cũ có thể giữ version store lâu sau khi query đã ngừng hoạt động nhưng transaction chưa kết thúc.

### Khi ADR sử dụng Persistent Version Store

Khi ADR được bật, theo dõi PVS trong database thay vì chỉ nhìn tempdb. Các DMV liên quan đến PVS có sẵn tùy phiên bản SQL Server; ví dụ `sys.dm_tran_persistent_version_store_stats` cung cấp thông tin thống kê PVS ở các phiên bản hỗ trợ. Đối chiếu tài liệu phiên bản đang chạy và theo dõi kích thước file dữ liệu, tốc độ version generation và trạng thái cleanup.

Không kết luận PVS khỏe chỉ vì version store trong tempdb nhỏ. Khi ADR bật, nguồn tiêu thụ dung lượng có thể đã chuyển sang database file.

## 9. So sánh cách lưu và thu gom giữa các engine

| Hệ quản trị | Nơi giữ phiên bản cũ | Cơ chế thu gom chính | Chỉ số/chẩn đoán quan trọng |
| --- | --- | --- | --- |
| PostgreSQL | Tuple version cũ trong heap; WAL có thể được giữ riêng bởi slot | VACUUM/autovacuum, freeze; WAL recycling/checkpoint riêng | `n_dead_tup`, `backend_xmin`, transaction age, slot `xmin`/`restart_lsn`, vacuum progress, `age(datfrozenxid)` |
| MySQL/InnoDB | Undo records trong undo tablespace | Purge thread loại lịch sử không còn cần | History list length, `information_schema.innodb_trx`, undo tablespace, purge lag |
| Oracle | Undo segments trong undo tablespace | Tái sử dụng extent theo active transaction và retention | `V$UNDOSTAT`, `TUNED_UNDORETENTION`, `SSOLDERRCNT`, `DBA_UNDO_EXTENTS` |
| SQL Server | Row version store trong tempdb; PVS khi ADR bật | Version store cleanup/ADR cleanup | Version store reserved space, active snapshot transactions, tempdb/PVS growth |

Không so sánh trực tiếp History list length của InnoDB với `n_dead_tup` của PostgreSQL hoặc số page trong SQL Server. Chúng đo những đơn vị và cơ chế khác nhau. Hãy dùng xu hướng trong cùng engine, cùng phiên bản và cùng cấu hình.

## 10. Chẩn đoán theo trình tự

Khi thấy dung lượng hoặc backlog tăng, hãy đi từ triệu chứng đến nguồn giữ phiên bản thay vì lập tức tăng cấu hình cleanup.

### Bước 1: xác định loại dung lượng tăng

- PostgreSQL: heap/index bloat, WAL, replication slot retention hay transaction ID age?
- InnoDB: History list length, undo tablespace hay file table/index tăng?
- Oracle: undo tablespace, active/unexpired extents hay lỗi snapshot too old?
- SQL Server: tempdb version store, PVS, user/internal object hay file database tăng?

### Bước 2: tìm transaction hoặc snapshot cũ nhất

Lấy danh sách transaction đang mở, thời gian bắt đầu, trạng thái, session ID, query và ứng dụng. Đối chiếu với chỉ số horizon đặc thù engine. Đừng chỉ nhìn query đang chạy; một connection idle trong transaction cũng có thể giữ snapshot.

### Bước 3: xác định nguồn tạo phiên bản

Xem bảng hoặc workload có tốc độ UPDATE/DELETE cao, batch lớn, cascade, cleanup job hoặc ghi dữ liệu liên tục. Một backlog tăng có thể do generation rate tăng đột ngột chứ không phải cleanup hỏng.

### Bước 4: đo tốc độ cleanup

Quan sát VACUUM progress, InnoDB purge history, Oracle undo reuse/retention và SQL Server version store cleanup. Xác định cleanup đang chạy, bị chặn hay thiếu I/O/CPU.

### Bước 5: tìm retention blocker

Kiểm tra long transaction, replication slot, backup snapshot, cursor lâu hoặc subscriber chậm. Chỉ một reader cũ có thể giữ lại lượng dữ liệu lớn được tạo ra bởi hàng nghìn transaction sau đó.

### Bước 6: ước lượng tốc độ tăng và thời gian còn lại

Lấy mẫu dung lượng theo chu kỳ cố định. Tính tốc độ tăng trung bình và tốc độ cleanup trong khoảng thời gian đủ dài. Nếu dung lượng đang tăng đều, dự báo thời điểm chạm giới hạn filesystem/tablespace để xử lý trước khi hệ thống hết chỗ.

### Bước 7: xử lý đúng nguyên nhân rồi xác nhận

Giải phóng hoặc kết thúc transaction cũ nếu an toàn, khắc phục subscriber, điều chỉnh batch/transaction duration, hoặc tăng năng lực cleanup sau khi xác nhận bottleneck. Sau đó theo dõi backlog giảm, không chỉ nhìn một lần query trả về số thấp.

## 11. Transaction lâu trong ứng dụng Java và ORM

Một nguyên nhân phổ biến nằm ở ranh giới transaction của ứng dụng chứ không phải câu SQL riêng lẻ.

Ví dụ không tốt:

```java
@Transactional(readOnly = true)
public void exportOrders(OutputStream output) {
    List<Order> orders = repository.streamAllOrders();

    for (Order order : orders) {
        writeToSlowClient(output, order);
    }
}
```

Nếu stream/cursor giữ transaction mở trong khi ứng dụng gửi dữ liệu đến client chậm, snapshot có thể tồn tại rất lâu. Trong thời gian đó, database tiếp tục cập nhật và tạo phiên bản cũ mà cleanup chưa thể loại bỏ.

Các nguyên tắc:

- Không giữ transaction mở trong lúc chờ người dùng, gọi HTTP service hoặc ghi ra output chậm.
- Đóng `ResultSet`, `Statement`, cursor và stream đúng lúc.
- Với export lớn, cân nhắc phân trang theo khóa ổn định hoặc chia thành batch transaction ngắn. Phải xác định semantics dữ liệu nhất quán cần giữ giữa các trang.
- `@Transactional(readOnly = true)` không đồng nghĩa không tạo snapshot hoặc không giữ tài nguyên. Nó chủ yếu là hint/optimization tùy framework và driver.
- Kiểm tra transaction propagation để tránh một method tham gia transaction ngoài có thời gian sống dài hơn dự kiến.
- Theo dõi connection pool: connection đang `active`, `idle`, hoặc bị giữ bởi thread lâu có thể giúp tìm owner của transaction.
- Tránh Open Session in View hoặc streaming pattern giữ persistence context/transaction lâu nếu endpoint thực hiện I/O kéo dài.

Một phương án export có thể đọc theo từng batch, đóng transaction sau mỗi batch rồi ghi ra output. Nếu cần một snapshot nhất quán cho toàn bộ export, phải cân nhắc chi phí giữ snapshot dài hoặc dùng snapshot/export mechanism phù hợp với engine; không thể vừa yêu cầu một snapshot duy nhất kéo dài vừa kỳ vọng mọi phiên bản cũ được thu gom ngay.

## 12. Cách xử lý theo từng engine

### PostgreSQL

1. Xác định backend có `backend_xmin` cũ và transaction `idle in transaction`.
2. Kiểm tra replication slot có `xmin`/`catalog_xmin` hoặc `restart_lsn` cũ.
3. Xem dead tuple và autovacuum trên bảng tăng nhanh.
4. Giải quyết session/slot cản horizon theo quy trình an toàn.
5. Đảm bảo autovacuum có đủ thời gian và tài nguyên; cân nhắc per-table threshold/scale factor cho bảng cập nhật nhiều.
6. Theo dõi freeze age và không bỏ qua cảnh báo wraparound.

Không chạy `VACUUM FULL` như phản xạ đầu tiên. Nó có thể cần lock mạnh và tạo tải I/O/dung lượng tạm lớn. Thường nên giải quyết retention blocker và để VACUUM thường tái sử dụng không gian trước.

### MySQL/InnoDB

1. Theo dõi History list length theo thời gian.
2. Tìm transaction lâu trong `information_schema.innodb_trx`, kể cả read-only hoặc idle.
3. Xác định transaction nào giữ read view cũ và kết thúc/điều chỉnh ứng dụng nếu an toàn.
4. Xác nhận purge thread có tiến triển và storage không bị nghẽn.
5. Chỉ điều chỉnh purge thread/lag sau khi đo bottleneck và thử nghiệm trên workload tương tự.
6. Theo dõi undo tablespace và cấu hình truncate theo phiên bản.

Không kill transaction chỉ vì nó lâu nếu chưa biết nghiệp vụ và tác dụng phụ. Rollback transaction lớn cũng có thể tạo tải đáng kể trong thời gian hoàn tác.

### Oracle

1. Đối chiếu `V$UNDOSTAT` với thời điểm ORA-01555/ORA-30036.
2. Tìm query dài và transaction tạo undo nhiều.
3. Kiểm tra dung lượng undo tablespace, autoextend và tỷ lệ extent ACTIVE/UNEXPIRED/EXPIRED.
4. Đánh giá `UNDO_RETENTION` theo query duration và undo generation rate.
5. Cân nhắc `RETENTION GUARANTEE` chỉ khi chấp nhận writer có thể thất bại khi hết chỗ.
6. Theo dõi lỗi snapshot too old sau thay đổi, không chỉ tăng tablespace mà bỏ qua query dài.

### SQL Server

1. Xác định database dùng RCSI, Snapshot Isolation hay ADR.
2. Nếu không dùng ADR, theo dõi version store trong tempdb và dung lượng tempdb.
3. Nếu dùng ADR, theo dõi PVS trong database.
4. Tìm active snapshot transaction lâu và liên kết với session/query.
5. Kết thúc transaction cũ hoặc sửa ứng dụng giữ snapshot lâu.
6. Đảm bảo tempdb/PVS có dung lượng và I/O phù hợp; kiểm tra version cleanup tiến triển sau khi blocker kết thúc.

## 13. Những hành động có thể làm tình hình xấu hơn

- **Chỉ tăng dung lượng mà không tìm blocker:** có thể trì hoãn sự cố nhưng backlog vẫn tăng không giới hạn.
- **Tăng cleanup thread không đo bottleneck:** làm CPU/I/O cạnh tranh nhiều hơn trong khi snapshot cũ vẫn giữ phiên bản.
- **Kill transaction hàng loạt:** có thể gây rollback lớn, lỗi người dùng hoặc tác dụng phụ ngoài database.
- **Xóa replication slot/undo/WAL file thủ công:** có thể phá khả năng recovery hoặc replication.
- **VACUUM FULL/shrink file tùy tiện:** có thể gây lock, I/O và thời gian gián đoạn đáng kể.
- **Tăng retention vô hạn:** giữ dữ liệu cũ lâu hơn và làm tăng nhu cầu dung lượng.
- **Tắt MVCC/isolation để giảm version store:** có thể làm thay đổi tính đúng đắn của nghiệp vụ và tạo anomaly.
- **Chỉ cảnh báo theo một ngưỡng cố định:** một giá trị bình thường với database lớn có thể nguy hiểm với database nhỏ; cần thêm tốc độ tăng và thời gian còn lại.

## 14. Dashboard và cảnh báo nên có gì?

Một dashboard hữu ích nên kết hợp các chỉ số theo thời gian:

| Nhóm | Metric gợi ý | Cảnh báo khi |
| --- | --- | --- |
| Transaction age | Tuổi transaction/snapshot lâu nhất, số `idle in transaction` | Vượt SLA hoặc tăng bất thường |
| Retention horizon | PostgreSQL `backend_xmin`/slot xmin; InnoDB read view; SQL Server active snapshot | Mốc cũ không tiến lên dù workload bình thường |
| Backlog | Dead tuple, History list length, undo usage, version store/PVS pages | Tăng liên tục qua nhiều chu kỳ |
| Cleanup | Vacuum/purge/checkpoint/version cleanup progress | Cleanup không tiến triển hoặc throughput thấp hơn generation rate |
| Storage | WAL, undo tablespace, tempdb, PVS và filesystem free space | Dự báo hết chỗ trước thời gian xử lý sự cố |
| Errors | ORA-01555, ORA-30036, serialization/lock errors, wraparound warnings | Có lỗi mới hoặc tần suất tăng |
| Replication | Slot lag, retained WAL, replica apply lag | Consumer/replica không theo kịp và retention tăng |

Nên có cả ngưỡng tuyệt đối và ngưỡng theo xu hướng. Ví dụ, cảnh báo khi backlog tăng trong nhiều chu kỳ liên tiếp, transaction lâu nhất vượt thời gian dự kiến và storage còn dưới số giờ/ngày an toàn theo tốc độ tăng hiện tại.

## 15. Quy trình điều tra một sự cố thực tế

Giả sử filesystem tăng nhanh và truy vấn bắt đầu chậm. Có thể điều tra theo trình tự:

1. Xác định file/tablespace nào tăng: heap, WAL, undo, tempdb hay PVS.
2. Ghi lại baseline và tốc độ tăng theo phút/giờ.
3. Tìm transaction/snapshot lâu nhất và connection sở hữu nó.
4. Kiểm tra trạng thái connection ở ứng dụng: thread nào đang giữ, query/cursor nào mở, có đang chờ HTTP hay không.
5. Tìm replication slot, backup hoặc subscriber có thể giữ retention horizon.
6. Đối chiếu generation rate của UPDATE/DELETE với cleanup throughput.
7. Xác định liệu cleanup bị chặn bởi horizon cũ hay thiếu tài nguyên.
8. Chọn hành động nhỏ nhất có thể: kết thúc transaction bị bỏ quên, khắc phục consumer chậm, chia batch hoặc điều chỉnh cleanup.
9. Theo dõi horizon tiến lên và backlog giảm.
10. Xác nhận dung lượng có thể tái sử dụng; nếu cần thu nhỏ file vật lý, lập kế hoạch riêng cho thao tác rewrite/shrink.

Trong incident, ưu tiên giữ database hoạt động và tránh thao tác phá hủy. Một transaction cũ có thể là nguyên nhân, nhưng việc terminate nó có thể gây rollback lâu hoặc làm ứng dụng thất bại. Xác định owner, mức ảnh hưởng và khả năng retry trước khi can thiệp.

## 16. Kiểm thử áp lực thu gom

Có thể xây dựng integration test hoặc workload test để quan sát retention và cleanup:

### Test transaction giữ snapshot

1. Connection R bắt đầu transaction đọc và giữ snapshot.
2. Connection W thực hiện nhiều UPDATE/DELETE và commit.
3. Quan sát backlog/version store/undo tăng trong khi R vẫn mở.
4. Kết thúc R.
5. Quan sát vacuum/purge/version cleanup tiếp tục và backlog giảm.

### Test tốc độ ghi vượt cleanup

1. Tạo workload update/delete ổn định.
2. Tăng tốc độ ghi có kiểm soát.
3. Theo dõi generation rate và cleanup throughput.
4. Xác định thời điểm backlog bắt đầu tăng đều.
5. Giảm workload hoặc giải phóng retention blocker.
6. Xác nhận cleanup bắt kịp và storage ổn định.

### Test ứng dụng giữ transaction lâu

1. Mở transaction trong service.
2. Đọc dữ liệu rồi tạm dừng thread trước khi kết thúc transaction.
3. Từ connection khác tạo cập nhật liên tục.
4. Quan sát chỉ số transaction/version của engine.
5. Tiếp tục thread và xác nhận transaction kết thúc, cleanup có thể tiến lên.

### Test replica/slot retention

Với PostgreSQL, tạo slot hoặc consumer test giữ mốc cũ, tạo cập nhật và quan sát tuple/WAL retention. Sau khi consumer tiến lên hoặc slot được xử lý đúng cách, xác nhận horizon và WAL retention giảm. Không dùng slot production để thử nghiệm.

Test phải chạy trên engine/version gần môi trường triển khai. Các metric và cách cleanup phụ thuộc cấu hình, nên kết quả cần được diễn giải theo đúng engine.

## 17. Những điểm cần ghi nhớ

- MVCC cần giữ phiên bản cũ cho snapshot đang hoạt động; phiên bản chỉ có thể thu gom khi không còn transaction hoặc cơ chế nào cần nó.
- Transaction đọc lâu, idle transaction, cursor/stream mở lâu, backup và replication có thể giữ retention horizon cũ.
- Theo dõi cả retention horizon, tốc độ tạo phiên bản và cleanup throughput; backlog đơn lẻ không đủ để kết luận nguyên nhân.
- PostgreSQL giữ tuple version cũ trong heap và dùng VACUUM/autovacuum để dọn; replication slot có thể giữ tuple hoặc WAL theo các mốc khác nhau.
- InnoDB giữ undo record cho consistent read và dùng purge thread; History list length cần được theo dõi theo xu hướng.
- Oracle dùng undo segments; `V$UNDOSTAT`, `TUNED_UNDORETENTION`, `SSOLDERRCNT` và extent status giúp chẩn đoán ORA-01555/ORA-30036.
- SQL Server lưu row version trong tempdb hoặc PVS khi ADR bật; RCSI và Snapshot Isolation có thời gian sống snapshot khác nhau.
- Thu gom không nhất thiết trả dung lượng file về filesystem; nhiều engine chỉ đánh dấu không gian để tái sử dụng.
- Không kill transaction, xóa slot/file, tăng cleanup thread hoặc shrink database một cách mù quáng.
- Trong Java/ORM, tránh giữ transaction mở khi chờ người dùng, network I/O hoặc stream dữ liệu chậm.
- Cảnh báo nên dựa trên tuổi snapshot, tốc độ backlog, tiến độ cleanup và dung lượng còn lại, không chỉ một ngưỡng tuyệt đối.
- Sau khi xử lý blocker, xác nhận retention horizon tiến lên và backlog giảm qua nhiều chu kỳ lấy mẫu.
