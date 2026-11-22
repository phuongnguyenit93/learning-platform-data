# Java 11 — Thiết kế thí nghiệm giảm allocation có số đo

**Chủ đề:** Java 11 → **Heap profiling**. Bài này hướng dẫn xây dựng một thí nghiệm tối ưu có thể tái lập, trong đó **mức cấp phát heap** được đo bằng byte trên mỗi đơn vị nghiệp vụ, không chỉ dựa vào ấn tượng “code ít đối tượng hơn”. Từ giả thuyết, lựa chọn baseline/candidate, kiểm đúng kết quả, warm-up JIT, nhiều lần đo, đọc JFR, đến đánh giá throughput/GC/p95/p99, bạn sẽ biết khi nào một tối ưu thực sự có giá trị.

**Phạm vi Java 11 và Special Note:** Chỉ dùng kiến thức và công cụ **vẫn áp dụng hiện nay**, không chọn hướng dẫn legacy/lỗi thời. Ví dụ chạy được bằng `javac --release 11`; phép đo per-thread sử dụng `com.sun.management.ThreadMXBean` trong `jdk.management`, còn profiling cấp phát sử dụng `jdk.jfr`. Các số byte/thời gian trong ví dụ là **dữ liệu đo thực sự trên JDK thử nghiệm**, không phải định luật của mọi JVM.

**Mục tiêu:**
1. Phân biệt **allocated bytes**, allocation rate, retained/live heap, GC pressure và CPU time.
2. Đặt giả thuyết và tiêu chí chấp nhận trước khi sửa code.
3. Tính `B/item`, `B/batch`, phần trăm giảm và mức sai số.
4. Chạy thí nghiệm `List<Long>` so với `long[]` có cùng kết quả nghiệp vụ.
5. Phân tích JFR allocation events mà không nhầm chúng là tổng số object tạo ra.
6. Hiểu warm-up, escape analysis, JIT, GC, JMH, thread boundaries và các guardrail sản phẩm.
7. Báo cáo cả lợi ích và đánh đổi, đề xuất canary/rollback sau thử nghiệm.

## 1. Allocation không phải là mức RAM đang giữ

Khi Java tạo object, JVM có thể cấp phát trên heap; nhưng HotSpot JIT có thể loại bỏ một số allocation qua **escape analysis/scalar replacement**. Hai cách nhìn khác nhau:

- **Allocation:** số byte được JVM cấp phát trong một khoảng, kể cả object đã chết rất nhanh.
- **Retention:** các object còn sống vì vẫn có references; đây là lượng chiếm heap về lâu dài.
- **Heap used/committed:** snapshot của heap ở thời điểm quan sát.
- **GC count/pause:** hoạt động thu hồi và chi phí của collector; không phải phép đếm tất cả object.
- **RSS/native memory:** bộ nhớ process ngoài/bao gồm heap, class metadata, JIT, thread stacks, direct buffers.

| Thông số | Đơn vị | Trả lời câu hỏi |
| --- | --- | --- |
| Allocated bytes | Byte trong khoảng | Batch/request này tạo bao nhiêu dữ liệu heap mới? |
| B/item | Byte trên một phần tử | Một đơn vị nghiệp vụ có allocation cost bao nhiêu? |
| B/request | Byte trên request | Mỗi request tạo bao nhiêu byte? |
| Allocation rate | MB/s hoặc B/s | Chương trình tạo heap objects nhanh cỡ nào? |
| Live/retained heap | MB tại thời điểm | Object nào bị giữ, có thể gây leak? |
| GC pause | ms, count, % thời gian | Collection ảnh hưởng latency/throughput thế nào? |
| Throughput | item/s, request/s | Có cải thiện tốc độ xử lý không? |
| p95/p99 latency | ms | Tail latency của nghiệp vụ có xấu đi không? |

**Sai lầm phổ biến:** đo `Runtime.totalMemory() - Runtime.freeMemory()` trước/sau rồi gọi chênh lệch là số bytes đã allocated. Hai snapshot này chịu ảnh hưởng mạnh của GC và object retention; nhiều objects chết nhanh có thể không còn tại snapshot dù đã tạo rất nhiều.

Một API có thể cấp phát 200 MB/s nhưng live heap chỉ 100 MB vì object sống ngắn. Giảm allocation thường giúp giảm pressure lên GC; không có nghĩa live heap tự giảm cùng tỷ lệ.

## 2. Tình huống nghiên cứu: boxing `Long` so với `long[]`

Giả sử service xử lý các giá trị số của một batch, lưu tạm chúng rồi cộng thành checksum. Baseline:

~~~java
static long boxedBatch(int count) {
    List<Long> values = new ArrayList<>(count);
    for (int i = 0; i < count; i++) {
        values.add((1024L + i) * 31L + i % 13);
    }
    long sum = 0;
    for (Long value : values) {
        sum += value;
    }
    return sum;
}
~~~

Candidate:

~~~java
static long primitiveBatch(int count) {
    long[] values = new long[count];
    for (int i = 0; i < count; i++) {
        values[i] = (1024L + i) * 31L + i % 13;
    }
    long sum = 0;
    for (long value : values) {
        sum += value;
    }
    return sum;
}
~~~

**Hai đoạn code trên là method snippets**, chương trình biên dịch độc lập có ở mục 6.

**Vì sao đáng thử?** `List<Long>` chứa references đến những `Long` wrappers được tạo qua boxing; `long[]` chứa số nguyên thủy liên tục, không cần wrapper riêng cho mỗi giá trị. Các giá trị tính ra lớn hơn phạm vi cache số nguyên nhỏ của `Long.valueOf` nên thử nghiệm không vô tình được hưởng lợi từ `Long` cache mặc định.

**Vì sao chưa chắc nên thay trong production?** `List<Long>` có thể nhận `null`, hỗ trợ API collection, interface abstraction và một số hành vi khác. `long[]` kích thước cố định, không chứa null và không truyền được trực tiếp vào API yêu cầu `List<Long>`. Chỉ đổi khi hợp đồng nghiệp vụ cho phép và đã kiểm mọi consumer/serializer/concurrency. Tối ưu code nhưng đổi ý nghĩa dữ liệu là thất bại.

