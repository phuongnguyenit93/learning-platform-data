# Thực hành: Đo allocation và tác động của Garbage Collector bằng tải đại diện (Java 11+)

## 1. Mục tiêu bài thực hành

**Đề bài:** Tạo tải gần với cách ứng dụng thực cấp phát và giữ object, đo *allocation* (lượng cấp phát heap), quan sát GC, rồi so sánh ảnh hưởng của các collector khi **giữ nguyên đặc điểm tải**. Ví dụ sử dụng những API và công cụ còn áp dụng trên Java hiện đại: Java 11+, `com.sun.management.ThreadMXBean`, GC unified logging và Java Flight Recorder (JFR).

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **allocation rate**, **live set**, heap được sử dụng, và GC pause.
2. Mô tả tải từ kích thước yêu cầu, tần suất, object ngắn hạn và dữ liệu giữ lâu.
3. Đo bytes/request, MiB/s, throughput, latency p50/p95/p99 và hoạt động collector.
4. Chạy thí nghiệm G1/Parallel GC với heap và workload giống nhau, đồng thời nhận ra phép so sánh thiếu công bằng.
5. Dùng GC log/JFR để tìm sự kiện có khả năng làm tăng latency và đưa ra quyết định theo SLO.

**Giới hạn:** Ví dụ mô phỏng **một worker xử lý request tuần tự** với dữ liệu cache. Nó tạo được tải thử nghiệm có kiểm soát, nhưng chưa phản ánh chính xác dịch vụ nhiều luồng, I/O, network, queue và traffic thực. Muốn suy luận cho production, cần hiệu chỉnh đặc điểm tải dựa trên log/trace/metrics của ứng dụng rồi đo trong môi trường tương đương.

## 2. Các khái niệm cần đo đúng

| Chỉ số | Điều được phản ánh | Cách đo hoặc quan sát |
| --- | --- | --- |
| **Allocation rate (MiB/s)** | Số byte heap cấp phát mới mỗi giây, **kể cả object sẽ chết ngay** | JMX `ThreadMXBean` trong ví dụ; JFR/profiler để phân tích sâu |
| **Allocated bytes/request** | Byte cấp phát mới chia cho số request đã xử lý | Delta allocation / `requests` |
| **Live set** | Những object còn được tham chiếu và phải được GC bảo toàn | Cache cố định trong ví dụ; heap profile/GC logs trong hệ thống thật |
| **Heap used** | Dung lượng heap đang được sử dụng tại một mốc; không tương đương tổng số byte đã cấp phát | GC log/heap metrics |
| **Actual throughput** | Số request hoàn thành / thời gian | `actual_rps` |
| **Latency p50/p95/p99** | Phân vị thời gian xử lý một request | `System.nanoTime()` quanh `request(...)`; chưa gồm queue/network |
| **GC pause** | Thời gian ứng dụng bị dừng bởi một công đoạn GC/safepoint | GC unified log/JFR, xem phân phối pause và max |
| **GC count/time JMX** | Số collection và thời gian GC mà JVM báo cáo | `GarbageCollectorMXBean`; chỉ số phụ, không thay được pause timeline |
| **CPU, RSS, memory limit** | Điều kiện tài nguyên có thể khiến GC và throughput khác nhau | OS/container monitoring, JVM flags |

Ví dụ một request tạo mảng 8 KiB rồi giải phóng ngay thì **đã cấp phát** 8 KiB dù sau GC phần heap đó có thể được tái sử dụng. Ngược lại, cache giữ mảng qua nhiều request làm tăng live set. Giảm allocation có thể giúp bớt áp lực GC nhưng không bảo đảm giảm p99 nếu nút thắt nằm ở I/O hoặc lock.

