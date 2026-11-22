# Ghi nhận kết quả chức năng, tài nguyên và hiệu năng trong bài thực hành Java

## 1. Mục tiêu: không chỉ “chạy được”, mà phải có bằng chứng

Khi hoàn thành một bài thực hành tổng hợp Java, kết luận “chương trình chạy tốt” là chưa đủ. Cần **ghi nhận bằng chứng có thể tái lập** theo ba chiều độc lập:

1. **Chức năng (functional correctness):** chương trình nhận đầu vào nào, cho kết quả nào, xử lý lỗi và trường hợp biên ra sao? Những điều được kiểm tra có đúng với tiêu chí chấp nhận không?
2. **Tài nguyên (resources):** chương trình mở/đóng file, stream, socket, thread, executor như thế nào? Heap, bộ nhớ native, CPU, số thread, file descriptor và GC thay đổi ra sao? Có dấu hiệu rò rỉ hoặc vượt giới hạn vận hành không?
3. **Hiệu năng (performance):** trong một workload và môi trường xác định, thời gian xử lý, độ trễ, throughput, mức tiêu thụ tài nguyên và biến động giữa các lần chạy là bao nhiêu?

Bài học dùng **Java 17+** và các công cụ vẫn còn được hỗ trợ trong JDK hiện đại: `try-with-resources`, `java.lang.management`, **Java Flight Recorder (JFR)**, `jcmd`, **unified logging `-Xlog`**, và khi cần microbenchmark nghiêm túc là **JMH**. Không dùng các công cụ/flag logging cũ đã bị thay thế từ lâu.

**Nguyên tắc nền:** số đo chỉ có ý nghĩa khi có **bối cảnh, đơn vị, phương pháp, thời điểm và đầu ra gốc**. Đừng biến một số đo một lần thành khẳng định tổng quát về hiệu năng.

## 2. Trước khi chạy: định nghĩa tiêu chí và cấu hình thử nghiệm

Một bản ghi thử nghiệm tối thiểu phải trả lời:

| Nhóm | Cần ghi cụ thể | Ví dụ cách ghi |
| --- | --- | --- |
| Danh tính bản chạy | Bản ứng dụng, commit/build, câu lệnh biên dịch, cấu hình | Java 17 bytecode (`javac --release 17`), tên class main |
| JVM | Vendor, phiên bản, VM, tham số heap và GC | Lưu đầu ra `java -version`, JVM flags |
| Máy/chạy | OS/kiến trúc, CPU/vCPU, RAM, container limit, filesystem | Linux x64, 4 vCPU, 8 GiB, giới hạn container nếu có |
| Workload | Dữ liệu đầu vào, kích thước file, concurrency, số request, thời gian tải | 10.000 phép xử lý/trial, 3 warmup và 5 lần đo |
| Chức năng | Expected, actual, số test PASS/FAIL, đầu vào biên, mã thoát | Không chỉ ghi “OK”; lưu assertion và lỗi khi test thất bại |
| Tài nguyên | Đối tượng cần đóng, heap, native memory, threads, handles, CPU/GC | Tách “đóng stream thành công” khỏi “không rò rỉ bộ nhớ” |
| Hiệu năng | Thời lượng, latency percentile, throughput, variance, đơn vị | ms, ops/s, req/s, MiB; mẫu đo và cách tổng hợp |
| Đánh giá | Ngưỡng pass/fail, baseline, độ biến động, điều kiện chấp nhận | Ngưỡng do yêu cầu hệ thống xác định, không tự bịa SLA |
| Bằng chứng | Log chuẩn, JFR, GC log, test report, timestamp | Gắn mỗi nhận xét với đúng file/đầu ra và run ID |

