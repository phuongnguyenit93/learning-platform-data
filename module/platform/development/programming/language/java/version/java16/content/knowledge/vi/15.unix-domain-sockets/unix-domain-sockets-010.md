# Xử lý partial read, partial write và ByteBuffer trong giao thức

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Unix-domain socket. Java 16 chuẩn hóa Unix-domain socket channels trong NIO, cho phép ứng dụng giao tiếp qua địa chỉ socket trên hệ thống tệp bằng `UnixDomainSocketAddress`, `ServerSocketChannel` và `SocketChannel`. Các channel này truyền dữ liệu theo dạng byte stream: một lần đọc có thể chỉ nhận một phần header hoặc payload, còn một lần ghi có thể chỉ gửi được một phần buffer. Bài học hướng dẫn xây dựng framing cho giao thức, xử lý partial read/write với `ByteBuffer` ở chế độ blocking và non-blocking, phát hiện EOF giữa frame và kiểm chứng dữ liệu trước khi chuyển cho tầng ứng dụng.

## Mục tiêu

Sau bài học, bạn có thể:

- Mở server và client Unix-domain socket bằng API chuẩn từ Java 16.
- Hiểu vì sao ranh giới của lần gọi read/write không phải ranh giới message.
- Thiết kế giao thức có header độ dài và giới hạn kích thước frame.
- Dùng vòng lặp để đọc đủ header/payload và ghi hết frame ở chế độ blocking.
- Duy trì trạng thái đọc khi channel non-blocking chỉ nhận được một phần dữ liệu.
- Dùng `flip()`, `clear()` và `compact()` đúng theo trạng thái buffer.
- Quản lý hàng đợi ghi và `OP_WRITE` để không làm mất phần dữ liệu chưa gửi.
- Phân biệt EOF sạch với kết nối bị đóng giữa header hoặc payload.
- Kiểm thử các trường hợp phân mảnh, gộp frame, dữ liệu sai và giới hạn tài nguyên.

## 1. Unix-domain SocketChannel là byte stream

Java 16 bổ sung hỗ trợ Unix-domain socket cho các channel stream của NIO. Server mở channel với `StandardProtocolFamily.UNIX`, bind tới một địa chỉ file-system và accept kết nối. Client mở `SocketChannel` cùng protocol family rồi connect tới địa chỉ đó.

Ví dụ phần khởi tạo server:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;

Path directory = Files.createTempDirectory("uds-demo-");
Path socketPath = directory.resolve("orders.sock");

try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
    server.bind(UnixDomainSocketAddress.of(socketPath));

    try (SocketChannel connection = server.accept()) {
        // Đọc và ghi dữ liệu qua connection.
    }
} finally {
    Files.deleteIfExists(socketPath);
    Files.deleteIfExists(directory);
}
```

Client kết nối tới cùng địa chỉ:

```java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

Path socketPath = Path.of("/path/to/private-directory/orders.sock");

try (SocketChannel channel =
             SocketChannel.open(StandardProtocolFamily.UNIX)) {
    channel.connect(UnixDomainSocketAddress.of(socketPath));
    // Gửi request và nhận response.
}
```

Các ví dụ này dùng API chuẩn của Java 16 trở lên. Khả năng mở Unix-domain socket phụ thuộc hệ điều hành và provider NIO; nếu nền tảng không hỗ trợ, việc mở channel có thể thất bại. Địa chỉ là đường dẫn socket trên hệ thống tệp, vì vậy quyền truy cập thư mục, quyền socket, giới hạn độ dài đường dẫn và việc dọn socket file cũ đều thuộc trách nhiệm triển khai.

Chỉ xóa socket path mà ứng dụng sở hữu trong thư mục riêng. Không xóa tùy tiện một đường dẫn đã tồn tại vì có thể đó là socket của tiến trình khác.

### 1.1. Stream không giữ ranh giới message

Unix-domain `SocketChannel` có semantics stream giống socket TCP. Giả sử ứng dụng gửi hai frame:

```text
[HEADER A][PAYLOAD A][HEADER B][PAYLOAD B]
```

Bên nhận không được đảm bảo một lần `read()` sẽ trả về đúng một frame. Một lần đọc có thể nhận:

- Chỉ một phần header.
- Header đầy đủ nhưng payload mới có vài byte.
- Phần còn lại của payload.
- Một frame đầy đủ và một phần frame tiếp theo.
- Nhiều frame nối liền trong cùng một lần đọc.

Tương tự, một lần `write()` có thể gửi ít byte hơn số byte còn lại trong buffer. Vì thế, ứng dụng cần tự định nghĩa ranh giới message và duy trì trạng thái phần dữ liệu chưa đọc hoặc chưa ghi.

Không được viết logic kiểu “mỗi lần read là một request”. Điều đó có thể hoạt động trong một số lần chạy thử nhưng không phải hợp đồng của stream channel.

## 2. Định nghĩa framing cho giao thức

Một cách phổ biến là dùng length-prefixed frame: header có độ dài cố định cho biết payload dài bao nhiêu byte.

Trong bài này, giao thức dùng header 4 byte big-endian:

```text
+----------------------+---------------------------+
| Length: 4 bytes      | Payload: Length bytes     |
+----------------------+---------------------------+
| Big-endian int       | UTF-8 hoặc binary payload |
+----------------------+---------------------------+
```

Ví dụ payload UTF-8 là `HELLO` có 5 byte:

```text
00 00 00 05 48 45 4C 4C 4F
|-----------| |-----------|
  length=5       payload