**Giới hạn của JMX ở đây:** Chương trình dùng `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(long[])` và danh sách ID của các **platform thread còn sống** tại mỗi snapshot. Delta là **ước lượng allocation**, có thể bao gồm thread nền, bỏ sót thread đã kết thúc giữa hai lần đọc và không bao gồm toàn bộ native allocation hay các virtual thread trên JDK mới. JVM có thể trả về `-1` nếu không hỗ trợ. Không được coi đây là tổng allocation chính xác của dịch vụ đa luồng; cần đối chiếu với JFR, profiler và metric runtime.

## 3. Thế nào là “tải đại diện”?

Trước khi chạy benchmark, hãy biết ứng dụng thật có:

- **RPS:** trung bình, peak, burst, phân phối theo thời gian và tỷ lệ request bị từ chối. Target RPS chỉ là **yêu cầu của load generator**; phải kiểm tra RPS thực đạt được.
- **Payload:** size p50/p95, tỷ lệ request lớn/nhỏ, các bước parse/serialize và mức cấp phát các buffer/chuỗi/bản sao.
- **Tuổi thọ object:** dữ liệu tạm trong một request, request context, cache, session, queue, index và dữ liệu tồn tại qua nhiều collection.
- **Concurrency và phụ thuộc:** số thread/connection, blocking I/O, truy vấn dữ liệu, contention. Tải một thread trong chương trình mẫu không mô tả tất cả yếu tố đó.
- **Giới hạn tài nguyên và SLO:** JVM/JDK, số CPU, memory limit, heap, p99 end-to-end, throughput tối thiểu, max pause chấp nhận được.

Không lấy dữ liệu người dùng nhạy cảm đưa trực tiếp vào benchmark. Có thể trích xuất phân phối và replay dữ liệu đã ẩn danh.

Bài mẫu mô phỏng mỗi request tạo mảng payload, điền dữ liệu, tính checksum CRC32, tạo response UTF-8. Một cache gồm các block 8 KiB tồn tại trong heap; cứ 8 request thay một block để tạo object có đời sống dài hơn. Chương trình nhận năm tham số:

| Tham số | Giá trị thí nghiệm | Ý nghĩa |
| --- | ---: | --- |
| `warmupSec` | 10 | Giây khởi động cho class loading/JIT và trạng thái heap |
| `measureSec` | 60 | Giây đo thực tế |
| `targetRps` | 400 | Nhịp mục tiêu; kiểm chứng với `actual_rps` |
| `payloadBytes` | 8192 | Byte của payload được tạo ở mỗi request |
| `retainedMiB` | 32 | MiB dữ liệu cache sống lâu (xấp xỉ, chưa kể object header/reference) |

Cỡ cache là một biến **khác** với allocation rate; tốc độ thay cache và số lượng request cũng có ảnh hưởng. Heap tổng còn chứa response, các object tạm, stack metadata và dữ liệu runtime, nên `retainedMiB=32` không có nghĩa heap used đúng 32 MiB.

## 4. Ví dụ Java 11+ biên dịch và chạy được

Tạo file **`GcWorkload.java`** đúng như sau. Chương trình dùng các API Java 11 đang được hỗ trợ và không gọi `System.gc()`:

~~~java
import com.sun.management.ThreadMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.locks.LockSupport;
import java.util.zip.CRC32;

public final class GcWorkload {
    private static final int CACHE_BLOCK = 8 * 1024;
    private static final int MAX_SAMPLES = 50_000;
    private static volatile byte[] lastResponse;
    private static volatile long lastChecksum;
    private static byte[][] cache;
    private static int cacheCursor;
    private static long requestId;

    private static final class Phase {
        long operations;
        long elapsedNanos;
        long missedSlots;
        long allocatedBytes;
        long collections;
        long collectionTimeMs;
        long[] latencySamples;
        int sampleCount;
    }

