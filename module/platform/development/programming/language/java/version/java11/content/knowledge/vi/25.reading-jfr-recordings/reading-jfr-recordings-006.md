# Đọc bản ghi JFR: Phân tích CPU, khóa, I/O và GC trong Java 11+

> **Phạm vi:** Java Flight Recorder (JFR), đặc biệt là `jdk.jfr.consumer.RecordingFile`, `RecordedEvent`, `RecordedObject` và `RecordedStackTrace`. Mục tiêu là đọc file `.jfr` để tìm **CPU hotspots**, **monitor contention/park**, **file/socket I/O latency**, và **GC pauses/heap trend**. Các API chính có từ Java 11 và vẫn dùng được trong JDK hiện đại. Các ví dụ có thể biên dịch với `javac --release 11`; dữ liệu JFR thực tế phụ thuộc JDK, collector, OS, cấu hình ghi và workload.

## 1. Mục tiêu

Hoàn thành bài này, bạn có thể:

1. Mở `.jfr` bằng `RecordingFile` theo cách **streaming**; không tải toàn bộ file vào heap.
2. Phân tích `getEventType().getName()`, `getStartTime()`, `getDuration()`, `getStackTrace()` và fields theo `hasField`.
3. Phân biệt **CPU load** với **execution samples**; xác định hot method/call path mà không nhầm sample count với method invocation count.
4. Phân biệt **`JavaMonitorEnter`**, **`JavaMonitorWait`**, **`ThreadPark`**; đọc thời gian chờ, stack, owner khi được ghi.
5. Tổng hợp `FileRead`/`FileWrite`/`SocketRead`/`SocketWrite` với count, duration, bytes đã ghi nhận.
6. Phân biệt `GarbageCollection` (một collection) với `GCPhasePause` (pause) và `GCHeapSummary` (trạng thái heap).
7. Chọn **time window** theo incident, so baseline, không cộng durations của các operations song song thành wall-clock elapsed.
8. Hiểu **threshold, period, stackTrace settings**, các điểm mù sampling và vì sao event vắng mặt không chứng minh thao tác không xảy ra.
9. Chạy ví dụ Java 11 độc lập ghi và đọc JFR với bốn loại workload, có stdout đã kiểm thử.
10. Dùng `jfr summary`/`jfr print` và JMC để đối chiếu; thiết kế báo cáo có thể audit và an toàn dữ liệu.

## 2. JFR chứa gì?

JFR lưu **events có timestamp**, được JVM/JDK và ứng dụng phát ra. Event có thể chứa:

- Tên event type như `jdk.CPULoad`, `jdk.ExecutionSample`, `jdk.JavaMonitorEnter`, `jdk.SocketRead`, `jdk.GarbageCollection`.
- Thời gian bắt đầu/kết thúc và `Duration` khi event đại diện cho thao tác có thời lượng.
- Metadata/fields: mức CPU, bytes, gcId, tên GC, class monitor, thread, path/host (khi được bật/ghi).
- Stack trace, nếu event/recording có cấu hình ghi.
- Custom events của ứng dụng để liên hệ nghiệp vụ với sự kiện runtime.

~~~text
                     JFR (.jfr) + event timeline
                                  |
          +-----------------------+-------------------------+
          |                       |                         |
       CPU events              Lock events                I/O events
          |                       |                         |
 CPULoad, samples     JavaMonitorEnter / Wait       File / Socket Read/Write
          |                       |                         |
 load vs hot code     contention vs normal wait      duration vs bytes
                                  |
                              GC events
                                  |
                 GarbageCollection / GCPhasePause /
                           GCHeapSummary
                                  |
                        correlation theo thời gian
                                  |
                      Giả thuyết -> đo kiểm lại
~~~

**JFR không phải heap dump hoặc thread dump**. File JFR thường không chứa đầy đủ object reference graph để tìm GC roots; nếu cần retained object graph, dùng heap dump. Một stack sample cũng không tương đương với ảnh chụp đầy đủ trạng thái tất cả threads tại một thời điểm.

## 3. Ma trận: triệu chứng nào xem nhóm event nào?

| Triệu chứng | Event JFR ưu tiên | Điều kiện cần đối chiếu |
| --- | --- | --- |
| CPU quá cao, throughput giảm | `jdk.CPULoad`, `ThreadCPULoad`, `ExecutionSample` | OS/container CPU limits, GC/JIT, tải |
| Latency cao nhưng CPU thấp | `JavaMonitorEnter`, `ThreadPark`, `SocketRead`/`FileRead` | Request tracing, downstream metrics |
| Nghi contention ở `synchronized` | `JavaMonitorEnter` | Stack, `monitorClass`, duration, threshold |
| Nghi chờ queue/`ReentrantLock` | `ThreadPark` | Thread role, stack, thread dump |
| Socket read chậm | `SocketRead` | Peer/server latency, proxy, pool, tracing |
| File I/O chậm | `FileRead`/`FileWrite` | Disk/device metrics, path group, throughput |
| p99 spike trùng GC | `GCPhasePause` và `GarbageCollection` | Request timestamps, actual STW pause |
| Heap sau GC tăng dần | `GCHeapSummary`, GC metrics/allocation samples | Workload baseline, heap dump nếu cần roots |
| Nghi deadlock | JFR lock events hỗ trợ | **Thread dump/deadlock detector** xác nhận vòng chờ |

Không gọi một công cụ “chiếm 80%” nếu chưa xác định **80% của metric nào**: CPU utilization, tỷ lệ sampled stacks, cumulative I/O wait hay STW pause đều khác nhau.

## 4. Ghi đủ sự kiện trước khi phân tích

Trước khi truy vấn file, hỏi:

- Recording có được bật ở **đúng JVM/PID** và **đúng thời điểm incident** không?
- Dùng `default.jfc` hay `profile.jfc`? Các events cần thiết đã enable chưa?
- `threshold` có thể bỏ các thao tác quá ngắn không?
- `period` của CPU sampling có đủ độ phân giải theo time window không?
- `stackTrace` có được bật để xác định call path không?
- `maxage`/`maxsize` có làm dữ liệu cũ bị loại không?
- Có một khoảng thời gian khác được thu do timezone/clock drift không?

### default và profile

- `default.jfc` thường cân bằng overhead/dữ liệu cho recording dài hơn.
- `profile.jfc` thường ghi thêm samples hoặc events phục vụ chẩn đoán.
- **Không** coi `profile` là thứ phải bật vô hạn trên mọi production.
- Một số các event/heap statistic có thể gây chi phí cao; lựa chọn theo nhu cầu và benchmark.
- File chứa một event type nhưng thiếu instance có thể đơn giản vì workload chưa phát sinh hoặc threshold chưa đạt.

### EventSettings Java 11

