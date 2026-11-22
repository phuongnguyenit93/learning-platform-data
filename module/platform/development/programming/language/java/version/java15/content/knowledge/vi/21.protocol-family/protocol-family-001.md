# SocketChannel.open(ProtocolFamily) trong Java 15+: chọn họ giao thức khi mở socket channel

> **Chủ đề cha: Protocol family.** Từ **Java 15**, `java.nio.channels.SocketChannel` có overload `SocketChannel.open(ProtocolFamily family)`. Thay vì chỉ yêu cầu một Internet socket channel mặc định, ứng dụng có thể **chỉ định họ giao thức** khi tạo channel: `StandardProtocolFamily.INET` (IPv4), `INET6` (IPv6) hoặc, từ **Java 16**, `UNIX` (Unix-domain stream socket). Đây là cách chọn loại socket được hỗ trợ bởi hệ điều hành/`SelectorProvider`; **chưa phải kết nối tới remote** và không tự bảo đảm IPv6 hay Unix-domain sockets sẽ khả dụng trên mọi môi trường.

Bài sử dụng kiến thức và API vẫn được hỗ trợ trong Java hiện đại. Các chương trình chạy độc lập bên dưới biên dịch bằng `javac --release 17`, đã được kiểm tra với JDK 24; mọi kết quả phụ thuộc IPv6/Unix-domain socket được ghi rõ điều kiện nền tảng.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích `ProtocolFamily` là gì, tại sao `SocketChannel.open(family)` nhận **một family** mà không phải địa chỉ remote.
2. Phân biệt `StandardProtocolFamily.INET`, `INET6`, `UNIX` và cột mốc phiên bản **Java 15 vs Java 16**.
3. So sánh ba overload `SocketChannel.open()`, `open(ProtocolFamily)` và `open(SocketAddress)` về trạng thái sau khi mở.
4. Mở **client và server tương thích** bằng `SocketChannel.open(family)` và `ServerSocketChannel.open(family)`, sau đó `bind`/`connect`/`accept`.
5. Dùng đúng `InetSocketAddress` cho Internet sockets, `UnixDomainSocketAddress` cho Unix-domain sockets.
6. Đọc/ghi TCP hoặc Unix-domain **byte stream** bằng `ByteBuffer` với vòng lặp xử lý partial I/O.
7. Nhận diện `UnsupportedOperationException` (family không được hỗ trợ), `UnsupportedAddressTypeException` (address type không phù hợp), `NotYetConnectedException` và `IOException`.
8. Phân biệt **protocol family**, **transport semantics (stream vs datagram)**, **blocking/non-blocking**, **network availability** và **authentication**.
9. Cân nhắc portability, file path/permissions của Unix-domain socket và quản lý tài nguyên bằng `try-with-resources`.

## 2. ProtocolFamily là gì?

`java.net.ProtocolFamily` là interface mô tả **họ giao thức truyền thông**. Trong JDK, enum `java.net.StandardProtocolFamily` triển khai interface đó:

| Family | Ý nghĩa | Loại địa chỉ thông thường | Ghi chú phiên bản |
| --- | --- | --- | --- |
| `StandardProtocolFamily.INET` | Họ Internet Protocol Version 4, IPv4 | `InetSocketAddress` có `Inet4Address` | Có từ trước Java 15, overload `SocketChannel.open(family)` có từ **Java 15** |
| `StandardProtocolFamily.INET6` | Họ Internet Protocol Version 6, IPv6 | `InetSocketAddress` có `Inet6Address` | Khả dụng tùy hệ điều hành, VM và cấu hình |
| `StandardProtocolFamily.UNIX` | Unix-domain local IPC, `AF_UNIX` | `UnixDomainSocketAddress` dùng filesystem path | JDK NIO channel hỗ trợ từ **Java 16** / JEP 380 |

**Điểm quan trọng:** Family **không phải** một tên host, số port, proxy, DNS resolver hay URL. `INET` và `INET6` chỉ ra loại Internet socket; địa chỉ cụ thể và port chỉ xuất hiện khi `bind(...)` hoặc `connect(...)`.

### 2.1. Family không đồng nghĩa TCP/UDP

`SocketChannel` là **stream-oriented connecting channel**:
- Với `INET`/`INET6`, thông thường đó là **TCP socket**.
- Với `UNIX`, đó là **Unix-domain stream socket**, dùng cho IPC cùng máy.
- Muốn gửi/nhận **UDP datagrams**, dùng `DatagramChannel`/`DatagramSocket` — không phải `SocketChannel`.
- Đừng suy ra rằng `SocketChannel.open(StandardProtocolFamily.UNIX)` sẽ tạo Unix-domain *datagram* socket. JDK hỗ trợ ở đây là **stream socket channel**; Unix-domain datagrams không được cung cấp như một phép thay thế tương ứng trong chuẩn NIO này.

Nói cách khác, **lựa chọn channel class** xác định mô hình I/O (stream hay datagram); **family** chọn nhóm giao thức/địa chỉ thích hợp bên trong mô hình đó.

### 2.2. Vì sao phải chỉ định family khi có `open()` không tham số?

`SocketChannel.open()` tạo một Internet socket channel theo default provider/configuration. Tùy môi trường, socket có thể hỗ trợ IPv4/IPv6 theo cơ chế của hệ điều hành và JVM. Nếu một protocol yêu cầu rõ IPv4, IPv6 hoặc Unix-domain stream, overload nhận `ProtocolFamily` giúp **thể hiện yêu cầu ngay lúc tạo channel**, thay vì thử tùy ý sau đó.

Ví dụ:

~~~java
// Đoạn minh họa nằm trong một phương thức có throws IOException.
// Các imports cần thiết nằm trong ví dụ đầy đủ phía dưới.
SocketChannel ipv4 =
    SocketChannel.open(StandardProtocolFamily.INET);
SocketChannel ipv6 =
    SocketChannel.open(StandardProtocolFamily.INET6);
SocketChannel local =
    SocketChannel.open(StandardProtocolFamily.UNIX);
~~~

Mỗi lời gọi có thể mở một channel thành công hoặc thất bại tùy family được hỗ trợ. Trong code thật, **đóng channel** bằng `try-with-resources`; đừng dùng đoạn minh họa trên nguyên xi vì nó chưa giải phóng tài nguyên.

