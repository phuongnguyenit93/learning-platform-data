# Autovacuum không theo kịp và cảnh báo transaction ID

Autovacuum là cơ chế bảo trì nền quan trọng của PostgreSQL. Nó tự động dọn các phiên bản hàng không còn cần thiết, cập nhật thống kê cho query planner và đóng băng transaction ID cũ để ngăn hiện tượng transaction ID wraparound. Khi autovacuum không theo kịp tốc độ ghi, bảng có thể phình to, truy vấn chậm, thống kê lỗi thời và tuổi transaction ID tăng tới mức đe dọa khả năng tiếp tục ghi dữ liệu.

Hai vấn đề cần được xử lý cùng lúc nhưng phải phân biệt rõ:

- **Autovacuum lag**: công việc vacuum/analyze được tạo ra nhanh hơn khả năng xử lý, hoặc bị cản trở bởi transaction dài, replication slot, tải I/O hay cấu hình không phù hợp.
- **Transaction ID wraparound risk**: PostgreSQL sắp hết khoảng an toàn để so sánh transaction ID 32-bit. Đây là rủi ro toàn vẹn dữ liệu nghiêm trọng. Khi quá gần ngưỡng, PostgreSQL có thể buộc phải ưu tiên vacuum và cuối cùng từ chối cấp transaction ID mới để bảo vệ dữ liệu.

Mục tiêu vận hành là phát hiện sớm, tìm đúng nguyên nhân, đưa vacuum bắt kịp và xác nhận tuổi transaction ID giảm hoặc ổn định ở mức an toàn. Không nên chỉ tăng tài nguyên hay chạy một lệnh vacuum mà bỏ qua nguyên nhân khiến hệ thống tụt lại.

## 1. Vì sao PostgreSQL cần autovacuum?

### 1.1. MVCC tạo ra các phiên bản hàng

PostgreSQL dùng Multi-Version Concurrency Control (MVCC) để cho phép các transaction nhìn thấy snapshot dữ liệu phù hợp với thời điểm của chúng. Khi một hàng được cập nhật hoặc xóa, PostgreSQL thường tạo phiên bản mới hoặc đánh dấu phiên bản cũ không còn hiện hành. Phiên bản cũ chưa thể bị thu hồi ngay nếu còn transaction có snapshot cần nhìn thấy nó.

Ví dụ:

```sql
UPDATE orders
SET status = 'shipped'
WHERE order_id = 1001;

DELETE FROM session_events
WHERE created_at < now() - interval '90 days';
```

Các thao tác này có thể để lại dead tuple trong heap. Dead tuple không còn nhìn thấy bởi bất kỳ transaction hợp lệ nào, nhưng vẫn chiếm chỗ trong table và có thể còn tham chiếu trong index. Vacuum xác định những tuple đã hết khả năng hiển thị, dọn tham chiếu index cần thiết và đánh dấu không gian có thể tái sử dụng.

Vacuum thông thường **không nhất thiết thu nhỏ file table trên filesystem**. Phần không gian được giải phóng thường được giữ lại để PostgreSQL tái sử dụng cho các lần insert/update sau. Điều này khác với việc trả dung lượng về hệ điều hành.

### 1.2. Những nhiệm vụ chính của autovacuum

Autovacuum launcher theo dõi các database và khởi chạy worker khi có công việc cần thực hiện. Các worker thực hiện hai loại công việc chính:

1. **VACUUM**: dọn dead tuple, xử lý index liên quan, cập nhật visibility map và freeze transaction ID đủ cũ.
2. **ANALYZE**: lấy mẫu dữ liệu để cập nhật thống kê cho query planner, giúp PostgreSQL ước lượng số hàng và chọn kế hoạch truy vấn phù hợp.

Autovacuum cũng có nhiệm vụ đặc biệt là vacuum để chống wraparound. Nhiệm vụ này không chỉ dựa trên số dead tuple. Một bảng ít cập nhật vẫn có thể cần vacuum freeze nếu transaction ID cũ trong bảng sắp vượt giới hạn an toàn.

### 1.3. Vacuum, analyze và freeze khác nhau thế nào?

| Hoạt động | Mục đích | Vấn đề nếu chậm |
|---|---|---|
| `VACUUM` | Thu hồi dead tuple có thể dọn và giúp tái sử dụng không gian | Table/index bloat, nhiều dead tuple, tăng I/O và giảm hiệu năng. |
| `ANALYZE` | Cập nhật thống kê cho planner | Planner ước lượng sai, chọn scan/join không phù hợp. |
| `VACUUM FREEZE` | Đóng băng transaction ID cũ trong tuple | Tăng nguy cơ transaction ID wraparound. |

Một lần autovacuum có thể thực hiện nhiều nhiệm vụ trong cùng chu kỳ, nhưng điều kiện kích hoạt vacuum và analyze khác nhau. Không nên xem `last_analyze` là bằng chứng rằng freeze đã theo kịp, hoặc xem `last_autovacuum` là bằng chứng mọi bảng đều an toàn.

## 2. Transaction ID và nguy cơ wraparound

### 2.1. Transaction ID là gì?

PostgreSQL cấp transaction ID (XID) cho các transaction cần định danh trong hệ thống MVCC. XID thông thường là số nguyên 32-bit, nên không gian ID hữu hạn và sẽ quay vòng sau khoảng (2^{32}) giá trị. Do cách PostgreSQL so sánh tuổi transaction theo modulo, khoảng cách an toàn giữa các XID phải nhỏ hơn một nửa không gian đó, tức khoảng (2^{31}) transaction.

PostgreSQL không thể để một tuple chứa XID quá cũ rồi tiếp tục so sánh nó như một XID mới sau khi bộ đếm quay vòng. Nếu điều đó xảy ra, tuple cũ có thể bị diễn giải sai về khả năng hiển thị, đe dọa tính toàn vẹn dữ liệu.

