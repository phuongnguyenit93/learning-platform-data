# Throughput ổn định theo thời gian khi mở rộng Spring Batch

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt **throughput tức thời**, **throughput trung bình**, **sustained throughput** và **goodput** thực sự có ích cho nghiệp vụ.
- Giải thích vì sao một job có thông lượng trung bình cao vẫn có thể không đạt yêu cầu khi xuất hiện những khoảng tụt tốc độ, backlog tăng hoặc retry storm.
- Đo throughput theo các cửa sổ thời gian, xác định pha **warm-up, steady state, degradation và recovery**, chọn ngưỡng ổn định có thể kiểm chứng.
- Đọc kết hợp throughput, latency, backlog, retry/rollback, CPU, GC, pool kết nối, I/O, lock và chỉ số của `JobRepository` để tìm nút thắt.
- Phân tích hiệu ứng tăng worker trong multi-threaded step, parallel steps, local/remote partitioning và remote chunking; nhận ra bottleneck chuyển từ CPU sang DB/broker.
- Thiết kế counter và metric bằng **Java 17, Micrometer, Spring Batch 5.x**, phân biệt telemetry gần đúng với dữ liệu audit bền vững.
- Xây dựng thử nghiệm tải dài hạn, thử ngắt worker/restart, tính capacity và chọn giới hạn đồng thời dựa trên bằng chứng.
- Thiết lập SLO throughput, kiểm soát backpressure, retry/idempotency và bảo đảm chất lượng dữ liệu trong khi mở rộng.

## 1. Vấn đề: nhanh lúc đầu chưa chắc nhanh đến cuối

Module **SPRING_BATCH_SCALING_OPERATIONS** tập trung vào mở rộng Spring Batch để xử lý workload lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán; đồng thời phải đo nút thắt, bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực tế.

Giả sử một job cần nhập **2,4 triệu giao dịch trong 40 phút**. Khi chạy 8 worker, dashboard cho thấy tốc độ chạm **2.500 item/s** trong hai phút đầu. Nhưng 20 phút sau tốc độ chỉ còn **600 item/s**, rồi tăng lại sau khi DB được giải phóng.

Có thể nhóm phát triển báo “peak throughput = 2.500 item/s”, trong khi đối tác nghiệp vụ hỏi: “Job có hoàn thành trong 40 phút, mọi lần chạy, mà không bỏ sót hay xử lý trùng giao dịch không?”

Đây là hai câu hỏi hoàn toàn khác nhau.

~~~mermaid
flowchart LR
    IN["Snapshot / nguồn đầu vào"] --> RD["Readers"]
    RD --> PR["Processors"]
    PR --> WR["Writers"]
    WR --> OUT["Business output commit"]
    OUT --> REC["Reconciliation / publish"]
    RD -. "Thời gian đọc, queue" .-> M["Metrics"]
    PR -. "CPU, GC, retry" .-> M
    WR -. "DB pool, locks, commit" .-> M
    OUT -. "Unique committed items" .-> M
~~~

**Ý chính:** throughput ổn định là khả năng duy trì một **tốc độ kết quả nghiệp vụ hữu ích** trong khoảng thời gian đủ dài, dưới workload và giới hạn tài nguyên thực tế, không chỉ đạt một peak ngắn khi cache nóng hoặc queue còn ít.

## 2. Định nghĩa phép đo: throughput không đồng nghĩa goodput

Các số đo cần định nghĩa thật rõ **đơn vị, phạm vi và nguồn sự thật**.

| Chỉ số | Ý nghĩa | Sai lầm dễ gặp |
| --- | --- | --- |
| `read items/s` | Reader phát ra bao nhiêu item mỗi giây | Đếm item đọc lại sau rollback như kết quả mới |
| `processed items/s` | Processor được gọi bao nhiêu lần | Retry/skip có thể làm tăng số lần xử lý |
| `write attempts/s` | Item được đưa vào writer bao nhiêu lần | Write được gọi không chứng minh DB đã commit |
| **Committed business items/s** | Số business item hợp lệ được commit và đủ điều kiện tính một lần | Cần tiêu chí dedup/commit rõ ràng |
| **End-to-end goodput/s** | Số item hữu ích đã qua các gate bắt buộc, gồm side effect theo business contract | Chỉ nhìn bảng đích, bỏ qua outbox/email/ledger |
| `chunks/s` | Số chunk được commit/attempt theo định nghĩa metric | Chunk size khác nhau nên không so trực tiếp với item/s |
| `bytes/s` | Lưu lượng dữ liệu qua network hoặc broker | Payload lớn không chắc làm tăng business throughput |
| `job throughput` | Total eligible business items / thời gian toàn job | Trung bình che giấu tụt tốc độ giữa chừng |

Với một cửa sổ `[t0,t1)`, định nghĩa:

~~~text
goodput(t0,t1) =
  số business item được xác nhận commit hợp lệ trong cửa sổ
  / (t1 - t0), tính bằng giây

read_rate(t0,t1) =
  số lần đọc thành công / (t1 - t0)

retry_amplification =
  tổng số lần xử lý thử / số unique business item hoàn tất
~~~

Ví dụ 1.200 item được writer thử trong 1 giây, trong đó 200 là replay/duplicate và chỉ có 900 unique item mới được commit. `write attempts/s=1.200` nhưng **goodput=900 item/s**; 100 item còn lại có thể bị skip, fail hoặc chưa commit.

### Phân biệt snapshot với cùng một item qua nhiều JobInstance

Một business key có thể được reprocess trên snapshot mới vì nghiệp vụ muốn tính lại, không nhất thiết là “duplicate sai”. Vì thế counter “unique” cần định nghĩa theo **operation identity** như `(snapshotId, businessId)` hoặc `(businessWindow, logicalOperationId)` và quy tắc reprocess rõ. Không áp dụng `COUNT(DISTINCT id)` toàn hệ thống khi snapshot khác nhau hợp lệ được xử lý lặp có chủ đích.

### Throughput và latency là hai trục khác nhau

**Throughput** đo số item hoàn tất mỗi giây; **latency** đo thời gian từ lúc item/công việc đi vào phạm vi tới khi hoàn tất. Một hệ có thể tăng throughput nhờ nhiều worker trong khi latency tăng vì backlog và contention. Cần theo dõi cả hai, đặc biệt với remote chunking và middleware.

## 3. Vì sao số trung bình toàn job có thể đánh lừa?

Giả sử job xử lý được 900.000 item trong 15 phút:

~~~text
Whole-job average = 900.000 / (15 * 60)
                  = 1.000 item/s
~~~

Nhưng diễn biến thực tế:

| Khoảng 5 phút | Unique item đã commit | Goodput trung bình trong khoảng |
| --- | ---: | ---: |
| 00:00–05:00 | 420.000 | 1.400 item/s |
| 05:00–10:00 | 360.000 | 1.200 item/s |
| 10:00–15:00 | 120.000 | 400 item/s |
| **Toàn job** | **900.000** | **1.000 item/s** |

Nhìn số trung bình toàn job, tốc độ “đạt 1.000”. Nhưng worker bị giảm còn **400 item/s** trong một phần ba thời gian; nếu suy giảm tiếp, SLA của các run dài hơn có thể thất bại.

### Tính ổn định phải được quan sát theo thời gian

Các thuộc tính cần đo:

1. **Mức thông lượng:** trung bình/median trên các cửa sổ `goodput_i`.
2. **Độ biến động:** biên độ, độ lệch chuẩn/CV hoặc p5/p95 **của các cửa sổ throughput**, không nhầm với p95 item latency.
3. **Xu hướng:** throughput có trượt giảm liên tục trong một giờ không?
4. **Tỷ lệ đạt sàn:** bao nhiêu cửa sổ liên tiếp hoặc bao nhiêu phần trăm cửa sổ có `goodput_i >= ngưỡng`?
5. **Recovery:** sau outage, mất bao lâu để throughput trở lại vùng yêu cầu?
6. **Chất lượng:** tỷ lệ retry, duplicate attempts, failed/skipped business items có tăng không?

Không có một ngưỡng CV, peak-to-mean hoặc thời lượng cửa sổ đúng cho mọi hệ. Chọn ngưỡng theo mức biến động của workload, SLA và sai số phép đo.

## 4. Chọn cửa sổ đo và thước đo ổn định

### 4.1. Cửa sổ thời gian

