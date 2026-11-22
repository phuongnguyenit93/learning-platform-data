# Đo thông lượng, độ trễ, thời gian dừng và phân bố cấp phát khi đánh giá G1 và NUMA

## Mục tiêu và phạm vi

Khi đánh giá **Garbage-First Garbage Collector (G1 GC)** trên máy có **Non-Uniform Memory Access (NUMA)**, một phép đo “chạy nhanh hơn” không đủ để khẳng định cấu hình tốt hơn. Một thay đổi có thể tăng số thao tác xử lý mỗi giây nhưng làm đuôi độ trễ xấu đi; giảm số lần GC nhưng khiến một lần dừng lâu hơn; hoặc tăng lượng bộ nhớ nằm ở NUMA node cục bộ nhưng không cải thiện thời gian phản hồi của dịch vụ.

Bài này tập trung đúng bốn nhóm chỉ số:

1. **Thông lượng (*throughput*)**: lượng công việc hữu ích hoàn tất mỗi giây, và chi phí GC đi kèm.
2. **Độ trễ (*latency*)**: phân bố thời gian hoàn thành một thao tác hoặc một request, đặc biệt p95/p99, không chỉ trung bình.
3. **Thời gian dừng (*GC pause*)**: số lần, tổng thời gian, mức phân vị và đỉnh của các khoảng *stop-the-world* (STW).
4. **Phân bố cấp phát (*allocation distribution*)**: đối tượng được cấp phát theo kích thước, lớp, call stack, thread và — khi có NUMA thật — vị trí bộ nhớ theo node.

Bạn sẽ xây dựng chương trình Java 17+ đo một workload nhân tạo, thu GC log bằng **Unified Logging**, dùng **Java Flight Recorder (JFR)** để quan sát allocation, và so sánh `-XX:-UseNUMA` với `-XX:+UseNUMA` trên phần cứng phù hợp. Phần quan trọng không kém là phân biệt **chỉ số ứng dụng**, **GC statistics**, **dữ liệu lấy mẫu JFR** và **số liệu trang bộ nhớ do OS ghi nhận**.

**Special Note về tính hiện hành:** G1 và hỗ trợ cấp phát nhận biết NUMA được đưa vào G1 từ Java 14 (JEP 345) và vẫn có ý nghĩa trong các JDK hiện đại. Mã và lệnh thực hành dùng **JDK 17 trở lên**, `-Xlog`, JFR và các API đang được hỗ trợ; không dùng các cờ GC logging lỗi thời từ thế hệ JDK trước.

## 1. Bối cảnh: G1 quản lý bộ nhớ và NUMA ảnh hưởng điều gì?

G1 chia Java heap thành các **region**, thực hiện thu gom young generation và một phần old generation theo từng nhóm region, đồng thời làm một số công việc concurrent. G1 hướng tới **cân bằng throughput với độ dài pause có thể kiểm soát**, chứ không cam kết mọi pause đều dưới một số mili-giây cố định.

NUMA là kiến trúc trong đó CPU tiếp cận RAM **cùng node** thường nhanh hơn RAM **ở node khác**. Trên máy nhiều socket/nhiều NUMA node, thread ứng dụng hoặc GC thread có thể phải đọc/ghi bộ nhớ “remote”. Độ trễ truy cập và băng thông có thể phụ thuộc node, chính sách gán CPU/memory, cgroup, VM/container và hành vi của OS.

JEP 345 bổ sung **NUMA-aware memory allocation cho G1**. Hướng tối ưu quan trọng là cải thiện tính cục bộ cấp phát của **young generation**; không nên suy rộng rằng tất cả old/humongous regions hoặc mọi truy cập của ứng dụng đều được “ghim cứng” vào một node. Cơ chế cụ thể có thể phát triển theo phiên bản HotSpot.

### Khi nào NUMA có ý nghĩa?

- **Có ý nghĩa để đo:** máy thật có ít nhất hai NUMA node có bộ nhớ khả dụng; workload đủ lớn hoặc chạy đủ song song để tạo truy cập bộ nhớ giữa các node.
- **Ít có ý nghĩa:** laptop, VM chỉ thấy một node, container bị che topology, workload quá nhỏ hoặc phần lớn thời gian chạy dành cho I/O mà không chịu áp lực heap.
- **Không bảo đảm lợi ích:** `-XX:+UseNUMA` là một cấu hình cần **benchmark trên hệ thống đích**, không phải “công tắc tăng tốc” tuyệt đối.

**Kiểm tra nền tảng trước khi kết luận:** Trên Linux, các tiện ích như `numactl --hardware` và `numastat` giúp xác định topology và phân bố trang bộ nhớ. Chúng **không** được phân phối như một phần Java SE. Khi chạy JVM trong container, cần kiểm tra CPU/memory binding và số node mà tiến trình thật sự nhìn thấy; đừng chỉ tin topology tổng của host.

## 2. Bốn nhóm chỉ số không thể thay thế nhau

| Chỉ số | Câu hỏi trả lời | Nguồn dữ liệu tốt | Đơn vị/nhận xét |
| --- | --- | --- | --- |
| Throughput | Một giây xử lý bao nhiêu request/operation thành công? | Load generator hoặc metric nghiệp vụ | requests/s hoặc ops/s |
| Latency | Mất bao lâu để một thao tác/request hoàn tất? | Timer theo request, tracing, histograms | ms; p50/p95/p99/p99.9 |
| GC pause | JVM dừng các application threads vì GC bao lâu? | `-Xlog:gc*`, JFR GC pause events | ms; count, sum, p95/p99/max |
| Allocation | Ứng dụng sinh ra bao nhiêu object/byte và từ đâu? | JFR allocation sample, profiler, instrumented workload | bytes/s; phân bố class/size/stack/thread |
| Memory locality | Trang nhớ có xu hướng nằm ở NUMA node nào? | OS `numastat -p`, perf/NUMA tracing | trang/MB theo node; **không phải object allocation count** |
| GC CPU/overhead | GC dùng CPU hoặc chiếm thời gian bao nhiêu? | GC log `gc+cpu`, OS CPU metrics | CPU time, wall time; không đồng nhất với STW pause |

