# Chi phí CPU của công việc thu gom nền trong GC độ trễ thấp (Java 15+)

> **Chủ đề cha: GC độ trễ thấp.** Một garbage collector (GC) ưu tiên **pause ngắn** thường chuyển nhiều công việc thu gom sang các pha **concurrent**: thread GC chạy **đồng thời với các thread ứng dụng** (*mutators*). Phương pháp này giảm thời gian ứng dụng phải dừng để thu gom, nhưng không biến GC thành “miễn phí”: GC vẫn tiêu thụ **CPU-seconds, băng thông bộ nhớ/cache, tài nguyên heap và chi phí barriers trên mutator**. Khi CPU bị giới hạn bởi container/quota hoặc workload cấp phát rất nhanh, GC nền có thể tranh CPU với request threads, giảm throughput, tăng độ trễ đầu-cuối; nếu GC chạy không kịp còn có thể gây allocation stalls hoặc áp lực bộ nhớ.

Bài tập trung vào kiến thức **còn áp dụng cho JVM hiện đại**. Chúng ta phân tích **G1, ZGC và Shenandoah**, hiểu cơ chế trade-off, sử dụng JVM Unified Logging, Java Management API và JFR, rồi thực hành với các chương trình **Java 17+** biên dịch/chạy thực tế. Không dùng các GC flag đã bị gỡ ở JDK mới và không khẳng định một collector luôn nhanh hơn collector khác trong mọi ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **STW pause time**, **concurrent GC elapsed time**, **GC CPU time**, **total process CPU time**, **application throughput** và **request tail latency**.
2. Giải thích vì sao ít dừng JVM hơn thường đồng nghĩa phải dùng thêm CPU trong khi application vẫn chạy.
3. Nêu các nguồn chi phí của concurrent GC: marking, scanning, relocation/evacuation, remembered-set/refinement, read/write barriers, scheduling và memory bandwidth.
4. Hiểu sự đánh đổi khi tăng/giảm **concurrent GC worker threads**; vì sao “giảm thread để tiết kiệm CPU” có thể làm GC không theo kịp allocation rate.
5. Đọc đúng `-Xlog:gc*`, `-Xlog:gc+cpu`, `-XX:ConcGCThreads`, `-Xmx`, `-XX:SoftMaxHeapSize`, GC MXBeans và sự kiện JFR.
6. Đo **process CPU-seconds so với wall-clock** và biết rằng kết quả này **không tự tách CPU GC với CPU ứng dụng**.
7. Đối chiếu GC phases và CPU load bằng JFR mà **không lấy tổng wall-time pha concurrent làm GC CPU**.
8. Thiết kế một benchmark so sánh G1/ZGC/Shenandoah có kiểm soát CPU quota, heap, live set, allocation rate, warmup và tail latency.
9. Nhận diện các khuyến nghị/version hiện hành: ZGC từ **JDK 24 chỉ còn generational mode**, Shenandoah generational có trong **JDK 25 trên các bản dựng hỗ trợ**.
10. Đề xuất các bước tối ưu theo dữ liệu thay vì vô điều kiện giảm `ConcGCThreads` hoặc tăng `-Xmx`.

## 2. GC độ trễ thấp không đồng nghĩa CPU thấp

### 2.1. Hai cách bố trí công việc thu gom

Ví dụ khái niệm, **không phải biểu đồ thời gian của một collector cụ thể**:

~~~text
GC chủ yếu stop-the-world (minh họa):
Thời gian ------> 
Ứng dụng:  [ chạy ] [ DỪNG ] [ chạy ] [ DỪNG ] [ chạy ]
GC:                   [ GC ]              [ GC ]

GC có nhiều pha concurrent (minh họa):
Ứng dụng:  [ chạy ---- chạy ---- chạy ---- chạy ---- ]
GC nền:          [ mark ---- relocate ---- cleanup ]
STW:               [pause]            [pause]

Đích giảm: độ dài mỗi STW pause.
Giá phải trả: CPU/cache/memory bandwidth cùng được sử dụng
              khi ứng dụng cũng cần những tài nguyên đó.
~~~

GC phải xác định object nào còn reachable, quản lý việc di chuyển/tham chiếu nếu có, và thu hồi memory. Thay vì dồn phần lớn việc vào một khoảng dừng, collector concurrent phân bổ nhiều việc cho GC workers chạy trong nền. Tổng lượng công việc vẫn tồn tại và có thể tăng do tracking/barriers/coordination. **Thời gian dừng rất ngắn không chứng minh CPU tiêu tốn thấp.**

### 2.2. “Concurrent” không có nghĩa “CPU rảnh mới chạy”

GC thread là công việc thực thi trên CPU. Nếu một JVM bị giới hạn **2 effective CPU cores**, và tại thời điểm cao tải có:
- Application muốn dùng đủ 2 cores.
- Concurrent GC workers cũng đang cần CPU.
- JVM/JIT, kernel, logging và các thread khác có chi phí.

Thì OS scheduler phải chia thời gian CPU giữa các tác vụ. Kết quả có thể là:
- CPU utilization ở gần quota.
- Request threads ít CPU hơn -> throughput giảm hoặc p95/p99 latency tăng.
- GC hoàn tất nhanh hơn nếu cấp thêm worker CPU, nhưng phần này cạnh tranh với mutator.
- Nếu **không cấp đủ CPU cho GC**, garbage có thể tích lũy, heap headroom giảm và application bị chờ tại allocation slow path.

Vì thế câu “concurrent GC chỉ dùng CPU idle, không ảnh hưởng application” là **sai**. Heuristics có thể điều chỉnh GC workers tùy tình hình nhưng không loại bỏ chi phí tài nguyên.

### 2.3. Các mục tiêu hiệu năng khác nhau

| Chỉ số | Câu hỏi | Có được suy ra từ GC pause thấp không? |
| --- | --- | --- |
| **STW pause** | Mỗi lần dừng mutators trong GC bao lâu? | Đây là chính chỉ số pause, nhưng không phải toàn bộ latency |
| **Concurrent cycle elapsed time** | Một pha concurrent kéo dài bao lâu theo đồng hồ? | Không phải thời gian CPU của GC |
| **GC worker CPU time** | Các native GC threads thực sự dùng bao nhiêu CPU-seconds? | **Không**, cần đo attribution phù hợp |
| **Mutator barrier overhead** | Read/write/reference barriers làm application chậm bao nhiêu? | **Không**, chi phí xuất hiện ngay trên mutator |
| **Process CPU time** | Tất cả threads trong JVM dùng bao nhiêu CPU? | **Không** tự phân loại GC vs application |
| **Throughput** | Bao nhiêu requests/events xử lý mỗi giây? | **Không**; pause giảm có thể đi cùng throughput giảm |
| **Request tail latency** | p95/p99/p99.9 end-to-end của requests? | **Không**; CPU contention vẫn làm requests chậm |
| **Allocation stall** | Thread cấp phát có phải chờ GC giải phóng heap? | Không thể kết luận chỉ từ average pause |
| **Headroom / memory footprint** | Bao nhiêu heap trống có thể cấp phát trong khi GC chạy? | Không thể kết luận chỉ từ pause |
| **CPU throttling** | Process/container bị quota giới hạn bao nhiêu? | Không; cần cgroup/OS metrics |

**Độ trễ của request** còn chịu ảnh hưởng từ xử lý nghiệp vụ, lock, scheduling, I/O, network, CPU quota, page faults, JIT warmup. Không được coi một biểu đồ GC pause đẹp là bằng chứng trực tiếp mọi API đều đáp ứng SLO.

## 3. CPU được dùng ở đâu trong GC concurrent?

### 3.1. Concurrent marking và scanning

Để tìm object còn sống, GC phải đi qua object graph:
1. Xác định roots/điểm bắt đầu có thể reachable.
2. Quét references để đánh dấu object reachable.
3. Xử lý việc mutators tiếp tục thay đổi graph trong khi GC đang chạy.
4. Chuẩn bị vùng có thể thu hồi và cập nhật metadata cần thiết.