- **10–30 giây:** phát hiện spike, GC pause và retry storm nhanh; dễ nhiễu khi chunk commit theo đợt.
- **1 phút:** phù hợp bảng điều khiển vận hành, quan sát trend vừa phải.
- **5 phút:** làm mượt nhiễu ngắn, nhận diện sustained throughput và capacity.
- **15–30 phút:** kiểm tra xu hướng chậm, resource leak hoặc suy giảm do dữ liệu phân bố khác nhau.
- **Toàn job:** cần để đánh giá SLA end-to-end, nhưng **không thay** các cửa sổ bên trong.

Dùng cửa sổ không chồng lấn khi tính tỷ lệ đạt SLA trên một tập khoảng cố định; dùng rolling window để hiển thị trend/alert. Hai kiểu cửa sổ có thể cho các thống kê phụ thuộc nhau, nên không kết luận “80% khoảng độc lập” nếu rolling windows chồng lấn mạnh.

### 4.2. Average, median, p5 và hệ số biến thiên

Với `n` cửa sổ bằng nhau, tốc độ `x1...xn`:

~~~text
mean = (x1 + ... + xn) / n

stddev = sqrt( sum((xi - mean)^2) / n )

CV = stddev / mean, nếu mean > 0

p5(window goodput) = percentile thấp của các xi
p95(window goodput) = percentile cao của các xi
~~~

**CV thấp** cho thấy tương đối ít dao động so với mức trung bình, nhưng **CV thấp không đủ**: một job luôn ở `300 item/s` khi SLA yêu cầu `900 item/s` có CV gần 0 nhưng không đạt mục tiêu.

**p5 throughput thấp** phơi bày các khoảng tụt tốc độ, còn p95 item latency cao báo dấu hiệu trễ trên item. Đây là hai phân phối khác nhau.

### 4.3. SLO minh họa, không phải thông số mặc định của Spring Batch

Giả sử workload đầu vào ổn định, giai đoạn steady state được định nghĩa rõ, yêu cầu:

- Trong ít nhất **95% cửa sổ 5 phút**, goodput đạt **≥900 unique business item/s**.
- Không có **3 cửa sổ liên tiếp** thấp hơn `800 item/s` khi input và capacity theo contract vẫn sẵn sàng.
- Toàn `JobInstance` hoàn thành và reconciliation đạt trong **≤40 phút**.
- Retry amplification không vượt ngưỡng đã được thống nhất, không có missing/duplicate business effect không được phép.

Các ngưỡng `900`, `800`, `95%` chỉ là **ví dụ thiết kế SLO**. Việc phân loại giai đoạn `warm-up`, `input starvation`, downtime có được tính vào SLO hay không phải công bố trước, không loại bỏ những phút xấu sau khi xem kết quả.

### 4.4. Pha warm-up và cooldown

Một job bắt đầu phải mở kết nối, xây cursor, nạp cache, khởi tạo pool, tạo partition/worker. Giai đoạn cuối có thể giảm throughput vì dữ liệu còn lại ít hơn số worker. Khi phân tích steady-state throughput, hãy báo cáo riêng:

~~~text
T_total = T_prepare + T_warmup + T_steady + T_drain + T_reconcile

SLA toàn job bao gồm cả T_prepare / T_drain / T_reconcile
Steady-state stability chỉ tính phần được định nghĩa trước
~~~

Không được “loại warm-up, cooldown” rồi dùng steady rate để khẳng định job đã đạt SLA end-to-end.

## 5. Throughput, tốc độ vào và backlog: một hệ không thể ổn định khi bị ngập việc

Nếu job xử lý luồng liên tục hoặc middleware có queue, throughput phải được so với **arrival rate**.

Gọi:

- `λ`: tốc độ công việc đến hàng đợi, business item/s.
- `μ`: tốc độ xử lý hữu ích bền vững, business item/s.
- `B(t)`: backlog item đợi hoặc chưa hoàn tất.

Trong mô hình đơn giản không loại bỏ/dedup/burst và không có nhiều nguồn/sink:

~~~text
dB/dt ≈ λ - μ, khi B > 0

Nếu λ > μ kéo dài: backlog tăng.
Nếu λ < μ và có backlog: backlog có khả năng giảm.
Nếu λ ≈ μ: có thể giữ backlog nhưng rất nhạy với dao động.
~~~

Ví dụ hàng đợi có `60.000 item` chờ, arrival tiếp tục `1.000 item/s`, các worker commit mới `1.100 item/s` ổn định:

~~~text
Net drain rate = 1.100 - 1.000 = 100 item/s

Thời gian giảm 60.000 backlog về 0 lý tưởng:
60.000 / 100 = 600 giây = 10 phút
~~~

Nếu `μ` giảm còn 950 item/s, backlog **tăng** 50 item/s thay vì được giải phóng. Đừng chỉ nhìn “workers busy 100%” rồi kết luận hệ đang phục vụ tốt.

### Little's Law áp dụng khi nào?

Trong hệ gần steady state, có chính sách đo nhất quán và điều kiện lưu lượng phù hợp:

~~~text
L = λ * W
~~~

`L` là số item trung bình đang ở trong hệ; `λ` là throughput/arrival hiệu dụng của hệ ổn định; `W` là thời gian trung bình item nằm trong hệ. Công thức giúp kiểm tra tương quan giữa in-flight, queue depth và latency, **không được áp dụng máy móc** lúc backlog tăng liên tục, có job hữu hạn đang cạn input hay khi retry làm counts bị đếm trùng.

### Batch có input hữu hạn

Với job đọc một snapshot hữu hạn, khi còn ít item hơn số worker, tốc độ tự giảm ở cuối job. Đó không nhất thiết là suy thoái. Phân biệt **source exhaustion / partition straggler** với CPU/DB bottleneck bằng counter còn lại, in-flight và expected count theo partition.

## 6. Tính capacity theo SLA, không theo đỉnh ngắn hạn

Giả sử cần commit **2.400.000 item** trong **40 phút**, bao gồm chuẩn bị, xử lý, retry và đối soát.

~~~text
Tổng ngân sách = 40 * 60 = 2.400 giây

Throughput tối thiểu theo trung bình toàn hành trình:
2.400.000 / 2.400 = 1.000 business item/s
~~~

Nếu `prepare + reconciliation` mất **5 phút**, chỉ còn **35 phút** cho processing:

~~~text
Processing budget = 35 * 60 = 2.100 giây
Required sustained processing goodput:
2.400.000 / 2.100 ≈ 1.143 item/s
~~~

Nếu muốn thêm **20% headroom minh họa** để chịu retry/skew/bursts, mục tiêu capacity có thể khoảng:

~~~text
1.143 * 1,20 ≈ 1.372 unique business item/s
~~~

Headroom 20% không phải quy định chung. Nó phải phản ánh phân phối throughput thực đo, input size variance, DB limit và SLA confidence. Nếu số record thuộc workload không đủ phân công đều, đạt peak 1.500 item/s trên một partition không chứng minh toàn job có capacity 1.372 item/s.

### Critical path không chỉ có processor

~~~text
T_end_to_end =
  T_capture_snapshot
  + T_partition_dispatch
  + T_processing
  + T_retry_and_recovery
  + T_reconciliation
  + T_publish
~~~

Một worker step tăng từ 800 lên 1.600 item/s chưa chắc rút thời gian job tương ứng nếu capture, writer DB hoặc final reconciliation đang chiếm phần lớn critical path.

## 7. Cách nhận diện throughput không ổn định trên time series

Giả sử ta đo được `goodput` theo cửa sổ 5 phút trong 30 phút steady-state.

| Cửa sổ | Goodput item/s | Retry attempts/item | p95 chunk latency |
| --- | ---: | ---: | ---: |
| 00–05 phút | 980 | 1,01 | 0,20 s |
| 05–10 phút | 1.010 | 1,01 | 0,19 s |
| 10–15 phút | 995 | 1,02 | 0,21 s |
| 15–20 phút | 620 | 1,35 | 1,10 s |
| 20–25 phút | 590 | 1,42 | 1,45 s |
| 25–30 phút | 975 | 1,05 | 0,24 s |

Giá trị là **dữ liệu mô phỏng**, chưa phải thống kê trên một môi trường cụ thể. Mẫu hình cho thấy throughput tụt mạnh cùng lúc retry tăng và tail chunk latency tăng. Những giả thuyết cần đo thêm:

- DB connection pool đầy khiến nhiều worker đợi connection.
- Database lock/deadlock gây rollback/retry.
- Broker redelivery và worker xử lý lại cùng item.
- CPU hoặc GC pause kéo dài khiến commit bị trễ.
- Input partition bị skew; các worker nhanh hết việc và chỉ một straggler còn chạy.
- Sự cố mạng hoặc storage làm tăng latency.

