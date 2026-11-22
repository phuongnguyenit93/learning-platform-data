# ReadableByteChannel, WritableByteChannel và ByteChannel trong Java NIO

## 1. NIO Channel là gì?

Trong Java NIO, **channel** là một đối tượng đại diện cho một kết nối I/O đang mở với nguồn hoặc đích dữ liệu: tệp, kết nối mạng, pipe, hoặc một nguồn/đích được chuyển đổi từ `InputStream` và `OutputStream`. Khi làm việc với **byte channel**, chương trình trao đổi dữ liệu qua `ByteBuffer`.

Ba interface nền tảng trong package `java.nio.channels` là:

- **`ReadableByteChannel`**: cho phép đọc byte từ channel vào `ByteBuffer`.
- **`WritableByteChannel`**: cho phép ghi byte từ `ByteBuffer` ra channel.
- **`ByteChannel`**: kết hợp cả hai khả năng đọc và ghi qua cùng một đối tượng.

Một channel thường có trạng thái **open/closed** qua interface `Channel`. Channel không đồng nghĩa với stream, nhưng có thể thích ứng với stream qua `java.nio.channels.Channels`. Quan trọng hơn, cả ba interface được thiết kế để dùng với buffer: các thao tác làm thay đổi **position** của `ByteBuffer` theo số byte đã chuyển, chứ không tự quản lý văn bản, charset hay ranh giới message.

Bài này tập trung vào **hợp đồng của các interface**, cách xử lý kết quả đọc/ghi chưa đủ, và cách chuyển trạng thái buffer để không làm mất dữ liệu.

## 2. Quan hệ kế thừa

Sơ đồ interface:

```text
                         java.nio.channels.Channel
                         + isOpen()
                         + close()
                            ^
                            |
           +----------------+----------------+
           |                                 |
ReadableByteChannel                 WritableByteChannel
+ read(ByteBuffer dst)              + write(ByteBuffer src)
           ^                                 ^
           |                                 |
           +---------------+-----------------+
                           |
                       ByteChannel
              (kế thừa cả read và write)
```

`Channel` mở rộng `java.io.Closeable`, nên có thể dùng `try-with-resources`. `ByteChannel` là interface hợp thành, không khai báo thêm phương thức đọc/ghi nào ngoài các phương thức kế thừa.

Các chữ ký quan trọng:

```java
// ReadableByteChannel
int read(ByteBuffer dst) throws IOException;

// WritableByteChannel
int write(ByteBuffer src) throws IOException;

// Channel
boolean isOpen();
void close() throws IOException;
```

Đây là các chữ ký API rút gọn để học tập, không phải một chương trình chạy độc lập.

| Interface | Đọc? | Ghi? | Đặc điểm |
| --- | --- | --- | --- |
| `ReadableByteChannel` | Có | Không bắt buộc | Lấy byte từ nguồn vào vùng còn trống của `dst` |
| `WritableByteChannel` | Không bắt buộc | Có | Lấy byte còn lại của `src` và đẩy tới đích |
| `ByteChannel` | Có | Có | Một đối tượng có cả hai hợp đồng, vẫn tùy cách mở và triển khai |
| `SeekableByteChannel` | Có | Có | Mở rộng `ByteChannel` với `position()`, `position(long)`, `size()`, `truncate()` |

**Lưu ý:** Một lớp có thể triển khai `ByteChannel` nhưng thao tác thực tế còn tùy cấu hình/mode. Ví dụ `FileChannel` mở chỉ để đọc không cho phép ghi; gọi `write` có thể ném `NonWritableChannelException`. Việc có phương thức `write` trong kiểu Java chưa bảo đảm tài nguyên đang được mở với quyền ghi.

## 3. `ReadableByteChannel.read(ByteBuffer dst)`

Lệnh:

```java
int n = channel.read(dst);
```

giả định `channel` là `ReadableByteChannel` đang mở và `dst` là `ByteBuffer` có thể ghi.

