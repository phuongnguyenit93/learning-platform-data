# Bảng API truyền thống, NIO, NIO.2 và các mốc phiên bản Java

Java có nhiều lớp I/O cùng tồn tại vì nền tảng được mở rộng qua các phiên bản JDK. **`java.io` truyền thống**, **NIO (Java 1.4)** và **NIO.2 (Java 7)** là các nhóm API có điểm mạnh khác nhau; NIO.2 bổ sung hệ thống tệp hiện đại và một số API bất đồng bộ, **không thay thế toàn bộ `java.io` hoặc NIO**. Bảng tra cứu này giúp tìm đúng lớp, hiểu mốc phiên bản và chọn API phù hợp cho chương trình Java 17+.

## 1. Bản đồ ba thế hệ API

| Nhóm | Xuất hiện | Gói/lớp tiêu biểu | Mô hình chính | Bài toán phù hợp |
|---|---|---|---|---|
| I/O truyền thống | Java 1.0; bổ sung Reader/Writer ở Java 1.1 | `java.io.InputStream`, `OutputStream`, `Reader`, `Writer`, `File`, `RandomAccessFile` | Luồng byte hoặc ký tự, xử lý tuần tự; các lệnh đọc/ghi thông thường có thể chặn | Đọc/ghi stream, protocol đơn giản, bộ lọc/đệm, API tương thích lâu đời |
| NIO (New I/O) | Java 1.4 | `java.nio.Buffer`/`ByteBuffer`, `java.nio.channels.FileChannel`/`SocketChannel`/`Selector`, `java.nio.charset.Charset` | Buffer, channel, charset; hỗ trợ multiplexing và non-blocking cho **một số** channel | Dữ liệu nhị phân, I/O dùng buffer, nhiều kết nối mạng với selector, thao tác channel |
| NIO.2 (thường gọi NIO.2/JSR 203) | Java 7 | `java.nio.file.Path`, `Files`, `FileSystem`, `WatchService`, `FileVisitor`; `java.nio.channels.AsynchronousFileChannel` | Hệ thống tệp giàu chức năng, thuộc tính tệp, duyệt cây, giám sát thay đổi, I/O bất đồng bộ | Quản lý file/directory, copy/move/delete, metadata, symbolic link, watch directory, async channel |

**Phân biệt tên:** NIO nghĩa là *New I/O*, không phải lời hứa mọi thao tác đều *non-blocking*. `FileChannel` có các thao tác đọc/ghi thường mang tính blocking; `SocketChannel` có thể cấu hình blocking hoặc non-blocking. `Selector` chỉ dùng với `SelectableChannel` phù hợp (ví dụ `SocketChannel`), không đăng ký `FileChannel` để theo dõi file thường.

**Hai thứ cùng có thể đúng:** `Files.newInputStream(path)` thuộc tiện ích NIO.2 nhưng trả về kiểu `java.io.InputStream`; một ứng dụng có thể kết hợp `Path`, `Files`, stream và channel trong cùng luồng xử lý. Cách phân loại theo *API được bổ sung ở mốc nào*, không phải các công nghệ loại trừ lẫn nhau.

## 2. Dòng thời gian các mốc quan trọng