    public static void main(String[] args) {
        if (args.length != 5) {
            System.err.println("Usage: java GcWorkload "
                    + "<warmupSec> <measureSec> <targetRps> "
                    + "<payloadBytes> <retainedMiB>");
            System.exit(2);
        }

        int warmupSec = Integer.parseInt(args[0]);
        int measureSec = Integer.parseInt(args[1]);
        int targetRps = Integer.parseInt(args[2]);
        int payloadBytes = Integer.parseInt(args[3]);
        int retainedMiB = Integer.parseInt(args[4]);

        if (warmupSec < 1 || measureSec < 1 || targetRps < 1
                || targetRps > 100_000 || payloadBytes < 64
                || payloadBytes > 1024 * 1024
                || retainedMiB < 0 || retainedMiB > 1024) {
            throw new IllegalArgumentException("Invalid workload parameters");
        }

        int slots = (int) (((long) retainedMiB * 1024 * 1024
                + CACHE_BLOCK - 1) / CACHE_BLOCK);
        cache = new byte[slots][];
        for (int i = 0; i < slots; i++) {
            cache[i] = new byte[CACHE_BLOCK];
            cache[i][0] = (byte) i;
        }

        ThreadMXBean allocationBean = allocationBean();
        System.out.printf(Locale.ROOT,
                "java=%s processors=%d collectors=%s%n",
                System.getProperty("java.runtime.version"),
                Runtime.getRuntime().availableProcessors(),
                collectorNames());
        System.out.printf(Locale.ROOT,
                "target_rps=%d payload_bytes=%d retained_mib=%d%n",
                targetRps, payloadBytes, retainedMiB);

        runPhase(warmupSec, targetRps, payloadBytes, allocationBean, false);
        System.out.println("warmup=complete");

        Phase measured = runPhase(
                measureSec, targetRps, payloadBytes, allocationBean, true);
        print(measured);
        System.out.println("sink_checksum=" + lastChecksum);
    }

    private static ThreadMXBean allocationBean() {
        java.lang.management.ThreadMXBean base =
                ManagementFactory.getThreadMXBean();
        if (!(base instanceof ThreadMXBean)) {
            return null;
        }
        ThreadMXBean extension = (ThreadMXBean) base;
        try {
            if (!extension.isThreadAllocatedMemorySupported()) {
                return null;
            }
            if (!extension.isThreadAllocatedMemoryEnabled()) {
                extension.setThreadAllocatedMemoryEnabled(true);
            }
            return extension;
        } catch (SecurityException | UnsupportedOperationException ex) {
            return null;
        }
    }

    private static void request(int payloadBytes) {
        long id = ++requestId;

        // Tạm thời: mô phỏng parse dữ liệu, tính checksum và tạo response.
        byte[] payload = new byte[payloadBytes];
        Arrays.fill(payload, (byte) (id & 0xff));
        CRC32 crc = new CRC32();
        crc.update(payload, 0, payload.length);
        byte[] response = ("id=" + id + ";crc=" + crc.getValue())
                .getBytes(StandardCharsets.UTF_8);

        // Sống lâu hơn: bộ đệm cache có kích thước gần cố định,
        // thay một phần tử trên mỗi 8 yêu cầu.
        if (cache.length != 0 && (id & 7) == 0) {
            byte[] cached = Arrays.copyOf(payload, CACHE_BLOCK);
            cache[cacheCursor] = cached;
            cacheCursor = (cacheCursor + 1) % cache.length;
        }

        lastResponse = response; // Làm kết quả quan sát được, tránh bỏ việc.
        lastChecksum = crc.getValue() ^ response.length;
    }

