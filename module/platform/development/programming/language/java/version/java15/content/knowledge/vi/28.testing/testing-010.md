# Kiểm thử GC dưới tải ổn định, tải tăng và bộ nhớ giới hạn (Java hiện hành)

> **Ngữ cảnh:** Kiểm thử ứng dụng Java có cấp phát đối tượng liên tục. Phạm vi dùng các cơ chế vẫn còn được hỗ trợ ở JDK 17+ và các JDK hiện hành: G1 GC, Unified JVM Logging (`-Xlog`), Java Flight Recorder (JFR), các MXBean quản lý JVM, giới hạn heap bằng `-Xmx`, và ý thức về giới hạn bộ nhớ tiến trình/container. **GC dưới tải** phải được đánh giá cùng hiệu năng ứng dụng và mức dùng bộ nhớ, không chỉ bằng một con số “GC chạy bao nhiêu lần”.

## 1. Mục tiêu kiểm thử và các khái niệm cốt lõi

Garbage collection (GC) giúp JVM thu hồi phần heap của các đối tượng **không còn truy cập được** từ các GC roots. GC không có nhiệm vụ thu hồi đối tượng vẫn đang được ứng dụng giữ tham chiếu; vì vậy một ứng dụng giữ ngày càng nhiều dữ liệu không dùng nữa vẫn có thể hết heap dù collector hoạt động đúng.

Các khái niệm cần phân biệt:

- **Heap used:** lượng heap đang sử dụng tại thời điểm đo; thường tăng khi cấp phát rồi giảm sau các đợt thu hồi. Một đồ thị răng cưa là điều bình thường.
- **Live set:** phần dữ liệu vẫn còn truy cập được và cần giữ lại; độ lớn live set quyết định lượng heap tối thiểu collector không thể giải phóng.
- **Allocation rate:** số byte đối tượng mới được cấp phát mỗi giây, ví dụ MiB/s; khác với live set. Một dịch vụ có thể cấp phát rất nhanh nhưng chỉ giữ rất ít đối tượng sống.
- **GC pause:** thời gian các luồng ứng dụng bị tạm dừng trong một pha stop-the-world. Không đồng nhất tổng thời gian GC hoặc thời gian collector chạy đồng thời với tổng thời gian dừng ứng dụng.
- **Application latency/throughput:** thời gian đáp ứng p50/p95/p99 và lượng tác vụ hoàn thành/giây, là chỉ số tác động tới người dùng. Một pause ngắn có thể ảnh hưởng nhiều request, nhưng GC pause p99 **không bằng** request latency p99.
- **Heap committed/reserved/used:** bộ nhớ đã cam kết, không gian địa chỉ dành trước và lượng dùng hiện tại là những số khác nhau. Heap used nhỏ hơn `-Xmx` không chứng minh tiến trình còn đủ native memory.
- **RSS/container memory:** bộ nhớ vật lý tiến trình/container tiêu thụ, bao gồm thêm metadata, thread stacks, code cache, direct buffers, native allocations và các thành phần khác ngoài Java heap.

**Giả thuyết để kiểm thử:** dưới tải ổn định hệ thống giữ thông lượng/độ trễ trong ngưỡng chấp nhận; khi tải tăng, GC có thể diễn ra nhiều hơn nhưng dịch vụ vẫn phải thỏa SLA/SLO trong vùng công suất dự kiến; với bộ nhớ bị giới hạn, phải xác định điểm giảm hiệu năng hoặc thất bại và kiểu thất bại thực sự.

## 2. Ba tình huống cần kiểm thử

| Tình huống | Điều khiển tải | Cần quan sát | Dấu hiệu bất thường |
| --- | --- | --- | --- |
| **Ổn định (steady)** | Số request/s, số người dùng đồng thời hoặc lượng cấp phát/giây gần như không đổi sau warm-up | Throughput đạt mục tiêu; response-time p95/p99 ổn; GC pause và heap sau GC không có xu hướng xấu kéo dài | Full GC liên tiếp, p99 vượt SLO, heap sau GC tăng dần không giải thích được, CPU bão hòa |
| **Tải tăng (ramp)** | Tăng tải theo bước, ví dụ 8 → 16 → 32 MiB cấp phát/s hoặc các mức requests/s | Điểm bắt đầu GC dày hơn; giới hạn công suất; sự tăng của queue, CPU, pause và latency | Throughput không tăng theo offered load, tail latency phình mạnh, backlog lớn, lỗi/timeout |
| **Bộ nhớ giới hạn (memory-constrained)** | Cố định tải, giảm `-Xmx` hoặc giới hạn container; kiểm soát live set | GC có đủ khoảng trống để copy/thu hồi hay không; áp lực old generation; RSS và OOM | Allocation stall, repeated Full GC, `OutOfMemoryError`, container OOM kill, lỗi native memory |

