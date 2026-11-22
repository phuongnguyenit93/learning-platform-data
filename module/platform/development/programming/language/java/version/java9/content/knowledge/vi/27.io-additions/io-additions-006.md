# Lỗi I/O, trạng thái luồng và dữ liệu đã chuyển một phần

Khi đọc hoặc ghi dữ liệu bằng Java I/O, một lời gọi không nhất thiết xử lý toàn bộ số byte mà ứng dụng yêu cầu. Nguồn có thể trả về ít byte hơn kích thước buffer; đích có thể ghi được một phần; lỗi có thể xuất hiện sau khi một phần dữ liệu đã đi qua. Vì vậy, mã I/O cần theo dõi số byte thực tế, nhận biết EOF, quản lý vòng đời tài nguyên và quyết định cách phục hồi khi thao tác thất bại.

Bài này tập trung vào luồng I/O byte (`InputStream`, `OutputStream`) và kênh NIO (`ReadableByteChannel`, `WritableByteChannel`). Đây là trạng thái truyền dữ liệu của I/O, không phải `java.util.stream.Stream`.

## 1. Các trạng thái cần phân biệt

Một luồng I/O không có một API trạng thái chung kiểu `isEOF()` hoặc `isFailed()` cho mọi implementation. Trạng thái thường được nhận biết từ kết quả đọc/ghi, ngoại lệ và vòng đời tài nguyên.

| Trạng thái | Cách nhận biết | Ý nghĩa |
|---|---|---|
| Đang mở | Đọc/ghi chưa báo lỗi đóng; với channel có thể kiểm tra `isOpen()` | Có thể tiếp tục thao tác theo hợp đồng của implementation |
| Đã đến EOF | `InputStream.read(...)` trả `-1`; channel đọc trả `-1` | Nguồn không còn dữ liệu; đây không phải lỗi I/O |
| Đã đóng | Ứng dụng đã gọi `close()`; channel trả `isOpen() == false` | Tài nguyên đã được giải phóng; thao tác tiếp theo thường thất bại |
| Gặp lỗi I/O | Phương thức ném `IOException` hoặc subclass | Thao tác không hoàn tất như yêu cầu; trạng thái và lượng dữ liệu đã chuyển phụ thuộc API/implementation |
| Bị gián đoạn hoặc timeout | Có thể gặp `InterruptedIOException`, `SocketTimeoutException`, `ClosedByInterruptException` hoặc ngoại lệ liên quan channel | Cần xử lý thời gian chờ, interrupt và tiến độ đã thực hiện theo loại API |

EOF chỉ có ý nghĩa với phía đọc. Một `OutputStream` không có trạng thái EOF: ứng dụng ghi dữ liệu, flush và đóng luồng để kết thúc việc sử dụng tài nguyên.

Với `InputStream`, kết quả `-1` cho biết đã hết dữ liệu. Với `ReadableByteChannel`, `read(ByteBuffer)` trả `-1` khi đạt EOF. Một channel có thể đang mở nhưng nguồn đã hết dữ liệu; “mở” và “còn dữ liệu” là hai khái niệm khác nhau.

`InputStream` không có phương thức `isOpen()` chung. Việc một stream đã đóng thường được quản lý bằng cấu trúc sở hữu tài nguyên, chẳng hạn `try-with-resources`. Hành vi đọc sau khi đóng phụ thuộc implementation; nhiều stream sẽ ném `IOException`.

## 2. Đọc một phần: không giả định buffer luôn đầy

`InputStream.read(byte[], off, len)` cố gắng đọc tối đa `len` byte và trả về số byte thực tế đã đọc. Kết quả có thể nhỏ hơn `len`, ví dụ khi dữ liệu đến theo từng đợt hoặc nguồn chỉ cung cấp một phần tại thời điểm gọi.

Quy tắc quan trọng:

- Số dương: có đúng số byte đó được ghi vào vùng buffer bắt đầu từ `off`.
- `-1`: đã đến EOF và không có byte nào được đọc trong lần gọi đó.
- `0`: xảy ra khi `len == 0`; với `len > 0`, hợp đồng `InputStream` thông thường cố gắng đọc ít nhất một byte nếu chưa EOF.
- `IOException`: thao tác đọc thất bại. Với một số lời gọi, dữ liệu có thể đã được lấy trước khi lỗi xuất hiện; API không phải lúc nào cũng trả lại số byte đó.

