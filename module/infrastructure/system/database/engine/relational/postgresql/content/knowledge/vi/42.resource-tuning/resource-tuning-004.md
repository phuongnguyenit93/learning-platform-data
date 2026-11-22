# maintenance_work_mem và bộ nhớ phục vụ bảo trì trong PostgreSQL

## 1. Vai trò của maintenance_work_mem

PostgreSQL dùng bộ nhớ cho nhiều hoạt động khác nhau. Query thông thường sử dụng `work_mem` cho các thao tác sort/hash; `shared_buffers` giữ database pages; còn các hoạt động bảo trì như VACUUM và tạo index có thể dùng một giới hạn riêng là **`maintenance_work_mem`**.

`maintenance_work_mem` quy định lượng bộ nhớ tối đa mà một maintenance operation có thể sử dụng. Các thao tác điển hình gồm VACUUM, CREATE INDEX và một số thao tác ALTER TABLE cần xử lý dữ liệu/constraint. Tùy command và PostgreSQL version, các operation như REINDEX, CLUSTER hoặc VACUUM FULL cũng có thể dùng vùng memory này cho các bước liên quan.

Giá trị lớn hơn có thể giúp:
- VACUUM giữ được nhiều dead tuple identifiers trong memory trước khi phải xử lý theo nhiều lượt.
- CREATE INDEX/REINDEX xử lý dữ liệu và sort hiệu quả hơn, giảm spill ra temporary files trong trường hợp phù hợp.
- Một số thao tác bảo trì/validation hoàn thành nhanh hơn.

Nhưng đặt giá trị quá lớn có thể làm nhiều maintenance jobs đồng thời tranh chấp RAM. `maintenance_work_mem` là giới hạn theo operation, không phải một ngân sách tổng cho toàn server. Vì vậy phải tính cả số thao tác thủ công, autovacuum workers, query workload và memory dành cho hệ điều hành.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `maintenance_work_mem` dùng cho loại công việc nào.
2. Phân biệt `maintenance_work_mem` với `work_mem`, `shared_buffers`, `temp_buffers` và `effective_cache_size`.
3. Hiểu vai trò của `autovacuum_work_mem` và quan hệ với `maintenance_work_mem`.
4. Ước lượng tổng memory demand khi nhiều maintenance operations chạy đồng thời.
5. Điều chỉnh memory cho VACUUM, CREATE INDEX và REINDEX.
6. Theo dõi vacuum/index progress và nhận diện dấu hiệu thiếu memory.
7. Phân biệt memory pressure với I/O bottleneck hoặc lock contention.
8. Cấu hình setting ở server, role, session và transaction scope.
9. Thiết kế maintenance windows và concurrency budgets.
10. Thực hành tuning trong môi trường lab và xác minh kết quả.

### 1.2. Nguyên tắc quan trọng

- `maintenance_work_mem` là giới hạn tối đa cho từng maintenance operation, không phải lượng RAM luôn được cấp phát ngay.
- Nhiều maintenance operations đồng thời có thể cùng tiêu thụ memory.
- Autovacuum có setting riêng `autovacuum_work_mem`; giá trị `-1` nghĩa là dùng `maintenance_work_mem`.
- Số autovacuum workers có thể làm tổng memory demand tăng theo concurrency.
- Tăng memory không sửa được mọi bottleneck: storage chậm, lock waits, stale statistics hoặc query plan kém vẫn cần xử lý riêng.
- Không tính `maintenance_work_mem` như giới hạn duy nhất; cần cộng `work_mem`, `shared_buffers`, backend memory và OS headroom.
- Đo trước/sau trên workload đại diện, tránh thay đổi production dựa trên một lần chạy.

---

## 2. Maintenance operations dùng bộ nhớ

### 2.1. VACUUM

VACUUM thường xuyên tìm và xử lý dead tuples để giữ table/index khỏe mạnh, cho phép tái sử dụng không gian và hỗ trợ transaction ID maintenance. Trong quá trình này, PostgreSQL cần theo dõi các tuple đã được xác định là có thể cleanup.

`maintenance_work_mem` giới hạn memory dành cho hoạt động VACUUM thủ công. Nếu vùng memory không đủ để giữ tập dead tuple identifiers trong một lượt, VACUUM có thể phải thực hiện nhiều chu kỳ index cleanup hơn. Điều đó làm tăng số lần quét index và I/O.

Điều này không có nghĩa VACUUM sẽ dừng hoặc bỏ qua dead tuples chỉ vì memory thấp. Nó có thể xử lý theo batches/multiple cycles, nhưng chi phí I/O và thời gian có thể tăng.

### 2.2. Autovacuum

Autovacuum là các background workers tự động VACUUM/ANALYZE tables theo thresholds và configuration. Nó dùng `autovacuum_work_mem` làm giới hạn memory cho mỗi worker.

- `autovacuum_work_mem = -1`: dùng giá trị `maintenance_work_mem`.
- Giá trị dương: dùng giới hạn riêng được cấu hình cho autovacuum.
- Nhiều autovacuum workers có thể chạy đồng thời; tổng memory demand không bằng một worker đơn lẻ.

Đừng tăng `maintenance_work_mem` mà quên rằng `autovacuum_work_mem=-1` có thể khiến autovacuum workers kế thừa mức mới.

### 2.3. CREATE INDEX

CREATE INDEX cần đọc dữ liệu và xây dựng index structure. Nhiều index builds dùng sort-based process; bộ nhớ đủ lớn có thể giảm nhu cầu external sorting/temporary files và cải thiện thời gian build.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer_created
ON app.orders (customer_id, created_at DESC);
~~~

Nếu index build là operation lớn, session có thể được cấp `maintenance_work_mem` cao hơn trong thời gian chạy. Tuy nhiên, memory không thay thế được I/O throughput, CPU và lock planning.

### 2.4. REINDEX

REINDEX xây dựng lại index. Nó có thể cần memory cho quá trình build tương tự CREATE INDEX. Trước khi chạy:
- Ước lượng số lượng và kích thước indexes.
- Kiểm tra disk headroom cho index mới/temporary files.
- Kiểm tra locks và write impact.
- Chọn REINDEX thường hay CONCURRENTLY theo availability requirement.
- Điều chỉnh memory trong session bảo trì.

### 2.5. ALTER TABLE và foreign key validation

Một số thao tác ALTER TABLE, chẳng hạn thêm foreign key, cần quét dữ liệu để xác minh constraint. `maintenance_work_mem` có thể ảnh hưởng đến một số bước bảo trì/validation theo command/version.

Không giả định mọi ALTER TABLE đều dùng setting này. Một số thao tác chủ yếu bị giới hạn bởi lock acquisition, table rewrite hoặc I/O.

### 2.6. CLUSTER và VACUUM FULL

Các thao tác rewrite table như CLUSTER hoặc VACUUM FULL có thể cần memory cho bước xây dựng lại indexes hoặc các xử lý liên quan. Nhưng thời gian và tài nguyên thường bị chi phối đáng kể bởi việc đọc/ghi lại table, index và lock requirements.

Tăng `maintenance_work_mem` không làm biến mất yêu cầu disk space cho bản rewrite và không loại bỏ lock impact của VACUUM FULL.

### 2.7. Dump restore và maintenance

Các quy trình restore có thể tạo nhiều indexes/constraints sau khi nạp dữ liệu. `pg_restore` có thể chạy nhiều jobs đồng thời; mỗi job có thể khởi chạy maintenance commands riêng. Vì vậy cần tính concurrency của restore jobs khi chọn `maintenance_work_mem`.

### 2.8. Bảng tóm tắt

| Operation | Vai trò của maintenance memory | Điều cần theo dõi |
|---|---|---|
| VACUUM | Theo dõi dead tuple identifiers và cleanup batches | Vacuum cycles, I/O, dead tuples |
| Autovacuum | Dùng `autovacuum_work_mem` hoặc kế thừa setting | Worker count, table churn |
| CREATE INDEX | Memory cho index build/sort | Build duration, temp files, I/O |
| REINDEX | Memory cho rebuild | Index size, locks, disk headroom |
| ALTER TABLE ADD FOREIGN KEY | Hỗ trợ bước validation theo implementation | Scan time, lock wait |
| CLUSTER/VACUUM FULL | Có thể dùng cho bước index/build liên quan | Rewrite I/O, lock, free space |
| pg_restore | Nhiều index/constraint jobs có thể chạy song song | Job count, aggregate memory |

