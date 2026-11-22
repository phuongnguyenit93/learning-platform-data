# `Channels.newChannel()`, `newInputStream()` và `newOutputStream()` trong Java NIO

## 1. Mục tiêu và bối cảnh

Java cung cấp hai nhóm API I/O thường gặp:

- **`java.io.InputStream` / `OutputStream`:** làm việc với chuỗi byte bằng `read()`, `read(byte[])`, `write(int)`, `write(byte[])`.
- **`java.nio.channels.ReadableByteChannel` / `WritableByteChannel`:** làm việc với byte thông qua `ByteBuffer` bằng `read(ByteBuffer)` và `write(ByteBuffer)`.

Khi thư viện cũ yêu cầu stream nhưng ứng dụng đang giữ channel, hoặc ngược lại, bạn không cần chép toàn bộ tệp vào RAM để đổi kiểu API. Lớp tiện ích **`java.nio.channels.Channels`** cung cấp các adapter giữ kết nối tới nguồn/đích I/O gốc.

Bài này giúp bạn:

1. Chọn đúng overload `Channels.newChannel(InputStream/OutputStream)`, `Channels.newInputStream(ReadableByteChannel)` và `Channels.newOutputStream(WritableByteChannel)`.
2. Hiểu luồng byte, quy tắc `ByteBuffer.flip()/clear()` và hành vi đọc/ghi một phần.
3. Quản lý đúng vòng đời: đóng adapter sẽ đóng I/O nguồn/đích phía dưới.
4. Nhận diện giới hạn blocking/nonblocking, việc không có bộ đệm bổ sung, encoding khi chuyển từ byte sang text và việc một adapter không biến stream thành channel ngẫu nhiên truy cập.
5. Chạy ví dụ Java 17+ kết nối hai hướng, kể cả `FileChannel` và `ByteArrayInputStream`.

Đây là bài về **kết nối API byte I/O**, không phải tạo một kiểu hệ thống tệp mới hay so sánh toàn bộ kiến trúc stream với channel.

## 2. Bản đồ chuyển đổi hai chiều

```text
                    Channels.newChannel(...)
  InputStream  ---------------------------------->  ReadableByteChannel
   read(byte[])                                      read(ByteBuffer)

                    Channels.newChannel(...)
  OutputStream ---------------------------------->  WritableByteChannel
   write(byte[])                                     write(ByteBuffer)


                    Channels.newInputStream(...)
  ReadableByteChannel -------------------------->  InputStream
   read(ByteBuffer)                                  read(byte[])

                    Channels.newOutputStream(...)
  WritableByteChannel -------------------------->  OutputStream
   write(ByteBuffer)                                 write(byte[])
```

Các kiểu và phương thức:

| Đầu vào | Hàm adapter | Kết quả | Hướng byte |
| --- | --- | --- | --- |
| `InputStream` | `Channels.newChannel(in)` | `ReadableByteChannel` | Đọc từ stream vào `ByteBuffer` |
| `OutputStream` | `Channels.newChannel(out)` | `WritableByteChannel` | Ghi từ `ByteBuffer` tới stream |
| `ReadableByteChannel` | `Channels.newInputStream(ch)` | `InputStream` | Đọc từ channel vào byte array hoặc một byte |
| `WritableByteChannel` | `Channels.newOutputStream(ch)` | `OutputStream` | Ghi byte array hoặc một byte tới channel |

`Channels` là một **lớp tiện ích có phương thức static**; ví dụ `Channels.newChannel(input)`, không dùng `new Channels()`. Những phương thức này không tự di chuyển con trỏ đọc của tệp về đầu, không nhân bản tệp hay tạo kết nối mạng khác. Chúng tạo một đối tượng nhìn vào nguồn/đích đã có.

Các adapter vẫn tuân thủ hướng của giao diện gốc. `newChannel(InputStream)` chỉ cho bạn giao diện **đọc**; không thể gọi `write()` trên kết quả ấy. Tương tự, `newChannel(OutputStream)` chỉ trả giao diện **ghi**.

## 3. `Channels.newChannel(InputStream)`: stream thành channel đọc

Chữ ký:

```java
public static ReadableByteChannel newChannel(InputStream in)
```

Adapter cho phép code đang nhận `ReadableByteChannel` tiêu thụ một `InputStream` đã có. Thay vì đọc vào `byte[]`, bên gọi sẽ đọc vào `ByteBuffer`:

```java
byte[] bytes = "ABC".getBytes(StandardCharsets.US_ASCII);
InputStream source = new ByteArrayInputStream(bytes);
ReadableByteChannel channel = Channels.newChannel(source);

ByteBuffer buffer = ByteBuffer.allocate(8);
int count = channel.read(buffer); // 3 byte trong ví dụ
buffer.flip();
while (buffer.hasRemaining()) {
    System.out.print((char) buffer.get());
}
channel.close(); // đóng cả source
```

Đoạn mã này là **minh họa cần import** (không phải chương trình độc lập). Nó cho thấy đường đi của byte:

1. `InputStream` cung cấp các byte `A`, `B`, `C`.
2. `ReadableByteChannel.read(buffer)` đưa byte vào khoảng `[position, limit)` còn trống và tăng `position` theo số byte đã đưa vào.
3. `buffer.flip()` chuẩn bị đọc lại số byte vừa nạp bằng `get()`.
4. `channel.close()` đóng luôn stream nguồn theo hợp đồng adapter.

`read(ByteBuffer)` trả số byte thực đọc, có thể nhỏ hơn `buffer.remaining()` trước khi gọi. `-1` biểu thị đã hết dữ liệu đầu vào (EOF). Nếu buffer không còn vị trí để nhận dữ liệu, yêu cầu đọc 0 byte có thể trả 0; nó không có nghĩa đã gặp EOF. Đừng mặc định mỗi `read()` luôn lấp đầy buffer, kể cả khi nguồn có thêm dữ liệu.

**Adapter không thêm buffering riêng.** Nếu nguồn là `BufferedInputStream`, buffer của chính `BufferedInputStream` vẫn tồn tại; câu “không buffer” của adapter nghĩa là nó không tự giới thiệu thêm một lớp bộ đệm có chính sách lưu dữ liệu độc lập.

## 4. `Channels.newChannel(OutputStream)`: stream thành channel ghi

Chữ ký:

```java
public static WritableByteChannel newChannel(OutputStream out)
```

Khi một API muốn nhận `WritableByteChannel` nhưng bạn chỉ có `OutputStream`, tạo adapter:

```java
ByteArrayOutputStream destination = new ByteArrayOutputStream();
WritableByteChannel channel = Channels.newChannel(destination);

ByteBuffer buffer = ByteBuffer.wrap(new byte[] {65, 66, 67});
while (buffer.hasRemaining()) {
    int written = channel.write(buffer);
    if (written == 0) {
        throw new IOException("Write made no progress");
    }
}
channel.close(); // đóng cả destination
System.out.println(destination.toString(StandardCharsets.US_ASCII));
```

Đoạn này là minh họa cần import và xử lý `IOException`; với `ByteArrayOutputStream`, việc đóng không làm mất những byte đã ghi. Output:

```text
ABC
```

Chữ ký `write(ByteBuffer)` trả số byte được ghi thực tế và tăng position của buffer. Theo hợp đồng `WritableByteChannel` nói chung, bên gọi cần xử lý **partial write** khi kết quả nhỏ hơn số byte ban đầu còn lại. Dùng `while (buffer.hasRemaining())` và có chiến lược khi không có tiến triển, tránh vòng lặp vô hạn với channel không chặn. Adapter từ `OutputStream` chuyển hướng việc ghi vào stream gốc; nó không biến đối tượng `OutputStream` thành `FileChannel` có `position(long)`, `truncate()` hoặc `transferTo()`.

Nếu chương trình chỉ cần chép một `InputStream` vào một `OutputStream`, `InputStream.transferTo(OutputStream)` có thể đơn giản hơn. Adapter hữu ích khi **chữ ký của API phải dùng channel** hoặc bạn đang xử lý dữ liệu qua `ByteBuffer`.

## 5. Ví dụ Java 17+ hoàn chỉnh: stream → channel → stream đích

Lưu chương trình sau thành **`StreamToChannelDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Channels;
import java.nio.channels.ReadableByteChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;

public class StreamToChannelDemo {
    public static void main(String[] args) throws IOException {
        byte[] input = "Xin chào NIO".getBytes(StandardCharsets.UTF_8);

        ByteArrayInputStream source = new ByteArrayInputStream(input);
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (ReadableByteChannel from = Channels.newChannel(source);
             WritableByteChannel to = Channels.newChannel(destination)) {

            ByteBuffer buffer = ByteBuffer.allocate(4);

            while (true) {
                int read = from.read(buffer);
                if (read == -1) {
                    break;
                }
                if (read == 0) {
                    throw new IOException("Unexpected read without progress");
                }

                buffer.flip();
                while (buffer.hasRemaining()) {
                    int written = to.write(buffer);
                    if (written == 0) {
                        throw new IOException("Write made no progress");
                    }
                }
                buffer.clear();
            }
        }

        System.out.println("bytes=" + destination.size());
        System.out.println("text="
                + destination.toString(StandardCharsets.UTF_8));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac StreamToChannelDemo.java
java StreamToChannelDemo
```

