# Theo dõi dung lượng, tốc độ tăng trưởng và tài nguyên còn lại

Trong chương **Quan sát và vận hành** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một hệ thống Java không chỉ phải ghi dữ liệu đúng trong từng transaction mà còn phải **duy trì khả năng ghi, đọc, phục hồi và mở rộng theo thời gian**. Database có thể vận hành ổn định với độ trễ thấp hôm nay nhưng ngừng ghi vào tuần sau vì dung lượng đĩa, WAL, bảng tạm hoặc tài nguyên kết nối cạn kiệt. Tình huống này thường không được phát hiện nếu dashboard chỉ theo dõi CPU và thời gian SQL.

Chủ đề **“Theo dõi dung lượng, tốc độ tăng trưởng và tài nguyên còn lại”** yêu cầu trả lời ba nhóm câu hỏi: **đang dùng bao nhiêu**, **đang tăng/giảm theo cơ chế nào**, và **còn bao lâu hoặc bao nhiêu dư địa trước khi một giới hạn trở thành rủi ro**. Muốn trả lời, cần kết hợp số liệu của ứng dụng Java, hệ quản trị cơ sở dữ liệu, hệ điều hành, lưu trữ, hệ thống backup và các thành phần phân tán.

Điểm quan trọng nhất: **kích thước dữ liệu logic, kích thước file database và dung lượng trống của thiết bị không phải cùng một đại lượng**. Tương tự, “còn 30% disk” không đảm bảo hệ thống đủ tài nguyên cho một lần tạo index, failover, restore hoặc chiến dịch marketing làm số đơn tăng đột biến. Bài học xây dựng cách đo có ý nghĩa, tính dự báo với giả định rõ ràng, đặt cảnh báo theo thời gian còn lại và thực hiện runbook mà không phá vỡ tính bền vững của dữ liệu.

## 1. Bắt đầu từ câu hỏi vận hành chứ không từ một biểu đồ

Giả sử dịch vụ đơn hàng Java sử dụng PostgreSQL. Hôm nay API có p95 latency tốt và các câu SQL đều chạy đúng. Tuy nhiên:

- Bảng sự kiện tăng nhanh do mỗi đơn phát ra nhiều bản ghi.
- Index mới được tạo cho chức năng tìm kiếm làm dung lượng tăng.
- WAL archive bị trễ khi object storage chập chờn.
- Một replication slot ngừng được consume, giữ lại WAL.
- Lượng dữ liệu xóa logic lớn nhưng dung lượng file chưa giảm.
- Connection pool trên nhiều pod đồng thời tiến gần giới hạn `max_connections` của PostgreSQL.

Một dashboard “database CPU 25%” không phát hiện được các rủi ro đó. Cần định nghĩa **capacity signals** theo từng mục tiêu:

| Câu hỏi của người vận hành | Chỉ số/bằng chứng cần xem | Hậu quả nếu bỏ qua |
| --- | --- | --- |
| Còn bao nhiêu chỗ để ghi dữ liệu? | Dung lượng khả dụng thực của từng filesystem/volume, quota và autoscaling giới hạn. | Ghi thất bại, WAL/checkpoint gặp lỗi, downtime. |
| Dữ liệu nghiệp vụ đang tăng nhanh đến đâu? | Kích thước DB/bảng/index theo thời gian, số hàng và lưu lượng ghi. | Dự báo sai ngày chạm giới hạn. |
| WAL có tích lũy bất thường không? | Kích thước/tuổi WAL, archive backlog, replication slot, replica lag. | Đĩa đầy dù bảng không tăng nhiều. |
| Có đủ RAM/CPU/I/O cho tải tương lai? | CPU, RSS, buffer hit, IOPS/throughput/latency, queue/wait. | p95/p99 tăng trước khi disk đầy. |
| Còn bao nhiêu kết nối? | DB active/idle, pool pending, giới hạn phía DB và tổng các replica ứng dụng. | Connection storm, từ chối kết nối. |
| Backup và restore còn nằm trong năng lực hạ tầng? | Dung lượng backup, thời gian backup/restore, WAL retention, RPO/RTO đo được. | Có bản sao nhưng không phục hồi kịp. |
| Biểu đồ thay đổi vì workload hay do sự cố? | Deployment, migration, bulk job, vacuum, index build, failover, tăng traffic. | Xử lý nhầm nguyên nhân, làm rủi ro lớn hơn. |

Không nên chọn một con số “% dung lượng đã dùng” rồi coi đó là toàn bộ bài toán capacity.

## 2. Những lớp lưu trữ cần được phân biệt

Một đường ghi phổ biến:

```text
HTTP / Message
      |
      v
Java Service --Connection pool---> PostgreSQL
      |                               |
      |                               +-- Table heap / TOAST
      |                               +-- Index / materialized view
      |                               +-- WAL / checkpoints
      |                               +-- Temp files / sort / hash
      |                               +-- Catalog / metadata
      |                               |
      |                               v
      |                       Filesystem / Volume / Quota
      |
      +-- Cache (JVM/Redis)   +-- WAL archive / backup storage
      +-- Logs/traces         +-- Replica / DR region
```

Mỗi lớp có đơn vị, chính sách retention và giới hạn khác nhau:

| Lớp | Dung lượng được tính cho | Nguồn tăng trưởng điển hình |
| --- | --- | --- |
| **Bảng và TOAST** | Dữ liệu lưu ở relation của PostgreSQL. | Hàng mới, cập nhật tạo phiên bản, giá trị lớn. |
| **Index** | Cấu trúc tìm kiếm của bảng/index phụ trợ. | Bản ghi mới, index mới, fragmentation. |
| **WAL tại primary** | Log phục hồi/replication trong `pg_wal`. | Lưu lượng ghi, checkpoint, archiving/slot giữ WAL. |
| **Temporary files** | Sort, hash, thao tác SQL dùng disk tạm. | Query lớn, `work_mem`/plan không phù hợp. |
| **Backup và WAL archive** | Bản sao, log phục hồi ở kho riêng. | Tần suất backup, retention, độ biến động dữ liệu. |
| **Cache** | RAM/disk của Redis, JVM hoặc DB buffer. | Tập key nóng, TTL, số session, dữ liệu mapping. |
| **Log ứng dụng** | Log/traces, audit, file diagnostics. | Tăng traffic, lỗi lặp, bật SQL logging quá chi tiết. |
| **Bộ nhớ/CPU/connections** | Tài nguyên xử lý, không phải dung lượng data file. | Tăng request, query nặng, tăng số pod/pool. |

Với hệ thống có nhiều tablespace hoặc volume khác nhau, bảng/index có thể nằm trên một thiết bị, WAL/log/backup trên thiết bị khác. **Đĩa nào đầy mới quyết định sự cố**; không thể cộng tất cả phần trống rồi suy ra có một kho dùng chung.

## 3. Dung lượng logic và dung lượng vật lý không tăng giống nhau

Một bảng 100 triệu bản ghi không nhất thiết có cùng kích thước file ở hai thời điểm hoặc hai cluster. Kích thước phụ thuộc:

1. Độ dài hàng, độ rộng cột, các giá trị `NULL` và TOAST.
2. Số/chủng loại index và kích thước key.
3. Mức độ cập nhật/xóa, các phiên bản hàng mà MVCC đang giữ.
4. Vacuum, khả năng tái sử dụng trang, free space và fragmentation.
5. Fillfactor, pattern insert/update, partitioning và version engine.
6. Compression, lưu trữ tệp/volume, snapshot và provisioning của hạ tầng.

