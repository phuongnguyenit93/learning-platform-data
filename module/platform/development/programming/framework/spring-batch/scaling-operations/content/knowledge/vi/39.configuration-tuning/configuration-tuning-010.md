# Tránh tối ưu dựa trên một benchmark trong Spring Batch

Một nhóm vận hành Spring Batch tăng số worker threads từ 8 lên 32, chạy thử một lần với 1 triệu bản ghi giả lập và thấy thời gian giảm từ 13 xuống 7 phút. Nhóm quyết định đưa cấu hình 32 threads vào production. Hôm sau, workload thật có nhiều bản ghi trùng khóa, SQL update tranh lock và API downstream trả HTTP 429. Job hoàn thành chậm hơn, rollback tăng mạnh, Hikari pool luôn hết connection. Benchmark ban đầu **không sai phép đo**, nhưng **không đại diện cho quyết định cần đưa ra**.

**“Tránh tối ưu dựa trên một benchmark”** không có nghĩa là ngừng benchmark, cũng không phải kết luận rằng kết quả nào cũng chủ quan. Nó có nghĩa **không dùng một phép đo đơn lẻ, một tập dữ liệu thuận lợi, một mức tải hoặc một môi trường không kiểm soát để kết luận một cấu hình nhanh và an toàn hơn**. Tối ưu Spring Batch phải dựa trên **một chuỗi thí nghiệm có thể lặp lại**, gồm performance, correctness, restartability và giới hạn tài nguyên ở các điều kiện mà production thực sự gặp.

Bài học thuộc chương **Tối ưu cấu hình** của module **SPRING_BATCH_SCALING_OPERATIONS**, chuyên mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các kiến trúc phân tán. Trong toàn bài, mục tiêu luôn là **committed throughput, SLA, thread safety, retry/restart và tài nguyên thực tế**, không chỉ một con số elapsed time đẹp.

Ví dụ sử dụng **Spring Batch 5.2.x**, **Java 17+**, **Spring Framework 6.x**, **Micrometer** và **PostgreSQL** trong những tình huống phù hợp. Giá trị chunk size, threads, pool, thời gian hoặc số liệu trong bảng đều là **dữ liệu minh họa**, không phải kết quả đo thật hay mặc định Spring Batch. Khi làm trên hệ thống riêng, phải thu thập benchmark thực và áp dụng cùng quy trình kiểm chứng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nêu vì sao **một lần chạy nhanh** chưa đủ để chọn `chunkSize`, `gridSize`, `TaskExecutor`, pool JDBC hoặc số worker pods.
2. Thiết kế **baseline → giả thuyết → thí nghiệm → phân tích → quyết định → rollback** có bằng chứng.
3. Lập ma trận workload theo kích thước, skew, kích cỡ item, tỉ lệ lỗi, CPU/I/O, data hot spots và downstream quotas.
4. Phân biệt **warmup**, cache cold/warm, JIT/GC, DB buffer cache, index stats và contention giữa các lần chạy.
5. Thu thập **committed unique items/s**, wall-clock end-to-end, p95/p99 chunk duration, retry, rollback, queue, CPU, memory, JDBC và metadata latency.
6. Hiểu variance, median, confidence interval, paired experiments, effect size và vì sao những run không độc lập không thể coi là nhiều mẫu độc lập.
7. Sử dụng speedup, parallel efficiency, Amdahl và Little's law như **mô hình kiểm tra giả thuyết**, không như phép chứng minh tăng threads sẽ tăng throughput.
8. Giữ tập dữ liệu, snapshot, partition plan, job parameters và output comparison **tái lập được** giữa baseline và candidate.
9. Thiết kế thí nghiệm thay đổi **một biến có chủ đích**, đồng thời kiểm soát các biến tương tác mạnh.
10. So sánh local multi-threaded step, local/remote partitioning và remote chunking mà không bỏ qua transaction/restart semantics.
11. Loại bỏ những benchmark “nhanh” nhờ skip lỗi, không checkpoint, không ghi output hoặc mất dữ liệu.
12. Xây dựng quy trình tuning, canary, rollback và CI performance regression với tiêu chí rõ ràng.

## 2. Benchmark là quan sát; lựa chọn cấu hình là một quyết định

Một benchmark chỉ cho biết: **với dữ liệu, môi trường, thời điểm, cấu hình và cách đo cụ thể đó, hệ thống có kết quả đo được như vậy**. Nó **không tự chứng minh** kết quả sẽ lặp lại trong giờ cao điểm hoặc sau khi một worker crash.

Ví dụ:

| Run | Dữ liệu | Workers | Kết quả | Có thể kết luận gì? |
| --- | --- | ---: | --- | --- |
| A | 1M events không trùng key, DB cache warm | 8 | 13 phút | Baseline đúng điều kiện A |
| B | Cùng dữ liệu, cùng môi trường, chạy một lần | 32 | 7 phút | Candidate có lần chạy nhanh hơn |
| C | Production: updates vào hot account rows | 32 | 24 phút | Workload khác có bottleneck khác |
| D | Production: API quota 60 req/s | 32 | 429 + retry tăng | Worker count có thể vượt quota |
| E | Worker crash giữa chunk | 32 | 1.000 items bị replay | Phải kiểm chứng idempotency/restart |

Các kết quả trên là **minh họa**, không phải measured study. Một lần B tốt không phủ định được C/D/E; nó chỉ chứng minh B phù hợp với một điều kiện.

### 2.1. Bảy câu phải trả lời trước khi nói “nhanh hơn”

1. **Workload nào?** Số records, payload sizes, skew, hot keys, joins, data distribution, error rate?
2. **Đo cái gì?** Thời gian chạy, items đã read, đã write, đã commit, hay end-to-end publish?
3. **Môi trường nào?** CPU, RAM, JVM, DB version, network, disk, quotas, shared neighbors?
4. **Thí nghiệm lặp lại bao nhiêu lần?** Có warmup, randomize order, kiểm soát drift không?
5. **Candidate thay đổi những gì?** Một parameter hay cả chunk, threads, pool, index và hardware?
6. **Tính đúng đắn thế nào?** Checkpoint, output keyset/hash, retry, external effects có được đối soát?
7. **Quyết định dùng vào production được không?** SLA p95/p99, headroom, operational risk, rollback plan?

Nếu không trả lời được các câu này, “tối ưu 46%” có thể chỉ là **con số của một thí nghiệm chưa được kiểm soát**.

## 3. Khác nhau giữa performance testing và đo để tuning

Các mục đích đo có thể bổ sung nhau nhưng không đồng nhất.

| Loại đo | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Microbenchmark** | Một đoạn code/algorithm tốn bao nhiêu? | Parse 1 JSON record, hash keys |
| **Component benchmark** | Reader, processor hoặc writer riêng nhanh đến đâu? | JDBC batch insert 10k rows |
| **Integrated job benchmark** | Spring Batch end-to-end xử lý/chốt output mất bao lâu? | JobInstance với 32 partitions |
| **Load test** | Hệ thống xử lý tải mục tiêu ổn định không? | 600 committed items/s 1 giờ |
| **Stress test** | Bottleneck và failure mode khi tăng tải là gì? | 64 workers, DB lock contention |
| **Soak test** | Sau nhiều giờ có leak, GC degradation, connection leak? | Batch 12 giờ, queue backlog |
| **Fault/restart test** | Crash giữa commit/ACK có mất/trùng work không? | Kill worker sau commit |
| **Capacity test** | Giới hạn worker/DB/API/CPU đạt SLA là bao nhiêu? | 6 pods × 8 workers |

**Không lấy microbenchmark JSON parser thay cho benchmark cả Spring Batch job.** Lợi ích 30% ở processor có thể chỉ mang lại 1–2% end-to-end nếu phần lớn thời gian ở database hoặc HTTP.

### 3.1. Phân biệt “latency” và “throughput”

- **Job elapsed time**: thời gian từ start tới terminal state của JobExecution.
- **End-to-end latency**: có thể tính thêm queue wait, snapshot preparation, validation và publication.
- **Throughput**: output công việc mỗi đơn vị thời gian.
- **Concurrency**: số chunks/partitions/requests đang chạy đồng thời, không phải throughput.
- **Tail latency**: p95/p99 của chunk/request; có thể quyết định partition chậm nhất và SLA.
- **Resource utilization**: CPU usage, Hikari active/pending, memory, IOPS... không phải “số item đã hoàn thành”.

Một job có thể tăng **read throughput** nhưng giảm **committed business throughput** vì retries và rollbacks. Tuning chỉ dựa trên số `readCount` hoặc requests sent sẽ chọn nhầm cấu hình.

## 4. Xác định SLO và bất biến trước khi chạy benchmark

Một thí nghiệm có thể chọn cấu hình nhanh nhất chỉ khi **chất lượng đầu ra đạt** và **không vi phạm resource budgets**.

Ví dụ business contract:

~~~text
Workload:           12 triệu payment events/ngày
Allowed job window: 90 phút từ khi snapshot READY
Expected output:    đúng unique event IDs, source version, amount
SLA:                >=99% daily executions xong trong 90 phút
External API:       tối đa 60 requests/s và 20 in-flight cho batch
DB pool budget:     tối đa 80 configured connections cho batch cluster
Business correctness:
  missing keys      = 0
  extra keys        = 0
  mismatched hash   = 0
  duplicate effects = 0
  restart/crash     = replay-safe và recoverable
~~~

Số liệu chỉ minh họa. **90 phút** phải được định nghĩa: chỉ xử lý chunks, hay bao gồm chờ scheduler, retries, validation/publish? Nếu không định nghĩa, hai benchmark có thể báo “đạt SLA” theo hai đồng hồ khác nhau.

### 4.1. Acceptance gate có điều kiện cứng

Một candidate **không đạt** khi:

- Job COMPLETED nhưng thiếu output rows.
- `skipCount` tăng do nuốt lỗi dữ liệu bắt buộc.
- Worker restart phát lại external payment charge.
- Snapshot/partition manifest bị thay đổi giữa hai runs.
- DB connections vượt ngân sách cluster, HTTP rate vượt quota.
- p99 latency/rollback làm job dễ trễ SLA khi gặp tail.
- Sau 4 giờ job treo ở `STARTED` mà không có bounded recovery.

**Tính đúng đắn không phải một “điểm” đem trao đổi lấy tốc độ** trong hệ thống tài chính/critical batch; yêu cầu nghiệp vụ quyết định hard gates.