```

Header có độ dài byte, không phải số ký tự. Với UTF-8, một ký tự có thể chiếm nhiều byte; không tính length bằng `String.length()`.

Giao thức cần quy định rõ:

- Kích thước header và byte order.
- Đơn vị của length: byte hay ký tự.
- Kích thước frame tối đa.
- Cách xử lý length âm hoặc vượt giới hạn.
- Encoding của payload nếu payload là văn bản.
- Hành vi khi peer đóng kết nối giữa frame.
- Quy tắc phiên bản, loại message hoặc correlation ID nếu ứng dụng cần.

Ví dụ này dùng giới hạn 1 MiB để minh họa. Ứng dụng phải chọn giới hạn phù hợp với tài nguyên và giao thức thực tế.

### 2.1. Kiểm tra length trước khi cấp phát

Không cấp phát buffer trực tiếp theo một length chưa được xác thực từ peer. Nếu header khai báo vài gigabyte, việc cấp phát ngay có thể làm cạn heap.

Quy tắc tối thiểu:

```java
private static final int HEADER_BYTES = Integer.BYTES;
private static final int MAX_FRAME_BYTES = 1024 * 1024;

static void validateLength(int length) throws IOException {
    if (length < 0 || length > MAX_FRAME_BYTES) {
        throw new IOException("Invalid frame length: " + length);
    }
}
```

Một giao thức có thể dùng unsigned length hoặc header nhiều trường, nhưng phải thống nhất cách diễn giải ở cả hai phía. Ví dụ này dùng signed 32-bit integer và từ chối số âm.

## 3. Tạo và gửi frame ở chế độ blocking

Khi gửi frame, ghi length trước rồi ghi payload vào cùng một `ByteBuffer`. Sau đó gọi `flip()` để chuyển buffer từ write mode sang read mode trước khi gửi.

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.SocketChannel;

final class BlockingFrameWriter {
    private static final int MAX_FRAME_BYTES = 1024 * 1024;

    static void writeFrame(SocketChannel channel, byte[] payload)
            throws IOException {
        if (!channel.isBlocking()) {
            throw new IllegalArgumentException(
                    "This method requires a blocking channel");
        }
        if (payload.length > MAX_FRAME_BYTES) {
            throw new IOException("Frame is too large");
        }

        ByteBuffer frame = ByteBuffer
                .allocate(Integer.BYTES + payload.length)
                .order(ByteOrder.BIG_ENDIAN);

        frame.putInt(payload.length);
        frame.put(payload);
        frame.flip();

        while (frame.hasRemaining()) {
            channel.write(frame);
        }
    }
}
```

Điểm quan trọng là vòng lặp `while (frame.hasRemaining())`. Một lần `write()` không nhất thiết tiêu thụ toàn bộ buffer. Mỗi lần ghi thành công, position của buffer tăng theo số byte đã gửi. Vòng lặp tiếp tục từ position mới cho đến khi frame được gửi hết.

