# Đưa channel sang non-blocking và đăng ký SelectionKey trong Java NIO

## 1. Mục tiêu và bức tranh tổng thể

Trong Java NIO, **`Selector` theo dõi nhiều `SelectableChannel` bằng một hoặc một số ít thread**. Để một channel tham gia cơ chế này, cần **đưa nó sang chế độ non-blocking trước**, sau đó **đăng ký với `Selector` bằng `register(...)`**. Kết quả đăng ký là một **`SelectionKey`**: đối tượng biểu diễn mối quan hệ giữa **một channel**, **một selector**, **những sự kiện ứng dụng muốn quan tâm** và **những sự kiện hiện được hệ điều hành báo sẵn sàng**.

Ví dụ tối giản cho một TCP server:

~~~java
// Trích đoạn: selector và server đã được khởi tạo.
server.bind(new InetSocketAddress("127.0.0.1", 8080));
server.configureBlocking(false);
SelectionKey key = server.register(selector, SelectionKey.OP_ACCEPT);
~~~

Sau `register`, server **chưa tự accept hay đọc payload**. Nó chỉ nói với selector: “hãy thông báo khi có thể nhận kết nối mới”. Vòng lặp sự kiện gọi `selector.select()`, lấy các key được chọn trong `selectedKeys()`, rồi xử lý `isAcceptable()`, `isConnectable()`, `isReadable()` hoặc `isWritable()` tương ứng.

**Quy tắc quan trọng nhất:**

~~~text
open channel
  → bind/connect (nếu API và ngữ cảnh cần)
  → configureBlocking(false)
  → register(selector, interestOps [, attachment])
  → selector.select(...)
  → duyệt selectedKeys và remove từng key
  → kiểm tra readyOps, thực hiện I/O không blocking
  → cập nhật interestOps khi nhu cầu I/O thay đổi
  → cancel/close khi kết thúc
~~~

Đối với client TCP non-blocking, `connect()` có thể còn đang tiến hành khi đăng ký `OP_CONNECT`; không bắt buộc kết nối hoàn tất trước khi gọi `register`. Đối với server TCP, phải **bind trước khi `accept()` hoạt động**, và nên bind trước khi đợi `OP_ACCEPT`.

## 2. Ba đối tượng: Channel, Selector và SelectionKey

| Thành phần | Vai trò | API thường dùng |
|---|---|---|
| `SelectableChannel` | Đầu mối I/O có thể chuyển giữa blocking và non-blocking | `configureBlocking(false)`, `isBlocking()`, `register(...)`, `keyFor(...)`, `validOps()` |
| `Selector` | Bộ điều phối nhận thông báo **readiness** của các channel đã đăng ký | `Selector.open()`, `select()`, `select(timeout)`, `selectNow()`, `selectedKeys()`, `wakeup()` |
| `SelectionKey` | “Giấy đăng ký” cho **một cặp channel + selector** | `interestOps()`, `readyOps()`, `isReadable()`, `attachment()`, `cancel()` |

Một channel chỉ có **một key cho mỗi selector** nhưng có thể đăng ký với nhiều selector khác nhau theo các quy tắc của API. `selector.keys()` và `selector.selectedKeys()` không phải một tập: tập đầu chứa các đăng ký hiện có; tập sau chứa các key được chọn bởi thao tác selection trước đó và chưa được ứng dụng loại khỏi tập được chọn.

~~~text
ServerSocketChannel #A -- register(OP_ACCEPT) ---+
                                                  |
SocketChannel #B ------ register(OP_READ) --------+--> Selector #1
                                                  |      |
SocketChannel #C -- register(OP_READ|OP_WRITE) ---+      +--> select()
                                                         +--> selectedKeys()
                                                         +--> SelectionKey.readyOps
~~~

`Selector` là bộ ghép nhiều **readiness event**, không chuyển một channel thành thread riêng; cũng không tự viết business logic, tự gửi dữ liệu, tự decode UTF-8, tự định nghĩa ranh giới request hoặc tự giải phóng socket.

## 3. Bước bắt buộc: `configureBlocking(false)`

### 3.1. Mặc định là blocking

`ServerSocketChannel.open()` và `SocketChannel.open()` tạo channel mới với **blocking mode**. Kiểm tra:

~~~java
ServerSocketChannel server = ServerSocketChannel.open();
System.out.println(server.isBlocking()); // true khi mới mở
server.configureBlocking(false);
System.out.println(server.isBlocking()); // false
~~~

Đây là **đoạn minh họa**, cần đóng `server` sau khi dùng. Trong blocking mode, gọi `accept()` thường chờ kết nối đến; gọi `read()` có thể chờ byte. Trong non-blocking mode, thao tác I/O trả về ngay với lượng công việc hiện làm được: `accept()` có thể trả `null`, `SocketChannel.read()` có thể trả `0`, `write()` có thể ghi ít hơn số byte mong đợi.

### 3.2. Thứ tự không được đảo

Đăng ký một selectable channel **đang blocking** vào selector ném `IllegalBlockingModeException`.

~~~java
// SAI: server mới mở mặc định blocking.
ServerSocketChannel server = ServerSocketChannel.open();
SelectionKey badKey = server.register(selector, SelectionKey.OP_ACCEPT);
// ↑ IllegalBlockingModeException
~~~

Đúng:

~~~java
// Đúng theo thứ tự; giả sử selector còn mở.
try (ServerSocketChannel server = ServerSocketChannel.open()) {
    server.bind(new InetSocketAddress("127.0.0.1", 0));
    server.configureBlocking(false);
    SelectionKey key = server.register(selector, SelectionKey.OP_ACCEPT);
}
~~~

Cũng **không thể tùy tiện quay về `configureBlocking(true)`** khi channel vẫn còn đăng ký với một hay nhiều selector. Việc đó ném `IllegalBlockingModeException`. `key.cancel()` chỉ **đánh dấu hủy đăng ký**; việc deregister thường được hoàn tất trong một selection operation tiếp theo. `isRegistered()` có thể vẫn là `true` ngay sau `cancel()`. Đừng viết code giả định `cancel()` tức thì cho phép đổi sang blocking.

### 3.3. Mode của listening channel khác mode của accepted channel

Đây là điểm thường sai khi xây TCP server NIO:

- `ServerSocketChannel` đã `configureBlocking(false)` để selector theo dõi `OP_ACCEPT`.
- `ServerSocketChannel.accept()` trả về một **`SocketChannel` mới** cho client khi có kết nối sẵn sàng.
- Theo Javadoc Java 17, **SocketChannel vừa được accept mặc định ở blocking mode**, **bất kể listener đang blocking hay non-blocking**.
- Do đó **phải gọi `accepted.configureBlocking(false)` trên mỗi accepted channel** trước khi `accepted.register(selector, SelectionKey.OP_READ)`.

~~~java
SocketChannel accepted = server.accept();
if (accepted != null) {
    accepted.configureBlocking(false); // Không được bỏ dòng này!
    accepted.register(selector, SelectionKey.OP_READ);
}
~~~

Trong non-blocking mode, `server.accept()` **có thể trả `null`** nếu chưa có kết nối đang chờ. Một readiness event chỉ là gợi ý ở một thời điểm; không dùng `accept() != null` như giả định bất biến ngay sau `isAcceptable()`.

## 4. Đăng ký `SelectionKey` và các dạng overload

### 4.1. Cú pháp cơ bản

~~~java
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
~~~

hoặc thêm attachment:

~~~java
ByteBuffer inbound = ByteBuffer.allocate(4096);
SelectionKey key = channel.register(
        selector, SelectionKey.OP_READ, inbound);
~~~

`register(selector, ops, attachment)` tạo/định vị key đại diện cho cặp channel-selector, đặt **interest set** ban đầu, đồng thời cho phép gắn **một đối tượng trạng thái ứng dụng** (attachment). Khi có nhiều kết nối, attachment là chỗ thuận tiện để lưu buffer nhận, buffer gửi, parser, session ID hoặc trạng thái giao thức **riêng từng connection**.

`register(selector, ops)` tương đương gọi `register(selector, ops, null)`; khi đã có key, đối số attachment `null` **không tự xóa attachment cũ** theo hợp đồng của `register`. Muốn xóa attachment hiện tại, dùng `key.attach(null)` nếu cần.

### 4.2. Giá trị trả về và key “đã đăng ký”

Khi cùng channel gọi `register` lần nữa với **cùng selector** và key hiện hành chưa bị cancel, API **trả lại cùng key**, cập nhật `interestOps` và attachment nếu truyền attachment khác `null`; nó **không tạo thêm đăng ký thứ hai** trên cùng cặp channel-selector.

~~~java
// Trích đoạn trên SocketChannel non-blocking và Selector còn mở.
SelectionKey first = socket.register(selector, SelectionKey.OP_READ);
SelectionKey second = socket.register(
        selector, SelectionKey.OP_READ | SelectionKey.OP_WRITE);

System.out.println(first == second); // true (nếu key vẫn hợp lệ)
~~~

Việc đưa `OP_WRITE` vào ví dụ trên **chỉ nhằm minh họa bitmask**, không phải lời khuyên đăng ký `OP_WRITE` liên tục cho mọi socket.

Có thể dùng `channel.keyFor(selector)` để tìm key hiện có (hoặc `null` nếu không còn đăng ký với selector này); `channel.isRegistered()` chỉ trả lời có đăng ký với **bất kỳ selector nào** hay không. Với key đã cancel, `register` lại trước khi việc hủy hoàn tất có thể gây `CancelledKeyException`; hãy xử lý vòng đời rõ ràng, không retry mù.

## 5. Interest set và ready set: hai khái niệm khác nhau

Một `SelectionKey` có hai **bitmask** quan trọng:

- **`interestOps()`:** tập thao tác mà ứng dụng **muốn selector giám sát**; ví dụ `OP_READ` hoặc `OP_READ | OP_WRITE`.
- **`readyOps()`:** tập thao tác mà **lần selection** xác định có thể thực hiện; key có thể sẵn sàng với một phần của interest set.

Ví dụ:

~~~text
interestOps = OP_READ | OP_WRITE
readyOps    = OP_WRITE

=> Ứng dụng quan tâm cả đọc lẫn ghi, nhưng lần này chỉ phát hiện khả năng ghi.
=> Không được coi OP_READ là sẵn sàng chỉ vì đã đưa nó vào interestOps.
~~~

Các bit của `SelectionKey`:

