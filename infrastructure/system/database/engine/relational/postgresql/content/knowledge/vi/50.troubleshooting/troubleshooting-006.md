# Đầy đĩa do bảng, WAL, archive hoặc nhật ký trong PostgreSQL

Sự cố hết dung lượng đĩa trong PostgreSQL có thể xuất hiện ở nhiều vị trí: data files của tables và indexes, TOAST storage, thư mục pg_wal, archive destination, temporary files, log files hoặc một tablespace riêng. Các nguyên nhân này có cách xử lý khác nhau. Xóa nhầm một file trong PGDATA có thể làm database không khởi động hoặc mất khả năng recovery; trong khi chỉ tăng dung lượng ổ đĩa mà không xử lý replication slot hay archive backlog có thể khiến dung lượng tiếp tục tăng.

Khi filesystem gần đầy, PostgreSQL có thể không ghi được WAL, không tạo được temporary files, không hoàn tất checkpoint hoặc không ghi được logs. Một database vẫn trả lời query đọc có thể đã ở trạng thái sắp mất khả năng ghi. Nếu disk đầy hoàn toàn, backend có thể báo lỗi No space left on device, transaction thất bại và cluster có thể dừng nếu không thể ghi các thành phần cần thiết.

Bài học thuộc chương **Xử lý sự cố**, tập trung vào:

- Nhận diện filesystem, mount, tablespace hoặc volume đang cạn dung lượng.
- Phân biệt dung lượng do tables, indexes, TOAST, large objects và bloat.
- Chẩn đoán pg_wal tăng do workload, checkpoint, replication slots hoặc archive failure.
- Kiểm tra archive destination, archive_command, pg_stat_archiver và backup retention.
- Nhận diện temporary files và query sort/hash spill.
- Quản lý PostgreSQL logs, rotation và logging configuration.
- Phân biệt disk space exhaustion với inode, quota và container volume exhaustion.
- Xử lý sự cố theo thứ tự an toàn, giữ nguyên WAL và dữ liệu cần recovery.
- Thu hồi dung lượng có kiểm soát, xử lý replication lag và khôi phục archiving.
- Thiết lập capacity planning, alerting và runbook phòng ngừa.

> **Quy tắc khẩn cấp:** không xóa thủ công file trong PGDATA/pg_wal, base, global hoặc các thư mục tablespace để giải phóng dung lượng. Không xóa WAL archive khi chưa xác định backup/standby retention. Trước tiên xác định filesystem nào đầy, bảo toàn khả năng recovery, rồi giải phóng dung lượng từ nguồn đã được xác minh hoặc mở rộng volume.

## 1. Hiểu các vùng lưu trữ của PostgreSQL

PostgreSQL sử dụng nhiều loại file với vòng đời và yêu cầu dung lượng khác nhau. Cần biết file nào thuộc database storage, file nào thuộc WAL, archive, logs và temporary work.

### 1.1. Data directory

data_directory (thường gọi là PGDATA) chứa cluster data, gồm:

- base/: các database files trong default tablespace.
- global/: cluster-wide catalogs và shared files.
- pg_wal/: write-ahead log segments.
- pg_tblspc/: symbolic links tới tablespaces bên ngoài data directory.
- pg_multixact/, pg_subtrans/, pg_commit_ts/: các thành phần transaction metadata khi được sử dụng.
- pg_stat/, pg_stat_tmp/: statistics files.
- pg_logical/, pg_replslot/: logical decoding/replication metadata và slot state.
- pg_xact/: transaction status data.
- Các file cấu hình, PID và control files.

Tên và nội dung một số thư mục có thể thay đổi theo version. Không sửa hoặc xóa các file nội bộ bằng công cụ filesystem.

### 1.2. Tables và indexes

Mỗi table/index có physical relation files. Relation có thể có nhiều segments khi lớn hơn giới hạn file của filesystem/PostgreSQL. Một table còn có các forks như main, FSM và visibility map.

Dung lượng table/index tăng theo số rows, kích thước row, UPDATE/DELETE tạo dead tuples, index count và key size, TOAST values, page utilization, bloat do workload hoặc vacuum không theo kịp, cùng partition count và dữ liệu từng partition.

### 1.3. TOAST storage

Các values lớn như text, bytea, jsonb có thể được nén hoặc lưu out-of-line trong TOAST table. Vì vậy, kích thước heap chính không phản ánh đầy đủ dung lượng table.

Khi điều tra, dùng pg_table_size() hoặc pg_total_relation_size() thay vì chỉ xem pg_relation_size() của main fork.

### 1.4. WAL

WAL ghi lại các thay đổi cần thiết để crash recovery và replication. Thư mục pg_wal chứa các WAL segments đang được sử dụng hoặc được giữ lại cho crash recovery, checkpoint/recycling, streaming replication, replication slots, WAL archiving và backup/PITR requirements.

WAL không phải log text thông thường. Không được xóa segment dựa trên tên hoặc tuổi file.

### 1.5. WAL archive

Khi archiving được bật, PostgreSQL gọi archive_command hoặc archive library để chuyển completed WAL segments tới archive destination. Archive thường nằm ngoài PGDATA, có thể ở filesystem khác, object storage gateway hoặc backup repository.

Archive destination đầy có thể làm archive command thất bại; PostgreSQL sẽ giữ WAL cần archive trong pg_wal và thử lại. Khi backlog tiếp tục tăng, cả archive destination lẫn primary data volume đều có thể gặp vấn đề.

### 1.6. Temporary files

Query sort, hash join, hash aggregation, materialization hoặc một số operations khác có thể spill ra temporary files khi không đủ memory. Temporary files thường nằm trong base/pgsql_tmp của database hoặc location được cấu hình qua temp_tablespaces.

Các file này thường được backend dọn khi operation/session kết thúc. Không xóa file tạm đang được backend sử dụng.

### 1.7. PostgreSQL logs

Logs có thể được ghi qua logging collector vào log_directory, ra stderr và được service manager/container runtime thu thập, qua syslog hoặc hệ thống logging bên ngoài, hoặc vào một volume riêng do managed platform quản lý.

Nếu log_directory là relative path, nó được resolve theo data directory. Logs có thể nằm trên cùng filesystem với database và làm cạn dung lượng.

### 1.8. Những nơi khác

Cũng kiểm tra backup staging directories, base backups và WAL archive copies, core dumps sau backend crash, CSV/JSON logs, export files và ETL staging data, container writable layer, Kubernetes PersistentVolumeClaim, filesystem snapshots và cloud volume snapshots, OS package cache hoặc unrelated services trên cùng mount.

Không quy mọi dung lượng tăng trên server cho PostgreSQL trước khi xác định mount và thư mục thực tế.

## 2. Triệu chứng và phân loại sự cố

### 2.1. Dấu hiệu disk full

Các dấu hiệu thường gặp:

- SQL errors có No space left on device.
- PostgreSQL log báo không thể ghi WAL, temporary file hoặc relation file.
- INSERT, UPDATE, CREATE INDEX, VACUUM hoặc backup thất bại.
- archive_command liên tục trả non-zero.
- pg_wal tăng nhanh.
- Replica lag tăng hoặc replication slot giữ WAL.
- PostgreSQL shutdown/crash hoặc không thể hoàn tất recovery.
- Log collector không ghi được file log.
- Một tablespace cụ thể hết dung lượng trong khi PGDATA vẫn còn chỗ.

### 2.2. Phân biệt filesystem full và database object lớn

Một database có thể lớn nhưng filesystem còn đủ chỗ. Ngược lại, database size không quá lớn nhưng pg_wal, logs hoặc temporary files có thể làm volume đầy.

| Nguồn | Dấu hiệu | Kiểm tra chính |
| --- | --- | --- |
| Tables/indexes/TOAST | Relation sizes tăng | pg_total_relation_size, OS directory usage |
| Table bloat | Dead tuples/free space tăng | pg_stat_user_tables, pgstattuple |
| WAL retention | pg_wal tăng nhanh | pg_replication_slots, pg_stat_archiver |
| Archive backlog | Archive command failures | pg_stat_archiver, destination capacity |
| Temporary files | Query spill nhiều | pg_stat_database.temp_files/temp_bytes |
| Logs | Log directory tăng | log_directory, OS directory usage |
| Tablespace | Một mount riêng đầy | pg_tablespace_location, df |
| Inodes/quota | Không tạo file dù bytes còn | df -i, filesystem quota |
| Container/PVC | Host còn chỗ nhưng volume đầy | Container mount/PVC metrics |

