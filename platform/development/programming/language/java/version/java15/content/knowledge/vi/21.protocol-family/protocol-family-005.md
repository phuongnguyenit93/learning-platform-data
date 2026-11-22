# SelectorProvider và mở channel theo họ giao thức (Java 15)

> **Mục tiêu:** Hiểu vai trò của `java.nio.channels.spi.SelectorProvider` trong NIO, phân biệt **provider**, **ProtocolFamily**, **loại channel** và **địa chỉ socket**; biết cách mở `SocketChannel`, `ServerSocketChannel`, `DatagramChannel` đúng họ giao thức `INET`/`INET6`, phối hợp với `Selector`, xử lý provider/family không hỗ trợ và nhận diện hỗ trợ Unix-domain stream sockets trên Java hiện đại. Bài thuộc nhóm **Protocol family** của Java 15. Những API được trình bày **vẫn còn áp dụng đến hiện nay**, không dựa vào lớp nội bộ `sun.nio.*` hay cơ chế đã lỗi thời; các chương trình kiểm thử dùng **Java 17+** và không bật preview.

## 1. Đâu là điểm liên quan trực tiếp đến Java 15?

`SelectorProvider` đã xuất hiện từ **Java 1.4** để cung cấp các implementation NIO cho selectable channels và selectors. `ProtocolFamily` cùng `StandardProtocolFamily.INET`/`INET6` và `SelectorProvider.openDatagramChannel(ProtocolFamily)` có từ **Java 7**.

Điểm bổ sung quan trọng ở **Java 15** là hai phương thức **mở TCP-style stream channels theo họ giao thức** trên provider:

~~~java
SelectorProvider provider = SelectorProvider.provider();

SocketChannel client =
        provider.openSocketChannel(StandardProtocolFamily.INET);

ServerSocketChannel server =
        provider.openServerSocketChannel(StandardProtocolFamily.INET);
~~~

Đây là **đoạn mã trong method**, cần import `java.nio.channels.*`, `java.nio.channels.spi.SelectorProvider`, `java.net.StandardProtocolFamily` và quản lý `IOException`/đóng channels.

Cùng từ Java 15, các factory tĩnh được thêm để chuyển tiếp xuống default provider:

~~~java
SocketChannel client =
        SocketChannel.open(StandardProtocolFamily.INET);

ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.INET);
~~~

Hai API `open(ProtocolFamily)` này được đánh dấu **Since: 15** trong Javadoc. Khi không chỉ định family, `SocketChannel.open()` và `ServerSocketChannel.open()` sử dụng Internet protocol socket theo cách mặc định của hệ thống.

**Không quy toàn bộ NIO/provider/family về Java 15.** Cần phân biệt mốc phát triển:

| API / tính năng | Có từ | Ý nghĩa |
| --- | --- | --- |
| `SelectorProvider`, `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`, `Selector` | Java 1.4 | Kiến trúc NIO provider và selectable channels |
| `ProtocolFamily`, `StandardProtocolFamily.INET`/`INET6` | Java 7 | Biểu diễn họ giao thức IPv4/IPv6 |
| `DatagramChannel.open(ProtocolFamily)` | Java 7 | Mở UDP channel chọn họ IP tường minh |
| `SelectorProvider.openDatagramChannel(ProtocolFamily)` | Java 7 | Provider factory cho UDP theo family |
| `SelectorProvider.openSocketChannel(ProtocolFamily)` | **Java 15** | Provider factory cho stream client chọn family |
| `SelectorProvider.openServerSocketChannel(ProtocolFamily)` | **Java 15** | Provider factory cho stream server chọn family |
| `SocketChannel.open(ProtocolFamily)`, `ServerSocketChannel.open(ProtocolFamily)` | **Java 15** | Tĩnh factory chuyển xuống provider mặc định |
| `StandardProtocolFamily.UNIX`, Unix-domain socket channels | **Java 16** | Local interprocess communication theo filesystem path |
| `SelectorProvider.provider()` / `Selector.open()` | API có từ trước Java 15 | Lấy default provider và selector do provider cung cấp |

**Ý nghĩa học tập:** Java 15 làm cho các API stream channel có thêm khả năng **yêu cầu protocol family cụ thể** giống API datagram trước đó. Trên Java hiện đại, ba họ giao thức chuẩn thường thấy là `INET`, `INET6` và `UNIX`, nhưng **không phải mọi loại channel hỗ trợ mọi họ**.

## 2. Phân biệt bốn khái niệm trước khi viết code

| Khái niệm | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **SelectorProvider** | Nhà cung cấp implementation cho selectors/channels | `SelectorProvider.provider()` |
| **ProtocolFamily** | Họ giao thức socket được yêu cầu khi tạo channel | `StandardProtocolFamily.INET`, `INET6`, `UNIX` |
| **Channel kind** | Mô hình vận chuyển/loại endpoint được tạo | `DatagramChannel` (datagram), `SocketChannel` (stream client), `ServerSocketChannel` (stream listener) |
| **SocketAddress** | Địa chỉ cụ thể dùng để bind/connect/send | `InetSocketAddress` (IP+port), `UnixDomainSocketAddress` (path) |

**Một family không đồng nghĩa một transport.** `INET` nghĩa là chọn họ địa chỉ **IPv4**; nó không tự có nghĩa TCP hay UDP. Loại channel quyết định mô hình I/O:

- `DatagramChannel` với `INET`: **UDP/IPv4**.
- `SocketChannel` với `INET`: **stream TCP/IPv4**.
- `ServerSocketChannel` với `INET`: **TCP listener/IPv4**.
- `SocketChannel` hoặc `ServerSocketChannel` với `UNIX`: **Unix-domain stream socket** khi JDK/OS hỗ trợ.
- `DatagramChannel` với `UNIX`: **không hỗ trợ** theo API JDK hiện hành.

**Provider không phải network protocol.** `SelectorProvider` là cơ chế chọn **implementation I/O** của Java NIO. Chọn một provider khác không tự mã hóa kết nối, không làm UDP thành TCP và không biến một family không hỗ trợ thành được hỗ trợ.

## 3. Các họ giao thức chuẩn: INET, INET6, UNIX

Java định nghĩa `java.net.ProtocolFamily` và `java.net.StandardProtocolFamily`:

~~~java
StandardProtocolFamily.INET
StandardProtocolFamily.INET6
StandardProtocolFamily.UNIX
~~~

**`INET`:** Họ **IPv4**. Với chương trình thử nghiệm đáng tin cậy, thường bind vào `127.0.0.1` và cổng `0` để hệ điều hành chọn cổng local trống. Đây là cấu hình loopback, không tiếp nhận kết nối từ mạng bên ngoài.