Stdout (UTF-8):

```text
bytes=13
text=Xin chào NIO
```

Giải thích:

- Chuỗi `Xin chào NIO` chứa 12 ký tự Java ở mức code point thông thường, nhưng UTF-8 mã hóa `à` bằng hai byte; vì vậy dữ liệu có **13 byte**. Cách đếm dung lượng dựa vào `byte[]` thực tế chứ không giả định `String.length()` bằng số byte.
- Buffer chỉ 4 byte để minh họa **nhiều vòng lặp**; UTF-8 có thể bị cắt giữa ký tự khi vận chuyển các chunk. Điều này **không làm hỏng dữ liệu** vì chương trình ghép nguyên vẹn byte rồi mới giải mã ở cuối.
- `from.read(buffer)` thay đổi position; `flip()` đổi từ nạp vào buffer sang đọc từ buffer; `to.write(buffer)` tiêu thụ các byte; `clear()` chuẩn bị nhận chunk mới.
- `try-with-resources` đóng hai channel, từ đó đóng các stream gốc theo hợp đồng adapter. Các thao tác `ByteArrayOutputStream.size()` và `toString(...)` vẫn dùng được sau `close()` vì loại stream này duy trì bộ nhớ đã ghi.

**Không dùng `new String(buffer.array(), UTF_8)` trên toàn bộ capacity sau mỗi `read()`:** phần còn lại của mảng có thể không chứa byte vừa nhận, và ký tự UTF-8 có thể nằm vắt qua hai chunk. Nếu ứng dụng phải chuyển **byte thành text khi đang streaming**, dùng `CharsetDecoder` có trạng thái hoặc lớp `Reader` phù hợp.

## 6. `Channels.newInputStream(ReadableByteChannel)`: channel thành stream đọc

Chữ ký:

```java
public static InputStream newInputStream(ReadableByteChannel ch)
```

Adapter này hữu ích khi code mới đang mở dữ liệu bằng `FileChannel` hoặc một `ReadableByteChannel`, nhưng thư viện cần tham số `InputStream`:

```java
ReadableByteChannel channel = FileChannel.open(path, StandardOpenOption.READ);
try (InputStream input = Channels.newInputStream(channel)) {
    byte[] bytes = input.readAllBytes();
    // Xử lý bytes; đóng input cũng đóng channel.
}
```

Đây là minh họa không độc lập; giả định `path` đã khai báo, trỏ đến tệp phù hợp, có các import cần thiết và phương thức bao quanh xử lý `IOException`. `readAllBytes()` hợp lý cho **dữ liệu nhỏ, có giới hạn**; tránh dùng để kéo cả file lớn hoặc đầu vào mạng vô hạn vào bộ nhớ. Có thể thay bằng vòng đọc `byte[]` theo chunk cố định.

Hợp đồng quan trọng của stream adapter này:

- `read()` và `read(byte[], off, len)` vận chuyển byte từ channel; khi channel đến EOF, lời gọi `read()` theo hợp đồng stream trả `-1`.
- Stream kết quả **không có buffering bổ sung**.
- Stream kết quả **không hỗ trợ `mark()` và `reset()`**; `markSupported()` trả `false`. Nếu thực sự cần hỗ trợ đánh dấu, cân nhắc `BufferedInputStream` và hiểu giới hạn readlimit của nó.
- Stream được công bố là **an toàn khi nhiều thread truy cập các phương thức của adapter**; điều này không biến toàn bộ resource, giao thức hay việc phối hợp với I/O từ các object khác thành thread-safe.
- **Đóng stream sẽ đóng channel nền**. Không dùng lại channel đó sau khi stream đóng.

Nếu một `FileChannel` có vị trí hiện tại khác 0, adapter sẽ đọc từ vị trí hiện tại ấy; nó không chủ động `position(0)` hoặc giải thích cấu trúc record thay bạn. Nếu cùng channel bị thao tác qua nhiều đường tham chiếu, việc thay đổi position có thể ảnh hưởng đến byte tiếp theo adapter đọc.