Không thể suy nguyên nhân chỉ từ ba cột. Cần ghép các nguồn metric theo cùng time axis, xem CPU, DB locks, connection pending, memory/GC và queue depth trước khi quyết định tăng worker.

### Sử dụng chart để nhìn trend

~~~text
Goodput (item/s):
1100 |                      .          .
1000 |    .     .     .     :          .
 900 |                      :          :
 800 |                      :          :
 700 |                      .          :
 600 |                    *     *      :
 500 +-------------------------------------
         0-5  5-10 10-15 15-20 20-25 25-30

* là hai cửa sổ suy giảm cần điều tra
~~~

Một đường biến thiên không có thông tin về queue và input còn lại dễ gây hiểu nhầm. Nếu source hết bản ghi ở hai cửa sổ cuối, `goodput` thấp không nên được phân loại là “suy giảm capacity” theo cùng cách với một backlog đang tăng.

## 8. Pha hoạt động: chuẩn bị, steady state, saturation và recovery

Không nhất thiết một job duy trì cùng throughput từ đầu đến cuối. Nên chia giai đoạn theo **trạng thái hệ thống**, không chỉ theo phút:

| Pha | Dấu hiệu | Cách đánh giá |
| --- | --- | --- |
| Prepare | Tạo snapshot, JobRepository metadata, partition manifest | Thời gian chuẩn bị và độ tin cậy |
| Warm-up | Khởi tạo bean, mở cursor/connection, cache, JVM warm-up | Time-to-steady, không che khỏi SLA |
| Steady state | Có đủ input, workers có khả năng chạy bền vững | SLO windowed goodput, latency, resource |
| Saturation | CPU/DB/broker đạt giới hạn; pending/latency tăng | Tìm bottleneck, không chỉ tăng worker |
| Failure/recovery | Node, DB, broker lỗi; retry hoặc failover | Tốc độ phục hồi, goodput sau recovery |
| Drain/straggler | Input gần hết hoặc chỉ còn partition chậm | Remaining work, skew, không đo capacity bằng peak |
| Reconciliation/publish | Đối soát và công bố | Correctness, SLA end-to-end |

Nếu cần benchmark **steady-state capacity**, tạo workload đủ dài để nguồn luôn có data, sau đó báo riêng kết quả chạy job hữu hạn thực tế.

## 9. Instrumentation: đo đúng thứ có thể tin tưởng

Spring Batch cung cấp `JobExecution`/`StepExecution` với `readCount`, `writeCount`, `commitCount`, `rollbackCount` và các thông tin khác; Micrometer có thể thu thập metric của framework tùy phiên bản/cấu hình.

Tuy nhiên cần hiểu:

- `readCount` tăng khi framework đọc item, **không phải** unique result committed.
- `writeCount` có semantics của writer/step; với `UPSERT`, một item được đưa tới writer nhưng có thể không thêm hàng mới.
- `commitCount` đếm transaction commits, không cùng đơn vị với business items.
- `rollbackCount` và retry tăng làm attempt throughput cao nhưng goodput thấp.
- `StepExecution` hoàn thành không tự chứng minh output đầy đủ nếu partitioning/reader logic sai.
- Một metric time-series có thể mất mẫu khi process crash; nếu số liệu phải phục vụ kiểm toán, cần **nguồn bền vững**.

### Bộ metric tối thiểu

| Metric | Nhóm | Mục đích |
| --- | --- | --- |
| `business_items_committed_total` | Counter | Goodput từ hiệu ứng mới đã commit |
| `business_items_attempted_total` | Counter | So tỷ lệ attempt/replay |
| `chunk_commit_duration_seconds` | Histogram/timer | p50/p95/p99 latency chunk |
| `chunk_rollback_total` | Counter | Retry/rollback pressure |
| `worker_active` | Gauge | Số worker thật đang xử lý |
| `worker_queue_depth` | Gauge | Công việc chưa được phục vụ |
| `snapshot_remaining_business_items` | Gauge/derived | Phân biệt job đang cạn input |
| `jdbc_connections_active/pending` | Gauge | Pool saturation |
| `db_lock_wait_seconds` | Timer/histogram | Contention phía đích |
| `jvm_gc_pause_seconds` | Histogram/timer | GC ảnh hưởng chunk latency |
| `jobrepository_write_duration_seconds` | Timer | Metadata trở thành nút thắt |
| `reconciled_missing_keys_total` | Counter/gauge | Ngăn tính nhanh bằng cách bỏ sót |

**Tất cả tên ở bảng là gợi ý**, không bảo đảm Spring Batch/Micrometer cung cấp sẵn đúng metric hay nhãn. Cần chuẩn hóa schema monitoring theo hệ thống thực tế.

### Tránh nhãn cardinality cao

Không đặt `orderId`, `customerId`, `chunkId` hay message ID riêng từng item thành label Prometheus. Dùng các dimension nhỏ và ổn định: `jobType`, `stepType`, `environment`, `workerRole`, `resultStatus`; các ID dùng cho điều tra nên ở log/tracing được phân quyền.

## 10. Java 17 + Micrometer: counter sau commit, không đếm attempt trước commit

Ví dụ dùng PostgreSQL với unique key `(snapshot_id, order_id)`, mỗi lần insert thành công tạo **một business row mới**.

~~~sql
CREATE TABLE imported_order (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);
~~~

Tình huống worker crash sau commit nhưng trước reply có thể khiến Spring Batch replay. `ON CONFLICT DO NOTHING` bảo đảm replay cùng business key **không thêm hàng mới**, và phép đo dùng số insert thành công thay vì số lần gọi writer.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

record OrderRow(String snapshotId, long orderId, String payload) {}

@Configuration
class ThroughputWriterConfiguration {

    @Bean("measuredOrderWriter")
    ItemWriter<OrderRow> measuredOrderWriter(
            JdbcTemplate jdbc, MeterRegistry registry) {

        Counter committed = Counter.builder(
                "batch.business.items.committed")
                .description("New unique business rows committed")
                .tag("jobType", "import-orders")
                .register(registry);

        return chunk -> {
            if (!TransactionSynchronizationManager
                    .isActualTransactionActive()
                    || !TransactionSynchronizationManager
                    .isSynchronizationActive()) {
                throw new IllegalStateException(
                        "A transactional chunk is required");
            }

            long newlyInserted = 0L;
            for (OrderRow item : chunk) {
                int rows = jdbc.update("""
                    INSERT INTO imported_order(
                        snapshot_id, order_id, payload
                    ) VALUES (?, ?, ?)
                    ON CONFLICT (snapshot_id, order_id) DO NOTHING
                    """,
                    item.snapshotId(), item.orderId(), item.payload());
                newlyInserted += rows; // Thông thường rows = 0 hoặc 1.
            }

            long countForThisCommit = newlyInserted;

            TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        if (countForThisCommit > 0L) {
                            committed.increment(countForThisCommit);
                        }
                    }
                });
        };
    }
}
~~~

**Ý nghĩa chính xác của ví dụ:**

- Nếu cùng chunk bị rollback, callback `afterCommit` **không được gọi**, nên không tăng counter vì transaction đó.
- Với cùng business key đã tồn tại, `ON CONFLICT DO NOTHING` không thêm row mới, counter không đếm lại.
- Counter được nâng sau transaction commit của **transaction manager bao quanh writer**. Cần cấu hình writer `JdbcTemplate` dùng cùng datasource/transaction context như chunk.
- Ví dụ dùng một `jdbc.update`/item để minh họa rõ semantics; production có thể dùng batching/SQL set-based nhưng phải kiểm chứng số row được insert thật.
- `afterCommit` chạy trong JVM: nếu process chết **ngay sau DB commit nhưng trước callback/metrics scrape**, counter có thể không phản ánh sự kiện đó. **Đây là telemetry gần đúng, không phải audit ledger bảo đảm exactly-once**.
- Counter không bao gồm record đã có từ lần chạy trước hoặc hợp lệ được reprocess có chủ đích; định nghĩa “new unique business row” phải khớp business SLO.
- Nếu writer phát sinh side effect ngoài DB (HTTP, email, broker), counter này **không** đo toàn bộ end-to-end business goodput.

Đối với kết quả cần đối soát chính xác, duy trì output/audit bền vững và truy vấn theo `(snapshotId, businessKey)` hoặc hệ thống CDC/audit với semantics commit phù hợp. Timestamp ghi trước commit không mặc định là **thời điểm commit chính xác**.

### Một lỗi instrumentation thường gặp