## 3. Chữ ký và hợp đồng `SocketChannel.open(ProtocolFamily)`

API:

~~~java
// Chữ ký API, không phải một chương trình độc lập.
public static SocketChannel open(ProtocolFamily family)
        throws IOException
~~~

Nó hoạt động tương đương việc yêu cầu **system-wide default `SelectorProvider`** mở socket channel thông qua `openSocketChannel(family)`. Kết quả là một `SocketChannel`:
- **Đang mở** (`isOpen() == true`) khi tạo thành công.
- **Chưa kết nối** (`isConnected() == false`).
- Ở **blocking mode mặc định**, trừ khi ứng dụng gọi `configureBlocking(false)`.
- Chưa có peer; phải gọi `connect(remote)` (và quản lý connection establishment nếu non-blocking).
- Việc mở không chứng minh remote còn hoạt động, cổng có listener hoặc authorization sẽ thành công.

### 3.1. Bảng so sánh overload

| Cách gọi | Family/remote được quyết định thế nào? | Sau khi trả thành công |
| --- | --- | --- |
| `SocketChannel.open()` | Provider tạo **Internet protocol socket** mặc định | **Open, chưa connected** |
| `SocketChannel.open(StandardProtocolFamily.INET)` | Yêu cầu IPv4 family | **Open, chưa connected** |
| `SocketChannel.open(StandardProtocolFamily.INET6)` | Yêu cầu IPv6 family | **Open, chưa connected** |
| `SocketChannel.open(StandardProtocolFamily.UNIX)` | Yêu cầu Unix-domain stream socket (Java 16+) | **Open, chưa connected** |
| `SocketChannel.open(remoteAddress)` | Dựa trên `SocketAddress`; hiện hành nhận Internet/Unix-domain address theo API | **Đã connected**, nếu không có lỗi |
| `ServerSocketChannel.open(family)` | Mở server channel cùng family | **Open, chưa bind**; cần `bind()` trước `accept()` |

**Không nhầm** `open(ProtocolFamily)` với `open(SocketAddress)`. Chúng cùng tên, nhưng overload thứ hai có thể **kết nối ngay trong lúc mở**.

### 3.2. Các ngoại lệ quan trọng

- `NullPointerException`: `family == null`.
- `UnsupportedOperationException`: `SelectorProvider` hoặc nền tảng không hỗ trợ family được chỉ định; ví dụ `INET6` khi IPv6 không khả dụng.
- `IOException`: sự cố I/O khi mở socket channel hoặc các thao tác về sau.
- `UnsupportedAddressTypeException`: khi `connect/bind` dùng `SocketAddress` không phù hợp với socket channel.
- `NotYetConnectedException`: đọc/ghi channel chưa connected.
- `UnresolvedAddressException`: địa chỉ Internet remote chưa được phân giải khi `connect` theo hợp đồng.
- `AlreadyConnectedException` hoặc `ConnectionPendingException`: gọi `connect` không đúng trạng thái.
- `ConnectException` hoặc ngoại lệ `IOException` khác: remote unreachable/refused, tùy tình huống.
- `ClosedChannelException` và các tình huống interruption/async close khi vận hành channel.

Không viết một `catch (Exception)` rồi âm thầm chuyển sang family khác nếu protocol hoặc policy bảo mật yêu cầu family cố định. Hãy ghi nhận lỗi có thể hành động được và **chỉ fallback** khi ứng dụng đã xác định một phương án an toàn, tương thích.

## 4. Kết hợp client và server đúng family

Một `SocketChannel` là đầu kết nối phía client hoặc một channel đã được server chấp nhận. Để nghe kết nối mới, sử dụng `ServerSocketChannel`. Luồng tối thiểu:

~~~text
Server                                          Client
------                                          ------
ServerSocketChannel.open(family)                SocketChannel.open(family)
        |                                               |
bind(local SocketAddress)                       connect(remote SocketAddress)
        |                                               |
accept() -> SocketChannel peer                          |
        |                                               |
read/write ByteBuffer  <------ byte stream ------> read/write ByteBuffer
        |                                               |
close peer / server                              close client
~~~

### 4.1. Loại địa chỉ phải phù hợp

| Family/Socket | `SocketAddress` phù hợp thường dùng | Không nên dùng |
| --- | --- | --- |
| `INET` | `new InetSocketAddress(ipv4, port)` | `UnixDomainSocketAddress` |
| `INET6` | `new InetSocketAddress(ipv6, port)` | `UnixDomainSocketAddress` |
| `UNIX` | `UnixDomainSocketAddress.of(path)` | `InetSocketAddress` |

**Cần nuance về dual stack:** `INET6` có thể tương tác với IPv4-mapped addresses tùy hệ điều hành và cài đặt VM. **Không tự khẳng định** “INET6 luôn từ chối mọi IPv4 endpoint” trên tất cả platform. Nếu giao thức yêu cầu IPv6 thuần, dùng IPv6 literal/address rõ ràng và có integration test/cấu hình OS tương ứng.

### 4.2. Mở không đồng nghĩa bind hoặc connect

- `ServerSocketChannel.open(family)`: có channel để làm listener nhưng **chưa bind**.
- `server.bind(address)`: gắn server socket vào địa chỉ local; với Internet có thể dùng port `0` để OS tự chọn ephemeral port.
- `SocketChannel.open(family)`: chưa connected, có thể đặt socket options/bind local nếu cần.
- `client.connect(remote)`: bắt đầu kết nối. **Trong blocking mode**, khi trả về thành công, channel đã connected.
- `server.accept()`: trả một `SocketChannel` mới đã connected; server listener vẫn tồn tại để nhận nhiều kết nối khác.
- `client.getRemoteAddress()` có thể được dùng sau khi connected để xem remote; kiểu địa chỉ phản ánh family.

## 5. Ví dụ 1 — Chọn IPv4 bằng `INET` và trao đổi TCP stream

Chương trình dùng `StandardProtocolFamily.INET` ở **cả listener lẫn client**, bind vào IPv4 loopback `127.0.0.1` với port ngẫu nhiên và trao đổi `PING`/`PONG`.

