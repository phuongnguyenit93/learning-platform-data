# Xử lý tệp lớn theo từng khối thay vì đưa toàn bộ tệp vào bộ nhớ (Java Core I/O)

## 1. Vấn đề: tệp lớn hơn ngân sách bộ nhớ

Khi tệp chỉ vài kilobyte, cách đọc toàn bộ nội dung có thể rất tiện:

~~~java
byte[] bytes = Files.readAllBytes(path);
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là **đoạn minh họa**, với `path` là `Path` đã có và cần import `Files`, `StandardCharsets`. Hai lời gọi trên thuận tiện cho tệp nhỏ có giới hạn rõ ràng; nhưng không nên tự động áp dụng cho file vài gigabyte hoặc dữ liệu đầu vào không tin cậy.

Khi đọc toàn bộ vào `byte[]`, chương trình cần một mảng đủ chứa nội dung tệp và có thể cần thêm các bản sao trong quá trình giải mã, chuyển đổi hoặc xử lý. Một `byte[]` dùng chỉ số `int`; việc nạp tệp rất lớn vào một mảng cũng bị giới hạn bởi kích thước mảng và heap JVM. `Files.readAllBytes` có thể ném `OutOfMemoryError` hoặc `IOException` với tệp quá lớn; `Files.readString` cũng cần materialize cả chuỗi nội dung trong bộ nhớ.

**Cách tiếp cận theo khối (chunked/streaming I/O)** là chỉ giữ một vùng đệm có kích thước giới hạn, ví dụ 8 KiB, 64 KiB hoặc 1 MiB; đọc dữ liệu vào đó, xử lý/ghi ra, rồi tái sử dụng vùng đệm. Khi thiết kế đúng, bộ nhớ đệm I/O **không tăng theo tổng kích thước tệp**.

Bài này giúp bạn:

- So sánh mô hình đọc toàn bộ và đọc theo khối, nhận diện ưu/nhược điểm.
- Viết vòng lặp đọc/ghi Java I/O chuẩn cho tệp lớn, xử lý EOF và số byte thực tế.
- Phân biệt `InputStream`/`OutputStream` với `FileChannel`/`ByteBuffer`, nhất là ghi từng phần.
- Chọn buffer và cơ chế chuyển dữ liệu phù hợp workload.
- Tránh lỗi tràn số, mất dữ liệu ở chunk cuối, hỏng UTF-8, tích lũy bộ nhớ ngầm và thiếu kiểm soát tài nguyên.
- Hiểu khi nào streaming đơn thuần chưa đủ, chẳng hạn thuật toán cần random access hoặc sắp xếp toàn bộ dữ liệu.

## 2. Hai mô hình xử lý

### 2.1. Đọc toàn bộ rồi xử lý

~~~text
Tệp trên đĩa: [................................ nhiều GB ................................]
                            |
                            v
                       readAllBytes()
                            |
                            v
Heap:              [......... toàn bộ file .........]
                            |
                            v
                      Xử lý / ghi ra
~~~

Các bước thường gặp là đọc tất cả byte, tạo đối tượng biểu diễn nội dung, biến đổi rồi ghi ra. Ưu điểm: mã có thể ngắn, dễ truy cập ngẫu nhiên trong mảng đối với dữ liệu đủ nhỏ. Nhược điểm: peak heap và thời gian chờ trước khi có dữ liệu để xử lý tăng theo kích thước file.

Một bộ chuyển đổi vô ý giữ `byte[]` đầu vào, `String` trung gian và `byte[]` đầu ra cùng lúc có thể làm nhu cầu RAM lớn hơn nhiều lần kích thước tệp. Không có công thức nhân cố định cho mọi chương trình; phụ thuộc encoding, cấu trúc đối tượng, thuật toán và GC.

### 2.2. Đọc từng khối rồi xử lý/ghi ngay

~~~text
Tệp nguồn [block 1][block 2][block 3]...[block N]
             |          |         |          |
             v          v         v          v
         [buffer 8 KiB tái sử dụng] ---> [tệp đích / consumer]
~~~

Đường đi điển hình:

1. Cấp phát một `byte[]` hoặc `ByteBuffer` có dung lượng cố định.
2. Đọc tối đa một lượng byte vào buffer.
3. Sử dụng **đúng lượng byte được báo đã đọc**, không phải luôn cả kích thước buffer.
4. Ghi, kiểm tra hoặc biến đổi dữ liệu.
5. Lặp lại đến EOF; đóng luồng/kênh và xử lý lỗi.

Nếu chỉ dùng một buffer 8 KiB, việc tệp dài 1 MiB hay 100 GiB **không buộc buffer đó lớn thêm**. Tuy nhiên, bộ nhớ toàn chương trình còn bao gồm JVM, thư viện, page cache, hàng đợi, dữ liệu do nghiệp vụ tích lũy; streaming **không tự động bảo đảm** tổng RAM luôn thấp nếu mỗi khối bị giữ lại trong `List` hoặc cache không giới hạn.