Các kịch bản này chỉ so sánh được nếu **cùng code, JDK, collector, số CPU, môi trường, dữ liệu đầu vào, cách đo**, và có warm-up tương đương. Không đổi cả collector, heap và tải trong cùng một phép thử rồi kết luận nguyên nhân.

### Thiết lập một cuộc thử nghiệm có giá trị

1. Chọn workload gần thực tế: tỷ lệ đọc/ghi, kích thước payload, lượng đối tượng sống, số worker, connection pool và mẫu request. Tải **offered** phải được đo riêng với throughput **completed**.
2. Xác định ngân sách: heap tối đa, CPU, RAM/container limit, mức SLA/SLO (ví dụ p99 dưới ngưỡng của hệ thống), giới hạn lỗi và điều kiện dừng an toàn.
3. Có ít nhất hai giai đoạn: **warm-up** để JIT/cache/connection pool đạt trạng thái tương đối ổn định; **measurement** kéo dài đủ để thấy chu kỳ GC, không chỉ vài giây.
4. Ghi đồng thời metrics ứng dụng, JVM, OS/container và log; dùng cùng mốc thời gian hoặc dấu phase để đối chiếu.
5. Lặp lại nhiều lần trên môi trường ít nhiễu; so sánh phân phối, không chỉ một lần chạy.
6. Giữ phiên bản JDK cố định trong một phép so; nếu nâng JDK, tạo baseline mới vì GC ergonomics có thể đổi.

## 3. G1 GC là baseline phù hợp

G1 là collector mặc định của HotSpot trên cấu hình phổ biến, kể cả các JDK hiện hành. Nó hoạt động theo vùng (regions), có các pha thu hồi young/mixed, có công việc concurrent và các khoảng stop-the-world pause. Mục tiêu `-XX:MaxGCPauseMillis` của G1 là **mục tiêu điều chỉnh**, không phải cam kết cứng rằng mọi pause ngắn hơn ngưỡng.

Với phép thử baseline, có thể dùng `-XX:+UseG1GC` để xác định rõ collector đang dùng. Sau đó mới thử collector khác nếu có yêu cầu latency/throughput cụ thể và bản phân phối JDK hỗ trợ. ZGC là một lựa chọn hiện hành cho mục tiêu pause rất thấp; nó có trade-off về CPU, heap headroom và throughput, nên **không mặc định tốt hơn** với mọi tải. Shenandoah cũng chỉ được thử khi bản JDK cung cấp hỗ trợ. Tránh tái sử dụng các tuning flag cũ từ bài viết về CMS/GC logging đời cũ.

Một thay đổi của G1 cần hiểu khi đọc log:

- **Young GC** thường thu hồi đối tượng sống ngắn, nhất là khi cấp phát nhiều.
- **Concurrent marking/mixed collections** giúp xử lý các vùng old có thể thu hồi; chi tiết thay đổi theo phiên bản JDK.
- **Full GC** có thể xuất hiện trong tình huống áp lực bất thường và làm thời gian dừng tăng; cần đọc **GC cause** và các dòng lân cận, không chỉ lọc số lần.
- **Humongous allocations** (đối tượng rất lớn so với kích thước region) có thể gây áp lực khác với việc tạo nhiều mảng nhỏ. Tình huống này nên là một biến thử riêng.
- Khi live set gần mức heap tối đa, tăng tần suất GC không đồng nghĩa sẽ thu hồi đủ: những đối tượng còn được tham chiếu vẫn phải giữ lại.

## 4. Chỉ số tối thiểu và cách diễn giải

