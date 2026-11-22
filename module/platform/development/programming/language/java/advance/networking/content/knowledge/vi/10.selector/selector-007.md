# Lưu trạng thái giao thức và buffer riêng cho từng kết nối với Selector

## 1. Bài toán: một Selector xử lý nhiều kết nối, mỗi kết nối có tiến độ khác nhau

Java NIO cho phép một thread sử dụng `Selector` theo dõi nhiều `SocketChannel`. Cách này tránh phải cấp riêng một thread đang chờ `read()` cho mỗi kết nối, nhưng cũng tạo ra một yêu cầu bắt buộc: **trạng thái giao thức và dữ liệu chưa xử lý phải thuộc về đúng kết nối của nó**.

Giả sử hai client A và B cùng dùng giao thức TCP với mỗi message có header 4 byte biểu diễn payload length:

```text
Client A gửi frame "ALPHA":
  [00 00 00 05][41 4C 50 48 41]
Client B gửi frame "BETA":
  [00 00 00 04][42 45 54 41]

Một lượt xử lý Selector có thể nhìn thấy:
  event #1: A đã nhận 2 byte đầu header
  event #2: B đã nhận 1 byte đầu header
  event #3: A nhận thêm header + 2 byte payload
  event #4: B nhận đủ dữ liệu và hoàn thành "BETA"
  event #5: A nhận đủ dữ liệu và hoàn thành "ALPHA"

Kết quả đúng: BETA hoàn thành trước ALPHA.
Không được ghép header A với payload B.
```

Nếu chương trình tạo **một `ByteBuffer` dùng chung** cho tất cả các channel rồi ghi dữ liệu mới lên byte cũ, parser có thể đọc nhầm dữ liệu của A thành message của B. Nếu chương trình tạo buffer mới mỗi lần có `OP_READ`, phần header/payload còn thiếu từ lần trước sẽ biến mất. Tương tự, nếu lưu một biến `expectedLength` toàn cục, việc đọc header của B có thể ghi đè độ dài đang chờ của A.

**Giải pháp:** mỗi kết nối có một đối tượng `ConnectionState` riêng, gắn với `SelectionKey` của channel đó (hoặc lưu trong bản đồ `SocketChannel → ConnectionState` được quản lý nhất quán). State tồn tại **xuyên nhiều sự kiện readiness/read/write** và được giải phóng khi kết nối kết thúc.

Sau bài này, bạn cần:
- Giải thích đúng quan hệ `Selector` → `SelectionKey` → `SocketChannel` → `ConnectionState`.
- Lưu riêng **inbound buffer, outbound queue, trạng thái parser, cờ handshake, timeout, quota** theo từng kết nối.
- Ghép và phân tích frame TCP qua nhiều lần `read` mà không mất, lặp hoặc trộn byte giữa các client.
- Dùng `SelectionKey.attach()/attachment()` cùng `OP_READ`/`OP_WRITE` đúng cách.
- Dọn state khi EOF, lỗi, hủy key hoặc đóng channel; bảo vệ server trước slow client và memory growth.

## 2. Selector theo dõi readiness, không tự hiểu giao thức

`Selector` cho phép một luồng event loop hỏi hệ điều hành xem các channel đã đăng ký đang sẵn sàng cho những nhóm thao tác nào. Với Java 17, các loại interest/ready thường gặp:

| Thao tác | Đối tượng chủ yếu | Ý nghĩa |
| --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | Có thể nhận một kết nối tới listener |
| `SelectionKey.OP_CONNECT` | `SocketChannel` | Kết nối nonblocking có thể hoàn tất hoặc báo lỗi; gọi `finishConnect()` |
| `SelectionKey.OP_READ` | `SocketChannel` | Có thể đọc dữ liệu, nhận EOF hoặc gặp lỗi; **chưa hứa có đủ một message** |
| `SelectionKey.OP_WRITE` | `SocketChannel` | Có khả năng ghi ít nhất một phần, nhưng không hứa ghi hết queue |

`key.isReadable()` là **tín hiệu readiness**, không phải câu trả lời “có một frame đầy đủ”. Parser phải căn cứ vào **byte đã nhận + quy tắc frame**. `SocketChannel.read(ByteBuffer)` trong nonblocking mode có thể trả `0`, trả số byte dương nhưng ít hơn kỳ vọng, hoặc `-1` nếu đã tới EOF.

`SelectionKey` là biểu diễn của **một đăng ký channel với một Selector**. Nó có:
- `channel()`: channel đang được theo dõi.
- `selector()`: selector quản lý đăng ký.
- `interestOps()`: thao tác **muốn theo dõi**.
- `readyOps()` và `isReadable()`/`isWritable()`: thao tác **được báo sẵn sàng** tại lần select.
- `attachment()`: **một đối tượng tuỳ ý của ứng dụng** gắn với key.
- `isValid()` và `cancel()`: kiểm tra/huỷ đăng ký.

Một `SelectionKey` **không tự lưu buffer ứng dụng** hoặc giải mã protocol. Những thứ đó do chương trình định nghĩa trong attachment.

## 3. Mô hình sở hữu state cho mỗi kết nối

Một kiến trúc rõ ràng:

```text
                        ┌────────────────────────────┐
                        │ Selector + event loop     │
                        └──────────────┬─────────────┘
                                       │
               ┌───────────────────────┼────────────────────────┐
               ▼                       ▼                        ▼
        Key của listener         Key A / Socket A        Key B / Socket B
        OP_ACCEPT                OP_READ, OP_WRITE       OP_READ
        attachment: null         attachment: State A     attachment: State B
                                 ┌──────────────────┐    ┌──────────────────┐
                                 │ inbound A        │    │ inbound B        │
                                 │ pending frames A │    │ pending frames B │
                                 │ outbound queue A │    │ outbound queue B │
                                 │ protocol phase A │    │ protocol phase B │
                                 │ quota/deadline A │    │ quota/deadline B │
                                 └──────────────────┘    └──────────────────┘

Dữ liệu của A chỉ chảy vào State A; dữ liệu của B chỉ chảy vào State B.
```

Một lớp state điển hình có thể có:

