# Đối chiếu dữ liệu mẫu với heap, GC và tải ứng dụng — Heap profiling bằng Java 11+

## 1. Vấn đề cần giải quyết

Khi một Java service có dấu hiệu tăng bộ nhớ hoặc độ trễ, **allocation samples**, **heap usage**, **garbage collection (GC)** và **tải ứng dụng** trả lời các câu hỏi khác nhau. Chỉ nhìn một biểu đồ heap tăng hoặc thấy nhiều allocation events **chưa đủ để kết luận memory leak**.

Bài này xây dựng cách đối chiếu bốn nguồn theo **cùng trục thời gian**:

- **Allocation profiling:** thread, class, method hoặc stack trace nào đang cấp phát nhiều object? Các sample chỉ phản ánh các điểm quan sát theo chính sách JFR, không phải bảng kê mọi object.
- **Heap:** lượng bộ nhớ đã dùng thay đổi thế nào; có giảm sau GC không; đáy heap sau những lần GC tương đương có tăng trong lúc tải ổn định không?
- **GC:** tần suất thu gom, heap trước/sau GC, thời lượng pause, impact đến CPU/latency ra sao?
- **Application load:** requests/s, operations/s, concurrency, payload size, response latency p95/p99, retry/error rate và request mix có biến động không?

**Mục tiêu:** phân biệt *tăng allocation do tải* với *allocation regression*, *GC pressure* và *object retention/leak*. Ta dùng **JDK Flight Recorder (JFR)**, public API `jdk.jfr` và `java.lang.management`, cùng JDK Mission Control (JMC), đều còn áp dụng trong JDK hiện hành. Nội dung lập trình tương thích **Java 11+**, không dựa vào API hoặc công cụ legacy.

## 2. Ba phép đo quan trọng không được đánh đồng

### 2.1. Allocation samples đo áp lực tạo object, không phải object còn sống

Một chương trình có thể cấp phát hàng triệu object tạm trong mỗi phút. Sau GC, hầu hết có thể đã chết. Phân tích allocation cho biết **vị trí tạo object và mức độ cấp phát**, nhưng không tự cho biết **object nào vẫn reachable**, vì vậy nó không phải phép đo live heap trực tiếp.

Một sample có thể được gắn với class, thread, stack trace và thông số byte tùy loại event. Không thể khẳng định:

```text
1 allocation sample == 1 object được tạo.
1000 samples == 1000 objects còn sống.
sum of any allocationSize fields == exact heap allocated bytes.
```

Những khẳng định trên thường sai vì **sampling strategy**, TLAB refill, sample weight và các event khác nhau. Khi cần allocation rate định lượng, phải dùng đúng **mô hình ước lượng** hoặc nguồn đo thực, không chỉ đếm events.

### 2.2. Heap used và live set khác nhau

`MemoryMXBean.getHeapMemoryUsage()` trả một `MemoryUsage` chứa:

| Trường | Ý nghĩa |
| --- | --- |
| `used` | Bytes heap JVM đang dùng ở thời điểm snapshot |
| `committed` | Bytes heap JVM đã cam kết, có thể vượt `used` |
| `max` | Giới hạn heap nếu runtime biết được |
| `init` | Heap size ban đầu được JVM cấu hình/yêu cầu |

**`used` không phải số bytes của những object sẽ sống mãi.** Nó chứa cả object có thể được thu hồi tại GC tiếp theo. Heap thường tăng dần khi cấp phát rồi giảm đột ngột khi GC hoàn tất, tạo đường **răng cưa**.

Muốn xem retention, thường phải quan sát các điểm **heap-after-GC** tương đương qua nhiều chu kỳ, kết hợp live-object analysis và đường tham chiếu giữ object. Hai snapshot `used` không cùng vị trí trong chu kỳ GC có thể gây kết luận sai.

**`committed` không phải live heap**, còn RSS của process cũng không phải chỉ Java heap: metaspace, code cache, native/direct buffers, thread stacks và JNI dùng memory ngoài heap.

### 2.3. GC activity có tác động nhưng không tự là lỗi

GC events giúp phân biệt allocation nhanh tạo nhiều garbage tạm với retained heap tăng. Quan sát:

- GC count/rate trong mỗi cửa sổ.
- Heap before/after GC từ sự kiện phù hợp.
- Pause time, max pause, tỉ lệ thời gian ứng dụng tạm dừng, p95/p99 latency.
- Collector/phase: young, mixed, full, concurrent... có hợp đồng duration khác nhau.

**Không cộng mọi GC event duration rồi gọi kết quả là stop-the-world pause.** Concurrent phases có thể mất nhiều wall time mà ứng dụng không bị dừng toàn bộ khoảng đó. Muốn tính pause fraction phải dùng đúng các pause metrics/event fields theo collector.

GC nhiều hơn khi requests/s tăng có thể là điều bình thường. Cần chuẩn hóa theo tải và xem tác động tới latency hoặc throughput.

## 3. Những event hữu ích cho bài Heap profiling