    private static Phase runPhase(int seconds, int targetRps,
                                  int payloadBytes, ThreadMXBean allocationBean,
                                  boolean record) {
        Phase p = new Phase();
        long expected = (long) seconds * targetRps;
        long stride = Math.max(1L,
                (expected + MAX_SAMPLES - 1) / MAX_SAMPLES);
        int capacity = (int) Math.min(MAX_SAMPLES,
                (expected + stride - 1) / stride);
        p.latencySamples = record ? new long[capacity] : new long[0];

        long allocatedBefore = allocatedNow(allocationBean);
        long gcCountBefore = gcCount();
        long gcTimeBefore = gcTimeMs();
        long started = System.nanoTime();
        long deadline = started + seconds * 1_000_000_000L;
        long period = Math.max(1L, 1_000_000_000L / targetRps);
        long next = started;

        while (true) {
            long now = System.nanoTime();
            if (now >= deadline) {
                break;
            }
            if (now < next) {
                LockSupport.parkNanos(Math.min(next - now, 1_000_000L));
                continue;
            }
            if (now - next >= period) {
                p.missedSlots += (now - next) / period;
                next = now;
            }
            long operationStart = System.nanoTime();
            request(payloadBytes);
            long operationNanos = System.nanoTime() - operationStart;
            if (record && p.operations % stride == 0
                    && p.sampleCount < p.latencySamples.length) {
                p.latencySamples[p.sampleCount++] = operationNanos;
            }
            p.operations++;
            next += period;
        }

        p.elapsedNanos = System.nanoTime() - started;
        long allocatedAfter = allocatedNow(allocationBean);
        long gcCountAfter = gcCount();
        long gcTimeAfter = gcTimeMs();
        p.allocatedBytes = difference(allocatedBefore, allocatedAfter);
        p.collections = difference(gcCountBefore, gcCountAfter);
        p.collectionTimeMs = difference(gcTimeBefore, gcTimeAfter);
        return p;
    }

    private static long allocatedNow(ThreadMXBean bean) {
        if (bean == null) {
            return -1;
        }
        long[] ids = ManagementFactory.getThreadMXBean().getAllThreadIds();
        long[] amounts = bean.getThreadAllocatedBytes(ids);
        long total = 0;
        boolean supported = false;
        for (long amount : amounts) {
            if (amount >= 0) {
                total += amount;
                supported = true;
            }
        }
        return supported ? total : -1;
    }

    private static long gcCount() {
        long total = 0;
        boolean supported = false;
        for (GarbageCollectorMXBean bean
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            long n = bean.getCollectionCount();
            if (n >= 0) {
                total += n;
                supported = true;
            }
        }
        return supported ? total : -1;
    }

    private static long gcTimeMs() {
        long total = 0;
        boolean supported = false;
        for (GarbageCollectorMXBean bean
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            long n = bean.getCollectionTime();
            if (n >= 0) {
                total += n;
                supported = true;
            }
        }
        return supported ? total : -1;
    }

    private static long difference(long before, long after) {
        return before < 0 || after < 0 ? -1 : after - before;
    }

    private static String collectorNames() {
        StringBuilder names = new StringBuilder();
        for (GarbageCollectorMXBean bean
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            if (names.length() > 0) {
                names.append(", ");
            }
            names.append(bean.getName());
        }
        return names.toString();
    }

    private static double percentileMs(long[] sorted, double fraction) {
        int index = Math.max(0,
                (int) Math.ceil(sorted.length * fraction) - 1);
        return sorted[index] / 1_000_000.0;
    }

    private static void print(Phase p) {
        double elapsedSec = p.elapsedNanos / 1_000_000_000.0;
        System.out.printf(Locale.ROOT,
                "requests=%d elapsed_sec=%.3f actual_rps=%.1f missed_slots=%d%n",
                p.operations, elapsedSec, p.operations / elapsedSec,
                p.missedSlots);

        if (p.sampleCount != 0) {
            long[] sorted = Arrays.copyOf(p.latencySamples, p.sampleCount);
            Arrays.sort(sorted);
            System.out.printf(Locale.ROOT,
                    "latency_samples=%d p50_ms=%.3f p95_ms=%.3f p99_ms=%.3f%n",
                    p.sampleCount, percentileMs(sorted, 0.50),
                    percentileMs(sorted, 0.95),
                    percentileMs(sorted, 0.99));
        }

        if (p.allocatedBytes >= 0 && p.operations > 0) {
            System.out.printf(Locale.ROOT,
                    "allocated_mib_per_sec=%.2f allocated_bytes_per_request=%.1f%n",
                    p.allocatedBytes / 1_048_576.0 / elapsedSec,
                    (double) p.allocatedBytes / p.operations);
        } else {
            System.out.println("allocation=unavailable_on_this_jvm");
        }

        System.out.printf(Locale.ROOT,
                "gc_collections=%d gc_collection_time_ms=%d%n",
                p.collections, p.collectionTimeMs);
    }
}
~~~

