# Phân biệt tốc độ cấp phát với dữ liệu được giữ lại (Heap profiling — Java 11)

**Heap profiling** trong Java có hai câu hỏi khác nhau: **(1) đối tượng được cấp phát nhanh đến mức nào?** và **(2) những đối tượng nào vẫn được giữ lại trong heap?** Một ứng dụng có thể tạo hàng gigabyte đối tượng tạm mỗi phút mà heap sau GC ổn định; ứng dụng khác chỉ cấp phát ít mỗi giây nhưng liên tục giữ references, khiến live heap tăng không giới hạn.

**Allocation rate cao không tự chứng minh memory leak. Retained heap tăng cũng không đồng nghĩa allocation rate cao.** Muốn tối ưu đúng cần biết đang xử lý **object churn/GC pressure** hay **retention/leak**.

Bài thuộc nhóm **Heap profiling**, module **Java 11**, chỉ sử dụng API và công cụ còn phù hợp trên JDK hiện đại: **Java Flight Recorder (JFR)**, **JDK Mission Control**, `jcmd`, GC unified logging, public `ThreadMXBean` extension và **Eclipse Memory Analyzer (MAT)**. Ba chương trình Java đầy đủ được biên dịch bằng `javac --release 11`; không dựa vào profiler hoặc JVM options đã lỗi thời.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt allocated bytes, allocation rate, live heap, retained size, shallow size, committed heap và RSS.
2. Tính allocation rate từ hai counters và khoảng thời gian.
3. Đọc đồ thị heap dạng răng cưa, đặc biệt là **after-GC baseline**.
4. Hiểu GC roots, dominator tree và paths to GC roots.
5. Dùng JFR Java 11 để tìm allocation sites và old-object samples mà không nhầm sampling với full census.
6. Dùng `ThreadMXBean`, `jcmd GC.class_histogram` và `GC.heap_dump` đúng phạm vi.
7. Chạy chương trình minh họa temporary allocations so với static-cache retention.
8. Phân biệt metric tăng do warmup/traffic/caching hợp lệ với leak thật.
9. Biết các giới hạn overhead, bảo mật và độ tin cậy của heap dumps/JFR.
10. Thiết kế thử nghiệm so sánh nhiều thời điểm để xác định root cause.

## 2. Các khái niệm đo lường cần tách riêng

| Chỉ số | Đơn vị | Câu hỏi được trả lời | Không nói được |
| --- | --- | --- | --- |
| **Allocated bytes** | B | Tổng bytes đã từng cấp phát trong giai đoạn | Bao nhiêu bytes còn sống |
| **Allocation rate** | B/s, MB/s | Tốc độ tạo mới object | Có leak hay không |
| **Heap used** | B | Heap đang dùng tại một thời điểm | Chỉ gồm các objects còn sống sau GC |
| **Live set** | B | Dữ liệu còn reachable theo GC roots tại một thời điểm | Tổng bytes đã từng cấp phát |
| **Shallow size** | B/object | Kích thước của riêng object gồm header/fields/alignment | Kích thước đồ thị nó đang giữ |
| **Retained size** | B/object hoặc group | Bao nhiêu bộ nhớ sẽ trở thành unreachable nếu bỏ retaining object/group | Tổng mọi đối tượng nó trỏ tới nếu có shared references |
| **Heap committed** | B | JVM đã cam kết dung lượng heap từ OS | Live heap |
| **Max heap** | B | Giới hạn Java heap, ví dụ `-Xmx256m` | Tổng RAM process |
| **RSS** | B | Bộ nhớ vật lý process/container | Riêng Java heap |
| **GC pause/frequency** | ms, lần/s | Chi phí thu gom | Ai giữ object |
| **Class histogram** | instances/bytes | Objects hiện diện theo class tại snapshot | Allocation rate hoặc root giữ chúng |

**Không lấy một chỉ số có tên “allocated” từ profiler A rồi trừ trực tiếp một heap snapshot từ công cụ B** nếu sampling model, thời điểm, units và phạm vi khác nhau.

### Công thức

```text
Allocation rate (B/s)
    = (allocatedBytes(t2) - allocatedBytes(t1))
      / (t2 - t1)

Ví dụ: 500 MB cấp phát trong 10 s -> 50 MB/s.

Live-set growth rate (xấp xỉ)
    = (liveBytes(t2) - liveBytes(t1))
      / (t2 - t1)
```

Với live-set growth, cần đo ở **hai pha tương đương sau GC**, khống chế workload và chú ý hệ thống có thể đang warmup hoặc thay đổi số người dùng. Heap used trước một lần GC không đồng nhất với live objects sau GC.

## 3. Cấp phát nhiều nhưng giữ lại ít

