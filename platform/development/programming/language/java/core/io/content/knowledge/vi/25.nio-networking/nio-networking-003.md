# Connect, finishConnect, accept, read và write trong Java NIO mạng

## 1. Bức tranh tổng thể: từ thiết lập kết nối đến trao đổi byte

Java NIO cung cấp hai channel quan trọng cho mạng TCP:

- `ServerSocketChannel`: **lắng nghe** tại một địa chỉ/cổng và `accept()` một kết nối TCP đến, tạo ra `SocketChannel` cho phía server trao đổi dữ liệu.
- `SocketChannel`: đại diện một kết nối TCP; phía client dùng `connect(...)`/`finishConnect()` để thiết lập kết nối, cả hai phía dùng `read(...)` và `write(...)` để nhận/gửi byte.

Có thể sử dụng các channel này ở hai chế độ:

- **Blocking** (mặc định): những lời gọi có thể chờ đến khi một thao tác có thể hoàn tất theo hợp đồng, nhưng một `read` hoặc `write` vẫn không nhất thiết xử lý hết buffer.
- **Non-blocking** (`configureBlocking(false)`): lời gọi trả về khi chưa thể hoàn tất ngay; chương trình phải lưu trạng thái và thử tiếp vào lúc thích hợp, thường phối hợp `Selector`.

Luồng hoạt động điển hình:

~~~text
             SERVER                                  CLIENT
    ServerSocketChannel.open()                 SocketChannel.open()
               |                                        |
           bind(local)                                 |
               |                                  connect(remote)
               |                                        |
         accept() chờ/yield                    [có thể pending]
               |                                        |
       SocketChannel accepted                   finishConnect()
               |                                        |
               +----------- TCP connected --------------+
               |                                        |
         read() / write()                         write() / read()
               |                                        |
          close() / EOF                    shutdownOutput() / close()
~~~

`accept()` chỉ thuộc `ServerSocketChannel`. `connect()` và `finishConnect()` thuộc `SocketChannel`. Còn `read()/write()` dùng trên các `SocketChannel` của **cả hai đầu kết nối**; giao tiếp TCP là hai chiều.

**Điều cần phân biệt:** hoàn tất kết nối là một trạng thái khác với có dữ liệu để đọc hoặc chỗ trống để ghi. `finishConnect() == true` không có nghĩa bên kia đã gửi dữ liệu; `OP_READ`/`OP_WRITE` không có nghĩa một thông điệp ứng dụng đã đủ.

## 2. Mở, bind, connect và accept

### 2.1. Phía server: bind rồi accept

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

try (ServerSocketChannel server = ServerSocketChannel.open()) {
    server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
    System.out.println(server.getLocalAddress());

    try (SocketChannel peer = server.accept()) {
        // Dùng peer.read(...) và peer.write(...).
    }
}
~~~

Đây là **mảnh minh họa**, không phải ví dụ độc lập hoàn toàn: đặt trong `main` hoặc phương thức khai báo/xử lý `IOException`, và cần một client kết nối thì lời gọi blocking `accept()` mới tiếp tục.

- `ServerSocketChannel.open()` tạo channel server chưa bind.
- `bind(local)` chọn địa chỉ IP và port để lắng nghe. `port=0` yêu cầu hệ điều hành cấp một cổng khả dụng; `getLocalAddress()` cho biết địa chỉ thực tế sau bind.
- `accept()` trả về **một `SocketChannel` mới** cho kết nối được chấp nhận. Server socket vẫn dùng để chờ thêm kết nối; không dùng chính nó để đọc/ghi payload.
- Channel được `accept()` tạo ra ban đầu ở **blocking mode**, kể cả khi `ServerSocketChannel` được cấu hình non-blocking. Nếu muốn sử dụng nó với selector, phải chủ động `peer.configureBlocking(false)` trước khi đăng ký.

Khi server dùng blocking mode, `accept()` thường chờ cho đến khi có kết nối hoặc xảy ra lỗi/đóng channel. Khi dùng non-blocking mode, `accept()` **trả `null`** nếu hiện chưa có kết nối nào có thể nhận; `null` không đồng nghĩa server socket đã đóng.

Lưu ý: server được bind trên loopback (`127.0.0.1`/`::1` tương ứng môi trường) chỉ để giao tiếp nội bộ trong máy. Khi muốn nhận kết nối từ máy khác, cần địa chỉ bind, cấu hình mạng, firewall và chính sách bảo mật phù hợp.

