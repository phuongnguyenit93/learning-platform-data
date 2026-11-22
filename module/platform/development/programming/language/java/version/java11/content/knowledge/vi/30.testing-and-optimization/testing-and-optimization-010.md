# Dựa vào nhiều nguồn bằng chứng trước khi xác định nguyên nhân — Kiểm thử và tối ưu Java 11+

## 1. Triệu chứng, giả thuyết và nguyên nhân được kiểm chứng

Trong quá trình tối ưu ứng dụng Java 11, một request chậm có thể liên quan **GC pause**, CPU thiếu, queue chờ executor, database connection pool, lock contention, network retry, truy vấn SQL hoặc một thay đổi deployment. Chỉ dựa vào **một biểu đồ latency**, một dòng log hoặc một thread dump rất dễ dẫn đến cách sửa sai.

Ví dụ, p99 HTTP latency tăng cùng lúc heap usage tăng. Điều đó **không đủ** để kết luận GC làm chậm ứng dụng: traffic spike có thể khiến hàng đợi dài hơn, trong khi backlog giữ nhiều object sống, làm cả heap usage **và** latency cùng tăng. Hai hiện tượng có thể cùng do **nguyên nhân thứ ba**, chứ không nhất thiết hiện tượng này gây ra hiện tượng kia.

**Nguyên tắc:** đối chiếu **nhiều nguồn bằng chứng** (triangulation) trong **cùng cửa sổ thời gian, cùng instance, cùng workload** trước khi xác định nguyên nhân; từ quan sát đến giả thuyết, từ giả thuyết đến phép kiểm chứng có khả năng bác bỏ.

| Cấp độ | Phát biểu | Tính chất |
| --- | --- | --- |
| **Triệu chứng** | “p95 latency tăng từ 20 lên 90 ms” | Số đo đã quan sát |
| **Tương quan** | “queue wait cũng tăng trong cùng cửa sổ” | Gợi ý hướng điều tra, chưa là nhân quả |
| **Giả thuyết** | “Executor queueing đang đóng góp vào tail latency” | Có thể đúng hoặc sai; cần test |
| **Nguyên nhân đã được xác nhận trong phạm vi thử nghiệm** | “Ở cùng tải, khi xử lý đúng bottleneck và đo lại, queue wait/latency giảm lặp lại, errors/CPU/DB không xấu đi” | Có bằng chứng can thiệp, phạm vi và giới hạn rõ |
| **Điều chưa biết** | “Chưa có dữ liệu CPU throttling của node B” | Phải ghi rõ, không giả làm đã đo |

**Correlation ≠ causation.** Dữ liệu bổ trợ nhau không có nghĩa luôn độc lập: hai dashboard có thể lấy từ **cùng một counter**. Một giả thuyết tốt cần xác định trước **dữ liệu nào sẽ làm nó kém tin cậy**, không chỉ gom số liệu ủng hộ.

## 2. Những nguồn bằng chứng quan trọng

| Nguồn | Câu hỏi trả lời tốt | Hạn chế cần nhớ |
| --- | --- | --- |
| **Service metrics** | Khi nào chậm, endpoint nào, p95/p99 latency, throughput, error rate, queue depth | Tổng hợp có thể che request hiếm; không tự cho biết method chậm |
| **Distributed traces** | Request đi qua bước nào, mỗi span mất bao lâu, nằm trên critical path không | Bị sampling; spans có thể thiếu hoặc chồng lấn |
| **Structured logs** | Lỗi gì, retry, timeout, deployment ID, request/trace ID nào | Log thiếu context, bị drop hoặc logging tạo overhead |
| **Java Flight Recorder (JFR)** | GC, monitor contention, thread park, socket/file I/O, allocation, method profiling | Event disabled/threshold/sampling; không phải mọi event đều có |
| **GC và safepoint logs** | JVM dừng ứng dụng trong khoảng nào, pause duration, heap behavior | GC cùng lúc không nhất thiết là nguyên nhân |
| **Thread dumps/ThreadMXBean** | Thread đang đợi/chạy gì, monitor owner, deadlock candidate | Snapshot đơn lẻ không là timeline |
| **OS/container metrics** | CPU throttling, RSS, I/O wait, page faults, network retransmissions, CPU quota | Không tự chỉ ra business method nào chịu trách nhiệm |
| **DB/HTTP downstream telemetry** | Query execution, connection acquire wait, remote response, retry/429/5xx | DB client span có thể chứa phần không ở DB engine |
| **Deployment/config history** | Phiên bản, feature flag, JDK patch, pool size, traffic changes | Thay đổi gần sự cố chưa chắc là nguyên nhân |

Dùng **RED** (*Rate, Errors, Duration*) để xác định vấn đề người dùng thấy và **USE** (*Utilization, Saturation, Errors*) để xem tài nguyên có nghẽn. Ví dụ: request p95 tăng; thread pool có 8/8 workers bận; queue depth=42; database query p95 ổn định. Đó là **dấu hiệu cần điều tra queue**, chưa đủ kết luận vì workers có thể đang chờ một dependency khác.

