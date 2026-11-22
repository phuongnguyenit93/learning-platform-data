# Giám sát lỗi restore, thời gian sẵn sàng và sức khỏe tài nguyên

CRaC giúp Java application phục hồi từ checkpoint nhanh hơn một lần khởi động đầy đủ, nhưng thời gian restore thành công không đồng nghĩa với thời gian ứng dụng có thể nhận traffic. Sau khi process được khôi phục, ứng dụng vẫn có thể phải chạy `afterRestore` callbacks, nạp cấu hình và secret, tạo lại connection pool, kết nối broker, khôi phục worker, kiểm tra dependency và chuyển readiness sang trạng thái chấp nhận request.

Để vận hành đáng tin cậy, cần giám sát riêng ba kết quả:

1. **Restore thành công:** JVM và checkpoint engine khôi phục được process.
2. **Bootstrap sau restore hoàn tất:** callback và các resource bắt buộc đã hoạt động.
3. **Ứng dụng sẵn sàng:** health check đạt yêu cầu và traffic có thể được chuyển tới instance.

Một hệ thống quan sát tốt phải trả lời được: lần restore nào thất bại, thất bại ở phase nào, mất bao lâu để Ready, dependency nào làm chậm quá trình, tài nguyên nào đang cạn và instance có tiếp tục khỏe sau khi bắt đầu phục vụ hay không.

## 1. Phân biệt restore duration và time to ready

Không nên gộp mọi thời gian vào một metric tên `startup_time`. Với CRaC, có nhiều mốc khác nhau.

Có thể định nghĩa các mốc sau:

| Mốc | Ý nghĩa | Nguồn quan sát |
|---|---|---|
| T0 | Container hoặc restore process bắt đầu | Kubernetes Pod/container status, entrypoint log hoặc node agent |
| T1 | JVM bắt đầu thực hiện phần lifecycle sau khi process được khôi phục | Log đầu tiên trong callback hoặc application restore hook |
| T2 | Tất cả `afterRestore` callbacks và bước bootstrap bắt buộc hoàn tất | Application lifecycle event |
| T3 | Readiness chuyển sang `ACCEPTING_TRAFFIC` và probe thành công | Spring Boot availability, Kubernetes condition/EndpointSlice |

Từ đó có thể đo:

- **Engine/process restore time:** T0 đến T1. Khoảng này có thể chỉ đo được từ bên ngoài JVM vì Java code chưa chạy để ghi log.
- **Post-restore bootstrap time:** T1 đến T2. Đo trong application lifecycle.
- **Readiness propagation time:** T2 đến T3. Bao gồm thời gian probe và cập nhật trạng thái trong Kubernetes.
- **Restore-to-ready time:** T0 đến T3. Đây là chỉ số quan trọng nhất đối với khả năng phục vụ của deployment.

Nếu chỉ đo thời gian `afterRestore`, dashboard có thể báo restore mất 200 ms trong khi Pod cần thêm 15 giây mới Ready. Nếu chỉ nhìn Pod Ready timestamp, lại khó xác định phần nào của quá trình đang chậm. Hãy theo dõi cả các phase và tổng thời gian.

### 1.1. Đo thời gian bên trong và bên ngoài process

Trong Java, dùng `System.nanoTime()` hoặc Micrometer `Timer` để đo thời lượng callback và các bước bootstrap. Đây là phép đo monotonic phù hợp cho một khoảng thời gian đang diễn ra.

~~~java
long started = System.nanoTime();

try {
    reconnectDatabase();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    logger.info(
            "restore_step=database_reconnect elapsedMs={}",
            elapsedNanos / 1_000_000);
}
~~~

Để đo T0 đến T1, cần quan sát từ bên ngoài process, ví dụ entrypoint ghi log trước khi gọi JVM restore, container runtime event hoặc telemetry của node. Không giả định Java có thể ghi log trước khi JVM đã được khôi phục.

Không lưu giá trị `System.nanoTime()` vào checkpoint rồi dùng nó để tính thời gian trôi qua trong thời gian process bị dừng. Dùng monotonic clock cho khoảng đo trong cùng một phase đang chạy; nếu cần lưu deadline qua checkpoint, dùng `Instant` hoặc epoch timestamp và xác định rõ chính sách xử lý thời gian đã trôi qua.

### 1.2. Phân biệt cold start và restore

Khi đánh giá lợi ích CRaC, so sánh:

- Cold start: container start đến readiness.
- Restore: container start/restore invocation đến readiness.
- Post-restore callback time.
- Dependency reconnect time.
- Warm-up time sau restore.

So sánh các percentile trên cùng workload, cùng node profile, cùng resource limit và cùng điều kiện dependency. Nếu restore nhanh nhưng reconnect database chậm, tối ưu thêm checkpoint image có thể không cải thiện đáng kể thời gian phục vụ thực tế.

## 2. Phân loại lỗi theo phase

Một restore failure có thể xảy ra trước khi JVM chạy lại, trong callback hoặc sau khi callback thành công. Cần phân loại lỗi để alert tới đúng nhóm chịu trách nhiệm.

| Phase | Ví dụ lỗi | Bằng chứng cần thu thập |
|---|---|---|
| Artifact selection | Checkpoint thiếu file, sai checksum hoặc sai manifest | Artifact ID, checksum, manifest validation |
| Engine restore | CRIU không khôi phục được process, kernel/CPU không tương thích | CRIU log, node fingerprint, container exit code |
| JVM resume | JVM không thể tiếp tục từ image | JVM stderr, JDK vendor/build, CPU feature |
| `afterRestore` callback | Resource callback ném exception hoặc bị timeout | Callback log, resource name, stack trace |
| Runtime configuration | Thiếu config, secret hết hạn, schema không hợp lệ | Config revision, secret provider status |
| Dependency reconnect | Database, broker hoặc partner API không truy cập được | Connection error, timeout, endpoint health |
| Resource initialization | Pool, executor, listener hoặc HTTP server không tạo được | Pool/worker metrics, bind error, resource log |
| Readiness | Ứng dụng không chuyển sang accepting traffic | Availability state, readiness endpoint |
| Post-ready degradation | Heap, thread, file descriptor hoặc queue tăng bất thường | JVM metrics, cgroup metrics, resource saturation |

