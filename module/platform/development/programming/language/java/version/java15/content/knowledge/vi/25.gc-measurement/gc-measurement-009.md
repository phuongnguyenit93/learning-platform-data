# Kiểm thử quá tải và khả năng phục hồi khi đo lường GC trong Java 15+

## 1. Mục tiêu: phát hiện điểm gãy và chứng minh hệ thống phục hồi được

Một dịch vụ Java có thể xử lý rất tốt ở tải bình thường nhưng mất ổn định khi **tốc độ cấp phát object**, số request đồng thời, kích thước live set hoặc tốc độ giữ dữ liệu trong queue/cache tăng đột ngột. Garbage collector (GC) cố thu hồi bộ nhớ, nhưng vẫn phải cạnh tranh CPU, memory bandwidth và heap headroom với application threads.

Kiểm thử **quá tải (*overload/stress*)** không chỉ hỏi “JVM có bị `OutOfMemoryError` không?”. Nó phải xác định:

1. **Tải công bố có thể phục vụ** (*supported load*) là bao nhiêu, với p95/p99 latency, throughput và error rate thỏa mục tiêu.
2. **Điểm bão hòa** nằm ở đâu và triệu chứng sớm là gì: queue tăng, CPU throttling, allocation stalls, GC pauses, timeouts hoặc lỗi.
3. Khi tải **vượt công suất**, ứng dụng có **giới hạn tài nguyên**, **backpressure/load shedding** và trả lỗi có kiểm soát hay cứ nhận thêm đến khi sụp đổ.
4. Khi tải giảm lại, **độ trễ, tỷ lệ lỗi, backlog, mức dùng heap và số instance khỏe mạnh** có trở lại ngưỡng chấp nhận được trong một thời hạn xác định không.
5. Nếu xảy ra lỗi nặng hơn (OOM, container OOMKilled, restart), **dịch vụ** có tự phục hồi qua supervisor/orchestrator hay không, và có mất dữ liệu/vi phạm idempotency không.

**Phân biệt ba khái niệm:**

- **GC đang chạy:** đã xác định collector, thấy GC logs/events.
- **Thử nghiệm đã hoàn thành:** chương trình/luồng thao tác không bị lỗi trong bài test cụ thể.
- **Khả năng phục hồi đạt yêu cầu:** service trở về trạng thái ổn định theo SLO và recovery criteria; đây là kết luận cần số liệu nhiều lần thử, không thể chỉ đọc exit code 0.

Bài áp dụng trên **Java 15+**, ưu tiên các API/flags vẫn hiện hành trên **JDK 17, 21, 24–26**. Các ví dụ Java tự chứa được biên dịch bằng `javac --release 17`. GC options chỉ là tham số của HotSpot và phụ thuộc JDK/vendor/OS; không mặc định mọi collector đều hỗ trợ trên mọi runtime.

## 2. Cơ chế làm quá tải GC và hệ quả đến ứng dụng

Khi application code gọi `new` liên tục, JVM phải cấp phát bộ nhớ object. Object hết reachable có thể được GC thu hồi, nhưng **GC không tạo ra bộ nhớ vô hạn**, cũng không tự giải quyết giữ dữ liệu không giới hạn.

```text
Tốc độ request tăng / payload lớn hơn / batch rộng hơn
                |
                v
       Allocation rate tăng (MiB/s)
                |
                +-- object ngắn sống ---> GC phải reclaim thường xuyên
                |
                +-- object còn được giữ ---> live set/old occupancy tăng
                |
                +-- large objects -------> humongous/fragmentation pressure
                |
                v
      GC work + CPU + memory bandwidth + heap headroom
                |
                +-- còn đủ năng lực --> latency/throughput ổn định
                |
                +-- gần ngưỡng -----> GC cycles nhiều, queue, p99 tăng
                |
                +-- vượt ngưỡng ----> allocation stalls / Full GC /
                                      OOME / process death
                |
                v
  Giảm tải, loại bỏ backlog, kiểm tra recovery
```

Tốc độ cấp phát (**allocation rate**) và mức dùng heap (**heap occupancy**) không phải cùng một số:

- Tạo 500 MiB object ngắn sống trên **một khoảng thời gian**, nhưng chỉ giữ 20 MiB reachable, có thể không cần heap 500 MiB tại cùng một thời điểm.
- Giữ 200 MiB trong cache/queue và tiếp tục tạo object mới có thể làm GC không còn đủ free space, dù tốc độ cấp phát trung bình không quá cao.
- Một hệ thống có GC pauses ngắn vẫn có thể bị **pacing/allocation stalls**, cạn CPU, timeout hoặc nghẽn thread pool.

**GC pressure không đồng nghĩa GC là root cause.** Queue không có giới hạn, retry storm, DB nghẽn, slow downstream, thread contention hoặc CPU quota thấp có thể dẫn đến allocation tăng rồi GC bị áp lực như **hệ quả**. Đo cả request path lẫn GC mới phân biệt được.

## 3. Các kiểu kiểm thử phải tách bạch

| Loại thử nghiệm | Cách tăng tải | Câu hỏi cần trả lời |
|---|---|---|
| **Baseline** | Tải nhẹ/ổn định, sau warm-up | Hệ thống bình thường có p95/p99, GC rate và memory footprint thế nào? |
| **Ramp / step test** | Tăng request rate hoặc concurrency từng nấc | Ngưỡng nào bắt đầu làm latency/error/queue tăng nhanh? |
| **Spike / burst** | Tăng tải đột ngột trong thời gian ngắn | Headroom và autoscaling/backpressure có hấp thụ đợt đỉnh được không? |
| **Sustained stress** | Duy trì trên mức công suất được tuyên bố | Hệ thống suy giảm có kiểm soát hay bị sập dây chuyền? |
| **Soak / endurance** | Tải vừa hoặc cao trong thời gian đủ dài | Có memory leak, queue/backlog tăng dần, fragmentation và GC trend xấu không? |
| **Recovery** | Giảm tải từ stress về baseline và đo từng cửa sổ | Có trả p99/error/heap/backlog về mức đạt yêu cầu không? Mất bao lâu? |
| **Fault injection** | Cô lập tình huống restart, OOM, node loss, CPU throttle | Có xử lý lỗi và phục hồi dịch vụ/dữ liệu theo thiết kế không? |

**Tránh định nghĩa “stress” bằng một số duy nhất như `-Xmx128m`.** Một heap nhỏ có thể làm lộ bug/pressure nhanh hơn, nhưng ứng dụng production có heap khác, live set khác và concurrency khác. Stress test có ý nghĩa phải có **workload profile** và kết quả gắn với một môi trường đã mô tả.

Ví dụ để phân biệt:

```text
normal:  400 request/s trong 10 phút
step 1:  600 request/s trong 5 phút
step 2:  800 request/s trong 5 phút
spike:  1600 request/s trong 30 giây
return:  400 request/s, quan sát thêm 5 phút
```

Đây là **kịch bản minh họa**, không phải mức công suất hợp lệ cho mọi service. Cần chọn số, thời gian và concurrency dựa trên capacity/SLO thật, không lấy các giá trị này để áp dụng ngay ở production.

## 4. Trước khi chạy: định nghĩa tiêu chí đạt và môi trường

Một bài kiểm thử có thể tạo đồ thị rất đẹp mà không đưa ra được kết luận nếu không có acceptance criteria **trước khi chạy**.

Cần ghi rõ:

- **SLO dưới tải được hỗ trợ:** ví dụ p99 request latency không quá **200 ms** và error rate dưới **1%** trong khoảng tải đã công bố. Những số này chỉ là **giả định của ví dụ**, không phải chuẩn của Java.
- **Quá tải có kiểm soát:** request vượt capacity nên nhận `429`, `503` hoặc response phù hợp trong một deadline, thay vì bị treo/queue vô hạn. Xác định cách phân loại rejected vs service errors khi tính SLO.
- **Recovery:** sau khi tải về mức bình thường, trong **2 phút** p99 và error rate trở lại các ngưỡng trên, backlog thu hẹp và instance đủ khỏe. Đây cũng là **ví dụ yêu cầu**, không áp dụng chung.
- **Không mất dữ liệu sai hợp đồng:** kiểm tra idempotency, duplicate requests, semantics của retries; metric latency “đẹp” không bù được dữ liệu sai.
- **Giới hạn tài nguyên:** heap/RSS, container memory, CPU quota, thread/connection pool, queue depth và eviction policy.
- **Giới hạn phạm vi tải:** chỉ môi trường staging/lab có quyền, tách các downstream/tenant thật, dữ liệu giả và kế hoạch dừng test.

**Baseline phải tương đương:** cùng JDK build, GC, `-Xms/-Xmx`, CPU limit, hardware, traffic mix, dependency latency và warm-up khi so sánh một thay đổi. Nếu thay collector và tăng gấp đôi RAM trong cùng thử nghiệm, không thể kết luận collector là nguyên nhân cải thiện.

## 5. Workload profile ảnh hưởng GC thế nào?

Không chỉ số request/s; **mỗi request cấp phát gì và giữ bao lâu** cũng quyết định khả năng chịu tải.

| Yếu tố | Khi thay đổi | Điều cần đo |
|---|---|---|
| **Request size / JSON complexity** | Object graph lớn, nhiều mảng và String | Allocated bytes/request, allocations/s, CPU |
| **Concurrency** | Nhiều request cùng tồn tại | Live request objects, queue, threads, peak heap |
| **Cache/retention** | Keys hoặc results bị giữ lâu | Live set, old generation occupancy, eviction |
| **Batch size** | Một request tạo nhiều object một lượt | Allocation burst, p99, GC pause |
| **Payload lớn** | Humongous allocations hoặc direct buffers | Fragmentation, RSS, large-object allocation failures |
| **Retries/timeouts** | Failed requests quay lại | Retry amplification, queue growth và churn |
| **Downstream chậm** | Request giữ state lâu | Object lifetime, pending futures, backlog |
| **GC CPU** | Concurrent GC chia CPU với app | Throughput, CPU saturation, allocation stalls |
| **Native/direct memory** | `ByteBuffer.allocateDirect`, JNI, TLS | RSS/OOMKilled dù heap chưa chạm `-Xmx` |

**Tải có cùng RPS nhưng allocation rate khác nhau** không phải hai bài thử tương đương. Ví dụ một endpoint trả tài liệu lớn có thể cấp phát nhiều hơn nhiều so với endpoint health-check, dù throughput request bằng nhau.

Cần có **request mix** hoặc workload chia theo loại endpoint, không chỉ một route giả quá nhẹ. Khi muốn đo memory pressure, kết hợp cả **short-lived allocations** và **long-lived live set** thay vì chỉ tạo một mảng thật lớn rồi giữ nó mãi.

## 6. Những metric cần thu thập cùng thời gian

| Metric | Đơn vị/cách quan sát | Vai trò trong stress/recovery |
|---|---|---|
| **Arrival rate / offered load** | requests/s được load generator cố gửi | Biết tải yêu cầu, không lẫn với requests hoàn tất |
| **Completed throughput** | successful requests/s | Biết công suất thực đạt |
| **Latency p50/p95/p99/p99.9** | ms của request end-to-end | Phát hiện tail latency; không thay bằng average |
| **Timeouts / errors / rejections** | số lượng và tỷ lệ, phân tách theo loại | Nhận biết fail có kiểm soát vs service bất ổn |
| **In-flight / pending / queue depth** | count, age of oldest item | Phát hiện backlog che giấu quá tải |
| **Allocation rate** | MiB/s, allocated bytes/request | Đo tốc độ tạo object và đỉnh |
| **Live set / heap used/committed/max** | MiB và tỷ lệ qua thời gian | Theo dõi dữ liệu còn reachable, headroom |
| **GC cycles, pause histogram** | count, duration, percentiles | Phân biệt GC activity với GC stop-the-world |
| **GC CPU/concurrent work** | thời gian/CPU utilization | Đánh giá overhead và khả năng theo kịp |
| **Allocation stalls / pacing** | số lần và thời gian chờ | Có thể làm p99 xấu ngay cả khi GC pause ngắn |
| **Full GC / degenerated GC** | số lần, duration | Dấu hiệu collector pressure hoặc recovery mode |
| **Process RSS / container memory** | MiB, OOMKilled events | Phát hiện native memory vượt budget |
| **CPU throttling / saturation** | quota throttling, utilization | GC concurrent không có đủ CPU |
| **Recovery time** | giây từ lúc tải giảm đến khi đạt ngưỡng | Tiêu chí chính của khả năng phục hồi |
| **Restart count / healthy replicas** | count theo thời gian | Đánh giá phục hồi cấp tiến trình/service |

**Không đánh đồng `GarbageCollectorMXBean.getCollectionTime()` với tổng thời gian dừng application trong mọi collector.** Với G1, ZGC, Shenandoah hoặc các JVM khác, bean names, count/time semantics và hỗ trợ `-1` có thể khác. Để đo GC pause thật, ưu tiên **GC log/JFR events** được tài liệu phiên bản VM xác nhận.

## 7. Công cụ Java đang áp dụng: GC logs, JFR, JMX và hệ thống ngoài JVM

### 7.1. Unified GC logging

Với HotSpot Java 17+:

```bash
java -Xms64m -Xmx256m -Xlog:gc*=info:file=gc-stress.log:uptime,level,tags -cp . GcOverloadRecoveryDemo
```

Cú pháp `-Xlog` là cơ chế hiện hành. File sẽ chứa các sự kiện từ JVM (tùy collector), bao gồm thời điểm khởi tạo, chu kỳ và những dữ liệu GC khác.

Khi chạy trên **PowerShell**, có thể quote toàn bộ các `-XX` và `-Xlog` arguments:

```powershell
java '-Xms64m' '-Xmx256m' '-Xlog:gc*=info:file=gc-stress.log:uptime,level,tags' -cp . GcOverloadRecoveryDemo
```

Log GC có thể thay đổi **tên trường, tags, số lần và thời điểm** giữa JDK/collector. Không snapshot nguyên file để QA xuyên phiên bản; chỉ kiểm tra tín hiệu có ý nghĩa với collector thực tế, bảo vệ disk quota/rotation/retention.

### 7.2. Java Flight Recorder (JFR)

**JFR** là công cụ quan sát tích hợp trong OpenJDK/HotSpot hiện hành; tùy template/config có thể thu thập GC, allocation, CPU, thread stalls và các sự kiện liên quan.

Với một tiến trình đang chạy, có thể dùng:

```text
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jcmd <PID> JFR.start name=GcStress settings=profile duration=60s filename=gc-stress.jfr
jcmd <PID> JFR.check
```

