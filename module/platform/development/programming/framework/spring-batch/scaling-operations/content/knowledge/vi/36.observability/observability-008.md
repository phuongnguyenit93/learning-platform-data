# Alert backlog tăng liên tục trong Spring Batch phân tán

> **Chương:** Observability
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình xử lý phân tán; đo nút thắt, bảo đảm thread safety, retry/restart và vận hành job theo tài nguyên thực tế.

Khi một job có 24 remote workers, một hàng đợi chứa 50.000 requests **không nhất thiết là sự cố**: manager có thể vừa nạp một snapshot lớn. Nhưng nếu backlog tăng trong nhiều chu kỳ đo, tuổi item chờ lâu nhất vượt SLA hoặc tốc độ hoàn tất gần bằng 0 dù workers đang hoạt động, hệ thống có thể đang bão hòa database, mất consumer, gặp broker redelivery hay retry storm.

**Alert backlog tăng liên tục** phải trả lời được: *Backlog nào? Đơn vị là chunks, partitions, messages hay business items? Bao nhiêu đang chờ, đang xử lý và chưa biết kết quả? Nguồn đang nạp nhanh hơn worker hoàn tất hay worker đã dừng? Có phải hiện tại là khung giờ phải chạy không?* Bài này xây các số đo, quy tắc cảnh báo, runbook và kiểm thử để phát hiện vấn đề mà không đánh đổi tính đúng dữ liệu.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa backlog theo từng kiến trúc: remote chunking, remote partitioning, local partitioning, multi-threaded step và durable work queue.
2. Phân biệt `READY`, `RETRY_WAIT`, `IN_FLIGHT`, `UNKNOWN`, `DONE`, `QUARANTINED` và dead-letter; tránh tính trùng redelivery.
3. Tính backlog growth rate, ingress/completion rate, oldest age, ETA xử lý hết và dự báo trễ deadline.
4. Thu thập gauge/counter bằng Micrometer, Prometheus; dùng `deriv`, `rate`, `for` và recording rules đúng kiểu dữ liệu.
5. Viết alert tăng liên tục, không có tiến độ, item chờ quá lâu, UNKNOWN và metrics bị stale/missing.
6. Xác định nguyên nhân tại manager, worker, broker, JobRepository, database và downstream API rồi điều tiết capacity an toàn.
7. Kiểm thử spike, backlog tăng bền vững, mất reply, worker crash, restart, miss schedule và mất telemetry.

## 1. Một backlog lớn chưa đủ để kết luận quá tải

Xét job nhập 4 triệu đơn hàng bằng remote chunking, chunk size 200, 16 consumers:

~~~text
01:02 ready backlog = 2.000 chunk requests
01:07 ready backlog = 5.000 chunk requests
01:12 ready backlog = 8.000 chunk requests
01:17 ready backlog = 11.000 chunk requests

Manager gửi mới     ≈ 30 chunks/s
Workers hoàn tất    ≈ 20 chunks/s
Tốc độ tích lũy ròng ≈ +10 chunks/s
~~~

Nếu xu hướng kéo dài, hệ thống không bắt kịp tốc độ nạp. Nhưng với một snapshot được nạp một lần:

~~~text
01:00  ready =     0
01:01  ready = 8.000  (upstream burst)
01:02  ready = 7.000
01:05  ready = 4.000
01:10  ready = 1.000
01:12  ready =     0
~~~

Đó là một **spike hợp lệ** nếu worker có khả năng hoàn tất trước SLA. Alert `backlog > 2.000` ở mỗi lần đo sẽ báo động quá nhiều. Một alert tốt xét **ngưỡng, xu hướng và thời gian kéo dài**, kết hợp cảnh báo khác cho item tồn đọng quá tuổi.

## 2. Định nghĩa backlog theo đơn vị chính xác

| Mô hình Spring Batch | Đơn vị công việc chờ | Không được suy ra |
| --- | --- | --- |
| **Remote chunking** | Chunk requests chưa được worker xử lý, cùng các requests in-flight cần theo dõi riêng | Một message = một item nguồn |
| **Remote partitioning** | Logical worker partitions chưa hoàn tất/chưa dispatch, dựa trên StepExecution và partition plan | Một partition = một chunk hoặc một lượng dữ liệu bằng nhau |
| **Local partitioning** | Worker tasks còn trong executor queue hoặc partitions pending | `gridSize` là số threads đang chạy thật |
| **Multi-threaded step** | Chunk tasks chờ TaskExecutor | `readCount` chính là queue length |
| **Durable work queue tự quản** | Work IDs ở trạng thái có thể nhận hoặc đang chờ retry | Một redelivery = một work unit mới |
| **Kafka-based consumer** | Offset lag của consumer group/topic partitions | Lag luôn bằng số business effects chưa commit |

Luôn ghi **unit** trên dashboard: `ready_messages`, `pending_partitions`, `pending_business_items`, `remaining_bytes`, `oldest_age_seconds`. Không cộng hàng nghìn chunk requests với hàng trăm worker partitions rồi gọi đó là tổng số records.

### Những trạng thái phải tách riêng

Với một work registry tự quản:

~~~text
READY        đủ điều kiện được cấp ngay
RETRY_WAIT   đang đợi available_at/backoff
IN_FLIGHT    đã giao worker nhưng chưa có outcome được xác nhận
UNKNOWN      commit/HTTP reply/ACK không rõ kết quả
DONE         hoàn tất theo hợp đồng nghiệp vụ
QUARANTINED  record đã cách ly theo chính sách được duyệt
~~~

Đặt:

~~~text
pending_backlog = READY + RETRY_WAIT
ready_backlog   = READY
unresolved_work = READY + RETRY_WAIT + IN_FLIGHT + UNKNOWN
~~~

**QUARANTINED** không nằm trong pending vì đã được đưa ra khỏi hàng xử lý thông thường, nhưng vẫn có thể chặn publish hoặc cần replay; phải có metrics và audit riêng. `DONE` phải là kết quả đã xác nhận, không chỉ là worker trả về từ hàm `write(...)`.

### Không đếm attempts thành số work units

~~~text
Logical work_id: W-17
  Delivery attempt #1: worker timeout
  Delivery attempt #2: reply thất lạc
  Delivery attempt #3: no-op idempotent

work units chưa xác nhận = 1
delivery attempts       = 3
~~~

Broker delivery, chunk attempt, StepExecution và business work ID là các identity khác nhau. Dùng **stable logical ID** và unique constraints để tránh backlog phóng đại vì redelivery.

## 3. Một pipeline có nhiều hàng đợi

~~~mermaid
flowchart LR
    S["Input snapshot"] --> M["Manager reader/dispatcher"]
    M --> Q[("Broker ready queue")]
    Q --> W["Workers"]
    W --> D[("Business DB / durable inbox")]
    D --> R["Reconciliation / projection"]
    R --> P["Publish"]
    Q --> B1["Ready / unacked"]
    D --> B2["Unapplied / UNKNOWN"]
    R --> B3["Publish blocked"]
~~~

Ví dụ broker queue `ready=0` nhưng:

