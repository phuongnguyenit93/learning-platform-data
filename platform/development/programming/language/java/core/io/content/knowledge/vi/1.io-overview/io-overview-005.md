# Bản đồ `java.io`, `java.nio` và NIO.2

## Mục tiêu bài học

Sau bài này, bạn có thể chọn đúng API cho đọc/ghi tệp, xử lý văn bản, dữ liệu nhị phân, kết nối mạng và theo dõi hệ thống tệp; hiểu vai trò của **stream**, **reader/writer**, **buffer**, **channel**, **selector**, **`Path`** và **`Files`**; phân biệt I/O chặn, không chặn và bất đồng bộ.

Ba tên gọi thường đi cùng nhau nhưng không phải ba hệ thống loại trừ nhau:

- **`java.io`**: API stream/reader/writer truyền thống, thiên về xử lý dữ liệu tuần tự.
- **`java.nio`** (cùng `java.nio.channels`, `java.nio.charset`): buffer, channel, selector và chuyển đổi charset.
- **NIO.2**, xuất hiện từ Java 7: tên gọi các mở rộng I/O, nổi bật nhất là `java.nio.file` với `Path`, `Files`, `FileSystem`, file attributes và `WatchService`, cùng các channel bất đồng bộ. Không có gói chuẩn `java.nio2`.

## 1. Bản đồ hệ sinh thái

```text
Bài toán I/O
├── Đọc/ghi byte tuần tự
│   ├── java.io.InputStream / OutputStream
│   └── java.nio.file.Files.newInputStream / newOutputStream
├── Đọc/ghi văn bản
│   ├── java.io.Reader / Writer, BufferedReader / BufferedWriter
│   ├── java.nio.charset.Charset / CharsetDecoder / CharsetEncoder
│   └── java.nio.file.Files.newBufferedReader / newBufferedWriter
├── Đường dẫn, tệp, thư mục, metadata
│   ├── java.io.File (đời trước)
│   └── java.nio.file.Path / Files / FileSystem / FileStore / attributes
├── Truy cập byte có buffer, vị trí, mapping
│   └── java.nio.ByteBuffer + java.nio.channels.FileChannel
├── Kết nối mạng
│   ├── java.net.Socket + InputStream / OutputStream
│   └── java.nio.channels.SocketChannel / ServerSocketChannel /
│       DatagramChannel + ByteBuffer
├── Quản lý nhiều socket theo sự kiện
│   └── SelectableChannel + Selector
└── Đọc/ghi tệp với kết quả bất đồng bộ
    └── java.nio.channels.AsynchronousFileChannel
```

Có ba câu hỏi độc lập:

1. **Dữ liệu là byte hay văn bản?** Stream xử lý byte; Reader/Writer xử lý ký tự và dùng charset để liên hệ với byte. `ByteBuffer` giữ byte trong bộ nhớ.
2. **Nguồn/đích là gì?** Hệ thống tệp dùng `Path`/`Files`; socket có kênh riêng; một API không thay thế mọi loại nguồn dữ liệu.
3. **Mô hình thực thi nào?** Chặn, không chặn hay completion bất đồng bộ? Tên NIO không bảo đảm mọi thao tác đều non-blocking.

## 2. `java.io`: stream, reader/writer và các lớp bao

### Byte stream

`InputStream` đọc byte, `OutputStream` ghi byte. Các API tiêu biểu:

| API | Công dụng |
|---|---|
| `FileInputStream` / `FileOutputStream` | Byte I/O từ tệp |
| `BufferedInputStream` / `BufferedOutputStream` | Giảm số thao tác I/O nhỏ |
| `DataInputStream` / `DataOutputStream` | Đọc/ghi các kiểu nguyên thủy theo định dạng nhị phân |
| `ByteArrayInputStream` / `ByteArrayOutputStream` | Dữ liệu trong mảng byte |
| `PrintStream` | Xuất dữ liệu dạng chữ, như `System.out` |
| `ObjectInputStream` / `ObjectOutputStream` | Java serialization; tránh giải tuần tự dữ liệu không tin cậy |

`InputStream.read()` trả về `0..255` hoặc `-1` khi hết dữ liệu. `read(byte[])` **có thể đọc ít hơn** số byte yêu cầu; không được coi một lời gọi read là một record/thông điệp hoàn chỉnh. `flush()` đẩy dữ liệu khỏi buffer của stream, nhưng không mặc nhiên đồng nghĩa ghi bền vững xuống thiết bị lưu trữ.

