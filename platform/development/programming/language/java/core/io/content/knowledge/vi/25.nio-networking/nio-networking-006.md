# Partial read, partial write và lưu trạng thái giữa các lần sẵn sàng trong Java NIO

Một kết nối TCP truyền **dòng byte** liên tục. Một lời gọi `SocketChannel.read(ByteBuffer)` không tương ứng với đúng một thông điệp nghiệp vụ; một lần `write(ByteBuffer)` cũng không đảm bảo toàn bộ thông điệp đã được gửi. Đặc biệt với `SocketChannel` ở chế độ non-blocking và `Selector`, `read()` hoặc `write()` có thể xử lý **một phần dữ liệu**, hoặc trả về `0` mà không phải lỗi.

Bài toán quan trọng là: **sau mỗi lần có sự kiện sẵn sàng, phải giữ nguyên số byte đã nhận, số byte còn cần gửi và trạng thái phân tích thông điệp để lần sẵn sàng tiếp theo tiếp tục đúng chỗ**. Nếu vứt bộ đệm giữa các lần `select()`, chương trình có thể làm mất byte, gửi thiếu thông điệp, ghép sai frame hoặc chạy vòng lặp tốn CPU khi socket chưa thể tiến triển.

## 1. TCP stream không có ranh giới thông điệp

Giả sử client gửi chuỗi UTF-8 `HELLO\n` dài 6 byte. Tại phía server, các lần đọc hợp lệ có thể trông như:

```text
Client write:  [ H E L L O \n ]

Server read #1: [ H E ]
Server read #2: [ L ]
Server read #3: [ L O \n ]
```

Hoặc server có thể đọc cả 6 byte trong một lần. Ngược lại, nếu client gửi hai thông điệp `HELLO\n` và `WORLD\n`, server có thể nhận nhiều byte của cả hai trong cùng một lần đọc.

Các nguyên nhân gồm trạng thái bộ đệm TCP, điều kiện mạng, kích thước `ByteBuffer`, tốc độ xử lý và hệ điều hành. Vì thế **mỗi lần socket báo readable không đại diện cho một thông điệp hoàn chỉnh**.

Ứng dụng phải tự định nghĩa **framing**, chẳng hạn:

- Kết thúc bằng dấu phân cách (`\n` cho dòng văn bản).
- Tiền tố độ dài: bốn byte đầu biểu diễn số byte payload, sau đó đọc đúng lượng byte tương ứng.
- Khung có cấu trúc cố định, nếu giao thức thật sự quy định kích thước không đổi.
- Trình phân tích giao thức riêng có thể nhận nhiều frame hoặc một frame chia thành nhiều phần.

Framing phải được xử lý trên **chuỗi byte liên tục**. Với UTF-8, một ký tự có thể trải qua nhiều lần đọc; không nên `new String(chunk)` rồi giả định từng chunk là văn bản hoàn chỉnh.

## 2. Ý nghĩa chính xác của kết quả `SocketChannel.read`

Đối với một `SocketChannel` có đăng ký `OP_READ`, lời gọi:

```java
int n = socket.read(inputBuffer);
```

có ba loại kết quả cần tách bạch:

| Giá trị | Ý nghĩa | Ứng dụng cần làm gì |
| --- | --- | --- |
| `n > 0` | Có `n` byte được đưa vào vùng còn trống của `inputBuffer` | Giữ dữ liệu đã nhận và thử phân tích frame hoàn chỉnh |
| `n == 0` | Chưa đọc được byte nào trong lời gọi này; điều này bình thường với non-blocking socket hoặc buffer không có chỗ | Không coi là EOF, không spin vô hạn; giữ trạng thái cho lần readiness sau |
| `n == -1` | Phía remote đã kết thúc luồng đọc của kênh (EOF phía nhận) | Quyết định đóng kết nối, xử lý half-close hoặc kiểm tra frame dở dang theo giao thức |

Đọc vào buffer sẽ tăng `inputBuffer.position()` đúng bằng số byte đọc được, **không tự thay đổi `limit()`**. Nếu trước lần gọi buffer đã chứa ba byte chưa xử lý, lần đọc tiếp theo phải tiếp tục ở vị trí sau ba byte đó.

