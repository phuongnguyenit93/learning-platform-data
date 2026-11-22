# Đo throughput, latency và mức sử dụng bộ nhớ khi xử lý I/O và tệp lớn trong Java

## 1. Vì sao phải đo cả ba nhóm chỉ số?

Tối ưu xử lý tệp lớn không thể dựa vào một con số “chạy nhanh”. Cùng một chương trình có thể đạt throughput cao nhưng làm các yêu cầu đơn lẻ chờ lâu, hoặc đọc rất nhanh vì dùng quá nhiều RAM. Ba nhóm chỉ số cần được theo dõi cùng nhau:

- **Throughput (thông lượng):** lượng dữ liệu hoặc số thao tác hoàn tất trên một đơn vị thời gian; ví dụ `MiB/s`, `MB/s` hay `operations/s`.
- **Latency (độ trễ):** thời gian hoàn tất **một thao tác được xác định rõ**; ví dụ mỗi lần `InputStream.read(...)`, mỗi lần đọc toàn bộ tệp hoặc mỗi yêu cầu tải lên. Cần xem phân phối độ trễ, đặc biệt `p95`/`p99`, không chỉ trung bình.
- **Memory usage (mức dùng bộ nhớ):** bộ nhớ mà chương trình chiếm trong quá trình làm việc, bao gồm Java heap, direct buffer, mapped memory, native memory và bộ nhớ cấp tiến trình; phải phân biệt các phạm vi đo để không kết luận nhầm.

Trong Java I/O, kết quả còn chịu ảnh hưởng của kích thước buffer, trạng thái page cache của hệ điều hành, đặc tính SSD/HDD/network filesystem, số luồng đồng thời, GC và hành vi của thư viện. Bài này tập trung vào **cách đo đúng**, cách đọc kết quả và cách lựa chọn giải pháp phù hợp trong Java 17+.

## 2. Định nghĩa chỉ số trước khi bấm đồng hồ

### 2.1. Throughput: bytes trên thời gian thực

Nếu đã đọc/ghi thành công `B` bytes trong thời gian đo `T` giây:

\[
\text{Throughput (MiB/s)}=\frac{B}{1024^2 \times T}
\]

Ví dụ đọc `512 MiB` trong `4 s` cho throughput trung bình `128 MiB/s`. Nếu cần dùng MB theo hệ thập phân, `1 MB = 1\,000\,000 bytes`; `1 MiB = 1\,048\,576 bytes`. **Ghi rõ đơn vị** khi đối chiếu công cụ đo hoặc cấu hình thiết bị.

Hai dạng throughput có thể cho những câu trả lời khác nhau:

- **Data throughput:** `MiB/s` có ý nghĩa với sao chép, đọc/ghi tệp hoặc truyền dữ liệu lớn.
- **Operation throughput:** `ops/s` có ý nghĩa với nhiều thao tác nhỏ. Một hệ thống `10\,000 ops/s` nhưng mỗi thao tác chỉ 100 bytes chuyển ít dữ liệu hơn một hệ thống có `500 ops/s` nhưng mỗi thao tác 1 MiB.

Khi đo đọc tệp, đếm **số byte thực sự trả về** từ `read`, không lấy kích thước buffer nhân số lần gọi; một lần `read(byte[])` có thể trả số byte nhỏ hơn buffer. Với đọc song song, throughput tổng là **tổng byte hoàn tất của tất cả worker chia cho cùng khoảng thời gian thực**; không cộng các giá trị throughput đo trên những khoảng thời gian khác nhau.

### 2.2. Latency: xác định ranh giới của một thao tác

Latency = thời điểm kết thúc − thời điểm bắt đầu thao tác. Trong I/O có ít nhất ba phạm vi hợp lệ:

| Phạm vi | Cách đo | Diễn giải |
| --- | --- | --- |
| Một lệnh `read(...)` | `nanoTime()` trước và sau lần gọi | Độ trễ của lời gọi API, có thể nhận bytes từ bộ đệm |
| Một lần xử lý tệp | Bắt đầu từ mở file đến đóng/đọc xong | Độ trễ end-to-end của công việc đó |
| Một yêu cầu hệ thống | Từ lúc yêu cầu đến lúc trả kết quả | Bao gồm hàng đợi, parse, xử lý nghiệp vụ, I/O và lập lịch |