Dùng try-with-resources để đóng nguồn/đích ngay cả khi có exception:

```java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(destination)) {
    in.transferTo(out);
}
```

Đây là **đoạn minh họa** (có hai biến `Path source`, `Path destination`; import `java.io.*` và `java.nio.file.*`). `transferTo` có từ Java 9. `Files.newInputStream` thuộc NIO.2 nhưng **trả về `java.io.InputStream`**: các họ API được thiết kế để phối hợp.

### Character stream và charset

`Reader`/`Writer` làm việc với ký tự; `InputStreamReader`/`OutputStreamWriter` chuyển qua lại giữa byte stream và character stream nhờ một charset. `BufferedReader.readLine()` đọc dòng nhưng **bỏ ký tự xuống dòng**, còn `BufferedWriter` hữu ích để ghi dần lượng văn bản lớn.

```text
file bytes → InputStream → UTF-8 decoder → Reader → char
char → Writer → UTF-8 encoder → OutputStream → file bytes
```

Ưu tiên charset tường minh, ví dụ `StandardCharsets.UTF_8`. Trên **Java 17**, charset mặc định có thể phụ thuộc hệ điều hành/thiết lập; từ Java 18, JEP 400 đưa UTF-8 thành mặc định. Với định dạng dữ liệu cần tính di động, vẫn chỉ rõ charset.

Một điểm Unicode: độ dài `String` đếm đơn vị UTF-16 `char`, không phải số byte UTF-8 hay số code point. Ký tự ngoài BMP có thể dùng hai `char` (surrogate pair).

### `java.io.File`

`File` đại diện cho đường dẫn theo API cũ, không phải chính nội dung tệp. Trong mã mới, thường ưu tiên `Path`/`Files` vì nhiều thao tác hệ thống tệp và ngoại lệ I/O cụ thể hơn. Khi kết nối API cũ:

```java
Path path = oldFile.toPath();
File oldFileAgain = path.toFile();
```

Đoạn này giả định `oldFile` là `java.io.File`; `toFile()` chỉ được bảo đảm cho `Path` thuộc filesystem provider mặc định.

## 3. `java.nio`: Buffer + Channel + Charset + Selector

### `ByteBuffer` có trạng thái

`ByteBuffer` lưu byte và quản lý ba giá trị:

| Giá trị | Ý nghĩa |
|---|---|
| `capacity` | Sức chứa cố định |
| `position` | Chỉ số byte tiếp theo sẽ ghi/đọc |
| `limit` | Ranh giới được phép truy cập trong pha hiện tại |

Bất biến: `0 <= position <= limit <= capacity`. Mô hình chuyển pha:

```text
put(...) ──> buffer ở chế độ ghi ── flip() ──> get(...)
                                     │
                               hasRemaining()
                                     │
                           ┌─────────┴─────────┐
                           │                   │
                   clear() ghi lại      compact() giữ dữ liệu
                   từ đầu buffer        chưa đọc, ghi tiếp
```

- `put(...)` tăng `position` khi ghi vào buffer.
- `flip()` đặt `limit = position`, `position = 0` để đọc phần vừa ghi.
- `get()` tăng `position` khi đọc.
- `clear()` đặt `position = 0`, `limit = capacity`, **không xóa byte khỏi bộ nhớ**.
- `compact()` đưa các byte chưa đọc về đầu và đặt vị trí để bổ sung byte.
- `rewind()` đặt `position = 0` mà không đổi `limit`.

Chương trình Java 17 độc lập, lưu vào **`ByteBufferStateDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

public class ByteBufferStateDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(5);
        buffer.put(new byte[] {10, 20, 30});
        System.out.printf(
            "write: position=%d, limit=%d, capacity=%d%n",
            buffer.position(), buffer.limit(), buffer.capacity()
        );

        buffer.flip();
        System.out.println("read: " + buffer.get() + ", " + buffer.get());

        buffer.compact();  // Giữ 30, chuẩn bị ghi tiếp
        buffer.put((byte) 40);
        buffer.flip();

        List<Integer> remaining = new ArrayList<>();
        while (buffer.hasRemaining()) {
            remaining.add(Byte.toUnsignedInt(buffer.get()));
        }
        System.out.println("remaining: " + remaining);
    }
}
```

Chạy:

```bash
javac ByteBufferStateDemo.java
java ByteBufferStateDemo
```