**Tránh sai lầm:** GC pause không bằng request latency. Một request có thể chậm vì database, lock, mạng hoặc scheduling dù GC log không có pause dài. Ngược lại, throughput có thể ổn nhưng một số request bị đuôi p99 nặng khi dừng GC.

## 3. Đo thông lượng — công việc hữu ích trên một đơn vị thời gian

Công thức cơ bản:

```text
Throughput (ops/s) = số thao tác hoàn tất / thời gian wall-clock đo được (giây)
```

Với dịch vụ web, chỉ nên đếm **request hoàn tất hợp lệ**; ghi riêng status code, lỗi và timeout. Với benchmark CPU/memory nội bộ, đếm thao tác mà test thực sự đã thực hiện.

Ví dụ **số liệu minh họa, không phải đo thực tế**:

- Baseline: 120.000 ops hoàn tất trong 10 giây → `12.000 ops/s`.
- NUMA enabled: 126.000 ops trong 10 giây → `12.600 ops/s`.
- Chênh lệch quan sát: `(12.600 / 12.000 - 1) × 100% = +5%`.

Không đủ căn cứ kết luận NUMA tốt hơn từ một lần chạy: phải xem **độ biến thiên giữa các run, tải CPU, GC pauses, latency SLO và môi trường**. Chênh lệch nhỏ có thể chỉ là noise do JIT warmup, thermal throttling hoặc tiến trình khác.

**Thông lượng ứng dụng không phải `100% - GC pause share`.** G1 còn có công việc concurrent, card barrier, remembered set, copy objects và overhead bộ nhớ; throughput phụ thuộc toàn bộ chương trình.

## 4. Đo độ trễ — nhìn phân bố thay vì chỉ trung bình

Giả sử `tStart` và `tEnd` là hai lần đo bằng `System.nanoTime()` trên cùng JVM:

```java
long begin = System.nanoTime();
performOneOperation();
long elapsedNs = System.nanoTime() - begin;
```

Đoạn này là **mã minh họa bên trong một method**, với `performOneOperation()` là phép toán thực tế của ứng dụng do người học định nghĩa.

Phân biệt:

- **Mean**: trung bình cộng, có thể che các sự kiện chậm hiếm gặp.
- **p50**: một nửa quan sát không lớn hơn ngưỡng này (theo cách tính percentile được chọn).
- **p95/p99**: quan trọng với SLO/tail latency; cần đủ số mẫu.
- **Max**: giúp phát hiện spike, nhưng rất nhạy với một lần scheduling hoặc tải nền.
- **End-to-end**: tính từ lúc hệ thống **nhận request** đến lúc có response, gồm queueing, downstream, lock, GC.
- **Micro-operation latency**: đo một thao tác nội bộ như `new byte[]`; **không** được gắn nhãn là latency của dịch vụ web.

Khi đo thời gian rất ngắn, bản thân `System.nanoTime()` và công cụ instrumentation cũng có overhead. Cần warmup, số lượng mẫu đủ lớn, cách lấy mẫu cân bằng và báo rõ scope đo.

Không suy ra “G1 đã đạt p99 10 ms” chỉ từ việc đặt `-XX:MaxGCPauseMillis=10`: đây là **mục tiêu điều chỉnh GC pause, không phải hard deadline** và cũng không phải target latency của request.

## 5. Đo GC pause — phân biệt STW với thời gian GC khác

G1 thực hiện các khoảng dừng STW như young/mixed pause, remark/cleanup và có thể Full GC. Một số công việc GC khác là concurrent. Vì vậy:

- **GC pause duration**: thời gian JVM dừng các thread ứng dụng tại một pause, nên phân tích từ event/log cụ thể.
- **Total STW pause time**: tổng các khoảng STW trong cửa sổ đo; một dạng chỉ số ảnh hưởng đến khả năng phục vụ.
- **Pause ratio**: `sum(STW pause duration) / elapsed wall-clock × 100%`, dùng như một mô tả thời gian bị dừng, không phải phép suy ra throughput.
- **GC CPU user/sys/real**: `User` có thể lớn hơn `Real` vì các GC worker chạy song song; `Real` gần hơn với wall time của riêng hoạt động được báo nhưng không phải một chỉ số request latency.
- **MXBean collection time**: một chỉ số tổng hợp/coarse do JVM cung cấp, **không nên coi là cùng một phép đo chính xác với tổng STW GC pauses**.

Đọc những dòng kiểu sau từ GC log (chỉ là **mẫu cấu trúc, số liệu thay đổi theo JVM**):

```text
[2.123s][info][gc] GC(4) Pause Young (Normal) (G1 Evacuation Pause) ... 6.214ms
[4.211s][info][gc] GC(5) Pause Young (Mixed) (G1 Evacuation Pause) ... 12.074ms
[7.102s][info][gc] GC(6) Pause Full (...) ... 134.892ms
```

Từ `Pause` và con số duration, nhóm theo loại collection, tính count, sum, p95, p99 và max trong **đúng cửa sổ benchmark**. Không ghép lẫn những lần GC xảy ra trước warmup hay sau thời gian đo nếu mục tiêu là so sánh pha steady state.

Với một mẫu nhỏ, p99 có thể gần bằng max và không ổn định. Cần đủ số pause/số run hoặc báo phân vị kèm sample count thay vì cố vẽ một kết luận có vẻ chính xác.

## 6. Đo phân bố cấp phát — object size không đồng nghĩa NUMA placement

Đây là phần rất dễ nhầm vì có nhiều nghĩa của từ **allocation distribution**.