- `unacked=5.000`: workers đã nhận requests nhưng chưa ACK.
- Inbox có 500.000 events chưa apply đúng thứ tự.
- 40 partitions `FAILED` đang chờ restart.
- Publish gate bị chặn do 100 business operations `UNKNOWN`.

**Queue rỗng không đồng nghĩa công việc nghiệp vụ đã hoàn tất.** Đo từng hàng đợi và biết rõ **điểm kết thúc** được người dùng nghiệp vụ kỳ vọng.

### Broker ready, unacked, redelivery, DLQ

| Tín hiệu | Ý nghĩa | Dễ bị hiểu sai |
| --- | --- | --- |
| Ready | Messages sẵn sàng chưa được consumer nhận | Không bao gồm requests đang xử lý |
| Unacked/in-flight | Đã giao nhưng chưa xác nhận theo broker | Không cho biết business DB đã commit hay chưa |
| Redelivery | Message được phát lại | Không phải logical work mới |
| DLQ | Messages chuyển sang hàng lỗi | Không phải tất cả item được xử lý thành công |
| Kafka lag | Chênh offsets của consumer group | Không phải business commit count nếu commit offset và DB khác transaction |
| Reply pending | Manager chưa có response tương ứng | Timeout không chứng minh worker chưa ghi dữ liệu |

Ý nghĩa của metrics và ACK phụ thuộc RabbitMQ/Kafka/Spring Integration adapter cụ thể. Không mặc định broker có exactly-once business effects.

## 4. Công thức tốc độ backlog và giới hạn của nó

Cho cùng một loại logical work unit:

~~~text
B(t): pending backlog tại thời điểm t
λ(t): tốc độ thêm work vào pending, units/s
μ(t): tốc độ work được hoàn tất hợp lệ, units/s
~~~

Trong mô hình đơn giản không có requeue, quarantine, UNKNOWN hay chuyển trạng thái phức tạp:

~~~text
dB/dt ≈ λ - μ
~~~

Nếu `λ > μ` trong thời gian dài, backlog tăng. Nhưng hệ thống thực tế có:

- `IN_FLIGHT → READY` khi lease hết.
- `RETRY_WAIT → READY` khi hết backoff.
- `IN_FLIGHT → UNKNOWN` khi mất phản hồi.
- `READY → QUARANTINED` khi phát hiện lỗi nghiệp vụ.

Vì vậy **rate(enqueued_total) - rate(completed_total)** chỉ là tín hiệu chẩn đoán, không nhất thiết bằng độ dốc pending ở một state machine nhiều trạng thái. Cần đo snapshot trạng thái trực tiếp từ nguồn đáng tin.

### Độ dốc trong khoảng thời gian

~~~text
ΔB = B(t2) - B(t1)
growth = ΔB / (t2 - t1)
~~~

Ví dụ backlog tăng 5.000 → 11.000 trong 10 phút:

~~~text
ΔB = 6.000 work units
Δt = 600 seconds
growth ≈ 10 units/s
~~~

Đây là tốc độ ròng, **không phải** số message producers thực sự gửi. Một retry storm cũng có thể làm ready backlog tăng.

### Vì sao đo qua nhiều cửa sổ?

| Window | Phát hiện tốt | Hạn chế |
| --- | --- | --- |
| 1–2 phút | Sự cố đột ngột, mất consumer | Dễ nhiễu do burst |
| 10–15 phút | Tăng liên tục, nghẽn bền vững | Có độ trễ nhận biết |
| 30–60 phút | Trend và capacity planning | Có thể che lỗi ngắn |
| Cửa sổ SLA | Có kịp giờ publish không | Cần business schedule/manifest chính xác |

Kết hợp **absolute backlog threshold + positive slope + khoảng `for`** giúp tránh cảnh báo chỉ vì một lần nạp theo lô.

## 5. Tuổi item cũ nhất và ETA xử lý hết

Backlog 300 work units vẫn có thể nghiêm trọng nếu một item chờ **4 giờ**. Ngược lại 50.000 items vừa nạp có thể hợp lệ nếu SLA còn xa.

~~~text
oldest_ready_age_seconds
  = now - thời điểm READY work unit cũ nhất bắt đầu đủ điều kiện claim
~~~

Với work `RETRY_WAIT` chưa tới `available_at`, không nên tính nó là **READY quá hạn**. Cần tách:

- `oldest_ready_age_seconds`.
- `oldest_retry_wait_age_seconds` nếu có retry SLA.
- `oldest_unresolved_age_seconds` theo thời điểm tạo operation ban đầu nếu nghiệp vụ cần.

**Lưu ý:** Nếu SLA tính từ lúc source tạo event, đừng reset tuổi business item chỉ vì chuyển từ IN_FLIGHT về READY. Dùng `source_created_at` hoặc `first_seen_at` riêng.

### Dự báo ETA

Nếu snapshot đã ngừng nạp:

~~~text
T_drain ≈ B / μ
~~~

Nếu vẫn nạp và `μ > λ`:

~~~text
T_catch_up ≈ B / (μ - λ)
~~~

Nếu `μ ≤ λ`, sẽ **không bắt kịp** nếu tốc độ hiện tại kéo dài. Không chia cho 0 hoặc báo ETA = 0.

Ví dụ:

~~~text
B = 90.000 units
μ = 200 units/s
λ = 150 units/s

T_catch_up = 90.000 / 50 = 1.800 giây = 30 phút
~~~

Đây chỉ là ước lượng khi work units có chi phí tương đương, throughput ổn định và không có skew/retry storm. Với partitions kích thước khác nhau, dùng bytes/items remaining hoặc weighted progress.

## 6. Metrics cần đo và đơn vị

| Metric do ứng dụng chọn | Loại | Đơn vị | Ý nghĩa |
| --- | --- | --- | --- |
| `batch_work_units{state="ready"}` | Gauge | work IDs | Chờ cấp ngay |
| `batch_work_units{state="retry_wait"}` | Gauge | work IDs | Chờ backoff |
| `batch_work_units{state="in_flight"}` | Gauge | work IDs | Đang xử lý, chưa xác nhận |
| `batch_work_units{state="unknown"}` | Gauge | work IDs | Outcome chưa rõ |
| `batch_work_units{state="quarantined"}` | Gauge | work IDs | Cách ly có audit |
| `batch_oldest_ready_age_seconds` | Gauge | seconds | Work đủ điều kiện chờ lâu nhất |
| `batch_work_units_enqueued_total` | Counter | events/transitions | Số lần thêm vào queue theo contract |
| `batch_work_units_completed_total` | Counter | completed events | Số lần hoàn tất theo contract |
| `batch_worker_active` | Gauge | workers | Số workers active thực |
| `batch_retry_attempts_total` | Counter | attempts | Retry/redelivery |
| `batch_worker_lease_expired_total` | Counter | events | Hết lease |
| `batch_chunk_rollbacks_total` | Counter | rollbacks | Chunk rollback |
| `batch_reconciliation_mismatch_total` | Counter | incidents/items | Sai lệch theo định nghĩa |

Đây là **schema metrics mẫu**, không phải danh sách Spring Batch tự xuất. Spring Batch hỗ trợ observation/metrics tùy phiên bản, nhưng workload backlog xuyên broker, JobRepository và business store thường cần instrument bổ sung.