| Bit | Giá trị hex | Channel điển hình | Ý nghĩa của readiness |
|---|---|---|---|
| `OP_ACCEPT` | `0x10` | `ServerSocketChannel` | Có kết nối mới có thể được `accept` |
| `OP_CONNECT` | `0x08` | `SocketChannel` | Kết nối non-blocking đang ở trạng thái có thể kiểm tra/hoàn tất |
| `OP_READ` | `0x01` | `SocketChannel`, `DatagramChannel`, `Pipe.SourceChannel` | Có thể đọc, hoặc có sự kiện kết thúc/lỗi cần đọc xử lý |
| `OP_WRITE` | `0x04` | `SocketChannel`, `DatagramChannel`, `Pipe.SinkChannel` | Có thể ghi ít nhất một phần hoặc tiếp nhận trạng thái ghi tương ứng |

Readiness là **gợi ý**, không phải cam kết số byte tối thiểu hay việc peer đã xử lý. Hệ điều hành và thời điểm thực hiện I/O có thể làm trạng thái thay đổi sau `select`. Vì vậy code xử lý phải chấp nhận `read(...) == 0`, `write(...) == 0` hoặc `accept() == null` trên channel non-blocking.

Có thể kiểm tra:

~~~java
if (key.isValid() && key.isReadable()) {
    SocketChannel ch = (SocketChannel) key.channel();
    // Đọc chỉ khi channel có kiểu và trạng thái phù hợp.
}
~~~

Các hàm `isReadable()`, `isWritable()`, `isAcceptable()`, `isConnectable()` kiểm tra **bit trong ready set**, không phải `interestOps`. Không gọi các hàm này vô điều kiện trên key đã bị cancel; `CancelledKeyException` có thể xuất hiện. Trong vòng lặp đa thread, validity có thể thay đổi sau lần check nên cần thêm xử lý lỗi/race phù hợp.

## 6. `validOps()`: chỉ đăng ký loại sự kiện channel hỗ trợ

Không phải tất cả channel đều hiểu mọi flag.

| Loại channel | Ops hợp lệ |
|---|---|
| `ServerSocketChannel` | `OP_ACCEPT` |
| `SocketChannel` | `OP_CONNECT | OP_READ | OP_WRITE` |
| `DatagramChannel` | `OP_READ | OP_WRITE` |
| `Pipe.SourceChannel` | `OP_READ` |
| `Pipe.SinkChannel` | `OP_WRITE` |

Kiểm tra bằng `channel.validOps()` thay vì giả định tất cả luôn chấp nhận bốn bit. Ví dụ đăng ký `OP_ACCEPT` cho `SocketChannel` hoặc `OP_READ` cho `ServerSocketChannel` là không hợp lệ và gây `IllegalArgumentException`.

~~~java
// Trích đoạn:
int requested = SelectionKey.OP_READ | SelectionKey.OP_WRITE;
if ((requested & ~socket.validOps()) != 0) {
    throw new IllegalArgumentException("Unsupported interest operation");
}
socket.register(selector, requested);
~~~

`ops=0` cũng hợp lệ: key vẫn đăng ký nhưng không bày tỏ interest nào; dùng khi cần tạm ngừng theo dõi I/O. Tuy nhiên lúc này selector sẽ không thông báo readiness cho các bit đã tắt. Cần quản lý khi nào bật lại để không “treo” logic ứng dụng.

## 7. Ví dụ hoàn chỉnh Java 17+: server non-blocking, register, select và đọc dữ liệu

Ví dụ sau chỉ dùng **localhost/loopback** và một port được hệ điều hành cấp phát, nên không cần Internet hay server bên ngoài. Nó chủ động dùng một **client ở blocking mode** để giữ phần demo tập trung vào đăng ký selector phía server. Chỉ **server listener và accepted socket** được giám sát bằng selector.

Luồng demo:

1. `Selector.open()`; `ServerSocketChannel.open()`; bind loopback port `0`.
2. `server.configureBlocking(false)` rồi đăng ký `OP_ACCEPT`.
3. Client kết nối và gửi dòng ASCII `PING\n`.
4. `selector.select(1000)` trả về khi có readiness; vòng lặp lấy và **remove** từng selected key.
5. Khi `OP_ACCEPT`: `accept()`, **đưa accepted channel sang non-blocking**, đăng ký `OP_READ` kèm ByteBuffer riêng.
6. Khi `OP_READ`: đọc vào buffer, kiểm tra delimiter newline; nếu đủ, in `PING` và đóng accepted channel.
7. Có deadline tổng thể 5 giây để demo không chờ mãi khi chạy trong môi trường bị hạn chế.

Tạo tệp **`SelectorRegistrationDemo.java`**:

~~~java
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

