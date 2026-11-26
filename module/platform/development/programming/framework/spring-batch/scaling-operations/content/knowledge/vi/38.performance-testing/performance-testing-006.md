# Test throughput khi database chậm trong Spring Batch

> **Chương:** Performance testing
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán phù hợp; đo nút thắt, bảo đảm thread safety, retry/restart và lựa chọn kiến trúc theo tài nguyên thực tế.

Một job Spring Batch có thể xử lý 100.000 bản ghi/giây khi database khỏe, nhưng giảm xuống 8.000 bản ghi/giây khi DB phải chia sẻ tài nguyên với ứng dụng OLTP, gặp lock contention hoặc mất nhiều thời gian chờ connection. Khi đó, tăng từ 8 lên 32 worker **có thể làm throughput giảm thêm**, dù CPU worker vẫn rảnh. Nếu chỉ nhìn `writeCount` hoặc tổng thời gian job, nhóm vận hành dễ kết luận sai rằng cần nhiều thread hơn.

**Test throughput khi database chậm** là một thí nghiệm có kiểm soát, vừa đo **năng lực xử lý thực** vừa chứng minh **tính đúng của dữ liệu sau timeout, rollback, retry và restart**. Thay vì gắn một `Thread.sleep(...)` vào processor rồi gọi đó là "DB chậm", bài học này chỉ ra cách tách **query/transaction latency**, **connection-pool wait**, **lock contention**, **I/O pressure** và **network latency** — vì mỗi nguyên nhân có cách tối ưu khác nhau.

## Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

1. Định nghĩa throughput theo **unique business items hoàn tất/giây** và phân biệt với `readCount`, `writeCount`, attempts, commits và request rate.
2. Xây baseline có thể tái lập: snapshot input, workload distribution, DB schema/index, chunk size, worker concurrency, pool và warm-up giống nhau.
3. Mô phỏng **DB chậm** bằng các cơ chế riêng: SQL delay có kiểm soát, query/lock contention, network proxy và connection pool saturation.
4. Thiết kế ma trận baseline → tăng worker → DB slowdown → soak → failure/recovery → restart; tránh thay đồng thời nhiều biến.
5. Đo throughput, P50/P95/P99, lock/pool waits, số transaction, rollback/retry, queue lag, resource saturation và backlog.
6. Suy luận vì sao **chunk size, số workers, DB connections và transaction duration** liên hệ nhau, và khi nào tăng concurrency phản tác dụng.
7. Dùng Java/Spring Batch 5.x, PostgreSQL, Micrometer và PromQL để instrument kết quả có thể kiểm chứng.
8. Đưa ra ngưỡng dừng thử nghiệm, SLO pass/fail, mẫu báo cáo và runbook khi benchmark phát hiện bottleneck.

## 1. Một bài toán đo hiệu năng có tiêu chí rõ ràng

Giả sử doanh nghiệp cần nhập **12 triệu giao dịch** trong một đêm, qua Spring Batch với PostgreSQL:

- Input là snapshot bất biến, có **12.000.000 business operation IDs duy nhất**.
- Mỗi item cần validate, transform và ghi tối đa một lần về mặt nghiệp vụ.
- Chunk size ban đầu: **200**.
- Thử 1, 2, 4, 8, 16 worker threads/partitions, sau đó chọn mức phù hợp.
- Có thêm workload OLTP mô phỏng; một số lúc DB lock wait tăng.
- Deadline: hoàn tất nhập liệu, đối soát và publish trước **06:00**.

Một câu hỏi benchmark hữu ích không phải "càng nhiều worker càng nhanh?" mà là:

> Với input và resources không đổi, khi DB latency tăng từ bình thường lên một mức xác định, số worker nào tạo **throughput business hợp lệ tốt nhất** mà vẫn giữ P95 latency, lock waits, DB pool wait, retry rate và dữ liệu đầu ra trong ngưỡng chấp nhận?

### Các đại lượng đầu ra của thử nghiệm

| Chỉ số | Mục đích | Cách diễn giải |
| --- | --- | --- |
| **Unique committed items/s** | Throughput nghiệp vụ | Chỉ đếm các operation IDs thực sự có outcome hợp lệ |
| **Wall-clock duration** | Thời gian hoàn tất toàn job | Từ mốc bắt đầu xác định đến trạng thái terminal + gate được quy định |
| **Chunk/transaction duration P95/P99** | Độ trễ tail của xử lý/DB | Phải nói rõ bắt đầu/kết thúc đo ở đâu |
| **DB connection acquisition wait** | Pool có bị bão hòa không | Thời gian chờ lấy JDBC connection |
| **DB query/lock wait** | SQL có bị block không | Phân biệt xử lý SQL với chờ lock |
| **Rollback/retry/skip** | Mức độ khuếch đại tải | Thông lượng "thành công" có thể giảm dù attempts tăng |
| **Worker active/queue age** | Concurrency thực và backlog | Worker configured khác worker đang làm việc |
| **Input-output reconciliation** | Tính đúng | Phát hiện thiếu, trùng và side effect chưa rõ |

**Chỉ benchmark thành công khi cả hiệu năng và tính đúng cùng đạt.** Job ghi được 11.999.000 rows thay vì 12 triệu rồi báo nhanh không phải là kết quả tốt hơn.

## 2. Phân biệt năm kiểu "database chậm"

"DB latency 100 ms" không đủ thông tin để tái lập một nút thắt. Cần xác định **100 ms phát sinh ở đâu**.

| Kiểu chậm | Cơ chế thường gặp | Dấu hiệu quan sát | Hướng can thiệp |
| --- | --- | --- | --- |
| **SQL execution latency** | Query plan kém, index không phù hợp, disk I/O | SQL duration cao; CPU/IO của DB tăng | Index, query plan, batch statement |
| **Transaction/commit latency** | WAL flush, synchronous replication, transaction dài | Commit tail latency/IO wait cao | Điều chỉnh chunk/transaction và storage theo bằng chứng |
| **Lock contention** | Workers cùng cập nhật hot rows/index/key range | Lock wait/deadlock/rollback tăng | Thay partition key, giảm cạnh tranh |
| **Connection-pool wait** | Nhiều threads cần connection hơn pool size | Hikari pending/wait time cao | Hạn chế concurrency, sizing pool, rút ngắn transaction |
| **Network/service latency** | RTT, proxy, packet delay, service endpoint xa | JDBC round-trip tăng, DB CPU chưa bão hòa | Đặt gần DB, giảm số round-trips, batching |

Ngoài ra, **quá nhiều metadata writes vào `JobRepository`** cũng có thể khiến job chậm, dù business database chưa quá tải. Phải đo **business datasource** và **Batch metadata datasource** riêng khi chúng là các nguồn khác nhau.

### Không dùng một delay injection để đại diện tất cả

~~~text
Thread.sleep(100) trước writer:
  trì hoãn worker trước DB, có thể không chiếm DB connection.

SELECT pg_sleep(0.1) trong cùng chunk transaction:
  giữ JDBC connection và kéo dài transaction, nhưng không tự
  tạo lock contention hoặc storage I/O chậm.

Network proxy delay:
  tăng thời gian request/response, không đồng nghĩa SQL CPU tăng.

Hot row updates:
  tạo lock serialization/deadlock risk theo workload cụ thể.
~~~

Thí nghiệm phải **ghi rõ injection nào được dùng**; nếu không, kết luận "DB chậm thì cần X workers" sẽ không có giá trị ngoại suy.

## 3. Kiến trúc tham chiếu và nơi đặt phép đo

~~~mermaid
flowchart LR
    S[("Sealed input snapshot")] --> M["Batch manager/reader"]
    M --> C["Chunk / partition work"]
    C --> W1["Worker 1"]
    C --> W2["Worker 2"]
    C --> W3["Worker N"]
    W1 --> POOL["JDBC/Hikari pool"]
    W2 --> POOL
    W3 --> POOL
    POOL --> DB[("PostgreSQL business DB")]
    W1 --> JR[("JobRepository")]
    W2 --> JR
    W3 --> JR
    DB --> RECON["Business reconciliation"]
    JR --> OBS["Batch metadata + telemetry"]
    POOL --> OBS
    DB --> OBS
~~~

Sơ đồ là mô hình logic. Nếu remote chunking, manager đọc/chia items, worker process/write; nếu remote partitioning, mỗi worker có reader, processor và writer cho phạm vi input riêng. Hai mô hình có **concurrency và checkpoint khác nhau**, nên phải ghi **mô hình được đo**.

### Các đoạn thời gian trong một chunk

~~~text
T_chunk =
    T_wait_for_task
  + T_reader/processor
  + T_wait_for_connection
  + T_sql_execute
  + T_lock_wait
  + T_commit
  + T_retry/rollback overhead (nếu có)
  + T_middleware (nếu remote)
~~~

Đây là **phân rã khái niệm**, không phải các thời gian luôn tách rời tuyệt đối: lock wait có thể đã nằm trong SQL execution time; connection wait có thể đã nằm trong writer duration. **Không cộng trực tiếp các metric chồng lấn** để ra chunk duration.

Đặc biệt, timer bao quanh `ItemWriter.write(...)` **không mặc định bao gồm JDBC transaction commit**: commit có thể diễn ra sau khi writer trả về. Để đo commit latency, phải instrument transaction boundary hoặc dùng datasource/proxy/DB telemetry có ngữ nghĩa phù hợp.

## 4. Bất biến dữ liệu phải cố định trước khi chạy test

Nếu input, schema hoặc lượng dữ liệu thay đổi, hai lần benchmark không so sánh được.

