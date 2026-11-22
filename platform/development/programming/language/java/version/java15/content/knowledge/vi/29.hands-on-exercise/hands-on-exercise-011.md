# So sánh Garbage Collector bằng một kịch bản tải tái lập được

Bài **Thực hành** này hướng dẫn thiết kế và chạy một thí nghiệm so sánh bộ thu gom rác (*garbage collector*, GC) trong Java. Ta dùng **cùng một chương trình, seed, khối lượng cấp phát, giới hạn heap và phiên bản JDK**, chỉ thay bộ thu gom rác, rồi đối chiếu **thời gian hoàn thành công việc, GC pause và khả năng đáp ứng mục tiêu độ trễ**.

Thí nghiệm chạy được trên **JDK 17+**, phù hợp khi học Java 15 và bảo trì ứng dụng Java hiện đại. Ví dụ dùng ba collector còn được hỗ trợ trong HotSpot hiện nay: **G1**, **ZGC** và **Parallel GC**. Tùy bản phân phối JDK, có thể kiểm tra thêm **Shenandoah**. Phân biệt rõ kiến thức ổn định với chi tiết thay đổi theo phiên bản: từ **JDK 24**, ZGC chỉ còn chế độ **generational**; không áp dụng cấu hình chuyển đổi giữa chế độ non-generational và generational của các hướng dẫn JDK cũ.

> Kịch bản này là **bài thực hành đo và phân tích**, không phải bảng xếp hạng GC chung cho mọi hệ thống. Cùng tải logic vẫn có timing khác nhau vì JIT, scheduler, số lõi CPU, CPU throttling, tình trạng bộ nhớ và hoạt động nền. Chỉ quyết định collector cho ứng dụng thật sau khi đo **SLO latency, throughput và chi phí tài nguyên** trên workload đại diện.

## 1. Bạn cần biết gì trước khi đo?

### 1.1. GC xử lý vấn đề nào?

Các object còn **reachable** từ GC roots là tập dữ liệu cần giữ (*live set*); object không còn reachable có thể được JVM thu hồi. Một ứng dụng liên tục tạo object ngắn hạn nhưng giữ một tập dữ liệu sống lâu sẽ tạo ra áp lực khác với ứng dụng ít cấp phát nhưng có live set rất lớn.

GC có thể làm việc:

- **Stop-the-world (STW)**: tạm dừng các application threads để hoàn tất một giai đoạn GC. Đây là **GC pause** quan sát được.
- **Concurrent**: thực hiện một phần công việc GC trong khi application threads vẫn chạy. Các pha concurrent có thể **tiêu thụ CPU/băng thông bộ nhớ** dù không tạo pause dài.
- **Parallel**: dùng nhiều GC worker threads để hoàn thành công việc thu gom nhanh hơn; “parallel” và “concurrent” không đồng nghĩa. Một collector có thể dùng cả hai kỹ thuật ở các giai đoạn khác nhau.

Vì vậy, **pause ngắn không tự suy ra throughput cao**: collector có thể ít dừng ứng dụng nhưng dùng nhiều CPU trong nền. Ngược lại, một collector có tổng thời gian hoàn thành thấp vẫn có thể tạo các lần pause vượt yêu cầu độ trễ của dịch vụ.

### 1.2. Ba collector để so sánh

| Collector | Bật trên HotSpot | Đặc điểm hiện hành | Khi đáng thử |
| --- | --- | --- | --- |
| **G1** | `-XX:+UseG1GC` | Collector mặc định trên các môi trường HotSpot server phổ biến; generational, chia heap thành regions, cân bằng pause và throughput | Điểm xuất phát tốt cho nhiều ứng dụng |
| **ZGC** | `-XX:+UseZGC` | Collector ưu tiên **pause rất ngắn**, nhiều công đoạn concurrent; ZGC của JDK 24+ là generational | Dịch vụ nhạy độ trễ, cân nhắc CPU và headroom của heap |
| **Parallel GC** | `-XX:+UseParallelGC` | Thu gom theo hướng throughput, dùng nhiều GC threads; các pha collection tạo STW pause | Batch/compute jobs ưu tiên tổng lượng công việc hoàn thành |
| **Shenandoah** (tùy JDK build) | `-XX:+UseShenandoahGC` | Collector concurrent, hướng tới pause thấp; khả dụng và cấu hình phụ thuộc bản phân phối/JDK | Lựa chọn mở rộng khi runtime thực sự hỗ trợ |