### Không nhầm StepExecution counters với backlog

`StepExecution.readCount`, `writeCount`, `rollbackCount` và skip counters đo một **execution**, không cho biết trực tiếp bao nhiêu logical work units còn pending.

~~~text
partition-01 COMPLETED readCount=50.000
partition-02 STARTED   readCount=30.000
partition-03 FAILED    readCount=12.000
partition-04 chưa dispatch
~~~

Không thể tính `pending = 4 × 50.000 - SUM(readCount)` nếu partitions không đều, có rollback, restart hoặc writer idempotent no-op. Tính từ **input manifest và logical partition states**, đối soát tới business output.

## 7. Chọn nguồn dữ liệu đáng tin và tránh nhân bản gauges

### Broker, JobRepository hay business work registry?

1. **Broker exporter:** phù hợp đo ready/unacked/redelivery/lag, nhưng metric có đơn vị **messages**.
2. **JobRepository/JobExplorer:** phù hợp trạng thái Job/StepExecution, cần tổng hợp theo **logical partition** qua restart.
3. **Durable work registry:** phù hợp đo READY/RETRY/UNKNOWN theo **stable work ID**, nếu ứng dụng thật sự có queue state machine này.
4. **Business ledger/inbox:** phù hợp xác nhận effect/operation đã commit và reconciliation.
5. **Sealed input manifest:** phù hợp số expected items/bytes và partition plan cố định.

Nếu 4 manager replicas cùng query và xuất `batch_work_units{state="ready"}=10.000` (mỗi replica báo **toàn bộ** pipeline), Prometheus `sum` sẽ tạo **40.000**, sai gấp 4. Dùng **một exporter authoritative**, hoặc `max`/leader aggregation chỉ khi đã kiểm chứng leader/freshness semantics. Chỉ `sum` khi mỗi series đại diện một **shard không giao nhau**.

### Ghi timestamp refresh

Exporter còn sống không có nghĩa database query thành công. Có thể xuất:

~~~text
batch_metrics_last_refresh_epoch_seconds
batch_metrics_refresh_failures_total
~~~

Chỉ cập nhật timestamp sau khi đọc thành công. **Không đặt backlog=0 khi database không truy vấn được**, vì sẽ làm dashboard trông như đã hoàn tất.

## 8. Ví dụ SQL đọc backlog từ durable work queue

Đây là **schema tự quản lý work units**, không phải schema mặc định của `BATCH_*`:

~~~sql
CREATE TABLE batch_work_queue (
    work_id        VARCHAR(160) PRIMARY KEY,
    pipeline       VARCHAR(120) NOT NULL,
    manifest_id    VARCHAR(160) NOT NULL,
    state          VARCHAR(30) NOT NULL,
    available_at   TIMESTAMPTZ NOT NULL,
    state_since    TIMESTAMPTZ NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_batch_work_state CHECK (
        state IN ('READY', 'RETRY_WAIT', 'IN_FLIGHT',
                  'UNKNOWN', 'DONE', 'QUARANTINED')
    )
);

CREATE INDEX idx_batch_queue_monitor
    ON batch_work_queue (pipeline, state, available_at);
~~~

Queue production còn cần owner/lease/fencing, attempts, priority và outcome ledger nếu dùng dynamic ownership. Khi đã sử dụng Spring Batch remote partitioning chuẩn, **không nên xây thêm queue state machine xung đột với StepExecution**; chỉ dùng mẫu này khi kiến trúc thật cần work queue riêng.

### Đếm trạng thái

~~~sql
SELECT
    pipeline,
    COUNT(*) FILTER (WHERE state = 'READY') AS ready_count,
    COUNT(*) FILTER (WHERE state = 'RETRY_WAIT') AS retry_wait_count,
    COUNT(*) FILTER (WHERE state = 'IN_FLIGHT') AS in_flight_count,
    COUNT(*) FILTER (WHERE state = 'UNKNOWN') AS unknown_count,
    COUNT(*) FILTER (WHERE state = 'QUARANTINED') AS quarantined_count
FROM batch_work_queue
WHERE pipeline = :pipeline
GROUP BY pipeline;
~~~

`FILTER` và `TIMESTAMPTZ` là PostgreSQL; `:pipeline` là placeholder khi gọi bằng Spring JDBC/DAO, không phải cú pháp PostgreSQL trực tiếp. Với bảng hàng triệu rows, tránh chạy `COUNT(*)` mỗi giây nếu làm nóng DB; chọn chu kỳ 30–60 giây, index và read model/counters có reconciliation định kỳ.

### Đo READY age đúng thời điểm đủ điều kiện

~~~sql
SELECT COALESCE(
    EXTRACT(EPOCH FROM (
        NOW() - MIN(GREATEST(state_since, available_at))
    )),
    0
) AS oldest_eligible_age_seconds
FROM batch_work_queue
WHERE pipeline = :pipeline
  AND state = 'READY'
  AND available_at <= NOW();
~~~

Nếu SLA tính từ nguồn, query `source_created_at` riêng; đừng tự “trẻ hóa” item bằng cách reset `state_since` khi retry. Query trên chỉ là một phép đo **age trong trạng thái READY hiện tại**.

### Vì sao cần UNKNOWN riêng?

Worker upload/commit thành công nhưng mất reply, manager coi outcome `UNKNOWN`. `READY+RETRY_WAIT` có thể giảm mà business output **chưa được xác nhận với manager**. Không báo “job xong” khi chỉ số pending thấp mà UNKNOWN hoặc reconciliation mismatch còn tồn tại.

## 9. Micrometer gauges: cập nhật từ authoritative snapshot

Để thu thập đúng số liệu, một **monitor/poller chuyên trách** đọc snapshot trạng thái và cập nhật gauges cho Prometheus.

### 9.1. Định nghĩa snapshot

~~~java
public record BacklogSnapshot(
        long ready,
        long retryWait,
        long inFlight,
        long unknown,
        long quarantined,
        long oldestEligibleAgeSeconds) {}
~~~

Đây là record Java 17 do ứng dụng định nghĩa, không phải Spring Batch class có sẵn.

### 9.2. Publisher dùng Micrometer

~~~java
import java.util.concurrent.atomic.AtomicLong;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;

public final class BacklogGaugePublisher {

    private final AtomicLong ready = new AtomicLong();
    private final AtomicLong retryWait = new AtomicLong();
    private final AtomicLong inFlight = new AtomicLong();
    private final AtomicLong unknown = new AtomicLong();
    private final AtomicLong quarantined = new AtomicLong();
    private final AtomicLong oldestAgeSeconds = new AtomicLong();
    private final AtomicLong lastRefreshEpochSeconds = new AtomicLong();

    public BacklogGaugePublisher(
            MeterRegistry registry,
            String pipeline,
            String environment) {
        Tags base = Tags.of(
                "pipeline", pipeline, "environment", environment);
        registerState(registry, base, "ready", ready);
        registerState(registry, base, "retry_wait", retryWait);
        registerState(registry, base, "in_flight", inFlight);
        registerState(registry, base, "unknown", unknown);
        registerState(registry, base, "quarantined", quarantined);

        Gauge.builder("batch_oldest_ready_age_seconds",
                oldestAgeSeconds, AtomicLong::get)
                .tags(base).register(registry);
        Gauge.builder("batch_metrics_last_refresh_epoch_seconds",
                lastRefreshEpochSeconds, AtomicLong::get)
                .tags(base).register(registry);
    }