### 4.1. Input manifest

~~~yaml
datasetId: perf-orders-v1
expectedItemCount: 12000000
schemaVersion: order-v2
source:
  type: immutable-files
  manifestId: orders-perf-2026-11-25-v1
  checksumAlgorithm: SHA-256
  # Mỗi file/version/checksum phải có trong manifest thật.
distribution:
  tenants: 1000
  hotTenantPercent: 5
  operationTypes:
    debit: 50
    credit: 50
~~~

Các con số là fixture minh họa. Metadata như `datasetId`, source version, hash, timestamp và seed tạo dữ liệu phải được ghi vào báo cáo. Không gọi LIST/SELECT không nhất quán rồi lấy tập input khác cho mỗi run.

### 4.2. Phân phối dữ liệu quan trọng hơn số records

Cùng 12 triệu records nhưng:

- Dataset A ghi vào 12 triệu keys độc lập.
- Dataset B có 70% records cập nhật 100 hot account rows.
- Dataset C có payload 10 KB và nhiều secondary indexes.

Ba dataset có **lock contention, I/O và WAL hoàn toàn khác nhau**. Để mô phỏng production, phải có:

1. Phân phối payload sizes.
2. Tỷ lệ inserts/updates/upserts.
3. Tỷ lệ hot keys và multi-tenant skew.
4. Tần suất duplicate/replay hợp lệ.
5. Indexes, constraints, triggers và foreign keys thực tế.
6. Batch writer/SQL giống production.
7. Tỷ lệ rows bị filter/skip đúng business rules.

Chỉ dùng `SELECT pg_sleep(...)` mà bỏ qua phân phối key khiến thí nghiệm thiếu một phần quan trọng của vấn đề.

### 4.3. Output và idempotency

Ví dụ bảng test PostgreSQL:

~~~sql
CREATE TABLE perf_import_result (
    dataset_id     VARCHAR(120) NOT NULL,
    operation_id   VARCHAR(160) NOT NULL,
    tenant_id      VARCHAR(80) NOT NULL,
    amount_minor   BIGINT NOT NULL,
    payload_hash   VARCHAR(128) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (dataset_id, operation_id)
);

CREATE INDEX idx_perf_result_tenant
ON perf_import_result (dataset_id, tenant_id);
~~~

`PRIMARY KEY` giúp phát hiện duplicate business operation. Nếu writer dùng upsert/idempotent no-op, phải xác minh **same key + same payload** và báo conflict nếu payload khác; đừng chỉ `ON CONFLICT DO NOTHING` để giấu dữ liệu bị sửa.

### 4.4. Reconciliation cuối mỗi run

~~~text
expected unique operation IDs
  = successfully applied unique IDs
  + explicitly rejected IDs (nếu policy cho phép)

Không tồn tại:
  missing mandatory input
  duplicate business effects
  unaccounted UNKNOWN outcomes
  conflicts bị bỏ qua im lặng
~~~

Nếu output nằm ở database **khác** với `JobRepository`, transaction checkpoint và business commit có thể không atomic. Restart/retry có thể replay item; test phải giữ identity ổn định và writer idempotent.

## 5. Xây baseline công bằng

Một baseline nên bắt đầu với **một worker** và DB không injection, sau đó mới tăng parallelism.

| Thành phần | Thông số cần khóa và ghi |
| --- | --- |
| Java/Spring | JDK, Spring Boot, Spring Batch, driver versions |
| Hardware | CPU cores, RAM, disk/network, VM/pod resource limits |
| PostgreSQL | Version, instance size, storage, replication/durability config |
| Connection pool | maxPoolSize, minIdle, connectionTimeout, maxLifetime |
| Job | jobName, Step names, chunk size, retry/skip policy |
| Scaling | Single step/local multi-thread/partitioned/remote workers |
| Workload | Dataset ID, row count, payload, hot keys, seed |
| DB schema | Indexes, FK, triggers, statistics, partition layout |
| Isolation | Transaction manager, isolation, read-only/not, autoCommit |
| Background load | OLTP/maintenance/backup traffic hoặc phiên bản mô phỏng |
| JVM | Heap, GC, warm-up, worker thread pool, CPU throttling |
| Metric collection | Sampling interval, dashboard, DB monitoring overhead |

**Không** chạy baseline lúc DB lạnh còn lần sau DB đã warm cache rồi kết luận 8 workers nhanh hơn. Tối thiểu cần warm-up, lặp lại nhiều lần hoặc randomize thứ tự các mức concurrency để phát hiện cache/order effects.

### Baseline cần đo ở đâu?

~~~text
T0: input snapshot sealed, trước job start
T1: JobExecution thực sự STARTED
T2: worker chunks bắt đầu commit
T3: step/job terminal theo Batch lifecycle
T4: reconcile output hoàn tất
T5: publish gate hoàn tất (nếu SLA bao gồm publish)
~~~

Các metric thường dùng:

- **Processing time:** `T3 - T1`, cần ghi rõ step/setup có bao gồm không.
- **End-to-end time:** `T4 - T0` hoặc `T5 - T0` tùy hợp đồng.
- **Steady-state throughput:** unique completed operations trong các cửa sổ ổn định.
- **Whole-run throughput:** unique completed operations / thời gian toàn run; dễ bị ảnh hưởng warm-up/tail.

Không chọn riêng một cửa sổ ngắn có tốc độ cao rồi gọi đó là throughput toàn job.

## 6. Ma trận thí nghiệm: thay một biến mỗi lượt

Bắt đầu bằng một ma trận vừa đủ nhỏ để giải thích kết quả:

| Scenario | DB delay model | Worker concurrency | Chunk size | Mục tiêu |
| --- | --- | ---: | ---: | --- |
| B0 | Không injection | 1 | 200 | Baseline tuần tự |
| B1 | Không injection | 4 | 200 | Scale hiệu quả ban đầu |
| B2 | Không injection | 8 | 200 | Tìm ngưỡng saturation |
| B3 | Không injection | 16 | 200 | Kiểm tra tăng worker phản tác dụng |
| L1 | `pg_sleep` 20ms/chunk | 4 | 200 | Transaction dài hơn |
| L2 | `pg_sleep` 20ms/chunk | 8 | 200 | DB pool/connection occupancy |
| L3 | `pg_sleep` 100ms/chunk | 8 | 200 | Slow DB transaction |
| L4 | `pg_sleep` 100ms/chunk | 16 | 200 | Pool contention |
| C1 | Lock contention workload | 8 | 200 | Hot-key conflict |
| P1 | maxPoolSize giảm | 8 | 200 | Connection wait |
| N1 | JDBC network latency | 8 | 200 | Round-trip overhead |
| R1 | L3 + worker crash | 8 | 200 | Retry/restart correctness |

**20ms/100ms là giá trị giả định để học**, không phải latency mặc định hay SLO phù hợp mọi DB. Với production throughput vài triệu records/giây, chậm 20ms/chunk có thể rất đáng kể; với HTTP-heavy processing, phần tăng này có thể không phải bottleneck.

### Khi nào mở rộng ma trận?

Sau khi xác định plateau của concurrency, thử thêm chunk sizes 50/200/500 và database pool sizes phù hợp. Không chạy toàn bộ tích Descartes một cách mù quáng; ưu tiên **lần thử có thể trả lời câu hỏi nguyên nhân**.

### Lặp lại và thống kê

1. Warm-up theo quy định nhất quán, không trộn kết quả warm-up với kết quả chính nếu đang đo steady state.
2. Chạy ít nhất vài repetitions cho mỗi scenario khi môi trường cho phép.
3. Ghi median, độ biến thiên, P95/P99 và confidence/uncertainty theo cách tính được công bố.
4. Randomize thứ tự scenario hoặc chạy lại B0 sau một số scenario để phát hiện drift.
5. Nếu DB bị hỏng trạng thái/index/cache sau một scenario, **reset bằng quy trình chuẩn** trước lần so sánh.

Một bảng chỉ có `threads=8, duration=5m` không đủ chứng minh "8 là tối ưu" nếu không biết variance và dữ liệu đã được xử lý đầy đủ chưa.

## 7. Tăng tải kiểu ramp, plateau, soak và recovery

### Ramp test

Tăng concurrency 1 → 2 → 4 → 8 → 16, giữ input/schema/DB resources cố định. Mỗi mức đủ dài để vượt warm-up và quan sát P95/P99, connection wait, rollback.

### Plateau test

Giữ concurrency ở mức vừa có throughput tốt nhất, tăng dần DB delay. Tìm mức mà completion throughput **không còn tăng** và tail latency tăng mạnh.

### Soak test

Giữ workload trong thời gian dài để phát hiện:

- Connection leak, thread leak, heap growth.
- Disk/WAL growth và checkpoint pressure.
- Queue/backlog tích lũy.
- Pool timeouts, transaction timeouts, GC pauses.
- Retry thưa nhưng liên tục làm giảm throughput.

### Recovery/fault test

Trong khi database đang chậm có kiểm soát, tạo một lỗi có chủ đích: dừng một worker, broker reply delay hoặc network disconnect. Xác minh:

- Job/StepExecution trạng thái đúng.
- Work được replay an toàn với cùng business operation ID.
- Không nhân đôi output/side effects.
- Throughput phục hồi, không mắc kẹt ở STARTED/UNKNOWN không có runbook.
- Không tăng attempts vô hạn khi DB vẫn lỗi.