### 6.1. Phân bố theo kích thước yêu cầu

Nếu workload cố ý tạo các mảng `byte[256]`, `byte[1024]`, `byte[8192]` và `byte[16384]`, code có thể **đếm số thao tác cấp phát theo nhóm**.

```text
Nhóm          Số lần     Payload được yêu cầu
256 bytes      70%       70 × 256
1024 bytes     20%       20 × 1024
8192 bytes      9%        9 × 8192
16384 bytes     1%        1 × 16384
```

Các tỷ lệ là **ví dụ phân phối do workload định nghĩa**. Đặc biệt, `requestedPayloadBytes = số lần × kích thước mảng` **không phải** tổng Java heap bytes cấp phát: array header, padding/alignment, TLAB, scalar replacement, JIT, JFR/profiler overhead và các object phụ trợ có thể làm số thực khác.

Đếm theo **số object** và theo **byte** thường cho ranking khác nhau: rất nhiều object nhỏ có thể có số lượng cao nhưng chiếm ít byte hơn một nhóm object lớn.

### 6.2. Phân bố theo class/call stack/thread bằng JFR

JFR có các event/khả năng như `jdk.ObjectAllocationSample` để lấy mẫu object allocation pressure (trên các JVM hỗ trợ). Phân tích theo:

- `objectClass`: loại object được cấp phát.
- `weight` của sample: **trọng số ước lượng**, dùng khi tổng hợp phân bố allocation pressure; không phải kích thước chính xác của object được lấy mẫu.
- Stack trace: vị trí code làm phát sinh allocation.
- Thread: nhóm công việc chịu trách nhiệm cấp phát.

**Không đếm số JFR allocation samples rồi tuyên bố đó là tổng số object đã cấp phát.** Sampling có bias và giới hạn tốc độ; so sánh phải dùng cấu hình lấy mẫu nhất quán.

### 6.3. Phân bố theo NUMA node bằng OS

`numastat -p <PID>` trên Linux cho thông tin **phân bố trang bộ nhớ** của tiến trình theo NUMA node; `numactl --hardware` mô tả topology. Cần phân biệt:

- Đây **không phải** số lượng Java object cấp phát trên từng node.
- Số liệu OS có thể bao gồm Java heap, metadata, code cache, native allocations, stack và memory mappings khác.
- “Nhiều trang ở node 0” **không tự đồng nghĩa** truy cập local tốt: phải xem thread chạy trên node nào, CPU affinity, remote accesses, page migration và chính sách của kernel.
- Cùng tổng memory placement có thể tạo latency rất khác nếu luồng di chuyển node thường xuyên.

Vì vậy muốn biết **G1/NUMA có ích không**, kết hợp app throughput/latency, GC pause, JFR allocation patterns **và** OS placement/remote-access counters phù hợp. Không dựa vào duy nhất `numastat`.

## 7. Chương trình Java 17+ độc lập: tạo tải cấp phát, đo throughput và latency mẫu

Ví dụ này tạo một workload nhỏ **để học phương pháp đo**, không phải benchmark có đủ độ tin cậy để kết luận về production NUMA. Nhiều worker thread liên tục tạo mảng theo phân bố 70% nhỏ, 20% vừa, 9% lớn, 1% rất lớn. Chương trình:

- Đếm số operation hoàn tất và tính ops/s từ thời gian wall-clock.
- Lấy mẫu một thao tác trong mỗi 127 operation bằng `System.nanoTime()`, sau đó in p50/p95/p99 của **allocation-operation sample**, không phải request latency.
- Thống kê `requestedPayloadBytes` theo nhóm kích thước, không tự gán thành actual allocation bytes của JVM.
- Lấy mức chênh `GarbageCollectorMXBean` về số lần collect và collection time gần đúng; **không** tuyên bố đó là bảng phân vị STW.
- Giới hạn input (số thread và số giây) để tránh chạy vô hạn; giữ các mảng gần đây trong một ring buffer, nhằm tạo workload có cấp phát và dữ liệu còn được sử dụng.