---

## 3. Phân biệt các memory settings

### 3.1. maintenance_work_mem

Dành cho maintenance operations. Nó không phải memory limit của mọi SQL query và không thay thế `work_mem`.

~~~sql
SHOW maintenance_work_mem;
~~~

### 3.2. autovacuum_work_mem

Dành riêng cho mỗi autovacuum worker. Khi đặt `-1`, worker dùng `maintenance_work_mem`.

~~~sql
SHOW autovacuum_work_mem;
SHOW autovacuum_max_workers;
~~~

### 3.3. work_mem

`work_mem` là giới hạn memory cho các thao tác query như sort và hash operations trước khi cần spill ra disk. Một query có thể có nhiều sort/hash nodes; nhiều queries chạy đồng thời; vì vậy tổng usage có thể lớn hơn `work_mem` rất nhiều lần.

Một hash operation còn có thể dùng `hash_mem_multiplier` theo version/configuration. Không cộng `work_mem` chỉ một lần cho mỗi connection khi lập ngân sách.

### 3.4. shared_buffers

`shared_buffers` là vùng shared memory PostgreSQL dùng làm cache database pages. Đây là vùng memory server-level, khác với giới hạn theo operation của `maintenance_work_mem`.

### 3.5. temp_buffers

`temp_buffers` là memory buffers dùng cho temporary tables trong mỗi session. Nó không phải vùng sort/hash và cũng không phải maintenance memory.

### 3.6. effective_cache_size

`effective_cache_size` là ước lượng cho planner về lượng cache có thể dùng bởi một query, bao gồm PostgreSQL shared buffers và filesystem cache. Nó không cấp phát RAM và không phải memory limit.

### 3.7. So sánh

| Setting | Phục vụ | Phạm vi chính | Có cấp phát toàn bộ ngay không? |
|---|---|---|---|
| `maintenance_work_mem` | VACUUM/index/maintenance | Từng maintenance operation | Không |
| `autovacuum_work_mem` | Autovacuum | Từng autovacuum worker | Không |
| `work_mem` | Sort/hash query operations | Từng operation trong query | Không |
| `shared_buffers` | Cache database pages | Shared server memory | Được reserve/allocate theo startup |
| `temp_buffers` | Temporary tables | Từng session | Theo nhu cầu/session |
| `effective_cache_size` | Planner estimate | Ước lượng toàn hệ thống | Không cấp phát |

### 3.8. Ví dụ không nên nhầm

Giả sử:
- `maintenance_work_mem = 1GB`.
- `work_mem = 32MB`.
- `shared_buffers = 8GB`.
- `effective_cache_size = 24GB`.

Điều đó không có nghĩa server chỉ cần 9.032 MB RAM. Query operations, autovacuum, backend overhead, OS cache và các process khác có thể cần thêm nhiều memory. `effective_cache_size` không cấp phát 24GB; nó chỉ là planner estimate.

---

## 4. Phạm vi setting và concurrency

### 4.1. Một operation, không phải toàn server

`maintenance_work_mem` áp dụng cho một maintenance command/operation. Nếu ba sessions cùng chạy ba CREATE INDEX hoặc VACUUM operations, mỗi operation có thể dùng tới giới hạn của nó.

Không coi setting là một pool duy nhất mà các sessions tự chia nhau.

### 4.2. Parallel maintenance

Một số maintenance commands có thể dùng parallel workers. Cách áp dụng memory limit cho command và workers được PostgreSQL quản lý theo semantics của từng operation/version; không tự nhân `maintenance_work_mem` với số parallel workers nếu tài liệu version nói memory budget áp dụng cho toàn command.

Ngược lại, nhiều maintenance commands độc lập chạy song song vẫn có thể tạo nhiều budget đồng thời. Phân biệt parallel workers của một command với nhiều commands/sessions khác nhau.

### 4.3. Autovacuum workers

Nếu `autovacuum_work_mem=-1`, mỗi worker dùng giới hạn `maintenance_work_mem`. Ví dụ cấu hình:
- `maintenance_work_mem = 512MB`.
- `autovacuum_max_workers = 5`.
- `autovacuum_work_mem = -1`.

Một ngân sách bảo thủ cho phần autovacuum có thể tính tới khoảng 5 × 512MB, dù các workers không nhất thiết đều tiêu thụ hết giới hạn cùng lúc.

### 4.4. Manual maintenance concurrency

Ví dụ:
- Hai index builds thủ công, mỗi operation có giới hạn 2GB.
- Ba autovacuum workers, mỗi worker có giới hạn 512MB.
- Một VACUUM thủ công với giới hạn 2GB.

Ngân sách cực đại bảo thủ cho các giới hạn này là 2 × 2GB + 3 × 512MB + 2GB, chưa kể query workload và OS. Thực tế usage có thể thấp hơn, nhưng đây là phép tính hữu ích để tránh overcommit.

### 4.5. pg_restore jobs

`pg_restore -j N` có thể chạy nhiều restore jobs song song. Nếu jobs đồng thời tạo indexes hoặc constraints, memory demand tăng theo số maintenance operations thực sự chạy, không chỉ theo số database connections.

Lập kế hoạch job count và memory setting cùng nhau. Một restore chạy 8 jobs với maintenance memory lớn có thể làm host hết RAM dù từng job riêng lẻ hoạt động tốt.

### 4.6. VACUUM thủ công và autovacuum

Nếu DBA chạy VACUUM thủ công trong khi autovacuum đang xử lý các tables khác, hai nhóm hoạt động có thể đồng thời dùng memory. Kiểm tra `pg_stat_activity`, `pg_stat_progress_vacuum` và worker count trước khi khởi động thêm maintenance.

### 4.7. Memory budget bảo thủ

Một công thức lập kế hoạch:

~~~text
Total RAM budget
  >= shared_buffers
   + concurrent manual maintenance operations * maintenance_work_mem
   + autovacuum workers * autovacuum_work_mem
   + concurrent query operations * work_mem/hash allowance
   + backend/process overhead
   + OS and filesystem cache headroom
   + monitoring/agent/other services
~~~

Đây là phép ước lượng giới hạn bảo thủ, không phải dự báo usage chính xác. Cần đo RSS/cgroup memory trên workload đại diện và giữ headroom cho spike.

### 4.8. Không overcommit theo tổng giá trị cấu hình

Không phải mọi operation luôn dùng hết limit, nhưng OOM thường xảy ra khi nhiều workloads cùng tăng memory trong cùng thời điểm. Ngân sách phải xét peak concurrency, maintenance windows, restore jobs và workload bursts.

---

## 5. VACUUM memory và dead tuple tracking

### 5.1. Dead tuples

UPDATE/DELETE tạo ra tuple versions cũ. Khi không còn transaction snapshot nào cần chúng, VACUUM có thể đánh dấu không gian có thể tái sử dụng và xử lý index entries tương ứng.

VACUUM cần giữ thông tin về dead tuple identifiers trong quá trình cleanup. Memory limit ảnh hưởng số lượng identifiers có thể xử lý trong một lượt.

### 5.2. Memory thấp

Nếu memory không đủ cho tập dead tuples:
- VACUUM có thể chia cleanup thành nhiều cycles.
- Indexes có thể phải được xử lý nhiều lần.
- I/O tăng.
- Vacuum duration có thể dài hơn.
- Table/index cleanup vẫn tiến triển theo cơ chế phù hợp.

Tăng `maintenance_work_mem` có thể giúp một số bảng có churn cao, nhưng phải cân nhắc RAM và concurrency.

### 5.3. Memory cao

Memory cao hơn có thể cho phép xử lý nhiều dead tuple identifiers trong một lượt. Tuy nhiên, nếu bottleneck là disk throughput, lock contention, long-running transactions hoặc vacuum cost delay, tăng memory có thể không cải thiện đáng kể.