~~~mermaid
flowchart TD
    D["Fixed dataset and environment"] --> B["Baseline (1 worker)"]
    B --> R["Ramp concurrency"]
    R --> P["Observe plateau and DB waits"]
    P --> L["Inject controlled DB slowdown"]
    L --> S["Soak at chosen point"]
    S --> F["Fault and restart"]
    F --> V["Reconcile input, output and metadata"]
    V --> A["Compare results and write report"]
~~~

## 8. Đơn vị throughput đúng: items/s khác attempts/s

Nếu một writer retry 5 lần vì deadlock, `ItemWriter.write(...)` có thể được gọi lại cho cùng chunk. Đếm callbacks sẽ làm throughput **trông như tăng** ngay khi hệ thống đang lỗi.

~~~text
attempted items = 10.000
unique business commits = 8.000
duplicate attempts = 1.500
failed items = 500

Attempt rate ≠ successful business throughput.
~~~

### Hai đại lượng nên xuất

~~~text
throughput_unique =
  unique valid business items committed in window / elapsed_seconds

throughput_attempts =
  item/chunk attempts processed in window / elapsed_seconds
~~~

Chỉ tiêu kinh doanh phải gắn với **unique operations** thực sự có outcome xác nhận. Nếu job idempotent dùng `ON CONFLICT DO NOTHING`, `writeCount` có thể tăng dù không có row mới; dùng business ledger hoặc query kiểm toán để đo hiệu lực.

### Các ngưỡng chấp nhận

Một scenario chỉ **PASS** nếu:

- Unique operations đầy đủ theo manifest.
- Không phát sinh duplicate side effect.
- Không có UNKNOWN chưa được reconcile trước publish.
- Throughput đạt mục tiêu.
- P95/P99 và rollback/retry nằm trong giới hạn.
- Đủ tài nguyên headroom cho workload khác.

Nếu job `COMPLETED` nhưng bỏ qua 5% records vì lỗi kết nối bị cấu hình skip nhầm, kết quả benchmark là **FAIL**, không phải "nhanh hơn".

## 9. Chunk size khi DB chậm

Trong chunk-oriented step, một transaction thường xử lý một số item rồi commit. Chunk size ảnh hưởng:

- Số transaction/commit.
- Số JDBC batch rows và round trips.
- Thời gian giữ connection/lock.
- Lượng work bị replay khi rollback.
- Kích thước memory của chunk.
- Độ phân phối công việc giữa workers.

### Ví dụ lý thuyết

Nếu có 1.000.000 items:

~~~text
chunk=50   -> khoảng 20.000 chunk transactions
chunk=200  -> khoảng  5.000 chunk transactions
chunk=500  -> khoảng  2.000 chunk transactions
~~~

Đây là số chunk lý thuyết **khi mọi item đi qua bình thường và phân bổ đơn giản**, không bao gồm retries/skip/step boundaries. Nếu mỗi transaction có chi phí cố định cao, chunk lớn hơn có thể tăng throughput. Nhưng nếu DB lock contention và rollback lớn, chunk quá lớn có thể làm tail latency và replay cost tăng.

### Không tối ưu chunk size một chiều

| Chunk quá nhỏ | Chunk quá lớn |
| --- | --- |
| Nhiều commits/metadata operations | Transaction/lock giữ lâu |
| Nhiều round trips | Rollback replay nhiều items |
| Executor/broker overhead tăng | Straggler/tail latency tăng |
| Throughput có thể bị transaction overhead giới hạn | Memory pressure, timeout/deadlock dễ nghiêm trọng hơn |

**Không có một chunk size tối ưu chung** cho multi-threaded step, remote chunking và remote partitioning. Tối ưu bằng benchmark khi biết nguyên nhân DB chậm.

## 10. Connection pool và định luật hàng đợi

Một worker thường cần một JDBC connection trong transaction ghi, nhưng **số connections tiêu thụ thực tế** phụ thuộc reader, writer, `JobRepository`, transaction managers và những lời gọi JDBC bên ngoài chunk.

### 10.1. Không coi số workers bằng số connections

~~~text
local partition executor:  16 threads
business DB pool:           8 connections
JobRepository DB pool:      4 connections (có thể cùng/khác DB)

Không có nghĩa 16 SQL transactions có thể thực thi đồng thời
trên 8 business connections.
~~~

Nếu cả 16 worker threads cùng gọi JDBC, một số threads **chờ pool**. Nếu pool timeout trước khi lấy được connection, worker có thể fail/retry. Càng tăng workers, tổng transaction time và retry cost có thể tăng dù database SQL execution vẫn nhanh.

### 10.2. Ước tính giới hạn lý tưởng

Giả sử:

- C = 8 connections có thể dùng **riêng** cho writes.
- W = 0,100 giây mỗi chunk giữ connection, gồm SQL và commit.
- N = 200 items/chunk.

Ở trạng thái ổn định và **bỏ qua hoàn toàn tranh chấp, I/O, CPU và các overhead khác**:

~~~text
maxChunksPerSecond ≈ C / W
                   ≈ 8 / 0,100 = 80 chunks/s

maxItemsPerSecond  ≈ N × C / W
                   ≈ 200 × 80 = 16.000 items/s
~~~

Đây chỉ là **ước lượng trần theo connection occupancy**, không phải cam kết throughput. Nếu DB chỉ ghi được 6.000 items/s do WAL/disk hoặc lock contention, tăng pool lên 32 không khiến đích đạt 64.000 items/s.

### 10.3. Little's Law

Trong hệ thống ổn định:

~~~text
L ≈ λ × W

L = số request/transaction trung bình trong hệ thống
λ = throughput trung bình (units/second)
W = thời gian một unit ở trong hệ thống (seconds)
~~~

Định luật hữu ích khi kiểm tra quan hệ giữa **concurrency, latency và throughput**, nhưng cần đo **cùng một boundary và cùng đơn vị work**. Không lấy tổng broker queue depth làm L trong khi W chỉ đo thời gian giữ JDBC connection; hai boundary khác nhau.

### 10.4. Khi DB chậm thêm, điều gì xảy ra?

~~~text
DB transaction occupancy tăng
  → pool connections bận lâu hơn
  → acquisition wait tăng
  → executor threads block nhiều hơn
  → manager/partition backlog tăng
  → retries/timeouts có thể khuếch đại tải
~~~

Nếu queue đầy gây rejection, đó là **một kết quả benchmark cần ghi nhận**, không phải nguyên nhân để tăng queue vô hạn. Queue lớn chỉ che độ trễ và làm giảm khả năng áp backpressure kịp thời.

## 11. Ví dụ Java: writer thực dùng JDBC batch

Ví dụ Spring Batch 5.x, Spring JDBC, Java 17 và PostgreSQL. Một row nguồn đã có `datasetId`, `operationId`, `tenantId`, `amountMinor` và `payloadHash` ổn định.

~~~java
public record PerfRow(
        String datasetId,
        String operationId,
        String tenantId,
        long amountMinor,
        String payloadHash) {}
~~~

### 11.1. Writer có bảo vệ identity

~~~java
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

import javax.sql.DataSource;

public final class PerfWriterFactory {

    public static JdbcBatchItemWriter<PerfRow> create(DataSource source) {
        return new JdbcBatchItemWriterBuilder<PerfRow>()
                .dataSource(source)
                .sql("""
                    INSERT INTO perf_import_result (
                        dataset_id, operation_id, tenant_id,
                        amount_minor, payload_hash
                    ) VALUES (
                        :datasetId, :operationId, :tenantId,
                        :amountMinor, :payloadHash
                    )
                    ON CONFLICT (dataset_id, operation_id)
                    DO UPDATE
                    SET payload_hash = perf_import_result.payload_hash
                    WHERE
                        perf_import_result.payload_hash =
                            EXCLUDED.payload_hash
                        AND perf_import_result.tenant_id =
                            EXCLUDED.tenant_id
                        AND perf_import_result.amount_minor =
                            EXCLUDED.amount_minor
                    """)
                .itemSqlParameterSourceProvider(row ->
                        new MapSqlParameterSource()
                                .addValue("datasetId", row.datasetId())
                                .addValue("operationId", row.operationId())
                                .addValue("tenantId", row.tenantId())
                                .addValue("amountMinor", row.amountMinor())
                                .addValue("payloadHash", row.payloadHash()))
                .assertUpdates(true)
                .build();
    }
}
~~~

Trong ví dụ PostgreSQL:

- Operation mới được **INSERT**.
- Replay cùng key và cùng nội dung cho **UPDATE no-op về giá trị** với affected row hợp lệ, nên có thể được coi là duplicate an toàn theo identity contract.
- Cùng key nhưng `payloadHash`, `tenantId` hoặc `amountMinor` khác làm `WHERE` của `DO UPDATE` không khớp, trả affected row = 0; cấu hình `assertUpdates(true)` có thể khiến writer báo lỗi thay vì bỏ qua conflict.

**Giới hạn:** Row count semantics phụ thuộc driver/batching và phải được integration test với PostgreSQL JDBC thực tế. Một update no-op vẫn tạo overhead/WAL/locks tùy điều kiện và DB, không phải writer tối ưu throughput cho production. Nó nhằm minh họa **tính đúng khi replay**; hệ thống lớn có thể chọn transactional unique insert + conflict-check path chuyên biệt để hạn chế unnecessary updates.

`PerfRow` và `PerfWriterFactory` phải ở các file Java riêng; snippet chỉ trình bày trọng tâm, còn cần imports/beans, reader, transaction manager, JobRepository và dependencies phù hợp.

### 11.2. Không để benchmark đo một thuật toán khác production

