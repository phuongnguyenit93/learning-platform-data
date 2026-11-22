# Đánh giá ứng dụng Java trong container với các mức CPU và bộ nhớ khác nhau

## 1. Bài thực hành tổng hợp: cùng ứng dụng, khác tài nguyên, kết luận dựa trên số liệu

Một ứng dụng Java chạy ổn khi Docker container có **2 CPU và 1 GiB RAM** có thể phản hồi chậm, thường xuyên bị throttling hoặc thậm chí bị kết thúc khi chỉ được cấp **0,5 CPU và 256 MiB RAM**. Ngược lại, tăng giới hạn tài nguyên không mặc nhiên giúp ứng dụng nhanh hơn nếu nó đang chờ I/O, khóa, database hoặc không sử dụng hết tài nguyên được cấp.

Câu hỏi của bài thực hành:

1. Khi giữ nguyên Java code và workload, thay đổi **CPU quota** ảnh hưởng throughput, latency và thời gian throttling thế nào?
2. Khi giữ nguyên CPU, heap và workload, thay đổi **container memory limit** có thực sự cải thiện hiệu năng không, hay chỉ tạo thêm headroom?
3. Khi thay **`-Xmx`/heap policy**, số lần GC, latency và rủi ro OOM thay đổi thế nào?
4. Có thể giải thích sự khác nhau giữa **host CPU count**, **`Runtime.availableProcessors()`**, **CPU usage**, **heap usage** và **memory cgroup usage** hay không?
5. Cách nào phân biệt một **Java `OutOfMemoryError`** với tình huống **kernel/container OOM kill**?
6. Dựa vào số liệu nào để chọn cấu hình nhỏ nhất đáp ứng mục tiêu throughput, độ trễ, ổn định và chi phí?

Chủ đề nằm trong phần **Thực hành tổng hợp** của module **Java 10**. Java 10 có cải tiến HotSpot **container awareness** (nhận diện CPU và memory constraints trên Docker/cgroups). Những nguyên tắc đo hiệu năng, cấu hình Docker, `UseContainerSupport`, `ActiveProcessorCount`, `MaxRAMPercentage` và các APIs quan sát được dùng trong bài **vẫn áp dụng với các JDK hiện đại**. Phần thực hành chọn **JDK 17+** để có một runtime ổn định, không đề xuất sử dụng bản Java 10 cũ cho hệ thống mới.

**Nguyên tắc đánh giá:** chỉ kết luận sau khi đã xác minh **giới hạn thực sự được kernel áp dụng**, đo **nhiều lần**, dùng **cùng workload**, và hiểu **định nghĩa từng metric**. Đừng chọn cấu hình qua một lần chạy hoặc một con số `docker stats` đơn lẻ.

## 2. Phân biệt CPU và bộ nhớ ở bốn tầng

### 2.1. Host, container, JVM, ứng dụng

~~~text
Host / VM / Kubernetes node
  |-- logical CPUs, physical RAM, NUMA, scheduler, contention
  |
  +-- Linux container / cgroup
       |-- CPU quota + period
       |-- cpuset / affinity
       |-- CPU shares / weight
       |-- memory hard limit, memory usage, memory events
       |
       +-- HotSpot JVM (JDK version/build cụ thể)
            |-- container support và active processor count
            |-- -Xms, -Xmx hoặc MaxRAMPercentage
            |-- GC threads, JIT/compiler threads, platform threads
            |-- Java heap, metaspace, code cache, direct/native memory
            |
            +-- Ứng dụng
                 |-- concurrency, CPU work, I/O waits
                 |-- queues, caches, retained objects
                 |-- throughput, latency p50/p95/p99, error rate
~~~

Bốn tầng tương tác với nhau nhưng không có metric duy nhất mô tả tất cả.

| Đại lượng | Trả lời câu hỏi | Không tự chứng minh |
| --- | --- | --- |
| Host logical CPU count | OS/VM nhìn thấy bao nhiêu logical CPUs? | Container có quyền dùng hết |
| CPU quota/period | Mỗi chu kỳ container được tiêu thụ bao nhiêu CPU time? | Bao nhiêu core vật lý độc quyền |
| Cpuset/affinity | Threads được schedule trên những logical CPUs nào? | Có bao nhiêu CPU time không bị tranh chấp |
| CPU shares/weight | Cgroup được ưu tiên tương đối thế nào khi cạnh tranh? | Một hard limit tính bằng CPU |
| `availableProcessors()` | JVM chọn số nguyên processors nào cho ergonomics? | CPU usage, quota dạng phân số |
| Java heap max/used | Vùng heap Java tối đa/đang dùng bao nhiêu? | Tổng memory của container |
| Container memory.current | Bao nhiêu memory đang được charge trong cgroup? | Chỉ riêng Java heap |
| GC count/time | Collector đã có bao nhiêu hoạt động đo được? | Tự nó giải thích mọi độ trễ |
| Throughput | Một đơn vị thời gian hoàn tất bao nhiêu task/request? | Chất lượng của những tail latencies |
| p95/p99 latency | Phần lớn yêu cầu hoàn tất nhanh tới đâu? | Mọi yêu cầu đều dưới ngưỡng đó |

### 2.2. Quota CPU có thể là phân số

Trên Linux cgroup v2, file `cpu.max` có thể chứa:

~~~text
150000 100000
~~~

Công thức:

~~~text
CPU-equivalent quota = quota_us / period_us

150000 / 100000 = 1.50 CPU
 50000 / 100000 = 0.50 CPU
200000 / 100000 = 2.00 CPU
~~~

Một container có quota **1,5 CPU** không sở hữu “một core rưỡi” vật lý. Quota giới hạn **ngân sách CPU time**, có thể được tiêu thụ nhanh hơn wall time khi nhiều threads chạy đồng thời. Khi hết quota trong chu kỳ, scheduler có thể **throttle** cgroup.

`Runtime.getRuntime().availableProcessors()` trả một **số nguyên** và có thể phản ánh quota/cpuset/affinity hoặc override, tùy bản HotSpot và cgroup. Nếu nó là 2 khi quota bằng 1,5, **không** có nghĩa container đã được cấp đúng 2,0 CPU time liên tục.

### 2.3. CPU shares không phải hard cap

Docker `--cpu-shares` hoặc cgroup v2 `cpu.weight` biểu diễn trọng số tương đối trong tình trạng CPU bị tranh chấp; chúng **không** tương đương `--cpus`. Các bản JDK mới cũng đã thay đổi cách dùng CPU shares khi tính active processor count.

Khi thí nghiệm, dùng `--cpus` để tạo quota rõ ràng. Không đổi `--cpu-shares=256` thành một tuyên bố “đã giới hạn xuống 0,25 CPU”.

### 2.4. Memory limit không phải Java heap max

Ví dụ:

~~~text
Docker --memory=512m
Java -Xmx256m
~~~

`512m` là giới hạn memory của container theo Docker/kernel; `256m` là giới hạn **Java heap**. Những vùng memory còn có thể bao gồm metaspace, code cache, thread stacks, direct NIO buffers, JNI/native libraries, memory-mapped pages và các charges khác của cgroup.

Nếu heap còn chỗ nhưng total memory bị charge vượt điều kiện limit, kernel có thể kết thúc process. Ngược lại, `-Xmx` quá nhỏ có thể dẫn tới `OutOfMemoryError: Java heap space` **trước** khi container chạm hard limit.

## 3. Đặt mục tiêu đánh giá trước khi chạy

Đừng bắt đầu bằng việc đổi CPU/RAM ngẫu nhiên rồi nhìn kết quả.

### 3.1. Tách tiêu chí chức năng và phi chức năng

**Chức năng:**

- Mọi task hoàn thành thành công.
- Kết quả tính toán/chuyển đổi đúng, không mất hay lặp.
- Không có exceptions bất thường, không bị OOM kill.
- Không phụ thuộc kết quả vào thứ tự scheduler ngoài hợp đồng chương trình.

**Phi chức năng:**

- Throughput tối thiểu bao nhiêu requests/tasks mỗi giây?
- p95 hoặc p99 latency phải nhỏ hơn ngưỡng nào?
- Có chấp nhận CPU throttling hay không, và ở mức độ nào?
- Memory peak phải còn bao nhiêu headroom dưới cgroup hard limit?
- Có cho phép swap không? Có deadline GC pause hoặc startup không?
- Cost per useful unit of work và nguồn lực tối đa là gì?

Một cấu hình **nhanh nhất** chưa chắc là cấu hình **tốt nhất**. Nếu tăng CPU từ 2 lên 4 mà throughput chỉ tăng rất ít, việc thêm CPU có thể không đáng chi phí.

### 3.2. Chỉ so sánh khi workload tương đương

Giữ cố định trong một phép thử:

- Cùng mã nguồn, cùng JDK vendor/build và image digest.
- Cùng dữ liệu đầu vào, số task, số vòng tính, độ lớn retained working set.
- Cùng số worker threads **ở vòng thí nghiệm kiểm ảnh hưởng CPU quota**.
- Cùng heap flags/GC policy và mức CPU khi **chỉ kiểm ảnh hưởng container memory**.
- Cùng warm-up, thời gian đo, host/nút nếu có thể.
- Cùng chính sách swap, filesystem, background load và số lần lặp.
- Cùng cách đo latency, throughput và memory usage.