Không gọi `clear()` giữa các lần ghi. `clear()` sẽ đặt position về 0 và khiến dữ liệu đã gửi bị gửi lại. Cũng không gọi `flip()` lặp lại trong vòng lặp vì điều đó có thể làm thay đổi vùng byte còn lại cần gửi.

### 3.1. Vì sao blocking vẫn có partial write?

Blocking mode có nghĩa thao tác có thể chờ khi channel chưa sẵn sàng. Nó không có nghĩa một lần ghi luôn gửi hết toàn bộ buffer. Socket có thể chỉ nhận một phần dữ liệu trong lần gọi hiện tại, nên caller vẫn phải kiểm tra `hasRemaining()` và tiếp tục ghi.

Với buffer không rỗng trên blocking `SocketChannel`, thao tác thường chờ đến khi ít nhất một byte được ghi hoặc phát sinh lỗi. Nếu channel được cấu hình non-blocking, `write()` có thể trả về 0; khi đó không được dùng vòng lặp blocking này vì có thể tạo busy loop.

## 4. Đọc đủ header và payload ở chế độ blocking

Một frame có hai phần cần đọc đủ: header 4 byte và payload theo length trong header. Phương thức `readFully` tiếp tục đọc cho đến khi buffer đầy hoặc kết nối kết thúc.

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.SocketChannel;

final class BlockingFrameReader {
    private static final int MAX_FRAME_BYTES = 1024 * 1024;

    static byte[] readFrame(SocketChannel channel) throws IOException {
        if (!channel.isBlocking()) {
            throw new IllegalArgumentException(
                    "This method requires a blocking channel");
        }

        ByteBuffer header = ByteBuffer
                .allocate(Integer.BYTES)
                .order(ByteOrder.BIG_ENDIAN);

        // EOF trước byte đầu tiên của header là kết thúc stream sạch.
        if (!readFully(channel, header, true)) {
            return null;
        }

        header.flip();
        int length = header.getInt();

        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("Invalid frame length: " + length);
        }

        ByteBuffer body = ByteBuffer.allocate(length);
        readFully(channel, body, false);

        return body.array();
    }

    private static boolean readFully(
            SocketChannel channel,
            ByteBuffer target,
            boolean allowCleanEof
    ) throws IOException {
        int totalRead = 0;

        while (target.hasRemaining()) {
            int count = channel.read(target);

            if (count == -1) {
                if (allowCleanEof && totalRead == 0) {
                    return false;
                }
                throw new EOFException("Connection closed inside a frame");
            }

            totalRead += count;
        }

        return true;
    }
}
```

`readFully()` không giả định một lần đọc đủ số byte. Ví dụ header 4 byte có thể được nhận qua bốn lần đọc, mỗi lần một byte. Payload 100 byte cũng có thể đến thành nhiều phần.

Phương thức trả về `null` chỉ khi peer đóng kết nối trước khi gửi bất kỳ byte nào của header mới. Nếu đã nhận một phần header rồi EOF, hoặc header hoàn chỉnh nhưng payload chưa đủ rồi EOF, đó là frame bị cắt cụt và phải được báo lỗi.

Payload có length bằng 0 là hợp lệ trong ví dụ này: `ByteBuffer.allocate(0)` không còn byte cần đọc, nên kết quả là mảng rỗng.

### 4.1. Chuyển payload thành văn bản

Chỉ giải mã văn bản sau khi đã nhận đủ payload. Một ký tự UTF-8 có thể bị chia giữa hai lần `read()`. Nếu decode từng mảnh độc lập, byte cuối của mảnh đầu có thể là byte mở đầu của một ký tự nhiều byte và bị xử lý sai.

```java
import java.nio.charset.StandardCharsets;

byte[] payload = BlockingFrameReader.readFrame(channel);

if (payload != null) {
    String message = new String(payload, StandardCharsets.UTF_8);
}
```

`new String` dùng hành vi thay thế cho chuỗi byte UTF-8 không hợp lệ. Nếu giao thức yêu cầu từ chối văn bản sai encoding, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` thay vì âm thầm thay byte lỗi.

## 5. Luồng blocking hoàn chỉnh ở phía client

Client có thể dùng `SocketChannel` ở blocking mode mặc định. Nó gửi một frame và đọc một frame phản hồi:

```java
import java.io.EOFException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

Path socketPath = Path.of("/tmp/orders.sock");

try (SocketChannel channel =
             SocketChannel.open(StandardProtocolFamily.UNIX)) {
    channel.connect(UnixDomainSocketAddress.of(socketPath));

    byte[] request = "CREATE ORDER".getBytes(StandardCharsets.UTF_8);
    BlockingFrameWriter.writeFrame(channel, request);

    byte[] response = BlockingFrameReader.readFrame(channel);
    if (response == null) {
        throw new EOFException("Server closed without a response");
    }

    System.out.println(new String(response, StandardCharsets.UTF_8));
}
```

Phần server có thể gọi `BlockingFrameReader.readFrame()` trong vòng lặp để xử lý nhiều frame trên cùng kết nối. Khi client đóng kết nối sạch giữa hai frame, phương thức trả về `null` và server kết thúc vòng lặp.

Nếu server chỉ gọi `read()` một lần sau `accept()`, nó có thể nhận một phần header rồi xử lý thiếu dữ liệu. Hãy để logic framing chịu trách nhiệm lắp ráp message.

## 6. Non-blocking: giữ trạng thái giữa các lần readiness

Trong non-blocking mode, `read()` và `write()` có thể trả về 0 khi hiện tại không có byte nào được chuyển. Selector thông báo khi channel có thể đọc hoặc ghi; nó không đảm bảo toàn bộ frame đã sẵn sàng.

Mỗi kết nối cần giữ trạng thái riêng:

- Buffer header và vị trí đã nhận.
- Length của frame hiện tại.
- Buffer payload và số byte đã nhận.
- Hàng đợi frame đang chờ gửi.
- Buffer đang được ghi và position hiện tại.

Không tạo lại buffer header hoặc payload mỗi lần `OP_READ` xảy ra. Nếu làm vậy, phần byte đã nhận ở lần trước sẽ bị mất.

### 6.1. State cho một kết nối

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayDeque;
import java.util.Queue;

final class ConnectionState {
    final ByteBuffer header = ByteBuffer
            .allocate(Integer.BYTES)
            .order(ByteOrder.BIG_ENDIAN);

    ByteBuffer body;

    final Queue<ByteBuffer> outbound = new ArrayDeque<>();
}
```

Header và body được giữ ở write mode trong lúc nhận. Position cho biết số byte đã tích lũy; khi buffer đầy, gọi `flip()` để đọc giá trị hoặc payload.

### 6.2. Đọc nhiều frame mà vẫn giữ phần chưa đủ

Method dưới đây được gọi khi selector báo `OP_READ`. Nó đọc cho đến khi channel trả về 0, xử lý mọi frame hoàn chỉnh và giữ phần frame chưa đủ trong state.

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.SocketChannel;
import java.util.function.Consumer;

final class NonBlockingFrameReader {
    private static final int MAX_FRAME_BYTES = 1024 * 1024;

    static void readAvailable(
            SocketChannel channel,
            SelectionKey key,
            ConnectionState state,
            Consumer<byte[]> onFrame
    ) throws IOException {
        while (true) {
            ByteBuffer target =
                    state.body == null ? state.header : state.body;

            int count = channel.read(target);

            if (count == -1) {
                boolean partialFrame =
                        state.body != null || state.header.position() != 0;

                if (partialFrame) {
                    throw new EOFException(
                            "Connection closed inside a frame");
                }

                key.cancel();
                channel.close();
                return;
            }

            if (count == 0) {
                return; // Chờ lần OP_READ tiếp theo.
            }

            if (state.body == null && !state.header.hasRemaining()) {
                state.header.flip();
                int length = state.header.getInt();
                state.header.clear();

                if (length < 0 || length > MAX_FRAME_BYTES) {
                    throw new IOException("Invalid frame length: " + length);
                }

                if (length == 0) {
                    onFrame.accept(new byte[0]);
                } else {
                    state.body = ByteBuffer.allocate(length);
                }

                continue;
            }

            if (state.body != null && !state.body.hasRemaining()) {
                state.body.flip();

                byte[] payload = new byte[state.body.remaining()];
                state.body.get(payload);
                state.body = null;

                onFrame.accept(payload);
            }
        }
    }
}
```

Method có thể đọc một phần header rồi trả về khi `read()` trả 0. Lần `OP_READ` sau tiếp tục ghi vào chính buffer header đó. Khi header đầy, code đọc length, kiểm tra giới hạn và chuyển sang buffer body. Khi body đầy, code phát frame hoàn chỉnh rồi quay lại đọc header frame tiếp theo.