### 2.2. Freeze giải quyết vấn đề như thế nào?

Khi một tuple đủ cũ và đã an toàn để freeze, PostgreSQL có thể đánh dấu XID tạo tuple (`xmin`) là `FrozenTransactionId`. Giá trị frozen có ý nghĩa đặc biệt: tuple được xem như đã tồn tại từ trước mọi transaction hiện tại, vì vậy PostgreSQL không cần giữ XID gốc để so sánh mãi mãi.

Vacuum freeze cũng cập nhật metadata về tuổi transaction cũ nhất có thể còn xuất hiện trong một relation. Một số khái niệm cần phân biệt:

- `pg_class.relfrozenxid`: XID cũ nhất mà PostgreSQL cần xem xét đối với relation đó.
- `pg_database.datfrozenxid`: mốc XID cũ nhất của database, được suy ra từ các relation cần theo dõi trong database.
- `age(xid)`: số transaction ước tính đã đi qua kể từ XID được chỉ định.
- `autovacuum_freeze_max_age`: ngưỡng tuổi để autovacuum khởi chạy vacuum chống wraparound cho bảng.

`datfrozenxid` và `relfrozenxid` là mốc quản lý freeze, không phải thời điểm tạo database hay thời điểm transaction gần nhất. Tuổi XID càng lớn thì càng cần chú ý.

### 2.3. Các ngưỡng freeze quan trọng

PostgreSQL có nhiều tham số liên quan:

| Tham số | Ý nghĩa |
|---|---|
| `vacuum_freeze_min_age` | Tuổi tối thiểu của XID trước khi vacuum thông thường cân nhắc freeze tuple. |
| `vacuum_freeze_table_age` | Tuổi relation mà khi vượt qua, vacuum có thể thực hiện aggressive scan để freeze rộng hơn. |
| `autovacuum_freeze_max_age` | Tuổi tối đa để autovacuum chủ động chạy vacuum chống wraparound. |
| `vacuum_failsafe_age` | Ngưỡng rất cao để vacuum bật chế độ failsafe, ưu tiên hoàn tất chống wraparound. |
| `autovacuum_multixact_freeze_max_age` | Ngưỡng tương ứng cho MultiXact ID. |

Giá trị mặc định và giới hạn cấu hình có thể thay đổi theo major version. Các giá trị phổ biến ở nhiều phiên bản PostgreSQL là hàng chục triệu cho `vacuum_freeze_min_age`, khoảng 150 triệu cho `vacuum_freeze_table_age`, 200 triệu cho `autovacuum_freeze_max_age` và khoảng 1,6 tỷ cho `vacuum_failsafe_age`; hãy kiểm tra giá trị thực tế trên server thay vì dựa vào con số minh họa này.

Khi vacuum tiến gần ngưỡng failsafe, PostgreSQL có thể bỏ qua cost-based delay và một số công việc bảo trì không thiết yếu như index cleanup để ưu tiên hoàn tất freeze. Đây là chế độ bảo vệ cuối, không phải trạng thái vận hành mong muốn.

### 2.4. Vì sao cảnh báo transaction ID nghiêm trọng?

Nếu database tiến gần giới hạn wraparound, PostgreSQL có thể ghi cảnh báo như:

```text
WARNING: database "..." must be vacuumed within ... transactions
```

Nếu tiếp tục tiến tới ngưỡng nguy hiểm, PostgreSQL có thể từ chối cấp transaction ID mới để tránh wraparound và báo lỗi dạng:

```text
ERROR: database is not accepting commands to avoid wraparound data loss
```

Đây là biện pháp tự bảo vệ. Khi hệ thống tới trạng thái này, thao tác ghi có thể bị gián đoạn nghiêm trọng và việc phục hồi cần can thiệp DBA hoặc nhà cung cấp dịch vụ. Không chờ tới cảnh báo cuối mới xử lý.

### 2.5. MultiXact cũng có ngưỡng wraparound riêng

Ngoài XID, PostgreSQL dùng MultiXact ID để biểu diễn một nhóm transaction cùng giữ lock trên một tuple, chẳng hạn nhiều transaction cùng khóa hàng ở chế độ tương thích. MultiXact có vòng đời và cơ chế freeze riêng.

Nếu log cảnh báo `multixact` hoặc tuổi `datminmxid`/`relminmxid` tăng cao, cần điều tra tương tự nhưng dùng các hàm và tham số MultiXact, ví dụ `mxid_age()` và `autovacuum_multixact_freeze_max_age`. Không dùng `age()` cho MultiXact ID.

## 3. Nhận biết autovacuum không theo kịp

Một dấu hiệu đơn lẻ không đủ kết luận autovacuum bị lỗi. Cần kết hợp số dead tuple, thời điểm vacuum gần nhất, tuổi XID, trạng thái worker, transaction lâu và replication slot.

### 3.1. Dấu hiệu ở mức bảng

- `n_dead_tup` tăng liên tục qua nhiều lần lấy mẫu.
- `last_autovacuum` hoặc `last_autoanalyze` lâu không thay đổi dù bảng có nhiều ghi.
- Table/index size tăng nhanh hơn tốc độ tăng dữ liệu hữu ích.
- Query latency tăng, buffer hit giảm hoặc nhiều page phải đọc từ storage.
- Bảng cập nhật/xóa thường xuyên không được vacuum đủ nhanh.
- Tuổi `relfrozenxid` tăng qua các lần đo.

`n_dead_tup` là số ước lượng từ thống kê, không phải phép đếm chính xác từng tuple. Cần xem xu hướng theo thời gian và kết hợp kích thước bảng, lượng ghi và tiến độ vacuum.

### 3.2. Dấu hiệu ở mức database/cluster