JFR event types phải được kiểm tra ở **runtime và JFR configuration cụ thể**. Java 11 và những JDK hiện hành hỗ trợ các nhóm dữ liệu sau, nhưng cài đặt bật/tắt mặc định có thể khác theo vendor/version:

| Tên event / API | Nội dung | Hạn chế |
| --- | --- | --- |
| `jdk.ObjectAllocationInNewTLAB` | Điểm cấp phát liên quan TLAB mới, class/stack/size theo schema | Không ghi mọi object cấp phát trong TLAB |
| `jdk.ObjectAllocationOutsideTLAB` | Điểm cấp phát ngoài TLAB | Không cộng counts để suy ra tổng objects |
| `jdk.GarbageCollection` | Sự kiện GC, tên/nhân tố/duration tùy GC | Không dùng tổng duration thay pause |
| `jdk.GCHeapSummary` | Heap snapshots liên quan trước/sau GC | So đúng GC ID/phase trước–sau |
| `jdk.CPULoad` | CPU load được lấy mẫu | Recording quá ngắn có thể cho count 0 |
| `jdk.ThreadAllocationStatistics` | Số liệu cấp phát theo thread theo periodic/chunk settings | Không đại diện mỗi allocation |
| `jdk.ObjectAllocationSample` nếu được runtime hỗ trợ | Event sampling cấp phát, có thể có `objectClass` và `weight` | Không giả định có trong **mọi Java 11** |
| `MemoryMXBean` | Heap `used/committed/max` | Snapshot không nhất thiết là sau GC |
| `GarbageCollectorMXBean` | GC collection count/time tùy runtime | Không thay thế JFR pause attribution |
| Application metrics/custom JFR event | RPS, operations, phase, payload, p95 | Có mẫu số/dải thời gian và cardinality rõ |

### 3.1. TLAB sampling khác `ObjectAllocationSample`

Với hai event `jdk.ObjectAllocationInNewTLAB` và `jdk.ObjectAllocationOutsideTLAB`, một event được ghi tại **điểm quan sát cấp phát** theo cơ chế JVM. Một TLAB có thể chứa nhiều allocations, do đó một event không tương ứng mọi object.

Trên JDK có `jdk.ObjectAllocationSample`, trường `weight` là **trọng số tương đối của sample**; việc tổng hợp các weight theo class/thread/stack có thể dùng để ước lượng áp lực cấp phát theo mô hình của event đó. Đừng trộn `weight` với `allocationSize` hoặc `tlabSize` từ loại event khác như thể cùng ngữ nghĩa.

**Tính tương thích:** không khẳng định `jdk.ObjectAllocationSample` chắc chắn tồn tại với một schema cụ thể trên tất cả JDK 11, vendor và bản update. Kiểm tra event types thực tế bằng `FlightRecorder.getFlightRecorder().getEventTypes()` hoặc metadata/summary file rồi mới sử dụng. Demo Java 11 ở phần sau dùng **hai event TLAB**, được kiểm thử đầy đủ.

### 3.2. Không có event không có nghĩa hiện tượng không xảy ra

Một recording rất ngắn có thể không có `jdk.CPULoad` vì sampling period. Một phase ít allocations có thể không có allocation sample. Điều đó **không chứng minh CPU idle hoặc không có allocation**.

Trước khi kết luận cần hỏi:

1. Event type đã có trên runtime chưa?
2. Recording thực sự đang chạy trong cửa sổ quan sát không?
3. Event được bật với `enabled=true` và threshold/period phù hợp không?
4. Có filter sai loại event, thread, category hoặc timestamp không?
5. Workload có đủ dài và tạo đủ hoạt động để mẫu có ý nghĩa không?

## 4. Đối chiếu theo cùng trục thời gian

Một cách nhìn phù hợp là chia thời gian thành các **cửa sổ có nhãn**, chẳng hạn baseline, warm-up, load ramp, steady high load, recovery:

```text
Timeline:      T0         T1          T2          T3
               |----------|-----------|-----------|
Application    baseline   ramp-up     high load   recovery
RPS            thấp       tăng        cao         giảm
Alloc samples  . .        .::::       ::::::::    . .
Heap used      /\/\       /\/\/\      /\/\/\/\/\  /\/
GC events      |          ||          ||||        |
p95 latency    30 ms      35 ms       60 ms       30 ms
```

Đây là **dữ liệu minh họa**, không phải kết quả benchmark thực. Trên một timeline, ta có thể kiểm tra GC/heap changes có xảy ra trong chính cửa sổ tải cao hay không.

### 4.1. Các phép tính nên dùng

Giả sử một cửa sổ dài `T` giây:

```text
Throughput                 = completedOperations / T
Estimated allocation rate  = estimatedAllocatedBytes / T
Estimated bytes/operation  = estimatedAllocatedBytes / completedOperations
GCs/minute                 = GCCount * 60 / T
GC pause fraction          = sumOfMeasuredStopTheWorldPauses / T
```

Đơn vị của mẫu số phải nhất quán. Số byte có nguồn sampling phải ghi là **estimated** và được tính theo weight/model phù hợp, không thay bằng `sampleCount * kích_thước_giả_định`. Khi tính bytes per request phải phân biệt request accepted/completed/retried và các loại payload.