Không lấy p95 của từng `read` rồi gọi đó là “p95 xử lý tệp”; hàng trăm thao tác `read` có thể tạo thành **một** lần xử lý tệp.

Các percentile thường dùng:

- `p50` (median): ít nhất khoảng 50% số mẫu có latency không lớn hơn giá trị này.
- `p95`: khoảng 95% số mẫu có latency không lớn hơn giá trị này.
- `p99`: khoảng 99% số mẫu có latency không lớn hơn giá trị này.

Để percentile đáng tin, cần số lượng mẫu đủ lớn và các mẫu có cùng định nghĩa thao tác. Với vài mẫu, `p99` gần như chỉ phản ánh giá trị cực đại. Nên báo thêm kích thước mẫu, số lần lặp, trung bình/trung vị, min/max khi có ích và khoảng biến thiên giữa các lượt đo.

### 2.3. Dùng `System.nanoTime()` để đo elapsed time

`System.nanoTime()` được thiết kế để lấy chênh lệch thời gian trong cùng quá trình JVM, không phải timestamp gắn với thời gian lịch. Ví dụ:

~~~java
long start = System.nanoTime();
long transferred = doRead(); // Đoạn minh họa: doRead() là hàm do ứng dụng cung cấp.
long elapsedNanos = System.nanoTime() - start;

double elapsedSeconds = elapsedNanos / 1_000_000_000.0;
double mibPerSecond = (transferred / (1024.0 * 1024.0))
        / elapsedSeconds;
~~~

Đây là **đoạn mã minh họa** bên trong một phương thức, không phải chương trình hoàn chỉnh: `doRead()` phải được triển khai và trả về số byte thực đọc. Trong mã thực tế, kiểm tra trường hợp thời gian đo quá nhỏ, đo nhiều lượt và không tối ưu dựa vào một phép đo nhiễu. Không dùng `System.currentTimeMillis()` để benchmark đoạn code ngắn: đồng hồ lịch có thể bị điều chỉnh và độ phân giải thường không phù hợp.

## 3. Thí nghiệm Java 17+: đo throughput, p50/p95/p99 và heap snapshot

Ví dụ sau:

1. Tạo một **tệp thử 32 MiB** trước khi bắt đầu đo.
2. Đọc tệp bằng `BufferedInputStream` và buffer ứng dụng 64 KiB.
3. Chạy 2 lượt warm-up, **không đưa kết quả warm-up vào thống kê**.
4. Chạy 5 lượt đo, cộng số byte và thời gian để tính data throughput.
5. Ghi latency của từng `read(byte[])`, sắp xếp và tính `p50/p95/p99`.
6. Lấy hai ảnh chụp Java heap trước/sau pha đo, ghi rõ chúng **không phải đỉnh heap**.

Tạo file `IoMetricsDemo.java`:

~~~java
import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class IoMetricsDemo {
    private static final int BUFFER_BYTES = 64 * 1024;
    private static final long FILE_BYTES = 32L * 1024 * 1024;
    private static final int WARMUP = 2;
    private static final int MEASURED = 5;

    private record Trial(long bytes, long elapsedNanos, long readCalls) {}

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-metrics-", ".bin");
        try {
            prepareFile(file);

            for (int i = 0; i < WARMUP; i++) {
                readOnce(file, null);
            }

            long heapBefore = usedHeapBytes();
            long totalBytes = 0;
            long totalNanos = 0;
            long totalCalls = 0;
            List<Long> callLatencies = new ArrayList<>();

            for (int i = 0; i < MEASURED; i++) {
                Trial trial = readOnce(file, callLatencies);
                totalBytes += trial.bytes();
                totalNanos += trial.elapsedNanos();
                totalCalls += trial.readCalls();
            }
            long heapAfter = usedHeapBytes();

            callLatencies.sort(Long::compareTo);
            double seconds = totalNanos / 1_000_000_000.0;
            double mib = totalBytes / (1024.0 * 1024.0);

            System.out.println("File bytes: " + Files.size(file));
            System.out.println("Measured passes: " + MEASURED);
            System.out.println("Total read bytes: " + totalBytes);
            System.out.println("Read calls: " + totalCalls);
            System.out.printf(Locale.ROOT,
                    "Throughput: %.2f MiB/s%n", mib / seconds);
            System.out.printf(Locale.ROOT,
                    "read() p50/p95/p99: %.3f / %.3f / %.3f ms%n",
                    percentile(callLatencies, 0.50) / 1_000_000.0,
                    percentile(callLatencies, 0.95) / 1_000_000.0,
                    percentile(callLatencies, 0.99) / 1_000_000.0);
            System.out.println("Heap before (bytes): " + heapBefore);
            System.out.println("Heap after  (bytes): " + heapAfter);
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static void prepareFile(Path file) throws IOException {
        byte[] block = new byte[BUFFER_BYTES];
        Arrays.fill(block, (byte) 0x5A);
        try (OutputStream out = Files.newOutputStream(file,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING)) {
            long written = 0;
            while (written < FILE_BYTES) {
                int n = (int) Math.min(block.length, FILE_BYTES - written);
                out.write(block, 0, n);
                written += n;
            }
        }
    }

    private static Trial readOnce(Path file, List<Long> samples)
            throws IOException {
        byte[] buffer = new byte[BUFFER_BYTES];
        long bytes = 0;
        long calls = 0;
        long start = System.nanoTime();

        try (InputStream in = new BufferedInputStream(
                Files.newInputStream(file), BUFFER_BYTES)) {
            while (true) {
                long before = System.nanoTime();
                int n = in.read(buffer);
                long after = System.nanoTime();
                if (n == -1) {
                    break;
                }
                if (n == 0) {
                    continue;
                }
                bytes += n;
                calls++;
                if (samples != null) {
                    samples.add(after - before);
                }
            }
        }

        return new Trial(bytes, System.nanoTime() - start, calls);
    }

    private static long percentile(List<Long> sorted, double fraction) {
        int index = (int) Math.ceil(fraction * sorted.size()) - 1;
        return sorted.get(Math.max(0, index));
    }

    private static long usedHeapBytes() {
        return ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
    }
}
~~~

Lệnh chạy với JDK 17+:

~~~bash
javac IoMetricsDemo.java
java IoMetricsDemo
~~~

**Ba dòng đầu là cố định** khi chạy hoàn tất (kích thước được chọn trong code):

~~~text
File bytes: 33554432
Measured passes: 5
Total read bytes: 167772160
~~~

Các dòng `Read calls`, `Throughput`, `read() p50/p95/p99` và `Heap before/after` đều **phụ thuộc máy, JVM, OS, trạng thái cache và tải hệ thống**; không có một stdout số học cố định cho chúng. Những dòng này luôn dùng nhãn và đơn vị đúng như trong mã, còn giá trị cần lấy từ lần chạy thật.

### 3.1. Vì sao code đo theo cách này?

- **Tạo dữ liệu trước khi đo:** không tính thời gian ghi file test vào throughput đọc.
- **Warm-up:** giảm ảnh hưởng của việc nạp class, JIT compilation và phần nào trạng thái chưa ổn định. Hai lượt chỉ đủ cho ví dụ học tập, chưa đủ để khẳng định benchmark đại diện.
- **Đếm byte thật:** biến `bytes` tăng theo `n` mà `read` trả về, không mặc định lần nào cũng nhận 64 KiB.
- **Tính throughput từ tổng byte / tổng elapsed:** cộng thời gian các lượt đo, tránh lấy trung bình số học đơn giản của những throughput vốn có thời lượng khác nhau.
- **Latency theo từng call:** danh sách `callLatencies` đo những lời gọi `read` thành công, không ghi riêng lần `read` cuối trả `-1`. Percentile dùng quy tắc *nearest-rank* với chỉ số bắt đầu từ 0.
- **Hai loại clock window:** latency chỉ bao phần thực thi lời gọi `read`; throughput tính cả mở/đóng stream, duyệt vòng lặp và lưu sample trong mỗi lần đọc. Hai chỉ số có phạm vi khác nhau nên không kỳ vọng lấy tổng latency các call để ra chính xác elapsed.
- **Memory snapshots:** `MemoryMXBean` trả `heap.used` tại hai thời điểm; giá trị có thể tăng hoặc giảm do GC và các cấp phát khác. Chênh lệch `after - before` **không phải** tổng bytes đã cấp phát và cũng **không phải** peak heap.

### 3.2. Giới hạn quan trọng của chính ví dụ

Bài demo vừa đo latency, vừa ghi từng sample vào `ArrayList<Long>` nên có **observer overhead**: boxing `Long`, lời gọi `nanoTime()`, lưu sample và GC có thể làm throughput chậm hơn. Với phép đo nghiêm túc, chạy **một lượt đo throughput ít instrumentation** và **một lượt đo latency có sampling**, rồi so sánh kết quả. Có thể thay danh sách boxing bằng `long[]` được cấp phát đủ trước khi đo, nhưng vẫn còn overhead từ đồng hồ.

Ngoài ra, 5 lượt đọc cùng một file 32 MiB có khả năng chạy chủ yếu từ **OS page cache**, không phải throughput truy cập vật lý lạnh của SSD/HDD. Vì vậy kết quả phản ánh **cấu hình và workload cụ thể của ví dụ**, không phải thông số công bố của ổ đĩa.

## 4. Đo độ trễ end-to-end và tình huống ghi file

Đối với yêu cầu “đọc xong một file rồi trả dữ liệu”, nên đo một window bao toàn bộ đường đi tương ứng:

~~~java
long startedAt = System.nanoTime();
long count = 0;
try (InputStream in = Files.newInputStream(path)) {
    byte[] chunk = new byte[64 * 1024];
    int n;
    while ((n = in.read(chunk)) != -1) {
        count += n;
        // Nếu nghiệp vụ có parse/transform, đặt ở đây để đo chung end-to-end.
    }
}
long elapsed = System.nanoTime() - startedAt;
~~~

Đây là **đoạn mã đặt trong một phương thức** có biến `Path path` và xử lý `IOException`; không phải lớp standalone. `elapsed` bao gồm thao tác mở, đọc đến hết, đóng tệp và xử lý trong vòng lặp.

Đo **ghi** lại có nhiều tầng hoàn thành khác nhau:

1. `OutputStream.write(...)` trả về: bytes đã được giao cho các tầng buffer/provider tương ứng; chưa đồng nghĩa dữ liệu nằm bền vững trên thiết bị.
2. `flush()` của stream có buffer: đẩy dữ liệu khỏi buffer của ứng dụng xuống tầng tiếp theo; chưa tương đương cam kết durable trên ổ đĩa.
3. `FileChannel.force(true)` hoặc `FileDescriptor.sync()`: yêu cầu các thay đổi thích hợp được đẩy xuống thiết bị lưu trữ theo hợp đồng API/hệ điều hành, với caveat về thiết bị và hệ thống tệp.

Nếu benchmark tuyên bố đo **durable write latency**, phải bao cả bước `force`/`sync` trong ranh giới latency. Nếu chỉ đo throughput của `write` vào bộ đệm mà đem so với giải pháp khác có `fsync` ở mỗi giao dịch, kết luận sẽ không công bằng.

Ví dụ **minh họa cách đặt ranh giới** khi dùng `FileChannel`:

~~~java
long start = System.nanoTime();
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    ByteBuffer data = ByteBuffer.wrap(payload);
    while (data.hasRemaining()) {
        channel.write(data);
    }
    channel.force(true);
}
long durableWriteNanos = System.nanoTime() - start;
~~~

