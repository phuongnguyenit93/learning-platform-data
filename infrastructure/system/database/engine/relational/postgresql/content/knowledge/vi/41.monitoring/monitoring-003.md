# Wait event và phân biệt chờ khóa, I/O, client trong PostgreSQL

## 1. Wait event giúp trả lời câu hỏi gì?

Khi một query chạy lâu, thời gian chờ có thể đến từ nhiều nguyên nhân: transaction khác đang giữ lock, PostgreSQL đợi storage đọc/ghi dữ liệu, backend chờ client gửi command hoặc đọc kết quả, hay một process khác đang phối hợp nội bộ. Chỉ nhìn thời gian query chưa đủ để biết nguyên nhân.

PostgreSQL cung cấp **wait events** để cho biết backend hoặc process đang chờ tại điểm nào. Hai trường quan trọng trong `pg_stat_activity` là:

- `wait_event_type`: nhóm nguyên nhân chờ, ví dụ `Lock`, `IO`, `Client`, `LWLock`.
- `wait_event`: điểm chờ cụ thể, ví dụ `transactionid`, `DataFileRead`, `ClientRead`.

Kết hợp wait event với `state`, thời gian query/transaction, blocker information, I/O statistics và metrics hệ điều hành sẽ giúp phân biệt ba nhóm thường gặp:

1. **Chờ khóa:** query không thể tiếp tục vì cần một lock đang được backend khác giữ.
2. **Chờ I/O:** backend đợi thao tác đọc/ghi/flush/extend dữ liệu hoặc WAL.
3. **Chờ client:** PostgreSQL đợi dữ liệu từ client hoặc đang cố gửi dữ liệu về client.

Một wait event chỉ là ảnh chụp trạng thái tại thời điểm lấy mẫu. Nó không tự kết luận query đang lỗi, database bị nghẽn hay cần kill backend. Phải quan sát lặp lại và kết hợp ngữ cảnh.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc `state`, `wait_event_type` và `wait_event` trong `pg_stat_activity`.
2. Phân biệt heavyweight lock với LWLock và BufferPin.
3. Tìm blocker bằng `pg_blocking_pids()` và `pg_locks`.
4. Nhận diện I/O waits và phân tích read/write/flush pressure.
5. Phân biệt `ClientRead` với `ClientWrite`.
6. Nhận ra session idle bình thường và `idle in transaction` nguy hiểm.
7. Lấy mẫu wait events để tìm pattern thay vì kết luận từ một lần query.
8. Thiết kế dashboard, alert và runbook cho lock/I/O/client waits.
9. Xác định khi nào cần điều tra query plan, storage, network hay application.
10. Thực hành troubleshooting trong PostgreSQL lab.

### 1.2. Nguyên tắc cần nhớ

- `wait_event_type` là nhóm; `wait_event` là tên điểm chờ cụ thể.
- `state='active'` không có nghĩa backend đang sử dụng CPU liên tục; nó có thể đang chờ.
- `state='idle'` cùng `ClientRead` thường là connection đang chờ command tiếp theo, không phải lỗi.
- `ClientWrite` thường cho biết server đang chờ gửi dữ liệu tới client; client chậm hoặc network/output lớn có thể là nguyên nhân.
- `Lock` thường liên quan lock được quản lý bởi lock manager; `LWLock` là cơ chế đồng bộ nội bộ khác.
- `IO` chỉ ra backend đang chờ một thao tác I/O, nhưng chưa chứng minh storage device là bottleneck duy nhất.
- Một wait event thoáng qua có thể hoàn toàn bình thường.
- `pg_stat_activity` chỉ cho trạng thái hiện tại; muốn lịch sử wait cần sampling/monitoring riêng.
- Không kill backend chỉ dựa vào một wait event.
- Luôn kiểm tra blocker, transaction age, query, application, storage/network metrics và tác động business.

---

## 2. Đọc pg_stat_activity

### 2.1. Các trường quan trọng

`pg_stat_activity` có một dòng cho mỗi server process, gồm client backends và nhiều loại background workers.

| Field | Ý nghĩa |
|---|---|
| `pid` | Process ID |
| `datname` | Database |
| `usename` | User |
| `application_name` | Tên ứng dụng/connection |
| `client_addr` | Địa chỉ client |
| `backend_type` | Loại backend/process trên các version hỗ trợ |
| `state` | Trạng thái query/session |
| `wait_event_type` | Nhóm wait event |
| `wait_event` | Điểm chờ cụ thể |
| `query_start` | Thời điểm query hiện tại bắt đầu |
| `xact_start` | Thời điểm transaction hiện tại bắt đầu |
| `state_change` | Lần gần nhất state thay đổi |
| `query` | Query hiện tại hoặc query gần nhất tùy state |

Một số columns chỉ có ở các major versions nhất định. Kiểm tra schema của view trên server thực tế trước khi dùng query trong automation.

### 2.2. state

Các trạng thái phổ biến:

- `active`: backend đang thực thi query.
- `idle`: backend đang chờ command mới từ client.
- `idle in transaction`: backend đang ở trong transaction nhưng hiện không chạy query.
- `idle in transaction (aborted)`: transaction đã lỗi và đang chờ client rollback/đóng transaction.
- `fastpath function call`: backend đang thực thi fast-path function call trên các version có trạng thái này.

`idle in transaction` có thể giữ locks, snapshot và transaction ID lâu hơn cần thiết. Nó có thể làm vacuum không cleanup được dead tuples, giữ relation locks và gây bloat dù không có query active.

### 2.3. Query cơ bản để xem waits

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    query
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
~~~

`query_age` chỉ có ý nghĩa trực tiếp với query hiện tại khi `state='active'`. Với session idle, `query` có thể là query cuối cùng và `query_start` không đại diện cho một query đang chạy.

### 2.4. Chỉ xem backend đang active và có wait

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE state = 'active'
  AND wait_event IS NOT NULL
ORDER BY query_start;
~~~

Query này hữu ích để lấy danh sách đang chờ, nhưng không hiển thị session idle-in-transaction có thể đang giữ lock và là blocker của query khác.

### 2.5. Hiểu active nhưng đang chờ

Khi `state='active'` và `wait_event IS NOT NULL`, query đang được xem là active nhưng process hiện tại đang chờ tại wait point. Ví dụ:
- Active + Lock: query đang chờ lock.
- Active + IO: query đang chờ I/O.
- Active + LWLock: query đang chờ một internal lightweight lock.

Nếu `state='active'` nhưng `wait_event IS NULL`, backend không ở một wait point được instrument tại thời điểm lấy mẫu. Nó có thể đang chạy CPU, runnable hoặc ở đoạn code không ghi wait event. Cần kiểm tra CPU, plan và OS scheduler để phân biệt.

### 2.6. Permission và visibility

Để xem đầy đủ thông tin của sessions khác, role cần quyền phù hợp, thường là superuser hoặc role như `pg_read_all_stats` theo version. Nếu không đủ quyền, một số thông tin query/activity của backend khác có thể bị ẩn.

Không cấp superuser chỉ để dashboard đọc stats; dùng role giám sát có quyền tối thiểu cần thiết.

### 2.7. Query text và dữ liệu nhạy cảm

`query` có thể chứa literal values, email, identifiers hoặc dữ liệu nhạy cảm. Không đưa raw query text vào dashboard/ticket có audience rộng. Có thể redact, giới hạn quyền, dùng query ID từ pg_stat_statements hoặc lưu mẫu đã xử lý.

---

## 3. Wait event taxonomy

### 3.1. Nhóm wait_event_type

Các nhóm thường gặp trong PostgreSQL gồm:

| Wait event type | Ý nghĩa tổng quát | Ví dụ |
|---|---|---|
| `Activity` | Background process chờ hoạt động chính | `WalWriterMain`, `AutoVacuumMain` |
| `BufferPin` | Chờ buffer pin được giải phóng | `BufferPin` |
| `Client` | Chờ giao tiếp với client socket | `ClientRead`, `ClientWrite` |
| `Extension` | Wait point do extension định nghĩa | Tùy extension |
| `IO` | Chờ thao tác I/O | `DataFileRead`, `WALWrite` |
| `IPC` | Chờ liên lạc/điều phối giữa processes | Event phụ thuộc version |
| `Lock` | Chờ heavyweight lock | `relation`, `transactionid` |
| `LWLock` | Chờ lightweight lock nội bộ | `BufferContent`, `WALWrite` |
| `Timeout` | Chờ timeout/delay | `PgSleep`, `VacuumDelay` |

