# Đo bộ nhớ, thời gian làm nóng, thông lượng và độ trễ trong JVM

Đánh giá hiệu năng JVM cần đo nhiều khía cạnh cùng lúc. **Bộ nhớ** cho biết heap đang sử dụng bao nhiêu và ứng dụng cấp phát nhanh thế nào; **warmup** cho phép JVM tải lớp, profiling và biên dịch mã nóng; **throughput** đo số thao tác hoàn thành trong một đơn vị thời gian; **latency** đo thời gian một thao tác hoặc request phải chờ.

Không thể dùng một con số để đại diện cho tất cả. Heap snapshot thấp không chứng minh allocation rate thấp; throughput cao không bảo đảm p99 latency tốt; số đo trước khi JIT ổn định cũng có thể không đại diện cho hiệu năng sau warmup. Bài này dùng API JDK hiện hành, JMH cho microbenchmark và JFR cho profiling.

## 1. Bốn nhóm số đo cần phân biệt

| Chỉ số | Câu hỏi cần trả lời | Đơn vị thường dùng |
| --- | --- | --- |
| Heap usage | JVM đang giữ bao nhiêu bộ nhớ heap tại thời điểm lấy mẫu? | bytes, MiB |
| Allocation rate | Ứng dụng tạo object/array mới nhanh đến mức nào? | bytes/s, objects/s |
| Throughput | Hệ thống hoàn thành bao nhiêu thao tác trong một đơn vị thời gian? | ops/s, requests/s |
| Latency | Một thao tác/request mất bao lâu? | ns, µs, ms; p50/p95/p99 |

Heap usage là ảnh chụp trạng thái tại một thời điểm. Allocation rate là tốc độ tạo object, bao gồm cả object sống ngắn sẽ được GC thu hồi. Throughput là tốc độ hoàn thành công việc. Latency là thời gian chờ của từng thao tác. Các chỉ số liên quan nhưng không thể thay thế cho nhau.

## 2. Đo bộ nhớ heap

`MemoryMXBean` cung cấp thông tin heap của JVM:

```java
MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = memoryBean.getHeapMemoryUsage();
long used = heap.getUsed();
long committed = heap.getCommitted();
long max = heap.getMax();
```

- `used`: dung lượng heap đang được sử dụng tại thời điểm lấy mẫu.
- `committed`: dung lượng heap JVM đã được cấp để sử dụng.
- `max`: giới hạn heap tối đa nếu JVM biết được; có thể là `-1` nếu không xác định.

Giá trị thay đổi sau GC, khi heap mở rộng/thu hẹp hoặc khi workload thay đổi. Một lần đọc không cho biết peak usage và cũng không cho biết tổng byte đã cấp phát trong một khoảng thời gian.

### Heap không phải toàn bộ bộ nhớ tiến trình

Heap usage không bao gồm toàn bộ RSS của tiến trình. JVM còn sử dụng metaspace, thread stack, JIT code cache, direct byte buffers, native memory do JNI/thư viện native quản lý và các vùng native khác của runtime. Vì vậy, không kỳ vọng heap usage bằng RAM mà hệ điều hành hoặc container báo cáo.