### 4.2. So cửa sổ tương đương mới đáng tin

Một hệ thống đang xử lý 50 requests/s không thể so nguyên tổng allocation bytes/s với hệ thống đang xử lý 500 requests/s rồi tuyên bố regression. Cần giữ tương đương về:

- JDK version/vendor, heap size, GC algorithm.
- JFR event enablement, period, threshold, stack trace và cách ước lượng bytes.
- Duration của cửa sổ, warm-up/JIT state.
- Request mix, payload size, concurrency, traffic, retry.
- SLO: p95/p99 latency, error/timeout rate.

Nếu khác biệt là chủ ý, phải **ghi rõ** và chuẩn hóa theo operation phù hợp.

### 4.3. Dùng timestamps chính xác nhưng tránh giả quan hệ nhân quả

JFR events có `Instant`; app metrics nên có timezone/clock offset rõ. Khi phân tích nhiều process, cần xử lý clock synchronization và timezone.

Cùng một thời điểm GC tăng, p95 tăng và allocation tăng **là tương quan**, chưa tự chứng minh cái nào gây cái nào. Nên đặt giả thuyết, xem stack traces, thêm metrics và thực hiện thay đổi có kiểm soát.

## 5. Phân biệt áp lực cấp phát và giữ lại đối tượng

| Hiện tượng | Allocation rate | Heap sau GC | GC / tải | Cách hiểu sơ bộ |
| --- | --- | --- | --- | --- |
| Traffic tăng bình thường | Tăng theo RPS | Phẳng | GC tăng cùng operations | Nhiều object tạm, chưa phải leak |
| Regression sau deploy | Bytes/op tăng dù RPS ổn | Có thể phẳng | GC/CPU tăng | Code tạo object không cần thiết |
| Retention/cache không giới hạn | Có thể tăng hoặc không | Đáy heap tăng dần | Old/mixed collections nặng hơn | Cần tìm retaining path |
| Warm-up cache hợp lệ | Cao lúc đầu | Tăng rồi ổn định | GC thay đổi theo khởi động | Không gọi leak nếu cache có giới hạn |
| CPU hoặc I/O bottleneck | Có thể không đổi | Phẳng | p95 tăng | Cần xem CPU, locks, network, downstream |
| RSS tăng mà heap phẳng | Có thể không đổi | Phẳng | GC tương đối ổn | Kiểm tra native/off-heap memory |

**Không tự chẩn đoán memory leak** chỉ từ số sample, heap peak hay GC count. Dấu hiệu retention mạnh hơn là **heap-after-GC liên tục tăng** trong các điều kiện so sánh hợp lý, sau đó được xác nhận bằng live objects và references.

### 5.1. Vì sao một heap snapshot chưa đủ?

Giả sử `heapUsedAfter` cuối phase tăng. Điều đó có thể do chưa xảy ra GC, do cache warm-up hợp lệ, hoặc do object vẫn được giữ lại. Phải nhìn chuỗi các GC phù hợp và trạng thái load.

Với collectors concurrent, ranh giới trước/sau GC cũng phức tạp. Không tự ép `System.gc()` trong production chỉ để nhận một mốc “sau GC”, vì full/old GC hoặc heap statistics có thể gây pause và phá dữ liệu độ trễ đang muốn đo.

## 6. Chuẩn bị JFR recording để thu dữ liệu

Một lệnh `jcmd` minh họa cho JVM đang chạy:

```bash
jcmd -l
jcmd 12345 JFR.start name=heapcheck settings=profile duration=120s filename=heapcheck.jfr
jcmd 12345 JFR.check
```

Thay PID `12345` bằng PID thật; đường dẫn `filename` tương đối được diễn giải theo môi trường process đích. Trong container cần xác nhận PID namespace, disk mounts, quyền file.

Khi recording xong:

```bash
jfr summary heapcheck.jfr
jfr metadata heapcheck.jfr
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary heapcheck.jfr
```

`profile.jfc` thường bật nhiều dữ liệu hơn `default.jfc` và overhead có thể lớn hơn. Bật **có thời hạn**, theo dõi file size, chi phí sampling và tính nhạy cảm của thông tin. Đừng tự bật heap statistics/old-object analysis nặng trên hệ thống latency-sensitive khi chưa hiểu overhead.

### 6.1. Bật event cụ thể qua Java API

```java
// Snippet minh họa, phải import Recording và Configuration.
// Mục 8 có chương trình đầy đủ start/stop/dump.
Recording r = new Recording(Configuration.getConfiguration("profile"));
r.enable("jdk.ObjectAllocationInNewTLAB").withStackTrace();
r.enable("jdk.ObjectAllocationOutsideTLAB").withStackTrace();
r.enable("jdk.GCHeapSummary");
r.enable("jdk.GarbageCollection");
r.enable("jdk.CPULoad");
```