Dùng một tập giá trị phase và reason có giới hạn, chẳng hạn `engine`, `callback`, `config`, `dependency`, `resource`, `readiness`. Không đưa toàn bộ exception message hoặc URL vào metric label.

### 2.1. Không gộp mọi lỗi thành restore failure

Ví dụ database tạm thời unavailable sau khi JVM đã restore:

- Engine restore: thành công.
- CRaC callback: có thể đang retry hoặc đã hoàn tất một phần.
- Database reconnect: thất bại tạm thời.
- Readiness: vẫn từ chối traffic.
- Liveness: có thể vẫn khỏe nếu process đang tiến triển và có khả năng tự phục hồi.

Nếu ghi tất cả thành `restore_failed`, vận hành sẽ khó phân biệt lỗi checkpoint với lỗi dependency. Ghi nhận phase riêng và chỉ đánh dấu toàn bộ restore attempt là failed khi policy thực tế kết luận không thể tiếp tục.

## 3. Thiết kế log có cấu trúc cho restore lifecycle

Log cần giúp nối các sự kiện từ lúc container bắt đầu restore đến khi Pod Ready. Mỗi sự kiện nên có các trường ổn định:

- `event`: tên sự kiện, ví dụ `restore_started`, `callback_completed`, `readiness_changed`.
- `phase`: engine, callback, configuration, dependency, resource hoặc readiness.
- `checkpoint_id`: ID của artifact được restore.
- `restore_operation_id`: ID của một lần restore.
- `pod_uid` và `container_id`: nhận diện instance trong Kubernetes.
- `node_name` và `node_profile`: nhận diện node/CPU profile.
- `application_version` và `image_digest`.
- `jdk_vendor`, `jdk_version`, `criu_version` khi có.
- `resource`: tên callback/resource nếu sự kiện thuộc một resource.
- `elapsed_ms`: thời lượng bước vừa hoàn tất.
- `result`: success, failure, timeout hoặc retry.
- `error_type`: lớp exception hoặc nhóm lỗi đã chuẩn hóa.
- `config_revision`: revision không nhạy cảm của cấu hình runtime.

Ví dụ log:

~~~json
{
  "timestamp": "2026-11-13T07:10:00.015Z",
  "level": "INFO",
  "event": "restore_step_completed",
  "phase": "dependency",
  "restore_operation_id": "restore-20261113-001",
  "checkpoint_id": "orders-2.4.0-amd64-001",
  "resource": "database-pool",
  "elapsed_ms": 420,
  "result": "success",
  "pod_uid": "pod-uid-example",
  "node_profile": "orders-amd64-v2",
  "config_revision": "runtime-42"
}
~~~

Ví dụ chỉ minh họa schema. ID, version và timestamp phải lấy từ runtime thật. Không ghi password, token, private key, connection string chứa credential, nội dung secret hoặc payload khách hàng.

### 3.1. Các sự kiện lifecycle nên ghi

Một chuỗi sự kiện hữu ích:

~~~text
restore_requested
restore_process_started
restore_engine_completed
after_restore_started
runtime_config_loaded
secrets_loaded
database_reconnected
external_clients_ready
background_workers_resumed
application_ready
~~~

Nếu engine restore thất bại trước khi JVM hoạt động, application log có thể không có `restore_engine_completed`. Khi đó, cần ghép log CRIU/container runtime với Pod Events và exit code.

### 3.2. Dùng log để đo từng bước chậm

Không chỉ ghi `afterRestore completed`. Hãy ghi riêng thời lượng:

- Đọc config.
- Lấy secret.
- Tạo connection pool.
- Kiểm tra database.
- Kết nối message broker.
- Tạo HTTP client.
- Warm-up cache.
- Resume scheduler/worker.
- Health check cuối.

Nếu tổng callback mất 12 giây và database reconnect chiếm 10 giây, dashboard cần cho thấy rõ phần đó. Khi có nhiều callback, ghi cả tên resource và thứ tự thực thi.

## 4. Metrics cốt lõi cho CRaC

Metrics giúp theo dõi xu hướng qua nhiều Pod, checkpoint và node. Nên phân chia thành các nhóm: kết quả restore, thời lượng, callback, readiness, dependency và tài nguyên.

### 4.1. Restore result và failure

Các metric gợi ý:

| Metric | Loại | Ý nghĩa |
|---|---|---|
| `crac_restore_attempts_total` | Counter | Tổng số lần restore được ghi nhận |
| `crac_restore_failures_total` | Counter | Số lần restore thất bại |
| `crac_restore_in_progress` | Gauge | Có restore/bootstrap đang diễn ra hay không |
| `crac_restore_phase_failures_total` | Counter | Lỗi theo phase đã chuẩn hóa |
| `crac_checkpoint_artifact_validation_failures_total` | Counter | Lỗi xác minh artifact trước restore |

Counter failure nên tăng đúng một lần cho mỗi attempt thất bại. Tránh tăng nhiều lần cho cùng một exception vì retry nội bộ; nếu cần quan sát retry, tạo metric riêng như `crac_dependency_retries_total`.

### 4.2. Restore duration và callback duration