## 7. `Channels.newOutputStream(WritableByteChannel)`: channel thành stream ghi

Chữ ký:

```java
public static OutputStream newOutputStream(WritableByteChannel ch)
```

Bây giờ thư viện chỉ biết `OutputStream.write(byte[])` vẫn có thể ghi tới một channel đang có:

```java
WritableByteChannel channel = FileChannel.open(
        path, StandardOpenOption.WRITE, StandardOpenOption.CREATE);

try (OutputStream output = Channels.newOutputStream(channel)) {
    output.write("hello".getBytes(StandardCharsets.UTF_8));
}
```

Đoạn minh họa cần `path`, import và xử lý `IOException`. Quy tắc:

- `OutputStream.write(byte[], offset, length)` chuyển byte đến channel nền; adapter xử lý các thao tác ghi theo hợp đồng stream và byte channel.
- `newOutputStream` **không tự thêm buffering**, nên nếu muốn gom nhiều lệnh ghi nhỏ, có thể cân nhắc bọc `BufferedOutputStream` nhưng cần hiểu chính sách `flush()/close()`.
- **Đóng OutputStream đóng WritableByteChannel**.
- `flush()` ở tầng stream không đồng nghĩa file đã được đồng bộ bền vững ra thiết bị vật lý. Khi ứng dụng yêu cầu durability, cần xét `FileChannel.force(boolean)` hoặc API phù hợp, cũng như đặc tính hệ thống tệp.
- Nếu channel nền đang ở vị trí nào đó và có khả năng định vị, byte sẽ được ghi theo vị trí/trạng thái channel; adapter không tự mở tệp ở chế độ append hoặc reset vị trí.

`OutputStream` không có phương thức `position(long)`: adapter không biến channel có khả năng seek thành stream có khả năng seek. Nếu nghiệp vụ cần sửa byte tại offset, hãy sử dụng trực tiếp `SeekableByteChannel` hoặc `FileChannel`.

## 8. Ví dụ Java 17+ hoàn chỉnh: `FileChannel` → `OutputStream` / `InputStream`

Lưu dưới tên **`ChannelToStreamDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ChannelToStreamDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("channel-stream-", ".txt");

        try {
            byte[] bytes = "café".getBytes(StandardCharsets.UTF_8);

            FileChannel writable = FileChannel.open(
                    file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);

            try (OutputStream output = Channels.newOutputStream(writable)) {
                output.write(bytes);
            }
            System.out.println("write channel open=" + writable.isOpen());

            FileChannel readable = FileChannel.open(
                    file, StandardOpenOption.READ);

            byte[] copy;
            try (InputStream input = Channels.newInputStream(readable)) {
                copy = input.readAllBytes(); // chỉ vì ví dụ này rất nhỏ
            }
            System.out.println("read channel open=" + readable.isOpen());
            System.out.println("UTF-8 bytes=" + copy.length);
            System.out.println("text=" + new String(copy, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac ChannelToStreamDemo.java
java ChannelToStreamDemo
```

Stdout khi các thao tác I/O thành công:

```text
write channel open=false
read channel open=false
UTF-8 bytes=5
text=café
```

`café` có 5 byte UTF-8: ba chữ `c`, `a`, `f` chiếm mỗi chữ một byte, còn `é` chiếm hai byte. Hai dòng `isOpen=false` kiểm tra trực tiếp quan hệ đóng tài nguyên: đối tượng adapter là đối tượng được đóng trong `try-with-resources`, nhưng channel mà nó bọc cũng chuyển sang trạng thái đóng.

Mục đích của `Files.createTempFile` là tạo dữ liệu thử nghiệm ở vùng tạm, sau khi cả hai channel đóng mới xóa. Nếu quyền ghi, quyền đọc, xóa file hoặc dung lượng thiết bị không cho phép, `IOException` có thể xảy ra; đây là trường hợp lỗi I/O cần được xử lý ở ứng dụng thực tế.

## 9. Blocking và nonblocking: ranh giới quan trọng nhất

Một số channel hỗ trợ chế độ **nonblocking**, ví dụ `SocketChannel` hoặc `Pipe.SourceChannel` / `Pipe.SinkChannel` là những `SelectableChannel`. Trong nonblocking mode, lời gọi `read(ByteBuffer)` / `write(ByteBuffer)` có thể trả 0 khi hiện chưa có dữ liệu hoặc chưa thể ghi.