### 5.4. Autovacuum riêng

Nếu `autovacuum_work_mem` có giá trị dương, thay đổi `maintenance_work_mem` không tự làm autovacuum workers dùng giá trị mới. Kiểm tra cả hai:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_settings
WHERE name IN (
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'autovacuum_max_workers'
);
~~~

### 5.5. Theo dõi vacuum progress

~~~sql
SELECT
    p.pid,
    a.datname,
    p.relid::regclass AS relation_name,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    p.max_dead_tuples,
    p.num_dead_tuples,
    a.query
FROM pg_stat_progress_vacuum AS p
JOIN pg_stat_activity AS a
    ON a.pid = p.pid;
~~~

Các progress columns thay đổi theo major version. `max_dead_tuples` và `num_dead_tuples` hữu ích để hiểu dead tuple tracking khi chúng có mặt, nhưng không phải mọi version đều có cùng schema.

### 5.6. Phân biệt memory với vacuum delay

VACUUM có cost-based delay để giới hạn I/O pressure. Nếu vacuum chậm do cost delay, tăng `maintenance_work_mem` không nhất thiết giải quyết. Xem `autovacuum_vacuum_cost_limit`, `autovacuum_vacuum_cost_delay` và các per-table storage parameters.

### 5.7. Long-running transactions

Transaction/snapshot cũ có thể ngăn VACUUM loại bỏ dead tuples. Khi đó tăng memory không giải quyết được nguyên nhân gốc. Kiểm tra `backend_xmin`, `xact_start`, replication slots và prepared transactions theo bối cảnh.

### 5.8. Vacuum không phải VACUUM FULL

VACUUM thường không rewrite toàn bộ table; nó làm không gian có thể tái sử dụng. VACUUM FULL rewrite table và cần lock mạnh, thêm disk space và thời gian. Tăng maintenance memory không loại bỏ các yêu cầu đó.

---

## 6. CREATE INDEX và REINDEX memory

### 6.1. Index build cần memory

Index build thường phải đọc rows và sắp xếp keys. Nếu dữ liệu lớn hơn vùng memory khả dụng, PostgreSQL có thể dùng external sort/temporary files. Tăng `maintenance_work_mem` có thể giảm spill trong trường hợp sort là bottleneck.

### 6.2. Cấu hình riêng cho session bảo trì

Có thể đặt mức cao hơn trong session DBA:

~~~sql
SET maintenance_work_mem = '2GB';

CREATE INDEX idx_orders_created_at
ON app.orders (created_at);

RESET maintenance_work_mem;
~~~

Cần bảo đảm host còn đủ RAM và không có nhiều jobs tương tự chạy đồng thời.

### 6.3. CREATE INDEX CONCURRENTLY

`CREATE INDEX CONCURRENTLY` giảm mức blocking writes so với CREATE INDEX thông thường nhưng có nhiều phase và có thể chạy lâu hơn. Nó vẫn cần memory cho index build và có yêu cầu về transaction context khác.

~~~sql
SET maintenance_work_mem = '1GB';

CREATE INDEX CONCURRENTLY idx_orders_customer
ON app.orders (customer_id);

RESET maintenance_work_mem;
~~~

Không chạy CREATE INDEX CONCURRENTLY bên trong transaction block. Nếu command thất bại, có thể để lại invalid index cần xử lý theo runbook.

### 6.4. Theo dõi index build

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    lockers_total,
    lockers_done,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
~~~

Các cột/phase thay đổi theo version và command. View này giúp biết build đang ở phase nào, không trực tiếp cho biết memory đã dùng bao nhiêu.

### 6.5. Temporary files

Nếu index build dùng external sorting, temp files có thể được tạo. `log_temp_files` có thể giúp phát hiện temporary files theo threshold. Tuy nhiên, temp files còn được tạo bởi query sorts/hashes; phải correlate với PID/time/operation để xác định nguồn.

### 6.6. REINDEX CONCURRENTLY

REINDEX CONCURRENTLY có nhiều phase và yêu cầu disk space bổ sung. Memory tuning có thể cải thiện build phase, nhưng không loại bỏ yêu cầu storage và lock coordination. Kiểm tra invalid indexes và progress sau failure.

### 6.7. Chọn mức memory

Đừng đặt `maintenance_work_mem` lên nhiều GB chỉ vì index build chậm. Trước hết xem:
- Index size và table size.
- Build duration theo phase.
- Temp file size.
- Storage throughput/latency.
- CPU utilization.
- Số build concurrent.
- Free memory/cgroup pressure.

Nếu storage là bottleneck, tăng memory có thể không giúp.

---

## 7. Cấu hình maintenance_work_mem

### 7.1. Kiểm tra giá trị hiện tại

~~~sql
SHOW maintenance_work_mem;
SHOW autovacuum_work_mem;

SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'autovacuum_max_workers'
);
~~~

`setting` thường được hiển thị theo đơn vị nội bộ; dùng `unit` để hiểu giá trị. `context` cho biết phạm vi thay đổi; không suy đoán reload/restart chỉ từ tên setting.

### 7.2. SET ở session

~~~sql
SET maintenance_work_mem = '1GB';
SHOW maintenance_work_mem;

CREATE INDEX idx_events_created_at
ON app.events (created_at);

RESET maintenance_work_mem;
~~~

Session-level SET phù hợp cho một maintenance session. Nếu command thất bại trước RESET, connection có thể vẫn giữ setting; trong automation, đảm bảo reset hoặc đóng connection.

### 7.3. SET LOCAL

`SET LOCAL` chỉ có hiệu lực tới hết transaction:

~~~sql
BEGIN;
SET LOCAL maintenance_work_mem = '512MB';

CREATE INDEX idx_events_type
ON app.events (event_type);

COMMIT;
~~~

Chỉ dùng khi command được phép chạy trong transaction block. Một số commands như VACUUM và CREATE INDEX CONCURRENTLY không được chạy trong transaction block; khi đó cần session-level SET.

### 7.4. ALTER ROLE

Có thể gán default theo role:

~~~sql
ALTER ROLE maintenance_operator
SET maintenance_work_mem = '1GB';
~~~

Setting áp dụng khi role mở session mới. Nó không tự thay đổi các sessions đang tồn tại. Cần kiểm soát role và connection pool để tránh cấp memory cao cho mọi session của user.

### 7.5. ALTER DATABASE

Có thể đặt default theo database:

~~~sql
ALTER DATABASE analytics
SET maintenance_work_mem = '768MB';
~~~

Đây là setting default cho sessions mới vào database đó. Cân nhắc số lượng maintenance users/jobs và không xem database-level default là global memory cap.

### 7.6. ALTER SYSTEM

Thay đổi server default:

~~~sql
ALTER SYSTEM SET maintenance_work_mem = '512MB';
SELECT pg_reload_conf();

SHOW maintenance_work_mem;
~~~

Sau reload, kiểm tra giá trị hiệu lực trong session mới và source trong `pg_settings`. ALTER SYSTEM ghi vào `postgresql.auto.conf`; nếu configuration management cũng quản lý setting này, tránh tạo hai nguồn thay đổi cạnh tranh.

### 7.7. Thay đổi autovacuum_work_mem

`autovacuum_work_mem` thường được quản lý qua cấu hình server và có context riêng. Kiểm tra `pg_settings.context` để biết có cần reload/restart hay không trên version đang chạy. Khi đặt giá trị dương, lập ngân sách độc lập với `maintenance_work_mem`.

### 7.8. Xác nhận cấu hình file

Có thể xem file settings và lỗi parse:

~~~sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE name IN (
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'autovacuum_max_workers'
)
ORDER BY seqno;
~~~

Quyền đọc catalog/configuration có thể bị giới hạn. Không xuất toàn bộ file settings nếu có secret hoặc thông tin môi trường nhạy cảm.

### 7.9. Tránh thay đổi toàn server khi chỉ cần một job