Nếu production dùng `JdbcBatchItemWriter`, đừng chạy benchmark với mỗi item gọi `jdbc.update(...)` riêng rồi kết luận DB quá chậm do production. Ngược lại, đừng dùng một COPY/LOAD fast-path trong benchmark nếu production writer vẫn cập nhật hot rows và trigger phức tạp.

Muốn thử một thay đổi kiến trúc (batched inserts, multi-row INSERT, bulk loader), làm **scenario riêng**, ghi rõ khác baseline.

## 12. Inject latency trong DB transaction bằng PostgreSQL

Để chủ động kéo dài transaction mà không chạm production, có thể đặt `SELECT pg_sleep(...)` trước writer trong **cùng transaction chunk**.

~~~java
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

public final class LatencyInjectingWriter<T>
        implements ItemWriter<T> {

    private final JdbcTemplate jdbc;
    private final ItemWriter<T> delegate;
    private final boolean enabled;

    public LatencyInjectingWriter(
            JdbcTemplate jdbc, ItemWriter<T> delegate, boolean enabled) {
        this.jdbc = jdbc;
        this.delegate = delegate;
        this.enabled = enabled;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        if (enabled) {
            // PostgreSQL: thêm khoảng 50 ms mỗi lần gọi writer.
            // Dùng chỉ trong benchmark DB riêng.
            jdbc.execute("SELECT pg_sleep(0.050)");
        }
        delegate.write(chunk);
    }
}
~~~

Điều kiện thí nghiệm:

1. `JdbcTemplate` và delegate writer dùng **cùng business datasource**.
2. Chunk transaction được quản lý bởi transaction manager gắn với datasource đó (ví dụ `DataSourceTransactionManager`/`JdbcTransactionManager`).
3. `pg_sleep` nằm trong transaction đang mở, nên kéo dài **connection occupancy**.
4. Inject chỉ bật trong **benchmark environment** bằng cấu hình explicit; tuyệt đối không vô tình chạy trong production.
5. Ghi mức delay 0/20/50/100 ms, vị trí injection và số lần writer được gọi thực sự (retry có thể khiến số lần tăng).

**Nó không mô phỏng đầy đủ mọi loại DB slow.** `pg_sleep` chủ yếu thêm delay trong DB session/transaction; nó không tự tạo disk latency, lock contention, network drops hoặc query plan xấu. Đây là một công cụ để **cô lập tác động transaction occupancy**.

### Nếu delay trước khi transaction bắt đầu?

~~~java
Thread.sleep(50); // Trong processor trước writer.
~~~

Điều này có thể **không giữ DB connection**, nên kết quả pool saturation rất khác. Đừng thay vị trí sleep mà vẫn gắn nhãn hai bài test đều là "DB latency 50 ms".

### Nếu có nhiều ItemWriter callbacks/chunk?

Spring Batch fault-tolerant step có thể retry hoặc phân rã xử lý theo semantics riêng. "50 ms cho mỗi lần `write(...)`" không nhất thiết bằng "50 ms cho mỗi committed chunk" khi xuất hiện rollback/retry. Do đó cần cả **attempt metrics** và **committed chunks metrics**, không chỉ số delay cấu hình.

## 13. Cấu hình chunk step và partitioning cho benchmark

Một worker step chunk-oriented của Spring Batch 5.x:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step perfWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTxManager,
        ItemReader<PerfRow> perfReader,
        ItemWriter<PerfRow> measuredWriter) {

    return new StepBuilder("perfWorkerStep", jobRepository)
            .<PerfRow, PerfRow>chunk(200, businessTxManager)
            .reader(perfReader)
            .writer(measuredWriter)
            .build();
}
~~~

Đây là skeleton: cần đặt trong class `@Configuration`, khai báo `@Bean`/imports và các beans thực. Nếu project có **nhiều transaction managers**, dùng `@Qualifier` cho `businessTxManager` và datasources; đừng để JobRepository metadata DB và business DB bị nhầm.

### Local partition manager minh họa

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.core.task.TaskExecutor;

@Bean
Step perfManagerStep(
        JobRepository jobRepository,
        Partitioner stableDatasetPartitioner,
        Step perfWorkerStep,
        TaskExecutor partitionExecutor) {

    return new StepBuilder("perfManagerStep", jobRepository)
            .partitioner(perfWorkerStep.getName(),
                    stableDatasetPartitioner)
            .step(perfWorkerStep)
            .gridSize(8)
            .taskExecutor(partitionExecutor)
            .build();
}
~~~

`gridSize(8)` không mặc nhiên có nghĩa `Partitioner` tạo đúng tám partitions hoặc có tám workers đang chạy. Tác dụng của `gridSize` phụ thuộc partitioner/handler; `partitionExecutor` và resources quyết định concurrency local. Để benchmark nhất quán, **giữ partition plan và mapping source ranges cố định** giữa các lần test.

### Vì sao ưu tiên partitioning trong ví dụ?

Một `FlatFileItemReader` hay paging/cursor reader stateful chia sẻ trong multi-threaded step có thể không thread-safe. Khi mỗi partition có `StepExecutionContext` và step-scoped reader riêng, mỗi worker có source range/reader state độc lập, dễ đo và restart hơn.

Nếu muốn thử multi-threaded step, cần scenario riêng và xác minh:

- Reader/processor/writer thread safety.
- Ordering/duplicate/skip semantics.
- Checkpoint và restart khi chunks commit không theo thứ tự đọc.
- Thread pool/queue và connection pool không bị dùng chung mutable state sai.

**Không biến concurrency tuning thành lỗi dữ liệu rồi chỉ báo throughput cao.**

## 14. Tạo lock contention có kiểm soát

`pg_sleep` làm transaction lâu hơn nhưng không cho biết một hệ thống có nhiều hot updates sẽ hoạt động ra sao. Để tái hiện **row lock** trong một DB test cách ly, tạo bảng:

~~~sql
CREATE TABLE perf_hot_account (
    account_id    VARCHAR(80) PRIMARY KEY,
    balance_minor BIGINT NOT NULL
);

INSERT INTO perf_hot_account (account_id, balance_minor)
VALUES ('acct-hot', 0);
~~~

Trên **session A**, tạo một transaction giữ lock:

~~~sql
BEGIN;

UPDATE perf_hot_account
SET balance_minor = balance_minor + 1
WHERE account_id = 'acct-hot';

-- Giữ row lock thêm 5 giây trong transaction test.
SELECT pg_sleep(5);

COMMIT;
~~~

Trong khi session A chưa commit, session B ghi cùng row:

~~~sql
BEGIN;

UPDATE perf_hot_account
SET balance_minor = balance_minor + 1
WHERE account_id = 'acct-hot';

COMMIT;
~~~

Session B có thể phải đợi row lock, thấy `lock wait`/`transaction duration` tăng. **Chỉ chạy trong database benchmark được cấp quyền**, không thử trên tài khoản giao dịch hoặc hệ thống production; chủ động set `lock_timeout`/`statement_timeout` ở môi trường test để không treo kết nối vô hạn.

### Giới hạn của thí nghiệm lock mẫu

- Một hot row bị khóa là **trường hợp cực đoan**, có thể khác tỷ lệ hot keys thật.
- Deadlock cần ít nhất một chu trình chờ tài nguyên; giữ một row lock không tự chứng minh deadlock.
- Nếu production có nhiều indexes và triggers, latency khác.
- Phải giữ tỷ lệ hot keys, transaction ordering và data distribution theo fixture.

### Quan sát phiên DB đang chờ

~~~sql
SELECT
    state,
    wait_event_type,
    wait_event,
    COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Và tìm blockers (quyền đọc có thể bị giới hạn):

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock';
~~~

Đừng bật log tất cả SQL statements hoặc query `pg_stat_activity` quá dày trong load test làm thêm overhead, rồi coi số liệu không bị can thiệp.

## 15. Mô phỏng connection-pool saturation

Giả sử PostgreSQL xử lý từng transaction không quá chậm, nhưng `HikariDataSource.maximumPoolSize=4` trong khi 16 worker threads đều cần ghi.

~~~text
Worker threads = 16
Pool size      = 4
DB max connections = còn headroom

Tại thời điểm peak:
  4 threads giữ JDBC connections
  tới 12 threads có thể đang chờ connection/đang xử lý phần khác
~~~

Mục tiêu:

- Đo `connection acquisition latency` và số pending waiters.
- Đo tỷ lệ `ConnectionTimeoutException`/pool timeout.
- So sánh pool size 4 và 8 **khi worker concurrency giữ nguyên**.
- Đối chiếu CPU/IO DB để biết pool hay DB mới là bottleneck.

### Vì sao không tăng pool lên bằng tổng số threads của mọi pods?

Nếu có 20 pods, mỗi pod pool 30 connections thì **cấu hình cho phép tới 600 connections** tới cùng database, chưa kể app/OLTP/JobRepository. Database không nhất thiết xử lý tốt nhiều active sessions như vậy. Pool phải được **budget toàn cụm**, tính replica count, metadata, background services và reserved OLTP capacity.

### Hikari metrics

Với Micrometer/Spring Boot Actuator đã cấu hình, Hikari có thể xuất metric về:

- Active/idle/pending/total connections.
- Acquisition time và usage duration.
- Timeouts khi lấy connection.

Tên Prometheus metric thực tế phụ thuộc registry, phiên bản và prefix. Ví dụ có thể thấy `hikaricp_connections_active` và `hikaricp_connections_pending`. **Kiểm tra endpoint `/actuator/prometheus` của đúng version trước khi dùng PromQL**, đừng xem tên trong tài liệu mẫu là hợp đồng bất biến.