public class SelectorRegistrationDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(loopback, 0));
            server.configureBlocking(false);
            SelectionKey listenKey =
                    server.register(selector, SelectionKey.OP_ACCEPT);
            System.out.println("listenInterest=" +
                    (listenKey.interestOps() == SelectionKey.OP_ACCEPT));

            try (SocketChannel client = SocketChannel.open(
                    new InetSocketAddress(loopback,
                            server.socket().getLocalPort()))) {
                ByteBuffer request = StandardCharsets.US_ASCII.encode("PING\n");
                while (request.hasRemaining()) {
                    client.write(request);
                }
                client.shutdownOutput();

                boolean done = false;
                long deadline = System.nanoTime() + 5_000_000_000L;
                while (!done && System.nanoTime() < deadline) {
                    if (selector.select(1000) == 0) {
                        continue;
                    }
                    Iterator<SelectionKey> keys = selector.selectedKeys().iterator();
                    while (keys.hasNext()) {
                        SelectionKey key = keys.next();
                        keys.remove();
                        if (!key.isValid()) {
                            continue;
                        }
                        if (key.isAcceptable()) {
                            ServerSocketChannel listener =
                                    (ServerSocketChannel) key.channel();
                            SocketChannel peer = listener.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ,
                                        ByteBuffer.allocate(64));
                                System.out.println("acceptedNonBlocking=" +
                                        !peer.isBlocking());
                            }
                        } else if (key.isReadable()) {
                            SocketChannel peer = (SocketChannel) key.channel();
                            ByteBuffer data = (ByteBuffer) key.attachment();
                            int n = peer.read(data);
                            if (n == -1) {
                                throw new IOException("EOF before newline");
                            }
                            for (int i = 0; i < data.position(); i++) {
                                if (data.get(i) == '\n') {
                                    data.flip();
                                    String text = StandardCharsets.US_ASCII
                                            .decode(data).toString();
                                    System.out.println("received=" +
                                            text.substring(0, text.indexOf('\n')));
                                    done = true;
                                    key.cancel();
                                    peer.close();
                                    break;
                                }
                            }
                            if (!done && !data.hasRemaining()) {
                                throw new IOException("Request exceeded buffer");
                            }
                        }
                    }
                }
                if (!done) {
                    throw new IOException("Selector deadline expired");
                }
            }
        }
    }
}
~~~

Chạy bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 SelectorRegistrationDemo.java
java SelectorRegistrationDemo
~~~

**Stdout đã được kiểm chứng trên OpenJDK 24 khi biên dịch `--release 17`:**

~~~text
listenInterest=true
acceptedNonBlocking=true
received=PING
~~~

Giải thích kết quả:

- `listenInterest=true`: key của listener có interest set chính xác `OP_ACCEPT`.
- `acceptedNonBlocking=true`: kênh **vừa accept** đã được chuyển sang non-blocking **trước khi đăng ký `OP_READ`**. Nếu bỏ `peer.configureBlocking(false)`, `peer.register(...)` sẽ gây `IllegalBlockingModeException`.
- `received=PING`: selector báo readiness, accepted SocketChannel nhận byte, parser tìm newline và trích xuất dòng hoàn chỉnh.

**Giới hạn minh họa:** đây không phải production multi-client server. Nó phục vụ một request ngắn, chỉ cấp buffer 64 byte và kết thúc sau một message. Nó không có protocol đầy đủ, không ghi response, không hỗ trợ nhiều frame nối tiếp, không thay thế TLS/HTTP server, không bảo đảm graceful shutdown cho một số lượng lớn connection. Client được cố ý để blocking; nếu cần kết nối client bằng selector thì dùng `OP_CONNECT` và `finishConnect()` như phần sau.

## 8. Vì sao phải `keys.remove()` khi duyệt `selectedKeys()`?

Một thao tác `selector.select(...)` thêm/cập nhật những key có sự kiện readiness trong **selected-key set**. Tập này **không tự bị xóa sạch chỉ vì bạn đã đọc nó**. Nếu quên loại key ra sau khi xử lý, một key cũ có thể tiếp tục nằm trong tập, làm code xử lý lại sự kiện hoặc báo thống kê sai.

Cách phổ biến:

~~~java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();                   // Bỏ khỏi selected-key set
    if (!key.isValid()) continue;

    if (key.isAcceptable()) {
        // Chấp nhận kết nối mới.
    } else if (key.isConnectable()) {
        // Hoàn tất một connect non-blocking.
    } else {
        if (key.isReadable()) {
            // Nhận dữ liệu.
        }
        if (key.isWritable()) {
            // Gửi dữ liệu đang đợi.
        }
    }
}
~~~

Đây là **khung xử lý sự kiện**, không phải chương trình chạy độc lập. `it.remove()` chỉ bỏ key khỏi **selected-key set**, **không hủy đăng ký** channel với selector. Muốn hủy đăng ký, gọi `key.cancel()` và/hoặc đóng channel khi phù hợp.

Trong khung trên, `isReadable()` và `isWritable()` được kiểm tra **độc lập** vì một selected key có thể sẵn sàng cả đọc lẫn ghi trong cùng lượt. Đừng đặt một chuỗi `else if` làm bỏ lỡ một phía khi ứng dụng cần phục vụ cả hai. Với `OP_ACCEPT` và `OP_CONNECT` thường có xử lý riêng theo loại channel.

`selector.keys()` cho thấy toàn bộ registration hiện còn được quản lý; **không dùng `keys().clear()` để hủy tất cả**. Tập key tổng không hỗ trợ sửa trực tiếp như selected-key set; hủy key bằng `cancel` và quản lý lifecycle channel.

## 9. Quản lý từng connection bằng attachment

Với nhiều accepted socket, mỗi kết nối cần buffer nhận/ghi riêng. Có thể gắn đối tượng session state:

~~~java
// Trích đoạn khai báo trạng thái ứng dụng.
final class ConnectionState {
    final ByteBuffer inbound = ByteBuffer.allocate(8192);
    ByteBuffer outbound;
    boolean peerFinishedSending;
}
~~~

Khi accept:

~~~java
SocketChannel peer = server.accept();
if (peer != null) {
    peer.configureBlocking(false);
    peer.register(selector, SelectionKey.OP_READ, new ConnectionState());
}
~~~

Khi selected key sẵn sàng:

~~~java
// Trích đoạn, key là đăng ký hợp lệ của một SocketChannel.
ConnectionState state = (ConnectionState) key.attachment();
SocketChannel peer = (SocketChannel) key.channel();
int n = peer.read(state.inbound);