Để quan sát native memory của HotSpot, bật Native Memory Tracking khi khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar application.jar
jcmd <pid> VM.native_memory summary
```

Native Memory Tracking có overhead và cần bật từ lúc JVM khởi động. Chỉ dùng khi cần phân tích native memory; nó không thay thế phép đo heap.

## 3. Đo allocation rate

Heap usage và allocation rate trả lời hai câu hỏi khác nhau. Một request có thể tạo nhiều object tạm thời rồi GC thu hồi; heap usage cuối request có thể thấp dù allocation rate rất cao.

Trên JDK hiện hành, extension `com.sun.management.ThreadMXBean` có thể lấy số byte một thread đã cấp phát:

```java
com.sun.management.ThreadMXBean bean =
    (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

if (bean.isThreadAllocatedMemorySupported()) {
    bean.setThreadAllocatedMemoryEnabled(true);
    long threadId = Thread.currentThread().threadId();
    long before = bean.getThreadAllocatedBytes(threadId);
    // Chạy workload cần đo.
    long after = bean.getThreadAllocatedBytes(threadId);
    long allocatedBytes = after - before;
}
```

`getThreadAllocatedBytes` đo byte được cấp phát bởi thread. Lấy hiệu giữa hai lần đọc để tính allocation trong đoạn code được đo. Nếu API không hỗ trợ hoặc không bật được, cần xử lý trường hợp không có số liệu.

API này đo allocation theo thread. Với ứng dụng nhiều thread, cần lấy số liệu từng thread hoặc dùng JFR để quan sát allocation toàn JVM. Không cộng heap usage trước/sau để suy ra allocation rate.

Allocation rate cao có thể làm tăng young GC, CPU dành cho allocation/GC và tail latency. Tuy nhiên, allocation rate cao không tự động là lỗi; cần đối chiếu object lifetime, heap headroom, GC pause, CPU và latency.

## 4. Warmup và JIT compilation

JVM không nhất thiết thực thi một method theo cùng cách từ lần gọi đầu tiên đến khi ứng dụng chạy ổn định. Trong quá trình hoạt động, JVM có thể load/initialize class, thực thi bằng interpreter, thu thập profile của call site và branch, biên dịch code nóng bằng JIT, rồi tối ưu hoặc deoptimize khi giả định không còn đúng.

**Warmup** là giai đoạn chạy workload đại diện trước khi lấy số đo chính. Warmup giúp giảm ảnh hưởng của class loading, JIT compilation và các lần khởi tạo ban đầu.

Warmup phải dùng cùng đường code, dữ liệu và kiểu tải tương tự giai đoạn đo. Chỉ gọi method vài lần hoặc dùng `Thread.sleep()` không chứng minh JVM đã ổn định.

Dấu hiệu warmup chưa ổn định gồm throughput tăng rõ giữa các iteration, latency percentile thay đổi mạnh, JIT compilation vẫn diễn ra đáng kể trong measurement hoặc class loading/cache initialization chưa hoàn tất. Với benchmark nghiêm túc, dùng JMH để tách warmup và measurement, chạy nhiều fork JVM độc lập.

## 5. Đo throughput

Throughput là số lượng thao tác hoàn thành chia cho thời gian đo:

\[
\text{throughput} = \frac{\text{completed operations}}{\text{elapsed time}}
\]

Nếu hoàn thành 500.000 thao tác trong 2 giây, throughput trung bình là 250.000 ops/s.

Khi tự đo elapsed time trong Java, dùng `System.nanoTime()`:

```java
long start = System.nanoTime();
runWorkload();
long elapsedNanos = System.nanoTime() - start;
double operationsPerSecond =
    operations * 1_000_000_000.0 / elapsedNanos;
```

`nanoTime()` phù hợp để đo khoảng thời gian vì nó là đồng hồ monotonic. Không dùng `System.currentTimeMillis()` để đo duration ngắn vì đó là thời gian lịch và có thể bị điều chỉnh.

Throughput phụ thuộc concurrency, CPU, allocation, lock contention, I/O, queueing và giới hạn tài nguyên. Khi tăng số thread, throughput có thể tăng đến điểm bão hòa rồi chững lại hoặc giảm.

## 6. Đo latency và percentile

Latency là thời gian của một thao tác cụ thể. Không nên chỉ báo cáo average vì trung bình có thể che giấu các request rất chậm.

- **p50:** một nửa thao tác có latency không vượt giá trị này; đây là median.
- **p95:** 95% thao tác hoàn thành trong hoặc dưới giá trị này.
- **p99:** 99% thao tác hoàn thành trong hoặc dưới giá trị này; hữu ích để theo dõi tail latency.
- **max:** latency lớn nhất quan sát được; nhạy với outlier và số lượng mẫu.

Ví dụ p50 = 8 ms và p99 = 250 ms cho thấy đa số request nhanh nhưng một phần nhỏ bị chậm đáng kể. Cần xem histogram và phân bố thay vì chỉ nhìn average.

### Cẩn thận khi đo thao tác rất ngắn

Mỗi lần gọi `System.nanoTime()` cũng có chi phí. Nếu operation chỉ mất vài chục nanosecond, đo trước/sau từng lần gọi có thể làm sai lệch kết quả đáng kể. Với microbenchmark, dùng JMH `SampleTime` hoặc đo theo batch phù hợp; với request thực, đo ở ranh giới request bằng instrumentation của ứng dụng.

Trong load test, nếu generator chỉ gửi request mới sau khi request trước hoàn tất, khi hệ thống chậm nó cũng giảm tốc độ gửi và có thể bỏ sót tail latency (coordinated omission). Với hệ thống nhận request liên tục, cần đo offered load, completed throughput, queue time và latency theo mô hình tải phù hợp.

## 7. Dùng JMH cho microbenchmark

JMH (Java Microbenchmark Harness) là công cụ chuyên dụng để đo các đoạn code Java nhỏ. JMH quản lý warmup, measurement iteration, fork JVM, tiêu thụ kết quả benchmark và các chi tiết harness dễ làm sai khi tự viết vòng lặp đo.

Ví dụ benchmark:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class ParsingBenchmark {
    private String input;

    @Setup(Level.Trial)
    public void setup() {
        input = "user:42:active";
    }

    @Benchmark
    @BenchmarkMode(Mode.Throughput)
    @OutputTimeUnit(TimeUnit.SECONDS)
    public int parseThroughput() {
        return input.indexOf(':');
    }

    @Benchmark
    @BenchmarkMode(Mode.SampleTime)
    @OutputTimeUnit(TimeUnit.MICROSECONDS)
    public int parseLatency() {
        return input.indexOf(':');
    }
}
```

`@Warmup` cấu hình iteration warmup; `@Measurement` cấu hình iteration lấy số đo; `@Fork(2)` chạy benchmark trong hai JVM fork độc lập; `@State(Scope.Thread)` tạo state riêng cho từng benchmark thread. JMH tiêu thụ kết quả trả về để tránh compiler loại bỏ công việc không quan sát được.

Chạy benchmark bằng JMH runner của project:

```bash
java -jar target/benchmarks.jar ParsingBenchmark
```

JMH báo cáo throughput hoặc sample-time distribution theo benchmark mode. Có thể chọn mode bằng tham số runner như `-bm thrpt` hoặc `-bm sample`. Dùng dependency và annotation processor JMH hiện hành của project; không coi vòng lặp `System.nanoTime()` tự viết tương đương JMH.

JMH phù hợp cho microbenchmark trong JVM. Đo HTTP service, database, queue hoặc hệ thống nhiều tiến trình cần load test ở cấp ứng dụng và quan sát tài nguyên hệ thống.

## 8. Dùng JFR để quan sát CPU, allocation và GC

Java Flight Recorder (JFR) là profiler tích hợp trong JDK, phù hợp để thu thập dữ liệu runtime với overhead thấp khi dùng cấu hình phù hợp. Có thể bắt đầu recording khi chạy ứng dụng:

```bash
java -XX:StartFlightRecording=filename=app.jfr,settings=profile,dumponexit=true -jar application.jar
```

Hoặc bắt đầu recording cho một JVM đang chạy:

```bash
jcmd <pid> JFR.start name=performance settings=profile duration=60s filename=performance.jfr
```

Đọc tổng quan recording và in các event quan tâm:

```bash
jfr summary performance.jfr
jfr print --events jdk.GCPhasePause,jdk.ObjectAllocationSample performance.jfr
```

JFR giúp quan sát CPU samples, allocation samples, GC phases, thread activity, lock contention và nhiều event runtime khác. Java Mission Control hỗ trợ xem timeline, flame graph và phân bố event thuận tiện hơn.

JFR là dữ liệu profiling; chọn recording duration/settings phù hợp và bảo vệ file recording vì nó có thể chứa thông tin nhạy cảm về ứng dụng và runtime.

## 9. Native memory và process footprint

Nếu heap usage ổn định nhưng RSS của tiến trình tăng, hãy xem các vùng ngoài heap: Native Memory Tracking của HotSpot, direct buffer pool, metaspace/class loading, số lượng thread và stack size, JNI/native library cùng code cache. Đối chiếu JFR với công cụ hệ điều hành/container để xem RSS, CPU và memory pressure.

Không kết luận memory leak chỉ từ một lần RSS hoặc heap snapshot tăng. Theo dõi xu hướng qua nhiều chu kỳ workload và GC, phân biệt memory retained với allocation tạm thời.

## 10. Chương trình Java 21 đo các chỉ số cơ bản

Chương trình sau chạy warmup trước, đo throughput trên batch cố định, lấy mẫu latency để tính p50/p95/p99, đọc heap usage trước/sau và đọc số byte thread đã cấp phát. Workload có allocation có chủ đích để tạo số liệu quan sát được.

Đây là ví dụ học API và cách phân biệt các số đo. Kết quả của vòng lặp tự viết không thay thế JMH; phép đo từng operation còn bao gồm overhead của `nanoTime()`.

```java
import com.sun.management.ThreadMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.util.Arrays;

public class PerformanceProbe {
    private static final int WARMUP_ROUNDS = 5;
    private static final int WARMUP_OPERATIONS = 100_000;
    private static final int MEASURED_OPERATIONS = 250_000;
    private static final int LATENCY_SAMPLES = 10_000;
    private static final int RING_SIZE = 4096;
    private static final byte[][] RING = new byte[RING_SIZE][];
    private static volatile long sink;

    public static void main(String[] args) {
        MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
        ThreadMXBean threadBean = allocationBean();
        long threadId = Thread.currentThread().threadId();

        long checksum = 0;
        for (int round = 0; round < WARMUP_ROUNDS; round++) {
            checksum += runBatch(WARMUP_OPERATIONS);
        }
        sink = checksum;
        System.out.println("warmup complete: " + WARMUP_ROUNDS + " rounds");

        long heapBefore = heapUsed(memoryBean);
        long allocatedBefore = allocatedBytes(threadBean, threadId);

        long start = System.nanoTime();
        checksum += runBatch(MEASURED_OPERATIONS);
        long elapsed = System.nanoTime() - start;
        sink = checksum;
        double throughput = MEASURED_OPERATIONS * 1_000_000_000.0 / elapsed;
        System.out.printf("throughput: %.0f ops/s%n", throughput);

        long[] latency = new long[LATENCY_SAMPLES];
        long latencyChecksum = 0;
        for (int i = 0; i < latency.length; i++) {
            long before = System.nanoTime();
            latencyChecksum += work(i + checksum);
            latency[i] = System.nanoTime() - before;
        }
        sink = latencyChecksum;
        Arrays.sort(latency);
        System.out.printf("latency p50/p95/p99: %d/%d/%d ns%n",
            percentile(latency, 50), percentile(latency, 95), percentile(latency, 99));

        long heapAfter = heapUsed(memoryBean);
        long allocatedAfter = allocatedBytes(threadBean, threadId);
        System.out.printf("heap used before/after measurement: %d/%d bytes%n",
            heapBefore, heapAfter);
        if (allocatedBefore >= 0 && allocatedAfter >= allocatedBefore) {
            System.out.printf("thread allocated bytes during measurement: %d%n",
                allocatedAfter - allocatedBefore);
        } else {
            System.out.println("thread allocated bytes during measurement: unsupported");
        }
    }

    private static long runBatch(int operations) {
        long result = 0;
        for (int i = 0; i < operations; i++) {
            result += work(i + result);
        }
        return result;
    }

    private static long work(long value) {
        long mixed = value;
        for (int i = 0; i < 512; i++) {
            mixed = Long.rotateLeft(mixed ^ (value + i), 7) * 0x9E3779B97F4A7C15L;
        }
        byte[] data = new byte[128];
        data[0] = (byte) mixed;
        data[127] = (byte) (mixed >>> 8);
        RING[(int) value & (RING_SIZE - 1)] = data;
        return mixed + data[0] + data[127];
    }

    private static long percentile(long[] sorted, int percentile) {
        int index = (int) Math.ceil(percentile / 100.0 * sorted.length) - 1;
        return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
    }

    private static long heapUsed(MemoryMXBean bean) {
        MemoryUsage usage = bean.getHeapMemoryUsage();
        return usage.getUsed();
    }

    private static ThreadMXBean allocationBean() {
        java.lang.management.ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        if (bean instanceof ThreadMXBean extended
                && extended.isThreadAllocatedMemorySupported()) {
            if (!extended.isThreadAllocatedMemoryEnabled()) {
                extended.setThreadAllocatedMemoryEnabled(true);
            }
            return extended;
        }
        return null;
    }

    private static long allocatedBytes(ThreadMXBean bean, long threadId) {
        return bean == null ? -1 : bean.getThreadAllocatedBytes(threadId);
    }
}
```

Lưu thành `PerformanceProbe.java`, biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 -Xlint:all PerformanceProbe.java
java PerformanceProbe
```

Một lần chạy thử cho kết quả dạng:

```text
warmup complete: 5 rounds
throughput: 2068798 ops/s
latency p50/p95/p99: 500/600/600 ns
heap used before/after measurement: 68272920/2343736 bytes
thread allocated bytes during measurement: 38084032
```

Các số throughput, latency và memory thay đổi theo CPU, JDK, GC, hệ điều hành và tải máy; không dùng số minh họa làm ngưỡng hiệu năng cố định.

Trong ví dụ, heap used giảm sau khi GC thu hồi object tạm thời, trong khi thread allocated bytes vẫn lớn vì counter ghi nhận allocation đã xảy ra dù object không còn sống. `ThreadMXBean` là extension của JDK management API; runtime image tối giản cần module `jdk.management` để sử dụng.

## 11. Quy trình benchmark và đọc kết quả

1. **Xác định câu hỏi:** cần đo throughput, latency, allocation, heap, native memory hay CPU.
2. **Chọn workload đại diện:** dùng dữ liệu, concurrency, request mix và cấu hình gần production.
3. **Tách setup khỏi measurement:** khởi tạo dữ liệu, kết nối và cache trong setup nếu đó không phải phần cần đo.
4. **Warmup:** chạy đủ iteration để JIT và runtime đạt trạng thái ổn định.
5. **Fork và lặp lại:** chạy nhiều process JVM độc lập; quan sát độ biến thiên giữa các lần.
6. **Đo nhiều chiều:** throughput, p50/p95/p99, allocation rate, heap, GC và CPU.
7. **Đối chiếu tải:** ghi offered load, concurrency, completed throughput và queue time.
8. **Tìm bottleneck:** dùng JFR để xác định CPU hotspots, allocation, lock contention hoặc GC.
9. **Thay đổi một yếu tố mỗi lần:** tránh thay heap, GC, thread count và workload cùng lúc.
10. **Lặp lại trên môi trường tương đương:** CPU quota, container memory, JDK build và cấu hình JVM ảnh hưởng kết quả.

### Diễn giải một số tình huống

| Quan sát | Hướng điều tra |
| --- | --- |
| Throughput tăng nhưng p99 xấu đi | Queueing, contention, GC pause, thread pool và saturation. |
| Heap sau GC ổn định nhưng allocation rate cao | Object tạm thời, boxing, collection churn, buffer copy. |
| Heap tăng qua nhiều chu kỳ GC | Object retained, cache không giới hạn, listener/reference leak. |
| RSS tăng nhưng heap ổn định | Direct buffer, metaspace, thread stack, native library, code cache. |
| Warmup iteration nhanh dần | JIT compilation, class loading, cache hoặc lazy initialization. |
| CPU thấp nhưng latency cao | I/O wait, lock, queueing, network hoặc downstream service. |

## 12. Những lỗi thường gặp

1. **Đồng nhất heap usage với allocation rate.** Heap là ảnh chụp object còn sống; allocation là tổng byte đã cấp phát trong khoảng đo.
2. **Dùng `Runtime.freeMemory()` làm báo cáo bộ nhớ duy nhất.** Dùng `MemoryMXBean` để đọc heap usage và công cụ phù hợp để quan sát native memory/RSS.
3. **Đo ngay lần gọi đầu tiên.** Class loading và JIT warmup làm kết quả không đại diện cho trạng thái ổn định.
4. **Dùng `Thread.sleep()` làm warmup.** Thời gian trôi qua không chứng minh workload đã được JIT tối ưu.
5. **Dùng `currentTimeMillis()` cho duration.** Dùng `System.nanoTime()` để đo khoảng thời gian.
6. **Chỉ báo cáo average latency.** Báo cáo p50/p95/p99 và histogram để thấy tail latency.
7. **Tự viết microbenchmark rồi tin tuyệt đối.** Harness có thể bị dead-code elimination, constant folding, timer overhead hoặc JIT profile sai; dùng JMH.
8. **Không tách setup khỏi measurement.** Khởi tạo dữ liệu hoặc mở kết nối trong vùng đo có thể làm sai câu hỏi benchmark.
9. **Không dùng fork JVM.** Trạng thái JIT, heap và profile của một JVM có thể ảnh hưởng kết quả giữa các lần chạy.
10. **Đo một thread rồi suy ra throughput production.** Concurrency, queueing, lock contention và downstream dependency làm thay đổi kết quả.
11. **Bỏ qua coordinated omission trong load test.** Load generator cần phản ánh tốc độ request đến hệ thống, kể cả khi hệ thống đang chậm.
12. **Coi số heap sau một lần GC là memory footprint.** RSS còn chứa native memory, stack, metaspace, code cache và direct buffer.
13. **Kết luận leak từ một snapshot tăng.** Theo dõi xu hướng qua nhiều chu kỳ GC và phân tích object retained.
14. **So sánh số đo từ máy hoặc JDK khác nhau mà không ghi cấu hình.** Ghi lại JDK build, GC, heap flags, CPU quota và môi trường.

## 13. Ghi nhớ

1. Heap usage, allocation rate, throughput và latency là bốn loại số đo khác nhau.
2. `MemoryMXBean.getHeapMemoryUsage()` cung cấp used, committed và max tại thời điểm lấy mẫu.
3. Heap không bao gồm toàn bộ RSS; native memory, metaspace, stack, code cache và direct buffer cần được xem riêng.
4. `ThreadMXBean.getThreadAllocatedBytes()` có thể đo allocation theo thread; JFR hỗ trợ profiling allocation toàn JVM.
5. Warmup giúp class loading, JIT compilation và runtime profile ổn định trước measurement.
6. `System.nanoTime()` phù hợp để đo elapsed time; không dùng wall-clock time cho duration.
7. Throughput đo số thao tác hoàn thành mỗi giây; latency nên báo cáo p50/p95/p99.
8. Dùng JMH cho microbenchmark; dùng load test và JFR cho ứng dụng nhiều thread hoặc service.
9. Phân tích cả offered load, queueing, GC, CPU, allocation và memory để tìm bottleneck.
10. Số đo chỉ có ý nghĩa khi workload, môi trường và phương pháp đo được kiểm soát.