**Chỉ thay một biến mỗi vòng thử** để không lẫn nguyên nhân. Sau đó mới chạy ma trận phối hợp và thử workload thật.

### 3.3. Không dùng kết quả một lần chạy làm kết luận

JIT warm-up, class loading, GC, CPU contention của host, hypervisor scheduling, cache, temperature và background traffic đều có thể thay đổi kết quả.

Quy trình tối thiểu: warm-up hợp lý, chạy nhiều lượt độc lập (ví dụ năm lượt), trình bày median, dải biến động và p95/p99 latency của từng lượt. Không chọn duy nhất lần chạy nhanh nhất hoặc một sample may mắn.

Nếu workload thật có tính chu kỳ, hãy đo các giai đoạn steady state và spikes một cách riêng biệt.

## 4. Ma trận thử nghiệm có kiểm soát

### 4.1. Vòng A — thay CPU, giữ memory và workload

| Kịch bản | CPU quota | Container memory | Java heap | Mục đích |
| --- | ---: | ---: | ---: | --- |
| A1 | 0,5 CPU | 512 MiB | `-Xmx256m` | Quan sát thiếu CPU/throttling |
| A2 | 1 CPU | 512 MiB | `-Xmx256m` | Mốc đối chiếu |
| A3 | 2 CPU | 512 MiB | `-Xmx256m` | Kiểm mức scaling |
| A4 | 4 CPU | 512 MiB | `-Xmx256m` | Kiểm lợi ích tăng thêm |

Cần xác minh host/VM thực có đủ logical CPUs để thử 4 CPU. Nếu host không đủ, kết quả A4 không phản ánh riêng quota được chọn.

**Giữ nguyên:** JDK, `-Xms`, `-Xmx`, số worker threads, task count, rounds, retained memory, churn allocation, swap và workload.

**Đo:** elapsed time, throughput, p50/p95/p99, CPU usage, `cpu.stat` throttling, `availableProcessors`, GC.

### 4.2. Vòng B — thay container memory, giữ heap và CPU

| Kịch bản | CPU quota | Container memory | Java heap | Mục đích |
| --- | ---: | ---: | ---: | --- |
| B1 | 1 CPU | 256 MiB | `-Xmx128m` | Kiểm headroom/OOM |
| B2 | 1 CPU | 512 MiB | `-Xmx128m` | Cùng heap, nới memory cgroup |
| B3 | 1 CPU | 1 GiB | `-Xmx128m` | Kiểm giới hạn memory có là bottleneck không |

**Quan trọng:** nếu ứng dụng trước đó không gần limit và `-Xmx`/workload giống nhau, việc tăng `--memory` **có thể gần như không tăng throughput**. Điều đó là một kết quả bình thường, không phải bài thử thất bại.

Nếu B1 thường xuyên OOM hoặc phải reclaim/swap và B2 ổn định, kết luận nằm ở **memory headroom và sự ổn định**, không phải “512 MiB làm CPU chạy nhanh gấp đôi”.

### 4.3. Vòng C — thay heap policy trong cùng container

| Kịch bản | CPU | Memory | Heap | Mục đích |
| --- | ---: | ---: | ---: | --- |
| C1 | 1 CPU | 512 MiB | `-Xmx128m` | Kiểm GC dưới heap hẹp |
| C2 | 1 CPU | 512 MiB | `-Xmx256m` | Kiểm GC và headroom native |
| C3 | 1 CPU | 512 MiB | `-XX:MaxRAMPercentage=50` | Kiểm heap sizing tự động |

Không nên đặt cùng lúc `-Xmx` và `MaxRAMPercentage` khi muốn so ảnh hưởng của chính sách sizing mà không hiểu flag priority. Với C3, trước tiên xem heap max thực bằng `-XshowSettings:vm` hoặc `MemoryMXBean`.

**Cảnh báo:** nếu heap tăng làm GC ít hơn nhưng tổng RSS/cgroup tăng sát limit, rủi ro OOM kill có thể cao hơn. Cần kiểm cả **GC và container memory**, không chỉ số lần collection.

### 4.4. Vòng D — giữ resources, thay concurrency

Dùng cùng CPU/memory, thay số worker threads từ 1 → 2 → 4 → 8, giữ tổng công việc.

**Mục tiêu:** biết tăng concurrency tới đâu cải thiện throughput và từ đâu làm queueing, context switching, GC hoặc throttling tệ hơn.

Số threads **không phải số CPUs**. Java có thể tạo 8 workers trong quota 1 CPU, nhưng 8 workers không tạo thêm CPU time. Với I/O-bound workload, nhiều threads có thể hữu ích; với CPU-bound workload, quá nhiều runnable threads thường không tăng capacity tương ứng.

## 5. Chương trình Java 17+ chạy độc lập để đo CPU, heap và workload

Bài thực hành dùng một chương trình **không cần Maven/Gradle hay server bên ngoài**. Chương trình có hai chế độ:

- `selftest`: kiểm công thức và logic cơ bản với **stdout chính xác**, không phụ thuộc máy.
- `bench`: tạo một đợt task có CPU work, bộ nhớ giữ lại và một lượng cấp phát tạm; in số liệu đo **phụ thuộc môi trường**.

Với phép đo bench, chương trình sử dụng:

- `Executors.newFixedThreadPool` cho số workers cố định.
- Một phép tính CPU bằng các phép toán `long` và rotate, giữ kết quả để tránh coi CPU work là vô dụng.
- Các mảng `byte[]` 1 MiB giữ sống và chạm một byte trên mỗi trang 4 KiB nhằm tạo working set.
- Một mảng tạm mỗi task khi `churnKiB` lớn hơn 0 để tạo allocation pressure lên Java heap.
- `System.nanoTime()` cho elapsed time và latency.
- `Runtime.availableProcessors()` và `MemoryMXBean` cho góc nhìn JVM.
- `GarbageCollectorMXBean` cho delta số collections khi API cung cấp.
- p50/p95/p99 dùng **nearest-rank percentile** trên độ trễ đã sắp xếp.

**Giới hạn của phép đo:** đây là **batch/burst workload**, tất cả tasks được submit trong một đợt. Latency tính từ **lúc submit** tới **lúc hoàn tất**, nên bao gồm queue waiting và CPU/memory work. Nó không phải latency của một HTTP service thực hoặc kiểm thử steady-state arrival rate. Muốn đánh giá một dịch vụ thật, cần load generator, traffic profile và cả upstream/downstream metrics.

### 5.1. Mã hoàn chỉnh: ContainerResourceLab.java