Không phải mọi JFR event type đều có schema/cấu hình mặc định bất biến. Một bản JDK mới có thể ưu tiên `jdk.ObjectAllocationSample` với trọng số khác. Luôn kiểm tra metadata runtime, không gộp mọi type có prefix `jdk.ObjectAllocation` vào một count định lượng.

## 7. Custom JFR marker gắn tải ứng dụng vào sampling timeline

Để phân đoạn dữ liệu JFR có ý nghĩa, ta phát một custom event kéo dài suốt workload:

```java
@Name("lesson.LoadPhase")
@Label("Load phase")
@Category({"Learning", "Heap"})
public static class LoadPhase extends Event {
    public String phase;
    public long operations;
    public long requestedPayloadBytes;
    public long heapUsedBefore;
    public long heapUsedAfter;
    public long gcCountBefore;
    public long gcCountAfter;
    public int retainedArrays;
}
```

Đây là **snippet nested class**, chương trình đầy đủ có imports.

Các fields được hiểu chính xác:

| Field | Ý nghĩa | Không phải |
| --- | --- | --- |
| `phase` | Baseline/transient/retained, phân loại cửa sổ | Timestamp tuyệt đối |
| `operations` | Số hoạt động do code đếm | Số object JVM tạo |
| `requestedPayloadBytes` | Tổng kích thước payload của mảng mà code chủ ý yêu cầu | Số bytes JVM thực tế cấp phát chính xác |
| `heapUsedBefore/After` | Snapshot `MemoryMXBean` tại đầu/cuối phase | Heap after full GC |
| `gcCountBefore/After` | Tổng GC count từ management beans được hỗ trợ | Tổng pause time |
| `retainedArrays` | Mảng cố tình còn strong reference trong demo | Toàn bộ live objects trong JVM |

Dùng `begin()/end()` cho phase marker. Khi đọc lại `RecordedEvent.getStartTime()/getEndTime()`, có thể gán những allocation events có timestamp thuộc khoảng đó vào phase. Không để giá trị status/text có cardinality rất lớn hoặc bí mật người dùng trong custom events.

## 8. Chương trình Java 11 hoàn chỉnh: transient vs retained và tương quan với GC

Demo sau hoàn toàn chạy được trên JDK 11+ có JFR, không cần network hay dependency ngoài JDK.

- Phase **transient**: tạo **24.000 mảng 4.096 byte**, không giữ lâu phần lớn dữ liệu.
- Phase **retained**: tạo **512 mảng 8.192 byte**, giữ **256** trong một `List` static.
- Ghi snapshot heap/GC và số operations ở từng phase.
- Đọc JFR và assert 2 phase markers đúng tên, đúng field, đúng thứ tự.
- Đếm hai loại TLAB-related events **riêng biệt với `ObjectAllocationSample`** trong từng phase.
- Đếm GC và GCHeapSummary events; **không yêu cầu số sample/GC chính xác** giữa các runtime.