## 3. Giả thuyết và tiêu chí chấp nhận (pre-register)

**Câu hỏi chính:** với cùng batch input, cùng JDK/JVM settings và cùng checksum, chuyển `List<Long>` sang `long[]` có giảm allocated bytes trên một item không?

**Giả thuyết H0:** không có cải thiện B/item có ý nghĩa thực tiễn trong workload đã chọn, hoặc có trade-off khiến phương án mới không phù hợp.

**Giả thuyết H1:** phương án primitive giảm B/item một mức đáng kể, bảo toàn output và không làm throughput/p99/GC/heap retention tệ hơn ngoài giới hạn chấp nhận.

Ghi lại trước khi nhìn số đo:

| Hạng mục | Kế hoạch |
| --- | --- |
| Independent variable | Representation `List<Long>` hoặc `long[]`, không đổi công thức. |
| Primary metric | `allocated heap bytes / item`. |
| Correctness guardrail | Checksum A bằng B; thêm edge-case tests ở production. |
| Secondary metric | Throughput, latency, GC count/pause, heap RSS/retention. |
| Input | Ví dụ 100.000 items/sample, có kiểm 0/1/nhỏ/lớn về sau. |
| Warm-up | Hai biến thể đều warm up trước khi đo. |
| Trials | 9 samples mỗi biến thể cho pilot, đảo thứ tự A/B. |
| Decision gate (ví dụ) | B/item giảm ≥20%; throughput không giảm >5%; p99 và error rate không xấu đi đáng kể. |
| Environment | Cùng JDK/flags/CPU limit/heap/GC/dataset và cách gọi. |

Những **ngưỡng 20%, 5% chỉ là ví dụ về quy tắc ra quyết định**; dự án thực phải định nghĩa theo chi phí, SLO và risk budget. Đừng đặt ngưỡng *sau* khi thấy kết quả.

## 4. Loại bỏ biến nhiễu trước khi đo

JVM/JIT và hệ thống điều hành có nhiều nguồn nhiễu:

1. **JIT compilation/warm-up:** cùng code nhưng bytecode interpreted, C1 và C2 có thể khác thời gian và allocation.
2. **Escape analysis:** HotSpot có thể biến object thành scalar values, triệt tiêu allocation mà source vẫn có `new`.
3. **Class loading/caches:** lượt đầu có initialization và classloader alloc không lặp ở lượt sau.
4. **Thread scheduling/CPU throttling:** nếu CPU bị giới hạn trong container hoặc có workload nền, ns/op dao động.
5. **GC:** heap sizing, generation state, collector và allocation pressure tác động pause/throughput.
6. **Order bias:** nếu luôn chạy baseline trước candidate, candidate có thể được hưởng cache/JIT nóng hơn.
7. **Input distribution:** giá trị trong cache wrapper, payload dễ tính hoặc toàn happy path có thể không đại diện production.
8. **Dead-code elimination:** nếu kết quả không được sử dụng, JIT có thể xóa cả một phép tính.
9. **Instrumentation overhead:** JFR, logging và allocation counters có overhead riêng.
10. **Multi-threading:** nếu công việc chạy ở thread pool, phép đo của HTTP thread có thể bỏ sót allocated bytes ở worker threads.

**Kế hoạch:** dùng cùng dữ liệu, warm-up, lặp samples, đảo thứ tự, đo batch lớn, giữ kết quả quan sát được, sau đó kiểm JMH và tích hợp dưới tải thật. Thí nghiệm local không thay thế production-like load test.

## 5. Công cụ đo `com.sun.management.ThreadMXBean`

Java 11 có extension `com.sun.management.ThreadMXBean` trong module `jdk.management`. Một phép đo tổng byte heap cấp phát cho current platform thread:

~~~java
long threadId = Thread.currentThread().getId();
long before = meter.getThreadAllocatedBytes(threadId);
long checksum = workload();
long after = meter.getThreadAllocatedBytes(threadId);
long allocatedBytes = after - before;
~~~

Đây là **snippet minh họa**, `meter` đã được kiểm hỗ trợ và enabled. `getThreadAllocatedBytes` là **ước lượng tổng bytes đã allocated theo thread**; có thể có độ trễ cập nhật do cách JVM quản lý allocations. Delta không đồng nghĩa lượng object còn sống.

### 5.1. Kiểm capability, không mặc định trả 0

~~~java
java.lang.management.ThreadMXBean platform =
    ManagementFactory.getThreadMXBean();
if (!(platform instanceof com.sun.management.ThreadMXBean)) {
    // Báo UNSUPPORTED, không coi allocated bytes bằng 0.
}
com.sun.management.ThreadMXBean meter =
    (com.sun.management.ThreadMXBean) platform;
if (!meter.isThreadAllocatedMemorySupported()) {
    // Báo UNSUPPORTED.
}
if (!meter.isThreadAllocatedMemoryEnabled()) {
    meter.setThreadAllocatedMemoryEnabled(true);
}
~~~

**Đoạn minh họa:** cần imports và nhánh điều khiển hoàn chỉnh nếu dùng trong code. API này không phải Java SE thuần trên mọi JVM; một custom runtime image có thể thiếu `jdk.management`. Bật capability có thể bị từ chối bởi security policy. Nếu `getThreadAllocatedBytes(id)` trả `-1` do unsupported/disabled/dead thread, phải báo metric **NA/UNSUPPORTED**, không đem số âm vào B/item.

Để bảo đảm source chạy trên Java 11, dùng `Thread.currentThread().getId()` thay vì API `Thread.threadId()` xuất hiện sau này. `getCurrentThreadAllocatedBytes()` là convenience API chỉ được thêm ở một số bản cập nhật Java 11, do đó code dùng `getThreadAllocatedBytes(id)` để có phạm vi tương thích rộng hơn.

### 5.2. Phạm vi của counter

- **Chỉ thread được đo**, không tự tổng hợp tất cả thread pool workers.
- **Byte heap allocated**, không phải memory used, RSS hay live heap.
- Chi phí gọi counter có thể ảnh hưởng benchmark quá nhỏ; đo một batch đủ lớn.
- Counter có thể xấp xỉ và JVM/provider có thể khác nhau.
- Không dựa vào per-thread counter cho virtual-thread semantics ở các JDK mới mà không xem Javadoc của runtime đích.
- Nếu process có các nguồn allocation từ background system threads, per-thread số đo ở main không chứa chúng; đo cả process hoặc profiler khi cần.

