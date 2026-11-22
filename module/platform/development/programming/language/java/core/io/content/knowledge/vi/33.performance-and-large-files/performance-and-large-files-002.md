# Chọn kích thước buffer theo phép đo trong Java I/O và xử lý tệp lớn

## 1. Tại sao không có một kích thước buffer tối ưu chung?

Khi đọc và ghi tệp lớn, chương trình Java có thể sử dụng `InputStream`, `BufferedInputStream`, `BufferedOutputStream`, `FileChannel` và `ByteBuffer`. Kích thước vùng đệm (buffer size) là số byte có thể được gom hoặc chuyển trong một lượt thao tác. Nó tác động đến **số lần gọi I/O**, **CPU**, **throughput**, **latency**, **heap/direct memory** và khả năng phục vụ nhiều tác vụ đồng thời.

Buffer quá nhỏ dễ tăng overhead vì chương trình phải thực hiện nhiều lượt đọc/ghi. Tuy nhiên, **tăng buffer mãi không đồng nghĩa tốc độ tăng mãi**: khi thiết bị lưu trữ, hệ điều hành, cache hoặc CPU đã đạt ngưỡng, vùng đệm lớn hơn có thể gần như không cải thiện thông lượng mà vẫn tiêu tốn thêm RAM.

Do đó, câu trả lời đúng cho câu hỏi “nên dùng 4 KiB, 8 KiB, 64 KiB, 256 KiB hay 1 MiB?” là **chọn bằng phép đo trên workload thực tế**. Không có một con số cố định áp dụng được cho SSD/HDD, NFS, file vài kilobyte hay file hàng trăm gigabyte.

Bài thuộc **Java Core I/O → Hiệu năng và tệp lớn**. Nội dung hướng dẫn xác định biến đo, thiết kế benchmark, phân biệt heap/direct buffer, chạy chương trình Java 17+, phân tích độ bão hòa và lựa chọn kích thước cân bằng giữa hiệu năng và tài nguyên.

## 2. Cơ chế: buffer ảnh hưởng số lượt gọi I/O như thế nào?

Giả sử cần đọc tuần tự một tệp đúng 1 GiB (1.073.741.824 byte). **Nếu mỗi lần đọc đều lấp đầy buffer**, số lần đọc lý thuyết là:

| Buffer | Số lượt đọc đầy buffer cho 1 GiB |
| ---: | ---: |
| 4 KiB | 262.144 |
| 8 KiB | 131.072 |
| 16 KiB | 65.536 |
| 64 KiB | 16.384 |
| 256 KiB | 4.096 |
| 1 MiB | 1.024 |

Công thức tổng quát:

```text
estimatedCalls = ceil(fileBytes / bufferCapacity)
```

Đây **không phải số syscall thực tế được API cam kết**: một lời gọi `read()` có thể nhận ít byte hơn yêu cầu, và một số tầng stream hay filesystem provider có thể thực hiện nhiều thao tác ngầm. Nếu buffer 64 KiB còn đủ chỗ nhưng `read()` chỉ trả 1 KiB, lần đó vẫn hoàn toàn hợp lệ.

Với `FileChannel.read(ByteBuffer)`, một mẫu cơ bản là:

```java
ByteBuffer buffer = ByteBuffer.allocate(64 * 1024);

try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    while (true) {
        buffer.clear();
        int n = channel.read(buffer);

        if (n == -1) break;
        if (n == 0) continue;

        buffer.flip();
        while (buffer.hasRemaining()) {
            byte value = buffer.get();
            // Xử lý byte thuộc lượt đọc hiện tại.
        }
    }
}
```

Đây là **snippet trong phương thức**, cần `import java.nio.*`, `import java.nio.channels.FileChannel`, `import java.nio.file.*`, biến `path` và xử lý `IOException`. Nó minh họa cách đọc đúng, không phải benchmark. Nếu một channel có thể liên tục trả `0`, không nên dùng vòng `continue` không có cơ chế chờ phù hợp. Với một file channel đọc vào buffer còn chỗ, kết quả `0` thường không phải trạng thái lặp mãi.

`clear()` **chỉ đặt lại** `position=0`, `limit=capacity`, không xóa dữ liệu cũ. `flip()` giới hạn phần đọc đúng số byte mới nhận; parser không được đọc toàn bộ mảng backing rồi vô tình dùng byte của lượt trước.

### 2.1. Khi buffer nhỏ gây overhead

- Nhiều lần gọi phương thức Java và có thể nhiều thao tác native I/O hơn.
- Nhiều lần quản lý `position`, `limit`, loop branch hoặc gọi parser/decoder.
- Nếu application flush hoặc ghi những block quá nhỏ, chi phí đồng bộ hóa/flush có thể cao.
- Với kết nối có latency hoặc server có nhiều request, số lượt xử lý tăng làm throughput/CPU xấu đi.