### 2.3. Xác định mức độ khẩn cấp

Đánh giá filesystem còn bao nhiêu bytes và inodes; PGDATA, pg_wal, tablespaces và archive có nằm trên cùng mount không; PostgreSQL còn nhận writes không; WAL archive có đang fail không; replication slots có giữ WAL không; backup/PITR có còn usable không; và có thể mở rộng volume nhanh không.

Nếu filesystem chứa PGDATA hoặc pg_wal gần đầy, ưu tiên bảo vệ khả năng ghi WAL và recovery. Đừng đợi tới 100% mới xử lý.

## 3. Runbook phản ứng ban đầu

Khi nhận alert disk usage cao, làm theo trình tự có kiểm soát.

### 3.1. Ghi nhận hiện trạng

Thu thập thời điểm và alert source, host/cluster/database, filesystem/mount bị ảnh hưởng, total/used/available bytes và inode usage, PostgreSQL version và trạng thái service, PGDATA/tablespaces/WAL archive/log locations, workload/deployment/backup vừa diễn ra, cùng thay đổi gần đây về replication, archiving hoặc retention.

Chụp metrics/logs trước khi cleanup để giữ evidence.

### 3.2. Xác định growth rate

Một volume đang dùng 95% nhưng ổn định có tình trạng khác volume tăng 5 GiB mỗi phút. Lấy ít nhất hai snapshots cách nhau một khoảng thời gian ngắn để tính tốc độ tăng:

```text
growth_rate_bytes_per_second =
    (used_bytes_now - used_bytes_before)
    / elapsed_seconds

estimated_time_to_full =
    available_bytes_now / growth_rate_bytes_per_second
```

Đây là ước tính tuyến tính; workload, checkpoint, archive retry và log rotation có thể làm tốc độ thay đổi nhanh.

### 3.3. Contain nguồn tăng dung lượng

Nếu đã xác định được nguồn, pause hoặc throttle job đang bulk load/backfill/index build; tạm dừng export/ETL đang ghi file staging; sửa archive destination trước khi WAL backlog tăng thêm; khôi phục replica/consumer hoặc xử lý slot theo retention policy; điều chỉnh log verbosity nếu có query logging bùng nổ, sau khi giữ evidence; giới hạn workload tạo temporary files; và mở rộng filesystem/volume nếu khả thi.

Không dừng mọi application writes một cách tự động. Chọn containment nhỏ nhất mà vẫn ngăn volume tiếp tục đầy.

### 3.4. Ưu tiên mở rộng dung lượng khi cần

Mở rộng volume/filesystem thường là cách ít rủi ro nhất khi không thể xác định ngay file nào an toàn để dọn. Sau khi mở rộng, xác nhận filesystem đã nhận capacity mới, PostgreSQL có thể ghi file, archive command/replication recovery hoạt động, rồi tiếp tục điều tra root cause và thiết lập cleanup/retention đúng policy.

Tăng dung lượng không thay thế việc xử lý slot/archive backlog hoặc log retention.

### 3.5. Không thực hiện cleanup mù

Không xóa file WAL trong pg_wal, relation file trong base, thư mục tablespace đang được PostgreSQL sử dụng, archive theo mtime mà không xét backup chain và standby needs, temporary file khi backend còn chạy, hoặc backup duy nhất. Không chạy VACUUM FULL hoặc REINDEX ngay khi volume đã gần hết chỗ. Không chạy docker system prune -a mà không biết dữ liệu/volume nào sẽ bị ảnh hưởng.

Những hành động này có thể biến disk alert thành mất dữ liệu hoặc outage kéo dài.

## 4. Kiểm tra filesystem ở operating system

SQL cho biết PostgreSQL objects và catalog state; OS cho biết mount thực sự còn bao nhiêu dung lượng.

### 4.1. Linux: xem dung lượng mount

```bash
df -h
df -h /var/lib/postgresql
df -h /mnt/pg_archive
```

Dùng path thực tế của PGDATA, tablespace và archive. Không giả định tất cả nằm trên /var/lib/postgresql.

### 4.2. Linux: kiểm tra inode

```bash
df -i
```

Filesystem có thể hết inode dù còn bytes. Khi đó PostgreSQL không tạo được file mới. Tìm directory tạo hàng triệu small files, nhưng không xóa file nội bộ PostgreSQL tùy tiện.

### 4.3. Linux: tìm directory lớn

```bash
sudo du -xhd1 /var/lib/postgresql
sudo du -xhd1 /var/log
sudo du -xhd1 /mnt/pg_archive
```

-x giữ việc scan trên cùng filesystem, tránh cộng nhầm mount khác. du có thể tạo I/O đáng kể trên directory lớn; chạy có kiểm soát và không dùng output thay cho catalog understanding.

### 4.4. File đã xóa nhưng process vẫn giữ mở

Trên Linux, file đã unlink có thể vẫn chiếm disk cho tới khi process đóng file descriptor. lsof +L1 có thể giúp tìm deleted-open files. Nếu log rotation unlink file nhưng process vẫn ghi vào file cũ, dung lượng chưa được giải phóng.

Xử lý bằng cơ chế reopen/rotate logs phù hợp với service, không kill process database một cách tùy tiện.

### 4.5. Windows

Trên Windows server, kiểm tra volume bằng PowerShell:

```powershell
Get-Volume |
    Select-Object DriveLetter, FileSystemLabel, Size, SizeRemaining, HealthStatus

Get-PSDrive -PSProvider FileSystem
```

Dùng công cụ quản trị filesystem để tìm thư mục lớn. Kiểm tra volume chứa data directory, WAL, tablespaces, logs và archive riêng biệt.

### 4.6. Quota và reserved blocks

Kiểm tra filesystem quotas, container limits và reserved blocks. Một database service account có thể hết quota dù df vẫn báo còn dung lượng cho root hoặc user khác.

## 5. Xác định PostgreSQL storage paths

Bắt đầu bằng configuration thực tế:

```sql
SHOW data_directory;
SHOW config_file;
SHOW log_destination;
SHOW logging_collector;
SHOW log_directory;
SHOW archive_mode;
SHOW archive_command;
SHOW archive_library;
SHOW wal_level;
SHOW max_wal_size;
SHOW min_wal_size;
SHOW wal_keep_size;
SHOW max_slot_wal_keep_size;
```

Một số settings chỉ tồn tại ở các PostgreSQL versions nhất định hoặc có thể không được hỗ trợ bởi managed service. Nếu SHOW báo unknown parameter, kiểm tra version và provider configuration thay vì giả định server hỏng.

### 5.1. Xác định tablespace locations

```sql
SELECT
    spcname AS tablespace_name,
    pg_tablespace_location(oid) AS location,
    pg_size_pretty(pg_tablespace_size(oid)) AS size
FROM pg_tablespace
ORDER BY spcname;
```

pg_default và pg_global có location rỗng vì chúng nằm trong data directory theo cấu trúc cluster. Tablespace riêng có thể map tới mount riêng.

### 5.2. Kiểm tra database sizes

```sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
```

Tổng database sizes không bao gồm WAL archive ngoài cluster, logs hoặc mọi file tạm bên ngoài relation storage. Không cộng các con số này rồi giả định bằng tổng filesystem usage.

### 5.3. Kiểm tra phiên bản

```sql
SELECT version();
SHOW server_version_num;
```

Version giúp xác định catalog fields, statistics views và parameters có sẵn. Ghi lại version trong incident notes.

## 6. Tìm tables và indexes chiếm nhiều dung lượng

### 6.1. Top relations theo tổng size

```sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS main_fork,
    pg_size_pretty(pg_table_size(relid)) AS table_including_toast,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
```

pg_relation_size mặc định đo main fork của relation. pg_table_size gồm table storage và các thành phần liên quan như TOAST, FSM, visibility map; không cộng indexes. pg_indexes_size đo indexes của table. pg_total_relation_size cộng table storage và indexes.

### 6.2. Top indexes

```sql
SELECT
    schemaname,
    tablename,
    indexrelname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 30;
```