## 6. Chương trình Java 11 hoàn chỉnh: hai biến thể, warm-up và median

**Tệp `AllocationExperiment.java`.** Chương trình này không cần Maven/JMH; cần JDK có `jdk.management`. Nó có kiểm checksum, sáu vòng warm-up, 9 samples mỗi biến thể, thứ tự xen kẽ và đo bytes/elapsed time cho mỗi batch 100.000 item.

~~~java
import com.sun.management.ThreadMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public final class AllocationExperiment {
    private static final int OPERATIONS = 100_000;
    private static final int WARMUPS = 6;
    private static final int SAMPLES = 9;
    private static volatile long observed;

    private AllocationExperiment() {}

    static long boxedBatch(int count) {
        List<Long> values = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            values.add((1024L + i) * 31L + i % 13);
        }
        long sum = 0;
        for (Long value : values) {
            sum += value;
        }
        return sum;
    }

    static long primitiveBatch(int count) {
        long[] values = new long[count];
        for (int i = 0; i < count; i++) {
            values[i] = (1024L + i) * 31L + i % 13;
        }
        long sum = 0;
        for (long value : values) {
            sum += value;
        }
        return sum;
    }

    static long median(long[] values) {
        long[] sorted = values.clone();
        Arrays.sort(sorted);
        return sorted[sorted.length / 2];
    }

    static long[] sample(ThreadMXBean bean, long threadId,
                         boolean primitive, int operations) {
        long before = bean.getThreadAllocatedBytes(threadId);
        long start = System.nanoTime();
        long checksum = primitive
            ? primitiveBatch(operations) : boxedBatch(operations);
        long elapsed = System.nanoTime() - start;
        long after = bean.getThreadAllocatedBytes(threadId);
        if (before < 0 || after < before) {
            throw new IllegalStateException("Allocation meter unavailable");
        }
        observed = checksum;
        return new long[] { after - before, elapsed, checksum };
    }

    public static void main(String[] args) {
        java.lang.management.ThreadMXBean platform =
            ManagementFactory.getThreadMXBean();
        if (!(platform instanceof ThreadMXBean)) {
            System.out.println("status=UNSUPPORTED_THREAD_ALLOCATION_METER");
            return;
        }
        ThreadMXBean meter = (ThreadMXBean) platform;
        if (!meter.isThreadAllocatedMemorySupported()) {
            System.out.println("status=UNSUPPORTED_THREAD_ALLOCATION_METER");
            return;
        }
        if (!meter.isThreadAllocatedMemoryEnabled()) {
            meter.setThreadAllocatedMemoryEnabled(true);
        }
        long threadId = Thread.currentThread().getId();
        long expected = boxedBatch(OPERATIONS);
        if (expected != primitiveBatch(OPERATIONS)) {
            throw new AssertionError("Non-equivalent business result");
        }
        for (int i = 0; i < WARMUPS; i++) {
            observed = boxedBatch(OPERATIONS);
            observed = primitiveBatch(OPERATIONS);
        }

        long[] baseBytes = new long[SAMPLES];
        long[] baseNanos = new long[SAMPLES];
        long[] optBytes = new long[SAMPLES];
        long[] optNanos = new long[SAMPLES];
        for (int i = 0; i < SAMPLES; i++) {
            // Alternate order to reduce drift/order bias.
            boolean optFirst = (i & 1) == 1;
            long[] first = sample(meter, threadId, optFirst, OPERATIONS);
            long[] second = sample(meter, threadId, !optFirst, OPERATIONS);
            if (first[2] != expected || second[2] != expected) {
                throw new AssertionError("Checksum changed between variants");
            }
            long[] base = optFirst ? second : first;
            long[] opt = optFirst ? first : second;
            baseBytes[i] = base[0];
            baseNanos[i] = base[1];
            optBytes[i] = opt[0];
            optNanos[i] = opt[1];
        }
        double baseAlloc = (double) median(baseBytes) / OPERATIONS;
        double optAlloc = (double) median(optBytes) / OPERATIONS;
        double baseTime = (double) median(baseNanos) / OPERATIONS;
        double optTime = (double) median(optNanos) / OPERATIONS;
        double reduction = 100.0 * (baseAlloc - optAlloc) / baseAlloc;

        System.out.println("business.checksum.equal=true");
        System.out.println("operations.per.sample=" + OPERATIONS);
        System.out.println("samples.per.variant=" + SAMPLES);
        System.out.printf(Locale.ROOT,
            "boxed.bytes.per.item.median=%.1f%n", baseAlloc);
        System.out.printf(Locale.ROOT,
            "primitive.bytes.per.item.median=%.1f%n", optAlloc);
        System.out.printf(Locale.ROOT,
            "allocation.change.percent=%.1f%n", reduction);
        System.out.printf(Locale.ROOT,
            "boxed.ns.per.item.median=%.1f%n", baseTime);
        System.out.printf(Locale.ROOT,
            "primitive.ns.per.item.median=%.1f%n", optTime);
        System.out.println("metric=per-thread-allocated-heap-bytes");
    }
}
~~~

Lệnh:

~~~bash
javac --release 11 -encoding UTF-8 AllocationExperiment.java
java AllocationExperiment
~~~

**Stdout thực tế từ một lần chạy trên JDK 24:**

~~~text
business.checksum.equal=true
operations.per.sample=100000
samples.per.variant=9
boxed.bytes.per.item.median=28.0
primitive.bytes.per.item.median=8.0
allocation.change.percent=71.4
boxed.ns.per.item.median=6.3
primitive.ns.per.item.median=3.1
metric=per-thread-allocated-heap-bytes
~~~

**Đây là số đo động, KHÔNG phải output cố định mọi lần.** Trong hai lần chạy bổ sung trên cùng JDK thử, `B/item` vẫn là 28.0 và 8.0 nhưng `ns/item` dao động (ví dụ baseline 6.0 rồi 6.8; candidate 3.1 rồi 2.0). Nếu một JVM không hỗ trợ capability, output chỉ có dòng `status=UNSUPPORTED_THREAD_ALLOCATION_METER`, không được diễn giải là zero allocation.