Các lựa chọn trên **không có một thứ tự chiến thắng bất biến**. Cũng không nên lấy số lần “GC” làm thước đo hơn thua: một G1 collection và một ZGC cycle không có cùng cấu trúc pha.

### 1.3. Năm nhóm thước đo

| Chỉ số | Ý nghĩa | Lưu ý diễn giải |
| --- | --- | --- |
| **Application elapsed time** | Thời gian hoàn tất số vòng công việc cố định (wall clock) | Bị tác động bởi JIT, GC, CPU scheduling, I/O log |
| **GC pause p50/p95/p99/max** | Phân vị của **mỗi sự kiện STW pause** quan sát được | Đây **không phải** p95/p99 của HTTP request |
| **Total recorded pause time** | Tổng thời gian các STW pause được log trong khoảng đo | Không đại diện cho toàn bộ chi phí CPU của concurrent GC |
| **Allocation rate / live set** | Lượng object tạo ra mỗi giây và lượng dữ liệu phải giữ sống | Cùng vòng công việc nhưng tốc độ thực thi khác sẽ cho allocation rate theo giây khác |
| **Heap, native memory, CPU/RSS** | Mức sử dụng tài nguyên của process/host | `-Xmx` chỉ giới hạn Java heap, **không giới hạn tổng RSS** |

Trước khi chạy, hãy xác định **mục tiêu thực tế**. Ví dụ dịch vụ xử lý giao dịch có thể cần p99 request dưới ngưỡng cụ thể, còn batch job cần hoàn thành đủ số record trước deadline. Ta không chọn GC chỉ vì một giá trị “average pause” đẹp.

## 2. Thiết kế kịch bản tải có thể tái lập

### 2.1. Giả thuyết và các biến

Giả thuyết có thể kiểm chứng:

1. Với cùng seed và số vòng lặp, **checksum** phải giống nhau giữa các collector: chương trình đã thực hiện cùng công việc logic.
2. Với cùng giới hạn heap, các collector có thể cho **số lượng, thời lượng GC pauses khác nhau**, và khác về tổng thời gian thực thi.
3. Nếu tăng **live set** hoặc **allocation rate**, kết luận về thời gian chạy/pause có thể đổi; đây là lý do cần nhiều workload, không chỉ một benchmark.

Biến **giữ cố định**: cùng JDK binary/build và kiến trúc, cùng host/cgroup, cấu hình CPU, `-Xms`, `-Xmx`, source code/class file, seed, số vòng, cách ghi log, tình trạng hoạt động nền và số lần lặp. Biến **thử nghiệm**: một cờ `-XX:+Use...GC`.

### 2.2. Tải sẽ tạo bao nhiêu object?

Trong mỗi lần gọi hàm `phase`:

- Tạo **256 mảng byte[] × 256 KiB ≈ 64 MiB** còn được giữ trong mảng `retained`. Đây là **live set có chủ đích**.
- Tạo một mảng **64 KiB ở mỗi vòng lặp** và lưu vào **ring 16 phần tử**, nên các mảng cũ liên tục bị thay thế và có thể thu gom.
- Cứ **64 vòng**, thay một mảng `retained` dài **256 KiB** để mô phỏng dữ liệu sống tương đối lâu nhưng vẫn có tỷ lệ thay thế.
- Sử dụng `SplittableRandom` với seed cố định, chạm dữ liệu trong mảng và tính `checksum` để compiler/JIT không coi vòng lặp là phép tính không có tác dụng quan sát được.
- Chạy một pha `WARMUP` trước, sau đó pha `MEASURE`. Cả hai trong **một JVM riêng cho mỗi collector**.

Với **200.000 vòng MEASURE**, phần dữ liệu byte-array được yêu cầu cấp phát xấp xỉ:

~~~text
Live set khởi tạo       = 256 × 256 KiB         =   64,00 MiB
Temporary allocations   = 200000 × 64 KiB       = 12500,00 MiB
Thay retained arrays    = 3125 × 256 KiB        =   781,25 MiB
Tổng byte-array payload ≈                       13345,25 MiB
~~~

Con số `allocatedMiB` này là **payload lý thuyết của các mảng được tạo**, chưa bao gồm header/alignment, object phụ trợ và allocation của chính JVM. Nó **không phải** số MiB cùng lúc nằm trên heap: các mảng ngắn hạn được GC thu gom và vùng heap được tái sử dụng nhiều lần.

Không dùng `System.gc()` để “ép” số lần thu gom giống nhau. Thời điểm GC là quyết định của collector; cố định các GC event sẽ làm méo chính đặc điểm cần so sánh.

## 3. Chương trình thực hành: `GcLoad.java`