| Metric | Thu thập | Cách hiểu / lưu ý |
| --- | --- | --- |
| Request throughput, offered vs completed | Load generator và service metrics | Nếu offered tăng mà completed đứng yên, có thể đang chạm giới hạn công suất; GC chỉ là một trong các nguyên nhân |
| Response time p50/p95/p99, error/timeout | Metrics ứng dụng hoặc công cụ load | So theo từng phase và cửa sổ thời gian; kiểm tra cùng CPU/queue/I/O |
| Heap used, committed và max; live set ước tính | JMX/MXBean, JFR, GC log | Heap used tức thời nhấp nhô; xem xu hướng sau các lần GC tương đương, sau warm-up |
| Allocation rate và allocation hot spots | JFR allocation sampling; metrics ứng dụng | Rate cao làm GC thường xuyên hơn; sampling là **ước lượng**, không phải đo chính xác mọi byte |
| GC pause duration, count, cause | `-Xlog:gc*`, JFR GC events | Tổng và p95/p99 pause giúp so sánh; phân biệt pause với thời gian concurrent |
| Full GC, evacuation failure, allocation failure | GC log cụ thể theo collector | Đọc bản ghi ngữ cảnh của từng failure; đừng coi mọi GC là vấn đề |
| CPU process/GC threads, run queue | OS, profiler/JFR | Nhiều GC background có thể tiêu thụ CPU dù pause nhỏ |
| RSS, memory limit, container OOM events | OS/container metrics | Java heap không bao gồm toàn bộ bộ nhớ tiến trình |
| Time in GC / mutator utilization | Tính từ pause log và elapsed time, có định nghĩa rõ | Tỉ lệ pause STW = tổng duration các pause STW không chồng lấp / wall time; không cộng trùng pha con |

**Đọc đồ thị đúng cách:** Nếu heap đã warm-up, dao động trong một dải và các chỉ số SLO ổn định, số lần Young GC tăng theo allocation rate có thể là hành vi lành mạnh. Nếu sau mỗi lần thu hồi mức heap thấp nhất tiếp tục tăng, hãy kiểm tra cache, queue, dữ liệu bị giữ và khả năng memory leak bằng JFR/heap analysis; chưa thể kết luận leak chỉ từ một đường tăng.

Một dấu hiệu giảm hiệu năng rõ là **GC chiếm ngày càng nhiều tài nguyên nhưng throughput ứng dụng không tăng**. Tuy nhiên, cần loại trừ CPU bão hòa vì business logic, I/O, locks, cache miss và load generator thiếu công suất.

## 5. Chương trình Java độc lập để tái tạo ba chế độ tải

Ví dụ dưới đây tạo hai loại allocation: một **live set có thể điều chỉnh** được giữ bằng tham chiếu mạnh, và một lượng mảng mới được tạo đều theo MiB/s rồi dần bị thay thế trong ring. Dùng mảng `byte[16 * 1024]` để giữ thí nghiệm đơn giản và tránh tự tạo những đối tượng khổng lồ. Một giây thử được chia thành nhiều batch ~1 MiB để tránh dồn tất cả allocation vào đầu giây.

**Lưu thành tệp `GcLoadStudy.java`**. Chương trình chạy bằng Java 17+; các lệnh và giá trị được minh họa trên HotSpot. Nó kiểm soát **tốc độ cấp phát nhắm tới**, không giả vờ là bộ tạo request thật. `gcCountDelta` là số đếm từ GC MXBeans nếu collector hỗ trợ, **không phải tổng thời gian pause**; để phân tích chính xác pause phải xem log/JFR.

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Locale;
import java.util.concurrent.locks.LockSupport;

public final class GcLoadStudy {
    private static volatile byte[][] longLived;
    private static final byte[][] shortLivedRing = new byte[64][];
    private static volatile byte sink;

    private static long gcCount() {
        long total = 0;
        for (GarbageCollectorMXBean gc : ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = gc.getCollectionCount();
            if (count >= 0) total += count;
        }
        return total;
    }

    private static void holdMiB(int liveMiB) {
        byte[][] data = new byte[liveMiB * 64][];
        for (int i = 0; i < data.length; i++) {
            data[i] = new byte[16 * 1024];
            data[i][0] = (byte) i;
        }
        longLived = data;
    }

    private static long churnForOneSecond(int rateMiB) {
        long start = System.nanoTime();
        for (int mb = 0; mb < rateMiB; mb++) {
            for (int c = 0; c < 64; c++) {
                byte[] bytes = new byte[16 * 1024];
                bytes[0] = (byte) (mb + c);
                shortLivedRing[c] = bytes;
            }
            long due = start + (mb + 1L) * 1_000_000_000L / rateMiB;
            long wait = due - System.nanoTime();
            if (wait > 0) LockSupport.parkNanos(wait);
        }
        sink = shortLivedRing[63][0];
        return System.nanoTime() - start;
    }