Stdout:

```text
write: position=3, limit=5, capacity=5
read: 10, 20
remaining: [30, 40]
```

Kết quả chứng minh `compact()` giữ giá trị 30 chưa được đọc. Nếu gọi `clear()` thay `compact()`, vùng byte đó không còn được đánh dấu cần giữ.

`ByteBuffer.allocate` cấp phát heap buffer; `allocateDirect` tạo direct buffer có thể giảm một số bước sao chép ở native I/O nhưng chi phí cấp phát/thu hồi và giới hạn bộ nhớ khác. Không mặc định direct buffer luôn nhanh hơn. `ByteOrder` quy định thứ tự byte cho số nhiều byte, khác với charset của văn bản.

### `Channel` vận chuyển; `Buffer` chứa byte

`Channel` biểu diễn kết nối I/O. Các channel byte đọc vào `ByteBuffer` hoặc ghi từ `ByteBuffer`:

```text
Đọc: nguồn → channel.read(buffer) → buffer ghi → flip() → get()
Ghi: put(...) → buffer có dữ liệu → flip() → channel.write(buffer) → đích
```

`FileChannel` hỗ trợ đọc/ghi theo vị trí, `position`, `size`, `truncate`, `transferTo`, `transferFrom`, `map` và `force`. Một `read(buffer)` có thể trả `-1` ở EOF, `0` hoặc số byte dương nhỏ hơn sức chứa; một `write(buffer)` có thể ghi ít hơn toàn bộ số byte còn lại. Nếu cần chuyển hết dữ liệu, kiểm tra kết quả và lặp theo trạng thái `hasRemaining()`.

`FileChannel.map` trả `MappedByteBuffer` để ánh xạ vùng tệp vào bộ nhớ. Nó giúp truy cập một số kiểu dữ liệu lớn/ngẫu nhiên nhưng kéo theo quản lý mapping, native resource và nhất quán dữ liệu; không phải cách đọc file mặc định.

### Charset và ranh giới từng chunk

`java.nio.charset.Charset`, `CharsetDecoder`, `CharsetEncoder` xử lý biểu diễn ký tự. `StandardCharsets.UTF_8.decode(buffer)` thuận tiện nếu buffer chứa **toàn bộ** chuỗi byte UTF-8. Khi dữ liệu đến nhiều chunk, các byte của cùng một ký tự có thể bị chia ở hai chunk; hãy dùng decoder streaming, giữ phần byte chưa đủ, tránh chuyển từng chunk riêng thành String gây ký tự lỗi.

### Selector và mạng không chặn

`Selector` cho phép một thread chờ sự kiện sẵn sàng trên nhiều **`SelectableChannel`**:

1. Mở `Selector`, tạo `SocketChannel`, gọi `configureBlocking(false)`.
2. Đăng ký channel với các operation phù hợp như `OP_CONNECT`, `OP_READ`, `OP_WRITE`.
3. Trong event loop, gọi `select()` hoặc `select(timeout)`, xử lý các `SelectionKey` sẵn sàng, loại key đã xử lý khỏi selected-key set.
4. Giữ trạng thái đọc/ghi từng phần qua các sự kiện, xử lý lỗi, đóng tài nguyên và backpressure.

`SocketChannel`, `ServerSocketChannel`, `DatagramChannel` và một số pipe channel có thể dùng selector. **`FileChannel` không phải `SelectableChannel` và không đăng ký selector được.** Việc đăng ký `OP_WRITE` liên tục có thể gây vòng lặp bận vì socket thường sẵn sàng để ghi; chỉ đăng ký khi có dữ liệu còn chờ, tùy thiết kế event loop.

Selector không tự xử lý protocol framing, timeout, thread safety hoặc backpressure. TCP là **byte stream**: một `read` có thể nhận nửa message hoặc nhiều message; ứng dụng phải định nghĩa khung dữ liệu.

## 4. NIO.2: `Path`, `Files` và filesystem services

### `Path` biểu diễn đường dẫn; `Files` thao tác

`Path` đại diện các thành phần đường dẫn thuộc một `FileSystem`, không có nghĩa tệp đã tồn tại. `Files` là tập phương thức thao tác file/thư mục.