## 5. Thiết kế ma trận workload đại diện

Workload production hiếm khi chỉ có một loại item. Ngay cả khi total records giữ nguyên, sự phân bố quyết định lock, memory, reader skew và downstream latency.

### 5.1. Các chiều cần thay đổi

| Chiều | Trường hợp nhẹ | Trường hợp khó | Tác động |
| --- | --- | --- | --- |
| Số item | 100k | 20M+ | Metadata overhead vs volume |
| Kích thước item | 200 B | 2 MB | Heap/GC, serialization |
| Key distribution | Gần uniform | Một số hot keys 50% writes | DB row lock contention |
| Partition distribution | Đều | Một partition chiếm 70% records | Straggler critical path |
| Processor cost | 0.1 ms/item | 20 ms/item | CPU saturation |
| Reader/writer | In-memory fixture | PostgreSQL/network storage | I/O, connection pool |
| HTTP ratio | 0% | 30% items gọi API | In-flight/rate quotas |
| Error rate | 0% | 3% transient failures | Retry amplification |
| Retry/outage | Không | API 429/503 trong 10 phút | Backpressure và SLA |
| Source state | Frozen | Mutable input | Restart correctness |
| Concurrency môi trường | Job chạy một mình | Daily + backfill + online traffic | Shared resource contention |
| Cache | Warm | Cold sau deploy/failover | Startup/scan costs |
| Output pattern | Append distinct rows | UPSERT cùng hot rows | SQL locks/IOPS |
| Worker lifetime | Clean run | Kill giữa commit/reply | Restart và replay |
| Deadline | Rộng | Hẹp, recovery buffer nhỏ | Tính bền vững của tuning |

**Không nhất thiết phải lấy full Cartesian product** của 14 chiều (quá tốn). Hãy chọn profile đại diện, profile xấu nhất có khả năng xảy ra và các tương tác rủi ro cao.

### 5.2. Năm profile tối thiểu

1. **P1 – I/O streaming:** Nhiều records vừa, đọc JDBC/file ổn định, ít processor CPU.
2. **P2 – CPU-heavy:** Mỗi record nặng tính toán, dữ liệu phân bố tương đối đều.
3. **P3 – Write contention:** UPSERT nhiều vào vài hot business keys, nhiều row locks.
4. **P4 – Downstream latency:** 10–30% items gọi HTTP, có 429/p99 lớn và retry.
5. **P5 – Skew + restart:** Partition kích thước chênh lệch, kill worker rồi restart.

Đối với module scaling, **P3/P4/P5** thường quyết định cấu hình có thể vận hành an toàn hơn P1. Profile nào có tần suất cao thực tế phải được ưu tiên theo business traffic chứ không chỉ theo mức độ dễ benchmark.

### 5.3. Ghi rõ “workload fingerprint”

~~~yaml
# Ví dụ manifest của một benchmark scenario, KHÔNG phải file cần tạo.
scenarioId: batch-hotkeys-v1
snapshotId: immutable-snapshot-2026-11-20-v3
sourceCount: 12000000
sourceChecksum: sha256:verified-from-fixture
recordSizeP50Bytes: 850
recordSizeP99Bytes: 18000
hotKeyShare: 0.35
httpCallRatio: 0.10
injectedTransientFailureRate: 0.02
partitionManifestId: fixed-64-shards-v1
pipelineVersion: normalize-v3
repeatableRandomSeed: 429701
~~~

Đây là ví dụ record thông tin thí nghiệm, **không** thêm một file vào module. Trong thực tế phải tính các thống kê từ fixture; seed cố định không thay thế snapshot bất biến nếu nguồn ngoài thay đổi.

## 6. Reproducibility: thứ phải giữ cố định giữa baseline/candidate

Để so sánh cấu hình A và B, giữ nguyên:

- Source snapshot/version/checksum, số records và phân bố keys.
- Code logic nghiệp vụ, SQL schema/index/statistics, test workload generator.
- JobInstance *logical workload*: có thể dùng identifying test run ID khác để cô lập metadata, nhưng snapshot/output semantics phải tương đương.
- Partition names/ranges/manifest để không vô tình đổi bài toán.
- Vị trí deployment: pods, node type, CPU/memory limits, database và network topology.
- Concurrent online traffic hoặc load generator, thời điểm nếu có thể.
- Sampling period, measurement boundaries và cách tính throughput.
- Retry/skip policy và quality-gate criteria.
- GC/JVM flags, JDBC driver, broker config, Spring Batch version.
- Cache warmup policy; nếu kiểm thử cold start, phải áp dụng cold start tương đương.

### 6.1. Không chỉnh bốn tham số cùng lúc rồi gán toàn bộ công lao cho một tham số

Nếu A dùng `chunk=100`, `threads=4`, `pool=10` còn B dùng `chunk=1000`, `threads=32`, `pool=50`, chỉ biết **gói B khác gói A**. Không biết cái gì đã giúp hay gây regressions. Cách an toàn là thí nghiệm có **một biến ưu tiên**, sau đó khảo sát tương tác có chọn lọc.

Tuy nhiên, đôi khi tăng threads **bắt buộc** tăng resource allocation để tránh bottleneck giả; khi đó phải gọi rõ đó là **package change** và lập ma trận phân biệt: threads-only, pool-only, threads+pool. Không tuyên bố đã tách nguyên nhân nếu chưa đo.

### 6.2. Mỗi run có output namespace riêng

Nếu cùng snapshot được chạy 10 lần, không thể ghi tất cả vào một bảng output unique rồi lấy lần sau làm benchmark: writer có thể toàn `ON CONFLICT DO NOTHING`, khiến thời gian giảm vì **không còn ghi thật**.

Chọn một trong các cách:

- Reset database/test schema đúng quy trình trước mỗi run, bao gồm indices/caches theo policy.
- Dùng `outputRevision/runNamespace` riêng được tính là một phần key và bảo đảm cùng SQL path/IO profile.
- Clone snapshot/database ở cùng trạng thái đầu vào.
- Với database có dữ liệu tích lũy, định nghĩa profile “steady-state upsert” riêng, không trộn với “first insert”.

**Tuyệt đối đo business output trước/sau mỗi run.** Một benchmark nhanh vì writer bỏ qua tất cả records là benchmark sai mục đích.

## 7. Những nguồn nhiễu khiến lần benchmark thứ hai “tự nhiên nhanh”

### 7.1. Cold cache và warm cache

- OS page cache nóng dần sau lần scan đầu.
- PostgreSQL buffer cache có thể giữ data/index pages.
- Prepared statements/query plans/JDBC connections có thể đã warm.
- Connection pool startup/TLS handshake chỉ tốn lần đầu.
- JIT compilation/class loading và caches trong JVM được warm.
- Object storage metadata, DNS/TLS và remote API caches thay đổi theo thời gian.

Nếu **A chạy trước B** thì B có thể hưởng cache warm của A. Chạy B trước A hoặc randomize order/ABBA design sẽ giúp phát hiện order effect.

### 7.2. JVM JIT, GC và heap

Một Java batch job dài có thể thay đổi hiệu suất sau warmup, JIT optimize hoặc heap filling. Không cắt 30 giây warmup một cách máy móc nếu SLA thật **bao gồm cold startup**; thay vào đó báo cả:

- **Cold-start elapsed** từ khi process/job thật bắt đầu.
- **Steady-state throughput** sau warmup xác định.
- **Startup cost** riêng.
- **GC pauses, allocation rate, heap/RSS** suốt run.

Một candidate nhanh 10% steady state nhưng khởi động chậm thêm 12 phút có thể tệ cho job chạy 15 phút/ngày.

### 7.3. Database state và planner

Autovacuum, statistics, index bloat, checkpoints, WAL writes, lock waits và độ đầy bảng có thể thay đổi query performance. Nếu A chạy trên bảng nhỏ sạch còn B chạy trên bảng đã chèn 30 triệu rows, so sánh thiếu fairness.

Kiểm tra `EXPLAIN (ANALYZE, BUFFERS)`, table/index sizes, autovacuum và lock metrics khi cần. **Không** chạy `ANALYZE`/`VACUUM FULL` lên production chỉ để “làm sạch benchmark”; dùng môi trường test phù hợp và quy trình DB chuẩn.

### 7.4. Shared host/container contention

Một Kubernetes worker pod có CPU usage 40% nhưng bị throttling theo quota, hoặc database dùng chung với backup/online traffic, có thể chậm đột biến. Ghi lại CPU requests/limits, container restarts, node neighbors, DB connections, IO wait và network saturation. Đừng loại mọi run chậm như “outlier” nếu production thường gặp load đó.

## 8. Thực nghiệm lặp lại: không chọn lần nhanh nhất

Một đo đơn lẻ bị ảnh hưởng bởi noise và bias. Ngay cả 5 lần chạy cũng chỉ có ích nếu môi trường tương tự và không bị run order/confounding che lấp.

### 8.1. Baseline–candidate theo cặp

Thay vì `AAAAA BBBBB` luôn có nguy cơ B hưởng warm cache hoặc workload drift, cân nhắc:

~~~text
Warmup/pilot: A, B (không đưa vào kết luận chính nếu policy tách warmup)

Comparison rounds:
  round 1: A -> B
  round 2: B -> A
  round 3: A -> B
  round 4: B -> A

For each run:
  same snapshot distribution and output-work contract
  independent output namespace / reset state
  exact environment fingerprint
  correctness validation and metrics
~~~

Nếu chạy 2 phiên bản đồng thời để “công bằng về thời điểm”, chúng có thể **tranh nhau DB/API** và tạo thí nghiệm khác. Khi muốn concurrent load, hãy mô phỏng rõ shared traffic. Khi muốn đo từng candidate độc lập, không để chúng cạnh tranh cùng resource mà không ghi trong design.

### 8.2. Bao nhiêu repetitions là đủ?

Không có số `n=5` hay `n=30` phù hợp mọi workload. Chọn từ **pilot variance**, mức cải thiện nhỏ nhất đáng quan tâm và chi phí benchmark:

- Nếu một run mất 3 phút, 10–20 runs có thể khả thi.
- Nếu một run mất 8 giờ, có thể cần nhiều ngày/đại diện sharded runs và chấp nhận độ bất định lớn hơn.
- Nếu noise cao, làm sạch experimental design trước khi tăng n.
- Nếu không đủ samples, **ghi rõ uncertainty**, không tuyên bố cải thiện đã được chứng minh.

