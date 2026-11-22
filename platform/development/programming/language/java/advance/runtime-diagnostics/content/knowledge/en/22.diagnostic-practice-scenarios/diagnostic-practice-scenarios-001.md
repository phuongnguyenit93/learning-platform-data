# 22.1 Tạo ứng dụng mẫu với tên thread, chỉ số cơ bản và custom JFR event

## 1. Mục tiêu của bài thực hành tổng hợp

Khi ứng dụng Java phản hồi chậm hoặc tiêu thụ tài nguyên cao, ba nguồn thông tin thường được đọc riêng lẻ:

- **Thread:** request/task nào đang chạy, worker nào xử lý và thread có bị kẹt/chờ hay không?
- **Metrics:** có bao nhiêu công việc được nhận, đã xong, lỗi, đang chạy; queue time và work time biến động ra sao?
- **Java Flight Recorder (JFR):** sự kiện cụ thể nào đã xảy ra, kéo dài bao lâu, thuộc task/thread nào và có liên hệ với GC, allocation, CPU hoặc lock contention không?

Nếu chỉ nhìn một nguồn, rất dễ chẩn đoán thiếu. Ví dụ, `active=2` không cho biết hai worker đang xử lý task nào; event `jdk.JavaMonitorEnter` không tự nói task nghiệp vụ nào tạo contention; một log `task failed` không giải thích JVM đang chịu GC pressure hay không.

Bài này xây dựng một **ứng dụng Java 17+ độc lập**, không cần Maven hay thư viện ngoài, nhằm tích hợp:

1. `ThreadFactory` tạo worker threads với tên ổn định `diag-worker-1`, `diag-worker-2`.
2. `ExecutorService` với **hai worker**, nhận **bốn task**, một task được giả lập thất bại.
3. **Chỉ số cơ bản**: `submitted`, `finished`, `successes`, `failures`, `active`, `peakActive`, tổng `queueNanos` và `workNanos`.
4. **Custom JFR event** `demo.WorkTask` có `taskId`, `workerName`, `outcome`, `queueNanos` và `workNanos`.
5. `Recording` tự mở/đóng để tạo file `thread-metrics-lab.jfr`.
6. `RecordingFile` đọc lại JFR và xác minh số event, kết quả, tên thread và duration.

Bạn cũng sẽ biết cách dùng `jfr summary`/`jfr print`, phân biệt counter với gauge, kiểm tra đơn vị thời gian, tránh metric labels có cardinality cao và vận dụng mẫu này khi xử lý sự cố.

**Phạm vi:** Đây là một *diagnostic lab*. `Thread.sleep(30)` giả lập một công việc có thời lượng, **không phải I/O thật**, không phải benchmark CPU hay throughput. Các metrics được giữ trong bộ nhớ để học cơ chế; production thường xuất chúng qua hệ thống monitoring riêng. Kết quả số đếm được thiết kế ổn định, còn thời lượng thực và worker nào nhận từng task có thể thay đổi theo JVM/OS.

## 2. Kiến trúc ứng dụng mẫu

```text
                           main thread
                               |
                               v
              submit task-1, task-2, task-3, task-4
                               |
                     ExecutorService(2)
                               |
                      task queue / dispatch
                          /          \
                         v            v
                 diag-worker-1    diag-worker-2
                  execute(...)     execute(...)
                         \            /
                          \          /
                           v        v
                     Metrics in memory
                   counters + gauges + sums
                               |
                    per-task WorkTaskEvent
                               |
                         JFR Recording
                               |
                       thread-metrics-lab.jfr
                               |
                       RecordingFile reader
                               |
                       invariants / checks
```

**Ba góc nhìn phải gắn được với nhau:**

- `taskId` cho phép nhận diện một instance task.
- `workerName` (và JFR event thread metadata nếu được ghi) cho biết task được thực thi trên worker nào.
- `outcome` và duration cho phép so sánh thành công/lỗi, queue wait/work và tìm các outlier.

Thread name giúp người vận hành xem thread dump/JFR dễ hơn, nhưng **không phải unique request ID**. Một worker pool tái sử dụng thread cho nhiều task, nên muốn ghép logic nghiệp vụ vẫn phải ghi `taskId` hoặc trace/span ID riêng.

### 2.1. Các pha trong một task

```text
main:      enqueuedNano  --submit()----------------->
                          |
executor:                 | chờ worker
                          v
worker:                  startedNano -- work --> endedNano
                          |                        |
                          |<------ workNanos ------>|
            |<---------- queueNanos --------------?|
            |<------------- total elapsed ---------------->|

queueNanos = startedNano - enqueuedNano
workNanos  = endedNano - startedNano
```

Sơ đồ là biểu diễn khái niệm; `queueNanos` ở ví dụ thực tế bao gồm **thời gian từ trước gọi submit đến khi worker bắt đầu**, tức có cả scheduling và dispatch, không chỉ thời gian nằm đúng trong cấu trúc queue. Nếu phải đo thời gian enqueue/dequeue thuần túy, cần thêm mốc trên đúng API queue.

`Event.begin()` của JFR được gọi khi worker đã khởi động task, `Event.end()` khi phần work kết thúc. Vì vậy **JFR intrinsic event duration gần với work time**, không bao gồm thời gian chờ trước STARTED. Ta lưu `queueNanos` thành một field riêng để quan sát phần chờ.

## 3. Thiết kế tên thread và vòng đời executor

### 3.1. Tại sao đặt tên thread?

Một thread dump gồm hàng chục hoặc hàng trăm thread với những tên mặc định như `pool-7-thread-2` thường khó liên hệ đến thành phần nghiệp vụ. Tên có cấu trúc làm việc truy nguyên đơn giản hơn:

```text
diag-worker-1
diag-worker-2
```

Trong ứng dụng lớn, đặt prefix theo **component** thay vì một ID request riêng trên mỗi thread: `order-io-worker-1`, `sync-job-worker-2`, `cache-refresh-1`. Worker phục vụ nhiều request; nếu gắn request ID vào thread name, phải thay và khôi phục an toàn, tránh thông tin cũ bị rò sang task khác.

Tên thread là **gợi ý chẩn đoán**, không là bằng chứng duy nhất. Nên dùng thêm thread ID/native ID, process/PID, timestamp và task/trace ID. Hai JVM trên hai container có thể có cùng `diag-worker-1`.

### 3.2. ThreadFactory đúng chức năng

Ví dụ của bài dùng `AtomicInteger` cấp số và tạo thread trực tiếp:

```java
// Fragment minh họa; namedFactory được dùng trong chương trình đầy đủ ở mục 7.
AtomicInteger sequence = new AtomicInteger();
ThreadFactory namedFactory = task -> {
    Thread worker = new Thread(task,
            "diag-worker-" + sequence.incrementAndGet());
    worker.setDaemon(false);
    return worker;
};
```