Ví dụ nếu mỗi ngày có một triệu `UPDATE` trên các hàng cũ, **số hàng sống** gần như không đổi nhưng database vẫn tạo thêm phiên bản hàng/index tùy mô hình cập nhật. Autovacuum có thể thu hồi không gian cho **tái sử dụng bên trong relation**, nhưng thường không làm file ở filesystem nhỏ ngay. Một bộ đếm “số hàng tăng 0%” không chứng minh dung lượng vật lý không tăng.

Ngược lại, xóa hàng triệu hàng cũng không bảo đảm filesystem lập tức có thêm nhiều GiB khả dụng. Bởi vậy cần đo **kích thước file và dung lượng hệ lưu trữ**, không chỉ đếm dòng.

## 4. PostgreSQL: đo kích thước database và các bảng lớn

PostgreSQL cung cấp các hàm trả về dung lượng theo byte. Ví dụ:

```sql
-- Tổng kích thước của database hiện tại.
SELECT current_database() AS database_name,
       pg_database_size(current_database()) AS size_bytes,
       pg_size_pretty(pg_database_size(current_database())) AS size_display;
```

Những bảng chiếm nhiều dung lượng:

```sql
SELECT
    schemaname,
    relname AS table_name,
    pg_relation_size(relid) AS table_main_bytes,
    pg_table_size(relid) AS table_with_toast_bytes,
    pg_indexes_size(relid) AS indexes_bytes,
    pg_total_relation_size(relid) AS total_bytes,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_display
FROM pg_stat_user_tables
ORDER BY total_bytes DESC
LIMIT 30;
```

Ở đây:

- `pg_relation_size` mặc định báo kích thước **main fork** của relation, không phải toàn bộ heap + index + TOAST.
- `pg_table_size` giúp nhìn kích thước của bảng cùng các phần liên quan theo định nghĩa PostgreSQL, gồm TOAST (nếu có) nhưng **không tính index thông thường của bảng**.
- `pg_indexes_size` phản ánh dung lượng index liên quan.
- `pg_total_relation_size` gồm bảng, index và các phần liên quan theo định nghĩa của PostgreSQL.
- View thống kê `pg_stat_user_tables` chủ yếu liệt kê relation người dùng; với partitioned tables cần xem **các partition vật lý**. Kích thước của một parent partitioned table không tự bằng tổng mọi partition con.

**Cẩn trọng:** các hàm kích thước mô tả những file mà PostgreSQL thống kê ở phạm vi object/database. Chúng **không trả dung lượng trống thực của filesystem**, và không tự bao gồm mọi WAL/archive, OS logs, backup hoặc khối volume bị snapshot giữ lại.

### Khi đọc kích thước theo thời gian

Để đo tăng trưởng, cần lấy mẫu định kỳ và lưu ngoài một câu query tức thời:

```text
2026-11-20 00:00Z: orders total = 210 GiB
2026-11-21 00:00Z: orders total = 219 GiB
2026-11-22 00:00Z: orders total = 228 GiB

Mức tăng trung bình quan sát: khoảng 9 GiB/ngày trong 2 ngày.
```

Đây là số liệu **minh họa**. Nếu chỉ có hai điểm đo, không đủ kết luận 9 GiB/ngày sẽ giữ nguyên trong 6 tháng. Cần xem chu kỳ cuối tuần, batch cuối tháng, index build, backfill và thay đổi retention.

## 5. Dung lượng trống phải lấy từ lớp filesystem/volume hoặc provider

Một sai lầm nguy hiểm là dùng:

```text
free_space = provisioned_volume_size - pg_database_size(...)
```

Phép tính đó thường **sai** vì file system còn chứa WAL, logs, dữ liệu DB khác, temp file, metadata và các file không thuộc `pg_database_size`. Bên cạnh đó, tablespace có thể nằm trên volume khác; filesystem có block dành riêng, quota hoặc đặc tính thin provisioning.

Số liệu dung lượng trống nên đến từ:

- OS/host metrics: `node_filesystem_avail_bytes`, `node_filesystem_size_bytes` hoặc chỉ số tương đương.
- Volume/bucket metrics do cloud provider/managed DB cung cấp, gồm quota, autoscaling ceiling.
- Thông tin filesystem và mountpoint thật chứa `PGDATA`, `pg_wal`, tablespace, temp và logs.
- Với container/Kubernetes: giới hạn và chính sách PersistentVolume/StorageClass, không nhầm dung lượng root filesystem của container với PV chứa dữ liệu.

Trên máy Linux được phép quan sát, kiểm tra minh họa:

```bash
# Chỉ dùng trên hệ thống được phép vận hành.
df -h /var/lib/postgresql/data
df -i /var/lib/postgresql/data
```

`df -h` trả mức dùng block theo filesystem; `df -i` kiểm tra inode (có thể cạn dù còn GiB, tùy filesystem). Nếu `pg_wal` hoặc tablespace là mount khác, phải kiểm tra chính mount đó. Trên managed DB, có thể không có shell; sử dụng metric của provider.

**Phân biệt:** available bytes, free bytes, usable quota và remaining autoscale headroom có thể khác nhau; nên dùng đại lượng thực sự quyết định liệu tiến trình database còn **có thể ghi file**.

## 6. Theo dõi WAL, checkpoint và sự cố giữ log

PostgreSQL dùng **write-ahead log (WAL)** để hỗ trợ durability, recovery và replication. WAL phát sinh từ các thao tác ghi và maintenance; tốc độ WAL **không đồng nghĩa tốc độ tăng kích thước bảng**.

Các tình huống khiến WAL tích lũy:

- Replication slot không được consumer xử lý, khiến WAL cần giữ lại.
- WAL archiving lỗi hoặc chạy chậm, làm WAL đã sẵn sàng chưa được lưu/giải phóng theo chính sách.
- Replica lag hoặc workload ghi lớn tạo backlog.
- Checkpoint, full-page writes và hoạt động bulk làm tốc độ sinh WAL tăng.
- Cấu hình retention, slot/archiving, sự cố mạng và hệ lưu trữ không đáp ứng.

Kiểm tra thông tin archiver:

```sql
SELECT archived_count,
       last_archived_wal,
       last_archived_time,
       failed_count,
       last_failed_wal,
       last_failed_time,
       stats_reset
FROM pg_stat_archiver;
```

Kiểm tra các replication slot và **ước lượng WAL đã phát sinh kể từ vị trí restart của slot**:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    database,
    restart_lsn,
    pg_size_pretty(
        GREATEST(
            pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn),
            0
        )::bigint
    ) AS wal_since_restart_lsn
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC;
```

**Không diễn giải con số ở cột cuối là chính xác số byte WAL đang chiếm disk vì slot đó.** Nó là khoảng cách LSN ước lượng, có thể chưa phản ánh segmentation, chia sẻ retention giữa nhiều slot, archiving, config giới hạn slot hoặc tổng file vật lý trong `pg_wal`. Để xác định nguy cơ đầy disk, vẫn phải đo **dung lượng mount WAL thực tế**.

### Không can thiệp bằng cách xóa WAL thủ công

**Không xóa file trong `pg_wal` để giải phóng dung lượng.** Việc đó có thể phá crash recovery, replica hoặc PITR. Cách xử lý phụ thuộc nguyên nhân: kiểm tra archive destination, sửa consumer, phục hồi replication, điều chỉnh retention/slot theo runbook và đánh giá tác động dữ liệu. Xóa/drop replication slot cũng có thể làm replica/consumer không tiếp tục từ vị trí cũ; cần phê duyệt và kế hoạch resync.

## 7. Theo dõi tablespace, index, TOAST và partition

Dung lượng database có thể tăng do những đối tượng ít xuất hiện trong API:

- Index mới hoặc index phình do cập nhật.
- Bảng có cột JSONB/text lớn chuyển dữ liệu sang TOAST.
- Partition cũ chưa được drop theo retention.
- Materialized view được refresh hoặc tăng số dòng.
- Bảng audit/inbox/outbox/event ngày càng lớn.
- Temporary relation và index build tạm ở thời điểm migration.

Kiểm tra kích thước tablespace:

```sql
SELECT spcname,
       pg_tablespace_size(oid) AS size_bytes,
       pg_size_pretty(pg_tablespace_size(oid)) AS size_display