Danh sách event và tên cụ thể thay đổi giữa major versions. Luôn đối chiếu tài liệu PostgreSQL đúng release.

### 3.2. Wait event không phải error code

Một process chờ I/O, lock hoặc client socket có thể là hoạt động bình thường. Wait event mô tả backend đang đợi gì, không nói rằng wait đã vượt SLA hoặc có lỗi.

Cần thêm:
- Wait duration/repeated samples.
- Query/transaction age.
- Number of affected sessions.
- Query rate/throughput.
- Resource saturation.
- User-visible latency.
- Blocking chain hoặc storage/network evidence.

### 3.3. Một process có một wait event tại một thời điểm

Một backend có thể chuyển liên tục giữa CPU work, lock waits, I/O waits và client waits. Một query lấy mẫu duy nhất có thể bỏ lỡ wait quan trọng. Sampling định kỳ giúp quan sát pattern, nhưng cần chọn interval phù hợp để không tạo quá nhiều telemetry.

### 3.4. Wait event và query duration

Query chạy 10 phút không nhất thiết chờ 10 phút ở cùng một event. Nó có thể:
- Chờ lock 8 phút rồi đọc dữ liệu 2 phút.
- Đọc nhiều pages và chờ I/O rải rác.
- Tạo kết quả lớn rồi chờ client nhận.
- Chạy CPU-bound với wait_event null phần lớn thời gian.

Do đó không suy ra tổng wait time chỉ từ current wait event.

### 3.5. Nhóm waits cần phân biệt

Bài này tập trung vào ba nhóm vận hành:

1. `Lock`: thường cần tìm blocker/lock conflict.
2. `IO`: cần phân tích query plan, buffer/cache, storage và WAL.
3. `Client`: cần xem ứng dụng, socket, network và transaction/session lifecycle.

Các nhóm `LWLock` và `BufferPin` cũng quan trọng vì chúng có thể trông giống “lock wait” nhưng nguyên nhân và cách xử lý khác heavyweight locks.

---

## 4. Chờ khóa: Lock waits

### 4.1. Heavyweight lock là gì?

PostgreSQL dùng lock manager để điều phối truy cập đồng thời vào các resources như tables, rows/tuples, transactions, objects và advisory locks. Khi một backend yêu cầu mode xung đột với lock đang được backend khác giữ, nó phải chờ.

Ví dụ:
- Một transaction giữ ACCESS EXCLUSIVE lock do ALTER TABLE.
- Query SELECT cần ACCESS SHARE lock và phải chờ.
- Một UPDATE chờ row lock do transaction khác đang sửa cùng row.
- Một transaction chờ transaction ID của transaction chưa commit/rollback.

### 4.2. Nhận diện Lock wait

Trong `pg_stat_activity`:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS xact_age,
    query
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
~~~

Khi thấy `wait_event_type='Lock'`, tìm blocker trực tiếp bằng `pg_blocking_pids()`. Không kết luận chỉ từ tên event; xem lock type, mode và query gây giữ lock.

### 4.3. pg_blocking_pids()

`pg_blocking_pids(pid)` trả về PID của các processes đang block backend được chỉ định. Đây thường là cách dễ nhất để tìm blocker vì PostgreSQL đã tính lock conflict.

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

Kết quả có thể chứa nhiều blocker. Một PID blocker có thể là parallel worker hoặc process khác theo behavior của version; đối chiếu đầy đủ process information.

### 4.4. Hiển thị waiter và blocker cùng dòng

~~~sql
SELECT
    waiter.pid AS waiter_pid,
    waiter.usename AS waiter_user,
    waiter.application_name AS waiter_app,
    waiter.state AS waiter_state,
    waiter.wait_event,
    clock_timestamp() - waiter.query_start AS waiter_query_age,
    waiter.query AS waiter_query,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    blocker.query AS blocker_query