Không được tính 100.000 item latencies của **một job run** thành 100.000 phép lặp **độc lập** cho kết luận “cấu hình B nhanh hơn A qua các executions”; chúng có thể cùng chịu một DB outage, JVM GC hoặc node CPU contention.

## 9. Biến đổi số liệu từ “time” sang “đã commit thật”

Với snapshot có `N` unique items và tổng thời gian job `T` giây, mô hình đơn giản:

\[
R_{\mathrm{committed}}=\frac{N_{\mathrm{correct\ unique\ outputs}}}{T}.
\]

Nếu 12 triệu items cần có output, chỉ có 11,4 triệu đúng và 600.000 bị skip nhưng job chạy 1.000 giây, **không gọi** tốc độ là `12.000 items/s thành công`.

Cần ghi cả:

- `R_readAttempt`: attempts đọc/s, có thể gồm retry/restart.
- `R_processedAttempt`: attempts processor/s.
- `R_committed`: unique business outcomes đã commit/s.
- `R_published`: kết quả đã validate/publish/s nếu contract yêu cầu.
- `R_effective`: các output đúng/s theo quality oracle.

### 9.1. Ví dụ “nhanh do bỏ qua lỗi”

| Run | Elapsed | Read attempts | Valid unique output | Missing | Có đáng chọn? |
| --- | ---: | ---: | ---: | ---: | --- |
| A | 900 s | 12,1M | 12,0M | 0 | Có thể |
| B | 720 s | 12,0M | 11,4M | 600k | **Không** |
| C | 840 s | 12,3M | 12,0M | 0 | Cần xét variance/SLO/resource |

B “nhanh 20%” trên elapsed nhưng vi phạm invariants. C nhanh hơn A một lần nhưng chưa chứng minh repeatability hoặc tail risk; cần nhiều runs.

### 9.2. Tính throughput qua checkpoint/restart

Một benchmark có fault injection ở 60% tiến độ phải tính **end-to-end recovery time**, gồm fail detection, worker replacement, rerun và reconciliation. Không chỉ đo “thời gian JobExecution #2” rồi bỏ qua 60% việc trước crash.

Có thể báo hai figures:

- `T_clean`: toàn bộ job trên clean run.
- `T_restart_total`: từ first launch đến final validated output sau fault, bao gồm downtime/recovery theo policy.

**Recovery correctness là hard gate** ngay cả khi `T_restart_total` dài hơn clean run.


## 10. Đọc thống kê đúng: trung bình, median, p95/p99 và uncertainty

Bảng giả định dưới đây là elapsed time của hai cấu hình trên cùng workload, tính bằng giây; con số được đặt để minh họa cách suy luận chứ không phải benchmark Spring Batch thực:

| Vòng | A: 8 workers | B: 16 workers | B nhanh hơn A? |
| --- | ---: | ---: | --- |
| 1 | 901 | 840 | Có |
| 2 | 865 | 859 | Ít |
| 3 | 915 | 882 | Có |
| 4 | 878 | 930 | Không |
| 5 | 889 | 852 | Có |
| 6 | 904 | 861 | Có |

Nếu chỉ lấy vòng 1, có thể báo `(901-840)/901 ≈ 6,8%`. Nhưng vòng 4 B chậm hơn A. Quyết định cần nhìn **phân phối của hiệu ứng và độ bất định**, không phải cherry-pick vòng nhanh nhất.

### 10.1. Trung bình hay median?

- **Mean elapsed** hữu ích khi tổng chi phí các lần chạy quan trọng, nhưng rất nhạy với tail/outlier.
- **Median elapsed** bền vững hơn trước một vài spikes, nhưng **không đại diện cho p99** khi SLA đòi đảm bảo phần lớn runs.
- **p95/p99 của từng chunk** cho biết tail của chunks, **khác** p95/p99 của **toàn JobExecution** qua nhiều runs.
- **Max partition time** có thể chi phối makespan của partitioned job dù median partition rất thấp.
- **Confidence interval** của hiệu ứng A/B mô tả độ bất định từ mẫu/thiết kế, không phải phạm vi của mọi lần chạy production.

Không gộp 10.000 chunk durations của một Job thành “10.000 independent JobExecution observations”. Chunk latencies trong một run có thể cùng chịu GC/DB locks/network outage, nên đơn vị suy luận phải phù hợp câu hỏi.

### 10.2. Phân tích theo cặp giảm nhiễu

Nếu mỗi round A/B được chạy trong môi trường/khung tải tương đồng, tính khác biệt cho từng cặp:

\[
d_i=T_{A,i}-T_{B,i}.
\]

`d_i > 0` nghĩa B nhanh hơn A trong cặp đó. Có thể tính median của `d_i`, mean và khoảng tin cậy của paired differences để xem hiệu ứng có đáng kể và bền không.

Nếu A và B **không thực sự paired** (ví dụ chạy mỗi cấu hình ở ngày khác, hardware khác), không được giả định d_i là paired experiment. Hãy dùng design đúng với dữ liệu hoặc chạy lại thí nghiệm.

### 10.3. Bootstrap confidence interval để truyền đạt uncertainty

Với mẫu hiệu ứng theo **run/round** đã được thiết kế phù hợp, có thể bootstrap các paired differences:

1. Thu thập n cặp A/B độc lập hợp lý ở cấp round.
2. Resample **các cặp** có hoàn lại, không resample từng chunk như run độc lập.
3. Tính thống kê quan tâm cho mỗi bootstrap sample (median `d` hoặc mean `d`).
4. Lấy quantiles 2,5% và 97,5% để có bootstrap percentile interval gần đúng.
5. Diễn giải phụ thuộc assumptions và số lượng runs; n nhỏ/serial correlation lớn cho kết quả kém tin cậy.

Nếu samples có **thứ tự thời gian và autocorrelation** (ví dụ DB warms dần), bootstrap i.i.d. có thể quá tự tin. Nên điều chỉnh thiết kế, dùng block/bootstrap theo sessions hoặc phân tích chuyên sâu; đừng lấy khoảng tin cậy hẹp giả làm chứng minh.

### 10.4. Thống kê không thay business judgment

Ngay cả khi B nhanh hơn A **có ý nghĩa thống kê 2%**, cải thiện ấy có thể không đáng tăng CPU cost 50% hoặc rủi ro mất restart safety. Ngược lại, cải thiện 15% nhưng uncertainty rộng cũng chưa đủ để rollout toàn cluster.

Cần xác định **minimum practical improvement** trước khi đo, ví dụ:

~~~text
Accept candidate only if:
  correctness/restart invariants all PASS
  p95 end-to-end job duration <= 75 minutes
  95% interval of paired improvement > +5% (when feasible)
  configured resource budgets not exceeded
  throughput/cost acceptable
  tail latency and failure rates not regressed materially
~~~

Đây chỉ là **decision policy ví dụ**, không phải chuẩn thống kê bắt buộc. Với dữ liệu ít, có thể phải ghi “inconclusive” và pilot thêm thay vì gán PASS từ một test may mắn.

## 11. Tính speedup, efficiency và giới hạn Amdahl

Cho baseline throughput `R_1` ở một worker và candidate throughput `R_C` ở C workers:

\[
S(C)=\frac{R_C}{R_1}
\]

là **speedup theo throughput**, với điều kiện cùng work/quality contract. Parallel efficiency:

\[
E(C)=\frac{S(C)}{C}.
\]

Ví dụ:

| Active workers C | Committed items/s | Speedup so với C=1 | Efficiency |
| --- | ---: | ---: | ---: |
| 1 | 120 | 1,00× | 100% |
| 2 | 229 | 1,91× | ~95% |
| 4 | 413 | 3,44× | ~86% |
| 8 | 670 | 5,58× | ~70% |
| 16 | 720 | 6,00× | 37,5% |
| 32 | 665 | 5,54× | ~17% |

Bảng **giả định** cho thấy từ 16 lên 32 workers, committed throughput **giảm** vì contention/coordination mặc dù nhiều threads hơn.

### 11.1. Amdahl's law là giới hạn lý tưởng

Nếu `s` là phần công việc không thể song song hóa, số processors/workers `C`, trong mô hình cố định công việc và không có overhead:

\[
S_{\mathrm{ideal}}(C)\le
\frac{1}{s+(1-s)/C}.
\]

Nếu `s=0.10` và `C=16`:

\[
S_{\mathrm{ideal}}\le
\frac{1}{0.10+0.90/16}\approx6.40.
\]

Đây là **upper bound từ mô hình**, không có nghĩa job chắc đạt 6,40×. Spring Batch còn metadata DB, thread scheduling, writer locks, network, skew, retry, CPU/heap và broker, khiến hiệu quả thấp hơn.

### 11.2. Các điểm serial hóa thực tế

- Một `ItemReader` có cursor/state và không thread-safe, phải khóa chung.
- JobRepository metadata updates trên cùng tables/row versions.
- Writer update cùng hot account/aggregate rows.
- Một external API chỉ chấp nhận 20 requests in-flight.
- Job validation/publish là bước tuần tự sau tất cả partitions.
- Một partition có skew quá lớn và là critical path.
- Single manager dispatch/replies là bottleneck trong remote patterns.

Nếu bottleneck là một tài nguyên serial, **tăng threads làm tăng queue wait, không tạo thông lượng**.

### 11.3. Phân biệt weak scaling và strong scaling

- **Strong scaling:** tổng work N giữ nguyên, tăng workers, đo thời gian hoàn thành.
- **Weak scaling:** work mỗi worker giữ gần tương đương, tăng N theo số workers, đo thời gian/throughput ở tải lớn hơn.

Một benchmark từ 1M records trên 2 workers lên 8M trên 16 workers là **weak scaling**, không thể dùng trực tiếp để nói fixed 1M data sẽ nhanh gấp tám. Báo rõ mô hình và measurement units.

## 12. Little's law, queuing và dấu hiệu tối ưu nhầm chỗ

Trong một hệ thống ổn định, quan hệ trung bình:

\[
L=\lambda W
\]

với `L` là số requests/items đang ở trong hệ thống, `\lambda` là throughput (per second) và `W` là thời gian từ vào tới ra (seconds). Phải xác định ranh giới: `HTTP in-flight`, `JDBC connections held` hay toàn pipeline có cả queue.

### 12.1. Ví dụ API limiter