Các biến `path` (`Path`) và `payload` (`byte[]`) được truyền từ mã gọi. Cần import `java.nio.ByteBuffer`, `java.nio.channels.FileChannel` và `java.nio.file.StandardOpenOption`. Đây là đoạn minh họa trong phương thức có xử lý `IOException`. `channel.write` có thể ghi ít hơn `ByteBuffer.remaining()`, do đó cần vòng `while (data.hasRemaining())`.

## 5. Đo bộ nhớ: Java heap không đại diện cho toàn bộ RAM

### 5.1. Những phạm vi bộ nhớ phải phân biệt

| Chỉ số | Ý nghĩa | Cách quan sát điển hình |
| --- | --- | --- |
| `heap.used` | Số bytes đang dùng trong Java heap theo cơ chế đo của JVM | `MemoryMXBean`, JFR, GC logs |
| `heap.committed` | Bộ nhớ JVM đã cam kết cho heap | `MemoryUsage.getCommitted()` |
| `heap.max` | Giới hạn heap, có thể là giá trị “không xác định” tùy pool/JVM | `MemoryUsage.getMax()`, tùy cấu hình |
| Direct buffer pool | Bộ nhớ liên quan `ByteBuffer.allocateDirect` được quản lý bởi pool | `BufferPoolMXBean` với tên `direct` |
| Mapped buffer pool | Số lượng/kích thước mapped buffer được theo dõi | `BufferPoolMXBean` với tên `mapped` / pool hiện hữu |
| Native memory khác | Thread stacks, metadata, code cache, vùng native của JVM/thư viện | Native Memory Tracking/JFR/OS tùy nguồn |
| RSS / working set | Trang bộ nhớ vật lý đang resident của tiến trình theo OS | Công cụ giám sát tiến trình của OS |
| OS page cache | Trang file cache được OS giữ, có thể phục vụ I/O mà không đọc đĩa | Thống kê hệ điều hành, không phải heap Java |

