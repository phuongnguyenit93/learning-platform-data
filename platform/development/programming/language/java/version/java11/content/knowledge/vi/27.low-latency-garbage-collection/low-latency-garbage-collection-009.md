# So sánh collector dưới cùng tải và điều kiện phần cứng (Java 11+)

## 1. Tại sao cần một phép thử công bằng?

Khi tối ưu độ trễ của một ứng dụng Java, bạn có thể cân nhắc **G1**, **ZGC** hoặc **Shenandoah**. Các collector này khác nhau về thời gian tạm dừng ứng dụng (*GC pause*), công việc thu hồi bộ nhớ thực hiện đồng thời (*concurrent GC work*), tổng throughput, CPU usage và memory footprint. Một GC có **pause rất ngắn** nhưng sử dụng nhiều tài nguyên concurrent vẫn có thể khiến **request latency hoặc throughput của ứng dụng không tốt hơn**.

Một phép so sánh đúng phải trả lời đồng thời:

- **GC pause:** JVM phải dừng application threads trong mỗi GC pause bao lâu, p50/p95/max ra sao?
- **Application latency:** request hoặc batch mất bao lâu, có p95/p99 outliers không?
- **Throughput:** bao nhiêu request hoặc batch **thành công** mỗi giây?
- **Bộ nhớ:** Java heap, live set, **RSS** và khả năng chịu allocation spikes có phù hợp ngân sách không?
- **CPU:** hoạt động GC concurrent có tranh CPU với mutator threads không?
- **Độ chính xác:** cùng đầu vào cho cùng kết quả, không tăng errors/OOM/timeouts?
- **Độ ổn định:** số liệu có lặp lại qua nhiều lần thử, trên chính hệ thống mục tiêu không?

**Nguyên tắc trung tâm:** chỉ thay **collector/mode** trong vòng benchmark đầu tiên; giữ **cùng code, cùng dữ liệu, cùng workload, cùng JDK build, cùng máy, CPU limit, heap budget, GC logs và JFR settings**. Nếu thay đồng thời JDK, CPU quota hoặc code nghiệp vụ, không thể kết luận chênh lệch chỉ đến từ collector.

Bài này triển khai một chương trình **biên dịch được bằng `javac --release 11`**, chạy cùng một bài toán cấp phát bộ nhớ bằng G1, Generational ZGC và Shenandoah trên OpenJDK 21. Ta dùng **JDK Flight Recorder (JFR)** và `jdk.GCPhasePause` để đo GC pauses, kết hợp `System.nanoTime()` đo độ trễ batch và throughput. Các con số thực nghiệm chỉ mang tính minh họa: không khẳng định collector nào luôn thắng.

## 2. Các collector hiện hành cần hiểu đúng phiên bản

### G1: điểm xuất phát cho đa số ứng dụng

**Garbage-First (G1)** là GC mặc định trên phần lớn cấu hình HotSpot hiện hành. Nó là generational, mostly concurrent, thực hiện một số pha **stop-the-world (STW)** để evacuation và cân bằng throughput với thời gian pause.

- Chọn bằng `-XX:+UseG1GC`.
- Thường phù hợp làm baseline trước khi tối ưu hoặc chuyển collector.
- `-XX:MaxGCPauseMillis` là **mục tiêu mềm**, không bảo đảm mọi pause luôn dưới ngưỡng.
- Một cấu hình heap/young generation quá chặt có thể làm G1 khó tự điều chỉnh kích thước vùng trẻ và đáp ứng pause goal.
- G1 có thể gặp long/Full GC trong các tình huống khó như allocation pressure cao, heap quá chật hoặc nhiều humongous objects.

### ZGC: rất ít thời gian dừng, cần đo giá concurrent work

**Z Garbage Collector (ZGC)** làm phần lớn công việc GC đồng thời với application threads, nhắm tới **pause cực ngắn**. Trade-off có thể là CPU, memory headroom, throughput hoặc allocation stalls nếu collector không theo kịp tốc độ cấp phát.

- Chọn ZGC trên JDK mới bằng `-XX:+UseZGC`.
- **Riêng JDK 21**, để dùng **Generational ZGC** cần `-XX:+UseZGC -XX:+ZGenerational`.
- **Từ JDK 24**, ZGC chỉ còn chế độ generational; **cờ `-XX:+ZGenerational` đã bị loại bỏ**. Trên JDK 24/25/26 chỉ dùng `-XX:+UseZGC`.
- ZGC ở **JDK 11** mới là tính năng experimental. Không dùng ví dụ JDK 11 experimental làm khuyến nghị production hiện nay; hãy thử trên bản JDK LTS còn được hỗ trợ và đúng mode.

**Vì sao việc ghi version quan trọng?** ZGC JDK 21 không generational, Generational ZGC JDK 21 và ZGC JDK 24+ không phải ba cấu hình có cùng thuật toán. Nếu so G1 trên JDK 21 với ZGC trên JDK 25, chênh lệch còn đến từ cả JVM version.

### Shenandoah: concurrent low-pause, phụ thuộc JVM build/mode

**Shenandoah** cũng hướng tới low-pause-time GC bằng công việc thu hồi đồng thời với ứng dụng.

- Cờ cơ bản khi HotSpot build hỗ trợ: `-XX:+UseShenandoahGC`.
- Được tích hợp vào OpenJDK ở JDK 12 và trở thành **product feature ở JDK 15**.
- Không giả định mọi bản phân phối Java 11 có Shenandoah.
- Các JDK mới như JDK 25 hỗ trợ **Generational Shenandoah** qua `-XX:ShenandoahGCMode=generational` trên build phù hợp. Phải ghi rõ mode và version trong benchmark; Shenandoah JDK 21 mặc định không tương đương một mode generational JDK 25.
- Nếu runtime từ chối cờ, đó là **collector không khả dụng**, không phải kết quả hiệu năng “0 ms”.