| Mốc Java | API/đặc điểm tiêu biểu | Ý nghĩa đối với mã nguồn |
|---|---|---|
| **JDK 1.0 (1996)** | `InputStream`, `OutputStream`, `File`, `FileInputStream`, `FileOutputStream`, `RandomAccessFile` | Nền tảng byte stream và đường dẫn file truyền thống |
| **JDK 1.1 (1997)** | Họ `Reader`/`Writer`, `InputStreamReader`, `OutputStreamWriter` | Tầng chuyển đổi byte ↔ ký tự theo character encoding |
| **JDK 1.4 (2002)** | `ByteBuffer`/`CharBuffer`, `Channel`, `FileChannel`, `SocketChannel`, `Selector`, `Charset` | NIO 1: buffer/channel, mã hóa ký tự, multiplexing socket |
| **Java 7 (2011)** | `Path`, `Paths`, `Files`, `FileSystem`, `WatchService`, `FileVisitor`, `StandardOpenOption`; `AsynchronousFileChannel`/`AsynchronousSocketChannel` | NIO.2: API hệ thống tệp mới, tệp bất đồng bộ và quan sát thư mục |
| **Java 8 (2014)** | `Files.list`, `Files.walk`, `Files.find`, `Files.lines` | Tích hợp `Stream` để liệt kê/tìm/đọc dòng theo nhu cầu; stream giữ tài nguyên cần đóng |
| **Java 9 (2017)** | `InputStream.readAllBytes`, `readNBytes`, `transferTo` | Thêm tiện ích cho stream truyền thống; **khác** `Files.readAllBytes` vốn có từ Java 7 |
| **Java 11 (2018)** | `Path.of`; `Files.readString`, `Files.writeString` | Thuận tiện khi đọc/ghi tệp văn bản UTF-8; `Paths.get` vẫn là lựa chọn tương thích Java 7 |
| **Java 12 (2019)** | `Files.mismatch` | Trả chỉ số byte khác đầu tiên giữa hai file, hoặc `-1` nếu không có khác biệt |
| **Java 21 (2023)** | Virtual threads chuẩn hóa (JEP 444), dùng được với nhiều cách viết I/O blocking | Cải thiện mô hình lập trình đồng thời; **không tạo ra một thế hệ API “NIO.3”** |

Ngày/phiên bản ở bảng chỉ ra **lần đầu API xuất hiện**, không phải ngày một lớp cũ ngừng hoạt động. Trong Java 17/21, `java.io`, NIO và NIO.2 vẫn được hỗ trợ. Hãy kiểm tra chính xác **phương thức** chứ không chỉ **tên lớp**: `InputStream` có từ Java 1.0 nhưng `InputStream.transferTo` phải tới Java 9; `Path` có từ Java 7 nhưng `Path.of` chỉ có từ Java 11.

## 3. Bảng tra cứu lớp/phương thức theo nhu cầu

| Nhu cầu | `java.io` truyền thống | NIO (Java 1.4) | NIO.2 (Java 7+) và bổ sung sau đó |
|---|---|---|---|
| Biểu diễn một đường dẫn | `File` | — | `Path`/`Paths.get` (7), `Path.of` (11) |
| Tạo thư mục, kiểm tra, lấy kích thước | `File.mkdir`/`mkdirs`, `exists`, `length` | — | `Files.createDirectory`/`createDirectories`, `exists`, `size` |
| Mở luồng byte từ file | `FileInputStream`/`FileOutputStream`, đệm bằng `BufferedInputStream`/`BufferedOutputStream` | `FileChannel`, `ByteBuffer` | `Files.newInputStream`/`newOutputStream`, `Files.newByteChannel` |
| Đọc/ghi ký tự có charset | `InputStreamReader`/`OutputStreamWriter`, `BufferedReader`/`BufferedWriter` | `Charset`, `CharsetDecoder`/`CharsetEncoder` | `Files.newBufferedReader`/`newBufferedWriter` (7); `readString`/`writeString` (11) |
| Đọc toàn bộ file nhỏ | `FileInputStream` và vòng lặp đọc | Channel và buffer | `Files.readAllBytes` (7); `Files.readString` (11) |
| Đọc các dòng file lớn | `BufferedReader.readLine` | `FileChannel` + decoder tự quản lý | `Files.lines` (8) tạo stream dòng; phải đóng stream |
| Đọc/ghi dữ liệu tại vị trí bất kỳ | `RandomAccessFile.seek` | `FileChannel.position`, `read/write(ByteBuffer, position)`, `map` | `Files.newByteChannel` → `SeekableByteChannel` |
| Sao chép/di chuyển/đổi tên file | Sao chép bằng stream; `File.renameTo` có hành vi phụ thuộc nền tảng | `FileChannel.transferTo`/`transferFrom` | `Files.copy`, `Files.move`, các `CopyOption` |
| Xóa file và biết nguyên nhân lỗi | `File.delete` trả `boolean` | — | `Files.delete` ném lỗi cụ thể; `deleteIfExists` |
| Liệt kê hoặc duyệt thư mục | `File.listFiles` | — | `DirectoryStream`, `Files.walkFileTree` (7); `Files.list/walk/find` (8) |
| Đọc metadata/permission/symbolic link | `File.lastModified`, `canRead` ... giới hạn | — | `Files.readAttributes`, `BasicFileAttributes`, `PosixFileAttributes`, `FileOwnerAttributeView`, `Files.readSymbolicLink` |
| Phát hiện file xuất hiện/thay đổi | Tự polling `File` | — | `WatchService` và `WatchKey` (7) |
| Mạng socket truyền thống | `java.net.Socket`/`ServerSocket` + stream | `SocketChannel`, `ServerSocketChannel`, `Selector` | `AsynchronousSocketChannel`/`AsynchronousServerSocketChannel` (7) |
| File I/O bất đồng bộ | Không có API tương ứng trực tiếp trong họ stream cổ điển | `FileChannel` thường đọc/ghi đồng bộ | `AsynchronousFileChannel` (7), `Future` hoặc `CompletionHandler` |