FROM pg_tablespace
ORDER BY size_bytes DESC;
```

Đây là dung lượng nội dung tablespace theo cách PostgreSQL tính, **không phải capacity hoặc available bytes của volume chứa tablespace**. Khi so sánh với filesystem, phải lập bản đồ tablespace → mountpoint đúng.

Để xem partition lớn, có thể truy vấn metadata cây partition rồi đo các **leaf relation** thực tế. Đừng cộng cả parent (đặc biệt partitioned table thường không chứa heap data) rồi cho rằng kết quả chính xác nếu query đã bao gồm tất cả leaf, TOAST và index theo định nghĩa khác nhau.

### Dung lượng index không phải “dữ liệu thừa”

Một index 100 GiB có thể cần thiết để giữ p99 query thấp; xóa bừa sẽ làm query chậm, tăng CPU/I/O hoặc lock contention. Khi đề xuất giảm index phải xem query plan, workload đọc/ghi, index usage, unique constraint và chi phí maintenance.

Thêm index cũng không miễn phí: ngoài dung lượng lâu dài còn có **dung lượng tạm/đỉnh**, WAL và tải I/O khi xây. Mỗi migration lớn cần ước lượng headroom trước khi chạy.

## 8. MVCC, dead tuples và bloat: vì sao xóa hàng chưa làm đĩa trống?

PostgreSQL dùng MVCC. Khi `UPDATE` hoặc `DELETE`, các phiên bản hàng cũ không nhất thiết biến mất khỏi file ngay; vacuum xử lý việc thu hồi không gian có thể tái sử dụng theo điều kiện.

Thống kê hữu ích:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

**Các bộ đếm `n_live_tup` và `n_dead_tup` là ước lượng thống kê**, không phải một phép đo bloat chính xác theo byte. Một giá trị n_dead_tup lớn cần được đặt cạnh tỷ lệ update/delete, thời điểm vacuum, transaction dài, replication/retention và số trang relation.

Các điểm cần hiểu:

1. Vacuum thông thường thường giúp **tái sử dụng không gian trong relation** hơn là trả toàn bộ GiB cho OS.
2. Một transaction lâu hoặc điều kiện giữ phiên bản cũ có thể cản cleanup theo cơ chế MVCC.
3. `VACUUM FULL` hoặc các thao tác rewrite có thể thu hồi file vật lý nhưng có chi phí khóa, I/O, WAL và **cần dung lượng trống để tạo bản mới**.
4. Reindex cũng có thể đòi thêm không gian, không phù hợp khi disk đã gần 100%.
5. Xóa dữ liệu không đúng chính sách retention có thể vi phạm pháp lý/kiểm toán.

**Sai lầm:** “Disk gần đầy, chạy VACUUM FULL toàn DB ngay”. Đây có thể là thao tác làm sự cố tệ hơn. Trước tiên cần xác định object nào tăng và còn đủ headroom cho maintenance hay không.

## 9. Đừng quên temporary files và workload đột biến

Một query phân tích hoặc sort lớn có thể làm hệ thống tạo file tạm trên disk. Mức dùng tạm có thể tăng rất nhanh rồi biến mất sau khi query kết thúc, nên sampling một lần mỗi ngày dễ bỏ lỡ.

Trong PostgreSQL, có thể xem tổng bộ đếm temp ở mức database:

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    pg_size_pretty(temp_bytes) AS temp_bytes_display,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

`temp_bytes` là **bộ đếm tích lũy dung lượng file tạm được ghi theo thống kê**, không phải số byte file tạm đang chiếm disk ngay lúc query chạy. Muốn phát hiện đỉnh, cần metric filesystem/temp directories với khoảng sampling phù hợp, log temp file theo policy và phân tích query plan.

Các nguyên nhân:

- Sort hoặc hash aggregate lớn so với bộ nhớ khả dụng.
- Join thiếu index hoặc dữ liệu skew gây temp spill.
- Reporting query chạy đồng thời quá nhiều.
- Migration/index build/batch sử dụng vùng tạm.

Tăng `work_mem` cho mọi session không phải giải pháp đơn giản: đây là cấu hình có thể áp dụng **theo thao tác trong query và nhiều session song song**, nên tổng RAM tiêu thụ có thể tăng rất mạnh. Cần đo workload, giới hạn concurrency và thay đổi có kiểm soát.

## 10. Tốc độ tăng trưởng: đo bằng delta theo khoảng thời gian

Một số liệu dung lượng tức thời không cho biết khi nào cần mở rộng. Phải lưu chuỗi thời gian:

```text
time                 used_bytes   available_bytes   wal_used_bytes
2026-11-19 00:00Z     600 GiB        400 GiB          15 GiB
2026-11-20 00:00Z     611 GiB        389 GiB          16 GiB
2026-11-21 00:00Z     622 GiB        378 GiB          16 GiB
2026-11-22 00:00Z     634 GiB        366 GiB          35 GiB
```

Các con số giả định này cho thấy:

- Phần dữ liệu đang tăng khoảng 11–12 GiB/ngày theo cửa sổ ngắn.
- WAL có thể tăng đột biến 19 GiB trong một ngày; cần xem archive/replication và workload.
- Sự khác biệt giữa used và available còn chịu tác động của logs, filesystem overhead, volume quota và các thành phần khác.

Với chuỗi điểm `S(t)` đo bằng **byte trên cùng phạm vi**, tăng trưởng trung bình trong cửa sổ \(\Delta t\) là:

\[
g_{\text{bytes/day}} = \frac{S(t_2)-S(t_1)}{(t_2-t_1)\ \text{tính theo ngày}}
\]

Nếu dung lượng giảm vì retention/cleanup, `g` có thể âm; cần kiểm tra đó là hành vi bình thường hay do xóa dữ liệu bất thường. Khi muốn dự báo capacity, nên dùng **xu hướng dùng thực tế của volume**, không chỉ tốc độ tăng bảng. Dữ liệu DB logical tăng trong khi available bytes giảm còn nhanh hơn có thể do WAL hoặc backup cùng disk.

### Chọn cửa sổ đo

- **5–15 phút:** phát hiện đột biến, disk sụt nhanh, WAL tăng bất thường.
- **24 giờ:** so với chu kỳ ngày, batch ban đêm.
- **7–30 ngày:** đánh giá xu hướng tuần, tăng trưởng bền vững.
- **Quý/năm:** lập ngân sách, retention và mở rộng hạ tầng.

Tần suất là **gợi ý theo loại workload**, không phải chuẩn chung. Các đối tượng lớn có thể đo ít thường xuyên để giảm chi phí; filesystem free và alert cần quan sát đủ nhanh theo tốc độ có thể đầy thực tế.

## 11. Dự báo ngày chạm ngưỡng và dành khoảng an toàn

Một dự báo đơn giản khi tốc độ tăng gần tuyến tính:

\[
\text{ngày tới ngưỡng} = \frac{\text{dung lượng khả dụng}-\text{dự trữ an toàn}}{\text{tốc độ tăng GiB/ngày}}
\]

Chỉ dùng công thức khi tốc độ tăng dương và đã thống nhất **đơn vị, phạm vi filesystem và ngưỡng**.

Ví dụ minh họa:

**Một volume có usable capacity 1.000 GiB**, đã dùng 620 GiB, còn 380 GiB. Nhóm chủ động chừa **100 GiB dự trữ** cho peak WAL, maintenance và vận hành. Dung lượng dùng đang tăng **12 GiB/ngày**.

```text
Capacity theo mức cần quản lý:   1.000 GiB
Đang sử dụng:                     620 GiB
Available:                         380 GiB
Phần dự trữ an toàn:               100 GiB
Headroom có thể tiêu thụ:          280 GiB
Growth dự kiến:                    12 GiB/ngày