**QA đã thực hiện:** File trên thực sự biên dịch bằng `javac --release 11` và chạy trong JDK24. Chưa chạy trên JVM 11 thực tế; cần bổ sung CI runtime Java 11 nếu sản phẩm vận hành ở đúng JVM đó.

### 6.1. Hiểu kết quả đúng cách

| Metric | Baseline | Candidate | Diễn giải trên JVM thử nghiệm |
| --- | ---: | ---: | --- |
| Allocated bytes/item (median) | **28.0** | **8.0** | Giảm 20 byte cho mỗi item trong code path thử. |
| Reduction | — | **71.4%** | `(28−8)/28×100`. |
| Time ns/item (median một lần) | 6.3 | 3.1 | Tạm tham khảo, không chứng minh latency production. |
| Checksum | Bằng nhau | Bằng nhau | Hai variants làm đúng phép tính của ví dụ. |
| Samples | 9 | 9 | Cùng JVM process, chưa phải independent forks. |

Đừng suy đoán “một `Long` luôn tốn chính xác 20 byte” trên mọi JVM; object header, alignment, compressed OOPs, escape analysis, JIT và TLAB có thể làm kết quả khác. Candidate vẫn cấp phát `long[]` (8 byte phần tử cộng array header/padding theo JVM). Đây là ví dụ cải thiện **đúng đơn vị đo**, không phải lời hứa tỷ lệ giảm cố định.

### 6.2. Tại sao median và nhiều samples?

Median giảm ảnh hưởng một vài samples nhiễu so với mean, nhưng 9 samples **trong cùng một JVM không phải 9 forks độc lập**. Để kết luận production:
- Chạy nhiều independent JVM process/forks, mỗi fork warm-up tương tự.
- Thay đổi lịch A-B/B-A, hoặc randomization có seed.
- Lưu raw bytes và nanos của từng sample/fork, không chỉ median.
- Báo median, phân bố và confidence interval nếu dữ liệu đủ, tính đến dependence giữa samples.
- Lặp trên nhiều batch sizes, JVM vendor/flags và workload production-like.
- Giữ correctness và guardrails xuyên các trials.

## 7. Tránh “zero allocation” giả vì JIT

Một đoạn code được viết có `new` nhưng không dùng kết quả:

~~~java
static void misleading(int count) {
    for (int i = 0; i < count; i++) {
        new Object();
    }
}
~~~

Đây là **ví dụ sai có chủ đích**: HotSpot JIT có thể xóa toàn bộ vòng tạo object vì không có tác động quan sát, làm benchmark báo gần 0 B/op. Không thể từ đó suy ra code production tạo object thật cũng không tốn allocation.

Trong demo, checksum được trả về và lưu `volatile observed`, giảm rủi ro dead-code elimination. Nhưng vẫn phải dùng harness tốt và hiểu JIT có thể scalar-replace object tạm. **Đừng tắt mọi tối ưu JVM trong benchmark để ép ra số byte “đúng với source”** nếu production chạy với tối ưu đó.

### 7.1. Input quá dễ sẽ che boxing

`Long.valueOf` có cache cho các số nhỏ thông dụng, nên nếu baseline chỉ add những giá trị trong cache, số `Long` wrappers mới có thể ít hơn kỳ vọng. Ví dụ deliberately tạo giá trị `(1024 + i)*31 + i%13` lớn hơn cache. Dù vậy, production data distribution có thể khác; test cả các vùng số thường gặp để quyết định có nên đổi representation.

## 8. JFR allocation events: tìm hotspot, không đếm mọi object

Java 11 JFR có các event điển hình:

- `jdk.ObjectAllocationInNewTLAB` — ghi nhận allocation khi liên quan đến việc lấy một Thread Local Allocation Buffer mới. Có thể có class/stack để phân tích.
- `jdk.ObjectAllocationOutsideTLAB` — ghi nhận đường allocation ngoài TLAB.
- `jdk.GarbageCollection` và các JFR GC events — giúp thấy collection activity, nhưng không tự chứng minh nguồn allocation.

**Rất quan trọng:** Hai JFR allocation events này **không được phát cho từng object**; chúng gắn với các đường allocation đặc biệt và sampling/slow path. **Số event quan sát ≠ số object được tạo.** Cũng không cộng `allocationSize` hay `tlabSize` như một thước đo chính xác tất cả bytes cấp phát.

`tlabSize` là kích thước vùng buffer TLAB, không phải kích thước object. Một số JDK mới hơn hỗ trợ `jdk.ObjectAllocationSample`; **không đưa event đó làm giả định có sẵn trên Java 11**.

| Công cụ | Nên dùng cho |
| --- | --- |
| `ThreadMXBean.getThreadAllocatedBytes` | B/item tương đối chính xác theo thread khi được hỗ trợ. |
| JFR allocation events | Class/stack allocation hotspots, xác định nơi cần sửa. |
| JFR GC events | GC counts/pauses/bối cảnh collector. |
| Heap dump / dominator tree | Retained heap/GC roots/leaks, không phải tổng ephemeral allocations. |
| JMH `-prof gc` | `gc.alloc.rate.norm` trong harness và điều kiện JMH. |
| Load test với telemetry | Thông lượng, p95/p99, errors, CPU/RSS/GC trong hệ thống. |

## 9. Chương trình Java 11 thứ hai: JFR allocation probe

