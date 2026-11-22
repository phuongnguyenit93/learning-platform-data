# Không mặc định NIO hoặc memory mapping luôn nhanh hơn

## 1. Tư duy nền tảng: API không phải lời hứa về tốc độ

Khi làm việc với **tệp lớn** trong Java, thường nghe những nhận định như:

- “`FileChannel` thuộc NIO nên luôn nhanh hơn `FileInputStream`.”
- “`MappedByteBuffer` ánh xạ file vào bộ nhớ nên gần như không mất chi phí I/O.”
- “`transferTo()` luôn là zero-copy nên chắc chắn nhanh nhất.”
- “Direct `ByteBuffer` luôn tốt hơn heap `ByteBuffer`.”
- “File lớn thì cứ map hết file vào RAM.”

**Không nhận định nào đúng trong mọi điều kiện.** Các API Java cung cấp **cách truy cập và khả năng tối ưu hóa khác nhau**. Hiệu năng thực tế phụ thuộc workload, OS, filesystem, thiết bị, caching, kiểu đọc, kích thước khối, chi phí khởi tạo, bộ nhớ sẵn có, CPU, thiết lập JVM và cách chương trình đo.

Cần đánh giá ít nhất ba câu hỏi độc lập:

1. **Đúng chức năng không?** Copy xong dữ liệu có đầy đủ, đúng byte, không mất phần cuối, xử lý được EOF/partial read/write?
2. **Dùng tài nguyên như thế nào?** Heap, native memory, page cache, file descriptor, CPU, số syscall, GC pressure, page faults, disk I/O?
3. **Nhanh trong điều kiện nào?** File nhỏ hay lớn, đọc tuần tự hay ngẫu nhiên, đọc một lần hay lặp lại, cache nóng hay lạnh, một hay nhiều luồng, SSD hay network filesystem?

**Kết luận của bài:** chọn cách tiếp cận phù hợp dựa trên đặc tính dữ liệu và phép đo có kiểm soát. Không thay vòng lặp stream bằng NIO/mmap chỉ vì tên API nghe “hiện đại” hơn.

## 2. Phân biệt Java I/O, NIO và memory mapping

Java có nhiều API I/O tồn tại song song, không có ranh giới “cũ chậm / mới nhanh” tuyệt đối:

| Cách làm | API đại diện | Cơ chế thường dùng | Thế mạnh thường gặp |
| --- | --- | --- | --- |
| Stream tuần tự | `InputStream`, `OutputStream` | Đọc/ghi byte theo thứ tự | Đơn giản, xử lý pipeline, dễ giới hạn dữ liệu |
| Buffered stream | `BufferedInputStream`, `BufferedOutputStream` | Bộ đệm ứng dụng quanh stream | Giảm số lời gọi I/O nhỏ, xử lý tuần tự |
| Files utilities | `Files.copy`, `Files.newInputStream` | Implementation chọn cơ chế | Code ngắn, biểu đạt ý định copy rõ |
| NIO channel | `FileChannel` | Đọc/ghi với `ByteBuffer`, positional I/O | Truy cập theo offset, scattering/gathering, chuyển giữa channel |
| Channel transfer | `FileChannel.transferTo`/`transferFrom` | Cơ hội sử dụng optimized transfer | Chuyển dữ liệu giữa channel, có thể tránh copy trung gian |
| Memory-mapped file | `FileChannel.map` → `MappedByteBuffer` | Ánh xạ vùng tệp vào không gian địa chỉ | Truy cập nhiều vị trí bằng phép `get/put`, đọc ngẫu nhiên |
| Asynchronous file | `AsynchronousFileChannel` | I/O biểu diễn bằng completion/Future | Tổ chức ứng dụng bất đồng bộ |

**NIO** là tên một nhóm API (*New I/O*) chứ không phải một thuật toán nén, một kiểu bộ đệm hay bảo đảm giảm số syscall trên mọi JVM. Tương tự, “mmap” là kỹ thuật ánh xạ vào bộ nhớ ảo: **không đồng nghĩa toàn bộ file đã được tải lên RAM**.

Một chương trình dùng `FileChannel` có thể vẫn thực hiện **blocking file I/O**. `FileChannel` không phải `SelectableChannel`, không thể đăng ký `Selector` như một `SocketChannel`. Không nên nhầm NIO file channel với non-blocking socket.

## 3. Cơ chế liên quan tới hiệu năng

### 3.1. Bộ đệm ứng dụng và chi phí mỗi lời gọi

Nếu đọc từng byte bằng:

```java
int value;
while ((value = input.read()) != -1) {
    output.write(value);
}
```

thì khi stream không được buffer phù hợp, số lần gọi qua các tầng Java/OS có thể rất lớn. Một bước tối ưu thường hiệu quả hơn việc chuyển ngay sang API khác là **đọc theo khối**:

```java
byte[] buffer = new byte[64 * 1024];
int n;
while ((n = input.read(buffer)) != -1) {
    if (n == 0) {
        continue; // Cần chính sách không tiến triển tùy nguồn.
    }
    output.write(buffer, 0, n);
}
```

Hai đoạn chỉ minh họa; cần khai báo input/output, kiểm soát quyền sở hữu stream và lỗi I/O. Với `InputStream` chuẩn và độ dài > 0, `read` thông thường trả số dương hoặc `-1`; nếu một nguồn đặc biệt liên tục trả 0 thì vòng lặp trên sẽ busy-spin và cần xử lý khác.

**Đọc theo khối** thường giúp giảm overhead so với đọc từng byte, nhưng từ “thường” quan trọng: kích thước khối tối ưu vẫn phải đo và phụ thuộc API/tầng buffer bên dưới.

### 3.2. Page cache của hệ điều hành

Với file thông thường, OS thường cache dữ liệu trang tệp trong **page cache**. Do đó:

- Lần đọc đầu tiên (*cold-ish*) có thể cần đợi storage.
- Lần đọc sau (*warm*) có thể lấy phần lớn byte từ RAM của hệ thống.
- Hai chương trình dùng API khác nhau nhưng chạy liên tiếp trên cùng file có thể nhận mức cache **khác nhau**.
- File lớn hơn dung lượng cache và workload tranh chấp có thể thay đổi kết quả rất mạnh.

`Files.readAllBytes`, `FileChannel.read` và `MappedByteBuffer.get` đều có thể hưởng lợi từ page cache. Mapping **không loại bỏ** chi phí đưa trang từ storage vào cache. Nó thay cách truy cập dữ liệu, không vượt qua giới hạn vật lý của SSD/HDD/mạng.

### 3.3. System call, memory copy và page fault

Một `FileChannel.read(ByteBuffer)` có thể đi qua lời gọi hệ điều hành và sao chép byte tới buffer tương ứng. Memory mapping cho phép chương trình đọc vùng mapped bằng thao tác bộ nhớ sau khi mapping được thiết lập. Tuy nhiên, mapping có thể phát sinh **page faults**, chi phí ánh xạ và quản lý trang, TLB pressure, chi phí tạo/bỏ mapping, áp lực địa chỉ ảo và tương tác cache.

Giảm số lần copy **không có nghĩa tổng chi phí giảm** nếu chuyển khối nhỏ một lần rồi hủy mapping. Với truy cập ngẫu nhiên lặp đi lặp lại trên những trang đã có trong cache, mapping có thể thuận lợi; với một lần đọc tuần tự, buffer stream hoặc channel đôi khi dễ đạt throughput cao với ít phức tạp hơn.