- `age(datfrozenxid)` tăng nhanh hoặc database có tuổi cao bất thường so với các database khác.
- Log có cảnh báo phải vacuum trong một số lượng transaction nhất định.
- Autovacuum worker thường xuyên bận, số worker tối đa không đủ hoặc vacuum chạy lâu.
- WAL, storage hoặc I/O tăng mạnh khi vacuum bắt đầu chạy dồn dập.
- Replication slot hoặc standby feedback giữ lại xmin cũ.
- Nhiều session ở trạng thái `idle in transaction` hoặc transaction kéo dài hàng giờ/ngày.

### 3.3. Đọc cấu hình autovacuum hiện tại

Chạy trong database cần điều tra:

```sql
SHOW autovacuum;
SHOW track_counts;
SHOW autovacuum_naptime;
SHOW autovacuum_max_workers;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_vacuum_insert_threshold;
SHOW autovacuum_vacuum_insert_scale_factor;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
SHOW autovacuum_vacuum_cost_limit;
SHOW autovacuum_vacuum_cost_delay;
SHOW autovacuum_work_mem;
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
SHOW autovacuum_freeze_max_age;
SHOW vacuum_failsafe_age;
```

Một số tham số có thể không tồn tại ở major version cũ. Dùng `pg_settings` để kiểm tra tên, giá trị, nguồn cấu hình và khả năng thay đổi:

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name LIKE 'autovacuum%'
   OR name LIKE 'vacuum_freeze%'
   OR name = 'vacuum_failsafe_age'
ORDER BY name;
```

`track_counts` cần được bật để autovacuum dựa vào thống kê hoạt động đúng. Trong môi trường managed PostgreSQL, một số tham số có thể bị khóa hoặc chỉ thay đổi qua parameter group và có thể cần restart.

## 4. Các truy vấn chẩn đoán quan trọng

### 4.1. Xếp hạng database theo tuổi XID

Chạy truy vấn sau từ một database bất kỳ mà role có quyền đọc catalog:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint AS freeze_max_age,
    round(
        100.0 * age(datfrozenxid)
        / current_setting('autovacuum_freeze_max_age')::bigint,
        1
    ) AS pct_of_freeze_max_age
FROM pg_database
WHERE datallowconn
ORDER BY age(datfrozenxid) DESC;
```

Truy vấn này giúp xác định database cần ưu tiên. Tỷ lệ phần trăm là chỉ số giám sát tương đối so với ngưỡng cấu hình; không phải xác suất wraparound. Nên theo dõi xu hướng và tốc độ tăng tuổi XID thay vì chỉ lấy một ảnh chụp.

### 4.2. Xếp hạng relation theo tuổi `relfrozenxid`

Chạy trong database có tuổi cao:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    age(c.relfrozenxid) AS xid_age,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    COALESCE(s.n_live_tup, 0) AS estimated_live_tuples,
    COALESCE(s.n_dead_tup, 0) AS estimated_dead_tuples,
    s.last_autovacuum,
    s.autovacuum_count
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
LEFT JOIN pg_stat_all_tables AS s
    ON s.relid = c.oid
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY age(c.relfrozenxid) DESC
LIMIT 30;
```

`r` là table có lưu trữ, `m` là materialized view và `t` là TOAST table. Các partition leaf có storage sẽ xuất hiện; partitioned parent không chứa heap riêng nên không được dùng để đánh giá tuổi tuple như một bảng thường. Không lọc bỏ `pg_catalog` trong lần điều tra đầu tiên vì catalog cũng cần freeze.

### 4.3. Kiểm tra dead tuple và lịch sử vacuum

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
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

Nếu `n_dead_tup` lớn nhưng autovacuum vừa chạy, có thể worker chưa xử lý xong toàn bộ hoặc bảng tiếp tục phát sinh dead tuple nhanh. Hãy lấy mẫu nhiều lần và so sánh xu hướng. Với bảng partition, kiểm tra từng partition leaf vì mỗi partition có chu kỳ vacuum riêng.

### 4.4. Xem vacuum đang chạy

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum
ORDER BY datname, relation_name;
```

View này cho biết các vacuum đang chạy và phase hiện tại. Có thể lấy mẫu theo chu kỳ để ước lượng tiến độ. Không phải mọi loại vacuum hoặc mọi giai đoạn đều được thể hiện bằng cùng một trường tiến độ.

### 4.5. Tìm transaction kéo dài và snapshot cũ

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    age(backend_xmin) AS backend_xmin_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
   OR backend_xmin IS NOT NULL
ORDER BY xact_start NULLS LAST;
```

Đặc biệt chú ý `idle in transaction`, transaction bắt đầu từ lâu, session dùng cursor/snapshot dài và các tiến trình batch bị treo. Snapshot cũ có thể khiến vacuum không thể loại bỏ những tuple mà transaction đó vẫn có khả năng nhìn thấy.

Không tự động terminate mọi session lâu. Trước khi hủy, xác định chủ sở hữu ứng dụng, trạng thái transaction, tác động tới người dùng và liệu transaction có đang giữ lock quan trọng hay không. Nếu đã xác định cần dừng, `pg_cancel_backend()` chỉ hủy câu query hiện tại; `pg_terminate_backend()` kết thúc session và làm rollback transaction chưa commit. Việc này cần theo runbook và quyền được cấp.

### 4.6. Kiểm tra replication slot giữ xmin

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    age(xmin) AS xmin_age,
    catalog_xmin,
    age(catalog_xmin) AS catalog_xmin_age,
    restart_lsn
FROM pg_replication_slots
ORDER BY GREATEST(
    COALESCE(age(xmin), 0),
    COALESCE(age(catalog_xmin), 0)
) DESC;
```

Logical replication slot hoặc slot của công cụ CDC có thể giữ `xmin`/`catalog_xmin`, khiến vacuum phải giữ lại tuple hoặc catalog row cũ. Slot không hoạt động lâu ngày vẫn có thể giữ tài nguyên. Trước khi drop slot, xác định consumer còn cần slot hay không; xóa nhầm slot có thể khiến subscriber phải tạo lại hoặc đồng bộ lại dữ liệu.