**Không cộng bừa** `heap.used + direct pool + RSS`: RSS đã bao gồm một số phần của heap/native resident, nên phép cộng có thể đếm trùng. `heap.committed` là khái niệm khác với số trang vật lý thực tế đang resident. File-backed mapping cũng có quan hệ riêng với page cache.

### 5.2. Hai chiến lược xử lý tệp lớn có dấu chân bộ nhớ khác nhau

**Đọc toàn bộ file:**

~~~java
byte[] all = Files.readAllBytes(path);
process(all); // process là hàm của ứng dụng; đoạn này không standalone.
~~~

`readAllBytes` yêu cầu một mảng chứa nội dung file trong heap, có thể phát sinh thêm mảng tạm/chi phí JVM tùy hiện thực. Với file rất lớn, có thể gặp `OutOfMemoryError` hoặc giới hạn kích thước mảng Java. Thích hợp khi file nhỏ, nằm trong giới hạn bộ nhớ và thực sự cần giữ toàn bộ nội dung.

**Đọc streaming theo chunk:**

~~~java
try (InputStream in = Files.newInputStream(path)) {
    byte[] chunk = new byte[64 * 1024];
    int n;
    while ((n = in.read(chunk)) != -1) {
        process(chunk, n); // Ứng dụng xử lý ngay n bytes hợp lệ.
    }
}
~~~

Hai đoạn trên là **mã minh họa** đặt trong phương thức có biến `Path path` và hàm `process` phù hợp, không phải chương trình độc lập. Streaming có thể giữ working set heap gần với kích thước buffer nếu `process` không tích lũy dữ liệu. Nếu `process` giữ tất cả chunk vào `List` hoặc tạo `String` lớn thì **streaming không còn bảo đảm footprint thấp**.

### 5.3. Theo dõi direct/mapped buffer bằng `BufferPoolMXBean`

Chương trình độc lập `BufferPoolDemo.java`:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;

public class BufferPoolDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocateDirect(8 * 1024 * 1024);
        System.out.println("Direct: " + buffer.isDirect());

        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            if (pool.getName().equals("direct")
                    || pool.getName().equals("mapped")) {
                System.out.printf(
                        "%s: count=%d, used=%d, capacity=%d%n",
                        pool.getName(),
                        pool.getCount(),
                        pool.getMemoryUsed(),
                        pool.getTotalCapacity());
            }
        }
    }
}
~~~

~~~bash
javac BufferPoolDemo.java
java BufferPoolDemo
~~~

Dòng đầu cố định:

~~~text
Direct: true
~~~