### 3.4. Chi phí allocation và GC

`ByteBuffer.allocate(n)` tạo heap buffer; `ByteBuffer.allocateDirect(n)` tạo direct buffer có backing memory ngoài Java heap. Direct buffer có thể thuận lợi cho một số đường I/O native, nhưng:

- Cấp phát/thu hồi direct buffer có chi phí.
- Native memory không hiện toàn bộ ở biểu đồ heap.
- Tạo nhiều direct buffer ngắn hạn có thể gây áp lực tài nguyên.
- Một số thao tác vẫn cần copy hoặc tạo view tùy API.
- Không có hợp đồng “direct luôn nhanh hơn heap”.

**Đừng liên tục cấp phát buffer mới trong vòng copy nếu có thể tái sử dụng một buffer với vòng đời rõ ràng.**

## 4. Hiệu năng phụ thuộc workload

Một cách chọn hợp lý là mô tả workload trước:

| Workload | Ứng viên thường đáng thử | Không nên kết luận sớm |
| --- | --- | --- |
| File vài KiB, đọc một lần | `Files.readAllBytes` (nếu đã giới hạn), buffered stream | Mapping chắc chắn nhanh |
| File rất lớn, đọc tuần tự | Buffered stream, `FileChannel` + buffer, `Files.copy` | NIO chắc chắn hơn buffered stream |
| Sao chép nguyên file | `Files.copy`, `transferTo`/`transferFrom`, buffered copy | `transferTo` luôn zero-copy |
| Truy cập ngẫu nhiên nhiều offset | Positional `FileChannel.read`, memory mapping | Mmap luôn tốt hơn positional read |
| Truy cập lặp lại một vùng nhỏ | Cache ở ứng dụng, buffer reuse, mmap vùng nhỏ | Map toàn bộ file là tối ưu |
| Đọc một lần và bỏ file | Streaming buffer cố định | Luôn map rồi GC |
| Nhiều file nhỏ | Stream/`Files` đơn giản; đo overhead mở file | API tối ưu trên một file lớn vẫn tối ưu |
| Dữ liệu chưa biết kích thước | Streaming + byte limit | `readAllBytes` rồi mới kiểm tra |
| File luân phiên ghi, truncate, rotate | Channel đọc/ghi thường với state rõ | Mapping an toàn trước mọi thay đổi kích thước |

Các gợi ý trên chỉ để tạo **danh sách phương án benchmark**, không phải bảng xếp hạng tốc độ.

## 5. Buffered stream: baseline đơn giản nhưng mạnh

Một thiết kế dễ hiểu để copy file:

```java
try (InputStream input = new BufferedInputStream(
         Files.newInputStream(source), 64 * 1024);
     OutputStream output = new BufferedOutputStream(
         Files.newOutputStream(target), 64 * 1024)) {

    byte[] buffer = new byte[64 * 1024];
    int read;
    while ((read = input.read(buffer)) != -1) {
        output.write(buffer, 0, read);
    }
}
```

Đây là đoạn mã minh họa, giả định `source`/`target` là `Path` phù hợp và đã import lớp cần dùng. `close()` của buffered output sẽ flush dữ liệu còn trong buffer theo hợp đồng; lỗi trong close vẫn cần xử lý. Một số cách bố trí buffer ứng dụng có thể **thừa nhiều tầng đệm**, ví dụ có cả `BufferedInputStream` lẫn mảng đọc 64 KiB, nhưng vẫn là baseline dễ triển khai. Có thể thử `Files.newInputStream` + mảng lớn trực tiếp để xem buffered wrapper có lợi trong workload cụ thể hay không.

### Khi stream là lựa chọn tốt

- Dữ liệu xử lý **tuần tự**, không cần seek.
- Input lớn hoặc không giới hạn: muốn kiểm soát bộ nhớ bằng bộ đệm cố định.
- Dữ liệu cần xử lý qua pipeline nén, checksum, parser, encryption.
- Cần tương thích rộng, code đơn giản, dễ bảo trì.

### Khi stream chưa đủ

- Cần đọc/ghi ở offset tuyệt đối mà không đổi file position.
- Cần thao tác trên đoạn lớn hoặc nhiều vị trí của cùng file.
- Có cơ hội tối ưu chuyển byte giữa hai channel.
- Cần tính năng như `FileLock`, `force`, scattering/gathering.

Ngay cả khi nhu cầu dẫn đến NIO, vẫn phải xét **tổng chi phí** chứ không coi đó là bằng chứng tốc độ.

## 6. `FileChannel` và `ByteBuffer`: linh hoạt không đồng nghĩa miễn phí

`FileChannel` hỗ trợ các overload điển hình:

```java
int read(ByteBuffer dst) throws IOException;
int read(ByteBuffer dst, long position) throws IOException;
int write(ByteBuffer src) throws IOException;
int write(ByteBuffer src, long position) throws IOException;
long position() throws IOException;
FileChannel position(long newPosition) throws IOException;
```

Đây là chữ ký API rút gọn để minh họa, không phải class hoàn chỉnh.

`read` và `write` có thể hoàn tất **một phần** dữ liệu; không mặc định `read` lấp đầy `ByteBuffer` hoặc `write` tiêu thụ hết `remaining()` trong mọi tình huống. Với positional I/O, tham số `position` là offset **tuyệt đối trên file**; các overload có đối số offset **không sửa `channel.position()`**, nhưng vẫn thay đổi `ByteBuffer.position()` theo số byte truyền thực.

Mẫu copy theo channel:

```java
ByteBuffer buffer = ByteBuffer.allocate(64 * 1024);

while (true) {
    buffer.clear();
    int n = sourceChannel.read(buffer);
    if (n == -1) {
        break;
    }
    if (n == 0) {
        throw new IOException("Read made no progress");
    }

    buffer.flip();
    while (buffer.hasRemaining()) {
        int written = targetChannel.write(buffer);
        if (written == 0) {
            throw new IOException("Write made no progress");
        }
    }
}
```

Đây là đoạn minh họa, giả định file channels đã mở và có import. Nó xử lý **partial write**, một yếu tố quan trọng về correctness. Với file thông thường trong chế độ blocking, không tiến triển thường là tình huống bất thường; chính sách cụ thể cần tùy loại channel.

Thêm một lớp buffer không tự đảm bảo tốc độ cao: nếu bạn chọn buffer quá nhỏ, phát sinh nhiều lời gọi; nếu chọn quá lớn, tăng chi phí cấp phát và ảnh hưởng cache/memory. Kích thước `4 KiB`, `64 KiB` hay `1 MiB` đều chỉ là **candidate cho phép đo**, không phải con số phổ quát.

## 7. `FileChannel.transferTo` và `transferFrom`: có thể tối ưu, không cam kết zero-copy

`FileChannel.transferTo(long position, long count, WritableByteChannel target)` chuyển một vùng dữ liệu từ file source tới channel đích.

Ưu điểm tiềm năng: implementation có thể dùng cơ chế native để hạn chế các bước trung gian khi chuyển giữa file và socket hoặc giữa những channel được hỗ trợ. Nhưng Javadoc nói rõ số byte chuyển **có thể ít hơn `count`**, và tùy hệ thống/loại channel, implementation **có thể không chuyển được tất cả hoặc có giới hạn riêng**.

