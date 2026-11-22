# Đo dung lượng, tốc độ tăng dữ liệu và phần trống trong PostgreSQL

Theo dõi dung lượng PostgreSQL không chỉ là chạy một câu lệnh để biết database đang chiếm bao nhiêu gigabytes. Người vận hành cần biết **dữ liệu nào đang tăng, tăng nhanh đến mức nào, volume nào sắp hết chỗ và phần dung lượng trống đang nằm ở đâu**.

PostgreSQL cung cấp các hàm như pg_database_size, pg_total_relation_size, pg_table_size, pg_indexes_size và pg_tablespace_size để đo dung lượng ở các cấp khác nhau. Các statistics views giúp ước lượng hoạt động ghi, temporary files, dead tuples và WAL generation. Tuy nhiên, dung lượng trống của filesystem hoặc cloud volume phải được quan sát ở lớp hệ điều hành hoặc nhà cung cấp hạ tầng.

Một điểm dễ nhầm là “free space” có nhiều nghĩa. Một table có thể chứa các page còn chỗ để tái sử dụng, nhưng file relation vẫn chiếm nguyên số bytes trên disk. Filesystem có thể còn nhiều chỗ dù database có bloat lớn; ngược lại, một database nhỏ vẫn có thể nằm trên volume gần đầy do WAL, logs, backups hoặc files khác.

Bài học này hướng dẫn đo dung lượng database, table, index, TOAST, tablespace và WAL; xây lịch sử tăng trưởng; tính growth rate và thời gian dự kiến tới ngưỡng đầy; phân biệt reusable space với filesystem free space; theo dõi autovacuum, temporary files và replication slots; cuối cùng thiết kế dashboard, alerts và runbooks về capacity.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt dung lượng database, relation, table, index, tablespace và filesystem.
2. Dùng pg_database_size, pg_relation_size, pg_table_size, pg_indexes_size và pg_total_relation_size.
3. Đo dung lượng theo schema, table, index và partition.
4. Xác định ảnh hưởng của TOAST, dead tuples và bloat.
5. Đo dung lượng tablespace và ánh xạ tới storage volume.
6. Theo dõi pg_wal, archive backlog và WAL bị giữ bởi replication slots.
7. Đo temporary files và hoạt động ghi dữ liệu.
8. Lưu snapshot dung lượng theo thời gian và tính growth rate.
9. Dự báo thời điểm volume đạt ngưỡng capacity.
10. Phân biệt page-level free space, dead tuples, reusable space và filesystem free space.
11. Hiểu VACUUM, VACUUM FULL, TRUNCATE, DROP và REINDEX ảnh hưởng dung lượng thế nào.
12. Thiết kế cảnh báo theo dung lượng, tốc độ tăng và thời gian còn lại.
13. Điều tra disk growth bất thường và tránh các thao tác làm đầy disk.
14. Xây dashboard và runbook capacity management cho PostgreSQL.

## 2. Bốn lớp dung lượng cần theo dõi

Một báo cáo capacity nên tách ít nhất bốn lớp:

| Lớp | Câu hỏi | Công cụ chính |
| --- | --- | --- |
| Database/object | Database, table, index đang chiếm bao nhiêu? | PostgreSQL size functions |
| Tablespace | Dữ liệu đang nằm ở tablespace nào? | pg_tablespace_size, pg_tablespace |
| WAL/temporary | WAL và temporary files đang dùng bao nhiêu? | pg_ls_waldir, pg_stat_wal, pg_stat_database |
| Filesystem/volume | Volume còn bao nhiêu bytes/inodes? | OS tools, cloud metrics |

### 2.1. Database size không phải filesystem usage

pg_database_size đo dung lượng các files thuộc một database. Nó không phải phép đo toàn bộ volume chứa PostgreSQL. Volume còn có thể chứa:
- Các databases khác.
- WAL trong pg_wal.
- Tablespaces đặt trên cùng volume.
- PostgreSQL logs.
- Temporary files.
- Backup staging hoặc export files.
- Files của hệ điều hành và các dịch vụ khác.

### 2.2. Filesystem free space là giới hạn vận hành thực tế

PostgreSQL có thể cần thêm dung lượng cho WAL, temporary files, index builds, VACUUM rewrites hoặc bulk loads. Khi volume đầy, writes và maintenance có thể thất bại. Vì vậy cần đo free bytes ở từng mount point, không chỉ nhìn database size.

### 2.3. Free space bên trong table khác free space của volume

VACUUM thông thường có thể làm các tuple slots/dead tuple space được tái sử dụng trong relation. File relation thường không nhỏ lại tương ứng và filesystem không tự nhận lại toàn bộ bytes đó.

### 2.4. Dung lượng backup là một failure domain khác

Backup repository hoặc object storage thường nằm ngoài database volume. Đưa backup usage vào capacity dashboard riêng, tránh cộng nhầm hoặc bỏ qua quota/retention của nơi lưu backup.

## 3. Đo dung lượng database

Hàm pg_database_size trả về số bytes database đang sử dụng.

~~~sql
SELECT
    datname,
    pg_database_size(oid) AS bytes,
    pg_size_pretty(pg_database_size(oid)) AS pretty_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(oid) DESC;
~~~

### 3.1. Giữ giá trị bytes để tính toán

pg_size_pretty chỉ phục vụ hiển thị. Lưu giá trị bigint bytes vào monitoring store để tính delta và growth rate. Không parse chuỗi hiển thị như 12 GB để làm toán.

### 3.2. Đo database hiện tại

~~~sql
SELECT
    current_database() AS database_name,
    pg_database_size(current_database()) AS bytes,
    pg_size_pretty(pg_database_size(current_database())) AS size;
~~~

### 3.3. Quyền truy cập

Một số size functions yêu cầu quyền phù hợp để xem đối tượng/database khác. Dùng role monitoring có quyền tối thiểu cần thiết và xác minh hành vi trên PostgreSQL version đang chạy.

### 3.4. Database có thể giảm kích thước

Database size có thể tăng hoặc giảm khi tạo/drop tables, truncate, rewrite relation, vacuum full hoặc thay đổi dữ liệu. Không giả định growth rate luôn dương.

### 3.5. Không cộng nhầm database và tablespace

pg_database_size đo database; pg_tablespace_size đo tổng dung lượng trong tablespace. Vì tablespace chứa objects của databases, cộng tất cả database sizes với tablespace sizes có thể đếm trùng.

## 4. Đo dung lượng table, index và TOAST

Các hàm size của PostgreSQL đo các phần khác nhau của một relation.

| Hàm | Phần dung lượng |
| --- | --- |
| pg_relation_size(relation) | Mặc định main fork của relation |
| pg_table_size(relation) | Table storage, gồm TOAST và các forks liên quan; không gồm indexes |
| pg_indexes_size(relation) | Tổng dung lượng indexes của table |
| pg_total_relation_size(relation) | Table storage cộng indexes |

### 4.1. Xem table lớn nhất

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_relation_size(relid) AS main_bytes,
    pg_table_size(relid) AS table_bytes,
    pg_indexes_size(relid) AS index_bytes,
    pg_total_relation_size(relid) AS total_bytes,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