    private static void registerState(
            MeterRegistry registry, Tags base,
            String state, AtomicLong value) {
        Gauge.builder("batch_work_units", value, AtomicLong::get)
                .tags(base.and("state", state))
                .register(registry);
    }

    public void publish(BacklogSnapshot s, long nowEpochSeconds) {
        ready.set(s.ready());
        retryWait.set(s.retryWait());
        inFlight.set(s.inFlight());
        unknown.set(s.unknown());
        quarantined.set(s.quarantined());
        oldestAgeSeconds.set(s.oldestEligibleAgeSeconds());
        lastRefreshEpochSeconds.set(nowEpochSeconds);
    }
}
~~~

**Yêu cầu production:** Tạo publisher thành bean còn sống trong suốt thời gian metric được dùng; gauge có thể tham chiếu yếu tới object quan sát. Cần `MeterRegistry`, Spring Boot Actuator và registry Prometheus tương thích. Các `AtomicLong` cập nhật tuần tự không tạo một snapshot **atomic across all metrics** trong lúc scrape; nếu yêu cầu nhất quán hoàn toàn, dùng một immutable snapshot/read model và cách xuất metrics tương ứng.

### 9.3. Poller

~~~java
import java.time.Clock;
import org.springframework.scheduling.annotation.Scheduled;

public final class BacklogSnapshotPoller {

    private final BacklogSnapshotReader reader;
    private final BacklogGaugePublisher publisher;
    private final Clock clock;

    public BacklogSnapshotPoller(
            BacklogSnapshotReader reader,
            BacklogGaugePublisher publisher,
            Clock clock) {
        this.reader = reader;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Scheduled(fixedDelay = 30_000)
    public void refresh() {
        BacklogSnapshot s = reader.read();
        publisher.publish(s, clock.instant().getEpochSecond());
    }
}
~~~

`BacklogSnapshotReader` là interface ứng dụng cần tự khai báo/triển khai; `Clock` cần bean. `@Scheduled` yêu cầu bật scheduling theo cấu hình ứng dụng. Nếu `reader.read()` lỗi, **không** cập nhật timestamp như một lần refresh thành công; ghi metric/log lỗi riêng và dùng stale alert. Một poller trên nhiều pods có thể phát cùng backlog toàn cục nhiều lần: tránh `sum` sai.

## 10. Prometheus: chọn đúng hàm theo metric type

Giả sử các metrics được scrape với low-cardinality labels `pipeline` và `environment`.

~~~promql
# Tổng pending queue (ready + retry_wait) theo logical work units.
sum by (pipeline, environment) (
  batch_work_units{state=~"ready|retry_wait"}
)
~~~

### Deriv với gauge, rate với counter

| Bài toán | PromQL phù hợp | Ghi chú |
| --- | --- | --- |
| Backlog tăng/giảm | `deriv(gauge[15m])` | Ước lượng slope bằng hồi quy tuyến tính |
| Backlog thay đổi tuyệt đối | `delta(gauge[15m])` | Gauge có thể giảm hoặc tăng |
| Completion throughput | `rate(completed_total[15m])` | Counter với semantics rõ |
| Số completed trong window | `increase(completed_total[15m])` | Ước lượng từ counter, không phải authoritative unique ledger |
| Dự báo backlog tuyến tính | `predict_linear(gauge[30m], 1800)` | Chỉ là ngoại suy |
| Mất dữ liệu metrics | `absent_over_time(series[10m])` | Cần expected-pipeline inventory |

**Không dùng `rate` cho backlog gauge**: backlog không phải counter luôn tăng. Ngược lại không dùng `deriv` làm phép thay thế trực tiếp `rate` của một counter có reset.

### Recording rules minh họa

~~~yaml
groups:
  - name: batch-backlog-recording
    interval: 1m
    rules:
      - record: pipeline:backlog_pending_work_units
        expr: |
          sum by (pipeline, environment) (
            batch_work_units{state=~"ready|retry_wait"}
          )

      - record: pipeline:backlog_growth_units_per_second:15m
        expr: |
          deriv(pipeline:backlog_pending_work_units[15m])

      - record: pipeline:completed_units_per_second:15m
        expr: |
          sum by (pipeline, environment) (
            rate(batch_work_units_completed_total[15m])
          )