idx_scan là số scans kể từ lần reset statistics gần nhất. Index có scan count thấp không tự động là unused: statistics có thể vừa reset, index có thể phục vụ constraint/rare queries hoặc workload theo mùa.

### 6.3. Top tables theo dead tuples

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_percent,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

Các tuple counts là estimates từ statistics, không phải phép đếm chính xác. Dùng để định hướng điều tra bloat và vacuum activity.

### 6.4. Kiểm tra TOAST relation

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.reltoastrelid::regclass AS toast_relation,
    pg_size_pretty(pg_total_relation_size(c.reltoastrelid)) AS toast_total_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND c.reltoastrelid <> 0
ORDER BY pg_total_relation_size(c.reltoastrelid) DESC
LIMIT 30;
```

TOAST relation có thể lớn khi table chứa nhiều text/jsonb/bytea values. Xem xét dữ liệu thực tế, compression/storage strategy và query patterns trước khi thay đổi schema.

### 6.5. Partitioned tables

Một parent partitioned table có thể không lưu rows trực tiếp; dữ liệu nằm trong child partitions. Inventory các inheritance edges:

```sql
SELECT
    parent.oid::regclass AS parent_table,
    child.oid::regclass AS partition_table,
    pg_size_pretty(pg_total_relation_size(child.oid)) AS total_size
FROM pg_inherits AS inh
JOIN pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_class AS child
    ON child.oid = inh.inhrelid
ORDER BY pg_total_relation_size(child.oid) DESC;
```

Với partition nhiều tầng, query trên liệt kê từng inheritance edge. Có thể dùng recursive CTE để dựng toàn hierarchy.

### 6.6. Large objects

Large objects được lưu trong catalog relations như pg_largeobject và metadata pg_largeobject_metadata. Nếu application dùng lo_* APIs, kiểm tra usage của large objects và cleanup theo ownership/reference policy. Không xóa rows trực tiếp khỏi system catalogs.

## 7. Table bloat và vacuum

Dung lượng relation tăng không nhất thiết là dữ liệu nghiệp vụ đang tăng tương ứng. UPDATE/DELETE tạo dead tuple versions do MVCC; VACUUM cần dọn chúng khi không còn snapshot nào cần.

### 7.1. Dead tuples và long-running transactions

Dead tuples có thể chiếm pages nhưng chưa được reclaim. Long-running transactions, prepared transactions hoặc replication horizons có thể ngăn cleanup.

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
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Không terminate transaction chỉ dựa vào tuổi; xác định owner và impact trước.

### 7.2. VACUUM thông thường

```sql
VACUUM (VERBOSE, ANALYZE) app.orders;
```

VACUUM thường làm không gian trong relation có thể tái sử dụng cho rows tương lai. Nó thường không thu nhỏ file table trên filesystem trừ một số trường hợp có thể truncate pages ở cuối relation.

VACUUM không phải thao tác compact/rewrite toàn bộ table.

### 7.3. VACUUM FULL

```sql
VACUUM (FULL, ANALYZE) app.orders;
```

VACUUM FULL rewrite table và cần ACCESS EXCLUSIVE lock. Nó cần dung lượng bổ sung để tạo bản mới và có thể làm tăng WAL/replication load. Không chạy như phản ứng tức thời khi filesystem đã đầy.

### 7.4. pg_repack và index bloat

pg_repack có thể giảm bloat với thời gian lock mạnh ngắn hơn một số phương án rewrite truyền thống, nhưng vẫn cần extra disk, WAL, trigger/log table và các lock phases. Đây là extension/tool riêng, không phải lệnh PostgreSQL core.

REINDEX tạo index mới, cần extra disk và I/O. REINDEX CONCURRENTLY có thêm phases và không thể chạy trong transaction block; nó vẫn cần dung lượng cho index cũ và mới cùng tồn tại.

### 7.5. pgstattuple

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstattuple('app.orders');
```

pgstattuple có thể cung cấp số liệu chi tiết hơn về tuple/free space. Đọc toàn relation có thể tốn I/O. Chỉ chạy trên object được chọn, trong maintenance window phù hợp. Có thể dùng pgstattuple_approx nếu cần ước tính nhẹ hơn theo behavior của extension/version.

## 8. WAL: vì sao pg_wal tăng?

WAL tăng không nhất thiết do lỗi. Một bulk load, UPDATE lớn, CREATE INDEX hoặc checkpoint workload có thể tạo WAL nhanh. Vấn đề xảy ra khi PostgreSQL không thể recycle segments vì một consumer hoặc archive chưa theo kịp.

### 8.1. WAL generation

Các hoạt động tạo WAL gồm INSERT/UPDATE/DELETE, CREATE INDEX và REINDEX, table rewrite, VACUUM FULL, CLUSTER, một số DDL/catalog updates, full-page images sau checkpoint khi full_page_writes bật, cùng bulk operations.

Đo tốc độ WAL thay vì chỉ nhìn số file trong pg_wal.

### 8.2. max_wal_size không phải hard cap

max_wal_size là mục tiêu mềm để điều khiển checkpoint frequency. WAL có thể vượt mức này khi cần giữ segments cho archiving, replication slots hoặc các yêu cầu khác.

Tăng max_wal_size có thể giảm checkpoint pressure nhưng cũng có thể cho phép nhiều WAL hơn tồn tại. Không tăng setting này như cách dọn disk.

### 8.3. min_wal_size và wal_keep_size

min_wal_size ảnh hưởng số WAL segments PostgreSQL giữ để tái sử dụng. Đây không phải giới hạn tổng WAL retention.

wal_keep_size yêu cầu giữ một lượng WAL tối thiểu cho standby streaming trong một số tình huống. Đây không phải cap cho tổng WAL và không giải quyết slot/archive backlog.

### 8.4. Replication slots và archiving

Replication slot giữ WAL cần thiết cho consumer. Nếu standby hoặc logical subscriber ngừng hoạt động, slot có thể giữ WAL rất lâu.

Khi archive command thất bại, các WAL segments cần archive không thể được recycle theo cách thông thường. pg_wal có thể tăng dù workload không thay đổi.

## 9. Đo kích thước WAL và retention

### 9.1. Dung lượng thư mục pg_wal

Trên PostgreSQL versions hỗ trợ pg_ls_waldir():

```sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)) AS wal_directory_size
FROM pg_ls_waldir();
```

Function có yêu cầu privilege phù hợp. Nếu role không có quyền, dùng OS metrics hoặc role giám sát được cấp quyền. Đừng cấp superuser chỉ để dashboard chạy một query.

### 9.2. WAL statistics

Trên versions có pg_stat_wal:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
```

wal_bytes là counter tích lũy kể từ stats reset. Lấy hai snapshots cách nhau một khoảng thời gian để ước tính generation rate. Catalog fields và view availability phụ thuộc version.

### 9.3. Replication slots inventory

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
```

Một số columns như wal_status và safe_wal_size không có trên mọi major version. Điều chỉnh query theo catalog thực tế.

### 9.4. Ước tính WAL giữ bởi slot