### 2.2. Khi buffer lớn đem lại hiệu quả giảm dần

- Đĩa, OS cache hoặc CPU parser có thể đã là bottleneck.
- Nhiều request đồng thời giữ các vùng đệm lớn, gây heap/direct-memory pressure.
- Copy, giải mã, checksum hay logic nghiệp vụ có thể áp đảo lợi ích giảm lượt đọc.
- Nếu tầng ứng dụng cố gom đầy buffer trước khi xử lý thì **time-to-first-result** có thể tăng, nhưng không được nhầm với hành vi mặc định của mọi `read()`: Java không luôn đợi buffer đầy.
- File nhỏ hơn buffer có thể không được lợi từ tăng kích thước.

Từ đây hình thành nguyên tắc: **tìm điểm hiệu năng bão hòa, sau đó ưu tiên cấu hình nhỏ và ổn định**.

## 3. Những loại buffer cần phân biệt

### 3.1. Heap ByteBuffer

```java
ByteBuffer buffer = ByteBuffer.allocate(64 * 1024);
```

Heap buffer lưu byte trong heap Java, có backing array và thường thuận tiện cho code xử lý `byte[]`. Cấp phát nhiều buffer mới có thể tạo thêm object và áp lực GC.

Với đọc file theo stream, **tái sử dụng một buffer** ngoài vòng lặp thường quan trọng hơn việc tranh luận 64 KiB hay 128 KiB.