Trong khi đó, các adapter:

- `Channels.newInputStream(ReadableByteChannel)`
- `Channels.newOutputStream(WritableByteChannel)`

được thiết kế cho giao diện stream thông thường. Theo Java 17 API, các phương thức `read` / `write` của các adapter này sẽ ném **`IllegalBlockingModeException`** khi channel nền đang ở **nonblocking mode** tại thời điểm thao tác.

Vì vậy, không thể dùng `Channels.newInputStream(nonblockingSocketChannel)` như một cách né quy trình `Selector`. Nếu ứng dụng có event loop và channel nonblocking, tiếp tục dùng API channel theo đúng chiến lược readiness; đổi sang stream chỉ phù hợp khi lối truy cập blocking thật sự đúng cho thiết kế.

### Ví dụ xác nhận `IllegalBlockingModeException` (Java 17+)

Lưu thành **`NonBlockingAdapterDemo.java`**:

```java
import java.io.InputStream;
import java.nio.channels.Channels;
import java.nio.channels.IllegalBlockingModeException;
import java.nio.channels.Pipe;

public class NonBlockingAdapterDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);

            try (InputStream input = Channels.newInputStream(source)) {
                try {
                    input.read();
                    System.out.println("unexpected read");
                } catch (IllegalBlockingModeException expected) {
                    System.out.println("nonblocking channel rejected");
                }
            }
        }
    }
}
```

```bash
javac NonBlockingAdapterDemo.java
java NonBlockingAdapterDemo
```

Stdout theo hợp đồng khi chạy thành công:

```text
nonblocking channel rejected
```

`Pipe` được tạo nhưng không có byte nào được ghi vào sink; không hề cần đợi dữ liệu xuất hiện: adapter từ channel nonblocking từ chối thao tác đọc. `try-with-resources` đóng stream và đồng thời đóng source; việc đóng source lần nữa bởi outer `try` vẫn hợp lệ.

Cách xử lý đúng nếu ứng dụng thực sự cần chờ dữ liệu là dùng `source.configureBlocking(true)` trước khi truy cập kiểu stream (phải bảo đảm không xung đột với các đăng ký selector và luồng khác), hoặc tiếp tục đọc theo mô hình nonblocking với readiness/event loop thích hợp. **Không** vòng lặp gọi `input.read()` liên tục và bắt `IllegalBlockingModeException` để chờ I/O.

## 10. Overload cho `AsynchronousByteChannel`

Ngoài các adapter cho `ReadableByteChannel` và `WritableByteChannel`, `Channels` trong Java 17 còn cung cấp:

```java
InputStream  Channels.newInputStream(AsynchronousByteChannel ch)
OutputStream Channels.newOutputStream(AsynchronousByteChannel ch)
```

Ví dụ `AsynchronousSocketChannel` triển khai `AsynchronousByteChannel` và có thể dùng trực tiếp với các overload trên. Trái lại, **`AsynchronousFileChannel` không triển khai `AsynchronousByteChannel`**: các phương thức đọc/ghi bất đồng bộ của nó yêu cầu vị trí file (`read(buffer, position)` / `write(buffer, position)`), nên không thể truyền đối tượng này trực tiếp vào hai overload nhận `AsynchronousByteChannel`. Khi chương trình cần ghép một asynchronous byte channel với thư viện chỉ nhận `InputStream` / `OutputStream`, adapter sẽ cung cấp giao diện stream phù hợp.

Lưu ý về ý nghĩa: **API stream gọi đồng bộ từ thread sử dụng stream**; việc bọc một asynchronous channel không tự biến các lời gọi `InputStream.read()` / `OutputStream.write()` thành API nonblocking event-driven. Nếu muốn tận dụng callback hoặc `Future`, nên dùng trực tiếp các phương thức bất đồng bộ của channel.

Bốn điều vẫn cần nhớ với overload này: không có buffering bổ sung, `newInputStream` không hỗ trợ `mark/reset`, đóng stream đóng asynchronous channel, và phải xử lý lỗi I/O theo hợp đồng của stream. Không nhầm hai overload này với cách bọc một `SelectableChannel` đang cấu hình nonblocking ở mục trước.

## 11. Encoding và buffering khi chuyển đổi sang API text

`InputStream`, `OutputStream` và các byte channel **chỉ vận chuyển byte**. `Channels.newInputStream` / `newOutputStream` không nhận tham số charset và không giải mã hoặc mã hóa UTF-8 giùm ứng dụng.