Tạo tệp **`G1NumaMetricsDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class G1NumaMetricsDemo {
    private static final int[] SIZES = {256, 1024, 8192, 16384};
    private static final int SAMPLE_LIMIT = 16000;

    private G1NumaMetricsDemo() {
    }

    private record Result(
            long operations,
            long requestedPayloadBytes,
            long[] counts,
            long[] samplesNs,
            int sampleCount,
            long checksum) {
    }

    private static int groupFor(long operation) {
        int v = (int) (operation % 100);
        return v < 70 ? 0 : v < 90 ? 1 : v < 99 ? 2 : 3;
    }

    private static Result runWorker(int seconds) {
        long[] counts = new long[SIZES.length];
        long[] samples = new long[SAMPLE_LIMIT];
        int sampleCount = 0;
        long operations = 0;
        long requestedBytes = 0;
        byte[][] recent = new byte[128][];
        long checksum = 0;

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(seconds);

        while (System.nanoTime() < deadline) {
            int group = groupFor(operations);
            boolean sample = operations % 127 == 0
                    && sampleCount < SAMPLE_LIMIT;
            long started = sample ? System.nanoTime() : 0L;

            byte[] array = new byte[SIZES[group]];
            array[0] = (byte) group;
            array[array.length - 1] = (byte) operations;
            recent[(int) (operations & 127)] = array;

            checksum += (array[0] & 0xff)
                    + (array[array.length - 1] & 0xff);
            counts[group]++;
            requestedBytes += array.length;
            operations++;

            if (sample) {
                samples[sampleCount++] = System.nanoTime() - started;
            }
        }

        for (byte[] array : recent) {
            if (array != null) {
                checksum += array.length;
            }
        }
        return new Result(operations, requestedBytes,
                counts, samples, sampleCount, checksum);
    }

    private static long[] gcTotals() {
        long counts = 0;
        long millis = 0;
        boolean countAvailable = false;
        boolean timeAvailable = false;

        for (GarbageCollectorMXBean bean
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            long c = bean.getCollectionCount();
            long t = bean.getCollectionTime();
            if (c >= 0) {
                counts += c;
                countAvailable = true;
            }
            if (t >= 0) {
                millis += t;
                timeAvailable = true;
            }
        }

        return new long[] {
                countAvailable ? counts : -1,
                timeAvailable ? millis : -1
        };
    }

    private static long delta(long before, long after) {
        return before < 0 || after < 0 ? -1 : after - before;
    }

    private static double percentileMs(
            List<Long> sortedSamples, double percentile) {
        if (sortedSamples.isEmpty()) {
            return Double.NaN;
        }
        int index = (int) Math.ceil(
                percentile * sortedSamples.size()) - 1;
        return sortedSamples.get(Math.max(0, index)) / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 2) {
            throw new IllegalArgumentException(
                    "Usage: G1NumaMetricsDemo [threads] [seconds]");
        }

        int threads = args.length >= 1
                ? Integer.parseInt(args[0]) : 2;
        int seconds = args.length >= 2
                ? Integer.parseInt(args[1]) : 5;
        if (threads < 1 || threads > 16
                || seconds < 1 || seconds > 60) {
            throw new IllegalArgumentException(
                    "threads=1..16, seconds=1..60");
        }

        ExecutorService executor =
                Executors.newFixedThreadPool(threads);
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<Result>> futures = new ArrayList<>();
            for (int i = 0; i < threads; i++) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return runWorker(seconds);
                }));
            }

            ready.await();
            long[] before = gcTotals();
            long begin = System.nanoTime();
            start.countDown();

            long totalOps = 0;
            long totalPayloadBytes = 0;
            long checksum = 0;
            long[] buckets = new long[SIZES.length];
            List<Long> samples = new ArrayList<>();

            for (Future<Result> future : futures) {
                Result result = future.get();
                totalOps += result.operations();
                totalPayloadBytes += result.requestedPayloadBytes();
                checksum += result.checksum();

                for (int k = 0; k < SIZES.length; k++) {
                    buckets[k] += result.counts()[k];
                }
                for (int k = 0; k < result.sampleCount(); k++) {
                    samples.add(result.samplesNs()[k]);
                }
            }

            double wallSeconds =
                    (System.nanoTime() - begin) / 1_000_000_000.0;
            long[] after = gcTotals();
            Collections.sort(samples);

            System.out.println("threads=" + threads);
            System.out.println("secondsRequested=" + seconds);
            System.out.printf(Locale.ROOT,
                    "throughputOpsPerSecond=%.1f%n",
                    totalOps / wallSeconds);
            System.out.printf(Locale.ROOT,
                    "sampleLatencyMs p50=%.3f p95=%.3f p99=%.3f%n",
                    percentileMs(samples, 0.50),
                    percentileMs(samples, 0.95),
                    percentileMs(samples, 0.99));
            System.out.println("latencySamples=" + samples.size());
            System.out.println("gcCountDeltaApprox="
                    + delta(before[0], after[0]));
            System.out.println("gcCollectionTimeDeltaMsApprox="
                    + delta(before[1], after[1]));
            System.out.println("requestedPayloadBytes="
                    + totalPayloadBytes);
            System.out.println("sizeBytes,operations,payloadBytes");
            for (int k = 0; k < SIZES.length; k++) {
                System.out.println(SIZES[k] + "," + buckets[k]
                        + "," + buckets[k] * SIZES[k]);
            }
            System.out.println("checksum=" + checksum);
        } finally {
            executor.shutdownNow();
        }
    }
}
```

### Biên dịch và chạy

Dùng JDK 17+:

```bash
javac --release 17 G1NumaMetricsDemo.java
java -XX:+UseG1GC -Xms256m -Xmx256m G1NumaMetricsDemo 2 5
```

**Hình dạng stdout khi chạy thành công** (các giá trị đo biến đổi theo máy):

```text
threads=2
secondsRequested=5
throughputOpsPerSecond=<số đo>
sampleLatencyMs p50=<số đo> p95=<số đo> p99=<số đo>
latencySamples=<số mẫu thực>
gcCountDeltaApprox=<số đo hoặc -1>
gcCollectionTimeDeltaMsApprox=<số đo hoặc -1>
requestedPayloadBytes=<số byte>
sizeBytes,operations,payloadBytes
256,<số lần>,<số byte>
1024,<số lần>,<số byte>
8192,<số lần>,<số byte>
16384,<số lần>,<số byte>
checksum=<giá trị tính được>
```

Các ký hiệu `<...>` ở **minh họa stdout** là ô mô tả kết quả do runtime tạo ra, không phải output literal hay số đo giả. **Không thể dự đoán chính xác** throughput, p99, GC count, sample count và checksum trước khi chạy trên phần cứng cụ thể. Hai dòng `threads=2`, `secondsRequested=5` và header CSV cố định với lệnh mẫu; các giá trị còn lại là đo thực.

### Giới hạn của demo

- `sampleLatencyMs` là latency của **một thao tác cấp phát và cập nhật số đếm nội bộ được lấy mẫu**, không phải end-to-end request latency của ứng dụng thật. Việc lấy mẫu mỗi 127 operation giúp tránh đo mọi operation, nhưng vẫn có overhead và sampling bias.
- `requestedPayloadBytes` chỉ cộng **kích thước payload được yêu cầu** của những mảng do demo tự tạo, **không** bao gồm header/padding và các object JVM khác. Nó không phải giá trị tương đương với số byte allocation do profiler/JFR ước lượng.
- `gcCollectionTimeDeltaMsApprox` dựa trên `GarbageCollectorMXBean`, có thể là chỉ số gần đúng hoặc không được hỗ trợ (trả `-1`). Không lấy số này làm bảng STW pause p99; phân tích GC pause phải dựa vào GC log/JFR.
- `System.nanoTime()` không bảo đảm một thao tác được đo không bị OS scheduler, safepoint hoặc JIT ảnh hưởng. Thời gian đo ngắn và tải nhân tạo **không thể đại diện** cho production.
- Số thread và khoảng chạy được giới hạn nhằm tránh benchmark vô tình chiếm tài nguyên quá lâu. Với production bench, cần warmup, workload thật, nhiều lần lặp và chính sách quan sát phù hợp.