Nếu downstream trung bình mất `W=0.4s` mỗi call, chỉ cho `C_{\mathrm{http}}=12` calls in-flight thì lý tưởng:

\[
R_{\mathrm{http}}\lesssim\frac{12}{0.4}=30\ \mathrm{requests/s}.
\]

Nếu mỗi item cần một API call và job phải làm 500 items/s, **đẩy workers từ 8 lên 64 không giải quyết quota này**. Cần thay số API calls/item, batch API, cache hợp lệ, tăng quota có phê duyệt hoặc điều chỉnh SLA.

**Lưu ý:** `30 requests/s` chỉ là upper approximation khi latency ổn định, một request chiếm một slot trong toàn thời gian và không tính timeouts/retries. Rate limiter riêng có thể giới hạn thấp hơn.

### 12.2. Queue growth khi input vượt downstream

Nếu upstream tiếp nhận `R_{\mathrm{in}}=300` items/s mà downstream chỉ hoàn tất `R_{\mathrm{out}}=120` items/s, sau 10 phút:

\[
\Delta Q\approx(300-120)\times600
=108{,}000\ \text{items}.
\]

Nếu `Q` là executor queue trong heap, benchmark có thể thấy read throughput cao ban đầu, rồi OOM/timeout nhiều phút sau. Nếu queue là durable broker/manifest, có thể chịu được backlog nhưng vẫn phải tính retention, age và deadline. **Không gọi ingest rate tăng là scaling success khi backlog không drain**.

### 12.3. Coordinated omission

Nếu load generator chỉ gửi request mới sau khi request trước hoàn thành, lúc hệ thống chậm nó **tự giảm tốc phát**. Latency đo được có thể thấp hơn điều người dùng gặp dưới arrival pattern cố định — một dạng **coordinated omission**. Trong batch, biểu hiện tương tự là chỉ đo successful chunks và bỏ qua thời gian worker chờ queue/permit hoặc giờ hệ thống ngừng nhận việc.

Hãy phân biệt:

- **Open-loop arrival/load:** work đến theo schedule không bị hãm bởi response (đến khi admission/capacity policy từ chối).
- **Closed-loop load:** worker gửi work kế tiếp sau khi xong work trước.
- **End-to-end backlog age:** thời gian từ work ready/queued tới validated output.
- **Service time:** thời gian thực sự xử lý khi tài nguyên đã được cấp.

Tùy workload production mà chọn mô hình phù hợp; không chỉnh metrics để che thời gian chờ.

## 13. Vì sao Spring Batch cần benchmark ở đúng ranh giới transaction?

`chunkSize` có ảnh hưởng trực tiếp tới:

- Số chunk commits, JobRepository checkpoint updates.
- JDBC round trips và batch writer efficiency.
- Memory giữ items/objects/buffer trong một chunk.
- Lock hold time và rollback scope khi chunk thất bại.
- Retry behavior, commit interval, reader state persistence.
- Độ trễ graceful stop và khả năng khôi phục sau crash.

Một `chunk=2000` có thể thắng `chunk=200` trong clean run vì giảm metadata/commit overhead, nhưng thua hẳn khi lỗi 1% chunks: mỗi rollback/retry làm lại nhiều work hơn.

### 13.1. Mô hình chi phí giản lược

Giả sử:

- `N` items.
- `K` items/chunk.
- `t_item` trung bình xử lý một item.
- `h_commit` overhead mỗi chunk commit.

Trong trường hợp chạy tuần tự, không lỗi:

\[
T(K)\approx N\,t_{\mathrm{item}}
+\left\lceil N/K\right\rceil h_{\mathrm{commit}}.
\]

Mô hình giải thích vì sao tăng K giảm commit overhead. Nó **bỏ qua** memory, DB lock waits, batch latency, failure/retry, writer size effects và parallelism; không dùng nó để tối ưu K tới vô hạn.

### 13.2. Benchmark chunk size kèm failure profile

| Chunk K | Committed throughput clean (giả định) | p99 TX latency | 1% injected failure | Kết luận |
| --- | ---: | ---: | --- | --- |
| 50 | 480 items/s | 90 ms | Retry cost thấp | Có thể metadata-bound |
| 200 | 690 items/s | 280 ms | Chịu được | Candidate |
| 500 | 740 items/s | 900 ms | Rollback tốn hơn | Cần SLO check |
| 2000 | 770 items/s | 4,2 s | Retry tail rất xấu | Không chọn từ clean speed |
| 5000 | 720 items/s | 12 s | Lock/memory đắt | Regression |

Không lấy 770 items/s làm “winner” nếu job phải đáp ứng graceful stop ≤5s, metadata/correctness hoặc p99 DB transaction latency. Chọn trên **Pareto frontier** của throughput, tail, resource, recovery và vận hành.

### 13.3. Không tối ưu bằng cách giảm độ an toàn checkpoint

Tắt `saveState` hoặc đổi reader không checkpoint có thể làm clean run nhanh hơn chút, nhưng restart sau fail có thể đọc từ đầu/bỏ qua data. Nếu job phải restart, benchmark không có checkpoint **không so sánh tương đương** với baseline có checkpoint.

Nếu business case cho phép “at most once” không restart hoặc full reprocess có versioned output, phải ghi hợp đồng rõ. Đừng âm thầm bỏ checkpoint chỉ vì số elapsed đẹp hơn.

## 14. Phân biệt threads, partitions, gridSize và datasource pool

| Tham số | Điều khiển | Không đồng nghĩa với |
| --- | --- | --- |
| `taskExecutor.corePoolSize` | Số threads cốt lõi theo executor semantics | Số partition logic |
| `taskExecutor.maxPoolSize` | Trần threads có thể tạo | Throughput đảm bảo |
| `taskExecutor.queueCapacity` | Pending tasks trong memory | Durable work queue |
| `Partitioner.partition(gridSize)` | Input/hint cho partitioning | Cố định số threads/pods |
| `gridSize` của partition manager | Hint/splitting dispatch | Trần database connections |
| `chunk(K)` | Số items mục tiêu mỗi transaction | Số concurrent chunks |
| Hikari `maximumPoolSize` | Trần JDBC connections của **một pool** | Trần DB cluster hay DB transaction throughput |
| Broker consumer concurrency | Consumers active | Unacked message prefetch |
| Kubernetes replicas | Số JVM instances | Cluster-wide quota tự điều chỉnh |

Một benchmark chỉ thay `maxPoolSize` trên executor nhưng để `queueCapacity=10000` có thể không tăng active threads vì backing `ThreadPoolExecutor` ưu tiên queue sau core threads. **Đo active workers thực**, không suy từ cấu hình.

### 14.1. Tổng pool size toàn cluster

Nếu 6 worker pods, mỗi pod Hikari max 20, manager pool 6, online services 25:

\[
C_{\mathrm{configured,total}}
=6\times20+6+25=151.
\]

Nếu DB chỉ dành `120 connections` cho các thành phần này, cấu hình đã oversubscribe trước khi tính rollback/rolling surge. Một run trong lúc chỉ hai pods active có thể pass, nhưng **max rollout pods** có thể làm DB connection exhaustion. Benchmark phải ghi actual/configured pool budgets và concurrency toàn cluster.

### 14.2. Bounded executor mẫu trong Spring

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean("partitionExecutor")
public ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setThreadNamePrefix("batch-partition-");
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setWaitForTasksToCompleteOnShutdown(true);
    return executor;
}
~~~

Đây là bean method trong `@Configuration`; container Spring quản lý lifecycle/initialization. Ví dụ **4 active threads tối đa** và queue 16 tasks. Khi quá tải, task có thể bị reject, nên Spring Batch/job phải có recovery policy phù hợp. Đừng biến executor queue thành database công việc không bền.

### 14.3. Spring Batch 5.2 partition manager minh họa

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;

@Bean("partitionManagerStep")
public Step partitionManagerStep(
        JobRepository repository,
        Partitioner immutablePartitioner,
        @Qualifier("workerStep") Step worker,
        @Qualifier("partitionExecutor") TaskExecutor executor) {

    return new StepBuilder("partitionManagerStep", repository)
            .partitioner("workerStep", immutablePartitioner)
            .step(worker)
            .gridSize(16)
            .taskExecutor(executor)
            .build();
}
~~~

`immutablePartitioner` và `workerStep` là bean ứng dụng cung cấp. `gridSize(16)` là hint; executor được cấu hình cap 4 active trong ví dụ. Nếu partitioner tạo 16 shards, có thể chỉ 4 shards chạy đồng thời. Khi restart, partition names/ranges và source snapshot phải **không đổi**.

### 14.4. Multi-threaded step: benchmark phải kèm thread safety

Thêm `.taskExecutor(executor)` vào chunk-oriented worker step để chạy nhiều chunks song song không tự làm `ItemReader` stateful an toàn. Một `@StepScope` reader có thể bị **nhiều chunk threads trong cùng StepExecution** sử dụng; nó không phải `@ThreadScope`. Benchmark tăng threads có thể cho throughput cao nhưng bỏ sót/trùng item nếu reader không thread-safe. Test dữ liệu bằng unique business keyset/versions/hash, không chỉ timing.

### 14.5. Không lấy throttleLimit deprecated làm tuning mới

Trong Spring Batch 5.2, `throttleLimit` cho multi-threaded step đã **deprecated từ 5.0**. Nếu cần bounded chunk concurrency, cân nhắc executor và cơ chế `RepeatOperations`/`StepBuilder.stepOperations(...)` theo tài liệu Spring Batch tương ứng. Phải benchmark queue/rejection/stop/restart semantics, không chỉ chỉnh một con số deprecated rồi kết luận cải thiện.


## 15. Benchmark harness: đo run và kiểm chứng output

Một phép đo đáng tin phải ghi lại **scenario, identifying JobParameters, mã nguồn/cấu hình, elapsed, output version, resource metrics và quality gate**. Lưu một record riêng cho từng run; không chỉ in một dòng “duration=420s”.

### 15.1. Java 17: đo một JobExecution đồng bộ

~~~java
import java.util.UUID;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.jdbc.core.JdbcTemplate;

record BenchmarkResult(
        String candidate, String revision,
        double elapsedSeconds, long outputCount) {}

final class BatchBenchmarkRunner {

    private final JobLauncher launcher;
    private final Job job;
    private final JdbcTemplate businessJdbc;

    BatchBenchmarkRunner(
            JobLauncher launcher, Job job,
            JdbcTemplate businessJdbc) {
        this.launcher = launcher;
        this.job = job;
        this.businessJdbc = businessJdbc;
    }