Lưu file **`ContainerResourceLab.java`** theo UTF-8:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class ContainerResourceLab {

    private static final int MIB = 1024 * 1024;
    private static final int PAGE = 4096;

    private ContainerResourceLab() {
    }

    record Sample(long latencyNs, long checksum) {
    }

    static int positiveInt(
            String value, String name, int min, int max) {
        final int n;
        try {
            n = Integer.parseInt(value);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    name + " must be an integer", ex);
        }
        if (n < min || n > max) {
            throw new IllegalArgumentException(
                    name + " must be between " + min
                    + " and " + max);
        }
        return n;
    }

    static double cpuEquivalent(
            long quotaUs, long periodUs) {
        if (quotaUs <= 0 || periodUs <= 0) {
            throw new IllegalArgumentException(
                    "invalid CPU quota or period");
        }
        return (double) quotaUs / periodUs;
    }

    static long squares(int n) {
        long sum = 0;
        for (int i = 1; i <= n; i++) {
            sum += (long) i * i;
        }
        return sum;
    }

    static long percentileNs(long[] sorted, int percent) {
        if (sorted.length == 0
                || percent < 1 || percent > 100) {
            throw new IllegalArgumentException(
                    "invalid percentile");
        }
        int rank = (int) Math.ceil(
                percent * sorted.length / 100.0);
        return sorted[Math.max(0, rank - 1)];
    }

    static void selftest() {
        System.out.printf(
                Locale.ROOT, "quotaEquivalent=%.2f%n",
                cpuEquivalent(150_000, 100_000));
        System.out.println("sumSquares10=" + squares(10));
        System.out.println("oneMiBBytes=" + MIB);
        long[] example = {
                10_000_000L, 20_000_000L, 30_000_000L
        };
        System.out.println(
                "sampleP95Ms="
                + percentileNs(example, 95) / 1_000_000L);
    }

    static byte[][] retainWorkingSet(int retainedMiB) {
        byte[][] blocks = new byte[retainedMiB][];
        for (int i = 0; i < retainedMiB; i++) {
            byte[] block = new byte[MIB];
            for (int p = 0; p < block.length; p += PAGE) {
                block[p] = 1;
            }
            blocks[i] = block;
        }
        return blocks;
    }

    static long runWork(
            int rounds, byte[][] retained, int churnKiB) {
        long x = 0x1234ABCDL;

        for (int i = 1; i <= rounds; i++) {
            x = Long.rotateLeft(
                    x ^ (i * 0x9E3779B97F4A7C15L),
                    13) + 0xC2B2AE3D27D4EB4FL;
        }

        // Đọc các trang của working set đang được giữ sống.
        for (byte[] block : retained) {
            for (int p = 0; p < block.length; p += PAGE) {
                x += block[p] & 0xffL;
            }
        }

        // Tạo allocation tạm nhằm gây áp lực GC có kiểm soát.
        if (churnKiB > 0) {
            byte[] temporary = new byte[churnKiB * 1024];
            for (int p = 0; p < temporary.length; p += PAGE) {
                temporary[p] = (byte) ((p / PAGE + 1) & 127);
                x += temporary[p] & 0xffL;
            }
        }
        return x;
    }

    static long gcCount() {
        long total = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = bean.getCollectionCount();
            if (count >= 0) {
                total += count;
            }
        }
        return total;
    }

    static void bench(
            int workers,
            int tasks,
            int rounds,
            int retainedMiB,
            int churnKiB) throws Exception {

        byte[][] retained = retainWorkingSet(retainedMiB);
        ExecutorService pool =
                Executors.newFixedThreadPool(workers);

        long[] latencyNs = new long[tasks];
        long gcBefore = gcCount();
        long startNs = System.nanoTime();

        try {
            List<Future<Sample>> futures =
                    new ArrayList<>(tasks);

            for (int i = 0; i < tasks; i++) {
                final long submittedAt = System.nanoTime();
                futures.add(pool.submit(() -> {
                    long result = runWork(
                            rounds, retained, churnKiB);
                    return new Sample(
                            System.nanoTime() - submittedAt,
                            result);
                }));
            }

            long checksum = 0;
            for (int i = 0; i < tasks; i++) {
                Sample sample = futures.get(i).get();
                latencyNs[i] = sample.latencyNs();
                checksum += sample.checksum();
            }

            long elapsedNs =
                    Math.max(1, System.nanoTime() - startNs);
            long gcAfter = gcCount();
            Arrays.sort(latencyNs);

            MemoryUsage heap = ManagementFactory
                    .getMemoryMXBean()
                    .getHeapMemoryUsage();

            double elapsedSec = elapsedNs / 1_000_000_000.0;
            double throughput = tasks / elapsedSec;

            System.out.printf(
                    Locale.ROOT,
                    "configuration=workers:%d,tasks:%d,"
                    + "rounds:%d,retainedMiB:%d,churnKiB:%d%n",
                    workers, tasks, rounds,
                    retainedMiB, churnKiB);

            System.out.println(
                    "jvmAvailableProcessors="
                    + Runtime.getRuntime()
                            .availableProcessors());

            System.out.println(
                    "heapMaxMiB="
                    + (heap.getMax() < 0
                    ? "unknown"
                    : Long.toString(heap.getMax() / MIB)));

            System.out.println(
                    "heapUsedMiB="
                    + heap.getUsed() / MIB);

            System.out.printf(
                    Locale.ROOT,
                    "elapsedSeconds=%.3f%n",
                    elapsedSec);

            System.out.printf(
                    Locale.ROOT,
                    "throughputTasksPerSecond=%.2f%n",
                    throughput);

            System.out.printf(
                    Locale.ROOT,
                    "p50LatencyMs=%.3f%n",
                    percentileNs(latencyNs, 50) / 1_000_000.0);

            System.out.printf(
                    Locale.ROOT,
                    "p95LatencyMs=%.3f%n",
                    percentileNs(latencyNs, 95) / 1_000_000.0);

            System.out.printf(
                    Locale.ROOT,
                    "p99LatencyMs=%.3f%n",
                    percentileNs(latencyNs, 99) / 1_000_000.0);

            System.out.println(
                    "gcCollectionsDuringBench="
                    + Math.max(0, gcAfter - gcBefore));

            System.out.println("checksum=" + checksum);
        } finally {
            pool.shutdownNow();
        }
    }

    public static void main(String[] args)
            throws Exception {

        if (args.length == 1
                && "selftest".equals(args[0])) {
            selftest();
            return;
        }

        if (args.length != 6
                || !"bench".equals(args[0])) {
            throw new IllegalArgumentException(
                    "usage: selftest OR "
                    + "bench workers tasks rounds "
                    + "retainedMiB churnKiB");
        }

        int workers = positiveInt(
                args[1], "workers", 1, 32);
        int tasks = positiveInt(
                args[2], "tasks", 1, 10_000);
        int rounds = positiveInt(
                args[3], "rounds", 1, 2_000_000);
        int retainedMiB = positiveInt(
                args[4], "retainedMiB", 1, 128);
        int churnKiB = positiveInt(
                args[5], "churnKiB", 0, 1024);

        bench(workers, tasks, rounds,
                retainedMiB, churnKiB);
    }
}
~~~

### 5.2. Biên dịch và chạy selftest

Yêu cầu: JDK 17 hoặc mới hơn, với `javac`, `java` sẵn có trên `PATH`.

~~~bash
javac --release 17 -encoding UTF-8 ContainerResourceLab.java
java ContainerResourceLab selftest
~~~

**Stdout chính xác, không phụ thuộc host:**

~~~text
quotaEquivalent=1.50
sumSquares10=385
oneMiBBytes=1048576
sampleP95Ms=30
~~~

Giải thích:

- `quotaEquivalent=1.50` đến từ `150000 / 100000`, không phải phép đọc quota host thật.
- `sumSquares10=385` là tổng bình phương các số 1 tới 10.
- `oneMiBBytes=1048576` sử dụng 1 MiB = 1.048.576 bytes.
- `sampleP95Ms=30` dùng nearest-rank: trong ba mẫu 10, 20 và 30 ms, rank p95 = ceil(0,95 × 3) = 3.

Lệnh `selftest` kiểm **tính toán minh họa**, không phải kiểm máy đang có 1,5 CPU, 1 MiB RAM hay p95 thật là 30 ms.

### 5.3. Chạy benchmark không có container

~~~bash
java -Xms64m -Xmx256m \
  ContainerResourceLab bench 4 400 250000 32 128
~~~

Năm tham số sau `bench`:

| Tham số | Trong ví dụ | Vai trò |
| --- | ---: | --- |
| `workers` | 4 | Số platform threads trong pool |
| `tasks` | 400 | Số task được submit trong một đợt |
| `rounds` | 250000 | Lượng CPU computation mỗi task |
| `retainedMiB` | 32 | Số MiB byte arrays được giữ sống |
| `churnKiB` | 128 | Số KiB cấp phát tạm mỗi task |

Một output có **dạng** sau, các giá trị số đo phải lấy từ lần chạy thật:

~~~text
configuration=workers:4,tasks:400,rounds:250000,retainedMiB:32,churnKiB:128
jvmAvailableProcessors=...
heapMaxMiB=...
heapUsedMiB=...
elapsedSeconds=...
throughputTasksPerSecond=...
p50LatencyMs=...
p95LatencyMs=...
p99LatencyMs=...
gcCollectionsDuringBench=...
checksum=...
~~~

**Đây là sơ đồ định dạng**, không phải stdout cố định. Số CPU JVM nhìn thấy, memory usage, elapsed time, throughput và latency thay đổi theo runtime, host, quota và môi trường. `checksum` là kết quả tích lũy `long` theo quy tắc overflow Java và có thể dùng để quan sát workload có thực sự thực thi, nhưng không phải kết quả năng lực phần cứng.

### 5.4. Điều gì được đo và chưa được đo?

**Được đo:**

- Thời gian wall-clock từ trước khi submit tới sau khi đọc toàn bộ results.
- Throughput `tasks / elapsed seconds` của **batch**.
- Độ trễ từ **submit → hoàn tất** từng task, bao gồm cả queue waiting.
- Heap used/max do `MemoryMXBean` báo ở cuối batch.
- Delta số collections theo `GarbageCollectorMXBean` nếu collector cung cấp số liệu.
- JVM active processor count theo `Runtime.availableProcessors()`.

**Chưa được đo trong code:**

- CPU usage thật của container và CPU throttling.
- Container memory.current/peak, OOM events, swap.
- RSS/PSS, native allocations của thư viện bên ngoài HotSpot.
- Thời lượng GC pauses chi tiết.
- CPU utilization theo từng thread.
- Latency của HTTP/network/database ở traffic thực.

Những số liệu đó phải thu ở **Docker/cgroup/Kubernetes/JFR/metrics platform**, không suy ra từ `MemoryMXBean.getHeapMemoryUsage()`.

### 5.5. Caveat về GC và cấp phát mảng

`retainedMiB` tạo **một mảng 1 MiB cho mỗi MiB** thay vì một mảng khổng lồ. Code chạm mỗi 4 KiB để khiến các pages được dùng. Tuy nhiên bộ nhớ thực của JVM còn có object headers, alignment và GC metadata, nên heap used không nhất thiết **bằng đúng 32 MiB** khi `retainedMiB=32`.