~~~java
recording.enable("jdk.CPULoad")
         .withPeriod(Duration.ofMillis(200));

recording.enable("jdk.ExecutionSample")
         .withPeriod(Duration.ofMillis(20));

recording.enable("jdk.JavaMonitorEnter")
         .withThreshold(Duration.ofMillis(10));

recording.enable("jdk.FileRead")
         .withThreshold(Duration.ofMillis(10));

recording.enable("jdk.GCPhasePause");
~~~

**Đoạn minh họa** trong method có `Recording recording`. Mức 10 ms, 20 ms và 200 ms là giá trị được ví dụ **chủ động chọn**, không phải mặc định bất biến của mọi JDK. Đặt threshold thấp hơn có thể tăng số events, overhead và dung lượng JFR, nên chỉ giảm trong phiên điều tra có giới hạn.

## 5. API đọc JFR trong Java 11

| API | Chức năng |
| --- | --- |
| `RecordingFile(Path)` | Mở file `.jfr` |
| `hasMoreEvents()` | Kiểm còn event hay không |
| `readEvent()` | Đọc một `RecordedEvent` tiếp theo |
| `RecordedEvent.getEventType().getName()` | Lấy định danh event type |
| `RecordedEvent.getStartTime()/getEndTime()` | Thời gian dạng `Instant` |
| `RecordedEvent.getDuration()` | `Duration` của event |
| `RecordedEvent.getStackTrace()` | Stack hoặc `null` |
| `RecordedEvent.getThread()` | Event thread nếu được ghi |
| `RecordedObject.hasField(name)` | Field có tồn tại không? |
| `RecordedObject.getDouble/getLong/getString` | Truy cập dữ liệu kiểu cụ thể |
| `RecordedObject.getValue(name)` | Truy cập field dạng object hoặc nested |
| `RecordedEvent.getFields()` | Metadata tên/kiểu fields |

### Mẫu streaming

~~~java
Path file = Paths.get("incident.jfr");

try (RecordingFile reader = new RecordingFile(file)) {
    while (reader.hasMoreEvents()) {
        RecordedEvent event = reader.readEvent();
        String type = event.getEventType().getName();

        if ("jdk.CPULoad".equals(type)) {
            // Tính aggregate theo field có thực.
        }
    }
}
~~~

**Đoạn minh họa**, cần imports `Path`, `Paths`, `RecordedEvent`, `RecordingFile` và xử lý checked exceptions.

### Vì sao không đọc toàn bộ file vào List?

`RecordingFile.readAllEvents(file)` hợp lý với test nhỏ. Nhưng một recording nhiều giờ có thể tạo hàng triệu events; giữ cả `List<RecordedEvent>` làm memory footprint tăng mạnh. Đọc streaming, giữ counters/histograms/top-N aggregates rồi bỏ tham chiếu events là mặc định tốt cho parser production.

## 6. Schema: đừng đoán field name/kiểu dữ liệu

Javadoc `RecordedObject` khuyến nghị kiểm field trước khi truy cập: tên/kiểu field có thể khác theo event type hoặc đổi giữa các bản JDK.

~~~java
if (event.hasField("jvmUser")
        && event.hasField("jvmSystem")) {
    double load = event.getDouble("jvmUser")
            + event.getDouble("jvmSystem");
}
~~~

**Đoạn minh họa**: có `hasField` không tự chứng minh field khác null, và typed getter vẫn có thể ném `IllegalArgumentException` nếu kiểu không phù hợp. Với các loại event lạ, trước tiên liệt kê metadata:

~~~java
for (ValueDescriptor field : event.getFields()) {
    System.out.println(field.getName()
            + " : " + field.getTypeName());
}
~~~

**Đoạn minh họa** với import `jdk.jfr.ValueDescriptor`, chạy trên **một số event mẫu**, không in toàn bộ file chứa hàng triệu events hoặc thông tin nhạy cảm.

### Cẩn trọng với stack trace

~~~java
RecordedStackTrace trace = event.getStackTrace();

if (trace != null && !trace.getFrames().isEmpty()) {
    RecordedFrame top = trace.getFrames().get(0);
    // Có stack mẫu để phân tích.
}
~~~

Stack có thể bằng `null` vì event không chứa stack hoặc setting `stackTrace=false`; không được coi đó là file hỏng.

## 7. CPU: jdk.CPULoad khác execution samples

### jdk.CPULoad

`jdk.CPULoad` là event **theo chu kỳ**, có các field thường gặp:

- `jvmUser`: tỷ lệ CPU time JVM ở user mode;
- `jvmSystem`: tỷ lệ CPU time JVM ở system/kernel mode;
- `machineTotal`: CPU load của toàn máy.

~~~java
if ("jdk.CPULoad".equals(type)
        && event.hasField("jvmUser")
        && event.hasField("jvmSystem")) {
    double jvmFraction = event.getDouble("jvmUser")
            + event.getDouble("jvmSystem");
    double percent = jvmFraction * 100.0;
}
~~~

**Đoạn minh họa**. Đây là fraction do event cung cấp, **không** phải phần trăm latency của một request, cũng không mặc định là “số lõi CPU” trong container. Để diễn giải đúng, kiểm CPU quotas, số CPUs, OS telemetry và cách JDK/provider ghi CPU load.

### jdk.ThreadCPULoad

`jdk.ThreadCPULoad` đo hoạt động CPU theo thread trong khoảng thời gian. Nó giúp nhận diện thread có CPU load đáng chú ý, nhưng không đủ xác định chính xác method hot nếu không có stack/call path.

**Thread ID** cần được đặt trong ngữ cảnh của một recording/process; không dùng thread ID thô để nối các JVM khác nhau.

### jdk.ExecutionSample / jdk.NativeMethodSample

Đây là **stack samples** của threads được quan sát khi đang thực thi; thường dùng để xây flame graph/call tree.

~~~java
RecordedStackTrace trace = event.getStackTrace();

if (trace != null && !trace.getFrames().isEmpty()) {
    RecordedFrame top = trace.getFrames().get(0);

    if (top.getMethod() != null
            && top.getMethod().getType() != null) {
        String key = top.getMethod().getType().getName()
                + "#" + top.getMethod().getName();
        sampleCounts.merge(key, 1L, Long::sum);
    }
}
~~~

**Đoạn minh họa**, `sampleCounts` là `Map<String,Long>`. Đếm **sample count**, không phải số lần gọi method.

Nếu event có `sampledThread`:

~~~java
if (event.hasField("sampledThread")) {
    RecordedThread sampled =
            event.getThread("sampledThread");

    if (sampled != null) {
        String name = sampled.getJavaName();
        // Aggregate theo role của thread; không log tên nhạy cảm.
    }
}
~~~

`event.getThread()` là event thread; với execution sample, `sampledThread` có thể là field thích hợp. Không suy ra mọi event đều dùng cùng một trường thread.