~~~java
// KHÔNG dùng làm counter "committed":
// writer.write(chunk);
// committed.increment(chunk.size());
// Nếu transaction rollback sau đó, metric đã đếm sai.
~~~

`ItemWriteListener.afterWrite` cũng không mặc nhiên là after-commit callback; đừng dùng listener đó để kết luận transaction đã commit nếu chưa đối chiếu lifecycle.

## 11. Prometheus/PromQL: cửa sổ và tỷ lệ

Giả sử counter Micrometer ở mục 10 được export dưới tên `batch_business_items_committed_total`. **Tên thực tế phụ thuộc registry và cấu hình naming convention**, phải xem endpoint metrics thật trước khi sao chép query.

### Goodput trong cửa sổ 5 phút

~~~promql
sum(rate(batch_business_items_committed_total[5m]))
~~~

### Số item tăng trong 5 phút

~~~promql
sum(increase(batch_business_items_committed_total[5m]))
~~~

`rate` và `increase` cho counter có xử lý việc reset counter khi process restart ở mức semantics của Prometheus; điều đó **không sửa** các sự kiện DB commit nhưng telemetry chưa kịp ghi hoặc export.

### Quan sát backlog song song

~~~promql
sum(batch_worker_queue_depth)
~~~

Metric queue depth ở đây là **giả định có instrumentation**. Trong broker, cần phân biệt ready/unacked/retry/DLQ với tổng business item độc lập; một message chứa nhiều item và có thể được replay.

### Kiểm tra p95 chunk latency

Nếu timer có histogram bucket và được export đúng tên:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(batch_chunk_commit_duration_seconds_bucket[5m])
  )
)
~~~

Timer/histogram phải được **cấu hình publish buckets** trước; nếu không tồn tại chuỗi `_bucket`, query trên sẽ không có kết quả hợp lệ. Không nhầm “p95 chunk duration” với percentile của item latency hay với p5 goodput.

### Đọc đồ thị cho đúng

- Một counter reset khi pod restart không nhất thiết là throughput âm.
- Nếu metric chỉ xuất hiện trên pod đang sống, mất pod có thể làm series biến mất và biểu đồ nhìn giả thấp hoặc giả cao tùy phép aggregate.
- `sum(rate(...[5m]))` phù hợp đo theo process exporters, nhưng không thay thế số business record bền vững khi cần quyết toán.
- Cần đặt rate, latency và backlog trên **cùng trục thời gian** để phân biệt nguyên nhân và hệ quả.

## 12. Tính tốc độ theo time-window và xử lý counter reset

Một metric counter hữu ích vì có tính tăng dần. Tuy nhiên khi node restart, counter trong JVM có thể quay về 0. Việc lấy “counter mới trừ counter cũ” mà không xử lý reset sẽ tạo throughput âm và làm biểu đồ sai.

Đoạn Java 17 dưới đây minh họa phép tính **trên hai mẫu thuộc cùng một chuỗi counter chưa reset**:

~~~java
import java.time.Duration;
import java.time.Instant;

record CounterSample(Instant at, long totalCommitted) {}

public final class WindowGoodput {

    public static double itemsPerSecond(
            CounterSample previous, CounterSample current) {

        if (previous == null || current == null
                || previous.at() == null || current.at() == null
                || !current.at().isAfter(previous.at())) {
            throw new IllegalArgumentException(
                    "Samples must be ordered by time");
        }

        long delta = current.totalCommitted()
                - previous.totalCommitted();

        if (delta < 0L) {
            // Một khả năng: counter đã reset khi pod restart.
            // Phải rebase theo instance/epoch, không trả tốc độ âm.
            throw new IllegalStateException(
                    "Counter reset or invalid sample pair");
        }

        double durationSeconds = Duration.between(
                previous.at(), current.at()).toNanos()
                / 1_000_000_000.0;

        return delta / durationSeconds;
    }
}
~~~

Test JUnit 5 đơn giản:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class WindowGoodputTest {

    @Test
    void calculatesCommittedRatePerSecond() {
        Instant t0 = Instant.parse("2026-11-25T00:00:00Z");

        double rate = WindowGoodput.itemsPerSecond(
                new CounterSample(t0, 1000L),
                new CounterSample(t0.plusSeconds(60), 4600L));

        assertEquals(60.0, rate, 0.000001);
    }

    @Test
    void refusesCounterResetInsteadOfShowingNegativeRate() {
        Instant t0 = Instant.parse("2026-11-25T00:00:00Z");

        assertThrows(IllegalStateException.class, () ->
                WindowGoodput.itemsPerSecond(
                        new CounterSample(t0, 5000L),
                        new CounterSample(t0.plusSeconds(60), 100L)));
    }
}
~~~

Các sample này là **telemetry**, không phải lịch sử commit chuẩn cho kiểm toán. Nếu hệ giám sát đã dùng Prometheus, ưu tiên hàm `rate`/`increase` có handling counter reset, xem xét labels của process, missing series và scrape gaps.

### Cần nhìn vào timestamp và nguồn dữ liệu

- Nếu lấy metric từ hai pod khác nhau nhưng giả định cùng một counter, delta sẽ vô nghĩa.
- Nếu sample tới trễ hoặc cùng timestamp, không tính rate bằng phép chia cho 0.
- Nếu nhiều cửa sổ có duration khác nhau, whole-period mean phải được tính từ **tổng delta / tổng thời gian**, không lấy trung bình không trọng số của những tốc độ không cùng độ dài.
- Nếu metric missing do worker down, cần biểu diễn outage theo policy; không tự bỏ cửa sổ xấu khi xét SLO toàn hệ.
- Nếu JobInstance kết thúc và không có input mới, throughput bằng 0 không tự là sự cố capacity; phân biệt end-of-work và worker starvation.

## 13. Dữ liệu từ JobRepository giúp chẩn đoán nhưng không đủ để tính goodput

`JobRepository` lưu `StepExecution`, `ExecutionContext` và state của từng step. Có thể dùng metadata để theo dõi tiến độ khi debug.

Ví dụ truy vấn chẩn đoán (tên cột minh họa theo schema JDBC Spring Batch 5.x phổ biến):

~~~sql
SELECT
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Đây không phải truy vấn tính unique committed item/s trực tiếp:

- `StepExecution` có thể được cập nhật theo chunk hoặc lifecycle, không phải liên tục từng item.
- Các counter mang semantics của Spring Batch và có thể có retry/skip/filter.
- Một JobInstance được restart có thể có **nhiều JobExecution**; cộng dữ liệu không điều kiện có thể đếm lại.
- Parallel/partitioned steps không nhất thiết có cùng size và business semantics.
- `WRITE_COUNT` có thể không bằng số row DB mới vì upsert, `DO NOTHING` hoặc processor filter.
- `STATUS='COMPLETED'` không thay thế source–target reconciliation.

Dùng metadata để phát hiện partition đang chậm hoặc không commit, sau đó nhìn metric DB/CPU/queue và kiểm tra business output trên snapshot cố định.

### Khi thực sự cần audit bền vững

Có thể lưu một bảng `processed_record` theo `(snapshotId,businessId)` cùng idempotency result, rồi kiểm tra số unique completed keys theo snapshot khi job kết thúc. Nếu cần **chuỗi thời gian commit chính xác**, cần thiết kế cơ chế ghi nhận sự kiện commit có semantics rõ (CDC, transactional outbox, DB audit). Một cột `created_at` được ghi trước khi transaction commit **không tự bằng commit timestamp**.

## 14. Phân tích nút thắt bằng các tín hiệu có liên quan

Throughput ổn định là một bài toán **công suất cả pipeline**. Không nên thay đổi concurrency chỉ vì biểu đồ rate giảm.

| Nút thắt | Dấu hiệu đồng thời | Hướng điều tra |
| --- | --- | --- |
| **CPU-bound processor** | CPU worker cao, DB/queue còn dư, chunk process latency tăng | Algorithm, vectorization/batch, CPU quota, worker slots |
| **GC/heap pressure** | Heap tăng, GC pause và p95 chunk latency tăng sau thời gian dài | Allocation rate, leak, chunk size, streaming vs materialization |
| **JDBC pool cạn** | Pending/acquire wait tăng, CPU có thể không cao | Tổng connections của mọi JVM, pool size, cursor usage |
| **DB writer/locks** | Commit p95 tăng, lock wait/deadlock tăng, retry storm | Index, write contention, transaction scope, idempotency |
| **DB source read I/O** | Cursor fetch chậm, disk IOPS/IO wait cao | Index/range scan, partition skew, snapshot locality |
| **JobRepository hot spot** | Metadata write latency tăng khi partition/chunk quá nhỏ | Giảm metadata churn, số partition, commit frequency |
| **Broker/middleware** | Ready/unacked/retry backlog tăng, publish-confirm/reply latency cao | Consumer capacity, message size, prefetch, DLQ |
| **External API throttle** | HTTP 429/503, timeout, retry/backoff tăng | Rate limiter, bounded concurrency, circuit breaker |
| **Partition skew** | Nhiều workers idle, một partition còn backlog lớn | Chia theo cost/record distribution cho run mới |
| **Input cạn** | Remaining work gần 0, queue trống, workers idle | Không vội coi throughput thấp là suy thoái |
| **Network/transmission** | RTT, retransmit, serialization/bytes cao | Payload reduction, placement, compression theo benchmark |