Vòng lặp cũng xử lý trường hợp nhiều frame đã nằm sẵn trong socket receive buffer: sau khi phát frame đầu, nó tiếp tục đọc frame kế tiếp cho đến khi `read()` trả 0.

Nếu peer đóng kết nối khi header hoặc body còn dang dở, code ném `EOFException`. Nếu EOF xảy ra đúng giữa hai frame, state không có byte dang dở và kết nối được đóng sạch.

### 6.3. Selector và đăng ký OP_READ

Khi chấp nhận một kết nối non-blocking, cấu hình channel trước khi đăng ký selector:

```java
channel.configureBlocking(false);

ConnectionState state = new ConnectionState();
SelectionKey key = channel.register(
        selector,
        SelectionKey.OP_READ,
        state
);
```

Khi key readable, lấy state từ attachment và gọi `readAvailable`. Không chia sẻ cùng một `ConnectionState` cho nhiều kết nối; mỗi channel có header, body và outbound queue riêng.

Nếu callback `onFrame` thực hiện xử lý lâu, hãy cân nhắc chuyển công việc nghiệp vụ sang executor để không chặn event loop. Việc cập nhật key interest set và queue phải tuân theo mô hình thread ownership đã chọn cho selector.

## 7. Non-blocking write: giữ phần buffer chưa gửi

Với non-blocking channel, `write()` có thể gửi một phần hoặc trả về 0. Sau lần gọi, position của buffer phản ánh byte đã được gửi. Không bỏ buffer cho đến khi `hasRemaining()` trả false.

Khi enqueue một frame, tạo buffer hoàn chỉnh ở read mode:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.SelectionKey;

final class NonBlockingFrameWriter {
    private static final int MAX_FRAME_BYTES = 1024 * 1024;

    static void enqueue(
            SelectionKey key,
            ConnectionState state,
            byte[] payload
    ) throws IOException {
        if (payload.length > MAX_FRAME_BYTES) {
            throw new IOException("Frame is too large");
        }

        ByteBuffer frame = ByteBuffer
                .allocate(Integer.BYTES + payload.length)
                .order(ByteOrder.BIG_ENDIAN);

        frame.putInt(payload.length);
        frame.put(payload);
        frame.flip();

        state.outbound.add(frame);
        key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
    }
}
```

Khi selector báo `OP_WRITE`, ghi từ buffer đầu hàng đợi:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.SocketChannel;

final class NonBlockingFrameFlusher {
    static void flush(
            SocketChannel channel,
            SelectionKey key,
            ConnectionState state
    ) throws IOException {
        while (!state.outbound.isEmpty()) {
            ByteBuffer current = state.outbound.peek();

            channel.write(current);

            if (current.hasRemaining()) {
                break; // Partial write hoặc write trả về 0.
            }

            state.outbound.remove();
        }

        if (state.outbound.isEmpty()) {
            key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
        } else {
            key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
        }
    }
}
```

Nếu buffer đầu queue còn remaining sau lần `write()`, giữ nguyên buffer và chờ lần `OP_WRITE` tiếp theo. Nếu buffer đã cạn, bỏ nó và tiếp tục frame kế tiếp.

Chỉ đăng ký `OP_WRITE` khi thực sự có dữ liệu chờ gửi. Socket thường xuyên writable; nếu luôn bật `OP_WRITE`, selector có thể liên tục đánh thức event loop dù không có gì cần gửi.

Khi queue rỗng, bỏ `OP_WRITE` khỏi interest set. Khi enqueue frame mới, bật lại interest này.

### 7.1. Event loop tối thiểu

Phần xử lý key thường có dạng:

```java
if (key.isReadable()) {
    NonBlockingFrameReader.readAvailable(
            channel,
            key,
            state,
            payload -> handleFrame(payload)
    );
}

if (key.isValid() && key.isWritable()) {
    NonBlockingFrameFlusher.flush(channel, key, state);
}
```

`handleFrame` là xử lý nghiệp vụ của ứng dụng. Nếu callback thêm response vào queue, gọi `NonBlockingFrameWriter.enqueue()` để bật `OP_WRITE`. Trong ứng dụng nhiều thread, không cập nhật `interestOps` tùy tiện từ thread khác; dùng cơ chế điều phối về selector thread hoặc `wakeup()` theo kiến trúc đã chọn.