`<PID>` là ký hiệu **thay bằng PID thực**, không gõ nguyên dấu góc trong shell. `JFR.start` ghi đến đường dẫn do bạn chỉ định nếu runtime/JFR/tooling/quyền cho phép. Tên event và event settings phụ thuộc JDK và template đang chọn, nên cần kiểm tra những event mong muốn **thật sự được bật**.

JFR/heap dump có thể chứa thông tin về class, stack traces hoặc dữ liệu ứng dụng nhạy cảm; phải kiểm soát **quyền truy cập, retention và đường dẫn xuất**. Không tự bật full tracing trên production hoặc ghi heap dump trong môi trường đa tenant mà không được phép.

### 7.3. JMX/ManagementFactory

Trong Java có API:

```java
ManagementFactory.getGarbageCollectorMXBeans();
ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
```

Đây là **các biểu thức minh họa trong class có `import java.lang.management.ManagementFactory;`**. Có thể đọc GC count/time và heap memory usage; tuy nhiên:

- `getCollectionCount()` có thể trả **`-1`** nếu VM không hỗ trợ.
- `getCollectionTime()` có semantics phụ thuộc VM/collector, **không thay thế pause histogram**.
- `MemoryUsage.getUsed()` là snapshot heap, **không phải allocation rate**.
- Một số beans hoặc pool names khác nhau giữa collector/JDK; không hard-code tên `"G1 Young Generation"`, `"ZGC Cycles"` hay tên tương tự làm điều kiện duy nhất để xác nhận Collector hoạt động.

### 7.4. Metrics ở ngoài JVM

Thu thập cả **CPU quota/throttling**, RSS/working set, OOMKilled từ container, reverse proxy/LB request metrics, queue length, thread pools, dependency latency. Một lần GC xấu có thể là hệ quả của **dịch vụ downstream chậm**, không phải lỗi tuning của GC.

Tất cả nguồn nên có **timestamp đồng bộ** để tương quan khi phân tích một spike. Không dùng một đồ thị chỉ lấy average toàn bộ thời gian kiểm thử để kết luận recovery.

## 8. Thiết kế bài lab an toàn: ba giai đoạn và giới hạn cấp phát

Bài lab sau làm việc **trong một tiến trình test độc lập**, không có network traffic và không cần dịch vụ thật. Chúng ta tạo một workload bằng các object `byte[]` có giới hạn số vòng lặp; mục tiêu là quan sát GC và xác minh code còn hoạt động sau một giai đoạn cấp phát cao.

**Cấu hình mặc định của lab:**

| Giai đoạn | Số batch | Mỗi batch | Tổng payload cấp phát |
|---|---:|---:|---:|
| **Baseline** | 128 | 8 mảng × 32 KiB | **32 MiB** |
| **Burst** | 2048 | 8 mảng × 32 KiB | **512 MiB** |
| **Post-burst** | 128 | 8 mảng × 32 KiB | **32 MiB** |
| **Live data giữ lại** | 256 mảng | 64 KiB/mảng | **16 MiB** |
| **Tổng tạo trong 3 phase** | — | — | **576 MiB** transient payload |
| **Cộng vùng retained được tạo** | — | — | **592 MiB** payload qua thời gian |

**576 MiB transient allocations không có nghĩa JVM cần heap 576 MiB cùng lúc.** Các mảng trong loop liên tục thay reference; nhiều object không còn reachable và có thể thu hồi. Lab dùng `-Xmx256m` với **16 MiB live retained** để có free headroom. Nó **không ép JVM phải OOM** và **không phải load test đại diện cho traffic HTTP**.

Đặc biệt: một bài test cấp phát cao nhưng chạy xong nhanh chưa chắc đã đạt **saturation/overload**. Cụm từ “burst” ở lab chỉ một phase có **tổng số allocation lớn hơn**, còn việc JVM thực sự bão hòa phải chứng minh bằng observed rate, CPU, GC cycle, queue hoặc stalls. Đừng đổi tên kết quả thành “ứng dụng chịu được 512 MiB/s” vì chương trình **không điều khiển rate cố định**.

### 8.1. Giới hạn an toàn

Code có `demo.burstBatches` mặc định **2048**, chỉ chấp nhận **1–8192**. Mỗi batch tạo **256 KiB transient data**. Đây là giới hạn lập trình để tránh một vòng vô hạn, **không phải định mức an toàn cho mọi máy**. Với `8192`, tổng transient allocations có thể rất lớn qua thời gian; chỉ thay đổi trong sandbox/lab được cấp quyền.

Không nên chạy nhiều bản sao đồng thời trên máy sản xuất, không chạy trong container dùng chung tài nguyên quan trọng và không dùng dữ liệu/credential người dùng thật trong bài thử.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình tự tạo các mảng trong RAM, giữ một lượng live set nhỏ, lấy mẫu **thời gian một batch cấp phát**, quan sát GC bean và in **11 dòng quyết định được** theo cấu hình mặc định đã kiểm thử. Bật property `demo.showMetrics=true` để xem rate và p99 thực đo nhưng **không ép giá trị đo thời gian phải giống nhau giữa hai máy**.