**Tệp `AllocationJfrProbe.java`.** Ví dụ bật hai event types Java11, chạy allocation-heavy workload, dump một file `.jfr` tạm và đọc lại để đếm **số events quan sát**, không assert đó là số object. Không cần dependency ngoài JDK.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class AllocationJfrProbe {
    private static volatile long sink;
    private AllocationJfrProbe() {}

    static long workload(int n) {
        List<Long> values = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            values.add((1024L + i) * 31L + i % 13);
        }
        long sum = 0;
        for (Long v : values) {
            sum += v;
        }
        return sum;
    }

    public static void main(String[] args) throws Exception {
        final String inTlab = "jdk.ObjectAllocationInNewTLAB";
        final String outsideTlab = "jdk.ObjectAllocationOutsideTLAB";
        boolean in = FlightRecorder.getFlightRecorder().getEventTypes()
            .stream().anyMatch(t -> inTlab.equals(t.getName()));
        boolean out = FlightRecorder.getFlightRecorder().getEventTypes()
            .stream().anyMatch(t -> outsideTlab.equals(t.getName()));
        if (!in || !out) {
            System.out.println("allocation.event.types.available=false");
            return;
        }

        Path file = Files.createTempFile("jfr-alloc-probe-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(inTlab).withStackTrace();
                recording.enable(outsideTlab).withStackTrace();
                recording.start();
                long check = 0;
                for (int k = 0; k < 12; k++) {
                    check ^= workload(100_000);
                }
                sink = check;
                recording.stop();
                recording.dump(file);
            }
            int events = 0;
            int inCount = 0;
            int outsideCount = 0;
            for (RecordedEvent e : RecordingFile.readAllEvents(file)) {
                String name = e.getEventType().getName();
                if (inTlab.equals(name)) {
                    inCount++;
                    events++;
                } else if (outsideTlab.equals(name)) {
                    outsideCount++;
                    events++;
                }
            }
            System.out.println("allocation.event.types.available=true");
            System.out.println("jfr.recording.readable=true");
            System.out.println("jdk.allocation.events.observed=" + events);
            System.out.println("jdk.in.new.tlab.events=" + inCount);
            System.out.println("jdk.outside.tlab.events=" + outsideCount);
            System.out.println("jfr.event.count.is.exact.allocations=false");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 11 -encoding UTF-8 AllocationJfrProbe.java
java AllocationJfrProbe
~~~

**Một stdout thực tế đã ghi nhận trong lượt thử trên JDK24:**

~~~text
allocation.event.types.available=true
jfr.recording.readable=true
jdk.allocation.events.observed=21
jdk.in.new.tlab.events=17
jdk.outside.tlab.events=4
jfr.event.count.is.exact.allocations=false
~~~

**21, 17, 4 là số động theo JVM, heap, TLAB, JIT và recording settings**, không phải expected values cố định. Chương trình chỉ xác nhận file đọc được và đếm sample events. Nếu runtime không có hai event types, in `allocation.event.types.available=false`. Chương trình đã thực sự biên dịch `--release 11` và chạy thành công trên JDK24 trong thử nghiệm.

### 9.1. Cách nhìn file JFR

Nếu giữ lại một file (thay vì xóa ngay như demo), có thể dùng:

~~~bash
jfr summary alloc-before.jfr
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB alloc-before.jfr
~~~

Đây là **lệnh minh họa**, cần file đã tồn tại. Dùng JDK Mission Control để nhóm events theo class và stack trace. Chú ý thời lượng recording, filter/sample, overhead và không công khai file production có stack/class name hoặc dữ liệu nội bộ.

## 10. JMH: thí nghiệm microbenchmark có forks/warm-up

Pilot `ThreadMXBean` rất tốt để học cách đo B/item, nhưng một quyết định performance ảnh hưởng production cần **JMH** (Java Microbenchmark Harness) hoặc harness tương đương. JMH hỗ trợ JVM forks, warm-up, benchmark modes, consumption of results, report formats và profiler như `-prof gc`.

**Ví dụ benchmark class minh họa** cho project JMH có `jmh-core` và annotation processor phù hợp; không tự biên dịch chỉ bằng JDK11 vì nó cần thư viện JMH ngoài:

~~~java
package bench;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 7)
@Fork(3)
public class BatchAllocationJmh {
    @Param({"1000", "10000"})
    public int items;

    @Benchmark
    public long boxedBatch() {
        List<Long> list = new ArrayList<>(items);
        for (int i = 0; i < items; i++) {
            list.add((1024L + i) * 31L + i % 13);
        }
        long sum = 0;
        for (Long x : list) {
            sum += x;
        }
        return sum;
    }

    @Benchmark
    public long primitiveBatch() {
        long[] values = new long[items];
        for (int i = 0; i < items; i++) {
            values[i] = (1024L + i) * 31L + i % 13;
        }
        long sum = 0;
        for (long x : values) {
            sum += x;
        }
        return sum;
    }
}
~~~

Dùng official JMH archetype/build template (ví dụ tọa độ `org.openjdk.jmh:jmh-core`, JMH 1.37 nếu chọn bản đã được kiểm tương thích), cài dependency/annotation processor và đóng gói `benchmarks.jar`. Sau khi có JAR:

~~~bash
java -jar target/benchmarks.jar BatchAllocationJmh \
  -f 3 -wi 5 -i 7 -prof gc -rf json -rff results.json
~~~

**Lệnh JMH là minh họa**, chỉ chạy được khi dự án đã dựng đúng. `BatchAllocationJmh` chưa được thực thi riêng trong lượt QA này; **hai chương trình Java11 độc lập ở mục 6 và 9 đã chạy thật**.

### 10.1. B/batch khác B/item trong JMH

Với code trên, mỗi lần `@Benchmark` gọi method xử lý `items` phần tử. JMH có thể báo:
- Throughput **batch/s** nếu benchmark mode là Throughput.
- `gc.alloc.rate.norm` thường là **B/invocation**, tức **B/batch**, không tự là B/item.

Do đó:

~~~text
B/item  = gc.alloc.rate.norm / items
items/s = batches/s × items
~~~

Phải ghi rõ denominator, không báo `gc.alloc.rate.norm=280000 B/op` như thể `280000 B/item`. Nếu có nhiều `@Param` sizes, chuẩn hóa từng size riêng.

### 10.2. Vì sao không lấy ns/item của pilot làm KPI cuối?

`AllocationExperiment` chỉ chạy một JVM và dùng `System.nanoTime` trong method đo batch. Nó không có nhiều process forks, có thể chịu drift, JIT và noisy neighbors. Dòng `boxed.ns.per.item.median=6.3` và `primitive.ns.per.item.median=3.1` trong một lần chạy không phải bằng chứng service production “nhanh gấp đôi”.