### 3.2. Direct ByteBuffer

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);
```

Direct buffer thường sử dụng memory ngoài Java heap. Theo tài liệu `ByteBuffer`, JVM sẽ **best effort** tận dụng native I/O trực tiếp để tránh một số bước copy trung gian. Điều đó **không bảo đảm** direct luôn nhanh hơn heap.

Đặc điểm cần đo:

- Chi phí cấp phát/giải phóng direct thường cao hơn non-direct.
- Dung lượng direct memory vẫn là tài nguyên thật, có quota và rủi ro `OutOfMemoryError`.
- `buffer.array()` không thể giả định hoạt động với direct buffer.
- `clear()` không giải phóng hay xóa vùng nhớ.
- Tạo direct buffer một lần rồi tái sử dụng là lựa chọn khác hẳn tạo direct buffer ở mỗi request.

Nếu cần so heap và direct, **giữ nguyên các tham số khác**: cùng file, kích thước, kiểu truy cập, số luồng, warm-up và cách xử lý byte.

### 3.3. BufferedInputStream/BufferedOutputStream

```java
try (InputStream in = new BufferedInputStream(
        Files.newInputStream(path), 64 * 1024)) {
    // Đọc file theo API InputStream.
}
```

Đoạn này cần import `java.io.*`, `java.nio.file.*`, cùng biến `path`.

`BufferedInputStream` hữu ích khi ứng dụng thực hiện nhiều lần đọc nhỏ, đặc biệt đọc từng byte hoặc khối rất ngắn. Nhưng nếu ứng dụng đã đọc block lớn bằng `FileInputStream.read(byte[])`, thêm một wrapper với buffer nhỏ hơn **không bảo đảm** tăng throughput. Đường xử lý của từng overload, chi phí copy và dữ liệu thực tế mới quyết định kết quả.

Phải phân biệt **buffer của wrapper**, **byte[] do ứng dụng dùng**, **OS page cache** và **buffer của thiết bị**. Chúng tồn tại ở những tầng khác nhau.

### 3.4. Memory-mapped file và transferTo

`FileChannel.map()` cùng `MappedByteBuffer` thay cơ chế truy cập thành vùng nhớ được ánh xạ; `FileChannel.transferTo()` có thể tối ưu việc chuyển byte giữa các channel. Chúng **không đơn giản là chọn một buffer size khác** trong vòng `read()`. Nếu bài toán thực sự là copy file hay random access, hãy benchmark mapping/transfer như những phương án riêng trên cùng đầu ra nghiệp vụ.

## 4. Chọn mục tiêu phép đo trước khi viết code

Một ứng dụng sao lưu có thể coi **throughput** là chỉ số hàng đầu; ứng dụng phục vụ request có thể coi **p99 latency** và memory per connection quan trọng hơn.

| Đại lượng | Ý nghĩa | Cách xem |
| --- | --- | --- |
| Throughput | Tổng MiB xử lý trên một giây | Đo bytes thực nhận / thời gian |
| Per-file latency | Thời gian hoàn thành một tệp | Thống kê median, p95/p99 |
| CPU | Xử lý, copy, parser, checksum | Quan sát CPU utilization/profiler |
| GC | Allocation và pause do heap buffers/objects | JFR, GC log, profiler |
| Direct memory | Bộ nhớ native/direct buffer còn sống | Quota JVM, native memory/profiler |
| I/O calls | Số lần gọi đọc/ghi thực tế | Instrument code hoặc system tracer |
| Peak concurrency | Số request đồng thời giữ buffer | Counter/quota |
| Correctness | Số byte và nội dung thực sự đúng | Byte count, checksum/hash, test |

Công thức tính throughput:

```text
MiB/s = bytesProcessed / (1024 × 1024) / seconds
```

**MiB** (2²⁰ byte) khác **MB** (10⁶ byte). Khi so sánh các bảng kết quả, hãy luôn ghi đúng đơn vị và không dùng số lượng byte theo giả định khi thực tế có partial read/write.

Trước khi chạy, tự trả lời:

- Đọc, ghi, copy, parse hay giải nén?
- SSD local, HDD, NFS, network share hay dữ liệu đã nằm trong cache?
- Tệp điển hình là 1 KiB, 32 MiB, 10 GiB hay hỗn hợp?
- Một job hay hàng nghìn job đồng thời?
- Có cần `force()/fsync` khi ghi để đáp ứng durability?
- Dữ liệu có thể bị thay đổi giữa các lượt đo không?
- Cần ưu tiên throughput, latency hay giới hạn RAM?

## 5. Dải buffer size cần khảo sát

Dải thử ban đầu thường có ích:

```text
4 KiB → 16 KiB → 64 KiB → 256 KiB → 1 MiB
```

Đây là **dãy ứng viên**, không phải một khuyến cáo rằng 1 MiB luôn là tốt nhất. Đo thô theo bậc lớn giúp tìm vùng cải thiện nhanh; sau đó có thể thử thêm 32, 96, 128 hoặc 192 KiB quanh vùng bão hòa.

**Không chọn một giá trị chỉ vì lớn nhất trong một lần benchmark**. Nếu 64 KiB đạt 95% hiệu năng tốt nhất và 1 MiB chỉ nhỉnh hơn trong sai số, 64 KiB có thể là quyết định tốt hơn vì ít tốn memory và dễ hỗ trợ nhiều tác vụ.

Ngưỡng 95% chỉ là một ví dụ về **tiêu chí chọn cấu hình của dự án**, không phải một định luật của JVM.

## 6. Java 17+ chạy được: benchmark đọc file với nhiều kích thước buffer

Chương trình sau tạo một file tạm **16 MiB**, sau đó đo các lượt quét tuần tự bằng `FileChannel.read(ByteBuffer)` với heap và direct buffers. Mỗi cấu hình có hai lượt warm-up và năm mẫu đo; chọn median để giảm ảnh hưởng của một lần bất thường.

**Thiết kế bài đo:**

1. Ghi fixture **ngoài** vùng tính thời gian.
2. Mở channel và cấp buffer **trước** khi bắt đầu đếm `nanoTime()`, để cô lập thời gian đọc loop.
3. Tái sử dụng buffer trong suốt một lượt.
4. Mỗi lượt đọc luôn tới EOF, kiểm tra tổng byte đúng `FILE_BYTES`.
5. Không parse byte, chỉ đếm lượng byte `read()` trả về; đây là benchmark **đọc dữ liệu**, không phải xử lý nghiệp vụ.
6. Không ép làm lạnh OS page cache; các lượt sau có thể chủ yếu đo warm-cache.

Tạo file `BufferSizeBenchmark.java`:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.Locale;

public class BufferSizeBenchmark {
    private static final int FILE_BYTES = 16 * 1024 * 1024;
    private static final int WARMUP = 2;
    private static final int SAMPLES = 5;
    private static final int[] CAPACITIES = {
        4 * 1024, 16 * 1024, 64 * 1024,
        256 * 1024, 1024 * 1024
    };

    private static void createFixture(Path file) throws IOException {
        byte[] block = new byte[8192];
        for (int i = 0; i < block.length; i++) {
            block[i] = (byte) (i & 0xff);
        }

        try (OutputStream out = Files.newOutputStream(file)) {
            int remaining = FILE_BYTES;
            while (remaining > 0) {
                int n = Math.min(remaining, block.length);
                out.write(block, 0, n);
                remaining -= n;
            }
        }
    }

    private static long oneRun(
            Path file, int capacity, boolean direct) throws IOException {

        ByteBuffer buffer = direct
                ? ByteBuffer.allocateDirect(capacity)
                : ByteBuffer.allocate(capacity);

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ)) {

            long bytesRead = 0;
            long started = System.nanoTime();

            while (true) {
                buffer.clear();
                int n = channel.read(buffer);

                if (n == -1) {
                    break;
                }
                if (n == 0) {
                    throw new IOException(
                            "No progress with nonempty buffer");
                }
                bytesRead += n;
            }

            long elapsed = System.nanoTime() - started;
            if (bytesRead != FILE_BYTES) {
                throw new IOException("Read " + bytesRead
                        + " instead of " + FILE_BYTES);
            }
            return elapsed;
        }
    }

    private static void measure(
            Path file, int capacity, boolean direct) throws IOException {

        for (int i = 0; i < WARMUP; i++) {
            oneRun(file, capacity, direct);
        }

        long[] times = new long[SAMPLES];
        for (int i = 0; i < times.length; i++) {
            times[i] = oneRun(file, capacity, direct);
        }

        Arrays.sort(times);
        long medianNs = times[times.length / 2];
        double elapsedSeconds = medianNs / 1_000_000_000.0;
        double throughputMiB = (FILE_BYTES / 1_048_576.0)
                / elapsedSeconds;
        double millis = medianNs / 1_000_000.0;

        System.out.printf(Locale.ROOT,
                "%-6s %5d KiB: median %.3f ms; %.2f MiB/s%n",
                direct ? "direct" : "heap",
                capacity / 1024, millis, throughputMiB);
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("buffer-benchmark-", ".dat");
        try {
            createFixture(file);
            System.out.println("Fixture bytes: " + Files.size(file));

            for (boolean direct : new boolean[] {false, true}) {
                for (int capacity : CAPACITIES) {
                    measure(file, capacity, direct);
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BufferSizeBenchmark.java
java BufferSizeBenchmark
```