Mẫu đúng khi cần copy toàn bộ:

```java
long size = source.size();
long copied = 0;

while (copied < size) {
    long n = source.transferTo(
            copied, size - copied, destination);

    if (n <= 0) {
        throw new IOException("transferTo made no progress");
    }
    copied += n;
}
```

Đoạn này cần khai báo `source` là `FileChannel` và `destination` là `WritableByteChannel`. Khi gặp 0, **không spin vô hạn**. Tùy API và thiết bị có thể chuyển sang buffer-based fallback, chờ điều kiện thích hợp hoặc báo lỗi; ví dụ ném ngoại lệ để không che lỗi copy thiếu.

**Những điều không được suy diễn:**

- Không có bảo đảm **mọi lần transferTo đều là zero-copy**.
- “Zero-copy” không có nghĩa CPU bằng 0, I/O storage bằng 0 hoặc không có bộ nhớ kernel tham gia.
- Không có bảo đảm lần truyền `count` sẽ chuyển đủ `count`.
- Thay đổi OS, JDK, filesystem, loại đích hoặc kích thước file có thể thay đổi đường tối ưu.
- Copy từ file vào **file khác** và truyền từ file vào **socket** có đường kernel khác nhau; không gộp thành một benchmark vô danh.

Nếu hệ thống cần copy file theo `Path` mà không phải xử lý dữ liệu từng byte, **`Files.copy`** cũng là candidate quan trọng. Implementation của nó có thể chọn tối ưu riêng, nên không nên buộc mọi trường hợp đi qua mã `transferTo` tự viết.

## 8. Ví dụ Java 17 chạy được: ba cách copy, cùng dữ liệu

Ví dụ này copy một file 8 KiB bằng ba kỹ thuật:

1. Buffered stream.
2. `FileChannel` + `ByteBuffer`.
3. `FileChannel.transferTo`.

Nó **không in thời gian** vì stdout cố định ở đây dùng để kiểm tra tính đúng đắn. Một lần chạy nhỏ trên file đã cache không đủ làm benchmark.