Tạo một thư mục thực hành trống, sau đó tạo file **`GcLoad.java`** với toàn bộ mã sau. File biên dịch độc lập bằng Java 17 trở lên, không cần dependency ngoài JDK.

~~~java
import java.lang.management.ManagementFactory;
import java.util.Locale;
import java.util.SplittableRandom;

public final class GcLoad {
    private static final int LIVE_SLOTS = 256;
    private static final int LIVE_BYTES = 256 * 1024;
    private static final int TEMP_BYTES = 64 * 1024;
    private static final int RING_SLOTS = 16;

    // Đảm bảo kết quả vòng lặp có tác dụng quan sát được.
    private static volatile long sink;

    private static void phase(String name, int rounds, long seed) {
        byte[][] retained = new byte[LIVE_SLOTS][];
        for (int i = 0; i < retained.length; i++) {
            byte[] block = new byte[LIVE_BYTES];
            block[0] = (byte) i;
            retained[i] = block;
        }

        byte[][] ring = new byte[RING_SLOTS][];
        SplittableRandom random = new SplittableRandom(seed);
        long checksum = 0;

        // Uptime giúp lọc GC logs theo đúng khoảng MEASURE.
        long startUptime = ManagementFactory.getRuntimeMXBean().getUptime();
        long start = System.nanoTime();

        for (int i = 0; i < rounds; i++) {
            byte[] temporary = new byte[TEMP_BYTES];
            temporary[0] = (byte) random.nextInt(256);
            temporary[temporary.length - 1] = (byte) i;

            int ringSlot = i % RING_SLOTS;
            if (ring[ringSlot] != null) {
                checksum += Byte.toUnsignedInt(ring[ringSlot][0]);
            }
            ring[ringSlot] = temporary;

            // Mô phỏng live set có dữ liệu được làm mới dần.
            if ((i & 63) == 0) {
                int liveSlot = random.nextInt(LIVE_SLOTS);
                byte[] replacement = new byte[LIVE_BYTES];
                replacement[0] = (byte) liveSlot;
                retained[liveSlot] = replacement;
            }

            checksum += Byte.toUnsignedInt(temporary[0]);
        }

        // Dùng lại nội dung của cả retained và ring ở cuối pha.
        for (byte[] block : retained) {
            checksum += Byte.toUnsignedInt(block[0]);
        }
        for (byte[] block : ring) {
            if (block != null) {
                checksum += Byte.toUnsignedInt(block[0]);
            }
        }

        long elapsedNanos = System.nanoTime() - start;
        long endUptime = ManagementFactory.getRuntimeMXBean().getUptime();
        sink = checksum;

        double allocatedMiB =
                ((double) LIVE_SLOTS * LIVE_BYTES
                        + (double) rounds * TEMP_BYTES
                        + (double) ((rounds + 63) / 64) * LIVE_BYTES)
                        / (1024.0 * 1024.0);

        System.out.printf(Locale.ROOT,
                "%s rounds=%d allocatedMiB=%.1f elapsedMs=%.3f"
                        + " checksum=%d uptimeMs=%d..%d%n",
                name, rounds, allocatedMiB,
                elapsedNanos / 1_000_000.0,
                sink, startUptime, endUptime);
    }

    public static void main(String[] args) {
        int rounds = args.length == 0
                ? 200_000
                : Integer.parseInt(args[0]);

        if (rounds < 1) {
            throw new IllegalArgumentException(
                    "rounds must be positive");
        }

        phase("WARMUP", 4_000, 20261108L);
        phase("MEASURE", rounds, 20261108L);
    }
}
~~~

Biên dịch:

~~~bash
java -version
javac -version
javac --release 17 GcLoad.java
~~~

Chạy thử không chỉ định collector:

~~~bash
java -Xms512m -Xmx512m GcLoad 200000
~~~

Kết quả có cấu trúc:

~~~text
WARMUP rounds=4000 allocatedMiB=329.8 elapsedMs=... checksum=1037174 uptimeMs=.....
MEASURE rounds=200000 allocatedMiB=13345.3 elapsedMs=... checksum=51105704 uptimeMs=.....
~~~

**`elapsedMs` và `uptimeMs` là số đo động**, khác nhau theo JVM/host; dấu `...` trong khung trên chỉ biểu thị các số đo cần đọc từ lần chạy thực tế, **không phải stdout cố định**. Ngược lại, với đúng mã và số vòng trên, các giá trị `rounds`, `allocatedMiB` và `checksum` được xác định bởi kịch bản. Ba collector phải cho cùng `MEASURE checksum=51105704`. Nếu checksum khác, kiểm tra lại source/class/arguments trước khi so sánh hiệu năng.

