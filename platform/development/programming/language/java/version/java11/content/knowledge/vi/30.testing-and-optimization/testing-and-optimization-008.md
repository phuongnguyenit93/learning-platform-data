# Java 11 — So sánh allocation, throughput và độ trễ sau warm-up

**Chủ đề:** Java 11 → **Kiểm thử và tối ưu**. Bài học này chỉ cách thiết kế và thực thi một phép so sánh có thể lặp lại giữa **lượng heap cấp phát cho mỗi thao tác (allocation, B/op)**, **thông lượng (throughput, ops/s)** và **độ trễ (latency, ns/op; p50/p95/p99)** *sau giai đoạn warm-up*. Một phương án có thể cấp phát ít byte hơn trên mỗi thao tác nhưng vẫn tạo **nhiều MB/s hơn** nếu thông lượng tăng mạnh. Vì vậy, không có một con số đơn lẻ đủ để kết luận “đã tối ưu tốt”.

**Giới hạn kiến thức:** Nội dung sử dụng cách đo và công cụ **vẫn áp dụng hiện nay**: Java 11, `System.nanoTime()`, `com.sun.management.ThreadMXBean` (khi JVM hỗ trợ), JMH 1.37, JFR, Unified JVM Logging và load test có guardrails. Không sử dụng API Java chỉ có trong JDK mới để làm ví dụ chạy với `--release 11`; không khuyến nghị phương pháp/cờ GC profiling legacy. JMH 1.37 là phiên bản public đã được kiểm tra cho ví dụ; nếu nâng JMH, phải kiểm tương thích và chạy lại phép đo.

**Mục tiêu:** Bạn sẽ biết phân biệt ba metric, chọn đơn vị `op`, warm up cả baseline và candidate, kiểm tra output tương đương, đo mỗi metric theo đúng phương pháp, dùng nhiều iterations/forks, đọc kết quả JMH, nhận diện timer resolution/coordinated omission, lập bảng có uncertainty, và quyết định có nên triển khai tối ưu theo tác động trên request thật.

## 1. Ba mục tiêu không đồng nghĩa

Giả sử service cần tạo mã ticket từ số nguyên 0–9999 theo định dạng `TKT-0000` đến `TKT-9999`. Ta có thể triển khai bằng `String.format` hoặc `StringBuilder` có zero padding. Cả hai làm **cùng nhiệm vụ**, nhưng tạo lượng objects và dùng CPU khác nhau.

Ba câu hỏi tương ứng:

| Chỉ số | Câu hỏi | Đơn vị thường dùng | Hướng mong muốn |
| --- | --- | --- | --- |
| **Allocation per op** | Mỗi ticket làm JVM cấp phát bao nhiêu bytes trên heap? | `B/op` hoặc `B/ticket`. | Càng thấp càng tốt nếu không đánh đổi chức năng. |
| **Throughput** | Sau warm-up, một worker/JVM xử lý được bao nhiêu ticket mỗi giây? | `ops/s`. | Cao hơn ở cùng điều kiện khi phù hợp nhu cầu. |
| **Latency** | Mỗi lần tạo ticket mất bao lâu? Phần đuôi phân phối ra sao? | `ns/op`, `µs/op`, p50/p95/p99. | Thấp hơn, đặc biệt ở tail latency của workload thật. |

**Không suy “B/op giảm 50% thì throughput tăng 2×”**. Allocation có thể không là bottleneck: chương trình còn tiêu CPU, truy cập cache, sync/locks, I/O, GC, serialization. Tương tự, throughput tăng không đảm bảo p99 giảm nếu đổi batching/queueing.

### 1.1. Throughput và latency có mối quan hệ gì?

Trong trường hợp lý tưởng **một thread thực hiện tuần tự, mỗi lúc chỉ một operation và không có thời gian chờ khác**, throughput có thể xấp xỉ nghịch đảo thời gian trung bình cho mỗi operation:

~~~text
ideal ops/s ≈ 1_000_000_000 / mean ns/op
~~~

Nhưng trong service có nhiều threads, queue, I/O hoặc batching, `ops/s` không tương đương `1/p99 latency`. Ví dụ 32 threads có thể đạt throughput cao dù mỗi request chờ network 100ms; queueing khi saturation có thể làm p99 tăng nhanh trong khi throughput gần như không đổi.

### 1.2. B/op khác MB/s

~~~text
allocation rate (B/s) ≈ allocated bytes/op × completed ops/s
~~~

Khi candidate xử lý **nhiều operations/s hơn**, tổng bytes allocated mỗi giây **có thể tăng** dù bytes/op giảm. Để so GC pressure công bằng giữa A/B, có hai chế độ khác nhau:
- **Fixed arrival rate/load:** cùng số operations/s yêu cầu; so allocation rate/GC và latency ở cùng tải.
- **Maximum throughput:** mỗi variant chạy hết năng lực; so B/op, throughput cực đại và MB/s **trong điều kiện đã thay đổi lượng work/s**.

Không so MB/s của hai nhánh tại throughput cực đại rồi gọi số thấp hơn là “hiệu quả hơn mỗi ticket”; phải có `B/op`.

## 2. Warm-up là gì, không phải “chạy vài lần cho đẹp”?

Java chạy với JIT compiler có các giai đoạn class loading, interpreter, profiling, tiered compilation, deoptimization và steady-state. Warm-up là bước thực thi workload **trước khi thu samples chính** để các chi phí khởi tạo và tối ưu hóa đầu đời không làm lệch phép so.

~~~text
JVM start
 |-- class loading --|-- interpreted/tiered code --|-- compiled hot code ------|
        warm-up iterations                          | measurement iterations |
                                                     ^ chỉ đo sau checkpoint
~~~

**Nhưng warm-up không phải bảo đảm tuyệt đối rằng JIT/GC đã đạt “trạng thái ổn định”.** JIT còn có thể compile lại, GC heap state vẫn thay, CPU frequency/thermal effects có thể biến thiên, load background có thể gây nhiễu. Không khẳng định đã steady-state chỉ vì đã chạy một triệu lần; xem trend theo iteration và chạy nhiều independent forks.

### 2.1. Thống nhất warm-up giữa baseline/candidate

- Cùng lượng input, cùng phân phối và cùng mã checksum/response.
- Warm-up **cả hai** variants, không để candidate hưởng code cache/hot state khác baseline.
- Chọn số lần/độ dài warm-up đủ để ổn định trên **JVM đích**, không ép mọi workload dùng đúng 5 iterations.
- Không tính cold-start latency vào số “steady-state latency”; nhưng nếu sản phẩm quan trọng startup/serverless, **đo cold-start riêng**.
- Chạy nhiều forks hoặc thí nghiệm đảo thứ tự A/B để giảm order bias.
- Ghi rõ warm-up measurement protocol; không giấu số lượng iterations đã bỏ.

## 3. Định nghĩa operation và điều kiện tương đương

Ví dụ domain: format ticket ID trong khoảng **0 ≤ id ≤ 9999**. Đầu ra chính xác có 8 ký tự, prefix `TKT-` và bốn chữ số zero-padded.

Baseline dễ đọc:

~~~java
static String baseline(int id) {
    return String.format(Locale.ROOT, "TKT-%04d", id);
}
~~~

Candidate dành riêng cho domain giới hạn 0–9999:

~~~java
static String candidate(int id) {
    StringBuilder b = new StringBuilder(8).append("TKT-");
    if (id < 1000) b.append('0');
    if (id < 100) b.append('0');
    if (id < 10) b.append('0');
    return b.append(id).toString();
}
~~~

Hai đoạn này **là method snippets**; chương trình đầy đủ nằm ở mục 6. Candidate chưa đủ hợp đồng để thay baseline với **giá trị âm, lớn hơn 9999, locale khác, format flags khác hoặc input không phải int**. Vì vậy, testcase phải xác nhận domain chính thức; không thay API công khai chỉ dựa trên microbenchmark.

### 3.1. Correctness trước performance

So từng kết quả `baseline(id).equals(candidate(id))` với toàn bộ 10.000 IDs cho phép. Không chấp nhận cải thiện chỉ vì một nhánh bỏ bước formatting, có output sai, dùng buffer chia sẻ gây race hoặc truncate dữ liệu. Trong service thật phải thêm unit/property/integration tests với giá trị biên, encoding, validation, error path và downstream serialization.

### 3.2. Chọn denominator đúng

Một invocation của JMH ở bài này tạo **một ticket** → `B/op` trùng `B/ticket`. Nếu một benchmark khác xử lý một batch 100 tickets trong mỗi invocation, `gc.alloc.rate.norm` có thể là **B/batch**; muốn B/ticket phải chia cho 100. Đừng lẫn `B/op` của benchmark với `B/request` của endpoint nếu endpoint còn routing, DB, logging và response work.

## 4. Bố trí phép so sánh có đối chứng

| Yếu tố | Baseline A | Candidate B | Quy tắc |
| --- | --- | --- | --- |
| Công việc | `String.format(Locale.ROOT, "TKT-%04d", id)` | `StringBuilder` với zero-padding tương đương. | Chỉ đổi implementation. |
| Input | IDs 0–9999 | Cùng IDs và distribution. | Không đổi workload mix. |
| Output | `TKT-0000`…`TKT-9999` | Kết quả giống từng ID. | Assert trước đo. |
| JDK/VM | Cùng vendor/version và flags. | Cùng. | Ghi `java -version`. |
| Heap/GC | Cùng `-Xms/-Xmx`/collector khi có cấu hình. | Cùng. | GC pressure phải so trên nền chung. |
| Warm-up | Có và ghi số iterations. | Tương tự. | Bỏ kết quả warm-up khỏi report chính. |
| Repetitions | Nhiều windows và JVM forks. | Tương đương. | Ước lượng nhiễu. |
| Metric | B/op, ops/s, p50/p95/p99. | Cùng định nghĩa. | Không thay units/denominator. |
| Guardrails | Correctness, memory, CPU, p99, error rate. | Cùng. | Không đánh đổi vì một metric đẹp. |

**Pre-register decision gate**, ví dụ: giảm allocation ít nhất 15%; throughput không giảm quá 5%; p99 không tăng quá 5% ở tải sản phẩm; chức năng hoàn toàn tương đương. Những con số này **chỉ là ngưỡng minh họa**, phải định nghĩa theo SLO/chi phí hệ thống trước khi chạy; không đổi ngưỡng sau khi nhìn outcome.

## 5. Cách đo các metric trong Java 11

### 5.1. Allocation: `ThreadMXBean`

`com.sun.management.ThreadMXBean` trong module `jdk.management` có `getThreadAllocatedBytes(long id)`: số **byte heap đã allocated xấp xỉ bởi thread được chỉ định**. Lấy hiệu của hai lần đọc:

~~~java
long threadId = Thread.currentThread().getId();
long before = meter.getThreadAllocatedBytes(threadId);
runWorkload();
long after = meter.getThreadAllocatedBytes(threadId);
long allocated = after - before;
double bytesPerOp = (double) allocated / operations;
~~~

**Đoạn minh họa**, `meter` phải được kiểm `isThreadAllocatedMemorySupported()` và bật `setThreadAllocatedMemoryEnabled(true)` khi cần. `getThreadAllocatedBytes` có thể trả **-1** nếu không hỗ trợ, disabled hoặc thread đã chết; phải báo **N/A/UNSUPPORTED** chứ không đổi thành 0 B/op.

Số đo là **allocated bytes**, không phải heap used, live/retained heap hay process RSS. Nó không tự gom allocation từ workers khác. Đừng dùng `Thread.currentThread().threadId()` (API JDK mới hơn) trong chương trình target Java 11; dùng `getId()`.

### 5.2. Throughput: operations / elapsed time

~~~java
long t0 = System.nanoTime();
long checksum = 0;
for (int i = 0; i < operations; i++) {
    checksum += compute(i).hashCode();
}
long elapsedNanos = System.nanoTime() - t0;
double opsPerSec = operations * 1_000_000_000.0 / elapsedNanos;
~~~

Đoạn minh họa. `System.nanoTime()` là clock đo **elapsed duration** trong cùng process, không đồng nghĩa CPU time và không dùng để tạo timestamp có ý nghĩa lịch. Với workloads quá nhỏ, timer overhead/JIT noise ảnh hưởng lớn; đo **batch đủ lớn**, sau warm-up.

### 5.3. Latency: từng operation và percentiles

Nếu có mẫu latencies `l_1, ..., l_n`, ta có thể sort và lấy p50, p95, p99 theo chính sách quantile đã định nghĩa. Nhưng **lấy `nanoTime` trước/sau một method cực nhanh trên Windows/JDK thử có thể cho delta 0 ns** vì độ phân giải/clock quantization. Giá trị 0 **không có nghĩa một ticket được tạo trong 0 ns vật lý**.

Do đó phân biệt:
- **Pilot latency mẫu riêng**: giúp thấy timer granularity/đuôi phân phối, không phải benchmark authoritative.
- **JMH Mode.SampleTime**: sampling theo harness, nhận phân phối và p95/p99 của benchmark invocation, vẫn cần đủ samples/forks.
- **Load-test latency**: end-to-end request duration bao gồm queue/IO/GC/network, đo ở protocol boundary. Đây mới là số gắn với SLO request.

**Cảnh báo quan trọng:** p99 đo bằng JMH đối với `StringBuilder` gọi trong một method **không phải p99 của HTTP endpoint**. Cần đo đúng phạm vi.

## 6. Chương trình Java 11 độc lập đo cả ba metric sau warm-up

Tệp **`WarmupThreeMetrics.java`** sau hoạt động không cần Maven. Nó kiểm đầy đủ 10.000 outputs, warm-up hai variants, đo median B/op và throughput trên 7 windows (40.000 operations mỗi window), rồi thu 4.096 samples latency mỗi variant để minh họa percentiles. Thứ tự A/B **đảo theo vòng**; số latency đo theo từng operation có giới hạn clock như đã nói.

~~~java
import com.sun.management.ThreadMXBean;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Locale;

public final class WarmupThreeMetrics {
    private static final int MAX_ID = 10_000;
    private static final int WARMUP_ROUNDS = 4;
    private static final int MEASURE_ROUNDS = 7;
    private static final int OPERATIONS_PER_ROUND = 40_000;
    private static final int LATENCY_SAMPLES = 4_096;
    private static volatile long sink;

    private WarmupThreeMetrics() {}