### 9.1. Tạo `GcOverloadRecoveryDemo.java`

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.ref.Reference;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public final class GcOverloadRecoveryDemo {
    private static final int KIB = 1024;
    private static final int MIB = KIB * KIB;
    private static final int BLOCK_SIZE = 32 * KIB;
    private static final int BLOCKS_PER_BATCH = 8;
    private static volatile byte[] observable;

    private static final class Phase {
        final int batches;
        final long bytes;
        final long elapsedNanos;
        final long p99BatchNanos;
        final long checksum;

        Phase(int batches, long bytes, long elapsedNanos,
                long p99BatchNanos, long checksum) {
            this.batches = batches;
            this.bytes = bytes;
            this.elapsedNanos = elapsedNanos;
            this.p99BatchNanos = p99BatchNanos;
            this.checksum = checksum;
        }
    }

    private static Phase runPhase(int batches) {
        long[] batchLatency = new long[batches];
        long totalChecksum = 0;
        long started = System.nanoTime();
        for (int i = 0; i < batches; i++) {
            long batchStarted = System.nanoTime();
            for (int j = 0; j < BLOCKS_PER_BATCH; j++) {
                byte[] block = new byte[BLOCK_SIZE];
                block[0] = (byte) (i + j);
                observable = block;
                totalChecksum += Byte.toUnsignedInt(block[0]);
            }
            batchLatency[i] = Math.max(1L, System.nanoTime() - batchStarted);
        }
        long elapsed = Math.max(1L, System.nanoTime() - started);
        Arrays.sort(batchLatency);
        int index = Math.max(0, (int) Math.ceil(0.99 * batches) - 1);
        return new Phase(batches, (long) batches * BLOCKS_PER_BATCH * BLOCK_SIZE,
                elapsed, batchLatency[index], totalChecksum);
    }

    private static long gcCount() {
        long sum = 0L;
        boolean anySupported = false;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionCount();
            if (value >= 0) {
                sum += value;
                anySupported = true;
            }
        }
        return anySupported ? sum : -1L;
    }

    private static double allocationRateMiBps(Phase phase) {
        return (phase.bytes / (double) MIB)
                / (phase.elapsedNanos / 1_000_000_000.0);
    }

    public static void main(String[] args) {
        int burstBatches = Integer.getInteger("demo.burstBatches", 2048);
        if (burstBatches < 1 || burstBatches > 8192) {
            throw new IllegalArgumentException("demo.burstBatches must be 1..8192");
        }

        final int baselineBatches = 128;
        final int recoveryBatches = 128;
        List<byte[]> retained = new ArrayList<>();
        for (int i = 0; i < 256; i++) {
            byte[] block = new byte[64 * KIB];
            block[0] = (byte) i;
            retained.add(block);
        }

        long gcBefore = gcCount();
        Phase baseline = runPhase(baselineBatches);
        Phase burst = runPhase(burstBatches);
        Phase recovery = runPhase(recoveryBatches);
        long gcAfter = gcCount();

        boolean samplesValid = baseline.p99BatchNanos > 0
                && burst.p99BatchNanos > 0 && recovery.p99BatchNanos > 0;
        boolean ratesPositive = allocationRateMiBps(baseline) > 0
                && allocationRateMiBps(burst) > 0
                && allocationRateMiBps(recovery) > 0;
        boolean gcMonotonicOrUnsupported = gcBefore < 0 || gcAfter < 0
                || gcAfter >= gcBefore;

        System.out.println("gcBeansPresent="
                + !ManagementFactory.getGarbageCollectorMXBeans().isEmpty());
        System.out.println("baselineAllocatedMiB=" + (baseline.bytes / MIB));
        System.out.println("burstAllocatedMiB=" + (burst.bytes / MIB));
        System.out.println("recoveryAllocatedMiB=" + (recovery.bytes / MIB));
        System.out.println("retainedPayloadMiB=" + (256L * 64 * KIB / MIB));
        System.out.println("allPhasesCompleted=true");
        System.out.println("postBurstOperationsSucceeded=" + (recovery.batches == recoveryBatches));
        System.out.println("p99SamplesMeasured=" + samplesValid);
        System.out.println("allocationRatesPositive=" + ratesPositive);
        System.out.println("gcCountMonotonicOrUnsupported=" + gcMonotonicOrUnsupported);
        System.out.println("checksum=" + (baseline.checksum + burst.checksum + recovery.checksum));

        if (Boolean.getBoolean("demo.showMetrics")) {
            System.out.printf(Locale.ROOT,
                    "observedRatesMiBps=%.1f,%.1f,%.1f%n",
                    allocationRateMiBps(baseline),
                    allocationRateMiBps(burst), allocationRateMiBps(recovery));
            System.out.printf(Locale.ROOT,
                    "observedP99BatchMs=%.3f,%.3f,%.3f%n",
                    baseline.p99BatchNanos / 1_000_000.0,
                    burst.p99BatchNanos / 1_000_000.0,
                    recovery.p99BatchNanos / 1_000_000.0);
            System.out.println("gcCountDelta="
                    + (gcBefore >= 0 && gcAfter >= 0 ? gcAfter - gcBefore
                            : "UNAVAILABLE"));
        }
        Reference.reachabilityFence(retained);
    }
}
```

### 9.2. Biên dịch và chạy

Lưu source dưới dạng UTF-8, ở thư mục chỉ dùng để thử nghiệm:

```bash
javac --release 17 -encoding UTF-8 GcOverloadRecoveryDemo.java
java -XX:+UseG1GC -Xms64m -Xmx256m -cp . GcOverloadRecoveryDemo
```

**Stdout chính xác đã kiểm chứng** trên **OpenJDK Zulu 24.0.2, HotSpot, Windows** với G1, ZGC và Shenandoah được chạy **riêng từng tiến trình**:

```text
gcBeansPresent=true
baselineAllocatedMiB=32
burstAllocatedMiB=512
recoveryAllocatedMiB=32
retainedPayloadMiB=16
allPhasesCompleted=true
postBurstOperationsSucceeded=true
p99SamplesMeasured=true
allocationRatesPositive=true
gcCountMonotonicOrUnsupported=true
checksum=2226176
```

**Quan trọng:** đây là **kết quả cụ thể của demo trong môi trường kiểm thử**, không phải cam kết rằng bất kỳ JVM/OS nào cũng có GC beans và đáp ứng mọi memory limit. Một hệ thống chạy không đúng VM hoặc thiếu memory có thể báo lỗi. Những giá trị như `gcBeansPresent=true` có thể không portable sang VM khác, và việc test còn chạy được **không chứng minh dịch vụ HTTP đã phục hồi về p99 SLO**.

### 9.3. Kết quả phần nào là bất biến?

- **`baselineAllocatedMiB=32`**: `128 × 8 × 32 KiB`.
- **`burstAllocatedMiB=512`**: `2048 × 8 × 32 KiB`.
- **`recoveryAllocatedMiB=32`**: cùng số batch với baseline.
- **`retainedPayloadMiB=16`**: `256 × 64 KiB` mảng được giữ trong `List`.
- **`checksum=2226176`**: cộng tất cả `Byte.toUnsignedInt(block[0])` do chương trình tự gán trong các vòng lặp.
- **`gcCountMonotonicOrUnsupported=true`**: đếm GC không giảm nếu có chỉ số được hỗ trợ, hoặc một mẫu không khả dụng trả `-1` được phân loại đúng. Nó **không** nói chắc GC đã chạy ít nhất một cycle.
- **`allPhasesCompleted=true`**: chỉ in sau khi các vòng lặp đã hoàn tất mà không có uncaught exception trong quá trình chạy; không thay thế health-check của ứng dụng.
- **`postBurstOperationsSucceeded=true`**: code vẫn hoàn thành **128 batch sau burst**, không phải bằng chứng latency đã phục hồi về SLO.

Đoạn code dùng `volatile` field `observable` để một object vừa cấp phát được publish, hạn chế việc JIT loại bỏ toàn bộ phép cấp phát không quan sát được. `Reference.reachabilityFence(retained)` đảm bảo danh sách retained vẫn được coi là reachable tới cuối bài test. Đây là mô hình nhân tạo, không phải mô hình giữ object của một dịch vụ thực.

### 9.4. Tại sao tổng cấp phát vượt `-Xmx` nhưng chương trình vẫn chạy?

Tổng **592 MiB payload qua thời gian** (gồm mảng giữ lại) khác với **592 MiB live cùng lúc**. Các mảng ngắn sống có thể được GC thu hồi rồi dùng lại không gian trong heap tối đa `256 MiB`. Một vài object khác, class metadata và object headers cũng chiếm bộ nhớ nhưng không nằm trong số payload byte-array được tính trong bài.

Không suy luận “JVM có thể dùng 592 MiB cùng lúc trong heap 256 MiB”, cũng không suy luận phải có tối thiểu bao nhiêu GC cycle dựa vào tổng bytes của chương trình. Collector, timing và heap policy quyết định thực tế.

## 10. Bật metric chi tiết: rate, p99 batch và GC count

Có thể chạy:

```bash
java -XX:+UseG1GC -Xms64m -Xmx256m -Ddemo.showMetrics=true -cp . GcOverloadRecoveryDemo
```

Ba dòng **bổ sung** sẽ có dạng:

```text
observedRatesMiBps=3612.0,9713.0,13192.6
observedP99BatchMs=0.062,0.077,0.022
gcCountDelta=12
```

**Đây chỉ là một lần đo đã quan sát trên máy thử**, không phải expected stdout cố định. Con số rate/p99/GC count có thể khác rất nhiều giữa các lần chạy, kể cả trên cùng máy, vì JIT, scheduler, CPU, GC activity, system load và platform. Không dùng ba con số mẫu đó làm threshold.

Dòng `observedRatesMiBps` lần lượt mô tả:

```text
baseline MiB/s, burst MiB/s, post-burst MiB/s
```

Chúng được tính bằng tổng **bytes được mã test chủ động tạo** chia cho thời gian wall-clock đo bằng `System.nanoTime()`. Đây **không phải lượng object toàn JVM tạo**, không phải GC reclaim rate và không phải công suất request/s.

Dòng `observedP99BatchMs` là percentile 99 của **thời gian cấp phát 8 mảng** trong từng phase. Đây **không phải HTTP request p99**; không có network, queue, serialization, downstream hoặc server thread pool. Nếu burst phase có p99 thấp hơn baseline ở một lần đo, điều đó có thể do JIT/warm-up và phương pháp sampling, **không** phải bằng chứng stress giúp ứng dụng nhanh hơn.

### Cách tính p99 trong demo

Với một tập `N` độ trễ batch, code sắp xếp giá trị tăng dần và lấy chỉ số:

```text
index = max(0, ceil(0.99 × N) - 1)
p99   = sortedLatency[index]
```

Đây là phương pháp **nearest-rank percentile** cho tập dữ liệu trong lab. Khi đo hệ thống thực, cần **đủ số mẫu** ở mỗi khoảng, quy định cách tính percentile nhất quán và phân biệt windowing, sampling, completion latency với offered-load latency.

### Vì sao không in p99 như một con số cố định?

Ngay cả khi payload và checksum không thay đổi, thời gian phân bổ object phụ thuộc GC/JIT/CPU, nên một “stdout exact” chứa p99 với ba số thực sẽ dễ sai. Bài chọn in **`p99SamplesMeasured=true`** cố định, còn giá trị p99 được cung cấp ở mode diagnostic **để người học tự quan sát**.

## 11. So sánh G1, ZGC và Shenandoah đúng cách

Java/HotSpot hỗ trợ nhiều collectors tùy phiên bản/runtime. Một thử nghiệm hợp lệ cần khởi động **JVM riêng cho từng collector**; không cố đổi GC bằng `System.setProperty` trong cùng process.

Trên **JDK đã xác minh có hỗ trợ các collector**:

```bash
java -XX:+UseG1GC -Xms64m -Xmx256m -Xlog:gc=info:file=g1-gc.log:uptime,level,tags -cp . GcOverloadRecoveryDemo
java -XX:+UseZGC -Xms64m -Xmx256m -Xlog:gc=info:file=zgc-gc.log:uptime,level,tags -cp . GcOverloadRecoveryDemo
java -XX:+UseShenandoahGC -Xms64m -Xmx256m -Xlog:gc=info:file=shenandoah-gc.log:uptime,level,tags -cp . GcOverloadRecoveryDemo
```

Trên **OpenJDK 24.0.2** thử nghiệm, cả **G1, ZGC và Shenandoah** đều biên dịch/chạy chương trình với **11 dòng stdout khớp** và tạo GC log. **Không** suy luận tất cả JDK vendors, platforms hoặc phiên bản đều hỗ trợ đủ ba options. Nếu một VM không có collector, JVM có thể từ chối khởi động; kết luận đúng là **UNSUPPORTED CONFIGURATION**, không phải “GC thua benchmark”.

### Những gì so sánh cần giữ công bằng

- Cùng JDK major/minor/vendor khi có thể; nếu khác, ghi rõ.
- Cùng `-Xmx`, `-Xms`, container memory/cpu limit và OS policies.
- Cùng traffic mix, arrival rate, duration, concurrency policy, warm-up.
- Cùng trạng thái cache/dataset và các hệ thống phụ thuộc.
- Chạy nhiều lần, đảo thứ tự thử nếu cần để giảm bias do thermal throttling/OS state.
- So **app latency/error/throughput, GC pauses, CPU, RSS, allocation stalls và recovery**; không so mỗi số GC cycles.

**Collector “tốt hơn” phải xét mục tiêu:** G1 có thể phù hợp với throughput và footprint của nhiều dịch vụ; ZGC và Shenandoah có thể cải thiện low-pause latency ở workload phù hợp nhưng concurrent work có trade-offs CPU/RAM. Một demo vài trăm MiB transient cấp phát không đủ để xếp hạng collectors.

**Phiên bản hiện hành:** từ JDK 24, ZGC chỉ còn generational mode; Shenandoah có lịch sử/chế độ generational riêng (JDK 25+). Không dùng các flags chuyển tiếp bị loại bỏ hoặc giả định hai collectors có lifecycle flags giống nhau. Bài này ưu tiên **các startup flags chuẩn đang được hỗ trợ** thay vì microtuning theo tài liệu rất cũ.

## 12. Tại sao phép đo tải phải tránh *coordinated omission*?

Khi load generator gửi request **chỉ sau khi request trước hoàn thành**, một hệ thống chậm lại sẽ tự động nhận ít request hơn. Nếu thống kê chỉ trên các request hoàn thành và bỏ qua khoảng thời gian khách hàng đáng lẽ gửi request, kết quả p99 có thể **trông tốt hơn** tình huống arrival rate thật.

Đây là vấn đề thường gọi là **coordinated omission**.

### 12.1. Closed-loop vs open-loop

- **Closed-loop:** mỗi client/virtual user gửi request tiếp khi request trước xong. Hữu ích để mô phỏng số người dùng cố định, nhưng offered load có thể tự giảm khi server chậm.
- **Open-loop/arrival-rate:** generator cố gắng phát request theo lịch đến xác định, không tự giảm offered load vì response chậm. Phù hợp khi muốn xác định service phản ứng ra sao với tải vào cố định, nhưng chính generator cũng cần đủ capacity.

Không có mô hình duy nhất đúng cho mọi sản phẩm. Nên chọn theo workload thật và **công bố rõ** loại generator; khi thử capacity/overload, đừng chỉ nhìn throughput hoàn thành mà quên **offered RPS**.

### 12.2. Có phải mọi latency thấp là đạt?

Không. Ví dụ:

```text
Offered load       : 2000 requests/s
Completed          : 800 requests/s
Rejected/Timed out : 1200 requests/s
p99 successful only: 25 ms
```

Nếu chỉ nhìn `p99 successful=25ms`, kết quả có vẻ tốt, nhưng **60% yêu cầu không hoàn thành thành công**. Cần một biểu đồ/đánh giá riêng cho **timeouts, rejections, backlog và deadline violations**. Định nghĩa SLO phải nói rõ request bị shed có được tính vào error budget hay là hành vi được phép dưới overload.

**Đừng bỏ các request timeout ra khỏi bộ đo của bài test chỉ vì chúng không có response latency hoàn chỉnh.** Ghi outcome và deadline; nếu dùng histogram latency, quy định cách báo cáo những request không hoàn tất.

## 13. Backpressure, bounded queues và load shedding là khả năng phục hồi

Một service có thể tránh OOME bằng cách **không giữ vô hạn dữ liệu chờ**. Các biện pháp hiện hành ở tầng ứng dụng:

- **Bounded thread/connection pools:** giới hạn số công việc chạy đồng thời; không mở thread tùy ý cho mỗi request.
- **Bounded queues:** giới hạn request/tasks đang chờ, tránh giữ hàng triệu DTO hoặc `CompletableFuture` rồi gây live-set growth.
- **Admission control:** từ chối có kiểm soát khi capacity đã đầy.
- **Backpressure:** downstream/client giảm tốc độ gửi hoặc chỉ cấp thêm khi có slot.
- **Timeout + deadline propagation:** request hết thời hạn không tiếp tục giữ object/resources vô ích.
- **Retry budget + jitter:** tránh “retry storm” khiến một service vừa hồi phục bị quá tải lại.
- **Circuit breaker:** khi downstream liên tục lỗi, ngừng đổ thêm request và thử hồi phục có kiểm soát.
- **Autoscaling:** có thể mở thêm capacity nhưng **không phải giải pháp tức thời** cho burst dưới vài giây; còn thời gian start/warm-up.

**Load shedding có thể là dấu hiệu hệ thống hoạt động đúng** dưới tải vượt công suất: vài request được từ chối nhanh, nhưng service giữ ổn định cho request được nhận và phục hồi nhanh khi tải trở lại bình thường.

Tuy nhiên, không tự coi `429`/`503` là “thành công”: báo cáo **rejection rate và error budget rõ ràng**, và kiểm tra hợp đồng API/client retry chính xác. Nếu một payment API bị timeout nhưng thực ra đã thực hiện giao dịch, retry không có idempotency key có thể tạo kết quả sai.

### Sơ đồ quyết định ở mức ứng dụng

```text
Request đến
     |
     +-- deadline đã hết? ---> trả timeout/reject theo contract
     |
     +-- có slot xử lý và queue dưới ngưỡng?
             |
             +-- có ---> nhận, xử lý, release slot trong finally
             |
             +-- không ---> reject nhanh / backpressure
                                      |
                                      v
                           theo dõi admitted/rejected