**Không có một nguồn “phản ánh toàn bộ sự thật”.** Metrics có độ phân giải lấy mẫu; tracing có sampling; logs có thể thiếu request ID; JFR có event thresholds; thread dumps là lát cắt; OS telemetry có scope container/host khác JVM. Đối chiếu có giá trị vì các nguồn bù cho những hạn chế đó.

## 3. Định nghĩa chính xác câu hỏi trước khi thu thập

Trước khi bật profiler hay chỉnh JVM flags, viết một câu hỏi đo được:

> Trong 15 phút sau khi deploy, p95 latency của một API tăng từ 45 lên 220 ms ở ba pods, với request rate gần như không đổi. Thời gian tăng nằm ở queue, database, GC hay network, và có liên quan phiên bản deploy mới không?

Một bản khai báo sự cố tốt gồm:

- **Impact/SLO:** endpoint, job type, tỷ lệ request ảnh hưởng, p95/p99, error/timeout rate, throughput, user-facing consequences.
- **Phạm vi:** application version, region/AZ, pod/host, JDK vendor/build, container image digest, CPU/memory quota, GC và heap flags.
- **Thời điểm:** bắt đầu, kéo dài, kết thúc, timezone/UTC, các mốc deploy/scale/restart/feature flag.
- **Baseline:** dữ liệu cùng endpoint và **workload tương đương**, trước thay đổi; phân biệt traffic mix, payload sizes, cache warm-up.
- **Control group:** requests/pods bình thường trong cùng điều kiện để so sánh với nhóm lỗi.
- **Data quality:** sample counts, scrape interval, sampling rate, số spans/logs bị drop, request timeouts bị loại khỏi histogram hay không.

Không so sánh p99 của 100 req/s hôm qua với p99 của 10.000 req/s hôm nay rồi quy toàn bộ khác biệt cho JDK upgrade. Cũng không loại các requests timeout khỏi báo cáo để p95 nhìn đẹp hơn: **error rate và latency phải được xem cùng nhau**.

## 4. Đồng bộ nguồn bằng chứng theo thời gian và ID

Dữ liệu phải được ghép trên **cùng bản triển khai, cùng pod, cùng time window và cùng request** nếu truy nguyên một request cụ thể.

```text
Cửa sổ          bình thường          chậm          phục hồi
-----------------------------------------------------------------
HTTP p95            22ms              92ms            24ms
Executor queue p95   4ms              75ms             5ms
DB query p95        13ms              13ms            12ms
GC pause p99         4ms               4ms             4ms
Active workers      3/8               8/8             4/8
Queue depth          0                42               2
Trace chậm: request -> enqueue -> [chờ] -> worker -> DB -> response
```

**Đây là bảng minh họa, không phải dữ liệu production.** Nó gợi ý nhìn vào executor queue. Tuy nhiên queue cũng có thể tăng **do** workers mắc kẹt ở DB/network, nên phải xác minh nội dung work trên workers.

### Timestamp vs duration

- **UTC wall-clock timestamp** để ghép metrics/logs/traces/JFR giữa hệ thống; kiểm tra clock skew/NTP.
- **`System.nanoTime()`** để lấy **hiệu hai mốc** trong một JVM, phù hợp đo duration ngắn. Không dùng `System.currentTimeMillis()` làm timer vì clock có thể bị chỉnh.
- Timestamp khi exporter **ingest** log khác timestamp event xảy ra. Scrape interval và buffering có thể làm lệch biểu đồ vài giây.
- Không suy thứ tự thực giữa hai services từ wall clock khi host clocks lệch; dùng trace parent/child, protocol events, request IDs và clock corrections.
- Correlation ID/trace context phải **được truyền qua async boundaries và downstream**. ThreadLocal/MDC ở thread nhận request không tự động chuyển sang thread pool.

Ví dụ đo enqueue-to-start và worker execution time trên Java 11 (**mã minh họa** cần biến `executor`, `task`, metrics recorder):

```java
long submittedAt = System.nanoTime();
executor.execute(() -> {
    long startedAt = System.nanoTime();
    long enqueueToStartNs = startedAt - submittedAt;
    long workStart = System.nanoTime();
    try {
        task.run();
    } finally {
        long workNs = System.nanoTime() - workStart;
        // metrics.recordEnqueueToStart(enqueueToStartNs);
        // metrics.recordWorkDuration(workNs);
    }
});
```

`enqueueToStartNs` đo cả **queue delay và scheduling delay**, không chính xác thời gian chỉ “nằm trong queue” nếu chưa instrument enqueue/dequeue riêng. Tên metric phải phản ánh điều đã đo. Khi truyền context qua executor, cần dùng thư viện/instrumentation **còn được hỗ trợ hiện nay** hoặc task wrapper có kiểm soát; không copy context có dữ liệu nhạy cảm vào log.

## 5. Dùng metrics đúng: percentiles, histograms, counters và saturation

### Metrics phải trả lời câu hỏi về phân phối

Hãy theo dõi **request duration histogram**, error/timeout count, request rate, p95/p99 latency; ngoài ra, instrument **enqueue-to-start**, work duration, DB connection acquisition, query execution, remote HTTP time, retry count.

**Không cộng percentiles của nhiều span để được percentile tổng.** Ví dụ `p95(total)=100ms`, `p95(DB)=40ms` và `p95(queue)=60ms` không chứng minh request ở percentile 95 đã chờ đúng 60 ms rồi chạy DB đúng 40 ms. Các sample có thứ tự và độ tương quan khác nhau. Với async/parallel calls, các spans còn **overlap**, khiến việc cộng durations đếm trùng.