### Đọc CPU samples đúng

- 500 mẫu liên quan `Parser.parse` **không có nghĩa** 500 lời gọi `parse`.
- 40% samples **không tự bằng** 40% request latency.
- Mẫu ít có sai số thống kê lớn.
- CPU sampling thường bỏ lỡ threads **đang chờ socket/lock/queue**.
- Top frame không luôn đủ giải thích hot path: xem **full call tree**.
- JVM GC/JIT/native threads có thể chiếm CPU nhưng không thuộc code nghiệp vụ.

## 8. Khóa: JavaMonitorEnter, JavaMonitorWait, ThreadPark

| Loại event | Phản ánh | Lưu ý |
| --- | --- | --- |
| `jdk.JavaMonitorEnter` | Thread chờ **chiếm monitor** khi tranh `synchronized` | Một lần monitor enter không bị contention có thể không xuất hiện |
| `jdk.JavaMonitorWait` | Thread ở cơ chế `Object.wait` | Không đồng nhất với monitor acquisition |
| `jdk.ThreadPark` | Thread đang park, ví dụ `LockSupport.park` | Có thể là `ReentrantLock` hoặc đợi queue bình thường |
| `jdk.ThreadSleep` | Ngủ theo yêu cầu | Sleep hợp lệ không phải deadlock |

### Đọc monitor contention duration

~~~java
if ("jdk.JavaMonitorEnter".equals(type)) {
    Duration waited = event.getDuration();

    if (waited.compareTo(Duration.ofMillis(100)) > 0) {
        // Candidate cho lock hotspot cần điều tra.
    }
}
~~~

**Đoạn minh họa**. Chỉ số cần báo: **count, max, p95/p99 của recorded waits, top stack/monitor class, event threshold và time window**.

Các fields `monitorClass`, `previousOwner` hoặc `eventThread` có thể hữu ích khi có trong schema; kiểm `hasField` rồi mới truy cập.

~~~java
if (event.hasField("monitorClass")) {
    Object value = event.getValue("monitorClass");

    if (value instanceof RecordedClass) {
        String className = ((RecordedClass) value).getName();
        // Group theo loại monitor, không suy ra object identity.
    }
}
~~~

**Đoạn minh họa**, cần import `RecordedClass`. Một class có thể có hàng nghìn object monitors, nên group theo class không xác định duy nhất lock instance.

### Không nhầm contention với deadlock

- 10.000 lần chờ 10 μs có thể làm giảm throughput nhưng bị threshold 20 ms **lọc hết**.
- Một lần chờ 4 s làm hỏng p99 dù count thấp.
- `ThreadPark` của worker chờ queue rỗng có thể hợp lệ.
- **Deadlock** đòi xác nhận vòng chờ/owner bằng thread dump, `ThreadMXBean.findDeadlockedThreads()` hoặc công cụ tương ứng; một event JFR riêng lẻ chưa đủ.

## 9. I/O: FileRead, FileWrite, SocketRead, SocketWrite

Bốn loại event thường có:

| Event | Thời lượng | Bytes field | Ngữ cảnh có thể có |
| --- | --- | --- | --- |
| `jdk.FileRead` | Một thao tác đọc file | `bytesRead` | `path` |
| `jdk.FileWrite` | Một thao tác ghi file | `bytesWritten` | `path` |
| `jdk.SocketRead` | Một lần đọc socket | `bytesRead` | `host`, `port`, stack |
| `jdk.SocketWrite` | Một lần ghi socket | `bytesWritten` | `host`, `port`, stack |

### Tổng bytes quan sát được

~~~java
if (("jdk.FileRead".equals(type)
        || "jdk.SocketRead".equals(type))
        && event.hasField("bytesRead")) {
    observedBytes += Math.max(0L,
            event.getLong("bytesRead"));
}
~~~

**Đoạn minh họa**: `observedBytes` **chỉ gồm các recorded events**, không phải tổng bytes thật của process. Những calls nhanh hơn threshold hoặc events chưa bật có thể không ghi vào file. Giá trị âm có thể đại diện sentinel như EOF; clamp về 0 để báo số byte có ích, không làm thay đổi field gốc.

### Duration I/O không đồng nghĩa tốc độ mạng

`SocketRead` mất 2 s có thể vì peer chậm, long-poll, connection pool, proxy, request scheduling, hoặc ứng dụng chưa gửi dữ liệu. Không kết luận “Internet chậm” chỉ từ duration. Đối chiếu server traces, metrics, timeouts và traffic.

`SocketWrite` lâu có thể là backpressure, send buffer, network hay scheduling. Event ghi thành công không chứng minh **business transaction ở peer** đã thành công.

### Ngưỡng ghi và I/O nhỏ

Oracle JFR troubleshooting ghi nhận nhiều application events có threshold khoảng **20 ms** trong các cấu hình thường gặp. Nếu một FileRead mất 50 μs, có thể có hàng nghìn lần thực hiện mà không event nào vượt threshold.

Nếu nghi nhiều I/O nhỏ, giảm threshold **có thời hạn** trong staging hoặc một phiên đo được duyệt; theo dõi overhead và kích thước recording. Không bật threshold 0 kéo dài trên production traffic cao mà chưa đánh giá.

### Giữ bí mật path/host

JFR `path`, `host`, thread name và stack trace có thể chứa chi tiết hệ thống nội bộ. Dùng nhóm tài nguyên đã chuẩn hóa, không in raw token/hostname/customer ID ra báo cáo công khai.

## 10. GC: collection, pause, heap summary

### jdk.GarbageCollection

Một event cho **một GC collection**, có thể chứa `gcId`, `name`, `cause` và `duration`. Tùy collector, một phần xử lý GC chạy **concurrently** với application. Vì vậy:

**`GarbageCollection.duration` không tự đồng nghĩa stop-the-world pause duration.**

### jdk.GCPhasePause

`GCPhasePause` là nguồn phù hợp hơn để phân tích **pause ảnh hưởng thread ứng dụng**. Khi tính tổng, tránh cộng chồng các subphase event types có quan hệ cha/con như các `GCPhasePauseLevel...`, vì có thể đếm trùng một pause.

~~~java
if ("jdk.GCPhasePause".equals(type)) {
    Duration pause = event.getDuration();

    if (pause.compareTo(Duration.ofMillis(100)) > 0) {
        // Đối chiếu timestamp với p95/p99 request latency.
    }
}
~~~

**Đoạn minh họa**. Một long collection có thể có nhiều pause events. Report nên chứa **count, max pause, tổng pause theo đúng event semantics** và time window, không chỉ duration của collection.

### jdk.GCHeapSummary

`jdk.GCHeapSummary` có thể chứa `heapUsed` cùng `gcId` và giá trị xác định **Before GC / After GC**. Để xem retention:

1. Ghép các records theo `gcId` khi có;
2. So sánh heap **sau GC** giữa nhiều lần collection;
3. Đối chiếu request volume và cache warm-up;
4. Xem allocation rate và GC frequency;
5. Nếu heap sau GC tăng dai dẳng, dùng heap dump/GC roots để tìm ai giữ references.

**Một heapUsed cao không tự chứng minh memory leak.** JFR không thay thế full object graph của heap dump. Native/off-heap memory cũng không được biểu diễn đầy đủ bởi `heapUsed`.

## 11. Time window và correlation

### Lọc đúng khoảng incident

~~~java
Instant from = Instant.parse("2026-11-07T09:00:00Z");
Instant to = Instant.parse("2026-11-07T09:01:00Z");

Instant start = event.getStartTime();
Instant end = event.getEndTime();

boolean overlaps = !end.isBefore(from)
        && !start.isAfter(to);
~~~

**Đoạn minh họa**, cần import `java.time.Instant`. Lọc bằng overlap giúp giữ event bắt đầu trước nhưng kéo dài vào cửa sổ. Khi tính thời gian **chỉ nằm trong window**, phải clip interval theo hai biên; chỉ lọc overlap chưa đủ.

### Các lỗi thống kê thời gian

~~~text
SocketRead A: từ 10:00:00 đến 10:00:02 -> duration 2 giây
SocketRead B: từ 10:00:00 đến 10:00:02 -> duration 2 giây

Cumulative I/O duration = 4 giây
Wall-clock elapsed       = 2 giây
~~~

Đừng nói “server bị đứng 4 giây” khi hai operations chạy đồng thời. Duration sum của nhiều threads là **cumulative operation time**, không phải elapsed end-to-end latency.

### JFR và request tracing

JFR không tự ghi request ID của mọi HTTP request. Nếu cần correlation:

- Lưu metadata về JVM PID, JDK version, deployment, pod ID, timezone và recording settings;
- Đối chiếu incident timestamps với traces/metrics;
- Dùng custom JFR events có checkpoint/trace ID **được kiểm soát, không chứa PII** nếu cần;
- Kiểm lệch đồng hồ giữa các services trước khi quy kết một event gây lỗi ở service khác.

## 12. Chương trình Java 11 hoàn chỉnh: tự ghi và phân tích bốn nhóm

Ví dụ sau không cần Internet, database hay server ngoài. Chương trình có hai mode:

- `capture`: dùng JFR profile recording có giới hạn; tạo CPU work, monitor contention, file read/write và GC thử nghiệm. Tự phát **4 custom checkpoints** tên `lesson.DiagnosticCheckpoint`.
- `analyze`: đọc file bằng `RecordingFile` theo streaming pattern, phân nhóm `CPU / Lock / I/O / GC` và đếm top frames của execution samples.
- Không cố xác nhận số CPU samples, số lock/I/O/GC events cố định: JFR là hệ thống ghi theo sampling/threshold.

**Lưu ý:** `System.gc()` bên dưới chỉ nhằm tạo tình huống test; **không phải hướng dẫn gọi System.gc trong ứng dụng sản xuất**. JVM có thể tắt explicit GC hoặc dùng collector khác.