Với streaming standby, kiểm tra thêm `pg_stat_replication` và `hot_standby_feedback`. Feedback có thể giảm việc query trên standby bị hủy do conflict, nhưng có thể giữ xmin cũ trên primary và làm tăng bloat.

### 4.7. Kiểm tra prepared transaction

```sql
SELECT
    gid,
    owner,
    database,
    prepared,
    now() - prepared AS prepared_age
FROM pg_prepared_xacts
ORDER BY prepared;
```

Prepared transaction bị bỏ quên có thể giữ trạng thái và ảnh hưởng tới khả năng dọn dẹp. Cần liên hệ với hệ thống transaction coordinator hoặc chủ sở hữu ứng dụng để quyết định `COMMIT PREPARED` hay `ROLLBACK PREPARED`. Không tự rollback một prepared transaction chỉ vì nó cũ; quyết định sai có thể làm lệch dữ liệu giữa các hệ thống tham gia giao dịch.

## 5. Vì sao autovacuum không theo kịp?

### 5.1. Tốc độ phát sinh dead tuple lớn hơn năng lực vacuum

Một bảng có tỷ lệ update/delete cao có thể phát sinh dead tuple nhanh hơn một worker có thể dọn. Điều này thường gặp ở bảng event, bảng trạng thái, session, queue hoặc bảng cập nhật liên tục.

Autovacuum vacuum thông thường được kích hoạt theo ngưỡng kết hợp threshold và scale factor. Công thức gần đúng cho bảng có update/delete:

\[
\text{Vacuum threshold} =
\text{autovacuum\_vacuum\_threshold} +
\text{autovacuum\_vacuum\_scale\_factor} \times
\text{estimated table tuples}
\]

Ví dụ, nếu threshold là 50, scale factor là 0,2 và bảng có 10 triệu tuple, ngưỡng kích hoạt xấp xỉ 2.000.050 dead tuple. Với bảng rất lớn, chờ tới 20% dead tuple có thể quá muộn và khiến mỗi lần vacuum phải xử lý khối lượng lớn.

Ngoài vacuum do update/delete, PostgreSQL có ngưỡng riêng cho insert để freeze tuple mới trên bảng insert-heavy. `autovacuum_vacuum_insert_threshold` và `autovacuum_vacuum_insert_scale_factor` điều khiển cơ chế này; nếu đặt threshold thành `-1`, trigger insert-based vacuum bị tắt.

### 5.2. Transaction hoặc snapshot kéo dài

Một transaction mở lâu, kể cả khi session ở trạng thái `idle in transaction`, có thể giữ snapshot cũ. Vacuum không thể thu hồi những phiên bản hàng còn có thể nhìn thấy từ snapshot đó.

Nguyên nhân phổ biến:

- Ứng dụng mở transaction trước khi gọi API bên ngoài rồi chờ phản hồi quá lâu.
- Job batch xử lý hàng triệu bản ghi trong một transaction duy nhất.
- Connection pool trả connection về pool trong khi transaction chưa kết thúc.
- Người vận hành mở transaction trong psql rồi để session qua đêm.
- Báo cáo hoặc cursor giữ snapshot lâu.

Khắc phục ở tầng ứng dụng bằng transaction ngắn, batch có checkpoint, timeout phù hợp và bảo đảm `COMMIT`/`ROLLBACK` trong mọi nhánh lỗi. Không giữ transaction trong lúc chờ người dùng hoặc dịch vụ mạng.

### 5.3. Replication slot hoặc standby feedback giữ dữ liệu cũ

Replication slot được thiết kế để giữ WAL và/hoặc tuple cần thiết cho consumer. Nếu consumer ngừng hoạt động hoặc lag dài, slot có thể giữ `xmin` hoặc `catalog_xmin` cũ. Tương tự, `hot_standby_feedback` có thể giữ horizon cũ để giảm query conflict trên standby.

Hậu quả có thể gồm:

- Dead tuple không được loại bỏ dù autovacuum đã chạy.
- Table/index bloat tăng.
- Catalog row cũ tồn tại lâu hơn.
- WAL archive hoặc `pg_wal` tăng nếu slot giữ `restart_lsn` cũ.

Giải pháp là khôi phục consumer, xử lý lag, sửa pipeline CDC hoặc đánh giá lại chính sách feedback. Chỉ drop slot khi đã xác nhận consumer không còn cần nó và đã có kế hoạch tái tạo đồng bộ.

### 5.4. Không đủ autovacuum worker hoặc worker bị quá tải

`autovacuum_max_workers` giới hạn số worker có thể chạy đồng thời. Nếu nhiều bảng lớn cần vacuum, số worker thấp có thể khiến công việc xếp hàng. `autovacuum_naptime` ảnh hưởng tần suất launcher kiểm tra database.

Ngay cả khi đủ worker, chúng có thể bị giới hạn bởi cost delay, I/O, CPU hoặc storage throughput. Vacuum nhiều bảng cùng lúc có thể cạnh tranh với workload ứng dụng. Tăng worker hoặc tăng cost limit có thể cải thiện tốc độ nhưng cũng tăng tải I/O và ảnh hưởng latency của hệ thống.

### 5.5. Autovacuum bị vô hiệu hóa hoặc thống kê không hoạt động

Kiểm tra `autovacuum` và `track_counts`. Nếu autovacuum bị tắt, hoặc thống kê không được thu thập, các trigger thông thường có thể không hoạt động như mong đợi. Không nên tắt autovacuum để giảm tải production mà không có quy trình vacuum thủ công tương đương và theo dõi freeze chặt chẽ.

Một số bảng có storage parameter riêng có thể ghi đè cấu hình mặc định. Kiểm tra reloptions:

```sql
SELECT
    n.nspname,
    c.relname,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.reloptions IS NOT NULL
ORDER BY n.nspname, c.relname;
```