**Không lấy trung bình p95 giữa pods để ra p95 toàn hệ thống**. Percentiles không tổng hợp tuyến tính; dùng histogram buckets/raw observations thích hợp, hoặc một bộ công cụ biết cách gộp phân phối đúng. Cần ghi rõ định nghĩa percentile (nearest-rank, interpolation...) và số lượng mẫu. p99.9 từ vài chục request không đáng tin cậy.

### Counters và gauges khác nhau

- `request_total`, retry/rejection counts thường là **monotonic counters**, có thể **reset khi process restart**. Tính rate phải xử lý reset và scrape gaps.
- `executor.queueDepth` hay connection pool active count là **gauge**, thay đổi tức thời; một sample không đại diện toàn bộ cửa sổ.
- CPU percent trong container phải đặt cạnh **CPU quota, throttled time** và workloads; “host CPU còn rảnh” không có nghĩa pod được cấp đủ CPU.
- Label cardinality: không dùng raw `userId`, `requestId`, SQL statement hoặc token làm metric labels; explosion về storage và privacy có thể gây thêm sự cố.

### RED + USE trong cùng cửa sổ

Nếu latency tăng mà queue depth/active workers cũng tăng, có dấu hiệu saturation. Nhưng **saturation là biểu hiện**, chưa chắc là nguyên nhân sâu nhất. Phải kiểm tra workers bị CPU-bound, block lock, I/O, connection pool hay GC.

## 6. Traces: phân rã request vào đúng giai đoạn

Giả sử một request mất 100 ms:

```text
HTTP server span (100 ms)
  ├── admission/queue             70 ms
  └── worker business task        30 ms
      ├── DB connection acquire    8 ms
      ├── DB query execution       9 ms
      └── encoding/response       13 ms
```

Sơ đồ là **trường hợp minh họa tuần tự**. Trong chương trình thật, spans có thể lồng nhau hoặc chạy song song; **end-to-end latency** phụ thuộc **critical path**, không phải tổng mọi span durations.

Phân biệt **DB client span** và **DB server execution**: một DB span 200 ms có thể bao gồm 188 ms **chờ connection** và chỉ 12 ms query. Tối ưu index SQL trong trường hợp đó có thể không tác động đáng kể.

Traces bị sampling, context propagation errors và không phủ mọi thư viện. Không thấy span **không chứng minh hoạt động không diễn ra**. OpenTelemetry Java hiện cung cấp hệ sinh thái traces/metrics/logs; context propagation và exemplars hỗ trợ liên kết telemetry, nhưng phải xác minh setup của runtime. Dùng traceId/requestId để nối request chậm với error logs, retry attempts và các events liên quan.

## 7. Logs: tìm lỗi, retry và thay đổi — không dùng làm histogram

Structured logs hữu ích nhất khi có:

```text
timestamp=UTC  service=orders  instance=pod-a
requestId=<opaque-id>  traceId=<trace-context>
operation=place-order  attempt=2  outcome=timeout
durationMs=185  deployVersion=<version>
```

Đây là **dạng log minh họa**, không phải thông tin request thật. Không ghi raw access tokens, passwords, session cookies, payment details hoặc PII vào logs/traces. Có chính sách retention, redaction và quyền đọc. Log framework cũng có thể gây lock contention/IO pressure; bật debug logging mọi request trong production có thể **làm sai lệch phép đo**.

Đừng kết luận một request lỗi chỉ bằng việc thấy log cùng millisecond nếu thiếu IDs: khi concurrency cao, nhiều request trùng timestamp. Ngoài ra, async logging exporter có thể drop events hoặc ingest trễ, nên “không thấy exception trong log” chưa đủ chứng minh không có lỗi.

## 8. JFR trên Java 11: kiểm tra JVM thay vì đoán

**Java Flight Recorder (JFR)** đã có API chính thức trong OpenJDK Java 11. JFR cung cấp nhiều nguồn bằng chứng có timestamp:

| Event / nhóm dữ liệu | Nên dùng cho câu hỏi nào? |
| --- | --- |
| `jdk.GarbageCollection` và `jdk.GCHeapSummary` | GC cycles, trạng thái heap và tác động tới pauses |
| `jdk.JavaMonitorEnter` | Chờ vào `synchronized` monitor/lock contention |
| `jdk.ThreadPark` | Thread đợi tại `LockSupport.park`, có thể là idle hoặc contention |
| `jdk.SocketRead` / `jdk.SocketWrite` | Socket I/O duration/endpoint và slow downstream candidates |
| `jdk.FileRead` / `jdk.FileWrite` | File I/O chậm hoặc nhiều |
| `jdk.ExecutionSample` | Method execution stack samples, hot paths tương đối |
| `jdk.ObjectAllocationInNewTLAB` / `jdk.ObjectAllocationOutsideTLAB` | Allocation-related evidence trong Java 11 |
| `jdk.CPULoad` | CPU usage context |