### 2.2. Phía client: connect

~~~java
SocketChannel client = SocketChannel.open();
boolean connectedNow = client.connect(remoteAddress);
~~~

`remoteAddress` là một `SocketAddress` hợp lệ như `new InetSocketAddress("localhost", port)`. Sau khi `connect(...)`:

| Chế độ của client | Kết quả `connect(remote)` | Ý nghĩa |
| --- | --- | --- |
| Blocking (mặc định) | Thông thường trả `true` nếu kết nối được thiết lập; có thể chặn hoặc ném `IOException`. | Kết nối đã hoàn tất khi trở về thành công. |
| Non-blocking | Trả `true` nếu hoàn tất ngay, hoặc `false` nếu đang kết nối. | Nếu trả `false`, còn bước `finishConnect()` trước khi truyền dữ liệu. |

`connect` không đồng nghĩa “đã có một kết nối hoàn chỉnh” trong **non-blocking mode** khi nó trả `false`. Ở thời điểm đó, `client.isConnectionPending()` có thể trả `true`. Muốn biết đã thực sự sẵn sàng gửi/nhận, dùng `isConnected()` hoặc kết quả của `finishConnect()` theo chu trình phù hợp.

Có thể gặp ngoại lệ khi địa chỉ không hợp lệ, không có route, từ chối kết nối, cổng bị chặn, channel đóng, hoặc thao tác kết nối không hợp lệ với trạng thái hiện tại. Ví dụ cố connect lại khi đã kết nối có thể gặp `AlreadyConnectedException`; khi đã có kết nối pending, có thể gặp `ConnectionPendingException`.

## 3. finishConnect(): hoàn tất kết nối đang chờ

`SocketChannel.finishConnect()` dùng để hoàn thành quá trình TCP connect đã được khởi tạo nhưng chưa xong.

~~~java
client.configureBlocking(false);
boolean connected = client.connect(remoteAddress);
if (!connected) {
    // Một lúc sau, khi channel sẵn sàng kết nối:
    connected = client.finishConnect();
}
~~~

Đoạn này là minh họa theo trạng thái. Với client **non-blocking**:

- `finishConnect() == true`: kết nối đã hoàn tất; có thể bắt đầu `read`/`write`.
- `finishConnect() == false`: vẫn chưa hoàn tất; lưu trạng thái, đợi sự kiện sẵn sàng rồi thử lại.
- Ném `IOException`: việc thiết lập kết nối thất bại.
- Gọi khi không có thao tác kết nối đang chờ và channel cũng chưa kết nối có thể ném `NoConnectionPendingException`.

Trong **blocking mode**, `finishConnect()` có thể chờ tới khi tiến trình kết nối hoàn tất hoặc phát sinh lỗi. Với mô hình non-blocking, không gọi lặp liên tục trong vòng `while` không có cơ chế chờ vì dễ gây busy-spin.

### 3.1. Selector với OP_CONNECT

`Selector` cho phép đợi một hoặc nhiều channel báo trạng thái sẵn sàng. Mẫu đơn giản cho non-blocking connect:

~~~java
// client và remoteAddress đã được tạo.
// Đây là đoạn minh họa, đặt trong phương thức throws IOException.
client.configureBlocking(false);

boolean connected = client.connect(remoteAddress);
if (!connected) {
    try (Selector selector = Selector.open()) {
        SelectionKey key = client.register(selector, SelectionKey.OP_CONNECT);

        while (!client.finishConnect()) {
            int ready = selector.select(5_000);
            if (ready == 0) {
                throw new java.net.SocketTimeoutException(
                        "Không hoàn tất kết nối trong khoảng chờ");
            }

            selector.selectedKeys().clear();
        }
        key.cancel();
    }
}

// Chỉ tại đây mới thực hiện read/write trên kết nối đã thiết lập.
~~~

Các import thêm cho mảnh minh họa: `java.nio.channels.Selector` và `java.nio.channels.SelectionKey`.

Trong ví dụ, `selector.select(5_000)` có thể trở về sau khi có sự kiện, timeout, wakeup hoặc do tác động khác; cách ứng dụng thực tế xử lý sự kiện sẽ xét từng selected key và trạng thái channel. Đoạn này chỉ thể hiện vòng đời **một kết nối đang pending**, không phải mẫu selector production hoàn chỉnh.