      - record: pipeline:enqueued_units_per_second:15m
        expr: |
          sum by (pipeline, environment) (
            rate(batch_work_units_enqueued_total[15m])
          )
~~~

Đây là file rules mẫu. Nếu nhiều instances phát cùng **global gauge**, tổng `sum` trên các instances bị trùng sẽ sai; phải đảm bảo một exporter authoritative hoặc aggregation theo semantics thật. Nếu mỗi instance chỉ phát **shard riêng không overlap**, sum là hợp lý.

## 11. Alert backlog tăng liên tục

Rule `BatchBacklogGrowing` yêu cầu đồng thời:

1. Pending backlog vượt ngưỡng đáng kể.
2. Slope dương trong cửa sổ 15 phút.
3. Pipeline đang trong cửa sổ **kỳ vọng hoạt động**.
4. Điều kiện kéo dài thêm `for: 10m`.

Metrics custom về lịch:

~~~text
pipeline_schedule_active{pipeline="ordersImport",environment="prod"} 1
~~~

Giá trị 1 nghĩa là chính sách **kỳ vọng pipeline xử lý**, không phải chỉ đếm hiện có bao nhiêu worker. Nếu worker chết, metric này **không** được tự đổi về 0 rồi tắt alert.

~~~yaml
groups:
  - name: batch-backlog-alerts
    rules:
      - alert: BatchBacklogGrowing
        expr: |
          (pipeline:backlog_pending_work_units > 2000)
          and on (pipeline, environment)
          (pipeline:backlog_growth_units_per_second:15m > 0.05)
          and on (pipeline, environment)
          (pipeline_schedule_active == 1)
        for: 10m
        labels:
          severity: warning
          owner: data-platform
        annotations:
          summary: "Backlog pipeline {{ $labels.pipeline }} dang tang"
          description: "Pending backlog cao va slope duong keo dai"
~~~

**Ngưỡng chỉ là ví dụ:** `0.05 units/s` tương đương khoảng 45 units/15 phút. Một batch xử lý hàng triệu units/s cần threshold khác, hoặc dùng baseline theo kích thước snapshot và SLA. `for` yêu cầu biểu thức tiếp tục đúng qua nhiều lần evaluation, không phải phép chứng minh backlog **tăng trên từng giây riêng lẻ**.

### Khi nào rule này không phát hiện sự cố?

- Backlog lớn nhưng **đang giảm quá chậm để kịp deadline**.
- Ready=0 trong khi 5.000 work units kẹt `IN_FLIGHT`.
- `UNKNOWN` tăng khiến pending giảm nhưng kết quả chưa được xác nhận.
- Exporter chết, series mất hoặc stale.
- Job/scheduler không tạo input nào dù kỳ này **đáng lẽ phải chạy**.

Vì vậy cần cảnh báo bổ sung, không dựa duy nhất vào một slope rule.

## 12. Alert không có tiến độ và backlog quá tuổi

### 12.1. Backlog có nhưng throughput gần bằng 0

~~~yaml
- alert: BatchBacklogNoProgress
  expr: |
    (pipeline:backlog_pending_work_units > 300)
    and on (pipeline, environment)
    (pipeline:completed_units_per_second:15m < 0.01)
    and on (pipeline, environment)
    (pipeline_schedule_active == 1)
  for: 15m
  labels:
    severity: critical
  annotations:
    summary: "Pipeline {{ $labels.pipeline }} co backlog nhung khong hoan tat work"
~~~

Rule yêu cầu series `completed_units_per_second` **có tồn tại** và biểu diễn một counter hợp lệ. Nếu exporter chưa phát metric completion, phép so sánh trả vector rỗng và alert có thể im lặng; cần **telemetry missing alert** riêng. Ngưỡng 0,01 units/s chỉ minh họa.

### 12.2. Item READY cũ nhất vượt SLA

~~~yaml
- alert: BatchOldestReadyTooOld
  expr: |
    (max by (pipeline, environment) (
      batch_oldest_ready_age_seconds
    ) > 3600)
    and on (pipeline, environment)
    (pipeline_schedule_active == 1)
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Oldest READY work qua 1 gio cho {{ $labels.pipeline }}"
~~~

Age tăng gần **1 giây mỗi giây** khi một item còn chờ, nên không cần thêm `deriv(age) > 0`. Giá trị chính là **tuổi vượt ngưỡng**. Nếu item `IN_FLIGHT` treo hàng giờ, rule này không thấy; cần `oldest_unacked_age_seconds` hoặc `oldest_unresolved_age_seconds` tương ứng.

### 12.3. UNKNOWN không được xem là đã hoàn tất

~~~yaml
- alert: BatchUnknownOutcomes
  expr: |
    sum by (pipeline, environment) (
      batch_work_units{state="unknown"}
    ) > 0
  for: 15m
  labels:
    severity: critical
  annotations:
    summary: "Pipeline {{ $labels.pipeline }} co outcomes chua xac nhan"
~~~

`>0` hợp với hệ thống không cho phép UNKNOWN tồn tại quá 15 phút. Hệ thống khác có thể đặt ngưỡng theo số operations, tuổi UNKNOWN hoặc mức rủi ro nghiệp vụ; không page ngay cho một reply chỉ đến chậm vài giây.

### 12.4. Dead-letter và quarantine

Nếu DLQ/quarantine vượt ngưỡng, tạo alert riêng với **reason code** và audit workflow. Không coi DLQ là backlog đã hoàn tất và cũng không mặc định số DLQ messages bằng số business records: một chunk request có thể chứa nhiều items.

## 13. Dự báo deadline breach dù backlog đang giảm

Một pipeline còn 200.000 work units lúc 06:00, completion rate 100 units/s và deadline publish là 06:15:

~~~text
ETA = 200.000 / 100 = 2.000 giây
    = 33 phút 20 giây

Deadline còn 15 phút
→ nguy cơ trễ dù backlog đang giảm.
~~~

Với snapshot đã **ngừng nạp**, ta có thể xuất custom metric:

~~~text
pipeline_publish_deadline_epoch_seconds
~~~

Một phép kiểm tra ETA mẫu:

~~~promql
(
  pipeline:backlog_pending_work_units
  /
  clamp_min(pipeline:completed_units_per_second:15m, 0.001)
)
>
(
  pipeline_publish_deadline_epoch_seconds - time()
)
~~~

**Giới hạn của phép tính:** Nó bỏ qua in-flight, UNKNOWN, data skew và thời gian reconciliation/publish; nếu throughput thay đổi, ETA cũng thay đổi. Nếu deadline đã trôi qua, vế phải âm và alert nên được xử lý như **deadline already missed**, không diễn giải thành dự báo thông thường.

### Predict_linear

~~~promql
predict_linear(
  pipeline:backlog_pending_work_units[30m],
  1800
) > 10000
~~~

`predict_linear` ngoại suy tuyến tính backlog sau 30 phút; nó **không phải** dự đoán chính xác khi có một lần ingest burst lớn, thay đổi worker count hoặc broker requeue hàng loạt. Dùng để hỗ trợ điều phối và phải kiểm chứng bằng lịch sử workload.

### SLA gắn với business date

Giữa 00:00 và 07:00, một job có thể xử lý nhiều kỳ dữ liệu khác nhau. Deadline cần lấy từ **run registry/manifest/businessDate** đã xác định, không dựa vào local clock của một worker pod hay timestamp `JobExecution` duy nhất. Nếu scheduler miss một kỳ, queue depth có thể bằng 0 nhưng vẫn chưa đáp ứng SLA của kỳ đó.

## 14. Mất telemetry không có nghĩa backlog về 0

~~~text
01:00 exporter ghi backlog=40.000
01:01 poll database timeout
01:02 scrape vẫn hoạt động nhưng số liệu không đổi
01:10 exporter bị kill, metrics series biến mất
~~~

Nếu dashboard điền mọi giá trị missing bằng 0, operator có thể nghĩ batch đã hoàn tất. Cần giám sát:

1. `up` của metrics exporter/Prometheus target.
2. `batch_metrics_last_refresh_epoch_seconds`.
3. Query failures/timeouts của nguồn backlog.
4. Series thiếu so với **inventory các pipelines kỳ vọng**.
5. JobRepository và business outcomes khi telemetry suy giảm.

### Stale refresh

~~~yaml
- alert: BatchBacklogTelemetryStale
  expr: |
    (time() - max by (pipeline, environment) (
      batch_metrics_last_refresh_epoch_seconds
    )) > 180
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Backlog metrics khong duoc refresh cho {{ $labels.pipeline }}"
~~~

Rule hoạt động khi exporter vẫn xuất `last_refresh` cũ. Nếu series **biến mất hoàn toàn**, expression trên không có output; cần thêm target-down hoặc missing-series rule.

~~~yaml
- alert: BatchBacklogExporterMissing
  expr: |
    absent_over_time(
      batch_work_units{
        pipeline="ordersImport",
        environment="prod",
        state="ready"
      }[10m]
    )
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Khong co backlog metric cua ordersImport prod"
~~~

Đây là rule cho **một pipeline cụ thể**. Với nhiều pipelines phát sinh động, phải có danh sách expected pipelines và một công cụ sinh rules hoặc join với inventory metrics; `absent_over_time` không thể tự biết tất cả nhãn từng tồn tại.

## 15. Khung giờ vận hành và planned pauses

Một Batch job chỉ chạy 01:00–06:00. Lúc 22:00 có 100.000 events được chuẩn bị trong queue; workers chưa chạy là **chủ đích**:

~~~text
22:00 pending=100.000, expected_active=0
01:00 pending=100.000, expected_active=1
01:10 pending= 90.000, expected_active=1
~~~

`BatchBacklogGrowing` có thể chỉ bật trong cửa sổ expected active. Nhưng:

- **Missed schedule** vẫn cần alert khi không có JobExecution nào được tạo.
- **Deadline violation** vẫn cần alert ngoài giờ dispatch nếu chưa publish.
- **UNKNOWN hoặc dữ liệu đối soát sai** không được im lặng chỉ vì ban ngày.
- **Telemetry missing** vẫn cần phát hiện khi pipeline dự kiến được theo dõi.

### Chính sách cảnh báo theo ngữ cảnh

| Tình trạng | Hành động |
| --- | --- |
| Planned pause đã duyệt, chưa tới SLA | Không page vì ready backlog tăng |
| Expected active nhưng không có worker | Alert no progress/capacity |
| Đến deadline mà chưa đủ dữ liệu | Page SLA/integrity dù worker tạm dừng |
| Worker downtime do maintenance có lịch | Alertmanager silence có hạn, vẫn có monitoring tối thiểu |
| Exporter chết | Báo thiếu telemetry; không set schedule_active=0 để giấu lỗi |
| Quarantine vượt quality threshold | Cảnh báo data quality riêng |

`pipeline_schedule_active` phải do **run registry/admission policy** cấp, không lấy từ phép `worker_active > 0`. Nếu workers chết, expected active vẫn bằng 1 để alert còn hiệu lực.

### Tránh alert storm

Nếu 24 partitions cùng gặp lỗi DB, đừng gửi 24 trang cảnh báo giống nhau. Gộp theo `environment`, `pipeline` và `dependency`; dùng label `severity`, `owner`. Không gắn mỗi `StepExecutionId`, `sourceKey` hay exception message làm nhãn time series/alert không giới hạn. Có thể dùng Alertmanager grouping/inhibition có kiểm soát, nhưng **không che mất business integrity hoặc SLA incident khác**.

## 16. Runbook phân loại nguyên nhân gốc

~~~mermaid
flowchart TD
    A["Alert backlog tang lien tuc"] --> B{"So lieu co fresh khong?"}
    B -- "Khong" --> E["Sua exporter / scrape / source poll"]
    B -- "Co" --> C{"Ingress tang hay completion giam?"}
    C -- "Ingress tang" --> G["Burst, manifest, capacity & deadline"]
    C -- "Completion giam" --> D{"Workers con active?"}
    D -- "Khong" --> W["Pod/consumer/broker connection"]
    D -- "Co" --> F{"Bottleneck o dau?"}
    F --> DB["DB pool/lock/rollback"]
    F --> API["HTTP 429/timeout"]
    F --> CPU["CPU/heap/GC/disk"]
    F --> BRO["Broker/reply/JobRepository"]
    G --> R["Backpressure/scale co gioi han"]
    W --> R
    DB --> R
    API --> R
    CPU --> R
    BRO --> R
    R --> X["Verify progress + reconciliation"]
~~~

### Ma trận triệu chứng

| Quan sát | Giả thuyết | Kiểm tra |
| --- | --- | --- |
| Ready tăng, consumers=0 | Worker pods không có hoặc mất broker connection | Deployment/readiness, broker consumer count |
| Ready giảm, unacked tăng | Worker nhận request rồi kẹt | P95 chunk duration, DB lock, prefetch, ACK |
| In-flight tăng, reply timeout | Manager chưa nhận kết quả, worker có thể đã commit | Correlation, StepExecution, business ledger |
| Retry-wait tăng và 429/503 nhiều | Downstream bị throttling/outage | HTTP metrics, rate limit, retry budget |
| Rollback/deadlock tăng | Database contention | Connection pool, lock wait, SQL timing |
| CPU cao, network chưa bão hòa | Parse/transform/serialization bottleneck | CPU profile, heap, GC |
| Queue depth nhỏ, UNKNOWN tăng | Work chuyển sang trạng thái chưa xác nhận | Reconciler, external provider status |
| Một partition lâu gấp 10 lần | Input skew / hot key | Input bytes, item count, partition plan |
| Queue empty, chưa publish | Đang kẹt ở projection/reconciliation | Quality gate, inbox, manifests |
| Metric không refresh, log vẫn có worker | Telemetry broken | `up`, last refresh, poll errors |
| Input không có, kỳ này chưa launch | Missed schedule/upstream missing | Run registry, sealed source manifest |

### Trình tự 12 bước cho người trực

1. **Xác nhận metrics fresh** và biết đúng đơn vị queue/partition/items.
2. **Chốt kỳ dữ liệu**: JobInstance, JobExecution, business date, sourceVersion/manifest.
3. **Đọc xu hướng**: pending, slope 5/15/30 phút, ingress/completion rates, oldest age và deadline.
4. **Tách trạng thái**: READY, RETRY_WAIT, IN_FLIGHT, UNKNOWN, DLQ/quarantine, DONE.
5. **Xem worker capacity**: replicas/consumers active, thread pool queue, readiness, GC/CPU/memory.
6. **Xem broker**: ready/unacked/redelivery, consumer lag, reply/correlation timeouts.
7. **Xem JobRepository**: failed/stopped/running StepExecutions, rollback/commit counts và checkpoint.
8. **Xem dependency**: DB pool, locks, API rate limit/429, object storage GET, network.
9. **Khoanh nguyên nhân**: burst hợp lệ, capacity thiếu, hot partition, outage, poison work hoặc missing reply.
10. **Điều tiết an toàn**: scale vừa phải khi downstream còn headroom; giảm dispatch khi dependency nghẽn; sửa root cause.
11. **Xác minh hồi phục**: backlog slope chuyển âm, oldest age giảm, completion rate tăng, UNKNOWN/DLQ không tăng.
12. **Đối soát business outcome trước publish**: nguồn expected, output unique, quarantine và các effects chưa xác nhận.

Không xóa pending messages, không tăng `skipLimit` cho lỗi hạ tầng, không tự sửa bảng `BATCH_*` để ép job `COMPLETED`.

## 17. Vì sao backlog tăng không có nghĩa cứ thêm workers

Giả sử 12 workers đạt 1.000 items/s vì DB đã gần hết khả năng ghi. Tăng lên 24 workers có thể dẫn tới:

~~~text
12 workers -> 1.000 items/s
24 workers ->   900 items/s
              lock waits cao hơn
              rollback/retry tăng
              DB connections cạn
~~~

Nút thắt có thể là CPU, disk I/O, WAL/redo throughput, network, broker, DB lock, API quota, hoặc per-key sequencer. **Tăng concurrency có thể giảm throughput**.

### Điều chỉnh theo bottleneck

| Nút thắt | Quyết định hợp lý |
| --- | --- |
| CPU worker cao, DB/API còn headroom | Tăng workers từng bước |
| DB pool/lock waits tăng | Giảm chunk/worker concurrency, tối ưu query/index |
| API 429/503 tăng | Rate limiting toàn cụm, bounded retry/backoff + jitter |
| Broker request/reply latency cao | Kiểm tra middleware, message size, correlation |
| JobRepository metadata nóng | Giảm tiny partitions/metadata writes; sizing pool |
| Input file lớn không đều | Điều chỉnh partition sizing ở job/snapshot mới có kế hoạch |
| Một key cần strict order | Shard theo key, không ép global FIFO nếu không cần |

### Autoscaling và backpressure

KEDA/HPA có thể scale consumers theo queue depth/lag hoặc custom metrics. Nhưng một burst nạp 1 triệu messages có thể khiến autoscaler tăng pods nhanh trong khi DB không chịu nổi. Cần:

- Max worker concurrency theo **database/API capacity**.
- Graceful drain khi scale down; không coi pod terminated là StepExecution đã hoàn tất.
- Durable queue và ACK semantics rõ để tránh mất work.
- Business idempotency và reconciliation khi redelivery.
- Circuit breaker/health gate để không dispatch thêm vào dependency đang lỗi.
- Metrics theo `worker_active`, `completed_rate` và dependency, không chỉ depth.

### Pseudocode policy

~~~text
if dependency_degraded:
    pause_new_dispatch()
    preserve_durable_pending_work()
elif db_pool_wait_high or api_429_high:
    reduce_dispatch_rate()
elif backlog_slope_positive_sustained and resources_have_headroom:
    scale_workers_gradually()
else:
    keep_capacity()
~~~

Đây là **chính sách ứng dụng**, không phải API mặc định của Spring Batch. Không kill workers ngay khi backlog tăng nếu đang có transaction/external effects chưa rõ.

## 18. Remote chunking: ready queue không đo được reply lost

~~~text
Manager sends C-101, C-102, C-103.
Worker A commits C-101, reply arrives.
Worker B commits C-102, reply lost.
Worker C still processing C-103.

Broker ready depth = 0.
Nhưng C-102 và C-103 chưa có outcome được manager xác nhận.
~~~

Nên instrument:

| Metric | Diễn giải |
| --- | --- |
| `chunk_requests_dispatched_total` | Attempts dispatched theo contract |
| `chunk_replies_correlated_total` | Replies ghép đúng logical request |
| `chunk_requests_unresolved` | Requests chưa có outcome được xác nhận |
| `oldest_chunk_unresolved_age_seconds` | Request chưa xác nhận lâu nhất |
| `chunk_reply_timeouts_total` | Timeouts, không đồng nghĩa business failure |
| `chunk_redeliveries_total` | Delivery lại do broker/adapter |

Không tính unresolved bằng `dispatched_total - replies_total` nếu counters có duplicate replies/redeliveries; cần **correlation identity** và state machine. Một manager timeout sau worker DB commit cần reconciliation, không tự coi chunk là bad data.

### Khác biệt của remote partitioning

Giả sử 200 logical partitions:

~~~text
COMPLETED  = 150
RUNNING    = 20
FAILED     = 5
PENDING    = 25
UNKNOWN    = 0
~~~

`unfinished = 50 partitions` nhưng `ready/pending=25`, `failure recovery=5` và `in-flight=20`. Không xem 150/200 = 75% **records** nếu partitions có kích thước khác nhau. Dùng expected records/bytes theo manifest.

`StepExecutionId` có thể đổi khi restart; phải tổng hợp theo **logical partition key** để không đếm cùng partition nhiều lần. Một partition `FAILED` cũng không tự được xem là READY để bất kỳ worker khác chạy lại ngay nếu external side effects chưa đối soát.

## 19. Structured logs nối backlog với JobRepository

Khi alert firing, log nên có:

~~~text
jobName
jobInstanceId / jobExecutionId
stepName / stepExecutionId
partitionName
sourceVersion / manifestId
workerId / podId
chunkRequestId / correlationId (nếu remote)
errorCode / outcome
elapsedMs
~~~

~~~json
{
  "event": "chunk_reply_timeout",
  "jobName": "ordersImport",
  "jobExecutionId": 502,
  "stepExecutionId": 719,
  "partitionName": "partition-0007",
  "chunkRequestId": "C-101",
  "workerId": "worker-12",
  "outcome": "UNKNOWN",
  "errorCode": "REPLY_TIMEOUT",
  "elapsedMs": 90000
}
~~~

Đây là **schema log custom**. Không mặc định Spring Batch tự xuất các fields này. Local/multi-threaded workers cần bind/cleanup SLF4J MDC đúng thread; remote workers phải tái tạo identity từ `StepExecution`/message envelope, không giả định MDC đi qua broker.

**Không dùng source ID hoặc payload nhạy cảm làm metric labels**; log/audit có quyền truy cập riêng dành cho điều tra business item.

## 20. Kiểm thử metric và alert

### 20.1. Test phân loại backlog

~~~text
READY        = 120
RETRY_WAIT   = 20
IN_FLIGHT    = 35
UNKNOWN      = 3
QUARANTINED  = 2
DONE         = 500

Expected:
  pending_backlog = 140
  ready_backlog   = 120
  unresolved_work = 178
~~~

Mỗi logical work ID phải có đúng một trạng thái được công nhận trong snapshot; redelivery không tạo work ID mới.

### 20.2. Unit test Micrometer publisher

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class BacklogGaugePublisherTest {

    @Test
    void publishSnapshotToGauges() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            BacklogGaugePublisher publisher =
                new BacklogGaugePublisher(
                    registry, "ordersImport", "test");

            publisher.publish(
                new BacklogSnapshot(120, 20, 35, 3, 2, 900),
                1_700_000_000L);

            assertEquals(120.0,
                registry.get("batch_work_units")
                        .tags("pipeline", "ordersImport",
                              "environment", "test",
                              "state", "ready")
                        .gauge().value());

            assertEquals(900.0,
                registry.get("batch_oldest_ready_age_seconds")
                        .tags("pipeline", "ordersImport",
                              "environment", "test")
                        .gauge().value());
        }
    }
}
~~~