| Trường | Tác dụng | Ghi chú ownership |
| --- | --- | --- |
| `ByteBuffer inbound` | Tích lũy byte TCP chưa phân tích hết | Mỗi connection một buffer hoặc một accumulator sở hữu riêng |
| `Deque<ByteBuffer> outbound` | Những response/byte còn chờ được ghi ra socket | Mỗi channel một queue; giữ `position` khi partial write |
| `int expectedPayloadBytes` | Độ dài frame đã parse từ header khi dùng state machine | Không phải global; reset theo frame |
| `ProtocolPhase phase` | Ví dụ chờ handshake, active, closing | Thay đổi theo trình tự giao thức của **connection đó** |
| `long lastActivityNanos` | Phát hiện idle/slow connection | Đo thời gian cùng nguồn clock monotonic |
| `int queuedBytes` | Áp quota và backpressure | Cập nhật khi queue/flush |
| `String requestId` hoặc stream map | Theo dõi yêu cầu hoặc logical stream trong một kết nối | Nếu protocol multiplex nhiều stream, state còn có tầng con |

Không nhất thiết dùng đủ mọi trường. Với ví dụ length-prefix nhỏ, một `ByteBuffer inbound` và số frame đã xử lý đủ minh họa. Với giao thức nhiều bước (TLS, authentication, WebSocket, RPC), state còn phải biểu diễn các bước handshake, fragment, outstanding request, timeout và hàng đợi ghi.

**Quy tắc ranh giới:** một đối tượng connection state thuộc về **một connection** và còn sống tới khi close/cleanup. Không dùng một instance cho nhiều client chỉ vì cùng protocol.

## 4. Gắn state vào SelectionKey

Khi listener chấp nhận một client:

```java
SocketChannel accepted = listener.accept();
if (accepted != null) {
    accepted.configureBlocking(false);
    ConnectionState state = new ConnectionState(nextConnectionId++);
    accepted.register(selector, SelectionKey.OP_READ, state);
}
```

Đây là **mảnh code minh họa**; `listener` đã được đặt nonblocking, `selector` là event loop selector, `nextConnectionId` là bộ sinh ID và `ConnectionState` là class ứng dụng. `register(selector, ops, attachment)` tạo/thiết lập đăng ký cùng attachment. Nếu server socket nonblocking có nhiều connection chờ accept, thường lặp `accept()` tới khi trả `null`.

Khi có read event:

```java
if (key.isValid() && key.isReadable()) {
    SocketChannel channel = (SocketChannel) key.channel();
    ConnectionState state = (ConnectionState) key.attachment();
    int n = channel.read(state.inbound);
    if (n > 0) {
        parseAvailableFrames(state);
    } else if (n == -1) {
        finishOrRejectPendingFrame(state);
        closeConnection(key);
    }
}
```

Đây là **mảnh code minh họa**; ba phương thức xử lý và class state do ứng dụng định nghĩa. Điểm cốt lõi là **lấy state từ chính key được thông báo**, không dựa vào biến “client hiện tại” toàn cục.

`key.attach(state)` cũng dùng được khi đăng ký trước rồi gắn state sau. Mỗi key có đúng **một attachment slot**; muốn lưu nhiều trường thì gói thành một đối tượng. Gắn một object mới bằng `attach(other)` thay attachment cũ; vì vậy đừng vô tình thay thế state đang giữ buffer dở.

Ngoài attachment, có thể dùng `Map<SocketChannel, ConnectionState>`; cần map theo identity của channel hoặc khóa connection phù hợp, quản lý concurrency và dọn entry khi close. Attachment thường ít phải tra cứu thêm vì callback đã có `SelectionKey`. **Không** cho rằng attachment tự động được persist giữa các lần chạy ứng dụng hay có thể chia sẻ an toàn giữa nhiều thread.

## 5. Ranh giới event không phải ranh giới message

Với TCP, một `read` có thể trả:
- 2 byte đầu của header 4 byte.
- Header hoàn chỉnh nhưng mới có một phần payload.
- Một frame hoàn chỉnh và 3 byte đầu header tiếp theo.
- Nhiều frame hoàn chỉnh.
- 0 byte (đặc biệt khi nonblocking).
- `-1` khi đã EOF.

Không tình huống nào cho phép kết luận “mỗi OP_READ = một request”. Ví dụ wire format có 4-byte big-endian length:

```text
Client A: [00 00]                             (header còn thiếu 2)
Client B: [00]                                (header còn thiếu 3)
Client A: [00 05 41 4C]                       (header A đủ, payload A mới "AL")
Client B: [00 00 04 42 45 54 41]             (B đã đủ "BETA")
Client A: [50 48 41]                         (A đã đủ "ALPHA")
```

Khi A còn pending, event loop có thể xử lý hàng trăm event từ B hoặc client khác. Vì vậy:
- **Pending header** của A phải giữ ở A.
- **Expected length** của A phải giữ ở A.
- **Pending payload** của A phải giữ ở A.
- **Byte response chờ ghi** của A phải giữ ở A.

Không thể chỉ tạo `ByteBuffer` tại đầu callback rồi bỏ ở cuối nếu giao thức cho phép frame bị chia. Một buffer mới có thể dùng làm I/O scratch chung nếu **trước khi tái sử dụng** đã chuyển và giữ chính xác mọi byte chưa xử lý vào state riêng của connection; nhưng mẫu này cần ownership rõ và copy đúng kích thước.

## 6. ByteBuffer: flip, compact và byte chưa xử lý

Một `ByteBuffer` dùng làm accumulator thường tồn tại ở **write mode** ngoài parser:

```text
Trước read:
[byte pending][khoảng trống để ghi tiếp]
position = số byte pending; limit = capacity

SocketChannel.read(buffer):
[byte pending][byte mới vừa nhận][vùng trống]
position tăng theo số byte mới

flip():
[byte có thể parse ở read mode][vùng nằm ngoài limit]
position = 0; limit = tổng byte pending + mới

Parser tiêu thụ hết các frame hoàn chỉnh:
[byte đã xử lý][header/payload dở]
             ▲ position

compact():
[header/payload dở][vùng trống để đọc thêm]
position = số byte còn dở; limit = capacity
```