Trên primary, có thể ước tính khoảng cách LSN:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS retained_wal_estimate
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC;
```

Đây là ước tính khoảng cách LSN từ restart_lsn tới current WAL position, không phải phép đo filesystem bytes chính xác. Nhiều slots có thể giữ chung các segments; không cộng các estimates rồi coi đó là tổng dung lượng bị chiếm.

### 9.5. Standby lag

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

Lag time fields có thể NULL hoặc không đại diện đầy đủ độ trễ khi không có sample gần đây. Có thể tính LSN distance để bổ sung.

### 9.6. Xác định inactive slot

Slot active = false không nhất thiết vô dụng. Nó có thể thuộc subscriber tạm ngắt, backup service hoặc consumer đang maintenance. Tra owner/service và retention contract trước khi drop.

### 9.7. max_slot_wal_keep_size

max_slot_wal_keep_size giới hạn lượng WAL được giữ cho replication slots ở các versions hỗ trợ. Khi vượt giới hạn, slot có thể bị invalidated và consumer phải resynchronize/reinitialize.

Không giảm setting trong incident mà không hiểu hậu quả. Một slot bị invalid có thể làm mất khả năng tiếp tục replication/CDC từ vị trí cũ.

## 10. Xử lý replication slot giữ WAL

### 10.1. Xác định slot owner

Gắn slot với physical standby, logical subscriber, CDC connector, backup tool, custom logical decoding client hoặc managed database service. Kiểm tra monitoring và application config của consumer.

### 10.2. Khôi phục consumer trước

Nếu consumer còn cần dữ liệu, ưu tiên khôi phục network, credentials, subscription hoặc worker để slot tiến lên và WAL có thể được recycle khi các điều kiện khác cho phép.

### 10.3. Slot không còn dùng

Chỉ drop khi owner xác nhận không còn consumer hoặc recovery requirement:

```sql
SELECT pg_drop_replication_slot('old_cdc_slot');
```

Không drop active slot. Trước khi drop, xác nhận consumer có thể được tạo lại từ snapshot/rebootstrap và business owner chấp thuận mất continuity.

### 10.4. Logical subscription và physical slot

Nếu slot thuộc logical replication subscription, quản lý thông qua subscription lifecycle và documented procedures. Physical standby có thể cần slot để nhận WAL sau downtime. Nếu drop slot, standby có thể cần reinitialize từ base backup nếu WAL cần thiết đã bị recycle.

Drop slot có thể giải phóng WAL nhưng đồng thời làm mất khả năng resume consumer. Đây là thay đổi replication state, không phải xóa file rác.

## 11. WAL archive và archive backlog

### 11.1. Kiểm tra archive configuration

```sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_library;
SHOW archive_timeout;
```

Nếu archive_mode off, PostgreSQL không archive WAL bằng cơ chế archiving truyền thống. Nếu dùng archive library, archive_command có thể trống.

### 11.2. pg_stat_archiver

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

Nếu failed_count tăng, kiểm tra command logs, permissions, network, destination capacity và file naming. Stats có thể reset nên so sánh timestamps/counters với incident timeline.

### 11.3. Archive command contract

archive_command phải trả exit status 0 khi WAL file được lưu thành công. Nếu trả non-zero, PostgreSQL sẽ thử lại. Command phải idempotent: nếu file đã tồn tại với cùng nội dung, không được làm hỏng archive hoặc báo success cho một file khác.

Ví dụ minh họa cho local archive path:

```conf
archive_mode = on
archive_command = 'test ! -f /mnt/pg_archive/%f && cp %p /mnt/pg_archive/%f'
```

Đây là ví dụ đơn giản, không phải cấu hình production hoàn chỉnh. Cần xử lý permissions, atomic publish, checksums, duplicate delivery, filesystem errors và retention. Với cloud storage, dùng archiver/tool được hỗ trợ thay vì shell command tự chế nếu có.

### 11.4. Archive destination đầy

Nếu archive volume đầy, xác nhận mount và capacity của archive path; kiểm tra backup retention và standby recovery needs; mở rộng destination hoặc dọn dữ liệu đã hết retention theo backup policy; sửa archive command credentials/permissions nếu có; xác nhận archive command trả 0; theo dõi pg_stat_archiver và WAL directory cho đến khi backlog giảm.

Giải phóng archive disk không tự động giải phóng primary pg_wal nếu command vẫn fail hoặc slot vẫn giữ segments.

### 11.5. Archive destination unreachable

Network outage, expired credentials, DNS, TLS, bucket policy hoặc mount disconnect có thể khiến archive command thất bại. Kiểm tra cả service logs và remote storage metrics.

### 11.6. Archive status files

Các file .ready trong pg_wal/archive_status biểu thị segments cần archive; .done biểu thị archive command đã hoàn tất cho segment tương ứng. Đây là metadata nội bộ để PostgreSQL quản lý archiving.

Có thể inventory trạng thái bằng OS tools, nhưng không xóa/đổi tên .ready hoặc .done thủ công để ép PostgreSQL bỏ qua archive.

### 11.7. Archive retention

WAL archive có thể cần cho PITR, standby recovery, backup chain, logical decoding/CDC workflows và compliance/audit recovery requirements.

Chỉ cleanup bằng retention policy aware với base backups và standby requirements. pg_archivecleanup có thể hữu ích trong topology phù hợp, nhưng phải tính đúng oldest required WAL segment. Không chạy nó trên archive repository dùng chung nếu chưa hiểu mọi consumers.

## 12. Checkpoint và WAL recycling

Checkpoint ghi trạng thái cần thiết để recovery biết từ đâu cần replay WAL. Sau checkpoint, một số WAL segments có thể trở thành ứng viên recycle nếu không còn retention requirement khác.

Ngay cả khi checkpoint hoàn tất, PostgreSQL không thể recycle WAL mà replication slot hoặc archiving vẫn cần. Vì vậy CHECKPOINT không phải lệnh giải phóng WAL tùy ý.

Checkpoint quá thường xuyên có thể tăng I/O và full-page writes. Checkpoint quá thưa có thể cần nhiều WAL và kéo dài recovery. Cấu hình cần dựa trên workload, storage và recovery objectives.

View/columns checkpoint statistics có thể khác theo major version. Kiểm tra pg_stat_bgwriter và các statistics views phù hợp version; ở các versions mới, một số checkpoint metrics được tách sang view khác.

Không spam CHECKPOINT. Nó có thể tạo I/O pressure và không giải quyết WAL bị giữ bởi slot/archive. Tăng max_wal_size có thể giảm số checkpoint theo workload nhưng có thể tăng lượng WAL được phép tích lũy.

## 13. Temporary files làm đầy disk

### 13.1. Nguồn temporary files

Temporary files có thể được tạo bởi ORDER BY/sort không fit trong work_mem, hash joins/hash aggregation, DISTINCT và GROUP BY, materialized intermediate results, một số index builds và explicit temporary tables.

### 13.2. pg_stat_database

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_bytes_since_reset,
    stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY temp_bytes DESC;
```

temp_bytes là counter tích lũy kể từ stats reset, không phải số temporary files hiện còn trên disk.

### 13.3. Log temporary files

Có thể cấu hình:

```conf
log_temp_files = 64MB
```

Setting này log temporary files có kích thước vượt threshold khi file được xóa. Giá trị 0 log mọi temp file; giá trị âm tắt logging. Chọn threshold để tránh log noise.

### 13.4. Tìm query tạo temp files

Kết hợp pg_stat_statements nếu extension được cài, query logs với duration/temporary file messages, pg_stat_database.temp_files/temp_bytes, pg_stat_activity để tìm active queries và EXPLAIN (ANALYZE, BUFFERS) trên test workload.

Một query đang chạy có thể tạo file rất lớn sau thời điểm lấy snapshot; statistics không luôn chỉ ra chính xác file path hoặc backend owner.

### 13.5. work_mem

work_mem là memory budget cho mỗi sort/hash operation, không phải per-session cap. Một query có nhiều operations và nhiều concurrent sessions có thể dùng tổng memory lớn hơn nhiều lần giá trị này.

Tăng work_mem để giảm spill có thể làm memory exhaustion. Dùng SET LOCAL cho một query đã hiểu, thay vì tăng global setting tùy tiện.

### 13.6. temp_file_limit và temp_tablespaces

temp_file_limit giới hạn tổng dung lượng temporary files mà một process có thể dùng trong các điều kiện PostgreSQL quy định:

```sql
SHOW temp_file_limit;
SHOW temp_tablespaces;
```

Có thể đặt giới hạn theo role/database hoặc session phù hợp. Khi vượt limit, query có thể bị hủy; điều này bảo vệ disk nhưng cũng có thể làm application requests fail.

Nếu temp tablespace riêng đầy, query spill có thể fail dù PGDATA còn chỗ. Kiểm tra đúng mount.

### 13.7. Không xóa pgsql_tmp đang hoạt động

Temporary files thường được backend dọn khi kết thúc operation/session. Nếu thấy file lớn, xác định PID/backend và query trước. Nếu backend đã crash, PostgreSQL xử lý orphan temporary files theo startup cleanup; không xóa file của process đang chạy.

## 14. PostgreSQL logs làm đầy disk

### 14.1. Xác định log destination

```sql
SHOW log_destination;
SHOW logging_collector;
SHOW log_directory;
SHOW log_filename;
SHOW log_rotation_age;
SHOW log_rotation_size;
SHOW log_truncate_on_rotation;
SHOW log_min_duration_statement;
SHOW log_statement;
```