Chú ý các giá trị như `autovacuum_enabled=false`, scale factor rất cao hoặc threshold lớn. Không nên dựa vào giả định rằng một bảng bị tắt autovacuum sẽ luôn được bảo vệ như bảng thông thường ở mọi phiên bản; cần xác minh hành vi phiên bản đang dùng và không vô hiệu hóa bảo vệ freeze.

### 5.6. Vacuum bị chặn hoặc bị hủy

Vacuum thông thường có thể chạy song song với nhiều thao tác đọc/ghi, nhưng vẫn cần lock và có thể bị xung đột với một số DDL hoặc maintenance operation. Autovacuum cũng có thể bị hủy do lock conflict, worker crash hoặc quản trị viên terminate.

Kiểm tra log PostgreSQL để tìm thông báo worker bị cancel, lock timeout, lỗi I/O hoặc lỗi filesystem. Đối chiếu với `pg_stat_progress_vacuum`, `pg_stat_activity` và thời điểm DDL.

### 5.7. Bulk load và bảng insert-heavy

Một lần import hàng trăm triệu dòng có thể tạo lượng dữ liệu mới lớn trong thời gian ngắn. Với bảng ít update, trigger vacuum dựa trên dead tuple có thể không phản ánh nhu cầu freeze tuple mới. Cần xem insert-based vacuum threshold và kế hoạch chạy `VACUUM` sau bulk load nếu cần.

Sau một lần bulk load lớn, có thể chạy `ANALYZE` để cập nhật thống kê. Nếu bảng cần freeze sớm hoặc tuổi XID cao, cân nhắc `VACUUM (FREEZE, ANALYZE)` theo quy trình kiểm soát tài nguyên.

## 6. Quy trình xử lý khi nhận cảnh báo transaction ID

Khi log báo database phải vacuum trong một số lượng transaction còn lại, hãy coi đó là sự cố ưu tiên cao. Mục tiêu đầu tiên là xác định database và relation có tuổi XID lớn, đồng thời bảo đảm PostgreSQL có thể tiếp tục vacuum.

### 6.1. Bước 1 — Đánh giá mức độ khẩn cấp

1. Ghi nhận nguyên văn cảnh báo, thời điểm và major version PostgreSQL.
2. Chạy truy vấn tuổi XID ở tất cả database có thể kết nối.
3. Xếp hạng relation theo `age(relfrozenxid)`.
4. So sánh tuổi hiện tại với `autovacuum_freeze_max_age` và `vacuum_failsafe_age`.
5. Kiểm tra tốc độ tăng tuổi XID bằng nhiều mẫu theo thời gian.
6. Xác định hệ thống còn cho phép ghi và autovacuum worker có đang chạy không.

Có thể thiết lập ngưỡng cảnh báo nội bộ theo tỷ lệ phần trăm `autovacuum_freeze_max_age`, ví dụ cảnh báo sớm ở 50%, nâng mức ở 70% và critical ở 85%. Đây chỉ là điểm khởi đầu cho monitoring; cần hiệu chỉnh theo tốc độ phát sinh XID, khả năng vacuum và yêu cầu vận hành. Cảnh báo trực tiếp của PostgreSQL luôn cần được xử lý dù dashboard chưa chạm ngưỡng nội bộ.

### 6.2. Bước 2 — Kiểm tra autovacuum và worker

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;

SELECT
    pid,
    backend_type,
    datname,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE backend_type = 'autovacuum worker'
ORDER BY query_start;
```

Nếu không có worker, kiểm tra launcher, cấu hình, `track_counts`, log và quyền/giới hạn của managed service. Nếu worker có nhưng tiến độ chậm, xem phase, relation size, I/O latency và các session giữ snapshot cũ.

### 6.3. Bước 3 — Loại bỏ nguyên nhân giữ horizon

Kiểm tra transaction dài, prepared transaction, replication slot và standby feedback. Phối hợp với chủ sở hữu ứng dụng để kết thúc transaction bị bỏ quên. Khôi phục consumer của replication slot hoặc xử lý lag theo runbook.

Không drop slot, terminate session hoặc rollback prepared transaction một cách tự động chỉ dựa trên tuổi. Mỗi thao tác có thể gây mất đồng bộ hoặc rollback nghiệp vụ. Ghi nhận owner, lý do và tác động trước khi xử lý.

### 6.4. Bước 4 — Chạy vacuum freeze có kiểm soát

Nếu tuổi XID đã cao và autovacuum không kịp, DBA có thể chạy vacuum freeze thủ công trên relation ưu tiên:

```sql
VACUUM (FREEZE, VERBOSE) public.large_events;
```

`FREEZE` yêu cầu freeze tuple đủ điều kiện, giúp đưa tuổi XID của relation về mức an toàn hơn. Chạy ở đúng database chứa bảng. `VACUUM` không thể chạy bên trong transaction block, vì vậy không bọc lệnh trong `BEGIN`/`COMMIT`.

Với một database có nhiều bảng cần xử lý, có thể dùng `vacuumdb` từ máy quản trị:

```bash
vacuumdb \
  --all \
  --freeze \
  --jobs=2 \
  --verbose