Các phương thức:
- `flip()` đưa buffer từ write mode sang read mode bằng cách đặt `limit = position; position = 0`.
- `compact()` copy các byte trong `[position, limit)` về đầu rồi chuẩn bị ghi tiếp, **giữ đúng phần chưa tiêu thụ**.
- `clear()` chỉ reset position/limit, **không giữ an toàn phần frame dở** để đọc tiếp.
- `mark()` và `reset()` hữu ích khi đọc header rồi phát hiện payload chưa đủ: reset lại vị trí **đầu header** trước khi compact.
- `remaining()` cho biết số byte còn khả dụng theo mode hiện tại, không phải số frame hoặc số byte trên wire còn đang được gửi.
- `capacity()` là dung lượng buffer, không phải độ dài request. Không decode/parse byte nằm ngoài `[position, limit)` ở read mode.

### Cẩn thận khi header đã đọc nhưng body chưa đủ

```text
Buffer ở read mode:
[00 00 00 05][48 45]
[length = 5]   "HE" (thiếu "LLO")
```

Nếu parser gọi `getInt()` thì position đã vượt qua 4 byte header. Khi thấy `remaining() < 5`, nó phải `reset()` về **đầu header** trước `compact()`. Nếu không, lần read sau chỉ còn `HE...` và parser sẽ hiểu sai đó là header mới. Một lựa chọn khác là state machine lưu `expectedLength = 5` và chuyển sang giai đoạn `READ_BODY`; khi đó không cần giữ header trong buffer nhưng phải bảo quản expected length theo đúng connection.

Ví dụ đoạn parse trong read mode:

```java
while (buffer.remaining() >= Integer.BYTES) {
    buffer.mark();               // đầu frame
    int length = buffer.getInt();
    if (length < 0 || length > MAX_PAYLOAD) {
        throw new IOException("Invalid frame length");
    }
    if (buffer.remaining() < length) {
        buffer.reset();          // giữ header + payload dở
        break;
    }
    byte[] payload = new byte[length];
    buffer.get(payload);
    dispatchFrame(payload);
}
buffer.compact();
```

**Đây là mảnh code**, phụ thuộc các biến `buffer`, `MAX_PAYLOAD` và hàm `dispatchFrame`. `while` cần thiết vì một lần read có thể chứa **nhiều** frame hoàn chỉnh. Parser phải xử lý tới khi chỉ còn byte dở, không chờ một read event mới cho byte vốn đã nằm trong buffer.

## 7. Dữ liệu riêng của connection A và B diễn biến thế nào?

Giả sử mọi frame đều có header 4 byte, và A/B đều được gắn state riêng với buffer ban đầu rỗng. Khi event loop xử lý, ta có bảng:

| Event | State A sau parse/compact | State B sau parse/compact | Message hoàn tất |
| --- | --- | --- | --- |
| A nhận `00 00` | 2 byte header A | Trống | Chưa có |
| B nhận `00` | Giữ 2 byte A | 1 byte header B | Chưa có |
| A nhận `00 05 41 4C` | 4 byte header + 2 byte payload `AL` | Giữ 1 byte B | Chưa có |
| B nhận `00 00 04 42 45 54 41` | A vẫn pending | B parse `BETA`, pending rỗng | BETA |
| A nhận `50 48 41` | A parse `ALPHA`, pending rỗng | B vẫn rỗng | ALPHA |

Đây là một **lịch sự kiện giả định hợp lệ**; TCP/network không đảm bảo thứ tự giữa các socket khác nhau. Điều quan trọng là **thứ tự byte trên *từng* socket** vẫn được bảo toàn, và state không bị trộn giữa các socket.

Một thiết kế lỗi:

```java
// Sai: một buffer nhận cho mọi client, không giữ riêng pending state
static final ByteBuffer sharedInbound = ByteBuffer.allocate(4096);
// Sai: độ dài đang chờ của A bị B ghi đè
static int expectedLength = -1;
```

Ngay cả khi event loop chạy **một thread**, shared mutable state vẫn sai logic: read event B có thể chen giữa hai read event A. “Chỉ một thread” loại bỏ một số data race nhưng **không loại bỏ sự xen kẽ hợp lệ giữa nhiều connection**.

## 8. Java 17+ runnable: Selector và hai connection có frame bị chia

Chương trình sau tạo listener TCP trên loopback `127.0.0.1`, đăng ký `OP_ACCEPT`, chấp nhận hai client theo thứ tự A rồi B, gắn **một `ConnectionState` riêng** vào `SelectionKey` của từng channel và cho hai client gửi các phần của frame đan xen.

Giao thức thử nghiệm:
- 4 byte `int` big-endian mô tả payload length.
- Payload UTF-8, giới hạn `MAX_PAYLOAD = 32` byte.
- Mỗi client gửi đúng **một frame** để có thể kiểm thử invariant đơn giản lúc EOF.

Khi parser thấy header đủ nhưng payload thiếu, nó dùng `mark()/reset()` để giữ nguyên frame dở; `compact()` chuyển phần dở về đầu của **buffer gắn với connection đó**. Chương trình cố ý gửi B hoàn tất trước A để nhìn rõ không có sự pha trộn hai buffer.