Đoạn minh họa đúng ý tưởng:

```java
// socket: SocketChannel non-blocking; input: ByteBuffer được giữ lâu dài.
int n = socket.read(input);
if (n > 0) {
    input.flip();       // Đọc các byte đã nhận.
    parseFrames(input); // Hàm phân tích frame có thể để lại dữ liệu dở.
    input.compact();    // Dồn byte chưa tiêu thụ về đầu, chuẩn bị đọc thêm.
} else if (n == -1) {
    closeOrHalfClose(socket); // Hàm nghiệp vụ minh họa.
}
```

Hai hàm `parseFrames` và `closeOrHalfClose` là **hàm minh họa chưa định nghĩa**, đoạn này không phải chương trình Java độc lập. Quan trọng nhất: `parseFrames` phải để `position` sau byte cuối đã tiêu thụ; `compact()` giữ nguyên các byte còn lại. Nếu ứng dụng dùng parser lưu trạng thái khác, vẫn phải bảo toàn byte chưa xử lý.

## 3. Partial write và trạng thái `ByteBuffer` còn lại

Ghi non-blocking có quy tắc tương tự:

```java
int n = socket.write(outputBuffer);
```

- Nếu `n > 0`, channel nhận `n` byte từ buffer; `outputBuffer.position()` tăng lên `n`. Các byte đã được kernel nhận vào đường gửi **chưa chắc phía remote đã nhận hoặc xử lý**.
- Nếu `n == 0`, tại thời điểm đó channel không ghi thêm được byte nào (hoặc buffer không còn byte). Với buffer còn dữ liệu, giữ nguyên buffer và chờ sự kiện writable tiếp theo.
- `write(ByteBuffer)` không có hợp đồng "ghi hết `remaining()` trong một lần". Cần xử lý partial write dựa trên giá trị trả về và `buffer.hasRemaining()`.

Ví dụ buffer chứa 5 byte `ABCDE`, các lần ghi có thể là:

```text
Trước ghi:  position=0, limit=5, remaining=5
write #1:  trả 2  -> position=2, remaining=3
write #2:  trả 0  -> position=2, remaining=3
write #3:  trả 3  -> position=5, remaining=0
```

Khi quay lại từ event loop, **không gọi `rewind()` hoặc `flip()` trên output buffer chưa gửi hết**, vì như vậy có thể gửi lại byte đã gửi hoặc đổi sai miền dữ liệu hợp lệ. Giữ buffer với `position` hiện tại cho tới khi `hasRemaining()` là `false`.

Nếu có nhiều frame đang chờ, mỗi kết nối thường giữ **hàng đợi các buffer đầu ra**. Chỉ lấy phần tử đầu ra sau khi buffer đó đã hết byte; sau đó mới chuyển sang frame tiếp theo để giữ đúng thứ tự TCP.

## 4. Vì sao phải lưu trạng thái giữa những lần `select()`?

`Selector` giúp một luồng theo dõi nhiều `SelectableChannel` bằng các `SelectionKey`. Với socket không chặn:

1. Đăng ký `OP_READ` khi muốn nhận dữ liệu.
2. Khi `select()` báo khóa có `isReadable()`, thử đọc và cập nhật input buffer.
3. Nếu thông điệp đã hoàn chỉnh, chuẩn bị response thành output buffer và đăng ký `OP_WRITE` khi còn byte cần gửi.
4. Khi khóa có `isWritable()`, thử ghi phần còn lại; nếu chưa hết, giữ `OP_WRITE`.
5. Khi output buffer đã hết byte, **bỏ `OP_WRITE`** để tránh selected liên tục vì socket thường xuyên writable, dù không còn dữ liệu cần gửi.

Tính chất readiness là **gợi ý về khả năng thao tác**, không phải bảo đảm read/write sẽ xử lý tất cả dữ liệu mong muốn hoặc luôn tiến triển. Ngay cả khi selected key báo ready, `read` hoặc `write` vẫn có thể trả `0`; phải cập nhật trạng thái dựa vào giá trị thật.