Cách đọc an toàn là xử lý đúng phần `[0, count)` mà lời gọi trả về:

```java
byte[] buffer = new byte[8192];

try (InputStream input = Files.newInputStream(path)) {
    int count;
    while ((count = input.read(buffer)) != -1) {
        process(buffer, 0, count);
    }
}
```

Không xử lý toàn bộ buffer nếu `count` nhỏ hơn kích thước mảng. Các byte sau `count` có thể là dữ liệu cũ từ lần đọc trước hoặc giá trị chưa được ghi.

Nếu cần đọc tối đa một số byte xác định, Java 9 trở lên có `readNBytes`:

```java
byte[] header = input.readNBytes(16);
if (header.length < 16) {
    // Nguồn kết thúc trước khi có đủ header.
}
```

`readNBytes(byte[], off, len)` trả về số byte thực tế đọc được và có thể trả ít hơn yêu cầu khi gặp EOF. `readAllBytes()` đọc toàn bộ phần còn lại của stream; chỉ dùng khi dữ liệu có kích thước hợp lý vì toàn bộ nội dung phải nằm trong bộ nhớ. `transferTo(OutputStream)` chuyển phần còn lại sang output và trả tổng số byte khi hoàn tất bình thường.

Không dùng `InputStream.available()` để quyết định đã đọc hết dữ liệu hay để suy ra kích thước đầy đủ của file/socket. Phương thức này chỉ ước lượng số byte có thể đọc mà không bị chặn tại thời điểm gọi.

### Đọc một bản ghi có kích thước cố định

Nếu giao thức yêu cầu chính xác 16 byte cho một header, đọc được 7 byte rồi gặp EOF không phải là một header hợp lệ. Có thể dùng `DataInputStream.readFully`:

```java
byte[] header = new byte[16];

try (DataInputStream data = new DataInputStream(input)) {
    data.readFully(header);
}
```

Nếu nguồn kết thúc trước khi đủ dữ liệu, `readFully` ném `EOFException`. Buffer đích có thể đã được điền một phần; không được coi nó là một header hoàn chỉnh. Đây là khác biệt giữa “đọc tối đa” và “đọc đủ chính xác”.

## 3. Ghi một phần: OutputStream không trả số byte đã ghi

`OutputStream.write(byte[], off, len)` yêu cầu ghi các byte đã chỉ định nhưng không trả về số byte thực tế. Nếu phương thức ném `IOException`, một phần dữ liệu có thể đã được ghi ra đích trước khi lỗi xảy ra.

Điều này đặc biệt quan trọng với file, socket và output stream có buffer:

- Ghi thành công không đồng nghĩa dữ liệu đã được ứng dụng phía bên kia xử lý.
- `flush()` đẩy dữ liệu đang đệm xuống tầng output bên dưới theo hợp đồng của stream, nhưng không chứng minh peer đã nhận hoặc dữ liệu đã được lưu bền vững trên thiết bị.
- `close()` kết thúc việc sử dụng stream và thường flush buffer của các wrapper có buffering.
- Nếu ghi lỗi giữa chừng, không có số byte tổng quát để ứng dụng biết chính xác phần nào đã đến đích.

Ví dụ, nếu gửi một thông điệp dài 100 byte và `write` ném lỗi sau khi một phần đã được gửi, gọi lại `write` với toàn bộ 100 byte có thể gửi lặp phần đầu. Với giao thức mạng, cần có framing, sequence number, acknowledgment hoặc cơ chế idempotency để xác định phần nào đã được xử lý.

Với file cần thay thế nguyên vẹn, một mẫu an toàn là ghi vào file tạm, flush/đóng thành công rồi mới di chuyển file tạm đến tên đích. Có thể dùng `Files.move` với `StandardCopyOption.ATOMIC_MOVE` khi filesystem hỗ trợ; nếu không hỗ trợ, cần xác định chiến lược fallback phù hợp. Khi cần đảm bảo dữ liệu file được đẩy xuống thiết bị lưu trữ, xem xét `FileChannel.force(...)`; `flush()` đơn thuần không cam kết điều đó.

## 4. Channel có thể báo chính xác tiến độ từng lần gọi