`ThreadFactory.newThread(Runnable)` cho phép đặt tên, daemon status, priority hoặc uncaught exception handler khi cần. Không tùy tiện nâng priority, thay daemon status của executor production hay ghi secrets vào thread name.

**Tại sao `AtomicInteger`?** `ThreadFactory` có thể được gọi từ nhiều đường tạo worker; phép tăng số cần an toàn đồng thời. Số 1, 2 chỉ bảo đảm unique **trong instance factory này**, không toàn hệ thống.

**Tại sao `setDaemon(false)`?** Đây là platform threads cần xử lý task đã nhận; daemon threads không giữ JVM sống một mình và có thể bị dừng khi process kết thúc. Dù dùng non-daemon, vẫn phải shutdown executor có kiểm soát.

### 3.3. Chọn fixed thread pool cho lab

`Executors.newFixedThreadPool(2, namedFactory)` dùng tối đa hai worker đang hoạt động, với queue nội bộ lưu task đang đợi. Điều này thuận tiện để quan sát queue-to-start latency. Tuy nhiên, **fixed thread pool mặc định có queue không giới hạn**; đừng sao chép nó cho production nhận tải không giới hạn mà không có backpressure, deadline và rejection policy.

Trong production thường nên cân nhắc một `ThreadPoolExecutor` có bounded queue và `RejectedExecutionHandler` thích hợp, cùng metrics cho queue depth và rejected count.

Khi kết thúc, ví dụ gọi `shutdown()`, `awaitTermination(...)` và `shutdownNow()` nếu cần. `shutdownNow()` yêu cầu interrupt các task đang chạy, không bảo đảm mọi tác vụ tự dừng; code task cần xử lý interrupt đúng hợp đồng.

## 4. Chọn metric: counter, gauge và phép đo duration

### 4.1. Những metric được sử dụng

| Metric | Loại | Ý nghĩa | Invariant hữu ích |
| --- | --- | --- | --- |
| `submitted` | Counter | Số task được chấp nhận vào luồng demo và đã submit | Không giảm |
| `finished` | Counter | Task đi tới khối `finally` và kết thúc đường xử lý | Không giảm |
| `successes` | Counter | Task có outcome SUCCESS | Không giảm |
| `failures` | Counter | Task có outcome khác SUCCESS trong demo | Không giảm |
| `active` | Gauge | Số task đang được worker xử lý ngay lúc đo | Từ 0 đến 2 trong demo |
| `peakActive` | High-water mark | Mức active cao nhất đã quan sát | Không vượt capacity=2 |
| `queuedNanos` | Sum | Tổng wait-to-start của các task đã xong | Chỉ có nghĩa cùng clock/unit |
| `workedNanos` | Sum | Tổng work duration của các task đã xong | Không phải wall-clock elapsed của cả pool |

Sau khi tất cả Future hoàn tất thành công về mặt **điều phối**, kỳ vọng:

```text
submitted = finished = successes + failures = 4
successes = 3
failures = 1
active = 0
0 <= peakActive <= 2
```

Thực tế `peakActive` kỳ vọng ít nhất 1 khi có task, nhưng việc chạy song song **không bảo đảm** quan sát đúng 2 trong mọi lần chạy — tùy scheduling.

### 4.2. LongAdder cho counters có nhiều writer

`LongAdder` hữu ích với các counter có nhiều threads tăng đồng thời: thường giảm contention so với `AtomicLong` trong tải lớn. Nó phù hợp cho **tổng hợp**:

```java
// Fragment minh họa, dùng khi đã có imports java.util.concurrent.atomic.*.
LongAdder completed = new LongAdder();
completed.increment();
long total = completed.sum();
```

**Quan trọng:** `sum()` trong lúc nhiều writer đang cập nhật **không phải snapshot nguyên tử của cả hệ thống**. Nếu bạn đọc liên tiếp các counters khi service còn chạy, có thể thấy `finished != successes+failures` tạm thời do thứ tự cập nhật. Đừng phát cảnh báo sai trên một lần đọc không đồng bộ; dùng một lần chụp sau khi mọi Future hoàn thành để kiểm tra invariant lab.

Trong một luồng sự cố thực tế, metrics scrape có thể xảy ra giữa lúc cập nhật; counter nên được xem là **eventually consistent** theo thiết kế.

### 4.3. AtomicInteger cho active gauge

`active.incrementAndGet()` khi task bắt đầu và `active.decrementAndGet()` trong `finally` khi task kết thúc. Nếu chỉ decrement trên nhánh SUCCESS, counter sẽ tăng mãi sau lỗi và gây ảo giác worker bị kẹt.

`peakActive.accumulateAndGet(nowActive, Math::max)` là phép max atomic; tránh kiểu `if (nowActive > peak) peak = nowActive` vì dễ mất cập nhật giữa threads.

### 4.4. Duration bằng nanoTime, không dùng timestamp tường

`System.nanoTime()` dùng để đo **elapsed time**, không phải UTC timestamp. Cần đo hai hoặc ba mốc trong **cùng JVM** rồi lấy hiệu. Giá trị tuyệt đối không được lấy so giữa hai máy/JVM.

Trong lab:

```java
// Fragment minh họa các phép đo.
long enqueuedNano = System.nanoTime();
// Task được submit và được worker chạy sau đó:
long startedNano = System.nanoTime();
// Khi thao tác xong:
long endedNano = System.nanoTime();

long queueNanos = startedNano - enqueuedNano;
long workNanos = endedNano - startedNano;
double workMillis = workNanos / 1_000_000.0;
```

`1 ms = 1.000.000 ns`. Không đổi một số đo nano giây sang milliseconds bằng cách gắn nhãn `ms` mà quên chuyển đơn vị.

**Không dùng `System.currentTimeMillis()` làm clock duy nhất để đo duration ngắn.** Wall clock có thể bị chỉnh; dùng `Instant.now()` hoặc epoch millis khi cần đối chiếu với log UTC, còn duration dùng monotonic clock.

### 4.5. Histogram và p95/p99 là bước sau

Chỉ có `workedNanos.sum()` và `finished.sum()` thì có thể tính **trung bình** trên tập task đã kết thúc, nhưng **không tính được p95/p99 chính xác**. Muốn tail latency, cần timer/histogram với buckets hoặc cơ chế quantiles được thiết kế phù hợp.

Cũng không cộng `workedNanos` để suy ra elapsed wall-clock của pool: hai worker có thể chạy cùng lúc, nên tổng thời gian xử lý nhiều task vượt thời gian đồng hồ thực.

Trong production, có thể dùng Micrometer/OpenTelemetry Metrics hoặc Prometheus-compatible exporter cho counter/gauge/timer; **bài này không phụ thuộc thư viện đó** để giữ runnable trên JDK 17+.

## 5. Thiết kế custom JFR event có nghĩa

### 5.1. JFR event là gì?