Days to safety threshold = 280 / 12 ≈ 23,3 ngày
```

Điều này **không có nghĩa disk sẽ đầy chính xác sau 23,3 ngày**. Đó là thời gian ước tính tới ngưỡng an toàn với giả định tốc độ tăng không đổi. Nếu workload tăng gấp đôi, WAL bị giữ lại hoặc có maintenance tạo dữ liệu tạm, thời gian sẽ ngắn hơn.

Ngược lại, với volume còn 380 GiB nhưng autoscaling storage có trần và mở rộng không tức thời, cần xem **mốc phải quyết định** trước cả ngày chạm ngưỡng.

### Dự báo với nhiều kịch bản

| Kịch bản | Tốc độ tăng giả định | Ngày tới ngưỡng 100 GiB từ ví dụ |
| --- | ---: | ---: |
| Thấp | 8 GiB/ngày | 35 ngày |
| Cơ sở | 12 GiB/ngày | 23,3 ngày |
| Cao | 20 GiB/ngày | 14 ngày |
| Đột biến tạm thời | +80 GiB ngay hôm nay, sau đó 12 GiB/ngày | Khoảng 16,7 ngày |

Số ngày trên chỉ là **phép tính theo giả định**, không phải dự báo quan sát một hệ thống thật. Dùng nhiều kịch bản giúp quyết định trước khi thiếu thời gian mua thêm dung lượng, điều chỉnh quota hoặc di chuyển dữ liệu.

## 12. Đừng bỏ qua tính mùa vụ và thay đổi kiến trúc

Một đường xu hướng thẳng có thể sai khi:

- Traffic cuối tuần/tháng/quý khác ngày bình thường.
- Chiến dịch bán hàng làm số đơn và log tăng đột biến.
- Migration backfill thêm 40% dữ liệu hoặc tạo index lớn.
- Retention chạy hàng tuần, khiến dung lượng giảm theo bậc.
- Sharding/partitioning chuyển dữ liệu sang volume khác.
- Compression, schema change hoặc TOAST làm byte/record thay đổi.
- Cấu hình WAL archiving/replication thay đổi khiến tốc độ giữ log tăng.

Một dự báo đủ tốt nên có **mốc thay đổi**: triển khai version nào, thêm index nào, cleanup lúc nào, số lượng khách hàng dự kiến ra sao. Khi thay đổi kiến trúc lớn, cần **tái hiệu chỉnh baseline**, không lấy tốc độ tăng cũ như chân lý.

Có thể dùng percentile của tốc độ tăng theo ngày, hồi quy tuyến tính theo nhiều cửa sổ, hoặc mô hình có mùa vụ. Nhưng mô hình phức tạp vẫn cần dữ liệu chính xác và **giải thích được giới hạn**.

Một biểu đồ dự báo nên hiển thị **khoảng bất định**, không chỉ một ngày cụ thể. Cần phân biệt “đến ngưỡng 80%”, “đến ngưỡng dự trữ an toàn”, “đến quota cứng” và “đến giới hạn autoscaling”.

## 13. Headroom không chỉ là dung lượng trống

Một database có thể hết khả năng phục vụ trước khi disk đầy:

| Tài nguyên | Đơn vị/metric | Giới hạn có thể chạm | Tác động điển hình |
| --- | --- | --- | --- |
| Disk/data volume | bytes available, inode, quota. | Quota/volume/filesystem. | Không thể mở rộng file hoặc ghi mới. |
| WAL volume/archive | WAL bytes, tốc độ archive, retention. | Disk, archive quota, lag. | Commit hoặc replication gặp rủi ro. |
| CPU | Sử dụng, run queue, CPU throttling. | CPU cores/throttling. | Query và commit latency tăng. |
| RAM | RSS, available memory, cache, swap. | RAM/cgroup limit. | OOM, swap, hệ thống chậm. |
| Storage I/O | IOPS, throughput, latency, queue depth. | Giới hạn volume/device. | Query, WAL fsync và checkpoint chậm. |
| DB connections | session count, active/idle, waiting. | `max_connections` và slot dự trữ. | Từ chối connection mới. |
| Connection pool | active, idle, pending, acquire latency. | Pool size và số instance. | Request xếp hàng hoặc timeout. |
| Transaction ID/maintenance | `age(datfrozenxid)`, vacuum progress. | Ngưỡng bảo vệ chống wraparound. | Rủi ro từ chối ghi nếu không bảo trì kịp. |
| Replication lag | lag bytes/time, slot lag. | Lag tối đa theo sản phẩm/retention. | Stale read hoặc giữ WAL. |
| Backup/restore | backup time, size, restore speed. | RTO, băng thông, DR capacity. | Không phục hồi đúng mục tiêu. |

**Capacity là khả năng duy trì các SLO và cam kết dữ liệu trong điều kiện tải**, không phải một chiều dung lượng ổ đĩa. Tăng disk không chữa được CPU bão hòa; tăng connection pool không chữa được lock contention.

## 14. Kết nối: tính cả nhiều pod và khoảng tăng khi rollout

Trong Java, mỗi instance có thể sử dụng một connection pool, ví dụ HikariCP. Nếu có `N` pod và mỗi pod cho phép `P` kết nối tối đa, nhu cầu lý thuyết có thể lên tới:

\[
\text{connection budget ứng dụng} = N \times P
\]

Ví dụ 12 pod, mỗi pod tối đa 20 connection tạo ra khả năng cần **240 connection**, chưa kể worker, report, migration, admin và connection dự trữ. Trong rolling deployment, số pod cũ và mới có thể **cùng tồn tại**, làm nhu cầu tăng tạm thời.

Kiểm tra phía PostgreSQL:

```sql
SHOW max_connections;

SELECT
    state,
    COUNT(*) AS sessions
FROM pg_stat_activity
GROUP BY state
ORDER BY sessions DESC;

SELECT application_name,
       usename,
       COUNT(*) AS sessions