### Trình tự chẩn đoán

1. Xác nhận **định nghĩa metric** không đổi giữa các release và counter không bị reset làm sai graph.
2. Kiểm tra snapshot **còn item cần xử lý** hay không.
3. So goodput cùng **arrival rate/backlog** và số worker thực sự đang active.
4. Xác định **thành phần có saturation + queue/latency tăng**.
5. So sánh thời điểm xuất hiện triệu chứng với thay đổi cấu hình, data distribution, retry hoặc GC.
6. Thử một biến duy nhất ở staging (ví dụ pool limit, chunk size hoặc số worker), giữ workload và snapshot đủ tương đương.
7. Đối soát kết quả để chắc rằng throughput tăng không đến từ skip/duplicate.

Một counter throughput tụt cùng CPU thấp và JDBC pending cao gợi ý “đợi DB”, không phải thiếu CPU. Tăng threads lúc này thường **không giải quyết** bottleneck.

## 15. Tác động của các mô hình scaling lên độ ổn định

| Mô hình | Lợi ích throughput | Rủi ro ổn định theo thời gian |
| --- | --- | --- |
| **Multi-threaded step** | Tăng xử lý song song trong một Step | Reader/writer không thread-safe, shared `ExecutionContext`, pool/lock contention |
| **Parallel steps** | Chạy các bước độc lập cùng lúc | Các steps cạnh tranh DB, CPU, I/O hoặc dependency chưa sẵn sàng |
| **Local partitioning** | Mỗi `StepExecution` có range/state riêng, parallel trên một JVM | Một process JVM/heap chung, GC pause ảnh hưởng nhiều partitions |
| **Remote partitioning** | Nhiều JVM, worker tự đọc input; dễ tăng node theo partition | DB connection tổng, snapshot I/O, skew, failed nodes, JobRepository |
| **Remote chunking** | Manager đọc một nguồn, worker xử lý/ghi từ chunk requests | Broker backlog, serialization, request/reply latency, consumer redelivery |

### Multi-threaded step và thread safety

Nếu reader/processor/writer chia sẻ mutable state không được bảo vệ, biểu đồ throughput có thể “đẹp” nhưng dữ liệu bị bỏ sót hoặc trùng. Sử dụng component thread-safe hoặc thiết kế riêng; `@StepScope` **không biến** một reader được chia sẻ trong cùng `StepExecution` thành thread-safe.

Đánh giá throughput phải đi kèm **correctness**, đặc biệt khi `TaskExecutor` khiến chunk completion order không còn như xử lý tuần tự.

### Partitioning giúp cô lập state, nhưng không tự cân bằng tải

Một partition đọc 50% dữ liệu, các partition khác cùng nhau đọc 50%. Khi các worker khác hoàn tất, chỉ còn một partition chạy: throughput cluster giảm dù tất cả tài nguyên khác rảnh. Đây là **straggler/tail effect**, khác với suy giảm do DB lock.

Vì vậy ngoài tổng throughput cần đo `expectedCount`, `readCount`, duration và bytes/CPU mỗi partition. Không thay ranh giới partition trong khi restart cùng `JobInstance`; kế hoạch rebalancing cần ổn định cho job plan mới.

### Remote chunking và request/reply

Nếu manager đọc nhanh hơn consumer commit, message backlog tăng. Nếu broker retry nhiều, attempt throughput có thể cao nhưng goodput giảm. Cần so:

~~~text
manager input rate
broker publish/ack rate
worker unique business commit rate
broker ready + unacked + retry backlog
reply latency / timeout
~~~

Broker ACK không mặc nhiên bằng transaction commit ở business DB; protocol và transaction boundaries phải được kiểm chứng.

## 16. Skew của partition: throughput nhìn giảm vì việc phân bố không đều

Giả sử có 4 partition với số item:

~~~text
P0 = 100.000
P1 = 100.000
P2 = 100.000
P3 = 900.000
Tổng = 1.200.000 item
~~~

Bốn worker cùng xử lý `2.000 item/s` khi có đủ input và DB chưa đạt trần.

~~~text
P0/P1/P2 hoàn thành khoảng 50 giây.
P3 hoàn thành khoảng 450 giây.

Trong 50 giây đầu: tổng rate có thể ~8.000 item/s.
Trong 400 giây sau: chỉ P3 còn việc, rate ~2.000 item/s.
~~~

Nếu báo `peak=8.000 item/s` rồi kỳ vọng cả job duy trì số đó, kết luận sẽ sai. Đây là **tính chất phân công dữ liệu**, không nhất thiết là đột ngột giảm capacity của hạ tầng.

### Chia lại thế nào?

- Đo số record/byte/CPU cost theo partition, không chỉ lấy độ rộng ID.
- Chia theo quantile, time window, hashed buckets hoặc bảng manifest có expected cost.
- Số partition có thể nhiều hơn số worker slots để mỗi node nhận nhiều partition theo lịch; nhưng quá nhiều partition làm metadata/dispatch overhead tăng.
- Với nguồn immutable và job mới, lập kế hoạch partition ổn định trước khi chạy.
- Không tự tái chia range của **JobInstance đang restart**, vì checkpoint cũ không còn đúng miền.

Nếu input chứa few very large records với cost xử lý cao, cân bằng theo số record vẫn có thể lệch; cần đo **cost/byte/latency distribution**.

## 17. Chunk size, commit frequency và độ ổn định

Một chunk-oriented step có các chi phí:

~~~text
T_chunk ≈ T_read + T_process + T_write
        + T_transaction_commit + T_metadata_update
        + T_retry_or_rollback
~~~

Đây là decomposition gần đúng; các thành phần có thể overlap hoặc cùng nằm trong một transaction, không cần đo cộng chính xác bằng wall time trừ khi instrumentation phù hợp.

### Chunk nhỏ

- Commit/checkpoint thường xuyên.
- Mỗi lỗi rollback ít item hơn.
- Nhưng metadata và DB transaction overhead có thể lớn.
- Nếu chunk size quá nhỏ, throughput có thể dao động theo flush/commit latency.

### Chunk lớn

- Giảm số lần commit tương đối khi mỗi item nhẹ.
- Nhưng chunk giữ nhiều item trong heap; writer/transaction có thể rất dài.
- Khi lỗi, replay/rollback nhiều item hơn.
- Lock/connection bị giữ lâu, p95/p99 latency xấu có thể kéo toàn throughput xuống.

### Benchmark theo nhiều kích thước

| Chunk size | Thuận lợi dự kiến | Cần đo |
| --- | --- | --- |
| 100 | Checkpoint dày, rollback ít | Commits/s, metadata IO, rate |
| 500 | Cân bằng thử nghiệm | Goodput, p95 commit, heap |
| 2.000 | Ít transaction hơn | Heap, lock time, rollback exposure |
| 5.000 | Có thể tốt khi writer batch và item nhẹ | GC, timeout, stale connections, RTO |

Các giá trị chỉ là **điểm thử**, không phải cấu hình chuẩn. Đánh giá ở cùng snapshot, cùng worker count, cùng DB quota; kiểm tra cả chất lượng output và thời gian restart.

### Không nhầm chunk size với broker message size

Trong remote chunking, chunk size có thể ảnh hưởng kích thước request và serialization cost. Một chunk lớn chứa bản ghi phức tạp có thể làm broker backlog/latency tăng dù số chunk/s trông giảm “hợp lý”.

## 18. Backpressure và bounded concurrency: ổn định tốt hơn peak cao

Khi một tầng downstream không theo kịp upstream, cách an toàn thường là **giới hạn tốc độ/độ đồng thời** và điều chỉnh theo capacity thật, thay vì đẩy nhiều việc hơn vào queue.

