# Kiểm thử độ trễ đuôi, throughput và allocation stall — GC độ trễ thấp

## 1. Mục tiêu, ngữ cảnh Java 11 và kiến thức hiện hành

Một garbage collector được xem là **độ trễ thấp** khi nó giảm ảnh hưởng của GC tới thời gian đáp ứng ứng dụng. Tuy nhiên, **GC pause ngắn không bảo đảm request p99/p99.9 ngắn**. Bên cạnh stop-the-world (STW) còn có queueing, CPU throttling, safepoints, I/O, thread scheduling, và **allocation stall**: Java mutator cần cấp phát nhưng phải chờ bộ nhớ khả dụng.

Bài học này hướng dẫn **kiểm thử và diễn giải bằng chứng**, thay vì tuyên bố một collector luôn nhanh nhất. Các mục tiêu:

1. Định nghĩa **p50/p95/p99/p99.9/max**, thông lượng request, tỉ lệ lỗi và cách tính nearest-rank percentile.
2. Phân biệt **end-to-end từ planned arrival tới completion** với producer scheduling lag, queue wait, service time và GC STW pause.
3. Hiểu lỗi đo **coordinated omission** khi load generator đợi request trước hoàn tất rồi mới gửi tiếp.
4. Xây thử nghiệm **open-loop**, bounded queue, giữ nguyên planned arrivals và ghi rõ rejections/timeouts.
5. Hiểu **allocation stall**, nhất là đối với collector đồng thời như ZGC: GC pauses rất ngắn nhưng thread có thể chờ allocation nếu heap/GC không theo kịp.
6. Thu bằng chứng từ **unified GC logging `-Xlog`**, **JFR `jdk.GCPhasePause`/`jdk.ZAllocationStall`**, thread/CPU/heap metrics và `GarbageCollectorMXBean`.
7. Biên dịch **hai chương trình Java tương thích Java 11**, đo latency/throughput và đọc file JFR, so sánh G1/ZGC ở runtime hỗ trợ.
8. Thiết kế benchmark có **warm-up, sustained/burst/overload, đủ mẫu cho p99.9, kiểm generator capacity và repetitions**.
9. Phân biệt GC cycle duration với STW duration; không cộng sai percentiles của nhiều service hoặc tổng thread-stall times với wall-clock downtime.
10. Biết khi nào nên điều chỉnh heap headroom, giảm allocation rate, xem queue limits hoặc kiểm OS scheduling thay vì đổi GC.

**Special Note — chỉ kiến thức còn áp dụng:** `-Xlog`, JFR, G1, ZGC và các chỉ số tail latency vẫn là công cụ hiện hành. Trên **JDK 24 trở lên, ZGC chỉ còn generational mode**; tùy chọn `ZGenerational` đã bị xóa, không đưa flags legacy đó vào lệnh chạy. ZGC ở một số bản JDK 11 là experimental, trong khi trên JDK mới đã production-ready; bài dùng **Java 11 source compatibility** nhưng không đánh đồng mọi phiên bản ZGC. Không hướng dẫn dùng CMS đã lỗi thời.

## 2. Đo tail latency và throughput đúng nghĩa

### 2.1. Các percentile

Cho N độ trễ quan sát được, sắp xếp tăng dần. Với phương pháp **nearest-rank**, percentile p được lấy ở vị trí `ceil(p × N)`, đánh số từ 1. Ví dụ mảng 1, 2, 3, 4, 100 milliseconds:

| Percentile | Nearest-rank result |
| --- | --- |
| p50 | 3 ms |
| p90 | 100 ms |
| p99 | 100 ms |
| p99.9 | 100 ms |
| max | 100 ms |

N chỉ có 5 observations nên p90/p99/p99.9 đều rơi vào max. **Đó là giới hạn sample size, không chứng minh hệ thống có tail thật ở mọi phân vị.** Để đánh giá p99.9 có độ ổn định, cần hàng chục nghìn đến hàng trăm nghìn observations tùy độ tin cậy yêu cầu, nhiều cửa sổ đo và nhiều repetitions. p99.9 tính trên 1.000 mẫu chỉ nằm gần giá trị cao nhất; p99 của 100 samples cũng quá nhạy với vài outliers.

**Không lấy trung bình của các p99 theo phút hay máy rồi gọi đó là p99 tổng thể**. Muốn gộp cần giữ raw samples hoặc merge histogram tương thích, ví dụ HdrHistogram, chứ percentile không cộng được như sum.

### 2.2. Độ trễ client, queue và service

Dùng đồng hồ đơn điệu `System.nanoTime()` cho durations trong cùng JVM:

~~~text
t_due              t_enqueued              t_start                t_finish
  |--------------------|-----------------------|-----------------------|
  | producer delay     | queue wait            | service time          |
  |<-------------------- E2E from planned arrival ------------------------>|

producer_lag = max(0, t_enqueued - t_due)
queue_wait   = max(0, t_start - t_enqueued)
service_time = max(0, t_finish - t_start)
E2E          = max(0, t_finish - t_due)
~~~

Một phép đo chỉ từ `t_start` đến `t_finish` là **service time**, không gồm backlog. Nếu một request chờ 90 ms trong queue rồi xử lý 3 ms, service time đẹp nhưng latency người dùng tệ.

**Không cộng các percentile**: `p99(E2E)` không nhất thiết bằng `p99(queue) + p99(service) + p99(producer lag)`, dù với **một request cụ thể**, các khoảng thời gian có thể cộng để tạo E2E.

### 2.3. Throughput và rejection