### Dấu hiệu pool wait là bottleneck

| Tín hiệu | Giải thích ưu tiên |
| --- | --- |
| Pending waiters tăng, DB CPU thấp | Pool quá nhỏ hoặc giữ connection quá lâu |
| Active pool luôn max, DB IO/CPU cao | DB có thể đã bão hòa; tăng pool rủi ro |
| Connection timeout tăng | Độ chờ vượt timeout; job retry/rollback |
| Mở rộng pool không tăng throughput | Nút thắt phía DB/lock/WAL |
| Giảm chunk size giúp latency nhưng tăng commits | Trade-off cần đo, không sửa bằng cảm giác |

## 16. Network delay khác query delay

Để thử network RTT giữa worker pod và PostgreSQL có thể dùng **proxy mô phỏng** như Toxiproxy trong môi trường test, cho JDBC traffic đi qua proxy và bật latency/toxic controls.

~~~text
Worker -> test proxy (delay / jitter) -> PostgreSQL test

Không sửa query plan/index của DB.
Không chạy proxy delay trên kết nối production.
~~~

Giữ:

- Cùng dataset.
- Cùng pool size.
- Cùng query/driver.
- Cùng worker concurrency.
- Tăng **một chiều** latency có định nghĩa, hoặc cả hai chiều nếu muốn mô phỏng round trip; ghi rõ.

### Kết quả có thể khác pg_sleep

Giả sử mỗi chunk thực hiện 50 JDBC round trips. Thêm 10ms network RTT/round trip có thể kéo dài chunk **hàng trăm mili giây** dù `pg_sleep(0.050)` chỉ thêm 50ms một lần. Điều này cho thấy cần tối ưu **batching và số round trips**, không chỉ tăng pool.

Nếu dùng remote chunking, còn có **broker RTT** và serialize/deserialize cost. Không trộn network latency của JDBC với broker latency nếu muốn biết nút thắt chính.

### Giới hạn của proxy

Proxy latency không mô phỏng full DB I/O saturation, lock waits, replication lag hoặc query CPU. Proxy loss/timeout có thể kích hoạt driver retries, connection validation và failover; tách thành scenario fault, không diễn giải như một "query tăng 20ms" đơn giản.

## 17. Resource monitoring: đo từ hai phía

### 17.1. Ở phía Java/Spring Batch

- Processing throughput unique items/s theo cửa sổ 1/5/15 phút.
- Chunks completed/s, commits/s, rollback/s, item skip/filter.
- StepExecution durations và partition skew.
- Worker active/busy, executor queue depth, rejected tasks.
- JDBC pool active/pending/acquisition duration/timeouts.
- JVM CPU, GC pause, heap/allocations, threads blocked.
- Broker queue/lag, request-reply latency nếu remote.
- Tỷ lệ API/DB retry và pending outcomes.

### 17.2. Ở phía PostgreSQL

- Active sessions, `wait_event_type` và lock blockers.
- Query latency/P95 nếu có telemetry hỗ trợ.
- `pg_stat_statements` (nếu extension/quyền được bật) cho query fingerprints và total/mean execution time.
- Commit/rollback counts; WAL activity và storage I/O.
- Cache hit ratio chỉ là tham số phụ, không thay thế query/IO latency.
- Replication/commit durability nếu có synchronous replica.
- CPU, memory, disk throughput/IOPS và latency.

### 17.3. Đo đúng datasource

~~~text
Batch metadata repository DB
  ↔ JobExecution/StepExecution/checkpoint updates

Business target DB
  ↔ item writes, upsert, indexes, locks
~~~

Hai hệ thống có thể nằm chung PostgreSQL instance nhưng khác schema/database/connection pool. Khi cả hai cùng tăng độ trễ, cần phân tách metrics theo datasource/job để không tối ưu nhầm.

## 18. Micrometer: đo writer callback nhưng đừng gọi đó là commit

Ví dụ decorator:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;

public final class TimedWriter<T> implements ItemWriter<T> {

    private final ItemWriter<T> delegate;
    private final Timer writeCallTimer;

    public TimedWriter(
            ItemWriter<T> delegate,
            MeterRegistry registry,
            String stepName) {
        this.delegate = delegate;
        this.writeCallTimer = Timer.builder(
                "batch_perf_writer_call_duration")
                .description("Duration of ItemWriter.write callback")
                .tag("step", stepName)
                .publishPercentileHistogram()
                .register(registry);
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        writeCallTimer.recordCallable(() -> {
            delegate.write(chunk);
            return null;
        });
    }
}
~~~

`recordCallable` đo thời gian callback kết thúc hoặc ném lỗi. **Nó không chứng minh transaction đã commit** khi `write(...)` trả về, cũng không đo riêng SQL execution, connection acquisition hay commit. Phải đặt tên metric diễn đạt đúng boundary.

### Counter thành công không nên tăng trước commit

Nếu instrument:

~~~java
// Không nên: có thể rollback sau khi writer trả về.
successfulItemsCounter.increment(chunk.size());
~~~

thì số "success" sẽ bị phóng đại. Có thể:

1. Dùng transaction lifecycle callback cho **commit acknowledgement** trong cùng transaction manager (cần xử lý crash/metrics loss).
2. Tổng hợp từ business operation ledger/output records đã commit.
3. Dùng một read model/metrics exporter quét delta **unique successful operations**.
4. Dựa trên Spring Batch counters để phân tích thực thi, **không thay business reconciliation**.

Đừng đặt một metric label cho mỗi `operationId`, `JobExecutionId` hay partition ID không giới hạn vì sẽ tạo cardinality cực lớn.

### Histogram P95/P99

Micrometer `publishPercentileHistogram()` cho phép backend như Prometheus dùng histogram buckets khi registry hỗ trợ; nhớ có **đơn vị thời gian rõ** và đủ lượng sample.

PromQL ví dụ, **sau khi xác minh tên bucket đã được exporter xuất**:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, step) (
    rate(batch_perf_writer_call_duration_seconds_bucket[5m])
  )
)
~~~

P95 này là **writer callback latency**, không phải DB transaction P95 hay item end-to-end P95. Tránh trộn nhiều workload/chunk sizes trong cùng một series khi diễn giải latency; dùng bounded labels như `scenario` với tập giá trị cố định, hoặc tách môi trường benchmark.

## 19. Các phép đo thường sai khi DB chậm

| Phép đo sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `readCount / duration` = business throughput | Item có thể retry/rollback hoặc bị filter | Đếm unique committed output |
| `writer_calls × chunkSize` = rows inserted | Retry/duplicate no-op, chunk cuối ngắn | Read business ledger + actual chunk sizes |
| `write callback P95` = commit P95 | Commit xảy ra sau callback | Instrument transaction boundary/DB wait riêng |
| `threads=16` = 16 concurrent SQL sessions | Pool có thể chỉ 4 connections | Đo active/pending JDBC + DB sessions |
| `DB CPU thấp` = DB không bottleneck | Có thể đang lock wait/IO/network | Xem `wait_event`, SQL latency, pool |
| `queue=0` = tất cả complete | Inflight/UNKNOWN/outbox còn dở | Reconcile outcomes |
| `JobExecution COMPLETED` = external API confirmed | DB transaction không bao external effects | Provider idempotency/status + reconciliation |
| `avg duration` là đủ | Tail latency/stragglers che bởi average | P95/P99, min/max và distribution |
| `C1 nhanh hơn C2` từ một lần chạy | Noise/cache/background load | Repetitions + variability |
| Tăng pool làm nhanh hơn tại máy dev | Production DB/replica budget khác | Benchmark gần production |

## 20. Những thứ phải giữ ổn định khi benchmark phân tán

### Remote partitioning

- Giữ `partitionName → input range/file/manifest` bất biến.
- Ghi số partitions thực do `Partitioner` tạo, không chỉ `gridSize`.
- Đo số worker pods/consumers **active thực**, không chỉ cấu hình replicas.
- Cố định worker image/JVM/resource limits và network placement nếu so sánh concurrency.
- Dùng shared JobRepository đúng kiến trúc; không cho worker có H2 metadata riêng.
- Ghi số partitions failed/restarted và business output reconciliation.

### Remote chunking

- Manager đọc input; ghi chunk size và **số item thực** mỗi request.
- Đo broker publish/deliver/ACK/reply rates, queue lag và outstanding requests.
- Worker completion order có thể khác dispatch order.
- Mất reply **không chứng minh** DB transaction chưa commit.
- Retry/redelivery có thể làm attempts tăng; business operation key vẫn ổn định.

### Multi-threaded step

- Reader/processor/writer phải thread-safe hoặc có chiến lược per-thread/per-partition hợp lệ.
- Checkpoint/restart semantics cần được kiểm thử khi chunks commit lệch thứ tự.
- Không chia sẻ mutable `ExecutionContext`/cursor tùy tiện.
- Throughput tốt nhưng duplicate/missing output là **benchmark FAIL**.

### Local partitioning

- Executor pool và partition count có thể độc lập.
- `StepScope` giúp tách reader state theo `StepExecution`, không thay các transaction rules.
- Đo contention ở cùng JVM: GC, CPU, connection pool, `JobRepository`.

**So sánh giữa các kiến trúc chỉ hợp lệ** nếu kiểm soát input, database, schema, tài nguyên và cách tính success throughput. Một kết quả local 8 threads và remote 8 pods thường **không có cùng CPU/network budget**.

