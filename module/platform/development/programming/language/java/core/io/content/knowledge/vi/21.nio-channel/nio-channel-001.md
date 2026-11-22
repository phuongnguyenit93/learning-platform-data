# Channel khác InputStream và OutputStream như thế nào trong Java?

Trong Java, **`InputStream` / `OutputStream`** thuộc `java.io` và **Channel** thuộc `java.nio.channels` đều có thể vận chuyển **byte**, nhưng chúng tổ chức thao tác I/O theo những mô hình khác nhau. Hiểu khác biệt giúp chọn API đúng khi đọc tệp, gửi dữ liệu qua socket, xử lý tệp lớn hoặc cần truy cập những vị trí cụ thể trong file.

- **Stream** biểu diễn luồng byte được đọc từ một nguồn (`InputStream`) hoặc ghi đến một đích (`OutputStream`), với các phương thức xoay quanh `int` và `byte[]`.
- **Channel** biểu diễn một kết nối I/O có các khả năng được thể hiện qua interface: đọc, ghi, cả hai, seek, truyền trực tiếp, hoặc dùng cơ chế lựa chọn sự kiện nếu *đúng loại channel*. API đọc/ghi byte thông thường dùng **`ByteBuffer`**.
- **Không phải mọi Channel đều hai chiều, không phải mọi Channel đều non-blocking, và Stream không có nghĩa là luôn chậm.** Tính năng phụ thuộc loại channel/stream cụ thể, nơi lưu dữ liệu và cách sử dụng.

Một tệp văn bản nhỏ thường rất phù hợp với `Files.readString`, `BufferedReader` hoặc `InputStream`. Trong khi đó, đọc một phần tệp theo offset, ghi một record tại vị trí xác định, chuyển byte giữa hai channel hoặc lập trình mạng với `Selector` là những trường hợp NIO channel phát huy khả năng riêng.

## 1. Nền tảng: Stream là hướng byte, Channel là khả năng I/O

### `InputStream` và `OutputStream`

`InputStream` là lớp trừu tượng **đọc byte**; `OutputStream` là lớp trừu tượng **ghi byte**:

```java
int one = in.read();                   // 0..255 hoặc -1 tại EOF
int n = in.read(data, 0, data.length); // số byte thực đọc hoặc -1 tại EOF
out.write(data);                       // cố ghi toàn bộ mảng hoặc ném IOException
out.flush();                           // đẩy dữ liệu buffered nếu stream có buffer
```

Đây là **đoạn minh họa API**, giả định `in`, `out` và `data` đã được khởi tạo. Đừng coi một lần `read(byte[])` luôn lấp đầy mảng: nó có thể trả ít byte hơn số yêu cầu. Dù `OutputStream.write(byte[])` không trả số byte, việc gọi hàm có thể thất bại bằng `IOException`; không nên diễn giải đó là giao dịch ghi nguyên tử hoặc bảo đảm dữ liệu đã nằm trên đĩa.

Stream thường được ghép các lớp wrapper:

- `BufferedInputStream` / `BufferedOutputStream` thêm bộ đệm giúp giảm số lời gọi đến nguồn/đích nền.
- `DataInputStream` / `DataOutputStream` đọc/ghi giá trị kiểu nguyên thủy theo giao thức riêng; không biến stream thành một kho random access.
- `InputStreamReader` / `OutputStreamWriter` chuyển byte ↔ ký tự theo `Charset`. `BufferedReader` xử lý theo dòng sau khi đã giải mã ký tự.
- `FileInputStream` / `FileOutputStream` dùng tệp; `ByteArrayInputStream` / `ByteArrayOutputStream` dùng dữ liệu trong bộ nhớ; socket cũng có thể cung cấp stream.

Có thể dùng stream từ đầu đến cuối mà không cần tạo hay quản lý `ByteBuffer`. Khả năng đọc liên tục và bọc filter/decoder là ưu điểm quan trọng của mô hình này.

### Channel

Các interface nằm trong `java.nio.channels` phân biệt chức năng rõ hơn:

| Interface / lớp | Hợp đồng chính | Ví dụ |
| --- | --- | --- |
| `Channel` | Có trạng thái mở/đóng, `isOpen()` và `close()`; **chưa hề hứa có thể đọc/ghi**. | Nền tảng cho channel khác. |
| `ReadableByteChannel` | `read(ByteBuffer dst)` đọc byte vào buffer. | `FileChannel`, `SocketChannel`, `Pipe.SourceChannel`. |
| `WritableByteChannel` | `write(ByteBuffer src)` ghi byte còn lại của buffer. | `FileChannel`, `SocketChannel`, `Pipe.SinkChannel`. |
| `ByteChannel` | Kết hợp khả năng đọc và ghi; **không tự thêm phương thức mới**. | `FileChannel`, `SocketChannel`. |
| `SeekableByteChannel` | `position()`, `position(long)`, `size()`, `truncate(long)` cho thực thể có dãy byte thay đổi độ dài. | `FileChannel` hoặc channel trả bởi `Files.newByteChannel` nếu hỗ trợ. |
| `FileChannel` | Channel gắn với file: truy cập offset tuyệt đối, `map`, `transferTo/transferFrom`, `force`, file lock... | Đọc/ghi tệp, random access. |
| `SelectableChannel` | Có thể đăng ký `Selector`; có thể cấu hình blocking/non-blocking khi loại channel hỗ trợ. | `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`. |
| `AsynchronousFileChannel` | API bất đồng bộ với `Future` hoặc callback, khác `FileChannel` đồng bộ thông thường. | Truy cập file bất đồng bộ. |

Không lấy tên “NIO” rồi suy ra tất cả channel đều dùng `Selector` hoặc non-blocking. `FileChannel` không phải `SelectableChannel` và không đăng ký trực tiếp với `Selector`. Ngược lại, một `SocketChannel` có thể cấu hình `configureBlocking(false)` và kết hợp `Selector`.

## 2. So sánh chính xác những khác biệt quan trọng

| Tiêu chí | `InputStream` / `OutputStream` | NIO Channel |
| --- | --- | --- |
| Đơn vị API | Byte đơn lẻ hoặc mảng `byte[]`. | Thường là `ByteBuffer`, một số channel hỗ trợ nhiều buffer. |
| Hướng dữ liệu | Hai lớp độc lập: đọc hoặc ghi. | Chức năng do interface quyết định: read, write, both hoặc khả năng khác. |
| Kết quả đọc | `read()` trả byte `0..255` / `-1`; `read(byte[])` trả số byte hoặc `-1`. | `read(ByteBuffer)` trả số byte hoặc `-1`; có thể trả `0` tùy buffer/trạng thái/blocking. |
| Kết quả ghi | `write(...)` trả `void` theo hợp đồng stream. | `write(ByteBuffer)` trả số byte thực ghi; có thể ghi ngắn hoặc bằng `0`. |
| Quản lý bộ đệm | `byte[]` và optional `Buffered*Stream`. | `ByteBuffer` có `position`, `limit`, `capacity`; có heap/direct buffer. |
| Di chuyển offset | `InputStream` không có phương thức tổng quát “đặt vị trí tệp bằng offset” (một số stream có `skip` hoặc `mark/reset` theo điều kiện). | Chỉ **seekable** channel có `position(long)`; `FileChannel` còn hỗ trợ read/write theo offset tuyệt đối. |
| Non-blocking/selector | API stream căn bản thường được dùng theo cách blocking; không có `register(selector)`. | Một số **selectable** channel hỗ trợ non-blocking/`Selector`; không áp dụng chung. |
| Đặc tính tệp | Có thể đọc/ghi file qua stream, một vài file stream có `getChannel()`. | `FileChannel` chuyên cho file mapping, transfer, lock, force, positional I/O. |
| Thao tác thuận tiện | Stream wrappers, `readNBytes`, `transferTo(OutputStream)`, `Reader/Writer`. | Positional I/O, scattering/gathering, file channel transfer, event-driven socket I/O. |
| Đóng tài nguyên | `Closeable` / `AutoCloseable`; khuyến nghị `try-with-resources`. | `Channel extends Closeable`, cũng khuyến nghị `try-with-resources`. |

Hai cột chỉ so sánh **hợp đồng API**, không quyết định hiệu năng trong mọi bài toán. `BufferedInputStream` đọc tệp nhỏ có thể nhanh và đơn giản hơn việc cấp phát rồi quản lý `ByteBuffer` bằng tay. `FileChannel.transferTo` có thể được OS tối ưu để giảm bản sao dữ liệu, nhưng vẫn có thể chuyển ít hơn số byte yêu cầu hoặc dùng đường fallback tùy môi trường.

## 3. Khác biệt về bộ đệm: `byte[]` so với `ByteBuffer`

Với stream, buffer thường là một mảng do caller truyền vào:

```java
byte[] block = new byte[4096];
int n = in.read(block);
if (n > 0) {
    // Chỉ block[0..n-1] là dữ liệu vừa đọc.
}
```