log_directory có thể là relative path theo data directory hoặc absolute path. Nếu logging collector off, logs có thể được gửi qua stderr/syslog/service manager thay vì thư mục do PostgreSQL quản lý.

### 14.2. Log rotation

Một cấu hình ví dụ:

```conf
logging_collector = on
log_destination = 'stderr'
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_truncate_on_rotation = on
```

Đây là ví dụ, cần điều chỉnh theo traffic và retention. log_truncate_on_rotation có semantics phụ thuộc filename/rotation timing; không thay thế external retention policy.

### 14.3. Log verbosity

Các setting như log_statement = all, log_min_duration_statement = 0 hoặc verbose error logging có thể tạo lượng log rất lớn. Kiểm tra thay đổi gần đây và chỉ giữ mức cần thiết cho incident/security requirements.

Không tắt logging hoàn toàn chỉ để giảm disk khi đang điều tra sự cố. Có thể giảm noisy categories hoặc tăng threshold sau khi lưu evidence.

### 14.4. Retention và deleted-open files

Dùng log rotation/collector, OS logrotate hoặc centralized logging với retention có chủ đích. Nếu PostgreSQL giữ file descriptor tới file đã unlink, cần cơ chế reopen/reload phù hợp để giải phóng disk.

Không xóa log đang được ghi mà không hiểu process handling.

### 14.5. Logs trên container và managed database

Nếu PostgreSQL ghi stderr, Docker/container runtime có thể lưu logs trong host storage hoặc logging driver. Kiểm tra container log rotation và node disk pressure. PostgreSQL log_rotation_size không quản lý Docker json-file logs.

Managed service có thể lưu logs trong provider logging service hoặc expose download/export. Dùng provider retention/rotation controls; không giả định có quyền truy cập host filesystem.

### 14.6. Audit logs

Audit logs có thể cần retention dài hơn operational logs. Tách storage/retention policy nếu cần, bảo vệ integrity và hạn chế dữ liệu nhạy cảm trong logs.

## 15. Tablespace hoặc mount riêng bị đầy

### 15.1. Xác định relation thuộc tablespace nào

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    COALESCE(ts.spcname, 'database default') AS tablespace_name,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
LEFT JOIN pg_tablespace AS ts
    ON ts.oid = NULLIF(c.reltablespace, 0)
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND c.relkind IN ('r', 'i', 'm', 't')
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 50;
```

reltablespace = 0 thường có nghĩa relation dùng database default tablespace. Database default có thể khác pg_default; kiểm tra pg_database.dattablespace khi cần xác định chính xác.

### 15.2. Database default tablespace

```sql
SELECT
    datname,
    dattablespace::regclass AS default_tablespace
FROM pg_database
ORDER BY datname;
```

### 15.3. Di chuyển relation

ALTER TABLE ... SET TABLESPACE hoặc ALTER INDEX ... SET TABLESPACE có thể copy physical files, cần lock và dung lượng ở destination. Không dùng migration move để chữa filesystem đã cạn nếu chưa có đủ headroom ở cả nguồn và đích.

### 15.4. Tablespace location mất mount

Nếu mount không được attach khi PostgreSQL start, relation files có thể không truy cập được. Không tạo thư mục rỗng cùng path để đánh lừa PostgreSQL. Khôi phục đúng mount/device và kiểm tra filesystem integrity.

## 16. Kiểm tra backup và archive storage

### 16.1. Phân biệt base backup và WAL archive

Base backup là bản sao dữ liệu cluster tại một thời điểm. WAL archive cung cấp log segments để replay tới thời điểm cần thiết. PITR thường cần cả base backup hợp lệ và WAL liên tục từ backup tới recovery target.

### 16.2. Không xóa WAL archive theo tuổi file đơn giản

Một WAL segment cũ vẫn có thể cần cho base backup đang trong retention hoặc standby đang replay chậm. Retention cần biết backup nào còn hợp lệ, WAL range mà từng backup cần, standby recovery point, logical decoding/CDC retention, PITR window đã cam kết và replication topology.

### 16.3. Backup catalog và archive cleanup

Dùng backup tool/catalog để xác định backup chains và retention. Không chỉ dựa vào directory listing.

Nếu dùng pg_archivecleanup, xác định đúng oldest segment cần giữ và chỉ áp dụng cho archive directory được dành riêng cho standby/topology đó. Không dùng chung một cleanup cutoff cho repository nhiều clusters nếu không có coordination.

### 16.4. Kiểm tra backup restore

Một cleanup chỉ an toàn khi backup còn restore được. Kiểm thử restore định kỳ và xác minh WAL archive continuity.

## 17. Tìm nguyên nhân tăng dung lượng nhanh

### 17.1. Bulk load hoặc backfill

COPY/INSERT/UPDATE lớn có thể tăng table size và WAL. Kiểm tra application release, ETL schedule, migration jobs và batch sizes.

### 17.2. UPDATE tạo dead tuples

UPDATE tạo row versions mới. Nếu autovacuum không theo kịp, table/index bloat tăng. Kiểm tra vacuum thresholds, table-specific settings, long transactions và I/O capacity.

### 17.3. CREATE INDEX/REINDEX và table rewrite

Index build cần space cho index mới. Concurrent build có thể tạm giữ cả old/new index. Theo dõi pg_stat_progress_create_index khi operation đang chạy.

ALTER COLUMN TYPE, VACUUM FULL, CLUSTER và một số DDL có thể rewrite relation. Ước tính peak space, WAL và replication impact trước khi chạy.

### 17.4. Replication slot và archive command

Một CDC consumer ngừng chạy có thể khiến restart_lsn đứng yên và WAL tăng liên tục. Alert theo retained WAL per slot và slot age/activity.

Destination full, permissions, network hoặc credentials khiến archive failure count tăng và WAL không được recycle.

### 17.5. Logging, temp spill và backup staging

log_statement = all, duration threshold quá thấp, audit logging hoặc lỗi retry liên tục có thể tạo hàng GB logs.

Sort/hash queries, reporting workload hoặc query plan regression có thể tạo temp files lớn. Kiểm tra temp_bytes và query stats.

Backup job có thể tạo temporary copies trên cùng volume. Kiểm tra backup staging và retention, tránh xóa bản duy nhất còn khả năng restore.

### 17.6. Core dumps

Crash lặp lại có thể tạo core dump lớn. Xác định nguồn và xử lý theo OS crash-dump policy sau khi giữ evidence cần thiết.

## 18. Các truy vấn chẩn đoán tổng hợp

### 18.1. Database sizes

```sql
SELECT
    datname,
    pg_database_size(datname) AS bytes,
    pg_size_pretty(pg_database_size(datname)) AS pretty_size
FROM pg_database
WHERE datallowconn
ORDER BY bytes DESC;
```

### 18.2. Top user tables

```sql
SELECT
    schemaname,
    relname,
    pg_total_relation_size(relid) AS bytes,
    pg_size_pretty(pg_total_relation_size(relid)) AS pretty_size,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
ORDER BY bytes DESC
LIMIT 25;
```

### 18.3. Top indexes

```sql
SELECT
    schemaname,
    relname,
    indexrelname,
    pg_relation_size(indexrelid) AS bytes,
    pg_size_pretty(pg_relation_size(indexrelid)) AS pretty_size,
    idx_scan
FROM pg_stat_user_indexes
ORDER BY bytes DESC
LIMIT 25;
```

### 18.4. WAL directory

```sql
SELECT
    count(*) AS file_count,
    sum(size) AS bytes,
    pg_size_pretty(sum(size)) AS pretty_size
FROM pg_ls_waldir();
```

### 18.5. Archive health

```sql
SELECT *
FROM pg_stat_archiver;
```

### 18.6. Replication slots

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

### 18.7. Temporary file counters

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
```