### Một cấu trúc trạng thái trên mỗi kết nối

Một mô hình thường dùng là `Session` hoặc `ConnectionState`, được gắn vào `SelectionKey`:

```java
// Đoạn định nghĩa minh họa.
final class ConnectionState {
    final ByteBuffer inbound = ByteBuffer.allocate(8192);
    final java.util.ArrayDeque<ByteBuffer> outgoing =
            new java.util.ArrayDeque<>();
    boolean peerInputClosed;
}
```

Sau khi `channel.register(selector, SelectionKey.OP_READ, state)`, có thể lấy lại state qua `(ConnectionState) key.attachment()`. **Không tạo lại `ByteBuffer` ở mỗi vòng selector**: buffer mới sẽ không còn các byte chưa đủ tạo frame từ lượt trước.

State có thể phải chứa thêm số byte payload đang đợi, trạng thái parser, charset decoder, deadline, bộ đếm giới hạn, trạng thái half-close và các giao thức request/response đang chạy.

## 5. `flip()`, `compact()` và dữ liệu nhận dở

Giả sử ứng dụng nhận một frame kết thúc bằng `\n`, nhưng lần đọc thứ nhất chỉ nhận `HEL`:

```text
Buffer sau read #1:
[ H E L _ _ _ _ _ ]  position=3, limit=8
flip():
[ H E L _ _ _ _ _ ]  position=0, limit=3
parser: chưa có '\n', không tiêu thụ byte
compact():
[ H E L _ _ _ _ _ ]  position=3, limit=8

read #2 thêm "LO\n":
[ H E L L O \n _ _ ] position=6, limit=8
flip() -> parser nhận đủ "HELLO\n".
compact() -> position=0, limit=8 nếu đã tiêu thụ hết.
```

Nếu buffer có `ONE\nTWO`, parser nên lấy frame `ONE\n`, giữ lại `TWO` bằng `compact()` và chờ `\n` còn thiếu. Nếu buffer có `ONE\nTWO\n`, parser phải có thể trả ra **hai frame trong cùng lần phân tích**.

Cần phân biệt:

- `flip()`: chuyển từ chế độ ghi dữ liệu vào buffer sang chế độ đọc dữ liệu đã ghi.
- `clear()`: đặt position=0, limit=capacity, **không giữ riêng vùng byte chưa xử lý** và không xóa byte thật.
- `compact()`: giữ byte còn lại trong vùng `position..limit`, dồn về đầu buffer và đặt lại trạng thái để tiếp tục nhận.

Nếu parser đã tiêu thụ toàn bộ byte, `compact()` có kết quả position=0 giống trạng thái sẵn sàng ghi mới. Nếu còn phần frame dở, `compact()` mới bảo vệ nó.

### Khi buffer đầu vào đầy mà vẫn chưa có frame

Nếu `inbound.remaining()==0` trong chế độ ghi nhưng parser chưa hoàn thành frame, ứng dụng không thể tiếp tục nhận thêm byte vào buffer cũ. Cần chính sách rõ ràng: giới hạn kích thước frame, mở rộng buffer tới hạn mức hợp lệ hoặc từ chối thông điệp quá lớn. Đừng cứ gọi `read()` vào buffer đầy rồi spin với kết quả 0.

## 6. Chương trình Java 17+ hoàn chỉnh: một kết nối TCP, nhiều lượt readiness

Ví dụ sau dùng TCP loopback để kết quả có thể chạy độc lập. Client gửi một frame ASCII `PING\n`, server xử lý bằng `SocketChannel` non-blocking và `Selector`. Để **minh họa chắc chắn** việc lưu trạng thái, mỗi lần xử lý readable chỉ cho phép đọc tối đa **2 byte**, mỗi lần writable chỉ cho phép ghi tối đa **2 byte**, bằng cách tạm hạ `ByteBuffer.limit()`. Đây là giới hạn do ví dụ đặt ra để buộc có nhiều bước xử lý; trong ứng dụng thật các lần read/write có thể ngắn hơn do mạng hoặc thiết bị.