### Bảng so sánh định tính

| Collector | Mục tiêu chính | Chi phí và rủi ro cần đo | Cách chọn |
| --- | --- | --- | --- |
| G1 | Cân bằng pause/throughput, mặc định phổ biến | STW evacuation/Full GC outliers, concurrent phases | `-XX:+UseG1GC` |
| Generational ZGC | GC pause rất thấp | CPU concurrent, heap headroom, allocation stalls, throughput | JDK21: `-XX:+UseZGC -XX:+ZGenerational`; JDK24+: `-XX:+UseZGC` |
| Shenandoah | Giảm pause qua concurrent collection | Concurrent CPU, throughput/footprint, mode/build | `-XX:+UseShenandoahGC` |
| Parallel GC | Ưu tiên throughput khi pause không nghiêm ngặt | STW pauses thường đáng kể hơn | `-XX:+UseParallelGC` |

**Collector “low-pause” không đồng nghĩa “low CPU cost” hoặc “maximum throughput”.** Những ứng dụng có latency SLO rất nghiêm ngặt đáng thử ZGC/Shenandoah, nhưng lựa chọn chỉ nên dựa trên số liệu cụ thể ở tải tương đương.

## 3. Thiết lập phép đo công bằng

Một **bản hợp đồng thử nghiệm** cần ghi lại:

| Nhóm | Giữ nhất quán trong vòng so collector |
| --- | --- |
| Ứng dụng | Cùng source/binary, dependencies, business logic, kết quả |
| Dữ liệu | Cùng dataset, seed, payload sizes, key distribution, valid/invalid ratio |
| Tải | Cùng số requests/batches, concurrency, allocation profile, live set, request mix, ramp-up |
| Runtime | Cùng **JDK vendor + full build**, GC chỉ là biến được thay |
| Phần cứng | Cùng CPU model/NUMA, RAM, OS/kernel, I/O và background load |
| Container | Cùng cgroup CPU quota/cpuset, memory limit, swap/affinity |
| Heap | Cùng `-Xms` và `-Xmx` trong vòng đầu |
| JVM options | Cùng những cờ không liên quan trực tiếp đến GC |
| Warm-up | Cùng số vòng/thời gian trước measured window |
| Measurement | Cùng timer, JFR event types/threshold, GC log verbosity và cửa sổ ghi |
| Correctness | Cùng checksum/outputs, success/error/timeout counts |
| Phân tích | Cùng thống kê percentiles, cùng mẫu số operations/time |

**`-XX:ActiveProcessorCount=2` không phải CPU pinning.** Nó chỉ làm HotSpot nhận biết số CPU logic để quyết định ergonomics. Nó **không** tự đặt cgroup quota/cpuset và không ngăn noisy neighbors tranh tài nguyên. Một benchmark nghiêm ngặt cần kiểm cả CPU affinity, throttling, host load và chính sách frequency/turbo.

### Cùng heap không có nghĩa cùng RSS

`-Xms256m -Xmx256m` giới hạn Java heap, **không** giới hạn RSS của JVM bằng 256 MB. Các GC khác nhau có thể dùng native memory, metadata, page mappings, GC threads, stacks và CPU concurrent khác nhau. Khi đánh giá cost/instance, đo cả:

- Heap used/committed và live set.
- Process **RSS/peak RSS**, container memory usage và OOM events.
- CPU utilization/CPU time, đặc biệt concurrent GC workers.
- Native memory nếu có công cụ phù hợp và được cấu hình nhất quán.
- Dung lượng dự phòng cho allocation spikes.

**Có hai vòng so sánh khác mục đích:** (1) giữ cùng heap/CPU budget, **chỉ đổi collector**; (2) cho phép **tuning riêng từng collector** trong cùng cost và SLO budget, rồi so cấu hình tối ưu. Đừng trộn hai vòng thành một kết luận.

## 4. Kịch bản tải phải gây GC thật và tạo kết quả kiểm được

Một phép đo đáng tin cần đủ lượng allocations và dữ liệu còn sống:

- **Allocation rate:** bao nhiêu bytes/second, object sizes/second.
- **Object lifetime:** phần lớn rất ngắn hay giữ qua nhiều GC cycles.
- **Live set:** objects còn reachable có chiếm lớn hơn một phần heap không.
- **Reference pattern:** có nhiều cập nhật pointers/cross-generation references không.
- **Concurrency:** bao nhiêu application threads cùng cấp phát.
- **Spike:** peak allocation khác steady-state bao nhiêu.
- **I/O:** DB/network/file có che tác động GC lên end-to-end latency không.

**Đừng ép GC bằng `System.gc()` trong mỗi vòng để “có dữ liệu”.** Explicit GC có semantics phụ thuộc collector và cờ JVM, làm tải không giống môi trường thật.

### Tránh benchmark mà JIT xóa allocations

Đoạn code kiểu:

~~~java
for (int i = 0; i < 100_000; i++) {
    byte[] unused = new byte[1024];
}
~~~

có thể bị JIT optimize vì mảng không được dùng. Demo bên dưới sử dụng một **ring buffer static** giữ tham chiếu các mảng mới và tính checksum từ nội dung của chúng. Từ đó allocations có observable effects, không đơn thuần là tạo dữ liệu rồi bỏ.

### Warm-up và measured phase