NIO channel khác với `OutputStream`: `ReadableByteChannel.read(ByteBuffer)` và `WritableByteChannel.write(ByteBuffer)` trả về số byte đã đọc/ghi trong lần gọi.

- Số dương: số byte đã chuyển.
- `-1` từ thao tác đọc: EOF.
- `0`: không có byte nào được chuyển trong lần gọi đó. Điều này có thể xảy ra với non-blocking channel; thao tác ghi cũng có thể trả 0 khi chưa thể ghi thêm.
- Với `ByteBuffer`, vị trí (`position`) được cập nhật theo số byte đã chuyển.

Do đó, khi ghi một buffer qua channel, phải tiếp tục cho đến khi `hasRemaining()` là false nếu mục tiêu là gửi hết dữ liệu:

```java
ByteBuffer buffer = ByteBuffer.wrap(payload);

while (buffer.hasRemaining()) {
    int written = channel.write(buffer);
    if (written == 0) {
        // Non-blocking channel: chờ readiness bằng Selector
        // rồi thử lại; tránh vòng lặp bận (busy loop).
    }
}
```

Đoạn trên minh họa logic. Với channel blocking thông thường, lời gọi thường chờ để có tiến độ hoặc lỗi. Với non-blocking channel, không nên lặp liên tục khi nhận 0; đăng ký `OP_WRITE` với `Selector`, chờ channel sẵn sàng rồi tiếp tục.

Đọc từ channel cũng phải lặp nếu cần đủ dữ liệu:

```java
ByteBuffer buffer = ByteBuffer.allocate(4096);

while (true) {
    int count = channel.read(buffer);
    if (count == -1) {
        break; // EOF
    }
    if (count == 0) {
        // Non-blocking channel: chờ OP_READ.
        continue;
    }
    // buffer.position() đã tăng thêm count.
}
```

Trong mã thực tế, phần xử lý `count == 0` cần phối hợp với cơ chế readiness của channel non-blocking; ví dụ không được biến thành busy loop.

## 5. Ngoại lệ I/O và dữ liệu đã chuyển một phần

`IOException` là lớp ngoại lệ checked tổng quát cho lỗi I/O. Nên bắt ngoại lệ cụ thể khi ứng dụng có cách xử lý khác nhau cho từng tình huống; nếu không, để lỗi truyền lên tầng có đủ ngữ cảnh để quyết định retry, báo lỗi hoặc rollback.

| Ngoại lệ | Tình huống thường gặp | Cách suy nghĩ khi xử lý |
|---|---|---|
| `EOFException` | Đọc đủ bản ghi nhưng nguồn kết thúc sớm | Bản ghi chưa hoàn chỉnh; không dùng dữ liệu thiếu như dữ liệu hợp lệ |
| `NoSuchFileException` | Đường dẫn không tồn tại trong NIO | Kiểm tra đường dẫn, tên file và thời điểm file được tạo |
| `AccessDeniedException` | Không có quyền truy cập | Kiểm tra quyền và cấu hình môi trường; không retry liên tục |
| `ClosedChannelException` | Thao tác trên channel đã đóng | Kiểm tra quyền sở hữu và vòng đời channel |
| `SocketTimeoutException` | Socket hết thời gian chờ; đây là subclass của `InterruptedIOException` | Quyết định timeout là lỗi tạm thời hay hết hạn nghiệp vụ; không mặc định dữ liệu chưa được gửi |
| `InterruptedIOException` | I/O bị gián đoạn | Trường `bytesTransferred` có thể cho biết số byte đã chuyển trước khi bị gián đoạn |

Không phải mọi `IOException` đều chứa thông tin tiến độ. `InterruptedIOException.bytesTransferred` chỉ có ý nghĩa với loại ngoại lệ đó và implementation liên quan; không thể suy ra số byte đã chuyển cho mọi lỗi I/O.

Lỗi cũng không tự động có nghĩa stream đã đóng hoặc có thể tiếp tục dùng an toàn. Hãy đọc hợp đồng của API cụ thể. Với socket, timeout khi đọc thường không chứng minh peer đã đóng kết nối; timeout khi ghi cũng không chứng minh peer chưa nhận dữ liệu. Với file, một lỗi giữa lúc ghi có thể để lại file đích chưa hoàn chỉnh.