Lưu vào đúng file `SelectorStateDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
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
import java.util.Iterator;

public class SelectorStateDemo {
    private static final int MAX_PAYLOAD = 32;
    private static int nextId;
    private static int messages;
    private static int closed;

    static final class ConnectionState {
        final int id;
        final ByteBuffer inbound = ByteBuffer.allocate(4 + MAX_PAYLOAD);
        int frames;
        ConnectionState(int id) { this.id = id; }
    }

    private static byte[] frame(String text) throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(payload.length);
            out.write(payload);
        }
        return bytes.toByteArray();
    }

    private static void sendPart(SocketChannel channel, byte[] wire,
                                 int start, int end) throws IOException {
        ByteBuffer part = ByteBuffer.wrap(wire, start, end - start);
        while (part.hasRemaining()) channel.write(part);
    }

    private static void parse(ConnectionState state) throws IOException {
        ByteBuffer buffer = state.inbound;
        buffer.flip();
        while (buffer.remaining() >= Integer.BYTES) {
            buffer.mark();
            int length = buffer.getInt();
            if (length < 0 || length > MAX_PAYLOAD) {
                throw new IOException("Invalid length: " + length);
            }
            if (buffer.remaining() < length) {
                buffer.reset();
                break;
            }
            byte[] payload = new byte[length];
            buffer.get(payload);
            state.frames++;
            messages++;
            System.out.println("connection " + state.id + ": "
                    + new String(payload, StandardCharsets.UTF_8));
        }
        buffer.compact();
    }

    private static void service(Selector selector) throws IOException {
        if (selector.select(2000) == 0) {
            throw new IOException("Timed out waiting for channel event");
        }
        Iterator<SelectionKey> selected = selector.selectedKeys().iterator();
        while (selected.hasNext()) {
            SelectionKey key = selected.next();
            selected.remove();
            if (!key.isValid()) continue;
            if (key.isAcceptable()) {
                ServerSocketChannel listener = (ServerSocketChannel) key.channel();
                SocketChannel accepted;
                while ((accepted = listener.accept()) != null) {
                    accepted.configureBlocking(false);
                    accepted.register(selector, SelectionKey.OP_READ,
                            new ConnectionState(++nextId));
                }
            } else if (key.isReadable()) {
                SocketChannel channel = (SocketChannel) key.channel();
                ConnectionState state = (ConnectionState) key.attachment();
                int n = channel.read(state.inbound);
                if (n == -1) {
                    if (state.inbound.position() != 0) {
                        throw new EOFException("Partial frame on connection " + state.id);
                    }
                    if (state.frames != 1) {
                        throw new IOException("Expected one frame on connection " + state.id);
                    }
                    closed++;
                    key.cancel();
                    channel.close();
                } else if (n > 0) {
                    parse(state);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.configureBlocking(false);
            listener.bind(new InetSocketAddress(loopback, 0));
            listener.register(selector, SelectionKey.OP_ACCEPT);
            int port = ((InetSocketAddress) listener.getLocalAddress()).getPort();
            try (SocketChannel a = SocketChannel.open(
                         new InetSocketAddress(loopback, port))) {
                service(selector); // accept A, connection 1
                try (SocketChannel b = SocketChannel.open(
                             new InetSocketAddress(loopback, port))) {
                    service(selector); // accept B, connection 2
                    byte[] aFrame = frame("ALPHA");
                    byte[] bFrame = frame("BETA");
                    sendPart(a, aFrame, 0, 2); // partial A header
                    service(selector);
                    sendPart(b, bFrame, 0, 1); // partial B header
                    service(selector);
                    sendPart(a, aFrame, 2, 6); // A header + 2 body bytes
                    service(selector);
                    sendPart(b, bFrame, 1, bFrame.length); // B complete
                    service(selector);
                    sendPart(a, aFrame, 6, aFrame.length); // A complete
                    service(selector);
                    a.shutdownOutput();
                    b.shutdownOutput();
                    while (closed < 2) service(selector);
                    System.out.println("messages=" + messages + " closed=" + closed);
                }
            } finally {
                for (SelectionKey key : selector.keys()) key.channel().close();
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac SelectorStateDemo.java
java SelectorStateDemo
```

Stdout đã kiểm chứng khi chạy trên loopback:

```text
connection 2: BETA
connection 1: ALPHA
messages=2 closed=2
```

Nếu hệ điều hành không cho bind socket, môi trường loopback gặp lỗi I/O hoặc sự kiện không đến trước thời hạn 2 giây, chương trình có thể ném `IOException`. Ví dụ cố ý dùng timeout để tránh treo trong test; kết quả mẫu giả định các thao tác TCP loopback thành công.

### Vì sao ví dụ chứng minh state độc lập?

1. `listener.register(selector, OP_ACCEPT)` làm event loop quan sát connection mới.
2. Sau mỗi accept, server tạo `new ConnectionState(++nextId)` rồi gắn vào `accepted.register(..., OP_READ, state)`. ID của A là 1; ID của B là 2 do chương trình accept tuần tự.
3. `state.inbound` là field của **mỗi instance** nên byte A và B không thể nằm trong cùng buffer.
4. `parse(state)` chỉ đọc buffer của connection đang có `OP_READ`. Nếu header/payload chưa đủ, nó reset position và compact; không dispatch message dở.
5. B gửi xong trước A nên `connection 2: BETA` xuất hiện trước. A vẫn giữ phần `AL` của riêng mình rồi hoàn tất thành `ALPHA` sau đó.
6. `shutdownOutput()` tạo EOF cho server sau khi byte gửi được xử lý; server kiểm tra không còn frame dở, rồi cancel key/close channel.
7. Bài test yêu cầu đúng **một frame trên mỗi connection**; đó là assertion của test, **không** phải giới hạn của Selector hay TCP. Server thực tế có thể nhận hàng nghìn frame trên mỗi connection.

### Những điều ví dụ không làm thay server production

Ví dụ cố ý điều phối từng `sendPart(...); service(selector)` để lịch xen kẽ dễ đọc và stdout ổn định. Server thật phải chạy event loop lâu dài, có nhiều client, có outbound response, có xử lý lỗi riêng từng connection, timeout/quota và backpressure. Trường hợp này mới minh hoạ receiving và state ownership. Các mục dưới giải thích cách mở rộng.

## 9. Một key có thể báo nhiều loại readiness trong cùng vòng

Event loop production thường không dùng `if (isReadable()) ... else if (isWritable()) ...` vì một key có thể **đồng thời** báo readable và writable. Hãy xử lý từng loại phù hợp, kiểm tra lại `key.isValid()` sau nhánh có thể đóng connection:

```java
if (key.isValid() && key.isConnectable()) {
    finishConnection(key);
}
if (key.isValid() && key.isReadable()) {
    readAndDecode(key);
}
if (key.isValid() && key.isWritable()) {
    flushPendingWrites(key);
}
```

Đây là mảnh code: các hàm là điểm mở rộng của ứng dụng, không phải Java API có sẵn. Trong server listener, `OP_ACCEPT` thường nằm trên key của `ServerSocketChannel` và không cần các xử lý socket client. Kịch bản client TCP nonblocking dùng `OP_CONNECT` thì phải gọi `finishConnect()` và sau đó cập nhật `interestOps` sang `OP_READ` hoặc những ops cần thiết.

**Khi nhận từ `Selector.selectedKeys()`, loại bỏ key đã xử lý khỏi selected set:**

```java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();
    if (!key.isValid()) continue;
    // dispatch theo ready ops
}
```

Nếu quên `it.remove()`, key cũ có thể còn trong selected-key set và bị xử lý lại dù event không còn phù hợp, dẫn đến busy loop hoặc logic khó đoán. Không tự chèn key vào selected-key set; selector quản lý việc phát hiện readiness.

