# Selector và mô hình nhiều channel trên một luồng (Java NIO)

Thông thường, khi một ứng dụng mạng sử dụng lời gọi đọc blocking, mỗi kết nối có thể cần một luồng riêng để chờ dữ liệu. Java NIO cung cấp **`Selector`** để một luồng có thể theo dõi **nhiều channel có khả năng lựa chọn (selectable channels)** và chỉ xử lý các thao tác I/O mà hệ điều hành/provider báo là **có khả năng tiến triển** (*readiness*). Kiến trúc này là nền tảng của nhiều **event loop** và máy chủ mạng quản lý nhiều kết nối.

Điều cốt lõi: **Selector không tự đọc/ghi dữ liệu, không tạo luồng cho mỗi channel và không đảm bảo một lần `read` hoặc `write` chuyển hết dữ liệu.** Nó phối hợp với `SelectableChannel`, `SelectionKey`, `ByteBuffer` và logic ứng dụng để đợi rồi xử lý sự kiện.

## 1. Selector giải quyết vấn đề gì?

Hãy hình dung máy chủ có nhiều kết nối TCP, phần lớn thời gian mỗi kết nối chỉ chờ một yêu cầu tiếp theo:

```text
Mô hình đơn giản: một luồng cho một kết nối

Client A ── Socket A ── Thread A ── read() chờ
Client B ── Socket B ── Thread B ── read() chờ
Client C ── Socket C ── Thread C ── read() chờ
...                        ...

Mô hình event loop dùng Selector

Client A ── SocketChannel A ─┐
Client B ── SocketChannel B ─┼── Selector.select() ── Event-loop thread
Client C ── SocketChannel C ─┘                       ├── A: OP_READ?
                                                    ├── B: OP_WRITE?
                                                    └── C: OP_CONNECT?
```

Một luồng đợi readiness của nhiều channel, sau đó xử lý từng `SelectionKey` phù hợp. Điều này có thể giảm chi phí quản lý nhiều luồng đang chờ I/O, nhất là với lượng lớn kết nối phần lớn thời gian rảnh.

Tuy nhiên, **một event-loop thread vẫn chỉ thực hiện code tại một thời điểm**. Nếu handler chạy CPU nặng, gọi database blocking, `Thread.sleep` lâu hoặc chờ một Future blocking, tất cả kết nối do luồng đó quản lý có thể bị chậm. Vì vậy event loop thường làm I/O và logic ngắn gọn, giao tác vụ blocking/CPU nặng sang nhóm worker phù hợp.

## 2. Các thành phần và quan hệ sở hữu

| Thành phần | Vai trò |
| --- | --- |
| `Selector` | Đăng ký nhiều `SelectableChannel`, đợi readiness, cung cấp tập khóa sẵn sàng. |
| `SelectableChannel` | Channel có thể đặt non-blocking và đăng ký với một hoặc nhiều selector; ví dụ `SocketChannel`, `ServerSocketChannel`, các channel của `Pipe`. |
| `SelectionKey` | Quan hệ đăng ký **một channel trên một selector**, chứa interest ops, ready ops và attachment. |
| `SelectionKey.interestOps()` | Những loại sự kiện ứng dụng muốn selector giám sát. |
| `SelectionKey.readyOps()` | Những loại thao tác mà lựa chọn gần nhất cho thấy có thể tiến triển. |
| `SelectionKey.attachment()` | State tùy ý của ứng dụng, ví dụ buffer đọc dở, hàng đợi ghi, parser. |
| `ByteBuffer` | Dữ liệu được đọc/ghi qua channel, với `position`, `limit` và `remaining()`. |

Một channel có thể được đăng ký với nhiều selector, nhưng với **cùng một selector**, mỗi channel có tối đa một đăng ký/`SelectionKey` còn hiệu lực. Thao tác `register(selector, ops, attachment)` trên channel đã đăng ký có thể cập nhật interest/attachment của khóa hiện có, không tạo vô hạn khóa trùng.

`Selector.open()` chọn provider khả dụng; không nên phụ thuộc cứng vào cơ chế native như `epoll`, `kqueue` hay `poll` để suy ra mọi đặc tính nền tảng. JVM và hệ điều hành chọn triển khai thích hợp.

## 3. Interest ops và ready ops: hai tập khác nhau

Các thao tác quan trọng:

| Operation | Channel thường dùng | Khi nào quan tâm? |
| --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | Server có kết nối mới chờ `accept()`. |
| `SelectionKey.OP_CONNECT` | `SocketChannel` | Kết nối non-blocking đang có thể hoàn tất; gọi `finishConnect()`. |
| `SelectionKey.OP_READ` | `SocketChannel`, `Pipe.SourceChannel` | Có khả năng đọc được dữ liệu, EOF hoặc trạng thái cần xử lý. |
| `SelectionKey.OP_WRITE` | `SocketChannel`, `Pipe.SinkChannel` | Có khả năng ghi thêm dữ liệu vào channel. |

Mỗi loại channel chỉ hỗ trợ một tập ops được công bố qua `validOps()`. Không đăng ký `OP_ACCEPT` cho `SocketChannel` hoặc `OP_READ` cho `ServerSocketChannel`: tổ hợp không được hỗ trợ có thể ném `IllegalArgumentException`.

Ví dụ:

```java
// Snippet: socket là SocketChannel non-blocking đã kết nối.
SelectionKey key = socket.register(selector, SelectionKey.OP_READ);
int wanted = key.interestOps(); // Ứng dụng đang quan tâm đến OP_READ.
int ready = key.readyOps();     // Readiness được phát hiện ở lần chọn gần đây.
```

Hai tập cờ dạng bitmask này **không đồng nghĩa**. `interestOps` là ý định theo dõi; `readyOps` là tín hiệu readiness đã chọn. Kiểm tra an toàn bằng `key.isValid()` trước các phương thức phụ thuộc trạng thái khóa. Các tiện ích như `isReadable()`, `isWritable()`, `isAcceptable()`, `isConnectable()` tương ứng với bit trong ready ops.

**Readiness không bảo đảm thao tác sẽ chuyển dữ liệu.** Giữa lúc `select()` trả về và lời gọi I/O, trạng thái có thể thay đổi; một lần `read`/`write` trên non-blocking channel vẫn có thể trả 0. Luôn xử lý kết quả thực tế.

## 4. Bắt buộc cấu hình non-blocking trước khi register

Để đăng ký channel với selector, channel phải ở chế độ **non-blocking**:

```java
// Snippet: server là ServerSocketChannel đang mở.
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);
```

Nếu channel vẫn blocking, đăng ký có thể ném `IllegalBlockingModeException`. Với `SocketChannel` đã kết nối:

```java
socket.configureBlocking(false);
socket.register(selector, SelectionKey.OP_READ, connectionState);
```

Đây là snippet; `selector` và `connectionState` do chương trình khai báo. Khi channel đã đăng ký với bất kỳ selector nào, không thể tùy tiện chuyển ngược về blocking mode; cố cấu hình blocking thường gây `IllegalBlockingModeException` khi còn đăng ký hợp lệ.

**FileChannel không phải SelectableChannel** và không dùng `register(selector, OP_READ)`. Thao tác đọc file theo `FileChannel` vẫn có thể blocking; khi cần event loop mạng, hãy xử lý file I/O có chiến lược riêng như thread pool, asynchronous API phù hợp hoặc truyền dữ liệu được kiểm soát.

## 5. Chu trình event loop chuẩn

Luồng xử lý thường thấy:

```text
1. Selector.open()
2. Tạo + configureBlocking(false) cho các channel
3. register(selector, interestOps, attachment)
                    |
                    v
          selector.select()
                    |
       +------------+-------------+
       | selectedKeys()           |
       v                          |
4. Duyệt từng SelectionKey        |
5. iterator.remove()              |
6. Kiểm tra key.isValid()         |
7. Xử lý ACCEPT/CONNECT/READ/WRITE|
8. Cập nhật interestOps, buffers  |
9. Đóng/cancel khi cần            |
       |                          |
       +--------------------------+
```

Khung Java điển hình:

```java
// Snippet: selector đã được mở, channel đã được register.
while (running) {
    selector.select(); // Chờ ít nhất một event hoặc wakeup/interrupt.
    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove(); // Xóa khỏi selected-key set sau khi lấy ra.

        if (!key.isValid()) {
            continue;
        }
        if (key.isAcceptable()) {
            handleAccept(key);
        }
        if (key.isValid() && key.isConnectable()) {
            handleConnect(key);
        }
        if (key.isValid() && key.isReadable()) {
            handleRead(key);
        }
        if (key.isValid() && key.isWritable()) {
            handleWrite(key);
        }
    }
}
```

Đoạn trên là **pseudocode dạng Java**, giả định tồn tại `running` và các hàm `handle...` trong chương trình của bạn. Từng handler có thể hủy khóa, đóng channel hoặc thay đổi interest ops, nên cần kiểm tra tính hợp lệ phù hợp trước lần sử dụng tiếp theo.