## 8. flip, compact và buffer tích lũy

Các ví dụ state machine ở trên dùng một buffer cho header và một buffer cho payload. Cách khác là dùng một buffer tích lũy cho toàn bộ byte đến. Khi đó `flip()` chuyển sang đọc, parser lấy các frame hoàn chỉnh và `compact()` giữ phần đuôi chưa đủ.

Chu trình:

```text
Read mode (đọc dữ liệu từ channel)
        |
        v
flip() -> parse complete frames
        |
        v
Giữ lại byte của frame chưa hoàn chỉnh
        |
        v
compact()
        |
        v
Write mode (đón thêm byte)
```

Ví dụ logic parser cho một buffer đã flip:

```java
input.flip();

while (input.remaining() >= Integer.BYTES) {
    input.mark();

    int length = input.getInt();
    validateLength(length);

    if (input.remaining() < length) {
        input.reset(); // Giữ nguyên cả header để parse lại lần sau.
        break;
    }

    byte[] payload = new byte[length];
    input.get(payload);
    handleFrame(payload);
}

input.compact();
```

Nếu chưa đủ 4 byte header, vòng lặp không đọc gì và `compact()` giữ toàn bộ byte. Nếu header đủ nhưng payload chưa đủ, `reset()` quay lại vị trí trước header; `compact()` giữ cả header lẫn phần payload đã nhận để lần sau parse lại.

Buffer tích lũy phải có khả năng chứa frame lớn nhất cộng header. Nếu không, một frame hợp lệ lớn hơn capacity có thể lấp đầy buffer trong khi parser vẫn chưa có đủ dữ liệu để xử lý. Khi đó cần tăng dung lượng có kiểm soát hoặc dùng state machine tách header/body như phần trước.

### 8.1. Không gọi clear khi cần giữ phần dang dở

`clear()` đặt position về 0 và limit bằng capacity. Nó không giữ lại ranh giới phần dữ liệu chưa xử lý. Nếu parser đã nhận một phần payload rồi gọi `clear()`, các byte đó sẽ bị bỏ khỏi trạng thái logic và frame không thể được lắp ráp chính xác.

Dùng `compact()` khi cần giữ byte còn lại ở đầu buffer để ghi thêm dữ liệu phía sau. Dùng `clear()` chỉ khi mọi byte hiện có đã được xử lý hoặc cố ý loại bỏ.

## 9. EOF, timeout và lỗi giao thức

EOF có ý nghĩa khác nhau tùy vị trí xảy ra:

| Thời điểm EOF | Diễn giải |
|---|---|
| Trước byte đầu tiên của header mới | Peer đóng kết nối giữa các frame; kết thúc sạch |
| Sau một phần header | Frame bị cắt cụt; giao thức không hoàn chỉnh |
| Sau header nhưng trước khi đủ payload | Frame bị cắt cụt; giao thức không hoàn chỉnh |
| Sau payload hoàn chỉnh | Frame đã nhận đủ; lần đọc tiếp theo có thể trả EOF sạch |

Không chờ vô hạn nếu giao thức yêu cầu thời gian phản hồi. Blocking channel có thể đợi lâu khi peer ngừng gửi giữa header và payload. Ứng dụng cần timeout ở tầng giao thức, cơ chế quản lý deadline hoặc chuyển sang non-blocking selector để áp dụng thời hạn cho từng kết nối/frame.

Với non-blocking mode, nếu một frame đã bắt đầu nhưng không hoàn tất trong thời hạn quy định, đóng kết nối hoặc áp dụng chính sách phục hồi được giao thức định nghĩa. Không giữ buffer dang dở vô thời hạn vì mỗi kết nối có thể chiếm bộ nhớ.

### 9.1. Xử lý length không hợp lệ

Khi length âm hoặc vượt `MAX_FRAME_BYTES`, từ chối frame ngay sau khi đọc header. Không cố cấp phát payload, không tiếp tục diễn giải byte tiếp theo như một frame mới vì stream đã mất đồng bộ.

Các lựa chọn thường là đóng kết nối và ghi log lỗi giao thức. Không phản hồi bằng cách cấp phát buffer lớn hơn giới hạn chỉ vì peer yêu cầu.