**Không suy ra hiệu năng chỉ từ tên API.** `Files.copy` có thể tiện và ít lỗi; `FileChannel.transferTo` có thể cho phép tối ưu ở hệ điều hành nhưng không đảm bảo zero-copy mọi nền tảng; `ByteBuffer.allocateDirect` có chi phí cấp phát và quản lý riêng. Đo theo tải thực tế, kích thước dữ liệu và hệ thống tệp.

## 4. Mốc phiên bản theo đúng phương thức: tránh nhầm khi build

| Câu lệnh/tính năng | Java tối thiểu | Ghi chú |
|---|---:|---|
| `new File("a.txt")`, `new FileInputStream(...)` | 1.0 | `File` chỉ đại diện đường dẫn; không tự mở stream |
| `new InputStreamReader(in, charset)` | 1.1 (họ Reader/Writer) | Luôn nên chỉ định charset thay vì mặc định nền tảng |
| `ByteBuffer.allocate(1024)`, `FileInputStream.getChannel()` | 1.4 | `FileChannel`/`ByteBuffer` thuộc NIO 1 |
| `Paths.get("a.txt")`, `Files.readAllBytes(path)` | 7 | Thuộc NIO.2; toàn bộ bytes có thể tốn nhiều RAM |
| `Files.copy(source, target, ...)`, `Files.walkFileTree(root, visitor)` | 7 | Hoạt động theo `Path`; có các tùy chọn và ngoại lệ riêng |
| `FileChannel.open(path, options...)` | 7 | Lớp `FileChannel` cũ hơn phương thức tiện ích `open` này |
| `Files.lines(path)`, `Files.walk(root)` | 8 | Stream thường gắn với tài nguyên I/O, cần `try-with-resources` |
| `in.transferTo(out)`, `in.readAllBytes()` trên `InputStream` | 9 | Không nhầm `InputStream.transferTo` (9) với `FileChannel.transferTo` (1.4) |
| `Path.of("a.txt")`, `Files.readString(path)`, `Files.writeString(path, text)` | 11 | Mặc định UTF-8 nếu dùng overload không truyền charset |
| `Files.mismatch(path1, path2)` | 12 | Kết quả là chỉ số byte đầu tiên khác, không phải boolean |
| Virtual threads cho tác vụ I/O | 21 | Tính năng concurrency; không đổi lịch sử xuất hiện của NIO.2 |

Khi xây ứng dụng cho nhiều JDK, nên dùng `javac --release 8` (hoặc cấu hình build tương đương) để compiler kiểm tra cả ngôn ngữ lẫn API có trong Java 8; chỉ đặt `-source`/`-target` bằng 8 trên JDK mới không cung cấp cùng mức kiểm tra API. Ví dụ `Files.readString` không biên dịch được với `--release 8` vì cần Java 11.

## 5. Quan hệ giữa stream, channel, buffer, file system

~~~text
java.io
  InputStream / OutputStream        Reader / Writer
           │                              │
           └────────── dữ liệu ──────────┘
                         │
java.nio                 │
  ByteBuffer ←→ Channel  │   Charset: giải mã/mã hóa byte ↔ ký tự
  SelectableChannel → Selector (khi dùng socket phù hợp)
                         │
java.nio.file (NIO.2)
  Path → Files (copy, move, attributes, tree, stream factories)
             │
             ├── Files.newInputStream(...) → java.io.InputStream
             ├── Files.newByteChannel(...) → SeekableByteChannel
             ├── Files.newBufferedReader(...) → java.io.BufferedReader
             └── FileSystem / WatchService / FileVisitor