if (n == -1) {
    state.peerFinishedSending = true;
    // Xử lý EOF/khung còn dang dở theo protocol, rồi quyết định đóng.
} else if (n > 0) {
    state.inbound.flip();
    // Parse được bao nhiêu message đầy đủ thì xử lý bấy nhiêu.
    // Giữ lại byte chưa parse, không đánh rơi nửa frame.
    state.inbound.compact();
}
~~~

**Đây là các trích đoạn liên kết**, không phải chương trình tự chạy. `ConnectionState` phải do ứng dụng cung cấp; parser và outbound queue phải được triển khai theo protocol. `ByteBuffer` giữ trạng thái riêng từng connection, tránh dùng chung một `ByteBuffer` cho mọi client mà không có quy tắc ownership.

Không giữ reference tới session/buffer vô hạn sau khi key bị hủy: đóng channel và loại tham chiếu, hàng đợi, timer hoặc map liên quan để tránh memory leak.

## 10. `OP_CONNECT`: đăng ký client đang kết nối theo non-blocking

Với `SocketChannel` ở non-blocking mode, `connect(remote)` có thể hoàn tất ngay (`true`) hoặc đang chờ hoàn tất (`false`). Nếu kết nối chưa xong, đăng ký `OP_CONNECT`:

~~~java
// Trích đoạn: selector đã được mở; remote là InetSocketAddress hợp lệ.
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);
boolean alreadyConnected = client.connect(remote);

SelectionKey key = client.register(
        selector,
        alreadyConnected ? SelectionKey.OP_READ : SelectionKey.OP_CONNECT
);
~~~

Nếu lần selection tiếp theo thấy `key.isConnectable()`:

~~~java
// Trích đoạn cho cùng client ở non-blocking mode.
if (key.isValid() && key.isConnectable()) {
    SocketChannel client = (SocketChannel) key.channel();
    if (client.finishConnect()) {
        key.interestOps(SelectionKey.OP_READ);
        // Kết nối TCP đã hoàn tất; bắt đầu protocol của ứng dụng.
    }
}
~~~

`finishConnect()` có thể ném `IOException` nếu kết nối bị từ chối, timeout hoặc lỗi ở tầng hệ điều hành. Đăng ký `OP_CONNECT` **không tự gửi request ứng dụng**, cũng không bảo đảm kết nối cuối cùng sẽ thành công. Nếu `connect` đã trả `true`, không cần đợi `OP_CONNECT`; chuyển sang interest phù hợp ngay.

Trong chương trình có outbound data đang chờ gửi, có thể đổi thành `OP_READ | OP_WRITE` **chỉ khi cần** (và tắt `OP_WRITE` khi đã gửi hết). Một client HTTP hoàn chỉnh còn cần message framing, timeout, shutdown và chính sách lỗi ngoài kết nối TCP.

## 11. `OP_WRITE`: tránh busy loop và mất dữ liệu khi ghi một phần

Sai lầm điển hình:

~~~java
// Dễ gây busy loop khi socket có sẵn send-buffer capacity:
socket.register(selector, SelectionKey.OP_READ | SelectionKey.OP_WRITE);
~~~

Trên nhiều hệ điều hành, socket TCP thường **writable** phần lớn thời gian. Nếu luôn quan tâm `OP_WRITE`, selector có thể thức dậy liên tục dù ứng dụng không có byte nào cần gửi: vòng lặp chiếm CPU (“spin”) không có ích.

Quy tắc thực tế:

1. Mặc định chỉ đăng ký `OP_READ` sau khi connection đã sẵn sàng cho việc nhận.
2. Khi queue outbound có byte chưa gửi, bật thêm `OP_WRITE`.
3. Trong `isWritable()`, gọi `SocketChannel.write(ByteBuffer)`; sau lần ghi, `ByteBuffer.position()` thể hiện số byte đã chuyển ra local channel.
4. Nếu buffer vẫn `hasRemaining()`, giữ buffer đó cho lần writable tiếp theo. **Không `clear()` rồi ghi đè phần chưa gửi**.
5. Khi không còn outbound pending, **tắt `OP_WRITE`** để tránh thức dậy liên tục.

~~~java
// Trích đoạn: key hợp lệ, accepted SocketChannel, một outbound ByteBuffer.
if (key.isWritable()) {
    SocketChannel peer = (SocketChannel) key.channel();
    ByteBuffer data = (ByteBuffer) key.attachment(); // Ví dụ gắn outbound.
    peer.write(data);
    if (!data.hasRemaining()) {
        key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
    }
}
~~~

Đây chỉ là **một mảnh logic**, không phải vòng lặp hoàn chỉnh. Production app sẽ có connection state lưu **inbound và outbound riêng**, xử lý nhiều buffer, close, backpressure, cancellation và race condition.

`OP_WRITE` nghĩa socket có thể chấp nhận thêm **một phần** byte ở phía local; **không phải** ACK rằng phía bên kia đã nhận hoặc xử lý dữ liệu. `write` có thể trả **0** trong non-blocking mode; khi đó đừng chạy một vòng `while(hasRemaining)` vô hạn trên thread selector. Giữ phần dư và đợi readiness tiếp theo.

## 12. `Selector.select`, timeout và wakeup

Những API thường dùng:

| API | Ý nghĩa |
|---|---|
| `select()` | Chờ đến khi có readiness, bị wakeup/interrupt hoặc điều kiện được tài liệu cho phép làm nó trở về |
| `select(long timeout)`, với `timeout > 0` | Chờ tối đa khoảng thời gian yêu cầu tính bằng **mili giây** |
| `select(0)` | **Chờ không giới hạn theo timeout**, **không phải** poll tức thì |
| `selectNow()` | **Không chờ**; kiểm tra readiness hiện tại |
| `wakeup()` | Yêu cầu một thao tác selection hiện tại hoặc lần tiếp theo trở về; thường dùng để phối hợp thay đổi interest/cấu hình từ thread khác |

Đừng viết logic `if (selector.select() == 0) throw ...` rồi kết luận chắc chắn “không còn channel nào hoạt động”: selection có thể trở về do wakeup, interrupt hoặc những điều kiện khác, và readiness có thể đổi theo thời gian.

Ví dụ deadline:

~~~java
long deadline = System.nanoTime() + 5_000_000_000L;
while (System.nanoTime() < deadline) {
    int count = selector.select(1000);
    if (count == 0) {
        continue; // Chưa có selected key mới; kiểm tra deadline.
    }
    // Duyệt selectedKeys và xử lý.
}
~~~

Dùng `System.nanoTime()` cho **khoảng thời gian trôi qua trong cùng JVM**, không dùng làm timestamp có ý nghĩa giữa máy hoặc phiên JVM khác. Với deadline production, phải tính timeout còn lại thay vì luôn chờ một khoảng lớn vượt ngân sách; ví dụ demo dùng các đợt 1 giây và kiểm tra deadline trước mỗi đợt, nên có thể lệch tới một đợt selection.

Khi **thread khác** thay đổi `interestOps` hoặc đưa công việc vào queue, thời điểm cập nhật được quan sát bởi một lời gọi `select` đang diễn ra phụ thuộc quy tắc đồng bộ của selector; mô hình phổ biến là đặt task vào queue thread-selector rồi gọi `selector.wakeup()` để nó lấy task và cập nhật interest trước vòng lặp kế tiếp. Đừng sửa buffer, key và hàng đợi từ nhiều thread mà không định nghĩa rõ cơ chế phối hợp.

## 13. Sự kiện ready không thay thế protocol framing

Selector quan sát khả năng thực hiện **I/O ở mức kênh**, không biết thế nào là “đã đọc hết JSON”, “đã nhận đủ HTTP request” hay “đã có trọn vẹn bản tin dài N byte”.

Ví dụ client muốn gửi frame dài 100 byte nhưng một lần `read` đưa vào ByteBuffer 37 byte: `OP_READ` đã xuất hiện, `read()` trả 37, nhưng **message chưa đủ**. Khi parse:

~~~java
// Trích đoạn: channel là SocketChannel đã đăng ký OP_READ.
int bytes = channel.read(inbound);
if (bytes > 0) {
    inbound.flip();   // Chuẩn bị đọc những byte thực nhận.
    // Chỉ tiêu thụ frame trọn vẹn; giữ tail chưa hoàn chỉnh.
    inbound.compact();
} else if (bytes == -1) {
    // EOF: đối tác đã đóng chiều gửi; kiểm tra frame còn dang dở.
} else {
    // bytes == 0 trong non-blocking mode: hiện chưa chuyển được byte nào.
}
~~~

Không đồng nhất `ByteBuffer.remaining() > 0` với “socket đã có dữ liệu mới”: đó là số byte còn trong **cửa sổ ByteBuffer** đang được thao tác. Sau `flip`, remaining thường là byte chưa parse; trước `flip`, remaining thường là **không gian còn được phép ghi**.

Nếu một frame lớn hơn capacity, `compact` sẽ không tự mở rộng bộ nhớ. Thiết kế kích thước buffer và giới hạn payload để tránh parser bị kẹt khi buffer đầy nhưng chưa đủ message.

## 14. Quản lý lifecycle và hủy đăng ký an toàn

`SelectionKey` còn hợp lệ cho đến khi bị `cancel()`, đóng channel hoặc đóng selector. Nhưng hủy key **không đồng nghĩa** đóng socket: trách nhiệm quản lý resource ở ứng dụng.

~~~java
// Trích đoạn cleanup một kết nối; có thể ném IOException khi close.
key.cancel();
key.channel().close();
~~~

Khi **đóng channel**, các key đăng ký liên quan được cancel ngầm. Khi **đóng selector**, các key của selector bị invalidated và deregistered; các channel liên quan **không nhất thiết được đóng bởi việc đóng selector**. Do đó nên quản lý `Selector`, listening channel, accepted channels và client channels bằng resource ownership rõ ràng.

Trong server đa client, nên gom cleanup vào một hàm idempotent có thể được gọi từ lỗi đọc, lỗi ghi, EOF, timeout và shutdown:

~~~java
// Trích đoạn khung logic; state cleanup khác được ứng dụng triển khai.
static void closeConnection(SelectionKey key) {
    if (key == null) return;
    key.cancel();
    try {
        key.channel().close();
    } catch (java.io.IOException e) {
        // Ghi log phù hợp; không vô hạn retry thao tác đóng.
    }
}
~~~

Không trông chờ `key.isValid()` chuyển thành false như một dấu hiệu **đã đóng toàn bộ tài nguyên**: key invalid có thể do cancel riêng, trong khi channel vẫn open. `isRegistered()` còn có thể tạm thời là true cho đến khi selector xử lý các key bị hủy.