Trong event loop production, thường xử lý `key.isConnectable()` rồi gọi `finishConnect()`. Khi thành công, thay `interestOps` khỏi `OP_CONNECT` và đăng ký các thao tác mong muốn như `OP_READ` hoặc `OP_WRITE`; luôn có quy tắc timeout, hủy và đóng channel nếu kết nối thất bại.

### 3.2. Phân biệt OP_CONNECT và OP_ACCEPT

| Event | Channel đăng ký | Khi sẵn sàng |
| --- | --- | --- |
| `SelectionKey.OP_CONNECT` | `SocketChannel` đang kết nối non-blocking | Gọi `finishConnect()` để xác nhận thiết lập xong; có thể vẫn cần xử lý lỗi. |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` non-blocking | Gọi `accept()` để lấy `SocketChannel`; có thể trả `null` nếu không còn kết nối chờ. |
| `SelectionKey.OP_READ` | `SocketChannel` đã kết nối | Gọi `read(...)`; có thể đọc ít byte, `0` hoặc `-1`. |
| `SelectionKey.OP_WRITE` | `SocketChannel` đã kết nối | Gọi `write(...)` khi có dữ liệu chờ; có thể ghi một phần hoặc `0`. |

Readiness chỉ là lời nhắc **nên thử thao tác**, không phải cam kết toàn bộ yêu cầu I/O sẽ hoàn tất trong một lần gọi.

## 4. accept(): nhận kết nối chờ, không đọc dữ liệu

Một server TCP có thể chấp nhận nhiều client. Mỗi `accept()` thành công trả một `SocketChannel` riêng đại diện kết nối đó. SocketChannel này có hai hướng dữ liệu độc lập theo luồng byte TCP.

Trong non-blocking mode:

~~~java
try (ServerSocketChannel server = ServerSocketChannel.open()) {
    server.bind(new InetSocketAddress("127.0.0.1", 9000));
    server.configureBlocking(false);

    SocketChannel peer = server.accept();
    if (peer != null) {
        peer.configureBlocking(false);
        // Đăng ký OP_READ hoặc quản lý tiếp theo trong event loop.
    }
}
~~~

Đây là **mảnh minh họa**, cần `import java.net.InetSocketAddress;` và API channel tương ứng. Port 9000 chỉ dùng minh họa; có thể đang bị chiếm trong môi trường thực tế.

Nếu `accept() == null`, không nên suy ra server có lỗi. Nó chỉ cho biết **lượt gọi non-blocking này** chưa lấy được kết nối. Event loop cần đợi `OP_ACCEPT` để thử lại.

Với selector, một lượt `OP_ACCEPT` có thể có nhiều kết nối chờ; một mẫu thường dùng là:

~~~java
if (key.isAcceptable()) {
    ServerSocketChannel listener = (ServerSocketChannel) key.channel();
    SocketChannel peer;

    while ((peer = listener.accept()) != null) {
        peer.configureBlocking(false);
        peer.register(selector, SelectionKey.OP_READ,
                new ClientState());
    }
}
~~~

Đây là **pseudocode tích hợp vào event loop**: `key`, `selector` và `ClientState` cần được ứng dụng định nghĩa; `ClientState` có thể chứa các buffer và trạng thái protocol. Vòng `while` dạng này thích hợp khi listener đã được cấu hình **non-blocking**; nếu listener blocking thì gọi `accept()` thêm lần nữa có thể chờ vô hạn.

Một server thực tế còn phải áp dụng giới hạn số kết nối, timeout không hoạt động, backpressure, xác thực ứng dụng và quy trình đóng socket theo trạng thái.

## 5. read(): lấy byte từ TCP vào ByteBuffer

Trên `SocketChannel`, cú pháp:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
int count = socket.read(buffer);
~~~

`socket` ở đây là `SocketChannel` đã được kết nối. Các kết quả đọc:

| Giá trị trả về | Diễn giải |
| --- | --- |
| `count > 0` | Chính xác `count` byte được chép vào buffer; `position` tăng tương ứng. |
| `count == 0` | Không byte nào được chuyển trong lần gọi; thường gặp khi non-blocking và chưa có dữ liệu. |
| `count == -1` | Peer đã kết thúc phía gửi (end-of-stream) và không còn byte tiếp theo để đọc. |

Trong blocking mode, một lần đọc với buffer còn chỗ thường đợi để có ít nhất một byte, gặp EOF hoặc lỗi; **không đợi để lấp đầy buffer**. Trong non-blocking mode, `read()` có thể trả `0` rất nhanh. Không suy ra `0` là kết nối đã bị đóng. `-1` thể hiện EOF của hướng đọc.

Sau khi `read(buffer)` ghi một lượng byte vào buffer, chương trình chuyển sang đọc chính buffer bằng `flip()`:

~~~java
int n = socket.read(buffer);
if (n > 0) {
    buffer.flip();

    while (buffer.hasRemaining()) {
        byte b = buffer.get();
        // Phân tích byte b.
    }

    buffer.clear();
} else if (n == -1) {
    // Peer đã đóng hướng gửi.
} else {
    // n == 0: chưa tiến triển; chờ lần sẵn sàng tiếp theo.
}
~~~

Đây là **mảnh minh họa** dành cho trường hợp ứng dụng xử lý **toàn bộ byte vừa đọc**. Nếu parser mới tiêu thụ được một phần thông điệp, phải giữ các byte chưa xử lý bằng `compact()` hoặc cấu trúc tích lũy phù hợp, không gọi `clear()` để chúng có thể bị ghi đè.

### 5.1. Một lần read không phải một thông điệp

TCP là **byte stream**: không giữ nguyên ranh giới giữa các `write(...)` phía gửi. Nếu người gửi gửi:

~~~text
[HEL][LO]
~~~

người nhận có thể thấy:

~~~text
read #1: HELLO
~~~

hoặc:

~~~text
read #1: H
read #2: EL
read #3: LO
~~~

Cả hai đều phù hợp với TCP. Ứng dụng phải có **framing** như độ dài gói, delimiter hoặc khuôn dạng record. Nếu header dài 4 byte, cần đọc đủ 4 byte theo trạng thái chứ không kết luận chỉ từ một lần `read`.

### 5.2. Khi EOF đến lúc một frame còn dang dở

Nếu đã nhận 2/4 byte header rồi `read() == -1`, đó là **thông điệp bị thiếu/truncated** theo giao thức độ dài cố định. Ngược lại, khi ứng dụng chỉ đọc toàn bộ luồng đến EOF, `-1` là điều kiện hoàn tất bình thường.

`SocketChannel.shutdownOutput()` cho phép một phía ngừng gửi nhưng có thể tiếp tục đọc từ peer; đây là dạng **half-close** TCP. `-1` trên hướng đọc không nhất thiết có nghĩa ứng dụng phải lập tức hủy dữ liệu gửi còn chờ theo chiều ngược lại; quyết định thuộc protocol.

## 6. write(): gửi byte từ ByteBuffer sang kết nối

`write(buffer)` lấy các byte từ **`position` đến trước `limit`** của buffer và tăng position theo số byte thực gửi:

~~~java
ByteBuffer buffer = ByteBuffer.wrap(
        "PING".getBytes(StandardCharsets.US_ASCII));

int written = socket.write(buffer);
System.out.println("remaining=" + buffer.remaining());
~~~

Đây là **mảnh minh họa**, có `socket` đã kết nối và import `java.nio.ByteBuffer`, `java.nio.charset.StandardCharsets`. Kết quả `remaining` phụ thuộc số byte được socket tiêu thụ ở lần write.

- `written > 0`: số byte đã được channel tiếp nhận; có thể vẫn còn byte phải gửi.
- `written == 0`: chưa byte nào được tiêu thụ; ở non-blocking mode thường cần đợi `OP_WRITE`.
- Các lỗi I/O được thể hiện bằng exception. `write()` không dùng `-1` để báo EOF như `read()`.

Một mẫu blocking phù hợp cho gửi hết buffer:

~~~java
static void writeFully(SocketChannel channel, ByteBuffer src)
        throws IOException {
    while (src.hasRemaining()) {
        int n = channel.write(src);
        if (n == 0) {
            throw new IOException("Blocking write không tiến triển");
        }
    }
}
~~~

Mẫu trên giả định channel **blocking và đã kết nối**. Sau partial write, `src.position()` tự tiến đến byte tiếp theo, vì vậy chỉ gọi lại `write(src)`. **Không `flip()` lần nữa**, không `clear()` khi vẫn còn `src.hasRemaining()`.

Với non-blocking, thay vì ném lỗi ngay ở `n == 0`, ứng dụng nên giữ buffer trong hàng đợi chờ gửi và đăng ký `OP_WRITE`. Chỉ tái sử dụng hoặc giải phóng buffer khi mọi byte của nó đã được tiêu thụ.

### 6.1. OP_WRITE và backpressure

Nếu ứng dụng luôn quan tâm `OP_WRITE` dù không có dữ liệu chờ, selector có thể báo socket sẵn sàng ghi rất thường xuyên, gây bận CPU. Quy tắc thường dùng:

1. Khi có dữ liệu gửi, xếp buffer vào hàng đợi và bật `OP_WRITE` nếu chưa thể gửi hết.
2. Khi có `OP_WRITE`, thử ghi buffer ở đầu hàng đợi, giữ phần còn lại nếu partial write.
3. Khi tất cả buffer đã hết `remaining` và hàng đợi trống, **bỏ `OP_WRITE` khỏi interest set**, chỉ giữ những event cần thiết như `OP_READ`.

`write()` thành công chỉ xác nhận byte được channel tiếp nhận theo hợp đồng, **không xác nhận** ứng dụng peer đã xử lý thông điệp. Nếu cần xác nhận nghiệp vụ, hãy định nghĩa ACK/response ở tầng ứng dụng.

## 7. Blocking và non-blocking: bảng hành vi cần nhớ

| Thao tác | Blocking mode | Non-blocking mode |
| --- | --- | --- |
| `SocketChannel.connect(remote)` | Chờ hoàn tất, thường trả `true` hoặc lỗi. | Có thể trả `false` khi kết nối đang pending. |
| `SocketChannel.finishConnect()` | Nếu pending, có thể chờ đến khi hoàn tất/lỗi. | Trả `false` khi vẫn pending; dùng `OP_CONNECT` để đợi. |
| `ServerSocketChannel.accept()` | Có thể chờ client đến. | Trả `null` nếu chưa có kết nối sẵn. |
| `SocketChannel.read(dst)` | Có thể chờ ít nhất một byte/EOF/lỗi, không bảo đảm đầy buffer. | Có thể trả `0` nếu chưa có byte sẵn. |
| `SocketChannel.write(src)` | Có thể chờ để ghi tiến triển, không bảo đảm hoàn tất buffer trong một lượt. | Có thể trả `0` nếu tạm thời không ghi được. |

`configureBlocking(false)` cần được gọi **trước** khi đăng ký channel với selector. Nếu channel đã đăng ký với một selector và registration còn hiệu lực, việc chuyển lại blocking có thể gây `IllegalBlockingModeException`. Khi muốn đổi về blocking, cần hủy registration, bảo đảm key không còn đăng ký hợp lệ, rồi mới thay đổi mode. Nhiều thiết kế giữ nguyên non-blocking trong suốt vòng đời kết nối để tránh phức tạp này.

Không xây dựng vòng `while` gọi ngay lại `finishConnect/accept/read/write` mỗi khi nhận `false/null/0` mà không có điều kiện chờ hoặc giới hạn lượt xử lý. Nó có thể trở thành busy-spin, làm CPU tăng và giảm khả năng phục vụ nhiều kết nối.

## 8. Ví dụ Java 17+ chạy được: TCP loopback với đủ connect, accept, read, write

Ví dụ này dùng **blocking mode** để trình bày luồng kết nối trọn vẹn, dễ biên dịch và kiểm chứng. Một luồng server nhận kết nối từ `ServerSocketChannel.accept()`, đọc đúng 4 byte `PING` rồi trả 2 byte `OK`. Luồng main đóng vai client, kết nối loopback, gửi PING và đọc phản hồi.

`finishConnect()` không cần gọi trong ví dụ blocking vì `connect()` hoàn tất trước khi trả thành công. Phần sau có riêng ví dụ non-blocking `finishConnect`.

Lưu file `NioTcpLifecycleDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class NioTcpLifecycleDemo {

    static void readFully(SocketChannel channel, ByteBuffer dst)
            throws IOException {
        while (dst.hasRemaining()) {
            int n = channel.read(dst);
            if (n == -1) {
                throw new EOFException("Peer đóng khi dữ liệu chưa đủ");
            }
            if (n == 0) {
                throw new IOException("Blocking read không tiến triển");
            }
        }
    }

    static void writeFully(SocketChannel channel, ByteBuffer src)
            throws IOException {
        while (src.hasRemaining()) {
            int n = channel.write(src);
            if (n == 0) {
                throw new IOException("Blocking write không tiến triển");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> received = executor.submit(() -> {
                    try (SocketChannel peer = server.accept()) {
                        ByteBuffer incoming = ByteBuffer.allocate(4);
                        readFully(peer, incoming);
                        incoming.flip();

                        String request = StandardCharsets.US_ASCII
                                .decode(incoming).toString();

                        ByteBuffer reply = ByteBuffer.wrap(
                                "OK".getBytes(StandardCharsets.US_ASCII));
                        writeFully(peer, reply);
                        return request;
                    }
                });

                try (SocketChannel client = SocketChannel.open()) {
                    boolean connected = client.connect(
                            (InetSocketAddress) server.getLocalAddress());

                    ByteBuffer request = ByteBuffer.wrap(
                            "PING".getBytes(StandardCharsets.US_ASCII));
                    writeFully(client, request);

                    ByteBuffer answer = ByteBuffer.allocate(2);
                    readFully(client, answer);
                    answer.flip();

                    String acknowledgment = StandardCharsets.US_ASCII
                            .decode(answer).toString();

                    System.out.println("connected=" + connected);
                    System.out.println("response=" + acknowledgment);
                }

                System.out.println("received=" +
                        received.get(5, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac NioTcpLifecycleDemo.java
java NioTcpLifecycleDemo
~~~

**Stdout trong môi trường cho phép kết nối TCP loopback:**

~~~text
connected=true
response=OK
received=PING
~~~

Đối chiếu với các API:

1. `server.bind(...)` lắng nghe ở một port loopback do hệ điều hành chọn. Client dùng `server.getLocalAddress()` nên không cần hard-code cổng.
2. `server.accept()` ở luồng phụ chờ một kết nối và trả về `SocketChannel peer`. Bởi vì accepted socket mặc định blocking, vòng `readFully` phù hợp.
3. `client.connect(...)` ở blocking mode trả `true` khi kết nối thiết lập thành công.
4. `client.write(...)` gửi 4 byte PING; hàm `writeFully` lặp nếu cần cho tới khi buffer hết dữ liệu.
5. `peer.read(...)` nhận đủ 4 byte bằng `readFully` rồi `flip()` để giải mã ASCII.
6. Server ghi lại 2 byte OK; client đọc đủ, `flip()` và decode.
7. Chỉ luồng main in ra stdout, nên thứ tự các dòng được cố định. `Future.get` lấy kết quả server sau khi xử lý xong.

Ví dụ này hoạt động qua TCP thật trên máy cục bộ, nên cần môi trường cho phép mở socket loopback. Nó không dùng selector và không cố tình kích hoạt partial read/write; các hàm `readFully`/`writeFully` được viết đúng hợp đồng ngay cả nếu một lần truyền ít byte hơn yêu cầu. Trong ứng dụng production, nên thêm deadline/timeout cho toàn bộ vòng đời đọc/ghi, giới hạn kích thước và cơ chế dừng luồng nếu peer không phản hồi.

## 9. Ví dụ non-blocking connect/finishConnect đơn giản

Sau khi nắm chu trình blocking, có thể đổi riêng phía client sang non-blocking. Đoạn này minh họa **thiết lập kết nối**, không phải toàn bộ server production:

~~~java
try (SocketChannel client = SocketChannel.open();
     Selector selector = Selector.open()) {

    client.configureBlocking(false);
    boolean connected = client.connect(remote);

    if (!connected) {
        SelectionKey key = client.register(
                selector, SelectionKey.OP_CONNECT);

        while (!client.finishConnect()) {
            int ready = selector.select(5_000);
            if (ready == 0) {
                throw new java.net.SocketTimeoutException(
                        "Kết nối không sẵn sàng");
            }
            selector.selectedKeys().clear();
        }
        key.cancel();
    }

    // client.isConnected() == true:
    // Có thể đăng ký đọc/ghi hoặc gửi/nhận non-blocking.
}
~~~

Đây là **mảnh minh họa**, biến `remote` là `SocketAddress` được cung cấp trước và import `java.nio.channels.SocketChannel`, `Selector`, `SelectionKey`, `java.net.SocketAddress`. Đối với một event loop đa kết nối, nên dùng từng `SelectionKey` và attachment quản lý trạng thái thay vì vòng connect chuyên dụng như trên.

Nếu gọi `client.read(...)` hoặc `client.write(...)` ngay khi `connect(remote)` trả `false` mà chưa hoàn tất bằng `finishConnect()`, có thể gặp `NotYetConnectedException`. Do đó sự kiện `OP_CONNECT` và bước `finishConnect` cần được xử lý trước `OP_READ/OP_WRITE`.

### 9.1. Skeleton xử lý SelectionKey

~~~java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();

    if (!key.isValid()) {
        continue;
    }
    try {
        if (key.isAcceptable()) {
            // ServerSocketChannel.accept() trong non-blocking mode.
        }
        if (key.isConnectable()) {
            // SocketChannel.finishConnect() cho connect pending.
        }
        if (key.isReadable()) {
            // SocketChannel.read(...); xử lý >0, 0, -1.
        }
        if (key.isWritable()) {
            // SocketChannel.write(...); xử lý partial/0.
        }
    } catch (IOException ex) {
        key.cancel();
        key.channel().close();
    }
}
~~~

Đây là **pseudocode khung event loop**: `selector` và các channel cần được khởi tạo, đăng ký đúng mode, cũng như phải quản lý các `ByteBuffer` và trạng thái kết nối. Các nhánh chưa phải code production. Không thể dùng mỗi nhánh `isReadable` rồi đọc một lần và coi đã nhận đủ thông điệp.

## 10. Các tình huống biên dễ gây lỗi

### 10.1. connect trả false nhưng bỏ qua finishConnect

~~~java
client.configureBlocking(false);
boolean done = client.connect(remote);
// Sai nếu done == false mà lập tức client.write(...).
~~~

Cách đúng: khi pending, đăng ký `OP_CONNECT` và gọi `finishConnect()` cho tới khi thành công hoặc lỗi/timeout. Trạng thái `isConnected()` giúp theo dõi nhưng không thay thế hợp đồng hoàn tất của `finishConnect()`.

### 10.2. accept trả null rồi cho rằng server hỏng

Trong non-blocking mode, `accept() == null` là kết quả thường gặp khi chưa có kết nối chờ. Đợi `OP_ACCEPT` thay vì tự spin vô hạn.

### 10.3. read trả 0 bị hiểu là EOF

`0` có nghĩa chưa byte nào được chuyển trong lần đó; `-1` mới biểu thị hướng đọc đã hết dữ liệu. Với non-blocking, chờ `OP_READ`. Với blocking channel và buffer có chỗ, sự kiện `0` là dấu hiệu cần xem lại giả định về provider/trạng thái ứng dụng.

### 10.4. read() một lần rồi parse cả frame

Chưa chắc buffer đã có đủ frame. Cần kiểm tra `n` và `remaining()`, duy trì trạng thái parser qua nhiều lần đọc, xử lý trường hợp một read chứa nhiều frame. Dùng `compact()` khi có byte cuối đang dang dở.

### 10.5. write() xong liền clear buffer

Nếu write chỉ gửi một phần, `clear()` có thể khiến byte chưa gửi bị ghi đè. Giữ `position/limit` như hiện tại; gửi tiếp khi channel sẵn sàng.

### 10.6. Đăng ký OP_WRITE liên tục

Socket thường rất hay “sẵn sàng ghi”, ngay cả khi ứng dụng không có gì để gửi. Quan tâm `OP_WRITE` suốt thời gian kết nối có thể làm selector thức dậy quá nhiều; chỉ bật khi thực sự có byte chờ ghi, tắt khi hàng đợi trống.

### 10.7. Gọi configureBlocking(true) khi channel vẫn đăng ký selector

Nếu channel đang có registration hợp lệ, việc đổi sang blocking mode có thể ném `IllegalBlockingModeException`. Tổ chức vòng đời channel sao cho mode và selector registration nhất quán.

### 10.8. Không xử lý peer đóng nửa kết nối

Khi `read() == -1`, peer đã đóng hướng gửi; ứng dụng có thể còn byte chờ ghi theo chiều còn lại tùy giao thức. Chọn quy trình kết thúc an toàn, hoàn tất dữ liệu cần gửi hoặc hủy theo quy tắc rõ ràng. Đừng coi EOF là “socket đã hủy cả hai chiều” một cách mặc định.

### 10.9. Tin rằng write hoàn tất đồng nghĩa peer đã xử lý

Ghi hết buffer chỉ nói rằng dữ liệu đã được chuyển cho cơ chế channel ở phía gửi theo hợp đồng. TCP và logic ứng dụng phía nhận là các tầng khác. Nếu muốn xác nhận xử lý nghiệp vụ, giao thức cần thông điệp trả lời/ACK riêng.

### 10.10. Không giới hạn tài nguyên kết nối

Mỗi client có thể giữ socket, buffer và trạng thái parser. Server production cần giới hạn connections, kích thước frame, thời gian chờ header/payload, hàng đợi write, tốc độ nhận dữ liệu và các cơ chế đóng/hủy để tránh cạn bộ nhớ và file descriptor.

## 11. Tóm tắt bằng bảng quyết định

| Bạn đang làm gì? | API phù hợp | Dấu hiệu phải tiếp tục/xử lý |
| --- | --- | --- |
| Client bắt đầu kết nối | `SocketChannel.connect(remote)` | `false` trong non-blocking → đang pending. |
| Client có kết nối pending | `SocketChannel.finishConnect()` | `false` → đợi OP_CONNECT; `true` → kết nối xong. |
| Server nhận client | `ServerSocketChannel.accept()` | `null` trong non-blocking → đợi OP_ACCEPT. |
| Đọc payload vào buffer | `SocketChannel.read(dst)` | `>0` xử lý byte; `0` đợi tiếp; `-1` EOF. |
| Ghi buffer ra TCP | `SocketChannel.write(src)` | `>0` kiểm tra remaining; `0` đợi OP_WRITE. |
| Đọc thông điệp nhiều đợt | `ByteBuffer.flip/compact` + parser | Giữ byte chưa đủ frame; không clear nhầm. |
| Đợi sẵn sàng trên nhiều channel | `Selector.select` + `SelectionKey` | Xử lý đúng kind, mode, timeout và lifecycle. |

## 12. Bài tập tự kiểm tra

1. **Phương thức nào nhận TCP connection ở server?** `ServerSocketChannel.accept()`, trả về `SocketChannel` của client mới.
2. **Non-blocking `connect(remote)` trả `false` có phải thất bại?** Không. Kết nối đang chờ; cần `finishConnect()`.
3. **`finishConnect()` trả `false` nghĩa là gì?** Chưa hoàn tất, nên đợi readiness hoặc cơ chế retry thích hợp.
4. **Sự kiện nào thường gắn với kết nối client đang pending?** `SelectionKey.OP_CONNECT`.
5. **Non-blocking `accept()` chưa có kết nối thì trả gì?** `null`.
6. **SocketChannel do server accept tạo có tự non-blocking theo listener không?** Không. Channel accepted ban đầu ở blocking mode; cần chủ động cấu hình nếu dùng selector.
7. **`read(buffer)` trả `0` có phải EOF?** Không; `-1` mới báo EOF hướng đọc.
8. **`write(buffer)` đã gửi 3 trong 8 byte thì gửi tiếp từ đâu?** Từ `buffer.position()` hiện tại, không flip/clear lần nữa; còn 5 byte.
9. **Hai lần client.write("HE") và client.write("LLO") có bảo đảm server.read hai lần tương ứng không?** Không, TCP là byte stream.
10. **Tại sao phải tắt `OP_WRITE` khi không còn dữ liệu chờ?** Để event loop tránh các thông báo writable lặp liên tục.
11. **Đã connect thành công có nghĩa phía server gửi đủ một frame chưa?** Không. Connection lifecycle và message framing độc lập.
12. **Một socket nhận `-1` từ read có thể vẫn có dữ liệu cần gửi?** Có thể, theo protocol half-close; cần quyết định xử lý theo trạng thái ứng dụng.

**Ghi nhớ:** `connect` khởi đầu thiết lập TCP, `finishConnect` xác nhận hoàn tất kết nối pending, `accept` tạo socket của client ở phía server, và `read/write` truyền từng phần của **dòng byte**. Với NIO non-blocking, hãy kiểm tra **giá trị trả về, trạng thái buffer và readiness event**, bảo toàn các byte chưa xử lý, và có cơ chế đóng/timeout rõ ràng.