Ví dụ một ứng dụng có tổng 6 GB allocations trong một phút, nhưng live heap ổn định 20 MB:

```text
Cumulative allocation: 0 GB ----------------> 6 GB

Heap used:
100 MB  /\     /\     /\     /\     /\
       /  \   /  \   /  \   /  \   /  \
 20 MB    \_/    \_/    \_/    \_/    \_

          Sau mỗi GC, live baseline gần 20 MB.
```

**Không có bằng chứng memory leak**, vì phần lớn objects tạm đã hết reachable và được GC thu hồi. Dù vậy, allocation rate cao có thể:
- Làm young GC xảy ra thường xuyên.
- Tăng CPU và memory bandwidth.
- Tăng latency trong hot path.
- Cho thấy code tạo nhiều temporary arrays, boxing, JSON/string trung gian hoặc objects được dùng đúng một lần.

**Phương án:** dùng allocation flame graph/JFR để tìm call stacks, tối ưu những cấu trúc tạm khi có số liệu chứng minh. Không tự áp object pooling cho mọi thứ: pooling có thể giữ objects lâu hơn và làm retained heap tăng.

## 4. Cấp phát chậm nhưng giữ lại liên tục

Một cache không có eviction có thể thêm 100 KB mỗi giây và không bao giờ bỏ references. Sau nhiều giờ, live heap tăng dù allocation rate không cao:

```text
GC root
   |
   v
static Map<String, Payload> cache
   +--> entry A --> payload
   +--> entry B --> payload
   +--> entry C --> payload
   ...
Không có TTL / max size / cleanup
   |
   v
Objects vẫn reachable, GC không thể thu hồi
```

Trong Java, **logical memory leak** thường là **đối tượng không còn cần theo nghiệp vụ nhưng vẫn có strong references**. GC không có cách biết một cache entry đã hết giá trị. Nó chỉ xét reachability.

Những nguyên nhân phổ biến:
- Static Map/List không giới hạn.
- Queue chỉ enqueue nhưng không xử lý hoặc không có backpressure.
- Session/connection context không expire.
- Listener/subscriber/callback không unregister.
- Thread-local data không được dọn theo lifecycle.
- Executor tasks giữ request context.
- Class loader không được release do registry/thread/reference bên ngoài.

**Không phải mọi object sống lâu đều leak.** Cache có giới hạn, active sessions và immutable reference data có thể là retention hợp lệ.

## 5. Đọc heap sau GC và tránh nhầm warmup

Heap used bình thường lên xuống theo kiểu **sawtooth**. Nên nhìn những điểm **sau** GC trong các giai đoạn tải tương đương.

| Diễn biến | Cách hiểu ban đầu |
| --- | --- |
| Heap used tăng rồi giảm, after-GC ổn định | Nhiều temporary allocations; có thể là bình thường |
| Allocation rate cao, GC thường xuyên, after-GC ổn định | Allocation pressure, chưa phải leak |
| After-GC tăng theo thời gian dù workload ổn định | Có thêm live objects; cần tìm retaining owners |
| Heap committed tăng, after-GC used ổn định | JVM giữ capacity; chưa phải leak |
| RSS/container memory tăng, Java heap ổn định | Có thể là native/off-heap memory |
| Old-gen used cao ở workload lớn | Có thể là dữ liệu sống lâu hợp lệ |

Một lần đo ngay lúc startup so với lúc peak traffic **không đủ**. JVM có thể lazy load classes, warm caches, tăng số session, JIT compile và thay đổi heap capacity. **Baseline sau GC tăng** là tín hiệu điều tra, không tự là chẩn đoán.

### RSS không phải Java heap

Process RSS còn có thread stacks, direct buffers, metaspace, JIT code cache, mapped files và JNI/native allocations. Nếu RSS tăng mà heap live ổn định, cần điều tra memory ngoài heap thay vì chỉ tăng `-Xmx`.

## 6. GC roots, shallow size, retained size

**GC roots** là những điểm khởi đầu xác định object reachability: ví dụ static fields, active thread stacks, JNI handles và runtime structures.

**Shallow size** là bộ nhớ riêng của một object. Với `byte[8192]`, 8192 chỉ là **payload length**; heap object thực tế còn array header và alignment. Kích thước phụ thuộc architecture, JVM và cấu hình.

**Retained size** là kích thước objects có thể trở thành unreachable nếu bỏ object/group đang giữ chúng theo reference graph. Ví dụ:

```text
GC root
   |
   v
Cache manager (shallow nhỏ)
   |
   v
HashMap / entries
   +--> byte[10 MB]
   +--> byte[12 MB]
   +--> byte[ 8 MB]

Retained size của cache có thể rất lớn.
```