~~~text
JVM startup --> warm-up 8 rounds --> START JFR --> measure 40 rounds
                                               |     |
                                               |   durations + checksum
                                               |     |
                                               +---- STOP/DUMP JFR
                                                     |
                                                 print metrics
~~~

JFR bắt đầu **sau warm-up**, tránh lấy GC pause của startup rồi đem so với latency chỉ tính trong phase đo. GC log dòng lệnh có thể ghi **cả warm-up và phase đo**; vì thế phải phân biệt phạm vi khi đọc.

Nếu mục tiêu là **startup latency**, hãy làm phép đo riêng có ghi từ Java launcher (`-XX:StartFlightRecording`) và định nghĩa đúng startup boundary. Không dùng kết quả steady-state để kết luận startup nhanh/chậm.

## 5. Chọn metrics: GC pause khác request/batch latency

| Chỉ số | Nguồn | Ý nghĩa |
| --- | --- | --- |
| GC pause count, p50/p95/max | JFR `jdk.GCPhasePause` | Thời lượng từng phase JVM tạm dừng |
| Tổng pause duration | Tổng duration của GC pause events | Tổng thời gian JVM bị dừng trong cửa sổ đo |
| GC cycle count/duration | `jdk.GarbageCollection`/GC logs | Hoạt động thu gom, concurrent cycles và nguyên nhân |
| Application latency p50/p95/p99 | Timers trong app hoặc load generator | Độ trễ người dùng/tác vụ quan tâm |
| Throughput | Successful work / measured seconds | Công việc hoàn tất trên đơn vị thời gian |
| Peak RSS/heap occupancy | OS/container và JVM | Tính khả thi về memory budget |
| CPU, GC CPU contention | CPU metrics/profiling | Chi phí concurrent work |
| Allocation stalls, fallback/Full GC | GC logs/JFR | Collector có theo kịp allocation rate? |
| Errors, OOM, timeouts | Application/load generator | Kết quả có hợp lệ không? |

### Hai cách diễn giải dễ sai

**Không xem thời lượng `jdk.GarbageCollection` như thời gian JVM stop-the-world**. Một GC cycle của ZGC/Shenandoah có thể có những đoạn concurrent dài, không dừng toàn bộ ứng dụng. Để đo pause, chọn **`jdk.GCPhasePause`**.

**Không xem số `GCPhasePause` events là số GC cycles.** Một cycle có thể có nhiều pause phases. Nếu ZGC có 63 pause events và G1 có 10, không kết luận ZGC chạy “6,3 lần nhiều GC” hay “tổng pause gấp 6,3 lần”. Cần phân biệt **số phase, duration mỗi phase, tổng pause duration** và số GC cycles.

Nếu `GCPhasePause` không xuất hiện trong một recording ngắn, ghi **“không đủ mẫu”**, không in p95=0 ms. Event settings/threshold hoặc recording window cũng có thể làm mất dữ liệu.

### G1 soft goal không phải SLO

`-XX:MaxGCPauseMillis=100` có nghĩa G1 sẽ **cố** hướng tới pause target 100 ms, không có bảo đảm mọi pause đều nhỏ hơn. Request SLO còn chịu CPU, locks, network, queuing và DB. **Không ép một GC tuning flag giống nhau vào mọi collector** rồi gọi là cấu hình công bằng.

## 6. Chạy một chương trình Java 11-compatible dưới ba GC của JDK 21

Ví dụ thực tế được kiểm trên **OpenJDK 21.0.12.1**. Java source biên dịch với `javac --release 11`, nhưng cờ Generational ZGC là **cờ riêng của JDK 21**.

Cùng JVM budget:

~~~text
-Xms256m -Xmx256m -XX:ActiveProcessorCount=2
~~~

Collector flags:

~~~text
G1:           -XX:+UseG1GC
ZGC (JDK 21): -XX:+UseZGC -XX:+ZGenerational
Shenandoah:   -XX:+UseShenandoahGC
~~~

**Chỉ dành cho JDK 21:** trước tiên kiểm các lệnh có hoạt động trên chính JDK sẽ benchmark không:

~~~bash
java -XX:+UseG1GC -version
java -XX:+UseZGC -XX:+ZGenerational -version
java -XX:+UseShenandoahGC -version
~~~

Một JVM build không hỗ trợ Shenandoah có thể từ chối lệnh thứ ba. Đừng thay bằng flags experimental/không thuộc support policy để “cho chạy bằng được”. Trên JDK 24+ **loại bỏ `-XX:+ZGenerational`**, chỉ dùng `-XX:+UseZGC` cho ZGC generational. Đừng lấy G1 trên JDK 21 so ZGC trên JDK 25 rồi gán mọi khác biệt cho collector.

## 7. Ví dụ Java 11 hoàn chỉnh: ứng dụng tạo cùng tải và ghi JFR

Chương trình `GcSameLoadDemo.java` có cùng workload cho mọi collector:

- **8 warm-up rounds**, tiếp theo **40 measured rounds**.
- **50.000 allocations mỗi round**.
- Kích thước byte arrays lần lượt **512, 640, 768, 896 bytes**.
- **35.200.000 bytes requested array payload mỗi round** (không tính object headers/alignment).
- Tham chiếu mảng đi qua ring buffer `LIVE` có 4.096 entries.
- Mỗi mảng được ghi hai byte; checksum đo trên các giá trị thực đọc từ mảng.
- JFR `default` + bật `jdk.GCPhasePause` và `jdk.GarbageCollection` với threshold 0.
- JFR **start sau warm-up và stop ngay sau measured rounds**.
- `System.nanoTime()` tính thời lượng mỗi batch, p50/p95/max và measured rounds/second.
- Không dùng `System.gc()`, không thay source giữa runs.