Nếu một index build lớn cần memory cao, session-level SET thường giới hạn phạm vi tốt hơn ALTER SYSTEM. Chỉ tăng default toàn server khi workload maintenance thường xuyên cần và memory budget đã được tính.

---

## 8. Lập memory budget cho maintenance

### 8.1. Các thành phần

Khi lập ngân sách, tính:
- `shared_buffers`.
- Số maintenance operations thủ công chạy đồng thời.
- `maintenance_work_mem` của từng operation.
- Số autovacuum workers và `autovacuum_work_mem`.
- Query `work_mem` theo số sort/hash operations đồng thời.
- Backend/process memory.
- Extension memory và connection pool overhead.
- OS/filesystem cache.
- Monitoring agents và các services cùng host.

### 8.2. Ví dụ ngân sách

Giả sử host có 64GB RAM:
- Shared buffers: 16GB.
- Hai maintenance operations, mỗi operation giới hạn 2GB: 4GB.
- Bốn autovacuum workers, mỗi worker giới hạn 512MB: 2GB.
- Query workload/other backend memory: 12GB dự toán.
- OS, filesystem cache và agents: 12GB dự toán.

Tổng các phần đã dự toán là 46GB; phần còn lại là headroom cho biến động. Đây chỉ là ví dụ; cần đo RSS/cgroup memory và peak workload thực tế.

### 8.3. Công thức concurrency

~~~text
Maintenance peak allowance
  = manual_operation_count * maintenance_work_mem
  + autovacuum_worker_count * autovacuum_work_mem
~~~

Nếu `autovacuum_work_mem=-1`, thay nó bằng giá trị `maintenance_work_mem`. Không cộng số parallel workers của một command một cách máy móc; kiểm tra semantics của version/command.

### 8.4. Kịch bản restore

Một restore có thể chạy nhiều CREATE INDEX đồng thời. Nếu mỗi operation được cấp 2GB và 6 jobs chạy cùng lúc, ngân sách bảo thủ cho nhóm đó là 12GB. Cộng thêm autovacuum, query workload và OS.

Giảm `pg_restore -j` có thể là cách kiểm soát memory tốt hơn việc giảm maintenance memory xuống quá thấp.

### 8.5. Kịch bản autovacuum burst

Nhiều tables cùng vượt vacuum threshold có thể khiến nhiều workers chạy đồng thời. Nếu mỗi worker được phép dùng nhiều memory, peak usage tăng. Điều chỉnh:
- `autovacuum_max_workers`.
- `autovacuum_work_mem`.
- Vacuum thresholds/scale factors.
- Cost delay/limit.
- Table-level storage parameters.
- Workload write rate và maintenance windows.

### 8.6. Headroom

Không phân bổ 100% RAM theo các giới hạn lý thuyết. Giữ headroom cho:
- Burst query memory.
- Backup/restore tools.
- OS page cache.
- Kernel memory.
- Connection spikes.
- Monitoring/agents.
- Memory fragmentation và process overhead.

### 8.7. OOM risk

Nếu hệ điều hành hoặc cgroup OOM killer kết thúc PostgreSQL backend/process, có thể gây query failures, transaction rollback hoặc thậm chí ảnh hưởng server tùy process bị chọn. Theo dõi kernel/cgroup OOM events và memory pressure; đừng chỉ nhìn PostgreSQL logs.

---

## 9. Monitoring maintenance operations

### 9.1. Current settings

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'autovacuum_max_workers',
    'work_mem',
    'shared_buffers'
)
ORDER BY name;
~~~

Đây là cách xác nhận setting đang hiệu lực trong server/session hiện tại. Một session có thể override server default; hãy kiểm tra bằng connection/role thực sự chạy maintenance.

### 9.2. Autovacuum workers đang chạy

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE backend_type = 'autovacuum worker'
ORDER BY query_start;
~~~

`backend_type` có trên các major versions mới; với version cũ, lọc theo query/process details và đối chiếu monitoring docs.

### 9.3. Tables cần vacuum/analyze

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

`n_dead_tup` và `n_live_tup` là estimates, không phải row counts chính xác. Dùng chúng để trend và ưu tiên điều tra, không làm số liệu tuyệt đối cho billing/capacity.

### 9.4. Vacuum progress

~~~sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
~~~

Progress view giúp biết phase và tiến độ scan/cleanup. Nó không hiển thị chính xác tổng memory của worker.

### 9.5. Index build progress

~~~sql
SELECT
    pid,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
~~~

Dùng cùng process memory/OS metrics để xem liệu operation có gặp memory pressure. Progress có thể không tuyến tính giữa các phases.

### 9.6. Temp file logging

Có thể cấu hình `log_temp_files` để ghi nhận temporary files vượt threshold. Điều này giúp tìm sort/hash spill, nhưng không chỉ riêng CREATE INDEX tạo temp files. Correlate timestamp, PID, database và command.

### 9.7. OS và cgroup metrics

Theo dõi:
- Host available memory.
- PostgreSQL process RSS.
- Cgroup memory.current/memory.max nếu chạy trong container.
- Memory pressure/PSI trên Linux.
- Swap activity.
- OOM killer events.
- Filesystem free space và temp volume capacity.

PostgreSQL không cung cấp một view duy nhất hiển thị chính xác memory consumed by maintenance operation. Kết hợp progress views với OS process metrics.

### 9.8. Vacuum logs

`log_autovacuum_min_duration` có thể ghi nhận autovacuum operations lâu hơn threshold. Log hữu ích cho duration, pages scanned/removed và thông tin cleanup theo version. Không để logging volume quá lớn mà không có retention/aggregation.

### 9.9. Checkpoint và I/O

Maintenance có thể tạo nhiều I/O dù memory đủ. Correlate vacuum/index progress với:
- Storage latency/throughput/IOPS.
- Checkpoint write/sync time.
- WAL generation.
- `pg_stat_io` trên PostgreSQL 16+.
- Temp file size.
- CPU utilization.

### 9.10. Dashboard

Một dashboard bảo trì nên có:
- Maintenance operations đang chạy.
- Autovacuum worker count.
- Oldest/longest vacuum.
- Dead tuple estimates theo table.
- Index build phase/duration.
- Temp file volume.
- Process/cgroup memory.
- Host available memory và swap.
- Storage latency/queue.
- Lock waits và transaction age.

---

## 10. Chọn mức maintenance_work_mem

### 10.1. Bắt đầu từ baseline

Không có giá trị tối ưu áp dụng cho mọi database. Mức mặc định thường nhỏ để phù hợp nhiều workload; có thể nâng trong hệ thống có RAM dư và maintenance jobs được kiểm soát.

Đánh giá:
- RAM vật lý/container limit.
- Database size và table churn.
- Index build frequency/size.
- Số autovacuum workers.
- Maintenance concurrency.
- Query memory budget.
- OS headroom và memory pressure.

### 10.2. VACUUM-heavy OLTP

Với OLTP có nhiều UPDATE/DELETE:
- Theo dõi dead tuples và vacuum frequency.
- Kiểm tra autovacuum thresholds.
- Xem `autovacuum_work_mem` trước khi tăng `maintenance_work_mem`.
- Kiểm tra transaction age/replication slots cản cleanup.
- Đo vacuum duration và I/O.
- Tăng memory có kiểm soát nếu nhiều cleanup cycles là vấn đề.

Đừng để autovacuum workers dùng một mức lớn mà không nhân với concurrency.

### 10.3. Index build window

Với index build lớn:
1. Chọn maintenance window.
2. Ước lượng index size và disk headroom.
3. Giới hạn số jobs concurrent.
4. SET session-level memory cao hơn nếu host đủ RAM.
5. Theo dõi progress, temp files, RSS và storage.
6. RESET/đóng session sau operation.

### 10.4. Data warehouse

Bulk loads và index builds có thể cần memory cao theo giai đoạn. Có thể tăng maintenance memory cho restore/build window rồi giảm về baseline. Kiểm soát concurrency để không làm query workload bị OOM.

### 10.5. Containerized PostgreSQL