Tạo file **`JfrFourPillarsDemo.java`**:

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class JfrFourPillarsDemo {
    private static final Object MONITOR = new Object();
    private static volatile long cpuResult;

    @Name("lesson.DiagnosticCheckpoint")
    static class Checkpoint extends Event {
        String stage;
    }

    private static void checkpoint(String name) {
        Checkpoint event = new Checkpoint();
        event.stage = name;
        event.commit();
    }

    private static void cpuWork() {
        long until = System.nanoTime()
                + Duration.ofMillis(850).toNanos();
        long value = 1;
        while (System.nanoTime() < until) {
            value = (value * 1103515245L + 12345L)
                    ^ (value >>> 13);
        }
        cpuResult = value;
    }

    private static void lockWork() throws InterruptedException {
        CountDownLatch holding = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        Thread holder = new Thread(() -> {
            synchronized (MONITOR) {
                holding.countDown();
                try {
                    release.await(3, TimeUnit.SECONDS);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-lock-holder");
        Thread waiter = new Thread(() -> {
            synchronized (MONITOR) {
                cpuResult++;
            }
        }, "demo-lock-waiter");
        holder.start();
        holding.await();
        waiter.start();
        Thread.sleep(160);
        release.countDown();
        holder.join();
        waiter.join();
    }

    static void capture(Path output) throws Exception {
        Path temp = Files.createTempFile("jfr-io-", ".txt");
        try (Recording recording = new Recording(
                Configuration.getConfiguration("profile"))) {
            recording.setToDisk(true);
            recording.setMaxSize(32L * 1024 * 1024);
            recording.enable(Checkpoint.class);
            recording.enable("jdk.CPULoad")
                    .withPeriod(Duration.ofMillis(200));
            recording.enable("jdk.ExecutionSample")
                    .withPeriod(Duration.ofMillis(20));
            recording.enable("jdk.JavaMonitorEnter")
                    .withThreshold(Duration.ZERO);
            recording.enable("jdk.ThreadPark")
                    .withThreshold(Duration.ZERO);
            recording.enable("jdk.FileRead")
                    .withThreshold(Duration.ZERO);
            recording.enable("jdk.FileWrite")
                    .withThreshold(Duration.ZERO);
            recording.enable("jdk.SocketRead")
                    .withThreshold(Duration.ZERO);
            recording.enable("jdk.SocketWrite")
                    .withThreshold(Duration.ZERO);
            recording.enable("jdk.GarbageCollection");
            recording.enable("jdk.GCPhasePause");
            recording.enable("jdk.GCHeapSummary");
            recording.start();

            checkpoint("CPU");
            cpuWork();
            checkpoint("LOCK");
            lockWork();
            checkpoint("IO");
            Files.write(temp, "Java JFR sample"
                    .getBytes(StandardCharsets.UTF_8));
            Files.readAllBytes(temp);
            checkpoint("GC");
            System.gc(); // Test only, không dùng như phương án GC tuning.
            Thread.sleep(350);

            recording.stop();
            recording.dump(output);
        } finally {
            Files.deleteIfExists(temp);
        }
        System.out.println("capture.fileExists="
                + Files.isRegularFile(output));
    }

    private static final class Summary {
        long checkpoints, cpuLoads, samples;
        long monitorEvents, parkEvents;
        long ioEvents, ioBytes;
        long gcEvents, gcPauseEvents, gcHeapSummaries;
        double maxJvmCpu = 0;
        long maxMonitorNanos = 0;
        long maxGcPauseNanos = 0;
        Map<String, Long> sampleTopFrames = new HashMap<>();

        void consume(RecordedEvent event) {
            String name = event.getEventType().getName();
            switch (name) {
                case "lesson.DiagnosticCheckpoint":
                    checkpoints++;
                    break;
                case "jdk.CPULoad":
                    cpuLoads++;
                    if (event.hasField("jvmUser")
                            && event.hasField("jvmSystem")) {
                        double v = event.getDouble("jvmUser")
                                + event.getDouble("jvmSystem");
                        maxJvmCpu = Math.max(maxJvmCpu, v);
                    }
                    break;
                case "jdk.ExecutionSample":
                case "jdk.NativeMethodSample":
                    samples++;
                    RecordedStackTrace stack = event.getStackTrace();
                    if (stack != null
                            && !stack.getFrames().isEmpty()) {
                        RecordedFrame top = stack.getFrames().get(0);
                        if (top.getMethod() != null
                                && top.getMethod().getType() != null) {
                            String symbol =
                                    top.getMethod().getType().getName()
                                    + "#" + top.getMethod().getName();
                            sampleTopFrames.merge(
                                    symbol, 1L, Long::sum);
                        }
                    }
                    break;
                case "jdk.JavaMonitorEnter":
                    monitorEvents++;
                    maxMonitorNanos = Math.max(
                            maxMonitorNanos,
                            event.getDuration().toNanos());
                    break;
                case "jdk.ThreadPark":
                    parkEvents++;
                    break;
                case "jdk.FileRead":
                case "jdk.SocketRead":
                    ioEvents++;
                    if (event.hasField("bytesRead")) {
                        ioBytes += Math.max(
                                0L, event.getLong("bytesRead"));
                    }
                    break;
                case "jdk.FileWrite":
                case "jdk.SocketWrite":
                    ioEvents++;
                    if (event.hasField("bytesWritten")) {
                        ioBytes += Math.max(
                                0L, event.getLong("bytesWritten"));
                    }
                    break;
                case "jdk.GarbageCollection":
                    gcEvents++;
                    break;
                case "jdk.GCPhasePause":
                    gcPauseEvents++;
                    maxGcPauseNanos = Math.max(
                            maxGcPauseNanos,
                            event.getDuration().toNanos());
                    break;
                case "jdk.GCHeapSummary":
                    gcHeapSummaries++;
                    break;
                default:
                    // Có thể có nhiều JVM event types khác.
            }
        }
    }

    static void analyze(Path source) throws Exception {
        Summary summary = new Summary();
        try (RecordingFile reader = new RecordingFile(source)) {
            while (reader.hasMoreEvents()) {
                summary.consume(reader.readEvent());
            }
        }
        System.out.println("checkpoints=" + summary.checkpoints);
        System.out.println("cpu.loadEvents=" + summary.cpuLoads);
        System.out.println("cpu.sampleEvents=" + summary.samples);
        System.out.println("cpu.peakJvmFraction="
                + String.format(java.util.Locale.ROOT,
                        "%.3f", summary.maxJvmCpu));
        System.out.println("lock.monitorEvents=" + summary.monitorEvents);
        System.out.println("lock.parkEvents=" + summary.parkEvents);
        System.out.println("io.eventCount=" + summary.ioEvents);
        System.out.println("io.bytesObserved=" + summary.ioBytes);
        System.out.println("gc.collectionEvents=" + summary.gcEvents);
        System.out.println("gc.pauseEvents=" + summary.gcPauseEvents);
        System.out.println("gc.heapSummaryEvents="
                + summary.gcHeapSummaries);
        System.out.println("cpu.distinctTopFrames="
                + summary.sampleTopFrames.size());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: capture|analyze <file.jfr>");
        }
        Path file = Paths.get(args[1]).toAbsolutePath();
        if ("capture".equals(args[0])) {
            capture(file);
        } else if ("analyze".equals(args[0])) {
            analyze(file);
        } else {
            throw new IllegalArgumentException("Unknown mode");
        }
    }
}
~~~

### Chạy chương trình

~~~bash
javac --release 11 JfrFourPillarsDemo.java
java JfrFourPillarsDemo capture incident.jfr
java JfrFourPillarsDemo analyze incident.jfr
~~~

JDK 11 trực tiếp có thể dùng `javac JfrFourPillarsDemo.java`. Tạo file ở thư mục có quyền ghi; sau bài học xóa bản ghi thử nghiệm theo chính sách của môi trường.

### Stdout đã được xác minh khi chạy trên JVM

Mode `capture`:

~~~text
capture.fileExists=true
~~~

Mode `analyze` — **một lượt chạy thực tế**, không phải output cố định của mọi JVM:

~~~text
checkpoints=4
cpu.loadEvents=4
cpu.sampleEvents=40
cpu.peakJvmFraction=0.066
lock.monitorEvents=2
lock.parkEvents=2
io.eventCount=3
io.bytesObserved=30
gc.collectionEvents=1
gc.pauseEvents=1
gc.heapSummaryEvents=2
cpu.distinctTopFrames=2
~~~

### Giải thích kết quả, tránh học sai

1. **`checkpoints=4`** là phần gần như deterministic do fixture commit bốn `lesson.DiagnosticCheckpoint`: CPU, LOCK, IO, GC.
2. `cpu.loadEvents` là số **CPU load events được ghi**, phụ thuộc periodic sampling và thời gian recording.
3. `cpu.sampleEvents` đếm execution/native samples, **không đếm method invocations**.
4. `cpu.peakJvmFraction` chỉ là **max của những CPU load samples có mặt**, không phải toàn bộ CPU utilization timeline hoặc chính xác phần trăm một core.
5. `lock.monitorEvents` đếm contention events được ghi, không phải tổng `synchronized` statements đã thực thi.
6. `lock.parkEvents` có thể gồm hoạt động của runtime/threads khác. **Không** suy ra số deadlocks.
7. `io.eventCount` và `io.bytesObserved` chỉ tổng hợp recorded File/Socket events; fixture không tạo socket server nhưng runtime có thể ghi I/O khác.
8. `gc.collectionEvents` và `gc.pauseEvents` có nghĩa **khác nhau**; explicit GC có thể bị disabled nên số events có thể khác.
9. `gc.heapSummaryEvents` không bằng số GC cycles; một GC có thể có summary trước/sau.
10. `cpu.distinctTopFrames` là số symbol top-frame khác nhau trong samples, không phải tổng methods ứng dụng.
11. CPU/lock/I/O/GC event counts **có thể thay đổi** theo JDK, OS, CPU cores, JIT, GC collector, threshold và scheduling. Không viết test assert cố định mọi dòng trên.
12. Bốn custom checkpoints **đánh dấu điểm bắt đầu fixture**, không tự tính duration của workload. Muốn đo duration nghiệp vụ, dùng custom duration events với `begin()/end()/commit()` hoặc tracing phù hợp.
13. `System.gc()` trong fixture chỉ để thử GC events; không đưa vào code production để cố gây GC tùy ý.

## 13. Mở rộng CPU report: top methods theo cửa sổ

Từ `summary.sampleTopFrames`:

~~~java
summary.sampleTopFrames.entrySet().stream()
        .sorted(Map.Entry.<String, Long>comparingByValue()
                .reversed())
        .limit(10)
        .forEach(item -> System.out.println(
                item.getKey() + "=" + item.getValue()));
~~~

**Đoạn minh họa**, không có stdout cố định. Khi group theo top frame:

- Hãy ưu tiên **full stack/call tree** khi cần hiểu vì sao method được gọi.
- Lọc time window lúc CPU spike, so với baseline chứ không trộn cả 3 giờ recording.
- Kiểm GC/JIT/native threads, CPU quota và shared host load.
- Số sample ít thì không kết luận tỷ lệ chính xác.
- CPU hotspot có thể làm đúng công việc cần thiết; một tối ưu chỉ được chấp nhận sau benchmark/measurement.

### Sự khác nhau giữa CPU và wall-clock

Một request mất 3 giây trong `SocketRead` nhưng CPU dùng 5 ms có thể **không xuất hiện** như hot method trong CPU samples. Khi CPU thấp nhưng latency cao, xem **I/O duration, parks, locks và tracing**.

## 14. Mở rộng lock report: owner, stack, phân vị

Các thông tin có thể group từ `JavaMonitorEnter`:

- `duration`: mức chờ;
- `monitorClass`: kiểu monitor;
- `previousOwner` hoặc `eventThread` nếu có;
- `stackTrace` khi ghi;
- thời điểm và request/trace context nếu được liên kết.

Đừng chỉ group theo `monitorClass` rồi nghĩ một class tương ứng một lock instance. Một type có thể có hàng triệu object monitors.

### Khi nào lock count thấp nhưng nguy hiểm?

- Một contention 5 giây có thể làm p99 xấu dù số event rất ít.
- Hàng triệu contention vài microseconds có thể gây overhead nhưng bị ngưỡng 20 ms bỏ sót.
- Một thread đang `park` dài có thể chỉ là worker chờ queue hợp lệ.
- Chỉ dấu “thread WAITING” không đủ chứng minh deadlock; cần kiểm vòng chờ.

**Báo cáo tốt:** count, max duration, p95/p99 của recorded waits, top stack, thread role, threshold, time window và lock owner nếu có.

## 15. Mở rộng I/O report: latency hay throughput?

Ví dụ:

~~~text
SocketRead A: 200 bytes, duration 1.5s
SocketRead B: 16 MiB, duration 20ms
~~~

Nếu đang điều tra **latency**, A có thể đáng chú ý. Nếu đang điều tra **bandwidth**, B có thể quan trọng hơn. Không chỉ xếp theo số byte hoặc duration đơn lẻ.

- Event duration có thể bao gồm wait/scheduling ở tầng Java I/O.
- `SocketRead` chậm không tự xác định peer/server/network là thủ phạm.
- Dữ liệu I/O ngắn hơn threshold có thể bị bỏ sót, nên tổng bytes recorded không bằng tổng bytes thật.
- Tránh log full `path`/`host` vào báo cáo ngoài nhóm phân tích.
- Group theo resource/operation và time window, đối chiếu metrics disk/network/downstream tracing.

### Cần thêm thông tin gì?

CPU thấp + SocketRead lâu → xem downstream response time, connection pool và timeouts. FileRead lâu → xem disk IOPS, filesystem latency, page cache và concurrent load. Một event JFR là **dấu vết**, không phải chứng nhận nguyên nhân.

## 16. Mở rộng GC report: pauses và heap retention

### Pauses

`jdk.GCPhasePause` phản ánh pause, có thể tương quan trực tiếp hơn với latency spike. **Không cộng lẫn** các sự kiện phân cấp `GCPhasePauseLevel1/2/...` vì có thể mô tả cùng một pause ở các cấp.

### GC collection

Một `jdk.GarbageCollection` có thể bao gồm hoạt động concurrent, do đó duration của toàn collection không phải STW duration. Đừng dùng `GarbageCollection.duration` làm tên metric `stoppedMilliseconds`.

### Heap summaries

Nếu file có `jdk.GCHeapSummary`:

~~~java
if (event.hasField("heapUsed")) {
    long heapUsed = event.getLong("heapUsed");
    // Gắn với gcId/when nếu fields đó có mặt.
}
~~~

**Đoạn minh họa**. So **heap sau GC** theo nhiều mốc có workload tương đương; một snapshot cao đơn lẻ chưa chứng minh memory leak.

### Khi nào dùng heap dump?

JFR allocation/GC events cho biết **xu hướng**, còn heap dump và GC roots cho biết **ai đang giữ references**. Nếu heap sau GC tăng bền vững, nghi leak, hãy cân nhắc heap dump có kiểm soát, biết rằng nó có thể gây pause và chứa secrets.

## 17. Lọc theo time window và không nhầm đơn vị

Ví dụ muốn xem chỉ các events giao với phút xảy ra spike:

~~~java
Instant from = Instant.parse("2026-11-07T09:00:00Z");
Instant to = Instant.parse("2026-11-07T09:01:00Z");

boolean intersects =
        !event.getEndTime().isBefore(from)
        && !event.getStartTime().isAfter(to);
~~~

**Đoạn minh họa** trong method, cần import `Instant`. Một event kéo dài vượt biên chỉ được **chọn vào window**, còn duration của phần nằm trong window cần **clip** nếu tính time totals.

### Không cộng duration song song thành elapsed

Hai threads cùng chờ I/O 2 giây từ `t=0` tới `t=2s` có tổng **cumulative wait 4 giây**, nhưng wall-clock chỉ trôi qua 2 giây. Tương tự, nhiều GC phase events có thể mô tả nested sections. Khi báo cáo, ghi rõ **cumulative operation time**, **per-event latency** hay **elapsed wall-clock**.

### Kết hợp request tracing

JFR không tự biết mọi HTTP request ID. Nếu cần correlation, ghi một custom event với **trace ID đã kiểm soát** hoặc kết hợp với hệ thống tracing; tuyệt đối không ghi raw Authorization headers, passwords hay PII vào JFR chỉ để tiện nối dữ liệu.

## 18. Xác minh bằng jfr CLI

Các lệnh dưới đây là công cụ JDK để đọc file, không cần ứng dụng Java tự viết parser:

~~~bash
jfr summary incident.jfr
jfr print --events jdk.CPULoad incident.jfr
jfr print --events jdk.ExecutionSample incident.jfr
jfr print --events jdk.JavaMonitorEnter incident.jfr
jfr print --events jdk.SocketRead incident.jfr
jfr print --events jdk.GCPhasePause incident.jfr
jfr metadata incident.jfr
~~~

- `jfr summary`: xem khoảng ghi, event types và số events.
- `jfr print --events`: xem dữ liệu một type theo thời gian.
- `jfr metadata`: tìm field names/types khi parser báo thiếu field.

**Lưu ý:** Các phiên bản JDK có thể có thêm các lệnh mới như `jfr view`, nhưng bài Java 11 này chỉ dựa vào những khả năng có thể kiểm qua `jfr help` của runtime thực tế. Không dump toàn bộ output chứa đường dẫn/hostname/stack của production ra nơi công khai.

### JDK Mission Control

JDK Mission Control (JMC) là GUI phân tích JFR, được phân phối riêng, không mặc định có trong mọi JDK installation. Dùng để xem **timeline CPU/threads/locks/I/O/GC**, hot methods/call tree và lọc theo time range. Nếu kết quả Java parser khác JMC, xác minh cả hai đang xem **cùng file, cùng interval và cùng event filter**.

## 19. Lấy .jfr từ JVM đang chạy bằng jcmd

Với HotSpot JVM cho phép attach và người vận hành đã được cấp quyền:

~~~bash
jcmd -l
jcmd <PID> help JFR.start
jcmd <PID> JFR.start name=Incident299 settings=profile duration=60s filename=/secure/incident299.jfr
~~~

Đây là **lệnh tham khảo**, không phải thao tác đã chạy trên production. Chọn đúng PID/namespace, duration, quota và quyền file.

Nếu recording đang chạy:

~~~bash
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=ExistingRecording filename=/secure/snapshot.jfr
~~~

Một snapshot không nhất thiết dừng recording gốc. Không bật nhiều `profile` recordings trùng khi không cần thiết; có thể tăng overhead/disk. Trong Kubernetes, PID và filesystem path của target JVM có thể khác shell trên host.

## 20. Quy trình điều tra theo bốn nhóm

### A. CPU cao

1. Đọc `CPULoad` trong time window CPU spike, so OS/container CPU.
2. Đọc `ExecutionSample`/`ThreadCPULoad`, nhóm theo thread và full call paths.
3. Kiểm GC/JIT/native threads vì chúng cũng dùng CPU.
4. Đối chiếu throughput và request volume.
5. Tối ưu hot path có giả thuyết rõ, đo lại CPU, throughput và p95/p99.

**Sai:** nói một method chiếm 60% request latency chỉ vì chiếm 60% CPU samples.

### B. p99 cao nhưng CPU thấp

1. Tìm `SocketRead`, `FileRead`, `ThreadPark` và `JavaMonitorEnter` trùng window.
2. Xem duration/max, stack, request role và threshold.
3. Xem pool, queue, downstream tracing và lock ownership.
4. Không coi một `ThreadPark` hợp lệ của idle worker là deadlock.
5. Sửa timeout/backpressure/lock granularity hoặc downstream và đo lại.

### C. GC pauses tăng

1. So `GCPhasePause` với latency timestamps.
2. Kiểm `GarbageCollection` count/name/cause theo schema.
3. Xem `GCHeapSummary` after-GC heap và allocation pressure.
4. Tránh cộng hai lần nested pause phases.
5. So sau fix với cùng workload; nếu suspect retained leak dùng heap dump.

### D. I/O byte nhiều nhưng latency có vẻ bình thường

1. Xác định bottleneck mục tiêu là bandwidth hay latency.
2. Group `FileWrite`/`SocketWrite` bytes/operation; kiểm threshold.
3. So network/disk metrics và tracing.
4. Không kết luận “tối ưu I/O” chỉ vì event count nhiều; có thể ứng dụng đang làm việc cần thiết.
5. Chỉ thay đổi sau khi đã chọn metric ảnh hưởng người dùng.

## 21. Anti-pattern và lỗi đọc JFR

| Sai | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Đọc `.jfr` bằng `Files.readString` | Đây là binary format | `RecordingFile`/`jfr`/JMC |
| `readAllEvents` với file lớn | Giữ quá nhiều objects | Streaming aggregates |
| Lấy field không kiểm `hasField` | Schema thiếu/khác | Typed access an toàn, metadata |
| Giả định stack luôn có | StackTrace có thể null | Null check |
| `ExecutionSample count` là số lời gọi method | Sampling không phải instrumentation count | Gọi đúng là sample count |
| CPU samples đo network wait | Threads ngủ/chờ ít được sample | I/O/park/tracing |
| Mọi `ThreadPark` là deadlock | Park có thể hợp lệ | Đọc thread role và ownership |
| Mọi monitor acquisition có `JavaMonitorEnter` | Threshold chỉ ghi những contention phù hợp | Nêu threshold |
| `SocketRead` lâu chứng minh mạng lỗi | Có thể peer/app/proxy/long-poll | Downstream metrics/traces |
| Tổng bytes event bằng tổng traffic | Events nhanh bị lọc | “Bytes observed” |
| `GarbageCollection.duration` bằng STW | Concurrent GC phases | `GCPhasePause` |
| Cộng nested GC pause events | Đếm lặp | Chọn đúng cấp event |
| HeapUsed cao một lần là leak | Thiếu trend và references | After-GC trend + heap dump |
| 0 events = 0 hoạt động | Missing/disabled/threshold | Báo unavailable/ghi rõ settings |
| Không lọc time window | Baseline che incident | Interval và correlation |
| Cộng durations song song | Sai elapsed latency | Phân biệt cumulative vs wall |
| Bật threshold=0 vô hạn | Overhead/volume lớn | Đo có thời hạn |
| Ghi raw path/host/token | Rò dữ liệu | Aggregate/redaction |
| Output demo là giá trị cố định | Event counts biến động | Chỉ assert fixture checkpoints |
| Gọi `System.gc()` để chữa leak | Không giải quyết retained references | Chỉ dùng trong test |

## 22. Bảo mật và lưu trữ

JFR có thể chứa tên class, method, thread, stack, path, host, JVM settings, và custom fields. Cần:

- Chỉ thu thập đúng process/incident đã được phê duyệt.
- Dùng thư mục có ACL, encryption và retention; không đặt file dưới web root.
- Không gửi raw `.jfr` vào issue tracker/chat công khai.
- Không đưa token, credentials, PII vào custom events.
- Giới hạn `duration`/`maxsize`/`maxage` và disk quota.
- Ghi JDK build, GC algorithm, PID, time zone, settings cùng report.
- Nếu share dữ liệu, xuất summary đã loại path/host/identifiers nhạy cảm.
- Xóa recording theo chính sách sau khi phân tích.

## 23. Ma trận kiểm thử

| Test | Kỳ vọng |
| --- | --- |
| JFR hợp lệ | `RecordingFile` đọc được, không exception |
| File sai định dạng | Báo lỗi rõ, không coi như 0 events hợp lệ |
| Bốn checkpoints | Fixture ghi/đếm đúng `4` |
| CPU load event được bật | Truy cập fields khi `hasField` |
| CPU sample không có stack | Parser không NPE |
| CPU sample có top frame | Group theo method symbol |
| Contention test | Monitor events nếu threshold cho phép |
| Park bình thường | Không gắn nhãn deadlock |
| File write/read | Đếm I/O recorded events |
| Socket I/O từ server test | Phân biệt read/write và bytes |
| GC enabled | Phân biệt collection/pause |
| GC bị disable | Test không assert count bắt buộc |
| GCHeapSummary schema khác | Gracefully handle missing fields |
| Events ngoài window | Filter đúng time overlap |
| Two threads wait song song | Không coi sum là elapsed |
| JFR quá lớn | Streaming memory usage bounded |
| Nâng JDK | Parser vẫn handle optional fields |
| Recording thiếu event type | Không ngầm coi metric 0 |
| Sensitive metadata | Report không lộ raw path/host |

## 24. Checklist khi review

- [ ] Đọc `RecordingFile` streaming và đóng file đúng cách.
- [ ] Phân loại bằng event type name; không dựa vào thứ tự file.
- [ ] Kiểm `hasField`, null stack và data type.
- [ ] CPU load và CPU sample count được báo thành hai metric khác nhau.
- [ ] Tính top method từ sample, không suy ra method invocations.
- [ ] Lock events phân biệt monitor enter, wait, park và sleep.
- [ ] Không kết luận deadlock chỉ từ một event park/monitor.
- [ ] I/O count/bytes ghi rõ là **recorded events**, không phải toàn operations.
- [ ] GC collection duration không nhầm với STW pause.
- [ ] Không cộng GC nested pause levels nhiều lần.
- [ ] Có time window, baseline, JDK/version, settings, threshold.
- [ ] Duration sum không nhầm elapsed latency.
- [ ] Có tracing/metrics để xác thực causal hypotheses.
- [ ] Có security/redaction và retention cho file.
- [ ] Mã demo compile với Java 11 và không dùng API chỉ có từ JDK mới.
- [ ] QA không hardcode số built-in events vốn phụ thuộc workload.
- [ ] Có kiểm tra sau khi nâng JDK/collector.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** File có 300 `jdk.ExecutionSample`, tức method đã được gọi 300 lần?

**Không.** Đó là **300 stack samples**. Cần instrumentation riêng nếu muốn đếm calls.

**Câu 2.** `jdk.CPULoad` và `jdk.ExecutionSample` khác nhau thế nào?

**CPULoad** là tỷ lệ sử dụng CPU theo mốc thời gian; **ExecutionSample** là stack được lấy mẫu khi thread thực thi.

**Câu 3.** Vì sao file không có `FileRead` chưa chứng minh app không đọc file?

Vì **event có thể bị tắt, threshold cao, hoạt động quá nhanh hoặc cửa sổ ghi không bao phủ**.

**Câu 4.** `JavaMonitorEnter` và `ThreadPark` có giống nhau?

**Không.** Một loại liên quan chờ monitor acquisition, loại kia liên quan thread park; cả hai cần phân tích stack/role.

**Câu 5.** `SocketRead` lâu có chứng minh mạng Internet chậm không?

**Không.** Có thể do peer, proxy, application scheduling hoặc long-poll. Cần downstream telemetry.

**Câu 6.** Hai socket reads song song mỗi lần 2 giây nghĩa tổng wall-clock 4 giây?

**Không.** Cumulative operation wait là 4 giây, elapsed có thể chỉ 2 giây.

**Câu 7.** `jdk.GarbageCollection.duration` là thời gian ứng dụng dừng hoàn toàn?

**Không nhất thiết.** Với concurrent collector, cần xem `jdk.GCPhasePause`.

**Câu 8.** Heap sau một GC cao có đủ chứng minh leak?

**Không.** Xem trend after-GC với cùng workload và object retention bằng heap dump khi cần.

**Câu 9.** `getStackTrace() == null` nghĩa file sai?

**Không.** Event có thể không ghi stack hoặc stack tracing bị tắt.

**Câu 10.** Tại sao `hasField` quan trọng khi đọc file từ JDK khác?

**Schema có thể khác/đổi**. Parser phải tránh giả định tất cả events có cùng fields.

**Câu 11.** Metric không có event nên đưa về 0% CPU?

**Không.** “Không có dữ liệu” và “CPU được đo bằng 0%” là hai tình huống khác.

**Câu 12.** Một JavaMonitorEnter 200 ms trùng spike có đủ chứng minh nó gây toàn bộ p99?

**Chưa.** Cần chứng minh cùng request/thread và so các nguồn khác.

## 26. Tài liệu chính thức hiện hành

1. [Java SE 11 — `RecordingFile`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): `hasMoreEvents/readEvent` và streaming JFR.
2. [Java SE 11 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): timestamp, duration, stack trace, thread, event type.
3. [Java SE 11 — `RecordedObject`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): `hasField`, typed getters, schema caveat.
4. [Java SE 11 — `RecordedStackTrace`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedStackTrace.html), [`RecordedFrame`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedFrame.html): đọc stack samples.
5. [Java SE 11 — `Recording`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html), [`EventSettings`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): cấu hình event/threshold/period.
6. [Java SE 11 — JFR Package Summary](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event settings và API.
7. [Oracle JDK 26 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html): CPU, synchronization, I/O, GC, threshold và sampling caveats.
8. [Oracle JDK 26 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html): Flight Recorder và JMC.
9. [Oracle JDK 25 — jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `jfr print`, `summary`, `metadata`; kiểm `jfr help` cho runtime Java 11.
10. [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR tích hợp OpenJDK.
11. [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): `RecordingStream` được bổ sung sau Java 11 (JDK 14); **không nhầm với API đọc file `RecordingFile` vốn có trên Java 11**.
12. [JDK Mission Control](https://openjdk.org/projects/jmc/): GUI phân tích JFR, cần cài riêng nếu môi trường không có.

**Ghi nhớ:** Đọc bản ghi JFR đúng nghĩa là **phân tích các event theo thời gian**. `CPULoad`/`ExecutionSample` giúp tìm tải CPU và hot code; `JavaMonitorEnter`/`ThreadPark` gợi ý contention/waiting; `FileRead`/`SocketRead` cho dấu vết I/O; `GarbageCollection`/`GCPhasePause`/`GCHeapSummary` cho GC và heap. Dùng `RecordingFile`, kiểm schema, công bố rõ time window và threshold, không biến samples thành calls hay cumulative durations thành wall-clock elapsed. Kết luận chỉ chắc hơn khi đã đối chiếu với metrics/tracing và đo lại sau fix.