`churnKiB` tạo một mảng tạm cho mỗi task khi lớn hơn 0. Số allocations/GC events phụ thuộc collector, JIT, heap state và các tối ưu hóa runtime; không bảo đảm giá trị `gcCollectionsDuringBench` cố định hoặc số byte trong metric tăng tuyến tính chính xác.

Vì chương trình dùng nhiều workers, kết quả wall-clock khác giữa lần chạy là bình thường. **Đừng lấy output động này làm regression test yêu cầu từng con số bằng nhau**.

## 6. Chuẩn bị container lab và chẩn đoán môi trường

### 6.1. Xác nhận Java version và Docker Engine

~~~bash
java --version
javac -version
docker version
docker info
~~~

`docker info` có thể cảnh báo kernel không hỗ trợ memory/swap limits. Nếu đang dùng Docker Desktop, tài nguyên của **Linux VM** và background load của host cũng ảnh hưởng phép thử. Không khẳng định mọi container có cùng tốc độ chỉ vì `--cpus=1`.

Thực hành dùng một image Java 17 phổ biến:

~~~text
eclipse-temurin:17-jdk
~~~

Để có benchmark tái lập, nên **pin image digest hoặc JDK vendor/build chính xác**, thay vì tin rằng một tag có thể cập nhật sẽ luôn cho cùng HotSpot patch. Nếu `javac` ngoài host mới hơn 17, dùng `--release 17` để class-file chạy được trong Java 17 image.

### 6.2. Tìm Java container awareness thực

Trên Linux HotSpot hiện đại:

~~~bash
java -XshowSettings:system -version
java -XshowSettings:vm -version
~~~

`-XshowSettings:system` có thể hiển thị provider cgroup, effective CPU count, quota, memory limit tùy môi trường/JDK. Đây là một **diagnostic view**, không phải danh sách dòng output cố định.

Nếu muốn xem HotSpot nhận diện cgroup chi tiết hơn:

~~~bash
java -Xlog:os+container=debug -version
~~~

Các dòng log khác giữa patch versions. Java 10 bổ sung nhận diện giới hạn Docker, nhưng trên nền tảng hiện đại cần JDK có hỗ trợ **cgroup v2** và các bản vá tương ứng; một build cũ có thể nhìn tài nguyên host thay vì giới hạn cgroup.

`-XX:+UseContainerSupport` mặc định bật trên HotSpot Linux được hỗ trợ. **Không tắt** bằng `-XX:-UseContainerSupport` như một mẹo tối ưu: kernel vẫn áp hạn mức, còn JVM có thể sizing heap hoặc thread pools sai.

### 6.3. Docker flags sẽ dùng

| Docker flag | Ý nghĩa | Nhầm lẫn cần tránh |
| --- | --- | --- |
| `--cpus=0.5` | CPU bandwidth hard quota tương đương 0,5 CPU | Không phải CPU vật lý độc quyền |
| `--cpuset-cpus=0-1` | Chỉ định logical CPUs được phép chạy | Không tự đặt quota 2 CPUs |
| `--cpu-shares=512` | Trọng số CPU khi cạnh tranh | Không phải hard limit 0,5 CPU |
| `--memory=512m` | Hard memory limit của container | Không bằng Java `-Xmx` |
| `--memory-swap=512m` cùng `--memory=512m` | Tổng memory + swap bằng memory (không cho swap khi được hỗ trợ) | Kernel/daemon có thể không hỗ trợ swap accounting |
| `--memory-reservation` | Soft limit/reservation theo Docker | Không thay hard limit |
| `--name sizing-lab` | Tên dễ dùng khi đo với Docker | Không tự theo dõi metrics |

Trên Docker Engine Linux, nếu `--memory-swap` và `--memory` có cùng giá trị dương, Docker docs mô tả container không được dùng swap. **Xác minh trên host thật**; option có thể không hiệu lực nếu kernel/VM/daemon thiếu hỗ trợ.

### 6.4. Đảm bảo Docker nhìn thấy class đã biên dịch

Trong thư mục chứa:

~~~text
ContainerResourceLab.java
ContainerResourceLab.class
ContainerResourceLab$Sample.class
~~~

Dòng `ContainerResourceLab$Sample.class` là file nội bộ do Java compiler sinh cho `record Sample`; tên có ký tự `$`, thường xuất hiện khi liệt kê file. Không cần nhập tên đó vào lệnh chạy.

Ví dụ bên dưới dành cho **shell POSIX (Linux/macOS)**, mount thư mục hiện tại vào container ở chế độ chỉ đọc:

~~~bash
docker run --rm \
  --mount type=bind,source="$(pwd)",target=/lab,readonly \
  -w /lab \
  eclipse-temurin:17-jdk \
  java -cp /lab ContainerResourceLab selftest
~~~

Nếu dùng Windows/PowerShell, cần điều chỉnh cách truyền host path cho bind mount. **Không** tự đồng nhất cú pháp `$(pwd)` của shell POSIX với Command Prompt. Nếu chạy Docker Desktop, quyền chia sẻ ổ/thư mục host với VM cũng cần được bật phù hợp.

Sau khi mount đúng, kết quả `selftest` trong container phải là bốn dòng cố định ở mục 5.2, không phụ thuộc CPU hoặc memory limit.

## 7. Thực hành vòng A — thay quota CPU

### 7.1. Các lệnh kiểm CPU 0,5 / 1 / 2

Giữ container memory 512m, heap max 256m, retained 32 MiB và workload:

~~~bash
docker run --rm --cpus=0.5 \
  --memory=512m --memory-swap=512m \
  --mount type=bind,source="$(pwd)",target=/lab,readonly \
  -w /lab eclipse-temurin:17-jdk \
  java -Xms64m -Xmx256m \
  -cp /lab ContainerResourceLab bench 4 400 250000 32 128
~~~

~~~bash
docker run --rm --cpus=1 \
  --memory=512m --memory-swap=512m \
  --mount type=bind,source="$(pwd)",target=/lab,readonly \
  -w /lab eclipse-temurin:17-jdk \
  java -Xms64m -Xmx256m \
  -cp /lab ContainerResourceLab bench 4 400 250000 32 128
~~~

~~~bash
docker run --rm --cpus=2 \
  --memory=512m --memory-swap=512m \
  --mount type=bind,source="$(pwd)",target=/lab,readonly \
  -w /lab eclipse-temurin:17-jdk \
  java -Xms64m -Xmx256m \
  -cp /lab ContainerResourceLab bench 4 400 250000 32 128
~~~

Khi có ít hơn 2 logical CPUs khả dụng hoặc host rất bận, A3 có thể không đạt throughput cao hơn tương xứng. **Không hứa số lần tăng tốc cố định**.

### 7.2. Dùng loop để chạy lặp

Ví dụ shell POSIX:

~~~bash
for quota in 0.5 1 2; do
  echo "CPU quota = $quota"
  docker run --rm --cpus="$quota" \
    --memory=512m --memory-swap=512m \
    --mount type=bind,source="$(pwd)",target=/lab,readonly \
    -w /lab eclipse-temurin:17-jdk \
    java -Xms64m -Xmx256m \
    -cp /lab ContainerResourceLab bench 4 400 250000 32 128
done
~~~

Chạy thêm nhiều vòng độc lập; giữ kết quả đầy đủ và xuất bảng từ dữ liệu thực. Nếu cần đo thời gian startup, phải ghi rõ có/không tính startup/JIT warm-up vào elapsed time. Chương trình bench ở mục 5 **không tính thời gian JVM startup** vào `elapsedSeconds`, vì timestamp bắt đầu sau khi class loading và cấp phát retained working set đã diễn ra.

### 7.3. Cách giải thích kết quả

Kỳ vọng **định tính**, không phải số đo được bịa:

- Ở **0,5 CPU**, bốn workers tranh cùng quota. Nếu workload CPU-bound và luôn runnable, khả năng bị throttling cao hơn, elapsed time có thể dài.
- Ở **1 CPU**, CPU capacity cao hơn; throughput có thể cải thiện khi workload thực sự bị giới hạn CPU.
- Ở **2 CPU**, các workers có thể chạy song song nhiều hơn khi host đủ CPU, nhưng không bảo đảm throughput gấp đôi do scheduler, heap/GC, memory access và overhead.
- Khi CPU quota tăng mà throughput **không** tăng, cần kiểm workload có CPU-bound không, số workers có đủ không, memory bandwidth/locks/I/O/GC có phải bottleneck không.

**Không giải thích** Java báo `availableProcessors=1` trong quota 0,5 là container đã có một CPU đầy đủ. API là **integer hint**, còn quota là **CPU time fraction**.

## 8. Thực hành vòng B — thay memory limit, không đổi heap

### 8.1. Các lệnh memory 256m / 512m / 1g

Ở vòng này, giữ CPU = 1, `-Xms64m`, `-Xmx128m`, cùng workers=4, tasks=400, rounds=250000, retainedMiB=32, churnKiB=128.

~~~bash
docker run --rm --cpus=1 \
  --memory=256m --memory-swap=256m \
  --mount type=bind,source="$(pwd)",target=/lab,readonly \
  -w /lab eclipse-temurin:17-jdk \
  java -Xms64m -Xmx128m \
  -cp /lab ContainerResourceLab bench 4 400 250000 32 128