Nếu container có memory limit, phải dùng giới hạn cgroup thực tế làm ngân sách. Host có thể còn nhiều RAM nhưng container vẫn bị OOM kill. Không đặt maintenance memory theo tổng RAM host nếu container chỉ được cấp một phần.

### 10.6. Managed PostgreSQL

Một số managed services giới hạn parameter values, quyền thay đổi hoặc visibility của OS metrics. Dùng parameter group/provider docs và dashboard được cung cấp; không giả định có thể truy cập process RSS hoặc thay mọi GUC.

### 10.7. Đặt giới hạn riêng cho autovacuum

Nếu manual index builds cần 2GB nhưng autovacuum cần giới hạn nhỏ hơn để bảo vệ concurrency, có thể đặt `autovacuum_work_mem` dương và riêng biệt. Đảm bảo mức đó vẫn đủ cho vacuum workload; đo hiệu quả qua progress/logs và dead tuple trends.

### 10.8. Không dùng memory để che vấn đề vacuum design

Nếu autovacuum không theo kịp:
- Xem thresholds/scale factors theo table.
- Xem write rate và table churn.
- Kiểm tra long-running transactions và replication slots.
- Kiểm tra vacuum cost delay/limit.
- Xem index bloat/maintenance overhead.
- Cân nhắc partitioning hoặc schema/workload changes.

Memory là một yếu tố trong hệ thống, không phải giải pháp thay thế cho thiết kế autovacuum.

---

## 11. Quan hệ với các tham số bảo trì khác

### 11.1. autovacuum_work_mem

`autovacuum_work_mem` đặt memory limit cho từng autovacuum worker. Khi giá trị là `-1`, worker dùng `maintenance_work_mem`. Khi đặt giá trị riêng, thay đổi `maintenance_work_mem` không nhất thiết thay đổi giới hạn autovacuum.

Ví dụ:

~~~conf
maintenance_work_mem = 512MB
autovacuum_work_mem = 256MB
autovacuum_max_workers = 5
~~~

Ngân sách bảo thủ cho autovacuum là tối đa khoảng 5 × 256MB theo cấu hình này, cộng các workloads khác.

### 11.2. autovacuum_max_workers

Tham số này giới hạn số autovacuum workers chạy đồng thời. Tăng workers có thể giúp nhiều tables được xử lý song song, nhưng cũng tăng:
- Memory demand.
- Storage I/O.
- CPU usage.
- Lock/IO contention.
- WAL/checkpoint pressure.

Không tăng workers mà không xem memory và storage capacity.

### 11.3. vacuum_cost_limit và vacuum_cost_delay

Các tham số cost-based vacuum điều tiết tốc độ I/O của VACUUM. `vacuum_cost_delay` tạo khoảng nghỉ khi cost vượt ngưỡng; `vacuum_cost_limit` quy định budget cost. Autovacuum có các tham số tương ứng.

Nếu VACUUM chậm do bị throttle để bảo vệ workload, tăng maintenance memory có thể không làm nó nhanh hơn. Cần xác định mục tiêu là giảm memory-driven extra cycles hay tăng I/O throughput.

### 11.4. vacuum_buffer_usage_limit

`vacuum_buffer_usage_limit` điều khiển kích thước buffer ring VACUUM sử dụng để hạn chế tác động lên shared buffers. Đây là khái niệm khác với `maintenance_work_mem`, vốn giới hạn memory cho maintenance operation.

Không tăng `vacuum_buffer_usage_limit` để thay thế việc tăng maintenance memory; mỗi setting xử lý một phần khác nhau của resource usage.

### 11.5. max_parallel_maintenance_workers

Tham số này giới hạn parallel workers cho các maintenance commands hỗ trợ parallelism, chẳng hạn một số index builds. Nó không phải memory limit.

Với parallel utility commands, `maintenance_work_mem` được áp dụng cho toàn command theo semantics PostgreSQL, không tự nhân limit với số parallel workers. Tuy nhiên, nhiều maintenance commands độc lập vẫn có thể dùng nhiều budgets đồng thời.

### 11.6. maintenance_io_concurrency

Ở các PostgreSQL versions hỗ trợ, `maintenance_io_concurrency` điều chỉnh mức I/O concurrency cho maintenance operations. Nó có thể ảnh hưởng throughput và queue depth, nhưng không cấp phát memory.

Điều chỉnh cùng storage characteristics; tăng concurrency trên storage đã bão hòa có thể làm latency xấu hơn.

### 11.7. Per-table storage parameters

Có thể điều chỉnh autovacuum behavior theo table, ví dụ:
- `autovacuum_vacuum_scale_factor`.
- `autovacuum_vacuum_threshold`.
- `autovacuum_analyze_scale_factor`.
- `autovacuum_analyze_threshold`.
- `autovacuum_vacuum_cost_limit`.
- `autovacuum_vacuum_cost_delay`.
- `autovacuum_enabled`.

Điều này giúp tables có write churn cao được vacuum sớm hơn mà không phải tăng global workers/memory cho mọi relation.

### 11.8. Parameter matrix

| Setting | Điều khiển | Không điều khiển |
|---|---|---|
| `maintenance_work_mem` | Memory ceiling cho maintenance operation | Tổng memory server |
| `autovacuum_work_mem` | Memory ceiling mỗi autovacuum worker | Số worker |
| `autovacuum_max_workers` | Worker concurrency | Memory mỗi worker |
| `vacuum_cost_limit`/`vacuum_cost_delay` | Tốc độ I/O/cost của vacuum | Dead tuple memory ceiling |
| `vacuum_buffer_usage_limit` | Buffer ring behavior | Maintenance work memory |
| `max_parallel_maintenance_workers` | Parallel workers cho command | Memory ceiling tổng command |
| `maintenance_io_concurrency` | Maintenance I/O concurrency | RAM allocation |

---

## 12. Quy trình tuning có kiểm soát

### 12.1. Xác định triệu chứng

Trước khi thay đổi setting, phân loại:
- VACUUM có nhiều index cleanup cycles?
- Autovacuum không theo kịp write churn?
- CREATE INDEX spill ra temp files?
- Restore jobs gây memory pressure?
- OOM hoặc swap tăng?
- Maintenance chậm do lock hoặc storage?

Không dùng một giá trị maintenance memory để chữa mọi loại vấn đề.

### 12.2. Thu thập baseline

Ghi lại:
- Setting hiện tại và source.
- Host/container memory limit.
- Concurrent maintenance operations.
- Autovacuum worker count.
- Process RSS/cgroup memory.
- Vacuum/index progress và duration.
- Temp file volume.
- Storage latency/throughput.
- CPU và swap.
- Query workload trong cùng thời gian.

### 12.3. Thay đổi một yếu tố

Ví dụ nếu index build spill nhiều:
1. Giữ nguyên job concurrency.
2. Tăng session `maintenance_work_mem` ở mức vừa phải.
3. Chạy lại trên cùng dữ liệu/test window.
4. So sánh duration, temp files, RSS và storage.
5. Chỉ tăng tiếp nếu kết quả cải thiện và memory headroom còn đủ.

Nếu đồng thời thay memory, job count, storage tier và parallel workers, khó xác định thay đổi nào tạo tác động.

### 12.4. Chọn giới hạn an toàn

Đặt upper bound theo peak memory budget. Ví dụ:
- Giới hạn memory cho maintenance role.
- Giới hạn số jobs chạy đồng thời trong scheduler.
- Giới hạn autovacuum worker concurrency.
- Đặt maintenance window.
- Theo dõi cgroup/host memory.
- Có phương án dừng/giảm concurrency khi headroom thấp.

### 12.5. Session override cho một job

Đây thường là cách tốt để thử một mức memory khác mà không thay đổi mọi sessions:

~~~sql
SET maintenance_work_mem = '1GB';
-- Run one maintenance command.
RESET maintenance_work_mem;
~~~

Với automation, dùng cleanup logic ở client hoặc đóng session sau command để không giữ setting ngoài ý muốn.

### 12.6. Đánh giá kết quả