Các dòng còn lại ghi số buffer, số byte bộ nhớ ước tính pool quản lý và tổng capacity. **Số cụ thể thay đổi giữa các JDK/môi trường và lúc đo**; không nên coi chúng là toàn bộ native memory. `BufferPoolMXBean` còn có thể trả giá trị không xác định cho vài thuộc tính/tình huống; tên các pool khả dụng phụ thuộc JVM. Việc giải phóng direct buffer thường phụ thuộc cơ chế quản lý vòng đời và GC; không giả định rằng một object local hết scope làm native memory lập tức được trả lại.

### 5.4. Cách đo memory peak đúng hơn

Hai snapshot trước/sau như trong `IoMetricsDemo` có thể **bỏ sót đỉnh dùng bộ nhớ ở giữa**. Với ứng dụng dài hạn hoặc áp lực cấp phát lớn:

- Ghi nhiều mẫu `heap.used` trong suốt giai đoạn chạy, kèm timestamp và mức tải; đỉnh trong chuỗi mẫu chỉ là **sampled peak**, không phải tuyệt đối nếu có spike giữa hai lần lấy mẫu.
- Dùng **JDK Flight Recorder (JFR)** hoặc công cụ profiling để quan sát allocation, heap, GC pause và tiến trình chạy. Allocation rate (bytes cấp phát mỗi giây) khác với heap giữ lại.
- Dùng `jcmd <pid> GC.heap_info` hoặc JVM/JMX metrics tùy runtime để xem trạng thái heap tại thời điểm gọi.
- Nếu cần hiểu phần native bên trong JVM, bật **Native Memory Tracking** từ lúc khởi động (`-XX:NativeMemoryTracking=summary`) rồi dùng `jcmd <pid> VM.native_memory summary`; NMT có overhead, không đại diện toàn bộ bộ nhớ bên ngoài JVM mà thư viện native tùy ý quản lý.
- Dùng công cụ OS cho **RSS/working set**, page cache, I/O bytes và page faults; không suy toàn bộ RAM tiến trình từ riêng `-Xmx`.

Các lệnh `jcmd` cần chạy với process/JDK phù hợp và quyền truy cập tiến trình. Nếu không bật NMT khi khởi động, lệnh summary sẽ không cung cấp cùng thông tin chi tiết như phiên đã bật.

## 6. Tránh benchmark sai vì cache, warm-up và cấu hình đo

### 6.1. Cold cache và warm cache

Đọc cùng một file nhiều lần có thể chuyển từ disk-backed I/O sang đọc từ **OS page cache**. Kết quả warm-cache vẫn hữu ích nếu workload sản xuất thật có đọc lặp, nhưng đừng dùng nó đại diện cho tốc độ đọc file mới từ thiết bị. “Đóng stream” hoặc `FileChannel.force(...)` không đồng nghĩa xóa page cache.

Thực hành tốt là báo rõ:

- File mới hay file lặp lại, kích thước file so với RAM, có đọc lại cùng offset hay không.
- Thiết bị và filesystem cục bộ/network, giới hạn cgroup/container và tải nền.
- Kết quả lần chạy đầu so với các lần tiếp theo; nếu cần đo cold cache, sử dụng **phương pháp kiểm soát cache phù hợp với hệ điều hành/thử nghiệm**, chỉ khi có quyền và khi không ảnh hưởng hệ thống dùng chung.
- Đọc tuần tự hay random; access pattern có thể thay đổi throughput rất mạnh do read-ahead và seek.

### 6.2. Warm-up và JIT/GC

JVM có thời gian nạp lớp và biên dịch tối ưu; GC và scheduler có thể tạo spike. Nên chạy warm-up riêng, nhiều lượt đo độc lập, báo median/tail giữa các lượt và giữ cấu hình JVM nhất quán. Không gọi `System.gc()` liên tục để “ổn định” benchmark: không bảo đảm thực hiện như mong muốn và làm méo điều kiện thực.

Đối với microbenchmark CPU hoặc API cực ngắn, dùng **JMH** với fork/warm-up/measurement được cấu hình rõ ràng. Với I/O thật, JMH vẫn không thể tự kiểm soát ổ đĩa, filesystem cache, network, durable write hay phân phối request; phải thiết kế workload và tầng hạ tầng tương ứng. Đừng để bộ đo gây cấp phát nhiều đến mức đo GC thay cho I/O.

### 6.3. Giữ workload công bằng