| Metric | Loại | Ý nghĩa |
|---|---|---|
| `crac_restore_to_ready_seconds` | Histogram | Thời gian từ T0 đến T3 |
| `crac_engine_restore_seconds` | Histogram | Thời gian engine/process restore |
| `crac_post_restore_bootstrap_seconds` | Histogram | T1 đến T2 |
| `crac_callback_duration_seconds` | Histogram | Thời lượng callback theo resource và phase |
| `crac_dependency_reconnect_seconds` | Histogram | Thời gian reconnect dependency |
| `crac_readiness_transition_seconds` | Histogram | Thời gian từ bootstrap complete đến readiness success |

Dùng histogram để tính p50, p95 và p99 trên nhiều instance. Không chỉ dùng average; một số Pod restore rất chậm có thể bị che khuất bởi giá trị trung bình.

### 4.3. Readiness và thời gian không sẵn sàng

| Metric | Loại | Ý nghĩa |
|---|---|---|
| `application_ready` | Gauge | 1 khi ứng dụng chấp nhận traffic, 0 khi chưa sẵn sàng |
| `application_not_ready_seconds` | Histogram hoặc tổng thời lượng | Thời gian ở trạng thái không Ready |
| `crac_restore_ready_timeout_total` | Counter | Số lần vượt thời hạn readiness |
| `crac_readiness_transitions_total` | Counter | Số lần đổi trạng thái readiness |
| `crac_background_workers_ready` | Gauge | Trạng thái worker bắt buộc |

Với trạng thái Ready, có thể dùng Spring Boot availability state hoặc một gauge do ứng dụng cập nhật. Không tạo một gauge mới cho từng request hoặc từng lần callback.

### 4.4. Callback failure và timeout

Theo dõi:

- Callback đang chạy.
- Callback đã hoàn tất.
- Callback timeout.
- Callback exception theo nhóm.
- Callback duration theo resource.
- Thời gian drain worker và đóng pool.

Metric gợi ý:

~~~text
crac_callback_duration_seconds{phase="afterRestore",resource="database",outcome="success"}
crac_callback_failures_total{phase="beforeCheckpoint",resource="worker",error_type="TimeoutException"}
crac_callback_in_progress{phase="afterRestore",resource="http-client"}
~~~

Chỉ dùng giá trị `resource`, `phase`, `outcome` và `error_type` trong một danh sách giới hạn. Không dùng exception message làm label vì mỗi message có thể khác nhau và tạo cardinality rất lớn.

## 5. Micrometer instrumentation trong Spring Boot

Spring Boot Actuator và Micrometer có thể cung cấp metrics cho Prometheus hoặc backend quan sát khác. Các custom metric giúp đo lifecycle mà metric JVM mặc định không biết.

Ví dụ một recorder:

~~~java
package com.example.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.TimeUnit;

@Component
public class RestoreMetrics {

    private final MeterRegistry registry;
    private final AtomicInteger restoreInProgress = new AtomicInteger();

    public RestoreMetrics(MeterRegistry registry) {
        this.registry = registry;
        Gauge.builder(
                "crac_restore_in_progress",
                restoreInProgress,
                AtomicInteger::get)
                .register(registry);
    }

    public Timer.Sample startTimer() {
        return Timer.start(registry);
    }

    public void setRestoreInProgress(boolean inProgress) {
        restoreInProgress.set(inProgress ? 1 : 0);
    }

    public void recordCallback(
            Timer.Sample sample,
            String phase,
            String resource,
            String outcome) {

        Timer timer = Timer.builder("crac_callback_duration")
                .description("Duration of CRaC resource callbacks")
                .tag("phase", phase)
                .tag("resource", resource)
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry);

        sample.stop(timer);
    }

    public void incrementRestoreFailure(String phase, String reason) {
        Counter.builder("crac_restore_failures")
                .description("Failed CRaC restore attempts")
                .tag("phase", phase)
                .tag("reason", reason)
                .register(registry)
                .increment();
    }

    public void recordRestoreToReady(long elapsedNanos) {
        Timer.builder("crac_restore_to_ready")
                .description("Time from restore invocation to application readiness")
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);
    }
}
~~~

Micrometer chuẩn hóa tên metric theo registry. Ví dụ tên `crac_restore_to_ready` có thể được export thành `crac_restore_to_ready_seconds` trong Prometheus. Hãy kiểm tra tên thực tế tại endpoint metrics của registry đang dùng.

Ví dụ gọi trong callback:

~~~java
@Override
public void afterRestore(
        Context<? extends Resource> context) throws Exception {

    Timer.Sample sample = restoreMetrics.startTimer();
    String outcome = "success";

    try {
        reconnectDatabase();
        restoreHttpClient();
    } catch (Exception failure) {
        outcome = "failure";
        restoreMetrics.incrementRestoreFailure(
                "afterRestore",
                classify(failure));
        throw failure;
    } finally {
        restoreMetrics.recordCallback(
                sample,
                "afterRestore",
                "runtime-dependencies",
                outcome);
    }
}
~~~

Đây là mẫu minh họa. Trong code production, nên ghi callback riêng cho từng resource để biết chính xác bước nào chậm. Nếu callback bị treo vô hạn, khối `finally` không chạy; watchdog hoặc supervisor bên ngoài phải phát hiện trạng thái đó.

### 5.1. Tránh cardinality cao

Không dùng các giá trị sau làm metric label:

- Checkpoint ID duy nhất cho mỗi build hoặc lần dump.
- Restore operation ID.
- Pod UID nếu hệ thống có số lượng instance lớn và không cần phân tích theo từng Pod trong metrics.
- Exception message.
- Full URL hoặc database hostname.
- User ID, tenant ID hoặc request ID.