So sánh:
- Runtime.
- CPU.
- Peak RSS.
- Memory pressure/swap.
- Temp file bytes.
- I/O latency/throughput.
- Number of vacuum cycles.
- Lock impact.
- Concurrent workload latency.
- Autovacuum backlog sau operation.

Một job nhanh hơn nhưng gây OOM hoặc làm application latency vượt SLO không phải kết quả tuning tốt.

### 12.7. Rollback setting

Ghi lại previous value/source. Nếu memory pressure tăng:
- Dừng khởi chạy maintenance jobs mới.
- Hạ concurrency.
- Reset session override.
- Khôi phục server/role/database setting theo change record.
- Theo dõi memory và active operations.
- Không kill autovacuum worker hàng loạt nếu chưa xác định table/transaction impact.

---

## 13. Troubleshooting thường gặp

### 13.1. VACUUM chậm dù maintenance_work_mem lớn

Kiểm tra:
- Dead tuple churn và table size.
- Vacuum progress/number of index cycles.
- Cost delay/limit.
- Long-running transactions và replication slots.
- Storage latency.
- Lock contention.
- Autovacuum workers cạnh tranh.
- Index count/size.

Memory lớn không đảm bảo vacuum nhanh nếu nguyên nhân là I/O, lock hoặc snapshot horizon.

### 13.2. Autovacuum không dùng mức memory vừa cấu hình

Kiểm tra `autovacuum_work_mem`. Nếu giá trị dương, worker dùng setting đó; nếu `-1`, worker kế thừa `maintenance_work_mem`. Xác nhận server đã reload setting cần thiết và không có table-level/workload behavior khác.

### 13.3. OOM khi chạy CREATE INDEX

Điều tra:
- Bao nhiêu index builds cùng chạy?
- Mỗi session đang dùng maintenance_work_mem bao nhiêu?
- Query workload có nhiều work_mem operations không?
- Autovacuum worker count và memory?
- Cgroup memory limit?
- Swap/OOM logs?
- pg_restore/automation job concurrency?

Giảm job concurrency hoặc giới hạn session memory trước khi tăng thêm RAM.

### 13.4. Temp files lớn trong index build

Xác định temp files có đúng do index build hay do query sort/hash khác. Kiểm tra build phase, index size, storage và maintenance memory. Nếu tăng memory không giảm temp files hoặc runtime, bottleneck có thể nằm ở I/O/CPU.

### 13.5. VACUUM FULL không giải phóng RAM/disk như kỳ vọng

VACUUM FULL rewrite table và cần disk space cho bản mới trong lúc thực hiện. Nó không phải công cụ giải phóng RAM. Memory setting không làm mất lock và disk-space requirements. Cân nhắc VACUUM thường, pg_repack hoặc phương án maintenance phù hợp.

### 13.6. Restore chậm

Kiểm tra:
- `pg_restore -j` concurrency.
- Index build time/temp files.
- `maintenance_work_mem` của restore sessions.
- Storage throughput.
- Constraint validation.
- WAL/checkpoint pressure.
- Network nếu restore từ remote archive.

Tăng jobs và tăng memory cùng lúc có thể làm peak memory vượt giới hạn.

### 13.7. Swap tăng sau khi tăng maintenance_work_mem

Xác định session/worker nào đang tiêu thụ memory, số operations concurrent và cgroup limit. Hạ concurrency/setting theo budget, sau đó kiểm tra query workload có bị swap latency ảnh hưởng không.

### 13.8. Autovacuum bị chậm do cost delay

Tăng memory không thay đổi cost delay. Kiểm tra vacuum cost parameters và storage headroom. Nếu cần giảm delay, đo tác động tới application I/O latency.

### 13.9. Memory setting không thay đổi trong session

Kiểm tra:
- SET có chạy thành công không?
- Role/database default có override không?
- Connection pool có giữ session cũ không?
- SHOW maintenance_work_mem.
- pg_settings.source và setting.
- Có đang xem đúng cluster/database/session không?

### 13.10. Không có memory metric theo PID trong PostgreSQL

PostgreSQL progress views thường không báo chính xác memory allocated per operation. Lấy PID từ progress/activity views rồi đối chiếu process RSS/cgroup metrics ở OS/monitoring platform. Không suy ra memory usage chỉ từ giá trị GUC.

---

## 14. Runbook cho maintenance memory pressure

1. Xác nhận alert và host/container memory headroom.
2. Kiểm tra OOM/swap/PSI/cgroup events.
3. Liệt kê maintenance commands và autovacuum workers đang chạy.
4. Đọc `maintenance_work_mem`, `autovacuum_work_mem`, `autovacuum_max_workers` và `work_mem`.
5. Xác định sessions có maintenance setting override.
6. Kiểm tra restore/index build job concurrency.
7. Tạm ngăn scheduler khởi chạy thêm maintenance jobs.
8. Nếu cần, giảm job concurrency hoặc kết thúc job theo quy trình ứng dụng/DBA đã phê duyệt.
9. Không terminate autovacuum hoặc backend tùy tiện; cân nhắc rollback/cleanup.
10. Khôi phục headroom và xác nhận database/application latency.
11. Điều chỉnh budget/setting và scheduler concurrency.
12. Ghi incident findings và theo dõi lần maintenance kế tiếp.

### 14.1. Khi OOM đã xảy ra

- Thu thập kernel/cgroup OOM logs.
- Xác định process bị OOM kill.
- Kiểm tra PostgreSQL logs và transaction rollback.
- Kiểm tra index invalid/incomplete sau build failure.
- Kiểm tra vacuum/autovacuum backlog.
- Xác minh database recovery và application retry.
- Chỉ chạy lại maintenance khi memory budget đã được sửa.

### 14.2. Khi chỉ một maintenance job chậm

Nếu memory headroom tốt và chỉ một job chậm, đừng mặc định đây là memory incident. Xem progress phase, lock wait, storage/CPU và query/object size. Điều chỉnh đúng resource bottleneck.

---

## 15. Tài liệu tham khảo PostgreSQL

Ưu tiên tài liệu đúng major version:

- [PostgreSQL — Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html): maintenance_work_mem, autovacuum_work_mem, work_mem và các resource settings.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): VACUUM, autovacuum và dead tuple cleanup.
- [PostgreSQL — Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): pg_stat_progress_vacuum và pg_stat_progress_create_index.
- [PostgreSQL — Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html): worker concurrency và vacuum cost settings.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index build behavior và parallelism.
- [PostgreSQL — pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html): parallel restore jobs.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): statistics views và pg_stat_io trên version hỗ trợ.

Các trang /current/ có thể trỏ tới major version mới hơn. Kiểm tra setting context, view columns và parallel maintenance behavior theo phiên bản đang chạy.

---

## 16. Bài lab: quan sát và điều chỉnh VACUUM

Thực hiện trong database lab có đủ disk/RAM. Không tạo churn lớn hoặc tăng memory trên production chỉ để chạy bài tập.

### 16.1. Tạo bảng thử nghiệm

~~~sql
CREATE SCHEMA IF NOT EXISTS maintenance_lab;