Khi graph lớn và nhiều references, marking/scanning có thể dùng đáng kể CPU/cache bandwidth. **Tổng heap lớn không luôn kéo theo nhiều CPU:** Live set, object graph, allocation rate, fragmentation và pattern truy cập có thể quyết định chi phí quan trọng hơn dung lượng heap tối đa.

### 3.2. Relocation / evacuation concurrent

Collector như ZGC và Shenandoah có các cơ chế di chuyển/giải phóng object nhằm giảm pause. Di chuyển dữ liệu có thể tốn:
- CPU cycles cho copy object và xử lý metadata.
- Memory bandwidth cho đọc/ghi vùng nhớ.
- Cache misses, TLB effects, page faults hoặc NUMA traffic.
- Barriers/điều phối để mutators tham chiếu tới object đúng.

Ngay khi GC workers được chạy trên core “khác”, chúng vẫn có thể tranh **memory bandwidth hoặc shared caches** với application. Vì vậy CPU của mutator nhìn có vẻ chưa 100% nhưng throughput vẫn có thể giảm.

### 3.3. Barriers trên application threads

Một số collector dùng **read barriers, write barriers, load/store barriers, remembered sets, card marking** để tracking object graph trong khi application tiếp tục chạy. Các phép này thường có đường tối ưu nhanh, nhưng chúng:
- Thêm instruction/nhánh hoặc truy cập metadata vào đường chạy mutator.
- Có thể gây cache traffic và tương tác với memory fences/atomic operations.
- Có chi phí phụ thuộc workload: object churn, pointer updates, reference-heavy algorithms.

**Đây là chi phí GC nhưng có thể được tính vào CPU của chính application thread.** Vì vậy ngay cả khi lấy được tổng CPU của native GC worker threads, con số đó vẫn **không bao gồm toàn bộ GC overhead**.

### 3.4. Coordination, scheduling và background services

Còn có chi phí để:
- Bắt đầu/kết thúc chu kỳ GC, handshakes/safepoints ngắn.
- Phân phối việc giữa worker threads.
- Concurrent refinement, reference processing, cleanup, heap management.
- Xử lý lệnh allocation khi thiếu heap trống, thu gom gấp hoặc chờ khôi phục capacity.
- Lập lịch CPU khi runnable threads vượt tài nguyên thực tế.

Không phải mọi pha GC đều concurrent; collector vẫn có một số pause. Ngược lại, tổng thời gian concurrent dài **không đồng nghĩa application bị pause dài bằng đó**.

## 4. Bức tranh collector hiện đại

### 4.1. G1: cân bằng độ trễ và throughput

G1 là lựa chọn **mặc định của HotSpot server-class** trong nhiều cấu hình, thực hiện phần việc song song trong **stop-the-world pauses** và phần việc **concurrent** (đặc biệt marking và remembered-set refinement). Oracle mô tả G1 nhắm tới cân bằng pause tương đối ngắn, throughput tốt và không cần tuning quá phức tạp.

- **Ưu điểm thường gặp:** Throughput tốt với pause goal phù hợp; generational collector có các heuristics.
- **Chi phí nền:** Concurrent marking/refinement chạy cùng ứng dụng.
- **Chi phí pause:** Young/mixed collection vẫn có stop-the-world phases.
- **Hệ quả:** Giảm phần CPU concurrent không có nghĩa tổng chi phí biến mất: một số việc có thể chuyển vào pause, làm pause dài hơn.
- **`-XX:MaxGCPauseMillis`:** Là **mục tiêu/heuristic**, không phải cam kết hard real-time.

G1 thích hợp khi SLO cho phép pause nhất định và cân bằng throughput/tài nguyên quan trọng hơn việc cực tiểu hóa mọi pause. Không kết luận G1 kém ZGC/Shenandoah trong mọi workload.

### 4.2. ZGC: GC độ trễ thấp với nhiều việc concurrent

ZGC được thiết kế cho **pause rất ngắn** và cho phép các pha tốn công diễn ra đồng thời với ứng dụng; chi phí là CPU, memory bandwidth, barriers và heap headroom. Oracle GC tuning guide khuyên chú ý:
- **`-Xmx`:** Heap phải chứa live set **cộng không gian dự phòng để ứng dụng tiếp tục cấp phát trong lúc GC làm việc**.
- **`-XX:ConcGCThreads`:** JVM có heuristics chọn số concurrent GC workers; đặt quá cao có thể cạnh tranh CPU với app, quá thấp khiến GC không bắt kịp allocation rate.
- **`-XX:SoftMaxHeapSize`:** Ngưỡng heap **mềm** cho ZGC; được phép vượt tới `-Xmx` để hạn chế application stalls.
- ZGC có adaptive heuristics và cơ chế thu hồi bộ nhớ không dùng; quan sát CPU và latency khi điều chỉnh memory policy.

**Lưu ý phiên bản cực kỳ quan trọng:** Từ **JDK 24**, ZGC chỉ còn **generational**; **non-generational ZGC mode đã bị gỡ** (JEP 490). Vì vậy **không** khuyến nghị dùng `-XX:+ZGenerational` hoặc `-XX:-ZGenerational` trên JDK 24+; các hướng dẫn đó đã lỗi thời. Chọn ZGC bằng:

~~~bash
java -XX:+UseZGC -Xms128m -Xmx256m -version
~~~

Ở JDK15, ZGC trở thành production feature theo JEP 377; các phiên bản sau tiếp tục phát triển. Khi đọc bài về Java 15, cần phân biệt **mốc xuất hiện tính năng** và **hành vi của JDK hiện đại đang triển khai**.

### 4.3. Shenandoah: concurrent GC và tính khả dụng theo bản dựng

Shenandoah cũng dùng công việc concurrent để giảm các lần dừng dài. Cần xem build/JDK/vendor:
- JEP 379 đưa Shenandoah vào trạng thái production trong **JDK 15**.
- **Generational Shenandoah** là tính năng hoàn thiện trong **JDK 25 (JEP 521)** khi build hỗ trợ, có thể chọn `-XX:ShenandoahGCMode=generational`.
- Chế độ mặc định của Shenandoah trong JDK25 có thể vẫn khác generational, và không phải mọi bản phân phối Java đều tích hợp Shenandoah. Không tuyên bố nó luôn có hoặc luôn mặc định generational.
- Phải kiểm tra JVM options/GC initialization log và chạy benchmark cùng workload trước khi quyết định.

Ví dụ **chỉ dùng ở JDK 25+ có Shenandoah generational support**, không phải Java17 thuần trên mọi vendor:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -version
~~~

Nếu báo **Unrecognized VM option** hoặc collector không có, đây là giới hạn phiên bản/build. Không ép JVM chạy flags nó không hỗ trợ.

### 4.4. So sánh theo chi phí CPU, không phải tên gọi

| Collector | Work concurrent đặc trưng | Pause | Chi phí CPU cần chú ý |
| --- | --- | --- | --- |
| **G1** | Marking, refinement và nhiều công việc bổ trợ concurrent | Vẫn có young/mixed STW pauses | Concurrent marking/refinement + STW workers; trade-off pause/throughput |
| **ZGC (JDK24+)** | Generational marking, relocation/thu hồi concurrent | Thiết kế ưu tiên pause ngắn | Workers/barriers + headroom; thiếu CPU có thể dẫn đến allocation stalls |
| **Shenandoah** | Concurrent marking/evacuation/updates theo mode | Thiết kế ưu tiên pause ngắn | Workers/barriers/pacing; generational mode (JDK25+) có profile khác mode truyền thống |

**Không thể rút ra từ bảng rằng ZGC luôn “tốn X% CPU hơn G1”.** Tùy JDK, cấu hình, OS, CPU quota, allocation rate, live set, generational mix, payload, cùng một collector có thể thắng ở một thước đo và thua ở thước đo khác.

## 5. Định lượng CPU và CPU budget cho công việc GC

### 5.1. Wall-clock time và CPU time