**Lưu ý shared references:** nếu một object còn được root khác giữ, xóa cache không làm nó unreachable; retained size không đơn giản là tổng mọi references của cache. **Dominator Tree** trong MAT dùng quan hệ dominator để tính những vùng mà một object/group có trách nhiệm giữ.

**Paths to GC Roots** giúp tìm:
- Object được static registry, ThreadLocal, queue hay callback nào giữ?
- Path đó có hợp lý với business lifecycle không?
- Xóa/unregister/cancel đúng chỗ có làm reference biến mất không?

**Allocation site trả lời “object được tạo ở đâu?”; root path trả lời “vì sao object còn sống?”.**

## 7. JFR events trong Java 11

| Event Java 11 | Mục đích | Giới hạn |
| --- | --- | --- |
| `jdk.ObjectAllocationInNewTLAB` | Allocation ở điểm thread nhận TLAB mới; có class/stack khi bật, `allocationSize`, `tlabSize` | **Không có 1 event cho mỗi new object** |
| `jdk.ObjectAllocationOutsideTLAB` | Allocation ngoài TLAB, có class, stack, allocationSize | Không suy ra retention |
| `jdk.ThreadAllocationStatistics` | Thông tin allocated bytes theo thread | Không có live heap |
| `jdk.GCHeapSummary` | Heap usage quanh các đợt GC | Không có reference graph |
| `jdk.GarbageCollection` | GC activity/pause | Không có mọi object |
| `jdk.OldObjectSample` | Mẫu objects sống lâu, có thể có allocation stack/root path | Sampling, không phải full heap snapshot |

**Phân biệt phiên bản:** Event `jdk.ObjectAllocationSample` là cơ chế sampling ở **JDK 16+**, không dùng nó như một event của Java 11.

### TLAB sampling không phải toàn bộ allocation

**TLAB (Thread-Local Allocation Buffer)** là vùng nhỏ dành cho mỗi thread tạo objects nhanh. Khi TLAB hết, thread lấy vùng mới. `ObjectAllocationInNewTLAB` ghi **điểm cấp phát liên quan TLAB mới**, không ghi mọi lần `new` trong TLAB.

- `allocationSize` là kích thước object được ghi ở event, không phải tất cả bytes đã cấp phát.
- `tlabSize` mô tả vùng TLAB liên quan, có thể giúp profiler ước lượng tổng allocation pressure.
- Tổng `allocationSize` được ghi **không phải total allocated bytes**.
- Event ngoài TLAB không đồng nghĩa object bị leak.
- Không có sample không chứng minh không có allocation.

`OldObjectSample` dành cho objects tồn tại lâu, có thể ghi allocation site, tuổi và path-to-GC-roots nếu có cấu hình phù hợp. Nó cũng chỉ lấy mẫu: muốn phân tích **retained size chính xác theo snapshot**, cần heap dump/object graph.

## 8. Chạy JFR và đọc TLAB allocation events

Chỉ dùng khi có quyền xem process và thu diagnostics:

```sh
jcmd -l
jcmd <PID> JFR.start name=HeapProfile settings=profile duration=60s filename=alloc.jfr
jcmd <PID> JFR.check
```

Thay `<PID>` bằng PID thật. `profile` có thể gây overhead lớn hơn `default`, phù hợp điều tra có giới hạn thời gian. Nếu cần dump trước khi kết thúc:

```sh
jcmd <PID> JFR.dump name=HeapProfile filename=alloc-snapshot.jfr
```

Khi cần kết thúc recording:

```sh
jcmd <PID> JFR.stop name=HeapProfile
```

Đọc allocation events từ file đã tạo:

```sh
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB alloc.jfr
```

Các events có xuất hiện hay không còn phụ thuộc JFC settings, runtime và workload. Không mặc định file có dữ liệu, và không đọc `jfr print` như một phép tổng hợp allocation chính xác nếu nó chỉ hiển thị sampled events.

## 9. `jcmd` và heap dump khi nghi retention

### Class histogram

```sh
jcmd <PID> GC.class_histogram
```

Đây là **snapshot instances và bytes theo class**, không phải allocation rate. Một số class như `byte[]` và `java.lang.String` có thể đứng đầu hoàn toàn bình thường. Tìm retaining owner qua heap dump nếu cần.

**Impact:** đây có thể là tác vụ nặng, gây pause theo heap size. Option `-all` nếu dùng sẽ gồm **cả unreachable objects**, không được coi là snapshot live thuần.

### Heap dump HPROF

```sh
jcmd <PID> GC.heap_dump heap-snapshot.hprof
```

Theo công cụ Java 11, heap dump có **high impact** và mặc định có thể yêu cầu **full GC** nếu không dùng `-all`. HPROF có thể rất lớn và chứa token, credentials, request data và PII.