### Phân tích cơ chế đo trong code

- **Warmup tách khỏi measurement:** `runPhase` chạy hai lần. Warmup được thực hiện trước khi đọc các số của giai đoạn đo; với ứng dụng thật, cần kiểm tra đã ổn định JIT, cache và live set chưa.
- **Allocation:** trước/sau giai đoạn đo, `getAllThreadIds()` liệt kê các platform thread còn sống và `getThreadAllocatedBytes(long[])` lấy ước lượng byte đã cấp phát. Lấy hiệu giữa hai tổng; nếu unsupported, chương trình in `allocation=unavailable_on_this_jvm`. Trong workload một worker, con số khá hữu ích để quan sát thay đổi; trong dịch vụ đa luồng phức tạp, số liệu cần được xác minh bằng profiler.
- **Latency:** lấy thời gian từ trước tới sau lời gọi `request`, lấy mẫu đều đặn tối đa 50.000 request, sắp xếp mẫu và tính phân vị. Đây là **service time** cục bộ, không phải end-to-end request latency. Nếu chỉ có vài chục mẫu, p99 rất thiếu ổn định.
- **Pacing:** `LockSupport.parkNanos` nhường CPU khi chưa tới lượt. Độ phân giải timer và scheduler (đặc biệt trên Windows hoặc container) có thể khiến `target_rps` không đạt được. `missed_slots` đo số slot trễ/bỏ lỡ gần đúng. Với request dài, chương trình bỏ nhịp cũ thay vì chạy đuổi không giới hạn.
- **Chống JIT loại bỏ công việc:** response cuối được gán vào `lastResponse` (volatile), checksum lưu trong `lastChecksum`. Tuy vậy phép đo tổng hợp vẫn bị ảnh hưởng bởi JIT, CPU và các tối ưu phụ thuộc phiên bản JVM.
- **GC time/count:** `GarbageCollectorMXBean` chỉ dùng làm chỉ số phụ. Đặc biệt với collector concurrent, collection time JMX không nhất thiết bằng thời gian ứng dụng bị dừng. Muốn xem pause duration, kiểm tra `-Xlog`/JFR.
- **Output không cố định:** RPS thực, allocation và các phân vị phụ thuộc máy, collector, JVM, tải, OS. Không có giá trị stdout số học duy nhất đúng cho mọi máy.

## 5. Chạy thí nghiệm so sánh G1 và Parallel GC

Dùng JDK 11+ và chạy trong thư mục chứa `GcWorkload.java`:

~~~bash
javac --release 11 GcWorkload.java
~~~

**Lần A — G1**, heap cố định 128 MiB:

~~~bash
java -Xms128m -Xmx128m -XX:+UseG1GC "-Xlog:gc*,safepoint:file=g1-gc.log:uptime,level,tags" GcWorkload 10 60 400 8192 32
~~~

**Lần B — Parallel GC**, giữ nguyên heap và năm tham số:

~~~bash
java -Xms128m -Xmx128m -XX:+UseParallelGC "-Xlog:gc*,safepoint:file=parallel-gc.log:uptime,level,tags" GcWorkload 10 60 400 8192 32
~~~

G1 và Parallel đều là các collector HotSpot còn hỗ trợ. G1 thiết kế để cân bằng throughput với thời gian pause; Parallel thường thiên về thông lượng. Đây là định hướng thiết kế, **không phải đảm bảo** một collector sẽ thắng trên mọi workload. Trong nhiều cấu hình server-class, G1 là mặc định, nhưng nên dùng cờ lựa chọn tường minh khi so sánh.