| Số liệu | Định nghĩa |
| --- | --- |
| **Offered** | Tổng số request được lên lịch để đưa tới hệ thống. |
| **Accepted** | Request được nhận vào worker pool/queue. |
| **Completed** | Request đã xử lý xong, có completion timestamp. |
| **Rejected/timeout/failed** | Những request không thành công; phải tính vào SLO lỗi. |
| **Application throughput** | Completed per wall-second, khác offered rate. |
| **GC throughput** | Tỉ lệ thời gian hệ thống không làm GC, là khái niệm JVM riêng. |
| **Drain time** | Thời gian xử lý backlog còn lại sau khi ngừng sinh requests. |

Công thức minh họa:

~~~text
rejection_rate = rejected / offered * 100%
completed_throughput = completed / wall_seconds
success_fraction = successful / offered
~~~

Một p99=5ms nhưng rejection 20% **không tốt hơn** p99=12ms, rejection 0% nếu SLO bao gồm tất cả offered arrivals. Vì accepted-only histogram bỏ qua rejections, **khi overload latency percentiles có thể đẹp lên giả**.

`GarbageCollectorMXBean.getCollectionCount()` không phải request throughput hoặc allocation-stall counter. G1/ZGC có nhiều collector beans với meanings khác nhau; **không so chênh lệch count giữa collectors như số GC pauses tương đương**.

### 2.4. Coordinated omission là gì?

Load generator kiểu closed-loop:

~~~text
send one request -> wait response -> measure -> send next request
~~~

Khi server stall 500 ms, generator cũng đợi 500 ms; những requests **đáng lẽ đến trong 500 ms đó** không được gửi/đo. Histogram thiếu nhiều bad observations, và p99/p99.9 trông tốt hơn thực tế. Đây là **coordinated omission**.

Đối với SLO có arrivals độc lập, dùng **open-loop scheduling**:

~~~text
rate = 500 request/s   =>  period = 2 ms
due[0] = T0
due[1] = T0 + 2 ms
due[2] = T0 + 4 ms
due[3] = T0 + 6 ms
...
~~~

Generator không đợi completion để định lịch request tiếp theo. Đo từ **planned due** để phản ánh producer tự thức dậy muộn. Nếu generator không phát được traffic do CPU/connection limits, phải ghi **dropped/scheduling lag**; không đẩy lịch qua phải rồi lờ các arrivals bị bỏ qua.

**Giới hạn của ví dụ Java:** load generator và workers chạy cùng JVM nên bản thân producer cũng có thể bị GC pause/scheduler trì hoãn. Đây là **bài tập về phương pháp**, không phải network end-to-end load test. Để đo SLO thực, chạy một **client độc lập** có constant-arrival-rate, đủ CPU/connections, đồng hồ ổn định và báo dropped iterations.

## 3. STW pause, concurrent GC và allocation stall

### 3.1. GC pause khác GC cycle duration

G1 có stop-the-world phases, thậm chí Full GC khi pressure xấu. Với ZGC, phần lớn công việc GC có thể **chạy đồng thời** với Java mutator. Một cycle kéo dài 300 ms không có nghĩa ứng dụng dừng 300 ms; phải kiểm **pause phases** trong GC logs/JFR.

- **GC cycle duration:** toàn bộ một chu trình, có thể có nhiều công việc concurrent.
- **STW pause:** JVM dừng Java mutators để thực hiện một phase cụ thể.
- **Safepoint duration:** có thể bao gồm lý do ngoài GC; cần `-Xlog:safepoint`.
- **End-to-end request latency:** có thể ảnh hưởng bởi mọi yếu tố trên, nhưng còn queue, CPU, network, locks và application logic.

### 3.2. Allocation stall

**Allocation stall** là thời gian thread đang cấp phát đối tượng phải **chờ bộ nhớ khả dụng**. Với ZGC, collector làm nhiều công việc concurrently để giảm STW pause, nhưng nó vẫn cần **heap headroom** cho allocations trong lúc GC reclaim. Nếu allocation rate cao, heap quá chật hoặc concurrent GC thiếu CPU, mutator có thể chờ. JFR event **`jdk.ZAllocationStall`** và các unified GC log messages có thể chứng minh tình huống này.

Ví dụ giả định:

~~~text
ZGC STW pause        = 0.15 ms
Thread A allocation stall = 18 ms
Request trên Thread A     = 21 ms

Kết luận đúng: pause ngắn nhưng allocation stall làm request chậm.
Kết luận sai: GC hoàn toàn không gây latency vì pause <1ms.
~~~

Đừng nhầm:
- **Queue wait**: request chờ worker, có thể không liên quan GC trực tiếp.
- **Java lock contention**: chờ mutex/monitor.
- **OS scheduling**: không được CPU hoặc bị container throttled.
- **TLAB refill/slow path**: không tự động đồng nghĩa ZGC allocation stall.
- **OutOfMemoryError**: trạng thái allocation fail; không phải latency đo bình thường.
- **GC concurrent cycle duration**: không bằng STW downtime.

Một hệ thống có thể nhận **0 `jdk.ZAllocationStall` events** vì chưa gặp pressure, chưa bật event, runtime/collector không phát nó hoặc threshold lọc event; **zero event không chứng minh zero stalls**.

### 3.3. G1 và ZGC ở JDK hiện hành

**G1** cân bằng throughput và pause goals; `-XX:MaxGCPauseMillis` chỉ là mục tiêu **mềm**, không phải hard real-time guarantee. Nếu thấy G1 Full GC/evacuation failure/humongous allocations, xem heap/live set và log trước khi điều chỉnh flags.

**ZGC** giảm STW bằng concurrent work, có thể đánh đổi CPU, throughput và memory footprint; cần heap đủ cho **live set + allocations khi GC đang hoạt động**. Từ **JDK 24**, ZGC chỉ còn generational mode, không cấu hình `ZGenerational`. Java 11 cho phép test G1 một cách phổ biến; ZGC trên JDK 11 cần kiểm version/vendor/platform, không áp lệnh ZGC production của JDK 24 vào một build Java 11 bất kỳ.