Kết quả **dòng đầu tiên cố định** khi file tạm được ghi đúng và đọc được:

```text
Fixture bytes: 16777216
```

Sau đó chương trình in mười dòng, một dòng cho mỗi cấu hình heap/direct và kích thước 4, 16, 64, 256, 1024 KiB. **Các con số thời gian và MiB/s thay đổi theo máy chạy**, vì vậy không có stdout số học cố định đáng tin để chép vào tài liệu. Dạng kết quả là:

```text
heap       4 KiB: median <thời gian> ms; <thông lượng> MiB/s
...
direct  1024 KiB: median <thời gian> ms; <thông lượng> MiB/s
```

Dấu `<...>` và dòng `...` ở trên biểu diễn vị trí **số đo thực tế**, không phải output nguyên văn hoặc kết quả đã đo sẵn. Không trình bày những số liệu giả như benchmark thực.

### 6.1. Phân tích chương trình

- `createFixture()` ghi theo từng block 8 KiB để tạo file 16 MiB mà không cần `byte[]` dài bằng file.
- `oneRun()` cấp một `ByteBuffer` trước khi bắt đầu đo rồi mở `FileChannel` trong `try-with-resources`.
- `buffer.clear()` mở phạm vi nhận dữ liệu từ `position=0` tới `capacity`. Vì bài đo **chỉ đếm byte**, không xử lý nội dung vừa đọc, không cần `flip()` giữa các lượt.
- `read()` trả số byte thực chuyển, `-1` nghĩa là EOF; code từ chối `0` nếu file channel và buffer còn chỗ không tạo tiến triển, tránh một busy loop vô hạn trong demo.
- `bytesRead` được cộng theo **kết quả mỗi lần read**, không ước lượng bằng capacity. Kiểm tra cuối vòng giúp phát hiện fixture bị thiếu hoặc thay đổi.
- Mỗi cấu hình có warm-up và các mẫu measured. Việc sort rồi lấy phần tử giữa là cách tính median đơn giản với năm mẫu.
- `System.nanoTime()` là đồng hồ đo khoảng thời gian, không phải wall-clock dùng để xác định ngày giờ.
- Tổng throughput đo **lượng byte đi qua FileChannel trong timed loop**, không bao gồm tạo file, cấp phát ByteBuffer, mở/đóng channel hoặc parse dữ liệu.

**Đây không phải benchmark end-to-end hay benchmark cold-disk.** Nó minh họa phương pháp lựa chọn cấu hình. Nếu production liên tục cấp phát buffer theo request, phải làm thêm thí nghiệm gồm chi phí allocation và lifecycle.

### 6.2. Vì sao ví dụ chưa đủ để công bố bảng xếp hạng?

- Thứ tự chạy là heap trước, direct sau. Nhóm sau có thể hưởng lợi từ page cache đã nóng hơn; cần đảo hoặc random hóa thứ tự trong thí nghiệm nghiêm túc.
- File 16 MiB có thể nằm trọn trong OS page cache. Con số cao không chứng minh ổ đĩa vật lý đạt tốc độ đó.
- `read` loop không parse nội dung, chưa đo CPU xử lý CSV/JSON/UTF-8 hay copy dữ liệu sang đầu ra.
- Buffer được cấp trước đồng hồ đo; chi phí cấp phát direct không nằm trong elapsed time.
- Số mẫu nhỏ, điều kiện nhiệt/CPU và tiến trình khác có thể làm nhiễu.
- `FileChannel` được mở mới cho từng lượt nhưng điều đó **không làm lạnh OS page cache**.