~~~

- **Stream** mô tả dòng dữ liệu tuần tự. `InputStream`/`OutputStream` xử lý **byte**; `Reader`/`Writer` xử lý **char** (ký tự UTF-16 ở mức Java). Chuyển giữa byte và text cần charset; `BufferedReader` là bộ đệm ở tầng ký tự, không thay cho decoder.
- **Channel + Buffer** mô tả trao đổi qua một vùng bộ nhớ có `position`, `limit`, `capacity`. Sau khi ghi vào buffer để đọc lại, thường `flip()`; sau khi tiêu thụ, dùng `clear()` hoặc `compact()` tùy có cần giữ bytes chưa xử lý.
- **Path + Files** mô tả đối tượng trong hệ thống tệp và thao tác với nó. `Path` có thể chỉ tới tệp chưa tồn tại; `Files` thực hiện các hành động có thể ném `IOException`.
- **Bridge**: `File.toPath()` và `Path.toFile()` hỗ trợ chuyển giữa mã truyền thống và NIO.2 với file system mặc định. `Path.toFile()` không nhất thiết khả dụng cho các provider tùy biến (chẳng hạn hệ thống tệp ZIP).
- **Blocking / non-blocking / asynchronous** là tính chất của **cơ chế thao tác cụ thể**. Không thể kết luận chỉ từ package: NIO chứa `FileChannel` thường blocking; NIO.2 chứa `Files.readAllBytes` đồng bộ; channel mạng có thể non-blocking; asynchronous channel dùng kết quả tương lai hoặc callback.

## 6. Ví dụ Java 17+: một file, bốn cách truy cập theo mốc API

Chương trình này tạo tệp tạm và viết dữ liệu bằng `FileOutputStream`, sau đó đọc bằng (1) stream truyền thống, (2) `FileChannel` + `ByteBuffer` của NIO 1, (3) `Files.readAllBytes` của NIO.2 Java 7 và (4) `Files.readString` Java 11. Tệp và thư mục tạm được xóa trong `finally`.