**Tệp `CopyStrategiesDemo.java`:**

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public class CopyStrategiesDemo {
    static void bufferedCopy(Path source, Path target)
            throws IOException {
        try (InputStream input = new BufferedInputStream(
                Files.newInputStream(source));
             OutputStream output = new BufferedOutputStream(
                Files.newOutputStream(target))) {
            byte[] bytes = new byte[4096];
            int n;
            while ((n = input.read(bytes)) != -1) {
                output.write(bytes, 0, n);
            }
        }
    }

    static void channelCopy(Path source, Path target)
            throws IOException {
        try (FileChannel input = FileChannel.open(
                    source, StandardOpenOption.READ);
             FileChannel output = FileChannel.open(
                    target, StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
            ByteBuffer buffer = ByteBuffer.allocate(4096);
            while (true) {
                buffer.clear();
                int n = input.read(buffer);
                if (n == -1) {
                    break;
                }
                if (n == 0) {
                    throw new IOException("No read progress");
                }
                buffer.flip();
                while (buffer.hasRemaining()) {
                    if (output.write(buffer) == 0) {
                        throw new IOException("No write progress");
                    }
                }
            }
        }
    }

    static void transferCopy(Path source, Path target)
            throws IOException {
        try (FileChannel input = FileChannel.open(
                    source, StandardOpenOption.READ);
             FileChannel output = FileChannel.open(
                    target, StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
            long size = input.size();
            long copied = 0;
            while (copied < size) {
                long n = input.transferTo(
                        copied, size - copied, output);
                if (n <= 0) {
                    throw new IOException("No transfer progress");
                }
                copied += n;
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("copy-demo-");
        Path source = directory.resolve("source.bin");
        Path a = directory.resolve("buffered.bin");
        Path b = directory.resolve("channel.bin");
        Path c = directory.resolve("transfer.bin");

        try {
            byte[] data = new byte[8192];
            for (int i = 0; i < data.length; i++) {
                data[i] = (byte) (i % 251);
            }
            Files.write(source, data);

            bufferedCopy(source, a);
            channelCopy(source, b);
            transferCopy(source, c);

            System.out.println("Buffered correct: "
                    + (Files.mismatch(source, a) == -1));
            System.out.println("Channel correct: "
                    + (Files.mismatch(source, b) == -1));
            System.out.println("Transfer correct: "
                    + (Files.mismatch(source, c) == -1));
            System.out.println("Original size: " + Files.size(source));
        } finally {
            Files.deleteIfExists(c);
            Files.deleteIfExists(b);
            Files.deleteIfExists(a);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac CopyStrategiesDemo.java
java CopyStrategiesDemo
```

**Stdout trong điều kiện I/O thành công:**

```text
Buffered correct: true
Channel correct: true
Transfer correct: true
Original size: 8192
```

`Files.mismatch` (có từ Java 12) trả `-1` nếu hai file giống nhau về byte. Phép kiểm tra này xác minh **đầu ra**, không chứng minh phương thức nào nhanh hơn.

### Phân tích ví dụ

- Tệp nguồn được tạo với 8.192 byte có quy luật, không phụ thuộc dữ liệu mạng.
- Buffered copy đọc/ghi theo khối 4.096 byte.
- Channel copy dùng đúng chu kỳ `clear → read → flip → write hết remaining`.
- Transfer copy dùng vòng lặp với `copied` để không bỏ phần nếu `transferTo` trả số nhỏ hơn `count`.
- Các file đích có tên khác nhau; code không ghi đè nguồn.
- `try-with-resources` đóng tất cả handle trước khi xóa file tạm.

**Nếu thay thành file rất lớn:** bản mẫu `Files.mismatch` sẽ đọc tệp để đối chiếu, làm thay đổi tình trạng cache. Khi đo throughput, phải tách **thời gian copy** khỏi **thời gian verify** (hoặc báo rõ cả hai), và bảo đảm các phương án được so trên **cùng điều kiện đầu vào**. Mỗi lượt chạy có thể cần reset file đích, cache policy và chế độ lưu trữ.

## 9. Memory mapping là gì — và không phải gì?

`FileChannel.map` ánh xạ một vùng tệp vào bộ nhớ ảo của tiến trình, trả về `MappedByteBuffer` (API thông dụng trên Java 17):

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY,
        offset,
        length);
```

Đây là đoạn minh họa; `channel` phải mở đúng mode, `offset`/`length` hợp lệ. Sau khi map, `get(index)`/`getInt(index)` có thể truy cập vị trí trong vùng mapped mà không cần gọi `channel.read` cho mỗi phần tử.

**Nhưng mapping không có nghĩa:**

- File đã được tải toàn bộ vào RAM ngay lúc `map()` trả về.
- Truy cập byte đầu tiên không thể xảy ra page fault.
- Dữ liệu luôn nằm trong CPU cache.
- Không còn kernel, OS hoặc filesystem tham gia.
- Không bao giờ gây lỗi nếu file bị truncate từ tiến trình khác.
- Đã có API unmap đồng bộ tường minh trên `MappedByteBuffer` Java 17.
- Luôn nhanh hơn `FileChannel.read`, kể cả file nhỏ, mở/đọc một lần rồi đóng.

### Khi nào mapping đáng xem xét?

- Truy cập **nhiều lần** các vùng tệp khác nhau bằng offset.
- Bảng tra cứu hoặc cấu trúc dữ liệu nhị phân có địa chỉ bản ghi dễ tính.
- Nhiều lần random read trên vùng mapping có vòng đời đủ dài.
- Dữ liệu phù hợp để xem như một **vùng byte trong bộ nhớ** với index và format rõ ràng.

### Khi nào nên cân nhắc tránh?

- Tệp rất nhỏ, mở/đọc một lần.
- File cần thay thế/truncate/xóa ngay và quan tâm tính portable giữa OS.
- Pipeline tuần tự vốn đã đạt throughput phù hợp.
- Ứng dụng tạo/hủy hàng nghìn mapping ngắn hạn.
- Dữ liệu đầu vào có thể bị tiến trình khác thay đổi kích thước bất ngờ.
- Môi trường có giới hạn address space, native memory hoặc mapping count chặt.

**Map phù hợp workload, không phải “chế độ turbo” cho mọi I/O.**

## 10. Không gian địa chỉ ảo, RAM và page faults là ba thứ khác nhau

Khi mmap một tệp, tiến trình có **vùng ánh xạ địa chỉ ảo** để truy cập trang tệp. Việc một vùng rộng được ánh xạ không đồng nghĩa bằng ấy byte đã được copy vào Java heap hoặc đều resident trong RAM.

Phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Java heap | Nơi chứa object, array, một phần metadata do GC quản lý |
| Virtual address space | Không gian địa chỉ process, nơi mapping đặt vùng truy cập |
| Resident memory | Trang bộ nhớ vật lý hiện đang resident, phụ thuộc OS |
| Page cache | Bộ nhớ đệm của OS cho trang tệp |
| Page fault | Truy cập trang chưa sẵn sàng trong mapping hoặc cần thiết lập mapping/đọc từ storage |
| MappedByteBuffer | Java view tới vùng file mapped, có giới hạn `int` index |
| File descriptor/channel | Tài nguyên I/O để mở file; đóng channel không nhất thiết unmap vùng đã tạo |

Tốc độ có thể khác nhau tùy dữ liệu đã nằm trong page cache hay chưa. Đọc ngẫu nhiên qua mapping có thể phát sinh nhiều page faults không đều; đọc tuần tự qua buffered stream cho phép OS nhận diện pattern tốt và dùng prefetch/read-ahead. Với một workload khác, mapping có thể giảm overhead của nhiều thao tác positional read nhỏ.

**Đo cả CPU, page faults và I/O latency**, không chỉ tổng số byte đọc trên lý thuyết.

## 11. Ví dụ Java 17: random access bằng FileChannel và mmap đều đúng

Ví dụ sau tạo file nhị phân gồm bốn số nguyên big-endian và đọc số thứ ba (index 2) bằng:

1. `FileChannel.read(dst, offset)` từ vị trí tuyệt đối.
2. `MappedByteBuffer.getInt(index)` từ mapping read-only.

Mục tiêu: chứng minh **tính tương đương kết quả** trên dữ liệu này và phân biệt mô hình state. Không có khẳng định cách nào nhanh hơn từ vài byte.

**Tệp `RandomAccessStrategiesDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class RandomAccessStrategiesDemo {
    static int readIntAt(FileChannel channel, long offset)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(Integer.BYTES);
        buffer.order(ByteOrder.BIG_ENDIAN);

        int received = 0;
        while (buffer.hasRemaining()) {
            int n = channel.read(buffer, offset + received);
            if (n == -1) {
                throw new IOException("Unexpected EOF");
            }
            if (n == 0) {
                throw new IOException("No progress");
            }
            received += n;
        }

        buffer.flip();
        return buffer.getInt();
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("random-access-", ".bin");
        file.toFile().deleteOnExit();

        ByteBuffer source = ByteBuffer.allocate(4 * Integer.BYTES);
        source.order(ByteOrder.BIG_ENDIAN);
        source.putInt(10).putInt(20).putInt(30).putInt(40);
        Files.write(file, source.array());

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ)) {

            channel.position(1);
            int positional = readIntAt(channel, 2L * Integer.BYTES);

            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_ONLY, 0, channel.size());
            mapped.order(ByteOrder.BIG_ENDIAN);
            int viaMap = mapped.getInt(2 * Integer.BYTES);

            System.out.println("FileChannel: " + positional);
            System.out.println("MappedByteBuffer: " + viaMap);
            System.out.println("Same value: "
                    + (positional == viaMap));
            System.out.println("Channel position: "
                    + channel.position());
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac RandomAccessStrategiesDemo.java
java RandomAccessStrategiesDemo
```

**Stdout khi I/O thành công:**

```text
FileChannel: 30
MappedByteBuffer: 30
Same value: true
Channel position: 1
```

**Giải thích:**

- Số thứ ba nằm từ offset 8 đến offset 11 (mỗi `int` dài 4 byte).
- `readIntAt` lặp đến khi lấy đủ 4 byte và dùng `offset + received`; overload positional read không thay đổi `channel.position()`.
- `mapped.getInt(8)` là truy cập tuyệt đối trong buffer mapped; không cần gọi `channel.read` cho lần `getInt`.
- Trước thao tác, channel được đặt `position(1)`, và hai cách đọc không làm thay đổi giá trị này.
- Cả hai trả 30 nhưng **không suy ra hiệu năng tương đương hay ưu việt** chỉ từ correctness.

**Lưu ý vòng đời:** ví dụ dùng `deleteOnExit()` thay vì yêu cầu xóa file tạm ngay sau khi tạo mapped buffer, vì trên một số nền tảng mapping còn sống có thể ảnh hưởng thao tác xóa/rename. `deleteOnExit` cũng chỉ là nỗ lực dọn dẹp khi JVM thoát, không bảo đảm file sẽ được xóa trong mọi tình huống; ứng dụng chạy lâu cần chính sách quản lý lifecycle phù hợp.

### Vấn đề byte order

`MappedByteBuffer` và `ByteBuffer` có `ByteOrder`. Với dữ liệu định dạng big-endian, phải thiết lập/diễn giải nhất quán. Nếu sai endianness, hai cách đọc có thể trả giá trị khác nhau dù cả hai hoàn toàn đúng về byte. Đừng dùng kết quả parser sai để kết luận về API nhanh/chậm.

## 12. Giới hạn riêng của `MappedByteBuffer` trên Java 17

`MappedByteBuffer` kế thừa `ByteBuffer`, mà `capacity`, `position` và `limit` được biểu diễn bằng `int`. Vì vậy **một mapping đơn theo API trả MappedByteBuffer không thể chứa tùy ý cả file nhiều terabyte**. Java SE 17 `FileChannel.map` ràng buộc `size` theo giới hạn kiểu buffer; thực tế thường giới hạn mỗi vùng mapping ở cỡ tối đa `Integer.MAX_VALUE` byte.

**Muốn xử lý file lớn hơn giới hạn một buffer**, chia thành các cửa sổ (*windows*):

```text
File 10 GiB
   |
   +-- map window #1 (ví dụ 256 MiB)
   +-- map window #2 (256 MiB)
   +-- ...
   +-- map window N (phần cuối)
```

Nhưng mapping nhiều cửa sổ có chi phí tạo/quản lý; không nên mặc định **càng nhiều mapping càng nhanh**. Hệ thống có thể giới hạn số mapping, file descriptors hoặc address space, đặc biệt trên môi trường 32-bit hoặc container bị hạn chế.

### Cleanup/unmap không do `FileChannel.close()` quyết định

Với API `FileChannel.map(MapMode, long, long)` truyền thống trên Java 17:

- Mapping có thể tiếp tục hợp lệ **sau khi FileChannel đóng**.
- `MappedByteBuffer` không cung cấp `close()`/`unmap()` chuẩn công khai.
- Thời gian unmap phụ thuộc lifecycle bộ nhớ/GC, không phải thao tác `clear()` hoặc `force()`.
- Đổi tên/xóa/truncate file đang được map có thể gặp hành vi khác nhau giữa hệ điều hành và file system.

Điều này ảnh hưởng trực tiếp tới benchmark và hệ thống sản xuất: nếu mỗi lượt benchmark map một vùng mới nhưng không kiểm soát được vòng đời các mapping cũ, phép đo có thể tích lũy tài nguyên và trở nên không công bằng.

**Ghi chú theo phiên bản:** Từ Java 22, API chuẩn có overload `FileChannel.map(..., Arena)` trả `MemorySegment`, cho phép quản lý vòng đời qua arena có thể đóng. Đó là **API khác**, không khiến `MappedByteBuffer` Java 17 tự có `close()`. Khi cần tương thích Java 17, không dùng overload chỉ có ở Java 22.

## 13. Memory mapping có thể làm công việc chậm hơn ra sao?

Một số tình huống phản trực giác:

### 13.1. Một file nhỏ được đọc một lần

Chi phí thiết lập mapping, page faults và cleanup có thể lớn hơn lợi ích giảm số lời gọi `read`. Một lệnh `Files.readAllBytes` hoặc buffered stream có thể đơn giản và nhanh hơn trong bài đo cụ thể.

### 13.2. Đọc tuần tự lượng rất lớn

OS có thể thực hiện read-ahead hiệu quả với các lệnh đọc tuần tự. Memory mapping cũng có thể được tối ưu theo pattern, nhưng nó phát sinh page faults và chịu cách CPU/OS xử lý truy cập. Không có kết quả cố định về bên thắng.

### 13.3. Nhiều mapping ngắn hạn

Thay vì tái sử dụng một mapping lâu dài, chương trình map/unmap liên tục có thể chịu overhead metadata và native memory. Với API legacy, khi nào unmap còn phụ thuộc GC. Do đó pattern “mở → map → đọc 1 byte → bỏ mapping” thường không phải cách dùng tối ưu.

### 13.4. File thường xuyên bị truncate hoặc rotate

Mapping sống trong lúc file bị thay đổi kích thước có thể làm một phần vùng không truy cập được; hành vi lỗi có thể phụ thuộc OS. Nếu hệ thống là log rotate, temp file hoặc spool thường xuyên xóa, buffered FileChannel/read có thể dễ quản lý vòng đời hơn.

### 13.5. Áp lực bộ nhớ và cạnh tranh tài nguyên

Mapping không tự copy toàn bộ file lên heap nhưng có thể làm tăng pressure lên address space, page tables và cache. Trên máy nhiều service, một workload mmap có thể làm cache của workload khác bị đẩy ra, hoặc chính nó bị page faults nhiều hơn dự kiến.

**Đánh giá hiệu năng không chỉ nhìn time của một tác vụ mà còn nhìn ảnh hưởng tới toàn hệ thống.**

## 14. `Files.copy`: đừng bỏ qua API mức cao

Nếu mục tiêu chỉ là copy tệp:

```java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

`Files.copy` thường đơn giản hơn code tự viết nhiều vòng `read`/`write`, với ý định rõ và hỗ trợ các option phù hợp. Implementation có thể tận dụng các tối ưu dựa trên filesystem/provider.

**Nhưng**:

- Đừng mặc định mọi provider xử lý copy giống nhau.
- `COPY_ATTRIBUTES` và `REPLACE_EXISTING` liên quan hành vi metadata/xung đột tên, không phải bảo đảm tốc độ.
- Đừng tính kết quả benchmark nếu không kiểm tra file đích đã hợp lệ.
- Copy metadata, permission và symlink có khác biệt theo API/option và filesystem.
- Một số thao tác copy có thể thất bại giữa chừng; code nghiệp vụ cần quyết định cleanup/rollback.

Với dữ liệu cần kiểm tra/checksum hoặc biến đổi, tự stream theo chunk có thể là lựa chọn rõ hơn. Với thao tác copy nguyên file bình thường, nên **đưa Files.copy vào danh sách phương án đo**.

## 15. Cách thiết kế một benchmark công bằng

### 15.1. Xác định câu hỏi trước khi đo

Ví dụ câu hỏi có ý nghĩa:

> “Trên SSD này, với file 4 GiB và đọc tuần tự vào một checksum, throughput của buffered stream 64 KiB, FileChannel 64 KiB và mapping cửa sổ 256 MiB như thế nào khi cache nóng và cache lạnh?”

Một câu hỏi không rõ:

> “NIO có nhanh hơn IO không?”

Câu thứ hai thiếu workload, thiết bị, kích thước, tình trạng cache, điều kiện đo và tiêu chí thành công.

### 15.2. Kiểm soát các biến ảnh hưởng

| Biến | Tại sao cần kiểm soát |
| --- | --- |
| JVM/JDK và flags | JIT, GC, runtime implementation có thể khác |
| OS, filesystem, storage | Ảnh hưởng native I/O path, page cache, throughput |
| File size và phân bố dữ liệu | File nhỏ/ lớn và mức nén/file sparsity khác nhau |
| Kiểu truy cập | Sequential vs random, tỷ lệ read/write |
| Warm/cold cache | OS page cache có thể chi phối kết quả |
| Số lần lặp và warmup | JIT/GC/OS scheduler tạo nhiễu |
| Concurrency | I/O queue depth, contention và memory pressure |
| Buffer size và allocation | Có thể biến kết quả từ lợi ích API thành khác biệt kích thước khối |
| Đích copy | SSD cùng volume, volume khác, socket, network mount |
| Độ bền ghi | `force/fsync` thay đổi rất mạnh latency |
| Verification và setup | Tốn CPU/I/O, nên tách khỏi thời gian thao tác chính |
| Error/partial I/O handling | Code sai nhưng nhanh không phải chiến thắng |

Khi đo, chỉ nên thay **một chiều thiết kế** trong một nhóm so sánh (ví dụ thay cơ chế I/O, giữ kích thước block và input tương đương), rồi thử nghiệm thêm các chiều khác. So sánh một stream đọc từng byte với FileChannel buffer 1 MiB rồi kết luận “NIO nhanh hơn” là so sánh **hai thuật toán có số lần thao tác khác nhau**, không cô lập hiệu ứng của API.

### 15.3. Warmup và thứ tự chạy

Một vài lần benchmark đầu có thể gồm:
- Tải class và khởi tạo JVM/JIT.
- Cấp phát buffer, mở file và tạo metadata.
- Trang file chưa nằm trong cache.
- Các background processes và GC.

Nếu luôn chạy Stream trước rồi Mmap sau, Mmap có thể hưởng cache đã được Stream làm nóng. Nếu luôn đảo lại, người chạy trước chịu bất lợi. Nên **thay đổi/đảo thứ tự chạy, lặp nhiều lượt và báo phân bố kết quả**. Khi benchmark cold cache, chỉ dùng phương pháp thực sự kiểm soát được trạng thái cache và báo rõ cách thực hiện; đọc file với một tên mới không chắc làm dữ liệu lạnh về mặt OS.

**Không xóa cache toàn hệ thống trên môi trường đang chạy dịch vụ** chỉ để lấy một con số đo đẹp: tác động tới tác vụ khác và không phản ánh workload thực.

### 15.4. Tách throughput và latency

Một phương pháp có thể đạt **throughput MB/s** cao khi copy file lớn nhưng có **latency per lookup** không tốt nếu mỗi lần lại map/unmap. Một phương pháp khác có thể tối ưu truy cập random khi mapping đã tồn tại nhưng không phù hợp startup lạnh.

Các metric hữu ích:

- Tổng thời gian copy hoặc scan, đơn vị ms/s.
- Throughput theo MiB/s: `bytes / elapsedSeconds / 2^20`.
- Latency theo từng thao tác, median, p95, p99 khi phù hợp.
- CPU user/system, page faults, số syscall, context switches.
- GC pause/allocation rate, direct/native memory, resident memory.
- Disk reads/writes thực tế, IOPS, filesystem cache hit/miss nếu đo được.
- Tỷ lệ lỗi, số lần partial transfer, thời gian setup/cleanup.

Đừng công bố “nhanh gấp 3” nếu không có số liệu lặp, điều kiện đo và correctness check.

## 16. Một ví dụ đo thời gian đơn giản — chỉ để khám phá, không phải kết luận

`System.nanoTime()` thích hợp để đo khoảng thời gian đã trôi qua trong JVM, không phải đồng hồ ngày giờ. Một hàm đo rất đơn giản:

```java
long start = System.nanoTime();
copyOperation.run();
long elapsedNanos = System.nanoTime() - start;

double millis = elapsedNanos / 1_000_000.0;
System.out.printf("Elapsed: %.3f ms%n", millis);
```

Đây là đoạn **minh họa không độc lập**, giả định `copyOperation` là tác vụ đã khai báo. Con số `Elapsed` **không cố định** và tuyệt đối không được xem là kết quả hứa trước.

Nếu tự viết benchmark đơn giản:

1. Tạo sẵn input ở ngoài vùng đo.
2. Giữ mỗi phương án làm **cùng công việc**.
3. Đưa setup/cấp phát/open/close vào hay ra vùng đo **theo mục tiêu đo**; nếu hai phương án được so end-to-end trong production, nên tính cả overhead của chúng.
4. Tránh in log trong vùng đo.
5. Sau mỗi lượt, verify dữ liệu (có thể ở ngoài vùng đo).
6. Chạy nhiều vòng, xen kẽ thứ tự và thống kê median/dispersion.
7. Theo dõi cache/GC/paging để giải thích outlier.
8. Chỉ kết luận cho cấu hình đo, tránh tổng quát hóa.

JMH (Java Microbenchmark Harness) rất hữu ích cho mã thuần CPU/JIT; nhưng với file I/O, dùng JMH cũng **không tự kiểm soát OS page cache, thiết bị, filesystem và cạnh tranh tài nguyên**. Cần thiết kế benchmark I/O ở cấp hệ thống, có thể kết hợp công cụ profiling như JFR, `jcmd` và counters của OS.

## 17. Một cách thử nghiệm có ích hơn câu “NIO nhanh hơn”

Đặt ra ma trận đo, thay vì chỉ chọn 2 API:

| Workload | Cỡ dữ liệu | Kiểu | Candidates |
| --- | --- | --- | --- |
| Rất nhỏ | 1–16 KiB | Copy nguyên file | `Files.copy`, buffered stream, channel |
| Trung bình | 1–32 MiB | Copy tuần tự | buffered stream, channel, transferTo |
| Lớn | 1–8 GiB | Copy tuần tự | buffer/transferTo/Files.copy |
| Lookup ngẫu nhiên | 1 GiB | 8-byte records | positional FileChannel, mmap windows |
| Truy cập lặp lại | 256 MiB | Hot random reads | channel với cache tự quản, mmap |
| Nhiều file nhỏ | 10.000 file | Open+read+close | Files/stream, channel |
| Đọc dữ liệu có transform | Tùy ý | Hash/parse | streaming buffer, channel với buffer |

**Cần thử warm và cold-ish riêng**, và với file lớn phải có chiến lược không làm benchmark tự biến thành phép đo bộ nhớ cache (ví dụ dữ liệu quá nhỏ so với RAM có thể tạo kết quả “disk throughput” giả).

Mỗi workload cần thước đo riêng: số file/s với nhiều file nhỏ, MiB/s với copy tuần tự, p95 latency với random lookup, memory/time-to-cleanup với mapping ngắn hạn.

## 18. Những yếu tố có thể làm benchmark sai lệch

### 18.1. Chạy nhanh hơn vì không đọc đủ byte

Một đoạn `FileChannel.read(buffer)` có thể trả ít hơn `remaining()`. Nếu code không loop và chỉ xử lý số byte đầu, nó sẽ nhanh hơn đơn giản vì **bỏ sót dữ liệu**. Tương tự, `transferTo` có thể chuyển một phần; code không loop có thể trả về nhanh trước khi file đích đủ.

Luôn verify byte count và checksum/`Files.mismatch` sau khi chạy.

### 18.2. Thay đổi tốc độ bằng cách vô tình thay kích thước buffer

`BufferedInputStream` với mặc định buffer, `FileChannel` với 1 MiB direct buffer và mmap toàn file có chi phí rất khác. Muốn quy phần lợi ích cho API, phải kiểm soát hoặc ít nhất báo rõ buffer sizes và allocation reuse.

### 18.3. Trộn hot và cold cache

Một phương án chạy sau hưởng lợi từ phương án chạy trước. Không dùng một lần chạy duy nhất để đại diện cho cả hệ thống.

### 18.4. Đưa setup ra ngoài một cách thiên vị

Nếu mapping được tạo trước vùng đo, còn stream phải mở file trong vùng đo, bài đo có thể thiên vị mmap. Nhưng nếu ứng dụng thực reuse mapping trong nhiều giờ, **bài đo steady-state không tính startup** lại có lý do chính đáng. Vấn đề không phải đúng/sai tuyệt đối, mà là **định nghĩa rõ câu hỏi** và đo cả startup/end-to-end nếu cần.

### 18.5. Đếm `write()` là durability

Khi `write` trả về, dữ liệu thường đi vào cache hoặc hàng đợi của OS, không nhất thiết đã xuống thiết bị lưu trữ bền vững. `FileChannel.force(...)` hoặc `MappedByteBuffer.force()` có thể cần thiết tùy yêu cầu durability.

Nếu phương án A gọi `force` còn B không gọi, không thể kết luận B “nhanh hơn” cho cùng mức bảo đảm dữ liệu. Phải so theo cùng mức durability và error policy.

### 18.6. Bộ nhớ native không hiện đủ trong heap metric

Mmap và direct buffers có thể tiêu thụ native memory/virtual address, hoặc tăng page cache pressure, không hiện trực tiếp trong `Runtime.totalMemory()-freeMemory()`. Theo dõi RSS/process memory, Native Memory Tracking khi phù hợp, OS mapping statistics, page faults.

### 18.7. File bị nén, sparse hoặc copy-on-write

Một số filesystem có nén, sparse file hoặc *reflink/copy-on-write*. Lệnh copy có thể nhanh vì filesystem tối ưu metadata/copy semantics thay vì truyền toàn bộ byte qua storage. Điều này có giá trị trong workload thực, nhưng phải báo rõ bởi nó không chứng minh Java API đó luôn nhanh trên mọi filesystem.

## 19. Vấn đề correctness riêng của mapping

### 19.1. Khi file bị truncate trong lúc mapped buffer còn sống

Nếu file bị thay đổi kích thước hoặc truncate trong lúc chương trình đang truy cập mapping, một phần vùng mapped có thể trở nên không hợp lệ. Hành vi truy cập khi ấy có yếu tố phụ thuộc OS. Không mặc định `mapped.get(index)` luôn cho byte hợp lệ chỉ vì `index < mapped.capacity()`.

Khi file có writer khác, cần cơ chế phối hợp, snapshot hoặc chính sách versioning/locking thích hợp; mapping không tự khóa nội dung file.

### 19.2. `force()` không phải `unmap()`

`MappedByteBuffer.force()` yêu cầu đẩy thay đổi mapping (trong điều kiện phù hợp) theo hợp đồng, không giải phóng mapping. `clear()` chỉ đặt lại `position`/`limit` của buffer. `FileChannel.close()` đóng channel, không đảm bảo mapping legacy đã được tháo.

Sự nhầm lẫn về vòng đời có thể gây vấn đề xóa file trên một số OS, làm leak tài nguyên địa chỉ ảo trong chương trình chạy dài và khiến benchmark ngắn hạn không đại diện cho production.

### 19.3. Mapping không cho atomic update tùy ý

Ghi một cấu trúc nhiều field qua mapped buffer không tự tạo giao dịch nguyên tử. Reader ở tiến trình khác có thể thấy trạng thái cập nhật dở nếu không có protocol phối hợp. Với file dữ liệu nhạy cảm hoặc đòi consistency, cần cơ chế lock, versioning, checksum, journal hoặc transactional storage phù hợp.

Không nên chọn mmap chỉ để “ghi nhanh hơn” rồi bỏ qua tính nhất quán.

## 20. Chọn buffer size theo phép đo và giới hạn bộ nhớ

Mỗi buffer tác động tới:

- **Overhead mỗi lần read/write**: buffer nhỏ có thể gây nhiều lần gọi.
- **Heap/native allocation**: buffer lớn chiếm tài nguyên nhiều hơn.
- **CPU cache locality**: pattern có thể ảnh hưởng cache.
- **Concurrency**: nếu mỗi kết nối/tác vụ giữ buffer riêng, buffer size nhân lên theo lượng đồng thời.
- **Latency**: buffer quá lớn có thể tăng độ trễ xử lý một số pipeline.
- **I/O scheduler/readahead**: OS và thiết bị có hành vi khác nhau.

Ví dụ ngân sách đơn giản: nếu 200 tác vụ mỗi tác vụ giữ một buffer 1 MiB thì chỉ riêng buffer đã khoảng **200 MiB**. Nếu là hai buffer mỗi tác vụ, khoảng 400 MiB, chưa tính parser và object khác. `ByteBuffer.allocateDirect` không biến tài nguyên thành miễn phí chỉ vì nó ngoài heap.

**Kỹ thuật nên cân nhắc:** pool buffer có giới hạn, reuse buffer, bounded concurrency, admission control, chunked streaming; kết hợp đo GC/native memory.

## 21. Giới hạn đầu vào và khả năng chống resource exhaustion

Hiệu năng tốt không chỉ là copy nhanh trong điều kiện bình thường. Đầu vào lớn hoặc không tin cậy còn cần:

1. **Byte limit** trước và trong lúc đọc — không chỉ tin metadata.
2. **Timeout/deadline** để tránh luồng vô hạn hoặc client gửi rất chậm.
3. **Dung lượng file tạm và disk quota** nếu copy/giải nén ra đĩa.
4. **Giới hạn concurrency và hàng đợi** để không tạo hàng nghìn buffer lớn.
5. **Cơ chế rollback** khi copy chưa hoàn tất.
6. **Kiểm tra integrity và publish** sau khi dữ liệu đầy đủ.
7. **Giới hạn giải nén sau compression** nếu nguồn là ZIP/GZIP.

`Files.readAllBytes` thuận tiện nhưng cấp bộ nhớ tỷ lệ với kích thước file; không dùng trên đầu vào không có hạn mức rồi mới kiểm tra. Với memory mapping, không được xem file mmap là “không dùng RAM”: nó vẫn tham gia page cache, RSS, address-space management và page faults.

Đôi khi phương án có benchmark trung bình chậm hơn chút nhưng **ổn định, dễ cleanup, memory bounded** lại phù hợp production hơn phương án đạt peak throughput cao nhưng có rủi ro tăng tài nguyên không kiểm soát.

## 22. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “NIO luôn nhanh hơn IO.” | API không quyết định mọi chi phí | Benchmark theo workload |
| “mmap là đọc từ RAM, không dùng disk.” | Page fault có thể phải tải dữ liệu từ storage | Xem page cache, warm/cold |
| “transferTo luôn zero-copy.” | Implementation/path/target có thể khác | Đo theo OS/channel, xử lý partial |
| “Một lần transferTo copy đủ count.” | Có thể chuyển ít hơn yêu cầu | Vòng lặp cộng dồn bytes |
| “Một lần FileChannel.write gửi hết buffer.” | Partial write có thể xảy ra | Loop theo `hasRemaining()` |
| “Đổi heap ByteBuffer sang direct luôn nhanh.” | Allocation/native memory có chi phí | Đo, reuse, kiểm soát memory |
| “Mmap cho file nhỏ sẽ nhanh hơn.” | Setup/map/page fault có thể chiếm ưu thế | Thử buffered/Files baseline |
| “Map toàn bộ file nhiều terabyte bằng một buffer Java 17.” | `ByteBuffer` index `int` | Chia window hoặc API khác |
| “Đóng channel là unmap.” | Mapping legacy còn vòng đời riêng | Quản lý mapping lifecycle |
| “`mapped.force()` giải phóng mapping.” | Force là persistence, không phải release | Phân biệt flush/unmap |
| “Đo file thứ hai nhanh hơn chứng minh API tốt.” | File thứ hai có thể cache nóng | Xen kẽ, kiểm soát cache |
| “Đo 1 lần và in 1 số milliseconds là kết luận.” | Nhiễu JIT/GC/OS | Warmup, nhiều lần, thống kê |
| “Không cần verify khi benchmark.” | Code thiếu dữ liệu có vẻ nhanh | So byte count/hash/mismatch |
| “Chỉ xem Java heap là đủ.” | Native mapping/buffers dùng tài nguyên khác | Theo dõi RSS/page faults/native |
| “Benchmark không tính cleanup nhưng production có.” | Đang đo workload khác | Báo cả steady-state và end-to-end |
| “Write xong là chắc chắn durable.” | Cache/flush semantics khác nhau | So cùng mức force/durability |
| “Cứ map file đang bị ghi/truncate liên tục.” | Rủi ro invalid mapping/OS khác nhau | Phối hợp writer, snapshot hoặc I/O thường |
| “Buffer 1 MiB tốt cho mọi workload.” | Overhead/memory/concurrency khác nhau | Sweep kích thước buffer |

## 23. Bài tập thực hành

### Bài 1: một lần copy file 4 KiB

Bạn đang copy một file 4 KiB, kết quả phải được ghi đúng byte. Có nên mở `MappedByteBuffer` mặc định?

**Gợi ý:** bắt đầu với `Files.copy` hoặc buffered stream và đo nếu có nhu cầu tối ưu rõ ràng. Với file nhỏ, overhead thiết lập mapping có thể đáng kể so với lượng dữ liệu cần chuyển. Không khẳng định mmap luôn chậm; chỉ không mặc định chọn nó.

### Bài 2: kiểm tra đầu ra `transferTo`

Một lệnh `source.transferTo(0, 10_000, target)` trả về `4096`. File target đã có đủ 10.000 byte chưa?

**Chưa.** Chỉ có 4.096 byte được báo chuyển trong lần gọi ấy. Phải tiếp tục ở offset 4.096 và còn 5.904 byte, kiểm tra progress/lỗi và verify đích.

### Bài 3: cache làm sai kết luận

Bạn chạy buffered stream trước, lần sau chạy mapping và thấy mapping nhanh hơn nhiều. Có thể kết luận mapping tốt hơn không?

**Không.** Có thể file đã được stream đầu tiên làm nóng trong OS page cache, hoặc JIT/CPU/storage có trạng thái khác. Lặp, đảo thứ tự, kiểm soát cache và báo điều kiện.

### Bài 4: random lookup trên file đã mapped

Một ứng dụng đọc một record 8 byte ở 100.000 offset ngẫu nhiên của file dữ liệu lớn, lặp lại nhiều lần. Candidate nào đáng benchmark?

**Positional FileChannel.read và memory mapping** đều đáng thử, có thể thêm application-level caching. Mapping có thể giảm overhead gọi `read` lặp lại nhưng có thể tăng page faults/cache pressure. Quyết định bằng kết quả đo trên workload thật.

### Bài 5: đóng channel sau map

`FileChannel.close()` đã gọi sau khi map read-only trên Java 17. Bạn có thể bảo đảm file có thể xóa ngay lập tức trên mọi OS không?

**Không.** Legacy `MappedByteBuffer` có vòng đời mapping riêng, và Windows cùng một số môi trường có thể hạn chế xóa/rename file đang mapped. Thiết kế cleanup không được phụ thuộc giả định portable sai.

### Bài 6: “chạy nhanh hơn” vì không fsync

Hai phương án ghi file: A gọi `force(true)` sau ghi, B không gọi. B có thời gian ngắn hơn. Kết luận B tối ưu cho cùng yêu cầu durability được không?

**Không.** Hai phương án thực hiện **khác mức bảo đảm đồng bộ dữ liệu**. Cần so cùng hợp đồng durability.

### Bài 7: FileChannel có phải non-blocking giống SocketChannel?

**Không.** `FileChannel` là channel tệp có các thao tác `read/write` bình thường và không có `configureBlocking(false)`/`Selector` như `SelectableChannel` mạng. NIO không đồng nghĩa non-blocking với mọi channel.

### Bài 8: Cùng throughput, RAM khác nhau

Stream-copy 64 KiB buffer và `Files.readAllBytes` trên file 3 GiB có throughput gần tương đương trên máy thử nghiệm. Phương án nào thường dễ kiểm soát bộ nhớ hơn?

**Streaming với buffer giới hạn**, vì `readAllBytes` cố tạo mảng chứa toàn bộ tệp, có thể không cấp phát được và chiếm heap lớn; còn stream-copy không phải giữ mọi byte đầu vào trong một mảng. Vẫn cần kiểm soát output và dữ liệu trung gian.

## 24. Checklist quyết định trong dự án thật

**Trước khi tối ưu:**

- Mô tả workload: file size, số file, sequential/random, read/write, một lần hay lặp, concurrency.
- Xác định correctness: byte count, integrity, EOF, partial reads, cleanup và data durability.
- Xác định ràng buộc: RAM, address space, file descriptors, latency SLO, platform/JDK.
- Chọn baseline đơn giản: `Files.copy`, buffered stream hoặc `Files.newInputStream`.

**Khi thử NIO và mmap:**

- Với channel: dùng buffer hợp lý, xử lý partial I/O, tránh cấp phát lại mỗi lần.
- Với transfer: kiểm tra số byte thực chuyển, có fallback/error khi không tiến triển.
- Với mmap: xem cả phí setup, page faults, unmap lifecycle, truncate/rename, window size.
- So sánh theo cùng input và durability policy.
- Đo cả total time, throughput, latency, CPU, heap/native memory, page cache/paging.

**Khi báo kết quả:**

- Ghi version JDK, OS, filesystem, thiết bị, kích thước file, cache state, buffer size.
- Công bố số lượt chạy, phương pháp warmup và thống kê kết quả.
- Tách cold/warm, steady-state/end-to-end nếu cần.
- Xác minh mọi phương án đều tạo kết quả giống nhau.
- Chỉ khuyến nghị phương án “nhanh hơn” **cho workload đã đo**, không nâng thành quy luật chung.

## 25. Tổng kết

Không có một lựa chọn duy nhất luôn chiến thắng giữa **Buffered IO**, **FileChannel**, **`transferTo`**, **`Files.copy`** và **`MappedByteBuffer`**.

- **Buffered stream** đơn giản, phù hợp tuần tự và có thể rất hiệu quả.
- **FileChannel** hữu ích cho positional I/O và thao tác với `ByteBuffer`; không có bảo đảm nhanh hơn chỉ vì thuộc NIO.
- **`transferTo`/`transferFrom`** mở cơ hội tối ưu chuyển dữ liệu; phải xử lý partial transfer và không giả định luôn zero-copy.
- **Memory mapping** có thể thuận tiện, đặc biệt với random access lặp lại, nhưng có chi phí page faults, metadata, tài nguyên native và vòng đời mapping cần quản lý.
- **Page cache, filesystem, OS, JVM và workload** là những biến chi phối thực tế; điều kiện warm/cold quan trọng.
- **Benchmark có kiểm soát + correctness verification** là cơ sở lựa chọn, không phải tên API hoặc kết quả một lần chạy.

**Nguyên tắc thực tế:** bắt đầu bằng phương án **đúng, dễ hiểu và bounded**, xác định bottleneck bằng phép đo, rồi chỉ tăng độ phức tạp khi lợi ích có thể chứng minh và vẫn đáp ứng yêu cầu về độ ổn định, tính portable và khả năng bảo trì.

**Tài liệu Java SE 17:**

1. [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html) — `read/write`, positional I/O, `transferTo`, `transferFrom`, `map`, `force`.
2. [MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html) — mapping semantics, `load/isLoaded/force`.
3. [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html) — heap/direct buffer, `position/limit`.
4. [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `copy`, `newInputStream`, `mismatch`.
5. [BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html) và [BufferedOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html).
