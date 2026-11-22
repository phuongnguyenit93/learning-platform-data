# ServerSocketChannel.open với ProtocolFamily trong Java

**`ServerSocketChannel.open(ProtocolFamily family)`** tạo một kênh server socket NIO cho **họ giao thức mạng được chỉ định**. Overload này được bổ sung từ **Java 15** và vẫn có mặt trong Java hiện đại. Thay vì chỉ gọi `ServerSocketChannel.open()` rồi để runtime chọn socket Internet mặc định, ứng dụng có thể yêu cầu rõ **`StandardProtocolFamily.INET`** (IPv4) hoặc **`INET6`** (IPv6), miễn môi trường hỗ trợ.

Từ **Java 16**, `StandardProtocolFamily.UNIX` được bổ sung qua JEP 380 để tạo **Unix-domain stream socket** phục vụ IPC trên cùng máy. Phải phân biệt chính xác hai mốc: **phương thức `open(ProtocolFamily)` có từ Java 15; riêng giá trị `UNIX` và các API Unix-domain socket có từ Java 16**. Không viết mã dùng `UNIX` rồi tuyên bố nó biên dịch được bằng JDK 15.

Chủ đề thuộc nhóm **Protocol family**. Bài học giải thích cách chọn family, cơ chế `open → bind → accept`, kiểu địa chỉ tương ứng, hành vi blocking/non-blocking, tính tương thích và lỗi thường gặp; kèm chương trình Java 17+ có thể chạy với TCP IPv4 loopback.

## 1. ServerSocketChannel và ProtocolFamily là gì?

`ServerSocketChannel` thuộc package `java.nio.channels`, dùng để **nghe kết nối dạng luồng** (*stream-oriented listening socket*). Với `INET` hoặc `INET6`, đó là server socket cho **TCP/IP**. Với `UNIX` từ JDK 16+, nó là kênh nghe **Unix-domain stream socket** dùng cho liên lạc giữa các tiến trình trên một máy.

**Không nhầm với UDP:** UDP dùng `DatagramSocket` hoặc `DatagramChannel`, không dùng `ServerSocketChannel.accept()`. Mặc dù tên `ProtocolFamily` nghe rất rộng, nó **không biến ServerSocketChannel thành một server UDP**.

`java.net.ProtocolFamily` là **interface** mô tả một họ giao thức. JDK cung cấp enum `java.net.StandardProtocolFamily` với các giá trị tiêu chuẩn:

| Family | Loại socket | Kiểu địa chỉ thường dùng | Mốc Java | Lưu ý |
| --- | --- | --- | --- | --- |
| `INET` | Internet IPv4 | `InetSocketAddress` với địa chỉ IPv4 | Có trước Java 15 | TCP IPv4 trên `ServerSocketChannel` |
| `INET6` | Internet IPv6 | `InetSocketAddress` với địa chỉ IPv6 | Có trước Java 15 | Phụ thuộc hỗ trợ IPv6 của OS/JVM |
| `UNIX` | Unix-domain local stream socket | `UnixDomainSocketAddress` | **Java 16** | IPC cùng máy; hỗ trợ theo nền tảng |

Hai tên `INET`/`INET6` **không biểu diễn “TCP” và “UDP”**. Chúng biểu diễn **họ địa chỉ/protocol IPv4 và IPv6**. Loại channel mới quyết định giao tiếp là **stream** hay **datagram**.

Ví dụ các lựa chọn khác nhau:

```java
// TCP listening socket, IPv4:
ServerSocketChannel tcp4 =
        ServerSocketChannel.open(StandardProtocolFamily.INET);

// TCP listening socket, IPv6:
ServerSocketChannel tcp6 =
        ServerSocketChannel.open(StandardProtocolFamily.INET6);

// UDP channel, IPv4 — API khác:
DatagramChannel udp4 =
        DatagramChannel.open(StandardProtocolFamily.INET);
```

Đây là **các đoạn minh họa**, cần import `java.net.StandardProtocolFamily`, `java.nio.channels.ServerSocketChannel` và `DatagramChannel`, xử lý `IOException` và **đóng các channel đã tạo**. Không phải chương trình độc lập; phần chạy hoàn chỉnh có ở mục 5.

## 2. Chữ ký API và điểm mới từ Java 15

Chữ ký công khai:

```java
public static ServerSocketChannel open(ProtocolFamily family)
        throws IOException;
```

Hàm nhận một `ProtocolFamily` và trả về **một `ServerSocketChannel` mới, đang mở nhưng chưa bind**. Theo API Java SE hiện đại, lời gọi tạo channel thông qua:

```java
SelectorProvider.provider().openServerSocketChannel(family)
```

Đó là **cách vận hành theo API**, chỉ là mã giải thích; không cần người học trực tiếp khởi tạo `SelectorProvider`. Tên family định hướng **provider mặc định của JVM** tạo socket có họ giao thức phù hợp. Một custom provider có thể không hỗ trợ một family nào đó; không thể mặc định mọi provider đều hoạt động giống nhau.

So sánh:

| API | Ý nghĩa | Cần làm tiếp |
| --- | --- | --- |
| `ServerSocketChannel.open()` | Tạo kênh server Internet mặc định | `bind(...)` rồi `accept()` |
| `ServerSocketChannel.open(INET)` | Yêu cầu family IPv4 | `bind(InetSocketAddress IPv4)` rồi accept |
| `ServerSocketChannel.open(INET6)` | Yêu cầu family IPv6 | Kiểm tra hỗ trợ IPv6, bind vào địa chỉ phù hợp |
| `ServerSocketChannel.open(UNIX)` | Tạo Unix-domain server (JDK **16+**) | Bind với `UnixDomainSocketAddress` |
| `SocketChannel.open(family)` | Tạo **client** socket channel theo family | `connect(remoteAddress)` |
| `DatagramChannel.open(family)` | Tạo kênh **datagram** | Dùng send/receive UDP, **không accept** |

`open()` không tự chọn “IPv4 vĩnh viễn”; cấu hình mạng và provider có thể quyết định kênh Internet mặc định hoạt động thế nào. **Dùng `open(INET)` khi bạn cần cưỡng định IPv4**, chẳng hạn hệ thống chỉ công bố một IPv4 listening endpoint. Dùng `INET6` khi yêu cầu IPv6 là một phần của hợp đồng triển khai.

**INET6 không bảo đảm mọi môi trường có cùng chính sách dual-stack.** Việc một IPv6 socket có nhận kết nối IPv4-mapped hay không phụ thuộc OS/JVM/cấu hình; nếu ứng dụng cần IPv6-only hoặc cần cả IPv4 lẫn IPv6, hãy kiểm tra chính sách thực tế, địa chỉ bind và kiểm thử tương ứng. Không suy ra “INET6 = chắc chắn chỉ nhận IPv6” cho mọi runtime.

## 3. Cách dùng căn bản: open → bind → accept

Trình tự cho một server TCP IPv4:

```java
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.INET)) {

    server.bind(new InetSocketAddress("127.0.0.1", 8080));

    try (SocketChannel peer = server.accept()) {
        // Đọc/ghi bytes qua peer.
    }
}
```

Đây là **ví dụ ngắn về luồng API**, không phải demo tự kết thúc. `accept()` sẽ **chờ kết nối** nếu không có client; port 8080 có thể đang được sử dụng nên lệnh bind cũng có thể thất bại.

### Trạng thái từng bước

**`open(family)`:**

- Channel đã mở: `server.isOpen() == true`.
- Chưa bind: `server.getLocalAddress() == null`.
- Chưa thể gọi `accept()` hợp lệ; sẽ có `NotYetBoundException`.
- Channel mới mặc định ở **blocking mode**.

**`bind(address, backlog)`:**

- Gắn listening socket vào local address phù hợp family, ví dụ IPv4 loopback + port.
- `backlog` là yêu cầu về độ dài hàng đợi pending connections; hành vi và giới hạn thực tế do implementation/OS quyết định.
- Port bằng `0` yêu cầu OS cấp **ephemeral port**; sau khi bind, lấy port thật qua `getLocalAddress()`.
- `bind(null)` có hành vi địa chỉ tự chọn theo hợp đồng từng loại socket; để bảo mật và tránh mơ hồ, nên chọn local bind address tường minh khi cần kiểm soát phạm vi kết nối.

**`accept()`:**

- Ở blocking mode, chờ một kết nối tới; khi thành công trả về một **`SocketChannel` kết nối với client**, không phải chính listener.
- Ở non-blocking mode, nếu chưa có kết nối chờ thì **trả về `null`** ngay.
- `SocketChannel` được trả về ban đầu ở **blocking mode**, kể cả listener đang non-blocking.
- Listener tiếp tục dùng để chấp nhận **những kết nối tiếp theo**.