Dùng **JMH cho microbenchmark**, rồi **load test tích hợp** trên endpoint thật với concurrency, database, network và GC phù hợp; cân bằng throughput/p99/error rates. Không biến JMH numbers thành quảng cáo hiệu năng nếu chưa xác minh workload thật.

## 11. Công thức tính allocation và cách diễn giải

\[
\mathrm{B/item} = \frac{\mathrm{allocatedBytes}_{after}-\mathrm{allocatedBytes}_{before}}{N}
\]

\[
\mathrm{reduction}(\%) = 100\times \frac{\mathrm{B/item}_{base}-\mathrm{B/item}_{candidate}}{\mathrm{B/item}_{base}}
\]

\[
\mathrm{allocationRate}(\mathrm{B/s}) = \mathrm{B/item}\times\mathrm{items/s}
\]

Với một lần chạy demo:

~~~text
Baseline:          28.0 B/item
Candidate:          8.0 B/item
Absolute saving:   20.0 B/item
Reduction:          (28 - 8) / 28 × 100 = 71.4%
~~~

Đây là **giảm 71.4% lượng heap bytes allocated trên một item trong môi trường đo**, không phải “giảm 71.4% RAM”, “giảm 71.4% GC pause” hay “nhanh hơn 71.4%”. Nếu dùng công thức change thay reduction, `(candidate-baseline)/baseline` là **-71.4%**; báo rõ dấu và metric.

Ví dụ ngoại suy **chỉ mang tính điều kiện**: nếu thực sự xử lý 200.000 items/s cùng code path, tiết kiệm 20 B/item ~4.000.000 B/s (~4 MB/s decimal, 3.81 MiB/s binary). Production có thể không giống pilot do concurrency, JIT, tải, cache và consumer.

## 12. Thiết kế A/B test có thể tái lập

**Trước khi sửa:**
1. Chọn đơn vị đo (request, item, transaction), mô tả business scope.
2. Lưu SHA của baseline, JDK vendor/version, build flags, JVM flags, OS/container/CPU/heap.
3. Chụp workload distribution (input sizes, success/error mix, concurrency, request rate) với dữ liệu được ẩn PII.
4. Dùng JFR/allocation profiling tìm class/stack có chi phí lớn, không sửa theo trực giác.
5. Đăng ký hypothesis, primary metric và guardrails trước đo.

**Khi sửa:**
1. Chỉ thay một yếu tố chính để cô lập tác động.
2. Giữ logic nghiệp vụ, input/output contract và error handling.
3. Thêm unit/property/integration tests cho edge cases.
4. Không đổi đồng thời JDK, GC, logging, serializer và concurrency nếu không cần.

**Khi đo:**
1. Warm up cả hai variants.
2. Chạy nhiều independent JVM forks; hoán đổi thứ tự A/B hoặc randomize có seed.
3. Lưu raw measurements của từng fork/sample; tính median, dispersion và confidence interval phù hợp.
4. Chạy trên nhiều batch sizes và workload/cùng resource quotas.
5. Đối chiếu JFR hotspots, GC, RSS/retention, throughput và latency guardrails.

**Khi kết luận:**
1. Chỉ chấp nhận tối ưu nếu kết quả đúng và guardrails đạt.
2. Nếu kết quả không rõ ràng hoặc trái giả thuyết, báo “inconclusive” hoặc “regressed”, không sửa dữ liệu để trông tốt hơn.
3. Chạy canary/rollout có giám sát và rollback nếu p99/error/heap xấu đi.

### 12.1. Về sample size và confidence interval

9 samples trong một JVM chỉ mô tả **within-process variation**. Để ước lượng uncertainty thật, cần independent forks/trials và tránh giả định mỗi phần tử trong cùng batch là quan sát độc lập. Có thể bootstrap theo **fork** hoặc dùng hierarchical model; số forks đủ lớn phụ thuộc biến thiên, target effect và power analysis của đội. Báo effect size (ví dụ -20 B/item) cùng confidence interval khi đủ dữ liệu, không chỉ p-value hoặc “có lợi” từ một lần chạy.

## 13. Guardrails: allocation ít hơn chưa chắc tốt hơn

| Chiến lược | Lợi ích có thể có | Rủi ro cần kiểm |
| --- | --- | --- |
| Primitive array thay wrappers | Giảm boxing/refs. | API/null semantics, fixed size, copy cost. |
| Reuse `StringBuilder` local | Giảm builder allocation trong loop. | Không chia sẻ đa thread; `toString` vẫn tạo String. |
| `ThreadLocal` buffer | Tránh tạo buffer lặp. | Retained heap lâu theo thread pool, cleanup. |
| Shared object pool | Hạn chế allocations mới. | Lock contention, stale state, data leak/races. |
| Cache parsed values | Giảm parse CPU/alloc. | Memory retention, eviction, stale cache. |
| Larger batches | Giảm fixed overhead per item. | Peak memory, waiting latency, backpressure. |
| Off-heap/direct buffer | Có thể giảm heap pressure. | Native memory/RSS tăng, life-cycle phức tạp. |

**Đừng chọn object pooling mặc định**: hiện đại HotSpot cấp phát objects sống ngắn khá rẻ; cache/pool có thể làm hệ thống chậm hoặc tốn RAM hơn. Mỗi chiến lược là một hypothesis mới và cần experiment riêng.

Một thay đổi tạo ít byte hơn nhưng tăng p99, leak dữ liệu giữa tenants, gây race hoặc thay đổi kết quả nghiệp vụ **không được coi là thành công**.

## 14. Kiểm GC/heap bằng công cụ Java 11 hiện hành

Dùng **Unified JVM Logging** của Java 11 (thay vì các cờ GC logging cũ), ví dụ:

~~~bash
java -Xms512m -Xmx512m -Xlog:gc*:file=gc.log:time,uptime,level,tags AllocationExperiment
~~~

Đây là lệnh minh họa; `512m` không phải cấu hình chuẩn cho mọi workload. Cần giữ flags/collector/heap tương ứng giữa A/B; GC logging có overhead nên bật cùng cách trong hai nhánh.