### 9.2. Phân biệt lỗi I/O với lỗi payload

`IOException` có thể xuất hiện khi socket bị đóng, quyền truy cập bị từ chối hoặc lỗi hệ thống xảy ra. Lỗi giao thức có thể do header sai, length không hợp lệ hoặc EOF giữa frame. Lỗi decode có thể do payload không phải UTF-8 hợp lệ.

Giữ các lớp lỗi riêng biệt giúp logging và phản hồi phù hợp. Không nên biến mọi lỗi thành một payload rỗng vì điều đó làm mất thông tin nguyên nhân và có thể che giấu lỗi giao thức.

## 10. Kiểm thử partial read/write có chủ đích

Partial I/O phụ thuộc trạng thái socket và lịch chạy, nên test tích hợp chỉ gửi một payload nhỏ có thể không tái hiện được tình huống phân mảnh. Hãy kiểm thử parser và writer với các mảnh dữ liệu được điều khiển, sau đó bổ sung test tích hợp qua socket thật.

Một số trường hợp cần có:

- Header đến thành 1 + 3 byte.
- Payload đến thành nhiều mảnh.
- Hai frame đến liền nhau trong một lần đọc.
- Header đầy đủ nhưng payload chưa đủ.
- EOF giữa header.
- EOF giữa payload.
- Length âm hoặc vượt giới hạn.
- Write chỉ tiêu thụ một phần buffer.
- Non-blocking write trả về 0 và queue vẫn giữ nguyên phần còn lại.

### 10.1. Kiểm thử parser theo mảnh

Nếu dùng state machine, có thể tách logic nhận byte khỏi `SocketChannel` để test deterministic. Mỗi lần test đưa một mảnh byte vào state rồi gọi parser. Ví dụ giao thức frame có header length 5 và payload `HELLO`:

```text
Lần 1: 00
Lần 2: 00 00 05 48
Lần 3: 45 4C
Lần 4: 4C 4F
Kết quả: một payload HELLO sau lần 4
```

Parser không được phát frame ở lần 1, 2 hoặc 3. Nó chỉ phát frame sau khi nhận đủ 4 byte header và 5 byte payload.

Với buffer tích lũy, test cần kiểm tra rằng `compact()` giữ đúng các byte chưa xử lý. Với state machine header/body, test cần kiểm tra position của buffer tương ứng được giữ qua các lần gọi.

### 10.2. Kiểm thử writer với buffer giả lập

Có thể tách việc xếp frame khỏi thao tác channel để kiểm tra trạng thái buffer. Trong test tích hợp, dùng socket channel thật và payload đủ lớn để có cơ hội partial write, nhưng không dựa vào giả định rằng hệ điều hành chắc chắn sẽ trả partial write trong mọi lần chạy.

Nếu muốn kiểm tra deterministic việc queue giữ phần còn lại, trừu tượng hóa thao tác ghi bằng một interface nhỏ hoặc một adapter test có thể giới hạn số byte tiêu thụ mỗi lần. Test phải xác minh position tăng theo byte đã ghi và frame chỉ bị lấy khỏi queue khi buffer hết remaining.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Xem mỗi `read()` là một message | Mất framing khi header/payload bị chia hoặc nhiều frame gộp | Định nghĩa header và parser state |
| Gọi `write()` một lần rồi bỏ buffer | Byte cuối frame có thể chưa được gửi | Lặp đến khi hết ở blocking; giữ queue ở non-blocking |
| Gọi `clear()` sau một partial read | Mất byte đã nhận nhưng chưa đủ frame | Dùng state header/body hoặc `compact()` |
| `flip()` lại ở mỗi lần readiness | Đọc sai vùng byte hoặc bỏ trạng thái | Chỉ flip khi chuyển từ write mode sang read mode |
| Cấp phát theo length chưa kiểm tra | Có thể cạn heap | Kiểm tra length với giới hạn giao thức |
| Decode UTF-8 theo từng mảnh tùy ý | Ký tự nhiều byte có thể bị hỏng | Decode sau khi đủ payload hoặc dùng decoder giữ state |
| Bật `OP_WRITE` liên tục | Selector có thể busy wakeup | Chỉ bật khi outbound queue không rỗng |
| Bỏ frame khỏi queue sau partial write | Mất phần byte chưa gửi | Giữ buffer đến khi `hasRemaining()` false |
| Không phân biệt EOF sạch và EOF giữa frame | Chấp nhận dữ liệu bị cắt cụt | Theo dõi header/body state |
| Dùng một state cho nhiều kết nối | Trộn byte giữa các client | Mỗi channel có state riêng |
| Cho rằng blocking mode đảm bảo full write | Frame có thể bị gửi thiếu | Vẫn lặp theo `hasRemaining()` |
| Cho rằng UNIX socket có mặt trên mọi OS | Ứng dụng có thể không mở được channel | Kiểm tra hỗ trợ của platform/provider |