### File `GcSameLoadDemo.java`

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.Locale;

public class GcSameLoadDemo {
    private static final int WARMUP = 8;
    private static final int ROUNDS = 40;
    private static final int ITEMS = 50_000;
    private static final int SLOTS = 4_096;
    private static final byte[][] LIVE = new byte[SLOTS][];

    private static long batch(int round) {
        long checksum = 0;
        for (int i = 0; i < ITEMS; i++) {
            int len = 512 + (i & 3) * 128;
            byte[] payload = new byte[len];
            payload[0] = (byte) i;
            payload[len - 1] = (byte) (round + i);
            LIVE[i & (SLOTS - 1)] = payload;
            checksum += len + (payload[0] & 255)
                    + (payload[len - 1] & 255);
        }
        return checksum;
    }

    private static double percentileMillis(
            long[] values, double fraction) {
        long[] sorted = values.clone();
        Arrays.sort(sorted);
        int index = (int) Math.ceil(fraction * sorted.length) - 1;
        return sorted[index] / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1)
            throw new IllegalArgumentException("Usage: out.jfr");
        for (int i = 0; i < WARMUP; i++) batch(i);

        long checksum = 0;
        long[] elapsed = new long[ROUNDS];
        double wallSeconds;

        try (Recording rec =
                     new Recording(Configuration.getConfiguration("default"))) {
            rec.setToDisk(true);
            rec.enable("jdk.GCPhasePause")
                    .withThreshold(Duration.ZERO);
            rec.enable("jdk.GarbageCollection")
                    .withThreshold(Duration.ZERO);
            rec.start();

            long started = System.nanoTime();
            for (int i = 0; i < ROUNDS; i++) {
                long a = System.nanoTime();
                checksum += batch(i);
                elapsed[i] = System.nanoTime() - a;
            }
            wallSeconds = (System.nanoTime() - started)
                    / 1_000_000_000.0;
            rec.stop();
            rec.dump(Path.of(args[0]));
        }

        System.out.println("warmupRounds=" + WARMUP);
        System.out.println("measuredRounds=" + ROUNDS);
        System.out.println("allocationsPerRound=" + ITEMS);
        System.out.println("bytesPerRound="
                + (ITEMS / 4 * (512 + 640 + 768 + 896)));
        System.out.println("checksum=" + checksum);
        System.out.printf(Locale.ROOT, "batchP50Ms=%.3f%n",
                percentileMillis(elapsed, 0.50));
        System.out.printf(Locale.ROOT, "batchP95Ms=%.3f%n",
                percentileMillis(elapsed, 0.95));
        System.out.printf(Locale.ROOT, "batchMaxMs=%.3f%n",
                percentileMillis(elapsed, 1.0));
        System.out.printf(Locale.ROOT, "measuredRoundsPerSecond=%.2f%n",
                ROUNDS / wallSeconds);
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("collectorBean=" + bean.getName());
        }
    }
}
~~~

### Điểm cần hiểu về code

`LIVE` là static array giữ tham chiếu mảng: tạo observable work để hạn chế việc JIT loại bỏ toàn bộ allocations. Mỗi round xử lý đúng số lượng mảng và tính checksum có thể so được.

**`bytesPerRound` chỉ là payload array bytes được yêu cầu**, không phải số bytes chính xác JVM đã allocate trên heap sau overhead, và càng không phải RSS.

JFR thu event chỉ trong measured rounds. Phần `rec.stop()/rec.dump()` xảy ra **sau** khi đồng hồ measured window được chốt, nên chi phí xuất file không nằm trong throughput counter. Tuy nhiên chi phí instrumentation trong lúc JFR chạy vẫn có thể ảnh hưởng ứng dụng; vì vậy mọi collector dùng **cùng cấu hình JFR**.

`ManagementFactory.getGarbageCollectorMXBeans()` in tên các collector beans của runtime. Tên và số lượng bean có thể khác giữa G1/ZGC/Shenandoah và JDK versions. **Không dùng tên bean như số liệu hiệu năng.**

### Biên dịch

~~~bash
javac --release 11 GcSameLoadDemo.java
~~~

Bài code dùng các API JFR/management/Path/Duration tồn tại trong Java 11. **Java 11-compatible code** khác với **JVM collector options**: cờ `-XX:+ZGenerational` trong ma trận bên dưới chỉ hợp lệ cho một số bản JDK (trong ví dụ là JDK 21).

## 8. Chạy ba GC với cùng heap và CPU ergonomics trên JDK 21

Từ thư mục chứa `GcSameLoadDemo.class`:

~~~bash
mkdir -p results

# G1
java -XX:+UseG1GC \
  -Xms256m -Xmx256m -XX:ActiveProcessorCount=2 \
  -Xlog:gc:file=results/g1.gc.log:uptime,level,tags \
  GcSameLoadDemo results/g1.jfr > results/g1.stdout

# Generational ZGC (JDK 21 only: needs -XX:+ZGenerational)
java -XX:+UseZGC -XX:+ZGenerational \
  -Xms256m -Xmx256m -XX:ActiveProcessorCount=2 \
  -Xlog:gc:file=results/zgc.gc.log:uptime,level,tags \
  GcSameLoadDemo results/zgc.jfr > results/zgc.stdout

# Shenandoah (only if this JDK build supports it)
java -XX:+UseShenandoahGC \
  -Xms256m -Xmx256m -XX:ActiveProcessorCount=2 \
  -Xlog:gc:file=results/shenandoah.gc.log:uptime,level,tags \
  GcSameLoadDemo results/shenandoah.jfr > results/shenandoah.stdout
~~~