Chỉ chạy khi được phép. Hạn chế quyền file, chọn đường dẫn bảo mật, đủ disk, chọn thời gian ít tác động, không upload ra bên ngoài tùy tiện và có retention/xóa an toàn. Đừng dùng `-all` rồi kết luận mọi object trong dump đều còn sống.

### MAT Dominator Tree

Trong Eclipse Memory Analyzer:
1. Mở HPROF từ nguồn đáng tin cậy.
2. Xem class histogram và **Dominator Tree**.
3. Tìm object/group retained size lớn.
4. Xem **Paths to GC Roots** của payload đáng nghi.
5. Kiểm tra cache/lifecycle của retaining owner.
6. Thu lại snapshot cùng tải sau sửa để kiểm chứng.

### JFR Old Object Sample và GC roots

Có thể yêu cầu thu đường đến roots khi dump JFR trong tình huống nghi leak:

```sh
jcmd <PID> JFR.dump name=HeapProfile filename=retention.jfr path-to-gc-roots=true
jfr print --events jdk.OldObjectSample retention.jfr
```

`path-to-gc-roots=true` có thể gây overhead/pause đáng kể. Dùng chỉ khi được phép và thật sự cần; xác minh flags trên JVM bằng `jcmd <PID> help JFR.dump`. Không có event `OldObjectSample` trong file **không bác bỏ memory leak**.

### Unified GC logging

Java 11 hỗ trợ `-Xlog`:

```sh
java -Xmx256m -Xlog:gc*,gc+heap=debug:file=gc.log:time,uptime,level,tags MyApp
```

`MyApp` là tên class ứng dụng đã được compile, đây là lệnh minh họa. Dùng GC logs để xem after-GC used, frequency/pause và so với workload. Không coi heap committed hoặc RSS đứng yên là thất bại GC.

## 10. Ví dụ 1 — cấp phát 16,45 MB payload nhưng giữ 0,40%

Chương trình tạo **2.000 mảng `byte[8192]` tạm** và **8 mảng `byte[8192]` được cache giữ**. Nó đếm **logical payload bytes**, không đo heap overhead hay retained size thực tế.

Tạo file **`AllocationRetentionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class AllocationRetentionDemo {
    private static final int BLOCK_SIZE = 8 * 1024;
    private static final int TEMPORARY_BLOCKS = 2_000;
    private static final int RETAINED_BLOCKS = 8;
    private static final List<byte[]> CACHE = new ArrayList<>();
    private static volatile byte[] escape;

    private static long allocateTemporary() {
        long payloadBytes = 0;
        for (int i = 0; i < TEMPORARY_BLOCKS; i++) {
            byte[] block = new byte[BLOCK_SIZE];
            block[0] = (byte) i;
            escape = block;
            payloadBytes += block.length;
        }
        escape = null;
        return payloadBytes;
    }

    private static long retain() {
        for (int i = 0; i < RETAINED_BLOCKS; i++) {
            byte[] block = new byte[BLOCK_SIZE];
            block[0] = (byte) i;
            CACHE.add(block);
        }
        long bytes = 0;
        for (byte[] block : CACHE) {
            bytes += block.length;
        }
        return bytes;
    }

    public static void main(String[] args) throws InterruptedException {
        if (args.length > 1 ||
                (args.length == 1 && !args[0].equals("--pause"))) {
            throw new IllegalArgumentException(
                    "Usage: java AllocationRetentionDemo [--pause]");
        }
        long temporaryPayloadBytes = allocateTemporary();
        long retainedPayloadBytes = retain();
        long totalPayloadBytes = temporaryPayloadBytes + retainedPayloadBytes;

        System.out.println("Temporary blocks allocated: " + TEMPORARY_BLOCKS);
        System.out.println("Temporary payload bytes: " +
                temporaryPayloadBytes);
        System.out.println("Total payload bytes allocated: " +
                totalPayloadBytes);
        System.out.println("Retained entries before clear: " +
                CACHE.size());
        System.out.println("Retained payload bytes before clear: " +
                retainedPayloadBytes);
        System.out.printf(Locale.ROOT,
                "Retained-to-allocated payload ratio: %.2f%%%n",
                100.0 * retainedPayloadBytes / totalPayloadBytes);

        if (args.length == 1) {
            System.out.println("Inspect live phase, PID: " +
                    ProcessHandle.current().pid());
            Thread.sleep(20_000);
        }

        CACHE.clear();
        System.out.println("Retained entries after clear: " +
                CACHE.size());
        if (args.length == 1) {
            System.out.println("Inspect cleared phase, PID: " +
                    ProcessHandle.current().pid());
            Thread.sleep(20_000);
        }
    }
}
```

Biên dịch/chạy:

```sh
javac --release 11 -encoding UTF-8 AllocationRetentionDemo.java
java -Xmx128m AllocationRetentionDemo
```