**Giải thích thiết kế:**

- Mỗi collector chạy một JVM riêng. Không thể đổi collector của một JVM đang chạy rồi coi đó là một phép đo tương đương.
- `retained` và `ring` tạo các đường tham chiếu mạnh trong pha, trong khi object bị thay khỏi mảng có thể trở thành garbage. Không hứa thời điểm chính xác GC sẽ thu hồi chúng.
- `volatile sink`, checksum và việc đọc các mảng giúp công việc có hiệu ứng quan sát được. Đây vẫn là workload tổng hợp; kết quả không thay thế benchmark ứng dụng thật.
- `System.nanoTime()` dùng để đo **elapsed duration**, không đổi thẳng thành thời gian đồng hồ/thời điểm tuyệt đối.
- Pha warmup chỉ là **warmup tối thiểu**, không bảo đảm toàn bộ JIT compilation, page faults và collector heuristics đã ổn định. Vì vậy phép đo thực tế phải chạy nhiều JVM forks.

## 4. Chạy cùng tải với từng collector

Dùng **cùng thư mục chứa `GcLoad.class`**, đủ RAM để JVM tạo heap 512 MiB cộng các vùng native và chạy **từng process lần lượt**. Các lệnh này dùng được với Bash và PowerShell; tên file log riêng giúp không ghi đè.

### 4.1. G1

~~~bash
java -Xms512m -Xmx512m -XX:+UseG1GC "-Xlog:gc*:file=g1-gc.log:uptime,level,tags" GcLoad 200000
~~~

### 4.2. ZGC

~~~bash
java -Xms512m -Xmx512m -XX:+UseZGC "-Xlog:gc*:file=zgc-gc.log:uptime,level,tags" GcLoad 200000
~~~

### 4.3. Parallel GC

~~~bash
java -Xms512m -Xmx512m -XX:+UseParallelGC "-Xlog:gc*:file=parallel-gc.log:uptime,level,tags" GcLoad 200000
~~~

Ý nghĩa của các cờ:

- `-Xms512m -Xmx512m`: đặt cùng **initial/maximum Java heap** cho các lần chạy để giảm khác biệt do resize heap. Không có nghĩa RSS của các JVM giống nhau.
- `-XX:+UseG1GC`, `-XX:+UseZGC`, `-XX:+UseParallelGC`: chọn một GC tại JVM startup. Chỉ chọn **một** collector trong một run.
- `-Xlog:gc*:file=...:uptime,level,tags`: bật **Unified JVM Logging**, ghi hoạt động GC và pha con ra file, kèm uptime, level, tag. Tùy JDK, nội dung/chi tiết từng dòng có thể thay đổi.

Chỉ có một loại collector được dùng cho mỗi lần chạy; không bật các cờ GC xung đột trong cùng JVM. Với JDK 24+ **không thêm cờ điều khiển `ZGenerational`**: non-generational ZGC đã bị loại bỏ.

Nếu JVM báo **“Unrecognized VM option”** hoặc collector không có trong build: lưu lỗi và thông tin `java -version`; không ép bật tùy chọn của runtime khác. Với Shenandoah, kiểm tra sự hiện diện bằng `java -XX:+UseShenandoahGC -version` trước khi đưa vào thí nghiệm mở rộng.

### 4.4. Kiểm tra tính tương đương trước khi so tốc độ

Từ mỗi stdout, xác nhận:

1. `MEASURE rounds=200000` ở cả ba.
2. `allocatedMiB=13345.3` ở cả ba.
3. `checksum=51105704` ở cả ba.
4. Mỗi file GC log tương ứng tồn tại và có dữ liệu, đồng thời lệnh chạy kết thúc với exit code `0`.
5. Cùng JVM binary, máy, heap và không có tác vụ nặng khác chạy xen giữa.

Nếu một run ném `OutOfMemoryError`, thời gian của run lỗi **không có ý nghĩa** để so sánh như một lần hoàn thành bình thường. Khi điều chỉnh heap, điều chỉnh **giống nhau** cho mọi collector và chạy lại từ đầu; vẫn phải xác nhận workload có live set/throughput đáp ứng mục tiêu.

## 5. Tách đúng khoảng MEASURE trong GC log

Log chứa cả quá trình JVM khởi động và **WARMUP**. Nếu cộng mọi sự kiện từ đầu file thì sẽ lẫn tải trước phép đo.