### 8.1. Tạo file `HeapLoadCorrelationDemo.java`

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class HeapLoadCorrelationDemo {
    @Name("lesson.LoadPhase")
    @Label("Load phase")
    @Category({"Learning", "Heap"})
    public static class LoadPhase extends Event {
        public String phase;
        public long operations;
        public long requestedPayloadBytes;
        public long heapUsedBefore;
        public long heapUsedAfter;
        public long gcCountBefore;
        public long gcCountAfter;
        public int retainedArrays;
    }

    static final List<byte[]> RETAINED = new ArrayList<>();
    static volatile byte[] lastTransient;

    static long usedHeap() {
        return ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
    }

    static long collections() {
        long total = 0;
        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (gc.getCollectionCount() >= 0) {
                total += gc.getCollectionCount();
            }
        }
        return total;
    }

    static void runPhase(String name, int count, int payloadSize, boolean retain)
            throws Exception {
        LoadPhase phase = new LoadPhase();
        phase.phase = name;
        phase.operations = count;
        phase.requestedPayloadBytes = (long) count * payloadSize;
        phase.heapUsedBefore = usedHeap();
        phase.gcCountBefore = collections();

        phase.begin();
        for (int i = 0; i < count; i++) {
            byte[] data = new byte[payloadSize];
            data[0] = (byte) i;
            if (retain && (i % 2 == 0)) {
                RETAINED.add(data);
            } else {
                lastTransient = data;
            }
        }
        Thread.sleep(150);
        phase.end();

        phase.heapUsedAfter = usedHeap();
        phase.gcCountAfter = collections();
        phase.retainedArrays = RETAINED.size();
        phase.commit();
    }

    static boolean inWindow(Instant when, RecordedEvent phase) {
        return !when.isBefore(phase.getStartTime()) &&
                !when.isAfter(phase.getEndTime());
    }

    static boolean isTlabSample(RecordedEvent event) {
        String name = event.getEventType().getName();
        return name.equals("jdk.ObjectAllocationInNewTLAB") ||
               name.equals("jdk.ObjectAllocationOutsideTLAB");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("output directory");
        }
        Path output = Path.of(args[0], "heap-load.jfr");

        try (Recording r =
                new Recording(Configuration.getConfiguration("profile"))) {
            r.enable(LoadPhase.class).withoutStackTrace();
            r.enable("jdk.ObjectAllocationInNewTLAB").withStackTrace();
            r.enable("jdk.ObjectAllocationOutsideTLAB").withStackTrace();
            r.enable("jdk.GCHeapSummary");
            r.enable("jdk.GarbageCollection");
            r.enable("jdk.CPULoad");
            r.setMaxSize(32L * 1024 * 1024);

            r.start();
            runPhase("transient", 24000, 4096, false);
            runPhase("retained", 512, 8192, true);
            r.stop();
            r.dump(output);
        }

        List<RecordedEvent> all = RecordingFile.readAllEvents(output);
        List<RecordedEvent> phases = all.stream()
                .filter(e -> e.getEventType().getName()
                        .equals("lesson.LoadPhase"))
                .sorted(Comparator.comparing(RecordedEvent::getStartTime))
                .collect(Collectors.toList());

        if (phases.size() != 2) {
            throw new AssertionError(
                    "Expected 2 phase markers, got " + phases.size());
        }
        RecordedEvent transientPhase = phases.get(0);
        RecordedEvent retainedPhase = phases.get(1);

        boolean phaseNamesCorrect =
                transientPhase.getString("phase").equals("transient") &&
                retainedPhase.getString("phase").equals("retained");
        boolean payloadPlanCorrect =
                transientPhase.getLong("requestedPayloadBytes")
                        == 24000L * 4096 &&
                retainedPhase.getLong("requestedPayloadBytes")
                        == 512L * 8192;
        boolean countsCorrect =
                transientPhase.getLong("operations") == 24000L &&
                retainedPhase.getLong("operations") == 512L &&
                transientPhase.getInt("retainedArrays") == 0 &&
                retainedPhase.getInt("retainedArrays") == 256;
        boolean timesCorrect =
                transientPhase.getDuration().toNanos() > 0 &&
                retainedPhase.getDuration().toNanos() > 0 &&
                !retainedPhase.getStartTime()
                        .isBefore(transientPhase.getEndTime());
        boolean heapSnapshotsValid =
                transientPhase.getLong("heapUsedBefore") >= 0 &&
                transientPhase.getLong("heapUsedAfter") >= 0 &&
                retainedPhase.getLong("heapUsedBefore") >= 0 &&
                retainedPhase.getLong("heapUsedAfter") >= 0;

        if (!(phaseNamesCorrect && payloadPlanCorrect &&
                countsCorrect && timesCorrect && heapSnapshotsValid)) {
            throw new AssertionError("JFR phase fields/timestamps mismatch");
        }

        long tlabTransient = all.stream()
                .filter(HeapLoadCorrelationDemo::isTlabSample)
                .filter(e -> inWindow(e.getStartTime(), transientPhase))
                .count();
        long tlabRetained = all.stream()
                .filter(HeapLoadCorrelationDemo::isTlabSample)
                .filter(e -> inWindow(e.getStartTime(), retainedPhase))
                .count();
        long gcEvents = all.stream()
                .filter(e -> e.getEventType().getName()
                        .equals("jdk.GarbageCollection"))
                .count();
        long heapSummaryEvents = all.stream()
                .filter(e -> e.getEventType().getName()
                        .equals("jdk.GCHeapSummary"))
                .count();

        System.out.println("phase markers: " + phases.size());
        System.out.println("phase names correct: " + phaseNamesCorrect);
        System.out.println("payload plan correct: " + payloadPlanCorrect);
        System.out.println("operation/retention fields correct: " + countsCorrect);
        System.out.println("phase timestamps ordered: " + timesCorrect);
        System.out.println("heap snapshots valid: " + heapSnapshotsValid);
        System.out.println("retained arrays held: " + RETAINED.size());
        System.out.println("JFR file nonempty: " + (Files.size(output) > 0));
        System.out.println("TLAB-related samples during transient phase: "
                + tlabTransient);
        System.out.println("TLAB-related samples during retained phase: "
                + tlabRetained);
        System.out.println("GC events: " + gcEvents);
        System.out.println("GC heap summary events: " + heapSummaryEvents);
    }
}
```

### 8.2. Cách biên dịch/chạy

Linux/macOS:

```bash
mkdir -p jfr-heap-output
javac --release 11 -encoding UTF-8 HeapLoadCorrelationDemo.java
java -Xms32m -Xmx64m HeapLoadCorrelationDemo jfr-heap-output
jfr summary jfr-heap-output/heap-load.jfr
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path .\jfr-heap-output
javac --release 11 -encoding UTF-8 HeapLoadCorrelationDemo.java
java -Xms32m -Xmx64m HeapLoadCorrelationDemo .\jfr-heap-output
jfr summary .\jfr-heap-output\heap-load.jfr
```

`-Xms32m -Xmx64m` là **cấu hình phòng lab** để kích thích GC, không phải heap size đề xuất cho production. Chương trình không gọi `System.gc()` vì ép GC làm thay đổi dữ liệu thời gian đang cần quan sát.

### 8.3. Stdout đã kiểm thử

**Tám dòng đầu là các assertions về tính đúng của fixture:**

```text
phase markers: 2
phase names correct: true
payload plan correct: true
operation/retention fields correct: true
phase timestamps ordered: true
heap snapshots valid: true
retained arrays held: 256
JFR file nonempty: true
```

**Bốn dòng sau có số đếm phụ thuộc runtime. Một lần chạy thực tế:**

```text
TLAB-related samples during transient phase: 329
TLAB-related samples during retained phase: 12
GC events: 7
GC heap summary events: 14
```

**Không hardcode 329/12/7/14** làm expected output mỗi lần chạy. Các con số đó có thể đổi khi JDK/vendor, GC, heap size, tốc độ CPU, JIT, TLAB hoặc scheduling thay đổi. Đo chính xác cần dùng methodology và thời lượng đủ dài.

`jfr summary` trong một lần chạy nhận diện `lesson.LoadPhase` có 2 events, `jdk.GarbageCollection` có 7 events, `jdk.GCHeapSummary` có 14 events và nhiều TLAB-related samples. Số `jdk.CPULoad` có thể **0** ở một recording rất ngắn; không được diễn giải là CPU idle.

### 8.4. Ý nghĩa của chương trình

- `phase markers: 2`: file chứa cả cửa sổ transient và retained.
- `payload plan correct`: các field ứng dụng chứa đúng `24000*4096` và `512*8192` **payload bytes đã yêu cầu**; chưa tính object headers/allocations phụ.
- `retained arrays held: 256`: strong references trong static List còn giữ 256 mảng, không khẳng định đây là toàn bộ JVM live heap.
- `heap snapshots valid`: số heap used lấy từ MemoryMXBean hợp lệ, nhưng test **không assert heapUsedAfter > heapUsedBefore**, vì GC có thể xảy ra xen giữa.
- Hai sample counts là **số event thuộc hai loại TLAB được lọc theo timestamp phase**. Chúng không là tổng số object/bytes.
- GC counts cho biết trong recording có hoạt động GC. Muốn phân tích pause cần xem chính những pause metrics, chứ không cộng tùy tiện event durations.

Trong source, `lastTransient` là tham chiếu volatile đến mảng mới gần nhất để công việc cấp phát hiện diện rõ trong demo; `RETAINED` giữ các mảng mạnh qua phase. Không lấy kỹ thuật tạo tải này làm mẫu code ứng dụng thực tế.

## 9. Đọc file JFR và tương quan trong JDK Mission Control

Sau khi có `heap-load.jfr`, dùng CLI:

```bash
jfr summary jfr-heap-output/heap-load.jfr
jfr metadata jfr-heap-output/heap-load.jfr
jfr print --events lesson.LoadPhase jfr-heap-output/heap-load.jfr
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary jfr-heap-output/heap-load.jfr
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB jfr-heap-output/heap-load.jfr
```

`jfr summary` hiển thị event type counts và kích thước, `jfr metadata` cho biết schema thực tế; `jfr print --events` hữu ích để đọc một tập event hẹp. Không xuất toàn bộ .jfr của production vào console vì có thể chứa stack trace, đường dẫn, dữ liệu nhạy cảm.

Trong JMC (tên tab có thể thay đổi theo phiên bản):

1. Mở file `.jfr` và tìm nhóm **Memory / Allocations** (hoặc Event Browser).
2. Xem top classes, threads, allocation stack traces và loại sampling.
3. Xem **Memory / Garbage Collections**, GC pause và heap usage before/after.
4. Nếu recording đủ dài, so CPU load/CPU method samples.
5. Đặt giai đoạn load của ứng dụng và các operation/request metrics lên cùng timeline.
6. So baseline/peak/recovery theo traffic mix, không so hai cửa sổ khác độ dài và gọi đó là regression.

### 9.1. Tránh đọc sai schema event

Khi hỗ trợ nhiều JDK:

```java
// Snippet: biến RecordedEvent event đã được đọc từ file.
if (event.hasField("objectClass")) {
    jdk.jfr.consumer.RecordedClass clazz =
            event.getClass("objectClass");
    if (clazz != null) {
        System.out.println(clazz.getName());
    }
}
if (event.hasField("weight")) {
    long sampleWeight = event.getLong("weight");
    // Diễn giải theo đúng loại event và sampling model.
}
```

Đây là **mã minh họa, không độc lập**. `hasField`/`getFields` là cách kiểm tra an toàn khi event schema có thể khác. Không lấy `weight` của `ObjectAllocationSample` để cộng với `allocationSize` của TLAB event.

Với file lớn, tránh `RecordingFile.readAllEvents` vì nó tạo List giữ toàn bộ events; thay bằng `RecordingFile.hasMoreEvents()/readEvent()` trong vòng lặp để tổng hợp theo bucket và giải phóng memory.

## 10. Cách đọc các tình huống điển hình

### 10.1. Traffic cao, allocation và GC tăng, heap sau GC ổn định

Đây có thể là **allocation pressure theo tải** chứ không phải leak. Xem bytes/request, top allocation stacks và GC pauses so với latency budget. Nếu code có nhiều copy/buffer tạm, tối ưu sau khi profiling xác định điểm nóng; đừng đổi collector trước khi có bằng chứng.

### 10.2. RPS không đổi nhưng bytes/operation tăng sau deploy

Nghi **allocation regression**: một endpoint tạo nhiều temporary String, boxing, DTO, buffer hoặc xử lý retry hơn. Dùng JFR stack traces và metrics per endpoint, so hai build dưới workload như nhau rồi thử sửa code.

### 10.3. Đáy heap sau GC liên tục tăng

Có thể có **object retention**, nhưng vẫn phải tách cache warm-up hợp lệ và request backlog. Kiểm tra ownership, eviction policy, thread-local objects, unbounded collections, session buffers, retaining paths tới GC roots. Khi cần, dùng heap dump/live-object tools được phê duyệt. Heap statistics hoặc heap dump có thể gây pause, memory pressure và lộ dữ liệu nhạy cảm.

### 10.4. Heap ổn nhưng RSS tăng

Xem direct buffers, native memory, metaspace, code cache, thread stacks, JNI và container RSS. Có thể dùng `BufferPoolMXBean`/Native Memory Tracking theo cấu hình phù hợp; heap-only profile không chứng minh native leak.

### 10.5. Latency xấu nhưng allocation samples ít

Không mặc định heap là thủ phạm. Kiểm tra CPU scheduling, locks, I/O, downstream latency, thread pool saturation, retry amplification và request tracing. Sampling thiếu dữ liệu trong một cửa sổ ngắn cũng có thể giải thích số samples thấp.

## 11. Bảng ví dụ minh họa cách chuẩn hóa

Giả sử hai cửa sổ đều dài 60 giây, cùng cấu hình JFR và request mix:

| Metric (giả định) | Baseline | High load |
| --- | ---: | ---: |
| Completed operations | 6.000 | 18.000 |
| Throughput | 100 ops/s | 300 ops/s |
| Estimated allocation | 120 MiB/s | 360 MiB/s |
| Estimated allocation mỗi operation | ~1,2 MiB | ~1,2 MiB |
| GC count | 4 | 12 |
| Heap sau GC | 500 MiB | 510 MiB |
| p95 latency | 40 ms | 45 ms |

**Các số trên chỉ là ví dụ giả định**, không phải output từ Java ở mục 8. Khi bytes/op không đổi, heap sau GC gần ổn và RPS tăng gấp ba, tổng allocation/s và GC count tăng ba lần có thể là điều hoàn toàn phù hợp.

Nếu 60 giây có **0,3 giây dừng stop-the-world được đo đúng**, pause fraction = `0.3/60 = 0.005 = 0.5%`. Không suy ra p99 latency chỉ tăng 0,5%: pause phân bố không đồng đều.

Nếu RPS ổn nhưng estimated bytes/operation tăng mạnh, xem regression; nếu đáy heap sau GC tăng đều, xem retention. **Kết luận phải dựa trên nhiều chỉ số, không chỉ một cột.**

## 12. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Sample count là object count | Sai mô hình sampling | Dùng weight/metrics đúng schema |
| Tổng sample allocationSize là exact allocated bytes | Bỏ qua TLAB và sample bias | Tính estimate đúng hoặc dùng nguồn đo bổ sung |
| Gộp ObjectAllocationSample và TLAB counts | Hai loại sampling khác nhau | Tách event types |
| Không thấy CPULoad nghĩa CPU=0 | Recording ngắn/periodic event chưa phát | Ghi lâu hơn, xem hệ thống metrics |
| Heap used cao = leak | Garbage có thể chưa GC | So heap-after-GC qua nhiều lần |
| Heap committed = live set | Committed là capacity | Xem used/live evidence |
| GC count cao = lỗi | Tải cao có thể tạo GC hợp lý | Chuẩn hóa theo operations và pause budget |
| Tổng GC duration = STW pause | Concurrent GC không dừng toàn bộ app | Dùng đúng pause fields |
| RSS tăng = heap leak | Có cả off-heap/native | Theo dõi heap và native riêng |
| So mẫu khác JDK/template | Sampling policy thay đổi | Đồng nhất môi trường hoặc ghi khác biệt |
| So raw bytes/s khi RPS khác | Không chuẩn hóa tải | Dùng bytes/op và request mix |
| Bỏ warm-up | Cache/JIT tăng dữ liệu lúc khởi động | Phân tích steady state |
| Ép System.gc trong benchmark | GC nhân tạo thay đổi latency | Không ép GC thường xuyên |
| Bật Heap Statistics thường trực | Có thể gây GC nặng/overhead | Chỉ bật điều tra khi phù hợp |
| Dùng .jfr như transaction log | Sampling/filter/retention không bảo đảm audit | Dùng audit log có durability |
| Bỏ qua timezone | Sai phép gán event vào phase | Dùng Instant/UTC và clock sync |
| Ghi token/PII trong JFR | Rò rỉ dữ liệu | Chỉ ghi metadata được phép |
| Đọc toàn bộ file quá lớn vào RAM | OOM và memory pressure | Dùng RecordingFile streaming |
| Kết luận nhân quả từ cùng timestamp | Chỉ là correlation | Thử nghiệm thay đổi có kiểm soát |

## 13. Checklist khi làm trên production hoặc CI

- [ ] JDK/runtime, GC algorithm, heap limit và JFR settings được ghi rõ.
- [ ] Event type và schema có thật bằng `jfr summary/metadata` hoặc JFR API.
- [ ] Phân biệt TLAB events, ObjectAllocationSample/weight và measured bytes.
- [ ] Có application throughput, concurrency, request mix, p95/p99 cùng window.
- [ ] Có baseline, load ramp, steady-state và recovery (nếu phù hợp).
- [ ] So allocation per operation, không chỉ tổng sample counts.
- [ ] So heap-after-GC qua nhiều chu kỳ tương đương.
- [ ] Phân biệt GC duration, pause, concurrent work và CPU utilization.
- [ ] Giới hạn profiling duration, size và stack trace overhead.
- [ ] Không ép full/old GC để tạo mốc số liệu production khi không cần.
- [ ] Nếu nghi retention, xác nhận live objects và retaining paths.
- [ ] Test canary/thay đổi code dưới tải kiểm soát trước khi chốt nguyên nhân.
- [ ] Tệp JFR được lưu/anonymize/retention theo chính sách, không chứa secrets.

## 14. Bài tập tự kiểm tra

**1.** Allocation rate tăng gấp 3 khi throughput tăng gấp 3, chứng minh leak?  
**Đáp án:** Không. Phải kiểm tra bytes/operation, heap sau GC và latency.

**2.** Vì sao `jdk.ObjectAllocationInNewTLAB` không đếm mọi object?  
**Đáp án:** Nhiều allocations được phục vụ trong một TLAB; đây là các điểm quan sát theo sampling/refill, không phải log mọi object.

**3.** Có thể cộng `ObjectAllocationSample#weight` với `OutsideTLAB#allocationSize` rồi gọi tổng bytes?  
**Đáp án:** Không, vì semantics và phương pháp sampling khác nhau.