CREATE TABLE maintenance_lab.events (
    event_id bigserial PRIMARY KEY,
    account_id bigint NOT NULL,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO maintenance_lab.events(account_id, payload)
SELECT
    (g % 10000)::bigint,
    repeat('x', 300)
FROM generate_series(1, 200000) AS g;
~~~

Kích thước dataset cần phù hợp tài nguyên lab. Có thể giảm số rows trên laptop/container nhỏ.

### 16.2. Tạo dead tuples

~~~sql
UPDATE maintenance_lab.events
SET payload = repeat('y', 300)
WHERE event_id % 3 = 0;

DELETE FROM maintenance_lab.events
WHERE event_id % 7 = 0;
~~~

Các thao tác này tạo tuple versions/dead tuples. Số lượng chính xác chịu ảnh hưởng autovacuum và visibility map.

### 16.3. Kiểm tra thống kê table

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'maintenance_lab';
~~~

Các tuple counts là estimates. Nếu autovacuum đã chạy trước khi quan sát, tạo thêm workload nhỏ hoặc dùng table mới.

### 16.4. Chạy VACUUM với session setting

~~~sql
SET maintenance_work_mem = '128MB';
VACUUM (VERBOSE, ANALYZE) maintenance_lab.events;
RESET maintenance_work_mem;
~~~

VACUUM không chạy bên trong transaction block. Dùng psql session riêng; kiểm tra logs/VERBOSE output và progress khi table đủ lớn.

### 16.5. So sánh với mức memory khác

Trong lab, chạy lại với một mức maintenance memory khác sau khi tạo churn tương đương. Ghi:
- Vacuum duration.
- Number of index cleanup cycles nếu có trong output/progress.
- Dead tuple estimates trước/sau.
- I/O latency và throughput.
- Process RSS.
- Application workload impact nếu có.

Không kết luận từ hai runs nếu dataset/cache/workload khác nhau nhiều.

### 16.6. Quan sát autovacuum

Xem `autovacuum_work_mem`, `autovacuum_max_workers` và worker activity. Nếu muốn thử inheritance, dùng cluster lab và đặt `autovacuum_work_mem=-1`; sau đó so sánh với giá trị dương. Thay đổi cấu hình autovacuum có thể cần reload theo setting context.

---

## 17. Bài lab: CREATE INDEX và memory budget

### 17.1. Tạo bảng index test

~~~sql
CREATE TABLE maintenance_lab.index_source AS
SELECT
    g::bigint AS id,
    (g % 50000)::bigint AS customer_id,
    md5(g::text) AS payload,
    clock_timestamp() - (g || ' seconds')::interval AS created_at
FROM generate_series(1, 500000) AS g;

ALTER TABLE maintenance_lab.index_source
ADD PRIMARY KEY (id);
~~~

Điều chỉnh row count theo dung lượng lab.

### 17.2. Tạo index với mức mặc định

~~~sql
CREATE INDEX idx_index_source_customer
ON maintenance_lab.index_source (customer_id);
~~~

Ghi lại thời gian, temp file logs nếu được bật và storage metrics.

### 17.3. Rebuild với mức session khác

~~~sql
DROP INDEX maintenance_lab.idx_index_source_customer;

SET maintenance_work_mem = '512MB';

CREATE INDEX idx_index_source_customer
ON maintenance_lab.index_source (customer_id);

RESET maintenance_work_mem;
~~~

Đây là test so sánh; không nên drop index production để benchmark. Chạy trên dataset/host tương tự và kiểm soát cache state.

### 17.4. Quan sát progress

Với bảng đủ lớn, query pg_stat_progress_create_index trong session khác. So sánh phases và blocks/tuples progress; memory usage cần lấy từ process/cgroup metrics.

### 17.5. Thử concurrency budget

Chạy hai index builds trên hai bảng lab riêng với session settings đã định. Quan sát host/cgroup memory. Dừng thử nghiệm khi headroom xuống dưới ngưỡng an toàn. Bài lab minh họa vì sao một setting cao có thể an toàn cho một job nhưng không an toàn cho nhiều jobs.

---

## 18. Bài lab: cấu hình và xác nhận settings

### 18.1. Xem context và source

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name LIKE '%work_mem%'
ORDER BY name;
~~~

Xác định setting nào session có thể override và setting nào cần cấu hình server/reload theo context.

### 18.2. Session override

~~~sql
SET maintenance_work_mem = '256MB';
SHOW maintenance_work_mem;
RESET maintenance_work_mem;
SHOW maintenance_work_mem;
~~~

Xác nhận giá trị trở về session default sau RESET.

### 18.3. Role default

Trong lab, tạo role riêng và gán default:

~~~sql
CREATE ROLE lab_maintenance LOGIN;
ALTER ROLE lab_maintenance
SET maintenance_work_mem = '384MB';
~~~

Mở session mới bằng role đó và kiểm tra SHOW. Session đang mở trước ALTER ROLE không tự nhận default mới.

### 18.4. Database default

~~~sql
ALTER DATABASE maintenance_lab
SET maintenance_work_mem = '256MB';
~~~

Mở session mới vào database và kiểm tra. Gỡ setting sau lab bằng ALTER DATABASE ... RESET maintenance_work_mem.

### 18.5. Kiểm tra nguồn cấu hình

Dùng pg_settings.source để biết setting đến từ default, configuration file, role/database setting hay session override. Dùng pg_file_settings để kiểm tra parse errors nếu có quyền.

---

## 19. Bài tập thực hành

Các câu hỏi dùng PostgreSQL lab. Không tăng memory hoặc chạy maintenance concurrency cao trên production để kiểm tra một giả thuyết.

### Bài 1 — Mục đích

maintenance_work_mem phục vụ loại công việc nào? Nêu ba ví dụ.

### Bài 2 — Per operation

Vì sao không thể coi maintenance_work_mem là một ngân sách memory tổng cho toàn server?

### Bài 3 — VACUUM

Memory thấp có thể ảnh hưởng VACUUM như thế nào?

### Bài 4 — Index build

Vì sao tăng maintenance_work_mem có thể giảm temp files khi CREATE INDEX?

### Bài 5 — Autovacuum

autovacuum_work_mem=-1 có nghĩa gì?

### Bài 6 — Worker concurrency

Có 4 autovacuum workers và mỗi worker có giới hạn 512MB. Ngân sách bảo thủ cho nhóm workers là bao nhiêu?

### Bài 7 — work_mem

Phân biệt work_mem và maintenance_work_mem.

### Bài 8 — effective_cache_size

effective_cache_size có cấp phát RAM không?

### Bài 9 — shared_buffers

shared_buffers khác maintenance_work_mem ở phạm vi nào?

### Bài 10 — Parallel maintenance

Có nên nhân maintenance_work_mem với số parallel workers của một command không? Vì sao?

### Bài 11 — Restore jobs

Sáu pg_restore jobs đồng thời, mỗi job đang build một index với maintenance_work_mem 1GB. Ngân sách bảo thủ cho nhóm index builds là bao nhiêu?

### Bài 12 — OOM

Một index build chạy riêng lẻ thành công với 2GB nhưng hai builds đồng thời làm container OOM. Giải thích.

### Bài 13 — Vacuum progress

View nào cho biết phase và tiến độ VACUUM? View đó có báo memory usage chính xác không?

### Bài 14 — Index progress

View nào cho biết phase/blocks/tuples của CREATE INDEX?

### Bài 15 — Autovacuum chậm

Autovacuum chậm do vacuum_cost_delay. Tăng maintenance_work_mem có giải quyết trực tiếp không?

### Bài 16 — Long transaction

Vì sao transaction lâu có thể khiến VACUUM không cleanup được dead tuples dù memory cao?

### Bài 17 — Setting scope

Nêu cách đặt maintenance_work_mem chỉ cho một session DBA.

### Bài 18 — VACUUM transaction

Vì sao không thể đặt SET LOCAL rồi chạy VACUUM trong transaction block?

### Bài 19 — ALTER ROLE

ALTER ROLE SET maintenance_work_mem ảnh hưởng sessions đang mở hay sessions mới?

### Bài 20 — Memory budget

Liệt kê ít nhất sáu thành phần cần tính khi lập memory budget cho PostgreSQL host.

### Bài 21 — Temp files

Temp files lớn trong thời gian index build có nhất thiết được tạo bởi index build không? Cần correlate gì?

### Bài 22 — pg_stat_io

pg_stat_io có từ PostgreSQL major version nào? Nó có báo chính xác memory consumed không?

### Bài 23 — vacuum_buffer_usage_limit

Setting này khác maintenance_work_mem như thế nào?

### Bài 24 — Index build chậm

Nêu các metrics cần kiểm tra trước khi tăng maintenance_work_mem.

### Bài 25 — Incident

Host có memory pressure, 3 index builds thủ công, 4 autovacuum workers và query latency tăng. Nêu trình tự ứng phó.

---

## 20. Lời giải — bài 1 đến 25

### Bài 1 — Mục đích

maintenance_work_mem dành cho maintenance operations. Ví dụ VACUUM, CREATE INDEX/REINDEX và một số thao tác ALTER TABLE cần validation.

### Bài 2 — Per operation

Setting là giới hạn cho từng operation. Nhiều sessions hoặc workers có thể chạy maintenance đồng thời và mỗi operation có budget riêng; vì vậy tổng memory có thể là bội số của setting.

### Bài 3 — VACUUM

Memory thấp có thể khiến VACUUM xử lý dead tuple identifiers theo nhiều cycles, làm index cleanup lặp lại và tăng I/O/duration. VACUUM vẫn có cơ chế xử lý theo batches.

### Bài 4 — Index build

Index build có thể cần sort dữ liệu. Nếu memory đủ lớn, có thể giảm external sorting/temp file spill và cải thiện build time khi sort là bottleneck.

### Bài 5 — Autovacuum

autovacuum_work_mem=-1 nghĩa là mỗi autovacuum worker kế thừa maintenance_work_mem. Nếu đặt giá trị dương, worker dùng giới hạn riêng.

### Bài 6 — Worker concurrency

4 × 512MB = 2GB là ngân sách bảo thủ cho giới hạn memory của nhóm autovacuum workers, chưa tính các workloads khác. Workers không nhất thiết luôn dùng hết limit.

### Bài 7 — work_mem

work_mem dành cho sort/hash operations trong query; maintenance_work_mem dành cho maintenance commands như VACUUM/index build. Một query có nhiều sort/hash nodes và nhiều sessions, nên work_mem aggregate cũng có thể lớn.

### Bài 8 — effective_cache_size

Không. Đây là planner estimate về cache có thể dùng; nó không cấp phát hoặc reserve RAM.

### Bài 9 — shared_buffers

shared_buffers là shared cache vùng server-level cho database pages. maintenance_work_mem là memory ceiling theo maintenance operation.

### Bài 10 — Parallel maintenance

Không tự nhân một cách máy móc. Với parallel utility commands, PostgreSQL áp dụng maintenance_work_mem cho toàn command theo semantics của nó; kiểm tra tài liệu version/command. Nhiều commands độc lập vẫn có thể dùng nhiều budgets cùng lúc.

### Bài 11 — Restore jobs

6 × 1GB = 6GB là ngân sách bảo thủ cho sáu index builds đồng thời. Cộng thêm autovacuum, query memory, backend overhead và OS.

### Bài 12 — OOM

Một build đơn lẻ có thể nằm trong RAM budget, nhưng hai builds đồng thời nhân peak demand. Container memory limit có thể thấp hơn host RAM; thêm autovacuum/query workload sẽ làm tổng vượt giới hạn.

### Bài 13 — Vacuum progress

pg_stat_progress_vacuum cho biết phase và heap scan/vacuum progress. Nó không báo chính xác memory consumed; cần OS/cgroup process metrics để theo dõi RSS.

### Bài 14 — Index progress

pg_stat_progress_create_index hiển thị command, phase, blocks/tuples progress. Nó không phải memory usage view.

### Bài 15 — Autovacuum chậm

Không trực tiếp. vacuum_cost_delay điều tiết I/O rate. Cần đánh giá cost parameters/storage và workload; tăng memory chỉ có thể giúp nếu memory-driven extra cycles là vấn đề.

### Bài 16 — Long transaction

Snapshot cũ có thể vẫn cần tuple versions cũ, nên VACUUM không thể cleanup chúng. Memory cao không thay đổi visibility horizon.

### Bài 17 — Setting scope

Mở session DBA và chạy SET maintenance_work_mem = '1GB'; sau maintenance command chạy RESET maintenance_work_mem hoặc đóng session. Không dùng ALTER SYSTEM nếu chỉ cần một job.

### Bài 18 — VACUUM transaction

VACUUM không được chạy trong transaction block. SET LOCAL chỉ có hiệu lực trong transaction nên không thể bao quanh VACUUM theo cách đó; dùng session-level SET trước command.

### Bài 19 — ALTER ROLE

ALTER ROLE SET áp dụng default cho sessions mới khi role đăng nhập. Sessions đang mở không tự nhận setting mới.

### Bài 20 — Memory budget

Ví dụ: shared_buffers, manual maintenance concurrency, maintenance_work_mem, autovacuum workers/autovacuum_work_mem, query work_mem/hash allowance, backend overhead, OS/filesystem cache, agents và container memory limit.

### Bài 21 — Temp files

Không. Query sort/hash hoặc operations khác có thể tạo temp files cùng thời điểm. Correlate PID, timestamp, database, application/query và maintenance progress/logs.

### Bài 22 — pg_stat_io

pg_stat_io có từ PostgreSQL 16. Nó tổng hợp I/O activity; không báo chính xác memory consumed bởi từng maintenance operation.

### Bài 23 — vacuum_buffer_usage_limit

Setting này điều khiển buffer ring VACUUM dùng để hạn chế tác động lên shared buffers. maintenance_work_mem giới hạn memory cho maintenance operation; hai settings phục vụ mục đích khác nhau.

### Bài 24 — Index build chậm

Kiểm tra table/index size, progress phase, temp files, storage latency/throughput, CPU, memory headroom/RSS, số jobs concurrent và locks. Chỉ tăng memory nếu có bằng chứng memory/sort là bottleneck.

### Bài 25 — Incident

1. Xác nhận memory pressure, cgroup/host limit, swap và OOM logs.
2. Liệt kê ba index builds, PID, session settings và progress.
3. Xem bốn autovacuum workers, autovacuum_work_mem và worker activity.
4. Tạm ngăn scheduler khởi chạy maintenance jobs mới.
5. Giảm concurrency hoặc pause/cancel một số index jobs theo change/runbook đã duyệt.
6. Đối chiếu query latency và query memory demand.
7. Khôi phục memory headroom, kiểm tra invalid indexes/transaction outcomes.
8. Điều chỉnh memory budget, job scheduling và autovacuum settings.
9. Theo dõi lần maintenance tiếp theo và ghi incident findings.

---

## 21. Tổng kết

maintenance_work_mem là một resource limit quan trọng cho VACUUM và các maintenance operations như index build. Giá trị cao hơn có thể giảm số lượt cleanup hoặc temporary sort spill trong những workload phù hợp, nhưng nó không phải giới hạn tổng RAM và không thay thế tuning I/O, lock behavior hay autovacuum policy.

Các nguyên tắc cần nhớ:

1. maintenance_work_mem áp dụng theo operation; nhiều operations đồng thời có thể nhân memory demand.
2. autovacuum_work_mem đặt giới hạn mỗi autovacuum worker; -1 kế thừa maintenance_work_mem.
3. Tính autovacuum_max_workers khi lập peak memory budget.
4. work_mem dành cho sort/hash query operations và cũng có concurrency multiplier.
5. shared_buffers là shared cache; effective_cache_size chỉ là planner estimate.
6. VACUUM memory thấp có thể làm tăng cleanup cycles/I/O; memory cao không xử lý được long transactions hoặc cost delay.
7. CREATE INDEX/REINDEX có thể giảm external sort spill khi đủ memory, nhưng storage/CPU vẫn là yếu tố chính.
8. Parallel workers của một command không đồng nghĩa mỗi worker được cấp thêm toàn bộ maintenance_work_mem; xác nhận semantics theo version.
9. pg_stat_progress_vacuum và pg_stat_progress_create_index cho progress, không báo memory chính xác.
10. Kết hợp PostgreSQL views với RSS/cgroup/OS metrics và temp-file logs.
11. Dùng session override cho một maintenance job nếu cần memory cao tạm thời.
12. Giới hạn job concurrency, đặc biệt trong pg_restore và index builds.
13. Tuning theo baseline, thay đổi từng yếu tố và so sánh duration, memory, temp files, I/O cùng application latency.
14. Khi OOM/memory pressure, giảm concurrency và phục hồi headroom trước khi tăng thêm memory.

Quy trình vận hành: **xác định maintenance bottleneck → đo baseline và concurrency → lập memory budget có headroom → chọn maintenance/autovacuum limits → áp dụng trong phạm vi nhỏ → theo dõi progress/RSS/I/O → so sánh tác động → cập nhật scheduler và runbook**.
