# hot_standby_feedback và đánh đổi phình dữ liệu trong PostgreSQL

## 1. Vấn đề: query trên standby có thể xung đột với VACUUM trên primary

PostgreSQL hỗ trợ hot standby để một server replica có thể phục vụ các truy vấn read-only trong khi nhận và replay Write-Ahead Log (WAL) từ primary. Cơ chế này hữu ích cho read scaling, báo cáo, truy vấn phân tích và giảm tải đọc cho primary.

Tuy nhiên, primary vẫn phải dọn các tuple versions cũ bằng VACUUM. Khi VACUUM loại bỏ một tuple version, thao tác cleanup được ghi vào WAL. Standby replay WAL đó; nếu một query đang chạy trên standby vẫn cần tuple version vừa bị loại bỏ, recovery có thể phát sinh conflict và PostgreSQL phải chọn giữa hai mục tiêu:

- Giữ query trên standby chạy đến khi hoàn tất.
- Replay WAL kịp thời để standby không bị tụt quá xa primary.

`hot_standby_feedback` là một cơ chế giúp giảm một loại conflict quan trọng: conflict do VACUUM cleanup. Standby gửi thông tin về transaction snapshot cũ nhất mà nó còn cần cho primary. Primary dùng thông tin đó để trì hoãn việc loại bỏ các tuple versions mà standby query có thể cần.

Đổi lại, primary có thể phải giữ dead tuples lâu hơn. Nếu query trên standby chạy lâu hoặc thường xuyên giữ snapshot cũ, dead tuples tích tụ trên primary, làm tăng table/index bloat và áp lực storage. Đây là đánh đổi giữa độ ổn định của read queries trên standby và khả năng cleanup dữ liệu trên primary.

```text
                         PRIMARY
                 INSERT / UPDATE / DELETE
                           |
                           v
                    WAL records
                           |
                           v
                    STREAMING WAL
                           |
                           v
                         STANDBY
                    Read-only queries
                           |
             +-------------+-------------+
             |                           |
             v                           v
      Feedback OFF                Feedback ON
             |                           |
             v                           v
  VACUUM cleanup replay       Standby sends old xmin
  may conflict with query     to primary
             |                           |
             v                           v
  Query may be canceled       Primary retains old tuples
  after delay                 for longer
             |                           |
             v                           v
  Less primary retention      Fewer cleanup conflicts
  pressure                    More bloat risk
```

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao query trên hot standby có thể conflict với WAL cleanup.
2. Mô tả cách `hot_standby_feedback` gửi xmin feedback từ standby về primary.
3. Phân biệt cleanup conflict với lock, buffer pin, tablespace và deadlock conflicts.
4. Hiểu đánh đổi giữa query cancellation, replay lag và bloat trên primary.
5. Bật/tắt `hot_standby_feedback` đúng phía và đúng cách.
6. Đọc `pg_stat_replication.backend_xmin` trên primary.
7. Đọc `pg_stat_database_conflicts` trên standby.
8. Tìm transaction và snapshot lâu trên standby bằng `pg_stat_activity`.
9. Theo dõi dead tuple estimates, relation size và VACUUM trên primary.
10. Phân biệt feedback horizon với replication slot retention.
11. Hiểu vai trò của `max_standby_streaming_delay` và `max_standby_archive_delay`.
12. Giải thích vì sao replication lag thấp không chứng minh xmin horizon đã an toàn.
13. Nhận diện standby query giữ xmin quá lâu.
14. Đánh giá tác động của nhiều standbys lên vacuum horizon.
15. Thiết kế monitoring và alert cho feedback age, conflict counters và bloat.
16. Chọn cấu hình theo workload và yêu cầu đọc dữ liệu.
17. Xử lý trường hợp primary bloat tăng sau khi bật feedback.
18. Thực hiện lab quan sát query conflict và feedback.
19. Lập runbook điều tra, giảm bloat và phục hồi replay progress.
20. Đánh giá các rủi ro vận hành trước khi thay đổi cấu hình production.

## 3. Hot standby và recovery conflict

### 3.1. Primary và standby có hai công việc khác nhau

Primary nhận writes, tạo WAL và chạy VACUUM. Standby nhận WAL rồi replay để cập nhật bản sao dữ liệu. Trong hot standby mode, standby còn cho phép clients chạy read-only queries.

WAL replay phải áp dụng các thay đổi theo thứ tự. Nếu một WAL record yêu cầu thao tác không tương thích với snapshot/query đang chạy trên standby, recovery conflict có thể xảy ra.

### 3.2. Cleanup conflict

Giả sử primary có một row được UPDATE:

1. Transaction trên primary tạo tuple version mới.
2. Tuple version cũ vẫn được giữ vì một snapshot còn có thể cần nó.
3. Sau khi primary xác định version cũ không còn cần thiết, VACUUM có thể cleanup version đó.
4. WAL ghi nhận thay đổi cleanup.
5. Standby replay WAL cleanup.
6. Nếu một query trên standby vẫn cần version cũ, replay và query xung đột.

Nếu không có cơ chế bảo vệ phù hợp, PostgreSQL có thể cancel query trên standby để replay WAL tiếp tục.

### 3.3. Query trên standby là read-only nhưng vẫn giữ snapshot

Một query SELECT có thể giữ snapshot trong suốt thời gian thực thi. Snapshot xác định tuple versions nào query được phép nhìn thấy. Vì vậy một query không ghi dữ liệu vẫn có thể cản trở việc cleanup các tuple versions cũ trên primary nếu feedback được bật.

### 3.4. Conflict không chỉ do VACUUM

Recovery conflicts còn có thể liên quan tới:

- Access-exclusive locks do DDL trên primary.
- Tablespace bị xóa hoặc thay đổi.
- Buffer pins.
- Deadlocks trong quá trình recovery.
- Snapshot conflicts do cleanup records.

`hot_standby_feedback` chủ yếu giúp tránh cleanup conflicts bằng cách giữ các tuple versions cần thiết. Nó không bảo đảm mọi loại recovery conflict biến mất.

### 3.5. Replay và query cần phối hợp

Nếu standby phải cancel query, replay có thể tiếp tục. Nếu primary giữ lại dead tuples, standby có thể hoàn tất query mà không gặp cleanup conflict tương ứng. Không có cấu hình nào xóa bỏ mọi chi phí: một phía phải chịu chi phí của việc chờ, query cancellation hoặc giữ dữ liệu.

## 4. xmin feedback là gì?

### 4.1. xmin và visibility horizon

Trong MVCC, xmin là transaction ID tạo tuple version. Một snapshot cũ có thể cần nhìn thấy tuple versions được tạo trước những transaction mới hơn.

PostgreSQL duy trì một visibility horizon để biết transaction cũ nhất nào còn có thể ảnh hưởng tới việc loại bỏ tuple versions. VACUUM không thể cleanup một số versions nếu một snapshot hợp lệ vẫn có thể cần chúng.

### 4.2. Standby gửi xmin về primary

Khi `hot_standby_feedback` được bật trên standby, standby định kỳ gửi feedback về primary, trong đó có thông tin về xmin cũ nhất cần được bảo vệ bởi các transactions/snapshots trên standby.

Primary dùng feedback đó để trì hoãn cleanup đối với các tuple versions có thể vẫn cần trên standby.

### 4.3. Feedback không sao chép dữ liệu