## 8. Bật GC Unified Logging để đo pause và hành vi G1

**Không** dùng các cờ như `-XX:+PrintGCDetails` hoặc `-XX:+PrintGCTimeStamps` làm cách thu thập chính trong JDK hiện đại. Cơ chế được hỗ trợ là **Unified Logging `-Xlog`**.

Ví dụ trên Linux/macOS (các tham số JVM đứng **trước** main class):

```bash
java -XX:+UseG1GC -Xms256m -Xmx256m \
  '-Xlog:gc*,safepoint:file=g1-%p.log:uptime,level,tags:filecount=5,filesize=20M' \
  G1NumaMetricsDemo 2 5
```

Với Windows PowerShell, dùng **một lệnh trên một dòng**:

```powershell
java -XX:+UseG1GC -Xms256m -Xmx256m '-Xlog:gc*,safepoint:file=g1-%p.log:uptime,level,tags:filecount=5,filesize=20M' G1NumaMetricsDemo 2 5
```

Giải thích:

- `-XX:+UseG1GC`: chọn G1 rõ ràng để so sánh giữa các lần chạy.
- `-Xms256m -Xmx256m`: giữ giới hạn heap thống nhất trong ví dụ; **không phải** kích thước đủ lớn để kiểm thử NUMA production.
- `gc*`: lấy các thông tin GC, gồm subtype tags phù hợp ở mức info.
- `safepoint`: cung cấp thông tin về safepoint, hữu ích khi tìm khoảng dừng không chỉ từ GC.
- `file=g1-%p.log`: tên file bao gồm PID do JVM thay thế, tránh nhầm log của những lần chạy.
- `filecount` và `filesize`: giới hạn số file và kích thước log theo cơ chế rotation.
- `-Xlog:gc+phases=debug` có thể bật riêng khi cần phân tích pha nào của G1 chiếm nhiều thời gian; mức debug tạo thêm dữ liệu và overhead.

Dòng `Pause Young` hoặc `Pause Full` và duration cuối dòng là nguồn để thống kê **pause frequency và distribution**. Không coi mọi dòng log chứa chữ GC là một pause riêng, vì một GC ID có thể có nhiều dòng liên quan đến phase/cpu/heap.

### Khuyến nghị khi phân tích log

1. Ghi nhận timestamp bắt đầu/kết thúc **cửa sổ workload**; bỏ qua các pause ở giai đoạn warmup nếu đang đo steady state.
2. Chỉ lấy các dòng **mô tả STW pause**; phân biệt young/mixed/remark/cleanup/full.
3. Tính count, total, mean, p50, p95, p99, max theo kiểu pause và toàn bộ pause.
4. Kiểm tra `gc+cpu` với `User`, `Sys`, `Real` để phân biệt CPU sử dụng, OS stalls và thời gian thực.
5. Kiểm tra `gc+heap` (eden/survivor/old/humongous regions) và G1 region sizing để tìm áp lực heap.
6. Không nhầm thời gian các pha concurrent với STW pauses; nên dùng tên event/tag rõ ràng.
7. Không so sánh log giữa các JDK version bằng một regex quá cứng; format có thể thay đổi. Đối với phân tích tự động dài hạn, dùng parser hoặc JFR event metadata tương thích với bản JDK.

## 9. Bật JFR để xem phân bố cấp phát theo class và call stack

JFR là công cụ chính thức của JDK phù hợp để lấy mẫu event về hoạt động JVM mà không cần sửa toàn bộ code nghiệp vụ.

Chạy một thử nghiệm có JFR:

```bash
java -XX:+UseG1GC -Xms256m -Xmx256m \
  '-XX:StartFlightRecording=settings=profile,filename=g1-profile.jfr,dumponexit=true' \
  G1NumaMetricsDemo 2 5
```

Nếu dùng Windows PowerShell, viết tham số trên một dòng; cách quote khác nhau theo shell, nhưng nội dung JVM option không thay đổi.

Sau khi JVM kết thúc và file JFR được tạo, có thể kiểm tra metadata/event:

```bash
jfr summary g1-profile.jfr
jfr print --events jdk.ObjectAllocationSample g1-profile.jfr
```

Những lệnh này có trong các JDK hiện đại hỗ trợ JFR. Nếu file chưa tồn tại, không tự giả định event bị lỗi: xem liệu recording thực sự đã được khởi động/đóng/dump và kiểm tra quyền ghi. `settings=profile` **không phải** lời hứa mọi event đều được bật giống nhau ở mọi vendor/version; nên kiểm tra `jfr summary` và cấu hình JFR của runtime.

Với `jdk.ObjectAllocationSample`, các field như `objectClass` và `weight` giúp phân tích **allocation pressure ước lượng**. Phân loại theo class và stack trace (nếu được ghi). **Không lấy số event = số object** hoặc gộp các `weight` rồi tuyên bố độ chính xác tuyệt đối, vì đây là dữ liệu sampling.