~~~mermaid
flowchart LR
    S["Input / Manager"] --> Q["Bounded queue / broker"]
    Q --> W["Bounded worker slots"]
    W --> DB["DB writer: quota hữu hạn"]
    DB -. "Lock/latency/pool pending" .-> C["Capacity controller"]
    C -. "Giảm tốc độ dispatch" .-> S
    C -. "Giữ mức worker an toàn" .-> W
~~~

### Các biện pháp

1. **Bounded executor:** giới hạn số thread và queue capacity; xử lý chính sách bị từ chối thay vì tạo unbounded threads.
2. **JDBC connection budget:** tổng connection tối đa của mọi process (manager, worker, metadata, monitoring), không chỉ mỗi pod.
3. **Rate limiting** khi gọi API ngoài có quota và yêu cầu 429/backoff.
4. **Broker consumer prefetch/credit** phù hợp với khả năng ghi và transaction time.
5. **Retry với backoff và jitter**, giới hạn attempts, không tạo vòng retry tức thời.
6. **Circuit breaker/stop policy** nếu downstream đã quá tải; không cố ghi tiếp chỉ để giữ graph throughput đẹp.
7. **Adaptive concurrency** chỉ khi có metric tin cậy và hysteresis; tránh bộ điều khiển tăng/giảm worker quá nhạy gây dao động.
8. **Snapshot/partition scheduling** để worker không đồng thời quét toàn DB cùng một bảng/index gây I/O hotspot.

### Luật điều khiển đơn giản, có hysteresis

Ví dụ policy minh họa:

~~~text
Nếu JDBC pending > threshold trong >= 3 cửa sổ:
    ngừng tăng concurrency; có thể giảm worker slots có kiểm soát.

Nếu DB latency p95 ổn, queue còn backlog thật,
   retry thấp và CPU/DB còn headroom >= 5 cửa sổ:
    thử tăng concurrency 1 cấp.

Sau mỗi thay đổi:
    giữ đủ thời gian ổn định rồi mới điều chỉnh tiếp.
~~~

Threshold và số cửa sổ phải được benchmark. Đừng tạo vòng lặp “CPU thấp → tăng 8 workers → DB timeout → giảm 8 → CPU thấp” liên tục.

### Little's law và số in-flight

Nếu mỗi item cần `W` giây trung bình trong một hệ ổn định với `λ` item/s, in-flight trung bình khoảng `L=λW`. Nhưng nếu worker giữ 10.000 item chưa commit, hãy đo memory và failure blast radius: quá nhiều in-flight có thể làm RTO và retry amplification tăng dù peak rate cao.

## 19. Retry, restart, idempotency và hiệu ứng của chúng lên goodput

Một lần worker thất bại có thể làm `read/s` tăng vì đọc lại dữ liệu, trong khi goodput không tăng.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker / Step handler
    participant W as Worker A
    participant D as Business DB
    participant B as Worker B
    M->>Q: Partition/chunk K
    Q->>W: Deliver K
    W->>D: Commit output
    Note over W,M: Worker mất reply / ACK
    Q->>B: Redeliver K
    B->>D: Replay với business key K
    D-->>B: Unique/UPSERT prevents duplicate final row
    B-->>M: Reply
~~~

### Tình huống dễ báo sai throughput

Nếu metrics increment khi writer được gọi, lần redelivery sẽ tạo một “item processed” mới trên graph dù business output đã có. Sau sự cố, attempts/s có thể tăng mạnh và **goodput thật không đổi**.

Cần cùng lúc đo:

- New unique business commits/s.
- Read/process/write attempts/s.
- Retry/rollback/skip counts.
- DLQ/undelivered work.
- Missing/extra business keys sau reconciliation.
- Thời gian mất để throughput hữu ích trở lại sau failover.

### Checkpoint không tự tạo exactly-once

`ItemStream`/`JobRepository` quản lý restart state, nhưng nếu business DB và repository hoặc broker không cùng transaction, worker có thể commit rồi mất checkpoint/reply. Writer cần idempotency theo business key, ledger, outbox và cơ chế chống double side effects theo nghiệp vụ.

Không tạo `JobInstance` mới bằng identifying `run.id` chỉ để né execution đang `STARTED` sau crash rồi coi tất cả replay là “tăng thông lượng”. Đó có thể là reprocess toàn bộ snapshot; cần mô hình đếm và reconciliation riêng.

## 20. Thiết kế benchmark dài hạn thay vì chỉ chạy một lượt ngắn

Muốn chứng minh throughput bền vững, workload phải đủ đại diện cho production và **đủ dài để bộc lộ nút thắt tích lũy**.

### 20.1. Cố định biến và baseline

Trước khi benchmark:

1. **Chọn business scope:** số bản ghi, kích thước payload, tỉ lệ record có cost cao, loại processor, tỉ lệ retry dự kiến.
2. **Chốt input snapshot/manifest**: không để dữ liệu nguồn live thay đổi làm sai so sánh.
3. **Ghi phiên bản chạy:** Java, Spring Batch, DB schema/index, broker config, worker image, CPU/memory limits, connection pool.
4. **Định nghĩa measurement:** committed unique items/s, cửa sổ 1 phút/5 phút, thời gian warm-up, SLO và gate dữ liệu.
5. **Baseline một worker** trước khi tăng lên 2/4/8/16 slots; không dùng peak ở một pod khác cấu hình để so.
6. **Chỉ đổi một biến mỗi lần**: worker count, chunk size, JDBC pool hoặc partition count; nếu đổi nhiều biến, khó rút kết luận.
7. **Dành đủ input cho steady state**: job ngắn hoàn thành trước khi hệ đạt trạng thái ổn định không chứng minh long-run capacity.

### 20.2. Các pha một bài thử đề xuất

| Pha | Việc làm | Điều cần lưu |
| --- | --- | --- |
| Baseline | Chạy 1 worker trên snapshot/partition có cost tiêu biểu | CPU, throughput, p95 chunk, DB pool, output |
| Ramp | Tăng 1 → 2 → 4 → 8 slots theo từng mức | Độ tăng goodput, saturation mới |
| Steady soak | Giữ load đại diện trong khoảng đủ dài (ví dụ 60–120 phút) | Windowed goodput, trend slope, GC, memory, connection waits |
| Burst | Tăng input/arrival trong một khoảng có kiểm soát | Backlog, autoscaling/backpressure và khả năng hồi phục |
| Failure | Kill worker hoặc làm DB/broker chậm có kiểm soát | Retry amplification, RTO, lost ACK/response |
| Recovery soak | Duy trì sau sự cố, không chỉ xem service up | Goodput có trở lại sàn SLO không? |
| Drain | Để workload hữu hạn chạy hết | Straggler, final reconciliation |
| Re-run | Lặp lại phép thử ở các thời điểm độc lập | Độ lặp lại kết quả và confidence |

Thời lượng 60–120 phút là **ví dụ**; nhiều hệ cần chạy dài hơn để thấy memory leak, retention, database autovacuum, log growth hay GC. Những số đo ngắn 1–2 phút có thể bỏ lỡ bottleneck quan trọng.

### 20.3. Điều kiện so sánh công bằng

- Không so 8 worker đang chạy trên cache nóng với 1 worker sau cold start mà không đánh dấu khác biệt.
- Nếu làm sạch bảng output giữa các lần test, phải khôi phục snapshot/workload và trạng thái idempotency tương đương; nếu không, upsert conflict làm goodput “new records” giảm tự nhiên.
- Nếu dùng database production shared, noisy neighbors có thể làm kết quả biến động. Ghi lịch backup, maintenance, retention, lock và storage pressure khi benchmark.
- Không dùng cùng `JobInstance` đang restart để thay đổi partition names/boundaries nhằm thí nghiệm khác. Tạo kế hoạch run mới, vẫn đảm bảo input nghiệp vụ tương đương.
- Có phép **reconciliation** trước và sau test, tránh đạt số đẹp nhờ silently skipped items.

### 20.4. Kết quả nên báo cáo

Không chỉ báo một số peak. Mỗi cấu hình nên có:

~~~text
Workload: snapshot + record count + payload mix
Environment: CPU/RAM, DB quota, worker count, chunk size
Window: 1m và 5m; rule warm-up/steady đã xác định trước
Steady mean/median/p5 goodput, min window và trend
% windows đạt sàn SLO, số cửa sổ tụt liên tiếp
Peak goodput và thời lượng peak
p50/p95/p99 chunk latency, commit latency
Retry amplification, skip/rollback/DLQ
Queue depth/backlog trend và thời gian drain
CPU/GC, JDBC pending, DB locks, broker IO
RTO sau kill worker/manager
End-to-end JobInstance duration (gồm reconciliation)
Business reconciliation: PASS/FAIL
~~~