Giả sử quan sát trong một cửa sổ **2 giây** trên máy/quota cho ứng dụng tương đương **4 cores**:
- Dung lượng CPU tối đa lý thuyết: `4 × 2 = 8 core-seconds`.
- Mutators thực thi `5.0 CPU-seconds`.
- GC native workers thực thi `1.8 CPU-seconds`.
- Runtime/OS threads khác trong process thực thi `0.4 CPU-seconds`.
- Tổng CPU của process: `7.2 CPU-seconds`.

Đây là **số liệu giả định để học cách tính**, không phải kết quả đo thật của một ứng dụng. Khi phân tích CPU thực tế cần có profiler phân loại thread roles và kiểm soát quota.

~~~text
Effective CPU cores: 4
Measurement wall-time: 2 s
Capacity: 4 × 2 = 8 CPU-seconds

Application work:   5.0 CPU-seconds
GC worker work:     1.8 CPU-seconds
Other process work: 0.4 CPU-seconds
                   ----------------
Process total:      7.2 CPU-seconds

Average process cores used = 7.2 / 2 = 3.6 cores
Process CPU / capacity      = 7.2 / 8 = 90.0%
GC CPU / capacity           = 1.8 / 8 = 22.5%
GC CPU / process CPU        = 1.8 / 7.2 = 25.0%
~~~

**Chú ý mẫu số:** “GC dùng 25% process CPU” và “GC chiếm 22.5% dung lượng CPU đã cấp” là hai chỉ số khác nhau. Nếu benchmark báo “CPU tăng 20%” mà không nêu CPU-seconds, số cores/quota và khoảng thời gian, rất dễ diễn giải sai.

### 5.2. Ví dụ Java 17+ số học CPU budget

**Tệp `GcCpuBudgetExample.java` — độc lập:**

~~~java
import java.util.Locale;