JFR ghi sự kiện tại runtime vào một recording, có thể bao gồm các event từ JVM và event do ứng dụng định nghĩa. Với custom event, bạn tạo lớp kế thừa `jdk.jfr.Event`, khai báo fields có thể ghi và điều khiển vòng đời:

```text
new WorkTaskEvent()
        |
     event.begin()  <- bắt đầu work
        |
     thực hiện task
        |
     event.end()    <- kết thúc work
        |
     gán taskId, workerName, outcome, durations
        |
     event.commit() <- gửi event để JFR quyết định ghi
        |
     recording dump thành .jfr
```

`commit()` có thể được gọi sau `end()` và sau khi điền fields cần lưu; JFR xét cấu hình `enabled`/`threshold` để quyết định ghi. Trong ví dụ, `withThreshold(Duration.ZERO)` giữ cả event ngắn. Nếu nâng threshold, event ngắn hơn ngưỡng sẽ không xuất hiện và số event đọc lại có thể thấp hơn `finished`.

### 5.2. Lớp WorkTaskEvent

Trong chương trình sẽ có:

```java
@Name("demo.WorkTask")
@Label("Work task")
@Category({"Demo", "Diagnostics"})
@StackTrace(false)
public static final class WorkTaskEvent extends Event {
    @Label("Task ID")
    public String taskId;
    @Label("Worker name")
    public String workerName;
    @Label("Outcome")
    public String outcome;
    @Timespan(Timespan.NANOSECONDS)
    public long queueNanos;
    @Timespan(Timespan.NANOSECONDS)
    public long workNanos;
}
```

Đây là **fragment nằm trong class chương trình đầy đủ** ở mục 7; tự nó chưa có import/main. Các annotation giúp JFR metadata có ý nghĩa:

- `@Name("demo.WorkTask")` tạo tên event type **ổn định** để tìm trong `jfr summary`, `jfr print`, JMC hoặc `RecordingFile`.
- `@Label` là tên hiển thị, không dùng làm key kỹ thuật.
- `@Category` nhóm event trong giao diện JFR/JMC.
- `@StackTrace(false)` là default không lưu call stack để giảm chi phí; recording có thể override bằng `withStackTrace()` nếu cần.
- `@Timespan(Timespan.NANOSECONDS)` nói rõ hai field `long` mang đơn vị thời gian, để công cụ hiểu được ý nghĩa chúng.

Nếu muốn xem call sites, bật stack trong recording tương ứng, cân nhắc event volume và overhead. Trong demo, worker name và task ID đã cung cấp correlation đơn giản, nên không cần stack cho mọi task.

### 5.3. Field nào nên đưa vào custom event?

Một schema production có thể dùng `taskId`, `operation` (giá trị phân loại có cardinality thấp), `workerName`, `outcome`, `queueNanos`, `workNanos`, `errorType`. Nhưng cần giới hạn payload:

- Tránh raw HTTP body, SQL parameters, access tokens, cookies, secrets, email/PII.
- Không đưa một object graph tùy ý vào event; JFR event fields có tập kiểu dữ liệu được hỗ trợ.
- Dùng `String` / primitive fields, class/thread metadata phù hợp; không kỳ vọng JFR tự serialize `Map<String,Object>` tùy biến.
- Không đưa `taskId` vào metric **label** của Prometheus: mỗi request sinh một series mới gây cardinality explosion. Task ID phù hợp hơn cho JFR/logs/traces với retention và sampling được kiểm soát.
- Khi schema thay đổi, cân nhắc versioning để parser downstream nhận diện đúng fields.

### 5.4. Event duration và field duration là hai phép đo khác nhau

`event.getDuration()` trong `RecordingFile` cho duration nội tại giữa `begin()` và `end()`. Trong lab, `workNanos` được tính bằng `endedNano - startedNano`, bao gồm một chút overhead quanh `event.begin/end`; hai giá trị gần nhau nhưng **không cần bằng tuyệt đối**.

`queueNanos` là field application tự tính, **không nằm trong intrinsic event duration**. Nếu worker bắt đầu rất muộn nhưng work nhanh, event JFR với threshold cao vẫn có thể bị lọc, dù `queueNanos` lớn. Đây là lý do phải chọn ranh giới và threshold đúng theo mục tiêu chẩn đoán.

## 6. Cấu trúc và cách chạy lab

Bài dùng **một file Java duy nhất** và một file output JFR:

```text
lab/
├── ThreadMetricsJfrLab.java
├── ThreadMetricsJfrLab.class     (tạo sau javac)
├── ThreadMetricsJfrLab$*.class   (các class lồng nhau sau javac)
└── thread-metrics-lab.jfr        (tạo sau khi chương trình chạy)
```

Yêu cầu:

- **JDK 17+** có module `jdk.jfr`.
- Chạy bằng terminal có quyền ghi thư mục hiện tại.
- Không cần Maven, Gradle hay JVM agent ngoài.
- JFR được kích hoạt và cấu hình ngay trong `main()`.
- Mỗi lần chạy sinh/ghi lại tệp `thread-metrics-lab.jfr` trong thư mục làm việc; **không dùng tên/path này trên dữ liệu production cần giữ**.

Nên tạo một thư mục lab riêng trước khi chạy để tránh ghi đè artifact ngoài ý muốn.

## 7. Toàn bộ chương trình Java 17+ chạy được

Tạo file **`ThreadMetricsJfrLab.java`** với nội dung dưới đây:

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import jdk.jfr.*;
import jdk.jfr.consumer.*;

public final class ThreadMetricsJfrLab {
    @Name("demo.WorkTask")
    @Label("Work task")
    @Category({"Demo", "Diagnostics"})
    @StackTrace(false)
    public static final class WorkTaskEvent extends Event {
        @Label("Task ID")
        public String taskId;
        @Label("Worker name")
        public String workerName;
        @Label("Outcome")
        public String outcome;
        @Timespan(Timespan.NANOSECONDS)
        public long queueNanos;
        @Timespan(Timespan.NANOSECONDS)
        public long workNanos;
    }

    private static final class Metrics {
        final LongAdder submitted = new LongAdder();
        final LongAdder finished = new LongAdder();
        final LongAdder successes = new LongAdder();
        final LongAdder failures = new LongAdder();
        final LongAdder queuedNanos = new LongAdder();
        final LongAdder workedNanos = new LongAdder();
        final AtomicInteger active = new AtomicInteger();
        final AtomicInteger peakActive = new AtomicInteger();
    }