### 18.8. Long-running transactions

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 250) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 18.9. Vacuum và index build activity

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
```

```sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    phase,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
```

Các progress views có mặt tùy operation/version. Nếu query không trả rows, có thể không có operation tương ứng đang chạy; điều đó không chứng minh không có disk pressure.

## 19. Xử lý khẩn cấp theo từng nguồn

### 19.1. Nếu table/index data chiếm dung lượng

Xác định top relations và growth rate; tìm bulk jobs, backfills hoặc table rewrite đang chạy; pause/throttle producer nếu growth vượt capacity; kiểm tra dead tuples và vacuum progress; không chạy VACUUM FULL/REINDEX khi thiếu headroom; mở rộng volume hoặc chuyển workload sang storage phù hợp; lập maintenance plan để reclaim bloat sau khi ổn định.

### 19.2. Nếu pg_wal chiếm dung lượng

Kiểm tra pg_stat_archiver, pg_replication_slots và retained LSN; kiểm tra standby/CDC consumers; kiểm tra archive destination capacity và connectivity; sửa archive path/credentials/permissions; khôi phục consumer cần thiết; chỉ drop slot sau owner approval và recovery impact review; theo dõi WAL directory giảm/recycle sau khi retention blockers được giải quyết.

Không xóa WAL segment bằng filesystem.

### 19.3. Nếu archive volume đầy

Xác định backup chains và retention; mở rộng archive storage nếu cần; cleanup chỉ phần đã hết retention theo backup catalog; sửa archive command và xác nhận success; theo dõi backlog được archive và primary WAL được recycle.

### 19.4. Nếu temporary files chiếm dung lượng

Tìm queries tạo temp spill; dừng hoặc throttle reporting/job gây tăng đột biến; xem query plan, indexes, sort/hash operations; điều chỉnh work_mem có giới hạn và đo concurrency; đặt temp_file_limit theo role/database khi phù hợp; kiểm tra temp tablespace; để backend kết thúc/cleanup file theo lifecycle.

### 19.5. Nếu logs chiếm dung lượng

Xác định log destination và file owner; giữ evidence cần thiết cho incident; sửa rotation/retention; giảm log verbosity gây bùng nổ nếu policy cho phép; reopen logs qua cơ chế phù hợp nếu process giữ deleted file descriptor; tách log volume hoặc centralized logging cho tương lai.

### 19.6. Nếu một tablespace đầy

Map relation tới tablespace và mount; kiểm tra mount có bị disconnect hay không; mở rộng volume hoặc giải phóng file ngoài database đã được xác minh; tránh di chuyển relation khi source/destination thiếu capacity; xác minh tablespace location trước khi PostgreSQL restart.

## 20. Khôi phục khi PostgreSQL không thể ghi hoặc đã dừng

### 20.1. Mở rộng filesystem trước

Nếu PostgreSQL dừng vì disk full, ưu tiên tăng capacity hoặc giải phóng dung lượng an toàn bên ngoài database storage. Đảm bảo đủ headroom để startup recovery, ghi WAL và logs.

### 20.2. Kiểm tra mount

Xác nhận mọi mount chứa PGDATA, tablespaces, WAL symlinks và required storage đang được attach đúng. Một mount rỗng thay thế mount cũ có thể khiến PostgreSQL thấy directory trống hoặc mất relation files.

### 20.3. Đọc startup logs

Tìm lỗi cuối cùng về WAL, checkpoint, control file, relation file, permissions và filesystem. Phân biệt disk-full failure với corruption hoặc missing tablespace.

### 20.4. Không initdb lại hoặc xóa WAL

Không chạy initdb lên data directory cũ để sửa disk full. Initdb tạo cluster mới và có thể phá hủy khả năng truy cập dữ liệu hiện tại.

Không xóa WAL để PostgreSQL khởi động. Nếu WAL cần cho crash recovery hoặc archive continuity đã bị xóa, cluster có thể không khởi động hoặc recovery không thể hoàn tất. Phục hồi từ backup/WAL hợp lệ theo documented recovery procedure.

### 20.5. Sau khi service khởi động

Xác nhận database consistency và logs; kiểm tra archive health, replication slots/standbys, tablespace paths, application writes/read behavior và backup job. Theo dõi disk growth rate. Chỉ resume bulk jobs khi capacity ổn định.

Nếu nghi WAL hoặc data files bị xóa, dừng thao tác cleanup, bảo toàn volume/snapshot hiện tại và đánh giá backup/PITR hoặc chuyên gia PostgreSQL recovery. Không tự tạo file rỗng hoặc sửa catalog để lấp chỗ trống.

## 21. Reclaim dung lượng an toàn

### 21.1. Logs và backup staging

Có thể cleanup logs đã hết retention theo logging policy sau khi xác nhận chúng không còn được process mở và không thuộc evidence cần giữ.

Xóa staging files chỉ khi backup job hoàn tất/failed state đã rõ, bản backup chính thức đã được xác minh và retention cho phép. Không xóa backup duy nhất.

### 21.2. Archive retention

Dùng backup catalog/retention-aware cleanup. Kiểm tra mọi base backups và standby consumers trước khi xóa WAL archive.

### 21.3. Temporary files orphaned

Nếu PostgreSQL đã dừng sạch hoặc backend process đã kết thúc, startup cleanup thường xử lý temp files. Nếu còn orphan files sau crash, chỉ cleanup theo documented procedure sau khi xác nhận không backend nào sử dụng chúng và path đúng là temp area.

### 21.4. Table bloat

Sau khi có đủ headroom, VACUUM thường để reclaim reusable space; điều chỉnh autovacuum thresholds/cost limits theo table workload; đánh giá pg_repack hoặc VACUUM FULL cho maintenance window; đánh giá index bloat và reindex; kiểm tra long-running transactions/replication horizons.

### 21.5. Unused indexes

Không drop index chỉ dựa trên idx_scan thấp trong incident. Xác nhận statistics window, constraint dependencies, query patterns và seasonal workload. Dùng DROP INDEX CONCURRENTLY khi phù hợp, nhưng nhớ nó vẫn cần tài nguyên và không chạy trong transaction block.

### 21.6. Move data sang tablespace khác

Di chuyển relation có thể giải phóng một mount nhưng cần capacity và lock ở destination. Plan từng object, kiểm tra index/TOAST/partition behavior và rollback path.

## 22. Capacity planning cho PostgreSQL

### 22.1. Tính growth theo workload

Theo dõi growth theo ngày/tuần/tháng của table data, indexes, TOAST, WAL, archive, logs, temporary files và backup staging. Tách growth bình thường và growth do maintenance/incident.

### 22.2. Dự trù peak, không chỉ steady state

Một operation có thể cần đồng thời old table/index files, new table/index copy, WAL được tạo trong operation, archive backlog, temporary sort/build files, backup staging và safety headroom.

Không chỉ provision theo final relation size.

### 22.3. Headroom và time-to-full

Đặt ngưỡng cảnh báo trước khi volume đạt 100%. Ví dụ policy nội bộ có thể cảnh báo ở 70%, 80%, 90% và critical ở mức cao hơn; chọn thresholds theo growth rate và thời gian mở rộng volume.

Dùng available bytes và growth rate để ước tính thời gian tới full. Alert dựa trên time-to-full có thể hữu ích hơn percentage đơn lẻ.

### 22.4. Tách storage domains

Khi có thể, tách database data, WAL, WAL archive/backup repository, PostgreSQL logs, temporary workload và application/export staging. Tách mount giúp sự cố một loại file không ngay lập tức làm cạn toàn bộ cluster storage, nhưng cần quản lý capacity riêng cho từng volume.

### 22.5. Cloud volumes, containers và Kubernetes

Theo dõi provisioned capacity, burst credits/IOPS throughput, filesystem expansion và cloud billing. Tăng volume có thể cần filesystem grow step riêng sau khi provider cấp thêm block capacity.

Với container/Kubernetes, theo dõi PVC capacity/usage, node ephemeral storage, container writable layer, log driver storage, volume mount path, StorageClass expansion support và pod eviction thresholds.

Host còn dung lượng không đảm bảo PVC hoặc container quota còn dung lượng.

## 23. Monitoring và alerting

### 23.1. Filesystem metrics

Alert theo từng mount: used bytes/percent, available bytes, inode usage, growth rate/time-to-full, I/O latency và volume attach/health.

### 23.2. PostgreSQL relation metrics

Theo dõi database/table/index/TOAST sizes theo thời gian, dead tuples, autovacuum activity và relation growth.

### 23.3. WAL metrics

Theo dõi pg_wal directory size, WAL generation bytes/sec, replication slot retained WAL, inactive slot age, pg_stat_archiver.failed_count, last successful archive time, standby replay lag và WAL archive backlog.

### 23.4. Temporary file và logging metrics

Theo dõi pg_stat_database.temp_files/temp_bytes, query-level temp blocks từ pg_stat_statements nếu version/extension hỗ trợ, log_temp_files messages, log bytes/day, rotation success, external log driver storage và retention cleanup.

### 23.5. Alert theo nguyên nhân

Một alert disk 90% chỉ báo hậu quả. Kết hợp alert cụ thể như archive failed count tăng, slot retained WAL vượt threshold, inactive slot giữ WAL quá lâu, temp bytes tăng đột biến, table growth vượt baseline, long transaction age vượt threshold, log volume tăng nhanh và backup staging vượt retention.

## 24. Dashboard điều tra

Một dashboard hữu ích nên đặt các signals cạnh nhau theo cùng timeline:

| Nhóm | Metrics | Câu hỏi |
| --- | --- | --- |
| Filesystem | Used/available/inodes/growth | Mount nào đầy và khi nào? |
| Relation | Database/table/index/TOAST size | Dữ liệu nào tăng? |
| Vacuum | Dead tuples, last autovacuum, progress | Cleanup có theo kịp không? |
| WAL | pg_wal size, wal_bytes/sec | WAL đang được tạo/giữ bao nhiêu? |
| Replication | Slot retained bytes, replay lag | Consumer nào giữ WAL? |
| Archiving | failed_count, last_archived_time | WAL có được archive không? |
| Temp | temp_files/temp_bytes | Query nào tạo spill? |
| Logs | Bytes/hour, rotation status | Log source nào bùng nổ? |
| Workload | Active queries, jobs, deployments | Sự kiện nào bắt đầu growth? |

Đồng bộ timezone và timestamps giữa PostgreSQL, OS, cloud metrics và application logs để correlation chính xác.

## 25. Các lỗi thường gặp

| Triệu chứng/giả định | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Database size nhỏ nhưng disk đầy | WAL/log/temp/backup nằm ngoài relation size | Kiểm tra mọi mount và directory |
| pg_wal tăng dù traffic bình thường | Slot hoặc archive giữ segments | Kiểm tra restart_lsn, archiver và consumers |
| max_wal_size tăng nhưng disk vẫn đầy | Đây là soft limit; retention blockers vẫn giữ WAL | Xử lý slot/archive và capacity |
| Archive failed liên tục | Destination full, permissions hoặc network | Sửa archive path/service, xác nhận command exit 0 |
| Replica offline và WAL tăng | Physical slot giữ WAL | Khôi phục standby hoặc đánh giá reinitialize/drop slot |
| CDC connector dừng và WAL tăng | Logical slot inactive | Khôi phục consumer hoặc coordinated rebootstrap |
| VACUUM chạy nhưng disk không giảm | VACUUM thường giữ space để reuse | Hiểu khác biệt với VACUUM FULL/repack |
| VACUUM FULL báo hết disk | Cần copy mới cùng old relation | Mở rộng capacity và plan maintenance |
| Index rebuild làm disk tăng | Index cũ/mới cùng tồn tại | Dự trù peak space trước REINDEX |
| Temp files tăng | Sort/hash spill hoặc reporting workload | Query analysis, bounded work_mem/temp_file_limit |
| Log directory tăng không dừng | Rotation/retention sai hoặc verbose logging | Kiểm tra collector, rotation và log driver |
| Xóa log nhưng disk không giảm | Process còn mở file đã unlink | Reopen/rotate đúng cách, kiểm tra deleted-open files |
| df còn chỗ nhưng không tạo file được | Hết inode/quota | Kiểm tra df -i và quotas |
| Host còn chỗ nhưng PostgreSQL báo full | PVC/container quota hoặc mount khác đầy | Kiểm tra volume thực tế của process |
| Drop slot làm CDC/standby hỏng | Consumer vẫn cần continuity | Reinitialize/rebootstrap theo owner approval |
| Xóa WAL thủ công làm cluster không start | Crash recovery/archive chain bị phá | Restore từ backup/WAL hợp lệ |
| Archive cleanup làm PITR mất khả năng | Xóa WAL cần cho backup chain | Restore test và retention-aware cleanup |

## 26. Production incident runbook

**Bước 1 — Xác nhận mount.** Ghi filesystem, available bytes, inode usage, mount path và tốc độ tăng.

**Bước 2 — Map PostgreSQL paths.** Kiểm tra data_directory, tablespaces, pg_wal, log_directory, temp_tablespaces và archive destination.

**Bước 3 — Contain growth.** Pause/throttle workload hoặc job gây tăng dung lượng; giữ application traffic cần thiết nếu an toàn.

**Bước 4 — Bảo toàn recovery.** Không xóa WAL/data files. Xác định backup chain, archive status và replication slot owners.

**Bước 5 — Điều tra relations.** Query top databases, tables, indexes, TOAST và dead tuples.

**Bước 6 — Điều tra WAL.** Kiểm tra directory size, pg_stat_wal, slots, standby lag và archive failures.

**Bước 7 — Điều tra temporary files/logs.** Kiểm tra temp counters, active queries, log destination, rotation và external log driver.

**Bước 8 — Tăng capacity hoặc cleanup an toàn.** Ưu tiên volume expansion; cleanup chỉ file ngoài PGDATA đã xác nhận hết retention/không còn được sử dụng.

**Bước 9 — Khôi phục archiving/replication.** Sửa destination, credentials, consumer và theo dõi backlog.

**Bước 10 — Xác nhận PostgreSQL ổn định.** Kiểm tra writes, checkpoints, vacuum, archive, replication, logs và application errors.

**Bước 11 — Reclaim bloat sau incident.** Lên kế hoạch vacuum/repack/reindex khi đủ headroom và maintenance window.

**Bước 12 — Phòng ngừa tái diễn.** Thêm alerts theo nguồn, time-to-full, retention review và capacity forecast.

## 27. Recovery checklist khi disk đã đầy 100%

Khi volume đã cạn hoàn toàn, ưu tiên khôi phục khả năng ghi:

1. Ngăn workload gây growth tiếp tục.
2. Xác định chính xác mount chứa filesystem full.
3. Mở rộng volume hoặc giải phóng file ngoài PostgreSQL đã được xác minh.
4. Đảm bảo còn dung lượng cho WAL, checkpoints, logs và recovery.
5. Nếu archive destination đầy, khôi phục storage/permissions trước.
6. Nếu PostgreSQL đã dừng, đọc startup logs và khôi phục mounts.
7. Không xóa pg_wal, relation files hoặc archive chưa hết retention.
8. Khi service lên, kiểm tra archiver và replication slots.
9. Xác minh backup/PITR continuity.
10. Theo dõi disk usage và growth rate cho tới khi ổn định.

Nếu đã có file nội bộ bị xóa hoặc filesystem corruption, giữ nguyên volume/snapshot và chuyển sang recovery assessment thay vì tiếp tục thử cleanup.

## 28. Bài thực hành

Thực hiện trên PostgreSQL lab có filesystem/volume riêng. Không cố tình làm đầy production, không xóa file trong PGDATA và không xóa archive dùng cho backup thật.

### Bài 1 — Kiểm tra database size

Dùng pg_database_size() liệt kê databases lớn nhất và so sánh với filesystem usage.

### Bài 2 — Top relations

Dùng pg_total_relation_size() liệt kê 20 tables/indexes lớn nhất. So sánh table size với total size.

### Bài 3 — TOAST storage

Tạo table có text/jsonb values lớn. Kiểm tra TOAST relation và so sánh pg_table_size() với pg_relation_size().

### Bài 4 — Index footprint

Tạo nhiều indexes trên một table. Đo pg_indexes_size() và phân tích index nào chiếm phần lớn dung lượng.

### Bài 5 — Partition footprint

Tạo partitioned table với nhiều partitions. Liệt kê size từng child và tìm partition lớn nhất.

### Bài 6 — Dead tuples

Tạo workload UPDATE/DELETE lớn. Quan sát n_dead_tup, chạy VACUUM và so sánh size trước/sau.

### Bài 7 — VACUUM thường và VACUUM FULL

Trên lab có đủ disk, so sánh lock, runtime và relation size của hai thao tác. Ghi nhận vì sao VACUUM thường không nhất thiết thu nhỏ file.

### Bài 8 — pgstattuple

Cài pgstattuple trong lab, đo dead tuples/free space của một relation và so sánh với statistics estimates.

### Bài 9 — WAL generation

Chạy INSERT/UPDATE batches và lấy hai snapshots pg_stat_wal. Tính WAL bytes/sec.

### Bài 10 — pg_wal inventory

Dùng pg_ls_waldir() và OS du để so sánh file count/size. Xác định quyền cần thiết cho SQL function.

### Bài 11 — max_wal_size

Thay đổi workload/checkpoint settings trong lab. Quan sát vì sao pg_wal có thể vượt max_wal_size khi retention blockers tồn tại.

### Bài 12 — Physical replication slot

Tạo physical slot trong lab, giữ standby không consume WAL và quan sát retained WAL tăng. Khôi phục consumer và theo dõi behavior.

### Bài 13 — Inactive logical slot

Tạo logical slot, không consume changes và quan sát restart_lsn. Xác định retention risk và cleanup/rebootstrap plan.

### Bài 14 — Slot monitoring

Viết query report retained WAL estimate cho từng slot, active state, database và owner metadata.

### Bài 15 — Archive command

Bật archiving trong lab với archive path riêng. Xác nhận WAL file được archive và pg_stat_archiver tăng archived_count.

### Bài 16 — Archive failure

Làm archive command thất bại trong lab có kiểm soát. Quan sát failed_count, .ready status và pg_wal growth. Khôi phục command và theo dõi backlog.

### Bài 17 — Archive destination full

Dùng filesystem quota nhỏ trong lab hoặc mô phỏng lỗi ghi. Khôi phục capacity và kiểm tra archive retry.

### Bài 18 — Archive retention

Tạo base backup và WAL archive trong lab. Thử retention cleanup trên bản sao riêng và chứng minh backup còn PITR được.

### Bài 19 — Temporary file spill

Chạy sort/hash workload trên dataset đủ lớn với work_mem nhỏ. Quan sát temp_files/temp_bytes.

### Bài 20 — log_temp_files

Bật log_temp_files với threshold nhỏ trong lab. Chạy query spill và tìm log entry tương ứng.

### Bài 21 — temp_file_limit

Đặt temp_file_limit thấp cho session test. Chạy query tạo temp file lớn và quan sát query failure/cleanup.

### Bài 22 — work_mem concurrency

Chạy nhiều concurrent queries có sort/hash. Đo memory và temp usage; tìm cấu hình không gây memory exhaustion.

### Bài 23 — Log rotation

Cấu hình logging collector và log_rotation_size/age trong lab. Xác nhận file mới được tạo và retention hoạt động.

### Bài 24 — Log verbosity

So sánh log growth với log_statement/statement duration settings khác nhau. Thiết kế threshold cân bằng diagnostics và storage.

### Bài 25 — Deleted-open logs

Trên Linux lab, rotate/unlink file log trong khi process còn mở. Dùng lsof +L1 tìm file descriptor và thử reopen theo cơ chế service phù hợp.

### Bài 26 — Inode exhaustion

Tạo nhiều small files trong một filesystem test riêng để mô phỏng inode pressure. Phân biệt inode exhaustion với bytes exhaustion.

### Bài 27 — Tablespace monitoring

Tạo tablespace trên mount riêng, đặt table/index vào đó và query pg_tablespace_size() cùng OS usage.

### Bài 28 — Tablespace full

Dùng quota nhỏ trong lab để làm tablespace đầy. Xác định statement lỗi và recovery bằng cách mở rộng volume.

### Bài 29 — Long transaction và vacuum

Giữ transaction snapshot lâu, tạo UPDATE/DELETE và quan sát vacuum cleanup bị hạn chế. Kết thúc transaction và theo dõi vacuum.

### Bài 30 — REINDEX capacity

Tạo index lớn, đo dung lượng cần cho REINDEX thường và CONCURRENTLY trong lab. Xác định peak disk requirements.

### Bài 31 — Docker volume

Chạy PostgreSQL lab trong Docker volume có giới hạn. So sánh host free space, volume usage và container log usage.

### Bài 32 — Kubernetes PVC

Tạo workload test trên PVC, quan sát capacity/usage và thực hành volume expansion theo StorageClass hỗ trợ.

### Bài 33 — Time-to-full alert

Thu thập filesystem snapshots định kỳ và tính growth rate/time-to-full. Tạo alert test theo ngưỡng giả định.

### Bài 34 — Incident tabletop

Mô phỏng tình huống pg_wal tăng, archive destination đầy và một logical slot inactive. Viết thứ tự containment/recovery mà không drop slot mù quáng.

### Bài 35 — End-to-end recovery runbook

Tạo lab có table growth, WAL archiving và logs. Mô phỏng disk pressure, giữ evidence, mở rộng capacity, khôi phục archiving, xác minh replication và viết post-incident report.

## 29. Tổng kết

Những điểm cốt lõi khi xử lý **đầy đĩa do bảng, WAL, archive hoặc nhật ký**:

1. Xác định filesystem/mount thực sự đầy trước khi cleanup.
2. Database size không bao gồm mọi nguồn chiếm disk như WAL archive, logs, temp files, backup staging hoặc container logs.
3. Dùng pg_total_relation_size, pg_table_size và pg_indexes_size để phân tích table/index/TOAST footprint.
4. Dead tuples và bloat có thể làm relation tăng; VACUUM thường giữ space để reuse, còn VACUUM FULL/repack cần extra disk và lock.
5. pg_wal tăng có thể do workload, replication slots, archive failure hoặc retention requirements.
6. max_wal_size là soft limit, không phải hard cap; wal_keep_size và slot retention có semantics riêng.
7. Dùng pg_replication_slots, pg_stat_replication và pg_stat_archiver để tìm WAL consumers và archive blockers.
8. Chỉ drop replication slot sau khi xác định owner, recovery impact và kế hoạch rebootstrap.
9. Archive cleanup phải aware với base backups, PITR window và standby consumers.
10. Temporary files thường đến từ sort/hash spill; work_mem là per-operation budget nên tăng global setting có thể gây memory pressure.
11. Logs cần rotation/retention phù hợp; kiểm tra cả PostgreSQL collector và container/OS logging.
12. Kiểm tra inode, quota, tablespace và PVC, không chỉ bytes trên host.
13. Không xóa thủ công pg_wal, relation files hoặc archive chưa hết retention.
14. Khi disk full, ưu tiên containment và mở rộng capacity; cleanup relation/reindex/rewrite sau khi có headroom.
15. Sau recovery, xác minh archiving, replication, backup/PITR, application writes và growth rate.

Sự cố hết dung lượng là vấn đề quản lý nhiều storage lifecycles cùng lúc. Một runbook tốt nối filesystem metrics với PostgreSQL catalogs, WAL retention, archive health, query workload và backup policy. Khi xác định được nguồn tăng và consumer đang giữ file, có thể khôi phục dung lượng mà vẫn bảo toàn khả năng crash recovery, replication và PITR.

## 30. Tài liệu tham khảo PostgreSQL

- [Database Physical Storage](https://www.postgresql.org/docs/current/storage.html) — relation files, pages, forks và TOAST.
- [Database File Layout](https://www.postgresql.org/docs/current/storage-file-layout.html) — cấu trúc data directory.
- [Write-Ahead Logging](https://www.postgresql.org/docs/current/wal-intro.html) — WAL architecture.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — checkpoint, WAL size và archiving settings.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html) — archive_command, WAL archive và PITR.
- [Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS) — slot behavior và retained WAL.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publisher/subscriber and logical slot behavior.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity và statistics views.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ARCHIVER-VIEW) — archiver statistics.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html) — vacuum, index build và operation progress.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dead tuples, autovacuum và space reuse.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — VACUUM options và FULL behavior.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html) — relation storage locations.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html) — work_mem và temp_file_limit.
- [Logging Configuration](https://www.postgresql.org/docs/current/runtime-config-logging.html) — logging collector, rotation và log settings.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html) — tuple/free-space inspection extension.

Các liên kết /current/ trỏ tới tài liệu PostgreSQL hiện hành. Catalog fields, monitoring views, replication slot limits và configuration parameters có thể khác theo major version. Trước khi chạy recovery, xác nhận PostgreSQL version, storage topology, backup tool, WAL archive retention và các standby/CDC consumers đang phụ thuộc.