**Stdout chính xác (không có `--pause`):**

```text
Temporary blocks allocated: 2000
Temporary payload bytes: 16384000
Total payload bytes allocated: 16449536
Retained entries before clear: 8
Retained payload bytes before clear: 65536
Retained-to-allocated payload ratio: 0.40%
Retained entries after clear: 0
```

**Giải thích:**
- `escape` là volatile reference để phép cấp phát có observable effect; mỗi gán mới thay reference cũ và cuối cùng gán `null`.
- `CACHE` là một `static final List`. `final` chỉ cố định tham chiếu tới List; content vẫn mutable và giữ strong references của 8 arrays.
- Tổng payload được tạo là `16.449.536`, còn payload trong cache là `65.536`. Đây là **tỷ lệ payload logic**, không phải retained heap do dominator tree tính.
- `CACHE.clear()` bỏ đường giữ tham chiếu, nhưng không buộc JVM lập tức GC hoặc trả committed heap cho OS.

**Quan sát live và cleared phases:** chạy:

```sh
java -Xmx128m AllocationRetentionDemo --pause
```

Chương trình in PID và dừng khoảng 20 giây khi cache đang giữ dữ liệu, sau đó `CACHE.clear()` và dừng thêm 20 giây. Dùng terminal khác để chạy `jcmd <PID> GC.class_histogram` khi cần. Không kỳ vọng histogram có chính xác 8 byte arrays, vì JVM và thư viện còn những arrays khác. Muốn biết reference path của một mảng, cần heap dump/MAT.

## 11. Ví dụ 2 — ThreadMXBean đếm allocation, không đếm retained

Java 11 có public management extension `com.sun.management.ThreadMXBean` (module `jdk.management`). Khi được hỗ trợ và bật, `getThreadAllocatedBytes(threadId)` trả **xấp xỉ cumulative heap bytes đã được cấp phát bởi thread**.

Đừng dùng `getTotalThreadAllocatedBytes()` trong bài tập Java 11 vì API đó được bổ sung về sau. Đây là public extension API, nhưng không được bảo đảm mọi JVM vendor đều hỗ trợ tính năng thống kê tương ứng.

Tạo file **`ThreadAllocationCounterDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import com.sun.management.ThreadMXBean;

public final class ThreadAllocationCounterDemo {
    private static volatile byte[] sink;

    private static long performAllocations() {
        long payload = 0L;
        for (int i = 0; i < 1_000; i++) {
            byte[] array = new byte[16 * 1024];
            array[0] = (byte) i;
            sink = array;
            payload += array.length;
        }
        sink = null;
        return payload;
    }

    public static void main(String[] args) {
        java.lang.management.ThreadMXBean standard =
                ManagementFactory.getThreadMXBean();
        if (!(standard instanceof ThreadMXBean)) {
            System.out.println("Thread allocation counter: unsupported");
            return;
        }
        ThreadMXBean extended = (ThreadMXBean) standard;
        if (!extended.isThreadAllocatedMemorySupported()) {
            System.out.println("Thread allocation counter: unsupported");
            return;
        }
        if (!extended.isThreadAllocatedMemoryEnabled()) {
            extended.setThreadAllocatedMemoryEnabled(true);
        }
        long id = Thread.currentThread().getId();
        long before = extended.getThreadAllocatedBytes(id);
        long logicalPayload = performAllocations();
        long after = extended.getThreadAllocatedBytes(id);

        if (before < 0 || after < 0) {
            System.out.println("Thread allocation counter: unavailable");
            return;
        }

        System.out.println("Logical payload bytes: " + logicalPayload);
        System.out.println("Measured allocation positive: " +
                (after > before));
        System.out.println("Measured count is cumulative: true");
        System.out.println("Retained byte count known from counter: false");
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 ThreadAllocationCounterDemo.java
java ThreadAllocationCounterDemo
```

**Stdout khi JVM thử nghiệm hỗ trợ counter:**

```text
Logical payload bytes: 16384000
Measured allocation positive: true
Measured count is cumulative: true
Retained byte count known from counter: false
```

Trên runtime không hỗ trợ, chương trình có thể in `Thread allocation counter: unsupported` hoặc `unavailable` rồi thoát.

**Tại sao raw allocated bytes không bằng logical payload?** Vì còn object headers, alignment và các allocations của thread không thuộc vòng lặp. Counter được ước lượng theo JVM và không giảm sau GC. Muốn tính rate, lấy `(after - before) / elapsedSeconds` trên cùng thread với khoảng đo hợp lệ; **không** dùng delta counter để suy ra heap còn sống.

## 12. Ví dụ 3 — 15.000 lần cấp phát nhưng JFR chỉ ghi một số events