Một báo cáo không có thông số phân phối theo thời gian và đầu ra nghiệp vụ chưa đủ để khẳng định “throughput ổn định”.

## 21. Tiêu chí nghiệm thu và ví dụ đọc SLO

Dùng dữ liệu cửa sổ 5 phút ở mục 7: `[980,1010,995,620,590,975]` business item/s.

Nếu SLO yêu cầu **ít nhất 95%** cửa sổ đạt `900 item/s` thì có **4 trong 6** cửa sổ đạt, tương đương:

~~~text
pass_window_fraction = 4 / 6 ≈ 66,7%
SLO target = 95%
Result = FAIL
~~~

Dù không có lỗi mã nguồn, hệ thống **không đạt** SLO ví dụ. Hai cửa sổ liên tiếp đạt khoảng 620/590 là dấu hiệu cần điều tra sâu.

### Một hàm đánh giá đơn giản

Ví dụ Java 17 dùng dữ liệu các cửa sổ đã được chuẩn hóa về **cùng độ dài** và đã lọc pha theo quy tắc được công bố trước:

~~~java
import java.util.List;

public final class ThroughputSlo {

    public static double passingFraction(
            List<Double> windowRates,
            double floorItemsPerSecond) {

        if (windowRates == null || windowRates.isEmpty()
                || !Double.isFinite(floorItemsPerSecond)
                || floorItemsPerSecond < 0) {
            throw new IllegalArgumentException("Invalid SLO inputs");
        }

        for (double rate : windowRates) {
            if (!Double.isFinite(rate) || rate < 0) {
                throw new IllegalArgumentException("Invalid window rate");
            }
        }

        long passing = windowRates.stream()
                .filter(rate -> rate >= floorItemsPerSecond)
                .count();

        return passing / (double) windowRates.size();
    }
}
~~~

JUnit 5 kiểm chứng ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class ThroughputSloTest {

    @Test
    void failsWhenSteadyWindowsContainLongSlowPeriod() {
        var rates = List.of(
                980.0, 1010.0, 995.0,
                620.0, 590.0, 975.0);

        double fraction = ThroughputSlo.passingFraction(
                rates, 900.0);

        assertEquals(4.0 / 6.0, fraction, 0.000001);
        assertFalse(fraction >= 0.95);
    }
}
~~~

Hàm chỉ kiểm tra **một** thuộc tính SLO; production còn cần đánh giá consecutive-bad-windows, SLA end-to-end, số input tồn đọng, data correctness và số mẫu đủ đáng tin cậy.

### Tránh Goodhart's Law trong observability

Nếu chỉ thưởng cho tốc độ `read/s` cao, một hệ có thể skip record khó, giảm độ tin cậy transaction hoặc không làm reconciliation để “đạt KPI”. Tốc độ phải được gắn với **dữ liệu nghiệp vụ hợp lệ**, độ trễ hoàn tất, retry và các invariant kiểm thử.

## 22. Fault injection: throughput ổn định cả khi một phần hệ thống hỏng

Bài benchmark không chỉ thử môi trường “không lỗi”. Thực tế batch lớn gặp DB thỉnh thoảng chậm, worker mất kết nối, broker redelivery và rollout.

| Tình huống | Inject | Kỳ vọng |
| --- | --- | --- |
| Worker CPU pressure | Giảm quota CPU hoặc thêm CPU load | Rate suy giảm có thể giải thích, backpressure không vỡ |
| GC pressure | Tăng allocation/giảm memory an toàn trong staging | Nhận ra pause, throughput hồi phục sau điều chỉnh |
| JDBC pool saturation | Giảm pool dưới nhu cầu giả định | Pending + chunk latency tăng, giới hạn worker hợp lý |
| DB writer lock | Tạo row contention có kiểm soát | Retry/backoff hiệu quả, output không trùng |
| Read I/O slowdown | Throttle source hoặc storage | Goodput phản ánh bottleneck đọc, không retry storm |
| Broker publish latency | Giảm broker/network throughput | Backlog và reply latency được quan sát |
| Worker mất reply | Drop worker reply sau commit | Idempotency, metadata và recovery đúng |
| Kill worker trong chunk | `SIGKILL` worker ở nhiều điểm | Restart từ checkpoint bền vững, output đúng |
| Manager mất node | Kill manager, worker còn chạy | Không dispatch duplicate owner, recovery hợp lệ |
| Retry poison message | Gây lỗi có tính quyết định trên một record | Không retry vô hạn, DLQ/failure policy rõ |
| Partition skew | Đưa phần lớn record khó vào một range | Nhận biết straggler, không nhầm với mất capacity |
| Rolling deploy | Chạy worker phiên bản cũ/mới tương thích | Thông lượng không sụp do schema/codec mismatch |
| Snapshot expiry | Mô phỏng nguồn bị thu hồi sớm | Fail rõ, không đọc nguồn live sai version |
| Tăng concurrency quá mức | 4 → 8 → 16 slots trong quota hữu hạn | Tìm điểm bão hòa, không kết luận càng nhiều càng tốt |
| Data reconciliation | Tạo thiếu/trùng giả ở output | Gate chặn publish dù graph goodput đẹp |

**Pass criteria:** sau sự cố, goodput ổn định trở lại trong RTO mục tiêu và mọi business output đúng. Nếu throughput hồi phục nhưng writer đã nhân đôi thanh toán, bài thử **thất bại**.

### Các failure window khó

Một worker có thể commit DB rồi chết trước khi cập nhật `JobRepository` hoặc gửi reply. Lúc restart, chunk được replay; nếu chỉ tính attempts/s, biểu đồ có thể tăng đột biến. Test phải phân biệt committed unique effects với attempts và chứng minh idempotency.

### Không tự động scale-out khi control plane không chắc worker cũ đã dừng

Trong network partition, worker cũ có thể vẫn ghi business DB. Giao lại công việc cho worker mới mà không có ownership/fencing hoặc xác minh dừng có thể tạo duplicate side effect, làm rate cao lên giả tạo. Trong SLO, throughput sai nghiệp vụ phải bị loại khỏi **goodput**.

## 23. Runbook khi throughput giảm dần trong production

Nếu goodput từ vùng ổn định tụt thấp trong nhiều cửa sổ liên tiếp:

1. **Xác minh metric:** business goodput hay write attempts? Counter reset/scrape gaps/label changes có xảy ra không?
2. **Xác định khối lượng công việc còn lại:** snapshot remaining, backlog và expected record counts. Nếu input gần hết, đây có thể là drain bình thường.
3. **Đối chiếu latency và retry:** p95 chunk latency, rollback/skip, DB lock và API 429/503.
4. **Kiểm tra resource:** CPU throttle, GC, heap, JDBC pool active/pending, disk IO, broker unacked/retry.
5. **Kiểm tra phân bố việc:** worker idle, partition straggler, key range/tenant skew.
6. **Xác định thời điểm bắt đầu tụt:** trùng với deploy, thay index, DB vacuum/backup, broker restart hay tăng workload không?
7. **Khoanh vùng bottleneck:** một resource saturation có hàng đợi tăng hay hệ chỉ thiếu input?
8. **Giảm áp lực có kiểm soát** nếu downstream nghẽn: hạn chế dispatch/concurrency, bật backoff/rate limiter; không tạo retry storm.
9. **Tránh thay nhiều tham số cùng lúc**; dùng một canary hoặc thử nghiệm trên staging với snapshot tương đương.
10. **Kiểm tra correctness:** read/write/skip/retry counts cùng missing/extra business keys; không bỏ qua record lỗi để giữ tốc độ.
11. **Theo dõi sau thay đổi đủ dài:** sustained windows trở lại SLO, backlog có giảm, p95 latency và lock wait ổn định?
12. **Ghi nhận RTO, root cause và threshold mới**, bổ sung regression/load test.

### Một sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Goodput giảm liên tục"] --> B{"Còn input/backlog?"}
    B -->|"Không"| C["Drain bình thường: kiểm tra end-to-end SLA"]
    B -->|"Có"| D{"Retry/rollback tăng?"}
    D -->|"Có"| E["DB locks, timeouts, poison records, broker redelivery"]
    D -->|"Không"| F{"Worker active thấp?"}
    F -->|"Có"| G["Skew, scheduler, missing tasks, worker health"]
    F -->|"Không"| H{"DB pool/IO/CPU/GC saturation?"}
    H -->|"Có"| I["Tối ưu bottleneck, bounded concurrency"]
    H -->|"Không"| J["Kiểm tra metric, network, external dependencies"]
    E --> K["Canary + sustained test + reconciliation"]
    G --> K
    I --> K
    J --> K