public class GcCpuBudgetExample {
    public static void main(String[] args) {
        double effectiveCpuCores = 4.0;
        double wallSeconds = 2.0;
        double appCpuSeconds = 5.0;
        double gcWorkerCpuSeconds = 1.8;
        double otherCpuSeconds = 0.4;

        double capacity = effectiveCpuCores * wallSeconds;
        double processCpu = appCpuSeconds
                + gcWorkerCpuSeconds + otherCpuSeconds;

        System.out.printf(Locale.ROOT,
                "capacityCoreSeconds=%.1f%n", capacity);
        System.out.printf(Locale.ROOT,
                "processCpuSeconds=%.1f%n", processCpu);
        System.out.printf(Locale.ROOT,
                "avgProcessCores=%.1f%n",
                processCpu / wallSeconds);
        System.out.printf(Locale.ROOT,
                "processCpuOfCapacityPct=%.1f%%%n",
                100.0 * processCpu / capacity);
        System.out.printf(Locale.ROOT,
                "gcOfCapacityPct=%.1f%%%n",
                100.0 * gcWorkerCpuSeconds / capacity);
        System.out.printf(Locale.ROOT,
                "gcOfProcessCpuPct=%.1f%%%n",
                100.0 * gcWorkerCpuSeconds / processCpu);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 GcCpuBudgetExample.java
java GcCpuBudgetExample
~~~

Stdout **chính xác**:

~~~text
capacityCoreSeconds=8.0
processCpuSeconds=7.2
avgProcessCores=3.6
processCpuOfCapacityPct=90.0%
gcOfCapacityPct=22.5%
gcOfProcessCpuPct=25.0%
~~~

### 5.3. Tại sao con số GC CPU khó lấy?

Một OS/process CPU counter tổng hợp sẽ đếm CPU của application + GC + JIT + runtime khác. Muốn ước lượng **GC worker CPU** cần theo dõi native threads/CPU profiler hoặc instrumentation phù hợp. Tuy nhiên **mutator barrier overhead nằm trong thread ứng dụng**, không dễ tách bằng cách cộng CPU của các thread có tên chứa `GC`.

**Không dùng `ThreadMXBean.getThreadCpuTime()` làm phép đo đầy đủ GC CPU**: API này chủ yếu quan sát các Java platform threads, còn HotSpot có native GC worker threads không được biểu diễn đầy đủ như Java threads bình thường. Tên GC threads cũng là chi tiết implementation, không phải API ổn định.

### 5.4. Hai rủi ro về phần trăm CPU

**Rủi ro 1 — Process CPU nhiều hơn elapsed time.** Nếu process dùng trung bình 3 cores trong một giây, `processCpuTimeDelta=3s` trong khi `wall=1s` là bình thường. Không được kết luận số đo “sai” vì CPU seconds lớn hơn elapsed seconds.

**Rủi ro 2 — Container quota khác host cores.** Một container bị giới hạn 2 cores trên host 32 cores có thể hiển thị:
- JVM process CPU time cao so với wall-clock.
- Host overall CPU utilization thấp vì host còn nhiều CPU.
- Container đã bị CPU throttling và request latency tăng.

Do đó **host CPU % thấp không chứng minh JVM đủ CPU**. Hãy đối chiếu effective CPU quota/period, cgroup throttling, node pressure, vCPU steal và `Runtime.availableProcessors()` dưới đúng môi trường.

## 6. Ví dụ thực tế 1 — Đo process CPU, wall time và GC activity với Java 17+

Ta tạo workload cấp phát tổng cộng **1,536 MiB** các `byte[]`, giữ tối đa **1,024 blocks × 64 KiB ≈ 64 MiB` trong một ring buffer. Mục tiêu không phải chứng minh collector nào tốt hơn, mà tạo GC pressure có lặp lại để đối chiếu:

- **Process CPU time** qua `com.sun.management.OperatingSystemMXBean.getProcessCpuTime()` — tổng CPU của process, gồm GC + mutators + runtime.
- **Wall time** qua `System.nanoTime()`.
- **GC events và reported collection time** qua `GarbageCollectorMXBean` — counters phụ thuộc collector/implementation; **không phải GC worker CPU**.
- **GC phases và pauses** bằng Unified Logging chạy cùng chương trình.

`com.sun.management.OperatingSystemMXBean` là API quản lý mở rộng được các JDK/HotSpot phổ biến cung cấp qua module `jdk.management`, phù hợp bài thực hành Java 17+. Với JVM khác hoặc OS counter không khả dụng, cần kiểm tra hỗ trợ; không xem extension API là chuẩn Java SE có mặt trên mọi runtime tối giản.

### 6.1. Mã hoàn chỉnh — `ConcurrentGcCpuProbe.java`

~~~java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;
import java.util.Locale;

public class ConcurrentGcCpuProbe {
    static long count(List<GarbageCollectorMXBean> beans) {
        long total = 0;
        for (GarbageCollectorMXBean bean : beans) {
            long n = bean.getCollectionCount();
            if (n >= 0) total += n;
        }
        return total;
    }

    static long timeMs(List<GarbageCollectorMXBean> beans) {
        long total = 0;
        for (GarbageCollectorMXBean bean : beans) {
            long n = bean.getCollectionTime();
            if (n >= 0) total += n;
        }
        return total;
    }

    public static void main(String[] args) {
        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();
        OperatingSystemMXBean os = (OperatingSystemMXBean)
                ManagementFactory.getOperatingSystemMXBean();

        long beforeCounts = count(beans);
        long beforeTimes = timeMs(beans);
        long wallBefore = System.nanoTime();
        long cpuBefore = os.getProcessCpuTime();

        final int blockBytes = 64 * 1024;
        final int iterations = 24_576;
        byte[][] retained = new byte[1_024][];
        long fingerprint = 0;

        for (int i = 0; i < iterations; i++) {
            byte[] b = new byte[blockBytes];
            b[0] = (byte) (i & 255);
            b[blockBytes - 1] = (byte) (i >>> 8);
            retained[i & (retained.length - 1)] = b;
            fingerprint += b[0];
        }
        for (byte[] b : retained) {
            fingerprint += b[blockBytes - 1];
        }

        long cpuDelta = os.getProcessCpuTime() - cpuBefore;
        long wallDelta = System.nanoTime() - wallBefore;
        long gcCountDelta = count(beans) - beforeCounts;
        long gcTimeDelta = timeMs(beans) - beforeTimes;
        double avgCores = cpuDelta / (double) wallDelta;

        System.out.println("allocatedMiB=" +
                ((long) iterations * blockBytes / 1024 / 1024));
        System.out.println("retainedSlots=" + retained.length);
        System.out.println("gcNames=" + beans.stream()
                .map(GarbageCollectorMXBean::getName).toList());
        System.out.println("gcEventCountDelta=" + gcCountDelta);
        System.out.println("gcReportedTimeMsDelta=" + gcTimeDelta);
        System.out.printf(Locale.ROOT, "wallSeconds=%.3f%n",
                wallDelta / 1e9);
        System.out.printf(Locale.ROOT,
                "processCpuSeconds=%.3f%n", cpuDelta / 1e9);
        System.out.printf(Locale.ROOT, "avgProcessCores=%.2f%n",
                avgCores);
        System.out.println("fingerprint=" + fingerprint);
    }
}
~~~

**Chạy với JDK 17+ / HotSpot**, từ thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 ConcurrentGcCpuProbe.java

# G1: log GC phases và pauses vào file riêng
java -XX:+UseG1GC -Xms128m -Xmx256m \
  -XX:ActiveProcessorCount=2 \
  -Xlog:gc*=info:file=g1-gc.log:uptime,level,tags \
  ConcurrentGcCpuProbe

# ZGC (trên JDK 24+ là generational)
java -XX:+UseZGC -Xms128m -Xmx256m \
  -XX:ActiveProcessorCount=2 \
  -Xlog:gc*=info:file=zgc-gc.log:uptime,level,tags \
  ConcurrentGcCpuProbe
~~~

Trong PowerShell, đặt mỗi lệnh `java` trên **một dòng**, hoặc dùng ký tự continuation `\u0060` của PowerShell; dấu `\` ở ví dụ là line continuation dành cho shell Unix/Bash.

**Ví dụ một lần chạy thực tế trên JDK 24, Windows, `ActiveProcessorCount=2`:**

~~~text
G1:
allocatedMiB=1536
retainedSlots=1024
gcNames=[G1 Young Generation, G1 Concurrent GC, G1 Old Generation]
gcEventCountDelta=106
gcReportedTimeMsDelta=365
wallSeconds=0.484
processCpuSeconds=0.922
avgProcessCores=1.90
fingerprint=83456

ZGC:
allocatedMiB=1536
retainedSlots=1024
gcNames=[ZGC Minor Cycles, ZGC Minor Pauses, ZGC Major Cycles, ZGC Major Pauses]
gcEventCountDelta=52
gcReportedTimeMsDelta=398
wallSeconds=0.355
processCpuSeconds=0.531
avgProcessCores=1.50
fingerprint=83456
~~~

**Đây là hai samples ngắn riêng rẽ, không phải kết luận ZGC luôn nhanh hơn G1.** Chúng có startup, JVM warmup, logging overhead, collector-specific MXBean definitions và ảnh hưởng từ hệ thống. Trong benchmark thực, cần nhiều lần lặp và statistical analysis.

### 6.2. Giải thích số liệu, không diễn giải quá mức

- `allocatedMiB=1536` là **tổng bytes do loop tạo ra**; không phải heap live 1,536 MiB. Các blocks cũ của ring bị ghi đè và có thể thu gom.
- `retainedSlots=1024` là số slot; tối đa xấp xỉ 64 MiB payload còn được ring giữ. Object headers, array refs và runtime metadata tạo thêm overhead.
- `gcNames` liệt kê MXBeans hiện có. **Số lượng và tên beans phụ thuộc collector/JDK**.
- `gcEventCountDelta` là tổng giá trị collection-count mà những beans cung cấp. **Không so G1 count=106 với ZGC count=52 như cùng loại sự kiện**; collector có các beans/semantics khác nhau và có thể double-count một số activity theo cách tổ chức.
- `gcReportedTimeMsDelta` là phần tăng trong thời gian mà MXBeans báo cáo. Với một số collector, đây có thể là pause/cycle metrics có semantics riêng; **không phải tổng CPU của GC workers** và không nhất thiết là tổng STW pause.
- `wallSeconds` đo thời gian đồng hồ của loop, `processCpuSeconds` đo CPU toàn process trong cùng khoảng; `avgProcessCores` là tỉ số đó.
- `avgProcessCores=1.90` không nghĩa 1.90 cores chỉ cho GC; đó là **tổng** mutators+GC+JIT+runtime.
- `fingerprint=83456` là kết quả tính toán của workload, giúp kiểm tra chương trình thực sự sử dụng dữ liệu thay vì bỏ hết.
- `-XX:ActiveProcessorCount=2` điều chỉnh số processors JVM nhìn thấy để thử ergonomics; **không tự áp đặt cgroup CPU quota/cpuset thực trên OS**.

**Nếu muốn tính phần trăm GC CPU:** Cần profiler/native-thread CPU accounting thích hợp (cùng cảnh báo barrier overhead), không lấy `gcReportedTimeMsDelta / wallSeconds` làm GC utilization.

### 6.3. Đọc log G1 và ZGC

Với `-Xlog:gc*=info`, log G1 có thể chứa:

~~~text
[...][info][gc          ] GC(4) Concurrent Mark Cycle
[...][info][gc,marking  ] GC(4) Concurrent Scan Root Regions ...
[...][info][gc,cpu      ] GC(3) User=0.00s Sys=0.00s Real=0.00s
~~~

Log ZGC có thể chứa:

~~~text
[...][info][gc,phases] GC(0) Y: Concurrent Mark ...
[...][info][gc,phases] GC(0) Y: Concurrent Relocate ...
[...][info][gc,alloc ] GC(0) Y: Allocation Stalls: ...
~~~

Đó là các **mẫu rút gọn**, ký hiệu `...` chỉ các trường/timestamp có thể thay đổi theo runtime. Trong log thật, hãy ghép `GC(id)` và timestamp để phân biệt cycles và phases.

**Đặc biệt:** G1 `User/Sys/Real` trong dòng `[gc,cpu]` thường mô tả CPU/wall cho một công đoạn/pause được báo cáo; **không thay thế phép đo tổng native GC CPU concurrent trên toàn bộ workload**. Tương tự, `Concurrent Mark 2.0ms` của ZGC là **thời lượng pha**, không tự nói “GC đã dùng 2.0 CPU-ms”.

### 6.4. Giới hạn của microbenchmark

Ví dụ cố tình tạo allocation pressure nhanh hơn đa số service trong vài trăm mili-giây. Nó giúp trình diễn **công cụ đo**, không thể dùng để lựa chọn collector production vì:
- JVM JIT chưa warm đủ.
- Workload đơn giản, không có IO/request mix.
- Thời gian quá ngắn để tách tác động của OS scheduling.
- Khi chạy các collector theo thứ tự, môi trường nền có thể khác.
- Heap `256 MiB` không đại diện cho live set GB thực.
- `ActiveProcessorCount` là hint về processor ergonomics, không tái hiện chính xác container throttling.
- Không đo p99 latency của requests hay tail degradation.

Đừng viết báo cáo “ZGC tốt hơn G1 26.7%” chỉ từ hai dòng `wallSeconds` ví dụ.

## 7. Ví dụ thực tế 2 — JFR ghi concurrent phases và CPU load

JDK Flight Recorder (JFR) cho phép theo dõi sự kiện máy ảo theo cửa sổ thời gian. Ví dụ dùng các event:

| Event JFR | Quan sát | Giới hạn |
| --- | --- | --- |
| `jdk.GCPhaseConcurrent` | Tên pha GC concurrent, GC ID, **elapsed duration** | Duration không phải GC worker CPU time |
| `jdk.GarbageCollection` | Một sự kiện thu gom GC theo JFR | Không phải cùng định nghĩa với mọi MXBean collection count |
| `jdk.CPULoad` | Tỉ lệ `jvmUser`, `jvmSystem`, `machineTotal` được sample | Là overall load, **không** phân loại GC vs mutator |
| `jdk.GCPhasePause` | Khi có/được bật: pause phases | Chỉ về pause, không đo toàn bộ GC overhead |

JFR có chi phí đo nhỏ nhưng không phải 0; độ phân giải sampling và event availability phụ thuộc JDK/provider. Bài thực hành bật các sự kiện cụ thể trước khi chạy workload, không giả định default recording đã bật chúng.

### 7.1. Mã hoàn chỉnh — `GcConcurrentJfrProbe.java`

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class GcConcurrentJfrProbe {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile(
                "gc-concurrent-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.enable("jdk.CPULoad")
                        .withPeriod(Duration.ofMillis(100));
                recording.enable("jdk.GCPhaseConcurrent")
                        .withThreshold(Duration.ZERO);
                recording.enable("jdk.GarbageCollection");
                recording.start();

                byte[][] live = new byte[512][];
                for (int i = 0; i < 12_288; i++) {
                    byte[] block = new byte[64 * 1024];
                    block[0] = 1;
                    live[i % live.length] = block;
                }
                Thread.sleep(1_600);

                recording.stop();
                recording.dump(file);
            }

            long concurrentEvents = 0;
            long phaseDurationMs = 0;
            long gcEvents = 0;
            long samples = 0;
            double sumJvm = 0.0;
            double sumMachine = 0.0;
            Set<String> phaseNames = new HashSet<>();

            for (RecordedEvent event :
                    RecordingFile.readAllEvents(file)) {
                switch (event.getEventType().getName()) {
                    case "jdk.GCPhaseConcurrent" -> {
                        concurrentEvents++;
                        phaseDurationMs +=
                                event.getDuration().toMillis();
                        phaseNames.add(event.getString("name"));
                    }
                    case "jdk.GarbageCollection" -> gcEvents++;
                    case "jdk.CPULoad" -> {
                        samples++;
                        sumJvm += event.getFloat("jvmUser")
                                + event.getFloat("jvmSystem");
                        sumMachine += event.getFloat("machineTotal");
                    }
                    default -> { }
                }
            }

            System.out.println("gcEvents=" + gcEvents);
            System.out.println("concurrentPhaseEvents=" +
                    concurrentEvents);
            System.out.println("distinctConcurrentPhases=" +
                    phaseNames.size());
            System.out.println("concurrentPhaseDurationMsSum=" +
                    phaseDurationMs);
            System.out.println("cpuLoadSamples=" + samples);

            if (samples > 0) {
                System.out.printf(Locale.ROOT,
                        "avgJvmLoadPct=%.2f%n",
                        100.0 * sumJvm / samples);
                System.out.printf(Locale.ROOT,
                        "avgMachineLoadPct=%.2f%n",
                        100.0 * sumMachine / samples);
            }

            System.out.println(
                    "concurrentDurationsAreCpuTime=false");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy với JDK 17+ có module `jdk.jfr`:

~~~bash
javac --release 17 -encoding UTF-8 GcConcurrentJfrProbe.java

java -XX:+UseG1GC -Xms128m -Xmx256m \
  -XX:ActiveProcessorCount=2 GcConcurrentJfrProbe

java -XX:+UseZGC -Xms128m -Xmx256m \
  -XX:ActiveProcessorCount=2 GcConcurrentJfrProbe
~~~

**Hai ví dụ đầu ra thực tế trên JDK 24/Windows** (con số có thể khác ở mỗi lần chạy):

~~~text
G1:
gcEvents=58
concurrentPhaseEvents=22
distinctConcurrentPhases=6
concurrentPhaseDurationMsSum=162
cpuLoadSamples=7
avgJvmLoadPct=2.27
avgMachineLoadPct=82.70
concurrentDurationsAreCpuTime=false

ZGC:
gcEvents=9
concurrentPhaseEvents=59
distinctConcurrentPhases=7
concurrentPhaseDurationMsSum=248
cpuLoadSamples=7
avgJvmLoadPct=2.43
avgMachineLoadPct=63.98
concurrentDurationsAreCpuTime=false
~~~

**Cách đọc đúng:**
- `concurrentPhaseEvents` chứng minh JVM đã ghi các phases concurrent vào JFR trong cửa sổ này.
- `concurrentPhaseDurationMsSum` là tổng **elapsed durations** của events. Các phases có thể trùng thời gian, lồng nhau hoặc mô tả công việc khác nhau. **Không** coi tổng đó là “GC dùng N milliseconds CPU” hoặc “GC % = tổng duration / wall”.
- `cpuLoadSamples` là số samples mà JFR tạo. Cửa sổ rất ngắn có thể không có samples dù đã bật event; khi đó code không in phần average.
- `avgJvmLoadPct` ở đây lấy trung bình `jvmUser+jvmSystem` do JFR báo, được chuẩn hóa theo cách của event/platform; nó không phải % trên một core và **không** phải GC-only CPU.
- `avgMachineLoadPct` là machine-wide CPU sample, có thể bao gồm nhiều tiến trình khác.
- `GC events` của G1 khác định nghĩa và số lượng events của ZGC; đừng xem số lượng ít hơn là kết luận collector tốt hơn.
- **Thông điệp quyết định:** JFR giúp ghép **thời điểm GC phases** với **CPU/load trend**, nhưng để attribution chính xác GC CPU cần OS/native-thread profiler hoặc phân tích chuyên dụng hơn.

### 7.2. Dùng file JFR trong thử nghiệm dài

Trong một ứng dụng thật, có thể ghi recording bằng JVM flag/tool thay vì code:

~~~bash
java -XX:+UseZGC -Xmx2g \
  -XX:StartFlightRecording=filename=gc-study.jfr,dumponexit=true \
  -jar app.jar

# Phân tích offline các event đã có trong recording:
jfr print --events jdk.GCPhaseConcurrent,jdk.GarbageCollection,jdk.CPULoad \
  gc-study.jfr
~~~

**Lưu ý:** Tùy recording settings, `jdk.GCPhaseConcurrent` hoặc `jdk.CPULoad` có thể không được bật. Khi phải đo bắt buộc, dùng `.jfc`/`jdk.jfr.Recording.enable(...)` và xác minh event thực sự được ghi. Đường `app.jar` là ví dụ về **ứng dụng do bạn cung cấp**, không phải file của bài thực hành.

## 8. Đọc GC log và metric đúng vai trò

### 8.1. Unified Logging

HotSpot hiện đại hỗ trợ `-Xlog`. Một số cấu hình hữu ích:

~~~bash
# Tổng quan các GC events:
java -XX:+UseZGC -Xlog:gc -jar app.jar

# Chi tiết phases, heap, CPU reporting và init:
java -XX:+UseZGC -Xlog:gc*=info:file=gc.log:uptime,level,tags \
  -jar app.jar

# G1: theo dõi GC và safepoints ở mức phù hợp:
java -XX:+UseG1GC -Xlog:gc*,safepoint=info:file=g1.log:uptime,level,tags \
  -jar app.jar
~~~

Dùng tên tags được runtime hỗ trợ (xem `java -Xlog:help`). Giữ thông số logging nhất quán trong benchmark; log quá chi tiết như `trace` ở workload cực nhanh có thể tự tăng CPU/I/O overhead.

**Có gì trong log?**
- GC cycle start/end và trigger, allocation pressure.
- Pause duration/phase.
- Concurrent phases và công việc kéo dài.
- Heap occupancy/capacity trước-sau.
- Allocation stalls hoặc thông tin về tốc độ/khả năng reclaim theo collector/version.
- GC CPU line `User/Sys/Real` ở một số loại sự kiện.

**Không có gì tự động?** Tổng GC worker CPU mà không cần phân loại; total cost mutator barriers; request p99; container throttling. Những dữ liệu này cần thêm nguồn.

### 8.2. GC MXBeans

`java.lang.management.ManagementFactory.getGarbageCollectorMXBeans()` trả các beans do JVM cung cấp. `getCollectionCount()` và `getCollectionTime()` có thể là nguồn thống kê, nhưng:
- Tên beans không được chuẩn hóa giống nhau giữa collectors.
- `getCollectionTime()` có unit **milliseconds**, nhưng semantics thời gian được báo khác nhau theo collector.
- Một số beans có thể trả `-1` nếu chỉ số không được hỗ trợ.
- Có thể có nhiều beans (ví dụ ZGC minor/major cycles/pauses) cho các nhóm hoạt động khác nhau.
- **Không cộng mọi MXBean time rồi tuyên bố đó là total GC CPU**; trong ví dụ 1, ta cộng chỉ để minh họa số liệu cần đọc cẩn trọng.

Nếu muốn báo cáo chuẩn, định nghĩa metric theo **tên collector/JDK cụ thể**, kiểm chứng semantics và dùng cùng phương pháp trong tất cả lần thử.

### 8.3. JFR và Native profiling

JFR hữu ích để:
- Xem phases concurrent, pauses, CPU load samples, allocation pressure.
- Correlate GC với slow requests, thread scheduling và JVM runtime events.
- Phân tích profile của ứng dụng qua thời gian thay vì nhìn một dòng log.

Để phân biệt **CPU của GC workers** và **CPU của mutators**, cần profiler ở mức process/native threads hoặc công cụ quan sát OS có khả năng phân loại GC threads. Trên Linux có thể dùng hệ sinh thái profiler/perf/eBPF theo quyền và cấu hình phù hợp; trên Windows dùng tooling tương đương. Hãy tính cả profiler overhead và cấp quyền truy cập phù hợp.

**Đừng nhầm:** JFR `jdk.GCPhaseConcurrent.duration` đo elapsed-time; JFR `jdk.CPULoad` đo JVM/host load; GC CPU thread attribution là **bài toán khác**.

## 9. Khi CPU của GC nền trở thành bottleneck

### 9.1. CPU quota thấp, load cao

Giả sử service có 2 CPU cores hữu hiệu và tải request đang dùng gần hết quota. Nếu concurrently có GC marking/relocation:
- Runtime threads phải chia CPU.
- Scheduler latency tăng.
- GC progress chậm hơn nếu mutators lấy phần lớn CPU.
- Có thể tăng request p99 dù GC STW pause chỉ rất ngắn.

**Điểm cần đo:** CPU quota/throttling (không chỉ host usage), request p95/p99, GC phases/triggers, allocation stalls, throughput và GC CPU thread profile.

### 9.2. Allocation rate tăng đột biến

Một ứng dụng có thể tạo lượng garbage nhanh hơn GC concurrent thu hồi. Nếu heap free headroom nhỏ:
- GC cycle bắt đầu thường xuyên hơn.
- Workers phải làm nhiều việc hơn và tranh CPU hơn.
- Có thể phát sinh allocation stalls, collector-specific pacing, hoặc các tình trạng thiếu bộ nhớ.
- Tăng `ConcGCThreads` đôi khi giúp GC theo kịp nhưng làm application thiếu CPU.
- Tăng heap headroom có thể giảm áp lực mà không cần tăng CPU worker count.

**Không có một giá trị `-XX:ConcGCThreads=2` đúng cho mọi app.** Nó tùy CPU quota, live set, allocation rate và GC heuristics.

### 9.3. Live set lớn hoặc object graph phức tạp

Live set lớn làm GC phải quản lý nhiều object/references. Hai ứng dụng cùng heap 4 GiB:
- App A sống lâu 100 MiB, phần lớn object chết nhanh.
- App B live 3 GiB, giữ object graph phức tạp.

Chúng có thể có GC costs khác nhau rất lớn dù cùng `-Xmx`. **Heap max không phải live set**. Trong benchmark, đo occupancy sau GC và lifetime distribution.

### 9.4. Băng thông bộ nhớ / cache saturation

Các pha scan/relocate sử dụng memory bandwidth và cache. Khi GC concurrent với ứng dụng có workload memory-bound (duyệt nhiều arrays/graphs):
- Cả hai tranh shared cache, memory bus, NUMA interconnect.
- App IPC/instructions per cycle có thể giảm, CPU utilization chưa chắc đạt 100%.
- Tăng số GC worker threads đôi khi không làm collection hoàn tất tuyến tính nhanh hơn.
- Giải pháp có thể nằm ở heap locality, allocation patterns, NUMA/deployment chứ không chỉ CPU flags.

## 10. Tuning theo trình tự an toàn

### Bước 1 — Đặt SLO và đường cơ sở

Trước khi thay flags:
- Xác định p95/p99/p99.9 request latency và throughput mục tiêu.
- Ghi JDK distribution/version, GC, architecture, OS, cgroup quota, heap `-Xms`/`-Xmx`.
- Thu thập allocation rate, live set, GC cycle frequencies, pauses, CPU/process usage, OS throttling.
- Chạy workload đủ lâu sau warmup với pattern tương tự production.
- So sánh từng lần thử với baseline, không thay nhiều flags và code cùng lúc.

### Bước 2 — Kiểm tra ứng dụng cấp phát gì

Tối ưu allocation rate đôi khi đem lại lợi ích lớn hơn bất kỳ collector tuning:
- Tránh tạo nhiều object tạm không cần thiết trong hot path.
- Kiểm soát serialization/deserialization, byte buffers, stream transformations.
- Xem lại cache/lifetime giữ object sống quá lâu.
- Không tự tối ưu bằng pooling mọi thứ: pooling sai có thể tăng live set, contention và memory retention.
- Dùng Java profiler/JFR allocation events theo overhead cho phép.

**Giảm allocation không phải luôn giảm CPU tổng** nếu thay vào đó tạo logic phức tạp hơn; phải đo lại.

### Bước 3 — Đảm bảo heap headroom

Với ZGC concurrent, nếu live set và allocation rate cao, thiếu free headroom có thể làm mutators chờ GC. Cân nhắc tăng `-Xmx` theo memory budget của máy/container. Với ZGC, `-XX:SoftMaxHeapSize` là ngưỡng mềm, có thể vượt khi cần tránh stalls; không dùng nó như hard limit.

**Đổi heap cũng có giá:** RAM, RSS/container limit, commit/uncommit overhead, memory pressure của host và thời gian GC cycle có thể thay đổi. Không tăng tới sát memory limit rồi gây OOMKill.

### Bước 4 — Để heuristics tự điều chỉnh trước

Mặc định HotSpot/JDK mới đã có GC heuristics. Thông thường nên:
1. Dùng collector ở cấu hình mặc định với heap phù hợp.
2. Đo tail latency, throughput, GC progress và CPU throttling.
3. Chỉ khi có bằng chứng bottleneck mới chỉnh `-XX:ConcGCThreads` hoặc các options chi tiết.
4. Thay **một biến mỗi lần**, đủ các repetitions; quay lại giá trị mặc định nếu hiệu quả không rõ.

Ví dụ option minh họa để thử nghiệm (không phải cấu hình “khuyến nghị cho mọi service”):

~~~bash
java -XX:+UseZGC -Xmx2g -XX:ConcGCThreads=2 -jar app.jar
~~~

Có thể GC hoàn tất nhanh hơn khi tăng workers nhưng application mất CPU; hoặc GC chậm lại khi giảm workers và dẫn tới stalls. Quan hệ thường **không tuyến tính**.

### Bước 5 — Điều chỉnh G1 pause goal khi phù hợp

Nếu G1 đang được dùng và latency cần cải thiện, `-XX:MaxGCPauseMillis=N` có thể được thử như **mục tiêu**, không phải bảo đảm.

~~~bash
java -XX:+UseG1GC -Xmx2g -XX:MaxGCPauseMillis=100 -jar app.jar
~~~

Một pause target quá thấp có thể tăng tần suất GC/overhead hoặc giảm throughput. G1 còn có concurrent refinement options, nhưng dồn phần concurrent work vào pause **không phải cách miễn phí để tiết kiệm CPU**; nó có thể làm pause dài hơn.

### Bước 6 — Kiểm thử container quotas và overload

Dùng chính CPU quota của production:
- Monitor CPU throttling, cgroup usage, run queues.
- Đo p99 khi throughput tăng tới bão hòa, không chỉ idle load.
- Xem số runnable GC workers và mutators cạnh tranh.
- Đảm bảo SLO giữ được với burst traffic, memory pressure và GC under load.
- Có safe rollback nếu flags mới làm latency/throughput kém đi.

## 11. Ma trận tình huống và quyết định

| Quan sát | Giả thuyết có thể | Thử gì tiếp theo? |
| --- | --- | --- |
| GC pause rất nhỏ nhưng request p99 cao | CPU contention, cgroup throttling hoặc nguyên nhân ngoài GC | Correlate p99 với process CPU, quota, JFR concurrent GC windows |
| ZGC có allocation stalls | GC không theo kịp allocation hoặc headroom thiếu | Đo live set/allocation rate, heap max, CPU quota, concurrent workers |
| Nhiều concurrent phases liên tiếp | Allocation/live-set pressure cao | Phân tích GC log/JFR, giảm allocation, xem heap headroom |
| CPU process cao nhưng GC log ít | Workload CPU/JIT hoặc barrier overhead/CPU ngoài GC | Native profiler + allocation profiling, không quy lỗi cho GC vô căn cứ |
| Process CPU-seconds > wall-seconds | Có nhiều cores chạy đồng thời | Quy đổi avg cores = CPU/wall, không coi là lỗi đo |
| CPU toàn host chỉ 20% nhưng container throttled | Container quota nhỏ hơn host capacity | Đọc cgroup quota/throttling, tăng capacity hoặc giảm tải |
| Giảm `ConcGCThreads` xong throughput giảm | GC tiến triển chậm, chu kỳ dày hoặc stall | Trả default, đối chiếu GC backlog và allocation stalls |
| Tăng `ConcGCThreads` xong p99 tăng | GC tranh CPU/bandwidth với app | Kiểm native worker CPU, scheduler, thử mức nhỏ hơn |
| G1 pause goal giảm nhưng GC nhiều hơn | Trade-off giữa pause và throughput | Điều chỉnh target theo SLO, kiểm throughput và total CPU |
| JFR `concurrentPhaseDuration` tăng | Pha kéo dài hơn, có thể do contention/workload | Không gọi đó là GC CPU; correlate với CPU profile và memory |
| Collector đổi mà performance khác | JVM/compiler/heap/warmup/collector differences | A/B tests lặp lại, cùng JDK/config và traffic |
| RSS không giảm ngay sau GC | JVM giữ reserved/committed memory | Phân biệt heap occupancy, committed, RSS và OS policy |

## 12. Khi nào chọn collector nào?

**G1** thường là điểm bắt đầu tốt khi cần throughput cao và pause mục tiêu không ở mức cực nhỏ; HotSpot hỗ trợ rộng, ergonomics trưởng thành. **ZGC** phù hợp khi mục tiêu pause rất ngắn quan trọng và CPU/headroom trade-off chấp nhận được, nhất là trên JDK hiện đại. **Shenandoah** cũng là lựa chọn low-latency trên các bản JDK có hỗ trợ, cần kiểm mode/build/version.

Lựa chọn cuối cùng cần trả lời:
- **Tail latency SLO** trong peak và p99.9 là bao nhiêu?
- CPU quota và ngân sách hạ tầng cho việc GC concurrent là bao nhiêu?
- Live set, allocation rate, object churn là gì?
- G1 có thực sự vi phạm pause SLO không?
- ZGC/Shenandoah có bớt STW nhưng làm CPU contention lớn không?
- JVM version cụ thể hỗ trợ collector mode nào?
- Khi overload, collector gây allocation stalls/throughput collapse hay giữ được ổn định?

**Không có collector “nhanh nhất” tách khỏi workload và SLO.** Dùng chỉ số end-to-end, không chọn chỉ theo GC pause chart.

## 13. Thử nghiệm chuẩn để so CPU GC và request latency

Một runbook hữu ích:

1. **Cố định môi trường:** Cùng máy/VM, CPU quota, governor, RAM, OS/JDK version, networking và traffic profile. Ghi lại các điểm không kiểm soát được.
2. **Cùng logic ứng dụng:** Không để collector A chạy bản build khác collector B.
3. **Warmup:** JIT/C2, class loading, cache, connection pools đạt trạng thái vận hành.
4. **Độ dài đủ:** Mỗi run gồm nhiều GC cycles, nhiều request samples và burst/steady phases.
5. **GC log/JFR:** Bật cùng độ chi tiết/recording overhead phù hợp giữa các runs.
6. **Process CPU:** Đo CPU-seconds và quy đổi avg cores trên cửa sổ; không dùng “CPU 100%” không rõ mẫu số.
7. **GC CPU attribution:** Nếu cần, dùng native thread profiler; lưu ý barrier overhead nằm trong mutators.
8. **User-facing latency:** p50/p95/p99/p99.9 và timeout/error rate, throughput req/s.
9. **Memory:** Live set, allocation rate, headroom, major/minor cycles, allocation stalls.
10. **Thử overload:** Tăng tải có kiểm soát, theo dõi quota throttling và khả năng phục hồi.
11. **Lặp nhiều lần:** So distribution, confidence intervals và outliers; không quyết định từ một run.
12. **Chỉ đổi một factor mỗi lần:** `collector`, `-Xmx`, `ConcGCThreads` hoặc code allocation pattern — tránh trộn.
13. **Ghi cost:** CPU-hours và memory cost thực tế ở mức throughput/latency đã đạt, không so giá trị tối ưu từng chỉ số độc lập.

Một bảng báo cáo có thể dùng:

~~~text
JDK/build: ...
OS/container quota: ...
Collector/mode: ...
Heap Xms/Xmx: ...
Workload: ... requests/s, allocation MiB/s, live-set MiB

Request p99/p99.9: ...
Throughput successful requests/s: ...
Process CPU-seconds / observation wall-time: ...
Native GC worker CPU-seconds (nếu có): ...
Container CPU throttled time: ...
STW pause max/p99: ...
Concurrent phase durations: ...
Allocation stalls / OOM / Full GC: ...
Decision relative to SLO and infrastructure cost: ...
~~~

Các dòng `...` trong biểu mẫu là **các trường để điền từ kết quả thực nghiệm**, không phải số liệu đo được hoặc stdout của chương trình.

## 14. Những lỗi phổ biến

| Nhầm lẫn | Vì sao sai? | Cách khắc phục |
| --- | --- | --- |
| “GC concurrent không dùng CPU ứng dụng” | GC workers cạnh tranh scheduling và bandwidth | Đo process/thread CPU, p99 và quota trong cùng cửa sổ |
| “Pause 1 ms nghĩa là GC chỉ tốn 1 CPU-ms” | Concurrent work và barriers ngoài pause | Tách pause, concurrent elapsed, native GC CPU và mutator overhead |
| Cộng `GCPhaseConcurrent` durations = GC CPU | Durations là wall time, phases có thể overlap | Dùng CPU profiler/attribution phù hợp |
| Lấy `GarbageCollectorMXBean.collectionTime` làm GC worker CPU | Semantics/beans tùy collector | Đọc là metric JVM reported, không quy đổi trực tiếp CPU |
| Chỉ đọc host CPU % | Container có thể bị CPU quota throttle | Đọc cgroup metrics và effective cores |
| Thấy process CPU-seconds > wall rồi báo “bug” | Nhiều threads chạy trên nhiều cores | Quy về avg cores = CPU/wall |
| Hạ `ConcGCThreads` càng thấp càng tốt | GC có thể không theo kịp allocations | Bắt đầu bằng heuristics mặc định; đo stalls/headroom |
| Tăng workers càng nhiều càng tốt | Tranh CPU/cache/bandwidth và overhead phối hợp | Tune bằng SLO, workload và số cores thực |
| Tăng heap vô hạn để tránh GC | Tốn RAM/cost, memory pressure/OOMKill | Đo live set và cân bằng headroom |
| Dùng `-XX:+ZGenerational` trên JDK 24+ | Option đã bị gỡ, ZGC mặc định/chỉ còn generational | Dùng `-XX:+UseZGC` và docs phiên bản đúng |
| Giả định Shenandoah generational mặc định mọi JDK | Mode/build support khác nhau | Kiểm JEP/JVM flags và GC init log của build |
| Chỉ đo trên workload loop ngắn | Warmup/alloc pattern sai thực tế | Benchmark nhiều lần với production-like traffic |
| Thấy GC CPU cao là lỗi ứng dụng ngay | Có thể do live set/collector/memory bandwidth/quota | Điều tra với allocation and native profiling |
| Chỉ giảm STW pause mà bỏ throughput/cost | Tail p99 và CPU cost có thể kém | Đặt đa mục tiêu SLO + throughput + resources |
| Tuyên bố ZGC luôn nhanh hơn G1 từ một mẫu | Hệ thống/JVM/workload thay đổi | A/B controlled, repetitions và error bars |
| `System.gc()` là cách benchmark GC production | Thay đổi workload, behavior phụ thuộc JVM flags | Tạo allocation workload tự nhiên, đo GC dưới tải thực |
| Đếm số GC event làm thước đo xếp hạng | Event taxonomy khác giữa collector/JDK | So end-to-end metrics và GC progress tương ứng |
| Đọc JFR `CPULoad` là “GC CPU %” | Event là JVM/host CPU samples | Cần native GC thread attribution và barrier analysis |

## 15. Bài tập tự kiểm tra (kèm đáp án)

**Câu 1.** Một JVM có p99 STW pause chỉ 2 ms nhưng request p99 tăng khi CPU quota gần đầy. Có thể loại GC khỏi danh sách nghi vấn không?

**Đáp án:** Không. Concurrent GC workers/barriers vẫn tốn CPU/cache/memory bandwidth. Cần correlate GC phases với process CPU, cgroup throttling, request latency và phân loại native threads.

**Câu 2.** `jdk.GCPhaseConcurrent` báo một pha 200 ms. Có thể khẳng định GC đã tiêu tốn 200 CPU-ms?

**Đáp án:** Không. 200 ms là elapsed duration; có thể nhiều GC threads cùng làm việc, bị scheduler preempt hoặc chờ. CPU consumed cần dữ liệu CPU-time attribution riêng.

**Câu 3.** Process dùng 3 CPU-seconds trong một khoảng wall 1 second. Đây có phải lỗi metric không?

**Đáp án:** Không. Trên hệ thống nhiều cores, process có thể đồng thời dùng xấp xỉ 3 cores. `avgProcessCores=3/1=3`.

**Câu 4.** GC native workers dùng 1.8 CPU-seconds trong 2 giây trên effective 4 cores. Tỉ lệ GC / capacity là bao nhiêu?

**Đáp án:** Capacity = `4×2=8 core-seconds`, GC share = `1.8/8=22.5%`. Cần nói rõ hiệu lực 4 cores và cửa sổ 2 giây.

**Câu 5.** Giảm `-XX:ConcGCThreads` từ 4 xuống 1 khiến process CPU thấp hơn nhưng allocation stalls tăng. Đây là tối ưu tốt chưa?

**Đáp án:** Chưa. CPU tiết kiệm có thể đổi lấy latency xấu và GC không theo kịp allocation. Đánh giá tổng SLO/throughput, headroom và quay về heuristics khi cần.

**Câu 6.** Tại sao tăng `-Xmx` có thể giảm allocation stalls với ZGC?

**Đáp án:** Heap headroom lớn hơn cho phép app tiếp tục cấp phát trong khi concurrent GC làm việc. Nhưng phải đối chiếu RAM cost, live set và container memory limit.

**Câu 7.** Có nên dùng `-XX:+ZGenerational` trên JDK 24 hay JDK 25 để bật generational ZGC?

**Đáp án:** **Không.** JDK 24 đã loại non-generational ZGC và gỡ tùy chọn `ZGenerational`. Dùng `-XX:+UseZGC`.

**Câu 8.** G1 báo ít CPU concurrent sau khi thay cấu hình, nhưng STW pauses tăng. Vì sao?

**Đáp án:** Một số công việc trước đó concurrent có thể đã chuyển vào pause; giảm CPU đồng thời có thể tăng độ dài pause. Phải so end-to-end latency và throughput.

**Câu 9.** Vì sao không dùng `ThreadMXBean.getThreadCpuTime()` để kết luận toàn bộ GC CPU?

**Đáp án:** JVM có các native GC worker threads không hiện đầy đủ dưới Java thread MXBean, và barrier overhead nằm trên mutator threads. Cần OS/native thread profiling.

**Câu 10.** Hai JVM cùng heap max 4 GiB nhưng GC overhead khác nhau nhiều. Có hợp lý không?

**Đáp án:** Có. Live set, allocation rate, object graph và memory locality khác nhau ảnh hưởng rất lớn tới công việc GC, không chỉ `-Xmx`.

**Câu 11.** Host CPU thấp nhưng container request latency tăng và cgroup throttled time cao. Nên ưu tiên quan sát gì?

**Đáp án:** Effective quota, throttling và runnable demand trong container; host average CPU không mô tả đúng tài nguyên app được cấp.

**Câu 12.** Một lần microbenchmark cho ZGC wall-time ngắn hơn G1, có nên chuyển production ngay?

**Đáp án:** Không. Cần production-like A/B tests lặp lại, warmup, p99/p99.9, throughput, CPU/memory cost, allocation stalls và mức độ ổn định trước khi quyết định.

## 16. Ghi nhớ cuối bài

- **GC nền sử dụng CPU thực.** Chuyển việc ra khỏi STW pause là trade-off giữa latency và tài nguyên, không làm chi phí biến mất.
- **Không đánh đồng** concurrent elapsed time, STW pause, process CPU time và GC worker CPU-seconds.
- **CPU contention và mutator barriers** có thể làm request p99 tăng dù GC pause cực ngắn.
- **Ít workers quá** có thể khiến GC không theo kịp allocation; **nhiều workers quá** có thể tranh CPU/cache/memory bandwidth với app.
- **Heap headroom** có vai trò đặc biệt với concurrent GC; `-Xmx` và `-XX:SoftMaxHeapSize` phải được hiểu đúng semantics.
- **G1, ZGC, Shenandoah có trade-off khác nhau**; chọn bằng SLO, workload, CPU quota và benchmark, không theo nhãn “low-latency”.
- **JDK 24+: ZGC chỉ còn generational**; không dùng cờ `ZGenerational` cũ. **JDK 25:** generational Shenandoah theo JEP 521 khi build hỗ trợ.
- **Quan sát nhiều nguồn:** JVM GC logs, JFR, process CPU, native profiling, container metrics, allocation/live set và tail latency.
- **Đo trong môi trường giống production** và đổi từng biến để có kết luận đáng tin.

## 17. Tài liệu tham khảo hiện hành

- [Oracle Java SE 25 — HotSpot GC Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html)
- [Oracle Java SE 25 — Garbage-First (G1) Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html)
- [Oracle Java SE 25 — G1 GC Tuning và concurrent refinement](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html)
- [Oracle Java SE 25 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/z-garbage-collector.html)
- [Oracle Java SE 25 — java command, `-Xlog`, `-XX:ConcGCThreads` và GC flags](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Oracle Java SE 25 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [Oracle Java SE 25 — `com.sun.management.OperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html)
- [Oracle Java SE 25 — JFR `Recording`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle Java SE 25 — JFR `RecordingFile` và `RecordedEvent`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [OpenJDK JEP 377 — ZGC: Production (Java 15)](https://openjdk.org/jeps/377)
- [OpenJDK JEP 379 — Shenandoah: Production (Java 15)](https://openjdk.org/jeps/379)
- [OpenJDK JEP 490 — ZGC: Remove the Non-Generational Mode (JDK 24)](https://openjdk.org/jeps/490)
- [OpenJDK JEP 521 — Generational Shenandoah (JDK 25)](https://openjdk.org/jeps/521)