Ví dụ cần JUnit 5/Micrometer dependencies. Unit test xác nhận **gauge values**, không chứng minh database snapshot query, scrape endpoint hoặc recording rules chính xác.

### 20.3. Test spike rồi giảm

~~~text
Backlog theo phút:
  0 -> 8.000 -> 7.000 -> 5.000 -> 3.000 -> 1.000 -> 0

Expected:
  Không firing BatchBacklogGrowing chỉ do spike ngắn.
  Age/deadline alert vẫn có thể firing nếu SLA vi phạm.
~~~

### 20.4. Test tăng liên tục

~~~text
Backlog mỗi 5 phút:
  1.000 -> 3.000 -> 5.000 -> 7.000 -> 9.000 -> 11.000

Expected:
  Có đủ samples trong cửa sổ 15 phút.
  Sau for=10m, alert firing khi active window=1.
  Không firing khi thấp hơn absolute threshold.
~~~

### 20.5. Test mất telemetry

- Exporter trả `/metrics` nhưng query database fail: last-refresh không đổi và stale alert firing.
- Exporter bị kill: series biến mất; `up`/absent-series rule firing.
- Dashboard không thay missing values bằng zero.
- Sau recovery, số liệu trở lại và alert resolution đúng.

### 20.6. Ma trận fault injection