Nếu kết quả có chênh lệch nhỏ, cần lặp lại phép đo với thứ tự đổi ngẫu nhiên, file lớn hơn và cùng cấu hình JVM/OS. Đối với quyết định production, benchmark đúng đường đi đọc và xử lý **thực sự được chạy**.

## 7. Cách chọn từ bảng số đo: điểm bão hòa

Giả sử **chỉ để minh họa** một hệ thống cho bảng sau (không phải kết quả thực tế của chương trình ở trên):

| Buffer | Throughput giả định | Buffer memory / 1 tác vụ |
| ---: | ---: | ---: |
| 4 KiB | 320 MiB/s | 4 KiB |
| 16 KiB | 760 MiB/s | 16 KiB |
| 64 KiB | 940 MiB/s | 64 KiB |
| 256 KiB | 970 MiB/s | 256 KiB |
| 1 MiB | 973 MiB/s | 1 MiB |

Từ 4 KiB tới 16 KiB tăng nhiều; từ 64 KiB tới 1 MiB chỉ tăng khoảng 3,5% trong bảng giả định, nhưng tiêu thụ buffer lớn gấp 16 lần. Nếu sai số benchmark đã gần 5%, không có đủ bằng chứng rằng 1 MiB thực sự tốt hơn.

**Cách quyết định có căn cứ:**

1. Loại giá trị không đáp ứng correctness, gây quá tải, tốn RAM hoặc p99 latency xấu.
2. Tìm kích thước nhỏ nhất đạt mục tiêu hiệu năng, ví dụ trong vòng 95% throughput tốt nhất đã thấy.
3. Nếu chênh lệch nằm trong nhiễu, đo thêm thay vì khẳng định có “winner”.
4. Nếu một cấu hình nhanh hơn nhưng tiêu thụ bộ nhớ nhiều, đặt nó vào bối cảnh **số tác vụ đồng thời**.
5. Chốt giá trị rồi benchmark lại với file size, concurrency và môi trường production.

**Giá trị “95%” là ngưỡng chọn có thể áp dụng của dự án, không phải hằng số của Java.** Với nhiệm vụ nhạy cảm latency, hãy chọn theo p95/p99 và throughput tối thiểu thay vì chỉ tối đa hóa MB/s.

## 8. Bộ nhớ, GC và tác vụ song song

Nếu mỗi tác vụ giữ một buffer riêng:

```text
estimatedBufferMemory = activeOperations × bufferCapacity
```

Ví dụ 512 job cùng lúc:

| Buffer mỗi job | Tổng vùng byte trước overhead |
| ---: | ---: |
| 8 KiB | 4 MiB |
| 64 KiB | 32 MiB |
| 256 KiB | 128 MiB |
| 1 MiB | 512 MiB |

Đây chỉ là tổng buffer, **chưa kể** object headers, queue, file descriptors, TLS, page cache, parser objects, class metadata và native resources.

Với heap buffers, nhiều lần allocate có thể tạo GC pressure. Với direct buffers, phần memory có thể không hiển thị đầy đủ trong heap metrics, vì thế cần đo native/direct memory riêng.

**Không dùng một buffer chung cho nhiều thread cùng ghi nếu không đồng bộ.** `ByteBuffer` có state `position/limit` không thread-safe. Nếu dùng buffer pool, bảo đảm một buffer chỉ có một owner tại mỗi thời điểm, chỉ trả lại pool khi I/O đã kết thúc và consumer đã xử lý xong.

### 8.1. Buffer và giới hạn in-flight

Khi server có nhiều upload/download hoặc asynchronous file requests, chỉ tăng buffer size mà không giới hạn số operations đang chạy có thể làm cạn tài nguyên.

Một thiết kế cân bằng có thể kết hợp:

- Buffer 64 KiB hoặc 128 KiB cho mỗi job (sau khi đo).
- Số job in-flight tối đa theo `Semaphore`/bounded queue.
- Quota số byte pending ở đầu vào và đầu ra.
- Giới hạn số file handles/sockets mở.
- Backpressure nếu consumer không xử lý kịp.

Ở hệ thống nhiều request, **buffer size tối ưu riêng cho một job** có thể không phải giá trị tối ưu cho **toàn dịch vụ**.

## 9. Bài toán đọc tệp khác sao chép tệp

Benchmark `FileChannel.read(buffer)` không thay thế benchmark **copy**, vì copy còn phải ghi sang đích.

Snippet sao chép qua hai channel:

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);