## 21. Mẫu metrics và dashboard cho benchmark

Một dashboard chỉ hiện "rows/s" rất khó hỗ trợ kết luận. Nên ghép **sáu trục**:

| Nhóm | Đồ thị nên có | Câu hỏi |
| --- | --- | --- |
| Input/throughput | Unique committed rows/s, cumulative verified rows | Năng suất thực có đang tăng? |
| Latency | Writer call P50/P95/P99, transaction/commit P95 nếu có | Work bị chậm ở đâu? |
| Concurrency | Active workers, busy threads, executor queue | Có bao nhiêu công việc thực sự song song? |
| JDBC/DB | Hikari active/pending/acquire wait, DB lock/IO/CPU | DB hoặc pool đã bão hòa? |
| Errors | Rollbacks/s, retries/s, deadlocks/s, SQL timeouts | Tải dư thừa do lỗi là bao nhiêu? |
| End-to-end | Pending/inflight/UNKNOWN, oldest age, ETA/SLA | Job có tiến tới kết thúc đúng không? |

### Các metric custom nên giữ đơn vị rõ

~~~text
batch_perf_committed_business_items_total   counter (unique operations)
batch_perf_attempted_items_total            counter (attempts)
batch_perf_writer_call_duration_seconds     timer/histogram
batch_perf_inflight_chunks                  gauge
batch_perf_pending_work_units               gauge
batch_perf_reconciled_business_items        gauge/read model
batch_perf_unknown_outcomes                 gauge
~~~

**Không tuyên bố `committed_business_items_total` là unique** nếu counter tăng trong writer trước transaction commit. Counter này nên lấy từ một event/ledger đáng tin cậy hoặc thiết kế phát sau commit kèm cách xử lý exporter mất event; dùng output count như nguồn kết quả cuối.

### PromQL tính write callback throughput

~~~promql
# Attempts/s từ callback timer, KHÔNG phải business success/s.
sum by (step) (
  rate(batch_perf_writer_call_duration_seconds_count[5m])
)
~~~

### PromQL tính success throughput theo counter đã được xác nhận

~~~promql
sum by (pipeline) (
  rate(batch_perf_committed_business_items_total[5m])
)
~~~

Counter thành công này là **metric custom chỉ có ý nghĩa nếu semantics thực sự đúng**: mỗi unique operation được xác nhận đúng một lần trong cửa sổ và có cách xử lý restart/exporter crash. Không nên chỉ tăng bằng `chunk.size()` trong callback.

### PromQL đo mức độ pool saturation

~~~promql
max by (pool) (hikaricp_connections_pending)
~~~

Tên metric Hikari chỉ là ví dụ có thể xuất hiện khi tích hợp Micrometer. Xác minh tên thực trên `/actuator/prometheus`; nếu DB có nhiều datasources, nhớ chọn **đúng pool** thay vì gộp metadata và business.

### Commit và lock latency

Histogram writer callback không phản ánh commit. Nếu muốn đo transaction end-to-end, đặt instrumentation theo **transaction boundary** hoặc datasource/proxy/DB telemetry. Một số `pg_stat_*` metrics chỉ là counters tích lũy hoặc snapshot, không hỗ trợ P99 trực tiếp. Không tự suy P99 commit từ `AVG(query_time)`.

## 22. SQL xác minh output sau mỗi scenario

Sau khi job terminal, cần có **kết quả SQL độc lập với Batch counters**.

~~~sql
SELECT
    dataset_id,
    COUNT(*) AS actual_unique_rows,
    COUNT(DISTINCT operation_id) AS distinct_operations
FROM perf_import_result
WHERE dataset_id = :datasetId
GROUP BY dataset_id;
~~~

Với primary key `(dataset_id,operation_id)`, `COUNT(DISTINCT)` bằng `COUNT(*)` trong một dataset; phép kiểm giúp báo cáo dễ đọc, nhưng **không phát hiện missing keys** nếu chỉ so tổng số. Cần đối chiếu **tập keys nguồn**.

### Khi source cũng có bảng manifest keys

Giả sử fixture được materialize trong:

~~~sql
CREATE TABLE perf_expected_input (
    dataset_id     VARCHAR(120) NOT NULL,
    operation_id   VARCHAR(160) NOT NULL,
    payload_hash   VARCHAR(128) NOT NULL,
    PRIMARY KEY (dataset_id, operation_id)
);
~~~

Kiểm tra thiếu keys:

~~~sql
SELECT e.operation_id
FROM perf_expected_input e
LEFT JOIN perf_import_result r
  ON r.dataset_id = e.dataset_id
 AND r.operation_id = e.operation_id
WHERE e.dataset_id = :datasetId
  AND r.operation_id IS NULL;
~~~

Kiểm tra **payload mismatch**:

~~~sql
SELECT e.operation_id
FROM perf_expected_input e
JOIN perf_import_result r
  ON r.dataset_id = e.dataset_id
 AND r.operation_id = e.operation_id
WHERE e.dataset_id = :datasetId
  AND e.payload_hash <> r.payload_hash;
~~~

Nếu mỗi item có amount/tenant/side effects khác, thêm field comparisons phù hợp. Nếu có skips được chấp nhận, expected set phải được phân loại `APPLIED` / `REJECTED` với lý do duyệt; **không** mặc định missing input là skip hợp lệ.

### Mức độ durable của việc đã commit

Những phép query này xác nhận dữ liệu hiện có tại thời điểm đọc. Nếu hệ thống còn external HTTP/Kafka effects, thêm **provider-side state/idempotency ledger và outbox reconciliation**. Một row ở DB chỉ phản ánh một phần của business outcome; performance test phải có invariant theo hợp đồng.

## 23. Làm sao tính end-to-end throughput công bằng?

Một lần benchmark dùng **datasetId độc lập** có thể đo:

~~~text
jobStartMonotonicTime
jobTerminalMonotonicTime
reconciliationCompleteMonotonicTime
uniqueCompletedOperations

processingThroughput =
    uniqueCompletedOperations
    / (jobTerminalTime - jobStartTime)

endToEndThroughput =
    uniqueCompletedOperations
    / (reconciliationCompleteTime - jobStartTime)
~~~

Đây là cách ghi **định nghĩa**, không phải quy tắc duy nhất. Nếu input được tạo và upload trong SLA, phải tính thêm thời gian chuẩn bị; nếu job chạy định kỳ trong batch window, báo cáo thời gian kể từ **scheduled fire time** bên cạnh `JobExecution.startTime`.

### Dùng đồng hồ nào?

Trong cùng một process, dùng monotonic clock (`System.nanoTime()`/meter timer) để đo duration; không lấy hiệu thời gian local wall clock có thể bị chỉnh. Với manager và remote workers ở nhiều hosts, đừng trừ trực tiếp hai `System.nanoTime()` khác process; dùng timestamps đồng bộ/trace spans và xử lý clock skew.

### Khi job có warm-up và tail

Ví dụ:

~~~text
00:00–02:00  starting readers/connections:  4.000 items/s
02:00–18:00  steady state:                 10.000 items/s
18:00–22:00  one straggler partition:       700 items/s
~~~

Steady-state 10.000 items/s là thông tin hữu ích cho capacity planning nhưng **không** là whole-run throughput. Tail lớn có thể khiến job trễ deadline. Báo cả hai chỉ số kèm phân phối thời gian theo partition và total elapsed.

## 24. Thiết kế benchmark tránh thay đổi trạng thái DB không kiểm soát

### Cache nóng và cache lạnh

Một lần chạy có thể hưởng lợi từ OS page cache, PostgreSQL buffer cache và prepared statement caches của lần trước. Có hai hợp đồng benchmark hợp lệ:

1. **Warm-cache throughput**: warm-up nhất quán, chạy trên dữ liệu/trạng thái đã chuẩn bị.
2. **Cold-start/end-to-end throughput**: setup/restore môi trường có kiểm soát, chấp nhận thời gian đầu và đo toàn bộ.

Không trộn cold baseline và warm 16-worker rồi kết luận scale tuyến tính. Thực tế production job ban đêm thường có một mức cache khác biệt, cần chọn tình huống tương ứng.

### Database cleanup

- Dùng `datasetId`/schema riêng cho mỗi run hoặc restore snapshot database.
- Khi cleanup/test lại, đảm bảo indexes, statistics, bloat và WAL condition không thay khác nhau bất ngờ.
- Không chạy `TRUNCATE` trên bảng dùng chung bởi production/OLTP.
- Nếu test đo INSERT-only vs upsert, reset/trạng thái row tồn tại phải như nhau cho từng scenario.
- Ghi rõ setup time có nằm trong kết quả hay không.

### Production-like traffic

Nếu workload OLTP tranh database với Batch, benchmark chỉ chạy Batch một mình có thể quá lạc quan. Có thể chạy **load generator cách ly** mô phỏng truy vấn đọc/ghi OLTP với tỷ lệ và SLA kiểm soát; giữ background load giống nhau giữa scenarios, đồng thời đo **OLTP P95/P99** để biết Batch có làm xấu trải nghiệm người dùng hay không.

### Bảo vệ môi trường và người dùng

Chỉ làm các thử nghiệm load, `pg_sleep`, lock contention, proxy faults, kill worker trên **môi trường được phép và cô lập**. Có hard stops về:

- CPU/DB saturation và storage space.
- Thời gian thử.
- Request quota / connection limit.
- Business-data safety.
- Cost budget.

Không chạy load test mạnh trên database production khi chưa có kế hoạch và quyền rõ ràng.

## 25. Integration test: DB chậm, rollback và restart