**`INET6`:** Họ **IPv6**. Có thể bind IPv6 loopback `::1` khi OS/JVM hỗ trợ. Không mặc định runtime nào cũng có IPv6; một số máy/cấu hình tắt IPv6 hoặc dùng thuộc tính JVM ảnh hưởng IP stack. Thao tác mở family này có thể ném `UnsupportedOperationException` hoặc `IOException`.

**`UNIX`:** Họ **Unix domain socket** cho local IPC, bổ sung trong **Java 16**, không phải Java 15. Với `SocketChannel`/`ServerSocketChannel`, địa chỉ thường là `UnixDomainSocketAddress` chứa một đường dẫn filesystem. Hỗ trợ phụ thuộc platform/provider, và **không thể dùng `DatagramChannel.open(UNIX)`** trong JDK hiện hành.

| Family | Địa chỉ phù hợp | DatagramChannel | SocketChannel | ServerSocketChannel |
| --- | --- | --- | --- | --- |
| `INET` | `InetSocketAddress` dùng IPv4 | Có, khi OS hỗ trợ IPv4 | Có | Có |
| `INET6` | `InetSocketAddress` dùng IPv6 | Có nếu IPv6 được bật | Có nếu IPv6 được bật | Có nếu IPv6 được bật |
| `UNIX` (Java 16+) | `UnixDomainSocketAddress` | **Không hỗ trợ** | Có nếu platform/provider hỗ trợ | Có nếu platform/provider hỗ trợ |

**Không đánh đồng INET6 với “IPv4+IPv6 luôn cùng hoạt động”.** Khả năng IPv4-mapped IPv6, dual-stack, socket options và multicast phụ thuộc OS/JVM. Khi giao thức bắt buộc IPv4 hoặc IPv6, hãy chọn family tường minh và kiểm tra thông qua một test thật thay vì suy từ `getLocalAddress()` chưa bind.

## 4. `SelectorProvider.provider()` là gì?

~~~java
import java.nio.channels.spi.SelectorProvider;

SelectorProvider defaultProvider = SelectorProvider.provider();
~~~

`provider()` trả về **default provider duy nhất trên toàn JVM** tại thời điểm runtime chạy. Lần gọi đầu tiên chọn provider theo quy trình của Javadoc; những lần gọi sau trả lại **cùng một provider instance**.

Một cách khái quát, provider được chọn qua:

1. Thuộc tính hệ thống JVM `java.nio.channels.spi.SelectorProvider` nếu được định nghĩa, trỏ đến tên lớp provider tương ứng.
2. Cấu hình service-provider phù hợp trong `META-INF/services/java.nio.channels.spi.SelectorProvider` khi được runtime tìm thấy.
3. Nếu không có cấu hình thay thế, **provider mặc định do JDK/platform cung cấp**.

**Không nên cấu hình custom provider chỉ để chọn IPv4/IPv6.** Hãy dùng `open(StandardProtocolFamily.INET/INET6)` trước. Cấu hình provider thay thế là công việc đặc biệt dành cho implementation I/O; cần hiểu constructor, class loading, module, provider compatibility và cả đời JVM.

**Không tự tạo instance bằng một lớp triển khai nội bộ như `sun.nio.ch.*`.** Những tên lớp đó không phải public API ổn định. Code ứng dụng nên dùng **`SelectorProvider.provider()` hoặc các static factories**, để JDK lựa chọn implementation phù hợp.

### Factory tĩnh là đường vào default provider

Các factory tĩnh dùng provider mặc định:

~~~java
DatagramChannel dc = DatagramChannel.open(StandardProtocolFamily.INET);
SocketChannel sc = SocketChannel.open(StandardProtocolFamily.INET);
ServerSocketChannel ssc =
        ServerSocketChannel.open(StandardProtocolFamily.INET);
Selector selector = Selector.open();
~~~

Về mặt thiết kế, chúng tương ứng với việc yêu cầu:

~~~java
SelectorProvider p = SelectorProvider.provider();

DatagramChannel dc = p.openDatagramChannel(StandardProtocolFamily.INET);
SocketChannel sc = p.openSocketChannel(StandardProtocolFamily.INET);
ServerSocketChannel ssc =
        p.openServerSocketChannel(StandardProtocolFamily.INET);
Selector selector = p.openSelector();
~~~

Đây là **hai cách tạo các object mới tương đương về provider được yêu cầu**, **không phải cùng một object channel**. Trong code thật, đặt các channels/selectors trong `try-with-resources` để đóng. Không nên sao chép hai đoạn liên tiếp vào cùng method khi trùng tên biến như trên.

## 5. Ba phương thức provider factory có family và mốc tương thích

| Provider method | Loại trả về | Since | Hành vi tổng quan |
| --- | --- | --- | --- |
| `openDatagramChannel(ProtocolFamily family)` | `DatagramChannel` | 1.7 | Tạo datagram channel chọn family; từ chối family không hỗ trợ |
| `openSocketChannel(ProtocolFamily family)` | `SocketChannel` | **15** | Tạo stream client chưa connected, chọn family |
| `openServerSocketChannel(ProtocolFamily family)` | `ServerSocketChannel` | **15** | Tạo stream listener chưa bind, chọn family |
| `openSelector()` | `AbstractSelector` | 1.4 | Tạo selector gắn với provider |
| `openDatagramChannel()` | `DatagramChannel` | 1.4 | Không chỉ định family, do platform/provider chọn |
| `openSocketChannel()` | `SocketChannel` | 1.4 | Stream client mặc định Internet protocol |
| `openServerSocketChannel()` | `ServerSocketChannel` | 1.4 | Stream listener mặc định Internet protocol |

### Vì sao hai overload stream mới có thể ném UnsupportedOperationException trên custom provider?

Javadoc của `SelectorProvider` định nghĩa **default implementation** của hai phương thức `openSocketChannel(ProtocolFamily)` và `openServerSocketChannel(ProtocolFamily)` **kiểm tra family không null rồi ném `UnsupportedOperationException`**. Một provider tùy chỉnh muốn hỗ trợ factory theo family phải cung cấp implementation thích hợp.

Vì thế:

- **Provider cũ** có thể vẫn hỗ trợ `openSocketChannel()` không tham số nhưng **không hỗ trợ** `openSocketChannel(INET)`.
- Tên family là enum chuẩn **không bảo đảm mọi provider đều hỗ trợ**.
- Bắt `UnsupportedOperationException` đúng phạm vi là cách báo **không hỗ trợ**, không phải lý do im lặng chuyển sang một transport/family khác khi hợp đồng bắt buộc một family cụ thể.
- `openDatagramChannel(ProtocolFamily)` có từ Java 7 và là **phương thức abstract** trong provider, không có default implementation tương tự hai overload stream kể trên.