**4.** `MemoryMXBean.getHeapMemoryUsage().getUsed()` cuối phase là live set?  
**Đáp án:** Không nhất thiết có GC trước đó.

**5.** Một JFR recording ngắn không có `jdk.CPULoad` nghĩa CPU idle?  
**Đáp án:** Không, event periodic có thể chưa được phát.

**6.** Khi nghi leak, chỉ xem top allocation stack là đủ?  
**Đáp án:** Không. Phải xem object còn sống, retaining references và heap-after-GC trend.

**7.** Tại sao chương trình demo cần hai custom phase markers?  
**Đáp án:** Để gắn sampling/heap/GC data với giai đoạn transient và retained trên cùng timeline.

**8.** Khi heap phẳng nhưng RSS tăng, kiểm tra gì?  
**Đáp án:** Native/off-heap buffers, thread stacks, metaspace, code cache và process/container metrics.

**9.** Đã quan sát 7 GC events trong lab, có yêu cầu các máy khác phải đúng 7?  
**Đáp án:** Không. Số GC và samples phụ thuộc runtime, JIT và workload timing.

**10.** Có nên dùng heap statistics nặng trong mọi production recording?  
**Đáp án:** Không. Nó có thể ảnh hưởng chi phí và gây GC nặng; chỉ dùng khi mục đích live-set analysis đủ rõ.