### 25.1. Kiến trúc kiểm thử

~~~text
Test driver / CI perf runner
       |
       +-- deterministic dataset seed
       +-- PostgreSQL test instance
       +-- Spring Batch manager
       +-- 1/4/8/16 workers, tùy scenario
       +-- metrics collector
       +-- fault injector (DB delay / proxy / worker kill)
       +-- reconciliation reporter
~~~

**Testcontainers PostgreSQL** có thể dùng cho integration correctness và latency injection nhỏ; benchmark throughput dài hạn/production-like cần database có kích thước, IO và resource limits tương đương production. Container local nhỏ trên laptop **không chứng minh** khả năng của cloud database production.

### 25.2. Các bước một testcase

1. Restore schema và materialize fixture có `datasetId`, expected IDs/hash.
2. Seal input manifest và xác minh checksums.
3. Cấu hình đúng worker/pool/chunk/slowdown scenario.
4. Warm-up theo quy định của test plan.
5. Start JobInstance với identifying parameters ổn định.
6. Thu thập JVM, Hikari, database, broker và Batch metrics theo cùng time window.
7. Chỉ inject fault tại mốc có thể tái lập (ví dụ sau 5 chunk commits hoặc tại checkpoint ID đã ghi).
8. Chờ job terminal hoặc hard-stop deadline.
9. Chạy source/output reconciliation; phân loại success/failed/skipped/UNKNOWN.
10. Ghi performance metrics, resource saturation và errors.
11. Reset môi trường theo protocol; chạy repetition tiếp theo.

Không dùng `Thread.sleep(60000)` rồi đo writer count tại đúng giây 60 nếu job chưa hoàn tất và còn một lượng lớn work chưa confirmed.

### 25.3. Example test assertion về dữ liệu

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class PerfOutputReconciliationTest {

    private JdbcTemplate jdbc;

    @Test
    void allExpectedUniqueOperationsArePresent() {
        String datasetId = "perf-orders-v1";

        Long missing = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM perf_expected_input e
                LEFT JOIN perf_import_result r
                  ON r.dataset_id = e.dataset_id
                 AND r.operation_id = e.operation_id
                WHERE e.dataset_id = ?
                  AND r.operation_id IS NULL
                """,
                Long.class, datasetId);

        Long mismatched = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM perf_expected_input e
                JOIN perf_import_result r
                  ON r.dataset_id = e.dataset_id
                 AND r.operation_id = e.operation_id
                WHERE e.dataset_id = ?
                  AND e.payload_hash <> r.payload_hash
                """,
                Long.class, datasetId);

        assertEquals(0L, missing);
        assertEquals(0L, mismatched);
    }
}
~~~

**Đây là snippet học tập**, cần Spring test configuration/injected `JdbcTemplate` và data fixture. Nếu expected source có 0 rows, cả hai assertions đều pass — cần thêm assertion expected count **đúng theo manifest**. Kiểm tra thêm **unexpected extra output IDs**, duplicates ngoài unique constraint và downstream side effects nếu nghiệp vụ có.

### 25.4. Fault injection matrix

| Kịch bản | Điều phải kiểm chứng |
| --- | --- |
| DB query chậm 20/50/100ms | Throughput/latency biến đổi, không mất dữ liệu |
| Hikari pool max nhỏ hơn workers | Wait tăng có lý do; timeout được ghi nhận |
| Hot row bị khóa tạm thời | Lock wait tăng; không lén skip transaction |
| Deadlock khi workers update nhiều keys | Rollback/retry bounded, dữ liệu vẫn đúng |
| JDBC network delay | Round-trip và pool use tăng, giải thích bằng telemetry |
| Connection drop trước SQL | Retry/rollback đúng state |
| Connection drop sau DB commit nhưng trước response | Reconcile outcome, không phát operation ID mới |
| Worker kill trước chunk commit | Chunk rollback/replay an toàn |
| Worker kill sau business commit, trước ACK | Idempotent retry, không double effect |
| Manager crash khi remote workers còn chạy | Xác minh workers/StepExecutions, không launch trùng mù |
| Broker redelivery chunk | Không tạo duplicate output |
| StepExecution bị restart | Identifying JobParameters/input snapshot giữ nguyên |
| Nhiều partitions cùng source range do bug | Reconciliation phát hiện overlap |
| DB metadata repository chậm | Phân biệt metadata wait với business SQL |
| Pool leak qua soak test | Active connections trở về baseline sau run |
| Retry storm khi API/DB outage | Backpressure/bounded retry, không bùng số attempts |
| SkipLimit sai cho DB exception | Test fail nếu bỏ dữ liệu hạ tầng |
| Publish gate khi còn UNKNOWN | Không publish cho đến khi reconcile |
| DB đột ngột phục hồi | Throughput hồi phục, outstanding work được xử lý |

## 26. So sánh concurrency công bằng khi DB chậm

Một bảng kết quả minh họa **giả định**, không phải số đo Spring Batch thực tế:

| Workers | Injected delay | Pool | Unique items/s | Writer P95 | Pool wait P95 | Rollback rate | Nhận xét |
| ---: | --- | ---: | ---: | --- | --- | --- | --- |
| 1 | 0ms | 8 | 4.000 | 32ms | 0ms | 0% | Baseline |
| 4 | 0ms | 8 | 11.000 | 48ms | 0ms | 0% | Scale tốt |
| 8 | 0ms | 8 | 14.000 | 72ms | 3ms | 0,1% | Gần plateau |
| 16 | 0ms | 8 | 13.200 | 130ms | 45ms | 0,5% | Over-concurrency |
| 4 | 100ms/chunk | 8 | 6.000 | 180ms | 0ms | 0% | Delay giữ connection |
| 8 | 100ms/chunk | 8 | 8.000 | 210ms | 12ms | 0,2% | Còn headroom |
| 16 | 100ms/chunk | 8 | 7.100 | 380ms | 120ms | 1,8% | Pool wait/rollback |

Mọi giá trị trong bảng là **synthetic example để diễn giải**, không chứng minh cấu hình 8 workers tốt nhất cho mọi ứng dụng. `Writer P95` ở đây không mặc định bao commit, và pool wait P95 cần instrumentation chuyên biệt. Việc delay 100ms/chunk cùng biến động throughput tùy hạ tầng và writer SQL.

### Rút kết luận từ bảng đúng cách

1. Throughput tăng 1 → 8 workers rồi plateau/giảm khi 16.
2. Pool wait P95 và rollback tăng khi 16, là bằng chứng cần điều tra pool/DB.
3. Không kết luận chỉ từ worker CPU; phải nhìn DB saturation và query/lock waits.
4. Với delay 100ms/chunk, 8 workers giả định nhanh hơn 4, nhưng 16 có throughput thấp hơn và P95 lớn hơn.
5. Nếu job cần OLTP headroom, có thể chọn 4–8 workers dù 8 có throughput peak cao nhất.
6. Mỗi dòng phải đi kèm số repetitions, variance, input reconciliation, resource limits và timestamps.

### Visualization nên có

~~~text
Plot A: workers (x) vs unique items/s (y)
Plot B: workers (x) vs writer/transaction P95/P99 (y)
Plot C: workers (x) vs pool wait + DB lock wait (y)
Plot D: time (x) vs ready/inflight/UNKNOWN backlog (y)
Plot E: time (x) vs DB CPU/IO/WAL/connection usage (y)
~~~

**Không chỉ vẽ Plot A:** peak throughput cao hơn 5% nhưng pool timeouts tăng 10 lần có thể là phương án vận hành tệ hơn.

## 27. Dừng benchmark khi nào?

Tăng worker/concurrency không nên tiếp tục vô hạn. Một tiêu chí dừng hợp lý nếu một trong các điều kiện:

- P95/P99 latency vượt ngân sách latency.
- Throughput không tăng đáng kể qua nhiều mức concurrency, còn resource usage tăng.
- DB pool acquisition timeout hoặc rollback/deadlock vượt ngưỡng.
- DB ảnh hưởng quá mức tới OLTP SLO.
- Queue/backlog không giảm hoặc ngày càng tăng trong cửa sổ active.
- Memory/disk/connection limit gần chạm guardrail.
- Input/output reconciliation sai hoặc có external UNKNOWN outcome.

Định nghĩa guardrails **trước khi chạy**, tránh sau khi thấy kết quả mới chọn threshold làm đẹp báo cáo. Nếu benchmark được thực hiện trên cluster dùng chung, dừng tải khi có dấu hiệu ảnh hưởng người dùng, không đợi đủ số lần thử.

## 28. Runbook khi throughput giảm do database

1. **Xác nhận nguồn đo:** Số liệu có fresh không, throughput là unique commits hay writer attempts?
2. **Chốt scenario:** datasetId, jobInstance/JobExecution, chunk size, concurrency, datasource, injected delay/lock/network.
3. **Xác minh trạng thái Batch:** StepExecutions, commit/rollback counts, retries, outstanding chunks/partitions.
4. **Xem pool:** Active/idle/pending/acquisition timeouts, connection leak hoặc maxPoolSize.
5. **Xem DB:** CPU/IO, `pg_stat_activity` wait events, blockers, query plan/statements và WAL.
6. **Phân biệt nguyên nhân:** Pool contention, lock hot key, slow query, commit latency, network RTT hay metadata DB.
7. **Kiểm tra resource contention:** Worker JVM CPU/GC, broker lag và OLTP background load.
8. **Đánh giá batching:** Chunk size, JDBC batch vs per-item SQL, indexes và statement count.
9. **Không sửa bừa:** Không tăng mọi pools/workers đồng thời, không tăng `skipLimit` cho DB lỗi.
10. **Thay một biến:** Giảm concurrency hoặc chunk size có kiểm soát; tối ưu query/index khi có bằng chứng.
11. **Quan sát phục hồi:** Throughput, P95/P99, rollback rate, pool waits và backlog slope.
12. **Đối soát output:** Expected unique IDs, payload equivalence, quarantine, UNKNOWN outcomes.
13. **Khôi phục có kiểm soát:** Nếu execution failed, restart **cùng JobInstance** và source snapshot theo policy, không tạo identifying timestamp mới.
14. **Ghi nhận:** Kết quả trước/sau, confidence, chi phí/tài nguyên và cấu hình được chọn.