    BenchmarkResult measure(
            String candidate, String snapshotId) throws Exception {

        // Mỗi CLEAN benchmark run có output riêng,
        // tránh lần sau chỉ thực hiện ON CONFLICT DO NOTHING.
        String revision = "bench-" + UUID.randomUUID();

        JobParameters params = new JobParametersBuilder()
                .addString("snapshotId", snapshotId, true)
                .addString("outputRevision", revision, true)
                .addString("candidate", candidate, true)
                .toJobParameters();

        long startNanos = System.nanoTime();
        JobExecution execution = launcher.run(job, params);
        long elapsedNanos = System.nanoTime() - startNanos;

        // Chỉ áp dụng khi JobLauncher được cấu hình đồng bộ.
        if (execution.getStatus() != BatchStatus.COMPLETED) {
            throw new IllegalStateException(
                    "Job not COMPLETED (or launcher is async): "
                    + execution.getStatus());
        }

        Long rowCount = businessJdbc.queryForObject(
                """
                SELECT COUNT(*) FROM normalized_event
                WHERE output_revision = ?
                """,
                Long.class, revision);

        return new BenchmarkResult(
                candidate, revision,
                elapsedNanos / 1_000_000_000.0,
                rowCount == null ? 0L : rowCount);
    }
}
~~~

Đây là **snippet hạ tầng benchmark**, không phải test production hoàn chỉnh. Nó giả định `normalized_event` có cột `output_revision` và writer thực sự ghi mỗi run vào revision đó. Nếu `JobLauncher` bất đồng bộ, `launcher.run(...)` có thể trả `STARTING`/`STARTED`; khi ấy cần `JobExplorer` poll theo **deadline hữu hạn** tới trạng thái terminal trước khi dừng đồng hồ và query output. Không đánh đồng elapsed của `run(...)` với toàn job khi launcher async.

`outputCount` chỉ là check sơ bộ: phải thêm **missing/extra/mismatched key/hash/version** oracle. Candidate không hợp lệ nếu output thiếu hoặc có lỗi nghiệp vụ dù JobStatus COMPLETED.

### 15.2. Phân biệt identity benchmark với restart

`UUID` trong ví dụ tạo JobInstance/output riêng **cho clean-run benchmark lặp lại**. Khi test restart, **không tạo revision/identifying params mới**: cùng JobInstance, tạo JobExecution mới theo `JobOperator.restart(executionId)` sau khi job FAILED/STOPPED và recovery checks. Trong production, identity phải gắn business date, snapshot và logic version, không tạo random `run.id` để lách completed status.

### 15.3. Phạm vi đo

~~~text
T_queue_wait = READY -> Job launch
T_job        = Job launch -> terminal JobExecution
T_validation = Job terminal -> output reconciliation
T_publish    = validation -> published revision
T_end_to_end = sum all phases
~~~

`System.nanoTime()` là đồng hồ elapsed trong một JVM; nếu worker/manager crash, test controller cần giữ outer clock. Không trừ timestamps của hai pods khi chưa có clock synchronization. Báo riêng **cold startup** và **steady-state** nếu cả hai có giá trị theo SLA.

### 15.4. Structured report mẫu

~~~json
{
  "scenario": "hotkeys-v1",
  "candidate": "C16-K250-pool12",
  "snapshotId": "immutable-v42",
  "runId": "round-07-B",
  "cacheProfile": "warm-cache",
  "inputCount": 12000000,
  "validUniqueOutput": 12000000,
  "elapsedSeconds": 720,
  "committedItemsPerSecond": 16666.7,
  "p99ChunkLatencyMs": 650,
  "hikariAcquireP99Ms": 18,
  "rollbackCount": 0,
  "missingKeyCount": 0,
  "mismatchCount": 0,
  "status": "COMPLETED",
  "note": "synthetic illustrative data"
}
~~~

Đây là **số liệu giả định**, không phải measurements. `committedItemsPerSecond` được làm tròn từ `12.000.000/720`; report thật nên có checksum đã tính, JVM flags, DB schema/index stats, git commit và environment fingerprint.

## 16. Đo từng tầng: Job, Step, executor, JDBC, network

| Tầng | Metric cần có | Nếu xấu thì xem gì? |
| --- | --- | --- |
| Job | End-to-end elapsed, committed unique items/s, status | SLA/restart |
| Step | Read/write/commit/rollback/filter/skip counts | Retry/skip/correctness |
| Partition | Duration per shard, max/p95, skew ratio | Critical path/straggler |
| Executor | Active/queued/rejected tasks | Threads, queue/backpressure |
| Hikari | Active/idle/pending, acquire/hold p99 | Pool starvation |
| Business DB | Query p99, row lock waits, WAL/IOPS, deadlocks | SQL/hot keys |
| JobRepository | Metadata update latency, optimistic conflicts | Chunk/partition overhead |
| HTTP | Requests/s, inflight, p95/p99, 429/503 | Quota/latency/retry |
| Broker | Ready/unacked, redelivery, reply lag | Remote dispatch/recovery |
| JVM/K8s | CPU throttling, heap/RSS, GC pauses, OOMKills | Resource saturation |
| Correctness | Missing/extra/mismatch keys, duplicate external effects | Invalid benchmark |

Tên metrics cụ thể phụ thuộc Spring Batch 5.2, Micrometer, Hikari, broker và code instrumentation. Bảng là **danh sách phải đo**, không khẳng định mọi metric có sẵn mặc định.

### 16.1. Ví dụ Micrometer Timer cho phase riêng

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

final class PhaseMetrics {
    private final MeterRegistry registry;

    PhaseMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    <T> T timed(String scenario, CheckedAction<T> action)
            throws Exception {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";
        try {
            return action.execute();
        } catch (Exception ex) {
            outcome = "error";
            throw ex;
        } finally {
            sample.stop(Timer.builder("batch.phase.duration")
                    .tag("scenario", scenario)
                    .tag("outcome", outcome)
                    .register(registry));
        }
    }

    interface CheckedAction<T> {
        T execute() throws Exception;
    }
}
~~~

Đoạn này đo duration của method được bọc, **không tự tương đương chunk transaction duration**. Tránh dùng `JobExecutionId`, business key hoặc vô số partition IDs làm metric tags vì high cardinality; đưa IDs vào logs/traces.

### 16.2. Phân biệt JDBC acquire, hold, SQL và TX duration

- **Acquire latency**: chờ Hikari cấp JDBC connection.
- **Hold duration**: từ lúc mượn tới trả connection.
- **SQL execution/lock waits**: truy vấn chậm vì CPU/IO/locks.
- **Chunk transaction duration**: begin → commit/rollback.

Nếu acquire p99 cao nhưng SQL nhanh, threads có thể đợi pool. Nếu SQL lock waits cao nhưng acquire nhanh, tăng pool chỉ khiến thêm transactions tranh hot rows. Nếu worker giữ connection khi chờ HTTP, transaction boundaries cần sửa trước khi tăng pool.

## 17. Một ma trận tuning có kiểm soát

Trình tự thực hành:

1. Đo **baseline production config** trên P1–P5 qua nhiều repeated runs.
2. Xác định bottleneck/giả thuyết thay đổi: chunk overhead, SQL locks, CPU, skew, API quota?
3. Thử `K=100,250,500,1000` với cùng C/pool để hiểu ảnh hưởng chunk.
4. Thử `C=2,4,8,16` với K hợp lý trong resource budgets.
5. Đo Hikari occupancy/hold time, không tự tăng pool tới max_connections.
6. Thử selected `C×K` interactions để phát hiện memory/lock amplification.
7. Inject 429/503, DB timeout, skew và worker crash vào top candidates.
8. So repeated paired runs và uncertainty; nếu inconclusive thì đo thêm.

### 17.1. Ma trận minh họa

| Run | Workers C | Chunk K | Hikari max/pod | Partitions P | Câu hỏi |
| --- | ---: | ---: | ---: | ---: | --- |
| A | 4 | 100 | 8 | 16 | Baseline |
| B | 4 | 250 | 8 | 16 | Chunk commit overhead |
| C | 4 | 500 | 8 | 16 | Memory/rollback |
| D | 8 | 250 | 8 | 16 | C vượt pool không? |
| E | 8 | 250 | 12 | 16 | Pool interaction |
| F | 16 | 250 | 12 | 16 | DB contention |
| G | 16 | 500 | 12 | 16 | Long TX × C |
| H | 16 | 500 | 12 | 64 | Skew/partition overhead |
| I | 16 | 500 | 12 | 64 | Worker kill/restart |
| J | 8 | 250 | 12 | 64 | HTTP quota/retry |

Khi C=16 và pool=12, workload một-connection-per-worker có thể nghẽn; workload tách HTTP ngoài transaction có thể vẫn đủ vì connection occupancy thấp. **Đo occupancy, không chỉ nhìn con số pool.**

### 17.2. Interaction experiment

One-factor-at-a-time giúp giải thích một biến nhưng bỏ lỡ tương tác. Sau pilot, thử factorial subset:

~~~text
C in {4, 8, 16}
K in {100, 500}
6 combinations, each with repeated runs
~~~

Không gọi candidate thắng trong 6 combinations là “global optimum”. Chỉ kết luận **tốt nhất trong phạm vi đã đo**.

### 17.3. Giữ input invariant khi đổi P

Với P=16 hay P=64, tổng source snapshot/keyset/logic phải giống nhau để so hiệu năng chia shard. Sự thay đổi P có thể kéo theo **partition plan khác**, vì vậy dùng JobInstance benchmark **mới** có output namespace riêng; **không đổi ranges/names giữa restart của cùng JobInstance**.

### 17.4. Không tối ưu theo một seed

Nếu seed P1 tạo keys uniform, candidate có thể rất tốt; nhưng P3 hot keys gây lock contention. Cả A và B nên chạy trên **cùng sets of seeds/profiles** và tổng hợp theo từng profile. Không để cải thiện trung bình che một regression nghiêm trọng ở workload bắt buộc.


## 18. Truy bottleneck bằng dữ liệu trước khi tăng concurrency

### 18.1. Cây chẩn đoán rút gọn