**Chỉ khi benchmark end-to-end qua nhiều lần chạy** mới so sánh được sự đánh đổi collector ở workload đó.

## 4. Chương trình Java 11: open-loop load, percentile và bounded queue

### 4.1. Thiết kế

File `GcTailLatencyLab.java`:

- `selftest` kiểm nearest-rank percentile và phân rã thời gian bằng dữ liệu cố định.
- Chế độ đo nhận `ratePerSecond seconds workers allocKiB`.
- Producer phát `rate × seconds` slots theo lịch `System.nanoTime`; không chờ tasks cũ hoàn thành.
- `ThreadPoolExecutor` có số threads cố định và queue có giới hạn; `AbortPolicy` tạo `RejectedExecutionException` khi đầy.
- Workers cấp phát byte arrays, giữ tối đa 64 arrays để tạo heap allocation pressure.
- Lưu riêng E2E, queue wait, service time, scheduling lag cho accepted requests.
- Sau khi drain, báo throughput, rejection rate, percentiles p50/p99/p99.9/max và GC MXBean activity count.
- Mọi tham số được giới hạn để tránh benchmark tạo hàng triệu tasks hoặc arrays quá lớn vì nhập sai.

Đây là ví dụ độc lập, **không cần HTTP server** hoặc thư viện ngoài.

### 4.2. File GcTailLatencyLab.java

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReferenceArray;
import java.util.concurrent.locks.LockSupport;

public final class GcTailLatencyLab {
    private static final int CAPTURED_SURVIVORS = 64;

    private static void check(boolean ok, String what) {
        if (!ok) throw new AssertionError(what);
    }

    private static long percentile(long[] observations, int count,
                                   int basisPoints) {
        if (count <= 0 || basisPoints < 1 || basisPoints > 10000) {
            throw new IllegalArgumentException("invalid percentile input");
        }
        long[] sorted = Arrays.copyOf(observations, count);
        Arrays.sort(sorted);
        long rank = ((long) count * basisPoints + 9999L) / 10000L;
        return sorted[(int) rank - 1];
    }

    private static void selftest() {
        long[] values = {
                1_000_000L, 2_000_000L, 3_000_000L,
                4_000_000L, 100_000_000L
        };
        check(percentile(values, 5, 5000) == 3_000_000L,
                "nearest-rank p50");
        check(percentile(values, 5, 9000) == 100_000_000L,
                "nearest-rank p90");
        check(percentile(values, 5, 9900) == 100_000_000L,
                "nearest-rank p99");
        check(percentile(values, 5, 9990) == 100_000_000L,
                "nearest-rank p99.9");
        System.out.println("PASS nearest-rank percentile boundaries");

        long due1 = 1_000_000_000L;
        long queuedAt = 1_004_000_000L;
        long workerStart = 1_012_000_000L;
        long finish = 1_019_000_000L;
        check(finish - due1 == 19_000_000L,
                "scheduled arrival to completion");
        check(workerStart - queuedAt == 8_000_000L,
                "actual queue wait");
        check(finish - workerStart == 7_000_000L,
                "service time");
        check(queuedAt - due1 == 4_000_000L,
                "producer scheduling lag");
        System.out.println("PASS end-to-end decomposition");

        long interval = TimeUnit.SECONDS.toNanos(1) / 500L;
        check(interval == 2_000_000L, "arrival spacing");
        check((1499L * 1_000_000_000L) / 500L
                == 2_998_000_000L, "planned arrival index");
        System.out.println("PASS open-loop schedule arithmetic");
        System.out.println("ALL LATENCY MATH TESTS PASSED");
    }