`SelectionKey.isValid()` có thể chuyển false khi channel đóng, selector đóng hoặc key bị cancel. Một sự kiện readiness chỉ là gợi ý, **không đảm bảo** một lần read/write luôn trả số byte dương. Hãy xử lý `0`, EOF và exceptions chính xác.

## 10. State của outbound: partial write cũng thuộc riêng từng client

Trong nonblocking mode, `SocketChannel.write(ByteBuffer)` có thể ghi **ít hơn toàn bộ `remaining()`** hoặc trả `0`. Không được coi một `write` là đã gửi xong response. Nếu A còn 200 byte response và B đang chờ response khác, byte còn dư của A phải nằm trong **outbound queue của A** với `ByteBuffer.position` đã cập nhật.

Một state mở rộng:

```java
static final class ConnectionState {
    final ByteBuffer inbound = ByteBuffer.allocate(4096);
    final Deque<ByteBuffer> outbound = new ArrayDeque<>();
    int queuedBytes;
    // protocol phase, deadline, request state...
}
```

Đây là mảnh code minh họa; cần import `java.nio.ByteBuffer`, `java.util.Deque` và `java.util.ArrayDeque`. Khi ứng dụng đã mã hóa xong một frame response:

```java
state.outbound.addLast(ByteBuffer.wrap(encodedFrame));
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
```

`encodedFrame` ở đây là `byte[]` **sở hữu riêng**; không được thay đổi sau khi enqueued trừ khi thực hiện copy an toàn. Cần cập nhật `queuedBytes` tương ứng theo thực tế, và đảm bảo gọi trên thread quản lý selector (hoặc gửi task tới event loop rồi `wakeup()`). Đừng thêm queue không giới hạn.

Khi key báo writable:

```java
SocketChannel channel = (SocketChannel) key.channel();
ConnectionState state = (ConnectionState) key.attachment();
while (!state.outbound.isEmpty()) {
    ByteBuffer head = state.outbound.peekFirst();
    channel.write(head); // position tự tăng theo số byte đã ghi
    if (head.hasRemaining()) {
        return;          // chờ OP_WRITE mới, không ghi lặp/đảo byte
    }
    state.outbound.removeFirst();
}
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

Đây là mảnh code minh họa; production cần cập nhật `queuedBytes` theo số byte ghi, hạn mức thời gian/byte mỗi vòng, và xử lý `IOException` bằng cách đóng connection bị ảnh hưởng. Chỉ bật `OP_WRITE` khi có dữ liệu chờ; **socket thường luôn writable**, nên để `OP_WRITE` bật vĩnh viễn khi queue rỗng có thể tạo event loop nóng, tốn CPU.

### Inbound và outbound có liên hệ nhưng không dùng chung state

Một connection có thể đồng thời:
- Đang nhận dở request thứ hai.
- Đã xử lý xong request thứ nhất.
- Còn một phần response thứ nhất chưa ghi hết.
- Chờ handshake protocol hoặc xử lý nghiệp vụ bất đồng bộ.

Mỗi hướng I/O có state và buffer riêng. Không dùng cùng `ByteBuffer` để vừa `channel.read` vừa `channel.write` trên một kết nối nếu không có cấu trúc ownership rõ; càng không dùng chung buffer đó cho nhiều connection.

## 11. Protocol phase và parser state là dữ liệu của connection

Một protocol thực tế có thể chuyển qua các trạng thái:

```text
ACCEPTED
  │
  ▼
HANDSHAKE / AUTHENTICATING
  │ thành công
  ▼
ACTIVE
  │
  ├── READ_HEADER -> READ_PAYLOAD -> DISPATCH -> READ_HEADER
  │
  ├── QUEUED_WRITE -> PARTIAL_WRITE -> COMPLETE_WRITE
  │
  └── CLOSING -> CLOSED