FROM pg_stat_activity
GROUP BY application_name, usename
ORDER BY sessions DESC
LIMIT 30;
```

Các nhóm session cần được diễn giải thận trọng: session `idle` vẫn chiếm kết nối, nhưng `idle in transaction` còn có thể giữ transaction/snapshot/lock; session `active` chưa chắc đang sử dụng CPU thay vì chờ I/O/lock.

Đừng lấy số session hiện tại trừ `max_connections` rồi coi toàn bộ chênh lệch là khả dụng cho mọi role. PostgreSQL có thể dự trữ kết nối cho quyền quản trị/role ưu tiên tùy phiên bản/cấu hình; pool proxy như PgBouncer cũng làm số client session khác backend connection.

### Khi pool gần đầy

Trước khi tăng `maximumPoolSize`, cần hỏi: số query/request có N+1 không? Transaction có giữ connection khi gọi HTTP không? Có lock wait không? DB CPU/I/O có đang bão hòa? Pool quá lớn có thể chỉ tạo **hàng đợi bên trong database** thay vì tăng throughput.

## 15. CPU, RAM và I/O: biết loại tài nguyên nào đang thiếu

### CPU

CPU cao có thể do query plan kém, sort/hash, quá nhiều SQL nhỏ, chức năng JSON, autovacuum hoặc replication. Đo:

- CPU sử dụng theo process và host/cgroup.
- Thời gian chạy SQL, số executions, query plan.
- CPU throttling trên container.
- Kích thước hàng đợi và p95/p99 khi tải tăng.

### RAM

RAM dùng cho shared buffers, OS page cache, backend memory, sort/hash, kết nối và tiến trình khác. **Không cộng các cấu hình bộ nhớ như thể mọi thành phần luôn dùng đúng một mức cố định**, nhưng cũng không bỏ qua khả năng nhiều session cùng sử dụng memory tạm thời.

Ví dụ PostgreSQL có `shared_buffers` và `work_mem` với ý nghĩa khác nhau: một là vùng buffer chung; cái còn lại ảnh hưởng các thao tác query và có thể nhân theo số operation/session. Nếu tăng `work_mem` mà không kiểm soát concurrency, peak RSS có thể vượt RAM.

### I/O

I/O thường là giới hạn quan trọng của persistence. Phân biệt:

- **IOPS:** số thao tác I/O/giây.
- **Throughput:** byte/giây.
- **Latency:** thời gian hoàn tất I/O.
- **Queue depth/wait:** số yêu cầu đang chờ thiết bị.
- **WAL fsync/checkpoint:** ghi và đồng bộ liên quan commit/recovery.

Một thiết bị có 30% dung lượng trống nhưng IOPS đã chạm trần vẫn làm giao dịch chậm. Ngược lại, buffer hit ratio cao không loại bỏ WAL fsync và query CPU.

## 16. Theo dõi transaction ID age và sức khỏe autovacuum

Ở PostgreSQL, theo dõi dung lượng **không thể tách rời khả năng housekeeping**. Nếu vacuum bị chậm hoặc transaction kéo dài, dead tuples tích lũy, bộ nhớ và file quan hệ phình; ngoài ra còn có rủi ro liên quan transaction ID wraparound.

Một truy vấn quan sát:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;

SELECT pid,
       usename,
       state,
       xact_start,
       wait_event_type,
       wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 20;
```

`age(datfrozenxid)` chỉ là **một tín hiệu**; việc đánh giá rủi ro còn phụ thuộc ngưỡng cấu hình, version PostgreSQL, tuổi multixact và hoạt động vacuum. Không đặt một ngưỡng cố định cho mọi cluster mà không xem cấu hình `autovacuum_freeze_max_age` và các thông số liên quan.

Nếu phát hiện transaction rất lâu, không mặc định dùng lệnh kill ngay. Cần xác định session đó là backup, migration, job hay giao dịch người dùng; hủy session có thể gây rollback tốn thời gian hoặc làm gián đoạn xử lý.

## 17. Java: lấy số liệu kích thước DB mà không biến monitoring thành tải lớn