Phương thức cố gắng chuyển byte từ channel vào **vùng còn lại của buffer**: từ `dst.position()` tới ngay trước `dst.limit()`. Khi chuyển được `n > 0` byte, `position` tăng đúng `n`; `limit` và `capacity` không đổi vì thao tác này chỉ đặt thêm byte vào buffer.

Giá trị trả về có ba tình huống:

| Giá trị | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| `n > 0` | Đã đọc đúng `n` byte | Có thể tiếp tục đọc hoặc `flip()` để xử lý |
| `n == 0` | Lần gọi này chưa chuyển byte nào | Xem buffer còn chỗ không, mode blocking/non-blocking và readiness |
| `n == -1` | Đã tới **end-of-stream (EOF)** | Không chờ thêm dữ liệu từ nguồn đã kết thúc |

**Không hứa đọc đầy buffer trong một lần gọi.** Nếu `dst.remaining() == 100`, lệnh `read(dst)` có thể trả về 1, 24 hoặc một số dương khác tối đa 100. Buffer có `remaining()==0` thì không có chỗ để nhận byte; thường thao tác đọc trả về 0 khi không thể chuyển byte.

Với channel có chế độ **non-blocking**, `read` có thể trả về 0 khi chưa có dữ liệu sẵn sàng. Nếu channel blocking và buffer có chỗ, thao tác có thể phải chờ dữ liệu hoặc EOF theo hợp đồng của triển khai. Không viết vòng `while (read(...) == 0)` quay liên tục trên non-blocking channel: vòng lặp đó chiếm CPU mà không tạo tiến độ; cần phối hợp readiness/`Selector` hoặc cơ chế đợi phù hợp.

### Position trước và sau khi đọc

Giả sử `dst.capacity()==8`, `position==2`, `limit==6`, channel chuyển 3 byte:

```text
Trước: [ ? ][ ? ][ _ ][ _ ][ _ ][ _ ][ ? ][ ? ]
                    ^
                   pos=2
                                     ^
                                   limit=6

Sau:   [ ? ][ ? ][ A ][ B ][ C ][ _ ][ ? ][ ? ]
                                   ^
                                  pos=5
                                     ^
                                   limit=6
```

Chỉ vùng `[2,5)` được ghi mới. `n=3`; `dst.remaining()` sau đọc bằng 1. Byte cũ ngoài vùng này không tự bị xóa hay kiểm tra.

Một lệnh `read` cần buffer **có thể ghi**. Nếu `dst` chỉ đọc, thao tác có thể ném `ReadOnlyBufferException`; nếu channel đã đóng, có thể ném `ClosedChannelException` (đều cần phân biệt với kết quả EOF).

## 4. `WritableByteChannel.write(ByteBuffer src)`

Lệnh:

```java
int n = channel.write(src);
```

giả định `channel` là `WritableByteChannel` và `src` chứa dữ liệu cần chuyển ra ngoài ở vùng `[position, limit)`.

- `write` tiêu thụ **tối đa `src.remaining()` byte**, bắt đầu từ `position`.
- Trả về **số byte thực sự đã ghi**, không trả về `-1` như `read`.
- Sau khi ghi `n` byte, `src.position()` tăng đúng `n`; `limit` và `capacity` giữ nguyên.
- Nếu chưa ghi được byte nào, có thể trả về **0**, đặc biệt với channel không chặn hoặc khi `src` không còn byte.

**Không giả định một lần `write` ghi hết buffer.** Ví dụ nếu `src.remaining()==10` nhưng chỉ ghi được 4 byte, position tăng 4 và còn 6 byte chờ gửi. Gọi `clear()` lúc này sẽ làm mất trạng thái của phần chưa gửi; nếu tiếp tục sử dụng buffer, cần giữ nguyên position/limit rồi ghi tiếp cho đến khi hết `remaining` hoặc lưu lại phần dư theo chính sách.

### Quan hệ với `ByteBuffer.flip()`

Thông thường chương trình chuẩn bị byte để gửi như sau:

```java
ByteBuffer src = ByteBuffer.allocate(8);
src.put((byte) 65);
src.put((byte) 66);
src.put((byte) 67);
src.flip();   // position=0, limit=3
// WritableByteChannel.write(src) đọc 3 byte từ src nếu đích tiếp nhận đủ.
```

Đoạn mã trên là minh họa trạng thái; chưa chứa đối tượng channel. Quên `flip()` có thể khiến channel cố ghi từ offset 3 đến limit cũ 8, tức vùng không đại diện cho ba byte mới vừa chuẩn bị.

## 5. `ByteChannel`: một đối tượng có thể đọc và ghi

`ByteChannel` kế thừa cả `ReadableByteChannel` và `WritableByteChannel`. Vì thế biến có kiểu `ByteChannel` gọi được cả `read(ByteBuffer)` lẫn `write(ByteBuffer)`.

Nhưng **hai chiều thao tác không đồng nghĩa có file pointer, seek hoặc khả năng full-duplex luôn sẵn sàng**:

- `ByteChannel` **không định nghĩa** `position()` hay `position(long)`.
- Nếu cần di chuyển offset của tệp, dùng `SeekableByteChannel` hoặc `FileChannel`.
- Nếu cần channel mạng hỗ trợ đọc/ghi, `SocketChannel` là ví dụ triển khai có thêm cơ chế kết nối và non-blocking.
- Khả năng đọc và ghi tại cùng thời điểm, trạng thái kết nối, quyền I/O và khả năng thread-safe phụ thuộc vào lớp cụ thể.

Trong hệ thống tệp, `Files.newByteChannel(path, options...)` trả về `SeekableByteChannel`; đối tượng đó đồng thời là `ByteChannel`. Một handle có thể dùng để đọc và ghi nếu được mở với các `StandardOpenOption` phù hợp.

## 6. Ví dụ Java 17+ độc lập: sao chép dữ liệu qua hai channel

Chương trình tạo nguồn byte trong bộ nhớ và một đích byte trong bộ nhớ, rồi sử dụng hai interface riêng:

- `ReadableByteChannel` chuyển dữ liệu từ `ByteArrayInputStream` vào `ByteBuffer`.
- `WritableByteChannel` chuyển dữ liệu từ `ByteBuffer` vào `ByteArrayOutputStream`.
- `Channels.newChannel(...)` tạo adapter từ Java IO stream sang NIO channel.

Không cần tệp ngoài hoặc mạng; đầu ra xác định trên mọi môi trường Java 17+.

**Tệp `ChannelCopyDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Channels;
import java.nio.channels.ReadableByteChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;

public class ChannelCopyDemo {
    public static void main(String[] args) throws IOException {
        byte[] input = "Java NIO!".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (ReadableByteChannel source =
                     Channels.newChannel(new ByteArrayInputStream(input));
             WritableByteChannel target =
                     Channels.newChannel(sink)) {

            ByteBuffer buffer = ByteBuffer.allocate(4);
            int total = 0;

            while (true) {
                int count = source.read(buffer);

                if (count == -1) {
                    break; // EOF
                }
                if (count == 0) {
                    throw new IOException("No progress in blocking demo");
                }

                total += count;
                buffer.flip(); // Chuẩn bị vùng vừa nhận để ghi ra.

                while (buffer.hasRemaining()) {
                    int written = target.write(buffer);
                    if (written == 0) {
                        throw new IOException("No write progress in demo");
                    }
                }

                buffer.clear(); // Đã chuyển hết, chuẩn bị nhận vòng sau.
            }

            System.out.println("Da sao chep: " + total + " byte");
        }

        System.out.println(
            "Noi dung: " + sink.toString(StandardCharsets.UTF_8));
    }
}
```

Biên dịch và chạy:

```bash
javac ChannelCopyDemo.java
java ChannelCopyDemo
```

**Stdout chính xác khi thao tác thành công:**

```text
Da sao chep: 9 byte
Noi dung: Java NIO!
```

Giải thích bằng các vòng lặp buffer `capacity=4`:

| Lần nhận | Byte nhận | Position sau `read` | Sau `flip` | Đã ghi ra |
| --- | --- | ---: | --- | --- |
| 1 | `Java` (4 byte) | 4 | `position=0, limit=4` | `Java` |
| 2 | ` NIO` (4 byte) | 4 | `position=0, limit=4` | ` NIO` |
| 3 | `!` (1 byte) | 1 | `position=0, limit=1` | `!` |
| 4 | EOF | Không chuyển byte | Không `flip` | Thoát |

Với adapter trên `ByteArrayInputStream`, các lần đọc có đủ dữ liệu sẽ trả về số byte dương phù hợp kích thước buffer trong ví dụ. Trong **channel thực tế**, không nên dựa vào số byte nhận cố định như bảng minh họa; logic chính là dùng giá trị `count` thật sự, `flip` rồi ghi cho tới khi hết remaining.

Chương trình xử lý `count==0` và `written==0` bằng ngoại lệ vì đang dùng các adapter stream trong bộ nhớ mang tính blocking và luôn có buffer khác rỗng ở điểm thao tác. Đây **không phải chiến lược dùng cho mọi channel non-blocking**. Với `SocketChannel` non-blocking, cần cơ chế chờ readiness, giữ lại dữ liệu chưa gửi và tiếp tục khi channel sẵn sàng.

### Vì sao cần vòng lặp `while (buffer.hasRemaining())`?

`WritableByteChannel.write` có quyền tiêu thụ **một phần** dữ liệu. Nếu chỉ gọi `write` một lần rồi `clear`, phần chưa ghi có thể bị mất. Vòng lặp bảo đảm chương trình không bỏ qua phần dư; trong các ứng dụng non-blocking, vòng lặp sẽ được **tạm dừng khi write trả về 0** và tiếp tục sau khi có tín hiệu sẵn sàng, thay vì chạy quay liên tục.

## 7. Ví dụ Java 17+ độc lập: `ByteChannel` và đọc/ghi tệp

Ví dụ kế tiếp dùng `SeekableByteChannel` do `Files.newByteChannel` tạo ra. Vì interface này kế thừa `ByteChannel`, ta gán cùng đối tượng cho biến `ByteChannel io` để gọi `write` và `read`. Riêng thao tác đưa vị trí tệp về đầu phải gọi qua `SeekableByteChannel`.

**Tệp `ByteChannelFileDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ByteChannel;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ByteChannelFileDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("byte-channel-", ".bin");

        try {
            try (SeekableByteChannel file = Files.newByteChannel(
                    path,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteChannel io = file;
                ByteBuffer outgoing =
                    ByteBuffer.wrap("ABC".getBytes(StandardCharsets.US_ASCII));

                while (outgoing.hasRemaining()) {
                    int n = io.write(outgoing);
                    if (n == 0) {
                        throw new IOException("No file write progress");
                    }
                }

                System.out.println("Kich thuoc tep: " + file.size());

                file.position(0); // ByteChannel không có position(long).
                ByteBuffer incoming = ByteBuffer.allocate(3);

                while (incoming.hasRemaining()) {
                    int n = io.read(incoming);
                    if (n == -1) {
                        break;
                    }
                    if (n == 0) {
                        throw new IOException("No file read progress");
                    }
                }

                incoming.flip();
                System.out.println(
                    "Doc lai: " + StandardCharsets.US_ASCII.decode(incoming));
                System.out.println("Channel dang mo: " + io.isOpen());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Lệnh:

```bash
javac ByteChannelFileDemo.java
java ByteChannelFileDemo
```

**Stdout chính xác nếu I/O thành công:**

```text
Kich thuoc tep: 3
Doc lai: ABC
Channel dang mo: true
```

Vì sao có thể đọc lại?

1. `write` chuyển ba byte `A B C` xuống tệp và làm position của channel tệp tiến tới offset 3.
2. `file.position(0)` đặt lại offset trước khi đọc. `ByteChannel` thuần túy **không có** phương thức di chuyển vị trí này.
3. `read` đọc ba byte từ tệp vào `incoming` (đã cấp 3 byte).
4. `incoming.flip()` thiết lập vùng có dữ liệu để decoder lấy đúng ba byte.
5. `io.isOpen()` trả về `true` tại thời điểm kiểm tra bên trong `try`. Khi ra khỏi `try-with-resources`, channel được đóng.

`SeekableByteChannel` và `FileChannel` có thêm trạng thái vị trí tệp, khác với `ByteBuffer.position()`. **Hai vị trí này là hai trạng thái khác nhau**: position của buffer điều khiển byte nào trong bộ nhớ được chuyển; position của tệp điều khiển offset tệp nơi I/O diễn ra.

## 8. ByteBuffer là phần không thể tách rời của hợp đồng channel

`ReadableByteChannel.read(dst)` và `WritableByteChannel.write(src)` đều làm việc với một `ByteBuffer` đã được chuẩn bị đúng:

```text
Đọc từ channel vào buffer:
  buffer.clear() --> channel.read(buffer) --> buffer.flip()
  --> ứng dụng gọi buffer.get(...)