Các giá trị định danh chi tiết nên đặt trong log hoặc trace. Metrics nên dùng các dimension giới hạn như phase, resource class, outcome, environment và node profile.

### 5.2. Xử lý metric state được khôi phục từ checkpoint

Metrics registry, counter, timer hoặc gauge có thể là object trong heap và được lưu trong checkpoint. Vì vậy, sau restore không mặc định mọi counter bắt đầu từ 0 hoặc mọi timestamp phản ánh lần restore hiện tại.

Cần quyết định semantics cho từng metric:

- Counter nghiệp vụ/lifetime có thể tiếp tục từ giá trị được checkpoint nếu muốn giữ tổng lịch sử.
- Counter theo process/restore attempt nên được khởi tạo theo vòng đời instance hoặc restore generation.
- Gauge về kết nối, active worker, queue size và readiness phải được cập nhật lại từ trạng thái resource thực tế.
- Timestamp kiểu process start hoặc last scrape cần được kiểm tra để tránh phản ánh thời điểm trước checkpoint.
- Exporter/registry phải kết nối lại backend và không giữ trạng thái transport đã hết hiệu lực.

Nếu cùng một checkpoint được restore nhiều lần, mỗi instance có thể bắt đầu từ cùng một snapshot counter. Hãy dùng instance identity phù hợp với Pod/container, hoặc khởi tạo lại nhóm metric process-local sau restore theo policy. Không gắn một restore ID duy nhất vào mọi metric label nếu điều đó làm cardinality tăng không giới hạn.

## 6. Giám sát sức khỏe JVM sau restore

Sau restore, JVM có thể hoạt động nhưng tài nguyên nội bộ đã ở mức gần giới hạn hoặc có trạng thái không còn phù hợp.

### 6.1. Heap và non-heap memory

Theo dõi:

- Heap used, committed và max.
- Metaspace và compressed class space.
- Direct buffer memory.
- Code cache.
- Garbage collection count và pause duration.
- Allocation rate và promotion rate.

Một checkpoint được tạo sau warm-up có thể chứa heap đã tăng do workload chuẩn bị. Sau restore, nếu heap đã gần max, request mới có thể kích hoạt GC liên tục hoặc OutOfMemoryError.

Đừng chỉ nhìn heap percentage ngay sau restore. Quan sát xu hướng trong vài phút sau khi traffic bắt đầu và so sánh với baseline cold start.

### 6.2. Thread và executor

Theo dõi:

- Live thread count.
- Daemon thread count.
- Thread state: RUNNABLE, BLOCKED, WAITING, TIMED_WAITING.
- Executor active count.
- Queue depth.
- Rejected task count.
- Worker start/stop failures.
- Callback duration và lock wait.

Nếu thread count sau restore cao hơn bình thường, có thể callback đã tạo thread mới mà không dừng thread cũ, hoặc executor bị khởi tạo hai lần. Nếu queue depth tăng liên tục, worker có thể chưa resume hoặc dependency đang làm throughput giảm.

### 6.3. Class loading, JIT và GC

Warm-up trước checkpoint có thể làm code cache và JIT state đã được khởi tạo. Sau restore, quan sát:

- JIT compilation activity.
- Code cache usage.
- Class loading count.
- GC pause.
- Safepoint duration.
- CPU usage trong giai đoạn bootstrap.

Không suy luận rằng mọi optimization sẽ luôn được giữ nguyên như mong đợi trên mọi JDK/runtime. Hãy đo trên đúng JDK build và workload.

### 6.4. Native memory và direct buffer

Heap không phản ánh toàn bộ memory của JVM. HTTP client, TLS, Netty, NIO, compression và native library có thể sử dụng native/direct memory.

Theo dõi:

- Direct buffer pool used/capacity.
- Native Memory Tracking nếu đã bật từ lúc JVM khởi động.
- RSS của process/container.
- Cgroup memory usage.
- Memory pressure và OOM kill event.

Nếu direct buffer hoặc native memory tăng mạnh sau restore, kiểm tra client/resource có bị tạo trùng hoặc buffer cũ chưa được giải phóng.

## 7. Giám sát sức khỏe resource và dependency

Readiness có thể thành công nhưng resource vẫn đang ở trạng thái bão hòa. Cần theo dõi health và saturation của từng dependency.

### 7.1. Database connection pool

Với HikariCP, các chỉ số hữu ích gồm:

- Active connections.
- Idle connections.
- Pending threads đang chờ connection.
- Maximum pool size.
- Connection acquisition time.
- Connection timeout count.
- Connection creation/validation failures.

Sau restore, pool cần được tạo lại hoặc xác minh theo lifecycle đã thiết kế. Nếu active connections bằng 0 ngay sau restore có thể chỉ là chưa có traffic; nếu pending threads tăng liên tục thì pool có thể không đáp ứng tải.

Không đánh dấu pool khỏe chỉ vì object DataSource tồn tại. Kiểm tra khả năng cấp connection và query nhẹ có timeout.

### 7.2. HTTP client và external service

Theo dõi:

- Số connection đang mở/available/pending.
- TLS handshake failures.
- DNS resolution errors.
- Connect/read/request timeout.
- Retry count và backoff.
- Request error rate và latency.

Connection được restore trong heap có thể không còn hợp lệ ở phía server. Client phải reconnect hoặc validate connection theo lifecycle. Không để health indicator tạo hàng loạt request tới partner API trên mỗi probe.

### 7.3. Message broker và consumer

Theo dõi:

- Consumer connected/registered.
- Partition assignment hoặc subscription state.
- Consumer lag.
- Message in-flight.
- Ack/nack/retry rate.
- Lease/session expiry.
- Rebalance duration.
- Duplicate processing hoặc idempotency conflict.