    public static void main(String[] args) {
        if (args.length != 4 ||
                (!args[0].equals("steady") && !args[0].equals("ramp"))) {
            throw new IllegalArgumentException(
                    "Usage: GcLoadStudy steady|ramp seconds liveMiB baseMiBPerSec");
        }
        String mode = args[0];
        int seconds = Integer.parseInt(args[1]);
        int liveMiB = Integer.parseInt(args[2]);
        int baseRateMiB = Integer.parseInt(args[3]);
        if (seconds < 1 || liveMiB < 0 || liveMiB > 1024 ||
                baseRateMiB < 1 || baseRateMiB > 128) {
            throw new IllegalArgumentException("Invalid workload size");
        }

        holdMiB(liveMiB);
        System.out.printf(Locale.ROOT, "mode=%s maxHeapMiB=%d liveMiB=%d%n",
                mode, Runtime.getRuntime().maxMemory() / (1024 * 1024), liveMiB);
        long previousGC = gcCount();
        for (int t = 1; t <= seconds; t++) {
            int stage = mode.equals("ramp") ?
                    Math.min(2, (t - 1) * 3 / seconds) : 0;
            int rate = Math.multiplyExact(baseRateMiB, 1 << stage);
            long elapsed = churnForOneSecond(rate);
            double actualRate = rate * 1_000_000_000.0 / elapsed;
            double usedMiB = ManagementFactory.getMemoryMXBean()
                    .getHeapMemoryUsage().getUsed() / 1048576.0;
            long nowGC = gcCount();
            System.out.printf(Locale.ROOT,
                    "step=%d targetMiBPerSec=%d actualMiBPerSec=%.1f heapUsedMiB=%.1f gcCountDelta=%d%n",
                    t, rate, actualRate, usedMiB, nowGC - previousGC);
            previousGC = nowGC;
        }
    }
}
```

Biên dịch (JDK 17+):

```bash
javac -encoding UTF-8 GcLoadStudy.java
```

Hai điều nên biết về harness:

- `longLived` là biến static giữ tham chiếu tới live set, nên GC **không thể** loại bỏ dữ liệu này khi còn được giữ. `shortLivedRing` giữ 64 mảng gần nhất rồi thay thế; các mảng cũ có thể trở thành garbage. Việc giữ các tham chiếu trong biến static giúp workload khó bị tối ưu thành “không cấp phát gì”.
- `LockSupport.parkNanos` giúp dàn trải tốc độ cấp phát nhưng việc đánh thức thread chỉ mang tính best-effort. Cột `actualMiBPerSec` có thể thấp hơn `targetMiBPerSec` nếu JVM/hệ thống không theo kịp; **không nên coi đạt mục tiêu nếu chỉ kiểm tra input của load generator**. `heapUsedMiB` là ảnh chụp ở cuối mỗi giây, không phải live set hay RSS.

### 5.1. Tải ổn định, heap 128 MiB

```bash
java -Xms64m -Xmx128m -XX:+UseG1GC "-Xlog:gc*,safepoint:file=gc-steady.log:uptime,level,tags" GcLoadStudy steady 30 16 24
```

Ý nghĩa các tham số: `steady`; chạy 30 giây; giữ khoảng 16 MiB dữ liệu còn tham chiếu; cấp phát mục tiêu 24 MiB/s. `-Xms64m` là mức heap ban đầu, `-Xmx128m` là tối đa. File `gc-steady.log` chứa GC/safepoint log. Hãy cho thử nghiệm thực tế chạy lâu hơn 30 giây sau warm-up nếu muốn phân tích p99 và độ ổn định.

### 5.2. Tải tăng theo ba bậc

```bash
java -Xms64m -Xmx128m -XX:+UseG1GC "-Xlog:gc*,safepoint:file=gc-ramp.log:uptime,level,tags" GcLoadStudy ramp 30 16 8
```

Trong mỗi 10 giây liên tiếp, target đổi `8 → 16 → 32 MiB/s`. Thời gian mỗi bậc trong benchmark thật phải đủ để tránh nhầm transient lúc tăng tải với steady state mới. Nếu tải làm throughput thực không còn theo kịp target, ghi nhận **điểm bão hòa** và kết hợp CPU, GC log, queue, latency để tìm nguyên nhân.

### 5.3. Bộ nhớ heap giới hạn

```bash
java -Xms64m -Xmx64m -XX:+UseG1GC "-Xlog:gc*,safepoint:file=gc-limited.log:uptime,level,tags" GcLoadStudy steady 30 40 24
```

Giữ ~40 MiB live set trong heap tối đa 64 MiB; vẫn cấp phát mục tiêu 24 MiB/s. Trong môi trường thử thực tế, mức này có thể gây GC dày, áp lực thăng cấp đối tượng hoặc OOME tùy JVM/OS và tải. **Không khẳng định 64 MiB luôn chạy thành công** chỉ dựa vào 40 MiB dữ liệu: còn object headers, mảng tham chiếu, short-lived objects và overhead của VM.

Để so sánh đúng, chạy lại cùng workload với `-Xmx128m` rồi đối chiếu log, elapsed time và các số đo khác. Đừng thay đổi live set và heap cùng lúc trong phép so đầu tiên.

### 5.4. Ví dụ đầu ra được ghi nhận trong một lượt thử ngắn

Một lần chạy OpenJDK 24 trên máy thử (chỉ 2 hoặc 3 giây để kiểm tra chương trình và cờ JVM, **không đủ để kết luận SLO**) cho:

```text
mode=steady maxHeapMiB=128 liveMiB=16
step=1 targetMiBPerSec=24 actualMiBPerSec=24.0 heapUsedMiB=27.0 gcCountDelta=1
step=2 targetMiBPerSec=24 actualMiBPerSec=24.0 heapUsedMiB=32.7 gcCountDelta=1
```

Một lượt `ramp 3 16 8` lần lượt có target `8`, `16`, `32` MiB/s; một lượt `steady 2 40 24` với `-Xmx64m` cũng kết thúc thành công trên cùng máy thử, nhưng tăng số lượng GC. **Số liệu GC, heap used và actual rate không có stdout cố định**; khác nhau giữa các phiên bản JDK, cấu hình CPU, tốc độ máy và mỗi lần chạy. Không được viết test unit “assert `gcCountDelta == 1`”.

## 6. Ghi và đọc GC log bằng công cụ hiện hành

Từ JDK 9 trở đi, Unified Logging là cách được hỗ trợ để ghi thông tin GC: `-Xlog:gc` ở mức cơ bản; `-Xlog:gc*` lấy thêm các tag GC liên quan; có thể bổ sung `safepoint` cho các lần dừng vì lý do khác GC. Ví dụ có log rotation:

```bash
java -Xms64m -Xmx128m "-Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M" GcLoadStudy steady 60 16 24
```

Đây là cú pháp của Unified Logging trên Java hiện hành. `time` cho thời gian lịch, `uptime` cho thời gian từ lúc JVM khởi động; dùng dấu phase hoặc timestamp để đối chiếu với biểu đồ ứng dụng. Việc ghi chi tiết hơn có overhead, vì vậy giữ cùng mức log cho mọi kịch bản so sánh.

Khi đọc log, cần xác định:

1. Collector thực tế và heap max; xác nhận cờ đầu vào đã áp dụng (không chỉ tin câu lệnh chạy).
2. Số sự kiện GC, **loại GC** (young/mixed/full hoặc thuật ngữ của collector đang dùng), nguyên nhân, heap trước/sau, thời lượng pause.
3. Sự kiện bất thường như allocation/evacuation failure, Full GC liên tục, heap sau GC không giảm được, pause kéo dài khi live set lớn.
4. Thời gian log tương ứng với các bước tăng tải và với p99/error của ứng dụng.

Một dòng chứa `Pause Young` không tự chứng minh hệ thống bị nghẽn. Cần đọc **thời lượng** và kết quả thu hồi, so với SLO cùng thời điểm. Không đoán “Full GC” chỉ từ biến động heap used.

Các cờ cũ như `-XX:+PrintGCDetails` hoặc `-Xloggc` không nên dùng cho tài liệu Java hiện hành; dùng `-Xlog`. Không ép `System.gc()` để tạo “dữ liệu kiểm thử GC thực tế”; đó là một yêu cầu GC mang tính nhân tạo, có thể thay đổi hành vi theo collector/cờ, không đại diện áp lực workload.

## 7. Dùng JFR để nhìn GC cùng allocation và CPU

JFR là bộ ghi sự kiện JVM được hỗ trợ trong JDK hiện đại. Để thu một recording cho một lượt thử:

```bash
java -Xms64m -Xmx128m "-XX:StartFlightRecording=filename=gc-steady.jfr,settings=profile,dumponexit=true" GcLoadStudy steady 60 16 24
```

Sau khi JVM thoát:

```bash
jfr summary gc-steady.jfr
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary gc-steady.jfr
```

Có thể mở file `gc-steady.jfr` bằng JDK Mission Control để đối chiếu GC, allocation sampling, CPU và thread activity theo thời gian. Mỗi phiên bản JDK và cấu hình recording có bộ event khác nhau; dùng `jfr summary` để xác nhận sự kiện **thực sự được thu** trước khi suy luận từ một event vắng mặt.

Đối với JVM đang chạy, có thể dùng `jcmd -l` để tìm PID rồi:

```bash
jcmd <PID> JFR.start name=gc-study settings=profile
jcmd <PID> JFR.dump name=gc-study filename=gc-study.jfr
jcmd <PID> JFR.stop name=gc-study
```

Ở ví dụ này `<PID>` là giá trị cần thay bằng PID số thật; đây là mẫu lệnh, không phải câu lệnh chạy nguyên văn. `jcmd` cần chạy trên cùng máy/container namespace phù hợp và có quyền của process. Việc thay đổi cấu hình recorder hoặc dump lúc hệ thống đang căng có overhead, nên ghi chú tác động trong kết quả thử.

**Phân tích:** xem pause duration theo thời gian, số lượng collection, kích thước heap sau GC, allocation rate và CPU. JFR hỗ trợ tìm điểm nóng allocation, nhưng sampling không ghi lại toàn bộ allocation; không dùng số mẫu để suy ra chính xác tuyệt đối từng byte nếu không có phương pháp hiệu chỉnh.

## 8. Giới hạn bộ nhớ: `-Xmx` và giới hạn container khác nhau

`-Xmx64m` chỉ giới hạn tối đa **Java heap**, không giới hạn tổng RSS/working set của tiến trình. `OutOfMemoryError: Java heap space` có nghĩa bộ cấp phát trên heap không thể đáp ứng sau các nỗ lực phù hợp, nhưng thiếu native memory, metaspace hoặc direct buffers có thể biểu hiện khác; khi hệ điều hành/container giết process do quá bộ nhớ, có thể **không có** Java stack trace OOME.

Ví dụ một container có giới hạn RAM 256 MiB: nếu heap tối đa cũng đặt 256 MiB, các phần ngoài heap vẫn cần bộ nhớ nên nguy cơ bị OOM kill. Một cấu hình `-XX:MaxRAMPercentage=60` có thể được dùng **nếu để JVM tự chọn heap tối đa theo RAM khả dụng**, nhưng giá trị 60% không phải công thức chung cho mọi service. Cần dự trù thread stacks, metaspace, code cache, JIT, direct/mapped buffers, native libraries, lưu lượng mạng và memory pressure bất thường. Khi đã chỉ định `-Xmx`, kiểm tra precedence và giá trị heap thực thay vì mặc nhiên nghĩ phần trăm sẽ thay thế nó.

Ví dụ kiểm tra các tham số JVM:

```bash
java -XshowSettings:vm -version
java -XshowSettings:system -version
java -Xlog:os+container=info -version
```

Dữ liệu `-XshowSettings:system` và log OS/container phụ thuộc hệ điều hành và cấu hình JDK; một số môi trường không có cgroup hoặc không cung cấp chi tiết. Hãy xác nhận **memory limit thực tế** của container bằng công cụ orchestration/OS tương ứng; chỉ số `Runtime.maxMemory()` giúp quan sát heap max JVM nhận được nhưng không mô tả toàn bộ giới hạn process.

Khi gặp failure, phân loại:

- Heap bị thiếu vì **live set lớn** hoặc **object retention không mong muốn**: GC không giải phóng dữ liệu còn tham chiếu; cần giảm retained state, xem queue/cache, phân tích heap.
- **Allocation rate lớn** và headroom nhỏ: GC có thể chạy dày hoặc không đủ vùng để di chuyển dữ liệu; đánh giá tăng heap, giảm allocation, điều chỉnh concurrency, tính pause/throughput.
- **OutOfMemoryError: Java heap space**: lỗi cấp phát heap, điều tra log/heap dump theo chính sách bảo mật và dung lượng đĩa.
- **Native/direct/metaspace/thread memory**: vấn đề có thể xảy ra ngay cả khi `heapUsed` thấp; kiểm tra RSS, Native Memory Tracking khi được bật từ đầu, allocator/direct buffer metrics.
- **Container OOMKilled**: xem event và exit code của runtime/container, đối chiếu memory usage; không coi là bằng chứng chắc chắn do chính GC.

Không cố “sửa” áp lực bộ nhớ bằng các cờ GC tùy tiện khi chưa xác định loại memory bị giới hạn và workload giữ bao nhiêu dữ liệu sống.

## 9. Kế hoạch kiểm thử thực tế cho dịch vụ Java

Đối với backend nhận HTTP request hoặc xử lý message, harness ở phần 5 chỉ giúp **tách riêng** tác động allocation/live set. Muốn kết luận về dịch vụ cần load generator phát request thật, ví dụ Gatling, JMeter hoặc k6 (lựa chọn công cụ tùy stack); đo **offered rate**, completed RPS/TPS, throughput dữ liệu, retry, queue depth và error rate.

Ví dụ ma trận tối thiểu để thảo luận thiết kế (con số chỉ minh họa, không phải SLO chung):

| Test | Offered load | Heap / RAM | Điều kiện | Điều cần kết luận |
| --- | --- | --- | --- | --- |
| Baseline | 100 RPS | Xmx 512 MiB, RAM theo môi trường | Warm-up xong, giữ tải đủ dài | p95/p99, GC pauses, live set cơ sở |
| Steady-high | 300 RPS | Cùng baseline | Giữ mức ổn định | Có đạt completed RPS và error budget? |
| Ramp | 100 → 200 → 300 → 400 RPS | Cùng baseline | Mỗi bậc đủ dài | Bậc nào bắt đầu p99/queue/GC xấu đi? |
| Limited heap | 300 RPS | Xmx 256 MiB, giữ CPU/cấu hình khác | Giảm heap có kiểm soát | Heap headroom giảm ảnh hưởng thế nào? |
| Limited container | 300 RPS | Heap đã budget ngoài heap; giảm RAM container | Quan sát RSS/OOM events | Có OOM kill/native pressure không? |

Để đo một ảnh hưởng riêng, giữ các biến khác không đổi trong từng cặp so sánh. Nếu tăng tải đồng thời giảm heap, bạn chỉ biết hệ thống có vấn đề ở tổ hợp mới; bạn **không biết** tác nhân nào chiếm phần lớn.

Một bản báo cáo kiểm thử nên ghi: commit/release, JDK vendor/version, collector và các cờ GC, host/container CPU/RAM, heap min/max, phase start/end, workload profile, số lần lặp, thông lượng, latency phân vị, error, metrics heap, event GC quan trọng, log/JFR đã lưu và nhận định có bằng chứng. Luôn phân biệt phép thử **thực sự chạy** với giá trị dự kiến hoặc giả thuyết.

### Tiêu chí PASS/FAIL nên xuất phát từ SLO

Ví dụ điều kiện cần thiết cho một phép thử tải ổn định:

1. Completed throughput đạt ngưỡng đã xác định, error/timeout không vượt error budget.
2. p95/p99 của request không vượt ngưỡng, tính trên đủ số request và cửa sổ thời gian.
3. Không xuất hiện OOME hay OOM kill; heap và RSS sau warm-up không tăng mất kiểm soát.
4. GC pause và GC overhead nằm trong ngân sách đã xác định **với collector/heap đang thử**.
5. Ứng dụng còn đủ headroom trước biến động hợp lý, không chỉ “chạy được vài giây”.

Đối với ramp, không nhất thiết mọi mức vượt công suất thiết kế đều PASS; mục tiêu là tìm **ngưỡng bão hòa**, khả năng graceful degradation và phản ứng khi giảm tải trở lại. Đối với limited memory, phải ghi cả failure mode và giá trị giới hạn: thất bại có kiểm soát/nhanh với thông báo rõ có thể được chấp nhận trong test phá giới hạn, còn rò rỉ kéo dài và OOM kill không kiểm soát cần xử lý.

## 10. Quy trình chẩn đoán từ kết quả quan sát

**Hiện tượng A: Young GC nhiều hơn khi ramp, throughput vẫn ổn.**  
Đây có thể là hành vi bình thường vì allocation rate tăng. So thời lượng pause, CPU và p99; đừng đánh fail chỉ vì đếm nhiều GC.

**Hiện tượng B: Sau GC, heap used tăng liên tục suốt steady.**  
Kiểm tra warm-up chưa xong, cache có tăng đến mức giới hạn không, backlog/queue tăng, request giữ object lâu hay có memory leak. Phân tích live set qua các thời điểm tương đương, không so một mẫu ngay trước GC với mẫu ngay sau GC.

**Hiện tượng C: Limited heap xuất hiện Full GC liên tiếp, throughput giảm.**  
Live set và allocation pressure có thể đang ép heap quá sát trần. So cùng workload trên heap lớn hơn; kiểm tra cause, old generation occupancy và đối tượng còn sống. Không dùng `System.gc()` hoặc tuning tùy tiện để “đè” hiện tượng.

**Hiện tượng D: p99 cao nhưng GC pause rất nhỏ.**  
Đừng quy hết cho GC. Kiểm tra queueing, lock contention, CPU throttling, I/O, mạng, database, thread pool, JIT và scheduling. Một collector concurrent cũng tiêu tốn CPU; xem thêm mức sử dụng CPU tổng và từng thread.

**Hiện tượng E: Container OOMKilled khi `heapUsed` còn thấp.**  
Kiểm tra max heap, metaspace, thread stacks, direct/mapped memory, native memory và giới hạn cgroup. Đó là bài toán tổng memory footprint, không được giải quyết chỉ bằng cách tối ưu Young GC.

## 11. Bẫy phổ biến và kiến thức không nên dùng làm baseline hiện hành

- Không dùng **CMS**, `-XX:+UseConcMarkSweepGC`, các cờ `PrintGC...` cũ, hay trình phân tích log chỉ hiểu định dạng GC logging trước JDK 9. CMS đã được gỡ khỏi HotSpot hiện đại.
- Không mặc định mọi Java version có cùng cơ chế ZGC: đời JDK đã thay đổi chế độ hoạt động của ZGC. Với JDK hiện hành, chọn collector/cờ theo tài liệu **đúng phiên bản** và kiểm tra bằng log startup.
- Không kết luận `-XX:MaxGCPauseMillis=100` bảo đảm pause ≤100 ms. Đây là mục tiêu của collector, chịu giới hạn bởi tải và heap.
- Không tự động gọi `System.gc()` giữa các phase rồi coi dữ liệu này đại diện production; nó thay đổi workflow và có thể gây sai lệch.
- Không dùng `freeMemory()` đơn lẻ để kết luận leak hay hết RAM. Nó không đại diện live set, heap max hoặc RSS.
- Không so p99 trên 10 request với p99 trên 100.000 request rồi kết luận không cần xét kích thước mẫu và thời gian đo.
- Không xem một run vài giây với log ít GC là bằng chứng ổn định. GC có thể chưa đi hết chu kỳ marking/old collection; service chưa hoàn tất warm-up.
- Không chạy load generator và service trên cùng một máy thiếu CPU rồi gán mọi sụt throughput cho GC; generator cũng có thể là nút thắt.
- Không thay đổi cấu hình cờ GC liên tục khi chưa có baseline và một chỉ số thành công rõ. G1 tự điều chỉnh nhiều thông số; tuning quá sớm có thể giảm hiệu quả.

## 12. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Steady:** Chạy `steady 60 16 24` hai lần, cùng `-Xmx128m`. Đọc log và ghi tổng số pause, max pause, phân bố pause, heap sau GC và actual allocation rate. So sánh độ khác nhau giữa hai lần; giải thích vì sao `gcCountDelta` không cố định.

**Bài 2 — Ramp:** Chạy `ramp 30 16 8`. Chia kết quả theo ba bậc `8/16/32 MiB/s`. Bậc nào làm số lần GC tăng? Nếu actual rate ở bậc cuối thấp hơn target, cần xem gì ngoài GC?  
**Gợi ý:** CPU, giới hạn scheduling, overhead của đo/logging, hệ điều hành và trạng thái heap.

**Bài 3 — Limited heap:** Giữ nguyên `steady 30 40 24`, thử `-Xmx64m` và `-Xmx128m`. Mức heap nhỏ có bắt buộc OOME không?  
**Đáp án:** Không. Kết quả phụ thuộc live set thực, overhead và collector/JVM. Cần quan sát GC log cùng kết quả process, không kết luận chỉ từ tỷ lệ 40/64.

**Bài 4 — Phân biệt lỗi:** Một container giới hạn 256 MiB, JVM `-Xmx192m`, process bị kill khi RSS vượt trần dù heap used báo 140 MiB. Có đủ cơ sở khẳng định memory leak trên Java heap không?  
**Đáp án:** Không. Phải xem OOM event, native/direct/metaspace/threads và các thành phần khác của RSS trước khi quy nguyên nhân.

**Bài 5 — Metric:** Nếu log ghi tổng 1,2 giây stop-the-world pause trong cửa sổ đo 60 giây (đã loại trùng pha), pause ratio là bao nhiêu?  
**Đáp án:** `1,2 / 60 × 100% = 2%`. Con số này khác `gcCountDelta` và không thay thế phép đo p99 request.

## Tài liệu tham chiếu (API và hướng dẫn hiện hành)

- [Oracle JDK 25 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): GC concepts, pause goals và hành vi G1 dưới áp lực cấp phát.
- [Oracle JDK 25 — `java` launcher options / Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp `-Xlog`, GC log rotation, heap sizing và `MaxRAMPercentage`.
- [Oracle JDK 25 — `jcmd`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): diagnostic command và JFR.start/JFR.dump/JFR.stop.
- [Oracle JDK 25 — `jfr`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): đọc và tổng hợp file JFR.
- [OpenJDK — G1 Tuning](https://ops.java/performance/jvm/articles/tuning-g1/): hướng dẫn vận hành G1 trên JVM hiện đại.