### Retry phải dựa trên khả năng xác định tiến độ

Không retry mù quáng toàn bộ thao tác sau một lỗi:

- Với channel, dùng số byte trả về và vị trí `ByteBuffer` để tiếp tục phần còn lại khi channel vẫn ở trạng thái hợp lệ.
- Với `OutputStream`, nếu `write` ném lỗi thì API không trả số byte đã ghi. Cần có chiến lược ở tầng ứng dụng hoặc bỏ output hiện tại và bắt đầu một giao dịch/file mới.
- Với giao thức mạng, dùng message ID, offset, checksum và acknowledgment nếu cần phục hồi sau kết nối bị ngắt.
- Với cập nhật file, ghi ra file tạm và chỉ công bố file mới sau khi toàn bộ nội dung đã ghi thành công.
- Không retry thao tác không idempotent nếu chưa biết lần trước đã thực hiện được bao nhiêu.

## 6. Quản lý vòng đời và try-with-resources

Tài nguyên I/O thường giữ file descriptor, socket hoặc bộ đệm. Hãy xác định rõ thành phần nào sở hữu tài nguyên và đóng nó đúng một lần khi hoàn tất.

```java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(target)) {

    input.transferTo(output);
    output.flush();
}
```

`try-with-resources` tự đóng tài nguyên khi rời khỏi khối, kể cả khi thân khối ném ngoại lệ. Nếu cả thân khối và `close()` cùng lỗi, ngoại lệ từ thân khối là ngoại lệ chính; lỗi khi đóng được gắn vào danh sách suppressed exceptions và có thể xem bằng `getSuppressed()`.

Một số lưu ý:

- Đóng stream ở tầng sở hữu nó; không đóng một stream dùng chung khi thành phần khác vẫn cần sử dụng.
- Không tiếp tục đọc/ghi sau khi đã đóng tài nguyên.
- Không bỏ qua lỗi từ `flush()` hoặc `close()` nếu tính toàn vẹn dữ liệu quan trọng.
- Đừng dùng `available()` thay cho EOF và đừng giả định một lần `read` lấp đầy buffer.
- Với `BufferedInputStream`, `BufferedOutputStream` và các wrapper khác, nhớ rằng dữ liệu có thể còn trong buffer cho đến khi đọc/flush/đóng.

## 7. Ví dụ Java chạy được: đọc từng phần, ghi lỗi và channel ghi từng phần

Chương trình sau mô phỏng ba tình huống có thể xảy ra: input chỉ trả tối đa 3 byte mỗi lần đọc; output thất bại sau khi đã ghi một prefix; channel chỉ nhận tối đa 2 byte trong mỗi lần ghi.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;

public class Main {
    static final class ChunkedInputStream extends ByteArrayInputStream {
        ChunkedInputStream(byte[] data) {
            super(data);
        }

        @Override
        public synchronized int read(byte[] buffer, int offset, int length) {
            return super.read(buffer, offset, Math.min(length, 3));
        }
    }

    static final class FailingOutputStream extends OutputStream {
        private final ByteArrayOutputStream sink = new ByteArrayOutputStream();
        private final int failAfter;

        FailingOutputStream(int failAfter) {
            this.failAfter = failAfter;
        }

        @Override
        public void write(int value) throws IOException {
            if (sink.size() == failAfter) {
                throw new IOException("simulated output failure");
            }
            sink.write(value);
        }

        byte[] writtenBytes() {
            return sink.toByteArray();
        }
    }

    static final class ChunkedChannel implements WritableByteChannel {
        private final ByteArrayOutputStream sink = new ByteArrayOutputStream();
        private boolean open = true;

        @Override
        public int write(ByteBuffer source) throws IOException {
            if (!open) {
                throw new ClosedChannelException();
            }
            int count = Math.min(source.remaining(), 2);
            for (int i = 0; i < count; i++) {
                sink.write(source.get());
            }
            return count;
        }

        @Override
        public boolean isOpen() {
            return open;
        }

        @Override
        public void close() {
            open = false;
        }

        byte[] writtenBytes() {
            return sink.toByteArray();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] source = "ABCDEFGHIJ".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream copied = new ByteArrayOutputStream();
        int readCalls = 0;