```

GC tuning không thể thay thế một hàng đợi vô hạn bằng phép màu. Khi live objects còn referenced trong queue, GC **không được** giải phóng chúng.

## 14. Đo khả năng phục hồi một cách kiểm chứng được

**Recovery** cần mốc thời gian và điều kiện rõ ràng:

```text
T0  bắt đầu tải baseline
T1  bắt đầu spike/stress
T2  kết thúc stress, offered load quay về baseline
T3  request p99/error/queue/healthy replicas đáp ứng điều kiện
    trong đủ N cửa sổ quan sát liên tiếp
Recovery time = T3 - T2
```

Đừng kết luận “phục hồi ngay ở T2” chỉ vì client ngừng phát thêm request. Hệ thống có thể còn backlog, pending retries, GC concurrent work, full GC, old objects chưa được giải phóng hoặc replicas đang restart.

### Ví dụ acceptance criteria có cấu trúc

Giả sử service công bố ở baseline:

```text
Mục tiêu minh họa (KHÔNG phải tiêu chuẩn chung):
  latency p99 <= 200 ms
  errors < 1% dưới tải được hỗ trợ
  queue depth <= 100
  ít nhất 2 replicas healthy
  recovery <= 120 s sau khi offered load trở về baseline
```

Để chống kết luận từ một vài mẫu may mắn, định nghĩa **cửa sổ 10 giây** và yêu cầu, chẳng hạn, **3 cửa sổ liên tiếp** thỏa các điều kiện. Khoảng thời gian và ngưỡng phải được tổ chức chấp nhận trước khi chạy. Không chỉ dùng một lần gọi health endpoint trả 200.

**Có thể cần recovery cấp nhiều tầng:**

1. **Application recovery:** tiếp nhận request mới, queue drained, circuit breaker đóng lại nếu phù hợp, không có hidden data corruption.
2. **GC/memory recovery:** không còn lỗi memory/GC liên tục, heap used/live ổn định theo tải mới và headroom đủ; không đòi heap committed/RSS phải trở về đúng giá trị trước đó ngay lập tức.
3. **Infrastructure recovery:** readiness, số replicas, restart count, memory throttling trở lại bình thường.
4. **Data recovery:** công việc đã nhận không bị mất/nhân đôi ngoài hợp đồng; retry và idempotency được kiểm thử.

**Heap committed không cần giảm về mức ban đầu để coi app phục hồi**: một số JVM giữ heap đã commit để tái sử dụng. Ngược lại, heap used thấp nhưng backlog vẫn tăng và error rate cao thì service **chưa** phục hồi.

## 15. Kiểm thử OOM và process death — cách làm an toàn

Bài demo **cố tình không gây `OutOfMemoryError`**. Thử OOM và failover là nhiệm vụ khác, có thể ảnh hưởng dữ liệu, file system, heap dump, pods và downstream.

Nếu mục tiêu yêu cầu thử **OOM handling / restart**:

- Chỉ thực hiện trong **một sandbox/staging riêng**, được phép tác động, với dữ liệu giả và resource limits.
- Có **process boundary**: nếu JVM chết, test harness bên ngoài ghi exit status, OOMKilled, restart count và health state. Code trong JVM vừa OOM **không phải** thành phần đáng tin duy nhất để báo “đã phục hồi”.
- Đặt memory/CPU quota rõ; kiểm tra các container khác không bị ảnh hưởng.
- Chỉ inject một failure mode tại một thời điểm để quan sát nguyên nhân.
- Kiểm tra readiness/liveness probes, replica replacement, backlog/idempotency và client behavior sau restart.
- Không tạo infinite allocation loop mà không có giới hạn chỉ để “xem bao giờ die”.
- Nếu dùng `-XX:+HeapDumpOnOutOfMemoryError`, heap dump có thể chứa thông tin nhạy cảm; cấu hình **đường dẫn, quota, quyền truy cập, retention** và không lưu cùng public logs.

**Khác biệt quan trọng:** `OutOfMemoryError: Java heap space` là lỗi JVM không đáp ứng cấp phát heap. **OOMKilled** do OS/container memory limit có thể dừng process mà không có Java exception hoặc hook cleanup. Chúng không phải cùng một tín hiệu, và cách giám sát/recovery khác nhau.

### Có nên `catch (OutOfMemoryError)` rồi tiếp tục service?

Không nên xem catch `OutOfMemoryError` là một chiến lược tổng quát để ứng dụng phục hồi an toàn: khi không đủ memory, logger, exception formatter, cache cleanup hay việc khởi tạo response cũng có thể thất bại. Một số hệ thống có thiết kế chuyên biệt có thể xử lý một trường hợp cụ thể, nhưng phải có hợp đồng được thử nghiệm; recovery cấp **process/orchestrator** thường cần được xem xét riêng.

**Không dùng `System.gc()` làm công cụ “cứu OOME” mặc định.** Lời gọi này là yêu cầu/đề nghị đối với JVM tùy collector/config, có thể gây tác động latency và không giải phóng object vẫn reachable.

## 16. Diễn giải GC log khi overload

Khi đã có GC logs và workload timeline, kiểm tra **đúng giai đoạn** thay vì chỉ quét keyword.

| Dấu hiệu | Ý nghĩa có thể | Bước điều tra |
|---|---|---|
| GC cycles tăng mạnh | Allocation pressure tăng hoặc heap headroom giảm | So allocation rate, live set, throughput cùng cửa sổ |
| Pause histogram có spike | GC/safepoint gây ngừng application | Correlate request p99, cpu/scheduling, phase của collector |
| `Pause Full` (G1) | Full GC có thể tốn nhiều thời gian | Tìm allocation failure, humongous, retained/old occupancy |
| ZGC allocation stalls | Concurrent GC không theo kịp allocation | Kiểm tra heap headroom, live set, rate, CPU |
| Shenandoah pacing | Mutators bị điều tiết để GC bắt kịp | Tách pacing delay khỏi stop-the-world pause |
| Shenandoah degenerated/full | Recovery collector tốn pause hơn | Kiểm tra reserve/free-set, allocation burst và fragmentation |
| Heap used tăng không trở lại | Có thể tăng retained set hoặc GC chưa chạy ở phase mong đợi | Dùng JFR/heap profiling, queue/cache instrumentation |
| GC CPU cao, app throughput giảm | CPU contention với concurrent GC hoặc overhead | So collector và CPU quota, phân bổ threads |
| Container RSS tăng liên tục | Heap + native/direct buffers/threads | Tách heap committed khỏi native memory và page cache |
| Có lỗi khi tắt tải | Có thể còn request in-flight hoặc leaked resources | Kiểm tra drain, deadline, cleanup, thread state |

Không suy luận một Full GC nhất thiết có nguyên nhân duy nhất là “heap quá nhỏ”. Có thể có memory leak, humongous fragmentation, explicit `System.gc()`, native pressure hoặc một heap policy đặc thù; dùng timestamps, logs và code profile để xác định.

**GC log không phải SLO:** ngay cả khi collector không hề có pause quá 1 ms, người dùng vẫn có thể thấy request timeout do queue/dependency. Hãy dùng cả metrics bên ngoài JVM.

## 17. Thí nghiệm đối chiếu với nhiều mức heap

Để thấy headroom ảnh hưởng GC như thế nào, chạy **ba JVM riêng**, giữ workload demo mặc định:

```bash
# Mức heap 128 MiB (có thể gây nhiều áp lực hơn)
java -XX:+UseG1GC -Xms64m -Xmx128m -Xlog:gc=info -cp . GcOverloadRecoveryDemo