    private static long gcCollections() {
        long count = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionCount();
            if (value >= 0) count += value;
        }
        return count;
    }

    private static String gcNames() {
        StringBuilder builder = new StringBuilder();
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (builder.length() != 0) builder.append(", ");
            builder.append(bean.getName());
        }
        return builder.toString();
    }

    private static int positive(String text, int max, String label) {
        int result;
        try {
            result = Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(label + " must be integer", ex);
        }
        if (result < 1 || result > max) {
            throw new IllegalArgumentException(
                    label + " must be within 1.." + max);
        }
        return result;
    }

    private static double millis(long nanos) {
        return nanos / 1_000_000.0;
    }

    private static void report(String name, long[] all,
                               int[] acceptedIndexes, int completed) {
        if (completed == 0) {
            System.out.println(name + "=NO_COMPLETED_SAMPLES");
            return;
        }
        long[] compact = new long[completed];
        for (int i = 0; i < completed; i++) {
            compact[i] = all[acceptedIndexes[i]];
            check(compact[i] >= 0, "all recorded measurements present");
        }
        long p50 = percentile(compact, compact.length, 5000);
        long p99 = percentile(compact, compact.length, 9900);
        long p999 = percentile(compact, compact.length, 9990);
        long max = percentile(compact, compact.length, 10000);
        check(p50 <= p99 && p99 <= p999 && p999 <= max,
                "monotonic percentiles");
        System.out.printf(Locale.ROOT,
                "%s: p50=%.3fms p99=%.3fms p99.9=%.3fms max=%.3fms%n",
                name, millis(p50), millis(p99),
                millis(p999), millis(max));
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "selftest".equals(args[0])) {
            selftest();
            return;
        }
        if (args.length != 4) {
            System.err.println("Usage: java GcTailLatencyLab "
                    + "<ratePerSecond> <seconds> <workers> <allocKiB>");
            System.err.println("Or: java GcTailLatencyLab selftest");
            System.exit(2);
            return;
        }

        int rate = positive(args[0], 20_000, "ratePerSecond");
        int seconds = positive(args[1], 120, "seconds");
        int workers = positive(args[2], 64, "workers");
        int allocKiB = positive(args[3], 256, "allocKiB");
        long offeredLong = (long) rate * seconds;
        if (offeredLong > 300_000L) {
            throw new IllegalArgumentException("max 300000 offered requests");
        }
        int offered = (int) offeredLong;
        int queueCapacity = Math.max(128, workers * 64);
        AtomicReferenceArray<byte[]> survivors =
                new AtomicReferenceArray<>(CAPTURED_SURVIVORS);
        long[] endToEnd = new long[offered];
        long[] enqueueToStart = new long[offered];
        long[] service = new long[offered];
        long[] schedulingLag = new long[offered];
        Arrays.fill(endToEnd, -1L);
        Arrays.fill(enqueueToStart, -1L);
        Arrays.fill(service, -1L);
        Arrays.fill(schedulingLag, -1L);

        AtomicInteger completedCount = new AtomicInteger();
        AtomicInteger rejectedCount = new AtomicInteger();
        int[] acceptedIndexes = new int[offered];
        int accepted = 0;
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                workers, workers, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(queueCapacity),
                new ThreadPoolExecutor.AbortPolicy());
        executor.prestartAllCoreThreads();

        System.out.println("GC_COLLECTORS=" + gcNames());
        System.out.printf(Locale.ROOT,
                "CONFIG rate=%d/s seconds=%d workers=%d allocKiB=%d queue=%d%n",
                rate, seconds, workers, allocKiB, queueCapacity);

        long gcBefore = gcCollections();
        long plannedStart = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(100);
        for (int i = 0; i < offered; i++) {
            long due = plannedStart
                    + ((long) i * 1_000_000_000L) / rate;
            long delay;
            while ((delay = due - System.nanoTime()) > 0L) {
                LockSupport.parkNanos(Math.min(delay, 1_000_000L));
            }
            final int index = i;
            final long dueTime = due;
            final long enqueuedAt = System.nanoTime();
            schedulingLag[index] = Math.max(0L, enqueuedAt - dueTime);
            try {
                executor.execute(() -> {
                    long workerStart = System.nanoTime();
                    byte[] bytes = new byte[allocKiB * 1024];
                    bytes[0] = (byte) index;
                    bytes[bytes.length - 1] = (byte) (index >>> 8);
                    survivors.set(index % CAPTURED_SURVIVORS, bytes);
                    long finish = System.nanoTime();
                    enqueueToStart[index] =
                            Math.max(0L, workerStart - enqueuedAt);
                    service[index] =
                            Math.max(0L, finish - workerStart);
                    endToEnd[index] = Math.max(0L, finish - dueTime);
                    completedCount.incrementAndGet();
                });
                acceptedIndexes[accepted++] = index;
            } catch (RejectedExecutionException expected) {
                rejectedCount.incrementAndGet();
            }
        }

        executor.shutdown();
        check(executor.awaitTermination(60, TimeUnit.SECONDS),
                "all accepted requests complete within 60 sec");
        long finishedAt = System.nanoTime();
        long wallNanos = Math.max(1L,
                finishedAt - plannedStart);
        long gcDelta = gcCollections() - gcBefore;
        int completed = completedCount.get();
        int rejected = rejectedCount.get();
        check(accepted + rejected == offered, "accounted offers");
        check(accepted == completed, "all accepted requests completed");

        System.out.printf(Locale.ROOT,
                "COUNTS offered=%d accepted=%d completed=%d rejected=%d%n",
                offered, accepted, completed, rejected);
        System.out.printf(Locale.ROOT,
                "THROUGHPUT completedPerSecond=%.1f "
                        + "rejectionRate=%.3f%% wallSeconds=%.3f%n",
                completed * 1_000_000_000.0 / wallNanos,
                100.0 * rejected / offered,
                wallNanos / 1_000_000_000.0);

        report("E2E_FROM_PLANNED_ARRIVAL", endToEnd,
                acceptedIndexes, completed);
        report("QUEUE_WAIT", enqueueToStart,
                acceptedIndexes, completed);
        report("SERVICE_TIME", service,
                acceptedIndexes, completed);
        report("PRODUCER_SCHEDULING_LAG", schedulingLag,
                acceptedIndexes, completed);
        System.out.println("GC_MXBEAN_COLLECTION_DELTA=" + gcDelta
                + " (not an allocation-stall counter)");
        System.out.println("NOTE: rejected requests are NOT in latency "
                + "percentiles; inspect rejectionRate alongside p99/p99.9");
        System.out.println("ALL GC LATENCY WORKLOAD CHECKS PASSED");
    }
}
~~~

### 4.3. Lệnh biên dịch và selftest

~~~bash
javac --release 11 -encoding UTF-8 GcTailLatencyLab.java
java GcTailLatencyLab selftest
~~~

**Stdout chính xác:**

~~~text
PASS nearest-rank percentile boundaries
PASS end-to-end decomposition
PASS open-loop schedule arithmetic
ALL LATENCY MATH TESTS PASSED
~~~

Kiểm thử xác nhận ví dụ planned due 1.000s, enqueue 1.004s, start 1.012s, finish 1.019s tạo producer lag **4ms**, queue wait **8ms**, service **7ms**, E2E **19ms**. Nắm vững cách phân rã này giúp tránh quy mọi p99 E2E spike cho GC.

### 4.4. Chạy benchmark có GC logs

~~~bash
# G1:
java -Xms128m -Xmx128m -XX:+UseG1GC \
  -Xlog:gc*,safepoint:file=g1-gc.log:time,uptime,level,tags \
  -cp . GcTailLatencyLab 600 5 4 128

# ZGC trên JDK production-ready, ví dụ JDK 24+:
java -Xms128m -Xmx128m -XX:+UseZGC \
  -Xlog:gc*,safepoint:file=zgc-gc.log:time,uptime,level,tags \
  -cp . GcTailLatencyLab 600 5 4 128