**Các lệnh trên nên chạy tuần tự**, không cùng lúc trên một host nhỏ; nếu chạy đồng thời, collector tranh CPU/memory/disk và kết quả không độc lập. Các file kết quả phải được đặt tên riêng cho từng collector/run; tránh ghi đè file kết quả cũ.

**Dữ liệu checksum cố định đã kiểm chứng** trên OpenJDK 21.0.12.1:

~~~text
warmupRounds=8
measuredRounds=40
allocationsPerRound=50000
bytesPerRound=35200000
checksum=1917499200
~~~

Trong phép thử cả ba collector đều in **checksum = 1.917.499.200**. Nếu một run không cho checksum tương tự, hãy kiểm vì sao công việc/đầu ra khác trước khi so latencies.

Những dòng sau thay đổi theo môi trường:

~~~text
batchP50Ms=...
batchP95Ms=...
batchMaxMs=...
measuredRoundsPerSecond=...
collectorBean=...
~~~

Đây là mẫu output rút gọn để chỉ loại thông tin, **không phải stdout cố định**. Các số đo microseconds/milliseconds thay đổi bởi JIT, OS scheduler, GC, allocation pressure và background jobs.

## 9. Bộ đọc Java 11: tính GC pause p50, p95 và maximum từ JFR

`jdk.GCPhasePause` ghi các giai đoạn GC pause. **Không cộng `jdk.GCPhasePauseLevel1/2/...` cùng parent event nếu mục tiêu là pause chính**, vì có nguy cơ đếm trùng thời gian của các pha con.

Để so cùng tiêu chí, parser chỉ nhận event có **tên chính xác `jdk.GCPhasePause`** rồi lấy duration từ `RecordedEvent.getDuration().toNanos()`.

### File `GcPauseFromJfr.java`

~~~java
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Locale;

public class GcPauseFromJfr {
    private static double percentileMs(
            ArrayList<Long> values, double fraction) {
        int pos = (int) Math.ceil(fraction * values.size()) - 1;
        return values.get(Math.max(0, pos)) / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        ArrayList<Long> pauses = new ArrayList<>();
        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent e = file.readEvent();
                if ("jdk.GCPhasePause".equals(
                        e.getEventType().getName())) {
                    pauses.add(e.getDuration().toNanos());
                }
            }
        }

        Collections.sort(pauses);
        System.out.println("gcPauseEvents=" + pauses.size());
        if (!pauses.isEmpty()) {
            System.out.printf(Locale.ROOT, "gcPauseP50Ms=%.3f%n",
                    percentileMs(pauses, 0.50));
            System.out.printf(Locale.ROOT, "gcPauseP95Ms=%.3f%n",
                    percentileMs(pauses, 0.95));
            System.out.printf(Locale.ROOT, "gcPauseMaxMs=%.3f%n",
                    percentileMs(pauses, 1.0));
        } else {
            System.out.println("gcPauseStats=NOT_AVAILABLE_IN_RECORDING");
        }
    }
}
~~~

### Chạy parser và công cụ JFR

~~~bash
javac --release 11 GcPauseFromJfr.java

jfr summary results/g1.jfr
jfr summary results/zgc.jfr
jfr summary results/shenandoah.jfr

java GcPauseFromJfr results/g1.jfr
java GcPauseFromJfr results/zgc.jfr
java GcPauseFromJfr results/shenandoah.jfr
~~~

Nếu JVM không hỗ trợ một collector, không có file JFR hợp lệ để phân tích cho nó. **Không thay “collector không chạy được” bằng số 0 ms.**

**Thiết kế bộ đọc:** vòng lặp `RecordingFile.hasMoreEvents()/readEvent()` đọc streaming thay vì `readAllEvents()` đưa toàn bộ recording vào RAM. Các duration đã lọc được sort rồi tính percentile theo **nearest-rank**. Khi không có pause event, parser in `NOT_AVAILABLE_IN_RECORDING` thay vì chia cho 0 hoặc giả định GC pause bằng 0.

Dùng CLI để kiểm sự kiện thật:

~~~bash
jfr print --events jdk.GCPhasePause results/g1.jfr
jfr print --events jdk.GCPhasePause results/zgc.jfr
jfr print --events jdk.GCPhasePause results/shenandoah.jfr
~~~

**JFR file là dữ liệu nhị phân**, không phải text log. Đừng dùng `Files.readString(...)` để phân tích. Đối với file production, nên đọc từ nguồn đáng tin, có giới hạn file size, quyền truy cập và retention.

## 10. Kết quả đã đo thực tế trên cùng môi trường

**Môi trường thử:** OpenJDK **21.0.12.1**, Linux, một container host, cùng `-Xms256m -Xmx256m -XX:ActiveProcessorCount=2`, cùng binary Java 11-compatible, cùng load, cùng `jdk.GCPhasePause` threshold 0 và cùng JFR recording window.

Workload của mỗi collector:

~~~text
8 warm-up rounds
40 measured rounds
50,000 byte-array allocations / measured round
35,200,000 requested payload bytes / round
checksum = 1,917,499,200 (identical)
~~~

**Bảng dưới là một lần chạy cụ thể. Không coi đó là thứ hạng hiệu năng áp dụng cho mọi workload hoặc JDK.**