### Luồng nhiều client

Trong event loop thật, khi `OP_ACCEPT` phát sinh có thể có **nhiều connection** đang chờ. Với listener non-blocking, mô hình thường là:

~~~java
// Trích đoạn trong handler isAcceptable:
for (;;) {
    SocketChannel peer = server.accept();
    if (peer == null) break;
    peer.configureBlocking(false);
    peer.register(selector, SelectionKey.OP_READ, new ConnectionState());
}
~~~

Đây là trích đoạn cần class `ConnectionState` như phần 9. Không dùng vòng `while(true)` trên `accept()` của **listener blocking**, vì sau khi hết connection chờ thì nó sẽ chặn toàn bộ event loop.

Hạn chế số connection, tổng byte pending, thời hạn timeout và thời gian dành cho mỗi key; một connection gửi dữ liệu liên tục không được chiếm mãi thread-selector làm các connection khác đói tài nguyên.

## 15. Ngoại lệ, lỗi cấu hình và nguyên nhân phổ biến

| Dấu hiệu | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| `IllegalBlockingModeException` ngay lúc `register` | Channel vẫn blocking | Gọi `configureBlocking(false)` trước `register` |
| `IllegalBlockingModeException` khi `configureBlocking(true)` | Channel vẫn registered | Cancel và bảo đảm deregister xong trước khi trở về blocking |
| `IllegalArgumentException` khi đăng ký flags | `ops` chứa bit không thuộc `channel.validOps()` | Dùng `OP_ACCEPT` cho listener; `OP_READ/WRITE/CONNECT` cho socket |
| `CancelledKeyException` lúc truy cập key | Key đã bị cancel/close, hoặc đang ở giai đoạn deregister | Kiểm tra lifecycle, xử lý race, không tiếp tục sử dụng key |
| `ClosedChannelException` khi đăng ký | Channel đã đóng | Chỉ register channel mở |
| `ClosedSelectorException` khi đăng ký hoặc select | Selector đã đóng | Quản lý shutdown thứ tự rõ ràng |
| `IllegalSelectorException` | Channel và selector không tương thích `SelectorProvider` | Dùng provider thích hợp, tránh trộn provider không tương thích |
| `NotYetBoundException` từ `accept` | `ServerSocketChannel` chưa bind | Bind local endpoint trước |
| `accept() == null` | Listener non-blocking, hiện chưa có connection sẵn sàng | Trở về event loop, không xem là lỗi |
| `SocketChannel.read() == 0` | Tạm không có byte sẵn hoặc buffer không có remaining | Xét trạng thái ByteBuffer và đợi readiness tiếp |
| `SocketChannel.read() == -1` | Đã thấy EOF chiều đọc | Xử lý khung dở dang, cleanup thích hợp |
| `write()` gửi ít hơn length | Ghi không hoàn chỉnh, send buffer có hạn | Giữ phần outbound còn lại, đăng ký `OP_WRITE` khi cần |
| Selector loop dùng CPU cao | `OP_WRITE` luôn bật, không remove selected keys, hoặc loop chạy poll liên tục | Tắt `OP_WRITE` khi hết pending, remove key, tránh polling vô hạn |
| Đã gọi `cancel()` nhưng `isRegistered()` còn true | Deregistration có độ trễ | Đợi selector xử lý cancellation; đừng phỏng đoán hoàn tất tức thời |
| Server nhận kết nối nhưng `peer.register` lỗi | Accepted channel vẫn mặc định blocking | Gọi `peer.configureBlocking(false)` trên từng accepted channel |
| Interest thay đổi mà thread select chưa thức | Thay đổi từ thread khác không đồng bộ với vòng selector | Dùng task queue và `selector.wakeup()` phù hợp |

Đừng xử lý mọi exception bằng cách `continue` vô hạn: một key lỗi liên tục có thể khiến event loop spin và giữ tài nguyên. Phân loại lỗi **mỗi kết nối**, lỗi **listener**, lỗi **selector**, và chính sách **shutdown**.

## 16. Những điểm có thể kiểm tra bằng log và thử nghiệm

Một số thông tin chẩn đoán nên log **không chứa dữ liệu nhạy cảm**:

- Channel loại gì, `isOpen()`, `isBlocking()`, `isRegistered()`.
- Selector mở hay đóng; `key.isValid()`; bitmask `interestOps()` và `readyOps()`.
- Mỗi vòng `select` chọn được bao nhiêu key; có quên remove selected keys hay không.
- `SocketChannel.read`, `write` trả bao nhiêu byte; buffer `position/limit/remaining` trước và sau.
- Số accepted connection đang sống, số outbound bytes đang chờ, tổng buffer memory.
- Tần suất `OP_WRITE`, lỗi EOF, timeout nghiệp vụ, cancel/close và số lượng kết nối bị từ chối do quota.

Ví dụ cách in ops:

~~~java
// Trích đoạn; chỉ chạy khi key đang hợp lệ:
System.out.println("interest=" + key.interestOps());
System.out.println("ready=" + key.readyOps());
System.out.println("readable=" + key.isReadable());
~~~

Bitmask thường hiện dưới dạng số nguyên: `OP_READ=1`, `OP_WRITE=4`, `OP_CONNECT=8`, `OP_ACCEPT=16`. Nếu muốn log dễ đọc, kiểm tra từng bit thay vì dùng integer làm “mã sự kiện duy nhất”: một tập có thể chứa **nhiều bit** cùng lúc.