~~~

~~~bash
docker run --rm --cpus=1 \
  --memory=512m --memory-swap=512m \
  --mount type=bind,source="$(pwd)",target=/lab,readonly \
  -w /lab eclipse-temurin:17-jdk \
  java -Xms64m -Xmx128m \
  -cp /lab ContainerResourceLab bench 4 400 250000 32 128
~~~

~~~bash
docker run --rm --cpus=1 \
  --memory=1g --memory-swap=1g \
  --mount type=bind,source="$(pwd)",target=/lab,readonly \
  -w /lab eclipse-temurin:17-jdk \
  java -Xms64m -Xmx128m \
  -cp /lab ContainerResourceLab bench 4 400 250000 32 128
~~~

Các giá trị đây là **thiết kế thí nghiệm**, không phải guarantee container 256m sẽ luôn chạy ổn trên mọi JDK/build. Native memory, thread stacks và overhead có thể khác nhau. Hãy thực hiện trên máy thử, không chạy workload thiếu memory trên production.

### 8.2. Kết quả đáng chú ý nhất có thể là “không khác”

Nếu tất cả ba kịch bản đều không bị memory pressure, giữ cùng heap và CPU có thể cho **throughput và latency tương tự nhau** trong sai số thử nghiệm.

Từ đó kết luận hợp lệ là: với workload này và heap cố định, **container memory limit chưa phải bottleneck đã quan sát được**. Không được kết luận mọi ứng dụng đều không cần thêm memory.

Nếu memory.current gần limit và `memory.events` phát hiện OOM, đó là bằng chứng riêng về headroom. Nếu container bị OOMKilled, thử nghiệm kịch bản đó là **không đạt về tính ổn định**, không nên ghi throughput bằng 0 rồi so như một phép benchmark hoàn thành bình thường.

### 8.3. Memory thấp hơn heap max cũng chưa chắc chết ngay

`-Xmx128m` là giới hạn heap tối đa chứ không nhất thiết toàn bộ 128 MiB được committed/resident mọi lúc. Ngược lại, một `-Xmx128m` nhỏ vẫn có thể hết heap trước khi memory cgroup chạm 256 MiB nếu workload cần giữ object vượt sức chứa heap.

Cần tách:

~~~text
Java heap used
Java heap committed
Java heap max
Process RSS/PSS
Cgroup memory.current
Cgroup memory.max
OOM events
~~~

Không cộng `RSS + heap used` để suy total memory; heap pages đã nằm trong RSS, việc cộng như vậy dễ **đếm trùng**.

## 9. Thực hành vòng C — so kích thước heap và áp lực GC

### 9.1. Giữ memory container 512m

Chọn CPU 1, memory 512m và workload cố định, thay riêng:

~~~text
C1: -Xms64m -Xmx128m
C2: -Xms64m -Xmx256m
~~~

Ví dụ:

~~~bash
docker run --rm --cpus=1 \
  --memory=512m --memory-swap=512m \
  --mount type=bind,source="$(pwd)",target=/lab,readonly \
  -w /lab eclipse-temurin:17-jdk \
  java -Xms64m -Xmx128m \
  -cp /lab ContainerResourceLab bench 4 400 250000 64 512
~~~

~~~bash
docker run --rm --cpus=1 \
  --memory=512m --memory-swap=512m \
  --mount type=bind,source="$(pwd)",target=/lab,readonly \
  -w /lab eclipse-temurin:17-jdk \
  java -Xms64m -Xmx256m \
  -cp /lab ContainerResourceLab bench 4 400 250000 64 512
~~~

Đây là thí nghiệm **tạo thêm allocation pressure** với retained 64 MiB và churn 512 KiB mỗi task. Nếu heap nhỏ, GC có thể phải thu gom thường xuyên hơn; nhưng không có bảo đảm delta `gcCollectionsDuringBench` sẽ luôn lớn hơn ở C1 trên mọi collector và JDK.

Nếu C1 không hoàn thành do Java heap OOME, ghi nhận đó là **failure** của cấu hình. Không tiếp tục tăng retained/churn tới khi kernel giết cả môi trường dùng chung.

### 9.2. MaxRAMPercentage và -Xmx

Khi không đặt `-Xmx`, HotSpot có thể dùng container-aware available memory để chọn max heap theo `-XX:MaxRAMPercentage` và các heuristics của bản JDK.

~~~bash
java -XX:MaxRAMPercentage=50 \
  -XshowSettings:vm -version
~~~

Điều này **không đặt toàn bộ process memory bằng 50%**. Nó liên quan **Java heap sizing**, còn metaspace, JIT code cache, thread stacks, direct NIO, JNI/native allocations và memory cgroup accounting cần ngân sách riêng.

Trong thử nghiệm C3, **không đặt `-Xmx`** nếu mục tiêu là quan sát tác động của `MaxRAMPercentage`; nếu đặt cả hai, cần hiểu thứ tự/độ ưu tiên flags của HotSpot và kiểm heap max thực.

### 9.3. Giới hạn direct memory và native headroom

`-XX:MaxDirectMemorySize` được dùng để kiểm soát các cấp phát **direct NIO buffers thuộc phạm vi HotSpot**, **không** giới hạn mọi native allocation bên thứ ba. `-Xmx` chỉ áp cho Java heap.

Một budgeting table **giả định** khi container limit là 512 MiB:

| Thành phần | MiB ước lượng |
| --- | ---: |
| Java heap peak | 256 |
| Direct buffers | 48 |
| Metaspace/class | 48 |
| Thread stacks và runtime threads | 40 |
| Code cache/JIT/GC/native | 48 |
| File/shared/cache/other charges | 24 |
| **Tổng** | **464** |
| **Headroom** | **48** |

Đây **không phải số đo thực** của ví dụ. Dùng để minh họa vì sao **512 - 256** không tự đồng nghĩa mọi off-heap/native memory có đủ 256 MiB. Trong production, phải đo peak qua OS/cgroup, JVM metrics và tải thật, không áp con số giả định này.

## 10. Thu thập CPU throttling và memory events từ Linux cgroup

### 10.1. Cgroup v2: files cần biết

Trên Linux cgroup v2, các file thường gặp:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.stat
~~~

**Không giả định** mọi container có đúng đường dẫn đó. Một số hệ dùng cgroup v1, nested hierarchies, namespace hoặc mount layout khác. Nếu file không tồn tại, xác định loại cgroup và mount từ `/proc/self/cgroup`, `/proc/self/mountinfo` hoặc công cụ vận hành, thay vì kết luận không có quota.

### 10.2. Hiểu cpu.stat theo chênh lệch thời gian

Ví dụ **dữ liệu minh họa**:

~~~text
t1:
  nr_periods   1000
  nr_throttled 200

t2:
  nr_periods   1100
  nr_throttled 260
~~~

Phép tính:

~~~text
delta periods   = 100
delta throttled = 60
60/100 = 60% chu kỳ có xảy ra throttling
~~~

**Không diễn giải** là “60% latency bị mất” hoặc “throughput giảm chính xác 60%”. Các counters cần được phân tích cùng `throttled_usec`, CPU usage, traffic, GC và request latency.

Đối với các kịch bản CPU .5, 1, 2, tỷ lệ chu kỳ bị throttled và delta throttled duration giúp trả lời: **CPU quota có thực sự đang ngăn workload chạy không?**

### 10.3. Cgroup v2 memory events

Ví dụ:

~~~text
memory.max = 536870912
memory.events:
  low 0
  high 0
  max 12
  oom 2
  oom_kill 1
~~~

Các số này là **minh họa**, không phải kết quả chạy từ máy của người đọc. `oom_kill=1` có thể liên quan một lần kernel kết thúc tiến trình trong cgroup, trong phạm vi thống kê kernel.

Không nên diễn giải sự kiện độc lập: xem **delta cùng khoảng đo**, Pod/container restart status và kernel logs. Một bộ đếm tích lũy cao từ lịch sử cũ không tự chứng minh lần benchmark đang chạy vừa bị OOM.

### 10.4. Cgroup v1 tương đương

Trên hệ còn dùng cgroup v1, các tên file có thể là:

~~~text
cpu.cfs_quota_us
cpu.cfs_period_us
cpu.stat
memory.limit_in_bytes
memory.usage_in_bytes
memory.failcnt
memory.oom_control
~~~

Không cố lấy một script hard-code v2 rồi chạy trên v1. Những bản JDK/OS có hỗ trợ container awareness khác nhau; cần kiểm **provider được JVM phát hiện**.

## 11. Thu thập số liệu bằng Docker và JVM

### 11.1. Docker stats

Khi benchmark đang chạy trong một container có tên `sizing-lab` (không phải sau khi nó kết thúc), ở một terminal khác:

~~~bash
docker stats --no-stream sizing-lab
~~~

`docker stats` hiển thị CPU %, memory usage/limit, network và I/O metrics với định nghĩa theo Docker/platform. CPU % có thể **vượt 100% khi sử dụng hơn một CPU-equivalent**, tùy phương pháp trình bày.