    private static String execute(String taskId, boolean fail,
                                  long enqueuedNano, Metrics metrics) {
        long startedNano = System.nanoTime();
        int nowActive = metrics.active.incrementAndGet();
        metrics.peakActive.accumulateAndGet(nowActive, Math::max);

        WorkTaskEvent event = new WorkTaskEvent();
        event.begin();
        String outcome = "SUCCESS";
        try {
            Thread.sleep(30);
            if (fail) {
                throw new IllegalStateException("simulated failure");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            outcome = "CANCELLED";
        } catch (IllegalStateException exception) {
            outcome = "ERROR";
        } finally {
            event.end();
            long endedNano = System.nanoTime();
            long queueNanos = startedNano - enqueuedNano;
            long workNanos = endedNano - startedNano;

            event.taskId = taskId;
            event.workerName = Thread.currentThread().getName();
            event.outcome = outcome;
            event.queueNanos = queueNanos;
            event.workNanos = workNanos;
            event.commit();

            metrics.queuedNanos.add(queueNanos);
            metrics.workedNanos.add(workNanos);
            if ("SUCCESS".equals(outcome)) {
                metrics.successes.increment();
            } else {
                metrics.failures.increment();
            }
            metrics.finished.increment();
            metrics.active.decrementAndGet();
        }
        return outcome;
    }

    private static void verifyRecording(Path path) throws Exception {
        Map<String, String> outcomes = new TreeMap<>();
        int count = 0, ok = 0, error = 0;
        try (RecordingFile file = new RecordingFile(path)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (!"demo.WorkTask".equals(
                        event.getEventType().getName())) {
                    continue;
                }
                count++;
                String taskId = event.getString("taskId");
                String outcome = event.getString("outcome");
                String worker = event.getString("workerName");
                if (!worker.matches("diag-worker-[12]")) {
                    throw new IllegalStateException("Worker name mismatch");
                }
                if (event.getLong("queueNanos") < 0 ||
                        event.getLong("workNanos") < 0) {
                    throw new IllegalStateException("Negative duration");
                }
                if (outcomes.put(taskId, outcome) != null) {
                    throw new IllegalStateException("Duplicate event");
                }
                if ("SUCCESS".equals(outcome)) ok++;
                if ("ERROR".equals(outcome)) error++;
            }
        }
        if (count != 4 || ok != 3 || error != 1 ||
                outcomes.size() != 4 ||
                !"ERROR".equals(outcomes.get("task-3"))) {
            throw new IllegalStateException("Unexpected JFR results: " + outcomes);
        }
        System.out.printf("jfrEvents=%d jfrSuccess=%d jfrError=%d%n",
                count, ok, error);
    }