`-Xms128m` và `-Xmx128m` giữ heap ban đầu và tối đa giống nhau; thay collector là biến thử nghiệm chính. Nếu bạn thay kích thước heap hay live set thì đó là **một thí nghiệm khác**. Với máy ít RAM/CPU, chọn thông số thấp hơn nhưng giữ giống nhau giữa hai lần chạy.

`-Xlog:gc*,safepoint` là unified logging từ Java 9 trở đi và vẫn được dùng. Tránh các cờ GC logging cũ đã deprecated/thay thế như `-Xloggc`, `-XX:+PrintGCDetails` trong script benchmark mới. File log có thể chứa sự kiện từ warmup, vì thế cần căn mốc `uptime` khi phân tích giai đoạn measurement.

Chương trình in các trường sau, **số thực tế thay đổi theo môi trường**:

~~~text
java=... processors=... collectors=...
target_rps=... payload_bytes=... retained_mib=...
warmup=complete
requests=... elapsed_sec=... actual_rps=... missed_slots=...
latency_samples=... p50_ms=... p95_ms=... p99_ms=...
allocated_mib_per_sec=... allocated_bytes_per_request=...
gc_collections=... gc_collection_time_ms=...
sink_checksum=...
~~~

Nếu JVM không hỗ trợ JMX allocation, chương trình in `allocation=unavailable_on_this_jvm` thay cho hai trường allocation. Mã nguồn đã được kiểm tra biên dịch bằng `javac --release 11` và chạy trên JDK thực tế; giá trị số không thể dự đoán chính xác khi chưa chạy trên máy bạn.

### Điều kiện tối thiểu để so sánh công bằng

1. **Cùng máy và bản JDK:** vendor/version/build, CPU được JVM nhìn thấy, heap, container memory limit, object sizes, cache, thời gian đo và cấu hình logging giống nhau.
2. **Cùng tải thực hiện:** kiểm tra `actual_rps` và `missed_slots`. Nếu target 2500 RPS nhưng chạy thực tế chỉ 700 RPS do scheduler, không xem đó là thử nghiệm ở 2500 RPS; hạ target hoặc dùng load generator chuẩn hơn.
3. **Warmup và thời gian đo hợp lý:** đo đủ lâu để có nhiều collection; pause hiếm phải đo lâu hơn. Lặp lại **nhiều process độc lập** cho mỗi collector (chẳng hạn 5 lần), đổi thứ tự A/B và ghi median + độ biến thiên.
4. **Theo dõi môi trường:** CPU utilization, throttling, swap, heap after GC, RSS, tốc độ ổ đĩa/ghi log, điều kiện không phát sinh OOM hoặc chặn thread bất thường.
5. **Không cưỡng bức GC:** gọi `System.gc()` trong vòng đo làm thay đổi hoàn toàn pattern và có thể khiến kết luận sai. Không giảm kích thước heap chỉ để “ép hiện GC” rồi suy luận trực tiếp ra production.
6. **Đo latency end-to-end riêng:** nếu bài toán là HTTP service, phát tải từ client và theo dõi thời gian phản hồi, hàng đợi và tỷ lệ lỗi; mã này chỉ đo thời gian xử lý tại một worker.

## 6. Phân tích allocation và ảnh hưởng của GC

**Bước 1 — Kiểm tra tải trước khi nhìn collector.** Ghi `target_rps`, `actual_rps`, `missed_slots` và CPU. Nếu RPS không đạt, hai run có thể đang ở các điểm làm việc khác nhau. Tăng RPS thường làm allocation MiB/s cao hơn ngay cả khi bytes/request gần giữ nguyên.

**Bước 2 — Phân tích allocated bytes/request và live set riêng.** Nếu payload đổi từ 8 KiB thành 16 KiB, bytes/request thường tăng; điều này không cho biết ngay số byte đang còn sống sau GC. Nếu cache tăng từ 16 MiB lên 64 MiB, old/live set có thể tăng dù kiểu request giữ nguyên. Đối chiếu với heap sau collection, GC log hoặc heap profile khi cần.