```

**Hai bộ state khác nhau:**
- **Protocol phase:** client đã xác thực chưa, đã gửi magic/version chưa, đang chờ handshake hay đang đóng?
- **Frame decoder phase:** đang cần bao nhiêu byte header hoặc payload? Có bao nhiêu byte còn phải nhận để hoàn thành một frame?

Chúng có thể được lưu dưới dạng enum và số byte cần đọc trong `ConnectionState`. Một client đang ở phase handshake không được dùng chung biến phase với client đã authenticated. Nếu dùng finite state machine, chuyển phase chỉ khi dữ liệu cần thiết của **connection đó** đã đầy đủ và vượt qua validation.

Ví dụ application protocol có yêu cầu `HELLO` trước rồi mới cho `DATA`: nếu A gửi `HEL` (chưa đủ) và B gửi `HELLO` (đủ), phải chỉ cho B sang `ACTIVE`. Không vì B hoàn tất handshake mà đổi phase của A.

State còn có thể lưu `requestId` hoặc map các logical stream nếu một connection hỗ trợ nhiều request song song. Khi multiplex, cần **tầng state theo stream ID** trong chính connection, thay vì tạo một selector key mới cho mỗi request. Key theo channel; application request không tự biến thành channel.

## 12. Kết nối outbound nonblocking: OP_CONNECT và finishConnect

Với server nhận client, `OP_ACCEPT` đưa ra `SocketChannel` đã được accept. Khi ứng dụng tự mở kết nối tới remote theo kiểu nonblocking, có thêm trạng thái **đang connect**:

```java
SocketChannel channel = SocketChannel.open();
channel.configureBlocking(false);
boolean connected = channel.connect(remote);
int ops = connected ? SelectionKey.OP_READ : SelectionKey.OP_CONNECT;
ConnectionState state = new ConnectionState(...);
SelectionKey key = channel.register(selector, ops, state);
```

Đây là mảnh code với `remote` (kiểu `SocketAddress`), `selector` và class state do ứng dụng cung cấp. Khi `key.isConnectable()`, gọi `channel.finishConnect()` và xử lý kết quả hoặc `IOException`. Sau khi kết nối hoàn tất, đăng ký `OP_READ` và chỉ bật `OP_WRITE` khi có outbound data. Nếu kết nối chưa hoàn tất, gọi read/write như socket đã connected có thể ném `NotYetConnectedException`.

Phải lưu **trạng thái kết nối** và **thời hạn connect** trong state của client đó, không lưu biến `boolean connected` chung cho mọi key.

## 13. EOF, half-close, lỗi và cleanup đúng connection

`SocketChannel.read` trả `-1` khi peer đã kết thúc chiều gửi và không còn byte để đọc. Điều này **không tự đồng nghĩa** mọi protocol frame đã hoàn chỉnh: có thể EOF đến khi buffer còn 1–3 byte của header hoặc một phần payload.

Khi EOF:
1. Cho parser tiêu thụ mọi frame hoàn chỉnh còn trong buffer (nếu đang giữ byte đã đọc).
2. Nếu còn header/payload dở, báo **truncated frame** theo protocol.
3. Nếu ứng dụng cho phép TCP half-close, cân nhắc tiếp tục flush outbound response trước khi đóng hoàn toàn; nếu không, đóng theo lifecycle đã định nghĩa.
4. Hủy key, đóng channel, xóa tham chiếu/queue, release tài nguyên và giảm các bộ đếm kết nối/bộ nhớ.
5. Không xóa hoặc reset state của client khác.

Ví dụ demo ở mục 8 đóng ngay sau khi nhận đúng một frame trên mỗi client, vì đó là mục đích test. Trong production, đôi khi request đã đọc xong nhưng response vẫn chờ `OP_WRITE`; nếu đóng ngay khi đọc EOF có thể đánh rơi response. Cần định nghĩa rõ protocol cho phép half-close hay không, và có phải flush trước khi close.

Một helper cleanup khái niệm:

```java
static void closeClient(SelectionKey key) {
    try {
        key.cancel();
        key.channel().close();
    } catch (IOException ex) {
        // log hoặc metrics theo policy
    } finally {
        // nếu còn map/queue/timer ngoài attachment: giải phóng ở đây
        key.attach(null);
    }
}
```

Đây là mảnh code dùng trong nơi còn quyền sở hữu key; trong hệ thống thật cần huỷ timer, xóa entry map, giải phóng pooled buffer, loại pending task và kết thúc response callbacks đúng cách. `key.cancel()` là yêu cầu huỷ đăng ký; key có thể chỉ được gỡ khỏi các key set của selector vào bước select sau đó. `key.channel().close()` giải phóng socket/channel. **Đóng Selector không đảm bảo tự đóng tất cả các channel đã đăng ký**, nên shutdown server cần chủ động close connection/channel.

### Exception chỉ nên làm hỏng đúng connection liên quan

Nếu B gửi length âm hoặc payload vượt max, server nên reject và đóng **B**; A vẫn tiếp tục nếu A không có vấn đề. Một lỗi parser của client không nên làm cả event loop thoát và đóng toàn bộ server. Đặt `try/catch` quanh thao tác của từng client, ghi log/metrics có giới hạn, cleanup đúng state. Những lỗi hạ tầng nghiêm trọng của selector có thể yêu cầu shutdown server, nhưng cần phân biệt chúng với input sai của một client.

## 14. Quản lý selected key, readiness và fairness

Một Selector có thể báo nhiều key cùng lúc; event loop cần cân bằng giữa các connection.

- Nếu mỗi key readable, đọc tới `0` trong nonblocking mode hoặc tới **byte/time budget** của lượt xử lý. Không để một client liên tục có dữ liệu chiếm event loop mãi.
- Nếu mỗi key writable, flush tối đa một quota byte/operation rồi chuyển key tiếp theo. Giữ phần còn lại trong outbound queue.
- Khi process nhiều key, luôn `iterator.remove()` key đã xử lý khỏi `selectedKeys()`. Không lưu reference tới selected-key set rồi xử lý lại mà không biết readiness đã thay đổi.
- `key.isReadable()` và `key.isWritable()` là bit readiness, có thể đồng thời true. Sau khi nhánh đọc đóng channel, phải kiểm tra `key.isValid()` trước nhánh ghi.
- Không đưa blocking business work, database query lâu, network call khác hoặc file I/O lớn trực tiếp vào event loop. Nếu cần worker pool, chuyển **message immutable/owned data** ra queue và xử lý kết quả trên event loop theo vòng đời connection.

### Backpressure theo từng kết nối

Một client chậm đọc response có thể khiến `outbound` của nó tăng không giới hạn. Cần quota rõ theo connection:
- Max số byte outbound đang chờ.
- Max số frame đang chờ xử lý.
- Timeout kết nối thiếu tiến triển.
- Quy tắc tạm tắt `OP_READ` khi phía xử lý không tiêu thụ kịp, rồi bật lại sau khi queue giảm.
- Giới hạn tổng thể của server, tránh một tập client xấu chiếm hết memory.

Khi tắt `OP_READ`, phải có cơ chế **bật lại** (queue drained, handler xong, deadline). Tắt đọc mãi có thể gây treo logic. Khi outbound queue rỗng, tắt `OP_WRITE` để tránh busy spin.

## 15. Bộ nhớ và giới hạn frame cho hàng nghìn connection

Nếu mỗi client được cấp `ByteBuffer.allocate(1_048_576)` (1 MiB) và có 5.000 kết nối, chỉ inbound buffer đã cần xấp xỉ 5 GiB chưa kể buffer ghi, object overhead, TLS và queue. Vì vậy ưu tiên:
- Mỗi state có buffer **nhỏ đủ dùng** hoặc buffer pool có ownership rõ.
- Frame length được kiểm tra trước cấp phát/grow; ví dụ ≤32 byte là policy của demo, không phải giới hạn chung.
- Dùng accumulator có khả năng grow **tối đa theo quota** hoặc parser incremental theo state header/payload để tránh cấp bộ nhớ tối đa ngay từ đầu.
- Quota theo connection và tổng server, cùng timeout để chặn client gửi từng byte cực chậm.
- Queue outbound riêng, có hạn mức và chính sách từ chối/đóng nếu client không nhận được response đủ nhanh.
- Cleanup mọi `ByteBuffer` pooled, timer, task, attachment, socket và map entry khi connection đóng.

**Không thể kết luận frame đã bị cắt chỉ vì read nhận ít byte**. TCP không mất phần dư như UDP; cần giữ và đọc tiếp. Nhưng nếu parser tự dùng `clear()` hoặc một scratch buffer chung không chuyển pending bytes vào state, dữ liệu đã nhận có thể bị chính ứng dụng ghi đè. 

### Tách state logic khỏi memory vật lý khi pooling

Có thể dùng buffer pool chung **để cấp phát/tái sử dụng vùng nhớ**, nhưng tại một thời điểm mỗi vùng đang chứa pending bytes phải có **chủ sở hữu rõ ràng**. Đừng đồng nhất “pool chung” với “buffer đang ghi của mọi channel”. Khi trả buffer về pool, phải chắc chắn không còn consumer hoặc worker nào giữ `slice()/duplicate()` trỏ vào vùng nhớ ấy.

`ByteBuffer.slice()` và `duplicate()` có position/limit riêng nhưng chia sẻ dữ liệu nền. Nếu worker giữ slice còn event loop đã `compact()` hoặc `read()` đè lên backing buffer, worker có thể thấy payload đổi. Cần copy payload hoặc reference-count/lifetime được kiểm soát.

## 16. Thread safety: một event loop sở hữu ConnectionState

Mô hình đơn giản nhất: chỉ event loop thread được thay đổi `ConnectionState`, `SelectionKey.interestOps`, position/limit của inbound/outbound buffer và parser phase. Worker khác có thể làm công việc nặng trên **bản sao dữ liệu** rồi gửi kết quả về event loop.

`ByteBuffer` và các queue/state mutable không tự an toàn khi nhiều thread cùng thay đổi. `Selector` có thể được wakeup từ thread khác, nhưng điều đó không khiến mọi sửa state trở thành thread-safe. Một cách tổ chức thông dụng:

```text
Worker thread hoàn thành kết quả
    │
    ▼