~~~mermaid
flowchart TD
    A["Committed throughput thấp"] --> B{"Output correctness PASS?"}
    B -->|No| FIX["Dừng tuning: sửa missing/duplicate/skip"]
    B -->|Yes| C{"CPU worker gần quota?"}
    C -->|Yes| CPU["CPU profile / JIT / GC / algorithm"]
    C -->|No| D{"Hikari pending hoặc DB lock waits?"}
    D -->|Yes| SQL["SQL plans / TX duration / hot keys / pool"]
    D -->|No| E{"API 429/p99 hoặc broker lag?"}
    E -->|Yes| NET["Rate/inflight limit / retries / backpressure"]
    E -->|No| F{"Metadata latency hoặc skew?"}
    F -->|Yes| PART["JobRepository / P / K / critical path"]
    F -->|No| TRACE["Trace reader/processor/writer và cache"]
~~~

Nhiều bottlenecks có thể cùng tồn tại; sơ đồ chỉ hướng kiểm tra, không phải chứng minh nguyên nhân. Sau khi xử lý một bottleneck, bottleneck mới có thể lộ ra.

### 18.2. DB-bound không nhất thiết thiếu connections

~~~text
Active workers       16/16
Hikari active/pending 12/4
DB CPU                22%
Row-lock wait p99     2.4 s
Committed throughput  320 items/s
~~~

Tăng pool 12→24 có thể cho thêm writers tranh hot rows và làm throughput **giảm**. Trước hết đo SQL query plan, index, lock ordering, transaction hold-time, hot keys và khả năng chia shard theo khóa ít tranh chấp.

### 18.3. CPU-bound không nhất thiết cần thêm threads

Pod chỉ có 4 vCPU với `ItemProcessor` CPU-heavy đã CPU-throttled. Tăng thread count từ 8 lên 32 có thể làm context switching/GC tăng. Thử optimize algorithm, tăng CPU allocation hợp lý hoặc phân phối workload qua pods có tổng DB/API budget đủ. So **items/s trên mỗi vCPU được cấp**, không chỉ tốc độ tuyệt đối.

### 18.4. Skew và metadata-bound

Nếu 63 partitions xong trong 4 phút nhưng một partition còn chạy 35 phút, critical path là shard nặng chứ không phải thiếu threads. Cải thiện split dựa trên **bytes/cost**, nhưng **không đổi partition names/ranges giữa restart cùng JobInstance**.

Ngược lại, 4096 partitions cực nhỏ có thể tạo overhead JobRepository/ExecutionContext, dispatch/serialization và reader setup lớn hơn useful work. Đo per-partition setup time và metadata latency trước khi tăng `gridSize`.

## 19. So sánh kiến trúc phải chuẩn hóa theo resource và restart

| Kiến trúc | Lợi ích tiềm năng | Điều cần benchmark ngoài clean throughput |
| --- | --- | --- |
| Single-threaded chunk | Đơn giản, ít overhead | Khả năng scale, elapsed |
| Multi-threaded Step | Chunks đồng thời | Reader/writer thread safety, restart |
| Parallel Steps | Flows độc lập chạy song song | Shared pool, dependencies |
| Local partitioning | Worker StepExecutions theo shards | Skew, manager/metadata overhead |
| Remote partitioning | Multi-JVM scaling | Broker, startup, lost reply, fencing |
| Remote chunking | Manager đọc, workers xử lý/ghi | Manager bottleneck, ACK/reply, replay |

Nếu baseline một JVM 4 vCPU còn candidate remote có 8 pods × 4 vCPU, speedup gấp 8 không tự chứng minh remote architecture hiệu quả hơn: CPU allocation đã tăng gấp 8. Báo throughput **per allocated vCPU**, memory/JDBC connections, broker/network bytes, chi phí mỗi triệu records và recovery time.

### 19.1. Tính startup, không chỉ worker processing

Remote worker xử lý 10 giây nhưng mất 45 giây start pods/JVM, init broker và aggregate replies có thể chậm hơn local job chỉ mất 30 giây. Với daily batch ngắn, **cold-start overhead** là phần lớn SLA. Đo từ Job ready cho tới output validated/published.

### 19.2. Restart semantics khác nhau

- Multi-threaded Step: share reader state/checkpoint, out-of-order chunks.
- Local partitioning: partition keys/ranges cố định, restart failed worker.
- Remote partitioning: process hard kill, lost ACK/reply và stale worker.
- Remote chunking: manager reader checkpoint, worker writer commits, message correlation.
- Parallel steps: dependencies và step-level partial completions.

Chỉ so sánh các candidates **đều đạt output và recovery contract**. Nếu một candidate nhanh nhờ bỏ checkpoint, nó không còn cùng workload contract.

## 20. Benchmark fault tolerance, không chỉ clean run

| Failure scenario | Mốc inject | Đo gì | Invariant |
| --- | --- | --- | --- |
| Processor/writer error | Trong chunk trước commit | Rollback/retry duration | Không partial writes |
| Worker hard kill | Sau business commit trước reply | Recovery time/redelivery | Không duplicate effects |
| Metadata DB outage | JobRepository updates | Checkpoint/restart lag | Không success giả |
| DB deadlock | Hot row writes | Lock wait/retry amplification | Writer atomic |
| HTTP 429/503 | Downstream fake server | Rate/backoff/queue age | Không skip required data |
| Broker ACK/reply lost | Transport | Requeue/retry | Idempotent output |
| Memory OOMKill | Large chunks/prefetch | Restart, heap/RSS | Không mất durable work |
| Partition skew | One heavy shard | Max partition duration | Full keyset |
| Daily + backfill | Shared pools | Daily SLA regression | Hai jobs đều đúng |
| Rolling update | Old/new pods active | Global quotas | Không double worker owner |
| Mutable input | Source changes after fail | Manifest detection | Fail closed |

### 20.1. Tổng recovery time phải được định nghĩa

~~~text
T_detect   = worker crash -> incident observed
T_drain    = time to resolve in-flight / ACK / lease
T_repair   = reconcile ambiguous business state
T_restart  = replacement process/worker ready
T_resume   = remaining processing -> COMPLETED
T_validate = final output reconciliation

T_recovery = sum of phases
~~~

Chỉ đo `T_resume` của worker mới sẽ che thời gian phát hiện lỗi, đợi lease và repair. Với SLA chặt, cần dự trữ headroom cho tail của cả chuỗi.

### 20.2. SQL oracle cơ bản sau crash/restart

~~~sql
-- Records từ immutable input chưa xuất hiện trong output.
SELECT event_id
FROM frozen_source_event
WHERE snapshot_id = :snapshotId

EXCEPT

SELECT event_id
FROM normalized_output
WHERE output_revision = :revision;
~~~

Query phải rỗng. Thêm phép `EXCEPT` ngược để tìm extra keys và join so versions, hashes, amounts. Không chỉ so `COUNT(*)`: missing/extra có thể triệt tiêu nhau.

Nếu business writer và JobRepository dùng **hai local datasources không atomic**, cần test:

- Business commit nhưng checkpoint cũ ⇒ replay, duplicate risk.
- Checkpoint tiến còn business chưa commit ⇒ missing risk.

Writer idempotent chống replay nhưng **không tự sinh item bị reader bỏ qua**; cần reconciliation và repair plan.

### 20.3. Những “tối ưu” không công bằng

Một candidate có thể nhanh hơn vì tắt `ItemStream.saveState`, loại kiểm tra idempotency, dùng skip để nuốt business errors, bỏ ACK/reply verification, hoặc publish async không đợi completion. Nếu tính đúng đắn/restart contract bị phá, **loại candidate**; không gọi đó là optimization cùng bài toán.

## 21. Chọn cấu hình trên Pareto frontier, không chọn thời gian thấp nhất

Bảng **minh họa giả định** các candidate đã chạy lặp và có quality gate:

| Candidate | Median committed items/s | Job p95 | DB lock p99 | Worker recovery | Data correctness |
| --- | ---: | ---: | ---: | ---: | --- |
| A: C4 K100 | 460 | 82 phút | 80 ms | 4 phút | PASS |
| B: C8 K250 | 690 | 66 phút | 140 ms | 5 phút | PASS |
| C: C16 K500 | 760 | 61 phút | 900 ms | 18 phút | PASS |
| D: C32 K1000 | 790 | 88 phút | 4 s | 34 phút | PASS |
| E: C32 K2000 | 810 | 55 phút | 5.1 s | — | **FAIL: missing keys** |

Nếu hợp đồng yêu cầu **p95 job ≤75 phút**, A và D không đạt. E bị loại ngay vì mất dữ liệu dù median throughput cao nhất. C có throughput hơn B nhưng recovery/lock waits xấu hơn. Chọn B hay C còn phụ thuộc SLA recovery, resource headroom và uncertainty của repeated runs.

### 21.1. Thứ tự ra quyết định

1. **Hard correctness gates:** missing=extra=mismatch=0, external effects idempotent, restart PASS.
2. **SLA/contract gates:** job p95/p99, recovery time, API/DB quotas, deadline.
3. **Operational risk:** contention, pool saturation, metadata lag, retries, rollout safety.
4. **Efficiency:** committed throughput, cost per good item, CPU/DB/broker consumption.
5. **Uncertainty:** hiệu ứng có lặp lại trên profiles/runs không?
6. **Rollback:** chuyển lại cấu hình trước có giữ nguyên JobInstance/partition state không?

Không dùng weighted score để “bù” mất dữ liệu bằng tốc độ. Score chỉ hữu ích **sau** khi hard gates PASS.

### 21.2. Kết luận “inconclusive” khi chưa đủ bằng chứng

Nếu chênh lệch giữa A/B nhỏ hơn noise, candidate chỉ chạy P1 chưa chạy P3/P4, hoặc chưa kiểm worker restart, kết luận đúng là **chưa đủ dữ liệu**. Đo thêm representative scenario/profiler hoặc làm canary với guardrails, không chọn từ một run đẹp.


## 22. Tránh overfitting benchmark bằng validation workload và rollout an toàn

Một candidate có thể “tối ưu” rất tốt cho bộ benchmark do chính người phát triển chọn nhưng hoạt động kém với workload chưa từng dùng để tune. Tương tự machine learning, cần **đánh giá ngoài bộ dùng để quyết định cấu hình**.

### 22.1. Tách tune set và validation set

Ví dụ:

- **Tune set:** ba snapshots đại diện, có uniform, CPU-heavy và một phân bố hot keys.
- **Validation set:** các snapshot/seed khác, trong đó có skew nghiêm trọng, dữ liệu đến muộn và API timeout.
- **Production canary:** workload thật có guardrails, được quan sát độc lập với tuning.