**Tiêu chí chấp nhận** phải viết trước khi đo: ví dụ bài toán yêu cầu cho ra dữ liệu đã chuẩn hóa và **không bỏ sót lỗi I/O**, còn giới hạn tài nguyên/độ trễ phải đến từ yêu cầu sản phẩm hoặc baseline có kiểm chứng. Không đặt một mốc như “mọi Java service phải dưới 100 ms” khi chưa có workload cụ thể.

Nên chạy ít nhất hai loại kiểm tra:
- **Smoke/functional check**: phản hồi nhanh, tính đúng có thể kiểm chứng bằng dữ liệu cố định, thất bại phải hiển thị rõ.
- **Resource/performance observation**: lặp lại dưới tải đại diện, ghi các chỉ số **thực đo**, hiểu rằng một số giá trị thay đổi giữa các JVM và máy.

## 3. Trục 1 — Ghi nhận kết quả chức năng

Một kết quả chức năng nên được trình bày theo **Arrange–Act–Assert**:

1. **Arrange:** chuẩn bị dữ liệu đầu vào và trạng thái cần thiết.
2. **Act:** gọi hành vi đang kiểm thử.
3. **Assert:** kiểm tra **giá trị mong đợi** và hiệu ứng phụ; nếu sai thì báo FAIL, không chỉ in thông báo.

Các loại case nên có khi liên quan:
- **Happy path:** đầu vào hợp lệ sinh kết quả đúng.
- **Boundary:** đầu vào rỗng, kích thước tối thiểu/tối đa, ký tự Unicode, dòng cuối không có newline.
- **Failure path:** lỗi đọc file, permission denied, timeout, dữ liệu không hợp lệ.
- **Recovery/cleanup:** tài nguyên vẫn được giải phóng nếu thao tác giữa chừng ném exception.
- **Tính xác định:** cùng đầu vào trong cùng điều kiện phải cho cùng kết quả chức năng, không phụ thuộc JIT/GC.

Có thể dùng **JUnit Jupiter (JUnit 5)** nếu dự án đã có test framework và CI; với bài thực hành độc lập dưới đây, một class chứa assertion tự viết giúp biên dịch/chạy bằng JDK 17 mà **không cần dependency**. Tự viết assertion chỉ phù hợp minh họa nhỏ, không thay thế hệ thống test chuyên dụng của dự án.

**Không tính số lần in `PASS` là coverage.** 2 ca kiểm thử có thể PASS nhưng chưa kiểm tra được hàng trăm tình huống khác. Ghi rõ các case được bao phủ và còn thiếu.

## 4. Trục 2 — Ghi nhận việc sử dụng và giải phóng tài nguyên

### 4.1. Tài nguyên có vòng đời phải được đóng

Những đối tượng thường cần quản lý rõ vòng đời: `InputStream`, `OutputStream`, `BufferedReader`, `FileChannel`, `ZipFile`, socket, `WatchService`, `ExecutorService`, kết nối database. Với đối tượng `AutoCloseable`/`Closeable`, ưu tiên **try-with-resources** khi phương thức sở hữu tài nguyên.

```java
try (InputStream input = Files.newInputStream(path)) {
    // Đọc / xử lý dữ liệu.
} // Tự đóng cả khi phần xử lý ném IOException.
```

Đoạn trên là **snippet**, không phải chương trình chạy độc lập. Trong API của dự án, cần quy định rõ **ai sở hữu stream**: phương thức nhận `InputStream` có tự đóng hay caller quản lý? Không âm thầm đóng tài nguyên do caller sở hữu nếu hợp đồng API không cho phép.

Kết quả kiểm thử “stream đã đóng” là bằng chứng về **một nhánh cleanup**, **không phải bằng chứng toàn ứng dụng không bị leak**. Test cần kiểm tra cả luồng bình thường và luồng exception.

### 4.2. Heap, thread, native memory và handles khác nhau