**Tệp `ExplicitFamilyIPv4Demo.java` — độc lập, Java 17+:**

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;

public class ExplicitFamilyIPv4Demo {
    static void writeFully(SocketChannel channel, String data)
            throws Exception {
        ByteBuffer buffer = StandardCharsets.UTF_8.encode(data);
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    static String readExactly(SocketChannel channel, int count)
            throws Exception {
        ByteBuffer buffer = ByteBuffer.allocate(count);
        while (buffer.hasRemaining()) {
            if (channel.read(buffer) == -1) {
                throw new IllegalStateException(
                        "Unexpected end of stream");
            }
        }
        buffer.flip();
        return StandardCharsets.UTF_8.decode(buffer).toString();
    }

    public static void main(String[] args) throws Exception {
        try (SocketChannel defaultChannel = SocketChannel.open()) {
            System.out.println("defaultOpenNotConnected=" +
                    !defaultChannel.isConnected());
        }

        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});

        try (ServerSocketChannel server =
                     ServerSocketChannel.open(
                         StandardProtocolFamily.INET);
             SocketChannel client =
                     SocketChannel.open(StandardProtocolFamily.INET)) {

            server.bind(new InetSocketAddress(loopback, 0));
            System.out.println("explicitOpenNotConnected=" +
                    !client.isConnected());

            client.connect(server.getLocalAddress());

            try (SocketChannel peer = server.accept()) {
                System.out.println("bothConnected=" +
                        (client.isConnected() && peer.isConnected()));
                System.out.println("remoteIsInetSocketAddress=" +
                        (client.getRemoteAddress()
                                instanceof InetSocketAddress));

                writeFully(client, "PING");
                System.out.println("serverRead=" +
                        readExactly(peer, 4));

                writeFully(peer, "PONG");
                System.out.println("clientRead=" +
                        readExactly(client, 4));
            }
        }
    }
}
~~~

**Chạy từ thư mục chứa file:**

~~~bash
javac --release 17 -encoding UTF-8 ExplicitFamilyIPv4Demo.java
java ExplicitFamilyIPv4Demo
~~~

**Stdout đã kiểm chứng với JDK 24/Windows IPv4 loopback:**

~~~text
defaultOpenNotConnected=true
explicitOpenNotConnected=true
bothConnected=true
remoteIsInetSocketAddress=true
serverRead=PING
clientRead=PONG
~~~

### 5.1. Giải thích

**`defaultOpenNotConnected=true`:** `open()` không tham số chỉ mở Internet socket channel. Nó không tự gửi gói SYN tới bất kỳ remote cụ thể nào.

**`explicitOpenNotConnected=true`:** Tương tự, `open(INET)` chọn family khi khởi tạo nhưng vẫn không biết endpoint remote; vì vậy `isConnected() == false` trước `connect()`.

**`bothConnected=true`:** `client.connect(...)` trong blocking mode thiết lập kết nối tới listener đang bind; `server.accept()` trả channel phía server đã connected.

**`serverRead=PING`, `clientRead=PONG`:** Hai channel trao đổi một byte stream. Vòng lặp `writeFully`/`readExactly` có vai trò quan trọng vì một lần `write` hay `read` **không đảm bảo xử lý toàn bộ bytes cần truyền** ngay lập tức.

### 5.2. Điều gì làm ví dụ có output ổn định?

- Server bind vào `127.0.0.1` thay vì hostname có thể resolve IPv4 hoặc IPv6 khác nhau.
- Port `0` để OS chọn một port đang rảnh; không phụ thuộc port hardcode.
- Tất cả trên một máy và đã có listener trước khi `connect`.
- Sử dụng blocking mode mặc định, tránh logic `Selector` không cần thiết.
- Gửi đúng 4 ASCII bytes cho mỗi message, đọc đúng 4 bytes bằng vòng lặp.
- Tự đóng cả client, peer và listener bằng `try-with-resources`.

Kết quả đã được kiểm tra trong môi trường có IPv4 loopback. Nếu OS/network sandbox chặn socket binding, chương trình vẫn có thể ném `IOException`; đó là vấn đề môi trường, không phải bằng chứng `open(INET)` bị xóa khỏi Java.

## 6. Ví dụ 2 — Chọn IPv6 bằng `INET6` và xử lý nền tảng chưa hỗ trợ

Không được mặc định rằng mọi host đang bật IPv6. Java và hệ điều hành có thể cấm hoặc vô hiệu hóa IPv6. Do đó ví dụ tạo endpoint loopback IPv6 `::1` và ghi nhận khả năng không hỗ trợ thay vì khẳng định lúc nào cũng thành công.

**Tệp `ExplicitFamilyIPv6Demo.java` — Java 17+:**

~~~java
import java.io.IOException;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;

public class ExplicitFamilyIPv6Demo {
    static void send(SocketChannel channel, String text)
            throws IOException {
        ByteBuffer buffer = StandardCharsets.UTF_8.encode(text);
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    static String readFour(SocketChannel channel)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(4);
        while (buffer.hasRemaining()) {
            if (channel.read(buffer) < 0) {
                throw new IOException("Unexpected EOF");
            }
        }
        buffer.flip();
        return StandardCharsets.UTF_8.decode(buffer).toString();
    }