**Quan trọng:** tạo channel **không** mở sẵn một cổng để client kết nối; chỉ khi **`bind` thành công** thì listener mới có local address/port hợp lệ.

## 4. Kiểu địa chỉ phải tương ứng với family

`ProtocolFamily` và `SocketAddress` là hai phần của cùng một quyết định cấu hình.

**IPv4 (Java 15+):**

```java
try (ServerSocketChannel s =
         ServerSocketChannel.open(StandardProtocolFamily.INET)) {

    s.bind(new InetSocketAddress(
            InetAddress.getByName("127.0.0.1"), 0));
}
```

Đây là đoạn minh họa, cần import `InetAddress`, `InetSocketAddress`, `StandardProtocolFamily`, `ServerSocketChannel` và xử lý ngoại lệ. IPv4 loopback là **`127.0.0.1`**, chỉ dành cho kết nối từ cùng máy khi chính sách mạng cho phép.

**IPv6 (Java 15+ nếu platform hỗ trợ):**

```java
try (ServerSocketChannel s =
         ServerSocketChannel.open(StandardProtocolFamily.INET6)) {

    s.bind(new InetSocketAddress(
            InetAddress.getByName("::1"), 0));
}
```

`::1` là IPv6 loopback. Nếu runtime tắt IPv6 hoặc nền tảng không hỗ trợ, `open(INET6)` có thể ném `UnsupportedOperationException`; `bind` cũng có thể thất bại do cấu hình mạng hoặc OS. **Không hứa đoạn này chạy trên mọi máy.**

**Unix domain (Java 16+, tùy nền tảng):**

```java
try (ServerSocketChannel s =
         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    s.bind(UnixDomainSocketAddress.of("/path/to/service.sock"));
}
```

Đây là **mã minh họa**, cần import `UnixDomainSocketAddress`, `StandardProtocolFamily` và `ServerSocketChannel`. Trên hệ thống thật, đường dẫn phải hợp lệ, thư mục phải tồn tại, và bạn phải quản lý việc dọn dẹp socket file khi không còn dùng. Việc đóng channel không có nghĩa **mọi nền tảng tự xóa pathname Unix-domain socket**. Không tùy tiện xóa một đường dẫn có thể thuộc tiến trình khác.

**Không đem `UnixDomainSocketAddress` bind vào kênh `INET`**, cũng không đem một `InetSocketAddress` truyền vào channel `UNIX`. Điều kiện tương thích address/family được kiểm tra tại runtime; lỗi có thể là `UnsupportedAddressTypeException` hoặc một ngoại lệ I/O/socket phù hợp.

## 5. Chương trình Java 17+ hoàn chỉnh: IPv4 loopback server và client

Ví dụ dưới đây được viết để **chạy độc lập trong một tiến trình**. Nó không chiếm port cố định, không cần Internet, không cần Unix-domain socket và không cần tạo thread phụ:

1. Mở listener **`ServerSocketChannel.open(INET)`**.
2. Xác nhận listener chưa bind và `accept()` trước bind ném `NotYetBoundException`.
3. Bind vào `127.0.0.1`, port `0`; OS cấp port tạm.
4. Mở **`SocketChannel.open(INET)`** ở phía client rồi connect tới endpoint vừa bind.
5. Listener chấp nhận kết nối và nhận `"ping"` từ client.
6. Server trả về `"pong"` và client đọc lại.
7. Mọi channel tự động đóng bằng **try-with-resources**.

Lưu file **`ProtocolFamilyServerDemo.java`** bằng UTF-8:

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.NotYetBoundException;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;

public class ProtocolFamilyServerDemo {
    private static void send(SocketChannel channel, String text)
            throws IOException {
        ByteBuffer bytes = StandardCharsets.UTF_8.encode(text);
        while (bytes.hasRemaining()) {
            channel.write(bytes);
        }
    }