    static String baseline(int id) {
        return String.format(Locale.ROOT, "TKT-%04d", id);
    }

    static String candidate(int id) {
        StringBuilder builder = new StringBuilder(8).append("TKT-");
        if (id < 1000) builder.append('0');
        if (id < 100) builder.append('0');
        if (id < 10) builder.append('0');
        return builder.append(id).toString();
    }

    private static String format(boolean optimized, int id) {
        return optimized ? candidate(id) : baseline(id);
    }

    static void verifyEquivalent() {
        for (int id = 0; id < MAX_ID; id++) {
            String a = baseline(id);
            String b = candidate(id);
            if (!a.equals(b) || a.length() != 8 ||
                    !a.startsWith("TKT-")) {
                throw new AssertionError("Mismatch for id=" + id);
            }
        }
    }

    static final class Window {
        final long bytes;
        final long nanos;
        final long checksum;
        Window(long bytes, long nanos, long checksum) {
            this.bytes = bytes;
            this.nanos = nanos;
            this.checksum = checksum;
        }
    }

    static Window runWindow(boolean optimized, int round,
                            ThreadMXBean meter, long threadId) {
        long beforeBytes = meter == null
                ? -1 : meter.getThreadAllocatedBytes(threadId);
        long start = System.nanoTime();
        long checksum = 0;
        for (int i = 0; i < OPERATIONS_PER_ROUND; i++) {
            int id = (i * 73 + round) % MAX_ID;
            checksum += format(optimized, id).hashCode();
        }
        long nanos = System.nanoTime() - start;
        long afterBytes = meter == null
                ? -1 : meter.getThreadAllocatedBytes(threadId);
        sink = checksum;
        long allocated = beforeBytes < 0 || afterBytes < beforeBytes
                ? -1 : afterBytes - beforeBytes;
        return new Window(allocated, nanos, checksum);
    }

    private static long measureOne(boolean optimized, int id) {
        long start = System.nanoTime();
        String value = format(optimized, id);
        long nanos = System.nanoTime() - start;
        sink = value.hashCode();
        return nanos;
    }

    private static double median(double[] data) {
        double[] values = data.clone();
        Arrays.sort(values);
        return values[values.length / 2];
    }

    private static long percentile(long[] values, double quantile) {
        long[] sorted = values.clone();
        Arrays.sort(sorted);
        int index = Math.max(0,
            Math.min(sorted.length - 1,
                (int) Math.ceil(quantile * sorted.length) - 1));
        return sorted[index];
    }

    private static void reportMetric(String name, double value,
                                      String unit) {
        System.out.printf(Locale.ROOT, "%s=%.2f %s%n",
            name, value, unit);
    }