FROM pg_stat_activity AS waiter
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(waiter.pid)) AS blocked(blocker_pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = blocked.blocker_pid
ORDER BY waiter.query_start;
~~~

Đây là query chẩn đoán trực tiếp. Nếu blocker ở trạng thái idle in transaction, xem transaction age và application owner. Query text của blocker có thể là statement cuối cùng, không nhất thiết là statement đã lấy lock đầu tiên.

### 4.5. Xem lock chưa được grant

~~~sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple,
    l.transactionid,
    l.virtualxid,
    l.granted,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE NOT l.granted
ORDER BY l.pid;
~~~

`granted=false` cho biết lock request đang chờ. Query này hiển thị waiter nhưng không tự giải thích toàn bộ conflict chain. Dùng `pg_blocking_pids()` để xác định blocker, sau đó xem các locks của blocker.

### 4.6. Lock mode và conflict

PostgreSQL có nhiều lock modes; hai modes chỉ conflict khi ma trận lock quy định chúng xung đột. Ví dụ:
- ACCESS SHARE thường tương thích với nhiều modes, nhưng conflict với ACCESS EXCLUSIVE.
- ROW EXCLUSIVE thường được giữ bởi INSERT/UPDATE/DELETE.
- SHARE/SHARE ROW EXCLUSIVE/EXCLUSIVE/ACCESS EXCLUSIVE có mức conflict khác nhau.

Không suy luận lock conflict chỉ bằng cách so tên mode. Tra lock conflict matrix trong PostgreSQL documentation.

### 4.7. Relation lock và row lock

`pg_locks` có thể hiển thị relation lock hoặc transaction ID lock. Row-level locks thường được lưu trong tuple headers và được đại diện qua transaction ID waits; không phải lúc nào cũng thấy một row lock đơn giản tương ứng như một dòng dễ đọc trong pg_locks.

Vì vậy một waiter có `wait_event='transactionid'` có thể đang chờ transaction đang giữ row lock kết thúc.

### 4.8. Lock queue và blocker chain

Một blocker có thể chặn nhiều waiters; một waiter lại có thể chặn các request khác phía sau. Tạo lock tree giúp xác định root blocker. Ưu tiên xử lý transaction ở đầu chain thay vì kill từng waiter.

### 4.9. Idle in transaction là blocker phổ biến

Một session `idle in transaction` có thể giữ locks sau khi statement đã kết thúc. Ứng dụng có thể:
- Mở transaction rồi đợi user input.
- Không commit/rollback do exception.
- Giữ connection trong pool quá lâu.
- Quên đóng transaction khi xử lý nhiều bước.

Theo dõi `xact_start`, `state_change` và `application_name`. `idle_in_transaction_session_timeout` có thể giúp giới hạn session bỏ quên, nhưng cần đánh giá tác động ứng dụng và version.

### 4.10. Advisory locks

Advisory locks do ứng dụng quản lý và không tự bảo vệ table rows như constraints. Chúng có thể gây wait event `advisory`. Cần tìm code path gọi `pg_advisory_lock`/`pg_try_advisory_lock` và quy ước key giữa services.

### 4.11. Cách xử lý Lock wait

1. Xác định waiter và thời gian chờ.
2. Tìm blocker bằng pg_blocking_pids.
3. Xác định transaction/query đã giữ lock và owner.
4. Kiểm tra transaction age, state, application và business operation.
5. Xem lock mode/resource để hiểu conflict.
6. Ưu tiên để transaction hoàn tất nếu có thể.
7. Nếu cần cancel/terminate, đánh giá rollback cost và unknown outcome phía ứng dụng.
8. Theo dõi queue giảm và query tiếp tục.

Không terminate blocker chỉ vì nó là blocker. Có thể nó đang thực hiện transaction hợp lệ hoặc migration cần thiết; quyết định phải dựa trên incident policy.

---

## 5. Phân biệt Lock, LWLock và BufferPin

### 5.1. Lock

`wait_event_type='Lock'` thường là heavyweight lock manager waits. Có thể dùng pg_blocking_pids để tìm backend đang giữ lock xung đột.

### 5.2. LWLock

Lightweight locks bảo vệ các cấu trúc shared memory nội bộ. Chúng không tương đương SQL table/row locks và không được xử lý bằng cách kill “blocker query” một cách máy móc.

Một số wait names minh họa:
- `BufferContent`: chờ quyền truy cập nội dung shared buffer.
- `BufferMapping`: đồng bộ cấu trúc mapping buffer.
- `WALInsert`/`WALWrite`: đồng bộ các đường ghi WAL.
- `LockManager`: đồng bộ nội bộ lock manager.
- `ProcArray`: đồng bộ cấu trúc process/transaction state.

Tên chính xác và nhóm wait có thể thay đổi theo version.

### 5.3. Điều tra LWLock

Nếu LWLock waits tăng:
- Xem wait event cụ thể.
- Xem số lượng backend bị ảnh hưởng.
- Xem workload concurrency.
- Kiểm tra buffer/WAL/transaction churn.
- Đối chiếu PostgreSQL version và known issues.
- Xem CPU, memory, storage và logs.
- Dùng profiling hoặc công cụ chuyên sâu nếu bottleneck nội bộ cần phân tích.

`pg_blocking_pids()` không phải công cụ tổng quát để tìm blocker cho mọi LWLock waits.

### 5.4. BufferPin

`wait_event_type='BufferPin'` nghĩa backend chờ một buffer pin được giải phóng. Pin giữ buffer không bị tái sử dụng trong một số thao tác; nó không giống heavyweight lock.

Nguyên nhân có thể liên quan query/scan giữ buffer pin lâu, cursor hoặc code path xử lý buffer. Kiểm tra query đang active, transaction age, workload và event context. Không dùng lock mode diagnosis cho BufferPin.

### 5.5. Vì sao phân biệt quan trọng?

- Heavyweight Lock: tìm blocker, transaction và lock conflict.
- LWLock: điều tra internal contention/concurrency; thường cần metrics/profiling.
- BufferPin: tìm backend giữ pin lâu và đường truy cập buffer.

Gộp tất cả thành “database lock” sẽ dẫn tới hành động sai và có thể làm incident nặng hơn.

---

## 6. Chờ I/O: IO waits

### 6.1. IO wait là gì?

`wait_event_type='IO'` cho biết backend đang chờ một thao tác I/O được PostgreSQL instrument. Tùy event, đó có thể là:
- Đọc page từ data file.
- Ghi/extend data file.
- Flush/sync data file.
- Đọc/ghi/sync WAL.
- I/O trên SLRU hoặc temporary files.
- Các file quản lý nội bộ khác.

Tên event thay đổi theo major version. Ví dụ thường gặp gồm `DataFileRead`, `DataFileWrite`, `DataFileExtend`, `DataFileSync`, `WALRead`, `WALWrite` và `WALSync`.

### 6.2. Nhận diện I/O waits

~~~sql
SELECT
    pid,
    datname,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE wait_event_type = 'IO'
ORDER BY query_start;
~~~

Một query có nhiều DataFileRead waits có thể đang đọc nhiều pages không có trong shared buffers, nhưng phải xem plan, cache behavior và storage latency trước khi kết luận.

### 6.3. Read wait không nhất thiết là disk hỏng

DataFileRead có thể là hoạt động bình thường khi query cần page chưa có trong shared buffers. Nó trở thành vấn đề khi:
- Wait duration/volume tăng bất thường.
- Storage latency cao.
- Cache hit giảm cùng workload.
- Query plan đọc quá nhiều pages.
- Nhiều sessions cùng bị ảnh hưởng.
- Throughput giảm và request latency tăng.

Kiểm tra query plan, indexes, selectivity, table bloat, cache size và OS/storage metrics.

### 6.4. Write/extend/sync waits

- DataFileWrite: backend chờ ghi data file.
- DataFileExtend: chờ mở rộng relation file.
- DataFileSync: chờ sync/flush data file theo đường I/O.
- WALWrite/WALSync: chờ thao tác ghi/sync WAL theo event của version.

WAL I/O và data-file I/O có đặc điểm khác nhau. Một query COMMIT chậm có thể bị ảnh hưởng bởi WAL flush; checkpoint có thể tạo write pressure trên data files.

### 6.5. I/O wait và checkpoint

Checkpoint ghi dirty buffers xuống data files. Nếu checkpoint writeback tạo áp lực lớn, foreground backends có thể cạnh tranh storage bandwidth. Theo dõi:
- Checkpoint frequency/duration.
- Checkpoint write/sync time.
- WAL volume và checkpoint spikes.
- Storage throughput/latency/queue depth.
- Background writer/checkpointer activity.

Các checkpoint statistics columns thay đổi theo version; xem pg_stat_checkpointer hoặc pg_stat_bgwriter theo major version hiện tại.

### 6.6. I/O wait và temporary files

Sort/hash operations có thể spill ra temporary files khi memory không đủ hoặc query xử lý tập dữ liệu lớn. I/O trên temp files có thể làm query chậm dù data table reads không nhiều.

Kiểm tra:
- EXPLAIN (ANALYZE, BUFFERS).
- Temp blocks read/written trong query stats.
- work_mem và số operations đồng thời.
- Join/sort plan.
- Query cardinality estimates.

Không tăng work_mem toàn server một cách tùy tiện; nó có thể được dùng cho nhiều sort/hash nodes trên nhiều sessions.

### 6.7. pg_stat_io từ PostgreSQL 16

PostgreSQL 16 bổ sung pg_stat_io để quan sát I/O aggregates theo backend type, object và context. View/columns có thể mở rộng ở major releases sau đó.

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

Dùng view để phân tích patterns như reads, writes, extends, hits, evictions và timing nếu column có ở version. Đây là thống kê tổng hợp theo nhóm, không phải một dòng cho từng query hay từng PID.

### 6.8. pg_stat_database và track_io_timing

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    round(
        100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_pct,
    blk_read_time,
    blk_write_time
FROM pg_stat_database
WHERE datname = current_database();
~~~

blk_read_time và blk_write_time chỉ có ý nghĩa timing khi track_io_timing được bật. Setting này có thể tạo overhead tùy platform/workload; đo trên môi trường đại diện trước khi bật rộng.

Cache hit ratio cao không đảm bảo query nhanh. Một query có thể đọc hàng triệu buffer hits và vẫn tốn CPU; một cache hit ratio thấp trong workload sequential scan có thể hoàn toàn bình thường.

### 6.9. pg_stat_statements

Nếu extension pg_stat_statements được cài và cấu hình, có thể tìm query tiêu thụ nhiều reads hoặc temp writes:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_read,
    shared_blks_hit,
    temp_blks_read,
    temp_blks_written,
    query
FROM pg_stat_statements
ORDER BY shared_blks_read DESC
LIMIT 20;
~~~

Columns thay đổi theo version/extension version. Đây là aggregate query statistics, không phải wait event history. Dùng queryid và plan để xác định workload gây I/O.

### 6.10. EXPLAIN để điều tra I/O

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL)
SELECT *
FROM app.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 100;
~~~

ANALYZE thực thi query. Chỉ dùng với SELECT an toàn hoặc môi trường test; DML/DDL có thể thay đổi dữ liệu. BUFFERS cho biết buffer activity; WAL hiển thị WAL generated trên các versions hỗ trợ. Nếu bật track_io_timing, plan có thể hiển thị I/O timing.

### 6.11. Đối chiếu OS/storage

PostgreSQL wait events không thay thế metrics của storage layer. Kiểm tra:
- Device latency và queue depth.
- IOPS/throughput limits.
- Cloud volume burst credits/throttling.
- Filesystem saturation/free space.
- Network storage latency.
- CPU steal/host contention.
- Memory pressure/page cache.
- Disk errors và kernel logs.

Một query có DataFileRead wait có thể do query plan đọc quá nhiều pages hoặc storage chậm; cần bằng chứng từ cả database và OS.

### 6.12. Khi nào IO wait là bình thường?

- Initial cache warm-up.
- Bulk load/index build.
- Backup/restore.
- Sequential scan có chủ đích.
- Checkpoint hoặc vacuum.
- Workload tăng đột biến.

So sánh với baseline cùng giờ/ngày và workload. Alert theo duration/impact thay vì mọi lần xuất hiện.

---

## 7. Chờ client: Client waits

### 7.1. Client wait là gì?

wait_event_type='Client' cho biết backend đang chờ hoạt động trên client socket. Hai events thường gặp:

- ClientRead: PostgreSQL đang chờ client gửi dữ liệu/command tiếp theo.
- ClientWrite: PostgreSQL đang chờ gửi dữ liệu về client.

Đây là nhóm dễ bị hiểu nhầm vì client wait có thể là trạng thái bình thường của một connection idle.

### 7.2. ClientRead khi state=idle

Một connection pool giữ kết nối mở để tái sử dụng thường có:
- state='idle'.
- wait_event_type='Client'.
- wait_event='ClientRead'.

Backend đang chờ command tiếp theo. Đây không phải database bottleneck; đó là một connection nhàn rỗi.

### 7.3. ClientRead khi idle in transaction

Nếu session có:
- state='idle in transaction'.
- wait_event='ClientRead'.
- xact_start rất cũ.

PostgreSQL đang chờ client tiếp tục transaction, nhưng transaction vẫn mở. Nó có thể giữ locks/snapshot, làm vacuum không cleanup được dead tuples, giữ relation locks và gây bloat dù không có query active.

Đây là vấn đề lifecycle phía ứng dụng dù wait event là Client. Kiểm tra transaction age, owner, application name và code path.

### 7.4. ClientWrite

ClientWrite cho biết server đang cố gửi dữ liệu nhưng socket/client chưa nhận đủ để server tiếp tục. Nguyên nhân có thể:
- Client xử lý rows chậm.
- Ứng dụng không đọc hết result set.
- Network latency/loss/congestion.
- Result set quá lớn.
- Client process bị pause/GC/CPU-starved.
- Proxy/load balancer hoặc socket buffer bị nghẽn.

Không mặc định đây là PostgreSQL storage I/O. Server có thể đã hoàn tất việc đọc dữ liệu và đang bị backpressure ở đường trả kết quả.

### 7.5. Query trả quá nhiều rows

Một query không có LIMIT hoặc pagination có thể trả hàng triệu rows. PostgreSQL gửi kết quả; nếu client đọc chậm, backend có thể chờ ClientWrite. Giải pháp thường là:
- Giới hạn result set.
- Dùng pagination/keyset pagination.
- Xử lý streaming/batch đúng cách.
- Tránh fetch toàn bộ dữ liệu vào memory.
- Xem query plan và payload size.

### 7.6. ClientRead không có nghĩa ứng dụng bị lỗi

Connection pool bình thường giữ nhiều idle sessions. Số lượng ClientRead cao không phải bằng chứng database đang bị treo. Cần phân biệt:
- Idle, ngoài transaction: thường bình thường.
- Idle in transaction: có thể gây operational risk.
- Active query với ClientWrite: cần xem output/network.
- Connection count vượt pool budget: cần xem pool sizing và app lifecycle.

### 7.7. Client wait và connection pool

Theo dõi:
- Active/idle/idle-in-transaction counts.
- Pool max size và wait queue ở application.
- Connection churn.
- Client connection age.
- Transaction age.
- ClientWrite durations.
- Application CPU/GC/network.

PostgreSQL không biết đầy đủ trạng thái request ở connection pool. Cần correlate database PID/application_name với trace/request ID ở app nếu có.

### 7.8. Kiểm tra client waits

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - state_change AS time_in_state,
    clock_timestamp() - xact_start AS transaction_age,
    query
FROM pg_stat_activity
WHERE wait_event_type = 'Client'
ORDER BY state_change;
~~~

Đặc biệt xem state để diễn giải ClientRead/ClientWrite.

### 7.9. Khi client không đọc kết quả

Nếu nhiều sessions active/ClientWrite:
1. Xác định query/result size.
2. Kiểm tra client CPU/memory/GC.
3. Kiểm tra network throughput/retransmits.
4. Kiểm tra proxy/pool behavior.
5. Xem ứng dụng có consume rows tuần tự hay bỏ dở.
6. Giảm result size hoặc cải thiện client consumption.
7. Kiểm tra connection được đóng/cancel đúng cách.

### 7.10. Khi client giữ transaction

Nếu idle-in-transaction:
1. Xác định app/user/PID và transaction age.
2. Xem query cuối cùng và xact_start.
3. Kiểm tra blocker chain và vacuum impact.
4. Kiểm tra application logs/trace.
5. Sửa code đảm bảo commit/rollback trong mọi nhánh.
6. Dùng transaction timeout theo policy.
7. Terminate session chỉ khi owner/impact đã được xác nhận.

---

## 8. Bảng phân biệt nhanh Lock, I/O và Client

| Dấu hiệu | Chờ khóa | Chờ I/O | Chờ client |
|---|---|---|---|
| wait_event_type | Lock | IO | Client |
| Event ví dụ | transactionid, relation | DataFileRead, WALSync | ClientRead, ClientWrite |
| Nguyên nhân điển hình | Transaction khác giữ lock | Backend đợi read/write/flush | Client chưa gửi/đọc dữ liệu |
| Công cụ đầu tiên | pg_blocking_pids(), pg_locks | pg_stat_io, plan, OS metrics | state, app/network metrics |
| Tín hiệu cần tìm | Blocker và lock age | Latency/throughput/plan | Idle transaction hoặc slow consumer |
| Hành động thường gặp | Kết thúc/điều chỉnh blocker có kiểm soát | Tối ưu query hoặc xử lý storage | Sửa client/pool/network/result handling |

### 8.1. Ví dụ diễn giải

**Ví dụ A:** Query UPDATE ở trạng thái active, wait event Lock/transactionid, pg_blocking_pids trả về PID 1200. Điều tra transaction của PID 1200 trước.

**Ví dụ B:** Query SELECT active, wait event IO/DataFileRead, không có blocker. Kiểm tra plan, buffers, storage latency và cache.

**Ví dụ C:** Session idle, Client/ClientRead, không có transaction mở. Đây thường là pooled connection bình thường.

**Ví dụ D:** Session idle in transaction, Client/ClientRead, transaction age 25 phút. Điều tra application giữ transaction; nó có thể là blocker dù query hiện tại không active.

**Ví dụ E:** Query active, Client/ClientWrite và app CPU cao. Kiểm tra client consumption và network trước khi tăng database resources.

### 8.2. Wait event khác với CPU-bound query

Một query active với wait_event NULL có thể đang CPU-bound. Kiểm tra:
- CPU usage per process/host.
- EXPLAIN ANALYZE.
- Sort/hash/aggregation.
- Function CPU.
- Parallel workers.
- Cardinality estimates và plan.
- OS scheduler/load.

Không cố tìm blocker khi không có Lock wait hoặc evidence lock conflict.

---

## 9. Lấy mẫu wait events và phân tích lịch sử

### 9.1. pg_stat_activity là current snapshot

Mỗi lần query pg_stat_activity chỉ trả trạng thái tại thời điểm quan sát. Nếu query chờ lock 200 ms giữa hai lần polling 10 giây, dashboard có thể không bao giờ nhìn thấy wait đó.

Một lần không thấy wait không chứng minh không có wait. Một lần thấy wait cũng không cho biết nó kéo dài bao lâu trước đó.

### 9.2. Sampling định kỳ

Có thể lấy mẫu bằng monitoring agent hoặc job ngoài database:
- Timestamp UTC.
- PID và backend type.
- Database/user/application/client.
- State và wait_event_type/wait_event.
- Query ID nếu có.
- Query/transaction age.
- Blocking PID list.
- LSN hoặc I/O metrics liên quan khi cần.

Không cần lưu raw query text cho mọi sample. Ưu tiên query ID, application name, wait category và durations; bảo vệ thông tin nhạy cảm.

### 9.3. Sampling interval

Chọn interval theo mục tiêu:
- 1–5 giây: bắt waits ngắn và incident troubleshooting, nhưng telemetry volume cao hơn.
- 10–30 giây: dashboard vận hành thường ngày.
- 1 phút hoặc hơn: trend dài hạn, có thể bỏ lỡ wait ngắn.

Đây chỉ là gợi ý. Cần đo overhead và retention cost. Có thể dùng sampling nhanh khi alert kích hoạt rồi giảm tần suất khi hệ thống bình thường.

### 9.4. Đếm số samples theo wait group

Nếu đã lưu samples vào một monitoring table bên ngoài hoặc hệ thống metrics, có thể tổng hợp:
- Count theo wait_event_type/event.
- Distinct PIDs và query IDs.
- Số sample liên tiếp một backend ở cùng wait.
- Tỷ lệ samples có Lock/IO/Client.
- Wait group theo application/database.
- Correlation với latency và throughput.

Số samples không phải tổng wait milliseconds nếu interval không đều hoặc wait thay đổi giữa samples. Đừng đổi count thành thời gian chờ bằng cách nhân interval khi có missing samples hoặc sampling jitter.

### 9.5. pg_wait_sampling và công cụ mở rộng

Có extension bên thứ ba như pg_wait_sampling để thu thập lịch sử wait events trên các môi trường hỗ trợ. Extension cần được cài/cấu hình và kiểm tra compatibility với major version; nó không phải mặc định có sẵn trong mọi PostgreSQL installation.

Các monitoring vendors cũng có thể thu thập wait profiles. Xác nhận retention, sampling frequency, privacy và overhead trước khi bật.

### 9.6. Kết hợp pg_stat_statements

pg_stat_statements lưu aggregate execution statistics theo query. Nó hữu ích để tìm query tiêu tốn nhiều thời gian/blocks, nhưng không lưu wait-event timeline đầy đủ cho từng lần execution.

Dùng hai nguồn cùng nhau:
- Wait sampling: backend đang đợi gì.
- pg_stat_statements: query nào có workload/time/blocks cao.
- EXPLAIN: plan nào tạo ra workload đó.
- OS metrics: resource layer nào đang bão hòa.

### 9.7. Correlate với trace ứng dụng

Đặt application_name có cấu trúc, ví dụ service/env/role. Nếu ứng dụng có request ID hoặc trace ID, lưu mapping giữa request và PID/query ID ở application telemetry. PostgreSQL không tự biết request lifecycle của connection pool.

### 9.8. Query age không phải wait duration

`clock_timestamp() - query_start` là tổng thời gian từ lúc query bắt đầu, không phải thời gian query đã ở wait event hiện tại. `state_change` là thời điểm state gần nhất đổi; nó không cho biết event hiện tại bắt đầu khi nào nếu state không đổi mà wait event đã đổi.

Nếu cần wait duration chính xác, phải sampling đủ dày hoặc dùng wait-history instrumentation.

---

## 10. Dashboard và alerting

### 10.1. Dashboard theo wait category

Nên có:
- Active backends theo wait_event_type.
- Wait event top N.
- Active queries có wait.
- Lock waiters và blocker count.
- Longest transaction/idle-in-transaction age.
- I/O wait samples theo event.
- ClientRead/ClientWrite samples.
- Query latency/throughput.
- CPU, storage latency, network throughput.
- Application pool saturation.

### 10.2. Dashboard lock

Hiển thị:
- Waiter PID/app/query age.
- Blocker PID/app/state/xact age.
- Lock event/resource/mode.
- Number of blocked sessions.
- Root blocker/chain depth.
- Relation/table nếu có.
- Incident start và owner.

### 10.3. Dashboard I/O

Hiển thị:
- IO wait samples theo event.
- Read/write/sync timing.
- pg_stat_io counters theo backend/object/context trên PG16+.
- pg_stat_database blocks/timing.
- pg_stat_statements shared/temp blocks.
- Storage latency/IOPS/throughput/queue.
- Checkpoint activity và WAL rate.

### 10.4. Dashboard client

Hiển thị:
- ClientRead sessions idle ngoài transaction.
- Idle-in-transaction sessions và tuổi transaction.
- ClientWrite active sessions.
- Connection pool active/idle/waiting.
- Result size/rows returned.
- Network latency/retransmits.
- Application CPU/GC/consumer lag.

### 10.5. Alert mẫu cho Lock

Có thể cảnh báo khi:
- Có waiter Lock kéo dài hơn threshold.
- Một blocker giữ nhiều sessions.
- Transaction age vượt SLA.
- Idle-in-transaction giữ lock lâu.
- DDL migration chặn production traffic.

Ngưỡng phải dựa trên workload. Một lock wait ngắn trong transaction bình thường không cần alert.

### 10.6. Alert mẫu cho I/O

Cảnh báo khi đồng thời:
- IO wait sample tăng bất thường.
- Storage latency/queue vượt baseline.
- Query latency/throughput xấu đi.
- IOPS/throughput quota bị chạm.
- Checkpoint hoặc WAL sync pressure tăng.

Không alert chỉ vì DataFileRead xuất hiện; read waits có thể bình thường.

### 10.7. Alert mẫu cho Client

Cảnh báo khi:
- Active ClientWrite kéo dài và nhiều sessions bị ảnh hưởng.
- Idle-in-transaction vượt tuổi tối đa.
- Connection pool wait queue tăng.
- ClientWrite đi cùng network retransmits hoặc app CPU saturation.
- Connection count tăng bất thường.

ClientRead trên idle session ngoài transaction thường không phải alert.

### 10.8. Alert phải có ngữ cảnh

Một alert tốt cần:
- Cluster/database.
- Wait category/event.
- PID/query ID/application.
- Duration hoặc số samples liên tiếp.
- Blocker nếu có.
- Resource metrics tương ứng.
- Runbook link/owner.
- Last known good baseline.
- Clear condition.

---

## 11. Runbook: điều tra Lock waits

### 11.1. Xác định phạm vi

1. Lấy pg_stat_activity.
2. Lọc active + Lock wait.
3. Đếm số waiter và applications bị ảnh hưởng.
4. Ghi query age, transaction age.
5. Xác định bảng/operation đang bị chặn.

### 11.2. Tìm blocker

Dùng pg_blocking_pids() để lấy direct blockers. Xem:
- PID/user/application/client.
- State và xact_start.
- Query cuối/current query.
- Locks đang giữ.
- Transaction có thể đang chờ một blocker khác không.

Nếu blocker cũng đang chờ, đi ngược chain tới root blocker.

### 11.3. Phân loại blocker

- Long-running transaction đang cập nhật dữ liệu.
- Idle in transaction.
- DDL giữ ACCESS EXCLUSIVE.
- Batch job/import.
- Advisory lock do application.
- Maintenance task.
- Session orphaned nhưng connection còn mở.

### 11.4. Chọn hành động

Ưu tiên:
1. Liên hệ owner/application nếu blocker là transaction hợp lệ.
2. Để transaction kết thúc nếu thời gian còn chấp nhận được.
3. Dừng/điều chỉnh batch job theo runbook.
4. Cancel query nếu chỉ cần hủy statement và rollback an toàn.
5. Terminate session nếu cần giải phóng lock và đã đánh giá rollback/unknown outcome.

pg_cancel_backend(pid) yêu cầu cancel query; pg_terminate_backend(pid) đóng session và rollback transaction đang mở. Cả hai cần quyền và đánh giá impact. Không thực hiện tự động dựa trên một wait event.

### 11.5. Xác minh sau xử lý

- Waiter queue giảm.
- Query được tiếp tục hoặc client nhận error rõ.
- Blocker transaction kết thúc.
- Application retry có idempotency.
- Không phát sinh duplicate business action.
- Không còn lock storm.
- Ghi lại root cause và owner.

---

## 12. Runbook: điều tra I/O waits

### 12.1. Xác định event

Phân biệt DataFileRead/Write/Extend/Sync, WALRead/Write/Sync, temp/SLRU events theo version. Ghi số sessions, duration samples và query IDs.

### 12.2. Tìm query gây workload

Dùng pg_stat_statements để xếp hạng:
- shared_blks_read.
- temp_blks_read/written.
- total/mean execution time.
- Calls và rows.
- Query ID.

Chọn query đại diện và kiểm tra EXPLAIN (ANALYZE, BUFFERS). Chú ý ANALYZE thực thi query.

### 12.3. Kiểm tra storage

Đối chiếu database với OS/cloud:
- Latency/read/write IOPS.
- Throughput và queue depth.
- Burst credits/throttling.
- Volume saturation.
- Filesystem free space.
- Kernel/device errors.
- Network storage health.

### 12.4. Kiểm tra checkpoint/WAL

Nếu WALSync/WALWrite hoặc data file sync tăng:
- Xem commit rate và synchronous_commit.
- Xem checkpoint frequency/duration.
- Xem WAL generation và archive pressure.
- Kiểm tra storage fsync behavior.
- Kiểm tra backup/maintenance jobs đồng thời.

### 12.5. Kiểm tra query plan

Nếu DataFileRead cao:
- Có sequential scan ngoài dự kiến không?
- Index có phù hợp predicate/order không?
- Estimate rows khác actual rows nhiều không?
- Có bloat hoặc stats stale không?
- Query có trả quá nhiều rows?
- Có join strategy/sort/hash spill không?

### 12.6. Khắc phục và xác minh

Tùy nguyên nhân:
- Tối ưu SQL/index/statistics.
- Giảm temp spill.
- Điều chỉnh concurrency/work_mem cẩn thận.
- Cân bằng checkpoint/storage.
- Nâng storage tier hoặc quota.
- Dời backup/batch workload.
- Theo dõi latency và throughput sau thay đổi.

Không tăng shared_buffers/work_mem hoặc thay storage settings chỉ dựa trên một event name.

---

## 13. Runbook: điều tra Client waits

### 13.1. Phân loại session

Lọc Client waits và xem state:
- Idle + ClientRead: pooled connection chờ command.
- Idle in transaction + ClientRead: ứng dụng giữ transaction.
- Active + ClientWrite: server đang gửi result, client/network có thể chậm.

### 13.2. Idle in transaction

Kiểm tra transaction age, last query, application_name, blocker list và vacuum impact. Xác định code path không commit/rollback; ưu tiên sửa transaction lifecycle và timeout policy.

### 13.3. ClientWrite

Kiểm tra rows/bytes trả về, application consumer, network throughput/retransmits, proxy và client CPU/GC. Giảm payload, dùng pagination/streaming và đảm bảo app consume/close result đúng cách.

### 13.4. Connection pool

So sánh PostgreSQL backend count với pool metrics:
- Pool max/active/idle.
- Wait queue và acquire timeout.
- Connection leak.
- Long transaction.
- Pool reset/session state.
- Request duration.

Nhiều idle connections có thể là bình thường; nhiều idle-in-transaction sessions cần xử lý.

### 13.5. Xác minh

Sau remediation:
- Idle-in-transaction count/age giảm.
- ClientWrite waits giảm.
- Pool acquire latency cải thiện.
- Không tăng connection churn.
- App logs không còn leaked transaction/result cursor.
- Không còn locks/snapshots bị giữ lâu.

---

## 14. Các lỗi diễn giải thường gặp

### 14.1. “Có wait event nghĩa là database bị nghẽn”

Sai. Wait event là trạng thái hiện tại. Cần duration, frequency, impact và baseline.

### 14.2. “ClientRead luôn là client lỗi”

Sai. Idle connection pool thường chờ ClientRead. Chỉ điều tra sâu khi session giữ transaction hoặc connection lifecycle bất thường.

### 14.3. “ClientWrite là disk chậm”

Không nhất thiết. ClientWrite liên quan server-to-client socket; client chậm, network hoặc result size có thể là nguyên nhân.

### 14.4. “Lock wait thì terminate blocker”

Không phải lúc nào cũng đúng. Blocker có thể là transaction hợp lệ, migration hoặc batch. Terminate gây rollback và có thể làm ứng dụng có unknown outcome.

### 14.5. “IO wait chứng minh storage device hỏng”

Không. Query có thể đọc nhiều pages, cache miss, temp spill hoặc workload cạnh tranh. Cần đối chiếu storage metrics và plan.

### 14.6. “LWLock giống row lock”

Không. LWLock bảo vệ internal shared-memory structures; không dùng pg_blocking_pids như công cụ tổng quát để xử lý.

### 14.7. “Query age chính là wait duration”

Không. query_start đo tổng thời gian từ lúc query bắt đầu. Wait event hiện tại có thể chỉ mới xuất hiện gần đây.

### 14.8. “Không có wait event tức là query nhanh”

Không. Query có thể CPU-bound, bị scheduler delay hoặc đang thực thi đoạn code không có wait point. Kiểm tra CPU/plan.

### 14.9. “Một sample đủ để kết luận”

Không. Wait có thể thay đổi liên tục. Sampling và correlation với metrics lịch sử mới cho thấy pattern.

### 14.10. “pg_stat_activity lưu lịch sử”

Không. Đây là snapshot hiện tại. Cần hệ thống sampling hoặc extension để có wait history.

---

## 15. Tài liệu tham khảo PostgreSQL

Ưu tiên tài liệu đúng major version:

- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_activity, pg_locks và wait events.
- [PostgreSQL — Wait Events](https://www.postgresql.org/docs/current/monitoring-stats.html#WAIT-EVENT-TABLE): danh mục wait event và ý nghĩa.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock modes và conflict behavior.
- [PostgreSQL — System Catalogs: pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html): thông tin lock.
- [PostgreSQL — pg_stat_io](https://www.postgresql.org/docs/current/monitoring-stats.html): thống kê I/O, tùy major version.
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): query-level aggregate statistics.
- [PostgreSQL — Runtime Statistics Configuration](https://www.postgresql.org/docs/current/runtime-config-statistics.html): track_io_timing và thống kê runtime.

Các trang /current/ có thể trỏ tới major version mới hơn. Xác minh wait event names, view columns và extension support theo phiên bản đang vận hành.

---

## 16. Bài lab: đọc wait events

### 16.1. Xem trạng thái backend

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS xact_age
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
~~~

Ghi lại:
- Sessions active.
- Sessions idle.
- Idle-in-transaction sessions.
- Các wait categories đang xuất hiện.

### 16.2. Tạo ClientRead bình thường

Mở một session psql và để prompt chờ command. Từ session khác quan sát pg_stat_activity. Session đang chờ input có thể xuất hiện ClientRead/idle. Đây là connection bình thường.

### 16.3. Tạo idle in transaction

Trong một session lab:

~~~sql
BEGIN;
SELECT now();
-- Giữ session mở, chưa COMMIT hoặc ROLLBACK.
~~~

Từ session khác xem state, ClientRead và xact_start. Kết thúc lab bằng:

~~~sql
ROLLBACK;
~~~

Không để transaction test mở lâu trên môi trường dùng chung.

### 16.4. Tạo Lock wait

Session A:

~~~sql
CREATE TABLE IF NOT EXISTS wait_lab (
    id integer PRIMARY KEY,
    value text
);

INSERT INTO wait_lab VALUES (1, 'before')
ON CONFLICT (id) DO UPDATE SET value = EXCLUDED.value;

BEGIN;
UPDATE wait_lab SET value = 'session-a' WHERE id = 1;
-- Giữ transaction mở.
~~~

Session B:

~~~sql
UPDATE wait_lab SET value = 'session-b' WHERE id = 1;
~~~

Session B có thể chờ row lock/transaction của session A. Quan sát pg_stat_activity, pg_blocking_pids và pg_locks. Sau đó COMMIT hoặc ROLLBACK session A.

### 16.5. Tạo I/O workload

Trên dữ liệu lab đủ lớn, chạy sequential scan hoặc sort có chủ đích. Quan sát wait events và EXPLAIN (ANALYZE, BUFFERS). Kết quả phụ thuộc cache, storage và dataset; không nhất thiết luôn thấy IO wait vì dữ liệu có thể ở memory.

### 16.6. Quan sát pg_stat_io

Trên PostgreSQL 16+:

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

Chạy trước/sau workload và so sánh counters/timing. View aggregate theo dimensions, không map trực tiếp từng row về PID.

### 16.7. Thử ClientWrite

Dùng một query trả nhiều rows trong lab và client đọc chậm có kiểm soát. Quan sát ClientWrite nếu socket backpressure xuất hiện. Không tạo result lớn trên production hoặc làm cạn memory/network.

---

## 17. Bài tập thực hành

Các bài tập dùng PostgreSQL lab. Không kill session hoặc tạo I/O overload trên production chỉ để quan sát wait.

### Bài 1 — Wait event

Wait event cho biết điều gì? Nó có phải error code không?

### Bài 2 — Hai trường chính

Phân biệt wait_event_type và wait_event.

### Bài 3 — State active

Một backend state=active, wait_event_type=Lock. Backend có đang chạy CPU liên tục không?

### Bài 4 — ClientRead

Một session idle + ClientRead có nhất thiết là lỗi không? Vì sao?

### Bài 5 — ClientWrite

ClientWrite thường cho biết điều gì? Nêu ba nguyên nhân có thể.

### Bài 6 — Lock

Một query UPDATE chờ Lock/transactionid. Công cụ nào giúp tìm blocker trực tiếp?

### Bài 7 — Blocker query

Viết query hiển thị waiter PID, blocker PID, application_name và blocker transaction age.

### Bài 8 — pg_locks

granted=false có nghĩa gì? Vì sao query pg_locks chưa đủ để tìm toàn bộ blocker chain?

### Bài 9 — Idle in transaction

Vì sao idle in transaction có thể gây bloat hoặc chặn DDL dù query không active?

### Bài 10 — LWLock

LWLock khác heavyweight Lock như thế nào? Có nên dùng pg_blocking_pids để tìm blocker cho mọi LWLock không?

### Bài 11 — BufferPin

BufferPin wait mô tả điều gì? Vì sao không nên coi nó là row lock?

### Bài 12 — DataFileRead

DataFileRead có chứng minh storage bị hỏng không? Cần kiểm tra gì?

### Bài 13 — WALSync

WALSync wait gợi ý backend đang chờ điều gì? Nêu một số nguyên nhân có thể.

### Bài 14 — Temporary files

Query sort/hash spill ra temp files có thể tạo loại I/O nào? Xem metric nào?

### Bài 15 — pg_stat_io

pg_stat_io có từ PostgreSQL major version nào? Nó cung cấp thống kê theo những dimensions nào?

### Bài 16 — track_io_timing

blk_read_time/blk_write_time có timing hữu ích khi nào? Cần cân nhắc gì trước khi bật?

### Bài 17 — Cache hit ratio

Vì sao cache hit ratio cao không đảm bảo query nhanh?

### Bài 18 — Query age

query_start age có bằng wait duration hiện tại không? Giải thích.

### Bài 19 — Sampling

Vì sao một lần query pg_stat_activity không đủ để kết luận wait pattern?

### Bài 20 — Historical waits

pg_stat_activity có lưu wait history không? Có thể dùng phương án nào để thu thập lịch sử?

### Bài 21 — pg_stat_statements

pg_stat_statements và wait sampling bổ sung cho nhau như thế nào?

### Bài 22 — CPU-bound

Một query active nhưng wait_event NULL. Nêu các hướng điều tra ngoài lock/I/O.

### Bài 23 — Lock chain

Một blocker cũng đang chờ một backend khác. Cần tìm node nào trong chain để giải quyết root cause?

### Bài 24 — Terminate blocker

Vì sao không nên terminate blocker chỉ dựa trên việc nó đang chặn nhiều sessions?

### Bài 25 — ClientRead trong transaction

Một session idle in transaction + ClientRead trong 20 phút. Cần kiểm tra những thông tin nào?

### Bài 26 — ClientWrite

Query trả hàng triệu rows và backend chờ ClientWrite. Nêu các biện pháp phía application/query.

### Bài 27 — Wait taxonomy

Phân biệt Lock, IO và Client bằng event examples và công cụ đầu tiên nên dùng.

### Bài 28 — Checkpoint

Checkpoint có thể ảnh hưởng I/O waits như thế nào? Nêu metrics cần correlate.

### Bài 29 — Alerting

Vì sao không nên alert chỉ khi wait_event_type='IO' xuất hiện?

### Bài 30 — Incident tổng hợp

Một dashboard cho thấy 50 backend active/Lock, 1 blocker idle in transaction 30 phút, 200 sessions idle/ClientRead. Hãy phân loại tác động và ưu tiên xử lý.

---

## 18. Lời giải — bài 1 đến 15

### Bài 1 — Wait event

Nó mô tả điểm backend/process đang chờ tại thời điểm lấy mẫu. Nó không phải error code; wait có thể bình thường hoặc là dấu hiệu bottleneck tùy duration/impact.

### Bài 2 — Hai trường chính

wait_event_type là category như Lock/IO/Client; wait_event là tên cụ thể như transactionid/DataFileRead/ClientRead.

### Bài 3 — State active

Không. Active nghĩa query đang được thực thi; khi wait event có giá trị, backend hiện đang chờ ở wait point thay vì tiến triển CPU liên tục.

### Bài 4 — ClientRead

Không. Idle connection trong pool thường chờ ClientRead để nhận command tiếp theo. Chỉ đáng lo khi giữ transaction, quá nhiều connections hoặc lifecycle bất thường.

### Bài 5 — ClientWrite

Server đang chờ gửi dữ liệu tới client. Nguyên nhân có thể là client consume chậm, network/proxy nghẽn hoặc result set quá lớn.

### Bài 6 — Lock

Dùng pg_blocking_pids(waiter_pid) để lấy blocker trực tiếp; sau đó xem pg_stat_activity và pg_locks.

### Bài 7 — Blocker query

~~~sql
SELECT
    w.pid AS waiter_pid,
    w.application_name AS waiter_app,
    b.pid AS blocker_pid,
    b.application_name AS blocker_app,
    clock_timestamp() - b.xact_start AS blocker_xact_age
FROM pg_stat_activity AS w
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(w.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS b
    ON b.pid = p.blocker_pid;
~~~

### Bài 8 — pg_locks

granted=false là lock request đang chờ. pg_locks cho biết requests/held locks nhưng việc ghép conflict chain thủ công phức tạp; pg_blocking_pids tính direct blockers thuận tiện hơn.

### Bài 9 — Idle in transaction

Transaction còn mở có thể giữ locks và snapshot lâu, ngăn vacuum cleanup dead tuples và làm DDL chờ lock. Session không chạy query nhưng transaction vẫn tồn tại.

### Bài 10 — LWLock

LWLock là synchronization primitive nội bộ cho shared-memory structures; heavyweight Lock điều phối database objects/transactions. pg_blocking_pids chủ yếu dùng cho heavyweight lock blockers, không phải công cụ tổng quát cho mọi LWLock.

### Bài 11 — BufferPin

Backend đang chờ một shared buffer pin được giải phóng. Pin bảo vệ buffer khỏi reuse trong một thao tác; nó không phải row-level lock.

### Bài 12 — DataFileRead

Không. Nó cho biết backend chờ đọc data file. Kiểm tra query plan, buffer reads/hits, storage latency, IOPS/queue, cache và workload.

### Bài 13 — WALSync

Backend/process đang chờ WAL sync/flush theo event semantics của version. Có thể do commit fsync, storage latency, checkpoint/WAL activity hoặc concurrency.

### Bài 14 — Temporary files

Sort/hash spill có thể tạo temp file reads/writes. Xem temp_blks_read/written trong pg_stat_statements, EXPLAIN BUFFERS, work_mem và query plan.

### Bài 15 — pg_stat_io

pg_stat_io được thêm từ PostgreSQL 16. Nó tổng hợp I/O theo backend_type, object và context; columns cụ thể cần xem theo major version.

### Bài 16 — track_io_timing

blk_read_time/blk_write_time hữu ích khi track_io_timing được bật. Đánh giá overhead trên platform/workload, quyền cấu hình và baseline trước khi bật rộng.

### Bài 17 — Cache hit ratio

Query có thể đọc rất nhiều buffers đã cache và vẫn tốn CPU/joins/sorts; hit ratio không phản ánh số lượng pages tuyệt đối, plan quality hay storage latency toàn hệ thống.

### Bài 18 — Query age

Không. query_start age là tổng thời gian từ lúc query bắt đầu; query có thể chuyển qua nhiều wait events hoặc chạy CPU giữa các lần chờ.

### Bài 19 — Sampling

Wait event có thể thay đổi nhanh và pg_stat_activity chỉ là snapshot. Một sample có thể bỏ lỡ wait ngắn hoặc không phản ánh duration/impact. Lấy mẫu lặp và correlate metrics.

### Bài 20 — Historical waits

pg_stat_activity không lưu lịch sử. Dùng monitoring agent tự sample, extension như pg_wait_sampling nếu tương thích, hoặc monitoring platform có wait profiling.

### Bài 21 — pg_stat_statements

pg_stat_statements cho aggregate query workload/time/blocks; wait sampling cho biết backend chờ gì theo thời gian. Kết hợp để tìm query và resource bottleneck.

### Bài 22 — CPU-bound

Kiểm tra CPU/process utilization, EXPLAIN ANALYZE, cardinality estimates, sort/hash/aggregation, functions, parallel workers và OS scheduler/load.

### Bài 23 — Lock chain

Đi ngược blocker chain tới root blocker, tức backend đang giữ resource khiến các waits phía sau không tiến triển. Xem transaction age và business owner của root blocker.

### Bài 24 — Terminate blocker

Blocker có thể là transaction hợp lệ hoặc migration quan trọng. Terminate gây rollback, tăng I/O và tạo unknown outcome phía client; cần xác định owner/impact trước.

### Bài 25 — ClientRead trong transaction

Kiểm tra PID/user/application/client, xact_start, state_change, query cuối, locks đang giữ, pg_blocking_pids, vacuum impact, application trace và lý do code chưa commit/rollback.

### Bài 26 — ClientWrite

Giảm result size, thêm LIMIT/pagination, dùng streaming/batching, tối ưu payload, đảm bảo client đọc hết result set, kiểm tra client CPU/GC và network/proxy.

### Bài 27 — Wait taxonomy

- Lock/transactionid: query chờ transaction/row conflict; dùng pg_blocking_pids và pg_locks.
- IO/DataFileRead hoặc WALSync: chờ file I/O; dùng pg_stat_io, plan và OS/storage metrics.
- Client/ClientRead hoặc ClientWrite: chờ socket; xem state, app, pool và network.

### Bài 28 — Checkpoint

Checkpoint ghi dirty buffers xuống data files, có thể tạo write/sync pressure và cạnh tranh storage với foreground queries. Correlate checkpoint frequency/duration, WAL volume, storage latency/queue và IO waits.

### Bài 29 — Alerting

IO waits có thể là bình thường trong cache warm-up, scans, backup hoặc vacuum. Alert cần duration/frequency tăng cùng latency/throughput/resource saturation và baseline.

### Bài 30 — Incident tổng hợp

50 backend active/Lock có thể bị chặn bởi một root blocker; ưu tiên điều tra blocker idle-in-transaction 30 phút, xác định owner/locks/business impact và xử lý có kiểm soát. 200 idle/ClientRead ngoài transaction có thể là pool bình thường; xác nhận state và pool budget, không coi đó là 200 lỗi. Sau khi xử lý blocker, kiểm tra waiters được giải phóng, vacuum/transaction age và application retry.

---

## 19. Bảng quyết định nhanh

| Quan sát | Cách diễn giải ban đầu | Bước tiếp theo |
|---|---|---|
| active + Lock | Query đang chờ heavyweight lock | pg_blocking_pids, pg_locks, blocker transaction |
| active + IO | Backend chờ thao tác I/O | Xem event, plan, pg_stat_io và storage |
| idle + ClientRead | Connection chờ command mới | Thường bình thường; kiểm tra pool |
| idle in transaction + ClientRead | Transaction mở nhưng client chưa gửi tiếp | Xem xact age, locks, app lifecycle |
| active + ClientWrite | Server chờ gửi kết quả | Kiểm tra client consumption/network/result size |
| active + LWLock | Internal shared-memory contention | Xem event cụ thể, concurrency và profiling |
| active + BufferPin | Chờ buffer pin được giải phóng | Tìm workload giữ pin/scan lâu |
| active + wait_event NULL | Không có wait point tại sample | Kiểm tra CPU, plan và OS scheduler |
| nhiều WALSync waits | Có thể có commit/WAL flush pressure | Xem storage fsync, commit rate, WAL/checkpoint |
| DataFileRead tăng | Read I/O/cache workload tăng | Xem buffers, query plan, storage latency |

---

## 20. Mẫu báo cáo incident wait event

~~~text
Incident ID:
Observed at (UTC):
Cluster/database:
PostgreSQL version:
Affected application/service:
Affected PIDs/query IDs:
Wait event type/event:
Number of affected backends:
Longest query age:
Oldest transaction age:
Blocker PID(s), if any:
Query plan / I/O evidence:
Storage/network/application evidence:
User-visible impact:
Mitigation:
Root cause:
Follow-up action owner:
Retest/verification:
~~~

### 20.1. Mẫu báo cáo Lock

~~~text
Waiter PID/app:
Blocker PID/app:
Lock type/mode/resource:
Blocker transaction age:
Blocker state/query:
Blocked sessions:
Action taken:
Rollback/unknown outcome:
Verification:
~~~

### 20.2. Mẫu báo cáo I/O

~~~text
Wait event(s):
Affected query IDs:
Read/write/sync pattern:
pg_stat_io / pg_stat_database evidence:
EXPLAIN BUFFERS evidence:
Storage latency/IOPS/queue:
Mitigation:
Verification:
~~~

### 20.3. Mẫu báo cáo Client

~~~text
Client wait event:
Session state:
Application/pool:
Transaction age:
Result size/rows:
Network/client CPU/GC:
Application root cause:
Mitigation:
Verification:
~~~

---

## 21. Tổng kết

Wait events cho biết PostgreSQL backend đang chờ tại điểm nào, nhưng phải đọc cùng session state, query/transaction age và resource metrics mới xác định được nguyên nhân.

Các điểm cần nhớ:

1. `wait_event_type` là nhóm wait; `wait_event` là tên cụ thể.
2. `pg_stat_activity` chỉ là snapshot hiện tại, không phải lịch sử wait.
3. `active` có thể đang chờ; `wait_event IS NULL` không tự chứng minh query nhanh.
4. `Lock` thường cần tìm blocker bằng `pg_blocking_pids()` và kiểm tra `pg_locks`.
5. `LWLock` và `BufferPin` khác heavyweight SQL locks; không dùng cùng một cách xử lý.
6. `IO` cần được đối chiếu với query plan, buffer statistics, pg_stat_io và OS/storage metrics.
7. `pg_stat_io` có từ PostgreSQL 16; view/columns thay đổi theo version.
8. `track_io_timing` cần bật để có read/write timing trong các thống kê tương ứng; cân nhắc overhead.
9. `ClientRead` trên session idle ngoài transaction thường bình thường.
10. `ClientRead` trên idle-in-transaction có thể giữ locks/snapshot và cản vacuum.
11. `ClientWrite` thường gợi ý server bị backpressure khi gửi result; xem client/network/payload.
12. Query age không phải wait duration.
13. Sampling nhiều lần và correlation với app/OS metrics giúp nhận ra pattern.
14. Không terminate blocker chỉ dựa trên wait event; xác định owner, rollback impact và business outcome.
15. Alert cần duration/frequency/impact, không alert mọi lần wait xuất hiện.
16. Wait diagnosis phải dẫn tới xác minh sau remediation: query tiếp tục, queue giảm, latency phục hồi và không tạo side effects.

Quy trình điều tra: **lấy snapshot pg_stat_activity → phân loại state và wait_event_type → tìm blocker hoặc query/resource gây wait → đối chiếu I/O/network/application metrics → chọn remediation có kiểm soát → lấy mẫu lại và xác nhận tác động đã hết**.