## 15. Ghi nhớ và tài liệu chính thức

**Nguyên tắc vàng:** **Allocation samples chỉ vị trí tạo object; heap-after-GC cho biết xu hướng bộ nhớ còn giữ; GC events phản ánh công việc thu gom; tải ứng dụng đưa ra mẫu số và impact.** Muốn phân tích đúng phải nối bốn loại số liệu bằng timestamp, đúng sampling model và normalize theo operation.

Chương trình `HeapLoadCorrelationDemo` dùng Java 11 JFR, `MemoryMXBean` và `GarbageCollectorMXBean`, đã biên dịch thành công với `--release 11` và đọc lại file có **2 custom phase markers**, **256 mảng giữ lại**, GC events và TLAB-related events. Những counts mang tính sampling phải được diễn giải theo JDK/GC thực tế.

**Nguồn chính thức còn áp dụng:**

1. [Oracle Java 11 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshoot-performance-issues-using-jfr.html).
2. [Oracle Java 11 — Diagnostic Tools / JDK Mission Control](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html).
3. [Oracle Java 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html).
4. [Oracle Java 11 — Configuration](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Configuration.html).
5. [Oracle Java 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html).
6. [Oracle Java 11 — RecordedObject và hasField/getClass/getLong](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html).
7. [Oracle Java 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
8. [Oracle Java 11 — MemoryMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html).
9. [Oracle Java 11 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html).
10. [Oracle — JDK Mission Control Flight Recorder Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html).
11. [Dev.java — JFR commands and analysis](https://dev.java/learn/jvm/monitoring-troubleshooting/monitoring/jfr/).