| Nhu cầu | API |
|---|---|
| Tạo đường dẫn | `Path.of(...)`; `base.resolve("name.txt")` |
| Chuẩn hóa cú pháp | `path.normalize()` |
| Kiểm tra loại file | `Files.isRegularFile`, `Files.isDirectory` |
| Đọc tệp văn bản nhỏ | `Files.readString(path, UTF_8)` |
| Ghi tệp văn bản | `Files.writeString(path, value, UTF_8)` |
| Xử lý văn bản dạng stream | `Files.newBufferedReader`, `newBufferedWriter` |
| Xử lý byte | `Files.newInputStream`, `newOutputStream` |
| Tạo cây thư mục | `Files.createDirectories` |
| Sao chép/di chuyển | `Files.copy`, `Files.move` cùng option |
| Liệt kê thư mục | `Files.list`, `Files.newDirectoryStream` |
| Duyệt đệ quy | `Files.walk`, `Files.walkFileTree` |
| Thuộc tính | `Files.readAttributes`, `BasicFileAttributes` |
| Theo dõi thay đổi | `WatchService`, `Path.register` |

`Path.of("data", "file.txt")` thường tương đối theo working directory của tiến trình. `toAbsolutePath()` chuyển thành đường dẫn tuyệt đối; `toRealPath()` còn truy vấn filesystem, có thể giải symbolic link. `normalize()` chỉ làm sạch thành phần cú pháp như `.`/`..`, không truy vấn đĩa và không bảo đảm an toàn.

`Files.exists(path)` và `Files.notExists(path)` đều có thể trả `false` khi không xác định. Kiểm tra trước rồi mở tệp có race condition (TOCTOU); hãy xử lý `IOException` của chính thao tác thay vì tin trạng thái ban đầu là bất biến.

### Ví dụ thực hành kết hợp cả ba họ API