Chương trình dùng `jdk.jfr.Recording` bật hai loại JFR events của Java 11, cấp phát **15.000 mảng `byte[2048]`** và đọc recording.

Tạo file **`JfrAllocationProbeDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrAllocationProbeDemo {
    private static volatile byte[] escape;

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("allocation-profile-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable("jdk.ObjectAllocationInNewTLAB")
                        .withStackTrace();
                recording.enable("jdk.ObjectAllocationOutsideTLAB")
                        .withStackTrace();
                recording.start();

                for (int i = 0; i < 15_000; i++) {
                    byte[] block = new byte[2048];
                    block[0] = (byte) i;
                    escape = block;
                }
                escape = null;
                recording.stop();
                recording.dump(file);
            }

            long inTlab = 0;
            long outsideTlab = 0;
            long reportedAllocationSize = 0;
            try (RecordingFile reader = new RecordingFile(file)) {
                while (reader.hasMoreEvents()) {
                    RecordedEvent event = reader.readEvent();
                    String name = event.getEventType().getName();
                    if ("jdk.ObjectAllocationInNewTLAB".equals(name)) {
                        inTlab++;
                        reportedAllocationSize +=
                                event.getLong("allocationSize");
                    } else if ("jdk.ObjectAllocationOutsideTLAB".equals(name)) {
                        outsideTlab++;
                        reportedAllocationSize +=
                                event.getLong("allocationSize");
                    }
                }
            }
            System.out.println("JFR file exists: " +
                    Files.isRegularFile(file));
            System.out.println("New-TLAB allocation records: " + inTlab);
            System.out.println("Outside-TLAB allocation records: " +
                    outsideTlab);
            System.out.println("Sum of recorded allocationSize: " +
                    reportedAllocationSize);
            System.out.println("Count/size represents all allocations: false");
            System.out.println("Retained heap known from these records: false");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 JfrAllocationProbeDemo.java
java JfrAllocationProbeDemo
```

**Một stdout đã được quan sát:**

```text
JFR file exists: true
New-TLAB allocation records: 16
Outside-TLAB allocation records: 0
Sum of recorded allocationSize: 33024
Count/size represents all allocations: false
Retained heap known from these records: false
```

**Các con số 16, 0 và 33.024 không cố định giữa JVM/run.** Đây là số của một lượt chạy thử nghiệm; số records còn phụ thuộc TLAB size, GC, runtime, threads và settings.

Vòng lặp tạo **15.000 × 2.048 = 30.720.000 byte payload**, nhưng JFR chỉ ghi một số điểm cấp phát liên quan TLAB. Tổng `allocationSize` trong những **events quan sát** không bằng total allocations, và các events không cho biết objects còn sống. Cần phân biệt JFR sampling với cumulative counter của `ThreadMXBean`, hoặc với heap dump.

## 13. So sánh ba cách nhìn một ứng dụng

| Công cụ | Thấy gì? | Câu hỏi nên dùng |
| --- | --- | --- |
| JFR allocation events/flame graph | Sampled/estimated allocation sites và threads | Đoạn code nào tạo quá nhiều temporary objects? |
| ThreadMXBean | Xấp xỉ cumulative allocated bytes theo thread | Thread nào tạo allocations nhiều trong khoảng đo? |
| GC logs/JFR heap summaries | Heap/GC theo thời gian | Live baseline sau GC có tăng không? |
| `jcmd GC.class_histogram` | Object counts và bytes theo class snapshot | Class nào nhiều/chiếm dung lượng ở thời điểm này? |
| MAT Dominator Tree | Object/group retained size lớn nhất | Ai giữ phần heap lớn nhất? |
| MAT Paths to GC Roots | Reference chain tới root | Vì sao object không bị GC thu hồi? |
| JFR `OldObjectSample` | Một số objects sống lâu | Có candidates đáng nghi nào để điều tra sâu? |

Nếu **allocation flame graph** nổi bật `StringBuilder` nhưng **heap after-GC ổn định**, thường điều tra object churn/CPU/GC. Nếu một `static Map` hiếm khi allocate nhưng có **retained size 2 GB**, điều tra lifecycle/eviction của Map chứ không chỉ tối ưu nơi tạo objects.

## 14. Quy trình điều tra một sự cố bộ nhớ

**Bước 1 — Xác định loại vấn đề.** Heap dùng tăng sau GC, GC frequency cao hay RSS tăng ngoài heap? Không áp một giải pháp cho cả ba.

**Bước 2 — Ghi môi trường và tải.** Thu JDK/vendor, GC mode, `-Xmx`, container limit, request rate, active sessions, queue depth, cache size, workload phase.

**Bước 3 — Đo allocation rate nếu nghi churn.** Dùng JFR, xem class/thread/call stacks, đối chiếu GC pauses và latency. Tối ưu các phép tạo temporary arrays, lặp serialize, boxing hoặc debug formatting khi có bằng chứng.