Ghi từ buffer ra channel:
  buffer.clear() --> ứng dụng buffer.put(...) --> buffer.flip()
  --> channel.write(buffer) (lặp/đợi đến khi xử lý phần cần gửi)
```

Với **chu trình truyền tiếp từ nguồn sang đích**, ví dụ `ChannelCopyDemo`, mỗi lần nhận một phần dữ liệu cần:

1. Buffer có không gian ghi: `position < limit`.
2. Channel nguồn `read(buffer)` và trả về số byte nhận.
3. Nếu đã nhận byte, `flip()` để limit thành số byte đã chuẩn bị.
4. Channel đích `write(buffer)` tới khi tiêu thụ hết hoặc tạm ngừng do chưa sẵn sàng.
5. Khi đã xử lý toàn bộ, dùng `clear()`; nếu cần giữ byte chưa xử lý thì dùng `compact()`.

| Phương thức Buffer | Ảnh hưởng tới state | Khi nào dùng |
| --- | --- | --- |
| `flip()` | `limit=position` cũ, `position=0` | Chuyển từ chuẩn bị dữ liệu sang tiêu thụ dữ liệu |
| `clear()` | `position=0, limit=capacity` | Bỏ vùng dữ liệu cũ đã hoàn thành |
| `compact()` | Giữ bytes chưa tiêu thụ ở đầu, `position=remaining` cũ, `limit=capacity` | Cần tiếp tục ghi thêm mà giữ phần dư |
| `remaining()` | `limit-position` | Xác định byte có thể chuyển trong lần này |
| `hasRemaining()` | `position<limit` | Kiểm tra còn dữ liệu hay không |

**`clear()` không xóa byte thực tế**. Khi buffer được dùng để chứa dữ liệu nhạy cảm, việc tái sử dụng/giải phóng bộ nhớ cần chính sách riêng.

### Lỗi rất thường gặp: đọc liên tục mà quên giải phóng chỗ

Giả sử channel đọc đủ 8 byte vào `ByteBuffer.allocate(8)`. Lúc đó position=limit=8; lần gọi `read(buffer)` kế tiếp **không còn chỗ**. Muốn nhận thêm, phải xử lý các byte có sẵn rồi `clear()` hoặc `compact()`. Không kết luận channel đã EOF chỉ vì nó không đưa thêm dữ liệu khi buffer đã đầy.

## 9. Blocking, non-blocking và tình huống không có tiến độ

Bản thân `ReadableByteChannel`, `WritableByteChannel` và `ByteChannel` **không cung cấp API cấu hình non-blocking**. Những chức năng như `configureBlocking(false)` thuộc `SelectableChannel` và các triển khai liên quan, chẳng hạn `SocketChannel`. `FileChannel` dùng I/O tệp và không phải `SelectableChannel`.

Với blocking channel, lời gọi thường chờ được dữ liệu hoặc đủ điều kiện xử lý theo hợp đồng của lớp đó; **không có bảo đảm mỗi lần đọc lấp đầy buffer, hay mỗi lần ghi hoàn thành toàn bộ dữ liệu nguồn**.

Với non-blocking channel:

- `read(dst) == 0`: có thể chưa có byte nào sẵn sàng; nếu buffer có chỗ, đăng ký/readiness `OP_READ` hoặc cơ chế tương đương.
- `write(src) == 0`: phía nhận chưa tiếp nhận thêm; giữ nguyên phần chưa gửi và chờ readiness `OP_WRITE` khi thích hợp.
- `read(dst) == -1`: EOF, cần kết thúc/đóng nửa đọc theo giao thức.

Không biến cả ba trường hợp thành cùng một trạng thái “xong”. Đặc biệt, chờ readiness phải phù hợp điều kiện kết nối và giao thức; ví dụ `SocketChannel` có thể có trạng thái kết nối chưa hoàn tất và truyền dữ liệu không đồng bộ.

### Khung thuật toán gửi non-blocking (minh họa)

```java
// Pseudocode gần Java: src đã ở read mode, channel non-blocking.
// Phương thức này chưa tự xử lý Selector và không chạy độc lập.
while (src.hasRemaining()) {
    int n = channel.write(src);

    if (n == 0) {
        // Lưu src/position, đăng ký cơ hội ghi tiếp;
        // kết thúc lượt xử lý hiện tại, không spin.
        break;
    }
}
```

Không gọi `src.clear()` sau khi chỉ mới gửi một phần. Những byte còn lại nằm trong `[src.position(), src.limit())`. Sau khi được báo có thể ghi tiếp, dùng lại cùng buffer hoặc lưu trạng thái tương đương; nếu cần nhận thêm dữ liệu trước đó, phải phối hợp `compact()` và `flip()` đúng pha.

## 10. EOF, close và lỗi I/O

Hợp đồng **read** và **write** khác nhau:

- **`read` trả về `-1`** khi kết thúc nguồn; đó là một giá trị bình thường của API, không mặc nhiên là lỗi I/O.
- **`write` không dùng `-1` báo EOF**. Nếu phía nhận đóng hoặc xảy ra lỗi, thao tác có thể ném `IOException` hay ngoại lệ cụ thể hơn.
- **`close()`** đóng channel. `isOpen()` phản ánh trạng thái mở/đóng của channel; một channel đã đóng không được “mở lại” bằng cách gọi `read` hoặc `write`.
- **`ClosedChannelException`** có thể phát sinh nếu thao tác khi channel đã đóng. Trong vài trường hợp, đóng không đồng bộ hoặc ngắt luồng lúc đang I/O có thể dẫn đến `AsynchronousCloseException` hoặc `ClosedByInterruptException` tùy triển khai.
- **`NonReadableChannelException` / `NonWritableChannelException`** xuất hiện trên các loại channel hỗ trợ cấu hình quyền đọc/ghi nhưng được mở với mode không phù hợp.

Tốt nhất quản lý vòng đời channel bằng `try-with-resources`:

```java
try (ReadableByteChannel source = /* kênh đã khởi tạo */) {
    // Đọc từ source, xử lý EOF và IOException.
}
```

Đây là **khung minh họa** và không phải chương trình biên dịch độc lập vì thiếu biểu thức tạo channel. Việc đóng channel cũng có thể đóng luồng/tài nguyên gốc khi dùng adapter như `Channels.newChannel(stream)`; cần thiết kế ownership tài nguyên cho rõ.

Không nên dùng `isOpen()` làm kiểm tra bảo đảm lời gọi I/O tiếp theo thành công: giữa hai lần gọi, channel có thể được đóng bởi luồng khác. Luôn xử lý ngoại lệ tại chính thao tác đọc/ghi.

## 11. Channel và Stream: khi nào dùng cái nào?

Java IO cổ điển có `InputStream.read(byte[])` và `OutputStream.write(byte[])`; NIO channel đọc/ghi qua `ByteBuffer`. Cả hai đều có chỗ sử dụng.

| Khía cạnh | `InputStream` / `OutputStream` | Byte channels |
| --- | --- | --- |
| Giao diện dữ liệu | Byte đơn, `byte[]` | `ByteBuffer` |
| Điều khiển vùng chuyển | Offset và length trên mảng | `position`, `limit`, `remaining` |
| Phối hợp NIO | Thông qua adapter hoặc API khác | Tương tác tự nhiên với buffer, một số channel hỗ trợ selector |
| Đọc/ghi chưa đủ | Vẫn phải xử lý theo hợp đồng từng API | Phải xử lý số byte trả về, partial write, EOF |
| Vị trí ngẫu nhiên | Không là khả năng chung của mọi stream | `SeekableByteChannel`/`FileChannel` hỗ trợ khi cần |

Có thể chuyển đổi qua `Channels`:

- `Channels.newChannel(InputStream)` → `ReadableByteChannel`.
- `Channels.newChannel(OutputStream)` → `WritableByteChannel`.
- `Channels.newInputStream(ReadableByteChannel)` → `InputStream`.
- `Channels.newOutputStream(WritableByteChannel)` → `OutputStream`.

Các adapter giúp tái sử dụng thành phần IO, **không tự biến nguồn/đích thành non-blocking** hoặc cho phép mọi channel tham gia `Selector`. Việc dùng stream hay channel còn phụ thuộc định dạng, độ phức tạp, chính sách blocking, khả năng tái sử dụng buffer và đo đạc hiệu năng thực tế; không mặc định NIO luôn nhanh hơn IO truyền thống trong mọi tải công việc.

## 12. Các interface mở rộng trong hệ sinh thái NIO

Sau khi hiểu ba interface căn bản, có thể nhận diện thêm một số khả năng mở rộng:

- **`ScatteringByteChannel`**: đọc dữ liệu từ một channel vào nhiều `ByteBuffer` theo thứ tự.
- **`GatheringByteChannel`**: ghi dữ liệu từ nhiều `ByteBuffer` ra một channel theo thứ tự.
- **`SeekableByteChannel`**: bổ sung vị trí và kích thước của tài nguyên có thể truy cập ngẫu nhiên.
- **`FileChannel`**: channel cho I/O tệp, mở rộng các khả năng đọc/ghi và vị trí, có thêm thao tác truyền dữ liệu, khóa tệp và ánh xạ bộ nhớ.
- **`SocketChannel`**: channel cho kết nối socket, hỗ trợ cả đọc và ghi cùng cơ chế non-blocking/selector.

Những khả năng này có **hợp đồng riêng**; `ByteChannel` không tự cung cấp thao tác `position(long)`, `transferTo`, `map`, `configureBlocking` hoặc `register`. Khi chương trình cần chức năng cụ thể, khai báo kiểu interface/lớp phù hợp thay vì giả định mọi channel đều có cùng API.

## 13. Bẫy API và cách tránh

| Sai lầm | Tác động | Cách làm đúng |
| --- | --- | --- |
| Dùng `channel.read(buffer)` một lần rồi tin đã đọc đủ | Mất dữ liệu nếu chỉ nhận một phần | Theo dõi số byte trả về và lặp/đợi theo giao thức |
| Coi `read == 0` là EOF | Kết thúc sớm, đặc biệt ở non-blocking | **Chỉ `-1` báo EOF** |
| Dùng vòng lặp vô hạn khi `read/write == 0` | Busy spin, tốn CPU | Dùng readiness/selector hoặc cơ chế đợi phù hợp |
| Chỉ gọi `write` một lần rồi `clear` | Bỏ các byte chưa gửi | Giữ phần `remaining` và viết tiếp |
| Quên `flip` sau `put` hoặc sau `read` vào buffer | Sai vùng byte đưa ra ngoài hoặc giải mã | Chuyển sang read mode trước khi tiêu thụ |
| `read` vào buffer đang đầy | Không còn chỗ nhận byte | Xử lý trước rồi `clear` hoặc `compact` |
| Mong `ByteChannel` có `seek` | API không định nghĩa seek | Dùng `SeekableByteChannel`/`FileChannel` |
| Gọi `write` qua `FileChannel` mở READ only | `NonWritableChannelException` | Mở với `WRITE` nếu cần ghi |
| Nghĩ channel luôn an toàn khi dùng từ nhiều luồng | Phụ thuộc triển khai và cách chia sẻ buffer | Kiểm tra hợp đồng thread-safety và quản lý sở hữu buffer |
| Không đóng channel | Rò rỉ tài nguyên | `try-with-resources` |
| Gọi `isOpen` rồi tin thao tác I/O chắc chắn thành công | Channel có thể bị đóng đồng thời | Xử lý ngoại lệ tại `read`/`write` |
| Nghĩ ByteChannel tự giải mã UTF-8 | Channel chuyển **byte**, không chuyển văn bản | Dùng `CharsetDecoder`/`CharsetEncoder` hoặc codec phù hợp |

## 14. Câu hỏi tự kiểm tra

**Tình huống A.** Một `ReadableByteChannel` chuyển hai byte vào `ByteBuffer.allocate(8)` mới tạo. Hỏi `position` và `limit` của buffer sau `read`?

**Đáp án:** Nếu `read` thực sự trả về `2`, `position=2` và `limit=8`. Gọi `flip()` tạo `position=0`, `limit=2` để đọc đúng hai byte đã nhận. Không được mặc định hai byte này là một ký tự hoặc một thông điệp hoàn chỉnh.

**Tình huống B.** `WritableByteChannel.write(src)` trả về 3 trong khi trước đó `src.remaining()==9`. Hỏi còn bao nhiêu byte chưa gửi?

**Đáp án:** Còn `9 - 3 = 6` byte. `src.position()` tăng 3; `src.limit()` giữ nguyên. Không được gọi `clear` rồi quên phần dữ liệu chưa gửi.

**Tình huống C.** Một `SocketChannel` non-blocking có buffer còn chỗ nhưng `read(dst)` trả về 0. Có thể kết luận peer đã đóng kết nối không?

**Đáp án:** Không. Giá trị 0 có thể nghĩa là hiện chưa có byte sẵn sàng. `-1` mới biểu thị EOF trong hợp đồng đọc. Cần sử dụng readiness và trạng thái giao thức tương ứng.

**Tình huống D.** Biến kiểu `ByteChannel channel` có thể gọi `channel.position(0)` không?

**Đáp án:** Không, interface `ByteChannel` không có phương thức ấy. Nếu đối tượng là `SeekableByteChannel`, khai báo đúng kiểu hoặc dùng kiểu đã được kiểm chứng để gọi `position(long)`.

## 15. Ghi nhớ

- **`ReadableByteChannel` đọc từ nguồn vào `ByteBuffer`**: kết quả `>0` cho số byte đã nhận, `0` cho chưa tiến triển, **`-1` cho EOF**.
- **`WritableByteChannel` ghi từ `ByteBuffer` ra đích**: trả về số byte đã ghi, có thể nhỏ hơn `remaining()`. Không bỏ dữ liệu còn lại.
- **`ByteChannel` kết hợp đọc và ghi**, nhưng **không tự định nghĩa seek, non-blocking hay khả năng đảm bảo đọc/ghi đồng thời**.
- **`ByteBuffer.position/limit` quyết định phần byte được trao đổi**; `flip`, `clear`, `compact` là công cụ chuyển pha chính.
- Dùng `try-with-resources`, xử lý `IOException`, phân biệt **0 với EOF**, và lựa chọn lớp channel cụ thể theo nhu cầu.
- Với tệp cần truy cập vị trí, tìm đến **`SeekableByteChannel` hoặc `FileChannel`**; với socket non-blocking, phải tổ chức vòng đời readiness và dữ liệu chờ gửi đúng cách.

**Tài liệu chuẩn:** Java SE 17 API: `java.nio.channels.Channel`, `ReadableByteChannel`, `WritableByteChannel`, `ByteChannel`, `SeekableByteChannel`, `FileChannel`, `SocketChannel`, `Channels` và `java.nio.ByteBuffer`.