**Nói rõ API boundary:** Sự khác nhau về **mốc Since** và **default implementation** là lý do cần hiểu sự thay đổi từ Java 15, thay vì xem mọi factory provider là một overload hoàn toàn đồng nhất.

## 6. Channel được tạo ra vẫn cần bind/connect

**Mở channel không phải hoàn thành kết nối.**

Với TCP client:

~~~java
try (SocketChannel client =
             SocketChannel.open(StandardProtocolFamily.INET)) {
    System.out.println(client.isConnected()); // false
    client.connect(remoteInetSocketAddress);
}
~~~

`remoteInetSocketAddress` là `InetSocketAddress` hợp lệ do ứng dụng cung cấp; code chỉ minh họa trong method. `SocketChannel.open(INET)` tạo socket **chưa connected**. Muốn truyền dữ liệu, phải `connect` tới server.

Với TCP server:

~~~java
try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.INET)) {
    server.bind(new InetSocketAddress(
            InetAddress.getByName("127.0.0.1"), 0));
    // server.accept() có thể chờ kết nối đến.
}
~~~

Server channel mới mở **chưa bind**. `accept()` trước `bind(...)` ném `NotYetBoundException`. Cổng `0` khi bind để OS tự chọn; lấy cổng thực tế bằng `server.getLocalAddress()`.

Với UDP:

~~~java
try (DatagramChannel udp =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    udp.bind(new InetSocketAddress(
            InetAddress.getByName("127.0.0.1"), 0));
    // udp.receive(buffer) để nhận; udp.send(buffer, target) để gửi.
}
~~~

`DatagramChannel` mới mở **chưa connected**; `send(ByteBuffer,target)` và `receive(ByteBuffer)` có thể sử dụng ngay cả khi chưa `connect`. `read`/`write` của `DatagramChannel` yêu cầu **connected peer**. Việc `bind` tường minh giúp kiểm soát địa chỉ local; một số thao tác I/O có thể tự động bind nếu chưa bind.

**Không nhập nhằng địa chỉ:** `INET/INET6` dùng `InetSocketAddress`, trong khi Unix-domain stream dùng `UnixDomainSocketAddress`. Chọn sai loại address có thể gây `UnsupportedAddressTypeException`; family và địa chỉ là **hai yếu tố cần khớp**.

## 7. Chương trình đầy đủ Java 17+: default provider, UDP, TCP và Selector

Tạo file **ProtocolFamilyProviderDemo.java**; chương trình dùng **IPv4 loopback** nên không phụ thuộc IPv6 hoặc Unix-domain support. Nó kiểm tra:

1. `SelectorProvider.provider()` trả **cùng singleton**.
2. `DatagramChannel.open(INET)` và `provider.openDatagramChannel(INET)` có cùng provider.
3. `provider.openSelector()` tạo selector cùng provider, dùng được với channel.
4. UDP gửi một datagram, selector báo readable, nhận đúng bytes.
5. `provider.openServerSocketChannel(INET)` và `provider.openSocketChannel(INET)` tạo TCP endpoints, kết nối và truyền dữ liệu thành công.
6. `DatagramChannel.open(UNIX)` bị từ chối bằng `UnsupportedOperationException` theo API hiện hành.

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.net.SocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.channels.spi.SelectorProvider;
import java.nio.charset.StandardCharsets;