Feedback chỉ truyền thông tin về visibility horizon. Nó không truyền rows, không thay WAL streaming, không thay replication slot và không thay backup.

### 4.4. Feedback không làm query trên standby trở thành transaction trên primary

Transaction snapshot trên standby vẫn thuộc workload read-only của standby. Primary chỉ nhận được mốc xmin để điều chỉnh việc cleanup.

### 4.5. Feedback thay đổi theo snapshot đang hoạt động

Khi query/transaction giữ snapshot kết thúc, xmin feedback có thể tiến lên ở các lần status update tiếp theo. Primary khi đó có thể cleanup nhiều tuple versions hơn trong các lần VACUUM sau.

Không nên kỳ vọng dead tuples biến mất ngay đúng thời điểm query trên standby kết thúc. Còn có chu kỳ gửi feedback, scheduling của VACUUM và điều kiện visibility khác.

## 5. Bật hot_standby_feedback

### 5.1. Setting nằm trên standby

`hot_standby_feedback` được cấu hình trên standby, vì standby là nơi biết snapshot/query nào đang hoạt động.

Ví dụ trong `postgresql.conf` của standby:

```conf
hot_standby_feedback = on
```

Sau đó reload cấu hình nếu parameter context của phiên bản cho phép:

```sql
SHOW hot_standby_feedback;
SELECT pg_reload_conf();
```

Kiểm tra giá trị có hiệu lực:

```sql
SHOW hot_standby_feedback;
```

Đừng chỉ đọc file cấu hình. Hãy xác minh setting runtime sau khi reload và kiểm tra logs nếu có lỗi cấu hình.

### 5.2. Tắt feedback

```conf
hot_standby_feedback = off
```

Khi tắt, standby không gửi xmin feedback theo cơ chế này. Primary có thể cleanup tuple versions sớm hơn, nhưng query trên standby có thể bị cancel nếu WAL replay cần cleanup những versions đó.

### 5.3. Parameter context và reload

`hot_standby_feedback` là setting cần cấu hình ở standby và thường có thể áp dụng bằng reload trong các phiên bản hỗ trợ. Kiểm tra `pg_settings.context`, `source`, `pending_restart` trên server thực tế:

```sql
SELECT
    name,
    setting,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name = 'hot_standby_feedback';
```

### 5.4. Không bật trên primary

Setting này có ý nghĩa ở standby. Bật/tắt nó trên primary không thay thế feedback từ standby. Thay đổi đúng instance và đúng cấu hình service.

### 5.5. Cần có hot standby

Standby phải ở chế độ hỗ trợ read-only queries trong recovery. Kiểm tra `hot_standby` và trạng thái recovery:

```sql
SHOW hot_standby;

SELECT pg_is_in_recovery();
```

`pg_is_in_recovery()` trả `true` trên standby đang replay WAL.

## 6. Đánh đổi chính: query cancellation hay bloat?

### 6.1. Khi feedback tắt

Primary có thể cleanup dead tuples theo vacuum horizon thông thường. Nếu cleanup WAL conflict với query trên standby, query có thể bị cancel sau khi đạt giới hạn delay được cấu hình.

Ưu điểm:

- Primary ít bị giữ dead tuples bởi standby feedback.
- Giảm một nguồn gây table/index bloat.
- Vacuum có thể tiến triển sớm hơn khi standby queries kết thúc hoặc bị cancel.

Nhược điểm:

- Query phân tích dài trên standby có thể bị hủy.
- Client phải retry hoặc chia query thành các phần nhỏ.
- Dashboard/reporting có thể thất bại khi replay cần cleanup.
- Người vận hành phải quản lý conflict và query duration.

### 6.2. Khi feedback bật

Primary nhận xmin horizon từ standby và trì hoãn cleanup các tuple versions còn có thể cần.

Ưu điểm:

- Giảm cleanup conflicts trên standby.
- Query read-only dài có cơ hội hoàn tất.
- Giảm lỗi query bị cancel do VACUUM cleanup.
- Hữu ích cho báo cáo/analytics cần snapshot ổn định.

Nhược điểm:

- Dead tuples có thể tồn tại lâu hơn trên primary.
- Heap và index có thể tăng kích thước/bloat.
- Autovacuum có thể chạy nhưng không reclaim được các tuples còn bị horizon giữ.
- Storage, I/O và backup size có thể tăng.
- Nếu horizon bị giữ quá lâu, áp lực transaction ID age và khả năng vacuum tiến triển cần được theo dõi.

### 6.3. Không có cấu hình miễn phí

Bật feedback chuyển một phần chi phí từ standby query cancellation sang primary tuple retention. Tắt feedback chuyển chi phí về standby query cancellations và replay scheduling.

Chọn theo SLA của query và giới hạn storage/maintenance của primary.

### 6.4. Bảng so sánh

| Tiêu chí | Feedback OFF | Feedback ON |
| --- | --- | --- |
| Cleanup conflict do VACUUM | Có thể cancel query | Giảm đáng kể nếu feedback còn hiệu lực |
| Standby query dài | Có nguy cơ bị hủy | Có cơ hội hoàn tất |
| Primary dead tuples | Ít bị giữ bởi standby feedback | Có thể tăng |
| Primary bloat | Ít áp lực từ nguồn này hơn | Có thể tăng theo snapshot age |
| Vacuum cleanup | Có thể tiến nhanh hơn | Có thể bị trì hoãn bởi xmin |
| Replay lag | Query cancel giúp replay tiếp tục | Thường giảm cleanup conflicts, nhưng WAL vẫn có thể bị trễ vì lý do khác |
| Phù hợp | Standby ưu tiên replay freshness | Standby ưu tiên query continuity |

## 7. Feedback và max_standby_streaming_delay

`max_standby_streaming_delay` quyết định thời gian tối đa standby được phép trì hoãn replay WAL khi gặp conflict trong streaming replication trước khi query bị cancel.

Ví dụ:

```conf
max_standby_streaming_delay = '60s'
```

Đây là giới hạn delay của việc replay WAL trong ngữ cảnh conflict, không phải timeout tuyệt đối cho từng query. Một query có thể chạy lâu hơn giá trị này nếu chưa tiêu hết delay budget; ngược lại, query có thể bị cancel sớm nếu replay đã bị trì hoãn bởi các conflicts trước đó.

### 7.1. Giá trị thấp

Giá trị thấp ưu tiên replay freshness. Query trên standby dễ bị cancel hơn khi conflict xảy ra.

### 7.2. Giá trị cao

Giá trị cao cho query nhiều thời gian hơn, nhưng standby có thể tụt xa primary trong lúc chờ. Nếu WAL generation rate cao, lag có thể tăng nhanh.

### 7.3. Giá trị -1

Trong các phiên bản hỗ trợ, `-1` cho phép standby chờ vô hạn đối với một số recovery conflicts. Điều này có thể giữ query lâu nhưng làm replay bị đình trệ không giới hạn. Không đặt vô hạn nếu SLA yêu cầu replica luôn theo kịp primary.

### 7.4. Archive delay khác streaming delay

`max_standby_archive_delay` áp dụng khi standby replay WAL từ archive; `max_standby_streaming_delay` áp dụng với WAL streaming. Nếu standby có cả hai nguồn WAL, cần hiểu cả hai settings.

### 7.5. Feedback và delay là hai công cụ khác nhau