Đây là đoạn minh họa, biến `in` được khai báo bên ngoài. Sau khi đọc, `n` là dữ liệu có nghĩa trong mảng; API không lưu `position/limit` trên chính mảng.

Với channel, bộ đệm mang theo cả **trạng thái vị trí**:

```java
ByteBuffer buffer = ByteBuffer.allocate(4096);
int n = channel.read(buffer); // ghi vào buffer từ position đến limit
buffer.flip();                // chuyển sang chế độ lấy dữ liệu đã đọc
// ... đọc dữ liệu từ buffer bằng get() / decoder ...
buffer.clear();               // chuẩn bị vùng chứa cho lần read tiếp theo
```

Đây là đoạn minh họa, biến `channel` là một `ReadableByteChannel` đã mở. Giải thích ba thuộc tính:

- `capacity`: sức chứa cố định của buffer.
- `position`: chỉ số đọc/ghi tiếp theo.
- `limit`: ranh giới có thể đọc/ghi của thao tác hiện tại.

Ví dụ buffer dung lượng `8` được channel đọc `3` byte: sau đọc, `position=3`, `limit=8`; sau `flip()`, `position=0`, `limit=3`; gọi `get()` ba lần thì `position=3`. `clear()` không xóa bytes về 0 mà chỉ đặt lại trạng thái để nhận dữ liệu mới. Nếu còn byte chưa xử lý khi muốn nhận thêm dữ liệu, dùng `compact()` để đưa phần còn lại về đầu rồi tiếp tục nhận.

**Lỗi rất phổ biến:** gọi `StandardCharsets.UTF_8.decode(buffer)` ngay sau `channel.read(buffer)` mà quên `flip()`; decoder sẽ xem vùng từ `position` hiện tại đến `limit`, thường gây thiếu dữ liệu hoặc kết quả rỗng/sai. Ngược lại, `flip()` không phải thứ cần gọi ở mọi bước: khi `ByteBuffer.wrap(bytes)`, buffer ban đầu đã có `position=0` và `limit=bytes.length`, sẵn sàng được channel **ghi ra**.

`ByteBuffer.allocate(...)` tạo heap buffer; `ByteBuffer.allocateDirect(...)` tạo direct buffer có thể hữu ích cho một số đường I/O native, nhưng cấp phát có chi phí và không được đảm bảo luôn nhanh hơn. Hãy đo bằng workload thực tế. Một `ByteBuffer` chia sẻ giữa nhiều thread cũng không tự thread-safe vì `position`/`limit` là mutable.

## 4. Khác biệt về vị trí: Stream tuần tự, channel có thể random access

`InputStream` tiến theo dữ liệu được đọc. Phương thức `skip(long)` chỉ yêu cầu bỏ qua byte theo kiểu tiến tới, có thể bỏ ít hơn yêu cầu; `mark/reset` không được mọi stream hỗ trợ và không đại diện cho offset tuyệt đối tùy ý trong file. `OutputStream` không có API chuẩn để “ghi ở byte thứ 100” của cùng một đối tượng stream.

`FileChannel` có thể:

```java
channel.position(100);        // đặt current file position
channel.read(buffer);         // đọc từ current position, vị trí tăng theo bytes đã đọc

channel.read(buffer, 500);    // đọc từ byte 500, KHÔNG đổi current position
channel.write(buffer, 200);   // ghi tại byte 200, KHÔNG đổi current position
```

Đây là đoạn minh họa khi `channel` là `FileChannel` và buffer đã chuẩn bị đúng trạng thái; lệnh có thể đọc/ghi ít byte hơn dự kiến. Cả `channel.position(100)` và positional overload chỉ có nghĩa với **đúng loại channel hỗ trợ**. `SocketChannel` không có phương thức `position(long)` vì socket là kết nối byte stream mạng chứ không phải một file seekable.

Khi dùng `FileInputStream.getChannel()` / `FileOutputStream.getChannel()`, channel gắn với stream đó và có liên hệ với vị trí file của cùng file descriptor: thay vị trí hoặc đọc/ghi từ một phía có thể ảnh hưởng vị trí quan sát qua phía kia. **Đừng giả định stream và channel lấy từ nó có hai cursor độc lập.** Nếu nhiều thao tác dùng chung current position, phải phối hợp theo yêu cầu ứng dụng. Mở hai handle riêng tạo trạng thái con trỏ riêng nhưng không làm dữ liệu file trở thành hai bản khác nhau.

### Ví dụ độc lập: Stream đọc tuần tự, FileChannel đọc/ghi theo offset

Tạo `StreamChannelComparison.java`:

```java
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class StreamChannelComparison {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("nio-contrast-", ".txt");
        try {
            Files.writeString(file, "ABCDEFG", StandardCharsets.US_ASCII);

            try (InputStream in = Files.newInputStream(file)) {
                byte[] first = in.readNBytes(3);
                System.out.println("stream=" + new String(first, StandardCharsets.US_ASCII));
            }

            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                ByteBuffer receive = ByteBuffer.allocate(3);
                int n = channel.read(receive, 4);
                receive.flip();
                System.out.println("channel-bytes=" + n);
                System.out.println("channel-data=" +
                        StandardCharsets.US_ASCII.decode(receive));
                System.out.println("current-position=" + channel.position());

                ByteBuffer replacement = ByteBuffer.wrap(
                        "xy".getBytes(StandardCharsets.US_ASCII));
                long offset = 1;
                while (replacement.hasRemaining()) {
                    int written = channel.write(replacement, offset);
                    if (written == 0) throw new IOException("Write stalled");
                    offset += written;
                }
            }
            System.out.println("final=" + Files.readString(file, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy trên Java 17+:

```bash
javac --release 17 StreamChannelComparison.java
java StreamChannelComparison
```

Kết quả:

```text
stream=ABC
channel-bytes=3
channel-data=EFG
current-position=0
final=AxyDEFG
```

**Vì sao có kết quả này?**

1. `Files.newInputStream` đọc ba byte liên tiếp bắt đầu từ đầu tệp, tạo chuỗi `ABC`.
2. `channel.read(receive, 4)` đọc ba byte tại offset `4..6` thành `EFG` nhưng **không di chuyển** current position của channel, nên vẫn là `0`.
3. `receive.flip()` cho phép decoder lấy ba byte vừa đọc.
4. `channel.write(replacement, offset)` ghi `xy` tại offset `1..2`; vòng lặp dự phòng khi một lần ghi chưa hết buffer. Nội dung cuối là `AxyDEFG`.
5. `try-with-resources` đóng stream và channel. File tạm được xóa ở `finally`.

Chương trình chủ động dùng ASCII để offset một byte trùng một ký tự. Với UTF-8, positional read/write phải xử lý ranh giới byte của ký tự đúng cách và chọn một giao thức record/encoding rõ ràng.

## 5. Blocking và non-blocking: khác biệt theo *loại channel*, không theo tên NIO

Một hiểu nhầm là “`java.io` blocking, `java.nio` luôn non-blocking”. Java NIO có cả channel **blocking** và channel có thể **non-blocking**.

- `FileChannel` thông thường thực hiện đọc/ghi đồng bộ với các lời gọi `read/write`; nó không phải `SelectableChannel` và không thể dùng `Selector` để chờ file sẵn sàng đọc như với socket.
- `SocketChannel` có thể ở chế độ blocking mặc định hoặc cấu hình `configureBlocking(false)`, khi đó `read/write` có thể trả `0` nếu chưa có dữ liệu hoặc chưa thể ghi. Kết hợp `Selector` để tránh tạo một thread chờ riêng cho mỗi kết nối, tùy kiến trúc server.
- `AsynchronousFileChannel` là lớp riêng, cung cấp thao tác file bất đồng bộ với completion callback hoặc `Future`; việc nhìn thấy “channel” trong tên không biến `FileChannel` thường thành API asynchronous.
- `InputStream.read` theo hợp đồng phổ biến chờ dữ liệu, EOF hoặc lỗi khi không có byte sẵn; tuy nhiên behavior cụ thể của stream wrapper/provider vẫn phải được hiểu từ API tương ứng.

`Selector` cũng **không tự tăng tốc đọc file** hoặc biến mọi luồng byte thành sự kiện. Đối với tệp lớn ở disk, `FileChannel` được chọn chủ yếu vì thao tác byte buffer, offset, transfer, mapping hoặc file control. Đối với hàng nghìn socket, selectable/non-blocking channel có thể cung cấp mô hình I/O rất khác stream kết hợp thread per connection.

## 6. Lệnh read/write không bảo đảm cùng lượng byte

Phân biệt hợp đồng I/O để tránh mất dữ liệu:

### Với `InputStream`

- `read()` trả `0..255` cho một byte hoặc `-1` khi EOF. Một byte giá trị `0xFF` trở thành số `255`, **khác** `-1`.
- `read(byte[])` trả số byte thực đọc hoặc `-1` khi EOF; không giả định một lời gọi luôn điền hết mảng.
- `readNBytes(length)` tiện khi muốn lấy tối đa một số byte; có thể trả ít nếu EOF đến trước. `readAllBytes()` tiện cho dữ liệu nhỏ đã có giới hạn, nhưng không thích hợp khi kích thước file/response không đáng tin và có thể quá lớn.
- Nếu cần đúng `N` byte trong một giao thức nhị phân, lặp cho đủ hoặc dùng API có nghĩa “đọc đủ hoặc lỗi”, như `DataInputStream.readFully(byte[])`; phải xử lý EOF phù hợp.

### Với Channel

- `ReadableByteChannel.read(ByteBuffer)` có thể trả số dương nhỏ hơn `remaining`, trả `0` khi không chuyển được byte trong một số trường hợp, hoặc `-1` ở EOF.
- `WritableByteChannel.write(ByteBuffer)` trả **số byte được tiêu thụ** từ buffer; có thể là `0` hoặc nhỏ hơn `remaining`.
- Sau khi đọc, cần `flip` trước khi tiêu thụ; sau khi xử lý một phần, cần `compact` nếu muốn giữ dữ liệu dư; khi ghi, loop tới khi `!buffer.hasRemaining()` hoặc áp chính sách non-blocking/backpressure phù hợp.
- Với channel non-blocking, không được busy-loop khi `read/write == 0`: đăng ký sự kiện với `Selector` hoặc lên lịch lại phù hợp.

Mẫu vòng lặp ghi đồng bộ (đoạn minh họa, `out` là `WritableByteChannel` đã mở):

```java
while (buffer.hasRemaining()) {
    int n = out.write(buffer);
    if (n == 0) {
        throw new IOException("Blocking write made no progress");
    }
}
```

Mẫu này phù hợp với ví dụ kênh blocking/dữ liệu nhỏ, nơi `0` bất thường. **Không sao chép nguyên xi chính sách “ném khi 0” vào network channel non-blocking**, nơi `0` là tình huống bình thường và cần quản lý `OP_WRITE`/backpressure thay vì ném lỗi hoặc quay CPU.

## 7. Stream và Channel kết nối với nhau được

Không cần viết lại toàn bộ ứng dụng để đổi giữa hai họ API: `java.nio.channels.Channels` cung cấp các adapter.

| Muốn có | API | Cần nhớ |
| --- | --- | --- |
| `ReadableByteChannel` từ `InputStream` | `Channels.newChannel(input)` | Adapter đọc qua stream gốc; không tự bổ sung seek/random access hay non-blocking. |
| `WritableByteChannel` từ `OutputStream` | `Channels.newChannel(output)` | Adapter ghi qua output stream gốc; không tạo file channel. |
| `InputStream` từ `ReadableByteChannel` | `Channels.newInputStream(channel)` | Đọc stream bằng channel phía dưới; quản lý trạng thái/đóng tài nguyên chung. |
| `OutputStream` từ `WritableByteChannel` | `Channels.newOutputStream(channel)` | Ghi stream bằng channel; không tự biến channel thành durable storage. |
| `Reader` / `Writer` từ byte channel | `Channels.newReader(...)` / `newWriter(...)` | Có giải mã/mã hóa ký tự theo charset; cẩn thận chữ tiếng Việt và ký tự cắt qua buffer. |

Một số adapter dùng channel có thể chọn non-blocking cần channel ở **blocking mode** cho lệnh bridge; nếu không, có thể gặp `IllegalBlockingModeException` tùy API. Dùng adapter không có nghĩa là bất đồng bộ hoặc non-blocking; khi chọn thiết kế mạng theo `Selector`, thường nên dùng trực tiếp `ByteBuffer`/`SocketChannel`.

**Ownership:** wrapper và channel/stream nền thường liên kết vòng đời. Đóng adapter có thể đóng channel/stream nguồn, vì vậy không được giả định có thể tiếp tục tái sử dụng tài nguyên gốc sau khi đóng wrapper. Tránh giao hai phần chương trình quyền tự ý đóng cùng một kết nối khi một phần vẫn đang dùng.

### Ví dụ độc lập: stream ↔ channel và UTF-8

Tạo `ChannelBridgeDemo.java`:

```java
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;