public class ProtocolFamilyProviderDemo {
    public static void main(String[] args) throws Exception {
        SelectorProvider provider = SelectorProvider.provider();
        System.out.println("defaultProviderSingleton="
                + (provider == SelectorProvider.provider()));

        InetAddress ipv4Loopback = InetAddress.getByName("127.0.0.1");

        try (DatagramChannel receiver =
                     provider.openDatagramChannel(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             Selector selector = provider.openSelector();
             ServerSocketChannel server =
                     provider.openServerSocketChannel(StandardProtocolFamily.INET);
             SocketChannel client =
                     provider.openSocketChannel(StandardProtocolFamily.INET)) {

            System.out.println("receiverProviderMatches="
                    + (receiver.provider() == provider));
            System.out.println("senderProviderMatches="
                    + (sender.provider() == provider));
            System.out.println("selectorProviderMatches="
                    + (selector.provider() == provider));
            System.out.println("serverProviderMatches="
                    + (server.provider() == provider));
            System.out.println("clientProviderMatches="
                    + (client.provider() == provider));
            System.out.println("datagramInitiallyUnconnected="
                    + !receiver.isConnected());
            System.out.println("clientInitiallyUnconnected="
                    + !client.isConnected());

            receiver.bind(new InetSocketAddress(ipv4Loopback, 0));
            receiver.configureBlocking(false);
            receiver.register(selector, SelectionKey.OP_READ);

            sender.send(
                    ByteBuffer.wrap(
                            "udp-v4".getBytes(StandardCharsets.UTF_8)),
                    receiver.getLocalAddress());

            int selected = selector.select(3000);
            if (selected == 0) {
                throw new AssertionError("No readable datagram");
            }

            ByteBuffer udpData = ByteBuffer.allocate(64);
            SocketAddress udpSender = receiver.receive(udpData);
            if (udpSender == null) {
                throw new AssertionError("Receive returned no datagram");
            }
            udpData.flip();
            String udpMessage =
                    StandardCharsets.UTF_8.decode(udpData).toString();

            System.out.println("udpPayload=" + udpMessage);
            System.out.println("udpSenderPresent=" + (udpSender != null));
            System.out.println("receiverIpv4="
                    + (((InetSocketAddress) receiver.getLocalAddress())
                            .getAddress() instanceof java.net.Inet4Address));

            selector.selectedKeys().clear();

            server.bind(new InetSocketAddress(ipv4Loopback, 0));
            client.connect(server.getLocalAddress());
            try (SocketChannel accepted = server.accept()) {
                System.out.println("tcpConnected="
                        + (client.isConnected() && accepted.isConnected()));
                System.out.println("acceptedProviderMatches="
                        + (accepted.provider() == provider));

                ByteBuffer outgoing = ByteBuffer.wrap(
                        "tcp-v4".getBytes(StandardCharsets.UTF_8));
                while (outgoing.hasRemaining()) {
                    client.write(outgoing);
                }

                ByteBuffer incoming = ByteBuffer.allocate(64);
                int size = accepted.read(incoming);
                if (size <= 0) {
                    throw new AssertionError("No TCP data");
                }
                incoming.flip();

                System.out.println("tcpPayload="
                        + StandardCharsets.UTF_8.decode(incoming));
            }
            System.out.println("serverIpv4="
                    + (((InetSocketAddress) server.getLocalAddress())
                            .getAddress() instanceof java.net.Inet4Address));
        }

        try {
            DatagramChannel.open(StandardProtocolFamily.UNIX).close();
            System.out.println("unixDatagram=UNEXPECTED");
        } catch (UnsupportedOperationException expected) {
            System.out.println("unixDatagram=UnsupportedOperationException");
        }
    }
}
~~~

Chạy trong thư mục chứa file, với Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 ProtocolFamilyProviderDemo.java
java ProtocolFamilyProviderDemo
~~~

**Stdout đã được biên dịch/chạy kiểm chứng trên môi trường có IPv4 loopback và provider mặc định:**

~~~text
defaultProviderSingleton=true
receiverProviderMatches=true
senderProviderMatches=true
selectorProviderMatches=true
serverProviderMatches=true
clientProviderMatches=true
datagramInitiallyUnconnected=true
clientInitiallyUnconnected=true
udpPayload=udp-v4
udpSenderPresent=true
receiverIpv4=true
tcpConnected=true
acceptedProviderMatches=true
tcpPayload=tcp-v4
serverIpv4=true
unixDatagram=UnsupportedOperationException
~~~

**Lưu ý về môi trường:** Network policy có thể chặn cả kết nối loopback trong một sandbox, gây lỗi mạng/timeout dù code và API đúng. `selector.select(3000)` chờ readiness tối đa khoảng 3 giây; nó **không bảo đảm datagram đã tới trong mọi môi trường**. Chương trình assert nếu không có gói, thay vì in một kết quả giả là thành công.

## 8. Giải thích kết quả: provider identity không phải channel identity

`defaultProviderSingleton=true` xác nhận hai lời gọi `SelectorProvider.provider()` trong cùng JVM trả về **cùng object provider**.

Các dòng `receiverProviderMatches`, `senderProviderMatches`, `selectorProviderMatches`, `serverProviderMatches` và `clientProviderMatches` đều true cho biết:

- Channel tạo qua `provider.openDatagramChannel(INET)` giữ reference tới provider đó.
- Channel tạo qua **static** `DatagramChannel.open(INET)` được tạo bởi **cùng default provider**.
- Selector tạo qua `provider.openSelector()` thuộc provider đó.
- Hai stream channels client/server mở qua provider đều thuộc provider mặc định.
- Kênh được `server.accept()` trả về cũng thuộc provider tương ứng ở môi trường thử nghiệm.

**Điểm quan trọng:** `receiver.provider() == sender.provider()` là true **không có nghĩa receiver == sender**. Chúng là **hai UDP sockets khác nhau**, chỉ dùng chung provider implementation. Đừng suy từ provider identity ra cùng cổng, cùng queue, cùng peer hoặc cùng connection.

### `INet` và địa chỉ IPv4

Trong ví dụ, `INET` cùng `InetAddress.getByName("127.0.0.1")` khiến địa chỉ bind thực tế là IPv4. Các dòng `receiverIpv4=true` và `serverIpv4=true` kiểm tra `Inet4Address` sau bind. Không dựa vào string nội bộ của provider để nhận diện family; hãy dùng API chuẩn và địa chỉ mong muốn.

### Tại sao UDP message và TCP message đều thành công?

Cả hai đều dùng `INET` nhưng:

- UDP gửi **một datagram** `udp-v4` và nhận với `DatagramChannel.receive`; `Selector` báo readiness của kênh non-blocking.
- TCP tạo **kết nối stream** thông qua `client.connect(server.getLocalAddress())` và `server.accept()`; sau đó `write` và `read` truyền bytes `tcp-v4`.

Đây là bằng chứng thực tế rằng **protocol family và channel kind độc lập**. Một lựa chọn IPv4 không tự biến tất cả channel thành UDP hoặc TCP.

### `unixDatagram=UnsupportedOperationException`

JDK hỗ trợ `UNIX` cho stream channel trên platform thích hợp, **không** hỗ trợ `UNIX` trong `DatagramChannel.open(ProtocolFamily)`. Điều này **không** đồng nghĩa mọi Unix-domain datagram API trên thế giới đều không tồn tại; chỉ là **đặc tả của DatagramChannel trong Java hiện hành** không cho phép nó.

## 9. SelectorProvider và Selector: phải tương thích provider

Một selector và channel có thể đăng ký với nhau qua:

~~~java
SelectorProvider provider = SelectorProvider.provider();

try (DatagramChannel dc =
             provider.openDatagramChannel(StandardProtocolFamily.INET);
     Selector selector = provider.openSelector()) {
    dc.configureBlocking(false);
    SelectionKey key = dc.register(selector, SelectionKey.OP_READ);
    // Chờ selector.select(timeout) rồi xử lý readiness.
}
~~~

Đây là **đoạn mã minh họa trong method**. Không có người gửi nên nếu thêm `select()` chờ vô hạn có thể bị treo.

### Quy tắc đăng ký

1. Channel phải **selectable** và ở **non-blocking mode** trước khi `register`.
2. `interestOps` phải thuộc những operations mà channel hỗ trợ. Với datagram, đọc/ghi: `OP_READ` và `OP_WRITE`.
3. Selector phải **cùng provider phù hợp** với selectable channel. Nếu dùng một custom provider khác không tương thích, `register` có thể ném **`IllegalSelectorException`**.
4. `selector.select(timeout)` báo readiness, **không tự đọc bytes**; phải gọi `channel.receive/read`.
5. Sau khi xử lý `selectedKeys`, phải **xóa/cập nhật keys đã xử lý** để không xử lý lặp kết quả cũ.
6. Khi không còn sử dụng, đóng selector và channels; dùng `try-with-resources`, không giữ file descriptors vô hạn.

**Không dùng `SelectionKey.OP_ACCEPT` cho `DatagramChannel`.** `OP_ACCEPT` chỉ hợp lệ với server socket channels hỗ trợ accept; `OP_CONNECT` áp dụng cho socket channels khi non-blocking connect. `validOps()` giúp biết loại interest phù hợp.

### Lỗi thường gặp khi đăng ký

~~~java
DatagramChannel udp =
        DatagramChannel.open(StandardProtocolFamily.INET);
Selector selector = Selector.open();

// udp.register(selector, SelectionKey.OP_READ);
// Sai nếu udp vẫn đang blocking.
~~~

Lời gọi register khi blocking có thể gây **`IllegalBlockingModeException`**. Phải:

~~~java
udp.configureBlocking(false);
udp.register(selector, SelectionKey.OP_READ);
~~~

Đây là mã minh họa; cần đóng `udp`/`selector` hoặc đặt trong `try-with-resources`. Chuyển channel **trở lại blocking** trong lúc vẫn có valid selector registration cũng không hợp lệ; hãy hủy key và đợi deregistration xử lý trước.

## 10. IPv6 là một khả năng cần kiểm tra, không phải default bảo đảm

Ví dụ chọn IPv6 tường minh:

~~~java
try (DatagramChannel ipv6 =
             DatagramChannel.open(StandardProtocolFamily.INET6)) {
    // Có thể bind vào ::1 khi IPv6 được cho phép.
}
~~~

**Không nên** dựa vào `DatagramChannel.open()` không family rồi đoán rằng JVM đã chọn IPv6 (hoặc hỗ trợ đồng thời cả IPv4 và IPv6). Javadoc nêu family khi không truyền tham số là **phụ thuộc platform và cấu hình**. Nếu chương trình join một **IPv6 multicast group**, family của datagram socket phải phù hợp với nhóm đó.

### Thực hành triển khai đa môi trường

Nếu ứng dụng yêu cầu IPv6:

- Yêu cầu `StandardProtocolFamily.INET6` **tường minh**.
- Dùng địa chỉ `Inet6Address`/`InetSocketAddress` tương ứng.
- Kiểm tra khả năng open/bind/connect trên **môi trường thật**.
- Xử lý `UnsupportedOperationException` hoặc `IOException` khi không có support.
- Nếu IPv6 là **yêu cầu bắt buộc**, không im lặng fallback xuống IPv4 rồi tuyên bố giữ nguyên security/network contract.
- Nếu protocol cho phép cả hai, thiết kế **policy fallback có chủ đích**, ghi nhận family thực tế và kiểm tra kết nối.

**Không dùng một câu “INET6 luôn chứa INET”** như quy tắc Java: tương tác IPv4-mapped IPv6 và dual-stack thay đổi theo OS, JVM và cấu hình socket.

## 11. Unix-domain stream channels trên Java 16+: phân biệt chính xác với Java 15

`StandardProtocolFamily.UNIX` và Unix-domain socket channels được chuẩn hóa **từ Java 16**, dựa trên các overload chọn family đã xuất hiện trong Java 15. Chúng vẫn được hỗ trợ trong Java hiện đại.

~~~java
try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX);
     SocketChannel client =
             SocketChannel.open(StandardProtocolFamily.UNIX)) {
    // Để giao tiếp thật, server phải bind bằng UnixDomainSocketAddress.
    // Sau đó client connect tới cùng UnixDomainSocketAddress.
}
~~~