| Chỉ số | G1 | Generational ZGC | Shenandoah |
| --- | ---: | ---: | ---: |
| Số measured rounds | 40 | 40 | 40 |
| Checksum | 1.917.499.200 | 1.917.499.200 | 1.917.499.200 |
| GC pause events | 10 | 63 | 22 |
| GC pause p50 (ms) | 2,321 | 0,004 | 0,010 |
| **GC pause p95 (ms)** | **3,354** | **0,009** | **0,036** |
| GC pause max (ms) | 3,354 | 0,225 | 0,220 |
| Batch latency p50 (ms) | 1,963 | 2,137 | 29,946 |
| **Batch latency p95 (ms)** | **8,575** | **8,423** | **60,485** |
| Batch latency max (ms) | 10,750 | 8,887 | 60,596 |
| Measured rounds/s | 288,43 | 326,74 | 33,26 |

Các số thập phân trong bảng được viết bằng dấu phẩy theo thông lệ Việt Nam; chương trình Java sử dụng `Locale.ROOT` nên stdout dùng dấu chấm.

### Diễn giải kết quả đúng cách

- **GC pause p95 thấp hơn nhiều ở ZGC/Shenandoah** trong lần chạy thử, phù hợp mục tiêu của collector concurrent.
- **Application batch p95 không giảm theo cùng tỷ lệ với GC pause.** Việc thu gom concurrent tiêu tốn CPU, còn batch duration phụ thuộc tất cả hoạt động của ứng dụng và OS.
- **Shenandoah rất chậm ở throughput của phép thử synthetic nhỏ, heap 256 MB và chỉ 2 CPU logic cho JVM.** Điều này **không chứng minh Shenandoah luôn chậm**; một workload nhiều CPU, live set khác hoặc generational mode JDK mới có thể cho kết quả khác.
- **ZGC có 63 pause events nhưng không phải 63 GC cycles.** Một collector có thể có nhiều pause phases trong một cycle. Cần dùng GC logs/JFR cycle events để phân biệt.
- **40 batch samples và 10–63 pause events quá ít để tuyên bố production p99.** Giá trị p95/max có độ dao động cao.

### Kết quả lặp lại minh họa mức nhiễu

Thử thêm hai cặp chạy G1/ZGC trên cùng môi trường, checksum vẫn **1.917.499.200** nhưng latency/throughput thay đổi:

| Lần chạy | Collector | Batch p95 (ms) | Rounds/s | GC pause p95 (ms) |
| --- | --- | ---: | ---: | ---: |
| 2 | ZGC | 5,838 | 371,42 | 0,008 |
| 2 | G1 | 7,731 | 330,09 | 2,970 |
| 3 | ZGC | 6,625 | 345,42 | 0,011 |
| 3 | G1 | 7,753 | 297,75 | 4,399 |

**Điều cần học:** không chọn một lần chạy nhanh nhất làm “benchmark result”. Số liệu workload nhỏ dao động ngay cả khi cùng source và checksum; báo cáo production cần nhiều independent runs và dữ liệu tải thực.

## 11. Đọc GC log và JFR đúng ngữ nghĩa

### Unified logging (Java 11+)

`-Xlog:gc:file=...:uptime,level,tags` tạo GC logs. Khi cần biết thêm các phase/heap occupancy, có thể dùng logging chi tiết hơn:

~~~bash
java -XX:+UseG1GC -Xms256m -Xmx256m \
  -Xlog:gc*=info:file=results/g1-detail.log:uptime,level,tags \
  GcSameLoadDemo results/g1-detail.jfr
~~~

Đây là ví dụ cho G1. Khi so chặt chẽ, đảm bảo verbosity/log IO tương đương giữa collectors, hoặc đo riêng overhead logging. GC log có thông tin warm-up và measured; **JFR trong code chỉ chứa measured window**.

**Không parse mọi dòng có chữ “GC” thành pause**. Với các concurrent collectors, log chứa phases đang chạy đồng thời và nhiều loại records. Format log thay đổi theo JDK/collector, cần hiểu schema/phase từng collector hoặc dùng phân tích JFR `jdk.GCPhasePause` có chọn lọc.

### `jdk.GarbageCollection` khác `jdk.GCPhasePause`

`jdk.GarbageCollection` giúp biết GC cycles. Nhưng **duration của concurrent GC cycle không tương đương tổng stop-the-world pause**. Dùng `GCPhasePause` cho pause duration, và ghi nhận có thể có **nhiều pause phases/cycle**. Nếu cần tổng thời gian ứng dụng bị dừng trong một cycle, nhóm đúng các phase theo `gcId` và chỉ tính những non-overlapping pause intervals phù hợp, tránh đếm lặp nested levels.

### Bổ sung application SLO

Một hệ thống thực có thể cần:

~~~text
Successful RPS >= mục tiêu được thống nhất
End-to-end request p99 <= SLO
Error rate <= error budget
Peak RSS <= container memory budget
GC pause p99 và total pause time được theo dõi
Không có allocation stalls/GC fallback gây outlier nghiêm trọng
~~~

Đây là **khung mục tiêu**, không phải các chỉ tiêu đã được chứng minh bởi demo. **GC pause không phải toàn bộ request latency**: queuing, lock contention, I/O, network, DB, thread scheduling, CPU starvation và application logic đều ảnh hưởng.

## 12. Hai vòng so sánh: baseline và cấu hình tối ưu

### Vòng 1: cố định tài nguyên, chỉ đổi collector

- Dùng cùng code, workload, dataset, JDK, `-Xms/-Xmx`, CPU quota và JFR settings.
- Để collector-specific tuning ở mặc định khi có thể.
- Ghi P50/P95/max GC pause, request/batch latency, throughput, CPU/RSS và errors.
- Xác định collector nào đáp ứng SLO **trong cùng ngân sách** trước khi tuning sâu.

### Vòng 2: tuning riêng để đạt SLO/cost