Một consumer object tồn tại không chứng minh broker vẫn coi nó là consumer hợp lệ. Sau restore, xác thực session/lease và quan sát lag trước khi coi worker đã sẵn sàng.

### 7.4. Background worker và scheduler

Theo dõi:

- Số worker active.
- Queue depth.
- Thời điểm job thành công gần nhất.
- Next scheduled run.
- Missed-run/catch-up count.
- Retry backlog.
- Task duration và failure count.

Readiness của HTTP server không tự chứng minh scheduler hoặc consumer đã hoạt động. Nếu worker là một phần của khả năng phục vụ, đưa trạng thái của nó vào readiness policy hoặc một health group riêng.

## 8. File descriptor, socket, filesystem và tài nguyên Linux

Một JVM có thể có heap bình thường nhưng gặp lỗi vì tài nguyên hệ điều hành.

Các chỉ số cần quan sát:

| Tài nguyên | Dấu hiệu bất thường |
|---|---|
| File descriptor | Open FD tiến gần `ulimit -n` hoặc giới hạn container |
| Socket | Nhiều connection ở trạng thái CLOSE_WAIT/TIME_WAIT, lỗi bind |
| Disk/ephemeral storage | Checkpoint, log hoặc temp file làm đầy volume |
| Inode | Không còn inode để tạo file mới |
| Cgroup memory | Memory usage gần limit hoặc OOM event |
| CPU throttling | Container bị giới hạn CPU trong bootstrap |
| PID/thread limit | Không tạo thêm worker thread hoặc process |
| Mount/volume | File không tồn tại, permission denied hoặc volume unavailable |

Trên Linux, một số lệnh kiểm tra:

~~~bash
cat /proc/self/limits
ls /proc/<PID>/fd | wc -l
cat /proc/<PID>/status
df -h
df -i
~~~

Trong Kubernetes:

~~~bash
kubectl describe pod <POD_NAME>
kubectl describe node <NODE_NAME>
kubectl top pod <POD_NAME>
kubectl top node <NODE_NAME>
~~~

Metric process và cgroup cần được thu thập từ đúng container/cgroup. Số liệu trên host không phải lúc nào cũng phản ánh giới hạn mà Pod thực sự chịu.

## 9. Readiness, liveness và resource health

Không nên dùng một health endpoint duy nhất để biểu diễn mọi loại sức khỏe.

Có thể chia thành các nhóm:

- **Liveness:** JVM/process còn tiến triển và có khả năng tự phục hồi.
- **Readiness:** request cần thiết có thể được phục vụ tại thời điểm hiện tại.
- **Startup/restore completion:** các bước bootstrap bắt buộc đã hoàn tất.
- **Dependency health:** trạng thái database, broker, secret provider và external API.
- **Resource health:** memory, thread, file descriptor, queue và pool có nằm trong giới hạn vận hành không.

Ví dụ, database đang tạm thời unavailable:

- Liveness: UP.
- Readiness: DOWN nếu mọi request quan trọng cần database.
- Dependency health: database DOWN.
- Restore completion: có thể COMPLETE nếu ứng dụng đã restore và có thể chờ reconnect.

Ví dụ, heap gần ngưỡng cảnh báo nhưng request vẫn hoạt động:

- Liveness: UP.
- Readiness: có thể UP nếu chưa vượt ngưỡng ảnh hưởng khả năng phục vụ.
- Resource health: DEGRADED.
- Alert: phát cảnh báo memory pressure.

Không đưa mọi resource warning vào liveness. Một metric vượt ngưỡng cảnh báo chưa chắc cần restart container.

### 9.1. Spring Boot Actuator health indicator

Có thể tạo health indicator riêng cho trạng thái restore:

~~~java
package com.example.health;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class RestoreHealthIndicator implements HealthIndicator {

    private final RestoreState restoreState;

    public RestoreHealthIndicator(RestoreState restoreState) {
        this.restoreState = restoreState;
    }

    @Override
    public Health health() {
        if (restoreState.isInProgress()) {
            return Health.down()
                    .withDetail("phase", restoreState.phase())
                    .build();
        }

        if (restoreState.hasFailed()) {
            return Health.down()
                    .withDetail("phase", restoreState.phase())
                    .withDetail("errorType", restoreState.errorType())
                    .build();
        }

        return Health.up()
                .withDetail("phase", "complete")
                .build();
    }
}
~~~

Đây là ví dụ về một health indicator; cần quyết định group nào include nó. Nếu indicator được đưa vào readiness group, Pod sẽ không nhận traffic khi restore chưa xong. Không nhất thiết đưa nó vào liveness group.

Health response public/internal nên giới hạn detail. Chỉ expose exception class hoặc phase đã chuẩn hóa; không trả message chứa credential hay URL nội bộ.

### 9.2. Cập nhật availability state

Spring Boot có thể dùng `AvailabilityChangeEvent` để chuyển readiness:

~~~java
publisher.publishEvent(
        new AvailabilityChangeEvent<>(
                this,
                ReadinessState.REFUSING_TRAFFIC));

// Sau khi config, dependency và resource bắt buộc sẵn sàng:
publisher.publishEvent(
        new AvailabilityChangeEvent<>(
                this,
                ReadinessState.ACCEPTING_TRAFFIC));
~~~

Sau restore, giữ `REFUSING_TRAFFIC` trong lúc callback và bootstrap còn chạy. Chỉ chuyển trạng thái sau khi resource bắt buộc được xác minh. Health indicator bổ sung giúp quan sát chi tiết; availability state điều khiển kết quả readiness.

## 10. Theo dõi restore trên Kubernetes

Kubernetes cung cấp trạng thái Pod, container, Events, restart count và EndpointSlice. Kết hợp các nguồn này để phân biệt restore failure với readiness delay.