## 3. API thường dùng trong Java 17+

| API | Đặc điểm | Khi nào cân nhắc |
| --- | --- | --- |
| `Files.newInputStream(path)` | Mở `InputStream` đọc byte từ tệp | Đọc tuần tự theo khối, tích hợp parser/transform |
| `Files.newOutputStream(path, options...)` | Mở `OutputStream` ghi byte | Ghi tuần tự, sao chép/biến đổi |
| `BufferedInputStream`/`BufferedOutputStream` | Tăng buffering cho nhiều thao tác nhỏ | Khi nguồn/đích có nhiều lời gọi I/O byte nhỏ |
| `FileChannel.read/write(ByteBuffer)` | API NIO với `ByteBuffer`, hỗ trợ offset/channel | Khi cần random access, position hoặc kiểm soát buffer |
| `FileChannel.transferTo/transferFrom` | Chuyển dữ liệu giữa channel | Sao chép/đẩy dữ liệu khối lớn; phải kiểm tra số byte thực tế |
| `Files.copy(source, destination, options...)` | API sao chép tệp mức cao | Khi chỉ cần copy, không cần xử lý từng chunk |
| `BufferedReader`/`Files.newBufferedReader` | Đọc văn bản theo ký tự/dòng | Khi parser logic hoạt động theo dòng; cần giới hạn độ dài dòng |
| `Files.lines(path)` | Trả về stream dòng đọc lazily | Khi xử lý tuần tự các dòng; đóng stream, tránh terminal operations tích lũy |

**Chọn công cụ theo yêu cầu**, không mặc định `FileChannel` luôn nhanh hơn stream hoặc `transferTo` luôn là zero-copy. Chúng có các chi phí, tối ưu hệ điều hành và hành vi khác nhau.

## 4. Vòng lặp byte stream đúng

Mẫu phổ biến:

~~~java
byte[] buffer = new byte[8192];
long totalBytes = 0;

try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(
             target, StandardOpenOption.CREATE_NEW,
             StandardOpenOption.WRITE)) {

    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n == 0) {
            throw new IOException("Không có tiến triển khi đọc file");
        }
        out.write(buffer, 0, n);
        totalBytes += n;
    }
}
~~~

Đây là **đoạn minh họa** với `source`/`target` là `Path` đã có, cần import `InputStream`, `OutputStream`, `Files`, `StandardOpenOption` và `IOException`. `target` phải chưa tồn tại do dùng `CREATE_NEW`. Chương trình chạy đầy đủ sẽ xuất hiện ở phần 7.

Các điểm thiết yếu:

- `in.read(buffer)` trả **số byte thực tế** trong khoảng cho phép, hoặc `-1` khi hết luồng.
- Một lời gọi đọc **không** bảo đảm điền đầy 8192 byte; có thể chỉ đọc vài trăm byte dù tệp còn dữ liệu.
- `out.write(buffer, 0, n)` dùng đúng `n` byte. Nếu cứ ghi `buffer.length` sẽ đưa byte cũ của lần đọc trước vào đầu ra ở lần đọc cuối.
- Với `OutputStream` đồng bộ, `write(byte[],off,len)` thành công nghĩa là phương thức đã ghi đủ `len` byte theo hợp đồng của API; khi không thể hoàn thành, nó ném `IOException`. Không cần vòng lặp ghi từng phần **cho chính lời gọi OutputStream.write này**; nhưng API channel có hợp đồng khác.
- `long totalBytes` cho phép đếm lượng dữ liệu lớn hơn 2 GiB; trong các vòng lặp xử lý rất dài còn phải cân nhắc overflow của `long` và quota nghiệp vụ.
- `try-with-resources` đóng cả đầu vào và đầu ra kể cả khi gặp exception. Đóng/flush và độ bền trên thiết bị lưu trữ là những vấn đề riêng nếu ứng dụng cần bảo đảm dữ liệu sống sót qua sự cố điện.

### EOF và số byte 0

Với `InputStream.read(byte[])` và buffer có chiều dài dương, một luồng file blocking thông thường tiến triển bằng số byte dương hoặc `-1`. Tuy nhiên, mã làm việc qua một wrapper/provider bất thường không nên biến kết quả `0` thành vòng lặp quay vô hạn; ví dụ trên chọn báo lỗi.

**Không dùng `in.available() == 0` để nhận biết EOF.** `available()` chỉ ước lượng lượng byte có thể đọc mà không chặn, **không phải** số byte còn lại của tệp, cũng không phải điều kiện kết thúc chính xác cho luồng bất kỳ.