**Bước 4 — Đo live baseline nếu nghi leak.** Quan sát nhiều điểm sau GC ở tải tương đương. Nếu baseline tăng dai dẳng, lấy histogram/heap dump có phê duyệt và phân tích dominator/path-to-roots.

**Bước 5 — Tìm retaining owner và tính hợp lệ.** Cache có bounds/TTL không, listener có unregister không, queue có backpressure không, session có expire không, ThreadLocal có cleanup không, class loader có dọn đúng lifecycle không?

**Bước 6 — Sửa đúng nơi.** Sửa cache/queue/lifecycle nếu leak, giảm temporary allocations nếu GC pressure. **Không mặc định tăng `-Xmx`** — có thể chỉ trì hoãn OOM.

**Bước 7 — Đo lại cùng tải.** So allocation rate, after-GC heap, GC pause, retained size và response latency. Không dùng một lần gọi `System.gc()` như một phép kiểm tra chắc chắn; nó không cam kết GC xảy ra tức thì hoặc trả bộ nhớ vật lý về OS.

## 15. Rủi ro và lưu ý vận hành

- **JFR `profile`:** có overhead cao hơn `default` tùy workload, dùng time box.
- **Histogram/heap dump:** tác động cao khi heap lớn; lập kế hoạch trước khi chạy production.
- **Path-to-GC-roots:** có thể gây pause tương tự tác vụ GC nặng, chỉ dùng khi thật sự cần.
- **HPROF:** chứa raw memory, có thể có token, passwords, PII; chỉ chia sẻ cho người có thẩm quyền.
- **RecordingFile.readAllEvents:** không nên dùng cho file quá lớn; ưu tiên `hasMoreEvents`/`readEvent` theo luồng.
- **JFR sampling:** không có sample không chứng minh không có leak.
- **Native memory:** công cụ heap không đo đủ direct buffers, native libraries, thread stacks; dùng công cụ phù hợp. NMT chỉ có ý nghĩa khi được bật phù hợp.
- **Cấu trúc dữ liệu:** object pooling/cache có thể giữ refs lâu và làm retained heap tăng; phải có giới hạn.
- **GC và JIT:** các kết quả về số bytes thực tế phụ thuộc implementation; phân biệt stdout cố định của vòng lặp với profiler counters không cố định.
- **Dữ liệu production:** áp kiểm soát truy cập, mã hóa lưu trữ, retention và quy trình xóa diagnostics.

## 16. Những sai lầm thường gặp

1. **“Đã allocate 2 GB tức là heap còn giữ 2 GB.”** Sai: dữ liệu tạm có thể đã bị GC.
2. **“Allocation rate cao = leak.”** Sai: cần live heap/GC roots.
3. **“Allocation rate thấp = không leak.”** Sai: một cache tăng chậm có thể leak.
4. **“Heap used tăng một lần = leak.”** Sai: có thể trước GC hoặc warmup.
5. **“Heap committed/RSS không giảm thì GC thất bại.”** Sai: committed và RSS không là live set.
6. **“Old gen cao tức là leak.”** Sai: có objects sống lâu hợp lệ.
7. **“byte[].length bằng heap size chính xác.”** Sai: còn header/alignment.
8. **“Retained size là tổng tất cả references trong collection.”** Sai nếu objects còn đường tới root khác.
9. **“TLAB event được ghi cho mọi new object.”** Sai: chỉ sampling/points liên quan TLAB.
10. **“Cộng allocationSize từ JFR là tổng bytes toàn app.”** Sai: samples không phải census.
11. **“Không có OldObjectSample tức là không leak.”** Sai: sampling có thể bỏ sót.
12. **“ThreadMXBean cho retained heap.”** Sai: chỉ allocated counter.
13. **“GC.class_histogram cho root path.”** Sai: cần heap dump/object graph.
14. **“Memory dump không làm ảnh hưởng performance.”** Sai: có thể stop-the-world/full GC.
15. **“Heap dump an toàn để gửi cho mọi người.”** Sai: thường chứa dữ liệu mật.
16. **“jdk.ObjectAllocationSample là Java 11 event.”** Sai: event xuất hiện ở JDK mới hơn.
17. **“Tăng -Xmx sửa memory leak.”** Có thể chỉ trì hoãn.
18. **“Tối ưu allocation bằng pooling mọi object.”** Pooling có thể tăng retention và complexity.
19. **“Một snapshot đủ chứng minh leak.”** Sai: cần time series và workload tương đương.
20. **“Một Object Allocation sample chỉ ra ai giữ object.”** Sai: cần GC-root paths và retained-size analysis.

## 17. Bài tập thực hành