Đối với workload thực, [JDK Mission Control (JMC)](https://www.oracle.com/java/technologies/jdk-mission-control.html) giúp nhìn flame graph, allocation hot spots, GC pauses và timeline. Công cụ phân tích khác có thể thay thế nếu hiểu được metadata JFR. **JFR không trực tiếp báo “mỗi object nằm ở NUMA node X”** trong mọi JVM; cần kết hợp OS placement metrics.

## 10. Đo phân bố bộ nhớ theo NUMA node trên máy Linux

Trên một hệ thống Linux hỗ trợ NUMA, kiểm tra topology:

```bash
numactl --hardware
```

Nếu chỉ có **một NUMA node khả dụng**, không có cơ sở cho một A/B test locality nhiều node tương ứng. Có thể chạy workload để học GC nhưng không tuyên bố một cải thiện NUMA.

Với tiến trình Java đang sống đủ lâu (ví dụ chạy benchmark 60 giây thay cho 5 giây), dùng một terminal khác:

```bash
numastat -p <PID>
```

Thay `<PID>` bằng PID thật. `numastat` có thể hiển thị phân bố RAM của tiến trình theo node. Đây là dữ liệu **page residency** ở cấp OS, không phải chính xác số object được tạo từ từng câu lệnh `new`.

Nếu cần thêm thông tin remote accesses hoặc CPU affinity, dùng công cụ chuyên biệt của Linux/perf/hardware counters theo quyền và cấu hình cho phép; một node có nhiều MB không tự chứng minh thấp hay cao về latency. Trường hợp dùng `numactl --cpunodebind` hoặc `--membind`, phải hiểu rằng **đang thay đổi chính sách OS** và có thể làm nhiễu kết quả so sánh bật/tắt NUMA-aware G1.

Cần lưu ý **JEP 345**: tối ưu NUMA-aware G1 tập trung vào cấp phát young region và placement gần node của thread; old/humongous behavior có cơ chế phân bổ riêng và thay đổi theo HotSpot version. Không giả định `-XX:+UseNUMA` sẽ đưa **mọi byte** của một tiến trình vào đúng một node.

## 11. A/B test NUMA với G1: thiết kế để kết luận có căn cứ

**Trước tiên kiểm tra hỗ trợ trên JDK/runtime đang sử dụng**. Oracle documentation cho thấy mặc định `-XX:+UseNUMA` có thể phụ thuộc collector và phiên bản; đừng giả định giá trị mặc định là cố định trên mọi JDK, và đừng suy từ tên option rằng NUMA có tác dụng khi topology chỉ có một node.

Để có baseline rõ ràng, chủ động tắt NUMA optimization của JVM:

```bash
java -XX:+UseG1GC -XX:-UseNUMA -Xms256m -Xmx256m \
  '-Xlog:gc*,safepoint:file=baseline-%p.log:uptime,level,tags:filecount=5,filesize=20M' \
  G1NumaMetricsDemo 2 5
```

Và cấu hình so sánh (chỉ khi hệ thống/JVM hỗ trợ NUMA thực sự):

```bash
java -XX:+UseG1GC -XX:+UseNUMA -Xms256m -Xmx256m \
  '-Xlog:gc*,numa*=debug,safepoint:file=numa-%p.log:uptime,level,tags:filecount=5,filesize=20M' \
  G1NumaMetricsDemo 2 5
```

Dạng trên dùng cú pháp dòng nối của **shell POSIX**. Windows PowerShell đặt cả lệnh trên một dòng hoặc sử dụng cách xuống dòng phù hợp của PowerShell. Với GC logging NUMA, xác nhận tag/level thực tế bằng `java -Xlog:help` trên JDK cụ thể. Nếu JVM không nhận một tag/flag, điều đó là **điểm cần xử lý trong môi trường**, không được âm thầm bỏ log và vẫn kết luận NUMA đã hoạt động.

Đây chỉ là **thí nghiệm thực hành nhỏ**: heap 256 MiB, hai threads, năm giây có thể không tạo khác biệt NUMA đo được. Một benchmark production phải dùng kích thước heap, số threads, load generator và thời lượng **thực của ứng dụng trên phần cứng NUMA**.

### Biến cần giữ bất biến

| Nhóm | Điều phải giữ giữa baseline và NUMA-enabled |
| --- | --- |
| Máy | Cùng CPU sockets, NUMA topology, RAM, kernel, BIOS, power governor |
| JVM | Cùng JDK build, vendor, GC, CPU/thread limits, heap, JIT, log/JFR settings |
| Ứng dụng | Cùng binary, input data, dependency, batch size, allocation pattern |
| Tải | Cùng lượng request đến, concurrency, mix request và tỷ lệ lỗi |
| Môi trường | Cùng CPU affinity/cgroup/memory policy; hạn chế tiến trình nền |
| Đo | Cùng warmup, steady-state, duration, sampling rate, histograms và clock |
| Phân tích | Cùng cách loại warmup, loại pause, phân vị, đơn vị và số run |

Trong hai lệnh minh họa ở trên, cấu hình logging **khác** ở chi tiết `numa*=debug` để quan sát NUMA. Khi đo throughput/latency chính thức, nên dùng **cùng mức logging** ở cả hai nhánh hoặc thực hiện lượt diagnostic riêng để tránh overhead logging tạo sai lệch.

### Tối thiểu một quy trình đáng tin

1. Xác nhận phần cứng có nhiều NUMA node và phiên bản JVM hỗ trợ option.
2. Dùng cấu hình mặc định G1 tương đối ổn, chỉ đặt `-Xmx` và những giới hạn thật sự cần. Không tùy ý ép `-Xmn` hoặc `-XX:NewRatio` làm mất tính thích ứng young-gen trước khi đo.
3. Warmup đủ cho class loading và JIT; đặt steady-state benchmark sau warmup.
4. Chạy **ít nhất vài lần lặp** mỗi cấu hình, đổi thứ tự thử nghiệm (ví dụ A–B–B–A) để giảm bias do thời gian/thermal drift.
5. Thu app throughput, p50/p95/p99 end-to-end, lỗi/timeout, GC pause distribution, GC CPU, JFR allocation, OS NUMA placement.
6. Báo median/trung bình giữa các run và **độ phân tán**, không chỉ một con số tốt nhất.
7. Nếu NUMA cải thiện throughput nhưng làm p99 request latency vượt SLO, đánh giá theo mục tiêu kinh doanh thật.
8. Nếu chỉ thay đổi vài phần trăm mà noise lớn hơn thay đổi, báo **chưa đủ bằng chứng**; không công bố thắng cuộc.

## 12. Cách diễn giải khi các chỉ số xung đột

| Tình huống quan sát | Giải thích khả dĩ | Hành động kiểm tra tiếp |
| --- | --- | --- |
| Throughput tăng, p99 xấu đi | GC CPU, contention, queueing hoặc đuôi GC nặng | Phân tích latency theo phase và GC pause timeline |
| GC count giảm, max pause tăng | Mỗi lần thu gom làm nhiều việc hơn | So p95/p99/max và loại pause, không chỉ count |
| Throughput giảm, pause giảm | Collector đổi throughput lấy latency hoặc workload khác | Xem throughput SLO và CPU/memory budget |
| JFR sample nhiều ở byte[] | Workload/tầng xử lý cấp phát nhiều byte arrays | Nhóm theo `weight`, stack trace và thời gian |
| `numastat` phân bố RAM đều | OS interleave hoặc placement theo policy | Kiểm tra CPU binding, truy cập remote, topology |
| NUMA enabled không đổi hiệu năng | Một node, heap nhỏ, CPU cache/locality đủ tốt hoặc workload không memory-bound | Xác minh option đã active và hardware |
| GC log xuất hiện Full GC | Heap pressure, evacuation failure, humongous regions hoặc nguyên nhân khác | Đọc GC cause, occupancy, allocation pattern |
| App latency spike nhưng GC không pause | OS scheduling, lock, I/O, network hoặc downstream | Tracing, thread dump, OS metrics |

Các nguyên nhân trong bảng là **giả thuyết cần kiểm tra**, không phải quy luật một-một.

## 13. Cẩn thận khi chỉnh tham số G1

Sau khi có baseline đáng tin, nếu phát hiện nguyên nhân liên quan GC, bạn mới cân nhắc tuning. Các lựa chọn thường gặp:

- `-XX:MaxGCPauseMillis=N`: mục tiêu thời gian dừng **mềm**, không phải SLA. Đặt quá thấp có thể làm G1 thu gom thường xuyên hơn hoặc ảnh hưởng throughput.
- `-Xmx`: giới hạn tối đa Java heap, cần tính cùng container memory limit và native memory.
- `-Xms`: mức heap khởi tạo; đặt bằng `-Xmx` có thể giảm resize ở một số workload, nhưng thay đổi footprint/commit behavior và cần đo tác động.
- `-XX:+AlwaysPreTouch`: chạm trước heap pages khi khởi động, có thể thay startup time, NUMA placement và page fault pattern; chỉ thử có chủ đích, không coi là bắt buộc.
- `-XX:G1HeapRegionSize`: kiểm tra nếu workload có **humongous objects** và fragmentation; không chọn giá trị theo cảm tính, vì region size ảnh hưởng nhiều heuristic.
- `-Xmn` và `-XX:NewRatio`: **tránh ép cứng** young generation khi đang sử dụng G1 pause prediction, vì nó làm giảm khả năng tự điều chỉnh theo mục tiêu pause.
- `-XX:+UseNUMA`: chỉ là một yếu tố trong cả hệ thống; so sánh trên topology thật với cùng CPU/memory policy.

JDK mới có thể thay đổi default và heuristic; đọc **G1 Tuning Guide của phiên bản đang triển khai**, thay vì sao chép một bộ tuning flag của Java 8/11 rồi coi là tối ưu cho Java hiện tại.

## 14. Những sai lầm phổ biến

**Sai lầm 1 — Đo GC “throughput” rồi suy ra service throughput.** GC runtime không biết request thành công; cần bộ đếm request/operation ở tầng ứng dụng và load generator.

**Sai lầm 2 — Báo mean latency nhưng không xem p99.** Một đuôi chậm có thể ảnh hưởng người dùng dù trung bình tốt. Cần histogram và đủ mẫu, đặc biệt khi tỷ lệ lỗi/timeout thay đổi.

**Sai lầm 3 — Dùng `MaxGCPauseMillis` như giới hạn cứng.** G1 cố đạt mục tiêu theo xác suất, không phải real-time GC, không đảm bảo mọi STW pause dưới cấu hình.

**Sai lầm 4 — Tưởng `GarbageCollectorMXBean.getCollectionTime()` là tổng STW pause tuyệt đối chính xác.** MXBean cung cấp số liệu tổng hợp do JVM định nghĩa, có giới hạn độ chính xác; dùng GC log/JFR event để phân tích pause distribution.

**Sai lầm 5 — Cộng số JFR samples rồi gọi đó là tổng object cấp phát.** Allocation sampling không ghi mọi allocation. Dùng metadata/trọng số thích hợp, xem đây là ước lượng.

**Sai lầm 6 — Coi `requestedPayloadBytes` trong ví dụ là bytes JVM đã cấp phát.** Mảng có header/padding, JIT có thể tối ưu; đo thực cần profiler/counter đúng scope.

**Sai lầm 7 — Coi `numastat -p` là thống kê object theo class và node.** Đây là số liệu OS page placement, không phân giải đến object Java.

**Sai lầm 8 — Bật `UseNUMA` trên máy chỉ có một node rồi báo lợi ích.** Kiểm tra topology và hỗ trợ runtime, cả khi chạy trong container.

**Sai lầm 9 — Thay nhiều biến một lúc.** Nếu đổi collector, heap, thread count và NUMA cùng lượt thì không thể quy kết nguyên nhân.

**Sai lầm 10 — Benchmark một lần, không warmup.** JIT, class loading, filesystem cache, CPU temperature và background load có thể tạo khác biệt giả.

**Sai lầm 11 — Dùng GC logging flag cũ không còn được khuyến nghị.** Dùng Unified Logging `-Xlog` và JFR được hỗ trợ trên JDK 17+, không ép các cờ chẩn đoán legacy.

**Sai lầm 12 — Cho rằng nhiều local pages nghĩa là request latency thấp.** NUMA performance còn phụ thuộc threads chạy ở CPU nào, bộ nhớ nào được truy cập nhiều, cache locality và băng thông.

## 15. Checklist nghiệm thu và bài tập

### Checklist benchmark

- [ ] Xác minh `java -version`/build và collector đang dùng.
- [ ] Xác minh NUMA topology bằng OS và số node khả dụng trong process/container.
- [ ] Định nghĩa workload hữu ích, thời gian warmup và steady-state.
- [ ] Thu throughput và error rate thực tế của app.
- [ ] Thu end-to-end p50/p95/p99, không chỉ average.
- [ ] Thu GC pause count/sum/p95/p99/max từ GC log/JFR.
- [ ] Thu JFR allocation sample có trọng số hoặc profiler có phương pháp rõ.
- [ ] Thu OS memory placement/remote access nếu mục tiêu là NUMA.
- [ ] Giữ heap, OS, load, tool overhead và logging giống nhau.
- [ ] Chạy nhiều lần, báo biến thiên và không bỏ những run xấu không có lý do.
- [ ] Không kết luận tối ưu nếu khác biệt nằm trong noise.
- [ ] Ghi rõ những chỉ số **không thể suy ra trực tiếp** từ demo.

### Bài 1 — Chạy chương trình

Biên dịch `G1NumaMetricsDemo.java` và chạy `G1NumaMetricsDemo 2 5`. Ghi lại throughput, sample p50/p95/p99 và bảng CSV requested payload. Giải thích vì sao số lượng theo group có tỷ lệ gần 70/20/9/1 nhưng **byte distribution** không giống tỷ lệ đó.

### Bài 2 — Đo pause thật

Chạy lại với `-Xlog:gc*,safepoint`. Lấy đúng các dòng `Pause` trong cửa sổ steady-state và tính count/sum/max; khi có đủ dữ liệu, bổ sung p95/p99. So sánh với `gcCollectionTimeDeltaMsApprox` trong stdout và giải thích vì sao chúng **không bắt buộc trùng nhau**.

### Bài 3 — JFR allocation

Bật `settings=profile` và phân tích `jdk.ObjectAllocationSample`. Tìm class/call stack có nhiều allocation pressure. So sánh với histogram do demo tự đếm; ghi rõ **một bên là sampled JVM allocation, một bên là requested payload của workload**.

### Bài 4 — NUMA A/B

Trên Linux có ít nhất hai NUMA node, chạy `-XX:-UseNUMA` và `-XX:+UseNUMA` với cùng runtime, heap và tải. Mỗi cấu hình lặp lại ít nhất ba lần; báo bảng throughput, latency p99, tổng GC pause và `numastat`. Nếu môi trường chỉ có một node, ghi **không đủ điều kiện để đánh giá locality NUMA**, thay vì cố tạo kết luận.

### Bài 5 — Phân tích xung đột

Nếu B tăng throughput 3% nhưng p99 xấu 25%, bạn có chọn B không? Trả lời bằng **SLO và độ tin cậy của mẫu**, không dựa vào một metric. Nêu thêm loại dữ liệu cần thu (thread scheduling, GC pause timeline, allocation hotspots).

### Bài 6 — Thử một tham số G1

Chỉ khi có GC pause bottleneck đã được xác minh, thử thay **một** tham số như `-XX:MaxGCPauseMillis`, giữ các yếu tố khác, so sánh nhiều run và xem tác động tới cả throughput lẫn p99. Không dùng một magic flag để “sửa mọi vấn đề”.

**Tiêu chí hoàn thành:** Người học đo và phân biệt được bốn nhóm chỉ số; báo scope/nguồn/đơn vị rõ ràng; không lẫn operation latency với request latency, không lẫn JFR samples với số cấp phát thật, không lẫn page placement với object distribution và thiết kế được một A/B test NUMA có kiểm soát.

## 16. Tài liệu chính thức và hiện hành

- [Oracle Java SE 26 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html): cơ chế region, young/old generations, pause targets và công việc concurrent.
- [Oracle Java SE 26 — G1 GC Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html): throughput/latency trade-off, GC pause phases và hướng tuning hiện hành.
- [Oracle Java SE 26 — `java` command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): Unified Logging `-Xlog`, collector flags, heap/NUMA options.
- [Oracle Java SE 17 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): `getCollectionCount`, `getCollectionTime` và giới hạn dữ liệu.
- [Oracle Java SE 17 — JFR](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `jfr summary`, `jfr print` và phân tích recording.
- [OpenJDK JEP 345 — NUMA-Aware Memory Allocation for G1](https://openjdk.org/jeps/345): nền tảng NUMA-aware G1 từ Java 14.
- [OpenJDK JFR event metadata](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/jfr/metadata/metadata.xml): `jdk.ObjectAllocationSample`, `objectClass` và `weight`; cần kiểm tra metadata trên runtime đang chạy.
- [Oracle Java SE 26 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/26/jfapi/): thu thập event hỗ trợ chẩn đoán.

**Ghi nhớ:** Trong **G1 và NUMA**, không có một con số duy nhất quyết định hiệu năng. Hãy đo **thông lượng thật**, **độ trễ theo phân vị**, **STW pause distribution**, **allocation pressure**, và **NUMA locality** theo đúng nguồn dữ liệu; chỉ bật/tối ưu NUMA khi phần cứng phù hợp và phép so sánh thực tế cho thấy lợi ích đủ lớn để vượt độ nhiễu.