Đầu ra `GcLoad` có hai mốc `uptimeMs`, ví dụ từ một lần chạy thực tế:

~~~text
MEASURE rounds=200000 allocatedMiB=13345.3 elapsedMs=818.082 checksum=51105704 uptimeMs=137..956
~~~

Ý nghĩa: khoảng đo bắt đầu gần **137 ms** và kết thúc gần **956 ms** kể từ khi JVM khởi động. Dòng log gắn `[0.500s]` nằm trong khoảng; dòng `[0.100s]` ở trước. Hai mốc được đọc qua `RuntimeMXBean.getUptime()`, độ chính xác ms, nên việc gán sự kiện nằm **sát ranh giới** chỉ có tính gần đúng.

Trong GC logs HotSpot, dòng tiêu biểu có dạng:

~~~text
[0.500s][info][gc] GC(7) Pause Young (...) ... 2.123ms
[0.600s][info][gc,phases] GC(9) Pause Mark Start 0.017ms
~~~

Hai dòng trên chỉ minh họa **định dạng**, không phải log bắt buộc của mọi collector/JDK. Tên pha khác nhau: G1 thường có “Pause Young”, “Pause Remark”, còn ZGC có nhiều pause ngắn theo giai đoạn. **Một dòng “GC cycle completed” không đồng nghĩa một STW pause.** Tránh cộng thời lượng concurrent cycle vào “total pause”.

## 6. Công cụ nhỏ để tính pause p50, p95 và max

Để việc đối chiếu dễ tái lập mà không cần cài thư viện, tạo file **`GcLogStats.java`**. Chương trình đọc **Unified GC Log** có decoration `uptime,level,tags` như các lệnh ở phần trên, chỉ lấy dòng chứa một `GC(...) Pause` và thời lượng `ms`, rồi lọc theo thời gian MEASURE.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class GcLogStats {
    private static final Pattern UPTIME =
            Pattern.compile("^\\[([0-9]+(?:\\.[0-9]+)?)s\\]");
    private static final Pattern PAUSE =
            Pattern.compile("\\bPause\\b.*\\s([0-9]+(?:\\.[0-9]+)?)ms\\s*$");

    private static double percentile(
            List<Double> sorted, double fraction) {
        int index = Math.max(0,
                (int) Math.ceil(fraction * sorted.size()) - 1);
        return sorted.get(index);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "usage: java GcLogStats log-file"
                            + " startUptimeMs endUptimeMs");
        }

        double startSeconds = Double.parseDouble(args[1]) / 1000.0;
        double endSeconds = Double.parseDouble(args[2]) / 1000.0;
        List<Double> pauses = new ArrayList<>();

        for (String line : Files.readAllLines(Path.of(args[0]))) {
            if (!line.contains(" GC(")
                    || !line.contains(" Pause ")) {
                continue;
            }

            Matcher uptime = UPTIME.matcher(line);
            Matcher pause = PAUSE.matcher(line);
            if (uptime.find() && pause.find()) {
                double when = Double.parseDouble(uptime.group(1));
                if (when >= startSeconds && when <= endSeconds) {
                    pauses.add(Double.parseDouble(pause.group(1)));
                }
            }
        }

        if (pauses.isEmpty()) {
            System.out.println(
                    "No completed GC pauses in selected window");
            return;
        }

        Collections.sort(pauses);
        double totalMs = pauses.stream()
                .mapToDouble(Double::doubleValue)
                .sum();

        System.out.printf(Locale.ROOT,
                "pauses=%d totalMs=%.3f"
                        + " p50Ms=%.3f p95Ms=%.3f maxMs=%.3f%n",
                pauses.size(),
                totalMs,
                percentile(pauses, 0.50),
                percentile(pauses, 0.95),
                pauses.get(pauses.size() - 1));
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 GcLogStats.java
~~~

Với **đúng lần chạy tham khảo** có `uptimeMs=137..956` của G1 ở trên, gọi:

~~~bash
java GcLogStats g1-gc.log 137 956
~~~

Kết quả quan sát được trong lần chạy tham khảo:

~~~text
pauses=71 totalMs=160.194 p50Ms=2.526 p95Ms=3.001 maxMs=5.274
~~~

**Trong lần chạy của bạn phải thay 137 và 956 bằng hai mốc riêng của stdout G1.** Với ZGC/Parallel, dùng file log và hai mốc uptime của **chính process** tương ứng; không dùng uptime của G1 cho JVM khác.