## 17. Chọn đúng cách tổ chức event loop

Một selector **không làm I/O tự động song song**. Thread-selector thường nên:

1. Xử lý task pending từ queue (ví dụ thay đổi interest do worker yêu cầu).
2. Gọi `select` với timeout/deadline phù hợp.
3. Duyệt và remove selected keys.
4. Với `OP_ACCEPT`, accept vừa đủ số connection theo fairness policy.
5. Với `OP_CONNECT`, gọi `finishConnect()` và đổi interest.
6. Với `OP_READ`, đọc đến mức hợp lý; tích lũy/parse message.
7. Với `OP_WRITE`, flush outbound có giới hạn, tắt writable interest nếu đã hết.
8. Đóng/cancel key lỗi hoặc EOF, giải phóng session state.
9. Lặp, kết hợp timeout và shutdown signal.

Nếu business logic mất nhiều thời gian (database, xử lý ảnh, gọi service khác), đừng chạy lâu ngay trong selector thread: giao cho worker thích hợp và đưa kết quả trở lại qua **task queue + wakeup**; quản lý data race, thứ tự phản hồi và backpressure.

Một app NIO tốt cần quan sát được **readiness ≠ hoàn tất I/O**, **register ≠ tự thực thi tác vụ**, **interest set ≠ ready set**, **cancel ≠ close**, và **non-blocking ≠ không bao giờ cần chờ deadline**.

## 18. Câu hỏi tự kiểm tra

**1. `SocketChannel.open()` mặc định blocking hay non-blocking?** Mặc định **blocking**; cần `configureBlocking(false)` trước khi đăng ký selector.

**2. `ServerSocketChannel` non-blocking gọi `accept()` trả về `SocketChannel`. Accepted channel có tự non-blocking không?** Không. Theo Java 17, nó **bắt đầu ở blocking mode**; phải chuyển riêng.

**3. `register(selector, OP_READ)` có nghĩa Java sẽ đọc ngay không?** Không. Nó chỉ thêm **interest**; event loop phải `select` rồi gọi `read`.

**4. Đưa `OP_WRITE` vào interest mãi có thể gây vấn đề gì?** Gây **busy loop** vì nhiều socket thường writable phần lớn thời gian, dù không có dữ liệu cần gửi.

**5. `key.isReadable()` dựa vào interest set hay ready set?** **Ready set**, là kết quả readiness selector quan sát.

**6. `selector.selectedKeys()` có tự xóa sạch khi xong vòng lặp không?** Không. Ứng dụng cần remove key đã xử lý; remove không phải cancel.

**7. `key.cancel()` có lập tức làm `channel.isRegistered() == false` và đóng socket không?** Không nhất thiết. Việc deregister có thể trì hoãn; cancel không tự đóng channel.

**8. `selector.select(0)` có tương đương `selectNow()` không?** Không. `select(0)` được định nghĩa là **đợi không có timeout**, còn `selectNow()` không blocking.

**9. Hai lần register cùng channel với cùng selector tạo hai SelectionKey?** Không. Trong khi key còn hiệu lực, API trả **cùng key** và có thể cập nhật interest/attachment.

**10. Key đăng ký `OP_ACCEPT | OP_READ` cho `ServerSocketChannel` có hợp lệ?** Không, vì listener chỉ hỗ trợ `OP_ACCEPT`.

**11. `SocketChannel.read(ByteBuffer) == 0` có chứng minh TCP đã đóng?** Không. EOF của chiều đọc là **`-1`**; 0 có thể do chưa sẵn data hoặc buffer không còn chỗ.

**12. Làm sao nhận một kết nối mới rồi đăng ký đọc?** `SocketChannel peer = server.accept();`, kiểm tra khác `null`, gọi `peer.configureBlocking(false)`, rồi `peer.register(selector, OP_READ, state)`.

**13. `isWritable()` có nghĩa client đã nhận được byte gửi đi không?** Không. Chỉ báo khả năng thao tác ghi cục bộ vào channel.

**14. Một thread khác bổ sung outbound data khi selector đang chờ phải làm gì?** Đồng bộ task/queue và dùng `selector.wakeup()` theo thiết kế để thay đổi interest và xử lý outbound đúng thời điểm.

## Tài liệu chính thức

- [Java SE 17 – SelectableChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html): `configureBlocking`, `register`, `validOps`, `keyFor`, quy tắc blocking.
- [Java SE 17 – SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOps`, `readyOps`, `OP_ACCEPT/CONNECT/READ/WRITE`, attachment và cancel.
- [Java SE 17 – Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select`, `selectedKeys`, tập key đã hủy và `wakeup`.
- [Java SE 17 – ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): `bind`, `accept`, non-blocking accept và mode mặc định của accepted channel.
- [Java SE 17 – SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): `connect`/`finishConnect`, partial read/write, EOF.
- [Java SE 17 – ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `compact`, `hasRemaining` và quản lý byte dở dang.

**Ghi nhớ:** Muốn dùng Selector, **`channel.configureBlocking(false)` trước `channel.register(selector, ops [, attachment])`**. `SelectionKey` phân biệt **interest** (muốn theo dõi) và **ready** (hiện được phát hiện sẵn sàng). Vòng lặp phải tự duyệt/xóa selected keys, xử lý non-blocking read/write/accept/connect, bật/tắt interest đúng lúc, bảo toàn dữ liệu chưa đọc/chưa ghi và dọn sạch tài nguyên.