**Bước 3 — Xem các pause thực trong log/JFR.** Tìm sự kiện kiểu `Pause ...`, thời lượng, vùng heap trước/sau collection, Full GC và giai đoạn concurrent. Dòng log chi tiết cùng GC ID không phải một collection mới. Thu thập số lần pause, p95/p99 và max pause; nếu chỉ có rất ít sự kiện thì các phân vị ít ý nghĩa.

**Bước 4 — Đối chiếu timeline với request latency.** Khi p99 service time tăng, xem timestamp tương ứng có GC pause, CPU throttling, lock contention hay I/O stall không. Đồng thời theo dõi p99 end-to-end từ phía client. Tương quan không tự động chứng minh nguyên nhân, nhưng giúp khoanh vùng cần profiler.

**Bước 5 — So sánh theo SLO.** Collector có average throughput tốt hơn nhưng pause p99 vượt giới hạn có thể không phù hợp với dịch vụ cần latency thấp. Collector có pause ngắn nhưng CPU cao hơn và không đạt RPS có thể cũng không phù hợp. Không có lựa chọn thắng tuyệt đối: dùng cả latency, error rate, throughput, memory và CPU.

### Vì sao GC collection time JMX chỉ là tín hiệu phụ?

`gc_collection_time_ms` là hiệu của `getCollectionTime()` trên các GC MXBean mà JVM cung cấp. Nó không tự bảo đảm bằng tổng **stop-the-world pause**, vì collector concurrent và cách đếm từng MXBean có khác biệt. Tỷ số `gc_collection_time_ms / elapsed_ms` không phải phần trăm downtime đáng tin cho mọi JVM. **GC log/JFR là nơi phù hợp hơn để lấy phân phối pause thực**, còn JMX giúp theo dõi xu hướng.

## 7. Dùng Java Flight Recorder (JFR) để đào sâu

JFR được tích hợp với Java 11 và còn là công cụ hiện hành trên JDK mới. Ví dụ ghi recording G1 với cùng workload:

~~~bash
java -Xms128m -Xmx128m -XX:+UseG1GC "-XX:StartFlightRecording=filename=g1.jfr,dumponexit=true,settings=profile" GcWorkload 10 60 400 8192 32
~~~

Phân tích bằng tiện ích `jfr` có trong JDK:

~~~bash
jfr summary g1.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause g1.jfr
~~~

Mở `g1.jfr` bằng **Java Mission Control (JMC)** để xem GC timeline, CPU, allocation samples và stack trace của các sự kiện đã được ghi. JFR có thể lấy mẫu allocation; không xem số event là tổng object chính xác, và không suy ra byte/request tuyệt đối từ số mẫu nếu chưa xét phương pháp sampling/cấu hình ghi.

Nếu so sánh collector bằng recording, bật cùng `settings` ở cả hai lần vì JFR có overhead. Có thể dùng profiler để tìm allocation stack trong code thực (parser, string concatenation, serialization, boxing), rồi tối ưu tác nhân tạo object trước khi can thiệp thông số collector.

## 8. Bài tập mở rộng

1. **Đổi allocation intensity:** chạy `payloadBytes=8192` rồi `16384`; giữ `retainedMiB=32`, RPS/heap/collector, so bytes/request, actual RPS, số GC và pause.
2. **Đổi live set:** giữ payload, chạy `retainedMiB=16` rồi `64`. So heap sau GC, frequency, pause. Nếu xảy ra OOM, ghi nhận giới hạn heap trong bài, giảm live set hoặc mở một thí nghiệm sizing mới.
3. **Đổi RPS:** thử 200, 400, 800. Chỉ dùng các mức mà `actual_rps` đủ gần target; nếu `missed_slots` lớn, điều chỉnh bộ phát tải hoặc hạ RPS.
4. **Quan sát collector khác trên JDK thích hợp:** nếu môi trường hỗ trợ, thử lựa chọn collector hiện đại khác trong một thí nghiệm riêng; luôn kiểm tra phiên bản JDK và khả năng hỗ trợ thực, không mặc định những flag của JDK mới chạy được trên Java 11.
5. **Đưa vào ứng dụng thật:** ghi lại phân phối payload, concurrency và retention từ ứng dụng; phát tải với dữ liệu đã ẩn danh, quan sát JFR/GC log ở JVM server và latency từ client. So sánh tính đại diện trước khi điều chỉnh collector/heap.