**Không dùng `read(...) == buffer.length` để đoán rằng mọi file đã đọc xong.** Mỗi lần đọc có thể trả ít byte; chỉ `-1` là EOF với `InputStream.read`.

## 5. Vì sao khối cuối rất dễ bị ghi sai?

Giả sử tệp có 20.003 byte và buffer dài 8.192 byte. Tùy hành vi đọc, một kịch bản có thể là:

~~~text
Đọc 1: 8192 byte --> ghi 8192
Đọc 2: 8192 byte --> ghi 8192
Đọc 3: 3619 byte --> ghi 3619
Đọc 4: -1        --> kết thúc
Tổng: 20003 byte
~~~

**Không bảo đảm** ba lần đọc đầu đúng như ví dụ: API có thể trả các khối ngắn hơn. Tuy nhiên, tổng các lần đọc dương phải bằng số byte mà ứng dụng thực sự đã nhận trước EOF. Không được suy ra lượng byte từ số vòng lặp nhân kích thước buffer.

Lỗi thường thấy:

~~~java
int n = in.read(buffer);
if (n > 0) {
    out.write(buffer); // SAI: ghi luôn 8192 byte, kể cả byte cũ.
}
~~~

Sửa thành:

~~~java
int n = in.read(buffer);
if (n > 0) {
    out.write(buffer, 0, n); // Chỉ ghi byte vừa đọc.
}
~~~

Hai đoạn này là **minh họa**, không phải chương trình độc lập. Với vòng lặp thật phải xử lý `-1` và trường hợp lỗi theo API.

## 6. Chọn kích thước buffer: không có con số thần kỳ

Một số kích thước thường thử khi benchmark: 4 KiB, 8 KiB, 64 KiB, 256 KiB hoặc 1 MiB. Không có quy tắc “buffer càng lớn càng tốt”.

| Buffer | Lợi ích tiềm năng | Chi phí/điểm cân nhắc |
| --- | --- | --- |
| Rất nhỏ (vài chục byte) | Ít heap cho từng luồng | Rất nhiều lời gọi đọc/ghi, overhead cao |
| 4–16 KiB | Dễ dùng, ít bộ nhớ cho mỗi thao tác | Có thể chưa tối ưu với throughput cao |
| 64–256 KiB | Ít vòng đọc/ghi hơn trong copy tuần tự | Tăng bộ nhớ theo số tác vụ đồng thời |
| 1 MiB trở lên | Có thể có ích trong một số workload lớn | Tốn RAM nếu hàng nghìn request cùng giữ buffer |

Ví dụ 2.000 tác vụ đồng thời, mỗi tác vụ giữ một buffer 1 MiB, riêng các buffer đã có thể chiếm xấp xỉ **2.000 MiB** (~1,95 GiB), chưa kể phần khác. Nếu mỗi buffer là 8 KiB thì tổng buffer khoảng **15,6 MiB**. Vì vậy phải tính ngân sách theo **buffer size × concurrency × số buffer/tác vụ**.

Benchmark cần cố định dữ liệu, môi trường, thiết bị lưu trữ, tình trạng page cache và mức độ đồng thời. Hãy đo throughput, CPU, garbage collection, heap/RSS, thời gian P95/P99 thay vì chỉ một lần chạy có cache nóng.

### Buffering lớp ngoài

`BufferedInputStream` hoặc `BufferedOutputStream` hữu ích khi nhiều lời gọi đọc/ghi nhỏ (ví dụ từng byte) gây overhead. Nếu đã tự gọi `in.read(buffer)` bằng các khối 64 KiB, thêm một lớp buffer nữa không đương nhiên cải thiện hiệu năng; đôi khi chỉ tạo thêm một lớp copy. Đo trên workload thật.

### Có nên cấp phát buffer trong mỗi vòng lặp?

Tránh:

~~~java
while (moreData) {
    byte[] data = new byte[8192]; // Cấp phát lại liên tục.
    // Đọc và xử lý.
}
~~~

Đây là **mẫu phản ví dụ** với `moreData` tượng trưng cho điều kiện của vòng lặp. Cấp phát mới trên mỗi lần đọc tạo áp lực GC không cần thiết. Với tác vụ đơn giản, cấp phát buffer **một lần trước vòng lặp** rồi tái sử dụng.

Nếu dùng pool buffer giữa nhiều tác vụ, phải xác định rõ ownership. Không cấp cùng buffer mutable cho hai thread đang đọc/ghi đồng thời nếu không có điều phối an toàn.

## 7. Ví dụ Java 17+ hoàn chỉnh và kiểm chứng được

Chương trình tạo một tệp nguồn chứa **12 khối 8.192 byte chữ A** và **3 byte XYZ**, tổng cộng **98.307 byte**. Sau đó nó sao chép sang tệp mới bằng buffer 8 KiB, đếm số byte sao chép, kiểm tra nội dung đích và xóa dữ liệu tạm khi kết thúc.