Không lấy CPU % 100 làm bằng chứng “đúng một core vật lý”. Không cộng CPU % với p95 hoặc đổi trực tiếp sang số active processors của JVM.

Docker có thể điều chỉnh cách tính memory usage hiển thị (ví dụ trừ một phần cache trên Linux), vì vậy số liệu Docker stats **có thể không bằng** `memory.current` hoặc RSS của process. Ghi rõ nguồn metric.

### 11.2. Xem thông tin cgroup ngay trong container

Nếu container còn chạy:

~~~bash
docker exec sizing-lab sh -c 'cat /proc/self/cgroup'
~~~

Với cgroup v2 và path hợp lệ:

~~~bash
docker exec sizing-lab sh -c \
  'cat /sys/fs/cgroup/cpu.max; cat /sys/fs/cgroup/cpu.stat'
~~~

~~~bash
docker exec sizing-lab sh -c \
  'cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/memory.events'
~~~

Nếu container kết thúc quá nhanh, lệnh `docker exec` sẽ thất bại; có thể tăng số tasks cho phép đo kéo dài, dùng hệ thu thập metrics, hoặc chạy container/service có thời gian sống đủ dài. Đừng tự giải thích lỗi “No such container” thành vấn đề Java.

### 11.3. GC logs và Java Flight Recorder

Trên HotSpot Java 17+:

~~~bash
java -Xlog:gc* \
  -Xms64m -Xmx256m \
  ContainerResourceLab bench 4 400 250000 32 128
~~~

GC logging bổ sung thông tin collection, pause và heap state. Output phụ thuộc collector và JDK, nên không có stdout/stderr cố định để so nguyên văn.

**Java Flight Recorder (JFR)** được hỗ trợ trên các JDK hiện đại và có thể cung cấp dữ liệu GC, CPU sampling, allocation và thread activities. Nhưng recording có overhead, file phải được thu lại trước khi container bị xóa; đừng bật quá nhiều sự kiện rồi so trực tiếp với một lượt không có instrumentation.

### 11.4. jcmd và Native Memory Tracking

Nếu nghi native memory tăng, có thể khởi động HotSpot với:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Khi JVM đang chạy, dùng `jcmd` với PID thực:

~~~bash
jcmd 12345 VM.native_memory summary scale=MB
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff scale=MB
~~~

`12345` chỉ là PID minh họa. **NMT phải được bật từ startup**, có overhead và **không bao phủ toàn bộ allocations của native libraries/JNI bên thứ ba**. NMT `reserved` khác RSS/resident memory; không cộng NMT committed vào RSS như hai tổng độc lập.

### 11.5. Quan sát thông qua JMX/MXBeans

Java 17+ có APIs được hỗ trợ:

~~~java
Runtime.getRuntime().availableProcessors();
ManagementFactory.getMemoryMXBean()
        .getHeapMemoryUsage();
ManagementFactory.getMemoryMXBean()
        .getNonHeapMemoryUsage();
ManagementFactory.getGarbageCollectorMXBeans();
~~~

Đây là những dữ liệu JVM hữu ích, nhưng `getHeapMemoryUsage` không nói tổng memory cgroup; `getNonHeapMemoryUsage` cũng không bao phủ mọi native library allocation.

Trong môi trường production, có thể xuất các metrics qua Micrometer/Prometheus hoặc observability stack sẵn có, với thỏa thuận rõ labels, units và polling interval. Chưa cần thư viện ngoài để chạy demo của bài.

## 12. Kubernetes: requests, limits và policy tạo khác biệt

### 12.1. CPU request không phải CPU hard limit

Một đoạn `resources` bên trong **container specification**:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "1500m"
    memory: "512Mi"
~~~

Ý nghĩa:

- `requests.cpu=500m`: yêu cầu tài nguyên dùng khi scheduler đặt Pod và hỗ trợ phân bổ tương đối.
- `limits.cpu=1500m`: hard CPU bandwidth limit tương đương **1,5 CPU** theo cơ chế quota trên Linux khi được áp dụng.
- `requests.memory=256Mi`: memory request khi scheduling; không phải Java heap max.
- `limits.memory=512Mi`: memory hard limit của container; kernel enforcement có thể dẫn tới OOM kill khi vượt hạn mức.

Đoạn YAML này là **một fragment** phải đặt đúng vào manifest có `containers[].resources`; không phải Deployment hoàn chỉnh có thể triển khai độc lập.

Một container **chỉ có CPU request** không mặc nhiên bị giới hạn hard CPU quota bằng request. Trong một số cấu hình Kubernetes, nếu chỉ đặt limit mà không đặt request, admission/kubelet có thể dùng limit làm request theo quy tắc mặc định; phải đọc manifest **sau khi được admission** để biết cấu hình thực.

### 12.2. CPU limit và memory limit có cơ chế enforcement khác nhau

Theo Kubernetes docs:

- CPU hard limit dùng CPU throttling; khi cgroup tiêu hết quota trong chu kỳ, scheduler hạn chế chạy tiếp.
- Memory hard limit thường được enforcement **reactively** bằng OOM kills; container có thể tiến sát/vượt giới hạn trong một khoảng thời gian trước khi kernel chọn kill.

Do đó, khi đo:

~~~text
CPU pressure:
  throughput giảm, request latency tăng,
  cpu.stat throttling tăng.

Memory pressure:
  reclaim/GC/swap tăng,
  memory.current sát memory.max,
  OOM events hoặc OOMKilled có thể xuất hiện.
~~~

Đây là **dấu hiệu định hướng**, không phải chẩn đoán độc quyền. Một request chậm cũng có thể do database, network, lock contention hoặc GC mà không hề chạm CPU quota.

### 12.3. Theo dõi Pod và container

~~~bash
kubectl top pod
kubectl describe pod sizing-lab
~~~

`sizing-lab` là **tên giả định của một Pod cần tồn tại trong cluster đang kiểm**. Thay bằng tên thực của deployment test; không có manifest nào ở trên tự tạo một Pod tên đó.

`kubectl top` phụ thuộc Metrics Server/metrics APIs trong cluster. Không thấy dữ liệu có thể do hệ giám sát chưa được cấu hình, không chứng minh Pod không dùng CPU/memory.

Kubernetes `status.containerStatuses[].lastState.terminated.reason` có thể hiển thị `OOMKilled`. Exit code **137** thường liên quan SIGKILL nhưng **không đủ một mình** để khẳng định kernel OOM: cần status/events và metrics cgroup.

### 12.4. Kubernetes CPU Manager và cpuset

Một số clusters có CPU Manager policies cho phép pin CPUs cho các workloads đủ điều kiện; điều này phụ thuộc QoS, request/limit CPU nguyên, node policy và cấu hình kubelet. Không giả định mọi Pod có CPU limit 2 sẽ sở hữu độc quyền hai physical cores.

Nếu workload có affinity/cpuset, hãy kiểm `cpuset.cpus.effective` và quota. Vị trí CPU được schedule và tổng CPU time quota là **hai trục khác nhau**.

## 13. Phân tích kết quả qua nhiều chỉ số

### 13.1. Throughput và p95/p99 phải đọc cùng nhau

Giả sử một thay đổi làm throughput tăng nhưng p99 latency tệ hơn. Có thể ứng dụng đang nhận nhiều request concurrent hơn, tăng queue length hoặc chịu GC/throttling spikes.

**Không chọn cấu hình chỉ có throughput cao nhất** nếu SLO p95/p99 và error rate không đạt. Một phương án có throughput thấp hơn một chút nhưng tail latency, memory headroom và stability tốt hơn có thể phù hợp hơn.

### 13.2. Bảng ghi kết quả thực nghiệm

Hãy lập bảng sau **sau khi chạy thật**, không chép các con số minh họa làm dữ liệu đo:

| Trường cần ghi | Ý nghĩa |
| --- | --- |
| Run ID, UTC timestamp | Ghép metrics của cùng lượt |
| Image digest, JDK build, OS/cgroup version | Tái lập môi trường |
| CPU quota/period, cpuset | Khả năng CPU được cấp |
| Memory limit, swap policy | Khả năng memory được cấp |
| `-Xms`, `-Xmx`, GC flags | Heap/collector policy |
| Workers, tasks, rounds, retainedMiB, churnKiB | Workload không bị thay lẫn |
| elapsed seconds, tasks/s | Throughput |
| p50, p95, p99 ms | Phân bố tail latency |
| CPU usage, delta throttling | CPU saturation/quota pressure |
| Heap used/committed/max, GC count/pause | GC/memory pressure |
| Cgroup memory usage/peak/events | Container memory/oom |
| Exit status, exceptions, checksum | Tính đúng và ổn định |
| Host load / noisy-neighbor notes | Yếu tố ngoại cảnh |
| Tổng số lần lặp và độ biến thiên | Mức tin cậy của kết luận |

Các dòng benchmark in từ `ContainerResourceLab` chỉ bao phủ **một phần bảng**. Các trường Docker/cgroup cần được thu riêng.