- **G1:** cân nhắc heap/`-XX:MaxGCPauseMillis` mềm; phân tích Full GC/humongous regions và đừng vô hiệu pause adaptation bằng fixed young size không cần thiết.
- **ZGC:** cân nhắc heap headroom, concurrent GC CPU, allocation spikes và memory uncommit. Đừng thu hẹp heap quá mức để “giảm RSS” nếu tăng allocation stalls.
- **Shenandoah:** kiểm heuristics và mode **thực sự có trên JDK đang dùng**; đo trade-off concurrent CPU, throughput và memory budget.
- **Tất cả:** đo dưới các peak loads thực tế, theo SLO và cost/instance thay vì một con số pause đẹp.

Vòng hai so **“best tuned configuration within the same cost/SLO budget”** chứ không còn “chỉ thay cờ collector”. Báo cáo phải phân biệt hai cách so này.

## 13. Các nguồn sai lệch và cách giảm

### CPU và noisy neighbors

Concurrent GC cần CPU trong khi mutator threads cũng cần. CPU quota, thermal throttling, frequency scaling, host load hoặc cạnh tranh I/O làm kết quả khác nhau. Chỉ dùng `ActiveProcessorCount` không phải cô lập. Với benchmark nghiêm ngặt, kiểm cpuset, cgroup metrics, CPU throttling và bối cảnh máy.

### Heap headroom và live set

Heap chật có thể dẫn tới allocation stalls/GC fallback, ngay cả khi những pauses bình thường rất ngắn. Một workload có live set cao hoặc humongous objects có thể cho kết quả khác benchmark arrays ngắn sống trong ring buffer. Cần thử cả steady state và spikes, không chỉ 256 MB/demo.

### Warm-up, JIT và cache

Cùng 8 warm-up rounds chưa chắc đã tới steady state với mọi JVM và collector. JIT compile có thể diễn ra trong measured window. Trên production-like load test, warm-up đủ lâu, đo nhiều runs và xem JFR/JIT/GC timeline.

### Thống kê ít mẫu và tail

`p95` của 40 batches tính nearest-rank là phần tử thứ `ceil(0.95*40)=38` sau sort. Một outlier GC hoặc OS scheduling có thể thay đổi đáng kể p95. Một `p95` tính trên 10 GC pauses cũng không đại diện cho service hoạt động nhiều giờ. Tăng số samples và runs; phân biệt **max observed** và **SLO percentile**.

### JDK/mode không tương đương

JDK 21 Generational ZGC cần `-XX:+ZGenerational`, nhưng JDK24+ đã bỏ flag. Shenandoah JDK21 và Generational Shenandoah JDK25 khác mode. **Không đặt các kết quả từ hai JDK khác nhau vào cùng bảng rồi quy sự khác biệt chỉ do GC**.

### Tính đúng nghiệp vụ

Nhanh hơn vì xử lý thiếu request, drop dữ liệu, nhiều timeout hoặc OOM không phải cải thiện. So số request thành công, responses và side effects; checksum demo chỉ là một tín hiệu consistency đơn giản.

## 14. Chạy lặp và lập báo cáo

Một sơ đồ thử nghiệm:

~~~text
Chuẩn bị một JDK, máy, data, CPU/heap budget
                |
        warm-up -> G1 run 1
        warm-up -> ZGC run 1
        warm-up -> Shenandoah run 1
                |
        warm-up -> Shenandoah run 2
        warm-up -> ZGC run 2
        warm-up -> G1 run 2
                |
       ... lặp AB/BA/ABBA để giảm order bias
                |
   so từng run + tổng hợp phân phối + quyết định SLO
~~~

Đừng chạy ba JVM cạnh tranh cùng tài nguyên khi mục tiêu là **đo độc lập**. Đảo thứ tự qua nhiều lần giúp giảm thiên lệch do thứ tự chạy, nhưng không thay thế khả năng cô lập tải/CPU.

Một bảng kết quả đầy đủ nên lưu:

| Nhóm metadata | Nội dung |
| --- | --- |
| Version/mode | Collector, JDK vendor/build, generational mode |
| Hardware | CPU model/cores, NUMA, RAM, OS/kernel |
| Limits | Heap, CPU quota/cpuset, container memory |
| Workload | Dataset/seed, request mix, allocation rate, live set, concurrency |
| Recording | JFR settings, event types/threshold, warm-up và measured window |
| Correctness | Checksum, successful responses, errors, timeouts, OOM |
| Pause | GC pause count, p50/p95/max, total pause time, cycles/stalls |
| App | Request/batch p50/p95/p99, throughput |
| Cost | CPU use, peak RSS/native memory, memory headroom |
| Conclusion | Meets SLO? Repeatable? Trade-offs? Rollback plan? |

Khi kết quả không ổn định, điều tra allocation spikes, GC phases, CPU throttling, JIT, cache, background jobs và load generator trước khi gán nguyên nhân.