    public static void main(String[] args) throws Exception {
        InetAddress ipv6 = InetAddress.getByName("::1");
        System.out.println("literalIsIPv6=" +
                (ipv6 instanceof Inet6Address));

        try (ServerSocketChannel server =
                     ServerSocketChannel.open(
                         StandardProtocolFamily.INET6);
             SocketChannel client =
                     SocketChannel.open(
                         StandardProtocolFamily.INET6)) {

            server.bind(new InetSocketAddress(ipv6, 0));
            client.connect(server.getLocalAddress());

            try (SocketChannel peer = server.accept()) {
                send(client, "PING");
                System.out.println("ipv6RoundTrip=" +
                        "PING".equals(readFour(peer)));
            }
        } catch (UnsupportedOperationException | IOException ex) {
            System.out.println("ipv6Unavailable=" +
                    ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 ExplicitFamilyIPv6Demo.java
java ExplicitFamilyIPv6Demo
~~~

**Stdout đã quan sát trên JDK 24 có IPv6 loopback hoạt động:**

~~~text
literalIsIPv6=true
ipv6RoundTrip=true
~~~

Trên hệ thống có IPv6 disabled hoặc gặp lỗi mạng/bind, có thể thay dòng thứ hai bằng:

~~~text
ipv6Unavailable=UnsupportedOperationException
~~~

hoặc một tên exception thuộc `IOException`, tùy nguyên nhân thực tế. **Không có một output “unavailable” cố định cho mọi nền tảng.**

### 6.1. Cẩn thận với hệ thống dual-stack

`INET6` xác định family được yêu cầu; trên một số nền tảng, IPv6 socket còn có thể hỗ trợ kết nối IPv4-mapped, trên nơi khác thì không. Hãy:
- Dùng `::1` nếu muốn thử IPv6 loopback.
- Không dựa vào hostname `localhost` để tự suy ra phiên bản địa chỉ được chọn.
- Xác minh hoạt động với OS/VM thực tế, bao gồm cấu hình như `java.net.preferIPv4Stack` nếu ứng dụng có thiết lập liên quan.
- Nếu yêu cầu IPv6-only là **security/network policy**, cần cấu hình và kiểm tra ở tầng OS/socket/network tương ứng; mỗi lựa chọn `ProtocolFamily` chưa tự định nghĩa mọi quy tắc firewall/identity.

### 6.2. Không nên “fallback sang IPv4” một cách vô điều kiện

Có ứng dụng cho phép IPv4/IPv6 dual support; có ứng dụng buộc IPv6 do network architecture. Khi `open(INET6)` thất bại:
- Nếu protocol **cho phép** IPv4, có thể có chiến lược fallback sang `INET` kèm logging và test.
- Nếu protocol **yêu cầu** IPv6-only, phải **fail closed** thay vì âm thầm đổi hướng truyền, vì điều đó có thể vi phạm ràng buộc deployment/security.

Đây là quyết định ứng dụng, không phải hành vi retry/fallback được `SocketChannel.open(family)` bảo đảm.

## 7. Ví dụ 3 — Unix-domain stream socket: `StandardProtocolFamily.UNIX` từ Java 16

**JEP 380** đưa Unix-domain socket channels vào JDK **16**. Chúng dùng `UnixDomainSocketAddress` chứa filesystem path, thay vì IP/port, và thích hợp cho **IPC cùng host**. API `open(ProtocolFamily)` đã có từ Java 15; nhưng enum family `UNIX` và kiểu địa chỉ Unix-domain đi cùng được bổ sung ở Java 16.

Điều này có nghĩa:
- Mã nguồn dùng `StandardProtocolFamily.UNIX` cần JDK **16+**.
- Ví dụ trong bài dùng `--release 17` để chắc chắn có đủ API và giữ mã Java LTS-compatible.
- Trên OS/VM không hỗ trợ Unix-domain socket channels, mở có thể ném `UnsupportedOperationException` hoặc thao tác bind/connect có thể gặp `IOException`.
- Đây là **stream socket**, không phải Unix-domain datagram socket.
- `SocketChannel.socket()` không áp dụng cho Unix-domain socket channel; phương thức này có thể ném `UnsupportedOperationException`. Dùng NIO `SocketChannel` trực tiếp.

### 7.1. Mã hoàn chỉnh — `UnixFamilyRoundTripDemo.java`

Chương trình tạo thư mục tạm riêng, dùng path `rpc.sock`, mở server/client qua `UNIX`, rồi trao đổi `PING`/`PONG`. Nó đóng channels và cố gắng dọn filesystem path ở `finally`.

~~~java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class UnixFamilyRoundTripDemo {
    static void writeFully(SocketChannel ch, String text)
            throws Exception {
        ByteBuffer buffer = StandardCharsets.UTF_8.encode(text);
        while (buffer.hasRemaining()) {
            ch.write(buffer);
        }
    }

    static String readExactly(SocketChannel ch, int length)
            throws Exception {
        ByteBuffer buf = ByteBuffer.allocate(length);
        while (buf.hasRemaining()) {
            if (ch.read(buf) < 0) {
                throw new IllegalStateException("Unexpected EOF");
            }
        }
        buf.flip();
        return StandardCharsets.UTF_8.decode(buf).toString();
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("java-uds-");
        Path path = directory.resolve("rpc.sock");

        try {
            UnixDomainSocketAddress address =
                    UnixDomainSocketAddress.of(path);

            try (ServerSocketChannel server =
                     ServerSocketChannel.open(
                         StandardProtocolFamily.UNIX);
                 SocketChannel client =
                     SocketChannel.open(
                         StandardProtocolFamily.UNIX)) {

                server.bind(address);
                client.connect(address);

                try (SocketChannel accepted = server.accept()) {
                    System.out.println("unixConnected=" +
                            (client.isConnected()
                                    && accepted.isConnected()));
                    System.out.println("unixRemoteAddressType=" +
                            (client.getRemoteAddress()
                                    instanceof UnixDomainSocketAddress));

                    writeFully(client, "PING");
                    System.out.println("serverRead=" +
                            readExactly(accepted, 4));

                    writeFully(accepted, "PONG");
                    System.out.println("clientRead=" +
                            readExactly(client, 4));
                }
            }
        } catch (UnsupportedOperationException ex) {
            System.out.println("unixUnsupported=true");
        } finally {
            Files.deleteIfExists(path);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 UnixFamilyRoundTripDemo.java
java UnixFamilyRoundTripDemo
~~~

**Stdout đã kiểm chứng trên JDK 24/Windows có Unix-domain sockets:**

~~~text
unixConnected=true
unixRemoteAddressType=true
serverRead=PING
clientRead=PONG
~~~

Khi nền tảng không hỗ trợ `UNIX` và ném `UnsupportedOperationException`, chương trình thay vì chạy luồng trao đổi sẽ in:

~~~text
unixUnsupported=true
~~~

**Lưu ý:** Các lỗi khác như socket path quá dài, permission, bind collision hoặc OS I/O không được bài thử che giấu. Ví dụ có thể ném `IOException` khi gặp chúng; đây là các lỗi thật cần kiểm tra thay vì tự gắn nhãn “UNIX unsupported”.

### 7.2. Unix-domain socket path không phải một tệp dữ liệu thông thường

`UnixDomainSocketAddress.of(path)` chỉ **tạo địa chỉ**, không tự mở kênh hay kết nối. `server.bind(address)` gắn listener vào một tên socket trong filesystem. Sau khi dùng:
- Đóng accepted/client/server channels đúng thứ tự.
- Dọn socket path khi thích hợp; không xóa **path không thuộc quyền sở hữu của ứng dụng**.
- Chú ý hệ điều hành có giới hạn **độ dài tên/path** cho socket (thường gần 100 bytes; tùy nền tảng).
- Nếu app sử dụng một path cố định, kiểm tra collisions, permissions, owner và nguy cơ *pre-creation/path hijacking*. Tạo thư mục sở hữu riêng với chính sách phù hợp.
- Unix-domain socket là IPC nội bộ host, **không tự bảo đảm** peer identity hay authorization. Với dữ liệu nhạy cảm, xem xét OS permissions, peer credentials và kiểm tra protocol phù hợp.
- Tạo một thư mục tạm ngẫu nhiên giúp tránh va chạm khi chạy test; trong production cần đường dẫn và chính sách vòng đời rõ ràng.

### 7.3. Vì sao không dùng port như TCP?

Unix-domain stream sockets được định danh bằng filesystem path (ví dụ `/run/myservice.sock` hoặc path tương ứng trên Windows), không phải IP + TCP port. Vì vậy:

~~~java
// Minh họa đúng kiểu địa chỉ:
UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(Path.of("/run/myservice.sock"));

// Không dùng InetSocketAddress cho SocketChannel UNIX:
SocketChannel channel =
    SocketChannel.open(StandardProtocolFamily.UNIX);
~~~

Đoạn này chỉ minh họa kiểu. Trước `connect(address)` phải có listener `UNIX` tương ứng, path có thể cần permissions và tồn tại; mở channel không tự tạo server.

## 8. Ví dụ 4 — Lỗi mở family, trạng thái chưa connected và address mismatch

Ví dụ sau cho thấy:
- `open((ProtocolFamily)null)` bị từ chối.
- `open(INET)` chưa connected, đọc ngay gây `NotYetConnectedException`.
- Dùng `UnixDomainSocketAddress` trên socket `INET` không khớp.
- `socket()` của `INET` có adapter `java.net.Socket`.
- `socket()` của `UNIX` không có adapter Internet socket.

**Tệp `FamilyBoundaryDemo.java` — độc lập Java 17+:**

~~~java
import java.net.ProtocolFamily;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.NotYetConnectedException;
import java.nio.channels.SocketChannel;
import java.nio.channels.UnsupportedAddressTypeException;
import java.nio.file.Path;

public class FamilyBoundaryDemo {
    public static void main(String[] args) throws Exception {
        try {
            SocketChannel.open((ProtocolFamily) null);
            System.out.println("nullFamilyRejected=false");
        } catch (NullPointerException expected) {
            System.out.println("nullFamilyRejected=true");
        }

        try (SocketChannel inet =
                     SocketChannel.open(StandardProtocolFamily.INET)) {
            System.out.println("inetStartsDisconnected=" +
                    !inet.isConnected());
            System.out.println("inetSocketAdapterPresent=" +
                    (inet.socket() != null));

            try {
                inet.read(ByteBuffer.allocate(1));
                System.out.println("unconnectedReadRejected=false");
            } catch (NotYetConnectedException expected) {
                System.out.println("unconnectedReadRejected=true");
            }

            try {
                inet.connect(UnixDomainSocketAddress.of(
                        Path.of("not-a-real.sock")));
                System.out.println("mismatchedAddressRejected=false");
            } catch (UnsupportedAddressTypeException expected) {
                System.out.println("mismatchedAddressRejected=true");
            }
        }

        try (SocketChannel unix =
                     SocketChannel.open(StandardProtocolFamily.UNIX)) {
            System.out.println("unixStartsDisconnected=" +
                    !unix.isConnected());
            try {
                unix.socket();
                System.out.println("unixSocketAdapterUnavailable=false");
            } catch (UnsupportedOperationException expected) {
                System.out.println("unixSocketAdapterUnavailable=true");
            }
        } catch (UnsupportedOperationException expected) {
            System.out.println("unixFamilyUnavailable=true");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 FamilyBoundaryDemo.java
java FamilyBoundaryDemo
~~~

**Stdout đã kiểm chứng trên JDK 24 với `INET` và `UNIX` khả dụng:**

~~~text
nullFamilyRejected=true
inetStartsDisconnected=true
inetSocketAdapterPresent=true
unconnectedReadRejected=true
mismatchedAddressRejected=true
unixStartsDisconnected=true
unixSocketAdapterUnavailable=true
~~~

Nếu hệ điều hành/JVM không hỗ trợ `UNIX`, nhánh cuối có thể chỉ in:

~~~text
unixFamilyUnavailable=true
~~~

sau các dòng `INET`. Những ngoại lệ do I/O khác cần được điều tra riêng; không nên coi mọi failure là tính năng không hỗ trợ.

### 8.1. Tại sao `null` không có nghĩa “mặc định”?

`SocketChannel.open()` là overload không tham số để yêu cầu Internet socket mặc định. `SocketChannel.open((ProtocolFamily)null)` **không** được hiểu là overload mặc định; nó ném `NullPointerException`.

Để tránh nhầm overload, trong code có biến `ProtocolFamily family`, hãy validate cấu hình đầu vào và chỉ gọi `open()` nếu ứng dụng thực sự **cố ý** không chỉ định family.

### 8.2. Vì sao `socket()` khác nhau?

`SocketChannel.socket()` là cầu nối tới `java.net.Socket` khi channel thuộc Internet protocol socket. Với Unix-domain channel, adapter đó không được hỗ trợ theo Javadoc.

Nếu viết API abstraction dùng chung `INET` và `UNIX`, tránh thiết kế cứng vào `java.net.Socket`; thao tác đọc/ghi/đóng trực tiếp qua `SocketChannel` và các `SocketAddress` phù hợp sẽ nhất quán hơn.

## 9. Blocking vs non-blocking: family không quyết định cách chờ

Cả Internet socket channels và Unix-domain socket channels đều tham gia mô hình NIO. `open(family)` không tự làm I/O **non-blocking**:

~~~java
// Đoạn minh họa trong phương thức, chưa phải chương trình độc lập.
try (SocketChannel ch =
        SocketChannel.open(StandardProtocolFamily.INET)) {
    ch.configureBlocking(false);

    // Sau khi đã có remote tương thích:
    boolean connectedImmediately = ch.connect(remote);

    if (!connectedImmediately) {
        // Thực tế: đăng ký Selector/OP_CONNECT,
        // sau khi ready thì gọi finishConnect().
    }
}
~~~

**Quy tắc đúng:**

- Channel được tạo ở **blocking mode** theo mặc định.
- Với blocking mode, `connect(remote)` chờ hoàn tất thiết lập hoặc lỗi.
- Với non-blocking mode, `connect(remote)` có thể trả `false` trong khi kết nối còn pending.
- Sử dụng `Selector` và `SelectionKey.OP_CONNECT`, gọi `finishConnect()` để hoàn tất theo contract. Không cho rằng `connect() == false` nghĩa là kết nối hỏng.
- Đừng gọi `read/write` như thể kết nối đã hoàn tất khi `isConnected() == false`.
- Đối với stream I/O, `read/write` có thể partial. Trong non-blocking mode `read` có thể trả `0`; không viết vòng lặp busy-spin vô hạn mà không có event-loop/timeout.

`family` chỉ là lựa chọn protocol/socket class; blocking, selector, buffering và framing là những trục thiết kế khác.

## 10. TCP/Unix-domain là byte stream, không giữ ranh giới message

Hai ví dụ trao đổi `PING` và `PONG` với kích thước đã biết 4 bytes để đơn giản. Với ứng dụng thực, một lời gọi `write` **không tương ứng** một lời gọi `read`. TCP/Unix-domain stream không ghi nhớ ranh giới thông điệp ứng dụng.

Ví dụ:

~~~text
Sender:
    write("HELLO")
    write("WORLD")

Receiver có thể thấy:
    read("HELLOWORLD")
hoặc
    read("HEL"), read("LOWOR"), read("LD")
...
~~~

Phải có **framing**:
- Length prefix: số bytes payload rồi payload.
- Delimiter với escaping rõ ràng, cho protocol văn bản.
- Một định dạng đã chuẩn hóa như HTTP framing khi phù hợp.

Đảm bảo:
1. Parse length an toàn, giới hạn max frame size.
2. `readFully` đọc chính xác đủ bytes, xử lý EOF giữa frame.
3. `writeFully` không giả định một lần `write` gửi hết.
4. Encoding chuẩn như UTF-8.
5. Timeout, backpressure, flow control và xử lý peer disconnect.

Đừng dùng newline giản đơn cho dữ liệu nhị phân tùy ý nếu không có quy tắc escaping. Thay đổi family `INET` sang `UNIX` **không** biến byte stream thành message-oriented datagrams.

## 11. Provider/OS support: không chỉ nhìn vào enum

`SocketChannel.open(family)` gọi `SelectorProvider.provider().openSocketChannel(family)`. Provider mặc định được chọn theo cấu hình JDK và có thể khác nhau giữa nền tảng hoặc môi trường triển khai. Javadoc `SelectorProvider.openSocketChannel(ProtocolFamily)` quy định implementation mặc định có thể từ chối family không hỗ trợ.

### 11.1. Những điều cần kiểm tra trước triển khai

| Yếu tố | Câu hỏi cần trả lời |
| --- | --- |
| Java version | Chạy ít nhất **Java 15** cho overload, **Java 16** nếu dùng `UNIX`? |
| JVM provider | Provider có hỗ trợ family yêu cầu không, có provider tùy chỉnh không? |
| IPv6 | IPv6 có bật trên OS/VM/container/network namespace không? |
| Internet bind/connect | IP/interface và port có sẵn, firewall/ACL cho phép không? |
| Unix-domain sockets | OS hỗ trợ `AF_UNIX`, path hợp lệ và quyền file/directory phù hợp không? |
| Unix-domain path length | Absolute path sau resolve có vượt ngưỡng platform không? |
| Unix socket cleanup | Socket path có được dọn đúng khi crash/restart không? |
| Selector/non-blocking | Event loop có xử lý pending connect và partial read/write đúng không? |
| Error policy | Có phân biệt unsupported family, sai address, connection refused, permission denied, timeout và shutdown không? |

**Đừng lấy `StandardProtocolFamily.valueOf("UNIX")` thành công làm bằng chứng OS hỗ trợ Unix-domain socket.** Tên enum tồn tại trong JDK không bảo đảm native socket creation/bind/connect sẽ thành công.

### 11.2. Cẩn thận với `java.net.preferIPv4Stack`

Tùy JVM/platform, system property `java.net.preferIPv4Stack` có thể ảnh hưởng stack mà Internet sockets dùng. Ví dụ triển khai cố định một family nên có integration tests với cấu hình thực tế.

Đừng tự động bật/tắt property đó để “sửa” lỗi mà không hiểu ràng buộc IPv4/IPv6 và chính sách deployment. Nếu người dùng cần IPv6 thật, hãy xác nhận OS IPv6, network namespace, interface và firewall.

### 11.3. `UnsupportedOperationException` khác `IOException`

- `UnsupportedOperationException`: Family được yêu cầu **không được hỗ trợ** bởi provider/platform trong tình huống đó.
- `IOException`: Lỗi I/O cụ thể khi tạo, bind, connect, accept hoặc truyền.
- `UnsupportedAddressTypeException`: Kết hợp channel/address không hợp lệ; thường là lỗi lập trình/cấu hình.
- `NotYetConnectedException`: Vi phạm trạng thái channel khi làm I/O.

Không ghi log “UNIX không hỗ trợ” nếu thực tế là **Permission denied** hoặc path collision. Với hệ thống nhiều platform, phân loại đúng lỗi là chìa khóa cho việc khắc phục.

## 12. Bảo mật: chọn family không tự xác thực peer

### 12.1. Internet TCP sockets

`SocketChannel.open(INET)` hay `open(INET6)` chỉ quyết định network protocol family. Nó:
- Không bật TLS tự động.
- Không xác minh certificate hoặc hostname.
- Không chứng minh remote server đúng danh tính mong đợi chỉ vì đã TCP connect.
- Không kiểm tra application authorization.
- Không làm `InetSocketAddress` trở thành một identity có chữ ký.

Với lưu lượng nhạy cảm, dùng TLS với certificate/hostname validation và chính sách phù hợp, hoặc transport/security layer đã được thiết kế đáng tin cậy.

### 12.2. Unix-domain sockets

Unix-domain IPC thường không đi qua network ngoài host, nhưng **local** không đồng nghĩa “không ai khác truy cập được”:
- Nếu filesystem path nằm trong directory public, một process khác có thể chiếm tên/giả mạo listener.
- File permissions và owner cần được thiết kế theo OS.
- Nếu cần xác minh peer, có thể dùng OS peer credentials/socket options khi được hỗ trợ và policy tin cậy; không suy từ path string.
- Đóng và dọn path đúng lúc, không xóa một socket path mà ứng dụng không sở hữu.
- Nếu dùng container, xác định rõ mount namespace/path visibility và ai có thể truy cập socket.

**Cùng process/máy** không bảo đảm service tin cậy, cũng không bảo đảm binary payload không cần validate.

## 13. Chọn overload nào trong ứng dụng?

| Yêu cầu | API khuyến nghị |
| --- | --- |
| Cần Internet socket channel mặc định, không ghim IPv4/IPv6 | `SocketChannel.open()` |
| Ghim family IPv4 vì giao thức/triển khai yêu cầu | `SocketChannel.open(StandardProtocolFamily.INET)` |
| Ghim family IPv6 và có kiểm tra IPv6 availability | `SocketChannel.open(StandardProtocolFamily.INET6)` |
| Dùng local Unix-domain stream IPC (Java 16+) | `SocketChannel.open(StandardProtocolFamily.UNIX)` |
| Biết remote `InetSocketAddress`, muốn tạo và kết nối luôn | `SocketChannel.open(remote)` |
| Biết remote `UnixDomainSocketAddress`, muốn mở/kết nối luôn (Java 16+) | `SocketChannel.open(remote)` |
| Server/listener cùng family | `ServerSocketChannel.open(family)` rồi `bind` |
| UDP/datagram transport | `DatagramChannel.open(...)` hoặc `DatagramSocket`, **không** `SocketChannel` |

### 13.1. Có nên luôn gọi `open(ProtocolFamily)` không?

Không nhất thiết. Với HTTP client, database driver hoặc các thư viện cao cấp, tốt hơn thường là sử dụng thư viện/protocol client được bảo trì để nó quản lý DNS, IPv4/IPv6, connect timeout, TLS, pooling và retries phù hợp.

`open(family)` hữu ích khi bạn trực tiếp xây một network client/server/IPC component và có lý do cụ thể để chọn family. Tránh gắn cứng `INET6` khi sản phẩm muốn dual-stack và môi trường IPv6 không được bảo đảm.

## 14. Những sai lầm thường gặp

| Sai lầm | Tại sao sai? | Hướng sửa |
| --- | --- | --- |
| Cho rằng `open(INET)` đã kết nối đến server | Chỉ tạo channel, chưa có remote | Gọi `connect(remote)` |
| Cho rằng `open(ProtocolFamily)` tự chọn UDP/TCP | Family khác với transport model | Chọn đúng `SocketChannel` cho stream hoặc `DatagramChannel` cho UDP |
| Dùng `StandardProtocolFamily.UNIX` rồi truyền `InetSocketAddress` | Address type không tương thích | Dùng `UnixDomainSocketAddress.of(path)` |
| Dùng `StandardProtocolFamily.INET` rồi truyền `UnixDomainSocketAddress` | Family mismatch | Dùng Internet address đúng loại |
| Nhầm `open(SocketAddress)` là tạo socket chưa connected | Overload này tạo và kết nối | Chọn overload đúng ý |
| Cho rằng `INET6` có trên mọi máy | IPv6 có thể tắt/không được OS hỗ trợ | Handle unsupported/IO errors, test platform |
| Cho rằng Java 15 có `StandardProtocolFamily.UNIX` | Unix-domain socket support đến từ **Java 16** | Dùng JDK 16+, bài dùng Java 17+ |
| Cho rằng enum `UNIX` tồn tại là đủ | OS/provider/path có thể không hỗ trợ | Thử bind/connect trong integration test |
| Dùng `channel.socket()` cho `UNIX` | Adapter `java.net.Socket` không hỗ trợ | Dùng NIO `SocketChannel` |
| Dùng `open(null)` để chọn mặc định | `null` bị từ chối | Dùng overload `open()` |
| Đọc/ghi trước `connect/finishConnect` | Channel chưa connected | Kiểm state và hoàn tất kết nối |
| Gọi `connect() == false` là thất bại | Với non-blocking, đó là pending | `Selector`/`OP_CONNECT` rồi `finishConnect()` |
| Giả định một `write` == một `read` | Stream không bảo đảm message boundary | Framing, partial read/write handling |
| Hardcode Unix-domain path rất dài | OS có giới hạn độ dài path | Đặt path ngắn, kiểm platform |
| Bỏ quên xóa socket path | Bind lần sau có thể lỗi | Cleanup sau close, kiểm owner/path |
| Tự động fallback sang IPv4 khi IPv6 lỗi | Có thể vi phạm protocol/security policy | Fail hoặc fallback chỉ khi được thiết kế |
| Cho rằng Internet TCP connect có authentication | Connect không phải TLS | Bảo mật transport và xác minh peer |
| Cho rằng Unix-domain path tự tin cậy | Process khác có thể truy cập nếu permission yếu | Directory permissions, peer checks nếu cần |

## 15. Bài tập có đáp án

**Câu 1.** `SocketChannel.open(StandardProtocolFamily.INET)` trả về channel thành công. `isConnected()` bằng gì?

**Đáp án:** `false`. `open(family)` chỉ tạo channel; cần `connect(remote)` mới thiết lập kết nối.

**Câu 2.** Sự khác nhau giữa `SocketChannel.open()` và `SocketChannel.open(StandardProtocolFamily.INET6)`?

**Đáp án:** `open()` tạo Internet socket mặc định theo provider/platform; `open(INET6)` yêu cầu IPv6 family rõ ràng và có thể không được hỗ trợ nếu IPv6 unavailable. Cả hai ban đầu đều chưa connected.

**Câu 3.** Dùng `StandardProtocolFamily.UNIX` có chạy trên Java 15 không?

**Đáp án:** **Không** với JDK Java 15 chuẩn: overload `open(ProtocolFamily)` có từ 15, còn enum `UNIX` và Unix-domain channel support được thêm ở Java 16. Dùng Java 16+; ví dụ bài dùng 17+.

**Câu 4.** Vì sao `SocketChannel.open(StandardProtocolFamily.UNIX).socket()` không phải cách chuẩn để giao tiếp?

**Đáp án:** `socket()` là adapter `java.net.Socket` cho Internet protocol socket, không hỗ trợ Unix-domain channel theo API. Dùng NIO `SocketChannel` và `ByteBuffer`.

**Câu 5.** Muốn bind listener trên IPv4 loopback với port OS chọn, phải dùng API nào?

**Đáp án:** `ServerSocketChannel.open(StandardProtocolFamily.INET)` rồi `bind(new InetSocketAddress(ipv4Loopback, 0))`. Sau đó client `SocketChannel.open(INET)`/`connect(server.getLocalAddress())`; server `accept()`.

**Câu 6.** Tại sao `SocketChannel.open(StandardProtocolFamily.INET6)` có thể thất bại trước khi gọi `connect`?

**Đáp án:** Provider/platform có thể không hỗ trợ IPv6 hoặc không bật IPv6; hợp đồng cho phép `UnsupportedOperationException`, bên cạnh các I/O errors. `open(family)` đã yêu cầu tạo native socket của family đó.

**Câu 7.** `SocketChannel.open(StandardProtocolFamily.INET)` rồi `connect(UnixDomainSocketAddress.of(path))` bị từ chối. Sửa thế nào?

**Đáp án:** Mở channel `UNIX` (Java 16+) và dùng `UnixDomainSocketAddress`, hoặc nếu muốn Internet thì dùng `InetSocketAddress` thích hợp. Đừng ép sai address type.

**Câu 8.** Chương trình `write("HELLO")` rồi `write("WORLD")`. Bên nhận có thể `read` một lần ra `"HELLOWORLD"` không?

**Đáp án:** **Có**. Cả TCP và Unix-domain stream không giữ message boundaries; phải có length-prefix/delimiter framing nếu cần thông điệp riêng.

**Câu 9.** Non-blocking `connect(remote)` trả `false` có chứng minh server từ chối kết nối không?

**Đáp án:** **Không**. Nó có thể chỉ là kết nối đang pending; theo dõi readiness bằng `Selector` và gọi `finishConnect()`, handle lỗi thực sự.

**Câu 10.** `SocketChannel.open(StandardProtocolFamily.INET)` có bảo đảm dữ liệu được mã hóa và server xác thực không?

**Đáp án:** **Không**. Nó chỉ tạo Internet TCP stream channel theo family được yêu cầu. TLS/peer identity verification và authorization phải được bổ sung bởi protocol/library thích hợp.

**Câu 11.** Unix-domain socket dùng filesystem path. Có thể cho mọi user/process cùng máy truy cập vì là IPC nội bộ không?

**Đáp án:** Không nên mặc định. Phải kiểm owner/permission của directory/socket và chính sách xác minh peer. “Local” không đồng nghĩa “trusted”.

**Câu 12.** Nếu công cụ/server cần chạy cả trên các OS chưa chắc hỗ trợ Unix-domain sockets, làm sao thiết kế?

**Đáp án:** Phát hiện hỗ trợ thực tế bằng open/bind/connect có error handling; nếu policy cho phép, cung cấp lựa chọn TCP localhost có authentication thích hợp; nếu không, fail rõ nguyên nhân. Không giả định `UNIX` luôn hoạt động chỉ vì tên enum có sẵn.

## 16. Ghi nhớ

- **`SocketChannel.open(ProtocolFamily)` có từ Java 15**; chọn socket family lúc mở, **không tự connect**.
- **`INET` = IPv4, `INET6` = IPv6** theo lựa chọn family; availability và dual-stack behavior phụ thuộc OS/VM.
- **`UNIX` = Unix-domain stream IPC từ Java 16**, dùng `UnixDomainSocketAddress` thay `InetSocketAddress`, không dùng `socket()` như Internet channel.
- **`SocketChannel` là stream-oriented**, không phải UDP; family khác transport model.
- **Đúng cặp API:** `ServerSocketChannel.open(family)` → `bind`/`accept`; `SocketChannel.open(family)` → `connect`; xử lý partial `read/write`.
- **Phân biệt overload:** `open()` và `open(family)` chưa connected; `open(remote)` đã connected nếu thành công.
- **Đúng error handling:** unsupported family, address mismatch, pending/unconnected state và I/O error không thể gộp làm một.
- **Không bỏ qua security:** family lựa chọn mạng/IPC, không tự cấp TLS, authentication hay authorization; Unix path cũng cần permission/ownership policy.
- **Ví dụ Java 17+** đã kiểm tra trên JDK 24, đủ hiện đại và không dựa vào API lỗi thời.

## 17. Tài liệu chính thức còn áp dụng

- [Java SE 26 — `SocketChannel`: `open()`, `open(ProtocolFamily)`, `open(SocketAddress)`, `connect` và `socket()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 26 — `ServerSocketChannel`: `open(ProtocolFamily)` và `bind`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Java SE 26 — `SelectorProvider`: `openSocketChannel(ProtocolFamily)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/spi/SelectorProvider.html)
- [Java SE 26 — `StandardProtocolFamily`: INET, INET6, UNIX](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html)
- [Java SE 26 — `UnixDomainSocketAddress`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/UnixDomainSocketAddress.html)
- [Java SE 26 — `DatagramChannel` để phân biệt UDP với stream channel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [JEP 380 — Unix-Domain Socket Channels (Java 16)](https://openjdk.org/jeps/380)
- [Java SE 15 — `SocketChannel.open(ProtocolFamily)` đã xuất hiện ở JDK 15](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/SocketChannel.html)