~~~

Các tham số `600 5 4 128` tương ứng **600 arrivals/giây, 5 giây, 4 workers, 128KiB allocation mỗi accepted task**. `-Xms128m -Xmx128m` chỉ là cấu hình minh họa pressure, **không phải khuyến nghị heap size của production**. Vì công việc trong benchmark rất nhỏ, scheduling lag của producer và JIT/GC cũng có thể đóng góp đáng kể.

Trên **JDK 24**, bản code đã được kiểm với lệnh `javac --release 11` và chạy cả G1 lẫn ZGC ở **600 req/s, 2 giây, 4 workers, 128KiB**. Số liệu ở một lần chạy:

~~~text
# G1:
GC_COLLECTORS=G1 Young Generation, G1 Concurrent GC, G1 Old Generation
COUNTS offered=1200 accepted=1200 completed=1200 rejected=0
THROUGHPUT completedPerSecond=600.1 rejectionRate=0.000% wallSeconds=2.000
E2E_FROM_PLANNED_ARRIVAL: p50=0.718ms p99=2.567ms p99.9=4.526ms max=5.594ms
GC_MXBEAN_COLLECTION_DELTA=3 (not an allocation-stall counter)

# ZGC:
GC_COLLECTORS=ZGC Minor Cycles, ZGC Minor Pauses, ZGC Major Cycles, ZGC Major Pauses
COUNTS offered=1200 accepted=1200 completed=1200 rejected=0
THROUGHPUT completedPerSecond=600.3 rejectionRate=0.000% wallSeconds=1.999
E2E_FROM_PLANNED_ARRIVAL: p50=0.812ms p99=2.193ms p99.9=3.332ms max=4.806ms
GC_MXBEAN_COLLECTION_DELTA=22 (not an allocation-stall counter)
~~~

**Chỉ là số liệu quan sát, không phải expected stdout hay so sánh đáng tin giữa hai collector.** Mỗi lần chạy sẽ thay đổi. Chương trình thực tế còn in percentiles `QUEUE_WAIT`, `SERVICE_TIME` và `PRODUCER_SCHEDULING_LAG` cùng dòng kết thúc:

~~~text
ALL GC LATENCY WORKLOAD CHECKS PASSED
~~~

**MXBean chú ý:** số lần collection của G1, ZGC có thể dùng beans cho **cycles và pauses** với semantics khác nhau; không nói rằng 22 của ZGC là «GC tệ hơn 3 của G1». Muốn so STW, xem GC pause events/durations riêng.

## 5. Thu bằng chứng allocation stall qua JFR

### 5.1. Hai loại event

- **`jdk.GCPhasePause`:** một nhóm event chứa thời lượng pause phase, không phải toàn bộ GC cycle duration.
- **`jdk.ZAllocationStall`:** event đặc thù ZGC khi thread phải chờ memory để cấp phát. Nó không là counter chung cho mọi GC hoặc mọi slow allocation.

Event type có thể xuất hiện trong danh sách metadata ngay cả khi **collector đang chạy không phát event đó**; `available=true` không đồng nghĩa đã có stall. Khi cần nhìn **stalls ngắn**, cấu hình `withThreshold(Duration.ZERO)` để tránh threshold mặc định lọc chúng. JFR và bản thân việc thu thập cũng tốn tài nguyên; khi benchmark so collectors, cần cùng instrumentation và cân nhắc đo cả chạy có/không có JFR.

### 5.2. Chương trình GcJfrCapture.java

Ví dụ này sử dụng chương trình `GcTailLatencyLab` ở trên, tạo `Recording`, enable những event type có metadata, dump file `.jfr` và **đọc streaming** để hạn chế memory footprint so với `RecordingFile.readAllEvents`:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.Locale;
import jdk.jfr.EventType;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class GcJfrCapture {
    private static boolean hasEvent(String name) {
        for (EventType type : FlightRecorder.getFlightRecorder().getEventTypes()) {
            if (name.equals(type.getName())) return true;
        }
        return false;
    }

    private static double millis(long nanos) {
        return nanos / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 5) {
            System.err.println("Usage: java GcJfrCapture <file.jfr> "
                    + "<ratePerSecond> <seconds> <workers> <allocKiB>");
            System.exit(2);
            return;
        }
        Path file = Path.of(args[0]);
        boolean pauseAvailable = hasEvent("jdk.GCPhasePause");
        boolean stallAvailable = hasEvent("jdk.ZAllocationStall");

        try (Recording recording = new Recording()) {
            if (pauseAvailable) {
                recording.enable("jdk.GCPhasePause")
                        .withThreshold(Duration.ZERO);
            }
            if (stallAvailable) {
                recording.enable("jdk.ZAllocationStall")
                        .withThreshold(Duration.ZERO);
            }
            recording.start();
            GcTailLatencyLab.main(Arrays.copyOfRange(args, 1, 5));
            recording.stop();
            recording.dump(file);
        }

        long pauses = 0;
        long pauseNanos = 0;
        long stalls = 0;
        long stallNanos = 0;
        long maxStallNanos = 0;
        try (RecordingFile recording = new RecordingFile(file)) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                String name = event.getEventType().getName();
                long nanos = event.getDuration().toNanos();
                if ("jdk.GCPhasePause".equals(name)) {
                    pauses++;
                    pauseNanos += nanos;
                } else if ("jdk.ZAllocationStall".equals(name)) {
                    stalls++;
                    stallNanos += nanos;
                    maxStallNanos = Math.max(maxStallNanos, nanos);
                }
            }
        }

        System.out.printf(Locale.ROOT,
                "JFR_GC_PHASE_PAUSE available=%s count=%d sumMs=%.3f%n",
                pauseAvailable, pauses, millis(pauseNanos));
        System.out.printf(Locale.ROOT,
                "JFR_Z_ALLOCATION_STALL available=%s count=%d "
                        + "sumMs=%.3f maxMs=%.3f%n",
                stallAvailable, stalls,
                millis(stallNanos), millis(maxStallNanos));
        System.out.println("NOTE: zero events is not proof of zero "
                + "GC cost or zero stalls; check collector, settings and load");
        System.out.println("ALL JFR EVIDENCE CHECKS PASSED");
    }
}
~~~