Đây là **đoạn mã minh họa**. Nó chỉ kiểm tra **mở stream endpoints**, chưa bind/connect và chưa gửi dữ liệu. Trên nền tảng không hỗ trợ, `open(UNIX)` có thể ném `UnsupportedOperationException` hoặc `IOException`.

Khi sử dụng thực tế:

- Dùng `UnixDomainSocketAddress.of(path)` cho địa chỉ **filesystem path**.
- Kiểm tra độ dài path phù hợp OS; hạn mức tên Unix domain socket thường khác nhau giữa các platform.
- Quản lý permissions, quyền truy cập filesystem và vòng đời file socket.
- Sau khi đóng server socket, file pathname có thể còn tồn tại; ứng dụng phải cleanup theo chính sách nếu nó tạo path.
- Không truyền `InetSocketAddress` cho Unix-domain endpoint hoặc `UnixDomainSocketAddress` cho IP endpoint.
- Không tìm `DatagramChannel.open(UNIX)` như một cách mở Unix datagram socket bằng Java NIO chuẩn.

**Điểm tinh tế:** Việc `openSocketChannel(ProtocolFamily)` có từ **Java 15** không nghĩa hằng `StandardProtocolFamily.UNIX` đã có ở chính Java 15. Ví dụ trong bài dùng Java 17 để kiểm thử cả mốc Java 15 và khả năng **Java 16+** còn áp dụng hiện nay, không đánh đồng niên đại.

## 12. Chương trình thứ hai: dò family support có điều kiện

Tạo file **ProtocolFamilyOptionalDemo.java**. Nó không cần bind, không cần mở cổng mạng thật và không cần Unix socket file. Mục tiêu là kiểm tra **provider hỗ trợ việc mở channel theo family hay không**, không phải kiểm tra kết nối tới peer.

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.nio.channels.DatagramChannel;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.channels.spi.SelectorProvider;