**Vì sao `iterator.remove()` là bắt buộc trong mẫu này?** `selectedKeys()` là tập khóa được chọn, không được tự làm sạch mỗi vòng. Nếu không xóa key đã xử lý, nó có thể tiếp tục xuất hiện và gây việc xử lý lặp trên sự kiện cũ. Không xóa bằng `selector.selectedKeys().clear()` giữa lúc đang duyệt cùng iterator.

## 6. Ví dụ Java 17+ chạy độc lập: một Selector giám sát hai Pipe

Để minh họa cơ chế **một luồng – nhiều channel** mà không phải phụ thuộc mạng hoặc port, ví dụ dùng **hai `Pipe.SourceChannel`**. Chúng là selectable channels có thể nhận `OP_READ`. Hai `Pipe.SinkChannel` ghi thông điệp và selector đọc từ các source tương ứng.

Mỗi thông điệp kết thúc bởi ký tự xuống dòng. Buffer đọc cố ý nhỏ (3 byte) để minh họa **một thông điệp có thể được nhận thành nhiều chunk**, nên trạng thái chưa hoàn chỉnh được giữ trong `Session.pending`. Khi đủ thông điệp, chương trình hủy key. Kết quả được lưu trong `TreeMap` để in theo thứ tự ổn định, vì **thứ tự các ready keys không được bảo đảm**.

Lưu đúng tên **`SelectorMultiplexDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.Map;
import java.util.TreeMap;

public class SelectorMultiplexDemo {
    private static final class Session {
        final String name;
        final ByteArrayOutputStream pending = new ByteArrayOutputStream();
        Session(String name) { this.name = name; }
    }

    private static void send(Pipe.SinkChannel sink, String text)
            throws IOException {
        ByteBuffer data = ByteBuffer.wrap(
                (text + "\n").getBytes(StandardCharsets.US_ASCII));
        while (data.hasRemaining()) {
            sink.write(data);
        }
    }

    public static void main(String[] args) throws IOException {
        Pipe a = Pipe.open();
        Pipe b = Pipe.open();
        try (Selector selector = Selector.open();
             Pipe.SourceChannel readA = a.source();
             Pipe.SinkChannel writeA = a.sink();
             Pipe.SourceChannel readB = b.source();
             Pipe.SinkChannel writeB = b.sink()) {

            readA.configureBlocking(false);
            readB.configureBlocking(false);
            readA.register(selector, SelectionKey.OP_READ, new Session("A"));
            readB.register(selector, SelectionKey.OP_READ, new Session("B"));

            send(writeA, "alpha");
            send(writeB, "beta");

            Map<String, String> received = new TreeMap<>();
            while (received.size() < 2) {
                if (selector.select(2_000) == 0) {
                    throw new IOException("Timeout chờ dữ liệu");
                }
                Iterator<SelectionKey> iterator =
                        selector.selectedKeys().iterator();
                while (iterator.hasNext()) {
                    SelectionKey key = iterator.next();
                    iterator.remove();
                    if (!key.isValid() || !key.isReadable()) {
                        continue;
                    }
                    Session session = (Session) key.attachment();
                    Pipe.SourceChannel channel =
                            (Pipe.SourceChannel) key.channel();
                    ByteBuffer chunk = ByteBuffer.allocate(3);
                    while (key.isValid()) {
                        int n = channel.read(chunk);
                        if (n == -1) {
                            throw new IOException("EOF trước dấu kết thúc");
                        }
                        if (n == 0) {
                            break;
                        }
                        chunk.flip();
                        while (chunk.hasRemaining()) {
                            byte ch = chunk.get();
                            if (ch == '\n') {
                                received.put(session.name,
                                        session.pending.toString(
                                                StandardCharsets.US_ASCII));
                                key.cancel();
                                break;
                            }
                            session.pending.write(ch);
                        }
                        chunk.clear();
                    }
                }
            }
            System.out.println("channels=" + received.size());
            received.forEach((name, message) ->
                    System.out.println(name + "=" + message));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 SelectorMultiplexDemo.java
java SelectorMultiplexDemo
```

Stdout đã đối chiếu khi biên dịch và chạy thực tế trên Java 17+:

```text
channels=2
A=alpha
B=beta
```

Điểm cần quan sát:

1. `Pipe.open()` tạo **hai** cặp source/sink. Chương trình chỉ chạy một `main` thread xử lý selection, không tạo thread per channel.
2. Hai source được `configureBlocking(false)` rồi `register(selector, OP_READ, Session)`. Mỗi khóa gắn tên và vùng chứa dữ liệu chưa hoàn chỉnh.
3. `send` ghi các chuỗi ASCII cùng newline vào hai sink. Phương thức `write` được gọi lặp đến khi buffer hết byte; sink trong demo vẫn ở chế độ blocking và chỉ ghi lượng nhỏ **trước** vòng event loop nên phù hợp với ví dụ khép kín.
4. `selector.select(2_000)` đợi tối đa khoảng hai giây để có ready keys; đoạn demo báo lỗi nếu không có tiến triển, giúp tránh chờ vô hạn khi môi trường không cung cấp dữ liệu như dự kiến.
5. Mỗi `SourceChannel.read` đọc tối đa ba byte một lần. Nếu trả 0, nguồn non-blocking hiện chưa có thêm byte; vòng inner thoát để trở về selector. Khi gặp `\n`, thông điệp hoàn chỉnh được lưu vào map, khóa được hủy.
6. Output được sắp xếp A rồi B bằng `TreeMap`. Không giả định `selectedKeys()` luôn duyệt key đăng ký trước rồi key đăng ký sau.
7. `try-with-resources` đóng selector và bốn channel khi kết thúc. Demo không gọi mạng, không mở port và không dùng nhiều thread.

**Giới hạn có chủ ý của demo:** chỉ nhận một dòng ASCII ngắn trên mỗi pipe và không cho phép thông điệp lớn hoặc nhiều dòng trong cùng chunk. Trong server thật, handler cần xử lý nhiều frame trong một lượt đọc, ràng buộc kích thước buffer, bảo vệ khỏi dữ liệu ác ý và giữ state qua các vòng select.

## 7. Đưa mô hình vào TCP ServerSocketChannel

Một máy chủ TCP thường bắt đầu bằng:

```java
// Snippet: cần imports Selector, SelectionKey,
// ServerSocketChannel, SocketChannel, InetSocketAddress.
Selector selector = Selector.open();
ServerSocketChannel server = ServerSocketChannel.open();
server.configureBlocking(false);
server.bind(new InetSocketAddress("127.0.0.1", 8080));
server.register(selector, SelectionKey.OP_ACCEPT);
```

Khi nhận `OP_ACCEPT`:

```java
// Snippet: key lấy từ vòng selectedKeys().
ServerSocketChannel server =
        (ServerSocketChannel) key.channel();
SocketChannel client = server.accept();
if (client != null) {
    client.configureBlocking(false);
    client.register(selector, SelectionKey.OP_READ,
            new ConnectionState());
}
```

`ConnectionState` là lớp **ứng dụng phải định nghĩa**, ví dụ chứa `ByteBuffer input`, hàng đợi output và parser state. Hai đoạn này là **minh họa**, chưa bao gồm vòng đời đóng server/socket, xử lý error hay import đầy đủ.

Với non-blocking server, `accept()` có thể trả `null` dù trước đó readiness báo accept; điều kiện có thể thay đổi. Không dùng vòng chờ `while (accept() == null) { }`. Khi một sự kiện cho phép, có thể lặp `accept()` đến khi trả null để xử lý nhiều kết nối đang chờ, nhưng phải đặt ngân sách công việc hợp lý để không bỏ đói các channel khác.

Một socket vừa accept cần `configureBlocking(false)` **trước khi** đăng ký `OP_READ`; nếu quên, `register` có thể thất bại. Luồng event loop có thể giữ danh sách state theo attachments mà không cần mỗi kết nối một Java thread.

## 8. OP_CONNECT: kết nối non-blocking chưa hoàn tất

Với client chủ động kết nối:

```java
// Snippet: selector đã mở.
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);
boolean connected = client.connect(remoteAddress);
if (connected) {
    client.register(selector, SelectionKey.OP_READ, state);
} else {
    client.register(selector, SelectionKey.OP_CONNECT, state);
}
```

`remoteAddress` và `state` phải được khai báo ở ngữ cảnh ứng dụng. Khi key báo `isConnectable()`:

```java
SocketChannel client = (SocketChannel) key.channel();
if (client.finishConnect()) {
    key.interestOps(SelectionKey.OP_READ);
}
```

Trước khi `finishConnect()` thành công, không coi socket là đã sẵn sàng để xử lý application protocol. Kết nối có thể thất bại bằng `IOException`. Khi thất bại, cần hủy đăng ký, đóng channel và thông báo lỗi/áp dụng retry policy; không tiếp tục kích hoạt `OP_READ` trên socket hỏng.

Lưu ý: `OP_CONNECT` là sự kiện để **kiểm tra và hoàn tất kết nối**, không phải bằng chứng kết nối đã thành công.

## 9. OP_READ: đọc bao nhiêu byte là đủ?

Một `OP_READ` nghĩa là đọc có khả năng tiến triển. Với `SocketChannel` non-blocking:

- `read(buffer) > 0`: đã đưa số byte đó vào buffer và tăng `position`.
- `read(buffer) == 0`: chưa chuyển byte; thoát khỏi vòng thử đọc hiện tại và chờ readiness mới.
- `read(buffer) == -1`: peer đóng phía ghi/EOF; tùy protocol, có thể chấp nhận half-close, hoặc đóng kết nối sau khi xử lý dữ liệu còn lại.

Mẫu trạng thái nếu parser có thể giữ frame chưa đủ:

```java
// Snippet: socket non-blocking; state.input là ByteBuffer
// đang ở pha ghi, đủ dung lượng xử lý tối thiểu header.
int n = socket.read(state.input);
if (n == -1) {
    closeConnection(key);
} else if (n > 0) {
    state.input.flip();
    decodeAvailableFrames(state.input, state);
    state.input.compact();
}
```

Các hàm `closeConnection`/`decodeAvailableFrames` và kiểu `state` là **khung thiết kế**, không phải API có sẵn trong JDK. `decodeAvailableFrames` chỉ được tiêu thụ các byte thực sự cấu thành frame đầy đủ hoặc tiếp tục giữ state cần thiết. `compact()` giữ các byte chưa được parser tiêu thụ, đưa chúng về đầu buffer để lần `read` tiếp nối sau đó.

**Không đồng nhất một TCP `read` với một request.** TCP là luồng byte: một `read` có thể nhận nửa header, một request đầy đủ hoặc nhiều request ghép. Chọn framing: length-prefix, delimiter, fixed-size hoặc protocol decoder tương ứng. Với dữ liệu không tin cậy, phải có giới hạn độ dài, số frame, tốc độ, bộ nhớ và thời gian.

Nếu parser không thể tiến triển và input buffer đầy, cần có kế hoạch tăng dung lượng có hạn mức, stream payload hoặc từ chối request; gọi `read` vào buffer không còn `remaining()` chỉ tạo tình trạng không tiến triển.

## 10. OP_WRITE: chỉ đăng ký khi có dữ liệu cần gửi

Với kết nối TCP, socket thường sẵn sàng để ghi trong phần lớn thời gian khi send buffer của OS còn chỗ. Nếu một chương trình giữ `OP_WRITE` trong interest ops **liên tục dù không có dữ liệu chờ**, selector có thể liên tục đánh thức event loop, gây **busy loop** và tốn CPU.

Chiến lược phổ biến:

1. Mặc định theo dõi `OP_READ`.
2. Khi có thông điệp muốn gửi, encode thành `ByteBuffer`, enqueue vào outbound queue của connection.
3. Thử `socket.write(buffer)`. Nếu còn byte chưa gửi, giữ nguyên buffer với `position` đã tiến và bật `OP_WRITE`.
4. Khi nhận `OP_WRITE`, ghi các buffer tồn đến khi hết dữ liệu, đạt giới hạn ngân sách hoặc `write` trả 0.
5. Khi outbound queue trống, **gỡ `OP_WRITE` khỏi interest ops** để tránh đánh thức không cần thiết.

Mẫu bật/tắt bitmask:

```java
// Bật quan tâm write, giữ nguyên các flags khác:
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Khi đã gửi hết:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

Đây là snippet; key phải còn hợp lệ. **Không** sử dụng `interestOps(SelectionKey.OP_WRITE)` một cách mù quáng nếu vẫn cần đọc, vì thao tác đó thay **toàn bộ** bitmask và có thể vô tình tắt `OP_READ`.

Mẫu xử lý ghi (có hàng đợi `ByteBuffer` do ứng dụng quản lý):

```java
// Snippet: pending là ByteBuffer đầu hàng đợi,
// socket non-blocking, key hợp lệ.
while (pending.hasRemaining()) {
    int written = socket.write(pending);
    if (written == 0) {
        break; // Giữ position/limit để thử tiếp khi OP_WRITE sẵn sàng.
    }
}
```

`write` có thể ghi ít hơn `remaining()`. Đừng `clear()` hoặc tạo lại buffer chưa ghi hết; sẽ mất dữ liệu hoặc gửi trùng. Một outbound queue thực tế cần điều phối nhiều buffer, giới hạn kích thước chờ (backpressure) và đóng kết nối chậm theo chính sách.

## 11. selectedKeys, keys và cancellation

Cần phân biệt các tập:

| API | Ý nghĩa |
| --- | --- |
| `selector.keys()` | Các khóa đang đăng ký với selector (trừ các khóa đã được loại khỏi tập theo tiến trình hủy). |
| `selector.selectedKeys()` | Tập khóa có readiness được chọn, dành cho ứng dụng duyệt và **xóa key đã xử lý**. |
| `key.cancel()` | Đánh dấu hủy đăng ký; khóa trở nên không hợp lệ, deregistration được xử lý trong các bước selection tiếp theo. |
| `key.isValid()` | Kiểm tra đăng ký còn hợp lệ ở thời điểm gọi. |
| `key.channel()` / `key.selector()` | Truy xuất channel/selector liên quan. |
| `key.attach(obj)` / `key.attachment()` | Lưu/đọc state của connection, giảm nhu cầu map toàn cục. |

Điều thực tiễn: **`key.cancel()` không đồng nghĩa đóng channel**. Nếu kết nối đã hỏng hoặc ứng dụng đã xử lý xong, cần đóng `SocketChannel`/`Pipe.SourceChannel` khi bạn sở hữu nó; đóng channel sẽ làm các đăng ký liên quan mất hiệu lực, nhưng không nhất thiết tự đóng selector.

Đừng lặp toàn bộ `selector.keys()` để tìm ready ops sau `select()`; hãy dùng `selectedKeys()`. Không tự sửa những tập khóa không được API cho phép tùy tiện; mẫu phổ biến là `iterator.remove()` trên selected set.

Một key có thể đồng thời ready nhiều ops hợp lệ, nên handler phải cân nhắc thứ tự, kiểm tra `isValid()` sau bước có khả năng hủy key và giới hạn lượng công việc mỗi vòng để các kết nối khác được phục vụ công bằng.

## 12. select(), select(timeout), selectNow() và wakeup()

| Phương thức | Ý nghĩa chính |
| --- | --- |
| `select()` | Chờ đến khi selection có điều kiện hoàn tất; có thể được đánh thức bởi `wakeup()`/interrupt/close. |
| `select(long timeout)` | Chờ tối đa thời gian nhất định tính bằng millisecond nếu timeout dương; `timeout == 0` có nghĩa chờ không giới hạn theo API. |
| `selectNow()` | Thực hiện selection **không chờ**. |
| `wakeup()` | Yêu cầu đánh thức một thao tác `select` đang hoặc sắp bị chặn; có hiệu lực đối với chu kỳ chọn. |
| `close()` | Đóng selector; các đăng ký liên quan bị hủy, không tự mặc nhiên đóng tất cả channel. |

`select()` trả về số key có thông tin readiness được cập nhật trong lần selection, **không** phải số request đã xử lý hay tổng số byte có thể đọc. Một lần trả 0 không nhất thiết là lỗi: có thể do timeout, wakeup hoặc ngữ cảnh chọn khác. Một event loop thực tế phải xử lý trả 0 hợp lý, tránh cứ quay vòng liên tục vì không có tiến triển.

Khi một thread khác cập nhật state ứng dụng để event loop cần xử lý nhanh, mô hình phổ biến:

```java
// Snippet: executed by producer thread.
pendingTasks.add(task); // Hàng đợi thread-safe do ứng dụng cấp.
selector.wakeup();
```

Event loop khi thức dậy sẽ lấy việc từ hàng đợi và cập nhật registration/interest ops. **Không** để producer thread trực tiếp chỉnh state không thread-safe của nhiều handler. Nếu quan tâm cấu hình concurrent selector, tham khảo quy tắc đồng bộ của JDK; đừng dựa vào “thường chạy đúng” để thay hợp đồng.

Waking selector **không gửi dữ liệu mạng** và không bảo đảm socket writable; đó chỉ là tín hiệu điều phối, sau đó event loop vẫn phải kiểm tra trạng thái channel và queue.

## 13. Những việc tuyệt đối không nên làm trong event loop

- **Không gọi blocking I/O** trong handler của một event loop quản lý nhiều kết nối: ví dụ JDBC đồng bộ, đọc file lớn trực tiếp hoặc network call blocking.
- **Không busy-spin khi `read/write == 0`.** Với non-blocking channel, quay về `select` và đợi readiness phù hợp.
- **Không giữ `OP_WRITE` thường trực khi outbound queue trống.** Readiness ghi có thể được thông báo liên tiếp làm nóng CPU.
- **Không giả định `readyOps` bảo đảm chuyển một số byte nhất định.** Lệnh `read/write` vẫn có thể chuyển ít, thậm chí 0.
- **Không dùng một `ByteBuffer`/parser state duy nhất cho mọi connection** nếu dữ liệu có thể xen kẽ; mỗi connection cần state riêng hoặc cơ chế sở hữu được kiểm soát.
- **Không xử lý toàn bộ một connection vô hạn trong một readiness**. Giới hạn số byte, số frame hoặc thời gian mỗi key để đảm bảo fairness.
- **Không giữ hàng đợi outbound không giới hạn**. Kết nối chậm có thể khiến ứng dụng hết bộ nhớ.
- **Không bỏ qua khóa invalid hoặc channel đóng** khi dọn tài nguyên; `CancelledKeyException`/`ClosedChannelException` có thể xảy ra nếu state thay đổi.
- **Không dùng Selector như sự thay thế cho application protocol**: framing, encoding, validation, authorization, timeout và recovery vẫn thuộc tầng ứng dụng.

## 14. Mô hình kiến trúc một thread và cách mở rộng

Với một số lượng lớn connection, một luồng theo dõi readiness của nhiều channel là hiệu quả khi từng handler làm việc nhẹ. Khi hệ thống tăng tải, có thể dùng **nhiều event-loop thread**, mỗi luồng sở hữu selector riêng và tập connection khác nhau, kết hợp worker pool cho CPU/việc blocking. Việc một kênh thuộc selector nào là quyết định kiến trúc; tránh đồng thời xử lý cùng một connection từ nhiều event loop khi chưa có chiến lược ownership.

Ví dụ phân tầng:

```text
                      Acceptor / ServerSocketChannel
                                  |
                       Chấp nhận TCP connection
                                  |
                           Phân chia connection
                          /                 \
                 Event loop A            Event loop B
                   Selector A              Selector B
                   N sockets               M sockets
                      |                       |
               Decode + queue          Decode + queue
                          \                 /
                           Worker pool
                        (CPU/blocking jobs)
                                  |
                         Kết quả qua task queue
                         + selector.wakeup()