Các quan sát cần phối hợp:
- GC count, pause time và frequency qua JFR/GC logs.
- Heap used sau/giữa các GC cycles.
- RSS và native memory, nhất là khi chuyển sang direct buffers hoặc pooling.
- CPU load/throttling, throughput, tail latency.
- Allocation per item bằng MXBean/JMH (đúng denominator).
- Correctness và error rate.

**Không dùng `System.gc()` để “làm sạch” heap giữa từng operation đo** trừ khi experiment chủ đích nghiên cứu hành vi GC. Ép GC trong hot path tạo workload nhân tạo và làm latency sai khác.

## 15. Multi-threading: một counter không phải toàn bộ request

Nếu request tạo task trên `ExecutorService` và worker thread thực hiện allocations, counter đọc từ thread HTTP chỉ tính phần work của thread đó. Với multi-thread request, tổng allocation có thể phân tán trên nhiều thread, dùng worker pools chung với các requests khác. Không cộng mù quáng tất cả thread counters rồi gán cho một request.

Giải pháp phù hợp tùy nhu cầu:
- Benchmark single-thread ở mức method để so từng variant với scope rõ.
- Profile toàn JVM/JFR để định vị hotspots dưới workload nhiều thread.
- Dùng request-level instrumentation hoặc tracing/attribution được thiết kế, không lấy một random thread ID.
- Đo system-level allocation rate dưới cùng QPS, cùng input mix, so GC/heap/CPU/latency.
- Khi có unrelated workload, cô lập benchmark environment hoặc dùng so sánh paired trials.

**Java 11 không có virtual threads.** Không đưa các API virtual thread/JDK 21+ vào code Java11. Với JVM hiện hành có virtual threads, phải kiểm semantics các counters theo tài liệu runtime mới; thread ID attribution không được giả định tương đương platform thread.

## 16. Heap profiling và memory leak là hai bài toán khác

Nếu lỗi là “heap tăng không giảm sau nhiều GC cycles”, cần nghiên cứu **retention/GC roots**, không chỉ per-request allocated bytes. Ngược lại, nếu service có GC rất thường xuyên trong khi live set ổn định, giảm objects tạm có thể hữu ích.

| Hiện tượng | Gợi ý kiểm |
| --- | --- |
| B/item rất cao, live heap ổn định | Allocation hotspot/object churn. |
| B/item ổn, old generation tăng mãi | Retention/leak/caches. |
| GC pauses cao nhưng allocation thấp | GC configuration, heap fragmentation, live set, collector. |
| RSS tăng trong khi Java heap không tăng | Native/direct memory, threads, metaspace, JIT. |
| Allocation giảm nhưng GC không đổi | Đã giảm chi phí nhưng chưa chạm GC threshold, hoặc workload khác chi phối. |
| Allocation giảm nhưng p99 tăng | CPU/cache misses/locks hoặc batch/pooling trade-offs. |

Không coi mọi memory symptom là “cần giảm số `new`”. Xác định xem bài toán là throughput, latency, memory footprint hay leak trước khi ra quyết định.

## 17. Bảng báo cáo thực nghiệm mẫu

| Chỉ số | Baseline | Candidate | Nhận xét |
| --- | ---: | ---: | --- |
| Business checksum | PASS | PASS | Cùng logic tính toán cho input thử. |
| Allocated B/item, median | **28.0** | **8.0** | Giảm 20.0 B/item, **71.4%** trên JDK thử. |
| B/item range theo fork | Chưa đo | Chưa đo | Chưa thể ước lượng CI độc lập. |
| Pilot ns/item | 6.3 | 3.1 | Số đo ngắn và biến động, chưa kết luận throughput. |
| JMH GC profiler | Chưa chạy | Chưa chạy | Cần chạy nhiều forks. |
| p95/p99 endpoint latency | Chưa đo | Chưa đo | Guardrail bắt buộc trước production rollout. |
| GC pause/count | Chưa so | Chưa so | Cần under-load evidence. |
| Retained heap / RSS | Chưa so | Chưa so | Cần kiểm không đổi allocation lấy retention. |
| JFR allocation events | Quan sát 21 events trong probe riêng | Chưa đo | Event count không phải object count. |
| Deployment JVM11 | Chưa chạy trực tiếp | Chưa chạy trực tiếp | Target source 11 không thay cho runtime test. |

**Nhận định ở giai đoạn này:** Thí nghiệm local có **bằng chứng B/item giảm** và code đúng trong workload đơn thread. **Chưa đủ bằng chứng** để tuyên bố latency/throughput/GC production tốt lên hay chấp thuận rollout. Đây là cách viết kết luận tách rõ **những gì đã đo** và **những gì chưa đo**.

## 18. Lỗi phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đếm số `new` | JIT/size/escape bị bỏ qua. | Đo heap allocated bytes. |
| Dùng `freeMemory` snapshot như tổng allocation | GC và retention bóp méo. | ThreadMXBean/JMH profiler. |
| Thấy JFR 21 events thì nói tạo 21 objects | JFR events không ghi mọi allocation. | Hiểu TLAB/slow-path semantics. |
| Chỉ đo baseline rồi không chạy candidate cùng điều kiện | Không có đối chứng. | Cố định workload/JVM/flags. |
| Một sample không warm-up | JIT chưa ổn định. | Warm-up và multiple samples/forks. |
| Luôn chạy A trước B | Order bias. | Đảo thứ tự và randomize. |
| Không dùng output | JIT xóa công việc. | Checksum/Blackhole và correctness. |
| Bỏ validation để tăng tốc | Sai business behavior. | Unit/integration equivalence tests. |
| Nhầm B/batch với B/item | Sai denominator. | Ghi tên đơn vị và chia số items. |
| Chỉ dùng current thread cho async code | Bỏ allocations của worker. | Attribution đúng scope. |
| Không xử lý `-1`/unsupported | Báo 0 hoặc giá trị sai. | Fail/NA và điều kiện hỗ trợ. |
| Assert exact ns/op | Flaky tests. | Dùng phân phối, JMH và CI tolerance. |
| B/op giảm nhưng p99 tăng | Có thể tệ hơn cho người dùng. | Guardrails system-level. |
| Cache/pool không có eviction | Retention/memory leak. | Track live heap/RSS và policy. |
| Quên khác biệt JVM11/JDK24 | Số đo không portable. | Ghi version và chạy target JVM. |
| Dùng flags JFR/GC cũ | Hướng dẫn legacy/lỗi thời. | JDK11 JFR + `-Xlog:gc*`. |
| Không lưu raw data/commit | Không tái lập được. | Lưu artifact + commands + environment. |