Tạo file **`PartialIoSelectorDemo.java`**:

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public final class PartialIoSelectorDemo {
    private static final byte[] REQUEST =
            "PING\n".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] RESPONSE =
            "ACK:PING\n".getBytes(StandardCharsets.US_ASCII);

    private PartialIoSelectorDemo() {}

    private static final class Session {
        final ByteBuffer inbound = ByteBuffer.allocate(32);
        ByteBuffer outbound;
        int readFragments;
        int writeFragments;
        boolean done;
    }

    public static void main(String[] args) throws IOException {
        try (ServerSocketChannel listener = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open();
             Selector selector = Selector.open()) {

            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            client.connect(listener.getLocalAddress());

            try (SocketChannel accepted = listener.accept()) {
                accepted.configureBlocking(false);
                Session session = new Session();
                accepted.register(selector, SelectionKey.OP_READ, session);

                // Client sử dụng blocking mode để gửi một request nhỏ.
                writeAll(client, ByteBuffer.wrap(REQUEST));

                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (!session.done) {
                    if (System.nanoTime() >= deadline) {
                        throw new IOException("Timed out waiting for I/O");
                    }

                    if (selector.select(100) == 0) {
                        continue;
                    }

                    Iterator<SelectionKey> it =
                            selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();
                        if (!key.isValid()) {
                            continue;
                        }

                        Session state = (Session) key.attachment();
                        if (key.isReadable()) {
                            readOneFragment(key, state);
                        }
                        if (key.isValid() && key.isWritable()) {
                            writeOneFragment(key, state);
                        }
                    }
                }

                ByteBuffer reply = ByteBuffer.allocate(RESPONSE.length);
                while (reply.hasRemaining()) {
                    int n = client.read(reply);
                    if (n < 0) {
                        throw new EOFException("Reply truncated");
                    }
                    if (n == 0) {
                        throw new IOException("No client read progress");
                    }
                }
                reply.flip();

                System.out.println("request=PING");
                System.out.println("reply="
                        + StandardCharsets.US_ASCII.decode(reply)
                                .toString().strip());
                System.out.println("read fragments >=3: "
                        + (session.readFragments >= 3));
                System.out.println("write fragments >=5: "
                        + (session.writeFragments >= 5));
            }
        }
    }

    private static void readOneFragment(SelectionKey key, Session state)
            throws IOException {
        SocketChannel socket = (SocketChannel) key.channel();

        if (!state.inbound.hasRemaining()) {
            throw new IOException("Request exceeds input capacity");
        }

        int oldLimit = state.inbound.limit();
        int cap = Math.min(2, state.inbound.remaining());
        state.inbound.limit(state.inbound.position() + cap);

        int n;
        try {
            n = socket.read(state.inbound);
        } finally {
            state.inbound.limit(oldLimit);
        }

        if (n < 0) {
            throw new EOFException("Peer closed before request completed");
        }
        if (n == 0) {
            return; // Đợi readability tiếp theo, giữ nguyên position.
        }

        state.readFragments++;
        int written = state.inbound.position();
        if (state.inbound.get(written - 1) != (byte) '\n') {
            return; // Frame chưa đủ, giữ byte đã nhận trong inbound.
        }

        state.inbound.flip();
        byte[] frame = new byte[state.inbound.remaining()];
        state.inbound.get(frame);
        if (!Arrays.equals(frame, REQUEST)) {
            throw new IOException("Unexpected request");
        }

        state.outbound = ByteBuffer.wrap(RESPONSE);
        key.interestOps(SelectionKey.OP_WRITE);
    }

    private static void writeOneFragment(SelectionKey key, Session state)
            throws IOException {
        SocketChannel socket = (SocketChannel) key.channel();
        ByteBuffer out = state.outbound;
        if (out == null) {
            throw new IOException("No outbound frame");
        }

        int oldLimit = out.limit();
        int cap = Math.min(2, out.remaining());
        out.limit(out.position() + cap);

        int n;
        try {
            n = socket.write(out);
        } finally {
            out.limit(oldLimit);
        }

        if (n > 0) {
            state.writeFragments++;
        }
        if (!out.hasRemaining()) {
            key.interestOps(0); // Không đăng ký OP_WRITE khi hết dữ liệu.
            state.done = true;
        }
        // Nếu n==0 hoặc còn byte: giữ nguyên out.position().
    }

    private static void writeAll(SocketChannel channel, ByteBuffer data)
            throws IOException {
        while (data.hasRemaining()) {
            int n = channel.write(data);
            if (n == 0) {
                throw new IOException("No blocking write progress");
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac PartialIoSelectorDemo.java
java PartialIoSelectorDemo
```

Kết quả khi TCP loopback và selector hoạt động bình thường:

```text
request=PING
reply=ACK:PING
read fragments >=3: true
write fragments >=5: true
```

Các dòng cuối **không giả định số lần đọc/ghi chính xác**. Vì chương trình giới hạn mỗi lần đọc/ghi thành tối đa 2 byte, frame 5 byte cần ít nhất 3 lần nhận byte thành công, frame 9 byte cần ít nhất 5 lần gửi byte thành công. Hệ điều hành có thể khiến số lần nhiều hơn; kết quả so sánh `>=3` và `>=5` vẫn là `true`. Timeout 5 giây chỉ là bảo vệ ví dụ khỏi vòng chờ vô hạn khi môi trường mạng bất thường.

### Trạng thái được giữ ở đâu?

- `Session.inbound` **không được cấp phát lại giữa các readiness**. Sau lượt đọc đầu tiên, position có thể là 2; lần kế tiếp đọc tiếp ở đó cho tới khi gặp byte xuống dòng.
- `Session.outbound` được tạo một lần khi frame request hoàn chỉnh. Sau mỗi lượt writable, `outbound.position()` tăng đúng bằng số byte đã ghi.
- `Session.readFragments`, `writeFragments` và `done` được giữ trong `Session` gắn với `SelectionKey` qua `register(..., session)` và `attachment()`.
- Khi đã nhận request, server đổi interest từ `OP_READ` sang `OP_WRITE`. Khi gửi xong, xóa interest, rồi kết thúc ví dụ.
- Hai lần tạm giảm `limit()` được khôi phục trong `finally`, bảo toàn capacity và giới hạn ban đầu của buffer.
- Ví dụ cố ý chỉ nhận **một frame ASCII xác định** và không hỗ trợ pipeline nhiều request; đây là giới hạn của giao thức demo. Server thực tế phải phân tích nhiều frame trong một buffer, giữ frame dở bằng `compact()` hoặc state parser và xử lý EOF/half-close.

Chương trình không cần chạy thêm server bên ngoài; hai đầu kết nối được tạo trong một process trên loopback. Với socket non-blocking, việc `select()` báo ready không được hiểu là một frame đầy đủ. Ví dụ chứng minh phần byte đang chờ sống qua nhiều lần readiness.

## 7. Thiết kế parser thông điệp có tiền tố độ dài

Giao thức dùng newline phù hợp minh họa nhưng không thích hợp cho mọi loại binary payload. Với frame gồm **4 byte độ dài** (big-endian) và tiếp theo là `length` byte payload, parser cần giữ hai giai đoạn:

1. `READ_LENGTH`: đọc đủ 4 byte; nếu mới có 1–3 byte thì giữ lại, chưa giải mã độ dài.
2. `READ_PAYLOAD`: sau khi giải mã length và kiểm tra hạn mức, tiếp tục gom đủ payload; sau khi hoàn thành có thể chuyển lại `READ_LENGTH` để nhận frame kế tiếp.

Có thể dùng hai buffer riêng:

```java
// Phác thảo state machine, các biến được lưu trên mỗi connection.
ByteBuffer lengthBytes = ByteBuffer.allocate(4);
ByteBuffer payload = null;

// Trong READ_LENGTH: nạp lengthBytes cho đến khi !hasRemaining().
if (!lengthBytes.hasRemaining()) {
    lengthBytes.flip();
    int length = lengthBytes.getInt(); // BIG_ENDIAN theo mặc định.
    if (length < 0 || length > MAX_FRAME_BYTES) {
        throw new IOException("Invalid frame length");
    }
    payload = ByteBuffer.allocate(length);
    lengthBytes.clear();
    // Chuyển state sang READ_PAYLOAD.
}
```

Đây là **đoạn phác thảo**, chưa định nghĩa `MAX_FRAME_BYTES`, trạng thái, hành vi gom byte hay thao tác xử lý payload; không phải chương trình biên dịch độc lập. Cần bảo đảm không đánh mất byte khi trong một `read` vừa đủ header vừa xuất hiện một phần payload. Không tạo buffer theo length khi chưa xác minh giới hạn, và nên kiểm tra cả tổng bộ nhớ đang dùng của nhiều kết nối.

Nếu frame có length 0, chính sách giao thức phải quyết định đó là frame rỗng hợp lệ hay lỗi; nếu hợp lệ, parser cần hoàn tất ngay mà không chờ `read` thêm byte vào buffer có remaining=0.

## 8. Điều khiển `OP_WRITE` và backpressure

Một sai lầm thường gặp là ngay khi tạo connection đã đăng ký:

```java
channel.register(selector, SelectionKey.OP_READ | SelectionKey.OP_WRITE);
```

Nếu không có dữ liệu chờ gửi, nhiều socket vẫn thường writable và selector có thể trả readiness liên tục. Event loop sẽ thức dậy vô ích, làm CPU tăng cao.

Chính sách phổ biến:

- **Không có dữ liệu chờ gửi:** chỉ quan tâm `OP_READ` (cùng các bit interest khác nếu giao thức cần).
- **Có dữ liệu gửi còn lại:** thêm `OP_WRITE` để có cơ hội hoàn thành khi socket nhận thêm byte.
- **Hàng đợi gửi đã rỗng:** bỏ `OP_WRITE` ngay.
- **Hàng đợi output vượt ngưỡng:** áp dụng backpressure: tạm giảm/loại `OP_READ` cho kết nối, từ chối thêm request, giới hạn bộ nhớ hoặc đóng kết nối theo chính sách dịch vụ.

Thay đổi bit interest phải **giữ những bit cần thiết khác**. Ví dụ nếu đang quan tâm read:

```java
// Phác thảo: key còn valid và thao tác do event-loop owner thực hiện.
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
// Khi queue đã rỗng:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

Nếu thread khác thêm dữ liệu vào outbound queue, cần phối hợp việc thay đổi `interestOps` và có thể gọi `selector.wakeup()` để thread event loop không đợi hết timeout trước khi xử lý. Không cho nhiều thread cùng sửa `ByteBuffer.position`, queue và key mà không có nguyên tắc sở hữu/đồng bộ nhất quán.

### Khi một kết nối rất bận

Không nên một callback đọc/ghi không giới hạn byte đến khi cạn socket, vì có thể khiến các kết nối khác bị đói tài nguyên (starvation). Đặt hạn mức công việc theo lượt, ví dụ tối đa một số byte, frame hoặc thời gian, rồi quay lại xử lý những key khác. Giới hạn 2 byte trong ví dụ là để quan sát partial I/O; trong hệ thống thật chọn ngưỡng dựa trên benchmark và mục tiêu latency/throughput.

## 9. EOF, half-close, timeout và đóng tài nguyên

`read() == -1` báo remote đã đóng hướng gửi (hoặc socket đã tới EOF phía đọc). Với TCP, có tình huống **half-close**: peer đã gọi `shutdownOutput()` nhưng vẫn có thể nhận dữ liệu theo hướng ngược lại. Ứng dụng không nên mặc định phải vứt ngay hàng đợi output trong mọi giao thức; chính sách phụ thuộc request đã nhận, response cần gửi và cách phát hiện kết thúc kết nối.

Khi EOF đến giữa frame:

- Nếu giao thức đòi frame hoàn chỉnh, báo lỗi frame không đầy đủ.
- Nếu giao thức dùng EOF làm dấu kết thúc thông điệp, xử lý theo quy ước đó, tránh lẫn với framing length-prefix/newline.
- Nếu còn output cần gửi, có thể giữ connection cho tới khi đã gửi hoặc hết deadline, nếu giao thức và trạng thái socket cho phép.

Khi đóng một channel có đăng ký selector, selection key liên quan sẽ bị hủy; nên loại bỏ key khỏi các cấu trúc dữ liệu và giải phóng những reference tới state/buffer. Đối với lỗi I/O, timeout hoặc protocol violation, đóng có kiểm soát, tránh giữ một queue buffer vĩnh viễn.

Một connection state hoàn chỉnh thường cần cả read timeout, write timeout, maximum frame size, maximum pending bytes và idle timeout. Readiness không tự đưa ra giới hạn nào trong số đó.

## 10. Ghi nhận trạng thái để debug partial I/O

Khi chẩn đoán, ghi log theo **số byte thực xử lý** thay vì theo giả định về một lần readiness:

| Trường | Mục đích |
| --- | --- |
| `readResult` | Số byte thực đọc, 0 hoặc -1 |
| `input.position/limit/capacity` | Lượng byte đã nhận và còn chỗ |
| `parserState` | Đang đợi header, payload, delimiter hay xử lý request |
| `writeResult` | Số byte channel thực chấp nhận |
| `output.remaining` | Tổng byte của buffer hiện tại còn phải gửi |
| `pendingQueueBytes` | Áp lực bộ nhớ đầu ra của kết nối |
| `key.interestOps/readyOps` | Đang quan tâm điều gì, selector vừa báo điều gì |
| Thời điểm nhận/gửi cuối | Phục vụ timeout và giám sát tiến độ |

Không log toàn bộ payload nếu chứa bí mật hoặc dữ liệu cá nhân; tập trung vào metadata, số byte và định danh kết nối phù hợp.

## 11. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Mỗi `read()` được xem là một thông điệp hoàn chỉnh | Tách sai frame hoặc ghép nhầm hai frame | Có framing và parser duy trì state |
| Nhận `0` rồi coi là EOF | Đóng kết nối hợp lệ quá sớm | Chỉ `-1` biểu thị EOF với `read` |
| Đọc được vài byte rồi tạo input buffer mới tại readiness tiếp theo | Mất header/payload còn dở | Giữ buffer trong connection state |
| Sau `write` chưa hết buffer lại `flip/rewind` | Gửi trùng byte hoặc sai ranh giới dữ liệu | Giữ `position` tới khi `hasRemaining()==false` |
| Gọi `clear()` khi parser còn byte chưa dùng | Vứt dữ liệu frame dở | `compact()` hoặc dùng parser state riêng |
| Không bỏ `OP_WRITE` khi queue rỗng | Vòng `select()` thức dậy liên tục, tốn CPU | Chỉ quan tâm write khi còn pending output |
| Loop khi `read/write` trả 0 | Busy-loop, không nhường thời gian cho các kết nối khác | Chờ readiness tiếp theo, dùng selector |
| Xử lý một key rất lâu hoặc không giới hạn output queue | Starvation, tăng memory/latency | Byte budget mỗi lượt và backpressure |
| Giải mã UTF-8 riêng từng chunk | Lỗi ký tự nhiều byte bị cắt ngang | Decode trên byte đã đủ frame hoặc dùng `CharsetDecoder` lưu state |
| `read()==-1` nhưng không kiểm tra frame dở | Chấp nhận thông điệp thiếu byte | Quy tắc xử lý EOF và frame chưa hoàn thành |
| Thay đổi `interestOps` từ thread khác nhưng không wakeup/phối hợp | Chậm hoặc bỏ lỡ tiến độ cho đến lần selector thức dậy tiếp | Một event-loop owner, queue an toàn và `selector.wakeup()` |

**Ghi nhớ:** Với Java NIO non-blocking, mỗi lần `OP_READ` hoặc `OP_WRITE` sẵn sàng chỉ là một *cơ hội* xử lý dữ liệu. **Luôn dựa vào số byte thật sự đọc/ghi, giữ buffer và parser state qua nhiều lần `select()`, đăng ký `OP_WRITE` khi còn dữ liệu gửi, và loại bỏ nó khi hoàn tất**. Đó là nền tảng để một server dùng selector xử lý TCP stream chính xác và hiệu quả.