Lưu file thành **`IoApiTimelineDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class IoApiTimelineDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("io-api-demo-");
        Path file = dir.resolve("example.txt");
        try {
            try (OutputStream out = new FileOutputStream(file.toFile())) {
                out.write("Hello IO!\n".getBytes(StandardCharsets.UTF_8));
            }

            ByteArrayOutputStream legacy = new ByteArrayOutputStream();
            try (InputStream in = new FileInputStream(file.toFile())) {
                byte[] bytes = new byte[4];
                int count;
                while ((count = in.read(bytes)) != -1) {
                    legacy.write(bytes, 0, count);
                }
            }
            System.out.println("java.io: "
                    + new String(legacy.toByteArray(), StandardCharsets.UTF_8).trim());

            ByteArrayOutputStream nio = new ByteArrayOutputStream();
            try (FileInputStream in = new FileInputStream(file.toFile());
                 FileChannel channel = in.getChannel()) {
                ByteBuffer buffer = ByteBuffer.allocate(4);
                while (channel.read(buffer) != -1) {
                    buffer.flip();
                    while (buffer.hasRemaining()) {
                        nio.write(buffer.get());
                    }
                    buffer.clear();
                }
            }
            System.out.println("NIO 1.4: "
                    + new String(nio.toByteArray(), StandardCharsets.UTF_8).trim());

            System.out.println("NIO.2/JDK 7: "
                    + new String(Files.readAllBytes(file), StandardCharsets.UTF_8).trim());
            System.out.println("Java 11+: "
                    + Files.readString(file, StandardCharsets.UTF_8).trim());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac IoApiTimelineDemo.java
java IoApiTimelineDemo
~~~

Stdout:

~~~text
java.io: Hello IO!
NIO 1.4: Hello IO!
NIO.2/JDK 7: Hello IO!
Java 11+: Hello IO!
~~~

Cùng một dữ liệu được đọc qua các API thuộc các mốc khác nhau. Chương trình **chạy trên Java 17+**: bản thân file nguồn không có nghĩa nó chạy nguyên vẹn trên Java 7, vì phương thức `Files.readString` ở ví dụ cuối đòi Java 11. Phần demo NIO tự dùng buffer bốn byte để thấy cách xử lý nhiều lần `read`; không cần buffer khi chỉ muốn đọc văn bản nhỏ bằng `Files.readString`.

## 7. Chọn API nào trong từng tình huống?

| Tình huống | Ưu tiên | Lý do/quy tắc triển khai |
|---|---|---|
| Đọc một file cấu hình nhỏ dạng UTF-8 trên Java 11+ | `Files.readString(path, UTF_8)` | Ngắn, rõ charset; chỉ dùng khi kích thước đủ nhỏ để nạp vào bộ nhớ |
| Ghi một file văn bản nhỏ trên Java 11+ | `Files.writeString(path, text, UTF_8)` | Dễ dùng; kiểm tra `OpenOption` nếu muốn append hoặc tránh ghi đè |
| Xử lý file văn bản lớn theo dòng | `Files.newBufferedReader` hoặc `Files.lines` | Đọc tuần tự; đóng reader/stream bằng `try-with-resources` |
| Sao chép, di chuyển, tạo thư mục | `Files.copy`, `Files.move`, `Files.createDirectories` | Lỗi có ngoại lệ cụ thể; xem xét replace, atomicity, symlink |
| Quét cây thư mục lớn/điều khiển lỗi từng nhánh | `Files.walkFileTree` + `FileVisitor` | Chủ động xử lý lỗi, rẽ nhánh và thời điểm thăm file |
| Theo dõi thay đổi trong thư mục | `WatchService` | Nhận sự kiện, xử lý `OVERFLOW` và đăng ký lại khi cần; không coi là log tuyệt đối chính xác |
| Đọc file ở vị trí xác định hoặc map file | `FileChannel` / `SeekableByteChannel` | Có thao tác position và truy cập byte phù hợp |
| Nhiều kết nối socket trên ít thread | `SocketChannel` + `Selector` | Cần cấu hình non-blocking và tự quản lý tình trạng đọc/ghi chưa xong |
| Muốn dùng callbacks cho I/O bất đồng bộ | `AsynchronousFileChannel` / `AsynchronousSocketChannel` | Tận dụng `Future`/`CompletionHandler`; kiểm tra hỗ trợ nền tảng |
| Ứng dụng phụ thuộc thư viện cũ nhận `InputStream`/`Reader` | Giữ `java.io` interface; tạo từ `Files` nếu thuận tiện | Không cần đổi chữ ký API chỉ để “chuyển sang NIO.2” |

**Bộ quy tắc lựa chọn:** dùng `Path`/`Files` cho phần lớn tác vụ *hệ thống tệp* mới; dùng `InputStream`/`OutputStream` hoặc `Reader`/`Writer` khi cần *luồng*; dùng channel và buffer khi cần vị trí byte hoặc đặc tính mạng/I/O cụ thể. “Mới hơn” không đồng nghĩa “nhanh hơn”, và việc nâng JDK không buộc xóa code `java.io` hợp lệ.

## 8. Các bẫy tương thích và hành vi thường gặp

1. **Đường dẫn khác với nội dung:** `new File(path)` và `Path.of(path)` không tạo tệp thật. `Files.exists(path)` còn có thể trả `false` khi không xác định được trạng thái tồn tại; đừng mặc định `false` luôn nghĩa là chắc chắn không có file. Các thao tác mở/đọc vẫn phải xử lý `IOException`.

2. **Charset:** `FileInputStream` chỉ tạo byte stream, không tự “đọc UTF-8”. Khi biến bytes thành text, nêu rõ `StandardCharsets.UTF_8`. NIO `Charset` là bộ mã hóa/giải mã; mặc định charset có thể khác giữa JDK/cấu hình chạy. `Files.readString`/`writeString` không truyền charset sử dụng UTF-8.

3. **Tài nguyên:** đóng stream, reader, channel, `DirectoryStream` và stream do `Files.list`/`walk`/`lines` trả về. `Files.readAllBytes`/`readString` tự đóng tệp sau thao tác; đổi lại toàn bộ dữ liệu được nạp vào bộ nhớ.

4. **Tùy chọn copy/move:** `Files.copy`, `Files.move` có quy tắc mặc định và `CopyOption`; `REPLACE_EXISTING` là yêu cầu cho hành vi thay thế. `ATOMIC_MOVE` chỉ là yêu cầu di chuyển nguyên tử và có thể thất bại với `AtomicMoveNotSupportedException`, nhất là khi khác file system. Đừng khẳng định các bước copy/move hoàn toàn transaction-safe.

5. **Symbolic link và thuộc tính tệp:** nhiều thao tác `Files` đi theo liên kết tượng trưng theo mặc định, nhưng một số API hoặc option có quy tắc khác. Dùng `LinkOption.NOFOLLOW_LINKS` khi API hỗ trợ và ngữ nghĩa yêu cầu. Quyền truy cập POSIX/ACL phụ thuộc provider/hệ điều hành; không áp quy tắc POSIX cho mọi ổ đĩa Windows.

6. **WatchService:** sự kiện có thể gộp, mất do overflow hoặc xảy ra khi writer vẫn đang cập nhật. Thường phải kiểm tra lại trạng thái thư mục khi nhận `OVERFLOW`. Không kỳ vọng WatchService tự đệ quy xuống mọi thư mục con.

7. **Non-blocking không phải asynchronous:** `SocketChannel.configureBlocking(false)` yêu cầu ứng dụng tự xử lý partial read/write và `Selector`; `AsynchronousSocketChannel` đưa kết quả qua `Future`/`CompletionHandler`. Kết quả bất đồng bộ không mặc nhiên chứng minh một lời gọi kernel non-blocking trên mọi hệ điều hành.

8. **Không lấy kích thước file để gọi `read` đúng một lần:** cả stream và channel có thể trả ít byte hơn số yêu cầu. Khi cần đủ byte, lặp có kiểm tra số byte đọc/EOF. Ghi qua channel cũng có thể chỉ tiêu thụ một phần buffer. Nếu xử lý mạng phân mảnh, dùng `compact()` để giữ byte chưa giải mã.

9. **`File` và `Path` không có quan hệ kế thừa:** chuyển qua `file.toPath()` hoặc `path.toFile()` (với default file-system provider). Các provider khác như ZIP file system có thể không hỗ trợ `toFile()`.

10. **Khi cần build cho JDK cũ:** phân biệt API tồn tại trên **JDK biên dịch** và API tồn tại trên **JDK chạy**; xác minh mốc *phương thức*, không chỉ mốc package. Không gọi `InputStream.readAllBytes` khi target Java 8, dù chính `InputStream` đã tồn tại lâu.

## 9. Tóm tắt để tra cứu nhanh

| Nếu nhìn thấy mã… | Nhận diện đúng |
|---|---|
| `new FileInputStream(file)`, `BufferedReader`, `OutputStream` | Truyền thống `java.io`; vẫn dùng tốt trong JDK mới |
| `ByteBuffer.flip()`, `FileChannel`, `Selector` | NIO từ Java 1.4; buffer/channel, chỉ một số channel non-blocking |
| `Path`, `Files.copy`, `Files.walkFileTree`, `WatchService` | NIO.2 từ Java 7; hệ thống tệp và API bổ sung |
| `Files.lines`, `Files.walk` | API convenience dựa trên Stream được thêm ở Java 8 |
| `InputStream.transferTo` | Tiện ích `java.io` bổ sung ở Java 9 |
| `Files.readString`, `Path.of` | Tiện ích `java.nio.file` bổ sung ở Java 11 |
| `Files.mismatch` | Bổ sung ở Java 12 |

**Nguyên tắc mấu chốt:** tra **lớp + phương thức + phiên bản tối thiểu**; chọn theo bài toán (stream, buffer/channel, hay filesystem). Java 7 là mốc NIO.2, nhưng các API trong `java.nio.file` tiếp tục được bổ sung ở Java 8/11/12.

### Tài liệu API chính thức

- [`java.io` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/package-summary.html)
- [`java.nio` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/package-summary.html)
- [`java.nio.channels` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html)
- [`java.nio.file` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/package-summary.html)
- [`java.nio.file` — Java SE 7](https://docs.oracle.com/javase/7/docs/api/java/nio/file/package-summary.html)