### 10.1. Pod conditions và container status

~~~bash
kubectl get pod <POD_NAME> -o wide
kubectl describe pod <POD_NAME>
kubectl get pod <POD_NAME> -o json
~~~

Quan sát:

- `PodScheduled`.
- `Initialized`.
- `ContainersReady`.
- `Ready`.
- Container `state`, `lastState`, `restartCount`.
- `startedAt`, `finishedAt` nếu có.
- Reason/message của container termination.
- Probe failure và Events.

`Pod Ready` là trạng thái Kubernetes tổng hợp từ readiness của container và các điều kiện liên quan. Nó không cho biết callback nào làm chậm; cần ghép với application log và metrics.

### 10.2. Xác nhận Pod đã vào Service endpoints

~~~bash
kubectl get endpointslices \
  -l kubernetes.io/service-name=<SERVICE_NAME> \
  -o yaml
~~~

Kiểm tra `conditions.ready` của endpoint. Khi readiness thất bại, endpoint không được xem là Ready để nhận traffic mới qua Service theo cấu hình thông thường.

Nếu ứng dụng đã log `application_ready` nhưng EndpointSlice chưa cập nhật, có thể có độ trễ propagation hoặc cấu hình Service/Pod khác. Đo riêng khoảng T2 đến T3 để phát hiện trường hợp này.

### 10.3. Thu thập log khi container restart

~~~bash
kubectl logs <POD_NAME> -c app
kubectl logs <POD_NAME> -c app --previous
kubectl get events --sort-by=.lastTimestamp
~~~

`--previous` hữu ích khi container đã restart và log của instance trước vẫn còn. Nếu engine restore thất bại trước khi Java log được khởi tạo, lấy cả container stderr, CRIU log và node/runtime diagnostics.

## 11. Dashboard vận hành cho CRaC

Một dashboard nên được sắp xếp theo câu hỏi mà người vận hành cần trả lời.

### 11.1. Hàng tổng quan

Hiển thị:

- Tổng số restore attempts trong khoảng thời gian.
- Restore success rate.
- Restore failure count theo phase.
- p50/p95/p99 restore-to-ready.
- Số Pod đang restore.
- Số Pod chưa Ready.
- Số Pod restart loop.
- Số node profile có restore failure.

### 11.2. Hàng lifecycle

Biểu đồ theo thời gian cho:

- Engine restore duration.
- `afterRestore` total duration.
- Callback duration theo resource.
- Runtime config/secret load duration.
- Database reconnect duration.
- Broker/client reconnect duration.
- Readiness propagation time.

Dùng stacked breakdown hoặc heatmap để nhận ra phase nào chiếm phần lớn thời gian.

### 11.3. Hàng JVM và resource

Hiển thị:

- Heap used/max và GC pause.
- Non-heap/direct memory.
- Live/blocked thread count.
- Executor active/queue/rejected.
- Database pool active/idle/pending.
- HTTP client connections/pending.
- Open file descriptors.
- Container memory/CPU/throttling.
- Ephemeral storage.
- Message consumer lag.

### 11.4. Hàng node và compatibility profile

Hiển thị:

- Node architecture.
- CPU profile/feature label.
- Kernel version.
- CRIU version.
- Container runtime.
- Restore success rate theo node profile.
- Restore-to-ready percentile theo profile.
- Lỗi tập trung trên một node hoặc một loại hardware.

Dashboard theo profile giúp phát hiện checkpoint chỉ lỗi trên nhóm node có CPU/kernel/runtime khác. Không đưa node name hoặc Pod UID thành label của mọi metric nếu số lượng lớn; dùng log/tracing hoặc dashboard drill-down cho chi tiết instance.

## 12. Alerting và SLI/SLO

Alert nên phản ánh ảnh hưởng tới người dùng hoặc rủi ro vận hành, không chỉ một lần probe thất bại.

Các tín hiệu đáng quan tâm:

- Restore failure tăng đột biến.
- p95/p99 restore-to-ready vượt budget.
- Pod không Ready quá thời hạn.
- Callback đang chạy quá lâu.
- Readiness flapping liên tục.
- Database pool pending hoặc connection timeout tăng.
- Thread count/FD/memory tăng gần giới hạn.
- Consumer lag tăng sau restore.
- Nhiều Pod cùng restart hoặc cùng lỗi trên một node profile.

### 12.1. Định nghĩa SLI

Ví dụ SLI cho restore:

- **Restore success rate:** số restore attempts thành công chia cho tổng attempts.
- **Restore-to-ready latency:** thời gian từ restore invocation đến readiness success.
- **Readiness availability:** tỷ lệ thời gian instance đủ điều kiện nhận traffic.
- **Post-restore stability:** tỷ lệ instance không restart hoặc không rơi khỏi readiness trong một cửa sổ sau restore đã định nghĩa.

Đặt SLO dựa trên workload và yêu cầu phục vụ thực tế. Ví dụ, có thể đặt mục tiêu p95 restore-to-ready dưới một budget nhất định và tỷ lệ restore thành công trên một ngưỡng. Không sao chép con số từ môi trường khác nếu chưa đo baseline.

### 12.2. Ví dụ PromQL

Giả sử metric histogram được export với suffix `_bucket`:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(crac_restore_to_ready_seconds_bucket[15m])
  )
)
~~~

Tỷ lệ lỗi trong một cửa sổ:

~~~promql
sum(rate(crac_restore_failures_total[10m]))
/
clamp_min(sum(rate(crac_restore_attempts_total[10m])), 1)
~~~

Số lần restore failure:

~~~promql
increase(crac_restore_failures_total[15m])
~~~