    public static void main(String[] args) throws Exception {
        Metrics metrics = new Metrics();
        AtomicInteger workerSequence = new AtomicInteger();
        ThreadFactory namedFactory = runnable -> {
            Thread worker = new Thread(runnable,
                    "diag-worker-" + workerSequence.incrementAndGet());
            worker.setDaemon(false);
            return worker;
        };

        Path path = Path.of("thread-metrics-lab.jfr");
        try (Recording recording = new Recording()) {
            recording.enable(WorkTaskEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withoutStackTrace();
            recording.start();

            ExecutorService executor =
                    Executors.newFixedThreadPool(2, namedFactory);
            List<Future<String>> results = new ArrayList<>();
            try {
                for (int n = 1; n <= 4; n++) {
                    String taskId = "task-" + n;
                    boolean fail = n == 3;
                    long enqueuedNano = System.nanoTime();
                    metrics.submitted.increment();
                    results.add(executor.submit(() ->
                            execute(taskId, fail, enqueuedNano, metrics)));
                }
                for (Future<String> result : results) {
                    result.get();
                }
            } finally {
                executor.shutdown();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            }

            recording.stop();
            recording.dump(path);
        }

        System.out.printf(
                "submitted=%d finished=%d success=%d failure=%d active=%d%n",
                metrics.submitted.sum(), metrics.finished.sum(),
                metrics.successes.sum(), metrics.failures.sum(),
                metrics.active.get());
        verifyRecording(path);
        System.out.println("checks=PASS");
    }
}
```

### 7.1. Lệnh biên dịch/chạy

Trên terminal trong thư mục chứa file:

```bash
javac --release 17 ThreadMetricsJfrLab.java
java ThreadMetricsJfrLab
```

Tùy terminal, dùng `java -version` và `javac -version` để bảo đảm đang dùng JDK có JFR. `--release 17` kiểm tra mã chỉ sử dụng API và cú pháp tương thích Java 17; lệnh chạy vẫn dùng JVM thực tế của máy.

**Stdout đã kiểm thử** bằng cách biên dịch `--release 17` và chạy trên JDK 24:

```text
submitted=4 finished=4 success=3 failure=1 active=0
jfrEvents=4 jfrSuccess=3 jfrError=1
checks=PASS
```

Ba dòng trên là **kết quả ổn định mong đợi khi chương trình thực thi thành công**, không in những phần phụ thuộc scheduling như task-to-worker assignment, nanoTime, RSS hoặc wall-clock timestamp. Trong cùng lần kiểm thử, `jfr summary` xác nhận bốn instance `demo.WorkTask`.

### 7.2. Phần ThreadFactory

Trong `main()`, `workerSequence` cấp tên `diag-worker-1`, `diag-worker-2` khi executor cần tạo worker. `ThreadFactory` không được gọi một lần cho mỗi task: **thread được tái sử dụng**. Có bốn task, nhưng chỉ cần tối đa hai threads.

Hàm `verifyRecording` kiểm tra tên của event đã ghi phải khớp `diag-worker-[12]`. Đây là xác minh **thực tế trong file JFR**, không phải chỉ nhìn code rồi tin thread đã được đặt tên.

### 7.3. Phần metric counters và gauges

`Metrics` chứa các kiểu đồng thời chuẩn thư viện Java:

- `LongAdder` cho counts và tổng durations.
- `AtomicInteger` cho gauge active và high-water mark.
- Không có static global metrics; một instance `Metrics` thuộc vòng đời một lần chạy lab. Trong service thật, đặt metric registry theo component/lifetime phù hợp.

Trong `execute`, khi task bắt đầu, `active` tăng; khi đi qua `finally`, `active` giảm. Status `SUCCESS` tăng `successes`, status `ERROR`/`CANCELLED` tăng `failures` theo cách đếm đơn giản của lab.

**Lưu ý ranh giới thất bại:** ví dụ bắt `IllegalStateException` để tạo một outcome `ERROR` thay vì để Future ném exception. Đó là lựa chọn để minh họa telemetry có đủ result và output xác định. Trong production, sau khi đã ghi metrics/event cần **trả lỗi hoặc hoàn thành future thất bại theo hợp đồng**, không được che khuất failure trước caller.

### 7.4. Phần JFR event

`WorkTaskEvent` được tạo khi worker vào `execute`, sau đó:

1. `event.begin()` đánh dấu điểm bắt đầu work.
2. `Thread.sleep(30)` giả lập hoạt động; `task-3` ném lỗi.
3. `event.end()` đánh dấu kết thúc work ngay đầu `finally`.
4. Các trường `taskId`, `workerName`, `outcome`, `queueNanos` và `workNanos` được gán.
5. `event.commit()` gửi event cho JFR recording.

Recording được bật bằng:

```java
recording.enable(WorkTaskEvent.class)
        .withThreshold(Duration.ZERO)
        .withoutStackTrace();
```

Đây là **fragment trích từ chương trình đầy đủ**, không phải class độc lập. `Duration.ZERO` giúp giữ các event demo ngắn; `withoutStackTrace()` tắt stack trong recording này. Một custom event không tự ghi khi không có recording phù hợp hoặc khi type bị disable.

### 7.5. Phần đọc JFR và kiểm tra kết quả

`RecordingFile` đọc tuần tự file `.jfr`; mỗi `RecordedEvent` được lọc theo `event.getEventType().getName()`. Chương trình kiểm tra:

- Có đúng **4** `demo.WorkTask` events.
- Có **3 SUCCESS** và **1 ERROR**.
- `task-3` là task lỗi giả lập.
- Mỗi `workerName` thuộc hai tên worker mong đợi.
- `queueNanos` và `workNanos` không âm.
- Không có task ID bị lặp.

Vì kiểm tra kết quả **sau khi ghi và đọc lại file**, dòng `checks=PASS` có ý nghĩa mạnh hơn việc chỉ đếm số lần gọi `event.commit()`. Tuy vậy đây là self-test của lab, không thay được kiểm thử hiệu năng hay đầy đủ telemetry production.

### 7.6. Không suy luận output không được in

Ví dụ không in `peakActive`, duration trung bình hay task-to-worker mapping, vì các giá trị có thể biến động. Bạn có thể tự thử thêm output:

```java
// Fragment minh họa ở cuối main(), nơi đã có biến metrics.
// Đọc sau khi mọi Future đã kết thúc để số liệu dễ giải thích.
System.out.println("peakActive=" + metrics.peakActive.get());
System.out.println("averageWorkMs="
        + (metrics.workedNanos.sum() / 1_000_000.0)
        / Math.max(1L, metrics.finished.sum()));
```

**Không có stdout cố định** cho hai dòng trên. `peakActive` nằm trong khoảng 1–2 khi các task đã chạy, còn average work quanh `Thread.sleep(30)` cộng overhead, có thể cao hơn đáng kể trên máy bận. `Thread.sleep` không bảo đảm wake-up đúng 30 ms.

## 8. Kiểm tra file JFR bằng công cụ đi kèm JDK

Sau khi chạy, file `thread-metrics-lab.jfr` ở thư mục hiện tại. Dùng CLI:

```bash
jfr summary thread-metrics-lab.jfr
jfr print --events demo.WorkTask thread-metrics-lab.jfr
jfr metadata thread-metrics-lab.jfr
```

### 8.1. `jfr summary` cho biết gì?

`jfr summary` liệt kê tên event type, số lượng và dung lượng gần đúng của event data tùy phiên bản JDK. Trong lần chạy thành công bạn kỳ vọng có:

```text
demo.WorkTask                 4
```

Dòng trên là **trích ý chính**, không phải toàn bộ stdout nguyên văn của `jfr summary`. Các cột size, metadata và event types khác phụ thuộc JVM và cách file được ghi. Không kết luận mọi event JFR file đều là `demo.WorkTask`, vì file có thể chứa các event JVM từ profile mặc định.

### 8.2. `jfr print` cho biết gì?

Với `--events demo.WorkTask`, CLI cho thấy từng bản ghi, ví dụ field `taskId`, `workerName`, `outcome`, `queueNanos`, `workNanos` cùng timestamp/duration theo cách format của JDK. **Không có một transcript chính xác chung** vì timestamp, durations và worker-to-task mapping thay đổi theo scheduling.

Một hình dung field value (dữ liệu **giả định để giải thích**, không phải output nguyên văn):

```text
taskId       = "task-3"
workerName   = "diag-worker-1"
outcome      = "ERROR"
queueNanos   = <nonnegative duration in ns>
workNanos    = <nonnegative duration in ns>
```

Số lượng event đọc lại và outcome phải khớp chương trình; vị trí worker hoặc giá trị nano giây thì không nên hardcode.

### 8.3. Đọc trong JDK Mission Control

Mở file bằng JDK Mission Control (JMC), tìm event type `demo.WorkTask`. Hãy:

1. Tìm các event theo tên type `demo.WorkTask`.
2. Xem tổng số event và phân phối duration.
3. Group hoặc filter theo `workerName` và `outcome`.
4. So sánh timestamp với GC, CPU/threads và built-in events nếu chúng được thu.
5. Kiểm tra sự tương quan giữa event duration và `queueNanos`, phân biệt queue wait với execution.

Bốn task của lab quá ít để suy ra performance distribution thực tế; JMC ở đây là **bài tập thao tác công cụ**, không phải nguồn benchmark.

## 9. Phân biệt ba câu hỏi chẩn đoán thường bị trộn

### 9.1. “Worker đang bận bao nhiêu?”

`metrics.active` là một gauge cập nhật khi task thực thi. Nếu active=2 ở fixed pool capacity 2, pool đang dùng đủ hai worker **tại thời điểm đọc**. Tuy nhiên chưa thể kết luận quá tải nếu không biết **queue depth**, số request đến/giây, processing rate và thời gian chờ.

`peakActive=2` nghĩa đã từng có 2 active đồng thời, không có nghĩa luôn saturated.

### 9.2. “Task phải chờ bao lâu trước khi chạy?”

`queueNanos` của mỗi event đo khoảng từ trước `submit` đến lúc `execute` bắt đầu. Một queue duration tăng trong khi work duration ổn định là tín hiệu đáng xem xét về worker saturation, queueing hoặc dispatch overhead.

Cần thêm queue depth/rejection count và arrival rate để kết luận. Với default fixed pool unbounded queue, task có thể đợi ngày càng lâu mà không xuất hiện rejection ngay.

### 9.3. “Task xử lý chậm do đâu?”

`workNanos` cho tổng thời gian trong task, nhưng **không tự phân chia CPU, blocking I/O, lock contention, GC pause hay scheduling**. Khi thấy outlier, dùng JFR built-in events như `jdk.ExecutionSample`, `jdk.JavaMonitorEnter`, `jdk.FileRead`/`jdk.SocketRead` và GC/safepoint events (nếu đã được bật) để điều tra sâu.

Khi có `workerName` và task ID, việc tìm tương quan dễ hơn, nhưng JFR event riêng lẻ không bảo đảm có đầy đủ thông tin root cause hoặc call stack khi `stackTrace=false`.

## 10. Mở rộng: snapshot heap và thread count với MXBeans

Tên thread và task metrics chỉ mô tả **component executor**. Muốn có bối cảnh JVM, Java cung cấp `java.lang.management`:

- `MemoryMXBean`: heap/non-heap used/committed/max.
- `ThreadMXBean`: live thread count, peak thread count, thông tin thread và CPU time nếu JVM hỗ trợ.
- `RuntimeMXBean`: uptime, JVM runtime identity.
- `OperatingSystemMXBean`: OS name, available processors và các thông tin JVM standard.

Ví dụ **fragment**, không phải chương trình độc lập (thêm `import java.lang.management.*;` vào ứng dụng):

```java
MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
ThreadMXBean threadBean = ManagementFactory.getThreadMXBean();
RuntimeMXBean runtimeBean = ManagementFactory.getRuntimeMXBean();

MemoryUsage heap = memoryBean.getHeapMemoryUsage();
long heapUsedBytes = heap.getUsed();
int liveJVMThreads = threadBean.getThreadCount();
long uptimeMs = runtimeBean.getUptime();

System.out.println("heapUsedBytes=" + heapUsedBytes);
System.out.println("jvmThreadCount=" + liveJVMThreads);
System.out.println("jvmUptimeMs=" + uptimeMs);
```

Các con số biến động theo JVM và thời điểm. `heapUsedBytes` **không phải process RSS**; `ThreadMXBean` đếm các thread theo semantics của VM, khác với `active` của executor. Nên chụp snapshot JVM và task metrics trong cùng time window, có timestamp UTC, PID/instance ID nếu dùng để so sánh.

### 10.1. Tên thread trong thread dump

Khi chương trình hoặc service thật còn sống, có thể dùng:

```bash
jcmd -l
jcmd 12345 Thread.print -l
```

Thay `12345` bằng PID thật. Thread names `diag-worker-*` có thể xuất hiện trong thread dump **khi worker còn sống**, nhưng lab ngắn có thể kết thúc trước khi bạn attach. Không dùng một PID giả rồi kết luận không có thread.

Trong service production chạy lâu, đặt tên và ghi correlation ID ổn định giúp liên kết JFR event với thread dump cùng thời gian. Cũng cần phân biệt Java thread ID với native OS TID (`nid` thường hiển thị hex trong một số dump).

## 11. Làm cho demo giống production hơn mà không làm sai bài học

### 11.1. Thêm metric queue depth và rejected tasks

Fixed pool mặc định có queue không giới hạn; trong service nhận tải cao nên cân nhắc bounded executor:

```java
// Fragment minh họa; cần imports và một namedFactory đã tạo.
// Không phải chương trình độc lập.
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 2,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100),
        namedFactory,
        new ThreadPoolExecutor.AbortPolicy());