### 5.3. Chạy cả workload và JFR

~~~bash
javac --release 11 --add-modules jdk.jfr -encoding UTF-8 \
  GcTailLatencyLab.java GcJfrCapture.java

java --add-modules jdk.jfr -Xms128m -Xmx128m -XX:+UseG1GC \
  -cp . GcJfrCapture g1-evidence.jfr 600 5 4 128

java --add-modules jdk.jfr -Xms128m -Xmx128m -XX:+UseZGC \
  -cp . GcJfrCapture zgc-evidence.jfr 600 5 4 128
~~~

**Dòng kết thúc ổn định khi JFR test thành công:**

~~~text
NOTE: zero events is not proof of zero GC cost or zero stalls; check collector, settings and load
ALL JFR EVIDENCE CHECKS PASSED
~~~

`JFR_GC_PHASE_PAUSE` và `JFR_Z_ALLOCATION_STALL` có **count/sumMs/maxMs thay đổi** theo runtime/load, vì vậy **không có expected exact numbers**. Ngay cả khi `available=true` và `count=0`, vẫn cần kiểm workload, GC hiện hành, threshold và các events thực được ghi. Đừng lấy **tổng thread-stall durations** làm wall-clock downtime: nếu 8 threads cùng stall 10ms, tổng có thể là 80 thread-ms dù wall clock chỉ khoảng 10ms.

### 5.4. JFR CLI

Có thể kiểm file đã ghi:

~~~bash
jfr summary zgc-evidence.jfr
jfr print --events jdk.ZAllocationStall,jdk.GCPhasePause zgc-evidence.jfr
~~~

Trên JDK hỗ trợ, `jfr view` cho phép các bảng tổng hợp. Chọn lọc events/đầu ra cho file lớn; không in file JFR có dữ liệu nhạy cảm vào log công khai. File JFR có thể chứa stack traces, thread/class names và business metadata; quản lý quyền đọc và retention.

## 6. Unified GC logging và timeline

Dùng các flags được hỗ trợ bởi HotSpot hiện hành:

~~~bash
java -Xlog:help

# G1:
java -XX:+UseG1GC -Xms128m -Xmx128m \
  -Xlog:gc*,safepoint:file=g1-gc.log:time,uptime,level,tags \
  -cp . GcTailLatencyLab 600 5 4 128

# ZGC:
java -XX:+UseZGC -Xms128m -Xmx128m \
  -Xlog:gc*,gc+alloc=debug,safepoint:file=zgc-gc.log:time,uptime,level,tags \
  -cp . GcTailLatencyLab 600 5 4 128
~~~

`gc*` chứa các GC tag combinations; `safepoint` cho thông tin các lần application threads được dừng. `gc+alloc=debug` hữu ích trên những ZGC builds có messages về allocation stalls; **log tags/format có thể khác giữa JDK versions**, cần dùng `-Xlog:help` và tránh parser dựa trên một thông điệp cố định.

| Bằng chứng | Cần đọc |
| --- | --- |
| G1 `Pause Young`, `Pause Full` | Stop-the-world pause duration, cause, Full GC/evacuation failure. |
| ZGC `Pause ...` | Những phần STW ngắn, không dùng toàn cycle duration thay thế. |
| ZGC `Concurrent ...` | Công việc đồng thời; không mặc định dừng tất cả requests suốt thời gian đó. |
| `Allocation Stall` lines / JFR ZAllocationStall | Mutator chờ memory, có thể kéo tail dù pause thấp. |
| `gc+heap` | Heap used/capacity và headroom. |
| `gc+cpu` | `User/Sys/Real`, gợi ý CPU/OS scheduling. |
| `safepoint` | Những lần JVM dừng mutators do GC hoặc công việc khác. |
| JFR `jdk.ThreadPark` / monitor events (nếu bật) | Queue/lock waits không tự là GC. |

**Đối chiếu timestamp mới đủ chứng cứ.** `System.nanoTime` là monotonic clock trong process; GC log thường có uptime/wall-clock decorators và JFR có timestamps riêng. Khi ghép với client trace khác host, cần một time mapping/correlation đúng, không tự xem `nanoTime` là epoch milliseconds.

## 7. Quy trình benchmark thực tế

### 7.1. Đặt SLO trước khi đo

Ví dụ **minh họa** cho một API:

~~~text
Offered sustained load   = 1,500 requests/second
p99 end-to-end           < 35 ms
p99.9 end-to-end         < 80 ms
Successful throughput    >= 1,495 requests/second
Rejected/timeout/failed  <= 0.1%
CPU and memory           <= allocated capacity; no OOM
~~~

Đây không phải SLO mặc định cho ứng dụng Java; mỗi hệ thống có yêu cầu riêng. Nếu request timeout hoặc reject, **không bỏ hẳn khỏi báo cáo**; quy định rõ chúng tính vào SLO failure budget và cách đo tail với incomplete requests.

### 7.2. Kịch bản tối thiểu