Candidate không được sửa tham số sau khi biết kết quả validation set rồi vẫn dùng chính bộ đó làm “bằng chứng khách quan”. Khi đổi candidate, ghi nhận validation set đã trở thành một phần vòng tune và cần thêm holdout hoặc production canary.

### 22.2. Khi không thể shadow-write trực tiếp

Một cách kiểm chứng candidate là **shadow run** trên cùng source snapshot, ghi vào output revision riêng rồi so keyset/hash/amount; **không publish** revision thử nghiệm.

Nhưng nếu worker gọi API thanh toán, gửi email hoặc tạo side effects không idempotent, **không được shadow-run hai phiên bản tạo effect thật**. Cần fake/sandbox downstream, dry-run side-effect policy có chứng minh, hoặc canary với partition input disjoint và operation keys ổn định.

### 22.3. Canary rollout theo cấp độ

Một quy trình gợi ý:

1. **Preflight:** baseline report, candidate config diff, rollback values, owner và SLO.
2. **Staging:** tune/validation/fault/restart tests PASS.
3. **Canary 1:** chạy trên một tập input hợp lệ nhỏ, output version riêng, giới hạn concurrency/rate.
4. **Canary 2:** tăng tỉ lệ workload trong budget nhưng giữ daily/online headroom.
5. **Peak observation:** quan sát trong cửa sổ có load đại diện, không chỉ lúc đêm vắng.
6. **Scale-up:** tăng workers/pods từng bước, ghi metrics/giới hạn qua rolling surge.
7. **Final decision:** chuyển toàn bộ hoặc rollback nếu vi phạm hard gates.

Mốc tỉ lệ canary cần theo business impact và load; không có chuẩn “10% luôn an toàn”. Với batch xử lý **phân hoạch**, đảm bảo canary và baseline không cùng ghi một business key không versioned.

### 22.4. Canary rollback không đồng nghĩa đảo ngược dữ liệu

Giảm `workers`/`chunkSize` cho **JobInstance mới** có thể dễ. Nhưng khi một Step đang chạy dở, thay partition manifest hoặc reader checkpoint giữa restart có thể làm sai dữ liệu. Rollback config phải chia thành:

- **Runtime tuning reversible:** executor concurrency, queue caps, admission rate trong giới hạn và sau kiểm thử.
- **Restart-sensitive settings:** chunk checkpoint assumptions, partition names/ranges, reader/writer state layout.
- **Business schema/logic:** output versions, SQL semantics, API operation keys.
- **Infrastructure:** DB pool, broker consumers, pod replicas, rollout overlap.

Nếu change ảnh hưởng checkpoint format hoặc partition plan, cần **migration/reprocess revision** có thử nghiệm; không áp “rollback binary” rồi resume cùng JobInstance tùy ý.

## 23. Lập kết quả cuối dưới dạng quyết định có thể kiểm toán

Đừng chỉ ghi “B nhanh hơn 15%, đã chọn B”. Một bản **performance decision record** ngắn nên có:

~~~text
Decision ID:         batch-tuning-2026-11-26-07
Current config:      C=8, K=250, P=32, DB pool=12/pod
Candidate config:    C=12, K=250, P=32, DB pool=12/pod
Reason/hypothesis:   Workers IO-bound, Hikari occupancy has headroom
Scenarios:           P1..P5, same immutable snapshots
Repetitions:         10 paired rounds (ordered/randomized)
Primary measure:     committed unique items/s
Secondary measures:  job p95, chunk p99, lock waits, CPU/RSS,
                     connection pending, retry/rollback, cost
Correctness:         missing=0, extra=0, mismatch=0
Restart:             process kill + replay safety PASS
Observed effect:     +X% median, 95% interval [L,U] (measured)
Risk/tradeoff:       resource use and failure tail documented
SLA decision:        PASS / FAIL / INCONCLUSIVE
Rollout:             staged canary with guardrails
Rollback:            restore former worker cap; do not mutate plan
Owner/approval:      ...
~~~

**`X`, `L`, `U` là chỗ cần thay bằng số thực**; không tự tạo confidence interval vì báo cáo “nên có”. Nếu chưa đủ dữ liệu, ghi `INCONCLUSIVE` và lý do.

### 23.1. Tiêu chí chọn trước khi xem kết quả

Chốt trước:

- Workload profiles bắt buộc.
- Primary metric và đơn vị measurement.
- Minimum practical improvement.
- Hard correctness/restart gates.
- p95/p99 hoặc worst-case SLO.
- Pool/API/CPU/memory/resource budgets.
- Cách làm warmup và cache policy.
- Số rounds, run order và phương pháp xử lý invalid runs.
- Ngưỡng rollback/canary stop.

Nếu nhìn kết quả xong mới đổi primary metric từ throughput sang median chỉ vì candidate thắng, đã mắc **selection bias**. Cho phép exploratory findings, nhưng ghi nhãn “exploratory” và xác nhận trên runs mới.

### 23.2. Không loại outlier chỉ vì chậm

Một run chậm do PostgreSQL autovacuum hoặc GC long pause có thể là **đặc tính production thật**. Chỉ loại run khỏi phân tích chính nếu đã có **quy tắc loại hợp lệ chốt trước**, ví dụ fixture migration failed hoặc một node bị mất điện ngoài test contract. Báo riêng tỉ lệ invalid/outlier; đừng âm thầm xóa lần chạy xấu.

## 24. Runbook tuning hiệu năng có kiểm soát

### 24.1. Trước benchmark

1. Xác định job name, dataset snapshot, volume, business SLA và quality gate.
2. Chốt **cấu hình baseline** cùng code commit, DB schema, JVM, worker/pod specs.
3. Lập workload profiles: I/O, CPU, hot-key, skew, downstream latency, restart.
4. Chọn primary metric: **committed unique items/s** và end-to-end elapsed.
5. Định nghĩa secondary/tail metrics và resource budgets.
6. Tạo immutable source/partition manifests; fingerprint data.
7. Chuẩn bị output namespace/reset strategy để mỗi run ghi thật.
8. Chọn warm/cold cache policy, startup measurement và run order.
9. Thống nhất repetitions/decision threshold trước khi thấy số liệu.
10. Thiết lập dashboards và fault injection có kiểm soát.

### 24.2. Trong benchmark

11. Chạy pilot/warmup và đo variance ban đầu.
12. Chạy A/B theo randomized/interleaved order khi phù hợp.
13. Kiểm tra job status **và business correctness sau mỗi run**.
14. Ghi read/write/commit/rollback, memory/CPU, Hikari, DB locks, HTTP/broker.
15. Ghi actual workers/pods active, không chỉ config declared.
16. Theo dõi drift: cache, DB size, background jobs, index stats, network.
17. Nếu một run fail business oracle, ghi **invalid/fail**, không dùng throughput của nó làm evidence tốt.
18. Không tự thay nhiều tham số giữa rounds mà không versioned candidate ID.
19. Giữ nguyên input distribution/logic contract; không dùng previous output để tạo no-op run.
20. Khi có fault injection, ghi marker, observed recovery và final reconciliation.

### 24.3. Phân tích và quyết định

21. Tính median/mean, per-run variation, paired effect và uncertainty phù hợp.
22. Tách p95/p99 **chunk** khỏi p95/p99 **JobExecution** và recovery tail.
23. So từng workload profile; tìm những regression bị mean che.
24. Phân tích critical path partition, resource saturation và retry amplification.
25. Loại candidate vi phạm correctness, restart hoặc resource budgets.
26. Đánh giá Pareto tradeoff throughput/tail/recovery/cost.
27. Chọn PASS/FAIL/INCONCLUSIVE theo policy đã đặt.
28. Chạy validation set chưa dùng để tune.
29. Tạo canary plan, rollback plan và incident owner.
30. Lưu decision record cùng snapshot checksums và exact config.

### 24.4. Sau triển khai

31. Theo dõi trên production nhiều business cycles, gồm peak và cold-start.
32. Canh rollback triggers: p99/lock waits, 429/503, output mismatch, daily SLA.
33. Khi bất thường, giảm admission/concurrency có kiểm soát; không tăng tất cả pools.
34. Trước restart từ FAILED/STOPPED, giữ JobInstance identifying params và partition manifest.
35. Đối soát output trước publish; không chỉ nhìn `BatchStatus.COMPLETED`.
36. Cập nhật benchmark suite theo profile production mới, nhưng giữ benchmark lịch sử để biết regressions.

## 25. Những hiểu nhầm phổ biến

| Nhận định | Điều cần sửa |
| --- | --- |
| “Một lần chạy nhanh hơn 20% đủ để chọn.” | Cần lặp lại/uncertainty/workload representative. |
| “Lần chạy thứ hai nhanh hơn nghĩa code B tốt.” | Cache/JIT/DB warmed có thể là nguyên nhân. |
| “Chỉ nên đo median, p99 không quan trọng.” | SLA/recovery có thể bị tail quyết định. |
| “p99 của 10.000 chunks là p99 của 10.000 jobs.” | Sai đơn vị mẫu, không độc lập. |
| “Có nhiều items/s đọc là throughput tốt.” | Phải đo business effects đã commit và validated. |
| “Job COMPLETED nghĩa output đúng.” | Missing/extra/hash/external effects cần oracle. |
| “Chunk càng lớn càng nhanh.” | Memory/locks/rollback/stop latency tăng. |
| “Nhiều threads luôn tăng throughput.” | Amdahl, DB contention, API quotas, metadata. |
| “GridSize là số worker threads.” | Partition hint khác executor/pods. |
| “Hikari max 32/pod nghĩa DB chỉ dùng 32 connections.” | Cộng mọi pods/pools/services. |
| “Tăng pool luôn chữa SQL lock waits.” | Có thể tăng thêm contention. |
| “CPU usage thấp thì còn khả năng scale threads.” | Worker có thể chờ JDBC/API/broker. |
| “Remote nhanh 8× thì kiến trúc 8× hiệu quả.” | Có thể dùng 8× CPU/pods; đo cost/throughput. |
| “Chỉ cần benchmark cache warm.” | Batch ngắn có thể cold start thường xuyên. |
| “Không cần đo startup nếu worker xử lý nhanh.” | E2E SLA gồm startup/dispatch/publish. |
| “Benchmark 1M rows dự đoán chuẩn 100M rows.” | DB size/skew/memory/index/metadata thay đổi. |
| “Tăng P là cách sửa partition skew khi restart.” | Không thay partition plan cùng JobInstance. |
| “Lỗi transient được skip để đo throughput.” | Không còn cùng business contract. |
| “ON CONFLICT DO NOTHING khiến test có output và rất nhanh.” | Output có thể từ run trước; phải cô lập namespace. |
| “A/B cùng lúc luôn công bằng hơn.” | Hai candidate có thể tranh cùng DB/API, tạo confounder. |
| “10 lần chạy trong cùng phút đều độc lập.” | Cache/time autocorrelation có thể làm confidence giả. |
| “Outlier chậm là noise, xóa hết.” | Có thể là production tail thật; cần rule chốt trước. |
| “Confidence interval hẹp là bằng chứng mọi SLA pass.” | Interval của hiệu ứng khác distribution/tail của jobs. |
| “Test JUnit exception đủ chứng minh worker crash safety.” | Hard-kill/lost reply/commit unknown khác exception. |
| “Idempotent upsert sửa cả item bị checkpoint skip.” | Chỉ bảo vệ replay; missing cần reconciliation. |
| “Một benchmark config thắng mọi workload.” | Tối ưu có phụ thuộc data/traffic/resource profile. |
| “Chọn cấu hình nhanh nhất rồi tìm SLA sau.” | Định nghĩa SLA/hard gates trước thí nghiệm. |
| “Rollback config là xong rollback dữ liệu.” | Checkpoint/output schema/partition plan có thể không tương thích. |