| Tình huống | Kỳ vọng |
| --- | --- |
| Hai workers cùng claim work | Không đếm logical work ID hai lần |
| Worker crash trước commit | Work còn đường retry theo state machine |
| Worker commit nhưng ACK/reply mất | UNKNOWN/reconciliation, không đếm request mới |
| Broker redeliver chunk ba lần | Attempts tăng, business effect unique |
| Manager nhận reply lệch thứ tự | Correlation đúng, không tráo outstanding requests |
| Partition restart với StepExecution mới | Logical progress không bị nhân đôi |
| Quarantine nhiều records | Quality backlog tách khỏi ready |
| DB poll exporter fail | Stale telemetry alert, không báo ready=0 giả |
| Job scheduled pause | Capacity alert được suppress, SLA/integrity vẫn có hiệu lực |
| Worker CPU cao và DB còn headroom | Scale từng bước làm slope giảm |
| DB pool saturated | Không tăng worker mù; điều chỉnh dispatch |
| Kafka consumer rebalance | Lag biến động ngắn được lọc bằng `for` |
| Kỳ bị miss scheduler và chưa tạo work | Run registry alert dù queue depth=0 |
| Publish khi còn UNKNOWN | Quality gate chặn |
| Manager StepExecution FAILED | Alert/recovery theo metadata, không coi queue rỗng là xong |