public class ProtocolFamilyOptionalDemo {
    public static void main(String[] args) throws Exception {
        SelectorProvider provider = SelectorProvider.provider();

        try (DatagramChannel datagram6 =
                     provider.openDatagramChannel(StandardProtocolFamily.INET6)) {
            System.out.println("ipv6Available=true");
            System.out.println("ipv6ProviderMatches="
                    + (datagram6.provider() == provider));
        } catch (UnsupportedOperationException | IOException unsupported) {
            System.out.println("ipv6Available=false");
        }

        try (ServerSocketChannel server =
                     provider.openServerSocketChannel(StandardProtocolFamily.UNIX);
             SocketChannel client =
                     provider.openSocketChannel(StandardProtocolFamily.UNIX)) {
            System.out.println("unixStreamAvailable=true");
            System.out.println("unixProviderMatches="
                    + (server.provider() == provider
                    && client.provider() == provider));
        } catch (UnsupportedOperationException | IOException unsupported) {
            System.out.println("unixStreamAvailable=false");
        }

        try (DatagramChannel unsupported =
                     provider.openDatagramChannel(StandardProtocolFamily.UNIX)) {
            System.out.println("unixDatagram=UNEXPECTED");
        } catch (UnsupportedOperationException expected) {
            System.out.println("unixDatagram=UnsupportedOperationException");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 ProtocolFamilyOptionalDemo.java
java ProtocolFamilyOptionalDemo
~~~

**Stdout của môi trường thử nghiệm đã chạy:**

~~~text
ipv6Available=true
ipv6ProviderMatches=true
unixStreamAvailable=true
unixProviderMatches=true
unixDatagram=UnsupportedOperationException
~~~

**Đừng coi những dòng `ipv6Available=true` và `unixStreamAvailable=true` là output bắt buộc trên mọi hệ điều hành.** Nếu platform không hỗ trợ, chương trình có thể in `ipv6Available=false` hoặc `unixStreamAvailable=false` thay thế, đúng theo thiết kế. Hơn nữa, **mở được channel** chưa chứng minh bind/listen/connect và các options mà ứng dụng cần đều hoạt động; muốn kết luận sẵn sàng triển khai, cần thử các bước đó.

**Phân biệt kiểm thử support và hành vi chuẩn:** Với `DatagramChannel`, `UNIX` không hỗ trợ theo API; chương trình in `unixDatagram=UnsupportedOperationException` trong JDK kiểm thử. Với `SocketChannel`/`ServerSocketChannel`, khả năng hỗ trợ Unix-domain stream là điều kiện phụ thuộc OS/provider nên không assert cố định.

## 13. Hợp đồng mạng: TCP stream và UDP datagram dù cùng family

Chọn `INET` cho cả UDP và TCP không khiến hai API cùng semantics.

### UDP / DatagramChannel

- Mỗi `send(ByteBuffer,target)` chuyển **một datagram** tới target (nếu thành công).
- `receive(ByteBuffer)` nhận **một datagram** và trả địa chỉ sender.
- Nếu receive buffer không đủ, phần dư datagram có thể **bị loại bỏ**, không xuất hiện lại như mảnh tiếp theo.
- UDP không bảo đảm delivery, ordering, deduplication, confidentiality hay peer identity.
- Có thể `connect` UDP để chọn peer mặc định, nhưng đó **không phải TCP handshake**.

### TCP / SocketChannel

- TCP cung cấp **dòng bytes có thứ tự** trong một kết nối, không bảo toàn ranh giới của mỗi lần `write` như packet message.
- Một lời gọi `read` có thể đọc **ít bytes hơn** `write` ở phía gửi, nhất là khi dữ liệu lớn hoặc non-blocking.
- Ví dụ mục 7 dùng chuỗi `tcp-v4` rất ngắn nên một lần `read` đã đủ trong môi trường thử nghiệm; **không dùng giả định đó làm framing cho giao thức thực**.
- Production nên có **message framing** rõ ràng (fixed-length header, length prefix, delimiter được escape, hoặc protocol parser) và vòng lặp đọc tới khi đủ message/EOF/error.
- `SocketChannel.connect` trong non-blocking mode có thể cần `finishConnect`; dùng `SelectionKey.OP_CONNECT` nếu triển khai NIO event loop.

**Tách rời semantics và family:** `INET6` thay địa chỉ sang IPv6 nhưng không biến TCP thành datagram, cũng không biến UDP thành connection reliable.

## 14. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `UnsupportedOperationException` khi mở family | Provider/OS không hỗ trợ family; ví dụ `UNIX` trên datagram | Kiểm tra compatibility; chỉ fallback khi protocol cho phép |
| `IOException` khi open/bind/connect | Hạn chế tài nguyên, OS policy, network config | Báo lỗi thật, cleanup, thử lại nếu policy cho phép |
| `NullPointerException` với family null | API yêu cầu `ProtocolFamily` không null | Kiểm tra config trước khi gọi factory |
| `UnsupportedAddressTypeException` | Dùng family và address sai loại | Ghép đúng `INET/INET6` với `InetSocketAddress`, `UNIX` với `UnixDomainSocketAddress` |
| `BindException` | Cổng/path đã dùng hoặc không được phép | Dùng cổng 0 trong test, giải phóng tài nguyên/đúng quyền |
| `NotYetBoundException` khi `server.accept` | Server channel chưa `bind` | Bind địa chỉ trước khi accept |
| `NotYetConnectedException` khi `client.read/write` | Stream client chưa connected | Connect/finishConnect đúng cách |
| `IllegalBlockingModeException` khi register | Channel còn ở blocking mode | `configureBlocking(false)` rồi register |
| `IllegalSelectorException` khi register | Channel và selector thuộc providers không tương thích | Tạo chúng từ cùng provider |
| `IllegalArgumentException` khi interestOps | Dùng invalid operations cho loại channel | Kiểm tra `validOps()` |
| `ClosedChannelException` | Channel đã đóng | Dừng I/O, tạo channel mới nếu cần |
| Non-blocking UDP `receive` trả `null` | Chưa có datagram sẵn | Đợi `Selector` hoặc retry theo event loop |
| TCP `read` trả ít bytes | Stream không giữ message boundaries | Implement framing + vòng lặp đọc |
| IPv6 không chạy dù code hợp lệ | OS/JVM tắt IPv6 hoặc sai địa chỉ | Feature detection, kiểm tra config thực |
| Unix socket path không bind được | OS không hỗ trợ, path dài/quyền hoặc file cũ | Dùng path hợp lệ, cleanup theo ownership |
| Selector có readiness nhưng app không thấy dữ liệu | Readiness có thể thay đổi do thread khác đọc/close | Kiểm tra trạng thái trả về, không giả định sẵn dữ liệu vĩnh viễn |

**Đừng bắt mọi exception rồi chuyển thành success.** Một factory mở channel thất bại là lỗi cấu hình/khả năng hỗ trợ hoặc tài nguyên cần được xử lý cụ thể. Nếu family là yêu cầu bảo mật (ví dụ chỉ cho local IPC), **không tự fallback ra IP network socket** và mở rộng bề mặt truy cập ngoài ý muốn.

## 15. Custom SelectorProvider: khi nào thực sự cần?

`java.nio.channels.spi` là **service-provider interface (SPI)**. Một custom provider có thể triển khai I/O multiplexing theo môi trường đặc biệt và override các factories. Đây là việc dành cho nhu cầu rất đặc thù, không phải bước cần thiết để dùng `StandardProtocolFamily.INET`.

Có thể xem mối quan hệ:

~~~text
Application
   |
   +-- DatagramChannel.open(INET)
   +-- SocketChannel.open(INET)
   +-- ServerSocketChannel.open(INET)
   +-- Selector.open()
             |
             v
    SelectorProvider.provider()
             |
             +-- openDatagramChannel(family)
             +-- openSocketChannel(family)
             +-- openServerSocketChannel(family)
             +-- openSelector()
             |
             v
       OS / JDK I/O implementation
~~~

**Lợi ích của public abstraction:** Application không cần biết lớp cụ thể bên dưới; JDK có thể thay đổi implementation qua các phiên bản mà contract public API vẫn giữ.

**Nếu thật sự dùng custom provider:**

- Bảo đảm selector/channels tạo ra **tương thích**.
- Hiểu `openSocketChannel(ProtocolFamily)` và `openServerSocketChannel(ProtocolFamily)` có default method **ném `UnsupportedOperationException`** nếu chưa override; chỉ test bản overload không family là chưa đủ.
- Dùng một provider thống nhất cho tài nguyên mà bạn muốn multiplex cùng nhau.
- Không để code cấu hình ngẫu nhiên thay provider giữa lúc ứng dụng đang chạy. `provider()` là default instance được chọn khi khởi tạo JVM/provider.
- Không phụ thuộc tên `sun.nio.ch.*` hoặc class impl private; các lớp này không có compatibility guarantee.
- Kiểm thử trên các JDK/provider thực tế triển khai; đừng giả định provider thứ ba hỗ trợ toàn bộ standard families.

**Với hầu hết code Java hiện đại**, các static factory methods là đủ; chỉ lấy `SelectorProvider.provider()` trực tiếp khi bạn thực sự cần kiểm tra provider identity, tạo resource nhất quán hoặc tích hợp SPI.

## 16. Tính sẵn có và bảo mật không suy ra từ tên family

Lựa chọn `INET`, `INET6` hoặc `UNIX` giúp quyết định **phạm vi giao thức và địa chỉ**, nhưng không tự áp dụng các biện pháp bảo mật.

- **INET/INET6:** Giới hạn bind vào loopback khi chỉ phục vụ local test/service; bind vào wildcard có thể làm ứng dụng reachable qua interface mạng khác. Firewall/network policy vẫn cần được thiết kế.
- **UNIX:** Thường dùng filesystem path và quyền của OS; kiểm soát ai được tạo/truy cập socket path, xử lý file còn lại sau khi đóng, không giả định local nghĩa là tự động đã xác thực client.
- **TCP:** Không tự mã hóa. Nếu cần confidentiality/integrity, dùng TLS hoặc protocol bảo mật thích hợp.
- **UDP:** Không tự bảo đảm delivery, authenticity hay confidentiality. Dùng bảo vệ phù hợp (ví dụ DTLS nếu kiến trúc triển khai hỗ trợ), message validation, replay/rate limiting khi cần.
- **Provider:** Có thể do môi trường runtime cấu hình. Tránh dùng các tên provider tùy ý từ input người dùng để tải code không đáng tin.
- **Fallback:** Từ chối cấu hình không hỗ trợ theo chính sách. Ví dụ service đòi `UNIX` chỉ trong máy thì **không nên âm thầm mở `INET` wildcard** làm thay đổi security boundary.

Trong server production, bổ sung logging/analyzers cho family thực tế, địa chỉ bind và provider identity, **không cần log dữ liệu nhạy cảm của packet** để chứng minh lựa chọn giao thức đã đúng.

## 17. Checklist chọn đúng provider/family trước khi deploy

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Java minimum version là gì? | Java 15+ cho stream `open(ProtocolFamily)`; Java 16+ cho `UNIX`; code ví dụ dùng Java 17 |
| Transport là UDP hay TCP stream? | `DatagramChannel` hoặc `SocketChannel/ServerSocketChannel` đúng loại |
| Cần IPv4 hay IPv6? | Chọn `INET`/`INET6`; địa chỉ bind/connect tương ứng |
| Cần Unix-domain IPC? | Chỉ stream sockets, platform hỗ trợ, path/permissions hợp lệ |
| Có đang dùng custom SelectorProvider? | Confirm hỗ trợ overload theo family, selector tương thích |
| Selector và channel thuộc cùng provider? | `channel.provider() == selector.provider()` trong trường hợp một default provider |
| Channel đã chuyển non-blocking? | `configureBlocking(false)` trước khi register |
| Chọn đúng selection operations? | `OP_READ`/`OP_WRITE`/`OP_CONNECT`/`OP_ACCEPT` theo `validOps()` |
| Mở channel rồi đã bind/connect đúng chưa? | Server bind trước accept; stream client connect trước I/O |
| Đã quản lý ByteBuffer chưa? | `position`/`limit`/`flip`; TCP partial reads/writes, UDP truncation |
| Platform có IPv6/Unix domain support thật không? | Test open **và** bind/connect theo nhu cầu; có handling khi unsupported |
| Fallback có làm sai yêu cầu bảo mật không? | Không âm thầm đổi local Unix IPC thành network socket |
| Có cleanup tài nguyên không? | `try-with-resources` cho channels/selectors, Unix path cleanup nếu được tạo |
| Có test khi đổi JDK/OS/provider không? | Regression với môi trường hỗ trợ và không hỗ trợ |

## 18. Những hiểu nhầm phổ biến

1. **“SelectorProvider mới xuất hiện trong Java 15.”** Sai: class tồn tại từ Java 1.4; hai overload stream theo `ProtocolFamily` có từ Java 15.
2. **“`openDatagramChannel(ProtocolFamily)` là API mới của Java 15.”** Sai: có từ Java 7.
3. **“`StandardProtocolFamily.UNIX` là hằng Java 15.”** Sai: thêm từ **Java 16**.
4. **“Family `INET` nghĩa là luôn UDP.”** Sai: UDP/TCP phụ thuộc loại channel.
5. **“`INET6` chắc chắn hỗ trợ IPv4 và IPv6 đồng thời.”** Sai: dual-stack phụ thuộc platform/config.
6. **“`DatagramChannel.open(UNIX)` chạy vì JDK hỗ trợ Unix-domain sockets.”** Sai: DatagramChannel không hỗ trợ UNIX theo Javadoc.
7. **“`SocketChannel.open(INET)` đã connected.”** Sai: cần `connect`.
8. **“`ServerSocketChannel.open(INET)` đã listening.”** Sai: cần `bind`.
9. **“Hai channels có cùng `provider()` nghĩa là dùng cùng endpoint.”** Sai: provider là implementation, mỗi factory mở channel mới.
10. **“Có thể register một blocking channel vào Selector.”** Sai: cần non-blocking.
11. **“Selector báo ready nghĩa là payload tự được đọc.”** Sai: ứng dụng phải `receive/read`.
12. **“Mọi provider thứ ba hỗ trợ `openSocketChannel(INET)` vì có no-arg open.”** Sai: default method family overload của custom provider có thể ném UnsupportedOperationException.
13. **“Chỉ định protocol family sẽ thay provider implementation.”** Sai: family là input cho factory; default provider vẫn là provider JVM đã chọn.
14. **“`SelectorProvider.provider()` tạo provider mới mỗi lần.”** Sai: trả default singleton của JVM.
15. **“Đổi system property sau khi provider được chọn sẽ chuyển provider của những channels cũ.”** Sai: provider được lựa chọn khi khởi tạo và gắn với object đã tạo.
16. **“`INET` và `UNIX` dùng cùng loại SocketAddress.”** Sai: IP dùng `InetSocketAddress`, Unix IPC dùng `UnixDomainSocketAddress`.
17. **“TCP write một lần nghĩa là peer read được đúng một message.”** Sai: TCP là byte stream; cần framing.
18. **“UDP send thành công chứng minh gói tới đích.”** Sai: UDP có thể mất/chậm/trùng/lệch thứ tự.
19. **“UNIX local socket tự có TLS hoặc xác thực đầy đủ.”** Sai: cần policy và kiểm tra thích hợp.
20. **“Nếu UNIX không hỗ trợ, fallback ra INET wildcard là tương đương.”** Sai: có thể làm lộ service ra mạng ngoài.
21. **“`Selector` dùng được cho mọi tùy chọn mà không cần check validOps.”** Sai: interest ops phải phù hợp channel kind.
22. **“Mở được IPv6 channel chứng minh giao thức IPv6 hoạt động toàn tuyến.”** Sai: phải kiểm tra bind/connect/route và policy nếu cần.

## 19. Bài luyện tập và tiêu chí đạt

**Bài 1 — Phân biệt niên đại API.** Lập bảng `SelectorProvider`, `openDatagramChannel(ProtocolFamily)`, `openSocketChannel(ProtocolFamily)`, `openServerSocketChannel(ProtocolFamily)`, `StandardProtocolFamily.UNIX`. **Đạt** khi trả đúng các mốc Java 1.4/7/15/16 và không gọi mọi thứ là “mới Java 15”.

**Bài 2 — Default provider identity.** Gọi `SelectorProvider.provider()` hai lần và so bằng `==`. **Đạt** khi được `true`; nêu lý do default provider được chọn chung cho JVM.

**Bài 3 — Static factory và provider factory.** Mở `DatagramChannel.open(INET)` và `provider.openDatagramChannel(INET)`. **Đạt** khi cả hai có `provider()==defaultProvider` nhưng **không** phải cùng channel object.

**Bài 4 — TCP qua provider.** Dùng `provider.openServerSocketChannel(INET)` và `provider.openSocketChannel(INET)`, bind loopback/cổng 0, connect và accept. **Đạt** khi gửi/nhận `tcp-v4` và phân biệt TCP stream với datagram.

**Bài 5 — UDP và Selector.** Tạo receiver qua provider, cấu hình non-blocking, register `OP_READ` và gửi gói bằng channel khác. **Đạt** khi nhận `udp-v4`, sender address không null và biết `Selector` không đọc thay ứng dụng.

**Bài 6 — Blocking mode.** Thử `register` khi channel blocking, sau đó chuyển non-blocking. **Đạt** khi giải thích `IllegalBlockingModeException` và sửa đúng trình tự.

**Bài 7 — INET6 support.** Chạy `ProtocolFamilyOptionalDemo` trên hai môi trường khác nhau nếu có. **Đạt** khi hiểu support phụ thuộc platform và in `ipv6Available=false` không phải lỗi compile.

**Bài 8 — UNIX support.** Chạy `openSocketChannel(UNIX)` và `openServerSocketChannel(UNIX)` trong Java 17+, nếu hỗ trợ. **Đạt** khi biết địa chỉ thật là `UnixDomainSocketAddress`, và `DatagramChannel.open(UNIX)` không được hỗ trợ.

**Bài 9 — Sai family/address.** Thử cung cấp Unix-domain address cho IP channel hoặc ngược lại. **Đạt** khi nhận diện `UnsupportedAddressTypeException` và không fallback nguy hiểm.

**Bài 10 — Custom provider.** Một custom provider cũ mở `SocketChannel` không tham số được nhưng `openSocketChannel(INET)` ném `UnsupportedOperationException`. **Đạt** khi giải thích default implementation từ Java 15 và cần override nếu muốn hỗ trợ family overload.

**Bài 11 — TCP framing.** Tách một message lớn thành nhiều writes; phía đọc sử dụng loop cộng dồn. **Đạt** khi không giả định một lần `read` đọc đủ message, dù family là `INET` hay `INET6`.

**Bài 12 — Multicast.** Thiết kế một kênh UDP cần join nhóm IPv4 hoặc IPv6. **Đạt** khi chọn protocol family phù hợp group address và network interface, không dựa vào no-arg default.

**Bài 13 — Cleanup.** Dùng `try-with-resources` cho client, server, UDP channels và selector; quản lý Unix socket path nếu có. **Đạt** khi không để leaked sockets/file descriptors hoặc bỏ lại path ngoài ownership.

**Bài 14 — Quyết định bảo mật.** Một service phải chỉ cho phép local IPC qua Unix domain socket. **Đạt** khi nếu UNIX không được hỗ trợ, ứng dụng fail rõ ràng thay vì âm thầm mở TCP network socket với wildcard bind.

## 20. Tài liệu chính thức (đang còn hiệu lực)

- [Java SE 25 — SelectorProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/spi/SelectorProvider.html): default provider, SPI, `openDatagramChannel(ProtocolFamily)` (since 1.7), `openSocketChannel(ProtocolFamily)` và `openServerSocketChannel(ProtocolFamily)` (since **15**), default behavior của custom providers.
- [Java SE 15 — SelectorProvider](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/spi/SelectorProvider.html): đối chiếu mốc xuất hiện hai overload stream theo family trong Java 15.
- [Java SE 25 — StandardProtocolFamily](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/StandardProtocolFamily.html): `INET`, `INET6`, `UNIX` và mốc `UNIX` từ Java 16.
- [Java SE 25 — DatagramChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html): `open(ProtocolFamily)`, family/IP multicast, sự kiện non-blocking, giới hạn `UNIX`.
- [Java SE 25 — SocketChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/SocketChannel.html): `open(ProtocolFamily)`, stream connect/read/write và Unix-domain support.
- [Java SE 25 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): `open(ProtocolFamily)`, bind/accept và family-specific behavior.
- [Java SE 25 — Selector](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html): provider, readiness, selectedKeys, cancellation và selection.
- [Java SE 25 — UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/UnixDomainSocketAddress.html): filesystem path của Unix-domain IPC.
- [Java SE 25 — ProtocolFamily](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/ProtocolFamily.html): interface đại diện cho họ giao thức.

**Ghi nhớ:** `SelectorProvider` là **nhà cung cấp implementation NIO**, còn `ProtocolFamily` là **tham số chọn họ địa chỉ/giao thức**; chúng không phải một. **Java 15 bổ sung `openSocketChannel(ProtocolFamily)` và `openServerSocketChannel(ProtocolFamily)`**, trong khi overload datagram đã tồn tại từ Java 7. `INET`/`INET6` dùng cho IP sockets, `UNIX` thêm từ Java 16 dùng cho **stream local IPC**, không dùng cho `DatagramChannel`. Mở channel theo family **chưa bind hoặc connect**, muốn `Selector` phải cấu hình non-blocking và giữ tương thích provider. Kiểm thử và xử lý rõ ràng unsupported family, không âm thầm thay đổi security/network contract.