## 26. Checklist trước khi chấp nhận một thay đổi cấu hình

- [ ] Có hypothesis và bottleneck evidence, không tuning theo cảm giác.
- [ ] Primary metric là committed useful work/time theo contract.
- [ ] End-to-end elapsed bao gồm startup, queue, validation/publish khi SLA yêu cầu.
- [ ] Workload matrix đại diện cho production và failure conditions.
- [ ] Source snapshot, source version và partition manifest bất biến.
- [ ] Data distribution, skew, payload sizes và hot-key ratios được ghi.
- [ ] A/B có same code/business logic và output semantics.
- [ ] Mỗi run dùng independent output namespace hoặc reset database đúng cách.
- [ ] Cache warm/cold, JVM JIT/GC và DB state policy rõ.
- [ ] Benchmark có repeated runs, paired/random order khi phù hợp.
- [ ] Variance/uncertainty được báo theo **run/round**, không pseudo-replication theo item.
- [ ] Không chọn fastest run hoặc bỏ outliers xấu sau khi nhìn dữ liệu.
- [ ] Concurrent online traffic/shared resource conditions được kiểm soát/ghi lại.
- [ ] Có p95/p99 chunk, job và critical-path partition theo đúng đơn vị.
- [ ] Hikari active/pending/acquire/hold time, DB lock waits, JobRepository latency được đo.
- [ ] CPU/GC/memory, broker/API inflight/rate/429/503 có metrics.
- [ ] Config thực applied = reported C/K/P/grid/pool/pods, không chỉ config file.
- [ ] Tổng pool sizes dưới cluster DB budget kể cả rolling surge.
- [ ] Retry/skip/rollback counts không bị che bởi throughput trung bình.
- [ ] Java reader/writer, partitioner và StepExecution restart semantics đã được test.
- [ ] Có fault injection hard-kill worker, lost reply và metadata outage khi phù hợp.
- [ ] Business oracle missing/extra/mismatch và external idempotency đều PASS.
- [ ] Không tắt checkpoint hoặc bỏ consistency guard để thắng benchmark.
- [ ] Các profile chưa dùng tune cũng đã validation.
- [ ] Production canary có guardrails, owner và rollback criteria.
- [ ] Rollback không làm drift partition context/identifying JobParameters.
- [ ] Có performance decision record và evidence đủ tái lập.
- [ ] Nếu evidence thiếu, decision là **INCONCLUSIVE**, không rollout mù.

## 27. Câu hỏi tự kiểm tra

1. Vì sao một benchmark duy nhất không đủ để tăng thread count trong Spring Batch?
2. Những yếu tố nào làm lần chạy thứ hai tự nhiên nhanh hơn dù code không đổi?
3. Committed unique items/s khác `readCount` và read attempts/s thế nào?
4. Khi `skipCount` tăng, vì sao JobExecution `COMPLETED` chưa chắc đạt business contract?
5. Median chunk latency và p95 JobExecution duration có phải cùng đơn vị quan sát không?
6. Tại sao không bootstrap item latencies của một job như các independent jobs?
7. Một paired experiment phải bảo đảm điều gì?
8. Khi nào nên chạy cache cold benchmark thay vì chỉ warm steady-state?
9. Vì sao một candidate chỉ tốt trên data keys uniform có thể thất bại ở hot-key workload?
10. Speedup và parallel efficiency được tính từ throughput ra sao?
11. Nếu phần serial của job là 10%, Amdahl giới hạn speedup ở 16 workers bao nhiêu?
12. Nếu API cho 12 inflight và mean latency 0,4s, trần lý tưởng requests/s là bao nhiêu?
13. Nếu upstream=300 items/s còn downstream=120 items/s, backlog tăng bao nhiêu trong 10 phút?
14. `gridSize`, `chunkSize`, `ThreadPoolTaskExecutor.maxPoolSize` và Hikari max pool khác nhau thế nào?
15. Tại sao Hikari pending cao và DB lock waits cao không tự chứng minh cần tăng pool?
16. Vì sao tăng `chunkSize` có thể giảm clean elapsed nhưng tăng recovery tail?
17. Nếu một benchmark bỏ checkpoint, tại sao so với baseline có restart là không công bằng?
18. Vì sao `ON CONFLICT DO NOTHING` có thể khiến lần benchmark sau nhanh giả?
19. Khi đổi số partitions P, phải giữ yếu tố nào invariant để so sánh?
20. Tại sao không thay partition plan của JobInstance đã FAILED để benchmark tuning mới?
21. Tại sao remote architecture dùng 32 vCPU không thể chỉ so elapsed với local 4 vCPU?
22. Những điểm nào khác nhau khi test restart multi-threaded step và remote chunking?
23. Business commit nhưng metadata checkpoint cũ dẫn đến lỗi nào khi restart?
24. Checkpoint tiến mà business chưa commit thì idempotent writer có tự sửa missing không?
25. Khi worker bị hard kill sau commit trước ACK, test cần assert gì?
26. Vì sao p99 JobExecution cần nhiều independent job runs hơn p99 của chunks?
27. Điều kiện nào khiến một khác biệt 2% có ý nghĩa thống kê nhưng không đáng triển khai?
28. Cần có những hard gates nào trước khi xếp candidate vào Pareto comparison?
29. Khi nào kết luận `INCONCLUSIVE` hợp lý hơn chọn candidate mới?
30. Trước canary rollback, tại sao phải xem checkpoint format/partition manifest thay vì chỉ restore env vars?

**Gợi ý trả lời:** (1) Noise, workload skew, cache, resources, repeatability. (2) JIT, DB/OS buffer cache, pools, network warmup. (3) Đã commit đúng business key thay vì attempts. (4) Có thể skip required records. (5) Không; một cái đo chunks, một cái đo jobs. (6) Pseudo-replication và correlated failures. (7) Điều kiện môi trường/workload tương đồng theo cặp. (8) Khi SLA thật gồm startup/cold paths. (9) Hot row lock contention. (10) `S=R_C/R_1, E=S/C`. (11) Khoảng 6,40×. (12) 30 requests/s lý tưởng. (13) 108.000 items. (14) Partition hint, commit size, thread cap, JDBC connection cap. (15) SQL locks có thể là nguyên nhân chính. (16) Memory/lock duration/retry replay cost. (17) Khác consistency contract. (18) Lần sau không ghi rows mới; DB bỏ qua conflicts. (19) Snapshot, total keyset, payloads, resource context. (20) Checkpoint/ranges cũ không tương thích. (21) Resource cost khác. (22) Reader/checkpoint và broker reply ownership. (23) Replay/duplicate risk. (24) Không, cần reconciliation/repair. (25) Output đúng, idempotency/reply/metadata consistency. (26) Phân phối jobs khác chunks, đơn vị độc lập khác. (27) Chi phí/complexity/tail risk vượt lợi ích. (28) Data correctness, SLA, quotas, restart. (29) Sample/uncertainty/profile chưa đủ. (30) Để không resume trên state không tương thích.

## Tài liệu tham khảo

- [Spring Batch 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): multi-threaded steps, partitioning, remote processing, `gridSize` và `throttleLimit` deprecated.
- [Spring Batch 5.2 — Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing.html): commit interval và transaction.
- [Spring Batch 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): `ItemStream`, `ExecutionContext`, restart.
- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest` và Job/Step testing.
- [Spring Batch 5.2 — JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): metadata persistence, transaction isolation.
- [Spring Batch 5.2 — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html): built-in observability, Micrometer and observation context.
- [Spring Framework 6.2 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): core/max threads, queue capacity, rejection.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): `Timer`, sample và histogram/percentile reporting.
- [HikariCP — Configuration Knobs](https://github.com/brettwooldridge/HikariCP): `maximumPoolSize`, acquire timeout và pool sizing.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): pool size không càng lớn càng tốt.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): query plan và `BUFFERS`.
- [PostgreSQL — Runtime Configuration / Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html): DB memory và resource budget.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory requests/limits, throttling.
- [Gil Tene — Coordinated Omission](https://www.youtube.com/watch?v=lJ8ydIuPFeU): đo latency không che overload do load generator tự giảm tốc; áp dụng có điều kiện với batch workloads.

**Điểm cốt lõi:** **Một benchmark chỉ là một quan sát trong một điều kiện; nó không phải bằng chứng cấu hình tốt nhất cho production.** Hãy dùng **immutable snapshots, workload matrix, repeated paired runs, cùng business output contract và metrics đa tầng** để hiểu speedup, variance, p95/p99 và bottlenecks. Trong Spring Batch, mọi lựa chọn `chunkSize`, `TaskExecutor`, `gridSize`, Hikari pool, local/remote scaling phải vượt **hard gates về output correctness, transaction/restart, quotas và SLA**, kể cả khi worker crash hoặc downstream bị quá tải. Chọn cấu hình theo tradeoff có thể kiểm toán và canary/rollback, không theo một con số elapsed đẹp nhất.