int queueDepth = executor.getQueue().size();
int activeWorkers = executor.getActiveCount();
```

`getQueue().size()` và `getActiveCount()` là những phép đo **tức thời/xấp xỉ** dưới concurrency; không thay được historical metric. Với bounded queue, `RejectedExecutionException` có thể xảy ra **trước khi task được worker chạy**. Khi đó `submitted` nên định nghĩa chính xác là **attempted** hay **accepted**: nếu tăng trước `submit`, chỉ số thực tế là attempted; nếu muốn accepted, tăng sau khi `submit` thành công.

Bài lab tăng `submitted` trước `submit`, nhưng không có rejection trong cấu hình và workload demo. Trong production, phân biệt `attempted`, `accepted`, `rejected` rõ ràng để các bất biến có ý nghĩa.

### 11.2. Ghi operation name và correlation ID

Để phân tích theo loại công việc, bổ sung `operation` với tập giá trị hữu hạn như `"cache.refresh"`, `"db.read"`, `"file.write"`. Điều này cho phép group duration theo operation mà không tạo hàng triệu series metric.

Một request có thể có nhiều attempts, nên dùng `requestId` + `attemptId` hoặc trace/span ID. Các giá trị này có cardinality cao: dùng trong JFR/logs/traces với retention phù hợp, **không** dùng như labels cho time-series metrics.

### 11.3. Truyền context khi task đổi thread

`ThreadLocal` hoặc logging MDC không tự được sao chép từ thread nhận request sang worker trong mọi framework. Nên truyền `TaskContext` qua constructor/lambda hoặc thiết lập/clear MDC có kiểm soát:

```java
// Fragment khái niệm: context được truyền vào task.
// MDC cụ thể phụ thuộc logging library của ứng dụng.
executor.submit(() -> processWithContext(context));
```

Khi dùng worker pool, luôn cleanup context trong `finally` để request mới không thừa hưởng request ID của task trước. Với virtual threads/reactive execution, phương án propagation phải phù hợp mô hình concurrency.

### 11.4. Bắt lỗi, timeout và cancellation đúng

Demo cố ý biến lỗi `task-3` thành outcome `ERROR` rồi vẫn trả một `Future<String>` thành công về mặt Java exception flow. Trong hệ thống thật:

- Với `ERROR`, caller có thể cần nhận exception/failure response; telemetry là side effect chẩn đoán, không thay contract.
- Với `TIMEOUT`, cần phân biệt deadline caller và thời điểm downstream thực sự dừng.
- Với `CANCELLED`, restore interrupt khi bắt `InterruptedException` và ngừng xử lý phù hợp; đừng giả định interruption chắc chắn đã giải phóng I/O resource.
- Nếu một task bị **REJECTED trước khi chạy**, không có `begin/end` của worker; ghi riêng rejection event hoặc metric cho đường submit.
- Nếu process bị `SIGKILL`, `finally` có thể không chạy và JFR event chưa commit/file chưa được dump. Monitoring/live logs cần xử lý được telemetry gaps.

Một ứng dụng production nên cân nhắc **một terminal outcome per attempt**, tránh callback completion và timeout cùng ghi hai event kết thúc.

## 12. Hiểu cấu hình JFR để không kết luận sai

### 12.1. Enabled, threshold, stack trace

Trong một recording:

- `enabled` quyết định có thể thu loại event không.
- `threshold` lọc theo **duration nội tại giữa begin và end**. `Duration.ZERO` giữ event dù work nhanh.
- `stackTrace` quyết định có ghi Java stack hay không cho event hỗ trợ.
- `period` thuộc về event định kỳ/lấy mẫu, **không phải** cơ chế tạo event custom `demo.WorkTask` mỗi N ms.

**Trong demo**, Java code chủ động `commit()` mỗi lần task kết thúc. Nếu recording bị tắt hoặc threshold lớn hơn work duration, số JFR events **không bằng** `finished`. Điều đó không mặc định là code mất task — có thể đơn giản là chính sách thu JFR.

Khi cần dùng JFR trong production, không nhất thiết bật `Duration.ZERO` liên tục cho mọi task nếu volume lớn. Bạn có thể lọc các duration events dài, dùng sampling hoặc ghi event chỉ khi có sự cố, nhưng lúc đó mọi phép tổng hợp từ file phải ghi rõ **selection bias**.

### 12.2. JFR không phải kho metrics 24/7 tự nhiên

Một file JFR là snapshot của recording có giới hạn thời gian/dung lượng. Nó không thay monitoring aggregation, alerting, storage/retention. Nếu một service xuất 50.000 task/s và JFR ghi một event mỗi task, dữ liệu và chi phí có thể đáng kể dù JFR thường tối ưu cho low overhead.

Nên quan sát:

- `jfr summary`: event count, những loại event có volume bất thường.
- Recording size và retention.
- CPU/GC overhead trong các đợt bật stack trace hoặc thu chi tiết.
- Cấu hình `jdk.jfr.Recording` / `jcmd JFR.start` và event settings thực tế.
- Khả năng lưu artifact qua container restart.

### 12.3. Dữ liệu nhạy cảm

JFR file có thể chứa thread names, class/method names, file paths, stack traces, metadata của JVM và custom fields. Hãy bảo vệ file `.jfr` như diagnostic artifact có khả năng chứa dữ liệu nhạy cảm. Không gửi public một recording production chưa redaction/kiểm soát quyền.

## 13. Khuyến nghị dashboard tối thiểu

Khi chuyển lab thành service, một dashboard cơ bản nên có **hai tầng**:

| Tầng | Metric/cột | Mục đích |
| --- | --- | --- |
| Component work | `tasks_accepted_total` | Lượng task được chấp nhận |
| Component work | `tasks_completed_total{result="success/error/..."}` | Kết quả theo status |
| Component work | `tasks_active` | Số task đang được worker thực thi |
| Component work | `tasks_queued` | Queue depth tại thời điểm scrape |
| Component work | `task_wait_seconds` histogram | Phân phối thời gian chờ trước thực thi |
| Component work | `task_work_seconds` histogram | Phân phối work duration |
| JVM | Heap used/max/committed | Bối cảnh memory/GC |
| JVM | Live threads, CPU, GC pause | Bối cảnh runtime |
| Diagnostic detail | `demo.WorkTask` event | Task/thread/outcome/duration cụ thể theo thời gian |

Các tên ở bảng là **đề xuất schema**, không được demo tự động export. Với histogram, dùng units nhất quán như seconds theo convention của hệ metrics, thay vì xuất nano giây dưới label `seconds`.

**Lưu ý về status label:** số outcome hữu hạn (SUCCESS/ERROR/CANCELLED...) thường là low-cardinality. `taskId`/`workerName` có thể cao hoặc không ổn định theo scale-out, vì vậy dùng làm field trong event/log nếu cần truy vết, không mặc định làm metric labels ở mọi tổ hợp.

### 13.1. Invariant và cảnh báo

Một vài phép kiểm tra hữu ích sau khi đã định nghĩa chính xác semantics:

- `active >= 0`; active không vượt công suất xử lý được giới hạn trong mô hình nhất định.
- `finished <= accepted` nếu accepted đếm mọi task thực sự được executor nhận và chỉ có một terminal event per task.
- `success + failure == finished` **sau khi xử lý xong và đã đồng bộ đọc** trong demo; trong scrape đồng thời có thể chênh tạm.
- Failure rate tăng bất thường so với baseline (tránh báo động chỉ từ một lỗi đơn lẻ).
- p95/p99 `queue wait` tăng khi `work` ổn định: xem worker saturation/backpressure.
- JFR event count giảm không nhất thiết là task count giảm: kiểm tra `enabled`/`threshold`/recording window.

Tự động alert cần đủ dữ liệu và cửa sổ thời gian, tránh lấy một instantaneous metric làm kết luận.

## 14. Các lỗi dễ gặp khi tự làm lab

**Lỗi 1 — Không dùng ThreadFactory và không biết worker nào làm việc.** Tên mặc định khó đối chiếu; nên đặt prefix theo component và số thứ tự.

**Lỗi 2 — Tưởng bốn task nghĩa là bốn threads.** Executor có hai worker có thể xử lý nhiều task lần lượt; task ID phải độc lập với tên worker.

**Lỗi 3 — Dùng một `long++` cho nhiều threads.** Cập nhật không an toàn dưới concurrency; dùng `LongAdder` hoặc `AtomicLong` theo nhu cầu.

**Lỗi 4 — Quên decrement `active` trên nhánh lỗi.** Gauge tăng mãi và sai; dùng `finally`.

**Lỗi 5 — Gọi `submit` rồi lập tức coi task đã STARTED.** Task có thể chờ queue; đo mốc ở worker thật.

**Lỗi 6 — Lấy hiệu `System.currentTimeMillis()` làm duration chuẩn.** Đồng hồ tường có thể điều chỉnh, độ phân giải hạn chế; dùng `System.nanoTime()` cùng JVM.

**Lỗi 7 — Gắn `@Timespan(NANOSECONDS)` nhưng truyền milliseconds.** Công cụ sẽ diễn giải sai duration; kiểm tra đơn vị tại nguồn.

**Lỗi 8 — Bỏ `event.commit()`.** Tạo event object và gọi begin/end chưa đủ để ghi custom event.

**Lỗi 9 — Không enable event trong recording.** Có thể có 0 event dù code gọi commit; cần đúng recording, tên event và settings.

**Lỗi 10 — Threshold quá cao.** Event của task chờ queue rất lâu nhưng xử lý nhanh vẫn có thể bị lọc vì intrinsic event duration chỉ bao work.

**Lỗi 11 — Dùng stackTrace=true cho mọi task cực dày.** Stack trace có chi phí; bật khi cần vị trí code, cân nhắc sampling/threshold.

**Lỗi 12 — Gọi `RecordingFile.readAllEvents` cho file rất lớn.** Có thể giữ hàng triệu event trong heap; dùng `hasMoreEvents()/readEvent()` và aggregate có giới hạn.

**Lỗi 13 — Cộng `workedNanos` rồi gọi đó là wall time.** Worker chạy song song; tổng durations không phải elapsed time toàn pool.

**Lỗi 14 — Lấy trung bình và suy ra p99.** Không thể dựng percentiles từ tổng và count; cần histogram/distribution.

**Lỗi 15 — In mọi task ID dưới dạng metric label.** Cardinality bùng nổ; ID dùng cho logs/JFR/traces, metrics cho category.

**Lỗi 16 — Nuốt exception khi thu metrics.** Code demo xử lý lỗi có chủ đích; trong ứng dụng thật phải bảo toàn hợp đồng báo lỗi.

**Lỗi 17 — Không shutdown executor.** Non-daemon worker threads có thể giữ JVM sống; dùng `shutdown`/`awaitTermination` và cleanup an toàn.

**Lỗi 18 — Kết luận không có sự cố vì JFR vắng event.** Có thể recording disabled, threshold, sampling, thiếu file, sai process hoặc recording window.

## 15. Bài tập thực hành mở rộng

### Bài A — Tính toán metric từ bốn task

Giả sử (số liệu **minh họa**) bốn task có:

| Task | Queue wait | Work | Outcome |
| --- | ---: | ---: | --- |
| task-1 | 5 ms | 30 ms | SUCCESS |
| task-2 | 6 ms | 31 ms | SUCCESS |
| task-3 | 36 ms | 32 ms | ERROR |
| task-4 | 38 ms | 30 ms | SUCCESS |

Hãy tính tổng queue wait, tổng work, average work và số lỗi.

**Đáp án:** Tổng queue wait = `5+6+36+38=85 ms`. Tổng work = `30+31+32+30=123 ms`. Average work = `123/4=30,75 ms`. Số ERROR = `1`. **Không thể** kết luận elapsed wall-clock toàn pool bằng `123 ms` vì task có thể chồng lấp.

### Bài B — Sửa cấu hình pool

Đổi số worker từ 2 xuống 1 (chỉ trong môi trường lab) và chạy lại nhiều lần. Quan sát queue wait trong JFR có xu hướng tăng với những task đến sau không? Vì sao tổng work có thể tương đối ổn định?

**Gợi ý:** Khi một worker xử lý tuần tự, task sau đợi nhiều hơn trong khi công việc mô phỏng 30 ms không thay đổi đáng kể. Kết quả thực vẫn có scheduling overhead; đừng giả định duration tuyệt đối.

### Bài C — Lấy histogram

Muốn biết p99 task latency từ metrics, `workedNanos.sum()` và `finished.sum()` đã đủ chưa?

**Đáp án:** Không. Hai số cho average trên tập task đã hoàn tất, không mô tả phân phối. Dùng histogram/timer; kiểm tra kết quả theo operation và outcome với đủ lượng dữ liệu.

### Bài D — Bắt lỗi nhưng không mất semantics

Trong demo, `task-3` được ghi `ERROR` nhưng `Future.get()` không ném vì `execute()` đã bắt exception. Hãy đề xuất cách để caller vẫn nhận lỗi mà telemetry không thiếu.

**Gợi ý:** Ghi outcome/metric/JFR event trong `catch/finally`, rồi propagate exception hoặc hoàn thành `CompletableFuture` thất bại theo contract. Đảm bảo không ghi hai terminal events.

### Bài E — JFR thiếu hai event

Bạn bật `threshold=100 ms` nhưng work mô phỏng chỉ khoảng 30 ms. File JFR xuất hiện 0 `demo.WorkTask` events dù `finished=4`. Đây có phải mất task không?

**Đáp án:** Chưa chắc. `threshold` lọc theo intrinsic duration của event. Có thể tất cả task đều được hoàn tất nhưng bị filter. Kiểm tra `enabled`, recording window và event settings trước khi kết luận telemetry lỗi.

### Bài F — Đọc stack trace

Đổi `withoutStackTrace()` sang `withStackTrace()` trong recording, rồi kiểm tra `getStackTrace()` hoặc JMC. Vì sao stack event không mặc định là full request trace?

**Gợi ý:** Stack chỉ phản ánh call stack tại điểm JFR thu event, không chứa mọi service hop/thread handoff. Cần trace IDs và distributed tracing nếu muốn full causal path.

### Bài G — Cùng tên thread ở hai pods

Hai replica đều có `diag-worker-1`. Làm sao ghép event đúng instance?

**Đáp án:** Dùng thêm pod/container identity, process start, PID/host namespace, JFR file/recording ID, thời gian và `taskId/traceId`. Tên thread không phải khóa toàn cục.

## 16. Checklist hoàn tất bài thực hành

- [ ] File `ThreadMetricsJfrLab.java` biên dịch được với `javac --release 17`.
- [ ] Dùng một `ThreadFactory` để đặt tên `diag-worker-1`/`diag-worker-2`.
- [ ] Có `ExecutorService` với hai worker và cleanup bằng `shutdown`/`awaitTermination`.
- [ ] Các counter submitted/finished/successes/failures nhất quán sau khi Future hoàn tất.
- [ ] Gauge `active` tăng khi bắt đầu và giảm trong `finally`, cuối chương trình về 0.
- [ ] `peakActive` được cập nhật atomic, không vượt pool size trong demo.
- [ ] Queue/work durations dùng `System.nanoTime()` cùng JVM, đơn vị nano giây.
- [ ] Custom event có `@Name`, `@Category`, `@Label` và `@Timespan` phù hợp.
- [ ] Có `Event.begin()`, `end()` và `commit()` đúng thứ tự và outcome ở nhánh lỗi.
- [ ] Recording enable `demo.WorkTask`, threshold đủ thấp để giữ các event demo.
- [ ] File `thread-metrics-lab.jfr` được dump và đọc bằng `RecordingFile`.
- [ ] Phân biệt event duration nội tại với `queueNanos` riêng của ứng dụng.
- [ ] `jfr summary` báo có 4 `demo.WorkTask` events khi demo chạy đúng.
- [ ] Output cuối là `checks=PASS`; không hardcode nanosecond/worker mapping.
- [ ] Hiểu metric labels cardinality, privacy của JFR và sự khác nhau giữa lab và production.
- [ ] Có khả năng ghép task event với runtime GC/CPU/thread nếu các event JVM đó được thu.

**Điểm cần nhớ:** Thread names trả lời **worker nào**; counters/gauges/timers trả lời **bao nhiêu, đang chạy bao nhiêu, chờ và xử lý bao lâu**; custom JFR events trả lời **mỗi task cụ thể mang outcome và duration nào trong thời gian JVM hoạt động**. Cả ba nguồn bổ sung cho nhau. Khi triển khai thực tế, phải giữ correlation ID, đơn vị thời gian, lifecycle và cấu hình ghi nhất quán để tránh kết luận sai.

## Tài liệu đối chiếu

- Oracle Java 17 — [`ThreadFactory` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadFactory.html): cách tạo và đặt tên worker.
- Oracle Java 17 — [`Executors` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): fixed thread pool, thread factory và cách executor quản lý task.
- Oracle Java 17 — [`LongAdder` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counters dưới concurrency, giới hạn của `sum()`.
- Oracle Java 17 — [`System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): phép đo elapsed time.
- Oracle JDK 21 — [`jdk.jfr.Event` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html): `begin`, `end`, `commit` và thu custom event.
- Oracle JDK 21 — [`Recording` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): enable event, start/stop/dump.
- Oracle JDK 21 — [`@Timespan` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Timespan.html): khai báo units cho duration fields.
- Oracle JDK 21 — [`RecordingFile` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc event từ file `.jfr`.
- Oracle JDK 21 — [`RecordedEvent` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): type, field, duration, thread metadata.
- Oracle JDK 21 — [`jfr` CLI](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `summary`, `print`, `metadata`.
- Oracle JDK 21 — [`jcmd` CLI](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print` và JFR diagnostics.