## 15. Những sai lầm hay gặp

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| ZGC pause thấp nhất thì app chắc nhanh nhất | Concurrent work/CPU/heap trade-off | Đo cả application latency/throughput |
| So tổng pause events thay cho GC cycles | Một cycle có nhiều phases | Phân biệt phase count/cycle count |
| Cộng duration `jdk.GarbageCollection` làm STW | GC cycle có concurrent work | Dùng `jdk.GCPhasePause` |
| Cộng `GCPhasePauseLevel1/2` vào parent | Đếm lặp nested intervals | Chọn event type đúng |
| Không có pause event nghĩa là 0 ms | Có thể không GC hoặc không ghi | In NOT_AVAILABLE, kéo dài ghi |
| Đổi code, heap, JDK cùng lúc | Không biết yếu tố gây chênh lệch | Chỉ thay GC ở vòng baseline |
| `-Xmx` bằng nhau nghĩa là RSS bằng nhau | Native/metadata/threads khác nhau | Đo peak RSS và container memory |
| `-XX:ActiveProcessorCount=2` pin 2 cores | Chỉ thay JVM ergonomics | Kiểm cpuset/quota/CPU contention |
| `-XX:MaxGCPauseMillis` bảo đảm cứng | G1 pause target là soft goal | Kiểm p95/p99 thực tế |
| Ép `System.gc()` để so GC | Thay workload và collector behavior | Tạo tải cấp phát thực |
| Một lần chạy đẹp nhất là kết luận | Outliers/JIT/OS nhiễu | Nhiều runs và đảo thứ tự |
| G1 JDK21 vs ZGC JDK25 “cùng điều kiện” | JVM/algorithm khác | Dùng cùng JDK build |
| Gắn `-XX:+ZGenerational` trên JDK25 | Flag đã bị loại ở JDK24 | Chỉ `-XX:+UseZGC` |
| Shenandoah không có trên build nhưng vẫn tạo bảng | Collector không chạy | Kiểm availability |
| Chỉ 40 samples mà báo production p99 | Tail không ổn định | Nhiều samples và load thật |
| Nhanh hơn nhưng checksum/response sai | Benchmark không có ý nghĩa | Correctness bắt buộc |
| GC logs có warm-up, JFR chỉ measured mà không ghi rõ | Cửa sổ khác nhau | Ghi rõ recording window |
| File JFR không nhạy cảm | Có metadata/stack/path thông tin | Giới hạn quyền và retention |

## 16. Checklist trước khi thay collector trong sản xuất

- [ ] Có **latency SLO**, throughput target, error budget và cost/CPU/memory budget.
- [ ] Đã thu baseline G1 dưới workload đại diện.
- [ ] Các collector candidate có trên đúng JDK/vendor/build và cờ được hỗ trợ.
- [ ] Ghi đúng mode Generational ZGC/Shenandoah theo JDK.
- [ ] Giữ cùng code, input, số công việc, concurrency và live set.
- [ ] Giữ cùng JDK, heap/cpu limit, hardware, warm-up và measurement window.
- [ ] Không ép `System.gc()` hoặc chỉ chạy một micro-workload không đại diện.
- [ ] JFR ghi `jdk.GCPhasePause` với cùng threshold trong đúng cửa sổ đo.
- [ ] GC log được phân tích theo collector, không nhầm cycle/concurrent với STW.
- [ ] So GC pause p50/p95/max và total pause time **cùng application p50/p95/p99**.
- [ ] So throughput, errors/timeouts/OOM, peak RSS, CPU, allocation stalls.
- [ ] Kết quả nghiệp vụ/response/checksum giống nhau.
- [ ] Có nhiều runs, đảo thứ tự và báo biến thiên, không chỉ run tốt nhất.
- [ ] Nếu tuning riêng, báo rõ baseline-vs-best-tuned là hai phép thử khác nhau.
- [ ] Có canary, monitoring và rollback khi đổi collector production.
- [ ] Bảo vệ file JFR/GC logs, không công khai thông tin nhạy cảm.

**Kết luận:** GC phù hợp nhất được quyết định bởi **SLO của ứng dụng trên phần cứng và tải thực**, không chỉ bởi p95 GC pause. Hãy giữ workload/JDK/heap/CPU budget như nhau ở vòng so đầu, ghi nhận đúng GC pause qua JFR, nhưng luôn kiểm **application latency, throughput, CPU, RSS và correctness**. **Pause rất thấp vẫn có thể đi cùng throughput kém** nếu concurrent collector không phù hợp ngân sách tài nguyên hoặc workload. Chỉ chọn sau khi đo nhiều lần, đúng mode và có rollback plan.

## Tài liệu chính thức hiện còn áp dụng

- [Oracle Java SE 25 — Available Collectors](https://docs.oracle.com/en/java/javase/25/gctuning/available-collectors.html): khuyến nghị chọn G1/ZGC/Parallel.
- [Oracle Java SE 25 — G1 Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): pause target mềm và throughput trade-off.
- [Oracle Java SE 21 — ZGC Tuning](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html): Generational ZGC trong JDK21.
- [OpenJDK JEP 439 — Generational ZGC](https://openjdk.org/jeps/439): JDK21.
- [OpenJDK JEP 490 — Remove Non-Generational ZGC](https://openjdk.org/jeps/490): JDK24 loại bỏ `ZGenerational` option.
- [OpenJDK JEP 379 — Shenandoah Production](https://openjdk.org/jeps/379): Shenandoah product feature từ JDK15.
- [OpenJDK JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): generational mode trên JDK mới.
- [Oracle Java SE 11 — The java Command](https://docs.oracle.com/en/java/javase/11/tools/java.html): `-Xlog` và các JVM flags hiện hành.
- [Oracle Java SE 25 — Troubleshooting GC using JFR](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): `jdk.GCPhasePause` và pause analysis.
- [Oracle Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): `enable`, `start`, `stop`, `dump`.
- [Oracle Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): streaming JFR file reader.
- [Oracle Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): duration events.
- [Oracle Java SE 25 — GC Implementation](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-collector-implementation.html): GC logs, throughput và footprint.

Bài chỉ dùng **kiến thức Java 11+ còn áp dụng**, không khuyến nghị legacy JVM/GC flags. Mã Java đã được **biên dịch bằng `javac --release 11`** và thực thi với G1, Generational ZGC, Shenandoah trên cùng OpenJDK 21; các giá trị thời gian chỉ là ví dụ đo được trên một môi trường, không phải cam kết cho hệ thống khác.