Concurrent queue chứa command (connection ID, result)
    │
    ▼
selector.wakeup()
    │
    ▼
Event loop nhận command, kiểm tra connection còn sống
    │
    ▼
Gắn response vào outbound queue của đúng connection
    │
    ▼
Bật OP_WRITE cho key tương ứng
```

**Đừng dùng trực tiếp `SocketChannel` hoặc `SelectionKey` cũ nếu connection đã bị đóng và ID được tái sử dụng**. Có thể dùng connection object/token không tái sử dụng, kiểm tra `key.isValid()` và state lifecycle trước khi áp kết quả async. Đừng giả định chỉ vì handler bắt đầu khi connection còn sống thì nó vẫn còn sống lúc handler kết thúc.

Trong hệ thống dùng nhiều event loop, gán mỗi connection cho một loop chủ; mọi sửa state của connection phải được đưa đến loop đó hoặc đồng bộ hóa rõ ràng. Mỗi loop có `Selector` riêng, tránh hai thread cùng đọc/compact một buffer.

## 17. Các lỗi thiết kế phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Một `static ByteBuffer` cho tất cả client | Byte bị ghi đè/trộn giữa connection | State inbound riêng cho mỗi key |
| Một `expectedLength` toàn cục | Header B ghi đè tiến độ parse A | Field parser riêng cho connection |
| Cấp buffer mới mỗi OP_READ | Mất header/payload chưa đủ | Buffer/decoder tồn tại qua events |
| `clear()` sau khi chỉ parse được một phần | Ghi đè byte pending | `compact()` hoặc chuyển sang state riêng |
| Chỉ parse một frame rồi ngừng | Các frame còn trong buffer bị kẹt | Vòng parse tất cả frame hoàn chỉnh |
| Tin `read()` luôn trả đủ frame | Cắt message hoặc parse lỗi | Length-prefix + partial-read state |
| Không giới hạn frame | Peer độc hại khai length rất lớn | Validate length trước allocate/grow |
| Luôn bật `OP_WRITE` | Busy loop, CPU cao | Bật khi queue có dữ liệu, tắt khi rỗng |
| Bỏ qua partial write | Response mất byte/đảo thứ tự | Queue `ByteBuffer` riêng, giữ position |
| Dùng một queue outbound toàn server không định tuyến | Gửi response sang sai client | Queue trong state từng connection |
| Quên `selectedKeys().iterator().remove()` | Xử lý lại key/sự kiện cũ | Gỡ key đã dispatch khỏi selected set |
| Đóng Selector mà quên đóng channels | Rò socket và connection resources | Cleanup từng key/channel |
| Đưa long-running task vào event loop | Mọi client bị chậm | Worker pool với message ownership |
| Worker mutate ByteBuffer cùng event loop | Data race, sai position/byte | Single owner hoặc synchronization đầy đủ |
| Không kiểm tra EOF giữa frame | Coi message bị cắt là hợp lệ | Kiểm tra pending bytes/phase lúc EOF |

Một lỗi khó thấy: nhận đủ frame của A, đưa `ByteBuffer.slice()` tới worker rồi ngay lập tức `compact()` để ghi tiếp. Nếu worker chưa xong, slice có thể nhìn thấy byte khác. Không nên coi `slice()` là payload immutable.

## 18. Kiểm thử state của từng connection, không chỉ kiểm thử parser đơn lẻ

Các unit test quan trọng cho decoder một connection:
1. Header 4 byte chia thành 1+1+2 byte.
2. Header đủ nhưng payload thiếu; parse phải giữ cả header hoặc state length.
3. Một read có 3 frame và vài byte đầu frame tiếp theo.
4. Một frame đúng tối đa kích thước; một frame vượt kích thước bị reject.
5. EOF giữa header hoặc payload phải báo lỗi.
6. Payload UTF-8 nhiều byte chia giữa read; decode sau khi đủ frame.

Các integration test quan trọng cho Selector:
1. Hai client A/B gửi header và payload đan xen như ví dụ mục 8; A không được nhận dữ liệu B và ngược lại.
2. A gửi frame dở, B gửi nhiều frame hoàn chỉnh; B không bị A chặn.
3. A ngắt giữa frame; chỉ state A cleanup, B vẫn hoạt động.
4. A gửi frame lỗi length âm/khổng lồ; B vẫn được phục vụ.
5. A chậm đọc response, outbound A backlog; B vẫn gửi/nhận bình thường.
6. Event writable nhưng `write()` trả 0 hoặc ghi một phần; queue và `position` vẫn giữ.
7. Nhiều connection được accept cùng lúc; mỗi connection có attachment riêng.
8. Worker trả kết quả sau khi client đã close; không queue response lên key invalid.
9. Shutdown event loop; toàn bộ key/channel/timer/queue/pooled buffer được giải phóng.
10. Thay đổi mọi cách chia chunk cho cùng một wire stream; parser cho cùng danh sách message.

Để test framing **deterministic**, hãy mã hóa wire bytes rồi chia ở mọi vị trí có thể, feed vào decoder riêng cho mỗi connection và so sánh payload sau decode. Không dựa duy nhất vào TCP loopback để “tình cờ” tạo partial read; OS có thể gom các write làm bug không lộ.

Để test connection isolation, tạo nhiều pair nguồn có ID/payload khác nhau; sau khi xử lý, so sánh log có **connection ID** và danh sách frame của từng connection. Hãy tránh suy ra correctness từ thứ tự log toàn cục: giữa các socket không có cam kết thứ tự đến.

## 19. Quy trình triển khai trong server thực tế

Một thiết kế event loop dễ bảo trì:

1. **Accept:** nonblocking `ServerSocketChannel` báo `OP_ACCEPT`; accept hết các connection đang chờ theo quota.
2. **Initialize:** mỗi accepted channel có `ConnectionState` mới, inbound parser/buffer, outbound queue, quota và deadline riêng; gắn vào key.
3. **Read:** khi `OP_READ`, đọc vào buffer của đúng state. `n > 0` thì parse tất cả frame hoàn chỉnh; `n == 0` thì chờ readiness; `n == -1` thì xử lý EOF/half-close.
4. **Parse:** bảo toàn header/payload dở, validate length và protocol phase; dispatch immutable/owned message tới handler.
5. **Business processing:** xử lý nhẹ trong loop hoặc gửi việc dài sang worker; kết quả được định tuyến về đúng connection còn sống.
6. **Write:** enqueue response vào state của connection; bật `OP_WRITE`. Mỗi writable event ghi phần có thể, giữ byte chưa gửi và tắt interest khi queue rỗng.
7. **Flow control:** áp inbound/outbound quota, timeout, max frame, số client, fairness và backpressure theo state.
8. **Close:** khi protocol kết thúc hoặc có lỗi, cancel key, đóng channel, release state/timer/queue và gỡ map entry.
9. **Shutdown:** dừng accept mới, xử lý hoặc hủy có quy tắc những connection đang tồn tại; đóng tất cả channels rồi selector.

Kiểm tra ba bất biến trong code review:
- **Isolation:** dữ liệu của kết nối A không thể đi vào buffer/queue/phase của B.
- **Continuity:** qua mỗi lần `select/read/write`, byte và protocol state chưa hoàn thành vẫn còn nguyên.
- **Ownership:** mọi buffer/attachment chỉ được sửa bởi một owner rõ ràng, và được giải phóng khi connection kết thúc.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một event loop chạy một thread vẫn phải có ByteBuffer riêng cho hai kết nối A và B?  
**Đáp án:** Vì các event từ A và B có thể xen kẽ. Một buffer/expectedLength dùng chung làm byte pending của A bị B ghi đè dù không có hai thread chạy đồng thời.

**Câu 2.** `key.isReadable()` có nghĩa một frame đã hoàn chỉnh chưa?  
**Đáp án:** Không. Nó chỉ cho biết channel có khả năng đọc (hoặc EOF/lỗi). Phải dùng framing và parser state của connection đó.

**Câu 3.** Bộ đệm có 4 byte header length=5 và mới 2 byte payload. Nếu parser đã gọi `getInt` thì cần làm gì trước `compact`?  
**Đáp án:** `reset()` về đầu header để giữ cả header và payload dở, hoặc lưu expectedLength trong state riêng và chỉ giữ phần payload.

**Câu 4.** B gửi frame hoàn chỉnh khi A đang chờ 3 byte cuối payload. Có được dispatch B ngay không?  
**Đáp án:** Có. B có buffer/state riêng; xử lý của B không cần chờ A, trừ khi có ràng buộc nghiệp vụ chung được thiết kế riêng.

**Câu 5.** Vì sao không bật `OP_WRITE` mọi lúc?  
**Đáp án:** Socket thường writable; event loop có thể liên tục nhận event writable dù không có response chờ, gây CPU cao. Bật khi queue có dữ liệu, tắt khi rỗng.

**Câu 6.** Nếu `SocketChannel.write` chỉ ghi 100/500 byte của response A, byte còn lại ở đâu?  
**Đáp án:** Trong `ByteBuffer` ở outbound queue của A, với position chỉ sau 100 byte đã ghi. Lần writable sau tiếp tục từ position đó.

**Câu 7.** Worker trả kết quả của client A sau khi A đóng. Có nên dùng SelectionKey cũ để enqueue?  
**Đáp án:** Không. Kiểm tra state lifecycle và key validity; bỏ hoặc xử lý theo policy, không gửi nhầm sang connection mới.

**Câu 8.** `Selector.close()` có tự đóng tất cả `SocketChannel` đã đăng ký không?  
**Đáp án:** Không nên dựa vào điều đó. Quản lý và chủ động đóng từng channel khi cleanup/shutdown.

**Câu 9.** Khi nào có thể dùng scratch buffer chung mà vẫn đúng?  
**Đáp án:** Khi mọi byte chưa xử lý được chuyển/copy sang state riêng của kết nối trước khi scratch buffer được tái sử dụng, và ownership được đảm bảo.

**Câu 10.** Trong ví dụ `SelectorStateDemo`, tại sao `BETA` được in trước `ALPHA` mà không có lỗi thứ tự TCP?  
**Đáp án:** Vì đó là hai kết nối TCP **khác nhau**. Không có cam kết thứ tự hoàn tất giữa hai connection; trong mỗi connection byte vẫn đúng thứ tự.

## 21. Tài liệu đối chiếu

- Java SE 17 `Selector` — key sets, selected keys và cơ chế readiness: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- Java SE 17 `SelectionKey` — `attach`/`attachment`, `interestOps`, `OP_READ/WRITE/ACCEPT/CONNECT`, cancellation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html
- Java SE 17 `SocketChannel` — nonblocking `read/write` và `finishConnect`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html
- Java SE 17 `ServerSocketChannel` — accept nonblocking: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html
- Java SE 17 `ByteBuffer` — `flip()`, `compact()`, `mark()/reset()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- RFC 9293, Transmission Control Protocol — TCP byte-stream semantics: https://www.rfc-editor.org/rfc/rfc9293