Callback đang chạy quá lâu, nếu gauge ghi nhận trạng thái callback và có metric start age riêng:

~~~promql
crac_callback_in_progress == 1
and
crac_callback_elapsed_seconds > 30
~~~

Các tên metric là ví dụ. Đảm bảo metric có đúng semantics và label trước khi sử dụng trong alert. Không chia counter failure cho attempt counter nếu một attempt có thể ghi nhận nhiều failure event; hãy định nghĩa rõ cách tăng counter để mẫu số và tử số cùng đơn vị.

### 12.3. Alert theo nhiều mức

| Mức | Ví dụ điều kiện | Hành động |
|---|---|---|
| Warning | p95 restore-to-ready tăng so với baseline | Kiểm tra phase chậm và node profile |
| Warning | Callback vượt budget nhưng chưa timeout | Thu thread dump hoặc xem resource metrics |
| Critical | Restore attempt thất bại liên tiếp | Dừng rollout, giữ artifact/node profile ổn định |
| Critical | Pod chưa Ready vượt SLO và không tiến triển | Kiểm tra callback, dependency và probe |
| Critical | Memory/FD gần giới hạn hoặc OOM kill | Điều tra leak, resource limit và concurrency |
| Critical | Nhiều node cùng profile restore fail | Kiểm tra compatibility, CRIU và kernel change |

Không alert chỉ vì một lần readiness fail ngắn trong lúc bootstrap bình thường. Kết hợp duration, failure count, restart count và ảnh hưởng tới số replica Ready.

## 13. Phát hiện readiness flapping và resource degradation

Một Pod có thể chuyển Ready/NotReady nhiều lần sau restore vì dependency chập chờn hoặc pool bị bão hòa.

Theo dõi:

- Số lần availability transition trong cửa sổ.
- Thời gian liên tục ở NotReady.
- Tỷ lệ request error và latency khi Ready.
- Pool pending và acquisition timeout.
- Worker queue depth và rejected tasks.
- Consumer lag và reconnect count.

Readiness flapping có thể làm EndpointSlice thay đổi liên tục, phân phối traffic không ổn định và tạo thêm tải lên các Pod còn lại. Cần xác định nguyên nhân trước khi chỉ tăng probe threshold.

Resource degradation có thể xảy ra mà readiness vẫn UP. Ví dụ heap 90%, GC pause tăng và request latency xấu đi nhưng health endpoint vẫn trả 200. Vì vậy, health endpoint không thay thế metrics saturation và alert.

## 14. Tracing các bước bootstrap sau restore

Distributed tracing có thể giúp phân tích chuỗi reconnect khi ứng dụng có nhiều dependency. Tạo một trace hoặc span mới cho mỗi restore attempt, với các child span:

~~~text
crac.restore.bootstrap
  ├── load.runtime-config
  ├── load.secrets
  ├── reconnect.database
  ├── reconnect.message-broker
  ├── create.http-client
  ├── warmup.required-cache
  ├── resume.background-workers
  └── publish.application-ready
~~~

Gắn các attribute có ích:

- `checkpoint.id`
- `restore.operation`
- `restore.phase`
- `application.version`
- `node.profile`
- `resource.name`
- `outcome`

Không gắn secret, full credential URL hoặc payload nhạy cảm. Giới hạn sampling và retention để tránh mỗi lần restore tạo quá nhiều trace.

Không giữ một span đang mở xuyên qua checkpoint rồi kỳ vọng trace exporter tiếp tục gửi đúng sau restore. Trước checkpoint, flush hoặc kết thúc span phù hợp; sau restore, tạo trace mới cho phase mới và nối quan hệ bằng checkpoint/operation correlation ID nếu tracing backend hỗ trợ link.

## 15. Phân biệt metric lỗi của ứng dụng và lỗi của checkpoint engine

Có trường hợp application log không có bất kỳ callback event nào vì process image chưa được khôi phục. Nếu chỉ dựa vào Micrometer, dashboard có thể không ghi nhận failure.

Cần thu thập dữ liệu ở nhiều lớp:

| Lớp | Dữ liệu |
|---|---|
| Pipeline/artifact store | Checkpoint ID, checksum, manifest, validation result |
| Kubernetes | Pod events, scheduling, restart count, node assignment |
| Container runtime | Container start/exit, image digest, runtime error |
| CRIU/CRaC engine | Dump/restore logs, error code, kernel/CPU diagnostic |
| JVM/application | Callback logs, exception, bootstrap duration |
| Metrics backend | Restore attempts, readiness, JVM/resource metrics |
| Node monitoring | Kernel, memory pressure, CPU, disk, cgroup |

Nếu `restore_requested` có trong orchestrator nhưng không có `after_restore_started`, hãy kiểm tra engine/runtime trước khi tìm lỗi trong application callback.

## 16. Kiểm thử observability và failure scenarios

Instrumentation chỉ hữu ích nếu được kiểm chứng trong các tình huống thực tế.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Restore thành công bình thường | Có đủ mốc T0–T3 và restore-to-ready duration |
| Callback ném exception | Failure counter tăng đúng một lần và log có phase/resource |
| Callback bị treo | Watchdog phát hiện, elapsed tăng và có thread dump |
| Database unavailable | Dependency failure được phân loại riêng, readiness theo policy |
| Secret provider timeout | Không log secret; có timeout và reason chuẩn hóa |
| Resource pool không khởi tạo | Callback/resource failure được ghi nhận |
| Readiness không chuyển | Pod vẫn NotReady và có alert theo budget |
| Pod restart sau restore | `--previous` logs và restore attempt identity nối được |
| Memory/FD thiếu | Metrics và node/container events chỉ ra giới hạn |
| Restore trên node profile khác | Dashboard tách được lỗi theo profile |
| Nhiều Pod restore đồng thời | Không tạo connection burst hoặc memory pressure ngoài dự kiến |
| Restore lặp lại cùng checkpoint | Metric counter/instance identity không gây hiểu sai |