    private static String receive(SocketChannel channel, int count)
            throws IOException {
        ByteBuffer bytes = ByteBuffer.allocate(count);
        while (bytes.hasRemaining()) {
            if (channel.read(bytes) < 0) {
                throw new EOFException("peer closed before full message");
            }
        }
        bytes.flip();
        return StandardCharsets.UTF_8.decode(bytes).toString();
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server =
                     ServerSocketChannel.open(StandardProtocolFamily.INET)) {

            System.out.println("open=" + server.isOpen());
            System.out.println("initiallyBound=" +
                    (server.getLocalAddress() != null));

            try {
                server.accept();
                System.out.println("acceptBeforeBind=unexpected");
            } catch (NotYetBoundException expected) {
                System.out.println("acceptBeforeBind=NotYetBoundException");
            }

            InetAddress loopback = InetAddress.getByName("127.0.0.1");
            server.bind(new InetSocketAddress(loopback, 0), 8);

            InetSocketAddress address =
                    (InetSocketAddress) server.getLocalAddress();
            System.out.println("ipv4=" +
                    (address.getAddress() instanceof Inet4Address));
            System.out.println("portAssigned=" + (address.getPort() > 0));

            try (SocketChannel client =
                         SocketChannel.open(StandardProtocolFamily.INET)) {
                client.connect(address);

                try (SocketChannel accepted = server.accept()) {
                    System.out.println("accepted=" + (accepted != null));
                    System.out.println("acceptedBlocking=" +
                            accepted.isBlocking());

                    send(client, "ping");
                    System.out.println("serverReceived=" +
                            receive(accepted, 4));

                    send(accepted, "pong");
                    System.out.println("clientReceived=" +
                            receive(client, 4));
                }
            }
        }
    }
}
```

Biên dịch và chạy với **JDK 17+** (lệnh cũng tương thích nguyên tắc API Java 15 vì chỉ dùng `INET`):

```bash
javac -encoding UTF-8 ProtocolFamilyServerDemo.java
java ProtocolFamilyServerDemo
```

**Đầu ra chính xác đã được kiểm chứng trên JDK 24 trong môi trường có IPv4 loopback:**

```text
open=true
initiallyBound=false
acceptBeforeBind=NotYetBoundException
ipv4=true
portAssigned=true
accepted=true
acceptedBlocking=true
serverReceived=ping
clientReceived=pong
```

### Giải thích kết quả

- `open=true`: channel đã được tạo và mở thành công.
- `initiallyBound=false`: `open` **không tự bind** địa chỉ.
- `acceptBeforeBind=NotYetBoundException`: gọi `accept` trước `bind` là sai trạng thái.
- `ipv4=true`: server đang bind địa chỉ loopback thuộc `Inet4Address`.
- `portAssigned=true`: OS đã chọn port khác 0; chương trình không phải đoán hoặc hard-code port.
- `accepted=true`: một TCP client thực sự kết nối được tới listener.
- `acceptedBlocking=true`: accepted channel ban đầu ở blocking mode.
- `serverReceived=ping` và `clientReceived=pong`: kênh truyền byte hai chiều thành công.

### Vì sao phải dùng vòng lặp read/write?

**TCP là byte stream, không phải datagram.** Một lần gọi `SocketChannel.write(ByteBuffer)` **không bảo đảm** ghi hết mọi byte; một lần `read` cũng không bảo đảm trả đủ một logical message.

Trong chương trình, `send` lặp khi buffer vẫn còn byte. `receive` đọc **đúng `count` byte** và báo `EOFException` nếu peer đóng quá sớm. Đây chỉ là giao thức demo với message dài cố định 4 byte. Trong ứng dụng thật, phải có **message framing** (length-prefix hoặc delimiter có escape), giới hạn kích thước, timeouts và xử lý đọc/ghi từng phần.

Nếu máy/container không cho bind hoặc dùng TCP loopback, chương trình có thể ném `IOException`; đó là giới hạn môi trường mạng, không phải bằng chứng API không tồn tại.

## 6. Lựa chọn INET, INET6 và UNIX theo yêu cầu

Một nguyên tắc quyết định:

| Bài toán | Family nên cân nhắc | Ghi chú |
| --- | --- | --- |
| Server cần nghe **IPv4** rõ ràng | `INET` | Bind địa chỉ IPv4 cụ thể và kiểm tra firewall |
| Server cần nghe **IPv6** | `INET6` | Kiểm tra OS hỗ trợ IPv6, địa chỉ và dual-stack policy |
| IPC giữa tiến trình trên **cùng một máy** | `UNIX` từ JDK 16+ | Phù hợp khi nền tảng hỗ trợ Unix-domain stream socket |
| Server cần tương thích API Internet mặc định | `open()` | Không cưỡng định family; behavior phụ thuộc provider/OS |
| Server giao thức **UDP** | Không dùng `ServerSocketChannel` | Sử dụng `DatagramChannel.open(family)` |
| Chạy trên JDK **15** | `INET`/`INET6` | **Không có `StandardProtocolFamily.UNIX` trong Java 15** |

Unix-domain socket dùng pathname cục bộ và không có khái niệm IP port như TCP. Nó **không phải TCP qua loopback**: về mặt giao diện stream, hai loại tương tự nhau, nhưng hệ địa chỉ và các tùy chọn socket khác nhau. Nếu dùng IPC qua Unix-domain socket, ứng dụng cần quan tâm quyền truy cập filesystem path, directory ownership, cleanup path và giới hạn nền tảng.

### JEP 380 không thay mốc Java 15 của open(ProtocolFamily)

Mốc thời gian chính xác:

- **Java 15:** `ServerSocketChannel.open(ProtocolFamily)` và `SocketChannel.open(ProtocolFamily)` đã có; lựa chọn thực tế `INET`, `INET6`.
- **Java 16 — JEP 380:** bổ sung `UNIX` và `UnixDomainSocketAddress`; các overload family-aware này từ đó có thể tạo Unix-domain stream sockets trên nền tảng hỗ trợ.
- **Java 17+ đến hiện đại:** các API tiếp tục được hỗ trợ; phải kiểm tra cấu hình runtime cụ thể trước khi dùng `INET6` hoặc `UNIX`.

**Không trích JEP 380 để kết luận `open(ProtocolFamily)` chỉ mới xuất hiện ở Java 16.** Hai mốc liên quan nhau nhưng là **hai phần khác nhau của API**.

## 7. Blocking và non-blocking với Selector

`ServerSocketChannel` là một `SelectableChannel`. Mặc định:

```java
ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.INET);