### Bài 1 — Công thức
Một app cấp phát 1.200 MB trong 20 giây. Tính allocation rate. Nếu after-GC live heap chỉ tăng 2 MB, đã đủ kết luận leak chưa?

### Bài 2 — Temporary vs retained
Chạy `AllocationRetentionDemo.java`. Vì sao tổng payload là 16.449.536 byte nhưng cache giữ 65.536 byte? Kích thước retained heap theo MAT sẽ có thể khác vì sao?

### Bài 3 — Live và cleared
Chạy demo với `--pause` và lấy histogram trước/sau `CACHE.clear()` bằng `jcmd`. Vì sao số `byte[]` tổng thể có thể không giảm đúng 8? Nếu cần xác nhận reference owner thì dùng công cụ gì?

### Bài 4 — Thread counter
Chạy `ThreadAllocationCounterDemo.java`. So giá trị logical payload với counter và giải thích header/alignment. Vì sao counter không giảm sau GC?

### Bài 5 — JFR TLAB
Chạy `JfrAllocationProbeDemo.java`. So 15.000 allocations với số events đọc được; tại sao không được lấy tổng `allocationSize` làm total allocated bytes?

### Bài 6 — Leak hay GC pressure?
JFR cho thấy string builders tạo rất nhiều objects tạm nhưng after-GC ổn định suốt một giờ. Bạn ưu tiên tối ưu điểm nào, và cần theo dõi CPU/GC gì?

### Bài 7 — Retained cache
Một `ConcurrentHashMap` có shallow nhỏ nhưng retained 1,2 GB, keys tăng không giới hạn. Đề xuất kiểm tra paths to roots, eviction/TTL và đo lại sau khi sửa.

### Bài 8 — RSS tăng
RSS container tăng nhưng heap sau GC ổn định. Nêu các thành phần native/off-heap cần điều tra và lý do không nên tăng `-Xmx` mặc định.

### Bài 9 — Diagnostic safety
Viết quy trình thu HPROF ở production với quyền truy cập, kế hoạch pause, disk budget, mã hóa, thời gian lưu và xóa dữ liệu.

### Checklist hoàn thành

- [ ] Phân biệt allocation history, allocation rate và live/retained heap.
- [ ] Hiểu shallow size, retained size, dominator và GC-root paths.
- [ ] Không coi sampled JFR TLAB events là toàn bộ allocations.
- [ ] Biết `jdk.ObjectAllocationSample` không là event của Java 11.
- [ ] Dùng ThreadMXBean đúng vai trò allocated bytes.
- [ ] Đọc after-GC baseline theo tải tương đương.
- [ ] Phân biệt allocation hotspot với retaining owner.
- [ ] Chạy 3 ví dụ Java 11 và hiểu stdout cố định/nondeterministic.
- [ ] Biết dùng JFR, jcmd, MAT và GC logs cho đúng câu hỏi.
- [ ] Không lấy/gửi heap dumps thiếu kiểm soát.

## 18. Tài liệu tham khảo chính thức và vẫn áp dụng

1. [Oracle Java 11 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshoot-performance-issues-using-jfr.html): JFR, TLAB allocation pressure và GC.
2. [Oracle Java 11 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshooting-memory-leaks.html): long-lived objects, JMC, OldObjectSample và paths to GC roots.
3. [Oracle Java 11 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html): `jcmd`, heap dump, class histogram, JFR.
4. [Oracle Java 11 — jcmd](https://docs.oracle.com/en/java/javase/11/tools/jcmd.html): commands và impact.
5. [Java SE 11 — com.sun.management.ThreadMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): đo allocated bytes theo thread.
6. [Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): cấu hình và dump JFR từ Java.
7. [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc recording theo luồng.
8. [OpenJDK 11 JFR Event Catalog](https://sap.github.io/jfrevents/11.html): event names và metadata.
9. [Eclipse MAT — Finding Memory Leak](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html): Dominator Tree/Leak Suspects/GC roots.
10. [Eclipse MAT — Configuration](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/configure_mat.html): tài nguyên khi phân tích HPROF lớn.
11. [Java SE 11 — java và -Xlog](https://docs.oracle.com/en/java/javase/11/tools/java.html): GC unified logging.
12. [Java SE 25 — jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): công cụ vẫn được hỗ trợ trên JDK hiện đại.

**Tóm tắt:** allocation profiling trả lời “code tạo bao nhiêu objects và ở đâu?”, còn retention analysis trả lời “ai giữ objects không cho GC thu hồi?”. Dùng **JFR/ThreadMXBean** cho allocation rate và **GC time series/heap dump/MAT** cho live heap, retained size và paths to GC roots. Cả hai cần dữ liệu theo thời gian và workload phù hợp; không kết luận leak chỉ từ một con số.