Khi so `Files.readAllBytes`, `BufferedInputStream`, `FileChannel` hay `MappedByteBuffer`:

1. Đảm bảo cùng dữ liệu, cùng kích thước tổng, cùng điều kiện cache và bộ đo.
2. Phân biệt read-only, write-only, read+parse, copy, checksum, durable write.
3. Có kiểm tra **đúng dữ liệu** hoặc byte count, tránh benchmark xử lý thiếu/tự bỏ công việc.
4. Kiểm soát buffer size, số thread, số thao tác đồng thời và chính sách mở/đóng.
5. Chạy nhiều lần theo thứ tự hoán đổi phù hợp; nếu luôn đo A trước B, lợi thế cache/JIT có thể thuộc về B.
6. Giám sát CPU, GC, I/O wait, page faults, heap, direct memory và RSS song song để giải thích throughput/latency.

Không có API “nhanh nhất” trong mọi workload. `Files.readAllBytes` có thể nhanh và thuận tiện với file nhỏ nhưng tăng peak heap; `FileChannel` và streaming thường hợp lý cho file lớn; memory mapping hữu ích ở một số kiểu random access nhưng cần tính đến page faults, lifetime mapping và virtual address space.

## 7. Kết hợp throughput, latency và memory để chẩn đoán

| Quan sát | Giả thuyết có thể kiểm tra | Phép đo tiếp theo |
| --- | --- | --- |
| Throughput cao, `p99` tăng mạnh | Hàng đợi, GC, cạnh tranh thread/lock, jitter I/O | p99 ở request-level, queue wait, GC pause, I/O latency |
| Throughput không tăng khi tăng concurrency | Thiết bị đã bão hòa, contention, scheduling overhead | Disk utilization, CPU, context switching, queue depth |
| Throughput tăng nhưng RSS tăng nhanh | Direct/mapped buffers, page cache, native allocation | Buffer pools, NMT, RSS, heap snapshots |
| Heap tăng tuyến tính theo kích thước file | `readAllBytes`, tích lũy record/byte arrays, giữ reference | Heap allocations và retained objects |
| Heap ổn định nhưng tiến trình vẫn dùng nhiều RAM | Direct memory/native/threads/mapping | BufferPoolMXBean, NMT, RSS |
| Lượt chạy đầu chậm, lượt sau nhanh | Page cache hoặc warm-up | So cold/warm, quan sát disk read bytes |
| `write` nhanh nhưng dữ liệu chưa durable | Đo trước `flush/force/sync` | Đo thời gian hoàn thành sau force/sync |
| `p50` ổn nhưng `p99` rất xấu | Tail bị ảnh hưởng bởi số ít yêu cầu chậm | Histogram đủ mẫu, trace mẫu chậm nhất, đo từng giai đoạn |

Các hàng chỉ là **giả thuyết cần xác minh**; một triệu chứng có thể có nhiều nguyên nhân. Ví dụ một thao tác chậm do network filesystem có thể khiến throughput suy giảm nhưng heap không đổi. Đặt các metrics lên cùng timeline thường hiệu quả hơn đọc một ảnh chụp rời rạc.

## 8. Cách lập báo cáo benchmark có thể tái lập

Ví dụ cấu trúc báo cáo (đây là **mẫu điền kết quả**, không phải số benchmark thực tế):

| Mục | Nội dung cần ghi |
| --- | --- |
| Mục tiêu | Đọc tuần tự tệp lớn, hoặc xử lý một request tải lên |
| Phạm vi latency | Một lần `read` / một file / một request |
| Data size và pattern | Kích thước tệp, chunk size, tuần tự/random, nén hay không |
| Runtime | JDK version, heap flags, GC, số worker |
| Máy và I/O | CPU, RAM, ổ đĩa/network filesystem, OS, page cache |
| Phương pháp | Số lượt warm-up, số lượt đo, số mẫu, cách tính percentile |
| Throughput | MiB/s và tổng bytes/thời gian |
| Latency | p50/p95/p99, đơn vị ms hoặc µs, rõ cấp đo |
| Memory | heap used/committed/peak sampled, direct pool, RSS, allocation rate |
| Độ tin cậy | Độ biến thiên, điều kiện cache, giới hạn và observer overhead |