```

Ví dụ trên chạy freeze vacuum trên các database có thể kết nối, với hai job song song. Chọn số job phù hợp với CPU, I/O, storage và tải production. Nếu đang xử lý một database cụ thể, giới hạn phạm vi thay vì chạy toàn cluster một cách thiếu kiểm soát. Với dịch vụ managed, lệnh hoặc quyền có thể bị giới hạn; làm theo hướng dẫn và kênh hỗ trợ của nhà cung cấp.

Không mặc định dùng `VACUUM FULL` để xử lý wraparound. `VACUUM FULL` viết lại table, cần lock mạnh và dung lượng đĩa bổ sung; nó có thể làm gián đoạn ứng dụng và không phải bước khẩn cấp đầu tiên để freeze XID. Vacuum thông thường hoặc `VACUUM (FREEZE)` phù hợp hơn cho mục tiêu chống wraparound.

### 6.5. Bước 5 — Theo dõi và xác nhận

Trong khi vacuum chạy, theo dõi:

- Tiến độ ở `pg_stat_progress_vacuum`.
- Tuổi `relfrozenxid` của relation ưu tiên và `datfrozenxid` của database.
- I/O latency, CPU, storage headroom và độ trễ truy vấn ứng dụng.
- Log về vacuum bị hủy, lỗi index, lỗi filesystem hoặc cảnh báo wraparound.
- Replication lag và WAL retention nếu có standby/slot.

Sau khi vacuum hoàn tất, chạy lại truy vấn tuổi XID. Xác nhận tuổi relation và database giảm hoặc được giữ dưới ngưỡng an toàn, không còn cảnh báo mới và autovacuum tiếp tục vận hành. Nếu tuổi database không giảm như dự kiến, kiểm tra relation khác có `relfrozenxid` cao hoặc catalog/TOAST table chưa được xử lý.

## 7. Tuning autovacuum để không tái diễn

Không có một bộ tham số tối ưu cho mọi bảng. Bảng nhỏ, bảng append-only, bảng update-heavy và partition lớn có hành vi khác nhau. Nên điều chỉnh dựa trên số liệu từng relation và đo tác động sau thay đổi.

### 7.1. Hạ ngưỡng vacuum cho bảng lớn, update-heavy

Ví dụ bảng `public.events` có hàng chục triệu dòng và thường xuyên cập nhật:

```sql
ALTER TABLE public.events SET (
    autovacuum_vacuum_threshold = 5000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 2000,
    autovacuum_analyze_scale_factor = 0.01
);
```

Các giá trị trên chỉ minh họa. Scale factor thấp làm vacuum chạy thường xuyên hơn, tránh chờ dead tuple tích tụ quá lớn. Threshold tuyệt đối giúp tránh vacuum quá dày trên bảng nhỏ. Phải cân nhắc số lần ghi, chi phí quét bảng, index và latency ứng dụng.

Để thay đổi trở lại mặc định kế thừa từ server:

```sql
ALTER TABLE public.events RESET (
    autovacuum_vacuum_threshold,
    autovacuum_vacuum_scale_factor,
    autovacuum_analyze_threshold,
    autovacuum_analyze_scale_factor
);
```

### 7.2. Cấu hình cho bảng insert-heavy

Với bảng chủ yếu insert, ít update/delete, xem xét insert-based vacuum:

```sql
ALTER TABLE public.audit_events SET (
    autovacuum_vacuum_insert_threshold = 10000,
    autovacuum_vacuum_insert_scale_factor = 0.05
);
```

Trigger này giúp freeze tuple mới trên bảng insert-heavy, tránh việc bảng chỉ được vacuum khi có nhiều dead tuple. Chọn giá trị theo kích thước bảng, lượng insert và yêu cầu tuổi XID.

### 7.3. Tăng năng lực worker

Các tham số cấp server thường được xem xét:

```conf
autovacuum = on
track_counts = on
autovacuum_max_workers = 5
autovacuum_naptime = 20s
autovacuum_vacuum_cost_limit = 2000
autovacuum_vacuum_cost_delay = 2ms
```

Đây là ví dụ để minh họa nhóm tham số, không phải cấu hình khuyến nghị chung. Tăng `autovacuum_max_workers` giúp xử lý nhiều relation song song nhưng cũng tăng cạnh tranh CPU, memory và I/O. Tăng cost limit hoặc giảm cost delay làm worker ít nghỉ hơn, có thể tăng tốc vacuum nhưng làm workload ứng dụng chậm đi.

`autovacuum_work_mem` điều khiển bộ nhớ làm việc cho worker khi thực hiện các bước cần lưu danh sách tuple/index. Cần đánh giá tổng memory khi nhiều worker chạy đồng thời. Một thay đổi có thể tốt cho một bảng nhưng gây áp lực cho toàn cluster.

Trong môi trường managed PostgreSQL, tham số thường được cấu hình qua parameter group hoặc API. Xác minh thay đổi nào cần restart, thay đổi nào có hiệu lực động và tham số nào bị nhà cung cấp giới hạn.

### 7.4. Tránh vacuum quá muộn và quá thường xuyên

Vacuum quá muộn làm dead tuple tích tụ, tăng thời gian mỗi lần vacuum và có thể đẩy tuổi XID tới vùng nguy hiểm. Vacuum quá thường xuyên lại tiêu tốn I/O, CPU và có thể làm giảm throughput ứng dụng.

Điều chỉnh bằng cách:

- Đặt scale factor thấp hơn cho bảng lớn và có churn cao.
- Giữ threshold hợp lý để bảng nhỏ không vacuum liên tục.
- Điều chỉnh insert threshold cho bảng append-only.
- Theo dõi `n_dead_tup`, `last_autovacuum`, table size và tuổi `relfrozenxid` theo thời gian.
- Phân vùng dữ liệu theo thời gian hoặc khóa nghiệp vụ nếu có thể giúp retention và maintenance dễ kiểm soát.
- Dùng batch update/delete có giới hạn thay vì một transaction khổng lồ.
- Dùng partition drop/detach cho retention khi mô hình dữ liệu cho phép, thay vì xóa hàng tỷ dòng rồi chờ vacuum.

### 7.5. Giảm bloat và churn ở tầng ứng dụng

Autovacuum không thể bù vô hạn cho thiết kế ghi dữ liệu kém hiệu quả. Một số cách giảm áp lực:

- Tránh cập nhật một cột thường xuyên nếu mỗi lần cập nhật tạo row version mới không cần thiết.
- Đặt fillfactor phù hợp cho bảng update-heavy để có chỗ cho HOT update khi điều kiện cho phép.
- Rà soát index không cần thiết vì mỗi update có thể phải duy trì nhiều index.
- Chia batch lớn thành transaction ngắn có checkpoint.
- Thiết kế retention và partition để loại bỏ dữ liệu cũ theo lô.
- Tránh giữ snapshot lâu trong báo cáo và job export.
- Giám sát replication slot và CDC consumer để không giữ xmin vô hạn.

## 8. Monitoring và cảnh báo chủ động

Nên giám sát cả sức khỏe autovacuum và nguy cơ wraparound. Chỉ giám sát CPU/disk không đủ phát hiện sớm.

### 8.1. Metric nên thu thập

| Metric | Nguồn | Mục đích |
|---|---|---|
| `age(datfrozenxid)` theo database | `pg_database` | Theo dõi nguy cơ XID wraparound ở cấp database. |
| `age(relfrozenxid)` theo relation | `pg_class` | Xác định bảng/catalog có tuổi cao nhất. |
| `n_dead_tup` | `pg_stat_all_tables` | Theo dõi dead tuple ước lượng. |
| `last_autovacuum`, `autovacuum_count` | `pg_stat_all_tables` | Theo dõi lịch sử vacuum tự động. |
| Worker đang chạy và phase | `pg_stat_progress_vacuum`, `pg_stat_activity` | Xác định công việc đang tiến triển hay bị kẹt. |
| Transaction age/backend xmin | `pg_stat_activity` | Phát hiện snapshot lâu và session giữ horizon. |
| Slot xmin/catalog_xmin/restart_lsn | `pg_replication_slots` | Phát hiện consumer giữ tuple hoặc WAL cũ. |
| WAL/archive và storage growth | `pg_stat_archiver`, hệ thống monitoring | Phát hiện archive thất bại hoặc dung lượng tăng bất thường. |
| MultiXact age | `pg_database`, `pg_class` và `mxid_age()` | Theo dõi rủi ro MultiXact riêng. |

### 8.2. Theo dõi tốc độ tăng tuổi XID

Một ảnh chụp tuổi XID cho biết mức hiện tại; hai hoặc nhiều mẫu theo thời gian cho biết tốc độ tăng. Có thể tính tốc độ gần đúng:

\[
\text{XID growth rate} =
\frac{\text{age}_{t2} - \text{age}_{t1}}{t2 - t1}
\]

Nếu tuổi tăng hàng triệu transaction mỗi giờ, thời gian còn lại trước ngưỡng có thể ngắn hơn dự kiến. Nên lưu lịch sử metric theo database và relation, đồng thời cảnh báo khi tốc độ tăng bất thường.

### 8.3. Ngưỡng cảnh báo

Một chính sách khởi đầu có thể gồm:

- **Warning**: tuổi XID đạt tỷ lệ đáng kể so với `autovacuum_freeze_max_age`, hoặc tăng nhanh qua nhiều chu kỳ.
- **High**: tuổi tăng liên tục, relation lớn không có autovacuum gần đây, worker thường xuyên bận hoặc có slot giữ xmin cũ.
- **Critical**: PostgreSQL phát cảnh báo phải vacuum trong số transaction còn lại, tuổi gần ngưỡng failsafe hoặc database không còn đủ headroom.

Không dùng một ngưỡng phần trăm duy nhất cho mọi hệ thống. Một database có tốc độ transaction cao cần cảnh báo sớm hơn vì thời gian thực tế tới ngưỡng có thể ngắn. Cảnh báo log của PostgreSQL phải được chuyển tới hệ thống alerting ngay.

### 8.4. Ghi log autovacuum

Có thể bật log cho vacuum chạy lâu bằng tham số:

```conf
log_autovacuum_min_duration = 1s
```

Giá trị nhỏ giúp quan sát chi tiết hơn nhưng có thể tạo nhiều log. `0` ghi mọi lần autovacuum; `-1` tắt log theo ngưỡng này. Hãy chọn theo volume log và chính sách lưu giữ. Một số dịch vụ managed cho phép xem log qua console hoặc export sang hệ thống log riêng.

Log vacuum có thể cung cấp thông tin số tuple được xử lý, dead tuple còn lại, buffer và thời gian. Dùng nó để phân biệt worker đang làm việc hiệu quả với worker liên tục bị cancel hoặc xử lý rất ít dữ liệu.

## 9. Những lỗi xử lý thường gặp

| Cách xử lý sai | Vì sao nguy hiểm | Hướng xử lý phù hợp |
|---|---|---|
| Tắt autovacuum để giảm I/O | Dead tuple và tuổi XID có thể tích tụ tới mức nguy hiểm | Giữ autovacuum bật; tune theo bảng và theo dõi worker. |
| Chỉ nhìn `n_dead_tup` | Không phản ánh trực tiếp tuổi XID hoặc freeze horizon | Theo dõi thêm `age(datfrozenxid)` và `age(relfrozenxid)`. |
| Tăng `autovacuum_freeze_max_age` để trì hoãn cảnh báo | Chỉ kéo dài khoảng thời gian trước vacuum, không giải quyết worker bị tụt | Tìm nguyên nhân vacuum không theo kịp; không nâng ngưỡng như biện pháp chữa cháy. |
| Chạy `VACUUM FULL` ngay khi thấy wraparound warning | Lock mạnh, rewrite table và cần dung lượng bổ sung | Ưu tiên `VACUUM (FREEZE)` có kiểm soát. |
| Drop mọi replication slot không active | Có thể làm mất khả năng tiếp tục replication/CDC | Xác định consumer và kế hoạch rebuild trước khi drop. |
| Kill mọi transaction lâu | Có thể rollback giao dịch nghiệp vụ hoặc gây lỗi ứng dụng | Xác định owner, snapshot và tác động rồi xử lý theo runbook. |
| Tăng worker/cost limit tối đa | Có thể làm storage và ứng dụng quá tải | Thử tăng dần, theo dõi latency và I/O. |
| Chỉ vacuum một bảng người dùng | Database age còn phụ thuộc các relation khác, kể cả catalog và TOAST | Xếp hạng toàn bộ relation và database. |
| Cho rằng vacuum đã chạy là XID đã an toàn | Worker có thể chưa quét relation hoặc bị giới hạn bởi horizon | Đo lại `relfrozenxid`/`datfrozenxid` sau khi hoàn tất. |
| Xử lý cảnh báo bằng cách restart PostgreSQL | Restart không tự freeze tuple và có thể kéo dài gián đoạn | Chẩn đoán và thực hiện vacuum theo quy trình. |

## 10. Runbook tham khảo cho sự cố autovacuum lag

Runbook dưới đây là khung thao tác; điều chỉnh theo major version, quyền và môi trường triển khai.

### Giai đoạn A — Triage

1. Thu thập log cảnh báo và thời điểm bắt đầu.
2. Chạy truy vấn tuổi XID trên tất cả database.
3. Xếp hạng relation theo `age(relfrozenxid)` và kích thước.
4. Xem worker đang chạy, phase và tốc độ tiến triển.
5. Kiểm tra transaction dài, prepared transaction, replication slot và standby feedback.
6. Kiểm tra `pg_wal`, archive, storage headroom, CPU và I/O.

### Giai đoạn B — Khôi phục khả năng vacuum

1. Kết thúc transaction bị bỏ quên sau khi xác nhận với owner.
2. Khôi phục hoặc xử lý consumer đang giữ replication slot.
3. Sửa cấu hình autovacuum hoặc thống kê nếu bị tắt/sai.
4. Nếu cần, chạy `VACUUM (FREEZE, VERBOSE)` trên relation tuổi cao nhất theo thứ tự ưu tiên.
5. Giới hạn số job và theo dõi ảnh hưởng tới workload.
6. Với managed PostgreSQL, liên hệ nhà cung cấp nếu không có quyền cần thiết hoặc dịch vụ tự quản lý anti-wraparound vacuum.

### Giai đoạn C — Xác nhận

1. Đo lại tuổi XID ở cấp relation và database.
2. Xác nhận cảnh báo wraparound không tiếp tục xuất hiện.
3. Xác nhận worker và lịch vacuum hoạt động bình thường.
4. Kiểm tra dead tuple, bloat, replication lag và WAL retention.
5. Theo dõi xu hướng trong nhiều chu kỳ để chắc chắn tuổi XID không tăng trở lại.
6. Ghi nguyên nhân gốc, hành động khắc phục và owner.

### Giai đoạn D — Phòng ngừa tái diễn

1. Đặt cảnh báo tuổi XID và tốc độ tăng theo database.
2. Tune scale factor/threshold cho bảng lớn hoặc write-heavy.
3. Điều chỉnh worker/cost dựa trên năng lực I/O.
4. Đặt timeout và quy tắc transaction cho ứng dụng.
5. Giám sát replication slot, prepared transaction và standby feedback.
6. Kiểm tra autovacuum sau mỗi lần nâng cấp, migration hoặc thay đổi workload.

## 11. Lưu ý khi vận hành trên managed PostgreSQL

Với dịch vụ PostgreSQL được quản lý, nhà cung cấp có thể kiểm soát autovacuum launcher, quyền superuser, parameter group và một số thao tác maintenance. Cần xác minh:

- Có thể xem log autovacuum và `pg_stat_progress_vacuum` không.
- Có thể chạy `VACUUM (FREEZE)` thủ công không.
- Có giới hạn về worker, cost limit, `autovacuum_freeze_max_age` hoặc tham số freeze không.
- Provider có tự thực hiện anti-wraparound vacuum hoặc cảnh báo qua monitoring riêng không.
- Có cách yêu cầu hỗ trợ khẩn cấp khi transaction ID age tăng nhanh không.
- Replication slot do dịch vụ tạo có thể được quản lý bằng SQL hay chỉ qua API.

Không giả định rằng provider sẽ tự xử lý mọi tình huống. Chủ sở hữu database vẫn cần theo dõi tuổi XID và hiểu quy trình escalation. Nếu dịch vụ không cho phép can thiệp vào một worker đang bị kẹt, hãy cung cấp cho nhà cung cấp database name, relation, tuổi XID, log, transaction lâu và thông tin slot để họ điều tra.

## 12. Kết luận

Autovacuum giữ cho PostgreSQL hoạt động ổn định bằng cách dọn dead tuple, cập nhật thống kê và freeze transaction ID cũ. Khi autovacuum không theo kịp, cần điều tra cả tốc độ phát sinh dữ liệu, transaction dài, replication slot, worker capacity, I/O và cấu hình từng bảng. Cảnh báo transaction ID là tín hiệu ưu tiên cao vì wraparound có thể khiến PostgreSQL từ chối cấp XID mới để bảo vệ tính toàn vẹn dữ liệu.

Quy trình xử lý đáng tin cậy bắt đầu bằng việc đo `age(datfrozenxid)` và `age(relfrozenxid)`, tìm relation cũ nhất, xác định horizon bị giữ, khôi phục năng lực vacuum và chạy freeze vacuum có kiểm soát khi cần. Sau sự cố, phải tune ngưỡng theo workload, giám sát xu hướng tuổi XID và ngăn transaction/slot giữ snapshot quá lâu. Không tắt autovacuum hoặc trì hoãn cảnh báo bằng cách tăng ngưỡng như một giải pháp thay thế cho việc xử lý nguyên nhân.

## Tài liệu tham khảo

- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [PostgreSQL — Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html)
- [PostgreSQL — VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html)
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — System Catalogs: pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html)
- [PostgreSQL — System Catalogs: pg_database](https://www.postgresql.org/docs/current/catalog-pg-database.html)
- [PostgreSQL — Replication Slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html)