- Feedback cố gắng ngăn primary cleanup các tuple versions mà standby còn cần.
- Standby delay cho phép replay chờ khi conflict đã xảy ra.
- Query cancellation là biện pháp để replay tiếp tục khi delay budget hết.

Có thể phối hợp cả hai, nhưng phải đo bloat và lag để biết cấu hình thực tế có phù hợp.

## 8. Những loại conflict feedback không giải quyết

### 8.1. Lock conflicts

Một DDL trên primary có thể cần AccessExclusiveLock. Khi WAL replay yêu cầu lock xung đột với query trên standby, feedback xmin không thể loại bỏ conflict này.

### 8.2. Tablespace conflicts

Nếu tablespace bị drop trên primary trong khi standby query đang sử dụng nó, recovery có thể phải cancel query. Feedback không bảo vệ tablespace object khỏi thao tác quản trị đó.

### 8.3. Buffer pin conflicts

Một query giữ buffer pin có thể cản trở replay thao tác cần buffer đó. Đây không phải cleanup horizon conflict đơn thuần.

### 8.4. Deadlock conflicts

Recovery và query workload có thể tạo deadlock conditions. Feedback không giải quyết deadlock.

### 8.5. Kết luận vận hành

Nếu bật `hot_standby_feedback` nhưng vẫn thấy query bị cancel, hãy phân loại conflict bằng `pg_stat_database_conflicts` và logs. Đừng giả định setting không có hiệu lực chỉ vì một query vẫn bị hủy.

## 9. Quan sát feedback trên primary

### 9.1. pg_stat_replication.backend_xmin

Trên primary, view `pg_stat_replication` hiển thị thông tin của các standbys kết nối trực tiếp. Cột `backend_xmin` thể hiện xmin được standby báo cáo.

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sync_state,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL
        THEN age(backend_xmin)
    END AS feedback_xmin_age,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_catalog.pg_stat_replication
ORDER BY age(backend_xmin) DESC NULLS LAST;
```

### 9.2. Diễn giải backend_xmin

- Có giá trị: standby đang báo một xmin horizon cần được bảo vệ.
- Giá trị có tuổi lớn: feedback horizon cũ; cần tìm transaction/query trên standby đang giữ snapshot.
- NULL: tại thời điểm đọc không có xmin được báo cáo trong row đó. Không kết luận chỉ từ NULL rằng setting chắc chắn đang tắt.

### 9.3. So sánh nhiều standbys

Nếu có nhiều replicas, mỗi standby có thể báo một horizon khác nhau. Một standby chạy query rất lâu có thể giữ xmin cũ hơn những standby còn lại. Khi đánh giá cleanup, cần xem tất cả standbys trực tiếp và các replication paths liên quan.

### 9.4. backend_xmin khác replay_lag

`replay_lag` phản ánh độ trễ replay được thống kê; `backend_xmin` phản ánh transaction horizon mà standby báo. Một standby có replay lag thấp vẫn có thể giữ xmin cũ do một transaction/query dài.

### 9.5. Feedback không phải số lượng dead tuples

Age của backend_xmin không cho biết có bao nhiêu dead tuples hoặc bao nhiêu GB bloat. Cần kết hợp với table statistics, relation sizes và vacuum logs.

## 10. Tìm query giữ snapshot trên standby

### 10.1. Long-running transactions

Trên standby:

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    query_start,
    clock_timestamp() - query_start AS query_age,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL
        THEN age(backend_xmin)
    END AS backend_xmin_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 10.2. Idle in transaction

Một client có thể BEGIN, đọc dữ liệu rồi để transaction mở trong khi ứng dụng chờ. Snapshot vẫn có thể tồn tại dù query hiện tại không còn chạy.

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    state,
    state_change,
    clock_timestamp() - state_change AS state_age,
    backend_xmin,
    left(query, 200) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
```

### 10.3. Query dài nhưng transaction ngắn

Không phải mọi query dài đều giữ snapshot qua nhiều transactions. Kiểm tra cả `xact_start`, `query_start`, state và `backend_xmin` để hiểu snapshot lifetime.

### 10.4. Application_name

Thiết lập `application_name` có ý nghĩa trên các connection pools và reporting jobs. Nó giúp xác định service nào tạo query dài thay vì chỉ nhìn PID.

### 10.5. Không terminate chỉ vì age cao

Một query có thể là báo cáo hợp lệ hoặc maintenance quan trọng. Xác định owner, business impact, cancellation policy và liệu có thể chia query thành batches trước khi terminate.

## 11. Theo dõi recovery conflicts trên standby

`pg_stat_database_conflicts` ghi nhận các query bị cancel do recovery conflicts.

```sql
SELECT
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock
FROM pg_catalog.pg_stat_database_conflicts
ORDER BY datname;
```

### 11.1. Các counters

| Counter | Ý nghĩa |
| --- | --- |
| confl_tablespace | Query bị cancel do tablespace bị xóa/thay đổi |
| confl_lock | Query bị cancel do lock conflict |
| confl_snapshot | Query bị cancel do snapshot/cleanup conflict |
| confl_bufferpin | Query bị cancel do buffer pin conflict |
| confl_deadlock | Query bị cancel do deadlock trong recovery |

### 11.2. Counter tăng không cho biết query nào bị cancel

View này là tổng hợp theo database. Để tìm query cụ thể, kết hợp PostgreSQL logs, application logs và timestamps.

### 11.3. Counter có thể bị reset

Statistics reset làm thay đổi counters. Nếu cần xu hướng dài hạn, scrape định kỳ và lưu ở hệ thống monitoring bên ngoài.

### 11.4. Đọc counter theo tỷ lệ

Một database có số `confl_snapshot` tăng nhanh trong giờ báo cáo có thể đang gặp cleanup conflicts. So sánh với query duration, feedback state và replay lag để xác định tác động.

## 12. Đo bloat và dead tuples trên primary

### 12.1. Table statistics

Trên primary, lấy estimates:

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
    ) AS estimated_dead_pct,
    last_autovacuum,
    autovacuum_count,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