~~~

pg_stat_user_tables có một dòng cho mỗi user table theo semantics của version; với partitioned tables, hãy xem riêng parent và các partitions để hiểu dung lượng vật lý.

### 4.2. Phân rã một table

~~~sql
SELECT
    'app.orders'::regclass AS relation,
    pg_size_pretty(pg_relation_size('app.orders')) AS main_fork,
    pg_size_pretty(pg_table_size('app.orders')) AS table_including_toast,
    pg_size_pretty(pg_indexes_size('app.orders')) AS indexes,
    pg_size_pretty(pg_total_relation_size('app.orders')) AS total;
~~~

### 4.3. Vì sao table_bytes và main_bytes khác nhau?

pg_table_size bao gồm TOAST storage và các forks như free space map/visibility map. pg_relation_size mặc định đo main fork, do đó có thể nhỏ hơn đáng kể.

### 4.4. TOAST

PostgreSQL có thể lưu các giá trị lớn như text, bytea hoặc các giá trị varlena khác trong TOAST relation. Một table có row width lớn có thể có phần TOAST đáng kể. pg_table_size và pg_total_relation_size tính đến phần này.

### 4.5. Indexes

Indexes có thể chiếm dung lượng bằng hoặc lớn hơn table heap. Một table có nhiều indexes, key rộng hoặc churn cao có thể tạo storage overhead lớn. pg_indexes_size giúp nhìn phần index riêng.

### 4.6. Table size không phải số lượng dữ liệu nghiệp vụ

Hai tables có cùng row count có thể có size rất khác do row width, TOAST, fillfactor, indexes và bloat. Dùng bytes để lập capacity, row counts để hiểu workload/data volume.

## 5. Xếp hạng relation theo schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned table'
        WHEN 'm' THEN 'materialized view'
        WHEN 'i' THEN 'index'
        ELSE c.relkind::text
    END AS relation_type,
    pg_total_relation_size(c.oid) AS total_bytes,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY total_bytes DESC;
~~~

### 5.1. Vì sao lọc relkind?

pg_class chứa nhiều loại relations, bao gồm tables, indexes, sequences, views và partitioned relations. Query trên chọn các loại có ý nghĩa như table/materialized view/partitioned table. Điều chỉnh filter nếu cần inventory loại object khác.

### 5.2. Partitioned parent

Partitioned parent thường không lưu rows trực tiếp nên size của parent có thể bằng 0 hoặc rất nhỏ. Dung lượng thực tế nằm ở các partitions. Báo cáo theo từng partition hoặc tổng hợp partition tree theo parent để tránh người đọc hiểu nhầm.

### 5.3. Indexes trong báo cáo

pg_total_relation_size của table đã bao gồm indexes. Nếu cộng thêm các index rows từ pg_class lần nữa, sẽ đếm trùng. Chọn một cách trình bày: table totals hoặc heap/index breakdown.

### 5.4. System objects

System catalogs, TOAST relations và objects nội bộ có thể không xuất hiện trong báo cáo user-table đơn giản. Khi đối chiếu với database size, cần tính cả objects không thuộc schema ứng dụng.

## 6. Đo dung lượng từng index

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    pg_relation_size(
        format('%I.%I', schemaname, indexname)::regclass
    ) AS index_bytes,
    pg_size_pretty(
        pg_relation_size(
            format('%I.%I', schemaname, indexname)::regclass
        )
    ) AS index_size,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_relation_size(
    format('%I.%I', schemaname, indexname)::regclass
) DESC
LIMIT 50;
~~~

### 6.1. Index lớn không mặc nhiên là index thừa

Một index lớn có thể phục vụ query quan trọng. Trước khi drop, kiểm tra usage statistics, query plans, constraints và application workload.

### 6.2. pg_stat_user_indexes

View này có các counters như idx_scan, idx_tup_read và idx_tup_fetch. Counters tích lũy từ stats reset/startup, không chứng minh một index chưa từng được dùng nếu chưa biết khoảng thời gian quan sát.

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan;
~~~

### 6.3. Unique indexes và constraints

Một index có thể enforce PRIMARY KEY hoặc UNIQUE constraint. Không drop index chỉ vì idx_scan thấp; index constraint có thể cần dù application query không dùng nó trực tiếp.

### 6.4. Reindex cần extra capacity

REINDEX tạo lại index và thường cần dung lượng bổ sung trong quá trình thực hiện. REINDEX CONCURRENTLY có behavior/overhead riêng. Tính peak storage trước khi chạy trên volume gần đầy.

## 7. Đo dung lượng theo tablespace

Tablespace cho phép đặt relation files trên các filesystem/volume khác nhau.

~~~sql
SELECT
    spcname AS tablespace_name,
    pg_tablespace_location(oid) AS location,
    pg_tablespace_size(oid) AS bytes,
    pg_size_pretty(pg_tablespace_size(oid)) AS size
FROM pg_tablespace
ORDER BY pg_tablespace_size(oid) DESC;
~~~

### 7.1. pg_default và pg_global

pg_default là tablespace mặc định cho database objects. pg_global chứa shared system catalogs. Vị trí của default/global tablespaces có semantics riêng; pg_tablespace_location có thể trả chuỗi rỗng cho các tablespaces mặc định.

### 7.2. Tablespace không phải mount point

Một tablespace có thể nằm trong một directory trên filesystem. Nhiều tablespaces có thể cùng nằm trên một volume, hoặc mỗi tablespace có volume riêng. Cần map location tới actual mount/volume bằng công cụ hệ điều hành.

### 7.3. Không cộng tablespace size với database size

Tablespace size là góc nhìn khác của cùng các relation files. Không cộng hai loại số đo để ra tổng disk usage.

### 7.4. Tablespace capacity

Nếu tablespace nằm trên volume riêng, volume đó có thể đầy dù PGDATA còn nhiều chỗ. Theo dõi free bytes riêng cho từng location.

### 7.5. Di chuyển relation sang tablespace

ALTER TABLE ... SET TABLESPACE hoặc ALTER INDEX ... SET TABLESPACE có thể cần copy relation và extra disk trong quá trình thực hiện. Đánh giá lock, I/O, free capacity và rollback trước khi chuyển.

## 8. Đo filesystem và volume free space

PostgreSQL SQL views không thay thế được việc đo filesystem. Dùng OS/host monitoring để biết free bytes và inode availability trên từng mount.

Ví dụ trên Linux:

~~~bash
df -h
df -i
~~~

Để xem dung lượng theo thư mục:

~~~bash
du -sh /var/lib/postgresql
du -sh /var/lib/postgresql/*
~~~

Đường dẫn phụ thuộc package, version, container layout và deployment. Không chạy du quét liên tục trên data directory lớn nếu gây I/O overhead.

### 8.1. Các mount cần theo dõi

- PGDATA.
- pg_wal nếu đặt riêng.
- Mỗi tablespace location.
- PostgreSQL logs.
- Temporary/staging directories.
- WAL archive local spool nếu có.
- Backup staging.
- Filesystem chứa container writable layer nếu dùng container.

### 8.2. Bytes và inodes

Một volume có thể còn bytes nhưng hết inodes do có quá nhiều files nhỏ. Theo dõi cả df -h và df -i.

### 8.3. Filesystem reserved blocks

Một số filesystems giữ reserved blocks cho privileged processes. Giá trị available có thể khác với tổng free blocks. Alert theo available space mà PostgreSQL process thực sự có thể dùng.

### 8.4. Cloud-managed storage

Với managed PostgreSQL, dùng provider metrics cho allocated storage, used storage, free storage, autoscaling/quota và storage latency. Một số dịch vụ không cho truy cập OS shell; không giả định pg_ls_waldir hoặc df có thể dùng được.

### 8.5. Không lấy database size làm phần trăm volume usage

Ví dụ database dùng 500 GB nhưng volume 1 TB còn chứa WAL, logs, temp và nhiều databases. Phần trăm database size/volume size không phải phần trăm disk used. Dùng metric filesystem/provider trực tiếp.

## 9. Dung lượng WAL và pg_wal

WAL có thể chiếm lượng disk lớn khi archive bị lỗi, standby lag hoặc replication slot giữ segment.

### 9.1. Xem dung lượng WAL directory

Trên PostgreSQL versions có pg_ls_waldir và role có quyền phù hợp:

~~~sql
SELECT
    count(*) AS file_count,
    sum(size) AS total_bytes,
    pg_size_pretty(sum(size)::bigint) AS total_size
FROM pg_ls_waldir();
~~~

Function và quyền truy cập phụ thuộc version. Không cấp pg_read_server_files hoặc superuser cho dashboard nếu không cần; ưu tiên host exporter/monitoring integration khi phù hợp.

### 9.2. WAL statistics

Trên các phiên bản có pg_stat_wal:

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
~~~

wal_bytes là counter tích lũy. Lấy delta giữa hai snapshots và chia cho thời gian để tính WAL generation rate. View này có từ PostgreSQL 14; kiểm tra version trước khi dùng.

### 9.3. WAL archive

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Archive failures có thể làm WAL backlog tăng. Một archive command lỗi liên tục có thể khiến pg_wal không được recycle như mong muốn.

### 9.4. Replication slots giữ WAL

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
        WHEN restart_lsn IS NOT NULL
        THEN pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
    END AS wal_distance_bytes
FROM pg_replication_slots
ORDER BY slot_type, slot_name;
~~~

wal_distance_bytes là khoảng cách LSN ước lượng, không phải dung lượng độc quyền được slot đó chiếm. Nhiều slots có thể cùng yêu cầu một đoạn WAL.

### 9.5. Inactive slot

Một slot inactive vẫn có thể giữ WAL. Không drop slot chỉ để giải phóng disk trước khi xác định consumer owner và khả năng resync.

### 9.6. max_slot_wal_keep_size

Setting này có thể giới hạn WAL được giữ bởi slots ở các versions hỗ trợ. Nếu vượt giới hạn, consumer có thể mất khả năng tiếp tục từ vị trí cũ và phải resynchronize. Cân bằng disk safety với recovery requirements.

### 9.7. Không xóa WAL files thủ công

Không xóa hoặc đổi tên files trong pg_wal để giải phóng disk. Dùng archive/slot troubleshooting và các thủ tục PostgreSQL được hỗ trợ.

## 10. Temporary files và temporary usage

Query sort/hash có thể spill ra temporary files khi memory không đủ hoặc workload lớn.

### 10.1. Thống kê theo database

~~~sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset,
    pg_size_pretty(temp_bytes) AS temp_written_since_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

temp_bytes là lượng dữ liệu đã ghi vào temporary files kể từ stats reset, không phải số bytes temporary files đang còn tồn tại trên disk.

### 10.2. Tính tốc độ temporary writes

Lưu hai snapshots của temp_bytes, lấy delta và chia elapsed seconds. Nếu stats_reset thay đổi giữa hai samples, không tính rate qua khoảng đó.

### 10.3. Logging temp files

Có thể dùng log_temp_files để ghi nhận temporary files vượt ngưỡng. Chọn threshold phù hợp để không tạo quá nhiều logs.

### 10.4. Query-level insight

pg_stat_statements có thể cung cấp temp_blks_read và temp_blks_written theo query entry ở versions hỗ trợ. Dùng để tìm query tạo temporary I/O nhiều.

### 10.5. Temp không chỉ do work_mem

Sort/hash spills, materialization, temporary tables và một số operations khác có thể tạo temp files. Điều tra query patterns và workload thay vì chỉ tăng work_mem.

## 11. Tốc độ tăng dung lượng

Một số đo dung lượng tại một thời điểm chỉ cho biết trạng thái hiện tại. Để lập kế hoạch capacity, cần lưu snapshots theo thời gian.

### 11.1. Công thức growth rate

Nếu dung lượng tại thời điểm trước là S1, tại thời điểm sau là S2, khoảng thời gian là delta t giây:

\[
\text{growth bytes/sec} = \frac{S_2-S_1}{\Delta t}
\]

Đổi sang bytes/day:

\[
\text{growth bytes/day} = \text{growth bytes/sec} \times 86400
\]

Đổi sang GiB/day:

\[
\text{GiB/day} = \frac{\text{growth bytes/day}}{1024^3}
\]

### 11.2. Tăng trưởng có thể âm

DROP, TRUNCATE, VACUUM FULL hoặc rewrite có thể làm size giảm. Giữ delta âm trong history để hiểu biến động; khi forecast, dùng rolling average/percentile phù hợp thay vì giả định mọi sample tăng.

### 11.3. Lấy mẫu thường xuyên đến mức nào?

- Hệ thống ổn định: snapshots mỗi 15–60 phút hoặc hàng ngày tùy yêu cầu.
- Hệ thống tăng nhanh: sampling mỗi 5–15 phút.
- Incident capacity: sampling dày hơn trong thời gian ngắn.
- Filesystem metrics: thường có thể lấy thường xuyên hơn database relation inventory.

Tần suất cần cân bằng với overhead của các size functions và số lượng relations.

### 11.4. Snapshot không phải transactionally consistent toàn cluster

Một query đọc sizes của nhiều databases/relations có thể không phản ánh cùng một instant tuyệt đối nếu files thay đổi trong lúc lấy mẫu. Với capacity planning, điều này thường chấp nhận được; với forensic validation cần phương pháp khác.

## 12. Lưu snapshot dung lượng

Nên gửi snapshots tới monitoring system hoặc metrics store bên ngoài database đang đo. Nếu lưu trong chính cluster, tính đến overhead và tránh để bảng metrics tự làm lệch phép đo.

Một schema minh họa:

~~~sql
CREATE SCHEMA IF NOT EXISTS monitoring;

CREATE TABLE monitoring.database_size_samples (
    sampled_at timestamptz NOT NULL,
    database_name name NOT NULL,
    size_bytes bigint NOT NULL,
    PRIMARY KEY (sampled_at, database_name)
);
~~~

Lưu một sample:

~~~sql
INSERT INTO monitoring.database_size_samples (
    sampled_at,
    database_name,
    size_bytes
)
SELECT
    clock_timestamp(),
    datname,
    pg_database_size(oid)
FROM pg_database
WHERE datallowconn;
~~~

### 12.1. Giữ snapshot filesystem riêng

Database size và filesystem free bytes là hai metrics khác nhau. Lưu filesystem samples từ host/provider exporter với labels cho mount point, volume ID và host.

### 12.2. Snapshot relation

Có thể lưu table/index sizes theo database, schema, relation và partition. Dùng tên qualified ổn định và metadata object identity phù hợp; OIDs có thể thay đổi sau dump/restore hoặc object recreation.

### 12.3. Retention

Không giữ mọi snapshot raw mãi mãi. Giữ raw samples đủ cho incident analysis và roll up thành hourly/daily aggregates theo policy.

### 12.4. Stats reset

Với counters như temp_bytes, wal_bytes hoặc tuple activity, lưu stats_reset cùng sample. Nếu reset timestamp đổi, đánh dấu counter series bắt đầu lại.

## 13. Tính growth rate từ snapshots

~~~sql
WITH ordered AS (
    SELECT
        database_name,
        sampled_at,
        size_bytes,
        lag(sampled_at) OVER (
            PARTITION BY database_name
            ORDER BY sampled_at
        ) AS previous_time,
        lag(size_bytes) OVER (
            PARTITION BY database_name
            ORDER BY sampled_at
        ) AS previous_bytes
    FROM monitoring.database_size_samples
),
rates AS (
    SELECT
        database_name,
        sampled_at,
        size_bytes,
        size_bytes - previous_bytes AS delta_bytes,
        extract(epoch FROM sampled_at - previous_time) AS elapsed_seconds
    FROM ordered
    WHERE previous_time IS NOT NULL
)
SELECT
    database_name,
    sampled_at,
    delta_bytes,
    round((delta_bytes / NULLIF(elapsed_seconds, 0))::numeric, 2)
        AS bytes_per_second,
    round((
        delta_bytes * 86400.0
        / NULLIF(elapsed_seconds, 0)
        / 1024 / 1024 / 1024
    )::numeric, 3) AS gib_per_day
FROM rates
ORDER BY sampled_at DESC, database_name;
~~~

### 13.1. Kiểm tra khoảng thời gian

Nếu samples cách nhau rất xa hoặc gần như trùng timestamp, rate có thể gây hiểu nhầm. Dùng NULLIF để tránh chia cho zero và loại bỏ samples lỗi.

### 13.2. Smoothing

Một sample spike có thể đến từ bulk load hoặc maintenance. Dùng moving average, median hoặc percentile trong cửa sổ đủ dài để lập forecast.

### 13.3. Phân biệt growth với churn

Database có thể ghi/xóa nhiều nhưng net size ít thay đổi. Growth rate đo thay đổi net storage; WAL generation/temp writes đo workload churn. Theo dõi cả hai để dự đoán capacity và I/O.

## 14. Dự báo thời gian tới ngưỡng đầy

Giả sử:
- Free bytes hiện tại là F.
- Growth rate dương trung bình là G bytes/day.
- Dự báo đơn giản:

\[
\text{days to full} = \frac{F}{G}
\]

Ví dụ volume còn 200 GiB và tăng trung bình 10 GiB/day thì ước tính còn 20 ngày tới 0 free bytes. Trên production, không nên đợi tới 0; đặt capacity threshold có headroom.

### 14.1. Forecast tới ngưỡng vận hành

Nếu muốn giữ lại reserve R:

\[
\text{days to reserve} = \frac{F-R}{G}
\]

Chỉ dùng khi G dương và F lớn hơn R.

### 14.2. Tốc độ tăng không cố định

Growth có thể thay đổi theo ngày/giờ cao điểm, mùa vụ, batch jobs, bulk imports, index builds, retention/cleanup jobs, WAL archive failures và replication consumer outage.

Dùng peak/percentile growth và kịch bản stress, không chỉ average dài hạn.

### 14.3. Capacity forecast theo nhiều lớp

Forecast riêng:
- Database/relation growth.
- WAL peak and retention.
- Temporary file peak.
- Index/rewrite overhead.
- Logs.
- Backup staging.
- Filesystem reserve.

### 14.4. Cloud autoscaling

Nếu storage auto-grow, theo dõi allocated capacity, max quota, growth event, billing và thời gian provision. Autoscaling không loại bỏ nguy cơ quota ceiling hoặc I/O throttling.

## 15. Free space bên trong PostgreSQL

Cần phân biệt các khái niệm:

| Khái niệm | Ý nghĩa | Có trả bytes cho filesystem ngay không? |
| --- | --- | --- |
| Free space trong page | Chỗ trống trong một data page | Không |
| Dead tuples | Row versions không còn cần cho snapshot | Chưa |
| Space reusable sau VACUUM | Có thể dùng lại cho inserts/updates | Thường không |
| Bloat | Dung lượng dư/không hiệu quả so với dữ liệu hữu ích | Không tự động |
| Filesystem free space | Bytes volume còn cấp phát được | Là capacity thực tế |
| Space được giải phóng bởi DROP/TRUNCATE | Relation files bị loại bỏ/truncate | Thường có |

### 15.1. Dead tuples

UPDATE/DELETE tạo dead tuple versions. Vacuum xác định tuples có thể dọn khi không còn snapshot cần chúng. Dead tuples không đồng nghĩa file table sẽ nhỏ đi ngay.

### 15.2. Free space map

FSM lưu thông tin ước lượng về free space trong relation pages để PostgreSQL tìm chỗ tái sử dụng. FSM không phải bản đồ filesystem free bytes.

### 15.3. Visibility map

Visibility map theo dõi page có thể được coi là all-visible/all-frozen trong một số operations. Nó cũng là metadata nội bộ, không phải filesystem capacity.

### 15.4. Fillfactor

Fillfactor thấp có thể giữ chỗ trong pages để hỗ trợ UPDATE/HOT update hoặc giảm page splits trong một số workload. Đó là trade-off hiệu năng và storage; không nên coi phần trống đó là bloat tự động.

## 16. Theo dõi dead tuples và vacuum

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_pct,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

### 16.1. Đây là estimates

n_live_tup và n_dead_tup là thống kê ước lượng. Chúng hữu ích để tìm table đáng điều tra, không phải phép đo byte bloat chính xác.

### 16.2. Autovacuum

Autovacuum dọn dead tuples và cập nhật visibility/frozen metadata. Nếu autovacuum không theo kịp write rate, dead tuples và bloat có thể tăng.

### 16.3. Transaction lâu

Transactions/snapshots lâu có thể ngăn vacuum loại bỏ tuples cũ. Kết hợp pg_stat_activity, backend_xmin và replication slots để tìm horizon bị giữ.

### 16.4. Vacuum không shrink file thông thường

VACUUM thông thường chủ yếu làm space có thể tái sử dụng bên trong relation. Chỉ trong một số điều kiện có thể truncate các empty pages ở cuối file. Đừng dự đoán filesystem free space sẽ tăng bằng toàn bộ dead tuple bytes sau VACUUM.

### 16.5. Analyze

ANALYZE cập nhật statistics cho planner; nó không phải công cụ giải phóng dung lượng.

## 17. Đo bloat và free space trong relation

Các extension như pgstattuple và pg_freespacemap cung cấp góc nhìn sâu hơn, nhưng cần cài đặt, quyền và đánh giá overhead.

### 17.1. pgstattuple

pgstattuple có thể báo tuple count/length, dead tuple count/length và free space bytes/percentage.

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstattuple('app.orders');
~~~

### 17.2. pgstattuple_approx

Với relation lớn, pgstattuple_approx có thể ước lượng nhanh hơn bằng cách tận dụng visibility map và các thông tin có sẵn. Kết quả là approximate; đọc tài liệu extension/version.

~~~sql
SELECT *
FROM pgstattuple_approx('app.orders');
~~~

### 17.3. Chi phí

pgstattuple có thể đọc nhiều pages và tạo I/O đáng kể. Không chạy đồng loạt trên mọi table lớn trong giờ cao điểm nếu chưa đánh giá.

### 17.4. pg_freespacemap

Extension pg_freespacemap cho phép xem thông tin free space map theo pages:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_freespacemap;

SELECT *
FROM pg_freespace('app.orders'::regclass)
LIMIT 20;
~~~

Kết quả là free space theo page theo FSM; không phải tổng bytes còn trống của filesystem.

### 17.5. Không coi free_percent là disk free

pgstattuple free_percent mô tả free space bên trong relation pages. Filesystem có thể vẫn không nhận lại bytes nếu relation file chưa shrink.

## 18. VACUUM, VACUUM FULL và giải phóng disk

### 18.1. VACUUM

~~~sql
VACUUM (ANALYZE) app.orders;
~~~

VACUUM thông thường dọn dead tuples có thể reclaim và làm space có thể tái sử dụng. Nó thường không cần exclusive lock trên table và không rewrite toàn relation.

### 18.2. VACUUM FULL

~~~sql
VACUUM (FULL, ANALYZE) app.orders;
~~~

VACUUM FULL rewrite table để thu hồi space và trả file nhỏ hơn cho filesystem. Nó cần ACCESS EXCLUSIVE lock và extra disk để tạo bản rewrite. Không chạy trên table lớn trong production nếu chưa có maintenance window và capacity plan.

### 18.3. TRUNCATE

TRUNCATE loại bỏ toàn bộ rows và thường giải phóng storage của table về filesystem, nhưng cần lock mạnh và có transaction/foreign-key semantics riêng. Xác minh cascade và application impact.

### 18.4. DROP

DROP TABLE/DATABASE xóa objects và relation files tương ứng. Đây là thao tác destructive, cần backup/approval và kiểm tra dependencies.

### 18.5. CLUSTER

CLUSTER rewrite table theo index order, có thể cải thiện locality nhưng cần extra space và lock mạnh trong quá trình thực hiện. Nó không phải thao tác capacity cleanup thường xuyên.

### 18.6. REINDEX

REINDEX xây lại index. Nó có thể thu hồi index bloat nhưng cần storage headroom; phương thức concurrent có trade-offs riêng.

## 19. WAL retention và disk growth bất thường

Một database có thể không tăng nhiều nhưng pg_wal tăng nhanh.

### 19.1. Archive command lỗi

Nếu archive_command thất bại, PostgreSQL giữ WAL cần archive và retry. Kiểm tra pg_stat_archiver, server logs, archive destination capacity và permissions.

### 19.2. Standby lag

Standby không nhận/replay kịp có thể giữ WAL qua replication slot hoặc làm cần nhiều WAL hơn. Theo dõi state, sent/write/flush/replay LSN và slot restart_lsn.

### 19.3. Logical slot inactive

CDC connector hoặc subscriber ngừng hoạt động có thể giữ WAL và catalog history. Xác định consumer trước khi xử lý slot.

### 19.4. Long-running transaction

Transaction/snapshot lâu có thể giữ tuple versions và ảnh hưởng vacuum. Kiểm tra pg_stat_activity và xmin horizons.

### 19.5. Không nhầm WAL generation với WAL retained

wal_bytes tăng cho biết WAL được tạo ra trong khoảng thời gian. pg_wal directory size cho biết files đang tồn tại trên disk. Hai metric có liên quan nhưng không giống nhau.

## 20. Temporary files và disk pressure

Temporary files có thể làm filesystem đầy ngay cả khi database relation sizes ổn định.

### 20.1. Nguồn phát sinh

- Sort spill.
- Hash aggregate/join spill.
- Materialization.
- Temporary tables.
- Index builds.
- Một số maintenance operations.
- Query concurrency cao.

### 20.2. Theo dõi temp_bytes

Dùng pg_stat_database.temp_bytes để tính tốc độ temporary writes qua snapshots. Kết hợp log_temp_files và query-level stats để tìm nguồn.

### 20.3. Temp tablespaces

Temporary files có thể nằm trong database default tablespace hoặc temp_tablespaces được cấu hình. Kiểm tra vị trí storage thực tế.

### 20.4. work_mem không phải memory limit toàn server

work_mem có thể được dùng cho nhiều sort/hash nodes trên mỗi query và nhiều concurrent sessions. Tăng work_mem để tránh temp spills có thể làm memory consumption tăng mạnh.

## 21. Dung lượng theo database và schema

PostgreSQL không có một built-in function đơn giản cho tổng size schema. Có thể tổng hợp relation sizes theo schema:

~~~sql
SELECT
    n.nspname AS schema_name,
    sum(pg_total_relation_size(c.oid)) AS bytes,
    pg_size_pretty(sum(pg_total_relation_size(c.oid))::bigint) AS size
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY n.nspname
ORDER BY bytes DESC;
~~~

### 21.1. Scope của schema query

Query trên cộng physical sizes của tables/materialized views trong schema, bao gồm indexes và TOAST qua pg_total_relation_size. Partitioned tables cần tính partitions và tránh đếm trùng khi custom query mở rộng sang parent/child mapping.

### 21.2. Không nhất thiết khớp pg_database_size

Database size còn có catalog, sequences, toast/index relations, temporary/per-database objects và các objects không nằm trong filter. Schema aggregate là breakdown, không phải tổng thay thế.

### 21.3. Schema có nhiều object nhỏ

Số lượng relations lớn có thể tạo overhead catalog và filesystem metadata. Theo dõi cả object count và total bytes.

## 22. Dung lượng theo partition

Với partitioned table, nên báo cáo dung lượng theo từng partition để tìm partition tăng nhanh hoặc phân bổ lệch.

~~~sql
SELECT
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    child_ns.nspname AS partition_schema,
    child.relname AS partition_name,
    pg_total_relation_size(child.oid) AS bytes,
    pg_size_pretty(pg_total_relation_size(child.oid)) AS size
FROM pg_inherits AS inh
JOIN pg_class AS parent
  ON parent.oid = inh.inhparent
JOIN pg_namespace AS parent_ns
  ON parent_ns.oid = parent.relnamespace
JOIN pg_class AS child
  ON child.oid = inh.inhrelid
JOIN pg_namespace AS child_ns
  ON child_ns.oid = child.relnamespace
ORDER BY bytes DESC;
~~~

Query trên liệt kê quan hệ cha-con trực tiếp. Partitioning nhiều cấp cần recursive traversal để gom toàn bộ descendants.

### 22.1. Partition skew

Một số partitions có thể lớn bất thường do key distribution, retention policy hoặc routing bug. Theo dõi min/max partition bounds cùng size.

### 22.2. Retention

Dropping/detaching old partitions có thể giải phóng storage nhanh hơn DELETE từng row, nhưng phải xác minh retention, foreign keys, publication/replication và application queries.

### 22.3. Future partitions

Tạo partitions trước thời điểm cần dùng và alert nếu partition tương lai chưa tồn tại. Một default partition có thể tăng nhanh khi partition routing không như dự kiến.

## 23. Capacity planning cho index build và maintenance

Đừng chỉ dự báo steady-state database size. Các thao tác maintenance có thể cần peak free space.

### 23.1. Index build

CREATE INDEX cần ghi index mới. Trong lúc build, index cũ/table vẫn tồn tại. REINDEX có thể cần thêm space cho bản mới; concurrent mode có behavior và thời gian khác.

### 23.2. VACUUM FULL/CLUSTER

Rewrite table cần đủ chỗ cho relation mới trong khi file cũ còn tồn tại. Nếu thiếu space, operation có thể thất bại hoặc làm workload bị ảnh hưởng.

### 23.3. pg_repack

Nếu dùng extension/tool rewrite online, tính thêm disk cho shadow table/index và thời gian giữ old relation. Tool có prerequisites và lock behavior riêng.

### 23.4. Bulk load

Import lớn tạo table/index growth và WAL. Tính cả temporary files, WAL archive và replication backlog.

### 23.5. Safety margin

Giữ headroom theo peak workload và thời gian cần để tăng volume/di chuyển dữ liệu. Không đặt ngưỡng dựa trên một con số phần trăm chung cho mọi deployment.

## 24. Tính growth theo relation

Có thể lưu snapshot theo schema/table:

~~~sql
CREATE TABLE monitoring.relation_size_samples (
    sampled_at timestamptz NOT NULL,
    schema_name name NOT NULL,
    relation_name name NOT NULL,
    total_bytes bigint NOT NULL,
    table_bytes bigint NOT NULL,
    index_bytes bigint NOT NULL,
    PRIMARY KEY (sampled_at, schema_name, relation_name)
);
~~~

Lấy sample:

~~~sql
INSERT INTO monitoring.relation_size_samples (
    sampled_at,
    schema_name,
    relation_name,
    total_bytes,
    table_bytes,
    index_bytes
)
SELECT
    clock_timestamp(),
    n.nspname,
    c.relname,
    pg_total_relation_size(c.oid),
    pg_table_size(c.oid),
    pg_indexes_size(c.oid)
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema');
~~~

### 24.1. Relation rename/drop/recreate

Tên relation có thể đổi hoặc được tái sử dụng. Với lịch sử dài, thêm database identity, relation OID, relfilenode hoặc metadata về object lifecycle; không coi schema/name luôn là một object vĩnh viễn.

### 24.2. Partition samples

Lưu partitions riêng và có mapping tới parent. Khi partition detach/drop, ghi nhận sự kiện để giải thích size giảm.

### 24.3. Không lấy size quá thường xuyên

Một cluster có hàng trăm nghìn relations có thể tốn thời gian khi gọi size functions cho tất cả. Chạy inventory đầy đủ theo lịch thưa hơn và dùng OS/provider metrics cho high-frequency capacity.

## 25. Dự báo và alerting

Một dashboard capacity tốt cần cảnh báo trước khi disk hết chỗ.

### 25.1. Absolute threshold

Ví dụ:
- Warning khi free bytes dưới reserve đã định.
- Critical khi free bytes dưới mức tối thiểu cần cho WAL/checkpoint/maintenance.
- Alert riêng cho từng tablespace volume.

### 25.2. Percentage threshold

Dùng phần trăm used/free kết hợp absolute bytes. Volume 95% used có thể nguy hiểm, nhưng 5% của volume 10 TB khác 5% của volume 20 GB.

### 25.3. Growth rate threshold

Alert khi growth bytes/day hoặc WAL bytes/sec tăng đột biến so với baseline.

### 25.4. Time-to-full

Dự báo số ngày tới reserve threshold bằng rolling growth rate. Alert khi time-to-full nhỏ hơn lead time cần để provision storage hoặc cleanup.

### 25.5. WAL-specific alerts

- pg_wal directory tăng nhanh.
- Archive failed_count tăng.
- Logical/physical slots inactive giữ WAL.
- Standby lag tăng.
- Free space trên WAL volume thấp.

### 25.6. Temporary-specific alerts

temp_bytes rate tăng mạnh, temp_files count tăng nhanh hoặc temp volume gần đầy. Kết hợp query logs để tìm workload tạo temp.

### 25.7. Alert quality

Alert phải chứa database/volume/tablespace, current bytes, free bytes, growth rate, threshold và trend. Tránh gửi hàng trăm alerts cho cùng một volume; group theo failure domain.

## 26. Runbook: volume gần đầy

1. Xác định mount/volume thực sự gần đầy.
2. Kiểm tra PGDATA, pg_wal, tablespaces, logs, temp và backup staging.
3. Xác định growth rate và thời gian tới ngưỡng.
4. Kiểm tra archive failures và replication slots.
5. Kiểm tra temporary files và long-running queries.
6. Kiểm tra tables/indexes tăng bất thường.
7. Dừng hoặc giảm đúng workload tạo growth nếu cần.
8. Mở rộng volume hoặc chuyển dữ liệu theo capacity plan.
9. Không xóa file PostgreSQL nội bộ bằng tay.
10. Xác minh free space, WAL/archive và application writes sau xử lý.

## 27. Runbook: database tăng dung lượng bất thường

1. So sánh database size snapshots với baseline.
2. Xếp hạng tables/indexes theo size hiện tại và delta.
3. Xác định table/partition tăng nhanh.
4. Kiểm tra n_live_tup, n_dead_tup và autovacuum timestamps.
5. Kiểm tra workload insert/update/delete và retention jobs.
6. Kiểm tra index growth và duplicate/unneeded indexes.
7. Kiểm tra TOAST/large values.
8. Kiểm tra transaction lâu và xmin horizons.
9. Dùng pgstattuple trên một số relations đại diện nếu cần và đã đánh giá I/O.
10. Chọn xử lý: fix workload, vacuum tuning, retention/partitioning hoặc rewrite có maintenance plan.

## 28. Runbook: pg_wal tăng bất thường

1. Đo pg_wal directory size và filesystem free bytes.
2. Đọc pg_stat_archiver và PostgreSQL logs.
3. Kiểm tra active/inactive replication slots.
4. Tính WAL distance từ current LSN tới restart_lsn.
5. Kiểm tra physical standby lag và logical subscriber health.
6. Kiểm tra WAL generation rate.
7. Khắc phục archive destination/permissions/network.
8. Khôi phục consumer hoặc quyết định resync nếu slot không còn dùng được.
9. Chỉ drop slot sau khi xác nhận owner và tác động.
10. Xác minh WAL directory giảm theo checkpoint/recycle lifecycle.

## 29. Runbook: xử lý bloat có kiểm soát

1. Xác định relation chiếm nhiều bytes và có growth bất thường.
2. Kiểm tra dead tuple estimates và autovacuum history.
3. Kiểm tra long-running transactions và replication horizons.
4. Chạy pgstattuple/approx trên sample relations nếu phù hợp.
5. Xác định có thể reclaim bằng VACUUM thông thường hay cần rewrite.
6. Tính extra disk cho VACUUM FULL/REINDEX/CLUSTER/tool.
7. Đánh giá lock và application downtime.
8. Chạy trong maintenance window hoặc dùng phương án online đã kiểm chứng.
9. So sánh relation size và filesystem free trước/sau.
10. Theo dõi planner, latency và autovacuum sau thay đổi.

## 30. Giới hạn trên managed PostgreSQL

Managed services có thể không cho truy cập OS filesystem hoặc pg_wal trực tiếp. Dùng provider metrics cho allocated/used/free storage, storage autoscaling và quota, IOPS/throughput/latency, temporary storage nếu được expose, WAL/replication lag metrics, backup storage và retention, tablespace limitations.

### 30.1. Provider storage metrics

Xác định metric là allocated bytes, used bytes hay available bytes. Các provider có thể định nghĩa khác nhau; đọc documentation để không so sánh nhầm.

### 30.2. Autoscaling

Xác minh max storage, growth increment, cooldown, billing và thời gian scale. Alert trước khi chạm quota.

### 30.3. Không giả định quyền superuser

Một số size functions hoặc filesystem functions có thể bị hạn chế. Thiết kế dashboard bằng metrics provider và SQL views được hỗ trợ.

### 30.4. Backup quota riêng

Backup retention có thể dùng storage/quota riêng với database volume. Theo dõi backup repository và export artifacts độc lập.

## 31. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ xem pg_database_size | Bỏ sót WAL/logs/temp/other files | Kết hợp volume metrics |
| Cộng database size và tablespace size | Đếm trùng storage | Dùng từng góc nhìn riêng |
| Dùng pg_relation_size làm total table size | Bỏ qua TOAST/indexes | Dùng pg_total_relation_size |
| Coi n_live_tup là exact count | Sizing/validation sai | Dùng count khi cần chính xác |
| Coi n_dead_tup là bytes bloat | Đánh giá sai disk impact | Dùng pgstattuple/analysis |
| Coi VACUUM thường trả disk về OS | Dự báo free space sai | Phân biệt reusable space với file shrink |
| Chạy VACUUM FULL khi volume gần đầy | Rewrite cần thêm disk, có thể thất bại | Tính peak space trước |
| Xóa file trong pg_wal thủ công | Corruption/recovery failure | Sửa archive/slot và dùng quy trình PostgreSQL |
| Drop inactive slot ngay | Consumer mất khả năng resume | Xác định owner/resync |
| Chỉ cảnh báo theo phần trăm | Bỏ qua absolute bytes và growth | Kết hợp percent, bytes, time-to-full |
| Dùng một sample để forecast | Forecast không ổn định | Rolling window và peak scenarios |
| Bỏ qua tablespace volume riêng | Một mount đầy trước PGDATA | Theo dõi từng mount |
| Bỏ qua inodes | Không tạo được files dù còn bytes | Theo dõi df -i |
| Coi temp_bytes là temp files hiện tại | Đọc sai dung lượng đang chiếm | Dùng filesystem và counters đúng nghĩa |
| Coi wal_bytes là pg_wal size | Nhầm generation với retention | Đo WAL files riêng |
| Quên index rebuild overhead | Thiếu disk khi maintenance | Tính peak storage |
| Quét pgstattuple toàn cluster thường xuyên | I/O overhead lớn | Chạy có chọn lọc |
| Không lưu snapshots | Không biết growth trend | Thu thập lịch sử theo thời gian |

## 32. Bài tập thực hành PostgreSQL

Thực hiện trên lab/staging hoặc môi trường có quyền monitoring. Tránh chạy size scans nặng, VACUUM FULL hoặc REINDEX trên production khi chưa có capacity/maintenance plan.

1. **Database size:** liệt kê database sizes bằng pg_database_size.
2. **Pretty size:** định dạng bytes bằng pg_size_pretty.
3. **Current database:** đo size của current_database().
4. **Largest database:** sắp xếp databases theo bytes.
5. **Relation size:** đo pg_relation_size của một table.
6. **Table size:** đo pg_table_size và giải thích khác biệt.
7. **Index size:** đo pg_indexes_size.
8. **Total relation:** đo pg_total_relation_size.
9. **Breakdown:** so sánh heap/table/index/total bytes.
10. **Largest tables:** liệt kê 30 tables lớn nhất.
11. **Schema size:** tổng hợp relation sizes theo schema.
12. **Index inventory:** liệt kê indexes lớn nhất.
13. **Index usage:** join pg_stat_user_indexes với size.
14. **Constraint index:** xác định index đang enforce primary/unique constraints.
15. **TOAST:** tìm table có TOAST storage lớn.
16. **Partition parent:** đo size của partitioned parent.
17. **Partition children:** liệt kê size từng partition.
18. **Partition skew:** tìm partition lớn nhất.
19. **Tablespace:** liệt kê tablespace locations và sizes.
20. **Volume mapping:** map tablespace path tới mount point.
21. **Filesystem:** chạy df -h trên lab host.
22. **Inodes:** chạy df -i và giải thích inode exhaustion.
23. **Database vs volume:** so sánh pg_database_size với filesystem usage.
24. **WAL directory:** đo pg_ls_waldir nếu version/permission hỗ trợ.
25. **WAL statistics:** đọc pg_stat_wal và wal_bytes.
26. **WAL rate:** lấy hai snapshots và tính WAL bytes/sec.
27. **Archive:** đọc pg_stat_archiver.
28. **Archive failure:** mô phỏng archive failure trong lab và quan sát WAL retention.
29. **Replication slot:** liệt kê physical/logical slots.
30. **Inactive slot:** tạo consumer dừng và quan sát slot inactive.
31. **WAL distance:** tính pg_wal_lsn_diff tới restart_lsn.
32. **Slot recovery:** khôi phục consumer và theo dõi WAL recycle.
33. **Temporary files:** đọc temp_files/temp_bytes từ pg_stat_database.
34. **Temp rate:** tính temp_bytes delta mỗi phút.
35. **Temp logging:** cấu hình log_temp_files trên lab.
36. **Query temp:** dùng pg_stat_statements tìm queries ghi temp blocks.
37. **Dead tuples:** đọc n_dead_tup/n_live_tup.
38. **Autovacuum:** xem last_autovacuum và autovacuum_count.
39. **Old transaction:** liên kết pg_stat_activity với vacuum horizon.
40. **VACUUM:** chạy VACUUM thường và so sánh relation size trước/sau.
41. **Reusable space:** giải thích vì sao VACUUM không nhất thiết giảm file size.
42. **pgstattuple:** cài extension và đo một table lab.
43. **Approximate tuple:** so sánh pgstattuple và pgstattuple_approx.
44. **Free space map:** cài pg_freespacemap và xem pg_freespace.
45. **FSM meaning:** giải thích page free space khác filesystem free.
46. **VACUUM FULL:** chạy trên table nhỏ lab và đo extra disk/lock.
47. **TRUNCATE:** truncate table lab và quan sát file size.
48. **DROP:** drop object lab và theo dõi filesystem usage.
49. **REINDEX:** rebuild index lab và đo peak storage.
50. **CLUSTER:** thử rewrite table lab và quan sát disk.
51. **Growth snapshot:** tạo bảng monitoring.database_size_samples.
52. **Sample job:** lưu database size snapshot theo lịch.
53. **Growth delta:** tính bytes tăng giữa hai samples.
54. **GiB/day:** chuyển growth rate sang GiB/day.
55. **Negative delta:** tạo/drop object và quan sát size giảm.
56. **Rolling average:** tính moving average growth rate.
57. **Forecast:** tính days-to-reserve từ free bytes và growth.
58. **Peak scenario:** dùng percentile/peak growth thay average.
59. **Relation snapshots:** tạo monitoring.relation_size_samples.
60. **Largest growth:** tìm tables có delta bytes lớn nhất.
61. **Partition history:** lưu size history theo partition.
62. **Schema inventory:** so sánh schema size theo ngày.
63. **Capacity threshold:** tạo alert theo free bytes.
64. **Percentage alert:** tạo alert theo phần trăm volume used.
65. **Time-to-full:** tạo alert khi forecast thấp hơn lead time.
66. **WAL alert:** cảnh báo khi pg_wal vượt ngưỡng.
67. **Temp alert:** cảnh báo khi temp writes tăng đột biến.
68. **Tablespace alert:** cảnh báo một volume tablespace gần đầy.
69. **Managed metrics:** tìm hiểu provider used/free storage definitions.
70. **Autoscaling:** thiết kế alert cho storage quota ceiling.
71. **Maintenance capacity:** ước lượng space cho REINDEX/VACUUM FULL.
72. **Bulk load:** benchmark growth/WAL/temp trong một bulk import.
73. **Retention:** thiết kế partition retention và đo bytes giải phóng.
74. **Bloat:** chọn table có dead tuples cao để điều tra.
75. **Incident:** viết runbook volume gần đầy.
76. **Incident:** viết runbook pg_wal tăng bất thường.
77. **Incident:** viết runbook database growth spike.
78. **Dashboard:** xây dashboard database/table/index/WAL/filesystem capacity.
79. **Forecast:** dự báo ngày chạm reserve threshold bằng dữ liệu 30 ngày.
80. **Thiết kế tổng hợp:** xây hệ thống capacity monitoring PostgreSQL có snapshots, growth rate, partition/table/index breakdown, WAL/temp/tablespace/filesystem metrics, forecast, alert thresholds, maintenance headroom và incident runbooks.

## 33. Checklist capacity monitoring

### Đo dung lượng

- [ ] Database sizes được thu thập bằng bytes.
- [ ] Table, index và TOAST được phân rã.
- [ ] Partitioned tables được tính không trùng.
- [ ] Tablespace locations được map tới volumes.
- [ ] WAL directory và archive được theo dõi.
- [ ] Temporary usage được thu thập.
- [ ] Backup repository có metrics riêng.

### Tăng trưởng

- [ ] Có snapshots theo lịch.
- [ ] Growth rate tính theo elapsed time thực tế.
- [ ] Stats reset được ghi nhận cho cumulative counters.
- [ ] Rolling average và peak growth được xem xét.
- [ ] Time-to-reserve được forecast.
- [ ] Relation/partition growth outliers được phát hiện.

### Free space và maintenance

- [ ] Filesystem bytes và inodes được theo dõi.
- [ ] Page free space được phân biệt với filesystem free.
- [ ] Dead tuples/autovacuum được giám sát.
- [ ] Replication slots và archive backlog được giám sát.
- [ ] Extra disk cho index build/rewrite được dự trù.
- [ ] Không xóa files PostgreSQL nội bộ thủ công.

### Alerts và runbooks

- [ ] Warning/critical thresholds có absolute bytes và percentages.
- [ ] Alert time-to-full tính theo growth trend.
- [ ] Mỗi tablespace volume có alert riêng.
- [ ] WAL/temp/archive alerts có owner.
- [ ] Runbook xác định nguồn growth và hành động an toàn.
- [ ] Managed storage quota/autoscaling được theo dõi.

## 34. Tổng kết

Capacity monitoring PostgreSQL cần kết hợp các số đo ở database, relation, tablespace, WAL, temporary storage và filesystem.

~~~text
DATABASE / RELATION
  pg_database_size
  pg_total_relation_size
  pg_table_size / pg_indexes_size
             |
             v
TABLESPACE / WAL / TEMP
  pg_tablespace_size
  pg_ls_waldir / pg_stat_wal
  pg_stat_database.temp_bytes
             |
             v
FILESYSTEM / CLOUD VOLUME
  used bytes / free bytes / inodes
             |
             v
TIME SERIES
  snapshots -> growth rate -> forecast
             |
             v
CAPACITY ALERTS + RUNBOOKS
~~~

Những nguyên tắc quan trọng:

- **Dùng size functions đúng cấp.** pg_database_size đo database; pg_total_relation_size đo relation cùng indexes và TOAST; pg_tablespace_size là một góc nhìn storage khác.
- **Không cộng database size và tablespace size.** Chúng có thể mô tả cùng các relation files.
- **Đo filesystem trực tiếp.** pg_database_size không bao gồm toàn bộ WAL, logs, temp, backups hoặc files khác trên volume.
- **Lưu bytes và snapshots.** Growth rate phải dựa trên delta bytes chia cho elapsed time, không tính từ chuỗi pg_size_pretty.
- **Dự báo tới reserve threshold.** Đừng chờ volume đạt 100%; tính peak growth, provision lead time và maintenance headroom.
- **Phân biệt free space trong page với free space của volume.** VACUUM thường làm space reusable trong relation, không nhất thiết trả bytes về filesystem.
- **Theo dõi WAL, slots, archive và temporary files.** Chúng có thể làm disk tăng nhanh dù table sizes ít thay đổi.
- **Tính extra storage cho maintenance.** VACUUM FULL, REINDEX, CLUSTER và bulk load có thể cần peak capacity lớn hơn steady-state.
- **Giám sát từng tablespace mount.** Một volume riêng có thể đầy trong khi PGDATA vẫn còn chỗ.
- **Dùng estimates đúng mục đích.** n_live_tup/n_dead_tup và tuple bloat estimates giúp tìm đối tượng cần điều tra; chúng không thay exact byte metrics hoặc filesystem metrics.

Một hệ thống capacity monitoring tốt không chỉ báo “database đang dùng bao nhiêu GB”. Nó cho biết dung lượng đang nằm ở đâu, tăng do nguyên nhân gì, còn bao lâu trước khi chạm reserve và cần hành động nào để duy trì khả năng ghi, backup, vacuum và recovery an toàn.

