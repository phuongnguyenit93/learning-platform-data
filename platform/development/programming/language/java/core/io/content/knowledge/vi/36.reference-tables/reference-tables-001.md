# Bảng chọn InputStream, Reader, Files hoặc Channel trong Java

Khi làm việc với I/O, đừng bắt đầu bằng câu hỏi “API nào nhanh nhất?”. Hãy xác định **dữ liệu là byte hay văn bản, nguồn/đích là gì, có cần truy cập ngẫu nhiên không, và kích thước dữ liệu có thể tăng đến đâu**. Bốn cái tên trong tiêu đề giải quyết các nhu cầu khác nhau; nhiều trường hợp chúng được kết hợp với nhau.

> Phạm vi: Java 17+, chủ yếu là I/O đồng bộ. Ví dụ dùng `java.nio.file.Files`, `java.io.InputStream`/`Reader` và `java.nio.channels.Channel`.

## 1. Bảng chọn nhanh theo tình huống

| Nhu cầu thực tế | Ưu tiên | Vì sao | Tránh nhầm |
| --- | --- | --- | --- |
| Đọc toàn bộ **file văn bản nhỏ**, biết charset | `Files.readString(path, UTF_8)` | Mở, đọc, đóng tài nguyên trong một lệnh | File quá lớn sẽ tốn nhiều bộ nhớ |
| Ghi một chuỗi văn bản xuống file | `Files.writeString(path, text, UTF_8)` | Đơn giản, kiểm soát charset, có tùy chọn ghi | Mặc định có thể tạo mới hoặc ghi đè nội dung cũ |
| Duyệt từng dòng của file văn bản | `Files.newBufferedReader` + `BufferedReader.readLine`, hoặc `Files.lines` | Xử lý tăng dần, không cần nạp hết file | Phải đóng reader/stream; `readLine` bỏ ký tự xuống dòng |
| Đọc/ghi **byte thô** từ file, socket, HTTP body hoặc nguồn bất kỳ | `InputStream` / `OutputStream` | API byte liên tục, phổ biến cho dữ liệu nhị phân | Không chuyển ảnh/ZIP/PDF thành `Reader` |
| Sao chép file có sẵn sang file khác | `Files.copy(source, target, options)` | Ngắn gọn, xử lý đường dẫn và file | Không tự viết vòng lặp copy nếu chỉ cần sao chép file |
| Đọc file nhị phân nhỏ thành mảng byte | `Files.readAllBytes(path)` | Thuận tiện khi dữ liệu đủ nhỏ | Mảng lớn có thể hết bộ nhớ |
| Cần đọc/ghi ở **vị trí byte cụ thể** trong file | `SeekableByteChannel` hoặc `FileChannel` | Có `position(long)`; dùng `ByteBuffer` | `InputStream` thường là luồng đọc tiến, không hỗ trợ seek tổng quát |
| Cần khóa file, ánh xạ bộ nhớ, hoặc thao tác chuyên biệt trên file | `FileChannel` | Có `lock`, `map`, `transferTo`, `transferFrom` | Nhiều tính năng phụ thuộc hệ điều hành/file system |
| I/O mạng kiểu non-blocking, dùng selector | `SocketChannel` + `Selector` | Có thể làm việc với `java.nio` non-blocking | Không dùng channel chỉ vì tên “NIO”; API phức tạp hơn |
| Dữ liệu xuất phát từ một `InputStream` nhưng cần **đọc ký tự** | `InputStreamReader(in, charset)`, thường bọc `BufferedReader` | Giải mã byte sang ký tự đúng charset | Không giả định charset mặc định của máy |
| Chỉ cần kiểm tra, tạo, liệt kê, đổi tên, xóa đường dẫn/file | `Path` + phương thức `Files` | Đây là các thao tác file system, không cần tự mở stream | `Path` biểu diễn đường dẫn; nó không chứa dữ liệu của file |
| Nguồn rất lớn hoặc chưa biết kích thước | Stream/Reader/Channel đọc theo khối | Giữ lượng bộ nhớ gần như cố định | Tránh `readAllBytes`, `readString`, `readAllLines` không giới hạn |