```

`n_dead_tup` là estimate, không phải phép đếm vật lý chính xác. Hãy nhìn trend và size cùng lúc.

### 12.2. Kiểm tra relation lớn

```sql
SELECT
    c.oid::regclass AS relation,
    pg_size_pretty(pg_relation_size(c.oid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS index_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_catalog.pg_class AS c
WHERE c.relkind IN ('r', 'm')
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 50;
```

### 12.3. Theo dõi VACUUM

```sql
SELECT
    p.pid,
    a.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    a.query_start,
    clock_timestamp() - a.query_start AS runtime,
    a.wait_event_type,
    a.wait_event
FROM pg_catalog.pg_stat_progress_vacuum AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid
ORDER BY a.query_start;
```

Nếu VACUUM chạy nhưng dead tuples không giảm, feedback horizon là một khả năng cần kiểm tra cùng long transactions, slots và workload writes.

### 12.4. pgstattuple

Extension `pgstattuple` có thể đo tuple/free-space information chi tiết hơn:

```sql
SELECT *
FROM pgstattuple('public.orders'::regclass);
```

Lệnh này có thể scan relation và tạo I/O đáng kể. Chỉ dùng có chọn lọc khi cần chẩn đoán bloat; không polling toàn bộ bảng lớn liên tục.

### 12.5. Dead tuple estimates không đồng nghĩa bloat percentage

Dead tuples là một thành phần của không gian chưa reclaim. Bloat còn phụ thuộc page fill, index structure, free space và khả năng tái sử dụng. Đừng chuyển thẳng `n_dead_tup / n_live_tup` thành tỷ lệ disk waste chính xác.

## 13. Feedback và replication slots

### 13.1. Replication slot có mục đích riêng

Replication slot giữ WAL cần thiết cho một consumer. Tùy loại slot và trạng thái, slot còn có thể giữ `xmin` hoặc `catalog_xmin`, ảnh hưởng khả năng vacuum cleanup.

### 13.2. Feedback horizon và slot horizon

- `pg_stat_replication.backend_xmin`: xmin mà standby báo trong replication connection.
- `pg_replication_slots.xmin`: xmin được slot giữ.
- `pg_replication_slots.catalog_xmin`: catalog horizon được slot giữ.
- `restart_lsn`: WAL position mà slot cần giữ từ đó.

Đây là các tín hiệu liên quan nhưng không nên gộp thành một metric duy nhất.

### 13.3. Kiểm tra slots trên primary

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE
        WHEN catalog_xmin IS NOT NULL
        THEN age(catalog_xmin)
    END AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY GREATEST(
    COALESCE(age(xmin), 0),
    COALESCE(age(catalog_xmin), 0)
) DESC;
```

Một số cột chỉ có ý nghĩa với slot type phù hợp; kiểm tra NULL và version.

### 13.4. Slot inactive

Slot inactive có thể vẫn giữ WAL hoặc transaction horizon. Không drop slot chỉ vì nó không active. Xác minh consumer, owner, recovery path và khả năng rebuild trước khi thay đổi.

### 13.5. Disconnect không nhất thiết giải phóng mọi retention

Feedback connection có thể biến mất khi standby ngắt kết nối, nhưng replication slot có thể giữ retention state riêng. Một số cấu hình/version còn liên kết feedback horizon với slot. Kiểm tra `pg_replication_slots` sau disconnect và không suy đoán chỉ từ trạng thái connection.

## 14. Nhiều standbys và xmin tổng hợp

### 14.1. Standby cũ nhất có thể giữ primary

Nếu primary phục vụ nhiều standbys và một trong số đó báo xmin rất cũ, cleanup có thể bị giới hạn bởi horizon đó. Một replica chạy báo cáo dài có thể ảnh hưởng cleanup toàn primary, kể cả khi các replicas khác luôn theo kịp.

### 14.2. Đừng chỉ xem replica lag cao nhất

Một standby có lag thấp vẫn có thể có query snapshot cũ. Ngược lại, standby lag cao nhưng không giữ xmin có thể không phải nguyên nhân trực tiếp khiến VACUUM không cleanup tuple versions.

### 14.3. Xếp hạng feedback horizons

```sql
SELECT
    application_name,
    client_addr,
    state,
    backend_xmin,
    age(backend_xmin) AS feedback_xmin_age,
    replay_lag
FROM pg_catalog.pg_stat_replication
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;
```

### 14.4. Xác định replica owner

Đảm bảo application_name phản ánh vai trò thực tế: reporting, BI, analytics, HA standby hoặc disaster recovery. Owner rõ ràng giúp xác định replica nào có thể giảm query duration hoặc thay đổi policy.

### 14.5. Cascading replication

Trong topology cascading, cần hiểu feedback được truyền và áp dụng trên từng replication hop theo cấu hình/version. Quan sát trực tiếp từng upstream connection và slot; đừng giả định một query trên leaf standby không thể ảnh hưởng upstream.

## 15. Quan hệ giữa feedback và autovacuum

### 15.1. Autovacuum vẫn có thể chạy

Bật feedback không tắt autovacuum. Worker vẫn có thể scan heap, xử lý các tuples đủ điều kiện, cập nhật statistics và freeze những gì an toàn.

### 15.2. Cleanup horizon giới hạn tuples có thể remove

Nếu xmin feedback cũ hơn các tuple versions mà VACUUM muốn loại bỏ, một số versions phải được giữ lại. VACUUM có thể hoàn thành nhưng dead tuple count vẫn cao hoặc không giảm như kỳ vọng.

### 15.3. Repeated vacuum không tự giải quyết horizon

Chạy VACUUM liên tục khi standby vẫn giữ cùng một xmin cũ không thể xóa các tuples còn cần thiết cho snapshot đó. Trước tiên phải hiểu và xử lý transaction/query giữ horizon.

### 15.4. Freeze age vẫn cần monitoring

Vacuum horizon cũ có thể làm chậm khả năng tiến mốc cleanup/freeze trong một số tình huống. Theo dõi `age(relfrozenxid)`, `age(datfrozenxid)` và MultiXact age độc lập với dead tuple metrics.

### 15.5. Anti-wraparound vẫn quan trọng

Không tắt autovacuum hoặc bỏ qua XID age chỉ vì đang điều tra feedback. Nếu age tiến gần ngưỡng nguy hiểm, ưu tiên runbook chống wraparound và xử lý blockers có kiểm soát.

## 16. Lab: quan sát query conflict và feedback

Lab này cần hai PostgreSQL instances: một primary và một physical standby đã cấu hình streaming replication. Không thực hiện trên production.

### 16.1. Chuẩn bị bảng trên primary

```sql
CREATE SCHEMA IF NOT EXISTS hs_feedback_lab;

CREATE TABLE hs_feedback_lab.events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO hs_feedback_lab.events (payload)
SELECT 'event-' || g
FROM generate_series(1, 10000) AS g;

ANALYZE hs_feedback_lab.events;
```

### 16.2. Bật feedback trên standby

Trong lab standby:

```conf
hot_standby_feedback = on
```

Reload nếu phù hợp với version và xác minh:

```sql
SHOW hot_standby_feedback;
SELECT pg_is_in_recovery();
```

### 16.3. Mở query/transaction lâu trên standby

Trên standby, mở một session:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*)
FROM hs_feedback_lab.events;

-- Giữ transaction mở trong lúc thực hiện bước tiếp theo.
```

Trong lab, giữ session này mở có chủ đích. Đừng để một transaction test như vậy chạy vô thời hạn.

### 16.4. Quan sát backend_xmin trên primary

```sql
SELECT
    application_name,
    state,
    backend_xmin,
    age(backend_xmin) AS feedback_xmin_age
FROM pg_catalog.pg_stat_replication;
```

Nếu snapshot feedback đã được gửi, có thể thấy xmin được báo. Thời điểm xuất hiện phụ thuộc status update interval và hoạt động replication.

### 16.5. Tạo dead tuples trên primary

```sql
UPDATE hs_feedback_lab.events
SET payload = payload || '-changed'
WHERE id <= 5000;

DELETE FROM hs_feedback_lab.events
WHERE id BETWEEN 7001 AND 8000;
```

### 16.6. Chạy VACUUM trên primary

```sql
VACUUM (VERBOSE) hs_feedback_lab.events;
```

VACUUM phải chạy ngoài transaction block. Quan sát verbose output và statistics:

```sql
SELECT
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_vacuum
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'hs_feedback_lab'
  AND relname = 'events';
```

Với feedback horizon cũ, VACUUM có thể phải giữ các tuple versions mà standby snapshot còn cần.

### 16.7. Kết thúc transaction trên standby

```sql
COMMIT;
```

Chờ feedback horizon tiến lên, sau đó chạy lại VACUUM trên primary và quan sát kết quả. Statistics có thể trễ; so sánh logs và nhiều mẫu thay vì chỉ một lần đọc.

### 16.8. Thử feedback OFF

Trong lab riêng hoặc sau khi reset state phù hợp:

1. Tắt `hot_standby_feedback` trên standby.
2. Mở một query snapshot lâu.
3. Tạo cleanup workload trên primary.
4. Theo dõi `pg_stat_database_conflicts` trên standby.
5. Quan sát query có thể bị cancel khi WAL cleanup replay gặp conflict và delay budget hết.

Kết quả phụ thuộc timing, query snapshot, WAL và các settings delay. Không kỳ vọng một chuỗi câu lệnh ngắn luôn tái tạo conflict giống hệt trên mọi phiên bản.

## 17. Tuning max_standby_streaming_delay và feedback

### 17.1. Xác định ưu tiên workload

Trước khi tuning, xác định:

- Replica phục vụ HA hay reporting?
- Query có SLA duration bao lâu?
- Replay lag tối đa chấp nhận được?
- Primary có storage headroom bao nhiêu?
- Dead tuple growth hiện tại ra sao?
- Có thể retry/cancel queries không?

### 17.2. Reporting replica

Một replica dành cho báo cáo có thể ưu tiên query completion. Có thể bật feedback và chấp nhận primary giữ dead tuples lâu hơn, nhưng phải đặt giới hạn cho query duration, transaction lifetime và storage growth.

### 17.3. HA replica

Một standby chủ yếu phục vụ failover thường ưu tiên replay gần primary. Có thể tắt feedback hoặc dùng delay ngắn hơn tùy nhu cầu, để primary vacuum cleanup ít bị giữ lại bởi reporting snapshots.

### 17.4. Delay dài không phải miễn phí

Tăng `max_standby_streaming_delay` có thể cho query nhiều thời gian hơn khi conflict, nhưng replay lag tăng. Khi standby lag lớn, failover freshness và read freshness đều giảm.

### 17.5. Feedback không kiểm soát query lifetime

Bật feedback không thay thế query timeout, idle-in-transaction timeout, connection pool policies hoặc reporting workload management. Một transaction mở lâu có thể giữ xmin dù ứng dụng không thực hiện công việc hữu ích.

## 18. Các biện pháp giảm bloat khi vẫn cần feedback

### 18.1. Giới hạn thời gian query trên standby

Đặt `statement_timeout` phù hợp cho reporting roles hoặc application pools. Điều này giảm khả năng một query giữ snapshot hàng giờ.

Ví dụ trong role reporting:

```sql
ALTER ROLE reporting_user
SET statement_timeout = '15min';
```

Đây chỉ là ví dụ. Chọn timeout theo query SLA và cách ứng dụng xử lý cancellation.

### 18.2. Tránh idle in transaction

Đặt timeout phù hợp:

```conf
idle_in_transaction_session_timeout = '2min'
```

Timeout này cần được đánh giá với application transaction patterns. Trên standby, session idle in transaction vẫn có thể giữ snapshot.

### 18.3. Chia báo cáo thành batches

Thay một transaction đọc hàng trăm triệu rows kéo dài nhiều giờ bằng các truy vấn có phạm vi thời gian/key rõ ràng, mỗi batch có snapshot ngắn hơn. Cần bảo đảm pagination và consistency requirements của báo cáo.

### 18.4. Tách reporting workload

Dùng một reporting replica riêng có policy feedback và query timeout phù hợp. Không để một replica HA quan trọng chịu mọi workload BI dài hạn nếu điều đó ảnh hưởng failover objectives.

### 18.5. Theo dõi indexes

Dead tuples và bloat có thể ảnh hưởng cả heap lẫn index. Theo dõi `pg_indexes_size`, index usage và cấu trúc index. Nếu cần REINDEX, lên kế hoạch locking, disk headroom và version-specific behavior.

### 18.6. Điều chỉnh autovacuum theo workload

Per-table autovacuum settings có thể giúp VACUUM bắt đầu sớm hơn sau khi horizon được giải phóng. Nhưng giảm threshold không làm VACUUM vượt qua một xmin còn được bảo vệ.

## 19. Monitoring dashboard

Một dashboard tốt phải kết hợp feedback, query duration, conflict counters, vacuum và storage.

| Nhóm | Metric | Nơi quan sát |
| --- | --- | --- |
| Feedback | backend_xmin, age(backend_xmin) | Primary pg_stat_replication |
| Replica state | state, sync_state, replay_lag | Primary pg_stat_replication |
| Standby queries | xact age, query age, backend_xmin | Standby pg_stat_activity |
| Conflicts | confl_snapshot, confl_lock, ... | Standby pg_stat_database_conflicts |
| Table cleanup | n_dead_tup, last_autovacuum | Primary pg_stat_user_tables |
| Relation size | heap/index/total bytes | Primary catalogs/functions |
| Vacuum | phase, blocks, runtime | Primary pg_stat_progress_vacuum |
| Slots | xmin, catalog_xmin, restart_lsn | Primary pg_replication_slots |
| Freeze safety | XID/MXID age | Primary pg_database, pg_class |
| Storage | disk free, IOPS, latency | OS/storage monitoring |

### 19.1. Alert theo feedback age

Alert khi `age(backend_xmin)` vượt baseline trong thời gian kéo dài, nhất là khi đồng thời dead tuple estimates hoặc relation size tăng.

Không đặt một ngưỡng chung cho mọi cluster. Tốc độ cấp XID và transaction rate khác nhau.

### 19.2. Alert theo conflict rate

Theo dõi delta của `confl_snapshot` và tổng conflicts theo thời gian. Một số lượng lớn tích lũy từ nhiều tháng không nhất thiết phản ánh tình trạng hiện tại.

### 19.3. Alert theo bloat trend

Kết hợp:

- Dead tuple estimates.
- Heap/index size growth.
- VACUUM cadence và runtime.
- Feedback xmin age.
- Write rate.
- Disk free space.

### 19.4. Alert theo replay lag riêng

Replay lag là chỉ số riêng của freshness/HA. Không dùng nó thay cho feedback horizon metric.

### 19.5. Lưu metrics bên ngoài

Statistics counters có thể reset khi restart hoặc reset stats. Scrape định kỳ và lưu lịch sử trong monitoring system để so sánh xu hướng.

## 20. Runbook: primary bloat tăng sau khi bật feedback

### Bước 1. Xác nhận setting

Trên standby, kiểm tra `SHOW hot_standby_feedback`. Trên primary, kiểm tra `pg_stat_replication.backend_xmin`.

### Bước 2. Xác định standby giữ horizon cũ

Xếp hạng `backend_xmin` theo age và application_name. Xác định replica/consumer liên quan.

### Bước 3. Tìm session giữ snapshot

Trên standby tương ứng, kiểm tra `pg_stat_activity`, đặc biệt:

- Transaction lâu nhất.
- `idle in transaction`.
- Query analytics/reporting kéo dài.
- Application name và user.
- `backend_xmin` và wait events.

### Bước 4. Đo tác động trên primary

Kiểm tra:

- `n_dead_tup` và trend.
- Heap/index/total relation size.
- Autovacuum activity.
- XID/MXID age.
- Disk free và storage latency.

### Bước 5. Phân biệt nguyên nhân

Feedback không phải nguyên nhân duy nhất của bloat. Kiểm tra thêm write churn, long transactions trên primary, replication slots, prepared transactions và autovacuum capacity.

### Bước 6. Chọn cách xử lý

Có thể:

- Kết thúc hoặc chia nhỏ query dài trên standby.
- Giới hạn transaction duration/statement timeout.
- Tắt feedback nếu primary storage/freeze risk quan trọng hơn query continuity.
- Điều chỉnh standby delay để cân bằng replay và query.
- Chuyển BI workload sang replica khác.
- Tăng capacity VACUUM sau khi horizon được giải phóng.

### Bước 7. Xác minh horizon tiến lên

Theo dõi `backend_xmin` trên primary sau khi query kết thúc. Chờ feedback update và VACUUM chạy lại. Kiểm tra dead tuple trends và size sau nhiều mẫu.

### Bước 8. Đánh giá XID safety

Nếu XID age tăng nhanh, xử lý theo runbook anti-wraparound. Không chỉ tắt feedback rồi cho rằng mọi tuple đã được reclaim tức thì.

### Bước 9. Cập nhật policy

Ghi lại replica role, query SLA, feedback policy, timeout, alert threshold và owner.

## 21. Khi nào nên bật hoặc tắt feedback?

### 21.1. Nên cân nhắc bật

- Standby phục vụ query dài có SLA rõ.
- Query cancellation do cleanup conflicts gây tác động business đáng kể.
- Primary có storage headroom và autovacuum capacity đủ.
- Query lifetime được giới hạn và monitoring đầy đủ.
- Có thể xác định replica nào đang giữ xmin.

### 21.2. Nên cân nhắc tắt

- Standby ưu tiên HA/failover freshness.
- Primary đang tăng bloat hoặc gần hết storage.
- XID horizon bị giữ quá lâu.
- Query trên standby có thể retry/chia batch.
- Reporting workload có thể chuyển sang replica riêng.
- Không có đủ monitoring để quản lý retention risk.

### 21.3. Có thể bật theo vai trò replica

Không nhất thiết mọi standby đều dùng cùng policy. Một reporting replica có thể bật feedback trong khi HA standby giữ feedback off, tùy kiến trúc và version. Cần đánh giá mỗi replication path và tác động tổng hợp lên primary.

### 21.4. Đừng bật vĩnh viễn mà không đo

Sau khi bật, cần baseline và alert cho backend_xmin age, dead tuples, relation growth và vacuum. Nếu không đo, bloat có thể tăng trong nhiều tuần trước khi gây ra vấn đề storage.

### 21.5. Đừng tắt ngay khi thấy một bảng lớn

Trước khi tắt, xác định query/standby nào giữ horizon, impact query cancellation và cách phục hồi reporting. Thay đổi nên theo runbook và có người chịu trách nhiệm.

## 22. Feedback và failover

### 22.1. Standby promotion

Khi standby được promote, nó trở thành primary trên timeline mới. Feedback từ standby tới primary cũ không còn vận hành theo topology trước đó.

### 22.2. Replica mới

Sau failover, xác định các standbys đang kết nối tới primary mới, setting feedback và replication slots. Không giả định config từ topology cũ tự động phù hợp.

### 22.3. Feedback không thay replication health

Dù feedback bật, vẫn phải theo dõi WAL receive/replay, slot state, connection state, timeline và failover readiness.

### 22.4. Standby disconnected

Nếu standby ngắt kết nối, primary không còn nhận feedback mới qua connection đó. Tuy nhiên replication slot có thể giữ WAL hoặc xmin state riêng. Kiểm tra slot trước khi kết luận vacuum horizon đã giải phóng.

## 23. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| hot_standby_feedback chạy trên primary | Setting được cấu hình trên standby |
| Bật feedback tắt VACUUM | VACUUM vẫn chạy nhưng phải giữ các tuples còn cần |
| Feedback ngăn mọi recovery conflict | Chủ yếu giảm cleanup conflicts |
| Query read-only không ảnh hưởng primary | Snapshot của nó có thể giữ xmin qua feedback |
| Feedback bật thì primary không bloat | Primary có thể giữ dead tuples lâu hơn |
| Feedback tắt thì standby luôn cancel query | Chỉ khi có conflict và delay policy dẫn tới cancellation |
| max_standby_streaming_delay là timeout từng query | Nó là giới hạn delay replay do conflicts |
| Replay lag thấp nghĩa xmin mới | Hai metric đo hai điều khác nhau |
| backend_xmin là dead tuple count | Nó là transaction horizon feedback |
| VACUUM chạy xong là dead tuples phải về 0 | Horizon có thể buộc giữ lại một số versions |
| Tăng workers giải quyết feedback horizon | Worker không thể xóa tuple còn cần cho snapshot |
| Feedback thay replication slot | Slot và feedback có retention semantics riêng |
| Slot inactive chắc chắn vô dụng | Slot có thể còn cần hoặc giữ WAL/xmin |
| Query kết thúc thì primary reclaim ngay | Cần feedback update và VACUUM tiếp theo |
| Tắt feedback sẽ thu nhỏ file ngay | VACUUM thường reuse space; file có thể không shrink |
| Bloat chỉ nằm trong heap | Indexes cũng có thể tăng kích thước |
| pg_stat_database_conflicts cho biết query text | Nó cung cấp counters theo database |
| pg_stat_replication có mọi leaf standby | Chỉ hiển thị standbys kết nối trực tiếp tới server |
| hot_standby_feedback thay backup | Nó không phải backup hoặc PITR |
| Mọi reporting replica cần feedback on | Phải cân bằng query SLA và primary storage |
| Feedback không ảnh hưởng XID safety | Horizon cũ có thể làm vacuum/freeze progress khó khăn hơn |

## 24. Bài tập thực hành có đáp án

Các bài tập giả định bạn có primary và standby lab. Không bật/tắt feedback hoặc giữ transaction lâu trên production chỉ để thử.

### Bài 1. hot_standby_feedback là gì?

**Đáp án:** Cơ chế để standby gửi xmin feedback về primary nhằm bảo vệ tuple versions mà standby queries còn có thể cần.

### Bài 2. Setting này cấu hình ở đâu?

**Đáp án:** Trên standby.

### Bài 3. Feedback giúp giảm loại conflict nào?

**Đáp án:** Cleanup conflicts do VACUUM loại tuple versions mà standby snapshot còn cần.

### Bài 4. Feedback có ngăn mọi recovery conflicts không?

**Đáp án:** Không. Lock, tablespace, buffer pin và deadlock conflicts vẫn có thể xảy ra.

### Bài 5. Vì sao query SELECT trên standby ảnh hưởng primary?

**Đáp án:** Snapshot của query có thể giữ xmin và feedback khiến primary trì hoãn cleanup.

### Bài 6. Xmin feedback được xem ở đâu trên primary?

**Đáp án:** Cột backend_xmin trong pg_stat_replication.

### Bài 7. Age của backend_xmin đo gì?

**Đáp án:** Tuổi transaction horizon mà standby đang báo, không phải số lượng dead tuples.

### Bài 8. Feedback ON có thể gây tác động nào trên primary?

**Đáp án:** Giữ dead tuples lâu hơn, làm tăng bloat và storage pressure.

### Bài 9. Feedback OFF có thể gây tác động nào trên standby?

**Đáp án:** Query có thể bị cancel khi cleanup WAL conflict với snapshot và delay budget hết.

### Bài 10. max_standby_streaming_delay điều khiển gì?

**Đáp án:** Giới hạn thời gian replay WAL có thể bị trì hoãn bởi recovery conflicts trong streaming replication.

### Bài 11. Đây có phải timeout tuyệt đối của từng query?

**Đáp án:** Không. Nó là delay budget của WAL replay do conflicts.

### Bài 12. max_standby_archive_delay dùng cho trường hợp nào?

**Đáp án:** Replay WAL từ archive trên standby.

### Bài 13. Giá trị -1 của max_standby_streaming_delay có ý nghĩa gì?

**Đáp án:** Trong các phiên bản hỗ trợ, cho phép chờ vô hạn đối với một số conflicts, có nguy cơ replay lag không giới hạn.

### Bài 14. View nào ghi nhận recovery conflict counters?

**Đáp án:** pg_stat_database_conflicts trên standby.

### Bài 15. confl_snapshot phản ánh gì?

**Đáp án:** Query bị cancel do snapshot/cleanup conflicts.

### Bài 16. confl_lock phản ánh gì?

**Đáp án:** Query bị cancel do lock conflicts.

### Bài 17. confl_tablespace phản ánh gì?

**Đáp án:** Query bị cancel do tablespace conflict.

### Bài 18. confl_bufferpin phản ánh gì?

**Đáp án:** Query bị cancel do buffer pin conflict.

### Bài 19. confl_deadlock phản ánh gì?

**Đáp án:** Query bị cancel do deadlock trong recovery.

### Bài 20. Tìm query giữ snapshot lâu trên standby bằng view nào?

**Đáp án:** pg_stat_activity.

### Bài 21. Vì sao idle in transaction nguy hiểm?

**Đáp án:** Transaction có thể giữ snapshot cũ dù session không chạy query hữu ích.

### Bài 22. Feedback có thay WAL streaming không?

**Đáp án:** Không. WAL streaming chuyển thay đổi; feedback chỉ báo xmin horizon.

### Bài 23. Feedback có thay backup không?

**Đáp án:** Không. Nó không tạo recovery point hoặc bản sao dữ liệu.

### Bài 24. Replay lag thấp có chứng minh feedback xmin mới không?

**Đáp án:** Không. Một query snapshot cũ vẫn có thể giữ xmin trong khi WAL replay theo kịp.

### Bài 25. Một standby cũ có thể ảnh hưởng các standby khác không?

**Đáp án:** Nó có thể giữ primary cleanup horizon và gây bloat cho primary, ảnh hưởng toàn hệ thống.

### Bài 26. Query kết thúc thì dead tuples biến mất ngay?

**Đáp án:** Không. Feedback cần cập nhật và VACUUM cần chạy lại khi tuple đã an toàn.

### Bài 27. Tăng autovacuum workers có xóa được tuple còn cần cho snapshot?

**Đáp án:** Không. Worker phải tôn trọng visibility horizon.

### Bài 28. Feedback có thể làm autovacuum chạy nhưng không reclaim nhiều tuples?

**Đáp án:** Có. Worker vẫn chạy nhưng phải giữ các versions chưa an toàn để remove.

### Bài 29. Cột nào trên primary giúp xem feedback horizon?

**Đáp án:** pg_stat_replication.backend_xmin.

### Bài 30. Cột nào xem replay lag?

**Đáp án:** pg_stat_replication.replay_lag.

### Bài 31. Hai metric đó có giống nhau?

**Đáp án:** Không. Một metric là transaction horizon; một metric là độ trễ replay.

### Bài 32. Replication slot có thể giữ thông tin gì liên quan vacuum?

**Đáp án:** xmin và catalog_xmin; restart_lsn giữ WAL position.

### Bài 33. Slot inactive có thể còn ảnh hưởng không?

**Đáp án:** Có. Nó có thể giữ WAL hoặc transaction/catalog horizon tùy slot state/type.

### Bài 34. Có nên drop slot inactive ngay?

**Đáp án:** Không. Xác minh owner, consumer, recovery path và retention trước.

### Bài 35. Bật feedback ở mọi standby có luôn tốt?

**Đáp án:** Không. Mỗi standby có workload và impact khác nhau; cần policy theo vai trò.

### Bài 36. Reporting replica có thể cần feedback vì sao?

**Đáp án:** Để giảm query cancellation khi báo cáo chạy lâu và cần snapshot ổn định.

### Bài 37. HA replica có thể ưu tiên feedback OFF vì sao?

**Đáp án:** Để giảm retention pressure trên primary và ưu tiên replay freshness, nếu query workload có thể retry/cancel.

### Bài 38. Query timeout giúp gì?

**Đáp án:** Giới hạn thời gian snapshot/query có thể giữ xmin, giảm bloat risk.

### Bài 39. Chia báo cáo thành batches có lợi gì?

**Đáp án:** Mỗi batch có thể kết thúc transaction sớm hơn, cho phép feedback horizon tiến lên.

### Bài 40. Cần theo dõi heap và index size riêng vì sao?

**Đáp án:** VACUUM cleanup và bloat có thể ảnh hưởng heap và indexes khác nhau.

### Bài 41. n_dead_tup có chính xác tuyệt đối không?

**Đáp án:** Không. Đây là estimate trong statistics view.

### Bài 42. pgstattuple dùng để làm gì?

**Đáp án:** Đo tuple và free-space information chi tiết hơn cho một relation.

### Bài 43. Vì sao không chạy pgstattuple liên tục?

**Đáp án:** Nó có thể scan relation và tạo I/O đáng kể.

### Bài 44. Bật feedback có ngăn VACUUM chạy không?

**Đáp án:** Không. VACUUM vẫn chạy nhưng không thể remove các tuple versions còn được horizon bảo vệ.

### Bài 45. Feedback có bảo vệ khỏi DDL lock conflicts không?

**Đáp án:** Không. Lock conflicts cần được xử lý riêng.

### Bài 46. Parameter nào giới hạn replay delay trong streaming?

**Đáp án:** max_standby_streaming_delay.

### Bài 47. Parameter nào bật feedback?

**Đáp án:** hot_standby_feedback.

### Bài 48. Có thể xem setting context ở đâu?

**Đáp án:** pg_settings.context, cùng source và pending_restart.

### Bài 49. Khi feedback age cao, bước điều tra đầu tiên?

**Đáp án:** Xác định standby qua application_name/backend_xmin và tìm query/transaction giữ snapshot trên standby đó.

### Bài 50. Nếu có nhiều replicas, cần xem gì?

**Đáp án:** Tất cả backend_xmin, query age, replay lag và vai trò của từng replica.

### Bài 51. Tắt feedback có làm file relation shrink ngay?

**Đáp án:** Không. Cần horizon tiến lên và VACUUM; VACUUM thường còn ưu tiên reuse space.

### Bài 52. XID age có cần theo dõi khi feedback giữ horizon lâu?

**Đáp án:** Có. Giữ horizon lâu có thể ảnh hưởng khả năng vacuum/freeze tiến triển.

### Bài 53. pg_stat_database_conflicts có chứa query text không?

**Đáp án:** Không. Đây là counters theo database; dùng logs/activity/application logs để tìm query cụ thể.

### Bài 54. Feedback có thể loại bỏ mọi lag không?

**Đáp án:** Không. Network, WAL generation, replay throughput và locks vẫn có thể gây lag.

### Bài 55. hot_standby_feedback có cần reload trên standby không?

**Đáp án:** Setting thường áp dụng bằng reload ở các version hỗ trợ; kiểm tra parameter context và runtime value.

### Bài 56. Standby disconnected thì feedback mới còn được gửi không?

**Đáp án:** Không qua connection đã mất; tuy nhiên replication slot có thể giữ retention state riêng.

### Bài 57. Nếu feedback ON nhưng query vẫn bị cancel, kiểm tra gì?

**Đáp án:** Phân loại conflict counters, logs và xem đó có phải lock/tablespace/bufferpin/deadlock conflict hay không.

### Bài 58. Vì sao không nên đặt delay vô hạn mặc định?

**Đáp án:** Replay có thể bị đình trệ không giới hạn và failover/read freshness giảm.

### Bài 59. Sau khi kết thúc query giữ xmin, cần xác minh gì?

**Đáp án:** backend_xmin tiến lên, VACUUM chạy lại, dead tuple trend giảm và storage/freeze metrics ổn định.

### Bài 60. Lập checklist xử lý bloat do hot_standby_feedback

**Đáp án gợi ý:**

1. Xác minh hot_standby_feedback trên standby.
2. Xếp hạng pg_stat_replication.backend_xmin trên primary theo age.
3. Xác định standby/application giữ xmin cũ.
4. Kiểm tra query age, xact age và idle-in-transaction trên standby.
5. Đọc pg_stat_database_conflicts để phân loại cancellations.
6. Đo dead tuple estimates, heap/index size và vacuum progress trên primary.
7. Kiểm tra replication slots, xmin/catalog_xmin và WAL retention.
8. Chọn feedback policy và standby delay theo SLA query/replay.
9. Giới hạn query/transaction duration hoặc tách reporting workload.
10. Theo dõi horizon tiến lên, VACUUM reclaim và XID safety sau thay đổi.

## 25. Checklist production

| Kiểm tra | Điều cần bảo đảm |
| --- | --- |
| Feedback policy | Mỗi standby có mục tiêu rõ |
| hot_standby_feedback | Được xác minh trên đúng standby |
| backend_xmin | Có monitoring trên primary |
| Feedback xmin age | Có baseline và alert |
| replay_lag | Được theo dõi riêng |
| max_standby_streaming_delay | Phù hợp query/replay SLA |
| max_standby_archive_delay | Được xem nếu replay archive |
| Standby query duration | Có dashboard |
| Long transactions | Có cảnh báo |
| Idle in transaction | Có timeout/runbook |
| Application_name | Phân biệt rõ từng replica/workload |
| Conflict counters | Theo dõi delta theo database |
| Primary dead tuples | Theo dõi estimate và trend |
| Heap/index size | Theo dõi riêng |
| Autovacuum progress | Có quan sát phase/runtime |
| XID/MXID age | Có alert chống wraparound |
| Replication slots | Theo dõi xmin/catalog_xmin/restart_lsn |
| Slot ownership | Có owner và recovery plan |
| Multiple standbys | Xem horizon của tất cả replicas |
| Reporting workload | Được tách và giới hạn phù hợp |
| Query timeout | Có policy theo role/service |
| Vacuum capacity | Đủ sau khi horizon tiến lên |
| Storage headroom | Đủ cho bloat và WAL |
| Failover readiness | Không phụ thuộc một metric lag |
| Logs | Có evidence cho query cancellations |
| Stats reset context | Được lưu khi phân tích counters |
| Restore/HA drills | Kiểm thử định kỳ |
| Configuration change | Có rollout và rollback plan |
| Post-change verification | Feedback, conflicts, bloat và lag ổn định |

## 26. Tổng kết

`hot_standby_feedback` giúp standby thông báo xmin horizon cho primary để giảm recovery conflicts do VACUUM cleanup. Nó cải thiện khả năng hoàn tất query read-only trên standby, nhưng có thể khiến primary giữ dead tuples lâu hơn và tăng bloat.

Những nguyên tắc quan trọng:

1. **Feedback được cấu hình trên standby.** Standby biết snapshot nào còn cần và gửi xmin về primary.
2. **Feedback chủ yếu tránh cleanup conflicts.** Lock, tablespace, buffer pin và deadlock conflicts vẫn có thể xảy ra.
3. **Query read-only vẫn có thể giữ xmin.** Transaction snapshot lâu có thể tác động đến VACUUM trên primary.
4. **Bật feedback chuyển chi phí sang primary retention.** Query cancellation giảm nhưng bloat risk tăng.
5. **Tắt feedback có thể làm query bị cancel.** Replay freshness được ưu tiên khi cleanup conflict xảy ra.
6. **backend_xmin và replay_lag là hai metric khác nhau.** Theo dõi cả hai.
7. **pg_stat_database_conflicts giúp phân loại cancellation.** Dùng logs để tìm query cụ thể.
8. **Replication slots có retention riêng.** Kiểm tra xmin, catalog_xmin và restart_lsn.
9. **Autovacuum vẫn chạy khi feedback bật.** Nó phải giữ những tuple versions còn được horizon bảo vệ.
10. **Tăng workers không vượt qua được snapshot horizon.** Xử lý query/transaction giữ xmin trước.
11. **Giới hạn query lifetime giúp giảm bloat.** Dùng statement timeout, idle transaction timeout và batch reporting.
12. **Nhiều standbys cần được xem cùng nhau.** Một replica cũ có thể giữ cleanup horizon của primary.
13. **Không dùng feedback thay backup hoặc HA monitoring.** Đây là cơ chế quản lý visibility conflict.
14. **Tuning phải theo SLA.** Reporting replica và HA replica có thể cần policy khác nhau.
15. **Xác minh sau thay đổi.** backend_xmin cần tiến lên, VACUUM cần reclaim được tuples an toàn và replay lag phải nằm trong mục tiêu.

Mô hình quyết định:

```text
Standby query bị cancel do recovery conflict?
                 |
                 v
        Có phải cleanup conflict?
             /          \
           Có            Không
           |               |
           v               v
  Cân nhắc feedback     Điều tra lock /
  hoặc standby delay    tablespace / bufferpin
           |
           v
  Feedback có giữ xmin lâu?
           |
       +---+---+
       |       |
      Có      Không
       |       |
       v       v
 Giảm query   Kiểm tra conflict
 lifetime     logs và delay
 hoặc tắt
 feedback
       |
       v
  VACUUM tiến lên?
       |
       v
  Xác minh bloat, XID age,
  replay lag và query SLA
```

**Câu hỏi review cuối cùng:** “Nếu reporting query trên standby chạy hai giờ, primary có biết xmin cần giữ không? Chúng ta có thấy được replica nào đang giữ horizon, bloat đang tăng bao nhiêu và VACUUM có thể tiến lên sau khi query kết thúc không? Nếu tắt feedback, query cancellation và replay lag có nằm trong SLA chấp nhận được không?” Một policy tốt phải trả lời được các câu hỏi đó bằng metrics của cả primary lẫn standby.