Để stdout không phụ thuộc việc `InputStream.read` tùy môi trường trả các khối ngắn hay dài, chương trình chỉ in **tổng byte**, **kích thước buffer** và **so sánh nội dung**; không cam kết số lần đọc cố định.

Lưu là **`ChunkedFileCopyDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public class ChunkedFileCopyDemo {
    private static final int BUFFER_SIZE = 8192;

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("chunked-copy-");
        Path source = directory.resolve("source.bin");
        Path target = directory.resolve("target.bin");

        try {
            makeSource(source);
            long copied = copyByChunks(source, target);

            System.out.println("Source bytes: " + Files.size(source));
            System.out.println("Copied bytes: " + copied);
            System.out.println("Buffer bytes: " + BUFFER_SIZE);
            System.out.println("Content equal: "
                    + (Files.mismatch(source, target) == -1));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }

    private static void makeSource(Path source) throws IOException {
        byte[] block = new byte[BUFFER_SIZE];
        Arrays.fill(block, (byte) 'A');

        try (OutputStream out = Files.newOutputStream(
                source,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE)) {
            for (int i = 0; i < 12; i++) {
                out.write(block);
            }
            out.write("XYZ".getBytes(StandardCharsets.US_ASCII));
        }
    }

    private static long copyByChunks(Path source, Path target)
            throws IOException {
        byte[] buffer = new byte[BUFFER_SIZE];
        long total = 0;

        try (InputStream in = Files.newInputStream(source);
             OutputStream out = Files.newOutputStream(
                     target,
                     StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE)) {

            int n;
            while ((n = in.read(buffer)) != -1) {
                if (n == 0) {
                    throw new IOException("No progress while reading");
                }
                out.write(buffer, 0, n);
                total = Math.addExact(total, n);
            }
        }
        return total;
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ChunkedFileCopyDemo.java
java ChunkedFileCopyDemo
~~~

**Stdout kỳ vọng khi tệp tạm tạo và sao chép thành công:**

~~~text
Source bytes: 98307
Copied bytes: 98307
Buffer bytes: 8192
Content equal: true
~~~

### Giải thích chi tiết

1. `makeSource` ghi 12 × 8.192 = 98.304 byte `A`, rồi thêm đúng ba byte ASCII `XYZ`. Tổng là 98.307 byte; nguồn được tạo trên đĩa bằng nhiều lần ghi, không phải bằng mảng 98.307 byte.
2. `copyByChunks` cấp phát **một** `byte[8192]`. Kích thước file không ảnh hưởng dung lượng buffer; chương trình tái sử dụng nó sau mỗi lần ghi xong.
3. `in.read(buffer)` có thể trả số byte bất kỳ phù hợp hợp đồng API. `out.write(buffer, 0, n)` đảm bảo không ghi byte cũ còn sót trong buffer, đặc biệt ở khối cuối.
4. `Math.addExact(total, n)` phát hiện tràn số `long` bằng exception thay vì âm thầm vòng về số âm. Với tệp demo ngắn, không thể tràn.
5. `CREATE_NEW` từ chối ghi đè một tệp đích đã tồn tại.
6. `Files.mismatch(source, target) == -1` xác nhận nội dung byte của hai tệp giống nhau sau khi đóng các luồng. Thao tác này đọc thêm dữ liệu để so sánh, phù hợp kiểm tra demo nhưng có chi phí I/O cho tệp sản xuất rất lớn.
7. `finally` dọn hai tệp và thư mục tạm sau khi hoàn tất. Nếu I/O lỗi, phương thức sẽ ném exception; chương trình không in một kết quả thành công giả.
8. Khối dữ liệu cuối có thể được trả về trong một hoặc nhiều lần `read`; **stdout vẫn giống nhau** do cách đếm byte thực tế và so sánh nội dung, không phải vì API bảo đảm lần đọc cuối đúng 3 byte.

## 8. Phiên bản dùng FileChannel và ByteBuffer

`FileChannel` phù hợp khi cần thao tác theo vị trí, đọc/ghi ngẫu nhiên hoặc dùng `ByteBuffer` trong NIO. Mẫu streaming tuần tự:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(64 * 1024);
long total = 0;

try (FileChannel src = FileChannel.open(source, StandardOpenOption.READ);
     FileChannel dst = FileChannel.open(
             target, StandardOpenOption.CREATE_NEW,
             StandardOpenOption.WRITE)) {

    while (src.read(buffer) != -1) {
        buffer.flip(); // Đọc byte vừa nhận từ buffer để ghi đi.

        while (buffer.hasRemaining()) {
            int n = dst.write(buffer);
            if (n == 0) {
                throw new IOException("Channel write made no progress");
            }
            total = Math.addExact(total, n);
        }
        buffer.clear(); // Sẵn sàng nhận khối tiếp theo.
    }
}
~~~

Đây là **đoạn minh họa**, cần các import `java.nio.ByteBuffer`, `java.nio.channels.FileChannel`, `java.nio.file.Files`, `java.nio.file.Path`, `StandardOpenOption` và `java.io.IOException`; `source`/`target` là các `Path` đã có. Để dùng trong môi trường có provider đặc biệt, cũng nên xử lý `src.read(...) == 0` theo chính sách không tiến triển thay vì vòng lặp nóng.

Khác biệt quan trọng so với `OutputStream`:

- `FileChannel.write(ByteBuffer)` có thể trả về **ít hơn** `buffer.remaining()`; vòng `while (buffer.hasRemaining())` đảm bảo đẩy hết khối vừa đọc trước khi tái sử dụng buffer.
- `ByteBuffer.flip()` chuyển từ trạng thái ghi dữ liệu vào buffer sang trạng thái đọc dữ liệu ra để gửi đi.
- `ByteBuffer.clear()` đặt lại `position/limit`, **không xóa byte**. Chỉ làm sau khi toàn bộ khối đã được ghi xong.
- Nếu `FileChannel.read(buffer)` trả `0`, `buffer.flip()` có thể tạo vùng không còn byte; chương trình ví dụ không busy-spin vì một lần ghi vòng trong không chạy, nhưng vòng ngoài có thể tiếp tục ngay. Với provider bất thường hoặc non-blocking channel, phải có chính sách backoff/readiness tương ứng.

### Có nên dùng direct buffer?

`ByteBuffer.allocateDirect(size)` tạo vùng bộ nhớ trực tiếp ngoài Java heap theo khả năng JVM/provider và có thể giảm một số copy khi I/O native. Đổi lại, allocation/cleanup có chi phí và bộ nhớ native vẫn cần được giám sát. Không tạo direct buffer mới ở mỗi vòng đọc; nên tái sử dụng theo vòng đời phù hợp. Không mặc định direct buffer nhanh hơn heap buffer trên mọi nền tảng.

## 9. FileChannel.transferTo/transferFrom và tệp lớn

Nếu mục tiêu chỉ là chuyển byte từ tệp sang channel khác, có thể cân nhắc:

~~~java
long remaining = sourceChannel.size();
long offset = 0;

while (remaining > 0) {
    long n = sourceChannel.transferTo(
            offset, remaining, destinationChannel);
    if (n == 0) {
        throw new IOException("Transfer made no progress");
    }
    offset += n;
    remaining -= n;
}
~~~

Đây là **đoạn minh họa**, `sourceChannel` là `FileChannel` nguồn đã mở, `destinationChannel` là `WritableByteChannel` đích đã mở, cần `IOException`. Gọi một lần với `count` lớn **không bảo đảm** chuyển đủ byte: hệ điều hành có thể giới hạn mỗi lần chuyển, EOF có thể đến sớm và đích có thể chịu backpressure.

Một số provider dùng kỹ thuật giảm copy (thường gọi là *zero-copy*) cho những cặp channel nhất định, nhưng Java không cam kết mọi trường hợp `transferTo` đều zero-copy. Cũng phải cân nhắc nguồn bị thay đổi trong lúc copy và đích không được chứa dữ liệu cũ còn thừa.

`Files.copy(source, target)` là lựa chọn đơn giản hơn khi không cần xử lý từng khối; ưu tiên API mức cao trước khi tự tối ưu nếu yêu cầu nghiệp vụ chỉ là sao chép.

## 10. Xử lý tệp văn bản theo khối: ranh giới byte khác ranh giới ký tự

Sao chép byte thuần có thể chia tùy ý: khi ghép đúng thứ tự, byte đầu ra sẽ vẫn giống đầu vào. Nhưng **giải mã văn bản** có ràng buộc mới.

UTF-8 biểu diễn một ký tự bằng 1–4 byte. Ví dụ chữ có dấu hoặc emoji có thể bị chia làm hai phần ở ranh giới giữa hai khối. Nếu gọi:

~~~java
String text = new String(buffer, 0, n, StandardCharsets.UTF_8);
~~~

trên **từng chunk độc lập**, bạn có thể giải mã một phần ký tự thành ký tự thay thế hoặc dữ liệu không chính xác. Đây là đoạn minh họa cho lỗi tiềm ẩn nếu byte UTF-8 bị cắt ngang.

### Các cách đúng theo bài toán

**Cách A — xử lý văn bản theo dòng bằng Reader:**

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
~~~

Đây là đoạn minh họa với `path` và phương thức `process(String)` do ứng dụng định nghĩa. `BufferedReader` quản lý giải mã ký tự xuyên qua các lần đọc byte bên trong; tuy nhiên `readLine()` vẫn xây dựng **cả một dòng thành `String`**. Một dòng dài hàng gigabyte vẫn có nguy cơ hết bộ nhớ. Nếu đầu vào không tin cậy, áp giới hạn chiều dài dòng hoặc dùng parser streaming giữ state hữu hạn.

**Cách B — xử lý định dạng nhị phân hoặc văn bản tự định nghĩa theo chunk:** dùng `CharsetDecoder` với `CoderResult` và giữ lại byte chưa giải mã ở cuối buffer bằng `compact()` hoặc state tương ứng. Chỉ công bố các ký tự đã giải mã hợp lệ; quản lý EOF và dữ liệu không đầy đủ cuối luồng. Cách này phức tạp hơn nhưng phù hợp khi cần kiểm soát chặt mức RAM, framing hay chính sách lỗi encoding.

**Cách C — chỉ sao chép nguyên byte:** không cần giải mã; dùng `InputStream`/`OutputStream` hoặc `FileChannel`. Đây là lựa chọn đơn giản, tránh việc biến đổi Unicode ngoài ý muốn.

### Ranh giới record có thể bắc qua chunk

Ngay cả khi dữ liệu là ASCII, một dòng CSV, khối JSON hoặc record nhị phân có thể bị cắt giữa hai lần đọc. Parser phải giữ **phần chưa xử lý** từ khối trước và nối với khối sau, hoặc thiết kế state machine đọc token/record tăng dần.

Nếu một record đơn lẻ có thể lớn không giới hạn, chỉ dùng buffer cố định không đủ để đảm bảo RAM: phải áp `MAX_RECORD_BYTES`, xuất record ra chỗ lưu tạm, hoặc thay đổi giao thức/thuật toán.

## 11. Xử lý lớn không chỉ là sao chép: checksum, nén, chuyển đổi

### 11.1. Tính SHA-256 streaming

Có thể tính hash mà không nạp toàn file:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] buffer = new byte[64 * 1024];

try (InputStream in = Files.newInputStream(path)) {
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n > 0) {
            digest.update(buffer, 0, n);
        }
    }
}
byte[] sha256 = digest.digest();
~~~

Đây là **đoạn minh họa** với `path` đã có; cần import `InputStream`, `Files`, `MessageDigest` và xử lý `NoSuchAlgorithmException`/`IOException`. Độ dài bộ đệm và state digest không tăng theo kích thước file; kết quả SHA-256 có 32 byte.

**Cẩn trọng:** hash xác nhận cùng nội dung khi so sánh với một digest **đáng tin**; tự tính hash trên file không tin cậy không chứng minh nguồn gửi hợp pháp. Nếu mục tiêu là phát hiện sửa đổi, cần quy trình nhận/phân phối digest độc lập và an toàn.

### 11.2. Nén và giải nén streaming

`GZIPInputStream`/`GZIPOutputStream` có thể đặt quanh luồng I/O để nén/giải nén theo dòng byte. Tuy nhiên, giải nén là nơi cần quan tâm **zip/decompression bomb**: dữ liệu nén nhỏ có thể giải nén rất lớn. Phải giới hạn **byte đầu ra thực tế**, ratio, thời gian và tài nguyên, không dùng streaming như lý do bỏ quota.

### 11.3. Chuyển đổi có trạng thái

Nếu biến đổi dữ liệu cần biết record trước/sau, phải giữ trạng thái đủ cho thuật toán. Đừng lén đưa toàn bộ file vào bộ nhớ bằng `List<String> allLines`, `Collectors.toList()` hoặc `ByteArrayOutputStream` không giới hạn rồi vẫn gọi chương trình là streaming.

Một thuật toán như sort toàn bộ file không thể chỉ dùng một buffer nhỏ mà giữ dữ liệu xếp hạng trong RAM nếu file lớn hơn RAM. Khi đó cân nhắc **external merge sort**: chia file thành các run vừa bộ nhớ, sắp xếp từng run ra tệp tạm rồi merge bằng queue giới hạn.

## 12. Backpressure và đường ống nhiều tầng

Đọc theo khối giúp giới hạn bộ nhớ của **một bước**, nhưng hệ thống có thể gồm nhiều bước: đọc → giải mã → parse → xử lý → ghi.

Nếu consumer chậm hơn producer và bạn đẩy mọi chunk vào một queue vô hạn, RAM vẫn tăng theo số chunk tồn đọng. Cần **backpressure**:

- Dùng queue có capacity cụ thể; khi queue đầy, nguồn phải chờ/tạm dừng hoặc từ chối/tải xuống chậm hơn.
- Hạn chế số worker và số buffer đồng thời.
- Chỉ tái sử dụng buffer sau khi consumer đã dùng xong.
- Định nghĩa timeout, cancellation và cleanup khi một tầng thất bại.
- Giám sát queue depth, tốc độ đọc/ghi, thời gian chờ, throughput và memory.

Với mô hình đơn luồng `read -> process -> write`, backpressure khá tự nhiên: chỉ đọc khối tiếp theo sau khi đã xử lý xong khối hiện tại. Với I/O async hoặc reactive pipeline, phải điều phối yêu cầu/khả năng nhận để tránh vượt ngân sách.

## 13. Tính đúng đắn khi tệp nguồn có thể thay đổi

Khi xử lý tệp lớn trong nhiều giây/phút, nguồn có thể bị ứng dụng khác sửa trong lúc đọc. Hãy xác định nhu cầu consistency:

- Nếu chỉ cần copy **byte đã đọc được trong lần chạy**, streaming tuần tự phù hợp; nhưng một file đang thay đổi có thể tạo kết quả pha trộn không nhất quán.
- Nếu cần bản sao nguyên vẹn của **một phiên bản cụ thể**, cần snapshot, phối hợp producer, phiên bản bất biến hoặc giao thức khóa thích hợp. `Files.size()` đọc trước không tự đóng băng nội dung.
- Nếu cần publish kết quả chỉ khi copy thành công, ghi vào **file staging** rồi kiểm tra và chuyển sang đường dẫn công bố theo khả năng file system. `Files.move(..., ATOMIC_MOVE)` chỉ có bảo đảm nếu provider hỗ trợ; phải xử lý `AtomicMoveNotSupportedException` theo thiết kế.
- Nếu đích đã tồn tại, lựa chọn `CREATE_NEW` giúp từ chối ghi đè. Nếu nghiệp vụ cho phép replace, phải định nghĩa quy trình overwrite/truncate và rollback khi copy lỗi.

### Quota và dữ liệu không tin cậy

Streaming không có nghĩa tệp vô hạn là an toàn. Khi nhận tệp từ bên ngoài, giới hạn tổng byte, thời gian, số file, tốc độ và dung lượng đĩa. Ví dụ kiểm tra quota tránh tràn:

~~~java
if (n > allowedBytes - totalBytes) {
    throw new IOException("Byte quota exceeded");
}
totalBytes += n;
~~~

Đây là đoạn minh họa, yêu cầu `n > 0`, `totalBytes >= 0` và `totalBytes <= allowedBytes` trước phép so sánh. Nếu vượt quota, **đừng ghi chunk đó**. Không chờ đến cuối mới kiểm tra vì disk/RAM có thể đã cạn.

## 14. Hiệu năng: cần đo điều gì?

Nếu dùng tệp rất lớn để benchmark, so sánh trên đúng storage workload. Các con số quan trọng:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Throughput (MiB/s) | Lượng byte xử lý thực tế mỗi giây |
| Peak heap / native RSS | Đánh giá memory pressure và allocation |
| CPU utilization | Phát hiện chi phí giải mã, copy hoặc hashing |
| GC pauses / allocation rate | Phát hiện cấp phát quá nhiều object mỗi chunk |
| Disk I/O, page cache | Phân biệt đọc từ cache với storage thực |
| P95/P99 latency | Quan trọng khi xử lý nhiều request đồng thời |
| Queue depth / wait time | Đo backpressure và cân bằng producer/consumer |
| Số byte/record xử lý thành công | Phát hiện mất dữ liệu hoặc xử lý thiếu |

**Đừng chỉ chọn khối lớn nhất vì một lần benchmark thấy nhanh.** Với 1.000 request đồng thời, RAM và GC có thể thay đổi thứ tự xếp hạng. Đo cold/warm cache riêng nếu mục tiêu là hiệu năng ổ đĩa.

Với tệp ổn định lớn, `Files.mismatch` hoặc hash sau khi copy là cách kiểm tra nội dung, nhưng bản thân bước verify tạo thêm I/O. Phải quyết định yêu cầu toàn vẹn của nghiệp vụ và tính chi phí này vào benchmark.

## 15. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gọi `Files.readAllBytes` cho file kích thước không kiểm soát | OOM, tốn heap | Đọc chunk, giới hạn input |
| Ghi đủ `buffer.length` dù lần đọc cuối ngắn hơn | Byte cũ ở đuôi bản sao | Ghi đúng `n` byte thực tế |
| Dùng `available() == 0` làm EOF | Dừng sớm hoặc logic sai | Dựa vào `read() == -1` |
| Dùng `int` đếm tổng byte | Tràn trên file >2 GiB | Dùng `long`, kiểm tra overflow/quota |
| Gọi `new byte[8192]` trong mọi vòng lặp | Allocation/GC tăng | Tái sử dụng buffer |
| Dùng `ByteBuffer.clear()` trước khi ghi hết | Mất phần chưa ghi | `flip` rồi `while(hasRemaining)`, sau đó `clear` |
| Giả định một lần `FileChannel.write` ghi hết | Bản sao thiếu dữ liệu | Kiểm tra giá trị trả về và lặp |
| Tự giải mã UTF-8 từng chunk byte độc lập | Hỏng ký tự đa byte | Reader/CharsetDecoder có trạng thái |
| `readLine()` trên văn bản không giới hạn độ dài dòng | Có thể tích lũy một dòng cực lớn | Quota per-line hoặc parser giới hạn |
| Gom mọi chunk vào `List` không giới hạn | Streaming giả, RAM tăng theo file | Xử lý và giải phóng từng chunk |
| Hàng đợi pipeline vô hạn | Consumer chậm làm RAM tăng | Bounded queue/backpressure |
| Không đóng stream/channel | Rò file descriptor, file lock | `try-with-resources` |
| Tự tăng offset theo kích thước yêu cầu của `transferTo` | Bỏ sót dữ liệu khi chuyển từng phần | Tăng theo byte thực tế |
| Tin file ổn định khi đang bị ghi | Copy phiên bản hỗn hợp | Snapshot/version/publish protocol |
| Không có quota và cleanup khi gặp lỗi | Disk đầy, file đích dang dở | Quota trong loop, staging và cleanup |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Bạn có tệp 30 GiB và JVM heap 512 MiB. Có nên gọi `Files.readAllBytes`?

**Đáp án:** Không. Không thể nhét tệp 30 GiB vào một `byte[]`/heap 512 MiB. Hãy xử lý theo chunk hoặc dùng API file-level khác phù hợp.

**Câu 2.** Buffer 8192 byte; lần `read` cuối chỉ trả 27. `out.write(buffer)` có đúng không?

**Đáp án:** Không. Phải dùng `out.write(buffer, 0, 27)` để tránh ghi byte cũ.

**Câu 3.** `FileChannel.write(buffer)` trả 2000 trong khi còn 8192 byte. Cần làm gì?

**Đáp án:** Còn 6192 byte trong buffer. Tiếp tục ghi đến khi `!buffer.hasRemaining()` rồi mới tái sử dụng buffer.

**Câu 4.** Streaming với buffer 64 KiB có bảo đảm ứng dụng dùng đúng 64 KiB RAM?

**Đáp án:** Không. Đó chỉ là một buffer. JVM, parser, queue, cache, native memory và các task khác vẫn cần RAM.

**Câu 5.** Tại sao `new String(bytes, UTF_8)` cho từng khối 8 KiB có thể lỗi dù file text hợp lệ?

**Đáp án:** Ranh giới khối có thể cắt giữa các byte UTF-8 của cùng ký tự. Dùng Reader hoặc CharsetDecoder có trạng thái.

**Câu 6.** Nếu có 500 tác vụ, mỗi tác vụ giữ 1 MiB input buffer và 1 MiB output buffer, riêng buffer tốn khoảng bao nhiêu?

**Đáp án:** 500 × 2 × 1 MiB = 1000 MiB (~0,98 GiB), chưa tính heap/runtime khác.

**Câu 7.** Đọc file theo khối giúp tự động có snapshot nhất quán khi producer đang ghi không?

**Đáp án:** Không. Phải phối hợp phiên bản/snapshot hoặc giao thức công bố an toàn.

**Câu 8.** Khi nào `Files.copy` tốt hơn tự viết loop streaming?

**Đáp án:** Khi chỉ cần sao chép file và không phải phân tích, giới hạn theo chunk hay chuyển đổi dữ liệu đặc biệt; API mức cao ngắn, dễ bảo trì hơn.

## 17. Ghi nhớ

- **Xử lý từng khối** cho phép bộ nhớ đệm I/O không tăng theo kích thước file, nếu dữ liệu được xử lý rồi giải phóng thay vì tích lũy.
- **Luôn dựa vào số byte đọc thực tế**; `-1` là EOF của `InputStream`, `out.write(buffer,0,n)` tránh ghi byte cũ ở khối cuối.
- Với **`FileChannel`**, xử lý cả ghi từng phần, `flip`/`clear` và kiểm tra tiến triển.
- Với **văn bản/record**, đừng nhầm ranh giới khối byte với ranh giới ký tự hay bản ghi.
- **Buffer size × concurrency** ảnh hưởng ngân sách RAM; queue phải có backpressure.
- Nếu dữ liệu lớn hoặc không tin cậy, kết hợp **quota, cleanup, staging, kiểm tra tính toàn vẹn và đo đạc** thay vì chỉ tăng heap JVM.