## 12. Checklist triển khai giao thức

Trước khi đưa Unix-domain socket protocol vào ứng dụng, hãy kiểm tra:

1. Nền tảng chạy có hỗ trợ `StandardProtocolFamily.UNIX` không?
2. Socket path nằm trong thư mục riêng với quyền truy cập phù hợp không?
3. Giao thức có header framing rõ ràng và byte order cố định không?
4. Length được xác thực trước khi cấp phát buffer không?
5. Blocking read có đọc đủ header và payload không?
6. Blocking write có tiếp tục đến khi hết buffer không?
7. Non-blocking state có giữ buffer dang dở giữa các lần readiness không?
8. `flip()`, `compact()` và `clear()` có được dùng đúng trạng thái không?
9. `OP_WRITE` chỉ bật khi còn dữ liệu chờ gửi không?
10. EOF giữa frame có được phát hiện và xử lý như lỗi không?
11. UTF-8 payload có được decode sau khi lắp ráp đầy đủ không?
12. Có test phân mảnh, gộp frame, invalid length và partial write không?
13. Có timeout/deadline và giới hạn bộ nhớ trên mỗi kết nối không?
14. Socket path được dọn an toàn khi server dừng không?

## 13. Bài tập vận dụng

**Bài 1 — Framing:** Thiết kế frame gồm 4 byte length big-endian và payload UTF-8. Viết hàm encode/decode và kiểm tra payload có ký tự tiếng Việt.

**Bài 2 — Blocking I/O:** Hoàn thiện `readFully()` và `writeFrame()`. Kiểm tra EOF trước header, EOF giữa header và EOF giữa payload.

**Bài 3 — Partial read:** Cho header đến thành nhiều mảnh và payload đến thành nhiều mảnh. Viết test chứng minh parser chỉ phát frame khi nhận đủ dữ liệu.

**Bài 4 — Non-blocking write:** Tạo outbound queue, mô phỏng write chỉ gửi một phần buffer. Xác minh frame vẫn nằm trong queue cho đến khi hết remaining và `OP_WRITE` được tắt khi queue rỗng.

**Bài 5 — Gộp frame:** Gửi liên tiếp ba frame trên cùng kết nối. Đảm bảo parser có thể phát cả ba dù chúng đến trong một lần đọc hoặc qua nhiều lần đọc.

---

## Tài liệu tham khảo

- [JEP 380 — Unix-Domain Socket Channels](https://openjdk.org/jeps/380): hỗ trợ Unix-domain socket channels được chuẩn hóa trong Java 16.
- [UnixDomainSocketAddress — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/UnixDomainSocketAddress.html): biểu diễn địa chỉ Unix-domain socket bằng đường dẫn.
- [SocketChannel — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SocketChannel.html): kết nối, đọc/ghi, blocking và non-blocking mode.
- [ByteBuffer — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html): trạng thái buffer, flip, compact và các thao tác byte.
- [SelectionKey — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SelectionKey.html): `OP_READ`, `OP_WRITE` và interest set.
- [SocketChannel — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html): API channel hiện hành và semantics read/write.
- [ByteBuffer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html): API buffer hiện hành.

---

**Ghi nhớ:** Unix-domain `SocketChannel` là byte stream, không phải message queue. Một frame có thể đến qua nhiều lần đọc và một lần đọc có thể chứa nhiều frame. Hãy định nghĩa framing, kiểm tra length, lặp đến khi đủ dữ liệu ở blocking mode, giữ state và outbound queue ở non-blocking mode, đồng thời dùng `flip()`/`compact()` đúng lúc để không làm mất byte chưa xử lý.