Ứng dụng Java có thể bổ sung một số metric ở ranh giới persistence. Ví dụ Spring JDBC và Micrometer: đọc `pg_database_size` theo lịch, lưu vào gauge; không thực hiện query trực tiếp trên **mỗi lần Prometheus scrape**.

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class DatabaseSizeSampler {
    private final JdbcTemplate jdbc;
    private final AtomicLong lastSizeBytes = new AtomicLong(-1);
    private final AtomicLong lastSuccessEpochSeconds =
            new AtomicLong(0);

    public DatabaseSizeSampler(JdbcTemplate jdbc, MeterRegistry registry) {
        this.jdbc = jdbc;
        Gauge.builder("persistence.database.size.bytes",
                      lastSizeBytes, AtomicLong::get)
             .register(registry);
        Gauge.builder("persistence.database.size.sample_epoch_seconds",
                      lastSuccessEpochSeconds, AtomicLong::get)
             .register(registry);
    }

    @Scheduled(fixedDelayString = "${monitoring.db-size-delay-ms:300000}")
    public void sample() {
        Long bytes = jdbc.queryForObject(
            "SELECT pg_database_size(current_database())",
            Long.class
        );
        if (bytes == null || bytes < 0) {
            throw new IllegalStateException("Invalid DB size sample");
        }
        lastSizeBytes.set(bytes);
        lastSuccessEpochSeconds.set(
            java.time.Instant.now().getEpochSecond()
        );
    }
}
```

Đây là mã minh họa cho ứng dụng có Spring Scheduling đã bật (ví dụ `@EnableScheduling`), Micrometer và datasource PostgreSQL phù hợp. Giá trị khởi đầu `-1` là trạng thái **chưa có mẫu**; dashboard phải xử lý nó như unknown, không xem là “dung lượng âm”. Khi query lỗi, scheduler/monitoring phải ghi nhận lỗi và độ cũ của mẫu; metric cũ **không có nghĩa là DB vẫn khỏe**. Trên môi trường chạy nhiều pod, nếu mỗi pod cùng query size mỗi 5 phút, có thể tạo truy vấn lặp; thường nên chọn collector tập trung hoặc giới hạn tần suất.

**Điều Java không thể tự suy ra từ `pg_database_size`:** số byte khả dụng trên volume, dung lượng WAL ở mount khác, quota thực và ngưỡng cloud autoscaling. Những thông số đó phải do OS/provider/storage monitoring cung cấp.

### Nên instrument những gì ở application?

- HikariCP: active/idle/pending, thời gian mượn connection, timeout.
- JDBC/ORM: thời gian SQL, số câu SQL/request, retries, commit/rollback/error.
- Application: số request/giây, tỉ lệ ghi/đọc, kích thước batch, số event/outbox đang pending.
- Business: số đơn, số dòng ghi, dung lượng payload trung bình hoặc số tài liệu đính kèm.
- Ghi lại deployment/migration để giải thích thay đổi tốc độ tăng.

Tránh gắn `customerId`, `requestId` hoặc SQL nguyên văn làm label metric vì cardinality sẽ bùng nổ và có thể lộ dữ liệu. Dùng metric ổn định với nhãn như environment, service, cluster, database được kiểm soát.

## 18. Prometheus/Grafana: ghép số liệu app, DB và filesystem

Trong hệ giám sát sử dụng Prometheus, có thể quan sát dung lượng filesystem theo metric của node exporter hoặc metric tương đương. Ví dụ truy vấn minh họa cho mount phù hợp:

```promql
node_filesystem_avail_bytes{
  instance="db-node-1",
  mountpoint="/var/lib/postgresql/data"
}
```

Phần trăm dung lượng có thể sử dụng còn lại:

```promql
100 *
node_filesystem_avail_bytes{
  instance="db-node-1", mountpoint="/var/lib/postgresql/data"
}
/
node_filesystem_size_bytes{
  instance="db-node-1", mountpoint="/var/lib/postgresql/data"
}
```

Đây là biểu thức ví dụ khi hai series **có cùng bộ label để đối chiếu** và mountpoint đúng. Trong môi trường có nhiều label, device, filesystem ảo hoặc bind mount, cần lọc/ghép series tương ứng; không nên lấy một bản sao mount trùng làm nhiều volume khác nhau. Với managed DB, nên dùng metric provider và không tự giả định exporter này tồn tại.

### Nhìn xu hướng thời gian

Một biểu thức như:

```promql
predict_linear(
  node_filesystem_avail_bytes{
    instance="db-node-1",
    mountpoint="/var/lib/postgresql/data"
  }[7d],
  24 * 3600
)
```

ước lượng available bytes sau **24 giờ tới** bằng hồi quy tuyến tính trên bảy ngày quan sát. Nó **không biết** trước lịch chạy VACUUM FULL, rollback lớn, thêm disk hay retention theo ngày; vì vậy chỉ là tín hiệu dự báo, không phải kết luận chắc chắn.

Nếu muốn cảnh báo theo dự trữ an toàn, so kết quả dự báo với một ngưỡng byte được đội vận hành thiết lập theo volume. Cũng nên cảnh báo theo tốc độ giảm **rất nhanh** dù tổng còn nhiều, để phát hiện WAL/temp files đột biến.

### Ví dụ dashboard nhiều tầng

| Biểu đồ | Phạm vi | Câu hỏi |
| --- | --- | --- |
| Available GiB / % per mount | Filesystem/volume. | Volume nào có nguy cơ đầy trước? |
| DB size, top 20 tables/indexes | PostgreSQL. | Object nào tạo tăng trưởng lâu dài? |
| WAL generation/retention/archiver failures | PostgreSQL + storage. | Có log tồn đọng bất thường không? |
| Temp bytes delta, temp file spikes | PostgreSQL + filesystem. | Query nào tạo disk spill? |
| Connection pool + DB sessions | Java + PostgreSQL. | Có đủ khả năng nhận kết nối? |
| IOPS, latency, CPU, memory | Host/provider. | Thiếu tài nguyên xử lý trước khi disk đầy? |
| Backup size/duration và DR restore time | Backup platform. | Có đáp ứng RPO/RTO khi dữ liệu lớn lên? |
| Forecast / days-to-safety-threshold | Dữ liệu chuỗi thời gian. | Khi nào phải hành động? |

**Không ghép metric khác scope vào một phép tính mà không giải thích.** Ví dụ size của một database không thể được trừ trực tiếp khỏi disk tổng của cluster nhiều database; đó không phải “free space của database”.

## 19. Thiết kế cảnh báo theo hành động và thời gian còn lại

Cảnh báo tốt trả lời **ai cần làm gì và còn bao lâu trước khi rủi ro xảy ra**, không chỉ một giá trị cao.

Một chính sách minh họa:

| Tình huống | Mức phản ứng | Hành động |
| --- | --- | --- |
| Dự báo chạm ngưỡng an toàn trong 30 ngày | Planning/ticket. | Xem growth trend, dự trù capacity, retention và roadmap. |
| Dự báo chạm ngưỡng trong 14 ngày | Cảnh báo chủ động. | Kiểm tra phương án tăng dung lượng, quy trình phê duyệt. |
| Dự báo chạm ngưỡng trong 7 ngày | Ưu tiên cao theo hệ thống. | Lập lịch triển khai, đo lại và chuẩn bị contingency. |
| Available giảm rất nhanh trong 15 phút | Cảnh báo sự cố. | Kiểm tra WAL, temp, backup/log, migration và process bất thường. |
| Archive liên tục thất bại, slot lag tăng | Cảnh báo phục hồi dữ liệu. | Điều tra archiver/consumer, theo dõi WAL disk và RPO. |
| Pool pending tăng và query latency cao | Cảnh báo năng lực xử lý. | Kiểm tra N+1, lock, pool, server CPU/I/O. |
| Query sampling/telemetry ngừng báo dữ liệu | Cảnh báo thiếu quan sát. | Kiểm tra exporter/credentials; không suy ra hệ thống khỏe. |

Các mốc 30/14/7 ngày là **ví dụ**, không phải quy định chung. Một hệ thống có thể mở rộng volume trong vài phút; hệ thống khác cần hai tuần để mua thêm storage, đồng bộ replica hoặc xin change window. Ngưỡng cảnh báo phải tính **thời gian thực hiện biện pháp + thời gian kiểm thử + dự phòng**.

### Hạn chế báo động giả

- Dùng cửa sổ đủ dài tránh spike từ một mẫu lỗi.
- Tách cảnh báo tốc độ tăng bất thường khỏi forecast dài hạn.
- Chú ý time series reset, metric missing và volume vừa được mở rộng.
- Đặt nhãn owner/runbook link rõ thay vì chỉ `DiskUsageHigh`.
- Tránh nhiều cảnh báo trùng cùng nguyên nhân (ví dụ cả bảng, DB, WAL đều alert vì một migration).

**Không tắt cảnh báo dài hạn chỉ vì hôm nay disk còn 25%.** Nếu tốc độ tăng cao, 25% vẫn có thể không đủ cho một sự kiện lớn.

## 20. Dữ liệu retention, archival và partition: giảm tăng trưởng có kiểm soát

Một cách mở rộng bền vững là quản lý vòng đời dữ liệu:

- Giữ dữ liệu giao dịch chính theo chính sách nghiệp vụ/pháp lý.
- Đưa audit/log/event cũ sang storage phù hợp nếu cho phép.
- Partition bảng lớn theo thời gian hoặc khóa phù hợp, tạo khả năng xóa/archival theo partition.
- Cấu hình retention cho inbox/outbox, events và job history **sau khi đảm bảo không còn cần cho retry/đối soát**.
- Giới hạn kích thước payload, tránh lưu JSON/blob không cần trong bảng nóng.
- Kiểm tra index trùng/không còn phục vụ query trước khi đề xuất loại bỏ.

### Cẩn trọng với outbox và idempotency

Xóa bản ghi idempotency quá sớm có thể khiến một request cũ được gửi lại và **tác động nghiệp vụ lần thứ hai**. Tương tự, xóa outbox chưa publish, inbox chưa xử lý hoặc event chưa được các consumer quan trọng xác nhận sẽ làm mất khả năng phục hồi.

Retention không chỉ dựa trên câu hỏi “bảng này đã 60 ngày tuổi chưa?” mà còn trên:

1. Thời hạn có thể retry hoặc nhận message trễ.
2. Yêu cầu audit, thanh toán, pháp lý và hỗ trợ khách hàng.
3. Khả năng đối soát khi mất ACK sau commit.
4. Backup/PITR và chính sách hủy dữ liệu.
5. Trạng thái consumer, replication và downstream.

**Giảm dung lượng mà làm mất bằng chứng kết quả giao dịch không phải tối ưu an toàn.**

## 21. Lập kế hoạch cho migration, maintenance và đỉnh dung lượng

Đừng thiết kế capacity chỉ dựa trên kích thước ở trạng thái bình thường. Một hoạt động bảo trì có thể cần **nhiều dung lượng đồng thời**:

| Hoạt động | Rủi ro tăng đỉnh | Cần kiểm tra |
| --- | --- | --- |
| `CREATE INDEX` hoặc reindex | Index mới, WAL, sort temp, cạnh tranh I/O. | Headroom, khóa, version/option, thời gian chạy. |
| Thêm cột có backfill lớn | Thêm dữ liệu, WAL, bloat và replication lag. | Chia batch, tốc độ, rollback và slot lag. |
| `VACUUM FULL` hoặc table rewrite | Bản mới song song với file cũ trong giai đoạn rewrite. | Dung lượng trống, lock, outage budget. |
| Thay kiểu cột có rewrite | File/index mới và log. | Tương thích rolling deployment và phương án rollback. |
| Restore một database lớn | Dung lượng dữ liệu + index/temp/WAL và file hệ thống. | Kích cỡ vùng DR, RTO và mạng. |
| Thêm replica | Dữ liệu gần đầy đủ và WAL catch-up. | Storage, bandwidth, slot và khả năng failover. |
| Chạy báo cáo lớn | Temporary files và memory. | Query plan, concurrency và quota. |

**Capacity plan phải tính peak headroom**, không chỉ mức tăng ổn định. Với hạ tầng có autoscale, cần xác nhận có thể scale đủ nhanh và chưa chạm **trần cấu hình**; không được mặc định hệ thống tự tăng vô hạn.

## 22. Lập runbook khi volume gần đầy

Khi dung lượng tiến tới ngưỡng nguy hiểm, cách xử lý phải ưu tiên **bảo toàn dữ liệu và khả năng phục hồi**.

**Bước 1 — Xác nhận tín hiệu:** metric nào tăng? Mount nào đầy? Có lỗi metric hay sai nhãn không? Phân biệt data volume, WAL, temp, backup, OS logs.

**Bước 2 — Đo tốc độ và thời gian còn lại:** available bytes, tốc độ thay đổi 5–15 phút gần nhất, ngưỡng dự trữ và thời điểm có nguy cơ ghi thất bại.

**Bước 3 — Tìm nguyên nhân gần:** deployment, index build, batch, query temp spill, replication slot, archiving thất bại, transaction dài, backup/job lưu sai chỗ.

**Bước 4 — Chọn hành động an toàn:** tăng volume theo quy trình, tạm dừng job ghi không thiết yếu khi được phê duyệt, khắc phục archiver/consumer, dọn log hoặc dữ liệu **được xác nhận có thể xóa**.

**Bước 5 — Bảo vệ recovery:** không xóa WAL thủ công, không drop slot khi chưa biết replica/consumer cần gì, không xóa backup chưa đủ retention, không hủy dữ liệu idempotency/outbox không rõ trạng thái.

**Bước 6 — Theo dõi hậu quả:** connection, lock, WAL archive, replica lag, p95/p99, trạng thái backup, tính nhất quán và recovery capability.

**Bước 7 — Ghi kết quả:** nguyên nhân gốc, số liệu trước/sau, quyết định thay đổi retention/capacity và lịch thử phục hồi.

### Những thao tác không nên “chữa cháy” một cách mù quáng

- Xóa trực tiếp file trong thư mục dữ liệu PostgreSQL hoặc `pg_wal`.
- Chạy `VACUUM FULL` toàn bộ database khi không đủ disk hoặc chưa đánh giá lock.
- Drop replication slot chỉ vì `restart_lsn` cũ.
- `TRUNCATE` bảng audit, outbox, ledger, idempotency để lấy chỗ.
- Tăng pool/concurrency để “đẩy nhanh xử lý” khi DB đang nghẽn.
- Xóa bản backup hoặc key giải mã mà không kiểm tra retention/RPO.

Nếu cần thao tác quyền cao, phải thực hiện theo runbook có xác nhận trạng thái và phê duyệt phù hợp. Một sự cố capacity có thể nhanh chóng biến thành sự cố **mất dữ liệu** nếu xử lý sai.

## 23. Đo capacity cho backup và disaster recovery

Dữ liệu chính tăng từ 1 TiB lên 2 TiB không chỉ làm tốn thêm đĩa primary. Nó có thể:

- Tăng thời gian truyền backup lên object storage.
- Tăng dung lượng lưu nhiều bản backup theo retention.
- Tăng thời gian restore, tạo index hoặc replay WAL.
- Làm DR region thiếu dung lượng/IOPS.
- Tăng WAL archive và chi phí lưu trữ liên vùng.
- Khiến RTO từng đạt trước đây không còn khả thi.

Vì vậy, dashboard capacity cần có:

| Chỉ số | Vì sao cần |
| --- | --- |
| Dung lượng backup gần nhất và xu hướng | Dự trù kho backup, retention và chi phí. |
| Thời gian tạo backup | Phát hiện backup window ngày càng dài. |
| WAL archive backlog và độ mới | Đánh giá nguy cơ không đạt RPO. |
| Thời gian restore thử và throughput | Đánh giá RTO thực tế. |
| Headroom của DR storage | Có đủ nơi nhận dữ liệu khi production mất không? |
| Tuổi lần restore drill gần nhất | Biết độ mới của bằng chứng phục hồi. |
| KMS/key accessibility trong DR | Tránh bản sao còn nguyên nhưng không giải mã được. |

**Một backup có checksum khớp không đủ bảo đảm restore trong 60 phút.** Capacity planning phải kết hợp drill khôi phục thật, bao gồm provisioning, lấy dữ liệu, replay, validation và cutover theo hợp đồng RTO.

## 24. Dung lượng theo tenant, dịch vụ và chi phí

Trong hệ thống dùng chung database, tăng trưởng có thể không đều:

- Một tenant lưu rất nhiều file/blob lớn.
- Một API mới thêm index hoặc cột JSON.
- Một job báo cáo tạo nhiều kết quả tạm.
- Một dịch vụ giữ event dài hơn các dịch vụ khác.

Hệ thống cần khả năng **quy trách nhiệm** nhưng không làm lộ dữ liệu:

- Gắn ownership cho database/schema/partition/object.
- Với dữ liệu multi-tenant, đo số hàng/byte ước lượng theo tenant **ở mức tổng hợp được phép**, không thêm tenant ID thành nhãn metric công khai có cardinality cực cao.
- Có quota hoặc admission control nghiệp vụ khi phù hợp.
- Phân biệt **chi phí lưu data chính, index, WAL, backup, replica và network**.
- Cân nhắc chargeback/showback theo phương pháp đo rõ ràng; kích thước dùng chung của index/heap không phải lúc nào phân bổ chính xác theo tenant được.

Một cách dự báo từ nghiệp vụ là:

```text
số đơn mới/ngày
  × byte lưu trữ trung bình mỗi đơn (data + index + audit)
  × hệ số retention/phiên bản thay đổi
  + dữ liệu phục vụ truy vấn và dự phòng