```

Đây là mô hình minh họa, không phải yêu cầu bắt buộc mọi hệ thống phải dùng nhiều selector. Với dịch vụ có traffic vừa phải, một event loop đơn giản, rõ ràng và đo được có thể đủ; thêm nhiều thread/selector đòi quản lý thread ownership, hàng đợi, đồng bộ state và shutdown phức tạp hơn.

### Độ phức tạp và giới hạn

Selector giảm nhu cầu giữ một thread blocking trên mỗi connection, nhưng **không làm số socket/file descriptor miễn phí**. Tài nguyên OS, bộ nhớ mỗi connection, số buffer, quota, latency của handler, TLS, timeout và backpressure vẫn giới hạn sức chứa. Hiệu năng thực tế phải được đo với mẫu traffic đại diện.

Không phải mọi channel đều hỗ trợ selector, không phải mọi loại I/O đều là readiness API. Ví dụ các stream/file channel thông thường có thể cần chiến lược xử lý khác. Lựa chọn event loop dựa trên mô hình workload và khả năng kiểm soát state.

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `IllegalBlockingModeException` | `register` khi channel đang blocking hoặc đổi sang blocking khi còn đăng ký. | `configureBlocking(false)` trước `register`; quản lý lifecycle rõ. |
| `IllegalArgumentException` tại `register` | Interest ops không thuộc `validOps()` của channel. | Chọn đúng OP_ACCEPT/CONNECT/READ/WRITE theo loại channel. |
| CPU 100% khi ít traffic | Luôn bật `OP_WRITE` hoặc spin khi `read/write == 0`. | Gỡ OP_WRITE khi queue trống; chờ readiness/wakeup. |
| Một request bị xử lý lặp | Không xóa key trong `selectedKeys()`. | Dùng iterator.remove() ngay trong vòng duyệt. |
| `CancelledKeyException` | Key bị cancel/đóng channel rồi vẫn kiểm tra readiness/interest. | Kiểm tra `isValid()` và dừng handler khi đóng. |
| Một connection làm chậm toàn bộ server | Handler blocking, CPU nặng hoặc loop xử lý không giới hạn. | Budget mỗi event, chuyển blocking/CPU sang worker. |
| Lệnh `write` báo thành công nhưng client nhận thiếu | Không lặp theo `ByteBuffer.hasRemaining()`, mất state khi partial write. | Giữ buffer pending, kích OP_WRITE đến khi gửi hết. |
| Server chờ mãi dù client đã gửi một phần | Parser đòi một frame đầy đủ nhưng không giữ state/compact đúng. | Xây framing, lưu input giữa các lượt và giới hạn kích thước. |
| Không thấy client kết nối | Quên đăng ký `OP_ACCEPT` hoặc `finishConnect()` với client non-blocking. | Phân biệt server/client lifecycle và OP_CONNECT. |
| Sau `wakeup()` không có key mới | Wakeup chỉ đánh thức `select`, không tạo I/O readiness. | Xử lý hàng đợi task rồi kiểm tra key như bình thường. |
| Dọn socket nhưng selector vẫn còn key invalid | Cancel được xử lý theo selection lifecycle; selected set chưa được dọn. | Hủy key, đóng channel, bỏ key đã xử lý và đóng selector khi shutdown. |

Trong khi debug, log có cấu trúc cho mỗi connection: ID, interest ops, ready ops, bytes read/written, `buffer.position/limit`, số byte pending, nguyên nhân đóng và thời gian xử lý handler. Cẩn trọng không log payload chứa thông tin nhạy cảm hoặc làm logger blocking trong event loop.

## 16. Bài tập thực hành

**Bài 1 — Thêm channel thứ ba.** Mở rộng chương trình demo với `Pipe c`, đăng ký thêm `SourceChannel` non-blocking và gửi `gamma\n`. Chỉnh điều kiện hoàn thành để đợi 3 thông điệp. Dùng `TreeMap` để giữ kết quả có thứ tự, không phụ thuộc thứ tự readiness.

**Bài 2 — Tách thông điệp thành nhiều chunk.** Đổi đoạn `ByteBuffer.allocate(3)` thành `allocate(1)` rồi `allocate(5)`. Chứng minh output không thay đổi nhờ `Session.pending` và xử lý newline. Giải thích vì sao chỉ gọi `read` một lần rồi lập tức chuyển nội dung thành request là sai.

**Bài 3 — OP_WRITE và backpressure.** Thiết kế outbound queue gồm ba `ByteBuffer` cho mỗi kết nối. Viết pseudocode bật `OP_WRITE` nếu còn pending; tắt khi queue hết; giữ `position` của buffer khi `write == 0`. Thêm quota cho số byte chờ để tránh tăng bộ nhớ vô hạn.

**Bài 4 — TCP echo server.** Dùng `ServerSocketChannel` non-blocking nhận client ở `OP_ACCEPT`, tạo `ConnectionState` với input/output buffers, đọc `OP_READ` và echo dữ liệu ở `OP_WRITE`. Giới hạn dung lượng hàng đợi; đóng socket khi `read == -1` và không còn output cần flush. Kiểm thử hai client gửi từng nửa thông điệp.

**Bài 5 — Thread khác cập nhật event loop.** Tạo một task queue thread-safe. Producer thêm tác vụ rồi gọi `selector.wakeup()`. Event loop nhận task, cập nhật interest ops và xử lý trong thread sở hữu selector. Giải thích tại sao không truyền một `ByteBuffer` mutable cho nhiều luồng mà không quản lý ownership.

**Bài 6 — Graceful shutdown.** Xây cơ chế ngừng nhận kết nối mới, tiếp tục xả outbound queue có deadline, sau đó cancel keys, đóng channels rồi đóng selector. Ghi lại những trường hợp timeout, exception và channel đã đóng để tránh resource leak.

### Tự kiểm tra

1. `Selector.select()` trả về các byte đã đọc hay danh sách channel có readiness?
2. Vì sao `SocketChannel` cần `configureBlocking(false)` trước đăng ký?
3. `interestOps` khác `readyOps` thế nào, và vì sao `OP_WRITE` không nên luôn bật?
4. Khi `socket.read(buffer) == 0`, ta có kết luận EOF hay phải chờ lần readiness tiếp?
5. `key.cancel()` có tự đóng socket không?
6. Vì sao `iterator.remove()` quan trọng khi duyệt `selectedKeys()`?
7. Một event-loop thread có thể xử lý nhiều socket, nhưng tại sao vẫn phải chuyển thao tác blocking/CPU nặng ra ngoài?
8. Vì sao parser cần xử lý partial reads, partial writes và nhiều frame trong cùng một đợt đọc?

## 17. Tham khảo chính thức

- [Java SE 21 — Selector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): các tập key, selection, wakeup và vòng đời.
- [Java SE 21 — SelectionKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html): interest/ready ops, attachments, key cancellation và bitmask.
- [Java SE 21 — SelectableChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectableChannel.html): non-blocking, valid ops và registration.
- [Java SE 21 — SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking connect, read/write và EOF.

**Ghi nhớ:** Selector là công cụ **multiplex readiness của nhiều selectable channel trên một event-loop thread**. Đăng ký non-blocking channel bằng đúng interest ops, duyệt và xóa selected keys, giữ state riêng mỗi connection, xử lý `read/write` có thể chỉ chuyển một phần, bật `OP_WRITE` khi thật sự có dữ liệu và không cho công việc blocking giữ chân event loop.