    public static void main(String[] args) {
        verifyEquivalent();

        ThreadMXBean meter = null;
        java.lang.management.ThreadMXBean platform =
            ManagementFactory.getThreadMXBean();
        if (platform instanceof ThreadMXBean) {
            ThreadMXBean available = (ThreadMXBean) platform;
            if (available.isThreadAllocatedMemorySupported()) {
                if (!available.isThreadAllocatedMemoryEnabled()) {
                    try {
                        available.setThreadAllocatedMemoryEnabled(true);
                    } catch (SecurityException | UnsupportedOperationException ex) {
                        // We can still measure throughput and sampled latency.
                    }
                }
                if (available.isThreadAllocatedMemoryEnabled()) {
                    meter = available;
                }
            }
        }
        long threadId = Thread.currentThread().getId();

        for (int i = 0; i < WARMUP_ROUNDS; i++) {
            // Warm up both implementations with identical input sets.
            Window a = runWindow(false, i, meter, threadId);
            Window b = runWindow(true, i, meter, threadId);
            if (a.checksum != b.checksum) {
                throw new AssertionError("Warm-up result mismatch");
            }
        }

        double[] baseBytes = new double[MEASURE_ROUNDS];
        double[] optBytes = new double[MEASURE_ROUNDS];
        double[] baseThroughput = new double[MEASURE_ROUNDS];
        double[] optThroughput = new double[MEASURE_ROUNDS];

        for (int round = 0; round < MEASURE_ROUNDS; round++) {
            boolean optimizedFirst = (round & 1) == 1;
            Window first = runWindow(optimizedFirst, round, meter, threadId);
            Window second = runWindow(!optimizedFirst, round, meter, threadId);
            if (first.checksum != second.checksum) {
                throw new AssertionError("Measurement result mismatch");
            }
            Window base = optimizedFirst ? second : first;
            Window opt = optimizedFirst ? first : second;
            baseBytes[round] = base.bytes < 0
                ? Double.NaN : (double) base.bytes / OPERATIONS_PER_ROUND;
            optBytes[round] = opt.bytes < 0
                ? Double.NaN : (double) opt.bytes / OPERATIONS_PER_ROUND;
            baseThroughput[round] = 1_000_000_000.0 *
                OPERATIONS_PER_ROUND / base.nanos;
            optThroughput[round] = 1_000_000_000.0 *
                OPERATIONS_PER_ROUND / opt.nanos;
        }

        long[] baseLatency = new long[LATENCY_SAMPLES];
        long[] optLatency = new long[LATENCY_SAMPLES];
        for (int i = 0; i < LATENCY_SAMPLES; i++) {
            int id = (i * 73) % MAX_ID;
            if ((i & 1) == 0) {
                baseLatency[i] = measureOne(false, id);
                optLatency[i] = measureOne(true, id);
            } else {
                optLatency[i] = measureOne(true, id);
                baseLatency[i] = measureOne(false, id);
            }
        }

        System.out.println("correctness.all.10000.ids=true");
        System.out.println("warmup.rounds.per.variant=" + WARMUP_ROUNDS);
        System.out.println("measure.rounds.per.variant=" + MEASURE_ROUNDS);
        System.out.println("operations.per.round=" + OPERATIONS_PER_ROUND);
        System.out.println("latency.samples.per.variant=" + LATENCY_SAMPLES);
        System.out.println("allocation.meter.available=" + (meter != null));
        if (meter != null) {
            reportMetric("baseline.median.bytes.per.op",
                median(baseBytes), "B/op");
            reportMetric("candidate.median.bytes.per.op",
                median(optBytes), "B/op");
        }
        reportMetric("baseline.median.throughput",
            median(baseThroughput), "ops/s");
        reportMetric("candidate.median.throughput",
            median(optThroughput), "ops/s");
        System.out.println("baseline.sample.p50.ns=" +
            percentile(baseLatency, .50));
        System.out.println("baseline.sample.p95.ns=" +
            percentile(baseLatency, .95));
        System.out.println("baseline.sample.p99.ns=" +
            percentile(baseLatency, .99));
        System.out.println("candidate.sample.p50.ns=" +
            percentile(optLatency, .50));
        System.out.println("candidate.sample.p95.ns=" +
            percentile(optLatency, .95));
        System.out.println("candidate.sample.p99.ns=" +
            percentile(optLatency, .99));
        System.out.println("pilot.metrics.are.not.production.sla=true");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 11 -encoding UTF-8 WarmupThreeMetrics.java
java WarmupThreeMetrics
~~~

**Một stdout thực đã ghi nhận từ Zulu OpenJDK 24.0.2:**

~~~text
correctness.all.10000.ids=true
warmup.rounds.per.variant=4
measure.rounds.per.variant=7
operations.per.round=40000
latency.samples.per.variant=4096
allocation.meter.available=true
baseline.median.bytes.per.op=461.08 B/op
candidate.median.bytes.per.op=96.00 B/op
baseline.median.throughput=7217610.97 ops/s
candidate.median.throughput=32291918.95 ops/s
baseline.sample.p50.ns=100
baseline.sample.p95.ns=400
baseline.sample.p99.ns=800
candidate.sample.p50.ns=0
candidate.sample.p95.ns=100
candidate.sample.p99.ns=200
pilot.metrics.are.not.production.sla=true
~~~

**Quan trọng:** Các dòng metrics **không phải expected stdout bất biến**; số sẽ khác theo JDK, OS, JIT, GC, CPU scheduling, clock granularity và workload. Đầu ra `candidate.sample.p50.ns=0` là ví dụ trực tiếp của **độ phân giải đồng hồ không đủ để đo từng call nhanh**, không có nghĩa operation thật có latency bằng 0. Nếu JVM không hỗ trợ meter, code vẫn đo throughput/latency và in `allocation.meter.available=false`; các dòng B/op sẽ vắng mặt thay vì bịa giá trị 0.

**Kiểm thử đã thực hiện:** File thực sự biên dịch với `javac --release 11` và chạy **ba lượt** trên JDK 24. Trong ba lượt này, median allocation ổn định khoảng `461.08 B/op` vs `96.00 B/op` nhưng throughput của cùng variant dao động đáng kể; đúng lý do phải dùng nhiều independent forks và không trích một lần chạy để tuyên bố tốc độ sản phẩm. Runtime Java 11 thực chưa được dùng để kiểm chứng trong lượt này.

### 6.1. Vì sao có `volatile sink` và checksum?

Để tránh benchmark vô tình đo một method bị JIT xóa vì kết quả không bao giờ được dùng, chương trình tiêu thụ output `String.hashCode()` và gán kết quả vào `volatile sink`. Việc kiểm mỗi ID từ 0 đến 9999 cùng checksum trong các measurement windows ngăn hai variants làm công việc khác mà ta không phát hiện.

Dẫu vậy, đây **chưa phải harness benchmark tối ưu**: `hashCode()` trong đường đo throughput có overhead và JIT có thể inline/optimize khác nhau. Hãy coi nó là **pilot dễ hiểu và chạy không dependency**, dùng JMH cho số liệu quyết định.

### 6.2. Vì sao đo throughput và latency ở hai pha?

Chèn `System.nanoTime()` vào **mọi** operation làm throughput bị ảnh hưởng bởi chi phí timer; do đó code đo throughput bằng **batch window**, sau đó có một pha timestamp từng call để minh họa latency distribution. Hai pha có instrumentation overhead khác nhau và **không nên đem nhân/chia kết quả như thể chúng đo cùng workload**.

Trong ứng dụng nhiều thread, queue hoặc I/O, pilot trên main thread **không chứa request-level end-to-end latency**. Nên load test ở endpoint boundary thật.

## 7. Công cụ đo nghiêm túc hơn: JMH

[JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh) là bộ công cụ OpenJDK để viết và chạy microbenchmark Java với **warm-up, measurement iterations, multiple JVM forks, consumption of results, benchmark modes và profilers**. Nó có thể:
- đo `Mode.Throughput` → ops/s;
- đo `Mode.SampleTime` → phân phối thời gian của *benchmark invocation*, gồm percentiles;
- dùng `-prof gc` để thêm `gc.alloc.rate.norm` (B/op), `gc.alloc.rate` và GC count/time;
- xuất kết quả JSON, giữ cấu hình JVM/flags, samples và error estimates.

**JMH không mặc định đo latency của HTTP request**. Nó đo method invocation như đã định nghĩa trong `@Benchmark`. Không gọi một JMH p99 là endpoint p99.

### 7.1. Phân biệt JMH modes

| Mode | Trả lời gì? | Điểm cần chú ý |
| --- | --- | --- |
| `Throughput` | Ops / đơn vị thời gian. | Thông thường `ops/s`; throughput cực đại không là fixed-load latency. |
| `AverageTime` | Mean time trên mỗi operation. | Có thể không phản ánh tail latency. |
| `SampleTime` | Randomly sampled elapsed time của các invocations. | Có percentiles; sampling không tự là toàn bộ mọi request. |
| `SingleShotTime` | Thời gian một invocation, hữu ích cho cold-start/initialization. | Khác câu hỏi steady-state sau warm-up. |

Theo tài liệu JMH, `SampleTime` dùng sampling có điều chỉnh tần suất, không bảo đảm ghi mọi operation. Trong case rất nhanh, timer granularity vẫn có thể khiến p50 bằng 0 ns. Vì vậy **không dùng một giá trị p50/p99 nanosecond để kết luận request tail latency**.

## 8. Mã nguồn JMH hoàn chỉnh: throughput và sample latency

Tạo cấu trúc:

~~~text
ticket-jmh/
  pom.xml
  src/main/java/bench/TicketIdJmh.java
~~~

**Tệp `src/main/java/bench/TicketIdJmh.java`:**

~~~java
package bench;

import java.util.Locale;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@Warmup(iterations = 4, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
public class TicketIdJmh {
    private int nextId;

    @Setup(Level.Iteration)
    public void reset() {
        nextId = 0;
    }

    private int id() {
        int value = nextId++;
        if (nextId == 10_000) nextId = 0;
        return value;
    }

    private String baseline() {
        return String.format(Locale.ROOT, "TKT-%04d", id());
    }

    private String candidate() {
        int value = id();
        StringBuilder b = new StringBuilder(8).append("TKT-");
        if (value < 1000) b.append('0');
        if (value < 100) b.append('0');
        if (value < 10) b.append('0');
        return b.append(value).toString();
    }

    @Benchmark
    @BenchmarkMode(Mode.Throughput)
    @OutputTimeUnit(TimeUnit.SECONDS)
    public String baselineThroughput() { return baseline(); }

    @Benchmark
    @BenchmarkMode(Mode.Throughput)
    @OutputTimeUnit(TimeUnit.SECONDS)
    public String candidateThroughput() { return candidate(); }

    @Benchmark
    @BenchmarkMode(Mode.SampleTime)
    @OutputTimeUnit(TimeUnit.NANOSECONDS)
    public String baselineLatency() { return baseline(); }

    @Benchmark
    @BenchmarkMode(Mode.SampleTime)
    @OutputTimeUnit(TimeUnit.NANOSECONDS)
    public String candidateLatency() { return candidate(); }
}
~~~

**Điểm quan trọng:**
- `@State(Scope.Thread)` tạo state riêng cho mỗi benchmark thread; không chia một counter mutable giữa threads.
- `id()` tạo dãy giá trị 0..9999 lặp lại, tương đương domain đã kiểm ở ví dụ standalone.
- `@Setup(Level.Iteration)` reset cursor để iteration bắt đầu cùng state logic.
- Method trả về `String` nên JMH có thể tiêu thụ result theo cơ chế harness; tránh method void hoàn toàn không quan sát được.
- Hai method throughput dùng `TimeUnit.SECONDS`; hai method sampletime dùng `NANOSECONDS`. Không trộn báo cáo `ops/s` với `ns/op`.
- `@Fork(3)`/`@Warmup`/`@Measurement` là cấu hình thử có ý nghĩa, nhưng CLI flags có thể override.
- JMH đưa chi phí state `id()` vào benchmark. Nếu muốn biết riêng chi phí formatter ở ngoài state, cần negative/control benchmark để đo overhead; đừng quên đây là một phần của phép đo đã định nghĩa.

## 9. POM Maven đã được kiểm chứng để build JMH

**Tệp `pom.xml`:** Dùng JMH 1.37 và annotation processor phù hợp. Đây là **một project benchmark riêng**, không phải dependency runtime của ứng dụng server.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>edu.example</groupId>
  <artifactId>ticket-jmh</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>11</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.openjdk.jmh</groupId>
      <artifactId>jmh-core</artifactId>
      <version>1.37</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
        <configuration>
          <release>11</release>
          <annotationProcessorPaths>
            <path>
              <groupId>org.openjdk.jmh</groupId>
              <artifactId>jmh-generator-annprocess</artifactId>
              <version>1.37</version>
            </path>
          </annotationProcessorPaths>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.2</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <finalName>benchmarks</finalName>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <mainClass>org.openjdk.jmh.Main</mainClass>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Lệnh build và chạy:**

~~~bash
mvn -q -DskipTests package
java -jar target/benchmarks.jar -l
java -jar target/benchmarks.jar 'bench.TicketIdJmh.*' \
  -f 3 -wi 5 -i 7 -w 1s -r 1s \
  -prof gc -rf json -rff results.json
~~~

Sau `package`, file `target/benchmarks.jar` là executable JMH JAR. Lệnh thứ hai liệt kê 4 benchmarks. Lệnh cuối chạy **nhiều forks và iterations** để đánh giá nghiêm túc hơn, có output JSON; giá trị `-f 3 -wi 5 -i 7 -w 1s -r 1s` chỉ là cấu hình khởi điểm, điều chỉnh theo thời gian JIT ổn định, tài nguyên và độ nhiễu workload thực.

**QA thực tế:** Project `pom.xml` và `TicketIdJmh.java` được build với Maven offline (artifacts đã được cache), `maven-compiler-plugin` dùng `release 11`; `target/benchmarks.jar` chạy được và liệt kê đủ 4 benchmarks. Không có thay đổi nào trong repository học tập; build được thực hiện ở thư mục tạm.

### 9.1. Lệnh smoke test ngắn khác phép đo kết luận

Để kiểm harness hoạt động, có thể chạy nhanh:

~~~bash
java -jar target/benchmarks.jar 'bench.TicketIdJmh.*' \
  -f 1 -wi 1 -i 2 -w 200ms -r 200ms \
  -prof gc -rf json -rff quick-results.json
~~~

**Chỉ dùng smoke test để xác nhận code/harness, không dùng làm benchmark công bố.** Một fork, một warm-up iteration rất ngắn, hai measurement windows 200ms chưa đủ đại diện các JVM/CPU/GC states. Các con số sau được ghi nhận từ **lệnh smoke test** trên Zulu OpenJDK 24.0.2, không phải kết quả SLO hay bằng chứng thống kê đa môi trường.

## 10. Kết quả JMH smoke test và cách đọc đúng ba metric

| Metric (JMH 1.37; 1 fork; 2×200ms đo) | Baseline `String.format` | Candidate `StringBuilder` | Diễn giải |
| --- | ---: | ---: | --- |
| **Throughput** | 10,101,291 ops/s | 71,032,265 ops/s | Candidate xử lý nhiều calls hơn trong thử ngắn. |
| **Normalized allocation** | 437.089 B/op | 96.000 B/op | Candidate ít bytes/call hơn. |
| **Aggregate allocation rate** | 4,206.415 MB/sec | 6,497.037 MB/sec | Candidate tạo nhiều bytes/s hơn vì ops/s rất lớn. |
| **SampleTime mean** | 129.878 ns/op | 68.463 ns/op | Giá trị mẫu JMH, không phải HTTP latency. |
| **SampleTime p50** | 100 ns/op | ~0 ns/op | Candidate gần giới hạn phân giải đồng hồ, không phải “zero time”. |
| **SampleTime p95** | 200 ns/op | 100 ns/op | Sampling có uncertainty; không là SLO p95. |
| **SampleTime p99** | 491 ns/op | 200 ns/op | Một lượt smoke test, không dùng làm product p99. |

**Hai nhận xét cốt lõi:**

**(A) B/op giảm, throughput tăng — nhưng MB/s tăng.** Đây là điều hoàn toàn hợp lý. Baseline có khoảng 437 B/op và 10.1 triệu ops/s; candidate có 96 B/op và 71 triệu ops/s. Tổng tạo heap bytes mỗi giây của candidate có thể cao hơn dù mỗi ticket hiệu quả hơn. Nếu giữ **cùng 1 triệu ops/s** (fixed arrival load), tính nhẩm allocation rate của baseline ~437 MB/s, candidate ~96 MB/s (đơn vị decimal), nhưng GC pressure thực tế còn phụ thuộc collector/object lifespan/heap.

**(B) Một số p50 bằng 0 ns vì timer quantization.** Không được viết “candidate có zero latency”. Ở tác vụ cực nhanh, dùng JMH SampleTime vẫn có thể thấy ngưỡng độ phân giải clock; muốn đánh giá API p99 phải load test qua boundary thực với quãng thời gian đủ lớn và phương pháp đo phù hợp.

### 10.1. Vì sao số `B/op` ở pilot khác JMH?

Pilot báo khoảng `461.08 B/op` cho baseline, còn JMH throughput profiler báo khoảng `437.089 B/op`. Hai bài đo không hoàn toàn cùng **instruction path**: pilot gọi `String.hashCode()`/tính checksum trong batch, còn JMH trả `String` và harness xử lý giá trị. Phần overhead, code shape, JIT inlining/escape analysis, method invocation và sampling/counter có thể khác. **Không chọn số đẹp hơn rồi thay thế số của bài đo kia**; ghi tên benchmark, implementation và điều kiện.

### 10.2. Ý nghĩa của JMH `-prof gc`

- `gc.alloc.rate.norm`: lượng allocated bytes **chuẩn hóa cho mỗi benchmark invocation**, thường B/op.
- `gc.alloc.rate`: lượng allocation trong một giây theo tốc độ invocation thực tế; có thể tăng khi throughput cao.
- `gc.count` và `gc.time`: số GC/chi phí thu gom quan sát; không suy p99 request từ chúng.
- Các counters có độ chính xác và availability phụ thuộc VM/implementation; kiểm header/metadata và error trong output.
- Phần `SampleTime` có các dòng `:p0.50`, `:p0.95`, `:p0.99`, nhưng số samples/độ phân giải vẫn cần đủ trước khi kết luận.

Ở JDK 24, JMH 1.37 có thể in warning liên quan `sun.misc.Unsafe`. Trong bài thử này harness vẫn build/run được; warnings là **compatibility signal** cần theo dõi ở runtime mới, không phải một lời khuyên để ứng dụng sử dụng `Unsafe` hoặc dựa vào API nội bộ.

## 11. Cách ra quyết định từ allocation + throughput + latency

Tùy sản phẩm, tối ưu có thể được chấp nhận hoặc từ chối ngay cả khi B/op giảm:

| Trường hợp | Allocation | Throughput | Latency | Cách kết luận |
| --- | --- | --- | --- | --- |
| A | B/op giảm rõ | Không giảm | p99 không tăng | Có ứng viên tối ưu; cần load test thật. |
| B | B/op giảm | Tăng | p99 tăng 30% | Có thể vi phạm SLA; chưa đạt. |
| C | B/op không đổi | Tăng 5% | p99 giảm | Có lợi khác, nhưng không được gọi là giảm allocation. |
| D | B/op giảm 80% | Throughput giảm 40% | Không đổi | Trade-off cần đánh giá lại. |
| E | B/op giảm | Throughput tăng ở max-load | MB/s tăng | Bình thường; so fixed-load GC để biết pressure theo traffic. |
| F | B/op giảm | Throughput không đổi | Memory retention/RSS tăng | Cảnh giác cache/object pooling/leak. |

**Quy tắc:** Báo **absolute delta + relative delta** với đơn vị. Nếu baseline 437 B/op còn candidate 96 B/op, giảm khoảng 341 B/op và ~78%. Không viết “GC pause giảm 78%” nếu không đo GC. Nếu throughput tăng gấp nhiều lần trong smoke test, không gọi đó là mức tăng chắc chắn của endpoint.

### 11.1. Cấu hình tải để kiểm ảnh hưởng sản phẩm

Một microbenchmark formatter không bao gồm HTTP server, JSON, network, database, authentication, queue wait hoặc blocking I/O. Muốn biết người dùng có nhanh hơn:
1. Chạy baseline/candidate trên staging tương đương production.
2. Giữ **arrival rate và request mix bằng nhau**, cùng connection reuse, warm-up, heap/GC.
3. Đo total endpoint latency từ boundary chính xác, cả queue wait.
4. Theo dõi p50/p95/p99, error rate, throughput, saturation, CPU, RSS, GC/JFR.
5. Kiểm load generator không gây **coordinated omission** (một client chờ response mới gửi request tiếp có thể che latency spikes khi service quá tải).
6. Chạy lại ở các mức thấp, vừa, gần saturation; có thể so max throughput như **một experiment riêng**.

## 12. Vì sao phải giữ cùng môi trường và JVM flags?

Hai benchmark chỉ so sánh công bằng khi điều kiện đủ tương đương:
- JDK vendor, version và build; một optimization có thể khác giữa Java 11, 17, 21, 25 hoặc 27.
- Heap/GC flags `-Xms`, `-Xmx`, collector, active processor count, container quotas.
- OS power plan, CPU governor, thermal state, noisy neighbors và pinning/CPU affinity nếu cần.
- JFR/GC logging/profiler config: bật giống nhau khi so A/B.
- Threads/concurrency, batch sizes, string locale, input distribution và output.
- Build compiler, code hash và classpath; không để một variant bị debug/logging thêm.
- Giai đoạn warm-up, measurement mode, forks và timer units.

**Chạy code target Java 11 bằng `javac --release 11` không đồng nghĩa đã test runtime Java 11.** Các chương trình ở đây compile target 11 và chạy trên JDK24. Với hệ thống deploy JDK11 thật, cần chạy CI/staging trên **runtime JDK11**, không sao chép số đo từ JVM24.

## 13. Đo thay đổi theo warm-up và kiểm steady state

Bỏ warm-up đúng nghĩa là đo sau một pha chuẩn bị, nhưng không được chỉ lấy iteration có kết quả đẹp nhất. JMH log mỗi warm-up/measurement iteration cho phép phát hiện:
- Càng chạy tốc độ càng tăng vì còn compile.
- Throughput giảm dần vì thermal throttling hoặc GC pressure.
- Allocation B/op thay đổi vì escape analysis/inlining code shape được tối ưu lại.
- GC heap state khác giữa các measurement windows.
- Một fork có outlier lớn so với các forks khác.

Nếu trend chưa ổn định, điều chỉnh warm-up duration/trial length, chứ **không tự chọn một cửa sổ tốt nhất**. Có thể dùng JFR/JDK Mission Control để kiểm JVM compilation, GC và allocation hotspot nếu có đầy đủ quyền/overhead budget.

### 13.1. Đừng nhầm “warm JVM” với “warm cache” của ứng dụng

JIT warm-up, class loading, database connection pool, HTTP/TLS handshake, caches và disk page cache là **các loại warm-up khác nhau**. Nếu benchmark chỉ warm một hàm format ID, nó không bảo đảm service đã warm DB pool hay network. Với benchmark cấp service, định nghĩa cụ thể có bật preload caches, khởi động tất cả consumers và đồng bộ trạng thái traffic hay không.

### 13.2. Cần đo cold-start riêng khi đó là yêu cầu

Ứng dụng serverless/job ngắn có thể có latency khởi động lớn. Dùng `Mode.SingleShotTime` hoặc end-to-end startup tests cho câu hỏi cold-start; không cộng cold-start vào steady-state p95 nếu mục tiêu là hiệu suất sau warm-up, và cũng không lấy steady-state để phủ nhận vấn đề startup.

## 14. Thống kê: bao nhiêu samples thì đủ?

Không có số iterations/forks duy nhất đúng cho mọi workload. Các phép đo trong một JVM fork **không hoàn toàn độc lập**: cùng JIT state, heap state, OS scheduling và CPU temperature. Vì vậy:
- Có **nhiều forks độc lập** cho mỗi variant, warm-up mỗi fork.
- Lưu raw results từng fork/iteration, không chỉ một mean/score.
- Đảo thứ tự A/B giữa experiments hoặc dùng thiết kế crossover có kiểm soát.
- Báo effect size và uncertainty interval (CI hoặc phân phối theo forks), không chỉ % change.
- Với p99, cần **đủ số sample tail** và kiểm độ phân giải; p99 từ 100 mẫu là rất yếu.
- Đừng bootstrap mỗi operation trong cùng process rồi giả định chúng độc lập nếu chúng chia sẻ contention/GC; có thể bootstrap ở mức fork/trial.
- Đặt decision gate về **practical significance** trước khi chạy; không chỉ dựa vào p-value.

JMH có score error estimates, nhưng một smoke test với một fork và hai windows **không tạo được độ tin cậy thống kê cao**. Lặp lại cả benchmark mới, không lấy dòng thấp nhất/cao nhất để quảng bá.

## 15. Tại sao latency sampling ở microbenchmark không là p99 request?

Dưới low load, một `StringBuilder` nhanh có thể mất vài chục nanoseconds nhưng timer hiển thị theo quanta ~100 ns, gây `p50≈0`. Trong HTTP service, trải nghiệm người dùng còn có routing, IO, database, queuing, JSON serialization, retries, GC và network. Vì vậy:
- **JMH SampleTime p99** là p99 của sampled method invocations trong chính harness.
- **Service p99** là p99 request latency theo protocol boundary đã định nghĩa, thuộc một tập requests thực/giả lập tại arrival rate xác định.
- **GC pause p99** là phân phối GC pauses, không cùng denominator.
- **Thread CPU time** không bao gồm toàn bộ elapsed wait/network.
- **Latency under load** phụ thuộc queueing, và không suy chỉ từ throughput cực đại.

Khi load generator đóng vòng (gửi request mới sau response), nó có thể gửi ít request đi đúng lúc server chậm nên bỏ qua các delays đáng lẽ người dùng phải chịu — **coordinated omission**. Cần chọn open-loop/constant-arrival load hoặc compensation thích hợp, và báo arrival rate thực, completions, timeouts, errors.

## 16. Phép đo allocation bằng JFR và GC logs

Java 11 có Java Flight Recorder (`jdk.jfr`) và công cụ JDK Mission Control tương ứng để tìm allocation hotspots/GC behavior. JFR events như `jdk.ObjectAllocationInNewTLAB` và `jdk.ObjectAllocationOutsideTLAB` có thể chỉ ra classes/call stacks cấp phát, nhưng **không phải một event cho từng object**. Không lấy **JFR allocation event count = exact object count**.

Để xem GC trong workload Java11:

~~~bash
java -Xms512m -Xmx512m \
  '-Xlog:gc*:file=gc.log:time,uptime,level,tags' \
  WarmupThreeMetrics
~~~

Đây là **lệnh minh họa**, cần JDK HotSpot hỗ trợ Unified Logging và bộ nhớ phù hợp. `-Xlog` là cơ chế logging hiện hành từ JDK9, phù hợp Java11; không dùng flags GC logging đã lỗi thời trong bài mới. So baseline/candidate với cùng logging config nếu muốn đối chiếu. Chỉ có **GC count giảm** không tự chứng minh B/op giảm nếu heap state/collector/load cũng thay đổi.

**Giới hạn:** JMH `-prof gc` bổ sung B/op, GC count/time cho benchmark, nhưng có profiler overhead. Để phân tích p99 service, thu JFR trong một khoảng ngắn có kiểm soát cùng load test, không bật tùy tiện recording nặng suốt ngày. Chú ý retention/privacy vì file `.jfr` chứa class/stack/thread names và có thể custom fields nhạy cảm.

## 17. Xây một bảng kết quả dễ quyết định

Bảng sau phân biệt **kết quả đã thực sự đo** và **các điều cần đo tiếp**:

| Trường | Trạng thái | Nội dung |
| --- | --- | --- |
| Bài toán | Xác định | Ticket ID 0–9999 → chuỗi `TKT-0000`…`TKT-9999`. |
| Correctness | **PASS (thử nghiệm)** | Toàn bộ 10.000 IDs của hai variants giống nhau. |
| Pilot B/op | **Đã đo trên JDK24** | Khoảng 461.08 vs 96.00 B/op trong local pilot. |
| Pilot throughput | **Đã đo trên JDK24** | Thay đổi giữa các lượt; một lượt 7.22m vs 32.29m ops/s. |
| Pilot p50/p95/p99 | **Đã đo nhưng độ phân giải thấp** | Candidate p50 có thể 0 ns, không có nghĩa latency bằng 0. |
| JMH Maven build | **PASS** | `release 11`, JMH1.37, 4 benchmarks tạo và chạy. |
| JMH B/op | **Đã đo trong smoke test** | Khoảng 437.089 vs 96.000 B/op. |
| JMH throughput | **Đã đo trong smoke test** | Khoảng 10.10m vs 71.03m ops/s. |
| JMH sampling | **Đã đo trong smoke test** | p95 khoảng 200 vs 100ns/op; p99 khoảng 491 vs 200ns/op. |
| JMH multi-fork credible run | **Chưa chạy** | Cần đủ iterations/forks nếu ra quyết định performance. |
| Production p99/throughput | **Chưa đo** | Cần load test endpoint dưới traffic thật. |
| JVM11 runtime test | **Chưa chạy** | Hiện chỉ compile `--release 11` và chạy JDK24. |
| Production rollout decision | **Chưa đủ bằng chứng** | Có ứng viên tốt, cần thực hiện guardrails. |

**Kết luận trong phạm vi kiểm thử:** Phương án `StringBuilder` có B/op thấp hơn rõ trên JVM thử và có throughput tốt trong thử ngắn; nhưng **không thể từ đó hứa** production p99, GC time hoặc cost giảm theo cùng tỷ lệ. Cũng không được gọi JMH smoke test “full benchmark” nếu nó chỉ dùng 1 fork × 200ms.

## 18. Những lỗi phổ biến khi so sánh ba metric

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| Đo ngay sau JVM startup | Class loading/JIT làm nhiễu. | Warm-up riêng, bỏ warm-up samples. |
| Chạy baseline trước candidate liên tục | Order bias và cache/JIT hot state. | Đảo thứ tự, forks độc lập. |
| So hai code không cùng output | “Tối ưu” bằng cách làm ít việc hơn. | Assert correctness trước đo. |
| Benchmark không dùng kết quả | JIT dead-code elimination. | Trả về result/Blackhole/volatile sink phù hợp. |
| Dùng `Runtime.freeMemory` làm B/op | Lẫn retained heap/GC với allocation. | MXBean/JMH `gc.alloc.rate.norm`. |
| `getThreadAllocatedBytes` trên thread sai | Bỏ sót worker threads. | Định nghĩa đúng scope, dùng profiler/attribution. |
| Không xử lý unsupported/-1 | Báo 0 B/op giả. | N/A, kiểm capability. |
| Dùng một `nanoTime` cho từng call quá nhanh | p50 0 hoặc quá nhiễu. | JMH SampleTime/batch sampling, mô tả clock limits. |
| Coi JMH p99 là HTTP p99 | Sai phạm vi đo. | Load test boundary của request. |
| So `B/op` với `MB/s` mà không xét throughput | Kết luận trái dấu sai. | `B/s = B/op × ops/s`. |
| So ops/s ở throughput max rồi suy fixed-load GC | Workload rate khác nhau. | So cùng arrival rate. |
| Nhầm `gc.alloc.rate.norm` B/batch với B/item | Mất denominator. | Ghi scope/invocation và chuẩn hóa. |
| Thời lượng warm-up quá ngắn | JIT còn compile khi đo. | Kiểm trend, tăng warm-up hợp lý. |
| Chỉ 1 fork/iteration | Không ước lượng giữa các process. | Nhiều forks/trials. |
| Dùng p99 với rất ít samples | Tail estimate không ổn định. | Thu đủ samples, báo uncertainty. |
| Gắn `@State(Scope.Benchmark)` cho counter mutable không sync | Contention/race khác bài toán. | `Scope.Thread` cho micro thread-local. |
| Bật JFR chỉ ở candidate | Instrumentation overhead khác nhau. | Cùng profiler config. |
| B/op giảm nhưng cache giữ objects mãi | Retained heap tăng/leak. | Heap/RSS/GC guardrails. |
| Lấy GC count ít hơn làm bằng chứng giảm B/op | GC policy khác heap state. | Đo allocated bytes trực tiếp. |
| Áp kết quả JDK24 cho Java11 runtime | JIT/object layout khác. | Chạy CI trên JDK11 thật. |
| Dùng API/flag legacy trong README mới | Khó tái hiện trên JDK hiện hành. | API Java11 + JMH + Unified Logging. |
| Không lưu raw results/VM flags | Không review hay tái lập được. | JSON, code SHA, JVM/OS info, script. |
| Không kiểm endpoint load saturation | Throughput tăng mà tail latency xấu. | So multiple load levels và queueing. |

## 19. Bài tập thực hành và câu hỏi phân tích

**Bài 1 — ba chỉ số:** Baseline 400 B/op, 5 triệu ops/s; candidate 100 B/op, 30 triệu ops/s. Hỏi B/op giảm bao nhiêu %, total B/s thay đổi thế nào? **Gợi ý:** giảm 75% B/op; baseline 2 tỷ B/s, candidate 3 tỷ B/s — tổng allocation/s tăng 50% ở throughput cực đại.

**Bài 2 — fixed load:** Với cùng fixed input 1 triệu requests/s và kết quả như bài 1, ước tính allocated B/s? **Gợi ý:** 400 triệu B/s vs 100 triệu B/s nếu cùng code path, không tính work khác.

**Bài 3 — warm-up:** Chạy `WarmupThreeMetrics` với `WARMUP_ROUNDS=0`, rồi 4 và 10. Vì sao số throughput khác nhau không nhất thiết chỉ do code logic? Thử quan sát từng iteration thay vì một median.

**Bài 4 — correctness:** Sửa `candidate` để dùng `StringBuilder` nhưng không zero pad. Tại sao `verifyEquivalent()` phải fail ngay cả khi candidate chạy nhanh hơn?

**Bài 5 — timer:** Trong stdout pilot có `candidate.sample.p50.ns=0`. Tại sao đây **không** phải “operation free”? Thiết kế phép đo batch hoặc JMH SampleTime để giảm ảnh hưởng của timer call.

**Bài 6 — JMH modes:** Chạy JMH `Throughput` và `SampleTime`, mô tả units, percentiles và vì sao không nhân `ops/s` với `p99` để ra số threads.

**Bài 7 — profiler:** Chạy `-prof gc`, ghi `gc.alloc.rate.norm` và `gc.alloc.rate` cho từng variant. Giải thích trường hợp B/op giảm nhưng MB/sec tăng.

**Bài 8 — robust experiment:** Tăng từ 1 fork/2×200ms lên 3 forks/7×1s, thu JSON và so độ phân tán. Đặt practical threshold trước khi chạy.

**Bài 9 — JVM11:** Dùng JDK11 runtime thật (không chỉ `--release 11`) và ghi số B/op/ops/s; không tự áp số JDK24.

**Bài 10 — batch:** Thay mỗi benchmark invocation tạo 100 tickets, báo `B/batch` rồi chuẩn hóa thành B/ticket. Ghi rõ khi throughput là batch/s.

**Bài 11 — concurrent:** Chạy 1 và 8 JMH threads, xem contention/GC rate và tại sao B/op có thể khác. Không dựa trên current-thread MXBean để suy mọi allocations của cả request.

**Bài 12 — load test:** Một HTTP service đạt throughput cao hơn nhưng p99 tăng 20% ở mức 90% CPU. Với gate “p99 không tăng >5%”, nên chấp nhận tối ưu chưa? **Không** khi chưa giải quyết vi phạm.

**Bài 13 — coordinated omission:** Một load generator gửi request mới chỉ sau khi nhận response. Khi server bị pause 2 giây, vì sao generator có thể under-report latency của requests lẽ ra đã đến trong 2 giây đó?

**Bài 14 — GC:** Với candidate ít B/op hơn nhưng nhiều completed ops/s hơn, tại sao GC count/time có thể tăng trong throughput-max trial?

**Bài 15 — report:** Lập bảng môi trường, commit SHA, JDK vendor/version, flags, warm-up, forks, input seed, B/op, ops/s, SampleTime p99, HTTP p99, error rate, GC and RSS, CI và rollout decision.

## 20. Checklist trước khi chấp nhận một tối ưu

- [ ] Có **định nghĩa rõ một operation**, không nhầm item/batch/request.
- [ ] Correctness baseline/candidate đã đối chiếu toàn bộ domain cần hỗ trợ.
- [ ] Cùng JDK/VM flags, heap/GC, CPU/container, data distribution và code path.
- [ ] Warm-up hai variants trước measurement; theo dõi trend, không chọn iteration đẹp nhất.
- [ ] Có nhiều independent forks và iterations, không chỉ một smoke test.
- [ ] Đo allocation `B/op` bằng MXBean/JMH profiler, xử lý unsupported/-1.
- [ ] Đo throughput với đúng unit `ops/s` và cùng concurrency/config.
- [ ] Đo latency với phương pháp phù hợp độ dài operation; kiểm clock quantization.
- [ ] Không coi p99 JMH của method là p99 end-to-end request.
- [ ] Hiểu B/op giảm có thể đồng thời làm MB/s tăng khi ops/s tăng.
- [ ] Có experiment fixed-load ngoài max-throughput để so GC pressure.
- [ ] Có GC/JFR/CPU/RSS/retained heap và p95/p99 endpoint guardrails.
- [ ] Không bỏ qua warm-up/cold-start nếu workload cần đo cả hai.
- [ ] Có raw JSON, build SHA, JVM version, flags và units để tái lập.
- [ ] Không claim Java11 runtime đã chạy chỉ vì `javac --release 11` biên dịch.
- [ ] Quyết định rollout theo correctness + effect size + uncertainty + SLO, không theo một % “nhanh hơn”.

## 21. Tài liệu và kết luận

**Nguồn chính thức/được duy trì:**

1. [OpenJDK — JMH Project](https://github.com/openjdk/jmh): giới thiệu harness, cấu hình dự án và annotation processing.
2. [JMH sample — Benchmark Modes](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_02_BenchmarkModes.java): `Throughput`, `AverageTime`, `SampleTime`, `SingleShotTime`.
3. [JMH sample — Profilers](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java): `gc.alloc.rate.norm` và chi phí profiling.
4. [JMH Mode Javadoc 1.37](https://javadoc.io/static/org.openjdk.jmh/jmh-core/1.37/org/openjdk/jmh/annotations/Mode.html): mô tả chính thức các benchmark modes và sampling.
5. [Maven Central — JMH Core 1.37](https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-core/1.37): dependency và phiên bản đã dùng trong ví dụ.
6. [Java SE 11 — com.sun.management.ThreadMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): `getThreadAllocatedBytes`, support/enable và giới hạn accuracy.
7. [Java SE 11 — System.nanoTime](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/System.html#nanoTime()): nguồn đo elapsed duration, không phải thời gian lịch.
8. [Java SE 11 — Unified Logging, java tool](https://docs.oracle.com/en/java/javase/11/tools/java.html): `-Xlog:gc*` và các tùy chọn JVM.
9. [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR trong JDK và quan sát performance.
10. [Java SE 11 — JFR RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc file JFR để phân tích JVM events.

**Ghi nhớ:** Sau warm-up, hãy so **đúng ba metric với đúng denominator và workload**: allocation (B/op), throughput (ops/s) và latency (p50/p95/p99 trong phạm vi định nghĩa). Một candidate có thể **ít B/op nhưng nhiều MB/s hơn** khi đạt throughput cao hơn. Pilot Java11 giúp hiểu phép đo; JMH với forks/warm-up/`-prof gc` cho microbenchmark đáng tin hơn; cuối cùng vẫn cần load test cùng arrival rate để xác minh p99, GC và SLO của service. Trong lượt thử này, bài code có correctness đầy đủ và số đo thật trên JDK24, nhưng kết luận production/JVM11 cần thí nghiệm riêng.