## 9. Những lỗi phổ biến và cách xử lý

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Benchmark một vòng chạy rất ngắn | Class loading, JIT, CPU scheduling lấn át GC | Warmup, đo lâu, chạy nhiều process |
| Chỉ kiểm tra target RPS | Khi scheduler chậm, tải thật thấp hơn nhiều | So `actual_rps`, `missed_slots` và CPU |
| Nhìn GC count rồi kết luận pause | Count không nói rõ thời lượng hoặc max | Xem sự kiện pause trong GC log/JFR |
| Cho rằng allocated MiB = heap live MiB | Object tạm có thể chết rất nhanh | Đo allocation và retained heap riêng |
| Nhầm service time với end-to-end | Bỏ qua queue, network, downstream | Đo latency tại client/ingress |
| Coi tổng JMX là chính xác cho mọi thread | Thread kết thúc, virtual thread, native memory bị bỏ sót | Dùng JFR/profiler/metrics bổ sung |
| Dùng profiler ở một cấu hình duy nhất | Overhead đo làm A/B khó so sánh | Bật cùng cấu hình ở cả hai lần |
| Thêm `System.gc()` để chuẩn hóa | Tạo collection cưỡng bức không tự nhiên | Để collector hoạt động theo workload |
| Sửa đồng thời heap, collector và RPS | Không biết nguyên nhân thay đổi | Chỉ đổi một biến hoặc nhóm biến được kiểm soát |
| Nhìn một run rồi kết luận | Biến thiên giữa các run, JIT và GC nhiễu | Chạy lặp, đổi thứ tự, so phân phối |
| Dùng cờ GC log cũ | Gặp cờ deprecated hoặc hành vi khác | Dùng unified `-Xlog` hiện hành |

## 10. Tiêu chí nghiệm thu kết quả

Báo cáo bài thực hành nên có: JDK vendor/build và collector, CPU/RAM/container, heap `-Xms/-Xmx`, cấu hình tải, số giây warmup/measure, **target và actual RPS**, bytes/request, MiB/s (kèm giới hạn JMX), p95/p99 service time, GC pause p95/max từ log/JFR, số lần chạy, độ biến thiên và kết luận gắn với SLO. Khi dữ liệu chưa đủ hoặc workload chưa đại diện, nói rõ điều còn thiếu thay vì đưa ra kết luận tuyệt đối.

## 11. Tài liệu chính thức để tra cứu

- [Available Collectors — Oracle Java 25](https://docs.oracle.com/en/java/javase/25/gctuning/available-collectors.html): các collector hiện được hỗ trợ và tiêu chí lựa chọn.
- [Java launcher — Java 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xlog`, lựa chọn collector, `-XX:StartFlightRecording`.
- [ThreadMXBean — Java 11](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): `getThreadAllocatedBytes`, trạng thái hỗ trợ và phép đo allocation.
- [GarbageCollectorMXBean — Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): ý nghĩa count và collection time.
- [Java Flight Recorder API — Java 25](https://docs.oracle.com/en/java/javase/25/jfapi/index.html): ghi nhận và phân tích sự kiện runtime.

**Kết luận kỹ thuật của bài:** kiến thức bền vững nằm ở cách dựng workload, giữ điều kiện so sánh, đo allocation và phân phối GC pause chính xác. Không có collector nào phù hợp mọi ứng dụng; dữ liệu trên bản JDK và tải thực quyết định lựa chọn.