Đây là bộ phân tích phục vụ **đúng mẫu GC log và log level** đã chọn; regex không phải chuẩn API log bất biến. Nếu nhận “No completed GC pauses”, xem vài dòng log và kiểm tra khoảng uptime, tags, định dạng đơn vị; có thể workload quá ngắn, GC chưa tạo pause trong cửa sổ đo hoặc JDK in log khác. **Không biến số lượng pause bằng 0 thành bằng chứng collector không tốn chi phí.** Với phân tích sản xuất, có thể dùng công cụ chuyên dụng hoặc các sự kiện GC trong Java Flight Recorder (JFR) và đối chiếu chúng với Unified Logging.

Cách tính phân vị là **nearest rank** trên danh sách pause đã sắp tăng: p95 lấy phần tử thứ `ceil(0.95 × số_pause)` (đếm từ 1). Nếu có ít pause, p95 rất nhiễu; đọc thêm max và kích thước mẫu.

## 7. Một lần chạy đã kiểm chứng: cách đọc kết quả đúng

Một lượt thực thi trên **OpenJDK 24**, cùng mã `GcLoad` và `GcLogStats` biên dịch bằng `javac --release 17`, với **200.000 vòng, heap 512 MiB**, đã cho kết quả sau. Các số chỉ là **quan sát của một host trong một lần chạy**, không được dùng làm dự đoán cho máy khác:

| Collector | `MEASURE elapsedMs` | Pause events | Tổng pause (ms) | p95 pause (ms) | Max pause (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| G1 | 818.082 | 71 | 160.194 | 3.001 | 5.274 |
| ZGC | 1375.699 | 220 | 3.908 | 0.027 | 0.041 |
| Parallel GC | 1026.711 | 96 | 152.007 | 2.175 | 8.290 |

**Ba kết quả đều có checksum `51105704`.** Lượng payload cấp phát là `13345.3 MiB` ở mỗi lần MEASURE.

Điều có thể nói từ **riêng dữ liệu này**:

- **ZGC có STW pauses ngắn hơn trong lượt đo này**, song tổng thời gian hoàn thành lớn hơn. Phần công việc GC concurrent không xuất hiện trong tổng STW pause.
- **G1 hoàn thành tải nhanh nhất trong lượt này**. Điều đó **không** chứng minh G1 luôn có throughput cao hơn Parallel GC: benchmark dưới một giây đến vài giây rất nhạy với JIT, CPU và log overhead.
- **Số pause của ZGC lớn hơn** không có nghĩa GC tệ hơn: các pha STW của ZGC nhỏ và có cấu trúc khác G1/Parallel. So sánh phân bố pause và latency thực của ứng dụng thay vì số sự kiện thuần túy.
- **Tổng pause không nên trừ trực tiếp khỏi elapsedMs rồi gọi phần dư là “application execution time”**. GC concurrent chiếm CPU song song, JIT và các hoạt động JVM khác cũng ảnh hưởng elapsed.

Không kết luận collector “tốt nhất” từ một bảng dữ liệu này. Trên một ứng dụng HTTP, hãy đo thêm **p95/p99 request latency khi chịu tải**, throughput request/s, tỷ lệ lỗi và CPU/RSS với từng collector.

## 8. Quy trình đo nhiều lần để giảm nhiễu

### 8.1. Mỗi collector chạy ít nhất vài JVM forks

Một kết quả hợp lệ cho so sánh cần nhiều lần chạy **độc lập**, không chỉ gọi lại `GcLoad.main` trong cùng JVM. Thực tế nên chạy **5–10 forks** cho mỗi collector để thấy độ biến thiên; tăng `rounds` nếu đoạn MEASURE quá ngắn so với thời gian khởi động và JIT warmup.

Ví dụ **PowerShell** chạy G1 năm JVM riêng, lưu log của từng fork:

~~~powershell
1..5 | ForEach-Object {
    java -Xms512m -Xmx512m -XX:+UseG1GC "-Xlog:gc*:file=g1-$_.log:uptime,level,tags" GcLoad 200000
}
~~~

Làm tương tự với ZGC và Parallel, mỗi loại dùng tên log riêng. Trên Bash, vòng lặp tương đương:

~~~bash
for i in 1 2 3 4 5; do
  java -Xms512m -Xmx512m -XX:+UseG1GC "-Xlog:gc*:file=g1-$i.log:uptime,level,tags" GcLoad 200000
done
~~~

Lưu **mỗi dòng MEASURE và log file** theo cùng run ID. Đảo thứ tự collector giữa các đợt (ví dụ G1 → ZGC → Parallel; sau đó Parallel → G1 → ZGC) để giảm thiên lệch do nhiệt độ CPU, cache và tải nền. Không chạy các JVM đo **đồng thời** nếu mục tiêu là so sánh hiệu năng độc lập trên cùng tài nguyên.

### 8.2. Ghi nhận và tổng hợp dữ liệu

Với mỗi fork, lưu tối thiểu: collector, JDK build, OS, CPU/memory limit, `rounds`, heap `Xms/Xmx`, checksum, `elapsedMs`, pause count, pause p95/max, lỗi JVM nếu có và file log. Tổng hợp **median elapsedMs** của nhiều forks và xem độ phân tán (min/max hoặc khoảng tứ phân vị).

Để đo gần sản xuất hơn:

- Dùng workload có **concurrency, request/response, tỷ lệ đọc/ghi, kích thước object và live set** tương tự ứng dụng thật.
- Đo **tail latency tại client**; p99 của pause GC và p99 của response time không tương đương.
- Theo dõi CPU time của ứng dụng và GC, RSS/native memory, throughput, allocation rate và tỷ lệ lỗi. G1 và ZGC có mức sử dụng GC concurrent khác nhau.
- Cân nhắc chạy **không có GC logging chi tiết** khi đánh giá throughput cuối cùng; logging nhiều sự kiện có thể tạo overhead khác nhau giữa collectors. Lưu các lượt có GC logging để chẩn đoán.
- Tăng thời gian MEASURE và warmup theo đặc điểm dịch vụ. Tránh coi kết quả workload ngắn này là benchmark chuẩn như một bộ thử nghiệm được thiết kế chuyên nghiệp.

### 8.3. JVM options không nên tùy tiện điều chỉnh

Khi mới so sánh, **giữ collector với các heuristics mặc định**, chỉ cố định heap/công việc. Không chỉnh riêng `-XX:MaxGCPauseMillis`, worker thread counts, generation sizing, region size hoặc các tuning flags khác trước khi có bằng chứng về nguyên nhân.

Nếu phần “live set” quá lớn so với `-Xmx`, các collector concurrent như ZGC cần **headroom** để tiếp tục cấp phát trong khi thu gom. Một cuộc thử nghiệm chỉ có 512 MiB heap có thể làm lộ hạn chế tài nguyên mà không phản ánh cấu hình production có nhiều RAM. Trước khi suy diễn, lặp phép đo với heap khác **nhưng áp dụng cùng một heap cho cả ba**.

## 9. Các phép thử tiếp theo: thay một biến tại một thời điểm

### Thử nghiệm A — Tăng heap

Chạy lại cùng seed/rounds với `-Xms1g -Xmx1g` cho cả ba collector (đảm bảo máy đủ bộ nhớ). Quan sát GC frequency, pause và elapsed. **Giả thuyết**: thêm heap có thể giảm áp lực GC, đặc biệt với collector concurrent; kết quả phải được đo, không mặc định luôn tốt hơn.

### Thử nghiệm B — Tăng live set

Đổi `LIVE_SLOTS` từ `256` thành `768` trong `GcLoad.java`, sau đó **biên dịch lại** và chạy đủ ba collector với heap phù hợp. Tổng payload live khởi tạo lúc đó xấp xỉ `192 MiB`. So sánh với trường hợp 64 MiB để thấy hậu quả của object retention; không dùng cùng một kết quả checksum của mã cũ để kiểm tra mã mới vì kịch bản đã thay đổi.

### Thử nghiệm C — Tăng tỷ lệ allocation

Tăng `rounds` từ `200000` lên `500000` cho mọi collector mà không đổi `LIVE_SLOTS`. Số vòng tăng, payload cấp phát tăng nhưng **đích so sánh mới vẫn phải giống nhau ở cả ba**. Ghi lại kích thước log và elapsed để tránh log quá lớn hoặc phép đo quá ngắn.

### Thử nghiệm D — Tải có giới hạn độ trễ

Bổ sung một luồng gửi request hoặc worker có operation timing, giữ đồng thời một luồng cấp phát background, sau đó đo **request latency histogram** ở đầu client. Một collector có p95 GC pause ngắn chưa chắc cho p99 request latency tốt nhất khi CPU bị GC concurrent sử dụng. Không dùng các bản ghi `elapsedMs` của một vòng allocation đơn luồng để giả định chúng là request latencies.

### Thử nghiệm E — So sánh với Shenandoah khi khả dụng

Chỉ bổ sung `-XX:+UseShenandoahGC` nếu **bản build JDK hiện tại hỗ trợ**; dùng cùng source, heap, seed, rounds và cách đo. Kiểm tra tài liệu JVM của chính distribution đang triển khai trước khi tuning các mode đặc thù.

## 10. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| So sánh G1 trên JDK này với ZGC trên JDK khác | Lẫn thay đổi JVM/JIT/API với thay đổi collector | Cùng JDK binary/build và flags nền |
| Không kiểm tra checksum | Hai run có thể làm công việc khác nhau | Assert `rounds` và checksum giống nhau |
| Chỉ đo một lần | Nhiễu do JIT, scheduler, CPU throttling | Nhiều forks, median và độ phân tán |
| Cộng cả log WARMUP vào MEASURE | Sai tổng pause/p95 cho phần đo | Lọc bằng `uptimeMs` của đúng JVM |
| Đồng nhất “GC count” giữa collectors | So sánh các event/cycle khác bản chất | Phân loại collector, đối chiếu pause và response latency |
| Xem tổng pause là toàn bộ GC overhead | Bỏ sót chi phí concurrent CPU và memory bandwidth | Đo CPU, wall time, request throughput, RSS |
| Xem `-Xmx` là giới hạn RAM của process | Bỏ sót native/metaspace/code cache/threads | Theo dõi RSS và native memory |
| Thấy không có pause trong cửa sổ đo rồi kết luận GC bằng 0 | Window quá ngắn hoặc log parser không bắt đủ | Kiểm tra log, duration, JFR, thời gian đo |
| Áp dụng flags GC cũ không còn hỗ trợ | JVM từ chối khởi động hoặc hành vi khác dự tính | Đọc tài liệu đúng JDK; dùng cờ hiện hành |
| Thay heap/tuning flags riêng từng collector trước khi so | Không còn thí nghiệm kiểm soát một biến | Cùng heap và cấu hình nền, sau đó mới tối ưu riêng |
| Để log output quá lớn trên ổ đĩa chậm | Logging trở thành một phần đáng kể elapsed time | Thử throughput không log chi tiết, giữ log chẩn đoán riêng |
| Kết luận từ workload byte[] tổng hợp rằng web service cũng nhanh tương ứng | Không phản ánh object graph, allocations, concurrency, I/O, response latency thực | Xây workload đại diện ứng dụng và đối chiếu SLO |

## 11. Câu hỏi tự kiểm tra

1. Vì sao **cùng checksum** cần thiết nhưng **chưa đủ** để kết luận benchmark công bằng?  
   *Gợi ý:* checksum xác nhận công việc logic, còn CPU/JDK/JIT, cấu hình, log overhead và host load vẫn có thể khác.
2. Nếu ZGC có p95 GC pause thấp nhất nhưng `elapsedMs` cao nhất, liệu đó là lỗi?  
   *Gợi ý:* không nhất thiết; chi phí GC concurrent và mục tiêu latency/throughput khác nhau.
3. Vì sao phải lấy khoảng uptime trong stdout **của từng process**, thay vì dùng số từ G1 cho ZGC?  
   *Gợi ý:* uptime tính từ lúc JVM riêng khởi động.
4. `allocatedMiB=13345.3` có nghĩa process dùng 13 GiB RAM tại một thời điểm không?  
   *Gợi ý:* không; đây là tổng payload được cấp phát qua thời gian, trong heap có thể tái sử dụng.
5. Collector có số “Pause” events nhiều gấp ba lần đã chắc chắn tệ hơn?  
   *Gợi ý:* chưa; xem **thời lượng từng pause**, cách collector chia pha và kết quả ứng dụng.
6. Vì sao một GC pause p99 thấp không bảo đảm **p99 HTTP response time** thấp?  
   *Gợi ý:* request còn chịu queueing, CPU contention, I/O, lock, database và nhiều nguyên nhân khác.

## 12. Tài liệu hiện hành để đối chiếu

- [Oracle JDK 25 — HotSpot Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html)
- [Oracle JDK 25 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html)
- [Oracle JDK 25 — G1 Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html)
- [Oracle JDK 24 — ZGC: generational và không còn `ZGenerational`](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html)
- [Oracle JDK 25 — `java` command, Unified JVM Logging `-Xlog`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [OpenJDK — JEP 439: Generational ZGC](https://openjdk.org/jeps/439)
- [OpenJDK — JEP 474: ZGC Generational Mode by Default](https://openjdk.org/jeps/474)
- [OpenJDK — JEP 490: Remove ZGC Non-Generational Mode](https://openjdk.org/jeps/490)
- [OpenJDK — JEP 521: Generational Shenandoah](https://openjdk.org/jeps/521)