## 19. Bài tập có đáp án gợi ý

1. **Phân biệt:** Heap used giảm 10 MB sau GC có chứng minh allocated bytes giảm 10 MB không? **Không**, đó là snapshot sau collection.
2. **Công thức:** Baseline 5.600.000 bytes, candidate 1.600.000 bytes cho 200.000 items. **Đáp án:** 28 vs 8 B/item, giảm 20 B/item = 71.4%.
3. **Tốc độ cấp phát:** Tiết kiệm 20 B/item ở 300.000 items/s là 6.000.000 B/s (~6 MB/s), nếu workload tương đương.
4. **Correctness:** Thêm assertions `boxedBatch(0)==primitiveBatch(0)`, `boxedBatch(1)==primitiveBatch(1)`, `boxedBatch(1000)==primitiveBatch(1000)`.
5. **JIT:** Tại sao benchmark `new Object()` rồi bỏ kết quả có thể báo gần 0 B/op? Vì optimizer có thể xóa allocation không quan sát được.
6. **Boxing cache:** Nếu `List<Long>` chỉ lưu giá trị 0..100, kết quả allocation có thay đổi so với demo không? Có thể, do cache và tối ưu JIT.
7. **JFR:** Chạy `AllocationJfrProbe.java`; tại sao 12×100.000 values không tạo đúng 1.200.000 JFR events? Vì TLAB events không đại diện từng object.
8. **GC:** Dùng `-Xlog:gc*` xem GC trước/sau. Tại sao B/item giảm 71% nhưng GC pause không bắt buộc giảm cùng tỷ lệ?
9. **JMH:** Chạy `BatchAllocationJmh` có `-prof gc`; chuyển `gc.alloc.rate.norm` thành B/item khi `items=1000` và `10000`.
10. **Threads:** Một request chuyển sang executor. Tại sao `getThreadAllocatedBytes` ở main thread không đủ cho request-level allocation?
11. **Pooling:** Object pool giảm allocations nhưng retained heap/RSS tăng. Đề xuất phân tích trade-off và policy eviction.
12. **Decision:** B/item giảm 35% nhưng p99 tăng 20% so với gate +5%. **Đáp án:** Không chấp nhận rollout theo gate đã định.
13. **Report:** Thiết kế bảng lưu JDK/commit/flags/raw runs/CI/GC/p99/correctness, không chỉ phần trăm giảm.
14. **Reproduction:** Chạy code với `WARMUPS=0` và `WARMUPS=6`, so raw samples; giải thích JIT chưa nóng.
15. **Scope:** Nếu batch bao gồm network serialization, có nên đo chỉ transform array rồi gọi là B/request không? **Không**, chỉ được gọi B/item của transform stage.

## 20. Checklist trước khi tuyên bố tối ưu thành công

- [ ] Có định nghĩa rõ **đơn vị nghiệp vụ** và primary metric B/item hoặc B/request.
- [ ] Có baseline, candidate và một thay đổi độc lập chính.
- [ ] Cùng data distribution, heap/GC flags, JVM version, environment.
- [ ] Code mới giữ nguyên correctness, error handling, null/API/concurrency semantics.
- [ ] Counter hỗ trợ và đã bật; không biến unsupported thành 0.
- [ ] Warm-up, nhiều samples, đảo thứ tự, nhiều independent forks khi quyết định production.
- [ ] Không đo dead code do JIT xóa mất, có output được sử dụng.
- [ ] Ghi exact bytes delta/denominator và effect size, phân biệt reduction vs percentage change.
- [ ] Không nhầm allocation với live heap, GC count hay JFR event count.
- [ ] JFR dùng cho hotspots và GC context, không ép event counts thành exact objects.
- [ ] JMH và load test nếu cần luận cứ throughput/p95/p99.
- [ ] Kiểm CPU, RSS, retained heap, GC, error rate và concurrency.
- [ ] Không dùng Java API/flags đã legacy hoặc không thuộc Java 11 trong ví dụ.
- [ ] Có raw data, commit, JDK vendor/version và lệnh chạy để tái lập.
- [ ] Nếu sản phẩm chạy JVM11, phải có CI test trên **JDK11 runtime thực**.
- [ ] Có acceptance gate, canary/rollback và kết luận phân biệt observed vs unverified.

## 21. Tài liệu tham khảo

- [Java SE 11 — com.sun.management.ThreadMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): đo per-thread allocated bytes, kiểm capability, ước lượng và giá trị `-1`.
- [Java SE 11 — ManagementFactory](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/ManagementFactory.html): truy cập platform MXBeans.
- [Java SE 11 — MemoryMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html): live heap/usage snapshot khác allocated bytes.
- [Java SE 11 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): GC collection counts/time.
- [Java SE 11 — JFR API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/module-summary.html): `FlightRecorder`, `Recording`, events và consumer.
- [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc file `.jfr`.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR như thành phần JDK.
- [OpenJDK JMH](https://github.com/openjdk/jmh): benchmark harness, warm-up, forks, result consumption và profiler.
- [JMH Maven artifact](https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-core): dependency phù hợp, kiểm phiên bản trước khi nâng.
- [Java SE 11 — JVM options and Unified Logging](https://docs.oracle.com/en/java/javase/11/tools/java.html): `-Xlog:gc*` và tùy chọn runtime.

**Kết luận:** Trong thí nghiệm mẫu target Java 11 đã chạy trên JDK thử, chuyển `List<Long>` sang `long[]` giảm lượng heap cấp phát quan sát từ **28.0 xuống 8.0 B/item**, tương đương **giảm 71.4%** cho cùng một checksum. Đây mới là bằng chứng **micro allocation** trong môi trường kiểm soát, không phải một lời hứa throughput/p99 production. Để khẳng định cải thiện, phải giữ baseline/candidate, warm-up/forks, đúng denominator và correctness, đồng thời đối chiếu JFR hotspots, GC, retained heap, latency và các guardrail.