1. **Baseline:** không có load pressure/hoặc rate thấp hơn capacity; quan sát service time và GC bình thường.
2. **Sustained:** rate mục tiêu đủ dài để có nhiều GC cycles sau warm-up.
3. **Burst:** traffic đột ngột cao hơn baseline; xem queue buildup, allocation spikes và tail.
4. **Overload:** vượt capacity có kiểm soát; phải thấy rejection/timeout, throughput collapse và drain behavior.
5. **Live-set change:** giữ cache/object graph sống lâu hơn, xem headroom và concurrent collector.
6. **Memory pressure:** thử heap sizes thích hợp với sản phẩm, tránh chỉ chạy 128MiB demo rồi khẳng định scalability.
7. **Multi-trial:** ít nhất vài repetitions mỗi cấu hình, thay đổi thứ tự G1/ZGC để hạn chế time-dependent noise.
8. **Independent load client:** đủ CPU/connection slots, không coordinated omission, log dropped arrivals.
9. **Same runtime:** JDK vendor/build/OS, CPU quota, GC log/JFR settings, heap, threads và request mix đều được ghi nhận.
10. **Decision:** chọn theo application SLO + throughput + error rate + headroom, không theo mỗi GC pause.

### 7.3. Đối chiếu CPU và allocation

Nếu p99 tăng nhưng GC pause không tăng, kiểm:
- CPU throttling container, host utilization, run queue;
- Java monitors/locks và thread pool queue;
- OS page faults/heap commit/uncommit;
- Memory headroom và ZGC allocation-stall events;
- Allocation rate cao khiến GC concurrent không theo kịp;
- Large objects, humongous G1 allocations hoặc Full GC;
- JIT warm-up, deoptimization, class loading và noisy neighbors.

Tăng `-Xmx` có thể giúp **nếu đúng là thiếu heap headroom**, nhưng tiêu tốn RAM; `-Xms = -Xmx` và `-XX:+AlwaysPreTouch` có thể giảm các độ trễ do commit/page-in trong một số tình huống và tăng startup/memory footprint. **Không đổ tất cả lỗi cho GC** và không bật nhiều tuning flags khi chưa có log chứng minh.

## 8. Hướng xử lý theo triệu chứng

| Hiện tượng | Giả thuyết cần xác minh |
| --- | --- |
| GC STW thấp, p99.9 cao, ZGC allocation stalls có | Allocation không có sẵn memory; thử tăng headroom, giảm allocation rate, kiểm CPU concurrent GC. |
| GC STW cao trùng request tail spikes | Có thể liên quan pause; so timestamps, queue wait, GC cause. |
| Service p99 thấp nhưng E2E p99 cao | Queue hoặc producer/OS scheduling là nguồn trễ lớn. |
| p99 tốt, rejection rate tăng | Accepted-only histogram che lỗi; SLO có thể fail. |
| Offered rate tăng, completed throughput đứng yên | Capacity saturation/queue/reject/generator bottleneck. |
| G1 Full GC/evacuation failure | Heap pressure, humongous allocations, allocation rate và live-set cần điều tra. |
| JFR type ZAllocationStall available, count=0 | Chưa đủ chứng minh không stall; event type không nhất thiết emitted bởi current collector. |
| `GC_MXBEAN_COLLECTION_DELTA` ZGC lớn hơn G1 | Không đủ kết luận: beans có thể đại diện cycle/pauses khác nhau. |
| Application chậm, logs GC bình thường | OS/network/locks/IO/CPU/JIT có thể chi phối. |

Cần chú ý **p99(E2E) không phải tổng p99 các thành phần**. Thay vì cộng các percentiles, trích những request thực sự chậm nhất, tìm timeline của chúng, sau đó xem GC log/JFR trong cùng thời điểm.

## 9. Sai lầm thường gặp

1. **Chỉ đo GC pause và gọi đó là user latency.** Request có thể chậm do allocation stall hoặc queueing.
2. **Lấy toàn bộ ZGC cycle duration làm STW pause.** Concurrent work không dừng toàn JVM suốt cycle.
3. **Bỏ qua coordinated omission** khi generator closed-loop ngừng gửi lúc server bị stall.
4. **Không báo rejected/timeout** và tuyên bố p99 accepted là p99 mọi request.
5. **Trung bình p99 của nhiều máy/time windows** thay vì merge histograms/raw samples.
6. **Đo p99.9 trên quá ít request**, không có khoảng tin cậy hay repetitions.
7. **Nhầm service time với E2E**, bỏ qua queue và scheduled arrival.
8. **Dùng `System.currentTimeMillis` để đo microsecond duration** thay vì `System.nanoTime`.
9. **Bỏ qua producer lag** của load generator chung JVM và coi mọi spike là server.
10. **Nhầm MXBean collection count với số pause cùng ý nghĩa giữa collectors**.
11. **Coi 0 JFR ZAllocationStall là 0 allocation stalls** mà không kiểm event settings, collector.
12. **Cộng thread-stall durations của nhiều threads thành wall-clock downtime**.
13. **Tuning `-XX:MaxGCPauseMillis` như hard realtime guarantee** dù đây là soft goal.
14. **Không cố định heap/JDK/CPU quota** khi so G1 với ZGC.
15. **Đem behavior ZGC experimental JDK11 so trực tiếp với JDK24 generational** như cùng implementation.
16. **Dùng `ZGenerational` trên JDK24+** dù đã bị xóa.
17. **Chạy cả hai benchmarks đồng thời trên một host** làm GC/CPU cạnh tranh.
18. **Không warm-up** và chỉ chạy thử 1–2 giây để quyết định sản phẩm.
19. **Chạy load generator thiếu CPU**, bỏ mất planned arrivals mà không báo dropped iterations.
20. **Coi allocation rate cao là memory leak** mà không có retained heap/reachability evidence.
21. **Đọc toàn bộ JFR file lớn vào RAM** thay vì streaming.
22. **Không giới hạn logs/tracing** khiến chính công cụ đo tạo ra overhead.
23. **Log dữ liệu nhạy cảm** trong stack trace/request metadata ra file JFR không kiểm soát quyền.
24. **Tự thay hàng loạt GC tuning flags trước khi xác định bottleneck**.
25. **Bỏ qua total successful throughput** khi chấm collector chỉ theo minimum pause.
26. **Không kiểm allocated heap headroom và concurrent GC CPU** khi có ZGC stalls.