        try (InputStream input = new ChunkedInputStream(source)) {
            byte[] buffer = new byte[8];
            int count;
            while ((count = input.read(buffer)) != -1) {
                readCalls++;
                copied.write(buffer, 0, count);
            }
        }
        System.out.println("Copied: " + copied.toString(StandardCharsets.UTF_8));
        System.out.println("Read calls: " + readCalls);

        FailingOutputStream failing = new FailingOutputStream(5);
        try {
            failing.write(source);
        } catch (IOException exception) {
            System.out.println("Output failed after stored bytes: "
                    + failing.writtenBytes().length);
            System.out.println("Stored prefix: "
                    + new String(failing.writtenBytes(), StandardCharsets.UTF_8));
        }

        ChunkedChannel channel = new ChunkedChannel();
        ByteBuffer buffer = ByteBuffer.wrap(source);
        int writeCalls = 0;

        try (channel) {
            while (buffer.hasRemaining()) {
                int written = channel.write(buffer);
                if (written == 0) {
                    throw new IllegalStateException(
                            "No progress; a non-blocking channel needs readiness handling");
                }
                writeCalls++;
            }
        }
        System.out.println("Channel output: "
                + new String(channel.writtenBytes(), StandardCharsets.UTF_8));
        System.out.println("Channel write calls: " + writeCalls);
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 Main.java
java Main
```

Kết quả stdout:

```text
Copied: ABCDEFGHIJ
Read calls: 4
Output failed after stored bytes: 5
Stored prefix: ABCDE
Channel output: ABCDEFGHIJ
Channel write calls: 5
```

Giải thích:

1. `ChunkedInputStream` giới hạn mỗi lần đọc ở tối đa 3 byte. Buffer có 8 byte nhưng chương trình vẫn phải lặp cho đến khi nhận `-1`; vì vậy có bốn lần đọc để lấy đủ 10 byte và xác nhận EOF.
2. Vòng lặp chỉ ghi `count` byte vào `ByteArrayOutputStream`. Nó không ghi cả 8 byte của buffer ở mỗi lượt.
3. `FailingOutputStream` mô phỏng output nhận được 5 byte rồi ném `IOException`. Ví dụ biết prefix dài 5 vì implementation mô phỏng tự lưu số byte; `OutputStream` nói chung không cung cấp số byte đã ghi khi `write` ném lỗi.
4. `ChunkedChannel` nhận tối đa 2 byte mỗi lần. `WritableByteChannel.write` trả số byte thực tế và cập nhật `ByteBuffer.position`, nên vòng lặp có thể tiếp tục cho đến khi buffer hết dữ liệu.
5. Ví dụ channel này luôn có tiến độ. Với non-blocking channel thật, nếu `write` trả 0 thì phải chờ readiness, thường qua `Selector`, thay vì lặp bận.

## 8. Checklist xử lý lỗi I/O

- Vòng lặp đọc có xử lý cả số byte thực tế và EOF `-1` chưa?
- Có dùng `available()` sai mục đích để xác định EOF hoặc kích thước dữ liệu không?
- Khi đọc bản ghi cố định, có kiểm tra đủ số byte trước khi sử dụng không?
- Sau lỗi ghi, ứng dụng có biết tiến độ hay có thể vô tình gửi lặp dữ liệu không?
- Với channel, vòng lặp có kiểm tra `ByteBuffer.hasRemaining()` và xử lý trường hợp trả 0 không?
- Khi gặp timeout hoặc interrupt, có phân biệt lỗi tạm thời với trạng thái kết nối/tài nguyên không?
- Tài nguyên có được đóng bằng `try-with-resources` và lỗi `close()` có được giữ lại không?
- Nếu dữ liệu cần nguyên vẹn, có cơ chế file tạm, checksum, acknowledgment hoặc giao dịch phù hợp không?

I/O là quá trình có thể tiến triển từng phần. Đọc phải dựa trên số byte thực tế và EOF; ghi phải tính đến khả năng đích đã nhận một prefix trước khi lỗi xuất hiện; channel cần lặp theo số byte trả về; và việc phục hồi phải dựa trên hợp đồng của API cùng khả năng xác định tiến độ. Quản lý đúng các trạng thái này giúp tránh mất dữ liệu, xử lý trùng lặp và đóng tài nguyên sai thời điểm.