### 13.3. Phân biệt throughput scaling với speedup lý tưởng

Khi quota tăng 1 lên 2 CPU:

~~~text
Speedup quan sát = throughput(2 CPU) / throughput(1 CPU)
~~~

Nếu throughput tăng từ 100 lên 160 tasks/s trong một **ví dụ toán học**, speedup = 1,6 lần, không phải 2 lần. Đây là **số minh họa**, không phải benchmark đã chạy.

Hiệu năng thường bị giới hạn bởi phần không song song, contention, queue scheduling, cache, memory bandwidth, GC và overhead. Vì vậy scaling không tuyến tính mãi.

### 13.4. Khi CPU tăng mà latency không cải thiện

Kiểm theo thứ tự:

1. CPU quota có được áp dụng đúng và đã thực sự bão hòa chưa?
2. `cpu.stat` có throttling đáng kể trong lượt thử thấp CPU không?
3. Số runnable worker threads đủ khai thác quota mới không?
4. Workload CPU-bound hay phần lớn thời gian chờ I/O/lock?
5. Java heap/GC có tạo stop-the-world pauses không?
6. Host có đủ CPUs và không bị noisy neighbor không?
7. Các input và traffic profiles giữa hai lượt có tương đương không?

Nếu bottleneck là database hoặc disk I/O, tăng CPU limit có thể gần như không có tác dụng.

### 13.5. Khi memory tăng mà throughput không cải thiện

Đây có thể là kết quả đúng. Nếu heap và workload giữ nguyên, CPU vẫn là bottleneck, memory usage không gần limit, tăng memory cgroup không thay đổi lượng CPU được cấp.

Memory limit quan trọng khi **thiếu headroom**, có kernel reclaim/swap, OOM hoặc khi JVM heap sizing tự điều chỉnh theo container limit. Nếu muốn đo tác dụng của memory limit **riêng nó**, giữ `-Xmx` cố định như vòng B. Nếu muốn đo tác dụng heap sizing tự động, tách sang vòng C.

## 14. Các lỗi benchmark gây kết luận sai

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| So hai phiên bản image/JDK khác nhau | JIT/GC/default flags thay đổi | Pin image digest/JDK build |
| Đổi cả CPU và memory cùng lúc | Không biết biến nào tạo tác dụng | Thay một biến mỗi vòng |
| Đổi cả `-Xmx` khi chỉ muốn đo memory limit | Heap/GC trở thành biến nhiễu | Giữ Xmx cố định ở vòng B |
| Dùng workers tự tăng theo CPU quota | Đã đổi concurrency cùng resource | Giữ workers cố định ở vòng A |
| Một lượt chạy là đủ | JIT, host contention, GC biến động | Warm-up và chạy nhiều lần |
| Đo sai thời điểm | Startup/JIT/GC khác nhau | Ghi rõ measurement window |
| Chỉ in Set/GC/CPU metric cuối | Mất time-series và tail spikes | Thu metrics theo thời gian |
| Coi availableProcessors là quota thật | Số nguyên heuristic | Đọc cgroup quota/period |
| Coi CPU shares là hard cap | Chỉ trọng số tương đối | Dùng `--cpus` |
| Coi heap used là container memory | Native/thread/cache cũng dùng memory | Đọc memory.current/OS |
| Coi `Xmx=512m` an toàn trong container 512m | Không có headroom | Budget non-heap/native |
| Coi exit code 137 luôn là Java OOME | SIGKILL có nhiều nguyên nhân | Xem `OOMKilled`/events |
| Coi OOM kill là “throughput bằng 0” của run hợp lệ | Run đã thất bại | Ghi status FAILED |
| Coi 100% CPU luôn là 1 physical core | Metrics có mẫu số khác nhau | Đọc Docker CPU % semantics |
| So `docker stats` memory bằng RSS trực tiếp | Cache/accounting khác nhau | Ghi nguồn/định nghĩa |
| Chỉ xét average latency | Bỏ tail p95/p99 | Báo cả percentiles/errors |
| Chỉ xét p95 mà bỏ throughput | Có thể chịu load ít hơn | Đọc đầy đủ throughput/SLO |
| Dùng batch benchmark thay HTTP load test | Không mô phỏng request arrival | Thử traffic thực |
| Tăng threads coi như thêm CPU | CPU quota không đổi | Tách concurrency experiment |
| Cố tình ép OOM trên production | Rủi ro dịch vụ/host | Chạy isolated test |
| Bật NMT/JFR ở một lượt và tắt lượt khác | Instrumentation overhead khác | Cùng policy đo |
| Dùng NMT như tổng native RSS | NMT không bao phủ mọi JNI | Kết hợp OS/native tools |
| Coi `-XX:-UseContainerSupport` là tối ưu | JVM có thể sizing theo host sai | Giữ detection mặc định |
| Gán trước con số speedup kỳ vọng | Scaling không tuyến tính | Đo thực, báo variance |

## 15. Phân tích GC, JIT và warm-up một cách công bằng

### 15.1. Startup versus steady state

Ứng dụng Java thường có giai đoạn **class loading, interpreter và JIT compilation**. Lượt chạy ngắn có thể dành phần lớn thời gian trong warm-up thay vì steady state.

Chương trình demo có `selftest` và `bench`, nhưng `bench` **không tự chạy warm-up phase riêng**. Để đánh giá sản phẩm, có thể:

- Khởi động ứng dụng và warm up bằng một khối lượng request trước phép đo.
- Giữ cùng giai đoạn warm-up ở mọi kịch bản.
- Đo startup latency riêng nếu đó là SLO.
- Dùng workload real traffic distribution thay vì chỉ một đoạn tính CPU tổng hợp.
- Với microbenchmark thuần CPU, cân nhắc **JMH** để tránh những lỗi đo JIT, dead-code elimination hoặc constant folding.

### 15.2. JIT/GC dùng cùng CPU budget

Cgroup CPU quota không chỉ dành cho application threads. JIT compiler threads, garbage collector workers và Java runtime cũng tiêu thụ CPU time. Ở quota thấp, chúng có thể bị throttled cùng application threads.

Một GC pause đo theo wall-clock có thể tăng khi CPU budget thấp, nhưng không được suy tất cả GC pause dài đều do throttling. Cần đối chiếu GC logs, CPU utilization, heap pressure và cgroup stats.

### 15.3. Không so GC count như một chỉ số chất lượng duy nhất

Một cấu hình có GC count thấp nhưng pause dài có thể không tốt hơn cấu hình có nhiều collections ngắn. Các collectors khác nhau còn có các loại concurrent/safepoint phases khác nhau.

Khi đánh giá ứng dụng thật, xem:

- Tổng GC time trong window và tỷ lệ so với wall time.
- Pause time distribution và p95/p99 liên quan requests.
- Heap after-GC/live set và allocation rate.
- Throughput thay đổi thế nào theo Xmx.
- Cgroup memory headroom còn bao nhiêu.
- Native/mapped/direct memory có tăng không.

Không dùng `System.gc()` trong benchmark để “chuẩn hóa” trạng thái rồi kết luận điều đó phản ánh production.

## 16. Phương pháp chọn cấu hình cuối cùng

### 16.1. Chọn theo SLO, không theo quota lớn nhất

Một quy trình thực tế:

1. Đặt SLO rõ, ví dụ throughput tối thiểu, p95 latency, error rate, không OOM.
2. Xác định workload peak và workload trung bình.
3. Đo ứng dụng ở vài cấu hình CPU và memory có kiểm soát.
4. Loại kịch bản không hoàn thành hoặc OOM.
5. Loại kịch bản có p95/p99 vượt SLO.
6. Kiểm headroom memory, CPU throttling và GC biến động qua nhiều lượt.
7. Trong những cấu hình đạt yêu cầu, chọn phương án có chi phí hợp lý và mức an toàn đủ.
8. Kiểm lại bằng integration/load test trên môi trường gần production.
9. Lưu cấu hình JVM/container cùng số đo và ngày kiểm thử.
10. Khi thay JDK/GC/heap/traffic, chạy lại benchmark thay vì dùng kết luận cũ.

### 16.2. Kịch bản lựa chọn theo nguyên nhân

**Ứng dụng CPU-bound:**
- CPU throttling tăng cùng lúc throughput giảm.
- Có thể tăng CPU quota, tối ưu CPU work hoặc giảm contention.
- Tăng memory limit riêng thường không giải quyết nếu bộ nhớ đã đủ.

**Ứng dụng memory/GC-bound:**
- Heap sát max, allocation rate cao, GC time/pause tăng.
- Cân nhắc giảm allocations, điều chỉnh heap và headroom; kiểm cgroup OOM.
- Tăng Xmx mà không tăng container memory có thể làm OOM kill dễ hơn.

**Ứng dụng I/O-bound:**
- CPU không cao, threads thường chờ network/database.
- Tăng CPU có thể ít tác dụng; cần tối ưu I/O, connection pooling, downstream latency và concurrency limits.

**Ứng dụng có memory leak:**
- Heap after-GC hoặc RSS/cgroup memory tăng liên tục theo thời gian.
- Chỉ tăng memory limit thường trì hoãn sự cố; phải tìm retention/native leak và sửa nguyên nhân.