~~~

### Tránh xử lý sai bằng cách chỉ tăng số worker

Nếu DB connection pool đã cạn và lock wait tăng, thêm 10 pod có thể làm `attempts/s` tăng trong vài phút nhưng `unique commit/s` còn giảm. Chỉ scale-out khi có nguồn input, tài nguyên headroom và bottleneck thực sự nằm ở worker.

## 24. Bài tập tình huống

Một job Spring Batch remote partitioning nhập **3,6 triệu sự kiện** trong 60 phút. Bốn worker lúc đầu chạy nhanh, sau đó đội vận hành tăng lên tám worker để giảm thời gian. Snapshot không thay đổi; mỗi worker `ItemReader` đọc range riêng. Writer dùng PostgreSQL và upsert business key.

Quan sát từ dashboard:

| Cửa sổ | Workers active | Read attempts/s | Unique commit/s | DB pending connections | p95 chunk commit |
| --- | ---: | ---: | ---: | ---: | ---: |
| 00–05 | 4 | 1.050 | 1.000 | 0 | 180 ms |
| 05–10 | 4 | 1.060 | 1.010 | 0 | 190 ms |
| 10–15 | 8 | 1.480 | 1.120 | 8 | 420 ms |
| 15–20 | 8 | 1.620 | 850 | 18 | 1.100 ms |
| 20–25 | 8 | 1.720 | 700 | 24 | 1.800 ms |
| 25–30 | 8 | 1.540 | 730 | 20 | 1.500 ms |

Đây là **dữ liệu giả định để luyện phân tích**, không phải benchmark thật của Spring Batch.

**Câu hỏi:**

1. Vì sao `read attempts/s` tăng nhưng throughput hữu ích lại giảm?
2. Vì sao throughput peak sau khi tăng từ 4 lên 8 worker chưa chứng minh hệ thống scale tốt?
3. Hai metric nào trong bảng gợi ý JDBC/database trở thành bottleneck?
4. Nên kiểm tra CPU/GС, DB lock, connection pool, retry và broker theo trình tự nào?
5. Nếu không còn input ở cuối job, có nên coi rate=0 là vi phạm SLO steady state?
6. Với 3,6 triệu event trong 60 phút, throughput trung bình toàn thời gian ít nhất cần bao nhiêu item/s?
7. Nếu chuẩn bị + đối soát mất 10 phút, target processing sustained tối thiểu là bao nhiêu item/s?
8. Với arrival rate 950 item/s và sustained μ=850 item/s, backlog thay đổi khoảng bao nhiêu sau 15 phút?
9. Nếu worker commit thành công nhưng mất reply và partition/chunk được chạy lại, counter nào có nguy cơ tăng sai?
10. Thử nghiệm nào giúp lựa chọn giữa 4, 6 và 8 worker khi DB pool là giới hạn?
11. Vì sao không nên dùng 5 phút peak đầu tiên để đặt `SLO=1.500 item/s`?
12. Nếu reconcile phát hiện 500 missing business keys nhưng JobExecution `COMPLETED`, có được publish không?

### Gợi ý đáp án

- **(1)** Các attempt/replay/rollback có thể tăng, trong khi DB unique commit thấp; cũng có contention khiến commit chậm.
- **(2)** Throughput cần được duy trì qua nhiều cửa sổ, dưới workload và resource budget nhất quán, không chỉ tăng ngắn hạn.
- **(3)** `DB pending connections` và `p95 chunk commit` tăng mạnh cùng lúc goodput giảm.
- **(4)** Xác nhận rate/remaining input, sau đó so DB pending/lock, retry/rollback, CPU/GC và queue/broker trên cùng timeline; không suy kết luận từ một metric.
- **(5)** Không nhất thiết. Nếu nguồn cạn, đó là pha drain; nhưng SLA toàn job vẫn phải xét thời gian thực.
- **(6)** `3.600.000 / 3.600 = 1.000 item/s`.
- **(7)** `3.600.000 / (50*60) = 1.200 item/s`, chưa có headroom.
- **(8)** `(950-850) * 900 = 90.000 item` tăng backlog trong mô hình lý tưởng.
- **(9)** Counter attempts hoặc write calls; phải đo unique committed business effects và đối soát output.
- **(10)** Chạy cùng snapshot/cost mix ở từng mức concurrency, đo goodput theo cửa sổ, DB pending/lock, p95 commit, RTO và correctness, có lặp lại.
- **(11)** Peak có thể do warm cache, snapshot dễ, queue/rate tạm thời; SLO cần dựa sustained capacity, không peak.
- **(12)** Không. Business reconciliation fail; phải điều tra, xử lý theo runbook và chứng minh kết quả đúng.

## 25. Checklist trước production

- [ ] Định nghĩa rõ **goodput**: business key/operation identity, điều kiện commit và phạm vi snapshot.
- [ ] Phân biệt read/process/write attempts với unique business commits.
- [ ] Có SLO theo cửa sổ thời gian **và** SLA hoàn tất JobInstance end-to-end.
- [ ] Đã xác định trước warm-up, steady-state, drain và nguyên tắc xử lý outage trong báo cáo.
- [ ] Counter/timer có nhãn cardinality thấp, theo dõi reset/missing scrape và thay đổi pod.
- [ ] Nếu telemetry sau commit có thể mất mẫu, đã có nguồn audit/reconciliation bền vững cho kết quả chính thức.
- [ ] Có rate 1m/5m, median/p5/CV hoặc chỉ số biến động và alert sustained decline.
- [ ] Theo dõi backlog, arrival rate, retries, DLQ và p95/p99 chunk/DB latency.
- [ ] Có CPU, heap/GC, JDBC pool, DB lock, IO, JobRepository, broker/network metrics.
- [ ] Đã kiểm tra thread safety nếu dùng multi-threaded step; partitioning giữ state/reader độc lập.
- [ ] Snapshot và partition manifest bất biến giữa các lần restart cùng `JobInstance`.
- [ ] Biết skew và expected record/cost theo partition; không kết luận từ peak cluster throughput.
- [ ] Đã benchmark nhiều chunk sizes và worker counts dưới cùng resource quota.
- [ ] Có bounded executor, backpressure, retry backoff và connection budget trên toàn cluster.
- [ ] Writer idempotent; side effect ngoài DB có ledger/outbox hoặc guard tương ứng.
- [ ] Đã thử soak dài hạn, kill worker, mất reply, DB/broker degradation và recovery.
- [ ] Đã tính throughput mục tiêu từ data volume, SLA và thời gian overhead ngoài processing.
- [ ] Báo cáo gồm độ biến động theo thời gian, RTO, reconciliation, không chỉ một số trung bình.
- [ ] Không publish kết quả thiếu/thừa/sai business key dù graph throughput đạt mục tiêu.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps, partitioning và distributed scaling.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): khả năng instrumentation/metrics của Spring Batch.
- [Spring Batch Reference – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution` và metadata.
- [Spring Batch Reference – Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk/commit/retry logic.
- [Spring Batch Reference – ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoint và state.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote partitioning/chunking và middleware.
- [Micrometer – Core Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): `Counter`, `Timer` và quan sát theo tags.
- [Prometheus – Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate`, `increase`, `histogram_quantile`.
- [Prometheus – Metric and Label Naming](https://prometheus.io/docs/practices/naming/): units, labels và cardinality.
- [PostgreSQL – Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): DB activity, waits và statistics.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): transaction consistency và read stability.
- [Java SE 17 – java.time](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): thời gian cửa sổ và duration.

## Ghi nhớ

**Throughput ổn định theo thời gian là khả năng duy trì tốc độ kết quả nghiệp vụ đúng và đã commit, không phải chạm peak read/write attempts trong vài phút.** Hãy đo **goodput trên nhiều cửa sổ**, gắn với backlog, retry, latency, CPU/GC, DB pool, I/O và JobRepository. Chỉ tăng worker khi bottleneck còn nằm ở worker và các tài nguyên dùng chung vẫn có headroom; nếu DB/broker đạt trần, bounded concurrency và backpressure có thể hiệu quả hơn scale-out. Dùng immutable snapshot, partition boundaries ổn định, checkpoint/restart và idempotent writer để throughput không bị “tăng giả” nhờ replay hoặc skip. Đánh giá cả warm-up, steady-state, failure/recovery và tổng thời gian job; **mở rộng Spring Batch chỉ thành công khi tốc độ hữu ích duy trì được, SLA đạt và kết quả nghiệp vụ vẫn chính xác**.