### Những điều không nên làm

- Chạy `pg_sleep` hoặc intentionally block transactions trên production DB.
- Chỉ so sánh duration một lần, không xét cache/variance.
- Đếm `writeCount` như số row mới dù idempotent writer có duplicate no-op.
- Tạo `run.id` identifying mới cho cùng input để retry test và vô tình nhân bản business output.
- Tăng từ 4 lên 100 JDBC connections vì có 100 threads mà không biết DB budget.
- Giảm/đổi partition mapping trong **cùng JobInstance** đang restart.
- Bật skip mọi `DataAccessException` để báo "job COMPLETED".
- Khi DB timeout, gọi external payment lại bằng idempotency key mới.
- Chỉ đọc CPU worker và bỏ qua `pg_stat_activity`/pool wait/OLTP SLO.
- Đưa ra kết luận throughput nhưng không đối soát dữ liệu.

## 29. Mẫu performance test report

Một báo cáo đầy đủ nên có cấu trúc:

~~~yaml
experiment:
  title: "PostgreSQL transaction delay vs Spring Batch workers"
  datasetId: perf-orders-v1
  expectedUniqueItems: 12000000
  inputManifest: orders-perf-2026-11-25-v1
  model: remote-partitioning
  workerImage: example-registry/perf-worker:1.0.0
  versions:
    java: "17"
    springBatch: "5.x"
    postgres: "<version-thuc-te>"
  scenario:
    name: L3
    chunkSize: 200
    workerConcurrency: 8
    businessDbPoolSizePerPod: 8
    delayModel: "pg_sleep(0.100) once per ItemWriter.write callback"
    repetitions: 5
  measurements:
    uniqueItemsPerSecondMedian: "<measured-value>"
    throughputVariation: "<measured-variation>"
    writerCallP95Ms: "<measured-value>"
    commitP95Ms: "<measured-if-instrumented>"
    poolAcquireP95Ms: "<measured-value>"
    dbLockWaitMs: "<measured-value>"
    rollbackCount: "<measured-value>"
    endToEndDurationSec: "<measured-value>"
  integrity:
    missingOperationIds: 0
    payloadMismatches: 0
    unexpectedExtraIds: 0
    unknownOutcomes: 0
  conclusion:
    status: "<PASS-or-FAIL>"
    bottleneck: "<evidence-based-finding>"
    nextExperiment: "<one-change>"
~~~

Các chuỗi trong dấu `<...>` là **placeholder**, không phải benchmark kết quả đã được đo. Trong báo cáo thật, cần điền **số thực cùng cách đo, timestamps, metric definitions và link dashboard**. Tỷ lệ rollback chỉ có nghĩa khi biết số transaction/attempts tương ứng.

## 30. Bài tập tình huống: thêm workers nhưng throughput giảm

Một team chạy Spring Batch **remote partitioning** xử lý 10 triệu rows, có 64 logical partitions và shared PostgreSQL writer database. Ban đầu:

~~~text
Worker pods                  = 4
Chunk size                   = 200
Hikari maxPoolSize / pod     = 8
Unique committed throughput  = 9.000 items/s
Writer callback P95          = 100 ms
DB lock wait                 = thấp
Rollback rate                = 0,1%
~~~

Để kịp deadline, team tăng lên **16 pods**, không đổi input/DB instance và schema:

~~~text
Unique committed throughput  = 7.200 items/s
Writer callback P95          = 480 ms
Hikari pending connections   = tăng
PostgreSQL active sessions   = tăng
Lock wait/deadlocks          = tăng
Rollback rate                = 4,5%
Queue backlog                = tăng
~~~

Phân tích cho thấy **65% records cập nhật 120 hot account keys**, và application metadata repository chung DB instance với business writer. Một đồng nghiệp đề nghị tăng `gridSize` lên 128, pool size mỗi pod lên 64 và tạm thời `skip(DataAccessException.class)` để job hoàn tất.

**Câu hỏi:**

1. Throughput giảm sau khi tăng pods có chứng minh DB đang bottleneck không? Cần đo thêm gì?
2. Vì sao 16 pods × 8 pooled connections khác với 16 workers trong một JVM?
3. `gridSize=128` có nhất thiết tạo 128 partitions hoặc tăng unique business throughput không?
4. Cần xác minh hot-key lock contention bằng metrics/SQL nào?
5. Trong trường hợp nào nên giảm worker count, chunk size hoặc đổi partitioning strategy?
6. `pg_sleep(0.100)` trong writer và JDBC network proxy +100ms mô phỏng những hiện tượng nào khác nhau?
7. Vì sao `writeCount` và số lần `ItemWriter.write` bị retry có thể làm throughput bị tính sai?
8. Nếu một worker chết sau business commit nhưng trước checkpoint metadata, phải xử lý replay như thế nào?
9. Điều gì xảy ra với business correctness nếu dùng skip mọi database exception?
10. Thiết kế ma trận benchmark và tiêu chí PASS/FAIL để chọn cấu hình mới.

**Định hướng trả lời:** Tăng pods có thể làm tổng số JDBC sessions/transactions và cạnh tranh hot rows tăng, giảm throughput do lock waits/rollback. Cần đo active/pending pool, query plans, `pg_stat_activity`, lock blockers, transaction/commit latency, WAL/IO, OLTP impact và restart correctness. `gridSize` không thay đổi khả năng ghi vật lý của DB. Chỉ đổi **một biến** mỗi scenario; thử giảm concurrency, chỉnh partitioning theo key để giảm overlap, tối ưu SQL/index và cân bằng chunk size. `pg_sleep` giữ DB session/connection trong transaction, còn proxy thêm network latency/round trips; không thể thay thế nhau. Tính throughput bằng **unique committed operation IDs**, không theo attempted writes. Khi rollback/restart, dùng stable business operation keys và writer idempotent; không skip lỗi hạ tầng hoặc tự tạo JobInstance mới để lách failure.

## 31. Checklist trước khi đưa kết luận production

| Hạng mục | Tiêu chí |
| --- | --- |
| Mục tiêu | SLO throughput/latency/deadline và resource guardrail ghi rõ |
| Dataset | Bất biến, có expected IDs/hash và phân phối hot keys |
| Môi trường | Versions, CPU/RAM/IO/network, DB và OLTP load được ghi |
| Baseline | One-worker benchmark và warm-up/cold-start protocol |
| Ma trận | Thay một biến, có repetitions và kiểm soát variance |
| Delay model | Phân biệt SQL/commit/lock/network/pool |
| Concurrency | Workers, partitions, threads, pool và broker consumers ghi rõ |
| Chunk | Kích thước, count, commits, rollback/replay cost |
| Throughput | Unique committed business items/s |
| Latency | Boundary, P95/P99, transaction vs callback được nêu rõ |
| DB | `pg_stat_activity`, lock waits, query stats, WAL/IO |
| Pool | Active/pending/acquisition wait/timeout |
| Batch | Job/StepExecution, restarts, skip/retry/rollback |
| Remote | Broker inflight/reply, idempotency, liveness |
| SLA | Whole-run duration, tail/straggler, publish gate |
| Integrity | Source-output set reconciliation, UNKNOWN=0 theo policy |
| Safety | Load test ở môi trường được phép, có hard stop |
| Report | Metrics, uncertainty, findings và next experiment |

## Tài liệu tham khảo

- [Spring Batch Reference — Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk, writer và transaction boundaries.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps, partitioning và concurrency.
- [Spring Batch Reference — Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote chunking/partitioning.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): metrics/observations.
- [Spring Batch Reference — Restartability](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoints và replay.
- [Spring Batch Reference — Flat File and JDBC Readers/Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): JDBC readers/writers.
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Actuator, Micrometer và tags.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): timer semantics và histograms.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): phân vị và histogram aggregation.
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): statistics và `pg_stat_activity`.
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): query-level statistics khi extension được bật.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, blockers và deadlocks.
- [PostgreSQL — pg_sleep](https://www.postgresql.org/docs/current/functions-datetime.html): mô phỏng chậm trong test session.
- [HikariCP — Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): pool sizing và contention.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): test database có thể tái lập.
- [Testcontainers — Toxiproxy](https://java.testcontainers.org/modules/toxiproxy/): kiểm thử network latency/fault.

> **Ghi nhớ:** Khi DB chậm, **tăng worker không mặc nhiên tăng throughput**. Cần phân biệt chậm SQL, commit, lock, network và connection pool; benchmark bằng **input bất biến, một biến mỗi lần, đo P95/P99 và unique committed operations**. Kết quả chỉ đáng tin khi retries/restarts không làm mất hoặc nhân đôi dữ liệu và khi DB/OLTP còn headroom vận hành. Hãy chọn concurrency theo **đường cong throughput + latency + resource saturation + correctness**, không theo số threads lớn nhất.