**Quy tắc ngắn:** Nếu bài toán mô tả **thao tác trên file và đường dẫn**, bắt đầu từ `Path`/`Files`. Nếu bài toán mô tả **luồng byte**, chọn `InputStream`. Nếu nó mô tả **ký tự/văn bản**, chọn `Reader` cùng charset. Nếu cần **vị trí, buffer, kênh file hoặc I/O non-blocking**, xem `Channel`.

## 2. Hiểu chính xác bốn nhóm API

### `InputStream`: đọc byte tuần tự

`java.io.InputStream` cung cấp `read()`, `read(byte[])`, `read(byte[], off, len)`, `readAllBytes()` và `transferTo(OutputStream)`. Kết quả đọc là các **byte**, không phải ký tự. `read(...)` trả về số byte thực đọc, hoặc `-1` khi hết dữ liệu; không được giả định một lần đọc sẽ lấp đầy buffer.

Các lớp thường gặp là `FileInputStream` (file), `ByteArrayInputStream` (bộ nhớ), `BufferedInputStream` (đệm) và những stream do thư viện HTTP/ZIP/socket trả về. `InputStream` phù hợp ảnh, âm thanh, ZIP, PDF, định dạng giao thức, và cả văn bản **khi mục tiêu chỉ là vận chuyển byte không thay đổi**. Để tạo luồng từ `Path`, dùng `Files.newInputStream(path)`.

`OutputStream` là phía ghi byte. `BufferedInputStream`/`BufferedOutputStream` giảm số lần truy cập nguồn/đích; chúng không tự giải mã văn bản.

### `Reader`: đọc ký tự sau khi giải mã byte

`java.io.Reader` cung cấp `read()` và `read(char[])`. `InputStreamReader` là cầu nối **byte → ký tự** theo charset được chỉ định. `BufferedReader` thêm `readLine()` và `lines()`; `Files.newBufferedReader(path, charset)` mở reader cho file.

Khi làm việc với log, CSV, JSON, cấu hình hay mã nguồn dưới dạng văn bản, cần quyết định **charset** trước (thường là `StandardCharsets.UTF_8`). Một ký tự Unicode có thể chiếm nhiều byte UTF-8, nên **số byte không bằng số ký tự**. Trong Java, `char` là một đơn vị mã UTF-16; một ký tự Unicode ngoài BMP có thể gồm hai `char`. Không chia byte tùy tiện rồi chuyển từng mảnh độc lập thành `String` vì có thể cắt ngang một chuỗi byte UTF-8.

`Reader` chỉ xử lý ký tự; không tự phân tích JSON/CSV theo đúng quy tắc định dạng. Khi cần parse, dùng parser phù hợp sau lớp đọc.

### `Files` và `Path`: thao tác file ở mức tiện ích

`Path` (`java.nio.file.Path`) biểu diễn đường dẫn; `Files` (`java.nio.file.Files`) có nhiều phương thức tĩnh: `readString`, `readAllBytes`, `writeString`, `write`, `copy`, `move`, `delete`, `createDirectories`, `newInputStream`, `newBufferedReader`, `newByteChannel` và `lines`. Nhờ đó `Files` có thể là API cấp cao **hoặc** điểm mở stream/channel cấp thấp.

Lưu ý phương thức “đọc hết” giữ dữ liệu trong bộ nhớ, còn `newBufferedReader`, `newInputStream` và `lines` thích hợp khi cần đọc tăng dần. Với `Files.lines`, đối tượng `Stream<String>` được liên kết với file đang mở và cần đóng qua `try-with-resources`.

### `Channel`: I/O qua buffer, có khả năng chuyên biệt

`java.nio.channels.Channel` là họ giao diện rộng. `ReadableByteChannel`/`WritableByteChannel` đọc/ghi với `ByteBuffer`; `SeekableByteChannel` hỗ trợ `position` và `size`; `FileChannel` hỗ trợ thao tác file nâng cao; `SocketChannel` có thể dùng chế độ non-blocking.