System.out.println(server.isBlocking()); // true
```

Đoạn trên chỉ minh họa trạng thái, cần đóng channel sau khi dùng. Khi server ở blocking mode và đã bind, `accept()` có thể chờ vô hạn tới khi client kết nối (hoặc lỗi/đóng channel).

Nếu xây event loop dùng `Selector`, chuyển listener sang non-blocking trước khi đăng ký:

```java
try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.INET);
     Selector selector = Selector.open()) {

    server.bind(new InetSocketAddress("127.0.0.1", 0));
    server.configureBlocking(false);
    server.register(selector, SelectionKey.OP_ACCEPT);

    int readyCount = selector.select(1000);
    if (readyCount > 0) {
        // Duyệt selectedKeys và xử lý OP_ACCEPT, rồi accept.
    }
}
```

Đây là **mã minh họa về cách cấu hình NIO**, cần import `Selector`, `SelectionKey`, `ServerSocketChannel`, `StandardProtocolFamily`, `InetSocketAddress`. Chương trình hoàn chỉnh ở mục 5 sử dụng blocking mode để giữ code dễ học.

Quan trọng:

1. `ServerSocketChannel.validOps()` hỗ trợ **`SelectionKey.OP_ACCEPT`**, không phải `OP_READ`/`OP_WRITE` để truyền dữ liệu trên listener.
2. Nếu listener **non-blocking** và chưa có kết nối đến, `accept()` trả **`null`**.
3. Khi `accept` thành công, `SocketChannel` được trả về **blocking**, kể cả listener non-blocking. Để đăng ký accepted channel cho `OP_READ`/`OP_WRITE`, cần gọi `accepted.configureBlocking(false)` trước.
4. `Selector.select(timeout)` là **thời gian chờ sự kiện** của selector; không phải thay thế cho application-level timeout, flow control hoặc giới hạn thời gian của toàn bộ request.
5. Khi một `SelectionKey` đã được xử lý, event loop phải quản lý và xóa selected-key entry đúng cách. Mẫu rút gọn ở trên không tự xử lý đầy đủ vòng đời connection.

Đối với chương trình chỉ có một listener và một client, blocking mode thường dễ hiểu hơn. Selector phù hợp khi cần multiplex nhiều kết nối bằng non-blocking I/O.

## 8. Socket options và socket() không giống nhau giữa các family

`ServerSocketChannel` có các API:

```java
server.supportedOptions();
server.setOption(StandardSocketOptions.SO_RCVBUF, 64 * 1024);
```

Đây là mã minh họa, cần có `server` và import `java.net.StandardSocketOptions`. **Không mặc định mọi socket family đều hỗ trợ cùng một tập option**.

Theo Javadoc hiện đại:

| Family | Một số option thông thường có thể hỗ trợ |
| --- | --- |
| Internet `INET`/`INET6` | `SO_RCVBUF`, `SO_REUSEADDR` |
| Unix-domain `UNIX` | `SO_RCVBUF` |
| Provider khác | Có thể có thêm tùy chọn implementation-specific |

Nếu ứng dụng cần một option cụ thể, có thể kiểm tra **`supportedOptions()`** và xử lý `UnsupportedOperationException` khi không được hỗ trợ; đừng đơn giản ép mọi channel dùng chung một cấu hình. Các option thuộc **listening socket** cũng không mặc định tương đương mọi option của accepted `SocketChannel`.

Một khác biệt đáng chú ý:

```java
java.net.ServerSocket traditional = server.socket();
```

Với channel Internet, `socket()` trả một `ServerSocket` tương ứng để dùng API socket truyền thống. Nhưng đối với **Unix-domain `ServerSocketChannel`**, phương thức `socket()` **có thể ném `UnsupportedOperationException`** theo hợp đồng API; không được cho rằng `java.net.ServerSocket` đại diện được mọi family.

Trong code mới dùng NIO, ưu tiên thao tác trực tiếp trên `ServerSocketChannel`, `bind`, `accept` và `setOption` thay vì ép qua `socket()` nếu không cần.

## 9. Các ngoại lệ đáng quan tâm

| Thao tác/tình huống | Lỗi/ngoại lệ có thể gặp | Cách xử lý |
| --- | --- | --- |
| `open(null)` | `NullPointerException` | Không truyền `null` làm `ProtocolFamily` |
| Family không được runtime/provider hỗ trợ | `UnsupportedOperationException` | Kiểm tra nền tảng, phiên bản JDK và lựa chọn fallback **có chủ đích** |
| Lỗi tài nguyên/OS khi `open` | `IOException` | Kiểm tra socket resource, quyền và cấu hình |
| `accept()` trước `bind()` | `NotYetBoundException` | Gọi `bind` trước |
| `bind` khi đã bind | `AlreadyBoundException` | Quản lý rõ một lần bind và vòng đời channel |
| Bind vào port đang sử dụng | Thường `BindException` | Chọn port hợp lệ, kiểm tra listener khác |
| Address không tương thích family | `UnsupportedAddressTypeException` hoặc lỗi socket/I/O tương ứng | Dùng đúng `InetSocketAddress` hoặc `UnixDomainSocketAddress` |
| `accept` sau `close` | `ClosedChannelException` | Không dùng lại channel đã đóng |
| Thread khác đóng channel lúc đang accept | `AsynchronousCloseException` | Xử lý kết thúc vòng đời thay vì retry mù quáng |
| Thread hiện tại bị interrupt trong blocking accept | `ClosedByInterruptException` theo hợp đồng | Giữ đúng chính sách hủy/interrupt |
| Server non-blocking chưa có pending connection | **`accept()==null`** | Không coi `null` là lỗi mất kết nối |

Cần bắt ngoại lệ ở mức **đúng ý nghĩa**, không dùng một `catch(Exception)` chung rồi trả về “không hỗ trợ IPv6” cho tất cả lỗi. Đặc biệt:

- `UnsupportedOperationException` khi `open(INET6)` báo một family không được provider hỗ trợ.
- `IOException` khi `bind` có thể phản ánh port đã dùng, quyền hạn, cấu hình địa chỉ hoặc mạng.
- `NotYetBoundException` là lỗi **thứ tự sử dụng API**, không phải “TCP server chưa có client”.

## 10. Phạm vi mạng và bảo mật khi bind

Việc chọn `ProtocolFamily` không tự mang tới TLS, authentication hay firewall rules. **Bind address** quyết định mức độ socket được công bố trong phạm vi mạng, kết hợp chính sách OS/firewall.

Ví dụ:

| Địa chỉ bind | Ý nghĩa thường gặp |
| --- | --- |
| `127.0.0.1` | IPv4 loopback, chỉ nhận kết nối cục bộ |
| `0.0.0.0` | IPv4 wildcard, có thể nghe trên mọi giao diện IPv4 phù hợp |
| `::1` | IPv6 loopback |
| `::` | IPv6 wildcard, phạm vi tiếp cận còn tùy dual-stack/firewall |
| Unix-domain pathname | IPC cục bộ theo đường dẫn; kiểm tra ownership, permissions, symlink/path collision |

**Không mở server lên `0.0.0.0` hoặc `::` chỉ để “thử cho chạy”** nếu dịch vụ không được phép tiếp nhận kết nối từ ngoài máy. Bài chạy ở mục 5 dùng **IPv4 loopback** để tránh công bố cổng ra mạng ngoài.

Khi đưa vào sản phẩm, cần bổ sung theo yêu cầu:

- Giới hạn nguồn kết nối bằng firewall/network policies hoặc lựa chọn địa chỉ bind tường minh.
- **TLS** cho các kết nối cần bí mật/toàn vẹn trên TCP/IP; family `INET`/`INET6` không tự bật TLS.
- Authentication/authorization cấp ứng dụng, hạn chế số kết nối, timeout và kích thước message.
- Không đọc một TCP stream như “mỗi read là một message”; phải có framing.
- Tài nguyên luôn được đóng: listener, accepted channels, selector và buffer theo vòng đời.
- Với Unix-domain socket, kiểm soát **path, owner, permissions, cleanup và khả năng process lạ truy cập pathname**; IPC cục bộ không tự làm mọi client đáng tin.

## 11. Checklist chọn family cho server

- [ ] Xác định dịch vụ là **TCP stream** hay **UDP datagram**. Nếu UDP, không chọn `ServerSocketChannel`.
- [ ] Xác định rõ requirement **IPv4, IPv6 hay local Unix-domain IPC**.
- [ ] Nếu cần Java 15: chỉ dùng `INET`/`INET6` với overload này; `UNIX` cần **JDK 16+**.
- [ ] Kiểm tra runtime/provider hỗ trợ family, đặc biệt IPv6 hoặc Unix-domain.
- [ ] Tạo listener với `ServerSocketChannel.open(family)` và **bind trước accept**.
- [ ] Chọn local address tường minh nếu cần giới hạn phạm vi truy cập; dùng port 0 cho demo hoặc test.
- [ ] Đọc lại `getLocalAddress()` khi cần biết port OS đã cấp.
- [ ] Dùng `try-with-resources` để đóng socket và connection đúng cách.
- [ ] Khi dùng non-blocking selector, đăng ký **`OP_ACCEPT`**, xử lý `accept()==null`, đổi accepted channel sang non-blocking nếu cần.
- [ ] Kiểm tra `supportedOptions()` thay vì giả định cùng option trên INET/UNIX.
- [ ] Không giả định IPv6 socket hỗ trợ dual-stack y hệt mọi nền tảng.
- [ ] Định nghĩa timeouts, framing, validation và resource limits ở tầng ứng dụng.
- [ ] Kiểm thử trên hệ điều hành/JDK/runtime image triển khai thật, không chỉ trên máy dev.

## 12. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| `open(ProtocolFamily)` mới xuất hiện ở Java 16 | Phương thức có từ **Java 15**; **UNIX family** mới có từ Java 16 |
| `INET` = TCP và `INET6` = UDP | `INET`/`INET6` phân biệt IPv4/IPv6; ServerSocketChannel là stream socket |
| `open(INET)` tự bind vào port | Phải gọi `bind(...)` |
| Có channel mở là `accept` được | Chưa bind sẽ ném `NotYetBoundException` |
| `SocketChannel.accept` tạo listener | `accept` là phương thức trên `ServerSocketChannel`, trả về `SocketChannel` |
| `INET6` luôn chỉ nhận IPv6 | Chính sách dual-stack/platform cần được kiểm chứng |
| `open(UNIX)` có thể bind `InetSocketAddress` | Dùng `UnixDomainSocketAddress` với Unix-domain channel |
| `socket()` hỗ trợ mọi family | Với Unix-domain channel, API có thể ném `UnsupportedOperationException` |
| Listener non-blocking trả accepted channel non-blocking | Accepted channel ban đầu vẫn **blocking** |
| Non-blocking `accept` chưa có connection sẽ treo | Nó trả `null`; cần xử lý đúng |
| `read(ByteBuffer)` trả đúng một message | TCP là byte stream; cần framing và đọc/ghi từng phần |
| Chọn `INET` đã tự bảo mật traffic | Chưa có TLS hay authorization; bind và mạng vẫn cần được cấu hình |

## 13. Bài tập và đáp án

**Bài 1.** Một ứng dụng bắt buộc chạy **JDK 15**. Có thể viết `ServerSocketChannel.open(StandardProtocolFamily.INET)` không? Có thể viết `open(StandardProtocolFamily.UNIX)` không?

**Bài 2.** Server gọi `open(INET)`, rồi `accept()` ngay mà chưa gọi `bind()`. Điều gì xảy ra?

**Bài 3.** Một chương trình dùng `ServerSocketChannel.open(INET6)` trên máy không hỗ trợ IPv6. API có thể báo gì và ứng dụng nên làm gì?

**Bài 4.** Một server bind `127.0.0.1:0`. Lấy port thật ở đâu và port 0 có nghĩa server sẽ nghe ở port 0 không?

**Bài 5.** Server đã chuyển sang non-blocking mode và gọi `accept()` nhưng không có pending connection. Kết quả là gì?

**Bài 6.** Một listener non-blocking nhận được một `SocketChannel`. Muốn dùng `Selector` để theo dõi đọc/ghi trên accepted channel, cần chú ý điều gì?

**Bài 7.** Một team muốn dùng `ServerSocketChannel` để nhận UDP datagram cho dịch vụ telemetry. Có đúng API không?

**Bài 8.** Một dịch vụ dùng Unix-domain socket với đường dẫn `/tmp/demo.sock`. Chỉ cần đóng `ServerSocketChannel` là mọi hệ điều hành sẽ tự xóa đường dẫn và bảo đảm không ai khác truy cập được chứ?

**Đáp án:**

1. `open(INET)` **có**, vì overload có từ Java 15. `StandardProtocolFamily.UNIX` **không** có trong JDK 15; cần Java 16+ và nền tảng hỗ trợ.
2. `accept()` ném **`NotYetBoundException`**. Phải bind local address trước.
3. Có thể `UnsupportedOperationException` do family không được hỗ trợ. Cần chẩn đoán môi trường, yêu cầu IPv6 và chọn fallback **chủ đích**, không âm thầm đổi family nếu trái hợp đồng.
4. Sau bind, gọi `(InetSocketAddress) server.getLocalAddress()`, rồi `getPort()`. Port 0 là yêu cầu **OS chọn ephemeral port**, không phải cổng lắng nghe cố định bằng 0.
5. Trả về **`null`**, không phải block vô hạn; cần đợi sự kiện bằng Selector hoặc cơ chế phù hợp.
6. Accepted channel ban đầu **blocking**, phải `configureBlocking(false)` trước khi đăng ký `OP_READ`/`OP_WRITE` với `Selector`.
7. Không. Dùng `DatagramChannel` hoặc `DatagramSocket` cho UDP; `ServerSocketChannel` là stream listening channel.
8. Không. Cần kiểm tra chính sách filesystem/OS, quyền truy cập, owner và quản lý cleanup pathname an toàn; **không** giả định close tự xóa socket file trên mọi nền tảng.

## Tài liệu tham khảo hiện hành

- [Oracle Java SE 26 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): `open(ProtocolFamily)` (`@since 15`), `bind`, `accept`, `getLocalAddress`, options và non-blocking semantics.
- [Oracle Java SE 26 — StandardProtocolFamily](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html): `INET`, `INET6`, `UNIX` (`@since 16`).
- [Oracle Java SE 26 — SocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html): client channel theo family, `connect`, `read`, `write`.
- [Oracle Java SE 26 — SelectorProvider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/spi/SelectorProvider.html): provider mặc định và `openServerSocketChannel(ProtocolFamily)`.
- [Oracle Java SE 26 — UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/UnixDomainSocketAddress.html): kiểu địa chỉ Unix-domain từ Java 16.
- [OpenJDK — JEP 380: Unix-Domain Socket Channels](https://openjdk.org/jeps/380): bổ sung Unix-domain stream sockets ở Java 16.
- [Oracle Java SE 15 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): mốc giới thiệu overload `open(ProtocolFamily)` tại Java 15.