Để đọc text UTF-8 khi thư viện cần `Reader`:

```java
Reader reader = new InputStreamReader(
        Channels.newInputStream(channel),
        StandardCharsets.UTF_8);
```

Đây là snippet minh họa: cần import `Reader`, `InputStreamReader`, `StandardCharsets`, khai báo `channel` là `ReadableByteChannel` và đóng `reader` đúng cách. Một lựa chọn khác là `Channels.newReader(channel, StandardCharsets.UTF_8)`.

Để ghi text UTF-8 khi thư viện cần `Writer`:

```java
Writer writer = new OutputStreamWriter(
        Channels.newOutputStream(channel),
        StandardCharsets.UTF_8);
```

Đây cũng là snippet minh họa cần import, channel là `WritableByteChannel`, và phải đóng/flush writer đúng vòng đời. Có thể dùng `Channels.newWriter(channel, StandardCharsets.UTF_8)` nếu phù hợp.

Lý do không tự `new String(chunk, UTF_8)` sau từng lần đọc channel: một ký tự nhiều byte có thể bị chia giữa hai chunk. `InputStreamReader`/`Channels.newReader` sử dụng decoder có trạng thái, xử lý các byte được nhận theo chuỗi.

Chú ý quan hệ nhiều lớp:

```text
Channel <- Channels.newInputStream(channel) <- InputStreamReader <- BufferedReader
                                         close theo chiều từ ngoài vào trong
```

Đóng `BufferedReader` sẽ đóng `InputStreamReader`, tiếp đó đóng adapter InputStream và cuối cùng channel nền. Nếu channel do thành phần khác vẫn cần sử dụng, không trao quyền đóng cho lớp ngoài hoặc phải thiết kế cơ chế sở hữu tài nguyên rõ ràng.

## 12. Sở hữu tài nguyên và hiệu ứng đóng lan truyền

Các phương thức `Channels.newChannel`, `newInputStream` và `newOutputStream` không tạo một bản sao độc lập của nguồn/đích. Chúng thường chia sẻ **cùng luồng byte và trạng thái nguồn/đích**; do đó thay đổi vị trí file, đọc trước, flush hay đóng ở một đường truy cập có thể ảnh hưởng đường khác.

Hợp đồng đóng:

| Adapter được tạo | Gọi `close()` trên | Hệ quả |
| --- | --- | --- |
| `Channels.newChannel(InputStream)` | Channel trả về | Đóng `InputStream` nền |
| `Channels.newChannel(OutputStream)` | Channel trả về | Đóng `OutputStream` nền |
| `Channels.newInputStream(ReadableByteChannel)` | Stream trả về | Đóng `ReadableByteChannel` nền |
| `Channels.newOutputStream(WritableByteChannel)` | Stream trả về | Đóng `WritableByteChannel` nền |
| `newInputStream/newOutputStream(AsynchronousByteChannel)` | Stream trả về | Đóng asynchronous channel nền |

Nếu một object đang được bên khác quản lý, hãy quyết định rõ **ai có quyền đóng**. Ví dụ, không bọc `System.out` bằng `Channels.newChannel(System.out)` rồi đóng channel trong thành phần nhỏ nếu chương trình vẫn cần in log bằng `System.out` sau đó. Đóng adapter theo thiết kế sẽ đóng luôn stream ấy.

Một vài nguyên tắc hữu ích:

- Dùng `try-with-resources` cho **đối tượng adapter ở tầng sở hữu cuối cùng**; tránh cố ý đóng tài nguyên nền quá sớm.
- Không giả định `flush()` trên stream tương đương ghi bền vững xuống ổ đĩa. Với dữ liệu quan trọng cần xem xét `FileChannel.force(...)` và chiến lược transaction/durability.
- Không gọi `read` hay `write` từ nhiều đường truy cập vào cùng channel/stream mà thiếu giao thức phối hợp, nhất là nếu vị trí đọc/ghi được chia sẻ.
- Việc stream adapter công bố an toàn cho nhiều thread **không bảo đảm** các object ở tầng trên hoạt động chính xác nếu đồng thời sửa trạng thái ứng dụng mà không đồng bộ.

## 13. Adapter giải quyết kiểu API, không cung cấp mọi tính năng channel

Bảng so sánh:

| Nhu cầu | Lựa chọn |
| --- | --- |
| API chỉ nhận `ReadableByteChannel` nhưng bạn có `InputStream` | `Channels.newChannel(input)` |
| API chỉ nhận `WritableByteChannel` nhưng bạn có `OutputStream` | `Channels.newChannel(output)` |
| API chỉ nhận `InputStream` nhưng bạn có `ReadableByteChannel` | `Channels.newInputStream(channel)` |
| API chỉ nhận `OutputStream` nhưng bạn có `WritableByteChannel` | `Channels.newOutputStream(channel)` |
| Đọc/ghi vị trí bất kỳ trong file | Dùng `FileChannel` hoặc `SeekableByteChannel` trực tiếp |
| Nonblocking socket và nhiều kết nối | Dùng `SelectableChannel` với `Selector` và xử lý readiness |
| Đọc/ghi text theo charset | Dùng `Reader`/`Writer` và `Charset` rõ ràng |
| Nạp cả file nhỏ vào RAM, xử lý đơn giản | `Files.readAllBytes` / `Files.readString` khi phù hợp giới hạn kích thước |
| Copy file lớn giữa các channel file | Cân nhắc `FileChannel.transferTo/transferFrom` khi điều kiện hỗ trợ phù hợp |

Adapter không tự chuyển một `InputStream` thành `SeekableByteChannel`, không tự cung cấp `FileLock`, không bảo đảm thao tác atomically hoặc tạo kênh có thể đăng ký `Selector`. Nó chỉ cung cấp giao diện đọc/ghi tương ứng, trên nguồn/đích gốc.

Nếu bạn cần dùng cả `InputStream` và channel để đọc một file, việc lựa chọn cách chia sẻ vị trí đọc phụ thuộc chính xác nguồn và adapter. Tránh giả định hai phía có hai con trỏ độc lập hoặc điều phối I/O bằng cách đổi API một cách tùy ý.

## 14. Lỗi phổ biến, dấu hiệu và cách khắc phục

### Lỗi 1: chọn nhầm hướng đọc/ghi

`Channels.newChannel(new FileInputStream(...))` trả `ReadableByteChannel`. Nếu code cần `WritableByteChannel`, hãy cung cấp `OutputStream` phù hợp. Trình biên dịch giúp phát hiện lỗi gán sai giao diện.

### Lỗi 2: quên `flip()` hoặc `clear()` khi chép qua `ByteBuffer`

Sau khi `read(buffer)`, position trỏ đến cuối dữ liệu nạp. Không `flip()` thì `write(buffer)` có thể ghi từ sai vùng. Sau khi ghi hết mà không `clear()`, lần đọc tiếp có thể thấy buffer không còn chỗ. Dùng quy trình `read → flip → write hết → clear` hoặc `compact` nếu cần giữ phần chưa tiêu thụ.

### Lỗi 3: giả định `write(buffer)` tiêu thụ hết

Một lần `WritableByteChannel.write(buffer)` có thể chỉ ghi một phần. Dùng:

```java
while (buffer.hasRemaining()) {
    int written = channel.write(buffer);
    if (written == 0) {
        // Với nonblocking channel: chờ OP_WRITE qua Selector.
        // Với channel chặn: xác định nguyên nhân thiếu tiến triển.
        throw new IOException("No write progress");
    }
}
```

Đây là snippet; thay logic khi `written == 0` bằng chính sách phù hợp với kiểu channel. Không áp dụng vòng quay bận CPU khi channel chưa sẵn sàng.

### Lỗi 4: bọc nonblocking channel thành stream rồi gọi `read()/write()`

`Channels.newInputStream` và `newOutputStream` cho `ReadableByteChannel` / `WritableByteChannel` ném `IllegalBlockingModeException` khi channel nền đang ở nonblocking mode. Tiếp tục dùng API channel và selector khi xử lý event-driven.

### Lỗi 5: tưởng adapter tự buffer hoặc chuyển mã

Adapter byte không tự thêm buffering, không mã hóa UTF-8. Muốn giảm số lời gọi I/O nhỏ, cân nhắc bộ đệm ở tầng thích hợp; muốn làm việc với ký tự, dùng `Reader`/`Writer` và charset chỉ định.

### Lỗi 6: đóng adapter rồi tiếp tục dùng nguồn/đích

`try-with-resources` đóng adapter và lan đến tài nguyên nền. Hãy kiểm soát vòng đời và quyền sở hữu, đặc biệt với `System.in`, `System.out`, socket hoặc kênh được chia sẻ.