public class ChannelBridgeDemo {
    public static void main(String[] args) throws IOException {
        byte[] encoded = "học Java".getBytes(StandardCharsets.UTF_8);

        try (ReadableByteChannel input =
                Channels.newChannel(new ByteArrayInputStream(encoded))) {
            ByteBuffer buffer = ByteBuffer.allocate(encoded.length);
            while (buffer.hasRemaining()) {
                int n = input.read(buffer);
                if (n < 0) break;
                if (n == 0) throw new IOException("Read stalled");
            }
            System.out.println("bytes=" + buffer.position());
            buffer.flip();
            System.out.println("decoded=" + StandardCharsets.UTF_8.decode(buffer));
        }

        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (WritableByteChannel output = Channels.newChannel(sink)) {
            ByteBuffer buffer = ByteBuffer.wrap(
                    "OK".getBytes(StandardCharsets.UTF_8));
            while (buffer.hasRemaining()) {
                if (output.write(buffer) == 0) throw new IOException("Write stalled");
            }
        }
        System.out.println("sink=" + sink.toString(StandardCharsets.UTF_8));
    }
}
```

```bash
javac --release 17 ChannelBridgeDemo.java
java ChannelBridgeDemo
```

Kết quả:

```text
bytes=10
decoded=học Java
sink=OK
```

Cụm `học Java` có **8 ký tự** nhưng được UTF-8 mã hóa thành **10 byte**: chữ `ọ` dùng ba byte UTF-8; các ký tự còn lại ở ví dụ đều dùng một byte. `ByteBuffer.position()` sau đọc cho biết đã nhận 10 byte; `flip()` chuẩn bị để `UTF_8.decode(...)` tái tạo text. Ở chiều ghi, `Channels.newChannel(sink)` bọc `ByteArrayOutputStream` thành `WritableByteChannel`, rồi giải mã phần ghi không cần file thực.

Ví dụ dùng nguồn byte trong bộ nhớ để số byte và output xác định. Với socket thực hoặc stream có dữ liệu đến theo nhiều đợt, cách tích lũy và decode phải quản lý byte UTF-8 chưa hoàn chỉnh ở ranh giới từng lần đọc; không nên giải mã rời mỗi chunk bằng cách giả định nó luôn kết thúc ở ranh giới ký tự.

## 8. Tính năng thêm của một số Channel không có trực tiếp trên stream căn bản

### `FileChannel.transferTo / transferFrom`

`FileChannel.transferTo(position, count, target)` chuyển dữ liệu từ một vùng file sang `WritableByteChannel`. `transferFrom(src, position, count)` nhận dữ liệu từ một `ReadableByteChannel`. Đây là những API hữu ích khi chuyển phần lớn byte giữa tệp và các kênh I/O.

```java
long moved = sourceFileChannel.transferTo(offset, remaining, targetChannel);
```

Đoạn trên là minh họa, `sourceFileChannel`/`targetChannel` đã mở. **Không giả định `moved == remaining`**: kết quả có thể nhỏ hơn (kể cả `0`), nên ứng dụng phải xử lý phần dư, EOF và tình huống không thể tiến triển. Một số OS có tối ưu kiểu zero-copy, nhưng không có bảo đảm “luôn zero-copy” hay “luôn nhanh hơn mọi stream”.

### File mapping

`FileChannel.map(...)` tạo `MappedByteBuffer` cho một vùng file, có thể giảm thao tác copy hoặc hỗ trợ truy cập dữ liệu với mô hình memory mapping. Đây là năng lực **của FileChannel**, không phải của mọi `Channel`. Cần cân nhắc giới hạn map, vòng đời mapping, tính nhất quán với writer khác, flush và tài nguyên bộ nhớ ngoài heap; không chọn mapping mặc định cho mọi file.

### Scattering / gathering

Một `ScatteringByteChannel` có thể đọc lần lượt vào nhiều `ByteBuffer` trong một thao tác; `GatheringByteChannel` có thể ghi từ nhiều buffer. Ví dụ định dạng record gồm header và payload có thể dùng buffer riêng rồi kết hợp. Một lần gọi vẫn có thể xử lý ít byte hơn yêu cầu, do đó phải kiểm tra số byte thực và trạng thái từng buffer. Không phải mọi `ByteChannel` đều hỗ trợ các interface này.

### File locking và metadata

`FileChannel.lock`/`tryLock` hỗ trợ khóa vùng file khi môi trường thực thi và file store đáp ứng hợp đồng; chúng **không thay thế khóa logic trong JVM** để bảo vệ chuỗi cập nhật record từ nhiều thread. `Files`/`Path` và các file attribute views phụ trách phần lớn thao tác metadata; việc có `FileChannel` không có nghĩa mọi đặc tính tệp đều là method của channel.

## 9. Hiệu năng: chọn theo nghiệp vụ, không theo khẩu hiệu

Không có quy tắc “NIO luôn nhanh hơn IO”:

1. **Tệp nhỏ, luồng đơn, code đơn giản:** `Files.readString`, `Files.writeString`, `BufferedInputStream`, `BufferedReader` thường dễ đọc và hoàn toàn phù hợp.
2. **Dữ liệu lớn xử lý tuần tự:** xử lý từng khối với `BufferedInputStream` hoặc `FileChannel` đều có thể hiệu quả. Không nên `readAllBytes()` một nguồn có kích thước không bị giới hạn.
3. **Cần offset cố định/random access:** `FileChannel` hoặc `SeekableByteChannel` có `position`; `FileChannel` có overload đọc/ghi offset tường minh.
4. **Truyền vùng file qua channel:** đánh giá `transferTo` / `transferFrom`, xử lý trường hợp chuyển thiếu và đo trên OS mục tiêu.
5. **Nhiều socket đồng thời:** `SocketChannel` + `Selector`/non-blocking có thể hữu ích khi yêu cầu lập trình mạng thiên về event loop; độ phức tạp cao hơn với trạng thái đọc/ghi dở, backpressure và scheduling.
6. **Mã hóa text/đọc dòng:** `Reader`/`Writer`, `BufferedReader` hoặc `Channels.newReader/newWriter` giúp xử lý charset; ByteBuffer đơn thuần không biết đâu là ranh giới ký tự.

Muốn so hiệu năng cần xác định throughput, latency, số lần gọi I/O, kích thước buffer, heap/direct allocation, OS file cache, read-ahead, SSD/network và chi phí decode/copy. Một số API cấp cao trong `Files` có thể sử dụng cơ chế NIO bên dưới; so “package” không thay cho đo thực tế. Nếu thao tác chỉ là sao chép tệp, `Files.copy(source, target)` còn có thể phù hợp hơn cả viết vòng lặp stream/channel tùy chỉnh.

## 10. Lỗi phổ biến khi chuyển từ Stream sang Channel

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `read` vào buffer xong lại giải mã ra chuỗi rỗng/sai | Quên `flip()`; `position` đã ở cuối vùng vừa ghi. | `flip()` trước khi đọc từ buffer; `compact()` khi cần giữ dữ liệu còn lại. |
| Chỉ ghi được một phần payload | Tưởng `channel.write(buffer)` xử lý hết dữ liệu trong một gọi. | Loop theo `buffer.hasRemaining()` và theo hợp đồng blocking/non-blocking. |
| CPU tăng cao khi socket chưa ghi/đọc được | Busy-loop khi non-blocking `read/write` trả `0`. | Dùng `Selector`/interest ops và backpressure đúng cách. |
| Đọc sai byte sau khi đổi offset | Chia sẻ current position của cùng channel hoặc stream lấy từ channel. | Positional read/write, lock, hoặc ownership rõ ràng cho từng kết nối. |
| `IllegalBlockingModeException` với adapter | Bọc selectable channel không đúng chế độ blocking mà adapter yêu cầu. | Hiểu mode, chọn direct channel API khi vận hành non-blocking. |
| Tưởng mọi channel hỗ trợ `position` | Chỉ `SeekableByteChannel` có hợp đồng seek. | Dùng đúng interface cho file; không seek `SocketChannel`. |
| File đọc Unicode bị lỗi | Dùng byte offset như chỉ số ký tự, cắt UTF-8 giữa code point, hoặc dùng charset ngầm. | Chọn `StandardCharsets.UTF_8` và decoder đúng ranh giới; dùng `Reader` khi bài toán theo ký tự. |
| Gọi `flush()` nhưng nghĩ đã sync disk | `OutputStream.flush` chỉ đẩy byte còn trong tầng buffer theo implementation. | Cân nhắc `FileChannel.force` hoặc API/FS phù hợp khi thực sự cần durability; kiểm chứng hợp đồng nền tảng. |
| Đóng stream khiến channel không dùng tiếp được | Wrapper và tài nguyên gốc chia sẻ ownership/vòng đời. | Có một owner cho tài nguyên; dùng `try-with-resources` ở đúng phạm vi. |
| Thấy `transferTo` chuyển ít byte hơn dự kiến | Hợp đồng cho phép partial transfer/`0` theo trạng thái nguồn và đích. | Loop có kiểm soát, kiểm tra EOF và xử lý thiếu tiến triển. |

Một số ngoại lệ hữu ích cần biết khi thao tác channel gồm `ClosedChannelException`, `NonReadableChannelException`, `NonWritableChannelException` và `IOException`. Khi đổi chế độ mạng, `IllegalBlockingModeException` liên quan cách phối hợp blocking và adapter/selector; đừng xử lý chúng bằng cách nuốt lỗi và giả định số byte đã truyền đủ.

## 11. Mẫu quyết định: chọn API nào?

| Nhu cầu | Lựa chọn có lý do |
| --- | --- |
| Đọc tệp cấu hình nhỏ thành text | `Files.readString(path, UTF_8)` — ngắn, rõ ý định. |
| Đọc file CSV theo dòng | `Files.newBufferedReader(path, UTF_8)` hoặc `BufferedReader` — giải mã ký tự và đọc dòng. |
| Đọc binary stream tuần tự từ network/library có sẵn `InputStream` | `InputStream` + buffer phù hợp — tận dụng API đang có. |
| Ghi binary stream đến API nhận `OutputStream` | `OutputStream` (có `BufferedOutputStream` nếu cần) — tránh adapter không cần thiết. |
| Thao tác tại byte offset hoặc đọc nhiều phần file rời nhau | `FileChannel.read/write(ByteBuffer, position)` hoặc `SeekableByteChannel`. |
| Cần đọc và ghi cùng file bằng một tài nguyên | `FileChannel` với `READ` và `WRITE` — hai hướng, có position rõ ràng. |
| Xử lý nhiều socket không blocking với event loop | `SocketChannel`/`ServerSocketChannel` + `Selector` — phối hợp readiness. |
| Chuyển vùng file sang writable channel | `FileChannel.transferTo(...)` — có thể tối ưu đường truyền, nhưng xử lý partial transfer. |
| Đã có `InputStream` nhưng thư viện chỉ nhận `ReadableByteChannel` | `Channels.newChannel(input)` — chuyển interface có kiểm soát vòng đời. |

### Câu hỏi tự kiểm tra

**1. Vì sao một `FileChannel` là `ByteChannel` nhưng một `Pipe.SourceChannel` không phải channel ghi được?**

Vì `ByteChannel` hợp nhất cả `ReadableByteChannel` và `WritableByteChannel`. Pipe source chỉ có nhiệm vụ nhận byte từ đầu source, không hứa khả năng ghi; chức năng phụ thuộc interface thực tế.

**2. `ByteBuffer.flip()` có nhiệm vụ gì?**

Nó đặt `limit` thành `position` hiện tại rồi đưa `position` về `0`, chuẩn bị tiêu thụ bytes vừa ghi vào buffer. Nó không thay đổi nội dung bytes và không phải lệnh flush xuống đĩa.

**3. Vì sao `write(ByteBuffer)` thường cần vòng lặp còn `OutputStream.write(byte[])` không trả số byte?**

Hai API có hợp đồng khác nhau. Writable channel trả số byte thực chuyển, có thể ghi ngắn hoặc chưa ghi; output stream không trả số byte và có thể báo lỗi bằng `IOException`. Không được từ điều đó suy ra output stream đảm bảo atomic/durable.

**4. `FileChannel` có non-blocking như `SocketChannel` không?**

Không theo nghĩa selectable non-blocking I/O. `FileChannel` thông thường là channel truy cập file đồng bộ và không đăng ký `Selector`; `SocketChannel` có thể cấu hình non-blocking.

**5. `Channels.newChannel(InputStream)` có làm InputStream thành file random access không?**

Không. Nó cung cấp adapter đọc kiểu channel trên nguồn có sẵn; không tự tạo `FileChannel` hoặc khả năng seek.

**6. Khi nào nên giữ `InputStream` thay vì đổi sang NIO?**

Khi bài toán là đọc tuần tự, giao diện thư viện đã phù hợp, performance chấp nhận được và không cần tính năng channel riêng; code đơn giản hơn thường dễ bảo trì và kiểm thử hơn.

## Tài liệu chính thức

- [Java SE 21 — `InputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html) và [`OutputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/OutputStream.html): hợp đồng byte stream.
- [Java SE 21 — `java.nio.channels` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/package-summary.html): hệ thống interface và mô hình channel.
- [Java SE 21 — `FileChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): file positioning, positional I/O, transfer, mapping và file locking.
- [Java SE 21 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip`, `clear`, `compact`.
- [Java SE 21 — `Channels`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Channels.html): adapter giữa channel, stream, reader và writer.
- [Java SE 21 — `SocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): channel socket và blocking mode.

**Ghi nhớ:** chọn API theo khả năng cần dùng và hợp đồng về bytes, buffer, offset, blocking, vòng đời tài nguyên. Stream thuận tiện cho xử lý tuần tự; channel mở rộng khả năng thao tác trên `ByteBuffer` và những tính năng riêng của file/network channel, nhưng không có lựa chọn nào tự động tốt hơn trong mọi hoàn cảnh.