### 16.3. Cost-efficiency và safety margin

Thử nghiệm trên một máy nhẹ tải có thể không phản ánh workload co-located trên Kubernetes. Nếu chọn cấu hình chỉ vừa chạm SLO trong lab, một đợt noisy-neighbor load hoặc traffic spike có thể khiến production vi phạm SLO.

Đặt safety headroom dựa trên biến động đo được, không dùng một tỉ lệ tuyệt đối cho mọi ứng dụng. Capacity planning phải cân nhắc vertical scaling, horizontal scaling, load shedding và autoscaling policy theo yêu cầu dịch vụ.

## 17. Checklist thực hiện và câu hỏi tự kiểm tra

### Checklist về công cụ và tính hợp lệ

- [ ] Đã biết đúng JDK build, Docker/OS/cgroup version?
- [ ] `javac --release 17` và chương trình selftest đã chạy thành công?
- [ ] Image runtime là JDK 17+ và class-file target phù hợp?
- [ ] Đã xác minh Docker CPU/memory limits thật, không chỉ đọc flag?
- [ ] Có nhớ CPU quota khác cpuset và CPU shares?
- [ ] Có nhớ Java heap max khác container memory limit?
- [ ] Không dựa vào một số `availableProcessors` để suy CPU-equivalent quota?
- [ ] Đã kiểm swap policy và host đủ tài nguyên?
- [ ] Ghi rõ benchmark batch latency bao gồm queue waiting?
- [ ] Không đánh tráo batch benchmark thành HTTP/service SLO thực?

### Checklist về thiết kế phép thử

- [ ] Có mục tiêu throughput, latency, error rate, memory headroom?
- [ ] Đổi riêng CPU hoặc memory ở từng vòng đầu?
- [ ] Giữ workload, workers, JDK, heap flags ổn định khi so CPU?
- [ ] Giữ CPU, workload và Xmx ổn định khi so memory limit?
- [ ] Có vòng riêng khi thử heap policy/GC?
- [ ] Có warm-up và nhiều lượt đo?
- [ ] Có ghi image digest, timestamps và host conditions?
- [ ] Có phân biệt run thành công với OOM/failure?
- [ ] Có throughput, p50/p95/p99 và variance?
- [ ] Có time-series CPU throttling và memory events trong đúng window?

### Checklist về kết luận

- [ ] Không coi throughput tăng là đủ khi p99/error rate tệ hơn?
- [ ] Không bảo đảm scaling tuyến tính theo số CPU?
- [ ] Không kết luận memory limit thấp là bottleneck nếu chưa chạm memory pressure?
- [ ] Đã phân biệt Java OOME và kernel OOM kill?
- [ ] Có xét GC/JIT/native memory/swap và downstream dependencies?
- [ ] Có chọn cấu hình đáp ứng SLO với headroom hợp lý?
- [ ] Có kế hoạch benchmark lại khi đổi JDK, dependencies hoặc traffic?

### Câu hỏi tự kiểm tra

**1.** Docker `--cpus=1.5` có nghĩa container sở hữu 1,5 core vật lý không?

**Đáp án:** Không. Nó cấu hình CPU bandwidth quota tương đương 1,5 CPU time.

**2.** Vì sao `availableProcessors()` có thể là 2 khi quota 1,5?

**Đáp án:** API trả số nguyên mà JVM dùng cho ergonomics; nó không phải giá trị quota dạng phân số và còn phụ thuộc phiên bản JVM/config.

**3.** CPU shares có phải CPU hard cap không?

**Đáp án:** Không. Đây là trọng số tương đối khi có contention.

**4.** Container memory 512m, `-Xmx256m` có bảo đảm không OOM không?

**Đáp án:** Không. Native/GC/metaspace/stacks/direct/file cache và memory cgroup charges khác vẫn tiêu thụ tài nguyên.

**5.** Khi chỉ muốn đo tác dụng memory limit, có nên đổi `-Xmx` cùng lúc không?

**Đáp án:** Không. Hãy giữ Xmx cố định trong vòng thử đó để tách biến.

**6.** Khi chỉ muốn đo tác dụng CPU quota, có nên đổi workers từ 1 lên 8 theo từng quota không?

**Đáp án:** Không trong vòng thử CPU riêng. Có thể làm vòng khác để đánh giá interaction với concurrency.

**7.** Tăng container memory limit từ 256 lên 1 GiB có chắc tăng throughput không?

**Đáp án:** Không nếu ứng dụng không chạm memory pressure và CPU/heap/workload không đổi.

**8.** Throttling ratio 60% theo `nr_throttled/nr_periods` có nghĩa mất 60% request time không?

**Đáp án:** Không. Nó là tỷ lệ chu kỳ có throttling; cần đối chiếu throttled duration, CPU usage và latency.

**9.** `MemoryMXBean.getHeapMemoryUsage()` có cho total container memory không?

**Đáp án:** Không. Nó nói về heap JVM, không bao phủ toàn bộ cgroup charges.

**10.** `OOMKilled` khác `OutOfMemoryError: Java heap space` ra sao?

**Đáp án:** Một bên là kernel/container termination, bên kia là lỗi cấp phát heap do JVM phát hiện; có thể xảy ra độc lập.

**11.** Vì sao cần pin image digest/JDK build?

**Đáp án:** JDK updates có thể thay GC/JIT/ergonomics và image tags có thể trỏ build khác qua thời gian.

**12.** Vì sao chương trình bench không cho stdout số liệu cố định?

**Đáp án:** Elapsed time, latency, GC và CPU available tùy host, kernel, JDK và scheduler; chỉ `selftest` có stdout xác định.

**13.** Nếu p95 cải thiện nhưng p99 xấu đi, có thể tuyên bố cấu hình mới tốt hơn không?

**Đáp án:** Chưa. Phải so với SLO, error rate, throughput và biến động theo nhiều lượt.

**14.** Nếu container hết swap nhưng heap chưa đầy, có thể OOM kill không?

**Đáp án:** Có. Tổng memory cgroup còn gồm nonheap/native và nhiều loại memory khác.

**15.** Khi CPU tăng mà throughput giữ nguyên, nên xem gì?

**Đáp án:** CPU usage/throttling, workers, lock/I/O, GC, host contention và workload thực.

**16.** Cách chọn cấu hình cuối cùng?

**Đáp án:** Chọn cấu hình nhỏ/hợp lý về chi phí trong số những cấu hình hoàn thành đầy đủ workload, đạt throughput/latency/error SLO và có headroom an toàn.

## 18. Nguồn chính thức và tài liệu hiện còn áp dụng

- [Oracle JDK 10 Release Notes — Docker container improvements](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): bối cảnh container awareness của HotSpot từ Java 10.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `UseContainerSupport`, `ActiveProcessorCount`, `MaxRAMPercentage`, `-XshowSettings` và JVM options hiện đại.
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cú pháp các flags dùng với ví dụ runnable Java 17.
- [Oracle Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/nonheap memory usage và management API.
- [Oracle Java SE 17 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): số collections và thời gian GC khi số liệu được hỗ trợ.
- [Oracle Java SE 17 — Runtime.availableProcessors()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#availableProcessors()): JVM processor count và khả năng giá trị thay đổi.
- [Oracle Java SE 25 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): NMT ở HotSpot, giới hạn với third-party native allocations và `jcmd`.
- [Docker Engine — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/): `--cpus`, quota, shares, cpuset, memory, swap và cách enforcement.
- [Docker CLI — docker stats](https://docs.docker.com/reference/cli/docker/container/stats/): quan sát CPU/memory và ý nghĩa metric do Docker hiển thị.
- [Linux Kernel — Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.max`, `cpu.stat`, `memory.max`, `memory.current` và `memory.events`.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory requests và limits, CPU throttling, reactive memory OOM.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): trạng thái terminated/restart và cách quan sát Pod.
- [OpenJDK JDK-8146115 — Improve docker container detection and resource configuration usage](https://bugs.openjdk.org/browse/JDK-8146115): tư liệu thiết kế về nhận diện tài nguyên container của JVM.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR và phân tích runtime.
- [OpenJDK JMH](https://github.com/openjdk/jmh): công cụ benchmark chuẩn khi nghiên cứu phép tính vi mô/JIT.

**Kết luận:** Muốn **đánh giá ứng dụng Java trong container có nhiều mức CPU và memory**, hãy thiết kế một **ma trận thực nghiệm giữ nguyên từng nhóm biến**, dùng `--cpus` và `--memory` để tạo giới hạn có thể kiểm, giữ `-Xmx`/concurrency/workload cố định trong từng vòng thử, đo throughput, latency, GC, CPU throttling và memory cgroup events. `Runtime.availableProcessors()` không phải CPU quota, `Java heap used` không phải container memory, và memory limit cao hơn không tự đảm bảo hiệu năng tốt hơn. Một cấu hình đáng chọn phải **chạy đúng, không OOM, đạt SLO, có headroom và có chi phí hợp lý qua nhiều lần đo**.