## 10. Câu hỏi tự đánh giá

**1.** p99.9 là gì? — Percentile 99,9%; không có nghĩa mọi request đều nhỏ hơn giá trị, và cần nhiều observations để ước lượng ổn định.

**2.** p99 E2E có bằng p99(queue) + p99(service) không? — Không. Các percentile của biến khác nhau không cộng được như duration của một request cụ thể.

**3.** Coordinated omission đến từ đâu? — Generator đợi request trước xong rồi mới gửi tiếp; khi server bị dừng, nhiều intended arrivals không được phát/đo.

**4.** Open-loop 500 req/s có planned interval bao nhiêu? — **2 ms** giữa slots.

**5.** Vì sao phải báo rejections cùng latency? — Vì requests bị từ chối không có successful completion latency, nên bỏ qua chúng có thể làm histogram trông đẹp giả.

**6.** Allocation stall là gì? — Java thread phải **chờ heap memory** để cấp phát, có thể xảy ra khi STW pauses rất ngắn.

**7.** Event ZGC nào có thể hỗ trợ tìm allocation stalls? — `jdk.ZAllocationStall` nếu event type/collector/runtime hỗ trợ và enabled phù hợp.

**8.** `jdk.GCPhasePause` và `jdk.GarbageCollection` có cùng nghĩa duration không? — Không. Một là pause phase, còn GC collection/cycle có thể chứa concurrent work.

**9.** Từ JDK 24, `-XX:+ZGenerational` còn cần không? — Không; tùy chọn đó đã bị loại bỏ, ZGC hiện chỉ generational.

**10.** Vì sao Java compile `--release 11` chưa đủ để xác nhận ZGC Java11 runtime? — Compile target chỉ kiểm source/API; GC phụ thuộc runtime JDK/vendor/version và platform.

**11.** `GC_MXBEAN_COLLECTION_DELTA` có đo thời gian allocation stall không? — Không; đó chỉ là chênh lệch bộ đếm GC MXBeans với semantics tùy implementation.

**12.** Một request có producer 4ms, queue 8ms, service 7ms thì E2E bao nhiêu? — **19ms** từ planned arrival đến completion.

**13.** Khi ZGC pause thấp, p99 cao, cần kiểm gì tiếp? — Allocation stalls, heap headroom, concurrent GC CPU, queue wait, OS scheduling và service time.

**14.** Có thể kết luận collector tốt nhất từ benchmark 2 giây không? — Không; cần warm-up, sustained/burst, sample size, repetitions và application SLO.

## 11. Checklist hoàn thành

- [ ] Đặt tiêu chí `p99, p99.9, completed throughput, rejected/timeout rate` trước khi so GC.
- [ ] Đo từ planned arrival trong open-loop hoặc dùng load generator độc lập phù hợp thực tế.
- [ ] Kiểm toán percentile nearest-rank và số samples đủ lớn.
- [ ] Báo accepted/completed/rejected, không chỉ successful histogram.
- [ ] Phân rã E2E, queue wait, service time và producer scheduling lag.
- [ ] Phân biệt ZGC concurrent cycle, STW pause và allocation stall.
- [ ] Thu `-Xlog:gc*,safepoint`, JFR GCPhasePause và ZAllocationStall nếu có.
- [ ] Không suy ra «không stall» từ event count bằng 0 khi chưa kiểm configuration.
- [ ] Không so MXBean counts G1 và ZGC như cùng một đơn vị pauses.
- [ ] Chạy `javac --release 11` và cả selftest, G1/ZGC runs phù hợp runtime.
- [ ] Test đủ lâu và lặp lại; tránh kết luận từ 2-second in-process demonstration.
- [ ] Ghi JDK vendor/version, heap, GC flags, CPU quota, allocation/live set, errors.
- [ ] Không dùng flags cũ `ZGenerational` trên JDK 24+.
- [ ] Bảo vệ dữ liệu nhạy cảm trong logs/JFR, quản lý retention và read permissions.

## 12. Tài liệu hiện hành và chính thức

1. [Java SE 11 HotSpot VM Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/11/gctuning/) — throughput và latency.
2. [Java SE 26 HotSpot VM Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/26/gctuning/) — collectors và hướng tuning mới.
3. [Java SE 26 G1 GC Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html) — Full GC, pauses, heap and CPU.
4. [Java SE 24 Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html) — concurrent GC, headroom, `ZGenerational` removed.
5. [OpenJDK JEP 490 — Remove the Non-Generational Mode of ZGC](https://openjdk.org/jeps/490).
6. [Java SE 11 java tool — Unified logging -Xlog](https://docs.oracle.com/en/java/javase/11/tools/java.html).
7. [Java SE 11 JFR Recording API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html).
8. [Java SE 11 JFR RecordingFile API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
9. [Java SE 11 GarbageCollectorMXBean API](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html).
10. [Java SE 25 jfr CLI command reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html).
11. [Inside Java — How ZGC Allocates Memory for the Java Heap](https://inside.java/2025/04/17/zgc-deep-dive/) — allocation stall khi JVM thiếu bộ nhớ cấp phát.
12. [HdrHistogram JavaDoc — coordinated omission correction](https://hdrhistogram.github.io/HdrHistogram/JavaDoc/).
13. [JFR event catalog JDK versions](https://sap.github.io/jfrevents/) — kiểm metadata event `jdk.ZAllocationStall` theo bản JDK.