| Chỉ số | Cách quan sát còn được hỗ trợ | Không được suy luận |
| --- | --- | --- |
| Heap used/committed/max | `MemoryMXBean`, JFR/GC log, `jcmd <pid> GC.heap_info` | Heap used tăng tại một thời điểm **không chứng minh** leak |
| Số thread sống | `ThreadMXBean.getThreadCount()`, `jcmd <pid> Thread.print`, JFR | Một snapshot số thread không nói rõ deadlock hay leak |
| CPU, allocation, GC pauses | JFR, GC unified logging và metrics JVM | Một lần gọi hàm nhanh không tương đương p99 latency của dịch vụ |
| Native memory HotSpot | `-XX:NativeMemoryTracking=summary` và `jcmd <pid> VM.native_memory summary` | NMT **không bao phủ mọi native allocation** của thư viện bên thứ ba |
| File descriptor/handle | Công cụ hệ điều hành, số lượng handle/process metrics | Không có một chỉ số JVM core portable bao phủ mọi OS |
| Tài nguyên đã `close` | Test có `CloseProbe`, lifecycle logs | Đóng thành công hai stream không chứng minh mọi đường lỗi đều sạch |

Để phát hiện leak thực sự, chạy workload lặp trong thời gian đủ dài, so sánh **sau những chu kỳ GC tương đương**, quan sát retained object/heap dump (khi phù hợp), xu hướng native memory, thread/handle, rồi xác định nguyên nhân bằng profiler. Đừng ép `System.gc()` để “làm sạch số liệu” trong benchmark thường: thao tác này thay đổi workload và không bảo đảm kết quả so sánh hữu ích.

## 5. Trục 3 — Ghi nhận hiệu năng có tính tái lập

### Thời gian, thông lượng và latency

- **Elapsed time:** khoảng thời gian giữa hai thời điểm, dùng `System.nanoTime()` cho đo *duration* trong một tiến trình. Không dùng `System.currentTimeMillis()` làm đồng hồ đo benchmark vì đồng hồ tường có thể được điều chỉnh.
- **Throughput:** số thao tác hoàn thành mỗi giây (`ops/s`, `req/s`), phải chỉ rõ một *operation* là gì.
- **Latency:** thời gian hoàn thành từng request/operation; ghi median, p95, p99 khi đủ mẫu và tính theo phân phối thích hợp. **Không suy p99 từ 5 số đo tổng thời lượng**.
- **CPU/GC/resource cost:** tăng ops/s bằng cách sử dụng nhiều CPU hoặc nhiều heap có thể không phù hợp ngân sách thực.
- **Warm-up và steady state:** những lần chạy đầu có thể bị ảnh hưởng bởi class loading, JIT compilation, cache, GC và mở kết nối. Phải ghi cách warm-up và cách chọn cửa sổ đo.

Các lần chạy nên đồng nhất: JVM flags, dữ liệu, tải đồng thời, CPU limit, nhiệt độ/tải máy, I/O và cách triển khai. Với kết quả biến động, lặp các **process forks** độc lập; báo mức dao động thay vì chỉ chọn kết quả nhanh nhất.

**Lưu ý:** microbenchmark trên HotSpot dễ bị **dead-code elimination, constant folding, loop optimization, JIT profiling** làm sai. Dùng **JMH (Java Microbenchmark Harness)** để đo cấp phương thức nghiêm túc với các cấu hình warm-up, measurement, forks, state và Blackhole phù hợp. Một vòng lặp tự đo bằng `nanoTime` trong ví dụ bên dưới là **bài tập ghi dữ liệu/quan sát**, không phải benchmark đủ chặt để tuyên bố performance sản phẩm.

## 6. Ví dụ Java 17+: ghi chức năng, đóng tài nguyên và số đo thực tế

Chương trình `EvidenceDemo` thực hiện tác vụ đếm từ (không phụ thuộc thư viện ngoài), gồm hai chế độ:

- `--check`: kiểm chứng kết quả đếm từ khi có dữ liệu và dữ liệu rỗng, sau đó kiểm tra stream đóng trong cả trường hợp thành công và trường hợp đọc ném `IOException`. Dữ liệu và kết quả xác định.
- `--measure`: chạy 3 vòng warm-up và 5 vòng đo, mỗi vòng thực hiện 10.000 phép đếm từ; in median/min/max của **thời gian tổng mỗi vòng**, ước tính ops/s và snapshot heap/thread. Các số thời gian và memory **phụ thuộc môi trường**.

Tạo tệp **`EvidenceDemo.java`** ở UTF-8:

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

public class EvidenceDemo {
    private static final byte[] SAMPLE =
            "Java java\nNIO JFR\n".getBytes(StandardCharsets.UTF_8);
    private static volatile long checksum;

    static Map<String, Long> countWords(InputStream source) throws IOException {
        Map<String, Long> counts = new TreeMap<>();
        // This method takes ownership of source and always closes it.
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(source, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                for (String token : line.strip().split("\\s+")) {
                    if (!token.isEmpty()) {
                        counts.merge(token.toLowerCase(Locale.ROOT), 1L, Long::sum);
                    }
                }
            }
        }
        return counts;
    }

    private static final class CloseProbe extends FilterInputStream {
        boolean closed;

        CloseProbe(InputStream source) {
            super(source);
        }

        @Override
        public void close() throws IOException {
            try {
                super.close();
            } finally {
                closed = true;
            }
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void check() throws IOException {
        Map<String, Long> expected = Map.of("java", 2L, "nio", 1L, "jfr", 1L);
        require(countWords(new ByteArrayInputStream(SAMPLE)).equals(expected),
                "Wrong word counts");
        require(countWords(new ByteArrayInputStream(new byte[0])).isEmpty(),
                "Empty input must have zero words");

        CloseProbe success = new CloseProbe(new ByteArrayInputStream(SAMPLE));
        countWords(success);
        require(success.closed, "Stream not closed on success");

        CloseProbe failure = new CloseProbe(new InputStream() {
            @Override
            public int read() throws IOException {
                throw new IOException("Simulated read failure");
            }
        });
        boolean sawFailure = false;
        try {
            countWords(failure);
        } catch (IOException expectedFailure) {
            sawFailure = true;
        }
        require(sawFailure && failure.closed, "Stream not closed on failure");

        System.out.println("FUNCTION PASS cases=2");
        System.out.println("RESOURCE PASS closedStreams=2");
    }

    private static void measure() throws IOException {
        int warmup = 3;
        int measured = 5;
        int operations = 10_000;
        long[] timesNanos = new long[measured];

        for (int round = 0; round < warmup + measured; round++) {
            long sum = 0;
            long start = System.nanoTime();
            for (int i = 0; i < operations; i++) {
                sum += countWords(new ByteArrayInputStream(SAMPLE)).get("java");
            }
            long elapsed = System.nanoTime() - start;
            checksum = sum; // Observable sink, not a JMH Blackhole replacement.
            if (round >= warmup) {
                timesNanos[round - warmup] = elapsed;
            }
        }
        Arrays.sort(timesNanos);
        double medianMs = timesNanos[measured / 2] / 1_000_000.0;
        double minMs = timesNanos[0] / 1_000_000.0;
        double maxMs = timesNanos[measured - 1] / 1_000_000.0;
        double opsPerSecond = operations * 1_000_000_000.0
                / timesNanos[measured / 2];
        long heapUsed = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
        int threads = ManagementFactory.getThreadMXBean().getThreadCount();

        System.out.printf(Locale.ROOT,
                "BENCH runs=%d opsPerRun=%d medianMs=%.3f minMs=%.3f maxMs=%.3f opsPerSec=%.0f%n",
                measured, operations, medianMs, minMs, maxMs, opsPerSecond);
        System.out.println("CHECKSUM " + checksum);
        System.out.println("RESOURCE_SAMPLE heapUsedBytes=" + heapUsed
                + " liveThreads=" + threads);
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--check")) {
            check();
        } else if (args.length == 1 && args[0].equals("--measure")) {
            measure();
        } else {
            System.out.println("Usage: java EvidenceDemo --check|--measure");
        }
    }
}
```

### 6.1. Kiểm chứng tính đúng và cleanup

```bash
javac --release 17 -encoding UTF-8 EvidenceDemo.java
java EvidenceDemo --check
```

**Stdout chính xác** (đã biên dịch và chạy trên JDK hiện đại):

```text
FUNCTION PASS cases=2
RESOURCE PASS closedStreams=2
```

Ý nghĩa chính xác:
- `FUNCTION PASS cases=2`: hai assertion kiểm tra bản đồ từ `{java=2, jfr=1, nio=1}` và đầu vào rỗng.
- `RESOURCE PASS closedStreams=2`: hai `CloseProbe` xác nhận stream được đóng khi xử lý thành công **và** khi `read()` ném `IOException`.
- Một assertion sai ném `AssertionError`, làm lệnh Java kết thúc không thành công. Không nuốt lỗi rồi in `PASS`.
- Phương thức `countWords` **nhận quyền sở hữu `source` và tự đóng**; đây là hợp đồng API của ví dụ, không phải quy tắc mặc định cho mọi phương thức nhận stream.

Độ bao phủ còn hạn chế: chương trình chưa kiểm tra Unicode phức tạp, file hệ điều hành thật, quyền truy cập hay hiệu năng nhiều luồng. Vì thế kết luận chỉ áp dụng cho **các case đã chạy**.

### 6.2. Quan sát số đo thay đổi theo máy

```bash
java EvidenceDemo --measure
```

Đầu ra có dạng (các phần trong ngoặc mô tả **giá trị thay đổi**, không phải dữ liệu đo được cam kết):

```text
BENCH runs=5 opsPerRun=10000 medianMs=<so-thuc> minMs=<so-thuc> maxMs=<so-thuc> opsPerSec=<so>
CHECKSUM 20000
RESOURCE_SAMPLE heapUsedBytes=<so-nguyen> liveThreads=<so-nguyen>
```

Các ký hiệu trong khối trên là **mô tả định dạng**, không phải chuỗi stdout nguyên văn. Khi chạy, JVM sẽ in những con số thực. `CHECKSUM 20000` là giá trị ổn định: mỗi lần `countWords` có 2 từ `java`, nhân 10.000 thao tác. Field `volatile` tạo điểm tiêu thụ kết quả quan sát được nhưng **không thay được JMH Blackhole**.

Giải thích các phép đo:
1. `timesNanos` chứa **5 thời lượng tổng** cho 10.000 thao tác mỗi vòng (không chứa 50.000 độ trễ từng thao tác).
2. `medianMs` là phần tử giữa sau khi sort 5 thời lượng; `minMs/maxMs` thể hiện chênh lệch giữa những vòng.
3. `opsPerSec` = `10000 × 1e9 / medianNanos`. Đây là **ước lượng throughput từ median của các batch**, không phải p95/p99 request.
4. `heapUsedBytes` đến từ `MemoryMXBean` tại **một thời điểm**, có thể cao do garbage chưa được GC thu hồi; không kết luận leak từ nó.
5. `liveThreads` từ `ThreadMXBean` bao gồm cả những luồng JVM liên quan; có thể khác nhau giữa các lần chạy.

Đừng so các số đo `--measure` giữa hai máy có CPU/JDK khác nhau rồi kết luận code của máy nhanh “tốt hơn”. Hãy chạy workload nhất quán trên cùng môi trường và lưu toàn bộ số liệu gốc.

## 7. Thu bằng chứng JVM: JFR và GC logging

### 7.1. Ghi Java Flight Recorder

**JFR** là hệ thống thu thập sự kiện profiling/diagnostics được JDK hỗ trợ. Với HotSpot JDK 17+, có thể chạy:

```bash
java -XX:StartFlightRecording=filename=evidence.jfr,settings=profile,dumponexit=true EvidenceDemo --measure
jfr summary evidence.jfr
```

Cú pháp khởi chạy và `jfr summary` đã được kiểm chứng trên JDK hiện đại. `settings=profile` thu thông tin chi tiết hơn, có chi phí quan sát cao hơn cấu hình `default`; chỉ dùng khi cần. File `evidence.jfr` là **binary recording**, không phải text log.

Phân tích khi cần:

```bash
jfr print --events jdk.CPULoad,jdk.GarbageCollection evidence.jfr
```

Các event hiện diện phụ thuộc profile, thời gian recording và JDK. Vì chương trình demo kết thúc rất nhanh, có thể **không có đủ mẫu CPU/GC** để phân tích; hãy ghi bản JFR **trên một workload đủ dài** mới suy ra xu hướng.

**Ứng dụng Java đang chạy lâu:** tìm PID và dùng các lệnh chẩn đoán trên máy có cùng user/quyền thích hợp:

```bash
jcmd -l
jcmd 12345 JFR.start name=practice settings=profile duration=60s filename=practice.jfr
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print
```

`12345` là **PID minh họa**, chỉ sử dụng sau khi thay bằng PID Java thật. Kiểm tra lệnh và các tùy chọn hỗ trợ của bản JVM bằng `jcmd 12345 help`. Một JFR dài 60 giây không chứng minh một vấn đề chỉ từ một event đơn lẻ; cần tương quan timeline với workload và số liệu ứng dụng.

### 7.2. GC log bằng unified logging

Trong HotSpot hiện đại, dùng unified logging, không dùng các công tắc `PrintGCDetails` từ thời Java cũ để thiết kế bài thực hành mới:

```bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags EvidenceDemo --measure
```

Lệnh lưu log vào `gc.log`. Khi phân tích, kiểm tra collector thực tế, số lần GC, thời lượng pause, heap trước/sau, allocation/promotion nếu các tag phù hợp có sẵn. Một lần chạy ít cấp phát có thể **không có nhiều GC event**. Không tự đưa ra con số “GC pause = 0” chỉ vì không thấy sự kiện trong một log ngắn.

Trong báo cáo, thống kê pause (count, max, p95/p99 nếu đủ mẫu) cần tính từ **các sự kiện thực**, có thời gian bắt đầu/kết thúc, và chỉ rõ phạm vi thu thập. Đặc biệt, đừng suy ra **latency của request** trực tiếp từ thời gian GC pause: một request còn có thời gian CPU, I/O, lock, scheduler và các thành phần khác.

### 7.3. Native Memory Tracking khi nghi ngờ native-memory growth

**NMT** là công cụ của **HotSpot** để theo dõi bộ nhớ native nội bộ VM. NMT thường **tắt mặc định**, phải bật từ **lúc JVM khởi động**; không thể bật lại bằng `jcmd` khi JVM đã chạy:

```bash
java -XX:NativeMemoryTracking=summary EvidenceDemo --measure
```

Với một tiến trình đủ lâu để quan sát, có thể dùng:

```bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
```

Các lệnh có PID minh họa như trên. `summary.diff` giúp xem mức thay đổi từ baseline, nhưng **NMT không theo dõi toàn bộ cấp phát native của thư viện bên thứ ba**, không phải chỉ số tổng RSS và có overhead (tài liệu Oracle cảnh báo khoảng 5–10% trong một số tình huống). Không bật NMT khi đo performance baseline nếu mục tiêu là giảm sai lệch; có thể chạy một phiên **diagnostic riêng**.

## 8. Tổng hợp thành một biên bản kết quả có thể audit

Một bảng kết quả hữu ích **không gộp cả ba trục thành một chữ PASS**. Hãy dùng tiêu chí, quan sát, bằng chứng và kết luận riêng.

Ví dụ bảng **diễn giải đúng từ bài chạy `--check`** (không phải cam kết về toàn ứng dụng):

| Trục | Hạng mục | Expected | Quan sát chắc chắn từ bài demo | Kết luận giới hạn |
| --- | --- | --- | --- | --- |
| Chức năng | Đếm từ cơ bản | `java=2, jfr=1, nio=1` | Assertion không lỗi; in `FUNCTION PASS cases=2` | PASS cho case này |
| Chức năng | Chuỗi rỗng | Map rỗng | Assertion không lỗi | PASS cho case này |
| Tài nguyên | Stream thành công | `close()` được gọi | `CloseProbe.closed == true` | PASS cho đường thực thi này |
| Tài nguyên | Stream ném `IOException` | Vẫn đóng stream | `CloseProbe.closed == true` | PASS cho đường lỗi này |
| Tài nguyên | Heap/thread | Ghi trị số thực tế | `RESOURCE_SAMPLE ...` khi dùng `--measure` | Chỉ là snapshot, chưa kết luận leak |
| Hiệu năng | Batch parsing | Lưu đủ 5 lần đo có đơn vị | `BENCH ...` khi dùng `--measure` | Chỉ là smoke measurement, chưa đủ làm SLA |

### Trường thông tin nên lưu cho mỗi lần chạy

Có thể ghi dưới dạng Markdown/JSON/CSV trong artifact thử nghiệm:

```text
run_id       : practice-java17-001
test_scope   : word-count functional/resource/performance smoke
jdk          : vendor + version được lấy từ java -version
environment  : CPU, RAM, OS, container limit thực tế
command      : lệnh biên dịch và lệnh chạy đã dùng
input        : Java java\nNIO JFR\n (UTF-8), 10.000 ops / batch
correctness  : FUNCTION PASS cases=2
resource     : RESOURCE PASS closedStreams=2; heap/thread snapshot thực đo
performance  : 3 warmup + 5 measured batches; median/min/max ms, ops/s thực đo
evidence     : stdout/stderr, exit code, JFR/GC log nếu đã bật
limitations  : chưa có performance SLA, chưa đo p99 request, chưa chứng minh không leak
```

Các trường ghi `vendor + version` và `thực đo` có ý nghĩa **phải ghi lại dữ liệu của lần chạy cụ thể**. Không sao chép log của máy khác rồi coi là bằng chứng của lần chạy mới.

### Ghi kết quả vào CI và các lần so sánh

- Chức năng: **exit code không bằng 0 khi test fail**, đưa stderr và stack trace vào CI artifacts. Một chữ `PASS` in ra rồi tiến trình vẫn exit 0 dù lỗi xảy ra sẽ khiến pipeline khó tin cậy.
- Tài nguyên: tạo metric và log có timestamp, so sánh theo tải tương đương, cảnh báo leak dựa trên **xu hướng**, không phải một điểm dữ liệu.
- Hiệu năng: lưu baseline theo commit, JDK, loại máy và workload; so sánh nhiều lần chạy. **Có thể đặt regression threshold** khi đã có phân phối thực tế; đừng tự chọn ngưỡng từ một phép đo.
- Artifacts chứa JFR, heap dump, log có thể mang đường dẫn, tên file, query hoặc dữ liệu nhạy cảm. **Giới hạn quyền truy cập, thời gian lưu và loại bỏ thông tin không cần thiết**.

## 9. Những lỗi phổ biến và cách phòng tránh

| Sai lầm | Hậu quả | Cách thực hiện đúng |
| --- | --- | --- |
| Chỉ ghi “chạy OK” | Không biết đúng với input/expected nào | Lưu test case, expected/actual, exit code |
| Chỉ kiểm tra happy path | Bỏ sót lỗi cleanup hoặc input biên | Kiểm tra negative path và exception |
| Gộp chức năng và hiệu năng thành một PASS | Đánh tráo correctness với latency | Báo cáo ba trục riêng |
| Một heap snapshot được gọi là “không leak” | Kết luận sai vì GC/JIT/heap ergonomics | So sánh xu hướng dưới tải lặp và phân tích retained objects |
| Một mẫu `nanoTime` được gọi là benchmark | Bị JIT, GC, scheduling, noise chi phối | Dùng JMH hoặc benchmark ứng dụng có nhiều mẫu và forks |
| So p99 từ 5 batch timings | Không có phân phối request-level | Thu đủ latency từng request, chọn cửa sổ đo và định nghĩa percentile |
| So số liệu giữa hai cấu hình khác nhau | Không quy được nguyên nhân thay đổi | Ghi JVM flags, input, JDK, máy, tải hệ thống |
| Bật nhiều profiler khi so baseline | Instrumentation làm tăng overhead | Chạy phiên baseline và phiên diagnostic tách biệt |
| Không lưu output gốc/log | Không thể kiểm tra kết quả | Lưu artifact, timestamp, checksum, tham số |
| Dùng cờ JDK đã lỗi thời | Lệnh không chạy hoặc semantics khác | Dùng `-Xlog`, JFR và tài liệu đúng phiên bản JVM |
| Không phân biệt thời gian chạy và startup | “Benchmark” chủ yếu đo class loading/JIT | Tách warm-up, steady state, đo startup riêng khi cần |

## 10. Checklist hoàn thành bài thực hành tổng hợp

Một lần nghiệm thu hợp lý cần trả lời được:

1. **Tính đúng:** mọi assertion/test được chỉ định có PASS không? Nếu FAIL, có case, expected, actual và stack trace rõ ràng không?
2. **Lỗi:** có thử đầu vào rỗng, exception và luồng cleanup không? Tài nguyên do ai đóng?
3. **Môi trường:** có `java -version`, CPU/RAM/OS, heap, GC, build id và lệnh chạy không?
4. **Tài nguyên:** có ghi heap/thread/CPU/GC hoặc handles theo **đúng nhu cầu** không? Có nhầm một snapshot với chứng minh không leak không?
5. **Hiệu năng:** workload, số vòng warm-up, số lần đo, thời gian, ops/s hoặc latency percentile có được định nghĩa đúng không?
6. **So sánh:** số liệu baseline và kết quả hiện tại có chạy dưới điều kiện tương đương không? Có ghi dao động, giới hạn và overhead quan sát không?
7. **Bằng chứng:** stdout/stderr, mã thoát, JFR/GC logs hoặc báo cáo JMH (khi cần) có được lưu và liên kết với đúng run ID không?
8. **Kết luận:** đã tách rõ điều **được test chứng minh**, điều **mới chỉ quan sát**, và điều **chưa thể khẳng định** chưa?

**Tổng kết:** Ghi nhận kết quả bài thực hành Java là hoạt động tạo **bằng chứng đúng chức năng**, **bằng chứng quản lý tài nguyên** và **số đo hiệu năng có ngữ cảnh**. Test chức năng phải có assertion, resource cleanup phải kiểm tra cả đường lỗi, phép đo hiệu năng phải được lặp và giải thích đúng, còn JFR/GC/NMT chỉ đóng vai trò công cụ đo phù hợp với từng câu hỏi. Một báo cáo tốt không cố tuyên bố ứng dụng “tốt tuyệt đối”; nó nói rõ **đã kiểm tra gì, đo thế nào, quan sát gì, và còn giới hạn nào**.

### Nguồn chính thức còn được hỗ trợ

- [Java SE 25 — JFR API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Java SE 25 — jcmd diagnostic command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html)
- [Java SE 25 — Performance troubleshooting với JFR](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Java SE 25 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html)
- [Java SE 25 — java command và unified logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [OpenJDK — JMH project](https://openjdk.org/projects/code-tools/jmh/)