# Mức heap 256 MiB của bài QA
java -XX:+UseG1GC -Xms64m -Xmx256m -Xlog:gc=info -cp . GcOverloadRecoveryDemo

# Mức heap 512 MiB để so thêm
java -XX:+UseG1GC -Xms64m -Xmx512m -Xlog:gc=info -cp . GcOverloadRecoveryDemo
```

**Các câu lệnh này chỉ dành cho môi trường lab**; không có bảo đảm GC count, p99 hay rate sẽ tăng/giảm theo một quan hệ tuyến tính. Khi tăng `-Xmx`, GC ergonomics có thể đổi kích thước young generation, heap regions hoặc ngưỡng GC, làm số chu kỳ biến động.

Một thí nghiệm đáng tin cần phân tích:

- `p99` theo nhiều lần chạy và số mẫu đủ lớn.
- Allocation rate có tương đương không; code có làm cùng lượng công việc không.
- Live set/retention có ổn định không; không bị warm-cache hoặc leak qua các lần.
- GC pause và CPU time; không so mỗi số cycles.
- Tổng RSS/native memory và container budget.
- Startup/JIT warm-up và noise từ OS.

**Không đánh đồng “heap lớn hơn” với “luôn phục hồi tốt hơn”**: heap lớn giúp có headroom hơn ở một số workload nhưng có thể tốn RAM, ảnh hưởng density/cost và thay đổi GC scheduling. Giải pháp bền vững có thể là giảm object churn, bounded queues hoặc sửa leak thay vì liên tục tăng heap.

## 18. Tạo test matrix cho CI và quy trình release

Một bộ kiểm tra tự động có thể phân làm **smoke**, **load test**, **stress test** và **chaos/failover**. Không phải mọi PR đều cần chạy phá hủy resource của một cluster.

| Cấp test | Chạy khi nào | Pass/fail nên dựa vào |
|---|---|---|
| **Unit/smoke trong JVM** | PR/CI thường xuyên | Bài demo compile, chạy đúng output invariants, không hang, exit code 0 |
| **Integration/GC config** | Build image hoặc đổi JDK/GC flags | Collector thực sự hỗ trợ, GC logs/JFR hoạt động, heap flags đúng |
| **Performance baseline** | Release định kỳ | p95/p99, throughput, error rate so với lịch sử/SLO trong môi trường chuẩn |
| **Stress/soak** | Release gate/định kỳ ngoài giờ | Saturation, GC stalls, queue bounds, ổn định khi tải cao |
| **Recovery test** | Release gate cho dịch vụ quan trọng | Đáp ứng SLO sau khi tải giảm trong deadline đã định |
| **Fault-injection/chaos** | Staging cô lập, có phê duyệt | Restart/failover, idempotency, backlog drain, không mất dữ liệu trái hợp đồng |

### 18.1. Kiểm thử smoke hữu ích

Đối với class mẫu, có thể xác minh:

- `javac --release 17` thành công.
- `java -XX:+UseG1GC -Xms64m -Xmx256m` trả exit code **0** trên HotSpot phù hợp.
- Kết quả 11 dòng trùng với mẫu được cung cấp **cho đúng cấu hình mặc định**.
- Có log `gc-stress.log` nếu đã bật `-Xlog`.
- Không cần hard-code `gcCountDelta>0` cho mọi VM/workload.
- Nếu dùng `-Ddemo.burstBatches` khác 2048, **giá trị burst và checksum có thể đổi**; không so với output mặc định.

### 18.2. Hướng kiểm tra overload ở mức dịch vụ

Một test harness chạy **ngoài process Java** nên ghi:

```text
test metadata:
  jdk, vendor, os, arch, heap flags, GC, pod CPU/memory limits
  load_generator + arrival rate schedule + request mix + concurrency
  app build version + dataset + dependency topology