### Lỗi 7: suy diễn an toàn đồng thời thành logic ứng dụng đúng

Việc adapter stream hỗ trợ truy cập từ nhiều thread không tự làm cho thứ tự record, trạng thái decoder, transaction hoặc khóa ứng dụng trở nên an toàn. Có thể cần một luồng đọc duy nhất hoặc cơ chế đồng bộ riêng.

### Lỗi 8: dùng `readAllBytes()` với file rất lớn hoặc nguồn vô hạn

`InputStream.readAllBytes()` có thể tiêu thụ lượng RAM lớn. Nếu kích thước không bị giới hạn, hãy xử lý chunk cố định hoặc dùng streaming parser.

### Lỗi 9: bọc qua nhiều lớp mà không kiểm tra ai flush/close

Cấu trúc `BufferedWriter(OutputStreamWriter(Channels.newOutputStream(ch)))` có nhiều tầng. `flush` của tầng ngoài đẩy dữ liệu đệm xuống tầng dưới, nhưng không hứa hẹn bền vững vật lý; `close` của tầng ngoài đóng dây chuyền đến channel. Chỉ một thành phần nên sở hữu quyết định đóng cuối cùng.

### Lỗi 10: kỳ vọng việc đổi adapter làm thay đổi trạng thái file

Bọc `FileChannel` thành `InputStream` không reset vị trí và không mở lại file. Khi cần đọc từ offset cụ thể, đặt vị trí bằng API channel (nếu được phép), hoặc mở resource mới theo ngữ nghĩa riêng.

## 15. Câu hỏi và bài tập thực hành

1. API nhận `ReadableByteChannel`, nhưng bạn đang có `BufferedInputStream`. Cần gọi phương thức nào? Đóng đối tượng trả về có ảnh hưởng gì đến stream cũ?
2. API nhận `OutputStream`, nhưng bạn đã có `FileChannel` mở với `WRITE`. Chọn adapter nào? Byte tiếp theo sẽ được ghi vào đâu?
3. Vì sao `Channels.newChannel(InputStream)` không tự tạo khả năng `seek`, `truncate` hoặc `FileLock`?
4. Nếu buffer capacity 4 chứa 4 byte UTF-8 đầu của một đoạn text, việc in riêng `new String(chunk)` có thể làm sai ký tự như thế nào?
5. Đoạn `while (buffer.hasRemaining()) channel.write(buffer)` có nguy cơ nào khi channel nonblocking không tiến triển? Bạn sẽ chờ theo cơ chế nào?
6. Điều gì xảy ra khi bạn đóng `Channels.newInputStream(fileChannel)` rồi gọi `fileChannel.read(...)`?
7. Vì sao stream adapter cho nonblocking `SocketChannel` không thay thế được `Selector`?
8. Đối với input 100 GiB, vì sao `InputStream.readAllBytes()` không phải thiết kế phù hợp? Hãy viết cách xử lý theo chunk hữu hạn.
9. `Channels.newInputStream(AsynchronousByteChannel)` có trả về API async để bên gọi await bằng `Future` không? Cần dùng interface nào nếu muốn callback/Future?
10. Thử giảm capacity buffer của `StreamToChannelDemo` từ 4 xuống 1. Kết quả text cuối có còn nguyên vẹn không? Giải thích điều kiện bảo toàn byte.

## 16. Tài liệu tham khảo

- [Java SE 17 API — `java.nio.channels.Channels`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Channels.html)
- [Java SE 17 API — package `java.nio.channels`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html)
- [Java SE 17 API — `java.nio.ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)

## 17. Ghi nhớ

**`Channels.newChannel(stream)`** chuyển stream byte sang byte channel cùng hướng; **`Channels.newInputStream(readableChannel)`** và **`newOutputStream(writableChannel)`** chuyển byte channel sang stream theo hướng tương ứng. Các adapter vận chuyển byte qua cùng tài nguyên nền, không tự thêm bộ đệm hoặc encoding, và đóng adapter sẽ đóng nguồn/đích bên dưới.

Khi kết hợp với NIO, hãy xử lý `ByteBuffer` bằng `flip()/clear()` đúng pha, kiểm tra kết quả `read/write`, tính đến partial write và không dùng adapter stream trên channel đang cấu hình nonblocking. Với text, dùng charset cùng `Reader/Writer`; với I/O có thể truy cập theo vị trí hoặc cần readiness/async thật sự, hãy giữ API channel chuyên dụng.