**Không tự động tin rằng mọi event luôn được ghi.** `default`/`profile` khác nhau, một số events có threshold, một số loại sampling cần bật; stack traces cũng có thể thiếu. Không thấy `jdk.SocketRead` không chứng minh socket nhanh nếu thời gian đọc dưới threshold hoặc event tắt.

Trên JVM có quyền diagnostic attach, ví dụ:

```bash
jcmd <PID> JFR.start name=Incident settings=profile duration=120s filename=incident.jfr
jcmd <PID> JFR.check
```

Thay `<PID>` bằng PID thực, và dùng path đủ quyền/quyền riêng tư cho output. Sau khi recording đã kết thúc:

```bash
jfr summary incident.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark,jdk.SocketRead incident.jfr
```

Các lệnh này **minh họa cách chẩn đoán**, output phụ thuộc JVM/JFR settings. Có thể dùng **JDK Mission Control (JMC)** để xem Threads, Lock Instances, Socket/File I/O, GC pauses, method profiling. Oracle Java SE 11 khuyến cáo chú ý **profiling overhead**, đặc biệt khi bật heap statistics, root paths hoặc thresholds rất thấp.

### GC logs và safepoints

Java 11 hỗ trợ **Unified Logging**:

```bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags:filecount=5,filesize=10m \
     -jar service.jar
```

Cú pháp trên phù hợp shell Unix, `service.jar` là ứng dụng giả định. Ở Windows PowerShell, dùng cú pháp xuống dòng tương ứng. `safepoint` **không phải mọi lúc đều do GC**. Để xác định GC gây slow requests, ghép **pause intervals** với các slow traces, xem độ lớn pause và độ bao phủ samples.

GC thường chạy nhưng pause p99 ổn định **làm giả thuyết GC trực tiếp gây tất cả tail latency kém thuyết phục hơn**; vẫn phải xét tác động gián tiếp của concurrent GC CPU, allocation stalls hoặc thiếu heap headroom.

## 9. Thread dumps và thread-pool metrics: hiểu trạng thái thay vì gán nhãn

Ví dụ với HotSpot:

```bash
jcmd <PID> Thread.print
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

Thread dump là **snapshot**. Một `WAITING` thread có thể **đang idle hợp lệ** trong pool; `RUNNABLE` có thể đang ở native I/O, không phải đang sử dụng CPU liên tục; `BLOCKED` thường liên quan monitor entry nhưng một snapshot không đủ mô tả lịch sử. Để tìm deadlock/lock contention, xem monitor owner, nhiều dumps cách nhau, tiến độ công việc, JFR events và `ThreadMXBean.findDeadlockedThreads()` nếu hỗ trợ.

Với `ThreadPoolExecutor`, có thể theo dõi `getActiveCount()`, `getQueue().size()`, `getCompletedTaskCount()`, rejections, enqueue-to-start duration và worker execution duration. Các methods có thể trả **ước lượng tức thời**, không phải transactionally consistent snapshot.

Nếu active=8/8 và queue=42, chưa nên chỉ tăng worker size. Worker có thể đang chờ DB connections (capacity 8), HTTP downstream hoặc lock; tăng từ 8 lên 64 có thể chuyển áp lực xuống DB, tăng memory và làm latency xấu hơn. **Cần biết các workers đang làm gì**.

## 10. Ví dụ Java 11 chạy được: đối chiếu nhiều tín hiệu trên dữ liệu synthetic

Demo đầu tiên tạo **fixture giả lập trong bộ nhớ**, 100 requests mỗi cửa sổ baseline và peak, tính p95 bằng **nearest-rank**. Nó cố ý giữ phân phối thời gian DB ổn định, tăng queue delay của 20% requests ở peak, và thêm một vài giá trị CPU/GC/pool **được gán làm minh họa**, không phải đo thật trong production.

**Lưu file `MultiEvidenceDiagnosisDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class MultiEvidenceDiagnosisDemo {
    static final class RequestSample {
        final int totalMs;
        final int queueMs;
        final int databaseMs;

        RequestSample(int queueMs, int databaseMs, int workMs) {
            this.queueMs = queueMs;
            this.databaseMs = databaseMs;
            this.totalMs = queueMs + databaseMs + workMs;
        }
    }

    static List<RequestSample> simulate(boolean peak) {
        List<RequestSample> samples = new ArrayList<>();
        for (int i = 0; i < 100; i++) {
            int queue = peak && i >= 80
                    ? 60 + (i % 5) * 5
                    : 2 + (i % 3);
            int database = 10 + (i % 4);
            samples.add(new RequestSample(queue, database, 5));
        }
        return samples;
    }

    static int percentile95(List<RequestSample> samples, String field) {
        List<Integer> values = new ArrayList<>();
        for (RequestSample sample : samples) {
            if ("total".equals(field)) {
                values.add(sample.totalMs);
            } else if ("queue".equals(field)) {
                values.add(sample.queueMs);
            } else {
                values.add(sample.databaseMs);
            }
        }
        Collections.sort(values);
        return values.get((int) Math.ceil(values.size() * 0.95) - 1);
    }

    public static void main(String[] args) {
        List<RequestSample> base = simulate(false);
        List<RequestSample> peak = simulate(true);
        long slowQueueRequests = peak.stream()
                .filter(s -> s.queueMs > 50).count();

        System.out.println("samples.perWindow=" + base.size());
        System.out.println("baseline.total.p95.ms=" +
                percentile95(base, "total"));
        System.out.println("peak.total.p95.ms=" +
                percentile95(peak, "total"));
        System.out.println("baseline.queue.p95.ms=" +
                percentile95(base, "queue"));
        System.out.println("peak.queue.p95.ms=" +
                percentile95(peak, "queue"));
        System.out.println("baseline.database.p95.ms=" +
                percentile95(base, "database"));
        System.out.println("peak.database.p95.ms=" +
                percentile95(peak, "database"));
        System.out.println("peak.queueOver50ms=" + slowQueueRequests);
        System.out.println("executor.active.peak=8/8");
        System.out.println("executor.queueDepth.peak=42");
        System.out.println("gc.pause.p99.ms.baseline=4");
        System.out.println("gc.pause.p99.ms.peak=4");
        System.out.println("candidate=executor queueing");
        System.out.println("conclusion=hypothesis, not proof");
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 MultiEvidenceDiagnosisDemo.java
java MultiEvidenceDiagnosisDemo
```

**Stdout chính xác trên OpenJDK 24 đã kiểm thử:**

```text
samples.perWindow=100
baseline.total.p95.ms=22
peak.total.p95.ms=92
baseline.queue.p95.ms=4
peak.queue.p95.ms=75
baseline.database.p95.ms=13
peak.database.p95.ms=13
peak.queueOver50ms=20
executor.active.peak=8/8
executor.queueDepth.peak=42
gc.pause.p99.ms.baseline=4
gc.pause.p99.ms.peak=4
candidate=executor queueing
conclusion=hypothesis, not proof
```

Đã biên dịch với `javac --release 11` và chạy trên **OpenJDK 24**, đúng cả **14 dòng stdout**. Dữ liệu hoàn toàn **synthetic**: chương trình không thu GC logs thật, không có DB thật hay executor 8 workers. Các dòng `gc.pause.*` và `executor.*` được **in từ fixture**, không phải phép đo.

### Đọc kết quả theo từng bước

1. **Triệu chứng:** `total.p95` tăng từ 22 lên 92 ms.
2. **Thành phần đáng nghi:** `queue.p95` tăng từ 4 lên 75 ms; 20/100 requests peak chờ trên 50 ms.
3. **DB execution:** `database.p95` cùng 13 ms trong fixture; không ủng hộ giả thuyết DB **query execution** tự tăng. Nhưng chưa loại được DB **connection acquire wait** nếu nó không nằm trong field được đo.
4. **GC:** `gc.pause.p99` giả lập không tăng; chưa có bằng chứng GC pause là nguyên nhân chính trong ví dụ.
5. **Saturation:** `executor.active.peak=8/8` và queue depth 42 giả lập phù hợp với hướng điều tra queue bottleneck.
6. **Kết luận phải giữ là giả thuyết**: cần phân tích lý do workers bị giữ, kiểm tra từng request và thử can thiệp trong hệ thống thực.

Không suy từ `92-75=17` rằng p95 work=17 ms: percentile tổng và percentile từng giai đoạn được tính trên **những vị trí sample có thể khác nhau**. 100 samples chỉ phù hợp minh họa tính p95; không đủ để tuyên bố p99.9 production.

## 11. Ví dụ Java 11 chạy được: quan sát queue thật bằng latch

Ví dụ thứ hai dùng **`ThreadPoolExecutor` thật**. Hai workers bị giữ bởi `CountDownLatch`, sau đó 4 tasks được enqueue. Khi hai workers chờ release, queue depth là 4. Đây là phép thử **trạng thái queue** có kiểm soát, không phải benchmark request latency.

**Lưu file `ExecutorQueueEvidenceDemo.java`:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecutorQueueEvidenceDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<Runnable>());
        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger done = new AtomicInteger();
        List<Runnable> queued = new ArrayList<>();

        try {
            for (int i = 0; i < 2; i++) {
                pool.execute(() -> {
                    started.countDown();
                    try {
                        if (!release.await(10, TimeUnit.SECONDS)) {
                            throw new IllegalStateException("Timed out");
                        }
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    } finally {
                        done.incrementAndGet();
                    }
                });
            }

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not start");
            }

            for (int i = 0; i < 4; i++) {
                queued.add(done::incrementAndGet);
            }
            for (Runnable task : queued) {
                pool.execute(task);
            }

            System.out.println("activeWorkers=" + pool.getActiveCount());
            System.out.println("queuedTasks=" + pool.getQueue().size());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not terminate");
            }
        }

        System.out.println("completedTasks=" + done.get());
        System.out.println("remainingQueue=" + pool.getQueue().size());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 ExecutorQueueEvidenceDemo.java
java ExecutorQueueEvidenceDemo
```

**Stdout thực tế trên OpenJDK 24:**

```text
activeWorkers=2
queuedTasks=4
completedTasks=6
remainingQueue=0
```

Hai workers chờ `release` trong khi bốn tasks xếp hàng; `finally` gọi `release.countDown()`, shutdown và awaitTermination, bảo đảm demo không giữ các threads vô hạn trong điều kiện bình thường.

**Giới hạn:** `getActiveCount`/`queue.size` là snapshots/ước lượng trong concurrent runtime. Demo dùng latch để tạo trạng thái kiểm soát. Trong production, cần trend nhiều mẫu; unbounded `LinkedBlockingQueue` trong ví dụ không phải cấu hình khuyến nghị — phải chọn capacity, backpressure và rejection policy phù hợp.

**Hai demo không phải cùng một thí nghiệm:** demo 1 synthetic latency/GC/DB metrics; demo 2 là queue thực, không đo request latency. Để xác nhận nguyên nhân trong production, **phải instrument queue wait thực tế trên cùng requests** rồi đối chiếu traces, logs, JFR, OS và downstream.

## 12. Bảng giả thuyết cạnh tranh

| Giả thuyết | Dấu hiệu ủng hộ | Phản chứng hoặc thiếu sót cần xem | Phép thử tiếp |
| --- | --- | --- | --- |
| **Executor queueing** | Enqueue-to-start p95 tăng, pool active max, queue depth tăng | Queue wait bình thường, workers idle | Per-task timing, worker stacks, canary/backpressure theo capacity |
| **DB query chậm** | Query execution time tăng, DB locks/slow query stats tăng | Query time giữ nguyên cùng workload | DB query plan, lock waits, tracing tới query thực |
| **DB connection pool cạn** | Connection acquire wait cao, pool max active, waiting threads | Acquire time ổn định | Tách acquire vs execute, kiểm tra idle/active/leak |
| **GC pauses trực tiếp** | Slow requests overlap long GC pauses và safepoints | Pauses nhỏ, không overlap với tail | JFR+GC logs trên cùng pod/time |
| **CPU starvation/throttling** | cgroup throttled time, runnable backlog, CPU quota hết | CPU còn headroom và tasks blocked vì I/O | OS/container CPU samples, profiles |
| **Lock contention** | `jdk.JavaMonitorEnter`/thread dumps cùng monitor, lock wait cao | Threads tiến triển và wait không tăng | Rút critical section trong canary |
| **Remote/network** | SocketRead dài, 429/5xx, retry, RTT tăng | Remote latency/requests đều ổn định | Trace downstream, check network errors |
| **Deployment/config** | Chỉ version mới chậm sau deploy | Old/new chậm giống nhau cùng tải | Canary/control, rollback, diff flags/config |

**Phải hỏi dữ liệu đang đo chính xác gì.** `DB p95 không tăng` không bác bỏ việc **connection pool** chờ nếu DB p95 chỉ đo SQL execution. `CPU=95%` không chứng minh CPU của application work là bottleneck nếu phần lớn là GC threads hay container bị throttled.

## 13. Quy trình điều tra từ nhiều nguồn, 8 bước

### Bước 1. Xác định hiện tượng và phạm vi

Ghi endpoint, affected pods, khoảng thời gian, SLO, request volume, p95/p99, errors/timeouts, version/JDK/OS. So sánh cả requests thành công và thất bại; không bỏ timeouts.

### Bước 2. Xác lập baseline hợp lệ

So sánh **cùng route/traffic mix/concurrency/size**, chưa có hay đã có canary, caches warm, DB load tương đương. Nếu traffic thay đổi mạnh, tách nhóm để tránh confounding.

### Bước 3. Quan sát RED/USE và thay đổi

Nhìn throughput, error rates, histogram latency; queue/pool depth, CPU quota/RSS, GC, DB waits, downstream retries. Overlay thời điểm deploy, scale, restart, JDK patch, feature flag và remote incidents.

### Bước 4. Truy ngược một số slow traces và fast controls

Dùng traceId/requestId để nối logs, spans và counters; xem critical path, enqueued-to-start, connection acquire, query execution, retry, timeout. Kiểm tra sampling và missing spans; không lấy một outlier làm đại diện toàn bộ.

### Bước 5. Thu JVM/OS evidence liên quan

Nghi GC → JFR GC + GC/safepoint logs + heap/allocation + CPU. Nghi locks → thread dumps ở nhiều mốc + monitor JFR events. Nghi CPU → execution sampling + per-thread/container CPU. Nghi network → socket JFR/remote traces + RTT/errors. Thu ở mức overhead chấp nhận được.

### Bước 6. Viết ít nhất hai giả thuyết **có thể bác bỏ**

Ví dụ:

```text
H1 - Queueing gây phần lớn tail:
  + queue p95, active/max và traces enqueue->start đều tăng
  ? worker bận làm gì: CPU, DB pool, lock hay remote?
  Test: tách worker execution, DB acquire, network timing

H2 - DB engine chậm:
  + có slow query logs gần đó
  - query execution p95 cùng endpoint/tenant vẫn ổn định
  ? slow queries có liên quan trace IDs bị ảnh hưởng?
  Test: nối DB logs với traces và đối chiếu execution/locks

H3 - GC pause làm chậm:
  - GC pause p99 ổn định và không overlap các slow requests
  ? JFR sample/clock skew có đầy đủ?
  Test: đồng bộ timestamps theo pod, GC logs và JFR
```

Đây là **mẫu phân tích**, không phải chứng cứ thật. Ghi rõ tín hiệu thiếu và confidence; không gọi một giả thuyết thành fact.

### Bước 7. Thử nghiệm can thiệp được kiểm soát

Trong canary hoặc staging, thay **một biến quan trọng**, giữ workload, JDK, heap, CPU quota gần tương đương. Khi nghi executor, thay bounded queue/backpressure/worker concurrency **sau khi hiểu downstream capacity**. So sánh p95 queue wait, throughput, 5xx, DB load và CPU, không chỉ latency. Nếu bottleneck chuyển sang DB, không coi đó là thành công.

### Bước 8. Xác minh lại và viết RCA có giới hạn

RCA cần ghi: triệu chứng, bằng chứng từ ít nhất các lớp thích hợp, alternative hypotheses, control/intervention, before/after, rủi ro/trade-off, rollback và phần còn chưa biết. **Nếu chưa làm thử nghiệm, ghi “khả năng cao/đang nghi ngờ”** thay vì “confirmed root cause”.

## 14. Các trường hợp dễ kết luận nhầm

### A. Heap tăng cùng latency

Queue backlog giữ request objects làm heap tăng trong khi requests chờ lâu. **Heap và latency là hai hậu quả**, không nhất thiết GC là nguyên nhân. Kiểm tra root owners, queue age, GC pauses, traces và CPU/heap limits trước khi tăng `-Xmx`.

### B. DB client span chậm

`DB span=200ms` có thể gồm 188 ms chờ lấy connection và 12 ms SQL thực thi. Đọc pool acquire wait, active/idle connections, DB server query time, lock waits; **không tối ưu SQL bừa bãi** hoặc tăng pool vượt DB capacity.

### C. Thread dump có nhiều `WAITING`

Nhiều workers chờ `BlockingQueue.take()` có thể là **idle đúng thiết kế**. Chỉ nghi deadlock/lock contention sau khi xem monitor owners, các dump tiếp theo, JFR lock events và progress. `RUNNABLE` cũng có thể bao gồm native I/O; không tự đồng nhất với CPU-bound.

### D. CPU cao và latency cao

Container chỉ có quota 1 vCPU có thể bị throttled dù host còn nhiều CPU. Concurrent GC cũng dùng CPU. Cần phân biệt CPU quota/throttling, per-thread CPU, GC activity và blocked time trước khi tối ưu một method xuất hiện trong sample.

### E. Tương quan với deploy

Thời điểm sự cố sau deploy là hướng điều tra mạnh, nhưng cũng có thể trùng traffic surge hoặc downstream outage. Cần control pods/rollback có kiểm soát và cùng workload; đổi cả JDK, pool size và feature flag cùng lúc không xác định được biến nào giải thích kết quả.

## 15. Sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Thấy GC và HTTP p99 tăng cùng lúc rồi quy lỗi GC | Cùng tăng do traffic spike | Đối chiếu GC pause overlap với slow traces/queue/CPU |
| Lấy trung bình p95 giữa pods | Percentiles không cộng/average trực tiếp | Gộp histogram/raw observations đúng |
| Chỉ đo latency requests thành công | Bỏ timeouts làm metric “đẹp giả” | Theo dõi error, timeout, rejection và volume |
| DB client span dài = SQL query dài | Có connection acquisition, retry, network | Tách từng giai đoạn |
| Một thread dump `WAITING` nghĩa deadlock | Idle thread wait là bình thường | Nhiều snapshots, lock owners, progress |
| Không thấy JFR event nghĩa không xảy ra | Sampling, threshold, event disabled | Kiểm tra JFR settings và time window |
| CPU 100% nghĩa method X tốn CPU | Có cgroup throttling/GC/native | Kết hợp OS CPU, profiles và JFR |
| Queue tăng nên tăng gấp 10 worker | Có thể đẩy nghẽn xuống DB | Phân tích worker tasks, capacity, backpressure |
| Dùng `System.currentTimeMillis` để đo latency ngắn | Wall clock có thể thay đổi | Dùng `System.nanoTime` cho duration |
| Ghép logs chỉ theo timestamp | Clock skew/concurrency tạo nhầm | Dùng traceId/requestId + host/time context |
| Chỉ dùng p99.9 từ 20 requests | Thiếu mẫu, sai độ tin cậy | Tăng observation count và ghi phương pháp |
| Bật mọi JFR event/profiling nặng | Instrumentation thay đổi workload | Thu có mục tiêu, đo overhead |
| Gắn raw user IDs vào metric labels | Cardinality/PII tăng | Labels hữu hạn; trace/log có kiểm soát |
| Canary đổi nhiều flags cùng lúc | Không tách được biến | Thử từng biến/thiết kế experiment có control |
| Gọi dữ liệu synthetic là production | Mất khả năng kiểm chứng | Ghi rõ fixture và nguồn |
| Chỉ tối ưu response p95 mà bỏ lỗi/throughput | “Nhanh” nhờ từ chối requests | So sánh error rate, successful throughput, CPU/RSS |

## 16. Checklist trước khi chốt nguyên nhân

```text
[ ] Triệu chứng, impacted users, route và SLO có định nghĩa đo được
[ ] Baseline cùng workload, version/region/pod được phân nhóm
[ ] Có sample counts, success/error/timeout và traffic volume
[ ] Metrics/traces/logs ghép UTC + traceId/requestId chính xác
[ ] Hiểu histogram aggregation, sampling và dropped telemetry
[ ] So request critical path với queue, DB acquire và query durations
[ ] JFR/GC/thread dump có đúng pod, time window và event settings
[ ] OS/container CPU quota, throttling, RSS/network được kiểm khi cần
[ ] Đã đặt ít nhất hai hypotheses, có tín hiệu phản chứng
[ ] Đã thử thay đổi có kiểm soát hoặc ghi lý do chưa thể thử
[ ] Đo lại p95/p99, errors, throughput, CPU, memory, downstream load
[ ] Không dùng synthetic data hoặc một snapshot làm bằng chứng đủ
[ ] Báo cáo phân biệt CONFIRMED / LIKELY / UNKNOWN
[ ] Có quyền truy cập phù hợp, redaction, retention và rollback plan
```

**Kết quả “done”** là một kết luận có căn cứ, có thể lặp lại trong điều kiện tương đương, không tạo regressions mới và mô tả những điều còn chưa biết. **Không có một biểu đồ, một dòng log hoặc một thread dump nào tự nó đủ để khẳng định nguyên nhân gốc**.

## 17. Câu hỏi tự kiểm tra

**Câu 1:** HTTP p99 tăng cùng heap used. Đã chứng minh GC gây chậm chưa?

**Đáp án:** Chưa. Cần GC pause overlap, traces, queue depth, CPU/OS metrics và workload context. Cả hai có thể cùng là hậu quả của backlog.

**Câu 2:** Tại sao không cộng p95 queue + p95 DB rồi suy thành p95 request?

**Đáp án:** Percentiles ở các vị trí samples khác nhau và spans có thể overlap. Phải xem per-request durations hoặc histogram aggregation đúng.

**Câu 3:** Nếu DB query duration không đổi nhưng DB client span tăng, nên đo thêm gì?

**Đáp án:** DB pool acquisition wait, retries, connection/transaction wait, network và remote service behavior.

**Câu 4:** Không thấy `jdk.JavaMonitorEnter` trong JFR có chứng minh không có monitor contention không?

**Đáp án:** Không. Event có thể chưa bật, dưới threshold, recording thiếu thời gian hoặc sampling không bắt được.

**Câu 5:** Tại sao `pool.getActiveCount()==maxPoolSize` chưa đủ kết luận pool bottleneck?

**Đáp án:** Nó là snapshot; nếu queue wait thấp và throughput đủ, pool bận có thể bình thường. Cần trend, queue wait, worker stacks và downstream capacity.

**Câu 6:** Vì sao không dùng `System.currentTimeMillis` để đo thời gian thao tác trong JVM?

**Đáp án:** Wall-clock có thể chỉnh; `System.nanoTime` thích hợp để lấy hiệu thời gian tương đối trong cùng JVM.

**Câu 7:** Tại sao p99.9 từ 30 requests là con số thiếu sức thuyết phục?

**Đáp án:** Số mẫu quá ít để đặc trưng tail cực hiếm. Cần đủ request volume và định nghĩa percentile/aggregation.

**Câu 8:** Canaries cùng lúc đổi JDK, executor size và cache TTL rồi latency giảm. Đã biết thành phần nào sửa lỗi chưa?

**Đáp án:** Chưa; thay quá nhiều biến. Cần experiment với control hoặc tách các biến để tìm tác động riêng.

**Câu 9:** Nếu p95 giảm nhưng 5xx tăng, đã tối ưu thành công chưa?

**Đáp án:** Không mặc nhiên. Có thể hệ thống từ chối các request chậm; phải xem errors/timeouts/successful throughput và SLO tổng thể.

**Câu 10:** Khi chưa có phép thử phản chứng, nên viết RCA thế nào?

**Đáp án:** Ghi **giả thuyết**, mức tin cậy, nguồn bằng chứng, những điều chưa biết và thử nghiệm tiếp theo; không gọi là nguyên nhân đã được xác nhận.

**Ghi nhớ:** Trong **kiểm thử và tối ưu Java 11+**, hãy đi theo chuỗi **triệu chứng → nhiều nguồn bằng chứng → giả thuyết cạnh tranh → phép thử có thể bác bỏ → kết luận được xác minh**. Metrics cho thấy xu hướng và phân phối; traces cho đường đi request; logs cho lỗi và bối cảnh; JFR, GC logs, thread dumps cho JVM; OS/container, DB và network telemetry cho điều kiện bên ngoài. So sánh đúng time window, workload, instance và IDs; phân biệt **tương quan** với **nguyên nhân**, đặc biệt trước khi chỉnh GC, tăng thread count hay thay đổi database.

**Tài liệu chính thức còn áp dụng:** [Oracle Java SE 11 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshoot-performance-issues-using-jfr.html); [Oracle Java SE 11 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html); [Oracle Java SE 11 — Unified Logging / java](https://docs.oracle.com/en/java/javase/11/tools/java.html); [Oracle Java SE 11 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html); [Oracle Java SE 11 — ThreadMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/ThreadMXBean.html); [Oracle Java SE 11 — System.nanoTime](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/System.html#nanoTime()); [OpenTelemetry Java — Instrumentation and Context Propagation](https://opentelemetry.io/docs/languages/java/instrumentation/); [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/); [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/).