time series:
  offered/s, completed/s, errors/s, rejects/s, timeouts/s
  request p50/p95/p99/p99.9 per window
  queue depth, in-flight, max queue age
  alloc MiB/s, GC pause histogram, stalls, cycles
  heap used/committed/max, process RSS, CPU throttling
  healthy replicas, restarts, OOMKilled, autoscaling events

conclusion:
  saturation threshold
  recovery T3-T2 và số windows hợp lệ
  SLO pass/fail + error budget
  root cause evidence (không chỉ suy đoán GC)
```

Đây là **schema gợi ý**, không phải định dạng chuẩn do Java tự xuất. Test harness phải tính percentile/response outcome đúng và không bỏ qua request đã timeout.

## 19. Những sai lầm thường gặp và cách tránh

| Sai lầm | Tại sao sai | Cách làm tốt hơn |
|---|---|---|
| Xem `java` exit 0 là “chịu được quá tải” | Chỉ một process lab nhỏ hoàn thành | Stress theo offered load và thu service metrics |
| Gọi tổng 512 MiB allocation là 512 MiB/s | Không đo thời gian | Dùng `bytes / seconds`, ghi rõ phạm vi đo |
| Coi 512 MiB transient là live set 512 MiB | Object có thể đã chết/được GC thu hồi | Theo dõi retention/heap occupancy |
| Chỉ xem average latency | Che p99/p99.9 spikes | Percentile/histogram với đủ mẫu |
| Bỏ request timeout khỏi thống kê | Tạo coordinated omission / báo cáo thiên lệch | Ghi offered, completed, timed-out và deadline |
| Đo chỉ request thành công | Dịch vụ reject 60% nhưng p99 “đẹp” | Tính error/rejection rate theo SLO |
| Chỉ xem GC cycle count | Nhiều cycle ngắn có thể ít gây hại hơn vài pause dài | Dùng GC pause histogram và app latency |
| Coi `GC MXBean collectionTime` là pause STW chuẩn | Semantics phụ thuộc collector/JVM | Dùng GC logs/JFR pause events |
| Kiểm thử soak quá ngắn | Memory leak có thể cần hàng giờ mới biểu hiện | Chạy đủ thời lượng, theo dõi live-set trend |
| Tăng concurrency mà không ghi actual RPS | Offered load không rõ và generator có thể nghẽn | Đo cả arrival rate và generator saturation |
| Chỉ hạ `-Xmx` rồi gọi là production stress | Khác production resource profile | Giữ tải, heap, CPU quota hợp lý và ghi rõ test objective |
| Tự động retry vô hạn khi server overload | Retry storm làm GC và queue trầm trọng hơn | Retry budget, exponential backoff + jitter |
| Dùng unbounded queue để “không bỏ request” | Live set tăng, OOM và latency vô hạn | Bounded queues và admission control |
| Gọi `System.gc()` để reset trước recovery | Thay đổi hành vi đo, không đảm bảo thu hồi object reachable | Đo recovery tự nhiên theo service protocol |
| Giả định ZGC/Shenandoah không thể bị stall | Concurrent collectors vẫn cần CPU/heap headroom | Theo dõi stalls, pacing, Full/Degenerated GC |
| Set `-Xmx` bằng container memory limit | Native memory vượt limit -> OOMKilled | Chừa native headroom và đo RSS |
| So collectors khi đổi hardware/dataset cùng lúc | Không phân biệt nguyên nhân | Chỉ đổi một yếu tố và chạy lặp |
| Thu heap dump/JFR không kiểm soát | Dump có thể chứa dữ liệu nhạy cảm | ACL, encryption, quota, retention |
| Để chaos test chạy vào production không phê duyệt | Có thể gây gián đoạn/dữ liệu sai | Test cô lập, tiêu chí dừng và rollback |
| Dùng mã giả lập này để tuyên bố dịch vụ đạt SLO | Demo không có network/request mix/backpressure | Load test end-to-end ngoài JVM |

## 20. Một quy trình điều tra khi p99 tăng lúc quá tải

Giả sử trong lúc tăng tải, p99 từ 80 ms lên 900 ms. Phân tích nên theo thứ tự:

1. **Xác nhận tải thực:** arrival rate, completion rate và request mix đã đổi như kế hoạch chưa?
2. **Xem queue/in-flight:** nếu queue age tăng trước p99, service có thể đang backlog.
3. **Xem CPU/quota:** CPU bị throttled có thể làm cả application và concurrent GC chậm.
4. **Xem allocation rate và live-set:** tăng object churn hay retained data?
5. **Xem GC logs/JFR:** có Full GC, evacuation failure, ZGC allocation stall hoặc Shenandoah pacing trùng thời điểm?
6. **Xem downstream metrics:** database/cache/network latency có tăng trước GC pressure không?
7. **Xem rejected/timeouts/retries:** có amplification làm tải còn cao hơn client gốc không?
8. **Khi trả tải về baseline:** đo thời gian backlog drain và p99/error ổn định, không đo một mẫu đơn.
9. **Kết luận:** đưa evidence về bottleneck, action (bounded queue, heap headroom, code allocation, CPU) và kiểm chứng lại trên cùng test.

Nếu nguyên nhân là queue giữ hàng triệu request đang chờ DB, thay `UseG1GC` bằng `UseZGC` có thể làm GC pauses ngắn hơn nhưng **không xóa được references trong queue**. Điều chỉnh backpressure/DB request timeout có thể hiệu quả hơn.

Nếu ngược lại GC log cho thấy Full GC hoặc allocation stalls khi free heap thấp và live set ổn định, cân nhắc **heap headroom hoặc giảm allocation churn** trước khi tinh chỉnh hàng loạt collector flags.

## 21. Checklist đầy đủ để tránh báo cáo QA sai

- [ ] Có **tài liệu test plan**: mục tiêu, workload, thời gian, SLO và recovery definition.
- [ ] Đã khóa JDK/vendor/collector/heap flags, CPU/RAM/OS/container image.
- [ ] Workload gồm short-lived allocations, live set và traffic mix phù hợp ứng dụng.
- [ ] Có warm-up, nhiều lần đo và cùng điều kiện so sánh.
- [ ] Đo offered load **và** completed throughput; không chỉ successful responses.
- [ ] Thu p95/p99 và cả errors/timeouts/rejections, tránh coordinated omission.
- [ ] GC metrics đủ: GC pauses, cycles, allocation rate, headroom, stalls và CPU.
- [ ] Thu queue depth, thread pool/connection pool, downstream latency và RSS.
- [ ] Test ramp/spike/sustained stress **đến ngưỡng được phê duyệt**, có điều kiện dừng.
- [ ] Không làm OOM/kill/cpu throttle trên môi trường dùng chung khi chưa được phép.
- [ ] Kiểm tra bounded queues, admission control, retries và idempotency.
- [ ] Sau khi giảm tải, đo **T3−T2** và xác nhận đủ cửa sổ liên tiếp đạt SLO.
- [ ] Không coi committed heap/RSS chưa giảm là tự động fail recovery.
- [ ] Không coi một request thành công hoặc exit code 0 là recovery đạt yêu cầu.
- [ ] Dùng JFR/GC logs và `jcmd` theo JDK mục tiêu; không hard-code log schema.
- [ ] Nếu cần failover, test ở **process/orchestrator boundary** và kiểm tra data consistency.
- [ ] Có kế hoạch rollback sau GC/JDK tuning thay đổi.
- [ ] Giới hạn log size, bảo vệ dữ liệu chẩn đoán và lưu lại metrics đủ để so sánh.

## 22. Kết luận

**Kiểm thử quá tải GC** là bài toán của cả **JVM, application, request scheduler và hệ thống vận hành**. Muốn hiểu giới hạn công suất phải đồng thời đo **allocation rate, live set, GC pauses/stalls, CPU, RSS, p99 latency, lỗi, backlog và throughput**. Muốn chứng minh **khả năng phục hồi** phải đo việc hệ thống trở về ngưỡng SLO sau khi tải giảm, cùng **thời gian recovery** và tính đúng đắn của dữ liệu, chứ không chỉ kiểm tra không có `OutOfMemoryError`.

Demo Java 17 trong bài tạo **baseline 32 MiB → burst 512 MiB → post-burst 32 MiB** với **16 MiB retained payload**, tính checksum và các sample latencies. Chương trình đã biên dịch và chạy trên **OpenJDK 24** với **G1, ZGC và Shenandoah** và cho **11 dòng stdout chính xác**. Nó là công cụ học tập và smoke test GC observations; **không phải chứng chỉ về hiệu năng, ngưỡng overload hay recovery SLO của một dịch vụ production**.

### Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — HotSpot Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/26/gctuning/index.html): collector selection, GC behavior và tuning.
- [Oracle Java SE 26 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html): Full GC, evacuation issues và cách đọc GC logs.
- [Oracle Java SE 26 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html): chẩn đoán bottleneck bằng JFR, không chỉ GC.
- [Oracle Java SE 26 — `jcmd` command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): `VM.flags`, `GC.heap_info`, `JFR.start`.
- [Oracle Java SE 26 — `java` command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): `-XX:+UseG1GC`, `-XX:+UseZGC`, `-XX:+UseShenandoahGC`, heap flags và `-Xlog`.
- [Oracle Java SE 26 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html), [`MemoryMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html): quan sát JVM qua API.
- [OpenJDK — JEP 271: Unified GC Logging](https://openjdk.org/jeps/271): unified logging được dùng từ các JDK hiện đại.