Khi tối ưu, cần giữ lại **baseline trước thay đổi**, sau đó chạy cùng workload với phiên bản mới. Hãy ghi cả tác động trade-off: tăng buffer từ 8 KiB lên 256 KiB có thể tăng throughput trên một máy nhưng làm tốn thêm RAM cho mỗi kết nối đồng thời, hoặc giảm tốc độ do GC/cache pressure ở quy mô khác.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Chương trình đọc 200 MiB trong 2,5 giây. Throughput là bao nhiêu?

**Đáp án:** `200 / 2.5 = 80 MiB/s`. Đơn vị là MiB nếu đầu vào tính theo MiB; chuyển sang MB/s cần đổi đơn vị trước khi tính.

**Câu 2.** Có thể lấy p95 của từng lệnh `read` để gọi là p95 “thời gian upload request” không?

**Đáp án:** Không. Request latency có thể gồm hàng đợi, nhiều lần read/write, xử lý và phản hồi. Phải đo từ đầu đến cuối yêu cầu nếu đó là SLA cần đánh giá.

**Câu 3.** Hai snapshot heap trước và sau đều 70 MiB. Có thể kết luận peak heap chỉ 70 MiB?

**Đáp án:** Không. Có thể đã cấp phát rất nhiều và GC thu gom giữa hai ảnh chụp, hoặc có spike ở thời điểm không lấy mẫu; cần lấy mẫu xuyên suốt/JFR/profiler. Direct memory và RSS còn nằm ngoài `heap.used`.

**Câu 4.** Vì sao đọc 5 lượt file 32 MiB có thể cho throughput cao hơn đọc lần đầu tệp mới?

**Đáp án:** OS page cache, readahead, warm-up JVM và nhiều yếu tố khác. Khi buffer file đã resident trong RAM, kết quả không còn đo thuần tốc độ ổ đĩa lạnh.

**Câu 5.** Vì sao `flush()` trên buffered stream chưa đủ để báo “ghi dữ liệu bền vững”?

**Đáp án:** `flush` chủ yếu đẩy dữ liệu khỏi buffer của tầng stream xuống tầng dưới. Durability có thể cần `FileChannel.force` hoặc `FileDescriptor.sync`, tính đến giới hạn thiết bị/OS và yêu cầu nghiệp vụ.

**Câu 6.** Nếu throughput tăng 20% nhưng p99 yêu cầu tăng gấp ba và RSS vượt giới hạn container, giải pháp đã tốt hơn chưa?

**Đáp án:** Chưa thể kết luận. Phải đánh giá đồng thời SLA latency, budget bộ nhớ, tải mục tiêu và chi phí vận hành. Nếu yêu cầu về latency/RAM bị vi phạm thì throughput cao hơn không đồng nghĩa tối ưu thành công.

## 10. Tóm lược thực hành

1. **Nói rõ đang đo thao tác gì và theo đơn vị nào.** `MiB/s`, `ops/s`, `p95 read()` hay `p95 request` có nghĩa khác nhau.
2. **Chỉ đếm công việc đã hoàn tất và dữ liệu đã thực sự truyền.** Dùng `System.nanoTime()` cho elapsed, đếm bytes theo kết quả `read`/`write` phù hợp.
3. **Đo đồng thời nhưng hiểu nguồn đo:** heap Java, direct/mapped, native và RSS là các lát cắt khác nhau; snapshot không phải peak.
4. **Tách workload và nhiễu:** khâu chuẩn bị tệp, cache, warm-up, JIT, GC, instrumentation và durability đều ảnh hưởng đến số đo.
5. **So sánh có kiểm soát, nhiều lượt, có tail percentile và điều kiện môi trường.** Kết quả đáng tin là kết quả người khác có thể tái lập và giải thích.

Với tệp lớn, cách tối ưu đáng tin nhất thường bắt đầu bằng benchmark theo workload thật, xác định nút nghẽn, rồi chỉ thay buffer/API/concurrency khi có số đo chứng minh thay đổi đáp ứng đồng thời mục tiêu tốc độ, độ trễ và bộ nhớ.