while (true) {
    buffer.clear();
    int n = source.read(buffer);
    if (n == -1) {
        break;
    }
    if (n == 0) {
        continue;
    }

    buffer.flip();
    while (buffer.hasRemaining()) {
        destination.write(buffer);
    }
}
```

Đoạn này minh họa trong phương thức có `FileChannel source` và `FileChannel destination` đã mở. Với channel có thể liên tục trả `0`, cần cơ chế chờ/giới hạn thích hợp để tránh busy loop. **Partial write** là bình thường: một lần `write()` có thể tiêu thụ ít byte hơn phần còn lại của buffer. Không được `clear()` ngay nếu còn byte chưa gửi/ghi.

Đối với bài toán copy file, benchmark thêm `FileChannel.transferTo`/`transferFrom` theo giới hạn provider và kết quả thực chuyển. Việc truyền trực tiếp có thể hiệu quả hơn tự copy qua buffer, nhưng không được mặc định.

### 9.1. Ghi file và durability

Một lời gọi `write()` thành công có thể chỉ có nghĩa dữ liệu đã được nhận trong các tầng I/O/cache, chưa chứng minh dữ liệu đã nằm trên thiết bị lưu trữ một cách bền vững.

Nếu nghiệp vụ yêu cầu durability, phải định nghĩa chính sách `FileChannel.force(true)` hoặc cơ chế sync tương đương theo hợp đồng API và đo chúng **công bằng**. Không so một phép đo có `force()` sau mỗi block với phép đo không `force()` rồi kết luận do buffer size.

Đối với file ghi mới, việc cấp phát dung lượng, filesystem journaling, metadata updates và storage cache có thể là nhân tố lớn hơn cỡ buffer.

## 10. Workload xử lý văn bản/JSON/CSV

Nếu nhiệm vụ thực là đọc tệp CSV, log, JSON Lines hoặc dữ liệu UTF-8:

- Kích cỡ buffer ảnh hưởng số lượt lấy byte, nhưng parser vẫn phải xử lý delimiters, quotes, escape và ký tự nhiều byte.
- Một ký tự UTF-8 có thể nằm qua ranh giới buffer; cần decoder streaming phù hợp.
- `BufferedReader.readLine()` có logic vùng đệm riêng; không thể áp trực tiếp kết quả đo vòng `FileChannel.read` vào nó.
- Nếu code giữ mọi dòng vào `List<String>`, heap có thể bị chi phối bởi dữ liệu đã parse chứ không phải read buffer.
- Parsing/validation/checksum có thể là bottleneck sau khi I/O đã đủ nhanh.

Khi đo parser thật, thời gian phải bao gồm **đọc, giải mã, parse và tiêu thụ dữ liệu** theo đúng yêu cầu. Nên có một phép đo end-to-end và một phép đo read-only để biết đang tối ưu đúng chỗ hay chưa.

## 11. Quy trình benchmark đáng tin cậy

1. **Xác định câu hỏi**: tìm size giúp tăng throughput, giảm latency, hay giảm áp lực RAM?
2. **Chọn dữ liệu đại diện**: file sizes và định dạng gần production, số lượng file tương ứng.
3. **Định nghĩa điều kiện cache**: warm-cache, cold-ish hoặc môi trường test được kiểm soát; đừng gọi file cache lạnh chỉ vì mở lại stream.
4. **Warm-up JVM**: khởi động, load class/JIT, thực thi nhiều lượt trước phần measured.
5. **Thử nhiều sizes**: ví dụ 4/16/64/256/1024 KiB.
6. **Đổi thứ tự**: random hóa thứ tự cấu hình trong các vòng lặp để giảm bias do cache và drift theo thời gian.
7. **Đo nhiều mẫu**: median, phân phối, min/max, p95/p99 khi đủ mẫu; không chỉ lấy một kết quả tốt nhất.
8. **Đo heap và direct riêng**: cần cùng kiểu công việc, allocation policy và quota rõ ràng.
9. **Quan sát tài nguyên**: CPU, GC, heap, native/direct memory, queue length, I/O counters.
10. **Kiểm tra correctness**: đúng số byte, checksum/hash hoặc kết quả parser; benchmark làm sai dữ liệu không có giá trị.
11. **Đo end-to-end**: nếu nghiệp vụ cần parse, copy, nén hoặc force, đưa những thao tác ấy vào thí nghiệm ứng dụng.
12. **Ghi metadata**: vendor/version JDK, JVM flags, OS, filesystem, CPU, RAM, thiết bị, kích thước file, concurrency và cấu hình cache.
13. **Chốt lựa chọn có ngân sách**: chọn size nhỏ nhất đáp ứng throughput/latency và tài nguyên.
14. **Lặp lại khi môi trường đổi**: nâng JDK, đổi SSD, tăng concurrency hoặc thay parser có thể làm optimum thay đổi.

### 11.1. Warm-cache và cold-cache

Hệ điều hành có page cache. Sau lần đọc đầu, file thường được cache nên lượt sau có thể nhanh hơn mà không liên quan hoàn toàn tới kích thước buffer.

- **Warm-cache test** giúp kiểm tra chi phí đường đi từ cache tới ứng dụng.
- **Cold-storage test** nhằm đo ảnh hưởng của thiết bị lưu trữ, nhưng phải kiểm soát cache bằng phương án phù hợp môi trường test.
- Chỉ gọi `FileChannel.close()` rồi mở lại **không xóa OS page cache**.
- File lớn hơn RAM có thể hạn chế khả năng cache toàn bộ, nhưng không bảo đảm mọi byte của lượt đọc là “cold”.

Không nên sử dụng lệnh drop caches hay điều chỉnh hệ thống production một cách tùy tiện chỉ để tạo kết quả benchmark.

### 11.2. JIT, CPU và GC

Dùng `System.nanoTime()` để đo khoảng thời gian, không dùng đồng hồ ngày giờ. JIT compilation, CPU governor, thermal throttling, background processes và scheduler đều có thể ảnh hưởng phép đo.

Java Flight Recorder (JFR), JDK Mission Control hoặc profiler phù hợp giúp xem allocation, CPU hotspots và GC pauses. Đừng kết luận direct buffers nhanh hơn nếu mọi thứ khác thay đổi giữa hai lượt thử.

### 11.3. JMH có đủ không?

JMH (Java Microbenchmark Harness) hữu ích để đo **đoạn tính toán trong JVM** với warm-up, forks và các kiểm soát microbenchmark. Tuy nhiên, I/O với filesystem còn phụ thuộc OS page cache, storage, network và cả máy chủ đang chạy. Dùng JMH **không tự biến** một phép đo file đã cache thành benchmark ổ đĩa lạnh hoặc kiểm định hiệu năng production.

Nên kết hợp microbenchmark cho parser/codec với phép đo I/O tích hợp và tải thật.

## 12. Kích thước buffer cho network không phải kích thước TCP packet

Với `SocketChannel`, `AsynchronousSocketChannel`, buffer cần cân đối:

- Kích thước message/frame của protocol.
- Số lượng client/connections.
- Inbound/outbound queues và backpressure.
- Partial read/write, `read()==0` và `read()==-1`.
- Độ trễ phản hồi, số lần selector/completion callback.
- TLS/encoding overhead khi có tầng bảo mật.
- Memory quota nếu mỗi connection giữ một buffer.

Không lấy MTU hoặc một TCP segment làm “buffer size bắt buộc”. `ByteBuffer.capacity()` và `SO_RCVBUF`/`SO_SNDBUF` thuộc những tầng khác nhau.

Nếu một server có 20.000 connections và cấp 1 MiB mỗi connection, chỉ riêng vùng buffer có thể lên tới khoảng 19,5 GiB. Con số này có thể là vấn đề lớn dù benchmark file đơn luồng cho thấy 1 MiB nhanh hơn đôi chút.

## 13. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chọn 1 MiB vì “to là nhanh” | Lãng phí RAM, không chắc tăng tốc | Đo nhiều kích thước và điểm bão hòa |
| Chỉ chạy benchmark một lượt | Nhiễu JIT/cache/scheduler | Warm-up, lặp mẫu, đổi thứ tự |
| Dùng file quá nhỏ | Chủ yếu đo cache/overhead khác | Dataset đại diện |
| Mở lại channel và gọi là cold-cache | OS cache còn giữ dữ liệu | Ghi rõ warm-cache/cold-storage điều kiện |
| So heap với direct nhưng đổi cả workload | Không biết tác nhân gây khác biệt | Chỉ đổi một biến mỗi lần |
| Allocate direct buffer trong vòng read | Tốn native memory và allocation cost | Reuse buffer, quota |
| Chỉ nhìn throughput | Có thể làm p99 hoặc GC xấu | Đo latency/memory/CPU cùng lúc |
| Lấy `buffer.array()` như toàn bộ dữ liệu đọc | Có byte cũ và vùng ngoài limit | `flip()` rồi dùng `remaining()` |
| Coi `read()==0` là EOF | Bỏ dở dữ liệu/đóng sớm | EOF là `-1` |
| Gọi `clear()` khi write chưa hết byte | Mất trạng thái pending | Lặp `hasRemaining()` hoặc chờ khả năng ghi |
| Dùng `(int) fileSize` để cấp buffer | Overflow với file lớn | Dùng buffer cố định, fileSize/offset kiểu `long` |
| Đo read rồi suy ra tốc độ CSV parser | Bỏ qua CPU decode/parse/alloc | Benchmark end-to-end |
| Đo write nhưng không force rồi kết luận durability | Không đo đúng hợp đồng bền vững | Định nghĩa flush/force policy |
| Thấy khác biệt 1% và tuyên bố chiến thắng | Có thể nằm trong nhiễu | Đo phân phối, chạy lặp |
| Không tính buffers × concurrency | Hết heap/direct memory khi nhiều job | Quota và backpressure |

## 14. Thực hành và lời giải

**Câu 1.** Tệp 1 GiB với buffer 4 KiB và 64 KiB có số lần đọc *đầy buffer* lý thuyết lần lượt bao nhiêu?

**Đáp án:** 262.144 và 16.384, chênh 16 lần. Số syscall thực tế có thể khác vì mỗi read có thể ngắn.

**Câu 2.** Vì sao buffer 256 KiB không chắc nhanh gấp bốn lần buffer 64 KiB?

**Đáp án:** Overhead giảm theo cách không tuyến tính; thiết bị lưu trữ, page cache, CPU và parser có thể đã bão hòa.

**Câu 3.** `ByteBuffer.allocateDirect()` có chắc ít tốn RAM hơn `allocate()`?

**Đáp án:** Không. Nó có thể dùng native/direct memory ngoài heap, vẫn chiếm tài nguyên và có quota riêng.

**Câu 4.** Sau năm lượt đọc cùng một file, lượt thứ sáu rất nhanh. Đó có chắc là tốc độ SSD thật không?

**Đáp án:** Không. OS page cache có thể làm nhiều byte đến từ RAM; cần hiểu điều kiện đo.

**Câu 5.** 512 operations đồng thời, buffer mỗi operation 1 MiB. Tổng buffer byte bao nhiêu?

**Đáp án:** 512 MiB, chưa tính overhead. Nếu dùng 64 KiB chỉ là 32 MiB.

**Câu 6.** Tại sao benchmark chỉ đếm byte trong ví dụ không dùng `flip()`?

**Đáp án:** Vì nó không đọc nội dung từ ByteBuffer sau `FileChannel.read`, chỉ đọc số byte trả về. Code thực sự cần parse byte phải `flip()` trước khi consume.

**Câu 7.** Buffer được cấp trước `System.nanoTime()`. Benchmark đo được chi phí allocation không?

**Đáp án:** Không. Muốn đánh giá workload liên tục tạo buffer, cần thử nghiệm thứ hai có tính allocation và GC/native memory.

**Câu 8.** Nếu throughput giữa 64 KiB và 1 MiB khác 2%, nhưng độ biến động phép đo khoảng ±5%, nên làm gì?

**Đáp án:** Không tuyên bố 1 MiB chắc nhanh hơn. Đo thêm, giảm nhiễu và cân nhắc dùng buffer ít tốn RAM.

**Câu 9.** Tại sao cần dùng `hasRemaining()` khi ghi qua channel?

**Đáp án:** `write()` có thể tiêu thụ một phần dữ liệu. Nếu còn byte trong buffer phải tiếp tục/chờ, không gọi `clear()` sớm.

**Câu 10.** Benchmark file read-only có thể dùng để kết luận buffer tốt nhất cho parser JSON Lines không?

**Đáp án:** Không đủ. Parser còn decode, tạo object, xử lý ranh giới và tiêu thụ CPU/GC; cần benchmark đúng luồng nghiệp vụ.

## 15. Checklist đưa vào production

1. Đã biết workload đọc/ghi/copy/parse và thước đo mục tiêu?
2. Đã thử ít nhất một dải kích thước có tính hệ thống?
3. Đã phân biệt heap/direct/wrapper/mapped/transfer?
4. Đã dùng warm-up, nhiều mẫu, đổi thứ tự để tránh bias?
5. Đã ghi điều kiện page cache và tính năng storage?
6. Đã kiểm tra tính đúng của số byte, payload, EOF/partial write?
7. Đã tính `bufferSize × maxConcurrentOperations` và các queue khác?
8. Đã đo throughput **và** latency/GC/memory ở tải dự kiến?
9. Đã chọn kích thước dựa trên điểm bão hòa cùng memory budget?
10. Đã lưu kết quả benchmark và điều kiện để lần nâng JDK/thiết bị đo lại?

**Ghi nhớ:** Đừng chọn buffer lớn nhất; hãy chọn **buffer đủ lớn**, được chứng minh bằng phép đo đại diện và phù hợp ngân sách tài nguyên. Với tệp lớn, một buffer cỡ vừa được tái sử dụng và lặp `read()/write()` đúng thường là điểm khởi đầu tốt hơn việc cố cấp phát vùng nhớ bằng toàn bộ file.

## Tài liệu tham khảo

- Java SE 17 — `ByteBuffer` (heap/direct, chi phí cấp phát và native I/O): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 — `FileChannel` (`read`, `write`, `force`, `map`, `transferTo`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 17 — `ReadableByteChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadableByteChannel.html
- Java SE 17 — `BufferedInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html
- Java SE 17 — `BufferedOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html
- Java SE 17 — `Files`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- OpenJDK JMH — Java Microbenchmark Harness: https://openjdk.org/projects/code-tools/jmh/