Với `ByteBuffer`:
1. `put` hoặc channel `read` làm **position** tiến lên.
2. Gọi `flip()` để chuyển từ ghi vào buffer sang đọc dữ liệu vừa nhận.
3. Đọc/ghi dữ liệu ra; nếu tiếp tục nhận thêm dữ liệu, dùng `clear()` hoặc `compact()` tùy còn byte chưa tiêu thụ hay không.

`Channel` không đồng nghĩa với “tự động nhanh hơn”. Với tác vụ file thông thường, `Files` hoặc stream có đệm thường đơn giản và đủ tốt. Một lần `channel.read(buffer)` cũng có thể chỉ trả về một phần dữ liệu; vòng lặp vẫn phải xử lý số byte trả về và EOF.

## 3. Sơ đồ quyết định khi cầm một yêu cầu I/O mới

```text
Yêu cầu liên quan tới file/path?
  ├─ Có: chỉ tạo/copy/move/xóa/kiểm tra → Path + Files
  └─ Có: cần đọc/ghi nội dung
       ├─ Văn bản, nội dung nhỏ → Files.readString / writeString + charset
       ├─ Văn bản, đọc tăng dần → BufferedReader / Files.lines
       ├─ Byte nhỏ → Files.readAllBytes / write
       ├─ Byte lớn/luồng liên tục → Files.newInputStream / newOutputStream
       └─ Truy cập vị trí, map/lock/buffer đặc thù → SeekableByteChannel / FileChannel

Nguồn không phải file (HTTP response, socket, dữ liệu nén, bộ nhớ...)?
  ├─ Chỉ cần byte → InputStream (hoặc channel nếu hệ thống cung cấp)
  ├─ Cần văn bản → InputStreamReader(stream, charset) → BufferedReader
  └─ Cần non-blocking/multiplexing qua selector → SocketChannel + Selector
```

Cây trên là điểm bắt đầu, không phải quy tắc loại trừ. Chẳng hạn, `Files.newInputStream(path)` **trả về** `InputStream`; `Files.newByteChannel(path)` **trả về** `SeekableByteChannel`. `Files` là nơi mở tài nguyên, còn stream/reader/channel là cách **tiêu thụ** dữ liệu.

## 4. Ví dụ Java 17 chạy độc lập: chọn đúng theo cùng một tập file

Chương trình sau tự tạo thư mục tạm, viết file văn bản UTF-8 và file nhị phân, rồi đọc mỗi loại theo yêu cầu. Lệnh và kết quả đầu ra ổn định trên các nền tảng hỗ trợ Java 17.

Tạo file `IoChoiceDemo.java`:

```java
import java.io.BufferedReader;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class IoChoiceDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("io-choice-");
        Path textFile = dir.resolve("notes.txt");
        Path binaryFile = dir.resolve("payload.bin");

        try {
            Files.writeString(textFile, "Xin chào\nJava IO\n",
                    StandardCharsets.UTF_8);
            Files.write(binaryFile, new byte[] {65, 66, 67});

            // Files: đọc toàn bộ file nhỏ thành String.
            String text = Files.readString(textFile, StandardCharsets.UTF_8);
            System.out.println("Files: " + text.split("\\R")[1]);

            // Reader: đọc văn bản theo dòng và charset đã biết.
            try (BufferedReader reader = Files.newBufferedReader(
                    textFile, StandardCharsets.UTF_8)) {
                System.out.println("Reader: " + reader.readLine());
            }

            // InputStream: đọc byte đầu tiên của dữ liệu nhị phân.
            try (InputStream in = Files.newInputStream(binaryFile)) {
                System.out.println("InputStream: " + (char) in.read());
            }

            // Channel: di chuyển tới offset 1 rồi đọc byte tại vị trí đó.
            try (SeekableByteChannel channel = Files.newByteChannel(
                    binaryFile, StandardOpenOption.READ)) {
                channel.position(1);
                ByteBuffer buffer = ByteBuffer.allocate(1);
                int count = channel.read(buffer);
                if (count != 1) {
                    throw new IllegalStateException("Cannot read byte at offset 1");
                }
                buffer.flip();
                System.out.println("Channel: " + (char) buffer.get());
            }
        } finally {
            Files.deleteIfExists(binaryFile);
            Files.deleteIfExists(textFile);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file mã nguồn:

```bash
javac -encoding UTF-8 IoChoiceDemo.java
java IoChoiceDemo
```

Kết quả chuẩn:

```text
Files: Java IO
Reader: Xin chào
InputStream: A
Channel: B
```

**Giải thích:** `Files.readString` trả về một `String` vì file văn bản nhỏ; `BufferedReader` đọc dòng đầu mà không cần giữ cả file; `InputStream.read()` trả về byte 65 (ASCII `A`); channel đặt vị trí tại byte thứ hai, nhận byte 66 (`B`) trong `ByteBuffer` rồi `flip()` trước khi lấy ra. `try-with-resources` đóng mọi reader/stream/channel; `finally` dọn các file tạm đã tạo.

Ví dụ dùng `throws Exception` để giữ sự tập trung vào cách chọn API. Trong ứng dụng thực tế, xử lý `IOException` theo ngữ cảnh, kèm tên đường dẫn và hành động đang thực hiện.

## 5. Ba mẫu thường dùng khi dữ liệu tăng lớn

### 5.1 Sao chép file: ưu tiên API trực tiếp

Nếu đầu vào và đầu ra đều là `Path`, không cần tự tạo vòng lặp:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path source = Path.of("data", "source.bin");
Path target = Path.of("data", "backup.bin");
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

Đây là **đoạn mã minh họa** đặt trong phương thức có xử lý/khai báo `IOException`; file nguồn và thư mục đích phải tồn tại. `REPLACE_EXISTING` cho phép thay file đích đang có. Nếu không muốn thay, bỏ tùy chọn này và xử lý `FileAlreadyExistsException`. API không bảo đảm mọi hệ file đều có cùng hành vi đối với metadata hay symbolic link; xem tùy chọn `CopyOption` khi cần.

### 5.2 Vận chuyển byte từ nguồn bất kỳ

Khi nguồn là `InputStream` (ví dụ response body, ZIP entry, socket), đọc dữ liệu byte và chuyển sang `OutputStream`:

```java
import java.io.InputStream;
import java.io.OutputStream;

// Đoạn mã minh họa nằm trong phương thức throws IOException.
// sourceStream là InputStream đã được mở bởi phía gọi.
try (InputStream in = sourceStream;
     OutputStream out = Files.newOutputStream(Path.of("download.bin"))) {
    in.transferTo(out);
}
```

Cần import thêm `java.nio.file.Files` và `java.nio.file.Path` nếu đưa đoạn này vào chương trình riêng. `transferTo` (Java 9+) chuyển tất cả byte tới EOF; không giải mã charset. Khi stream được sở hữu bởi thư viện/framework, kiểm tra **ai chịu trách nhiệm đóng** trước khi đặt nó trong `try-with-resources`. Với dữ liệu không tin cậy hoặc upload lớn, thêm giới hạn dung lượng, timeout và quy tắc hủy theo ngữ cảnh.

### 5.3 Xử lý file văn bản lớn theo dòng

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedReader reader = Files.newBufferedReader(
        Path.of("events.log"), StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        if (line.contains("ERROR")) {
            System.out.println(line);
        }
    }
}
```

Đoạn mã minh họa nằm trong phương thức khai báo/xử lý `IOException`. Nó xử lý từng dòng thay vì gọi `Files.readAllLines`. `readLine` **không trả lại** ký tự phân cách dòng; nếu cần bảo tồn byte gốc, loại newline hoặc charset gốc, phải chọn chiến lược khác. Dòng riêng lẻ quá lớn vẫn có thể tiêu tốn nhiều bộ nhớ.

Có thể dùng:

```java
try (var lines = Files.lines(Path.of("events.log"),
        StandardCharsets.UTF_8)) {
    long errors = lines.filter(line -> line.contains("ERROR")).count();
    System.out.println(errors);
}
```