```

Đây là mô hình ước lượng, phải hiệu chỉnh bằng **kích thước relation/volume thực đo** vì MVCC, index, fillfactor, compression và WAL không tăng tuyến tính đơn giản theo số đơn.

## 25. Kiểm thử cảnh báo và kịch bản tăng trưởng

Một hệ thống monitoring tốt phải được kiểm thử, không chỉ cấu hình dashboard:

| Kịch bản thử trong môi trường cô lập | Kỳ vọng |
| --- | --- |
| Sinh thêm dữ liệu với tốc độ được kiểm soát | Metric tăng; forecast điều chỉnh; alert đúng ngưỡng. |
| Tăng nhanh WAL nhưng bảng hầu như không tăng | Cảnh báo WAL/storage phát hiện trước khi hết disk. |
| Archive tạm lỗi | Metric lỗi/backlog tăng, có runbook; không xóa WAL thủ công. |
| Replication slot ngừng consume | Quan sát LSN lag/retention và dung lượng volume liên quan. |
| Temp query tạo spill lớn | Alert dung lượng ngắn hạn và metric temp ghi nhận. |
| Collector mất kết nối | Hệ thống báo telemetry stale/missing, không hiển thị xanh giả. |
| Volume được mở rộng | Forecast có thể reset baseline và phát hiện capacity mới. |
| Retention job chạy | Phân biệt giảm dung lượng hợp lệ với xóa dữ liệu bất thường. |
| Tăng gấp đôi pod khi rolling deployment | Connection budget vẫn dưới ngưỡng DB cho workload thực. |
| Mô phỏng restore DB tăng gấp đôi | DR storage và RTO có đủ theo mục tiêu không? |

Chỉ tạo dữ liệu/fault ở **môi trường thử được phép**, tránh cố tình làm đầy volume production. Với test alert, có thể dùng series synthetic vào hệ thống kiểm thử rule hoặc replay metric thay vì tạo sự cố thật.

### Ví dụ bài tập capacity

Bạn có dữ liệu quan sát (giả định):

```text
Primary data volume usable: 2 TiB
Available hôm nay:           480 GiB
Ngưỡng an toàn:              160 GiB
Growth 7 ngày:               14 GiB/ngày
Growth cao điểm:             28 GiB/ngày
Migration tuần sau:          có thể cần thêm 100 GiB tạm
Thời gian mở rộng:           10 ngày gồm review và triển khai
```

Phân tích:

1. Headroom trước ngưỡng an toàn: `480 - 160 = 320 GiB`.
2. Nếu chỉ tăng 14 GiB/ngày: `320 / 14 ≈ 22,9 ngày`.
3. Nếu tăng 28 GiB/ngày: `320 / 28 ≈ 11,4 ngày`.
4. Nếu migration dùng thêm 100 GiB tạm thì headroom giảm, kể cả khi sau đó phần tạm được giải phóng.
5. Với thời gian mở rộng 10 ngày, tình huống cao điểm và migration có thể **không còn đủ dư địa**; nên chuẩn bị mở rộng hoặc đổi lịch migration trước khi chạm ngưỡng.

Không được lấy 22,9 ngày làm lời hứa. Cần kiểm tra tốc độ sử dụng của từng mount, độ tin cậy của forecast, thời gian restore/rollout và khả năng thay đổi quota.

## 26. Checklist capacity trước mỗi lần phát hành

1. **Dung lượng thực:** đo available bytes/quota trên mọi volume/mount quan trọng, không chỉ `pg_database_size`.
2. **Dữ liệu tăng:** có chuỗi thời gian kích thước DB, top tables/indexes, partition và retention?
3. **WAL:** archive/slot/replica lag có thể giữ log quá lâu không?
4. **Temp files:** có query/batch/migration gây spill hoặc đỉnh tạm được dự báo không?
5. **MVCC/vacuum:** có bloat, transaction dài hoặc transaction ID age cần quan tâm?
6. **CPU/RAM/I/O:** có đủ dư địa ở p95/p99 và các thời điểm cao điểm?
7. **Connections:** tổng pool của mọi instance, job và rollout có dưới khả năng DB không?
8. **Forecast:** có tốc độ tăng 7/30 ngày, kịch bản cao điểm và khoảng bất định?
9. **Lead time:** thời gian mở rộng có ngắn hơn thời gian tới ngưỡng an toàn trong kịch bản xấu hợp lý?
10. **Migration headroom:** có đủ không gian cho index/rewrite/WAL/temp và rollback?
11. **Backup/DR:** backup retention, archive, restore time, DR storage có đáp ứng RPO/RTO?
12. **Observability:** metric đủ mới, labels không sai scope, có alert khi telemetry bị mất?
13. **Runbook:** ai chịu trách nhiệm, thao tác nào an toàn/cấm, khi nào phải escalation?
14. **Data safety:** retention/xóa dữ liệu đã được phê duyệt và không phá idempotency/ledger/audit?

## 27. Câu hỏi tự kiểm tra

**Câu 1.** PostgreSQL báo `pg_database_size('shopdb') = 600 GiB` trên volume 1 TiB. Có chắc còn 424 GiB cho database ghi không?

**Không.** Volume còn WAL, log, temp, dữ liệu DB khác, filesystem metadata, quota và có thể tablespace nằm ở volume khác. Cần đo available thực trên mount liên quan.

**Câu 2.** Bảng chỉ tăng 1 GiB/ngày nhưng `pg_wal` tăng 30 GiB trong buổi sáng. Nên kiểm tra gì?

Kiểm tra archiving, replication slots, replica lag, WAL generation và workload ghi/migration. Không xóa WAL thủ công để giải phóng dung lượng.

**Câu 3.** Sau khi xóa 10 triệu hàng, `df -h` gần như không đổi. Đây có chắc là database bị lỗi không?

**Không.** MVCC/vacuum có thể thu hồi chỗ để tái sử dụng trong relation mà không thu nhỏ file trên filesystem. Cần xem retention, vacuum, kích thước relation và khả năng bloat.

**Câu 4.** Có 500 GiB available và tăng 10 GiB/ngày; nhóm cần giữ 200 GiB dự phòng. Còn bao lâu tới ngưỡng dự phòng theo mô hình tuyến tính?

\((500 - 200) / 10 = 30\) ngày, **nếu** tốc độ tăng và phạm vi đo không đổi. Đây không phải ngày chắc chắn disk đầy.

**Câu 5.** Một connection pool có 20 kết nối/pod và 15 pod. Vì sao không chỉ so 300 với `max_connections`?

Vì còn worker/report/admin, giới hạn dự trữ theo role, số pod khi rollout, proxy và cách database chịu được số backend đồng thời. Ngoài số lượng còn phải xem SQL latency, lock và tài nguyên.

**Câu 6.** `temp_bytes` trong `pg_stat_database` có phải dung lượng file temp đang chiếm disk không?

**Không.** Đây là bộ đếm tích lũy; cần đo filesystem/temporary file trong thời gian thực để biết đỉnh dung lượng.

**Câu 7.** Tại sao xóa bản ghi outbox hoặc idempotency để giải phóng disk có thể làm sai nghiệp vụ?

Vì có thể mất sự kiện chưa publish, bằng chứng chống duplicate hoặc thông tin đối soát sau timeout/commit không rõ. Retention phải dựa trên giao thức retry và yêu cầu lưu lịch sử.

**Câu 8.** Nếu buffer hit ratio 99%, có thể kết luận database còn đủ năng lực không?

**Không.** CPU, WAL fsync, I/O write, lock waits, connection và dung lượng volume vẫn có thể là nút nghẽn.

**Câu 9.** Database tăng gấp đôi nhưng RTO đã thử một năm trước vẫn đạt 40 phút. Có thể tiếp tục báo RTO 40 phút không?

**Không có cơ sở chắc chắn.** Cần đo lại restore drill với backup và dung lượng mới, gồm truyền file, replay WAL, kiểm tra và cutover.

**Câu 10.** Vì sao nên cảnh báo theo “ngày tới ngưỡng an toàn” bên cạnh “disk dùng trên 80%”?

Vì một hệ thống tăng trưởng nhanh có thể mất khả năng mở rộng trước khi tới 80%; hệ thống tăng trưởng chậm có thể chưa cần hành động khẩn. Time-to-threshold kết hợp tốc độ tăng và lead time đưa ra quyết định chủ động hơn.

## Kết luận

**Theo dõi dung lượng, tốc độ tăng trưởng và tài nguyên còn lại** là công việc quan sát khả năng tiếp tục vận hành của toàn bộ đường persistence, từ các relation và index trong PostgreSQL đến WAL, filesystem, connection pool, CPU/RAM/I/O, backup và môi trường DR. Chỉ số size tức thời phải được đặt cạnh tốc độ tăng theo nhiều cửa sổ, mức dự phòng cho đỉnh tải/maintenance và thời gian cần để mở rộng.

Trong ứng dụng Java, hãy kết hợp instrument của application/JDBC/pool với metric DBMS và storage thực, phân biệt phạm vi của từng đại lượng, xây forecast có giả định, cảnh báo có hành động và kiểm thử runbook. **Một kế hoạch capacity tốt không chỉ tránh đầy đĩa; nó duy trì được transaction đúng, tính bền vững, khả năng khôi phục và trải nghiệm người dùng khi dữ liệu và tải tiếp tục phát triển.**