### 20.7. Test Prometheus rules

Trong CI/QA có thể dùng `promtool test rules` với fixtures time-series và expected alert firing. Bài STEP 4 chỉ mô tả cách kiểm thử, **không chạy lệnh test/Gradle**. Đặc biệt cần xác nhận rule không im lặng nếu completion counter chưa từng xuất hiện.

## 21. Bài tập tình huống

Một job Spring Batch đọc **12 triệu đơn hàng** qua RabbitMQ remote chunking, chunk size 200, 32 workers. Đến 02:00:

~~~text
01:30 ready_chunks =  2.000
01:40 ready_chunks =  5.000
01:50 ready_chunks =  8.000
02:00 ready_chunks = 11.000

Manager dispatch      = 40 chunks/s
Workers completed     = 20 chunks/s
Broker unacked        = 5.000
Worker replicas       = 32
DB pool usage         = 100%
DB deadlocks/rollback = tăng liên tục
HTTP 429              = tăng
UNKNOWN outcomes      = 250
Oldest READY age      = 38 phút
Deadline publish      = 06:30
~~~

Nhóm vận hành đề nghị tăng workers lên 80, tăng `skipLimit` và tạo rule `ready_chunks > 5000` ở mỗi lần scrape. Một nhóm khác muốn tắt mọi alert trong giờ maintenance.

**Câu hỏi:**

1. `ready_chunks=11.000` tương đương bao nhiêu business items? Có được nhân đơn giản với chunk size 200 nếu chunk cuối có thể nhỏ hơn?
2. Vì sao completion thấp hơn dispatch khiến backlog tăng, nhưng phép trừ hai counters không luôn bằng số pending chính xác?
3. `unacked=5.000` là backlog kiểu gì và cần alert nào khác?
4. Vì sao tăng 80 workers có thể làm DB và HTTP API tệ hơn?
5. Có 250 UNKNOWN; pending giảm có đủ chứng minh dữ liệu an toàn?
6. Thiết kế `BatchBacklogGrowing` để lọc spike bằng window, slope và `for`.
7. Các alert độc lập nào phải có: no progress, oldest age, SLA, telemetry stale và UNKNOWN?
8. Khi dependency đã bão hòa, phải giảm dispatch hay tiếp tục scale?
9. Dùng những nguồn nào để xác nhận chunk đã commit và worker nào cần restart?
10. Những tests nào bảo đảm exporter chết hoặc lịch bị miss vẫn được cảnh báo?

**Định hướng trả lời:** Queue có đơn vị **chunk requests**, cần metadata/manifest để tính item count. Slope dương liên tục là dấu hiệu tốc độ nạp lớn hơn tốc độ hoàn tất hoặc requeue tăng; DB pool/429 đang báo bottleneck nên **không tăng workers mù**. READY thấp không đồng nghĩa DONE khi còn UNKNOWN/unacked. Xây alert theo **backlog absolute + slope + `for` + schedule**, đồng thời có age/SLA/no progress/telemetry/integrity alerts. Thực hiện backpressure, điều tra DB/API/broker, bảo vệ business idempotency và đối soát trước publish; **không** tăng skipLimit cho lỗi hạ tầng.

## 22. Checklist triển khai production

| Kiểm tra | Tiêu chí đạt |
| --- | --- |
| Đơn vị backlog | Rõ message/chunk/partition/item/byte |
| Source of truth | Biết nguồn, unique work ID và cách tránh duplicate |
| State model | READY/RETRY_WAIT/IN_FLIGHT/UNKNOWN/QUARANTINED/DONE |
| Input snapshot | Expected work và partition identity ổn định |
| Gauge/counter | Phân loại đúng; `deriv` gauge, `rate` counter |
| Alert trend | Absolute threshold + window + `for` |
| Alert tuổi/SLA | Phát hiện backlog cũ dù đang giảm |
| No-progress | Bắt backlog còn nhưng worker không hoàn tất |
| Missing metrics | `up`/last-refresh/absent-series đều được giám sát |
| Schedule | Planned pause không làm tắt SLA/integrity |
| Cardinality | Không nhãn từng item/StepExecution không giới hạn |
| Multi-replica | Không nhân backlog vì `sum` global gauges |
| Dependency | DB/broker/API/worker metrics hiện trên dashboard |
| Retry/restart | Logical work key ổn định và idempotent writer |
| Runbook | Có phân luồng bottleneck và phục hồi an toàn |
| Verification | Reconciliation source/outcomes/publish gate |
| Tests | Spike, trend, stale, redelivery, crash, missed schedule |

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, partitioning và scale.
- [Spring Batch Reference — Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote chunking, remote partitioning và worker.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): observation/metrics trong Batch.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): JobExecution/StepExecution/counters.
- [Spring Batch Reference — Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint và restart.
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer/Actuator.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/): gauges, counters và registries.
- [Prometheus — Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate`, `deriv`, `predict_linear`, `absent_over_time`.
- [Prometheus — Recording Rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/): tạo series aggregate.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): `for`, expr và annotations.
- [Prometheus — Unit Testing for Rules](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/): kiểm thử time-series rules.
- [Alertmanager — Configuration](https://prometheus.io/docs/alerting/latest/configuration/): grouping, silences và inhibition.
- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): ready/unacked semantics.
- [RabbitMQ — Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): ACK/redelivery.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): consumer offsets và lag.
- [KEDA Scalers](https://keda.sh/docs/latest/scalers/): event-driven autoscaling.

> **Ghi nhớ:** **Backlog tăng liên tục** là dấu hiệu công việc nạp nhanh hơn khả năng hoàn tất hoặc work bị kẹt — **không phải lý do tự động tăng worker count**. Định nghĩa đúng đơn vị và trạng thái; quan sát **backlog slope, completion rate, oldest age, deadline và missing telemetry**. Trong Spring Batch phân tán, queue rỗng không chứng minh dữ liệu đúng: cần đối chiếu broker, worker StepExecution, JobRepository, business idempotency ledger và reconciliation trước khi publish.