Chương trình độc lập Java 17, lưu vào **`IoMapDemo.java`**. Nó tạo file bằng `Path`/`Files` (NIO.2), đọc text bằng `BufferedReader` (`java.io`) và đọc byte bằng `FileChannel`/`ByteBuffer` (NIO).

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class IoMapDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("io-map-");
        Path file = dir.resolve("message.txt");

        try {
            Files.writeString(file, "Xin chào Java\n", StandardCharsets.UTF_8);

            try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                System.out.println("Reader: " + reader.readLine());
            }

            try (FileChannel channel =
                     FileChannel.open(file, StandardOpenOption.READ)) {
                ByteBuffer buffer = ByteBuffer.allocate(64);
                int bytesRead = channel.read(buffer);
                buffer.flip();

                String text = StandardCharsets.UTF_8.decode(buffer)
                    .toString().stripTrailing();

                System.out.println("Channel bytes: " + bytesRead);
                System.out.println("Channel text: " + text);
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy:

```bash
javac IoMapDemo.java
java IoMapDemo
```

Stdout:

```text
Reader: Xin chào Java
Channel bytes: 15
Channel text: Xin chào Java
```

`Xin chào Java` kèm `\\n` có 14 `char` nhưng chiếm **15 byte UTF-8** do `à` dùng hai byte. Buffer 64 byte đủ chứa tất cả dữ liệu của ví dụ. Với file lớn, phải lặp read và quản lý ranh giới UTF-8 qua các chunk. `finally` dọn đúng thư mục/tệp vừa tạo trong ví dụ; không áp dụng xóa tương tự cho file người dùng.

### Duyệt thư mục và thuộc tính

`Files.list(dir)` trả về `Stream<Path>` gồm các mục trực tiếp; `Files.walk(dir)` có thể đi sâu vào cây. Stream do hai API này tạo ra sở hữu tài nguyên hệ thống tệp: phải đóng.

```java
try (var paths = Files.list(dir)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
```

Đoạn minh họa cần biến `Path dir` và import `java.nio.file.Files`; stdout phụ thuộc nội dung thực tế. `Files.walkFileTree` với `FileVisitor` thích hợp khi cần xử lý lỗi, traversal sâu và điều khiển hành vi theo từng nút.

`Files.size`, `BasicFileAttributes`, `PosixFileAttributes`, `DosFileAttributes` có mức hỗ trợ phụ thuộc filesystem provider/hệ điều hành. Không giả định attribute POSIX tồn tại trên Windows, hoặc symbolic link hoạt động như nhau mọi nơi. `Files.readSymbolicLink`, `Files.isSymbolicLink` và `LinkOption.NOFOLLOW_LINKS` giúp phân biệt một số thao tác đối với link. Nếu theo link khi duyệt cây, cần xử lý vòng lặp link/quyền truy cập.

### `WatchService`

`FileSystem.newWatchService()` tạo watcher; gọi `directory.register(watcher, ENTRY_CREATE, ENTRY_MODIFY, ENTRY_DELETE)` để đăng ký thư mục. Vòng lặp nhận `WatchKey`, đọc `pollEvents()`, xử lý `OVERFLOW` và gọi `reset()`; khi `reset()` trả false, key không còn hợp lệ. Việc watch một thư mục không tự động watch toàn bộ cây con. Sự kiện có thể gộp, đến trễ, bị mất do tràn hàng đợi hoặc do provider/hệ điều hành; ứng dụng cần đối chiếu trạng thái thực tế khi yêu cầu tính chính xác.

## 5. Chặn, không chặn, bất đồng bộ là các cơ chế khác nhau

| Mô hình | Ví dụ API | Đặc điểm |
|---|---|---|
| Đồng bộ, thường chặn | `InputStream.read`, `Files.readString`, các thao tác `FileChannel` thông thường | Thread gọi đợi thao tác hoàn tất theo ngữ nghĩa API |
| Non-blocking | `SocketChannel.configureBlocking(false)` + `Selector` | Một lần đọc/ghi có thể chưa tiến triển; tự giữ trạng thái và xử lý sự kiện |
| Asynchronous completion | `AsynchronousFileChannel.read` với `Future` hoặc `CompletionHandler` | Khởi động I/O rồi nhận kết quả sau; implementation có thể dựa trên thread pool |

Ví dụ async ngắn, **không phải chương trình độc lập** (giả sử có biến `Path path`, phương thức cho phép `throws Exception`):

```java
try (AsynchronousFileChannel channel =
         AsynchronousFileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(1024);
    Future<Integer> pending = channel.read(buffer, 0L);
    int count = pending.get();  // Thread hiện tại đợi ở đây
    if (count > 0) {
        buffer.flip();
        // Xử lý các byte vừa đọc
    }
}
```

Cần import `java.nio.ByteBuffer`, `java.nio.channels.AsynchronousFileChannel`, `java.nio.file.StandardOpenOption`, `java.util.concurrent.Future`. `pending.get()` ngay sau `read` khiến thread gọi vẫn **chờ**; để tránh chờ trực tiếp có thể dùng `CompletionHandler`. Provider không bắt buộc dùng native kernel asynchronous I/O.

NIO.2 còn bổ sung `AsynchronousSocketChannel`, `AsynchronousServerSocketChannel` cho mạng; mô hình callback/completion của chúng không giống event loop với `Selector`.

## 6. Các cầu nối (adapter) quan trọng

```text
java.io.File ──────────── .toPath() ──> Path
Path mặc định ─────────── .toFile() ──> java.io.File
Path ───────── Files.newInputStream ──> InputStream
Path ─── Files.newBufferedReader ──> BufferedReader
Path ──────── FileChannel.open ──> FileChannel ↔ ByteBuffer
Channel ─── Channels.newInputStream ──> InputStream
InputStream ─── Channels.newChannel ──> ReadableByteChannel
```

`java.nio.channels.Channels` là nơi có adapter stream/channel. Việc bọc stream thành channel **không tự biến nó thành selectable channel**. `Files.newByteChannel` có thể cung cấp `SeekableByteChannel` để truy cập byte theo vị trí; `FileChannel` có các tính năng tệp bổ sung như transfer, mapping, force.

Khi thư viện yêu cầu `InputStream`, `Reader`, `Path` hay `ByteBuffer`, nên dùng kiểu thư viện nhận và chuyển đổi ở đúng ranh giới. Không cần tái tạo một pipeline buffer/channel phức tạp chỉ để dùng API mới hơn.

## 7. Bảng chọn API theo bài toán

| Bài toán | Lựa chọn thông thường | Khi cần thay đổi |
|---|---|---|
| Đọc text nhỏ có charset xác định | `Files.readString(path, UTF_8)` | Text lớn: `newBufferedReader` để đọc dần |
| Ghi text | `Files.writeString` hoặc `newBufferedWriter` | Ghi lâu/dần: writer và buffer |
| Sao chép file | `Files.copy` | Dữ liệu không phải file: stream/channel |
| Xử lý binary tuần tự | `InputStream`/`OutputStream` | Truy cập offset: `FileChannel` |
| Cập nhật một vùng file | `FileChannel`/`SeekableByteChannel` | Mapping lớn đã đo đạc: `MappedByteBuffer` |
| Danh sách file, metadata | `Path`, `Files`, `FileVisitor` | API legacy cần `File`: dùng adapter |
| Mạng đơn giản | Socket + stream | Nhiều socket: cân nhắc channel + selector |
| Theo dõi thay đổi thư mục | `WatchService` | Cần trạng thái đúng: kết hợp quét xác minh |
| I/O tệp với completion bất đồng bộ | `AsynchronousFileChannel` | Chỉ cần I/O đồng bộ: `FileChannel`/`Files` |

Luôn xét **loại dữ liệu, kích thước, pattern truy cập, số kết nối và nhu cầu concurrency** trước khi chọn. `Files.readAllBytes` và `Files.readString` giữ nội dung trong bộ nhớ, dễ gây áp lực heap với file đầu vào không kiểm soát kích thước.

## 8. Lỗi phổ biến và các giới hạn cần nhớ

1. **Nhầm byte/character.** Không dựa vào độ dài `String` để suy số byte UTF-8, không decode từng chunk độc lập khi một ký tự có thể trải qua nhiều chunk.
2. **Đánh đồng NIO với non-blocking.** `Files.readString` và `FileChannel` thông thường là đồng bộ; `FileChannel` không đăng ký `Selector`.
3. **Giả định một lần read/write hoàn thành tất cả.** Xử lý EOF `-1`, partial read/write, backpressure và framing giao thức.
4. **Quên `flip()`, hoặc `clear()` quá sớm.** `compact()` giữ byte chưa đọc khi cần bổ sung dữ liệu.
5. **Rò rỉ tài nguyên.** Dùng try-with-resources cho stream, reader/writer, channel, `DirectoryStream`, `Files.list`/`walk` stream, `WatchService`.
6. **Nhầm flush/close với durability và atomicity.** `Files.move(..., ATOMIC_MOVE)` có thể báo `AtomicMoveNotSupportedException`; `flush` không tự bảo đảm `fsync`. Với dữ liệu quan trọng cần quy trình tệp tạm, sync, move và fallback có kiểm chứng theo platform.
7. **Giả định đường dẫn giống nhau mọi nơi.** Khác biệt case sensitivity, quyền, separator, symlink, metadata, charset mặc định và filesystem provider đều có thể làm mã thiếu tính di động.
8. **Kiểm tra rồi tin trạng thái không đổi.** `Files.exists`, `isReadable` và việc chuẩn hóa đường dẫn không ngăn TOCTOU, thay link, hoặc lỗi quyền truy cập; phải xử lý exception của thao tác thực.
9. **Không giới hạn tài nguyên.** Hạn chế open files/channels, buffer native, độ sâu traversal và kích thước dữ liệu; file mapping có vòng đời riêng.
10. **Giải tuần tự dữ liệu không tin cậy.** `ObjectInputStream` có rủi ro bảo mật với nguồn không đáng tin; ưu tiên định dạng/giao thức có xác thực đầu vào rõ ràng.

## 9. Câu hỏi tự kiểm tra

1. Cần đọc CSV 2 GB UTF-8. Vì sao `Files.readString` thường không phù hợp? Hãy chọn `Files.newBufferedReader` và giải thích việc đóng tài nguyên, xử lý từng record.
2. `ByteBuffer` có `capacity=8`, đã ghi 5 byte. Sau `flip()` thì `position=0, limit=5`. Đọc 2 byte rồi `compact()` thì **`position=3, limit=8`**. Vì sao?
3. Server cần phục vụ nhiều kết nối TCP. `SocketChannel` + `Selector` giải quyết bài toán gì, và vẫn cần tự giải quyết protocol framing/backpressure như thế nào?
4. Có thể đăng ký `FileChannel` với `Selector` không? **Không**, vì nó không phải `SelectableChannel`.
5. Có thể xem `WatchService` là lịch sử sự kiện đầy đủ không? **Không**, vì sự kiện có thể gộp/mất và xuất hiện `OVERFLOW`; cần đối chiếu filesystem.

**Ghi nhớ:** `java.io` cung cấp stream và reader/writer; `java.nio` cung cấp buffer, channel, charset và selector; NIO.2 mở rộng thành `Path`, `Files`, dịch vụ filesystem và API bất đồng bộ. Chúng bổ sung cho nhau và được chọn theo bản chất I/O của ứng dụng.