Đoạn thứ hai cũng cần import `Files`, `Path`, `StandardCharsets` và khai báo/xử lý `IOException`; đối tượng `Stream` phải được đóng. `Files.lines` là lazy, nhưng thao tác terminal (`count`, `forEach`, v.v.) mới kích hoạt đọc. Lỗi I/O trong lúc tiêu thụ stream có thể được bọc thành `UncheckedIOException`.

## 6. Nếu phải dùng Channel: hai tình huống thật sự có lợi

**Truy cập ngẫu nhiên trong file:** ví dụ đọc header tại offset 0, sau đó đọc một record tại offset N. `SeekableByteChannel.position(N)` phù hợp vì một `InputStream` tổng quát không có thao tác đặt vị trí bất kỳ. `FileChannel` bổ sung API như `read(ByteBuffer, position)` và `write(ByteBuffer, position)`.

**I/O mạng non-blocking:** `SocketChannel.configureBlocking(false)` kết hợp `Selector` cho phép quản lý nhiều kết nối. Cơ chế đó đòi hỏi vòng đời kết nối, quản lý partial read/write và xử lý trạng thái sẵn sàng. Không áp dụng sơ đồ selector cho một tác vụ đọc file văn bản đơn giản.

Ví dụ minh họa đọc theo khối bằng channel (đặt trong phương thức `throws IOException`):

```java
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

try (FileChannel channel = FileChannel.open(
        Path.of("large.bin"), StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(8192);
    long total = 0;

    while (true) {
        int n = channel.read(buffer);
        if (n == -1) break;
        if (n == 0) continue;
        total += n;

        buffer.flip();
        // Tiêu thụ các byte trong [position, limit) ở đây.
        buffer.position(buffer.limit());
        buffer.clear();
    }
    System.out.println("Total bytes: " + total);
}
```

`channel.read` có thể trả `0` ngay cả khi chưa EOF, nên phải xử lý giá trị đó. `flip` làm vùng byte vừa nhận sẵn sàng cho đọc; `clear` sau khi **đã tiêu thụ hết** vùng này. Trong ứng dụng thực tế, thay dòng `buffer.position(buffer.limit())` bằng xử lý dữ liệu và dùng `compact` nếu còn byte chưa xử lý. Không suy diễn rằng `FileChannel.transferTo` luôn thực hiện zero-copy: tối ưu hóa phụ thuộc môi trường và kênh đích.

## 7. Bộ nhớ, charset, tài nguyên và các lỗi chọn API hay gặp

| Sai lầm | Hậu quả | Cách chọn/điều chỉnh |
| --- | --- | --- |
| Dùng `Reader` để đọc ảnh, ZIP, PDF | Giải mã byte làm thay đổi dữ liệu | Dùng `InputStream`, `Files.readAllBytes` nếu nhỏ, hoặc channel khi cần |
| Dùng `InputStream` rồi ép từng byte sang `char` để đọc tiếng Việt | UTF-8 nhiều byte nên văn bản lỗi | Dùng `InputStreamReader(in, UTF_8)`/`Files.newBufferedReader` |
| Gọi `readString`/`readAllBytes` cho file không giới hạn | Nguy cơ dùng nhiều heap hoặc `OutOfMemoryError` | Đọc từng dòng hoặc từng khối với buffer |
| Dựa vào charset mặc định không chủ đích | Có thể đọc khác nhau giữa hệ thống hoặc nguồn dữ liệu | Truyền `StandardCharsets.UTF_8` hoặc charset thật của nguồn |
| Nghĩ `read(buffer)` luôn trả đủ `buffer.length` | Mất dữ liệu khi xử lý sai partial read | Lặp tới đủ số byte cần hoặc tới `-1` |
| Quên `flip()` trước khi lấy byte từ buffer vừa ghi | Position/limit sai, đọc sai vùng | `flip` khi chuyển pha ghi → đọc; `clear`/`compact` cho vòng tiếp theo |
| Không đóng `Files.lines`/reader/stream/channel | Rò file descriptor, khóa tài nguyên | `try-with-resources` |
| Dùng channel chỉ để đọc chuỗi nhỏ | Mã phức tạp, tự xử lý buffer/charset | `Files.readString(path, charset)` |
| Kiểm tra `Files.exists` rồi tin file vẫn tồn tại | File có thể thay đổi giữa kiểm tra và thao tác | Thực hiện thao tác và xử lý exception |
| Đo hiệu năng chỉ qua tên API | Quyết định sai vì cache, bộ đệm, kích thước và thiết bị | Benchmark theo tải thực tế; dùng API đơn giản trước |