### 16.1. Kiểm tra metric semantics

Đối chiếu số lần restore trong application log với `crac_restore_attempts_total` và `crac_restore_failures_total`. Kiểm tra histogram count có khớp số attempt hoàn tất hay không.

Nếu metric registry được khôi phục từ checkpoint, thử restore cùng artifact nhiều lần và quan sát counter, process start timestamp, gauge và exporter state. Xác nhận dashboard không hiểu nhầm giá trị được phục hồi là dữ liệu mới của attempt hiện tại.

### 16.2. Kiểm tra alert

Trong staging, mô phỏng:

- Restore duration vượt budget.
- Callback chậm.
- Dependency reconnect fail.
- Readiness giữ false.
- Memory pressure hoặc worker queue tăng.

Xác nhận alert tới đúng nhóm và chứa đủ checkpoint ID, phase, Pod/node identity trong log hoặc link dashboard để điều tra.

## 17. Runbook khi restore chậm hoặc thất bại

Khi nhận alert, xử lý theo trình tự:

1. Xác định checkpoint ID, restore operation ID, Pod UID và node.
2. Xem Pod Events, container exit code, restart count và trạng thái Ready.
3. Kiểm tra restore engine log để xác định process có được khôi phục hay không.
4. Nếu có `afterRestore start` nhưng chưa complete, xem callback/resource cuối cùng và lấy thread dump.
5. So sánh T0–T3 để xác định engine, callback, dependency hay readiness propagation đang chiếm thời gian.
6. Kiểm tra config revision, secret provider và dependency endpoint.
7. Kiểm tra heap, GC, thread, executor queue, pool, FD, cgroup memory/CPU và disk.
8. So sánh node fingerprint/profile nếu lỗi chỉ xảy ra trên một nhóm node.
9. Giữ Pod NotReady khi dependency bắt buộc chưa hoạt động.
10. Dừng rollout nếu lỗi lặp lại trên nhiều instance; thu thập artifact/manifest/log trước khi thử lại.
11. Chỉ chuyển sang cold start hoặc checkpoint khác theo recovery policy đã được kiểm thử.

Không restart hàng loạt chỉ vì database tạm thời unavailable. Không tăng timeout probe để che callback deadlock. Nếu checkpoint artifact hoặc node profile không tương thích, sửa nguồn gốc hoặc chọn artifact/profile đã xác minh.

## 18. Checklist vận hành

Trước khi đưa checkpoint vào production, xác nhận hệ thống có thể:

- [ ] Ghi nhận checkpoint ID và restore operation ID.
- [ ] Phân biệt engine restore, callback, dependency và readiness failure.
- [ ] Đo được restore-to-ready và từng phase duration.
- [ ] Có callback start/complete/error log.
- [ ] Có metrics attempt, failure, duration và in-progress.
- [ ] Có readiness state phản ánh đúng dependency bắt buộc.
- [ ] Theo dõi heap, GC, direct/native memory và thread.
- [ ] Theo dõi database pool, HTTP client, broker và worker queue.
- [ ] Theo dõi FD, socket, disk, cgroup memory và CPU throttling.
- [ ] Có dashboard theo node/CPU/runtime profile.
- [ ] Có alert theo SLO và failure budget.
- [ ] Có runbook lấy log, thread dump và CRIU diagnostics.
- [ ] Kiểm thử counter/gauge semantics sau nhiều lần restore.
- [ ] Không đưa secret hoặc high-cardinality ID vào metric label.
- [ ] Có canary restore và smoke test trước rollout rộng.

## 19. Nguyên tắc thiết kế observability cho CRaC

Giám sát CRaC cần bao quát cả process restore và khả năng phục vụ sau restore. Hãy đo riêng engine restore, callback/bootstrap, dependency reconnect và readiness propagation; ghi log có cấu trúc để nối sự kiện theo checkpoint và restore attempt; dùng metrics histogram để theo dõi percentile; và giám sát cả JVM lẫn resource của hệ điều hành.

Một Pod chỉ nên được xem là sẵn sàng khi các dependency bắt buộc và resource cần cho request đã hoạt động. Đồng thời, readiness không thay thế liveness, và health endpoint không thay thế metrics saturation. Database có thể unavailable trong khi process vẫn sống; heap có thể gần giới hạn trong khi readiness vẫn UP; consumer có thể chưa resume dù HTTP server đã Ready. Cần có tín hiệu riêng cho từng trạng thái.

Khi restore chậm hoặc thất bại, dashboard và log phải chỉ ra phase cuối cùng đã hoàn tất, node/profile đang chạy, resource nào đang chờ và liệu process có tiến triển hay không. Khi có đủ dữ liệu này, đội vận hành có thể phân biệt lỗi checkpoint engine, callback bị treo, dependency chậm và resource exhaustion, rồi chọn đúng cách xử lý mà không restart hoặc rollback thiếu căn cứ.

## 20. Tài liệu tham khảo

- [CRaC: Implementing the CRaC API](https://crac.org/use/implement-crac/): quản lý resource trước checkpoint và sau restore.
- [CRaC: Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/): cấu hình và thực hiện checkpoint/restore.
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): tích hợp Micrometer và metric trong Spring Boot.
- [Spring Boot Actuator — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): readiness/liveness health groups.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo thời lượng và histogram.
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): đếm sự kiện.
- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/): percentile và latency distribution.
- [Kubernetes — Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): Pod conditions và container lifecycle.
- [Kubernetes — Configure liveness, readiness and startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): hành vi probe và cấu hình.