**Giới hạn bộ nhớ:** `readAllBytes`/`readString`/`readAllLines` giữ toàn bộ dữ liệu hoặc cấu trúc kết quả trong RAM. `BufferedReader` và `InputStream` với buffer cố định thường giữ mức dùng RAM ổn định hơn; tuy nhiên một dòng đơn lẻ rất dài hoặc logic tự gom kết quả vẫn có thể gây phình bộ nhớ.

**Charset và lỗi giải mã:** UTF-8 là lựa chọn phổ biến, nhưng file thực tế có thể dùng charset khác hoặc có BOM. Xác nhận format trước khi đọc; không suy diễn mọi dãy byte đều là UTF-8 hợp lệ. Nếu cần chính sách nghiêm ngặt khi gặp byte lỗi, dùng `CharsetDecoder` cấu hình `CodingErrorAction.REPORT`, thay vì âm thầm chấp nhận ký tự thay thế.

**Tài nguyên:** `Files.readString`, `Files.readAllBytes`, `Files.copy(Path, Path, ...)` tự quản lý thao tác mở/đóng nội bộ. API trả về tài nguyên đang mở như `Files.newInputStream`, `Files.newBufferedReader`, `Files.lines` hay `FileChannel.open` thì phía gọi phải đóng. Với pipeline vừa đọc vừa ghi, xác định rõ quyền sở hữu stream; `flush` không thay thế `close`.

**Đường dẫn và quyền:** `NoSuchFileException`, `AccessDeniedException`, `FileAlreadyExistsException` và `IOException` cung cấp thông tin thất bại hữu ích. Không tự kết luận nguyên nhân từ `Files.exists`; quyền truy cập, liên kết tượng trưng và thay đổi đồng thời có thể ảnh hưởng kết quả. Nếu thao tác phải an toàn về ghi đè hay thay thế file, xác định rõ `OpenOption`/`CopyOption` và yêu cầu tính nguyên tử.

## 8. Checklist áp dụng trước khi viết code

1. **Nguồn/đích** là file (`Path`), bộ nhớ, HTTP body, socket hay luồng do thư viện cấp?
2. **Ý nghĩa dữ liệu** là byte nguyên trạng hay ký tự cần giải mã? Nếu là văn bản, charset nào?
3. **Dung lượng** có giới hạn chắc chắn không? Nếu không, xử lý theo dòng/khối và giới hạn đầu vào.
4. **Mẫu truy cập** là đọc từ đầu tới cuối, đọc từng dòng, hay cần seek/lock/mapping/non-blocking?
5. **Quyền sở hữu tài nguyên** thuộc ai; cần đóng gì; ghi đè/tạo mới/append theo tùy chọn nào?
6. **Xử lý lỗi** nên báo lại, retry, ghi log hay hủy? Có cần kiểm tra integrity của dữ liệu không?

Nếu một tác vụ chỉ cần “đọc file cấu hình UTF-8 vài KB”, lựa chọn dễ hiểu thường là `Files.readString`. Nếu cần “lọc 30 GB log theo dòng”, dùng `BufferedReader` hoặc `Files.lines` với vòng đời rõ ràng. Nếu cần “stream một file ZIP từ HTTP xuống đĩa”, dùng byte stream. Nếu cần “cập nhật trường nhị phân tại offset cụ thể”, chọn `SeekableByteChannel`/`FileChannel`. Đó là cách chọn dựa trên **hình dạng bài toán** thay vì tên API.